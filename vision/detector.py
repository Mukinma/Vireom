from typing import Any

import cv2

from config import config


class HaarFaceDetector:
    def __init__(self):
        cascade_path = cv2.data.haarcascades + config.cascade_filename
        self.classifier = cv2.CascadeClassifier(cascade_path)

    def detect(self, gray_image, params: dict[str, Any]):
        scale_factor = float(params.get("scaleFactor", config.detect_scale_factor))
        min_neighbors = int(params.get("minNeighbors", config.detect_min_neighbors))
        min_size = params.get("minSize", [config.detect_min_size_w, config.detect_min_size_h])
        min_size_tuple = (int(min_size[0]), int(min_size[1]))
        downscale = float(params.get("downscale", config.detect_downscale))

        if 0.0 < downscale < 1.0:
            reduced = cv2.resize(
                gray_image,
                (0, 0),
                fx=downscale,
                fy=downscale,
                interpolation=cv2.INTER_LINEAR,
            )
            min_size_reduced = (
                max(1, int(min_size_tuple[0] * downscale)),
                max(1, int(min_size_tuple[1] * downscale)),
            )
            faces_reduced = self.classifier.detectMultiScale(
                reduced,
                scaleFactor=scale_factor,
                minNeighbors=min_neighbors,
                minSize=min_size_reduced,
            )
            if len(faces_reduced) == 0:
                return faces_reduced

            inv = 1.0 / downscale
            height, width = gray_image.shape[:2]
            faces_scaled: list[tuple[int, int, int, int]] = []
            for face in faces_reduced:
                x, y, w, h = [int(v) for v in face]
                ox = max(0, int(round(x * inv)))
                oy = max(0, int(round(y * inv)))
                ow = max(1, int(round(w * inv)))
                oh = max(1, int(round(h * inv)))

                if ox >= width or oy >= height:
                    continue
                if ox + ow > width:
                    ow = width - ox
                if oy + oh > height:
                    oh = height - oy
                if ow <= 0 or oh <= 0:
                    continue
                faces_scaled.append((ox, oy, ow, oh))
            return faces_scaled

        return self.classifier.detectMultiScale(
            gray_image,
            scaleFactor=scale_factor,
            minNeighbors=min_neighbors,
            minSize=min_size_tuple,
        )
