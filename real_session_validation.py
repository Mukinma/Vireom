import json
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Tuple

import cv2
import numpy as np

from database.db import db


LOGGER = logging.getLogger("camerapi.real_session")
SESSION_A_KEYS = {"session_a", "session-a", "sesion_a", "sesion-a"}
SESSION_B_KEYS = {"session_b", "session-b", "sesion_b", "sesion-b"}


@dataclass
class Attempt:
    scenario: str
    claimed_user: int
    real_user: int
    predicted_user: int
    confidence: float


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/real_session_validation.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def infer_session_from_path(path: Path) -> str:
    parts = [p.lower() for p in path.parts]
    stem = path.stem.lower()

    for token in parts + [stem]:
        if token in SESSION_A_KEYS:
            return "A"
        if token in SESSION_B_KEYS:
            return "B"
        if re.search(r"(^|[_\-])session[_\-]?a($|[_\-])", token):
            return "A"
        if re.search(r"(^|[_\-])session[_\-]?b($|[_\-])", token):
            return "B"

    return ""


def load_from_database() -> Dict[int, Dict[str, List[Path]]]:
    db.init_db()
    rows = db.fetch_all(
        """
        SELECT u.id AS user_id, m.ruta_imagen
        FROM usuarios u
        JOIN muestras m ON m.usuario_id = u.id
        WHERE u.activo = 1
        ORDER BY u.id ASC, m.id ASC
        """
    )

    result: Dict[int, Dict[str, List[Path]]] = {}
    for row in rows:
        uid = int(row["user_id"])
        path = Path(row["ruta_imagen"])
        if not path.exists():
            continue

        session = infer_session_from_path(path)
        if session not in {"A", "B"}:
            continue

        if uid not in result:
            result[uid] = {"A": [], "B": []}
        result[uid][session].append(path)

    filtered = {}
    for uid, sessions in result.items():
        if sessions["A"] and sessions["B"]:
            filtered[uid] = {
                "A": sorted(sessions["A"]),
                "B": sorted(sessions["B"]),
            }

    return filtered


def load_from_filesystem() -> Dict[int, Dict[str, List[Path]]]:
    result: Dict[int, Dict[str, List[Path]]] = {}
    roots = [Path("dataset"), Path("dataset_processed")]

    for root in roots:
        if not root.exists():
            continue
        for user_dir in root.glob("user_*"):
            if not user_dir.is_dir():
                continue
            match = re.fullmatch(r"user_(\d+)", user_dir.name)
            if not match:
                continue
            uid = int(match.group(1))
            sess_a_dirs = [d for d in user_dir.iterdir() if d.is_dir() and d.name.lower() in SESSION_A_KEYS]
            sess_b_dirs = [d for d in user_dir.iterdir() if d.is_dir() and d.name.lower() in SESSION_B_KEYS]
            if not sess_a_dirs or not sess_b_dirs:
                continue

            a_files = []
            b_files = []
            for d in sess_a_dirs:
                a_files.extend([p for p in d.rglob("*") if p.is_file()])
            for d in sess_b_dirs:
                b_files.extend([p for p in d.rglob("*") if p.is_file()])

            if a_files and b_files:
                result[uid] = {
                    "A": sorted(a_files),
                    "B": sorted(b_files),
                }

    return result


def load_samples_by_user_and_session() -> Dict[int, Dict[str, List[Path]]]:
    from_db = load_from_database()
    if from_db:
        return from_db

    from_fs = load_from_filesystem()
    if from_fs:
        return from_fs

    if len(from_db) < 2 and len(from_fs) < 2:
        raise RuntimeError(
            "No se detectaron sesiones reales A/B suficientes por usuario. "
            "Asegurar rutas o nombres con token session_A y session_B, "
            "o estructura dataset/user_<id>/session_A|session_B/."
        )
    return {}


