import pytest
from autopilot.wind_estimator import WindEstimator


def test_wind_estimator_no_wind():
    estimator = WindEstimator(filter_gain=1.0)
    # Rüzgarsız ortam: Yer hızı = Hava hızı (18 m/s), Rota = Yönelim (90 derece)
    speed, direction, crab = estimator.update(
        groundspeed_m_s=18.0,
        course_over_ground_deg=90.0,
        heading_deg=90.0,
        true_airspeed_m_s=18.0
    )
    assert pytest.approx(speed, 0.1) == 0.0
    assert pytest.approx(crab, 0.1) == 0.0


def test_wind_estimator_crosswind():
    estimator = WindEstimator(filter_gain=1.0)
    # Kuzeyden esen rüzgarda doğuya uçuş (Pusula yönelimi 90°, Yer izi rotası 95°)
    speed, direction, crab = estimator.update(
        groundspeed_m_s=18.0,
        course_over_ground_deg=95.0,
        heading_deg=90.0,
        true_airspeed_m_s=18.0
    )
    assert speed > 0.0
    assert crab != 0.0


def test_wind_crab_compensation():
    estimator = WindEstimator(filter_gain=1.0)
    # Kompanse edilmiş rota
    compensated = estimator.apply_crab_compensation(desired_heading_deg=180.0, groundspeed=18.0, heading=180.0)
    assert 0.0 <= compensated <= 360.0
