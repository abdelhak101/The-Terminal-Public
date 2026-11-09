#!/bin/bash

# Exit on error
set -e

echo "🚀 Starting The-Terminal Environment Bootstrap..."

# 1. Create the external network if it doesn't exist
NETWORK_NAME="the-terminal-network"
if ! docker network ls | grep -q "$NETWORK_NAME"; then
    echo "🌐 Creating network: $NETWORK_NAME"
    docker network create "$NETWORK_NAME"
else
    echo "✅ Network $NETWORK_NAME already exists."
fi

# 2. Build and start all services (including gateway via root include)
echo "📦 Building and starting all services..."
docker compose up --build -d

echo ""
echo "✨ All services started!"
echo ""
echo "═══════════════════════════════════════════════════════"
echo "  📦 STORAGE"
echo "───────────────────────────────────────────────────────"
echo "  PostgreSQL            http://localhost:25432"
echo "  Redis                 http://localhost:26379"
echo "  ClickHouse (HTTP)     http://localhost:28123"
echo "  ClickHouse (Native)   localhost:29000"
echo "  CloudBeaver (DB UI)   http://localhost:28900 (cbadmin / ycQE4mniT8hztum)"
echo "    └─ CH Setup         JDBC URL: jdbc:clickhouse://clickhouse:8123/default | User: admin | Pass: admin_password"
echo "    └─ Postgress Setup  User: admin | Pass: admin_password"
echo ""
echo "  📡 STREAMING"
echo "───────────────────────────────────────────────────────"
echo "  Redpanda (Kafka)      localhost:29092"
echo "  Redpanda Console      http://localhost:28080"
echo ""
echo "  🔭 OBSERVABILITY"
echo "───────────────────────────────────────────────────────"
echo "  Grafana               http://localhost:23000"
echo "  Prometheus            http://localhost:29090"
echo "  Loki                  http://localhost:23100"
echo "  OTel Collector gRPC   localhost:24317"
echo "  OTel Collector HTTP   localhost:24318"
echo "  OTel Metrics          http://localhost:28888"
echo "  OTel Exporter         http://localhost:28889"
echo "  Observer              http://localhost:28082"
echo "  Dozzle (Logs)         http://localhost:28881"
echo "  cAdvisor              http://localhost:28081"
echo ""
echo "  ⚙️  ORCHESTRATION"
echo "───────────────────────────────────────────────────────"
echo "  Gateway (FastAPI)     http://localhost:28000"
echo "  Dagster               http://localhost:23001"
echo "  Docs Portal           http://localhost:23002"
echo "    ├─ Inventory        http://localhost:23002/inventory/dashboard"
echo "    ├─ Adapter Search   http://localhost:23002/inventory/adapter-search"
echo "    └─ Source Setup     http://localhost:23002/guides/playbooks/dynamic-source-setup/"
echo "═══════════════════════════════════════════════════════"
echo ""
