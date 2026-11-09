-- Connect to the metadata database
\c metadata;

-- Feature Definitions Registry
CREATE TABLE IF NOT EXISTS feature_definitions (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    owner VARCHAR(255),
    version VARCHAR(20) DEFAULT '1.0.0',
    dsl_json JSONB NOT NULL, -- Serialized DSL (inputs, transformation params)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Feature Lineage (Dependencies on Assets or other Features)
CREATE TABLE IF NOT EXISTS feature_lineage (
    id SERIAL PRIMARY KEY,
    feature_id INTEGER REFERENCES feature_definitions(id) ON DELETE CASCADE,
    source_type VARCHAR(50) NOT NULL, -- 'asset' or 'feature'
    source_name VARCHAR(255) NOT NULL, -- symbol or feature name
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(feature_id, source_type, source_name)
);

-- Index for dependency lookups
CREATE INDEX IF NOT EXISTS idx_feature_lineage_source ON feature_lineage(source_type, source_name);
