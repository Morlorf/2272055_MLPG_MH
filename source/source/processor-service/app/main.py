"""
Processor Service — FastAPI application entry point.

On startup:
  1. Initializes SQLite database
  2. Connects RabbitMQ publisher
  3. Loads active rules into memory
  4. Creates HTTP session for actuator commands
  5. Starts RabbitMQ consumer as background task

Exposes:
  - Rule CRUD API
  - State query API
  - Health check
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.actuator import close_session, init_session
from app.config import settings
from app.consumer import close_consumer, connect_and_consume, refresh_rules_cache
from app.database import close_db, init_db
from app.rabbitmq_publisher import publisher
from app.routes import router

# ── Logging ──────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("processor")


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Processor Service starting...")

    # 1. Init database
    await init_db()

    # 2. Connect publisher
    await publisher.connect()

    # 3. Load rules into memory
    await refresh_rules_cache()

    # 4. Init actuator HTTP session
    await init_session()

    # 5. Start consumer background task
    consumer_task = asyncio.create_task(connect_and_consume())

    yield

    # Shutdown
    logger.info("Processor Service shutting down...")
    consumer_task.cancel()
    try:
        await consumer_task
    except asyncio.CancelledError:
        pass
    await close_consumer()
    await publisher.close()
    await close_session()
    await close_db()
    logger.info("Processor Service stopped.")


# ── FastAPI App ──────────────────────────────────────────────

app = FastAPI(
    title="Mars Habitat — Processor Service",
    version="1.0.0",
    lifespan=lifespan,
)
app.include_router(router)
