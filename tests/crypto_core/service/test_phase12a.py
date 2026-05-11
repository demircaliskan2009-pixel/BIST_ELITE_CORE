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

import pytest

from crypto_core.execution.regime_contracts import (
    DataFreshness,
    EventCategory,
    EventRegimeLevel,
    OnChainRegimeLevel,
    OptionsRegimeLevel,
    OptionsRegimeState,
)
from crypto_core.runtime.models import RuntimeStatus
from crypto_core.service.evidence_store import EvidenceStore
from crypto_core.service.external_regime import (
    ExternalRegimeBundleApplyMode,
    ExternalRegimeDataPlane,
    ExternalRegimeFreshnessPolicy,
    ExternalRegimeManager,
    ExternalRegimeProviderPolicy,
    ExternalRegimeProviderProfile,
    ExternalRegimeProviderRole,
    ExternalRegimeProviderTrust,
    ExternalRegimeScenario,
    ExternalRegimeScenarioStep,
    ExternalRegimeUpdateStatus,
    external_regime_bundle_replay_artifact_from_dict,
    external_regime_bundle_replay_artifact_to_dict,
    external_regime_scenario_result_to_dict,
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

    def test_unknown_provider_is_rejected_by_source_policy(self):
        manager = ExternalRegimeManager()

        record = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
                "source": "mystery.options",
            },
            provider="mystery",
        )

        assert record.accepted is False
        assert record.rejection_stage == "source_policy"
        assert record.reason == "unsupported_provider:mystery"
        assert record.provider_trust == ExternalRegimeProviderTrust.UNSUPPORTED.value

    def test_wrong_dimension_provider_is_rejected_by_source_policy(self):
        manager = ExternalRegimeManager()

        record = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
                "source": "calendar.options",
            },
            provider="calendar",
        )

        assert record.accepted is False
        assert record.rejection_stage == "source_policy"
        assert record.reason == "provider_not_allowed_for_dimension:calendar:options"
        assert record.provider_role == ExternalRegimeProviderRole.DISALLOWED.value

    def test_trusted_owner_is_reported_and_direct_updates_stay_supported(self):
        manager = ExternalRegimeManager()
        accepted = manager.ingest_event_payload(
            {
                "level": EventRegimeLevel.PENDING.value,
                "snapshot_ns": _T0_NS,
                "source": "calendar.event",
                "event_category": EventCategory.MACRO.value,
            },
            provider="calendar",
        )

        direct = manager.update_options(
            OptionsRegimeState(
                symbol="BTCUSDT",
                level=OptionsRegimeLevel.NORMAL,
                snapshot_ns=_T0_NS + _NS_PER_S,
                source="operator.manual.options",
            ),
            received_at_ns=_T0_NS + _NS_PER_S,
        )
        lifecycle = manager.status_dict(_T0_NS + _NS_PER_S)

        assert accepted.accepted is True
        assert direct.accepted is True
        assert lifecycle["current_dimension_sources"]["event"]["provider"] == "calendar"
        assert lifecycle["current_dimension_sources"]["event"]["trust"] == ExternalRegimeProviderTrust.TRUSTED.value
        assert lifecycle["current_dimension_sources"]["options"]["ownership_mode"] == "direct_update"

    def test_lower_trust_overwrite_is_blocked(self):
        policy = ExternalRegimeProviderPolicy(
            profiles=(
                ExternalRegimeProviderProfile(
                    provider="manual",
                    trust=ExternalRegimeProviderTrust.TRUSTED,
                    options_role=ExternalRegimeProviderRole.PREFERRED,
                ),
                ExternalRegimeProviderProfile(
                    provider="backup",
                    trust=ExternalRegimeProviderTrust.PROVISIONAL,
                    options_role=ExternalRegimeProviderRole.FALLBACK,
                ),
            )
        )
        manager = ExternalRegimeManager(provider_policy=policy)

        first = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
                "source": "manual.options",
            },
            provider="manual",
        )
        second = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.ELEVATED.value,
                "snapshot_ns": _T0_NS + _NS_PER_S,
                "source": "backup.options",
            },
            provider="backup",
        )

        snapshot = manager.snapshot(_T0_NS + _NS_PER_S)

        assert first.accepted is True
        assert second.accepted is False
        assert second.rejection_stage == "source_policy"
        assert second.reason == "lower_trust_overwrite_blocked:provisional<trusted"
        assert snapshot.options is not None
        assert snapshot.options.source == "manual.options"

    def test_per_dimension_freshness_policy_is_applied(self):
        plane = ExternalRegimeDataPlane(
            freshness_policy=ExternalRegimeFreshnessPolicy(
                options_staleness_threshold_s=60.0,
                event_staleness_threshold_s=300.0,
                on_chain_staleness_threshold_s=600.0,
            )
        )
        manager = ExternalRegimeManager(plane=plane)
        manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
                "source": "manual.options",
            },
            provider="manual",
        )
        manager.ingest_event_payload(
            {
                "level": EventRegimeLevel.PENDING.value,
                "snapshot_ns": _T0_NS,
                "source": "calendar.event",
                "event_category": EventCategory.MACRO.value,
            },
            provider="calendar",
        )

        snapshot = manager.snapshot(_T0_NS + 120 * _NS_PER_S)

        assert snapshot.options_freshness.freshness == DataFreshness.STALE
        assert snapshot.options_freshness.staleness_threshold_s == 60.0
        assert snapshot.event_freshness.freshness == DataFreshness.FRESH
        assert snapshot.event_freshness.staleness_threshold_s == 300.0

    def test_persistence_roundtrip_restores_source_owner_and_policy(self, tmp_path: Path):
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        policy = ExternalRegimeProviderPolicy(
            profiles=(
                ExternalRegimeProviderProfile(
                    provider="manual",
                    trust=ExternalRegimeProviderTrust.TRUSTED,
                    options_role=ExternalRegimeProviderRole.PREFERRED,
                ),
            )
        )
        manager = ExternalRegimeManager(
            plane=ExternalRegimeDataPlane(
                freshness_policy=ExternalRegimeFreshnessPolicy(
                    options_staleness_threshold_s=45.0,
                    event_staleness_threshold_s=300.0,
                    on_chain_staleness_threshold_s=600.0,
                )
            ),
            evidence_store=store,
            provider_policy=policy,
        )
        accepted = manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS,
                "source": "manual.options",
            },
            provider="manual",
        )
        assert accepted.accepted is True

        restored = ExternalRegimeManager(evidence_store=store)
        assert restored.restore_state() is True

        lifecycle = restored.status_dict(_T0_NS)
        assert lifecycle["current_dimension_sources"]["options"]["provider"] == "manual"
        assert lifecycle["freshness_policy"]["options_staleness_threshold_s"] == pytest.approx(45.0)
        assert lifecycle["provider_policy"]["profiles"][0]["provider"] == "manual"


