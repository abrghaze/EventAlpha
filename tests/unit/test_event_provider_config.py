import httpx
import pytest

from app.config import Settings
from app.providers.news.factory import build_news_providers


@pytest.mark.asyncio
async def test_configured_event_sources_are_parsed_and_built(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVENTALPHA_EVENT_SOURCE_MODE", "configured")
    monkeypatch.setenv(
        "EVENTALPHA_OFFICIAL_RSS_FEEDS",
        "federal-reserve|central_bank|https://example.invalid/fed.xml",
    )
    monkeypatch.setenv("EVENTALPHA_SEC_CIKS", "320193, 789019")
    monkeypatch.setenv("EVENTALPHA_FRED_SERIES_IDS", "DFF,CPIAUCSL")
    monkeypatch.setenv("SEC_USER_AGENT", "EventAlpha ops@example.com")
    monkeypatch.setenv("FRED_API_KEY", "fixture-key")

    settings = Settings.from_environment()
    async with httpx.AsyncClient() as client:
        providers = build_news_providers(settings, client)

    assert settings.official_rss_feeds[0].source_id == "federal-reserve"
    assert [provider.name for provider in providers] == [
        "official-rss",
        "sec-edgar",
        "sec-edgar",
        "fred",
        "fred",
    ]


def test_configured_sec_source_requires_policy_user_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EVENTALPHA_EVENT_SOURCE_MODE", "configured")
    monkeypatch.setenv("EVENTALPHA_SEC_CIKS", "320193")
    monkeypatch.delenv("SEC_USER_AGENT", raising=False)
    with pytest.raises(RuntimeError, match="SEC_USER_AGENT"):
        Settings.from_environment()


def test_replay_clock_requires_utc_offset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENTALPHA_REPLAY_AT", "2026-08-27T12:00:00")
    with pytest.raises(RuntimeError, match="must include a timezone"):
        Settings.from_environment()


def test_market_poll_interval_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("EVENTALPHA_MARKET_POLL_SECONDS", "0")
    with pytest.raises(RuntimeError, match="must be positive"):
        Settings.from_environment()
