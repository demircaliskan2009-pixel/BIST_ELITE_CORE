"""Portfolio governor consumption — Phase 16D.

Consumes a paper-only ``PortfolioAllocationRecord`` (the output of
``project_governed_allocation``) and projects it into a deterministic, fail-closed
portfolio-governor lifecycle directive that a paper portfolio/governor surface can apply —
without re-sizing, without touching the broad ``sleeve_portfolio`` controller, and without
producing any order intent, live route, venue execution, or scheduler.

This is the *apply-time* governor boundary: where a planning-time allocation record becomes
an actionable paper-governor target directive. It adds an independent operational gate
(kill-switch / no-trade / operator halt) evaluated at apply time — distinct from the
projection's planning-time halt — because live operational state may differ from the state
that held when the record was projected. The gate accepts both raw operational blocker
strings and a structured ``NoTradeDecision`` from the existing No-Trade Guard surface.

Design rules:
  - Consume, don't re-size: per-sleeve weights and notionals are taken verbatim from the
    record. Nothing per-sleeve is recomputed; only aggregate invariants are re-derived for
    integrity (sum of targets vs claimed totals; total notional vs total weight * capital).
  - Paper-only enforcement: a record with real orders/money enabled (or paper_only not True)
    is rejected outright.
  - Apply-time operational gate: any supplied operational blocker, or a non-allowed
    ``NoTradeDecision``, zeroes the directive (no effective governor action).
  - Fail closed: a BLOCKED record, an operational halt, a malformed/non-paper record, missing
    provenance, or an internally inconsistent record (claimed totals not matching its targets,
    or totals exceeding the record budget/capital) yields no targets; nothing defaults
    permissive.
  - Provenance: plan_id, source_decision_digest, view_digest and record_digest are all
    preserved; the directive carries its own canonical SHA-256 digest.
  - PAPER ONLY: no order intent, no live/private execution, no scheduler/venue/route.

Direct wiring into the broad ``sleeve_portfolio`` controller is intentionally deferred: that
surface is far too large to wire safely in one bounded slice. This module is the bounded
governor-consumption seam between the allocation record and that controller.

PRD reference: §1.14-§1.28 Risk/Governance, §1.21 No-Trade, §7 Execution Engine, Phase 16D.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.guard.models import NoTradeDecision
from crypto_core.service.allocator_risk_bridge import AllocationStatus
from crypto_core.service.portfolio_allocation_projection import (
    PortfolioAllocationRecord,
    SleeveTarget,
)

_DIRECTIVE_SCHEMA_VERSION = "portfolio-governor-directive.v1"
_RECORD_SCHEMA_VERSION = "portfolio-allocation-record.v1"
_PRECISION = 12
_TOLERANCE = 1e-9
_FIXED_UNIT = 10**-_PRECISION
_AGGREGATE_TOLERANCE_MULTIPLIER = 4

_RECORD_BLOCKED_BLOCKER = "portfolio_governor:record_blocked"
_OPERATIONAL_HALT_BLOCKER = "portfolio_governor:operational_halt"
_NO_TRADE_BLOCKER_PREFIX = "portfolio_governor:no_trade_block"


class PortfolioGovernorError(RuntimeError):
    """Raised when a governor-consumption input is malformed, non-paper, or tampered (fail-closed)."""


class GovernorActionType(str, Enum):
    """Paper-only governor lifecycle action. Never an order/route/venue action."""

    SET_PAPER_TARGET = "set_paper_target"
    HOLD = "hold"


@dataclass(frozen=True)
class SleeveTargetDirective:
    """A single paper-governor lifecycle directive: set a sleeve's paper target. PAPER ONLY."""

    sleeve_id: str
    action: GovernorActionType
    weight: float
    notional: float


@dataclass(frozen=True)
class PortfolioGovernorDirective:
    """Deterministic, provenance-bound paper-governor lifecycle directive. PAPER ONLY."""

    plan_id: str
    status: AllocationStatus
    action: GovernorActionType
    budget: float
    capital_base: float
    total_weight: float
    total_notional: float
    targets: tuple[SleeveTargetDirective, ...]
    blockers: tuple[str, ...]
    source_decision_digest: str
    view_digest: str
    record_digest: str
    directive_digest: str
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _stable_blockers(values: object, *, error: str) -> tuple[str, ...]:
    if not isinstance(values, (tuple, list)):
        raise PortfolioGovernorError(error)
    blockers: list[str] = []
    for value in values:
        if not _non_empty_str(value):
            raise PortfolioGovernorError(error)
        blockers.append(value)
    return tuple(blockers)


