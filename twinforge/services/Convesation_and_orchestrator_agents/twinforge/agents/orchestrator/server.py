"""
TWINFORGE — Agent 2 (Orchestrator) Standalone Server.
Exposes orchestration tools (AAS, KPI, TFT) via REST API on Port 8002.
"""
from __future__ import annotations
import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List

from twinforge.agents.orchestrator.agent import TwinOrchestratorAgent
from twinforge.core.schemas import IntentResult, DataResponse, TwinResult, TwinEntry, Intent

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("agent2.orchestrator")

app = FastAPI(title="TwinForge Orchestrator (Agent 2)")

# Singleton instance of the agent
orchestrator = TwinOrchestratorAgent()

class IntentRequest(BaseModel):
    intent_result: IntentResult
    data_response: Optional[DataResponse] = None

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "orchestrator"}

@app.get("/")
async def root():
    """Agent 2 root — service info."""
    return {
        "service": "TwinForge Orchestrator (Agent 2)",
        "status": "running",
        "port": 8002,
        "endpoints": [
            "/health", "/process_intent", "/twins",
            "/smia/agents", "/tft/predict/{twin_id}",
            "/dashboard/overview", "/dashboard/predictions",
            "/docs",
        ],
    }

@app.post("/process_intent", response_model=TwinResult)
async def process_intent(req: IntentRequest):
    """Core entry point for Agent 1 to trigger Agent 2."""
    try:
        logger.info(f"Processing intent: {req.intent_result.intent}")
        result = orchestrator.process_intent(req.intent_result, req.data_response)
        return result
    except Exception as e:
        logger.error(f"Error in Agent 2: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/twins", response_model=List[TwinEntry])
async def list_twins():
    """Returns all twins from orchestrator memory."""
    twins = orchestrator.get_all_twins()
    return list(twins.values())

@app.get("/twins/{twin_id}", response_model=TwinEntry)
async def get_twin(twin_id: str):
    """Returns details for a specific twin."""
    twin = orchestrator.get_twin(twin_id)
    if not twin:
        raise HTTPException(status_code=404, detail="Twin not found")
    return twin

# ── Dashboard API Endpoints (Proxied from Port 8001) ──

@app.get("/dashboard/overview")
async def dashboard_overview():
    """Aggregate data for the main dashboard view."""
    return {
        "aggregate_kpis": orchestrator.get_aggregate_kpis(),
        "alerts": orchestrator.get_all_alerts(),
        "floors": {fl: len(ids) for fl, ids in orchestrator.get_twins_by_floor().items()},
        "lines": {ln: len(ids) for ln, ids in orchestrator.get_twins_by_line().items()}
    }

@app.get("/dashboard/predictions")
async def dashboard_predictions(sensor: str = "temperature"):
    """TFT multi-horizon predictions."""
    return {
        "predictions": orchestrator.get_all_predictions(target_sensor=sensor)
    }

@app.get("/dashboard/predictions/{twin_id}")
async def twin_predictions(twin_id: str, sensor: str = "temperature"):
    """Specific twin predictions."""
    return {
        "prediction": orchestrator.tft_predict(twin_id, sensor),
        "aas_prediction_submodel": orchestrator.get_tft_prediction_submodel(twin_id)
    }

# ── SMIA Agent Management Endpoints ──

@app.get("/smia/agents")
async def list_smia_agents():
    """List all spawned SMIA agents and their status."""
    return {
        "agent_count": orchestrator._smia_spawner.agent_count,
        "mode": orchestrator._smia_spawner.mode,
        "agents": orchestrator._smia_spawner.get_all_agents(),
    }

@app.get("/smia/agents/{twin_id}")
async def get_smia_agent(twin_id: str):
    """Get status of a specific SMIA agent."""
    status = orchestrator._smia_spawner.get_agent_status(twin_id)
    if not status:
        raise HTTPException(status_code=404, detail=f"No SMIA agent for twin {twin_id}")
    return status

# ── Direct TFT Prediction Endpoint ──

@app.get("/tft/predict/{twin_id}")
async def tft_predict_direct(twin_id: str, sensor: str = "temperature"):
    """Direct TFT prediction for a twin (no dashboard proxy)."""
    return orchestrator.tft_predict(twin_id, sensor)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8002)

