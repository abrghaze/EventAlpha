from __future__ import annotations

from datetime import UTC, datetime
from typing import overload
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from app.contracts import CanonicalEvent, EventMention, RawEnvelope
from app.db.models import EventMentionRow, EventRow, RawItemRow, SourceRow
from app.events.service import PersistedEventState, StoredItemIndex


@overload
def _utc(value: datetime) -> datetime: ...


@overload
def _utc(value: None) -> None: ...


def _utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def _canonical_event(row: EventRow, mentions: tuple[EventMention, ...]) -> CanonicalEvent:
    return CanonicalEvent(
        event_id=UUID(row.event_id),
        event_version=row.event_version,
        version_created_at=_utc(row.version_created_at),
        clustering_version=row.clustering_version,
        canonical_title=row.canonical_title,
        event_type=row.event_type,
        event_time=_utc(row.event_time),
        first_received_at=_utc(row.first_received_at),
        last_updated_at=_utc(row.last_updated_at),
        language=row.language,
        novelty=row.novelty,
        source_independence=row.source_independence,
        mentions=mentions,
    )


class SqlEventRepository:
    """Transactional persistence of one source item and its canonical event version."""

    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions

    def load_state(self) -> PersistedEventState:
        with self._sessions() as session:
            latest_versions = (
                select(
                    EventRow.event_id,
                    func.max(EventRow.event_version).label("event_version"),
                )
                .group_by(EventRow.event_id)
                .subquery()
            )
            latest_event_rows = tuple(
                session.scalars(
                    select(EventRow).join(
                        latest_versions,
                        (EventRow.event_id == latest_versions.c.event_id)
                        & (EventRow.event_version == latest_versions.c.event_version),
                    )
                )
            )
            joined = tuple(
                session.execute(
                    select(EventMentionRow, RawItemRow).join(
                        RawItemRow, EventMentionRow.raw_item_id == RawItemRow.id
                    )
                )
            )
        mentions_by_event: dict[str, list[EventMention]] = {}
        items: list[StoredItemIndex] = []
        for mention_row, raw_row in joined:
            mentions_by_event.setdefault(mention_row.event_id, []).append(
                EventMention(
                    raw_item_id=UUID(mention_row.raw_item_id),
                    source_id=mention_row.source_id,
                    independence_group=mention_row.independence_group,
                    published_at=_utc(mention_row.published_at),
                    received_at=_utc(mention_row.received_at),
                )
            )
            items.append(
                StoredItemIndex(
                    provider=raw_row.provider,
                    source_id=raw_row.source_id,
                    native_id=raw_row.native_id,
                    content_hash=raw_row.content_hash,
                    event_id=UUID(mention_row.event_id),
                )
            )
        events = tuple(
            _canonical_event(
                row,
                tuple(
                    sorted(
                        mentions_by_event.get(row.event_id, []),
                        key=lambda mention: mention.received_at,
                    )
                ),
            )
            for row in latest_event_rows
        )
        return PersistedEventState(events=events, items=tuple(items))

    def load_event_version(self, event_id: UUID, event_version: int) -> CanonicalEvent | None:
        """Reconstruct cumulative mention membership as known at a historical version."""
        with self._sessions() as session:
            row = session.get(EventRow, (str(event_id), event_version))
            if row is None:
                return None
            mention_rows = tuple(
                session.scalars(
                    select(EventMentionRow).where(
                        (EventMentionRow.event_id == str(event_id))
                        & (EventMentionRow.event_version <= event_version)
                    )
                )
            )
        mentions = tuple(
            sorted(
                (
                    EventMention(
                        raw_item_id=UUID(mention.raw_item_id),
                        source_id=mention.source_id,
                        independence_group=mention.independence_group,
                        published_at=_utc(mention.published_at),
                        received_at=_utc(mention.received_at),
                    )
                    for mention in mention_rows
                ),
                key=lambda mention: mention.received_at,
            )
        )
        return _canonical_event(row, mentions)

    def save(self, envelope: RawEnvelope, event: CanonicalEvent) -> None:
        with self._sessions.begin() as session:
            if session.get(SourceRow, envelope.source_id) is None:
                session.add(
                    SourceRow(
                        source_id=envelope.source_id,
                        provider=envelope.provider,
                        source_type=envelope.source_type,
                        credibility_prior=envelope.source_credibility_prior,
                        storage_policy=envelope.storage_policy.value,
                    )
                )
            session.merge(
                RawItemRow(
                    id=str(envelope.id),
                    trace_id=str(envelope.trace_id),
                    provider=envelope.provider,
                    source_id=envelope.source_id,
                    native_id=envelope.native_id,
                    event_time=envelope.event_time,
                    published_at=envelope.published_at,
                    received_at=envelope.received_at,
                    processed_at=envelope.processed_at,
                    title=envelope.title,
                    url=envelope.url,
                    language=envelope.language,
                    category=envelope.category,
                    content_hash=envelope.content_hash,
                    storage_policy=envelope.storage_policy.value,
                    independence_group=envelope.independence_group,
                    derived_attributes=envelope.derived_attributes,
                )
            )
            session.merge(
                EventRow(
                    event_id=str(event.event_id),
                    event_version=event.event_version,
                    version_created_at=event.version_created_at,
                    clustering_version=event.clustering_version,
                    canonical_title=event.canonical_title,
                    event_type=event.event_type,
                    event_time=event.event_time,
                    first_received_at=event.first_received_at,
                    last_updated_at=event.last_updated_at,
                    language=event.language,
                    novelty=event.novelty,
                    source_independence=event.source_independence,
                )
            )
            current_mention = next(
                mention for mention in event.mentions if mention.raw_item_id == envelope.id
            )
            session.merge(
                EventMentionRow(
                    raw_item_id=str(current_mention.raw_item_id),
                    event_id=str(event.event_id),
                    event_version=event.event_version,
                    source_id=current_mention.source_id,
                    independence_group=current_mention.independence_group,
                    published_at=current_mention.published_at,
                    received_at=current_mention.received_at,
                )
            )
