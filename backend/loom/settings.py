"""Env-based configuration. Secrets never live in the DB or hardcoded (ADR-0004)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./loom_dev.db"

    # T212's API uses HTTP Basic Auth: the API key as username, the API secret as password. T212's
    # Practice (demo) mode runs a genuinely separate API/account system from live — a key
    # generated while switched to Practice mode only ever authenticates against
    # demo.trading212.com, and a key generated in live mode only against live.trading212.com; they
    # are not interchangeable (confirmed the hard way: a fully-permissioned live-mode key 401s on
    # every demo endpoint no matter the auth method). So, unlike an earlier assumption in this
    # repo's history, there IS a separate credential per environment — generate one from each mode
    # in the T212 app.
    t212_demo_api_key: str = ""
    t212_demo_api_secret: str = ""
    t212_live_api_key: str = ""
    t212_live_api_secret: str = ""
    t212_demo_base_url: str = "https://demo.trading212.com/api/v0"
    t212_live_base_url: str = "https://live.trading212.com/api/v0"

    twelve_data_api_key: str = ""
    anthropic_api_key: str = ""

    # The research tier's free-automatic provider (ADR-0013). Empty -> FakeInsightGenerator;
    # never falls back to a paid provider automatically.
    google_api_key: str = ""

    api_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:3000"

    # Web Push (story 60/62/63, ADR-0012). Empty by default -> FakePushSender (no-op, logs only).
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_subject: str = "mailto:aayan@example.com"

    # Email (story 58/64, ADR-0012). Empty smtp_host -> FakeEmailSender (no-op, logs only).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "loom@example.com"

    # Where notification emails are sent — single-user v1, so one address (ADR-0004: no user
    # table, no per-recipient config yet).
    notify_email: str = "aayan@example.com"


def get_settings() -> Settings:
    return Settings()
