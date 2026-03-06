import os
import sys
import threading
import time
from typing import Optional

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel, Field

from config import config
from database.db import db

router = APIRouter()


def _is_admin(request: Request) -> bool:
    return bool(request.session.get("admin_authenticated"))


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
    return request.app.state.templates.TemplateResponse("index.html", {"request": request})


@router.get("/admin", response_class=HTMLResponse)
def admin(request: Request):
    if not _is_admin(request):
        return request.app.state.templates.TemplateResponse("login.html", {"request": request})
    return request.app.state.templates.TemplateResponse("admin.html", {"request": request})


@router.post("/auth/login")
def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username == config.admin_user and password == config.admin_password:
        request.session["admin_authenticated"] = True
        return RedirectResponse(url="/admin", status_code=303)
    return RedirectResponse(url="/admin", status_code=303)


@router.post("/auth/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin", status_code=303)


@router.get("/api/stream")
def stream(request: Request):
    service = request.app.state.service

    def generate():
        while True:
            frame = service.camera.get_jpeg()
            if frame is None:
                time.sleep(0.05)
                continue
            yield b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@router.get("/api/status")
def status(request: Request):
    return request.app.state.service.get_status()


@router.post("/api/recognize")
def recognize(request: Request):
    payload, status_code = request.app.state.service.analyze_once()
    return JSONResponse(payload, status_code=status_code)


@router.get("/health")
def health(request: Request):
    return request.app.state.service.health()


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


@router.patch("/api/users/{user_id}")
def update_user(user_id: int, payload: UserStatusUpdate, request: Request):
    _admin_required(request)
    db.set_user_status(user_id, payload.activo)
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
    while saved < count and attempts < count * 3:
        attempts += 1
        path = service.capture_sample(user_id, saved + 1)
        if path:
            db.insert_sample(user_id, path)
            saved += 1
        time.sleep(0.15)
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
def access_logs(request: Request, limit: int = 100):
    _admin_required(request)
    limit = max(1, min(500, limit))
    return db.list_access_logs(limit=limit)


@router.post("/api/restart")
def restart(request: Request):
    _admin_required(request)

    def _restart_proc():
        time.sleep(1)
        os.execv(sys.executable, [sys.executable, "main.py"])

    threading.Thread(target=_restart_proc, daemon=True).start()
    return JSONResponse({"ok": True, "message": "Reinicio solicitado"})


@router.post("/api/test/simulate-access")
def simulate_access(payload: SimulateAccessPayload, request: Request):
    _admin_required(request)
    return request.app.state.service.simulate_access_attempt(
        is_valid=payload.is_valid,
        confidence=payload.confidence,
    )
