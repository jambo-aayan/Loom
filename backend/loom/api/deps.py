"""Dependency providers for the FastAPI service. Falls back to in-process fakes (FakeBrokerClient,
FixtureMarketDataSource) when no live Trading 212 / Twelve Data key is configured, so the API is
runnable in local dev without external credentials — ADR-0004's env-config secrets model means a
real deployment simply sets the env vars and these providers pick the real clients up instead."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from loom import db
from loom.execution.broker import BrokerClient, FakeBrokerClient
from loom.fundamentals import FundamentalsProvider
from loom.insight.generator import FakeInsightGenerator, InsightGenerator
from loom.market_data.base import MarketDataSource
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment
from loom.notifications.email import EmailSender
from loom.notifications.push import PushSender
from loom.settings import get_settings

_fake_brokers: dict[Environment, FakeBrokerClient] = {}


def get_db() -> Generator[Session, None, None]:
    yield from db.get_session()


def get_broker(environment: Environment = Environment.demo) -> BrokerClient:
    """T212's Practice (demo) mode and live mode are separate API systems with separate
    credentials (settings.py) — a key generated in one mode does not authenticate against the
    other's base URL, so both key+secret AND base_url vary together here, per environment."""
    settings = get_settings()
    is_demo = environment == Environment.demo
    api_key = settings.t212_demo_api_key if is_demo else settings.t212_live_api_key
    api_secret = settings.t212_demo_api_secret if is_demo else settings.t212_live_api_secret
    if api_key and api_secret:
        from loom.execution.t212_client import Trading212Client

        base_url = settings.t212_demo_base_url if is_demo else settings.t212_live_base_url
        return Trading212Client(base_url=base_url, api_key=api_key, api_secret=api_secret)

    if environment not in _fake_brokers:
        _fake_brokers[environment] = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    return _fake_brokers[environment]


def get_market_data_source() -> MarketDataSource:
    settings = get_settings()
    if settings.twelve_data_api_key:
        from loom.market_data.composite import PrimaryWithBackfillSource
        from loom.market_data.twelve_data import TwelveDataSource
        from loom.market_data.yfinance_source import YFinanceSource

        # Twelve Data primary (ADR-0008); yfinance is the backfill supplement (story 49) —
        # never the primary dependency on its own.
        return PrimaryWithBackfillSource(
            primary=TwelveDataSource(api_key=settings.twelve_data_api_key), backfill=YFinanceSource()
        )
    return FixtureMarketDataSource()


def get_screening_generator() -> InsightGenerator:
    """The screening tier only (#30) — split out from `get_insight_generator` (ADR-0016 update):
    screening fires on essentially every signal a strategy produces, by far the highest-volume
    Gemini caller in the app, so it gets its own model and therefore its own daily quota bucket
    (Google's free-tier RPD limits are tracked per model, not pooled across models within a
    project) rather than competing with position commentary/"ask"/research for one shared 20-500
    request/day allowance. Prefers Anthropic when configured, same fallback order as
    `get_insight_generator`."""
    settings = get_settings()
    if settings.anthropic_api_key:
        from loom.insight.generator import AnthropicInsightGenerator

        return AnthropicInsightGenerator(api_key=settings.anthropic_api_key)
    if settings.google_api_key:
        from loom.insight.generator import GeminiInsightGenerator

        return GeminiInsightGenerator(api_key=settings.google_api_key, model="gemini-3.5-flash-lite")
    return FakeInsightGenerator()


def get_insight_generator() -> InsightGenerator:
    """Position commentary (#44) and on-demand "ask" (#45) — low-volume, user-triggered calls,
    deliberately on a *different* Gemini model than the screening tier (see
    `get_screening_generator`) so the two don't share a daily quota bucket. Prefers Anthropic when
    configured, falls back to Gemini (ADR-0016: amends ADR-0013's original Anthropic-only design
    for this path, since a real Anthropic key was never actually provisioned in practice while a
    Google one already was), and only reaches the fake generator when neither is configured."""
    settings = get_settings()
    if settings.anthropic_api_key:
        from loom.insight.generator import AnthropicInsightGenerator

        return AnthropicInsightGenerator(api_key=settings.anthropic_api_key)
    if settings.google_api_key:
        from loom.insight.generator import GeminiInsightGenerator

        return GeminiInsightGenerator(api_key=settings.google_api_key, model="gemini-3.1-flash-lite")
    return FakeInsightGenerator()


def get_research_generator() -> InsightGenerator:
    """The research tier's automatic, free path (ADR-0013) — Gemini Flash when configured, else
    the fake generator. Never falls back to a paid provider automatically. Shares its model (and
    therefore its daily quota bucket) with `get_insight_generator` rather than screening: both are
    comparatively low-volume (research is gated to investment-style strategies only; ask is
    user-triggered), while screening alone can burn through a bucket fast on its own."""
    settings = get_settings()
    if settings.google_api_key:
        from loom.insight.generator import GeminiInsightGenerator

        return GeminiInsightGenerator(api_key=settings.google_api_key, model="gemini-3.1-flash-lite")
    return FakeInsightGenerator()


def get_paid_research_generator() -> InsightGenerator:
    """The research tier's manual-only, paid path (ADR-0013) — Claude Sonnet 5 when configured,
    else the fake generator. Reachable only from the explicit user-triggered endpoint; no other
    code in the codebase calls this."""
    settings = get_settings()
    if settings.anthropic_api_key:
        from loom.insight.generator import AnthropicInsightGenerator

        return AnthropicInsightGenerator(api_key=settings.anthropic_api_key, model="claude-sonnet-5")
    return FakeInsightGenerator()


def get_fundamentals_provider() -> FundamentalsProvider:
    """yfinance needs no API key (unlike Twelve Data/Trading 212/Anthropic), so this always
    returns the real source — callers (loom.fundamentals.safe_sector_for) wrap lookups so a
    network failure degrades to "sector unknown" rather than breaking the endpoint."""
    from loom.market_data.yfinance_source import YFinanceSource

    return YFinanceSource()


_fake_push_sender: PushSender | None = None
_fake_email_sender: EmailSender | None = None


def get_push_sender() -> PushSender:
    settings = get_settings()
    if settings.vapid_private_key:
        from loom.notifications.push import WebPushSender

        return WebPushSender(settings.vapid_private_key, settings.vapid_subject)

    global _fake_push_sender
    if _fake_push_sender is None:
        from loom.notifications.push import FakePushSender

        _fake_push_sender = FakePushSender()
    return _fake_push_sender


def get_email_sender() -> EmailSender:
    settings = get_settings()
    if settings.smtp_host:
        from loom.notifications.email import SmtpEmailSender

        return SmtpEmailSender(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.smtp_from_email,
        )

    global _fake_email_sender
    if _fake_email_sender is None:
        from loom.notifications.email import FakeEmailSender

        _fake_email_sender = FakeEmailSender()
    return _fake_email_sender
