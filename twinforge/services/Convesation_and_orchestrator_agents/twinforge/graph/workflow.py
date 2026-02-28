"""
TWINFORGE — LangGraph FSM Orchestration Workflow.
Connects the 3 agents via a StateGraph with conditional routing.

Flow:
  START → conversation_intake → (needs_data?) → fetch_data → orchestrate_twin → format_response → END
                                      └─ no ──────────────────────┘
"""
from __future__ import annotations
import logging
from typing import Any, Optional, Tuple

from twinforge.core.schemas import (
    UserInput, IntentResult, Intent, DataRequest, DataResponse, TwinResult
)
from twinforge.core.logging_config import log_agent_action
from twinforge.agents.conversation.agent import ConversationAgent
from twinforge.agents.data_iot.agent import DataIoTAgent
from twinforge.agents.orchestrator.proxy import RemoteOrchestratorProxy
from twinforge.graph.state import create_initial_state

logger = logging.getLogger("twinforge.graph")

# ═══════════════════════════════════════════════════════════
# GLOBAL AGENT INSTANCES (shared across requests)
# ═══════════════════════════════════════════════════════════

_conversation_agent: Optional[ConversationAgent] = None
_orchestrator_proxy: Optional[RemoteOrchestratorProxy] = None
_data_agent: Optional[DataIoTAgent] = None


def get_agents() -> tuple[ConversationAgent, RemoteOrchestratorProxy, DataIoTAgent]:
    global _conversation_agent, _orchestrator_proxy, _data_agent
    if _conversation_agent is None:
        _conversation_agent = ConversationAgent()
    if _orchestrator_proxy is None:
        _orchestrator_proxy = RemoteOrchestratorProxy()
    if _data_agent is None:
        _data_agent = DataIoTAgent()
    return _conversation_agent, _orchestrator_proxy, _data_agent


# ═══════════════════════════════════════════════════════════
# NODE FUNCTIONS
# ═══════════════════════════════════════════════════════════

# Simple conversational fallback when LLM is unavailable
_GREETINGS = {"hello", "hi", "hey", "salut", "bonjour", "bonsoir", "ciao"}
_GREETING_RESPONSE = (
    "👋 Hello! I'm **TwinForge**, your Manufacturing Digital Twin assistant.\n\n"
    "Here's what I can do:\n"
    "- 🏭 **Create** a digital twin: *\"Create a CNC machine twin on floor 1, line A, 45 kWh\"*\n"
    "- 📊 **Show KPIs**: *\"Show me the KPI dashboard\"*\n"
    "- 📋 **List twins**: *\"List all twins\"*\n"
    "- ⚠️ **Alerts**: *\"Are there any alerts?\"*\n"
    "- 📈 **Predictions**: *\"Predict temperature for CNC-001\"*\n\n"
    "Just describe what you need!"
)

def conversation_intake(state: dict) -> dict:
    """Agent 1: Parse user message → structured intent."""
    conv, _, _ = get_agents()
    state["step_count"] = state.get("step_count", 0) + 1

    user_input = UserInput(
        user_message=state["user_message"],
        session_id=state.get("session_id", "default"),
    )

    try:
        result = conv.process_user_input(user_input)
    except Exception as e:
        logger.error(f"Conversation intake error: {e}")
        state["final_response"] = "⚠️ I encountered an internal error processing your message. Please try again."
        state["intent_result"] = None
        return state

    if isinstance(result, str):
        # LLM chat response or error message — return directly
        state["final_response"] = result
        state["intent_result"] = None
        return state

    state["intent_result"] = result

    # Handle GENERAL_QUERY locally (don't send to Agent 2)
    if result.intent == Intent.GENERAL_QUERY:
        msg_lower = state["user_message"].strip().lower().rstrip("!?.")
        if msg_lower in _GREETINGS:
            state["final_response"] = _GREETING_RESPONSE
        else:
            state["final_response"] = (
                f"💬 I understand you're asking about: *\"{state['user_message']}\"*\n\n"
                "I'm specialized in manufacturing digital twins. Try:\n"
                "- *\"Create a CNC machine twin on floor 1, line A\"*\n"
                "- *\"Show me the KPIs\"*\n"
                "- *\"List all twins\"*\n"
                "- *\"Are there any alerts?\"*"
            )
        state["intent_result"] = None  # Don't route further
        return state

    # Decide if we need sensor data
    intents_needing_data = {Intent.CREATE_TWIN, Intent.GET_KPI, Intent.QUERY_TWIN}
    state["needs_data"] = result.intent in intents_needing_data

    return state


