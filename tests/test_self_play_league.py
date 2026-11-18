import os
from tools.train_self_play_league import NeuralSelfPlayLeague


def test_elo_rating_update_formula():
    new_a, new_b = NeuralSelfPlayLeague.update_elo(1500.0, 1500.0, score_a=1.0, k_factor=32.0)
    assert new_a == 1516.0
    assert new_b == 1484.0


def test_self_play_league_tournament_and_export(tmp_path):
    export_file = os.path.join(str(tmp_path), "champion_weights.json")
    league = NeuralSelfPlayLeague(max_steps_per_match=40, seed=42)
    result = league.run_tournament(generations=2, export_path=export_file)

    assert os.path.exists(export_file)
    assert "champion_name" in result
    assert len(result["leaderboard"]) == 4
    assert result["total_matches"] == 12  # 4 takımlı ligde nesil başına 6 maç * 2 nesil
    assert len(result["champion_weights"]) == 16
    assert len(result["champion_bias"]) == 7
