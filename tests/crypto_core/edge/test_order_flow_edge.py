"""Tests for Order Flow Imbalance edge family (PRD §1.3 Family A)."""

from __future__ import annotations

import pytest

from crypto_core.data.models.events import Exchange, TradeEvent, TradeSide
from crypto_core.edge.engine import EdgeEngine
from crypto_core.edge.families.order_flow import (
    OFIConfig,
    OrderFlowImbalanceEdge,
    compute_ofi,
)
from crypto_core.edge.models import EdgeFamily, EdgeSignal, SignalDirection
from crypto_core.guard.models import NoTradeDecision, NoTradeReason
from crypto_core.state.models import SystemState

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000


def _trade(side: TradeSide, qty: float = 1.0, price: float = 50_000.0) -> TradeEvent:
    return TradeEvent(
        trade_id=f"{side}{qty}",
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        side=side,
        price=price,
        qty=qty,
        timestamp_ns=_T0_NS,
        sequence_no=1,
        is_maker=False,
    )


def _buys(n: int, qty: float = 1.0) -> list[TradeEvent]:
    return [_trade(TradeSide.BUY, qty) for _ in range(n)]


def _sells(n: int, qty: float = 1.0) -> list[TradeEvent]:
    return [_trade(TradeSide.SELL, qty) for _ in range(n)]


def _allow() -> NoTradeDecision:
    return NoTradeDecision.allow()


def _block() -> NoTradeDecision:
    return NoTradeDecision.block(NoTradeReason.STALE_DATA, {"reason": "test"})


# ---------------------------------------------------------------------------
# compute_ofi (pure function tests)
# ---------------------------------------------------------------------------


class TestComputeOfi:
    def test_all_buys_gives_positive_one(self) -> None:
        ofi, ev = compute_ofi(_buys(10))
        assert abs(ofi - 1.0) < 1e-9

    def test_all_sells_gives_negative_one(self) -> None:
        ofi, ev = compute_ofi(_sells(10))
        assert abs(ofi - (-1.0)) < 1e-9

    def test_equal_buys_and_sells_gives_zero(self) -> None:
        trades = _buys(5) + _sells(5)
        ofi, _ = compute_ofi(trades)
        assert abs(ofi) < 1e-9

    def test_partial_imbalance(self) -> None:
        # 70 buy vol, 30 sell vol → OFI = (70-30)/100 = 0.40
        trades = _buys(7, qty=10.0) + _sells(3, qty=10.0)
        ofi, ev = compute_ofi(trades)
        assert abs(ofi - 0.40) < 1e-9
        assert ev["buy_vol"] == 70.0
        assert ev["sell_vol"] == 30.0

    def test_empty_trades_returns_zero_with_error(self) -> None:
        ofi, ev = compute_ofi([])
        assert ofi == 0.0
        assert "error" in ev

    def test_zero_volume_returns_zero_with_error(self) -> None:
        # qty=0 trades
        trades = [_trade(TradeSide.BUY, qty=0.0) for _ in range(5)]
        ofi, ev = compute_ofi(trades)
        assert ofi == 0.0
        assert "error" in ev

    def test_window_clips_old_trades(self) -> None:
        # 100 old sells + 20 recent buys → window=20 sees only buys
        old = _sells(100)
        recent = _buys(20)
        trades = old + recent
        ofi, ev = compute_ofi(trades, window=20)
        assert abs(ofi - 1.0) < 1e-9
        assert ev["trade_count"] == 20

    def test_deterministic(self) -> None:
        trades = _buys(5) + _sells(3)
        ofi1, _ = compute_ofi(trades)
        ofi2, _ = compute_ofi(trades)
        assert ofi1 == ofi2


# ---------------------------------------------------------------------------
# OrderFlowImbalanceEdge.evaluate()
# ---------------------------------------------------------------------------


