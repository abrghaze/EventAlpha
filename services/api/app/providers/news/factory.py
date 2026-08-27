from __future__ import annotations

import httpx

from app.config import Settings
from app.providers.news.base import NewsProvider
from app.providers.news.http_sources import (
    FredObservationProvider,
    OfficialRssProvider,
    SecSubmissionsProvider,
)
from app.providers.news.replay import ReplayNewsProvider


def build_news_providers(settings: Settings, client: httpx.AsyncClient) -> tuple[NewsProvider, ...]:
    if settings.event_source_mode == "replay":
        return (ReplayNewsProvider(),)

    providers: list[NewsProvider] = [
        OfficialRssProvider(client, feed.url, feed.source_id, feed.category)
        for feed in settings.official_rss_feeds
    ]
    if settings.sec_ciks:
        if settings.sec_user_agent is None:
            raise RuntimeError("SEC user agent missing after configuration validation")
        providers.extend(
            SecSubmissionsProvider(client, cik, settings.sec_user_agent)
            for cik in settings.sec_ciks
        )
    if settings.fred_series_ids:
        if settings.fred_api_key is None:
            raise RuntimeError("FRED API key missing after configuration validation")
        providers.extend(
            FredObservationProvider(client, series_id, settings.fred_api_key)
            for series_id in settings.fred_series_ids
        )
    return tuple(providers)
