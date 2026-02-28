"""
TWINFORGE Shared Message Bus
Redis pub/sub client with HMAC-SHA256 message signing for inter-agent communication.
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator, Optional

import redis.asyncio as aioredis

from shared.security.message_signer import MessageSigner

logger = logging.getLogger(__name__)


class MessageBus:
    """Redis pub/sub message bus with HMAC-SHA256 signing."""

    def __init__(self, redis_url: str = "redis://localhost:6379", signing_key: str = "default-key") -> None:
        self.redis_url = redis_url
        self.signing_key = signing_key
        self._redis: Optional[aioredis.Redis] = None
        self._pubsub: Optional[aioredis.client.PubSub] = None
        self._signer = MessageSigner(signing_key)

    async def connect(self) -> None:
        """Connect to Redis."""
        try:
            self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
            await self._redis.ping()
            logger.info("Connected to Redis message bus at %s", self.redis_url)
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            self._redis = None

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        if self._pubsub:
            await self._pubsub.unsubscribe()
            await self._pubsub.close()
        if self._redis:
            await self._redis.close()
        logger.info("Disconnected from Redis message bus")

    async def publish(
        self,
        channel: str,
        sender_agent: str,
        recipient_agent: str,
        message_type: str,
        payload: dict[str, Any],
        session_id: str = "",
        tenant_id: str = "default",
    ) -> bool:
        """Publish a signed message to a Redis channel."""
        if not self._redis:
            logger.warning("Redis not connected, message not published")
            return False

        timestamp = datetime.now(timezone.utc).isoformat()
        message_id = f"{timestamp}_{sender_agent}_{uuid.uuid4().hex[:8]}"

        message = {
            "message_id": message_id,
            "sender_agent": sender_agent,
            "recipient_agent": recipient_agent,
            "message_type": message_type,
            "payload": payload,
            "session_id": session_id or str(uuid.uuid4()),
            "tenant_id": tenant_id,
            "timestamp": timestamp,
        }

        message["signature"] = self._signer.sign(message)

        try:
            await self._redis.publish(channel, json.dumps(message))
            logger.debug("Published message %s to channel %s", message_id, channel)
            return True
        except Exception as e:
            logger.error("Failed to publish message: %s", e)
            return False

    async def subscribe(self, channel: str) -> AsyncGenerator[dict[str, Any], None]:
        """Subscribe to a Redis channel and yield verified messages."""
        if not self._redis:
            logger.warning("Redis not connected, cannot subscribe")
            return

        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(channel)
        logger.info("Subscribed to channel: %s", channel)

        async for raw_message in self._pubsub.listen():
            if raw_message["type"] != "message":
                continue
            try:
                message = json.loads(raw_message["data"])
                signature = message.pop("signature", "")
                if self._signer.verify(message, signature):
                    yield message
                else:
                    logger.warning("Invalid signature on message %s", message.get("message_id"))
            except (json.JSONDecodeError, KeyError) as e:
                logger.error("Malformed message on channel %s: %s", channel, e)

    @property
    def is_connected(self) -> bool:
        """Check if Redis connection is active."""
        return self._redis is not None
