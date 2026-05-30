#!/bin/bash
set -e

# Kafka Topic Initialization Script
# Creates all topics defined in infrastructure/kafka/topics.yaml.
# Idempotent — safe to run multiple times (--if-not-exists).
#
# Usage (from project root):
#   ./scripts/init-kafka.sh
#
# Production deploys use the kafka-init Docker Compose service instead.
# This script is for local dev and manual recovery.

KAFKA_BIN="docker exec blackheart-kafka /opt/kafka/bin/kafka-topics.sh"
BROKER="localhost:9092"
MAX_RETRIES=30
RETRY_DELAY=2

echo "Initializing Kafka topics..."

# Wait for Kafka broker to be ready
echo "Waiting for Kafka broker at $BROKER..."
retry_count=0
while [ $retry_count -lt $MAX_RETRIES ]; do
  if docker exec blackheart-kafka /opt/kafka/bin/kafka-broker-api-versions.sh \
      --bootstrap-server "$BROKER" &>/dev/null; then
    echo "✓ Kafka broker is ready"
    break
  fi
  retry_count=$((retry_count + 1))
  if [ $retry_count -eq $MAX_RETRIES ]; then
    echo "✗ Kafka broker did not become ready after $((MAX_RETRIES * RETRY_DELAY)) seconds"
    exit 1
  fi
  echo "  Waiting... ($retry_count/$MAX_RETRIES)"
  sleep $RETRY_DELAY
done

create() {
  local topic=$1 partitions=$2 retention=$3
  echo -n "  $topic (p=$partitions, retention=${retention}ms)... "
  $KAFKA_BIN --bootstrap-server "$BROKER" \
    --create --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor 1 \
    --config "retention.ms=$retention" \
    --config "compression.type=snappy" &>/dev/null && echo "✓" || echo "⚠ (may already exist)"
}

# ── Topics (keep in sync with infrastructure/kafka/topics.yaml) ─────────────
create market.bars           3  604800000    # 7 days
create features.computed     3  604800000    # 7 days
create signals.live          2  604800000    # 7 days
create models.deployed       1  2592000000   # 30 days
create errors.inference      2  86400000     # 24 hours
create backtest-requests     3  2592000000   # 30 days
create backtest-requests.DLQ 1  604800000    # 7 days

echo ""
echo "✓ Kafka initialization complete. Current topics:"
docker exec blackheart-kafka /opt/kafka/bin/kafka-topics.sh \
  --bootstrap-server "$BROKER" --list
