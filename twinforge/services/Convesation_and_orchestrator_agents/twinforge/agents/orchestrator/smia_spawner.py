"""
TWINFORGE — SMIA Agent Spawner (Real SPADE Integration).

Implements the SMIA (Smart Manufacturing Interoperable Agent) pattern using
the SPADE multi-agent framework. Each digital twin gets its own SPADE agent
with cyclic behaviours for sensor monitoring, KPI computation, and fault
detection — following the CSS (Capability-Skill-Service) model.

Architecture (per README Agent 2 spec):
  - smia_agent_spawner.py: Spawns specialized agents for AAS submodel interaction
  - Each agent uses CyclicBehaviour (SPADE) for autonomous monitoring
  - Agents expose services: get_kpis, get_sensors, get_alerts
  - TFT predictions are wired as an agent service

Reference: SMIA documentation — ExtensibleSMIAAgent pattern.
"""
from __future__ import annotations
import asyncio
import logging
import time
import threading
from datetime import datetime
from typing import Any, Optional, Dict, Callable

logger = logging.getLogger("twinforge.smia.spawner")

# ═══════════════════════════════════════════════════════════
#  SPADE availability detection
# ═══════════════════════════════════════════════════════════

_SPADE_AVAILABLE = False
try:
    import spade
    from spade.agent import Agent as SPADEAgent
    from spade.behaviour import CyclicBehaviour, OneShotBehaviour, PeriodicBehaviour
    from spade.message import Message as SPADEMessage
    _SPADE_AVAILABLE = True
    logger.info("SPADE framework loaded (v%s) — real agent mode", spade.__version__)
except ImportError:
    logger.warning("SPADE not installed — SMIA agents will run in simulated mode")


# ═══════════════════════════════════════════════════════════
#  CSS MODEL  (Capability-Skill-Service)
# ═══════════════════════════════════════════════════════════

class CSSModel:
    """
    CSS (Capability-Skill-Service) model for SMIA agents.
    Reference: RAMI 4.0 / Industry 4.0 CSS architecture.
    """
    def __init__(self):
        self.capabilities: list[str] = []
        self.skills: list[str] = []
        self.services: dict[str, Callable] = {}

    def add_capability(self, cap: str):
        if cap not in self.capabilities:
            self.capabilities.append(cap)

    def add_skill(self, skill: str):
        if skill not in self.skills:
            self.skills.append(skill)

    def add_service(self, service_id: str, service_method: Callable):
        self.services[service_id] = service_method

    def to_dict(self) -> dict:
        return {
            "capabilities": self.capabilities[:],
            "skills": self.skills[:],
            "services": list(self.services.keys()),
        }


# ═══════════════════════════════════════════════════════════
#  SPADE BEHAVIOURS for SMIA Twin Agents
# ═══════════════════════════════════════════════════════════