class TestExternalRegimeBundleAdapters:
    def test_valid_multi_dimension_bundle_is_accepted(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "bundle_id": "bundle-001",
                "observed_at_ns": _T0_NS,
                "source": "operator.bundle",
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.ELEVATED.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                },
                "event": {
                    "level": EventRegimeLevel.PENDING.value,
                    "snapshot_ns": _T0_NS,
                    "source": "calendar.event",
                    "event_category": EventCategory.MACRO.value,
                },
            },
            provider="manual",
        )

        lifecycle = manager.status_dict(_T0_NS)

        assert result.accepted is True
        assert result.outcome == "fully_accepted"
        assert result.changed_dimensions == ("options", "event")
        assert lifecycle["latest_bundle_result"]["bundle_id"] == "bundle-001"
        assert lifecycle["latest_bundle_replay_artifact"]["normalized_bundle"]["source"] == "operator.bundle"

    def test_single_dimension_bundle_is_accepted(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "on_chain": {
                    "symbol": "BTC",
                    "level": OnChainRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "glassnode.flow",
                }
            },
            provider="glassnode",
        )

        assert result.accepted is True
        assert result.dimensions_present == ("on_chain",)
        assert result.changed_dimensions == ("on_chain",)

    def test_malformed_bundle_is_rejected(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "bundle_id": "bad-bundle",
                "unexpected": True,
            },
            provider="manual",
        )

        assert result.accepted is False
        assert result.outcome == "fully_rejected"
        assert result.reason == "bundle.unknown_fields:unexpected"

    def test_atomic_bundle_with_one_bad_dimension_rejects_without_mutation(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                },
                "event": {
                    "level": EventRegimeLevel.PENDING.value,
                    "snapshot_ns": _T0_NS,
                },
            },
            provider="manual",
            apply_mode=ExternalRegimeBundleApplyMode.ATOMIC,
        )

        snapshot = manager.snapshot(_T0_NS)

        assert result.accepted is False
        assert result.outcome == "fully_rejected"
        assert result.changed_dimensions == ()
        assert result.failed_dimensions == ("options", "event")
        assert snapshot.options is None
        assert snapshot.event is None
        assert any(item.reason.startswith("bundle_atomic_rejected:") for item in result.dimension_results)

    def test_partial_bundle_applies_valid_dimensions_and_reports_failures(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                },
                "event": {
                    "level": EventRegimeLevel.PENDING.value,
                    "snapshot_ns": _T0_NS,
                },
            },
            provider="manual",
            apply_mode=ExternalRegimeBundleApplyMode.PARTIAL,
        )

        snapshot = manager.snapshot(_T0_NS)

        assert result.accepted is False
        assert result.partially_accepted is True
        assert result.outcome == "partially_accepted"
        assert result.changed_dimensions == ("options",)
        assert result.failed_dimensions == ("event",)
        assert snapshot.options is not None
        assert snapshot.event is None

    def test_source_policy_is_enforced_inside_bundle(self):
        manager = ExternalRegimeManager()

        result = manager.ingest_bundle_payload(
            {
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "calendar.options",
                }
            },
            provider="calendar",
        )

        assert result.accepted is False
        assert result.failed_dimensions == ("options",)
        assert result.dimension_results[0].reason == "provider_not_allowed_for_dimension:calendar:options"

    def test_stale_policy_is_enforced_inside_bundle(self):
        manager = ExternalRegimeManager()
        manager.ingest_options_payload(
            {
                "symbol": "BTCUSDT",
                "level": OptionsRegimeLevel.NORMAL.value,
                "snapshot_ns": _T0_NS + 5 * _NS_PER_S,
                "source": "manual.options",
            },
            provider="manual",
        )

        result = manager.ingest_bundle_payload(
            {
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.EXTREME.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                }
            },
            provider="manual",
        )

        assert result.accepted is False
        assert result.dimension_results[0].update_status == ExternalRegimeUpdateStatus.REJECTED_STALE.value

    def test_bundle_replay_artifact_roundtrip(self):
        manager = ExternalRegimeManager()
        initial = manager.ingest_bundle_payload(
            {
                "bundle_id": "bundle-replay",
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.ELEVATED.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                },
            },
            provider="manual",
        )
        assert initial.accepted is True

        artifact = manager.latest_bundle_replay_artifact
        assert artifact is not None
        artifact_dict = external_regime_bundle_replay_artifact_to_dict(artifact)
        restored_artifact = external_regime_bundle_replay_artifact_from_dict(artifact_dict)
        replayed = ExternalRegimeManager().replay_bundle_artifact(restored_artifact)

        assert artifact_dict is not None
        assert replayed.accepted is True
        assert replayed.bundle_id == "bundle-replay"
        assert replayed.changed_dimensions == ("options",)


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
        assert lifecycle["current_dimension_sources"]["event"]["provider"] == "calendar"
        assert lifecycle["freshness_policy"]["event_staleness_threshold_s"] == pytest.approx(3600.0)

    def test_service_orchestrator_exposes_bundle_ingestion_and_replay(self):
        orchestrator = ServiceOrchestrator(
            service=_make_service(),
            external_regime_plane=ExternalRegimeDataPlane(),
        )

        accepted = orchestrator.ingest_external_regime_bundle_json(
            json.dumps(
                {
                    "bundle_id": "svc-bundle",
                    "options": {
                        "symbol": "BTCUSDT",
                        "level": OptionsRegimeLevel.ELEVATED.value,
                        "snapshot_ns": _T0_NS,
                        "source": "manual.options",
                    },
                    "event": {
                        "level": EventRegimeLevel.PENDING.value,
                        "snapshot_ns": _T0_NS,
                        "source": "manual.event",
                        "event_category": EventCategory.MACRO.value,
                    },
                }
            ),
            provider="manual",
        )
        artifact = orchestrator.external_regime_latest_bundle_replay_artifact()
        replayed = orchestrator.replay_external_regime_bundle_artifact(artifact)
        lifecycle = orchestrator.external_regime_lifecycle_dict()

        assert accepted.accepted is True
        assert artifact is not None
        assert replayed.accepted is True
        assert lifecycle is not None
        assert lifecycle["latest_bundle_result"]["bundle_id"] == "svc-bundle"
        assert lifecycle["latest_bundle_replay_artifact"]["result"]["bundle_id"] == "svc-bundle"


