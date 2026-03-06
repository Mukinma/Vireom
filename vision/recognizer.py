from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from config import config


class LBPHRecognizer:
    def __init__(self):
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=config.lbph_radius,
            neighbors=config.lbph_neighbors,
            grid_x=config.lbph_grid_x,
            grid_y=config.lbph_grid_y,
        )
        self.loaded = False

    def configure(self, radius: int, neighbors: int, grid_x: int, grid_y: int) -> None:
        self.recognizer = cv2.face.LBPHFaceRecognizer_create(
            radius=radius,
            neighbors=neighbors,
            grid_x=grid_x,
            grid_y=grid_y,
        )
        self.loaded = False

    def load_model(self, path: str = config.model_path) -> bool:
        model_file = Path(path)
        if not model_file.exists():
            self.loaded = False
            return False
        self.recognizer.read(path)
        self.loaded = True
        return True

    def save_model(self, path: str = config.model_path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.recognizer.write(path)
        self.loaded = True

    def train(self, images: list[np.ndarray], labels: list[int]) -> None:
        if not images or not labels:
            raise ValueError("No hay datos de entrenamiento")
        self.recognizer.train(images, np.array(labels))
        self.loaded = True

    def predict(self, face_200x200_gray) -> tuple[Optional[int], Optional[float]]:
        if not self.loaded:
            return None, None
        label, confidence = self.recognizer.predict(face_200x200_gray)
        return int(label), float(confidence)
