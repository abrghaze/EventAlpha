BEGIN;

CREATE TABLE IF NOT EXISTS sources (
    source_id VARCHAR(255) PRIMARY KEY,
    provider VARCHAR(100) NOT NULL,
    source_type VARCHAR(100) NOT NULL,
    credibility_prior DOUBLE PRECISION NOT NULL DEFAULT 0.5 CHECK (credibility_prior BETWEEN 0 AND 1),
    storage_policy VARCHAR(50) NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_items (
    id VARCHAR(36) PRIMARY KEY,
    trace_id VARCHAR(36) NOT NULL,
    provider VARCHAR(100) NOT NULL,
    source_id VARCHAR(255) NOT NULL REFERENCES sources(source_id),
    native_id VARCHAR(500),
    event_time TIMESTAMPTZ,
    published_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    processed_at TIMESTAMPTZ NOT NULL,
    title VARCHAR(1000) NOT NULL,
    url TEXT NOT NULL,
    language VARCHAR(10) NOT NULL,
    category VARCHAR(100) NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    storage_policy VARCHAR(50) NOT NULL,
    independence_group VARCHAR(255),
    derived_attributes JSONB NOT NULL DEFAULT '{}'
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_provider_native
    ON raw_items(provider, source_id, native_id) WHERE native_id IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_raw_provider_content_fallback
    ON raw_items(provider, source_id, content_hash) WHERE native_id IS NULL;

CREATE INDEX IF NOT EXISTS ix_raw_items_trace_id ON raw_items(trace_id);
CREATE INDEX IF NOT EXISTS ix_raw_items_received_at ON raw_items(received_at);
CREATE INDEX IF NOT EXISTS ix_raw_items_content_hash ON raw_items(content_hash);

CREATE TABLE IF NOT EXISTS events (
    event_id VARCHAR(36) NOT NULL,
    event_version INTEGER NOT NULL CHECK (event_version >= 1),
    version_created_at TIMESTAMPTZ NOT NULL,
    clustering_version VARCHAR(100) NOT NULL,
    canonical_title VARCHAR(1000) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    event_time TIMESTAMPTZ,
    first_received_at TIMESTAMPTZ NOT NULL,
    last_updated_at TIMESTAMPTZ NOT NULL,
    language VARCHAR(10) NOT NULL,
    novelty DOUBLE PRECISION NOT NULL CHECK (novelty BETWEEN 0 AND 1),
    source_independence DOUBLE PRECISION NOT NULL CHECK (source_independence BETWEEN 0 AND 1),
    PRIMARY KEY (event_id, event_version)
);

CREATE INDEX IF NOT EXISTS ix_events_type ON events(event_type);
CREATE INDEX IF NOT EXISTS ix_events_first_received ON events(first_received_at);
CREATE INDEX IF NOT EXISTS ix_events_event_id ON events(event_id);
CREATE INDEX IF NOT EXISTS ix_events_version_created_at ON events(version_created_at);

CREATE TABLE IF NOT EXISTS event_mentions (
    raw_item_id VARCHAR(36) PRIMARY KEY REFERENCES raw_items(id),
    event_id VARCHAR(36) NOT NULL,
    event_version INTEGER NOT NULL,
    source_id VARCHAR(255) NOT NULL,
    independence_group VARCHAR(255) NOT NULL,
    published_at TIMESTAMPTZ,
    received_at TIMESTAMPTZ NOT NULL,
    FOREIGN KEY (event_id, event_version) REFERENCES events(event_id, event_version)
);

CREATE INDEX IF NOT EXISTS ix_event_mentions_event_id ON event_mentions(event_id);

COMMIT;
