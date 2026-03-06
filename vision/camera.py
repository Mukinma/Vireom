import threading
import time
import sys
from typing import Optional

import cv2
import logging

from config import config


logger = logging.getLogger("camerapi.camera")


class CameraStream:
    def __init__(self):
        self.cap: Optional[cv2.VideoCapture] = None
        self.lock = threading.Lock()
        self.frame = None
        self.running = False
        self.thread: Optional[threading.Thread] = None
        self.last_frame_time = 0.0
        self.retry_delay_sec = 2.0
        self.max_open_retries = 5

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

    def _release_capture(self) -> None:
        if self.cap is not None:
            try:
                self.cap.release()
            except Exception:
                logger.exception("camera_release_failed")
        self.cap = None

    def _open_single(self, backend: Optional[int]) -> Optional[cv2.VideoCapture]:
        if backend is None:
            cap = cv2.VideoCapture(config.camera_index)
        else:
            cap = cv2.VideoCapture(config.camera_index, backend)
        self._configure_capture(cap)
        return cap

    def _open_camera(self) -> bool:
        for attempt in range(1, self.max_open_retries + 1):
            for backend_name, backend in self._preferred_backends():
                cap: Optional[cv2.VideoCapture] = None
                try:
                    cap = self._open_single(backend)
                    if cap.isOpened():
                        self._release_capture()
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
            logger.error("camera_open_failed attempt=%s retry_in=%ss", attempt, self.retry_delay_sec)
            time.sleep(self.retry_delay_sec)
        return False

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

            if self.cap is None or not self.cap.isOpened():
                logger.error("camera_stream_lost reopening=true")
                if not self._open_camera():
                    time.sleep(self.retry_delay_sec)
                    next_tick = time.perf_counter() + min_interval
                    continue
            ok, raw = self.cap.read() if self.cap is not None else (False, None)
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
        cap_ok = self.cap is not None and self.cap.isOpened()
        return bool(self.running and thread_alive and cap_ok and recent)

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
