"""Security Node - Screens requests through Agent 5 (Security Guardian)."""

import httpx
import logging
from typing import Any

from app.config import settings
from app.state import TwinForgeState

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


async def security_node(state: TwinForgeState) -> dict[str, Any]:
    """Send the user payload to Agent 5 for threat screening.

    Sets security_cleared=True unless Agent 5 returns a CRITICAL threat
    with a BLOCK recommendation. All other threats still allow the request
    through (elevated monitoring, not hard blocking).
    """
    errors: list[str] = list(state.get("errors", []))

    request_body = {
        "event_type": "MESSAGE",
        "source_agent": "langgraph-orchestrator",
        "payload": {
            "message": state.get("user_message", ""),
            **(state.get("payload", {})),
        },
        "session_id": state.get("session_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AGENT_5_URL}/analyze",
                json=request_body,
            )
            result = resp.json()

            threat_detected = result.get("threat_detected", False)
            severity = result.get("severity", "LOW")
            action = result.get("recommended_action", "LOG")

            # Only block on CRITICAL + BLOCK — everything else flows through
            blocked = threat_detected and severity == "CRITICAL" and action == "BLOCK"

            return {
                "security_cleared": not blocked,
                "security_report": result,
                "current_step": "security",
            }

    except httpx.TimeoutException:
        logger.warning("Security agent timed out — allowing request through")
        errors.append("Security agent timed out")
        return {
            "security_cleared": True,
            "security_report": {"error": "timeout", "detail": "Agent 5 unreachable"},
            "errors": errors,
            "current_step": "security",
        }

    except Exception as e:
        logger.warning(f"Security agent unavailable: {e}")
        errors.append(f"Security agent error: {str(e)[:200]}")
        return {
            "security_cleared": True,
            "security_report": {"error": "unavailable", "detail": str(e)[:200]},
            "errors": errors,
            "current_step": "security",
        }
