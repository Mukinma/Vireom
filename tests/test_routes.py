import api.routes as routes_module


def _login_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_stream_rechaza_acceso_anonimo(client):
    response = client.get("/api/stream")
    assert response.status_code == 401


def test_kiosk_home_setea_sesion(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "session" in response.headers.get("set-cookie", "").lower() or response.cookies
    html = response.text
    assert "tipsCarouselCamera" not in html
    assert 'id="cameraBadge"' not in html
    assert "?v=" in html


def test_health_publico_es_minimo(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"healthy": True}


def test_health_detallado_requiere_admin(client):
    response = client.get("/api/health/detail")
    assert response.status_code == 401


def test_health_detallado_para_admin(client):
    _login_admin(client)
    response = client.get("/api/health/detail")
    assert response.status_code == 200
    assert "metrics" in response.json()


def test_restart_deshabilitado_en_produccion(client):
    routes_module.config.debug = False
    _login_admin(client)
    response = client.post("/api/restart")
    assert response.status_code == 403


def test_simulate_access_oculto_en_produccion(client):
    routes_module.config.debug = False
    _login_admin(client)
    response = client.post("/api/test/simulate-access", json={"is_valid": True})
    assert response.status_code == 404


def test_recognize_tiene_rate_limiting(client):
    for _ in range(10):
        response = client.post("/api/recognize")
        assert response.status_code == 200

    response = client.post("/api/recognize")
    assert response.status_code == 429


def test_kiosk_sleep_requiere_sesion(client):
    response = client.post("/api/kiosk/sleep")
    assert response.status_code == 401


def test_kiosk_sleep_y_wake_con_sesion(client):
    home = client.get("/")
    assert home.status_code == 200

    sleep_response = client.post("/api/kiosk/sleep")
    assert sleep_response.status_code == 200
    assert sleep_response.json().get("sleep_mode") is True

    wake_response = client.post("/api/kiosk/wake")
    assert wake_response.status_code == 200
    assert wake_response.json().get("sleep_mode") is False


def test_enrollment_status_idle_para_admin(client):
    _login_admin(client)
    response = client.get("/api/enrollment/status")
    assert response.status_code == 200
    payload = response.json()
    assert payload["phase"] == "preflight"
    assert payload["state"] == "idle"


def test_enrollment_start_devuelve_snapshot_rehidratable(client, monkeypatch):
    monkeypatch.setattr(routes_module.db, "get_user", lambda user_id: {"id": user_id, "nombre": "Ada"})
    _login_admin(client)
    response = client.post("/api/enrollment/start", json={"user_id": 1})
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["phase"] == "active"
    assert payload["state"] == "step_active"
    assert payload["user_id"] == 1
    assert payload["actions"]["can_abort"] is True


def test_enrollment_finish_limpia_sesion_terminal(client):
    _login_admin(client)
    service = client.app.state.service
    service._enrollment_status = {
        **service._active_enrollment_status(7),
        "phase": "completed_review",
        "state": "completed",
        "actions": {
            "can_retry": False,
            "can_abort": False,
            "can_finish": True,
            "can_train": True,
        },
    }

    response = client.post("/api/enrollment/finish")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["phase"] == "preflight"
    assert service._enrollment_status is None


def test_enrollment_finish_rechaza_sesion_activa(client):
    _login_admin(client)
    client.app.state.service._enrollment_status = client.app.state.service._active_enrollment_status(3)

    response = client.post("/api/enrollment/finish")
    assert response.status_code == 409
    assert response.json()["error"] == "enrollment_not_finishable"
