# MASTER BUILD PROMPT — EventAlpha AI

You are the lead software architect, staff backend engineer, quantitative engineer, AI engineer, frontend engineer, DevOps/SRE engineer and test engineer responsible for building **EventAlpha AI**.

## Mission
Build a professional, low-latency, cloud/API-first **event-driven trading decision-support platform** that ingests worldwide events and market data, converts unstructured information into structured financial-impact hypotheses with the OpenAI API, combines them with deterministic quantitative evidence, applies a hard risk engine, and exposes auditable BUY / SELL / HOLD / AVOID signals in a web dashboard.

This project must **not** claim guaranteed profitability. The LLM is not the final authority and must never directly send a live order. The mandatory initial environment is **US equities/ETFs + paper trading**. Live trading must remain disabled by default behind explicit future feature flags, separate credentials and human approval.

## Non-negotiable architecture decisions

1. Production LLM inference is cloud-based via OpenAI API, not local CPU/GPU.
2. Backend: Python + FastAPI + Pydantic, asynchronous I/O.
3. Frontend: Next.js + React + TypeScript.
4. Persistence: PostgreSQL; TimescaleDB for time-series workloads.
5. Event/cache layer: Redis + Redis Streams for MVP. Design interfaces so Kafka/Redpanda can be introduced later without rewriting domain logic.
6. Object storage: S3-compatible for raw payload/archive/backtest artifacts.
7. Quant stack: Polars, NumPy, SciPy; scikit-learn + LightGBM/XGBoost for tabular baselines. PyTorch only if empirical results justify it.
8. OpenAI: Responses API, strict Structured Outputs/JSON Schema, backend-only keys, model routing Luna → Terra → Sol.
9. Market MVP: provider adapter with Alpaca implementation; use WebSocket market stream and Alpaca paper trading. Do not confuse free IEX feed with full SIP market coverage.
10. News/events: provider adapters for NewsAPI/GDELT/official feeds; SEC EDGAR; FRED/ALFRED; X Filtered Stream if credentials exist.
11. Observability: OpenTelemetry traces + structured JSON logs + Prometheus-compatible metrics + error reporting.
12. Docker Compose for local development; Terraform-ready cloud deployment.
13. No secrets in browser, source code, logs or committed config.
14. Build a modular monolith plus async workers first. Do not create unnecessary microservices.

## Repository structure

Create a monorepo approximately:

```text
eventalpha/
  apps/
    web/
  services/
    api/
      app/
        api/
        auth/
        providers/
        ingestion/
        normalization/
        entity_resolution/
        ai_intelligence/
        quant/
        signal_engine/
        risk_engine/
        execution/
        backtesting/
        audit/
        observability/
        db/
        contracts/
    worker/
  packages/
    contracts/
  migrations/
  tests/
    unit/
    integration/
    contract/
    replay/
    ai_evals/
    e2e/
  infra/
    docker/
    terraform/
  docs/
  scripts/
  .github/workflows/
  .env.example
  docker-compose.yml
  README.md
```

You may refine folders, but preserve clear domain boundaries.

## Core runtime roles

Implement deployable roles:
- `web`: Next.js dashboard;
- `api`: FastAPI REST + WebSocket gateway;
- `worker-fast`: time-sensitive ingestion/normalization/AI/quant/signal tasks;
- `worker-batch`: historical ingestion/backtests/reprocessing.

Use shared PostgreSQL/TimescaleDB, Redis and object storage.

## Required frontend pages

Implement:
- `/live` live intelligence dashboard;
- `/events` global event radar;
- `/signals` signal list;
- `/signals/[id]` evidence/audit detail;
- `/assets/[symbol]` asset chart + event markers + features + signals;
- `/watchlists`;
- `/portfolio/paper`;
- `/backtests`;
- `/models` model/eval versions and metrics;
- `/data-health` provider freshness/health;
- `/settings/providers` admin-only provider config status, never raw secrets;
- `/settings/risk` versioned risk configuration.

The dashboard must display data freshness. Never show missing data as a legitimate zero.

## Provider adapter contracts

