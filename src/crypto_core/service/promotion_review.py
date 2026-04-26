"""Execution calibration + promotion review surface — Phase 10B.

Aggregates campaign evidence into execution calibration conclusions,
multi-campaign summaries, and deterministic promotion verdicts.

Provides:
  1. ExecutionCalibrationSummary — compact calibration-grade evidence from one campaign.
  2. CampaignAggregation — multi-campaign aggregate summary.
  3. PromotionVerdict — PROMOTE / HOLD / REJECT / INCONCLUSIVE.
  4. PromotionThresholds — configurable policy thresholds.
  5. PromotionCriterion — per-criterion evaluation result.
  6. PromotionResult — verdict + criteria + reason codes.
  7. PromotionReview — full review report combining calibration + aggregation + verdict.
  8. PromotionPolicy — deterministic evaluator.
  9. PromotionReviewStore — persistence via EvidenceStore.

Design rules:
  - Fail-closed: missing or insufficient evidence → INCONCLUSIVE, never silent PROMOTE.
  - Frozen dataclasses for all output models.
  - Deterministic: same inputs → same outputs.
  - Reuses campaign.CampaignReport, readiness.ReadinessLevel, evidence_store.EvidenceStore.
  - No single lucky campaign can trigger PROMOTE.
  - Explicit unavailable / insufficient-evidence states required.
  - PAPER-ONLY: no real-money concepts.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from enum import Enum

from crypto_core.service.campaign import AcceptanceVerdict, CampaignReport
from crypto_core.service.evidence_store import EvidenceStore, WriteResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Evidence sufficiency
# ---------------------------------------------------------------------------


class EvidenceSufficiency(str, Enum):
    """Evidence sufficiency classification.

    SUFFICIENT:     enough data to draw reliable conclusions.
    MARGINAL:       some data present but below ideal thresholds.
    INSUFFICIENT:   not enough data — conclusions would be unreliable.
    UNAVAILABLE:    no data at all for this dimension.
    """

    SUFFICIENT = "sufficient"
    MARGINAL = "marginal"
    INSUFFICIENT = "insufficient"
    UNAVAILABLE = "unavailable"


# ---------------------------------------------------------------------------
# Execution calibration summary (per-campaign)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionCalibrationSummary:
    """Compact calibration-grade execution evidence from a single campaign.

    Built from a CampaignReport's snapshot and stability rollup.
    All ratios are in [0.0, 1.0]; -1.0 means unavailable.
    """

    campaign_id: str

    # --- Volume metrics ---
    total_cycles: int
    total_fills: int
    total_events: int
    symbol_count: int
    symbols_with_events: int
    symbols_with_cycles: int
    elapsed_seconds: float

    # --- Route metrics ---
    route_block_count: int
    route_abstain_count: int
    route_block_ratio: float  # blocks / cycles; -1 if 0 cycles
    route_abstain_ratio: float  # abstains / cycles; -1 if 0 cycles

    # --- Markout / TCA metrics ---
    pending_markout_count: int
    completed_markout_count: int  # total_fills - pending (proxy)
    markout_completion_ratio: float  # completed / total_fills; -1 if 0 fills
    persisted_tca_count: int
    persisted_tca_ratio: float  # persisted / total_fills; -1 if 0 fills
    persisted_attribution_count: int

    # --- Stability metrics ---
    degraded_intervals: int
    blocked_intervals: int
    recovery_incidents: int
    ei_degraded: bool
    blocked_cycle_ratio: float  # blocked / total; -1 if 0 cycles
    failed_cycle_ratio: float  # failed / total; -1 if 0 cycles

    # --- Sufficiency judgments ---
    markout_sufficiency: EvidenceSufficiency
    tca_sufficiency: EvidenceSufficiency
    campaign_breadth_sufficiency: EvidenceSufficiency
    symbol_participation_sufficiency: EvidenceSufficiency


def build_execution_calibration(
    report: CampaignReport,
    *,
    min_fills_sufficient: int = 20,
    min_fills_marginal: int = 5,
    min_tca_ratio_sufficient: float = 0.7,
    min_tca_ratio_marginal: float = 0.3,
    min_cycles_sufficient: int = 100,
    min_cycles_marginal: int = 20,
    min_symbols_sufficient: int = 3,
    min_symbols_marginal: int = 1,
) -> ExecutionCalibrationSummary:
    """Build an execution calibration summary from a campaign report.

    Pure function. No I/O. Deterministic.
    """
    snap = report.snapshot
    stab = report.stability

    total_fills = snap.total_fills
    total_cycles = snap.total_cycles

    # Route ratios
    route_block_ratio = snap.ei_route_blocks / total_cycles if total_cycles > 0 else -1.0
    route_abstain_ratio = snap.ei_route_abstains / total_cycles if total_cycles > 0 else -1.0

    # Phase 10D: execution evidence propagated from campaign snapshot.
    pending_markout_count = getattr(snap, "pending_markout_count", 0)
    completed_markout_count = getattr(snap, "completed_markout_count", 0)
    registered_fill_count = getattr(snap, "registered_fill_count", 0)
    persisted_tca_count = getattr(snap, "persisted_tca_count", 0)
    persisted_attribution_count = getattr(snap, "persisted_attribution_count", 0)

    # Markout completion ratio: prefer EI-registered fill denominator.
    if registered_fill_count > 0:
        markout_completion_ratio = completed_markout_count / registered_fill_count
    elif total_fills > 0:
        # No EI-registered fills — fall back to fill-based proxy.
        completed_markout_count = total_fills
        markout_completion_ratio = 1.0
    else:
        markout_completion_ratio = -1.0

    # TCA persistence ratio: based on registered fills (EI denominator).
    if registered_fill_count > 0:
        persisted_tca_ratio = persisted_tca_count / registered_fill_count
    elif total_fills > 0 and persisted_tca_count > 0:
        persisted_tca_ratio = persisted_tca_count / total_fills
    else:
        persisted_tca_ratio = -1.0

    # Blocked / failed cycle ratios
    blocked_cycle_ratio = snap.blocked_cycles / total_cycles if total_cycles > 0 else -1.0
    failed_cycle_ratio = snap.failed_cycles / total_cycles if total_cycles > 0 else -1.0

    # Stability from rollup
    degraded_intervals = stab.degraded_intervals if stab else 0
    blocked_intervals = stab.blocked_intervals if stab else 0
    recovery_incidents = stab.recovery_incidents if stab else 0
    ei_degraded = stab.ei_degraded if stab else snap.ei_degraded

    # --- Sufficiency judgments ---
    # Markout
    if total_fills >= min_fills_sufficient:
        markout_sufficiency = EvidenceSufficiency.SUFFICIENT
    elif total_fills >= min_fills_marginal:
        markout_sufficiency = EvidenceSufficiency.MARGINAL
    elif total_fills > 0:
        markout_sufficiency = EvidenceSufficiency.INSUFFICIENT
    else:
        markout_sufficiency = EvidenceSufficiency.UNAVAILABLE

    # TCA
    if persisted_tca_ratio >= min_tca_ratio_sufficient:
        tca_sufficiency = EvidenceSufficiency.SUFFICIENT
    elif persisted_tca_ratio >= min_tca_ratio_marginal:
        tca_sufficiency = EvidenceSufficiency.MARGINAL
    elif persisted_tca_ratio > 0:
        tca_sufficiency = EvidenceSufficiency.INSUFFICIENT
    else:
        # ratio is -1 (unavailable) or 0
        tca_sufficiency = EvidenceSufficiency.UNAVAILABLE

    # Campaign breadth
    if total_cycles >= min_cycles_sufficient:
        campaign_breadth_sufficiency = EvidenceSufficiency.SUFFICIENT
    elif total_cycles >= min_cycles_marginal:
        campaign_breadth_sufficiency = EvidenceSufficiency.MARGINAL
    elif total_cycles > 0:
        campaign_breadth_sufficiency = EvidenceSufficiency.INSUFFICIENT
    else:
        campaign_breadth_sufficiency = EvidenceSufficiency.UNAVAILABLE

    # Symbol participation
    if snap.symbols_with_events >= min_symbols_sufficient:
        symbol_participation_sufficiency = EvidenceSufficiency.SUFFICIENT
    elif snap.symbols_with_events >= min_symbols_marginal:
        symbol_participation_sufficiency = EvidenceSufficiency.MARGINAL
    elif snap.symbols_with_events > 0:
        symbol_participation_sufficiency = EvidenceSufficiency.INSUFFICIENT
    else:
        symbol_participation_sufficiency = EvidenceSufficiency.UNAVAILABLE

    return ExecutionCalibrationSummary(
        campaign_id=report.campaign_id,
        total_cycles=total_cycles,
        total_fills=total_fills,
        total_events=snap.total_events_enqueued,
        symbol_count=snap.symbol_count,
        symbols_with_events=snap.symbols_with_events,
        symbols_with_cycles=snap.symbols_with_cycles,
        elapsed_seconds=snap.elapsed_seconds,
        route_block_count=snap.ei_route_blocks,
        route_abstain_count=snap.ei_route_abstains,
        route_block_ratio=route_block_ratio,
        route_abstain_ratio=route_abstain_ratio,
        pending_markout_count=pending_markout_count,
        completed_markout_count=completed_markout_count,
        markout_completion_ratio=markout_completion_ratio,
        persisted_tca_count=persisted_tca_count,
        persisted_tca_ratio=persisted_tca_ratio,
        persisted_attribution_count=persisted_attribution_count,
        degraded_intervals=degraded_intervals,
        blocked_intervals=blocked_intervals,
        recovery_incidents=recovery_incidents,
        ei_degraded=ei_degraded,
        blocked_cycle_ratio=blocked_cycle_ratio,
        failed_cycle_ratio=failed_cycle_ratio,
        markout_sufficiency=markout_sufficiency,
        tca_sufficiency=tca_sufficiency,
        campaign_breadth_sufficiency=campaign_breadth_sufficiency,
        symbol_participation_sufficiency=symbol_participation_sufficiency,
    )


# ---------------------------------------------------------------------------
# Multi-campaign aggregation
# ---------------------------------------------------------------------------


class AggregateConsistency(str, Enum):
    """Cross-campaign evidence consistency.

    STABLE:        campaigns agree on execution quality.
    MIXED:         campaigns disagree (some pass, some fail/warn).
    INSUFFICIENT:  not enough campaigns to judge consistency.
    """

    STABLE = "stable"
    MIXED = "mixed"
    INSUFFICIENT = "insufficient"


@dataclass(frozen=True)
class CampaignAggregation:
    """Multi-campaign aggregate summary.

    Built from a sequence of CampaignReports.
    Captures verdict distribution, execution coverage, and consistency.
    """

    total_campaigns: int
    passed_count: int
    warned_count: int
    failed_count: int
    inconclusive_count: int

    # Aggregate execution metrics (sums across campaigns)
    total_cycles: int
    total_fills: int
    total_events: int
    total_elapsed_seconds: float

    # Symbol participation breadth
    unique_symbols: tuple[str, ...]
    unique_exchanges: tuple[str, ...]
    symbols_with_events_count: int  # max across campaigns

    # Aggregate stability
    total_recovery_incidents: int
    total_degraded_intervals: int
    any_ei_degraded: bool

    # Aggregate routing
    total_route_blocks: int
    total_route_abstains: int

    # Consistency assessment
    verdict_consistency: AggregateConsistency

    # Per-campaign calibration summaries
    calibrations: tuple[ExecutionCalibrationSummary, ...]

    # Phase 11B: aggregate external regime evidence
    campaigns_with_ext_regime: int = 0
    campaigns_ext_regime_fresh: int = 0
    campaigns_ext_regime_high_risk: int = 0
    ext_regime_coverage_ratio: float = 0.0
    campaigns_with_ext_regime_scenario: int = 0
    campaigns_with_meaningful_ext_regime_scenario: int = 0
    campaigns_ext_regime_stale_dominated: int = 0
    campaigns_ext_regime_unavailable_dominated: int = 0
    campaigns_ext_regime_high_risk_dominated: int = 0
    campaigns_ext_regime_gating_impacted: int = 0
    campaigns_ext_regime_supportive: int = 0
    ext_regime_meaningful_coverage_ratio: float = 0.0
    ext_regime_stale_dominated_ratio: float = 0.0
    ext_regime_unavailable_dominated_ratio: float = 0.0
    ext_regime_high_risk_dominated_ratio: float = 0.0
    ext_regime_gating_impacted_ratio: float = 0.0
    ext_regime_supportive_ratio: float = 0.0

    # Phase 16J: paper run evidence aggregation
    total_paper_runs: int = 0
    passed_runs: int = 0
    warned_runs: int = 0
    blocked_runs: int = 0
    inconclusive_runs: int = 0
    complete_runs: int = 0
    paper_run_pass_ratio: float = 0.0
    paper_run_complete_ratio: float = 0.0
    paper_run_evidence_supportive: bool = False


def _is_scenario_dominated(step_count: int, dominated_steps: int) -> bool:
    """True when a scenario condition dominates at least half of all steps."""
    return step_count > 0 and dominated_steps > 0 and dominated_steps * 2 >= step_count


def build_campaign_aggregation(reports: tuple[CampaignReport, ...]) -> CampaignAggregation:
    """Aggregate multiple campaign reports into a summary.

    Pure function. No I/O. Deterministic.

    Args:
        reports: completed campaign reports (order preserved).

    Returns:
        CampaignAggregation with cross-campaign evidence.
    """
    if not reports:
        return CampaignAggregation(
            total_campaigns=0,
            passed_count=0,
            warned_count=0,
            failed_count=0,
            inconclusive_count=0,
            total_cycles=0,
            total_fills=0,
            total_events=0,
            total_elapsed_seconds=0.0,
            unique_symbols=(),
            unique_exchanges=(),
            symbols_with_events_count=0,
            total_recovery_incidents=0,
            total_degraded_intervals=0,
            any_ei_degraded=False,
            total_route_blocks=0,
            total_route_abstains=0,
            verdict_consistency=AggregateConsistency.INSUFFICIENT,
            calibrations=(),
            # ext regime fields
            campaigns_with_ext_regime=0,
            campaigns_ext_regime_fresh=0,
            campaigns_ext_regime_high_risk=0,
            ext_regime_coverage_ratio=0.0,
            campaigns_with_ext_regime_scenario=0,
            campaigns_with_meaningful_ext_regime_scenario=0,
            campaigns_ext_regime_stale_dominated=0,
            campaigns_ext_regime_unavailable_dominated=0,
            campaigns_ext_regime_high_risk_dominated=0,
            campaigns_ext_regime_gating_impacted=0,
            campaigns_ext_regime_supportive=0,
            ext_regime_meaningful_coverage_ratio=0.0,
            ext_regime_stale_dominated_ratio=0.0,
            ext_regime_unavailable_dominated_ratio=0.0,
            ext_regime_high_risk_dominated_ratio=0.0,
            ext_regime_gating_impacted_ratio=0.0,
            ext_regime_supportive_ratio=0.0,
            # paper run fields
            total_paper_runs=0,
            passed_runs=0,
            warned_runs=0,
            blocked_runs=0,
            inconclusive_runs=0,
            complete_runs=0,
            paper_run_pass_ratio=0.0,
            paper_run_complete_ratio=0.0,
            paper_run_evidence_supportive=False,
        )
    # Phase 16J: paper run evidence aggregation
    total_paper_runs = 0
    passed_runs = 0
    warned_runs = 0
    blocked_runs = 0
    inconclusive_runs = 0
    complete_runs = 0
    # Paper run evidence aggregation (Phase 16J)
    # A paper run is a campaign with a verdict (any status)
    for r in reports:
        total_paper_runs += 1
        v = AcceptanceVerdict(r.verdict)
        if v == AcceptanceVerdict.PASS:
            passed_runs += 1
            complete_runs += 1
        elif v == AcceptanceVerdict.PASS_WITH_WARNINGS:
            warned_runs += 1
            complete_runs += 1
        elif v == AcceptanceVerdict.FAIL:
            blocked_runs += 1
        elif v == AcceptanceVerdict.INCONCLUSIVE:
            inconclusive_runs += 1

    passed = 0
    warned = 0
    failed = 0
    inconclusive = 0
    total_cycles = 0
    total_fills = 0
    total_events = 0
    total_elapsed = 0.0
    all_symbols: set[str] = set()
    all_exchanges: set[str] = set()
    max_symbols_with_events = 0
    total_recovery = 0
    total_degraded = 0
    any_degraded = False
    total_blocks = 0
    total_abstains = 0
    calibrations: list[ExecutionCalibrationSummary] = []
    # Phase 11B: external regime evidence aggregation
    ext_regime_count = 0
    ext_regime_fresh_count = 0
    ext_regime_high_risk_count = 0
    ext_regime_scenario_count = 0
    ext_regime_meaningful_count = 0
    ext_regime_stale_dominated_count = 0
    ext_regime_unavailable_dominated_count = 0
    ext_regime_high_risk_dominated_count = 0
    ext_regime_gating_impacted_count = 0
    ext_regime_supportive_count = 0

    for r in reports:
        verdict = AcceptanceVerdict(r.verdict)
        if verdict == AcceptanceVerdict.PASS:
            passed += 1
        elif verdict == AcceptanceVerdict.PASS_WITH_WARNINGS:
            warned += 1
        elif verdict == AcceptanceVerdict.FAIL:
            failed += 1
        else:
            inconclusive += 1

        snap = r.snapshot
        total_cycles += snap.total_cycles
        total_fills += snap.total_fills
        total_events += snap.total_events_enqueued
        total_elapsed += snap.elapsed_seconds
        max_symbols_with_events = max(max_symbols_with_events, snap.symbols_with_events)
        total_blocks += snap.ei_route_blocks
        total_abstains += snap.ei_route_abstains

        # Phase 11B: external regime evidence tracking
        if getattr(r, "ext_regime_available", False):
            ext_regime_count += 1
        if getattr(r, "ext_regime_fresh", False):
            ext_regime_fresh_count += 1
        if getattr(r, "ext_regime_high_risk", False):
            ext_regime_high_risk_count += 1

        scenario_available = bool(getattr(r, "ext_regime_scenario_available", False))
        scenario_step_count = int(getattr(r, "ext_regime_scenario_step_count", 0) or 0)
        scenario_stale_steps = int(getattr(r, "ext_regime_stale_steps", 0) or 0)
        scenario_unavailable_steps = int(getattr(r, "ext_regime_unavailable_steps", 0) or 0)
        scenario_high_risk_steps = int(getattr(r, "ext_regime_high_risk_steps", 0) or 0)
        scenario_safe_steps = int(getattr(r, "ext_regime_safe_steps", 0) or 0)
        scenario_gating_steps = (
            int(getattr(r, "ext_regime_activation_blocked_steps", 0) or 0)
            + int(getattr(r, "ext_regime_execution_blocked_steps", 0) or 0)
            + int(getattr(r, "ext_regime_activation_reduced_steps", 0) or 0)
        )
        scenario_meaningful = scenario_available and scenario_step_count > 0
        scenario_stale_dominated = _is_scenario_dominated(scenario_step_count, scenario_stale_steps)
        scenario_unavailable_dominated = _is_scenario_dominated(scenario_step_count, scenario_unavailable_steps)
        scenario_high_risk_dominated = _is_scenario_dominated(scenario_step_count, scenario_high_risk_steps)
        scenario_supportive = (
            scenario_meaningful
            and scenario_safe_steps > 0
            and not scenario_stale_dominated
            and not scenario_unavailable_dominated
            and not scenario_high_risk_dominated
        )

        if scenario_available:
            ext_regime_scenario_count += 1
        if scenario_meaningful:
            ext_regime_meaningful_count += 1
        if scenario_stale_dominated:
            ext_regime_stale_dominated_count += 1
        if scenario_unavailable_dominated:
            ext_regime_unavailable_dominated_count += 1
        if scenario_high_risk_dominated:
            ext_regime_high_risk_dominated_count += 1
        if scenario_meaningful and scenario_gating_steps > 0:
            ext_regime_gating_impacted_count += 1
        if scenario_supportive:
            ext_regime_supportive_count += 1

        total_recovery += snap.recovery_incidents
        if snap.stability:
            total_degraded += snap.stability.degraded_intervals
            if snap.stability.ei_degraded:
                any_degraded = True
        elif snap.ei_degraded:
            any_degraded = True

        for sp in r.symbol_participation:
            all_symbols.add(sp.symbol)
            all_exchanges.add(sp.exchange)

        calibrations.append(build_execution_calibration(r))

    # Consistency: if all verdicts agree → STABLE, mixed → MIXED
    n = len(reports)
    if n < 2:
        consistency = AggregateConsistency.INSUFFICIENT
    elif failed == 0 and inconclusive == 0:
        consistency = AggregateConsistency.STABLE
    elif passed + warned == 0:
        consistency = AggregateConsistency.STABLE  # consistently bad is still consistent
    else:
        consistency = AggregateConsistency.MIXED

    paper_run_pass_ratio = (passed_runs + warned_runs) / total_paper_runs if total_paper_runs > 0 else 0.0
    paper_run_complete_ratio = complete_runs / total_paper_runs if total_paper_runs > 0 else 0.0
    # Phase 16K: use PromotionThresholds for sufficiency
    default_thresholds = PromotionThresholds()
    paper_run_evidence_supportive = (
        total_paper_runs >= default_thresholds.min_paper_runs
        and paper_run_pass_ratio >= default_thresholds.min_paper_pass_ratio
        and paper_run_complete_ratio >= default_thresholds.min_paper_complete_ratio
        and (blocked_runs / total_paper_runs if total_paper_runs > 0 else 0.0)
        <= default_thresholds.max_paper_blocked_ratio
    )
    return CampaignAggregation(
        total_campaigns=n,
        passed_count=passed,
        warned_count=warned,
        failed_count=failed,
        inconclusive_count=inconclusive,
        total_cycles=total_cycles,
        total_fills=total_fills,
        total_events=total_events,
        total_elapsed_seconds=total_elapsed,
        unique_symbols=tuple(sorted(all_symbols)),
        unique_exchanges=tuple(sorted(all_exchanges)),
        symbols_with_events_count=max_symbols_with_events,
        total_recovery_incidents=total_recovery,
        total_degraded_intervals=total_degraded,
        any_ei_degraded=any_degraded,
        total_route_blocks=total_blocks,
        total_route_abstains=total_abstains,
        verdict_consistency=consistency,
        calibrations=tuple(calibrations),
        # Phase 11B: external regime evidence aggregation
        campaigns_with_ext_regime=ext_regime_count,
        campaigns_ext_regime_fresh=ext_regime_fresh_count,
        campaigns_ext_regime_high_risk=ext_regime_high_risk_count,
        ext_regime_coverage_ratio=(ext_regime_count / n if n > 0 else 0.0),
        campaigns_with_ext_regime_scenario=ext_regime_scenario_count,
        campaigns_with_meaningful_ext_regime_scenario=ext_regime_meaningful_count,
        campaigns_ext_regime_stale_dominated=ext_regime_stale_dominated_count,
        campaigns_ext_regime_unavailable_dominated=ext_regime_unavailable_dominated_count,
        campaigns_ext_regime_high_risk_dominated=ext_regime_high_risk_dominated_count,
        campaigns_ext_regime_gating_impacted=ext_regime_gating_impacted_count,
        campaigns_ext_regime_supportive=ext_regime_supportive_count,
        ext_regime_meaningful_coverage_ratio=(ext_regime_meaningful_count / n if n > 0 else 0.0),
        ext_regime_stale_dominated_ratio=(ext_regime_stale_dominated_count / n if n > 0 else 0.0),
        ext_regime_unavailable_dominated_ratio=(ext_regime_unavailable_dominated_count / n if n > 0 else 0.0),
        ext_regime_high_risk_dominated_ratio=(ext_regime_high_risk_dominated_count / n if n > 0 else 0.0),
        ext_regime_gating_impacted_ratio=(ext_regime_gating_impacted_count / n if n > 0 else 0.0),
        ext_regime_supportive_ratio=(ext_regime_supportive_count / n if n > 0 else 0.0),
        # Phase 16J: paper run evidence aggregation
        total_paper_runs=total_paper_runs,
        passed_runs=passed_runs,
        warned_runs=warned_runs,
        blocked_runs=blocked_runs,
        inconclusive_runs=inconclusive_runs,
        complete_runs=complete_runs,
        paper_run_pass_ratio=paper_run_pass_ratio,
        paper_run_complete_ratio=paper_run_complete_ratio,
        paper_run_evidence_supportive=paper_run_evidence_supportive,
    )


# ---------------------------------------------------------------------------
# Promotion verdict
# ---------------------------------------------------------------------------


class PromotionVerdict(str, Enum):
    """Deterministic promotion outcome.

    PROMOTE:      evidence supports advancement to next review level.
    HOLD:         evidence is trending positively but not yet sufficient.
    REJECT:       evidence shows hard failures; promotion denied.
    INCONCLUSIVE: not enough evidence to determine promotion readiness.
    """

    PROMOTE = "promote"
    HOLD = "hold"
    REJECT = "reject"
    INCONCLUSIVE = "inconclusive"


# ---------------------------------------------------------------------------
# Promotion criterion
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionCriterion:
    """Result of evaluating one promotion criterion.

    name:       criterion identifier (machine-readable).
    passed:     True if criterion is satisfied.
    severity:   'hard' (breach → REJECT), 'soft' (breach → warning),
                'coverage' (breach → INCONCLUSIVE).
    actual:     observed value.
    threshold:  configured threshold.
    message:    human-readable explanation.
    """

    name: str
    passed: bool
    severity: str  # "hard", "soft", "coverage"
    actual: float
    threshold: float
    message: str


# ---------------------------------------------------------------------------
# Promotion result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionResult:
    """Full promotion evaluation result with reason codes.

    verdict:              final PromotionVerdict.
    criteria:             all evaluated PromotionCriterion.
    pass_reasons:         criteria that support promotion.
    warning_reasons:      criteria that are marginal.
    fail_reasons:         criteria that block promotion.
    insufficient_reasons: criteria with not enough evidence.
    summary:              human-readable summary.
    """

    verdict: PromotionVerdict
    criteria: tuple[PromotionCriterion, ...]
    pass_reasons: tuple[PromotionCriterion, ...]
    warning_reasons: tuple[PromotionCriterion, ...]
    fail_reasons: tuple[PromotionCriterion, ...]
    insufficient_reasons: tuple[PromotionCriterion, ...]
    summary: str


# ---------------------------------------------------------------------------
# Promotion thresholds
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionThresholds:
    # --- Paper run evidence sufficiency thresholds (Phase 16K) ---
    min_paper_runs: int = 5
    min_paper_pass_ratio: float = 0.8
    min_paper_complete_ratio: float = 0.8
    max_paper_blocked_ratio: float = 0.2
    """Configurable thresholds for the promotion policy.

    Coverage → insufficient evidence if not met.
    Hard → REJECT if breached.
    Soft → warning if breached but not blocking.
    """

    # --- Coverage minimums (insufficient → INCONCLUSIVE) ---
    min_completed_campaigns: int = 3
    min_total_cycles: int = 200
    min_total_events: int = 500
    min_total_fills: int = 10
    min_unique_symbols: int = 2
    min_total_elapsed_seconds: float = 300.0

    # --- Hard failure thresholds (breach → REJECT) ---
    max_failed_campaigns: int = 1
    max_inconclusive_campaigns: int = 2
    max_route_block_ratio: float = 0.05
    max_route_abstain_ratio: float = 0.10
    max_degraded_interval_ratio: float = 0.15
    max_recovery_incidents: int = 10
    max_failed_cycle_ratio: float = 0.10
    require_stable_consistency: bool = False

    # --- Soft warning thresholds ---
    warn_route_block_ratio: float = 0.02
    warn_route_abstain_ratio: float = 0.05
    warn_degraded_interval_ratio: float = 0.05
    warn_recovery_incidents: int = 3
    warn_failed_campaigns: int = 0

    # --- Execution evidence quality ---
    min_markout_completion_ratio: float = 0.5  # coverage
    min_persisted_tca_ratio: float = -1.0  # -1 = not enforced (unavailable)

    # --- Phase 11B: external regime evidence coverage ---
    min_ext_regime_coverage_ratio: float = -1.0  # -1 = not enforced (unavailable)t enforced (unavailable)
    min_ext_regime_meaningful_campaigns: int = 1
    min_ext_regime_meaningful_coverage_ratio: float = 1.0 / 3.0
    max_ext_regime_high_risk_dominated_ratio: float = 0.5
    warn_ext_regime_stale_dominated_ratio: float = 0.25
    warn_ext_regime_unavailable_dominated_ratio: float = 0.25
    warn_ext_regime_gating_impacted_ratio: float = 0.5


# ---------------------------------------------------------------------------
# Promotion review (full report)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PromotionReview:
    """Full promotion review report.

    Combines calibration evidence, aggregation, and verdict into a single
    auditable artifact.
    """

    review_id: str
    reviewed_at_ns: int
    aggregation: CampaignAggregation
    result: PromotionResult
    readiness_level: str  # current ReadinessLevel.value
    readiness_is_supportive: bool  # readiness meets minimum for this promotion
    campaign_ids: tuple[str, ...]


# ---------------------------------------------------------------------------
# Promotion policy — deterministic evaluator
# ---------------------------------------------------------------------------


class PromotionPolicy:
    """Deterministic promotion evaluator.

    Evaluates a CampaignAggregation against PromotionThresholds.
    Pure logic — no side effects, no I/O.

    Usage::

        policy = PromotionPolicy(thresholds)
        result = policy.evaluate(aggregation, readiness_level="paper_live")
    """

    def __init__(self, thresholds: PromotionThresholds | None = None) -> None:
        self._t = thresholds or PromotionThresholds()

    @property
    def thresholds(self) -> PromotionThresholds:
        return self._t

    def evaluate(
        self,
        aggregation: CampaignAggregation,
        *,
        readiness_level: str = "not_assessed",
    ) -> PromotionResult:
        """Evaluate promotion readiness from campaign aggregation.

        Returns:
            PromotionResult with deterministic verdict and reason codes.
        """
        criteria: list[PromotionCriterion] = []
        t = self._t
        agg = aggregation

        # --- Coverage checks ---
        criteria.append(
            self._check_coverage(
                "min_completed_campaigns",
                agg.total_campaigns,
                t.min_completed_campaigns,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_total_cycles",
                agg.total_cycles,
                t.min_total_cycles,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_total_events",
                agg.total_events,
                t.min_total_events,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_total_fills",
                agg.total_fills,
                t.min_total_fills,
            )
        )
        criteria.append(
            self._check_coverage(
                "min_unique_symbols",
                len(agg.unique_symbols),
                t.min_unique_symbols,
            )
        )
        if t.min_total_elapsed_seconds > 0:
            criteria.append(
                self._check_coverage(
                    "min_total_elapsed_seconds",
                    agg.total_elapsed_seconds,
                    t.min_total_elapsed_seconds,
                )
            )

        # --- Hard failure checks ---
        criteria.append(
            self._check_hard(
                "max_failed_campaigns",
                agg.failed_count,
                t.max_failed_campaigns,
            )
        )
        criteria.append(
            self._check_hard(
                "max_inconclusive_campaigns",
                agg.inconclusive_count,
                t.max_inconclusive_campaigns,
            )
        )

        # Route ratios (aggregate)
        agg_route_block_ratio = agg.total_route_blocks / agg.total_cycles if agg.total_cycles > 0 else 0.0
        agg_route_abstain_ratio = agg.total_route_abstains / agg.total_cycles if agg.total_cycles > 0 else 0.0

        criteria.append(
            self._check_hard(
                "max_route_block_ratio",
                agg_route_block_ratio,
                t.max_route_block_ratio,
            )
        )
        criteria.append(
            self._check_hard(
                "max_route_abstain_ratio",
                agg_route_abstain_ratio,
                t.max_route_abstain_ratio,
            )
        )

        # Degradation ratio
        total_updates = agg.total_cycles  # proxy for update count
        agg_degraded_ratio = agg.total_degraded_intervals / total_updates if total_updates > 0 else 0.0
        criteria.append(
            self._check_hard(
                "max_degraded_interval_ratio",
                agg_degraded_ratio,
                t.max_degraded_interval_ratio,
            )
        )

        criteria.append(
            self._check_hard(
                "max_recovery_incidents",
                agg.total_recovery_incidents,
                t.max_recovery_incidents,
            )
        )

        # Failed cycle ratio (aggregate)
        total_failed_cycles = sum(
            c.failed_cycle_ratio * c.total_cycles
            for c in agg.calibrations
            if c.failed_cycle_ratio >= 0 and c.total_cycles > 0
        )
        agg_failed_cycle_ratio = total_failed_cycles / agg.total_cycles if agg.total_cycles > 0 else 0.0
        criteria.append(
            self._check_hard(
                "max_failed_cycle_ratio",
                agg_failed_cycle_ratio,
                t.max_failed_cycle_ratio,
            )
        )

        # Consistency
        if t.require_stable_consistency:
            criteria.append(
                PromotionCriterion(
                    name="require_stable_consistency",
                    passed=agg.verdict_consistency == AggregateConsistency.STABLE,
                    severity="hard",
                    actual=0.0 if agg.verdict_consistency == AggregateConsistency.STABLE else 1.0,
                    threshold=0.0,
                    message=f"verdict_consistency: {agg.verdict_consistency.value}",
                )
            )

        # --- Soft warning checks ---
        criteria.append(
            self._check_soft(
                "warn_route_block_ratio",
                agg_route_block_ratio,
                t.warn_route_block_ratio,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_route_abstain_ratio",
                agg_route_abstain_ratio,
                t.warn_route_abstain_ratio,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_degraded_interval_ratio",
                agg_degraded_ratio,
                t.warn_degraded_interval_ratio,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_recovery_incidents",
                agg.total_recovery_incidents,
                t.warn_recovery_incidents,
            )
        )
        criteria.append(
            self._check_soft(
                "warn_failed_campaigns",
                agg.failed_count,
                t.warn_failed_campaigns,
            )
        )

        # --- Execution evidence quality ---
        # Markout coverage: average markout_completion_ratio across calibrations
        markout_ratios = [c.markout_completion_ratio for c in agg.calibrations if c.markout_completion_ratio >= 0]
        avg_markout_ratio = sum(markout_ratios) / len(markout_ratios) if markout_ratios else -1.0
        if t.min_markout_completion_ratio >= 0 and avg_markout_ratio >= 0:
            criteria.append(
                self._check_coverage(
                    "min_markout_completion_ratio",
                    avg_markout_ratio,
                    t.min_markout_completion_ratio,
                )
            )

        # TCA persistence ratio
        tca_ratios = [c.persisted_tca_ratio for c in agg.calibrations if c.persisted_tca_ratio >= 0]
        avg_tca_ratio = sum(tca_ratios) / len(tca_ratios) if tca_ratios else -1.0
        if t.min_persisted_tca_ratio >= 0 and avg_tca_ratio >= 0:
            criteria.append(
                self._check_coverage(
                    "min_persisted_tca_ratio",
                    avg_tca_ratio,
                    t.min_persisted_tca_ratio,
                )
            )

        # Phase 11B: external regime evidence coverage
        if t.min_ext_regime_coverage_ratio >= 0:
            criteria.append(
                self._check_coverage(
                    "min_ext_regime_coverage_ratio",
                    agg.ext_regime_coverage_ratio,
                    t.min_ext_regime_coverage_ratio,
                )
            )
        if t.min_ext_regime_meaningful_campaigns >= 0:
            criteria.append(
                self._check_coverage(
                    "min_ext_regime_meaningful_campaigns",
                    agg.campaigns_with_meaningful_ext_regime_scenario,
                    t.min_ext_regime_meaningful_campaigns,
                )
            )
        if t.min_ext_regime_meaningful_coverage_ratio >= 0:
            criteria.append(
                self._check_coverage(
                    "min_ext_regime_meaningful_coverage_ratio",
                    agg.ext_regime_meaningful_coverage_ratio,
                    t.min_ext_regime_meaningful_coverage_ratio,
                )
            )
        if t.max_ext_regime_high_risk_dominated_ratio >= 0:
            criteria.append(
                self._check_hard(
                    "max_ext_regime_high_risk_dominated_ratio",
                    agg.ext_regime_high_risk_dominated_ratio,
                    t.max_ext_regime_high_risk_dominated_ratio,
                )
            )
        if t.warn_ext_regime_stale_dominated_ratio >= 0:
            criteria.append(
                self._check_soft(
                    "warn_ext_regime_stale_dominated_ratio",
                    agg.ext_regime_stale_dominated_ratio,
                    t.warn_ext_regime_stale_dominated_ratio,
                )
            )
        if t.warn_ext_regime_unavailable_dominated_ratio >= 0:
            criteria.append(
                self._check_soft(
                    "warn_ext_regime_unavailable_dominated_ratio",
                    agg.ext_regime_unavailable_dominated_ratio,
                    t.warn_ext_regime_unavailable_dominated_ratio,
                )
            )
        if t.warn_ext_regime_gating_impacted_ratio >= 0:
            criteria.append(
                self._check_soft(
                    "warn_ext_regime_gating_impacted_ratio",
                    agg.ext_regime_gating_impacted_ratio,
                    t.warn_ext_regime_gating_impacted_ratio,
                )
            )

        # --- Classify ---
        failed = tuple(c for c in criteria if not c.passed and c.severity == "hard")
        warnings = tuple(c for c in criteria if not c.passed and c.severity == "soft")
        insufficient = tuple(c for c in criteria if not c.passed and c.severity == "coverage")
        passed = tuple(c for c in criteria if c.passed)

        if insufficient:
            verdict = PromotionVerdict.INCONCLUSIVE
            summary = f"Insufficient evidence: {len(insufficient)} coverage criteria below minimum. " + "; ".join(
                c.message for c in insufficient
            )
        elif failed:
            verdict = PromotionVerdict.REJECT
            summary = f"REJECT: {len(failed)} hard criteria breached. " + "; ".join(c.message for c in failed)
        elif warnings:
            verdict = PromotionVerdict.HOLD
            summary = f"HOLD: {len(warnings)} warnings. Evidence trending but not clean. " + "; ".join(
                c.message for c in warnings
            )
        else:
            verdict = PromotionVerdict.PROMOTE
            summary = "All promotion criteria met. Evidence supports advancement."

        return PromotionResult(
            verdict=verdict,
            criteria=tuple(criteria),
            pass_reasons=passed,
            warning_reasons=warnings,
            fail_reasons=failed,
            insufficient_reasons=insufficient,
            summary=summary,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_coverage(name: str, actual: float, minimum: float) -> PromotionCriterion:
        passed = actual >= minimum
        return PromotionCriterion(
            name=name,
            passed=passed,
            severity="coverage",
            actual=actual,
            threshold=minimum,
            message=f"{name}: {actual} {'≥' if passed else '<'} {minimum}",
        )

    @staticmethod
    def _check_hard(name: str, actual: float, maximum: float) -> PromotionCriterion:
        passed = actual <= maximum
        return PromotionCriterion(
            name=name,
            passed=passed,
            severity="hard",
            actual=actual,
            threshold=maximum,
            message=f"{name}: {actual} {'≤' if passed else '>'} {maximum}",
        )

    @staticmethod
    def _check_soft(name: str, actual: float, maximum: float) -> PromotionCriterion:
        passed = actual <= maximum
        return PromotionCriterion(
            name=name,
            passed=passed,
            severity="soft",
            actual=actual,
            threshold=maximum,
            message=f"{name}: {actual} {'≤' if passed else '>'} {maximum}",
        )


# ---------------------------------------------------------------------------
# Build promotion review
# ---------------------------------------------------------------------------


def build_promotion_review(
    reports: tuple[CampaignReport, ...],
    *,
    review_id: str,
    readiness_level: str = "not_assessed",
    thresholds: PromotionThresholds | None = None,
    reviewed_at_ns: int | None = None,
) -> PromotionReview:
    """Build a full promotion review from campaign history.

    Pure function. No I/O. Deterministic.

    Args:
        reports: completed campaign reports.
        review_id: unique review identifier.
        readiness_level: current ReadinessLevel.value string.
        thresholds: promotion policy thresholds.
        reviewed_at_ns: review timestamp; defaults to time.time_ns().
    """
    ts = reviewed_at_ns if reviewed_at_ns is not None else time.time_ns()
    aggregation = build_campaign_aggregation(reports)
    policy = PromotionPolicy(thresholds)
    result = policy.evaluate(aggregation, readiness_level=readiness_level)

    # Readiness supportive: at least paper_live level
    _SUPPORTIVE_LEVELS = {"paper_live", "calibrated_paper", "shadow_live", "tiny_cap_live"}
    readiness_supportive = readiness_level in _SUPPORTIVE_LEVELS

    campaign_ids = tuple(r.campaign_id for r in reports)

    return PromotionReview(
        review_id=review_id,
        reviewed_at_ns=ts,
        aggregation=aggregation,
        result=result,
        readiness_level=readiness_level,
        readiness_is_supportive=readiness_supportive,
        campaign_ids=campaign_ids,
    )


# ---------------------------------------------------------------------------
# Promotion review store (persistence)
# ---------------------------------------------------------------------------

_REVIEW_SNAPSHOT_NAME = "promotion_review"
_REVIEW_REQUIRED_FIELDS = frozenset({"review_id", "reviewed_at_ns", "verdict"})


class PromotionReviewCorruptError(RuntimeError):
    """Raised when persisted promotion review data is malformed."""


class PromotionReviewStore:
    """Persistent store for promotion review artifacts.

    Uses EvidenceStore for JSONL evidence log and atomic JSON snapshots.
    Fail-closed: malformed data → raise, never skip.
    """

    def __init__(self, evidence_store: EvidenceStore) -> None:
        self._store = evidence_store

    def save_review(self, review: PromotionReview) -> WriteResult:
        """Persist a promotion review as an atomic snapshot + evidence log entry."""
        d = promotion_review_to_dict(review)
        # Atomic snapshot for latest review.
        result = self._store.save_snapshot(_REVIEW_SNAPSHOT_NAME, d)
        if not result.success:
            return result
        # Also append to evidence log.
        self._store.append_evidence("promotion_review", d)
        return result

    def load_review(self) -> dict:
        """Load the latest promotion review from disk.

        Returns:
            Raw dict envelope from the snapshot.

        Raises:
            EvidenceStoreCorruptError: if snapshot missing or malformed.
            PromotionReviewCorruptError: if review data is invalid.
        """
        envelope = self._store.load_snapshot(_REVIEW_SNAPSHOT_NAME)
        data = envelope.get("data")
        if not isinstance(data, dict):
            raise PromotionReviewCorruptError(f"Promotion review 'data' must be a dict, got {type(data).__name__!r}")
        missing = _REVIEW_REQUIRED_FIELDS - set(data)
        if missing:
            raise PromotionReviewCorruptError(f"Promotion review missing required fields: {sorted(missing)!r}")
        return data


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _calibration_to_dict(cal: ExecutionCalibrationSummary) -> dict:
    """Serialize ExecutionCalibrationSummary to a plain dict."""
    return {
        "campaign_id": cal.campaign_id,
        "total_cycles": cal.total_cycles,
        "total_fills": cal.total_fills,
        "total_events": cal.total_events,
        "symbol_count": cal.symbol_count,
        "symbols_with_events": cal.symbols_with_events,
        "symbols_with_cycles": cal.symbols_with_cycles,
        "elapsed_seconds": cal.elapsed_seconds,
        "route_block_count": cal.route_block_count,
        "route_abstain_count": cal.route_abstain_count,
        "route_block_ratio": cal.route_block_ratio,
        "route_abstain_ratio": cal.route_abstain_ratio,
        "pending_markout_count": cal.pending_markout_count,
        "completed_markout_count": cal.completed_markout_count,
        "markout_completion_ratio": cal.markout_completion_ratio,
        "persisted_tca_count": cal.persisted_tca_count,
        "persisted_tca_ratio": cal.persisted_tca_ratio,
        "persisted_attribution_count": cal.persisted_attribution_count,
        "degraded_intervals": cal.degraded_intervals,
        "blocked_intervals": cal.blocked_intervals,
        "recovery_incidents": cal.recovery_incidents,
        "ei_degraded": cal.ei_degraded,
        "blocked_cycle_ratio": cal.blocked_cycle_ratio,
        "failed_cycle_ratio": cal.failed_cycle_ratio,
        "markout_sufficiency": cal.markout_sufficiency.value,
        "tca_sufficiency": cal.tca_sufficiency.value,
        "campaign_breadth_sufficiency": cal.campaign_breadth_sufficiency.value,
        "symbol_participation_sufficiency": cal.symbol_participation_sufficiency.value,
    }


def _aggregation_to_dict(agg: CampaignAggregation) -> dict:
    """Serialize CampaignAggregation to a plain dict."""
    return {
        "total_campaigns": agg.total_campaigns,
        "passed_count": agg.passed_count,
        "warned_count": agg.warned_count,
        "failed_count": agg.failed_count,
        "inconclusive_count": agg.inconclusive_count,
        "total_cycles": agg.total_cycles,
        "total_fills": agg.total_fills,
        "total_events": agg.total_events,
        "total_elapsed_seconds": agg.total_elapsed_seconds,
        "unique_symbols": list(agg.unique_symbols),
        "unique_exchanges": list(agg.unique_exchanges),
        "symbols_with_events_count": agg.symbols_with_events_count,
        "total_recovery_incidents": agg.total_recovery_incidents,
        "total_degraded_intervals": agg.total_degraded_intervals,
        "any_ei_degraded": agg.any_ei_degraded,
        "total_route_blocks": agg.total_route_blocks,
        "total_route_abstains": agg.total_route_abstains,
        "verdict_consistency": agg.verdict_consistency.value,
        "campaigns_with_ext_regime": agg.campaigns_with_ext_regime,
        "campaigns_ext_regime_fresh": agg.campaigns_ext_regime_fresh,
        "campaigns_ext_regime_high_risk": agg.campaigns_ext_regime_high_risk,
        "ext_regime_coverage_ratio": agg.ext_regime_coverage_ratio,
        "campaigns_with_ext_regime_scenario": agg.campaigns_with_ext_regime_scenario,
        "campaigns_with_meaningful_ext_regime_scenario": agg.campaigns_with_meaningful_ext_regime_scenario,
        "campaigns_ext_regime_stale_dominated": agg.campaigns_ext_regime_stale_dominated,
        "campaigns_ext_regime_unavailable_dominated": agg.campaigns_ext_regime_unavailable_dominated,
        "campaigns_ext_regime_high_risk_dominated": agg.campaigns_ext_regime_high_risk_dominated,
        "campaigns_ext_regime_gating_impacted": agg.campaigns_ext_regime_gating_impacted,
        "campaigns_ext_regime_supportive": agg.campaigns_ext_regime_supportive,
        "ext_regime_meaningful_coverage_ratio": agg.ext_regime_meaningful_coverage_ratio,
        "ext_regime_stale_dominated_ratio": agg.ext_regime_stale_dominated_ratio,
        "ext_regime_unavailable_dominated_ratio": agg.ext_regime_unavailable_dominated_ratio,
        "ext_regime_high_risk_dominated_ratio": agg.ext_regime_high_risk_dominated_ratio,
        "ext_regime_gating_impacted_ratio": agg.ext_regime_gating_impacted_ratio,
        "ext_regime_supportive_ratio": agg.ext_regime_supportive_ratio,
        "calibrations": [_calibration_to_dict(c) for c in agg.calibrations],
        # Phase 16J: paper run evidence aggregation
        "total_paper_runs": agg.total_paper_runs,
        "passed_runs": agg.passed_runs,
        "warned_runs": agg.warned_runs,
        "blocked_runs": agg.blocked_runs,
        "inconclusive_runs": agg.inconclusive_runs,
        "complete_runs": agg.complete_runs,
        "paper_run_pass_ratio": agg.paper_run_pass_ratio,
        "paper_run_complete_ratio": agg.paper_run_complete_ratio,
        "paper_run_evidence_supportive": agg.paper_run_evidence_supportive,
    }


def _promotion_result_to_dict(result: PromotionResult) -> dict:
    """Serialize PromotionResult to a plain dict."""
    return {
        "verdict": result.verdict.value,
        "summary": result.summary,
        "criteria": [
            {
                "name": c.name,
                "passed": c.passed,
                "severity": c.severity,
                "actual": c.actual,
                "threshold": c.threshold,
                "message": c.message,
            }
            for c in result.criteria
        ],
        "pass_reasons": [c.name for c in result.pass_reasons],
        "warning_reasons": [c.name for c in result.warning_reasons],
        "fail_reasons": [c.name for c in result.fail_reasons],
        "insufficient_reasons": [c.name for c in result.insufficient_reasons],
    }


def promotion_review_to_dict(review: PromotionReview) -> dict:
    """Serialize PromotionReview to a plain dict for persistence."""
    return {
        "review_id": review.review_id,
        "reviewed_at_ns": review.reviewed_at_ns,
        "verdict": review.result.verdict.value,
        "readiness_level": review.readiness_level,
        "readiness_is_supportive": review.readiness_is_supportive,
        "campaign_ids": list(review.campaign_ids),
        "aggregation": _aggregation_to_dict(review.aggregation),
        "result": _promotion_result_to_dict(review.result),
    }


# ---------------------------------------------------------------------------
# Reporting API (read-only, deterministic)
# ---------------------------------------------------------------------------


def execution_sufficiency_summary(agg: CampaignAggregation) -> dict:
    """Summarize execution evidence sufficiency across campaigns."""
    sufficiency_counts: dict[str, dict[str, int]] = {
        "markout": {},
        "tca": {},
        "campaign_breadth": {},
        "symbol_participation": {},
    }
    for cal in agg.calibrations:
        for dim, val in [
            ("markout", cal.markout_sufficiency),
            ("tca", cal.tca_sufficiency),
            ("campaign_breadth", cal.campaign_breadth_sufficiency),
            ("symbol_participation", cal.symbol_participation_sufficiency),
        ]:
            sufficiency_counts[dim][val.value] = sufficiency_counts[dim].get(val.value, 0) + 1

    return {
        "total_campaigns": agg.total_campaigns,
        "sufficiency_distribution": sufficiency_counts,
    }


def verdict_distribution(agg: CampaignAggregation) -> dict:
    """Campaign verdict distribution summary, including paper run evidence (Phase 16J)."""
    return {
        "total": agg.total_campaigns,
        "passed": agg.passed_count,
        "warned": agg.warned_count,
        "failed": agg.failed_count,
        "inconclusive": agg.inconclusive_count,
        "consistency": agg.verdict_consistency.value,
        # Phase 16J: paper run evidence
        "total_paper_runs": agg.total_paper_runs,
        "passed_runs": agg.passed_runs,
        "warned_runs": agg.warned_runs,
        "blocked_runs": agg.blocked_runs,
        "inconclusive_runs": agg.inconclusive_runs,
        "complete_runs": agg.complete_runs,
        "paper_run_pass_ratio": agg.paper_run_pass_ratio,
        "paper_run_complete_ratio": agg.paper_run_complete_ratio,
        "paper_run_evidence_supportive": agg.paper_run_evidence_supportive,
    }


def paper_run_summary(agg: CampaignAggregation) -> dict:
    """Deterministic summary of paper run evidence (Phase 16J)."""
    return {
        "total_paper_runs": agg.total_paper_runs,
        "passed_runs": agg.passed_runs,
        "warned_runs": agg.warned_runs,
        "blocked_runs": agg.blocked_runs,
        "inconclusive_runs": agg.inconclusive_runs,
        "complete_runs": agg.complete_runs,
        "paper_run_pass_ratio": agg.paper_run_pass_ratio,
        "paper_run_complete_ratio": agg.paper_run_complete_ratio,
        "paper_run_evidence_supportive": agg.paper_run_evidence_supportive,
    }


def symbol_participation_summary(agg: CampaignAggregation) -> dict:
    """Symbol participation breadth across campaigns."""
    return {
        "unique_symbols": list(agg.unique_symbols),
        "unique_exchanges": list(agg.unique_exchanges),
        "max_symbols_with_events": agg.symbols_with_events_count,
        "total_campaigns": agg.total_campaigns,
    }


def promotion_reason_summary(result: PromotionResult) -> dict:
    """Recent reason-code summary from a promotion result."""
    return {
        "verdict": result.verdict.value,
        "pass_count": len(result.pass_reasons),
        "warning_count": len(result.warning_reasons),
        "fail_count": len(result.fail_reasons),
        "insufficient_count": len(result.insufficient_reasons),
        "pass_reasons": [c.name for c in result.pass_reasons],
        "warning_reasons": [c.name for c in result.warning_reasons],
        "fail_reasons": [c.name for c in result.fail_reasons],
        "insufficient_reasons": [c.name for c in result.insufficient_reasons],
        "summary": result.summary,
    }


def ext_regime_governance_summary(agg: CampaignAggregation) -> dict:
    """Compact external-regime governance summary for review/reporting surfaces."""
    return {
        "campaigns_with_ext_regime": agg.campaigns_with_ext_regime,
        "campaigns_ext_regime_fresh": agg.campaigns_ext_regime_fresh,
        "campaigns_ext_regime_high_risk": agg.campaigns_ext_regime_high_risk,
        "ext_regime_coverage_ratio": agg.ext_regime_coverage_ratio,
        "campaigns_with_ext_regime_scenario": agg.campaigns_with_ext_regime_scenario,
        "campaigns_with_meaningful_ext_regime_scenario": agg.campaigns_with_meaningful_ext_regime_scenario,
        "campaigns_ext_regime_stale_dominated": agg.campaigns_ext_regime_stale_dominated,
        "campaigns_ext_regime_unavailable_dominated": agg.campaigns_ext_regime_unavailable_dominated,
        "campaigns_ext_regime_high_risk_dominated": agg.campaigns_ext_regime_high_risk_dominated,
        "campaigns_ext_regime_gating_impacted": agg.campaigns_ext_regime_gating_impacted,
        "campaigns_ext_regime_supportive": agg.campaigns_ext_regime_supportive,
        "ext_regime_meaningful_coverage_ratio": agg.ext_regime_meaningful_coverage_ratio,
        "ext_regime_stale_dominated_ratio": agg.ext_regime_stale_dominated_ratio,
        "ext_regime_unavailable_dominated_ratio": agg.ext_regime_unavailable_dominated_ratio,
        "ext_regime_high_risk_dominated_ratio": agg.ext_regime_high_risk_dominated_ratio,
        "ext_regime_gating_impacted_ratio": agg.ext_regime_gating_impacted_ratio,
        "ext_regime_supportive_ratio": agg.ext_regime_supportive_ratio,
    }


def classify_ext_regime_governance(
    agg: CampaignAggregation,
    thresholds: PromotionThresholds | None = None,
) -> str:
    """Classify ext-regime governance support for promotion/readiness surfaces."""
    t = thresholds or PromotionThresholds()

    if agg.total_campaigns == 0 or agg.campaigns_with_ext_regime_scenario == 0:
        return "unavailable"
    if (
        t.min_ext_regime_meaningful_campaigns >= 0
        and agg.campaigns_with_meaningful_ext_regime_scenario < t.min_ext_regime_meaningful_campaigns
    ):
        return "insufficient"
    if (
        t.min_ext_regime_meaningful_coverage_ratio >= 0
        and agg.ext_regime_meaningful_coverage_ratio < t.min_ext_regime_meaningful_coverage_ratio
    ):
        return "insufficient"
    if (
        t.max_ext_regime_high_risk_dominated_ratio >= 0
        and agg.ext_regime_high_risk_dominated_ratio > t.max_ext_regime_high_risk_dominated_ratio
    ):
        return "blocking"
    if (
        (
            t.warn_ext_regime_stale_dominated_ratio >= 0
            and agg.ext_regime_stale_dominated_ratio > t.warn_ext_regime_stale_dominated_ratio
        )
        or (
            t.warn_ext_regime_unavailable_dominated_ratio >= 0
            and agg.ext_regime_unavailable_dominated_ratio > t.warn_ext_regime_unavailable_dominated_ratio
        )
        or (
            t.warn_ext_regime_gating_impacted_ratio >= 0
            and agg.ext_regime_gating_impacted_ratio > t.warn_ext_regime_gating_impacted_ratio
        )
    ):
        return "cautionary"
    return "supportive"