def _stable_no_trade_reason(reason: object) -> str:
    if isinstance(reason, str):
        value = reason
    else:
        enum_value = getattr(reason, "value", None)
        if not isinstance(enum_value, str):
            raise PortfolioGovernorError("portfolio_governor:no_trade_reason_malformed")
        value = enum_value
    if not value:
        raise PortfolioGovernorError("portfolio_governor:no_trade_reason_malformed")
    return value


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _is_positive_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _directive_digest(payload: dict[str, object]) -> str:
    return _canonical_digest(payload)


def _expected_record_digest(
    record: PortfolioAllocationRecord,
    targets: tuple[SleeveTarget, ...],
    blockers: tuple[str, ...],
) -> str:
    return _canonical_digest(
        {
            "schema_version": _RECORD_SCHEMA_VERSION,
            "plan_id": record.plan_id,
            "status": record.status.value,
            "budget": record.budget,
            "capital_base": record.capital_base,
            "total_weight": record.total_weight,
            "total_notional": record.total_notional,
            "targets": [[target.sleeve_id, target.weight, target.notional] for target in targets],
            "blockers": list(blockers),
            "source_decision_digest": record.source_decision_digest,
            "view_digest": record.view_digest,
            "paper_only": True,
            "real_orders_enabled": False,
            "real_money_enabled": False,
        }
    )


def _validate_record_targets(targets: object) -> tuple[SleeveTarget, ...]:
    if not isinstance(targets, tuple):
        raise PortfolioGovernorError("portfolio_governor:targets_malformed")
    validated: list[SleeveTarget] = []
    for target in targets:
        if not isinstance(target, SleeveTarget):
            raise PortfolioGovernorError("portfolio_governor:target_malformed")
        if not _non_empty_str(target.sleeve_id):
            raise PortfolioGovernorError("portfolio_governor:sleeve_id_invalid")
        if not _is_positive_finite(target.weight):
            raise PortfolioGovernorError("portfolio_governor:weight_invalid")
        if not _is_non_negative_finite(target.notional):
            raise PortfolioGovernorError("portfolio_governor:notional_invalid")
        validated.append(target)
    return tuple(validated)


def _notional_tolerance(target_count: int) -> float:
    return max(
        _TOLERANCE,
        _FIXED_UNIT * max(1, target_count) * _AGGREGATE_TOLERANCE_MULTIPLIER,
    )


