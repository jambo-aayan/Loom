from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from loom.api.deps import get_db, get_market_data_source
from loom.api.schemas import (
    BacktestOut,
    ConfigVersionOut,
    DraftBacktestCompareRequest,
    DraftConfigVersionIn,
    StrategyOut,
    StrategyUpdate,
)
from loom.backtest.engine import run_backtest
from loom.config_versions import create_draft, current_promoted, diff_params, promote
from loom.market_data.base import MarketDataSource
from loom.models import (
    BacktestRun,
    Environment,
    Order,
    OrderStatus,
    Signal,
    StrategyConfigVersion,
)
from loom.models import Strategy as StrategyModel
from loom.trading_pass import STRATEGY_REGISTRY, get_or_create_book

router = APIRouter(prefix="/strategies", tags=["strategies"])


@router.get("", response_model=list[StrategyOut])
def list_strategies(session: Session = Depends(get_db)):
    return session.execute(select(StrategyModel)).scalars().all()


@router.get("/{strategy_id}", response_model=StrategyOut)
def get_strategy(strategy_id: str, session: Session = Depends(get_db)):
    strategy = session.get(StrategyModel, strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy not found")
    return strategy


@router.patch("/{strategy_id}", response_model=StrategyOut)
def update_strategy(strategy_id: str, body: StrategyUpdate, session: Session = Depends(get_db)):
    strategy = session.get(StrategyModel, strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(strategy, field, value)
    session.commit()
    return strategy


@router.get("/{strategy_id}/config-versions", response_model=list[ConfigVersionOut])
def list_config_versions(strategy_id: str, session: Session = Depends(get_db)):
    return (
        session.execute(
            select(StrategyConfigVersion)
            .where(StrategyConfigVersion.strategy_id == strategy_id)
            .order_by(StrategyConfigVersion.created_at)
        )
        .scalars()
        .all()
    )


@router.post("/{strategy_id}/config-versions", response_model=ConfigVersionOut)
def create_config_draft(strategy_id: str, body: DraftConfigVersionIn, session: Session = Depends(get_db)):
    strategy = session.get(StrategyModel, strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy not found")
    return create_draft(session, strategy_id, body.params, body.note)


@router.post("/{strategy_id}/config-versions/{version_id}/promote", response_model=ConfigVersionOut)
def promote_config_version(strategy_id: str, version_id: str, session: Session = Depends(get_db)):
    version = session.get(StrategyConfigVersion, version_id)
    if version is None or version.strategy_id != strategy_id:
        raise HTTPException(404, "config version not found")
    return promote(session, version)


@router.get("/{strategy_id}/trades")
def strategy_trade_log(strategy_id: str, environment: str = "demo", session: Session = Depends(get_db)):
    """Every real trade this strategy has made (story 75) plus a live cumulative-return series
    (story 76), computed from filled Orders — not a backtest chart."""
    strategy = session.get(StrategyModel, strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy not found")

    env = Environment(environment)
    book = get_or_create_book(session, strategy_id, env, f"{strategy.name} · {environment}")
    orders = (
        session.execute(
            select(Order).where(Order.book_id == book.id, Order.status == OrderStatus.filled).order_by(Order.filled_at)
        )
        .scalars()
        .all()
    )

    trades = []
    cumulative_return = 0.0
    curve = []
    for order in orders:
        signal = session.get(Signal, order.signal_id)
        trades.append(
            {
                "order_id": order.id,
                "instrument": signal.instrument if signal else None,
                "action": signal.action if signal else None,
                "quantity": order.quantity,
                "fill_price": order.fill_price,
                "filled_at": order.filled_at,
            }
        )
        if signal and signal.action == "sell" and order.fill_price:
            # crude realized-return proxy per fill; a full FIFO cost-basis ledger is a natural
            # M2 deepening once volume grows past a single-book strategy.
            cumulative_return += (order.fill_price - signal.reference_price) / signal.reference_price
        filled_at = order.filled_at.isoformat() if order.filled_at else None
        curve.append({"date": filled_at, "cumulative_return": cumulative_return})

    return {"trades": trades, "equity_curve": curve}


@router.post("/{strategy_id}/draft-backtest")
def draft_backtest_and_compare(
    strategy_id: str,
    body: DraftBacktestCompareRequest,
    session: Session = Depends(get_db),
    source: MarketDataSource = Depends(get_market_data_source),
):
    """Backtest a not-yet-committed parameter change before it becomes the strategy's official
    config version (story 78), and show the literal diff against the current promoted version
    (story 77)."""
    strategy = session.get(StrategyModel, strategy_id)
    if strategy is None:
        raise HTTPException(404, "strategy not found")
    strategy_cls = STRATEGY_REGISTRY.get(strategy.key)
    if strategy_cls is None:
        raise HTTPException(400, f"no strategy implementation registered for key={strategy.key!r}")

    result = run_backtest(
        strategy=strategy_cls.from_config(body.draft_params),
        source=source,
        universe=body.universe,
        start=body.start,
        end=body.end,
        starting_capital=body.starting_capital,
    )

    current = current_promoted(session, strategy_id)
    param_diff = diff_params(current.params if current else {}, body.draft_params)

    return {
        "backtest": result.as_dict(),
        "current_version_id": current.id if current else None,
        "param_diff": param_diff,
    }


@router.get("/backtests/{backtest_id}", response_model=BacktestOut, tags=["backtests"])
def get_backtest(backtest_id: str, session: Session = Depends(get_db)):
    run = session.get(BacktestRun, backtest_id)
    if run is None:
        raise HTTPException(404, "backtest run not found")
    return run
