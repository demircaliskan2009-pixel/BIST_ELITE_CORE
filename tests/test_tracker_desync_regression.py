"""Tracker desync regression test.

Verifies that PortfolioDecisionEngine._tracker stays in sync
with actual open/closed trades throughout a backtest run.

This test catches the bug where out-of-order trade closures
cause notify_trade_closed() to be skipped, permanently blocking
tracker slots (desync > 0 → all new entries blocked after
_MAX_POSITIONS is hit).
"""

from __future__ import annotations

import csv
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bist_core.backtest.backtest_engine import BacktestEngine, CostModel
from bist_core.decision.portfolio_decision import PortfolioDecisionEngine
from bist_core.execution.order_state_machine import RiskLimits
from bist_core.execution.paper_engine import SlippageModel
from bist_core.models.ohlcv import OHLCVBar

ROOT = Path(__file__).resolve().parents[1]
VENDOR_CSV = ROOT / "data" / "vendor" / "datastore_normalized.csv"
EVENTS_DIR = ROOT / "data" / "events"
SYMS = [
    "SASA", "ISCTR", "CANTE", "TSPOR", "GSRAY",
    "PEKGY", "YKBNK", "EKGYO", "PSGYO", "ADESE",
    "EREGL", "HEKTS", "KATMR", "AKBNK", "PETKM",
]
EQUITY = 100_000.0


