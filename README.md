# EventAlpha

EventAlpha is an evidence-driven, event-based trading intelligence and research platform for US equities and ETFs. It does not promise profit, and it does not allow an LLM to bypass deterministic risk controls. The initial execution path is research, replay, shadow, and paper trading only.

## Current milestone

Phases 0 and 1 are implemented: architecture decision records, repository hygiene, typed FastAPI contracts, a safe replay-only event-to-signal-to-risk vertical slice, provider-neutral market-data contracts, typed replay bars/quotes, provider-freshness health, worker entry point, dashboard views, tests, Docker Compose setup, and CI.

Live trading is unsupported. Setting `EVENTALPHA_LIVE_TRADING_ENABLED=true` makes the API fail fast.

## Local setup

1. Copy `.env.example` to `.env` and leave provider values blank for replay mode.
2. Create a Python 3.11 virtual environment and install: `pip install -e ".[dev]"`.
3. Run tests: `pytest`.
4. Start the API: `uvicorn app.main:app --app-dir services/api --reload`.
5. Check `http://127.0.0.1:8000/api/v1/health` and `http://127.0.0.1:8000/api/v1/signals`.

The replay market endpoints are `GET /api/v1/assets/ACME/bars`, `GET /api/v1/assets/ACME/snapshot`, and `GET /api/v1/providers/health`. They explicitly return `source: replay`; they are not live market data.

Docker Compose is available after installing Docker: `docker compose up --build`.

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
