"""
TWINFORGE Agent 3 — FastAPI Entrypoint
Data/IoT Executor microservice: telemetry ingestion, streaming, anomaly detection, and simulation.
Runs on port 8003.
"""

import asyncio
import logging
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from app.agent import DataIoTAgent
from app.config import settings
from app.models.schemas import (
    AlertsResponse,
    AnomalyAlert,
    HealthResponse,
    HistoryResponse,
    IngestResponse,
    MachineTelemetry,
    MachineStateResponse,
    SimulationConfig,
    SimulationResponse,
    TelemetryIngest,
)

# ─── Logging ─────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","message":"%(message)s"}',
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# ─── Agent (singleton) ──────────────────────────────────────────────────────

agent = DataIoTAgent()

# ─── Lifespan ────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan: initialize on startup, cleanup on shutdown."""
    logger.info("Starting Agent 3 — Data/IoT Executor on port %d", settings.SERVICE_PORT)
    await agent.initialize()
    yield
    logger.info("Shutting down Agent 3")
    await agent.shutdown()


# ─── App ─────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="TWINFORGE Agent 3 — Data/IoT Executor",
    description="Industrial IoT telemetry ingestion, real-time streaming, anomaly detection, and simulation.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Prometheus Metrics (optional) ──────────────────────────────────────────

try:
    from prometheus_client import make_asgi_app
    metrics_app = make_asgi_app()
    app.mount("/metrics", metrics_app)
except ImportError:
    logger.info("prometheus_client not installed, /metrics disabled")


# ═══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ═══════════════════════════════════════════════════════════════════════════

# ─── Health ──────────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check():
    """Health check endpoint."""
    info = agent.get_health_info()
    return HealthResponse(**info)


# ─── Telemetry Ingestion ────────────────────────────────────────────────────

@app.post("/ingest", response_model=IngestResponse, tags=["Telemetry"])
async def ingest_telemetry(payload: TelemetryIngest):
    """
    Ingest telemetry data (batch or single record).
    Each record is validated -> anomaly-checked -> stored -> broadcast.
    """
    accepted, rejected, alerts = await agent.ingest_telemetry(payload.data)
    return IngestResponse(accepted=accepted, rejected=rejected, alerts=alerts)


# ─── Simulation ─────────────────────────────────────────────────────────────

@app.post("/simulate", response_model=SimulationResponse, status_code=202, tags=["Simulation"])
async def start_simulation(config: SimulationConfig):
    """Start a background simulation that generates realistic telemetry."""
    active = agent.get_active_simulation_count()
    if active >= settings.MAX_CONCURRENT_SIMULATIONS:
        raise HTTPException(
            status_code=429,
            detail=f"Max concurrent simulations ({settings.MAX_CONCURRENT_SIMULATIONS}) reached",
        )

    from app.simulation.simulation_engine import SimulationEngine

    engine = SimulationEngine(config=config, on_telemetry=agent.ingest_telemetry)
    task = asyncio.create_task(engine.run())
    agent.register_simulation(engine.simulation_id, task)

    logger.info("Simulation %s started with %d machines for %.1f hours",
                engine.simulation_id, config.number_of_machines, config.simulation_duration_hours)

    return SimulationResponse(
        simulation_id=engine.simulation_id,
        status="started",
        message=f"Simulation started with {config.number_of_machines} machines for {config.simulation_duration_hours}h",
        config=config,
    )


# ─── Machine State ──────────────────────────────────────────────────────────

@app.get("/machines/latest", response_model=MachineStateResponse, tags=["Machines"])
async def get_latest_machines():
    """Get the latest state of all known machines."""
    states = agent.get_all_machine_states()
    return MachineStateResponse(machines=states, total=len(states))


@app.get("/machines/{machine_id}/history", response_model=HistoryResponse, tags=["Machines"])
async def get_machine_history(
    machine_id: str,
    start: Optional[str] = Query(None, description="Start time (ISO8601)"),
    end: Optional[str] = Query(None, description="End time (ISO8601)"),
    limit: int = Query(100, ge=1, le=10000, description="Max records to return"),
):
    """Get historical telemetry for a specific machine."""
    records = await agent.get_machine_history(machine_id, start, end, limit)
    return HistoryResponse(machine_id=machine_id, records=records, total=len(records))


# ─── Alerts ──────────────────────────────────────────────────────────────────

@app.get("/alerts", response_model=AlertsResponse, tags=["Alerts"])
async def get_alerts(limit: int = Query(100, ge=1, le=1000)):
    """Get recent anomaly alerts."""
    alerts = agent.get_alerts(limit=limit)
    return AlertsResponse(alerts=alerts, total=len(alerts))


# ─── Inter-Agent Processing ─────────────────────────────────────────────────

@app.post("/process", tags=["Agent"])
async def process_request(request: dict):
    """Standard agent processing endpoint (called by other agents)."""
    payload = request.get("payload", request)
    result = await agent.process(payload)
    return {
        "session_id": request.get("session_id", ""),
        "agent_id": "agent-data-iot",
        "status": result.get("status", "success"),
        "payload": result,
        "timestamp": datetime.now().isoformat(),
    }


# ─── WebSocket ───────────────────────────────────────────────────────────────

@app.websocket("/ws/telemetry")
async def websocket_telemetry(websocket: WebSocket):
    """Real-time telemetry WebSocket endpoint."""
    await agent.ws_manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        agent.ws_manager.disconnect(websocket)
    except Exception as e:
        logger.error("WebSocket error: %s", e)
        agent.ws_manager.disconnect(websocket)


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.SERVICE_PORT,
        reload=False,
        log_level=settings.LOG_LEVEL.lower(),
    )
