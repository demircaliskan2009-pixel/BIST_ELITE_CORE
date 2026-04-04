import os, sys
sys.path.insert(0, 'src')
os.environ['IDEAL_CHART_DIR'] = 'C:/iDeal/ChartData/IMKBH'

from bist_core.brain.scoring_engine import (
    score_symbol, rank_symbols, SCORE_THRESHOLD
)
from bist_core.live.paper_trader import _default_ideal_fetcher, _SCORE_FEATURES
from bist_core.features.feature_engine import RegistryFeatureEngine

assert SCORE_THRESHOLD == 0.10, f'threshold must be 0.10 got {SCORE_THRESHOLD}'

SYMS = 'GARAN,AKBNK,THYAO,SISE,KCHOL,EREGL,BIMAS,ARCLK,TOASO,FROTO'.split(',')
fe = RegistryFeatureEngine()
data = _default_ideal_fetcher(SYMS)
scored = []
for sym in SYMS:
    bars = data.get(sym)
    if not bars or len(bars) < 21:
        continue
    feats = fe.compute_features(bars, _SCORE_FEATURES)
    r = score_symbol(sym, feats, bars[-1].close)
    if r:
        scored.append(r)
        print(f'{sym}: score={round(r["score"],4)}')

ranked = rank_symbols(scored)
print('RANKED:', [(r['symbol'], round(r['score'],4)) for r in ranked])
assert len(ranked) > 0, 'rank_symbols must return candidates'

from bist_core.live.paper_trader import PaperTrader
trades_seen = 0
pt = PaperTrader(symbols=SYMS, initial_capital=100000.0)
for i in range(5):
    r = pt.run_once()
    if r['status'] == 'executed':
        trades_seen += r['count']
    print(f'cycle {i+1}: {r["status"]} count={r["count"]}')

assert pt._portfolio_state.capital > 0, 'capital must remain positive'
print(f'TRADES IN 5 CYCLES: {trades_seen}')
print('SYSTEM VERIFIED — NO ERRORS — READY')
