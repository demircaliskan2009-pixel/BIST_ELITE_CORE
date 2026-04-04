"""Real-data backtest runner for iDeal dataset."""

from __future__ import annotations

import json
import sys

from bist_core.data.loader import load_ideal_dataset
from bist_core.backtest.backtest import BacktestEngine


SYMBOLS = ["ASELS", "THYAO", "GARAN", "AKBNK", "BIMAS"]
BASE_PATH = r"C:/iDeal/ChartData/IMKBH/G"


def main() -> int:
    """Load iDeal dataset, run backtest, print metrics and sample trades."""
    data = load_ideal_dataset(BASE_PATH, SYMBOLS)
    if not data:
        print("No data loaded. Check base_path and symbols.", file=sys.stderr)
        return 1

    engine = BacktestEngine(threshold=0.0)
    result = engine.run(data)

    print("=== METRICS ===")
    print(json.dumps(result["metrics"], indent=2))

    print("\n=== SAMPLE TRADES ===")
    trades = result["trades"][:5]
    for t in trades:
        print(json.dumps(t, indent=2))

    return 0


if __name__ == "__main__":
    sys.exit(main())
