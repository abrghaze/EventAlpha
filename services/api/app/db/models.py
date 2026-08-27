from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
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
