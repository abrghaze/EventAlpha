from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app import main as main_module
from app.contracts import MarketBar, MarketQuote, ProviderHealth, ProviderStatus
from app.db.market_repository import SqlMarketRepository
from app.db.models import Base, MarketBarRow, MarketQuoteRow
from app.market.service import MarketDataService, MarketPersistenceError
from app.providers.market import TransientMarketProviderError

NOW = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _quote(
    provider_timestamp: datetime,
    *,
    received_at: datetime | None = None,
    last: Decimal = Decimal("101.00"),
) -> MarketQuote:
    received = received_at or provider_timestamp
    return MarketQuote(
        provider="fixture-market",
        symbol="ACME",
        native_id=f"ACME:{provider_timestamp.isoformat()}",
        bid=last - Decimal("0.02"),
        ask=last + Decimal("0.02"),
        last=last,
        provider_timestamp=provider_timestamp,
        received_at=received,
        processed_at=received,
    )


def _bar(
    *,
    received_at: datetime,
    close: Decimal = Decimal("101.00"),
) -> MarketBar:
    start = NOW - timedelta(minutes=1)
    return MarketBar(
        provider="fixture-market",
        symbol="ACME",
        native_id=f"ACME:1m:{start.isoformat()}",
        timeframe="1m",
        timestamp=start,
        bar_end_at=NOW,
        provider_updated_at=received_at,
        received_at=received_at,
        processed_at=received_at,
        is_final=True,
        open=Decimal("100.50"),
        high=max(Decimal("101.10"), close + Decimal("0.10")),
        low=Decimal("100.40"),
        close=close,
        volume=10_000,
    )


def _repository(tmp_path: Path) -> tuple[SqlMarketRepository, Engine]:
    database = tmp_path / "market.db"
    engine = create_engine(f"sqlite+pysqlite:///{database}")
    Base.metadata.create_all(engine)
    return SqlMarketRepository(sessionmaker(engine, expire_on_commit=False)), engine


def test_quote_and_bar_redelivery_are_idempotent(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    quote = _quote(NOW)
    bar = _bar(received_at=NOW)
    assert repository.save_quote(quote)
    assert not repository.save_quote(
        quote.model_copy(update={"received_at": NOW + timedelta(seconds=1)})
    )
    assert repository.save_bars((bar,)) == 1
    assert (
        repository.save_bars((bar.model_copy(update={"received_at": NOW + timedelta(seconds=1)}),))
        == 0
    )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketQuoteRow)) == 1
        assert session.scalar(select(func.count()).select_from(MarketBarRow)) == 1
    engine.dispose()


def test_bar_corrections_are_append_only_and_as_of_safe(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    first_received = NOW
    revised_received = NOW + timedelta(minutes=5)
    original = _bar(received_at=first_received)
    revision = original.model_copy(
        update={
            "close": Decimal("101.40"),
            "high": Decimal("101.50"),
            "provider_updated_at": revised_received,
            "received_at": revised_received,
            "processed_at": revised_received,
        }
    )
    assert revision.id == original.id
    repository.save_bars((original,))
    repository.save_bars((revision,))

    before_revision = repository.bars(
        "fixture-market", "ACME", "1m", 10, NOW + timedelta(minutes=2)
    )
    after_revision = repository.bars("fixture-market", "ACME", "1m", 10, NOW + timedelta(minutes=6))
    assert before_revision[0].close == Decimal("101.00")
    assert after_revision[0].close == Decimal("101.40")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketBarRow)) == 2
        assert set(session.scalars(select(MarketBarRow.observation_id))) == {str(original.id)}
    engine.dispose()


def test_quote_corrections_can_retain_the_observation_id(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    original = _quote(NOW)
    revision = original.model_copy(
        update={
            "bid": Decimal("101.18"),
            "ask": Decimal("101.22"),
            "last": Decimal("101.20"),
            "received_at": NOW + timedelta(seconds=5),
            "processed_at": NOW + timedelta(seconds=5),
        }
    )
    assert revision.id == original.id
    assert repository.save_quote(original)
    assert repository.save_quote(revision)
    latest = repository.latest_quote("fixture-market", "ACME")
    assert latest is not None and latest.last == Decimal("101.20")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketQuoteRow)) == 2
        assert set(session.scalars(select(MarketQuoteRow.observation_id))) == {str(original.id)}
    engine.dispose()


