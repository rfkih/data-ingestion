"""
Kafka producer wrapper for publishing events to Kafka topics.

Provides an async context manager for managing AIOKafkaProducer lifecycle
and a publish() method for serializing and sending Pydantic events.
"""

import json
import logging
from typing import Any

try:
    from aiokafka import AIOKafkaProducer
except ImportError:
    # Kafka optional dependency; used in production but mocked in tests
    AIOKafkaProducer = None  # type: ignore

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class KafkaProducerClient:
    """
    Async Kafka producer client wrapper.

    Manages AIOKafkaProducer lifecycle (start/stop) and provides a
    publish() method that serializes Pydantic events to JSON and sends
    them to a Kafka topic.

    Usage::

        async with KafkaProducerClient(bootstrap_servers="localhost:9092") as client:
            event = ComputedFeatureEvent(...)
            await client.publish(topic="features.computed", key="regime_btc_v3", event=event)
    """

    def __init__(self, bootstrap_servers: str) -> None:
        """Initialize the Kafka producer client.

        Args:
            bootstrap_servers: Kafka bootstrap servers (e.g., "localhost:9092").
        """
        self.bootstrap_servers = bootstrap_servers
        self.producer: AIOKafkaProducer | None = None

    async def __aenter__(self) -> "KafkaProducerClient":
        """Enter async context: create and start the producer."""
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        logger.debug(
            "kafka_producer.started",
            extra={"bootstrap_servers": self.bootstrap_servers},
        )
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Exit async context: stop the producer."""
        if self.producer:
            await self.producer.stop()
            logger.debug("kafka_producer.stopped")

    async def publish(self, topic: str, key: str, event: BaseModel) -> None:
        """Publish a Pydantic event to a Kafka topic.

        Serializes the event to JSON and sends it to the specified topic
        with the given key. Raises an exception if send_and_wait fails.

        Args:
            topic: Kafka topic name (e.g., "features.computed").
            key: Event key for partitioning (e.g., signal_id).
            event: Pydantic BaseModel instance to serialize and publish.

        Raises:
            Exception: If Kafka send fails.
        """
        if not self.producer:
            raise RuntimeError("Producer not initialized; use 'async with' context manager")

        # Serialize event to JSON
        value_json = event.model_dump_json()
        value_bytes = value_json.encode("utf-8")
        key_bytes = key.encode("utf-8")

        try:
            await self.producer.send_and_wait(
                topic=topic,
                value=value_bytes,
                key=key_bytes,
            )
            logger.debug(
                "kafka_producer.published",
                extra={
                    "topic": topic,
                    "key": key,
                    "event_type": event.__class__.__name__,
                },
            )
        except Exception as e:
            logger.error(
                "kafka_producer.publish_failed",
                extra={
                    "topic": topic,
                    "key": key,
                    "error": str(e),
                },
            )
            raise
