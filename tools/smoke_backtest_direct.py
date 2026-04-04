from bist_core.backtest.backtest_engine import BacktestEngine
from bist_core.data.ideal_data_loader import load_ideal_bars


def main() -> None:
    symbols = ["ASELS", "THYAO", "SISE", "EREGL"]

    data: dict[str, list] = {}
    for s in symbols:
        b = load_ideal_bars(s)[-2000:]
        if isinstance(b, list) and len(b) > 50:
            data[s] = b

    data = {k: v for k, v in data.items() if len(v) >= 200}

    if len(data) == 0:
        raise RuntimeError("NO VALID DATA")

    min_len = min(len(v) for v in data.values())
    for k in data:
        data[k] = data[k][-min_len:]

    engine = BacktestEngine()
    res = engine.run(data)

    print("SUMMARY:")
    print("TOTAL TRADES:", res["metrics"].get("total_trades"))
    print("EXPECTANCY:", res["metrics"].get("expectancy"))
    print("EQUITY FINAL:", res["metrics"].get("equity_final"))
    print("STABLE:", res["metrics"].get("stable"))

    print("SIGNAL STATS:", res.get("signal_stats"))

    total_signals = sum(res.get("signal_stats", {}).get("entry_signals", {}).values())

    if total_signals == 0:
        print("CRITICAL: NO ENTRY SIGNALS GENERATED")

    print("ENTRY VS TRADE CHECK:")
    print("ENTRY SIGNALS:", total_signals)
    print("EXECUTED TRADES:", res["metrics"].get("total_trades"))

    if total_signals > 20 and res["metrics"].get("total_trades", 0) < 3:
        print("FILTER BLOCKING EXECUTION")

    if total_signals < 5:
        print("DECISION ENGINE TOO STRICT")

    print("TRADES PER SYMBOL:")
    counts: dict[str, int] = {}
    for t in res.get("trades", []):
        sym = t.get("symbol")
        if sym is not None:
            counts[str(sym)] = counts.get(str(sym), 0) + 1
    print(counts)

    metrics = res.get("metrics", {})

    if metrics.get("total_trades", 0) < 5:
        print("WARNING: LOW SAMPLE SIZE")

    if metrics.get("expectancy", 0) <= 0:
        print("WARNING: NO EDGE")


if __name__ == "__main__":
    main()
