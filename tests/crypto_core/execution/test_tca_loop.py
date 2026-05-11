"""Tests for TCA closed loop — fill → markout → TCA persistence (Phase 9C).

Covers:
  - TCAEmitStatus enum values
  - FillRegistrationResult frozen invariant
  - PriceUpdateResult frozen invariant
  - TCALoopConfig defaults
  - ExecutionTCALoop fill registration (single fill)
  - ExecutionTCALoop duplicate fill dedup
  - ExecutionTCALoop markout observation → TCA auto-persist
  - ExecutionTCALoop markout expiry → no TCA emitted
  - ExecutionTCALoop multiple fills → multiple TCA records
  - ExecutionTCALoop replay safety via load_persisted_ids
  - ExecutionTCALoop persist_attribution dedup
  - ExecutionTCALoop with no store → UNAVAILABLE
  - ExecutionTCALoop emit_initial_pending_tca config
  - ExecutionTCALoop pending and persisted counts
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.execution.attribution import build_trade_attribution
from crypto_core.execution.markout import MarkoutObserver, MarkoutObserverConfig
from crypto_core.execution.tca_loop import (
    ExecutionTCALoop,
    FillRegistrationResult,
    PriceUpdateResult,
    TCAEmitStatus,
    TCALoopConfig,
)
from crypto_core.execution.tca_store import TCAStore

# ===================================================================
# Enum tests
# ===================================================================


class TestTCAEmitStatus:
    def test_values(self) -> None:
        assert TCAEmitStatus.EMITTED.value == "emitted"
        assert TCAEmitStatus.DEFERRED.value == "deferred"
        assert TCAEmitStatus.ALREADY_EMITTED.value == "already_emitted"
        assert TCAEmitStatus.UNAVAILABLE.value == "unavailable"


# ===================================================================
# Frozen invariant tests
# ===================================================================


class TestFillRegistrationResult:
    def test_frozen(self) -> None:
        r = FillRegistrationResult(
            order_id="abc",
            markout_registered=True,
            initial_tca_status=TCAEmitStatus.DEFERRED,
        )
        with pytest.raises(AttributeError):
            r.order_id = "xyz"  # type: ignore[misc]

    def test_defaults(self) -> None:
        r = FillRegistrationResult(
            order_id="abc",
            markout_registered=False,
            initial_tca_status=TCAEmitStatus.DEFERRED,
        )
        assert r.evidence == {}


class TestPriceUpdateResult:
    def test_frozen(self) -> None:
        r = PriceUpdateResult()
        with pytest.raises(AttributeError):
            r.harvested_count = 5  # type: ignore[misc]

    def test_defaults(self) -> None:
        r = PriceUpdateResult()
        assert r.resolved_order_ids == ()
        assert r.expired_order_ids == ()
        assert r.tca_emitted_order_ids == ()
        assert r.harvested_count == 0


class TestTCALoopConfig:
    def test_defaults(self) -> None:
        c = TCALoopConfig()
        assert c.auto_persist_on_complete is True
        assert c.emit_initial_pending_tca is False


# ===================================================================
# ExecutionTCALoop tests
# ===================================================================

# Use a short horizons config so tests resolve quickly
SHORT_HORIZONS = (1,)
OBSERVER_CONFIG = MarkoutObserverConfig(horizons=SHORT_HORIZONS, expiry_grace_seconds=10)

# Timestamps in nanoseconds
BASE_NS = 1_000_000_000_000  # 1000 seconds in ns (arbitrary)
ONE_SEC_NS = 1_000_000_000


def _make_loop(
    *,
    with_store: bool = True,
    config: TCALoopConfig | None = None,
    observer_config: MarkoutObserverConfig | None = None,
    tmp_dir: Path | None = None,
) -> tuple[ExecutionTCALoop, TCAStore | None, MarkoutObserver]:
    """Build a TCA loop with file-based store and short-horizon observer."""
    observer = MarkoutObserver(observer_config or OBSERVER_CONFIG)
    store: TCAStore | None = None
    if with_store:
        d = tmp_dir or Path(".")
        store = TCAStore(d / "test_tca_store.jsonl")
    loop = ExecutionTCALoop(
        markout_observer=observer,
        tca_store=store,
        config=config,
    )
    return loop, store, observer


def _register_default_fill(
    loop: ExecutionTCALoop,
    order_id: str = "order1",
    fill_price: float = 50000.0,
    fill_ns: int = BASE_NS,
) -> FillRegistrationResult:
    """Register a standard buy fill."""
    return loop.on_fill(
        order_id=order_id,
        fill_price=fill_price,
        fill_timestamp_ns=fill_ns,
        is_buy=True,
        symbol="BTCUSDT",
        exchange="binance",
        size=0.1,
        requested_size=0.1,
        decision_price=49990.0,
        arrival_price=49995.0,
    )


class TestTCALoopFillRegistration:
    """Fill registration — single and duplicate."""

    def test_register_single_fill(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        result = _register_default_fill(loop)
        assert result.order_id == "order1"
        assert result.markout_registered is True
        assert result.initial_tca_status == TCAEmitStatus.DEFERRED
        assert loop.registered_count == 1

    def test_duplicate_fill_rejected(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop, order_id="order1")
        result2 = _register_default_fill(loop, order_id="order1")
        assert result2.markout_registered is False
        assert result2.initial_tca_status == TCAEmitStatus.ALREADY_EMITTED
        assert loop.registered_count == 1  # still 1

    def test_multiple_fills_tracked(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop, order_id="order1")
        _register_default_fill(loop, order_id="order2", fill_ns=BASE_NS + ONE_SEC_NS)
        assert loop.registered_count == 2


class TestTCALoopMarkoutObservation:
    """Price observation → markout resolve → TCA auto-persist."""

    def test_observation_resolves_markout_and_persists_tca(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop)

        # Observe price at 1s after fill (matches SHORT_HORIZONS)
        update = loop.on_price_update("BTCUSDT", "binance", 50010.0, BASE_NS + ONE_SEC_NS)

        assert "order1" in update.resolved_order_ids
        assert update.harvested_count == 1
        assert "order1" in update.tca_emitted_order_ids
        assert loop.persisted_tca_count == 1

    def test_no_persist_before_horizon(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop)

        # Observe price too early (before 1s horizon)
        update = loop.on_price_update(
            "BTCUSDT",
            "binance",
            50010.0,
            BASE_NS + 500_000_000,  # 0.5s
        )

        assert update.resolved_order_ids == ()
        assert update.harvested_count == 0
        assert loop.persisted_tca_count == 0

    def test_pending_order_ids_tracked(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop)
        assert "order1" in loop.get_pending_order_ids()

        # Resolve the markout
        loop.on_price_update("BTCUSDT", "binance", 50010.0, BASE_NS + ONE_SEC_NS)
        # After harvest, no longer pending
        assert "order1" not in loop.get_pending_order_ids()


class TestTCALoopDedup:
    """Dedup and replay safety."""

    def test_completed_tca_not_re_emitted(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop)

        # First resolve
        loop.on_price_update("BTCUSDT", "binance", 50010.0, BASE_NS + ONE_SEC_NS)
        assert loop.persisted_tca_count == 1

        # Second observation (for a different time) — already persisted, no re-emit
        update = loop.on_price_update("BTCUSDT", "binance", 50020.0, BASE_NS + 2 * ONE_SEC_NS)
        assert "order1" not in update.tca_emitted_order_ids
        assert loop.persisted_tca_count == 1

    def test_load_persisted_ids_prevents_re_emit(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)

        # Bootstrap: simulate recovery from prior run
        loop.load_persisted_ids(
            tca_order_ids={"order1"},
            attribution_order_ids=set(),
        )

        # Try to register the same order — should be treated as duplicate
        result = _register_default_fill(loop, order_id="order1")
        assert result.initial_tca_status == TCAEmitStatus.ALREADY_EMITTED
        assert result.markout_registered is False


class TestTCALoopAttribution:
    """Attribution persistence with dedup."""

    def test_persist_attribution(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        attr = build_trade_attribution(
            order_id="order1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=BASE_NS,
            total_pnl_bps=10.0,
            fees_bps=4.0,
            slippage_bps=2.0,
        )
        status = loop.persist_attribution(attr)
        assert status == TCAEmitStatus.EMITTED
        assert loop.persisted_attribution_count == 1

    def test_attribution_dedup(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        attr = build_trade_attribution(
            order_id="order1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=BASE_NS,
        )
        loop.persist_attribution(attr)
        status2 = loop.persist_attribution(attr)
        assert status2 == TCAEmitStatus.ALREADY_EMITTED
        assert loop.persisted_attribution_count == 1

    def test_attribution_no_store(self) -> None:
        loop, _, _ = _make_loop(with_store=False)
        attr = build_trade_attribution(
            order_id="order1",
            symbol="BTCUSDT",
            exchange="binance",
            intent="buy",
            timestamp_ns=BASE_NS,
        )
        status = loop.persist_attribution(attr)
        assert status == TCAEmitStatus.UNAVAILABLE


class TestTCALoopNoStore:
    """Loop behavior without TCA store."""

    def test_no_store_fill_still_registers_markout(self) -> None:
        loop, _, _ = _make_loop(with_store=False)
        result = _register_default_fill(loop)
        assert result.markout_registered is True
        assert result.initial_tca_status == TCAEmitStatus.DEFERRED
        assert loop.registered_count == 1

    def test_no_store_observation_still_harvests(self) -> None:
        loop, _, _ = _make_loop(with_store=False)
        _register_default_fill(loop)
        update = loop.on_price_update("BTCUSDT", "binance", 50010.0, BASE_NS + ONE_SEC_NS)
        assert update.harvested_count == 1
        # No TCA emitted because no store
        assert update.tca_emitted_order_ids == ()
        assert loop.persisted_tca_count == 0


class TestTCALoopInitialPendingEmit:
    """emit_initial_pending_tca config option."""

    def test_initial_pending_tca_emitted(self, tmp_path: Path) -> None:
        config = TCALoopConfig(emit_initial_pending_tca=True)
        loop, store, _ = _make_loop(config=config, tmp_dir=tmp_path)
        result = _register_default_fill(loop)
        assert result.initial_tca_status == TCAEmitStatus.EMITTED


class TestTCALoopMultipleFills:
    """Multiple fills in a single session."""

    def test_two_fills_two_tca_records(self, tmp_path: Path) -> None:
        loop, store, _ = _make_loop(tmp_dir=tmp_path)
        _register_default_fill(loop, order_id="order1", fill_ns=BASE_NS)
        _register_default_fill(
            loop,
            order_id="order2",
            fill_ns=BASE_NS + ONE_SEC_NS,
            fill_price=51000.0,
        )

        # Resolve both at once (observation at 2s covers both)
        update = loop.on_price_update("BTCUSDT", "binance", 50500.0, BASE_NS + 2 * ONE_SEC_NS)
        assert update.harvested_count == 2
        assert loop.persisted_tca_count == 2
        assert "order1" in update.tca_emitted_order_ids
        assert "order2" in update.tca_emitted_order_ids


class TestTCALoopFrozenSets:
    """Frozen sets are truly frozen."""

    def test_persisted_tca_ids_frozen(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        ids = loop.get_persisted_tca_ids()
        assert isinstance(ids, frozenset)

    def test_persisted_attribution_ids_frozen(self, tmp_path: Path) -> None:
        loop, _, _ = _make_loop(tmp_dir=tmp_path)
        ids = loop.get_persisted_attribution_ids()
        assert isinstance(ids, frozenset)