if _SPADE_AVAILABLE:

    class SensorMonitorBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour: polls sensor state every N seconds.
        Attached to each twin's SMIA agent for self-monitoring.
        """
        async def on_start(self):
            self.iteration = 0
            logger.info("SensorMonitorBehaviour started for %s", self.agent.jid)

        async def run(self):
            self.iteration += 1
            twin_id = getattr(self.agent, "twin_id", "unknown")
            sensor_snapshot = getattr(self.agent, "latest_sensors", {})

            if sensor_snapshot:
                logger.debug(
                    "SMIA[%s] sensor poll #%d: %d channels",
                    twin_id, self.iteration, len(sensor_snapshot)
                )
                # Check for threshold violations
                temp = sensor_snapshot.get("temperature", 0)
                vib = sensor_snapshot.get("vibration", 0)
                if temp > 85 or vib > 7:
                    logger.warning(
                        "SMIA[%s] threshold alert: temp=%.1f, vib=%.1f",
                        twin_id, temp, vib
                    )
                    alerts = getattr(self.agent, "active_alerts", [])
                    alerts.append({
                        "type": "threshold",
                        "sensor": "temperature" if temp > 85 else "vibration",
                        "value": temp if temp > 85 else vib,
                        "timestamp": datetime.utcnow().isoformat(),
                    })
                    self.agent.active_alerts = alerts

            await asyncio.sleep(5)  # Poll every 5 seconds


    class KPIComputeBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour: recomputes KPIs periodically.
        Uses the KPIEngine from Agent 2.
        """
        async def on_start(self):
            self.iteration = 0
            logger.info("KPIComputeBehaviour started for %s", self.agent.jid)

        async def run(self):
            self.iteration += 1
            twin_id = getattr(self.agent, "twin_id", "unknown")
            kpi_engine = getattr(self.agent, "kpi_engine", None)
            sensors = getattr(self.agent, "latest_sensors", {})

            if kpi_engine and sensors:
                # Convert flat sensor dict to nested format expected by kpi_engine
                sensor_input = {}
                for k, v in sensors.items():
                    if isinstance(v, (int, float)):
                        sensor_input[k] = {"value": v}
                    else:
                        sensor_input[k] = v

                kpis = kpi_engine.compute_kpis_from_sensors(sensor_input)
                self.agent.latest_kpis = kpis
                logger.debug("SMIA[%s] KPI update #%d: OEE=%.1f%%", twin_id, self.iteration, kpis.oee)

            await asyncio.sleep(10)  # Recompute every 10 seconds


    class TFTPredictionBehaviour(CyclicBehaviour):
        """
        Cyclic behaviour: runs TFT prediction at regular intervals.
        Attaches prediction results to the agent for service queries.
        """
        async def on_start(self):
            self.iteration = 0
            logger.info("TFTPredictionBehaviour started for %s", self.agent.jid)

        async def run(self):
            self.iteration += 1
            twin_id = getattr(self.agent, "twin_id", "unknown")
            tft_engine = getattr(self.agent, "tft_engine", None)

            if tft_engine:
                prediction = tft_engine.predict(twin_id, "temperature")
                self.agent.latest_prediction = prediction
                risk = prediction.get("anomaly_risk", 0)
                if risk > 0.5:
                    logger.warning("SMIA[%s] TFT anomaly risk HIGH: %.2f", twin_id, risk)

            await asyncio.sleep(30)  # Predict every 30 seconds


    class TwinSMIAAgent(SPADEAgent):
        """
        SPADE agent representing one digital twin — follows the
        ExtensibleSMIAAgent pattern from the SMIA package.

        Capabilities (SPADE Behaviours):
          - SensorMonitorBehaviour: self-monitoring
          - KPIComputeBehaviour: KPI computation
          - TFTPredictionBehaviour: predictive maintenance

        Services (callable methods):
          - get_kpis: return latest KPIs
          - get_sensors: return latest sensor snapshot
          - get_alerts: return active alerts
          - get_prediction: return latest TFT prediction
        """
        def __init__(self, jid: str, password: str, twin_id: str,
                     twin_level: str, kpi_engine=None, tft_engine=None):
            super().__init__(jid, password)
            self.twin_id = twin_id
            self.twin_level = twin_level
            self.kpi_engine = kpi_engine
            self.tft_engine = tft_engine

            # State
            self.latest_sensors: dict = {}
            self.latest_kpis = None
            self.latest_prediction: dict = {}
            self.active_alerts: list = []

            # CSS Model
            self.css_model = CSSModel()
            self.css_model.add_capability("self_monitoring")
            self.css_model.add_capability("kpi_computation")
            self.css_model.add_capability("fault_detection")
            self.css_model.add_capability("predictive_maintenance")
            self.css_model.add_skill("read_sensors")
            self.css_model.add_skill("compute_oee")
            self.css_model.add_skill("detect_anomalies")
            self.css_model.add_skill("tft_predict")
            self.css_model.add_service("get_kpis", self.service_get_kpis)
            self.css_model.add_service("get_sensors", self.service_get_sensors)
            self.css_model.add_service("get_alerts", self.service_get_alerts)
            self.css_model.add_service("get_prediction", self.service_get_prediction)

        async def setup(self):
            """Add SPADE behaviours (= SMIA agent capabilities)."""
            logger.info("SMIA Agent [%s] starting for twin %s (%s)",
                        self.jid, self.twin_id, self.twin_level)

            # Add behaviours like ExtensibleSMIAAgent.add_new_agent_capability()
            self.add_behaviour(SensorMonitorBehaviour())
            self.add_behaviour(KPIComputeBehaviour())
            self.add_behaviour(TFTPredictionBehaviour())

        # ─── Agent Services (ExtensibleSMIAAgent.add_new_agent_service pattern) ───

        def service_get_kpis(self) -> dict:
            if self.latest_kpis:
                return {
                    "oee": self.latest_kpis.oee,
                    "availability": self.latest_kpis.availability,
                    "performance": self.latest_kpis.performance,
                    "quality": self.latest_kpis.quality,
                    "energy_kwh": self.latest_kpis.energy_consumption_kwh,
                }
            return {}

        def service_get_sensors(self) -> dict:
            return self.latest_sensors.copy()

        def service_get_alerts(self) -> list:
            return self.active_alerts[:]

        def service_get_prediction(self) -> dict:
            return self.latest_prediction.copy()

        def update_sensors(self, sensor_data: dict):
            """Called by Agent 2 to push sensor updates to the SMIA agent."""
            clean = {}
            for k, v in sensor_data.items():
                if isinstance(v, dict):
                    clean[k] = float(v.get("value", 0))
                elif isinstance(v, (int, float)):
                    clean[k] = float(v)
            self.latest_sensors = clean

        def get_status(self) -> dict:
            return {
                "agent_jid": str(self.jid),
                "twin_id": self.twin_id,
                "twin_level": self.twin_level,
                "is_alive": self.is_alive(),
                "css_model": self.css_model.to_dict(),
                "behaviours_count": len(self.behaviours),
                "active_alerts": len(self.active_alerts),
                "has_kpis": self.latest_kpis is not None,
                "has_prediction": bool(self.latest_prediction),
                "sensor_channels": len(self.latest_sensors),
            }


