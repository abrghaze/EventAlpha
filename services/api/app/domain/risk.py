from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from app.config import Settings
from app.contracts import Action, FeatureSnapshot, RiskDecision, SignalCandidate

MAX_MARKET_DATA_AGE_MS = 15_000
MAX_REALIZED_VOL_30M = 0.10


def evaluate(candidate: SignalCandidate, features: FeatureSnapshot, settings: Settings) -> RiskDecision:
    """Authoritative deterministic gate. It can only reduce/deny a candidate."""
    checks = {
        "market_data_fresh": features.market_data_age_ms <= MAX_MARKET_DATA_AGE_MS,
        "volatility_ok": features.realized_vol_30m <= MAX_REALIZED_VOL_30M,
        "evidence_present": bool(candidate.evidence_ids),
        "kill_switch_off": not settings.kill_switch,
        "demo_mode": settings.demo_mode,
    }
    failures = tuple(name.upper() for name, ok in checks.items() if not ok)
    approved = not failures and candidate.proposed_action not in {Action.HOLD, Action.AVOID}
    final_action = candidate.proposed_action if approved else (Action.HOLD if not failures else Action.AVOID)
    size = Decimal("1000") if approved else Decimal("0")
    return RiskDecision(
        signal_id=candidate.signal_id,
        policy_version="paper-risk-v0.1.0",
        evaluated_at=datetime.now(timezone.utc),
        approved=approved,
        final_action=final_action,
        size_cap_notional=size,
        reason_codes=failures or (("INSUFFICIENT_EDGE",) if not approved else ()),
        checks=checks,
    )
