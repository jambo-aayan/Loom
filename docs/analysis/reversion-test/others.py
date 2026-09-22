"""The three never-measured strategies, scored the same way as the two dip rules.

Entry rules transcribed from the SHIPPED CODE (not from any ADR), so unlike measure.py
these are what the classes actually compute:

  trend_golden   _golden_cross(closes,50,200)          trend_follower.py:46
  trend_break    closes[-1] > max(closes[-21:-1])      trend_follower.py:68
  trend_any      golden OR breakout  (the real entry)  trend_follower.py:117-119
  squeeze_break  prev_w <= low*1.05 and <= mean*0.5
                 and close > prev_upper_band           volatility_breakout.py:117-125
  value_dip      (200d avg - close)/200d avg >= 0.08   value_quality_dip_buyer.py:109-111
                 PRICE HALF ONLY -- the P/E / yield / debt gate cannot be applied to ETFs.

CAVEAT: measured on 22 GBP index ETFs, which is NOT these strategies' intended universe
(they are designed for individual stocks). Indicative, not conclusive.
"""
import sys, statistics, random
from collections import defaultdict
sys.path.insert(0,'/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS

def sma(c,i,w): return sum(c[i-w+1:i+1])/w

def golden(c,i):
    if i < 200: return False
    return sma(c,i-1,50) <= sma(c,i-1,200) and sma(c,i,50) > sma(c,i,200)

def nday_high(c,i,w=20):
    if i < w: return False
    return c[i] > max(c[i-w:i])

def bandw(c,i,w=20,k=2.0):
    seg=c[i-w+1:i+1]; m=statistics.fmean(seg); sd=statistics.pstdev(seg)
    return ((m+k*sd)-(m-k*sd))/m if m else 0.0, m+k*sd

def squeeze(c,i,w=20,k=2.0,lb=60):
    if i < w+lb: return False
    widths=[bandw(c,j,w,k)[0] for j in range(i-lb+1,i+1)]
    if len(widths)<2: return False
    prev_w=widths[-2]; low=min(widths); mean_w=statistics.fmean(widths)
    if not (prev_w <= low*1.05 and prev_w <= mean_w*0.5): return False
    return c[i] > bandw(c,i-1,w,k)[1]

def value_dip(c,i,w=200,thr=0.08):
    if i < w: return False
    a=sma(c,i,w)
    return a>0 and (a-c[i])/a >= thr

RULES={'trend_golden':(golden,200,180),'trend_break':(nday_high,21,180),
       'trend_any':(lambda c,i: golden(c,i) or nday_high(c,i),200,180),
       'squeeze_break':(squeeze,81,45),'value_dip':(value_dip,200,60)}
HZ=[10,45,60,180]

def boot(cond,base,draws=3000,seed=31):
    keys=sorted(set(cond)|set(base)); rng=random.Random(seed); out=[]
    if len(keys)<3: return None
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        cv=[v for k in pick for v in cond.get(k,[])]; bv=[v for k in pick for v in base.get(k,[])]
        if cv and bv: out.append(statistics.fmean(cv)-statistics.fmean(bv))
    out.sort(); return out[int(.025*len(out))], out[int(.975*len(out))]

P=lambda x:f"{x*100:+.2f}%"


def main():
    h=load('real',TICKERS,'2018-01-01','2026-09-22')
    print("Entry rules transcribed from SHIPPED CODE, scored on 22 GBP ETFs, 2018-2026.")
    print("Entry at the NEXT OPEN (what a scheduled pass can do). Edge = conditional mean")
    print("forward return minus the mean over EVERY eligible day in the same instrument+year.\n")
    for name,(fn,warm,native) in RULES.items():
        print(f"═══ {name}   (native time exit {native}d) ═══")
        for hz in HZ:
            cond=defaultdict(list); base=defaultdict(list)
            for t,hh in h.items():
                b=hh.bars; c=[x.close for x in b]; o=[x.open for x in b]; d=[x.date for x in b]
                for i in range(warm, len(c)-hz-1):
                    e=i+1; px=o[e]
                    if px<=0: continue
                    k=(t,int(d[e][:4])); r=(c[e+hz]-px)/px
                    base[k].append(r)
                    if fn(c,i): cond[k].append(r)
            n=sum(len(v) for v in cond.values()); nb=sum(len(v) for v in base.values())
            if n<20: print(f"  {hz:4d}d  n={n:5d}  too few entries to measure"); continue
            cv=[v for vs in cond.values() for v in vs]; bv=[v for vs in base.values() for v in vs]
            edge=statistics.fmean(cv)-statistics.fmean(bv); ci=boot(cond,base)
            wins=sum(1 for v in cv if v>0)/len(cv)
            star=' <-- EXCLUDES ZERO' if ci and (ci[0]>0 or ci[1]<0) else ''
            print(f"  {hz:4d}d  n={n:5d} ({n/nb*100:4.1f}% of days)  cond {P(statistics.fmean(cv)):>8s}"
                  f"  base {P(statistics.fmean(bv)):>8s}  EDGE {P(edge):>8s}"
                  + (f"  [{P(ci[0])}, {P(ci[1])}]" if ci else "") + f"  win {wins*100:4.1f}%{star}")
        print()


if __name__ == "__main__":
    main()
