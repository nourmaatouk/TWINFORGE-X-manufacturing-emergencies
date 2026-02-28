"""
Tool Usage Monitor - Tracks agent tool invocations and detects suspicious patterns.

Monitors:
1. Tool call frequency per agent (rate limiting)
2. Unusual tool sequences (e.g. agent calling tools outside normal workflow)
3. Failed tool calls that might indicate probing
4. Tool call volume trends for anomaly detection
"""

import logging
from typing import Any
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

# Max tool calls per agent per minute before flagging
MAX_TOOL_CALLS_PER_MINUTE = 100

# Max consecutive failed tool calls before flagging
MAX_CONSECUTIVE_FAILURES = 5


class ToolUsageMonitor:
    """
    Tracks and monitors tool invocations across all agents.
    Maintains in-memory history for rate and pattern analysis.
    """

    def __init__(self):
        # agent_id -> list of (timestamp, event_type, tool_name, success)
        self._call_history: dict[str, list[dict]] = defaultdict(list)
        # agent_id -> count of consecutive failures
        self._consecutive_failures: dict[str, int] = defaultdict(int)

    def record(self, agent_id: str, event_type: str, payload: dict[str, Any]):
        """
        Record a tool invocation event.

        Args:
            agent_id: The agent making the tool call.
            event_type: The type of event (e.g. "TOOL_CALL", "MESSAGE").
            payload: The event payload (may contain tool_name, success, error).
        """
        now = time.time()
        tool_name = payload.get("tool_name", "unknown")
        success = payload.get("success", True)

        entry = {
            "timestamp": now,
            "event_type": event_type,
            "tool_name": tool_name,
            "success": success,
        }
        self._call_history[agent_id].append(entry)

        # Prune entries older than 5 minutes
        cutoff = now - 300
        self._call_history[agent_id] = [
            e for e in self._call_history[agent_id] if e["timestamp"] > cutoff
        ]

        # Track consecutive failures
        if not success:
            self._consecutive_failures[agent_id] += 1
        else:
            self._consecutive_failures[agent_id] = 0

    def get_stats(self, agent_id: str) -> dict[str, Any]:
        """
        Get usage statistics for an agent.

        Returns:
            dict with calls_last_minute, calls_last_5_minutes,
            unique_tools, consecutive_failures, and tool_breakdown.
        """
        now = time.time()
        history = self._call_history.get(agent_id, [])

        last_minute = [e for e in history if e["timestamp"] > now - 60]
        last_5_min = [e for e in history if e["timestamp"] > now - 300]

        tool_counts: dict[str, int] = defaultdict(int)
        for entry in last_5_min:
            tool_counts[entry["tool_name"]] += 1

        return {
            "agent_id": agent_id,
            "calls_last_minute": len(last_minute),
            "calls_last_5_minutes": len(last_5_min),
            "unique_tools": list(tool_counts.keys()),
            "consecutive_failures": self._consecutive_failures.get(agent_id, 0),
            "tool_breakdown": dict(tool_counts),
        }

    def check_anomalies(self, agent_id: str) -> dict[str, Any]:
        """
        Check for anomalous tool usage patterns for an agent.

        Returns:
            dict with anomaly_detected, issues list, and stats.
        """
        stats = self.get_stats(agent_id)
        issues = []

        # Check 1: Rate limit exceeded
        if stats["calls_last_minute"] > MAX_TOOL_CALLS_PER_MINUTE:
            issues.append({
                "type": "rate_limit_exceeded",
                "severity": "HIGH",
                "detail": (
                    f"Agent '{agent_id}' made {stats['calls_last_minute']} tool calls "
                    f"in the last minute (limit: {MAX_TOOL_CALLS_PER_MINUTE})"
                ),
            })

        # Check 2: Consecutive failures (possible probing)
        if stats["consecutive_failures"] >= MAX_CONSECUTIVE_FAILURES:
            issues.append({
                "type": "consecutive_failures",
                "severity": "MEDIUM",
                "detail": (
                    f"Agent '{agent_id}' has {stats['consecutive_failures']} consecutive "
                    f"failed tool calls - possible capability probing"
                ),
            })

        return {
            "anomaly_detected": len(issues) > 0,
            "issues": issues,
            "stats": stats,
        }

    def get_all_stats(self) -> dict[str, Any]:
        """Return aggregated stats across all tracked agents (for dashboard)."""
        now = time.time()
        total_calls = 0
        agents = list(self._call_history.keys())
        tool_counts: dict[str, int] = defaultdict(int)

        for agent_id in agents:
            history = self._call_history[agent_id]
            last_5_min = [e for e in history if e["timestamp"] > now - 300]
            total_calls += len(last_5_min)
            for entry in last_5_min:
                tool_counts[entry["tool_name"]] += 1

        return {
            "agents_tracked": agents,
            "total_calls_last_5_min": total_calls,
            "tool_breakdown": dict(tool_counts),
        }
