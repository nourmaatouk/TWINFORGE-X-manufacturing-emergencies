"""
TWINFORGE — KPI Engine & OEE Calculator.
Computes manufacturing KPIs from sensor data and historical records.
"""
from __future__ import annotations
import random
from typing import Any
from twinforge.core.schemas import KPIData


class KPIEngine:
    """
    Computes manufacturing Key Performance Indicators.
    
    OEE (Overall Equipment Effectiveness) = Availability × Performance × Quality
    - Availability: uptime / planned_time
    - Performance: actual_output / theoretical_output
    - Quality: good_parts / total_parts
    """
    
    def __init__(self):
        self._baselines: dict[str, KPIData] = {}
    
    def compute_oee(
        self,
        availability: float = None,
        performance: float = None,
        quality: float = None,
    ) -> float:
        """Compute OEE from A × P × Q (all as percentages)."""
        a = (availability or 92.0) / 100.0
        p = (performance or 88.0) / 100.0
        q = (quality or 97.0) / 100.0
        oee = a * p * q * 100.0
        return min(max(oee, 0.0), 100.0)
    
    def compute_kpis_from_sensors(
        self,
        sensor_data: dict[str, Any],
        asset_type: str = "CNC",
        energy_kwh: float = 0.0,
    ) -> KPIData:
        """
        Compute KPIs from live sensor data.
        Uses heuristics based on sensor values for demonstration.
        """
        # Extract key sensor values
        temp = sensor_data.get("temperature", {}).get("value", 65)
        vibration = sensor_data.get("vibration", {}).get("value", 2.5)
        spindle = sensor_data.get("spindle_speed", {}).get("value", 8000)
        tool_wear = sensor_data.get("tool_wear", {}).get("value", 35)
        energy = sensor_data.get("energy_consumption", {}).get("value", energy_kwh or 45)
        
        # Heuristic-based KPI computation
        # Availability: affected by temperature and vibration
        availability = 95.0
        if temp > 85:
            availability -= (temp - 85) * 0.5
        if vibration > 7:
            availability -= (vibration - 7) * 2
        availability = max(60.0, min(100.0, availability + random.uniform(-1, 1)))
        
        # Performance: affected by spindle speed relative to target
        target_spindle = 8000
        speed_ratio = spindle / target_spindle
        performance = min(100.0, speed_ratio * 90.0 + random.uniform(-2, 2))
        performance = max(60.0, min(100.0, performance))
        
        # Quality: affected by tool wear
        quality = 99.0 - (tool_wear * 0.1) + random.uniform(-0.5, 0.5)
        quality = max(75.0, min(100.0, quality))
        
        # OEE
        oee = self.compute_oee(availability, performance, quality)
        
        # Cycle time estimation
        cycle_time = 120 + random.uniform(-10, 10)  # seconds
        
        return KPIData(
            availability=round(availability, 1),
            performance=round(performance, 1),
            quality=round(quality, 1),
            oee=round(oee, 1),
            energy_consumption_kwh=round(energy, 1),
            cycle_time_seconds=round(cycle_time, 1),
        )
    
    def detect_faults(
        self,
        sensor_data: dict[str, Any],
        anomalies: list = None,
    ) -> list[dict[str, Any]]:
        """
        Rule-based fault detection from sensor data and anomalies.
        Returns list of detected faults with severity and recommendations.
        """
        faults = []
        
        # Check sensor values against fault conditions
        temp = sensor_data.get("temperature", {}).get("value", 0)
        vibration = sensor_data.get("vibration", {}).get("value", 0)
        tool_wear = sensor_data.get("tool_wear", {}).get("value", 0)
        coolant = sensor_data.get("coolant_flow", {}).get("value", 12)
        
        if temp > 90:
            faults.append({
                "fault_type": "OVERHEATING",
                "severity": "CRITICAL",
                "sensor": "temperature",
                "value": temp,
                "message": f"Machine overheating: {temp}°C exceeds safe limit",
                "recommendation": "Immediate shutdown recommended. Check cooling system."
            })
        elif temp > 80:
            faults.append({
                "fault_type": "HIGH_TEMPERATURE",
                "severity": "WARNING",
                "sensor": "temperature",
                "value": temp,
                "message": f"Elevated temperature: {temp}°C approaching limit",
                "recommendation": "Monitor closely. Schedule maintenance window."
            })
        
        if vibration > 10:
            faults.append({
                "fault_type": "EXCESSIVE_VIBRATION",
                "severity": "CRITICAL",
                "sensor": "vibration",
                "value": vibration,
                "message": f"Critical vibration level: {vibration} mm/s",
                "recommendation": "Check bearings, alignment, and balance immediately."
            })
        elif vibration > 7:
            faults.append({
                "fault_type": "HIGH_VIBRATION",
                "severity": "WARNING",
                "sensor": "vibration",
                "value": vibration,
                "message": f"Elevated vibration: {vibration} mm/s",
                "recommendation": "Schedule bearing inspection."
            })
        
        if tool_wear > 85:
            faults.append({
                "fault_type": "TOOL_WEAR_CRITICAL",
                "severity": "CRITICAL",
                "sensor": "tool_wear",
                "value": tool_wear,
                "message": f"Tool wear at {tool_wear}% — replacement needed",
                "recommendation": "Replace tooling immediately to prevent quality issues."
            })
        elif tool_wear > 65:
            faults.append({
                "fault_type": "TOOL_WEAR_HIGH",
                "severity": "WARNING",
                "sensor": "tool_wear",
                "value": tool_wear,
                "message": f"Tool wear at {tool_wear}%",
                "recommendation": "Schedule tool replacement within next maintenance window."
            })
        
        if coolant < 5:
            faults.append({
                "fault_type": "LOW_COOLANT",
                "severity": "WARNING",
                "sensor": "coolant_flow",
                "value": coolant,
                "message": f"Coolant flow low: {coolant} L/min",
                "recommendation": "Check coolant reservoir and pump."
            })
        
        # Include anomalies from threshold monitor
        if anomalies:
            for anomaly in anomalies:
                fault_msg = anomaly.message if hasattr(anomaly, "message") else str(anomaly)
                faults.append({
                    "fault_type": "THRESHOLD_ANOMALY",
                    "severity": anomaly.severity.value if hasattr(anomaly, "severity") else "WARNING",
                    "message": fault_msg,
                })
        
        return faults
    
    def store_baseline(self, twin_id: str, kpis: KPIData):
        """Store KPI baseline for future comparison."""
        self._baselines[twin_id] = kpis
    
    def get_baseline(self, twin_id: str) -> KPIData | None:
        return self._baselines.get(twin_id)
