"""Conversation Node - Routes to Agent 1 for intent extraction."""

import httpx
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.state import TwinForgeState

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


async def conversation_node(state: TwinForgeState) -> dict[str, Any]:
    """Send the user message to Agent 1 (Conversation) to determine intent.

    Agent 1 processes the natural language input and returns a structured
    response with the detected intent, which drives the routing decision.
    """
    errors: list[str] = list(state.get("errors", []))

    request_body = {
        "session_id": state.get("session_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
        "source_agent": "langgraph-orchestrator",
        "payload": {
            "message": state.get("user_message", ""),
            **(state.get("payload", {})),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_signature": "",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AGENT_1_URL}/process",
                json=request_body,
            )
            result = resp.json()

            # Extract intent from the conversation agent's response
            payload = result.get("payload", {})
            intent = (
                payload.get("intent")
                or payload.get("action")
                or payload.get("detected_intent")
                or "unknown"
            )

            return {
                "intent": intent,
                "conversation_result": result,
                "current_step": "conversation",
            }

    except httpx.TimeoutException:
        logger.warning("Conversation agent timed out")
        errors.append("Conversation agent timed out")
        return {
            "intent": "unknown",
            "conversation_result": {"error": "timeout"},
            "errors": errors,
            "current_step": "conversation",
        }

    except Exception as e:
        logger.warning(f"Conversation agent unavailable: {e}")
        errors.append(f"Conversation agent error: {str(e)[:200]}")
        return {
            "intent": "unknown",
            "conversation_result": {"error": str(e)[:200]},
            "errors": errors,
            "current_step": "conversation",
        }
