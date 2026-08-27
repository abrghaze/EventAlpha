from __future__ import annotations

import argparse
import asyncio

from app.config import Settings
from app.db.factory import create_database_engine, market_repository_for_engine
from app.db.locks import postgres_advisory_lease
from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider

MARKET_INGESTION_ADVISORY_LOCK_ID = 4_534_940_723
WATCHLIST = ("ACME", "SPY")


async def ingest_once(service: MarketDataService) -> tuple[int, int]:
    refreshed_quotes = await service.refresh_watchlist(WATCHLIST)
    refreshed_bars = await service.refresh_bars(WATCHLIST, "1m", 60)
    return refreshed_quotes, refreshed_bars


async def main(continuous: bool = False) -> None:
    settings = Settings.from_environment()
    if settings.replay_at is None:
        provider = ReplayMarketDataProvider()
    else:
        replay_at = settings.replay_at
        provider = ReplayMarketDataProvider(lambda: replay_at)
    if settings.database_url:
        engine = create_database_engine(settings.database_url)
        persistence = market_repository_for_engine(engine)
    else:
        engine = None
        persistence = None
    service = MarketDataService(provider, persistence=persistence)
    try:
        with postgres_advisory_lease(
            engine,
            MARKET_INGESTION_ADVISORY_LOCK_ID,
            "Another market ingestion worker already owns the database lease",
        ):
            while True:
                refreshed_quotes, refreshed_bars = await ingest_once(service)
                print(f"market observations: {refreshed_quotes} quotes; {refreshed_bars} bars")
                if not continuous:
                    break
                await asyncio.sleep(settings.market_poll_seconds)
    finally:
        if engine is not None:
            engine.dispose()


def cli() -> None:
    parser = argparse.ArgumentParser(description="Ingest EventAlpha market observations")
    parser.add_argument("--continuous", action="store_true")
    arguments = parser.parse_args()
    asyncio.run(main(continuous=arguments.continuous))


if __name__ == "__main__":
    cli()
