"""Does short-horizon mean reversion exist in the dip strategies' universe?

Throwaway scratchpad analysis (CLAUDE.md working agreement) for ADR 0021 / ADR 0024.

Both dip entries are reproduced exactly as the production strategies compute them, including the
detail that every window *includes* the current bar (`closes[-window:]` in
loom/strategies/*.py) — measuring the rule as written, not a tidier version of it.

The one thing this adds that neither ADR had: an unconditional baseline. Under any process
without reversion, the expected forward return after *any* price-conditioned entry is just the
asset's drift over the holding window. So the question "does the bounce exist" is not "is the
average move positive" — on a rising asset it always will be — it is "is the average move after
a dip bigger than the average move after a randomly chosen day in the same asset and year".
Every conditional number below is reported against that baseline.
"""

from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass

HORIZON = 10          # trading days measured after entry (ADR 0021 time exit)
SMA_SHORT = 10        # Steady Dip reference level / frozen bounce target
SMA_LONG = 50         # shared trend filter
Z_WINDOW = 20         # Deep Dip z-score window
Z_ENTRY = -1.5        # Deep Dip entry threshold
ROUND_TRIP_COST = 0.0008   # 0.08%, the GBP-ETF cost base ADR 0021 is built on
COST_BAR_MULTIPLE = 10     # ADR 0019's promotion floor


@dataclass(frozen=True)
class Event:
    instrument: str
    date: str
    year: int
    rule: str
    entry: float
    sma_short: float          # frozen bounce target level
    target_pct: float         # distance to it, frozen at entry (ADR 0024)
    fwd: float                # raw close-to-close move over HORIZON
    recovered_close: bool     # a *close* reached the frozen target within HORIZON
    recovered_high: bool      # an intraday *high* reached it within HORIZON
    days_to_recover: int | None
    trade_return: float       # target if recovered, else the raw move at the time exit


def _sma(closes: list[float], i: int, window: int) -> float:
    return sum(closes[i - window + 1 : i + 1]) / window


def _zscore(closes: list[float], i: int, window: int) -> float | None:
    recent = closes[i - window + 1 : i + 1]
    sd = statistics.pstdev(recent)
    if sd == 0:
        return None
    return (closes[i] - statistics.fmean(recent)) / sd


def fires(rule: str, closes: list[float], i: int) -> bool:
    """The two entry rules, as the production strategies express them."""
    close = closes[i]
    above_trend = close > _sma(closes, i, SMA_LONG)
    if rule == "steady":
        return close < _sma(closes, i, SMA_SHORT) and above_trend
    if rule == "deep":
        z = _zscore(closes, i, Z_WINDOW)
        return z is not None and z <= Z_ENTRY and above_trend
    raise ValueError(rule)


def scan(instrument: str, bars, rule: str, lag: int = 0) -> list[Event]:
    """Every day `rule` fires, with the next HORIZON trading days measured.

    lag=0 enters at the signal bar's close (the convention the ADRs' simulation used).
    lag=1 enters at the next bar's close, which is what the real runtime can actually do.
    """
    closes = [b.close for b in bars]
    highs = [b.high for b in bars]
    dates = [b.date for b in bars]
    warmup = max(SMA_LONG, Z_WINDOW)
    events: list[Event] = []
    stale = 0

    for i in range(warmup - 1, len(closes) - HORIZON - lag):
        if not fires(rule, closes, i):
            continue
        e = i + lag                      # bar the position is opened on
        entry = closes[e]
        # ADR 0024 freezes the target "at entry", so the reference level is the one visible on
        # the bar the position actually opens on — not the signal bar. Identical when lag=0;
        # with a fill lag it matters, because the dislocation can close before we act.
        target_level = _sma(closes, e, SMA_SHORT)
        target_pct = (target_level - entry) / entry
        if target_pct <= 0:
            # Already back at (or above) the reference by the time we could fill: there is no
            # trade left to make. Counted, not silently folded into the win rate.
            stale += 1
            continue
        fwd = (closes[e + HORIZON] - entry) / entry

        days_to_recover = None
        recovered_high = False
        for k in range(1, HORIZON + 1):
            if not recovered_high and highs[e + k] >= target_level:
                recovered_high = True
            if closes[e + k] >= target_level:
                days_to_recover = k
                break

        recovered_close = days_to_recover is not None
        trade_return = target_pct if recovered_close else fwd

        events.append(
            Event(
                instrument=instrument,
                date=dates[e],
                year=int(dates[e][:4]),
                rule=rule,
                entry=entry,
                sma_short=target_level,
                target_pct=target_pct,
                fwd=fwd,
                recovered_close=recovered_close,
                recovered_high=recovered_high,
                days_to_recover=days_to_recover,
                trade_return=trade_return,
            )
        )
    scan.stale = getattr(scan, "stale", 0) + stale
    return events


