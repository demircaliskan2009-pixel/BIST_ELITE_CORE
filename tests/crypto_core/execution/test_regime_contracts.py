"""Tests for regime state contracts — Phase 9B.

Covers:
  - OptionsRegimeLevel / EventRegimeLevel / OnChainRegimeLevel enum values
  - OptionsRegimeState frozen, is_available, is_extreme
  - EventRegimeState frozen, is_available, is_active_or_pending
  - OnChainRegimeState frozen, is_available, is_stress
  - CompositeRegimeState any_extreme, available_dimensions, unavailable_dimensions
  - Serialization round-trip for CompositeRegimeState
  - Fail-closed on malformed dict
"""

from __future__ import annotations

import pytest

from crypto_core.execution.regime_contracts import (
    CompositeRegimeState,
    EventCategory,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
    composite_regime_from_dict,
    composite_regime_to_dict,
)


class TestOptionsRegime:
    def test_enum_values(self) -> None:
        assert OptionsRegimeLevel.NORMAL.value == "normal"
        assert OptionsRegimeLevel.UNAVAILABLE.value == "unavailable"

    def test_frozen(self) -> None:
        state = OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.NORMAL,
            snapshot_ns=1_000_000,
            source="deribit",
        )
        with pytest.raises(AttributeError):
            state.level = OptionsRegimeLevel.EXTREME  # type: ignore[misc]

    def test_is_available(self) -> None:
        state = OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.NORMAL,
            snapshot_ns=1_000_000,
            source="deribit",
        )
        assert state.is_available is True

    def test_is_unavailable(self) -> None:
        state = OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.UNAVAILABLE,
            snapshot_ns=1_000_000,
            source="none",
        )
        assert state.is_available is False

    def test_is_extreme(self) -> None:
        state = OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.EXTREME,
            snapshot_ns=1_000_000,
            source="deribit",
            implied_vol_30d=0.95,
        )
        assert state.is_extreme is True

    def test_is_not_extreme(self) -> None:
        state = OptionsRegimeState(
            symbol="BTCUSDT",
            level=OptionsRegimeLevel.ELEVATED,
            snapshot_ns=1_000_000,
            source="deribit",
        )
        assert state.is_extreme is False


class TestEventRegime:
    def test_enum_values(self) -> None:
        assert EventRegimeLevel.QUIET.value == "quiet"
        assert EventRegimeLevel.ACTIVE.value == "active"

    def test_is_available(self) -> None:
        state = EventRegimeState(
            level=EventRegimeLevel.QUIET,
            snapshot_ns=1_000_000,
            source="calendar",
        )
        assert state.is_available is True

    def test_is_unavailable(self) -> None:
        state = EventRegimeState(
            level=EventRegimeLevel.UNAVAILABLE,
            snapshot_ns=1_000_000,
            source="none",
        )
        assert state.is_available is False

    def test_is_active_or_pending(self) -> None:
        for level in (EventRegimeLevel.ACTIVE, EventRegimeLevel.PENDING):
            state = EventRegimeState(
                level=level,
                snapshot_ns=1_000_000,
                source="calendar",
            )
            assert state.is_active_or_pending is True

    def test_is_not_active_or_pending(self) -> None:
        state = EventRegimeState(
            level=EventRegimeLevel.QUIET,
            snapshot_ns=1_000_000,
            source="calendar",
        )
        assert state.is_active_or_pending is False


class TestEventCategory:
    def test_values(self) -> None:
        assert EventCategory.MACRO.value == "macro"
        assert EventCategory.PROTOCOL.value == "protocol"
        assert EventCategory.UNKNOWN.value == "unknown"


class TestOnChainRegime:
    def test_enum_values(self) -> None:
        assert OnChainRegimeLevel.NORMAL.value == "normal"
        assert OnChainRegimeLevel.STRESS.value == "stress"

    def test_is_available(self) -> None:
        state = OnChainRegimeState(
            symbol="BTC",
            level=OnChainRegimeLevel.NORMAL,
            snapshot_ns=1_000_000,
            source="glassnode",
        )
        assert state.is_available is True

    def test_is_stress(self) -> None:
        state = OnChainRegimeState(
            symbol="BTC",
            level=OnChainRegimeLevel.STRESS,
            snapshot_ns=1_000_000,
            source="glassnode",
        )
        assert state.is_stress is True