Create provider-neutral interfaces for:
- `MarketDataProvider`;
- `NewsProvider`;
- `SocialProvider`;
- `FilingsProvider`;
- `MacroProvider`;
- `BrokerProvider`.

Each must expose health, start/stop, timeout/retry behavior, normalized timestamps and typed EventAlpha outputs. Vendor-specific payloads must not leak throughout domain code.

## Canonical timestamps

Persist separately:
- `event_time`;
- `published_at`;
- `received_at`;
- `processed_at`;
- decision `as_of`.

All internal timestamps are timezone-aware UTC. Backtests must reproduce what was actually available by `as_of`; never use future information.

## Core data model

Implement migrations/models for at least:
- `providers`;
- `sources`;
- `raw_items`;
- `event_clusters` / `events`;
- `event_mentions`;
- `entities`;
- `assets`;
- `event_entities`;
- `ai_analyses`;
- `feature_sets` / `feature_snapshots`;
- `strategy_versions`;
- `signals`;
- `risk_policy_versions`;
- `risk_decisions`;
- `paper_orders`;
- `paper_fills`;
- `positions`;
- `backtest_runs`;
- `audit_events`;
- `provider_health`.

Important historical outputs are append/version oriented. Never overwrite an old AI analysis or signal to make history look cleaner.

## Ingestion behavior

Every external item receives:
- provider/source ID;
- native ID;
- received timestamp;
- publication/event timestamps where available;
- content hash/fingerprint;
- trace ID;
- raw payload location or sanitized raw fields;
- licensing/storage flags.

Implement idempotency, bounded retries with jitter, reconnect, health heartbeat, dead-letter handling and metrics.

## Deduplication/event clustering

Use a layered approach:
1. native ID;
2. URL/content hash;
3. normalized title fingerprint;
4. semantic similarity;
5. entity + category + temporal similarity.

Create one canonical event with multiple mentions. Do not treat syndicated copies as independent corroboration.

## Entity resolution

Resolve companies/tickers/sectors/countries/commodities/currencies/indices. Return confidence and ambiguity. Never silently map an ambiguous entity to a ticker.

## OpenAI implementation

Use the OpenAI **Responses API** from the backend. Use Structured Outputs with a strict JSON Schema represented by Pydantic models.

Create a model router:
- GPT-5.6 Luna: default, high-volume relevance/classification/event extraction;
- GPT-5.6 Terra: important, ambiguous or multi-causal events;
- GPT-5.6 Sol: rare high-impact/conflicting complex events.

Router decisions must be stored with reasons.

Track per call:
- model;
- prompt version;
- schema version;
- latency;
- input/output token usage;
- estimated cost;
- request/correlation ID;
- retry/escalation reason;
- validation status.

Use compact prompts and evidence. Never send the entire database context. Apply timeout, circuit breaker and bounded retry. If AI is unavailable or response remains invalid, do not fabricate a signal; mark analysis unavailable and degrade to HOLD/AVOID as required.

## Required AI structured output

Implement `AIEventAnalysis` with fields equivalent to:

```json
{
  "event_type": "string taxonomy value",
  "summary": "string",
  "importance": 0.0,
  "novelty": 0.0,
  "uncertainty": 0.0,
  "entities": [
    {
      "entity_id": "string",
      "ticker": "nullable string",
      "direction": "bullish|bearish|neutral|uncertain",
      "impact": 0.0,
      "confidence": 0.0,
      "horizons": ["15m","1h","4h","1d"],
      "causal_channels": ["string"]
    }
  ],
  "contradictions": ["string"],
  "invalidation_conditions": ["string"],
  "evidence_source_ids": ["string"],
  "explanation": "short string"
}
```

Validate numeric ranges and enums. The model must cite only provided evidence IDs and must state uncertainty instead of inventing missing facts.

## Quant feature engine

Create deterministic, versioned point-in-time features including at minimum:
- returns at 1m/5m/15m/1h;
- gap;
- realized volatility/range;
- volume and dollar-volume z-score;
- momentum/reference/VWAP distance where data permits;
- relative return vs sector/index;
- broad market regime/context;
- source credibility/novelty/event metadata;
- calendar/session context.

Design incremental updates for live operation and historical reproducibility for backtests.

