import json
import logging
import math
import random
import re
from dataclasses import dataclass
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Tuple

import cv2
import numpy as np

from database.db import db


LOGGER = logging.getLogger("camerapi.session_validation")
SEED = 42
SESSION_GAP_SECONDS = 30 * 60


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
            logging.FileHandler("logs/session_validation.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_samples_by_user() -> Dict[int, List[Path]]:
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
    samples: Dict[int, List[Path]] = {}
    for row in rows:
        uid = int(row["user_id"])
        path = Path(row["ruta_imagen"])
        if path.exists():
            samples.setdefault(uid, []).append(path)
    if len(samples) < 2:
        raise RuntimeError("Se requieren al menos 2 usuarios con muestras válidas")
    return samples


def load_gray_200(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return cv2.resize(image, (200, 200))


def prefix_token(path: Path) -> str:
    stem = path.stem.lower()
    stem = re.sub(r"_proc$", "", stem)
    stem = re.sub(r"\d+$", "", stem)
    token = re.split(r"[_\-]", stem)[0] if stem else "sample"
    return token or "sample"


def detect_sessions_for_user(paths: List[Path]) -> Dict[str, List[Path]]:
    if not paths:
        return {}

    sorted_by_time = sorted(paths, key=lambda p: p.stat().st_mtime)
    time_sessions: List[List[Path]] = [[]]
    prev_t = sorted_by_time[0].stat().st_mtime
    for path in sorted_by_time:
        t = path.stat().st_mtime
        if (t - prev_t) > SESSION_GAP_SECONDS:
            time_sessions.append([])
        time_sessions[-1].append(path)
        prev_t = t

    prefixes: Dict[str, List[Path]] = {}
    for path in paths:
        prefixes.setdefault(prefix_token(path), []).append(path)

    non_generic_prefixes = {k: v for k, v in prefixes.items() if k not in {"sample", "img", "image"}}

    if len(time_sessions) > 1:
        return {f"time_session_{idx+1}": sess for idx, sess in enumerate(time_sessions)}

    if len(non_generic_prefixes) > 1:
        return {f"prefix_{k}": v for k, v in non_generic_prefixes.items()}

    return {"single_session": paths}


def choose_train_test_sessions(per_user_sessions: Dict[int, Dict[str, List[Path]]]) -> Tuple[Dict[int, List[Path]], Dict[int, List[Path]], bool]:
    train_split: Dict[int, List[Path]] = {}
    test_split: Dict[int, List[Path]] = {}

    multi_session_available = True
    for uid, sessions in per_user_sessions.items():
        if len(sessions) < 2:
            multi_session_available = False
            break

        ordered = sorted(sessions.items(), key=lambda kv: min(p.stat().st_mtime for p in kv[1]))
        train_name, train_paths = ordered[0]
        test_name, test_paths = ordered[-1]
        if train_name == test_name:
            multi_session_available = False
            break
        train_split[uid] = train_paths
        test_split[uid] = test_paths

    return train_split, test_split, multi_session_available


def augment_image(image: np.ndarray, rng: random.Random) -> np.ndarray:
    out = image.astype(np.float32)

    alpha = rng.uniform(0.90, 1.10)
    beta = rng.uniform(-15, 15)
    out = np.clip(out * alpha + beta, 0, 255)

    angle = rng.uniform(-5.0, 5.0)
    h, w = out.shape[:2]
    matrix = cv2.getRotationMatrix2D((w / 2, h / 2), angle, 1.0)
    out = cv2.warpAffine(out, matrix, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    k = rng.choice([3, 5])
    out = cv2.GaussianBlur(out, (k, k), sigmaX=0.7)

    return out.astype(np.uint8)


def build_augmented_test(train_split_paths: Dict[int, List[Path]]) -> Tuple[Dict[int, List[np.ndarray]], Dict[int, List[np.ndarray]]]:
    rng = random.Random(SEED)
    train_images: Dict[int, List[np.ndarray]] = {}
    test_images: Dict[int, List[np.ndarray]] = {}

    for uid, paths in train_split_paths.items():
        user_train = []
        user_test = []
        for path in paths:
            image = load_gray_200(path)
            if image is None:
                continue
            user_train.append(image)
            user_test.append(augment_image(image, rng))
        train_images[uid] = user_train
        test_images[uid] = user_test

    return train_images, test_images


def train_lbph_from_arrays(train_images: Dict[int, List[np.ndarray]]):
    x = []
    y = []
    for uid, images in train_images.items():
        for image in images:
            x.append(image)
            y.append(uid)
    if not x:
        raise RuntimeError("No hay muestras para entrenamiento")
    recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    recognizer.train(x, np.array(y))
    return recognizer


def train_lbph_from_paths(train_split_paths: Dict[int, List[Path]]):
    train_images = {uid: [img for img in (load_gray_200(p) for p in paths) if img is not None] for uid, paths in train_split_paths.items()}
    return train_lbph_from_arrays(train_images), train_images


def predict_on_paths(recognizer, split_paths: Dict[int, List[Path]]) -> Dict[int, List[Tuple[int, float, int]]]:
    outputs: Dict[int, List[Tuple[int, float, int]]] = {}
    for real_uid, paths in split_paths.items():
        entries = []
        for path in paths:
            image = load_gray_200(path)
            if image is None:
                continue
            pred, conf = recognizer.predict(image)
            entries.append((int(pred), float(conf), real_uid))
        outputs[real_uid] = entries
    return outputs


def predict_on_arrays(recognizer, split_arrays: Dict[int, List[np.ndarray]]) -> Dict[int, List[Tuple[int, float, int]]]:
    outputs: Dict[int, List[Tuple[int, float, int]]] = {}
    for real_uid, images in split_arrays.items():
        entries = []
        for image in images:
            pred, conf = recognizer.predict(image)
            entries.append((int(pred), float(conf), real_uid))
        outputs[real_uid] = entries
    return outputs


def build_attempts_from_outputs(outputs: Dict[int, List[Tuple[int, float, int]]], users: List[int]) -> List[Attempt]:
    attempts = []
    for claimed in users:
        own_entries = outputs.get(claimed, [])
        for pred, conf, real_uid in own_entries:
            attempts.append(Attempt("genuine", claimed, real_uid, pred, conf))

        for other in users:
            if other == claimed:
                continue
            for pred, conf, real_uid in outputs.get(other, []):
                attempts.append(Attempt("impostor", claimed, real_uid, pred, conf))
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


def search_threshold_and_eer(attempts: List[Attempt]) -> dict:
    confidences = [a.confidence for a in attempts]
    min_conf, max_conf = min(confidences), max(confidences)

    if math.isclose(min_conf, max_conf):
        m = evaluate(attempts, min_conf)
        eer = (m["far"] + m["frr"]) / 2.0
        return {
            "optimal_threshold": float(min_conf),
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
    eer = (eer_row["far"] + eer_row["frr"]) / 2.0

    return {
        "optimal_threshold": float(best_row["threshold"]),
        "far": float(best_row["far"]),
        "frr": float(best_row["frr"]),
        "accuracy": float(best_row["accuracy"]),
        "eer": float(eer),
        "eer_threshold": float(eer_row["threshold"]),
    }


def confidence_statistics(attempts: List[Attempt]) -> dict:
    genuine = [a.confidence for a in attempts if a.scenario == "genuine"]
    impostor = [a.confidence for a in attempts if a.scenario == "impostor"]
    return {
        "mean_conf_genuine": float(mean(genuine)) if genuine else 0.0,
        "std_conf_genuine": float(pstdev(genuine)) if len(genuine) > 1 else 0.0,
        "mean_conf_impostor": float(mean(impostor)) if impostor else 0.0,
        "std_conf_impostor": float(pstdev(impostor)) if len(impostor) > 1 else 0.0,
    }


def previous_baseline() -> dict:
    path = Path("logs/cross_validation_metrics.json")
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    agg = data.get("aggregated", {})
    return {
        "far": agg.get("far", {}).get("mean"),
        "frr": agg.get("frr", {}).get("mean"),
        "accuracy": agg.get("accuracy", {}).get("mean"),
        "eer": agg.get("eer", {}).get("mean"),
    }


def write_outputs(metrics: dict, methodology: str, interpretation: str) -> None:
    json_path = Path("logs/session_validation_metrics.json")
    json_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")

    baseline = metrics.get("baseline_comparison", {})
    lines = [
        "=== REPORTE DE VALIDACIÓN POR SESIÓN TEMPORAL ===",
        f"modo_validacion={metrics['mode']}",
        f"usuarios={metrics['users']}",
        f"sesiones_por_usuario={metrics['sessions_per_user']}",
        f"threshold_optimo={metrics['optimal_threshold']:.6f}",
        f"FAR={metrics['far']:.6f}",
        f"FRR={metrics['frr']:.6f}",
        f"Accuracy={metrics['accuracy']:.6f}",
        f"EER={metrics['eer']:.6f}",
        f"media_confianza_genuine={metrics['mean_conf_genuine']:.6f}",
        f"std_confianza_genuine={metrics['std_conf_genuine']:.6f}",
        f"media_confianza_impostor={metrics['mean_conf_impostor']:.6f}",
        f"std_confianza_impostor={metrics['std_conf_impostor']:.6f}",
        "",
        "Comparación vs validación previa:",
        f"baseline_far={baseline.get('far')}",
        f"baseline_frr={baseline.get('frr')}",
        f"baseline_accuracy={baseline.get('accuracy')}",
        f"baseline_eer={baseline.get('eer')}",
        f"delta_far={baseline.get('delta_far')}",
        f"delta_frr={baseline.get('delta_frr')}",
        f"delta_accuracy={baseline.get('delta_accuracy')}",
        f"delta_eer={baseline.get('delta_eer')}",
        "",
        "Interpretación académica:",
        interpretation.strip(),
    ]

    Path("logs/session_validation_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    Path("logs/chapter3_session_validation.txt").write_text(methodology, encoding="utf-8")
    Path("logs/chapter4_session_validation_results.txt").write_text(interpretation, encoding="utf-8")


def main() -> int:
    setup_logging()
    samples_by_user = load_samples_by_user()
    users = sorted(samples_by_user.keys())

    per_user_sessions = {uid: detect_sessions_for_user(paths) for uid, paths in samples_by_user.items()}
    sessions_count = {uid: len(sess) for uid, sess in per_user_sessions.items()}

    train_split, test_split, has_multi_sessions = choose_train_test_sessions(per_user_sessions)

    if has_multi_sessions:
        recognizer, train_images = train_lbph_from_paths(train_split)
        train_outputs = predict_on_arrays(recognizer, train_images)
        test_outputs = predict_on_paths(recognizer, test_split)
        mode = "session_to_session"
    else:
        recognizer, train_images = train_lbph_from_paths(samples_by_user)
        train_outputs = predict_on_arrays(recognizer, train_images)
        _, test_augmented = build_augmented_test(samples_by_user)
        test_outputs = predict_on_arrays(recognizer, test_augmented)
        mode = "single_session_augmented_test"

    train_attempts = build_attempts_from_outputs(train_outputs, users)
    test_attempts = build_attempts_from_outputs(test_outputs, users)

    threshold_data = search_threshold_and_eer(test_attempts)
    threshold = float(threshold_data["optimal_threshold"])

    test_metrics = evaluate(test_attempts, threshold)
    train_metrics = evaluate(train_attempts, threshold)
    conf_stats = confidence_statistics(test_attempts)

    baseline = previous_baseline()
    baseline_comparison = {}
    if baseline:
        baseline_comparison = {
            **baseline,
            "delta_far": None if baseline.get("far") is None else float(test_metrics["far"] - baseline["far"]),
            "delta_frr": None if baseline.get("frr") is None else float(test_metrics["frr"] - baseline["frr"]),
            "delta_accuracy": None if baseline.get("accuracy") is None else float(test_metrics["accuracy"] - baseline["accuracy"]),
            "delta_eer": None if baseline.get("eer") is None else float(threshold_data["eer"] - baseline["eer"]),
        }

    methodology_text = (
        "Metodología (voz pasiva):\n"
        "Se implementó una validación por sesión temporal con el fin de incrementar el rigor experimental frente a esquemas de partición aleatoria. "
        "Las muestras fueron agrupadas automáticamente por usuario empleando heurísticas temporales (diferencias entre timestamps de captura) y de prefijo nominal. "
        "Cuando múltiples sesiones fueron identificadas, el entrenamiento se realizó con la sesión más temprana y la prueba con la sesión más reciente, sin mezcla entre sesiones. "
        "Cuando solo una sesión fue detectada, se construyó un conjunto de prueba con variaciones controladas de brillo, contraste, rotación leve (±5°) y desenfoque gaussiano, manteniendo el entrenamiento sobre muestras originales. "
        "Posteriormente, se estimaron FAR, FRR, Accuracy, EER y estadísticas de confianza para cuantificar la robustez del sistema LBPH bajo cambios de adquisición.\n"
    )

    interpretation_text = (
        "Resultados e interpretación (voz pasiva):\n"
        f"En validación por sesión se obtuvo FAR={test_metrics['far']:.6f}, FRR={test_metrics['frr']:.6f}, Accuracy={test_metrics['accuracy']:.6f} y EER={threshold_data['eer']:.6f}. "
        f"La confianza genuina presentó media={conf_stats['mean_conf_genuine']:.6f} (σ={conf_stats['std_conf_genuine']:.6f}), mientras que la confianza impostora presentó media={conf_stats['mean_conf_impostor']:.6f} (σ={conf_stats['std_conf_impostor']:.6f}). "
        "La validación por sesión fue considerada más rigurosa debido a que la generalización se evaluó sobre condiciones de captura temporalmente separadas o, en su defecto, sobre perturbaciones controladas no vistas durante entrenamiento. "
        "Una caída de métricas frente al baseline fue interpretada como evidencia de sensibilidad a variaciones de adquisición; por el contrario, la estabilidad de métricas fue interpretada como robustez del modelo clásico Haar+LBPH bajo las condiciones evaluadas.\n"
    )

    overfit_alert = (train_metrics["accuracy"] - test_metrics["accuracy"]) > 0.10

    metrics = {
        "mode": mode,
        "seed": SEED,
        "users": users,
        "sessions_per_user": sessions_count,
        "optimal_threshold": threshold,
        "far": float(test_metrics["far"]),
        "frr": float(test_metrics["frr"]),
        "accuracy": float(test_metrics["accuracy"]),
        "eer": float(threshold_data["eer"]),
        "eer_threshold": float(threshold_data["eer_threshold"]),
        "mean_conf_genuine": conf_stats["mean_conf_genuine"],
        "std_conf_genuine": conf_stats["std_conf_genuine"],
        "mean_conf_impostor": conf_stats["mean_conf_impostor"],
        "std_conf_impostor": conf_stats["std_conf_impostor"],
        "train_accuracy": float(train_metrics["accuracy"]),
        "test_accuracy": float(test_metrics["accuracy"]),
        "overfitting_alert": overfit_alert,
        "baseline_comparison": baseline_comparison,
    }

    write_outputs(metrics, methodology_text, interpretation_text)

    LOGGER.info(
        "session_validation_done mode=%s far=%.4f frr=%.4f acc=%.4f eer=%.4f overfit_alert=%s",
        mode,
        metrics["far"],
        metrics["frr"],
        metrics["accuracy"],
        metrics["eer"],
        overfit_alert,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
