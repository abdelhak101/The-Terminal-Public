-- Connect to the metadata database
\c metadata;

-- Core Asset Registry
CREATE TABLE IF NOT EXISTS assets (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(255) NOT NULL,
    library VARCHAR(50) NOT NULL, -- bronze, silver, gold
    label VARCHAR(100) DEFAULT 'main',
    description TEXT,
    frequency VARCHAR(50), -- e.g., 'daily', 'hourly', 'minute'
    metadata JSONB DEFAULT '{}',
    current_version INTEGER,
    schema_version VARCHAR(20) DEFAULT 'v1',
    last_observed_timestamp TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(symbol, library, label)
);

-- Column-level Semantics
CREATE TABLE IF NOT EXISTS asset_columns (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    unit VARCHAR(50),
    semantic_type VARCHAR(100), -- price, volume, indicator, etc.
    is_canonical BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, name)
);

-- Lineage Tracking
CREATE TABLE IF NOT EXISTS lineage_log (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    version_id INTEGER, -- ArcticDB version number
    dagster_run_id VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending', -- pending, committed, failed
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    metadata JSONB DEFAULT '{}'
);

-- Indices for fast lookups
CREATE INDEX IF NOT EXISTS idx_lineage_asset_version ON lineage_log(asset_id, version_id);
CREATE INDEX IF NOT EXISTS idx_assets_symbol_library ON assets(symbol, library);

-- Data Quality Rules
CREATE TABLE IF NOT EXISTS asset_quality_rules (
    id SERIAL PRIMARY KEY,
    asset_id INTEGER REFERENCES assets(id) ON DELETE CASCADE,
    rule_type VARCHAR(100) NOT NULL,
    threshold JSONB,
    severity VARCHAR(20) DEFAULT 'warning',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(asset_id, rule_type)
);

-- Source Inventory for Dynamic Ingestion
CREATE TABLE IF NOT EXISTS source_inventory (
    id SERIAL PRIMARY KEY,
    adapter_type VARCHAR(50) NOT NULL, -- 'yahoo', 'fred'
    identifier VARCHAR(255) NOT NULL,   -- 'AAPL', 'CPI'
    label VARCHAR(100) DEFAULT 'main',
    is_active BOOLEAN DEFAULT TRUE,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(adapter_type, identifier, label)
);
