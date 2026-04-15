"""Tests for No-Trade Guard — all blocking paths and allow path (PRD §1.21)."""

from __future__ import annotations

import pytest

from crypto_core.guard.models import (
    BlockSeverity,
    NoTradeContext,
    NoTradeDecision,
    NoTradeReason,
)
from crypto_core.guard.no_trade_guard import NoTradeConfig, NoTradeGuard
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000  # base timestamp in ns (arbitrary)
_NS_PER_MS = 1_000_000
_NS_PER_S = 1_000_000_000


def _good_ctx(**overrides: object) -> NoTradeContext:
    """Returns a fully healthy context — all checks should pass."""
    defaults: dict[str, object] = {
        "symbol": "BTCUSDT",
        "exchange": "binance",
        "current_ns": _T0_NS,
        "book_last_update_ns": _T0_NS - 100 * _NS_PER_MS,  # 100ms ago
        "book_has_snapshot": True,
        "book_bid_count": 5,
        "book_ask_count": 5,
        "feed_connection_state": "connected",
        "feed_recovery_state": "ready",
        "supported_symbols": frozenset({"BTCUSDT", "ETHUSDT"}),
        "system_state": SystemState.NORMAL,
        "latency_ms": 10.0,
        "telemetry_last_emit_ns": _T0_NS - 1 * _NS_PER_S,  # 1 second ago
    }
    defaults.update(overrides)
    return NoTradeContext(**defaults)  # type: ignore[arg-type]


def _guard(**cfg_overrides: object) -> NoTradeGuard:
    return NoTradeGuard(NoTradeConfig(**cfg_overrides))  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Allow path
# ---------------------------------------------------------------------------


class TestAllowPath:
    def test_healthy_context_allows_trading(self) -> None:
        guard = _guard()
        decision = guard.evaluate(_good_ctx())
        assert decision.allowed is True
        assert decision.reason is None
        assert decision.severity is None

    def test_allow_evidence_populated(self) -> None:
        guard = _guard()
        decision = guard.evaluate(_good_ctx())
        assert "symbol" in decision.evidence

    def test_deterministic_repeated_calls(self) -> None:
        guard = _guard()
        ctx = _good_ctx()
        d1 = guard.evaluate(ctx)
        d2 = guard.evaluate(ctx)
        assert d1.allowed == d2.allowed


# ---------------------------------------------------------------------------
# NT-D01: Stale data
# ---------------------------------------------------------------------------


