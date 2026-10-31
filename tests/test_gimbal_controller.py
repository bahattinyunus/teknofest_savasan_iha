import pytest
from core.models import HedefKutusu
from vision.gimbal_controller import GimbalController


def test_gimbal_controller_centering():
    gimbal = GimbalController()
    # Hedef tam merkezde: 640, 360 (1280x720)
    center_box = HedefKutusu(x1=540, y1=260, x2=740, y2=460)
    pan, tilt = gimbal.compute_gimbal_angles(center_box, 1280, 720)
    assert abs(pan) < 1.0
    assert abs(tilt) < 1.0


def test_gimbal_controller_pan_right():
    gimbal = GimbalController()
    # Hedef sağ tarafta (x=1000)
    right_box = HedefKutusu(x1=950, y1=310, x2=1050, y2=410)
    pan, tilt = gimbal.compute_gimbal_angles(right_box, 1280, 720)
    # Pan açısı pozitif olmalı (sağa yönelme)
    assert pan > 0.0


def test_gimbal_controller_limits():
    gimbal = GimbalController(pan_limit_deg=45.0, tilt_min_deg=-30.0, tilt_max_deg=20.0)
    # Çok uç bir hedef (x=5000, y=-2000)
    extreme_box = HedefKutusu(x1=4900, y1=-2100, x2=5100, y2=-1900)
    for _ in range(20):
        pan, tilt = gimbal.compute_gimbal_angles(extreme_box, 1280, 720)

    assert pan <= 45.0
    assert -30.0 <= tilt <= 20.0


def test_gimbal_mavlink_mount_command():
    gimbal = GimbalController()
    gimbal.current_pan_deg = 15.5
    gimbal.current_tilt_deg = -10.2
    pitch, roll, yaw = gimbal.get_mavlink_mount_command()
    assert pitch == -1020
    assert roll == 0
    assert yaw == 1550
