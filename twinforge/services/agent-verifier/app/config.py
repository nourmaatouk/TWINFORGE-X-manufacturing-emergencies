from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    AGENT_NAME: str = "agent-verifier"
    AGENT_ID: str = "agent_4"
    PORT: int = 8004

    REDIS_URL: str = "redis://redis:6379"
    POSTGRES_URL: str = "postgresql://postgres:5432/twinforge"
    INFLUX_URL: str = "http://influxdb:8086"

    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""

    CLAUDE_API_KEY: str = ""

    SECURITY_AGENT_URL: str = "http://agent-security:8005"
    MESSAGE_SIGNING_KEY: str = ""

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
