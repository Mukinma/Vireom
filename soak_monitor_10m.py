import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def get_proc_stats(pid: int) -> tuple[float, float]:
    cmd = ["ps", "-p", str(pid), "-o", "%cpu=,rss="]
    output = subprocess.check_output(cmd, text=True).strip()
    if not output:
        return 0.0, 0.0
    cpu_str, rss_kb_str = output.split()
    rss_mb = float(rss_kb_str) / 1024.0
    return float(cpu_str), rss_mb


def detect_memory_leak(memory_samples: list[float]) -> bool:
    if len(memory_samples) < 5:
        return False
    start = memory_samples[0]
    end = memory_samples[-1]
    growth_pct = ((end - start) / max(start, 1.0)) * 100.0
    return growth_pct > 25.0


def scan_log_for_exceptions(log_path: Path, start_ts: float) -> list[str]:
    if not log_path.exists():
        return ["log_file_missing"]
    text = log_path.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()[-2000:]
    findings: list[str] = []
    patterns = [
        r"CRITICAL",
        r"Unhandled",
        r"Traceback",
        r"fatal_runtime_error",
        r"process_frame_failed",
        r"model_load_failed",
        r"watchdog_camera_inactive",
    ]
    for line in lines:
        if any(re.search(p, line) for p in patterns):
            findings.append(line)
    return findings[-20:]


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    pid = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    minutes = int(sys.argv[3]) if len(sys.argv) > 3 else 10
    log_path = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("logs/system.log")
    report_path = Path(sys.argv[5]) if len(sys.argv) > 5 else Path("logs/soak_report.txt")

    if pid <= 0:
        print("PID inválido para monitoreo")
        return 2

    start = time.time()
    mem_samples: list[float] = []
    cpu_samples: list[float] = []
    latency_samples: list[float] = []
    pipeline_samples: list[float] = []
    fps_samples: list[float] = []
    errors: list[str] = []
    peak_mem = 0.0
    start_attempts = None
    start_gpio_activations = None

    print(f"Soak iniciado pid={pid} url={base_url} duration_min={minutes}")

    duration_sec = minutes * 60
    minute = 0
    while (time.time() - start) < duration_sec:
        minute += 1
        try:
            status = fetch_json(f"{base_url}/api/status")
            health = fetch_json(f"{base_url}/health")
            cpu, mem_mb = get_proc_stats(pid)
            mem_samples.append(mem_mb)
            cpu_samples.append(cpu)
            peak_mem = max(peak_mem, mem_mb)

            fps = status.get("fps", 0)
            avg_recognition_ms = status.get("avg_recognition_ms", 0.0)
            avg_pipeline_ms = status.get("avg_pipeline_ms", 0.0)
            attempts = status.get("attempts_processed", 0)
            gpio_activations = status.get("gpio_activations", 0)
            latency_samples.append(float(avg_recognition_ms or 0.0))
            pipeline_samples.append(float(avg_pipeline_ms or 0.0))
            fps_samples.append(float(fps or 0.0))

            if start_attempts is None:
                start_attempts = int(attempts)
            if start_gpio_activations is None:
                start_gpio_activations = int(gpio_activations)

            print(
                f"min={minute} cpu={cpu:.2f}% mem={mem_mb:.2f}MB fps={fps} "
                f"avg_recognition_ms={avg_recognition_ms} avg_pipeline_ms={avg_pipeline_ms} "
                f"attempts={attempts} gpio_activations={gpio_activations}"
            )

            if not health.get("camera_active", False):
                errors.append(f"minute_{minute}:camera_thread_down_or_inactive")
            if not health.get("model_loaded", False):
                errors.append(f"minute_{minute}:model_not_loaded")
            if not health.get("db_accessible", False):
                errors.append(f"minute_{minute}:db_unavailable")
            gpio_mode = status.get("gpio", "")
            if not health.get("gpio_initialized", False) and gpio_mode != "mock":
                errors.append(f"minute_{minute}:gpio_not_initialized")
            if int(status.get("processing_errors", 0)) > 0:
                errors.append(f"minute_{minute}:processing_errors={status.get('processing_errors')}")

        except Exception as exc:
            errors.append(f"minute_{minute}:monitor_exception={exc}")

        remaining = duration_sec - (time.time() - start)
        if remaining > 0:
            time.sleep(min(60, remaining))

    leak_detected = detect_memory_leak(mem_samples)
    if leak_detected:
        errors.append("memory_leak_suspected")

    log_findings = scan_log_for_exceptions(log_path, start)
    if log_findings:
        errors.extend([f"log:{line}" for line in log_findings])

    total_sec = int(time.time() - start)
    avg_cpu = round(sum(cpu_samples) / max(1, len(cpu_samples)), 2)
    avg_mem = round(sum(mem_samples) / max(1, len(mem_samples)), 2)
    avg_latency = round(sum(latency_samples) / max(1, len(latency_samples)), 2)
    avg_pipeline = round(sum(pipeline_samples) / max(1, len(pipeline_samples)), 2)
    avg_fps = round(sum(fps_samples) / max(1, len(fps_samples)), 2)
    end_attempts = start_attempts if start_attempts is not None else 0
    end_gpio_activations = start_gpio_activations if start_gpio_activations is not None else 0
    try:
        status_final = fetch_json(f"{base_url}/api/status")
        end_attempts = int(status_final.get("attempts_processed", end_attempts))
        end_gpio_activations = int(status_final.get("gpio_activations", end_gpio_activations))
    except Exception as exc:
        errors.append(f"final_status_exception={exc}")

    attempts_delta = end_attempts - (start_attempts or 0)
    gpio_delta = end_gpio_activations - (start_gpio_activations or 0)

    if len(pipeline_samples) >= 6:
        head = sum(pipeline_samples[:3]) / 3.0
        tail = sum(pipeline_samples[-3:]) / 3.0
        if tail > (head * 1.3):
            errors.append("performance_degradation_detected")

    summary_lines = [
        "=== RESUMEN SOAK ===",
        f"tiempo_total_sec={total_sec}",
        f"cpu_promedio_pct={avg_cpu}",
        f"memoria_promedio_mb={avg_mem}",
        f"latencia_promedio_frame_ms={avg_latency}",
        f"pipeline_promedio_ms={avg_pipeline}",
        f"fps_promedio={avg_fps}",
        f"intentos_procesados={attempts_delta}",
        f"activaciones_gpio={gpio_delta}",
        f"pico_memoria_mb={peak_mem:.2f}",
        f"degradacion_detectada={'yes' if 'performance_degradation_detected' in errors else 'no'}",
        f"errores_detectados={len(errors)}",
    ]
    for err in errors[:50]:
        summary_lines.append(f"- {err}")

    summary_text = "\n".join(summary_lines) + "\n"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(summary_text, encoding="utf-8")

    print(summary_text)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
