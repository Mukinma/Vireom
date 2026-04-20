import numpy as np

import vision.camera as camera_module


class _FakePicamera:
    def __init__(self, frame):
        self.frame = frame
        self.stream_names = []

    def capture_array(self, stream_name=None):
        self.stream_names.append(stream_name)
        return self.frame


class _FakeCapture:
    def __init__(self, frame):
        self.frame = frame

    def read(self):
        return True, self.frame.copy()


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


def test_apply_frame_orientation_no_flip(monkeypatch):
    original = np.array([[[1, 0, 0], [2, 0, 0], [3, 0, 0]]], dtype=np.uint8)

    stream = camera_module.CameraStream()
    monkeypatch.setattr(camera_module.config, "camera_flip_horizontal", False)

    frame = stream._apply_frame_orientation(original)

    np.testing.assert_array_equal(frame, original)


def test_apply_frame_orientation_with_horizontal_flip(monkeypatch):
    original = np.array([[[1, 0, 0], [2, 0, 0], [3, 0, 0]]], dtype=np.uint8)

    stream = camera_module.CameraStream()
    monkeypatch.setattr(camera_module.config, "camera_flip_horizontal", True)

    frame = stream._apply_frame_orientation(original)

    expected = np.array([[[3, 0, 0], [2, 0, 0], [1, 0, 0]]], dtype=np.uint8)
    np.testing.assert_array_equal(frame, expected)


def test_read_frame_opencv_aplica_flip_horizontal(monkeypatch):
    original = np.array([[[10, 0, 0], [20, 0, 0], [30, 0, 0]]], dtype=np.uint8)

    stream = camera_module.CameraStream()
    stream._use_picamera2 = False
    stream.cap = _FakeCapture(original)
    monkeypatch.setattr(camera_module.config, "camera_flip_horizontal", True)

    ok, frame = stream._read_frame()

    assert ok is True
    expected = np.array([[[30, 0, 0], [20, 0, 0], [10, 0, 0]]], dtype=np.uint8)
    np.testing.assert_array_equal(frame, expected)


def test_read_frame_picamera2_aplica_flip_horizontal(monkeypatch):
    original = np.array([[[7, 0, 0], [8, 0, 0], [9, 0, 0]]], dtype=np.uint8)

    stream = camera_module.CameraStream()
    stream._use_picamera2 = True
    stream._picam = _FakePicamera(original)
    monkeypatch.setattr(camera_module.config, "camera_flip_horizontal", True)

    ok, frame = stream._read_frame()

    assert ok is True
    expected = np.array([[[9, 0, 0], [8, 0, 0], [7, 0, 0]]], dtype=np.uint8)
    np.testing.assert_array_equal(frame, expected)
