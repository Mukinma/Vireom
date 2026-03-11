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
