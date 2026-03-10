"""
Arbitrator for actuator commands.

Queues incoming commands within a time window, applying Safe-State logic
and deterministic tie-breaking for conflicting commands.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

from app.actuator import send_actuator_command
from app.models import EventType, RuleResponse, UnifiedEvent
from app.rabbitmq_publisher import publisher

logger = logging.getLogger("processor.arbitrator")

class Arbitrator:
    def __init__(self, window_seconds: float = 0.5):
        self.window_seconds = window_seconds
        # Maps actuator_name -> list of (rule, state, event_data)
        self._queues: dict[str, list[tuple[RuleResponse, str, dict]]] = {}
        # Tracks active asyncio tasks for process windows
        self._tasks: dict[str, asyncio.Task] = {}
        # Tracks active UI conflict state for actuators (True if currently in conflict)
        self._active_conflicts: dict[str, bool] = {}
        # Tracks rule IDs involved in each active conflict so the UI
        # can reconstruct conflict highlights after a page reload.
        self._active_conflict_rule_ids: dict[str, list[int]] = {}

    async def submit_command(self, rule: RuleResponse, actuator: str, state: str, event_data: dict) -> None:
        """Submit a command to the arbitrator queue."""
        if actuator not in self._queues:
            self._queues[actuator] = []
        
        self._queues[actuator].append((rule, state, event_data))

        # Start the processing window if not already active
        if actuator not in self._tasks or self._tasks[actuator].done():
            task = asyncio.create_task(self._process_window(actuator))
            self._tasks[actuator] = task
            # Fire and forget; the task will clear itself from _tasks when it finishes

    async def _process_window(self, actuator: str) -> None:
        """Wait for the window to close, then resolve and commit."""
        await asyncio.sleep(self.window_seconds)

        commands = self._queues.pop(actuator, [])
        if not commands:
            return

        # 1. Raggruppamento delle intenzioni (commands è già raggruppato per questo attuatore)
        # commands: list di tuple (rule, state, event_data)
        
        rules_asking_on = [cmd[0].id for cmd in commands if cmd[1].upper() == "ON"]
        rules_asking_off = [cmd[0].id for cmd in commands if cmd[1].upper() == "OFF"]
        
        original_event = commands[0][2]
        currently_in_conflict = self._active_conflicts.get(actuator, False)
        current_rule_ids = self._active_conflict_rule_ids.get(actuator, [])

        # 2. Controlla il conflitto
        if len(rules_asking_on) > 0 and len(rules_asking_off) > 0:
            # CONFLITTO RILEVATO
            # Default di sicurezza
            final_state = "OFF"
            
            # Tutte le regole coinvolte vanno in warning
            all_involved_rules = sorted(list(set(rules_asking_on + rules_asking_off)))
            
            if not currently_in_conflict or current_rule_ids != all_involved_rules:
                self._active_conflicts[actuator] = True
                self._active_conflict_rule_ids[actuator] = all_involved_rules
                await self._broadcast_conflict(actuator, all_involved_rules, resolved=False, event_data=original_event)

            # Tie breaker pseudo-casuale oppure basato su ID minore tra quelli validi
            candidates = [cmd for cmd in commands if cmd[1].upper() == final_state]
            winner_rule = min(candidates, key=lambda x: x[0].id)[0] if candidates else commands[0][0]

        else:
            # NESSUN CONFLITTO (Tutti d'accordo)
            final_state = "ON" if len(rules_asking_on) > 0 else "OFF"
            
            # Rimuove eventuali warning precedenti
            all_involved_rules = sorted(list(set(rules_asking_on + rules_asking_off)))
            
            if currently_in_conflict:
                self._active_conflicts[actuator] = False
                self._active_conflict_rule_ids.pop(actuator, None)
                await self._broadcast_conflict(actuator, [], resolved=True, event_data=original_event)

            candidates = [cmd for cmd in commands if cmd[1].upper() == final_state]
            winner_rule = min(candidates, key=lambda x: x[0].id)[0] if candidates else commands[0][0]

        logger.info(
            "Arbitrator resolved %d commands for %s -> %s (Winner Rule: %d)",
            len(commands), actuator, final_state, winner_rule.id
        )

        # Commit
        success = await send_actuator_command(actuator, final_state)

        # Publish Actuator Command Audit Event
        await self._publish_actuator_event(actuator, final_state, winner_rule, original_event, success)

        # Alert if failure
        if not success:
            await self._publish_alert(actuator, final_state, winner_rule, original_event)

        # Clear the task token so the next event starts a new window
        self._tasks.pop(actuator, None)

    def _resolve(self, commands: list[tuple[RuleResponse, str, dict]]) -> tuple[str, RuleResponse]:
        """
        Legacy resolver left intact as fallback.
        """
        has_off = any(cmd[1].upper() == "OFF" for cmd in commands)
        winning_state = "OFF" if has_off else "ON"
        candidates = [cmd for cmd in commands if cmd[1].upper() == winning_state]
        winner = min(candidates, key=lambda x: x[0].id)
        return winning_state, winner[0]

    async def _broadcast_conflict(self, actuator: str, rule_ids: list[int], resolved: bool, event_data: dict) -> None:
        """Publish a rule_conflict event so the UI can update."""
        conflict_event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": actuator,
            "event_type": EventType.RULE_CONFLICT.value,
            "location": event_data.get("location", "unknown"),
            "payload": {
                "actuator_id": actuator,
                "rule_ids": rule_ids,
                "resolved": resolved,
            },
            "metadata": {
                "trigger_source": event_data.get("source", "unknown"),
            },
        }
        try:
            event = UnifiedEvent(**conflict_event)
            await publisher.publish(event)
            logger.info("Broadcast conflict event for %s (resolved=%s)", actuator, resolved)
        except Exception as e:
            logger.error("Failed to publish conflict event: %s", e)

    async def _publish_actuator_event(self, actuator: str, state: str, rule: RuleResponse, event_data: dict, success: bool) -> None:
        """Publish an actuator_command event for audit trail."""
        actuator_event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": actuator,
            "event_type": EventType.ACTUATOR_COMMAND.value,
            "location": event_data.get("location", "unknown"),
            "payload": {
                "actuator_id": actuator,
                "command": state,
                "parameters": {},
                "triggered_by": f"rule-{rule.id}",
                "success": success,
            },
            "metadata": {
                "rule_name": rule.name,
                "trigger_source": event_data.get("source", "unknown"),
            },
        }
        try:
            event = UnifiedEvent(**actuator_event)
            await publisher.publish(event)
        except Exception as e:
            logger.error("Failed to publish actuator event: %s", e)

    async def _publish_alert(self, actuator: str, state: str, rule: RuleResponse, event_data: dict) -> None:
        """Publish an alert if the actuator command failed."""
        alert_event = {
            "event_id": str(uuid.uuid4()),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "source": actuator,
            "event_type": EventType.ALERT.value,
            "location": event_data.get("location", "unknown"),
            "payload": {
                "severity": "critical",
                "message": f"Actuator '{actuator}' failed to execute command '{state}' after retries",
                "related_source": event_data.get("source", "unknown"),
                "threshold_breached": None,
            },
            "metadata": {
                "rule_name": rule.name,
                "rule_id": rule.id,
            },
        }
        try:
            alert = UnifiedEvent(**alert_event)
            await publisher.publish(alert)
        except Exception as e:
            logger.error("Failed to publish alert event: %s", e)

    def get_active_conflicts(self) -> dict[str, list[int]]:
        """
        Return a snapshot of currently active conflicts.

        Shape:
          { "<actuator_id>": [<rule_id>, ...], ... }

        Used by the API to let the frontend restore conflict badges
        and borders after a page reload.
        """
        return dict(self._active_conflict_rule_ids)

# Singleton instance for the app
arbitrator = Arbitrator(window_seconds=0.5)
