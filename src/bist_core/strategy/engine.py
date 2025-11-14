from typing import List
from ..models import EODBar, PriceBand
def round_to_tick(p: float, tick: float) -> float: return round(round(p/tick)*tick, 2)
def within_band(pc: float, p: float, up: float, dn: float)->bool: return pc*(1-dn/100) <= p <= pc*(1+up/100)
def decide(symbols: List[str], bars: List[EODBar], bands: List[PriceBand], kap_events, cfg, gates_cfg, strat_cfg):
    out, by = [], {}
    for b in bars: by.setdefault(b.symbol, []).append(b)
    for s in symbols:
        arr = sorted(by.get(s, []), key=lambda x: x.date)
        if not arr: continue
        last = arr[-1]
        band = next((b for b in bands if b.price_min <= last.close <= b.price_max), None)
        if not band:
            out.append({'symbol':s,'date':last.date.isoformat(),'last_close':last.close,'decision':'PASS','reason':'no_band','plan':None}); continue
        entry = round_to_tick(last.close*1.01, band.tick)
        stop  = round_to_tick(last.close*0.98, band.tick)
        t1    = round_to_tick(last.close*1.03, band.tick)
        ok = lambda px: within_band(last.close, px, band.up_limit_pct, band.down_limit_pct)
        if not (ok(entry) and ok(stop) and ok(t1)):
            out.append({'symbol':s,'date':last.date.isoformat(),'last_close':last.close,'decision':'PASS','reason':'band_violation','plan':None}); continue
        out.append({'symbol':s,'date':last.date.isoformat(),'last_close':last.close,'decision':'WATCH','plan':{'entry':entry,'stop':stop,'t1':t1}})
    return out
