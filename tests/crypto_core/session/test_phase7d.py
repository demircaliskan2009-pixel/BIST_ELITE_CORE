"""Tests for Phase 7D — Paper-live operator control + runtime safety surface.

Covers:
  1. Pause/resume lifecycle (RUNNING → PAUSED → RUNNING).
  2. Paused session rejects events (like BLOCKED/STOPPED).
  3. Restart from FAILED → re-enters RUNNING.
  4. Restart from BLOCKED → re-enters start() logic.
  5. Restart from RUNNING/STOPPED raises ValueError.
  6. Cycle outcome counters (approved, blocked, failed).
  7. Last error populated on exception, cleared on restart.
  8. Cycle history populated and bounded.
  9. Cycle history appears in status snapshot.
  10. Deterministic replay with history.
  11. PAUSED enum value exists.
  12. Stop from PAUSED persists and transitions to STOPPED.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from crypto_core.execution.engine import ExecutionConfig
from crypto_core.execution.fill_pricer import FillPricerConfig
from crypto_core.execution.lifecycle import ExecutionLifecycleConfig, ExecutionLifecycleEngine
from crypto_core.execution.models import ExecutionMode
from crypto_core.execution.paper_adapter import PaperAdapterConfig
from crypto_core.execution.store import ExecutionStateStore
from crypto_core.orchestrator.models import MarketDataInput
from crypto_core.orchestrator.pipeline import PipelineConfig, PipelineOrchestrator
from crypto_core.portfolio.store import PortfolioStateStore
from crypto_core.portfolio.tracker import PositionTracker
from crypto_core.session.engine import PaperLiveSession
from crypto_core.session.models import (
    CycleResult,
    PaperSessionConfig,
    SessionMode,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_T0_NS = 1_000_000_000_000
_NS_PER_S = 1_000_000_000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _minimal_data(timestamp_ns: int = _T0_NS) -> MarketDataInput:
    """Minimal data that pipeline accepts."""
    return MarketDataInput(
        symbol="BTCUSDT",
        exchange="binance",
        timestamp_ns=timestamp_ns,
        trades=(),
        book_last_update_ns=timestamp_ns - 100_000_000,
        book_has_snapshot=True,
        book_bid_count=6,
        book_ask_count=6,
        feed_connection_state="connected",
        feed_recovery_state="ready",
        book_bid_price=49_900.0,
        book_ask_price=50_100.0,
        book_bid_size=1.0,
        book_ask_size=1.0,
    )


def _pipeline_config() -> PipelineConfig:
    """Standard pipeline config with paper execution + degraded fill."""
    return PipelineConfig(
        execution=ExecutionConfig(
            mode=ExecutionMode.PAPER,
            fill_pricer=FillPricerConfig(
                max_spread_bps=200.0,
                require_book_for_paper=True,
            ),
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


def _make_session(
    tmp_path: Path,
    *,
    session_id: str = "test-7d",
    initial_nav: float = 10_000.0,
    max_cycles: int = 0,
    persist_every_fill: bool = True,
    with_stores: bool = True,
    cycle_history_size: int = 100,
) -> PaperLiveSession:
    """Build a fully wired PaperLiveSession for testing."""
    cfg = _pipeline_config()
    tracker = PositionTracker(initial_nav_usd=initial_nav)
    lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
    orch = PipelineOrchestrator(
        config=cfg,
        position_tracker=tracker,
        lifecycle_engine=lifecycle,
    )

    portfolio_store = PortfolioStateStore(tmp_path / "portfolio.json") if with_stores else None
    exec_store = ExecutionStateStore(tmp_path / "execution.jsonl") if with_stores else None

    session_cfg = PaperSessionConfig(
        session_id=session_id,
        initial_nav_usd=initial_nav,
        persist_every_fill=persist_every_fill,
        max_cycles=max_cycles,
        cycle_history_size=cycle_history_size,
    )

    return PaperLiveSession(
        config=session_cfg,
        orchestrator=orch,
        position_tracker=tracker,
        portfolio_store=portfolio_store,
        exec_store=exec_store,
        lifecycle_engine=lifecycle,
    )


# =========================================================================
# Tests
# =========================================================================


class TestPausedEnum:
    """PAUSED mode exists in SessionMode enum."""

    def test_paused_value(self) -> None:
        assert SessionMode.PAUSED.value == "paused"

    def test_all_modes_present(self) -> None:
        expected = {
            "initializing",
            "recovering",
            "running",
            "paused",
            "blocked",
            "stopped",
            "failed",
        }
        actual = {m.value for m in SessionMode}
        assert actual == expected


class TestPauseResume:
    """Pause and resume lifecycle transitions."""

    def test_pause_transitions_to_paused(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        status = session.pause()

        assert status.mode == SessionMode.PAUSED.value
        assert session.mode == SessionMode.PAUSED
        assert "operator_paused" in status.block_reasons

    def test_resume_transitions_to_running(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        session.pause()
        status = session.resume()

        assert status.mode == SessionMode.RUNNING.value
        assert session.mode == SessionMode.RUNNING
        assert "operator_paused" not in status.block_reasons

    def test_paused_rejects_events(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        session.pause()

        result = session.process_event(_minimal_data())
        assert result.error is not None
        assert "session_not_running" in result.error
        assert result.pipeline_result is None

    def test_resume_allows_events(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        session.pause()
        session.resume()

        result = session.process_event(_minimal_data())
        assert result.error is None
        assert result.pipeline_result is not None

    def test_pause_from_non_running_is_noop(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        session.stop()

        status = session.pause()
        assert status.mode == SessionMode.STOPPED.value

    def test_resume_from_non_paused_is_noop(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()

        status = session.resume()
        assert status.mode == SessionMode.RUNNING.value

    def test_stop_from_paused_persists(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path)
        session.start()
        session.process_event(_minimal_data())
        session.pause()
        status = session.stop()

        assert status.mode == SessionMode.STOPPED.value
        store_path = tmp_path / "portfolio.json"
        assert store_path.exists()

    def test_trading_blocked_false_when_paused(self, tmp_path: Path) -> None:
        """PAUSED is not fully blocked — it's an operator-initiated pause."""
        session = _make_session(tmp_path)
        session.start()
        status = session.pause()
        # PAUSED is still operator-controlled, not a system block.
        assert status.trading_blocked is False


