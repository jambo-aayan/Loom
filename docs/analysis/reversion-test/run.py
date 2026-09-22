"""Run the reversion test and print the report.

    python run.py --source real          # the production data stack
    python run.py --source null-drift    # control: random walk with drift, no reversion
    python run.py --source null-zero     # control: driftless random walk

Throwaway analysis. No production code, no ticket (CLAUDE.md working agreement).
"""

from __future__ import annotations

import argparse
import statistics
import sys
from collections import defaultdict

from measure import (
    COST_BAR_MULTIPLE,
    HORIZON,
    ROUND_TRIP_COST,
    baseline,
    block_bootstrap_edge,
    overlap_days,
    scan,
    summarise,
)
from sources import currency_of, load
from universe import FUND, TICKERS

RULES = {"steady": "Steady Dip (close < 10d avg, close > 50d avg)",
         "deep": f"Deep Dip (20d z <= -1.5, close > 50d avg)"}


def pct(x, places=2):
    if x is None or (isinstance(x, float) and x != x):
        return "  n/a "
    return f"{x * 100:+.{places}f}%"


def rate(x):
    if x is None or (isinstance(x, float) and x != x):
        return " n/a "
    return f"{x * 100:.1f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default="real", choices=["real", "null-drift", "null-zero", "reverting"])
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--end", default="2026-09-22")
    ap.add_argument("--lag", type=int, default=0, help="0 = enter at signal close (ADR convention); 1 = next close")
    ap.add_argument("--check-currency", action="store_true")
    args = ap.parse_args()

    print(f"\n{'='*92}")
    print(f"SHORT-HORIZON REVERSION TEST — source={args.source}  {args.start}..{args.end}  "
          f"horizon={HORIZON}d  lag={args.lag}")
    print(f"{'='*92}\n")

    print("Resolving universe:", file=sys.stderr)
    histories = load(args.source, TICKERS, args.start, args.end)

    if not histories:
        print("NO INSTRUMENTS RESOLVED — nothing to measure. See stderr for per-ticker reasons.")
        return 2

    print(f"{'ticker':9s} {'fund':36s} {'bars':>6s}  {'from':10s} {'to':10s}"
          + ("  currency" if args.check_currency else ""))
    print("-" * 92)
    for t, h in histories.items():
        line = f"{t:9s} {FUND.get(t,'?')[:36]:36s} {len(h.bars):6d}  {h.bars[0].date} {h.bars[-1].date}"
        if args.check_currency:
            cur = currency_of(t)
            flag = "" if cur in ("GBp", "GBP") else "   <-- NOT A GBP LINE"
            line += f"  {str(cur):8s}{flag}"
        print(line)
    missing = [t for t in TICKERS if t not in histories]
    if missing:
        print(f"\nunresolved ({len(missing)}): {', '.join(missing)}")
    print()

    # ---- baseline: every eligible day, by (instrument, year) -------------------------------
    base_cells: dict[tuple[str, int], list[float]] = defaultdict(list)
    for t, h in histories.items():
        for year, fwd in baseline(t, h.bars, lag=args.lag):
            base_cells[(t, year)].append(fwd)
    all_base = [v for vs in base_cells.values() for v in vs]

    print(f"RANDOM-ENTRY BASELINE (every eligible day, same bars, same {HORIZON}d horizon)")
    print(f"  n = {len(all_base):,}   mean {pct(statistics.fmean(all_base))}   "
          f"median {pct(statistics.median(all_base))}   "
          f"win rate {rate(sum(1 for b in all_base if b > 0)/len(all_base))}")
    print("  Any entry rule has to beat this. A positive average move after a dip is not an edge;")
    print("  it is what a rising asset does after every kind of day.\n")

    results = {}
    for rule, label in RULES.items():
        events = [e for t, h in histories.items() for e in scan(t, h.bars, rule, lag=args.lag)]
        results[rule] = events
        s = summarise(events, all_base)
        if not s["n"]:
            print(f"{label}\n  never fired.\n")
            continue
        ci = block_bootstrap_edge(events, base_cells)

        print(f"{label}")
        print(f"  entry days                 {s['n']:,}  = {s['n']/len(all_base)*100:.1f}% of all eligible days")
        print(f"  frozen target distance     {pct(s['target_pct_median'])} (median)")
        print(f"  --- raw {HORIZON}-day move after entry ---")
        print(f"  mean                       {pct(s['fwd_mean'])}      baseline {pct(s['baseline_mean'])}")
        print(f"  median                     {pct(s['fwd_median'])}")
        print(f"  EDGE over random entry     {pct(s['edge'])}"
              + (f"   95% CI [{pct(ci[0])}, {pct(ci[1])}]" if ci else ""))
        print(f"  --- the bounce itself ---")
        print(f"  recovered to 10d avg       {rate(s['recovery_rate'])} on a close, "
              f"{rate(s['recovery_rate_high'])} intraday")
        print(f"  median days to recover     {s['median_days_to_recover']}")
        print(f"  --- as a trade (frozen target, {HORIZON}d time exit, no stop) ---")
        print(f"  mean gross                 {pct(s['trade_mean'])}   = {s['cost_multiple']:.1f}x "
              f"the {ROUND_TRIP_COST*100:.2f}% round trip (ADR 0019 bar: {COST_BAR_MULTIPLE}x)")
        print(f"  median gross               {pct(s['trade_median'])}")
        print(f"  mean net of cost           {pct(s['net_mean'])}")
        print(f"  win rate gross / net       {rate(s['win_rate'])} / {rate(s['net_win_rate'])}"
              f"      (baseline {rate(s['baseline_win_rate'])})")
        print()

        # ---- by year -----------------------------------------------------------------------
        by_year = defaultdict(list)
        for e in events:
            by_year[e.year].append(e)
        print(f"  {'year':6s} {'n':>6s} {'mean':>9s} {'median':>9s} {'baseline':>9s} {'edge':>9s} "
              f"{'recov':>7s} {'win':>7s} {'net':>9s}")
        print("  " + "-" * 78)
        for year in sorted(by_year):
            ev = by_year[year]
            yb = [v for (t, y), vs in base_cells.items() if y == year for v in vs]
            ys = summarise(ev, yb)
            print(f"  {year:<6d} {ys['n']:6d} {pct(ys['fwd_mean']):>9s} {pct(ys['fwd_median']):>9s} "
                  f"{pct(ys['baseline_mean']):>9s} {pct(ys['edge']):>9s} "
                  f"{rate(ys['recovery_rate']):>7s} {rate(ys['win_rate']):>7s} {pct(ys['net_mean']):>9s}")
        print()

    # ---- overlap and the deep-vs-steady question -------------------------------------------
    tot_s = tot_d = tot_both = 0
    for t, h in histories.items():
        s_, d_, b_ = overlap_days(h.bars)
        tot_s += s_
        tot_d += d_
        tot_both += b_
    print("OVERLAP (ADR 0024 measured 3.2% of Deep Dip days as shared)")
    print(f"  steady days {tot_s:,}   deep days {tot_d:,}   both {tot_both:,}"
          + (f"  = {tot_both/tot_d*100:.1f}% of deep days" if tot_d else ""))
    print(f"  Deep Dip is {tot_s/tot_d:.1f}x rarer than Steady Dip\n" if tot_d else "\n")

    se, de = results.get("steady", []), results.get("deep", [])
    if se and de:
        sm, dm = statistics.fmean([e.fwd for e in se]), statistics.fmean([e.fwd for e in de])
        print("DEEP vs STEADY — ADR 0024's least-trusted finding")
        print(f"  Steady mean {HORIZON}d move  {pct(sm)}   ({len(se):,} entries)")
        print(f"  Deep   mean {HORIZON}d move  {pct(dm)}   ({len(de):,} entries)")
        print(f"  difference               {pct(dm - sm)}")
        print(f"  Deep recovery rate       {rate(sum(e.recovered_close for e in de)/len(de))}"
              f"   vs Steady {rate(sum(e.recovered_close for e in se)/len(se))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
