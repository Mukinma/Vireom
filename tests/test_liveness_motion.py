"""Tests for Layer 2 (temporal / motion) liveness metrics.

F0: buffer push/pop mechanics and interface only.
F2 will add real optical-flow assertions.
"""

import time

import numpy as np
import pytest

from config import AppConfig
from vision.liveness import LivenessDetector, LivenessZone


def _make_cfg(enabled: bool = True, buf_size: int = 10) -> AppConfig:
    cfg = AppConfig()
    object.__setattr__(cfg, "liveness_enabled", enabled)
    object.__setattr__(cfg, "liveness_buffer_size", buf_size)
    return cfg


def _blank_frame(h: int = 60, w: int = 80) -> tuple[np.ndarray, np.ndarray]:
    import cv2
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, gray


def _face() -> tuple[int, int, int, int]:
    return (10, 10, 40, 40)


class TestBufferMechanics:
    def setup_method(self):
        self.cfg = _make_cfg(buf_size=5)
        self.det = LivenessDetector(self.cfg)

    def test_push_fills_buffer(self):
        for i in range(3):
            bgr, gray = _blank_frame()
            self.det.push_frame(bgr, gray, _face(), seq=i)
        assert len(self.det._buf) == 3

    def test_buffer_caps_at_maxlen(self):
        for i in range(10):
            bgr, gray = _blank_frame()
            self.det.push_frame(bgr, gray, _face(), seq=i)
        assert len(self.det._buf) == 5

    def test_frames_are_copies(self):
        bgr, gray = _blank_frame()
        self.det.push_frame(bgr, gray, _face(), seq=0)
        bgr[:] = 255  # mutate original
        stored = self.det._buf[-1].frame
        assert stored.max() == 0

    def test_buffer_is_thread_safe(self):
        import threading
        errors = []

        def worker(i: int):
            try:
                for j in range(20):
                    bgr, gray = _blank_frame()
                    self.det.push_frame(bgr, gray, _face(), seq=i * 20 + j)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert not errors


class TestMotionStubs:
    """F0: motion score is 0.5 stub; only interface tested."""

    def setup_method(self):
        self.cfg = _make_cfg()
        self.det = LivenessDetector(self.cfg)

    def _push_n(self, n: int) -> None:
        for i in range(n):
            bgr, gray = _blank_frame()
            self.det.push_frame(bgr, gray, _face(), seq=i)

    def test_motion_score_present_in_verdict(self):
        self._push_n(6)
        bgr, gray = _blank_frame()
        v = self.det.evaluate(bgr, gray, _face(), seq=99)
        assert v.motion is not None
        m = v.motion
        assert 0.0 <= m.affine_residual <= 1.0
        assert 0.0 <= m.bbox_variance <= 1.0
        assert 0.0 <= m.score <= 1.0

    def test_few_frames_returns_neutral_motion(self):
        self._push_n(2)  # fewer than 4 → neutral stub
        bgr, gray = _blank_frame()
        v = self.det.evaluate(bgr, gray, _face(), seq=99)
        assert v.motion.frames_used <= 3
        assert abs(v.motion.score - 0.5) < 1e-6

    def test_full_buffer_returns_frames_used(self):
        self._push_n(10)
        bgr, gray = _blank_frame()
        v = self.det.evaluate(bgr, gray, _face(), seq=99)
        assert v.motion.frames_used >= 4
