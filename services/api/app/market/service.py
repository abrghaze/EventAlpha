from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from math import isfinite
from secrets import randbelow
from typing import NoReturn, Protocol

from app.contracts import MarketBar, MarketQuote, ProviderHealth, ProviderStatus
from app.providers.market import MarketDataProvider, TransientMarketProviderError

Clock = Callable[[], datetime]
Sleeper = Callable[[float], Awaitable[None]]
Backoff = Callable[[int], float]
TRANSIENT_MARKET_ERRORS = (ConnectionError, TimeoutError, TransientMarketProviderError)


class MarketPersistenceError(RuntimeError):
    """Market data could not be published safely because durable persistence failed."""


@dataclass(frozen=True, slots=True)
class StoredMarketProviderState:
    provider_id: str
    heartbeat_at: datetime
    last_message_received_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    consecutive_failures: int
    reconnect_count: int
    status: ProviderStatus
    detail: str | None


class MarketPersistence(Protocol):
    def save_quote(self, quote: MarketQuote) -> bool: ...

    def save_bars(self, bars: tuple[MarketBar, ...]) -> int: ...

    def latest_quote(
        self, provider: str, symbol: str, as_of: datetime | None = None
    ) -> MarketQuote | None: ...

    def bars(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        limit: int,
        as_of: datetime | None = None,
        final_only: bool = True,
    ) -> tuple[MarketBar, ...]: ...

    def record_success(
        self,
        provider: str,
        observed_at: datetime,
        last_message_received_at: datetime | None,
        reconnected: bool,
    ) -> None: ...

    def record_failure(
        self,
        provider: str,
        observed_at: datetime,
        detail: str,
        exhausted: bool,
        last_message_received_at: datetime | None,
    ) -> None: ...

    def provider_state(self, provider: str) -> StoredMarketProviderState | None: ...


def _default_backoff(attempt: int) -> float:
    jitter = float(randbelow(51)) / 1000.0
    delay = 0.1 * 2.0**attempt + jitter
    return min(1.0, delay)


