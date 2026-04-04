"""Live paper trader — fetch data, run scan→rank→decision, simulate trades, log PnL."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

from bist_core.brain.scoring_engine import rank_symbols, score_symbol
from bist_core.execution.engine import ExecutionEngine, OrderState
from bist_core.execution.execution_model import ExecutionModel
from bist_core.features.feature_engine import FeatureEngine
from bist_core.risk.portfolio_state import PortfolioState
from bist_core.models.ohlcv import OHLCVBar
from bist_core.pipeline import Pipeline

_SCORE_FEATURES = ['atr_14', 'ema_20', 'momentum_20', 'rsi_14', 'sma_20', 'sma_50']

DEFAULT_OUTPUT_PATH = "paper_trades.jsonl"
DEFAULT_EXECUTION_MODEL = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
DEFAULT_EQUITY_PATH = "equity_curve.jsonl"
DEFAULT_INTERVAL_SEC = 60
MIN_BARS = 2
MIN_BARS_PIPELINE = 2
INITIAL_CAPITAL = 100_000.0
MIN_REQUIRED_BARS = 50


def _wait_next_5m() -> None:
    """Wait until the next 5-minute boundary (UTC)."""
    now = datetime.utcnow()
    sec = now.minute % 5 * 60 + now.second
    sleep = 300 - sec
    if sleep > 0:
        time.sleep(sleep)


def _last_bar_ts(bars):
    try:
        last = bars[-1]
    except Exception:
        return None

    for attr in ("timestamp", "time"):
        val = getattr(last, attr, None)
        if val is None:
            try:
                val = last[attr]
            except Exception:
                val = None
        if val is not None:
            return str(val)

    try:
        if hasattr(last, "index"):
            return str(getattr(last, "index")[-1])
    except Exception:
        pass

    return None


class _PortfolioState:
    """Minimal portfolio state for snapshot/update. Used only in paper_trader."""

    def __init__(self, trader: "PaperTrader") -> None:
        self._trader = trader

    def snapshot(self) -> dict:
        return {"capital": self._trader._capital}

    def update(self, result: dict) -> None:
        pnl = result.get("net_pnl") or result.get("pnl", 0)
        try:
            self._trader._capital += float(pnl)
        except (TypeError, ValueError):
            pass


def _parse_ts(v) -> int | None:
    try:
        if isinstance(v, str):
            from datetime import timezone as _tz
            _dt = datetime.fromisoformat(v)
            if _dt.tzinfo is None:
                _dt = _dt.replace(tzinfo=_tz.utc)
            return int(_dt.timestamp())
        v = int(v)
        if v > 1_000_000_000_000:
            return int(v / 1000)
        return v
    except Exception:
        return None


def _fetch_matriks(symbol: str) -> list[OHLCVBar] | None:
    """Fetch OHLCV bars from Matriks API. Guarded by MATRIKS_TOKEN env var. Returns None on failure."""
    token = os.environ.get("MATRIKS_TOKEN", "")
    if not token:
        return None
    try:
        import requests
    except ImportError:
        return None

    end = datetime.utcnow()
    start = end - timedelta(days=5)
    url = "https://apitest.matriksdata.com/dumrul/v1/tick/bar"
    params = {
        "symbol": symbol,
        "period": "1day",
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
    }
    headers = {"Authorization": f"jwt {token}"}

    try:
        r = requests.get(url, headers=headers, params=params)
    except Exception:
        return None

    if r.status_code != 200:
        return None

    try:
        data = r.json()
    except Exception:
        return None

    if not isinstance(data, list) or len(data) == 0:
        return None

    bars = []
    for x in data:
        try:
                ts = _parse_ts(x.get("time"))
                if ts is None:
                    continue
                _now_ts = int(datetime.utcnow().timestamp())
                if ts > _now_ts + 60:
                    continue
                bars.append(OHLCVBar(
                symbol=symbol,
                open=float(x["open"]),
                high=float(x["high"]),
                low=float(x["low"]),
                close=float(x["close"]),
                volume=float(x["volume"]),
                timestamp=ts,
            ))
        except Exception:
            return None

    if not bars:
        return None

    bars.sort(key=lambda b: b.timestamp)

    return bars


def _fetch_csv(symbol: str, csv_path: str) -> list[OHLCVBar] | None:
    import csv as _csv
    from datetime import datetime as _dt

    try:
        bars = []
        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                if row.get("symbol") != symbol:
                    continue
                try:
                    ts = int(_dt.strptime(row["date"], "%Y-%m-%d").timestamp())
                    bars.append(OHLCVBar(
                        symbol=symbol,
                        open=float(row.get("open", row["close"])),
                        high=float(row.get("high", row["close"])),
                        low=float(row.get("low", row["close"])),
                        close=float(row["close"]),
                        volume=float(row.get("volume", 0)),
                        timestamp=ts,
                    ))
                except Exception:
                    return None
        return bars if bars else None
    except Exception:
        return None


def _fetch_ideal(symbol: str, chart_dir: str) -> list[OHLCVBar] | None:
    """Load bars from iDeal ChartData .G file for symbol. Fail-closed."""
    import glob as _glob
    from bist_core.vendors.ideal.parser import IdealGParser, IdealFormatUnverifiedError

    try:
        pattern = chart_dir + "/G/*'" + symbol + ".G"
        matches = _glob.glob(pattern)
        if not matches:
            return None
        path = matches[0]
        parser = IdealGParser()
        import datetime as _dt
        norm_bars = parser.parse(path, last_date=_dt.date.today())
        bars = []
        for b in norm_bars:
            try:
                import datetime as _dt
                ts = int(_dt.datetime.strptime(b.ts[:10], "%Y-%m-%d").timestamp())
                bars.append(OHLCVBar(
                    symbol=symbol,
                    open=float(b.open),
                    high=float(b.high),
                    low=float(b.low),
                    close=float(b.close),
                    volume=float(b.volume),
                    timestamp=ts,
                ))
            except Exception:
                continue
        bars.sort(key=lambda x: x.timestamp)
        return bars if bars else None
    except (IdealFormatUnverifiedError, Exception):
        return None


def _fetch_ideal_intraday(symbol: str, chart_dir: str) -> OHLCVBar | None:
    """Fetch last 5m bar from iDeal binary .05 file using ideal_intraday parser.
    O(1) tail read. Fail-closed. ts_code_raw used as opaque ordering key.
    """
    import glob as _glob
    from bist_core.vendors.ideal_intraday import parse_file, infer_symbol_from_filename
    pattern = chart_dir + "/05/*'" + symbol + ".05"
    matches = _glob.glob(pattern)
    if not matches:
        return None
    path = matches[0]
    try:
        records = parse_file(path, tail=1)
        if not records:
            return None
        r = records[-1]
        o = float(r["open"])
        h = float(r["high"])
        l = float(r["low"])
        c = float(r["close"])
        v = float(r["volume"])
        if c <= 0 or o <= 0:
            return None
        # ts_code_raw used as ordering key — not wall-clock time
        ts = int(r["ts_code_raw"])
        return OHLCVBar(
            symbol=symbol,
            open=o,
            high=h,
            low=l,
            close=c,
            volume=v,
            timestamp=ts,
        )
    except Exception:
        return None


def _fetch_hybrid(symbol: str, ideal_dir: str) -> list[OHLCVBar] | None:
    """iDeal G bars as feature base. iDeal 05 last bar as current price override.
    ts_code_raw from 05 is an opaque vendor code — always override when close > 0.
    Fail-closed: returns None if no G base.
    """
    base = _fetch_ideal(symbol, ideal_dir)
    if not base:
        return None
    last_05 = _fetch_ideal_intraday(symbol, ideal_dir)
    if last_05 is not None and last_05.close > 0:
        price_bar = OHLCVBar(
            symbol=symbol,
            open=last_05.open,
            high=last_05.high,
            low=last_05.low,
            close=last_05.close,
            volume=last_05.volume,
            timestamp=int(base[-1].timestamp) + 1,
        )
        return base + [price_bar]
    live = _fetch_matriks(symbol)
    if live is not None and int(live[-1].timestamp) > int(base[-1].timestamp):
        return base + [live[-1]]
    return base


def _default_ideal_fetcher(symbols: list[str]) -> dict[str, list[OHLCVBar]]:
    data_map = {}
    _ideal_dir = os.environ.get("IDEAL_CHART_DIR", "")

    for symbol in symbols:
        bars = None

        # 1) Matriks — only accept if sufficient bars (>= MIN_REQUIRED_BARS)
        matriks_bars = _fetch_matriks(symbol)
        if matriks_bars is not None and len(matriks_bars) >= MIN_REQUIRED_BARS:
            bars = matriks_bars

        # 2) iDeal Hybrid (G history + 05 last price) — primary real data source
        if bars is None and _ideal_dir:
            bars = _fetch_hybrid(symbol, _ideal_dir)

        # 3) CSV fallback
        if bars is None:
            _csv_path = os.environ.get("BIST_EOD_CSV", "data/samples/eod_prices.csv")
            bars = _fetch_csv(symbol, _csv_path)

        if bars:
            data_map[symbol] = bars

    return data_map


def compute_paper_metrics(logs: list[dict]) -> dict[str, Any]:
    trades_with_pnl = [t for t in logs if ("pnl" in t or "net_pnl" in t) and t.get("action") == "BUY"]
    if not trades_with_pnl:
        return {
            "total_trades": 0, "wins": 0, "losses": 0, "win_rate": 0.0,
            "avg_win": 0.0, "avg_loss": 0.0, "expectancy": 0.0, "max_drawdown": 0.0,
            "total_cost": 0.0, "net_expectancy": 0.0,
        }
    pnls = [float(t.get("net_pnl", t.get("pnl", 0))) for t in trades_with_pnl]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    total = len(pnls)
    win_rate = len(wins) / total if total > 0 else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = abs(sum(losses)) / len(losses) if losses else 0.0
    expectancy = sum(pnls) / total if total > 0 else 0.0
    equity = 0.0
    peak = 0.0
    max_dd = 0.0
    for p in pnls:
        equity += p
        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    total_cost = sum(float(t.get("cost", 0)) for t in trades_with_pnl)
    return {
        "total_trades": total, "wins": len(wins), "losses": len(losses),
        "win_rate": round(win_rate, 4), "avg_win": round(avg_win, 4),
        "avg_loss": round(avg_loss, 4), "expectancy": round(expectancy, 4),
        "max_drawdown": round(max_dd, 4), "total_cost": round(total_cost, 6),
        "net_expectancy": round(expectancy, 4),
    }


def _normalize_result(result: dict) -> dict:
    if not isinstance(result, dict):
        return {"status": "no_trade", "reason": "invalid result", "symbols": [], "count": 0, "trades": []}
    status = result.get("status")
    if status == "executed":
        trades = result.get("trades")
        if not isinstance(trades, list):
            return {"status": "no_trade", "reason": "invalid trades structure", "symbols": [], "count": 0, "trades": []}
        return {
            "status": "executed",
            "count": int(result.get("count", len(trades))),
            "trades": trades,
        }
    return {
        "status": "no_trade",
        "reason": result.get("reason", "unknown"),
        "symbols": result.get("symbols") or [],
        "count": 0,
        "trades": [],
    }


class PaperTrader:
    def __init__(
        self,
        symbols: list[str],
        *,
        data_fetcher: Callable[[list[str]], dict[str, list[OHLCVBar]]] | None = None,
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
        equity_path: str | Path = DEFAULT_EQUITY_PATH,
        state_path: str | Path = "runtime_state.json",
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        threshold: float = 1.0,
        initial_capital: float = INITIAL_CAPITAL,
        execution_model: ExecutionModel | None = None,
    ) -> None:
        self._symbols = sorted(symbols)
        self._execution_model = execution_model or DEFAULT_EXECUTION_MODEL
        self._fetcher = data_fetcher or _default_ideal_fetcher
        self._output_path = Path(output_path)
        self._equity_path = Path(equity_path)
        self._state_path = Path(state_path)
        self._interval_sec = interval_sec
        self._threshold = threshold
        self._capital = float(initial_capital)
        self._consecutive_losses = 0
        self._pipeline = Pipeline()
        self.portfolio_engine = _PortfolioState(self)
        self._execution_engine = ExecutionEngine()
        self._portfolio_state = PortfolioState(capital=float(initial_capital))
        self._last_ts = {}

    def _run_cycle(self) -> dict:
        md = self._fetcher(self._symbols)
        if not isinstance(md, dict) or not md:
            return {"status": "no_trade", "reason": "no data"}

        clean = {s: b for s, b in md.items() if b}
        if not clean:
            return {"status": "no_trade", "reason": "no data"}

        current_prices = {}
        for s, b in clean.items():
            if b and len(b) > 0:
                current_prices[s] = float(b[-1].close)

        _fe = FeatureEngine()
        symbol_data = {}
        for s, bars in clean.items():
            if not bars:
                continue
            try:
                feats = _fe.compute_features(bars, _SCORE_FEATURES)
                sr = score_symbol(s, feats, bars[-1].close)
                if sr is not None:
                    symbol_data[s] = {"bars": bars, "features": feats, "scored": sr}
                else:
                    import logging as _log
                    _log.debug(f"SKIP {s}: score_symbol returned None")
            except Exception:
                continue

        ranked = rank_symbols([v["scored"] for v in symbol_data.values()])
        if not ranked:
            return {"status": "no_trade", "reason": "no valid signals", "symbols": list(clean.keys())}

        decisions = []
        for r in ranked:
            sym = r["symbol"]
            sd = symbol_data.get(sym)
            if not sd:
                continue
            bars = sd["bars"]
            feats = sd["features"]
            entry = float(bars[-1].close)
            atr_vals = feats.get("atr_14", [])
            atr = float(atr_vals[-1]) if atr_vals and atr_vals[-1] is not None else entry * 0.02
            stop = round(entry - max(atr, entry * 0.01), 4)
            target = round(entry + (entry - stop) * 2, 4)
            if stop >= entry:
                continue
            decisions.append({
                "symbol": sym,
                "entry": entry,
                "stop": stop,
                "target": target,
                "score": r["score"],
                "reason": r["reason"],
            })

        if not decisions:
            return {"status": "no_trade", "reason": "no valid signals after risk filter", "symbols": list(clean.keys())}

        for sym, pos in list(self._portfolio_state.open_positions.items()):
            price = current_prices.get(sym)
            if price is None:
                continue
            closed = self._execution_engine.update(sym, price)
            if closed:
                self._portfolio_state.close_position(sym, closed.net_pnl)
                self._portfolio_state.record_trade({
                    "symbol": sym, "net_pnl": closed.net_pnl,
                    "exit_price": closed.exit_price, "state": closed.state.value,
                })

        executed: list[dict] = []
        best_candidate: dict | None = None
        best_score: float = -999.0
        for d in decisions:
            try:
                symbol = d.get("symbol")
                stop = float(d.get("stop"))
            except (TypeError, ValueError):
                continue

            if not symbol:
                continue

            price = current_prices.get(symbol) or d.get("entry")
            if price is None:
                continue

            entry = float(price)

            if entry <= stop:
                continue

            rps = entry - stop
            if rps <= 0:
                continue

            if rps < 0.01:
                continue

            can, reason = self._portfolio_state.can_trade()
            if not can:
                import logging as _log
                _log.debug(f"SKIP {symbol}: portfolio blocked reason={reason}")
                continue

            size, size_reason = self._portfolio_state.size_trade(entry=entry, stop=stop)
            if size <= 0:
                import logging as _log
                _log.debug(f"SKIP {symbol}: sizing failed reason={size_reason}")
                continue

            if size > 0:
                score_val = float(d.get("score", 0.0))
                if score_val > best_score:
                    best_score = score_val
                    best_candidate = {
                        "symbol": symbol, "entry": entry,
                        "stop": stop, "size": size,
                        "target": d.get("target", round(entry + (entry - stop) * 2, 4)),
                        "score": score_val,
                    }

            if size > 100000:
                size = 100000

            size = float(int(size))

            order = self._execution_engine.submit(
                symbol=symbol, entry=entry, stop=stop,
                target=d.get("target", entry + (entry - stop)),
                size=size,
            )
            if order.state != OrderState.FILLED:
                continue

            result = {
                "symbol": order.symbol,
                "entry": order.entry,
                "exit": order.target,
                "fill_price": order.fill_price,
                "entry_fill": order.fill_price,
                "exit_fill": order.target,
                "size": order.size,
                "state": order.state.value,
                "net_pnl": 0.0,
                "pnl": 0.0,
            }
            self._portfolio_state.open_position(
                symbol=symbol, entry=order.fill_price,
                size=order.size, stop=stop,
                target=d.get("target", entry + (entry - stop)),
            )
            executed.append(result)

        if not executed and best_candidate is not None:
            sym = best_candidate["symbol"]
            can_fb, _ = self._portfolio_state.can_trade()
            if can_fb and sym not in self._execution_engine.open_positions():
                fb_size, fb_reason = self._portfolio_state.size_trade(
                    best_candidate["entry"], best_candidate["stop"]
                )
                if fb_size > 0:
                    fb_order = self._execution_engine.submit(
                        sym, best_candidate["entry"],
                        best_candidate["stop"],
                        best_candidate["target"],
                        fb_size,
                    )
                    if fb_order.state == OrderState.FILLED:
                        self._portfolio_state.open_position(
                            sym, fb_order.fill_price, fb_order.size,
                            best_candidate["stop"], best_candidate["target"],
                        )
                        result_fb = {
                            "symbol": sym,
                            "entry": best_candidate["entry"],
                            "exit": best_candidate["target"],
                            "fill_price": fb_order.fill_price,
                            "entry_fill": fb_order.fill_price,
                            "exit_fill": best_candidate["target"],
                            "size": fb_order.size,
                            "state": fb_order.state.value,
                            "net_pnl": 0.0,
                            "pnl": 0.0,
                            "fallback": True,
                        }
                        net_pnl_fb = float(result_fb.get("net_pnl", 0.0))
                        self._portfolio_state.close_position(sym, net_pnl_fb)
                        self._portfolio_state.record_trade(result_fb)
                        self._capital = self._portfolio_state.capital
                        executed.append(result_fb)

        for s, b in clean.items():
            t = _last_bar_ts(b)
            if t is not None:
                self._last_ts[s] = t

        if not executed:
            return {
                "status": "no_trade",
                "reason": "no executable trades",
                "symbols": list(clean.keys()),
                "decisions": decisions,
            }

        return {"status": "executed", "trades": executed, "count": len(executed)}

    def _append_logs(self, logs: list[dict]) -> None:
        if not logs:
            return
        self._output_path.parent.mkdir(parents=True, exist_ok=True)
        with self._output_path.open("a", encoding="utf-8") as f:
            for entry in logs:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _append_equity(self, equity: float, peak_equity: float, drawdown: float) -> None:
        self._equity_path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        line = json.dumps({"timestamp": ts, "equity": equity, "peak_equity": peak_equity, "drawdown": drawdown}, ensure_ascii=False) + "\n"
        with self._equity_path.open("a", encoding="utf-8") as f:
            f.write(line)

    def _save_state(self) -> None:
        from bist_core.live.state import load_state, save_state
        s = load_state(self._state_path)
        s["last_run_ts"] = datetime.now(timezone.utc).isoformat()
        s["equity"] = self._capital
        s["peak_equity"] = max(s.get("peak_equity", 0), self._capital)
        peak = s["peak_equity"]
        s["drawdown"] = (peak - self._capital) / peak if peak > 0 else 0.0
        s["consecutive_losses"] = self._consecutive_losses
        save_state(s, self._state_path)

    def run_once(self) -> dict:
        """Public single-cycle execution. Calls _run_cycle and logs result."""
        result = self._run_cycle()
        self._capital = self._portfolio_state.capital
        try:
            import json
            with open(self._output_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(result) + "\n")
        except Exception:
            pass
        return _normalize_result(result)

    def run_loop(self, cycles: int = 1) -> list:
        results: list = []
        for _ in range(cycles):
            result = self.run_once()
            if not isinstance(result, dict):
                continue
            if result.get("status") not in ("executed", "no_trade"):
                continue
            results.append(result)
        return results

    def run_live(self, cycles: int = 7) -> list:
        results: list = []
        for i in range(cycles):
            if i > 0:
                time.sleep(300)
            r = self.run_once()
            print(f"[{i+1}/{cycles}] {r}", flush=True)
            if isinstance(r, dict) and r.get("status") == "executed":
                results.append(r)
        return results

    def run(self) -> None:
        self.run_live()


__all__ = [
    "PaperTrader",
    "compute_paper_metrics",
    "DEFAULT_OUTPUT_PATH",
    "DEFAULT_EQUITY_PATH",
    "DEFAULT_INTERVAL_SEC",
]

if __name__ == "__main__":
    import os

    symbols = os.getenv("BIST_SYMBOLS", "GARAN").split(",")
    cycles = int(os.environ.get("BIST_CYCLES", "6"))
    t = PaperTrader(symbols)
    results = t.run_live(cycles=cycles)
    executed_count = sum(1 for r in results if isinstance(r, dict) and r.get("status") == "executed")
    trace = {
        "cycles": cycles,
        "results": results,
        "executed_count": executed_count,
        "notes": "ok" if executed_count >= 0 else "no trades",
    }
    print(json.dumps(trace, default=str), flush=True)
