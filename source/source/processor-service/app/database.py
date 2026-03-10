"""
SQLite database for persisting automation rules.

Uses aiosqlite for async I/O. The database is initialized on startup
and provides full CRUD operations for rules.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone

import aiosqlite

from app.config import settings
from app.models import (
    RuleAction,
    RuleCondition,
    RuleCreate,
    RuleResponse,
    RuleUpdate,
)

logger = logging.getLogger("processor.database")

_db: aiosqlite.Connection | None = None


# ── Lifecycle ────────────────────────────────────────────────

async def init_db() -> None:
    """Initialize the SQLite database and create the rules table."""
    global _db

    # Ensure the data directory exists
    os.makedirs(os.path.dirname(settings.DATABASE_PATH), exist_ok=True)

    _db = await aiosqlite.connect(settings.DATABASE_PATH)
    _db.row_factory = aiosqlite.Row

    await _db.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            condition_json TEXT NOT NULL,
            action_json TEXT NOT NULL,
            is_active INTEGER DEFAULT 1,
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    await _db.commit()
    logger.info("Database initialized at %s", settings.DATABASE_PATH)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None
        logger.info("Database connection closed.")


# ── Helpers ──────────────────────────────────────────────────

def _row_to_response(row: aiosqlite.Row) -> RuleResponse:
    """Convert a database row to a RuleResponse."""
    return RuleResponse(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        condition=RuleCondition.model_validate_json(row["condition_json"]),
        action=RuleAction.model_validate_json(row["action_json"]),
        is_active=bool(row["is_active"]),
        priority=row["priority"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── CRUD Operations ──────────────────────────────────────────

async def create_rule(rule: RuleCreate) -> RuleResponse:
    """Insert a new rule and return it."""
    now = _now()
    cursor = await _db.execute(
        """INSERT INTO rules (name, description, condition_json, action_json,
                              is_active, priority, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            rule.name,
            rule.description,
            rule.condition.model_dump_json(),
            rule.action.model_dump_json(),
            int(rule.is_active),
            rule.priority,
            now,
            now,
        ),
    )
    await _db.commit()
    return await get_rule(cursor.lastrowid)


async def get_rule(rule_id: int) -> RuleResponse | None:
    """Fetch a single rule by ID."""
    async with _db.execute("SELECT * FROM rules WHERE id = ?", (rule_id,)) as cursor:
        row = await cursor.fetchone()
        return _row_to_response(row) if row else None


async def get_all_rules() -> list[RuleResponse]:
    """Fetch all rules."""
    async with _db.execute("SELECT * FROM rules ORDER BY priority DESC") as cursor:
        rows = await cursor.fetchall()
        return [_row_to_response(row) for row in rows]


async def get_active_rules() -> list[RuleResponse]:
    """Fetch only active rules, ordered by priority (highest first)."""
    async with _db.execute(
        "SELECT * FROM rules WHERE is_active = 1 ORDER BY priority DESC"
    ) as cursor:
        rows = await cursor.fetchall()
        return [_row_to_response(row) for row in rows]


async def update_rule(rule_id: int, update: RuleUpdate) -> RuleResponse | None:
    """Update an existing rule. Only provided fields are updated."""
    existing = await get_rule(rule_id)
    if not existing:
        return None

    # Merge updates
    name = update.name if update.name is not None else existing.name
    description = update.description if update.description is not None else existing.description
    condition_json = (
        update.condition.model_dump_json()
        if update.condition is not None
        else existing.condition.model_dump_json()
    )
    action_json = (
        update.action.model_dump_json()
        if update.action is not None
        else existing.action.model_dump_json()
    )
    is_active = update.is_active if update.is_active is not None else existing.is_active
    priority = update.priority if update.priority is not None else existing.priority

    await _db.execute(
        """UPDATE rules SET name=?, description=?, condition_json=?,
                            action_json=?, is_active=?, priority=?, updated_at=?
           WHERE id=?""",
        (name, description, condition_json, action_json, int(is_active), priority, _now(), rule_id),
    )
    await _db.commit()
    return await get_rule(rule_id)


async def delete_rule(rule_id: int) -> bool:
    """Delete a rule. Returns True if the rule existed."""
    cursor = await _db.execute("DELETE FROM rules WHERE id = ?", (rule_id,))
    await _db.commit()
    return cursor.rowcount > 0
