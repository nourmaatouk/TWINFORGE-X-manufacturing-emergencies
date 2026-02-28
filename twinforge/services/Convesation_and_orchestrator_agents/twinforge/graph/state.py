"""
TWINFORGE — LangGraph shared state definition.
"""
from __future__ import annotations
from typing import Any, Optional
from twinforge.core.schemas import IntentResult, DataResponse, TwinResult


class TwinForgeState(dict):
    """
    Shared state flowing through the LangGraph FSM.
    Keys:
      user_message  : str
      session_id    : str
      intent_result : IntentResult | None
      data_response : DataResponse | None
      twin_result   : TwinResult | None
      final_response: str
      error         : str | None
      step_count    : int
      needs_data    : bool
    """
    pass


def create_initial_state(user_message: str, session_id: str = "default") -> dict[str, Any]:
    """Build the initial state dict for a new request."""
    return {
        "user_message": user_message,
        "session_id": session_id,
        "intent_result": None,
        "data_response": None,
        "twin_result": None,
        "final_response": "",
        "error": None,
        "step_count": 0,
        "needs_data": False,
    }
