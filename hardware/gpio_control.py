import threading
import time
import logging


try:
    import RPi.GPIO as GPIO  # type: ignore
except Exception:
    GPIO = None


logger = logging.getLogger("camerapi.gpio")


class RelayController:
    def __init__(self, pin: int = 18, active_high: bool = True):
        self.pin = pin
        self.active_high = active_high
        self.available = False
        self.initialized = False
        self.last_error = None
        if GPIO is not None:
            try:
                GPIO.setmode(GPIO.BCM)
                GPIO.setup(self.pin, GPIO.OUT)
                GPIO.output(self.pin, GPIO.LOW if active_high else GPIO.HIGH)
                self.available = True
                self.initialized = True
                logger.info("gpio_init_ok pin=%s", self.pin)
            except Exception as exc:
                self.available = False
                self.initialized = False
                self.last_error = str(exc)
                logger.exception("gpio_init_failed pin=%s", self.pin)
        else:
            logger.warning("gpio_module_unavailable mode=mock")

    def open_for(self, seconds: int) -> None:
        if not self.available:
            logger.error("gpio_open_skipped available=false")
            return
        threading.Thread(target=self._pulse, args=(seconds,), daemon=True).start()

    def _pulse(self, seconds: int) -> None:
        try:
            if self.active_high:
                GPIO.output(self.pin, GPIO.HIGH)
            else:
                GPIO.output(self.pin, GPIO.LOW)
            time.sleep(max(1, seconds))
            if self.active_high:
                GPIO.output(self.pin, GPIO.LOW)
            else:
                GPIO.output(self.pin, GPIO.HIGH)
            logger.info("gpio_pulse_ok duration=%s", seconds)
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("gpio_pulse_failed")

    def cleanup(self) -> None:
        if self.available:
            try:
                GPIO.cleanup()
                logger.info("gpio_cleanup_ok")
            except Exception:
                logger.exception("gpio_cleanup_failed")

    def is_healthy(self) -> bool:
        if GPIO is None:
            return False
        return bool(self.available and self.initialized)
