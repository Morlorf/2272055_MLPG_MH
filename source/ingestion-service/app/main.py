"""
Ingestion Service — FastAPI application entry point.

On startup:
  1. Connects to RabbitMQ (with retry)
  2. Starts the async sensor polling loop as a background task

Exposes:
  GET /health — service health check
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.poller import poller
from app.rabbitmq import publisher

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ingestion")


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage startup / shutdown of background services."""
    # Startup
    logger.info("Ingestion Service starting...")
    logger.info("Simulator URL: %s", settings.SIMULATOR_URL)
    logger.info("RabbitMQ URL:  %s", settings.rabbitmq_url)
    logger.info("Polling interval: %ds", settings.POLLING_INTERVAL_SECONDS)

    await publisher.connect()
    polling_task = asyncio.create_task(poller.start())

    yield

    # Shutdown
    logger.info("Ingestion Service shutting down...")
    await poller.stop()
    polling_task.cancel()
    try:
        await polling_task
    except asyncio.CancelledError:
        pass
    await publisher.close()
    logger.info("Ingestion Service stopped.")


# ── FastAPI App ──────────────────────────────────────────────

app = FastAPI(
    title="Mars Habitat — Ingestion Service",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "ingestion-service",
        "simulator_url": settings.SIMULATOR_URL,
        "polling_interval": settings.POLLING_INTERVAL_SECONDS,
    }
