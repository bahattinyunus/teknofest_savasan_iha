import os
import json
import pytest
from tools.benchmark_inference import benchmark_inference
from tools.mission_debrief import parse_and_print_debrief


def test_benchmark_inference_mock():
    # Sentetik dedektör ile 5 iterasyon hızlı benchmark testi
    results = benchmark_inference(
        model_path="non_existent_model.pt",
        img_size=320,
        iterations=5,
        warmup=2,
        device="cpu"
    )
    assert "fps" in results
    assert "avg_latency_ms" in results
    assert results["fps"] > 0


def test_mission_debrief_html_export(tmp_path):
    session_dir = str(tmp_path / "session_test")
    os.makedirs(session_dir, exist_ok=True)

    summary_file = os.path.join(session_dir, "flight_summary.json")
    with open(summary_file, "w", encoding="utf-8") as f:
        json.dump({
            "ucus_suresi_sn": 120.5,
            "toplam_telemetri_noktasi": 360,
            "onaylanan_kilitlenme_sayisi": 3,
            "kazanilan_tahmini_puan": 300,
            "tuketilen_batarya_yuzdesi": 18
        }, f)

    events_file = os.path.join(session_dir, "events.jsonl")
    with open(events_file, "w", encoding="utf-8") as f:
        f.write(json.dumps({"time_str": "14:30:15", "event": "LOCK_SUCCESS", "data": "Target 1"}) + "\n")

    summary_out = parse_and_print_debrief(session_dir, export_html=True)
    assert summary_out["onaylanan_kilitlenme_sayisi"] == 3
    assert os.path.exists(os.path.join(session_dir, "debrief_report.html"))
