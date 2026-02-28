"""
TWINFORGE Agent 3 — Redis Broadcaster
Publishes telemetry data to Redis pub/sub for cross-agent consumption.
Includes HMAC-SHA256 signing for secure inter-agent communication.
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

# Shared HMAC key from environment (same across all agents)
_SIGNING_KEY = os.environ.get("MESSAGE_SIGNING_KEY", "").encode("utf-8")


def _sign_payload(payload: dict[str, Any]) -> str:
    """Create HMAC-SHA256 signature for a message dict."""
    if not _SIGNING_KEY:
        return ""
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hmac.new(_SIGNING_KEY, canonical.encode("utf-8"), hashlib.sha256).hexdigest()


class RedisBroadcaster:
    """
    Redis pub/sub broadcaster for telemetry data.

    Publishes every ingested telemetry point to a configurable channel
    so other agents and services (dashboards, Agent 4 verifier) can consume
    the data in real time.  Each message is HMAC-SHA256 signed.
    """

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        channel: str = "telemetry:live",
    ) -> None:
        self.redis_url = redis_url
        self.channel = channel
        self._redis: Optional[aioredis.Redis] = None

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Redis broadcaster connected to %s", self.redis_url)
        except Exception as e:
            logger.error("Redis broadcaster connection failed: %s", e)
            self._redis = None
            raise

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._redis:
            await self._redis.close()
            self._redis = None
        logger.info("Redis broadcaster disconnected")

    async def publish(self, data: dict[str, Any], channel: Optional[str] = None) -> bool:
        """Publish a signed message to a Redis channel."""
        if not self._redis:
            return False

        target_channel = channel or self.channel
        try:
            envelope = {
                "sender_agent": "agent_3",
                "message_type": "telemetry",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": data,
            }
            envelope["signature"] = _sign_payload(envelope)

            message = json.dumps(envelope, default=str)
            await self._redis.publish(target_channel, message)

            # Also publish to the shared agent bus so agent-security can monitor
            await self._redis.publish("twinforge:agent-bus", message)
            return True
        except Exception as e:
            logger.error("Redis publish failed: %s", e)
            return False

    async def publish_alert(self, alert_data: dict[str, Any]) -> bool:
        """Publish a signed anomaly alert to the alerts channel."""
        if not self._redis:
            return False
        try:
            envelope = {
                "sender_agent": "agent_3",
                "message_type": "anomaly_alert",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "payload": alert_data,
            }
            envelope["signature"] = _sign_payload(envelope)

            message = json.dumps(envelope, default=str)
            await self._redis.publish("telemetry:alerts", message)
            await self._redis.publish("twinforge:agent-bus", message)
            return True
        except Exception as e:
            logger.error("Redis alert publish failed: %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        return self._redis is not None
