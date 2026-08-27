BEGIN;

CREATE TABLE providers (
    provider_id VARCHAR(100) PRIMARY KEY,
    provider_type VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE instruments (
    symbol VARCHAR(12) PRIMARY KEY,
    asset_class VARCHAR(50) NOT NULL DEFAULT 'unknown',
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL
);

CREATE TABLE market_bar_observations (
    content_hash VARCHAR(64) PRIMARY KEY,
    observation_id VARCHAR(36) NOT NULL,
    trace_id VARCHAR(36) NOT NULL,
    provider VARCHAR(100) NOT NULL REFERENCES providers(provider_id),
    native_id VARCHAR(500),
    symbol VARCHAR(12) NOT NULL REFERENCES instruments(symbol),
    timeframe VARCHAR(10) NOT NULL,
    bar_start_at TIMESTAMPTZ NOT NULL,
    bar_end_at TIMESTAMPTZ NOT NULL,
    provider_updated_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    is_final BOOLEAN NOT NULL,
    open NUMERIC(28, 10) NOT NULL,
    high NUMERIC(28, 10) NOT NULL,
    low NUMERIC(28, 10) NOT NULL,
    close NUMERIC(28, 10) NOT NULL,
    volume BIGINT,
    CONSTRAINT ck_market_bar_interval CHECK (bar_end_at > bar_start_at),
    CONSTRAINT ck_market_bar_high CHECK (high >= open AND high >= close AND high >= low),
    CONSTRAINT ck_market_bar_low CHECK (low <= open AND low <= close AND low <= high),
    CONSTRAINT ck_market_bar_volume CHECK (volume IS NULL OR volume >= 0)
);

CREATE INDEX ix_market_bar_trace ON market_bar_observations(trace_id);
CREATE INDEX ix_market_bar_observation ON market_bar_observations(observation_id);
CREATE INDEX ix_market_bars_lookup ON market_bar_observations(
    provider, symbol, timeframe, bar_start_at, received_at
);

CREATE TABLE market_quote_observations (
    content_hash VARCHAR(64) PRIMARY KEY,
    observation_id VARCHAR(36) NOT NULL,
    trace_id VARCHAR(36) NOT NULL,
    provider VARCHAR(100) NOT NULL REFERENCES providers(provider_id),
    native_id VARCHAR(500),
    symbol VARCHAR(12) NOT NULL REFERENCES instruments(symbol),
    bid NUMERIC(28, 10),
    ask NUMERIC(28, 10),
    last NUMERIC(28, 10),
    provider_timestamp TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT ck_market_quote_bid CHECK (bid IS NULL OR bid > 0),
    CONSTRAINT ck_market_quote_ask CHECK (ask IS NULL OR ask > 0),
    CONSTRAINT ck_market_quote_last CHECK (last IS NULL OR last > 0),
    CONSTRAINT ck_market_quote_spread CHECK (bid IS NULL OR ask IS NULL OR bid <= ask),
    CONSTRAINT ck_market_quote_has_price CHECK (
        bid IS NOT NULL OR ask IS NOT NULL OR last IS NOT NULL
    )
);

CREATE INDEX ix_market_quote_trace ON market_quote_observations(trace_id);
CREATE INDEX ix_market_quote_observation ON market_quote_observations(observation_id);
CREATE INDEX ix_market_quotes_lookup ON market_quote_observations(
    provider, symbol, provider_timestamp, received_at
);

CREATE TABLE provider_state (
    provider_id VARCHAR(100) PRIMARY KEY REFERENCES providers(provider_id),
    heartbeat_at TIMESTAMPTZ NOT NULL,
    last_message_received_at TIMESTAMPTZ,
    last_success_at TIMESTAMPTZ,
    last_failure_at TIMESTAMPTZ,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    reconnect_count INTEGER NOT NULL DEFAULT 0 CHECK (reconnect_count >= 0),
    status VARCHAR(30) NOT NULL,
    detail VARCHAR(1000)
);

COMMIT;
