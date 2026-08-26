# Development status

Updated: 2026-08-26

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
- Enforced Phase 0 safety: live configuration raises at startup and replay makes no provider, OpenAI or broker calls.

## In progress

- The Phase 2 ingestion foundation is complete and ready for local commit. The next Phase 2 slice is real provider adapters and source registry persistence.

## Remaining

- Durable database/migrations, real provider adapters (Alpaca; licensed news/official feeds; SEC; FRED/ALFRED), source registry persistence, OpenAI client/evals, quant storage/calibration, full policies, backtesting, paper broker, RBAC and cloud hardening.

## Known limitations

- Docker CLI is absent on this machine, so Compose cannot be run here.
- Credentials, licences, budgets, cloud and identity choices are absent by design and not Phase 0 blockers.
- The GitHub push has not occurred because this environment requires a further explicit approval before uploading the complete proprietary project pack to the remote.

## Next milestone

Phase 2 continuation: implement and contract-test real source adapters, then persist source registry, raw items and canonical events through database migrations.
