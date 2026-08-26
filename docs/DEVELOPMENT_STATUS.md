# Development status

Updated: 2026-08-26

## Completed

- Audited and reorganized the original project pack into `project_reference/`.
- Added ignore policies and environment-variable-only configuration template.
- Recorded ADR-001 and the implementation plan.
- Created FastAPI contracts, replay-only event-to-signal-to-risk path, minimal Next.js shell, Compose setup, CI and tests.
- Enforced Phase 0 safety: live configuration raises at startup and replay makes no provider, OpenAI or broker calls.

## In progress

- Phase 1 has not started. The Phase 0 checkpoint is locally committed and ready for review.

## Remaining

- Durable database/migrations, providers, OpenAI client/evals, quant storage/calibration, full policies, backtesting, paper broker, RBAC and cloud hardening.

## Known limitations

- Docker CLI is absent on this machine, so Compose cannot be run here.
- Credentials, licences, budgets, cloud and identity choices are absent by design and not Phase 0 blockers.
- The GitHub push has not occurred because this environment requires a further explicit approval before uploading the complete proprietary project pack to the remote.

## Next milestone

Phase 1: provider-neutral market adapter, replay source, bar/latest persistence, freshness checks, Data Health and live chart.
