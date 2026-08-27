from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime
from typing import Protocol

from app.contracts import MarketBar, MarketQuote, ProviderHealth


class MarketProviderError(RuntimeError):
    """Base error raised after a market adapter normalizes a vendor failure."""


class TransientMarketProviderError(MarketProviderError):
    """A retryable provider transport, timeout, throttling, or upstream failure."""


class MarketDataProvider(Protocol):
    """Vendor adapters map their payloads here before reaching domain code."""

    name: str

    async def latest_quote(self, symbol: str) -> MarketQuote: ...

    async def bars(self, symbol: str, timeframe: str, limit: int) -> tuple[MarketBar, ...]: ...

    def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]: ...

    async def health(self, now: datetime) -> ProviderHealth: ...
