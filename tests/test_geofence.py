import pytest
from autopilot.geofence import GeofenceMonitor


@pytest.fixture
def test_geofence():
    # Kare şeklinde test alanı
    # [41.100, 28.900] ile [41.110, 28.910] arası
    poly = [
        [41.100, 28.900],
        [41.100, 28.910],
        [41.110, 28.910],
        [41.110, 28.900]
    ]
    return GeofenceMonitor(
        polygon_coords=poly,
        min_alt_m=30.0,
        max_alt_m=120.0,
        warning_dist_m=30.0
    )


def test_geofence_inside(test_geofence):
    # Tam merkez nokta
    lat, lon, alt = 41.105, 28.905, 80.0
    assert test_geofence.is_inside_polygon(lat, lon) is True
    is_safe, msg = test_geofence.validate_position(lat, lon, alt)
    assert is_safe is True
    assert msg == "GÜVENLİ BÖLGE"


def test_geofence_outside(test_geofence):
    # Alan dışı nokta
    lat, lon, alt = 41.120, 28.920, 80.0
    assert test_geofence.is_inside_polygon(lat, lon) is False
    is_safe, msg = test_geofence.validate_position(lat, lon, alt)
    assert is_safe is False
    assert "İHLALİ" in msg


def test_geofence_altitude_limits(test_geofence):
    lat, lon = 41.105, 28.905
    # Çok düşük irtifa
    is_safe, msg = test_geofence.validate_position(lat, lon, 15.0)
    assert is_safe is False
    assert "DÜŞÜK İRTİFA" in msg

    # Çok yüksek irtifa
    is_safe, msg = test_geofence.validate_position(lat, lon, 140.0)
    assert is_safe is False
    assert "YÜKSEK İRTİFA" in msg
