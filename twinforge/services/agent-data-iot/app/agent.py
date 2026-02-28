"""
TWINFORGE Agent 3 — Core Agent Logic
DataIoTAgent class: manages lifecycle, connections, and request processing.
"""

import asyncio
import logging
import time
from typing import Any, Optional

from app.config import settings
from app.detection.anomaly_detector import AnomalyDetector
from app.models.schemas import (
    AnomalyAlert,
    MachineTelemetry,
    MachineState,
    MachineStatus,
)
from app.streaming.websocket_manager import WebSocketManager
from app.tools.sensor_validator import SensorValidator

logger = logging.getLogger(__name__)


class DataIoTAgent:
    """
    Core agent class for the Data/IoT Executor.
    Manages connections to Redis, MQTT, and coordinates
    telemetry ingestion, anomaly detection, and streaming.
    """

    def __init__(self) -> None:
        self.start_time: float = time.time()
        self.ws_manager = WebSocketManager()
        self.redis_broadcaster = None
        self.mqtt_client = None
        self.influxdb = None
        self.anomaly_detector = AnomalyDetector()
        self.sensor_validator = SensorValidator()

        # In-memory stores
        self._machine_states: dict[str, MachineState] = {}
        self._alerts: list[AnomalyAlert] = []
        self._alerts_lock = asyncio.Lock()
        self._simulations: dict[str, asyncio.Task] = {}
        self._max_alerts = 10000

    async def initialize(self) -> None:
        """Initialize all connections and background tasks."""
        logger.info("Initializing Agent 3 — Data/IoT Executor")

        # Redis broadcaster
        try:
            from app.streaming.redis_broadcaster import RedisBroadcaster
            self.redis_broadcaster = RedisBroadcaster(
                redis_url=settings.REDIS_URL,
                channel=settings.REDIS_TELEMETRY_CHANNEL,
            )
            await self.redis_broadcaster.connect()
            logger.info("Redis broadcaster connected")
        except Exception as e:
            logger.warning("Redis broadcaster unavailable: %s", e)
            self.redis_broadcaster = None

        # MQTT client
        try:
            from app.tools.mqtt_client import MQTTClient
            self.mqtt_client = MQTTClient(
                broker_host=settings.MQTT_BROKER_HOST,
                broker_port=settings.MQTT_BROKER_PORT,
                topic=settings.MQTT_TOPIC_TELEMETRY,
                client_id=settings.MQTT_CLIENT_ID,
                on_telemetry=self._handle_mqtt_telemetry,
            )
            await self.mqtt_client.connect()
            logger.info("MQTT client connected")
        except Exception as e:
            logger.warning("MQTT client unavailable: %s", e)
            self.mqtt_client = None

        logger.info("Agent 3 initialization complete")

    async def shutdown(self) -> None:
        """Gracefully shut down all connections and tasks."""
        logger.info("Shutting down Agent 3")

        # Cancel running simulations
        for sim_id, task in self._simulations.items():
            if not task.done():
                task.cancel()
                logger.info("Cancelled simulation %s", sim_id)

        if self.mqtt_client:
            await self.mqtt_client.disconnect()
        if self.redis_broadcaster:
            await self.redis_broadcaster.disconnect()

        logger.info("Agent 3 shutdown complete")

    # ─── Telemetry Ingestion Pipeline ────────────────────────────────────────

    async def ingest_telemetry(self, records: list[MachineTelemetry]) -> tuple[int, int, list[AnomalyAlert]]:
        """Process a batch of telemetry records through the full pipeline."""
        accepted = 0
        rejected = 0
        alerts: list[AnomalyAlert] = []

        for record in records:
            # Step 1: Validate
            is_valid, error = self.sensor_validator.validate(record)
            if not is_valid:
                logger.warning("Rejected telemetry from %s: %s", record.machine_id, error)
                rejected += 1
                continue

            # Step 2: Detect anomalies
            record_alerts = self.anomaly_detector.detect(record)
            if record_alerts:
                alerts.extend(record_alerts)
                async with self._alerts_lock:
                    self._alerts.extend(record_alerts)
                    if len(self._alerts) > self._max_alerts:
                        self._alerts = self._alerts[-self._max_alerts:]

            # Step 3: Update machine state
            self._update_machine_state(record, len(record_alerts))

            # Step 4: Broadcast to WebSocket clients
            await self.ws_manager.broadcast(record.model_dump(mode="json"))

            # Step 5: Broadcast to Redis
            if self.redis_broadcaster:
                try:
                    await self.redis_broadcaster.publish(record.model_dump(mode="json"))
                except Exception as e:
                    logger.error("Redis broadcast failed: %s", e)

            accepted += 1

        logger.info("Ingested %d/%d telemetry records, %d alerts", accepted, accepted + rejected, len(alerts))
        return accepted, rejected, alerts

    def _update_machine_state(self, record: MachineTelemetry, alert_count: int) -> None:
        """Update the in-memory latest state for a machine."""
        self._machine_states[record.machine_id] = MachineState(
            machine_id=record.machine_id,
            last_seen=record.timestamp,
            status=record.status,
            energy_kwh=record.energy_kwh,
            water_liters=record.water_liters,
            vibration=record.vibration,
            temperature=record.temperature,
            failure_flag=record.failure_flag,
            failure_risk_score=record.failure_risk_score,
            active_alerts=alert_count,
        )

    # ─── MQTT Callback ──────────────────────────────────────────────────────

    async def _handle_mqtt_telemetry(self, record: MachineTelemetry) -> None:
        """Callback for MQTT telemetry messages — feeds into ingestion pipeline."""
        await self.ingest_telemetry([record])

    # ─── State Queries ───────────────────────────────────────────────────────

    def get_all_machine_states(self) -> list[MachineState]:
        """Return the latest state of all known machines."""
        return list(self._machine_states.values())

    def get_machine_state(self, machine_id: str) -> Optional[MachineState]:
        """Return the latest state of a specific machine."""
        return self._machine_states.get(machine_id)

    async def get_machine_history(
        self,
        machine_id: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
        limit: int = 100,
    ) -> list[MachineTelemetry]:
        """Query historical telemetry."""
        if self.influxdb:
            return await self.influxdb.query_history(machine_id, start, end, limit)
        return []

    def get_alerts(self, limit: int = 100) -> list[AnomalyAlert]:
        """Return recent anomaly alerts."""
        return self._alerts[-limit:]

    # ─── Simulation Management ───────────────────────────────────────────────

    def register_simulation(self, sim_id: str, task: asyncio.Task) -> None:
        """Track a running simulation task."""
        self._simulations[sim_id] = task

    def get_active_simulation_count(self) -> int:
        """Return number of currently running simulations."""
        self._simulations = {k: v for k, v in self._simulations.items() if not v.done()}
        return len(self._simulations)

    # ─── Inter-Agent Processing ──────────────────────────────────────────────

    async def process(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Process an incoming agent request (from other agents)."""
        intent = payload.get("intent", "")
        logger.info("Processing agent request with intent: %s", intent)

        if intent == "query_sensor_data":
            machine_id = payload.get("machine_id")
            if machine_id:
                state = self.get_machine_state(machine_id)
                if state:
                    return {"status": "success", "data": state.model_dump(mode="json")}
                return {"status": "error", "message": f"Machine {machine_id} not found"}
            states = self.get_all_machine_states()
            return {"status": "success", "data": [s.model_dump(mode="json") for s in states]}

        elif intent == "query_history":
            machine_id = payload.get("machine_id", "M1")
            records = await self.get_machine_history(machine_id, limit=payload.get("limit", 100))
            return {"status": "success", "data": [r.model_dump(mode="json") for r in records]}

        elif intent == "anomaly_report":
            alerts = self.get_alerts(limit=payload.get("limit", 50))
            return {"status": "success", "data": [a.model_dump(mode="json") for a in alerts]}

        else:
            return {"status": "error", "message": f"Unknown intent: {intent}"}

    # ─── Health Info ─────────────────────────────────────────────────────────

    def get_health_info(self) -> dict[str, Any]:
        """Return detailed health information."""
        return {
            "status": "healthy",
            "agent": "agent-data-iot",
            "redis_connected": self.redis_broadcaster is not None,
            "influxdb_connected": self.influxdb is not None,
            "mqtt_connected": self.mqtt_client is not None,
            "active_simulations": self.get_active_simulation_count(),
            "uptime_seconds": round(time.time() - self.start_time, 2),
        }
