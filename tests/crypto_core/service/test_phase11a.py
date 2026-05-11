"""Phase 11A tests — External regime data plane integration.

Covers:
  1. Options regime contract construction
  2. Event regime contract construction (new categories)
  3. On-chain regime contract construction
  4. Composite external regime surface
  5. Unavailable / stale / partial / degraded truth handling
  6. Serialization / roundtrip
  7. Integration into operator/service/reporting surfaces
  8. High-risk external regime summary
  9. No-fake-data behavior
  10. DataFreshness and EventSeverity enums

PRD reference: §1.4, §1.29, §4.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from crypto_core.execution.regime_contracts import (
    CompositeRegimeState,
    DataFreshness,
    EventCategory,
    EventRegimeLevel,
    EventRegimeState,
    EventSeverity,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
    composite_regime_from_dict,
    composite_regime_to_dict,
)
from crypto_core.service.external_regime import (
    DimensionFreshness,
    ExternalRegimeDataPlane,
    dimension_freshness_from_dict,
    dimension_freshness_to_dict,
    external_regime_snapshot_from_dict,
    external_regime_snapshot_to_dict,
)
from crypto_core.service.service_orchestrator import (
    EvidenceSufficiencyState,
    OperatorSnapshot,
    ServiceOrchestrator,
    evidence_sufficiency_state_to_dict,
    operator_snapshot_to_dict,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NS_PER_S: int = 1_000_000_000
_T0_NS: int = 1_700_000_000 * _NS_PER_S  # base timestamp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_options_state(
    *,
    symbol: str = "BTCUSDT",
    level: OptionsRegimeLevel = OptionsRegimeLevel.NORMAL,
    snapshot_ns: int = _T0_NS,
    source: str = "deribit",
    implied_vol_30d: float | None = 0.55,
    implied_vol_7d: float | None = 0.60,
    skew_25d: float | None = -0.05,
) -> OptionsRegimeState:
    return OptionsRegimeState(
        symbol=symbol,
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        implied_vol_30d=implied_vol_30d,
        implied_vol_7d=implied_vol_7d,
        skew_25d=skew_25d,
    )


def _make_event_state(
    *,
    level: EventRegimeLevel = EventRegimeLevel.QUIET,
    snapshot_ns: int = _T0_NS,
    source: str = "calendar_api",
    event_category: EventCategory = EventCategory.UNKNOWN,
    event_label: str | None = None,
    hours_until_event: float | None = None,
    impact_estimate: float | None = None,
) -> EventRegimeState:
    return EventRegimeState(
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        event_category=event_category,
        event_label=event_label,
        hours_until_event=hours_until_event,
        impact_estimate=impact_estimate,
    )


def _make_on_chain_state(
    *,
    symbol: str = "BTC",
    level: OnChainRegimeLevel = OnChainRegimeLevel.NORMAL,
    snapshot_ns: int = _T0_NS,
    source: str = "glassnode",
    exchange_net_flow_24h_usd: float | None = 50_000_000.0,
    whale_transfer_count_24h: int | None = 12,
) -> OnChainRegimeState:
    return OnChainRegimeState(
        symbol=symbol,
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        exchange_net_flow_24h_usd=exchange_net_flow_24h_usd,
        whale_transfer_count_24h=whale_transfer_count_24h,
    )


def _make_mock_service() -> MagicMock:
    """Create a MagicMock PaperLiveService with realistic status()."""
    svc = MagicMock()
    ei_status = MagicMock()
    ei_status.degraded = False
    ei_status.degraded_reasons = ()

    watchdog = MagicMock()
    watchdog.last_event_time_ns = _T0_NS

    status = MagicMock()
    status.service_mode = "running"
    status.trading_enabled = True
    status.blocked_reason = None
    status.execution_intelligence = ei_status
    status.watchdog = watchdog

    session = MagicMock()
    session.total_cycles = 50
    session.total_fills = 5
    session.started_at_ns = _T0_NS
    session.elapsed_seconds = 100.0
    session.persisted_tca_count = 0
    session.registered_fill_count = 0
    status.runtime_status = MagicMock()
    status.runtime_status.session = session

    svc.status.return_value = status
    return svc


# ===================================================================
# Test classes
# ===================================================================


class TestNewEnums:
    """Phase 11A new enums: DataFreshness, EventSeverity, EventCategory extensions."""

    def test_data_freshness_values(self):
        assert DataFreshness.FRESH.value == "fresh"
        assert DataFreshness.STALE.value == "stale"
        assert DataFreshness.DEGRADED.value == "degraded"
        assert DataFreshness.UNAVAILABLE.value == "unavailable"
        assert len(DataFreshness) == 4

    def test_event_severity_values(self):
        assert EventSeverity.LOW.value == "low"
        assert EventSeverity.MEDIUM.value == "medium"
        assert EventSeverity.HIGH.value == "high"
        assert EventSeverity.CRITICAL.value == "critical"
        assert EventSeverity.UNKNOWN.value == "unknown"
        assert len(EventSeverity) == 5

    def test_event_category_new_values(self):
        """UNLOCK, GOVERNANCE, ETF must be present."""
        assert EventCategory.UNLOCK.value == "unlock"
        assert EventCategory.GOVERNANCE.value == "governance"
        assert EventCategory.ETF.value == "etf"
        # Original values still present
        assert EventCategory.MACRO.value == "macro"
        assert EventCategory.REGULATORY.value == "regulatory"
        assert EventCategory.PROTOCOL.value == "protocol"
        assert EventCategory.LISTING.value == "listing"

    def test_data_freshness_string_enum(self):
        assert DataFreshness("fresh") is DataFreshness.FRESH
        assert DataFreshness("stale") is DataFreshness.STALE

    def test_event_severity_string_enum(self):
        assert EventSeverity("critical") is EventSeverity.CRITICAL


class TestOptionsRegimeContract:
    """Options regime state contract construction and properties."""

    def test_normal_construction(self):
        state = _make_options_state()
        assert state.level == OptionsRegimeLevel.NORMAL
        assert state.is_available is True
        assert state.is_extreme is False
        assert state.implied_vol_30d == 0.55

    def test_extreme_construction(self):
        state = _make_options_state(level=OptionsRegimeLevel.EXTREME)
        assert state.is_extreme is True
        assert state.is_available is True

    def test_unavailable_construction(self):
        state = _make_options_state(
            level=OptionsRegimeLevel.UNAVAILABLE,
            implied_vol_30d=None,
            implied_vol_7d=None,
            skew_25d=None,
        )
        assert state.is_available is False
        assert state.is_extreme is False

    def test_suppressed_construction(self):
        state = _make_options_state(level=OptionsRegimeLevel.SUPPRESSED)
        assert state.level == OptionsRegimeLevel.SUPPRESSED
        assert state.is_available is True

    def test_frozen_immutable(self):
        state = _make_options_state()
        with pytest.raises(AttributeError):
            state.level = OptionsRegimeLevel.EXTREME  # type: ignore[misc]


class TestEventRegimeContract:
    """Event regime state contract construction and properties."""

    def test_quiet_construction(self):
        state = _make_event_state()
        assert state.level == EventRegimeLevel.QUIET
        assert state.is_available is True
        assert state.is_active_or_pending is False

    def test_pending_construction(self):
        state = _make_event_state(
            level=EventRegimeLevel.PENDING,
            event_category=EventCategory.MACRO,
            event_label="FOMC_2026_05",
            hours_until_event=4.0,
            impact_estimate=0.8,
        )
        assert state.is_active_or_pending is True
        assert state.event_category == EventCategory.MACRO

    def test_active_construction(self):
        state = _make_event_state(level=EventRegimeLevel.ACTIVE)
        assert state.is_active_or_pending is True

    def test_unavailable_construction(self):
        state = _make_event_state(level=EventRegimeLevel.UNAVAILABLE)
        assert state.is_available is False
        assert state.is_active_or_pending is False

    def test_new_event_categories(self):
        """Events with UNLOCK, GOVERNANCE, ETF categories."""
        for cat in (EventCategory.UNLOCK, EventCategory.GOVERNANCE, EventCategory.ETF):
            state = _make_event_state(
                level=EventRegimeLevel.PENDING,
                event_category=cat,
                event_label=f"test_{cat.value}",
            )
            assert state.event_category == cat
            assert state.event_label == f"test_{cat.value}"

    def test_aftermath_construction(self):
        state = _make_event_state(level=EventRegimeLevel.AFTERMATH)
        assert state.level == EventRegimeLevel.AFTERMATH
        assert state.is_active_or_pending is False


class TestOnChainRegimeContract:
    """On-chain regime state contract construction and properties."""

    def test_normal_construction(self):
        state = _make_on_chain_state()
        assert state.level == OnChainRegimeLevel.NORMAL
        assert state.is_available is True
        assert state.is_stress is False

    def test_stress_construction(self):
        state = _make_on_chain_state(level=OnChainRegimeLevel.STRESS)
        assert state.is_stress is True

    def test_whale_active_construction(self):
        state = _make_on_chain_state(level=OnChainRegimeLevel.WHALE_ACTIVE)
        assert state.level == OnChainRegimeLevel.WHALE_ACTIVE

    def test_unavailable_construction(self):
        state = _make_on_chain_state(
            level=OnChainRegimeLevel.UNAVAILABLE,
            exchange_net_flow_24h_usd=None,
            whale_transfer_count_24h=None,
        )
        assert state.is_available is False

    def test_accumulation_distribution(self):
        for level in (OnChainRegimeLevel.ACCUMULATION, OnChainRegimeLevel.DISTRIBUTION):
            state = _make_on_chain_state(level=level)
            assert state.is_available is True
            assert state.is_stress is False


class TestExternalRegimeDataPlane:
    """ExternalRegimeDataPlane core functionality."""

    def test_construction_default(self):
        plane = ExternalRegimeDataPlane()
        assert plane.staleness_threshold_s == 3600.0
        assert plane.options_state is None
        assert plane.event_state is None
        assert plane.on_chain_state is None

    def test_construction_custom_threshold(self):
        plane = ExternalRegimeDataPlane(staleness_threshold_s=1800.0)
        assert plane.staleness_threshold_s == 1800.0

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="staleness_threshold_s must be > 0"):
            ExternalRegimeDataPlane(staleness_threshold_s=0)
        with pytest.raises(ValueError, match="staleness_threshold_s must be > 0"):
            ExternalRegimeDataPlane(staleness_threshold_s=-100)

    def test_update_options(self):
        plane = ExternalRegimeDataPlane()
        state = _make_options_state()
        plane.update_options(state)
        assert plane.options_state is state

    def test_update_event(self):
        plane = ExternalRegimeDataPlane()
        state = _make_event_state()
        plane.update_event(state)
        assert plane.event_state is state

    def test_update_on_chain(self):
        plane = ExternalRegimeDataPlane()
        state = _make_on_chain_state()
        plane.update_on_chain(state)
        assert plane.on_chain_state is state

    def test_reset(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        plane.update_event(_make_event_state())
        plane.update_on_chain(_make_on_chain_state())
        plane.reset()
        assert plane.options_state is None
        assert plane.event_state is None
        assert plane.on_chain_state is None


class TestSnapshotFreshness:
    """Freshness / staleness / unavailable / degraded truth handling."""

    def test_all_unavailable_when_empty(self):
        """No data → all dimensions UNAVAILABLE."""
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        assert snap.options is None
        assert snap.event is None
        assert snap.on_chain is None
        assert snap.options_freshness.freshness == DataFreshness.UNAVAILABLE
        assert snap.event_freshness.freshness == DataFreshness.UNAVAILABLE
        assert snap.on_chain_freshness.freshness == DataFreshness.UNAVAILABLE
        assert snap.available_dimensions == ()
        assert set(snap.unavailable_dimensions) == {"options", "event", "on_chain"}
        assert snap.evidence_sufficient is False
        assert snap.any_extreme is False

    def test_fresh_when_within_threshold(self):
        """Data within staleness threshold → FRESH."""
        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        now = _T0_NS + 1800 * _NS_PER_S  # 30 min later
        snap = plane.snapshot(now)
        assert snap.options_freshness.freshness == DataFreshness.FRESH
        assert snap.options_freshness.staleness_seconds == pytest.approx(1800.0)
        assert snap.options_freshness.source == "deribit"
        assert "options" in snap.available_dimensions

    def test_stale_when_past_threshold(self):
        """Data past staleness threshold → STALE."""
        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        now = _T0_NS + 7200 * _NS_PER_S  # 2 hours later
        snap = plane.snapshot(now)
        assert snap.options_freshness.freshness == DataFreshness.STALE
        assert snap.options_freshness.staleness_seconds == pytest.approx(7200.0)
        # Stale dimensions tracked
        assert "options" in snap.stale_dimensions
        # Still in available (has data, but stale)
        assert "options" in snap.available_dimensions

    def test_unavailable_level_reports_unavailable(self):
        """State with UNAVAILABLE level → freshness UNAVAILABLE regardless of time."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(
            _make_options_state(
                level=OptionsRegimeLevel.UNAVAILABLE,
                implied_vol_30d=None,
                implied_vol_7d=None,
                skew_25d=None,
            )
        )
        snap = plane.snapshot(_T0_NS)
        assert snap.options_freshness.freshness == DataFreshness.UNAVAILABLE
        assert "options" in snap.unavailable_dimensions

    def test_degraded_when_evidence_gaps(self):
        """Options with no IV data → DEGRADED (not UNAVAILABLE)."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(
            _make_options_state(
                implied_vol_30d=None,
                implied_vol_7d=None,
                skew_25d=None,
            )
        )
        snap = plane.snapshot(_T0_NS)
        assert snap.options_freshness.freshness == DataFreshness.DEGRADED
        assert "options" in snap.available_dimensions

    def test_on_chain_degraded_when_no_flow_data(self):
        """On-chain with no flow/whale data → DEGRADED."""
        plane = ExternalRegimeDataPlane()
        plane.update_on_chain(
            _make_on_chain_state(
                exchange_net_flow_24h_usd=None,
                whale_transfer_count_24h=None,
            )
        )
        snap = plane.snapshot(_T0_NS)
        assert snap.on_chain_freshness.freshness == DataFreshness.DEGRADED

    def test_event_not_degraded_without_label(self):
        """Events don't have degradation concept for missing optional fields."""
        plane = ExternalRegimeDataPlane()
        plane.update_event(_make_event_state(event_label=None))
        snap = plane.snapshot(_T0_NS)
        assert snap.event_freshness.freshness == DataFreshness.FRESH

    def test_mixed_freshness(self):
        """Different dimensions can have different freshness."""
        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        plane.update_event(_make_event_state(snapshot_ns=_T0_NS - 5000 * _NS_PER_S))
        # on_chain not updated → UNAVAILABLE
        now = _T0_NS + 1000 * _NS_PER_S
        snap = plane.snapshot(now)
        assert snap.options_freshness.freshness == DataFreshness.FRESH
        assert snap.event_freshness.freshness == DataFreshness.STALE
        assert snap.on_chain_freshness.freshness == DataFreshness.UNAVAILABLE

    def test_staleness_seconds_nonnegative(self):
        """If now_ns < update_ns (clock skew), staleness clamped to 0."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS + 100 * _NS_PER_S))
        snap = plane.snapshot(_T0_NS)  # earlier than update
        assert snap.options_freshness.staleness_seconds == 0.0
        assert snap.options_freshness.freshness == DataFreshness.FRESH


class TestExternalRegimeAggregates:
    """Aggregate assessments: extreme, high-risk, evidence sufficiency."""

    def test_no_extreme_normal_data(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.NORMAL))
        plane.update_event(_make_event_state(level=EventRegimeLevel.QUIET))
        plane.update_on_chain(_make_on_chain_state(level=OnChainRegimeLevel.NORMAL))
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is False
        assert snap.high_risk_regime_present is False

    def test_extreme_options(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.EXTREME))
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is True
        assert snap.high_risk_regime_present is True

    def test_extreme_event_pending(self):
        plane = ExternalRegimeDataPlane()
        plane.update_event(
            _make_event_state(
                level=EventRegimeLevel.PENDING,
                event_category=EventCategory.MACRO,
            )
        )
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is True

    def test_extreme_on_chain_stress(self):
        plane = ExternalRegimeDataPlane()
        plane.update_on_chain(_make_on_chain_state(level=OnChainRegimeLevel.STRESS))
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is True
        assert snap.high_risk_regime_present is True

    def test_elevated_risk_without_extreme(self):
        """ELEVATED options = high_risk but not any_extreme."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.ELEVATED))
        plane.update_event(_make_event_state(level=EventRegimeLevel.QUIET))
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is False
        assert snap.high_risk_regime_present is True

    def test_whale_active_is_elevated_risk(self):
        plane = ExternalRegimeDataPlane()
        plane.update_on_chain(_make_on_chain_state(level=OnChainRegimeLevel.WHALE_ACTIVE))
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is False
        assert snap.high_risk_regime_present is True

    def test_evidence_sufficient_with_two_fresh(self):
        """At least 2 of 3 fresh → sufficient."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        plane.update_event(_make_event_state(snapshot_ns=_T0_NS))
        snap = plane.snapshot(_T0_NS)
        assert snap.evidence_sufficient is True

    def test_evidence_insufficient_with_one_fresh(self):
        """Only 1 of 3 fresh → insufficient."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        snap = plane.snapshot(_T0_NS)
        assert snap.evidence_sufficient is False

    def test_evidence_insufficient_all_empty(self):
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        assert snap.evidence_sufficient is False

    def test_any_unavailable_critical(self):
        """If any dimension is unavailable, any_unavailable_critical is True."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        plane.update_event(_make_event_state())
        # on_chain not set → unavailable
        snap = plane.snapshot(_T0_NS)
        assert snap.any_unavailable_critical is True

    def test_no_unavailable_critical_when_all_present(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        plane.update_event(_make_event_state())
        plane.update_on_chain(_make_on_chain_state())
        snap = plane.snapshot(_T0_NS)
        assert snap.any_unavailable_critical is False

    def test_regime_summary_no_data(self):
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        assert "No external regime data available" in snap.regime_summary

    def test_regime_summary_extreme(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.EXTREME))
        snap = plane.snapshot(_T0_NS)
        assert "EXTREME" in snap.regime_summary

    def test_regime_summary_elevated(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.ELEVATED))
        plane.update_event(_make_event_state())
        snap = plane.snapshot(_T0_NS)
        assert "Elevated" in snap.regime_summary


class TestCompositeRegimeBackcompat:
    """Backward-compatible CompositeRegimeState from the data plane."""

    def test_composite_regime_empty(self):
        plane = ExternalRegimeDataPlane()
        comp = plane.composite_regime(_T0_NS)
        assert comp.options is None
        assert comp.event is None
        assert comp.on_chain is None
        assert comp.any_extreme is False
        assert comp.available_dimensions == []
        assert set(comp.unavailable_dimensions) == {"options", "event", "on_chain"}

    def test_composite_regime_with_data(self):
        plane = ExternalRegimeDataPlane()
        opt = _make_options_state(level=OptionsRegimeLevel.EXTREME)
        plane.update_options(opt)
        comp = plane.composite_regime(_T0_NS)
        assert comp.options is opt
        assert comp.any_extreme is True
        assert "options" in comp.available_dimensions


class TestSerialization:
    """Serialization / deserialization roundtrip for all new models."""

    def test_dimension_freshness_roundtrip(self):
        f = DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=_T0_NS,
            staleness_seconds=42.5,
            source="deribit",
        )
        d = dimension_freshness_to_dict(f)
        f2 = dimension_freshness_from_dict(d)
        assert f2.freshness == f.freshness
        assert f2.last_update_ns == f.last_update_ns
        assert f2.staleness_seconds == f.staleness_seconds
        assert f2.source == f.source

    def test_dimension_freshness_unavailable_roundtrip(self):
        f = DimensionFreshness(
            freshness=DataFreshness.UNAVAILABLE,
            last_update_ns=None,
            staleness_seconds=None,
            source=None,
        )
        d = dimension_freshness_to_dict(f)
        f2 = dimension_freshness_from_dict(d)
        assert f2.freshness == DataFreshness.UNAVAILABLE
        assert f2.last_update_ns is None

    def test_dimension_freshness_malformed_raises(self):
        with pytest.raises(ValueError, match="Malformed DimensionFreshness"):
            dimension_freshness_from_dict({"bad": "data"})

    def test_external_regime_snapshot_roundtrip(self):
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        plane.update_event(_make_event_state())
        plane.update_on_chain(_make_on_chain_state())
        snap = plane.snapshot(_T0_NS)

        d = external_regime_snapshot_to_dict(snap)
        snap2 = external_regime_snapshot_from_dict(d)

        assert snap2.snapshot_ns == snap.snapshot_ns
        assert snap2.any_extreme == snap.any_extreme
        assert snap2.high_risk_regime_present == snap.high_risk_regime_present
        assert snap2.evidence_sufficient == snap.evidence_sufficient
        assert snap2.available_dimensions == snap.available_dimensions
        assert snap2.options_freshness.freshness == snap.options_freshness.freshness

    def test_external_regime_snapshot_json_roundtrip(self):
        """Full JSON serialize → deserialize roundtrip."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.ELEVATED))
        snap = plane.snapshot(_T0_NS)

        json_str = json.dumps(external_regime_snapshot_to_dict(snap))
        d = json.loads(json_str)
        snap2 = external_regime_snapshot_from_dict(d)
        assert snap2.options is not None
        assert snap2.options.level == OptionsRegimeLevel.ELEVATED

    def test_external_regime_snapshot_empty_roundtrip(self):
        """Roundtrip with no data loaded."""
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        d = external_regime_snapshot_to_dict(snap)
        snap2 = external_regime_snapshot_from_dict(d)
        assert snap2.options is None
        assert snap2.event is None
        assert snap2.on_chain is None
        assert snap2.options_freshness.freshness == DataFreshness.UNAVAILABLE

    def test_external_regime_snapshot_malformed_raises(self):
        with pytest.raises(ValueError, match="Malformed ExternalRegimeSnapshot"):
            external_regime_snapshot_from_dict({"bad": "data"})

    def test_composite_regime_serialization_with_new_categories(self):
        """CompositeRegimeState serialization works with new EventCategory values."""
        event = _make_event_state(
            level=EventRegimeLevel.PENDING,
            event_category=EventCategory.ETF,
            event_label="spot_etf_ruling",
        )
        comp = CompositeRegimeState(snapshot_ns=_T0_NS, event=event)
        d = composite_regime_to_dict(comp)
        comp2 = composite_regime_from_dict(d)
        assert comp2.event is not None
        assert comp2.event.event_category == EventCategory.ETF
        assert comp2.event.event_label == "spot_etf_ruling"


