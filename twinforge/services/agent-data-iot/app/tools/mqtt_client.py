"""
TWINFORGE Agent 3 — MQTT Client
Async MQTT client for subscribing to telemetry topics and publishing simulation data.
"""

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine, Optional

import paho.mqtt.client as mqtt

from app.models.schemas import MachineTelemetry

logger = logging.getLogger(__name__)


class MQTTClient:
    """
    Async-compatible MQTT client using paho-mqtt.

    Subscribes to telemetry topics and parses incoming messages
    into MachineTelemetry objects, then calls the provided callback.
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        topic: str = "twinforge/telemetry/#",
        client_id: str = "agent-data-iot",
        on_telemetry: Optional[Callable[[MachineTelemetry], Coroutine[Any, Any, None]]] = None,
    ) -> None:
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic = topic
        self.client_id = client_id
        self._on_telemetry = on_telemetry
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    async def connect(self) -> None:
        """Connect to the MQTT broker and start the background loop."""
        self._loop = asyncio.get_event_loop()
        self._client = mqtt.Client(
            client_id=self.client_id,
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
        )
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

        try:
            self._client.connect(self.broker_host, self.broker_port, keepalive=60)
            self._client.loop_start()
            logger.info("MQTT client connecting to %s:%d", self.broker_host, self.broker_port)
        except Exception as e:
            logger.error("MQTT connection failed: %s", e)
            raise

    async def disconnect(self) -> None:
        """Disconnect MQTT client."""
        if self._client:
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False
            logger.info("MQTT client disconnected")

    def _on_connect(self, client: Any, userdata: Any, flags: Any, rc: Any, properties: Any = None) -> None:
        """Callback when connected to broker."""
        if isinstance(rc, int):
            reason_code = rc
        else:
            reason_code = rc.value if hasattr(rc, 'value') else int(rc)

        if reason_code == 0:
            self._connected = True
            client.subscribe(self.topic)
            logger.info("MQTT connected and subscribed to %s", self.topic)
        else:
            logger.error("MQTT connection failed with code: %s", reason_code)

    def _on_disconnect(self, client: Any, userdata: Any, flags: Any = None, rc: Any = None, properties: Any = None) -> None:
        """Callback when disconnected from broker."""
        self._connected = False
        logger.warning("MQTT disconnected")

    def _on_message(self, client: Any, userdata: Any, msg: mqtt.MQTTMessage) -> None:
        """Callback when a message is received — schedule async processing."""
        if self._loop and self._on_telemetry:
            try:
                payload = json.loads(msg.payload.decode("utf-8"))
                record = MachineTelemetry.model_validate(payload)
                asyncio.run_coroutine_threadsafe(
                    self._on_telemetry(record),
                    self._loop,
                )
            except (json.JSONDecodeError, Exception) as e:
                logger.error("Failed to parse MQTT message on %s: %s", msg.topic, e)

    async def publish(self, topic: str, payload: dict[str, Any]) -> bool:
        """Publish a message to an MQTT topic."""
        if not self._client or not self._connected:
            logger.warning("MQTT not connected, cannot publish")
            return False
        try:
            msg = json.dumps(payload, default=str)
            result = self._client.publish(topic, msg, qos=1)
            return result.rc == mqtt.MQTT_ERR_SUCCESS
        except Exception as e:
            logger.error("MQTT publish failed: %s", e)
            return False

    @property
    def is_connected(self) -> bool:
        """Check if MQTT client is connected."""
        return self._connected
