from __future__ import annotations

import asyncio

import httpx

from app.config import Settings
from app.db.factory import build_persistent_event_service
from app.db.locks import postgres_advisory_lease
from app.events.service import EventService
from app.providers.news.factory import build_news_providers

INGESTION_ADVISORY_LOCK_ID = 4_534_940_722


async def main() -> None:
    settings = Settings.from_environment()
    if settings.database_url:
        service, engine = build_persistent_event_service(settings.database_url, create_schema=False)
    else:
        service = EventService()
        engine = None
    with postgres_advisory_lease(
        engine,
        INGESTION_ADVISORY_LOCK_ID,
        "Another event ingestion worker already owns the database lease",
    ):
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