def consume_portfolio_allocation(
    record: PortfolioAllocationRecord,
    *,
    operational_blockers: tuple[str, ...] = (),
    no_trade_decision: NoTradeDecision | None = None,
) -> PortfolioGovernorDirective:
    """Consume a paper-only ``PortfolioAllocationRecord`` into a paper-governor lifecycle directive.

    Per-sleeve weights and notionals are consumed verbatim from the record; nothing is re-sized.
    A BLOCKED record, any supplied operational blocker, a non-allowed ``NoTradeDecision``, missing
    provenance, an invalid budget/capital, or an internally inconsistent record (claimed totals not
    matching the targets, total notional not matching total weight * capital, or totals exceeding the
    record budget) yields a HOLD directive with no targets (fail closed). An ALLOCATED, consistent
    record yields a deterministic ``SET_PAPER_TARGET`` directive per sleeve. plan_id and the
    source/view/record digests are preserved for audit. No order intent or live wiring is produced.
    """
    if not isinstance(record, PortfolioAllocationRecord):
        raise PortfolioGovernorError("portfolio_governor:record_malformed")
    is_paper = record.paper_only is True and record.real_orders_enabled is False and record.real_money_enabled is False
    if not is_paper:
        raise PortfolioGovernorError("portfolio_governor:non_paper_record_rejected")
    if not isinstance(record.status, AllocationStatus):
        raise PortfolioGovernorError("portfolio_governor:status_invalid")
    if not (
        _non_empty_str(record.plan_id)
        and _non_empty_str(record.source_decision_digest)
        and _non_empty_str(record.view_digest)
        and _non_empty_str(record.record_digest)
    ):
        raise PortfolioGovernorError("portfolio_governor:provenance_missing")
    if not _is_non_negative_finite(record.budget):
        raise PortfolioGovernorError("portfolio_governor:budget_invalid")
    if not _is_positive_finite(record.capital_base):
        raise PortfolioGovernorError("portfolio_governor:capital_base_invalid")
    budget = float(record.budget)
    capital = float(record.capital_base)

    record_targets = _validate_record_targets(record.targets)
    record_blockers = _stable_blockers(record.blockers, error="portfolio_governor:record_blockers_malformed")
    if record.record_digest != _expected_record_digest(record, record_targets, record_blockers):
        raise PortfolioGovernorError("portfolio_governor:record_digest_mismatch")

    operational = _sorted_unique(
        _stable_blockers(operational_blockers, error="portfolio_governor:operational_blockers_malformed")
    )
    no_trade_reason: str | None = None
    if no_trade_decision is not None:
        if not isinstance(no_trade_decision, NoTradeDecision):
            raise PortfolioGovernorError("portfolio_governor:no_trade_decision_malformed")
        if not isinstance(no_trade_decision.allowed, bool):
            raise PortfolioGovernorError("portfolio_governor:no_trade_decision_malformed")
        if not no_trade_decision.allowed:
            no_trade_reason = _stable_no_trade_reason(no_trade_decision.reason)
    halted = bool(operational) or no_trade_reason is not None
    record_blocked = record.status != AllocationStatus.ALLOCATED

    if halted or record_blocked:
        targets: tuple[SleeveTargetDirective, ...] = ()
        total_weight = 0.0
        total_notional = 0.0
        status = AllocationStatus.BLOCKED
        action = GovernorActionType.HOLD
    else:
        directive_list: list[SleeveTargetDirective] = []
        seen_sleeves: set[str] = set()
        for target in record_targets:
            if target.sleeve_id in seen_sleeves:
                raise PortfolioGovernorError("portfolio_governor:duplicate_sleeve_id")
            seen_sleeves.add(target.sleeve_id)
            expected_notional = round(float(target.weight) * capital, _PRECISION)
            if float(target.notional) <= 0.0 or expected_notional <= 0.0:
                raise PortfolioGovernorError("portfolio_governor:notional_invalid")
            if abs(float(target.notional) - expected_notional) > _notional_tolerance(1):
                raise PortfolioGovernorError("portfolio_governor:target_notional_inconsistent")
            directive_list.append(
                SleeveTargetDirective(
                    sleeve_id=target.sleeve_id,
                    action=GovernorActionType.SET_PAPER_TARGET,
                    weight=float(target.weight),
                    notional=float(target.notional),
                )
            )
        # An ALLOCATED record must carry targets; an empty target set is a tampered/inconsistent state.
        if not directive_list:
            raise PortfolioGovernorError("portfolio_governor:allocated_without_targets")
        directive_list.sort(key=lambda directive: directive.sleeve_id)

        total_weight = round(math.fsum(directive.weight for directive in directive_list), _PRECISION)
        total_notional = round(math.fsum(directive.notional for directive in directive_list), _PRECISION)
        notional_budget = round(budget * capital, _PRECISION)
        notional_tolerance = _notional_tolerance(len(directive_list))
        # The record's own aggregate totals must agree with the consumed per-sleeve targets, and the
        # aggregate notional must agree with total_weight * capital_base. Any mismatch is a tampered or
        # inconsistent record and is rejected (fail closed) rather than driving a governor action.
        if abs(total_weight - record.total_weight) > _TOLERANCE:
            raise PortfolioGovernorError("portfolio_governor:total_weight_inconsistent")
        if abs(total_notional - record.total_notional) > notional_tolerance:
            raise PortfolioGovernorError("portfolio_governor:total_notional_inconsistent")
        if abs(total_notional - round(total_weight * capital, _PRECISION)) > notional_tolerance:
            raise PortfolioGovernorError("portfolio_governor:notional_weight_inconsistent")
        if total_weight > budget + _TOLERANCE:
            raise PortfolioGovernorError("portfolio_governor:total_weight_exceeds_budget")
        if total_notional > notional_budget + notional_tolerance:
            raise PortfolioGovernorError("portfolio_governor:total_notional_exceeds_budget")
        targets = tuple(directive_list)
        status = AllocationStatus.ALLOCATED
        action = GovernorActionType.SET_PAPER_TARGET

    blocker_values = list(record_blockers)
    if record_blocked:
        blocker_values.append(_RECORD_BLOCKED_BLOCKER)
    if operational:
        blocker_values.append(_OPERATIONAL_HALT_BLOCKER)
        blocker_values.extend(operational)
    if no_trade_reason is not None:
        blocker_values.append(f"{_NO_TRADE_BLOCKER_PREFIX}:{no_trade_reason}")
    blockers = _sorted_unique(tuple(blocker_values))

    digest_payload: dict[str, object] = {
        "schema_version": _DIRECTIVE_SCHEMA_VERSION,
        "plan_id": record.plan_id,
        "status": status.value,
        "action": action.value,
        "budget": record.budget,
        "capital_base": record.capital_base,
        "total_weight": total_weight,
        "total_notional": total_notional,
        "targets": [[t.sleeve_id, t.action.value, t.weight, t.notional] for t in targets],
        "blockers": list(blockers),
        "source_decision_digest": record.source_decision_digest,
        "view_digest": record.view_digest,
        "record_digest": record.record_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PortfolioGovernorDirective(
        plan_id=record.plan_id,
        status=status,
        action=action,
        budget=record.budget,
        capital_base=record.capital_base,
        total_weight=total_weight,
        total_notional=total_notional,
        targets=targets,
        blockers=blockers,
        source_decision_digest=record.source_decision_digest,
        view_digest=record.view_digest,
        record_digest=record.record_digest,
        directive_digest=_directive_digest(digest_payload),
    )
