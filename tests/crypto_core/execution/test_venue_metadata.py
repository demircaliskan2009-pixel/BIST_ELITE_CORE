"""Tests for venue metadata availability model — Phase 9B.

Covers:
  - MetadataFreshness / VenueOperationalStatus enum values
  - FeeMetadata frozen, is_usable, is_conservative
  - FundingMetadata frozen, is_usable
  - OperationalMetadata frozen, is_tradeable
  - VenueMetadataSnapshot execution_permitted (fail-closed)
  - build_hardcoded_fee_metadata factory
  - build_unavailable_metadata factory
  - Serialization round-trip
  - Fail-closed on malformed dict
"""

from __future__ import annotations

import pytest

from crypto_core.execution.venue_metadata import (
    FeeMetadata,
    FundingMetadata,
    MetadataFreshness,
    OperationalMetadata,
    VenueMetadataSnapshot,
    VenueOperationalStatus,
    build_hardcoded_fee_metadata,
    build_unavailable_metadata,
    venue_metadata_from_dict,
    venue_metadata_to_dict,
)


class TestMetadataFreshnessEnum:
    def test_values(self) -> None:
        assert MetadataFreshness.LIVE.value == "live"
        assert MetadataFreshness.ESTIMATED.value == "estimated"
        assert MetadataFreshness.STALE.value == "stale"
        assert MetadataFreshness.UNAVAILABLE.value == "unavailable"


class TestFeeMetadata:
    def test_frozen(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            freshness=MetadataFreshness.LIVE,
            source="api",
            observed_at_ns=1_000_000,
        )
        with pytest.raises(AttributeError):
            fee.taker_fee_bps = 10.0  # type: ignore[misc]

    def test_is_usable_live(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            freshness=MetadataFreshness.LIVE,
            source="api",
            observed_at_ns=1_000_000,
        )
        assert fee.is_usable is True

    def test_is_usable_estimated(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            freshness=MetadataFreshness.ESTIMATED,
            source="hardcoded",
            observed_at_ns=1_000_000,
        )
        assert fee.is_usable is True

    def test_is_usable_unavailable(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=0.0,
            taker_fee_bps=0.0,
            freshness=MetadataFreshness.UNAVAILABLE,
            source="none",
            observed_at_ns=0,
        )
        assert fee.is_usable is False

    def test_is_conservative(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            freshness=MetadataFreshness.ESTIMATED,
            source="hardcoded",
            observed_at_ns=1_000_000,
        )
        assert fee.is_conservative is True  # ESTIMATED is conservative

    def test_is_not_conservative_live(self) -> None:
        fee = FeeMetadata(
            maker_fee_bps=2.0,
            taker_fee_bps=5.0,
            freshness=MetadataFreshness.LIVE,
            source="api",
            observed_at_ns=1_000_000,
        )
        assert fee.is_conservative is False


class TestFundingMetadata:
    def test_frozen(self) -> None:
        f = FundingMetadata(
            funding_rate_bps=1.5,
            freshness=MetadataFreshness.LIVE,
            source="api",
            observed_at_ns=1_000_000,
        )
        with pytest.raises(AttributeError):
            f.funding_rate_bps = 2.0  # type: ignore[misc]

    def test_is_usable_live(self) -> None:
        f = FundingMetadata(
            funding_rate_bps=1.5,
            freshness=MetadataFreshness.LIVE,
            source="api",
            observed_at_ns=1_000_000,
        )
        assert f.is_usable is True

    def test_is_usable_unavailable(self) -> None:
        f = FundingMetadata(
            funding_rate_bps=0.0,
            freshness=MetadataFreshness.UNAVAILABLE,
            source="none",
            observed_at_ns=0,
        )
        assert f.is_usable is False


class TestOperationalMetadata:
    def test_is_tradeable_operational(self) -> None:
        op = OperationalMetadata(
            status=VenueOperationalStatus.OPERATIONAL,
            freshness=MetadataFreshness.LIVE,
            observed_at_ns=1_000_000,
        )
        assert op.is_tradeable is True

    def test_is_not_tradeable_degraded(self) -> None:
        op = OperationalMetadata(
            status=VenueOperationalStatus.DEGRADED,
            freshness=MetadataFreshness.LIVE,
            observed_at_ns=1_000_000,
        )
        assert op.is_tradeable is False  # fail-closed: only OPERATIONAL is tradeable

    def test_is_not_tradeable_maintenance(self) -> None:
        op = OperationalMetadata(
            status=VenueOperationalStatus.MAINTENANCE,
            freshness=MetadataFreshness.LIVE,
            observed_at_ns=1_000_000,
        )
        assert op.is_tradeable is False