class MarketDataService:
    """Persists observations before projection and exposes point-in-time-safe reads."""

    def __init__(
        self,
        provider: MarketDataProvider,
        clock: Clock | None = None,
        persistence: MarketPersistence | None = None,
        provider_reads_enabled: bool = True,
        sleeper: Sleeper = asyncio.sleep,
        backoff: Backoff = _default_backoff,
        stream_idle_timeout_seconds: float = 15.0,
    ) -> None:
        if not isfinite(stream_idle_timeout_seconds) or stream_idle_timeout_seconds <= 0:
            raise ValueError("stream idle timeout must be a positive finite number")
        self._provider = provider
        self._clock = clock or (lambda: datetime.now(UTC))
        self._persistence = persistence
        self._provider_reads_enabled = provider_reads_enabled
        self._sleeper = sleeper
        self._backoff = backoff
        self._stream_idle_timeout_seconds = stream_idle_timeout_seconds
        self._latest: dict[str, MarketQuote] = {}

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise ValueError("Market clock must return a timezone-aware timestamp")
        return current.astimezone(UTC)

    @staticmethod
    def _quote_rank(quote: MarketQuote) -> tuple[datetime, datetime, str]:
        return (
            quote.provider_timestamp or quote.received_at,
            quote.received_at,
            str(quote.id),
        )

    def _remember_quote(self, quote: MarketQuote) -> None:
        current = self._latest.get(quote.symbol)
        if current is None or self._quote_rank(quote) > self._quote_rank(current):
            self._latest[quote.symbol] = quote

    async def _raise_persistence_failure(
        self,
        error: Exception,
        last_message_received_at: datetime | None,
    ) -> NoReturn:
        if self._persistence is not None:
            with suppress(Exception):
                await asyncio.to_thread(
                    self._persistence.record_failure,
                    self._provider.name,
                    self._now(),
                    f"persistence:{type(error).__name__}",
                    True,
                    last_message_received_at,
                )
        raise MarketPersistenceError(f"Market persistence failed: {error}") from error

    async def _save_quote(self, quote: MarketQuote) -> None:
        if self._persistence is None:
            return
        try:
            await asyncio.to_thread(self._persistence.save_quote, quote)
        except Exception as error:  # noqa: BLE001 - persistence is an adapter boundary
            await self._raise_persistence_failure(error, quote.received_at)

    async def _save_bars(self, bars: tuple[MarketBar, ...]) -> None:
        if self._persistence is None:
            return
        try:
            await asyncio.to_thread(self._persistence.save_bars, bars)
        except Exception as error:  # noqa: BLE001 - persistence is an adapter boundary
            last_message = max((bar.received_at for bar in bars), default=None)
            await self._raise_persistence_failure(error, last_message)

    async def _record_success(
        self,
        last_message_received_at: datetime | None,
        reconnected: bool,
    ) -> None:
        if self._persistence is None:
            return
        try:
            await asyncio.to_thread(
                self._persistence.record_success,
                self._provider.name,
                self._now(),
                last_message_received_at,
                reconnected,
            )
        except Exception as error:  # noqa: BLE001 - persistence is an adapter boundary
            await self._raise_persistence_failure(error, last_message_received_at)

    async def latest(self, symbol: str, as_of: datetime | None = None) -> MarketQuote:
        normalized = symbol.upper()
        if self._persistence is not None and not self._provider_reads_enabled:
            quote = await asyncio.to_thread(
                self._persistence.latest_quote, self._provider.name, normalized, as_of
            )
            if quote is None:
                raise KeyError(normalized)
        else:
            quote = await self._provider.latest_quote(normalized)
            await self._save_quote(quote)
        self._remember_quote(quote)
        return quote

    async def bars(
        self,
        symbol: str,
        timeframe: str = "1m",
        limit: int = 60,
        as_of: datetime | None = None,
    ) -> tuple[MarketBar, ...]:
        normalized = symbol.upper()
        if timeframe not in {"1m", "5m", "15m", "1h", "1d"}:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if self._persistence is not None and not self._provider_reads_enabled:
            return await asyncio.to_thread(
                self._persistence.bars,
                self._provider.name,
                normalized,
                timeframe,
                limit,
                as_of,
                True,
            )
        bars = await self._provider.bars(normalized, timeframe, limit)
        await self._save_bars(bars)
        return bars

    def quote_freshness_ms(
        self,
        symbol: str,
        reference_at: datetime | None = None,
        *,
        quote: MarketQuote | None = None,
    ) -> int | None:
        quote = quote or self._latest.get(symbol.upper())
        if quote is None:
            return None
        reference = reference_at or self._now()
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("freshness reference must be timezone-aware")
        market_timestamp = quote.provider_timestamp or quote.received_at
        age_ms = int(
            (reference.astimezone(UTC) - market_timestamp.astimezone(UTC)).total_seconds() * 1000
        )
        return None if age_ms < 0 else age_ms

    def bar_freshness_ms(
        self,
        bars: tuple[MarketBar, ...],
        reference_at: datetime | None = None,
    ) -> int | None:
        if not bars:
            return None
        reference = reference_at or self._now()
        if reference.tzinfo is None or reference.utcoffset() is None:
            raise ValueError("freshness reference must be timezone-aware")
        latest_market_time = max(bar.bar_end_at for bar in bars)
        age_ms = int(
            (reference.astimezone(UTC) - latest_market_time.astimezone(UTC)).total_seconds() * 1000
        )
        return None if age_ms < 0 else age_ms

    async def health(self) -> ProviderHealth:
        now = self._now()
        if self._persistence is not None and not self._provider_reads_enabled:
            state = await asyncio.to_thread(self._persistence.provider_state, self._provider.name)
            if state is None:
                return ProviderHealth(
                    name=self._provider.name,
                    status=ProviderStatus.UNAVAILABLE,
                    last_message_at=None,
                    freshness_ms=None,
                    detail="No durable provider heartbeat is available.",
                )
            if state.last_message_received_at is None:
                freshness = None
            else:
                age_ms = int((now - state.last_message_received_at).total_seconds() * 1000)
                if age_ms < 0:
                    return ProviderHealth(
                        name=state.provider_id,
                        status=ProviderStatus.DEGRADED,
                        last_message_at=state.last_message_received_at,
                        freshness_ms=0,
                        detail="Provider receipt timestamp is ahead of the service clock.",
                    )
                freshness = age_ms
            status = state.status
            if freshness is None or freshness > 15_000:
                status = (
                    ProviderStatus.UNAVAILABLE
                    if status == ProviderStatus.UNAVAILABLE
                    else ProviderStatus.DEGRADED
                )
            return ProviderHealth(
                name=state.provider_id,
                status=status,
                last_message_at=state.last_message_received_at,
                freshness_ms=freshness,
                detail=state.detail,
            )
        health = await self._provider.health(now)
        if health.freshness_ms is None:
            return health
        if health.freshness_ms > 15_000 and health.status == ProviderStatus.HEALTHY:
            return health.model_copy(update={"status": ProviderStatus.DEGRADED})
        return health

    async def refresh_watchlist(self, symbols: tuple[str, ...], attempts: int = 3) -> int:
        if not self._provider_reads_enabled:
            raise RuntimeError("Read-only market service cannot open a provider stream")
        if attempts < 1:
            raise ValueError("attempts must be positive")
        count = 0
        last_message: datetime | None = None
        consecutive_failures = 0
        reconnect_pending = False
        while True:
            try:
                stream = self._provider.stream_quotes(symbols)
                while True:
                    quote = await asyncio.wait_for(
                        anext(stream), timeout=self._stream_idle_timeout_seconds
                    )
                    await self._save_quote(quote)
                    last_message = (
                        quote.received_at
                        if last_message is None
                        else max(last_message, quote.received_at)
                    )
                    await self._record_success(last_message, reconnect_pending)
                    self._remember_quote(quote)
                    count += 1
                    consecutive_failures = 0
                    reconnect_pending = False
            except StopAsyncIteration:
                return count
            except TRANSIENT_MARKET_ERRORS as error:
                consecutive_failures += 1
                exhausted = consecutive_failures >= attempts
                if self._persistence is not None:
                    try:
                        await asyncio.to_thread(
                            self._persistence.record_failure,
                            self._provider.name,
                            self._now(),
                            type(error).__name__,
                            exhausted,
                            last_message,
                        )
                    except Exception as persistence_error:
                        raise MarketPersistenceError(
                            f"Could not persist provider failure: {persistence_error}"
                        ) from persistence_error
                if exhausted:
                    raise
                reconnect_pending = True
                await self._sleeper(self._backoff(consecutive_failures - 1))
                continue

    async def refresh_bars(
        self,
        symbols: tuple[str, ...],
        timeframe: str = "1m",
        limit: int = 60,
        attempts: int = 3,
    ) -> int:
        if not self._provider_reads_enabled:
            raise RuntimeError("Read-only market service cannot fetch provider bars")
        if timeframe not in {"1m", "5m", "15m", "1h", "1d"}:
            raise ValueError(f"Unsupported timeframe: {timeframe}")
        if attempts < 1:
            raise ValueError("attempts must be positive")
        count = 0
        for symbol in symbols:
            for attempt in range(attempts):
                try:
                    bars = await self._provider.bars(symbol, timeframe, limit)
                except TRANSIENT_MARKET_ERRORS as error:
                    exhausted = attempt == attempts - 1
                    if self._persistence is not None:
                        await asyncio.to_thread(
                            self._persistence.record_failure,
                            self._provider.name,
                            self._now(),
                            type(error).__name__,
                            exhausted,
                            None,
                        )
                    if exhausted:
                        raise
                    await self._sleeper(self._backoff(attempt))
                    continue
                await self._save_bars(bars)
                await self._record_success(None, attempt > 0)
                count += len(bars)
                break
        return count
