"""BIST CLI — scan, paper trade, backtest commands.

Provides a standalone CLI entry point for the trading bot.
Outputs structured JSON.  Pure stdlib, no network unless guarded.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List, Sequence

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel, OHLCVBar
from bist_core.brain.ranking_engine import RankingEngine
from bist_core.brain.scanner_engine import ScannerEngine
from bist_core.brain.strategy_engine import StrategyEngine
from bist_core.execution.paper_engine import PaperExecutionEngine, SlippageModel
from bist_core.execution.paper_trading_loop import PaperTradingLoop
from bist_core.risk.trade_risk_engine import RiskProfile, TradeRiskGate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_synthetic_bars(symbols: List[str], n: int = 60) -> Dict[str, List[OHLCVBar]]:
    """Build minimal synthetic bars for demo/test purposes."""
    dataset: dict[str, list[OHLCVBar]] = {}
    for sym in symbols:
        bars: list[OHLCVBar] = []
        price = 100.0
        base_ts = 1704067200
        for i in range(n):
            c = round(price + (i % 5) * 0.3, 4)
            bars.append(OHLCVBar(
                timestamp=base_ts + i * 86400,
                symbol=sym.upper().strip(),
                open=c - 0.5,
                high=c + 1,
                low=max(c - 1, 0.01),
                close=c,
                volume=1_000_000,
            ))
            price = c
        dataset[sym.upper().strip()] = bars
    return dataset


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def run_scan(symbol_dataset: Dict[str, Sequence[OHLCVBar]]) -> Dict[str, Any]:
    """Scan universe and return ranked signals as dict."""
    strategy = StrategyEngine(lookback=50)
    ranking = RankingEngine()
    scanner = ScannerEngine(strategy_engine=strategy, ranking_engine=ranking)
    result = scanner.scan(symbol_dataset)
    return result.to_dict()


def run_paper(symbol_dataset: Dict[str, Sequence[OHLCVBar]]) -> Dict[str, Any]:
    """Run one paper trading cycle and return summary."""
    loop = PaperTradingLoop()
    return loop.run_cycle(symbol_dataset)


def run_backtest(bars: Sequence[OHLCVBar]) -> Dict[str, Any]:
    """Run backtest on bars and return result."""
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    engine = BacktestEngine(cost_model=cost)
    return engine.run(bars)


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

def _parse_symbols(raw: str) -> List[str]:
    return [s.strip().upper() for s in raw.split(",") if s.strip()]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="bist", description="BIST Elite Core CLI")
    sub = parser.add_subparsers(dest="command")

    scan_p = sub.add_parser("scan", help="Scan symbols for signals")
    scan_p.add_argument("--symbols", required=True, help="Comma-separated symbol list")

    paper_p = sub.add_parser("paper", help="Run one paper trading cycle")
    paper_p.add_argument("--symbols", required=True, help="Comma-separated symbol list")

    bt_p = sub.add_parser("backtest", help="Run backtest")
    bt_p.add_argument("--symbols", required=True, help="Comma-separated symbol list")
    bt_p.add_argument("--bars", type=int, default=60, help="Number of bars per symbol")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 2

    if args.command == "scan":
        symbols = _parse_symbols(args.symbols)
        dataset = _build_synthetic_bars(symbols)
        result = run_scan(dataset)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "paper":
        symbols = _parse_symbols(args.symbols)
        dataset = _build_synthetic_bars(symbols)
        result = run_paper(dataset)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "backtest":
        symbols = _parse_symbols(args.symbols)
        dataset = _build_synthetic_bars(symbols, n=args.bars)
        all_bars: list[OHLCVBar] = []
        for bars in dataset.values():
            all_bars.extend(bars)
        all_bars.sort(key=lambda b: (b.timestamp, b.symbol))
        result = run_backtest(all_bars)
        output = {
            "metrics": result.get("metrics"),
            "trade_count": len(result.get("trades", [])),
            "regime_summary": result.get("regime_summary"),
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
        return 0

    parser.print_help()
    return 2
