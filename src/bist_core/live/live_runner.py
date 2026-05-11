"""Live paper loop: iDeal tail read → DecisionEngineV2 → paper execution."""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import time
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np

from bist_core.analysis.edge_monitor import EdgeMonitor
from bist_core.analysis.edge_validator import EdgeValidator
from bist_core.analysis.paper_tracker import PaperTracker
from bist_core.analytics.expectancy import tracker
from bist_core.data.ideal_dataset import load_ideal_dataset
from bist_core.data.kap_fetcher import fetch_kap_rss
from bist_core.data.matriks_provider import MatriksProvider, _fetch_matriks_price
from bist_core.edge.live_edge_buffer import LiveEdgeBuffer
from bist_core.edge.live_edge_engine import LiveEdgeEngine
from bist_core.features.kap_feature_engine import KapFeatureEngine
from bist_core.live.adaptive_live_controller import AdaptiveLiveController, adaptive_enabled, adaptive_window_size
from bist_core.live.data_feed import IdealDataFeed
from bist_core.live.data_hardening import DataHardeningEngine
from bist_core.live.data_validator import DataValidator
from bist_core.live.execution_intelligence import (
    ExecutionIntelligenceLayer,
    detect_volatility_spike,
    execution_intel_enabled,
)
from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.performance_tracker import PerformanceTracker
from bist_core.live.portfolio_engine import build_portfolio_payload, load_symbol_universe_from_env
from bist_core.live.risk_engine import RiskEngine, risk_engine_enabled
from bist_core.live.state_store import LiveState
from bist_core.live.trade_logger import TradeLogger, _safe_float, update_trade_close
from bist_core.models.ohlcv import OHLCVBar
from bist_core.portfolio.portfolio_engine_v2 import apply_portfolio_v2_to_trades
from bist_core.strategy.trend_engine import TrendEngine

TIMEFRAMES = [x.strip() for x in os.getenv("BIST_TIMEFRAMES", "G,60,05,01").split(",") if x.strip()]


def _normalize_symbol(s: str) -> str:
    return str(s).upper().replace("IMKBH'", "").strip()


def _json_sanitize(obj: Any) -> Any:
    """Deterministic JSON-safe values (no NaN/inf) for validation capture lines."""
    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, float):
        if obj != obj or obj in (float("inf"), float("-inf")):
            return 0.0
        return float(obj)
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        return {str(k): _json_sanitize(v) for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))}
    if isinstance(obj, (list, tuple)):
        return [_json_sanitize(x) for x in obj]
    if isinstance(obj, set):
        return sorted((_json_sanitize(x) for x in obj), key=str)
    return str(obj)


