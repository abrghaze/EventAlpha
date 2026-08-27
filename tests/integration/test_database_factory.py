from sqlalchemy import inspect

from app.db.factory import build_persistent_event_service


def test_development_database_factory_creates_event_schema(tmp_path) -> None:
    database = tmp_path / "eventalpha.db"
    service, engine = build_persistent_event_service(
        f"sqlite+pysqlite:///{database}", create_schema=True
    )
    assert service.list_events() == ()
    assert {"sources", "raw_items", "events", "event_mentions"} <= set(
        inspect(engine).get_table_names()
    )
    engine.dispose()
