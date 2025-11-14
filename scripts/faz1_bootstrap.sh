#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

# Python yorumlayıcısını bul
PY="$(command -v python3 || command -v python)"

# Güvenlik: 'src' yanlışlıkla dosya ise yedekle, klasörü garanti et
[ -f src ] && mv src "src_file_backup_$(date +%s)" || true
mkdir -p src

echo "[1/3] Dosya ağacı ve örnek veriler…"
"$PY" - <<'PY'
import pathlib, json
root = pathlib.Path('.').resolve()

# Klasörler
for d in ['config','data/samples','src/bist_core/repositories','src/bist_core/strategy','tests']:
    p = root / d
    try:
        p.mkdir(parents=True, exist_ok=True)
    except FileExistsError:
        pass


def w_if_missing(rel, content):
    p = root / rel
    if not p.exists():
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
        except FileExistsError:
            pass
        p.write_text(content, encoding='utf-8')


# Paket işaretçileri
w_if_missing('src/__init__.py', "# package\n")
w_if_missing('src/bist_core/__init__.py', "# bist_core package\n")

# Konfig dosyaları
w_if_missing('config/core.json', json.dumps({
  "timezone":"Europe/Istanbul","default_spread_bps_max":80,
  "default_adv_tl_min":30000000,"default_auction_ratio_max":0.15,
  "default_price_band_pct":20.0,"risk_per_trade":0.015
}, indent=2, ensure_ascii=False))
w_if_missing('config/sources.json', json.dumps({
  "provider":"local_csv","local_csv":{"root_dir":"data/samples"},
  "vendor_api":{"enabled":False,"eod_endpoint":"","kap_endpoint":"","auth":{"api_key":""}}
}, indent=2, ensure_ascii=False))
w_if_missing('config/gates.json', json.dumps({
  "spread_bps_max":80,"auction_ratio_max":0.15,"adv_tl_min":30000000,
  "vbts_must_be":"NONE","data_freshness_days_max":2
}, indent=2, ensure_ascii=False))
w_if_missing('config/strategy.json', json.dumps({
  "mom_fast":5,"mom_slow":20,"vol_window":20,
  "kap_positive_keywords":["ihale","sözleşme","yeni iş","yatırım","kapasite","temettü"],
  "kap_negative_keywords":["iptal","durdur","fesih","soruşturma","tazminat","borç"],
  "kap_weight":1.0,"mom_weight":1.0,"vol_weight":0.5,
  "score_buy":1.5,"score_watch":0.5
}, indent=2, ensure_ascii=False))

# Örnek veriler
w_if_missing('data/samples/eod_prices.csv',
"""symbol,date,close,high,low,volume,turnover_tl
QNBFK,2025-11-08,72.00,72.50,71.50,340000,24400000
MEKAG,2025-11-08,5.59,5.64,5.55,405000,2280000
CMBTN,2025-11-08,2232.00,2246.00,2222.00,114000,255000000
""")
w_if_missing('data/samples/kap_events.csv',
"""symbol,ts_trt,title,body
QNBFK,2025-11-07 18:45:00,Yeni İş İlişkisi,Şirketimiz 12 ay süreli hizmet sözleşmesi imzalamıştır.
""")
w_if_missing('data/samples/price_bands.csv',
"""price_min,price_max,tick,up_limit_pct,down_limit_pct
0.01,19.999,0.01,20.0,20.0
20.00,49.999,0.02,20.0,20.0
50.00,99.999,0.05,20.0,20.0
100.00,249.999,0.10,20.0,20.0
250.00,499.999,0.25,20.0,20.0
500.00,999.999,0.50,20.0,20.0
1000.00,2499.999,1.00,20.0,20.0
2500.00,999999.999,2.50,20.0,20.0
""")

# Kod dosyaları
w_if_missing('src/config.py',
"""import json, pathlib
BASE = pathlib.Path(__file__).resolve().parents[1]
def load_json(rel):
    with open(BASE/rel, 'r', encoding='utf-8') as f: return json.load(f)
CORE     = load_json('config/core.json')
SOURCES  = load_json('config/sources.json')
GATES    = load_json('config/gates.json')
STRATEGY = load_json('config/strategy.json')
""")
w_if_missing('src/bist_core/models.py',
"""from dataclasses import dataclass
from datetime import date, datetime
@dataclass
class EODBar: symbol: str; date: date; close: float; high: float; low: float; volume: int; turnover_tl: int
@dataclass
class PriceBand: price_min: float; price_max: float; tick: float; up_limit_pct: float; down_limit_pct: float
@dataclass
class KapEvent: symbol: str; ts_trt: datetime; title: str; body: str
""")
w_if_missing('src/bist_core/repositories/local_csv.py',
"""import csv, pathlib
from datetime import datetime
from ..models import EODBar, PriceBand, KapEvent
from ...config import SOURCES
ROOT = pathlib.Path(SOURCES['local_csv']['root_dir']).resolve()
_d  = lambda s: datetime.strptime(s,'%Y-%m-%d').date()
_dt = lambda s: datetime.strptime(s,'%Y-%m-%d %H:%M:%S')
def eod_prices():
    out=[]
    with open(ROOT/'eod_prices.csv','r',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            out.append(EODBar(r['symbol'], _d(r['date']), float(r['close']), float(r['high']), float(r['low']), int(r['volume']), int(r['turnover_tl'])))
    return out
def kap_events():
    out=[]
    with open(ROOT/'kap_events.csv','r',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            out.append(KapEvent(r['symbol'], _dt(r['ts_trt']), r['title'], r['body']))
    return out
def price_bands():
    out=[]
    with open(ROOT/'price_bands.csv','r',encoding='utf-8') as f:
        for r in csv.DictReader(f):
            out.append(PriceBand(float(r['price_min']), float(r['price_max']), float(r['tick']), float(r['up_limit_pct']), float(r['down_limit_pct'])))
    return out
""")
w_if_missing('src/bist_core/strategy/engine.py',
"""from typing import List
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
""")
w_if_missing('src/bist_core/runner.py',
"""from .repositories import local_csv as repo
from ..config import CORE, GATES, STRATEGY
from .strategy.engine import decide
def run_decision():
    bars = repo.eod_prices(); kap = repo.kap_events(); bands = repo.price_bands()
    syms = sorted({b.symbol for b in bars})
    return decide(syms, bars, bands, kap, CORE, GATES, STRATEGY)
""")
w_if_missing('src/bist_core/cli.py',
"""import argparse, json
from .runner import run_decision
def main():
    p = argparse.ArgumentParser()
    p.add_subparsers(dest='cmd').add_parser('ask').add_argument('question', nargs='?')
    print(json.dumps(run_decision(), ensure_ascii=False, indent=2))
if __name__ == '__main__': main()
""")
w_if_missing('tests/test_smoke.py',
"""from src.bist_core.runner import run_decision
def test_smoke():
    res = run_decision()
    assert isinstance(res, list) and len(res)>0
""")
print("OK_FILES")
PY

echo "[2/3] PyTest kuruluyor…"
"$PY" -m pip install -U pip >/dev/null
"$PY" -m pip install -q pytest

echo "[3/3] Test ve örnek sorgular…"
PYTHONPATH="$PWD" "$PY" -m pytest -q
for q in "QNBFK alınır mı?" "MEKAG alınır mı?" "CMBTN alınır mı?"; do
  PYTHONPATH="$PWD" "$PY" -m src.bist_core.cli ask "$q"
done
echo "FAZ-1 TAMAM ✅"