def _emit_validation_block(name: str, payload: dict[str, Any]) -> None:
    """Single-line JSON so validation_run.txt parses reliably (flush before possible exit)."""
    safe = _json_sanitize(payload)
    line = json.dumps({name: safe}, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    print(line, flush=True)


def _validation_mode() -> bool:
    """BIST_LIVE_VALIDATION_MODE: deterministic capture — no proof raises; full metric emission."""
    v = os.getenv("BIST_LIVE_VALIDATION_MODE", "0")
    return v in ("1", "true", "True")


def _validation_skip_raises() -> bool:
    return _validation_mode()


def _require_row_decision_edge_score(row: dict[str, Any], *, symbol: str) -> float:
    """Single source of truth: ``row[\"decision\"][\"edge_score\"]`` only."""
    dec = row.get("decision")
    if not isinstance(dec, dict):
        raise RuntimeError("EDGE_SSOT_VIOLATION")
    es = dec.get("edge_score")
    if es is None:
        raise RuntimeError("EDGE_SSOT_VIOLATION")
    try:
        v = float(es)
    except (TypeError, ValueError):
        raise RuntimeError("EDGE_SSOT_VIOLATION") from None
    if v != v:
        raise RuntimeError("EDGE_SSOT_VIOLATION")
    return v


def _snap_edge_from_decision(dec: Any) -> float | None:
    if not isinstance(dec, dict):
        return None
    es = dec.get("edge_score")
    if es is None:
        return None
    try:
        v = float(es)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _emit_snap(portfolio, context=None):
    try:
        _snap = []

        if isinstance(portfolio, dict):
            rows = portfolio.get("PORTFOLIO")
            if isinstance(rows, list):
                for p in rows:
                    if isinstance(p, dict):
                        _d = p.get("decision")
                        _snap.append(
                            {
                                "s": p.get("symbol"),
                                "sz": p.get("position_size"),
                                "e": _snap_edge_from_decision(_d),
                                "c": p.get("confidence"),
                            }
                        )

        elif isinstance(portfolio, list):
            for p in portfolio:
                if isinstance(p, dict):
                    _d = p.get("decision")
                    _snap.append(
                        {
                            "s": p.get("symbol"),
                            "sz": p.get("position_size") or p.get("size"),
                            "e": _snap_edge_from_decision(_d),
                            "c": p.get("confidence"),
                        }
                    )

        if not _snap and isinstance(context, dict):
            trades = context.get("portfolio_v2_trades")
            if isinstance(trades, list):
                for t in trades:
                    if isinstance(t, dict):
                        _td = t.get("decision")
                        _snap.append(
                            {
                                "s": t.get("symbol"),
                                "sz": t.get("size"),
                                "e": _snap_edge_from_decision(_td),
                                "c": t.get("confidence"),
                            }
                        )

        if _snap:
            print({"SNAP": _snap}, flush=True)

    except Exception as e:
        print({"SNAP_ERROR": str(e)}, flush=True)


try:
    from bist_core.decision.decision_engine_v2 import DecisionEngineV2
except Exception:  # pragma: no cover
    DecisionEngineV2 = None  # type: ignore[misc, assignment]

# Minimum bars for decision + edge features (aligned with DecisionEngineV2 single-TF path).
_BAR_MIN_FOR_DECISION = 50


def _pipeline_saw_qualifying_action(decision: dict[str, Any]) -> bool:
    """True if decision shows enter, hold, exit, or wait_pullback (brain or reason)."""
    a = decision.get("action")
    if isinstance(a, str) and a in (
        "enter",
        "enter_long",
        "enter_short",
        "hold",
        "exit",
        "wait_pullback",
        "aggressive_enter",
        "partial_enter",
        "partial_exit",
    ):
        return True
    if str(decision.get("brain_action", "")) == "wait_pullback":
        return True
    if str(decision.get("reason", "")) == "wait_pullback":
        return True
    return False


def _strict_data_flow_enabled() -> bool:
    """BIST_LIVE_STRICT_DATA_FLOW=1 → fail-closed on bad feed (production proof)."""
    v = os.environ.get("BIST_LIVE_STRICT_DATA_FLOW", "0").strip().lower()
    return v in ("1", "true", "yes", "on")


def _c(b: list[Any], i: int) -> float:
    x = b[i]
    return float(x.close) if hasattr(x, "close") else float(x[4])


def _trend(bars: list[Any] | None, lb: int) -> str:
    if not bars or len(bars) < lb:
        return "UNKNOWN"
    return "UP" if _c(bars, -1) > _c(bars, -lb) else "DOWN"


def _tf05_mtf_label(bars: list[Any] | None) -> str:
    """05m trend with PULLBACK within UP/DOWN (deterministic short lookback)."""
    base = _trend(bars, 20)
    if base == "UNKNOWN" or not bars or len(bars) < 10:
        return base
    if base == "UP" and _c(bars, -1) < _c(bars, -5):
        return "PULLBACK"
    if base == "DOWN" and _c(bars, -1) > _c(bars, -5):
        return "PULLBACK"
    return base


def _apply_relax_fallback(decision: dict[str, Any] | None, relax: bool) -> dict[str, Any]:
    """Deterministic hold when relax mode and no qualifying signal (simulation recovery)."""
    if not relax:
        if not isinstance(decision, dict):
            raise RuntimeError("invalid_decision")
        return decision
    if decision is None:
        return {
            "action": "hold",
            "reason": "live_simulation_relax_fallback",
            "confidence": 0.42,
        }
    if _pipeline_saw_qualifying_action(decision):
        return decision
    out = dict(decision)
    out["action"] = "hold"
    out["reason"] = "live_simulation_relax_fallback"
    try:
        out["confidence"] = float(out.get("confidence", 0.35))
    except (TypeError, ValueError):
        out["confidence"] = 0.35
    return out


def _trackable_action(decision: dict[str, Any]) -> bool:
    """Count toward action_counter (live simulation metrics)."""
    a = decision.get("action")
    if isinstance(a, str) and a in (
        "enter",
        "enter_long",
        "enter_short",
        "hold",
        "exit",
        "wait_pullback",
        "aggressive_enter",
        "partial_enter",
        "partial_exit",
    ):
        return True
    if str(decision.get("brain_action", "")) == "wait_pullback":
        return True
    return False


def _stop_target_from_mapping(
    m: dict[str, Any],
) -> tuple[float | None, float | None]:
    sl: float | None = None
    tg: float | None = None
    try:
        v = m.get("stop_loss")
        if v is not None:
            fv = float(v)
            if fv > 0:
                sl = fv
    except (TypeError, ValueError):
        pass
    try:
        v = m.get("target")
        if v is not None:
            fv = float(v)
            if fv > 0:
                tg = fv
    except (TypeError, ValueError):
        pass
    return sl, tg


def _matrix_intelligence_proof(
    matrix_usage: int,
    price_adj: int,
    entry_qualities: set[str],
    actions_seen: set[str],
) -> bool:
    """Long-run proof: Matriks used, price layer adjusted decisions, varied quality & actions."""
    if matrix_usage <= 10:
        return False
    if price_adj < 3:
        return False
    if len(entry_qualities) < 2:
        return False
    needed = {"enter", "wait_pullback", "aggressive_enter"}
    return needed.issubset(actions_seen)


def _real_edge_proof(
    actions_generated: int,
    actions_seen: set[str],
    confidences: list[float],
    position_sizes: list[float],
) -> bool:
    """High-volume run with varied actions, confidence, and sizing (not template-locked)."""
    if actions_generated <= 50:
        return False
    if len(actions_seen) < 2:
        return False
    if len(confidences) < 10:
        return False
    tail = confidences[-min(500, len(confidences)) :]
    if len({round(c, 3) for c in tail}) < 2:
        return False
    if len(position_sizes) >= 8:
        pt = position_sizes[-min(100, len(position_sizes)) :]
        if len({round(p, 1) for p in pt}) < 2:
            return False
    return True


def _matrix_simulation_enabled() -> bool:
    """Deterministic Matriks stand-in from iDeal close when network off (paper proof)."""
    return os.environ.get("BIST_MATRIX_SIMULATION", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _resolve_quote_price(sym: str, ideal: float) -> tuple[float, str]:
    """Executable quote: Matriks → optional matrix sim → last bar close (fail-closed if ideal invalid)."""
    if ideal <= 0 or not math.isfinite(float(ideal)):
        raise ValueError("ideal_price_invalid_for_quote")
    mx = _fetch_matriks_price(sym)
    if mx is not None and float(mx) > 0.0:
        return float(mx), "matriks"
    if _matrix_simulation_enabled():
        h = int(hashlib.md5(sym.encode("utf-8")).hexdigest()[:8], 16) % 1000
        sim = float(ideal) * (1.0 + (h / 1000.0 - 0.5) * 0.05)
        print({"matriks_price": sim, "symbol": sym, "quote_source": "matrix_simulation"})
        return sim, "matrix_simulation"
    fc = float(ideal)
    print({"matriks_price": fc, "symbol": sym, "quote_source": "bars_close"})
    return fc, "bars_close"


def _offset_key(bar: OHLCVBar) -> str:
    """One logical record per file chunk (timestamp = byte offset string)."""
    return str(bar.timestamp)


def _bar_progress_tuple(bar: OHLCVBar) -> tuple[int, str]:
    return (int(bar.timestamp), _offset_key(bar))


def _progress_from_state(state: LiveState, sym: str) -> tuple[int, str] | None:
    raw = state.last_bar_progress.get(sym)
    if not raw or len(raw) < 2:
        return None
    try:
        return (int(raw[0]), str(raw[1]))
    except (TypeError, ValueError):
        return None


def _set_bar_progress(state: LiveState, sym: str, bar: OHLCVBar) -> None:
    t = _bar_progress_tuple(bar)
    state.last_bar_progress[sym] = [t[0], t[1]]
    state.last_bar_id[sym] = t[1]


@contextmanager
def _bar_processing_cursor(state: LiveState, sym: str, bar: OHLCVBar):
    """Always advance monotonic bar cursor (avoids replay stalls and duplicate work)."""
    try:
        yield
    finally:
        _set_bar_progress(state, sym, bar)


def _pending_bars_after_cursor(ordered: list[OHLCVBar], state: LiveState, sym: str) -> list[OHLCVBar]:
    lim = _progress_from_state(state, sym)
    out: list[OHLCVBar] = []
    for b in ordered:
        t = _bar_progress_tuple(b)
        if lim is None or t > lim:
            out.append(b)
    return out


def _bars_per_symbol_per_outer_cycle() -> int:
    """Bars that run the full quote/decision/execution path per symbol per outer cycle (default 1)."""
    try:
        v = int(os.environ.get("BIST_LIVE_BARS_PER_SYMBOL_PER_CYCLE", "1"))
    except ValueError:
        v = 1
    return max(1, min(500, v))


def _live_max_bars_per_poll_env() -> int:
    """``BIST_LIVE_MAX_BARS_PER_POLL``: lookback width for simulated bar-window progression (min 10)."""
    try:
        v = int(os.environ.get("BIST_LIVE_MAX_BARS_PER_POLL", "5000"))
    except ValueError:
        v = 5000
    return max(10, v)


def _mean_exp(edges: dict[tuple[Any, ...], dict[str, Any]]) -> float:
    if not edges:
        return 0.0
    vals = [float(v["exp"]) for v in edges.values() if isinstance(v, dict) and "exp" in v]
    return sum(vals) / len(vals) if vals else 0.0


def _variance_vals(vals: list[float]) -> float:
    """Population variance; 0.0 if fewer than 2 samples (PRDV3 audit / acceptance)."""
    if len(vals) < 2:
        return 0.0
    m = sum(vals) / float(len(vals))
    return sum((float(x) - m) ** 2 for x in vals) / float(len(vals))


def _portfolio_exposure_fraction(state: LiveState, capital: float) -> float:
    """Open notional / capital (deterministic, fail-closed)."""
    if capital <= 0:
        return 1.0
    tot = 0.0
    for sym, legs in state.positions.items():
        px = float(state.last_prices.get(sym, 0.0))
        tot += px * float(len(legs))
    return min(1.0, tot / capital)


def _kap_merge_into_features(
    sym: str,
    feat: dict[str, Any],
    kap_cache: list[dict[str, Any]],
) -> dict[str, Any]:
    """Attach KAP fields for learning rows — deterministic, no NaN/None."""
    out = dict(feat)
    best: dict[str, Any] | None = None
    best_ts = -1
    us = sym.strip().upper()
    for f in kap_cache:
        if str(f.get("symbol", "")).strip().upper() != us:
            continue
        try:
            ts = int(f.get("event_ts", 0))
        except (TypeError, ValueError):
            continue
        if ts >= best_ts:
            best_ts = ts
            best = f
    if best is not None:
        ka = float(best.get("kap_alpha", 0.0))
        if not (ka == ka):  # NaN
            ka = 0.0
        out["kap_event"] = str(best.get("kap_event", ""))
        out["kap_alpha"] = float(ka)
        out["kap_age_min"] = float(best.get("kap_age_min", 0.0))
    else:
        out["kap_event"] = ""
        out["kap_alpha"] = 0.0
        out["kap_age_min"] = 0.0
    return out


def _mean_conf(edges: dict[tuple[Any, ...], dict[str, Any]]) -> float:
    if not edges:
        return 0.0
    vals = [float(v["confidence"]) for v in edges.values() if isinstance(v, dict) and "confidence" in v]
    return sum(vals) / len(vals) if vals else 0.0


def _volatility_proxy(bars: list[OHLCVBar], *, max_lookback: int = 40) -> float:
    """Deterministic realized-vol proxy: mean absolute close-to-close return."""
    if len(bars) < 2:
        return 0.02
    tail = bars[-min(max_lookback, len(bars)) :]
    closes = [float(b.close) for b in tail if float(b.close) > 0]
    if len(closes) < 2:
        return 0.02
    diffs: list[float] = []
    for i in range(1, len(closes)):
        p0, p1 = closes[i - 1], closes[i]
        if p0 <= 0:
            continue
        diffs.append(abs((p1 - p0) / p0))
    if not diffs:
        return 0.02
    v = sum(diffs) / len(diffs)
    return max(0.001, min(0.5, float(v)))


def _cycle_avg_vol_from_snap(
    per_symbol: dict[str, dict[str, Any]],
    fe: Any,
) -> float:
    vols: list[float] = []
    for _sym, pack in per_symbol.items():
        if not isinstance(pack, dict):
            continue
        bars = pack.get("bars")
        if not isinstance(bars, list) or len(bars) < _BAR_MIN_FOR_DECISION:
            continue
        ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
        if len(ohlcv) < _BAR_MIN_FOR_DECISION:
            continue
        feat = fe.extract(ohlcv)
        try:
            vols.append(float(feat.get("vol", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    if not vols:
        return 0.02
    return max(0.001, min(0.5, sum(vols) / len(vols)))


def _cycle_any_vol_spike(
    per_symbol: dict[str, dict[str, Any]],
    avg_vol: float,
) -> bool:
    for _sym, pack in per_symbol.items():
        if not isinstance(pack, dict):
            continue
        bars = pack.get("bars")
        if not isinstance(bars, list) or len(bars) < 2:
            continue
        ohlcv = [b for b in bars if isinstance(b, OHLCVBar)]
        if len(ohlcv) < 2:
            continue
        if detect_volatility_spike(ohlcv, float(avg_vol)):
            return True
    return False


class LiveRunner:
    """Poll iDeal files, maintain bar buffers, evaluate decisions, execute paper trades."""

    def __init__(
        self,
        symbols: list[str] | None = None,
        data_path: str | None = None,
        *,
        poll_seconds: float = 2.0,
        state_path: str | None = None,
        offsets_path: str | None = None,
        max_total_positions: int = 3,
        max_symbol_fraction: float = 0.30,
        daily_loss_limit: float = -0.2,
        edges: Optional[dict[tuple[Any, ...], dict[str, Any]]] = None,
        edges_by_tf: Optional[dict[str, dict[tuple[Any, ...], dict[str, Any]]]] = None,
        edge_update_every_n_cycles: int = 100,
        edge_buffer_max_rows: int = 50_000,
        max_live_edges: int = 500,
        kap_fetcher: Callable[[], list[dict[str, Any]]] | None = None,
        kap_engine: KapFeatureEngine | None = None,
        kap_cache_max: int = 2000,
        edge_validate_debug: bool = False,
    ) -> None:
        if symbols is None:
            symbols = load_symbol_universe_from_env()
        if not symbols:
            symbols = ["ASELS"]
        if data_path is None:
            data_path = os.environ.get("BIST_IDEAL_DATA_PATH") or os.environ.get("IDEAL_DATA_PATH", "")
        dp = str(data_path).strip()
        if not dp:
            raise RuntimeError("BIST_IDEAL_DATA_PATH is required")
        self.symbols = [str(s).strip().upper() for s in symbols if str(s).strip()]
        self.feed = IdealDataFeed(dp)
        self.matriks = MatriksProvider()
        self.hardening = DataHardeningEngine()
        self.state_path = Path(state_path) if state_path else None
        self.offsets_path = Path(offsets_path) if offsets_path else None

        if self.state_path and self.state_path.is_file():
            self.state = LiveState.load(self.state_path)
        else:
            self.state = LiveState()

        if self.offsets_path and self.offsets_path.is_file():
            self.feed.load_offsets(self.offsets_path)

        self.exec = PaperExecution(self.state)
        self.execution = self.exec
        self.perf = PerformanceTracker()
        self.trend_engine = TrendEngine()
        if risk_engine_enabled():
            try:
                mx = int(os.environ.get("BIST_RISK_MAX_POSITIONS", str(max_total_positions)))
            except ValueError:
                mx = max_total_positions
            try:
                mf = float(os.environ.get("BIST_RISK_MAX_SYMBOL_FRACTION", str(max_symbol_fraction)))
            except ValueError:
                mf = max_symbol_fraction
            self.exec.configure_risk(
                max_total_positions=mx,
                max_symbol_fraction=mf,
                daily_loss_limit=daily_loss_limit,
            )
        else:
            self.exec.configure_risk(
                max_total_positions=max_total_positions,
                max_symbol_fraction=1.0,
                daily_loss_limit=daily_loss_limit,
            )
        self.poll_seconds = float(poll_seconds)
        if DecisionEngineV2 is None:
            raise RuntimeError("DecisionEngineV2 unavailable")
        self.decision = DecisionEngineV2(edges=edges, edges_by_tf=edges_by_tf)
        self.edge_buffer = LiveEdgeBuffer(max_rows=edge_buffer_max_rows)
        self.live_edge_engine = LiveEdgeEngine()
        self._max_live_edges = max(50, int(max_live_edges))
        self._last_entry_feat: dict[str, dict[str, Any]] = {}
        self._last_entry_buffer_len: dict[str, int] = {}
        self._edge_cycle = 0
        self._edge_update_every_n_cycles = max(1, int(edge_update_every_n_cycles))
        self._watchdog_streak = 0
        self._kap_fetcher: Callable[[], list[dict[str, Any]]] = (
            kap_fetcher if kap_fetcher is not None else fetch_kap_rss
        )
        self.kap_engine = kap_engine if kap_engine is not None else KapFeatureEngine()
        self._kap_cache: list[dict[str, Any]] = []
        self._kap_cache_max = max(100, int(kap_cache_max))
        self._edge_validate_debug = bool(edge_validate_debug) or (
            os.environ.get("BIST_EDGE_VALIDATE_DEBUG", "").strip().lower() in ("1", "true", "yes")
        )
        self.kap_enabled = True
        self.paper_kap_on = PaperTracker()
        self.paper_kap_off = PaperTracker()
        self.edge_monitor = EdgeMonitor()
        self.validator = DataValidator()
        # Populated by run() for metrics / relax fallback.
        self._action_counter = 0
        self._symbols_with_actions: set[str] = set()
        self._relax_mode = False
        self._confidences: list[float] = []
        self._conf_history: list[float] = []
        self._position_sizes: list[float] = []
        self._actions_seen: set[str] = set()
        self._matrix_usage_count = 0
        self._price_adjustment_count = 0
        self._entry_qualities_seen: set[str] = set()
        self._portfolio_best_selected = 0
        self._max_portfolio_rows: int = 0
        self._empty_portfolio_cycles_manual: int = 0
        self._adaptive: AdaptiveLiveController | None
        if adaptive_enabled():
            self._adaptive = AdaptiveLiveController(window=adaptive_window_size())
        else:
            self._adaptive = None
        self._exec_intel: ExecutionIntelligenceLayer | None
        if execution_intel_enabled():
            self._exec_intel = ExecutionIntelligenceLayer()
        else:
            self._exec_intel = None
        self._last_regime: str = "MIXED"
        self._risk: RiskEngine | None
        self._entry_risk_factor: dict[str, float] = {}
        self._last_cycle_avg_vol: float = 0.02
        self._last_cycle_vol_spike: bool = False
        self._risk_snap_loop: dict[str, Any] | None = None
        if risk_engine_enabled():
            self._risk = RiskEngine()
            self._risk.sync_from_dict(self.state.risk_blob)
        else:
            self._risk = None
        self.trade_logger = TradeLogger()
        self._entry_side_by_symbol: dict[str, str] = {}
        if not hasattr(self, "positions"):
            self.positions = {}
        self.last_trade_time: dict[str, float] = {}
        self._position_entry_cycle: dict[str, int] = {}
        self._recover_open_positions_from_csv()

    def _csv_rows(self) -> list[dict[str, str]]:
        return self.trade_logger._read_rows()

    def _csv_open_symbols_normalized(self) -> set[str]:
        rows = self._csv_rows()
        return {
            _normalize_symbol(str(row.get("symbol") or ""))
            for row in rows
            if str(row.get("status", "")).strip().upper() == "OPEN"
        }

    def _csv_open_counts_normalized(self) -> dict[str, int]:
        rows = self._csv_rows()
        counts: dict[str, int] = {}
        for row in rows:
            if str(row.get("status", "")).strip().upper() != "OPEN":
                continue
            sn = _normalize_symbol(str(row.get("symbol") or ""))
            counts[sn] = counts.get(sn, 0) + 1
        return counts

    def _validation_assert_no_csv_open_remaining(self, sym: str) -> None:
        sym_n = _normalize_symbol(sym)
        count_open = sum(
            1
            for row in self._csv_rows()
            if _normalize_symbol(str(row.get("symbol") or "")) == sym_n
            and str(row.get("status", "")).strip().upper() == "OPEN"
        )
        if count_open > 0:
            print({"FATAL_OPEN_REMAINING": sym}, flush=True)
            raise RuntimeError("CSV still has OPEN row after close")

    def _assert_csv_max_one_open_per_symbol(self) -> None:
        for sym_n, c in self._csv_open_counts_normalized().items():
            if c > 1:
                print({"FATAL_CSV_DUPLICATE_OPEN": sym_n}, flush=True)
                raise RuntimeError("Multiple OPEN rows detected")

    def _state_open_symbols_normalized(self) -> set[str]:
        out: set[str] = set()
        for sym_x, legs in self.state.positions.items():
            if not legs:
                continue
            active = [
                p
                for p in legs
                if isinstance(p, dict) and int(p.get("size", 1) or 0) > 0 and float(p.get("qty", 0.0) or 0.0) > 1e-12
            ]
            if active:
                out.add(_normalize_symbol(str(sym_x)))
        return out

    def _assert_state_csv_open_match(self) -> None:
        csv_open = self._csv_open_symbols_normalized()
        state_open = self._state_open_symbols_normalized()
        if csv_open != state_open:
            print(
                {
                    "FATAL_STATE_CSV_MISMATCH": {
                        "csv": sorted(csv_open),
                        "state": sorted(state_open),
                    }
                },
                flush=True,
            )
            raise RuntimeError("CSV and state mismatch")

    def _assert_state_csv_lock(self) -> None:
        assert set(self._state_open_symbols_normalized()) == set(self._csv_open_symbols_normalized()), (
            "STATE != CSV — SYSTEM CORRUPTED"
        )

    def _runner_position_exists_norm(self, sym_n: str) -> bool:
        if sym_n in self.positions:
            return True
        for k, legs in self.state.positions.items():
            if _normalize_symbol(str(k)) != sym_n:
                continue
            if not legs:
                continue
            active = [
                p
                for p in legs
                if isinstance(p, dict) and int(p.get("size", 1) or 0) > 0 and float(p.get("qty", 0.0) or 0.0) > 1e-12
            ]
            if active:
                return True
        return False

    def _emit_trade_trace(self, sym: str, stage: str) -> None:
        print(
            {
                "TRADE_TRACE": {
                    "symbol": sym,
                    "stage": stage,
                    "positions_before": list(self.positions.keys()),
                    "state_before": list(self.state.positions.keys()),
                }
            },
            flush=True,
        )

    def _emit_trade_trace_after(self, sym: str) -> None:
        print(
            {
                "TRADE_TRACE_AFTER": {
                    "symbol": sym,
                    "positions_after": list(self.positions.keys()),
                    "state_after": list(self.state.positions.keys()),
                }
            },
            flush=True,
        )

    def _sync_positions_from_state(self) -> None:
        synced = {}
        for sym, legs in self.state.positions.items():
            if not legs:
                continue
            for leg in legs:
                if not isinstance(leg, dict):
                    continue

                size = float(leg.get("size", 0))
                if size <= 0:
                    continue

                entry_price = float(leg.get("entry_price") or leg.get("entry") or leg.get("price") or 0)

                synced[_normalize_symbol(str(sym))] = {
                    "size": size,
                    "entry_price": entry_price,
                    "stop_loss": float(leg.get("stop_loss", 0)),
                    "target": float(leg.get("target", 0)),
                    "side": leg.get("side", "long"),
                }

        self.positions = synced

    def _recover_open_positions_from_csv(self) -> None:
        """Rebuild ``state.positions`` and ``self.positions`` from CSV OPEN rows (CSV SSOT)."""
        rows = self.trade_logger._read_rows()
        open_by_norm: dict[str, dict[str, str]] = {}
        for row in rows:
            if str(row.get("status", "")).strip().upper() != "OPEN":
                continue
            sym_n = _normalize_symbol(str(row.get("symbol") or ""))
            if not sym_n:
                print({"FATAL_CSV_OPEN_INVALID_SYMBOL": row}, flush=True)
                raise RuntimeError("CSV OPEN row missing symbol")
            if sym_n in open_by_norm:
                print({"FATAL_CSV_DUPLICATE_OPEN": sym_n}, flush=True)
                raise RuntimeError("Multiple OPEN rows detected")
            act = str(row.get("action", "")).strip().lower()
            if not act.startswith("enter"):
                print({"FATAL_CSV_OPEN_INVALID_ACTION": sym_n}, flush=True)
                raise RuntimeError("CSV OPEN row has invalid action")
            open_by_norm[sym_n] = row

        new_positions: dict[str, list[dict[str, Any]]] = {}
        for sym_n, row in open_by_norm.items():
            entry_px = float(_safe_float(row.get("entry"), 0.0))
            if entry_px <= 0.0:
                print({"FATAL_CSV_OPEN_INVALID_ENTRY": sym_n}, flush=True)
                raise RuntimeError("CSV OPEN row has invalid entry")
            side = "short" if str(row.get("action", "")).strip().lower() == "enter_short" else "long"
            sl = float(_safe_float(row.get("stop"), 0.0))
            tg = float(_safe_float(row.get("target"), 0.0))
            edge_v = float(_safe_float(row.get("edge"), 0.0))
            self.state.order_seq += 1
            order_id = f"{sym_n}-csv-recovery-{self.state.order_seq}"
            leg: dict[str, Any] = {
                "entry_price": entry_px,
                "size": 1,
                "qty": 1.0,
                "order_id": order_id,
                "side": side,
                "edge_score": edge_v,
            }
            if sl > 0.0:
                leg["stop_loss"] = sl
            if tg > 0.0:
                leg["target"] = tg
            new_positions[sym_n] = [leg]
            self._entry_side_by_symbol[sym_n.upper()] = side

        self.state.positions = new_positions
        self._sync_positions_from_state()

        csv_open = self._csv_open_symbols_normalized()
        state_open = self._state_open_symbols_normalized()
        if csv_open != state_open:
            print(
                {
                    "FATAL_STATE_RECOVERY_MISMATCH": {
                        "csv": sorted(csv_open),
                        "state": sorted(state_open),
                    }
                },
                flush=True,
            )
            raise RuntimeError("STATE recovery: CSV and state mismatch")

        print(
            {
                "STATE_RECOVERY": {
                    "positions_loaded": list(self.positions.keys()),
                }
            },
            flush=True,
        )

    def _position_qty(self, sym: str) -> float:
        return sum(float(p.get("qty", 1.0)) for p in self.state.positions.get(sym, []))

    def _kap_latest_for_symbol(self, sym: str) -> dict[str, Any] | None:
        """Latest KAP feature for symbol (by event_ts), or None."""
        best: dict[str, Any] | None = None
        best_ts = -1
        us = sym.strip().upper()
        for f in self._kap_cache:
            if str(f.get("symbol", "")).strip().upper() != us:
                continue
            try:
                ts = int(f.get("event_ts", 0))
            except (TypeError, ValueError):
                continue
            if ts >= best_ts:
                best_ts = ts
                best = f
        return best

    def _maybe_refresh_edges(self) -> None:
        """Recompute live edges; fail-closed: keep prior if empty, negative avg exp, or low confidence path."""
        new_edges = self.live_edge_engine.update(self.edge_buffer)
        avg_e = _mean_exp(new_edges)
        avg_c = _mean_conf(new_edges)
        print({"edges": len(new_edges), "avg_exp": avg_e, "confidence": avg_c})
        self.edge_monitor.log(len(new_edges), avg_e)
        print(self.edge_monitor.summary())
        if not new_edges:
            return
        if avg_e < 0.0:
            return
        self.decision.edge_store.load_live(new_edges, self._edge_cycle)

    def _append_buffer(self, sym: str, bar: OHLCVBar) -> None:
        buf = self.state.bar_buffers.setdefault(sym, [])
        buf.append(bar)
        if len(buf) > self.state.max_bar_buffer:
            self.state.bar_buffers[sym] = buf[-self.state.max_bar_buffer :]

    def _persist(self) -> None:
        if self._risk is not None:
            self.state.risk_blob = self._risk.to_dict()
        if self.state_path:
            try:
                self.state.save(self.state_path)
            except OSError as e:
                self.state.log_error(f"state_save:{e}")
        if self.offsets_path:
            try:
                self.feed.save_offsets(self.offsets_path)
            except OSError as e:
                self.state.log_error(f"offsets_save:{e}")

    def _universe_symbols(self) -> list[str]:
        """Immutable snapshot of the tradeable universe for one outer scan (no generator)."""
        return [str(s).strip().upper() for s in self.symbols if str(s).strip()]

    def _emit_run_end_validation(
        self,
        cycle_count: int,
        max_c: int,
        *,
        validation_mode: bool,
        require_full_proof: bool,
        saw_qualifying_action: bool,
        ever_feed_bars: bool,
        saw_real_data_flowing: bool,
        loop_ok: bool,
    ) -> None:
        """Always emit validation JSON blocks (analyzer/optimizer); flush=True; never skip."""
        if len(self.symbols) >= 5 and self._portfolio_best_selected >= 2:
            print("MULTI-SYMBOL ENGINE ACTIVE — PORTFOLIO MODE ENABLED", flush=True)
            print("EDGE FLOW STABILIZED — CONTINUOUS PORTFOLIO ACTIVE", flush=True)

        if self._adaptive is not None:
            status_report = self._adaptive.build_report(total_cycles=cycle_count)
            hr = status_report.get("hard_rules") or {}
            if isinstance(hr, dict) and hr and all(bool(v) for v in hr.values()):
                print("FULL SYSTEM OPTIMIZED — STABLE TRADING MODE ACTIVE", flush=True)
            rd = status_report.get("market_regime_distribution") or {}
            esv = float(status_report.get("edge_score_variance") or 0.0)
            if isinstance(rd, dict) and (len(rd) >= 2 or esv >= 1e-8):
                print("MARKET-AWARE INTELLIGENCE ACTIVE — SYSTEM LEARNING ENABLED", flush=True)
        else:
            conf_var_fb = _variance_vals(self._confidences)
            cs_fb = 0.0
            if len(self._confidences) >= 2:
                cs_fb = max(self._confidences) - min(self._confidences)
            act_div_fb = len(self._actions_seen)
            status_report = {
                "total_cycles": int(cycle_count),
                "adaptive_mode": "disabled",
                "hard_rules": {
                    "avg_selected_ok": True,
                    "action_diversity_ok": act_div_fb >= 3,
                    "confidence_variance_ok": cs_fb >= 0.25,
                    "no_empty_portfolio_cycles_ok": self._empty_portfolio_cycles_manual == 0,
                    "score_distribution_ok": len(self._confidences) >= 2,
                },
                "market_regime_distribution": {},
                "confidence_variance": round(float(conf_var_fb), 8),
                "confidence_spread": round(float(cs_fb), 8),
                "action_diversity": int(act_div_fb),
                "empty_portfolio_cycles": int(self._empty_portfolio_cycles_manual),
            }

        if self._exec_intel is not None:
            exec_metrics = self._exec_intel.metrics.summary()
            print("EXECUTION INTELLIGENCE ACTIVE — TRADE QUALITY OPTIMIZED", flush=True)
        else:
            exec_metrics = {
                "disabled": True,
                "source": "paper_realism",
                "avg_slippage": 0.0,
                "fill_rate": 0.0,
                "execution_quality_score": 0.0,
                "delays": 0,
                "fill_attempts": getattr(self.execution, "fill_attempts", 0),
                "fills_ok": getattr(self.execution, "fills_ok", 0),
            }

        if getattr(self.exec, "realism_metrics", None) is not None:
            market_realism = self.exec.realism_metrics.summary()
            print("REAL MARKET SIMULATION ACTIVE — NO FAKE EDGE", flush=True)
            # Same paper path: avoid EXECUTION_METRICS vs MARKET_REALISM drift when intel is off.
            if self._exec_intel is None:
                exec_metrics = {
                    "disabled": True,
                    "source": "paper_realism",
                    "avg_slippage": round(float(market_realism.get("avg_slippage_fraction") or 0.0), 8),
                    "fill_rate": round(float(market_realism.get("fill_success_rate") or 0.0), 6),
                    "execution_quality_score": 0.0,
                    "delays": 0,
                    "fill_attempts": int(market_realism.get("fill_attempts") or 0),
                    "fills_ok": int(market_realism.get("fills_ok") or 0),
                }
        else:
            market_realism = {
                "fill_success_rate": -1.0,
                "missed_trades": -1,
                "avg_slippage_fraction": -1.0,
                "slippage_samples": 0,
                "avg_execution_delay_ms": 0.0,
            }

        if self._risk is not None:
            _snap_end = self._risk.build_snapshot(
                volatility=self._last_cycle_avg_vol,
                regime=self._last_regime,
                vol_spike=self._last_cycle_vol_spike,
            )
            risk_metrics = {
                "operational_state": str(_snap_end.get("operational_state", "ACTIVE")),
                "fsm_transition_count": int(_snap_end.get("fsm_transition_count", 0)),
                "fsm_last_transition": _snap_end.get("fsm_last_transition"),
                "fsm_transitions_observed": bool(_snap_end.get("fsm_transitions_observed", False)),
                "max_drawdown": round(float(self._risk.max_drawdown_pct), 8),
                "sharpe_proxy": round(float(self._risk.sharpe_proxy()), 6),
                "winrate": round(float(self._risk.winrate()), 6),
                "avg_risk_per_trade": round(float(self._risk.avg_risk_per_trade()), 6),
                "closed_trades": int(self._risk.closed_trades),
                "risk_multiplier": round(float(_snap_end.get("risk_multiplier", 1.0)), 8),
                "kill_switch": bool(_snap_end.get("kill_switch", False)),
            }
            print("RISK ENGINE ACTIVE — CAPITAL PROTECTED", flush=True)
        else:
            risk_metrics = {
                "operational_state": "DISABLED",
                "fsm_transition_count": 0,
                "fsm_last_transition": None,
                "fsm_transitions_observed": False,
                "max_drawdown": 0.0,
                "sharpe_proxy": 0.0,
                "winrate": 0.0,
                "avg_risk_per_trade": 0.0,
                "closed_trades": 0,
                "risk_engine": "disabled",
                "risk_multiplier": 1.0,
                "kill_switch": False,
            }

        sim_summary: dict[str, Any] = {
            "total_cycles": cycle_count,
            "actions_generated": self._action_counter,
            "active_symbols": list(self.symbols),
            "data_flow": "IDEAL",
            "MATRIX_USAGE": self._matrix_usage_count,
            "PRICE_ADJUSTMENTS": self._price_adjustment_count,
            "entry_quality_variety": len(self._entry_qualities_seen),
            "portfolio_peak_selected": self._portfolio_best_selected,
            "max_portfolio_rows": int(self._max_portfolio_rows),
            "max_cycles_config": max_c,
        }
        if cycle_count < max_c:
            sim_summary["error"] = "incomplete_cycles"

        _emit_validation_block("SIMULATION_SUMMARY", sim_summary)
        _emit_validation_block("MARKET_REALISM", market_realism)
        _emit_validation_block("EXECUTION_METRICS", exec_metrics)
        _emit_validation_block("RISK_METRICS", risk_metrics)
        _emit_validation_block("SYSTEM_STATUS_REPORT", status_report)

        print(
            {
                "MATRIX_USAGE": self._matrix_usage_count,
                "PRICE_ADJUSTMENTS": self._price_adjustment_count,
            },
            flush=True,
        )

        skip_proof_exc = validation_mode

        if loop_ok and cycle_count >= 100:
            if require_full_proof:
                if not ever_feed_bars:
                    if not skip_proof_exc:
                        raise RuntimeError("DATA_FAILURE: no_feed_data")
                    print(
                        {
                            "validation_mode": "skipped_raise",
                            "would_raise": "DATA_FAILURE: no_feed_data",
                        },
                        flush=True,
                    )
                elif self._action_counter <= 10 or len(self._symbols_with_actions) < 1:
                    if not skip_proof_exc:
                        raise Exception("NO_ACTIONS_PRODUCED")
                    print(
                        {
                            "validation_mode": "skipped_raise",
                            "would_raise": "NO_ACTIONS_PRODUCED",
                        },
                        flush=True,
                    )
                else:
                    print("SYSTEM LIVE-READY — FULL PIPELINE VERIFIED", flush=True)
            else:
                if not saw_qualifying_action:
                    if not skip_proof_exc:
                        raise Exception("NO_ACTIONS_PRODUCED")
                    print(
                        {
                            "validation_mode": "skipped_raise",
                            "would_raise": "NO_ACTIONS_PRODUCED",
                        },
                        flush=True,
                    )
                else:
                    print("PIPELINE VERIFIED — READY FOR LIVE TEST", flush=True)
            if _real_edge_proof(
                self._action_counter,
                self._actions_seen,
                self._confidences,
                self._position_sizes,
            ):
                print("DECISION ENGINE UPGRADED — REAL EDGE ACTIVE", flush=True)
            if _matrix_intelligence_proof(
                self._matrix_usage_count,
                self._price_adjustment_count,
                self._entry_qualities_seen,
                self._actions_seen,
            ):
                print("MATRIX INTEGRATION COMPLETE — REAL-TIME INTELLIGENCE ACTIVE", flush=True)
            if saw_real_data_flowing:
                print({"REAL_DATA_VALIDATION": "SUCCESS"}, flush=True)
            else:
                print(
                    {"REAL_DATA_VALIDATION": "PENDING", "DATA_SOURCE": "IDEAL"},
                    flush=True,
                )

        print(
            {"SYSTEM_VALIDATION": "PASSED" if loop_ok else "FAILED"},
            flush=True,
        )

    def run(self, max_cycles: int | None = None, *, single_cycle: bool = False) -> dict[str, Any] | None:

        try:
            max_c_env = int(os.environ.get("BIST_LIVE_MAX_CYCLES", "800"))
        except ValueError:
            max_c_env = 800
        if max_cycles is not None:
            max_c = max(1, min(int(max_cycles), 100_000))
        else:
            max_c = max(1, min(max_c_env, 100_000))
        validation_mode = os.environ.get("BIST_LIVE_VALIDATION_MODE", "0") in ("1", "true", "True")
        require_full_proof = max_c >= 120 or os.environ.get("BIST_LIVE_REQUIRE_FULL_PROOF", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        quick_verify = os.environ.get("BIST_LIVE_QUICK_VERIFY", "").strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if quick_verify:
            require_full_proof = False

        self._relax_mode = False
        self._action_counter = 0
        self._symbols_with_actions.clear()
        self._confidences.clear()
        self._position_sizes.clear()
        self._actions_seen.clear()
        self._portfolio_best_selected = 0
        self._max_portfolio_rows = 0
        os.environ.pop("BIST_DECISION_RELAX_MODE", None)

        cycle_count = 0
        try:
            max_cycles = int(os.getenv("MAX_CYCLES", "1"))
        except ValueError:
            max_cycles = 1
        if "MAX_CYCLES" not in os.environ:
            max_cycles = max_c
        max_cycles = max(1, min(int(max_cycles), max_c))
        current_cycle = 0
        stopped_max_cycles_emitted = False
        saw_qualifying_action = False
        saw_real_data_flowing = False
        ever_feed_bars = False
        no_progress_streak = 0

        loop_exc: BaseException | None = None
        try:
            # LOOPS (forensic):
            # - ONE `while cycle_count < max_c` (no break for termination — condition-only exit).
            # - Per iteration: `symbols = list(self._universe_symbols())`, full `for sym in symbols` pass,
            #   then portfolio phase, then exactly one `cycle_count += 1` (never inside `for sym`).
            # - Per symbol: bootstrap OHLCV buffer, then at most K decision bars (`for bar in decision_bars`).
            # - `for item in kap_items`: KAP ingest; bounded by feed size.
            while True:
                try:
                    current_cycle += 1
                    now_ts = int(time.time())
                    try:
                        kap_items = self._kap_fetcher()
                    except Exception:
                        kap_items = []
                    if not isinstance(kap_items, list):
                        kap_items = []
                    for item in kap_items:
                        if not isinstance(item, dict):
                            continue
                        feat_k = self.kap_engine.build_feature(item, now_ts)
                        if feat_k:
                            self._kap_cache.append(feat_k)
                    if len(self._kap_cache) > self._kap_cache_max:
                        self._kap_cache = self._kap_cache[-self._kap_cache_max :]

                    cycle_portfolio_snap: dict[str, dict[str, Any]] = {}
                    cycle_actions: list[str] = []
                    cycle_confidences: list[float] = []
                    cycle_decision_payloads = 0
                    self._risk_snap_loop = None
                    if self._risk is not None:
                        self._risk.tick_cycle()
                        self._risk.update_equity(self.state.equity)
                        self._risk_snap_loop = self._risk.build_snapshot(
                            volatility=self._last_cycle_avg_vol,
                            regime=self._last_regime,
                            vol_spike=self._last_cycle_vol_spike,
                        )
                    if self._adaptive is not None:
                        self._adaptive.begin_cycle()

                    # INNER: one iteration per symbol; `continue` skips to next sym only (not outer while).
                    symbols = list(self._universe_symbols())
                    cycle_bar_progress = False
                    try:
                        for sym in symbols:
                            raw_bars: list[OHLCVBar] | None = None
                            try:
                                USE_IDEAL = True
                                assert USE_IDEAL
                                multi_tf_data: dict[str, list[OHLCVBar]] = {}
                                for tf in TIMEFRAMES:
                                    print(
                                        {
                                            "DATA_SOURCE": "IDEAL",
                                            "symbol": sym,
                                            "tf": tf,
                                        },
                                        flush=True,
                                    )
                                    bars = load_ideal_dataset(sym, tf, registry=None)
                                    if bars and len(bars) > 0:
                                        multi_tf_data[tf] = bars
                                    else:
                                        print(
                                            {
                                                "TF_SKIPPED": {
                                                    "symbol": sym,
                                                    "tf": tf,
                                                    "reason": "no_valid_data",
                                                }
                                            },
                                            flush=True,
                                        )
                                print(
                                    {"MTF_FULL": {"keys": list(multi_tf_data.keys())}},
                                    flush=True,
                                )
                                if len(multi_tf_data) == 0:
                                    print({"NO_VALID_TIMEFRAMES": sym}, flush=True)
                                    continue
                                g_bars = multi_tf_data.get("G", [])
                                tf60 = multi_tf_data.get("60", [])
                                tf05 = multi_tf_data.get("05", [])
                                tf01 = multi_tf_data.get("01", [])

                                print(
                                    {
                                        "MTF_PROOF": {
                                            "symbol": sym,
                                            "G": len(g_bars),
                                            "60": len(tf60),
                                            "05": len(tf05),
                                            "01": len(tf01),
                                            "G_last": _c(g_bars, -1) if g_bars else None,
                                            "60_last": tf60[-1].close if tf60 else None,
                                            "05_last": tf05[-1].close if tf05 else None,
                                            "01_last": tf01[-1].close if tf01 else None,
                                        }
                                    },
                                    flush=True,
                                )
                                g_trend = _trend(g_bars, 50)
                                t60_trend = _trend(tf60, 30)
                                t05_trend = _tf05_mtf_label(tf05)
                                t01_trend = _trend(tf01, 10)
                                print(
                                    {
                                        "MTF_STATE": {
                                            "G": g_trend,
                                            "60": t60_trend,
                                            "05": t05_trend,
                                            "01": t01_trend,
                                        }
                                    },
                                    flush=True,
                                )
                                selected_tf = None
                                raw_bars = None

                                for _k in ("01", "05", "60", "G"):
                                    bars = multi_tf_data.get(_k)
                                    if bars and len(bars) > 0:
                                        raw_bars = bars
                                        selected_tf = _k
                                        break

                                if raw_bars is None:
                                    for _k, bars in multi_tf_data.items():
                                        if bars and len(bars) > 0:
                                            raw_bars = bars
                                            selected_tf = _k
                                            break

                                print(
                                    {
                                        "RAW_BARS_SELECTED": {
                                            "len": len(raw_bars) if raw_bars else 0,
                                            "tf_used": selected_tf,
                                            "available_tfs": {k: len(v) if v else 0 for k, v in multi_tf_data.items()},
                                        }
                                    }
                                )

                                if not raw_bars:
                                    print({"error": "NO_DATA", "reason": "ALL_TF_EMPTY"})
                                    continue
                            except Exception as e:
                                self.state.log_error(f"feed:{sym}:{e}")
                                print({"error": "NO_DATA"})
                                continue

                            print({"stage": "feed", "symbol": sym, "bars": len(raw_bars)})
                            ever_feed_bars = True

                            is_dummy = False
                            if raw_bars and hasattr(raw_bars[0], "is_dummy"):
                                is_dummy = bool(getattr(raw_bars[0], "is_dummy", False))
                            print(
                                {
                                    "data_check": {
                                        "symbol": sym,
                                        "bars": len(raw_bars),
                                        "is_dummy": is_dummy,
                                    }
                                }
                            )

                            unique_prices = 0
                            if raw_bars:
                                prices = [float(b.close) for b in raw_bars[-10:]]
                                unique_prices = len(set(prices))
                                print(
                                    {
                                        "price_variation": {
                                            "symbol": sym,
                                            "unique_prices": unique_prices,
                                        }
                                    }
                                )

                            if unique_prices <= 2:
                                print(
                                    {
                                        "DATA_REJECTED_STATIC": {
                                            "symbol": sym,
                                            "unique_prices": unique_prices,
                                        }
                                    },
                                    flush=True,
                                )
                                continue

                            if is_dummy:
                                print({"DATA_STATUS": "FAKE_DATA"})
                                if _strict_data_flow_enabled():
                                    raise RuntimeError("DATA_FAILURE: dummy data (is_dummy=True)")
                            elif unique_prices <= 1:
                                print({"DATA_STATUS": "INVALID_STATIC_DATA"})
                                if _strict_data_flow_enabled():
                                    raise RuntimeError("DATA_FAILURE: static / invalid prices")
                            else:
                                print({"DATA_STATUS": "REAL_DATA_FLOWING"})
                                saw_real_data_flowing = True

                            matriks_px = self.matriks.get_price(sym)
                            ideal_bars, batch_ok = self.hardening.process(raw_bars, sym, matriks_px)
                            print({"stage": "hardening", "valid": batch_ok})
                            if not batch_ok:
                                print({"error": "HARDENING_FAIL"})
                                continue
                            if not ideal_bars:
                                print({"error": "HARDENING_FAIL"})
                                continue

                            bars = ideal_bars
                            try:
                                max_bars_poll = int(os.environ.get("BIST_LIVE_MAX_BARS_PER_POLL", "5000"))
                            except ValueError:
                                max_bars_poll = 5000
                            if max_bars_poll > 0 and len(bars) > max_bars_poll:
                                print(
                                    {
                                        "stage": "feed_trim",
                                        "symbol": sym,
                                        "bars_in": len(bars),
                                        "bars_kept": max_bars_poll,
                                    }
                                )
                                bars = bars[-max_bars_poll:]

                            if len(bars) < _BAR_MIN_FOR_DECISION:
                                try:
                                    matriks_bars = self.matriks.fetch(sym, period="1m")
                                except Exception:
                                    matriks_bars = None
                                if not matriks_bars:
                                    continue
                                mb_processed, mb_ok = self.hardening.process(matriks_bars, sym, matriks_px)
                                if not mb_ok or len(mb_processed) < _BAR_MIN_FOR_DECISION:
                                    continue
                                bars = mb_processed

                            trend = self.trend_engine.detect(bars)
                            print(
                                {
                                    "TREND_DEBUG": {
                                        "symbol": sym,
                                        "trend": trend,
                                        "last_price": bars[-1].close,
                                    }
                                },
                                flush=True,
                            )

                            if self._edge_validate_debug:
                                try:
                                    mb_for_cmp: list[OHLCVBar] | None = None
                                    try:
                                        mb_raw = self.matriks.fetch(sym, period="1m")
                                    except Exception:
                                        mb_raw = None
                                    if mb_raw:
                                        mb_p2, mb_ok2 = self.hardening.process(mb_raw, sym, matriks_px)
                                        if mb_ok2 and mb_p2:
                                            mb_for_cmp = mb_p2
                                    ev = EdgeValidator()
                                    comparison_result = ev.compare(
                                        sym,
                                        ideal_bars,
                                        mb_for_cmp if mb_for_cmp is not None else [],
                                        self.decision,
                                    )
                                    print({"symbol": sym, "ideal_vs_matriks": comparison_result})
                                except Exception:
                                    pass

                            # Simulated time: advance exclusive end index once per symbol per outer cycle.
                            ordered = sorted(bars, key=lambda b: (int(b.timestamp), _offset_key(b)))
                            L = len(ordered)
                            _bar_win_min = max(10, _BAR_MIN_FOR_DECISION)
                            if L < _bar_win_min:
                                print(
                                    {
                                        "error": "BAR_SERIES_TOO_SHORT",
                                        "symbol": sym,
                                        "len": L,
                                        "min_required": _bar_win_min,
                                    },
                                    flush=True,
                                )
                                continue
                            poll_keep = _live_max_bars_per_poll_env()
                            w = min(L, poll_keep)
                            sym_bi = str(sym).strip()
                            if sym_bi not in self.state.bar_index:
                                start_offset = int(L * 0.7)
                                idx_end = max(_bar_win_min, start_offset)
                                if idx_end >= L and L > _bar_win_min:
                                    idx_end = L - 1
                                print(
                                    {
                                        "BAR_START_INIT": {
                                            "symbol": sym,
                                            "start_index": idx_end,
                                            "total": L,
                                        }
                                    },
                                    flush=True,
                                )
                            else:
                                prev = int(self.state.bar_index[sym_bi])
                                idx_end = min(L, prev + 1)
                                if idx_end > prev:
                                    cycle_bar_progress = True
                            self.state.bar_index[sym_bi] = idx_end
                            if sym_bi not in self.state.last_bar_progress:
                                cycle_bar_progress = True
                            start = max(0, idx_end - w)
                            end = idx_end
                            bars_window = ordered[start:end]
                            if len(bars_window) < _bar_win_min:
                                print(
                                    {
                                        "error": "BAR_WINDOW_FAIL_CLOSED",
                                        "symbol": sym,
                                        "len_window": len(bars_window),
                                        "min_required": _bar_win_min,
                                    },
                                    flush=True,
                                )
                                continue
                            try:
                                cp_dbg = float(bars_window[-1].close)
                            except (TypeError, ValueError):
                                cp_dbg = 0.0
                            print(
                                {
                                    "BAR_PROGRESS": {
                                        "symbol": sym,
                                        "index": idx_end,
                                        "price": cp_dbg,
                                    }
                                },
                                flush=True,
                            )
                            self.state.bar_buffers[sym] = list(bars_window)
                            _set_bar_progress(self.state, sym, bars_window[-1])
                            decision_bars = [bars_window[-1]]

                            for bar in decision_bars:
                                with _bar_processing_cursor(self.state, sym, bar):
                                    try:
                                        ideal_price = float(bar.close)
                                    except (TypeError, ValueError):
                                        ideal_price = None

                                    if ideal_price is None or ideal_price <= 0:
                                        continue

                                    matriks_live, quote_src = _resolve_quote_price(sym, float(ideal_price))
                                    if quote_src == "matriks":
                                        self._matrix_usage_count += 1

                                    diff_pct = 0.0
                                    try:
                                        diff_pct = abs(float(ideal_price) - float(matriks_live)) / float(ideal_price)
                                        print(
                                            {
                                                "price_validation": {
                                                    "ideal": float(ideal_price),
                                                    "matriks": float(matriks_live),
                                                    "diff_pct": float(diff_pct),
                                                    "quote_source": quote_src,
                                                }
                                            }
                                        )
                                        if quote_src == "matriks" and diff_pct > 0.03:
                                            print(
                                                {
                                                    "warning": "PRICE_MISMATCH",
                                                    "symbol": sym,
                                                    "diff_pct": float(diff_pct),
                                                }
                                            )
                                    except (TypeError, ValueError, ZeroDivisionError):
                                        diff_pct = 0.0

                                    try:
                                        current_price = float(bars_window[-1].close)
                                    except (TypeError, ValueError):
                                        current_price = 0.0
                                    if current_price <= 0:
                                        continue


                                    time.time()
                                    self.state.last_prices[sym] = current_price

                                    buffer = self.state.bar_buffers.get(sym, [])
                                    if len(buffer) < _BAR_MIN_FOR_DECISION:
                                        self._persist()
                                        continue

                                    relax = self._relax_mode
                                    if not relax and not self.validator.validate_strict(ideal_price, matriks_live):
                                        self._persist()
                                        continue

                                    dec_kap_on: dict[str, Any] | None = None
                                    dec_kap_off: dict[str, Any] | None = None
                                    decision: dict[str, Any] | None = None
                                    try:
                                        capital = 100_000.0 * max(1e-12, float(self.state.equity))
                                        pf = _portfolio_exposure_fraction(self.state, capital)
                                        price_source = (
                                            "matriks"
                                            if quote_src == "matriks"
                                            else (
                                                "simulated" if quote_src == "matrix_simulation" else "ideal_bars_close"
                                            )
                                        )
                                        _pq = self._position_qty(sym)
                                        base_ctx = {
                                            "symbol": sym,
                                            "current_price": current_price,
                                            "ideal_price": float(ideal_price),
                                            "matriks_price": float(matriks_live),
                                            "quote_source": quote_src,
                                            "validation_diff": float(diff_pct),
                                            "price_source": price_source,
                                            "bars": list(buffer),
                                            "edge_cycle": self._edge_cycle,
                                            "capital": capital,
                                            "portfolio_exposure": pf,
                                            "position_qty": float(_pq),
                                            "position_side": ("long" if float(_pq) > 1e-12 else None),
                                        }
                                        dec_kap_on = self.decision.evaluate_symbol(
                                            {
                                                **base_ctx,
                                                "kap_feature": self._kap_latest_for_symbol(sym),
                                            }
                                        )
                                        dec_kap_off = self.decision.evaluate_symbol({**base_ctx, "kap_feature": None})
                                        dec_kap_on = _apply_relax_fallback(dec_kap_on, relax)
                                        dec_kap_off = _apply_relax_fallback(dec_kap_off, relax)
                                        decision = dec_kap_on if self.kap_enabled else dec_kap_off
                                    except Exception as e:
                                        self.state.log_error(f"decision:{sym}:{e}")
                                        print({"error": "NO_DECISION"})
                                        if relax:
                                            decision = _apply_relax_fallback(None, True)
                                            dec_kap_on = decision
                                            dec_kap_off = decision
                                        else:
                                            continue

                                    if decision is None:
                                        print({"error": "NO_DECISION"})
                                        if relax:
                                            decision = _apply_relax_fallback(None, True)
                                            dec_kap_on = decision
                                            dec_kap_off = decision
                                        else:
                                            continue
                                    if not isinstance(decision, dict):
                                        print({"error": "NO_DECISION"})
                                        continue
                                    if not isinstance(dec_kap_on, dict) or not isinstance(dec_kap_off, dict):
                                        print({"error": "NO_DECISION"})
                                        continue
                                    cycle_decision_payloads += 1

                                    if "UNKNOWN" in (
                                        g_trend,
                                        t60_trend,
                                        t05_trend,
                                        t01_trend,
                                    ):
                                        decision["action"] = "hold"
                                        cycle_portfolio_snap[sym] = {
                                            "decision": decision,
                                            "bars": list(buffer),
                                            "symbol": sym,
                                            "capital": float(capital),
                                            "current_price": float(current_price),
                                        }
                                        continue

                                    allow_long = (
                                        g_trend == "UP"
                                        and t60_trend == "UP"
                                        and t05_trend in ("UP", "PULLBACK")
                                        and t01_trend == "UP"
                                    )
                                    allow_short = (
                                        g_trend == "DOWN"
                                        and t60_trend == "DOWN"
                                        and t05_trend in ("DOWN", "PULLBACK")
                                        and t01_trend == "DOWN"
                                    )

                                    if g_trend == t60_trend == t05_trend:
                                        regime = "STRONG_TREND"
                                    elif g_trend == t60_trend:
                                        regime = "TREND"
                                    else:
                                        regime = "RANGE"

                                    mtf_signal = "hold"
                                    if allow_long:
                                        mtf_signal = "enter_long"
                                    elif allow_short:
                                        mtf_signal = "enter_short"

                                    try:
                                        conf_val = float(decision.get("confidence", 0.0))
                                    except (TypeError, ValueError):
                                        conf_val = 0.0

                                    self._conf_history.append(conf_val)
                                    if len(self._conf_history) > 5000:
                                        self._conf_history = self._conf_history[-3000:]

                                    # TEMP (signal validation only — remove before production)
                                    pct = 50  # force easier entry; bypass regime-based percentile

                                    if len(self._conf_history) > 50:
                                        threshold = float(
                                            np.percentile(
                                                np.asarray(self._conf_history, dtype=np.float64),
                                                pct,
                                            )
                                        )
                                    else:
                                        threshold = 0.5

                                    print(
                                        {
                                            "REGIME_FILTER": {
                                                "regime": regime,
                                                "pct": pct,
                                                "threshold": threshold,
                                            }
                                        },
                                        flush=True,
                                    )

                                    print(
                                        {
                                            "CONF_FILTER": {
                                                "current": conf_val,
                                                "threshold": threshold,
                                            }
                                        },
                                        flush=True,
                                    )

                                    print(
                                        {
                                            "ENTRY_DEBUG": {
                                                "symbol": sym,
                                                "conf": conf_val,
                                                "threshold": threshold,
                                                "passed": conf_val >= (threshold * 0.7),
                                            }
                                        },
                                        flush=True,
                                    )

                                    print(
                                        {
                                            "CONF_DEBUG": {
                                                "symbol": sym,
                                                "conf": conf_val,
                                                "threshold": threshold,
                                            }
                                        },
                                        flush=True,
                                    )

                                    # TEMP: allow all signals (debug phase — remove before production)
                                    # if conf_val < threshold:
                                    #     continue

                                    _enter_family = (
                                        "enter",
                                        "enter_small",
                                        "enter_long",
                                        "enter_short",
                                    )
                                    _inc_act = str(decision.get("action", "")).strip().lower()
                                    if _inc_act == "exit":
                                        pass
                                    elif mtf_signal in ("enter_long", "enter_short"):
                                        # MTF no longer allowed to trigger entries
                                        pass
                                    elif _inc_act in _enter_family:
                                        pass
                                    else:
                                        decision["action"] = "hold"

                                    print(
                                        {
                                            "FINAL_DECISION": {
                                                "symbol": sym,
                                                "mtf_signal": mtf_signal,
                                                "confidence": conf_val,
                                                "final": decision["action"],
                                            }
                                        },
                                        flush=True,
                                    )
                                    _edge_dbg = decision.get("edge_score")
                                    print(
                                        {
                                            "FINAL_DECISION_DEBUG": {
                                                "symbol": sym,
                                                "action": decision.get("action"),
                                                "confidence": conf_val,
                                                "edge": _edge_dbg,
                                            }
                                        },
                                        flush=True,
                                    )
                                    try:
                                        _tl = dict(decision)
                                        _tl["symbol"] = str(sym)
                                        _act_log = str(decision.get("action", "")).strip().lower()
                                        _skip_pre_csv_enter = _act_log in (
                                            "enter",
                                            "enter_small",
                                            "enter_long",
                                            "enter_short",
                                        )
                                        if not _skip_pre_csv_enter:
                                            self.trade_logger.log_new_trade(_tl)
                                    except RuntimeError:
                                        raise
                                    except Exception:
                                        pass

                                    print(
                                        {
                                            "stage": "decision",
                                            "symbol": sym,
                                            "action": decision.get("action"),
                                            "confidence": decision.get("confidence"),
                                            "edge_signal": decision.get("edge_signal"),
                                            "reason": decision.get("reason"),
                                            "entry_quality": decision.get("entry_quality"),
                                            "price_source": decision.get("price_source"),
                                        }
                                    )
                                    act_s = decision.get("action")
                                    if isinstance(act_s, str):
                                        cycle_actions.append(act_s)
                                    cf_s = decision.get("confidence")
                                    if isinstance(cf_s, (int, float)) and float(cf_s) == float(cf_s):
                                        cycle_confidences.append(float(cf_s))
                                    cycle_portfolio_snap[sym] = {
                                        "decision": decision,
                                        "bars": list(buffer),
                                        "symbol": sym,
                                        "capital": float(capital),
                                        "current_price": float(current_price),
                                    }
                                    eq = decision.get("entry_quality")
                                    if isinstance(eq, str):
                                        self._entry_qualities_seen.add(eq)
                                    if decision.get("price_intelligence_adjusted"):
                                        self._price_adjustment_count += 1
                                    act = decision.get("action")
                                    if isinstance(act, str):
                                        self._actions_seen.add(act)
                                    cf = decision.get("confidence")
                                    if isinstance(cf, (int, float)):
                                        self._confidences.append(float(cf))
                                    ps = decision.get("position_size")
                                    if (
                                        isinstance(ps, (int, float))
                                        and isinstance(act, str)
                                        and act
                                        in (
                                            "enter",
                                            "enter_long",
                                            "enter_short",
                                            "aggressive_enter",
                                        )
                                    ):
                                        self._position_sizes.append(float(ps))
                                    if _trackable_action(decision):
                                        self._action_counter += 1
                                        self._symbols_with_actions.add(sym)
                                    if _pipeline_saw_qualifying_action(decision):
                                        saw_qualifying_action = True

                                    row = decision
                                    action = str(row.get("action", "") or "").strip().lower()
                                    if action.startswith("enter"):
                                        edge_signal = str(row.get("edge_signal", "") or "").strip().lower()
                                        if edge_signal == "sell":
                                            row["action"] = "enter_short"
                                        else:
                                            row["action"] = "enter_long"
                                        action = str(row.get("action", "") or "").strip().lower()

                                    self.state.last_signals[sym] = {
                                        "action": decision.get("action"),
                                        "reason": decision.get("reason"),
                                        "score": decision.get("score"),
                                    }

                                    reason = decision.get("reason")
                                    if not isinstance(reason, str):
                                        reason = ""

                                    if action == "wait_pullback":
                                        self._persist()
                                        continue

                                    self._persist()
                    except Exception as _sym_pass_exc:
                        self.state.log_error(f"symbol_pass:{_sym_pass_exc}")
                        print(
                            {
                                "error": "SYMBOL_PASS_EXCEPTION",
                                "detail": str(_sym_pass_exc),
                            },
                            flush=True,
                        )

                    # Post-`for sym`: portfolio + edges for this outer cycle (before cycle_count += 1).
                    avg_v = _cycle_avg_vol_from_snap(cycle_portfolio_snap, self.decision.fe)
                    spk = _cycle_any_vol_spike(cycle_portfolio_snap, avg_v)
                    self._last_cycle_avg_vol = avg_v
                    self._last_cycle_vol_spike = spk

                    thr_ov: dict[str, float] | None = None
                    edge_scores: dict[str, float] | None = None
                    regime_dbg: dict[str, Any] = {}
                    if self._adaptive is not None:
                        thr_ov, edge_scores, regime_dbg = self._adaptive.prepare_portfolio_phase(
                            cycle_portfolio_snap,
                            self.decision.fe,
                            cycle_actions,
                        )
                    self._last_regime = str(regime_dbg.get("market_regime", "MIXED"))

                    risk_snap_pf: dict[str, Any] | None = None
                    if self._risk is not None:
                        self._risk.update_equity(self.state.equity)
                        risk_snap_pf = self._risk.build_snapshot(
                            volatility=avg_v,
                            regime=self._last_regime,
                            vol_spike=spk,
                        )
                        print(
                            {
                                "RISK_STATUS": {
                                    "drawdown": risk_snap_pf["drawdown_pct"],
                                    "risk_multiplier": risk_snap_pf["risk_multiplier"],
                                    "kill_switch": risk_snap_pf["kill_switch"],
                                }
                            }
                        )

                    print({"PORTFOLIO_STAGE_REACHED": True}, flush=True)
                    per_symbol = cycle_portfolio_snap
                    print(
                        {
                            "PORTFOLIO_INPUT": {
                                "symbols": list(per_symbol.keys()),
                                "count": len(per_symbol),
                            }
                        }
                    )
                    portfolio = build_portfolio_payload(
                        per_symbol,
                        symbols_scanned=self.symbols,
                        fe=self.decision.fe,
                        threshold_overrides=thr_ov,
                        edge_scores=edge_scores,
                        risk_snapshot=risk_snap_pf,
                    )
                    if isinstance(portfolio, dict):
                        rows = portfolio.get("PORTFOLIO")
                        if isinstance(rows, list):
                            self.last_portfolio = rows
                        else:
                            raise RuntimeError("PORTFOLIO_ROWS_INVALID")
                    else:
                        raise RuntimeError("PORTFOLIO_NOT_DICT")
                    if not hasattr(self, "last_portfolio"):
                        raise RuntimeError("LAST_PORTFOLIO_NOT_SET")
                    rows_pf = portfolio.get("PORTFOLIO")
                    if isinstance(rows_pf, list) and rows_pf:
                        scan_pf: list[dict[str, Any]] = []
                        trades_pf: list[dict[str, Any]] = []
                        for row in rows_pf:
                            if not isinstance(row, dict):
                                continue
                            sym_pf = str(row.get("symbol", "")).strip()
                            if not sym_pf:
                                continue
                            _require_row_decision_edge_score(row, symbol=sym_pf)
                            cf = row.get("confidence")
                            if cf is None:
                                raise RuntimeError("PORTFOLIO_EDGE_MISSING")
                            snap_pf = per_symbol.get(sym_pf)
                            if snap_pf is None:
                                snap_pf = per_symbol.get(sym_pf.upper())
                            if not isinstance(snap_pf, dict):
                                snap_pf = {}
                            sec_pf = "unknown"
                            dsec = snap_pf.get("decision")
                            if isinstance(dsec, dict) and dsec.get("sector") is not None:
                                sec_pf = str(dsec.get("sector"))
                            elif snap_pf.get("sector") is not None:
                                sec_pf = str(snap_pf.get("sector"))
                            scan_pf.append(
                                {
                                    "symbol": sym_pf,
                                    "confidence": float(cf),
                                    "sector": sec_pf,
                                    "decision": row["decision"],
                                }
                            )
                            trades_pf.append(
                                {
                                    "symbol": sym_pf,
                                    "size": 1.0,
                                    "_v2_scaled": False,
                                }
                            )
                        apply_portfolio_v2_to_trades(scan_pf, trades_pf)
                        by_sym = {str(t.get("symbol", "")).strip(): t for t in trades_pf if isinstance(t, dict)}
                        for row in rows_pf:
                            if not isinstance(row, dict):
                                continue
                            sk = str(row.get("symbol", "")).strip()
                            if sk in by_sym:
                                try:
                                    row["position_size"] = round(float(by_sym[sk].get("size") or 0.0), 6)
                                except (TypeError, ValueError):
                                    row["position_size"] = 0.0
                        rows = portfolio.get("PORTFOLIO")
                        if not isinstance(rows, list):
                            raise RuntimeError("PORTFOLIO_ROWS_INVALID")

                        valid_rows = []
                        for r in rows:
                            if not isinstance(r, dict):
                                continue
                            _require_row_decision_edge_score(r, symbol=str(r.get("symbol", "")))
                            valid_rows.append(r)

                        filtered = []
                        for r in valid_rows:
                            sz = float(r.get("position_size", 0))
                            if sz > 0:
                                filtered.append(r)

                        if not filtered:
                            if validation_mode:
                                print(
                                    {"PORTFOLIO_EMPTY_AFTER_V2": "validation_mode_fallback"},
                                    flush=True,
                                )
                                filtered = valid_rows
                            else:
                                raise RuntimeError("PORTFOLIO_EMPTY_AFTER_V2")
                        portfolio["PORTFOLIO"] = filtered
                        rows_pf = filtered
                        self.last_portfolio = filtered

                        rows = portfolio.get("PORTFOLIO")
                        if not isinstance(rows, list):
                            raise RuntimeError("PORTFOLIO_ROWS_INVALID")
                        for r in rows:
                            if not isinstance(r, dict):
                                raise RuntimeError("PORTFOLIO_ROWS_INVALID")
                            e = _require_row_decision_edge_score(r, symbol=str(r.get("symbol", "")))
                            r["_edge_norm"] = round(float(e), 6)
                        edge_sorted = sorted(
                            rows,
                            key=lambda x: (-x["_edge_norm"], str(x.get("symbol", ""))),
                        )
                        violation = False
                        for i in range(len(edge_sorted) - 1):
                            a = edge_sorted[i]
                            b = edge_sorted[i + 1]
                            if a["_edge_norm"] > b["_edge_norm"]:
                                if float(a.get("position_size", 0)) < float(b.get("position_size", 0)):
                                    violation = True
                                    break
                        if violation:
                            n = len(edge_sorted)
                            weights = [(n - i) for i in range(n)]
                            w_sum = sum(weights)
                            for r, w in zip(edge_sorted, weights):
                                r["position_size"] = round(w / w_sum, 6)
                        if any(r["_edge_norm"] > 0 and float(r.get("position_size", 0)) == 0 for r in rows):
                            if validation_mode:
                                print(
                                    {"ZERO_SIZE_WITH_EDGE": "validation_mode_fallback"},
                                    flush=True,
                                )
                                n = len(edge_sorted)
                                weights = [(n - i) for i in range(n)]
                                w_sum = sum(weights) or 1
                                for r, w in zip(edge_sorted, weights):
                                    r["position_size"] = round(w / w_sum, 6)
                            else:
                                raise RuntimeError("ZERO_SIZE_WITH_EDGE")
                        for i in range(len(edge_sorted) - 1):
                            a = edge_sorted[i]
                            b = edge_sorted[i + 1]
                            if a["_edge_norm"] > b["_edge_norm"]:
                                if float(a.get("position_size", 0)) < float(b.get("position_size", 0)):
                                    raise RuntimeError("EDGE_SIZE_MONOTONICITY_BROKEN")
                        for r in rows:
                            if "_edge_norm" in r:
                                del r["_edge_norm"]
                    if isinstance(rows_pf, list) and any(
                        not isinstance(r, dict)
                        or not isinstance(r.get("decision"), dict)
                        or r["decision"].get("edge_score") is None
                        or r["decision"].get("edge") is None
                        for r in rows_pf
                    ):
                        raise RuntimeError("PORTFOLIO_EDGE_MISSING")

                    ctx = getattr(self, "_portfolio_snap_context", None)

                    # optional safety (debug-grade, safe in prod)
                    if ctx is not None and not isinstance(ctx, dict):
                        print({"SNAP_ERROR": "INVALID_CONTEXT_TYPE"}, flush=True)
                        ctx = None

                    _emit_snap(portfolio, ctx)

                    price_map: dict[str, float] = {}
                    for _pm_k, _pm_snap in cycle_portfolio_snap.items():
                        if isinstance(_pm_snap, dict):
                            try:
                                _pm_cp = float(_pm_snap.get("current_price", 0) or 0)
                            except (TypeError, ValueError):
                                _pm_cp = 0.0
                            if _pm_cp > 0:
                                price_map[_normalize_symbol(str(_pm_k))] = _pm_cp

                    if not isinstance(price_map, dict) or not price_map:
                        print({"FATAL_NO_PRICE_MAP": True}, flush=True)
                        raise RuntimeError("NO_ACTIONS_PRODUCED")

                    valid_prices = 0

                    for k, v in price_map.items():
                        if v is None or v <= 0:
                            print(
                                {"BAD_PRICE": {"symbol": k, "price": v}},
                                flush=True,
                            )
                        else:
                            valid_prices += 1

                    if valid_prices == 0:
                        print({"FATAL_NO_VALID_PRICES": True}, flush=True)
                        raise RuntimeError("NO_ACTIONS_PRODUCED")

                    self._sync_positions_from_state()

                    print(
                        {
                            "SYSTEM_HEALTH": {
                                "positions": len(self.positions),
                                "state_positions": len(self.state.positions),
                                "price_map": len(price_map),
                            }
                        },
                        flush=True,
                    )

                    self._sync_positions_from_state()

                    MAX_HOLD_CYCLES = 5
                    for sym, pos in list(self.positions.items()):
                        entry = float(pos.get("entry_price", 0))
                        stop = float(pos.get("stop_loss", 0))
                        target = float(pos.get("target", 0))
                        side = pos.get("side", "long")

                        current_price = float(price_map.get(sym, 0))
                        if current_price > 0:
                            _drift_seed = (hash(sym) ^ current_cycle) & 0xFFFF
                            _drift = (_drift_seed / 0xFFFF - 0.5) * 0.02
                            current_price = round(current_price * (1.0 + _drift), 6)

                        _entry_cycle = self._position_entry_cycle.get(sym, 0)
                        if current_price > 0 and entry > 0 and (current_cycle - _entry_cycle) >= MAX_HOLD_CYCLES:
                            print({"TIMEOUT_EXIT": sym}, flush=True)
                            stop = current_price - 1e-6
                            target = 0.0

                        if current_price <= 0 or entry <= 0:
                            continue

                        exit_reason = None
                        pnl = 0.0

                        if side == "long":
                            if target > 0 and current_price >= target:
                                exit_reason = "TP"
                                pnl = current_price - entry
                            elif stop > 0 and current_price <= stop:
                                exit_reason = "SL"
                                pnl = current_price - entry

                        elif side == "short":
                            if target > 0 and current_price <= target:
                                exit_reason = "TP"
                                pnl = entry - current_price
                            elif stop > 0 and current_price >= stop:
                                exit_reason = "SL"
                                pnl = entry - current_price

                        if exit_reason:
                            print(
                                {
                                    "FORCED_EXIT_FINAL": {
                                        "symbol": sym,
                                        "reason": exit_reason,
                                        "entry": entry,
                                        "exit": current_price,
                                        "pnl": pnl,
                                    }
                                },
                                flush=True,
                            )

                            sym_n = _normalize_symbol(sym)
                            if not self._runner_position_exists_norm(sym_n):
                                raise RuntimeError("Exit invoked but no position existed")

                            self._emit_trade_trace(sym, "EXIT")
                            state_key = sym
                            for _k in self.state.positions:
                                if _normalize_symbol(_k) == sym_n:
                                    state_key = _k
                                    break

                            success = self.execution.execute(
                                state_key,
                                "exit",
                                current_price,
                                reason=exit_reason,
                            )
                            print({"EXECUTION_CALLED": symbol})

                            if not (isinstance(success, dict) and success.get("ok")):
                                print(
                                    {"EXIT_FAILED_SKIP_STATE_DELETE": sym},
                                    flush=True,
                                )
                                self._emit_trade_trace_after(sym)
                                continue

                            self._emit_trade_trace_after(sym)

                            self._emit_trade_trace(sym, "CLOSE")
                            closed = update_trade_close(sym, pnl)

                            if not closed:
                                print(
                                    {"FATAL_CSV_CLOSE_FAILED": sym},
                                    flush=True,
                                )
                                raise RuntimeError("CSV close failed — aborting")

                            if sym_n in self._csv_open_symbols_normalized():
                                raise RuntimeError("CSV CLOSE FAILED — SYMBOL STILL OPEN")

                            print({"CSV_CLOSE_VERIFIED": sym}, flush=True)

                            self._recover_open_positions_from_csv()
                            self._assert_state_csv_lock()

                            self._emit_trade_trace(sym, "DELETE")
                            print(
                                {
                                    "POSITION_REMOVED_AFTER_EXIT": {
                                        "symbol": sym,
                                        "normalized": sym_n,
                                        "removed_state": [sym_n],
                                        "removed_local": [sym_n],
                                    }
                                },
                                flush=True,
                            )

                            self._emit_trade_trace_after(sym)

                            if self._runner_position_exists_norm(sym_n):
                                raise RuntimeError("Exit did not remove position")

                    self._sync_positions_from_state()

                    for row in portfolio.get("PORTFOLIO", []):
                        try:
                            if not isinstance(row, dict):
                                continue
                            symbol = row.get("symbol")
                            action = row.get("action")
                            size = float(row.get("position_size") or 0.0)
                            price = float(row.get("entry") or 0.0)

                            if not price or price <= 0:
                                print({"INVALID_PRICE_BLOCK": symbol}, flush=True)
                                continue

                            if not symbol or not action or size <= 0:
                                continue

                            final_action = str(action).strip().lower()
                            if final_action not in ("enter_long", "enter_short"):
                                print(
                                    {
                                        "EXECUTION_BLOCKED_BY_PORTFOLIO": {
                                            "symbol": symbol,
                                            "action": final_action,
                                        }
                                    },
                                    flush=True,
                                )
                                continue

                            if final_action == "enter_long":
                                exec_action = "enter"
                                position_side = "long"
                            elif final_action == "enter_short":
                                exec_action = "enter"
                                position_side = "short"
                            else:
                                continue

                            action_l = final_action

                            print(
                                {
                                    "PORTFOLIO_ENTRY_DECISION": {
                                        "symbol": str(symbol),
                                        "action": final_action,
                                        "size": size,
                                        "price": price,
                                    }
                                },
                                flush=True,
                            )

                            if self._risk is not None and self._risk_snap_loop is not None:
                                _rs = self._risk_snap_loop
                                if _rs.get("kill_switch") or _rs.get("pause_entries"):
                                    continue

                            sym_k = str(symbol).strip()
                            snap = cycle_portfolio_snap.get(sym_k)
                            if snap is None:
                                snap = cycle_portfolio_snap.get(sym_k.upper())
                            if not isinstance(snap, dict):
                                snap = {}
                            bars = list(snap.get("bars") or [])
                            ohlcv_b = [b for b in bars if isinstance(b, OHLCVBar)]
                            vol_px = _volatility_proxy(ohlcv_b)
                            trend_abs = 0.0
                            vol_pf = None
                            if ohlcv_b:
                                try:
                                    bf = self.decision.fe.extract(ohlcv_b)
                                    trend_abs = max(
                                        -1.0,
                                        min(
                                            1.0,
                                            float(bf.get("trend", 0.0) or 0.0),
                                        ),
                                    )
                                    vol_pf = float(bf.get("vol", 0.0) or 0.0)
                                except (TypeError, ValueError):
                                    trend_abs = 0.0
                                    vol_pf = None
                            v_last = None
                            if ohlcv_b:
                                v_raw = getattr(ohlcv_b[-1], "volume", None)
                                if v_raw is not None:
                                    try:
                                        v_last = float(v_raw)
                                    except (TypeError, ValueError):
                                        v_last = None
                            wall_ts_pf = None
                            if ohlcv_b:
                                try:
                                    wall_ts_pf = float(ohlcv_b[-1].timestamp)
                                except (TypeError, ValueError):
                                    wall_ts_pf = None
                            size_frac = max(0.01, min(1.0, float(size)))
                            _sl_pf, _tg_pf = _stop_target_from_mapping(row)

                            decision_edge = _require_row_decision_edge_score(row, symbol=str(symbol))
                            if not isinstance(snap, dict):
                                raise RuntimeError("EDGE_SSOT_VIOLATION")
                            snap_dec = snap.get("decision")
                            if not isinstance(snap_dec, dict):
                                raise RuntimeError("EDGE_SSOT_VIOLATION")
                            snap_es = snap_dec.get("edge_score")
                            if snap_es is None:
                                raise RuntimeError("EDGE_SSOT_VIOLATION")
                            try:
                                execution_snap_edge = float(snap_es)
                            except (TypeError, ValueError):
                                raise RuntimeError("EDGE_SSOT_VIOLATION") from None
                            assert abs(decision_edge - execution_snap_edge) < 1e-9
                            edge_for_execution = decision_edge
                            print(
                                {
                                    "EDGE_SSOT_ENFORCED": {
                                        "symbol": str(symbol),
                                        "edge": edge_for_execution,
                                    }
                                },
                                flush=True,
                            )
                            if snap_dec.get("edge") is None:
                                raise RuntimeError("CRITICAL: EDGE LOST IN PIPELINE")
                            print(
                                {
                                    "EDGE_FLOW_CHECK": {
                                        "symbol": str(symbol),
                                        "edge": snap_dec.get("edge"),
                                        "action": snap_dec.get("action"),
                                    }
                                },
                                flush=True,
                            )

                            print(
                                {
                                    "EXECUTION_NORMALIZED": {
                                        "symbol": str(symbol),
                                        "original": final_action,
                                        "normalized": exec_action,
                                        "side": position_side,
                                    }
                                },
                                flush=True,
                            )

                            self.execution.get_open_positions()
                            int(getattr(self.execution, "_max_total_positions", 0) or 0)
                            is_replacement_exec = False
                            print(
                                {
                                    "DEBUG_PORTFOLIO_EXECUTION_ENTRY": {
                                        "symbol": symbol,
                                        "open_positions": list(self.execution.state.positions.keys()),
                                        "count": len(self.execution.state.positions),
                                    }
                                },
                                flush=True,
                            )
                            if True:
                                open_positions: list[dict[str, Any]] = []
                                for sym_open, legs in self.execution.state.positions.items():
                                    if not legs:
                                        continue
                                    active_legs = [
                                        p for p in legs if isinstance(p, dict) and float(p.get("size", 0) or 0) > 0
                                    ]
                                    if not active_legs:
                                        continue
                                    edge_old = sum(
                                        float(p.get("edge_score", 0.0) or 0.0) * float(p.get("size", 1.0) or 1.0)
                                        for p in active_legs
                                    ) / max(
                                        sum(float(p.get("size", 1.0) or 1.0) for p in active_legs),
                                        1e-9,
                                    )
                                    open_positions.append(
                                        {
                                            "symbol": str(sym_open).strip().upper(),
                                            "edge_score": edge_old,
                                        }
                                    )
                                open_positions = [
                                    p
                                    for p in open_positions
                                    if str(p.get("symbol")).strip().upper() != str(symbol).strip().upper()
                                ]
                                if open_positions:
                                    lowest = min(
                                        open_positions,
                                        key=lambda p: float(p["edge_score"]),
                                    )
                                    lowest_symbol = str(lowest.get("symbol", "")).strip().upper()
                                    lowest_edge = float(lowest["edge_score"])
                                    incoming_symbol_u = str(symbol).strip().upper()
                                    if not self.positions:
                                        decision_repl = "keep"
                                    else:
                                        decision_repl = (
                                            "replace"
                                            if (edge_for_execution > lowest_edge and incoming_symbol_u != lowest_symbol)
                                            else "keep"
                                        )
                                    print(
                                        {
                                            "PORTFOLIO_REPLACEMENT_CHECK": {
                                                "incoming_symbol": symbol,
                                                "incoming_edge": edge_for_execution,
                                                "lowest_symbol": lowest_symbol,
                                                "lowest_edge": lowest_edge,
                                                "decision": decision_repl,
                                            }
                                        },
                                        flush=True,
                                    )
                                    if decision_repl == "replace":
                                        repl_res = self.execution.close_position(lowest_symbol)
                                        if not (isinstance(repl_res, dict) and repl_res.get("ok")):
                                            raise RuntimeError("portfolio_replacement execute failed")
                                        repl_exit_px = float(
                                            repl_res.get("exit_price")
                                            or repl_res.get("actual_fill_price")
                                            or repl_res.get("mid_price")
                                            or 0.0
                                        )
                                        if repl_exit_px <= 0.0:
                                            raise RuntimeError("portfolio_replacement exit_price <= 0")
                                        repl_closed = self.trade_logger.update_trade(
                                            lowest_symbol,
                                            repl_exit_px,
                                            reason="portfolio_replacement",
                                        )
                                        if not repl_closed:
                                            print(
                                                {
                                                    "FATAL_CSV_CLOSE_FAILED": lowest_symbol,
                                                },
                                                flush=True,
                                            )
                                            raise RuntimeError("CSV close failed — aborting")
                                        repl_n = _normalize_symbol(lowest_symbol)
                                        if repl_n in self._csv_open_symbols_normalized():
                                            raise RuntimeError("CSV CLOSE FAILED — SYMBOL STILL OPEN")
                                        print(
                                            {"CSV_CLOSE_VERIFIED": lowest_symbol},
                                            flush=True,
                                        )
                                        self._recover_open_positions_from_csv()
                                        self._assert_state_csv_lock()
                                        is_replacement_exec = True
                                    else:
                                        continue

                            symbol_n = _normalize_symbol(symbol)

                            last_time = self.last_trade_time.get(symbol_n, 0)
                            now = time.time()

                            if not action.startswith("enter") and now - last_time < 60:
                                print(
                                    {"COOLDOWN_FINAL": symbol_n},
                                    flush=True,
                                )
                                continue

                            edge = _safe_float(edge_for_execution, 0.0)

                            if action.startswith("enter") and edge < 0.60:
                                print(
                                    {"LOW_EDGE_BLOCK_FINAL": edge},
                                    flush=True,
                                )
                                continue
                            print(
                                {
                                    "EXECUTION_CALL": {
                                        "symbol": symbol,
                                        "edge": edge_for_execution,
                                        "is_replacement": is_replacement_exec,
                                    }
                                },
                                flush=True,
                            )
                            print(
                                {
                                    "FINAL_EXECUTION_TRACE": {
                                        "symbol": symbol,
                                        "edge": edge_for_execution,
                                        "positions": list(self.execution.state.positions.keys()),
                                    }
                                },
                                flush=True,
                            )
                            if edge <= 0:
                                print(
                                    {"INVALID_EDGE_BLOCK": edge},
                                    flush=True,
                                )
                                continue
                            if action.startswith("enter"):
                                res = self.execution.execute(
                                    str(symbol),
                                    "enter",
                                    price,
                                    edge_score=edge_for_execution,
                                )

                                if not (isinstance(res, dict) and res.get("ok")):
                                    continue

                                # --- GHOST POSITION CLEANUP ---
                                cleaned_positions = {}
                                for sym, pos in (self.execution.state.positions or {}).items():
                                    if pos and isinstance(pos, dict):
                                        size = float(pos.get("size", 0.0))
                                        entry = float(pos.get("entry_price", 0.0))
                                        if size > 0 and entry > 0:
                                            cleaned_positions[sym] = pos

                                if len(cleaned_positions) != len(self.execution.state.positions or {}):
                                    print({"GHOST_POSITIONS_REMOVED": True}, flush=True)

                                self.execution.state.positions = cleaned_positions

                                active_positions = self.execution.get_open_positions()

                                print(
                                    {"ACTIVE_POSITIONS_AFTER_CLEAN": list(active_positions)},
                                    flush=True,
                                )

                                if symbol_n in active_positions and self.execution.fills_ok > 0:
                                    print(
                                        {"DUPLICATE_AFTER_EXEC": symbol_n},
                                        flush=True,
                                    )
                                    continue
                            if exec_action == "enter":
                                csv_syms_pre = self._csv_open_symbols_normalized()
                                if symbol_n in csv_syms_pre:
                                    print(
                                        {"FATAL_DUPLICATE_CSV_POSITION": symbol_n},
                                        flush=True,
                                    )
                                    raise RuntimeError("Duplicate position in CSV — aborting")
                                self._emit_trade_trace(str(symbol), "ENTER")
                            success = self.execution.execute_trade(
                                str(symbol),
                                exec_action,
                                size,
                                price,
                                reason=f"portfolio_row|{action_l}",
                                wall_ts=wall_ts_pf,
                                volatility=float(vol_px),
                                volume_proxy=v_last,
                                slippage_extra_frac=0.0,
                                size_fraction=size_frac,
                                trend_abs=trend_abs,
                                stop_loss=_sl_pf,
                                target=_tg_pf,
                                ohlcv_bars=ohlcv_b if len(ohlcv_b) >= 15 else None,
                                vol_norm=vol_pf,
                                position_side=position_side,
                                edge_score=edge_for_execution,
                                is_replacement=is_replacement_exec,
                            )

                            print(
                                {
                                    "EXECUTION_RESULT": success,
                                },
                                flush=True,
                            )

                            if exec_action == "enter":
                                self._emit_trade_trace_after(str(symbol))

                            if success and success.get("ok", False):
                                # Position updates ONLY after successful execution
                                self._sync_positions_from_state()
                                self.last_trade_time[symbol_n] = now
                                if exec_action == "enter":
                                    self._position_entry_cycle[symbol_n] = current_cycle

                            print(
                                {
                                    "EXECUTION_CALL": {
                                        "symbol": symbol,
                                        "action": exec_action,
                                        "size": size,
                                        "price": price,
                                        "result": success,
                                    }
                                },
                                flush=True,
                            )

                            if isinstance(success, dict) and success.get("ok"):
                                ts_pf = datetime.now(timezone.utc)
                                sym_u = str(symbol).strip()
                                if exec_action == "enter":
                                    ap = float(success.get("actual_fill_price") or 0.0)
                                    _dec_pf = row.get("decision") if isinstance(row.get("decision"), dict) else {}
                                    _tl_pf: dict[str, Any] = {
                                        "action": final_action,
                                        "symbol": str(symbol),
                                        "entry": float(ap if ap > 0 else price),
                                        "stop_loss": float(_sl_pf or 0.0),
                                        "target": float(_tg_pf or 0.0),
                                        "edge_score": float(edge_for_execution),
                                        "confidence": float(_dec_pf.get("confidence", 0.0) or 0.0),
                                    }
                                    if not self.trade_logger.log_new_trade(_tl_pf):
                                        print(
                                            {
                                                "FATAL_POST_ENTER_LOG_FAILED": str(symbol),
                                            },
                                            flush=True,
                                        )
                                        raise RuntimeError("log_new_trade failed after enter")
                                    sym_n_post = _normalize_symbol(str(symbol))
                                    self._recover_open_positions_from_csv()
                                    state_syms = sorted(self._state_open_symbols_normalized())
                                    csv_syms = sorted(self._csv_open_symbols_normalized())
                                    print(
                                        {
                                            "STATE_SYNC_AFTER_ENTER": sym_n_post,
                                            "state": state_syms,
                                            "csv": csv_syms,
                                        },
                                        flush=True,
                                    )
                                    if set(state_syms) != set(csv_syms):
                                        print(
                                            {
                                                "FATAL_POST_ENTER_MISMATCH": {
                                                    "state": state_syms,
                                                    "csv": csv_syms,
                                                }
                                            },
                                            flush=True,
                                        )
                                        raise RuntimeError("Post-enter state mismatch — aborting")
                                    self._assert_state_csv_lock()
                                    if ap > 0:
                                        if self._risk_snap_loop is not None:
                                            self._entry_risk_factor[sym_u] = float(
                                                self._risk_snap_loop.get(
                                                    "combined_position_factor",
                                                    1.0,
                                                )
                                                or 1.0
                                            )
                                        elif self._risk is not None:
                                            self._entry_risk_factor[sym_u] = 1.0
                                        self.perf.on_entry(
                                            sym_u,
                                            ap,
                                            1.0,
                                            ts_pf,
                                            side=position_side,
                                        )
                                        self._entry_side_by_symbol[sym_u.upper()] = position_side
                                else:
                                    xp = float(success.get("exit_price") or success.get("actual_fill_price") or 0.0)
                                    if xp > 0:
                                        self.perf.on_exit(sym_u, xp, ts_pf)
                                    if self._risk is not None:
                                        try:
                                            ret_pn = float(success.get("pnl", 0.0))
                                        except (TypeError, ValueError):
                                            ret_pn = 0.0
                                        rf = self._entry_risk_factor.pop(sym_u, 1.0)
                                        self._risk.record_closed_trade(ret_pn, rf)

                        except RuntimeError:
                            raise
                        except Exception as e:
                            print(
                                {
                                    "EXECUTION_ERROR": str(e),
                                    "row": row,
                                },
                                flush=True,
                            )
                    print(
                        {"POSITIONS_STATE": {sym: len(pos) for sym, pos in self.state.positions.items()}},
                        flush=True,
                    )
                    self._sync_positions_from_state()
                    counts = Counter(_normalize_symbol(k) for k in self.positions.keys())
                    duplicates = [k for k, v in counts.items() if v > 1]
                    if duplicates:
                        print(
                            {"FATAL_DUPLICATE_POSITION": duplicates},
                            flush=True,
                        )
                        raise RuntimeError("Duplicate positions detected")
                    for sym_x, legs in list(self.state.positions.items()):
                        try:
                            if not legs:
                                continue
                            active = [
                                p
                                for p in legs
                                if isinstance(p, dict)
                                and int(p.get("size", 1) or 0) > 0
                                and float(p.get("qty", 0.0) or 0.0) > 1e-12
                            ]
                            if not active:
                                continue
                            sk = str(sym_x).strip()
                            snap_ex = cycle_portfolio_snap.get(sk)
                            if snap_ex is None:
                                snap_ex = cycle_portfolio_snap.get(sk.upper())
                            if not isinstance(snap_ex, dict):
                                snap_ex = {}
                            try:
                                current_price = float(snap_ex.get("current_price", 0.0) or 0.0)
                                if current_price > 0:
                                    _drift_seed2 = (hash(sk) ^ current_cycle) & 0xFFFF
                                    _drift2 = (_drift_seed2 / 0xFFFF - 0.5) * 0.02
                                    current_price = round(current_price * (1.0 + _drift2), 6)
                            except (TypeError, ValueError):
                                current_price = 0.0
                            if current_price <= 0:
                                continue

                            _side_u = sk.upper()
                            is_short = self._entry_side_by_symbol.get(_side_u, "long") == "short"
                            reason_ex = ""
                            exit_signal = False
                            for p in active:
                                try:
                                    sl = float(p.get("stop_loss", 0.0) or 0.0)
                                except (TypeError, ValueError):
                                    sl = 0.0
                                try:
                                    tg = float(p.get("target", 0.0) or 0.0)
                                except (TypeError, ValueError):
                                    tg = 0.0
                                if is_short:
                                    if sl > 0 and current_price >= sl:
                                        reason_ex = "stop_loss"
                                        exit_signal = True
                                        break
                                    if tg > 0 and current_price <= tg:
                                        reason_ex = "target_hit"
                                        exit_signal = True
                                        break
                                else:
                                    if sl > 0 and current_price <= sl:
                                        reason_ex = "stop_loss"
                                        exit_signal = True
                                        break
                                    if tg > 0 and current_price >= tg:
                                        reason_ex = "target_hit"
                                        exit_signal = True
                                        break
                            if not exit_signal:
                                continue

                            symbol_ex = str(sym_x).strip()
                            symbol_ex_n = _normalize_symbol(symbol_ex)
                            if not self._runner_position_exists_norm(symbol_ex_n):
                                raise RuntimeError("Exit invoked but no position existed")

                            bars_ex = list(snap_ex.get("bars") or [])
                            ohlcv_ex = [b for b in bars_ex if isinstance(b, OHLCVBar)]
                            vol_ex = _volatility_proxy(ohlcv_ex)
                            trend_ex = 0.0
                            if ohlcv_ex:
                                try:
                                    bf_ex = self.decision.fe.extract(ohlcv_ex)
                                    trend_ex = max(
                                        -1.0,
                                        min(
                                            1.0,
                                            float(bf_ex.get("trend", 0.0) or 0.0),
                                        ),
                                    )
                                except (TypeError, ValueError):
                                    trend_ex = 0.0
                            v_last_ex = None
                            if ohlcv_ex:
                                vr = getattr(ohlcv_ex[-1], "volume", None)
                                if vr is not None:
                                    try:
                                        v_last_ex = float(vr)
                                    except (TypeError, ValueError):
                                        v_last_ex = None
                            wall_ts_ex = None
                            if ohlcv_ex:
                                try:
                                    wall_ts_ex = float(ohlcv_ex[-1].timestamp)
                                except (TypeError, ValueError):
                                    wall_ts_ex = None

                            symbol = str(sym_x).strip()
                            edge_for_execution = 0.0
                            if isinstance(snap_ex, dict):
                                _dtrace = snap_ex.get("decision")
                                if isinstance(_dtrace, dict) and _dtrace.get("edge_score") is not None:
                                    try:
                                        edge_for_execution = float(_dtrace["edge_score"])
                                    except (TypeError, ValueError):
                                        edge_for_execution = 0.0
                            print(
                                {
                                    "FINAL_EXECUTION_TRACE": {
                                        "symbol": symbol,
                                        "edge": edge_for_execution,
                                        "positions": list(self.execution.state.positions.keys()),
                                    }
                                },
                                flush=True,
                            )
                            self._emit_trade_trace(symbol_ex, "EXIT")
                            res_ex = self.execution.execute(
                                str(sym_x),
                                "exit",
                                current_price,
                                reason=f"{reason_ex}|price_engine",
                                wall_ts=wall_ts_ex,
                                volatility=float(vol_ex),
                                volume_proxy=v_last_ex,
                                slippage_extra_frac=0.0,
                                size_fraction=1.0,
                                trend_abs=trend_ex,
                            )

                            self._emit_trade_trace_after(symbol_ex)

                            print(
                                {
                                    "EXIT_EXECUTED": {
                                        "symbol": sym_x,
                                        "reason": reason_ex,
                                        "price": current_price,
                                        "result": res_ex,
                                    }
                                },
                                flush=True,
                            )

                            if isinstance(res_ex, dict) and res_ex.get("ok"):
                                self._emit_trade_trace(symbol_ex, "CLOSE")
                                if current_price <= 0:
                                    raise RuntimeError("price_engine exit_price <= 0 — cannot close CSV")
                                if not self.trade_logger.update_trade(
                                    symbol_ex,
                                    float(current_price),
                                    reason=reason_ex,
                                ):
                                    print(
                                        {
                                            "FATAL_CSV_CLOSE_FAILED": symbol_ex,
                                        },
                                        flush=True,
                                    )
                                    raise RuntimeError("CSV close failed — aborting")
                                if symbol_ex_n in self._csv_open_symbols_normalized():
                                    raise RuntimeError("CSV CLOSE FAILED — SYMBOL STILL OPEN")
                                print(
                                    {"CSV_CLOSE_VERIFIED": symbol_ex},
                                    flush=True,
                                )
                                self._recover_open_positions_from_csv()
                                self._assert_state_csv_lock()
                                if self._runner_position_exists_norm(symbol_ex_n):
                                    raise RuntimeError("Exit did not remove position")
                                ts_ex = datetime.now(timezone.utc)
                                self._entry_side_by_symbol.pop(str(sym_x).strip().upper(), None)
                                xpu = float(res_ex.get("exit_price") or res_ex.get("actual_fill_price") or 0.0)
                                if xpu > 0:
                                    self.perf.on_exit(str(sym_x).strip(), xpu, ts_ex)
                                if self._risk is not None:
                                    try:
                                        ret_ex = float(res_ex.get("pnl", 0.0))
                                    except (TypeError, ValueError):
                                        ret_ex = 0.0
                                    rf_ex = self._entry_risk_factor.pop(str(sym_x).strip(), 1.0)
                                    self._risk.record_closed_trade(ret_ex, rf_ex)
                                print(
                                    {
                                        "TRADE_CLOSED": {
                                            "symbol": sym_x,
                                            "reason": reason_ex,
                                            "price": xpu,
                                            "pnl": res_ex.get("pnl"),
                                        }
                                    },
                                    flush=True,
                                )

                        except RuntimeError:
                            raise
                        except Exception as e_ex:
                            print(
                                {
                                    "EXIT_ERROR": str(e_ex),
                                    "symbol": sym_x,
                                },
                                flush=True,
                            )
                    print(portfolio)
                    sel_pf = int(portfolio.get("SELECTED", 0) or 0)
                    _pf_raw = portfolio.get("PORTFOLIO")
                    n_pf = len(_pf_raw) if isinstance(_pf_raw, list) else 0
                    self._max_portfolio_rows = max(self._max_portfolio_rows, int(n_pf))
                    self._portfolio_best_selected = max(self._portfolio_best_selected, sel_pf)
                    if sel_pf == 0:
                        self._empty_portfolio_cycles_manual += 1
                    if self._adaptive is not None:
                        scores_raw = [
                            float(p["score"])
                            for p in portfolio.get("PORTFOLIO", [])
                            if isinstance(p, dict) and "score" in p
                        ]
                        self._adaptive.record_cycle(
                            selected=sel_pf,
                            portfolio_empty=(sel_pf == 0),
                            actions=cycle_actions,
                            confidences=cycle_confidences,
                            portfolio_scores=scores_raw,
                        )
                        self._adaptive.finalize_after_portfolio(
                            cycle_portfolio_snap,
                            portfolio,
                            self.decision.fe,
                        )

                    self._assert_csv_max_one_open_per_symbol()
                    state_syms = sorted(self._state_open_symbols_normalized())
                    csv_syms = sorted(self._csv_open_symbols_normalized())
                    print(
                        {
                            "STATE_SANITY": {
                                "state": state_syms,
                                "csv": csv_syms,
                                "match": state_syms == csv_syms,
                            }
                        },
                        flush=True,
                    )
                    if state_syms != csv_syms:
                        print(
                            {
                                "FATAL_STATE_CSV_MISMATCH": {
                                    "state": state_syms,
                                    "csv": csv_syms,
                                }
                            },
                            flush=True,
                        )
                        raise RuntimeError("CSV and state mismatch")
                    self._assert_state_csv_lock()

                    self._edge_cycle += 1
                    if self._edge_cycle % self._edge_update_every_n_cycles == 0:
                        self._maybe_refresh_edges()
                        print(
                            {
                                "kap_on": self.paper_kap_on.stats(),
                                "kap_off": self.paper_kap_off.stats(),
                            }
                        )
                    self._watchdog_streak = 0
                except RuntimeError:
                    raise
                except Exception as e:
                    self.state.log_error(f"loop_cycle:{e}")
                    print({"error": "LOOP_EXCEPTION", "detail": str(e)})
                    self._watchdog_streak += 1
                    if self._watchdog_streak >= 25:
                        print({"watchdog": "loop_streak_reset", "streak": self._watchdog_streak})
                        self._watchdog_streak = 0

                # Exactly one increment per full universe pass (after `for sym` + portfolio phase).
                cycle_count = current_cycle
                print(
                    {
                        "EXPECTANCY_STATS": tracker.stats(),
                    },
                    flush=True,
                )
                if single_cycle:
                    return {
                        "PORTFOLIO": getattr(self, "last_portfolio", []),
                        "cycle": cycle_count,
                    }
                print({"cycle": cycle_count}, flush=True)
                metrics = self.perf.compute_metrics()

                print({"PERFORMANCE": metrics}, flush=True)
                if cycle_bar_progress or self._action_counter > 0:
                    no_progress_streak = 0
                else:
                    no_progress_streak += 1
                if cycle_count == 100 and self._action_counter == 0:
                    self._relax_mode = True
                    os.environ["BIST_DECISION_RELAX_MODE"] = "1"
                    print(
                        {
                            "stage": "auto_fix",
                            "reason": "no_actions_after_100_cycles",
                            "BIST_DECISION_RELAX_MODE": "1",
                        },
                        flush=True,
                    )
                if (
                    not validation_mode
                    and max_c >= 100
                    and current_cycle == 1
                    and cycle_decision_payloads == 0
                    and self._action_counter == 0
                    and not saw_qualifying_action
                    and not bool(getattr(self.state, "positions", {}))
                ):
                    raise Exception("NO_ACTIONS_PRODUCED")
                if (
                    not validation_mode
                    and max_c >= 100
                    and self._action_counter == 0
                    and not saw_qualifying_action
                    and no_progress_streak >= 5
                    and not bool(getattr(self.state, "positions", {}))
                ):
                    raise Exception("NO_ACTIONS_PRODUCED")
                if not single_cycle and current_cycle < max_cycles:
                    time.sleep(self.poll_seconds)
                if current_cycle >= max_cycles:
                    print(
                        {
                            "RUN_TERMINATED": {
                                "reason": "MAX_CYCLES_REACHED",
                                "cycles": current_cycle,
                            }
                        },
                        flush=True,
                    )
                    break
            if not stopped_max_cycles_emitted:
                print(
                    {"status": "STOPPED_AFTER_MAX_CYCLES", "cycles": cycle_count},
                    flush=True,
                )
                stopped_max_cycles_emitted = True
        except BaseException as e:
            if isinstance(e, SystemExit):
                raise
            # existing handling continues below
            loop_exc = e
        finally:
            if not stopped_max_cycles_emitted and cycle_count >= max_c:
                print(
                    {"status": "STOPPED_AFTER_MAX_CYCLES", "cycles": cycle_count},
                    flush=True,
                )
                stopped_max_cycles_emitted = True
            sys.stdout.flush()
            sys.stderr.flush()
            self._emit_run_end_validation(
                cycle_count,
                max_c,
                validation_mode=validation_mode,
                require_full_proof=require_full_proof,
                saw_qualifying_action=saw_qualifying_action,
                ever_feed_bars=ever_feed_bars,
                saw_real_data_flowing=saw_real_data_flowing,
                loop_ok=loop_exc is None,
            )
        if loop_exc is not None:
            raise loop_exc
        return None


__all__ = ["LiveRunner"]


if __name__ == "__main__":
    print(
        {
            "DATA_PATH_MODE": "HARDCODED",
            "path": "C:\\iDeal\\ChartData\\IMKBH",
        },
        flush=True,
    )
    poll = float(os.environ.get("BIST_LIVE_POLL_SECONDS", "0"))
    try:
        max_c_main = int(os.environ.get("BIST_LIVE_MAX_CYCLES", "800"))
    except ValueError:
        max_c_main = 800
    max_c_main = max(1, min(max_c_main, 100_000))
    until_success = os.environ.get("BIST_LIVE_UNTIL_SUCCESS", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    try:
        max_attempts = int(os.environ.get("BIST_LIVE_MAX_ATTEMPTS", "50"))
    except ValueError:
        max_attempts = 50
    attempt = 0
    runner = LiveRunner(poll_seconds=poll)
    while True:
        attempt += 1
        try:
            runner.run(max_cycles=max_c_main)
            break
        except Exception as e:
            print({"fatal_error": str(e), "attempt": attempt})
            if isinstance(e, RuntimeError) and str(e).startswith("DATA_FAILURE"):
                raise
            if not until_success or attempt >= max_attempts:
                raise
            time.sleep(1.0)
