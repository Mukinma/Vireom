#!/usr/bin/env python3
"""Install Linux/Raspberry OS desktop shortcuts for Vireom."""

from __future__ import annotations

import argparse
import platform
from pathlib import Path


APP_NAME = "Vireom"
APP_COMMENT = "Abrir Vireom en una ventana nativa"
PROJECT_ROOT = Path(__file__).resolve().parent
RUNNER_PATH = PROJECT_ROOT / "run_desktop.sh"
ICON_PATH = PROJECT_ROOT / "frontend" / "static" / "images" / "favicon.svg"


def _desktop_escape(value: Path | str) -> str:
    return str(value).replace("\\", "\\\\").replace(" ", "\\ ")


def build_desktop_entry(exec_path: Path, icon_path: Path) -> str:
    return (
        "[Desktop Entry]\n"
        "Version=1.0\n"
        "Type=Application\n"
        f"Name={APP_NAME}\n"
        f"Comment={APP_COMMENT}\n"
        f"Exec={_desktop_escape(exec_path)}\n"
        f"Path={_desktop_escape(exec_path.parent)}\n"
        f"Icon={_desktop_escape(icon_path)}\n"
        "Terminal=false\n"
        "StartupNotify=true\n"
        "Categories=Utility;\n"
    )


def install_linux_shortcuts(
    *,
    applications_dir: Path,
    autostart_dir: Path,
    enable_autostart: bool,
    runner_path: Path = RUNNER_PATH,
    icon_path: Path = ICON_PATH,
) -> tuple[Path, Path | None]:
    applications_dir.mkdir(parents=True, exist_ok=True)
    desktop_entry = applications_dir / "vireom.desktop"
    desktop_entry.write_text(build_desktop_entry(runner_path, icon_path), encoding="utf-8")
    desktop_entry.chmod(0o755)

    autostart_entry: Path | None = None
    if enable_autostart:
        autostart_dir.mkdir(parents=True, exist_ok=True)
        autostart_entry = autostart_dir / "vireom.desktop"
        autostart_entry.write_text(build_desktop_entry(runner_path, icon_path), encoding="utf-8")
        autostart_entry.chmod(0o755)

    return desktop_entry, autostart_entry


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Vireom desktop shortcuts on Linux/Raspberry OS.")
    parser.add_argument(
        "--autostart",
        action="store_true",
        help="Also install an autostart entry in ~/.config/autostart.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    if platform.system().lower() != "linux":
        print("Este instalador solo aplica a Linux/Raspberry OS.")
        return 1

    args = _build_arg_parser().parse_args(argv)
    home = Path.home()
    applications_dir = home / ".local" / "share" / "applications"
    autostart_dir = home / ".config" / "autostart"

    desktop_entry, autostart_entry = install_linux_shortcuts(
        applications_dir=applications_dir,
        autostart_dir=autostart_dir,
        enable_autostart=bool(args.autostart),
    )

    print(f"Acceso directo instalado en: {desktop_entry}")
    if autostart_entry is not None:
        print(f"Autoarranque instalado en: {autostart_entry}")
    else:
        print("Autoarranque no instalado. Usa --autostart si quieres habilitarlo.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
