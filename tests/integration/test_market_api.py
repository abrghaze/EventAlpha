from fastapi.testclient import TestClient

from app.main import app


def test_market_api_exposes_bars_quote_and_health() -> None:
    client = TestClient(app)
    bars = client.get("/api/v1/assets/ACME/bars?limit=3")
    snapshot = client.get("/api/v1/assets/ACME/snapshot")
    health = client.get("/api/v1/providers/health")
    assert bars.status_code == 200
    assert len(bars.json()["data"]) == 3
    assert snapshot.json()["quote"]["symbol"] == "ACME"
    assert snapshot.json()["quote_freshness_ms"] is not None
    assert health.json()["providers"][0]["status"] == "healthy"


def test_market_api_rejects_unknown_symbol_and_invalid_limit() -> None:
    client = TestClient(app)
    assert client.get("/api/v1/assets/NOPE/bars").status_code == 404
    assert client.get("/api/v1/assets/ACME/bars?limit=1001").status_code == 422
