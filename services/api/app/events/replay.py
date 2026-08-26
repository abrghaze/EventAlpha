from __future__ import annotations

from app.events.service import EventService
from app.providers.news.replay import ReplayNewsProvider


class ReplayEventBootstrap:
    def __init__(self, service: EventService) -> None:
        self._service = service
        self._loaded = False

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        async for item in ReplayNewsProvider().stream_items():
            self._service.ingest(item)
        self._loaded = True