# ═══════════════════════════════════════════════════════════
#  SIMULATED SMIA AGENT (fallback if SPADE not available)
# ═══════════════════════════════════════════════════════════

class SimulatedSMIAAgent:
    """Fallback: simulates SMIA agent behaviour without SPADE."""

    def __init__(self, twin_id: str, twin_level: str, kpi_engine=None, tft_engine=None):
        self.twin_id = twin_id
        self.twin_level = twin_level
        self.kpi_engine = kpi_engine
        self.tft_engine = tft_engine
        self.latest_sensors: dict = {}
        self.latest_kpis = None
        self.latest_prediction: dict = {}
        self.active_alerts: list = []
        self.css_model = CSSModel()
        self.css_model.add_capability("self_monitoring")
        self.css_model.add_capability("kpi_computation")
        self.css_model.add_capability("fault_detection")
        self.css_model.add_capability("predictive_maintenance")
        self.css_model.add_skill("read_sensors")
        self.css_model.add_skill("compute_oee")
        self.css_model.add_skill("detect_anomalies")
        self.css_model.add_skill("tft_predict")
        self._active = True
        logger.info("SimulatedSMIAAgent created for twin %s (%s)", twin_id, twin_level)

    def is_alive(self) -> bool:
        return self._active

    def update_sensors(self, sensor_data: dict):
        clean = {}
        for k, v in sensor_data.items():
            if isinstance(v, dict):
                clean[k] = float(v.get("value", 0))
            elif isinstance(v, (int, float)):
                clean[k] = float(v)
        self.latest_sensors = clean

    def service_get_kpis(self) -> dict:
        if self.latest_kpis:
            return {
                "oee": self.latest_kpis.oee,
                "availability": self.latest_kpis.availability,
                "performance": self.latest_kpis.performance,
                "quality": self.latest_kpis.quality,
                "energy_kwh": self.latest_kpis.energy_consumption_kwh,
            }
        return {}

    def service_get_sensors(self) -> dict:
        return self.latest_sensors.copy()

    def service_get_alerts(self) -> list:
        return self.active_alerts[:]

    def service_get_prediction(self) -> dict:
        return self.latest_prediction.copy()

    def get_status(self) -> dict:
        return {
            "agent_jid": f"smia_{self.twin_id}@localhost",
            "twin_id": self.twin_id,
            "twin_level": self.twin_level,
            "is_alive": self._active,
            "css_model": self.css_model.to_dict(),
            "behaviours_count": 3,
            "active_alerts": len(self.active_alerts),
            "has_kpis": self.latest_kpis is not None,
            "has_prediction": bool(self.latest_prediction),
            "sensor_channels": len(self.latest_sensors),
            "mode": "simulated",
        }


# ═══════════════════════════════════════════════════════════
#  SMIA SPAWNER  (manages lifecycle of all SMIA agents)
# ═══════════════════════════════════════════════════════════

