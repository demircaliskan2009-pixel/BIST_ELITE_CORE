"""Tests for the implemented crypto edge families and registry wiring."""

from __future__ import annotations

from crypto_core.data.models.events import Exchange, LiquidationEvent, MarkPriceEvent, TradeEvent, TradeSide
from crypto_core.edge.activation import RegimeState
from crypto_core.edge.families.funding import FundingConfig, FundingRateEdge, FundingSafetyContext
from crypto_core.edge.families.liquidation import LiquidationConfig, LiquidationSignalEdge
from crypto_core.edge.families.volatility import VolatilityConfig, VolatilityTransitionEdge
from crypto_core.edge.models import EdgeFamily, SignalDirection
from crypto_core.edge.registry import EdgeFamilyRegistry, RegistryConfig

_NS_PER_MINUTE = 60 * 1_000_000_000
_T0_NS = 1_000_000_000_000


def _trade(price: float = 50_000.0, qty: float = 1.0, side: TradeSide = TradeSide.BUY) -> TradeEvent:
    return TradeEvent(
        trade_id=f"t-{price}-{qty}-{side}",
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
    for idx in range(n_spike):
        price = 50_000.0 * (1.02 if idx % 2 == 0 else 0.98)
        trades.append(_trade(price=price))
    return trades


def _mark_price_event(funding_rate: float = 0.0, mark_price: float = 50_000.0) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        mark_price=mark_price,
        index_price=mark_price,
        funding_rate=funding_rate,
        next_funding_time_ns=_T0_NS + 8 * 3600 * 1_000_000_000,
        timestamp_ns=_T0_NS,
    )


def _funding_ctx(
    *,
    regime_state: str | None = RegimeState.RANGE,
    regime_trending_recently: bool | None = False,
    recent_return_4h: float | None = 0.0,
    trend_strength: float | None = 0.0,
) -> FundingSafetyContext:
    return FundingSafetyContext(
        regime_state=regime_state,
        regime_trending_recently=regime_trending_recently,
        recent_return_4h=recent_return_4h,
        trend_strength=trend_strength,
    )


def _liq_event(*, side: TradeSide, qty: float, minutes_ago: float, current_ns: int = _T0_NS) -> LiquidationEvent:
    return LiquidationEvent(
        symbol="BTCUSDT",
        exchange=Exchange.BINANCE,
        side=side,
        price=50_000.0,
        qty=qty,
        timestamp_ns=current_ns - int(minutes_ago * _NS_PER_MINUTE),
    )


