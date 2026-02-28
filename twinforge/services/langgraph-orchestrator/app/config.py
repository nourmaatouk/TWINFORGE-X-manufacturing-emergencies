from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    AGENT_NAME: str = "langgraph-orchestrator"
    AGENT_ID: str = "orchestrator"
    PORT: int = 8000
    REDIS_URL: str = "redis://localhost:6379"
    AGENT_1_URL: str = "http://agent-conversation:8001"
    AGENT_2_URL: str = "http://agent-orchestrator:8002"
    AGENT_3_URL: str = "http://agent-data-iot:8003"
    AGENT_4_URL: str = "http://agent-verifier:8004"
    AGENT_5_URL: str = "http://agent-security:8005"
    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""
    CLAUDE_API_KEY: str = ""
    MESSAGE_SIGNING_KEY: str = ""
    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
