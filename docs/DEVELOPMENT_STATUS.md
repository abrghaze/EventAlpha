# Development status

Updated: 2026-08-27

## Completed

- Audited and reorganized the original project pack into `project_reference/`.
- Added ignore policies and environment-variable-only configuration template.
- Recorded ADR-001 and the implementation plan.
- Created FastAPI contracts, replay-only event-to-signal-to-risk path, minimal Next.js shell, Compose setup, CI and tests.
- Completed Phase 1: a provider-neutral market adapter contract, deterministic replay market provider, typed OHLCV/quote contracts, in-process latest-value cache, explicit freshness health, market worker entry point, bars/snapshot/health API endpoints, and replay-aware Live Market/Data Health views.
- Phase 1 verification passed: 9 Python tests; API behavior checks; replay worker refresh for ACME/SPY; and Next.js production build with route/type generation.
- Completed the Phase 2 event-ingestion foundation: timestamped/licensing-aware raw envelopes, provider-neutral event adapter, deterministic normalisation, content fingerprinting, native-ID idempotency, exact/near-title clustering, canonical-event/mention contracts, replay event worker, event APIs, and Event Radar.
- Phase 2 foundation verification passed: 13 Python tests; three replay source items formed two canonical events with the syndicated earnings item clustered into two mentions; and the Next.js production build generated seven routes.
- The first remote CI run identified CI configuration issues: ambiguous setuptools monorepo discovery and a secret-scan base equal to HEAD. Package discovery is now explicitly scoped to `services/api`, the scan uses the event-derived commit range, and CI now includes a clean npm dashboard build.
- Replacement CI passed all API, web, and secret-scan jobs. Official GitHub actions were then advanced to their current v7 releases to remove Node.js runtime deprecation annotations.
- Added contract-tested official RSS, SEC EDGAR, and FRED adapters with bounded HTTP timeouts, source-policy metadata, and point-in-time-safe timestamp semantics.
- Added runtime-configurable official RSS, SEC EDGAR, and FRED ingestion with credential preflight, bounded retry behavior, malformed/truncated payload rejection, and replay-safe defaults.
- Added SQLAlchemy source/raw-event/canonical-event/mention persistence, source types and neutral priors, UTC processing timestamps, append-only version history, historical lineage reconstruction, and restart-safe idempotency indexes.
- Added checksummed transactional migrations that reject incompatible/unversioned schemas, PostgreSQL migration and ingestion advisory locks, database-aware health, non-blocking API refresh, and migration -> ingestion -> API Compose readiness ordering.
- CI now repeats migration and replay ingestion against PostgreSQL, asserts schema/count invariants, runs an in-image ASGI smoke, and boots the image through its default Uvicorn command.
- Current local verification passes 43 Python tests, Ruff formatting/lint, strict mypy, bytecode compilation, replay-worker acceptance, and the seven-route Next.js production build.
- Enforced Phase 0 safety: live configuration raises at startup and replay makes no provider, OpenAI or broker calls.

## In progress

- Final remote CI verification of the durable event-foundation milestone.

## Remaining

- Durable historical market-bar/quote storage and reconnect behavior; licensed production news and ALFRED vintages; OpenAI client/evals; quant storage/calibration; full risk policies; backtesting; paper broker; RBAC; and cloud hardening.

## Known limitations

- Docker CLI is absent on this machine, so Compose cannot be run here.
- Credentials, licences, budgets, cloud and identity choices are absent by design and not Phase 0 blockers.
- Configured adapters perform one bounded ingestion pass; continuous Redis Stream scheduling and persisted provider-health history remain future operational work.

## Next milestone

Close the remaining market-data-foundation definition of done with durable historical bar/quote persistence and reconnect-safe ingestion, then begin Phase 3 structured OpenAI event intelligence and gold-set evaluation.
