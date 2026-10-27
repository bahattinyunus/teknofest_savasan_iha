import pytest
from core.models import HedefKutusu
from vision.latency_compensator import DelayedKalmanFilter


def test_delayed_kalman_filter_initialization():
    dkf = DelayedKalmanFilter()
    x, y = dkf.update(100.0, 200.0, timestamp=1.0)
    assert x == 100.0
    assert y == 200.0
    assert dkf.is_initialized is True


def test_delayed_kalman_filter_velocity_prediction():
    dkf = DelayedKalmanFilter()
    # Hedef 100 piksel/sn hızla X ekseninde ilerliyor
    dkf.update(100.0, 100.0, timestamp=1.0)
    dkf.update(110.0, 100.0, timestamp=1.1)  # 0.1 sn sonra 10 piksel -> v ~ 100 px/s
    dkf.update(120.0, 100.0, timestamp=1.2)

    # 35 ms (0.035 s) sonrasını tahmin et
    pred_x, pred_y = dkf.predict_future(latency_sec=0.035)

    # pred_x son ölçüm olan 120'den ileride olmalı
    assert pred_x > 120.0
    assert pytest.approx(pred_y, 1.0) == 100.0


def test_box_latency_compensation():
    dkf = DelayedKalmanFilter()
    box1 = HedefKutusu(x1=100, y1=100, x2=200, y2=200, track_id=1)
    box2 = HedefKutusu(x1=115, y1=100, x2=215, y2=200, track_id=1)

    dkf.compensate_box(box1, latency_sec=0.035, timestamp=1.0)
    compensated = dkf.compensate_box(box2, latency_sec=0.035, timestamp=1.1)

    # Kompanse edilmiş kutu merkez_x'i son ölçümden ileride olmalı
    assert compensated.merkez_x > box2.merkez_x
