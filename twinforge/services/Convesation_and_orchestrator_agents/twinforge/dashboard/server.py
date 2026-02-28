"""
TWINFORGE — FastAPI Dashboard Server.
REST API + WebSocket for the web dashboard.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
from urllib.parse import quote_plus
from pathlib import Path
from datetime import datetime

import httpx
import requests
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, List, Dict

from twinforge.core.config import get_settings
from twinforge.core.logging_config import setup_logging, get_action_store
from twinforge.graph.workflow import get_graph, get_agents
from twinforge.dashboard.dashboard_api import router as dashboard_router
from twinforge.core.schemas import DataRequest
from twinforge.agents.risk_engine import compute_risk, inject_scenario, clear_scenario

logger = logging.getLogger("twinforge.dashboard")

AUTH_BACKEND_URL = os.getenv("AUTH_BACKEND_URL", "http://localhost:5000").rstrip("/")
AUTH_LOGIN_URL = os.getenv("AUTH_LOGIN_URL", "http://localhost:5174")
AUTH_ALLOWED_ORIGINS = [
    AUTH_LOGIN_URL,
    "http://localhost:5173",
    "http://localhost:5174",
]


async def _is_authenticated_cookie(raw_cookie: str) -> bool:
    """Async cookie validator — uses httpx so it never blocks the event loop."""
    if not raw_cookie:
        return False
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(
                f"{AUTH_BACKEND_URL}/auth/me",
                headers={"Cookie": raw_cookie},
            )
            return response.status_code == 200
    except Exception:
        return False


def _build_login_redirect(next_path: str = "/") -> str:
    safe_next = quote_plus(next_path or "/")
    return f"{AUTH_LOGIN_URL}?next={safe_next}"

# ═══════════════════════════════════════════════════════════
# APP SETUP
# ═══════════════════════════════════════════════════════════

app = FastAPI(
    title="TWINFORGE",
    description="Conversational Manufacturing Digital Twin Platform",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=AUTH_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def auth_gate(request: Request, call_next):
    path = request.url.path
    # Health check, risk API and static assets are always public
    if path in ("/health",) or path.startswith("/static/") or path.startswith("/api/risk"):
        return await call_next(request)

    raw_cookie = request.headers.get("cookie", "")
    if await _is_authenticated_cookie(raw_cookie):
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse({"error": "Authentication required"}, status_code=401)

    return RedirectResponse(_build_login_redirect(path), status_code=307)

# Serve static files
static_dir = Path(__file__).parent / "static"
static_dir.mkdir(parents=True, exist_ok=True)

# Mount dashboard API router (dynamic data endpoints)
app.include_router(dashboard_router)

app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


# ═══════════════════════════════════════════════════════════
# REQUEST MODELS
# ═══════════════════════════════════════════════════════════

class ChatRequest(BaseModel):
    message: str = Field(..., max_length=4096)
    session_id: str = Field(default="default", max_length=128)


class ChatResponse(BaseModel):
    response: str
    twin_id: Optional[str] = None
    intent: Optional[str] = None
    confidence: Optional[float] = None
    kpis: Optional[dict] = None
    alerts: Optional[list] = None
    reasoning_trace: Optional[list] = None
    timestamp: str = ""


# ═══════════════════════════════════════════════════════════
# ROUTES
# ═══════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def root():
    index_path = static_dir / "index.html"
    if index_path.exists():
        return HTMLResponse(content=index_path.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>TWINFORGE</h1><p>Dashboard loading...</p>")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "twinforge-dashboard"}


@app.post("/api/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    """Process a chat message through the full agent pipeline."""
    graph = get_graph()
    state = graph.invoke(req.message, req.session_id)

    twin_result = state.get("twin_result")
    intent_result = state.get("intent_result")

    resp = ChatResponse(
        response=state.get("final_response", "No response"),
        timestamp=datetime.utcnow().isoformat(),
    )

    if twin_result:
        resp.twin_id = twin_result.twin_id
        resp.kpis = twin_result.kpis.model_dump() if twin_result.kpis else None
        resp.alerts = [a.model_dump(mode="json") for a in twin_result.alerts] if twin_result.alerts else []
        resp.reasoning_trace = twin_result.reasoning_trace

    if intent_result:
        resp.intent = intent_result.intent.value
        resp.confidence = intent_result.confidence

    return resp


@app.get("/api/twins")
def list_twins():
    """Proxy list_twins call to Agent 2 (Port 8002)."""
    import requests
    try:
        resp = requests.get("http://localhost:8002/twins", timeout=5)
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except Exception as e:
        logger.error(f"Failed to fetch twins from Agent 2: {e}")
        return JSONResponse([], status_code=500)


@app.get("/api/twins/{twin_id}")
def get_twin(twin_id: str):
    """Proxy get_twin call to Agent 2 (Port 8002)."""
    import requests
    try:
        resp = requests.get(f"http://localhost:8002/twins/{twin_id}", timeout=5)
        resp.raise_for_status()
        return JSONResponse(resp.json())
    except Exception as e:
        logger.error(f"Failed to fetch twin {twin_id} from Agent 2: {e}")
        return JSONResponse({"error": "Twin not found or Agent 2 offline"}, status_code=404)


@app.get("/api/logs")
def get_logs(n: int = 50):
    """Get recent agent action logs."""
    store = get_action_store()
    return JSONResponse(store.get_recent(n))


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    """WebSocket endpoint for streaming chat."""
    if not await _is_authenticated_cookie(ws.headers.get("cookie", "")):
        await ws.close(code=1008)
        return

    await ws.accept()
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            message = msg.get("message", "")
            session_id = msg.get("session_id", "default")

            graph = get_graph()
            # Run blocking graph.invoke in a thread to avoid event loop deadlock
            loop = asyncio.get_event_loop()
            state = await loop.run_in_executor(None, graph.invoke, message, session_id)

            twin_result = state.get("twin_result")
            intent_result = state.get("intent_result")

            resp = {
                "type": "response",
                "response": state.get("final_response", ""),
                "timestamp": datetime.utcnow().isoformat(),
            }

            if twin_result:
                resp["twin_id"] = twin_result.twin_id
                resp["kpis"] = twin_result.kpis.model_dump() if twin_result.kpis else None
                resp["alerts"] = [a.model_dump(mode="json") for a in twin_result.alerts] if twin_result.alerts else []
                resp["reasoning_trace"] = twin_result.reasoning_trace
                resp["components"] = twin_result.components

            if intent_result:
                resp["intent"] = intent_result.intent.value
                resp["confidence"] = intent_result.confidence

            await ws.send_text(json.dumps(resp, default=str))

    except WebSocketDisconnect:
        logger.info("WebSocket chat disconnected")
    except Exception as e:
        logger.error(f"WebSocket chat error: {e}")


@app.websocket("/ws/sensors")
async def ws_sensors(ws: WebSocket):
    """Stream live sensor data for all twins every 2 seconds."""
    if not await _is_authenticated_cookie(ws.headers.get("cookie", "")):

        await ws.close(code=1008)
        return

    await ws.accept()

    def _fetch_sensor_payload():
        """Blocking I/O — runs in a thread."""
        import requests as req
        try:
            twins_list = req.get("http://localhost:8002/twins", timeout=2).json()
        except Exception:
            twins_list = []
        _, _, data_agent = get_agents()
        payload = []
        for twin in twins_list:
            tid = twin["twin_id"]
            dreq = DataRequest(asset_id=tid, data_request="live_sensors")
            resp = data_agent.process_data_request(dreq)
            payload.append({
                "twin_id": tid,
                "sensor_data": resp.sensor_data,
                "anomaly_count": len(resp.anomalies),
            })
        return payload

    try:
        while True:
            # Run blocking I/O in thread to avoid deadlocking the event loop
            loop = asyncio.get_event_loop()
            payload = await loop.run_in_executor(None, _fetch_sensor_payload)
            await ws.send_text(json.dumps({"type": "sensor_update", "twins": payload}, default=str))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("WebSocket sensors disconnected")
    except Exception as e:
        logger.error(f"WebSocket sensors error: {e}")


# ═══════════════════════════════════════════════════════════
# TWINFORGE-X — RISK INTELLIGENCE ENDPOINTS
# ═══════════════════════════════════════════════════════════

@app.get("/api/risk/now")
async def get_risk_now():
    """Synchronous risk snapshot — for REST polling."""
    snap = compute_risk()
    return JSONResponse(_risk_to_dict(snap))


class ScenarioRequest(BaseModel):
    scenario: str   # "overheat" | "intrusion" | "cascade" | "clear"
    machine_id: Optional[str] = None


@app.post("/api/risk/scenario")
async def set_scenario(req: ScenarioRequest):
    """Inject or clear a live incident scenario for demo/testing."""
    if req.scenario == "clear":
        clear_scenario()
        return JSONResponse({"ok": True, "scenario": None})
    inject_scenario(req.scenario, req.machine_id)
    return JSONResponse({"ok": True, "scenario": req.scenario, "machine_id": req.machine_id})


@app.websocket("/ws/risk")
async def ws_risk(ws: WebSocket):
    """Stream live RiskSnapshot every 2 seconds to the Risk Intelligence tab."""
    await ws.accept()
    try:
        while True:
            snap = compute_risk()
            await ws.send_text(json.dumps(_risk_to_dict(snap), default=str))
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        logger.info("WebSocket risk disconnected")
    except Exception as e:
        logger.error(f"WebSocket risk error: {e}")


def _risk_to_dict(snap) -> dict:
    return {
        "timestamp":      snap.timestamp,
        "global_score":   snap.global_score,
        "global_level":   snap.global_level,
        "emergency_mode": snap.emergency_mode,
        "recommendation": snap.recommendation,
        "scenario":       snap.scenario,
        "agent_messages": snap.agent_messages,
        "ai_info":        snap.ai_info,
        "machines": [
            {
                "machine_id":        m.machine_id,
                "zone":              m.zone,
                "floor":             m.floor,
                "machine_type":      m.machine_type,
                "temp":              m.temp,
                "vibration":         m.vibration,
                "energy":            m.energy,
                "workers_present":   m.workers_present,
                "fire_risk":         m.fire_risk,
                "intrusion_risk":    m.intrusion_risk,
                "failure_risk":      m.failure_risk,
                "worker_risk":       m.worker_risk,
                "ml_anomaly_score":  m.ml_anomaly_score,
                "z_score":           m.z_score,
                "ai_method":         m.ai_method,
                "risk_score":        m.risk_score,
                "risk_level":        m.risk_level,
                "alerts":            m.alerts,
            }
            for m in snap.machines
        ],
        "predictions": snap.predictions,
    }

