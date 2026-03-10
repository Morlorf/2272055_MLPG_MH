"""
Actuator client — sends REST POST commands to the simulator.
"""

from __future__ import annotations

import asyncio
import logging

import aiohttp

from app.config import settings

logger = logging.getLogger("processor.actuator")

_session: aiohttp.ClientSession | None = None


async def init_session() -> None:
    """Create the aiohttp session."""
    global _session
    _session = aiohttp.ClientSession()


async def close_session() -> None:
    """Close the aiohttp session."""
    global _session
    if _session and not _session.closed:
        await _session.close()
        _session = None


async def send_actuator_command(
    actuator_name: str, state: str, retries: int = 3
) -> bool:
    """
    Send an actuator command to the simulator.

    POST /api/actuators/{actuator_name}   body: {"state": "ON" | "OFF"}

    Returns True on success, False on failure after retries.
    """
    url = f"{settings.SIMULATOR_URL}/api/actuators/{actuator_name}"
    payload = {"state": state.upper()}

    for attempt in range(1, retries + 1):
        try:
            async with _session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    logger.info(
                        "Actuator command sent: %s → %s (response: %s)",
                        actuator_name, state, result,
                    )
                    return True
                else:
                    body = await resp.text()
                    logger.warning(
                        "Actuator %s returned %d (attempt %d/%d): %s",
                        actuator_name, resp.status, attempt, retries, body,
                    )
        except Exception as e:
            logger.warning(
                "Actuator %s request failed (attempt %d/%d): %s",
                actuator_name, attempt, retries, e,
            )
        # Exponential backoff between retries
        if attempt < retries:
            await asyncio.sleep(2 ** (attempt - 1))

    logger.error(
        "Failed to send command to actuator %s after %d retries.", actuator_name, retries
    )
    return False
