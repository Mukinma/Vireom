"""Liveness / anti-spoofing detector — classical computer vision only.

Three-layer architecture:
  Layer 1 (Passive)  — per-frame texture/frequency/color signatures.
  Layer 2 (Motion)   — multi-frame optical-flow affine residual + bbox variance.
  Layer 3 (Active)   — randomized challenge with secondary Haar cascades.

No neural networks, no deep learning.  Only numpy + cv2 (contrib 4.10).
"""

from __future__ import annotations

import collections
import hashlib
import hmac
import json
import logging
import random
import threading
import time
from dataclasses import dataclass, field
from typing import Optional

import cv2
import numpy as np

from config import AppConfig

logger = logging.getLogger("camerapi.liveness")


# ─── Result types ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class PassiveScore:
    fft: float          # [0,1] — high-freq energy ratio
    laplacian: float    # [0,1] — micro-texture variance
    hsv: float          # [0,1] — skin-tone histogram plausibility
    score: float        # weighted combination
    method: str = "passive"


@dataclass(frozen=True)
class MotionScore:
    affine_residual: float  # [0,1] — non-rigid motion (parallax indicator)
    bbox_variance: float    # [0,1] — natural micro-movement of head
    score: float
    frames_used: int
    method: str = "motion"


class LivenessZone:
    LIVE = "live"
    GRAY = "gray"
    SPOOF = "spoof"
    DISABLED = "disabled"


@dataclass
class Verdict:
    score: float            # fused [0,1]; higher = more live
    zone: str               # LivenessZone constant
    passive: Optional[PassiveScore] = None
    motion: Optional[MotionScore] = None
    method: str = "fused"
    challenge_kind: Optional[str] = None


@dataclass
class ChallengeResult:
    verified: bool
    kind: str
    elapsed_ms: int
    reason: str = ""


# ─── Frame buffer entry ───────────────────────────────────────────────────────

@dataclass
class _FrameEntry:
    frame: np.ndarray   # BGR
    gray: np.ndarray
    face: tuple[int, int, int, int]   # x,y,w,h
    seq: int
    ts: float = field(default_factory=time.monotonic)


# ─── Liveness detector ────────────────────────────────────────────────────────

