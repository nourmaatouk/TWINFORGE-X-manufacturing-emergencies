"""
KPI Validator - Validates computed KPIs for plausibility and correctness.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

KPI_RULES = {
    "oee": {"min": 0.0, "max": 1.0},
    "availability": {"min": 0.0, "max": 1.0},
    "performance": {"min": 0.0, "max": 1.0},
    "quality_rate": {"min": 0.0, "max": 1.0},
    "throughput": {"min": 0.0, "max": 100000.0},
}


class KPIValidator:
    """Validates KPI values against expected ranges and consistency rules."""

    def validate(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Validate KPI results."""
        errors = []
        warnings = []
        kpi_name = payload.get("kpi_name", "")
        result = payload.get("result", {})

        # Check value ranges
        for key, value in result.items():
            if key in KPI_RULES and isinstance(value, (int, float)):
                rule = KPI_RULES[key]
                if value < rule["min"] or value > rule["max"]:
                    errors.append(f"{key}={value} is out of valid range [{rule['min']}, {rule['max']}]")

        # OEE consistency check
        if kpi_name == "oee":
            a = result.get("availability", 0)
            p = result.get("performance", 0)
            q = result.get("quality", 0)
            computed_oee = a * p * q
            reported_oee = result.get("oee", 0)
            if abs(computed_oee - reported_oee) > 0.001:
                errors.append(f"OEE inconsistency: A*P*Q={computed_oee:.4f} != reported {reported_oee:.4f}")

        return {
            "is_valid": len(errors) == 0,
            "verification_type": "kpi",
            "errors": errors,
            "warnings": warnings,
        }
