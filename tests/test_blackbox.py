import os
import time
import pytest
from core.models import TelemetriPaketi, ZamanBilgisi
from core.blackbox import FlightBlackBox


def test_blackbox_recording_and_summary(tmp_path):
    blackbox = FlightBlackBox(base_log_dir=str(tmp_path))
    blackbox.start()

    tel = TelemetriPaketi(
        takim_numarasi=1, IHA_enlem=41.100, IHA_boylam=28.900, IHA_irtifa=100.0,
        IHA_dikilme=1.0, IHA_yonelme=180.0, IHA_yatis=2.0, IHA_hiz=22.0,
        IHA_batarya=95, IHA_otonom=1, IHA_kilitlenme=0,
        Hedef_merkez_X=640, Hedef_merkez_Y=360, Hedef_genislik=200, Hedef_yukseklik=150,
        GPSSaati=ZamanBilgisi.now()
    )

    blackbox.log_telemetry(tel)
    blackbox.log_event("TEST_EVENT", {"detail": "unit_test"})

    time.sleep(0.3)
    blackbox.stop()

    assert os.path.exists(blackbox.telemetry_csv_path)
    assert os.path.exists(blackbox.events_jsonl_path)
    assert os.path.exists(blackbox.summary_json_path)

    with open(blackbox.summary_json_path, "r", encoding="utf-8") as f:
        import json
        summary = json.load(f)
        assert summary["toplam_telemetri_noktasi"] >= 1
        assert summary["maksimum_hiz_m_s"] == 22.0
