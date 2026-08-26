# EventAlpha implementation plan

## Executive summary and system understanding

EventAlpha is an evidence-driven US equities/ETF intelligence system, not an autonomous-profit claim or LLM trading bot. It records information availability, normalizes/clusters it, asks a cloud LLM for a structured impact hypothesis, combines it with deterministic market evidence, calibrates probability, and applies an overriding deterministic risk decision. Promotion is research -> point-in-time backtest -> walk-forward -> shadow -> paper -> explicit review; live trading is out of scope by default.

## Existing assessment and requirements classification

The initial repository was a complete planning pack with Word specifications, API contracts, diagrams, and a master prompt, but no source, Git repository, ignore policy, dependencies, CI, or secrets policy. The source pack now remains locally available in `project_reference/` and no longer clutters living engineering docs.

| Classification | Items |
| --- | --- |
| Fully defined | MVP universe, safety boundaries, architecture, contracts, provider candidates, SLOs, model routing, risk authority, dashboard modules, testing strategy |
| Assumption required | Compose runs local PostgreSQL/Redis; replay providers apply without credentials; baseline fusion uses documented versioned weights; authentication waits for admin mutations |
| Blocking | No Phase 0-5 blocker. Production vendors/licences, budget limits, cloud account, identity provider and any live-trading authority require future owner decisions. |

## Architecture, data, AI, quant, signal and risk

ADR-001 selects FastAPI modular monolith plus fast/batch workers, PostgreSQL/TimescaleDB, Redis Streams, S3-compatible archive, and Next.js. OpenAI runs server-side through Responses API structured outputs. Luna is the volume lane; Terra/Sol need auditable escalation. n8n is optional secondary automation only.

Adapters represent market, news, social, filings, macro and broker providers. Alpaca is initial market/paper adapter and IEX coverage is explicitly incomplete. GDELT, licensed news, official feeds, SEC EDGAR, FRED/ALFRED and optional X are independently normalized. Each source keeps provider/native ID, content hash, licence policy, event/published/received/processed times, trace ID and raw reference.

AI receives bounded evidence and emits versioned `AIEventAnalysis` validated by JSON Schema/Pydantic. It uses timeout, retry, rate-limit, circuit-breaker, routing, token/cost/latency telemetry and safe HOLD/AVOID degradation. Deterministic point-in-time features cover returns, volatility, volume, liquidity, relative/regime and event context. An interpretable config-versioned fusion precedes empirical chronological calibration. Risk gates freshness, provider health, evidence, volatility/liquidity, exposure, drawdown, approval, duplicate orders and kill switch; it is final authority.

## Backtesting, dashboard, paper, security and operations

Replay uses received/as-of time, historical membership, ALFRED vintages, fees, spread, slippage, delay, corporate actions and version hashes. Reports include return, drawdown, risk-adjusted metrics, calibration, attribution and coverage gaps. Dashboard pages cover overview, events, signals/audit, assets, paper portfolio, backtests, model evaluation, data health and settings; stale data never appears as zero.

Paper orders require idempotency, pre-trade risk, ambiguity reconciliation and durable fills. Security requires backend-only secrets, future RBAC, TLS, rate limits, least privilege, audit logs, paper/live separation and CI scanning. Trace IDs, structured JSON logs, Prometheus-compatible metrics and optional Sentry cover provider freshness, queue lag, AI costs/latency, risk blocks and reconciliation.

PR CI runs tests, compile/lint/type checks, migrations validation, secret/dependency scan and container build. Release adds replay regression, IaC plan, backups, staged smoke tests and rollback. Docker Compose is local; production uses managed storage, secrets, private network, WAF/TLS and runbooks. Costs are metered per provider/model, with retention governed by licence.

## Milestones and definition of done

| Phase | Scope | Done when |
| --- | --- | --- |
| 0 | Foundation | Health/replay tests pass; secrets protected; live mode rejected; documentation and CI exist |
| 1 | Market spine | Adapter/replay ingestion, freshness/reconnect, bars/latest persistence and chart pass reconnect tests |
| 2 | Event foundation | News/official/SEC/FRED adapters, dedup, clustering and source priors produce one canonical event per duplicate cluster |
| 3 | Intelligence | Structured OpenAI router/telemetry and gold-set evaluation meet schema-valid gate |
| 4 | Quant/signals | Point-in-time feature/signal replay is deterministic and audit detail/live updates work |
| 5 | Risk | All hard gates, sizing, policy versions and red-team failures block unsafe signals |
| 6 | Backtesting | Cost/timing-aware chronological walk-forward replay produces reproducible reports |
| 7 | Shadow/paper | Broker idempotency/reconciliation and multi-week operational evidence meet acceptance gates |
| 8 | Production | IaC, backups/restore, RBAC, SLOs, scans, runbooks and licence review are verified |

## Risks and controls

Upstream outage, bad/late/duplicate data, LLM hallucination, licensing breach, overfit research, cost spikes, stale prices, duplicate orders and operational complexity are controlled by provider redundancy, audit timestamps, schema validation, licence policy, chronological evaluation, budgets, risk/idempotency and progressive promotion. Live work requires separate explicit authorization.
