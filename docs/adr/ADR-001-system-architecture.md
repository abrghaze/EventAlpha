# ADR-001: Modular monolith with event-driven workers

- Status: Accepted
- Date: 2026-08-26
- Scope: EventAlpha MVP through paper trading

## Context

EventAlpha turns timestamped world events and market data into auditable, probabilistic research signals. It needs point-in-time replay, deterministic risk controls, provider portability, and a manageable operating model. An LLM is useful for text interpretation but must never directly issue an order.

## Options considered

| Option | Strength | Material drawback | Decision |
| --- | --- | --- | --- |
| Full custom platform | Best control over latency, backtests, risk, audit and brokers | Highest initial build effort | Selected as core |
| Automation-first / n8n | Strong scheduled workflows and notifications | Unsuitable for streaming, quantitative or execution authority | Secondary only |
| Hybrid custom + n8n | Uses automation where it is strongest | Requires explicit ownership boundaries | Selected operational pattern |
| Event-driven backend only | Lowest surface area | Insufficient research and audit visibility | Rejected for MVP UX |

## Decision

Build a Python FastAPI modular monolith with separate fast and batch workers. PostgreSQL (with TimescaleDB evaluation) is authoritative storage; Redis Streams is the MVP transient event bus/cache; object storage holds licensed raw archives and backtest artifacts. A Next.js dashboard reads typed REST and WebSocket summaries.

Provider adapters isolate all vendor schema. OpenAI Responses API calls run server-side and return Pydantic-validated structured analyses. Deterministic quant, signal, calibration, and risk modules remain independent. The risk engine is authoritative and can only reduce or block an action. Broker integration starts paper-only; live execution is unsupported and guarded by a startup rejection.

n8n may later run reports, alert fan-out, low-frequency enrichment, and administrative approvals. It must not own market streaming, canonical event state, feature calculation, signal fusion, risk decisions, backtesting, broker submission, or the audit ledger.

## Consequences

- One deployable codebase simplifies local development while preserving modules that can split later.
- Redis Streams avoids premature Kafka/Redpanda; stream semantics are isolated for a later replacement.
- Platform latency is separately measured from vendor latency.
- The first investment is data and safety quality rather than a misleading trading dashboard.

## Revisit triggers

Revisit the event bus after measured consumer lag/throughput exceeds Redis Streams, storage after tick-volume measurement, and service extraction only when real deployment/ownership boundaries require it.
