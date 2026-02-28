"""
TWINFORGE Agent 3 — Sensor Validator
Validates sensor readings against configurable plausible ranges.
"""

import logging
from typing import Optional

from app.models.schemas import MachineTelemetry

logger = logging.getLogger(__name__)


# Plausible ranges for industrial sensor readings
DEFAULT_RANGES: dict[str, tuple[float, float]] = {
    "energy_kwh": (0.0, 500.0),
    "water_liters": (0.0, 200.0),
    "vibration": (0.0, 50.0),
    "temperature": (-40.0, 200.0),
    "failure_risk_score": (0.0, 1.0),
}


class SensorValidator:
    """Validates sensor telemetry against configurable plausible ranges."""

    def __init__(self, ranges: Optional[dict[str, tuple[float, float]]] = None) -> None:
        self.ranges = ranges or DEFAULT_RANGES.copy()

    def validate(self, record: MachineTelemetry) -> tuple[bool, str]:
        """
        Validate a telemetry record.

        Returns:
            (is_valid, error_message)
        """
        # Check machine_id
        if not record.machine_id or not record.machine_id.strip():
            return False, "machine_id is empty"

        # Check numeric ranges
        for field_name, (min_val, max_val) in self.ranges.items():
            value = getattr(record, field_name, None)
            if value is not None and not (min_val <= value <= max_val):
                msg = f"{field_name}={value} out of range [{min_val}, {max_val}]"
                logger.warning("Validation failed for %s: %s", record.machine_id, msg)
                return False, msg

        # Check timestamp is not None
        if record.timestamp is None:
            return False, "timestamp is missing"

        return True, ""

    def set_range(self, field: str, min_val: float, max_val: float) -> None:
        """Update the plausible range for a specific field."""
        self.ranges[field] = (min_val, max_val)
        logger.info("Updated range for %s: [%s, %s]", field, min_val, max_val)
