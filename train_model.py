import json
import logging
import time
from pathlib import Path

import cv2
import numpy as np

from config import config
from database.db import db
from vision.recognizer import LBPHRecognizer


LOGGER = logging.getLogger("camerapi.train")
MIN_SAMPLES_PER_USER = 20


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/train_model.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def load_eligible_samples():
    users = db.fetch_all("SELECT id, nombre FROM usuarios ORDER BY id ASC")
    if not users:
        raise RuntimeError("No hay usuarios en BD")

    eligible_users = []
    user_sample_map = {}
    for user in users:
        uid = int(user["id"])
        rows = db.fetch_all("SELECT ruta_imagen FROM muestras WHERE usuario_id=?", (uid,))
        valid_paths = [Path(r["ruta_imagen"]) for r in rows if Path(r["ruta_imagen"]).exists()]
        user_sample_map[uid] = valid_paths
        if len(valid_paths) >= MIN_SAMPLES_PER_USER:
            eligible_users.append(uid)

    non_eligible = [uid for uid in user_sample_map.keys() if uid not in eligible_users]
    if non_eligible:
        raise RuntimeError(f"Usuarios no entrenables (<{MIN_SAMPLES_PER_USER} muestras): {non_eligible}")

    images = []
    labels = []
    for uid in eligible_users:
        for path in user_sample_map[uid]:
            image = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            if image is None:
                continue
            image = cv2.resize(image, (200, 200))
            images.append(image)
            labels.append(uid)

    if not images:
        raise RuntimeError("No hay muestras válidas para entrenamiento")

    return images, labels, eligible_users


def main() -> int:
    setup_logging()
    db.init_db()

    images, labels, eligible_users = load_eligible_samples()

    train_start = time.perf_counter()
    recognizer = cv2.face.LBPHFaceRecognizer_create(
        radius=1,
        neighbors=8,
        grid_x=8,
        grid_y=8,
    )
    recognizer.train(images, np.array(labels))
    elapsed_sec = time.perf_counter() - train_start

    model_path = Path(config.model_path)
    model_path.parent.mkdir(parents=True, exist_ok=True)
    recognizer.write(str(model_path))

    if not model_path.exists() or model_path.stat().st_size == 0:
        raise RuntimeError("Modelo no guardado correctamente")

    verifier = LBPHRecognizer()
    loaded = verifier.load_model(str(model_path))
    if not loaded:
        raise RuntimeError("Modelo guardado pero no cargable")

    metrics = {
        "training_time_sec": round(elapsed_sec, 4),
        "total_samples": len(images),
        "trained_users": len(set(eligible_users)),
        "user_ids": sorted(list(set(eligible_users))),
        "model_path": str(model_path),
        "model_size_bytes": model_path.stat().st_size,
    }

    Path("logs").mkdir(parents=True, exist_ok=True)
    metrics_path = Path("logs/train_metrics.json")
    metrics_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("training_completed metrics=%s", metrics)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