class TestStaleData:
    def test_stale_data_blocks(self) -> None:
        guard = _guard(stale_data_threshold_ms=5_000)
        # book updated 10 seconds ago
        ctx = _good_ctx(book_last_update_ns=_T0_NS - 10 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STALE_DATA
        assert d.severity == BlockSeverity.SOFT
        assert "age_ms" in d.evidence

    def test_fresh_data_passes(self) -> None:
        guard = _guard(stale_data_threshold_ms=5_000)
        ctx = _good_ctx(book_last_update_ns=_T0_NS - 100 * _NS_PER_MS)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_never_updated_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_last_update_ns=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.STALE_DATA


# ---------------------------------------------------------------------------
# NT-D02: Invalid book
# ---------------------------------------------------------------------------


class TestInvalidBook:
    def test_zero_bids_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_bid_count=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.INVALID_BOOK
        assert d.severity == BlockSeverity.HARD

    def test_zero_asks_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_ask_count=0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.INVALID_BOOK

    def test_sufficient_levels_passes(self) -> None:
        guard = _guard(min_book_bid_levels=1, min_book_ask_levels=1)
        ctx = _good_ctx(book_bid_count=1, book_ask_count=1)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D03: Missing snapshot
# ---------------------------------------------------------------------------


class TestMissingSnapshot:
    def test_no_snapshot_blocks(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_has_snapshot=False)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.MISSING_SNAPSHOT
        assert d.severity == BlockSeverity.HARD

    def test_snapshot_present_passes(self) -> None:
        guard = _guard()
        ctx = _good_ctx(book_has_snapshot=True)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D04: Unsupported symbol
# ---------------------------------------------------------------------------


class TestUnsupportedSymbol:
    def test_unsupported_symbol_blocks(self) -> None:
        guard = _guard(supported_symbols=frozenset({"ETHUSDT"}))
        ctx = _good_ctx(symbol="BTCUSDT", supported_symbols=frozenset())
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.UNSUPPORTED_SYMBOL
        assert d.severity == BlockSeverity.HARD

    def test_supported_symbol_passes(self) -> None:
        guard = _guard(supported_symbols=frozenset({"BTCUSDT"}))
        ctx = _good_ctx(symbol="BTCUSDT")
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_empty_supported_set_skips_check(self) -> None:
        guard = _guard(supported_symbols=frozenset())
        ctx = _good_ctx(symbol="XYZUSDT", supported_symbols=frozenset())
        d = guard.evaluate(ctx)
        # No supported_symbols configured → skip check
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-D05: Recovery active
# ---------------------------------------------------------------------------


class TestRecoveryActive:
    @pytest.mark.parametrize(
        "recovery_state",
        ["snapshotting", "replaying", "validating"],
    )
    def test_recovery_states_block(self, recovery_state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_recovery_state=recovery_state)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.RECOVERY_ACTIVE
        assert d.severity == BlockSeverity.SOFT

    @pytest.mark.parametrize(
        "conn_state",
        ["reconnecting", "failed", "disconnected", "connecting"],
    )
    def test_unhealthy_connection_states_block(self, conn_state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_connection_state=conn_state, feed_recovery_state="idle")
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.RECOVERY_ACTIVE

    def test_ready_state_passes(self) -> None:
        guard = _guard()
        ctx = _good_ctx(feed_recovery_state="ready", feed_connection_state="connected")
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-X01: System state defensive
# ---------------------------------------------------------------------------


class TestSystemStateBlock:
    @pytest.mark.parametrize(
        "state",
        [SystemState.DEFENSIVE, SystemState.CRISIS, SystemState.HALT],
    )
    def test_defensive_and_above_blocks(self, state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(system_state=state)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.SYSTEM_STATE_DEFENSIVE
        assert d.severity == BlockSeverity.CRITICAL

    @pytest.mark.parametrize(
        "state",
        [SystemState.NORMAL, SystemState.DEGRADED],
    )
    def test_normal_and_degraded_passes(self, state: str) -> None:
        guard = _guard()
        ctx = _good_ctx(system_state=state)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_custom_block_threshold(self) -> None:
        guard = _guard(block_at_state=SystemState.DEGRADED)
        ctx = _good_ctx(system_state=SystemState.DEGRADED)
        d = guard.evaluate(ctx)
        assert d.allowed is False


# ---------------------------------------------------------------------------
# NT-X02: Latency budget breach
# ---------------------------------------------------------------------------


class TestLatencyBudget:
    def test_latency_over_budget_blocks(self) -> None:
        guard = _guard(latency_budget_ms=100.0)
        ctx = _good_ctx(latency_ms=200.0)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.LATENCY_BUDGET_BREACH
        assert d.severity == BlockSeverity.SOFT
        assert d.evidence["latency_ms"] == 200.0

    def test_latency_within_budget_passes(self) -> None:
        guard = _guard(latency_budget_ms=500.0)
        ctx = _good_ctx(latency_ms=50.0)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NT-X03: Telemetry unavailable
# ---------------------------------------------------------------------------


class TestTelemetryUnavailable:
    def test_stale_telemetry_blocks(self) -> None:
        guard = _guard(telemetry_window_ms=60_000)
        # Telemetry last emitted 5 minutes ago
        ctx = _good_ctx(telemetry_last_emit_ns=_T0_NS - 5 * 60 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is False
        assert d.reason == NoTradeReason.TELEMETRY_UNAVAILABLE
        assert d.severity == BlockSeverity.HARD

    def test_fresh_telemetry_passes(self) -> None:
        guard = _guard(telemetry_window_ms=60_000)
        ctx = _good_ctx(telemetry_last_emit_ns=_T0_NS - 1 * _NS_PER_S)
        d = guard.evaluate(ctx)
        assert d.allowed is True

    def test_never_emitted_telemetry_allows_default(self) -> None:
        guard = _guard()
        # telemetry_last_emit_ns=0 → first-start, permissive
        ctx = _good_ctx(telemetry_last_emit_ns=0)
        d = guard.evaluate(ctx)
        assert d.allowed is True


# ---------------------------------------------------------------------------
# NoTradeDecision factory methods
# ---------------------------------------------------------------------------


class TestNoTradeDecisionFactories:
    def test_allow_factory(self) -> None:
        d = NoTradeDecision.allow({"key": "val"})
        assert d.allowed is True
        assert d.reason is None
        assert d.severity is None
        assert d.evidence == {"key": "val"}

    def test_block_factory_sets_severity(self) -> None:
        d = NoTradeDecision.block(NoTradeReason.STALE_DATA, {"age_ms": 9999})
        assert d.allowed is False
        assert d.severity == BlockSeverity.SOFT

    def test_block_is_frozen(self) -> None:
        d = NoTradeDecision.allow()
        with pytest.raises((AttributeError, TypeError)):
            d.allowed = False  # type: ignore[misc]
