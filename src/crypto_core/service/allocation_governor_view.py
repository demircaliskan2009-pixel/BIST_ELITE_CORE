"""Allocation governor view — Phase 16B.

Governs an allocator <-> risk ``AllocationDecision`` into a paper-only, provenance-bound effective
allocation view that a downstream portfolio/governor layer can consume.

Design rules:
  - Consume, don't duplicate: per-sleeve weights and the budget are taken verbatim from the
    ``AllocationDecision``; this layer never recomputes sizing.
  - Paper-only enforcement: a decision with real orders/money enabled (or paper_only not True) is
    rejected outright — the governor never lets a non-paper decision flow.
  - Fail closed: a BLOCKED decision, a supplied governance halt, or a malformed decision yields an
    empty effective allocation; nothing defaults permissive.
  - Provenance: the source decision digest and plan id are preserved for audit; the view carries its
    own canonical SHA-256 digest.
  - PAPER ONLY: no order intent, no live/private execution, no scheduler wiring is produced.

PRD reference: §1.14-§1.28 Risk/Governance, §7 Execution Engine, Phase 16B.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from crypto_core.service.allocator_risk_bridge import AllocationDecision, AllocationStatus

_VIEW_SCHEMA_VERSION = "allocation-governor-view.v1"
_DECISION_BLOCKED_BLOCKER = "allocation_governor:decision_blocked"
_GOVERNANCE_HALT_BLOCKER = "allocation_governor:governance_halt"
_PRECISION = 12
_BUDGET_TOLERANCE = 1e-9


class AllocationGovernorError(RuntimeError):
    """Raised when a governor view input is malformed or non-paper (fail-closed)."""


@dataclass(frozen=True)
class GovernedAllocationView:
    """Paper-only, provenance-bound effective allocation view for the portfolio/governor layer."""

    plan_id: str
    status: AllocationStatus
    budget: float
    total_effective: float
    effective_allocations: tuple[tuple[str, float], ...]
    blockers: tuple[str, ...]
    source_decision_digest: str
    view_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _view_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def govern_allocation_decision(
    decision: AllocationDecision,
    *,
    governance_blockers: tuple[str, ...] = (),
) -> GovernedAllocationView:
    """Govern an ``AllocationDecision`` into a paper-only effective allocation view (fail-closed).

    Enforces paper-only safety (a decision with real orders/money enabled is rejected), collapses to
    effective allocations for ALLOCATED sleeves only, applies any supplied governance blockers as a
    hard halt, and preserves the source decision digest + plan id for audit. Per-sleeve weights are
    taken verbatim from the decision (never recomputed) and the total never exceeds the decision
    budget. BLOCKED decisions and governance halts yield an empty effective allocation. No order
    intent or live wiring is produced. Malformed input raises ``AllocationGovernorError``.
    """
    if not isinstance(decision, AllocationDecision):
        raise AllocationGovernorError("allocation_governor:decision_malformed")
    is_paper = (
        decision.paper_only is True and decision.real_orders_enabled is False and decision.real_money_enabled is False
    )
    if not is_paper:
        raise AllocationGovernorError("allocation_governor:non_paper_decision_rejected")

    if (
        isinstance(decision.budget, bool)
        or not isinstance(decision.budget, (int, float))
        or not math.isfinite(decision.budget)
        or decision.budget < 0
    ):
        raise AllocationGovernorError("allocation_governor:budget_invalid")
    budget = float(decision.budget)

    governance = _sorted_unique(tuple(governance_blockers))
    halted = bool(governance)
    decision_blocked = decision.status != AllocationStatus.ALLOCATED

    if halted or decision_blocked:
        effective: tuple[tuple[str, float], ...] = ()
        total_effective = 0.0
        status = AllocationStatus.BLOCKED
    else:
        effective_pairs: list[tuple[str, float]] = []
        for allocation in sorted(decision.allocations, key=lambda item: item.sleeve_id):
            if allocation.status != AllocationStatus.ALLOCATED:
                continue
            weight = allocation.weight
            if (
                isinstance(weight, bool)
                or not isinstance(weight, (int, float))
                or not math.isfinite(weight)
                or weight < 0
            ):
                raise AllocationGovernorError("allocation_governor:weight_invalid")
            if weight > 0.0:
                effective_pairs.append((allocation.sleeve_id, float(weight)))
        # Derive the governed total from the effective weights; never trust decision.total_allocated.
        total_effective = round(math.fsum(weight for _, weight in effective_pairs), _PRECISION)
        if total_effective > budget + _BUDGET_TOLERANCE:
            raise AllocationGovernorError("allocation_governor:total_exceeds_budget")
        # The decision's own aggregate must agree with the derived effective total (no nonzero total
        # with no effective sleeves, no oversized/tampered aggregate leaking downstream).
        total_allocated = decision.total_allocated
        if (
            isinstance(total_allocated, bool)
            or not isinstance(total_allocated, (int, float))
            or not math.isfinite(total_allocated)
            or abs(float(total_allocated) - total_effective) > _BUDGET_TOLERANCE
        ):
            raise AllocationGovernorError("allocation_governor:total_inconsistent")
        effective = tuple(effective_pairs)
        status = AllocationStatus.ALLOCATED if effective else AllocationStatus.BLOCKED

    blocker_values = list(decision.blockers)
    if decision_blocked:
        blocker_values.append(_DECISION_BLOCKED_BLOCKER)
    if halted:
        blocker_values.append(_GOVERNANCE_HALT_BLOCKER)
        blocker_values.extend(governance)
    blockers = _sorted_unique(tuple(blocker_values))

    digest_payload: dict[str, object] = {
        "schema_version": _VIEW_SCHEMA_VERSION,
        "plan_id": decision.plan_id,
        "status": status.value,
        "budget": decision.budget,
        "total_effective": total_effective,
        "effective_allocations": [[sleeve, weight] for sleeve, weight in effective],
        "blockers": list(blockers),
        "source_decision_digest": decision.decision_digest,
    }

    return GovernedAllocationView(
        plan_id=decision.plan_id,
        status=status,
        budget=decision.budget,
        total_effective=total_effective,
        effective_allocations=effective,
        blockers=blockers,
        source_decision_digest=decision.decision_digest,
        view_digest=_view_digest(digest_payload),
    )
