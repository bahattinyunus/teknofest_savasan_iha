import time
import pytest
from core.models import HedefKutusu
from core.threat_library import AirframeType, ThreatLevel
from vision.threat_classifier import ThreatClassifierRWR, RWRStatus


def test_classify_airframe_aspect_ratio():
    classifier = ThreatClassifierRWR()

    # Sabit kanat: Geniş en-boy oranı (w/h = 2.0)
    fixed_box = HedefKutusu(class_id=0, class_name="iha", conf=0.9, x1=100, y1=100, x2=300, y2=200, track_id=1)
    airframe_fixed, conf_fixed = classifier.classify_target(fixed_box, estimated_speed_mps=24.0)
    assert airframe_fixed == AirframeType.FIXED_WING_FIGHTER
    assert conf_fixed > 0.5

    # Döner kanat: Kareye yakın (w/h = 1.0)
    rotary_box = HedefKutusu(class_id=0, class_name="iha", conf=0.9, x1=100, y1=100, x2=200, y2=200, track_id=2)
    airframe_rotary, conf_rotary = classifier.classify_target(rotary_box, estimated_speed_mps=14.0)
    assert airframe_rotary == AirframeType.ROTARY_WING_KAMIKAZE
    assert conf_rotary > 0.5



def test_rwr_threat_evaluation():
    classifier = ThreatClassifierRWR(lock_threat_time_threshold_s=0.2)

    # 1. Düşman uzakta ve nötr
    assessment_clear = classifier.evaluate_threat(
        target_id=1,
        airframe_type=AirframeType.FIXED_WING_FIGHTER,
        range_m=120.0,
        ata_deg=10.0,
        aspect_angle_deg=20.0
    )
    assert assessment_clear.threat_level == ThreatLevel.LOW
    assert assessment_clear.rwr_status == RWRStatus.CLEAR

    # 2. Düşman arkamızda (AA = 160) ve menzilde (30m)
    assessment_track = classifier.evaluate_threat(
        target_id=2,
        airframe_type=AirframeType.FIXED_WING_FIGHTER,
        range_m=30.0,
        ata_deg=160.0,
        aspect_angle_deg=160.0
    )
    assert assessment_track.rwr_status in (RWRStatus.TRACK, RWRStatus.LOCK_WARNING)

    # 0.25 saniye sonra tekrar sorguladığımızda LOCK_WARNING alarmı vermeli
    time.sleep(0.25)
    assessment_warning = classifier.evaluate_threat(
        target_id=2,
        airframe_type=AirframeType.FIXED_WING_FIGHTER,
        range_m=30.0,
        ata_deg=160.0,
        aspect_angle_deg=160.0
    )
    assert assessment_warning.rwr_status == RWRStatus.LOCK_WARNING
    assert assessment_warning.threat_level == ThreatLevel.CRITICAL
    assert assessment_warning.evasive_break_dir in ("LEFT", "RIGHT")
