import json
import sys
import time
import urllib.error
import urllib.request


def check_health(base_url: str) -> tuple[bool, dict]:
    try:
        with urllib.request.urlopen(f"{base_url}/health", timeout=3) as response:
            payload = json.loads(response.read().decode("utf-8"))
            return bool(payload.get("healthy", False)), payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return False, {}


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    duration_sec = int(sys.argv[2]) if len(sys.argv) > 2 else 7200
    interval_sec = int(sys.argv[3]) if len(sys.argv) > 3 else 5

    start = time.time()
    failures = 0
    max_consecutive_failures = 6

    print(f"Soak test iniciado url={base_url} duration={duration_sec}s interval={interval_sec}s")
    while (time.time() - start) < duration_sec:
        healthy, payload = check_health(base_url)
        if healthy:
            failures = 0
            metrics = payload.get("metrics", {})
            print(
                "ok",
                f"fps={metrics.get('fps', 0)}",
                f"avg_ms={metrics.get('avg_recognition_ms', 0)}",
                f"fails={metrics.get('failed_attempts_consecutive', 0)}",
            )
        else:
            failures += 1
            print(f"health_fail consecutive={failures}")
            if failures >= max_consecutive_failures:
                print("RESULT=FAIL degradación sostenida")
                return 1
        time.sleep(interval_sec)

    print("RESULT=PASS operación continua completada")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
