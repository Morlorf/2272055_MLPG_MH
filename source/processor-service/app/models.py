"""
Pydantic models for the Processor Service.

Includes:
  - UnifiedEvent (shared schema from ingestion)
  - Rule models (DB + API)
  - Condition / Action models for rule evaluation
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Event Schema (mirrors ingestion-service) ─────────────────

class EventType(str, Enum):
    SENSOR_READING = "sensor_reading"
    ACTUATOR_COMMAND = "actuator_command"
    ALERT = "alert"
    RULE_CONFLICT = "rule_conflict"


class UnifiedEvent(BaseModel):
    event_id: str
    timestamp: str
    source: str
    event_type: EventType
    location: str
    payload: dict[str, Any]
    metadata: dict[str, Any] | None = None


# ── Rule Condition & Action ──────────────────────────────────

class Operator(str, Enum):
    EQ = "=="
    NE = "!="
    GT = ">"
    GE = ">="
    LT = "<"
    LE = "<="


class Condition(BaseModel):
    """A single comparison condition."""
    field: str          # dot-path, e.g. "payload.value", "source", "location"
    operator: Operator
    value: Any          # the comparison value


class RuleCondition(BaseModel):
    """Compound condition with AND/OR logic."""
    logic: str = "AND"  # "AND" or "OR"
    conditions: list[Condition]


class RuleAction(BaseModel):
    """Action to trigger when a rule matches."""
    actuator: str       # e.g. "cooling_fan"
    state: str          # "ON" or "OFF"


# ── Rule CRUD Models ─────────────────────────────────────────

class RuleCreate(BaseModel):
    """Request body for creating a rule."""
    name: str
    description: str = ""
    condition: RuleCondition
    action: RuleAction
    is_active: bool = True
    priority: int = 0


class RuleUpdate(BaseModel):
    """Request body for updating a rule (all fields optional)."""
    name: str | None = None
    description: str | None = None
    condition: RuleCondition | None = None
    action: RuleAction | None = None
    is_active: bool | None = None
    priority: int | None = None


class RuleResponse(BaseModel):
    """Rule as returned by the API."""
    id: int
    name: str
    description: str
    condition: RuleCondition
    action: RuleAction
    is_active: bool
    priority: int
    created_at: str
    updated_at: str
