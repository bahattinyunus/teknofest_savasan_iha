"""
GNSS-Denied Anti-Jamming & Dead Reckoning Birim Testleri.
"""

import pytest
from autopilot.gnss_denied_nav import (
    GNSSDeniedNavigator,
    GNSSStatus,
    GNSSSample
)


def test_gnss_navigator_nominal():
    nav = GNSSDeniedNavigator()
    sample = GNSSSample(
        lat=41.1000,
        lon=28.9000,
        alt=80.0,
        speed_mps=20.0,
        heading_deg=0.0,
        hdop=0.9,
        satellites=14,
        timestamp=100.0
    )
    
    # 5 ardışık geçerli örnek
    for i in range(5):
        sample.timestamp = 100.0 + i * 0.1
        lat, lon, alt, status = nav.update(
            gnss=sample,
            airspeed_mps=20.0,
            heading_deg=0.0,
            dt=0.1
        )
    assert status == GNSSStatus.NOMINAL
    assert lat == pytest.approx(41.1000, abs=1e-5)
    assert lon == pytest.approx(28.9000, abs=1e-5)
    assert alt == pytest.approx(80.0, abs=0.1)


def test_gnss_navigator_jamming_dead_reckoning():
    nav = GNSSDeniedNavigator()
    # Başlangıçta geçerli konum ver
    init_sample = GNSSSample(
        lat=41.1000,
        lon=28.9000,
        alt=80.0,
        speed_mps=20.0,
        heading_deg=0.0, # Kuzeye uçuyor
        hdop=1.0,
        satellites=12,
        timestamp=1.0
    )
    for _ in range(5):
        nav.update(init_sample, airspeed_mps=20.0, heading_deg=0.0, dt=0.1)
        
    # GPS sinyali tamamen kesildi (None / Jamming)
    # 10 saniye boyunca 20 m/s hızla kuzeye uçuyor
    for _ in range(100): # 100 x 0.1s = 10.0s
        lat, lon, alt, status = nav.update(
            gnss=None,
            airspeed_mps=20.0,
            heading_deg=0.0, # Kuzey
            dt=0.1
        )
        
    assert status in (GNSSStatus.JAMMED, GNSSStatus.DEAD_RECKONING)
    # 10 saniyede 200 metre kuzeye gitmeli -> 200m / 111139m/deg ~ 0.0018 deg enlem artışı
    assert lat > 41.1000
    assert lat == pytest.approx(41.1000 + (200.0 / 111139.0), abs=1e-4)
    assert lon == pytest.approx(28.9000, abs=1e-5) # Doğu sapması yok
    assert nav.get_estimated_uncertainty_m() > 5.0 # Belirsizlik zamanla büyümeli


def test_gnss_navigator_spoofing_detection():
    nav = GNSSDeniedNavigator(max_position_jump_m=30.0)
    init_sample = GNSSSample(
        lat=41.1000,
        lon=28.9000,
        alt=80.0,
        speed_mps=20.0,
        heading_deg=0.0,
        timestamp=1.0
    )
    for _ in range(5):
        nav.update(init_sample, airspeed_mps=20.0, heading_deg=0.0, dt=0.1)
        
    # Aniden 10 kilometre öteye sıçrayan sahte GPS sinyali (Spoofing saldırısı)
    spoofed_sample = GNSSSample(
        lat=41.1900, # ~10 km kuzey
        lon=28.9000,
        alt=80.0,
        speed_mps=20.0,
        heading_deg=0.0,
        hdop=0.8,
        satellites=16,
        timestamp=1.6
    )
    lat, lon, alt, status = nav.update(
        gnss=spoofed_sample,
        airspeed_mps=20.0,
        heading_deg=0.0,
        dt=0.1
    )
    # Sıçrama reddedilmeli, sahte konuma geçilmemeli!
    assert status == GNSSStatus.SPOOFED
    assert lat < 41.1100 # 10 km öteye sıçramadı