def baseline(instrument: str, bars, lag: int = 0) -> list[tuple[int, float]]:
    """(year, HORIZON-day forward move) for *every* eligible day — the random-entry null.

    Same bar range and same entry convention as `scan`, so the comparison is like-for-like.
    """
    closes = [b.close for b in bars]
    dates = [b.date for b in bars]
    warmup = max(SMA_LONG, Z_WINDOW)
    out = []
    for i in range(warmup - 1, len(closes) - HORIZON - lag):
        e = i + lag
        out.append((int(dates[e][:4]), (closes[e + HORIZON] - closes[e]) / closes[e]))
    return out


def overlap_days(bars) -> tuple[int, int, int]:
    """(steady-only-ish count, deep count, days both rules fire) — ADR 0024's 3.2% claim."""
    closes = [b.close for b in bars]
    warmup = max(SMA_LONG, Z_WINDOW)
    s = d = both = 0
    for i in range(warmup - 1, len(closes)):
        fs, fd = fires("steady", closes, i), fires("deep", closes, i)
        s += fs
        d += fd
        both += fs and fd
    return s, d, both


# ---------------------------------------------------------------------------- summarising


def _pct(x: float) -> str:
    return f"{x * 100:+.2f}%"


def summarise(events: list[Event], base: list[float]) -> dict:
    if not events:
        return {"n": 0}
    fwd = [e.fwd for e in events]
    tr = [e.trade_return for e in events]
    net = [r - ROUND_TRIP_COST for r in tr]
    rec = [e for e in events if e.recovered_close]

    base_mean = statistics.fmean(base) if base else float("nan")
    base_win = (sum(1 for b in base if b > 0) / len(base)) if base else float("nan")

    return {
        "n": len(events),
        "fwd_mean": statistics.fmean(fwd),
        "fwd_median": statistics.median(fwd),
        "fwd_sd": statistics.pstdev(fwd) if len(fwd) > 1 else 0.0,
        "baseline_mean": base_mean,
        "edge": statistics.fmean(fwd) - base_mean,
        "recovery_rate": len(rec) / len(events),
        "recovery_rate_high": sum(1 for e in events if e.recovered_high) / len(events),
        "median_days_to_recover": statistics.median([e.days_to_recover for e in rec]) if rec else None,
        "target_pct_median": statistics.median([e.target_pct for e in events]),
        "trade_mean": statistics.fmean(tr),
        "trade_median": statistics.median(tr),
        "net_mean": statistics.fmean(net),
        "win_rate": sum(1 for r in tr if r > 0) / len(events),
        "net_win_rate": sum(1 for r in net if r > 0) / len(events),
        "baseline_win_rate": base_win,
        "cost_multiple": statistics.fmean(tr) / ROUND_TRIP_COST if ROUND_TRIP_COST else float("nan"),
    }


def block_bootstrap_edge(events: list[Event], base_by_cell: dict, draws: int = 2000, seed: int = 7):
    """95% interval for (conditional mean - baseline mean), resampling whole
    (instrument, year) cells. Dip days cluster hard in time and across funds that hold the same
    index, so an iid interval over individual events would be far too narrow.
    """
    cells: dict[tuple[str, int], list[float]] = {}
    for e in events:
        cells.setdefault((e.instrument, e.year), []).append(e.fwd)
    keys = list(cells)
    if len(keys) < 3:
        return None
    rng = random.Random(seed)
    edges = []
    for _ in range(draws):
        pick = [keys[rng.randrange(len(keys))] for _ in keys]
        cond = [v for k in pick for v in cells[k]]
        bs = [v for k in pick for v in base_by_cell.get(k, [])]
        if not cond or not bs:
            continue
        edges.append(statistics.fmean(cond) - statistics.fmean(bs))
    edges.sort()
    lo = edges[int(0.025 * len(edges))]
    hi = edges[int(0.975 * len(edges))]
    return lo, hi
