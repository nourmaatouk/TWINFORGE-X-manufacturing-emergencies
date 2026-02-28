"""Data Node - Routes to Agent 3 for IoT/telemetry operations."""

import httpx
import logging
from datetime import datetime, timezone
from typing import Any

from app.config import settings
from app.state import TwinForgeState

logger = logging.getLogger(__name__)

TIMEOUT = 30.0


async def data_node(state: TwinForgeState) -> dict[str, Any]:
    """Forward the request to Agent 3 (Data IoT).

    Agent 3 handles: query_telemetry, detect_anomalies, run_simulation.
    It connects to InfluxDB, MQTT, and Redis for sensor data and
    anomaly detection.
    """
    errors: list[str] = list(state.get("errors", []))

    request_body = {
        "session_id": state.get("session_id", ""),
        "tenant_id": state.get("tenant_id", "default"),
        "source_agent": "langgraph-orchestrator",
        "payload": {
            "intent": state.get("intent", "query_telemetry"),
            "message": state.get("user_message", ""),
            **(state.get("payload", {})),
        },
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "message_signature": "",
    }

    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(
                f"{settings.AGENT_3_URL}/process",
                json=request_body,
            )
            result = resp.json()

            return {
                "data_result": result,
                "current_step": "data",
            }

    except httpx.TimeoutException:
        logger.warning("Data-IoT agent timed out")
        errors.append("Data-IoT agent timed out")
        return {
            "data_result": {"error": "timeout"},
            "errors": errors,
            "current_step": "data",
        }

    except Exception as e:
        logger.warning(f"Data-IoT agent unavailable: {e}")
        errors.append(f"Data-IoT agent error: {str(e)[:200]}")
        return {
            "data_result": {"error": str(e)[:200]},
            "errors": errors,
            "current_step": "data",
        }
