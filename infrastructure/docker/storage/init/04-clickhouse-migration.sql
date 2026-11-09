-- Connect to the metadata database
\c metadata;

-- Add batch_id to lineage_log for ClickHouse migration
ALTER TABLE lineage_log ADD COLUMN IF NOT EXISTS batch_id UUID;
CREATE INDEX IF NOT EXISTS idx_lineage_batch_id ON lineage_log(batch_id);

-- Add comment for documentation
COMMENT ON COLUMN lineage_log.batch_id IS 'Unique ID for the ClickHouse ingestion batch associated with this lineage record.';
