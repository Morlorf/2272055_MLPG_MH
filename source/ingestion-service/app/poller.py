"""
Async REST sensor polling loop.

On startup, calls the simulator's /api/discovery endpoint to learn which
sensors are available and which schema each uses. Then polls each sensor
at the configured interval and publishes normalized events to RabbitMQ.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from app.config import settings
from app.models import NORMALIZERS, UnifiedEvent
from app.rabbitmq import publisher

logger = logging.getLogger("ingestion.poller")


class SensorPoller:
    """Discovers and polls REST sensors from the simulator."""

    def __init__(self) -> None:
        self._session: aiohttp.ClientSession | None = None
        self._sensors: list[dict] = []  # from /api/discovery
        self._running = False

    # ── Discovery ────────────────────────────────────────────

    async def discover_sensors(self) -> None:
        """Fetch the sensor list from the simulator discovery endpoint."""
        url = f"{settings.SIMULATOR_URL}/api/discovery"
        try:
            async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                data = await resp.json()
                self._sensors = data.get("rest_sensors", [])
                logger.info(
                    "Discovered %d REST sensors: %s",
                    len(self._sensors),
                    [s["sensor_id"] for s in self._sensors],
                )
        except Exception as e:
            logger.error("Failed to discover sensors: %s", e)
            self._sensors = []

    # ── Polling Loop ─────────────────────────────────────────

    async def start(self) -> None:
        """Start the polling loop as a long-running coroutine."""
        self._session = aiohttp.ClientSession()
        self._running = True

        # Discover sensors before first poll
        await self.discover_sensors()

        logger.info(
            "Starting polling loop — interval=%ds, sensors=%d",
            settings.POLLING_INTERVAL_SECONDS,
            len(self._sensors),
        )
        while self._running:
            await self._poll_all()
            await asyncio.sleep(settings.POLLING_INTERVAL_SECONDS)

    async def stop(self) -> None:
        """Stop the polling loop and close the HTTP session."""
        self._running = False
        if self._session and not self._session.closed:
            await self._session.close()
        logger.info("Poller stopped.")

    # ── Internal ─────────────────────────────────────────────

    async def _poll_all(self) -> None:
        """Poll all discovered sensors concurrently."""
        if not self._sensors:
            logger.warning("No sensors to poll — retrying discovery.")
            await self.discover_sensors()
            return

        tasks = [self._poll_sensor(sensor) for sensor in self._sensors]
        await asyncio.gather(*tasks, return_exceptions=True)

    async def _poll_sensor(self, sensor_info: dict) -> None:
        """
        Poll a single sensor, normalize, and publish.

        sensor_info: {"sensor_id": "...", "path": "...", "schema_id": "..."}
        """
        sensor_id = sensor_info["sensor_id"]
        path = sensor_info["path"]
        schema_id = sensor_info["schema_id"]
        url = f"{settings.SIMULATOR_URL}{path}"

        try:
            async with self._session.get(
                url, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Sensor %s returned status %d", sensor_id, resp.status
                    )
                    return
                raw = await resp.json()

        except asyncio.TimeoutError:
            logger.warning("Timeout polling sensor %s", sensor_id)
            return
        except Exception as e:
            logger.error("Error polling sensor %s: %s", sensor_id, e)
            return

        # Normalize using the appropriate schema handler
        normalizer = NORMALIZERS.get(schema_id)
        if not normalizer:
            logger.warning("No normalizer for schema '%s' (sensor %s)", schema_id, sensor_id)
            return

        try:
            events: list[UnifiedEvent] = normalizer(raw)
        except Exception as e:
            logger.error(
                "Normalization failed for sensor %s (schema %s): %s",
                sensor_id, schema_id, e,
            )
            return

        # Publish each normalized event
        for event in events:
            try:
                await publisher.publish(event)
            except Exception as e:
                logger.error("Failed to publish event for sensor %s: %s", sensor_id, e)


# Singleton instance
poller = SensorPoller()
