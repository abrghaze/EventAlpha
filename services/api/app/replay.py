from __future__ import annotations

from datetime import datetime, timezone

from app.config import Settings
from app.contracts import AIEventAnalysis, Direction, EventEntity, FeatureSnapshot, PublishedSignal
from app.domain.risk import evaluate
from app.domain.signal import create_candidate


def demo_signal(settings: Settings) -> PublishedSignal:
    """Safe replay fixture. It makes no network or broker calls."""
    now = datetime.now(timezone.utc)
    event_id = __import__("uuid").uuid4()
    analysis = AIEventAnalysis(
        event_id=event_id,
        model="replay-fixture",
        prompt_version="replay-v1",
        event_type="earnings",
        summary="Replay: stronger-than-expected earnings guidance.",
        importance=0.72,
        novelty=0.66,
        uncertainty=0.22,
        entities=(EventEntity(
            entity_id="demo-acme",
            ticker="ACME",
            direction=Direction.BULLISH,
            impact=0.68,
            confidence=0.79,
            horizons=("1h", "4h"),
            causal_channels=("guidance",),
        ),),
        evidence_source_ids=("replay-source-001",),
        explanation="Replay fixture generated for local developer experience.",
    )
    features = FeatureSnapshot(
        symbol="ACME",
        as_of=now,
        feature_set_version="replay-market-v1",
        ret_15m=0.018,
        realized_vol_30m=0.032,
        volume_z_30m=2.1,
        sector_relative_ret_15m=0.007,
        market_data_age_ms=42,
    )
    candidate = create_candidate(analysis, features)
    decision = evaluate(candidate, features, settings)
    return PublishedSignal(
        signal_id=candidate.signal_id,
        symbol=candidate.symbol,
        action=decision.final_action,
        score=candidate.score,
        confidence=candidate.calibrated_probability,
        horizon=candidate.horizon,
        as_of=candidate.as_of,
        expires_at=candidate.expires_at,
        risk=decision,
        summary="Replay-only candidate; no paper order is created in Phase 0.",
    )
