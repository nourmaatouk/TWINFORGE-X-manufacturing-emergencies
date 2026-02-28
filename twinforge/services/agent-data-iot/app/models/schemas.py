"""
TWINFORGE Agent 3 — Pydantic Schemas
Data models for telemetry, simulations, anomaly alerts, and API request/response.
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


# ─── Enums ───────────────────────────────────────────────────────────────────

class MachineStatus(str, Enum):
    """Machine operational status."""
    RUNNING = "running"
    IDLE = "idle"
    FAILURE = "failure"
    MAINTENANCE = "maintenance"
    STARTING = "starting"
    STOPPING = "stopping"


class AlertSeverity(str, Enum):
    """Anomaly alert severity levels."""
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"


class AlertType(str, Enum):
    """Types of anomaly alerts."""
    VIBRATION_THRESHOLD = "vibration_threshold"
    TEMPERATURE_THRESHOLD = "temperature_threshold"
    ENERGY_SPIKE = "energy_spike"
    WATER_SPIKE = "water_spike"
    ROLLING_DEVIATION = "rolling_deviation"
    FAILURE_PREDICTED = "failure_predicted"
    FAILURE_DETECTED = "failure_detected"


# ─── Core Telemetry Model ────────────────────────────────────────────────────

class MachineTelemetry(BaseModel):
    """Single telemetry data point from a machine."""
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    machine_id: str = Field(..., description="Machine identifier, e.g. M1")
    energy_kwh: float = Field(..., ge=0, description="Energy consumption in kWh")
    water_liters: float = Field(..., ge=0, description="Water usage in liters")
    vibration: float = Field(..., ge=0, description="Vibration level (mm/s)")
    temperature: float = Field(..., description="Machine temperature (°C)")
    status: MachineStatus = Field(default=MachineStatus.RUNNING, description="Machine status")
    failure_flag: bool = Field(default=False, description="Whether a failure event occurred")
    failure_risk_score: float = Field(default=0.0, ge=0.0, le=1.0, description="Probability of failure")

    model_config = {"json_schema_extra": {
        "example": {
            "timestamp": "2026-02-18T17:00:00",
            "machine_id": "M1",
            "energy_kwh": 12.4,
            "water_liters": 3.1,
            "vibration": 2.5,
            "temperature": 75.2,
            "status": "running",
            "failure_flag": False,
            "failure_risk_score": 0.12,
        }
    }}


# ─── Ingestion ───────────────────────────────────────────────────────────────

class TelemetryIngest(BaseModel):
    """Payload for the POST /ingest endpoint (batch or single)."""
    data: list[MachineTelemetry] = Field(..., min_length=1, description="Telemetry records")


class IngestResponse(BaseModel):
    """Response for the POST /ingest endpoint."""
    accepted: int = Field(..., description="Number of records accepted")
    rejected: int = Field(default=0, description="Number of records rejected")
    alerts: list["AnomalyAlert"] = Field(default_factory=list, description="Anomaly alerts triggered")


# ─── Simulation ──────────────────────────────────────────────────────────────

class SimulationConfig(BaseModel):
    """Configuration for the real-time simulation engine."""
    number_of_machines: int = Field(default=5, ge=1, le=20, description="Number of machines to simulate")
    simulation_duration_hours: float = Field(default=4.0, ge=0.01, le=12.0, description="Duration in hours")
    sampling_interval_seconds: int = Field(default=5, ge=1, le=60, description="Sampling interval in seconds")
    anomaly_frequency: float = Field(default=0.05, ge=0.0, le=1.0, description="Probability of anomaly per cycle")
    production_intensity_level: float = Field(default=0.7, ge=0.0, le=1.0, description="Base production intensity")
    dataset_csv: Optional[str] = Field(default=None, description="Optional CSV data to seed simulation from")


class SimulationStatus(BaseModel):
    """Status of a running simulation."""
    simulation_id: str
    status: str = "running"
    machines: int = 0
    duration_hours: float = 0.0
    elapsed_seconds: float = 0.0
    points_generated: int = 0
    started_at: Optional[datetime] = None


class SimulationResponse(BaseModel):
    """Response for POST /simulate endpoint."""
    simulation_id: str
    status: str = "started"
    message: str = ""
    config: SimulationConfig


# ─── Anomaly Alerts ──────────────────────────────────────────────────────────

class AnomalyAlert(BaseModel):
    """Anomaly detection alert."""
    alert_id: str = Field(..., description="Unique alert identifier")
    timestamp: datetime = Field(default_factory=lambda: datetime.now())
    machine_id: str = Field(..., description="Machine that triggered the alert")
    alert_type: AlertType = Field(..., description="Type of anomaly detected")
    severity: AlertSeverity = Field(..., description="Severity level")
    value: float = Field(..., description="Observed value that triggered the alert")
    threshold: float = Field(default=0.0, description="Threshold that was exceeded")
    message: str = Field(default="", description="Human-readable alert message")
    failure_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)


# ─── Machine State ───────────────────────────────────────────────────────────

class MachineState(BaseModel):
    """Latest state of a machine."""
    machine_id: str
    last_seen: datetime
    status: MachineStatus
    energy_kwh: float
    water_liters: float
    vibration: float
    temperature: float
    failure_flag: bool
    failure_risk_score: float
    active_alerts: int = 0


class MachineStateResponse(BaseModel):
    """Response for GET /machines/latest."""
    machines: list[MachineState] = Field(default_factory=list)
    total: int = 0


# ─── History ─────────────────────────────────────────────────────────────────

class HistoryQuery(BaseModel):
    """Query parameters for machine history."""
    start: Optional[datetime] = None
    end: Optional[datetime] = None
    limit: int = Field(default=100, ge=1, le=10000)


class HistoryResponse(BaseModel):
    """Response for GET /machines/{id}/history."""
    machine_id: str
    records: list[MachineTelemetry] = Field(default_factory=list)
    total: int = 0


# ─── Health ──────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "healthy"
    agent: str = "agent-data-iot"
    redis_connected: bool = False
    influxdb_connected: bool = False
    mqtt_connected: bool = False
    active_simulations: int = 0
    uptime_seconds: float = 0.0


# ─── Alerts List ─────────────────────────────────────────────────────────────

class AlertsResponse(BaseModel):
    """Response for GET /alerts."""
    alerts: list[AnomalyAlert] = Field(default_factory=list)
    total: int = 0


# ─── Agent Request / Response (inter-agent) ──────────────────────────────────

class AgentRequest(BaseModel):
    session_id: str = ""
    tenant_id: str = ""
    source_agent: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    message_signature: str = ""


class AgentResponse(BaseModel):
    session_id: str = ""
    agent_id: str = ""
    status: str = "success"
    payload: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.now)
    message_signature: str = ""


# Forward reference resolution
IngestResponse.model_rebuild()
