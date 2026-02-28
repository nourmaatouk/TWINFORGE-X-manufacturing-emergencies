"""Orchestrator Node - Routes to Agent 2 for digital twin operations."""

import httpx
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.state import TwinForgeState

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


async def orchestrator_node(state: TwinForgeState) -> dict[str, Any]:
    """Forward the request to Agent 2 (Orchestrator/Executor).

    Agent 2 handles: create_digital_twin, query_kpi, general_query,
    equipment_control. It routes internally to AASCreator, KPIEngine,
    or RAGRetriever based on the intent.
    """
    errors: list[str] = list(state.get("errors", []))

    request_body = {
        "session_id": state.get("session_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
        "source_agent": "langgraph-orchestrator",
        "payload": {
            "intent": state.get("intent", "general_query"),
            "message": state.get("user_message", ""),
            **(state.get("payload", {})),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_signature": "",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AGENT_2_URL}/process",
                json=request_body,
            )
            result = resp.json()

            return {
                "orchestrator_result": result,
                "current_step": "orchestrator",
            }

    except httpx.TimeoutException:
        logger.warning("Orchestrator agent timed out")
        errors.append("Orchestrator agent timed out")
        return {
            "orchestrator_result": {"error": "timeout"},
            "errors": errors,
            "current_step": "orchestrator",
        }

    except Exception as e:
        logger.warning(f"Orchestrator agent unavailable: {e}")
        errors.append(f"Orchestrator agent error: {str(e)[:200]}")
        return {
            "orchestrator_result": {"error": str(e)[:200]},
            "errors": errors,
            "current_step": "orchestrator",
        }