## Signal fusion

Create one signal candidate per asset/horizon. Implement an interpretable baseline before sophisticated ML.

Conceptual baseline:

```text
raw_edge =
    w_event   * event_impact * source_credibility * novelty
  + w_quant   * quant_score
  + w_context * context_score
  + w_social  * social_score
  + w_confirm * market_confirmation
score = tanh(raw_edge)
```

Store weights/configuration as versioned strategy artifacts. Add a calibration layer that maps features/score to empirical probabilities using chronologically valid training data.

Do not hardcode forever-thresholds. Initial configurable action semantics:
- sufficiently strong positive calibrated edge → BUY candidate;
- sufficiently strong negative edge → SELL/REDUCE candidate;
- weak/unclear edge → HOLD;
- inadequate data/conflict/risk → AVOID.

Every signal contains:
- `signal_id`;
- asset;
- action;
- score [-1,1];
- calibrated confidence/probability;
- horizon;
- generated_at/as_of;
- expires_at/TTL;
- evidence IDs;
- feature snapshot ID;
- AI analysis ID;
- strategy version;
- invalidation conditions;
- explanation summary.

## Risk engine — final authority

The LLM and signal engine cannot bypass risk.

Implement deterministic gates for:
- stale market data;
- provider degraded;
- missing evidence;
- ambiguous symbol mapping;
- liquidity/spread;
- extreme volatility;
- max position/risk budget;
- sector/correlation concentration;
- max concurrent positions;
- daily/weekly paper loss limits;
- strategy/model not approved;
- drift alarm;
- duplicate signal/order;
- global kill switch.

Risk output is typed and includes `approved`, `final_action`, `size_cap`, `reason_codes`, `policy_version`.

## Paper execution

Integrate Alpaca paper trading through a broker adapter.

Requirements:
- paper only by default;
- unique idempotent client order IDs;
- pre-trade risk validation;
- order submit with timeout handling;
- reconciliation after ambiguous timeout;
- trade update stream;
- partial fill/cancel/reject handling;
- durable order/fill records;
- position reconciliation;
- kill switch.

Never interpret network timeout as definitive order failure without reconciliation.

## Backtesting engine

Build event-aware point-in-time replay. It must reproduce ingestion/decision timing and never use future knowledge.

Include:
- historical market data;
- event received times;
- macro vintages where relevant;
- chronological train/validation/test;
- walk-forward evaluation;
- transaction costs;
- spread/slippage;
- latency/order delay assumptions;
- corporate actions;
- benchmark/sector-relative results;
- outcome labels at 15m/1h/4h/1d.

Report at minimum:
- net return;
- drawdown;
- Sharpe/Sortino where meaningful;
- hit rate;
- profit factor;
- turnover;
- exposure;
- performance by event type/horizon/confidence;
- Brier score/calibration;
- max favorable/adverse excursion.

## Promotion gates

A strategy version follows:
`research → point-in-time backtest → walk-forward/out-of-sample → shadow live → paper trading → explicit human risk review → optional future live canary`.

Do not implement automatic promotion to live.

## REST API

Implement versioned REST endpoints approximately:
- `GET /api/v1/health`;
- `GET /api/v1/providers/health`;
- `GET /api/v1/events`;
- `GET /api/v1/events/{id}`;
- `GET /api/v1/signals`;
- `GET /api/v1/signals/{id}`;
- `GET /api/v1/assets/{symbol}/snapshot`;
- `GET /api/v1/assets/{symbol}/bars`;
- `GET /api/v1/portfolio/paper`;
- `GET /api/v1/orders/paper`;
- `POST /api/v1/backtests`;
- `GET /api/v1/backtests/{id}`;
- admin endpoints for versioned strategy/risk configuration with RBAC.

Use pagination, filters, typed errors and request IDs.

## WebSocket API

Provide `/ws` or versioned equivalent. Typed message envelope:

```json
{
  "type": "signal.created",
  "version": 1,
  "timestamp": "ISO-8601 UTC",
  "trace_id": "...",
  "data": {}
}
```

Support at least:
- `event.created`;
- `event.updated`;
- `signal.created`;
- `signal.updated`;
- `risk.blocked`;
- `paper_order.updated`;
- `provider.health`.

