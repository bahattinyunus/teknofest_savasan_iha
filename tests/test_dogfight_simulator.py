"""
İt Dalaşı Simülatörü Birim Testleri.
"""

import pytest
from simulation.dogfight_simulator import (
    DogfightSimulator,
    TargetBehavior,
    AircraftState
)


def test_dogfight_simulator_initialization():
    sim = DogfightSimulator()
    assert sim.sim_time == 0.0
    assert sim.blue.speed > 0
    assert sim.red.speed > 0
    assert sim.successful_locks == 0


def test_dogfight_simulator_single_step():
    sim = DogfightSimulator()
    sim.reset(blue_pos=(0, 0, 80), red_pos=(40, 0, 80), behavior=TargetBehavior.WEAVE)
    
    res = sim.step()
    assert res.sim_time == pytest.approx(0.05, 0.01)
    assert res.target_box is not None
    assert res.target_in_fov is True
    assert 20.0 < res.distance_m < 60.0


def test_dogfight_simulator_run_batch():
    sim = DogfightSimulator(dt=0.1)
    sim.reset(blue_pos=(0, 0, 80), red_pos=(35, 0, 80), behavior=TargetBehavior.WEAVE)
    
    summary = sim.run_simulation(duration_s=4.5)
    assert summary["total_sim_time_s"] == 4.5
    assert summary["fov_occupancy_pct"] > 50.0
    assert summary["locking_time_s"] > 0.0
