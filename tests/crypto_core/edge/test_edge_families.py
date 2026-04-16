"""Tests for expanded edge families (volatility, liquidation, funding) + registry."""

from __future__ import annotations

from crypto_core.data.models.events import Exchange, MarkPriceEvent, TradeEvent, TradeSide
from crypto_core.edge.families.funding import FundingConfig, FundingRateEdge
from crypto_core.edge.families.liquidation import LiquidationConfig, LiquidationSignalEdge
from crypto_core.edge.families.volatility import VolatilityConfig, VolatilityTransitionEdge
from crypto_core.edge.models import EdgeFamily, SignalDirection
from crypto_core.edge.registry import EdgeFamilyRegistry, RegistryConfig

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
    trades = [_trade(price=50_000.0) for _ in range(n_flat)]
    for i in range(n_spike):
        price = 50_000.0 * (1.02 if i % 2 == 0 else 0.98)
        trades.append(_trade(price=price))
    return trades


def _mark_price_event(
    funding_rate: float = 0.0,
    mark_price: float = 50_000.0,
) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        mark_price=mark_price,
        index_price=mark_price,
        funding_rate=funding_rate,
        next_funding_time_ns=_T0_NS + 8 * 3600 * 1_000_000_000,
        timestamp_ns=_T0_NS,
    )


class TestVolatilityTransitionEdge:
    def test_insufficient_trades_returns_invalid(self) -> None:
        edge = VolatilityTransitionEdge()
        sig = edge.evaluate([_trade()], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_flat_prices_returns_neutral(self) -> None:
        edge = VolatilityTransitionEdge()
        sig = edge.evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_vol_expansion_returns_directional_signal(self) -> None:
        edge = VolatilityTransitionEdge(
            VolatilityConfig(short_window=20, long_window=80, expansion_threshold=1.2, min_trades=81)
        )
        sig = edge.evaluate(_expanding_vol_trades(80, 40), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.evidence["vol_ratio"] > 1.0

    def test_evidence_contains_required_fields(self) -> None:
        sig = VolatilityTransitionEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert "short_vol" in sig.evidence
        assert "long_vol" in sig.evidence

    def test_confidence_in_range(self) -> None:
        sig = VolatilityTransitionEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert 0.0 <= sig.confidence <= 1.0

    def test_family_tag(self) -> None:
        sig = VolatilityTransitionEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.family == EdgeFamily.VOLATILITY_TRANSITION


class TestLiquidationSignalEdge:
    def test_insufficient_trades_returns_invalid(self) -> None:
        sig = LiquidationSignalEdge().evaluate([_trade()], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_flat_prices_neutral(self) -> None:
        sig = LiquidationSignalEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_rapid_up_move_with_vol_spike_produces_signal(self) -> None:
        edge = LiquidationSignalEdge(
            LiquidationConfig(
                window=10, baseline_window=50, price_threshold=0.01, vol_spike_threshold=1.5, min_trades=51
            )
        )
        baseline = [_trade(price=50_000.0, qty=1.0) for _ in range(50)]
        spike = [_trade(price=50_000.0 * (1 + i * 0.005), qty=5.0) for i in range(10)]
        sig = edge.evaluate(baseline + spike, "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert "price_move_pct" in sig.evidence
        assert "vol_spike" in sig.evidence

    def test_confidence_in_range(self) -> None:
        sig = LiquidationSignalEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert 0.0 <= sig.confidence <= 1.0

    def test_family_tag(self) -> None:
        sig = LiquidationSignalEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.family == EdgeFamily.LIQUIDATION_SIGNAL


class TestFundingRateEdge:
    def test_no_mark_price_returns_invalid(self) -> None:
        sig = FundingRateEdge().evaluate([], "BTCUSDT", "binance", _T0_NS, mark_price_event=None)
        assert sig.is_valid is False
        assert sig.block_reason == "funding_feed_unavailable"
        assert sig.evidence["status"] == "unavailable"

    def test_low_rate_returns_neutral(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.0001),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL
        assert sig.confidence == 0.0

    def test_high_positive_rate_returns_sell(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.003),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.SELL
        assert sig.confidence > 0.0

    def test_high_negative_rate_returns_buy(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=-0.003),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.BUY
        assert sig.confidence > 0.0

    def test_confidence_in_range(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.005),
        )
        assert 0.0 <= sig.confidence <= 1.0

    def test_evidence_has_status_active(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.001),
        )
        assert sig.evidence["status"] == "active"
        assert "funding_rate" in sig.evidence

    def test_family_tag(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(),
        )
        assert sig.family == EdgeFamily.FUNDING_RATE

    def test_custom_threshold(self) -> None:
        edge = FundingRateEdge(FundingConfig(rate_threshold=0.001))
        sig = edge.evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.0005),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL


class TestEdgeFamilyRegistry:
    def test_registry_has_seven_families(self) -> None:
        reg = EdgeFamilyRegistry()
        assert len(reg) == 7

    def test_implemented_families_registered(self) -> None:
        families = EdgeFamilyRegistry().families()
        assert EdgeFamily.ORDER_FLOW_IMBALANCE in families
        assert EdgeFamily.FUNDING_RATE in families
        assert EdgeFamily.VOLATILITY_TRANSITION in families
        assert EdgeFamily.LIQUIDATION_SIGNAL in families

    def test_efg_contract_stubs_registered(self) -> None:
        families = EdgeFamilyRegistry().families()
        assert EdgeFamily.CROSS_EXCHANGE_SPREAD in families
        assert EdgeFamily.LATENCY_ARBITRAGE in families
        assert EdgeFamily.VOL_SURFACE_SKEW in families

    def test_efg_stubs_always_return_invalid(self) -> None:
        reg = EdgeFamilyRegistry()
        for fam in (
            EdgeFamily.CROSS_EXCHANGE_SPREAD,
            EdgeFamily.LATENCY_ARBITRAGE,
            EdgeFamily.VOL_SURFACE_SKEW,
        ):
            evaluator = reg.get(fam)
            assert evaluator is not None
            sig = evaluator.evaluate([], "BTCUSDT", "binance", 1_000_000_000)  # type: ignore[union-attr]
            assert sig.is_valid is False
            assert sig.block_reason == "family_not_implemented"

    def test_get_known_family_returns_evaluator(self) -> None:
        assert EdgeFamilyRegistry().get(EdgeFamily.ORDER_FLOW_IMBALANCE) is not None

    def test_get_unknown_family_returns_none(self) -> None:
        assert EdgeFamilyRegistry().get("COMPLETELY_UNKNOWN_FAMILY") is None

    def test_custom_config_is_wired(self) -> None:
        from crypto_core.edge.families.order_flow import OFIConfig

        reg = EdgeFamilyRegistry(RegistryConfig(ofi=OFIConfig(window=99)))
        evaluator = reg.get(EdgeFamily.ORDER_FLOW_IMBALANCE)
        assert evaluator is not None
        assert evaluator._cfg.window == 99  # type: ignore[attr-defined]
