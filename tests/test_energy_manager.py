"""
John Boyd Enerji-Manevra (E-M) Teorisi ve Uçuş Zarfı Birim Testleri
"""

import pytest
import math
from autopilot.energy_manager import EnergyManeuverabilityGovernor
from core.models import EnergyState


class TestEnergyManager:

    @pytest.fixture
    def governor(self):
        return EnergyManeuverabilityGovernor(
            mass_kg=4.5,
            wing_area_m2=0.52,
            cd0=0.028,
            induced_drag_k=0.045,
            max_thrust_n=38.0,
            max_load_factor_g=4.5,
            cl_max=1.25,
            stall_speed_mps=13.0
        )

    def test_specific_energy_calculation(self, governor):
        # He = h + V^2 / 2g
        # h = 50 m, V = 20 m/s -> He = 50 + 400 / 19.6133 = 50 + 20.394 = 70.39 m
        he = governor.calculate_specific_energy(altitude_m=50.0, airspeed_mps=20.0)
        expected = 50.0 + (20.0 ** 2) / (2.0 * governor.GRAVITY)
        assert pytest.approx(he, rel=1e-3) == expected
        assert he > 50.0

    def test_corner_velocity(self, governor):
        # V_c = sqrt(2 * n_max * W / (rho * S * C_L_max))
        vc = governor.calculate_corner_velocity()
        assert 18.0 < vc < 35.0  # Tipik Savaşan İHA için mantıklı köşe hızı aralığı
        assert vc > governor.stall_speed

    def test_specific_excess_power_positive_and_negative(self, governor):
        # Düşük hız ve tam gaz -> Ps pozitif olmalı (tırmanma/hızlanma gücü var)
        ps_full = governor.calculate_specific_excess_power(
            altitude_m=50.0,
            airspeed_mps=18.0,
            throttle_ratio=1.0,
            load_factor_g=1.0
        )
        assert ps_full > 0.0

        # Çok yüksek hız veya yüksek G dönüşü ve sıfır gaz -> Ps negatif olmalı
        ps_bleed = governor.calculate_specific_excess_power(
            altitude_m=50.0,
            airspeed_mps=35.0,
            throttle_ratio=0.0,
            load_factor_g=3.5
        )
        assert ps_bleed < 0.0

    def test_turn_performance(self, governor):
        turn_rate, radius = governor.calculate_turn_performance(airspeed_mps=20.0, load_factor_g=3.0)
        assert turn_rate > 0.0
        assert radius > 5.0
        # Daha yüksek G daha yüksek dönüş hızı ve daha dar yarıçap üretmeli
        high_rate, small_radius = governor.calculate_turn_performance(airspeed_mps=20.0, load_factor_g=4.0)
        assert high_rate > turn_rate
        assert small_radius < radius

    def test_sustained_turn_rate(self, governor):
        sust_rate = governor.calculate_sustained_turn_rate(airspeed_mps=22.0, altitude_m=50.0)
        assert sust_rate >= 0.0

    def test_combat_energy_evaluation_stall_danger(self, governor):
        # Stall hızının hemen altı veya çok düşük irtifa -> Stall koruma devreye girmeli
        state = governor.evaluate_combat_energy(
            own_alt_m=10.0,
            own_airspeed_mps=12.0  # Stall speed = 13.0 m/s
        )
        assert isinstance(state, EnergyState)
        assert state.perdovites_koruma_aktif is True
        assert state.onerilen_taktik == "STALL_RECOVERY_PULL_DOWN_BOOST"

    def test_combat_energy_evaluation_tactical_advantage(self, governor):
        # Yüksek irtifa ve yüksek hız avantajı -> 2-Circle Rate Fight önerilmeli
        state = governor.evaluate_combat_energy(
            own_alt_m=120.0,
            own_airspeed_mps=28.0,
            target_alt_m=40.0,
            target_airspeed_mps=18.0
        )
        assert state.enerji_avantaji_m > 40.0
        assert state.onerilen_taktik == "RATE_FIGHT_2_CIRCLE"

    def test_combat_energy_evaluation_tactical_disadvantage(self, governor):
        # Düşük enerji dezavantajı -> 1-Circle Radius Fight önerilmeli
        state = governor.evaluate_combat_energy(
            own_alt_m=35.0,
            own_airspeed_mps=16.0,
            target_alt_m=100.0,
            target_airspeed_mps=26.0
        )
        assert state.enerji_avantaji_m < -25.0
        assert state.onerilen_taktik == "RADIUS_FIGHT_1_CIRCLE"
