"""
RabbitMQ publisher for the Processor Service.

Used to publish actuator_command and alert events back to the exchange
for audit trail and dashboard display.
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika

from app.config import settings
from app.models import UnifiedEvent

logger = logging.getLogger("processor.rabbitmq")


class RabbitMQPublisher:
    """Publishes events to the mars.events exchange."""

    def __init__(self) -> None:
        self._connection: aio_pika.abc.AbstractRobustConnection | None = None
        self._channel: aio_pika.abc.AbstractChannel | None = None
        self._exchange: aio_pika.abc.AbstractExchange | None = None

    async def connect(self, max_retries: int = 10, delay: float = 3.0) -> None:
        for attempt in range(1, max_retries + 1):
            try:
                self._connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url, timeout=10
                )
                self._channel = await self._connection.channel()
                self._exchange = await self._channel.declare_exchange(
                    settings.RABBITMQ_EXCHANGE,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                logger.info("Publisher connected to RabbitMQ.")
                return
            except Exception as e:
                logger.warning("Publisher connect attempt %d failed: %s", attempt, e)
                if attempt < max_retries:
                    await asyncio.sleep(delay)
                else:
                    raise

    async def publish(self, event: UnifiedEvent) -> None:
        if not self._exchange:
            return
        metric = event.payload.get("metric", event.payload.get("command", "unknown"))
        routing_key = f"{event.event_type.value}.{event.location}.{metric}"
        message = aio_pika.Message(
            body=json.dumps(event.model_dump(), default=str).encode(),
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await self._exchange.publish(message, routing_key=routing_key)

    async def close(self) -> None:
        if self._connection and not self._connection.is_closed:
            await self._connection.close()


publisher = RabbitMQPublisher()
