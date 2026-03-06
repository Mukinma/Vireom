import csv
import logging
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

import cv2

from config import config
from database.db import db
from vision.recognizer import LBPHRecognizer


LOGGER = logging.getLogger("camerapi.experimental")
GENUINE_SAMPLES_PER_USER = 30
IMPOSTOR_SAMPLES_PER_USER = 30


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/experimental_validation.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_valid_samples() -> Dict[int, List[Path]]:
    rows = db.fetch_all(
        """
        SELECT u.id AS usuario_id, m.ruta_imagen
        FROM usuarios u
        JOIN muestras m ON m.usuario_id = u.id
        WHERE u.activo = 1
        ORDER BY u.id ASC, m.id ASC
        """
    )
    grouped: Dict[int, List[Path]] = defaultdict(list)
    for row in rows:
        user_id = int(row["usuario_id"])
        image_path = Path(row["ruta_imagen"])
        if image_path.exists():
            grouped[user_id].append(image_path)
    return grouped


def pick_with_cycle(paths: List[Path], n: int) -> List[Path]:
    if not paths:
        return []
    selected = []
    idx = 0
    while len(selected) < n:
        selected.append(paths[idx % len(paths)])
        idx += 1
    return selected


def predict_sample(recognizer: LBPHRecognizer, image_path: Path) -> Tuple[int, float, float]:
    image = cv2.imread(str(image_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        raise RuntimeError(f"No se pudo cargar imagen {image_path}")
    image = cv2.resize(image, (200, 200))

    t0 = time.perf_counter()
    label, confidence = recognizer.predict(image)
    infer_ms = (time.perf_counter() - t0) * 1000.0

    if label is None or confidence is None:
        raise RuntimeError("Predicción inválida: modelo no cargado o sin respuesta")
    return int(label), float(confidence), float(infer_ms)


def run_experiment() -> List[dict]:
    db.init_db()
    recognizer = LBPHRecognizer()

    if not Path(config.model_path).exists():
        raise RuntimeError("No existe modelo LBPH en models/lbph_model.xml")
    if not recognizer.load_model(config.model_path):
        raise RuntimeError("No fue posible cargar el modelo LBPH")

    samples_by_user = load_valid_samples()
    users = sorted(samples_by_user.keys())
    if len(users) < 2:
        raise RuntimeError("Se requieren al menos 2 usuarios con muestras válidas")

    for uid in users:
        if len(samples_by_user[uid]) == 0:
            raise RuntimeError(f"Usuario {uid} sin muestras válidas")

    results = []
    for user_id in users:
        own_paths = pick_with_cycle(samples_by_user[user_id], GENUINE_SAMPLES_PER_USER)

        impostor_pool: List[Tuple[int, Path]] = []
        for other_id in users:
            if other_id == user_id:
                continue
            for path in samples_by_user[other_id]:
                impostor_pool.append((other_id, path))

        if not impostor_pool:
            raise RuntimeError(f"No hay pool impostor para usuario {user_id}")

        impostor_selected = []
        idx = 0
        while len(impostor_selected) < IMPOSTOR_SAMPLES_PER_USER:
            impostor_selected.append(impostor_pool[idx % len(impostor_pool)])
            idx += 1

        for path in own_paths:
            pred, conf, infer_ms = predict_sample(recognizer, path)
            results.append(
                {
                    "scenario": "genuine",
                    "claimed_user": user_id,
                    "user_real": user_id,
                    "user_predicho": pred,
                    "confianza": conf,
                    "inferencia_ms": infer_ms,
                }
            )

        for real_user, path in impostor_selected:
            pred, conf, infer_ms = predict_sample(recognizer, path)
            results.append(
                {
                    "scenario": "impostor",
                    "claimed_user": user_id,
                    "user_real": real_user,
                    "user_predicho": pred,
                    "confianza": conf,
                    "inferencia_ms": infer_ms,
                }
            )

        LOGGER.info(
            "user_experiment_done user=%s genuine=%s impostor=%s",
            user_id,
            GENUINE_SAMPLES_PER_USER,
            IMPOSTOR_SAMPLES_PER_USER,
        )

    return results


def save_csv(results: List[dict], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario",
                "claimed_user",
                "user_real",
                "user_predicho",
                "confianza",
                "inferencia_ms",
            ],
        )
        writer.writeheader()
        for row in results:
            writer.writerow(row)


def main() -> int:
    setup_logging()
    results = run_experiment()
    output_csv = Path("logs/experimental_results.csv")
    save_csv(results, output_csv)
    LOGGER.info("experimental_results_written rows=%s path=%s", len(results), output_csv)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
