"""Env-based configuration. Secrets never live in the DB or hardcoded (ADR-0004)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./loom_dev.db"

    t212_demo_api_key: str = ""
    t212_live_api_key: str = ""
    t212_demo_base_url: str = "https://demo.trading212.com/api/v0"
    t212_live_base_url: str = "https://live.trading212.com/api/v0"

    twelve_data_api_key: str = ""
    anthropic_api_key: str = ""

    kill_switch_path: str = "./.loom_killswitch"

    api_base_url: str = "http://localhost:8000"


def get_settings() -> Settings:
    return Settings()
