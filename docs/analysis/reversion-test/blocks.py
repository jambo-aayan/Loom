import sys, statistics, random
from collections import defaultdict
sys.path.insert(0,'/home/user/Loom/docs/analysis/reversion-test')
from sources import load
from universe import TICKERS
from measure import scan, baseline

# Duplicate index lines collapsed: these are not independent series.
GROUP = {}
for g, ts in {
 'sp500':['VUSA.L','VUAG.L','CSP1.L'],
 'world':['VWRL.L','VWRP.L','VEVE.L','SWLD.L','HMWO.L'],
 'uk100':['ISF.L','VUKE.L'], 'uk250':['VMID.L','MIDD.L'],
 'europe':['VERX.L'], 'japan':['VJPN.L'],
 'em':['VFEM.L','EMIM.L'], 'highdiv':['VHYL.L'], 'ukdiv':['IUKD.L'],
 'gilt':['IGLT.L','VGOV.L'], 'globalagg':['VAGP.L','AGBP.L'],
}.items():
    for t in ts: GROUP[t]=g

def boot(events, base_cells, keyfn, draws=4000, seed=17):
    ec=defaultdict(list); bc=defaultdict(list)
    for e in events: ec[keyfn(e.instrument,e.year)].append(e.fwd)
    for (t,y),vs in base_cells.items(): bc[keyfn(t,y)].extend(vs)
    keys=sorted(set(ec)|set(bc))
    if len(keys)<3: return None
    rng=random.Random(seed); out=[]
    for _ in range(draws):
        pick=[keys[rng.randrange(len(keys))] for _ in keys]
        c=[v for k in pick for v in ec.get(k,[])]
        b=[v for k in pick for v in bc.get(k,[])]
        if c and b: out.append(statistics.fmean(c)-statistics.fmean(b))
    out.sort(); return out[int(.025*len(out))], out[int(.975*len(out))], len(keys)

P=lambda x: f"{x*100:+.2f}%"
for lag in (0,1):
    h=load('real',TICKERS,'2018-01-01','2026-09-22')
    bc=defaultdict(list)
    for t,hh in h.items():
        for y,f in baseline(t,hh.bars,lag=lag): bc[(t,y)].append(f)
    allb=[v for vs in bc.values() for v in vs]
    print(f"\n--- real lag={lag} ---")
    for r in ('steady','deep'):
        E=[e for t,hh in h.items() for e in scan(t,hh.bars,r,lag=lag)]
        edge=statistics.fmean([e.fwd for e in E])-statistics.fmean(allb)
        print(f" {r:7s} edge {P(edge)}")
        for lab,kf in (('(instrument,year)',lambda t,y:(t,y)),
                       ('(group,year)     ',lambda t,y:(GROUP[t],y)),
                       ('year only        ',lambda t,y:y)):
            ci=boot(E,bc,kf)
            if ci: print(f"          blocks={lab} nblocks={ci[2]:3d}  95% CI [{P(ci[0])}, {P(ci[1])}]"
                         f"  {'EXCLUDES zero' if ci[0]>0 else 'includes zero'}")
