from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Action(StrEnum):
    STRONG_BUY = "STRONG_BUY"
    BUY = "BUY"
    HOLD = "HOLD"
    SELL = "SELL"
    STRONG_SELL = "STRONG_SELL"
    AVOID = "AVOID"


class Direction(StrEnum):
    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"
    UNCERTAIN = "uncertain"


class ProviderStatus(StrEnum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"


class StoragePolicy(StrEnum):
    METADATA_AND_DERIVED_ONLY = "metadata_and_derived_only"
    LICENSED_RAW_ARCHIVE = "licensed_raw_archive"


class RawEnvelope(BaseModel):
    """Normalized source item with preserved availability timestamps."""

    model_config = ConfigDict(frozen=True)
    id: UUID = Field(default_factory=uuid4)
    trace_id: UUID = Field(default_factory=uuid4)
    provider: str
    source_id: str
    native_id: str | None = None
    event_time: datetime | None = None
    published_at: datetime | None = None
    received_at: datetime
    title: str = Field(min_length=1, max_length=1000)
    content: str = Field(min_length=1, max_length=10000)
    url: str = Field(min_length=1, max_length=2000)
    language: str = Field(min_length=2, max_length=10)
    category: str = Field(min_length=1, max_length=100)
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    storage_policy: StoragePolicy


class EventMention(BaseModel):
    model_config = ConfigDict(frozen=True)
    raw_item_id: UUID
    source_id: str
    published_at: datetime | None
    received_at: datetime


class CanonicalEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    event_id: UUID = Field(default_factory=uuid4)
    event_version: int = Field(ge=1)
    canonical_title: str
    event_type: str
    event_time: datetime | None
    first_received_at: datetime
    last_updated_at: datetime
    language: str
    novelty: float = Field(ge=0, le=1)
    source_independence: float = Field(ge=0, le=1)
    mentions: tuple[EventMention, ...]


class MarketBar(BaseModel):
    """Provider-neutral OHLCV bar; all timestamps are UTC-aware at boundaries."""

    model_config = ConfigDict(frozen=True)
    symbol: str = Field(pattern=r"^[A-Z.]{1,12}$")
    timeframe: Literal["1m", "5m", "15m", "1h", "1d"]
    timestamp: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)


class MarketQuote(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str = Field(pattern=r"^[A-Z.]{1,12}$")
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    last: Decimal = Field(gt=0)
    provider_timestamp: datetime
    received_at: datetime
    provider: str


class ProviderHealth(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    status: ProviderStatus
    last_message_at: datetime | None
    freshness_ms: int | None = Field(default=None, ge=0)
    detail: str | None = None


class EventEntity(BaseModel):
    model_config = ConfigDict(frozen=True)
    entity_id: str
    ticker: str | None = None
    direction: Direction
    impact: float = Field(ge=-1, le=1)
    confidence: float = Field(ge=0, le=1)
    horizons: tuple[Literal["15m", "1h", "4h", "1d"], ...]
    causal_channels: tuple[str, ...] = ()


class AIEventAnalysis(BaseModel):
    """Validated, evidence-bound LLM output; never an order instruction."""

    model_config = ConfigDict(frozen=True)
    analysis_id: UUID = Field(default_factory=uuid4)
    event_id: UUID
    model: str
    prompt_version: str
    schema_version: int = 1
    event_type: str
    summary: str = Field(min_length=1, max_length=1000)
    importance: float = Field(ge=0, le=1)
    novelty: float = Field(ge=0, le=1)
    uncertainty: float = Field(ge=0, le=1)
    entities: tuple[EventEntity, ...]
    contradictions: tuple[str, ...] = ()
    invalidation_conditions: tuple[str, ...] = ()
    evidence_source_ids: tuple[str, ...]
    explanation: str = Field(min_length=1, max_length=2000)


class FeatureSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    snapshot_id: UUID = Field(default_factory=uuid4)
    symbol: str = Field(pattern=r"^[A-Z.]{1,12}$")
    as_of: datetime
    feature_set_version: str
    ret_15m: float = Field(ge=-1, le=1)
    realized_vol_30m: float = Field(ge=0)
    volume_z_30m: float
    sector_relative_ret_15m: float = Field(ge=-1, le=1)
    market_data_age_ms: int = Field(ge=0)


class SignalCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_id: UUID = Field(default_factory=uuid4)
    symbol: str
    event_id: UUID
    analysis_id: UUID
    feature_snapshot_id: UUID
    strategy_version: str
    as_of: datetime
    horizon: Literal["15m", "1h", "4h", "1d"]
    score: float = Field(ge=-1, le=1)
    calibrated_probability: float = Field(ge=0, le=1)
    proposed_action: Action
    expires_at: datetime
    evidence_ids: tuple[str, ...]
    explanation: str


class RiskDecision(BaseModel):
    model_config = ConfigDict(frozen=True)
    risk_decision_id: UUID = Field(default_factory=uuid4)
    signal_id: UUID
    policy_version: str
    evaluated_at: datetime
    approved: bool
    final_action: Action
    size_cap_notional: Decimal = Field(ge=0)
    reason_codes: tuple[str, ...]
    checks: dict[str, bool]


class PublishedSignal(BaseModel):
    model_config = ConfigDict(frozen=True)
    signal_id: UUID
    symbol: str
    action: Action
    score: float
    confidence: float
    horizon: str
    as_of: datetime
    expires_at: datetime
    risk: RiskDecision
    summary: str