class SMIASpawner:
    """
    Manages the lifecycle of SMIA agents (one per digital twin).

    Uses real SPADE agents when the `spade` package is available,
    otherwise falls back to simulated agents.

    Usage:
        spawner = SMIASpawner(kpi_engine=kpi_engine, tft_engine=tft_engine)
        info = spawner.spawn(twin_id="CNC_001", twin_level="Asset")
        status = spawner.get_agent_status("CNC_001")
        spawner.update_sensors("CNC_001", {"temperature": 72.5})
    """

    def __init__(self, kpi_engine=None, tft_engine=None,
                 xmpp_server: str = "localhost"):
        self._agents: Dict[str, Any] = {}
        self._kpi_engine = kpi_engine
        self._tft_engine = tft_engine
        self._xmpp_server = xmpp_server
        self._use_spade = _SPADE_AVAILABLE
        self._agent_counter = 0
        logger.info("SMIASpawner initialized (mode=%s)",
                     "SPADE" if self._use_spade else "Simulated")

    def spawn(self, twin_id: str, twin_level: str) -> dict:
        """
        Spawn a new SMIA agent for a digital twin.

        Returns agent info dict compatible with existing code.
        """
        start = time.time()

        if twin_id in self._agents:
            agent = self._agents[twin_id]
            return self._build_agent_info(twin_id, twin_level, agent, "already_running")

        self._agent_counter += 1

        if self._use_spade:
            agent = self._spawn_spade_agent(twin_id, twin_level)
        else:
            agent = SimulatedSMIAAgent(
                twin_id=twin_id,
                twin_level=twin_level,
                kpi_engine=self._kpi_engine,
                tft_engine=self._tft_engine,
            )

        self._agents[twin_id] = agent

        duration_ms = (time.time() - start) * 1000
        logger.info("SMIA agent spawned for %s (%s) in %.1fms [%s mode]",
                     twin_id, twin_level, duration_ms,
                     "SPADE" if self._use_spade else "Simulated")

        return self._build_agent_info(twin_id, twin_level, agent, "spawned")

    def _spawn_spade_agent(self, twin_id: str, twin_level: str):
        """Create and start a real SPADE agent."""
        jid = f"smia_{twin_id.lower().replace('-', '_')}@{self._xmpp_server}"
        password = f"twinforge_{twin_id}"

        agent = TwinSMIAAgent(
            jid=jid,
            password=password,
            twin_id=twin_id,
            twin_level=twin_level,
            kpi_engine=self._kpi_engine,
            tft_engine=self._tft_engine,
        )

        # Start agent in background (non-blocking)
        # Note: in production, this would connect to an XMPP server.
        # For local dev, the agent runs with behaviours but no XMPP.
        try:
            future = agent.start(auto_register=True)
            # Don't wait for connection — in dev, there may be no XMPP server
            logger.info("SPADE agent %s start initiated", jid)
        except Exception as e:
            logger.warning("SPADE agent %s start failed (expected without XMPP): %s", jid, e)
            # Fall back to simulated mode for this agent
            agent = SimulatedSMIAAgent(
                twin_id=twin_id,
                twin_level=twin_level,
                kpi_engine=self._kpi_engine,
                tft_engine=self._tft_engine,
            )

        return agent

    def _build_agent_info(self, twin_id: str, twin_level: str,
                          agent, status: str) -> dict:
        """Build agent info dict (backward-compatible with old simulated format)."""
        is_spade = _SPADE_AVAILABLE and isinstance(agent, SPADEAgent) if _SPADE_AVAILABLE else False

        return {
            "agent_name": f"SMIA_{twin_level}Agent_{twin_id}",
            "agent_type": f"{twin_level}Agent",
            "twin_id": twin_id,
            "capabilities": [
                "self_monitoring",
                "kpi_computation",
                "fault_detection",
                "predictive_maintenance",
                "sensor_polling",
            ],
            "status": status,
            "runtime": "SPADE" if is_spade else "Simulated",
            "css_model": agent.css_model.to_dict() if hasattr(agent, "css_model") else {},
            "behaviours": [
                "SensorMonitorBehaviour",
                "KPIComputeBehaviour",
                "TFTPredictionBehaviour",
            ],
            "services": [
                "get_kpis",
                "get_sensors",
                "get_alerts",
                "get_prediction",
            ],
        }

    # ─── Agent Management ─────────────────────────────────

    def get_agent(self, twin_id: str):
        """Get the SMIA agent instance for a twin."""
        return self._agents.get(twin_id)

    def get_agent_status(self, twin_id: str) -> Optional[dict]:
        """Get status of a specific SMIA agent."""
        agent = self._agents.get(twin_id)
        if agent is None:
            return None
        return agent.get_status()

    def get_all_agents(self) -> list[dict]:
        """List all spawned SMIA agents."""
        result = []
        for twin_id, agent in self._agents.items():
            result.append(agent.get_status())
        return result

    def update_sensors(self, twin_id: str, sensor_data: dict):
        """Push sensor data to a twin's SMIA agent."""
        agent = self._agents.get(twin_id)
        if agent:
            agent.update_sensors(sensor_data)

    def stop_agent(self, twin_id: str) -> bool:
        """Stop and remove an SMIA agent."""
        agent = self._agents.pop(twin_id, None)
        if agent is None:
            return False
        if _SPADE_AVAILABLE and isinstance(agent, SPADEAgent):
            try:
                agent.stop()
            except Exception:
                pass
        elif isinstance(agent, SimulatedSMIAAgent):
            agent._active = False
        logger.info("SMIA agent stopped for %s", twin_id)
        return True

    @property
    def agent_count(self) -> int:
        return len(self._agents)

    @property
    def mode(self) -> str:
        return "SPADE" if self._use_spade else "Simulated"
