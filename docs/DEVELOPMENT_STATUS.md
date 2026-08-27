# Development status

Updated: 2026-08-27

## Completed

- Audited and reorganized the original project pack into `project_reference/`.
- Added ignore policies and environment-variable-only configuration template.
- Recorded ADR-001 and the implementation plan.
- Created FastAPI contracts, replay-only event-to-signal-to-risk path, minimal Next.js shell, Compose setup, CI and tests.
- Completed Phase 1: provider-neutral market contracts, deterministic replay ingestion, durable append-only quote/bar observations and revisions, point-in-time reads, persist-before-publish projection, separate market-age and ingestion-heartbeat freshness, bounded reconnect/backoff, idle-stream detection, advisory-lease worker ownership, and a gap-aware Live Market chart.
- Completed the Phase 2 event-ingestion foundation: timestamped/licensing-aware raw envelopes, provider-neutral event adapter, deterministic normalisation, content fingerprinting, native-ID idempotency, exact/near-title clustering, canonical-event/mention contracts, replay event worker, event APIs, and Event Radar.
- Phase 2 foundation verification passed: 13 Python tests; three replay source items formed two canonical events with the syndicated earnings item clustered into two mentions; and the Next.js production build generated seven routes.
- The first remote CI run identified CI configuration issues: ambiguous setuptools monorepo discovery and a secret-scan base equal to HEAD. Package discovery is now explicitly scoped to `services/api`, the scan uses the event-derived commit range, and CI now includes a clean npm dashboard build.
- Replacement CI passed all API, web, and secret-scan jobs. Official GitHub actions were then advanced to their current v7 releases to remove Node.js runtime deprecation annotations.
- Added contract-tested official RSS, SEC EDGAR, and FRED adapters with bounded HTTP timeouts, source-policy metadata, and point-in-time-safe timestamp semantics.
- Added runtime-configurable official RSS, SEC EDGAR, and FRED ingestion with credential preflight, bounded retry behavior, malformed/truncated payload rejection, and replay-safe defaults.
- Added SQLAlchemy source/raw-event/canonical-event/mention persistence, source types and neutral priors, UTC processing timestamps, append-only version history, historical lineage reconstruction, and restart-safe idempotency indexes.
- Added checksummed transactional migrations that reject incompatible/unversioned schemas, PostgreSQL migration and ingestion advisory locks, database-aware health, non-blocking API refresh, and migration -> ingestion -> API Compose readiness ordering.
- CI now repeats migration and replay ingestion against PostgreSQL, asserts schema/count invariants, runs an in-image ASGI smoke, and boots the image through its default Uvicorn command.
- Remote CI for the durable event-foundation milestone passed all API, web, PostgreSQL container, and secret-scan jobs.
- Current local verification passes 61 Python tests, Ruff formatting/lint, strict mypy, bytecode compilation, both replay-worker acceptance checks, YAML parsing, and the seven-route Next.js production build.
- Enforced Phase 0 safety: live configuration raises at startup and replay makes no provider, OpenAI or broker calls.

## In progress

- Final remote CI verification of the durable market-data milestone.

## Remaining

- Licensed production market/news adapters and ALFRED vintages; OpenAI client/evals; quant storage/calibration; full risk policies; backtesting; paper broker; RBAC; and cloud hardening.

## Known limitations

- Docker CLI is absent on this machine, so Compose cannot be run here.
- Credentials, licences, budgets, cloud and identity choices are absent by design and not Phase 0 blockers.
- The market provider is deterministic replay only; no licensed production market adapter is configured.
- Configured event adapters perform one bounded ingestion pass; continuous Redis Stream scheduling remains future operational work.

## Next milestone

Begin Phase 3 structured OpenAI event intelligence, model telemetry, and gold-set evaluation while keeping deterministic HOLD/AVOID degradation when AI is unavailable.
