# EventAlpha workers

Worker roles are deliberately separate from the FastAPI gateway, while sharing domain contracts:

- `worker-fast`: ingestion, normalization, AI routing, features, signal/risk jobs;
- `worker-batch`: historical ingestion, replay, backtests, reports.

Phase 0 supplies a deterministic in-process replay path only. Redis consumer groups and provider adapters are Phase 1/2 work; no worker currently calls a broker or OpenAI.
