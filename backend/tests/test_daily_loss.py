from loom.daily_loss import check_daily_loss_limit
from loom.execution.broker import FakeBrokerClient
from loom.models import Environment
from loom.risk import RiskLimits


def test_first_check_of_the_day_establishes_the_baseline_and_never_breaches(session):
    broker = FakeBrokerClient(starting_cash=10_000)
    limits = RiskLimits(daily_loss_limit_pct=0.05)

    breached, loss_pct = check_daily_loss_limit(session, Environment.demo, broker, limits)

    assert breached is False
    assert loss_pct == 0.0


def test_a_later_check_the_same_day_compares_against_the_baseline(session):
    broker = FakeBrokerClient(starting_cash=10_000)
    limits = RiskLimits(daily_loss_limit_pct=0.05)
    check_daily_loss_limit(session, Environment.demo, broker, limits)

    broker.cash = 9_000  # a 10% drop since the baseline was set

    breached, loss_pct = check_daily_loss_limit(session, Environment.demo, broker, limits)

    assert breached is True
    assert round(loss_pct, 2) == 0.1


def test_a_small_loss_within_the_limit_does_not_breach(session):
    broker = FakeBrokerClient(starting_cash=10_000)
    limits = RiskLimits(daily_loss_limit_pct=0.05)
    check_daily_loss_limit(session, Environment.demo, broker, limits)

    broker.cash = 9_800  # a 2% drop

    breached, _ = check_daily_loss_limit(session, Environment.demo, broker, limits)

    assert breached is False


def test_environments_are_tracked_independently(session):
    demo_broker = FakeBrokerClient(starting_cash=10_000)
    live_broker = FakeBrokerClient(starting_cash=5_000)
    limits = RiskLimits(daily_loss_limit_pct=0.05)
    check_daily_loss_limit(session, Environment.demo, demo_broker)
    check_daily_loss_limit(session, Environment.live, live_broker)

    demo_broker.cash = 9_000
    breached_demo, _ = check_daily_loss_limit(session, Environment.demo, demo_broker, limits)
    breached_live, _ = check_daily_loss_limit(session, Environment.live, live_broker, limits)

    assert breached_demo is True
    assert breached_live is False
