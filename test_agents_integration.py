"""
TWINFORGE Integration Tests — Agent Connectivity & Secure Communication
=========================================================================
Tests all agents are reachable, communicate via Redis pub/sub with HMAC
signatures, and respond correctly to inter-agent requests.

Run with:
    python test_agents_integration.py               # from host (needs all ports mapped)
    docker compose exec agent-security python -m pytest /tests/  # from inside Docker

Assumes docker-compose.microservices.yml is running.
"""

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx
import pytest

# ═══════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════

# When running from inside docker (internal network), use service names.
# When running from host, use localhost with mapped ports.
INSIDE_DOCKER = os.environ.get("INSIDE_DOCKER", "false").lower() == "true"

if INSIDE_DOCKER:
    AGENT_URLS = {
        "auth-backend":        "http://auth-backend:5000",
        "twinforge-dashboard": "http://twinforge-dashboard:8001",
        "agent-data-iot":      "http://agent-data-iot:8003",
        "agent-verifier":      "http://agent-verifier:8004",
        "agent-security":      "http://agent-security:8005",
        "mcp-mock-server":     "http://mcp-mock-server:9001",
    }
    REDIS_URL = os.environ.get("REDIS_URL", "redis://redis:6379")
else:
    # Default: tests run from inside Docker on the internal network
    # If running from host, override ports via env vars
    BASE = os.environ.get("BASE_URL", "http://localhost")
    AGENT_URLS = {
        "auth-backend":        f"{BASE}:5000",
        "twinforge-dashboard": f"{BASE}:8001",
        "agent-data-iot":      f"{BASE}:8003",
        "agent-verifier":      f"{BASE}:8004",
        "agent-security":      f"{BASE}:8005",
        "mcp-mock-server":     f"{BASE}:9001",
    }
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379")

MESSAGE_SIGNING_KEY = os.environ.get("MESSAGE_SIGNING_KEY", "twinforge_hmac_default_key_change_in_prod")
TIMEOUT = 10.0


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def sign_message(payload: dict) -> str:
    """Create HMAC-SHA256 signature for a message dict."""
    key = MESSAGE_SIGNING_KEY.encode("utf-8")
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


def verify_signature(payload: dict, signature: str) -> bool:
    """Verify HMAC-SHA256 signature."""
    expected = sign_message(payload)
    return hmac.compare_digest(expected, signature)


