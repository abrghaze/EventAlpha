from datetime import UTC, datetime, timedelta
from hashlib import sha256

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.contracts import RawEnvelope, StoragePolicy
from app.db.event_repository import SqlEventRepository
from app.db.models import Base, EventMentionRow, EventRow, RawItemRow, SourceRow
from app.events.service import EventService


def _item(
    native_id: str | None, source_id: str, received_at: datetime | None = None
) -> RawEnvelope:
    return RawEnvelope(
        provider="fixture",
        source_id=source_id,
        source_type="test_fixture",
        native_id=native_id,
        published_at=datetime(2026, 8, 26, 12, 0, tzinfo=UTC),
        received_at=received_at or datetime(2026, 8, 26, 12, 1, tzinfo=UTC),
        title="ACME raises outlook",
        content="ACME raised its outlook.",
        url=f"https://example.invalid/{native_id}",
        language="en",
        category="earnings",
        content_hash=sha256(b"same-cluster").hexdigest(),
        storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
        independence_group=source_id,
        derived_attributes={"fixture": native_id or "content-hash"},
    )


def test_event_ingestion_persists_auditable_cluster_transactionally() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    repository = SqlEventRepository(sessions)
    service = EventService(repository)
    first = service.ingest(_item("official-1", "official"))
    second = service.ingest(_item("wire-1", "wire"))
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(SourceRow)) == 2
        assert session.scalar(select(func.count()).select_from(RawItemRow)) == 2
        assert session.scalar(select(func.count()).select_from(EventRow)) == 2
        assert session.scalar(select(func.count()).select_from(EventMentionRow)) == 2
        versions = tuple(session.scalars(select(EventRow).order_by(EventRow.event_version)))
        assert [row.event_version for row in versions] == [1, 2]
        raw_items = tuple(session.scalars(select(RawItemRow).order_by(RawItemRow.source_id)))
        assert [row.derived_attributes for row in raw_items] == [
            {"fixture": "official-1"},
            {"fixture": "wire-1"},
        ]
        source_types = {
            row.source_id: row.source_type for row in session.scalars(select(SourceRow))
        }
        assert source_types == {"official": "test_fixture", "wire": "test_fixture"}
        for source in session.scalars(select(SourceRow)):
            assert source.credibility_prior == 0.5
            assert source.storage_policy == StoragePolicy.METADATA_AND_DERIVED_ONLY.value
    historical_v1 = repository.load_event_version(first.event.event_id, 1)
    historical_v2 = repository.load_event_version(second.event.event_id, 2)
    assert historical_v1 is not None and len(historical_v1.mentions) == 1
    assert historical_v2 is not None and len(historical_v2.mentions) == 2


def test_native_id_replay_is_not_persisted_twice() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    service = EventService(SqlEventRepository(sessions))
    item = _item("official-1", "official")
    service.ingest(item)
    service.ingest(item)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawItemRow)) == 1


def test_distinct_native_ids_allow_same_source_content_to_remain_auditable() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    service = EventService(SqlEventRepository(sessions))
    service.ingest(_item("official-1", "official"))
    result = service.ingest(_item("official-2", "official"))
    assert not result.idempotent
    assert len(result.event.mentions) == 2
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawItemRow)) == 2
        assert session.scalar(select(func.count()).select_from(EventMentionRow)) == 2


def test_restart_hydrates_idempotency_and_event_indexes() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    EventService(SqlEventRepository(sessions)).ingest(_item("official-1", "official"))
    restarted = EventService(SqlEventRepository(sessions))
    replay = restarted.ingest(_item("official-1", "official"))
    assert replay.idempotent
    assert len(restarted.list_events()) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawItemRow)) == 1


def test_missing_native_id_is_idempotent_by_source_and_content_hash() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    service = EventService(SqlEventRepository(sessions))
    service.ingest(_item(None, "official"))
    replay = service.ingest(_item(None, "official"))
    assert replay.idempotent
    assert len(replay.event.mentions) == 1


def test_reader_refreshes_events_committed_by_worker_process() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    reader = EventService(SqlEventRepository(sessions))
    writer = EventService(SqlEventRepository(sessions))
    writer.ingest(_item("official-1", "official"))
    assert reader.list_events() == ()
    reader.refresh()
    assert len(reader.list_events()) == 1


def test_out_of_order_persistence_keeps_the_new_raw_item_and_sorted_lineage() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    service = EventService(SqlEventRepository(sessions))
    later = datetime(2026, 8, 26, 12, 1, tzinfo=UTC)
    earlier = later - timedelta(hours=2)
    service.ingest(_item("official-1", "official", later))
    service.ingest(_item("wire-1", "wire", earlier))

    restarted = EventService(SqlEventRepository(sessions))
    event = restarted.list_events()[0]
    assert [mention.received_at for mention in event.mentions] == [earlier, later]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(RawItemRow)) == 2
        assert session.scalar(select(func.count()).select_from(EventMentionRow)) == 2
