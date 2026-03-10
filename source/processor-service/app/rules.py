"""
Rule evaluation engine.

Evaluates structured IF-THEN rules against incoming UnifiedEvents.
Conditions use dot-path field access with comparison operators.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models import Condition, Operator, RuleCondition, RuleResponse

logger = logging.getLogger("processor.rules")


def _resolve_field(data: dict[str, Any], field_path: str) -> Any:
    """
    Resolve a dot-separated field path against a dict.

    Examples:
      "source"          → data["source"]
      "payload.value"   → data["payload"]["value"]
      "payload.metric"  → data["payload"]["metric"]
    """
    parts = field_path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        else:
            return None
        if current is None:
            return None
    return current


def _compare(actual: Any, operator: Operator, expected: Any) -> bool:
    """Perform a comparison between an actual value and an expected value."""
    try:
        # Coerce types for numeric comparisons
        if operator in (Operator.GT, Operator.GE, Operator.LT, Operator.LE):
            actual = float(actual)
            expected = float(expected)

        match operator:
            case Operator.EQ:
                return actual == expected
            case Operator.NE:
                return actual != expected
            case Operator.GT:
                return actual > expected
            case Operator.GE:
                return actual >= expected
            case Operator.LT:
                return actual < expected
            case Operator.LE:
                return actual <= expected
    except (TypeError, ValueError):
        return False

    return False


def evaluate_condition(event_data: dict[str, Any], condition: RuleCondition) -> bool:
    """
    Evaluate a compound rule condition against an event.

    Returns True if the condition matches.
    """
    results = []
    for cond in condition.conditions:
        actual = _resolve_field(event_data, cond.field)
        result = _compare(actual, cond.operator, cond.value)
        results.append(result)

    if condition.logic.upper() == "OR":
        return any(results)
    return all(results)  # Default: AND


def evaluate_rules(
    event_data: dict[str, Any], rules: list[RuleResponse]
) -> list[RuleResponse]:
    """
    Evaluate an event against all active rules.

    Returns a list of rules that matched (triggered).
    Rules are expected to be pre-sorted by priority (highest first).
    """
    triggered = []
    for rule in rules:
        if not rule.is_active:
            continue
        try:
            if evaluate_condition(event_data, rule.condition):
                logger.info(
                    "Rule '%s' (id=%d) triggered by event from '%s'",
                    rule.name, rule.id, event_data.get("source", "?"),
                )
                triggered.append(rule)
        except Exception as e:
            logger.error("Error evaluating rule '%s' (id=%d): %s", rule.name, rule.id, e)

    return triggered
