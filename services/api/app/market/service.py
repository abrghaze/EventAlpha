from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

from app.contracts import MarketBar, MarketQuote, ProviderHealth, ProviderStatus
from app.providers.market import MarketDataProvider


class MarketDataService:
    """Owns latest-value cache and turns provider freshness into explicit state."""

    def __init__(
        self, provider: MarketDataProvider, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._latest: dict[str, MarketQuote] = {}

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise ValueError("Market clock must return a timezone-aware timestamp")
        return current.astimezone(UTC)

    async def latest(self, symbol: str) -> MarketQuote:
        quote = await self._provider.latest_quote(symbol)
        self._latest[quote.symbol] = quote
        return quote

    async def bars(
        self, symbol: str, timeframe: str = "1m", limit: int = 60
    ) -> tuple[MarketBar, ...]:
        return await self._provider.bars(symbol, timeframe, limit)

    def quote_freshness_ms(self, symbol: str) -> int | None:
        quote = self._latest.get(symbol.upper())
        if quote is None:
            return None
        return max(0, int((self._now() - quote.received_at).total_seconds() * 1000))

    async def health(self) -> ProviderHealth:
        health = await self._provider.health(self._now())
        if health.freshness_ms is None:
            return health
        if health.freshness_ms > 15_000 and health.status == ProviderStatus.HEALTHY:
            return health.model_copy(update={"status": ProviderStatus.DEGRADED})
        return health

    async def refresh_watchlist(self, symbols: tuple[str, ...]) -> int:
        count = 0
        async for quote in self._provider.stream_quotes(symbols):
            self._latest[quote.symbol] = quote
            count += 1
        return count
