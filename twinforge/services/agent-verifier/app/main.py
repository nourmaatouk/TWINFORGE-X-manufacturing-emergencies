"""
Agent Verifier - Main FastAPI application entry point.
Agent 4: Critic - Validates KPIs, verifies sources, detects anomalies.
"""

from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from prometheus_client import make_asgi_app
import logging

from app.agent import VerifierAgent
from app.models.schemas import AgentRequest, AgentResponse
from app.config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.AGENT_NAME}...")
    app.state.agent = VerifierAgent()
    await app.state.agent.initialize()
    yield
    logger.info(f"Shutting down {settings.AGENT_NAME}...")
    await app.state.agent.shutdown()


app = FastAPI(
    title=settings.AGENT_NAME,
    version="1.0.0",
    lifespan=lifespan
)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)


@app.get("/health")
async def health_check():
    return {"status": "healthy", "agent": settings.AGENT_NAME}


@app.post("/process", response_model=AgentResponse)
async def process_message(request: AgentRequest):
    try:
        result = await app.state.agent.process(request)
        return result
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=settings.PORT)
