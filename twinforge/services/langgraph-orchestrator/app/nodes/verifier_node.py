"""Verifier Node - Routes to Agent 4 for result validation."""

import httpx
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.state import TwinForgeState

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


async def verifier_node(state: TwinForgeState) -> dict[str, Any]:
    """Send the agent result to Agent 4 (Verifier/Critic) for validation.

    Agent 4 performs: KPI validation, source verification, anomaly detection,
    schema enforcement. It checks that outputs from Agent 2 or Agent 3 are
    accurate and well-formed.
    """
    errors: list[str] = list(state.get("errors", []))

    # Pick the result to verify — orchestrator or data, whichever ran
    route = state.get("route", "")
    if route == "orchestrator":
        result_to_verify = state.get("orchestrator_result", {})
        verification_type = "kpi_validation"
    elif route == "data":
        result_to_verify = state.get("data_result", {})
        verification_type = "anomaly_detection"
    else:
        # Nothing to verify (direct response path)
        return {"verifier_result": {}, "current_step": "verifier"}

    request_body = {
        "session_id": state.get("session_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
        "source_agent": "langgraph-orchestrator",
        "payload": {
            "verification_type": verification_type,
            "data": result_to_verify.get("payload", result_to_verify),
            "intent": state.get("intent", ""),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_signature": "",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AGENT_4_URL}/process",
                json=request_body,
            )
            result = resp.json()

            return {
                "verifier_result": result,
                "current_step": "verifier",
            }

    except httpx.TimeoutException:
        logger.warning("Verifier agent timed out")
        errors.append("Verifier agent timed out")
        return {
            "verifier_result": {"error": "timeout"},
            "errors": errors,
            "current_step": "verifier",
        }

    except Exception as e:
        logger.warning(f"Verifier agent unavailable: {e}")
        errors.append(f"Verifier agent error: {str(e)[:200]}")
        return {
            "verifier_result": {"error": str(e)[:200]},
            "errors": errors,
            "current_step": "verifier",
        }
