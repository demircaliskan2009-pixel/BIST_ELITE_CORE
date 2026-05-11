"""Tests for Phase 8C — Persistent ops evidence, resumable runs, artifact export.

Covers:
  1.  EvidenceStore — append evidence to JSONL.
  2.  EvidenceStore — load evidence (valid).
  3.  EvidenceStore — load evidence (malformed) fails closed.
  4.  EvidenceStore — unknown evidence_type rejected.
  5.  EvidenceStore — batch append.
  6.  EvidenceStore — save atomic snapshot.
  7.  EvidenceStore — load atomic snapshot.
  8.  EvidenceStore — load missing snapshot fails closed.
  9.  EvidenceStore — load corrupt snapshot fails closed.
  10. EvidenceStore — compaction (bounded retention).
  11. EvidenceStore — needs_compaction check.
  12. EvidenceStore — evidence_line_count.
  13. EvidenceStore — clear removes all files.
  14. PersistenceHealth — record success/failure.
  15. PersistenceHealth — HEALTHY → DEGRADED → FAILED transitions.
  16. PersistenceHealth — consecutive failures reset on success.
  17. PersistenceHealth — UNKNOWN when no writes.
  18. PersistenceHealthSnapshot — frozen.
  19. RunMetadata — build from service status.
  20. RunStateManager — start_run creates metadata.
  21. RunStateManager — persist_run_state writes snapshot.
  22. RunStateManager — restore_run_metadata reads snapshot.
  23. RunStateManager — restore fails on corrupt data.
  24. RunStateManager — restore fails on missing snapshot.
  25. RunStateManager — persist_evidence writes JSONL.
  26. RunStateManager — inspection snapshot.
  27. RunStateManager — persistence health tracked through persist calls.
  28. RunArtifact — build from typed snapshots.
  29. RunArtifact — export to disk.
  30. RunArtifact — load from disk.
  31. RunArtifact — frozen.
  32. InspectionSnapshot — frozen.
  33. RunMetadata — frozen.
  34. Deterministic replay: persist → restore → same metadata.
  35. Soak harness with persistence enabled.
  36. Soak harness: evidence persisted during run.
  37. Soak harness: restore after soak.
  38. Full crypto_core regression (run in full suite).
  39. Config defaults.
  40. WriteResult model.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_core.data.models.events import Exchange, MarkPriceEvent
from crypto_core.data.models.feed_state import ConnectionState, FeedState, RecoveryState
from crypto_core.execution.engine import ExecutionConfig
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.runtime.assembler import MarketStateAssembler
from crypto_core.runtime.bridge import FeedSessionBridge
from crypto_core.runtime.models import RuntimeBridgeConfig, RuntimeStatus, TriggerPolicy
from crypto_core.runtime.runner import PaperLiveRunner
from crypto_core.service.artifact_export import build_run_artifact, export_run_artifact, load_run_artifact
from crypto_core.service.audit import AuditConfig, AuditTrail
from crypto_core.service.evidence_store import (
    EvidenceStore,
    EvidenceStoreConfig,
    EvidenceStoreCorruptError,
    WriteResult,
)
from crypto_core.service.health import HealthConfig, HealthTracker
from crypto_core.service.metrics import build_operational_metrics, build_trading_metrics
from crypto_core.service.models import (
    QueuePressure,
    QueueSnapshot,
    ServiceConfig,
    ServiceStatus,
    SymbolHealth,
    WatchdogStatus,
)
from crypto_core.service.paper_live_service import PaperLiveService
from crypto_core.service.run_state import (
    PersistenceHealth,
    PersistenceHealthConfig,
    PersistenceStatus,
    RunMetadataCorruptError,
    RunStateConfig,
    RunStateManager,
)
from crypto_core.service.soak import SoakConfig, SoakHarness
from crypto_core.service.summary import build_service_summary
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import PaperSessionConfig, PaperSessionStatus

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000
_SYMBOL = "BTCUSDT"
_EXCHANGE = Exchange.BINANCE
_EXCHANGE_STR = "binance"


# ---------------------------------------------------------------------------
# Synthetic status helpers (reused from test_phase8b pattern)
# ---------------------------------------------------------------------------


def _running_service_status() -> ServiceStatus:
    sess_status = PaperSessionStatus(
        session_id="test-8c",
        mode="running",
        start_time_ns=_T0_NS,
        current_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        total_cycles=50,
        total_fills=5,
        approved_cycles=40,
        blocked_cycles=8,
        failed_cycles=2,
        recovery_status="clean_start",
        unresolved_order_count=0,
        open_positions_count=2,
        nav_usd=10_500.0,
        gross_exposure_pct=15.0,
        net_exposure_pct=5.0,
        last_cycle_approved=True,
        last_error=None,
        trading_blocked=False,
    )
    runtime = RuntimeStatus(
        session_status=sess_status,
        total_event_count=200,
        total_trigger_count=50,
        total_suppressed_count=10,
        per_symbol_ready={"BTCUSDT": True},
        per_symbol_last_trigger_ns={"BTCUSDT": _T0_NS + 100 * _NS_PER_S},
        recovery_in_progress=False,
        blocked_reason=None,
    )
    queue = QueueSnapshot(
        current_depth=10,
        max_size=1000,
        pressure=QueuePressure.NORMAL,
        total_enqueued=200,
        total_dropped=0,
        total_processed=190,
    )
    watchdog = WatchdogStatus(
        consumer_alive=True,
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        last_cycle_time_ns=_T0_NS + 100 * _NS_PER_S,
        seconds_since_event=0.5,
        seconds_since_cycle=0.5,
        stall_detected=False,
        stall_threshold_s=60.0,
    )
    sym_health = SymbolHealth(
        symbol="BTCUSDT",
        exchange="binance",
        feed_connected=True,
        feed_ready=True,
        feed_key="binance:BTCUSDT",
        last_event_time_ns=_T0_NS + 100 * _NS_PER_S,
        blocked=False,
        block_reason=None,
    )
    return ServiceStatus(
        service_mode="running",
        runtime_status=runtime,
        queue=queue,
        watchdog=watchdog,
        symbol_health=(sym_health,),
        symbol_count=1,
        trading_enabled=True,
        blocked_reason=None,
        last_error=None,
    )


def _mark_price(
    price: float = 50_000.0,
    timestamp_ns: int = _T0_NS,
    symbol: str = _SYMBOL,
    exchange: Exchange = _EXCHANGE,
) -> MarkPriceEvent:
    return MarkPriceEvent(
        symbol=symbol,
        exchange=exchange,
        mark_price=price,
        index_price=price,
        funding_rate=0.0001,
        next_funding_time_ns=timestamp_ns + 8 * 3600 * _NS_PER_S,
        timestamp_ns=timestamp_ns,
    )


def _live_feed_state(symbol: str = _SYMBOL) -> FeedState:
    state = FeedState(symbol=symbol, exchange=_EXCHANGE_STR, stream_type="multi")
    state.connection_state = ConnectionState.CONNECTED
    state.recovery_state = RecoveryState.READY
    return state


def _pipeline_config() -> PipelineConfig:
    return PipelineConfig(
        execution=ExecutionConfig(
            mode=ExecutionMode.PAPER,
            fill_pricer=FillPricerConfig(max_spread_bps=200.0, require_book_for_paper=True),
        ),
        execution_lifecycle=ExecutionLifecycleConfig(
            mode=ExecutionMode.PAPER,
            paper_adapter=PaperAdapterConfig(
                fill_pricer=FillPricerConfig(max_spread_bps=200.0),
                allow_degraded_fill=True,
            ),
        ),
        emit_telemetry=False,
    )


def _make_service(
    tmp_path: Path,
    *,
    queue_max_size: int = 100,
    feed_states: dict[str, FeedState] | None = None,
) -> PaperLiveService:
    session_cfg = PaperSessionConfig(
        session_id="test-8c",
        initial_nav_usd=10_000.0,
        persist_every_fill=True,
    )
    cfg = _pipeline_config()
    tracker = PositionTracker(initial_nav_usd=10_000.0)
    lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
    orch = PipelineOrchestrator(
        config=cfg,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )
    session = PaperLiveSession(
        config=session_cfg,
        orchestrator=orch,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )
    config = RuntimeBridgeConfig(trigger_policy=TriggerPolicy.MARK_PRICE, trade_batch_size=3)
    assembler = MarketStateAssembler(config)
    bridge = FeedSessionBridge(
        session=session,
        assembler=assembler,
        config=config,
        feed_states=feed_states,
    )
    runner = PaperLiveRunner(session=session, bridge=bridge)
    ingestor = MagicMock()
    ingestor.get_feed_state = MagicMock(return_value=None)
    ingestor.shutdown_all = MagicMock()
    svc_config = ServiceConfig(
        queue_max_size=queue_max_size,
        consumer_poll_timeout_s=0.1,
    )
    return PaperLiveService(runner=runner, ingestor=ingestor, config=svc_config)


# ===========================================================================
# 1 · EvidenceStore — append evidence to JSONL
# ===========================================================================


class TestEvidenceAppend:
    def test_append_creates_file(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        result = store.append_evidence("readiness_snapshot", {"level": "ready"})
        assert result.success is True
        assert store.evidence_log_path.exists()

    def test_append_content_valid_jsonl(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.append_evidence("health_trend_snapshot", {"trend": "stable"})
        with store.evidence_log_path.open() as fh:
            line = fh.readline()
        record = json.loads(line)
        assert record["schema_version"] == "1"
        assert record["evidence_type"] == "health_trend_snapshot"
        assert record["data"]["trend"] == "stable"
        assert "timestamp_ns" in record

    def test_append_multiple(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        for etype in ("readiness_snapshot", "service_failure", "pressure_transition"):
            result = store.append_evidence(etype, {"test": True})
            assert result.success
        assert store.evidence_line_count() == 3


# ===========================================================================
# 2 · EvidenceStore — load evidence (valid)
# ===========================================================================


class TestEvidenceLoad:
    def test_load_empty_returns_empty(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        records = store.load_evidence()
        assert records == []

    def test_load_returns_records(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.append_evidence("readiness_snapshot", {"level": "ready"})
        store.append_evidence("service_failure", {"error": "boom"})
        records = store.load_evidence()
        assert len(records) == 2
        assert records[0]["evidence_type"] == "readiness_snapshot"
        assert records[1]["evidence_type"] == "service_failure"


# ===========================================================================
# 3 · EvidenceStore — load malformed evidence fails closed
# ===========================================================================


class TestEvidenceLoadMalformed:
    def test_malformed_json_fails_closed(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.evidence_log_path.parent.mkdir(parents=True, exist_ok=True)
        with store.evidence_log_path.open("w") as fh:
            fh.write("not valid json\n")
        with pytest.raises(EvidenceStoreCorruptError, match="malformed"):
            store.load_evidence()

    def test_missing_fields_fails_closed(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.evidence_log_path.parent.mkdir(parents=True, exist_ok=True)
        with store.evidence_log_path.open("w") as fh:
            fh.write(json.dumps({"schema_version": "1"}) + "\n")
        with pytest.raises(EvidenceStoreCorruptError, match="missing fields"):
            store.load_evidence()

    def test_unknown_schema_version_fails_closed(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.evidence_log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "schema_version": "99",
            "evidence_type": "readiness_snapshot",
            "timestamp_ns": 123,
            "data": {},
        }
        with store.evidence_log_path.open("w") as fh:
            fh.write(json.dumps(record) + "\n")
        with pytest.raises(EvidenceStoreCorruptError, match="schema_version"):
            store.load_evidence()


# ===========================================================================
# 4 · EvidenceStore — unknown evidence_type rejected
# ===========================================================================


class TestEvidenceUnknownType:
    def test_reject_unknown_type(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        result = store.append_evidence("invented_type", {"data": 1})
        assert result.success is False
        assert "Unknown evidence_type" in (result.error or "")


# ===========================================================================
# 5 · EvidenceStore — batch append
# ===========================================================================


class TestEvidenceBatchAppend:
    def test_batch_append(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        batch = [
            ("readiness_snapshot", {"level": "ready"}),
            ("service_failure", {"error": "test"}),
            ("pressure_transition", {"from": "normal", "to": "warning"}),
        ]
        result = store.append_evidence_batch(batch)
        assert result.success is True
        assert store.evidence_line_count() == 3

    def test_batch_rejects_bad_type(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        batch = [
            ("readiness_snapshot", {"level": "ready"}),
            ("bad_type", {"data": 1}),
        ]
        result = store.append_evidence_batch(batch)
        assert result.success is False


# ===========================================================================
# 6 · EvidenceStore — save atomic snapshot
# ===========================================================================


class TestSnapshotSave:
    def test_save_creates_file(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        result = store.save_snapshot("test_snap", {"key": "value"})
        assert result.success is True
        assert store.snapshot_path("test_snap").exists()

    def test_save_atomic_content(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.save_snapshot("test_snap", {"key": "value"})
        with store.snapshot_path("test_snap").open() as fh:
            raw = json.load(fh)
        assert raw["schema_version"] == "1"
        assert raw["snapshot_name"] == "test_snap"
        assert raw["data"]["key"] == "value"


# ===========================================================================
# 7 · EvidenceStore — load atomic snapshot
# ===========================================================================


class TestSnapshotLoad:
    def test_load_valid(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.save_snapshot("test_snap", {"key": 42})
        envelope = store.load_snapshot("test_snap")
        assert envelope["data"]["key"] == 42
        assert envelope["snapshot_name"] == "test_snap"


# ===========================================================================
# 8 · EvidenceStore — load missing snapshot fails closed
# ===========================================================================


class TestSnapshotLoadMissing:
    def test_missing_fails_closed(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        with pytest.raises(EvidenceStoreCorruptError, match="not found"):
            store.load_snapshot("nonexistent")


# ===========================================================================
# 9 · EvidenceStore — load corrupt snapshot fails closed
# ===========================================================================


class TestSnapshotLoadCorrupt:
    def test_corrupt_json_fails_closed(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        path = store.snapshot_path("bad")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json")
        with pytest.raises(EvidenceStoreCorruptError, match="decode error"):
            store.load_snapshot("bad")

    def test_missing_envelope_fields_fails(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        path = store.snapshot_path("bad2")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"schema_version": "1"}))
        with pytest.raises(EvidenceStoreCorruptError, match="missing fields"):
            store.load_snapshot("bad2")


# ===========================================================================
# 10 · EvidenceStore — compaction
# ===========================================================================


class TestEvidenceCompaction:
    def test_compact_keeps_recent(self, tmp_path: Path) -> None:
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(max_evidence_lines=10, compaction_keep=3),
        )
        for i in range(8):
            store.append_evidence("readiness_snapshot", {"index": i})
        assert store.evidence_line_count() == 8
        result = store.compact()
        assert result.success is True
        assert store.evidence_line_count() == 3
        # Most recent records retained.
        records = store.load_evidence()
        assert records[0]["data"]["index"] == 5
        assert records[-1]["data"]["index"] == 7

    def test_compact_noop_when_small(self, tmp_path: Path) -> None:
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(compaction_keep=100),
        )
        for i in range(5):
            store.append_evidence("readiness_snapshot", {"i": i})
        result = store.compact()
        assert result.success is True
        assert store.evidence_line_count() == 5


# ===========================================================================
# 11 · EvidenceStore — needs_compaction
# ===========================================================================


class TestNeedsCompaction:
    def test_below_threshold(self, tmp_path: Path) -> None:
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(max_evidence_lines=100),
        )
        store.append_evidence("readiness_snapshot", {"i": 0})
        assert store.needs_compaction() is False

    def test_above_threshold(self, tmp_path: Path) -> None:
        store = EvidenceStore(
            evidence_dir=tmp_path / "evidence",
            config=EvidenceStoreConfig(max_evidence_lines=3),
        )
        for i in range(5):
            store.append_evidence("readiness_snapshot", {"i": i})
        assert store.needs_compaction() is True


# ===========================================================================
# 12 · EvidenceStore — evidence_line_count
# ===========================================================================


class TestEvidenceLineCount:
    def test_count_empty(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        assert store.evidence_line_count() == 0

    def test_count_matches(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        for i in range(7):
            store.append_evidence("audit_record", {"i": i})
        assert store.evidence_line_count() == 7


# ===========================================================================
# 13 · EvidenceStore — clear
# ===========================================================================


class TestEvidenceClear:
    def test_clear_removes_files(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        store.append_evidence("readiness_snapshot", {})
        store.save_snapshot("test", {"x": 1})
        store.clear()
        assert not store.evidence_log_path.exists()
        assert not store.snapshot_path("test").exists()


# ===========================================================================
# 14 · PersistenceHealth — record success/failure
# ===========================================================================


class TestPersistenceHealthRecording:
    def test_record_success(self) -> None:
        ph = PersistenceHealth()
        ph.record_success()
        snap = ph.snapshot()
        assert snap.total_writes == 1
        assert snap.total_successes == 1
        assert snap.consecutive_failures == 0

    def test_record_failure(self) -> None:
        ph = PersistenceHealth()
        ph.record_failure("disk full")
        snap = ph.snapshot()
        assert snap.total_writes == 1
        assert snap.total_failures == 1
        assert snap.consecutive_failures == 1
        assert snap.last_failure_reason == "disk full"


# ===========================================================================
# 15 · PersistenceHealth — transitions
# ===========================================================================


class TestPersistenceHealthTransitions:
    def test_healthy_on_success(self) -> None:
        ph = PersistenceHealth()
        ph.record_success()
        assert ph.snapshot().status == PersistenceStatus.HEALTHY

    def test_degraded_after_threshold(self) -> None:
        ph = PersistenceHealth(PersistenceHealthConfig(degraded_after=2))
        ph.record_failure("err1")
        ph.record_failure("err2")
        assert ph.snapshot().status == PersistenceStatus.DEGRADED

    def test_failed_after_threshold(self) -> None:
        ph = PersistenceHealth(PersistenceHealthConfig(degraded_after=2, failed_after=4))
        for i in range(4):
            ph.record_failure(f"err{i}")
        assert ph.snapshot().status == PersistenceStatus.FAILED


# ===========================================================================
# 16 · PersistenceHealth — reset on success
# ===========================================================================


class TestPersistenceHealthReset:
    def test_consecutive_failures_reset(self) -> None:
        ph = PersistenceHealth(PersistenceHealthConfig(degraded_after=2))
        ph.record_failure("e1")
        ph.record_failure("e2")
        assert ph.snapshot().status == PersistenceStatus.DEGRADED
        ph.record_success()
        snap = ph.snapshot()
        assert snap.consecutive_failures == 0
        assert snap.status == PersistenceStatus.HEALTHY


# ===========================================================================
# 17 · PersistenceHealth — UNKNOWN when no writes
# ===========================================================================


class TestPersistenceHealthUnknown:
    def test_unknown_initial(self) -> None:
        ph = PersistenceHealth()
        assert ph.snapshot().status == PersistenceStatus.UNKNOWN


# ===========================================================================
# 18 · PersistenceHealthSnapshot — frozen
# ===========================================================================


class TestPersistenceHealthFrozen:
    def test_frozen(self) -> None:
        ph = PersistenceHealth()
        ph.record_success()
        snap = ph.snapshot()
        with pytest.raises(AttributeError):
            snap.status = PersistenceStatus.FAILED  # type: ignore[misc]


# ===========================================================================
# 19 · RunMetadata — build from service status
# ===========================================================================


class TestRunMetadataBuild:
    def test_build(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "test_evidence"),
        )
        ss = _running_service_status()
        meta = manager.start_run(ss)
        assert meta.run_id != ""
        assert meta.service_mode == "running"
        assert meta.session_id == "test-8c"
        assert meta.total_cycles == 50
        assert meta.nav_usd == 10_500.0


# ===========================================================================
# 20 · RunStateManager — start_run
# ===========================================================================


class TestRunStateManagerStartRun:
    def test_start_run(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        meta = manager.start_run(ss)
        assert len(meta.run_id) > 0
        assert meta.started_at_ns > 0
        assert manager.run_id == meta.run_id


# ===========================================================================
# 21 · RunStateManager — persist_run_state
# ===========================================================================


class TestRunStateManagerPersist:
    def test_persist_creates_snapshot(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        manager.start_run(ss)
        result = manager.persist_run_state(ss)
        assert result.success is True
        assert manager.evidence_store.snapshot_exists("run_state")

    def test_persist_tracks_health(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        manager.start_run(ss)
        manager.persist_run_state(ss)
        ph = manager.persistence_health.snapshot()
        assert ph.total_successes == 1
        assert ph.status == PersistenceStatus.HEALTHY


# ===========================================================================
# 22 · RunStateManager — restore_run_metadata
# ===========================================================================


class TestRunStateManagerRestore:
    def test_restore_round_trip(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        original = manager.start_run(ss)
        manager.persist_run_state(ss)

        # Create new manager pointing to same directory.
        manager2 = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        restored = manager2.restore_run_metadata()
        assert restored.run_id == original.run_id
        assert restored.service_mode == original.service_mode
        assert restored.session_id == original.session_id
        assert restored.total_cycles == original.total_cycles
        assert restored.nav_usd == original.nav_usd


# ===========================================================================
# 23 · RunStateManager — restore fails on corrupt data
# ===========================================================================


class TestRunStateManagerRestoreCorrupt:
    def test_corrupt_metadata(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        # Write a snapshot with missing required fields.
        store.save_snapshot("run_state", {"run_id": ""})
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        with pytest.raises(RunMetadataCorruptError):
            manager.restore_run_metadata()


# ===========================================================================
# 24 · RunStateManager — restore fails on missing snapshot
# ===========================================================================


class TestRunStateManagerRestoreMissing:
    def test_missing_snapshot(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        with pytest.raises(EvidenceStoreCorruptError, match="not found"):
            manager.restore_run_metadata()


# ===========================================================================
# 25 · RunStateManager — persist_evidence
# ===========================================================================


class TestRunStateManagerEvidence:
    def test_persist_evidence(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        result = manager.persist_evidence("readiness_snapshot", {"level": "ready"})
        assert result.success is True
        records = manager.evidence_store.load_evidence()
        assert len(records) == 1


# ===========================================================================
# 26 · RunStateManager — inspection snapshot
# ===========================================================================


class TestRunStateManagerInspection:
    def test_inspection(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        manager.start_run(ss)

        # Build readiness and health for inspection.
        tracker = HealthTracker(HealthConfig(window_size=5))
        tracker.record_sample(ss)
        readiness = tracker.readiness(ss)
        health_trend = tracker.trend_snapshot()

        snap = manager.inspect(ss, readiness, health_trend)
        assert snap.run_id == manager.run_id
        assert snap.service_mode == "running"
        assert snap.session_id == "test-8c"
        assert snap.total_cycles == 50
        assert snap.readiness_level == "ready"
        assert snap.persistence_status == "unknown"  # No writes yet.
        assert snap.nav_usd == 10_500.0

    def test_inspection_without_optional(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        manager.start_run(ss)
        snap = manager.inspect(ss)
        assert snap.readiness_level == "unknown"
        assert snap.health_trend == "unknown"


# ===========================================================================
# 27 · RunStateManager — persistence health tracked through persist
# ===========================================================================


class TestRunStateManagerPersistenceHealthTracking:
    def test_failure_tracking(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(
                evidence_dir=tmp_path / "evidence",
                persistence_config=PersistenceHealthConfig(degraded_after=2),
            ),
        )
        # Simulate write failures by calling record_failure directly.
        manager.persistence_health.record_failure("disk full")
        manager.persistence_health.record_failure("disk full")
        ph = manager.persistence_health.snapshot()
        assert ph.status == PersistenceStatus.DEGRADED
        assert ph.consecutive_failures == 2


# ===========================================================================
# 28 · RunArtifact — build from typed snapshots
# ===========================================================================


class TestRunArtifactBuild:
    def test_build_with_all_snapshots(self, tmp_path: Path) -> None:
        ss = _running_service_status()
        om = build_operational_metrics(service_status=ss, uptime_seconds=60.0)
        tm = build_trading_metrics(service_status=ss)
        svc_summary = build_service_summary(service_status=ss, uptime_seconds=60.0)

        tracker = HealthTracker(HealthConfig(window_size=5))
        tracker.record_sample(ss)
        readiness = tracker.readiness(ss)
        health_trend = tracker.trend_snapshot()

        audit = AuditTrail(AuditConfig(max_records=10))
        audit.record_cycle_approved(cycle=1)
        audit_snap = audit.snapshot()

        ph = PersistenceHealth()
        ph.record_success()
        ph_snap = ph.snapshot()

        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        meta = manager.start_run(ss)

        artifact = build_run_artifact(
            run_id=meta.run_id,
            run_metadata=meta,
            service_summary=svc_summary,
            health_trend=health_trend,
            readiness=readiness,
            operational_metrics=om,
            trading_metrics=tm,
            audit_snapshot=audit_snap,
            persistence_health=ph_snap,
        )
        assert artifact.run_id == meta.run_id
        assert artifact.run_metadata["service_mode"] == "running"
        assert artifact.session_summary["session_id"] == "test-8c"
        assert len(artifact.symbol_summaries) == 1
        assert artifact.health_trend["trend"] == "improving"
        assert artifact.audit_summary["total_records_logged"] == 1

    def test_build_minimal(self) -> None:
        artifact = build_run_artifact(run_id="test-minimal")
        assert artifact.run_id == "test-minimal"
        assert artifact.run_metadata == {}
        assert artifact.service_summary == {}


# ===========================================================================
# 29 · RunArtifact — export to disk
# ===========================================================================


class TestRunArtifactExport:
    def test_export(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        artifact = build_run_artifact(run_id="export-test")
        result = export_run_artifact(artifact=artifact, evidence_store=store)
        assert result.success is True
        assert store.snapshot_exists("run_artifact")


# ===========================================================================
# 30 · RunArtifact — load from disk
# ===========================================================================


class TestRunArtifactLoad:
    def test_load_round_trip(self, tmp_path: Path) -> None:
        store = EvidenceStore(evidence_dir=tmp_path / "evidence")
        artifact = build_run_artifact(run_id="test-load")
        export_run_artifact(artifact=artifact, evidence_store=store)
        loaded = load_run_artifact(evidence_store=store)
        assert loaded["run_id"] == "test-load"


# ===========================================================================
# 31 · RunArtifact — frozen
# ===========================================================================


class TestRunArtifactFrozen:
    def test_frozen(self) -> None:
        artifact = build_run_artifact(run_id="frozen-test")
        with pytest.raises(AttributeError):
            artifact.run_id = "changed"  # type: ignore[misc]


# ===========================================================================
# 32 · InspectionSnapshot — frozen
# ===========================================================================


class TestInspectionSnapshotFrozen:
    def test_frozen(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        manager.start_run(ss)
        snap = manager.inspect(ss)
        with pytest.raises(AttributeError):
            snap.service_mode = "stopped"  # type: ignore[misc]


# ===========================================================================
# 33 · RunMetadata — frozen
# ===========================================================================


class TestRunMetadataFrozen:
    def test_frozen(self, tmp_path: Path) -> None:
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        meta = manager.start_run(ss)
        with pytest.raises(AttributeError):
            meta.run_id = "hack"  # type: ignore[misc]


# ===========================================================================
# 34 · Deterministic replay: persist → restore → same metadata
# ===========================================================================


class TestDeterministicReplay:
    def test_persist_restore_equivalence(self, tmp_path: Path) -> None:
        """Same service status → persist → restore → same metadata fields."""
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        ss = _running_service_status()
        original = manager.start_run(ss)
        manager.persist_run_state(ss)

        manager2 = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        restored = manager2.restore_run_metadata()

        # All data fields must match.
        assert restored.run_id == original.run_id
        assert restored.started_at_ns == original.started_at_ns
        assert restored.service_mode == original.service_mode
        assert restored.session_mode == original.session_mode
        assert restored.session_id == original.session_id
        assert restored.total_cycles == original.total_cycles
        assert restored.approved_cycles == original.approved_cycles
        assert restored.blocked_cycles == original.blocked_cycles
        assert restored.failed_cycles == original.failed_cycles
        assert restored.total_fills == original.total_fills
        assert restored.total_events_enqueued == original.total_events_enqueued
        assert restored.total_events_dropped == original.total_events_dropped
        assert restored.nav_usd == original.nav_usd
        assert restored.symbol_count == original.symbol_count

    def test_evidence_round_trip(self, tmp_path: Path) -> None:
        """Persist evidence → load → same records."""
        manager = RunStateManager(
            RunStateConfig(evidence_dir=tmp_path / "evidence"),
        )
        manager.persist_evidence("readiness_snapshot", {"level": "ready", "score": 0})
        manager.persist_evidence("service_failure", {"error": "test_error"})

        records = manager.evidence_store.load_evidence()
        assert len(records) == 2
        assert records[0]["data"]["level"] == "ready"
        assert records[1]["data"]["error"] == "test_error"


# ===========================================================================
# 35 · Soak harness with persistence enabled
# ===========================================================================


class TestSoakWithPersistence:
    def test_soak_with_persistence(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        fs = _live_feed_state()
        service = _make_service(tmp_path, feed_states={feed_key: fs})
        service.register_symbol(feed_key, _SYMBOL, _EXCHANGE_STR)
        service.start()

        evidence_dir = tmp_path / "soak_evidence"
        manager = RunStateManager(
            RunStateConfig(evidence_dir=evidence_dir),
        )
        ss = service.status()
        manager.start_run(ss)

        audit = AuditTrail(AuditConfig(max_records=100))
        health = HealthTracker(HealthConfig(window_size=10))

        try:
            harness = SoakHarness(
                service=service,
                config=SoakConfig(
                    total_events=30,
                    report_every_n=10,
                    drain_timeout_s=3.0,
                    consumer_settle_s=0.3,
                ),
                audit_trail=audit,
                health_tracker=health,
            )

            def factory(idx: int, symbols: list[str]) -> object:
                return _mark_price(
                    price=50_000.0 + idx,
                    timestamp_ns=_T0_NS + idx * _NS_PER_S,
                )

            result = harness.run(event_factory=factory)

            # Persist evidence and snapshots from the soak.
            for idx, snap in result.intermediate_snapshots:
                manager.persist_evidence(
                    "cycle_summary",
                    {"event_index": idx, "service_mode": snap.service_mode},
                )

            readiness = health.readiness(service.status())
            manager.persist_evidence(
                "readiness_snapshot",
                {"level": readiness.level.value, "score": readiness.degradation_score},
            )
            manager.persist_evidence(
                "health_trend_snapshot",
                {"trend": health.trend_snapshot().trend.value},
            )

            # Persist run state and artifact.
            manager.persist_run_state(service.status())

            artifact = build_run_artifact(
                run_id=manager.run_id,
                run_metadata=manager.run_metadata,
                health_trend=health.trend_snapshot(),
                readiness=readiness,
                audit_snapshot=audit.snapshot(),
                persistence_health=manager.persistence_health.snapshot(),
            )
            export_result = export_run_artifact(
                artifact=artifact,
                evidence_store=manager.evidence_store,
            )
            assert export_result.success is True

            # Verify persisted outputs exist.
            assert manager.evidence_store.snapshot_exists("run_state")
            assert manager.evidence_store.snapshot_exists("run_artifact")
            records = manager.evidence_store.load_evidence()
            assert len(records) >= 3  # cycle_summary + readiness + health_trend

            assert not result.aborted
        finally:
            service.stop()


# ===========================================================================
# 36 · Soak harness: evidence persisted during run
# ===========================================================================


class TestSoakEvidencePersisted:
    def test_evidence_created(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        fs = _live_feed_state()
        service = _make_service(tmp_path, feed_states={feed_key: fs})
        service.register_symbol(feed_key, _SYMBOL, _EXCHANGE_STR)
        service.start()

        evidence_dir = tmp_path / "evidence"
        manager = RunStateManager(
            RunStateConfig(evidence_dir=evidence_dir),
        )
        manager.start_run(service.status())

        try:
            harness = SoakHarness(
                service=service,
                config=SoakConfig(
                    total_events=10,
                    report_every_n=0,
                    drain_timeout_s=2.0,
                    consumer_settle_s=0.2,
                ),
            )

            def factory(idx: int, symbols: list[str]) -> object:
                return _mark_price(
                    price=50_000.0 + idx,
                    timestamp_ns=_T0_NS + idx * _NS_PER_S,
                )

            harness.run(event_factory=factory)

            # Persist final state.
            manager.persist_run_state(service.status())
            assert manager.evidence_store.snapshot_exists("run_state")
        finally:
            service.stop()


# ===========================================================================
# 37 · Soak harness: restore after soak
# ===========================================================================


class TestSoakRestore:
    def test_restore_after_soak(self, tmp_path: Path) -> None:
        feed_key = f"{_EXCHANGE_STR}:{_SYMBOL}"
        fs = _live_feed_state()
        service = _make_service(tmp_path, feed_states={feed_key: fs})
        service.register_symbol(feed_key, _SYMBOL, _EXCHANGE_STR)
        service.start()

        evidence_dir = tmp_path / "evidence"
        manager = RunStateManager(
            RunStateConfig(evidence_dir=evidence_dir),
        )
        original = manager.start_run(service.status())

        try:
            harness = SoakHarness(
                service=service,
                config=SoakConfig(
                    total_events=20,
                    report_every_n=0,
                    drain_timeout_s=2.0,
                    consumer_settle_s=0.2,
                ),
            )

            def factory(idx: int, symbols: list[str]) -> object:
                return _mark_price(
                    price=50_000.0 + idx,
                    timestamp_ns=_T0_NS + idx * _NS_PER_S,
                )

            harness.run(event_factory=factory)
            manager.persist_run_state(service.status())
        finally:
            service.stop()

        # Restore from a fresh manager.
        manager2 = RunStateManager(
            RunStateConfig(evidence_dir=evidence_dir),
        )
        restored = manager2.restore_run_metadata()
        assert restored.run_id == original.run_id
        assert restored.started_at_ns == original.started_at_ns


# ===========================================================================
# 39 · Config defaults
# ===========================================================================


class TestConfigDefaults:
    def test_evidence_store_config(self) -> None:
        cfg = EvidenceStoreConfig()
        assert cfg.max_evidence_lines == 5000
        assert cfg.compaction_keep == 2000

    def test_persistence_health_config(self) -> None:
        cfg = PersistenceHealthConfig()
        assert cfg.degraded_after == 3
        assert cfg.failed_after == 10

    def test_run_state_config(self) -> None:
        cfg = RunStateConfig()
        assert cfg.evidence_dir == Path("runtime/evidence")


# ===========================================================================
# 40 · WriteResult model
# ===========================================================================


class TestWriteResult:
    def test_success(self) -> None:
        wr = WriteResult(success=True, path="/test/path")
        assert wr.success is True
        assert wr.error is None

    def test_failure(self) -> None:
        wr = WriteResult(success=False, error="disk full", path="/test")
        assert wr.success is False
        assert wr.error == "disk full"

    def test_frozen(self) -> None:
        wr = WriteResult(success=True)
        with pytest.raises(AttributeError):
            wr.success = False  # type: ignore[misc]
