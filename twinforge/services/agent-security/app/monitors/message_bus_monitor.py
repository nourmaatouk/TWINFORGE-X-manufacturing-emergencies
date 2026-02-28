"""
Message Bus Monitor - Monitors Redis pub/sub traffic for security anomalies.

Analyzes inter-agent messages flowing through the Redis message bus:
1. Message volume per channel - detects flooding
2. Invalid/missing signatures - detects spoofing attempts
3. Unexpected sender-channel pairs - detects routing violations
4. Message schema violations - detects malformed payloads
"""

import logging
from typing import Any
from collections import defaultdict
import time

logger = logging.getLogger(__name__)

# Maximum messages per channel per minute
MAX_MESSAGES_PER_CHANNEL_PER_MINUTE = 200

# Expected channel -> authorized senders mapping
CHANNEL_SENDERS = {
    "agent_1_in": {"langgraph", "agent_2"},
    "agent_1_out": {"agent_1"},
    "orchestrator_in": {"agent_1", "agent_3", "agent_4", "agent_5", "langgraph"},
    "orchestrator_out": {"agent_2"},
    "agent_3_in": {"agent_2", "langgraph"},
    "agent_3_out": {"agent_3"},
    "agent_4_in": {"agent_2", "langgraph"},
    "agent_4_out": {"agent_4"},
    "security_events": {"agent_1", "agent_2", "agent_3", "agent_4", "agent_5"},
}

# Required fields in every message
REQUIRED_MESSAGE_FIELDS = {"sender_agent", "message_type", "payload", "timestamp"}


class MessageBusMonitor:
    """
    Monitors inter-agent message bus traffic for security anomalies.
    """

    def __init__(self):
        # channel -> list of timestamps for rate tracking
        self._channel_rates: dict[str, list[float]] = defaultdict(list)
        # Counters for stats
        self._total_messages = 0
        self._invalid_messages = 0

    def monitor(self, message: dict[str, Any]) -> dict[str, Any]:
        """
        Analyze a message from the bus for security issues.

        Args:
            message: The full message dict from Redis pub/sub. Expected fields:
                - channel: the Redis channel
                - sender_agent: claimed sender
                - message_type: type of message
                - payload: the message body
                - timestamp: when the message was sent
                - signature: HMAC signature (may be absent)

        Returns:
            dict with issues found (if any), channel stats, and message metadata.
        """
        self._total_messages += 1
        issues = []
        channel = message.get("channel", "unknown")
        sender = message.get("sender_agent", "")

        # --- Check 1: Missing required fields ---
        missing = REQUIRED_MESSAGE_FIELDS - set(message.keys())
        if missing:
            self._invalid_messages += 1
            issues.append({
                "type": "missing_fields",
                "severity": "MEDIUM",
                "detail": f"Message on '{channel}' missing required fields: {missing}",
            })

        # --- Check 2: Channel flooding ---
        now = time.time()
        self._channel_rates[channel].append(now)
        cutoff = now - 60
        self._channel_rates[channel] = [
            ts for ts in self._channel_rates[channel] if ts > cutoff
        ]
        rate = len(self._channel_rates[channel])
        if rate > MAX_MESSAGES_PER_CHANNEL_PER_MINUTE:
            issues.append({
                "type": "channel_flooding",
                "severity": "HIGH",
                "detail": (
                    f"Channel '{channel}' receiving {rate} msgs/min "
                    f"(limit: {MAX_MESSAGES_PER_CHANNEL_PER_MINUTE})"
                ),
            })

        # --- Check 3: Unauthorized sender for channel ---
        if channel in CHANNEL_SENDERS and sender:
            if sender not in CHANNEL_SENDERS[channel]:
                issues.append({
                    "type": "unauthorized_sender",
                    "severity": "HIGH",
                    "detail": (
                        f"Agent '{sender}' not authorized to send on channel '{channel}'. "
                        f"Allowed: {CHANNEL_SENDERS[channel]}"
                    ),
                })

        # --- Check 4: Missing signature ---
        if not message.get("signature"):
            issues.append({
                "type": "missing_signature",
                "severity": "MEDIUM",
                "detail": f"Message from '{sender}' on '{channel}' has no HMAC signature",
            })

        # --- Check 5: Security event flag from message bus ---
        if message.get("_security_event"):
            issues.append({
                "type": "invalid_signature",
                "severity": "CRITICAL",
                "detail": (
                    f"Message bus flagged invalid signature from "
                    f"'{message.get('sender_agent', 'unknown')}'"
                ),
            })

        return {
            "channel": channel,
            "sender": sender,
            "issues": issues,
            "has_issues": len(issues) > 0,
            "channel_rate": rate,
            "total_monitored": self._total_messages,
            "total_invalid": self._invalid_messages,
        }