class TestCompositeRegimeState:
    def _make_composite(
        self,
        options_level: OptionsRegimeLevel = OptionsRegimeLevel.NORMAL,
        event_level: EventRegimeLevel = EventRegimeLevel.QUIET,
        on_chain_level: OnChainRegimeLevel = OnChainRegimeLevel.NORMAL,
    ) -> CompositeRegimeState:
        return CompositeRegimeState(
            snapshot_ns=1_000_000,
            options=OptionsRegimeState(
                symbol="BTCUSDT",
                level=options_level,
                snapshot_ns=1_000_000,
                source="deribit",
            ),
            event=EventRegimeState(
                level=event_level,
                snapshot_ns=1_000_000,
                source="calendar",
            ),
            on_chain=OnChainRegimeState(
                symbol="BTC",
                level=on_chain_level,
                snapshot_ns=1_000_000,
                source="glassnode",
            ),
        )

    def test_no_extreme(self) -> None:
        state = self._make_composite()
        assert state.any_extreme is False

    def test_options_extreme(self) -> None:
        state = self._make_composite(options_level=OptionsRegimeLevel.EXTREME)
        assert state.any_extreme is True

    def test_event_active(self) -> None:
        state = self._make_composite(event_level=EventRegimeLevel.ACTIVE)
        assert state.any_extreme is True

    def test_onchain_stress(self) -> None:
        state = self._make_composite(on_chain_level=OnChainRegimeLevel.STRESS)
        assert state.any_extreme is True

    def test_available_dimensions(self) -> None:
        state = self._make_composite()
        assert sorted(state.available_dimensions) == ["event", "on_chain", "options"]

    def test_unavailable_dimensions_partial(self) -> None:
        state = CompositeRegimeState(
            snapshot_ns=1_000_000,
            options=OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.UNAVAILABLE,
                snapshot_ns=1_000_000,
                source="none",
            ),
        )
        assert "options" in state.unavailable_dimensions
        assert "event" in state.unavailable_dimensions  # None → unavailable

    def test_all_none(self) -> None:
        state = CompositeRegimeState(snapshot_ns=1_000_000)
        assert state.any_extreme is False
        assert state.available_dimensions == []
        assert len(state.unavailable_dimensions) == 3


class TestCompositeRegimeSerialization:
    def test_round_trip(self) -> None:
        original = CompositeRegimeState(
            snapshot_ns=1_000_000,
            options=OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.ELEVATED,
                snapshot_ns=1_000_000,
                source="deribit",
                implied_vol_30d=0.65,
            ),
            event=EventRegimeState(
                level=EventRegimeLevel.PENDING,
                snapshot_ns=1_000_000,
                source="calendar",
                event_category=EventCategory.MACRO,
                event_label="FOMC_2026_04",
                hours_until_event=12.5,
            ),
            on_chain=OnChainRegimeState(
                symbol="BTC",
                level=OnChainRegimeLevel.ACCUMULATION,
                snapshot_ns=1_000_000,
                source="glassnode",
                exchange_net_flow_24h_usd=-500_000_000.0,
            ),
        )
        d = composite_regime_to_dict(original)
        restored = composite_regime_from_dict(d)

        assert restored.snapshot_ns == original.snapshot_ns
        assert restored.options is not None
        assert restored.options.level == OptionsRegimeLevel.ELEVATED
        assert restored.options.implied_vol_30d == 0.65
        assert restored.event is not None
        assert restored.event.event_label == "FOMC_2026_04"
        assert restored.on_chain is not None
        assert restored.on_chain.exchange_net_flow_24h_usd == -500_000_000.0

    def test_round_trip_partial(self) -> None:
        """Round-trip with only options populated."""
        original = CompositeRegimeState(
            snapshot_ns=2_000_000,
            options=OptionsRegimeState(
                symbol="ETHUSDT",
                level=OptionsRegimeLevel.NORMAL,
                snapshot_ns=2_000_000,
                source="deribit",
            ),
        )
        d = composite_regime_to_dict(original)
        restored = composite_regime_from_dict(d)
        assert restored.options is not None
        assert restored.event is None
        assert restored.on_chain is None

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            composite_regime_from_dict({"bad": "data"})
