"""
15-Durumlu Havacılık Genişletilmiş Kalman Filtresi (Aerospace EKF) Birim Testleri
"""

import pytest
import numpy as np
import math
from core.aerospace_ekf import AerospaceEKF
from core.models import EKFState6DOF


class TestAerospaceEKF:

    @pytest.fixture
    def ekf(self):
        f = AerospaceEKF()
        f.initialize_state(
            pos_ned=(10.0, 20.0, -50.0),
            vel_ned=(25.0, 0.0, 0.0),
            euler_deg=(0.0, 0.0, 45.0)
        )
        return f

    def test_initialization(self, ekf):
        state = ekf.get_state()
        assert isinstance(state, EKFState6DOF)
        assert pytest.approx(state.pos_ned_m[0]) == 10.0
        assert pytest.approx(state.pos_ned_m[1]) == 20.0
        assert pytest.approx(state.pos_ned_m[2]) == -50.0
        assert pytest.approx(state.vel_ned_mps[0]) == 25.0
        assert pytest.approx(state.euler_deg[2], abs=1.0) == 45.0

    def test_quaternion_euler_roundtrip(self):
        # 30 derece roll, 10 derece pitch, 120 derece yaw
        r, p, y = 30.0, 10.0, 120.0
        q = AerospaceEKF.euler_to_quat(r, p, y)
        r_out, p_out, y_out = AerospaceEKF.quat_to_euler(q)
        assert pytest.approx(r, abs=0.01) == r_out
        assert pytest.approx(p, abs=0.01) == p_out
        assert pytest.approx(y, abs=0.01) == y_out

    def test_predict_strapdown_propagation(self, ekf):
        # Düz uçuşta yerçekimi gövde z ekseninde -g olarak hissedilir (1g askıda)
        accel_body = (0.0, 0.0, -ekf.GRAVITY)
        gyro_body = (0.0, 0.0, 0.0)

        p_before = ekf.x[0:3].copy()
        ekf.predict(accel_body_mps2=accel_body, gyro_body_rads=gyro_body, dt=0.05)
        p_after = ekf.x[0:3]

        # V_N = 25 m/s olduğundan 0.05 sn'de yaklaşık 1.25 m ileri gitmeli
        dx = p_after[0] - p_before[0]
        assert dx > 0.5

    def test_gnss_update_normal(self, ekf):
        # Filtre durumuna yakın bir GNSS ölçümü
        gnss_pos = (12.0, 21.0, -49.5)
        gnss_vel = (24.8, 0.2, 0.0)

        updated = ekf.update_gnss(pos_ned_m=gnss_pos, vel_ned_mps=gnss_vel)
        assert updated is True

        state = ekf.get_state()
        assert abs(state.pos_ned_m[0] - 12.0) < 5.0

    def test_gnss_update_outlier_gating_rejection(self, ekf):
        # Fizik dışı aşırı uzak bir GNSS verisi (Mahalanobis kapılamasıyla elenmeli)
        spoofed_pos = (5000.0, 5000.0, -500.0)
        spoofed_vel = (150.0, 150.0, 0.0)

        updated = ekf.update_gnss(pos_ned_m=spoofed_pos, vel_ned_mps=spoofed_vel, gating_threshold=18.0)
        assert updated is False  # Outlier reddedilmeli!

    def test_barometer_update(self, ekf):
        # Barometre -55 metre (55 metre irtifa) ölçüyor
        updated = ekf.update_barometer(altitude_down_m=-55.0)
        assert updated is True
        state = ekf.get_state()
        assert state.pos_ned_m[2] < -50.0

    def test_visual_odometry_update(self, ekf):
        # Görsel odometri hız ölçümü
        vo_vel = (24.5, 0.1, -0.2)
        updated = ekf.update_visual_odometry(vel_ned_mps=vo_vel)
        assert updated is True
