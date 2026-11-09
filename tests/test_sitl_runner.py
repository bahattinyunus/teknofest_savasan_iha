import os
import pytest
from simulation.sitl_runner import SITLBatchRunner, EngagementScorecard
from simulation.dogfight_simulator import TargetBehavior


def test_sitl_single_scenario_run(tmp_path):
    runner = SITLBatchRunner(output_dir=str(tmp_path))
    scorecard = runner.run_scenario(
        scenario_id="TEST_ORBIT",
        opponent_behavior=TargetBehavior.ORBIT,
        sim_duration_s=8.0,
        dt=0.05
    )

    assert isinstance(scorecard, EngagementScorecard)
    assert scorecard.scenario_id == "TEST_ORBIT"
    assert scorecard.duration_s == 8.0
    assert scorecard.wez_retention_pct >= 0.0
    assert scorecard.min_distance_m > 0.0


def test_sitl_benchmark_suite(tmp_path):
    runner = SITLBatchRunner(output_dir=str(tmp_path))
    report = runner.run_benchmark_suite()

    assert report["total_scenarios"] == 4
    assert "scorecards" in report
    assert os.path.exists(tmp_path / "benchmark_report.json")
    assert os.path.exists(tmp_path / "benchmark_summary.md")
