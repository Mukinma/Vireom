"""Tests for Layer 1 (passive) liveness metrics.

Fixtures use synthetic NumPy images — no real camera required.
Metric stubs return 0.5 (F0); tests will tighten in F1.
"""

import numpy as np
import pytest

from config import AppConfig
from vision.liveness import LivenessDetector, LivenessZone


# ─── Synthetic fixtures ───────────────────────────────────────────────────────

def _make_face_bbox(frame_shape: tuple[int, int, int]) -> tuple[int, int, int, int]:
    h, w = frame_shape[:2]
    x, y = w // 4, h // 4
    return x, y, w // 2, h // 2


def synthetic_live(h: int = 120, w: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Simulate a live face ROI: broadband texture + mild noise."""
    rng = np.random.default_rng(42)
    bgr = rng.integers(80, 200, (h, w, 3), dtype=np.uint8)
    # Add low-amplitude non-periodic texture
    noise = rng.normal(0, 12, (h, w, 3)).astype(np.int16)
    bgr = np.clip(bgr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    gray = cv2_gray(bgr)
    return bgr, gray


def synthetic_print(h: int = 120, w: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Simulate a printed photo: low-variance, desaturated, JPEG-artifact blur."""
    rng = np.random.default_rng(7)
    bgr = rng.integers(100, 160, (h, w, 3), dtype=np.uint8)
    # Heavily smooth (matte paper) — Gaussian blur reduces variance
    import cv2
    bgr = cv2.GaussianBlur(bgr, (9, 9), 3)
    # Desaturate
    gray_val = bgr.mean(axis=2, keepdims=True).astype(np.uint8)
    bgr = np.concatenate([gray_val] * 3, axis=2)
    gray = cv2_gray(bgr)
    return bgr, gray


def synthetic_screen(h: int = 120, w: int = 100) -> tuple[np.ndarray, np.ndarray]:
    """Simulate an LCD screen: regular sub-pixel grid pattern + high brightness."""
    bgr = np.zeros((h, w, 3), dtype=np.uint8)
    bgr[:, :, :] = 180  # base brightness
    # Sub-pixel grid: every 3 cols slightly brighter in one channel
    bgr[:, ::3, 2] = 220   # red sub-pixel column
    bgr[:, 1::3, 1] = 220  # green
    bgr[:, 2::3, 0] = 220  # blue
    # Horizontal scan-line artifact
    bgr[::2, :, :] = (bgr[::2, :, :].astype(int) * 9 // 10).astype(np.uint8)
    gray = cv2_gray(bgr)
    return bgr, gray


def cv2_gray(bgr: np.ndarray) -> np.ndarray:
    import cv2
    return cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _make_full_frame(roi_bgr: np.ndarray) -> tuple[np.ndarray, np.ndarray, tuple]:
    h, w = roi_bgr.shape[:2]
    frame = np.zeros((h * 2, w * 2, 3), dtype=np.uint8)
    frame[h // 2:h // 2 + h, w // 2:w // 2 + w] = roi_bgr
    import cv2
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    face = (w // 2, h // 2, w, h)
    return frame, gray, face


def _make_cfg(enabled: bool = True) -> AppConfig:
    cfg = AppConfig()
    object.__setattr__(cfg, "liveness_enabled", enabled)
    return cfg


# ─── Tests ────────────────────────────────────────────────────────────────────

class TestFeatureFlag:
    def test_disabled_returns_disabled_zone(self):
        cfg = _make_cfg(enabled=False)
        det = LivenessDetector(cfg)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = det.evaluate(frame, gray, face, seq=1)
        assert v.zone == LivenessZone.DISABLED
        assert v.score == 1.0

    def test_disabled_push_is_noop(self):
        cfg = _make_cfg(enabled=False)
        det = LivenessDetector(cfg)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        det.push_frame(frame, gray, face, seq=1)
        assert len(det._buf) == 0


class TestPassiveStubs:
    """F0 stubs return 0.5 — only interface and dataclass structure are tested."""

    def setup_method(self):
        self.cfg = _make_cfg(enabled=True)
        self.det = LivenessDetector(self.cfg)

    def test_passive_score_fields_present(self):
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        verdict = self.det.evaluate(frame, gray, face, seq=1)
        assert verdict.passive is not None
        p = verdict.passive
        assert 0.0 <= p.fft <= 1.0
        assert 0.0 <= p.laplacian <= 1.0
        assert 0.0 <= p.hsv <= 1.0
        assert 0.0 <= p.score <= 1.0

    def test_verdict_zone_is_valid(self):
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = self.det.evaluate(frame, gray, face, seq=1)
        assert v.zone in (LivenessZone.LIVE, LivenessZone.GRAY, LivenessZone.SPOOF)

    def test_empty_roi_does_not_crash(self):
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        import cv2
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face = (0, 0, 0, 0)  # zero-size bbox
        v = self.det.evaluate(frame, gray, face, seq=1)
        assert v.passive is not None


class TestFusionLogic:
    """Fusion math is testable even with stub metrics."""

    def _make_det_with_thresholds(self, t_live: float, t_spoof: float,
                                   w_passive: float = 0.5, w_motion: float = 0.5):
        cfg = _make_cfg(enabled=True)
        object.__setattr__(cfg, "liveness_t_live", t_live)
        object.__setattr__(cfg, "liveness_t_spoof", t_spoof)
        object.__setattr__(cfg, "liveness_w_passive", w_passive)
        object.__setattr__(cfg, "liveness_w_motion", w_motion)
        return LivenessDetector(cfg)

    def test_score_live_when_above_t_live(self):
        # Push stubs to return 1.0 by setting t_live very low
        det = self._make_det_with_thresholds(t_live=0.0, t_spoof=-1.0)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = det.evaluate(frame, gray, face, seq=1)
        assert v.zone == LivenessZone.LIVE

    def test_score_spoof_when_below_t_spoof(self):
        # Push stubs to return 0.5; set t_spoof above 0.5 to force SPOOF
        det = self._make_det_with_thresholds(t_live=1.1, t_spoof=1.0)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = det.evaluate(frame, gray, face, seq=1)
        assert v.zone == LivenessZone.SPOOF

    def test_score_gray_when_between_thresholds(self):
        # Stubs return 0.5; set t_spoof=0.3, t_live=0.7 → gray zone
        det = self._make_det_with_thresholds(t_live=0.70, t_spoof=0.30)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = det.evaluate(frame, gray, face, seq=1)
        assert v.zone == LivenessZone.GRAY

    def test_fused_score_is_weighted_average(self):
        det = self._make_det_with_thresholds(t_live=2.0, t_spoof=-1.0,
                                              w_passive=0.6, w_motion=0.4)
        frame, gray, face = _make_full_frame(synthetic_live()[0])
        v = det.evaluate(frame, gray, face, seq=1)
        # Both stubs return 0.5 → fused = 0.5 regardless of weights
        assert abs(v.score - 0.5) < 1e-6
