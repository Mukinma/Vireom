import json
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from http.cookiejar import CookieJar
from pathlib import Path
from typing import Optional

from config import config
from database.db import db
from vision.recognizer import LBPHRecognizer


@dataclass
class StepResult:
    ok: bool
    message: str


def log(msg: str) -> None:
    print(f"[PREVALIDATE] {msg}")


def run_python_script(script_name: str) -> StepResult:
    cmd = [sys.executable, script_name]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    output = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if output.strip():
        print(output.strip())
    if proc.returncode != 0:
        return StepResult(False, f"{script_name} falló con código {proc.returncode}")
    return StepResult(True, f"{script_name} OK")


def validate_dataset_report() -> StepResult:
    report_path = Path("logs/bootstrap_report.json")
    if not report_path.exists():
        return StepResult(False, "No existe logs/bootstrap_report.json")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    can_train = bool(report.get("can_train", False))
    if not can_train:
        return StepResult(False, f"Bootstrap indicó usuarios no entrenables: {report.get('non_trainable_users', [])}")
    return StepResult(True, "Dataset bootstrap validado")


def ensure_model_trained() -> StepResult:
    recognizer = LBPHRecognizer()
    model_path = Path(config.model_path)

    if model_path.exists() and recognizer.load_model(config.model_path):
        return StepResult(True, "Modelo LBPH ya existente y cargable")

    log("Modelo LBPH no encontrado/cargable. Ejecutando train_model.py...")
    train_result = run_python_script("train_model.py")
    if not train_result.ok:
        return train_result

    if not model_path.exists():
        return StepResult(False, "Entrenamiento completó pero no se encontró models/lbph_model.xml")
    if not recognizer.load_model(config.model_path):
        return StepResult(False, "Modelo entrenado no pudo cargarse correctamente")

    return StepResult(True, "Modelo entrenado correctamente")


def run_calibration() -> StepResult:
    result = run_python_script("calibrate_threshold.py")
    if not result.ok:
        return result
    report_path = Path("logs/calibration_report.txt")
    if not report_path.exists():
        return StepResult(False, "No se generó logs/calibration_report.txt")
    return StepResult(True, "Calibración experimental completada")


def wait_http(url: str, timeout_sec: int = 30) -> bool:
    start = time.time()
    while (time.time() - start) < timeout_sec:
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(1)
    return False


