from __future__ import annotations

from dataclasses import dataclass
from os import getenv


def _bool(name: str, default: bool) -> bool:
    return getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    demo_mode: bool
    live_trading_enabled: bool
    kill_switch: bool

    @classmethod
    def from_environment(cls) -> "Settings":
        live_enabled = _bool("EVENTALPHA_LIVE_TRADING_ENABLED", False)
        if live_enabled:
            raise RuntimeError("Live trading is deliberately unsupported in EventAlpha Phase 0.")
        return cls(
            environment=getenv("EVENTALPHA_ENV", "development"),
            demo_mode=_bool("EVENTALPHA_DEMO_MODE", True),
            live_trading_enabled=False,
            kill_switch=_bool("EVENTALPHA_KILL_SWITCH", False),
        )
