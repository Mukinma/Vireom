import hmac
import logging
import os
import signal
import threading
import time
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import config
from database.db import db
from rate_limit import limiter

router = APIRouter()
auth_logger = logging.getLogger("camerapi.auth")


def _is_admin(request: Request) -> bool:
    return bool(request.session.get("admin_authenticated"))


def _has_session(request: Request) -> bool:
    return bool(request.session.get("admin_authenticated") or request.session.get("kiosk"))


def _session_required(request: Request) -> None:
    if not _has_session(request):
        raise HTTPException(status_code=401, detail="No autorizado")


def _admin_required(request: Request) -> None:
    if not _is_admin(request):
        raise HTTPException(status_code=401, detail="No autorizado")


class ConfigUpdate(BaseModel):
    umbral_confianza: float = Field(ge=1, le=200)
    tiempo_apertura_seg: int = Field(ge=1, le=20)
    max_intentos: int = Field(ge=1, le=20)


class UserCreate(BaseModel):
    nombre: str = Field(min_length=2, max_length=80)


class UserStatusUpdate(BaseModel):
    activo: bool


class SimulateAccessPayload(BaseModel):
    is_valid: bool
    confidence: Optional[float] = None


@router.get("/", response_class=HTMLResponse)
def home(request: Request):
    request.session.setdefault("kiosk", True)
    return request.app.state.templates.TemplateResponse("index.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not _is_admin(request):
        has_error = request.query_params.get("error") == "1"
        return request.app.state.templates.TemplateResponse(
            "login.html",
            {"request": request, "login_error": has_error},
        )
    return request.app.state.templates.TemplateResponse("admin.html", {"request": request})


@router.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    admin_password = config.admin_password
    valid_user = hmac.compare_digest(username, config.admin_user)
    valid_password = bool(admin_password) and hmac.compare_digest(password, admin_password)
    if valid_user and valid_password:
        request.session["admin_authenticated"] = True
        return RedirectResponse(url="/admin", status_code=303)
    client_ip = request.client.host if request.client else "unknown"
    auth_logger.warning(
        "login_failed ip=%s username=%s timestamp=%s",
        client_ip,
        username,
        int(time.time()),
    )
    return RedirectResponse(url="/admin?error=1", status_code=303)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/api/stream")
def stream(request: Request):
    _session_required(request)
    service = request.app.state.service

    def generate():
        last_seq = 0
        register = getattr(service.camera, "register_jpeg_client", None)
        unregister = getattr(service.camera, "unregister_jpeg_client", None)
        if callable(register):
            register()
        try:
            while True:
                frame, last_seq = service.camera.get_jpeg(last_seq=last_seq, timeout=0.5)
                if frame is None:
                    if not service.running:
                        break
                    continue
                yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
        finally:
            if callable(unregister):
                unregister()

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/status")
def status(request: Request):
    return request.app.state.service.get_status()


@router.post("/api/recognize")
@limiter.limit("10/minute")
def recognize(request: Request):
    payload, status_code = request.app.state.service.analyze_once()
    return JSONResponse(payload, status_code=status_code)


@router.post("/api/kiosk/sleep")
def kiosk_sleep(request: Request):
    _session_required(request)
    return request.app.state.service.set_backend_sleep(True)


@router.post("/api/kiosk/wake")
def kiosk_wake(request: Request):
    _session_required(request)
    return request.app.state.service.set_backend_sleep(False)


@router.get("/health")
def health(request: Request):
    return request.app.state.service.health_liveness()


@router.get("/api/health/detail")
def health_detail(request: Request):
    _admin_required(request)
    return request.app.state.service.health_detail()


@router.post("/api/manual-open")
def manual_open(request: Request):
    _admin_required(request)
    request.app.state.service.manual_open()
    return {"ok": True}


@router.get("/api/users")
def list_users(request: Request):
    _admin_required(request)
    return db.list_users()


@router.post("/api/users")
def create_user(payload: UserCreate, request: Request):
    _admin_required(request)
    user_id = db.create_user(payload.nombre)
    return {"id": user_id}


@router.get("/api/users/{user_id}")
def get_user_detail(user_id: int, request: Request):
    _admin_required(request)
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    samples_count = db.count_user_samples(user_id)
    recent_logs = db.list_user_access_logs(user_id, limit=50)
    return {
        "user": user,
        "samples_count": samples_count,
        "recent_logs": recent_logs,
    }


@router.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UserStatusUpdate, request: Request):
    _admin_required(request)
    db.set_user_status(user_id, payload.activo)
    return {"ok": True}


@router.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request):
    _admin_required(request)
    deleted = db.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return {"ok": True}


@router.post("/api/users/{user_id}/capture")
def capture_samples(user_id: int, request: Request, count: int = 30):
    _admin_required(request)
    user = db.get_user(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if count < 1 or count > 60:
        raise HTTPException(status_code=400, detail="Cantidad inválida")

    service = request.app.state.service
    saved = 0
    attempts = 0
    while saved < count and attempts < count * 2:
        attempts += 1
        path = service.capture_sample(user_id, saved + 1)
        if path:
            db.insert_sample(user_id, path)
            saved += 1
        time.sleep(0.05)
    return {"saved": saved, "requested": count}


@router.post("/api/train")
def train(request: Request):
    _admin_required(request)
    service = request.app.state.service
    result = service.trainer.train_from_dataset()
    service.system_status["model"] = "loaded"
    return result


@router.get("/api/config")
def get_config(request: Request):
    _admin_required(request)
    return db.get_config()


@router.put("/api/config")
def update_config(payload: ConfigUpdate, request: Request):
    _admin_required(request)
    db.update_config(payload.umbral_confianza, payload.tiempo_apertura_seg, payload.max_intentos)
    return {"ok": True}


@router.get("/api/access-logs")
def access_logs(request: Request, limit: int = 100, offset: int = 0):
    _admin_required(request)
    limit = max(1, min(500, limit))
    offset = max(0, offset)
    return db.list_access_logs(limit=limit, offset=offset)


@router.post("/api/restart")
def restart(request: Request):
    _admin_required(request)
    if not config.debug:
        raise HTTPException(status_code=403, detail="No permitido en produccion")

    def _restart_proc():
        time.sleep(0.5)
        os.kill(os.getpid(), signal.SIGTERM)

    threading.Thread(target=_restart_proc, daemon=True).start()
    return JSONResponse({"ok": True, "message": "Reinicio solicitado"})


@router.post("/api/test/simulate-access")
def simulate_access(payload: SimulateAccessPayload, request: Request):
    if not config.debug:
        raise HTTPException(status_code=404, detail="No encontrado")
    _admin_required(request)
    return request.app.state.service.simulate_access_attempt(
        is_valid=payload.is_valid,
        confidence=payload.confidence,
    )
