from simulation.dryden_turbulence import DrydenWindTurbulenceModel, TurbulenceSeverity


def test_dryden_steady_wind_shear_logarithmic_profile():
    model = DrydenWindTurbulenceModel(severity=TurbulenceSeverity.LIGHT, wind_speed_20ft_mps=5.0, wind_direction_deg=0.0)
    low_wind = model.compute_steady_wind_shear_ned(altitude_m=15.0)
    high_wind = model.compute_steady_wind_shear_ned(altitude_m=120.0)

    assert abs(high_wind[0]) > abs(low_wind[0])


def test_dryden_turbulence_and_burnham_hallock_wake_vortex():
    model = DrydenWindTurbulenceModel(severity=TurbulenceSeverity.MODERATE, wind_speed_20ft_mps=6.0, seed=10)
    # Kendi İHA'mız öndeki lider/hedef İHA'nın 18m tam arkasında (kuyruk türbülansı içinde)
    sample = model.step(
        altitude_m=80.0,
        airspeed_mps=22.0,
        dt=0.05,
        own_pos_ned=(62.0, 0.4, -80.0),
        leader_pos_ned=(80.0, 0.0, -80.0),
        leader_vel_ned=(20.0, 0.0, 0.0)
    )

    assert sample.is_in_wake_hazard is True
    assert abs(sample.wake_vortex_induced_vel_ned_mps[2]) > 0.05
    assert sample.total_wind_ned_mps != sample.steady_wind_ned_mps
