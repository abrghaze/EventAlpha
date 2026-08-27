from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from hashlib import sha256
from typing import cast, overload
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.contracts import MarketBar, MarketQuote, MarketTimeframe, ProviderStatus
from app.db.models import (
    InstrumentRow,
    MarketBarRow,
    MarketQuoteRow,
    ProviderRow,
    ProviderStateRow,
)
from app.market.service import StoredMarketProviderState


@overload
def _utc(value: datetime) -> datetime: ...


@overload
def _utc(value: None) -> None: ...


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _decimal_text(value: Decimal | None) -> str:
    return "null" if value is None else format(value.normalize(), "f")


def _time_text(value: datetime | None) -> str:
    return "null" if value is None else value.astimezone(UTC).isoformat(timespec="microseconds")


def _fingerprint(parts: tuple[str, ...]) -> str:
    return sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def quote_fingerprint(quote: MarketQuote) -> str:
    effective_time = quote.provider_timestamp or quote.received_at
    return _fingerprint(
        (
            quote.provider,
            quote.symbol,
            quote.native_id or "",
            _time_text(effective_time),
            _decimal_text(quote.bid),
            _decimal_text(quote.ask),
            _decimal_text(quote.last),
        )
    )


def bar_fingerprint(bar: MarketBar) -> str:
    return _fingerprint(
        (
            bar.provider,
            bar.symbol,
            bar.timeframe,
            _time_text(bar.timestamp),
            _time_text(bar.bar_end_at),
            _decimal_text(bar.open),
            _decimal_text(bar.high),
            _decimal_text(bar.low),
            _decimal_text(bar.close),
            "null" if bar.volume is None else str(bar.volume),
            str(bar.is_final),
        )
    )


