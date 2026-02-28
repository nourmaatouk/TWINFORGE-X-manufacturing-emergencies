"""LangGraph Orchestrator - Main FastAPI entry point.

Central coordinator for all TwinForge agents. Exposes:
- POST /process  - Standard AgentRequest → AgentResponse workflow
- POST /workflow - Same workflow but returns full graph state (debug)
- GET  /health   - Health check
- GET  /graph    - Returns the graph topology for visualization
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from contextlib import asynccontextmanager
from datetime import datetime, timezone
import logging
import uuid

from app.config import settings
from app.graph import workflow, ORCHESTRATOR_INTENTS, DATA_INTENTS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.AGENT_NAME} v2.0.0 (LangGraph orchestrator)")
    logger.info(f"Agent URLs: 1={settings.AGENT_1_URL}, 2={settings.AGENT_2_URL}, "
                f"3={settings.AGENT_3_URL}, 4={settings.AGENT_4_URL}, 5={settings.AGENT_5_URL}")
    yield
    logger.info(f"Shutting down {settings.AGENT_NAME}")


app = FastAPI(
    title=settings.AGENT_NAME,
    version="2.0.0",
    lifespan=lifespan,
)
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "agent": settings.AGENT_NAME,
        "version": "2.0.0",
        "graph_nodes": ["security", "conversation", "orchestrator", "data", "verifier", "respond"],
    }


@app.post("/process")
async def process_request(request: dict):
    """Standard agent processing endpoint.

    Accepts an AgentRequest-shaped payload, runs the full LangGraph workflow
    (security → conversation → route → agent → verify → respond), and
    returns an AgentResponse-shaped result.
    """
    try:
        # Build initial state from the incoming request
        payload = request.get("payload", {})
        user_message = (
            payload.get("message", "")
            or payload.get("query", "")
            or payload.get("text", "")
            or ""
        )

        initial_state = {
            "session_id": request.get("session_id", str(uuid.uuid4())),
            "tenant_id": request.get("tenant_id", "default"),
            "user_message": user_message,
            "payload": payload,
            "errors": [],
        }

        # Run the LangGraph workflow
        result = await workflow.ainvoke(initial_state)

        # Extract final response
        final = result.get("final_response", {})

        return {
            "session_id": initial_state["session_id"],
            "agent_id": settings.AGENT_ID,
            "status": final.get("status", "success"),
            "payload": final,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/workflow")
async def workflow_debug(request: dict):
    """Debug endpoint that returns the full graph state after execution.

    Same as /process but returns every intermediate result from each node,
    useful for debugging and understanding the workflow flow.
    """
    try:
        payload = request.get("payload", {})
        user_message = (
            payload.get("message", "")
            or payload.get("query", "")
            or payload.get("text", "")
            or ""
        )

        initial_state = {
            "session_id": request.get("session_id", str(uuid.uuid4())),
            "tenant_id": request.get("tenant_id", "default"),
            "user_message": user_message,
            "payload": payload,
            "errors": [],
        }

        result = await workflow.ainvoke(initial_state)

        return {
            "session_id": initial_state["session_id"],
            "agent_id": settings.AGENT_ID,
            "full_state": result,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        logger.error(f"Workflow debug failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/graph")
async def graph_info():
    """Return the graph topology for visualization and debugging."""
    return {
        "nodes": ["security", "conversation", "orchestrator", "data", "verifier", "respond"],
        "edges": {
            "security": {"cleared": "conversation", "blocked": "respond"},
            "conversation": {
                "orchestrator_intents": sorted(ORCHESTRATOR_INTENTS),
                "data_intents": sorted(DATA_INTENTS),
                "default": "respond",
            },
            "orchestrator": "verifier",
            "data": "verifier",
            "verifier": "respond",
            "respond": "END",
        },
        "agents": {
            "security": {"agent": "Agent 5", "url": settings.AGENT_5_URL},
            "conversation": {"agent": "Agent 1", "url": settings.AGENT_1_URL},
            "orchestrator": {"agent": "Agent 2", "url": settings.AGENT_2_URL},
            "data": {"agent": "Agent 3", "url": settings.AGENT_3_URL},
            "verifier": {"agent": "Agent 4", "url": settings.AGENT_4_URL},
        },
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
