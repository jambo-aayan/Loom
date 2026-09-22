"""Year decomposition for the three never-measured entry rules. A full-sample edge that is
one crisis wearing a strategy's clothes is not an edge."""
import sys, statistics, random
from collections import defaultdict
sys.path.insert(0,'/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS
from others import golden, nday_high, squeeze, value_dip, sma   # noqa

RULES={'trend_any':(lambda c,i: golden(c,i) or nday_high(c,i),200,60),
       'squeeze_break':(squeeze,81,45),
       'value_dip':(value_dip,200,60)}
P=lambda x:f"{x*100:+.2f}%"
h=load('real',TICKERS,'2018-01-01','2026-09-22')

def cells(fn,warm,hz):
    cond=defaultdict(list); base=defaultdict(list)
    for t,hh in h.items():
        b=hh.bars; c=[x.close for x in b]; o=[x.open for x in b]; d=[x.date for x in b]
        for i in range(warm,len(c)-hz-1):
            e=i+1; px=o[e]
            if px<=0: continue
            k=(t,int(d[e][:4])); r=(c[e+hz]-px)/px
            base[k].append(r)
            if fn(c,i): cond[k].append(r)
    return cond,base

def edge(cond,base,drop=()):
    cv=[v for (t,y),vs in cond.items() if y not in drop for v in vs]
    bv=[v for (t,y),vs in base.items() if y not in drop for v in vs]
    if not cv or not bv: return None,0
    return statistics.fmean(cv)-statistics.fmean(bv), len(cv)

for name,(fn,warm,hz) in RULES.items():
    cond,base=cells(fn,warm,hz)
    print(f"═══ {name}  (horizon {hz}d, next-open entry) ═══")
    print(f"  {'year':6s} {'n':>6s} {'cond':>9s} {'base':>9s} {'edge':>9s}")
    for y in sorted({y for _,y in base}):
        cv=[v for (t,yy),vs in cond.items() if yy==y for v in vs]
        bv=[v for (t,yy),vs in base.items() if yy==y for v in vs]
        if not bv: continue
        if not cv: print(f"  {y:<6d} {0:6d}        —        —        —"); continue
        print(f"  {y:<6d} {len(cv):6d} {P(statistics.fmean(cv)):>9s} {P(statistics.fmean(bv)):>9s} "
              f"{P(statistics.fmean(cv)-statistics.fmean(bv)):>9s}")
    for lab,drop in (('full',()),('ex-2020',(2020,)),('ex-2022',(2022,)),('ex-2020&22',(2020,2022))):
        e,n=edge(cond,base,drop)
        print(f"  {lab:12s} edge {P(e):>9s}  (n={n})")
    print()
