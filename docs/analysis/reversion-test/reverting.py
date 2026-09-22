"""Positive control: a generator that genuinely mean-reverts.

Needed to keep "no edge found" from being indistinguishable from "the harness is broken".
If the measurement machinery cannot see reversion here, where it is switched on by construction
and its strength is known, then its verdict on any other series is worthless.

Log price = a drifting anchor plus an AR(1) deviation. `phi` sets the half-life of a
dislocation: 0.90 is a ~6.6 trading-day half-life, comfortably inside a 10-day hold. This is the
same shape of process ADR 0021 and ADR 0024 simulated against — the point of running it is to
show what its numbers look like, not to treat them as evidence about real ETFs.
"""

from __future__ import annotations

import math
import random
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, "/home/user/Loom/backend")
from loom.strategy import Bar, InstrumentHistory  # noqa: E402

from universe import BUCKET, NULL_PROFILE, NULL_START_PRICE  # noqa: E402


def _business_days(start: date, end: date) -> list[date]:
    days, d = [], start
    while d <= end:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return days


class RevertingSource:
    def __init__(self, phi: float = 0.90, dislocation_share: float = 0.6):
        self.phi = phi
        # How much of each day's shock is transient (and will revert) rather than permanent.
        self.dislocation_share = dislocation_share

    def get_history(self, instrument: str, start: str, end: str) -> InstrumentHistory:
        bucket = BUCKET.get(instrument, "core")
        drift, vol = NULL_PROFILE[bucket]
        price0 = NULL_START_PRICE[bucket]
        rng = random.Random(f"revert:{instrument}:{start}:{end}")

        daily_drift = drift / 252
        daily_vol = vol / math.sqrt(252)
        # Split total variance into a permanent random walk and a transient AR(1) part, so the
        # series still has roughly `vol` overall rather than reverting *and* being louder.
        sd_perm = daily_vol * math.sqrt(1 - self.dislocation_share)
        sd_trans = daily_vol * math.sqrt(self.dislocation_share) * math.sqrt(1 - self.phi**2)

        bars, anchor, x, prev_close = [], math.log(price0), 0.0, None
        for d in _business_days(date.fromisoformat(start), date.fromisoformat(end)):
            anchor += daily_drift + rng.gauss(0, sd_perm)
            x = self.phi * x + rng.gauss(0, sd_trans)
            close = math.exp(anchor + x)
            open_ = prev_close if prev_close is not None else close
            high = max(open_, close) * (1 + abs(rng.gauss(0, daily_vol / 3)))
            low = min(open_, close) * (1 - abs(rng.gauss(0, daily_vol / 3)))
            bars.append(Bar(date=d.isoformat(), open=round(open_, 4), high=round(high, 4),
                            low=round(low, 4), close=round(close, 4), volume=rng.uniform(1e3, 1e5)))
            prev_close = close
        return InstrumentHistory(instrument=instrument, bars=tuple(bars))
