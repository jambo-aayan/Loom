from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom import calibration
from loom.api.deps import get_db, get_market_data_source
from loom.api.schemas import BacktestOut, BacktestRequest
from loom.backtest.engine import run_backtest
from loom.config_versions import current_promoted
from loom.market_data.base import MarketDataSource
from loom.models import BacktestRun, StrategyConfigVersion
from loom.models import Strategy as StrategyModel
from loom.trading_pass import STRATEGY_REGISTRY

router = APIRouter(prefix="/backtests", tags=["backtests"])


@router.get("", response_model=list[BacktestOut])
def list_backtests(session: Session = Depends(get_db)):
    return session.execute(select(BacktestRun).order_by(BacktestRun.created_at.desc())).scalars().all()


@router.post("", response_model=BacktestOut)
def create_backtest(
    body: BacktestRequest,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    strategy = session.execute(select(StrategyModel).where(StrategyModel.key == body.strategy_key)).scalar_one_or_none()
    if strategy is None:
        raise HTTPException(404, f"strategy {body.strategy_key!r} not found")

    if body.config_version_id:
        version = session.get(StrategyConfigVersion, body.config_version_id)
    else:
        version = current_promoted(session, strategy.id)
    if version is None:
        raise HTTPException(400, "no config version available to backtest")

    strategy_cls = STRATEGY_REGISTRY.get(strategy.key)
    if strategy_cls is None:
        raise HTTPException(400, f"no strategy implementation registered for key={strategy.key!r}")

    result = run_backtest(
        strategy=strategy_cls.from_config(version.params),
        source=source,
        universe=body.universe,
        start=body.start,
        end=body.end,
        starting_capital=body.starting_capital,
    )

    run = BacktestRun(
        strategy_id=strategy.id,
        config_version_id=version.id,
        name=body.name or f"{strategy.name} {body.start}..{body.end}",
        universe=body.universe,
        start_date=body.start,
        end_date=body.end,
        starting_capital=body.starting_capital,
        results=result.as_dict(),
    )
    session.add(run)
    session.commit()

    calibration.save_calibration(session, strategy.id, version.id, result.trades, run.id)
    return run
