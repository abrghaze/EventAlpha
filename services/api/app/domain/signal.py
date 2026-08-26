from __future__ import annotations

from datetime import timedelta
from math import tanh

from app.contracts import AIEventAnalysis, Action, FeatureSnapshot, SignalCandidate


def _action(score: float, probability: float) -> Action:
    if probability < 0.55:
        return Action.HOLD
    if score >= 0.72:
        return Action.STRONG_BUY
    if score >= 0.35:
        return Action.BUY
    if score <= -0.72:
        return Action.STRONG_SELL
    if score <= -0.35:
        return Action.SELL
    return Action.HOLD


def create_candidate(analysis: AIEventAnalysis, features: FeatureSnapshot) -> SignalCandidate:
    """Fuse independent evidence using documented, versioned baseline weights."""
    entity = next((item for item in analysis.entities if item.ticker == features.symbol), None)
    if entity is None:
        raise ValueError(f"No evidence-bound entity exists for {features.symbol}")

    event_component = entity.impact * entity.confidence * analysis.novelty
    quant_component = (features.ret_15m * 8) + (features.sector_relative_ret_15m * 4)
    confirmation = min(features.volume_z_30m / 4, 1.0) * (1 if features.ret_15m >= 0 else -1)
    raw_edge = 0.55 * event_component + 0.30 * quant_component + 0.15 * confirmation
    score = tanh(raw_edge)
    probability = min(0.95, max(0.05, 0.50 + abs(score) * (1 - analysis.uncertainty) / 2))
    return SignalCandidate(
        symbol=features.symbol,
        event_id=analysis.event_id,
        analysis_id=analysis.analysis_id,
        feature_snapshot_id=features.snapshot_id,
        strategy_version="event-fusion-v0.1.0",
        as_of=features.as_of,
        horizon="4h",
        score=score,
        calibrated_probability=probability,
        proposed_action=_action(score, probability),
        expires_at=features.as_of + timedelta(hours=4),
        evidence_ids=analysis.evidence_source_ids,
        explanation="Interpretable event, price, sector-relative, and volume-confirmation fusion.",
    )
