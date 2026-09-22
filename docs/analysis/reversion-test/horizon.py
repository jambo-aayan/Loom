"""Where does the Deep Dip edge actually live -- in the hold, or in the first night?

Two questions run.py cannot answer:
  1. Edge as a function of holding horizon. Slow accumulation => genuine multi-day
     reversion. Front-loaded => the signal is about the close itself, and a 10-day
     hold is carrying risk for nothing.
  2. Entry at the NEXT DAY'S OPEN rather than the next close. ADR 0002's scheduled
     pass cannot trade the signal close, but an at-open pass is easy. If the edge
     survives to the open it is reachable; if not, it is an overnight effect.
"""
import sys, statistics, random
from collections import defaultdict
sys.path.insert(0,'/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS
from measure import fires, SMA_LONG, Z_WINDOW

HZ=[1,2,3,5,10,20]
WARM=max(SMA_LONG,Z_WINDOW)

def run(bars, rule, entry_at):
    """entry_at: 'signal_close' (lag0), 'next_close' (lag1), 'next_open'."""
    c=[b.close for b in bars]; o=[b.open for b in bars]; d=[b.date for b in bars]
    ev=defaultdict(list); base=defaultdict(list)
    for i in range(WARM-1, len(c)-max(HZ)-1):
        if entry_at=='signal_close': e, px = i, c[i]
        elif entry_at=='next_close': e, px = i+1, c[i+1]
        else:                        e, px = i+1, o[i+1]
        y=int(d[e][:4])
        row=[(c[e+h]-px)/px for h in HZ]
        base[(bars[0].date,y)].append(row)          # placeholder key, regrouped below
        if fires(rule,c,i): ev[y].append((row,d[e]))
    return ev

def edges(hists, rule, entry_at):
    cond=defaultdict(list); base=defaultdict(list)
    for t,h in hists.items():
        bars=h.bars; c=[b.close for b in bars]; o=[b.open for b in bars]; d=[b.date for b in bars]
        for i in range(WARM-1, len(c)-max(HZ)-1):
            if entry_at=='signal_close': e,px = i,c[i]
            elif entry_at=='next_close': e,px = i+1,c[i+1]
            else:                        e,px = i+1,o[i+1]
            if px<=0: continue
            k=(t,int(d[e][:4]))
            row=[(c[e+h]-px)/px for h in HZ]
            base[k].append(row)
            if fires(rule,c,i): cond[k].append(row)
    return cond, base

def boot(cond, base, j, draws=3000, seed=23):
    keys=sorted(set(cond)|set(base)); rng=random.Random(seed); out=[]
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        cv=[r[j] for k in pick for r in cond.get(k,[])]
        bv=[r[j] for k in pick for r in base.get(k,[])]
        if cv and bv: out.append(statistics.fmean(cv)-statistics.fmean(bv))
    out.sort(); return out[int(.025*len(out))], out[int(.975*len(out))]

P=lambda x: f"{x*100:+.2f}%"
h=load('real',TICKERS,'2018-01-01','2026-09-22')
for rule in ('deep','steady'):
    print(f"\n================ {rule.upper()} DIP ================")
    for entry_at,lab in (('signal_close','lag 0  (signal close — not executable)'),
                         ('next_open','lag 1  (NEXT OPEN — a pre-open pass could)'),
                         ('next_close','lag 1  (next close — today\'s convention)')):
        cond,base=edges(h,rule,entry_at)
        n=sum(len(v) for v in cond.values())
        print(f"\n {lab}   n={n:,}")
        print(f"   {'hold':>5s} {'cond':>9s} {'baseline':>9s} {'EDGE':>9s}  95% CI")
        for j,hz in enumerate(HZ):
            cv=[r[j] for v in cond.values() for r in v]
            bv=[r[j] for v in base.values() for r in v]
            e=statistics.fmean(cv)-statistics.fmean(bv)
            lo,hi=boot(cond,base,j)
            star=' <-- excludes zero' if lo>0 else ''
            print(f"   {hz:4d}d {P(statistics.fmean(cv)):>9s} {P(statistics.fmean(bv)):>9s} {P(e):>9s}  [{P(lo)}, {P(hi)}]{star}")