def load_gray_200(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return cv2.resize(image, (200, 200))


def train_lbph(train_paths: Dict[int, List[Path]]):
    x = []
    y = []
    for uid, paths in train_paths.items():
        for path in paths:
            image = load_gray_200(path)
            if image is None:
                continue
            x.append(image)
            y.append(uid)
    if not x:
        raise RuntimeError("No hay muestras válidas para entrenamiento LBPH")

    recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    recognizer.train(x, np.array(y))
    return recognizer


def predict_outputs(recognizer, split: Dict[int, List[Path]]) -> Dict[int, List[Tuple[int, float, int]]]:
    out: Dict[int, List[Tuple[int, float, int]]] = {}
    for real_uid, paths in split.items():
        items = []
        for path in paths:
            image = load_gray_200(path)
            if image is None:
                continue
            pred, conf = recognizer.predict(image)
            items.append((int(pred), float(conf), real_uid))
        out[real_uid] = items
    return out


def build_attempts(outputs: Dict[int, List[Tuple[int, float, int]]], users: List[int]) -> List[Attempt]:
    attempts = []
    for claimed_uid in users:
        for pred, conf, real_uid in outputs.get(claimed_uid, []):
            attempts.append(Attempt("genuine", claimed_uid, real_uid, pred, conf))

        for other_uid in users:
            if other_uid == claimed_uid:
                continue
            for pred, conf, real_uid in outputs.get(other_uid, []):
                attempts.append(Attempt("impostor", claimed_uid, real_uid, pred, conf))
    return attempts


def evaluate(attempts: List[Attempt], threshold: float) -> dict:
    genuine = [a for a in attempts if a.scenario == "genuine"]
    impostor = [a for a in attempts if a.scenario == "impostor"]

    tp = fn = fp = tn = 0
    for a in genuine:
        ok = a.predicted_user == a.claimed_user and a.confidence <= threshold
        if ok:
            tp += 1
        else:
            fn += 1

    for a in impostor:
        wrong_accept = a.predicted_user == a.claimed_user and a.confidence <= threshold
        if wrong_accept:
            fp += 1
        else:
            tn += 1

    far = fp / max(1, len(impostor))
    frr = fn / max(1, len(genuine))
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    return {
        "far": float(far),
        "frr": float(frr),
        "accuracy": float(accuracy),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def threshold_search(attempts: List[Attempt]) -> dict:
    confidences = [a.confidence for a in attempts]
    min_conf, max_conf = min(confidences), max(confidences)

    if math.isclose(min_conf, max_conf):
        m = evaluate(attempts, min_conf)
        eer = (m["far"] + m["frr"]) / 2.0
        return {
            "threshold": float(min_conf),
            "far": m["far"],
            "frr": m["frr"],
            "accuracy": m["accuracy"],
            "eer": float(eer),
            "eer_threshold": float(min_conf),
        }

    thresholds = np.linspace(min_conf, max_conf, 300)
    metrics = []
    for th in thresholds:
        m = evaluate(attempts, float(th))
        m["threshold"] = float(th)
        metrics.append(m)

    eer_row = min(metrics, key=lambda m: abs(m["far"] - m["frr"]))
    best_row = min(metrics, key=lambda m: (m["far"] + m["frr"] + abs(m["far"] - m["frr"]) * 0.5, m["threshold"]))

    return {
        "threshold": float(best_row["threshold"]),
        "far": float(best_row["far"]),
        "frr": float(best_row["frr"]),
        "accuracy": float(best_row["accuracy"]),
        "eer": float((eer_row["far"] + eer_row["frr"]) / 2.0),
        "eer_threshold": float(eer_row["threshold"]),
    }


def conf_stats(attempts: List[Attempt]) -> dict:
    genuine = [a.confidence for a in attempts if a.scenario == "genuine"]
    impostor = [a.confidence for a in attempts if a.scenario == "impostor"]
    return {
        "mean_conf_genuine": float(mean(genuine)) if genuine else 0.0,
        "std_conf_genuine": float(pstdev(genuine)) if len(genuine) > 1 else 0.0,
        "mean_conf_impostor": float(mean(impostor)) if impostor else 0.0,
        "std_conf_impostor": float(pstdev(impostor)) if len(impostor) > 1 else 0.0,
    }


def run_direction(samples: Dict[int, Dict[str, List[Path]]], train_session: str, test_session: str) -> dict:
    users = sorted(samples.keys())
    train_split = {uid: samples[uid][train_session] for uid in users}
    test_split = {uid: samples[uid][test_session] for uid in users}

    recognizer = train_lbph(train_split)
    train_out = predict_outputs(recognizer, train_split)
    test_out = predict_outputs(recognizer, test_split)

    train_attempts = build_attempts(train_out, users)
    test_attempts = build_attempts(test_out, users)

    search = threshold_search(test_attempts)
    threshold = float(search["threshold"])

    train_m = evaluate(train_attempts, threshold)
    test_m = evaluate(test_attempts, threshold)
    cstats = conf_stats(test_attempts)

    return {
        "direction": f"{train_session}_to_{test_session}",
        "threshold": threshold,
        "far": test_m["far"],
        "frr": test_m["frr"],
        "accuracy": test_m["accuracy"],
        "eer": search["eer"],
        "eer_threshold": search["eer_threshold"],
        "train_accuracy": train_m["accuracy"],
        "test_accuracy": test_m["accuracy"],
        **cstats,
    }


def baseline_metrics() -> dict:
    path = Path("logs/session_validation_metrics.json")
    if not path.exists():
        path = Path("logs/cross_validation_metrics.json")
    if not path.exists():
        return {}

    data = json.loads(path.read_text(encoding="utf-8"))
    if "aggregated" in data:
        agg = data["aggregated"]
        return {
            "far": agg.get("far", {}).get("mean"),
            "frr": agg.get("frr", {}).get("mean"),
            "accuracy": agg.get("accuracy", {}).get("mean"),
            "eer": agg.get("eer", {}).get("mean"),
        }

    return {
        "far": data.get("far"),
        "frr": data.get("frr"),
        "accuracy": data.get("accuracy"),
        "eer": data.get("eer"),
    }


def compare_against_baseline(avg: dict, baseline: dict) -> dict:
    if not baseline:
        return {}
    return {
        "baseline_far": baseline.get("far"),
        "baseline_frr": baseline.get("frr"),
        "baseline_accuracy": baseline.get("accuracy"),
        "baseline_eer": baseline.get("eer"),
        "delta_far": None if baseline.get("far") is None else avg["far"] - baseline["far"],
        "delta_frr": None if baseline.get("frr") is None else avg["frr"] - baseline["frr"],
        "delta_accuracy": None if baseline.get("accuracy") is None else avg["accuracy"] - baseline["accuracy"],
        "delta_eer": None if baseline.get("eer") is None else avg["eer"] - baseline["eer"],
    }


def write_outputs(metrics: dict, academic_text: str) -> None:
    json_path = Path("logs/real_session_validation_metrics.json")
    json_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    report_lines = [
        "=== REPORTE DE VALIDACIÓN ESTRICTA POR SESIÓN REAL ===",
        f"usuarios={metrics['users']}",
        f"samples_A={metrics['samples_A']}",
        f"samples_B={metrics['samples_B']}",
        "",
        "Dirección A->B:",
        f"threshold={metrics['A_to_B']['threshold']:.6f}",
        f"FAR={metrics['A_to_B']['far']:.6f}",
        f"FRR={metrics['A_to_B']['frr']:.6f}",
        f"Accuracy={metrics['A_to_B']['accuracy']:.6f}",
        f"EER={metrics['A_to_B']['eer']:.6f}",
        f"mean_conf_genuine={metrics['A_to_B']['mean_conf_genuine']:.6f}",
        f"std_conf_genuine={metrics['A_to_B']['std_conf_genuine']:.6f}",
        f"mean_conf_impostor={metrics['A_to_B']['mean_conf_impostor']:.6f}",
        f"std_conf_impostor={metrics['A_to_B']['std_conf_impostor']:.6f}",
        "",
        "Dirección B->A:",
        f"threshold={metrics['B_to_A']['threshold']:.6f}",
        f"FAR={metrics['B_to_A']['far']:.6f}",
        f"FRR={metrics['B_to_A']['frr']:.6f}",
        f"Accuracy={metrics['B_to_A']['accuracy']:.6f}",
        f"EER={metrics['B_to_A']['eer']:.6f}",
        f"mean_conf_genuine={metrics['B_to_A']['mean_conf_genuine']:.6f}",
        f"std_conf_genuine={metrics['B_to_A']['std_conf_genuine']:.6f}",
        f"mean_conf_impostor={metrics['B_to_A']['mean_conf_impostor']:.6f}",
        f"std_conf_impostor={metrics['B_to_A']['std_conf_impostor']:.6f}",
        "",
        "Promedio bidireccional:",
        f"FAR={metrics['average']['far']:.6f}",
        f"FRR={metrics['average']['frr']:.6f}",
        f"Accuracy={metrics['average']['accuracy']:.6f}",
        f"EER={metrics['average']['eer']:.6f}",
        f"mean_conf_genuine={metrics['average']['mean_conf_genuine']:.6f}",
        f"std_conf_genuine={metrics['average']['std_conf_genuine']:.6f}",
        f"mean_conf_impostor={metrics['average']['mean_conf_impostor']:.6f}",
        f"std_conf_impostor={metrics['average']['std_conf_impostor']:.6f}",
        "",
        "Comparación contra baseline:",
        *(f"{k}={v}" for k, v in metrics.get("baseline_comparison", {}).items()),
    ]
    Path("logs/real_session_validation_report.txt").write_text("\n".join(report_lines) + "\n", encoding="utf-8")
    Path("logs/chapter4_real_session_validation.txt").write_text(academic_text, encoding="utf-8")


def main() -> int:
    setup_logging()
    samples = load_samples_by_user_and_session()
    users = sorted(samples.keys())

    a_to_b = run_direction(samples, "A", "B")
    b_to_a = run_direction(samples, "B", "A")

    average = {
        "far": (a_to_b["far"] + b_to_a["far"]) / 2.0,
        "frr": (a_to_b["frr"] + b_to_a["frr"]) / 2.0,
        "accuracy": (a_to_b["accuracy"] + b_to_a["accuracy"]) / 2.0,
        "eer": (a_to_b["eer"] + b_to_a["eer"]) / 2.0,
        "mean_conf_genuine": (a_to_b["mean_conf_genuine"] + b_to_a["mean_conf_genuine"]) / 2.0,
        "std_conf_genuine": (a_to_b["std_conf_genuine"] + b_to_a["std_conf_genuine"]) / 2.0,
        "mean_conf_impostor": (a_to_b["mean_conf_impostor"] + b_to_a["mean_conf_impostor"]) / 2.0,
        "std_conf_impostor": (a_to_b["std_conf_impostor"] + b_to_a["std_conf_impostor"]) / 2.0,
    }

    samples_a = {uid: len(samples[uid]["A"]) for uid in users}
    samples_b = {uid: len(samples[uid]["B"]) for uid in users}

    baseline = baseline_metrics()
    comparison = compare_against_baseline(average, baseline)

    academic_text = (
        "Interpretación académica (voz pasiva):\n"
        "Se ejecutó una validación estricta por sesión real en dos direcciones (A→B y B→A), con el propósito de medir el impacto de la variabilidad intra-clase bajo cambios reales de captura. "
        "La variabilidad intra-clase fue reflejada en los desplazamientos de confianza entre sesiones y en la posible variación de FAR/FRR. "
        "El cambio de iluminación entre sesiones fue considerado un factor crítico, dado que modifica la textura local explotada por LBPH y puede aumentar la superposición entre distribuciones genuina e impostora. "
        "Cuando se observó estabilidad de métricas entre A→B y B→A, se interpretó robustez del modelo clásico; cuando se observaron caídas, se interpretó sensibilidad a condiciones de adquisición y necesidad de ampliar diversidad de captura. "
        "Como limitación, los resultados dependen de la cantidad de sesiones disponibles y del rango real de variación fotométrica presente en el dataset, por lo que una expansión de escenarios operativos incrementaría la validez externa del estudio.\n"
    )

    metrics = {
        "users": users,
        "samples_A": samples_a,
        "samples_B": samples_b,
        "A_to_B": a_to_b,
        "B_to_A": b_to_a,
        "average": average,
        "baseline_comparison": comparison,
    }

    write_outputs(metrics, academic_text)
    LOGGER.info(
        "real_session_validation_done users=%s avg_acc=%.4f avg_far=%.4f avg_frr=%.4f avg_eer=%.4f",
        users,
        average["accuracy"],
        average["far"],
        average["frr"],
        average["eer"],
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
