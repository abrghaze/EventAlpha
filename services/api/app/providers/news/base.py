from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from app.contracts import RawEnvelope


class NewsProvider(Protocol):
    """Common contract for licensed news, official sources, SEC and macro adapters."""

    name: str

    def stream_items(self) -> AsyncIterator[RawEnvelope]: ...
