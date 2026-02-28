from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATASET_DIR: str = "/datasets"

    class Config:
        env_file = ".env"


settings = Settings()
