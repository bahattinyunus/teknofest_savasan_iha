"""
ACAS / TCAS Hava Çarpışma Önleme Sistemi Birim Testleri.
"""

import pytest
from core.models import TelemetriPaketi, RakipIHABilgisi
from autopilot.collision_avoidance import (
    CollisionAvoidanceSystem,
    ACASAlertLevel,
    AvoidanceManeuver
)


def create_own_telemetry(lat=41.0, lon=29.0, alt=80.0, speed=20.0, heading=0.0):
    return TelemetriPaketi(
        takim_numarasi=1,
        IHA_enlem=lat,
        IHA_boylam=lon,
        IHA_irtifa=alt,
        IHA_dikilme=0.0,
        IHA_yonelme=heading,
        IHA_yatis=0.0,
        IHA_hiz=speed,
        IHA_batarya=85,
        IHA_otonom=1,
        IHA_kilitlenme=0,
        Hedef_merkez_X=0,
        Hedef_merkez_Y=0,
        Hedef_genislik=0,
        Hedef_yukseklik=0
    )


def test_acas_clear_when_far():
    acas = CollisionAvoidanceSystem()
    own = create_own_telemetry()
    # 500 metre uzakta rakip
    rival = RakipIHABilgisi(
        takim_numarasi=2,
        IHA_enlem=41.005,
        IHA_boylam=29.0,
        IHA_irtifa=80.0,
        IHA_dikilme=0.0,
        IHA_yonelme=180.0,
        IHA_yatis=0.0
    )
    advisory = acas.compute_advisory(own, [rival])
    assert advisory.alert_level == ACASAlertLevel.CLEAR
    assert advisory.maneuver == AvoidanceManeuver.MAINTAIN


def test_acas_traffic_advisory():
    acas = CollisionAvoidanceSystem(ta_distance_m=100.0)
    own = create_own_telemetry()
    # Yaklaşık 60 metre önde
    rival = RakipIHABilgisi(
        takim_numarasi=3,
        IHA_enlem=41.0005,
        IHA_boylam=29.0,
        IHA_irtifa=85.0,
        IHA_dikilme=0.0,
        IHA_yonelme=0.0, # Aynı yönde uçuyor, kafa kafaya değil
        IHA_yatis=0.0
    )
    threats = acas.assess_threats(own, [rival])
    assert len(threats) == 1
    assert threats[0].alert_level == ACASAlertLevel.TRAFFIC_ADVISORY


def test_acas_resolution_advisory_head_on():
    acas = CollisionAvoidanceSystem(ra_distance_m=35.0, ra_time_s=5.0)
    own = create_own_telemetry(heading=0.0) # Kuzeye uçuyor
    
    # 70 metre önde ve doğrudan bize (güneye 180 deg) uçan rakip
    # Saniyede 20+18 = 38 m/s yaklaşma hızı -> tau ~ 1.8 saniye (Çarpışma rotası!)
    rival = RakipIHABilgisi(
        takim_numarasi=4,
        IHA_enlem=41.0006, # ~66 metre kuzeyimizde
        IHA_boylam=29.0,
        IHA_irtifa=80.0,   # Aynı irtifada
        IHA_dikilme=0.0,
        IHA_yonelme=180.0, # Kafa kafaya bize geliyor
        IHA_yatis=0.0
    )
    advisory = acas.compute_advisory(own, [rival])
    assert advisory.alert_level == ACASAlertLevel.RESOLUTION_ADVISORY
    assert advisory.maneuver == AvoidanceManeuver.COORDINATED_ESCAPE
    assert advisory.target_heading_deg is not None
    assert advisory.target_altitude_m is not None
    # Kaçınma için irtifa veya yön değiştirilmiş olmalı
    assert advisory.target_altitude_m != own.IHA_irtifa or advisory.target_heading_deg != own.IHA_yonelme
