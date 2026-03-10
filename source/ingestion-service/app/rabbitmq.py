"""
Async RabbitMQ publisher client using aio_pika.

Declares the topic exchange `mars.events` and publishes normalized events
with routing keys in the format: {event_type}.{location}.{metric}

If RabbitMQ is unreachable, events are buffered in-memory and retried
on subsequent publish calls.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections import deque

import aio_pika

from app.config import settings
from app.models import UnifiedEvent

logger = logging.getLogger("ingestion.rabbitmq")

MAX_BUFFER_SIZE = 1000


class RabbitMQPublisher:
    """Manages the RabbitMQ connection and publishes events."""

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None
        self._buffer: deque[UnifiedEvent] = deque(maxlen=MAX_BUFFER_SIZE)

    async def connect(self, max_retries: int = 10, delay: float = 3.0) -> None:
        """Connect to RabbitMQ with retry logic."""
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(
                    "Connecting to RabbitMQ at %s (attempt %d/%d)",
                    settings.rabbitmq_url, attempt, max_retries,
                )
                self._connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url,
                    timeout=10,
                )
                self._channel = await self._connection.channel()

                # Declare the topic exchange
                self._exchange = await self._channel.declare_exchange(
                    settings.RABBITMQ_EXCHANGE,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                logger.info(
                    "Connected to RabbitMQ — exchange '%s' declared.",
                    settings.RABBITMQ_EXCHANGE,
                )
                return

            except Exception as e:
                logger.warning(
                    "RabbitMQ connection attempt %d failed: %s", attempt, e
                )
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                else:
                    logger.error("Failed to connect to RabbitMQ after %d attempts.", max_retries)
                    raise

    async def _publish_single(self, event: UnifiedEvent) -> None:
        """Publish a single event to the exchange (no buffering logic)."""
        metric = event.payload.get("metric", "unknown")
        routing_key = f"{event.event_type.value}.{event.location}.{metric}"

        message = aio_pika.Message(
            body=json.dumps(event.model_dump(), default=str).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await self._exchange.publish(message, routing_key=routing_key)
        logger.debug("Published event %s → %s", event.event_id[:8], routing_key)

    async def publish(self, event: UnifiedEvent) -> None:
        """Publish a unified event to the topic exchange.

        If the exchange is unavailable, the event is buffered in-memory
        and retried on the next publish call.
        """
        if not self._exchange:
            self._buffer.append(event)
            logger.warning(
                "RabbitMQ not connected — event buffered (%d in buffer).",
                len(self._buffer),
            )
            return

        # Flush any buffered events first
        while self._buffer:
            buffered = self._buffer[0]
            try:
                await self._publish_single(buffered)
                self._buffer.popleft()
            except Exception as e:
                logger.warning("Failed to flush buffered event: %s", e)
                self._buffer.append(event)
                return

        # Publish the current event
        try:
            await self._publish_single(event)
        except Exception as e:
            self._buffer.append(event)
            logger.warning(
                "Failed to publish event, buffered (%d in buffer): %s",
                len(self._buffer), e,
            )

    async def close(self) -> None:
        """Close the RabbitMQ connection gracefully."""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("RabbitMQ connection closed.")


# Singleton instance
publisher = RabbitMQPublisher()

