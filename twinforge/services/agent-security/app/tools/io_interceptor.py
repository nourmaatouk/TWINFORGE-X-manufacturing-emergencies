"""
I/O Interceptor - Captures and stores all inter-agent communication.

Provides two modes of operation:
1. Proxy mode: Other services route traffic through the security agent's
   /proxy/{agent_id} endpoint. The security agent forwards requests, captures
   both input and output, and runs security analysis on everything.
2. Redis tap mode: Agents publish their I/O to Redis channels
   (twinforge:io:{agent_id}). The security agent subscribes and records.

All captured I/O is stored in a circular buffer per agent for querying
via the /agent-io endpoint.
"""

import httpx
import logging
import json
import time
from datetime import datetime, timezone
from collections import defaultdict
from typing import Any

logger = logging.getLogger(__name__)

# Maps agent_id -> URL, shared with agent_tester
_agent_urls: dict[str, str] = {}


def init_agent_urls(agent_urls_config: str):
    """Parse AGENT_URLS config string into dict."""
    global _agent_urls
    if not agent_urls_config:
        return
    for pair in agent_urls_config.split(","):
        pair = pair.strip()
        if "=" in pair:
            agent_id, url = pair.split("=", 1)
            _agent_urls[agent_id.strip()] = url.strip()


class IOInterceptor:
    """Captures and stores inter-agent I/O for security monitoring."""

    def __init__(self, max_per_agent: int = 500):
        # agent_id -> list of I/O records
        self._buffer: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._max_per_agent = max_per_agent
        self._total_captured = 0

    def record(
        self,
        agent_id: str,
        direction: str,
        data: dict[str, Any],
        source: str = "proxy",
    ):
        """
        Record an I/O event.

        Args:
            agent_id: The agent whose I/O is being captured.
            direction: "input" or "output".
            data: The request or response payload.
            source: How this was captured ("proxy", "redis_tap", "direct").
        """
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "direction": direction,
            "source": source,
            "data_summary": self._summarize(data),
            "data": data,
            "size_bytes": len(json.dumps(data, default=str)),
        }

        self._buffer[agent_id].append(entry)
        if len(self._buffer[agent_id]) > self._max_per_agent:
            self._buffer[agent_id] = self._buffer[agent_id][-self._max_per_agent:]
        self._total_captured += 1

    def record_from_redis(self, channel: str, message_data: dict[str, Any]):
        """Record I/O captured from a Redis pub/sub channel."""
        # Expected channel format: twinforge:io:{agent_id}
        parts = channel.split(":")
        if len(parts) >= 3:
            agent_id = parts[2]
        else:
            agent_id = "unknown"

        direction = message_data.get("direction", "unknown")
        self.record(agent_id, direction, message_data, source="redis_tap")

    def get_io(
        self,
        agent_id: str | None = None,
        direction: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Query captured I/O.

        Args:
            agent_id: Filter by agent. None = all agents.
            direction: Filter by "input" or "output". None = both.
            limit: Max records to return.
        """
        if agent_id:
            records = list(self._buffer.get(agent_id, []))
        else:
            records = []
            for entries in self._buffer.values():
                records.extend(entries)
            records.sort(key=lambda r: r["timestamp"])

        if direction:
            records = [r for r in records if r["direction"] == direction]

        return records[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Return summary statistics of captured I/O."""
        per_agent = {}
        for agent_id, entries in self._buffer.items():
            inputs = sum(1 for e in entries if e["direction"] == "input")
            outputs = sum(1 for e in entries if e["direction"] == "output")
            per_agent[agent_id] = {
                "total": len(entries),
                "inputs": inputs,
                "outputs": outputs,
                "buffer_usage": f"{len(entries)}/{self._max_per_agent}",
            }

        return {
            "total_captured": self._total_captured,
            "agents_monitored": list(self._buffer.keys()),
            "per_agent": per_agent,
        }

    def _summarize(self, data: dict[str, Any]) -> str:
        """Create a short human-readable summary of the data."""
        s = json.dumps(data, default=str)
        if len(s) > 200:
            return s[:200] + "..."
        return s


# Singleton
io_interceptor = IOInterceptor()


async def proxy_request(
    agent_id: str,
    request_body: dict[str, Any],
) -> dict[str, Any]:
    """
    Forward a request to a target agent, capturing both input and output.

    Args:
        agent_id: Target agent ID.
        request_body: The full request payload to forward.

    Returns:
        dict with the agent's response and capture metadata.
    """
    if agent_id not in _agent_urls:
        return {
            "error": f"Unknown agent '{agent_id}'. Available: {list(_agent_urls.keys())}",
            "status": "error",
        }

    base_url = _agent_urls[agent_id]

    # Record input
    io_interceptor.record(agent_id, "input", request_body, source="proxy")

    start_time = time.time()
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{base_url}/process", json=request_body)
            elapsed = round(time.time() - start_time, 3)

            response_data = response.json() if response.status_code < 500 else {
                "error": response.text[:500]
            }

            # Record output
            io_interceptor.record(agent_id, "output", response_data, source="proxy")

            return {
                "status": "proxied",
                "agent_id": agent_id,
                "http_status": response.status_code,
                "elapsed_s": elapsed,
                "response": response_data,
            }

    except httpx.TimeoutException:
        error_resp = {"error": f"Agent {agent_id} timed out (30s)"}
        io_interceptor.record(agent_id, "output", error_resp, source="proxy")
        return {"status": "timeout", "agent_id": agent_id, "error": error_resp["error"]}

    except Exception as e:
        error_resp = {"error": str(e)[:300]}
        io_interceptor.record(agent_id, "output", error_resp, source="proxy")
        return {"status": "error", "agent_id": agent_id, "error": error_resp["error"]}
