#!/bin/sh

# Wait for Redpanda to be ready
echo "Waiting for Redpanda to be ready..."
until rpk cluster info --brokers redpanda:9092 > /dev/null 2>&1; do
  sleep 2
done

echo "Redpanda is ready. Provisioning topics..."

# Create core topics
rpk topic create telemetry.logs --brokers redpanda:9092
rpk topic create telemetry.metrics --brokers redpanda:9092
rpk topic create ingestion.status --brokers redpanda:9092
rpk topic create market.yahoo --brokers redpanda:9092
rpk topic create market.bars.1m --brokers redpanda:9092

echo "Topics provisioned successfully."
