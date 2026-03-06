from pathlib import Path


def soak_passed(report_path: Path) -> bool:
    if not report_path.exists():
        return False
    text = report_path.read_text(encoding="utf-8", errors="ignore")
    return "errores_detectados=0" in text and "degradacion_detectada=no" in text


def main() -> int:
    report_path = Path("logs/soak_2h_report.txt")
    if not soak_passed(report_path):
        print("Soak 2h no aprobado. No se generan artefactos systemd.")
        return 1

    project_path = Path.cwd()
    out_dir = Path("deploy/systemd")
    out_dir.mkdir(parents=True, exist_ok=True)

    service_text = f"""[Unit]
Description=Servicio Biometrico Facial
After=network.target

[Service]
Type=simple
Restart=always
RestartSec=5
User=pi
WorkingDirectory={project_path}
ExecStart=/usr/bin/python3 main.py
StandardOutput=append:/home/pi/biometrico/logs/systemd.log
StandardError=append:/home/pi/biometrico/logs/systemd_error.log

[Install]
WantedBy=multi-user.target
"""

    service_path = out_dir / "biometrico.service"
    service_path.write_text(service_text, encoding="utf-8")

    install_script = out_dir / "install_systemd.sh"
    install_script.write_text(
        """#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
REPORT_FILE="$PROJECT_DIR/logs/soak_2h_report.txt"
SERVICE_FILE="$PROJECT_DIR/deploy/systemd/biometrico.service"

if [[ ! -f "$REPORT_FILE" ]]; then
  echo "No existe reporte de soak: $REPORT_FILE"
  exit 1
fi

if ! grep -q "errores_detectados=0" "$REPORT_FILE"; then
  echo "Soak no aprobado: errores detectados"
  exit 1
fi

if ! grep -q "degradacion_detectada=no" "$REPORT_FILE"; then
  echo "Soak no aprobado: degradación detectada"
  exit 1
fi

sudo cp "$SERVICE_FILE" /etc/systemd/system/biometrico.service
sudo systemctl daemon-reload
sudo systemctl enable biometrico.service
sudo systemctl restart biometrico.service
sudo systemctl status biometrico.service --no-pager
""",
        encoding="utf-8",
    )

    print(f"Systemd artifacts generados: {service_path} y {install_script}")
    print("Para instalar: bash deploy/systemd/install_systemd.sh")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
