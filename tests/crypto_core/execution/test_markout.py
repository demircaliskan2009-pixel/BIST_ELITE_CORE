"""Tests for markout observation lifecycle — Phase 9B.

Covers:
  - MarkoutHorizonStatus / MarkoutSetStatus enum values
  - HorizonObservation frozen invariant
  - MarkoutObserver: register_fill, observe_price, expire_stale
  - Observation set lifecycle: ALL_PENDING → PARTIAL → ALL_READY
  - Expiry lifecycle: PENDING → EXPIRED
  - Mixed expired + ready = MIXED_EXPIRED
  - Fail-closed: invalid inputs → ValueError
  - harvest_complete removes completed fills
  - Serialization round-trip
"""

from __future__ import annotations

import pytest

from crypto_core.execution.markout import (
    HorizonObservation,
    MarkoutHorizonStatus,
    MarkoutObserver,
    MarkoutObserverConfig,
    MarkoutSetStatus,
    observation_set_from_dict,
    observation_set_to_dict,
)


class TestEnums:
    def test_horizon_status_values(self) -> None:
        assert MarkoutHorizonStatus.PENDING.value == "pending"
        assert MarkoutHorizonStatus.READY.value == "ready"
        assert MarkoutHorizonStatus.EXPIRED.value == "expired"

    def test_set_status_values(self) -> None:
        assert MarkoutSetStatus.ALL_PENDING.value == "all_pending"
        assert MarkoutSetStatus.ALL_READY.value == "all_ready"
        assert MarkoutSetStatus.PARTIAL.value == "partial"


class TestHorizonObservation:
    def test_frozen(self) -> None:
        h = HorizonObservation(
            horizon_seconds=5,
            status=MarkoutHorizonStatus.PENDING,
        )
        with pytest.raises(AttributeError):
            h.status = MarkoutHorizonStatus.READY  # type: ignore[misc]


