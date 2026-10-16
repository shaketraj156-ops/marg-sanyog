from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/blockplanner"
    redis_url: str = "redis://localhost:6379/0"
    slot_minutes: int = 30
    max_block_minutes: int = 360
    cors_origins: list[str] = []
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