def test_out_of_order_quote_does_not_regress_latest_projection(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    newer = _quote(NOW + timedelta(minutes=1), last=Decimal("102.00"))
    late_old = _quote(
        NOW,
        received_at=NOW + timedelta(minutes=2),
        last=Decimal("101.00"),
    )
    repository.save_quote(newer)
    repository.save_quote(late_old)
    latest = repository.latest_quote("fixture-market", "ACME")
    assert latest is not None
    assert latest.provider_timestamp == NOW + timedelta(minutes=1)
    assert latest.last == Decimal("102.00")
    engine.dispose()


@pytest.mark.asyncio
async def test_restart_reads_durable_quote_and_reports_staleness(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    repository.save_quote(_quote(NOW))
    repository.record_success("fixture-market", NOW, NOW, reconnected=False)
    _FlakyProvider.provider_connections = 0
    service = MarketDataService(
        _FlakyProvider(()),
        clock=lambda: NOW + timedelta(seconds=16),
        persistence=repository,
        provider_reads_enabled=False,
    )
    assert (await service.latest("ACME")).last == Decimal("101.00")
    assert service.quote_freshness_ms("ACME") == 16_000
    assert (await service.health()).status == ProviderStatus.DEGRADED
    assert _FlakyProvider.provider_connections == 0
    engine.dispose()


@pytest.mark.asyncio
async def test_recent_receipt_does_not_hide_stale_provider_timestamp(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    stale_quote = _quote(NOW - timedelta(hours=1), received_at=NOW)
    repository.save_quote(stale_quote)
    repository.record_success("fixture-market", NOW, NOW, reconnected=False)
    service = MarketDataService(
        _FlakyProvider(()),
        clock=lambda: NOW,
        persistence=repository,
        provider_reads_enabled=False,
    )
    quote = await service.latest("ACME")
    assert service.quote_freshness_ms("ACME", quote=quote) == 3_600_000
    assert (await service.health()).status == ProviderStatus.HEALTHY
    engine.dispose()


@pytest.mark.asyncio
async def test_historical_freshness_uses_the_returned_quote_not_newer_cache(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    original = _quote(NOW)
    current = _quote(NOW + timedelta(minutes=1), last=Decimal("102.00"))
    repository.save_quote(original)
    repository.save_quote(current)
    service = MarketDataService(
        _FlakyProvider(()),
        clock=lambda: NOW + timedelta(minutes=2),
        persistence=repository,
        provider_reads_enabled=False,
    )
    assert (await service.latest("ACME")).id == current.id
    historical = await service.latest("ACME", NOW + timedelta(seconds=30))
    assert historical.id == original.id
    assert (
        service.quote_freshness_ms("ACME", NOW + timedelta(seconds=30), quote=historical) == 30_000
    )
    assert service.quote_freshness_ms("ACME", NOW + timedelta(seconds=30)) is None
    engine.dispose()


@pytest.mark.asyncio
async def test_snapshot_current_then_historical_is_order_independent(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, engine = _repository(tmp_path)
    original = _quote(NOW)
    current = _quote(NOW + timedelta(minutes=1), last=Decimal("102.00"))
    repository.save_quote(original)
    repository.save_quote(current)
    service = MarketDataService(
        _FlakyProvider(()),
        clock=lambda: NOW + timedelta(minutes=2),
        persistence=repository,
        provider_reads_enabled=False,
    )
    monkeypatch.setattr(main_module, "market_data", service)
    monkeypatch.setattr(main_module, "database_engine", engine)

    current_payload = await main_module.asset_snapshot("ACME")
    historical_payload = await main_module.asset_snapshot("ACME", NOW + timedelta(seconds=30))
    assert current_payload["quote_freshness_ms"] == 60_000
    assert historical_payload["quote_freshness_ms"] == 30_000
    assert historical_payload["quote"]["id"] == str(original.id)
    engine.dispose()


class _FlakyProvider:
    name = "fixture-market"
    provider_connections = 0

    def __init__(self, attempts: tuple[tuple[MarketQuote | Exception, ...], ...]) -> None:
        self._attempts = list(attempts)

    async def latest_quote(self, symbol: str) -> MarketQuote:
        raise AssertionError("latest_quote must not be used by this test")

    async def bars(self, symbol: str, timeframe: str, limit: int) -> tuple[MarketBar, ...]:
        return ()

    async def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]:
        type(self).provider_connections += 1
        attempt = self._attempts.pop(0)
        for item in attempt:
            if isinstance(item, Exception):
                raise item
            yield item

    async def health(self, now: datetime) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            status=ProviderStatus.HEALTHY,
            last_message_at=now,
            freshness_ms=0,
        )


@pytest.mark.asyncio
async def test_stream_reconnect_is_bounded_and_duplicate_safe(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    first = _quote(NOW)
    second = _quote(NOW + timedelta(minutes=1), last=Decimal("102.00"))
    _FlakyProvider.provider_connections = 0
    provider = _FlakyProvider(((first, ConnectionError("disconnect")), (first, second)))
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    service = MarketDataService(
        provider,
        clock=lambda: NOW + timedelta(minutes=1),
        persistence=repository,
        sleeper=record_delay,
        backoff=lambda attempt: 0.25 * (attempt + 1),
    )
    assert await service.refresh_watchlist(("ACME",)) == 3
    assert delays == [0.25]
    assert _FlakyProvider.provider_connections == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketQuoteRow)) == 2
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.HEALTHY
    assert state.reconnect_count == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_successful_messages_reset_the_consecutive_reconnect_budget(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    quotes = tuple(
        _quote(NOW + timedelta(minutes=index), last=Decimal(101 + index)) for index in range(4)
    )
    _FlakyProvider.provider_connections = 0
    provider = _FlakyProvider(
        (
            (quotes[0], ConnectionError("first disconnect")),
            (quotes[1], TransientMarketProviderError("vendor unavailable")),
            (quotes[2], TimeoutError("idle")),
            (quotes[3],),
        )
    )
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    service = MarketDataService(
        provider,
        clock=lambda: NOW + timedelta(minutes=3),
        persistence=repository,
        sleeper=record_delay,
        backoff=lambda attempt: 0.1 * (attempt + 1),
    )
    assert await service.refresh_watchlist(("ACME",), attempts=2) == 4
    assert delays == [0.1, 0.1, 0.1]
    assert _FlakyProvider.provider_connections == 4
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.HEALTHY
    assert state.consecutive_failures == 0
    assert state.reconnect_count == 3
    engine.dispose()


class _LongLivedProvider(_FlakyProvider):
    def __init__(self, quote: MarketQuote) -> None:
        super().__init__(())
        self._quote = quote
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]:
        type(self).provider_connections += 1
        yield self._quote
        self.waiting.set()
        await self.release.wait()


@pytest.mark.asyncio
async def test_long_lived_stream_persists_health_before_termination(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    _LongLivedProvider.provider_connections = 0
    provider = _LongLivedProvider(_quote(NOW))
    service = MarketDataService(
        provider,
        clock=lambda: NOW,
        persistence=repository,
        stream_idle_timeout_seconds=60,
    )
    refresh = asyncio.create_task(service.refresh_watchlist(("ACME",)))
    await asyncio.wait_for(provider.waiting.wait(), timeout=1)
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.HEALTHY
    assert state.last_message_received_at == NOW
    refresh.cancel()
    with pytest.raises(asyncio.CancelledError):
        await refresh
    engine.dispose()


class _StallingProvider(_FlakyProvider):
    async def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]:
        type(self).provider_connections += 1
        await asyncio.Event().wait()
        if False:
            yield _quote(NOW)


@pytest.mark.asyncio
async def test_stalled_stream_times_out_and_exhausts_reconnects(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    _StallingProvider.provider_connections = 0
    service = MarketDataService(
        _StallingProvider(()),
        clock=lambda: NOW,
        persistence=repository,
        sleeper=lambda _: asyncio.sleep(0),
        backoff=lambda _: 0,
        stream_idle_timeout_seconds=0.01,
    )
    with pytest.raises(TimeoutError):
        await service.refresh_watchlist(("ACME",), attempts=2)
    assert _StallingProvider.provider_connections == 2
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.UNAVAILABLE
    assert state.consecutive_failures == 2
    engine.dispose()


@pytest.mark.asyncio
async def test_stream_persistence_failure_never_publishes_unstored_quote(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository, engine = _repository(tmp_path)
    first = _quote(NOW)
    second = _quote(NOW + timedelta(minutes=1), last=Decimal("102.00"))
    original_save = repository.save_quote
    calls = 0

    def fail_second_save(quote: MarketQuote) -> bool:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("database write rejected")
        return original_save(quote)

    monkeypatch.setattr(repository, "save_quote", fail_second_save)
    service = MarketDataService(
        _FlakyProvider(((first, second),)),
        clock=lambda: NOW + timedelta(minutes=1),
        persistence=repository,
    )
    with pytest.raises(MarketPersistenceError, match="database write rejected"):
        await service.refresh_watchlist(("ACME",))
    assert service.quote_freshness_ms("ACME") == 60_000
    latest = repository.latest_quote("fixture-market", "ACME")
    assert latest is not None and latest.id == first.id
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.UNAVAILABLE
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(MarketQuoteRow)) == 1
    engine.dispose()


@pytest.mark.asyncio
async def test_exhausted_reconnect_marks_unavailable_and_preserves_old_data(tmp_path) -> None:
    repository, engine = _repository(tmp_path)
    old_quote = _quote(NOW)
    repository.save_quote(old_quote)
    repository.record_success("fixture-market", NOW, NOW, reconnected=False)
    _FlakyProvider.provider_connections = 0
    provider = _FlakyProvider(
        (
            (TimeoutError("one"),),
            (TimeoutError("two"),),
            (TimeoutError("three"),),
        )
    )
    delays: list[float] = []

    async def record_delay(delay: float) -> None:
        delays.append(delay)

    service = MarketDataService(
        provider,
        clock=lambda: NOW + timedelta(minutes=5),
        persistence=repository,
        sleeper=record_delay,
        backoff=lambda attempt: 0.1 * (attempt + 1),
    )
    with pytest.raises(TimeoutError, match="three"):
        await service.refresh_watchlist(("ACME",), attempts=3)
    assert delays == [0.1, 0.2]
    assert _FlakyProvider.provider_connections == 3
    state = repository.provider_state("fixture-market")
    assert state is not None
    assert state.status == ProviderStatus.UNAVAILABLE
    assert state.consecutive_failures == 3
    latest = repository.latest_quote("fixture-market", "ACME")
    assert latest is not None and latest.id == old_quote.id
    engine.dispose()
