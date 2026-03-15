import logging
import math
import statistics
from dataclasses import dataclass
from pathlib import Path

import cv2

from config import config
from database.db import db
from vision.recognizer import LBPHRecognizer


LOGGER = logging.getLogger("camerapi.calibration")
MIN_SAMPLES_PER_USER = 20
SAMPLES_PER_SCENARIO = 10


@dataclass
class PredictionRecord:
    scenario: str
    claimed_user_id: int
    true_user_id: int
    predicted_label: int
    confidence: float


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/calibrate_threshold.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def stddev(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(statistics.pstdev(values))


def load_user_samples() -> dict[int, list[Path]]:
    users = db.fetch_all("SELECT id FROM usuarios WHERE activo=1 ORDER BY id ASC")
    user_samples: dict[int, list[Path]] = {}
    for row in users:
        uid = int(row["id"])
        samples = db.fetch_all("SELECT imagen_ref FROM muestras WHERE usuario_id=?", (uid,))
        paths = [Path(s["imagen_ref"]) for s in samples if Path(s["imagen_ref"]).exists()]
        if len(paths) >= MIN_SAMPLES_PER_USER:
            user_samples[uid] = sorted(paths)

    if len(user_samples) < 2:
        raise RuntimeError("Se requieren al menos 2 usuarios activos con >=20 muestras para calibración")
    return user_samples


def predict_image(recognizer: LBPHRecognizer, image_path: Path) -> tuple[int, float]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"No se pudo cargar imagen: {image_path}")
    image = cv2.resize(image, (200, 200))
    label, confidence = recognizer.predict(image)
    if label is None or confidence is None:
        raise RuntimeError("Predicción inválida: modelo no cargado")
    return int(label), float(confidence)


def collect_predictions(recognizer: LBPHRecognizer, user_samples: dict[int, list[Path]]) -> list[PredictionRecord]:
    user_ids = sorted(user_samples.keys())
    records: list[PredictionRecord] = []

    for idx, uid in enumerate(user_ids):
        own_samples = user_samples[uid][:SAMPLES_PER_SCENARIO]
        for sample in own_samples:
            pred_label, conf = predict_image(recognizer, sample)
            records.append(
                PredictionRecord(
                    scenario="genuine",
                    claimed_user_id=uid,
                    true_user_id=uid,
                    predicted_label=pred_label,
                    confidence=conf,
                )
            )

        other_uid = user_ids[(idx + 1) % len(user_ids)]
        impostor_samples = user_samples[other_uid][:SAMPLES_PER_SCENARIO]
        for sample in impostor_samples:
            pred_label, conf = predict_image(recognizer, sample)
            records.append(
                PredictionRecord(
                    scenario="impostor",
                    claimed_user_id=uid,
                    true_user_id=other_uid,
                    predicted_label=pred_label,
                    confidence=conf,
                )
            )

    return records


def compute_far_frr(records: list[PredictionRecord], threshold: float) -> tuple[float, float]:
    genuine = [r for r in records if r.scenario == "genuine"]
    impostor = [r for r in records if r.scenario == "impostor"]

    false_rejects = 0
    for r in genuine:
        accepted = r.predicted_label == r.claimed_user_id and r.confidence <= threshold
        if not accepted:
            false_rejects += 1

    false_accepts = 0
    for r in impostor:
        accepted_as_claimed = r.predicted_label == r.claimed_user_id and r.confidence <= threshold
        if accepted_as_claimed:
            false_accepts += 1

    frr = false_rejects / max(1, len(genuine))
    far = false_accepts / max(1, len(impostor))
    return far, frr


def suggest_threshold(records: list[PredictionRecord]) -> tuple[float, float, float]:
    confidences = [r.confidence for r in records]
    if not confidences:
        raise RuntimeError("No hay predicciones para calcular umbral")

    positives = [r.confidence for r in records if r.scenario == "genuine"]
    negatives = [r.confidence for r in records if r.scenario == "impostor"]

    min_c = min(confidences)
    max_c = max(confidences)
    step = max((max_c - min_c) / 200.0, 0.1)

    best_threshold = min_c
    best_far = 1.0
    best_frr = 1.0
    best_score = float("inf")
    midpoint = (statistics.mean(positives) + statistics.mean(negatives)) / 2.0

    threshold = min_c
    while threshold <= max_c:
        far, frr = compute_far_frr(records, threshold)
        score = abs(far - frr) + (far + frr)
        if score < best_score or (math.isclose(score, best_score) and abs(threshold - midpoint) < abs(best_threshold - midpoint)):
            best_score = score
            best_threshold = threshold
            best_far = far
            best_frr = frr
        threshold += step

    return best_threshold, best_far, best_frr


def build_report(records: list[PredictionRecord], threshold: float, far: float, frr: float) -> str:
    positives = [r.confidence for r in records if r.scenario == "genuine"]
    negatives = [r.confidence for r in records if r.scenario == "impostor"]

    report_lines = [
        "=== REPORTE DE CALIBRACIÓN LBPH ===",
        f"muestras_genuine={len(positives)}",
        f"muestras_impostor={len(negatives)}",
        f"media_confianza_positiva={statistics.mean(positives):.4f}",
        f"media_confianza_negativa={statistics.mean(negatives):.4f}",
        f"desviacion_positiva={stddev(positives):.4f}",
        f"desviacion_negativa={stddev(negatives):.4f}",
        f"umbral_sugerido={threshold:.4f}",
        f"FAR={far:.6f}",
        f"FRR={frr:.6f}",
    ]

    report_lines.append("\nDetalle por usuario:")
    user_ids = sorted({r.claimed_user_id for r in records})
    for uid in user_ids:
        own = [r.confidence for r in records if r.scenario == "genuine" and r.claimed_user_id == uid]
        imp = [r.confidence for r in records if r.scenario == "impostor" and r.claimed_user_id == uid]
        report_lines.append(
            f"usuario={uid} own_mean={statistics.mean(own):.4f} imp_mean={statistics.mean(imp):.4f} "
            f"own_std={stddev(own):.4f} imp_std={stddev(imp):.4f}"
        )

    return "\n".join(report_lines) + "\n"


def main() -> int:
    setup_logging()
    db.init_db()

    recognizer = LBPHRecognizer()
    if not Path(config.model_path).exists():
        raise RuntimeError("No existe modelo LBPH para calibrar")
    if not recognizer.load_model(config.model_path):
        raise RuntimeError("Modelo LBPH no cargable")

    user_samples = load_user_samples()
    records = collect_predictions(recognizer, user_samples)
    threshold, far, frr = suggest_threshold(records)

    report_text = build_report(records, threshold, far, frr)
    report_path = Path("logs/calibration_report.txt")
    report_path.write_text(report_text, encoding="utf-8")
    LOGGER.info("calibration_completed report_path=%s threshold=%.4f FAR=%.6f FRR=%.6f", report_path, threshold, far, frr)

    db.update_config(float(threshold), db.get_config()["tiempo_apertura_seg"], db.get_config()["max_intentos"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