def fetch_data(state: dict) -> dict:
    """Agent 3: Fetch sensor data from IoT layer."""
    _, _, data_agt = get_agents()
    state["step_count"] = state.get("step_count", 0) + 1

    intent_result: IntentResult = state.get("intent_result")
    if not intent_result:
        return state

    asset_id = intent_result.entities.get("twin_id", "")
    if not asset_id:
        asset_type = intent_result.entities.get("type", "CNC")
        asset_id = f"{asset_type}-SIM"

    request = DataRequest(asset_id=asset_id)
    try:
        data_resp = data_agt.process_data_request(request)
        state["data_response"] = data_resp
    except Exception as e:
        logger.error(f"Data fetch error: {e}")
        state["data_response"] = None

    return state


def orchestrate_twin(state: dict) -> dict:
    """Agent 2: Process intent (Remote Call)."""
    _, orch_proxy, _ = get_agents()
    state["step_count"] = state.get("step_count", 0) + 1

    intent_result: Optional[IntentResult] = state.get("intent_result")
    if not intent_result:
        state["final_response"] = state.get("error", "⚠️ Could not understand request.")
        return state

    data_response: Optional[DataResponse] = state.get("data_response")
    
    try:
        # Call Agent 2 (Orchestrator) proxy which handles HTTP to Port 8002
        twin_result = orch_proxy.process_intent(intent_result, data_response)
        state["twin_result"] = twin_result
    except Exception as e:
        logger.error(f"Failed to call Agent 2 microservice: {e}")
        state["error"] = f"Agent 2 (Orchestrator) offline: {e}"
        state["final_response"] = "⚠️ Engineering system (Agent 2) is currently unavailable."

    return state


def format_response(state: dict) -> dict:
    """Agent 1: Format final response for user."""
    conv, _, _ = get_agents()
    state["step_count"] = state.get("step_count", 0) + 1

    # If response was already set (GENERAL_QUERY, LLM chat, error), keep it
    if state.get("final_response"):
        return state

    twin_result: Optional[TwinResult] = state.get("twin_result")
    if twin_result:
        state["final_response"] = conv.format_response(twin_result)
    else:
        state["final_response"] = "⚠️ No result generated."

    return state


# ═══════════════════════════════════════════════════════════
# ROUTING LOGIC
# ═══════════════════════════════════════════════════════════

def should_fetch_data(state: dict) -> str:
    """Conditional edge: decide whether to fetch sensor data."""
    # Already handled (GENERAL_QUERY, error, or LLM response)
    if state.get("final_response") and not state.get("intent_result"):
        return "format_response"
    if state.get("error"):
        return "format_response"
    if state.get("needs_data", False):
        return "fetch_data"
    return "orchestrate_twin"


# ═══════════════════════════════════════════════════════════
# BUILD GRAPH (LangGraph-style, simplified for portability)
# ═══════════════════════════════════════════════════════════

class TwinForgeGraph:
    """
    LangGraph-style StateGraph FSM.
    Implements the workflow: intake → (fetch_data?) → orchestrate → format.
    """

    def __init__(self):
        self._nodes = {
            "conversation_intake": conversation_intake,
            "fetch_data": fetch_data,
            "orchestrate_twin": orchestrate_twin,
            "format_response": format_response,
        }

    def invoke(self, user_message: str, session_id: str = "default") -> dict:
        """Run the full pipeline synchronously."""
        state = create_initial_state(user_message, session_id)

        # Step 1: Conversation intake
        state = self._nodes["conversation_intake"](state)

        # Step 2: Conditional routing
        next_node = should_fetch_data(state)

        if next_node == "fetch_data":
            state = self._nodes["fetch_data"](state)
            state = self._nodes["orchestrate_twin"](state)
        elif next_node == "orchestrate_twin":
            state = self._nodes["orchestrate_twin"](state)
        # else: goes straight to format

        # Step 3: Format response
        state = self._nodes["format_response"](state)

        log_agent_action(
            "graph", "pipeline_complete", "workflow",
            user_message, state.get("final_response", ""),
            reasoning_trace=f"Steps: {state.get('step_count', 0)}"
        )

        return state


# Singleton
_graph: Optional[TwinForgeGraph] = None

def get_graph() -> TwinForgeGraph:
    global _graph
    if _graph is None:
        _graph = TwinForgeGraph()
    return _graph
