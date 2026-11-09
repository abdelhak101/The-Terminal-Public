from prometheus_client import Counter, Gauge, REGISTRY

def get_or_create_counter(name, documentation, labelnames=()):
    """
    Helper to prevent duplicate metric registrations in environments like Dagster 
    where modules might be imported multiple times.
    """
    if name in REGISTRY._names_to_collectors:
        collector = REGISTRY._names_to_collectors[name]
        # For counters, prometheus_client appends '_total', '_created' etc to the base name
        # but the registry might hold the base name. 
        # Actually, Counter(name, ...) registers 'name_total' if name doesn't end in total.
        return collector
    
    return Counter(name, documentation, labelnames)

def get_or_create_gauge(name, documentation, labelnames=()):
    if name in REGISTRY._names_to_collectors:
        return REGISTRY._names_to_collectors[name]
    return Gauge(name, documentation, labelnames)

# Global Metrics
TERMINAL_ADAPTER_MESSAGES_TOTAL = Counter(
    'terminal_adapter_messages_total',
    'Total number of messages/records fetched by adapters',
    ['source', 'entity_id']
)

TERMINAL_CLICKHOUSE_QUERY_TOTAL = Counter(
    'terminal_clickhouse_query_total',
    'Total number of queries executed against ClickHouse',
    ['operation', 'status']
)

TERMINAL_CLICKHOUSE_ROWS_TOTAL = Counter(
    'terminal_clickhouse_rows_total',
    'Total number of rows processed by ClickHouse',
    ['operation', 'layer']
)

TERMINAL_CLICKHOUSE_COMPRESSION_RATIO = Gauge(
    'terminal_clickhouse_compression_ratio',
    'Ratio of uncompressed size to compressed size in ClickHouse',
    ['layer']
)

TERMINAL_CLICKHOUSE_OLDEST_RECORD_DAYS = Gauge(
    'terminal_clickhouse_oldest_record_days',
    'Age of the oldest record in a ClickHouse layer in days',
    ['layer']
)

TERMINAL_ADAPTER_FALLBACK_TOTAL = get_or_create_counter(
    'terminal_adapter_fallback_total',
    'Total fallback cache retrievals by adapters',
    ['source', 'entity_id']
)
