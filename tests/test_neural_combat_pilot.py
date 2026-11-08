import math
import pytest
from autopilot.neural_combat_pilot import (
    NeuralCombatPilot,
    CombatRole,
    TacticalManeuver,
    CombatStateTensor
)


def test_neural_pilot_state_tensor_geometry():
    pilot = NeuralCombatPilot()
    
    # Ownship (0, 0, -50), Target (50, 0, -50) -> Hedef tam burnumuzun önünde (50m)
    own_pos = (0.0, 0.0, -50.0)
    own_vel = (25.0, 0.0, 0.0)
    tgt_pos = (50.0, 0.0, -50.0)
    tgt_vel = (20.0, 0.0, 0.0)

    tensor = pilot.compute_state_tensor(
        own_pos_ned=own_pos,
        own_vel_ned=own_vel,
        target_pos_ned=tgt_pos,
        target_vel_ned=tgt_vel,
        geofence_dist_m=80.0
    )

    assert math.isclose(tensor.range_m, 50.0, abs_tol=0.5)
    assert tensor.ata_deg < 5.0          # Burnumuz tam hedefe bakıyor
    assert tensor.aspect_angle_deg < 5.0 # Hedefin tam arkasındayız (6 hizası)
    assert tensor.closure_rate_mps > 0   # 25 m/s vs 20 m/s -> yaklaşıyoruz
    assert tensor.wez_score > 0.5        # WEZ skoru yüksek


def test_neural_pilot_offensive_pure_and_lead_pursuit():
    pilot = NeuralCombatPilot()
    
    # Offense senaryosu
    tensor = CombatStateTensor(
        range_m=35.0,
        closure_rate_mps=2.0,
        ata_deg=10.0,
        aspect_angle_deg=20.0,
        relative_altitude_m=0.0,
        own_airspeed_mps=24.0,
        target_airspeed_mps=22.0,
        energy_advantage_m=10.0,
        wez_score=0.85,
        geofence_margin_m=80.0
    )

    cmd = pilot.select_maneuver(
        state=tensor,
        own_pos_ned=(0.0, 0.0, -50.0),
        target_pos_ned=(35.0, 0.0, -50.0),
        target_vel_ned=(22.0, 0.0, 0.0)
    )

    assert cmd.role == CombatRole.OFFENSIVE
    assert cmd.maneuver_name == TacticalManeuver.PURE_PURSUIT
    assert cmd.throttle_cmd > 0.5


def test_neural_pilot_defensive_break():
    pilot = NeuralCombatPilot()
    
    # Düşman arkamızda (AA = 160) ve menzil 40m
    tensor = CombatStateTensor(
        range_m=40.0,
        closure_rate_mps=5.0,
        ata_deg=160.0,
        aspect_angle_deg=160.0,
        relative_altitude_m=0.0,
        own_airspeed_mps=22.0,
        target_airspeed_mps=26.0,
        energy_advantage_m=-20.0,
        wez_score=0.1,
        geofence_margin_m=70.0
    )

    cmd = pilot.select_maneuver(
        state=tensor,
        own_pos_ned=(0.0, 0.0, -50.0),
        target_pos_ned=(-40.0, 0.0, -50.0),
        target_vel_ned=(26.0, 0.0, 0.0)
    )

    assert cmd.role == CombatRole.DEFENSIVE
    assert cmd.maneuver_name == TacticalManeuver.DEFENSIVE_BREAK
    assert cmd.g_load_target >= 3.0
    assert abs(cmd.target_roll_deg) > 40.0


def test_neural_pilot_high_yoyo_on_overshoot():
    pilot = NeuralCombatPilot()
    
    # Çok yakınız (18m) ve aşırı hızlı yaklaşıyoruz (10 m/s) -> Overshoot riski!
    tensor = CombatStateTensor(
        range_m=18.0,
        closure_rate_mps=10.0,
        ata_deg=5.0,
        aspect_angle_deg=10.0,
        relative_altitude_m=0.0,
        own_airspeed_mps=30.0,
        target_airspeed_mps=20.0,
        energy_advantage_m=25.0,
        wez_score=0.7,
        geofence_margin_m=100.0
    )

    cmd = pilot.select_maneuver(
        state=tensor,
        own_pos_ned=(0.0, 0.0, -50.0),
        target_pos_ned=(18.0, 0.0, -50.0),
        target_vel_ned=(20.0, 0.0, 0.0)
    )

    assert cmd.maneuver_name == TacticalManeuver.HIGH_YOYO
    assert cmd.target_pitch_deg > 15.0  # Tırmanarak hızı kes
