from __future__ import annotations

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import sessionmaker

from app.db.event_repository import SqlEventRepository
from app.db.market_repository import SqlMarketRepository
from app.db.models import Base
from app.events.service import EventService


def create_database_engine(database_url: str, create_schema: bool = False) -> Engine:
    engine = create_engine(database_url, pool_pre_ping=True)
    if create_schema:
        Base.metadata.create_all(engine)
    return engine


def build_persistent_event_service(
    database_url: str, create_schema: bool = False
) -> tuple[EventService, Engine]:
    """Create a persistent service; automatic schema creation is development-only."""
    engine = create_database_engine(database_url, create_schema)
    sessions = sessionmaker(engine, expire_on_commit=False)
    return EventService(SqlEventRepository(sessions)), engine


def market_repository_for_engine(engine: Engine) -> SqlMarketRepository:
    return SqlMarketRepository(sessionmaker(engine, expire_on_commit=False))
