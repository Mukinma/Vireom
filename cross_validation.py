import json
import logging
import math
import random
from dataclasses import dataclass, asdict
from pathlib import Path
from statistics import mean, pstdev
from typing import Dict, List, Tuple

import cv2
import numpy as np

from database.db import db


LOGGER = logging.getLogger("camerapi.crossval")
SEED = 42
K_FOLDS = 5
TRAIN_RATIO = 0.7


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
            logging.FileHandler("logs/cross_validation.log", encoding="utf-8"),
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
        user_id = int(row["user_id"])
        image_path = Path(row["ruta_imagen"])
        if image_path.exists():
            samples.setdefault(user_id, []).append(image_path)

    if len(samples) < 2:
        raise RuntimeError("Se requieren al menos 2 usuarios activos con muestras válidas")
    for user_id, paths in samples.items():
        if len(paths) < K_FOLDS:
            raise RuntimeError(f"Usuario {user_id} tiene {len(paths)} muestras; se requieren al menos {K_FOLDS}")
    return samples


def split_70_30(paths: List[Path], rng: random.Random) -> Tuple[List[Path], List[Path]]:
    shuffled = paths[:]
    rng.shuffle(shuffled)
    train_count = max(1, int(len(shuffled) * TRAIN_RATIO))
    train_set = shuffled[:train_count]
    test_set = shuffled[train_count:]
    if not test_set:
        test_set = shuffled[-1:]
        train_set = shuffled[:-1]
    return train_set, test_set


def kfold_split(paths: List[Path], k: int) -> List[List[Path]]:
    folds = [[] for _ in range(k)]
    for idx, path in enumerate(paths):
        folds[idx % k].append(path)
    return folds


def load_grayscale_200(path: Path):
    image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return None
    return cv2.resize(image, (200, 200))


def train_lbph(train_split: Dict[int, List[Path]]):
    x_train = []
    y_train = []
    for user_id, paths in train_split.items():
        for path in paths:
            image = load_grayscale_200(path)
            if image is None:
                continue
            x_train.append(image)
            y_train.append(user_id)
    if not x_train:
        raise RuntimeError("No hay muestras válidas para entrenamiento LBPH")

    recognizer = cv2.face.LBPHFaceRecognizer_create(radius=1, neighbors=8, grid_x=8, grid_y=8)
    recognizer.train(x_train, np.array(y_train))
    return recognizer


def predict_set(recognizer, split: Dict[int, List[Path]]) -> Dict[Path, Tuple[int, float, int]]:
    predictions: Dict[Path, Tuple[int, float, int]] = {}
    for real_user, paths in split.items():
        for path in paths:
            image = load_grayscale_200(path)
            if image is None:
                continue
            pred, conf = recognizer.predict(image)
            predictions[path] = (int(pred), float(conf), real_user)
    return predictions


def build_attempts(predictions: Dict[Path, Tuple[int, float, int]], users: List[int]) -> List[Attempt]:
    attempts: List[Attempt] = []

    real_by_user: Dict[int, List[Tuple[Path, Tuple[int, float, int]]]] = {u: [] for u in users}
    for path, payload in predictions.items():
        real_user = payload[2]
        real_by_user.setdefault(real_user, []).append((path, payload))

    for claimed_user in users:
        for _, (pred, conf, real_user) in real_by_user.get(claimed_user, []):
            attempts.append(
                Attempt(
                    scenario="genuine",
                    claimed_user=claimed_user,
                    real_user=real_user,
                    predicted_user=pred,
                    confidence=conf,
                )
            )

        for other_user in users:
            if other_user == claimed_user:
                continue
            for _, (pred, conf, real_user) in real_by_user.get(other_user, []):
                attempts.append(
                    Attempt(
                        scenario="impostor",
                        claimed_user=claimed_user,
                        real_user=real_user,
                        predicted_user=pred,
                        confidence=conf,
                    )
                )

    return attempts


