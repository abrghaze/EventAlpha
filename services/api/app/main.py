from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.db.factory import build_persistent_event_service, market_repository_for_engine
from app.events.replay import ReplayEventBootstrap
from app.events.service import EventService
from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider
from app.replay import demo_signal

settings = Settings.from_environment()
app = FastAPI(title="EventAlpha API", version="0.3.0")
BAR_STALE_AFTER_MS = {
    "1m": 120_000,
    "5m": 600_000,
    "15m": 1_800_000,
    "1h": 7_200_000,
    "1d": 172_800_000,
}
market_provider = ReplayMarketDataProvider()
database_engine: Engine | None
if settings.database_url:
    events, database_engine = build_persistent_event_service(
        settings.database_url, create_schema=False
    )
    market_data = MarketDataService(
        market_provider,
        persistence=market_repository_for_engine(database_engine),
        provider_reads_enabled=False,
    )
    event_bootstrap = None
else:
    events = EventService()
    database_engine = None
    event_bootstrap = ReplayEventBootstrap(events)
    market_data = MarketDataService(market_provider)


@app.get("/api/v1/health")
def health() -> JSONResponse:
    payload: dict[str, object] = {
        "status": "ok",
        "mode": "replay" if settings.demo_mode else "configured",
        "live_trading": False,
        "database": "not_configured",
    }
    if database_engine is None:
        return JSONResponse(content=payload)
    required_tables = {
        "sources",
        "raw_items",
        "events",
        "event_mentions",
        "providers",
        "instruments",
        "market_bar_observations",
        "market_quote_observations",
        "provider_state",
    }
    try:
        with database_engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        missing = required_tables - set(inspect(database_engine).get_table_names())
        if missing:
            raise RuntimeError(f"missing schema tables: {', '.join(sorted(missing))}")
    except (SQLAlchemyError, RuntimeError) as error:
        payload.update(
            status="degraded", database="unavailable", database_error=type(error).__name__
        )
        return JSONResponse(status_code=503, content=payload)
    payload["database"] = "connected"
    return JSONResponse(content=payload)


@app.get("/api/v1/providers/health")
async def provider_health() -> dict[str, object]:
    return {"providers": [(await market_data.health()).model_dump(mode="json")]}


@app.get("/api/v1/signals")
def signals() -> dict[str, object]:
    return {"data": [demo_signal(settings).model_dump(mode="json")], "source": "replay"}


@app.get("/api/v1/events")
async def list_events() -> dict[str, object]:
    if event_bootstrap is not None:
        await event_bootstrap.ensure_loaded()
    else:
        await run_in_threadpool(events.refresh)
    return {
        "data": [event.model_dump(mode="json") for event in events.list_events()],
        "source": "replay" if event_bootstrap is not None else "persistent",
    }


@app.get("/api/v1/events/{event_id}")
async def get_event(event_id: UUID) -> dict[str, object]:
    if event_bootstrap is not None:
        await event_bootstrap.ensure_loaded()
    else:
        await run_in_threadpool(events.refresh)
    event = events.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Unknown event")
    return {
        "data": event.model_dump(mode="json"),
        "source": "replay" if event_bootstrap is not None else "persistent",
    }


@app.get("/api/v1/events/{event_id}/versions/{event_version}")
async def get_event_version(event_id: UUID, event_version: int) -> dict[str, object]:
    if event_version < 1:
        raise HTTPException(status_code=422, detail="event_version must be positive")
    if event_bootstrap is not None:
        await event_bootstrap.ensure_loaded()
        event = events.get_event_version(event_id, event_version)
    else:
        event = await run_in_threadpool(events.get_event_version, event_id, event_version)
    if event is None:
        raise HTTPException(status_code=404, detail="Unknown event version")
    return {
        "data": event.model_dump(mode="json"),
        "source": "replay" if event_bootstrap is not None else "persistent",
    }


def _as_of_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(status_code=422, detail="as_of must include a timezone")
    return value.astimezone(UTC)


@app.get("/api/v1/assets/{symbol}/snapshot")
async def asset_snapshot(symbol: str, as_of: datetime | None = None) -> dict[str, object]:
    as_of_utc = _as_of_utc(as_of)
    try:
        quote = await market_data.latest(symbol, as_of_utc)
    except KeyError as error:
        persistent = database_engine is not None
        raise HTTPException(
            status_code=503 if persistent else 404,
            detail=(
                f"No persisted quote is available for {symbol.upper()}"
                if persistent
                else f"Unknown replay symbol: {symbol.upper()}"
            ),
        ) from error
    signal = demo_signal(settings)
    freshness_ms = market_data.quote_freshness_ms(symbol, as_of_utc, quote=quote)
    return {
        "symbol": symbol.upper(),
        "quote": quote.model_dump(mode="json"),
        "quote_freshness_ms": freshness_ms,
        "stale": freshness_ms is None or freshness_ms > 15_000,
        "signal": signal.model_dump(mode="json"),
        "source": quote.provider,
        "storage": "persistent" if database_engine is not None else "ephemeral",
    }


@app.get("/api/v1/assets/{symbol}/bars")
async def asset_bars(
    symbol: str,
    timeframe: str = "1m",
    limit: int = 60,
    as_of: datetime | None = None,
) -> dict[str, object]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    as_of_utc = _as_of_utc(as_of)
    try:
        bars = await market_data.bars(symbol, timeframe, limit, as_of_utc)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown replay symbol: {symbol.upper()}"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    freshness_ms = market_data.bar_freshness_ms(bars, as_of_utc)
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "data": [bar.model_dump(mode="json") for bar in bars],
        "availability": "available" if bars else "unavailable",
        "latest_received_at": max((bar.received_at for bar in bars), default=None),
        "bar_freshness_ms": freshness_ms,
        "stale": freshness_ms is None or freshness_ms > BAR_STALE_AFTER_MS[timeframe],
        "source": bars[0].provider if bars else market_data.provider_name,
        "storage": "persistent" if database_engine is not None else "ephemeral",
    }


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {"type": "system.connected", "version": 1, "data": {"mode": "replay"}}
    )
    await websocket.close()
