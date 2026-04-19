"""Paper-live campaign models + acceptance policy — Phase 8D.

Provides:
  1. CampaignStatus — deterministic campaign lifecycle states.
  2. AcceptanceVerdict — pass/fail/inconclusive outcome.
  3. CampaignConfig — campaign parameters and acceptance thresholds.
  4. AcceptancePolicy — deterministic go/no-go evaluation.
  5. CampaignSnapshot — point-in-time campaign state.
  6. CampaignReport — final campaign report with verdict evidence.
  7. SymbolParticipation — per-symbol activity accounting.

Design rules:
  - All verdict logic is deterministic and threshold-based.
  - Fail-closed: insufficient coverage → INCONCLUSIVE, not silent PASS.
  - Frozen dataclasses for all snapshots and reports.
  - Operator clarity: every verdict carries explicit reason codes.
  - PAPER-ONLY: no real-money concepts.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Campaign status lifecycle
# ---------------------------------------------------------------------------


class CampaignStatus(str, Enum):
    """Deterministic campaign lifecycle states.

    CREATED   → start() → RUNNING
    RUNNING   → pause() → PAUSED
    RUNNING   → complete / limits → COMPLETED
    RUNNING   → abort() → ABORTED
    RUNNING   → fatal → FAILED
    PAUSED    → resume() → RUNNING
    PAUSED    → abort() → ABORTED
    COMPLETED → finalize() → verdict applied (COMPLETED stays terminal)
    FAILED    → (terminal)
    ABORTED   → (terminal)
    REJECTED  → (terminal, set when finalize verdict = FAIL)
    """

    CREATED = "created"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"
    REJECTED = "rejected"


_TERMINAL_STATUSES = frozenset(
    {CampaignStatus.COMPLETED, CampaignStatus.FAILED, CampaignStatus.ABORTED, CampaignStatus.REJECTED}
)


# ---------------------------------------------------------------------------
# Acceptance verdict
# ---------------------------------------------------------------------------


class AcceptanceVerdict(str, Enum):
    """Go/no-go outcome for a campaign.

    PASS:               all criteria met, no warnings.
    PASS_WITH_WARNINGS: all hard criteria met, some soft thresholds breached.
    FAIL:               one or more hard criteria breached.
    INCONCLUSIVE:       insufficient evidence to determine outcome.
    """

    PASS = "pass"  # noqa: S105
    PASS_WITH_WARNINGS = "pass_with_warnings"  # noqa: S105
    FAIL = "fail"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Campaign configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceThresholds:
    """Threshold configuration for the acceptance policy.

    Hard thresholds → breach causes FAIL.
    Soft thresholds → breach causes WARNING.
    Coverage thresholds → insufficient → INCONCLUSIVE.
    """

    # --- Hard failure thresholds ---
    max_failed_cycles: int = 50
    max_blocked_cycle_ratio: float = 0.5
    max_queue_overflows: int = 10
    max_watchdog_stalls: int = 5
    max_persistence_failures: int = 20
    max_service_restarts: int = 3

    # --- Soft warning thresholds ---
    warn_failed_cycles: int = 10
    warn_blocked_cycle_ratio: float = 0.2
    warn_queue_overflows: int = 3
    warn_persistence_failures: int = 5
    warn_ei_route_blocks: int = 10
    warn_ei_route_abstains: int = 20

    # --- Execution intelligence hard thresholds (Phase 10A) ---
    max_ei_route_blocks: int = 100
    max_ei_route_abstains: int = 200
    ei_degraded_is_hard_fail: bool = False

    # --- Stability hard thresholds (Phase 10A) ---
    max_recovery_incidents: int = 5
    max_degraded_intervals: int = 50

    # --- Minimum coverage (insufficient → INCONCLUSIVE) ---
    min_events_processed: int = 100
    min_cycles_processed: int = 10
    min_symbols_observed: int = 1
    min_campaign_duration_s: float = 0.0


@dataclass(frozen=True)
class CampaignConfig:
    """Configuration for a paper-live campaign.

    campaign_id:       optional pre-assigned campaign ID.
    max_duration_s:    maximum wall-clock duration; 0 = unlimited.
    max_events:        maximum events; 0 = unlimited.
    max_cycles:        maximum cycles; 0 = unlimited.
    target_symbols:    symbols to track (empty = all registered).
    target_exchanges:  exchanges to track (empty = all registered).
    thresholds:        acceptance thresholds.
    """

    campaign_id: str = ""
    max_duration_s: float = 0.0
    max_events: int = 0
    max_cycles: int = 0
    target_symbols: tuple[str, ...] = ()
    target_exchanges: tuple[str, ...] = ()
    thresholds: AcceptanceThresholds = field(default_factory=AcceptanceThresholds)


# ---------------------------------------------------------------------------
# Symbol participation accounting
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SymbolParticipation:
    """Per-symbol activity accounting within a campaign.

    symbol:          symbol name.
    exchange:        exchange name.
    feed_ready:      True if feed was ready at last check.
    blocked:         True if symbol was blocked at last check.
    events_observed: True if any events arrived for this symbol.
    cycles_observed: True if any cycles ran for this symbol.
    """

    symbol: str
    exchange: str
    feed_ready: bool
    blocked: bool
    events_observed: bool
    cycles_observed: bool


# ---------------------------------------------------------------------------
# Acceptance criterion result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CriterionResult:
    """Result of evaluating one acceptance criterion.

    name:       criterion identifier.
    passed:     True if criterion passed.
    severity:   'hard', 'soft', or 'coverage'.
    actual:     actual observed value.
    threshold:  configured threshold.
    message:    human-readable explanation.
    """

    name: str
    passed: bool
    severity: str
    actual: float
    threshold: float
    message: str


# ---------------------------------------------------------------------------
# Acceptance evaluation result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AcceptanceResult:
    """Full acceptance evaluation result.

    verdict:            final AcceptanceVerdict.
    criteria:           tuple of all evaluated CriterionResult.
    failed_criteria:    tuple of criteria that caused FAIL.
    warning_criteria:   tuple of criteria that caused WARNING.
    insufficient_criteria: tuple of criteria that caused INCONCLUSIVE.
    summary:            human-readable summary.
    """

    verdict: AcceptanceVerdict
    criteria: tuple[CriterionResult, ...]
    failed_criteria: tuple[CriterionResult, ...]
    warning_criteria: tuple[CriterionResult, ...]
    insufficient_criteria: tuple[CriterionResult, ...]
    summary: str


# ---------------------------------------------------------------------------
# Stability rollup (Phase 10A)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StabilityRollup:
    """Compact campaign-grade stability evidence.

    Separates raw operator metrics from campaign-grade acceptance evidence.
    All counters are campaign-scoped (not session-lifetime).
    """

    degraded_intervals: int
    blocked_intervals: int
    recovery_incidents: int
    queue_overflow_incidents: int
    queue_pressure_warnings: int
    persistence_failure_count: int
    ei_degraded: bool
    ei_degraded_reasons: tuple[str, ...] = ()
    ei_route_blocks: int = 0
    ei_route_abstains: int = 0


# ---------------------------------------------------------------------------
# Campaign snapshot
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignSnapshot:
    """Point-in-time campaign state for operator inspection.

    Frozen — safe to pass across threads.
    """

    campaign_id: str
    status: str
    started_at_ns: int
    updated_at_ns: int
    elapsed_seconds: float
    run_id: str
    service_mode: str
    session_mode: str
    total_events_enqueued: int
    total_events_dropped: int
    total_cycles: int
    approved_cycles: int
    blocked_cycles: int
    failed_cycles: int
    total_fills: int
    queue_overflows: int
    watchdog_stalls: int
    service_restarts: int
    persistence_failures: int
    symbol_count: int
    symbols_ready: int
    symbols_blocked: int
    symbols_with_events: int
    symbols_with_cycles: int
    readiness_level: str
    health_trend: str
    persistence_status: str
    nav_usd: float | None
    last_error: str | None
    # Phase 10A: execution intelligence + stability
    ei_degraded: bool = False
    ei_route_blocks: int = 0
    ei_route_abstains: int = 0
    recovery_incidents: int = 0
    stability: StabilityRollup | None = None
    # Phase 10D: execution evidence propagation
    pending_markout_count: int = 0
    completed_markout_count: int = 0
    persisted_tca_count: int = 0
    persisted_attribution_count: int = 0
    registered_fill_count: int = 0


# ---------------------------------------------------------------------------
# Campaign report
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignReport:
    """Final campaign report with verdict evidence.

    Answers: why did this campaign pass/fail/end inconclusive?
    """

    campaign_id: str
    status: str
    verdict: str
    started_at_ns: int
    completed_at_ns: int
    elapsed_seconds: float
    run_id: str
    snapshot: CampaignSnapshot
    acceptance: AcceptanceResult
    symbol_participation: tuple[SymbolParticipation, ...]
    config: dict
    stability: StabilityRollup | None = None


# ---------------------------------------------------------------------------
# Acceptance policy — deterministic evaluator
# ---------------------------------------------------------------------------


class AcceptancePolicy:
    """Deterministic go/no-go evaluator for paper-live campaigns.

    Evaluates a CampaignSnapshot against AcceptanceThresholds.
    Pure logic — no side effects, no I/O.

    Usage::

        policy = AcceptancePolicy(thresholds)
        result = policy.evaluate(snapshot)
        if result.verdict == AcceptanceVerdict.PASS:
            ...
    """

    def __init__(self, thresholds: AcceptanceThresholds | None = None) -> None:
        self._t = thresholds or AcceptanceThresholds()

    @property
    def thresholds(self) -> AcceptanceThresholds:
        return self._t

    def evaluate(self, snapshot: CampaignSnapshot) -> AcceptanceResult:
        """Evaluate campaign snapshot against acceptance criteria.

        Returns:
            AcceptanceResult with deterministic verdict and reason codes.
        """
        criteria: list[CriterionResult] = []
        t = self._t

        # --- Coverage checks ---
        criteria.append(
            self._check_coverage(
                "min_events_processed",
                snapshot.total_events_enqueued,
                t.min_events_processed,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_cycles_processed",
                snapshot.total_cycles,
                t.min_cycles_processed,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_symbols_observed",
                snapshot.symbols_with_events,
                t.min_symbols_observed,
            )
        )
        if t.min_campaign_duration_s > 0:
            criteria.append(
                self._check_coverage(
                    "min_campaign_duration_s",
                    snapshot.elapsed_seconds,
                    t.min_campaign_duration_s,
                )
            )

        # --- Hard failure checks ---
        criteria.append(
            self._check_hard(
                "max_failed_cycles",
                snapshot.failed_cycles,
                t.max_failed_cycles,
            )
        )
        blocked_ratio = snapshot.blocked_cycles / snapshot.total_cycles if snapshot.total_cycles > 0 else 0.0
        criteria.append(
            self._check_hard(
                "max_blocked_cycle_ratio",
                blocked_ratio,
                t.max_blocked_cycle_ratio,
            )
        )
        criteria.append(
            self._check_hard(
                "max_queue_overflows",
                snapshot.queue_overflows,
                t.max_queue_overflows,
            )
        )
        criteria.append(
            self._check_hard(
                "max_watchdog_stalls",
                snapshot.watchdog_stalls,
                t.max_watchdog_stalls,
            )
        )
        criteria.append(
            self._check_hard(
                "max_persistence_failures",
                snapshot.persistence_failures,
                t.max_persistence_failures,
            )
        )
        criteria.append(
            self._check_hard(
                "max_service_restarts",
                snapshot.service_restarts,
                t.max_service_restarts,
            )
        )

        # --- Soft warning checks ---
        criteria.append(
            self._check_soft(
                "warn_failed_cycles",
                snapshot.failed_cycles,
                t.warn_failed_cycles,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_blocked_cycle_ratio",
                blocked_ratio,
                t.warn_blocked_cycle_ratio,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_queue_overflows",
                snapshot.queue_overflows,
                t.warn_queue_overflows,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_persistence_failures",
                snapshot.persistence_failures,
                t.warn_persistence_failures,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_ei_route_blocks",
                snapshot.ei_route_blocks,
                t.warn_ei_route_blocks,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_ei_route_abstains",
                snapshot.ei_route_abstains,
                t.warn_ei_route_abstains,
            )
        )

        # --- Phase 10A: Execution intelligence hard checks ---
        criteria.append(
            self._check_hard(
                "max_ei_route_blocks",
                snapshot.ei_route_blocks,
                t.max_ei_route_blocks,
            )
        )
        criteria.append(
            self._check_hard(
                "max_ei_route_abstains",
                snapshot.ei_route_abstains,
                t.max_ei_route_abstains,
            )
        )
        if t.ei_degraded_is_hard_fail:
            criteria.append(
                CriterionResult(
                    name="ei_degraded",
                    passed=not snapshot.ei_degraded,
                    severity="hard",
                    actual=1.0 if snapshot.ei_degraded else 0.0,
                    threshold=0.0,
                    message=f"ei_degraded: {'degraded' if snapshot.ei_degraded else 'healthy'}",
                )
            )

        # --- Phase 10A: Stability hard checks ---
        criteria.append(
            self._check_hard(
                "max_recovery_incidents",
                snapshot.recovery_incidents,
                t.max_recovery_incidents,
            )
        )
        if snapshot.stability is not None:
            criteria.append(
                self._check_hard(
                    "max_degraded_intervals",
                    snapshot.stability.degraded_intervals,
                    t.max_degraded_intervals,
                )
            )

        # --- Classify ---
        failed = tuple(c for c in criteria if not c.passed and c.severity == "hard")
        warnings = tuple(c for c in criteria if not c.passed and c.severity == "soft")
        insufficient = tuple(c for c in criteria if not c.passed and c.severity == "coverage")

        if insufficient:
            verdict = AcceptanceVerdict.INCONCLUSIVE
            summary = f"Insufficient coverage: {len(insufficient)} criteria below minimum. Cannot determine pass/fail."
        elif failed:
            verdict = AcceptanceVerdict.FAIL
            summary = f"FAIL: {len(failed)} hard criteria breached. " + "; ".join(c.message for c in failed)
        elif warnings:
            verdict = AcceptanceVerdict.PASS_WITH_WARNINGS
            summary = f"PASS with {len(warnings)} warnings. " + "; ".join(c.message for c in warnings)
        else:
            verdict = AcceptanceVerdict.PASS
            summary = "All acceptance criteria met."

        return AcceptanceResult(
            verdict=verdict,
            criteria=tuple(criteria),
            failed_criteria=failed,
            warning_criteria=warnings,
            insufficient_criteria=insufficient,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_coverage(name: str, actual: float, minimum: float) -> CriterionResult:
        passed = actual >= minimum
        return CriterionResult(
            name=name,
            passed=passed,
            severity="coverage",
            actual=actual,
            threshold=minimum,
            message=f"{name}: {actual} {'≥' if passed else '<'} {minimum}",
        )

    @staticmethod
    def _check_hard(name: str, actual: float, maximum: float) -> CriterionResult:
        passed = actual <= maximum
        return CriterionResult(
            name=name,
            passed=passed,
            severity="hard",
            actual=actual,
            threshold=maximum,
            message=f"{name}: {actual} {'≤' if passed else '>'} {maximum}",
        )

    @staticmethod
    def _check_soft(name: str, actual: float, maximum: float) -> CriterionResult:
        passed = actual <= maximum
        return CriterionResult(
            name=name,
            passed=passed,
            severity="soft",
            actual=actual,
            threshold=maximum,
            message=f"{name}: {actual} {'≤' if passed else '>'} {maximum}",
        )


# ---------------------------------------------------------------------------
# Campaign metadata (mutable, used by controller)
# ---------------------------------------------------------------------------


def new_campaign_id() -> str:
    """Generate a new campaign identifier."""
    return str(uuid.uuid4())


@dataclass
class CampaignMetadata:
    """Mutable campaign metadata maintained by the controller.

    This is the internal bookkeeping structure — not exposed to operators
    directly. Use CampaignSnapshot / CampaignReport for operator views.
    """

    campaign_id: str
    config: CampaignConfig
    status: CampaignStatus = CampaignStatus.CREATED
    run_id: str = ""
    started_at_ns: int = 0
    updated_at_ns: int = 0
    completed_at_ns: int = 0
    paused_at_ns: int = 0
    total_pause_duration_ns: int = 0
    watchdog_stalls: int = 0
    service_restarts: int = 0
    queue_overflows: int = 0
    persistence_failures: int = 0
    verdict: AcceptanceVerdict | None = None
    verdict_reason: str = ""
    # Phase 10A: EI + stability tracking
    ei_degraded: bool = False
    ei_degraded_reasons: tuple[str, ...] = ()
    ei_route_blocks: int = 0
    ei_route_abstains: int = 0
    recovery_incidents: int = 0
    degraded_intervals: int = 0
    blocked_intervals: int = 0
    queue_pressure_warnings: int = 0
    # Phase 10D: execution evidence counters
    pending_markout_count: int = 0
    completed_markout_count: int = 0
    persisted_tca_count: int = 0
    persisted_attribution_count: int = 0
    registered_fill_count: int = 0

    def elapsed_seconds(self) -> float:
        """Wall-clock elapsed seconds excluding paused time."""
        if self.started_at_ns == 0:
            return 0.0
        end = self.completed_at_ns or time.time_ns()
        total_ns = end - self.started_at_ns - self.total_pause_duration_ns
        return max(0.0, total_ns / 1_000_000_000)

    def to_dict(self) -> dict:
        """Serialize to a plain dict for persistence."""
        return {
            "campaign_id": self.campaign_id,
            "status": self.status.value,
            "run_id": self.run_id,
            "started_at_ns": self.started_at_ns,
            "updated_at_ns": self.updated_at_ns,
            "completed_at_ns": self.completed_at_ns,
            "paused_at_ns": self.paused_at_ns,
            "total_pause_duration_ns": self.total_pause_duration_ns,
            "watchdog_stalls": self.watchdog_stalls,
            "service_restarts": self.service_restarts,
            "queue_overflows": self.queue_overflows,
            "persistence_failures": self.persistence_failures,
            "verdict": self.verdict.value if self.verdict else None,
            "verdict_reason": self.verdict_reason,
            "ei_degraded": self.ei_degraded,
            "ei_degraded_reasons": list(self.ei_degraded_reasons),
            "ei_route_blocks": self.ei_route_blocks,
            "ei_route_abstains": self.ei_route_abstains,
            "recovery_incidents": self.recovery_incidents,
            "degraded_intervals": self.degraded_intervals,
            "blocked_intervals": self.blocked_intervals,
            "queue_pressure_warnings": self.queue_pressure_warnings,
            "pending_markout_count": self.pending_markout_count,
            "completed_markout_count": self.completed_markout_count,
            "persisted_tca_count": self.persisted_tca_count,
            "persisted_attribution_count": self.persisted_attribution_count,
            "registered_fill_count": self.registered_fill_count,
            "config": {
                "campaign_id": self.config.campaign_id,
                "max_duration_s": self.config.max_duration_s,
                "max_events": self.config.max_events,
                "max_cycles": self.config.max_cycles,
                "target_symbols": list(self.config.target_symbols),
                "target_exchanges": list(self.config.target_exchanges),
            },
        }


class CampaignMetadataCorruptError(RuntimeError):
    """Raised when persisted campaign metadata is invalid."""


_CAMPAIGN_REQUIRED_FIELDS = frozenset(
    {
        "campaign_id",
        "status",
        "run_id",
        "started_at_ns",
        "updated_at_ns",
    }
)


def validate_campaign_metadata_dict(d: dict) -> None:
    """Fail-closed validation for persisted campaign metadata."""
    missing = _CAMPAIGN_REQUIRED_FIELDS - set(d)
    if missing:
        raise CampaignMetadataCorruptError(f"Campaign metadata missing required fields: {sorted(missing)!r}")
    if not isinstance(d["campaign_id"], str) or not d["campaign_id"]:
        raise CampaignMetadataCorruptError("campaign_id must be a non-empty string")
    try:
        CampaignStatus(d["status"])
    except ValueError as exc:
        raise CampaignMetadataCorruptError(f"Invalid campaign status: {d['status']!r}") from exc


def campaign_metadata_from_dict(d: dict, config: CampaignConfig | None = None) -> CampaignMetadata:
    """Restore CampaignMetadata from a validated dict."""
    validate_campaign_metadata_dict(d)
    cfg = config or CampaignConfig()
    verdict = None
    if d.get("verdict"):
        verdict = AcceptanceVerdict(d["verdict"])
    return CampaignMetadata(
        campaign_id=d["campaign_id"],
        config=cfg,
        status=CampaignStatus(d["status"]),
        run_id=d.get("run_id", ""),
        started_at_ns=d.get("started_at_ns", 0),
        updated_at_ns=d.get("updated_at_ns", 0),
        completed_at_ns=d.get("completed_at_ns", 0),
        paused_at_ns=d.get("paused_at_ns", 0),
        total_pause_duration_ns=d.get("total_pause_duration_ns", 0),
        watchdog_stalls=d.get("watchdog_stalls", 0),
        service_restarts=d.get("service_restarts", 0),
        queue_overflows=d.get("queue_overflows", 0),
        persistence_failures=d.get("persistence_failures", 0),
        verdict=verdict,
        verdict_reason=d.get("verdict_reason", ""),
        ei_degraded=d.get("ei_degraded", False),
        ei_degraded_reasons=tuple(d.get("ei_degraded_reasons", ())),
        ei_route_blocks=d.get("ei_route_blocks", 0),
        ei_route_abstains=d.get("ei_route_abstains", 0),
        recovery_incidents=d.get("recovery_incidents", 0),
        degraded_intervals=d.get("degraded_intervals", 0),
        blocked_intervals=d.get("blocked_intervals", 0),
        queue_pressure_warnings=d.get("queue_pressure_warnings", 0),
        pending_markout_count=d.get("pending_markout_count", 0),
        completed_markout_count=d.get("completed_markout_count", 0),
        persisted_tca_count=d.get("persisted_tca_count", 0),
        persisted_attribution_count=d.get("persisted_attribution_count", 0),
        registered_fill_count=d.get("registered_fill_count", 0),
    )
