from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from app.db.event_repository import SqlEventRepository
from app.db.models import Base
from app.events.service import EventService


def build_persistent_event_service(
    database_url: str, create_schema: bool = False
) -> tuple[EventService, Engine]:
    """Create a persistent service; automatic schema creation is development-only."""
    engine = create_engine(database_url, pool_pre_ping=True)
    if create_schema:
        Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    return EventService(SqlEventRepository(sessions)), engine
