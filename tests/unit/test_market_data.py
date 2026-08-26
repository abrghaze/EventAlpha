from datetime import datetime, timedelta, timezone

import pytest

from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider


@pytest.mark.asyncio
async def test_replay_provider_returns_typed_quote_and_bars() -> None:
    clock = lambda: datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    provider = ReplayMarketDataProvider(clock)
    quote = await provider.latest_quote("acme")
    bars = await provider.bars("ACME", "1m", 3)
    assert quote.symbol == "ACME"
    assert quote.bid < quote.ask
    assert [bar.volume for bar in bars] == [10_000, 10_100, 10_200]


@pytest.mark.asyncio
async def test_cache_reports_stale_quote_and_provider_health() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc)
    current = [now]
    provider = ReplayMarketDataProvider(lambda: current[0])
    service = MarketDataService(provider, lambda: current[0])
    await service.latest("ACME")
    current[0] = now + timedelta(seconds=16)
    assert service.quote_freshness_ms("ACME") == 16_000
    assert (await service.health()).status.value == "degraded"


@pytest.mark.asyncio
async def test_replay_stream_refreshes_watchlist() -> None:
    service = MarketDataService(ReplayMarketDataProvider())
    assert await service.refresh_watchlist(("ACME", "SPY")) == 2
    assert service.quote_freshness_ms("SPY") is not None
