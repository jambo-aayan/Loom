from sqlalchemy import select

from loom.execution.broker import BrokerPosition, FakeBrokerClient
from loom.market_data.fixture import FixtureMarketDataSource
from loom.models import (
    ApprovalMode,
    Book,
    ConfigVersionStatus,
    Environment,
    StrategyConfigVersion,
    StrategyStyle,
)
from loom.models import Strategy as StrategyModel
from loom.reconciliation import manual_positions
from loom.strategies.low_vol_compounder import DEFAULT_PARAMS
from loom.trading_pass import book_positions, get_or_create_book, run_trading_pass


def _seed_strategy(session):
    strategy = StrategyModel(
        key="low_vol_compounder",
        name="Low-Vol Compounder",
        style=StrategyStyle.trading,
        approval_mode=ApprovalMode.auto,
    )
    session.add(strategy)
    session.flush()
    config = StrategyConfigVersion(
        strategy_id=strategy.id, version_number=1, status=ConfigVersionStatus.promoted, params=dict(DEFAULT_PARAMS)
    )
    session.add(config)
    session.commit()
    return strategy


def test_a_position_the_broker_holds_but_no_book_accounts_for_is_manual(session):
    broker = FakeBrokerClient()
    broker.positions["AAPL"] = BrokerPosition(instrument="AAPL", quantity=10, average_price=150.0)

    manual = manual_positions(session, Environment.demo, broker)

    assert len(manual) == 1
    assert manual[0].instrument == "AAPL"
    assert manual[0].quantity == 10
    assert manual[0].average_price == 150.0


def test_a_position_fully_attributed_to_a_strategy_book_is_never_manual(session):
    _seed_strategy(session)
    source = FixtureMarketDataSource()
    signals = run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )
    executed = [s for s in signals if s.status.value == "executed"]
    assert executed  # sanity: auto-approval mode actually executed something

    books = session.execute(select(Book).where(Book.environment == Environment.demo)).scalars().all()
    broker = FakeBrokerClient()
    # Broker's own bookkeeping mirrors exactly what a strategy Book already claims.
    for book in books:
        for snap in book_positions(session, book.id):
            broker.positions[snap.instrument] = BrokerPosition(
                instrument=snap.instrument, quantity=snap.quantity, average_price=snap.average_price
            )

    manual = manual_positions(session, Environment.demo, broker)

    assert manual == ()


def test_only_the_untracked_portion_of_a_partially_owned_instrument_is_manual(session):
    _seed_strategy(session)
    source = FixtureMarketDataSource()
    run_trading_pass(
        Environment.demo, session, FakeBrokerClient(), source, universe=source.universe(), as_of="2023-08-01"
    )

    books = session.execute(select(Book).where(Book.environment == Environment.demo)).scalars().all()
    broker = FakeBrokerClient()
    strategy_snaps = []
    for book in books:
        for snap in book_positions(session, book.id):
            strategy_snaps.append(snap)
            # The live account holds 5 more shares of each instrument than any strategy Book
            # accounts for.
            broker.positions[snap.instrument] = BrokerPosition(
                instrument=snap.instrument, quantity=snap.quantity + 5, average_price=snap.average_price
            )
    assert strategy_snaps  # sanity: the trading pass actually opened at least one position

    manual = manual_positions(session, Environment.demo, broker)

    assert len(manual) == len(strategy_snaps)
    assert all(round(m.quantity, 6) == 5.0 for m in manual)
    assert {m.instrument for m in manual} == {s.instrument for s in strategy_snaps}


def test_reconciliation_is_idempotent(session):
    broker = FakeBrokerClient()
    broker.positions["TSLA"] = BrokerPosition(instrument="TSLA", quantity=3, average_price=200.0)

    first = manual_positions(session, Environment.demo, broker)
    second = manual_positions(session, Environment.demo, broker)

    assert first == second
    # Calling it doesn't create duplicate Manual Book rows.
    manual_books = session.execute(
        select(Book).where(Book.environment == Environment.demo, Book.strategy_id.is_(None))
    ).scalars().all()
    assert len(manual_books) <= 1


def test_get_or_create_manual_book_returns_a_stable_book(session):
    book1 = get_or_create_book(session, None, Environment.demo, "Manual")
    book2 = get_or_create_book(session, None, Environment.demo, "Manual")

    assert book1.id == book2.id
    assert book1.strategy_id is None