class TestVenueMetadataSnapshot:
    def _make_snapshot(
        self,
        fee_freshness: MetadataFreshness = MetadataFreshness.LIVE,
        op_status: VenueOperationalStatus = VenueOperationalStatus.OPERATIONAL,
    ) -> VenueMetadataSnapshot:
        return VenueMetadataSnapshot(
            venue="binance",
            symbol="BTCUSDT",
            snapshot_ns=1_000_000,
            fees=FeeMetadata(
                maker_fee_bps=2.0,
                taker_fee_bps=5.0,
                freshness=fee_freshness,
                source="api",
                observed_at_ns=1_000_000,
            ),
            funding=FundingMetadata(
                funding_rate_bps=1.5,
                freshness=MetadataFreshness.LIVE,
                source="api",
                observed_at_ns=1_000_000,
            ),
            operational=OperationalMetadata(
                status=op_status,
                freshness=MetadataFreshness.LIVE,
                observed_at_ns=1_000_000,
            ),
        )

    def test_execution_permitted_all_good(self) -> None:
        snap = self._make_snapshot()
        assert snap.execution_permitted is True

    def test_execution_blocked_fees_unavailable(self) -> None:
        snap = self._make_snapshot(fee_freshness=MetadataFreshness.UNAVAILABLE)
        assert snap.execution_permitted is False

    def test_execution_blocked_maintenance(self) -> None:
        snap = self._make_snapshot(
            op_status=VenueOperationalStatus.MAINTENANCE,
        )
        assert snap.execution_permitted is False

    def test_has_funding_data(self) -> None:
        snap = self._make_snapshot()
        assert snap.has_funding_data is True

    def test_worst_case_fee_bps(self) -> None:
        snap = self._make_snapshot()
        # Should return taker_fee_bps since fees are live
        assert snap.worst_case_fee_bps >= 5.0


class TestBuildFactories:
    def test_hardcoded_binance(self) -> None:
        fee = build_hardcoded_fee_metadata("binance", 1_000_000)
        assert fee.freshness == MetadataFreshness.ESTIMATED
        assert fee.taker_fee_bps > 0
        assert fee.source == "hardcoded_default"

    def test_hardcoded_bybit(self) -> None:
        fee = build_hardcoded_fee_metadata("bybit", 1_000_000)
        assert fee.freshness == MetadataFreshness.ESTIMATED

    def test_hardcoded_unknown_venue_returns_none(self) -> None:
        fee = build_hardcoded_fee_metadata("unknown_exchange", 1_000_000)
        assert fee is None  # fail-closed: unknown venue has no hardcoded fees

    def test_unavailable_metadata(self) -> None:
        snap = build_unavailable_metadata("binance", "BTCUSDT", 1_000_000)
        assert snap.execution_permitted is False
        assert snap.fees is None  # no fee data available


class TestVenueMetadataSerialization:
    def test_round_trip(self) -> None:
        original = VenueMetadataSnapshot(
            venue="binance",
            symbol="BTCUSDT",
            snapshot_ns=1_000_000,
            fees=FeeMetadata(
                maker_fee_bps=2.0,
                taker_fee_bps=5.0,
                freshness=MetadataFreshness.LIVE,
                source="api",
                observed_at_ns=1_000_000,
            ),
            funding=FundingMetadata(
                funding_rate_bps=1.5,
                freshness=MetadataFreshness.LIVE,
                source="api",
                observed_at_ns=1_000_000,
            ),
            operational=OperationalMetadata(
                status=VenueOperationalStatus.OPERATIONAL,
                freshness=MetadataFreshness.LIVE,
                observed_at_ns=1_000_000,
            ),
        )
        d = venue_metadata_to_dict(original)
        restored = venue_metadata_from_dict(d)
        assert restored.venue == original.venue
        assert restored.execution_permitted == original.execution_permitted
        assert restored.fees.taker_fee_bps == original.fees.taker_fee_bps

    def test_malformed_raises(self) -> None:
        with pytest.raises(ValueError, match="Malformed"):
            venue_metadata_from_dict({"bad": "data"})
