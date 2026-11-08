import os
import json
import pytest
from tools.export_flight_replay_3d import generate_3d_replay_html, create_sample_dogfight_recording


def test_export_flight_replay_3d(tmp_path):
    json_path = str(tmp_path / "test_flight.json")
    html_path = str(tmp_path / "test_replay.html")

    data = create_sample_dogfight_recording(output_file=json_path)
    assert len(data) > 0
    assert os.path.exists(json_path)

    out_file = generate_3d_replay_html(data, output_path=html_path)
    assert os.path.exists(out_file)

    with open(out_file, "r", encoding="utf-8") as f:
        content = f.read()
        assert "AeroCombat - 3D Hava Muharebesi" in content
        assert "three.min.js" in content
        assert "ownship" in content