def start_server() -> subprocess.Popen:
    cmd = [sys.executable, "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
    process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return process


def stop_server(process: subprocess.Popen) -> None:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()


def build_admin_client(base_url: str):
    cj = CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    payload = urllib.parse.urlencode({"username": config.admin_user, "password": config.admin_password}).encode("utf-8")
    req = urllib.request.Request(f"{base_url}/auth/login", data=payload, method="POST")
    opener.open(req, timeout=5)
    return opener


def fetch_json(opener, url: str, method: str = "GET", body: Optional[dict] = None) -> dict:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with opener.open(req, timeout=8) as response:
        return json.loads(response.read().decode("utf-8"))


def smoke_health(opener, base_url: str) -> StepResult:
    try:
        health = fetch_json(opener, f"{base_url}/health")
    except Exception as exc:
        return StepResult(False, f"Smoke /health falló: {exc}")

    camera_ok = bool(health.get("camera_active", False))
    model_ok = bool(health.get("model_loaded", False))
    db_ok = bool(health.get("db_accessible", False))
    gpio_ok = bool(health.get("gpio_initialized", False))

    status = fetch_json(opener, f"{base_url}/api/status")
    gpio_mode = status.get("gpio")
    gpio_acceptable = gpio_ok or gpio_mode == "mock"

    if not (camera_ok and model_ok and db_ok and gpio_acceptable):
        return StepResult(
            False,
            f"/health inválido camera={camera_ok} model={model_ok} db={db_ok} gpio={gpio_ok} gpio_mode={gpio_mode}",
        )
    return StepResult(True, "/health smoke OK")


def simulate_access_flow(opener, base_url: str) -> StepResult:
    before_logs = fetch_json(opener, f"{base_url}/api/access-logs?limit=300")
    before_count = len(before_logs)
    status_before = fetch_json(opener, f"{base_url}/api/status")
    gpio_before = int(status_before.get("gpio_activations", 0))

    for _ in range(5):
        fetch_json(
            opener,
            f"{base_url}/api/test/simulate-access",
            method="POST",
            body={"is_valid": True},
        )

    for _ in range(5):
        fetch_json(
            opener,
            f"{base_url}/api/test/simulate-access",
            method="POST",
            body={"is_valid": False},
        )

    logs = fetch_json(opener, f"{base_url}/api/access-logs?limit=400")
    status_after = fetch_json(opener, f"{base_url}/api/status")
    gpio_after = int(status_after.get("gpio_activations", 0))

    new_logs = logs[: max(0, len(logs) - before_count)]
    authorized = sum(1 for row in new_logs if row.get("resultado") == "AUTORIZADO")
    denied = sum(1 for row in new_logs if str(row.get("resultado", "")).startswith("DENEGADO"))
    blocked = sum(1 for row in new_logs if row.get("resultado") == "DENEGADO_BLOQUEO")
    gpio_delta = gpio_after - gpio_before

    cfg = fetch_json(opener, f"{base_url}/api/config")
    max_attempts = int(cfg.get("max_intentos", 3))

    checks = [
        (authorized >= 5, f"AUTORIZADO esperados>=5 obtenido={authorized}"),
        (denied >= 5, f"DENEGADO esperados>=5 obtenido={denied}"),
        (blocked >= (5 - max_attempts + 1), f"DENEGADO_BLOQUEO esperado>=1 obtenido={blocked}"),
        (gpio_delta >= 5 or status_after.get("gpio") == "mock", f"GPIO activaciones delta esperado>=5 obtenido={gpio_delta}"),
    ]

    failed = [msg for ok, msg in checks if not ok]
    if failed:
        return StepResult(False, "Simulación fallida: " + " | ".join(failed))
    return StepResult(True, "Simulación 5 válidos + 5 inválidos OK")


def run_extended_soak(pid: int, minutes: int = 120) -> StepResult:
    cmd = [
        sys.executable,
        "soak_monitor_10m.py",
        "http://127.0.0.1:8000",
        str(pid),
        str(minutes),
        "logs/system.log",
        "logs/soak_2h_report.txt",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    print(proc.stdout)
    if proc.returncode != 0:
        return StepResult(False, "Soak extendido reportó degradación/errores")
    return StepResult(True, "Soak extendido completado sin errores")


def main() -> int:
    db.init_db()

    bootstrap_result = run_python_script("bootstrap_dataset.py")
    log(bootstrap_result.message)
    if not bootstrap_result.ok:
        log("Se detiene flujo: bootstrap falló")
        return 1

    dataset_ok = validate_dataset_report()
    log(dataset_ok.message)
    if not dataset_ok.ok:
        log("Se detiene flujo: dataset no entrenable")
        return 1

    model_ok = ensure_model_trained()
    log(model_ok.message)
    if not model_ok.ok:
        log("Se detiene flujo: modelo LBPH no funcional")
        return 1

    calibration_ok = run_calibration()
    log(calibration_ok.message)
    if not calibration_ok.ok:
        log("Se detiene flujo: calibración fallida")
        return 1

    server = start_server()
    try:
        if not wait_http("http://127.0.0.1:8000/health", timeout_sec=40):
            log("Servidor no respondió /health")
            return 1

        opener = build_admin_client("http://127.0.0.1:8000")

        health_ok = smoke_health(opener, "http://127.0.0.1:8000")
        log(health_ok.message)
        if not health_ok.ok:
            return 1

        sim_ok = simulate_access_flow(opener, "http://127.0.0.1:8000")
        log(sim_ok.message)
        if not sim_ok.ok:
            return 1

        log("Prevalidación exitosa. Iniciando soak extendido de 2 horas...")
        soak_ok = run_extended_soak(server.pid, minutes=120)
        log(soak_ok.message)
        if not soak_ok.ok:
            return 1

        systemd_result = run_python_script("generate_systemd_artifacts.py")
        log(systemd_result.message)
        return 0 if systemd_result.ok else 1
    finally:
        stop_server(server)


if __name__ == "__main__":
    raise SystemExit(main())
