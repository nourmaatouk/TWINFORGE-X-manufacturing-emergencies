"""
Agent Security - Main FastAPI application entry point.
Agent 5: Security Guardian - Real-time threat detection and monitoring.

Features:
- /analyze and /process endpoints for threat detection
- Rate limiting middleware (per-IP)
- Quarantine-aware middleware (adds warning header, never blocks)
- Lockdown middleware (IP whitelist + API key, internal-only access)
- Redis pub/sub passive listener for message bus scanning
- WebSocket /ws/threats for real-time threat streaming
- /dashboard for aggregated security stats
- /incidents for incident replay and audit
- /quarantine/* for quarantine management
- /patterns for learned attack patterns
- /pentest/* for active security testing of other agents
- /proxy/* for proxying + capturing agent I/O
- /agent-io for querying captured inter-agent communications
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Request, Query
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app
import asyncio
import json
import logging
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from app.agent import SecurityAgent
from app.models.schemas import SecurityEventRequest, ThreatResponse
from app.config import settings
from app.tools import agent_tester
from app.tools.io_interceptor import io_interceptor, proxy_request, init_agent_urls as init_io_urls
from app.tools.lockdown import init_lockdown, lockdown_middleware

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Rate Limiting Config ---
RATE_LIMIT_REQUESTS = 100  # max requests per window per IP
RATE_LIMIT_WINDOW = 60     # seconds
_rate_counters: dict[str, list[float]] = defaultdict(list)

# --- WebSocket clients for real-time threat feed ---
_ws_clients: set[WebSocket] = set()


async def broadcast_threat(threat_data: dict):
    """Broadcast a threat event to all connected WebSocket clients."""
    if not _ws_clients:
        return
    message = json.dumps(threat_data, default=str)
    disconnected = set()
    for ws in _ws_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.add(ws)
    _ws_clients -= disconnected


async def redis_listener(agent: SecurityAgent):
    """Background task: subscribe to Redis message bus and I/O channels."""
    try:
        import hashlib
        import hmac as hmac_mod
        import redis.asyncio as aioredis

        signing_key = settings.MESSAGE_SIGNING_KEY.encode("utf-8") if settings.MESSAGE_SIGNING_KEY else b""

        def _verify_signature(data: dict) -> bool:
            """Verify HMAC-SHA256 signature on an incoming message."""
            if not signing_key:
                return True  # No key configured, skip verification
            sig = data.pop("signature", "")
            if not sig:
                return False
            canonical = json.dumps(data, sort_keys=True, default=str)
            expected = hmac_mod.new(signing_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
            data["signature"] = sig  # restore for downstream
            return hmac_mod.compare_digest(expected, sig)

        r = aioredis.from_url(settings.REDIS_URL)
        pubsub = r.pubsub()
        # Subscribe to message bus channels AND I/O tap channels
        await pubsub.psubscribe("twinforge:messages", "twinforge:agent-bus", "twinforge:io:*", "telemetry:*")
        logger.info(
            "Redis pub/sub listener active on twinforge:messages, "
            "twinforge:agent-bus, twinforge:io:*, telemetry:*"
        )

        async for message in pubsub.listen():
            if message["type"] not in ("message", "pmessage"):
                continue
            try:
                channel = message.get("channel", b"").decode() if isinstance(message.get("channel"), bytes) else message.get("channel", "")
                data = json.loads(message["data"])

                # I/O tap channel — record to interceptor
                if channel.startswith("twinforge:io:"):
                    io_interceptor.record_from_redis(channel, data)
                    continue

                # Verify HMAC signature
                if not _verify_signature(data):
                    logger.warning("Rejected unsigned/mis-signed message on %s from %s",
                                   channel, data.get("sender_agent", "unknown"))
                    # Still report it as a security event
                    bad_sig_request = SecurityEventRequest(
                        event_type="SIGNATURE_FAILURE",
                        source_agent=data.get("sender_agent", data.get("source_agent", "unknown")),
                        payload={"channel": channel, "reason": "invalid_or_missing_hmac"},
                    )
                    result = await agent.analyze(bad_sig_request)
                    if result.threat_detected:
                        await broadcast_threat(result.model_dump())
                    continue

                # Security monitoring channel — scan through pipeline
                request = SecurityEventRequest(
                    event_type=data.get("event_type", "MESSAGE"),
                    source_agent=data.get("source_agent", data.get("sender_agent", "")),
                    payload=data,
                )
                result = await agent.analyze(request)
                if result.threat_detected:
                    await broadcast_threat(result.model_dump())
            except Exception as e:
                logger.debug(f"Redis listener skipped message: {e}")
    except ImportError:
        logger.warning("redis package not available, pub/sub listener disabled")
    except Exception as e:
        logger.warning(f"Redis pub/sub unavailable ({e}), passive monitoring disabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.AGENT_NAME} v3.0...")

    # Initialize tools
    agent_tester.init_agent_urls(settings.AGENT_URLS)
    init_io_urls(settings.AGENT_URLS)
    init_lockdown(settings.LOCKDOWN_ENABLED, settings.INTERNAL_API_KEY, settings.ALLOWED_IPS)

    # Initialize agent
    app.state.agent = SecurityAgent()
    await app.state.agent.initialize()

    # Start Redis listener in background
    redis_task = asyncio.create_task(redis_listener(app.state.agent))

    yield

    redis_task.cancel()
    try:
        await redis_task
    except asyncio.CancelledError:
        pass
    logger.info(f"Shutting down {settings.AGENT_NAME}...")
    await app.state.agent.shutdown()


app = FastAPI(
    title=settings.AGENT_NAME,
    version="3.0.0",
    lifespan=lifespan,
)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


# =====================================================================
# MIDDLEWARE (order matters: last registered = first executed)
# =====================================================================

@app.middleware("http")
async def rate_limit_middleware(request: Request, call_next):
    """Reject requests that exceed the per-IP rate limit."""
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    cutoff = now - RATE_LIMIT_WINDOW
    _rate_counters[client_ip] = [t for t in _rate_counters[client_ip] if t > cutoff]

    if len(_rate_counters[client_ip]) >= RATE_LIMIT_REQUESTS:
        return JSONResponse(
            status_code=429,
            content={"detail": "Rate limit exceeded. Try again later."},
        )

    _rate_counters[client_ip].append(now)
    return await call_next(request)


@app.middleware("http")
async def quarantine_middleware(request: Request, call_next):
    """Tag requests from quarantined agents with a warning header.
    Messages still flow through — quarantine means elevated monitoring, not blocking."""
    response = await call_next(request)
    if request.url.path in ("/analyze", "/process") and request.method == "POST":
        try:
            body = await request.body()
            data = json.loads(body)
            source_agent = data.get("source_agent", "")
            if source_agent and hasattr(request.app.state, "agent"):
                if request.app.state.agent.is_quarantined(source_agent):
                    response.headers["X-Security-Quarantine"] = (
                        f"Agent '{source_agent}' is under elevated monitoring"
                    )
        except Exception:
            pass
    return response


# Lockdown: must be registered last so it runs FIRST
app.middleware("http")(lockdown_middleware)


# =====================================================================
# CORE ENDPOINTS
# =====================================================================

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "agent": settings.AGENT_NAME,
        "version": "3.0.0",
        "lockdown": settings.LOCKDOWN_ENABLED,
    }


@app.post("/analyze", response_model=ThreatResponse)
async def analyze_event(request: SecurityEventRequest):
    """Analyze a security event for threats."""
    try:
        result = await app.state.agent.analyze(request)
        if result.threat_detected:
            asyncio.create_task(broadcast_threat(result.model_dump()))
        return result
    except Exception as e:
        logger.error(f"Error analyzing security event: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/process", response_model=ThreatResponse)
async def process_message(request: SecurityEventRequest):
    """Alias for /analyze endpoint."""
    try:
        result = await app.state.agent.analyze(request)
        if result.threat_detected:
            asyncio.create_task(broadcast_threat(result.model_dump()))
        return result
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================================
# DASHBOARD & AUDIT
# =====================================================================

@app.get("/dashboard")
async def dashboard():
    """Aggregated security dashboard with stats from all monitors and detectors."""
    agent: SecurityAgent = app.state.agent
    incident_stats = agent.incident_logger.get_stats()
    tool_stats = agent.tool_usage_monitor.get_all_stats()
    anomaly_stats = agent.anomaly_monitor.get_stats()
    io_stats = io_interceptor.get_stats()

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "agent": settings.AGENT_NAME,
        "version": "3.0.0",
        "lockdown_enabled": settings.LOCKDOWN_ENABLED,
        "quarantined_agents": agent.get_quarantined(),
        "learned_patterns_count": len(agent.get_learned_patterns()),
        "incidents": incident_stats,
        "tool_usage": tool_stats,
        "anomaly_monitor": anomaly_stats,
        "io_interceptor": io_stats,
        "websocket_clients": len(_ws_clients),
    }


@app.get("/incidents")
async def get_incidents(
    severity: Optional[str] = Query(None, description="Filter by severity: CRITICAL, HIGH, MEDIUM, LOW"),
    limit: int = Query(50, ge=1, le=500, description="Max incidents to return"),
):
    """Query recent security incidents for audit and replay."""
    agent: SecurityAgent = app.state.agent
    if severity:
        incidents = agent.incident_logger.get_by_severity(severity.upper())
        incidents = incidents[-limit:]
    else:
        incidents = agent.incident_logger.get_recent(limit)

    return {
        "count": len(incidents),
        "incidents": incidents,
    }


# =====================================================================
# QUARANTINE MANAGEMENT
# =====================================================================

@app.get("/quarantine")
async def list_quarantined():
    """List all currently quarantined agents."""
    return {
        "quarantined_agents": app.state.agent.get_quarantined(),
        "count": len(app.state.agent.get_quarantined()),
    }


@app.delete("/quarantine/{agent_id}")
async def release_agent(agent_id: str):
    """Manually release an agent from quarantine."""
    released = app.state.agent.release_quarantine(agent_id)
    if released:
        return {"message": f"Agent '{agent_id}' released from quarantine"}
    raise HTTPException(status_code=404, detail=f"Agent '{agent_id}' is not quarantined")


# =====================================================================
# LEARNED PATTERNS
# =====================================================================

@app.get("/patterns")
async def list_learned_patterns():
    """Return attack patterns learned by the o3 rethinking loop."""
    patterns = app.state.agent.get_learned_patterns()
    return {
        "count": len(patterns),
        "patterns": patterns,
    }


# =====================================================================
# ACTIVE PENETRATION TESTING
# =====================================================================

@app.get("/pentest/agents")
async def list_testable_agents():
    """List all agents available for penetration testing."""
    return {
        "agents": agent_tester.get_available_agents(),
        "test_suites": list(agent_tester.TEST_SUITES.keys()),
    }


@app.post("/pentest/{agent_id}")
async def pentest_agent(
    agent_id: str,
    suites: Optional[str] = Query(None, description="Comma-separated test suites: prompt_injection,data_exfiltration,privilege_escalation,spoofing,payload_manipulation"),
):
    """Run penetration tests against a specific agent."""
    suite_list = suites.split(",") if suites else None
    result = await agent_tester.run_tests(agent_id, suite_list)
    return result


@app.post("/pentest")
async def pentest_all(
    suites: Optional[str] = Query(None, description="Comma-separated test suites to run"),
):
    """Run penetration tests against ALL registered agents."""
    suite_list = suites.split(",") if suites else None
    result = await agent_tester.run_all_agents(suite_list)
    return result


# =====================================================================
# I/O PROXY & INTERCEPTOR
# =====================================================================

@app.post("/proxy/{agent_id}")
async def proxy_to_agent(agent_id: str, request: Request):
    """
    Proxy a request to another agent while capturing both input and output.
    The security agent acts as a man-in-the-middle for full I/O visibility.
    """
    try:
        body = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    result = await proxy_request(agent_id, body)

    # Also run security analysis on the proxied input
    try:
        sec_request = SecurityEventRequest(
            event_type="PROXY",
            source_agent=body.get("source_agent", "unknown"),
            payload=body.get("payload", body),
        )
        sec_result = await app.state.agent.analyze(sec_request)
        if sec_result.threat_detected:
            result["security_alert"] = sec_result.model_dump()
            asyncio.create_task(broadcast_threat(sec_result.model_dump()))
    except Exception as e:
        logger.debug(f"Security analysis on proxied request failed: {e}")

    return result


@app.get("/agent-io")
async def get_all_agent_io(
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    direction: Optional[str] = Query(None, description="Filter: input or output"),
):
    """Query captured I/O across all agents."""
    records = io_interceptor.get_io(direction=direction, limit=limit)
    return {
        "count": len(records),
        "records": records,
    }


@app.get("/agent-io/stats")
async def get_io_stats():
    """Return I/O interception statistics."""
    return io_interceptor.get_stats()


@app.get("/agent-io/{agent_id}")
async def get_agent_io(
    agent_id: str,
    limit: int = Query(50, ge=1, le=500, description="Max records to return"),
    direction: Optional[str] = Query(None, description="Filter: input or output"),
):
    """Query captured I/O for a specific agent."""
    records = io_interceptor.get_io(agent_id=agent_id, direction=direction, limit=limit)
    return {
        "agent_id": agent_id,
        "count": len(records),
        "records": records,
    }


# =====================================================================
# WEBSOCKET: REAL-TIME THREAT FEED
# =====================================================================

@app.websocket("/ws/threats")
async def websocket_threat_feed(websocket: WebSocket):
    """Real-time threat feed via WebSocket. Clients receive threat events as JSON."""
    await websocket.accept()
    _ws_clients.add(websocket)
    logger.info(f"WebSocket client connected ({len(_ws_clients)} total)")
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
        logger.info(f"WebSocket client disconnected ({len(_ws_clients)} remaining)")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
