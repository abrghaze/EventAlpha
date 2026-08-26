from __future__ import annotations

from fastapi import FastAPI, HTTPException, WebSocket

from app.config import Settings
from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider
from app.replay import demo_signal

settings = Settings.from_environment()
app = FastAPI(title="EventAlpha API", version="0.1.0")
market_data = MarketDataService(ReplayMarketDataProvider())


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {"status": "ok", "mode": "replay" if settings.demo_mode else "configured", "live_trading": False}


@app.get("/api/v1/providers/health")
async def provider_health() -> dict[str, object]:
    await market_data.refresh_watchlist(("ACME", "SPY"))
    return {"providers": [(await market_data.health()).model_dump(mode="json")]}


@app.get("/api/v1/signals")
def signals() -> dict[str, object]:
    return {"data": [demo_signal(settings).model_dump(mode="json")], "source": "replay"}


@app.get("/api/v1/assets/{symbol}/snapshot")
async def asset_snapshot(symbol: str) -> dict[str, object]:
    try:
        quote = await market_data.latest(symbol)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Unknown replay symbol: {symbol.upper()}") from error
    signal = demo_signal(settings)
    return {"symbol": symbol.upper(), "quote": quote.model_dump(mode="json"),
            "quote_freshness_ms": market_data.quote_freshness_ms(symbol),
            "signal": signal.model_dump(mode="json"), "source": "replay"}


@app.get("/api/v1/assets/{symbol}/bars")
async def asset_bars(symbol: str, timeframe: str = "1m", limit: int = 60) -> dict[str, object]:
    if limit < 1 or limit > 1000:
        raise HTTPException(status_code=422, detail="limit must be between 1 and 1000")
    try:
        bars = await market_data.bars(symbol, timeframe, limit)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=f"Unknown replay symbol: {symbol.upper()}") from error
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"symbol": symbol.upper(), "timeframe": timeframe,
            "data": [bar.model_dump(mode="json") for bar in bars], "source": "replay"}


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "system.connected", "version": 1, "data": {"mode": "replay"}})
    await websocket.close()
