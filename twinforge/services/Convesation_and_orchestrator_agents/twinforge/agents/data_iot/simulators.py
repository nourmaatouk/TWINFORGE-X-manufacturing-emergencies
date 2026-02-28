"""
TWINFORGE — Realistic sensor data simulators.
Generates simulated OPC-UA / MQTT sensor feeds with configurable
noise, drift, and fault injection for demonstration purposes.
"""
from __future__ import annotations
import math
import random
import time
from datetime import datetime, timedelta
from typing import Any


class SensorSimulator:
    """
    Generates realistic sensor readings for manufacturing equipment.
    Supports temperature, vibration, pressure, spindle speed,
    energy consumption, and more.
    """
    
    # ── Default sensor profiles ──────────────────────────
    SENSOR_PROFILES: dict[str, dict[str, Any]] = {
        "temperature": {
            "unit": "°C",
            "base_value": 65.0,
            "noise_amplitude": 3.0,
            "drift_rate": 0.02,
            "min_val": 20.0,
            "max_val": 120.0,
            "threshold_warning": 85.0,
            "threshold_critical": 95.0,
        },
        "vibration": {
            "unit": "mm/s",
            "base_value": 2.5,
            "noise_amplitude": 0.8,
            "drift_rate": 0.005,
            "min_val": 0.0,
            "max_val": 15.0,
            "threshold_warning": 7.0,
            "threshold_critical": 10.0,
        },
        "pressure": {
            "unit": "bar",
            "base_value": 6.0,
            "noise_amplitude": 0.3,
            "drift_rate": 0.01,
            "min_val": 0.0,
            "max_val": 12.0,
            "threshold_warning": 9.0,
            "threshold_critical": 10.5,
        },
        "spindle_speed": {
            "unit": "RPM",
            "base_value": 8000.0,
            "noise_amplitude": 150.0,
            "drift_rate": 5.0,
            "min_val": 0.0,
            "max_val": 15000.0,
            "threshold_warning": 12000.0,
            "threshold_critical": 14000.0,
        },
        "energy_consumption": {
            "unit": "kWh",
            "base_value": 45.0,
            "noise_amplitude": 5.0,
            "drift_rate": 0.1,
            "min_val": 0.0,
            "max_val": 100.0,
            "threshold_warning": 70.0,
            "threshold_critical": 85.0,
        },
        "coolant_flow": {
            "unit": "L/min",
            "base_value": 12.0,
            "noise_amplitude": 1.5,
            "drift_rate": 0.03,
            "min_val": 0.0,
            "max_val": 25.0,
            "threshold_warning": 5.0,   # Too low
            "threshold_critical": 3.0,   # Too low
            "below_threshold": True,     # Alert when BELOW
        },
        "tool_wear": {
            "unit": "%",
            "base_value": 35.0,
            "noise_amplitude": 2.0,
            "drift_rate": 0.5,
            "min_val": 0.0,
            "max_val": 100.0,
            "threshold_warning": 70.0,
            "threshold_critical": 90.0,
        },
    }
    
    def __init__(self, fault_probability: float = 0.05):
        self._tick = 0
        self._fault_probability = fault_probability
        self._fault_active = False
        self._fault_sensor: str | None = None
    
    def generate_reading(self, sensor_type: str, asset_id: str = "CNC-01") -> dict[str, Any]:
        """Generate a single sensor reading with realistic noise and optional faults."""
        profile = self.SENSOR_PROFILES.get(sensor_type)
        if not profile:
            raise ValueError(f"Unknown sensor type: {sensor_type}")
        
        self._tick += 1
        t = self._tick * 0.1
        
        # Base sinusoidal pattern + noise
        base = profile["base_value"]
        noise = random.gauss(0, profile["noise_amplitude"] * 0.3)
        drift = math.sin(t * 0.05) * profile["drift_rate"] * self._tick
        seasonal = math.sin(t * 0.3) * profile["noise_amplitude"] * 0.5
        
        value = base + noise + drift + seasonal
        
        # Fault injection
        if random.random() < self._fault_probability:
            self._fault_active = True
            self._fault_sensor = sensor_type
            # Spike the value
            value = base + profile["noise_amplitude"] * random.uniform(3, 6)
        elif self._fault_active and self._fault_sensor == sensor_type:
            # Gradually recover
            if random.random() < 0.3:
                self._fault_active = False
                self._fault_sensor = None
            else:
                value = base + profile["noise_amplitude"] * random.uniform(2, 4)
        
        # Clamp to valid range
        value = max(profile["min_val"], min(profile["max_val"], value))
        
        return {
            "sensor_id": f"{asset_id}_{sensor_type}",
            "sensor_type": sensor_type,
            "value": round(value, 2),
            "unit": profile["unit"],
            "asset_id": asset_id,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def generate_all_readings(self, asset_id: str = "CNC-01") -> list[dict[str, Any]]:
        """Generate readings for all sensor types."""
        readings = []
        for sensor_type in self.SENSOR_PROFILES:
            readings.append(self.generate_reading(sensor_type, asset_id))
        return readings
    
    def generate_historical(
        self, 
        sensor_type: str, 
        asset_id: str = "CNC-01",
        hours: int = 1, 
        interval_seconds: int = 60
    ) -> list[dict[str, Any]]:
        """Generate historical time-series data."""
        readings = []
        now = datetime.utcnow()
        total_points = (hours * 3600) // interval_seconds
        
        for i in range(total_points):
            ts = now - timedelta(seconds=(total_points - i) * interval_seconds)
            reading = self.generate_reading(sensor_type, asset_id)
            reading["timestamp"] = ts.isoformat()
            readings.append(reading)
        
        return readings


class OPCUASimulator:
    """Simulates an OPC-UA server endpoint."""
    
    def __init__(self):
        self._sensor_sim = SensorSimulator(fault_probability=0.03)
        self._connected = False
        self._endpoint = "opc.tcp://simulated-server:4840"
    
    def connect(self, endpoint: str = None) -> dict[str, Any]:
        """Simulate connecting to OPC-UA server."""
        self._connected = True
        self._endpoint = endpoint or self._endpoint
        return {
            "status": "connected",
            "endpoint": self._endpoint,
            "protocol": "OPC-UA",
            "security_mode": "SignAndEncrypt",
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def read_nodes(self, asset_id: str, node_ids: list[str] = None) -> dict[str, Any]:
        """Read values from OPC-UA nodes."""
        if not self._connected:
            self.connect()
        
        readings = self._sensor_sim.generate_all_readings(asset_id)
        return {
            "endpoint": self._endpoint,
            "asset_id": asset_id,
            "readings": readings,
            "status": "OK",
            "read_timestamp": datetime.utcnow().isoformat(),
        }
    
    def disconnect(self):
        self._connected = False


class MQTTSimulator:
    """Simulates an MQTT broker subscription."""
    
    def __init__(self):
        self._sensor_sim = SensorSimulator(fault_probability=0.08)
        self._subscribed_topics: list[str] = []
    
    def subscribe(self, topic: str = "factory/+/sensors/#") -> dict[str, Any]:
        """Simulate subscribing to MQTT topic."""
        self._subscribed_topics.append(topic)
        return {
            "status": "subscribed",
            "topic": topic,
            "broker": "mqtt://simulated-broker:1883",
            "tls": True,
            "timestamp": datetime.utcnow().isoformat(),
        }
    
    def get_messages(self, asset_id: str, count: int = 5) -> list[dict[str, Any]]:
        """Get simulated MQTT messages."""
        messages = []
        for _ in range(count):
            reading = self._sensor_sim.generate_reading(
                random.choice(list(SensorSimulator.SENSOR_PROFILES.keys())),
                asset_id
            )
            messages.append({
                "topic": f"factory/{asset_id}/sensors/{reading['sensor_type']}",
                "payload": reading,
                "qos": 1,
                "retained": False,
            })
        return messages
