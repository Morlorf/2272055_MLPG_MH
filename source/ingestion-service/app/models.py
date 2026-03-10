"""
Pydantic models implementing the Unified Event Schema.

Handles normalization from 4 different simulator response schemas:
  - rest.scalar.v1    (temperature, humidity, co2, pressure)
  - rest.chemistry.v1 (pH, VOC — multi-measurement)
  - rest.level.v1     (water tank — level_pct + level_liters)
  - rest.particulate.v1 (PM — pm1, pm2.5, pm10)
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ── Enums ────────────────────────────────────────────────────

class EventType(str, Enum):
    SENSOR_READING = "sensor_reading"
    ACTUATOR_COMMAND = "actuator_command"
    ALERT = "alert"


class SensorStatus(str, Enum):
    OK = "ok"
    WARNING = "warning"


# ── Unified Event Schema ────────────────────────────────────

class SensorPayload(BaseModel):
    """Payload for a sensor_reading event."""
    metric: str
    value: float
    unit: str
    status: str = "ok"


class ActuatorPayload(BaseModel):
    """Payload for an actuator_command event."""
    actuator_id: str
    command: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    triggered_by: str = "manual"


class AlertPayload(BaseModel):
    """Payload for an alert event."""
    severity: str  # warning | critical
    message: str
    related_source: str | None = None
    threshold_breached: dict[str, Any] | None = None


class UnifiedEvent(BaseModel):
    """The canonical event schema used throughout the system."""
    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    source: str
    event_type: EventType
    location: str
    payload: dict[str, Any]
    metadata: dict[str, Any] | None = None


# ── Location Mapping ────────────────────────────────────────
# Maps simulator sensor_id prefixes to habitat zones

SENSOR_LOCATION_MAP: dict[str, str] = {
    "greenhouse_temperature": "greenhouse",
    "entrance_humidity": "entrance",
    "co2_hall": "hall",
    "hydroponic_ph": "greenhouse",
    "water_tank_level": "storage",
    "corridor_pressure": "corridor",
    "air_quality_pm25": "habitat",
    "air_quality_voc": "habitat",
}


# ── Normalizer Functions ────────────────────────────────────

def _status_from_simulator(raw_status: str) -> str:
    """Convert simulator status string to our status enum."""
    mapping = {"ok": "ok", "warning": "warning"}
    return mapping.get(raw_status, "ok")


def normalize_scalar(raw: dict) -> list[UnifiedEvent]:
    """Normalize a rest.scalar.v1 response into unified events."""
    sensor_id = raw["sensor_id"]
    return [
        UnifiedEvent(
            source=sensor_id,
            event_type=EventType.SENSOR_READING,
            location=SENSOR_LOCATION_MAP.get(sensor_id, "unknown"),
            payload=SensorPayload(
                metric=raw["metric"],
                value=raw["value"],
                unit=raw["unit"],
                status=_status_from_simulator(raw.get("status", "ok")),
            ).model_dump(),
            metadata={
                "ingestion_method": "rest_polling",
                "schema_id": "rest.scalar.v1",
                "raw_captured_at": raw.get("captured_at"),
            },
        )
    ]


def normalize_chemistry(raw: dict) -> list[UnifiedEvent]:
    """Normalize a rest.chemistry.v1 response (multi-measurement)."""
    sensor_id = raw["sensor_id"]
    events = []
    for m in raw.get("measurements", []):
        events.append(
            UnifiedEvent(
                source=sensor_id,
                event_type=EventType.SENSOR_READING,
                location=SENSOR_LOCATION_MAP.get(sensor_id, "unknown"),
                payload=SensorPayload(
                    metric=m["metric"],
                    value=m["value"],
                    unit=m["unit"],
                    status=_status_from_simulator(raw.get("status", "ok")),
                ).model_dump(),
                metadata={
                    "ingestion_method": "rest_polling",
                    "schema_id": "rest.chemistry.v1",
                    "raw_captured_at": raw.get("captured_at"),
                },
            )
        )
    return events


def normalize_level(raw: dict) -> list[UnifiedEvent]:
    """Normalize a rest.level.v1 response (dual value: pct + liters)."""
    sensor_id = raw["sensor_id"]
    status = _status_from_simulator(raw.get("status", "ok"))
    return [
        UnifiedEvent(
            source=sensor_id,
            event_type=EventType.SENSOR_READING,
            location=SENSOR_LOCATION_MAP.get(sensor_id, "unknown"),
            payload=SensorPayload(
                metric="level_pct",
                value=raw["level_pct"],
                unit="%",
                status=status,
            ).model_dump(),
            metadata={
                "ingestion_method": "rest_polling",
                "schema_id": "rest.level.v1",
                "raw_captured_at": raw.get("captured_at"),
            },
        ),
        UnifiedEvent(
            source=sensor_id,
            event_type=EventType.SENSOR_READING,
            location=SENSOR_LOCATION_MAP.get(sensor_id, "unknown"),
            payload=SensorPayload(
                metric="level_liters",
                value=raw["level_liters"],
                unit="L",
                status=status,
            ).model_dump(),
            metadata={
                "ingestion_method": "rest_polling",
                "schema_id": "rest.level.v1",
                "raw_captured_at": raw.get("captured_at"),
            },
        ),
    ]


def normalize_particulate(raw: dict) -> list[UnifiedEvent]:
    """Normalize a rest.particulate.v1 response (pm1, pm2.5, pm10)."""
    sensor_id = raw["sensor_id"]
    status = _status_from_simulator(raw.get("status", "ok"))
    particles = [
        ("pm1_ug_m3", raw.get("pm1_ug_m3", 0), "µg/m³"),
        ("pm25_ug_m3", raw.get("pm25_ug_m3", 0), "µg/m³"),
        ("pm10_ug_m3", raw.get("pm10_ug_m3", 0), "µg/m³"),
    ]
    return [
        UnifiedEvent(
            source=sensor_id,
            event_type=EventType.SENSOR_READING,
            location=SENSOR_LOCATION_MAP.get(sensor_id, "unknown"),
            payload=SensorPayload(
                metric=metric,
                value=value,
                unit=unit,
                status=status,
            ).model_dump(),
            metadata={
                "ingestion_method": "rest_polling",
                "schema_id": "rest.particulate.v1",
                "raw_captured_at": raw.get("captured_at"),
            },
        )
        for metric, value, unit in particles
    ]


# ── Schema-to-Normalizer Registry ───────────────────────────

NORMALIZERS: dict[str, callable] = {
    "rest.scalar.v1": normalize_scalar,
    "rest.chemistry.v1": normalize_chemistry,
    "rest.level.v1": normalize_level,
    "rest.particulate.v1": normalize_particulate,
}
