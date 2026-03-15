import json
import logging
import re
from dataclasses import dataclass, asdict
from pathlib import Path

import cv2

from config import config
from database.db import db


LOGGER = logging.getLogger("camerapi.bootstrap")
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp"}
MIN_SAMPLES_PER_USER = 20


@dataclass
class UserBootstrapStats:
    user_id: int
    user_created: bool
    total_images: int
    valid_samples: int
    discarded_samples: int
    trainable: bool


def setup_logging() -> None:
    Path("logs").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s level=%(levelname)s logger=%(name)s msg=%(message)s",
        handlers=[
            logging.FileHandler("logs/bootstrap_dataset.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def ensure_user(user_id: int) -> bool:
    existing = db.fetch_one("SELECT id FROM usuarios WHERE id=?", (user_id,))
    if existing:
        return False
    db.execute(
        "INSERT INTO usuarios (id, nombre, activo) VALUES (?, ?, 1)",
        (user_id, f"Usuario {user_id}"),
    )
    LOGGER.info("user_created user_id=%s", user_id)
    return True


def insert_sample_if_missing(user_id: int, image_path: str) -> None:
    existing = db.fetch_one(
        "SELECT id FROM muestras WHERE usuario_id=? AND imagen_ref=?",
        (user_id, image_path),
    )
    if existing:
        return
    db.insert_sample(user_id, image_path)


def detect_and_process_face(classifier, image_path: Path):
    raw = cv2.imread(str(image_path))
    if raw is None:
        return None, "image_read_failed"
    gray = cv2.cvtColor(raw, cv2.COLOR_BGR2GRAY)
    faces = classifier.detectMultiScale(
        gray,
        scaleFactor=config.detect_scale_factor,
        minNeighbors=config.detect_min_neighbors,
        minSize=(config.detect_min_size_w, config.detect_min_size_h),
    )
    if len(faces) == 0:
        return None, "no_face"
    if len(faces) > 1:
        return None, "multiple_faces"
    x, y, w, h = faces[0]
    roi = gray[y : y + h, x : x + w]
    roi = cv2.resize(roi, (200, 200))
    roi = cv2.equalizeHist(roi)
    return roi, "ok"


def main() -> int:
    setup_logging()
    db.init_db()

    dataset_root = Path(config.dataset_dir)
    processed_root = Path("dataset_processed")
    processed_root.mkdir(parents=True, exist_ok=True)

    cascade_path = cv2.data.haarcascades + config.cascade_filename
    classifier = cv2.CascadeClassifier(cascade_path)

    users_detected = []
    users_created = []
    user_stats: list[UserBootstrapStats] = []
    discarded_reasons: dict[str, int] = {}
    errors: list[str] = []

    user_dirs = sorted([d for d in dataset_root.glob("user_*") if d.is_dir()])
    for user_dir in user_dirs:
        match = re.fullmatch(r"user_(\d+)", user_dir.name)
        if not match:
            errors.append(f"invalid_user_dir_name:{user_dir}")
            LOGGER.error("invalid_user_dir_name path=%s", user_dir)
            continue

        user_id = int(match.group(1))
        users_detected.append(user_id)
        created = ensure_user(user_id)
        if created:
            users_created.append(user_id)

        output_dir = processed_root / f"user_{user_id}"
        output_dir.mkdir(parents=True, exist_ok=True)

        image_files = sorted([p for p in user_dir.iterdir() if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS])
        valid_samples = 0
        discarded_samples = 0

        for image_file in image_files:
            try:
                face_200, status = detect_and_process_face(classifier, image_file)
                if status != "ok":
                    discarded_samples += 1
                    discarded_reasons[status] = discarded_reasons.get(status, 0) + 1
                    LOGGER.warning(
                        "sample_discarded user_id=%s image=%s reason=%s",
                        user_id,
                        image_file,
                        status,
                    )
                    continue

                output_name = f"{image_file.stem}_proc.png"
                output_path = output_dir / output_name
                cv2.imwrite(str(output_path), face_200)
                insert_sample_if_missing(user_id, str(output_path))
                valid_samples += 1
            except Exception as exc:
                discarded_samples += 1
                discarded_reasons["exception"] = discarded_reasons.get("exception", 0) + 1
                message = f"sample_processing_exception user_id={user_id} image={image_file} error={exc}"
                errors.append(message)
                LOGGER.exception(message)

        trainable = valid_samples >= MIN_SAMPLES_PER_USER
        if not trainable:
            db.set_user_status(user_id, False)
            LOGGER.error(
                "user_not_trainable user_id=%s valid_samples=%s required=%s",
                user_id,
                valid_samples,
                MIN_SAMPLES_PER_USER,
            )
        else:
            db.set_user_status(user_id, True)

        user_stats.append(
            UserBootstrapStats(
                user_id=user_id,
                user_created=created,
                total_images=len(image_files),
                valid_samples=valid_samples,
                discarded_samples=discarded_samples,
                trainable=trainable,
            )
        )

    non_trainable = [s.user_id for s in user_stats if not s.trainable]
    can_train = len(non_trainable) == 0 and len(user_stats) > 0

    report = {
        "users_detected": users_detected,
        "users_created": users_created,
        "total_users_detected": len(users_detected),
        "total_users_created": len(users_created),
        "user_stats": [asdict(s) for s in user_stats],
        "total_valid_samples": sum(s.valid_samples for s in user_stats),
        "total_discarded_samples": sum(s.discarded_samples for s in user_stats),
        "discarded_reasons": discarded_reasons,
        "non_trainable_users": non_trainable,
        "can_train": can_train,
        "errors": errors,
    }

    Path("logs").mkdir(parents=True, exist_ok=True)
    report_path = Path("logs/bootstrap_report.json")
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    LOGGER.info("bootstrap_report_written path=%s can_train=%s", report_path, can_train)

    if not can_train:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
