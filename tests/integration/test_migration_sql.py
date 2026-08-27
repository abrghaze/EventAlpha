import sqlite3
from hashlib import sha256
from pathlib import Path

import pytest
from scripts.apply_migrations import apply_migrations
from sqlalchemy import create_engine, inspect, text


def test_event_foundation_migration_creates_required_tables() -> None:
    migration = Path(__file__).parents[2] / "migrations" / "versions" / "0001_event_foundation.sql"
    connection = sqlite3.connect(":memory:")
    connection.executescript(migration.read_text(encoding="utf-8"))
    tables = {
        row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    }
    assert {"sources", "raw_items", "events", "event_mentions"} <= tables


def test_migration_runner_applies_each_version_exactly_once(tmp_path: Path) -> None:
    database = tmp_path / "migration-runner.db"
    database_url = f"sqlite+pysqlite:///{database}"
    migrations = Path(__file__).parents[2] / "migrations" / "versions"

    assert apply_migrations(database_url, migrations) == ("0001_event_foundation.sql",)
    assert apply_migrations(database_url, migrations) == ()

    engine = create_engine(database_url)
    try:
        assert "schema_migrations" in inspect(engine).get_table_names()
        with engine.connect() as connection:
            assert (
                connection.execute(text("SELECT COUNT(*) FROM schema_migrations")).scalar_one() == 1
            )
            version, checksum = connection.execute(
                text("SELECT version, checksum FROM schema_migrations")
            ).one()
            assert version == "0001_event_foundation.sql"
            assert (
                checksum
                == sha256((migrations / "0001_event_foundation.sql").read_bytes()).hexdigest()
            )
    finally:
        engine.dispose()


def test_migration_runner_rejects_unversioned_domain_schema(tmp_path: Path) -> None:
    database = tmp_path / "unversioned.db"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE sources (source_id TEXT PRIMARY KEY)")
    connection.close()
    migrations = Path(__file__).parents[2] / "migrations" / "versions"

    with pytest.raises(RuntimeError, match="unversioned EventAlpha schema"):
        apply_migrations(f"sqlite+pysqlite:///{database}", migrations)


def test_migration_runner_rejects_changed_applied_migration(tmp_path: Path) -> None:
    database = tmp_path / "checksum.db"
    migrations = tmp_path / "migrations"
    migrations.mkdir()
    original = Path(__file__).parents[2] / "migrations" / "versions" / "0001_event_foundation.sql"
    copied = migrations / original.name
    copied.write_bytes(original.read_bytes())
    database_url = f"sqlite+pysqlite:///{database}"
    apply_migrations(database_url, migrations)
    copied.write_text(copied.read_text(encoding="utf-8") + "\n-- changed\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="checksum changed"):
        apply_migrations(database_url, migrations)
