import sys, statistics, random
from collections import defaultdict
sys.path.insert(0, '/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS
from measure import scan, baseline, ROUND_TRIP_COST

def cells_of(events, key=lambda e: (e.instrument, e.year)):
    d = defaultdict(list)
    for e in events: d[key(e)].append(e)
    return d

def boot_diff(deep, steady, draws=4000, seed=11):
    """Block bootstrap of (Deep mean fwd - Steady mean fwd), resampling whole
    (instrument, year) cells jointly so the two rules are resampled on the SAME blocks."""
    dc, sc = cells_of(deep), cells_of(steady)
    keys = sorted(set(dc) | set(sc))
    rng = random.Random(seed); out=[]
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        dv=[e.fwd for k in pick for e in dc.get(k,[])]
        sv=[e.fwd for k in pick for e in sc.get(k,[])]
        if dv and sv: out.append(statistics.fmean(dv)-statistics.fmean(sv))
    out.sort()
    return out[int(.025*len(out))], out[int(.975*len(out))]

def boot_mean(events, field, draws=4000, seed=13):
    c = cells_of(events); keys=list(c)
    if len(keys)<3: return None
    rng=random.Random(seed); out=[]
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        v=[getattr(e,field) for k in pick for e in c[k]]
        if v: out.append(statistics.fmean(v))
    out.sort()
    return out[int(.025*len(out))], out[int(.975*len(out))]

def edge_excl(events, base_cells, drop_years):
    ev=[e for e in events if e.year not in drop_years]
    bs=[v for (t,y),vs in base_cells.items() if y not in drop_years for v in vs]
    if not ev or not bs: return None
    return statistics.fmean([e.fwd for e in ev])-statistics.fmean(bs), len(ev)

P=lambda x: f"{x*100:+.2f}%"

for source in ['real','null-drift','null-zero','reverting']:
    for lag in ([0,1] if source=='real' else [0]):
        h=load(source,TICKERS,'2018-01-01','2026-09-22')
        base_cells=defaultdict(list)
        for t,hh in h.items():
            for y,f in baseline(t,hh.bars,lag=lag): base_cells[(t,y)].append(f)
        ev={r:[e for t,hh in h.items() for e in scan(t,hh.bars,r,lag=lag)] for r in ('steady','deep')}
        print(f"\n===== {source}  lag={lag} =====")
        for r in ('steady','deep'):
            E=ev[r]; tr=[e.trade_return for e in E]
            wins=[x for x in tr if x>0]; losses=[x for x in tr if x<=0]
            tp=[e.target_pct for e in E]
            ci=boot_mean(E,'trade_return')
            print(f" {r:7s} n={len(E):5d}  target mean {P(statistics.fmean(tp))} median {P(statistics.median(tp))}"
                  f"  -> CEILING {statistics.fmean(tp)/ROUND_TRIP_COST:5.1f}x")
            print(f"         mean gross {P(statistics.fmean(tr))} ({statistics.fmean(tr)/ROUND_TRIP_COST:+.1f}x)"
                  + (f" CI [{P(ci[0])}, {P(ci[1])}] = [{ci[0]/ROUND_TRIP_COST:.1f}x, {ci[1]/ROUND_TRIP_COST:.1f}x]" if ci else ""))
            print(f"         typical WIN (median of winners) {P(statistics.median(wins))} = {statistics.median(wins)/ROUND_TRIP_COST:.1f}x"
                  f" | typical LOSS {P(statistics.median(losses)) if losses else 'n/a'}"
                  f" | win rate {len(wins)/len(E)*100:.1f}%")
            for drop,lab in (((2020,),'ex-2020'),((2022,),'ex-2022'),((2020,2022),'ex-2020&22')):
                r2=edge_excl(E,base_cells,set(drop))
                if r2: print(f"         edge {lab:11s} {P(r2[0])}  (n={r2[1]})")
        d,s=ev['deep'],ev['steady']
        lo,hi=boot_diff(d,s)
        diff=statistics.fmean([e.fwd for e in d])-statistics.fmean([e.fwd for e in s])
        print(f" DEEP - STEADY  {P(diff)}   95% CI [{P(lo)}, {P(hi)}]   "
              f"{'EXCLUDES zero' if lo>0 or hi<0 else 'includes zero'}")