class TestExternalRegimeScenarioRunner:
    def test_multi_step_bundle_scenario_is_deterministic(self):
        scenario = ExternalRegimeScenario(
            scenario_id="scenario-deterministic",
            steps=(
                ExternalRegimeScenarioStep(
                    step_id="step-1",
                    received_at_ns=_T0_NS,
                    provider="manual",
                    bundle_payload={
                        "bundle_id": "scenario-bundle-1",
                        "options": {
                            "symbol": "BTCUSDT",
                            "level": OptionsRegimeLevel.NORMAL.value,
                            "snapshot_ns": _T0_NS,
                            "source": "manual.options",
                        },
                        "event": {
                            "level": EventRegimeLevel.QUIET.value,
                            "snapshot_ns": _T0_NS,
                            "source": "calendar.event",
                            "event_category": EventCategory.MACRO.value,
                        },
                        "on_chain": {
                            "symbol": "BTC",
                            "level": OnChainRegimeLevel.NORMAL.value,
                            "snapshot_ns": _T0_NS,
                            "source": "glassnode.flow",
                        },
                    },
                ),
                ExternalRegimeScenarioStep(
                    step_id="step-2",
                    received_at_ns=_T0_NS + _NS_PER_S,
                    provider="manual",
                    bundle_payload={
                        "bundle_id": "scenario-bundle-2",
                        "options": {
                            "symbol": "BTCUSDT",
                            "level": OptionsRegimeLevel.ELEVATED.value,
                            "snapshot_ns": _T0_NS + _NS_PER_S,
                            "source": "manual.options",
                        },
                        "on_chain": {
                            "symbol": "BTC",
                            "level": OnChainRegimeLevel.WHALE_ACTIVE.value,
                            "snapshot_ns": _T0_NS + _NS_PER_S,
                            "source": "glassnode.flow",
                        },
                    },
                    apply_mode=ExternalRegimeBundleApplyMode.PARTIAL.value,
                ),
            ),
        )

        first = ExternalRegimeManager().run_scenario(scenario)
        second = ExternalRegimeManager().run_scenario(scenario)

        assert external_regime_scenario_result_to_dict(first) == external_regime_scenario_result_to_dict(second)
        assert first.step_count == 2
        assert first.accepted_steps == 2
        assert first.activation_reduced_steps == 1

    def test_time_progression_can_make_regime_state_stale(self):
        manager = ExternalRegimeManager(
            plane=ExternalRegimeDataPlane(
                freshness_policy=ExternalRegimeFreshnessPolicy.uniform(60.0),
            )
        )
        scenario = ExternalRegimeScenario(
            scenario_id="scenario-stale",
            steps=(
                ExternalRegimeScenarioStep(
                    step_id="seed",
                    received_at_ns=_T0_NS,
                    provider="manual",
                    bundle_payload={
                        "options": {
                            "symbol": "BTCUSDT",
                            "level": OptionsRegimeLevel.NORMAL.value,
                            "snapshot_ns": _T0_NS,
                            "source": "manual.options",
                        },
                        "event": {
                            "level": EventRegimeLevel.QUIET.value,
                            "snapshot_ns": _T0_NS,
                            "source": "calendar.event",
                            "event_category": EventCategory.MACRO.value,
                        },
                        "on_chain": {
                            "symbol": "BTC",
                            "level": OnChainRegimeLevel.NORMAL.value,
                            "snapshot_ns": _T0_NS,
                            "source": "glassnode.flow",
                        },
                    },
                ),
                ExternalRegimeScenarioStep(
                    step_id="advance",
                    received_at_ns=_T0_NS + 120 * _NS_PER_S,
                    provider="calendar",
                    dimension_payloads={
                        "event": {
                            "level": EventRegimeLevel.QUIET.value,
                            "snapshot_ns": _T0_NS + 120 * _NS_PER_S,
                            "source": "calendar.event",
                            "event_category": EventCategory.MACRO.value,
                        }
                    },
                ),
            ),
        )

        result = manager.run_scenario(scenario)

        assert result.stale_steps == 1
        assert result.step_records[-1].stale_dimensions == ("options", "on_chain")
        assert result.execution_blocked_steps == 1

    def test_rejected_dimension_step_is_counted(self):
        result = ExternalRegimeManager().run_scenario(
            ExternalRegimeScenario(
                scenario_id="scenario-rejected",
                steps=(
                    ExternalRegimeScenarioStep(
                        step_id="bad-event",
                        received_at_ns=_T0_NS,
                        provider="calendar",
                        dimension_payloads={
                            "event": {
                                "level": EventRegimeLevel.PENDING.value,
                                "snapshot_ns": _T0_NS,
                            }
                        },
                    ),
                ),
            )
        )

        assert result.rejected_steps == 1
        assert result.accepted_steps == 0
        assert result.step_records[0].failed_dimensions == ("event",)

    def test_service_orchestrator_runs_scenario_and_tracks_replayed_steps(self):
        orchestrator = ServiceOrchestrator(
            service=_make_service(),
            external_regime_plane=ExternalRegimeDataPlane(),
        )
        orchestrator.ingest_external_regime_bundle(
            {
                "bundle_id": "seed-artifact",
                "options": {
                    "symbol": "BTCUSDT",
                    "level": OptionsRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "manual.options",
                },
                "event": {
                    "level": EventRegimeLevel.QUIET.value,
                    "snapshot_ns": _T0_NS,
                    "source": "calendar.event",
                    "event_category": EventCategory.MACRO.value,
                },
                "on_chain": {
                    "symbol": "BTC",
                    "level": OnChainRegimeLevel.NORMAL.value,
                    "snapshot_ns": _T0_NS,
                    "source": "glassnode.flow",
                },
            },
            provider="manual",
        )
        artifact = orchestrator.external_regime_latest_bundle_replay_artifact()
        result = orchestrator.run_external_regime_scenario(
            ExternalRegimeScenario(
                scenario_id="svc-scenario",
                steps=(
                    ExternalRegimeScenarioStep(
                        step_id="replay-seed",
                        received_at_ns=_T0_NS + 5 * _NS_PER_S,
                        provider="manual",
                        replay_artifact=artifact,
                    ),
                ),
            )
        )
        lifecycle = orchestrator.external_regime_lifecycle_dict()

        assert artifact is not None
        assert result.replayed_steps == 1
        assert lifecycle is not None
        assert lifecycle["scenario_status"] == "completed"
        assert lifecycle["latest_scenario_result"]["replayed_steps"] == 1