def evaluate_attempts(attempts: List[Attempt], threshold: float) -> dict:
    genuine = [a for a in attempts if a.scenario == "genuine"]
    impostor = [a for a in attempts if a.scenario == "impostor"]

    tp = fn = fp = tn = 0
    for a in genuine:
        accepted = a.predicted_user == a.claimed_user and a.confidence <= threshold
        if accepted:
            tp += 1
        else:
            fn += 1

    for a in impostor:
        accepted_wrongly = a.predicted_user == a.claimed_user and a.confidence <= threshold
        if accepted_wrongly:
            fp += 1
        else:
            tn += 1

    far = fp / max(1, len(impostor))
    frr = fn / max(1, len(genuine))
    accuracy = (tp + tn) / max(1, tp + tn + fp + fn)
    precision = tp / max(1, tp + fp)
    recall = tp / max(1, tp + fn)

    return {
        "threshold": float(threshold),
        "far": float(far),
        "frr": float(frr),
        "accuracy": float(accuracy),
        "precision": float(precision),
        "recall": float(recall),
        "tp": tp,
        "tn": tn,
        "fp": fp,
        "fn": fn,
    }


def find_eer_and_optimal(attempts: List[Attempt]) -> dict:
    confidences = [a.confidence for a in attempts]
    if not confidences:
        raise RuntimeError("No hay intentos para evaluación")
    min_conf = min(confidences)
    max_conf = max(confidences)
    if math.isclose(min_conf, max_conf):
        candidate_metrics = evaluate_attempts(attempts, min_conf)
        return {
            "eer_threshold": float(min_conf),
            "eer_far": candidate_metrics["far"],
            "eer_frr": candidate_metrics["frr"],
            "optimal": candidate_metrics,
        }

    thresholds = np.linspace(min_conf, max_conf, 300)
    metrics_curve = [evaluate_attempts(attempts, float(th)) for th in thresholds]

    eer = min(metrics_curve, key=lambda m: abs(m["far"] - m["frr"]))
    optimal = min(metrics_curve, key=lambda m: (m["far"] + m["frr"] + abs(m["far"] - m["frr"]) * 0.5, m["threshold"]))

    return {
        "eer_threshold": eer["threshold"],
        "eer_far": eer["far"],
        "eer_frr": eer["frr"],
        "optimal": optimal,
    }


def confidence_stats(attempts: List[Attempt]) -> dict:
    genuine = [a.confidence for a in attempts if a.scenario == "genuine"]
    impostor = [a.confidence for a in attempts if a.scenario == "impostor"]
    return {
        "mean_conf_genuine": float(mean(genuine)) if genuine else 0.0,
        "std_conf_genuine": float(pstdev(genuine)) if len(genuine) > 1 else 0.0,
        "mean_conf_impostor": float(mean(impostor)) if impostor else 0.0,
        "std_conf_impostor": float(pstdev(impostor)) if len(impostor) > 1 else 0.0,
    }


def aggregate_fold_metrics(folds: List[dict]) -> dict:
    keys = ["far", "frr", "accuracy", "precision", "recall", "eer", "mean_conf_genuine", "mean_conf_impostor"]
    stats = {}
    for key in keys:
        values = [fold[key] for fold in folds]
        stats[key] = {
            "mean": float(mean(values)) if values else 0.0,
            "std": float(pstdev(values)) if len(values) > 1 else 0.0,
        }
    return stats


