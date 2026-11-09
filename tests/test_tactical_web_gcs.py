import pytest
from fastapi.testclient import TestClient
from gcs.tactical_web_gcs import app, current_gcs_state


def test_tactical_web_gcs_html_dashboard():
    client = TestClient(app)
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "AeroCombat Tactical GCS" in response.text
    assert "Primary Flight Display" in response.text


def test_tactical_web_gcs_command_api():
    client = TestClient(app)
    payload = {"command": "BREAK_TURN"}
    response = client.post("/api/command", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ACK"
    assert data["active_mode"] == "DEFENSIVE_BREAK"
    assert current_gcs_state["autopilot_mode"] == "DEFENSIVE_BREAK"
