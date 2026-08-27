from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text


@contextmanager
def postgres_advisory_lease(
    engine: Engine | None, lock_id: int, unavailable_message: str
) -> Iterator[None]:
    if engine is None or engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"), {"lock_id": lock_id}
        ).scalar_one()
        if not acquired:
            raise RuntimeError(unavailable_message)
        try:
            yield
        finally:
            connection.execute(text("SELECT pg_advisory_unlock(:lock_id)"), {"lock_id": lock_id})