# ═══════════════════════════════════════════════════════════════════════════
# TEST 1: Health Checks — All Agents Reachable
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_all_agents_healthy():
    """Every agent should return 200 on /health."""
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        for name, url in AGENT_URLS.items():
            try:
                resp = await client.get(f"{url}/health")
                assert resp.status_code == 200, f"{name} /health returned {resp.status_code}"
                body = resp.json()
                assert body.get("status") in ("healthy", "ok", "success"), \
                    f"{name} /health status: {body}"
                print(f"  [PASS] {name} — healthy")
            except httpx.ConnectError:
                pytest.fail(f"{name} at {url} is not reachable")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 2: Agent-Data-IoT — Telemetry Ingestion
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_agent_data_iot_ingest():
    """agent-data-iot should accept telemetry via POST /ingest."""
    url = AGENT_URLS["agent-data-iot"]
    payload = {
        "data": [
            {
                "machine_id": "TEST-001",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "machine_type": "CNC",
                "temperature": 55.0,
                "vibration": 0.42,
                "energy_kwh": 12.5,
                "water_liters": 1.2,
                "status": "running",
                "failure_flag": False,
                "failure_risk_score": 0.1,
            }
        ]
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{url}/ingest", json=payload)
        assert resp.status_code == 200, f"Ingest returned {resp.status_code}: {resp.text}"
        body = resp.json()
        assert body["accepted"] >= 1, f"No records accepted: {body}"
        print(f"  [PASS] agent-data-iot accepted {body['accepted']} records")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 3: Agent-Verifier — Process Request
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_agent_verifier_process():
    """agent-verifier should accept POST /process requests."""
    url = AGENT_URLS["agent-verifier"]
    payload = {
        "session_id": "test-session-001",
        "intent": "verify_kpi",
        "payload": {
            "kpi_name": "energy_efficiency",
            "value": 0.85,
            "threshold": 0.8,
        },
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{url}/process", json=payload)
        assert resp.status_code in (200, 422), f"Process returned {resp.status_code}: {resp.text}"
        print(f"  [PASS] agent-verifier /process responded ({resp.status_code})")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 4: Agent-Security — Analyze Request
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_agent_security_analyze():
    """agent-security should accept POST /analyze for threat detection."""
    url = AGENT_URLS["agent-security"]
    payload = {
        "event_type": "MESSAGE",
        "source_agent": "agent_3",
        "payload": {
            "message_type": "telemetry",
            "data": {"temperature": 55.0},
        },
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{url}/analyze", json=payload)
        # May return 200 or 403 (lockdown) depending on IP
        assert resp.status_code in (200, 403), f"Analyze returned {resp.status_code}: {resp.text}"
        print(f"  [PASS] agent-security /analyze responded ({resp.status_code})")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 5: MCP Mock Server — Tools List
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_mcp_mock_server_tools():
    """mcp-mock-server should list available tools."""
    url = AGENT_URLS["mcp-mock-server"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{url}/tools")
        assert resp.status_code == 200
        tools = resp.json()
        assert isinstance(tools, list) and len(tools) >= 3
        tool_names = [t["name"] for t in tools]
        assert "cnc_read_sensors" in tool_names
        print(f"  [PASS] mcp-mock-server returned {len(tools)} tools")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 6: HMAC Signing — Verify signature generation/verification
# ═══════════════════════════════════════════════════════════════════════════

def test_hmac_signing():
    """HMAC-SHA256 sign/verify should work with the shared key."""
    payload = {
        "sender_agent": "agent_3",
        "message_type": "telemetry",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"temperature": 55.0, "machine_id": "TEST-001"},
    }

    signature = sign_message(payload)
    assert len(signature) == 64, f"Bad signature length: {len(signature)}"
    assert verify_signature(payload, signature), "Signature verification failed"

    # Tampered payload should fail
    tampered = {**payload, "payload": {"temperature": 999.0}}
    assert not verify_signature(tampered, signature), "Tampered payload should not verify"

    print("  [PASS] HMAC-SHA256 sign/verify works correctly")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 7: Redis Pub/Sub — Agent-to-Agent Message Flow
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_redis_pubsub_signed_message():
    """Publish a signed message to Redis and verify it can be consumed."""
    try:
        import redis.asyncio as aioredis
    except ImportError:
        pytest.skip("redis package not available")

    r = aioredis.from_url(REDIS_URL, decode_responses=True)
    try:
        await r.ping()
    except Exception:
        pytest.skip("Redis not reachable")

    channel = "twinforge:agent-bus"
    pubsub = r.pubsub()
    await pubsub.subscribe(channel)

    # Build signed message
    msg = {
        "sender_agent": "test_runner",
        "message_type": "test",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": {"test": True},
    }
    msg["signature"] = sign_message(msg)

    # Publish
    await r.publish(channel, json.dumps(msg))

    # Consume
    received = None
    deadline = time.time() + 3.0
    while time.time() < deadline:
        raw = await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.5)
        if raw and raw["type"] == "message":
            received = json.loads(raw["data"])
            break

    await pubsub.unsubscribe(channel)
    await r.close()

    assert received is not None, "No message received on Redis"
    sig = received.pop("signature", "")
    assert verify_signature(received, sig), "Received message has invalid signature"
    print("  [PASS] Redis pub/sub with HMAC-signed message works")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 8: Inter-Agent Request — Data-IoT → Security (via HTTP)
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_inter_agent_http():
    """agent-data-iot should expose /process for inter-agent requests."""
    url = AGENT_URLS["agent-data-iot"]
    payload = {
        "session_id": "test-inter-001",
        "intent": "query_sensor_data",
        "payload": {},
    }

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.post(f"{url}/process", json=payload)
        assert resp.status_code == 200, f"Inter-agent /process returned {resp.status_code}"
        body = resp.json()
        assert body.get("agent_id") == "agent-data-iot"
        print(f"  [PASS] Inter-agent HTTP request to agent-data-iot succeeded")


# ═══════════════════════════════════════════════════════════════════════════
# TEST 9: Dashboard Reachability
# ═══════════════════════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_dashboard_health():
    """twinforge-dashboard should be reachable."""
    url = AGENT_URLS["twinforge-dashboard"]
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        resp = await client.get(f"{url}/health")
        assert resp.status_code == 200
        print(f"  [PASS] twinforge-dashboard is healthy")


# ═══════════════════════════════════════════════════════════════════════════
# MAIN — Run all tests with summary
# ═══════════════════════════════════════════════════════════════════════════

async def run_all_tests():
    """Run all tests and print a summary."""
    tests = [
        ("Health checks (all agents)", test_all_agents_healthy),
        ("Telemetry ingestion", test_agent_data_iot_ingest),
        ("Verifier process", test_agent_verifier_process),
        ("Security analyze", test_agent_security_analyze),
        ("MCP mock tools", test_mcp_mock_server_tools),
        ("HMAC signing", lambda: asyncio.coroutine(lambda: test_hmac_signing())()),
        ("Redis pub/sub signed", test_redis_pubsub_signed_message),
        ("Inter-agent HTTP", test_inter_agent_http),
        ("Dashboard health", test_dashboard_health),
    ]

    passed = 0
    failed = 0
    errors = []

    print("\n" + "=" * 60)
    print("  TWINFORGE Integration Test Suite")
    print("=" * 60 + "\n")

    for name, test_fn in tests:
        try:
            if asyncio.iscoroutinefunction(test_fn):
                await test_fn()
            else:
                test_fn()
            passed += 1
        except Exception as e:
            failed += 1
            errors.append((name, str(e)))
            print(f"  [FAIL] {name}: {e}")

    print("\n" + "=" * 60)
    print(f"  Results: {passed} passed, {failed} failed out of {len(tests)}")
    print("=" * 60)

    if errors:
        print("\nFailed tests:")
        for name, err in errors:
            print(f"  - {name}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_all_tests())
    sys.exit(exit_code)
