from __future__ import annotations

import asyncio

from app.events.service import EventService
from app.providers.news.replay import ReplayNewsProvider


async def main() -> None:
    service = EventService()
    async for item in ReplayNewsProvider().stream_items():
        service.ingest(item)
    print(f"canonical replay events: {len(service.list_events())}")


if __name__ == "__main__":
    asyncio.run(main())
