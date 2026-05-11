"""Phase 11C tests — external regime ingestion, persistence, and restore.

Covers:
  1. Deterministic update API for options / event / on-chain.
  2. Explicit rejection of malformed / stale / contradictory updates.
  3. Overwrite semantics and provenance tracking.
  4. Bounded update history.
  5. Persistence / restore roundtrip and malformed restore fail-closed.
  6. Staleness truth after restore.
  7. Partial-dimension truthfulness.
  8. Service-level lifecycle APIs on ServiceOrchestrator.
  9. Campaign / review compatibility regression.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_core.execution.regime_contracts import (
    DataFreshness,
    EventCategory,
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.external_regime import (
    ExternalRegimeDataPlane,
    ExternalRegimeManager,
    ExternalRegimeStateCorruptError,
    ExternalRegimeUpdateStatus,
)
from crypto_core.service.models import (
    ExecutionIntelligenceStatus,
    QueuePressure,
    QueueSnapshot,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.service_orchestrator import ServiceOrchestrator
from crypto_core.session.models import PaperSessionStatus

_NS_PER_S = 1_000_000_000
_T0_NS = 1_700_000_000 * _NS_PER_S


def _make_options_state(
    *,
    snapshot_ns: int = _T0_NS,
    level: OptionsRegimeLevel = OptionsRegimeLevel.NORMAL,
    source: str = "operator.manual.options",
    symbol: str = "BTCUSDT",
    implied_vol_30d: float | None = 0.55,
    implied_vol_7d: float | None = 0.60,
) -> OptionsRegimeState:
    return OptionsRegimeState(
        symbol=symbol,
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        implied_vol_30d=implied_vol_30d,
        implied_vol_7d=implied_vol_7d,
    )


def _make_event_state(
    *,
    snapshot_ns: int = _T0_NS,
    level: EventRegimeLevel = EventRegimeLevel.QUIET,
    source: str = "operator.manual.event",
    event_label: str | None = "FOMC_2026_05",
) -> EventRegimeState:
    return EventRegimeState(
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        event_category=EventCategory.MACRO,
        event_label=event_label,
        hours_until_event=4.0 if level == EventRegimeLevel.PENDING else None,
        impact_estimate=0.8 if level in (EventRegimeLevel.PENDING, EventRegimeLevel.ACTIVE) else 0.1,
    )


def _make_on_chain_state(
    *,
    snapshot_ns: int = _T0_NS,
    level: OnChainRegimeLevel = OnChainRegimeLevel.NORMAL,
    source: str = "operator.manual.on_chain",
    symbol: str = "BTC",
) -> OnChainRegimeState:
    return OnChainRegimeState(
        symbol=symbol,
        level=level,
        snapshot_ns=snapshot_ns,
        source=source,
        exchange_net_flow_24h_usd=25_000_000.0,
        whale_transfer_count_24h=9,
    )


def _make_service_status(*, last_event_time_ns: int = _T0_NS) -> ServiceStatus:
    session = PaperSessionStatus(
        session_id="phase11c",
        mode="running",
        start_time_ns=_T0_NS,
        current_cycle_time_ns=last_event_time_ns,
        total_cycles=120,
        total_fills=12,
        approved_cycles=110,
        blocked_cycles=8,
        failed_cycles=2,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=1,
        nav_usd=10_250.0,
        gross_exposure_pct=12.0,
        net_exposure_pct=4.0,
        last_cycle_approved=True,
        last_error=None,
        trading_blocked=False,
        route_block_count=0,
        route_abstain_count=0,
        pending_markout_count=0,
        persisted_tca_count=2,
        persisted_attribution_count=1,
        registered_fill_count=2,
    )
    runtime = RuntimeStatus(
        session_status=session,
        total_event_count=500,
        total_trigger_count=120,
        total_suppressed_count=5,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": last_event_time_ns},
        recovery_in_progress=False,
        blocked_reason=None,
    )
    queue = QueueSnapshot(
        current_depth=4,
        max_size=100,
        pressure=QueuePressure.NORMAL,
        total_enqueued=1000,
        total_dropped=0,
        total_processed=996,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=last_event_time_ns,
        last_cycle_time_ns=last_event_time_ns,
        seconds_since_event=0.5,
        seconds_since_cycle=0.5,
        stall_detected=False,
        stall_threshold_s=60.0,
    )
    symbol = SymbolHealth(
        symbol="BTCUSDT",
        exchange="binance",
        feed_connected=True,
        feed_ready=True,
        feed_key="binance:BTCUSDT",
        last_event_time_ns=last_event_time_ns,
        blocked=False,
        block_reason=None,
    )
    ei = ExecutionIntelligenceStatus(
        mode="optional",
        route_binding_enabled=True,
        tca_loop_enabled=True,
        tca_store_available=True,
        replay_dedup_bootstrapped=True,
        degraded=False,
        degraded_reasons=(),
    )
    return ServiceStatus(
        service_mode="running",
        runtime_status=runtime,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(symbol,),
        symbol_count=1,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
        total_service_restarts=0,
        execution_intelligence=ei,
    )


def _make_service(*, last_event_time_ns: int = _T0_NS) -> MagicMock:
    service = MagicMock()
    service.status.return_value = _make_service_status(last_event_time_ns=last_event_time_ns)
    return service


class TestExternalRegimeManagerUpdateApi:
    def test_update_options_accepts_and_tracks_provenance(self):
        manager = ExternalRegimeManager(plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0))

        record = manager.update_options(
            _make_options_state(snapshot_ns=_T0_NS),
            received_at_ns=_T0_NS + 5 * _NS_PER_S,
        )

        assert record.status is ExternalRegimeUpdateStatus.ACCEPTED
        assert record.accepted is True
        assert record.dimension == "options"
        assert record.source_label == "operator.manual.options"
        assert record.state_snapshot_ns == _T0_NS
        assert record.freshness is DataFreshness.FRESH
        assert record.replaced_existing is False

    def test_update_event_accepts(self):
        manager = ExternalRegimeManager()

        record = manager.update_event(_make_event_state(level=EventRegimeLevel.PENDING))

        assert record.accepted is True
        assert record.dimension == "event"
        assert record.level == EventRegimeLevel.PENDING.value

    def test_update_on_chain_accepts(self):
        manager = ExternalRegimeManager()

        record = manager.update_on_chain(_make_on_chain_state(level=OnChainRegimeLevel.STRESS))

        assert record.accepted is True
        assert record.dimension == "on_chain"
        assert record.level == OnChainRegimeLevel.STRESS.value

    def test_invalid_type_is_rejected(self):
        manager = ExternalRegimeManager()

        record = manager.update_options(  # type: ignore[arg-type]
            _make_event_state(),
            received_at_ns=_T0_NS,
        )

        assert record.accepted is False
        assert record.status is ExternalRegimeUpdateStatus.REJECTED_INVALID
        assert "invalid_type" in record.reason

    def test_missing_source_is_rejected(self):
        manager = ExternalRegimeManager()

        record = manager.update_options(
            _make_options_state(source=""),
            received_at_ns=_T0_NS,
        )

        assert record.accepted is False
        assert record.status is ExternalRegimeUpdateStatus.REJECTED_INVALID
        assert record.reason == "missing_source_label"

    def test_older_update_is_rejected_and_state_preserved(self):
        manager = ExternalRegimeManager()
        newer = _make_options_state(snapshot_ns=_T0_NS + 10 * _NS_PER_S)
        older = _make_options_state(snapshot_ns=_T0_NS)

        accepted = manager.update_options(newer, received_at_ns=_T0_NS + 10 * _NS_PER_S)
        rejected = manager.update_options(older, received_at_ns=_T0_NS + 12 * _NS_PER_S)
        snap = manager.snapshot(_T0_NS + 12 * _NS_PER_S)

        assert accepted.accepted is True
        assert rejected.accepted is False
        assert rejected.status is ExternalRegimeUpdateStatus.REJECTED_STALE
        assert snap.options is not None
        assert snap.options.snapshot_ns == newer.snapshot_ns

    def test_same_timestamp_different_payload_is_rejected(self):
        manager = ExternalRegimeManager()
        first = _make_options_state(snapshot_ns=_T0_NS, level=OptionsRegimeLevel.NORMAL)
        second = _make_options_state(snapshot_ns=_T0_NS, level=OptionsRegimeLevel.EXTREME)

        manager.update_options(first, received_at_ns=_T0_NS)
        rejected = manager.update_options(second, received_at_ns=_T0_NS + _NS_PER_S)

        assert rejected.accepted is False
        assert rejected.status is ExternalRegimeUpdateStatus.REJECTED_INVALID
        assert rejected.reason == "contradictory_same_timestamp"

    def test_newer_update_marks_replaced_existing(self):
        manager = ExternalRegimeManager()
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)

        replaced = manager.update_options(
            _make_options_state(snapshot_ns=_T0_NS + 5 * _NS_PER_S, level=OptionsRegimeLevel.ELEVATED),
            received_at_ns=_T0_NS + 5 * _NS_PER_S,
        )

        assert replaced.accepted is True
        assert replaced.replaced_existing is True
        assert replaced.level == OptionsRegimeLevel.ELEVATED.value

    def test_partial_dimension_truth_is_explicit(self):
        manager = ExternalRegimeManager(plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0))
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)

        snap = manager.snapshot(_T0_NS + 10 * _NS_PER_S)

        assert snap.available_dimensions == ("options",)
        assert snap.unavailable_dimensions == ("event", "on_chain")
        assert snap.evidence_sufficient is False
        assert snap.any_unavailable_critical is True

    def test_history_is_bounded(self):
        manager = ExternalRegimeManager(history_limit=2)
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)
        manager.update_event(_make_event_state(snapshot_ns=_T0_NS + _NS_PER_S), received_at_ns=_T0_NS + _NS_PER_S)
        manager.update_on_chain(
            _make_on_chain_state(snapshot_ns=_T0_NS + 2 * _NS_PER_S),
            received_at_ns=_T0_NS + 2 * _NS_PER_S,
        )

        history = manager.recent_update_history()

        assert len(history) == 2
        assert history[0].dimension == "event"
        assert history[1].dimension == "on_chain"

    def test_reset_clears_state_explicitly(self):
        manager = ExternalRegimeManager()
        manager.update_options(_make_options_state(), received_at_ns=_T0_NS)

        record = manager.reset(received_at_ns=_T0_NS + _NS_PER_S)
        snap = manager.snapshot(_T0_NS + _NS_PER_S)

        assert record.status is ExternalRegimeUpdateStatus.RESET
        assert record.replaced_existing is True
        assert snap.available_dimensions == ()
        assert snap.unavailable_dimensions == ("options", "event", "on_chain")


class TestExternalRegimeManagerPersistence:
    def test_persistence_roundtrip_restores_state_and_history(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        manager = ExternalRegimeManager(
            plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0),
            evidence_store=store,
            history_limit=4,
        )
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)
        manager.update_event(
            _make_event_state(snapshot_ns=_T0_NS + _NS_PER_S, level=EventRegimeLevel.PENDING),
            received_at_ns=_T0_NS + _NS_PER_S,
        )

        restored = ExternalRegimeManager(evidence_store=store)
        assert restored.restore_state() is True

        snap = restored.snapshot(_T0_NS + 2 * _NS_PER_S)
        assert snap.options is not None
        assert snap.event is not None
        assert restored.latest_update is not None
        assert restored.latest_update.dimension == "event"
        assert len(restored.recent_update_history()) == 2
        assert restored.persistence_state().restored_from_snapshot is True

    def test_restore_missing_snapshot_returns_false(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        manager = ExternalRegimeManager(evidence_store=store)

        assert manager.restore_state() is False

    def test_restore_malformed_snapshot_fails_closed(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.save_snapshot("external_regime_state", {"bad": "data"})
        manager = ExternalRegimeManager(evidence_store=store)

        with pytest.raises(ExternalRegimeStateCorruptError, match="missing required fields"):
            manager.restore_state()

    def test_stale_truth_survives_restore(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        manager = ExternalRegimeManager(
            plane=ExternalRegimeDataPlane(staleness_threshold_s=30.0),
            evidence_store=store,
        )
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)

        restored = ExternalRegimeManager(evidence_store=store)
        assert restored.restore_state() is True

        snap = restored.snapshot(_T0_NS + 45 * _NS_PER_S)
        assert snap.options_freshness.freshness is DataFreshness.STALE
        assert snap.stale_dimensions == ("options",)

    def test_status_dict_exposes_snapshot_latest_history_and_persistence(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        manager = ExternalRegimeManager(evidence_store=store)
        manager.update_options(_make_options_state(snapshot_ns=_T0_NS), received_at_ns=_T0_NS)

        status = manager.status_dict(_T0_NS + _NS_PER_S)

        assert status["current_snapshot"]["options"]["source"] == "operator.manual.options"
        assert status["latest_update"]["dimension"] == "options"
        assert len(status["recent_history"]) == 1
        assert status["persistence"]["snapshot_present"] is True


class TestServiceOrchestratorExternalRegimeLifecycle:
    def test_service_level_updates_use_watchdog_time_when_not_provided(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        service = _make_service(last_event_time_ns=_T0_NS + 9 * _NS_PER_S)
        orchestrator = ServiceOrchestrator(
            service=service,
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0),
        )

        record = orchestrator.update_options_regime(_make_options_state(snapshot_ns=_T0_NS))

        assert record.received_at_ns == _T0_NS + 9 * _NS_PER_S
        assert orchestrator.external_regime_latest_update() == record
        assert len(orchestrator.external_regime_update_history()) == 1

    def test_external_regime_lifecycle_dict_is_available(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        orchestrator = ServiceOrchestrator(
            service=_make_service(),
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(),
        )
        orchestrator.update_event_regime(_make_event_state())

        lifecycle = orchestrator.external_regime_lifecycle_dict()

        assert lifecycle is not None
        assert lifecycle["latest_update"]["dimension"] == "event"
        assert lifecycle["persistence"]["snapshot_present"] is True

    def test_restore_external_regime_reconstructs_snapshot(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        orch1 = ServiceOrchestrator(
            service=_make_service(),
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0),
        )
        orch1.update_external_regime(
            options=_make_options_state(snapshot_ns=_T0_NS),
            event=_make_event_state(snapshot_ns=_T0_NS),
        )

        orch2 = ServiceOrchestrator(
            service=_make_service(last_event_time_ns=_T0_NS + 10 * _NS_PER_S),
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(),
        )

        assert orch2.restore_external_regime() is True
        snap = orch2.external_regime_snapshot()
        assert snap is not None
        assert snap.options is not None
        assert snap.event is not None

    def test_reset_external_regime_clears_snapshot(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        orch = ServiceOrchestrator(
            service=_make_service(),
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(),
        )
        orch.update_options_regime(_make_options_state())

        record = orch.reset_external_regime(reason="operator_clear")
        snap = orch.external_regime_snapshot()

        assert record.status is ExternalRegimeUpdateStatus.RESET
        assert snap is not None
        assert snap.available_dimensions == ()

    def test_methods_fail_without_external_regime_manager(self):
        orch = ServiceOrchestrator(service=_make_service())

        with pytest.raises(RuntimeError, match="No external regime manager configured"):
            orch.update_options_regime(_make_options_state())

    def test_campaign_review_compatibility_after_service_updates(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        orchestrator = ServiceOrchestrator(
            service=_make_service(last_event_time_ns=_T0_NS + 20 * _NS_PER_S),
            evidence_store=store,
            external_regime_plane=ExternalRegimeDataPlane(staleness_threshold_s=60.0),
        )
        orchestrator.update_options_regime(_make_options_state(snapshot_ns=_T0_NS + 10 * _NS_PER_S))
        orchestrator.update_event_regime(
            _make_event_state(
                snapshot_ns=_T0_NS + 12 * _NS_PER_S,
                level=EventRegimeLevel.PENDING,
            )
        )

        orchestrator.start_campaign(run_id="phase11c")
        report = orchestrator.finalize_campaign()

        assert report.snapshot.ext_regime_available is True
        assert report.snapshot.ext_regime_evidence_sufficient is True
        assert report.snapshot.ext_regime_summary != ""

        orchestrator.start_review()
        orchestrator.intake_last_campaign()
        current = orchestrator.review_snapshot()
        final = orchestrator.finalize_review()

        assert current is not None
        assert current.ext_regime_quality == "sufficient"
        assert final.ext_regime_quality == "sufficient"