def _ts(s: str) -> int:
    return int(datetime.strptime(s, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())


def _load_bars() -> list[OHLCVBar]:
    if not VENDOR_CSV.exists():
        pytest.skip("Vendor data not available")
    bars: list[OHLCVBar] = []
    with open(VENDOR_CSV, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            s = r["symbol"].upper().strip()
            if s not in SYMS:
                continue
            try:
                b = OHLCVBar(
                    timestamp=_ts(r["date"]),
                    symbol=s,
                    open=float(r["open"]),
                    high=float(r["high"]),
                    low=float(r["low"]),
                    close=float(r["close"]),
                    volume=float(r["volume"]),
                )
            except Exception:
                continue
            if b.open <= 0 or b.high <= 0 or b.low <= 0 or b.close <= 0:
                continue
            bars.append(b)
    bars.sort(key=lambda b: (b.timestamp, b.symbol))
    return bars


def _build_event_index() -> dict[tuple[str, str], list[str]]:
    if not EVENTS_DIR.exists():
        return {}
    idx: dict[tuple[str, str], list[str]] = {}
    for fn in sorted(os.listdir(EVENTS_DIR)):
        if not fn.endswith(".jsonl"):
            continue
        with open(EVENTS_DIR / fn, "r", encoding="utf-8") as f:
            for ln in f:
                ln = ln.strip()
                if not ln:
                    continue
                ev = json.loads(ln)
                ts = ev.get("ts", "")
                ds = ts[:10] if ts else fn.replace(".jsonl", "")
                sym = ev.get("symbol", "")
                kind = ev.get("kind", "unknown")
                k = (ds, sym)
                if k not in idx:
                    idx[k] = []
                idx[k].append(kind)
    return idx


def _run_backtest(event_filter: bool) -> tuple[dict, PortfolioDecisionEngine]:
    bars = _load_bars()
    cost = CostModel(
        slippage=SlippageModel(base_slippage_bps=5.0),
        commission_bps=10.0,
        exchange_fee_bps=5.0,
    )
    engine_d = PortfolioDecisionEngine(equity=EQUITY, event_filter_enabled=event_filter)
    if event_filter:
        idx = _build_event_index()
        engine_d.load_event_index(idx)
    eng = BacktestEngine(
        cost_model=cost,
        risk_limits=RiskLimits(),
        initial_equity=EQUITY,
        decision_fn=engine_d,
        decision_engine=None,
    )
    result = eng.run(bars)
    return result, engine_d


class TestTrackerDesyncRegression:
    """Ensure tracker open count == actual open trades (desync == 0)."""

    def test_baseline_tracker_desync_zero(self) -> None:
        """Baseline (no event filter): tracker must be in sync."""
        result, engine = _run_backtest(event_filter=False)
        actual_open = sum(
            1 for t in result["trades"] if t["status"] != "CLOSED"
        )
        tracker_open = engine._tracker.total_open()
        desync = tracker_open - actual_open
        assert desync == 0, (
            f"Tracker desync = {desync} (tracker={tracker_open}, actual={actual_open})"
        )

    def test_filtered_tracker_desync_zero(self) -> None:
        """With event filter: tracker must be in sync."""
        result, engine = _run_backtest(event_filter=True)
        actual_open = sum(
            1 for t in result["trades"] if t["status"] != "CLOSED"
        )
        tracker_open = engine._tracker.total_open()
        desync = tracker_open - actual_open
        assert desync == 0, (
            f"Tracker desync = {desync} (tracker={tracker_open}, actual={actual_open})"
        )

    def test_per_symbol_desync_zero(self) -> None:
        """Per-symbol tracker counts must match actual open trades."""
        result, engine = _run_backtest(event_filter=True)
        open_trades = [t for t in result["trades"] if t["status"] != "CLOSED"]
        actual_by_sym: dict[str, int] = {}
        for t in open_trades:
            s = t["symbol"]
            actual_by_sym[s] = actual_by_sym.get(s, 0) + 1

        for sym in SYMS:
            tracker_count = engine._tracker.symbol_open(sym)
            actual_count = actual_by_sym.get(sym, 0)
            assert tracker_count == actual_count, (
                f"{sym}: tracker={tracker_count}, actual={actual_count}"
            )


class TestEventEntryLogic:
    """Verify event entries generate trades only for allowed kinds."""

    def test_partnership_creates_event_trades(self) -> None:
        """Partnership events must create at least one event-source trade."""
        result, engine = _run_backtest(event_filter=True)
        event_trades = [
            t for t in result["trades"]
            if t["status"] == "CLOSED" and t["edge"].startswith("event_")
        ]
        assert len(event_trades) > 0, "No event trades generated"
        # All event trades must be partnership
        for t in event_trades:
            assert t["edge"] == "event_partnership", (
                f"Unexpected event edge: {t['edge']}"
            )

    def test_earnings_blocks_entry(self) -> None:
        """Earnings events must NOT create event entries."""
        result, _ = _run_backtest(event_filter=True)
        earnings_trades = [
            t for t in result["trades"]
            if t["edge"] == "event_earnings"
        ]
        assert len(earnings_trades) == 0, "Earnings event generated a trade"

    def test_event_multiplier_affects_size(self) -> None:
        """Event size multiplier must be applied to position sizes."""
        _, engine = _run_backtest(event_filter=True)
        boosted = [
            e for e in engine._event_log
            if e["event_multiplier"] != 1.0
        ]
        assert len(boosted) > 0, "No event multiplier was applied"
        for entry in boosted:
            if entry["event_multiplier"] > 1.0:
                # Boosted: final_size >= base_size (capped at max)
                assert entry["final_size"] >= entry["base_size"] or entry["final_size"] == 2000
            elif entry["event_multiplier"] < 1.0:
                # Penalized: final_size <= base_size
                assert entry["final_size"] <= entry["base_size"]

    def test_event_log_populated(self) -> None:
        """Event log must be populated with traceability data."""
        _, engine = _run_backtest(event_filter=True)
        assert len(engine._event_log) > 0, "Event log is empty"
        for entry in engine._event_log:
            assert "symbol" in entry
            assert "timestamp" in entry
            assert "source" in entry
            assert "event_kind" in entry
            assert "event_multiplier" in entry
            assert "base_size" in entry
            assert "final_size" in entry


class TestTradeAuditability:
    """Ensure each trade carries required audit fields."""

    def test_trade_has_source_field(self) -> None:
        """Every trade dict must include source tag."""
        result, _ = _run_backtest(event_filter=True)
        for t in result["trades"]:
            assert "edge" in t, f"Trade missing 'edge': {t.get('symbol')}"

    def test_event_trades_have_event_edge(self) -> None:
        """Event-sourced trades must have edge starting with 'event_'."""
        result, _ = _run_backtest(event_filter=True)
        for t in result["trades"]:
            if t.get("edge", "").startswith("event_"):
                assert t["edge"] in (
                    "event_partnership",
                    "event_buyback",
                    "event_regulatory",
                ), f"Unknown event edge: {t['edge']}"


class TestDeterminism:
    """Same inputs must produce same outputs."""

    def test_backtest_deterministic(self) -> None:
        """Two identical runs must produce identical trade counts and PnL."""
        r1, _ = _run_backtest(event_filter=True)
        r2, _ = _run_backtest(event_filter=True)
        trades1 = [t for t in r1["trades"] if t["status"] == "CLOSED"]
        trades2 = [t for t in r2["trades"] if t["status"] == "CLOSED"]
        assert len(trades1) == len(trades2), (
            f"Non-deterministic trade count: {len(trades1)} vs {len(trades2)}"
        )
        pnl1 = sum(t["pnl"] for t in trades1)
        pnl2 = sum(t["pnl"] for t in trades2)
        assert abs(pnl1 - pnl2) < 0.01, (
            f"Non-deterministic PnL: {pnl1} vs {pnl2}"
        )
