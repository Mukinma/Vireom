import logging
import sys
import threading
import time
from typing import Optional

import cv2
import numpy as np

from config import config

logger = logging.getLogger("camerapi.camera")

try:
    from picamera2 import Picamera2

    _HAS_PICAMERA2 = True
except ImportError:
    _HAS_PICAMERA2 = False


class CameraStream:
    STALE_FRAME_SECONDS = 3.0

    def __init__(self):
        self.lock = threading.Lock()
        self.frame_cond = threading.Condition(self.lock)
        self.frame = None
        self.jpeg_frame: Optional[bytes] = None
        self.stream_frame_content_type = "image/jpeg"
        self.frame_seq = 0
        self.stream_frame_seq = 0
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.started_at = 0.0
        self.last_frame_time = 0.0
        self.retry_delay_sec = 2.0
        self.max_open_retries = 5
        self.capture_fps = 0.0
        self._fps_tick_perf = time.perf_counter()
        self._fps_counter = 0
        self._jpeg_clients = 0
        self._last_stream_encode_perf = 0.0
        self.restart_count = 0
        self._capture_generation = 0

        self._use_picamera2 = _HAS_PICAMERA2 and sys.platform == "linux"

        # OpenCV backend
        self.cap: Optional[cv2.VideoCapture] = None

        # Picamera2 backend
        self._picam: Optional["Picamera2"] = None
        self._picam_started = False

        if self._use_picamera2:
            logger.info("camera_backend=picamera2")
        else:
            logger.info("camera_backend=opencv")

    # ── Picamera2 backend ────────────────────────────────────────────

    @staticmethod
    def _target_frame_duration_us() -> int:
        return int(round(1_000_000 / float(max(1, config.max_fps))))

    def _configure_picamera2_controls(self, picam: "Picamera2") -> None:
        target_fps = float(max(1, config.max_fps))
        frame_duration_us = self._target_frame_duration_us()
        controls = (
            {"FrameDurationLimits": (frame_duration_us, frame_duration_us)},
            {"FrameRate": target_fps},
        )
        for control in controls:
            try:
                picam.set_controls(control)
            except Exception:
                key = next(iter(control.keys()))
                logger.debug("picamera2_control_unsupported control=%s", key)

    def _open_picamera2(self) -> bool:
        for attempt in range(1, self.max_open_retries + 1):
            try:
                self._release_picamera2()
                picam = Picamera2()
                video_cfg = picam.create_video_configuration(
                    main={
                        "format": "BGR888",
                        "size": (config.frame_width, config.frame_height),
                    },
                )
                picam.configure(video_cfg)
                picam.start()
                self._configure_picamera2_controls(picam)
                time.sleep(0.5)
                self._picam = picam
                self._picam_started = True
                logger.info(
                    "picamera2_open_ok attempt=%s size=%sx%s fps=%s",
                    attempt,
                    config.frame_width,
                    config.frame_height,
                    config.max_fps,
                )
                return True
            except Exception:
                logger.exception("picamera2_open_failed attempt=%s", attempt)
                time.sleep(self.retry_delay_sec)
        return False

    def _release_picamera2(self) -> None:
        if self._picam is not None:
            try:
                if self._picam_started:
                    self._picam.stop()
                self._picam.close()
            except Exception:
                logger.exception("picamera2_release_failed")
        self._picam = None
        self._picam_started = False

    def _read_picamera2(self):
        if self._picam is None:
            return False, None
        try:
            frame = self._picam.capture_array("main")
            if frame is None or frame.size == 0:
                return False, None
            # Picamera2 puede reutilizar el buffer del request; trabajamos sobre una
            # copia contigua para evitar artefactos visuales durante el encode/render.
            frame = np.ascontiguousarray(frame.copy())
            if len(frame.shape) == 3:
                if frame.shape[2] == 4:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
            return True, frame
        except Exception:
            logger.exception("picamera2_capture_failed")
            return False, None

    # ── OpenCV backend ───────────────────────────────────────────────

    def _preferred_backends(self) -> list[tuple[str, Optional[int]]]:
        if sys.platform == "darwin" and hasattr(cv2, "CAP_AVFOUNDATION"):
            return [("AVFOUNDATION", int(cv2.CAP_AVFOUNDATION)), ("DEFAULT", None)]
        return [("DEFAULT", None)]

    def _configure_capture(self, cap: cv2.VideoCapture) -> None:
        if hasattr(cv2, "CAP_PROP_FOURCC"):
            try:
                cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
            except Exception:
                logger.debug("camera_fourcc_mjpg_unsupported")
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.frame_width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.frame_height)
        cap.set(cv2.CAP_PROP_FPS, config.max_fps)
        if hasattr(cv2, "CAP_PROP_BUFFERSIZE"):
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, config.camera_buffer_size)
            except Exception:
                logger.debug("camera_buffer_size_unsupported")

    def _open_single(self, backend: Optional[int]) -> Optional[cv2.VideoCapture]:
        if backend is None:
            cap = cv2.VideoCapture(config.camera_index)
        else:
            cap = cv2.VideoCapture(config.camera_index, backend)
        self._configure_capture(cap)
        return cap

    def _open_opencv(self) -> bool:
        for attempt in range(1, self.max_open_retries + 1):
            for backend_name, backend in self._preferred_backends():
                cap: Optional[cv2.VideoCapture] = None
                try:
                    cap = self._open_single(backend)
                    if cap.isOpened():
                        self._release_opencv()
                        self.cap = cap
                        logger.info(
                            "camera_open_ok attempt=%s index=%s backend=%s",
                            attempt,
                            config.camera_index,
                            backend_name,
                        )
                        return True
                except Exception:
                    logger.exception(
                        "camera_open_exception attempt=%s backend=%s",
                        attempt,
                        backend_name,
                    )
                finally:
                    if cap is not None and self.cap is not cap:
                        try:
                            cap.release()
                        except Exception:
                            logger.debug("camera_open_temp_release_failed")
            logger.error(
                "camera_open_failed attempt=%s retry_in=%ss",
                attempt,
                self.retry_delay_sec,
            )
            time.sleep(self.retry_delay_sec)
        return False

    def _release_opencv(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                logger.exception("camera_release_failed")
        self.cap = None

    # ── Unified interface ────────────────────────────────────────────

    def _open_camera(self) -> bool:
        if self._use_picamera2:
            return self._open_picamera2()
        return self._open_opencv()

    def _release_capture(self) -> None:
        if self._use_picamera2:
            self._release_picamera2()
        else:
            self._release_opencv()

    def _camera_lost(self) -> bool:
        if self._use_picamera2:
            return self._picam is None or not self._picam_started
        return self.cap is None or not self.cap.isOpened()

    def _read_frame(self):
        if self._use_picamera2:
            return self._read_picamera2()
        if self.cap is not None:
            return self.cap.read()
        return False, None

    def _encode_stream_frame(self, frame) -> Optional[bytes]:
        try:
            if frame is None or len(frame.shape) != 3 or frame.shape[2] < 3:
                return None
            bgr = frame[:, :, :3]
            if bgr.dtype != np.uint8:
                bgr = bgr.astype(np.uint8, copy=False)

            encoded_ok, encoded = cv2.imencode(
                ".jpg",
                bgr,
                [cv2.IMWRITE_JPEG_QUALITY, config.camera_jpeg_quality],
            )
            if encoded_ok:
                return encoded.tobytes()
        except Exception:
            logger.exception("camera_stream_frame_encode_failed")
        return None

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        thread_alive = self.thread is not None and self.thread.is_alive()
        if self.running and thread_alive:
            return
        if self.running and not thread_alive:
            self.stop(reset_clients=False)

        with self.frame_cond:
            self.frame = None
            self.jpeg_frame = None
            self.last_frame_time = 0.0
            self.capture_fps = 0.0
            self._fps_tick_perf = time.perf_counter()
            self._fps_counter = 0
            self.frame_cond.notify_all()

        if not self._open_camera():
            raise RuntimeError("No se pudo inicializar la cámara")
        with self.lock:
            self.running = True
            self.started_at = time.time()
            self._capture_generation += 1
            generation = self._capture_generation
        self.thread = threading.Thread(target=self._capture_loop, args=(generation,), daemon=True)
        self.thread.start()

    def _capture_loop(self, generation: int) -> None:
        min_interval = 1.0 / max(1, config.max_fps)
        stream_interval = 1.0 / max(1, min(config.max_fps, config.stream_fps))
        next_tick = time.perf_counter()
        while self.running and generation == self._capture_generation:
            now_perf = time.perf_counter()
            sleep_s = next_tick - now_perf
            if sleep_s > 0:
                time.sleep(sleep_s)
                continue
            next_tick = now_perf + min_interval

            if self._camera_lost():
                logger.error("camera_stream_lost reopening=true")
                if not self._open_camera():
                    time.sleep(self.retry_delay_sec)
                    next_tick = time.perf_counter() + min_interval
                    continue

            ok, raw = self._read_frame()
            if ok:
                with self.lock:
                    encode_jpeg = self._jpeg_clients > 0
                    last_stream_encode_perf = self._last_stream_encode_perf

                frame_tick_perf = time.perf_counter()
                should_encode_stream = (
                    encode_jpeg
                    and (
                        last_stream_encode_perf <= 0.0
                        or frame_tick_perf - last_stream_encode_perf >= stream_interval
                    )
                )
                jpeg = self._encode_stream_frame(raw) if should_encode_stream else None
                with self.frame_cond:
                    self.frame = raw.copy()
                    self.frame_seq += 1
                    if jpeg is not None:
                        self.jpeg_frame = jpeg
                        self.stream_frame_seq += 1
                        self._last_stream_encode_perf = frame_tick_perf
                    elif not encode_jpeg:
                        self.jpeg_frame = None
                    self.last_frame_time = time.time()
                    self._fps_counter += 1
                    elapsed = frame_tick_perf - self._fps_tick_perf
                    if elapsed >= 1.0:
                        self.capture_fps = self._fps_counter / elapsed
                        self._fps_counter = 0
                        self._fps_tick_perf = frame_tick_perf
                    self.frame_cond.notify_all()
            else:
                logger.error("camera_frame_read_failed")
                self._release_capture()
                time.sleep(self.retry_delay_sec)
                next_tick = time.perf_counter() + min_interval

    def get_frame(self, copy: bool = True):
        with self.lock:
            if self.frame is None:
                return None
            return self.frame.copy() if copy else self.frame

    def get_capture_fps(self) -> float:
        with self.lock:
            return float(self.capture_fps)

    def register_jpeg_client(self) -> None:
        with self.lock:
            self._jpeg_clients += 1

    def unregister_jpeg_client(self) -> None:
        with self.lock:
            self._jpeg_clients = max(0, self._jpeg_clients - 1)

    def get_frame_seq(self) -> int:
        with self.lock:
            return int(self.frame_seq)

    def get_stream_frame_seq(self) -> int:
        with self.lock:
            return int(self.stream_frame_seq)

    def get_stream_content_type(self) -> str:
        return self.stream_frame_content_type

    def get_snapshot_frame(self) -> tuple[Optional[bytes], str]:
        frame = self.get_frame(copy=True)
        if frame is None:
            return None, self.stream_frame_content_type
        return self._encode_stream_frame(frame), self.stream_frame_content_type

    def get_jpeg(self, last_seq: int = 0, timeout: float = 0.5) -> tuple[Optional[bytes], int]:
        deadline = time.monotonic() + max(0.0, timeout)
        with self.frame_cond:
            while self.running and self.stream_frame_seq <= last_seq:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self.frame_cond.wait(timeout=remaining)
            if self.stream_frame_seq <= last_seq or self.jpeg_frame is None:
                return None, last_seq
            return self.jpeg_frame, self.stream_frame_seq

    def stop(self, reset_clients: bool = True) -> None:
        with self.lock:
            self.running = False
            self._capture_generation += 1
        self._release_capture()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        with self.frame_cond:
            self.frame = None
            self.jpeg_frame = None
            self.last_frame_time = 0.0
            self.started_at = 0.0
            self.frame_cond.notify_all()
        with self.lock:
            self.capture_fps = 0.0
            self._fps_tick_perf = time.perf_counter()
            self._fps_counter = 0
            self._last_stream_encode_perf = 0.0
            if reset_clients:
                self._jpeg_clients = 0

    def is_stale(self, timeout_seconds: float = STALE_FRAME_SECONDS) -> bool:
        with self.lock:
            if not self.running:
                return False
            last_frame_time = float(self.last_frame_time or 0.0)
            started_at = float(self.started_at or 0.0)
        now = time.time()
        if last_frame_time <= 0.0:
            return started_at > 0.0 and (now - started_at) >= timeout_seconds
        return (now - last_frame_time) >= timeout_seconds

    def is_active(self) -> bool:
        recent = not self.is_stale(self.STALE_FRAME_SECONDS)
        thread_alive = self.thread is not None and self.thread.is_alive()
        cam_ok = not self._camera_lost()
        return bool(self.running and thread_alive and cam_ok and recent)

    def restart(self, reason: str = "unknown") -> bool:
        logger.warning("camera_restart_requested reason=%s", reason)
        self.stop(reset_clients=False)
        try:
            self.start()
            with self.lock:
                self.restart_count += 1
            logger.info("camera_restart_ok reason=%s", reason)
            return True
        except Exception:
            logger.exception("camera_restart_failed reason=%s", reason)
            return False

    def ensure_running(self) -> bool:
        if not self.running:
            return False
        if self.thread is None or not self.thread.is_alive():
            logger.critical("camera_capture_thread_dead restarting=true")
            return self.restart("thread_dead")
        if self._camera_lost():
            logger.critical("camera_device_lost restarting=true")
            return self.restart("device_lost")
        if self.is_stale(self.STALE_FRAME_SECONDS):
            logger.critical("camera_frame_stale restarting=true")
            return self.restart("frame_stale")
        return True
