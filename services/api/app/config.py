from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from os import getenv


def _bool(name: str, default: bool) -> bool:
    return getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _csv(name: str) -> tuple[str, ...]:
    return tuple(value.strip() for value in getenv(name, "").split(",") if value.strip())


def _positive_float(name: str, default: float) -> float:
    value = float(getenv(name, str(default)))
    if value <= 0:
        raise RuntimeError(f"{name} must be positive")
    return value


@dataclass(frozen=True, slots=True)
class OfficialRssFeedSettings:
    source_id: str
    category: str
    url: str


def _official_feeds() -> tuple[OfficialRssFeedSettings, ...]:
    """Parse `source_id|category|url` entries separated by semicolons."""
    feeds: list[OfficialRssFeedSettings] = []
    for entry in getenv("EVENTALPHA_OFFICIAL_RSS_FEEDS", "").split(";"):
        if not entry.strip():
            continue
        parts = tuple(part.strip() for part in entry.split("|", maxsplit=2))
        if len(parts) != 3 or not all(parts):
            raise RuntimeError(
                "EVENTALPHA_OFFICIAL_RSS_FEEDS entries must be source_id|category|url"
            )
        feeds.append(OfficialRssFeedSettings(parts[0], parts[1], parts[2]))
    return tuple(feeds)


def _optional_utc_datetime(name: str) -> datetime | None:
    value = getenv(name, "").strip()
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise RuntimeError(f"{name} must include a timezone")
    return parsed.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class Settings:
    environment: str
    demo_mode: bool
    live_trading_enabled: bool
    kill_switch: bool
    sec_user_agent: str | None = None
    fred_api_key: str | None = None
    database_url: str | None = None
    event_source_mode: str = "replay"
    official_rss_feeds: tuple[OfficialRssFeedSettings, ...] = ()
    sec_ciks: tuple[str, ...] = ()
    fred_series_ids: tuple[str, ...] = ()
    replay_at: datetime | None = None
    market_poll_seconds: float = 5.0

    @classmethod
    def from_environment(cls) -> Settings:
        live_enabled = _bool("EVENTALPHA_LIVE_TRADING_ENABLED", False)
        if live_enabled:
            raise RuntimeError("Live trading is deliberately unsupported in EventAlpha Phase 0.")
        event_source_mode = getenv("EVENTALPHA_EVENT_SOURCE_MODE", "replay").strip().lower()
        if event_source_mode not in {"replay", "configured"}:
            raise RuntimeError("EVENTALPHA_EVENT_SOURCE_MODE must be replay or configured")
        official_rss_feeds = _official_feeds()
        sec_ciks = _csv("EVENTALPHA_SEC_CIKS")
        fred_series_ids = _csv("EVENTALPHA_FRED_SERIES_IDS")
        sec_user_agent = getenv("SEC_USER_AGENT") or None
        fred_api_key = getenv("FRED_API_KEY") or None
        if event_source_mode == "configured":
            if not (official_rss_feeds or sec_ciks or fred_series_ids):
                raise RuntimeError("Configured event mode requires at least one event source")
            if sec_ciks and sec_user_agent is None:
                raise RuntimeError("SEC_USER_AGENT is required when SEC CIKs are configured")
            if fred_series_ids and fred_api_key is None:
                raise RuntimeError("FRED_API_KEY is required when FRED series are configured")
        return cls(
            environment=getenv("EVENTALPHA_ENV", "development"),
            demo_mode=_bool("EVENTALPHA_DEMO_MODE", True),
            live_trading_enabled=False,
            kill_switch=_bool("EVENTALPHA_KILL_SWITCH", False),
            sec_user_agent=sec_user_agent,
            fred_api_key=fred_api_key,
            database_url=getenv("EVENTALPHA_DATABASE_URL") or None,
            event_source_mode=event_source_mode,
            official_rss_feeds=official_rss_feeds,
            sec_ciks=sec_ciks,
            fred_series_ids=fred_series_ids,
            replay_at=_optional_utc_datetime("EVENTALPHA_REPLAY_AT"),
            market_poll_seconds=_positive_float("EVENTALPHA_MARKET_POLL_SECONDS", 5.0),
        )
