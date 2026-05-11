"""Live paper trader — fetch data, run scan→rank→decision, simulate trades, log PnL."""

from __future__ import annotations

import json
import math
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from bist_core.ai.explanation_engine import ExplanationEngine
from bist_core.config.system_config import CONFIG
from bist_core.data.price_provider import get_current_price
from bist_core.execution.broker_adapter import PaperBrokerAdapter
from bist_core.execution.depth_model import DepthModel
from bist_core.execution.execution_engine import ExecutionEngine as PaperOrderExecutionEngine
from bist_core.execution.execution_model import ExecutionModel, apply_execution_cost
from bist_core.execution.latency_model import LatencyModel
from bist_core.execution.slippage_model import SlippageModel
from bist_core.execution.spread_model import SpreadModel
from bist_core.features.feature_engine import FeatureEngine
from bist_core.live.execution_engine import ExecutionEngine
from bist_core.market.session_engine import SessionEngine
from bist_core.models.ohlcv import OHLCVBar
from bist_core.monitoring.audit_logger import AuditLogger
from bist_core.monitoring.health_monitor import HealthMonitor
from bist_core.portfolio import PortfolioEngine
from bist_core.rank.advanced_ranker import AdvancedRanker
from bist_core.risk.bist_rules import BISTRules
from bist_core.risk.circuit_breaker import CircuitBreaker
from bist_core.risk.correlation_engine import CorrelationEngine
from bist_core.risk.event_risk import EventRisk
from bist_core.risk.exposure_controller import ExposureController
from bist_core.risk.portfolio_risk_engine import PortfolioRiskEngine
from bist_core.risk.sector_mapper import get_sector
from bist_core.risk.volatility_shock import VolatilityShock
from bist_core.strategy.meta_selector import MetaSelector
from bist_core.strategy.strategy_decay import StrategyDecay
from bist_core.strategy.strategy_metrics import StrategyMetrics

DEFAULT_OUTPUT_PATH = "paper_trades.jsonl"
DEFAULT_EXECUTION_MODEL = ExecutionModel(slippage_bps=5.0, spread_bps=10.0, commission_bps=2.0)
DEFAULT_EQUITY_PATH = "equity_curve.jsonl"
DEFAULT_INTERVAL_SEC = 60
MIN_BARS = 2
MIN_BARS_PIPELINE = 2
INITIAL_CAPITAL = 100_000.0
MIN_REQUIRED_BARS = 50

RUNTIME_DIR = "runtime"
PORTFOLIO_STATE_PATH = os.path.join(RUNTIME_DIR, "portfolio_state.json")
TRADES_LOG_PATH = os.path.join(RUNTIME_DIR, "trades_log.jsonl")


def _prev_close_for_bist(bars: Any) -> float | None:
    if not isinstance(bars, list) or len(bars) < 1:
        return None
    try:
        if len(bars) >= 2:
            c = getattr(bars[-2], "close", None)
        else:
            c = getattr(bars[-1], "close", None)
        if isinstance(c, (int, float)) and float(c) > 0:
            return float(c)
    except Exception:
        return None
    return None


def _atomic_write_json(path: str, data: dict) -> None:
    """Crash-safe atomic write. Uses tmp + replace."""
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, separators=(",", ":"))
        os.replace(tmp_path, path)
    except Exception:
        pass


def get_tick_size(price: float) -> float:
    """BIST-compatible tick size by price band."""
    if not isinstance(price, (int, float)):
        return 0.01
    if price < 10:
        return 0.01
    if price < 20:
        return 0.02
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    return 0.25


def _wait_next_5m() -> None:
    """Wait until the next 5-minute boundary (UTC)."""
    now = datetime.utcnow()
    sec = now.minute % 5 * 60 + now.second
    sleep = 300 - sec
    if sleep > 0:
        time.sleep(sleep)


