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
    with engine.connect() as connection:
        counts = {
            table: connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()
            for table in (
                "schema_migrations",
                "sources",
                "raw_items",
                "events",
                "event_mentions",
            )
        }
    assert counts == {
        "schema_migrations": 1,
        "sources": 3,
        "raw_items": 3,
        "events": 3,
        "event_mentions": 3,
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
    print("container runtime smoke passed")


if __name__ == "__main__":
    main()
