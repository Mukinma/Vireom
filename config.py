import os
from dataclasses import dataclass


@dataclass
class AppConfig:
    app_name: str = "CameraPI Access"
    host: str = "0.0.0.0"
    port: int = 8000
    secret_key: str = os.getenv("CAMERAPI_SECRET", "camerapi-local-secret")

    db_path: str = "database/camerapi.db"
    model_path: str = "models/lbph_model.xml"
    dataset_dir: str = "dataset"
    logs_path: str = "logs/system.log"

    camera_index: int = 0
    frame_width: int = 640
    frame_height: int = 480
    max_fps: int = 15
    process_interval_ms: int = 200
    cv_threads: int = 2
    camera_buffer_size: int = 1

    cascade_filename: str = "haarcascade_frontalface_default.xml"
    detect_downscale: float = 0.5
    detect_scale_factor: float = 1.15
    detect_min_neighbors: int = 5
    detect_min_size_w: int = 96
    detect_min_size_h: int = 96

    recognition_cooldown_ms: int = 200
    roi_absdiff_threshold: float = 6.0
    roi_cache_max_age_ms: int = 200

    lbph_radius: int = 1
    lbph_neighbors: int = 8
    lbph_grid_x: int = 8
    lbph_grid_y: int = 8

    default_confidence_threshold: float = 70.0
    default_open_seconds: int = 3
    default_max_attempts: int = 3

    admin_user: str = os.getenv("CAMERAPI_ADMIN_USER", "admin")
    admin_password: str = os.getenv("CAMERAPI_ADMIN_PASSWORD", "admin123")


config = AppConfig()
