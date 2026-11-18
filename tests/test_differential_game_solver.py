from autopilot.differential_game_solver import (
    DifferentialGameSolver,
    PursuerAction,
    EvaderAction
)


def test_isaacs_capture_barrier_inside_wez():
    solver = DifferentialGameSolver()
    capturable, margin_m, ttc_s = solver.compute_isaacs_barrier(
        own_pos_ned=(0.0, 0.0, -80.0),
        own_vel_ned=(24.0, 0.0, 0.0),
        target_pos_ned=(40.0, 2.0, -80.0),
        target_vel_ned=(20.0, 0.0, 0.0)
    )

    assert capturable is True
    assert margin_m > 10.0
    assert ttc_s >= 0.0


def test_isaacs_minimax_saddle_point_solution():
    solver = DifferentialGameSolver()
    sol = solver.solve_saddle_point(
        own_pos_ned=(0.0, 0.0, -80.0),
        own_vel_ned=(22.0, 0.0, 0.0),
        target_pos_ned=(42.0, 18.0, -76.0),
        target_vel_ned=(20.0, 5.0, 0.0)
    )

    assert isinstance(sol.optimal_pursuer_action, PursuerAction)
    assert isinstance(sol.expected_evader_response, EvaderAction)
    assert sol.commanded_roll_deg > 2.0  # Sağdaki hedefe doğru yatış vermeli
    assert len(sol.payoff_matrix) == 5
    assert sol.saddle_point_value > 10.0
