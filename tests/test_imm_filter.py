import math
from core.imm_filter import InteractingMultipleModelFilter, FlightModelMode


def test_imm_filter_straight_constant_velocity():
    imm = InteractingMultipleModelFilter(target_id=7, turn_rate_deg_s=30.0, measurement_noise_m=0.8)
    imm.initialize(pos_ned_m=(0.0, 0.0, -80.0), vel_ned_mps=(20.0, 0.0, 0.0))

    dt = 0.1
    est = None
    for k in range(1, 20):
        pos = (20.0 * k * dt, 0.0, -80.0)
        est = imm.step(measured_pos_ned_m=pos, dt=dt, prediction_horizon_s=1.0)

    assert est is not None
    assert est.target_id == 7
    assert est.dominant_mode == FlightModelMode.CONSTANT_VELOCITY
    assert abs(est.vel_ned_mps[0] - 20.0) < 2.5
    assert abs(est.predicted_pos_ned_m[0] - (est.pos_ned_m[0] + 20.0)) < 4.0


def test_imm_filter_coordinated_turn_detection():
    imm = InteractingMultipleModelFilter(target_id=3, turn_rate_deg_s=28.0, measurement_noise_m=0.5)
    omega = math.radians(28.0)
    radius = 45.0
    dt = 0.1

    imm.initialize(pos_ned_m=(0.0, -radius, -75.0), vel_ned_mps=(omega * radius, 0.0, 0.0))
    est = None
    for k in range(1, 30):
        t = k * dt
        n = radius * math.sin(omega * t)
        e = -radius * math.cos(omega * t)
        est = imm.step(measured_pos_ned_m=(n, e, -75.0), dt=dt, prediction_horizon_s=1.0)

    assert est is not None
    # Sağa dönüş veya ivmeli manevra olasılığı düz uçuştan yüksek olmalı
    turn_prob = (
        est.model_probabilities[FlightModelMode.COORDINATED_TURN_RIGHT.value]
        + est.model_probabilities[FlightModelMode.CONSTANT_ACCELERATION.value]
    )
    assert turn_prob > 0.55
    assert est.estimated_g_load > 1.05


def test_imm_filter_future_horizon_prediction():
    imm = InteractingMultipleModelFilter(target_id=1)
    imm.initialize(pos_ned_m=(100.0, 50.0, -60.0), vel_ned_mps=(15.0, -5.0, 0.0))
    est = imm.step(measured_pos_ned_m=(101.5, 49.5, -60.0), dt=0.1, prediction_horizon_s=2.0)

    pred_2s = imm.predict_future_position(2.0)
    assert pred_2s[0] > est.pos_ned_m[0] + 15.0
    assert pred_2s[1] < est.pos_ned_m[1] - 4.0
    assert est.position_uncertainty_m > 0.0
