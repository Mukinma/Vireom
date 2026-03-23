from fastapi import FastAPI
from fastapi.templating import Jinja2Templates
from fastapi.testclient import TestClient
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.sessions import SessionMiddleware

import api.routes as routes_module
from api.routes import router
from rate_limit import limiter


class _DummyCamera:
    def get_jpeg(self, last_seq=0, timeout=0.5):
        return b"jpeg-bytes", int(last_seq) + 1


class _DummyService:
    def __init__(self):
        self.camera = _DummyCamera()
        self.running = True

    def analyze_once(self):
        return {"ok": True, "event": "authorized", "result": "AUTORIZADO"}, 200

    def get_status(self):
        return {
            "status": "ok",
            "camera": "online",
            "model": "loaded",
            "face_detected": False,
            "face_bbox": None,
            "analysis_busy": False,
            "face_guidance": {
                "state": "idle",
                "message": "Coloca tu rostro dentro de la guía",
                "is_aligned": False,
                "is_stable": False,
                "ready": False,
                "faces_count": 0,
                "offset_x": 0.0,
                "offset_y": 0.0,
                "scale_ratio": 0.0,
                "stability_score": 0.0,
                "steady_ms": 0,
            },
        }

    def health_liveness(self):
        return {"healthy": True}

    def health_detail(self):
        return {
            "healthy": True,
            "camera_active": True,
            "model_loaded": True,
            "db_accessible": True,
            "gpio_initialized": True,
            "metrics": {"fps": 10},
        }

    def simulate_access_attempt(self, is_valid, confidence=None):
        return {"result": "AUTORIZADO" if is_valid else "DENEGADO", "confidence": confidence}


def _build_app() -> FastAPI:
    app = FastAPI()
    app.state.templates = Jinja2Templates(directory="frontend/templates")
    app.state.service = _DummyService()
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)
    app.add_middleware(SessionMiddleware, secret_key="test-secret")
    app.include_router(router)
    return app


def _apply_test_config() -> None:
    routes_module.config.admin_user = "admin"
    routes_module.config.admin_password = "admin-pass"
    routes_module.config.debug = False


def _reset_limiter_state() -> None:
    storage = getattr(limiter, "_storage", None)
    if storage and hasattr(storage, "reset"):
        storage.reset()


def _build_client() -> TestClient:
    _apply_test_config()
    _reset_limiter_state()
    app = _build_app()
    return TestClient(app)


import pytest


@pytest.fixture()
def client():
    return _build_client()
