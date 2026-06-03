"""Portfolio allocation projection — Phase 16C.

Consumes a paper-only ``GovernedAllocationView`` and projects it into a deterministic, fail-closed
portfolio allocation record that a paper portfolio/governor path can apply.

This is the first link that turns governed *weights* into *paper capital per sleeve*
(``notional = weight * capital_base``) and adds an independent operational governance gate
(kill-switch / no-trade / operator halt) that the upstream allocation/governor layers do not carry.

Design rules:
  - Consume, don't re-size: per-sleeve weights are taken verbatim from the governed view; only the
    paper-capital projection (weight * capital_base) is computed here.
  - Paper-only enforcement: a view with real orders/money enabled (or paper_only not True) is
    rejected outright.
  - Operational halt: any supplied halt blocker (kill-switch/no-trade/operator) zeroes the record.
  - Fail closed: a BLOCKED view, a halt, an invalid capital base, an inconsistent view total, or a
    malformed/non-paper view yields no portfolio targets (raise or empty); nothing defaults permissive.
  - Provenance: plan_id, source_decision_digest and view_digest are preserved; the record carries its
    own canonical SHA-256 digest.
  - PAPER ONLY: no order intent, no live/private execution, no scheduler/venue wiring is produced.

Direct wiring into the full sleeve-portfolio controller is intentionally deferred (too broad for one
bounded slice); this projection is the bounded adapter seam.

PRD reference: §1.14-§1.28 Risk/Governance, §7 Execution Engine, Phase 16C.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass

from crypto_core.service.allocation_governor_view import GovernedAllocationView
from crypto_core.service.allocator_risk_bridge import AllocationStatus

_RECORD_SCHEMA_VERSION = "portfolio-allocation-record.v1"
_PRECISION = 12
_TOLERANCE = 1e-9

_VIEW_BLOCKED_BLOCKER = "portfolio_allocation:view_blocked"
_OPERATIONAL_HALT_BLOCKER = "portfolio_allocation:operational_halt"


class PortfolioAllocationError(RuntimeError):
    """Raised when a portfolio allocation projection input is malformed or non-paper (fail-closed)."""


@dataclass(frozen=True)
class SleeveTarget:
    """A single paper portfolio target: governed weight projected onto the capital base."""

    sleeve_id: str
    weight: float
    notional: float


@dataclass(frozen=True)
class PortfolioAllocationRecord:
    """Deterministic, provenance-bound paper portfolio allocation record. PAPER ONLY."""

    plan_id: str
    status: AllocationStatus
    budget: float
    capital_base: float
    total_weight: float
    total_notional: float
    targets: tuple[SleeveTarget, ...]
    blockers: tuple[str, ...]
    source_decision_digest: str
    view_digest: str
    record_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _is_positive_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _record_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def project_governed_allocation(
    view: GovernedAllocationView,
    *,
    capital_base: float,
    halt_blockers: tuple[str, ...] = (),
) -> PortfolioAllocationRecord:
    """Project a paper-only ``GovernedAllocationView`` into a paper portfolio allocation record.

    Per-sleeve weights are consumed verbatim from the view; each target's ``notional`` is
    ``weight * capital_base``. A BLOCKED view, any supplied operational halt blocker, an invalid
    ``capital_base``, an inconsistent view total, or a malformed/non-paper view yields no targets
    (fail closed). The total weight never exceeds the view budget and the total notional never
    exceeds ``budget * capital_base``. plan_id and the source/view digests are preserved for audit.
    No order intent or live wiring is produced.
    """
    if not isinstance(view, GovernedAllocationView):
        raise PortfolioAllocationError("portfolio_allocation:view_malformed")
    is_paper = view.paper_only is True and view.real_orders_enabled is False and view.real_money_enabled is False
    if not is_paper:
        raise PortfolioAllocationError("portfolio_allocation:non_paper_view_rejected")
    if not _is_positive_finite(capital_base):
        raise PortfolioAllocationError("portfolio_allocation:capital_base_invalid")
    capital = float(capital_base)
    if not _is_non_negative_finite(view.budget):
        raise PortfolioAllocationError("portfolio_allocation:budget_invalid")
    budget = float(view.budget)
    if not _is_non_negative_finite(view.total_effective):
        raise PortfolioAllocationError("portfolio_allocation:total_effective_invalid")

    halt = _sorted_unique(tuple(halt_blockers))
    halted = bool(halt)
    view_blocked = view.status != AllocationStatus.ALLOCATED

    if halted or view_blocked:
        targets: tuple[SleeveTarget, ...] = ()
        total_weight = 0.0
        total_notional = 0.0
        status = AllocationStatus.BLOCKED
    else:
        target_list: list[SleeveTarget] = []
        effective_pairs: list[tuple[str, float]] = []
        if not isinstance(view.effective_allocations, tuple):
            raise PortfolioAllocationError("portfolio_allocation:effective_allocations_malformed")
        for item in view.effective_allocations:
            if not isinstance(item, tuple) or len(item) != 2:
                raise PortfolioAllocationError("portfolio_allocation:effective_allocations_malformed")
            sleeve_id, weight = item
            if not isinstance(sleeve_id, str) or sleeve_id == "":
                raise PortfolioAllocationError("portfolio_allocation:sleeve_id_invalid")
            if not _is_non_negative_finite(weight):
                raise PortfolioAllocationError("portfolio_allocation:weight_invalid")
            effective_pairs.append((sleeve_id, float(weight)))
        for sleeve_id, weight in sorted(effective_pairs, key=lambda item: item[0]):
            notional = round(float(weight) * capital, _PRECISION)
            target_list.append(SleeveTarget(sleeve_id=sleeve_id, weight=float(weight), notional=notional))
        total_weight = round(math.fsum(target.weight for target in target_list), _PRECISION)
        total_notional = round(math.fsum(target.notional for target in target_list), _PRECISION)
        # The view's own governed total must agree with the consumed weights (fail closed otherwise).
        if abs(total_weight - view.total_effective) > _TOLERANCE:
            raise PortfolioAllocationError("portfolio_allocation:view_total_inconsistent")
        if total_weight > budget + _TOLERANCE:
            raise PortfolioAllocationError("portfolio_allocation:total_weight_exceeds_budget")
        notional_budget = round(budget * capital, _PRECISION)
        notional_tolerance = max(_TOLERANCE, abs(notional_budget) * _TOLERANCE)
        if total_notional > notional_budget + notional_tolerance:
            raise PortfolioAllocationError("portfolio_allocation:total_notional_exceeds_budget")
        targets = tuple(target_list)
        status = AllocationStatus.ALLOCATED if targets else AllocationStatus.BLOCKED

    blocker_values = list(view.blockers)
    if view_blocked:
        blocker_values.append(_VIEW_BLOCKED_BLOCKER)
    if halted:
        blocker_values.append(_OPERATIONAL_HALT_BLOCKER)
        blocker_values.extend(halt)
    blockers = _sorted_unique(tuple(blocker_values))

    digest_payload: dict[str, object] = {
        "schema_version": _RECORD_SCHEMA_VERSION,
        "plan_id": view.plan_id,
        "status": status.value,
        "budget": view.budget,
        "capital_base": capital,
        "total_weight": total_weight,
        "total_notional": total_notional,
        "targets": [[target.sleeve_id, target.weight, target.notional] for target in targets],
        "blockers": list(blockers),
        "source_decision_digest": view.source_decision_digest,
        "view_digest": view.view_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PortfolioAllocationRecord(
        plan_id=view.plan_id,
        status=status,
        budget=view.budget,
        capital_base=capital,
        total_weight=total_weight,
        total_notional=total_notional,
        targets=targets,
        blockers=blockers,
        source_decision_digest=view.source_decision_digest,
        view_digest=view.view_digest,
        record_digest=_record_digest(digest_payload),
    )
