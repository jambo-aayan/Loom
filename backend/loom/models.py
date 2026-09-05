"""Domain models: Signal, Order, Position, Strategy, Book, Environment,
StrategyConfigVersion, kill-switch events (CONTEXT.md glossary; ADR-0003, ADR-0010, ADR-0011).

Every row carries a nullable `owner_id` scaffolding column for future multi-tenancy (story 73),
even though v1 is single-user.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.utcnow()


class Base(DeclarativeBase):
    pass


class Environment(str, enum.Enum):
    demo = "demo"
    live = "live"


class StrategyStyle(str, enum.Enum):
    trading = "trading"
    investment = "investment"


class ConfigVersionStatus(str, enum.Enum):
    draft = "draft"
    promoted = "promoted"


class ApprovalMode(str, enum.Enum):
    manual = "manual"
    auto_above_threshold = "auto_above_threshold"
    auto = "auto"


class SignalType(str, enum.Enum):
    entry = "entry"
    exit = "exit"


class SignalStatus(str, enum.Enum):
    proposed = "proposed"
    auto_approved = "auto_approved"
    pending_approval = "pending_approval"
    approved = "approved"
    rejected = "rejected"
    expired = "expired"
    executed = "executed"


class OrderStatus(str, enum.Enum):
    submitted = "submitted"
    filled = "filled"
    failed = "failed"


class InsightTier(str, enum.Enum):
    screening = "screening"
    research = "research"
    position = "position"  # advisory commentary about a held position, not a Signal (story 37)


class Strategy(Base):
    __tablename__ = "strategies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    owner_id: Mapped[str | None] = mapped_column(String, nullable=True)
    key: Mapped[str] = mapped_column(String, unique=True)
    name: Mapped[str] = mapped_column(String)
    style: Mapped[StrategyStyle] = mapped_column(Enum(StrategyStyle))
    live_enabled: Mapped[bool] = mapped_column(default=False)
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        Enum(ApprovalMode), default=ApprovalMode.manual
    )
    approval_threshold: Mapped[float] = mapped_column(Float, default=0.8)
    notify_threshold: Mapped[float] = mapped_column(Float, default=0.85)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    config_versions: Mapped[list[StrategyConfigVersion]] = relationship(
        back_populates="strategy", order_by="StrategyConfigVersion.created_at"
    )
    books: Mapped[list[Book]] = relationship(back_populates="strategy")


class StrategyConfigVersion(Base):
    """A strategy's parameters. Starts as a `draft`; promoting assigns its permanent
    `version_number` and makes it the strategy's current config (CONTEXT.md)."""

    __tablename__ = "strategy_config_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    version_number: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[ConfigVersionStatus] = mapped_column(
        Enum(ConfigVersionStatus), default=ConfigVersionStatus.draft
    )
    params: Mapped[dict] = mapped_column(JSON)
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    promoted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    strategy: Mapped[Strategy] = relationship(back_populates="config_versions")


