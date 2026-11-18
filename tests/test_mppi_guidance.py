from autopilot.mppi_guidance import MPPILockGuidanceController


def test_mppi_guidance_steers_toward_off_axis_target():
    mppi = MPPILockGuidanceController(num_rollouts=48, horizon_steps=12, dt=0.2, seed=123)
    # Kendi İHA'mız Kuzey'e uçuyor, hedef Kuzey-Doğu'da (sağ tarafta)
    cmd = mppi.compute_optimal_command(
        own_pos_ned=(0.0, 0.0, -80.0),
        own_vel_ned=(22.0, 0.0, 0.0),
        target_pos_ned=(45.0, 28.0, -80.0),
        target_vel_ned=(20.0, 4.0, 0.0)
    )

    assert cmd.roll_cmd_deg > 3.0  # Sağa doğru yatış komutu vermeli
    assert 15.0 <= cmd.airspeed_cmd_mps <= 32.0
    assert len(cmd.planned_trajectory_ned) == 12
    assert 0.0 < cmd.predicted_lock_probability <= 1.0


def test_mppi_guidance_altitude_hard_deck_protection():
    mppi = MPPILockGuidanceController(num_rollouts=48, horizon_steps=12, dt=0.2, min_safe_alt_m=35.0, seed=77)
    # İHA asgari güvenli irtifanın (35m) altına (24m -> NED z = -24.0) inmiş durumda
    cmd = mppi.compute_optimal_command(
        own_pos_ned=(0.0, 0.0, -24.0),
        own_vel_ned=(22.0, 0.0, 2.0),
        target_pos_ned=(40.0, 0.0, -22.0),
        target_vel_ned=(20.0, 0.0, 0.0)
    )

    # Hard-deck cezası nedeniyle pozitif dikilme (tırmanış) komutu üretmeli
    assert cmd.pitch_cmd_deg > 1.0


def test_mppi_guidance_centered_wez_high_lock_probability():
    mppi = MPPILockGuidanceController(num_rollouts=36, horizon_steps=10, dt=0.2, optimal_range_m=36.0, seed=99)
    cmd = mppi.compute_optimal_command(
        own_pos_ned=(0.0, 0.0, -80.0),
        own_vel_ned=(20.0, 0.0, 0.0),
        target_pos_ned=(36.0, 0.0, -80.0),
        target_vel_ned=(20.0, 0.0, 0.0)
    )

    assert cmd.expected_boresight_error_deg < 10.0
    assert cmd.predicted_lock_probability > 0.70
