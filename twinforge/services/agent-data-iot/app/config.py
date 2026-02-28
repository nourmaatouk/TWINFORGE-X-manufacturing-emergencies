"""
TWINFORGE Agent 3 — Configuration
Pydantic Settings for agent-data-iot microservice.
All values configurable via environment variables.
"""

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Agent 3 configuration loaded from environment variables."""

    # ─── Service ──────────────────────────────────────────────────────────────
    SERVICE_NAME: str = "agent-data-iot"
    SERVICE_PORT: int = 8003
    LOG_LEVEL: str = "INFO"

    # ─── Redis ────────────────────────────────────────────────────────────────
    REDIS_URL: str = "redis://redis:6379"
    REDIS_TELEMETRY_CHANNEL: str = "telemetry:live"
    REDIS_ALERTS_CHANNEL: str = "telemetry:alerts"

    # ─── InfluxDB ─────────────────────────────────────────────────────────────
    INFLUXDB_URL: str = "http://localhost:8086"
    INFLUXDB_TOKEN: str = "my-super-secret-token"
    INFLUXDB_ORG: str = "twinforge"
    INFLUXDB_BUCKET: str = "twinforge_sensors"

    # ─── MQTT ─────────────────────────────────────────────────────────────────
    MQTT_BROKER_HOST: str = "mosquitto"
    MQTT_BROKER_PORT: int = 1883
    MQTT_TOPIC_TELEMETRY: str = "twinforge/telemetry/#"
    MQTT_TOPIC_PUBLISH: str = "twinforge/telemetry/live"
    MQTT_CLIENT_ID: str = "agent-data-iot"

    # ─── Security ─────────────────────────────────────────────────────────────
    MESSAGE_SIGNING_KEY: str = "default-signing-key"

    # ─── Observability ────────────────────────────────────────────────────────
    OTEL_ENDPOINT: str = "http://localhost:4317"

    # ─── Anomaly Detection Thresholds ─────────────────────────────────────────
    VIBRATION_THRESHOLD: float = 8.0
    TEMPERATURE_THRESHOLD: float = 95.0
    ENERGY_SPIKE_FACTOR: float = 2.0
    WATER_SPIKE_FACTOR: float = 2.5
    ROLLING_WINDOW_SIZE: int = 30
    DEVIATION_MULTIPLIER: float = 2.5

    # ─── Simulation Defaults ──────────────────────────────────────────────────
    DEFAULT_NUM_MACHINES: int = 5
    DEFAULT_SIMULATION_HOURS: float = 4.0
    DEFAULT_SAMPLING_INTERVAL: int = 5
    DEFAULT_ANOMALY_FREQUENCY: float = 0.05
    DEFAULT_PRODUCTION_INTENSITY: float = 0.7
    MAX_CONCURRENT_SIMULATIONS: int = 5

    # ─── Vault ────────────────────────────────────────────────────────────────
    VAULT_URL: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""

    # ─── Inter-Agent ──────────────────────────────────────────────────────────
    SECURITY_AGENT_URL: str = "http://agent-security:8005"
    AGENT_ID: str = "agent_3"

    model_config = {
        "env_prefix": "",
        "env_file": ".env",
        "case_sensitive": True,
        "extra": "ignore",
    }


# Singleton
settings = Settings()
