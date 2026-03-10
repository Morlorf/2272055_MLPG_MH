"""
RabbitMQ consumer — subscribes to the mars.events exchange and processes
incoming sensor events through the rule engine and state cache.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

import aio_pika

from app.arbitrator import arbitrator
from app.config import settings
from app.database import get_active_rules
from app.rules import evaluate_rules
from app.state import state_cache

logger = logging.getLogger("processor.consumer")

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None

# In-memory rules cache (refreshed on startup + CRUD operations)
_active_rules_cache: list = []


async def refresh_rules_cache() -> None:
    """Reload active rules from the database into memory."""
    global _active_rules_cache
    _active_rules_cache = await get_active_rules()
    logger.info("Rules cache refreshed: %d active rules loaded.", len(_active_rules_cache))


async def connect_and_consume() -> None:
    """Connect to RabbitMQ and start consuming events."""
    global _connection, _channel

    for attempt in range(1, 11):
        try:
            logger.info(
                "Connecting to RabbitMQ (attempt %d/10)...", attempt
            )
            _connection = await aio_pika.connect_robust(
                settings.rabbitmq_url, timeout=10
            )
            _channel = await _connection.channel()
            await _channel.set_qos(prefetch_count=10)

            # Declare the exchange (idempotent)
            exchange = await _channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )

            # Declare a queue for the processor and bind to all sensor readings
            queue = await _channel.declare_queue(
                "processor.events", durable=True
            )
            await queue.bind(exchange, routing_key="sensor_reading.#")

            logger.info("Connected to RabbitMQ — consuming from 'processor.events'")

            # Start consuming
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    async with message.process():
                        await _handle_message(message)

        except asyncio.CancelledError:
            logger.info("Consumer task cancelled.")
            return
        except Exception as e:
            logger.warning("Consumer error (attempt %d): %s", attempt, e)
            await asyncio.sleep(3)

    logger.error("Failed to connect consumer after 10 attempts.")


async def _handle_message(message: aio_pika.IncomingMessage) -> None:
    """Process a single incoming message."""
    try:
        data = json.loads(message.body.decode())
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error("Failed to decode message: %s", e)
        return

    # 1. Update state cache
    state_cache.update(data)

    # 2. Evaluate rules
    triggered = evaluate_rules(data, _active_rules_cache)

    # 3. Execute triggered rule actions via Arbitrator
    for rule in triggered:
        action = rule.action
        await arbitrator.submit_command(rule, action.actuator, action.state, data)


async def close_consumer() -> None:
    """Close the RabbitMQ consumer connection."""
    global _connection
    if _connection and not _connection.is_closed:
        await _connection.close()
        logger.info("Consumer connection closed.")
