"""Phase 12A tests — external regime provider adapter ingestion layer.

Covers:
  1. Strict dict / JSON / JSON-file payload ingestion.
  2. Raw payload validation before manager update.
  3. Preservation of stale / contradictory update semantics.
  4. Last accepted / rejected payload reporting.
  5. Service-level ingestion seam on ServiceOrchestrator.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from crypto_core.execution.regime_contracts import (
    EventCategory,
    EventRegimeLevel,
    OnChainRegimeLevel,
    OptionsRegimeLevel,
)
from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.external_regime import (
    ExternalRegimeDataPlane,
    ExternalRegimeManager,
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


def _make_service_status(*, last_event_time_ns: int = _T0_NS) -> ServiceStatus:
    session = PaperSessionStatus(
        session_id="phase12a",
        mode="running",
        start_time_ns=_T0_NS,
        current_cycle_time_ns=last_event_time_ns,
        total_cycles=40,
        total_fills=4,
        approved_cycles=36,
        blocked_cycles=2,
        failed_cycles=2,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=0,
        nav_usd=10_000.0,
        gross_exposure_pct=0.0,
        net_exposure_pct=0.0,
        last_cycle_approved=True,
        last_error=None,
        trading_blocked=False,
        route_block_count=0,
        route_abstain_count=0,
        pending_markout_count=0,
        persisted_tca_count=1,
        persisted_attribution_count=1,
        registered_fill_count=1,
    )
    runtime = RuntimeStatus(
        session_status=session,
        total_event_count=200,
        total_trigger_count=40,
        total_suppressed_count=1,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": last_event_time_ns},
        recovery_in_progress=False,
        blocked_reason=None,
    )
    queue = QueueSnapshot(
        current_depth=2,
        max_size=64,
        pressure=QueuePressure.NORMAL,
        total_enqueued=500,
        total_dropped=0,
        total_processed=498,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=last_event_time_ns,
        last_cycle_time_ns=last_event_time_ns,
        seconds_since_event=0.25,
        seconds_since_cycle=0.25,
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


class TestExternalRegimePayloadAdapters:
    def test_ingest_options_dict_payload_accepts_and_tracks_last_accepted(self):
        manager = ExternalRegimeManager()

        record = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.ELEVATED.value,
                "snapshot_ns": _T0_NS,
                "source": "manual.options",
                "implied_vol_30d": 0.62,
            },
            provider="manual",
            input_format="dict",
        )

        assert record.accepted is True
        assert record.reason == "accepted"
        assert record.payload_summary["provider"] == "manual"
        assert manager.latest_accepted_payload is not None
        assert manager.latest_accepted_payload.level == OptionsRegimeLevel.ELEVATED.value

        lifecycle = manager.status_dict(_T0_NS)
        assert lifecycle["latest_accepted_payload"]["source_label"] == "manual.options"
        assert lifecycle["latest_rejected_payload"] is None

    def test_ingest_event_json_payload_accepts(self):
        manager = ExternalRegimeManager()

        record = manager.ingest_event_payload(
            json.dumps(
                {
                    "level": EventRegimeLevel.PENDING.value,
                    "snapshot_ns": _T0_NS,
                    "source": "calendar.event",
                    "event_category": EventCategory.MACRO.value,
                    "event_label": "FOMC_2026_05",
                    "hours_until_event": 3.5,
                    "impact_estimate": 0.8,
                }
            ),
            provider="calendar",
            input_format="json",
        )

        assert record.accepted is True
        assert record.input_format == "json"
        assert record.payload_summary["event_label"] == "FOMC_2026_05"

    def test_ingest_on_chain_json_file_payload_accepts(self, tmp_path: Path):
        manager = ExternalRegimeManager()
        payload_path = tmp_path / "on_chain.json"
        payload_path.write_text(
            json.dumps(
                {
                    "symbol": "BTC",
                    "level": OnChainRegimeLevel.STRESS.value,
                    "snapshot_ns": _T0_NS,
                    "source": "glassnode.flow",
                    "exchange_net_flow_24h_usd": 12500000.0,
                    "whale_transfer_count_24h": 14,
                }
            ),
            encoding="utf-8",
        )

        record = manager.ingest_on_chain_payload(
            payload_path,
            provider="glassnode",
            input_format="json_file",
        )

        assert record.accepted is True
        assert record.payload_origin == str(payload_path)
        assert record.payload_summary["symbol"] == "BTC"

    def test_invalid_payload_is_rejected_and_does_not_mutate_state(self):
        manager = ExternalRegimeManager()

        record = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
            },
            provider="manual",
            input_format="dict",
        )

        snap = manager.snapshot(_T0_NS)

        assert record.accepted is False
        assert record.rejection_stage == "adapter_validation"
        assert record.reason == "options.missing_fields:source"
        assert snap.options is None
        assert manager.latest_rejected_payload is not None
        assert manager.latest_rejected_payload.reason == "options.missing_fields:source"

    def test_stale_payload_preserves_manager_rejection_semantics(self):
        manager = ExternalRegimeManager()
        accepted = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS + 10 * _NS_PER_S,
                "source": "manual.options",
            },
            provider="manual",
        )

        rejected = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.EXTREME.value,
                "snapshot_ns": _T0_NS,
                "source": "manual.options",
            },
            provider="manual",
            received_at_ns=_T0_NS + 12 * _NS_PER_S,
        )

        snap = manager.snapshot(_T0_NS + 12 * _NS_PER_S)

        assert accepted.accepted is True
        assert rejected.accepted is False
        assert rejected.rejection_stage == "update_validation"
        assert rejected.update_status == ExternalRegimeUpdateStatus.REJECTED_STALE.value
        assert "stale_update" in rejected.reason
        assert snap.options is not None
        assert snap.options.snapshot_ns == _T0_NS + 10 * _NS_PER_S


class TestServiceOrchestratorExternalRegimeAdapters:
    def test_service_orchestrator_exposes_payload_ingestion_and_lifecycle(self):
        orchestrator = ServiceOrchestrator(
            service=_make_service(),
            external_regime_plane=ExternalRegimeDataPlane(),
        )

        accepted = orchestrator.ingest_external_regime_payload(
            dimension="event",
            payload={
                "level": EventRegimeLevel.ACTIVE.value,
                "snapshot_ns": _T0_NS,
                "source": "calendar.event",
                "event_category": EventCategory.MACRO.value,
                "event_label": "CPI_2026_05",
                "hours_since_event": 0.25,
                "impact_estimate": 0.9,
            },
            provider="calendar",
        )
        rejected = orchestrator.ingest_options_regime_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS + _NS_PER_S,
                "source": "manual.options",
                "unexpected": True,
            },
            provider="manual",
        )

        lifecycle = orchestrator.external_regime_lifecycle_dict()

        assert accepted.accepted is True
        assert rejected.accepted is False
        assert lifecycle is not None
        assert lifecycle["latest_accepted_payload"]["dimension"] == "event"
        assert lifecycle["latest_rejected_payload"]["dimension"] == "options"
        assert lifecycle["latest_rejected_payload"]["reason"] == "options.unknown_fields:unexpected"
