import math
import pytest
from simulation.aerodynamics_6dof import (
    Aerodynamics6DoF,
    AircraftParameters,
    State6DoF,
    FlightControls6DoF,
    AtmosphereISA
)


def test_atmosphere_isa_sea_level_and_altitude():
    rho0, p0, t0, a0 = AtmosphereISA.get_conditions(0.0)
    assert math.isclose(rho0, 1.225, rel_tol=1e-2)
    assert math.isclose(p0, 101325.0, rel_tol=1e-2)
    assert math.isclose(t0, 288.15, rel_tol=1e-2)
    assert a0 > 335.0

    rho_1000, p_1000, t_1000, _ = AtmosphereISA.get_conditions(1000.0)
    assert rho_1000 < rho0
    assert p_1000 < p0
    assert t_1000 < t0


def test_6dof_trim_and_step():
    sim = Aerodynamics6DoF()
    trim_ctrl = sim.trim_level_flight(target_airspeed_mps=22.0, target_altitude_m=80.0)
    
    assert 0.1 <= trim_ctrl.throttle <= 0.95
    assert -0.4 <= trim_ctrl.elevator <= 0.4

    # Simülasyonda 10 adım koştur
    for _ in range(10):
        state = sim.step(trim_ctrl, dt=0.02)

    assert state.airspeed_mps > 10.0
    assert not sim.is_stalled
    assert 0.5 < sim.last_load_factor_g < 2.0


def test_6dof_stall_dynamics():
    sim = Aerodynamics6DoF()
    # Aşırı elevatör çekerek hücum açısını stall bölgesine taşıyalım
    aggressive_ctrl = FlightControls6DoF(throttle=0.3, elevator=1.0)
    
    for _ in range(25):
        sim.step(aggressive_ctrl, dt=0.02)

    # Aerodinamik katsayıları doğrudan yüksek AoA ile kontrol et
    cl, cd, _, _, _, _ = sim.compute_aerodynamic_coefficients(
        alpha=math.radians(20.0),  # 20 derece > stall açısı 14.5
        beta=0.0,
        controls=aggressive_ctrl,
        p=0.0, q=0.0, r=0.0,
        airspeed=20.0
    )
    assert sim.is_stalled
    assert cd > 0.10  # Stall sonrası sürükleme artışı
