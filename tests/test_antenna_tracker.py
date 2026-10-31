import pytest
from core.models import TelemetriPaketi, ZamanBilgisi
from tools.antenna_tracker import GroundAntennaTracker


def test_antenna_tracker_due_north():
    # Home: [41.100, 28.900], UAV tam kuzeyde [41.110, 28.900]
    tracker = GroundAntennaTracker(home_lat=41.100, home_lon=28.900, home_alt_m=50.0)
    az, el, dist = tracker.calculate_tracking_angles(uav_lat=41.110, uav_lon=28.900, uav_alt_m=150.0)

    # Azimuth yaklaşık 0 derece (Kuzey)
    assert pytest.approx(az, 1.0) == 0.0 or pytest.approx(az, 1.0) == 360.0
    # Elevation pozitif (Uçak yüksekte)
    assert el > 0.0
    assert dist > 1000.0


def test_antenna_tracker_due_east():
    tracker = GroundAntennaTracker(home_lat=41.100, home_lon=28.900, home_alt_m=50.0)
    # UAV tam doğuda [41.100, 28.910]
    az, el, dist = tracker.calculate_tracking_angles(uav_lat=41.100, uav_lon=28.910, uav_alt_m=50.0)

    # Azimuth yaklaşık 90 derece (Doğu)
    assert pytest.approx(az, 1.0) == 90.0
    # İrtifa farkı yoksa elevation ~0
    assert pytest.approx(el, 1.0) == 0.0


def test_antenna_tracker_telemetry_and_pwm():
    tracker = GroundAntennaTracker()
    tel = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.102, IHA_boylam=28.902, IHA_irtifa=120.0,
        IHA_dikilme=0.0, IHA_yonelme=0.0, IHA_yatis=0.0, IHA_hiz=20.0,
        IHA_batarya=90, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=0, Hedef_merkez_Y=0, Hedef_genislik=0, Hedef_yukseklik=0,
        GPSSaati=ZamanBilgisi.now()
    )
    az, el, dist = tracker.update_from_telemetry(tel)
    az_pwm, el_pwm = tracker.get_servo_pwm()

    assert 1000 <= az_pwm <= 2000
    assert 1000 <= el_pwm <= 2000
