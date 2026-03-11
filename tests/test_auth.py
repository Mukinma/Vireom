import logging


def test_login_ok_redirige_a_admin(client):
    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "admin-pass"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/admin"


def test_login_invalido_redirige_con_error_y_loguea(client, caplog):
    caplog.set_level(logging.WARNING, logger="camerapi.auth")
    response = client.post(
        "/auth/login",
        data={"username": "admin", "password": "incorrecta"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin?error=1"
    assert any("login_failed" in record.message for record in caplog.records)


def test_admin_muestra_feedback_de_error(client):
    response = client.get("/admin?error=1")
    assert response.status_code == 200
    assert "Credenciales inválidas.".encode("utf-8") in response.content
