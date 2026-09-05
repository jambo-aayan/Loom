from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class StrategyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    key: str
    name: str
    style: str
    live_enabled: bool
    approval_mode: str
    approval_threshold: float
    notify_threshold: float


class StrategyUpdate(BaseModel):
    live_enabled: bool | None = None
    approval_mode: str | None = None
    approval_threshold: float | None = None
    notify_threshold: float | None = None


class ConfigVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    version_number: int | None
    status: str
    params: dict
    note: str | None
    created_at: datetime
    promoted_at: datetime | None


class DraftConfigVersionIn(BaseModel):
    params: dict
    note: str | None = None


class BacktestRequest(BaseModel):
    strategy_key: str
    config_version_id: str | None = None  # None => current promoted version
    universe: list[str]
    start: str
    end: str
    starting_capital: float = 10_000.0
    name: str | None = None


class BacktestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    strategy_id: str
    config_version_id: str
    name: str
    universe: list
    start_date: str
    end_date: str
    starting_capital: float
    results: dict
    created_at: datetime


class DraftBacktestCompareRequest(BaseModel):
    strategy_id: str
    draft_params: dict
    universe: list[str]
    start: str
    end: str
    starting_capital: float = 10_000.0


class SignalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    strategy_id: str
    book_id: str
    environment: str
    instrument: str
    signal_type: str
    action: str
    confidence: float
    exit_plan: dict
    quantity: float
    reference_price: float
    status: str
    requires_manual_approval: bool
    note: str | None
    counterfactual_outcome: dict | None
    created_at: datetime
    decided_at: datetime | None


class SignalDecisionIn(BaseModel):
    note: str | None = None


class InsightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    signal_id: str | None = None
    book_id: str | None = None
    instrument: str | None = None
    tier: str
    content: str
    created_at: datetime


class AskIn(BaseModel):
    question: str = Field(min_length=1)
    instrument: str | None = None


class PositionOut(BaseModel):
    book_id: str
    book_name: str
    strategy_key: str | None
    instrument: str
    quantity: float
    average_price: float


class OverviewOut(BaseModel):
    environment: str
    cash: float
    positions: list[PositionOut]


class KillSwitchOut(BaseModel):
    environment: str
    engaged: bool