class TestMarkoutObserverRegister:
    def test_register_fill_success(self) -> None:
        obs = MarkoutObserver()
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")
        assert obs.pending_count == 1
        assert "o1" in obs.tracked_order_ids()

    def test_register_invalid_price_raises(self) -> None:
        obs = MarkoutObserver()
        with pytest.raises(ValueError, match="fill_price"):
            obs.register_fill("o1", -1.0, 1_000_000_000, True, "BTCUSDT", "binance")

    def test_register_invalid_timestamp_raises(self) -> None:
        obs = MarkoutObserver()
        with pytest.raises(ValueError, match="fill_timestamp_ns"):
            obs.register_fill("o1", 50000.0, 0, True, "BTCUSDT", "binance")

    def test_register_empty_order_id_raises(self) -> None:
        obs = MarkoutObserver()
        with pytest.raises(ValueError, match="order_id"):
            obs.register_fill("", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")

    def test_register_empty_symbol_raises(self) -> None:
        obs = MarkoutObserver()
        with pytest.raises(ValueError, match="symbol"):
            obs.register_fill("o1", 50000.0, 1_000_000_000, True, "", "binance")


class TestMarkoutObserverObserve:
    def _make_observer(self) -> MarkoutObserver:
        config = MarkoutObserverConfig(horizons=(1, 5))
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")
        return obs

    def test_initial_status_all_pending(self) -> None:
        obs = self._make_observer()
        s = obs.get_observation_set("o1")
        assert s is not None
        assert s.set_status == MarkoutSetStatus.ALL_PENDING
        assert all(h.status == MarkoutHorizonStatus.PENDING for h in s.horizons)

    def test_observe_resolves_first_horizon(self) -> None:
        obs = self._make_observer()
        # Price at 1s horizon (target = 1_000_000_000 + 1 * 1e9 = 2_000_000_000)
        resolved = obs.observe_price("BTCUSDT", "binance", 50010.0, 2_000_000_000)
        assert "o1" in resolved

        s = obs.get_observation_set("o1")
        assert s is not None
        assert s.set_status == MarkoutSetStatus.PARTIAL
        # 1s horizon should be READY
        h1 = s.horizons[0]
        assert h1.status == MarkoutHorizonStatus.READY
        assert h1.mid_price_at_horizon == 50010.0
        assert h1.markout_bps is not None
        assert h1.markout_bps > 0  # buy + price went up = favorable

    def test_observe_resolves_all_horizons(self) -> None:
        obs = self._make_observer()
        # Observe at time past both horizons (1s and 5s)
        obs.observe_price("BTCUSDT", "binance", 50020.0, 6_000_000_000)
        s = obs.get_observation_set("o1")
        assert s is not None
        assert s.set_status == MarkoutSetStatus.ALL_READY

    def test_observe_wrong_symbol_no_resolve(self) -> None:
        obs = self._make_observer()
        resolved = obs.observe_price("ETHUSDT", "binance", 50010.0, 2_000_000_000)
        assert resolved == []

    def test_observe_wrong_exchange_no_resolve(self) -> None:
        obs = self._make_observer()
        resolved = obs.observe_price("BTCUSDT", "bybit", 50010.0, 2_000_000_000)
        assert resolved == []

    def test_observe_too_early_no_resolve(self) -> None:
        obs = self._make_observer()
        resolved = obs.observe_price("BTCUSDT", "binance", 50010.0, 1_500_000_000)
        assert resolved == []


class TestMarkoutObserverExpiry:
    def test_expire_stale_horizons(self) -> None:
        config = MarkoutObserverConfig(horizons=(1,), expiry_grace_seconds=10)
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")

        # Target = 2e9, grace = 10e9, expire after 12e9 (strict >)
        expired = obs.expire_stale(12_000_000_001)
        assert "o1" in expired

        s = obs.get_observation_set("o1")
        assert s is not None
        assert s.set_status == MarkoutSetStatus.ALL_EXPIRED
        assert s.horizons[0].status == MarkoutHorizonStatus.EXPIRED

    def test_expire_does_not_affect_resolved(self) -> None:
        config = MarkoutObserverConfig(horizons=(1, 5), expiry_grace_seconds=10)
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")

        # Resolve 1s horizon
        obs.observe_price("BTCUSDT", "binance", 50010.0, 2_000_000_000)
        # Expire 5s horizon (target=6e9, grace=10e9 → expire after 16e9)
        obs.expire_stale(17_000_000_000)

        s = obs.get_observation_set("o1")
        assert s is not None
        assert s.set_status == MarkoutSetStatus.MIXED_EXPIRED
        assert s.horizons[0].status == MarkoutHorizonStatus.READY
        assert s.horizons[1].status == MarkoutHorizonStatus.EXPIRED


class TestMarkoutObserverHarvest:
    def test_harvest_complete(self) -> None:
        config = MarkoutObserverConfig(horizons=(1,))
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")
        obs.observe_price("BTCUSDT", "binance", 50010.0, 2_000_000_000)

        assert obs.is_complete("o1")
        harvested = obs.harvest_complete()
        assert len(harvested) == 1
        assert harvested[0].order_id == "o1"
        assert obs.pending_count == 0

    def test_harvest_does_not_remove_incomplete(self) -> None:
        config = MarkoutObserverConfig(horizons=(1, 5))
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")
        obs.observe_price("BTCUSDT", "binance", 50010.0, 2_000_000_000)

        assert not obs.is_complete("o1")
        harvested = obs.harvest_complete()
        assert len(harvested) == 0
        assert obs.pending_count == 1


class TestMarkoutObserverNonTracked:
    def test_get_observation_set_none(self) -> None:
        obs = MarkoutObserver()
        assert obs.get_observation_set("nonexistent") is None

    def test_is_complete_false_for_unknown(self) -> None:
        obs = MarkoutObserver()
        assert not obs.is_complete("nonexistent")


class TestMarkoutSellDirection:
    def test_sell_markout_favorable(self) -> None:
        config = MarkoutObserverConfig(horizons=(1,))
        obs = MarkoutObserver(config)
        # Sell at 50000, price drops to 49990 → favorable
        obs.register_fill("s1", 50000.0, 1_000_000_000, False, "BTCUSDT", "binance")
        obs.observe_price("BTCUSDT", "binance", 49990.0, 2_000_000_000)

        s = obs.get_observation_set("s1")
        assert s is not None
        assert s.horizons[0].markout_bps is not None
        assert s.horizons[0].markout_bps > 0  # favorable for sell


class TestMarkoutSerialization:
    def test_round_trip(self) -> None:
        config = MarkoutObserverConfig(horizons=(1,))
        obs = MarkoutObserver(config)
        obs.register_fill("o1", 50000.0, 1_000_000_000, True, "BTCUSDT", "binance")
        obs.observe_price("BTCUSDT", "binance", 50010.0, 2_000_000_000)

        original = obs.get_observation_set("o1")
        assert original is not None
        d = observation_set_to_dict(original)
        restored = observation_set_from_dict(d)

        assert restored.order_id == original.order_id
        assert restored.set_status == original.set_status
        assert len(restored.horizons) == len(original.horizons)
        assert restored.horizons[0].markout_bps == original.horizons[0].markout_bps

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            observation_set_from_dict({"bad": "data"})
