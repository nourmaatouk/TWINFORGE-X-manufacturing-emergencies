"""
Source Verifier - Verifies the provenance and authenticity of data sources.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

TRUSTED_SOURCES = [
    "opcua_simulator",
    "mqtt_simulator",
    "mcp_mock_server",
    "influxdb",
    "postgresql",
    "knowledge_base",
]


class SourceVerifier:
    """Verifies that data comes from trusted and authenticated sources."""

    def verify(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Verify a data source is trusted and authentic."""
        source = payload.get("source", "unknown")
        errors = []
        warnings = []

        if source not in TRUSTED_SOURCES:
            errors.append(f"Untrusted data source: {source}")

        has_signature = bool(payload.get("message_signature", ""))
        if not has_signature:
            warnings.append("Data has no message signature - cannot verify integrity")

        return {
            "is_valid": len(errors) == 0,
            "verification_type": "source",
            "source": source,
            "trusted": source in TRUSTED_SOURCES,
            "signed": has_signature,
            "errors": errors,
            "warnings": warnings,
        }
