from __future__ import annotations

from uuid import UUID

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool

from app.config import Settings
from app.db.factory import build_persistent_event_service
from app.events.replay import ReplayEventBootstrap
from app.events.service import EventService
from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider
from app.replay import demo_signal

settings = Settings.from_environment()
app = FastAPI(title="EventAlpha API", version="0.2.0")
market_data = MarketDataService(ReplayMarketDataProvider())
database_engine: Engine | None
if settings.database_url:
    events, database_engine = build_persistent_event_service(
        settings.database_url, create_schema=False
    )
    event_bootstrap = None
else:
    events = EventService()
    database_engine = None
    event_bootstrap = ReplayEventBootstrap(events)


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
    required_tables = {"sources", "raw_items", "events", "event_mentions"}
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
    await market_data.refresh_watchlist(("ACME", "SPY"))
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


@app.get("/api/v1/assets/{symbol}/snapshot")
async def asset_snapshot(symbol: str) -> dict[str, object]:
    try:
        quote = await market_data.latest(symbol)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown replay symbol: {symbol.upper()}"
        ) from error
    signal = demo_signal(settings)
    return {
        "symbol": symbol.upper(),
        "quote": quote.model_dump(mode="json"),
        "quote_freshness_ms": market_data.quote_freshness_ms(symbol),
        "signal": signal.model_dump(mode="json"),
        "source": "replay",
    }


@app.get("/api/v1/assets/{symbol}/bars")
async def asset_bars(symbol: str, timeframe: str = "1m", limit: int = 60) -> dict[str, object]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    try:
        bars = await market_data.bars(symbol, timeframe, limit)
    except KeyError as error:
        raise HTTPException(
            status_code=404, detail=f"Unknown replay symbol: {symbol.upper()}"
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "data": [bar.model_dump(mode="json") for bar in bars],
        "source": "replay",
    }


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json(
        {"type": "system.connected", "version": 1, "data": {"mode": "replay"}}
    )
    await websocket.close()