class Book(Base):
    """A ledger bucket owning Position lots, scoped to one Environment (CONTEXT.md, ADR-0010).
    strategy_id is null for the `Manual` book of a given environment."""

    __tablename__ = "books"
    __table_args__ = (UniqueConstraint("strategy_id", "environment", name="uq_book_strategy_env"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy_id: Mapped[str | None] = mapped_column(ForeignKey("strategies.id"), nullable=True)
    environment: Mapped[Environment] = mapped_column(Enum(Environment))
    name: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    strategy: Mapped[Strategy | None] = relationship(back_populates="books")


class Signal(Base):
    """proposed -> (auto_approved|pending_approval) -> (approved|rejected|expired) -> executed.
    Retained permanently regardless of outcome (CONTEXT.md)."""

    __tablename__ = "signals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    config_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_config_versions.id"))
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"))
    environment: Mapped[Environment] = mapped_column(Enum(Environment))

    instrument: Mapped[str] = mapped_column(String)
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType))
    action: Mapped[str] = mapped_column(String)  # "buy" | "sell" | "add"
    confidence: Mapped[float] = mapped_column(Float)
    exit_plan: Mapped[dict] = mapped_column(JSON)  # {profit_target, stop_loss, time_exit_days}
    quantity: Mapped[float] = mapped_column(Float)
    reference_price: Mapped[float] = mapped_column(Float)

    status: Mapped[SignalStatus] = mapped_column(Enum(SignalStatus), default=SignalStatus.proposed)
    requires_manual_approval: Mapped[bool] = mapped_column(default=True)

    note: Mapped[str | None] = mapped_column(String, nullable=True)
    counterfactual_outcome: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    strategy: Mapped[Strategy] = relationship()
    orders: Mapped[list[Order]] = relationship(back_populates="signal")
    insights: Mapped[list[Insight]] = relationship(back_populates="signal")


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id"))
    book_id: Mapped[str] = mapped_column(ForeignKey("books.id"))
    environment: Mapped[Environment] = mapped_column(Enum(Environment))
    idempotency_key: Mapped[str] = mapped_column(String, unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[OrderStatus] = mapped_column(Enum(OrderStatus), default=OrderStatus.submitted)
    quantity: Mapped[float] = mapped_column(Float)
    fill_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    signal: Mapped[Signal] = relationship(back_populates="orders")


class KillSwitchEvent(Base):
    __tablename__ = "kill_switch_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    environment: Mapped[Environment] = mapped_column(Enum(Environment))
    triggered: Mapped[bool] = mapped_column()  # True = engaged, False = resumed
    actor: Mapped[str] = mapped_column(String, default="user")
    at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class Insight(Base):
    """Either signal-keyed (`signal_id` set — screening/research tiers, story 50/54) or
    position-keyed (`book_id` + `instrument` set, `signal_id` null — the `position` tier, story
    37: advisory commentary about any held position, including `Manual` and other strategies'
    Books, not just the bot's own proposed signals)."""

    __tablename__ = "insights"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    signal_id: Mapped[str | None] = mapped_column(ForeignKey("signals.id"), nullable=True)
    book_id: Mapped[str | None] = mapped_column(ForeignKey("books.id"), nullable=True)
    instrument: Mapped[str | None] = mapped_column(String, nullable=True)
    tier: Mapped[InsightTier] = mapped_column(Enum(InsightTier))
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)

    signal: Mapped[Signal | None] = relationship(back_populates="insights")


class BacktestRun(Base):
    __tablename__ = "backtest_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    config_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_config_versions.id"))
    name: Mapped[str] = mapped_column(String)
    universe: Mapped[list] = mapped_column(JSON)
    start_date: Mapped[str] = mapped_column(String)
    end_date: Mapped[str] = mapped_column(String)
    starting_capital: Mapped[float] = mapped_column(Float)
    results: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class ConfidenceCalibration(Base):
    """Confidence calibration buckets (story 20, ADR-0009, ticket #36): historical entry-type
    signals from a backtest run, bucketed by strength, each bucket's realized win rate/expectancy
    — the source a live entry-type signal's confidence is looked up from (loom.calibration)."""

    __tablename__ = "confidence_calibrations"
    __table_args__ = (UniqueConstraint("strategy_id", "config_version_id", name="uq_calibration_strategy_version"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    strategy_id: Mapped[str] = mapped_column(ForeignKey("strategies.id"))
    config_version_id: Mapped[str] = mapped_column(ForeignKey("strategy_config_versions.id"))
    buckets: Mapped[list] = mapped_column(JSON)  # [{min, max, win_rate, expectancy, num_trades}, ...]
    source_backtest_run_id: Mapped[str | None] = mapped_column(ForeignKey("backtest_runs.id"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class PushSubscription(Base):
    """A per-device Web Push subscription (story 60, ticket #39) — VAPID keys sign what Loom
    sends; the endpoint/keys here are what the browser's push service needs to route it."""

    __tablename__ = "push_subscriptions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    environment: Mapped[Environment] = mapped_column(Enum(Environment))
    endpoint: Mapped[str] = mapped_column(String, unique=True)
    p256dh: Mapped[str] = mapped_column(String)
    auth: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class SignedActionLink(Base):
    """A single-use, short-expiry email action link (story 64, ticket #41) — clicking it hits
    the same approve/reject path as the dashboard, re-checked server-side, no login required."""

    __tablename__ = "signed_action_links"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    token: Mapped[str] = mapped_column(String, unique=True)
    signal_id: Mapped[str] = mapped_column(ForeignKey("signals.id"))
    action: Mapped[str] = mapped_column(String)  # "approve" | "reject"
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)


class DailyAccountSnapshot(Base):
    """The account's total value at the start of a trading day, per Environment — the baseline
    `loom.risk.daily_loss_breached` compares the current value against (story 24, ADR-0011)."""

    __tablename__ = "daily_account_snapshots"
    __table_args__ = (UniqueConstraint("environment", "date", name="uq_snapshot_environment_date"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    environment: Mapped[Environment] = mapped_column(Enum(Environment))
    date: Mapped[str] = mapped_column(String)  # ISO date, "YYYY-MM-DD"
    starting_value: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