class TestOFIEdgeEvaluate:
    def _edge(self, threshold: float = 0.10, min_count: int = 5) -> OrderFlowImbalanceEdge:
        return OrderFlowImbalanceEdge(OFIConfig(window=50, threshold=threshold, min_trade_count=min_count))

    def test_strong_buy_signal(self) -> None:
        edge = self._edge(threshold=0.10)
        trades = _buys(40) + _sells(10)  # OFI = 0.60 → BUY
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.BUY
        assert sig.confidence > 0.10
        assert sig.family == EdgeFamily.ORDER_FLOW_IMBALANCE

    def test_strong_sell_signal(self) -> None:
        edge = self._edge(threshold=0.10)
        trades = _sells(40) + _buys(10)  # OFI = -0.60 → SELL
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.SELL

    def test_neutral_signal_below_threshold(self) -> None:
        edge = self._edge(threshold=0.20)
        trades = _buys(11) + _sells(9)  # OFI ≈ 0.10 < 0.20 → NEUTRAL
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_empty_trades_invalid(self) -> None:
        edge = self._edge()
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "no_trades" in (sig.block_reason or "")

    def test_insufficient_trades_invalid(self) -> None:
        edge = self._edge(min_count=10)
        trades = _buys(3)  # only 3 trades, need 10
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_confidence_equals_abs_ofi(self) -> None:
        edge = self._edge(threshold=0.10)
        trades = _buys(7) + _sells(3)  # OFI = 0.40
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert abs(sig.confidence - 0.40) < 1e-9

    def test_deterministic_repeated_evaluation(self) -> None:
        edge = self._edge()
        trades = _buys(30) + _sells(20)
        s1 = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        s2 = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert s1.direction == s2.direction
        assert s1.confidence == s2.confidence
        assert s1.score == s2.score

    def test_invalid_signal_is_frozen(self) -> None:
        edge = self._edge()
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS)
        assert isinstance(sig, EdgeSignal)
        with pytest.raises((AttributeError, TypeError)):
            sig.is_valid = True  # type: ignore[misc]


# ---------------------------------------------------------------------------
# EdgeEngine integration
# ---------------------------------------------------------------------------


class TestEdgeEngine:
    def test_no_trade_block_returns_invalid_signals(self) -> None:
        engine = EdgeEngine()
        trades = _buys(30) + _sells(10)
        signals = engine.evaluate(
            trades, "BTCUSDT", "binance", _block(), SystemState.NORMAL, _T0_NS
        )
        assert len(signals) == 1
        assert signals[0].is_valid is False
        assert "no_trade_blocked" in (signals[0].block_reason or "")

    def test_defensive_state_blocks_all(self) -> None:
        engine = EdgeEngine()
        trades = _buys(30) + _sells(10)
        signals = engine.evaluate(
            trades, "BTCUSDT", "binance", _allow(), SystemState.DEFENSIVE, _T0_NS
        )
        assert all(not s.is_valid for s in signals)
        assert all("system_state_blocked" in (s.block_reason or "") for s in signals)

    def test_healthy_state_produces_valid_signal(self) -> None:
        engine = EdgeEngine()
        trades = _buys(40) + _sells(10)
        signals = engine.evaluate(
            trades, "BTCUSDT", "binance", _allow(), SystemState.NORMAL, _T0_NS
        )
        assert len(signals) == 1
        assert signals[0].is_valid is True

    def test_halt_state_blocks_all(self) -> None:
        engine = EdgeEngine()
        trades = _buys(30) + _sells(10)
        signals = engine.evaluate(
            trades, "BTCUSDT", "binance", _allow(), SystemState.HALT, _T0_NS
        )
        assert all(not s.is_valid for s in signals)

    def test_degraded_state_allows_trading(self) -> None:
        """DEGRADED < DEFENSIVE — edge evaluation should proceed."""
        engine = EdgeEngine()
        trades = _buys(40) + _sells(10)
        signals = engine.evaluate(
            trades, "BTCUSDT", "binance", _allow(), SystemState.DEGRADED, _T0_NS
        )
        assert len(signals) == 1
        assert signals[0].is_valid is True
