"""Live package: iDeal tail paper runner + legacy paper trading (local files, no network)."""

from __future__ import annotations

from bist_core.live.data_feed import IdealDataFeed
from bist_core.live.data_hardening import DataHardeningEngine
from bist_core.live.execution_runtime import PaperExecution
from bist_core.live.health import get_health
from bist_core.live.paper_trader import PaperTrader, compute_paper_metrics
from bist_core.live.performance_tracker import PerformanceTracker
from bist_core.live.report import generate_daily_report
from bist_core.live.scheduler import is_market_open
from bist_core.live.state import initialize_state, load_state, save_state
from bist_core.live.state_store import LiveState


def __getattr__(name: str) -> object:
    """Lazy import so ``python -m bist_core.live.live_runner`` does not preload this module."""
    if name == "LiveRunner":
        from bist_core.live.live_runner import LiveRunner as _LiveRunner

        return _LiveRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "DataHardeningEngine",
    "IdealDataFeed",
    "LiveRunner",
    "PerformanceTracker",
    "LiveState",
    "PaperExecution",
    "PaperTrader",
    "compute_paper_metrics",
    "generate_daily_report",
    "get_health",
    "initialize_state",
    "is_market_open",
    "load_state",
    "save_state",
]
