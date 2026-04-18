"""Tests for Layer 3 (active challenge) FSM.

F0: token issuance, expiry, and FSM interface.
F4 will add real cascade-driven feed() assertions.
"""

import time
from typing import List, Optional

import numpy as np
import pytest

from config import AppConfig
from vision.liveness import ChallengeResult, LivenessDetector


def _make_cfg(pool: Optional[List[str]] = None, timeout_ms: int = 5000) -> AppConfig:
    cfg = AppConfig()
    object.__setattr__(cfg, "liveness_enabled", True)
    object.__setattr__(cfg, "liveness_challenge_pool",
                       pool if pool is not None else ["blink", "smile"])
    object.__setattr__(cfg, "liveness_challenge_timeout_ms", timeout_ms)
    object.__setattr__(cfg, "secret_key", "test-secret-key-32chars-xxxxxxxx")
    return cfg


def _blank() -> tuple[np.ndarray, np.ndarray, tuple]:
    import cv2
    bgr = np.zeros((80, 80, 3), dtype=np.uint8)
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    return bgr, gray, (10, 10, 40, 40)


class TestTokenLifecycle:
    def setup_method(self):
        self.det = LivenessDetector(_make_cfg())

    def test_start_challenge_returns_string(self):
        token = self.det.start_challenge()
        assert isinstance(token, str)
        assert len(token) > 16

    def test_explicit_kind_is_respected(self):
        token = self.det.start_challenge(kind="smile")
        with self.det._challenge_lock:
            state = self.det._challenges.get(token)
        assert state is not None
        assert state.kind == "smile"

    def test_unknown_token_returns_not_found(self):
        result = self.det.resolve_challenge("nonexistent_token")
        assert result.verified is False
        assert result.reason == "token_not_found"

    def test_resolve_clears_token(self):
        token = self.det.start_challenge(kind="blink")
        self.det.resolve_challenge(token)
        result = self.det.resolve_challenge(token)
        assert result.reason == "token_not_found"

    def test_expired_challenge_returns_timeout(self):
        det = LivenessDetector(_make_cfg(timeout_ms=1))  # 1 ms TTL
        token = det.start_challenge(kind="smile")
        time.sleep(0.05)  # 50 ms — well past TTL
        bgr, gray, face = _blank()
        det.update_challenge(token, bgr, gray, face)  # should trigger expiry
        result = det.resolve_challenge(token)
        assert result.verified is False
        assert result.reason in ("timeout", "failed")

    def test_empty_pool_raises(self):
        det = LivenessDetector(_make_cfg(pool=[]))
        with pytest.raises(RuntimeError, match="pool is empty"):
            det.start_challenge()

    def test_update_unknown_token_returns_false(self):
        bgr, gray, face = _blank()
        result = self.det.update_challenge("bogus_token", bgr, gray, face)
        assert result is False


class TestChallengeResult:
    def test_result_is_dataclass(self):
        r = ChallengeResult(verified=True, kind="blink", elapsed_ms=1200)
        assert r.verified is True
        assert r.kind == "blink"
        assert r.elapsed_ms == 1200
        assert r.reason == ""