class TestOrchestratorIntegration:
    """Integration of external regime into ServiceOrchestrator."""

    def test_orchestrator_without_regime_plane(self):
        """No regime plane → external_regime is None in snapshot."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert snap.external_regime is None
        assert snap.evidence.external_regime_available is False
        assert snap.evidence.external_regime_fresh is False
        assert snap.evidence.external_regime_has_high_risk is False

    def test_orchestrator_with_empty_regime_plane(self):
        """Regime plane configured but no data → external_regime not None but all unavailable."""
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.operator_snapshot()
        assert snap.external_regime is not None
        assert snap.external_regime.evidence_sufficient is False
        assert snap.evidence.external_regime_available is False

    def test_orchestrator_with_fresh_regime_data(self):
        """Regime plane with fresh data → available + fresh in evidence."""
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        plane.update_event(_make_event_state(snapshot_ns=_T0_NS))
        plane.update_on_chain(_make_on_chain_state(snapshot_ns=_T0_NS))
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.operator_snapshot()
        assert snap.external_regime is not None
        assert snap.evidence.external_regime_available is True
        assert snap.evidence.external_regime_fresh is True
        assert snap.evidence.external_regime_has_high_risk is False

    def test_orchestrator_with_high_risk_regime(self):
        """Extreme options → high_risk in evidence."""
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.EXTREME, snapshot_ns=_T0_NS))
        plane.update_event(_make_event_state(snapshot_ns=_T0_NS))
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.operator_snapshot()
        assert snap.evidence.external_regime_has_high_risk is True
        assert snap.external_regime.any_extreme is True

    def test_orchestrator_evidence_summary_includes_regime(self):
        """Evidence summary mentions missing regime data."""
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        snap = orch.operator_snapshot()
        assert "external regime" in snap.evidence.summary.lower()

    def test_orchestrator_evidence_summary_high_risk(self):
        """Evidence summary mentions high-risk regime conditions."""
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.EXTREME, snapshot_ns=_T0_NS))
        plane.update_event(_make_event_state(snapshot_ns=_T0_NS))
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.operator_snapshot()
        assert "high-risk" in snap.evidence.summary.lower()

    def test_external_regime_plane_property(self):
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        assert orch.external_regime_plane is plane

    def test_external_regime_plane_none(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.external_regime_plane is None


class TestReportingAPI:
    """Reporting API with external regime."""

    def test_external_regime_snapshot_method(self):
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.external_regime_snapshot()
        assert snap is not None
        assert snap.options is not None

    def test_external_regime_snapshot_none_without_plane(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.external_regime_snapshot() is None

    def test_external_regime_dict_method(self):
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        d = orch.external_regime_dict()
        assert d is not None
        assert "options" in d
        assert "options_freshness" in d

    def test_external_regime_dict_none_without_plane(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        assert orch.external_regime_dict() is None

    def test_combined_status_dict_includes_regime(self):
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        d = orch.combined_status_dict()
        assert "external_regime" in d
        assert d["external_regime"] is not None

    def test_combined_status_dict_regime_none_without_plane(self):
        svc = _make_mock_service()
        orch = ServiceOrchestrator(service=svc)
        d = orch.combined_status_dict()
        assert d["external_regime"] is None

    def test_evidence_dict_includes_regime_fields(self):
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        plane.update_event(_make_event_state())
        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        d = orch.combined_status_dict()
        ev = d["evidence"]
        assert "external_regime_available" in ev
        assert "external_regime_fresh" in ev
        assert "external_regime_has_high_risk" in ev


class TestSerializationExtensions:
    """Serialization helpers for Phase 11A extended models."""

    def test_evidence_sufficiency_to_dict_new_fields(self):
        state = EvidenceSufficiencyState(
            campaign_evidence_available=True,
            review_evidence_available=True,
            execution_calibration_available=True,
            promotion_evidence_sufficient=True,
            insufficient_reasons=(),
            summary="OK",
            external_regime_available=True,
            external_regime_fresh=True,
            external_regime_has_high_risk=False,
        )
        d = evidence_sufficiency_state_to_dict(state)
        assert d["external_regime_available"] is True
        assert d["external_regime_fresh"] is True
        assert d["external_regime_has_high_risk"] is False

    def test_evidence_sufficiency_defaults(self):
        """New fields default to False for backward compat."""
        state = EvidenceSufficiencyState(
            campaign_evidence_available=False,
            review_evidence_available=False,
            execution_calibration_available=False,
            promotion_evidence_sufficient=False,
            insufficient_reasons=(),
            summary="test",
        )
        assert state.external_regime_available is False
        assert state.external_regime_fresh is False
        assert state.external_regime_has_high_risk is False

    def test_operator_snapshot_with_regime_serialization(self):
        """OperatorSnapshot with external_regime serializes correctly."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state())
        ext = plane.snapshot(_T0_NS)

        snap = OperatorSnapshot(
            service_mode="running",
            trading_enabled=True,
            blocked_reason=None,
            ei_available=True,
            ei_degraded=False,
            ei_degraded_reasons=(),
            campaign=None,
            review=None,
            readiness_level="paper_live",
            readiness_is_supportive=True,
            evidence=EvidenceSufficiencyState(
                campaign_evidence_available=False,
                review_evidence_available=False,
                execution_calibration_available=False,
                promotion_evidence_sufficient=False,
                insufficient_reasons=(),
                summary="test",
            ),
            provisional_recommendation=None,
            recommendation_summary="No review.",
            external_regime=ext,
        )
        d = operator_snapshot_to_dict(snap)
        assert d["external_regime"] is not None
        assert "options_freshness" in d["external_regime"]

    def test_operator_snapshot_without_regime_serialization(self):
        """OperatorSnapshot without external_regime serializes as None."""
        snap = OperatorSnapshot(
            service_mode="running",
            trading_enabled=True,
            blocked_reason=None,
            ei_available=True,
            ei_degraded=False,
            ei_degraded_reasons=(),
            campaign=None,
            review=None,
            readiness_level="paper_live",
            readiness_is_supportive=True,
            evidence=EvidenceSufficiencyState(
                campaign_evidence_available=False,
                review_evidence_available=False,
                execution_calibration_available=False,
                promotion_evidence_sufficient=False,
                insufficient_reasons=(),
                summary="test",
            ),
            provisional_recommendation=None,
            recommendation_summary="No review.",
        )
        d = operator_snapshot_to_dict(snap)
        assert d["external_regime"] is None


