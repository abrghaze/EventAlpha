from __future__ import annotations

import asyncio

from app.market.service import MarketDataService
from app.providers.replay_market import ReplayMarketDataProvider


async def main() -> None:
    """Phase 1 worker entry point; provider streams will replace replay in production."""
    service = MarketDataService(ReplayMarketDataProvider())
    refreshed = await service.refresh_watchlist(("ACME", "SPY"))
    print(f"refreshed {refreshed} replay quotes")


if __name__ == "__main__":
    asyncio.run(main())
