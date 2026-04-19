from __future__ import annotations

from unittest.mock import MagicMock

from crypto_core.execution.regime_contracts import (
    EventRegimeLevel,
    EventRegimeState,
    OnChainRegimeLevel,
    OnChainRegimeState,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.external_regime import ExternalRegimeDataPlane
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


def _service_status(*, last_event_time_ns: int = _T0_NS) -> ServiceStatus:
    session = PaperSessionStatus(
        session_id="phase11d",
        mode="running",
        start_time_ns=_T0_NS,
        current_cycle_time_ns=last_event_time_ns,
        total_cycles=10,
        total_fills=1,
        approved_cycles=8,
        blocked_cycles=2,
        failed_cycles=0,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=0,
        nav_usd=10_000.0,
        gross_exposure_pct=0.0,
        net_exposure_pct=0.0,
        last_cycle_approved=False,
        last_error=None,
        trading_blocked=False,
        route_block_count=0,
        route_abstain_count=0,
        pending_markout_count=0,
        persisted_tca_count=0,
        persisted_attribution_count=0,
        registered_fill_count=0,
    )
    runtime = RuntimeStatus(
        session_status=session,
        total_event_count=10,
        total_trigger_count=10,
        total_suppressed_count=0,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": last_event_time_ns},
        recovery_in_progress=False,
        blocked_reason=None,
    )
    return ServiceStatus(
        service_mode="running",
        runtime_status=runtime,
        queue=QueueSnapshot(
            current_depth=0,
            max_size=100,
            pressure=QueuePressure.NORMAL,
            total_enqueued=10,
            total_dropped=0,
            total_processed=10,
        ),
        watchdog=WatchdogStatus(
            consumer_alive=True,
            last_event_time_ns=last_event_time_ns,
            last_cycle_time_ns=last_event_time_ns,
            seconds_since_event=0.0,
            seconds_since_cycle=0.0,
            stall_detected=False,
            stall_threshold_s=60.0,
        ),
        symbol_health=(
            SymbolHealth(
                symbol="BTCUSDT",
                exchange="binance",
                feed_connected=True,
                feed_ready=True,
                feed_key="binance:BTCUSDT",
                last_event_time_ns=last_event_time_ns,
                blocked=False,
                block_reason=None,
            ),
        ),
        symbol_count=1,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
        total_service_restarts=0,
        execution_intelligence=ExecutionIntelligenceStatus(
            mode="optional",
            route_binding_enabled=True,
            tca_loop_enabled=True,
            tca_store_available=True,
            replay_dedup_bootstrapped=True,
            degraded=False,
            degraded_reasons=(),
        ),
    )


def _service(*, last_event_time_ns: int = _T0_NS) -> MagicMock:
    service = MagicMock()
    service.status.return_value = _service_status(last_event_time_ns=last_event_time_ns)
    return service


class TestOperatorExternalRegimeSafety:
    def test_operator_snapshot_surfaces_execution_block_on_stale_regime(self) -> None:
        plane = ExternalRegimeDataPlane(staleness_threshold_s=60.0)
        plane.update_options(
            OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.NORMAL,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_event(
            EventRegimeState(
                level=EventRegimeLevel.QUIET,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_on_chain(
            OnChainRegimeState(
                symbol="BTC",
                level=OnChainRegimeLevel.NORMAL,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )

        orch = ServiceOrchestrator(
            service=_service(last_event_time_ns=_T0_NS + 120 * _NS_PER_S),
            external_regime_plane=plane,
        )
        snap = orch.operator_snapshot()

        assert snap.external_regime_safety is not None
        assert snap.external_regime_safety.execution_blocked is True
        assert snap.external_regime_safety.execution_reason == "external_regime_stale"

    def test_operator_snapshot_surfaces_activation_block_on_event_risk(self) -> None:
        plane = ExternalRegimeDataPlane(staleness_threshold_s=60.0)
        plane.update_options(
            OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.NORMAL,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_event(
            EventRegimeState(
                level=EventRegimeLevel.PENDING,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_on_chain(
            OnChainRegimeState(
                symbol="BTC",
                level=OnChainRegimeLevel.NORMAL,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )

        orch = ServiceOrchestrator(service=_service(), external_regime_plane=plane)
        snap = orch.operator_snapshot()

        assert snap.external_regime_safety is not None
        assert snap.external_regime_safety.activation_blocked is True
        assert snap.external_regime_safety.activation_reason == "external_regime_event_risk_blocked"

    def test_combined_status_dict_includes_external_regime_safety(self) -> None:
        plane = ExternalRegimeDataPlane(staleness_threshold_s=60.0)
        plane.update_options(
            OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.ELEVATED,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_event(
            EventRegimeState(
                level=EventRegimeLevel.QUIET,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )
        plane.update_on_chain(
            OnChainRegimeState(
                symbol="BTC",
                level=OnChainRegimeLevel.WHALE_ACTIVE,
                snapshot_ns=_T0_NS,
                source="test",
            )
        )

        orch = ServiceOrchestrator(service=_service(), external_regime_plane=plane)
        status = orch.combined_status_dict()

        assert status["external_regime_safety"] is not None
        assert status["external_regime_safety"]["activation_blocked"] is False
        assert status["external_regime_safety"]["activation_allocation_scale"] == 0.5