class LivenessDetector:
    """Main liveness detector.  Thread-safe for concurrent push + evaluate."""

    def __init__(self, config: AppConfig) -> None:
        self._cfg = config
        self._enabled = config.liveness_enabled
        self._buf: collections.deque[_FrameEntry] = collections.deque(
            maxlen=config.liveness_buffer_size
        )
        self._lock = threading.Lock()

        # Secondary cascades (Layer 3 challenges)
        self._eye_cascade: Optional[cv2.CascadeClassifier] = None
        self._smile_cascade: Optional[cv2.CascadeClassifier] = None
        self._profile_cascade: Optional[cv2.CascadeClassifier] = None

        # Active challenges
        self._challenges: dict[str, "_ChallengeState"] = {}
        self._challenge_lock = threading.Lock()

        if self._enabled:
            self._load_cascades()
            logger.info("LivenessDetector enabled (buffer=%d, T_live=%.2f, T_spoof=%.2f)",
                        config.liveness_buffer_size, config.liveness_t_live, config.liveness_t_spoof)
        else:
            logger.info("LivenessDetector disabled (CAMERAPI_LIVENESS_ENABLED=0)")

    # ── Public API ────────────────────────────────────────────────────────────

    def push_frame(self, frame: np.ndarray, gray: np.ndarray,
                   face: tuple[int, int, int, int], seq: int) -> None:
        """Feed a new frame into the temporal buffer.

        Called from _process_loop — no recognition is triggered here.
        """
        if not self._enabled:
            return
        entry = _FrameEntry(frame=frame.copy(), gray=gray.copy(), face=face, seq=seq)
        with self._lock:
            self._buf.append(entry)

    def evaluate(self, frame: np.ndarray, gray: np.ndarray,
                 face: tuple[int, int, int, int], seq: int) -> Verdict:
        """Full liveness evaluation called from analyze_once (Layer 1 + 2 fusion).

        Returns DISABLED verdict when feature flag is off — caller proceeds normally.
        """
        if not self._enabled:
            return Verdict(score=1.0, zone=LivenessZone.DISABLED)

        passive = self._check_passive(frame, gray, face)
        with self._lock:
            buf_snapshot = list(self._buf)
        motion = self._check_motion(buf_snapshot, face)

        return self._fuse(passive, motion)

    def start_challenge(self, kind: Optional[str] = None) -> str:
        """Issue a randomized challenge token.  Returns a signed hex token string."""
        if not self._cfg.liveness_challenge_pool:
            raise RuntimeError("Challenge pool is empty")
        chosen = kind or random.choice(self._cfg.liveness_challenge_pool)
        state = _ChallengeState(
            kind=chosen,
            timeout_ms=self._cfg.liveness_challenge_timeout_ms,
            cascade=self._cascade_for(chosen),
        )
        token = self._sign_token({"kind": chosen, "ts": time.monotonic()})
        with self._challenge_lock:
            # Expire old challenges first
            now = time.monotonic()
            self._challenges = {
                t: s for t, s in self._challenges.items()
                if not s.is_expired(now)
            }
            self._challenges[token] = state
        logger.debug("Challenge started: kind=%s token=%.8s", chosen, token)
        return token

    def update_challenge(self, token: str, frame: np.ndarray,
                         gray: np.ndarray, face: tuple[int, int, int, int]) -> bool:
        """Feed a frame to an in-progress challenge.  Returns True when resolved."""
        with self._challenge_lock:
            state = self._challenges.get(token)
        if state is None or state.is_expired():
            return False
        resolved = state.feed(frame, gray, face)
        if resolved:
            logger.debug("Challenge resolved: kind=%s token=%.8s verified=%s",
                         state.kind, token, state.verified)
        return resolved

    def resolve_challenge(self, token: str) -> ChallengeResult:
        """Get the outcome of a completed or timed-out challenge."""
        with self._challenge_lock:
            state = self._challenges.pop(token, None)
        if state is None:
            return ChallengeResult(verified=False, kind="unknown",
                                   elapsed_ms=0, reason="token_not_found")
        elapsed = int((time.monotonic() - state.start_ts) * 1000)
        if state.is_expired() and not state.resolved:
            return ChallengeResult(verified=False, kind=state.kind,
                                   elapsed_ms=elapsed, reason="timeout")
        return ChallengeResult(verified=state.verified, kind=state.kind,
                               elapsed_ms=elapsed,
                               reason="success" if state.verified else "failed")

    # ── Layer 1 — Passive ─────────────────────────────────────────────────────

    def _check_passive(self, frame: np.ndarray, gray: np.ndarray,
                       face: tuple[int, int, int, int]) -> PassiveScore:
        x, y, w, h = face
        roi_gray = gray[y:y + h, x:x + w]
        roi_bgr  = frame[y:y + h, x:x + w]

        if roi_gray.size == 0:
            return PassiveScore(fft=0.5, laplacian=0.5, hsv=0.5, score=0.5)

        s_fft = self._fft_highfreq_ratio(roi_gray)
        s_lap = self._laplacian_variance_score(roi_gray)
        s_hsv = self._hsv_cheek_score(roi_bgr)

        w1 = w2 = w3 = 1.0 / 3.0
        score = w1 * s_fft + w2 * s_lap + w3 * s_hsv

        return PassiveScore(fft=s_fft, laplacian=s_lap, hsv=s_hsv, score=score)

    def _fft_highfreq_ratio(self, roi_gray: np.ndarray) -> float:
        """High-frequency energy ratio via 2D DFT.

        LCD screens have a regular sub-pixel pitch → strong harmonic at
        predictable spatial frequencies.  Printed photos have halftone
        patterns.  Live skin has broadband, non-periodic texture.

        Returns a score in [0,1] where higher = more live-like.
        Stub: always returns 0.5 until F1 calibration.
        """
        # TODO(F1): implement FFT band energy ratio with calibrated thresholds
        return 0.5

    def _laplacian_variance_score(self, roi_gray: np.ndarray) -> float:
        """Micro-texture variance via Laplacian.

        Printed photos (matte): low variance (smooth surface).
        Live skin: intermediate variance with non-regular texture.
        Screens: high variance but quantized (block pattern).

        Returns [0,1] where higher = more live-like.
        Stub: always returns 0.5 until F1 calibration.
        """
        # TODO(F1): implement with calibrated min/max variance range
        return 0.5

    def _hsv_cheek_score(self, roi_bgr: np.ndarray) -> float:
        """Skin-tone histogram plausibility in HSV cheek sub-regions.

        Live skin: H in [0,25]∪[340,360], S in [30,90], V moderate.
        Printed photo: low S (grey/matte).
        Screen: high V + possible H shift from backlight.

        Returns [0,1] where higher = more live-like.
        Stub: always returns 0.5 until F1 calibration.
        """
        # TODO(F1): implement with calibrated HSV histogram bins
        return 0.5

    # ── Layer 2 — Motion ─────────────────────────────────────────────────────

    def _check_motion(self, buf: list[_FrameEntry],
                      face: tuple[int, int, int, int]) -> MotionScore:
        """Temporal analysis over buffer snapshot.

        Stub: returns neutral (0.5) until F2 implementation.
        """
        if len(buf) < 4:
            return MotionScore(affine_residual=0.5, bbox_variance=0.5,
                               score=0.5, frames_used=len(buf))

        # TODO(F2): implement Shi-Tomasi + Lucas-Kanade + affine residual
        # TODO(F2): implement bbox w/h variance over buffer
        return MotionScore(affine_residual=0.5, bbox_variance=0.5,
                           score=0.5, frames_used=len(buf))

    # ── Fusion ────────────────────────────────────────────────────────────────

    def _fuse(self, passive: PassiveScore, motion: MotionScore) -> Verdict:
        wp = self._cfg.liveness_w_passive
        wm = self._cfg.liveness_w_motion
        total = wp + wm
        score = (wp * passive.score + wm * motion.score) / (total or 1.0)

        if score >= self._cfg.liveness_t_live:
            zone = LivenessZone.LIVE
        elif score <= self._cfg.liveness_t_spoof:
            zone = LivenessZone.SPOOF
        else:
            zone = LivenessZone.GRAY
            logger.debug("Liveness gray zone (score=%.3f) — challenge required", score)

        challenge_kind = None
        if zone == LivenessZone.GRAY and self._cfg.liveness_challenge_pool:
            challenge_kind = random.choice(self._cfg.liveness_challenge_pool)

        return Verdict(score=score, zone=zone,
                       passive=passive, motion=motion,
                       challenge_kind=challenge_kind)

    # ── Layer 3 — Challenge helpers ───────────────────────────────────────────

    def _load_cascades(self) -> None:
        base = cv2.data.haarcascades
        cascades = {
            "blink": ("haarcascade_eye.xml", "_eye_cascade"),
            "smile": ("haarcascade_smile.xml", "_smile_cascade"),
            "turn":  ("haarcascade_profileface.xml", "_profile_cascade"),
        }
        for kind, (filename, attr) in cascades.items():
            path = base + filename
            clf = cv2.CascadeClassifier(path)
            if clf.empty():
                logger.warning("Could not load cascade for '%s': %s", kind, path)
            else:
                setattr(self, attr, clf)

    def _cascade_for(self, kind: str) -> Optional[cv2.CascadeClassifier]:
        mapping = {"blink": self._eye_cascade,
                   "smile": self._smile_cascade,
                   "turn": self._profile_cascade}
        return mapping.get(kind)

    def _sign_token(self, payload: dict) -> str:
        secret = self._cfg.secret_key.encode() or b"vireom-liveness"
        msg = json.dumps(payload, sort_keys=True).encode()
        digest = hmac.new(secret, msg, hashlib.sha256).hexdigest()
        ts_hex = format(int(time.monotonic() * 1000), "016x")
        return f"{ts_hex}{digest}"


