"""Guided facial enrollment session — 7-step head-pose capture FSM.

Captures 5 samples per step (35 total) at different head orientations
to build a robust LBPH training set.  No neural networks — pose
verification uses only bbox geometry heuristics.
"""

import logging
import threading
import time
from pathlib import Path
from typing import Any, Optional

import cv2
import numpy as np

from config import config
from vision.pose_heuristic import PoseHeuristic, PoseHints

logger = logging.getLogger("camerapi.enrollment")

# ── Step definitions ───────────────────────────────────────────────

ENROLLMENT_STEPS: list[dict[str, str]] = [
    {"name": "center",     "label": "Mira de frente",               "icon": "circle-dot"},
    {"name": "tilt_left",  "label": "Inclina hacia la izquierda",   "icon": "arrow-left"},
    {"name": "tilt_right", "label": "Inclina hacia la derecha",     "icon": "arrow-right"},
    {"name": "look_up",    "label": "Mira hacia arriba",            "icon": "arrow-up"},
    {"name": "look_down",  "label": "Mira hacia abajo",             "icon": "arrow-down"},
    {"name": "turn_left",  "label": "Gira a la izquierda",          "icon": "rotate-ccw"},
    {"name": "turn_right", "label": "Gira a la derecha",            "icon": "rotate-cw"},
]

# ── Valid FSM states ───────────────────────────────────────────────

STATES = frozenset({
    "idle",
    "step_active",
    "holding",
    "capturing",
    "step_complete",
    "completed",
    "face_lost",
    "low_light",
    "error",
})


