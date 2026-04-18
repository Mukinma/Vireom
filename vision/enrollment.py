"""Guided facial enrollment session.

The backend owns the enrollment lifecycle and emits a rehydratable UI snapshot
that the admin interface can render directly.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from config import config
from vision.pose_heuristic import PoseHeuristic
from vision.secure_storage import storage as _storage

logger = logging.getLogger("camerapi.enrollment")


ENROLLMENT_STEPS: list[dict[str, str]] = [
    {"name": "center", "label": "Mira de frente", "icon": "circle-dot"},
    {"name": "tilt_left", "label": "Inclina hacia la izquierda", "icon": "arrow-left"},
    {"name": "tilt_right", "label": "Inclina hacia la derecha", "icon": "arrow-right"},
    {"name": "look_up", "label": "Mira hacia arriba", "icon": "arrow-up"},
    {"name": "look_down", "label": "Mira hacia abajo", "icon": "arrow-down"},
    {"name": "turn_left", "label": "Gira a la izquierda", "icon": "rotate-ccw"},
    {"name": "turn_right", "label": "Gira a la derecha", "icon": "rotate-cw"},
]

STATES = frozenset(
    {
        "idle",
        "step_active",
        "holding",
        "capturing",
        "step_complete",
        "completed",
        "face_lost",
        "low_light",
        "error",
    }
)


class EnrollmentSession:
    """FSM that drives the guided capture process."""

    def __init__(
        self,
        user_id: int,
        pose: PoseHeuristic,
        user_name: Optional[str] = None,
    ) -> None:
        self.user_id = user_id
        self.user_name = user_name or f"Usuario {user_id}"
        self.pose = pose

        self.samples_per_step: int = config.enrollment_samples_per_step
        self.hold_steady_ms: int = config.enrollment_hold_steady_ms
        self.brightness_threshold: float = config.enrollment_brightness_threshold
        self.face_lost_timeout_ms: int = config.enrollment_face_lost_timeout_ms

        now = self._now()
        self._state: str = "step_active"
        self._current_step: int = 0
        self._samples: dict[int, list[str]] = {}
        self._hold_start_ms: Optional[float] = None
        self._last_face_ms: float = now
        self._message: str = ENROLLMENT_STEPS[0]["label"]
        self._faces_count: int = 0
        self._started_at_ms: int = int(now)
        self._updated_at_ms: int = int(now)
        self._samples_persisted: bool = False
        self._lock = threading.Lock()

        self._user_dir = Path(config.dataset_dir) / f"user_{user_id}"
        self._user_dir.mkdir(parents=True, exist_ok=True)

        self.pose.clear_baseline()
        logger.info("enrollment_session_created user_id=%s steps=%s", user_id, len(ENROLLMENT_STEPS))

    @staticmethod
    def _now() -> float:
        return time.time() * 1000.0

    def _touch(self, now: Optional[float] = None) -> None:
        self._updated_at_ms = int(now if now is not None else self._now())

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_terminal(self) -> bool:
        return self._state in ("completed", "error")

    @property
    def samples_persisted(self) -> bool:
        return self._samples_persisted

    def mark_persisted(self) -> None:
        with self._lock:
            self._samples_persisted = True
            self._touch()

    @property
    def _step(self) -> dict[str, str]:
        return ENROLLMENT_STEPS[self._current_step]

    @property
    def _step_samples(self) -> list[str]:
        return self._samples.setdefault(self._current_step, [])

    def _delete_paths(self, paths: list[str]) -> None:
        dataset_root = Path(config.dataset_dir).resolve()
        for raw_path in paths:
            path_obj = Path(raw_path)
            if not path_obj.is_absolute():
                path_obj = Path.cwd() / path_obj
            try:
                if path_obj.exists():
                    path_obj.unlink()
                parent = path_obj.parent
                if parent.exists() and parent.resolve() != dataset_root and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                logger.warning("enrollment_cleanup_failed path=%s", raw_path)

    def clear_step_files(self, step_index: int) -> None:
        with self._lock:
            paths = list(self._samples.get(step_index, []))
            self._delete_paths(paths)
            self._samples[step_index] = []
            self._touch()

    def clear_all_files(self) -> None:
        with self._lock:
            paths = [path for step_paths in self._samples.values() for path in step_paths]
            self._delete_paths(paths)
            self._samples = {}
            self._touch()

    def update(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        face: Optional[tuple[int, int, int, int]],
        faces_count: int,
    ) -> None:
        with self._lock:
            self._update_inner(frame, gray, face, faces_count)

    def _update_inner(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        face: Optional[tuple[int, int, int, int]],
        faces_count: int,
    ) -> None:
        now = self._now()
        self._faces_count = max(0, int(faces_count))

        if self.is_terminal:
            return

        if face is None or faces_count == 0:
            elapsed = now - self._last_face_ms
            if elapsed >= self.face_lost_timeout_ms:
                self._state = "face_lost"
                self._message = "Centra tu rostro en la guia"
                self._hold_start_ms = None
                self._touch(now)
            return

        self._last_face_ms = now

        if self._state == "face_lost":
            self._state = "step_active"
            self._hold_start_ms = None
            self._touch(now)

        if faces_count > 1:
            self._state = "step_active"
            self._message = "Solo debe haber una persona"
            self._hold_start_ms = None
            self._touch(now)
            return

        frame_shape = gray.shape
        hints = self.pose.analyze(gray, face, frame_shape)

        if hints.brightness < self.brightness_threshold:
            self._state = "low_light"
            self._message = "Mejora la iluminacion"
            self._hold_start_ms = None
            self._touch(now)
            return

        if self._state == "low_light":
            self._state = "step_active"
            self._touch(now)

        step_name = self._step["name"]
        if step_name == "center" and not self.pose.has_baseline:
            self.pose.set_baseline(face, frame_shape)

        matched, guidance_msg = self.pose.check_step(step_name, hints)
        if not matched:
            self._state = "step_active"
            self._message = guidance_msg
            self._hold_start_ms = None
            self._touch(now)
            return

        if self._hold_start_ms is None:
            self._hold_start_ms = now
            self._touch(now)

        held_ms = now - self._hold_start_ms
        if held_ms < self.hold_steady_ms:
            self._state = "holding"
            self._message = "Mantente quieto..."
            self._touch(now)
            return

        self._state = "capturing"
        self._touch(now)
        path = self._capture(gray, face)
        self._hold_start_ms = None

        if not path:
            self._state = "step_active"
            self._message = "No se pudo capturar la muestra"
            self._touch(now)
            return

        self._step_samples.append(path)
        logger.info(
            "enrollment_capture step=%s sample=%s/%s path=%s",
            step_name,
            len(self._step_samples),
            self.samples_per_step,
            path,
        )

        if len(self._step_samples) >= self.samples_per_step:
            self._advance_step(now)
            return

        self._state = "step_active"
        self._message = self._step["label"]
        self._touch(now)

    def _capture(
        self,
        gray: np.ndarray,
        face: tuple[int, int, int, int],
    ) -> Optional[str]:
        x, y, w, h = [int(v) for v in face]
        x = max(0, x)
        y = max(0, y)
        roi = gray[y : y + h, x : x + w]
        if roi.size == 0:
            return None

        roi_resized = cv2.resize(roi, (200, 200))
        step_name = self._step["name"]
        idx = len(self._step_samples) + 1
        filename = f"enroll_{step_name}_{idx:03d}.jpg"
        full_path = self._user_dir / filename
        _storage.write_image(full_path, roi_resized)
        return f"{config.dataset_dir}/user_{self.user_id}/{filename}"

    def _advance_step(self, now: Optional[float] = None) -> None:
        self._state = "step_complete"
        self._message = "Paso completado"
        next_idx = self._current_step + 1

        if next_idx >= len(ENROLLMENT_STEPS):
            self._state = "completed"
            self._message = "Enrolamiento completado"
            self._touch(now)
            logger.info("enrollment_completed user_id=%s total_samples=%s", self.user_id, self.total_captured)
            return

        self._current_step = next_idx
        self._hold_start_ms = None
        self._state = "step_active"
        self._message = ENROLLMENT_STEPS[next_idx]["label"]
        self._touch(now)
        logger.info("enrollment_step_advance user_id=%s step=%s", self.user_id, ENROLLMENT_STEPS[next_idx]["name"])

    def retry_step(self) -> None:
        with self._lock:
            if self.is_terminal:
                return
            current_step = self._current_step
            self._delete_paths(list(self._samples.get(current_step, [])))
            self._samples[current_step] = []
            self._hold_start_ms = None
            self._state = "step_active"
            self._message = self._step["label"]
            self._touch()
            logger.info("enrollment_retry_step user_id=%s step=%s", self.user_id, self._step["name"])

    def abort(self) -> None:
        with self._lock:
            self._state = "error"
            self._message = "Enrolamiento cancelado"
            self._touch()
            logger.info("enrollment_aborted user_id=%s", self.user_id)

    def fail(self, message: str = "Se interrumpio la captura") -> None:
        with self._lock:
            self._state = "error"
            self._message = message
            self._touch()
            logger.warning("enrollment_failed user_id=%s message=%s", self.user_id, message)

    @property
    def total_captured(self) -> int:
        return sum(len(paths) for paths in self._samples.values())

    @property
    def all_sample_paths(self) -> list[tuple[str, str]]:
        result: list[tuple[str, str]] = []
        for step_idx, paths in sorted(self._samples.items()):
            pose_type = ENROLLMENT_STEPS[step_idx]["name"]
            for path in paths:
                result.append((path, pose_type))
        return result

    def get_status(self) -> dict[str, Any]:
        with self._lock:
            return self._build_status()

    def _build_status(self) -> dict[str, Any]:
        now = self._now()
        hold_progress = 0.0
        if self._hold_start_ms is not None and self._state == "holding":
            held = now - self._hold_start_ms
            hold_progress = min(1.0, held / max(1, self.hold_steady_ms))

        step = self._step
        step_samples = self._step_samples
        completed_session = self._state == "completed"

        steps_summary = []
        for i, step_meta in enumerate(ENROLLMENT_STEPS):
            captured = len(self._samples.get(i, []))
            if completed_session and i <= self._current_step:
                status = "complete"
            elif i < self._current_step:
                status = "complete"
            elif i == self._current_step:
                status = "active"
            else:
                status = "pending"

            steps_summary.append(
                {
                    "name": step_meta["name"],
                    "label": step_meta["label"],
                    "icon": step_meta["icon"],
                    "status": status,
                    "samples": captured,
                    "needed": self.samples_per_step,
                }
            )

        if self._state == "completed":
            phase = "completed_review"
        elif self._state == "error":
            phase = "recoverable_error"
        else:
            phase = "active"

        can_retry = phase == "active" and len(step_samples) > 0
        can_abort = phase in ("active", "recoverable_error")
        can_finish = phase == "completed_review"
        can_train = phase == "completed_review"

        guidance_arrow = None
        if phase == "active" and self._state not in ("holding", "capturing") and self._faces_count <= 1:
            guidance_arrow = PoseHeuristic.guidance_arrow(step["name"])

        instruction = step["label"]
        if phase == "completed_review":
            instruction = "Enrolamiento completado"
        elif phase == "recoverable_error":
            instruction = "Se detuvo el enrolamiento"

        hint = self._message
        if phase == "completed_review":
            hint = f"{self.total_captured} muestras listas para entrenar"

        return {
            "phase": phase,
            "state": self._state,
            "user_id": self.user_id,
            "user_name": self.user_name,
            "current_step": self._current_step,
            "total_steps": len(ENROLLMENT_STEPS),
            "step_name": step["name"],
            "step_label": step["label"],
            "step_icon": step["icon"],
            "samples_this_step": len(step_samples),
            "samples_needed": self.samples_per_step,
            "total_captured": self.total_captured,
            "total_needed": self.samples_per_step * len(ENROLLMENT_STEPS),
            "steps_summary": steps_summary,
            "guidance": {
                "instruction": instruction,
                "hint": hint,
                "arrow": guidance_arrow,
                "hold_progress": round(hold_progress, 3),
                "pose_matched": self._state in ("holding", "capturing", "step_complete", "completed"),
                "face_detected": self._faces_count > 0 and self._state != "face_lost",
                "brightness_ok": self._state != "low_light",
                "multiple_faces": self._faces_count > 1,
            },
            "actions": {
                "can_retry": can_retry,
                "can_abort": can_abort,
                "can_finish": can_finish,
                "can_train": can_train,
            },
            "started_at": self._started_at_ms,
            "updated_at": self._updated_at_ms,
        }
