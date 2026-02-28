"""
TWINFORGE Agent 3 — API Integration Tests
Tests for FastAPI endpoints using httpx test client.
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.asyncio
async def test_health_endpoint():
    """Test GET /health returns healthy status."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["agent"] == "agent-data-iot"


@pytest.mark.asyncio
async def test_ingest_valid_data():
    """Test POST /ingest with valid telemetry data."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "data": [
                {
                    "machine_id": "M1",
                    "energy_kwh": 12.4,
                    "water_liters": 3.1,
                    "vibration": 2.5,
                    "temperature": 75.2,
                }
            ]
        }
        resp = await client.post("/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] == 1
        assert data["rejected"] == 0


@pytest.mark.asyncio
async def test_ingest_empty_batch():
    """Test POST /ingest with empty batch is rejected."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/ingest", json={"data": []})
        assert resp.status_code == 422  # Validation error


@pytest.mark.asyncio
async def test_machines_latest():
    """Test GET /machines/latest returns machine state list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/machines/latest")
        assert resp.status_code == 200
        data = resp.json()
        assert "machines" in data
        assert "total" in data


@pytest.mark.asyncio
async def test_alerts_endpoint():
    """Test GET /alerts returns alerts list."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/alerts")
        assert resp.status_code == 200
        data = resp.json()
        assert "alerts" in data
        assert "total" in data


@pytest.mark.asyncio
async def test_simulate_endpoint():
    """Test POST /simulate starts simulation."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        config = {
            "number_of_machines": 2,
            "simulation_duration_hours": 0.001,
            "sampling_interval_seconds": 1,
        }
        resp = await client.post("/simulate", json=config)
        assert resp.status_code == 202
        data = resp.json()
        assert "simulation_id" in data
        assert data["status"] == "started"


@pytest.mark.asyncio
async def test_machine_history():
    """Test GET /machines/{id}/history."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/machines/M1/history")
        assert resp.status_code == 200
        data = resp.json()
        assert data["machine_id"] == "M1"
        assert "records" in data


@pytest.mark.asyncio
async def test_process_endpoint():
    """Test POST /process for inter-agent communication."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "session_id": "test-session",
            "payload": {"intent": "query_sensor_data"},
        }
        resp = await client.post("/process", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "agent-data-iot"
