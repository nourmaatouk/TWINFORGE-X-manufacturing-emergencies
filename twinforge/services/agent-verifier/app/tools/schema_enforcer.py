"""
Schema Enforcer - Validates agent outputs against expected Pydantic schemas.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

REQUIRED_RESPONSE_FIELDS = ["session_id", "agent_id", "status", "payload"]


class SchemaEnforcer:
    """Enforces output schema compliance for agent responses."""

    def enforce(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Check that a payload conforms to the expected schema."""
        errors = []
        warnings = []
        data = payload.get("data", payload)

        for field in REQUIRED_RESPONSE_FIELDS:
            if field not in data:
                errors.append(f"Missing required field: {field}")

        status = data.get("status", "")
        if status and status not in ("success", "error", "blocked", "rate_limited"):
            warnings.append(f"Non-standard status value: {status}")

        return {
            "is_valid": len(errors) == 0,
            "verification_type": "schema",
            "errors": errors,
            "warnings": warnings,
        }
