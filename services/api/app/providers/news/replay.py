from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from hashlib import sha256

from app.contracts import RawEnvelope, StoragePolicy
from app.providers.news.base import NewsProvider


def _hash(title: str, content: str) -> str:
    return sha256(f"{title.strip().casefold()}\n{content.strip().casefold()}".encode()).hexdigest()


class ReplayNewsProvider(NewsProvider):
    """Recorded events that validate event timing and duplicate clustering without network access."""

    name = "replay-news"

    async def stream_items(self) -> AsyncIterator[RawEnvelope]:
        received = datetime(2026, 8, 26, 14, 1, 5, tzinfo=UTC)
        title = "ACME raises full-year guidance after earnings"
        content = "ACME reported earnings and raised full-year revenue guidance."
        yield RawEnvelope(
            provider=self.name,
            source_id="acme-ir",
            source_type="investor_relations",
            native_id="acme-ir-20260826-01",
            published_at=received - timedelta(seconds=30),
            received_at=received,
            processed_at=received + timedelta(milliseconds=10),
            title=title,
            content=content,
            url="https://example.invalid/acme/earnings",
            language="en",
            category="earnings",
            content_hash=_hash(title, content),
            storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
            independence_group="acme-earnings-release",
        )
        yield RawEnvelope(
            provider=self.name,
            source_id="syndicated-wire",
            source_type="financial_news",
            native_id="wire-881",
            published_at=received - timedelta(seconds=20),
            received_at=received + timedelta(seconds=5),
            processed_at=received + timedelta(seconds=5, milliseconds=10),
            title=title,
            content=content,
            url="https://example.invalid/wire/acme-earnings",
            language="en",
            category="earnings",
            content_hash=_hash(title, content),
            storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
            independence_group="acme-earnings-release",
        )
        rate_title = "Federal Reserve publishes scheduled policy statement"
        rate_content = "Replay macro headline for independent event-cluster verification."
        yield RawEnvelope(
            provider=self.name,
            source_id="federal-reserve",
            source_type="central_bank",
            native_id="fed-20260826-statement",
            published_at=received + timedelta(minutes=1),
            received_at=received + timedelta(minutes=1, seconds=2),
            processed_at=received + timedelta(minutes=1, seconds=2, milliseconds=10),
            title=rate_title,
            content=rate_content,
            url="https://example.invalid/fed/statement",
            language="en",
            category="monetary_policy",
            content_hash=_hash(rate_title, rate_content),
            storage_policy=StoragePolicy.METADATA_AND_DERIVED_ONLY,
        )
