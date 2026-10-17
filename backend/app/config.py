import json
from functools import lru_cache
from typing import Annotated

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://app:app@localhost:5432/blockplanner"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str  # no default: the app refuses to start without it
    access_token_minutes: int = 15
    refresh_token_days: int = 7
    slot_minutes: int = 30
    max_block_minutes: int = 360
    solver_workers: int = 0  # 0 means one per CPU core, at most 8
    crews_per_department: int = 2
    login_max_failures: int = 5  # failed logins for one email before it is locked out
    login_lockout_seconds: int = 900
    login_rate_limit_per_minute: int = 10  # login attempts per client address per minute
    model_dir: str = "models"  # where trained model files are saved
    ml_cost_enabled: bool = True  # use an active delay model for the cost, when one beats its baseline
    solver_isolation: bool = True  # run each solve in a child process so a native crash cannot kill the API
    # NoDecode: the value is read as plain text and split by the validator below, so a plain URL cannot
    # stop the app from starting (the JSON-list form is still accepted).
    cors_origins: Annotated[list[str], NoDecode] = []
    log_level: str = "INFO"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _read_cors_origins(cls, value: object) -> object:
        """Accept a JSON list, one URL, or several URLs separated by commas. A slash at the end is dropped,
        because a browser's Origin never has one and a trailing slash would never match."""
        if isinstance(value, str):
            text = value.strip()
            items = json.loads(text) if text.startswith("[") else text.split(",")
            return [str(item).strip().rstrip("/") for item in items if str(item).strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
