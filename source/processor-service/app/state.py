"""
In-memory sensor state cache.

Maintains a dictionary of the latest UnifiedEvent for each sensor source.
Thread-safe via asyncio (single-threaded event loop).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger("processor.state")


class StateCache:
    """Keeps the latest reading for each sensor source."""

    def __init__(self) -> None:
        self._store: dict[str, dict[str, Any]] = {}

    def update(self, event: dict[str, Any]) -> None:
        """Update the cache with a new event."""
        source = event.get("source")
        if not source:
            return
        self._store[source] = {
            **event,
            "_cached_at": datetime.now(timezone.utc).isoformat(),
        }
        logger.debug("State updated: %s", source)

    def get_all(self) -> dict[str, dict[str, Any]]:
        """Return the full state dictionary."""
        return dict(self._store)

    def get(self, source: str) -> dict[str, Any] | None:
        """Return the latest event for a specific source."""
        return self._store.get(source)

    def get_sources(self) -> list[str]:
        """Return all known source identifiers."""
        return list(self._store.keys())

    def clear(self) -> None:
        """Clear the entire cache (used in tests)."""
        self._store.clear()


# Singleton
state_cache = StateCache()
