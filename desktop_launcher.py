#!/usr/bin/env python3
"""Native desktop launcher for Vireom.

Starts the local FastAPI app on 127.0.0.1 and wraps it in a pywebview window
without requiring the user to type localhost in a browser.
"""

from __future__ import annotations

import argparse
import importlib
import logging
import platform
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

import uvicorn


logger = logging.getLogger("camerapi.desktop")


@dataclass(frozen=True)
class DesktopLauncherConfig:
    host: str = "127.0.0.1"
    port: int = 8000
    start_path: str = "/"
    width: int = 1280
    height: int = 820
    health_timeout_s: float = 25.0
    health_interval_s: float = 0.25
    title: str = "Vireom"

    @property
    def base_url(self) -> str:
        return f"http://{self.host}:{self.port}"

    @property
    def start_url(self) -> str:
        return f"{self.base_url}{self.start_path}"


@dataclass
class DesktopServerHandle:
    server: uvicorn.Server
    thread: threading.Thread
    base_url: str

    def stop(self, timeout_s: float = 10.0) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=timeout_s)
        if self.thread.is_alive():
            self.server.force_exit = True
            self.thread.join(timeout=2.0)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Launch Vireom in a native desktop window.")
    parser.add_argument("--host", default="127.0.0.1", help="Local bind host for desktop mode.")
    parser.add_argument("--port", default=8000, type=int, help="Local bind port for desktop mode.")
    parser.add_argument("--width", default=1280, type=int, help="Initial window width.")
    parser.add_argument("--height", default=820, type=int, help="Initial window height.")
    parser.add_argument("--start-path", default="/", help="Initial route to open inside the app.")
    return parser


def build_launcher_config(args: argparse.Namespace) -> DesktopLauncherConfig:
    return DesktopLauncherConfig(
        host=str(args.host or "127.0.0.1"),
        port=int(args.port or 8000),
        width=max(960, int(args.width or 1280)),
        height=max(640, int(args.height or 820)),
        start_path=_normalize_start_path(str(args.start_path or "/")),
    )


def _normalize_start_path(raw_path: str) -> str:
    return raw_path if raw_path.startswith("/") else f"/{raw_path}"


def assert_port_available(host: str, port: int) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.5)
        if probe.connect_ex((host, port)) == 0:
            raise RuntimeError(
                f"El puerto local {port} ya esta en uso. Cierra la otra instancia de Vireom o libera ese puerto."
            )


def _build_server_config(app: Any, config: DesktopLauncherConfig) -> uvicorn.Config:
    return uvicorn.Config(
        app=app,
        host=config.host,
        port=config.port,
        reload=False,
        log_level="info",
        access_log=False,
    )


def create_server_handle(config: DesktopLauncherConfig) -> DesktopServerHandle:
    from main import get_app

    app = get_app()
    server = uvicorn.Server(_build_server_config(app, config))
    thread = threading.Thread(target=server.run, name="vireom-desktop-server", daemon=True)
    return DesktopServerHandle(server=server, thread=thread, base_url=config.base_url)


def wait_for_server_ready(
    base_url: str,
    timeout_s: float,
    interval_s: float,
    server_thread: threading.Thread | None = None,
) -> None:
    deadline = time.monotonic() + timeout_s
    health_url = f"{base_url}/health"

    while time.monotonic() < deadline:
        if server_thread is not None and not server_thread.is_alive():
            raise RuntimeError("El servidor local termino antes de completar el arranque.")
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                if 200 <= int(response.status) < 500:
                    return
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
            time.sleep(interval_s)

    raise RuntimeError("El servidor local no respondio a tiempo en /health.")


def start_server(config: DesktopLauncherConfig) -> DesktopServerHandle:
    assert_port_available(config.host, config.port)
    handle = create_server_handle(config)
    handle.thread.start()
    try:
        wait_for_server_ready(
            handle.base_url,
            timeout_s=config.health_timeout_s,
            interval_s=config.health_interval_s,
            server_thread=handle.thread,
        )
        return handle
    except Exception:
        handle.stop(timeout_s=2.0)
        raise


def load_webview_module() -> Any:
    try:
        return importlib.import_module("webview")
    except ImportError as exc:
        linux_hint = ""
        if platform.system().lower() == "linux":
            linux_hint = (
                " En Linux/Raspberry OS tambien necesitas un runtime grafico compatible "
                "(por ejemplo GTK/WebKit2GTK o Qt)."
            )
        raise RuntimeError(
            "No se encontro pywebview. Instala las dependencias de escritorio con "
            "`pip install -r requirements.txt`." + linux_hint
        ) from exc


def open_desktop_window(config: DesktopLauncherConfig) -> None:
    webview = load_webview_module()

    try:
        webview.create_window(
            config.title,
            config.start_url,
            width=config.width,
            height=config.height,
            resizable=True,
        )
        webview.start(debug=False)
    except Exception as exc:
        linux_hint = ""
        if platform.system().lower() == "linux":
            linux_hint = (
                " Verifica que Raspberry OS/Linux tenga instalado un backend compatible de "
                "GTK/WebKit2GTK o Qt para pywebview."
            )
        raise RuntimeError(
            f"No se pudo abrir la ventana nativa de Vireom.{linux_hint}"
        ) from exc


def _configure_launcher_logging() -> None:
    if logging.getLogger().handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run_launcher(config: DesktopLauncherConfig) -> int:
    _configure_launcher_logging()
    logger.info("desktop_launcher_start url=%s", config.start_url)

    handle: DesktopServerHandle | None = None
    try:
        handle = start_server(config)
        open_desktop_window(config)
        return 0
    except KeyboardInterrupt:
        logger.info("desktop_launcher_interrupted")
        return 130
    except Exception as exc:
        logger.error("desktop_launcher_failed error=%s", exc)
        print(f"[Vireom desktop] {exc}", file=sys.stderr)
        return 1
    finally:
        if handle is not None:
            handle.stop()
            logger.info("desktop_launcher_stop")


def main(argv: list[str] | None = None) -> int:
    parser = _build_arg_parser()
    args = parser.parse_args(argv)
    return run_launcher(build_launcher_config(args))


if __name__ == "__main__":
    raise SystemExit(main())