# ─── Challenge FSM ────────────────────────────────────────────────────────────

class _ChallengeState:
    """Per-token FSM that accumulates frame evidence for a single challenge."""

    def __init__(self, kind: str, timeout_ms: int,
                 cascade: Optional[cv2.CascadeClassifier]) -> None:
        self.kind = kind
        self.timeout_ms = timeout_ms
        self.cascade = cascade
        self.start_ts = time.monotonic()
        self.resolved = False
        self.verified = False
        self._history: list[bool] = []

    def is_expired(self, now: Optional[float] = None) -> bool:
        t = now or time.monotonic()
        return (t - self.start_ts) * 1000 > self.timeout_ms

    def feed(self, frame: np.ndarray, gray: np.ndarray,
             face: tuple[int, int, int, int]) -> bool:
        """Returns True when the challenge is resolved (pass or fail)."""
        if self.resolved or self.is_expired():
            self.resolved = True
            return True

        detected = self._detect(gray, face)
        self._history.append(detected)

        if self.kind == "blink":
            self.verified, self.resolved = self._eval_blink()
        elif self.kind == "smile":
            self.verified, self.resolved = self._eval_smile()
        elif self.kind == "turn":
            self.verified, self.resolved = self._eval_turn()

        return self.resolved

    def _detect(self, gray: np.ndarray, face: tuple[int, int, int, int]) -> bool:
        if self.cascade is None or self.cascade.empty():
            return False
        x, y, w, h = face
        if self.kind == "blink":
            roi = gray[y:y + h // 2, x:x + w]
        elif self.kind == "smile":
            roi = gray[y + h // 2:y + h, x:x + w]
        else:
            roi = gray[y:y + h, x:x + w]
        hits = self.cascade.detectMultiScale(roi, scaleFactor=1.1, minNeighbors=4)
        return len(hits) > 0

    def _eval_blink(self) -> tuple[bool, bool]:
        """Two open→closed transitions within the history."""
        transitions = sum(
            1 for i in range(1, len(self._history))
            if self._history[i - 1] and not self._history[i]
        )
        if transitions >= 2:
            return True, True
        if self.is_expired():
            return False, True
        return False, False

    def _eval_smile(self) -> tuple[bool, bool]:
        """Smile detected in ≥3 consecutive frames."""
        consecutive = 0
        best = 0
        for v in self._history:
            consecutive = consecutive + 1 if v else 0
            best = max(best, consecutive)
        if best >= 3:
            return True, True
        if self.is_expired():
            return False, True
        return False, False

    def _eval_turn(self) -> tuple[bool, bool]:
        """Profile detected at least once (head turned left/right)."""
        if any(self._history):
            return True, True
        if self.is_expired():
            return False, True
        return False, False
