"""
TWINFORGE — Agent 3: Data & IoT Agent.
Single interface to all external data sources.
Polls simulated OPC-UA / MQTT endpoints, manages AASX files,
validates sensor data, and monitors thresholds.
"""
from __future__ import annotations
import json
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from twinforge.core.schemas import (
    DataRequest, DataResponse, SensorReading, Anomaly, AlertSeverity, AgentAction
)
from twinforge.core.logging_config import log_agent_action
from twinforge.agents.data_iot.simulators import (
    SensorSimulator, OPCUASimulator, MQTTSimulator
)

logger = logging.getLogger("twinforge.agent.data_iot")

AGENT_ID = "agent_3_data_iot"


class DataIoTAgent:
    """
    Agent 3 — Data & IoT Agent
    
    Permissions:
    - READ from OPC-UA servers (simulated, read-only)
    - READ from MQTT broker (subscribe only)
    - READ/WRITE AASX file store
    - READ/WRITE time-series (in-memory)
    - NO access to Agent 1 (user layer)
    - NO LLM inference calls
    """
    
    def __init__(self, data_dir: Path = None):
        self._opcua = OPCUASimulator()
        self._mqtt = MQTTSimulator()
        self._sensor_sim = SensorSimulator()
        self._timeseries_store: dict[str, list[dict]] = {}
        self._data_dir = data_dir or Path("data")
        self._aasx_dir = self._data_dir / "aasx"
        self._aasx_dir.mkdir(parents=True, exist_ok=True)
    
    # ═══════════════════════════════════════════════════════
    # TOOL: OPC-UA Reader
    # ═══════════════════════════════════════════════════════
    
    def opcua_reader(self, asset_id: str) -> dict[str, Any]:
        """Read sensor data from OPC-UA endpoint (simulated)."""
        start = time.time()
        try:
            result = self._opcua.read_nodes(asset_id)
            duration = (time.time() - start) * 1000
            
            log_agent_action(
                agent_id=AGENT_ID,
                action="opcua_read",
                tool_used="opcua_reader",
                input_data=asset_id,
                output_data=json.dumps(result, default=str),
                duration_ms=duration,
                reasoning_trace=f"Read OPC-UA nodes for asset {asset_id}"
            )
            return result
        except Exception as e:
            log_agent_action(
                agent_id=AGENT_ID, action="opcua_read", tool_used="opcua_reader",
                success=False, error=str(e), input_data=asset_id,
                duration_ms=(time.time() - start) * 1000,
            )
            raise
    
    # ═══════════════════════════════════════════════════════
    # TOOL: MQTT Subscriber
    # ═══════════════════════════════════════════════════════
    
    def mqtt_subscriber(self, asset_id: str, count: int = 5) -> list[dict[str, Any]]:
        """Subscribe and get MQTT messages (simulated)."""
        start = time.time()
        self._mqtt.subscribe(f"factory/{asset_id}/sensors/#")
        messages = self._mqtt.get_messages(asset_id, count)
        
        log_agent_action(
            agent_id=AGENT_ID,
            action="mqtt_subscribe",
            tool_used="mqtt_subscriber",
            input_data=asset_id,
            duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Subscribed to MQTT topic for {asset_id}, got {len(messages)} messages"
        )
        return messages
    
    # ═══════════════════════════════════════════════════════
    # TOOL: AASX File Manager
    # ═══════════════════════════════════════════════════════
    
    def aasx_file_manager(self, action: str, asset_id: str, data: dict = None) -> dict[str, Any]:
        """Manage AASX files. Actions: save, load, list, delete."""
        start = time.time()
        filepath = self._aasx_dir / f"{asset_id}.json"
        
        if action == "save":
            filepath.write_text(json.dumps(data or {}, indent=2, default=str))
            result = {"action": "saved", "path": str(filepath)}
        elif action == "load":
            if filepath.exists():
                result = {"action": "loaded", "data": json.loads(filepath.read_text())}
            else:
                result = {"action": "not_found", "path": str(filepath)}
        elif action == "list":
            files = [f.stem for f in self._aasx_dir.glob("*.json")]
            result = {"action": "list", "files": files}
        elif action == "delete":
            if filepath.exists():
                filepath.unlink()
                result = {"action": "deleted", "path": str(filepath)}
            else:
                result = {"action": "not_found"}
        else:
            result = {"action": "unknown", "error": f"Unknown action: {action}"}
        
        log_agent_action(
            agent_id=AGENT_ID, action=f"aasx_{action}", tool_used="aasx_file_manager",
            input_data=asset_id, duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"AASX {action} for {asset_id}"
        )
        return result
    
    # ═══════════════════════════════════════════════════════
    # TOOL: Time-Series Writer
    # ═══════════════════════════════════════════════════════
    
    def timeseries_writer(self, asset_id: str, readings: list[dict]) -> dict[str, Any]:
        """Write readings to in-memory time-series store."""
        start = time.time()
        if asset_id not in self._timeseries_store:
            self._timeseries_store[asset_id] = []
        
        self._timeseries_store[asset_id].extend(readings)
        
        # Keep last 10000 readings per asset
        if len(self._timeseries_store[asset_id]) > 10000:
            self._timeseries_store[asset_id] = self._timeseries_store[asset_id][-10000:]
        
        log_agent_action(
            agent_id=AGENT_ID, action="timeseries_write", tool_used="timeseries_writer",
            input_data=asset_id, duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Stored {len(readings)} readings for {asset_id}"
        )
        return {"stored": len(readings), "total": len(self._timeseries_store[asset_id])}
    
    # ═══════════════════════════════════════════════════════
    # TOOL: Threshold Monitor
    # ═══════════════════════════════════════════════════════
    
    def threshold_monitor(self, readings: list[dict]) -> list[Anomaly]:
        """Validate sensor values against thresholds, flag anomalies."""
        start = time.time()
        anomalies = []
        
        for reading in readings:
            sensor_type = reading.get("sensor_type", "")
            value = reading.get("value", 0)
            profile = SensorSimulator.SENSOR_PROFILES.get(sensor_type)
            
            if not profile:
                continue
            
            below_threshold = profile.get("below_threshold", False)
            
            if below_threshold:
                # Alert when below threshold (e.g., coolant flow)
                if value <= profile["threshold_critical"]:
                    anomalies.append(Anomaly(
                        sensor_id=reading.get("sensor_id", "unknown"),
                        value=value,
                        threshold=profile["threshold_critical"],
                        severity=AlertSeverity.CRITICAL,
                        message=f"{sensor_type} critically low: {value}{profile['unit']} (min: {profile['threshold_critical']}{profile['unit']})"
                    ))
                elif value <= profile["threshold_warning"]:
                    anomalies.append(Anomaly(
                        sensor_id=reading.get("sensor_id", "unknown"),
                        value=value,
                        threshold=profile["threshold_warning"],
                        severity=AlertSeverity.WARNING,
                        message=f"{sensor_type} below normal: {value}{profile['unit']} (min: {profile['threshold_warning']}{profile['unit']})"
                    ))
            else:
                # Alert when above threshold
                if value >= profile["threshold_critical"]:
                    anomalies.append(Anomaly(
                        sensor_id=reading.get("sensor_id", "unknown"),
                        value=value,
                        threshold=profile["threshold_critical"],
                        severity=AlertSeverity.CRITICAL,
                        message=f"{sensor_type} critical: {value}{profile['unit']} (max: {profile['threshold_critical']}{profile['unit']})"
                    ))
                elif value >= profile["threshold_warning"]:
                    anomalies.append(Anomaly(
                        sensor_id=reading.get("sensor_id", "unknown"),
                        value=value,
                        threshold=profile["threshold_warning"],
                        severity=AlertSeverity.WARNING,
                        message=f"{sensor_type} elevated: {value}{profile['unit']} (max: {profile['threshold_warning']}{profile['unit']})"
                    ))
        
        log_agent_action(
            agent_id=AGENT_ID, action="threshold_check", tool_used="threshold_monitor",
            duration_ms=(time.time() - start) * 1000,
            reasoning_trace=f"Checked {len(readings)} readings, found {len(anomalies)} anomalies"
        )
        return anomalies
    
    # ═══════════════════════════════════════════════════════
    # MAIN ENTRY POINT (called by Agent 2 via LangGraph)
    # ═══════════════════════════════════════════════════════
    
    def process_data_request(self, request: DataRequest) -> DataResponse:
        """
        Main entry point: process a data request from Agent 2.
        Reads sensors, validates, checks thresholds, returns response.
        """
        start = time.time()
        
        # 1. Read OPC-UA sensors
        opcua_data = self.opcua_reader(request.asset_id)
        readings_raw = opcua_data.get("readings", [])
        
        # 2. Convert to SensorReading models
        sensor_readings = []
        for r in readings_raw:
            sensor_readings.append(SensorReading(
                sensor_id=r["sensor_id"],
                value=r["value"],
                unit=r["unit"],
                timestamp=datetime.fromisoformat(r["timestamp"]),
            ))
        
        # 3. Check thresholds for anomalies
        anomalies = self.threshold_monitor(readings_raw)
        
        # 4. Store in time-series
        self.timeseries_writer(request.asset_id, readings_raw)
        
        # 5. Build sensor_data dict for easy access
        sensor_data = {}
        for r in readings_raw:
            sensor_data[r["sensor_type"]] = {
                "value": r["value"],
                "unit": r["unit"],
            }
        
        return DataResponse(
            asset_id=request.asset_id,
            sensor_data=sensor_data,
            readings=sensor_readings,
            validated=True,
            anomalies=anomalies,
        )
