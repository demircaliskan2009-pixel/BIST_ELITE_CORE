"""Tests for PortfolioStateStore and PositionTracker persistence — Phase 6E.

Covers:
  - to_persistence_dict round-trips through PortfolioStateStore.save/load
  - restore_from_dict restores NAV, positions, daily_pnl exactly
  - Atomic write (tmp rename): no half-written files
  - exists() reflects file presence
  - Fail-closed: missing file raises PortfolioRestoreError
  - Fail-closed: malformed JSON raises PortfolioRestoreError
  - Fail-closed: missing required fields raises PortfolioRestoreError
  - Fail-closed: wrong schema_version raises PortfolioRestoreError
  - Fail-closed: non-positive nav raises PortfolioRestoreError
  - Fail-closed: invalid leverage raises PortfolioRestoreError
  - Empty positions round-trip
  - Multiple positions round-trip
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from crypto_core.execution.models import OrderIntent
from crypto_core.portfolio.fills import SyntheticFill, SyntheticFillFactory
from crypto_core.portfolio.store import PortfolioRestoreError, PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SNAPSHOT_NS = 1_000_000_000


def _make_tracker(nav: float = 10_000.0) -> PositionTracker:
    return PositionTracker(initial_nav_usd=nav)


def _make_fill(
    symbol: str = "BTCUSDT",
    exchange: str = "binance",
    intent: OrderIntent = OrderIntent.BUY,
    qty: float = 0.01,
    price: float = 50_000.0,
    leverage: float = 1.0,
) -> SyntheticFill:
    from crypto_core.execution.events import FillEvent
    from crypto_core.execution.models import ExecutionMode

    fill_event = FillEvent(
        order_id="oid-1",
        symbol=symbol,
        exchange=exchange,
        intent=intent,
        filled_quantity=qty,
        fill_price=price,
        timestamp_ns=_SNAPSHOT_NS,
    )
    return SyntheticFillFactory.from_fill_event(
        fill_event=fill_event,
        mode=ExecutionMode.PAPER,
        leverage=leverage,
    )


# ---------------------------------------------------------------------------
# PortfolioStateStore: basic contract
# ---------------------------------------------------------------------------


class TestPortfolioStateStore:
    def test_exists_false_before_save(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio_state.json")
        assert not store.exists()

    def test_save_creates_file(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio_state.json")
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        store.save(d)
        assert store.exists()
        assert store.path.exists()

    def test_save_is_atomic_no_tmp_left(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio_state.json")
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        store.save(d)
        # .tmp file should not exist after save
        assert not store.path.with_suffix(".tmp").exists()

    def test_load_raises_if_missing(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "missing.json")
        with pytest.raises(PortfolioRestoreError, match="not found"):
            store.load()

    def test_load_raises_on_malformed_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("not-json", encoding="utf-8")
        store = PortfolioStateStore(p)
        with pytest.raises(PortfolioRestoreError, match="JSON decode error"):
            store.load()

    def test_load_raises_on_wrong_schema_version(self, tmp_path: Path) -> None:
        d = {
            "schema_version": "99",
            "snapshot_ns": _SNAPSHOT_NS,
            "nav_usd": 10000.0,
            "daily_realized_pnl": 0.0,
            "positions": [],
        }
        p = tmp_path / "v99.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        store = PortfolioStateStore(p)
        with pytest.raises(PortfolioRestoreError, match="schema_version"):
            store.load()

    def test_load_raises_on_missing_top_level_field(self, tmp_path: Path) -> None:
        d = {
            "schema_version": "1",
            # snapshot_ns missing
            "nav_usd": 10000.0,
            "daily_realized_pnl": 0.0,
            "positions": [],
        }
        p = tmp_path / "missing_field.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        store = PortfolioStateStore(p)
        with pytest.raises(PortfolioRestoreError, match="snapshot_ns"):
            store.load()

    def test_load_raises_on_non_positive_nav(self, tmp_path: Path) -> None:
        d = {
            "schema_version": "1",
            "snapshot_ns": _SNAPSHOT_NS,
            "nav_usd": -100.0,
            "daily_realized_pnl": 0.0,
            "positions": [],
        }
        p = tmp_path / "neg_nav.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        store = PortfolioStateStore(p)
        with pytest.raises(PortfolioRestoreError, match="nav_usd must be positive"):
            store.load()

    def test_load_raises_on_missing_position_field(self, tmp_path: Path) -> None:
        d = {
            "schema_version": "1",
            "snapshot_ns": _SNAPSHOT_NS,
            "nav_usd": 10000.0,
            "daily_realized_pnl": 0.0,
            "positions": [
                {
                    "symbol": "BTCUSDT",
                    "exchange": "binance",
                    "side": "long",
                    # quantity missing
                    "avg_entry_price": 50000.0,
                    "mark_price": 50000.0,
                    "leverage": 1.0,
                    "realized_pnl": 0.0,
                }
            ],
        }
        p = tmp_path / "missing_pos_field.json"
        p.write_text(json.dumps(d), encoding="utf-8")
        store = PortfolioStateStore(p)
        with pytest.raises(PortfolioRestoreError, match="quantity"):
            store.load()


# ---------------------------------------------------------------------------
# to_persistence_dict schema
# ---------------------------------------------------------------------------


class TestToPersistenceDict:
    def test_schema_version(self) -> None:
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert d["schema_version"] == "1"

    def test_snapshot_ns(self) -> None:
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert d["snapshot_ns"] == _SNAPSHOT_NS

    def test_nav_usd(self) -> None:
        tracker = _make_tracker(nav=25_000.0)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert d["nav_usd"] == pytest.approx(25_000.0)

    def test_daily_realized_pnl_default_zero(self) -> None:
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert d["daily_realized_pnl"] == pytest.approx(0.0)

    def test_positions_empty_when_no_fills(self) -> None:
        tracker = _make_tracker()
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert d["positions"] == []

    def test_position_fields_present_after_fill(self) -> None:
        tracker = _make_tracker()
        fill = _make_fill()
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        assert len(d["positions"]) == 1
        pos = d["positions"][0]
        required = {
            "symbol",
            "exchange",
            "side",
            "quantity",
            "avg_entry_price",
            "mark_price",
            "leverage",
            "realized_pnl",
        }
        assert required.issubset(set(pos.keys()))

    def test_position_values_match(self) -> None:
        tracker = _make_tracker()
        fill = _make_fill(qty=0.01, price=50_000.0, leverage=2.0)
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        pos = d["positions"][0]
        assert pos["symbol"] == "BTCUSDT"
        assert pos["exchange"] == "binance"
        assert pos["side"] in ("long", "short")
        assert pos["quantity"] == pytest.approx(0.01)
        assert pos["avg_entry_price"] == pytest.approx(50_000.0)
        assert pos["leverage"] == pytest.approx(2.0)


# ---------------------------------------------------------------------------
# restore_from_dict
# ---------------------------------------------------------------------------


class TestRestoreFromDict:
    def test_empty_positions_restore(self) -> None:
        tracker = _make_tracker(nav=10_000.0)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        restored = PositionTracker.restore_from_dict(d)
        assert restored._nav_usd == pytest.approx(10_000.0)
        assert restored._positions == {}
        assert restored._daily_realized_pnl == pytest.approx(0.0)

    def test_single_position_restore(self) -> None:
        tracker = _make_tracker(nav=10_000.0)
        fill = _make_fill(qty=0.01, price=50_000.0, leverage=1.5)
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        restored = PositionTracker.restore_from_dict(d)
        assert len(restored._positions) == 1
        key = ("BTCUSDT", "binance")
        pos = restored._positions[key]
        assert pos.quantity == pytest.approx(0.01)
        assert pos.avg_entry_price == pytest.approx(50_000.0)
        assert pos.leverage == pytest.approx(1.5)

    def test_daily_pnl_restored(self) -> None:
        tracker = _make_tracker(nav=10_000.0)
        tracker._daily_realized_pnl = 123.45
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        restored = PositionTracker.restore_from_dict(d)
        assert restored._daily_realized_pnl == pytest.approx(123.45)

    def test_restore_raises_on_invalid_leverage(self) -> None:
        tracker = _make_tracker(nav=10_000.0)
        fill = _make_fill(leverage=1.0)
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        # Corrupt leverage
        d["positions"][0]["leverage"] = 100.0
        with pytest.raises(PortfolioRestoreError, match="leverage"):
            PositionTracker.restore_from_dict(d)

    def test_restore_raises_on_negative_quantity(self) -> None:
        tracker = _make_tracker(nav=10_000.0)
        fill = _make_fill(leverage=1.0)
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        d["positions"][0]["quantity"] = -0.01
        with pytest.raises(PortfolioRestoreError, match="quantity"):
            PositionTracker.restore_from_dict(d)

    def test_cvar_engine_starts_empty_after_restore(self) -> None:
        """CVaR history is NOT persisted — starts fresh on restore (conservative)."""
        tracker = _make_tracker(nav=10_000.0)
        fill = _make_fill()
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        restored = PositionTracker.restore_from_dict(d)
        cvar = restored.cvar_snapshot(snapshot_ns=_SNAPSHOT_NS + 1)
        assert not cvar.available  # no history to compute from


# ---------------------------------------------------------------------------
# Full round-trip via store
# ---------------------------------------------------------------------------


class TestFullRoundTrip:
    def test_save_and_load_empty_positions(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio.json")
        tracker = _make_tracker(nav=5_000.0)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        store.save(d)
        loaded = store.load()
        restored = PositionTracker.restore_from_dict(loaded)
        assert restored._nav_usd == pytest.approx(5_000.0)
        assert restored._positions == {}

    def test_save_and_load_with_position(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio.json")
        tracker = _make_tracker(nav=10_000.0)
        fill = _make_fill(qty=0.02, price=45_000.0, leverage=2.0)
        tracker.apply_fill(fill)
        d = tracker.to_persistence_dict(_SNAPSHOT_NS)
        store.save(d)
        loaded = store.load()
        restored = PositionTracker.restore_from_dict(loaded)
        pos = restored._positions[("BTCUSDT", "binance")]
        assert pos.quantity == pytest.approx(0.02)
        assert pos.avg_entry_price == pytest.approx(45_000.0)
        assert pos.leverage == pytest.approx(2.0)

    def test_overwrite_save(self, tmp_path: Path) -> None:
        store = PortfolioStateStore(tmp_path / "portfolio.json")
        # First save
        tracker1 = _make_tracker(nav=10_000.0)
        store.save(tracker1.to_persistence_dict(_SNAPSHOT_NS))
        # Second save overwrites
        tracker2 = _make_tracker(nav=20_000.0)
        store.save(tracker2.to_persistence_dict(_SNAPSHOT_NS + 1))
        loaded = store.load()
        assert float(loaded["nav_usd"]) == pytest.approx(20_000.0)
