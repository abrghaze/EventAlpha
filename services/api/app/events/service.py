from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol
from uuid import UUID

from app.contracts import CanonicalEvent, EventMention, RawEnvelope

CLUSTER_WINDOW = timedelta(hours=24)
CLUSTERING_VERSION = "title-jaccard-v1"


def title_fingerprint(value: str) -> frozenset[str]:
    """Stable low-cost candidate matcher; embeddings are a later, measured upgrade."""
    return frozenset(
        token
        for token in "".join(char.lower() if char.isalnum() else " " for char in value).split()
        if len(token) > 2
    )


def jaccard(left: frozenset[str], right: frozenset[str]) -> float:
    return len(left & right) / len(left | right) if left or right else 0.0


@dataclass(frozen=True, slots=True)
class IngestResult:
    event: CanonicalEvent
    created: bool
    idempotent: bool


@dataclass(frozen=True, slots=True)
class StoredItemIndex:
    provider: str
    source_id: str
    native_id: str | None
    content_hash: str
    event_id: UUID


@dataclass(frozen=True, slots=True)
class PersistedEventState:
    events: tuple[CanonicalEvent, ...] = ()
    items: tuple[StoredItemIndex, ...] = ()


class EventPersistence(Protocol):
    def save(self, envelope: RawEnvelope, event: CanonicalEvent) -> None: ...

    def load_state(self) -> PersistedEventState: ...

    def load_event_version(self, event_id: UUID, event_version: int) -> CanonicalEvent | None: ...


class EventService:
    """In-memory Phase 2 store with production-shaped append-only behavior."""

    def __init__(self, persistence: EventPersistence | None = None) -> None:
        self._events: dict[UUID, CanonicalEvent] = {}
        self._versions: dict[tuple[UUID, int], CanonicalEvent] = {}
        self._by_identity: dict[tuple[str, str, str], UUID] = {}
        self._by_content_hash: dict[str, set[UUID]] = {}
        self._persistence = persistence
        if persistence is not None:
            self.refresh()

    def refresh(self) -> None:
        """Reload indexes so API readers observe commits made by the ingestion worker."""
        if self._persistence is None:
            return
        state = self._persistence.load_state()
        events = {event.event_id: event for event in state.events}
        identities: dict[tuple[str, str, str], UUID] = {}
        content_hashes: dict[str, set[UUID]] = {}
        for item in state.items:
            identity = item.native_id or f"sha256:{item.content_hash}"
            identities[(item.provider, item.source_id, identity)] = item.event_id
            content_hashes.setdefault(item.content_hash, set()).add(item.event_id)
        self._events = events
        self._versions = {(event.event_id, event.event_version): event for event in state.events}
        self._by_identity = identities
        self._by_content_hash = content_hashes

    def _similar_event(self, envelope: RawEnvelope) -> CanonicalEvent | None:
        fingerprint = title_fingerprint(envelope.title)
        exact_event_ids = self._by_content_hash.get(envelope.content_hash, set())
        candidates: list[tuple[tuple[int, float, float, str], CanonicalEvent]] = []
        for event in self._events.values():
            distance = abs(envelope.received_at - event.last_updated_at)
            similarity = jaccard(fingerprint, title_fingerprint(event.canonical_title))
            exact_content = event.event_id in exact_event_ids
            if event.event_type != envelope.category or distance > CLUSTER_WINDOW:
                continue
            if not exact_content and similarity < 0.85:
                continue
            rank = (
                1 if exact_content else 0,
                similarity,
                -distance.total_seconds(),
                str(event.event_id),
            )
            candidates.append((rank, event))
        return max(candidates, key=lambda candidate: candidate[0])[1] if candidates else None

    def ingest(self, envelope: RawEnvelope) -> IngestResult:
        identity = envelope.native_id or f"sha256:{envelope.content_hash}"
        key = (envelope.provider, envelope.source_id, identity)
        existing_id = self._by_identity.get(key)
        if existing_id is not None:
            return IngestResult(self._events[existing_id], created=False, idempotent=True)
        existing = self._similar_event(envelope)
        mention = EventMention(
            raw_item_id=envelope.id,
            source_id=envelope.source_id,
            independence_group=envelope.independence_group or envelope.source_id,
            published_at=envelope.published_at,
            received_at=envelope.received_at,
        )
        if existing is None:
            event = CanonicalEvent(
                canonical_title=envelope.title,
                event_type=envelope.category,
                event_time=envelope.event_time or envelope.published_at,
                first_received_at=envelope.received_at,
                last_updated_at=envelope.received_at,
                language=envelope.language,
                novelty=1.0,
                source_independence=0.5,
                event_version=1,
                version_created_at=envelope.processed_at,
                clustering_version=CLUSTERING_VERSION,
                mentions=(mention,),
            )
            created = True
        else:
            independence_group = envelope.independence_group or envelope.source_id
            unique_groups = {item.independence_group for item in existing.mentions} | {
                independence_group
            }
            source_independence = min(1.0, 0.5 + 0.25 * (len(unique_groups) - 1))
            mentions = tuple(
                sorted(existing.mentions + (mention,), key=lambda item: item.received_at)
            )
            event = existing.model_copy(
                update={
                    "event_version": existing.event_version + 1,
                    "version_created_at": envelope.processed_at,
                    "clustering_version": CLUSTERING_VERSION,
                    "first_received_at": min(existing.first_received_at, envelope.received_at),
                    "last_updated_at": max(existing.last_updated_at, envelope.received_at),
                    "source_independence": source_independence,
                    "mentions": mentions,
                }
            )
            created = False
        if self._persistence is not None:
            self._persistence.save(envelope, event)
        self._events[event.event_id] = event
        self._versions[(event.event_id, event.event_version)] = event
        self._by_content_hash.setdefault(envelope.content_hash, set()).add(event.event_id)
        self._by_identity[key] = event.event_id
        return IngestResult(event, created=created, idempotent=False)

    def list_events(self) -> tuple[CanonicalEvent, ...]:
        return tuple(
            sorted(self._events.values(), key=lambda event: event.first_received_at, reverse=True)
        )

    def get_event(self, event_id: UUID) -> CanonicalEvent | None:
        return self._events.get(event_id)

    def get_event_version(self, event_id: UUID, event_version: int) -> CanonicalEvent | None:
        event = self._versions.get((event_id, event_version))
        if event is None and self._persistence is not None:
            event = self._persistence.load_event_version(event_id, event_version)
            if event is not None:
                self._versions[(event_id, event_version)] = event
        return event

    async def ingest_many(self, items: Iterable[RawEnvelope]) -> tuple[IngestResult, ...]:
        return tuple(self.ingest(item) for item in items)
