import math
from core.ukf_nonlinear import UnscentedKalmanFilter3D


def test_ukf_nonlinear_ctrv_turning_target():
    ukf = UnscentedKalmanFilter3D()
    omega = math.radians(22.0)
    radius = 50.0
    dt = 0.1

    ukf.initialize(
        pos_ned_m=(0.0, -radius, -80.0),
        vel_ned_mps=(omega * radius, 0.0, 0.0),
        turn_rate_rad_s=omega
    )

    state = None
    for k in range(1, 25):
        t = k * dt
        n = radius * math.sin(omega * t)
        e = -radius * math.cos(omega * t)
        state = ukf.step(
            measured_pos_ned_m=(n, e, -80.0),
            own_pos_ned_m=(0.0, 0.0, -80.0),
            dt=dt,
            prediction_horizon_s=1.0
        )

    assert state is not None
    assert math.dist(state.pos_ned_m, (n, e, -80.0)) < 4.5
    assert state.turn_rate_deg_s > 8.0
    assert state.horizontal_speed_mps > 10.0
    assert state.covariance_trace > 0.0
