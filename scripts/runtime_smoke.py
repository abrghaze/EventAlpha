from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import inspect, text

from app.main import app, database_engine


def main() -> None:
    engine = database_engine
    assert engine is not None
    schema = inspect(engine)
    assert schema.get_pk_constraint("events")["constrained_columns"] == [
        "event_id",
        "event_version",
    ]
    raw_indexes = {index["name"]: index for index in schema.get_indexes("raw_items")}
    assert raw_indexes["uq_raw_provider_native"]["unique"]
    assert raw_indexes["uq_raw_provider_content_fallback"]["unique"]
    raw_columns = {column["name"]: column for column in schema.get_columns("raw_items")}
    assert str(raw_columns["derived_attributes"]["type"]).upper() == "JSONB"
    assert "processed_at" in raw_columns
    assert {column["name"] for column in schema.get_columns("sources")} >= {
        "source_type",
        "credibility_prior",
        "storage_policy",
    }
    assert schema.get_pk_constraint("market_bar_observations")["constrained_columns"] == [
        "content_hash"
    ]
    bar_columns = {
        column["name"]: column for column in schema.get_columns("market_bar_observations")
    }
    assert str(bar_columns["close"]["type"]).upper().startswith("NUMERIC")
    assert str(bar_columns["volume"]["type"]).upper() == "BIGINT"
    bar_indexes = {index["name"]: index for index in schema.get_indexes("market_bar_observations")}
    assert not bar_indexes["ix_market_bar_observation"]["unique"]
    with engine.connect() as connection:
        counts = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "schema_migrations",
                "sources",
                "raw_items",
                "events",
                "event_mentions",
                "providers",
                "instruments",
                "market_quote_observations",
                "market_bar_observations",
                "provider_state",
            )
        }
    assert counts == {
        "schema_migrations": 2,
        "sources": 3,
        "raw_items": 3,
        "events": 3,
        "event_mentions": 3,
        "providers": 1,
        "instruments": 2,
        "market_quote_observations": 2,
        "market_bar_observations": 120,
        "provider_state": 1,
    }

    with TestClient(app) as client:
        health = client.get("/api/v1/health")
        health.raise_for_status()
        payload = health.json()
        assert payload["status"] == "ok"
        assert payload["database"] == "connected"

        events = client.get("/api/v1/events")
        events.raise_for_status()
        event_payload = events.json()
        assert event_payload["source"] == "persistent"
        assert len(event_payload["data"]) == 2
        assert sorted(len(event["mentions"]) for event in event_payload["data"]) == [1, 2]

        snapshot = client.get("/api/v1/assets/ACME/snapshot")
        snapshot.raise_for_status()
        assert snapshot.json()["source"] == "replay-market"
        assert snapshot.json()["storage"] == "persistent"
        assert snapshot.json()["quote"]["symbol"] == "ACME"

        bars = client.get("/api/v1/assets/ACME/bars?limit=60")
        bars.raise_for_status()
        assert bars.json()["source"] == "replay-market"
        assert bars.json()["storage"] == "persistent"
        assert bars.json()["bar_freshness_ms"] is not None
        assert len(bars.json()["data"]) == 60
        assert bars.json()["data"] == sorted(bars.json()["data"], key=lambda bar: bar["timestamp"])

        before_health = counts["market_quote_observations"]
        provider_health = client.get("/api/v1/providers/health")
        provider_health.raise_for_status()
        durable_health = provider_health.json()["providers"][0]
        assert durable_health["last_message_at"] is not None
        assert durable_health["freshness_ms"] is not None
        with engine.connect() as connection:
            after_health = connection.execute(
                text("SELECT COUNT(*) FROM market_quote_observations")
            ).scalar_one()
        assert after_health == before_health
    print("container runtime smoke passed")


if __name__ == "__main__":
    main()
