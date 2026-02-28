"""
TWINFORGE Agent 3 — MQTT Handler
MQTT topic management, message parsing, and routing to the ingestion pipeline.
"""

import json
import logging
from typing import Any, Optional

from app.models.schemas import MachineTelemetry

logger = logging.getLogger(__name__)


# ─── Topic Mapping ───────────────────────────────────────────────────────────

TOPIC_MAP: dict[str, str] = {
    "twinforge/telemetry/energy": "energy_kwh",
    "twinforge/telemetry/water": "water_liters",
    "twinforge/telemetry/vibration": "vibration",
    "twinforge/telemetry/temperature": "temperature",
    "twinforge/telemetry/status": "status",
    "twinforge/telemetry/failure": "failure_flag",
}


class MQTTHandler:
    """
    Handles MQTT topic routing and message parsing for telemetry data.

    Supports both full telemetry messages (JSON with all fields) and
    topic-specific messages (single field per topic).
    """

    def __init__(self) -> None:
        self._pending: dict[str, dict[str, Any]] = {}

    def parse_message(self, topic: str, payload: bytes) -> Optional[MachineTelemetry]:
        """
        Parse an MQTT message payload.

        For full telemetry topics, parses the entire JSON payload.
        For field-specific topics, accumulates partial data until
        a full record is available.

        Args:
            topic: MQTT topic string
            payload: Raw message bytes

        Returns:
            MachineTelemetry if a complete record was parsed, None otherwise
        """
        try:
            data = json.loads(payload.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            logger.error("Failed to decode MQTT payload on topic %s: %s", topic, e)
            return None

        # Full telemetry message
        if isinstance(data, dict) and "machine_id" in data and "energy_kwh" in data:
            try:
                return MachineTelemetry.model_validate(data)
            except Exception as e:
                logger.warning("Invalid telemetry payload: %s", e)
                return None

        # Field-specific topic
        field_name = TOPIC_MAP.get(topic)
        if field_name and isinstance(data, dict):
            machine_id = data.get("machine_id", "unknown")
            if machine_id not in self._pending:
                self._pending[machine_id] = {"machine_id": machine_id}

            self._pending[machine_id][field_name] = data.get("value")

            # Check if we have a complete record
            required = {"energy_kwh", "water_liters", "vibration", "temperature"}
            if required.issubset(self._pending[machine_id].keys()):
                try:
                    record = MachineTelemetry.model_validate(self._pending.pop(machine_id))
                    return record
                except Exception as e:
                    logger.warning("Failed to assemble telemetry record: %s", e)
                    self._pending.pop(machine_id, None)

        return None

    @staticmethod
    def get_machine_topic(machine_id: str) -> str:
        """Get the MQTT topic for a specific machine."""
        return f"twinforge/telemetry/{machine_id}"

    @staticmethod
    def get_live_topic() -> str:
        """Get the live telemetry broadcast topic."""
        return "twinforge/telemetry/live"