class TestNoFakeData:
    """No-fake-data behavior: plane does not fabricate anything."""

    def test_empty_plane_stays_unavailable(self):
        """Never silently becomes 'normal' or 'fresh' without updates."""
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        assert all(
            f.freshness == DataFreshness.UNAVAILABLE
            for f in (
                snap.options_freshness,
                snap.event_freshness,
                snap.on_chain_freshness,
            )
        )
        assert "No external regime data available" in snap.regime_summary

    def test_stale_does_not_appear_fresh(self):
        """Stale data never silently degrades to fresh."""
        plane = ExternalRegimeDataPlane(staleness_threshold_s=100)
        plane.update_options(_make_options_state(snapshot_ns=_T0_NS))
        now = _T0_NS + 200 * _NS_PER_S
        snap = plane.snapshot(now)
        assert snap.options_freshness.freshness == DataFreshness.STALE
        assert snap.options_freshness.freshness != DataFreshness.FRESH

    def test_unavailable_level_never_becomes_normal(self):
        """UNAVAILABLE level reports UNAVAILABLE freshness even if timestamp is fresh."""
        plane = ExternalRegimeDataPlane()
        plane.update_event(_make_event_state(level=EventRegimeLevel.UNAVAILABLE))
        snap = plane.snapshot(_T0_NS)
        assert snap.event_freshness.freshness == DataFreshness.UNAVAILABLE

    def test_no_data_fabrication_in_aggregates(self):
        """Aggregates don't claim extreme/risk when nothing is loaded."""
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        assert snap.any_extreme is False
        assert snap.high_risk_regime_present is False
        # But unavailable_critical IS True (missing is flagged)
        assert snap.any_unavailable_critical is True

    def test_partial_data_does_not_claim_sufficient(self):
        """1 of 3 dimensions → evidence_sufficient is False."""
        plane = ExternalRegimeDataPlane()
        plane.update_event(_make_event_state())
        snap = plane.snapshot(_T0_NS)
        assert snap.evidence_sufficient is False


