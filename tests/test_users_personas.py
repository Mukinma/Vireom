from pathlib import Path

import cv2
import numpy as np

import api.routes as routes_module
from database.db import Database

from tests.test_routes import _csrf_headers, _login_admin


def test_list_users_includes_personas_summary(tmp_path):
    db_path = tmp_path / "personas.db"
    store = Database(db_path=str(db_path))
    store.init_db()

    ada_id = store.create_user("Ada Lovelace")
    grace_id = store.create_user("Grace Hopper")
    store.set_user_status(grace_id, False)
    store.insert_sample_with_pose(ada_id, "dataset/user_1/sample_001.jpg", "center")
    store.insert_access(ada_id, 64.2, "AUTORIZADO")
    store.save_model_meta(samples=35, unique_users=1)

    users = store.list_users()

    ada = next(user for user in users if user["id"] == ada_id)
    grace = next(user for user in users if user["id"] == grace_id)
    assert ada["samples_count"] == 1
    assert ada["last_sample_at"]
    assert ada["last_access_at"]
    assert ada["last_access_result"] == "AUTORIZADO"
    assert ada["needs_training"] is False
    assert ada["thumbnail_url"] == f"/api/users/{ada_id}/thumbnail"
    assert grace["samples_count"] == 0
    assert grace["needs_training"] is True
    assert grace["thumbnail_url"] is None


def test_user_thumbnail_requires_admin(client):
    response = client.get("/api/users/1/thumbnail")

    assert response.status_code == 401


def test_user_thumbnail_returns_secure_jpeg(client, monkeypatch, tmp_path):
    sample_path = tmp_path / "dataset" / "user_1" / "sample_001.jpg"
    sample_path.parent.mkdir(parents=True)
    cv2.imwrite(str(sample_path), np.full((40, 40), 180, dtype=np.uint8))

    class FakeStorage:
        def read_image(self, path, flags=cv2.IMREAD_GRAYSCALE):
            assert Path(path) == sample_path
            return cv2.imread(str(sample_path), flags)

    monkeypatch.setattr(routes_module.db, "get_user_thumbnail_path", lambda user_id: str(sample_path))
    monkeypatch.setattr(routes_module, "_storage", FakeStorage(), raising=False)

    _login_admin(client)
    response = client.get("/api/users/1/thumbnail")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-type"].startswith("image/jpeg")
    assert response.content.startswith(b"\xff\xd8")


def test_user_thumbnail_without_sample_is_empty_no_store(client, monkeypatch):
    monkeypatch.setattr(routes_module.db, "get_user_thumbnail_path", lambda user_id: None, raising=False)

    _login_admin(client)
    response = client.get("/api/users/1/thumbnail")

    assert response.status_code == 204
    assert response.headers["cache-control"] == "no-store"
    assert response.content == b""
