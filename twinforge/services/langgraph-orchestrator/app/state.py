"""LangGraph shared state definition for TwinForge orchestrator."""

from typing import Any
from typing_extensions import TypedDict


class TwinForgeState(TypedDict, total=False):
    """Shared state that flows through the LangGraph workflow.

    Each node reads what it needs and returns a partial dict of updates.
    LangGraph merges updates into the running state automatically.
    """

    # --- Input (set once at workflow start) ---
    session_id: str
    tenant_id: str
    user_message: str
    payload: dict[str, Any]

    # --- Routing (set by conversation + router) ---
    intent: str          # e.g. "create_digital_twin", "query_kpi", "greeting"
    route: str           # "orchestrator", "data", or "respond"

    # --- Security (set by security node) ---
    security_cleared: bool
    security_report: dict[str, Any]

    # --- Agent results (set by respective nodes) ---
    conversation_result: dict[str, Any]
    orchestrator_result: dict[str, Any]
    data_result: dict[str, Any]
    verifier_result: dict[str, Any]

    # --- Output ---
    final_response: dict[str, Any]
    errors: list[str]
    current_step: str
