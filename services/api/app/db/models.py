from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class SourceRow(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("credibility_prior BETWEEN 0 AND 1", name="ck_sources_credibility_prior"),
    )
    source_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    credibility_prior: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    storage_policy: Mapped[str] = mapped_column(String(50), nullable=False)


class RawItemRow(Base):
    __tablename__ = "raw_items"
    __table_args__ = (
        Index(
            "uq_raw_provider_native",
            "provider",
            "source_id",
            "native_id",
            unique=True,
            postgresql_where=text("native_id IS NOT NULL"),
            sqlite_where=text("native_id IS NOT NULL"),
        ),
        Index(
            "uq_raw_provider_content_fallback",
            "provider",
            "source_id",
            "content_hash",
            unique=True,
            postgresql_where=text("native_id IS NULL"),
            sqlite_where=text("native_id IS NULL"),
        ),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(100), nullable=False)
    source_id: Mapped[str] = mapped_column(ForeignKey("sources.source_id"), nullable=False)
    native_id: Mapped[str | None] = mapped_column(String(500))
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(1000), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    storage_policy: Mapped[str] = mapped_column(String(50), nullable=False)
    independence_group: Mapped[str | None] = mapped_column(String(255))
    derived_attributes: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)


class EventRow(Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("event_version >= 1", name="ck_events_version"),
        CheckConstraint("novelty BETWEEN 0 AND 1", name="ck_events_novelty"),
        CheckConstraint(
            "source_independence BETWEEN 0 AND 1", name="ck_events_source_independence"
        ),
    )
    event_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    event_version: Mapped[int] = mapped_column(Integer, primary_key=True)
    version_created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    clustering_version: Mapped[str] = mapped_column(String(100), nullable=False)
    canonical_title: Mapped[str] = mapped_column(String(1000), nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    event_time: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    novelty: Mapped[float] = mapped_column(Float, nullable=False)
    source_independence: Mapped[float] = mapped_column(Float, nullable=False)


class EventMentionRow(Base):
    __tablename__ = "event_mentions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["event_id", "event_version"], ["events.event_id", "events.event_version"]
        ),
    )
    raw_item_id: Mapped[str] = mapped_column(ForeignKey("raw_items.id"), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    event_version: Mapped[int] = mapped_column(Integer, nullable=False)
    source_id: Mapped[str] = mapped_column(String(255), nullable=False)
    independence_group: Mapped[str] = mapped_column(String(255), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderRow(Base):
    __tablename__ = "providers"
    provider_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    provider_type: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class InstrumentRow(Base):
    __tablename__ = "instruments"
    symbol: Mapped[str] = mapped_column(String(12), primary_key=True)
    asset_class: Mapped[str] = mapped_column(String(50), nullable=False, default="unknown")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class MarketBarRow(Base):
    __tablename__ = "market_bar_observations"
    __table_args__ = (
        CheckConstraint("bar_end_at > bar_start_at", name="ck_market_bar_interval"),
        CheckConstraint(
            "high >= open AND high >= close AND high >= low",
            name="ck_market_bar_high",
        ),
        CheckConstraint(
            "low <= open AND low <= close AND low <= high",
            name="ck_market_bar_low",
        ),
        CheckConstraint("volume IS NULL OR volume >= 0", name="ck_market_bar_volume"),
        Index(
            "ix_market_bars_lookup",
            "provider",
            "symbol",
            "timeframe",
            "bar_start_at",
            "received_at",
        ),
        Index("ix_market_bar_trace", "trace_id"),
        Index("ix_market_bar_observation", "observation_id"),
    )
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(ForeignKey("providers.provider_id"), nullable=False)
    native_id: Mapped[str | None] = mapped_column(String(500))
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    timeframe: Mapped[str] = mapped_column(String(10), nullable=False)
    bar_start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bar_end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    provider_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False)
    open: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(28, 10), nullable=False)
    volume: Mapped[int | None] = mapped_column(BigInteger)


class MarketQuoteRow(Base):
    __tablename__ = "market_quote_observations"
    __table_args__ = (
        CheckConstraint("bid IS NULL OR bid > 0", name="ck_market_quote_bid"),
        CheckConstraint("ask IS NULL OR ask > 0", name="ck_market_quote_ask"),
        CheckConstraint("last IS NULL OR last > 0", name="ck_market_quote_last"),
        CheckConstraint("bid IS NULL OR ask IS NULL OR bid <= ask", name="ck_market_quote_spread"),
        CheckConstraint(
            "bid IS NOT NULL OR ask IS NOT NULL OR last IS NOT NULL",
            name="ck_market_quote_has_price",
        ),
        Index(
            "ix_market_quotes_lookup",
            "provider",
            "symbol",
            "provider_timestamp",
            "received_at",
        ),
        Index("ix_market_quote_trace", "trace_id"),
        Index("ix_market_quote_observation", "observation_id"),
    )
    content_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    observation_id: Mapped[str] = mapped_column(String(36), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(36), nullable=False)
    provider: Mapped[str] = mapped_column(ForeignKey("providers.provider_id"), nullable=False)
    native_id: Mapped[str | None] = mapped_column(String(500))
    symbol: Mapped[str] = mapped_column(ForeignKey("instruments.symbol"), nullable=False)
    bid: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    ask: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    last: Mapped[Decimal | None] = mapped_column(Numeric(28, 10))
    provider_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ProviderStateRow(Base):
    __tablename__ = "provider_state"
    __table_args__ = (
        CheckConstraint("consecutive_failures >= 0", name="ck_provider_state_consecutive_failures"),
        CheckConstraint("reconnect_count >= 0", name="ck_provider_state_reconnect_count"),
    )
    provider_id: Mapped[str] = mapped_column(ForeignKey("providers.provider_id"), primary_key=True)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_message_received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_failure_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    reconnect_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(1000))
