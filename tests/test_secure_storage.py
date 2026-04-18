"""Tests for vision/secure_storage.py"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import cv2
import numpy as np
import pytest

from config import AppConfig
from vision.secure_storage import SecureStorage


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cfg(encrypted: bool, secret: str = "test-secret-key-for-vireom-32ch") -> AppConfig:
    cfg = AppConfig()
    object.__setattr__(cfg, "storage_encrypted", encrypted)
    object.__setattr__(cfg, "secret_key", secret)
    return cfg


def _gray_image(h: int = 80, w: int = 60) -> np.ndarray:
    rng = np.random.default_rng(0)
    return rng.integers(0, 256, (h, w), dtype=np.uint8)


def _bgr_image(h: int = 80, w: int = 60) -> np.ndarray:
    rng = np.random.default_rng(1)
    return rng.integers(0, 256, (h, w, 3), dtype=np.uint8)


# ── SecureStorage construction ────────────────────────────────────────────────

class TestConstruction:
    def test_plain_mode_no_secret_required(self):
        cfg = _make_cfg(encrypted=False, secret="")
        store = SecureStorage(cfg)
        assert not store.enabled

    def test_encrypted_mode_empty_secret_raises(self):
        cfg = _make_cfg(encrypted=True, secret="")
        with pytest.raises(RuntimeError, match="CAMERAPI_SECRET"):
            SecureStorage(cfg)

    def test_encrypted_mode_initialises(self):
        cfg = _make_cfg(encrypted=True)
        store = SecureStorage(cfg)
        assert store.enabled
        assert store._fernet is not None


# ── Image write / read — plain mode ──────────────────────────────────────────

class TestImagePlainMode:
    def setup_method(self):
        self.store = SecureStorage(_make_cfg(encrypted=False))

    def test_write_read_roundtrip_gray(self, tmp_path):
        img = _gray_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        result = self.store.read_image(p, flags=cv2.IMREAD_GRAYSCALE)
        assert result is not None
        assert result.shape == img.shape

    def test_write_read_roundtrip_bgr(self, tmp_path):
        img = _bgr_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        result = self.store.read_image(p, flags=cv2.IMREAD_COLOR)
        assert result is not None
        assert result.shape == img.shape

    def test_plain_write_is_valid_jpeg(self, tmp_path):
        img = _gray_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        # Plain mode: file must be valid JPEG (readable by cv2.imread directly)
        direct = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        assert direct is not None

    def test_read_missing_file_returns_none(self, tmp_path):
        result = self.store.read_image(tmp_path / "missing.jpg")
        assert result is None


# ── Image write / read — encrypted mode ──────────────────────────────────────

class TestImageEncryptedMode:
    def setup_method(self):
        self.store = SecureStorage(_make_cfg(encrypted=True))

    def test_write_read_roundtrip_gray(self, tmp_path):
        img = _gray_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        result = self.store.read_image(p, flags=cv2.IMREAD_GRAYSCALE)
        assert result is not None
        assert result.shape == img.shape

    def test_encrypted_file_not_readable_by_opencv_directly(self, tmp_path):
        img = _gray_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        # Raw file must NOT be a valid JPEG (it's Fernet ciphertext)
        direct = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        assert direct is None

    def test_wrong_key_cannot_decrypt(self, tmp_path):
        img = _gray_image()
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        other_store = SecureStorage(_make_cfg(encrypted=True, secret="completely-different-secret-xyz"))
        result = other_store.read_image(p)
        assert result is None

    def test_pixel_fidelity_within_jpeg_tolerance(self, tmp_path):
        """After encrypt→decrypt, pixel values must be close (JPEG is lossy)."""
        img = _gray_image(h=200, w=200)
        p = tmp_path / "face.jpg"
        self.store.write_image(p, img)
        result = self.store.read_image(p, cv2.IMREAD_GRAYSCALE)
        assert result is not None
        # JPEG at quality=95 — max absolute pixel error < 10
        assert int(np.abs(img.astype(int) - result.astype(int)).max()) < 10

    def test_read_missing_file_returns_none(self, tmp_path):
        assert self.store.read_image(tmp_path / "missing.jpg") is None


# ── Model save / load ─────────────────────────────────────────────────────────

class TestModelPlainMode:
    def setup_method(self):
        self.store = SecureStorage(_make_cfg(encrypted=False))

    def test_load_missing_returns_false(self, tmp_path):
        mock_rec = MagicMock()
        ok = self.store.load_model(mock_rec, str(tmp_path / "model.xml"))
        assert ok is False
        mock_rec.read.assert_not_called()

    def test_load_existing_calls_read(self, tmp_path):
        p = tmp_path / "model.xml"
        p.write_text("<model/>")
        mock_rec = MagicMock()
        ok = self.store.load_model(mock_rec, str(p))
        assert ok is True
        mock_rec.read.assert_called_once_with(str(p))

    def test_save_calls_write(self, tmp_path):
        p = tmp_path / "model.xml"
        mock_rec = MagicMock()
        self.store.save_model(mock_rec, str(p))
        mock_rec.write.assert_called_once_with(str(p))


class TestModelEncryptedMode:
    def setup_method(self):
        self.store = SecureStorage(_make_cfg(encrypted=True))

    def test_save_encrypts_file_in_place(self, tmp_path):
        p = tmp_path / "model.xml"
        mock_rec = MagicMock()
        plain_xml = b"<opencv_storage><lbph/></opencv_storage>"

        def fake_write(path):
            Path(path).write_bytes(plain_xml)

        mock_rec.write.side_effect = fake_write
        self.store.save_model(mock_rec, str(p))

        # File must exist and must NOT be the original XML
        assert p.exists()
        assert p.read_bytes() != plain_xml
        # Must not start with XML tag (it's Fernet ciphertext now)
        assert not p.read_bytes().startswith(b"<")

    def test_load_decrypts_and_passes_temp_path(self, tmp_path):
        p = tmp_path / "model.xml"
        plain_xml = b"<opencv_storage/>"
        # Encrypt the file as if it was already saved encrypted
        p.write_bytes(self.store._fernet.encrypt(plain_xml))

        captured = {}

        def fake_read(path):
            captured["path"] = path
            captured["content"] = Path(path).read_bytes()

        mock_rec = MagicMock()
        mock_rec.read.side_effect = fake_read
        ok = self.store.load_model(mock_rec, str(p))

        assert ok is True
        assert captured.get("content") == plain_xml
        # Temp file must have been deleted
        assert not Path(captured["path"]).exists()

    def test_load_missing_returns_false(self, tmp_path):
        mock_rec = MagicMock()
        ok = self.store.load_model(mock_rec, str(tmp_path / "missing.xml"))
        assert ok is False
        mock_rec.read.assert_not_called()

    def test_wrong_key_on_load_returns_false(self, tmp_path):
        p = tmp_path / "model.xml"
        p.write_bytes(self.store._fernet.encrypt(b"<model/>"))

        other_store = SecureStorage(_make_cfg(encrypted=True, secret="different-key-padded-to-32chars!"))
        mock_rec = MagicMock()
        ok = other_store.load_model(mock_rec, str(p))
        assert ok is False


# ── encrypt_file / decrypt_file (migration helpers) ───────────────────────────

class TestMigrationHelpers:
    def setup_method(self):
        self.store = SecureStorage(_make_cfg(encrypted=True))

    def test_encrypt_file_roundtrip(self, tmp_path):
        p = tmp_path / "data.jpg"
        original = b"fake-jpeg-content-1234"
        p.write_bytes(original)
        self.store.encrypt_file(p)
        assert p.read_bytes() != original
        recovered = self.store.decrypt_file(p)
        assert recovered == original

    def test_encrypt_file_disabled_raises(self, tmp_path):
        plain_store = SecureStorage(_make_cfg(encrypted=False))
        p = tmp_path / "file.jpg"
        p.write_bytes(b"data")
        with pytest.raises(RuntimeError):
            plain_store.encrypt_file(p)

    def test_decrypt_file_disabled_returns_raw(self, tmp_path):
        plain_store = SecureStorage(_make_cfg(encrypted=False))
        p = tmp_path / "file.jpg"
        p.write_bytes(b"raw")
        assert plain_store.decrypt_file(p) == b"raw"