class TestVolatilityTransitionEdge:
    def test_insufficient_trades_returns_invalid(self) -> None:
        sig = VolatilityTransitionEdge().evaluate([_trade()], "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is False
        assert "insufficient_trades" in (sig.block_reason or "")

    def test_flat_prices_returns_neutral(self) -> None:
        sig = VolatilityTransitionEdge().evaluate(_flat_trades(150), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL

    def test_vol_expansion_returns_valid_signal(self) -> None:
        edge = VolatilityTransitionEdge(
            VolatilityConfig(short_window=20, long_window=80, expansion_threshold=1.2, min_trades=81)
        )
        sig = edge.evaluate(_expanding_vol_trades(80, 40), "BTCUSDT", "binance", _T0_NS)
        assert sig.is_valid is True
        assert sig.evidence["vol_ratio"] > 1.0
        assert 0.0 <= sig.confidence <= 1.0
        assert sig.family == EdgeFamily.VOLATILITY_TRANSITION


class TestLiquidationSignalEdge:
    def test_missing_feed_returns_invalid(self) -> None:
        sig = LiquidationSignalEdge().evaluate([], "BTCUSDT", "binance", _T0_NS, liquidation_events=None)
        assert sig.is_valid is False
        assert sig.block_reason == "liquidation_feed_unavailable"

    def test_empty_feed_returns_neutral_valid(self) -> None:
        sig = LiquidationSignalEdge().evaluate([], "BTCUSDT", "binance", _T0_NS, liquidation_events=())
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.NEUTRAL
        assert sig.evidence["cascade_state"] == "NORMAL"

    def test_building_cascade_blocks_entry(self) -> None:
        edge = LiquidationSignalEdge(
            LiquidationConfig(
                min_events=5,
                min_total_liquidation_qty=4.0,
                bucket_ns=_NS_PER_MINUTE,
                max_buckets=5,
                building_acceleration_threshold=1.5,
                active_acceleration_threshold=3.0,
            )
        )
        events = [
            _liq_event(side=TradeSide.BUY, qty=2.0, minutes_ago=4.5),
            _liq_event(side=TradeSide.BUY, qty=2.0, minutes_ago=3.5),
            _liq_event(side=TradeSide.BUY, qty=2.0, minutes_ago=2.5),
            _liq_event(side=TradeSide.BUY, qty=2.0, minutes_ago=1.5),
            _liq_event(side=TradeSide.BUY, qty=4.0, minutes_ago=0.2),
        ]
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS, liquidation_events=events)
        assert sig.is_valid is False
        assert sig.block_reason == "liquidation_cascade_building"
        assert sig.evidence["cascade_state"] == "BUILDING"

    def test_completed_long_cascade_returns_buy(self) -> None:
        edge = LiquidationSignalEdge(
            LiquidationConfig(
                min_events=4,
                min_total_liquidation_qty=5.0,
                imbalance_threshold=0.6,
                bucket_ns=_NS_PER_MINUTE,
                max_buckets=5,
                complete_ratio_threshold=0.10,
            )
        )
        events = [
            _liq_event(side=TradeSide.BUY, qty=8.0, minutes_ago=3.5),
            _liq_event(side=TradeSide.BUY, qty=0.4, minutes_ago=2.5),
            _liq_event(side=TradeSide.BUY, qty=0.4, minutes_ago=1.5),
            _liq_event(side=TradeSide.BUY, qty=0.4, minutes_ago=0.5),
        ]
        sig = edge.evaluate([], "BTCUSDT", "binance", _T0_NS, liquidation_events=events)
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.BUY
        assert sig.evidence["cascade_state"] == "CASCADE_COMPLETE"
        assert sig.evidence["liquidation_imbalance"] > 0.6


class TestFundingRateEdge:
    def test_no_mark_price_returns_invalid(self) -> None:
        sig = FundingRateEdge().evaluate([], "BTCUSDT", "binance", _T0_NS, mark_price_event=None)
        assert sig.is_valid is False
        assert sig.block_reason == "funding_feed_unavailable"
        assert sig.evidence["status"] == "unavailable"

    def test_low_rate_returns_neutral_without_safety_context(self) -> None:
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

    def test_directional_rate_requires_safety_context(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.003),
        )
        assert sig.is_valid is False
        assert sig.block_reason == "funding_safety_context_unavailable"

    def test_high_positive_rate_returns_sell_when_safe(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.003),
            safety_context=_funding_ctx(recent_return_4h=0.005, trend_strength=0.4),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.SELL
        assert sig.confidence > 0.0

    def test_high_negative_rate_returns_buy_when_safe(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=-0.003),
            safety_context=_funding_ctx(recent_return_4h=-0.005, trend_strength=-0.4),
        )
        assert sig.is_valid is True
        assert sig.direction == SignalDirection.BUY
        assert sig.confidence > 0.0

    def test_trending_context_blocks_directional_trade(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.003),
            safety_context=_funding_ctx(regime_trending_recently=True),
        )
        assert sig.is_valid is False
        assert sig.block_reason == "funding_transition_cooldown"

    def test_strong_runaway_move_blocks_directional_trade(self) -> None:
        sig = FundingRateEdge().evaluate(
            [],
            "BTCUSDT",
            "binance",
            _T0_NS,
            mark_price_event=_mark_price_event(funding_rate=0.003),
            safety_context=_funding_ctx(recent_return_4h=0.03, trend_strength=0.2),
        )
        assert sig.is_valid is False
        assert sig.block_reason == "funding_price_runaway_up"

    def test_custom_threshold_is_respected(self) -> None:
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
        assert sig.family == EdgeFamily.FUNDING_RATE


class TestEdgeFamilyRegistry:
    def test_registry_has_seven_families(self) -> None:
        assert len(EdgeFamilyRegistry()) == 7

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

    def test_custom_config_is_wired(self) -> None:
        from crypto_core.edge.families.order_flow import OFIConfig

        reg = EdgeFamilyRegistry(RegistryConfig(ofi=OFIConfig(window=99)))
        evaluator = reg.get(EdgeFamily.ORDER_FLOW_IMBALANCE)
        assert evaluator is not None
        assert evaluator._cfg.window == 99  # type: ignore[attr-defined]
