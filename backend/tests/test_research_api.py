import pytest
from fastapi.testclient import TestClient

from loom import db


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path}/research_test.db")
    monkeypatch.setattr("loom.api.deps._fake_brokers", {})
    from loom.api.main import app

    with TestClient(app) as c:
        yield c
    db._engine = None
    db._SessionLocal = None


def _dip_buyer_strategy_id(client):
    strategies = client.get("/strategies").json()
    return next(s["id"] for s in strategies if s["key"] == "value_quality_dip_buyer")


def _seed_eligible_signal(client, strategy_id):
    """Seeds a pending_approval Dip-Buyer signal directly — the real screen depends on live
    fundamentals data (yfinance), unavailable in this sandboxed test run, so this exercises the
    endpoint deterministically rather than hoping the real strategy fires."""
    from sqlalchemy import select

    from loom import db as db_module
    from loom.models import (
        Book,
        ConfigVersionStatus,
        Environment,
        Signal,
        SignalStatus,
        SignalType,
        StrategyConfigVersion,
    )
    from loom.models import Strategy as StrategyModel

    session = next(db_module.get_session())
    strategy = session.get(StrategyModel, strategy_id)
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=98, status=ConfigVersionStatus.draft, params={}
    )
    book = session.execute(select(Book).where(Book.strategy_id == strategy.id)).scalars().first()
    if book is None:
        book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Dip-Buyer · demo")
        session.add(book)
        session.flush()
    session.add(config)
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="AAPL",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=1,
        reference_price=100.0,
        status=SignalStatus.pending_approval,
    )
    session.add(signal)
    session.commit()
    return signal


def test_research_endpoint_generates_commentary_for_an_eligible_signal(client):
    strategy_id = _dip_buyer_strategy_id(client)
    signal = _seed_eligible_signal(client, strategy_id)

    resp = client.post(f"/signals/{signal.id}/research")

    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "research"
    assert body["signal_id"] == signal.id


def test_research_endpoint_404s_for_unknown_signal(client):
    resp = client.post("/signals/does-not-exist/research")
    assert resp.status_code == 404


def test_research_endpoint_rejects_a_trading_style_signal(client):
    # low_vol_compounder is trading-style — never eligible for research, automatic or manual.
    strategies = client.get("/strategies").json()
    compounder_id = next(s["id"] for s in strategies if s["key"] == "low_vol_compounder")
    client.patch(f"/strategies/{compounder_id}", json={"approval_mode": "auto"})
    client.post("/settings/auto-trading-gate/enable")

    signals = client.post("/trading-pass/run", params={"environment": "demo"}).json()
    compounder_signal = next((s for s in signals if s["strategy_id"] == compounder_id), None)
    if compounder_signal is None:
        pytest.skip("fixture data produced no Compounder signal this run")

    resp = client.post(f"/signals/{compounder_signal['id']}/research")

    assert resp.status_code == 400


def test_research_endpoint_rejects_a_not_yet_decided_signal(client):
    from sqlalchemy import select

    from loom import db as db_module
    from loom.models import (
        Book,
        ConfigVersionStatus,
        Environment,
        Signal,
        SignalStatus,
        SignalType,
        StrategyConfigVersion,
    )
    from loom.models import Strategy as StrategyModel

    session = next(db_module.get_session())
    strategy = session.get(StrategyModel, _dip_buyer_strategy_id(client))
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=99, status=ConfigVersionStatus.draft, params={}
    )
    book = session.execute(select(Book).where(Book.strategy_id == strategy.id)).scalars().first()
    if book is None:
        book = Book(strategy_id=strategy.id, environment=Environment.demo, name="Dip-Buyer · demo")
        session.add(book)
        session.flush()
    session.add(config)
    session.flush()
    signal = Signal(
        strategy_id=strategy.id,
        config_version_id=config.id,
        book_id=book.id,
        environment=Environment.demo,
        instrument="AAPL",
        signal_type=SignalType.entry,
        action="buy",
        confidence=0.9,
        exit_plan={"profit_target_pct": None, "stop_loss_pct": None, "time_exit_days": None},
        quantity=1,
        reference_price=100.0,
        status=SignalStatus.proposed,
    )
    session.add(signal)
    session.commit()

    resp = client.post(f"/signals/{signal.id}/research")

    assert resp.status_code == 400
