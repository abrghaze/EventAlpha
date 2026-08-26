from datetime import datetime, timezone
from uuid import uuid4

from app.config import Settings
from app.contracts import AIEventAnalysis, Direction, EventEntity, FeatureSnapshot
from app.domain.risk import evaluate
from app.domain.signal import create_candidate


def _analysis() -> AIEventAnalysis:
    return AIEventAnalysis(
        event_id=uuid4(), model="fixture", prompt_version="v1", event_type="earnings",
        summary="Positive guidance", importance=0.8, novelty=0.8, uncertainty=0.1,
        entities=(EventEntity(entity_id="acme", ticker="ACME", direction=Direction.BULLISH,
                              impact=0.9, confidence=0.9, horizons=("4h",)),),
        evidence_source_ids=("source-1",), explanation="Fixture.",
    )


def _features(**overrides: object) -> FeatureSnapshot:
    values: dict[str, object] = {"symbol": "ACME", "as_of": datetime.now(timezone.utc),
        "feature_set_version": "v1", "ret_15m": 0.03, "realized_vol_30m": 0.02,
        "volume_z_30m": 2.0, "sector_relative_ret_15m": 0.01, "market_data_age_ms": 30}
    values.update(overrides)
    return FeatureSnapshot(**values)


def test_signal_fusion_is_bounded_and_has_evidence() -> None:
    candidate = create_candidate(_analysis(), _features())
    assert -1 <= candidate.score <= 1
    assert candidate.evidence_ids == ("source-1",)


def test_stale_data_blocks_candidate() -> None:
    features = _features(market_data_age_ms=15_001)
    candidate = create_candidate(_analysis(), features)
    decision = evaluate(candidate, features, Settings("test", True, False, False))
    assert not decision.approved
    assert decision.final_action.value == "AVOID"
    assert "MARKET_DATA_FRESH" in decision.reason_codes


def test_kill_switch_overrides_signal() -> None:
    features = _features()
    candidate = create_candidate(_analysis(), features)
    decision = evaluate(candidate, features, Settings("test", True, False, True))
    assert not decision.approved
    assert "KILL_SWITCH_OFF" in decision.reason_codes
