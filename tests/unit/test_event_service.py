from datetime import datetime, timezone
from hashlib import sha256

from app.contracts import RawEnvelope, StoragePolicy
from app.events.service import EventService


def _item(native_id: str, source: str = "official") -> RawEnvelope:
    content = "ACME raised its full-year outlook."
    return RawEnvelope(provider="fixture", source_id=source, native_id=native_id,
                       published_at=datetime(2026, 8, 26, 12, 0, tzinfo=timezone.utc),
                       received_at=datetime(2026, 8, 26, 12, 1, tzinfo=timezone.utc),
                       title="ACME raises outlook", content=content, url="https://example.invalid/acme",
                       language="en", category="earnings", content_hash=sha256("acme".encode()).hexdigest(),
                       storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY)


def test_content_duplicates_form_one_canonical_event_with_mentions() -> None:
    service = EventService()
    first = service.ingest(_item("one"))
    second = service.ingest(_item("two", source="wire"))
    assert first.created
    assert not second.created
    assert len(second.event.mentions) == 2
    assert second.event.source_independence == 1.0


def test_native_id_is_idempotent() -> None:
    service = EventService()
    first = service.ingest(_item("one"))
    repeat = service.ingest(_item("one"))
    assert not repeat.created
    assert repeat.idempotent
    assert repeat.event.event_id == first.event.event_id
    assert len(repeat.event.mentions) == 1
