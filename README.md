# EventAlpha

EventAlpha is an evidence-driven, event-based trading intelligence and research platform for US equities and ETFs. It does not promise profit, and it does not allow an LLM to bypass deterministic risk controls. The initial execution path is research, replay, shadow, and paper trading only.

## Current milestone

Phases 0-2 are complete. EventAlpha now has a durable replay market spine and event foundation: provider-neutral bars and quotes, append-only corrections, point-in-time reads, freshness and reconnect state, time-preserving raw event envelopes, bounded duplicate clustering, source lineage and priors, append-only canonical event versions, Event Radar, PostgreSQL migrations, workers, Docker Compose, and CI.

Live trading is unsupported. Setting `EVENTALPHA_LIVE_TRADING_ENABLED=true` makes the API fail fast.

## Local setup

1. Copy `.env.example` to `.env` and leave provider values blank for replay mode.
2. Create a Python 3.11 virtual environment and install: `pip install -e ".[dev]"`.
3. Run tests: `pytest`.
4. Start the API: `uvicorn app.main:app --app-dir services/api --reload`.
5. Check `http://127.0.0.1:8000/api/v1/health` and `http://127.0.0.1:8000/api/v1/signals`.

For persistent mode, set `EVENTALPHA_DATABASE_URL`, run `python scripts/apply_migrations.py`, then run both `python services/worker/event_worker.py` and `python services/worker/market_worker.py` before starting the API. Add `--continuous` to the market worker for bounded polling with reconnect and heartbeat tracking. Migration files are checksummed and immutable; the runner refuses to silently adopt an unversioned or incompatible schema.

The market endpoints are `GET /api/v1/assets/ACME/bars`, `GET /api/v1/assets/ACME/snapshot`, and `GET /api/v1/providers/health`. They support timezone-aware `as_of` reads in persistent mode and distinguish provider identity (`source: replay-market`) from storage mode (`persistent` or `ephemeral`). Quote age uses provider time, while provider health separately measures ingestion heartbeat freshness. The data is deterministic replay, not live market data.

The replay event endpoints are `GET /api/v1/events`, `GET /api/v1/events/{id}`, and `GET /api/v1/events/{id}/versions/{version}`. The fixture intentionally includes a syndicated duplicate, which produces one canonical earnings event with two mentions while retaining its historical first version.

Phase 2 also includes contract-tested adapters for official RSS, SEC EDGAR submissions, and FRED observations. Replay is the default. Set `EVENTALPHA_EVENT_SOURCE_MODE=configured`, then provide one or more `EVENTALPHA_OFFICIAL_RSS_FEEDS`, `EVENTALPHA_SEC_CIKS`, or `EVENTALPHA_FRED_SERIES_IDS` values and the required `SEC_USER_AGENT`/`FRED_API_KEY`. RSS entries use `source_id|category|url` and are separated with semicolons. Normalized events persist transactionally to the source, raw-item, canonical-event-version, and mention schema. PostgreSQL advisory leases enforce one migration owner and one active event-ingestion worker.

Docker Compose is available after installing Docker: `docker compose up --build`. It waits for PostgreSQL, applies migrations, completes the initial event and market ingestion passes, starts the API, and retains one leased continuous market worker. CI repeats migrations and both workers to prove idempotency, checks PostgreSQL schema/count/API invariants, and starts the built image through its default Uvicorn command.

## Documentation

- [Architecture decision](docs/adr/ADR-001-system-architecture.md)
- [Implementation plan](docs/IMPLEMENTATION_PLAN.md)
- [Development status](docs/DEVELOPMENT_STATUS.md)
- `project_reference/` retains the original version-controlled architecture pack and diagrams.

## Safety boundaries

- OpenAI, market, news and broker credentials stay server-side environment variables.
- The current replay fixture never calls external providers, OpenAI, or a broker.
- A signal candidate is not an order; risk can only approve, reduce or block it.
- Production/paper execution waits for the documented promotion gates and a future owner decision.
