from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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
    cors_origins: list[str] = []
    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
