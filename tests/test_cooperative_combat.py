import time
import pytest
from autopilot.cooperative_combat import (
    CooperativeCombatGovernor,
    SwarmFormationType,
    TeamTacticMode,
    SwarmMemberState,
    TargetTrackInfo
)


def test_cooperative_formation_slots():
    gov = CooperativeCombatGovernor(own_id=1, is_initial_leader=True, formation_separation_m=40.0)
    gov.formation_type = SwarmFormationType.LINE_ABREAST

    leader_pos = (100.0, 100.0, -80.0)
    leader_heading = 0.0  # Kuzey

    slot1 = gov.calculate_formation_slot_ned(leader_pos, leader_heading, slot_index=1)
    slot2 = gov.calculate_formation_slot_ned(leader_pos, leader_heading, slot_index=2)

    # 1. Kanat sağda (+y / Doğu), 2. Kanat solda (-y / Batı)
    assert slot1[1] > leader_pos[1]
    assert slot2[1] < leader_pos[1]


def test_cooperative_target_allocation():
    gov = CooperativeCombatGovernor(own_id=1, is_initial_leader=True)
    
    # 2. İHA'yı ekle
    gov.update_member_heartbeat(SwarmMemberState(
        uav_id=2,
        is_leader=False,
        position_ned=(200.0, 200.0, -80.0),
        velocity_ned=(20.0, 0.0, 0.0),
        airspeed_mps=20.0,
        heading_deg=0.0
    ))

    targets = [
        TargetTrackInfo(target_id=101, position_ned=(10.0, 5.0, -80.0), velocity_ned=(18.0, 0.0, 0.0), airspeed_mps=18.0),
        TargetTrackInfo(target_id=102, position_ned=(195.0, 190.0, -80.0), velocity_ned=(18.0, 0.0, 0.0), airspeed_mps=18.0)
    ]

    allocations = gov.allocate_targets(targets)

    # UAV 1 hedef 101'e daha yakın, UAV 2 hedef 102'ye daha yakın olmalı
    assert allocations[1] == 101
    assert allocations[2] == 102


def test_cooperative_drag_and_bag_tactic():
    gov = CooperativeCombatGovernor(own_id=1, is_initial_leader=True)
    
    # Kanat uçağının kuyruğunda düşman olduğunu bildirelim
    gov.update_member_heartbeat(SwarmMemberState(
        uav_id=2,
        is_leader=False,
        position_ned=(50.0, 50.0, -80.0),
        velocity_ned=(20.0, 0.0, 0.0),
        airspeed_mps=20.0,
        heading_deg=0.0,
        is_being_pursued=True
    ))

    tactic, plan = gov.evaluate_drag_and_bag_tactic(own_pos=(0.0, 0.0, -100.0), own_vel=(25.0, 0.0, 0.0))
    
    assert tactic == TeamTacticMode.DRAG_AND_BAG
    assert plan["bait_uav"] == 2
    assert plan["shooter_uav"] == 1
    assert plan["shooter_action"] == "HIGH_PERCH_DIVE"
