from __future__ import annotations

from fastapi import FastAPI, WebSocket

from app.config import Settings
from app.replay import demo_signal

settings = Settings.from_environment()
app = FastAPI(title="EventAlpha API", version="0.1.0")


@app.get("/api/v1/health")
def health() -> dict[str, object]:
    return {"status": "ok", "mode": "replay" if settings.demo_mode else "configured", "live_trading": False}


@app.get("/api/v1/providers/health")
def provider_health() -> dict[str, object]:
    return {"providers": [{"name": "replay", "status": "healthy", "freshness_ms": 0}]}


@app.get("/api/v1/signals")
def signals() -> dict[str, object]:
    return {"data": [demo_signal(settings).model_dump(mode="json")], "source": "replay"}


@app.get("/api/v1/assets/{symbol}/snapshot")
def asset_snapshot(symbol: str) -> dict[str, object]:
    signal = demo_signal(settings)
    return {"symbol": symbol.upper(), "signal": signal.model_dump(mode="json"), "source": "replay"}


@app.websocket("/api/v1/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    await websocket.send_json({"type": "system.connected", "version": 1, "data": {"mode": "replay"}})
    await websocket.close()
