from dataclasses import dataclass
from datetime import date, datetime
@dataclass
class EODBar: symbol: str; date: date; close: float; high: float; low: float; volume: int; turnover_tl: int
@dataclass
class PriceBand: price_min: float; price_max: float; tick: float; up_limit_pct: float; down_limit_pct: float
@dataclass
class KapEvent: symbol: str; ts_trt: datetime; title: str; body: str
