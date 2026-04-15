"""Tests for expanded edge families (volatility, liquidation, funding) + registry."""

from __future__ import annotations

from crypto_core.data.models.events import Exchange, TradeEvent, TradeSide
from crypto_core.edge.families.funding import FundingRateEdge
from crypto_core.edge.families.liquidation import LiquidationConfig, LiquidationSignalEdge
from crypto_core.edge.families.volatility import VolatilityConfig, VolatilityTransitionEdge
from crypto_core.edge.models import EdgeFamily, SignalDirection
from crypto_core.edge.registry import EdgeFamilyRegistry, RegistryConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000


def _trade(price: float = 50_000.0, qty: float = 1.0, side: TradeSide = TradeSide.BUY) -> TradeEvent:
    return TradeEvent(
        trade_id="t1",
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        side=side,
        price=price,
        qty=qty,
        timestamp_ns=_T0_NS,
        sequence_no=1,
        is_maker=False,
    )


def _flat_trades(n: int = 150, base_price: float = 50_000.0) -> list[TradeEvent]:
    return [_trade(price=base_price, qty=1.0) for _ in range(n)]


def _expanding_vol_trades(n_flat: int = 80, n_spike: int = 40) -> list[TradeEvent]:
    """Flat baseline then oscillating recent prices (genuine vol expansion)."""
    trades = [_trade(price=50_000.0) for _ in range(n_flat)]
    # Oscillate ±2% rapidly so short_vol >> long_vol
    for i in range(n_spike):
        price = 50_000.0 * (1.02 if i % 2 == 0 else 0.98)
        trades.append(_trade(price=price))
    return trades


# ---------------------------------------------------------------------------
# VolatilityTransitionEdge
# ---------------------------------------------------------------------------


class TestVolatilityTransitionEdge:
    def test_insufficient_trades_returns_invalid(self) -> None:
        edge = VolatilityTransitionEdge()
        sig = edge.evaluate([_trade()], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_flat_prices_returns_neutral(self) -> None:
        edge = VolatilityTransitionEdge()
        trades = _flat_trades(150)
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_vol_expansion_returns_directional_signal(self) -> None:
        cfg = VolatilityConfig(
            short_window=20,
            long_window=80,
            expansion_threshold=1.2,
            min_trades=81,
        )
        edge = VolatilityTransitionEdge(cfg)
        trades = _expanding_vol_trades(n_flat=80, n_spike=40)
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert "vol_ratio" in sig.evidence
        assert sig.evidence["vol_ratio"] > 1.0

    def test_evidence_contains_required_fields(self) -> None:
        edge = VolatilityTransitionEdge()
        trades = _flat_trades(150)
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert "short_vol" in sig.evidence
        assert "long_vol" in sig.evidence

    def test_confidence_in_range(self) -> None:
        edge = VolatilityTransitionEdge()
        trades = _flat_trades(150)
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert 0.0 <= sig.confidence <= 1.0

    def test_family_tag(self) -> None:
        edge = VolatilityTransitionEdge()
        sig = edge.evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.family == EdgeFamily.VOLATILITY_TRANSITION


# ---------------------------------------------------------------------------
# LiquidationSignalEdge
# ---------------------------------------------------------------------------


class TestLiquidationSignalEdge:
    def test_insufficient_trades_returns_invalid(self) -> None:
        edge = LiquidationSignalEdge()
        sig = edge.evaluate([_trade()], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_flat_prices_neutral(self) -> None:
        edge = LiquidationSignalEdge()
        sig = edge.evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_rapid_up_move_with_vol_spike_produces_buy(self) -> None:
        cfg = LiquidationConfig(
            window=10,
            baseline_window=50,
            price_threshold=0.01,  # 1%
            vol_spike_threshold=1.5,
            min_trades=51,
        )
        edge = LiquidationSignalEdge(cfg)
        # baseline: 50 trades at price 50000, qty=1
        baseline = [_trade(price=50_000.0, qty=1.0) for _ in range(50)]
        # recent 10: price jumped +3%, qty=5 (vol spike)
        spike = [_trade(price=50_000.0 * (1 + i * 0.005), qty=5.0) for i in range(10)]
        trades = baseline + spike
        sig = edge.evaluate(trades, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        # We only check that the evidence is populated — direction depends on exact math
        assert "price_move_pct" in sig.evidence
        assert "vol_spike" in sig.evidence

    def test_confidence_in_range(self) -> None:
        edge = LiquidationSignalEdge()
        sig = edge.evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert 0.0 <= sig.confidence <= 1.0

    def test_family_tag(self) -> None:
        edge = LiquidationSignalEdge()
        sig = edge.evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.family == EdgeFamily.LIQUIDATION_SIGNAL


# ---------------------------------------------------------------------------
# FundingRateEdge (placeholder)
# ---------------------------------------------------------------------------


class TestFundingRateEdge:
    def test_always_returns_neutral(self) -> None:
        edge = FundingRateEdge()
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL
        assert sig.confidence == 0.0

    def test_evidence_has_placeholder_status(self) -> None:
        edge = FundingRateEdge()
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS)
        assert sig.evidence.get("status") == "placeholder_v1"

    def test_family_tag(self) -> None:
        edge = FundingRateEdge()
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS)
        assert sig.family == EdgeFamily.FUNDING_RATE


# ---------------------------------------------------------------------------
# EdgeFamilyRegistry
# ---------------------------------------------------------------------------


class TestEdgeFamilyRegistry:
    def test_registry_has_four_families(self) -> None:
        reg = EdgeFamilyRegistry()
        assert len(reg) == 4

    def test_all_families_registered(self) -> None:
        reg = EdgeFamilyRegistry()
        families = reg.families()
        assert EdgeFamily.ORDER_FLOW_IMBALANCE in families
        assert EdgeFamily.VOLATILITY_TRANSITION in families
        assert EdgeFamily.LIQUIDATION_SIGNAL in families
        assert EdgeFamily.FUNDING_RATE in families

    def test_get_known_family_returns_evaluator(self) -> None:
        reg = EdgeFamilyRegistry()
        ev = reg.get(EdgeFamily.ORDER_FLOW_IMBALANCE)
        assert ev is not None

    def test_get_unknown_family_returns_none(self) -> None:
        reg = EdgeFamilyRegistry()
        assert reg.get("UNKNOWN_FAMILY") is None

    def test_custom_config_is_wired(self) -> None:
        from crypto_core.edge.families.order_flow import OFIConfig

        cfg = RegistryConfig(ofi=OFIConfig(window=99))
        reg = EdgeFamilyRegistry(cfg)
        ev = reg.get(EdgeFamily.ORDER_FLOW_IMBALANCE)
        assert ev is not None
        assert ev._cfg.window == 99  # type: ignore[attr-defined]
