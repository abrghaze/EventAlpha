from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from app.contracts import CanonicalEvent, EventMention, RawEnvelope


def title_fingerprint(value: str) -> frozenset[str]:
    """Stable low-cost candidate matcher; embeddings are a later, measured upgrade."""
    return frozenset(token for token in "".join(char.lower() if char.isalnum() else " " for char in value).split() if len(token) > 2)


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


@dataclass(frozen=True, slots=True)
class IngestResult:
    event: CanonicalEvent
    created: bool
    idempotent: bool


class EventService:
    """In-memory Phase 2 store with production-shaped append-only behavior."""

    def __init__(self) -> None:
        self._events: dict[UUID, CanonicalEvent] = {}
        self._by_native_id: dict[tuple[str, str, str], UUID] = {}
        self._by_content_hash: dict[str, UUID] = {}

    def _similar_event(self, envelope: RawEnvelope) -> CanonicalEvent | None:
        fingerprint = title_fingerprint(envelope.title)
        for event in self._events.values():
            if event.event_type == envelope.category and jaccard(fingerprint, title_fingerprint(event.canonical_title)) >= 0.85:
                return event
        return None

    def ingest(self, envelope: RawEnvelope) -> IngestResult:
        if envelope.native_id is not None:
            key = (envelope.provider, envelope.source_id, envelope.native_id)
            existing_id = self._by_native_id.get(key)
            if existing_id is not None:
                return IngestResult(self._events[existing_id], created=False, idempotent=True)
        event_id = self._by_content_hash.get(envelope.content_hash)
        existing = self._events.get(event_id) if event_id is not None else self._similar_event(envelope)
        mention = EventMention(raw_item_id=envelope.id, source_id=envelope.source_id,
                               published_at=envelope.published_at, received_at=envelope.received_at)
        if existing is None:
            event = CanonicalEvent(canonical_title=envelope.title, event_type=envelope.category,
                                   event_time=envelope.event_time or envelope.published_at,
                                   first_received_at=envelope.received_at, last_updated_at=envelope.received_at,
                                   language=envelope.language, novelty=1.0, source_independence=1.0,
                                   event_version=1, mentions=(mention,))
            self._events[event.event_id] = event
            self._by_content_hash[envelope.content_hash] = event.event_id
            created = True
        else:
            unique_sources = {item.source_id for item in existing.mentions} | {envelope.source_id}
            source_independence = min(1.0, 0.5 + 0.25 * len(unique_sources))
            event = existing.model_copy(update={"event_version": existing.event_version + 1,
                                                "last_updated_at": envelope.received_at,
                                                "source_independence": source_independence,
                                                "mentions": existing.mentions + (mention,)})
            self._events[event.event_id] = event
            self._by_content_hash[envelope.content_hash] = event.event_id
            created = False
        if envelope.native_id is not None:
            self._by_native_id[(envelope.provider, envelope.source_id, envelope.native_id)] = event.event_id
        return IngestResult(event, created=created, idempotent=False)

    def list_events(self) -> tuple[CanonicalEvent, ...]:
        return tuple(sorted(self._events.values(), key=lambda event: event.first_received_at, reverse=True))

    def get_event(self, event_id: UUID) -> CanonicalEvent | None:
        return self._events.get(event_id)

    async def ingest_many(self, items: Iterable[RawEnvelope]) -> tuple[IngestResult, ...]:
        return tuple(self.ingest(item) for item in items)