class TestEdgeCases:
    """Edge cases and boundary conditions."""

    def test_snapshot_frozen(self):
        """ExternalRegimeSnapshot is frozen."""
        plane = ExternalRegimeDataPlane()
        snap = plane.snapshot(_T0_NS)
        with pytest.raises(AttributeError):
            snap.any_extreme = True  # type: ignore[misc]

    def test_dimension_freshness_frozen(self):
        f = DimensionFreshness(
            freshness=DataFreshness.FRESH,
            last_update_ns=_T0_NS,
            staleness_seconds=0.0,
            source="test",
        )
        with pytest.raises(AttributeError):
            f.freshness = DataFreshness.STALE  # type: ignore[misc]

    def test_overwrite_state(self):
        """Updating a dimension replaces the previous state."""
        plane = ExternalRegimeDataPlane()
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.NORMAL))
        plane.update_options(_make_options_state(level=OptionsRegimeLevel.EXTREME))
        snap = plane.snapshot(_T0_NS)
        assert snap.options is not None
        assert snap.options.level == OptionsRegimeLevel.EXTREME

    def test_full_pipeline_end_to_end(self):
        """Full end-to-end: plane → orchestrator → snapshot → serialization."""
        svc = _make_mock_service()
        plane = ExternalRegimeDataPlane(staleness_threshold_s=3600)

        plane.update_options(_make_options_state(level=OptionsRegimeLevel.ELEVATED, snapshot_ns=_T0_NS))
        plane.update_event(
            _make_event_state(
                level=EventRegimeLevel.PENDING,
                event_category=EventCategory.ETF,
                event_label="spot_etf_ruling",
                snapshot_ns=_T0_NS,
            )
        )
        plane.update_on_chain(_make_on_chain_state(level=OnChainRegimeLevel.WHALE_ACTIVE, snapshot_ns=_T0_NS))

        orch = ServiceOrchestrator(service=svc, external_regime_plane=plane)
        snap = orch.operator_snapshot()

        # External regime present and assessed
        assert snap.external_regime is not None
        assert snap.external_regime.any_extreme is True  # pending event
        assert snap.external_regime.high_risk_regime_present is True
        assert snap.external_regime.evidence_sufficient is True

        # Evidence reflects external regime
        assert snap.evidence.external_regime_available is True
        assert snap.evidence.external_regime_fresh is True
        assert snap.evidence.external_regime_has_high_risk is True

        # Serialization roundtrip
        d = orch.combined_status_dict()
        assert d["external_regime"]["any_extreme"] is True
        ext_d = d["external_regime"]
        snap2 = external_regime_snapshot_from_dict(ext_d)
        assert snap2.any_extreme is True
        assert snap2.options is not None
        assert snap2.options.level == OptionsRegimeLevel.ELEVATED

        # JSON roundtrip
        json_str = json.dumps(d)
        d2 = json.loads(json_str)
        assert d2["external_regime"]["evidence_sufficient"] is True
