import csv, pathlib
from datetime import datetime
from ..models import EODBar, PriceBand, KapEvent
from ..config import SOURCES
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
