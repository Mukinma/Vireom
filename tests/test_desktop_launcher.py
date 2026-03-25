import threading

import pytest

import desktop_launcher
import install_linux_desktop_entry


class _FakeSocket:
    def __init__(self, connect_result=0):
        self._connect_result = connect_result

    def settimeout(self, _timeout):
        return None

    def connect_ex(self, _address):
        return self._connect_result

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _FakeResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_assert_port_available_rechaza_puerto_ocupado(monkeypatch):
    monkeypatch.setattr(
        desktop_launcher.socket,
        "socket",
        lambda *args, **kwargs: _FakeSocket(connect_result=0),
    )

    with pytest.raises(RuntimeError, match="ya esta en uso"):
        desktop_launcher.assert_port_available("127.0.0.1", 8000)


def test_wait_for_server_ready_detecta_health(monkeypatch):
    attempts = {"count": 0}

    def _fake_urlopen(url, timeout):
        attempts["count"] += 1
        if attempts["count"] < 2:
            raise desktop_launcher.urllib.error.URLError("warming up")
        return _FakeResponse()

    monkeypatch.setattr(desktop_launcher.urllib.request, "urlopen", _fake_urlopen)
    monkeypatch.setattr(desktop_launcher.time, "sleep", lambda _seconds: None)

    desktop_launcher.wait_for_server_ready(
        "http://127.0.0.1:8000",
        timeout_s=2.0,
        interval_s=0.01,
        server_thread=threading.current_thread(),
    )

    assert attempts["count"] == 2


def test_load_webview_module_falla_con_mensaje_claro(monkeypatch):
    def _raise_import_error(name):
        raise ImportError(name)

    monkeypatch.setattr(desktop_launcher.importlib, "import_module", _raise_import_error)

    with pytest.raises(RuntimeError, match="pywebview"):
        desktop_launcher.load_webview_module()


def test_install_linux_shortcuts_escribe_archivos(tmp_path):
    applications_dir = tmp_path / "applications"
    autostart_dir = tmp_path / "autostart"
    runner_path = tmp_path / "run_desktop.sh"
    icon_path = tmp_path / "favicon.svg"
    runner_path.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    icon_path.write_text("<svg />\n", encoding="utf-8")

    desktop_entry, autostart_entry = install_linux_desktop_entry.install_linux_shortcuts(
        applications_dir=applications_dir,
        autostart_dir=autostart_dir,
        enable_autostart=True,
        runner_path=runner_path,
        icon_path=icon_path,
    )

    assert desktop_entry.exists()
    assert autostart_entry is not None and autostart_entry.exists()
    desktop_text = desktop_entry.read_text(encoding="utf-8")
    assert "Name=Vireom" in desktop_text
    assert str(runner_path).replace(" ", "\\ ") in desktop_text
    assert str(icon_path).replace(" ", "\\ ") in desktop_text