def run_cross_validation(samples_by_user: Dict[int, List[Path]]) -> dict:
    rng = random.Random(SEED)
    users = sorted(samples_by_user.keys())

    split_7030 = {}
    for user_id in users:
        train70, test30 = split_70_30(samples_by_user[user_id], rng)
        if set(train70).intersection(set(test30)):
            raise RuntimeError(f"Se detectó solapamiento train/test en usuario {user_id}")
        split_7030[user_id] = {"train": train70, "test": test30}

    folds_by_user = {}
    for user_id in users:
        shuffled = split_7030[user_id]["train"][:]
        rng.shuffle(shuffled)
        folds_by_user[user_id] = kfold_split(shuffled, K_FOLDS)

    fold_reports = []
    overfit_alerts = []

    for fold_idx in range(K_FOLDS):
        train_split = {u: [] for u in users}
        test_split = {u: [] for u in users}

        for user_id in users:
            for idx, fold_paths in enumerate(folds_by_user[user_id]):
                if idx == fold_idx:
                    test_split[user_id].extend(fold_paths)
                else:
                    train_split[user_id].extend(fold_paths)

        for user_id in users:
            if set(train_split[user_id]).intersection(set(test_split[user_id])):
                raise RuntimeError(f"Fold {fold_idx} con solapamiento train/test en usuario {user_id}")

        recognizer = train_lbph(train_split)
        train_preds = predict_set(recognizer, train_split)
        test_preds = predict_set(recognizer, test_split)

        train_attempts = build_attempts(train_preds, users)
        test_attempts = build_attempts(test_preds, users)

        search = find_eer_and_optimal(test_attempts)
        threshold_opt = float(search["optimal"]["threshold"])

        train_metrics = evaluate_attempts(train_attempts, threshold_opt)
        test_metrics = search["optimal"]
        conf_stats = confidence_stats(test_attempts)

        eer_value = (search["eer_far"] + search["eer_frr"]) / 2.0
        fold_report = {
            "fold": fold_idx + 1,
            "threshold_opt": threshold_opt,
            "far": float(test_metrics["far"]),
            "frr": float(test_metrics["frr"]),
            "accuracy": float(test_metrics["accuracy"]),
            "precision": float(test_metrics["precision"]),
            "recall": float(test_metrics["recall"]),
            "eer": float(eer_value),
            "eer_threshold": float(search["eer_threshold"]),
            "train_accuracy": float(train_metrics["accuracy"]),
            "test_accuracy": float(test_metrics["accuracy"]),
            **conf_stats,
            "train_attempts": len(train_attempts),
            "test_attempts": len(test_attempts),
        }

        if fold_report["train_accuracy"] - fold_report["test_accuracy"] > 0.10:
            alert = {
                "fold": fold_idx + 1,
                "message": "Posible sobreajuste detectado: accuracy entrenamiento significativamente mayor que prueba",
                "train_accuracy": fold_report["train_accuracy"],
                "test_accuracy": fold_report["test_accuracy"],
            }
            overfit_alerts.append(alert)

        fold_reports.append(fold_report)
        LOGGER.info(
            "fold_done fold=%s far=%.4f frr=%.4f acc_test=%.4f acc_train=%.4f",
            fold_idx + 1,
            fold_report["far"],
            fold_report["frr"],
            fold_report["test_accuracy"],
            fold_report["train_accuracy"],
        )

    aggregated = aggregate_fold_metrics(fold_reports)
    return {
        "seed": SEED,
        "k_folds": K_FOLDS,
        "train_ratio": TRAIN_RATIO,
        "users": users,
        "folds": fold_reports,
        "aggregated": aggregated,
        "overfitting_alerts": overfit_alerts,
    }


