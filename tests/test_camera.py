import numpy as np
import time

import vision.camera as camera_module


class _FakePicamera:
    def __init__(self, frame):
        self.frame = frame
        self.stream_names = []

    def capture_array(self, stream_name=None):
        self.stream_names.append(stream_name)
        return self.frame


class _AliveThread:
    def is_alive(self):
        return True


class _OpenedCapture:
    def isOpened(self):
        return True


def test_read_picamera2_usa_stream_main_y_devuelve_copia_estable():
    original = np.zeros((2, 2, 3), dtype=np.uint8)
    original[:, :, 0] = 10
    original[:, :, 1] = 20
    original[:, :, 2] = 30

    stream = camera_module.CameraStream()
    fake = _FakePicamera(original)
    stream._picam = fake

    ok, frame = stream._read_picamera2()

    assert ok is True
    assert fake.stream_names == ["main"]
    assert frame is not original
    np.testing.assert_array_equal(frame[0, 0], np.array([10, 20, 30], dtype=np.uint8))

    original[:, :, :] = 255
    np.testing.assert_array_equal(frame[0, 0], np.array([10, 20, 30], dtype=np.uint8))


def test_read_picamera2_convierte_bgra_a_bgr():
    original = np.array([[[5, 15, 25, 255]]], dtype=np.uint8)

    stream = camera_module.CameraStream()
    stream._picam = _FakePicamera(original)

    ok, frame = stream._read_picamera2()

    assert ok is True
    assert frame.shape == (1, 1, 3)
    np.testing.assert_array_equal(frame[0, 0], np.array([5, 15, 25], dtype=np.uint8))


def test_get_jpeg_no_codifica_frame_existente_fuera_del_hilo_de_captura():
    stream = camera_module.CameraStream()
    stream.running = True
    with stream.frame_cond:
        stream.frame = np.full((4, 4, 3), 80, dtype=np.uint8)
        stream.jpeg_frame = None
        stream.frame_seq = 1
        stream.stream_frame_seq = 0

    def fail_encode(_frame):
        raise AssertionError("get_jpeg no debe codificar JPEG")

    stream._encode_stream_frame = fail_encode

    jpeg, seq = stream.get_jpeg(last_seq=0, timeout=0)

    assert seq == 0
    assert jpeg is None
    with stream.frame_cond:
        assert stream.jpeg_frame is None


def test_capture_loop_codifica_frame_jpeg_cuando_hay_cliente_registrado():
    stream = camera_module.CameraStream()
    stream.running = True
    stream._capture_generation = 1
    stream._jpeg_clients = 1
    frame = np.full((4, 4, 3), 120, dtype=np.uint8)

    stream._camera_lost = lambda: False

    def read_once():
        stream.running = False
        return True, frame

    stream._read_frame = read_once

    stream._capture_loop(generation=1)

    assert stream.frame_seq == 1
    assert stream.stream_frame_seq == 1
    assert stream.jpeg_frame is not None
    assert stream.jpeg_frame.startswith(b"\xff\xd8")
    assert stream.get_stream_content_type() == "image/jpeg"


def test_capture_loop_limita_fps_de_stream_sin_frenar_captura(monkeypatch):
    monkeypatch.setattr(camera_module.config, "max_fps", 120)
    monkeypatch.setattr(camera_module.config, "stream_fps", 1)

    stream = camera_module.CameraStream()
    stream.running = True
    stream._capture_generation = 1
    stream._jpeg_clients = 1
    frame = np.full((4, 4, 3), 120, dtype=np.uint8)
    reads = 0

    stream._camera_lost = lambda: False

    def read_twice():
        nonlocal reads
        reads += 1
        if reads >= 2:
            stream.running = False
        return True, frame

    stream._read_frame = read_twice

    stream._capture_loop(generation=1)

    assert stream.frame_seq == 2
    assert stream.stream_frame_seq == 1


def test_get_frame_seq_devuelve_secuencia_actual():
    stream = camera_module.CameraStream()
    with stream.frame_cond:
        stream.frame_seq = 7

    assert stream.get_frame_seq() == 7


def test_get_stream_frame_seq_devuelve_secuencia_de_stream_actual():
    stream = camera_module.CameraStream()
    with stream.frame_cond:
        stream.stream_frame_seq = 5

    assert stream.get_stream_frame_seq() == 5


def test_get_snapshot_frame_codifica_ultimo_frame_jpeg():
    stream = camera_module.CameraStream()
    with stream.frame_cond:
        stream.frame = np.full((2, 2, 3), 50, dtype=np.uint8)
        stream.frame_seq = 1

    frame, content_type = stream.get_snapshot_frame()

    assert content_type == "image/jpeg"
    assert frame is not None
    assert frame.startswith(b"\xff\xd8")


def test_get_jpeg_usa_secuencia_de_stream_y_no_la_de_captura():
    stream = camera_module.CameraStream()
    stream.running = True
    with stream.frame_cond:
        stream.frame_seq = 10
        stream.stream_frame_seq = 2
        stream.jpeg_frame = b"\xff\xd8new"

    jpeg, seq = stream.get_jpeg(last_seq=2, timeout=0)
    assert jpeg is None
    assert seq == 2

    jpeg, seq = stream.get_jpeg(last_seq=1, timeout=0)
    assert jpeg == b"\xff\xd8new"
    assert seq == 2


def test_stop_limpia_buffers_y_puede_preservar_clientes_jpeg():
    stream = camera_module.CameraStream()
    stream.running = True
    stream.started_at = time.time()
    stream.last_frame_time = time.time()
    stream.capture_fps = 12.0
    stream._fps_counter = 5
    stream._jpeg_clients = 2
    with stream.frame_cond:
        stream.frame = np.zeros((2, 2, 3), dtype=np.uint8)
        stream.jpeg_frame = b"old-jpeg"
        stream.stream_frame_seq = 9

    stream.stop(reset_clients=False)

    assert stream.running is False
    assert stream.frame is None
    assert stream.jpeg_frame is None
    assert stream.stream_frame_seq == 9
    assert stream.last_frame_time == 0.0
    assert stream.started_at == 0.0
    assert stream.capture_fps == 0.0
    assert stream._fps_counter == 0
    assert stream._jpeg_clients == 2


def test_ensure_running_reinicia_cuando_el_frame_esta_congelado():
    stream = camera_module.CameraStream()
    stream.running = True
    stream.thread = _AliveThread()
    stream.cap = _OpenedCapture()
    stream.started_at = time.time() - 20
    stream.last_frame_time = time.time() - 20
    calls = []

    def fake_restart(reason):
        calls.append(reason)
        return True

    stream.restart = fake_restart

    assert stream.ensure_running() is True
    assert calls == ["frame_stale"]
