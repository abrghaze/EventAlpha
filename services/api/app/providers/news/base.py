from __future__ import annotations

from collections.abc import AsyncIterator

from app.contracts import RawEnvelope


class NewsProvider:
    """Common contract for licensed news, official sources, SEC and macro adapters."""

    name: str

    async def stream_items(self) -> AsyncIterator[RawEnvelope]:
        raise NotImplementedError
