"""
WebSocket manager — broadcasts RabbitMQ events to all connected frontend clients.
"""

from __future__ import annotations

import asyncio
import json
import logging

import aio_pika
from fastapi import WebSocket

from app.config import settings

logger = logging.getLogger("gateway.ws")


class ConnectionManager:
    """Manages WebSocket connections and broadcasts events."""

    def __init__(self) -> None:
        self._connections: list[WebSocket] = []
        self._mq_connection: aio_pika.abc.AbstractRobustConnection | None = None

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections.append(websocket)
        logger.info("WebSocket client connected. Total: %d", len(self._connections))

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self._connections:
            self._connections.remove(websocket)
        logger.info("WebSocket client disconnected. Total: %d", len(self._connections))

    async def broadcast(self, data: dict) -> None:
        """Send data to all connected WebSocket clients."""
        dead = []
        for ws in self._connections:
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)

    async def start_rabbitmq_listener(self) -> None:
        """Connect to RabbitMQ and forward all events to WebSocket clients."""
        for attempt in range(1, 11):
            try:
                logger.info("Connecting to RabbitMQ for WS broadcasting (attempt %d)...", attempt)
                self._mq_connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url, timeout=10
                )
                channel = await self._mq_connection.channel()
                await channel.set_qos(prefetch_count=20)

                exchange = await channel.declare_exchange(
                    settings.RABBITMQ_EXCHANGE,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )

                # Exclusive auto-delete queue for the gateway
                queue = await channel.declare_queue("", exclusive=True, auto_delete=True)
                await queue.bind(exchange, routing_key="#")    # all events

                logger.info("RabbitMQ listener started — broadcasting to WebSocket clients.")

                async with queue.iterator() as queue_iter:
                    async for message in queue_iter:
                        async with message.process():
                            try:
                                data = json.loads(message.body.decode())
                                await self.broadcast(data)
                            except Exception as e:
                                logger.error("Error broadcasting message: %s", e)

            except asyncio.CancelledError:
                logger.info("RabbitMQ listener cancelled.")
                return
            except Exception as e:
                logger.warning("RabbitMQ listener error (attempt %d): %s", attempt, e)
                await asyncio.sleep(3)

    async def close(self) -> None:
        if self._mq_connection and not self._mq_connection.is_closed:
            await self._mq_connection.close()


manager = ConnectionManager()
