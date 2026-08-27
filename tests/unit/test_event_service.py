from datetime import UTC, datetime, timedelta, timezone
from hashlib import sha256
from uuid import UUID

import pytest
from pydantic import ValidationError

from app.contracts import RawEnvelope, StoragePolicy
from app.events.service import EventService, PersistedEventState


def _item(
    native_id: str,
    source: str = "official",
    received_at: datetime | None = None,
    independence_group: str | None = None,
    content: str = "ACME raised its full-year outlook.",
) -> RawEnvelope:
    return RawEnvelope(
        provider="fixture",
        source_id=source,
        native_id=native_id,
        published_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        received_at=received_at or datetime(2026, 8, 26, 12, 1, tzinfo=UTC),
        title="ACME raises outlook",
        content=content,
        url="https://example.invalid/acme",
        language="en",
        category="earnings",
        content_hash=sha256(content.encode()).hexdigest(),
        storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
        independence_group=independence_group,
    )


def test_content_duplicates_form_one_canonical_event_with_mentions() -> None:
    service = EventService()
    first = service.ingest(_item("one"))
    second = service.ingest(_item("two", source="wire"))
    assert first.created
    assert not second.created
    assert len(second.event.mentions) == 2
    assert second.event.source_independence == 0.75


def test_syndicated_mentions_do_not_overstate_source_independence() -> None:
    service = EventService()
    service.ingest(_item("one", independence_group="acme-release"))
    result = service.ingest(_item("two", source="wire", independence_group="acme-release"))
    assert result.event.source_independence == 0.5


def test_similar_headline_outside_cluster_window_creates_a_new_event() -> None:
    service = EventService()
    first_time = datetime(2026, 8, 26, 12, 1, tzinfo=UTC)
    first = service.ingest(_item("one", received_at=first_time))
    second = service.ingest(
        _item(
            "two",
            source="wire",
            received_at=first_time + timedelta(hours=25),
        )
    )
    assert first.event.event_id != second.event.event_id
    assert second.created


def test_out_of_order_mentions_keep_monotonic_bounds_and_sorted_lineage() -> None:
    service = EventService()
    later = datetime(2026, 8, 26, 12, 1, tzinfo=UTC)
    earlier = later - timedelta(hours=2)
    service.ingest(_item("one", received_at=later))
    result = service.ingest(_item("two", source="wire", received_at=earlier))
    assert result.event.first_received_at == earlier
    assert result.event.last_updated_at == later
    assert [mention.received_at for mention in result.event.mentions] == [earlier, later]


def test_native_id_is_idempotent() -> None:
    service = EventService()
    first = service.ingest(_item("one"))
    repeat = service.ingest(_item("one"))
    assert not repeat.created
    assert repeat.idempotent
    assert repeat.event.event_id == first.event.event_id
    assert len(repeat.event.mentions) == 1


def test_raw_envelope_rejects_naive_availability_time() -> None:
    payload = _item("one").model_dump()
    payload["received_at"] = datetime(2026, 8, 26, 12, 1)  # noqa: DTZ001 - invalid fixture
    with pytest.raises(ValidationError, match="timestamp must include a timezone"):
        RawEnvelope.model_validate(payload)


def test_raw_envelope_normalizes_all_audit_times_to_utc() -> None:
    offset = timezone(timedelta(hours=2))
    local_time = datetime(2026, 8, 26, 14, 1, tzinfo=offset)
    payload = _item("one").model_dump()
    for field in ("event_time", "published_at", "received_at", "processed_at"):
        payload[field] = local_time
    envelope = RawEnvelope.model_validate(payload)
    assert envelope.event_time == datetime(2026, 8, 26, 12, 1, tzinfo=UTC)
    assert envelope.published_at == envelope.received_at == envelope.processed_at


def test_persistence_failure_does_not_leave_ghost_event() -> None:
    class FailingPersistence:
        def load_state(self) -> PersistedEventState:
            return PersistedEventState()

        def load_event_version(self, event_id: UUID, event_version: int) -> None:
            return None

        def save(self, envelope: RawEnvelope, event: object) -> None:
            raise RuntimeError("database unavailable")

    service = EventService(FailingPersistence())
    try:
        service.ingest(_item("one"))
    except RuntimeError as error:
        assert str(error) == "database unavailable"
    else:
        raise AssertionError("persistence failure must propagate")
    assert service.list_events() == ()