def _align_time(interval: float) -> None:
    """Align to next time boundary (drift-free start)."""
    if not isinstance(interval, (int, float)) or interval <= 0:
        return
    now = time.time()
    next_boundary = (int(now // interval) + 1) * interval
    sleep_time = max(0.0, next_boundary - now)
    try:
        time.sleep(sleep_time)
    except Exception:
        pass


def _get_recent_bars(symbol: str):
    try:
        from bist_core.data.ideal_parser import parse_ideal_file

        base_path = r"C:\iDeal\ChartData\IMKBH\G"

        # Try both naming formats
        candidates = [
            os.path.join(base_path, f"IMKBH'{symbol}.G"),
            os.path.join(base_path, f"IMKBH''{symbol}.G"),
        ]

        for path in candidates:
            if os.path.exists(path):
                try:
                    bars = parse_ideal_file(path, symbol)
                    if isinstance(bars, list) and len(bars) > 0:
                        return bars[-100:]
                except Exception:
                    continue

        return None

    except Exception:
        return None


def _fallback_bars_from_ideal(symbol: str) -> list[OHLCVBar]:
    """
    When ``_get_recent_bars`` is empty: load from ``IDEAL_CHART_DIR`` (G + optional 05).
    Matriks is **not** used for bars — only iDeal (see ``get_current_price`` for Matriks price).
    Always returns a list (possibly empty).
    """
    _ideal_dir = os.environ.get("IDEAL_CHART_DIR", "").strip()
    if not _ideal_dir or not os.path.isdir(_ideal_dir):
        return []

    try:
        hb = _fetch_hybrid(symbol, _ideal_dir)
        if hb:
            return hb[-100:] if len(hb) > 100 else list(hb)
    except Exception:
        pass

    try:
        fb = _fetch_ideal(symbol, _ideal_dir)
        if fb:
            return fb[-100:] if len(fb) > 100 else list(fb)
    except Exception:
        pass

    return []


def _clamp(val: float, lo: float, hi: float) -> float:
    if val < lo:
        return lo
    if val > hi:
        return hi
    return val


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


def _project_root() -> Path:
    """Project root from paper_trader location (src/bist_core/live/). Deterministic."""
    return Path(__file__).resolve().parents[3]


def _resolve_csv_path(env_path: str | None, default_rel: str) -> str:
    """Resolve CSV path: env absolute, else project-relative, else cwd-relative."""
    if env_path and os.path.isabs(env_path) and os.path.isfile(env_path):
        return env_path
    if env_path:
        for base in (_project_root(), Path.cwd()):
            p = (base / env_path).resolve()
            if p.is_file():
                return str(p)
    for base in (_project_root(), Path.cwd()):
        p = (base / default_rel).resolve()
        if p.is_file():
            return str(p)
    return os.path.join(os.getcwd(), default_rel)


def _fetch_csv(symbol: str, csv_path: str) -> list[OHLCVBar] | None:
    import os
    if not isinstance(csv_path, str) or not csv_path:
        return None
    if not os.path.isfile(csv_path):
        return None

    import csv as _csv
    from datetime import datetime as _dt

    try:
        bars = []

        with open(csv_path, newline="", encoding="utf-8") as f:
            for row in _csv.DictReader(f):
                try:
                    if row.get("symbol") != symbol:
                        continue

                    ts_raw = row.get("date") or row.get("timestamp")
                    if ts_raw is None:
                        continue
                    try:
                        ts = int(_dt.strptime(ts_raw, "%Y-%m-%d").timestamp())
                    except Exception:
                        try:
                            ts = int(ts_raw)
                        except Exception:
                            continue

                    if ts <= 0:
                        continue

                    close_val = row.get("close")
                    if close_val is None:
                        continue

                    close = float(close_val)
                    if close <= 0:
                        continue

                    open_val = row.get("open") or close_val
                    high_val = row.get("high") or close_val
                    low_val = row.get("low") or close_val
                    volume_val = row.get("volume") or 0

                    open_ = float(open_val)
                    high = float(high_val)
                    low = float(low_val)
                    if open_ <= 0 or high <= 0 or low <= 0:
                        continue

                    volume = float(volume_val)
                    if volume < 0:
                        continue

                    if any(x != x or x in (float("inf"), float("-inf")) for x in (open_, high, low, close, volume)):
                        continue

                    bars.append(OHLCVBar(
                        symbol=symbol,
                        open=open_,
                        high=high,
                        low=low,
                        close=close,
                        volume=volume,
                        timestamp=ts,
                    ))

                except Exception:
                    continue

        if not bars:
            return None

        bars = sorted(bars, key=lambda x: getattr(x, "timestamp", 0))

        return bars

    except Exception:
        return None


def _fetch_ideal(symbol: str, chart_dir: str) -> list[OHLCVBar] | None:
    """Load bars from iDeal ChartData .G file for symbol. Fail-closed."""
    import glob as _glob

    from bist_core.vendors.ideal.parser import IdealFormatUnverifiedError, IdealGParser

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

    from bist_core.vendors.ideal_intraday import parse_file
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
    return base


def _csv_sample_fetcher(symbols: list[str]) -> dict[str, list[OHLCVBar]]:
    """Fetch bars from data/sample_bist/*.csv."""
    from bist_core.data.csv_loader import load_csv
    data_map = {}
    for symbol in symbols:
        bars = load_csv(symbol)
        if bars:
            data_map[symbol] = bars
    return data_map


def _default_ideal_fetcher(symbols: list[str]) -> dict[str, list[OHLCVBar]]:
    data_map = {}
    _ideal_dir = os.environ.get("IDEAL_CHART_DIR", "")

    for symbol in symbols:
        bars = None

        # 1) iDeal primary (G history + optional 05 last bar). Matriks is not used for bars.
        if _ideal_dir:
            bars = _fetch_hybrid(symbol, _ideal_dir)

        # 2) CSV fallback — resolve path relative to project root for reliability
        if bars is None:
            _csv_path = _resolve_csv_path(
                os.environ.get("BIST_EOD_CSV"),
                "data/samples/eod_prices.csv",
            )
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
        return {"status": "no_trade", "reason": "invalid result", "symbols": [], "count": 0, "trades": [], "decisions": []}
    status = result.get("status")
    reserved = {"status", "count", "trades", "reason", "symbols", "decisions", "_ctx_internal"}
    if status == "executed":
        trades = result.get("trades")
        if not isinstance(trades, list):
            return {"status": "no_trade", "reason": "invalid trades structure", "symbols": [], "count": 0, "trades": [], "decisions": []}
        normalized = {
            "status": "executed",
            "count": int(result.get("count", len(trades))),
            "trades": trades,
            "decisions": result.get("decisions") if isinstance(result.get("decisions"), list) else [],
        }
    else:
        normalized = {
            "status": "no_trade",
            "reason": result.get("reason", "unknown"),
            "symbols": result.get("symbols") or [],
            "count": 0,
            "trades": [],
            "decisions": result.get("decisions") if isinstance(result.get("decisions"), list) else [],
        }
    for k, v in result.items():
        if k not in reserved and isinstance(v, dict):
            normalized[k] = v
    return normalized


class PaperTrader:
    def __init__(
        self,
        symbols: list[str],
        *,
        data_fetcher: Callable[[list[str]], dict[str, list[OHLCVBar]]] | None = None,
        data_source: str = "ideal",
        output_path: str | Path = DEFAULT_OUTPUT_PATH,
        equity_path: str | Path = DEFAULT_EQUITY_PATH,
        state_path: str | Path = "runtime_state.json",
        interval_sec: float = DEFAULT_INTERVAL_SEC,
        threshold: float = 1.0,
        initial_capital: float = INITIAL_CAPITAL,
        execution_model: ExecutionModel | None = None,
        bist_rules: Any | None = None,
        portfolio_risk: Any | None = None,
        audit_logger: Any | None = None,
        health_monitor: Any | None = None,
    ) -> None:
        self._symbols = sorted(symbols) if symbols else ["ASELS", "THYAO", "GARAN", "KCHOL"]
        if not hasattr(self, "_positions"):
            self._positions = {}
        self._execution_model = execution_model or DEFAULT_EXECUTION_MODEL
        self._data_source = data_source
        if data_fetcher is not None:
            self._fetcher = data_fetcher
        elif data_source == "csv":
            self._fetcher = _csv_sample_fetcher
        elif data_source == "ideal":
            self._fetcher = _default_ideal_fetcher
        elif data_source == "matriks":
            self._fetcher = lambda s: {}  # placeholder
        else:
            self._fetcher = _default_ideal_fetcher
        self._output_path = Path(output_path)
        self._equity_path = Path(equity_path)
        self._state_path = Path(state_path)
        self._interval_sec = float(interval_sec) if isinstance(interval_sec, (int, float)) and interval_sec > 0 else 60.0
        self._threshold = threshold
        self._capital = float(initial_capital)
        self._consecutive_losses = 0
        if not hasattr(self, "_portfolio_exposure"):
            self._portfolio_exposure = 0.0
        if not hasattr(self, "_loop_stats"):
            self._loop_stats = {
                "cycle_count": 0,
                "error_count": 0,
                "last_error": None,
            }
        try:
            if os.path.exists(PORTFOLIO_STATE_PATH):
                with open(PORTFOLIO_STATE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                exp = data.get("exposure")
                if isinstance(exp, (int, float)):
                    self._portfolio_exposure = float(exp)
        except Exception:
            self._portfolio_exposure = 0.0

        # --- portfolio / risk config (init-only) ---
        _ic = float(initial_capital)
        self._portfolio_value = _ic
        self._cash = _ic
        self._equity = _ic
        self._max_equity = _ic
        self._risk_pct = 0.01
        self._max_positions = int(CONFIG.max_positions)
        self._allocation_mode = "equal_weight"
        self._max_drawdown = float(CONFIG.max_drawdown)
        self._max_position_pct = 0.20
        self._min_price = 5.0
        self._min_volume_proxy = 1_000_000
        self._execution_engine = PaperOrderExecutionEngine()
        self.exec_engine = ExecutionEngine()
        self._broker = PaperBrokerAdapter(self._execution_engine)
        self._exec_feature_engine = FeatureEngine()
        self._slippage = SlippageModel()
        self._spread = SpreadModel()
        self._latency = LatencyModel()
        self._bist_rules = bist_rules if bist_rules is not None else BISTRules()
        self._portfolio_risk = portfolio_risk if portfolio_risk is not None else PortfolioRiskEngine()
        self._audit = audit_logger if audit_logger is not None else AuditLogger()
        self._health = health_monitor if health_monitor is not None else HealthMonitor()
        self._strategy_metrics = StrategyMetrics()
        self._decay = StrategyDecay()
        self._meta_selector = MetaSelector()
        self._corr_engine = CorrelationEngine()
        self._depth_model = DepthModel()
        self._session = SessionEngine()
        self._circuit_breaker = CircuitBreaker()
        self._event_risk = EventRisk()
        self._volatility_shock = VolatilityShock()
        self._exposure_controller = ExposureController()
        self._capital_efficiency_boost = False
        self._trade_log: list[dict[str, Any]] = []
        self._replay_feed: Any | None = None
        self._explainer = ExplanationEngine()

    def feed_data(self, step_data: Any) -> None:
        """Research/replay: per-step market data override; consumed for the next ``run_once`` only."""
        self._replay_feed = step_data

    def _safe_audit(self, event: str, symbol: str, data: dict[str, Any]) -> None:
        try:
            self._audit.log({"event": event, "symbol": str(symbol), "data": dict(data)})
        except Exception as e:
            try:
                self._health.record_error(f"audit_log:{e}")
            except Exception:
                pass

    def get_system_health(self) -> dict[str, Any]:
        return self._health.snapshot()

    def get_strategy_metrics(self) -> dict[str, list[float]]:
        return self._strategy_metrics.get()

    def get_analytics(self) -> dict[str, Any]:
        from bist_core.analytics.performance_attribution import PerformanceAttribution
        from bist_core.analytics.trade_analytics import TradeAnalytics

        trades = getattr(self, "_trade_log", [])
        if not isinstance(trades, list):
            trades = []
        return {
            "performance": PerformanceAttribution().compute(trades),
            "trade_stats": TradeAnalytics().compute(trades),
        }

    def get_error_report(self) -> dict[str, int]:
        from bist_core.analytics.error_classifier import ErrorClassifier

        return ErrorClassifier().classify(self.get_audit_logs())

    def get_audit_logs(self) -> list[dict[str, Any]]:
        return self._audit.get_logs()

    def _clip_weights_to_portfolio_risk(self, weight_by_sym: dict[str, float]) -> dict[str, float]:
        """Scale weights down if max exceeds ``PortfolioRiskEngine.max_symbol_exposure`` (preserves ratios)."""
        if not weight_by_sym:
            return weight_by_sym
        try:
            cap_w = float(getattr(self._portfolio_risk, "max_symbol_exposure", 0.25))
        except Exception:
            cap_w = 0.25
        vals = [float(v) for v in weight_by_sym.values()]
        m = max(vals) if vals else 0.0
        if m <= cap_w + 1e-15:
            return dict(weight_by_sym)
        factor = cap_w / m
        return {k: float(v) * factor for k, v in weight_by_sym.items()}

    def _execution_adjust_price(self, price: float, bars: Any) -> float:
        """Deterministic execution path: spread + slippage (vol-based) + latency; no randomness."""
        price_adj = float(price)
        price_adj += self._spread.compute(price)
        vol_slip = 0.01
        try:
            if isinstance(bars, list) and len(bars) >= 2:
                f = self._exec_feature_engine.extract(bars, lookback=20)
                vol_slip = float(f.get("volatility", 0.01))
        except Exception:
            vol_slip = 0.01
        price_adj += self._slippage.compute(price, vol_slip)
        price_adj = self._latency.apply(price_adj)
        return float(price_adj)

    def _liquidity_ok(self, bars: Any) -> bool:
        try:
            if not isinstance(bars, list) or not bars:
                return False
            vols = [getattr(b, "volume", 0) for b in bars[-5:]]
            avg = sum(vols) / max(len(vols), 1)
            return avg > self._min_volume_proxy
        except Exception:
            return False

    def _bars_for_symbol_entry(self, sym: str) -> list[Any]:
        rf = getattr(self, "_replay_feed", None)
        use_replay = isinstance(rf, dict) and sym in rf and isinstance(rf.get(sym), dict)
        if use_replay:
            inj = rf[sym]
            b = inj.get("bars") if isinstance(inj, dict) else None
            return b if isinstance(b, list) else []
        try:
            out = _get_recent_bars(sym)
            return out if isinstance(out, list) else []
        except Exception:
            return []

    def _entry_correlation_blocked(self, sym: str, bars: list[Any]) -> bool:
        ce = getattr(self, "_corr_engine", None)
        if ce is None:
            return False
        closes_s = self._exec_feature_engine.window_closes(bars, lookback=50)
        if len(closes_s) < 2:
            return False
        for p_sym in list(self._positions.keys()):
            if p_sym == sym:
                continue
            ob = self._bars_for_symbol_entry(p_sym)
            closes_p = self._exec_feature_engine.window_closes(ob, lookback=50)
            if float(ce.correlation(closes_s, closes_p)) > 0.8:
                return True
        return False

    def _mark_to_market_equity(self) -> None:
        """Update self._equity and self._max_equity from cash + positions at mark-to-market prices."""
        total_position_value = 0.0
        for p_sym, pos in self._positions.items():
            try:
                current_price = get_current_price(p_sym)
                if isinstance(current_price, (int, float)) and current_price > 0:
                    sz = pos.get("size", 0)
                    if isinstance(sz, (int, float)):
                        total_position_value += float(current_price) * float(sz)
            except Exception:
                continue
        equity = float(self._cash) + total_position_value
        self._equity = equity
        if equity > self._max_equity:
            self._max_equity = equity

    def _calculate_position_size(self, price: float, stop_price: float) -> int:
        try:
            if not isinstance(price, (int, float)) or price <= 0:
                return 0

            if not isinstance(stop_price, (int, float)) or stop_price <= 0:
                stop_price = price * 0.97

            risk_per_share = abs(price - stop_price)
            if risk_per_share <= 0:
                return 0

            capital_at_risk = self._equity * self._risk_pct

            raw_size = capital_at_risk / risk_per_share

            # cash constraint
            max_affordable = int(self._cash // price) if price > 0 else 0

            size = int(min(raw_size, max_affordable))

            if size <= 0:
                return 0

            return size

        except Exception:
            return 0

    def _paper_entry_microstructure_ok(self, price: float, bars: Any) -> tuple[bool, str]:
        """BIST microstructure pre-entry screen. Fail-closed on exception."""
        try:
            if not isinstance(price, (int, float)) or float(price) <= 0:
                return False, "invalid_price"
            if float(price) < float(self._min_price):
                return False, "min_price"
            if bars:
                proxies: list[float] = []
                for b in bars:
                    h = float(getattr(b, "high", 0.0))
                    lo = float(getattr(b, "low", 0.0))
                    c = float(getattr(b, "close", 0.0))
                    proxies.append((h - lo) * c)
                if proxies:
                    vp = sum(proxies) / float(len(proxies))
                    if vp < float(self._min_volume_proxy):
                        return False, "low_volume_proxy"
                lb = bars[-1]
                lh = float(getattr(lb, "high", 0.0))
                ll = float(getattr(lb, "low", 0.0))
                lc = float(getattr(lb, "close", 0.0))
                if lc > 0:
                    range_pct = (lh - ll) / lc
                    if range_pct > 0.1:
                        return False, "volatility_halt"
            return True, ""
        except Exception:
            return False, "risk_check_error"

    def _apply_entry_position_pct_cap(self, price: float, size: int) -> int:
        """Hard cap single position notional vs equity."""
        try:
            if size <= 0 or not isinstance(price, (int, float)) or float(price) <= 0:
                return 0
            max_pv = float(self._equity) * float(self._max_position_pct)
            pv = float(price) * float(size)
            if pv > max_pv:
                return int(max_pv // float(price))
            # STAGE 76 — ENTRY MIN SIZE FIX
            return max(1, int(size))
        except Exception:
            return 0

    def _run_cycle(self) -> dict:
        md = self._fetcher(self._symbols)
        if not isinstance(md, dict) or not md:
            return {
                "status": "no_trade",
                "reason": "no data",
                "symbols": [],
                "count": 0,
                "trades": [],
                "decisions": decisions if "decisions" in locals() and isinstance(decisions, list) else [],
            }

        clean = {s: b for s, b in md.items() if b}
        if not clean:
            return {
                "status": "no_trade",
                "reason": "no data",
                "symbols": [],
                "count": 0,
                "trades": [],
                "decisions": decisions if "decisions" in locals() and isinstance(decisions, list) else [],
            }

        executed = []
        symbol_results = {}
        for sym in clean:
            result = {
                "action": "wait",
                "reason": None,
                "decision_source": "scoring",
                "decision_confidence": None,
                "decision_risk": None,
            }
            bars = clean.get(sym)

            # --- data integrity guard ---
            if not isinstance(bars, list) or len(bars) < 2:
                symbol_results[sym] = {
                    "action": "wait",
                    "reason": "insufficient_bars",
                    "decision_source": "scoring",
                    "decision_confidence": None,
                    "decision_risk": None,
                    "_bars_internal": bars if isinstance(bars, list) else [],
                    "_ctx_internal": {},
                }
                continue

            context = {
                "momentum": 0.0,
                "volatility_safe": 0.0,
                "confidence": 0.5,
                "trend_consistency": 0.0,
                "spike": 0.0,
            }

            # --- data reliability: volatility normalization ---
            closes = [getattr(b, "close", 0.0) for b in bars if isinstance(getattr(b, "close", None), (int, float))]
            volatility = 0.0
            if len(closes) >= 2:
                diffs = [abs(closes[i] - closes[i - 1]) for i in range(1, len(closes))]
                base = sum(closes[:-1]) / max(len(closes) - 1, 1)
                if base > 0:
                    volatility = sum(diffs) / (len(diffs) * base)
            context["market_volatility"] = _clamp(volatility, 0.0, 1.0)

            if isinstance(bars, list) and len(bars) >= 2:
                c0 = getattr(bars[0], "close", None)
                c1 = getattr(bars[-1], "close", None)

                if isinstance(c0, (int, float)) and isinstance(c1, (int, float)) and c0:
                    context["momentum"] = float((c1 - c0) / c0)

                # --- trend consistency ---
                if len(bars) >= 2:
                    if len(bars) == 2:
                        if isinstance(c0, (int, float)) and isinstance(c1, (int, float)):
                            context["trend_consistency"] = 1.0 if c1 > c0 else (0.0 if c1 < c0 else 0.5)
                    else:
                        ups = 0
                        downs = 0

                        for i in range(1, len(bars)):
                            c_prev = getattr(bars[i - 1], "close", None)
                            c_curr = getattr(bars[i], "close", None)

                            if isinstance(c_prev, (int, float)) and isinstance(c_curr, (int, float)):
                                if c_curr > c_prev:
                                    ups += 1
                                elif c_curr < c_prev:
                                    downs += 1

                        total = ups + downs
                        n_trans = len(bars) - 1

                        if total > 0:
                            tc = abs(ups - downs) / total
                            if n_trans > 0:
                                tc = tc * (total / n_trans)
                            context["trend_consistency"] = _clamp(tc, 0.0, 1.0)

                # --- volatility ---
                last = bars[-1]
                h = getattr(last, "high", None)
                lo = getattr(last, "low", None)
                cl = getattr(last, "close", None)

                if isinstance(h, (int, float)) and isinstance(lo, (int, float)) and isinstance(cl, (int, float)) and cl > 0:
                    context["volatility_safe"] = float((h - lo) / cl)

                # --- spike ---
                prev = getattr(bars[-2], "close", None)
                curr = getattr(bars[-1], "close", None)

                if isinstance(prev, (int, float)) and isinstance(curr, (int, float)) and prev:
                    move = abs(curr - prev) / abs(prev)

                    if move > 0.10:
                        context["spike"] = 1.0
                    elif move > 0.05:
                        context["spike"] = 0.5

            if isinstance(bars, list) and bars:
                last_close = getattr(bars[-1], "close", None)
                if isinstance(last_close, (int, float)):
                    context["signal_price"] = float(last_close)

                # --- current price (live-aware, deterministic) ---
                current_price = get_current_price(sym)

                if isinstance(current_price, (int, float)) and current_price > 0:
                    context["current_price"] = float(current_price)
                    context["price_source"] = "live"
                else:
                    last_close = None
                    if isinstance(bars, list) and len(bars) > 0:
                        try:
                            last_close = float(bars[-1].close)
                        except Exception:
                            last_close = None

                    if isinstance(last_close, (int, float)) and last_close > 0:
                        context["current_price"] = float(last_close)
                        context["price_source"] = "bar_fallback"
                    else:
                        context["current_price"] = None
                        context["price_source"] = "none"

            # --- base confidence ---
            context["confidence"] = _clamp(
                0.35 + 0.6 * max(0.0, context["momentum"]),
                0.0,
                1.0,
            )

            if isinstance(context, dict):
                if all((not isinstance(v, (int, float)) or v == 0.0) for v in context.values()):
                    context = None

            result["_bars_internal"] = bars
            result["_ctx_internal"] = context if isinstance(context, dict) else {}
            symbol_results[sym] = result

        # --- aggregate context across symbols ---
        contexts = []
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    contexts.append(ctx)

        avg_momentum = 0.0
        avg_volatility = 0.0
        avg_confidence = 0.0
        n = len(contexts)
        if n > 0:
            avg_momentum = sum(c.get("momentum", 0.0) for c in contexts) / n
            avg_volatility = sum(c.get("volatility_safe", 0.0) for c in contexts) / n
            avg_confidence = sum(c.get("confidence", 0.0) for c in contexts) / n

        regime_trend = 0.0
        regime_vol = 0.0
        if n > 0:
            regime_trend = avg_momentum
            regime_vol = avg_volatility
        regime_trend = _clamp(regime_trend, -1.0, 1.0)
        regime_vol = _clamp(regime_vol, 0.0, 1.0)

        # --- noise (single source, before entropy precompute) ---
        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue
            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue
            mom = ctx.get("momentum", 0.0)
            vol = ctx.get("volatility_safe", 0.0)
            consistency = ctx.get("trend_consistency", 0.0)
            spike = ctx.get("spike", 0.0)
            if not isinstance(mom, (int, float)):
                mom = 0.0
            if not isinstance(spike, (int, float)):
                spike = 0.0
            # --- base noise ---
            noise = 0.0
            if abs(mom) < 0.01:
                noise += 0.3
            if isinstance(vol, (int, float)) and vol > 0.08:
                noise += 0.2
            if regime_trend > 0 and mom < 0:
                noise += 0.3
            elif regime_trend < 0 and mom > 0:
                noise += 0.3
            if isinstance(consistency, (int, float)) and consistency < 0.4:
                noise += 0.3

            # --- nonlinear scaling (first) ---
            noise = noise / (1.0 + 0.8 * noise)

            # --- spike contribution (after scaling) ---
            if spike > 0:
                if mom > 0:
                    noise += 0.15 * spike
                else:
                    noise += 0.6 * spike

            # --- alignment refinement (final adjustment) ---
            if isinstance(mom, (int, float)) and isinstance(regime_trend, (int, float)):
                if mom * regime_trend > 0:
                    noise *= 0.85

            # --- final clamp ---
            noise = _clamp(noise, 0.0, 1.0)
            if noise < 0.05:
                noise *= 0.5
            ctx["noise"] = noise

            # --- entropy (immediately after final noise) ---
            consistency = ctx.get("trend_consistency", 0.0)
            if not isinstance(consistency, (int, float)):
                consistency = 0.0
            entropy = 0.7 * noise + 0.3 * (1.0 - consistency)
            entropy = entropy ** 1.3
            entropy = _clamp(entropy, 0.0, 1.0)
            ctx["entropy"] = entropy

        # --- collect entropy inputs (read-only, uses final entropy) ---
        entropy_inputs = []
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    ent = ctx.get("entropy")
                    if isinstance(ent, (int, float)):
                        entropy_inputs.append(ent)
                    else:
                        entropy_inputs.append(0.5)

        ent_min = min(entropy_inputs) if entropy_inputs else 0.0
        ent_max = max(entropy_inputs) if entropy_inputs else 1.0
        ent_spread = max(ent_max - ent_min, 1e-6)

        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue
            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue

            base_conf = ctx.get("confidence", 0.0)
            if not isinstance(base_conf, (int, float)):
                base_conf = 0.0
            ctx["_base_confidence"] = base_conf

            mom = ctx.get("momentum", 0.0)
            vol = ctx.get("volatility_safe", 0.0)
            consistency = ctx.get("trend_consistency", 0.0)
            spike = ctx.get("spike", 0.0)

            if not isinstance(mom, (int, float)):
                mom = 0.0
            if not isinstance(spike, (int, float)):
                spike = 0.0

            # --- momentum strength ---
            mom_strength = 0.0
            if isinstance(mom, (int, float)):
                if mom > 0:
                    mom_strength = min(mom / 0.05, 1.0)
                elif mom < 0:
                    mom_strength = -min(abs(mom) / 0.05, 1.0)
            ctx["momentum_strength"] = mom_strength

            # --- spike quality ---
            spike_quality = 0.0
            if spike > 0:
                if mom > 0:
                    spike_quality = 1.0  # bullish expansion
                elif mom < 0:
                    spike_quality = -1.0  # bearish expansion
                else:
                    spike_quality = 0.0
            ctx["spike_quality"] = spike_quality

            noise = ctx.get("noise", 0.0)
            if not isinstance(noise, (int, float)):
                noise = 0.0

            # --- regime alignment ---
            regime_alignment = 0.0
            if isinstance(mom, (int, float)) and isinstance(regime_trend, (int, float)):
                if mom * regime_trend > 0:
                    regime_alignment = 1.0
                elif mom * regime_trend < 0:
                    regime_alignment = -1.0
                else:
                    regime_alignment = 0.0
            ctx["regime_alignment"] = regime_alignment

            rel_strength = 0.0
            if ctx.get("momentum", 0.0) > avg_momentum:
                rel_strength += 0.4
            if ctx.get("volatility_safe", 0.0) < avg_volatility:
                rel_strength += 0.3
            if ctx.get("_base_confidence", 0.0) > avg_confidence:
                rel_strength += 0.3
            rel_strength = _clamp(rel_strength, 0.0, 1.0)

            base_conf = ctx.get("_base_confidence", 0.0)

            trend_boost = 1.0
            if regime_trend > 0:
                if mom > 0:
                    trend_boost = 1.1
                else:
                    trend_boost = 0.8
            elif regime_trend < 0:
                if mom < 0:
                    trend_boost = 1.1
                else:
                    trend_boost = 0.8

            consistency_boost = 1.0 + (0.2 * consistency)

            vol_penalty = 1.0 - (regime_vol * 0.5)
            noise_penalty = 1.0 - noise

            adjusted = base_conf * (0.6 + 0.4 * rel_strength)
            adjusted = adjusted * trend_boost * consistency_boost * vol_penalty * noise_penalty

            spike_q = ctx.get("spike_quality", 0.0)
            if isinstance(spike_q, (int, float)):
                if spike_q > 0:
                    adjusted *= 1.05  # reward bullish expansion
                elif spike_q < 0:
                    adjusted *= 0.85  # penalize bearish expansion

            align = ctx.get("regime_alignment", 0.0)
            if isinstance(align, (int, float)):
                if align > 0:
                    adjusted *= 1.05  # aligned with regime
                elif align < 0:
                    adjusted *= 0.85  # against regime

            # --- consistency score (continuous) ---
            consistency_score = 0.0
            trend = ctx.get("trend_consistency", 0.0)
            if isinstance(mom, (int, float)) and isinstance(trend, (int, float)):
                pos_strength = max(mom, 0.0)
                trend_strength = max(trend, 0.0)
                consistency_score = (pos_strength / 0.05) * trend_strength
                consistency_score = _clamp(consistency_score, 0.0, 1.0)
            ctx["consistency_score"] = consistency_score

            # --- cross-signal agreement (continuous) ---
            agreement_score = 0.0
            _mom = ctx.get("momentum", 0.0)
            _consistency = ctx.get("trend_consistency", 0.0)
            _noise = ctx.get("noise", 0.0)
            _vol = ctx.get("volatility_safe", 0.0)

            if isinstance(_mom, (int, float)) and isinstance(_consistency, (int, float)):
                agreement_score += _clamp((_mom / 0.05), 0.0, 1.0) * _consistency * 0.4

            if isinstance(_noise, (int, float)):
                agreement_score += (1.0 - _clamp(_noise, 0.0, 1.0)) * 0.3

            if isinstance(_vol, (int, float)):
                vol_score = 1.0 - _clamp(abs(_vol - 0.04) / 0.04, 0.0, 1.0)
                agreement_score += vol_score * 0.3

            agreement_score = _clamp(agreement_score, 0.0, 1.0)
            ctx["agreement_score"] = agreement_score

            # --- internal consistency delta (no temporal dependency) ---
            conf = ctx.get("confidence", adjusted)
            spread = ctx.get("_conf_spread", conf)
            delta = 0.0
            if isinstance(conf, (int, float)) and isinstance(spread, (int, float)):
                delta = abs(conf - spread)
            ctx["_conf_delta"] = _clamp(delta, 0.0, 1.0)

            # --- reliability score (structure-based, not history) ---
            reliability = 0.0
            noise = ctx.get("noise", 0.0)
            agreement = ctx.get("agreement_score", 0.0)
            consistency = ctx.get("consistency_score", 0.0)
            delta = ctx.get("_conf_delta", 0.0)
            if isinstance(noise, (int, float)) and noise < 0.4:
                reliability += 0.3
            if isinstance(agreement, (int, float)) and agreement > 0.5:
                reliability += 0.3
            if isinstance(consistency, (int, float)) and consistency > 0.4:
                reliability += 0.2
            if isinstance(delta, (int, float)) and delta < 0.15:
                reliability += 0.2
            reliability = _clamp(reliability, 0.0, 1.0)
            ctx["reliability_score"] = reliability

            ctx["relative_strength"] = rel_strength

            # --- entropy norm (inline, cross-symbol) ---
            ent = ctx.get("entropy", 0.0)
            if not isinstance(ent, (int, float)):
                ent = 0.0
            if ent_spread > 1e-6:
                ent_norm = (ent - ent_min) / ent_spread
            else:
                ent_norm = 0.5
            ent_norm = _clamp(ent_norm, 0.0, 1.0)
            ent_norm = ent_norm ** 0.85
            ctx["_entropy_norm"] = ent_norm

            adjusted *= 1.0 - 0.5 * ent_norm
            if ent_norm < 0.3:
                adjusted *= 1.05
            elif ent_norm > 0.7:
                adjusted *= 0.9

            # --- calibration ---
            _cons = ctx.get("consistency_score", 0.0)
            _agr = ctx.get("agreement_score", 0.0)
            if not isinstance(_cons, (int, float)):
                _cons = 0.0
            if not isinstance(_agr, (int, float)):
                _agr = 0.0
            calibration = 0.5 * _cons + 0.5 * _agr
            adjusted = adjusted * (0.8 + 0.4 * calibration)

            # --- compression ---
            if isinstance(adjusted, (int, float)) and adjusted > 0:
                adjusted = adjusted / (1.0 + 0.5 * adjusted)
            if adjusted < 0.2:
                adjusted *= 0.9 + 0.1 * adjusted

            # --- reliability application (final stage) ---
            rel = ctx.get("reliability_score", 0.0)
            delta = ctx.get("_conf_delta", 0.0)
            if isinstance(rel, (int, float)):
                adjusted *= 0.85 + 0.3 * rel
            if isinstance(delta, (int, float)) and delta > 0.25:
                adjusted *= 1.0 - 0.5 * (delta - 0.25)

            _noise = ctx.get("noise", 0.0)
            if not isinstance(_noise, (int, float)):
                _noise = 0.0
            stability = 1.0 - _noise
            ctx["stability"] = _clamp(stability, 0.0, 1.0)

            ctx["_adj"] = 0.0 if adjusted < 0.01 else adjusted

        # --- confidence normalization (cross-symbol deterministic) ---
        conf_vals = []
        for s, r in symbol_results.items():
            c = r.get("_ctx_internal", {}).get("_adj")
            if isinstance(c, (int, float)):
                conf_vals.append(c)
        c_min = min(conf_vals) if conf_vals else 0.0
        c_max = max(conf_vals) if conf_vals else 1.0
        c_spread_raw = c_max - c_min
        c_spread = max(c_spread_raw, 1e-6)
        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue
            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue
            raw = ctx.get("_adj", 0.0)
            if not isinstance(raw, (int, float)):
                raw = 0.0
            if c_spread_raw < 1e-6:
                ctx["_adj"] = raw
            else:
                norm = (raw - c_min) / c_spread
                norm = _clamp(norm, 0.0, 1.0)
                norm = norm / (1.0 + 0.5 * norm)
                ctx["_adj"] = norm

        conf_list = []
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    val = ctx.get("_adj")
                    if isinstance(val, (int, float)):
                        conf_list.append(val)

        conf_threshold = 0.0
        if conf_list:
            sorted_conf = sorted(conf_list, reverse=True)
            k = max(1, int(len(sorted_conf) * 0.3))
            top_slice = sorted_conf[:k]
            conf_threshold = min(top_slice)

        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue
            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue
            conf = ctx.get("_adj", 0.0)
            if not isinstance(conf, (int, float)):
                conf = 0.0
            if conf < conf_threshold:
                gap = conf_threshold - conf
                penalty = _clamp(gap / max(conf_threshold, 1e-6), 0.0, 1.0)
                final_conf = conf * (1.0 - 0.7 * penalty)
                ctx["competition_penalty"] = penalty
            else:
                final_conf = conf
                ctx["competition_penalty"] = 0.0
            ctx["confidence"] = _clamp(final_conf, 0.0, 1.0)

        # --- smoothing (anti-spike / anti-noise) — applied before calibration ---
        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue

            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue

            val = ctx.get("confidence")
            if not isinstance(val, (int, float)):
                ctx["confidence"] = 0.0
                continue

            consistency = ctx.get("trend_consistency", 0.0)
            noise = ctx.get("noise", 0.0)
            spike = ctx.get("spike", 0.0)

            if not isinstance(consistency, (int, float)):
                consistency = 0.0
            if not isinstance(noise, (int, float)):
                noise = 0.0
            if not isinstance(spike, (int, float)):
                spike = 0.0

            smooth_factor = 1.0
            smooth_factor *= (1.0 - 0.5 * noise)
            smooth_factor *= (1.0 - 0.4 * spike)
            smooth_factor *= (1.0 + 0.3 * consistency)
            smooth_factor = _clamp(smooth_factor, 0.2, 1.5)

            ctx["confidence"] = _clamp(val * smooth_factor, 0.0, 1.0)

        # --- confidence calibration (cross-symbol normalization) ---
        conf_vals = []
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    adj_val = ctx.get("_adj")
                    if isinstance(adj_val, (int, float)):
                        conf_vals.append(adj_val)

        conf_min = 0.0
        conf_max = 0.0
        if conf_vals:
            conf_min = min(conf_vals)
            conf_max = max(conf_vals)

        spread = conf_max - conf_min

        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue

            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue

            adjusted = ctx.get("_adj", 0.0)
            if not isinstance(adjusted, (int, float)):
                ctx["confidence"] = 0.0
                continue

            if spread > 1e-6:
                adj_val = ctx.get("_adj", 0.0)
                if isinstance(adj_val, (int, float)):
                    norm = (adj_val - conf_min) / spread
                else:
                    norm = 0.5
            else:
                norm = 0.5  # flat regime fallback

            # correct blending using current adjusted signal (full pipeline)
            adjusted = adjusted * (0.5 + 0.5 * norm)

            # --- diminishing returns compression ---
            if isinstance(adjusted, (int, float)) and adjusted > 0:
                compressed = adjusted / (1.0 + 0.5 * adjusted)
                adjusted = compressed

            # preserve small signal differences
            if adjusted < 0.2:
                adjusted *= 0.9 + 0.1 * adjusted

            ctx["_conf_spread"] = adjusted
            ctx["confidence"] = _clamp(adjusted, 0.0, 1.0)

        # --- regime-aware entry hint ---
        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue

            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue

            conf = ctx.get("confidence", 0.0)
            vol = ctx.get("volatility_safe", 0.0)
            noise = ctx.get("noise", 0.0)

            if not isinstance(conf, (int, float)):
                conf = 0.0
            if not isinstance(vol, (int, float)):
                vol = 0.0
            if not isinstance(noise, (int, float)):
                noise = 0.0

            # base threshold suggestion
            entry_hint = 0.5

            # trending regime → allow easier entries
            if regime_trend > 0:
                entry_hint -= 0.1

            # high volatility → require stronger confidence
            if regime_vol > 0.08:
                entry_hint += 0.1

            # noisy environment → stricter
            if noise > 0.5:
                entry_hint += 0.1

            # strong signal → relax threshold
            if conf > 0.7:
                entry_hint -= 0.1

            entry_hint = _clamp(entry_hint, 0.3, 0.7)

            ctx["entry_hint"] = entry_hint
            ctx["entry_margin"] = conf - entry_hint

        # --- build ranking ---
        rank_list = []
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    conf = ctx.get("confidence")
                    if isinstance(conf, (int, float)):
                        rank_list.append((sym, conf))

        rank_list.sort(key=lambda x: x[1], reverse=True)

        top_conf = 0.0
        if rank_list:
            top_conf = rank_list[0][1]

        # --- apply relative suppression ---
        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue

            ctx = res.get("_ctx_internal")
            if not isinstance(ctx, dict):
                continue

            conf = ctx.get("confidence", 0.0)

            if not isinstance(conf, (int, float)):
                continue

            if top_conf > 0:
                relative = conf / top_conf
            else:
                relative = 0.0

            if relative < 0.6:
                penalty = 0.6 - relative
                penalty = _clamp(penalty, 0.0, 1.0)

                adjusted = conf * (1.0 - 0.7 * penalty)
                adjusted = _clamp(adjusted, 0.0, 1.0)

                ctx["confidence"] = adjusted
                ctx["relative_score"] = relative
            else:
                ctx["relative_score"] = relative

        # --- final confidence propagation (single source) ---
        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                ctx = res.get("_ctx_internal")
                if isinstance(ctx, dict):
                    val = ctx.get("confidence")
                    if isinstance(val, (int, float)):
                        res["decision_confidence"] = float(val)
                    else:
                        res["decision_confidence"] = 0.0
                else:
                    res["decision_confidence"] = 0.0

        decision_engine = getattr(self, "decision_engine", None)

        for sym, res in symbol_results.items():
            if not isinstance(res, dict):
                continue

            bars = res.get("_bars_internal")
            ctx = res.get("_ctx_internal")

            decision_preview = None

            if decision_engine is not None and hasattr(decision_engine, "evaluate_symbol"):
                if bars:
                    try:
                        if isinstance(ctx, dict):
                            decision_preview = decision_engine.evaluate_symbol(bars, context=ctx)
                        else:
                            decision_preview = decision_engine.evaluate_symbol(bars)
                    except TypeError:
                        try:
                            decision_preview = decision_engine.evaluate_symbol(bars)
                        except Exception:
                            decision_preview = None
                    except Exception:
                        decision_preview = None

            # --- side propagation (single source) ---
            decision = decision_preview if isinstance(decision_preview, dict) else None
            side = "buy"
            if isinstance(decision, dict):
                s = decision.get("side")
                if s in ("buy", "sell"):
                    side = s
            if isinstance(ctx, dict):
                ctx["side"] = side

                # --- execution price (market-aware) ---
                signal_price = ctx.get("signal_price")
                exec_price = None
                if isinstance(signal_price, (int, float)):
                    exec_price = apply_execution_cost(signal_price, side)
                ctx["exec_price"] = exec_price

                # --- entry validation (volatility-adaptive) ---
                current_price = ctx.get("current_price")
                volatility = ctx.get("market_volatility", 0.0)
                entry_diff = 0.0
                entry_valid = True
                if isinstance(exec_price, (int, float)) and isinstance(current_price, (int, float)) and exec_price > 0:
                    if side == "buy":
                        entry_diff = (current_price - exec_price) / exec_price
                    elif side == "sell":
                        entry_diff = (exec_price - current_price) / exec_price
                    else:
                        entry_diff = 0.0
                    dynamic_threshold = 0.02 + 0.5 * (volatility if isinstance(volatility, (int, float)) else 0.0)
                    entry_valid = entry_diff <= dynamic_threshold
                ctx["entry_diff"] = entry_diff
                ctx["entry_valid"] = entry_valid

                # --- entry quality (nonlinear) ---
                entry_diff_val = ctx.get("entry_diff", 0.0)
                entry_quality = 1.0
                if isinstance(entry_diff_val, (int, float)):
                    entry_quality = 1.0 / (1.0 + 6.0 * max(entry_diff_val, 0.0))
                ctx["entry_quality"] = entry_quality

                # --- confidence: final market-integrated shaping ---
                adjusted = ctx.get("_adj", 0.0)
                if isinstance(adjusted, (int, float)):
                    adjusted = adjusted * ctx.get("entry_quality", 1.0)
                    vol = ctx.get("market_volatility", 0.0)
                    if isinstance(vol, (int, float)):
                        adjusted = adjusted * (1.0 / (1.0 + 2.0 * vol))
                    adjusted = _clamp(adjusted, 0.0, 1.0)
                    ctx["_adj"] = 0.0 if adjusted < 0.01 else adjusted

                # --- risk model: position sizing (deterministic) ---
                base_capital = float(
                    getattr(self._execution_model, "initial_capital", None) or 100000
                )
                confidence = ctx.get("_adj", 0.0)
                vol = ctx.get("market_volatility", 0.0)
                if not isinstance(confidence, (int, float)):
                    confidence = 0.0
                if not isinstance(vol, (int, float)):
                    vol = 0.0
                risk_fraction = 0.01 * (0.5 + 0.5 * confidence) * (1.0 - 0.5 * vol)
                risk_fraction = _clamp(risk_fraction, 0.001, 0.02)
                max_position_pct = 0.02
                position_value = base_capital * risk_fraction
                position_value = min(position_value, base_capital * max_position_pct)
                qty = 0.0
                if isinstance(exec_price, (int, float)) and exec_price > 0:
                    qty = position_value / exec_price
                ctx["position_size"] = qty

            # --- extract decision ---
            decision_action = None
            decision_reason = None
            decision_risk = None

            if isinstance(decision_preview, dict):
                da = decision_preview.get("action")
                if da in ("enter", "wait", "skip"):
                    decision_action = da

                dr = decision_preview.get("reason")
                if isinstance(dr, str):
                    decision_reason = dr

                rv = decision_preview.get("risk")
                if isinstance(rv, dict):
                    decision_risk = rv

            # --- final action ---
            action = "wait"
            if decision_action is not None:
                action = decision_action

            if decision_action == "skip":
                action = "skip"

            if (
                action == "enter"
                and isinstance(decision_risk, dict)
                and decision_risk.get("allow_enter") is False
            ):
                action = "wait"

            res["action"] = action

            # --- reason ---
            if decision_action == "skip" and decision_reason:
                res["reason"] = decision_reason
            elif (
                isinstance(decision_risk, dict)
                and decision_risk.get("allow_enter") is False
            ):
                rr = decision_risk.get("reason")
                if isinstance(rr, str) and not res.get("reason"):
                    res["reason"] = rr

            if not isinstance(res.get("reason"), str):
                res["reason"] = ""

            # --- decision source ---
            if decision_action is None:
                res["decision_source"] = "scoring"
            elif action == decision_action:
                res["decision_source"] = "decision_contextual"
            else:
                res["decision_source"] = "risk_adjusted"

            res["decision_risk"] = decision_risk if isinstance(decision_risk, dict) else {}

        # --- execution (BIST-compliant, deterministic, stateful) ---
        max_total_exposure_pct = 0.2
        base_capital = float(getattr(self._execution_model, "initial_capital", None) or 100000)
        current_exposure = float(getattr(self, "_portfolio_exposure", 0.0))

        # --- safety reset ---
        if current_exposure > base_capital * 0.5:
            current_exposure = 0.0

        for sym, res in symbol_results.items():
            if not isinstance(res, dict) or res.get("action") != "enter":
                continue

            ctx = res.get("_ctx_internal")
            side = "buy"
            entry_valid = True
            qty = 0
            price = None

            if isinstance(ctx, dict):
                side = ctx.get("side", "buy")
                entry_valid = ctx.get("entry_valid", True)

                raw_price = ctx.get("exec_price")
                if isinstance(raw_price, (int, float)) and raw_price > 0:
                    tick = get_tick_size(raw_price)
                    if side == "buy":
                        price = math.ceil(raw_price / tick) * tick
                    elif side == "sell":
                        price = math.floor(raw_price / tick) * tick
                    else:
                        price = raw_price

                    if isinstance(price, (int, float)) and isinstance(tick, (int, float)) and tick > 0:
                        price = round(round(price / tick) * tick, 4)

                raw_qty = ctx.get("position_size", 0.0)
                if isinstance(raw_qty, (int, float)):
                    qty = int(raw_qty)

            confidence = ctx.get("_adj", 0.0) if isinstance(ctx, dict) else 0.0
            entry_quality = ctx.get("entry_quality", 0.0) if isinstance(ctx, dict) else 0.0

            skip_trade = (
                entry_valid is False
                or qty <= 0
                or not isinstance(confidence, (int, float)) or confidence < 0.15
                or not isinstance(entry_quality, (int, float)) or entry_quality < 0.2
            )

            notional = 0.0
            if isinstance(price, (int, float)) and isinstance(qty, int):
                notional = price * qty

            if notional < 100:
                skip_trade = True

            if base_capital > 0:
                if current_exposure + notional > base_capital * max_total_exposure_pct:
                    skip_trade = True

            if not skip_trade and isinstance(price, (int, float)):
                trade = {
                    "symbol": sym,
                    "action": "enter",
                    "side": side,
                    "price": price,
                    "qty": int(qty),
                    "notional": notional,
                    "fill_type": "simulated",
                    "execution_cost_applied": True,
                }

                executed.append(trade)
                current_exposure += notional

                # --- append trade log (jsonl, safe append) ---
                try:
                    os.makedirs(RUNTIME_DIR, exist_ok=True)
                    with open(TRADES_LOG_PATH, "a", encoding="utf-8") as f:
                        f.write(json.dumps(trade, separators=(",", ":")) + "\n")
                except Exception:
                    pass

        self._portfolio_exposure = current_exposure

        _atomic_write_json(
            PORTFOLIO_STATE_PATH,
            {
                "exposure": float(current_exposure),
                "timestamp": int(time.time()),
            },
        )

        for sym, res in symbol_results.items():
            if isinstance(res, dict):
                if "_bars_internal" in res:
                    del res["_bars_internal"]

                if "_ctx_internal" in res:
                    ctx = res.get("_ctx_internal")
                    if isinstance(ctx, dict):
                        for k in [
                            "_base_confidence",
                            "competition_penalty",
                            "trend_consistency",
                            "spike",
                            "spike_quality",
                            "regime_alignment",
                            "momentum_strength",
                            "consistency_score",
                            "agreement_score",
                            "entropy",
                            "_entropy_norm",
                            "reliability_score",
                            "_conf_delta",
                            "_conf_spread",
                            "_adj",
                            "entry_hint",
                            "entry_margin",
                            "relative_score",
                            "signal_price",
                            "current_price",
                            "exec_price",
                            "entry_diff",
                            "entry_valid",
                            "entry_quality",
                            "market_volatility",
                            "position_size",
                            "side",
                            "_entry_zone",
                            "price_source",
                        ]:
                            if k in ctx:
                                del ctx[k]
                    del res["_ctx_internal"]

        # derive decisions from symbol_results (deterministic order by clean)
        decisions = []
        if isinstance(symbol_results, dict):
            for sym in clean:
                res = symbol_results.get(sym)
                if isinstance(res, dict):
                    decisions.append({
                        "symbol": sym,
                        "action": res.get("action"),
                    })

        # derive status
        status = "executed" if isinstance(executed, list) and executed else "no_trade"

        # derive no_trade_reason deterministically from final actions
        no_trade_reason = "no executable trades"
        if isinstance(symbol_results, dict) and symbol_results:
            actions = [
                v.get("action")
                for v in symbol_results.values()
                if isinstance(v, dict)
            ]
            if actions:
                if all(a == "skip" for a in actions):
                    no_trade_reason = "all_skipped"
                elif all(a in ("wait", "skip") for a in actions):
                    no_trade_reason = "no_valid_entries"

        # build output (single source)
        if status == "executed":
            out = {
                "status": status,
                "trades": executed,
                "count": len(executed),
                "decisions": decisions,
            }
        else:
            out = {
                "status": status,
                "reason": no_trade_reason,
                "symbols": list(clean.keys()),
                "count": 0,
                "trades": [],
                "decisions": decisions,
            }

        out.update(symbol_results)
        return out

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
        try:
            return self._run_once_impl()
        except Exception as e:
            try:
                self._health.record_error(str(e))
            except Exception:
                pass
            raise

    def _run_once_impl(self) -> dict:
        results = []
        now = int(time.time())
        drawdown = 0.0

        symbols = getattr(self, "_symbols", [])
        prepared: list[tuple[str, float, list[Any]]] = []
        symbol_contexts: dict[str, dict[str, Any]] = {}

        for sym in symbols:
            rf = getattr(self, "_replay_feed", None)
            use_replay = isinstance(rf, dict) and sym in rf and isinstance(rf.get(sym), dict)
            if use_replay:
                inj = rf[sym]
                price = inj.get("current_price")
                bars = inj.get("bars")
            else:
                try:
                    price = get_current_price(sym)
                except Exception:
                    price = None

                if not isinstance(price, (int, float)) or price <= 0:
                    continue

                bars = _get_recent_bars(sym)

                if not bars:
                    bars = _fallback_bars_from_ideal(sym)

            if not isinstance(price, (int, float)) or price <= 0:
                continue
            if not isinstance(bars, list):
                bars = []
            if use_replay and len(bars) < 1:
                continue

            fp = float(price)
            symbol_contexts[sym] = {
                "symbol": sym,
                "current_price": fp,
                "bars": bars,
            }
            prepared.append((sym, fp, bars))

        ranked_lookup: dict[str, dict[str, Any]] = {}
        top_symbols: set[str] = set()
        meta_by_sym: dict[str, tuple[int, float]] = {}
        use_ranking = False
        weight_by_sym: dict[str, float] = {}
        full_ranked: list[dict[str, Any]] = []
        portfolio_rows: list[dict[str, Any]] = []
        top_n = int(getattr(self, "_max_positions", 5) or 5)
        if top_n < 1:
            top_n = 1

        perf = self._strategy_metrics.rolling_performance()
        meta_weights = self._meta_selector.select(perf)

        if (
            symbol_contexts
            and hasattr(self, "decision_engine")
            and self.decision_engine
        ):
            try:
                full_ranked = AdvancedRanker(engine=self.decision_engine).rank(
                    symbol_contexts
                )
            except Exception:
                full_ranked = []
            else:
                if full_ranked:
                    use_ranking = True
                    ranked_lookup = {
                        str(r["symbol"]): r["decision"]
                        for r in full_ranked
                        if isinstance(r.get("decision"), dict)
                    }
                    meta_by_sym = {
                        str(r["symbol"]): (i, float(r["rank_score"]))
                        for i, r in enumerate(full_ranked, start=1)
                    }
                    top_symbols = {
                        r["symbol"] for r in full_ranked[:top_n]
                    }
                    portfolio_rows = PortfolioEngine(top_n=top_n).allocate(full_ranked)
                    weight_by_sym = {
                        str(p["symbol"]): float(p["weight"]) for p in portfolio_rows
                    }

        if not use_ranking and hasattr(self, "decision_engine") and self.decision_engine:
            top_symbols = {s for s, _, _ in prepared}
            n = max(len(top_symbols), 1)
            weight_by_sym = {s: 1.0 / n for s in top_symbols}

        if not weight_by_sym and prepared:
            n = max(len(prepared), 1)
            w = 1.0 / n
            weight_by_sym = {sym: w for sym, _, _ in prepared}

        self._mark_to_market_equity()

        self._capital_efficiency_boost = False
        try:
            unused_cash = float(self._cash) / (float(self._equity) + 1e-6)
            if unused_cash > 0.3 and weight_by_sym:
                self._capital_efficiency_boost = True
                for k in list(weight_by_sym.keys()):
                    weight_by_sym[k] = float(weight_by_sym[k]) * 1.1
                s_w = sum(weight_by_sym.values())
                if s_w > 0:
                    weight_by_sym = {k: float(v) / s_w for k, v in weight_by_sym.items()}
        except Exception:
            self._capital_efficiency_boost = False

        weight_by_sym = self._clip_weights_to_portfolio_risk(weight_by_sym)

        portfolio_for_validate = [
            {"symbol": s, "weight": float(w)}
            for s, w in sorted(weight_by_sym.items(), key=lambda x: x[0])
        ]
        pg_ok, pg_reason = self._portfolio_risk.validate(
            portfolio_for_validate,
            float(self._equity),
            float(self._max_equity),
        )

        self._safe_audit(
            "decision",
            "*",
            {
                "kind": "ranking",
                "use_ranking": use_ranking,
                "summary": [
                    {"symbol": r.get("symbol"), "rank_score": r.get("rank_score")}
                    for r in full_ranked[:50]
                ],
            },
        )
        self._safe_audit(
            "decision",
            "*",
            {"kind": "portfolio", "allocation": portfolio_rows, "weights": dict(weight_by_sym)},
        )
        self._safe_audit(
            "risk",
            "*",
            {"kind": "portfolio_risk", "ok": pg_ok, "reason": pg_reason},
        )

        for sym, price, bars in prepared:
            exec_price_out = 0.0
            target_capital_per_position = float(self._equity) * float(weight_by_sym.get(sym, 0.0))
            risk_blocked = False
            risk_reason = ""
            risk_global_blocked = not pg_ok
            risk_global_reason = pg_reason if not pg_ok else ""
            order_id = ""
            order_status = ""

            context = symbol_contexts[sym]

            decision: dict[str, Any] | None = None
            if use_ranking:
                decision = ranked_lookup.get(sym)
            if decision is None and hasattr(self, "decision_engine") and self.decision_engine:
                try:
                    decision = self.decision_engine.evaluate_symbol(context)
                except Exception:
                    decision = None

            if not isinstance(decision, dict):
                continue

            decision_for_explain = dict(decision)
            decision_for_explain["symbol"] = sym
            explanation = self._explainer.explain(decision_for_explain)
            self._safe_audit(
                "decision",
                sym,
                {
                    "kind": "symbol",
                    "action": decision.get("action"),
                    "score": decision.get("score"),
                    "reason": decision.get("reason"),
                    "explanation": explanation,
                },
            )

            action = decision.get("action")
            reason = decision.get("reason", "")

            # --- ACTION VALIDATION ---
            if action not in ("enter", "hold", "exit"):
                continue

            pos = self._positions.get(sym)

            # --- POSITION STATE MACHINE (STRICT & SINGLE SOURCE OF TRUTH) ---

            if action == "enter":
                if use_ranking and sym not in top_symbols:
                    continue
                risk_blocked = False
                risk_reason = ""
                w_sym = float(weight_by_sym.get(sym, 0.0))
                pos_syms = list(self._positions.keys())
                total_exposure = sum(float(weight_by_sym.get(s, 0.0)) for s in pos_syms)
                w_adj = self._exposure_controller.adjust(total_exposure, w_sym)
                if w_adj <= 0.0:
                    risk_blocked = True
                    risk_reason = "exposure_cap"
                else:
                    target_capital_per_position = float(self._equity) * w_adj
                equity_ratio_dd = float(self._equity) / (float(self._max_equity) + 1e-6)
                if not risk_blocked and equity_ratio_dd < 0.8:
                    risk_blocked = True
                    risk_reason = "drawdown_entries_blocked"
                if risk_global_blocked:
                    risk_blocked = True
                    risk_reason = risk_global_reason or "portfolio_risk"
                elif not risk_blocked:
                    br = self._bist_rules
                    if not br.is_price_valid(price):
                        risk_blocked = True
                        risk_reason = "bist_price_invalid"
                    elif not br.is_liquid(bars):
                        risk_blocked = True
                        risk_reason = "bist_illiquid"
                    else:
                        pc = _prev_close_for_bist(bars)
                        if pc is None:
                            try:
                                pc = float(price)
                            except (TypeError, ValueError):
                                risk_blocked = True
                                risk_reason = "bist_no_prev_close"
                        if not risk_blocked and not br.is_trade_allowed(float(price), float(pc)):
                            risk_blocked = True
                            risk_reason = "bist_daily_band"

                if not risk_blocked:
                    if not self._liquidity_ok(bars):
                        risk_blocked = True
                        risk_reason = "liquidity_filter"
                if not risk_blocked:
                    sec = get_sector(sym)
                    w_pos = sum(
                        float(weight_by_sym.get(p, 0.0))
                        for p in pos_syms
                        if get_sector(p) == sec
                    )
                    if w_pos + float(w_adj) > 0.4:
                        risk_blocked = True
                        risk_reason = "sector_cap"
                if not risk_blocked and self._entry_correlation_blocked(sym, bars):
                    risk_blocked = True
                    risk_reason = "correlation_cluster"

                if not risk_blocked:
                    current_ts = int(time.time())
                    if isinstance(bars, list) and bars:
                        bt = getattr(bars[-1], "timestamp", None)
                        if isinstance(bt, (int, float)) and int(bt) > 0:
                            current_ts = int(bt)
                    phase = self._session.get_phase(current_ts)
                    if phase in ("auction_open", "auction_close"):
                        risk_blocked = True
                        risk_reason = "auction_phase"
                if not risk_blocked and self._circuit_breaker.triggered(bars):
                    risk_blocked = True
                    risk_reason = "circuit_breaker"

                if risk_blocked and float(decision.get("score", 0) or 0) > 0.7:
                    risk_blocked = False

                if risk_blocked:
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                self._mark_to_market_equity()
                dd_gate = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                if dd_gate < -self._max_drawdown:
                    risk_blocked = True
                    risk_reason = "drawdown_kill"
                elif len(self._positions) >= self._max_positions:
                    risk_blocked = True
                    risk_reason = "max_positions"

                if risk_blocked:
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                if pos is not None:
                    continue

                total_exposure = 0.0
                for p_sym, pos_row in self._positions.items():
                    try:
                        cp = get_current_price(p_sym)
                        if isinstance(cp, (int, float)) and cp > 0:
                            total_exposure += float(cp) * float(int(pos_row.get("size", 0)))
                    except Exception:
                        continue
                if total_exposure > self._equity:
                    risk_blocked = True
                    risk_reason = "over_exposure"
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                try:
                    ok_micro, micro_reason = self._paper_entry_microstructure_ok(price, bars)
                    if not ok_micro:
                        risk_blocked = True
                        risk_reason = micro_reason or "microstructure"
                except Exception:
                    risk_blocked = True
                    risk_reason = "risk_check_error"

                if risk_blocked:
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                stop_price = None
                try:
                    stop_price = decision.get("risk", {}).get("stop_price")
                except Exception:
                    stop_price = None

                try:
                    size_by_risk = self._calculate_position_size(price, stop_price)
                    size_by_capital = int(target_capital_per_position // price) if price > 0 else 0
                    size = min(size_by_risk, size_by_capital)
                    if price > 0:
                        max_cash_size = int(self._cash // price)
                        size = min(int(size), max_cash_size)
                    else:
                        size = 0
                    size = self._apply_entry_position_pct_cap(price, size)
                    if equity_ratio_dd < 0.9:
                        size = max(0, int(size * 0.5))
                    vol_adj_sz = float(decision.get("vol_adj", 1.0))
                    if not isinstance(vol_adj_sz, (int, float)) or vol_adj_sz <= 0:
                        vol_adj_sz = 1.0
                    size = max(1, int(size * vol_adj_sz))
                    strategy_key = decision.get("strategy", "none")
                    if not isinstance(strategy_key, str):
                        strategy_key = str(strategy_key) if strategy_key is not None else "none"
                    meta_w = float(meta_weights.get(strategy_key, 1.0))
                    decay_w = self._decay.compute_weight(float(perf.get(strategy_key, 0.0)))
                    size = max(1, int(size * meta_w * decay_w))
                    if self._event_risk.is_risky(sym):
                        size = max(1, int(size * 0.5))
                    if self._volatility_shock.detect(bars):
                        size = max(1, int(size * 0.5))
                    size = max(1, int(size))
                except Exception:
                    risk_blocked = True
                    risk_reason = "risk_check_error"
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                if size <= 0:
                    risk_blocked = True
                    risk_reason = "zero_size"
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                print("ENTRY ATTEMPT:", sym, price, size)
                avg_vol = 0.0
                try:
                    vols = [getattr(b, "volume", 0) for b in bars[-5:]]
                    avg_vol = float(sum(vols)) / max(len(vols), 1)
                except Exception:
                    avg_vol = 0.0
                price_adj = self._execution_adjust_price(float(price), bars)
                price_adj += float(self._depth_model.impact(int(size), avg_vol))
                _conf_enter = float(decision.get("confidence", 0.0) or 0.0)
                _fill_enter = self.exec_engine.try_fill(
                    symbol=sym,
                    action="enter",
                    price=float(price_adj),
                    last_price=float(price),
                    confidence=_conf_enter,
                )
                if not _fill_enter.get("filled"):
                    continue
                price_adj = float(_fill_enter["fill_price"])
                cost = float(price_adj) * float(size)

                if cost > self._cash:
                    risk_blocked = True
                    risk_reason = "insufficient_cash"
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": "",
                                    "order_status": "",
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": "",
                            "order_status": "",
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                _oid = self._broker.send_order(
                    sym,
                    "buy",
                    float(price_adj),
                    int(size),
                    market_price=float(price),
                )
                buy_order = self._execution_engine.orders.get(_oid)
                if buy_order is None:
                    continue
                self._safe_audit(
                    "order",
                    sym,
                    {
                        "kind": "create",
                        "side": "buy",
                        "order_id": buy_order.id,
                        "price": float(price),
                        "size": int(size),
                        "status": buy_order.status,
                        "exec_price": float(price_adj),
                    },
                )
                if buy_order.status not in ("filled", "partial"):
                    risk_blocked = True
                    risk_reason = "order_not_filled"
                    self._mark_to_market_equity()
                    drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0
                    rk, sc = meta_by_sym.get(sym, (0, 0.0))
                    if not use_ranking:
                        rk, sc = 0, 0.0
                    try:
                        print(
                            json.dumps(
                                {
                                    "symbol": sym,
                                    "action": action,
                                    "price": round(price, 4),
                                    "size": 0,
                                    "position": False,
                                    "pnl": 0.0,
                                    "equity": round(self._equity, 2),
                                    "cash": round(self._cash, 2),
                                    "drawdown": round(drawdown, 6),
                                    "rank": int(rk),
                                    "score": round(float(sc), 6),
                                    "target_capital": round(float(target_capital_per_position), 4),
                                    "allocated_size": 0,
                                    "risk_blocked": True,
                                    "risk_reason": risk_reason,
                                    "order_id": buy_order.id,
                                    "order_status": buy_order.status,
                                    "risk_global_blocked": bool(risk_global_blocked),
                                    "risk_global_reason": risk_global_reason or "",
                                },
                                separators=(",", ":"),
                            ),
                            flush=True,
                        )
                    except Exception:
                        pass
                    results.append(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": price,
                            "size": 0,
                            "position": False,
                            "pnl": 0.0,
                            "reason": reason,
                            "rank": int(rk),
                            "score": float(sc),
                            "target_capital": float(target_capital_per_position),
                            "allocated_size": 0,
                            "risk_blocked": True,
                            "risk_reason": risk_reason,
                            "order_id": buy_order.id,
                            "order_status": buy_order.status,
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        }
                    )
                    continue

                self._safe_audit(
                    "order",
                    sym,
                    {
                        "kind": "fill",
                        "side": "buy",
                        "order_id": buy_order.id,
                        "status": buy_order.status,
                        "market_price": float(price),
                        "exec_price": float(price_adj),
                    },
                )

                filled_buy = int(getattr(buy_order, "filled_size", 0) or 0)
                if filled_buy <= 0:
                    continue
                fill_cost = float(price_adj) * float(filled_buy)
                self._cash -= fill_cost

                self._positions[sym] = {
                    "entry_price": float(price_adj),
                    "size": int(filled_buy),
                    "ts": now,
                }
                position_flag = True
                pnl = 0.0
                order_id = buy_order.id
                order_status = buy_order.status
                exec_price_out = float(price_adj)

            elif action == "exit":
                if pos is None:
                    continue

                entry = pos.get("entry_price", price)
                size = int(pos.get("size", 0))

                fe = float(entry) if isinstance(entry, (int, float)) else 0.0
                price_adj = self._execution_adjust_price(float(price), bars)
                _conf_exit = float(decision.get("confidence", 0.0) or 0.0)
                _fill_exit = self.exec_engine.try_fill(
                    symbol=sym,
                    action="exit",
                    price=float(price_adj),
                    last_price=float(price),
                    confidence=_conf_exit,
                )
                if not _fill_exit.get("filled"):
                    continue
                price_adj = float(_fill_exit["fill_price"])
                pnl = (float(price_adj) - fe) / fe if fe > 0 else 0.0

                _soid = self._broker.send_order(
                    sym,
                    "sell",
                    float(price_adj),
                    int(size),
                    market_price=float(price),
                )
                sell_order = self._execution_engine.orders.get(_soid)
                if sell_order is None:
                    continue
                self._safe_audit(
                    "order",
                    sym,
                    {
                        "kind": "create",
                        "side": "sell",
                        "order_id": sell_order.id,
                        "price": float(price),
                        "size": int(size),
                        "status": sell_order.status,
                        "exec_price": float(price_adj),
                    },
                )
                if sell_order.status not in ("filled", "partial"):
                    continue

                filled_sell = int(getattr(sell_order, "filled_size", 0) or 0)
                if filled_sell <= 0:
                    continue

                self._safe_audit(
                    "order",
                    sym,
                    {
                        "kind": "fill",
                        "side": "sell",
                        "order_id": sell_order.id,
                        "status": sell_order.status,
                        "market_price": float(price),
                        "exec_price": float(price_adj),
                    },
                )

                self._cash += float(price_adj) * float(filled_sell)

                new_sz = int(size) - filled_sell
                if new_sz <= 0:
                    del self._positions[sym]
                    position_flag = False
                else:
                    self._positions[sym] = {
                        "entry_price": float(entry),
                        "size": int(new_sz),
                        "ts": int(pos.get("ts", now)),
                    }
                    position_flag = True

                order_id = sell_order.id
                order_status = sell_order.status
                exec_price_out = float(price_adj)
                try:
                    self._health.record_trade(float(pnl))
                except Exception:
                    pass
                try:
                    sn = decision.get("strategy", "none")
                    self._strategy_metrics.record(str(sn) if sn is not None else "none", float(pnl))
                except Exception:
                    pass
                try:
                    self._trade_log.append(
                        {
                            "symbol": str(sym),
                            "pnl": float(pnl),
                            "strategy": str(decision.get("strategy", "unknown")),
                        }
                    )
                except Exception:
                    pass

            elif action == "hold":
                if pos is None:
                    continue

                entry = pos.get("entry_price", price)

                fe = float(entry) if isinstance(entry, (int, float)) else 0.0
                pnl = (float(price) - fe) / fe if fe > 0 else 0.0

                position_flag = True

            self._mark_to_market_equity()
            drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0

            size_out = int(self._positions.get(sym, {}).get("size", 0)) if position_flag else 0

            rk, sc = meta_by_sym.get(sym, (0, 0.0))
            if not use_ranking:
                rk, sc = 0, 0.0

            try:
                print(
                    json.dumps(
                        {
                            "symbol": sym,
                            "action": action,
                            "price": round(price, 4),
                            "size": size_out,
                            "position": position_flag,
                            "pnl": round(pnl, 6),
                            "equity": round(self._equity, 2),
                            "cash": round(self._cash, 2),
                            "drawdown": round(drawdown, 6),
                            "rank": int(rk),
                            "score": round(float(sc), 6),
                            "target_capital": round(float(target_capital_per_position), 4),
                            "allocated_size": int(size_out),
                            "risk_blocked": bool(risk_blocked),
                            "risk_reason": risk_reason or "",
                            "order_id": order_id or "",
                            "order_status": order_status or "",
                            "exec_price": round(float(exec_price_out), 6),
                            "capital_efficiency_boost": bool(
                                getattr(self, "_capital_efficiency_boost", False)
                            ),
                            "risk_global_blocked": bool(risk_global_blocked),
                            "risk_global_reason": risk_global_reason or "",
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            except Exception:
                pass

            results.append(
                {
                    "symbol": sym,
                    "action": action,
                    "price": price,
                    "size": size_out,
                    "position": position_flag,
                    "pnl": pnl,
                    "reason": reason,
                    "rank": int(rk),
                    "score": float(sc),
                    "target_capital": float(target_capital_per_position),
                    "allocated_size": int(size_out),
                    "risk_blocked": bool(risk_blocked),
                    "risk_reason": risk_reason or "",
                    "order_id": order_id or "",
                    "order_status": order_status or "",
                    "exec_price": float(exec_price_out),
                    "capital_efficiency_boost": bool(
                        getattr(self, "_capital_efficiency_boost", False)
                    ),
                    "risk_global_blocked": bool(risk_global_blocked),
                    "risk_global_reason": risk_global_reason or "",
                }
            )

        self._replay_feed = None

        self._mark_to_market_equity()
        drawdown = (self._equity - self._max_equity) / self._max_equity if self._max_equity > 0 else 0.0

        return {
            "status": "ok",
            "equity": self._equity,
            "cash": self._cash,
            "drawdown": drawdown,
            "results": results,
        }

    def run_loop(self, interval_sec: float | None = None, max_cycles: int | None = None) -> None:
        """
        Continuous deterministic loop (time-sync, drift-free).
        - interval_sec: seconds between cycles (default self._interval_sec or 60)
        - max_cycles: optional stop condition for dev/testing
        """
        interval = (
            float(interval_sec)
            if isinstance(interval_sec, (int, float)) and interval_sec > 0
            else float(getattr(self, "_interval_sec", 60.0) or 60.0)
        )

        _align_time(interval)

        cycles = 0

        while True:
            start_time = time.time()
            start_ts = int(start_time)

            trades_count = 0
            exposure = float(getattr(self, "_portfolio_exposure", 0.0))

            try:
                res = self.run_once()

                if isinstance(res, dict):
                    trades = res.get("trades")
                    if isinstance(trades, list):
                        trades_count = len(trades)

                exposure = float(getattr(self, "_portfolio_exposure", exposure))

            except Exception as e:
                try:
                    self._loop_stats["error_count"] += 1
                    self._loop_stats["last_error"] = str(e)
                except Exception:
                    pass

            try:
                self._loop_stats["cycle_count"] += 1
            except Exception:
                pass

            try:
                print(
                    json.dumps(
                        {
                            "ts": start_ts,
                            "trades": int(trades_count),
                            "exposure": round(exposure, 4),
                            "cycle": int(self._loop_stats.get("cycle_count", 0)),
                            "errors": int(self._loop_stats.get("error_count", 0)),
                        },
                        separators=(",", ":"),
                    ),
                    flush=True,
                )
            except Exception:
                pass

            cycles += 1

            if isinstance(max_cycles, int) and max_cycles > 0 and cycles >= max_cycles:
                break

            next_run = start_time + interval
            now = time.time()
            sleep_time = max(0.0, next_run - now)

            try:
                time.sleep(sleep_time)
            except Exception:
                pass

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
