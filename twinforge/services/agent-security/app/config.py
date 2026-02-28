from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    AGENT_NAME: str = "agent-security"
    AGENT_ID: str = "agent_5"
    PORT: int = 8005

    REDIS_URL: str = "redis://redis:6379"
    POSTGRES_URL: str = "postgresql://postgres:5432/twinforge_security"

    VAULT_ADDR: str = "http://localhost:8200"
    VAULT_TOKEN: str = ""

    CLAUDE_API_KEY: str = ""

    GITHUB_TOKEN: str = ""
    GITHUB_MODEL: str = "openai/o3"
    GITHUB_MODELS_ENDPOINT: str = "https://models.github.ai/inference/chat/completions"

    SECURITY_AGENT_URL: str = "http://agent-security:8005"
    MESSAGE_SIGNING_KEY: str = ""
    ALERT_WEBHOOK_URL: str = ""
    SLACK_WEBHOOK_URL: str = ""

    # Agent URLs for testing and I/O interception
    AGENT_URLS: str = "agent_1=http://agent-conversation:8001,agent_2=http://agent-orchestrator:8002,agent_3=http://agent-data-iot:8003,agent_4=http://agent-verifier:8004,langgraph=http://langgraph-orchestrator:8000"

    # Lockdown: restrict access to internal network only
    LOCKDOWN_ENABLED: bool = True
    INTERNAL_API_KEY: str = ""
    ALLOWED_IPS: str = "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16,::1"

    OTEL_EXPORTER_OTLP_ENDPOINT: str = "http://otel-collector:4317"

    class Config:
        env_file = ".env"


@lru_cache
def get_settings():
    return Settings()


settings = get_settings()
