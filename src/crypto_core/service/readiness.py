"""Live-readiness status surface — Phase 9B.

Machine-readable readiness model that truthfully reports what the system
can and cannot do right now.  Each readiness level has explicit criteria
that must all be satisfied.

Design invariants:
  - Conservative truthfulness: never overstate readiness.
  - Every blocker is named and auditable.
  - Frozen models for immutable snapshots.
  - No silent promotion: if criteria are not provably met, level stays lower.

PRD reference: §2 System Orchestration, §7 Execution Engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

# ---------------------------------------------------------------------------
# Readiness levels
# ---------------------------------------------------------------------------


class ReadinessLevel(str, Enum):
    """System readiness tiers, ordered from least to most capable.

    RESEARCH_ONLY:      backtesting and analysis only; no real-time feeds.
    PAPER_LIVE:         paper execution with live data feeds.
    CALIBRATED_PAPER:   paper fills calibrated against historical live fills.
    SHADOW_LIVE:        real-time shadow tracking against live market (no orders).
    TINY_CAP_LIVE:      canary allocation with real orders (max $500 notional).
    NOT_ASSESSED:       readiness has not been evaluated yet.
    """

    NOT_ASSESSED = "not_assessed"
    RESEARCH_ONLY = "research_only"
    PAPER_LIVE = "paper_live"
    CALIBRATED_PAPER = "calibrated_paper"
    SHADOW_LIVE = "shadow_live"
    TINY_CAP_LIVE = "tiny_cap_live"


# Ordered levels for comparison.
_LEVEL_ORDER: dict[ReadinessLevel, int] = {
    ReadinessLevel.NOT_ASSESSED: 0,
    ReadinessLevel.RESEARCH_ONLY: 1,
    ReadinessLevel.PAPER_LIVE: 2,
    ReadinessLevel.CALIBRATED_PAPER: 3,
    ReadinessLevel.SHADOW_LIVE: 4,
    ReadinessLevel.TINY_CAP_LIVE: 5,
}


def level_at_least(current: ReadinessLevel, required: ReadinessLevel) -> bool:
    """True if current readiness is at or above the required level."""
    return _LEVEL_ORDER.get(current, 0) >= _LEVEL_ORDER.get(required, 0)


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------


class CriterionStatus(str, Enum):
    """Status of a single readiness criterion."""

    MET = "met"
    NOT_MET = "not_met"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReadinessCriterion:
    """A single readiness criterion evaluation.

    name: machine-readable criterion identifier.
    description: human-readable description.
    status: whether the criterion is met.
    blocker_reason: why the criterion is not met (None if met).
    evidence: supporting data for audit.
    """

    name: str
    description: str
    status: CriterionStatus
    blocker_reason: str | None = None
    evidence: dict = field(default_factory=dict)

    @property
    def is_met(self) -> bool:
        return self.status == CriterionStatus.MET

    @property
    def is_blocker(self) -> bool:
        return self.status == CriterionStatus.NOT_MET


# ---------------------------------------------------------------------------
# Readiness status
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadinessStatus:
    """Complete readiness assessment snapshot.

    level: the highest readiness level currently achievable.
    criteria: all evaluated criteria.
    blockers: criteria that are not met (prevent promotion).
    assessed_at_ns: when this assessment was performed.
    evidence: audit metadata.
    """

    level: ReadinessLevel
    criteria: tuple[ReadinessCriterion, ...]
    assessed_at_ns: int
    evidence: dict = field(default_factory=dict)

    @property
    def blockers(self) -> tuple[ReadinessCriterion, ...]:
        return tuple(c for c in self.criteria if c.is_blocker)

    @property
    def met_criteria(self) -> tuple[ReadinessCriterion, ...]:
        return tuple(c for c in self.criteria if c.is_met)

    @property
    def unknown_criteria(self) -> tuple[ReadinessCriterion, ...]:
        return tuple(c for c in self.criteria if c.status == CriterionStatus.UNKNOWN)

    @property
    def blocker_names(self) -> list[str]:
        return [c.name for c in self.blockers]

    @property
    def is_paper_ready(self) -> bool:
        return level_at_least(self.level, ReadinessLevel.PAPER_LIVE)

    @property
    def is_live_ready(self) -> bool:
        return level_at_least(self.level, ReadinessLevel.TINY_CAP_LIVE)


# ---------------------------------------------------------------------------
# Readiness evaluator
# ---------------------------------------------------------------------------


# Standard criterion names for each level.
RESEARCH_CRITERIA = (
    "execution_engine_initialized",
    "edge_definitions_loaded",
    "backtest_data_available",
)

PAPER_LIVE_CRITERIA = (
    *RESEARCH_CRITERIA,
    "live_data_feed_connected",
    "order_book_valid",
    "fill_pricer_configured",
    "system_state_engine_running",
    "evidence_store_writable",
    "execution_intelligence_active",
)

CALIBRATED_PAPER_CRITERIA = (
    *PAPER_LIVE_CRITERIA,
    "paper_campaign_completed",
    "paper_fill_calibration_available",
    "tca_records_sufficient",
)

SHADOW_LIVE_CRITERIA = (
    *CALIBRATED_PAPER_CRITERIA,
    "venue_metadata_live",
    "routing_engine_configured",
    "risk_limits_set",
    "kill_switch_tested",
)

TINY_CAP_LIVE_CRITERIA = (
    *SHADOW_LIVE_CRITERIA,
    "live_api_credentials_valid",
    "margin_requirements_verified",
    "canary_allocation_set",
    "operator_approval_recorded",
)

OPTIONAL_READINESS_CRITERIA = frozenset(
    {
        "external_regime_evidence_available",
        "external_regime_evidence_sufficient",
        "external_regime_scenario_nontrivial_coverage",
        "external_regime_not_stale_dominated",
        "external_regime_not_unavailable_dominated",
        "external_regime_not_high_risk_dominated",
        "external_regime_gating_not_dominant",
        "paper_shadow_evidence_available",
        "paper_shadow_evidence_passed",
        "paper_shadow_evidence_blocked",
        "paper_shadow_evidence_bundle_complete",
    }
)

NEGATED_READINESS_CRITERIA = frozenset({"paper_shadow_evidence_blocked"})


@dataclass(frozen=True)
class ReadinessEvaluatorConfig:
    """Configuration for readiness evaluation.

    criteria_overrides: dict of criterion_name → CriterionStatus to
    force-override specific criteria (e.g., for testing).
    """

    criteria_overrides: dict[str, CriterionStatus] = field(default_factory=dict)


class ReadinessEvaluator:
    """Evaluates system readiness from a set of criterion flags.

    Usage::

        evaluator = ReadinessEvaluator()
        status = evaluator.evaluate(
            flags={"execution_engine_initialized": True, "live_data_feed_connected": False, ...},
            assessed_at_ns=time.time_ns(),
        )
        print(status.level, status.blocker_names)

    Design:
      - Conservative: UNKNOWN criteria block promotion.
      - Each level requires ALL criteria of that level to be MET.
      - Highest achievable level is returned.
    """

    def __init__(self, config: ReadinessEvaluatorConfig | None = None) -> None:
        self._config = config or ReadinessEvaluatorConfig()

    def evaluate(
        self,
        flags: dict[str, bool | None],
        assessed_at_ns: int,
    ) -> ReadinessStatus:
        """Evaluate readiness from a dict of criterion flags.

        flags: mapping of criterion_name → True (met), False (not met),
               or None (unknown).
        assessed_at_ns: evaluation timestamp in ns.
        """
        criteria = self._build_criteria(flags)
        level = self._determine_level(criteria)

        return ReadinessStatus(
            level=level,
            criteria=tuple(criteria),
            assessed_at_ns=assessed_at_ns,
            evidence={
                "evaluator": "ReadinessEvaluator",
                "total_criteria": len(criteria),
                "met": sum(1 for c in criteria if c.is_met),
                "not_met": sum(1 for c in criteria if c.is_blocker),
                "unknown": sum(1 for c in criteria if c.status == CriterionStatus.UNKNOWN),
            },
        )

    def _build_criteria(
        self,
        flags: dict[str, bool | None],
    ) -> list[ReadinessCriterion]:
        """Build criterion objects from flags."""
        all_names = set(TINY_CAP_LIVE_CRITERIA)
        all_names.update(name for name in flags if name in OPTIONAL_READINESS_CRITERIA)
        criteria = []

        for name in sorted(all_names):
            override = self._config.criteria_overrides.get(name)
            if override is not None:
                status = override
                reason = "overridden" if override == CriterionStatus.NOT_MET else None
            elif name in flags:
                val = flags[name]
                if name in NEGATED_READINESS_CRITERIA and val is False:
                    status = CriterionStatus.MET
                    reason = None
                elif name in NEGATED_READINESS_CRITERIA and val is True:
                    status = CriterionStatus.NOT_MET
                    reason = f"{name} is blocking readiness"
                elif val is True:
                    status = CriterionStatus.MET
                    reason = None
                elif val is False:
                    status = CriterionStatus.NOT_MET
                    reason = f"{name} is not satisfied"
                else:
                    status = CriterionStatus.UNKNOWN
                    reason = f"{name} has not been evaluated"
            else:
                status = CriterionStatus.UNKNOWN
                reason = f"{name} not provided in flags"

            criteria.append(
                ReadinessCriterion(
                    name=name,
                    description=_CRITERION_DESCRIPTIONS.get(name, name),
                    status=status,
                    blocker_reason=reason,
                )
            )

        return criteria

    def _determine_level(
        self,
        criteria: list[ReadinessCriterion],
    ) -> ReadinessLevel:
        """Determine the highest achievable readiness level.

        Conservative: if any criterion for a level is NOT_MET or UNKNOWN,
        that level and all above it are blocked.
        """
        criteria_by_name = {c.name: c for c in criteria}

        def _all_met(names: tuple[str, ...]) -> bool:
            return all(criteria_by_name.get(n, _UNKNOWN_CRITERION).is_met for n in names)

        if _all_met(TINY_CAP_LIVE_CRITERIA):
            return ReadinessLevel.TINY_CAP_LIVE
        if _all_met(SHADOW_LIVE_CRITERIA):
            return ReadinessLevel.SHADOW_LIVE
        if _all_met(CALIBRATED_PAPER_CRITERIA):
            return ReadinessLevel.CALIBRATED_PAPER
        if _all_met(PAPER_LIVE_CRITERIA):
            return ReadinessLevel.PAPER_LIVE
        if _all_met(RESEARCH_CRITERIA):
            return ReadinessLevel.RESEARCH_ONLY
        return ReadinessLevel.NOT_ASSESSED


# Sentinel for missing criteria.
_UNKNOWN_CRITERION = ReadinessCriterion(
    name="_unknown",
    description="Unknown criterion",
    status=CriterionStatus.UNKNOWN,
    blocker_reason="criterion not evaluated",
)

# Human-readable descriptions for standard criteria.
_CRITERION_DESCRIPTIONS: dict[str, str] = {
    "execution_engine_initialized": "Execution engine is initialized and accepting requests",
    "edge_definitions_loaded": "At least one edge definition is loaded and validated",
    "backtest_data_available": "Historical data sufficient for backtesting is available",
    "live_data_feed_connected": "Live market data feed is connected and streaming",
    "order_book_valid": "Order book has valid bid/ask with acceptable spread",
    "fill_pricer_configured": "Fill pricer is configured with realistic parameters",
    "system_state_engine_running": "System state engine is running and producing health signals",
    "evidence_store_writable": "Evidence store directory is writable and functional",
    "execution_intelligence_active": "Execution intelligence (route binding + TCA loop) is active or explicitly disabled",
    "paper_campaign_completed": "At least one paper campaign has run to completion",
    "paper_fill_calibration_available": "Paper fill accuracy has been measured against reference",
    "tca_records_sufficient": "Sufficient TCA records exist for statistical analysis",
    "venue_metadata_live": "Venue fee and operational metadata is live (not hardcoded)",
    "routing_engine_configured": "Routing engine has venue scores and cost estimates",
    "risk_limits_set": "Risk limits (position size, leverage, drawdown) are configured",
    "kill_switch_tested": "Kill-switch has been tested and verified functional",
    "live_api_credentials_valid": "Live exchange API credentials are valid and permissioned",
    "margin_requirements_verified": "Margin requirements have been verified with the exchange",
    "canary_allocation_set": "Canary allocation size has been set (max $500 notional)",
    "operator_approval_recorded": "Operator has explicitly approved live trading",
    "external_regime_evidence_available": "External regime evidence is available on the campaign surface",
    "external_regime_evidence_sufficient": "External regime evidence is sufficient to support governance decisions",
    "external_regime_scenario_nontrivial_coverage": "Campaign completed with non-trivial external regime scenario coverage",
    "external_regime_not_stale_dominated": "External regime scenario was not dominated by stale conditions",
    "external_regime_not_unavailable_dominated": "External regime scenario was not dominated by unavailable conditions",
    "external_regime_not_high_risk_dominated": "External regime scenario was not dominated by high-risk conditions",
    "external_regime_gating_not_dominant": "External regime gating did not dominate campaign operation",
    "paper_shadow_evidence_available": "Paper/shadow evidence bundle is available",
    "paper_shadow_evidence_passed": "Paper/shadow evidence bundle passed",
    "paper_shadow_evidence_blocked": "Paper/shadow evidence bundle is not blocked",
    "paper_shadow_evidence_bundle_complete": "Paper/shadow evidence bundle includes all run-report drilldowns",
}


def paper_shadow_evidence_readiness_flags(bundle: object | None) -> dict[str, bool]:
    """Return conservative readiness flags from a PaperShadowEvidenceBundle."""
    bridge = paper_shadow_evidence_readiness_bridge(bundle)
    return {
        "paper_shadow_evidence_available": bool(bridge["paper_shadow_evidence_available"]),
        "paper_shadow_evidence_passed": bool(bridge["paper_shadow_evidence_passed"]),
        "paper_shadow_evidence_blocked": bool(bridge["paper_shadow_evidence_blocked"]),
        "paper_shadow_evidence_bundle_complete": bool(bridge["paper_shadow_evidence_bundle_complete"]),
    }


def paper_shadow_evidence_readiness_bridge(bundle: object | None) -> dict:
    """Build a compact readiness bridge from the bundle artifact only.

    Missing bundle is explicit and not supportive. Malformed bundle payloads
    fail through the bundle loader/serializer instead of being recomputed here.
    """
    if bundle is None:
        return {
            "paper_shadow_evidence_available": False,
            "paper_shadow_evidence_passed": False,
            "paper_shadow_evidence_blocked": False,
            "paper_shadow_evidence_bundle_complete": False,
            "paper_shadow_evidence_status": "missing",
            "bundle_id": None,
            "aggregate_id": None,
            "report_ids": [],
            "missing_report_ids": [],
            "blockers": ["paper_shadow_evidence_unavailable"],
            "reason_codes": ["paper_shadow_evidence_bundle_missing"],
            "next_actions": ["build_paper_shadow_evidence_bundle"],
            "supportive": False,
        }

    from crypto_core.service.paper_shadow_session_controller import (
        PaperShadowEvidenceBundle,
        PaperShadowRunEvidenceStatus,
        paper_shadow_evidence_bundle_from_dict,
        paper_shadow_evidence_bundle_to_dict,
    )

    resolved = paper_shadow_evidence_bundle_from_dict(bundle) if isinstance(bundle, dict) else bundle
    if not isinstance(resolved, PaperShadowEvidenceBundle):
        raise ValueError("paper_shadow_evidence_readiness_bridge requires a PaperShadowEvidenceBundle")
    paper_shadow_evidence_bundle_to_dict(resolved)

    nested_report_ids = tuple(report.report_id for report in resolved.run_reports)
    complete = not resolved.missing_report_ids and nested_report_ids == resolved.report_ids
    unsafe = not resolved.paper_only or resolved.real_orders_enabled or resolved.real_money_enabled
    blocked = resolved.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED or bool(resolved.blockers) or unsafe
    if not complete:
        blocked = True
    passed = resolved.evidence_status == PaperShadowRunEvidenceStatus.PASS and complete and not blocked
    blockers = list(resolved.blockers)
    if not complete:
        blockers.append("paper_shadow_evidence_incomplete")
    if unsafe:
        blockers.append("unsafe_real_trading_flags")
    if blocked and not blockers:
        blockers.append("paper_shadow_evidence_blocked")

    return {
        "paper_shadow_evidence_available": True,
        "paper_shadow_evidence_passed": passed,
        "paper_shadow_evidence_blocked": blocked,
        "paper_shadow_evidence_bundle_complete": complete,
        "paper_shadow_evidence_status": resolved.evidence_status.value,
        "bundle_id": resolved.bundle_id,
        "aggregate_id": resolved.aggregate_report.aggregate_id,
        "report_ids": list(resolved.report_ids),
        "missing_report_ids": list(resolved.missing_report_ids),
        "blockers": sorted(dict.fromkeys(blockers)),
        "reason_codes": list(resolved.reason_codes),
        "next_actions": list(resolved.next_actions),
        "supportive": passed,
    }


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def readiness_to_dict(status: ReadinessStatus) -> dict:
    """Serialize ReadinessStatus to a plain dict."""
    return {
        "level": status.level.value,
        "assessed_at_ns": status.assessed_at_ns,
        "blockers": status.blocker_names,
        "criteria": [
            {
                "name": c.name,
                "description": c.description,
                "status": c.status.value,
                "blocker_reason": c.blocker_reason,
            }
            for c in status.criteria
        ],
        "summary": {
            "met": len(status.met_criteria),
            "not_met": len(status.blockers),
            "unknown": len(status.unknown_criteria),
            "total": len(status.criteria),
        },
        "evidence": status.evidence,
    }


def readiness_from_dict(d: dict) -> ReadinessStatus:
    """Deserialize ReadinessStatus from a plain dict.

    Raises ValueError on malformed data (fail-closed).
    """
    try:
        criteria = tuple(
            ReadinessCriterion(
                name=c["name"],
                description=c.get("description", c["name"]),
                status=CriterionStatus(c["status"]),
                blocker_reason=c.get("blocker_reason"),
            )
            for c in d["criteria"]
        )
        return ReadinessStatus(
            level=ReadinessLevel(d["level"]),
            criteria=criteria,
            assessed_at_ns=int(d["assessed_at_ns"]),
            evidence=d.get("evidence", {}),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Malformed readiness status: {exc}") from exc
