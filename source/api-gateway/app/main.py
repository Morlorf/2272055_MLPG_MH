"""
API Gateway — FastAPI application.

Acts as the single entry point for the frontend:
  1. WebSocket /ws — real-time event stream to frontend
  2. Proxies REST requests to the Processor Service (rules + state)
  3. Proxies actuator commands to the Simulator
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

import aiohttp
from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.ws_manager import manager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("gateway")

_http_session: aiohttp.ClientSession | None = None


# ── Lifespan ─────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_session
    logger.info("API Gateway starting...")
    _http_session = aiohttp.ClientSession()

    # Start RabbitMQ → WebSocket bridge
    mq_task = asyncio.create_task(manager.start_rabbitmq_listener())

    yield

    logger.info("API Gateway shutting down...")
    mq_task.cancel()
    try:
        await mq_task
    except asyncio.CancelledError:
        pass
    await manager.close()
    if _http_session and not _http_session.closed:
        await _http_session.close()
    logger.info("API Gateway stopped.")


# ── App ──────────────────────────────────────────────────────

app = FastAPI(
    title="Mars Habitat — API Gateway",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ───────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "service": "api-gateway"}


# ── WebSocket ────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive; frontend can also send commands
            data = await websocket.receive_text()
            logger.debug("WS received: %s", data)
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Proxy Helpers ────────────────────────────────────────────

async def _proxy_get(url: str) -> JSONResponse:
    async with _http_session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        data = await resp.json()
        return JSONResponse(content=data, status_code=resp.status)


async def _proxy_post(url: str, body: dict) -> JSONResponse:
    async with _http_session.post(
        url, json=body, timeout=aiohttp.ClientTimeout(total=10)
    ) as resp:
        data = await resp.json()
        return JSONResponse(content=data, status_code=resp.status)


async def _proxy_put(url: str, body: dict) -> JSONResponse:
    async with _http_session.put(
        url, json=body, timeout=aiohttp.ClientTimeout(total=10)
    ) as resp:
        data = await resp.json()
        return JSONResponse(content=data, status_code=resp.status)


async def _proxy_delete(url: str) -> JSONResponse:
    async with _http_session.delete(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
        if resp.status == 204:
            return JSONResponse(content=None, status_code=204)
        data = await resp.json()
        return JSONResponse(content=data, status_code=resp.status)


# ── State Proxy ──────────────────────────────────────────────

@app.get("/api/state")
async def get_state():
    return await _proxy_get(f"{settings.PROCESSOR_SERVICE_URL}/api/state")


@app.get("/api/state/{source}")
async def get_sensor_state(source: str):
    return await _proxy_get(f"{settings.PROCESSOR_SERVICE_URL}/api/state/{source}")


# ── Conflict Proxy ────────────────────────────────────────────

@app.get("/api/conflicts")
async def list_conflicts():
    """Proxy for active rule conflicts."""
    return await _proxy_get(f"{settings.PROCESSOR_SERVICE_URL}/api/conflicts")


# ── Rules Proxy ──────────────────────────────────────────────

@app.get("/api/rules")
async def list_rules():
    return await _proxy_get(f"{settings.PROCESSOR_SERVICE_URL}/api/rules")


@app.get("/api/rules/{rule_id}")
async def get_rule(rule_id: int):
    return await _proxy_get(f"{settings.PROCESSOR_SERVICE_URL}/api/rules/{rule_id}")


@app.post("/api/rules")
async def create_rule(request: Request):
    body = await request.json()
    return await _proxy_post(f"{settings.PROCESSOR_SERVICE_URL}/api/rules", body)


@app.put("/api/rules/{rule_id}")
async def update_rule(rule_id: int, request: Request):
    body = await request.json()
    return await _proxy_put(f"{settings.PROCESSOR_SERVICE_URL}/api/rules/{rule_id}", body)


@app.delete("/api/rules/{rule_id}")
async def delete_rule(rule_id: int):
    return await _proxy_delete(f"{settings.PROCESSOR_SERVICE_URL}/api/rules/{rule_id}")


# ── Actuators Proxy ──────────────────────────────────────────

@app.get("/api/actuators")
async def list_actuators():
    return await _proxy_get(f"{settings.SIMULATOR_URL}/api/actuators")


@app.post("/api/actuators/{actuator_name}")
async def set_actuator(actuator_name: str, request: Request):
    body = await request.json()
    return await _proxy_post(
        f"{settings.SIMULATOR_URL}/api/actuators/{actuator_name}", body
    )