class EnrollmentSession:
    """FSM that drives the guided capture process."""

    def __init__(
        self,
        user_id: int,
        pose: PoseHeuristic,
    ) -> None:
        self.user_id = user_id
        self.pose = pose

        self.samples_per_step: int = config.enrollment_samples_per_step
        self.hold_steady_ms: int = config.enrollment_hold_steady_ms
        self.brightness_threshold: float = config.enrollment_brightness_threshold
        self.face_lost_timeout_ms: int = config.enrollment_face_lost_timeout_ms

        self._state: str = "step_active"
        self._current_step: int = 0
        self._samples: dict[int, list[str]] = {}  # step_index -> [paths]
        self._hold_start_ms: Optional[float] = None
        self._last_face_ms: float = self._now()
        self._last_hints: Optional[PoseHints] = None
        self._message: str = ENROLLMENT_STEPS[0]["label"]
        self._lock = threading.Lock()

        # Ensure dataset directory exists
        self._user_dir = Path(config.dataset_dir) / f"user_{user_id}"
        self._user_dir.mkdir(parents=True, exist_ok=True)

        self.pose.clear_baseline()
        logger.info("enrollment_session_created user_id=%s steps=%s", user_id, len(ENROLLMENT_STEPS))

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _now() -> float:
        return time.time() * 1000.0

    @property
    def _step(self) -> dict[str, str]:
        return ENROLLMENT_STEPS[self._current_step]

    @property
    def _step_samples(self) -> list[str]:
        return self._samples.setdefault(self._current_step, [])

    # ── Main update (called from process loop each cycle) ──────────

    def update(
        self,
        frame: np.ndarray,
        gray: np.ndarray,
        face: Optional[tuple[int, int, int, int]],
        faces_count: int,
    ) -> None:
        """Advance the FSM based on the current camera frame.

        Thread-safe — called from the detection pipeline thread.
        """
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

        # Terminal states — nothing to do
        if self._state in ("completed", "error"):
            return

        # ── No face ────────────────────────────────────────────────
        if face is None or faces_count == 0:
            elapsed = now - self._last_face_ms
            if elapsed >= self.face_lost_timeout_ms:
                self._state = "face_lost"
                self._message = "Centra tu rostro en la guia"
                self._hold_start_ms = None
            elif self._state != "face_lost":
                # Brief grace period — keep current state
                pass
            return

        # Face is present
        self._last_face_ms = now

        # Recover from face_lost
        if self._state == "face_lost":
            self._state = "step_active"
            self._hold_start_ms = None

        # ── Multiple faces ─────────────────────────────────────────
        if faces_count > 1:
            self._state = "step_active"
            self._message = "Solo debe haber una persona"
            self._hold_start_ms = None
            return

        # ── Brightness check ───────────────────────────────────────
        frame_shape = gray.shape
        hints = self.pose.analyze(gray, face, frame_shape)
        self._last_hints = hints

        if hints.brightness < self.brightness_threshold:
            self._state = "low_light"
            self._message = "Mejora la iluminacion"
            self._hold_start_ms = None
            return

        if self._state == "low_light":
            self._state = "step_active"

        # ── Center step: set baseline on first detection ───────────
        step_name = self._step["name"]
        if step_name == "center" and not self.pose.has_baseline:
            self.pose.set_baseline(face, frame_shape)

        # ── Check pose match ───────────────────────────────────────
        matched, guidance_msg = self.pose.check_step(step_name, hints)

        if not matched:
            self._state = "step_active"
            self._message = guidance_msg
            self._hold_start_ms = None
            return

        # Pose matched — start or continue holding
        if self._hold_start_ms is None:
            self._hold_start_ms = now

        held_ms = now - self._hold_start_ms

        if held_ms < self.hold_steady_ms:
            self._state = "holding"
            self._message = "Mantente quieto..."
            return

        # ── Capture sample ─────────────────────────────────────────
        self._state = "capturing"
        path = self._capture(frame, gray, face)
        if path:
            self._step_samples.append(path)
            logger.info(
                "enrollment_capture step=%s sample=%s/%s path=%s",
                step_name,
                len(self._step_samples),
                self.samples_per_step,
                path,
            )

        # Reset hold to capture another sample (or advance)
        self._hold_start_ms = None

        # ── Check step completion ──────────────────────────────────
        if len(self._step_samples) >= self.samples_per_step:
            self._advance_step()

    # ── Capture ────────────────────────────────────────────────────

    def _capture(
        self,
        frame: np.ndarray,
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
        cv2.imwrite(str(full_path), roi_resized)

        relative_path = f"{config.dataset_dir}/user_{self.user_id}/{filename}"
        return relative_path

    # ── Step advancement ───────────────────────────────────────────

    def _advance_step(self) -> None:
        self._state = "step_complete"
        self._message = "Paso completado"
        next_idx = self._current_step + 1
        if next_idx >= len(ENROLLMENT_STEPS):
            self._state = "completed"
            self._message = "Enrolamiento completado"
            logger.info("enrollment_completed user_id=%s total_samples=%s", self.user_id, self.total_captured)
            return

        self._current_step = next_idx
        self._hold_start_ms = None
        self._state = "step_active"
        self._message = ENROLLMENT_STEPS[next_idx]["label"]
        logger.info("enrollment_step_advance user_id=%s step=%s", self.user_id, ENROLLMENT_STEPS[next_idx]["name"])

    # ── Retry current step ─────────────────────────────────────────

    def retry_step(self) -> None:
        with self._lock:
            self._samples[self._current_step] = []
            self._hold_start_ms = None
            self._state = "step_active"
            self._message = self._step["label"]
            logger.info("enrollment_retry_step user_id=%s step=%s", self.user_id, self._step["name"])

    # ── Abort ──────────────────────────────────────────────────────

    def abort(self) -> None:
        with self._lock:
            self._state = "error"
            self._message = "Enrolamiento cancelado"
            logger.info("enrollment_aborted user_id=%s", self.user_id)

    # ── Properties ─────────────────────────────────────────────────

    @property
    def total_captured(self) -> int:
        return sum(len(paths) for paths in self._samples.values())

    @property
    def all_sample_paths(self) -> list[tuple[str, str]]:
        """Return list of (path, pose_type) for all captured samples."""
        result: list[tuple[str, str]] = []
        for step_idx, paths in sorted(self._samples.items()):
            pose_type = ENROLLMENT_STEPS[step_idx]["name"]
            for p in paths:
                result.append((p, pose_type))
        return result

    # ── Status snapshot ────────────────────────────────────────────

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

        steps_summary = []
        for i, s in enumerate(ENROLLMENT_STEPS):
            captured = len(self._samples.get(i, []))
            if i < self._current_step:
                status = "complete"
            elif i == self._current_step:
                status = "active"
            else:
                status = "pending"
            steps_summary.append({
                "name": s["name"],
                "label": s["label"],
                "icon": s["icon"],
                "status": status,
                "samples": captured,
            })

        guidance_arrow = None
        if self._state in ("step_active", "face_lost"):
            from vision.pose_heuristic import PoseHeuristic as _PH
            guidance_arrow = _PH.guidance_arrow(step["name"])

        return {
            "state": self._state,
            "current_step": self._current_step,
            "total_steps": len(ENROLLMENT_STEPS),
            "step_name": step["name"],
            "step_label": step["label"],
            "step_icon": step["icon"],
            "samples_this_step": len(step_samples),
            "samples_needed": self.samples_per_step,
            "total_captured": self.total_captured,
            "total_needed": self.samples_per_step * len(ENROLLMENT_STEPS),
            "pose_matched": self._state in ("holding", "capturing", "step_complete"),
            "hold_progress": round(hold_progress, 3),
            "face_detected": self._state not in ("face_lost",),
            "brightness_ok": self._state != "low_light",
            "message": self._message,
            "guidance_arrow": guidance_arrow,
            "steps_summary": steps_summary,
            "user_id": self.user_id,
        }
