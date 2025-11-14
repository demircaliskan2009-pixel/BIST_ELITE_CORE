from .repositories import local_csv as repo
from ..config import CORE, GATES, STRATEGY
from .strategy.engine import decide
def run_decision():
    bars = repo.eod_prices(); kap = repo.kap_events(); bands = repo.price_bands()
    syms = sorted({b.symbol for b in bars})
    return decide(syms, bars, bands, kap, CORE, GATES, STRATEGY)
