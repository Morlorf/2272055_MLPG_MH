"""
API routes for the Processor Service.

Provides:
  - Rule CRUD endpoints
  - State query endpoints
  - Health check
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.arbitrator import arbitrator
from app.consumer import refresh_rules_cache
from app.database import (
    create_rule,
    delete_rule,
    get_all_rules,
    get_rule,
    update_rule,
)
from app.models import RuleCreate, RuleResponse, RuleUpdate
from app.state import state_cache

router = APIRouter()


# ── Health ───────────────────────────────────────────────────

@router.get("/health")
async def health():
    return {
        "status": "healthy",
        "service": "processor-service",
        "cached_sensors": len(state_cache.get_sources()),
    }


# ── State Endpoints ──────────────────────────────────────────

@router.get("/api/state")
async def get_full_state():
    """Return the full in-memory state cache."""
    return state_cache.get_all()


@router.get("/api/state/{source}")
async def get_sensor_state(source: str):
    """Return the latest event for a specific sensor."""
    data = state_cache.get(source)
    if data is None:
        raise HTTPException(status_code=404, detail=f"Sensor '{source}' not found")
    return data


# ── Conflict Introspection ────────────────────────────────────

@router.get("/api/conflicts")
async def list_conflicts():
    """
    Return currently active rule conflicts.

    Shape:
      { "<actuator_id>": [<rule_id>, ...], ... }
    """
    return arbitrator.get_active_conflicts()


# ── Rule CRUD Endpoints ─────────────────────────────────────

@router.get("/api/rules", response_model=list[RuleResponse])
async def list_rules():
    """List all automation rules."""
    return await get_all_rules()


@router.get("/api/rules/{rule_id}", response_model=RuleResponse)
async def read_rule(rule_id: int):
    """Get a specific rule by ID."""
    rule = await get_rule(rule_id)
    if rule is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    return rule


@router.post("/api/rules", response_model=RuleResponse, status_code=201)
async def create_new_rule(rule: RuleCreate):
    """Create a new automation rule."""
    created = await create_rule(rule)
    await refresh_rules_cache()
    return created


@router.put("/api/rules/{rule_id}", response_model=RuleResponse)
async def update_existing_rule(rule_id: int, update: RuleUpdate):
    """Update an existing rule."""
    updated = await update_rule(rule_id, update)
    if updated is None:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await refresh_rules_cache()
    return updated


@router.delete("/api/rules/{rule_id}", status_code=204)
async def remove_rule(rule_id: int):
    """Delete a rule."""
    deleted = await delete_rule(rule_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"Rule {rule_id} not found")
    await refresh_rules_cache()