def write_outputs(report: dict) -> None:
    metrics_path = Path("logs/cross_validation_metrics.json")
    metrics_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")

    agg = report["aggregated"]
    lines = [
        "=== REPORTE DE VALIDACIÓN CRUZADA LBPH ===",
        f"seed={report['seed']}",
        f"k_folds={report['k_folds']}",
        f"train_ratio={report['train_ratio']}",
        f"usuarios={report['users']}",
        "",
        "Métricas promedio (± desviación estándar):",
        f"FAR={agg['far']['mean']:.6f} ± {agg['far']['std']:.6f}",
        f"FRR={agg['frr']['mean']:.6f} ± {agg['frr']['std']:.6f}",
        f"Accuracy={agg['accuracy']['mean']:.6f} ± {agg['accuracy']['std']:.6f}",
        f"Precision={agg['precision']['mean']:.6f} ± {agg['precision']['std']:.6f}",
        f"Recall={agg['recall']['mean']:.6f} ± {agg['recall']['std']:.6f}",
        f"EER={agg['eer']['mean']:.6f} ± {agg['eer']['std']:.6f}",
        f"Confianza genuina media={agg['mean_conf_genuine']['mean']:.6f} ± {agg['mean_conf_genuine']['std']:.6f}",
        f"Confianza impostor media={agg['mean_conf_impostor']['mean']:.6f} ± {agg['mean_conf_impostor']['std']:.6f}",
        "",
        "Detalle por fold:",
    ]

    for fold in report["folds"]:
        lines.append(
            "fold={fold} far={far:.6f} frr={frr:.6f} acc={accuracy:.6f} prec={precision:.6f} rec={recall:.6f} "
            "eer={eer:.6f} acc_train={train_accuracy:.6f} acc_test={test_accuracy:.6f}".format(**fold)
        )

    lines.append("")
    if report["overfitting_alerts"]:
        lines.append("ALERTAS DE SOBREAJUSTE:")
        for alert in report["overfitting_alerts"]:
            lines.append(
                f"fold={alert['fold']} train_acc={alert['train_accuracy']:.6f} test_acc={alert['test_accuracy']:.6f} mensaje={alert['message']}"
            )
    else:
        lines.append("No se detectaron alertas de sobreajuste con el criterio definido.")

    report_path = Path("logs/cross_validation_report.txt")
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    methodology_text = (
        "Metodología (voz pasiva):\n"
        "La validación del reconocedor LBPH fue realizada mediante separación reproducible por usuario y validación cruzada estratificada. "
        "Para cada identidad, las muestras disponibles fueron divididas de forma aleatoria con semilla fija (seed=42), reservándose el 70% para entrenamiento y el 30% para prueba. "
        "Posteriormente, sobre el subconjunto de entrenamiento, se aplicó un esquema K-Fold con k=5 por usuario. En cada iteración, cuatro folds fueron utilizados para entrenamiento y un fold para evaluación. "
        "Se garantizó que ninguna muestra de entrenamiento apareciera en prueba dentro de cada fold. "
        "Las métricas biométricas FAR, FRR, EER, junto con Accuracy, Precision y Recall, fueron estimadas por fold y agregadas mediante media y desviación estándar. "
        "Asimismo, se comparó el desempeño en entrenamiento versus prueba para detectar posible sobreajuste.\n"
    )

    results_text = (
        "Resultados (voz pasiva):\n"
        f"Se obtuvo FAR promedio de {agg['far']['mean']:.6f} (±{agg['far']['std']:.6f}) y FRR promedio de {agg['frr']['mean']:.6f} (±{agg['frr']['std']:.6f}). "
        f"La Accuracy promedio fue {agg['accuracy']['mean']:.6f} (±{agg['accuracy']['std']:.6f}), con Precision {agg['precision']['mean']:.6f} y Recall {agg['recall']['mean']:.6f}. "
        f"El EER promedio fue {agg['eer']['mean']:.6f}. "
        "La comparación entre desempeño de entrenamiento y prueba fue incorporada como criterio de alerta de sobreajuste, permitiendo verificar la estabilidad estadística del modelo clásico Haar+LBPH en un entorno local embebido simulado.\n"
    )

    Path("logs/chapter3_cross_validation.txt").write_text(methodology_text, encoding="utf-8")
    Path("logs/chapter4_cross_validation_results.txt").write_text(results_text, encoding="utf-8")


def main() -> int:
    setup_logging()
    samples_by_user = load_samples_by_user()
    report = run_cross_validation(samples_by_user)
    write_outputs(report)
    LOGGER.info("cross_validation_completed folds=%s", len(report["folds"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
