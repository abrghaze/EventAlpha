from __future__ import annotations

from hashlib import sha256
from os import getenv
from pathlib import Path

from sqlalchemy import create_engine, inspect, text

MIGRATIONS_DIRECTORY = Path(__file__).parents[1] / "migrations" / "versions"
DOMAIN_TABLES = {
    "sources",
    "raw_items",
    "events",
    "event_mentions",
    "providers",
    "instruments",
    "market_bar_observations",
    "market_quote_observations",
    "provider_state",
}
MIGRATION_ADVISORY_LOCK_ID = 4_534_940_721


def _migration_statements(path: Path) -> tuple[str, ...]:
    statements = tuple(
        statement.strip()
        for statement in path.read_text(encoding="utf-8").split(";")
        if statement.strip()
    )
    return tuple(
        statement for statement in statements if statement.upper() not in {"BEGIN", "COMMIT"}
    )


def migration_checksum(path: Path) -> str:
    canonical = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return sha256(canonical.encode("utf-8")).hexdigest()


def _legacy_byte_checksum(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def apply_migrations(database_url: str, directory: Path = MIGRATIONS_DIRECTORY) -> tuple[str, ...]:
    """Apply immutable, checksummed migrations under one database-owned lock."""
    engine = create_engine(database_url, pool_pre_ping=True)
    applied_now: list[str] = []
    try:
        with engine.begin() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(
                    text("SELECT pg_advisory_xact_lock(:lock_id)"),
                    {"lock_id": MIGRATION_ADVISORY_LOCK_ID},
                )
            tables = set(inspect(connection).get_table_names())
            if "schema_migrations" not in tables:
                unversioned = tables & DOMAIN_TABLES
                if unversioned:
                    raise RuntimeError(
                        "Refusing to bless an unversioned EventAlpha schema; found: "
                        + ", ".join(sorted(unversioned))
                    )
                connection.execute(
                    text(
                        """
                        CREATE TABLE schema_migrations (
                            version VARCHAR(255) PRIMARY KEY,
                            checksum VARCHAR(64) NOT NULL,
                            applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP
                        )
                        """
                    )
                )
            else:
                ledger_columns = {
                    column["name"]
                    for column in inspect(connection).get_columns("schema_migrations")
                }
                if {"version", "checksum", "applied_at"} - ledger_columns:
                    raise RuntimeError("schema_migrations ledger is incompatible or incomplete")

            migration_paths = tuple(sorted(directory.glob("*.sql")))
            checksums = {path.name: migration_checksum(path) for path in migration_paths}
            applied: dict[str, str] = {
                str(version): str(checksum)
                for version, checksum in connection.execute(
                    text("SELECT version, checksum FROM schema_migrations")
                ).tuples()
            }
            unavailable = set(applied) - set(checksums)
            if unavailable:
                raise RuntimeError(
                    "Database contains migrations unavailable to this release: "
                    + ", ".join(sorted(unavailable))
                )

            for path in migration_paths:
                recorded_checksum = applied.get(path.name)
                if recorded_checksum is not None:
                    if recorded_checksum != checksums[path.name]:
                        if recorded_checksum != _legacy_byte_checksum(path):
                            raise RuntimeError(f"Applied migration checksum changed: {path.name}")
                        connection.execute(
                            text(
                                "UPDATE schema_migrations SET checksum = :checksum "
                                "WHERE version = :version"
                            ),
                            {"version": path.name, "checksum": checksums[path.name]},
                        )
                    continue
                for statement in _migration_statements(path):
                    connection.exec_driver_sql(statement)
                connection.execute(
                    text(
                        "INSERT INTO schema_migrations(version, checksum) "
                        "VALUES (:version, :checksum)"
                    ),
                    {"version": path.name, "checksum": checksums[path.name]},
                )
                applied_now.append(path.name)
    finally:
        engine.dispose()
    return tuple(applied_now)


def main() -> None:
    database_url = getenv("EVENTALPHA_DATABASE_URL")
    if not database_url:
        raise RuntimeError("EVENTALPHA_DATABASE_URL is required to apply migrations")
    applied = apply_migrations(database_url)
    print(f"applied migrations: {', '.join(applied) if applied else 'none'}")


if __name__ == "__main__":
    main()
