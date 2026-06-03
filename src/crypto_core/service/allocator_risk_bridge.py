"""Allocator <-> risk bridge — Phase 16A.

Deterministic, fail-closed transformation of an evidence-backed paper/shadow activation plan into a
risk-bounded paper allocation decision.

Design rules:
  - Only evidence-backed admitted-active sleeves from a READY activation plan are eligible.
  - Risk semantics are *consumed*, not duplicated: each sleeve carries a ``SleeveRiskDecision``
    (the risk engine's decision surface). Build it from a ``crypto_core.risk.models.RiskEvaluation``
    with the one-line adapter::

        SleeveRiskDecision(
            sleeve_id=sleeve_id,
            approved=evaluation.approved,
            block_reasons=() if evaluation.approved else (str(evaluation.block_reason),),
        )

  - Fail closed: a non-READY plan, a missing/blocked risk decision, or a non-positive per-sleeve cap
    yields zero allocation for that sleeve with a stable, auditable blocker — never a permissive
    default.
  - Deterministic and digestable: allocations are sorted by sleeve id, blockers are sorted-unique,
    weights are rounded to a fixed precision, and the decision carries a canonical SHA-256 digest.
  - PAPER ONLY: no order intent, no live/private execution, no scheduler wiring is produced.

PRD reference: §1.14-§1.28 Risk, §7 Execution Engine, Phase 16A.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
)

_DECISION_SCHEMA_VERSION = "allocator-risk-decision.v1"
_WEIGHT_PRECISION = 12

_PLAN_NOT_READY_BLOCKER = "allocator_risk:plan_not_ready"
_NO_ELIGIBLE_BLOCKER = "allocator_risk:no_eligible_sleeves"
_RISK_INPUT_MISSING_BLOCKER = "allocator_risk:risk_input_missing"
_RISK_BLOCKED_BLOCKER = "allocator_risk:risk_blocked"
_ZERO_CAP_BLOCKER = "allocator_risk:zero_allocation_cap"


class AllocatorRiskBridgeError(RuntimeError):
    """Raised when allocator <-> risk bridge inputs are malformed (fail-closed)."""


class AllocationStatus(str, Enum):
    ALLOCATED = "allocated"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SleeveRiskDecision:
    """A sleeve's risk decision, mirroring ``RiskEvaluation`` semantics (approved + block reasons)."""

    sleeve_id: str
    approved: bool
    block_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class SleeveAllocation:
    """Per-sleeve allocation outcome. ``weight`` is 0.0 whenever ``status`` is BLOCKED."""

    sleeve_id: str
    status: AllocationStatus
    weight: float
    cap: float
    block_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class AllocationDecision:
    """Deterministic, digest-bound paper allocation decision. PAPER ONLY."""

    plan_id: str
    status: AllocationStatus
    budget: float
    total_allocated: float
    allocations: tuple[SleeveAllocation, ...]
    blockers: tuple[str, ...]
    decision_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _allocation_decision_digest(payload: Mapping[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_allocation_decision(
    plan: PaperShadowActivationPlan,
    risk_by_sleeve: Mapping[str, SleeveRiskDecision],
    *,
    budget: float = 1.0,
) -> AllocationDecision:
    """Build a deterministic, fail-closed, risk-bounded paper allocation decision.

    Eligibility = the activation plan's admitted-active sleeves, but only when the plan is
    ``READY_FOR_PAPER_SHADOW``. Each eligible sleeve is allocated an equal share of ``budget`` across
    the risk-approved candidates, capped by its PBO allocation cap (``plan.pbo_allocation_caps``).
    Total allocation never exceeds ``budget`` and per-sleeve allocation never exceeds its cap.

    A sleeve receives zero allocation with a stable blocker when: the plan is not READY, no risk
    decision is supplied (fail-closed), its risk decision is not approved, or its cap is non-positive.
    Malformed inputs raise ``AllocatorRiskBridgeError``. No order intent or live wiring is produced.
    """
    if not isinstance(plan, PaperShadowActivationPlan):
        raise AllocatorRiskBridgeError("allocator_risk:plan_malformed")
    if not isinstance(risk_by_sleeve, Mapping):
        raise AllocatorRiskBridgeError("allocator_risk:risk_map_malformed")
    if isinstance(budget, bool) or not isinstance(budget, (int, float)) or not math.isfinite(budget) or budget < 0:
        raise AllocatorRiskBridgeError("allocator_risk:budget_invalid")

    budget = round(float(budget), _WEIGHT_PRECISION)
    caps = dict(plan.pbo_allocation_caps)
    eligible = tuple(sorted(set(plan.active_sleeves)))
    plan_ready = plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW

    # Classify each eligible sleeve: (sleeve_id, approved_for_allocation, cap_or_None, block_reasons).
    classified: list[tuple[str, bool, float | None, tuple[str, ...]]] = []
    for sleeve in eligible:
        cap = caps.get(sleeve)
        if cap is not None:
            cap = round(float(cap), _WEIGHT_PRECISION)
        if not plan_ready:
            classified.append((sleeve, False, cap, (_PLAN_NOT_READY_BLOCKER,)))
            continue
        risk = risk_by_sleeve.get(sleeve)
        if risk is None:
            classified.append((sleeve, False, cap, (_RISK_INPUT_MISSING_BLOCKER,)))
        elif not isinstance(risk, SleeveRiskDecision):
            raise AllocatorRiskBridgeError("allocator_risk:risk_decision_malformed")
        elif not risk.approved:
            classified.append((sleeve, False, cap, (_RISK_BLOCKED_BLOCKER, *risk.block_reasons)))
        elif cap is not None and cap <= 0.0:
            classified.append((sleeve, False, cap, (_ZERO_CAP_BLOCKER,)))
        else:
            classified.append((sleeve, True, cap, ()))

    candidate_count = sum(1 for _, approved, _, _ in classified if approved)
    equal_share = round(budget / candidate_count, _WEIGHT_PRECISION) if candidate_count > 0 else 0.0

    allocations: list[SleeveAllocation] = []
    total = 0.0
    for sleeve, approved, cap, reasons in classified:
        if approved:
            weight = round(equal_share if cap is None else min(equal_share, cap), _WEIGHT_PRECISION)
            total += weight
            allocations.append(
                SleeveAllocation(
                    sleeve_id=sleeve,
                    status=AllocationStatus.ALLOCATED,
                    weight=weight,
                    cap=cap if cap is not None else equal_share,
                    block_reasons=(),
                )
            )
        else:
            allocations.append(
                SleeveAllocation(
                    sleeve_id=sleeve,
                    status=AllocationStatus.BLOCKED,
                    weight=0.0,
                    cap=cap if cap is not None else 0.0,
                    block_reasons=_sorted_unique(reasons),
                )
            )
    total = round(total, _WEIGHT_PRECISION)
    allocations.sort(key=lambda allocation: allocation.sleeve_id)

    blocker_values: list[str] = []
    for allocation in allocations:
        blocker_values.extend(allocation.block_reasons)
    if not eligible:
        blocker_values.append(_NO_ELIGIBLE_BLOCKER)
    if not plan_ready:
        blocker_values.extend(plan.evidence_blockers)
        blocker_values.extend(plan.activation_blockers)
        blocker_values.extend(plan.governance_blockers)
    blockers = _sorted_unique(tuple(blocker_values))

    status = AllocationStatus.ALLOCATED if total > 0.0 else AllocationStatus.BLOCKED

    digest_payload = {
        "schema_version": _DECISION_SCHEMA_VERSION,
        "plan_id": plan.plan_id,
        "budget": budget,
        "status": status.value,
        "total_allocated": total,
        "allocations": [
            {
                "sleeve_id": allocation.sleeve_id,
                "status": allocation.status.value,
                "weight": allocation.weight,
                "cap": allocation.cap,
                "block_reasons": list(allocation.block_reasons),
            }
            for allocation in allocations
        ],
        "blockers": list(blockers),
    }

    return AllocationDecision(
        plan_id=plan.plan_id,
        status=status,
        budget=budget,
        total_allocated=total,
        allocations=tuple(allocations),
        blockers=blockers,
        decision_digest=_allocation_decision_digest(digest_payload),
    )
