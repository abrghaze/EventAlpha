from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from app.contracts import MarketBar, MarketQuote, ProviderHealth


class MarketDataProvider(Protocol):
    """Vendor adapters map their payloads here before reaching domain code."""

    name: str

    async def latest_quote(self, symbol: str) -> MarketQuote: ...

    async def bars(self, symbol: str, timeframe: str, limit: int) -> tuple[MarketBar, ...]: ...

    async def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]: ...

    async def health(self, now: datetime) -> ProviderHealth: ...