Use one upstream provider stream and fan out internally; do not open market-data vendor connections per browser user.

## Security

- backend-only API keys;
- `.env.example` contains names, never values;
- managed secret storage interface;
- TLS;
- auth + RBAC;
- CSRF/cookie protections appropriate to chosen auth design;
- rate limiting;
- input validation;
- SQL injection-safe ORM/queries;
- security headers;
- log sanitization;
- dependency and secret scanning;
- admin audit log;
- paper/live credential separation.

## Observability

Instrument OpenTelemetry traces end-to-end. Metrics:
- provider freshness;
- ingest rate/lag;
- Redis queue depth;
- AI p50/p95/error/tokens/cost;
- feature latency;
- signal counts by action;
- risk blocks by reason;
- DB/Redis latency;
- WebSocket push latency;
- paper order reconciliation.

Structured JSON logs include trace/event/signal/order IDs and never secrets.

## Testing requirements

Implement:
1. unit tests for pure functions/risk/features;
2. provider contract tests using saved sanitized fixtures;
3. integration tests with ephemeral PostgreSQL/Redis;
4. mocked HTTP/WebSocket failure tests;
5. AI gold-set eval tests;
6. replay/backtest regression fixtures;
7. E2E test from incoming event → signal UI → paper order lifecycle;
8. chaos cases: stale feed, duplicate news, provider timeout, malformed AI result, DB/Redis interruption, broker ambiguous timeout.

No critical business path is allowed to remain untested.

## CI/CD

GitHub Actions should run:
- Python formatting/lint/type checking;
- TypeScript lint/type checking;
- unit/integration tests;
- migrations validation;
- secret scan;
- dependency/security scan;
- Docker build;
- selected AI evals with controlled budget/fixtures;
- release smoke tests.

## Local developer experience

A new developer must be able to:
1. copy `.env.example` to `.env`;
2. start PostgreSQL/Redis and services with documented Docker Compose commands;
3. run migrations;
4. optionally use mock/replay providers without paid API keys;
5. run tests;
6. open the web dashboard.

Provide realistic seeded/replay demo data. Make it visually obvious when the app is using replay/mock data.

## Performance targets

Design toward:
- market message → latest cache p95 <100ms after receipt;
- canonical fast event → Luna analysis target p95 <2.5s under normal conditions;
- event received → risk-reviewed signal target p95 <4s under normal conditions;
- signal publish → browser p95 <250ms;
- risk-only calculation p95 <100ms.

Measure upstream provider latency separately.

## Implementation order

Work in phases and keep main branch runnable:
0. repository/dev foundation;
1. market stream + chart + data health;
2. event/SEC/FRED/news ingestion + normalization;
3. OpenAI structured event intelligence;
4. quant features + signal engine;
5. risk engine;
6. point-in-time backtesting;
7. shadow + paper trading;
8. cloud/security/operational hardening.

At the end of each phase:
- run tests;
- update docs;
- state what is complete;
- state remaining limitations;
- do not hide mocked behavior.

## Coding standards

- typed Python and TypeScript;
- small focused modules;
- dependency inversion for providers;
- no hardcoded secrets/URLs/prices/weights where configuration belongs;
- UTC internally;
- Decimal for money where precision matters;
- idempotency for ingestion and orders;
- migrations for schema changes;
- async code must have cancellation/timeouts;
- comments explain why, not obvious syntax;
- no placeholder TODOs in core paths when claiming a phase complete.

## Required final deliverables

Produce:
- runnable source repository;
- Docker Compose local environment;
- migrations;
- API and WebSocket schemas;
- provider adapters and replay/mocks;
- test suite;
- architecture docs/diagrams;
- README with exact startup commands;
- operational runbooks;
- sample dashboards/screens;
- backtest/paper reports;
- security/configuration documentation.

## Final quality rule

If a choice is ambiguous, prefer **correctness, auditability, latency measurement, safe degradation and testability** over flashy AI behavior. EventAlpha should be able to explain exactly what information existed, which model/code versions processed it, why a signal was produced or blocked, and what happened afterward.
