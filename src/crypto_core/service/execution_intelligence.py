"""Execution intelligence bootstrap — Phase 9E.

Deterministic construction of execution intelligence components
(route binding, TCA loop, TCA store) from service-level configuration.

Ownership: the service layer builds these once and injects them into
the session/orchestrator construction path.  No duplicate bootstrap
logic in lower layers.

Design rules:
  - STRICT mode: missing dependencies → startup fails closed.
  - OPTIONAL mode: missing dependencies → degrade with explicit reasons.
  - DISABLED mode: no components built; no degradation reported.
  - Bootstrap is deterministic and idempotent.
  - Replay-dedup loading is part of bootstrap (if store exists).

PRD reference: §7 Execution Engine, §2 System Orchestration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from crypto_core.execution.markout import MarkoutObserver, MarkoutObserverConfig
from crypto_core.execution.route_binding import MetadataGatedRouter
from crypto_core.execution.tca_loop import ExecutionTCALoop, TCALoopConfig
from crypto_core.execution.tca_store import TCAStore
from crypto_core.execution.venue_scoring import ExpectedCostCalculator, RoutingEngine, VenueScoringEngine
from crypto_core.service.models import (
    ExecutionIntelligenceConfig,
    ExecutionIntelligenceMode,
    ExecutionIntelligenceStatus,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BootstrapResult:
    """Result of execution intelligence bootstrap.

    Contains constructed components (or None) and operator-visible status.
    """

    router: MetadataGatedRouter | None
    tca_loop: ExecutionTCALoop | None
    tca_store: TCAStore | None
    status: ExecutionIntelligenceStatus
    error: str | None = None


class ExecutionIntelligenceBootstrap:
    """Builds execution intelligence components from service config.

    Usage::

        bootstrap = ExecutionIntelligenceBootstrap()
        result = bootstrap.build(config)
        if result.error:
            # STRICT mode failure — do not start service
            raise RuntimeError(result.error)
        # Wire result.router, result.tca_loop, result.tca_store into session/orch
    """

    def build(self, config: ExecutionIntelligenceConfig) -> BootstrapResult:
        """Construct execution intelligence components.

        DISABLED: returns empty result, no degradation.
        OPTIONAL: builds what it can, reports degraded reasons.
        STRICT: builds all; returns error if any dependency is missing.
        """
        if config.mode == ExecutionIntelligenceMode.DISABLED:
            return BootstrapResult(
                router=None,
                tca_loop=None,
                tca_store=None,
                status=ExecutionIntelligenceStatus(
                    mode=config.mode.value,
                    route_binding_enabled=False,
                    tca_loop_enabled=False,
                    tca_store_available=False,
                    replay_dedup_bootstrapped=False,
                    degraded=False,
                ),
            )

        degraded_reasons: list[str] = []
        router: MetadataGatedRouter | None = None
        tca_loop: ExecutionTCALoop | None = None
        tca_store: TCAStore | None = None

        # 1. Build router
        try:
            router = self._build_router()
        except Exception as exc:
            reason = f"router_build_failed: {exc}"
            logger.error("Execution intelligence: %s", reason)
            degraded_reasons.append(reason)

        # 2. Build TCA store
        if config.tca_store_path is not None:
            try:
                tca_store = TCAStore(path=Path(config.tca_store_path))
            except Exception as exc:
                reason = f"tca_store_build_failed: {exc}"
                logger.error("Execution intelligence: %s", reason)
                degraded_reasons.append(reason)
        else:
            degraded_reasons.append("tca_store_path_not_configured")

        # 3. Build TCA loop
        try:
            tca_loop = self._build_tca_loop(config, tca_store)
        except Exception as exc:
            reason = f"tca_loop_build_failed: {exc}"
            logger.error("Execution intelligence: %s", reason)
            degraded_reasons.append(reason)

        # 4. Strict mode enforcement
        if config.mode == ExecutionIntelligenceMode.STRICT:
            if router is None:
                return BootstrapResult(
                    router=None,
                    tca_loop=None,
                    tca_store=None,
                    status=self._degraded_status(config, degraded_reasons),
                    error="STRICT mode: router construction failed",
                )
            if tca_loop is None:
                return BootstrapResult(
                    router=None,
                    tca_loop=None,
                    tca_store=None,
                    status=self._degraded_status(config, degraded_reasons),
                    error="STRICT mode: TCA loop construction failed",
                )
            if tca_store is None:
                return BootstrapResult(
                    router=None,
                    tca_loop=None,
                    tca_store=None,
                    status=self._degraded_status(config, degraded_reasons),
                    error="STRICT mode: TCA store not available",
                )

        degraded = bool(degraded_reasons)
        status = ExecutionIntelligenceStatus(
            mode=config.mode.value,
            route_binding_enabled=router is not None,
            tca_loop_enabled=tca_loop is not None,
            tca_store_available=tca_store is not None,
            replay_dedup_bootstrapped=False,  # set True after dedup load
            degraded=degraded,
            degraded_reasons=tuple(degraded_reasons),
        )

        return BootstrapResult(
            router=router,
            tca_loop=tca_loop,
            tca_store=tca_store,
            status=status,
        )

    @staticmethod
    def _build_router() -> MetadataGatedRouter:
        scorer = VenueScoringEngine()
        cost_calc = ExpectedCostCalculator()
        routing_engine = RoutingEngine(scorer, cost_calc)
        return MetadataGatedRouter(routing_engine)

    @staticmethod
    def _build_tca_loop(
        config: ExecutionIntelligenceConfig,
        tca_store: TCAStore | None,
    ) -> ExecutionTCALoop:
        observer = MarkoutObserver(
            config=MarkoutObserverConfig(horizons=config.tca_horizons),
        )
        return ExecutionTCALoop(
            markout_observer=observer,
            tca_store=tca_store,
            config=TCALoopConfig(
                auto_persist_on_complete=config.auto_persist_tca,
            ),
        )

    @staticmethod
    def _degraded_status(
        config: ExecutionIntelligenceConfig,
        reasons: list[str],
    ) -> ExecutionIntelligenceStatus:
        return ExecutionIntelligenceStatus(
            mode=config.mode.value,
            route_binding_enabled=False,
            tca_loop_enabled=False,
            tca_store_available=False,
            replay_dedup_bootstrapped=False,
            degraded=True,
            degraded_reasons=tuple(reasons),
        )
