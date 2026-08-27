from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager

import httpx
from sqlalchemy import Engine, text

from app.config import Settings
from app.db.factory import build_persistent_event_service
from app.events.service import EventService
from app.providers.news.factory import build_news_providers

INGESTION_ADVISORY_LOCK_ID = 4_534_940_722


@contextmanager
def ingestion_lease(engine: Engine | None) -> Iterator[None]:
    """Enforce the Phase 2 single-active-ingestion-worker invariant in PostgreSQL."""
    if engine is None or engine.dialect.name != "postgresql":
        yield
        return
    with engine.connect() as connection:
        acquired = connection.execute(
            text("SELECT pg_try_advisory_lock(:lock_id)"),
            {"lock_id": INGESTION_ADVISORY_LOCK_ID},
        ).scalar_one()
        if not acquired:
            raise RuntimeError("Another event ingestion worker already owns the database lease")
        try:
            yield
        finally:
            connection.execute(
                text("SELECT pg_advisory_unlock(:lock_id)"),
                {"lock_id": INGESTION_ADVISORY_LOCK_ID},
            )


async def main() -> None:
    settings = Settings.from_environment()
    if settings.database_url:
        service, engine = build_persistent_event_service(settings.database_url, create_schema=False)
    else:
        service = EventService()
        engine = None
    with ingestion_lease(engine):
        async with httpx.AsyncClient(follow_redirects=True) as client:
            providers = build_news_providers(settings, client)
            for provider in providers:
                async for item in provider.stream_items():
                    service.ingest(item)
    print(
        f"canonical events: {len(service.list_events())}; "
        f"source mode: {settings.event_source_mode}; providers: {len(providers)}"
    )
    if engine is not None:
        engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
