"""LangGraph workflow graph definition for TwinForge orchestrator.

Defines a StateGraph with 6 nodes and conditional routing:

    START → security → (blocked?) → conversation → router →
        ├─► orchestrator → verifier → respond → END
        ├─► data        → verifier → respond → END
        └─► respond                           → END
"""

import logging
from datetime import datetime, timezone
from typing import Any

from langgraph.graph import StateGraph, END

from app.state import TwinForgeState
from app.nodes.security_node import security_node
from app.nodes.conversation_node import conversation_node
from app.nodes.orchestrator_node import orchestrator_node
from app.nodes.data_node import data_node
from app.nodes.verifier_node import verifier_node

logger = logging.getLogger(__name__)

# --- Intent → route mapping ---
ORCHESTRATOR_INTENTS = {
    "create_digital_twin",
    "query_kpi",
    "general_query",
    "equipment_control",
}
DATA_INTENTS = {
    "query_telemetry",
    "detect_anomalies",
    "run_simulation",
}


# =====================================================================
# Respond node (assembles final output from whatever results are available)
# =====================================================================

async def respond_node(state: TwinForgeState) -> dict[str, Any]:
    """Assemble the final response from all available agent results."""

    # If security blocked the request, return early
    if not state.get("security_cleared", True):
        return {
            "final_response": {
                "status": "blocked",
                "detail": "Request blocked by security screening",
                "security_report": state.get("security_report", {}),
            },
            "current_step": "respond",
        }

    # Collect the primary result based on route
    route = state.get("route", "respond")
    primary_result = {}

    if route == "orchestrator":
        primary_result = state.get("orchestrator_result", {})
    elif route == "data":
        primary_result = state.get("data_result", {})
    else:
        # Direct response (greeting, unknown, etc.)
        conv = state.get("conversation_result", {})
        primary_result = conv.get("payload", conv)

    # Build final response
    verifier = state.get("verifier_result", {})
    errors = state.get("errors", [])

    final = {
        "status": "success" if not errors else "partial",
        "intent": state.get("intent", "unknown"),
        "route": route,
        "result": primary_result,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    if verifier and verifier.get("payload"):
        final["verification"] = verifier

    if errors:
        final["errors"] = errors

    return {
        "final_response": final,
        "current_step": "respond",
    }


# =====================================================================
# Router functions (conditional edges)
# =====================================================================

def after_security(state: TwinForgeState) -> str:
    """Route after security node: proceed or block."""
    if state.get("security_cleared", True):
        return "conversation"
    return "respond"


def route_by_intent(state: TwinForgeState) -> str:
    """Route after conversation node based on detected intent."""
    intent = state.get("intent", "unknown")

    if intent in ORCHESTRATOR_INTENTS:
        return "orchestrator"
    elif intent in DATA_INTENTS:
        return "data"
    else:
        return "respond"


# =====================================================================
# Build the graph
# =====================================================================

def build_graph() -> StateGraph:
    """Construct and compile the TwinForge LangGraph workflow."""
    graph = StateGraph(TwinForgeState)

    # Register nodes
    graph.add_node("security", security_node)
    graph.add_node("conversation", conversation_node)
    graph.add_node("orchestrator", orchestrator_node)
    graph.add_node("data", data_node)
    graph.add_node("verifier", verifier_node)
    graph.add_node("respond", respond_node)

    # Set entry point
    graph.set_entry_point("security")

    # Security → conversation (if cleared) or → respond (if blocked)
    graph.add_conditional_edges(
        "security",
        after_security,
        {
            "conversation": "conversation",
            "respond": "respond",
        },
    )

    # Conversation → route by intent
    graph.add_conditional_edges(
        "conversation",
        route_by_intent,
        {
            "orchestrator": "orchestrator",
            "data": "data",
            "respond": "respond",
        },
    )

    # Orchestrator / Data → Verifier
    graph.add_edge("orchestrator", "verifier")
    graph.add_edge("data", "verifier")

    # Verifier → Respond
    graph.add_edge("verifier", "respond")

    # Respond → END
    graph.add_edge("respond", END)

    return graph.compile()


# Pre-compiled graph instance (used by main.py)
workflow = build_graph()
