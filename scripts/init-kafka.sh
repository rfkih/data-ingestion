#!/bin/bash
set -e

# Kafka Topic Initialization Script
# Waits for Kafka broker availability and creates topics from topics.yaml config.
# Expected runtime: ~5-10 seconds after Kafka is healthy.

KAFKA_BROKER="localhost:9092"
TOPICS_CONFIG_FILE="infrastructure/kafka/topics.yaml"
MAX_RETRIES=30
RETRY_DELAY=2

echo "Initializing Kafka topics..."

# Wait for Kafka broker to be ready
echo "Waiting for Kafka broker at $KAFKA_BROKER..."
retry_count=0
while [ $retry_count -lt $MAX_RETRIES ]; do
  if docker exec blackheart-kafka kafka-broker-api-versions --bootstrap-server "$KAFKA_BROKER" &>/dev/null; then
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

# Parse topics.yaml and create each topic
if [ ! -f "$TOPICS_CONFIG_FILE" ]; then
  echo "✗ Topics config file not found: $TOPICS_CONFIG_FILE"
  exit 1
fi

echo "Creating topics from $TOPICS_CONFIG_FILE..."

# Simple YAML parser to extract topic names
# This extracts lines like "  - name: market.bars" and gets "market.bars"
topics=$(grep "^\s*- name:" "$TOPICS_CONFIG_FILE" | sed 's/.*- name:\s*//g' | tr -d ' ')

if [ -z "$topics" ]; then
  echo "✗ No topics found in config file"
  exit 1
fi

topic_count=0
for topic in $topics; do
  # Extract topic configuration from YAML
  # Find the line number of the topic definition
  topic_line=$(grep -n "- name: $topic" "$TOPICS_CONFIG_FILE" | cut -d: -f1)

  if [ -z "$topic_line" ]; then
    echo "✗ Could not find topic definition for $topic"
    continue
  fi

  # Extract partitions (default to 1 if not found)
  partitions=$(awk "NR>=$topic_line && NR<NR+100 && /^\s*partitions:/ {print \$2; exit}" "$TOPICS_CONFIG_FILE")
  partitions=${partitions:-1}

  # Extract replication_factor (default to 1 if not found)
  replication=$(awk "NR>=$topic_line && NR<NR+100 && /^\s*replication_factor:/ {print \$2; exit}" "$TOPICS_CONFIG_FILE")
  replication=${replication:-1}

  # Create topic using docker exec
  echo -n "  Creating topic '$topic' (partitions=$partitions, replication=$replication)... "

  if docker exec blackheart-kafka kafka-topics.sh \
    --bootstrap-server "$KAFKA_BROKER" \
    --create \
    --if-not-exists \
    --topic "$topic" \
    --partitions "$partitions" \
    --replication-factor "$replication" &>/dev/null; then
    echo "✓"
    topic_count=$((topic_count + 1))
  else
    echo "⚠ (may already exist)"
  fi
done

echo ""
echo "✓ Kafka initialization complete ($topic_count topics)"

# Verify all topics were created
echo "Listing created topics:"
docker exec blackheart-kafka kafka-topics.sh \
  --bootstrap-server "$KAFKA_BROKER" \
  --list

exit 0
