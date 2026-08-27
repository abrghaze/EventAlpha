from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid5

from app.contracts import MarketBar, MarketQuote, ProviderHealth, ProviderStatus

Clock = Callable[[], datetime]


class ReplayMarketDataProvider:
    """A credential-free, deterministic market adapter for local and CI use."""

    name = "replay-market"

    def __init__(self, clock: Clock | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self._last_message_at: datetime | None = None

    def _now(self) -> datetime:
        current = self._clock()
        if current.tzinfo is None:
            raise ValueError("Replay clock must return a timezone-aware timestamp")
        return current.astimezone(UTC)

    async def latest_quote(self, symbol: str) -> MarketQuote:
        normalized = symbol.upper()
        if normalized not in {"ACME", "SPY"}:
            raise KeyError(normalized)
        now = self._now()
        self._last_message_at = now
        last = Decimal("101.24") if normalized == "ACME" else Decimal("542.18")
        native_id = f"{normalized}:{now.isoformat()}"
        return MarketQuote(
            id=uuid5(NAMESPACE_URL, f"eventalpha:quote:{native_id}"),
            trace_id=uuid5(NAMESPACE_URL, f"eventalpha:quote-trace:{native_id}"),
            symbol=normalized,
            native_id=native_id,
            bid=last - Decimal("0.02"),
            ask=last + Decimal("0.02"),
            last=last,
            provider_timestamp=now,
            received_at=now,
            processed_at=now,
            provider=self.name,
        )

    async def bars(self, symbol: str, timeframe: str, limit: int) -> tuple[MarketBar, ...]:
        if timeframe != "1m":
            raise ValueError("Replay adapter currently supports 1m bars only")
        normalized = symbol.upper()
        if normalized not in {"ACME", "SPY"}:
            raise KeyError(normalized)
        received_at = self._now()
        now = received_at.replace(second=0, microsecond=0)
        anchor = Decimal("100.00") if normalized == "ACME" else Decimal("540.00")
        count = min(max(limit, 1), 1000)
        result: list[MarketBar] = []
        for index in range(count):
            timestamp = now - timedelta(minutes=count - index)
            minute_bucket = int(timestamp.timestamp() // 60) % 100
            close = anchor + Decimal(minute_bucket) * Decimal("0.08")
            native_id = f"{normalized}:1m:{timestamp.isoformat()}"
            result.append(
                MarketBar(
                    id=uuid5(NAMESPACE_URL, f"eventalpha:bar:{native_id}"),
                    trace_id=uuid5(NAMESPACE_URL, f"eventalpha:bar-trace:{native_id}"),
                    provider=self.name,
                    native_id=native_id,
                    symbol=normalized,
                    timeframe="1m",
                    timestamp=timestamp,
                    bar_end_at=timestamp + timedelta(minutes=1),
                    provider_updated_at=received_at,
                    received_at=received_at,
                    processed_at=received_at,
                    open=close - Decimal("0.03"),
                    high=close + Decimal("0.05"),
                    low=close - Decimal("0.06"),
                    close=close,
                    volume=10_000 + minute_bucket * 100,
                )
            )
        return tuple(result)

    async def stream_quotes(self, symbols: tuple[str, ...]) -> AsyncIterator[MarketQuote]:
        for symbol in symbols:
            yield await self.latest_quote(symbol)

    async def health(self, now: datetime) -> ProviderHealth:
        if now.tzinfo is None:
            raise ValueError("Health timestamp must be timezone-aware")
        freshness = (
            None
            if self._last_message_at is None
            else max(0, int((now - self._last_message_at).total_seconds() * 1000))
        )
        return ProviderHealth(
            name=self.name,
            status=ProviderStatus.HEALTHY
            if freshness is not None and freshness <= 15_000
            else ProviderStatus.DEGRADED,
            last_message_at=self._last_message_at,
            freshness_ms=freshness,
            detail="Deterministic replay provider; no external market coverage.",
        )
