from loom.risk import RiskLimits, daily_loss_breached, size_and_check
from loom.strategy import AccountState, ExitPlan, PositionSnapshot, ProposedSignal


def _signal(**overrides):
    defaults = dict(
        instrument="VUSA.L",
        signal_type="entry",
        action="buy",
        confidence=0.8,
        exit_plan=ExitPlan(profit_target_pct=0.04, stop_loss_pct=0.02),
        reference_price=100.0,
        quantity_hint=50,
    )
    defaults.update(overrides)
    return ProposedSignal(**defaults)


def test_approves_and_sizes_within_limits():
    account = AccountState(cash=10_000)
    decision = size_and_check(_signal(), account, account_value=10_000, limits=RiskLimits())
    assert decision.approved
    assert decision.sized_order.quantity * decision.sized_order.reference_price <= 10_000 * 0.15


def test_caps_position_size_at_max_position_pct():
    account = AccountState(cash=100_000)
    decision = size_and_check(
        _signal(quantity_hint=10_000), account, account_value=100_000, limits=RiskLimits(max_position_size_pct=0.1)
    )
    assert decision.approved
    assert decision.sized_order.quantity * decision.sized_order.reference_price <= 100_000 * 0.1 + 1e-6


def test_rejects_when_exposure_limit_leaves_no_headroom():
    account = AccountState(
        cash=1_000, positions=(PositionSnapshot("TSLA", 100, 100.0, book_id="b1"),)
    )
    decision = size_and_check(
        _signal(),
        account,
        account_value=10_000,
        limits=RiskLimits(max_total_exposure_pct=0.5, max_position_size_pct=0.9),
    )
    assert not decision.approved


def test_sell_signals_always_approved():
    account = AccountState(cash=1_000, positions=(PositionSnapshot("VUSA.L", 10, 100.0, book_id="b1"),))
    decision = size_and_check(_signal(action="sell"), account, account_value=1_000, limits=RiskLimits())
    assert decision.approved
    assert decision.sized_order.quantity == 10


def test_daily_loss_breach_detection():
    limits = RiskLimits(daily_loss_limit_pct=0.05)
    assert daily_loss_breached(10_000, 9_400, limits) is True
    assert daily_loss_breached(10_000, 9_600, limits) is False
