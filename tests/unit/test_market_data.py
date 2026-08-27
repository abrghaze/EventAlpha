from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.contracts import MarketBar, MarketQuote
from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider


@pytest.mark.asyncio
async def test_replay_provider_returns_typed_quote_and_bars() -> None:
    clock = lambda: datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    provider = ReplayMarketDataProvider(clock)
    quote = await provider.latest_quote("acme")
    bars = await provider.bars("ACME", "1m", 3)
    assert quote.symbol == "ACME"
    assert quote.bid < quote.ask
    assert len(bars) == 3
    assert [bar.timestamp for bar in bars] == sorted(bar.timestamp for bar in bars)
    assert bars == await provider.bars("ACME", "1m", 3)
    assert bars[-1] == (await provider.bars("ACME", "1m", 60))[-1]


@pytest.mark.asyncio
async def test_cache_reports_stale_quote_and_provider_health() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
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


@pytest.mark.asyncio
async def test_persistence_failure_does_not_publish_quote_to_cache() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)

    class FailingPersistence:
        def save_quote(self, quote: object) -> bool:
            raise RuntimeError("database unavailable")

    service = MarketDataService(
        ReplayMarketDataProvider(lambda: now),
        persistence=FailingPersistence(),  # type: ignore[arg-type]
    )
    with pytest.raises(RuntimeError, match="database unavailable"):
        await service.latest("ACME")
    assert service.quote_freshness_ms("ACME") is None


@pytest.mark.asyncio
async def test_market_contracts_reject_invalid_price_geometry() -> None:
    now = datetime(2026, 8, 26, 12, 0, tzinfo=UTC)
    provider = ReplayMarketDataProvider(lambda: now)
    quote_payload = (await provider.latest_quote("ACME")).model_dump()
    quote_payload.update(bid=Decimal(102), ask=Decimal(101))
    with pytest.raises(ValidationError, match="bid must be less"):
        MarketQuote.model_validate(quote_payload)

    bar_payload = (await provider.bars("ACME", "1m", 1))[0].model_dump()
    bar_payload.update(high=Decimal(99))
    with pytest.raises(ValidationError, match="OHLC high/low bounds"):
        MarketBar.model_validate(bar_payload)
