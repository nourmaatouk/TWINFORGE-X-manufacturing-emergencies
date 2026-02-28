from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATASET_DIR: str = "/datasets"
    AGENT_DATA_IOT_URL: str = "http://agent-data-iot:8003"
    MQTT_BROKER: str = "mosquitto:1883"
    REPLAY_SPEED: float = 1.0
    REPLAY_INTERVAL_SEC: float = 2.0
    BATCH_SIZE: int = 5

    class Config:
        env_file = ".env"


settings = Settings()
