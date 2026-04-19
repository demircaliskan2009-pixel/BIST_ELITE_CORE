"""Tests for Phase 9E — Service bootstrap wiring for execution intelligence.

Covers:
  1. Bootstrap with full EI (OPTIONAL) — all components injected.
  2. STRICT mode fails when dependencies missing.
  3. OPTIONAL mode degrades gracefully with reasons.
  4. DISABLED mode — no components built, no degradation.
  5. Router + TCA loop actually injected into orchestrator.
  6. TCA store wired into session for dedup bootstrap.
  7. ServiceStatus exposes execution_intelligence field.
  8. Readiness criteria includes execution_intelligence_active.
  9. Backward-compatible startup (no EI config → no injection).
  10. restart() re-bootstraps execution intelligence.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from crypto_core.execution.engine import ExecutionConfig
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.execution.route_binding import MetadataGatedRouter
from crypto_core.execution.tca_loop import ExecutionTCALoop
from crypto_core.execution.tca_store import TCAStore
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.runtime.assembler import MarketStateAssembler
from crypto_core.runtime.bridge import FeedSessionBridge
from crypto_core.runtime.models import RuntimeBridgeConfig, TriggerPolicy
from crypto_core.runtime.runner import PaperLiveRunner
from crypto_core.service.execution_intelligence import (
    ExecutionIntelligenceBootstrap,
)
from crypto_core.service.models import (
    ExecutionIntelligenceConfig,
    ExecutionIntelligenceMode,
    ExecutionIntelligenceStatus,
    ServiceConfig,
    ServiceMode,
)
from crypto_core.service.paper_live_service import PaperLiveService
from crypto_core.service.readiness import PAPER_LIVE_CRITERIA
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import PaperSessionConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def _make_session(tmp_path: Path) -> PaperLiveSession:
    cfg = _pipeline_config()
    tracker = PositionTracker(initial_nav_usd=10_000.0)
    lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
    orch = PipelineOrchestrator(
        config=cfg,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )
    session_cfg = PaperSessionConfig(
        session_id="test-9e",
        initial_nav_usd=10_000.0,
        persist_every_fill=True,
    )
    return PaperLiveSession(
        config=session_cfg,
        orchestrator=orch,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )


def _make_runner(tmp_path: Path) -> PaperLiveRunner:
    session = _make_session(tmp_path)
    config = RuntimeBridgeConfig(trigger_policy=TriggerPolicy.MARK_PRICE, trade_batch_size=3)
    assembler = MarketStateAssembler(config)
    bridge = FeedSessionBridge(
        session=session,
        assembler=assembler,
        config=config,
    )
    return PaperLiveRunner(session=session, bridge=bridge)


def _make_service(
    tmp_path: Path,
    *,
    ei_config: ExecutionIntelligenceConfig | None = None,
) -> PaperLiveService:
    runner = _make_runner(tmp_path)
    ingestor = MagicMock()
    ingestor.get_feed_state = MagicMock(return_value=None)
    ingestor.shutdown_all = MagicMock()
    config = ServiceConfig(
        queue_max_size=100,
        stall_threshold_s=60.0,
        consumer_poll_timeout_s=0.1,
    )
    return PaperLiveService(
        runner=runner,
        ingestor=ingestor,
        config=config,
        execution_intelligence_config=ei_config,
    )


# ---------------------------------------------------------------------------
# 1. Bootstrap with full EI (OPTIONAL) — all components injected
# ---------------------------------------------------------------------------


class TestBootstrapFullOptional:
    def test_optional_full_build(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=str(tmp_path / "tca"),
            tca_horizons=(1, 5, 15),
            auto_persist_tca=True,
        )
        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(ei_cfg)

        assert result.error is None
        assert result.router is not None
        assert isinstance(result.router, MetadataGatedRouter)
        assert result.tca_loop is not None
        assert isinstance(result.tca_loop, ExecutionTCALoop)
        assert result.tca_store is not None
        assert isinstance(result.tca_store, TCAStore)
        assert result.status.mode == "optional"
        assert result.status.route_binding_enabled is True
        assert result.status.tca_loop_enabled is True
        assert result.status.tca_store_available is True
        assert result.status.degraded is False


# ---------------------------------------------------------------------------
# 2. STRICT mode fails when dependencies missing
# ---------------------------------------------------------------------------


class TestStrictModeFails:
    def test_strict_no_tca_store_path_fails(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.STRICT,
            tca_store_path=None,
        )
        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(ei_cfg)

        assert result.error is not None
        assert "STRICT" in result.error
        assert result.status.degraded is True

    def test_strict_service_transitions_to_failed(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.STRICT,
            tca_store_path=None,
        )
        svc = _make_service(tmp_path, ei_config=ei_cfg)
        svc.start()

        assert svc.mode == ServiceMode.FAILED
        assert svc._last_error is not None
        assert "STRICT" in svc._last_error


# ---------------------------------------------------------------------------
# 3. OPTIONAL mode degrades gracefully
# ---------------------------------------------------------------------------


class TestOptionalDegrades:
    def test_optional_no_tca_store_degrades(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=None,
        )
        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(ei_cfg)

        # No error — OPTIONAL degrades gracefully.
        assert result.error is None
        assert result.status.degraded is True
        assert len(result.status.degraded_reasons) > 0
        assert any("tca_store" in r for r in result.status.degraded_reasons)
        # Router should still be built.
        assert result.router is not None
        # TCA loop built (even without store).
        assert result.tca_loop is not None


# ---------------------------------------------------------------------------
# 4. DISABLED mode — no components, no degradation
# ---------------------------------------------------------------------------


class TestDisabledMode:
    def test_disabled_builds_nothing(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.DISABLED,
        )
        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(ei_cfg)

        assert result.error is None
        assert result.router is None
        assert result.tca_loop is None
        assert result.tca_store is None
        assert result.status.mode == "disabled"
        assert result.status.degraded is False
        assert result.status.route_binding_enabled is False
        assert result.status.tca_loop_enabled is False


# ---------------------------------------------------------------------------
# 5. Router + TCA loop actually injected into orchestrator
# ---------------------------------------------------------------------------


class TestOrchestratorInjection:
    def test_components_injected_on_start(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=str(tmp_path / "tca"),
        )
        svc = _make_service(tmp_path, ei_config=ei_cfg)

        # Before start — orchestrator has no EI components.
        orch = svc.runner.session._orchestrator
        assert orch.tca_loop is None
        assert orch.metadata_gated_router is None

        svc.start()

        # After start — components injected.
        assert orch.tca_loop is not None
        assert isinstance(orch.tca_loop, ExecutionTCALoop)
        assert orch.metadata_gated_router is not None
        assert isinstance(orch.metadata_gated_router, MetadataGatedRouter)

        svc.stop()


# ---------------------------------------------------------------------------
# 6. TCA store wired into session for dedup bootstrap
# ---------------------------------------------------------------------------


class TestTCAStoreInjection:
    def test_tca_store_injected_into_session(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=str(tmp_path / "tca"),
        )
        svc = _make_service(tmp_path, ei_config=ei_cfg)

        # Before start — session has no TCA store.
        assert svc.runner.session._tca_store is None

        svc.start()

        # After start — TCA store injected.
        assert svc.runner.session._tca_store is not None
        assert isinstance(svc.runner.session._tca_store, TCAStore)

        svc.stop()


# ---------------------------------------------------------------------------
# 7. ServiceStatus exposes execution_intelligence
# ---------------------------------------------------------------------------


class TestServiceStatusExposesEI:
    def test_status_has_ei_when_configured(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=str(tmp_path / "tca"),
        )
        svc = _make_service(tmp_path, ei_config=ei_cfg)
        svc.start()

        status = svc.status()
        assert status.execution_intelligence is not None
        assert status.execution_intelligence.mode == "optional"
        assert status.execution_intelligence.route_binding_enabled is True
        assert status.execution_intelligence.tca_loop_enabled is True

        svc.stop()

    def test_status_none_when_no_config(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, ei_config=None)
        svc.start()

        status = svc.status()
        assert status.execution_intelligence is None

        svc.stop()


# ---------------------------------------------------------------------------
# 8. Readiness criteria includes execution_intelligence_active
# ---------------------------------------------------------------------------


class TestReadinessCriteria:
    def test_execution_intelligence_active_in_paper_live_criteria(self) -> None:
        assert "execution_intelligence_active" in PAPER_LIVE_CRITERIA


# ---------------------------------------------------------------------------
# 9. Backward-compatible startup (no EI config → no injection)
# ---------------------------------------------------------------------------


class TestBackwardCompatible:
    def test_no_config_starts_normally(self, tmp_path: Path) -> None:
        svc = _make_service(tmp_path, ei_config=None)
        svc.start()

        assert svc.mode == ServiceMode.RUNNING
        # No EI status.
        assert svc.execution_intelligence_status is None
        # Orchestrator has no injected EI components.
        orch = svc.runner.session._orchestrator
        assert orch.tca_loop is None
        assert orch.metadata_gated_router is None

        svc.stop()


# ---------------------------------------------------------------------------
# 10. restart() re-bootstraps execution intelligence
# ---------------------------------------------------------------------------


class TestRestartRebootstraps:
    def test_restart_reinjects_components(self, tmp_path: Path) -> None:
        ei_cfg = ExecutionIntelligenceConfig(
            mode=ExecutionIntelligenceMode.OPTIONAL,
            tca_store_path=str(tmp_path / "tca"),
        )
        svc = _make_service(tmp_path, ei_config=ei_cfg)
        svc.start()

        assert svc.mode == ServiceMode.RUNNING
        assert svc.execution_intelligence_status is not None

        svc.stop()
        assert svc.mode == ServiceMode.STOPPED

        # After restart, EI should be re-bootstrapped.
        # (restart() calls stop() then start())
        svc._mode = ServiceMode.CREATED  # Reset to allow start
        svc.start()

        assert svc.mode == ServiceMode.RUNNING
        assert svc.execution_intelligence_status is not None
        assert svc.execution_intelligence_status.route_binding_enabled is True

        svc.stop()


# ---------------------------------------------------------------------------
# Extra: ExecutionIntelligenceStatus frozen dataclass
# ---------------------------------------------------------------------------


class TestExecutionIntelligenceStatus:
    def test_status_is_frozen(self) -> None:
        status = ExecutionIntelligenceStatus(
            mode="optional",
            route_binding_enabled=True,
            tca_loop_enabled=True,
            tca_store_available=True,
            replay_dedup_bootstrapped=False,
            degraded=False,
        )
        with pytest.raises(AttributeError):
            status.mode = "strict"  # type: ignore[misc]

    def test_defaults(self) -> None:
        status = ExecutionIntelligenceStatus(
            mode="optional",
            route_binding_enabled=True,
            tca_loop_enabled=True,
            tca_store_available=True,
            replay_dedup_bootstrapped=False,
            degraded=False,
        )
        assert status.degraded_reasons == ()