class SqlMarketRepository:
    """Append-only market observations with received-time, point-in-time reads."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    @staticmethod
    def _ensure_provider(session: Session, provider: str, created_at: datetime) -> None:
        if session.get(ProviderRow, provider) is None:
            session.add(
                ProviderRow(
                    provider_id=provider,
                    provider_type="market_data",
                    created_at=created_at,
                )
            )

    @staticmethod
    def _ensure_instrument(session: Session, symbol: str, created_at: datetime) -> None:
        if session.get(InstrumentRow, symbol) is None:
            session.add(
                InstrumentRow(
                    symbol=symbol,
                    asset_class="unknown",
                    active=True,
                    created_at=created_at,
                )
            )

    def save_quote(self, quote: MarketQuote) -> bool:
        content_hash = quote_fingerprint(quote)
        with self._sessions.begin() as session:
            self._ensure_provider(session, quote.provider, quote.processed_at)
            self._ensure_instrument(session, quote.symbol, quote.processed_at)
            if session.get(MarketQuoteRow, content_hash) is not None:
                return False
            session.add(
                MarketQuoteRow(
                    content_hash=content_hash,
                    observation_id=str(quote.id),
                    trace_id=str(quote.trace_id),
                    provider=quote.provider,
                    native_id=quote.native_id,
                    symbol=quote.symbol,
                    bid=quote.bid,
                    ask=quote.ask,
                    last=quote.last,
                    provider_timestamp=quote.provider_timestamp,
                    received_at=quote.received_at,
                    processed_at=quote.processed_at,
                )
            )
        return True

    def save_bars(self, bars: tuple[MarketBar, ...]) -> int:
        inserted = 0
        with self._sessions.begin() as session:
            for bar in bars:
                self._ensure_provider(session, bar.provider, bar.processed_at)
                self._ensure_instrument(session, bar.symbol, bar.processed_at)
                content_hash = bar_fingerprint(bar)
                if session.get(MarketBarRow, content_hash) is not None:
                    continue
                session.add(
                    MarketBarRow(
                        content_hash=content_hash,
                        observation_id=str(bar.id),
                        trace_id=str(bar.trace_id),
                        provider=bar.provider,
                        native_id=bar.native_id,
                        symbol=bar.symbol,
                        timeframe=bar.timeframe,
                        bar_start_at=bar.timestamp,
                        bar_end_at=bar.bar_end_at,
                        provider_updated_at=bar.provider_updated_at,
                        received_at=bar.received_at,
                        processed_at=bar.processed_at,
                        is_final=bar.is_final,
                        open=bar.open,
                        high=bar.high,
                        low=bar.low,
                        close=bar.close,
                        volume=bar.volume,
                    )
                )
                inserted += 1
        return inserted

    def latest_quote(
        self, provider: str, symbol: str, as_of: datetime | None = None
    ) -> MarketQuote | None:
        query = select(MarketQuoteRow).where(
            (MarketQuoteRow.provider == provider) & (MarketQuoteRow.symbol == symbol.upper())
        )
        if as_of is not None:
            query = query.where(MarketQuoteRow.received_at <= as_of)
        query = query.order_by(
            func.coalesce(MarketQuoteRow.provider_timestamp, MarketQuoteRow.received_at).desc(),
            MarketQuoteRow.received_at.desc(),
            MarketQuoteRow.processed_at.desc(),
            MarketQuoteRow.content_hash.desc(),
        )
        with self._sessions() as session:
            row = session.scalar(query.limit(1))
        if row is None:
            return None
        return MarketQuote(
            id=UUID(row.observation_id),
            trace_id=UUID(row.trace_id),
            provider=row.provider,
            native_id=row.native_id,
            symbol=row.symbol,
            bid=row.bid,
            ask=row.ask,
            last=row.last,
            provider_timestamp=_utc(row.provider_timestamp),
            received_at=_utc(row.received_at),
            processed_at=_utc(row.processed_at),
        )

    def bars(
        self,
        provider: str,
        symbol: str,
        timeframe: str,
        limit: int,
        as_of: datetime | None = None,
        final_only: bool = True,
    ) -> tuple[MarketBar, ...]:
        query = select(MarketBarRow).where(
            (MarketBarRow.provider == provider)
            & (MarketBarRow.symbol == symbol.upper())
            & (MarketBarRow.timeframe == timeframe)
        )
        if as_of is not None:
            query = query.where(MarketBarRow.received_at <= as_of)
        if final_only:
            query = query.where(MarketBarRow.is_final.is_(True))
        query = query.order_by(
            MarketBarRow.bar_start_at.desc(),
            MarketBarRow.received_at.desc(),
            MarketBarRow.processed_at.desc(),
            MarketBarRow.content_hash.desc(),
        )
        with self._sessions() as session:
            rows = tuple(session.scalars(query))
        selected: list[MarketBarRow] = []
        seen_starts: set[datetime] = set()
        for row in rows:
            bar_start = _utc(row.bar_start_at)
            if bar_start in seen_starts:
                continue
            seen_starts.add(bar_start)
            selected.append(row)
            if len(selected) == limit:
                break
        return tuple(
            MarketBar(
                id=UUID(row.observation_id),
                trace_id=UUID(row.trace_id),
                provider=row.provider,
                native_id=row.native_id,
                symbol=row.symbol,
                timeframe=cast(MarketTimeframe, row.timeframe),
                timestamp=_utc(row.bar_start_at),
                bar_end_at=_utc(row.bar_end_at),
                provider_updated_at=_utc(row.provider_updated_at),
                received_at=_utc(row.received_at),
                processed_at=_utc(row.processed_at),
                is_final=row.is_final,
                open=row.open,
                high=row.high,
                low=row.low,
                close=row.close,
                volume=row.volume,
            )
            for row in reversed(selected)
        )

    def record_success(
        self,
        provider: str,
        observed_at: datetime,
        last_message_received_at: datetime | None,
        reconnected: bool,
    ) -> None:
        with self._sessions.begin() as session:
            self._ensure_provider(session, provider, observed_at)
            state = session.get(ProviderStateRow, provider)
            if state is None:
                state = ProviderStateRow(
                    provider_id=provider,
                    heartbeat_at=observed_at,
                    last_message_received_at=last_message_received_at,
                    last_success_at=observed_at,
                    last_failure_at=None,
                    consecutive_failures=0,
                    reconnect_count=1 if reconnected else 0,
                    status=ProviderStatus.HEALTHY.value,
                    detail=None,
                )
                session.add(state)
                return
            state.heartbeat_at = observed_at
            current_last_message = _utc(state.last_message_received_at)
            if last_message_received_at is not None and (
                current_last_message is None or last_message_received_at > current_last_message
            ):
                state.last_message_received_at = last_message_received_at
            state.last_success_at = observed_at
            state.consecutive_failures = 0
            state.reconnect_count += 1 if reconnected else 0
            state.status = ProviderStatus.HEALTHY.value
            state.detail = None

    def record_failure(
        self,
        provider: str,
        observed_at: datetime,
        detail: str,
        exhausted: bool,
        last_message_received_at: datetime | None,
    ) -> None:
        with self._sessions.begin() as session:
            self._ensure_provider(session, provider, observed_at)
            state = session.get(ProviderStateRow, provider)
            if state is None:
                session.add(
                    ProviderStateRow(
                        provider_id=provider,
                        heartbeat_at=observed_at,
                        last_message_received_at=last_message_received_at,
                        last_success_at=None,
                        last_failure_at=observed_at,
                        consecutive_failures=1,
                        reconnect_count=0,
                        status=(
                            ProviderStatus.UNAVAILABLE.value
                            if exhausted
                            else ProviderStatus.DEGRADED.value
                        ),
                        detail=detail,
                    )
                )
                return
            state.heartbeat_at = observed_at
            current_last_message = _utc(state.last_message_received_at)
            if last_message_received_at is not None and (
                current_last_message is None or last_message_received_at > current_last_message
            ):
                state.last_message_received_at = last_message_received_at
            state.last_failure_at = observed_at
            state.consecutive_failures += 1
            state.status = (
                ProviderStatus.UNAVAILABLE.value if exhausted else ProviderStatus.DEGRADED.value
            )
            state.detail = detail

    def provider_state(self, provider: str) -> StoredMarketProviderState | None:
        with self._sessions() as session:
            row = session.get(ProviderStateRow, provider)
        if row is None:
            return None
        return StoredMarketProviderState(
            provider_id=row.provider_id,
            heartbeat_at=_utc(row.heartbeat_at),
            last_message_received_at=_utc(row.last_message_received_at),
            last_success_at=_utc(row.last_success_at),
            last_failure_at=_utc(row.last_failure_at),
            consecutive_failures=row.consecutive_failures,
            reconnect_count=row.reconnect_count,
            status=ProviderStatus(row.status),
            detail=row.detail,
        )
