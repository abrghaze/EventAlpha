# EventAlpha AI — API & JSON Contracts

These contracts are a design baseline. Implement them as versioned Pydantic models in the backend and generated/shared TypeScript types for the frontend.

## 1. Common envelope

```json
{
  "schema_version": 1,
  "id": "uuid",
  "trace_id": "uuid",
  "created_at": "2026-08-26T12:00:00Z"
}
```

## 2. RawEnvelope

```json
{
  "schema_version": 1,
  "id": "raw_uuid",
  "trace_id": "trace_uuid",
  "provider": "newsapi",
  "source_id": "reuters",
  "native_id": "provider-native-id-or-null",
  "event_time": null,
  "published_at": "2026-08-26T10:01:10Z",
  "received_at": "2026-08-26T10:01:12.120Z",
  "content_hash": "sha256...",
  "url": "https://...",
  "language": "en",
  "payload_ref": "s3://...",
  "storage_policy": "metadata_and_derived_only"
}
```

## 3. CanonicalEvent

```json
{
  "event_id": "evt_uuid",
  "event_version": 3,
  "canonical_title": "...",
  "event_type": "monetary_policy",
  "event_time": "2026-08-26T10:00:00Z",
  "first_received_at": "2026-08-26T10:01:12.120Z",
  "last_updated_at": "2026-08-26T10:02:45Z",
  "language": "en",
  "novelty": 0.91,
  "source_independence": 0.77,
  "mention_ids": ["raw_1", "raw_2"],
  "entity_links": [
    {"entity_id":"ent_1","confidence":0.99,"relation":"subject"}
  ]
}
```

## 4. AIEventAnalysis

```json
{
  "analysis_id": "aia_uuid",
  "event_id": "evt_uuid",
  "event_version": 3,
  "model": "gpt-5.6-luna",
  "prompt_version": "event-impact-v1.4.0",
  "schema_version": 2,
  "importance": 0.86,
  "novelty": 0.91,
  "uncertainty": 0.18,
  "entities": [
    {
      "entity_id": "ent_1",
      "ticker": "XYZ",
      "direction": "bearish",
      "impact": -0.74,
      "confidence": 0.83,
      "horizons": ["1h", "4h", "1d"],
      "causal_channels": ["revenue_exposure", "supply_constraint"]
    }
  ],
  "contradictions": [],
  "invalidation_conditions": ["official denial"],
  "evidence_source_ids": ["raw_1", "raw_2"],
  "explanation": "Short evidence-bound explanation.",
  "router": {"tier":"luna","escalated":false,"reason":null},
  "usage": {"input_tokens":800,"output_tokens":180,"latency_ms":840}
}
```

## 5. FeatureSnapshot

```json
{
  "snapshot_id": "fs_uuid",
  "asset_id": "asset_xyz",
  "symbol": "XYZ",
  "as_of": "2026-08-26T10:01:13Z",
  "feature_set_version": "market-v3.2",
  "values": {
    "ret_1m": -0.0041,
    "ret_15m": -0.0092,
    "realized_vol_30m": 0.031,
    "volume_z_30m": 2.4,
    "sector_relative_ret_15m": -0.0061,
    "market_regime_risk_off": 1.0
  },
  "market_data_age_ms": 82
}
```

## 6. SignalCandidate

```json
{
  "signal_id": "sig_uuid",
  "asset_id": "asset_xyz",
  "symbol": "XYZ",
  "event_id": "evt_uuid",
  "analysis_id": "aia_uuid",
  "feature_snapshot_id": "fs_uuid",
  "strategy_version": "event-fusion-v0.8.0",
  "as_of": "2026-08-26T10:01:13.400Z",
  "horizon": "4h",
  "score": -0.73,
  "calibrated_probability": 0.78,
  "proposed_action": "SELL",
  "expires_at": "2026-08-26T14:01:13.400Z",
  "invalidation_conditions": ["official denial"],
  "evidence_ids": ["raw_1", "raw_2"],
  "explanation": "..."
}
```

## 7. RiskDecision

```json
{
  "risk_decision_id": "risk_uuid",
  "signal_id": "sig_uuid",
  "policy_version": "paper-risk-v1.0.0",
  "evaluated_at": "2026-08-26T10:01:13.450Z",
  "approved": false,
  "final_action": "AVOID",
  "size_cap_notional": 0,
  "reason_codes": ["VOLATILITY_EXTREME"],
  "checks": {
    "market_data_fresh": true,
    "provider_healthy": true,
    "liquidity_ok": true,
    "volatility_ok": false,
    "daily_loss_budget_ok": true
  }
}
```

## 8. PublishedSignal

```json
{
  "signal_id": "sig_uuid",
  "symbol": "XYZ",
  "action": "AVOID",
  "score": -0.73,
  "confidence": 0.78,
  "horizon": "4h",
  "as_of": "2026-08-26T10:01:13.450Z",
  "expires_at": "2026-08-26T14:01:13.400Z",
  "risk": {"approved":false,"reason_codes":["VOLATILITY_EXTREME"]},
  "summary": "Bearish event, but trade blocked by volatility gate."
}
```

## 9. WebSocket envelope

```json
{
  "type": "signal.created",
  "version": 1,
  "timestamp": "2026-08-26T10:01:13.500Z",
  "trace_id": "trace_uuid",
  "data": {"signal_id":"sig_uuid","symbol":"XYZ","action":"AVOID"}
}
```

Allowed initial types:
- `event.created`
- `event.updated`
- `signal.created`
- `signal.updated`
- `risk.blocked`
- `paper_order.updated`
- `provider.health`

## 10. REST error contract

```json
{
  "error": {
    "code": "PROVIDER_UNAVAILABLE",
    "message": "Market data provider is temporarily unavailable.",
    "request_id": "req_uuid",
    "retryable": true,
    "details": {}
  }
}
```

Do not expose stack traces/secrets to clients.

## 11. Endpoint baseline

```text
GET  /api/v1/health
GET  /api/v1/providers/health
GET  /api/v1/events
GET  /api/v1/events/{id}
GET  /api/v1/signals
GET  /api/v1/signals/{id}
GET  /api/v1/assets/{symbol}/snapshot
GET  /api/v1/assets/{symbol}/bars
GET  /api/v1/portfolio/paper
GET  /api/v1/orders/paper
POST /api/v1/backtests
GET  /api/v1/backtests/{id}
WS   /api/v1/ws
```

## 12. Contract rules

- API versions are explicit.
- Schema changes are additive when possible.
- IDs are stable UUIDs/ULIDs.
- Money uses decimal-safe server representations.
- UTC ISO-8601 timestamps.
- List endpoints paginate.
- Mutating endpoints use auth/RBAC and idempotency where applicable.
- Provider payloads never become public API contracts directly.
- Every signal/risk/order response includes enough version metadata to find its audit bundle.