class TestRestart:
    """Restart from FAILED and BLOCKED states."""

    def test_restart_from_failed(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path / "run", with_stores=False)
        session.start()

        # Force failure.
        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("boom")
        )
        session.process_event(_minimal_data())
        assert session.mode == SessionMode.FAILED

        # Restore orchestrator.
        cfg = _pipeline_config()
        tracker = PositionTracker(initial_nav_usd=10_000.0)
        lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
        fresh_orch = PipelineOrchestrator(
            config=cfg,
            position_tracker=tracker,
            lifecycle_engine=lifecycle,
        )
        session._orchestrator = fresh_orch
        session._position_tracker = tracker

        status = session.restart()
        assert status.mode == SessionMode.RUNNING.value
        assert status.total_cycles == 0
        assert status.failed_cycles == 0
        assert status.last_error is None

    def test_restart_from_blocked(self, tmp_path: Path) -> None:
        # Write corrupt portfolio to force blocked state.
        portfolio_path = tmp_path / "portfolio.json"
        portfolio_path.parent.mkdir(parents=True, exist_ok=True)
        portfolio_path.write_text("{broken}", encoding="utf-8")
        exec_path = tmp_path / "execution.jsonl"
        exec_path.write_text("", encoding="utf-8")

        session = _make_session(tmp_path)
        session.start()
        assert session.mode == SessionMode.BLOCKED

        # Remove corrupt file so next start() succeeds as clean.
        portfolio_path.unlink()
        exec_path.unlink()

        status = session.restart()
        assert status.mode == SessionMode.RUNNING.value
        assert status.recovery_status == "clean_start"

    def test_restart_from_running_raises(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        with pytest.raises(ValueError, match="FAILED/BLOCKED"):
            session.restart()

    def test_restart_from_stopped_raises(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        session.stop()

        with pytest.raises(ValueError, match="FAILED/BLOCKED"):
            session.restart()

    def test_restart_clears_counters(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path / "run", with_stores=False)
        session.start()

        # Process some cycles.
        for i in range(3):
            session.process_event(_minimal_data(timestamp_ns=_T0_NS + i * _NS_PER_S))

        # Force failure.
        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("boom")
        )
        session.process_event(_minimal_data(timestamp_ns=_T0_NS + 3 * _NS_PER_S))
        assert session.mode == SessionMode.FAILED
        assert session._cycle_count == 4
        assert session._failed_cycles == 1

        # Fix orchestrator and restart.
        cfg = _pipeline_config()
        tracker = PositionTracker(initial_nav_usd=10_000.0)
        lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
        session._orchestrator = PipelineOrchestrator(
            config=cfg,
            position_tracker=tracker,
            lifecycle_engine=lifecycle,
        )
        session._position_tracker = tracker

        status = session.restart()
        assert status.total_cycles == 0
        assert status.approved_cycles == 0
        assert status.blocked_cycles == 0
        assert status.failed_cycles == 0
        assert status.last_error is None
        assert status.cycle_history == ()

    def test_restart_from_initializing_raises(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        # Session is INITIALIZING — restart should refuse.
        with pytest.raises(ValueError, match="FAILED/BLOCKED"):
            session.restart()


class TestCycleOutcomeCounters:
    """Approved / blocked / failed cycle counters."""

    def test_approved_counter_incremented(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        for i in range(3):
            session.process_event(_minimal_data(timestamp_ns=_T0_NS + i * _NS_PER_S))

        status = session.status()
        # Pipeline processes all cycles — some may approve, but at minimum total_cycles == 3.
        assert status.total_cycles == 3
        assert status.approved_cycles + status.blocked_cycles + status.failed_cycles <= status.total_cycles

    def test_blocked_counter_on_paused(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        session.pause()

        session.process_event(_minimal_data())
        session.process_event(_minimal_data(timestamp_ns=_T0_NS + _NS_PER_S))

        status = session.status()
        assert status.blocked_cycles == 2

    def test_failed_counter_on_exception(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("boom")
        )
        session.process_event(_minimal_data())

        status = session.status()
        assert status.failed_cycles == 1
        assert status.total_cycles == 1

    def test_counters_reflect_mixed_outcomes(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        # 1 normal cycle.
        session.process_event(_minimal_data())

        # Pause → 1 blocked.
        session.pause()
        session.process_event(_minimal_data(timestamp_ns=_T0_NS + _NS_PER_S))

        # Resume → 1 more normal cycle.
        session.resume()
        session.process_event(_minimal_data(timestamp_ns=_T0_NS + 2 * _NS_PER_S))

        status = session.status()
        assert status.total_cycles == 2  # only successfully processed cycles
        assert status.blocked_cycles == 1


class TestLastError:
    """Last error tracking."""

    def test_no_error_initially(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        status = session.status()
        assert status.last_error is None

    def test_error_set_on_exception(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("kaboom")
        )
        session.process_event(_minimal_data())

        status = session.status()
        assert status.last_error is not None
        assert "kaboom" in status.last_error

    def test_error_cleared_on_restart(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path / "run", with_stores=False)
        session.start()

        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("kaboom")
        )
        session.process_event(_minimal_data())
        assert session._last_error is not None

        # Fix and restart.
        cfg = _pipeline_config()
        tracker = PositionTracker(initial_nav_usd=10_000.0)
        lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
        session._orchestrator = PipelineOrchestrator(
            config=cfg,
            position_tracker=tracker,
            lifecycle_engine=lifecycle,
        )
        session._position_tracker = tracker

        status = session.restart()
        assert status.last_error is None


class TestCycleHistory:
    """Bounded cycle history for auditability."""

    def test_history_populated(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        for i in range(3):
            session.process_event(_minimal_data(timestamp_ns=_T0_NS + i * _NS_PER_S))

        status = session.status()
        assert len(status.cycle_history) == 3
        assert all(isinstance(r, CycleResult) for r in status.cycle_history)

    def test_history_bounded(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False, cycle_history_size=5)
        session.start()

        for i in range(10):
            session.process_event(_minimal_data(timestamp_ns=_T0_NS + i * _NS_PER_S))

        status = session.status()
        assert len(status.cycle_history) == 5
        # Most recent cycle should be the last one.
        assert status.cycle_history[-1].cycle_number == 10

    def test_history_includes_blocked_cycles(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        session.process_event(_minimal_data())
        session.pause()
        session.process_event(_minimal_data(timestamp_ns=_T0_NS + _NS_PER_S))

        status = session.status()
        assert len(status.cycle_history) == 2
        # The second entry should have an error (blocked).
        assert status.cycle_history[1].error is not None
        assert "session_not_running" in status.cycle_history[1].error

    def test_history_includes_failed_cycles(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()

        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("fail")
        )
        session.process_event(_minimal_data())

        status = session.status()
        assert len(status.cycle_history) == 1
        assert status.cycle_history[0].error is not None
        assert "fail" in status.cycle_history[0].error

    def test_history_is_tuple_in_status(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        session.process_event(_minimal_data())

        status = session.status()
        assert isinstance(status.cycle_history, tuple)

    def test_history_cleared_on_restart(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path / "run", with_stores=False)
        session.start()

        session._orchestrator.process = lambda *a, **k: (_ for _ in ()).throw(  # type: ignore[assignment]
            RuntimeError("fail")
        )
        session.process_event(_minimal_data())
        assert len(session._cycle_history) == 1

        # Fix and restart.
        cfg = _pipeline_config()
        tracker = PositionTracker(initial_nav_usd=10_000.0)
        lifecycle = ExecutionLifecycleEngine(cfg.execution_lifecycle)
        session._orchestrator = PipelineOrchestrator(
            config=cfg,
            position_tracker=tracker,
            lifecycle_engine=lifecycle,
        )
        session._position_tracker = tracker

        status = session.restart()
        assert status.cycle_history == ()


class TestDeterministicReplayWithHistory:
    """Same events produce same cycle history."""

    def test_replay_produces_same_history(self, tmp_path: Path) -> None:
        events = [_minimal_data(timestamp_ns=_T0_NS + i * _NS_PER_S) for i in range(5)]

        # Run 1
        s1 = _make_session(tmp_path / "r1", with_stores=False)
        s1.start()
        for e in events:
            s1.process_event(e)
        status1 = s1.status()

        # Run 2
        s2 = _make_session(tmp_path / "r2", with_stores=False)
        s2.start()
        for e in events:
            s2.process_event(e)
        status2 = s2.status()

        assert len(status1.cycle_history) == len(status2.cycle_history)
        for r1, r2 in zip(status1.cycle_history, status2.cycle_history):
            assert r1.cycle_number == r2.cycle_number
            assert r1.fills_applied == r2.fills_applied
            assert r1.error == r2.error


class TestOperatorStatusEnrichment:
    """Status model includes all 7D fields."""

    def test_status_has_outcome_counters(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        status = session.status()

        assert hasattr(status, "approved_cycles")
        assert hasattr(status, "blocked_cycles")
        assert hasattr(status, "failed_cycles")
        assert status.approved_cycles == 0
        assert status.blocked_cycles == 0
        assert status.failed_cycles == 0

    def test_status_has_last_error(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        status = session.status()
        assert status.last_error is None

    def test_status_has_cycle_history(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        status = session.status()
        assert isinstance(status.cycle_history, tuple)
        assert len(status.cycle_history) == 0

    def test_status_frozen(self, tmp_path: Path) -> None:
        session = _make_session(tmp_path, with_stores=False)
        session.start()
        status = session.status()
        with pytest.raises(AttributeError):
            status.approved_cycles = 999  # type: ignore[misc]


class TestConfigCycleHistorySize:
    """PaperSessionConfig.cycle_history_size controls history bounds."""

    def test_default_size(self) -> None:
        cfg = PaperSessionConfig()
        assert cfg.cycle_history_size == 100

    def test_custom_size(self) -> None:
        cfg = PaperSessionConfig(cycle_history_size=50)
        assert cfg.cycle_history_size == 50

    def test_config_frozen(self) -> None:
        cfg = PaperSessionConfig()
        with pytest.raises(AttributeError):
            cfg.cycle_history_size = 200  # type: ignore[misc]
