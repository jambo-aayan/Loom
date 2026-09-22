"""Trade economics of the executable variant: Deep Dip, entry at the NEXT OPEN,
frozen target from information known at that moment (closes through the signal bar),
time exit at H days, no stop. Compared against the ADR 0021 geometry (10d)."""
import sys, statistics, random
from collections import defaultdict
sys.path.insert(0,'/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS
from measure import fires, _sma, SMA_LONG, SMA_SHORT, Z_WINDOW, ROUND_TRIP_COST
WARM=max(SMA_LONG,Z_WINDOW)

def trades(hists, rule, H, entry_at):
    cells=defaultdict(list)
    for t,h in hists.items():
        b=h.bars; c=[x.close for x in b]; o=[x.open for x in b]; hi=[x.high for x in b]; d=[x.date for x in b]
        for i in range(WARM-1, len(c)-H-2):
            if not fires(rule,c,i): continue
            if entry_at=='next_open': e,px,lvl = i+1, o[i+1], _sma(c,i,SMA_SHORT)
            elif entry_at=='next_close': e,px,lvl = i+1, c[i+1], _sma(c,i+1,SMA_SHORT)
            else: e,px,lvl = i, c[i], _sma(c,i,SMA_SHORT)
            if px<=0: continue
            tgt=(lvl-px)/px
            if tgt<=0: continue                      # nothing left to trade
            r=None
            for k in range(1,H+1):
                if c[e+k]>=lvl: r=tgt; break
            if r is None: r=(c[e+H]-px)/px
            cells[(t,int(d[e][:4]))].append((r,tgt))
    return cells

def boot(cells, draws=3000, seed=29):
    keys=sorted(cells); rng=random.Random(seed); out=[]
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        v=[r for k in pick for r,_ in cells[k]]
        if v: out.append(statistics.fmean(v))
    out.sort(); return out[int(.025*len(out))], out[int(.975*len(out))]

P=lambda x: f"{x*100:+.2f}%"
h=load('real',TICKERS,'2018-01-01','2026-09-22')
for rule in ('deep','steady'):
    print(f"\n===== {rule.upper()} DIP — mean gross per trade vs the 0.80% bar =====")
    print(f" {'entry':12s} {'hold':>5s} {'n':>6s} {'target':>8s} {'mean gross':>11s} {'xcost':>6s}  {'CI (xcost)':>18s} {'win':>6s} {'net':>8s}")
    for entry_at in ('signal_close','next_open','next_close'):
        for H in (3,5,10):
            cells=trades(h,rule,H,entry_at)
            tr=[r for v in cells.values() for r,_ in v]
            tg=[t for v in cells.values() for _,t in v]
            if not tr: continue
            m=statistics.fmean(tr); lo,hi=boot(cells)
            w=sum(1 for x in tr if x>0)/len(tr)
            print(f" {entry_at:12s} {H:4d}d {len(tr):6d} {P(statistics.fmean(tg)):>8s} {P(m):>11s} {m/ROUND_TRIP_COST:5.1f}x"
                  f"  [{lo/ROUND_TRIP_COST:5.1f}x,{hi/ROUND_TRIP_COST:5.1f}x] {w*100:5.1f}% {P(m-ROUND_TRIP_COST):>8s}")
