import math
import numpy as np
from autopilot.mesh_datalink import TacticalMeshDatalink


def test_mesh_passive_3d_triangulation_accuracy():
    true_target_ned = np.array([140.0, 65.0, -85.0], dtype=np.float64)
    obs_positions = [
        (0.0, 0.0, -80.0),
        (0.0, 120.0, -90.0),
        (60.0, 60.0, -75.0),
    ]
    bearings = []
    for obs in obs_positions:
        vec = true_target_ned - np.array(obs, dtype=np.float64)
        vec = vec / np.linalg.norm(vec)
        bearings.append((float(vec[0]), float(vec[1]), float(vec[2])))

    res = TacticalMeshDatalink.triangulate_target_3d(
        target_id=99,
        observer_positions_ned=obs_positions,
        bearing_unit_vectors_ned=bearings,
        observer_ids=[1, 2, 3]
    )

    assert res.target_id == 99
    assert math.dist(res.estimated_pos_ned_m, tuple(true_target_ned)) < 0.1
    assert res.triangulation_error_m < 0.05
    assert res.observing_uav_ids == [1, 2, 3]


def test_mesh_cbba_multi_target_conflict_free_allocation():
    uav_pos = {
        1: (0.0, 0.0, -80.0),
        2: (0.0, 200.0, -80.0),
        3: (150.0, 100.0, -80.0),
    }
    uav_vel = {
        1: (22.0, 0.0, 0.0),
        2: (22.0, 0.0, 0.0),
        3: (22.0, 0.0, 0.0),
    }
    target_pos = {
        101: (45.0, 5.0, -80.0),     # İHA-1'in tam önünde
        102: (50.0, 195.0, -80.0),   # İHA-2'nin tam önünde
        103: (195.0, 100.0, -80.0),  # İHA-3'ün tam önünde
    }

    alloc = TacticalMeshDatalink.run_cbba_target_allocation(
        uav_positions_ned=uav_pos,
        uav_velocities_ned=uav_vel,
        target_positions_ned=target_pos
    )

    assert len(alloc.uav_to_target) == 3
    assert len(set(alloc.uav_to_target.values())) == 3  # Çakışmasız birebir eşleşme
    assert alloc.uav_to_target[1] == 101
    assert alloc.uav_to_target[2] == 102
    assert alloc.uav_to_target[3] == 103
    assert alloc.total_swarm_utility > 200.0


def test_mesh_packet_broadcast_and_link_quality():
    node1 = TacticalMeshDatalink(own_uav_id=1, max_comm_range_m=1000.0, base_packet_loss_rate=0.0, seed=1)
    node2 = TacticalMeshDatalink(own_uav_id=2, max_comm_range_m=1000.0, base_packet_loss_rate=0.0, seed=2)

    pkt = node1.broadcast_state(pos_ned_m=(10.0, 20.0, -80.0), vel_ned_mps=(20.0, 0.0, 0.0), allocated_target_id=5)
    accepted = node2.receive_peer_packet(pkt, own_pos_ned=(100.0, 50.0, -80.0), jamming_intensity=0.1)

    assert accepted is True
    assert 2 not in node1.peer_states
    assert 1 in node2.peer_states
    assert node2.peer_states[1].allocated_target_id == 5
