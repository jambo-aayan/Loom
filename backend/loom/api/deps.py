"""Dependency providers for the FastAPI service. Falls back to in-process fakes (FakeBrokerClient,
FixtureMarketDataSource) when no live Trading 212 / Twelve Data key is configured, so the API is
runnable in local dev without external credentials — ADR-0004's env-config secrets model means a
real deployment simply sets the env vars and these providers pick the real clients up instead."""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy.orm import Session

from loom import db
from loom.execution.broker import BrokerClient, FakeBrokerClient
from loom.insight.generator import FakeInsightGenerator, InsightGenerator
from loom.market_data.base import MarketDataSource
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import Environment
from loom.settings import get_settings

_fake_brokers: dict[Environment, FakeBrokerClient] = {}


def get_db() -> Generator[Session, None, None]:
    yield from db.get_session()


def get_broker(environment: Environment = Environment.demo) -> BrokerClient:
    settings = get_settings()
    key = settings.t212_demo_api_key if environment == Environment.demo else settings.t212_live_api_key
    if key:
        from loom.execution.t212_client import Trading212Client

        base_url = settings.t212_demo_base_url if environment == Environment.demo else settings.t212_live_base_url
        return Trading212Client(base_url=base_url, api_key=key)

    if environment not in _fake_brokers:
        _fake_brokers[environment] = FakeBrokerClient(starting_cash=10_000, fill_price=100.0)
    return _fake_brokers[environment]


def get_market_data_source() -> MarketDataSource:
    settings = get_settings()
    if settings.twelve_data_api_key:
        from loom.market_data.twelve_data import TwelveDataSource

        return TwelveDataSource(api_key=settings.twelve_data_api_key)
    return FixtureMarketDataSource()


def get_insight_generator() -> InsightGenerator:
    settings = get_settings()
    if settings.anthropic_api_key:
        from loom.insight.generator import AnthropicInsightGenerator

        return AnthropicInsightGenerator(api_key=settings.anthropic_api_key)
    return FakeInsightGenerator()
