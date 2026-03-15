import logging
import sys
import threading
import time
from typing import Optional

import cv2

from config import config

logger = logging.getLogger("camerapi.camera")

try:
    from picamera2 import Picamera2

    _HAS_PICAMERA2 = True
except ImportError:
    _HAS_PICAMERA2 = False


class CameraStream:
    def __init__(self):
        self.lock = threading.Lock()
        self.frame = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_frame_time = 0.0
        self.retry_delay_sec = 2.0
        self.max_open_retries = 5

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
                time.sleep(0.5)
                self._picam = picam
                self._picam_started = True
                logger.info(
                    "picamera2_open_ok attempt=%s size=%sx%s",
                    attempt,
                    config.frame_width,
                    config.frame_height,
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
            frame = self._picam.capture_array()
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

    # ── Lifecycle ────────────────────────────────────────────────────

    def start(self) -> None:
        if self.running:
            return
        if not self._open_camera():
            raise RuntimeError("No se pudo inicializar la cámara")
        self.running = True
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()

    def _capture_loop(self) -> None:
        min_interval = 1.0 / max(1, config.max_fps)
        next_tick = time.perf_counter()
        while self.running:
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
                    self.frame = raw
                    self.last_frame_time = time.time()
            else:
                logger.error("camera_frame_read_failed")
                self._release_capture()
                time.sleep(self.retry_delay_sec)
                next_tick = time.perf_counter() + min_interval

    def get_frame(self):
        with self.lock:
            return None if self.frame is None else self.frame.copy()

    def get_jpeg(self) -> Optional[bytes]:
        frame = self.get_frame()
        if frame is None:
            return None
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else None

    def stop(self) -> None:
        self.running = False
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=1.0)
        self._release_capture()
        with self.lock:
            self.frame = None

    def is_active(self) -> bool:
        recent = (time.time() - self.last_frame_time) < 3.0
        thread_alive = self.thread is not None and self.thread.is_alive()
        cam_ok = not self._camera_lost()
        return bool(self.running and thread_alive and cam_ok and recent)

    def ensure_running(self) -> bool:
        if not self.running:
            return False
        if self.thread is None or not self.thread.is_alive():
            logger.critical("camera_capture_thread_dead restarting=true")
            try:
                self.thread = threading.Thread(target=self._capture_loop, daemon=True)
                self.thread.start()
                return True
            except Exception:
                logger.exception("camera_thread_restart_failed")
                return False
        return True
