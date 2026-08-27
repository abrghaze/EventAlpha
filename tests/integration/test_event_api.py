from fastapi.testclient import TestClient

from app.main import app


def test_event_api_returns_clustered_replay_events() -> None:
    client = TestClient(app)
    response = client.get("/api/v1/events")
    assert response.status_code == 200
    events = response.json()["data"]
    assert len(events) == 2
    acme = next(event for event in events if event["event_type"] == "earnings")
    assert len(acme["mentions"]) == 2
    assert client.get(f"/api/v1/events/{acme['event_id']}").status_code == 200
    historical = client.get(f"/api/v1/events/{acme['event_id']}/versions/1")
    assert historical.status_code == 200
    assert len(historical.json()["data"]["mentions"]) == 1
    assert client.get(f"/api/v1/events/{acme['event_id']}/versions/3").status_code == 404


def test_event_api_rejects_unknown_event() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/events/00000000-0000-0000-0000-000000000000").status_code == 404
