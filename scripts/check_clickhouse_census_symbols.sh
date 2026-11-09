#!/bin/bash
cd /mnt/d/10-26-2024/Projects/Personal/The-Terminal
docker compose -f infrastructure/docker/storage/docker-compose.storage.yml exec -T clickhouse clickhouse-client -q "
SELECT symbol, count() FROM terminal.silver_data WHERE symbol LIKE '%eits%' OR symbol LIKE '%marts%' GROUP BY symbol ORDER BY symbol;
"
