"""
Real-time feature stream processor for event-driven ML pipeline.

Consumes MarketBarEvents from Kafka, computes features, and publishes
ComputedFeatureEvents. Bridges market data → feature computation → ML signals.

Usage::

    async def compute_regime_features(bar: MarketBarEvent) -> dict[str, float]:
        # ... compute features from bar ...
        return {"rsi_14": 65.5, "macd": -0.25}

    processor = FeatureStreamProcessor(
        bootstrap_servers="kafka:9092",
        compute_fn=compute_regime_features,
        signal_id="regime_btc_v3",
        feature_version="1.0.0",
    )
    await processor.start()
    # In background:
    await processor.run()  # Main event loop
    await processor.stop()
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Callable

try:
    from aiokafka import AIOKafkaConsumer
except ImportError:
    # Kafka optional dependency; used in production but mocked in tests
    AIOKafkaConsumer = None  # type: ignore

from blackheart_ingest.schemas.events import ComputedFeatureEvent, MarketBarEvent
from blackheart_ingest.services.kafka_producer import KafkaProducerClient

logger = logging.getLogger(__name__)


class FeatureStreamProcessor:
    """
    Real-time feature stream processor for the event-driven ML pipeline.

    Consumes market bars from Kafka, applies a feature computation function,
    and publishes computed feature vectors. Supports async context management
    and clean lifecycle (start/run/stop).

    Attributes:
        bootstrap_servers: Kafka bootstrap servers.
        signal_id: ML signal identifier (e.g., "regime_btc_v3").
        feature_version: Feature definition version (e.g., "1.0.0").
        compute_fn: Async callable that takes MarketBarEvent → dict[str, float].
    """

    def __init__(
        self,
        bootstrap_servers: str,
        compute_fn: Callable[[MarketBarEvent], Any],
        signal_id: str,
        feature_version: str,
    ) -> None:
        """Initialize the feature stream processor.

        Args:
            bootstrap_servers: Kafka bootstrap servers (e.g., "kafka:9092").
            compute_fn: Async function that computes features from a market bar.
            signal_id: ML signal identifier (e.g., "regime_btc_v3").
            feature_version: Feature definition version (e.g., "1.0.0").
        """
        self.bootstrap_servers = bootstrap_servers
        self.compute_fn = compute_fn
        self.signal_id = signal_id
        self.feature_version = feature_version

        self.consumer: AIOKafkaConsumer | None = None
        self.producer_client: KafkaProducerClient | None = None

    async def start(self) -> None:
        """Start the consumer and producer.

        Creates an AIOKafkaConsumer subscribed to market.bars and initializes
        the KafkaProducerClient for publishing computed features.
        """
        # Create and start Kafka consumer
        if AIOKafkaConsumer is None:
            raise RuntimeError("aiokafka not installed; install with: pip install blackheart-ingest[kafka]")

        self.consumer = AIOKafkaConsumer(
            "market.bars",
            bootstrap_servers=self.bootstrap_servers,
            group_id=f"feature-stream-{self.signal_id}",
            value_deserializer=lambda m: m.decode("utf-8") if m else None,
        )
        await self.consumer.start()
        logger.info(
            "feature_stream.consumer_started",
            extra={
                "bootstrap_servers": self.bootstrap_servers,
                "signal_id": self.signal_id,
            },
        )

        # Initialize producer client (don't start context yet; done in run())
        self.producer_client = KafkaProducerClient(
            bootstrap_servers=self.bootstrap_servers
        )
        logger.info(
            "feature_stream.producer_initialized",
            extra={"signal_id": self.signal_id},
        )

    async def stop(self) -> None:
        """Stop the consumer and producer."""
        if self.consumer:
            await self.consumer.stop()
            logger.info("feature_stream.consumer_stopped")

        # Producer client is managed as context in run(); no explicit stop needed here
        logger.info("feature_stream.stopped")

    async def _compute_features(self, bar: MarketBarEvent) -> dict[str, float]:
        """Compute features for a market bar.

        Args:
            bar: MarketBarEvent from Kafka.

        Returns:
            Dictionary of feature name → float value.
        """
        try:
            features = await self.compute_fn(bar)
            return features
        except Exception as e:
            logger.error(
                "feature_stream.compute_failed",
                extra={"symbol": bar.symbol, "ts": bar.ts, "error": str(e)},
            )
            raise

    async def run(self) -> None:
        """Main event loop: consume bars, compute features, publish events.

        Runs indefinitely, consuming from market.bars, calling compute_fn,
        and publishing to features.computed. Errors are logged; processing
        continues with the next message.

        Should be run as a background task (e.g., asyncio.create_task()).
        """
        if not self.consumer or not self.producer_client:
            raise RuntimeError("Processor not started; call start() first")

        async with self.producer_client as producer:
            async for message in self.consumer:
                try:
                    if not message:
                        continue

                    # Parse market bar from JSON
                    bar_data = json.loads(message)
                    bar = MarketBarEvent(**bar_data)

                    # Compute features
                    feature_vector = await self._compute_features(bar)

                    # Create and publish computed feature event
                    # Extract interval from context; for now use a placeholder
                    # In production, interval would come from the bar or signal config
                    event = ComputedFeatureEvent(
                        signal_id=self.signal_id,
                        symbol=bar.symbol,
                        interval="1h",  # TODO: extract from bar metadata or config
                        ts=bar.ts,
                        feature_vector=feature_vector,
                        feature_version=self.feature_version,
                    )

                    await producer.publish(
                        topic="features.computed",
                        key=self.signal_id,
                        event=event,
                    )

                    logger.debug(
                        "feature_stream.published",
                        extra={
                            "symbol": bar.symbol,
                            "signal_id": self.signal_id,
                            "features_count": len(feature_vector),
                        },
                    )

                except asyncio.CancelledError:
                    logger.info("feature_stream.cancelled", extra={"signal_id": self.signal_id})
                    raise
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "feature_stream.process_error",
                        extra={"error": str(e)},
                    )
                    # Continue processing next message


async def run_feature_stream(
    bootstrap_servers: str,
    compute_fn: Callable[[MarketBarEvent], Any],
    signal_id: str,
    feature_version: str = "1.0.0",
) -> None:
    """Runner function for feature stream processor.

    Convenience function to create, start, and run a processor.

    Args:
        bootstrap_servers: Kafka bootstrap servers.
        compute_fn: Feature computation function.
        signal_id: ML signal identifier.
        feature_version: Feature definition version.
    """
    processor = FeatureStreamProcessor(
        bootstrap_servers=bootstrap_servers,
        compute_fn=compute_fn,
        signal_id=signal_id,
        feature_version=feature_version,
    )
    await processor.start()
    try:
        await processor.run()
    except KeyboardInterrupt:
        logger.info("feature_stream.interrupted")
    finally:
        await processor.stop()
