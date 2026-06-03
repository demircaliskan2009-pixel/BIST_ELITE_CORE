"""Portfolio governor ledger entry — Phase 16E.

Projects a paper-only ``PortfolioGovernorDirective`` (the output of
``consume_portfolio_allocation``) into a deterministic, provenance-bound, canonical audit
ledger entry that the paper governor lifecycle can record — before any controller/application
wiring exists.

This is a *projection*, not a store write: it builds the auditable ledger-entry object (with
its own canonical SHA-256 digest and the full upstream provenance chain expressed as audit
``DecisionEvidenceRef`` evidence) that can be written to a decision ledger / evidence store
later. Direct writing into the existing ``DecisionLedgerRecord`` is intentionally deferred:
that record's contract is keyed on the StrategySpec -> LBR -> PIT validation stages
(strategy_id / strategy_digest / input/output digests) and does not fit a portfolio governor
directive without distorting its schema. This bounded entry reuses only the audit
``DecisionEvidenceRef`` vocabulary, keeping the seam small and audit-coherent.

Design rules:
  - Consume, don't recompute: status, action, targets, weights, notionals and blockers are
    taken verbatim from the directive. No sizing / projection / governor-consumption decision
    logic is duplicated; the directive digest is recomputed only to verify integrity.
  - Paper-only enforcement: a directive with real orders/money enabled (or paper_only not True)
    is rejected outright.
  - Fail closed: a malformed/non-paper directive, missing provenance, a directive whose digest
    does not match its content (tampered), or a structurally inconsistent directive (HOLD with
    targets, or ALLOCATED/SET_PAPER_TARGET without targets) is rejected; nothing defaults
    permissive.
  - Provenance: plan_id, source_decision_digest, view_digest, record_digest and directive_digest
    are all preserved; the upstream digests are bound as evidence refs and the entry carries its
    own canonical digest.
  - PAPER ONLY: no order intent, no live/private execution, no scheduler/venue/route.

PRD reference: §1.14-§1.28 Risk/Governance, §4 DecisionLedger/EvidenceStore, Phase 16E.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from enum import Enum

from crypto_core.audit.decision_ledger import DecisionEvidenceRef
from crypto_core.service.allocator_risk_bridge import AllocationStatus
from crypto_core.service.portfolio_governor_consumption import (
    GovernorActionType,
    PortfolioGovernorDirective,
    SleeveTargetDirective,
)

_ENTRY_SCHEMA_VERSION = "portfolio-governor-ledger-entry.v1"
_DIRECTIVE_SCHEMA_VERSION = "portfolio-governor-directive.v1"
_PRECISION = 12
_TOLERANCE = 1e-9
_FIXED_UNIT = 10**-_PRECISION
_AGGREGATE_TOLERANCE_MULTIPLIER = 4
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdefABCDEF")

_EVIDENCE_SOURCE_DECISION = "portfolio_allocation_decision"
_EVIDENCE_SOURCE_VIEW = "allocation_governor_view"
_EVIDENCE_SOURCE_RECORD = "portfolio_allocation_record"
_EVIDENCE_SOURCE_DIRECTIVE = "portfolio_governor_directive"


class PortfolioGovernorLedgerError(RuntimeError):
    """Raised when a governor-directive ledger projection input is malformed or tampered (fail-closed)."""


class PortfolioGovernorLedgerStatus(str, Enum):
    """Auditable paper-governor lifecycle posture recorded by the ledger entry."""

    RECORDED_ACTIVE = "recorded_active"
    RECORDED_BLOCKED = "recorded_blocked"


@dataclass(frozen=True)
class PortfolioGovernorLedgerEntry:
    """Deterministic, provenance-bound paper-governor audit ledger entry. PAPER ONLY."""

    schema_version: str
    status: PortfolioGovernorLedgerStatus
    action: GovernorActionType
    plan_id: str
    source_decision_digest: str
    view_digest: str
    record_digest: str
    directive_digest: str
    budget: float
    capital_base: float
    total_weight: float
    total_notional: float
    targets: tuple[SleeveTargetDirective, ...]
    blockers: tuple[str, ...]
    evidence_refs: tuple[DecisionEvidenceRef, ...]
    correlation_id: str
    entry_digest: str
    previous_entry_digest: str | None = None
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False


def _non_empty_str(value: object) -> bool:
    return isinstance(value, str) and value != ""


def _sha256_hex_digest(value: object) -> bool:
    return isinstance(value, str) and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_non_negative_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value >= 0


def _is_positive_finite(value: object) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and math.isfinite(value) and value > 0


def _sorted_unique(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted(set(values)))


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _serialize_targets(targets: tuple[SleeveTargetDirective, ...]) -> list[list[object]]:
    return [[t.sleeve_id, t.action.value, t.weight, t.notional] for t in targets]


def _notional_tolerance(target_count: int) -> float:
    return max(
        _TOLERANCE,
        _FIXED_UNIT * max(1, target_count) * _AGGREGATE_TOLERANCE_MULTIPLIER,
    )


def _expected_directive_digest(directive: PortfolioGovernorDirective) -> str:
    # Mirror of the governor-consumption directive digest payload. Recomputed here only to verify
    # the supplied directive has not been tampered with (matching the upstream consumer pattern);
    # it does not re-derive any sizing/gating decision. A real directive built by
    # ``consume_portfolio_allocation`` keeps this in lockstep (asserted by the tests).
    payload: dict[str, object] = {
        "schema_version": _DIRECTIVE_SCHEMA_VERSION,
        "plan_id": directive.plan_id,
        "status": directive.status.value,
        "action": directive.action.value,
        "budget": directive.budget,
        "capital_base": directive.capital_base,
        "total_weight": directive.total_weight,
        "total_notional": directive.total_notional,
        "targets": _serialize_targets(directive.targets),
        "blockers": list(directive.blockers),
        "source_decision_digest": directive.source_decision_digest,
        "view_digest": directive.view_digest,
        "record_digest": directive.record_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    return _canonical_digest(payload)


def _validate_directive_targets(directive: PortfolioGovernorDirective) -> tuple[SleeveTargetDirective, ...]:
    if not isinstance(directive.targets, tuple):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:targets_malformed")
    seen: set[str] = set()
    for target in directive.targets:
        if not isinstance(target, SleeveTargetDirective):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:target_malformed")
        if not _non_empty_str(target.sleeve_id):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:sleeve_id_invalid")
        if not isinstance(target.action, GovernorActionType):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:target_action_invalid")
        if not _is_positive_finite(target.weight):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:weight_invalid")
        if not _is_non_negative_finite(target.notional):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:notional_invalid")
        if target.sleeve_id in seen:
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:duplicate_sleeve_id")
        seen.add(target.sleeve_id)
    return directive.targets


def _validate_active_target_totals(
    directive: PortfolioGovernorDirective,
    targets: tuple[SleeveTargetDirective, ...],
) -> None:
    total_weight = round(math.fsum(target.weight for target in targets), _PRECISION)
    total_notional = round(math.fsum(target.notional for target in targets), _PRECISION)
    notional_tolerance = _notional_tolerance(len(targets))

    for target in targets:
        expected_notional = round(float(target.weight) * float(directive.capital_base), _PRECISION)
        if float(target.notional) <= 0.0 or expected_notional <= 0.0:
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:notional_invalid")
        if abs(float(target.notional) - expected_notional) > _notional_tolerance(1):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:target_notional_inconsistent")

    if abs(total_weight - float(directive.total_weight)) > _TOLERANCE:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:total_weight_inconsistent")
    if abs(total_notional - float(directive.total_notional)) > notional_tolerance:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:total_notional_inconsistent")
    if abs(total_notional - round(total_weight * float(directive.capital_base), _PRECISION)) > notional_tolerance:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:notional_weight_inconsistent")

    notional_budget = round(float(directive.budget) * float(directive.capital_base), _PRECISION)
    if total_weight > float(directive.budget) + _TOLERANCE:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:total_weight_exceeds_budget")
    if total_notional > notional_budget + notional_tolerance:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:total_notional_exceeds_budget")


def _resolve_ledger_status(
    directive: PortfolioGovernorDirective,
    targets: tuple[SleeveTargetDirective, ...],
) -> PortfolioGovernorLedgerStatus:
    if directive.status == AllocationStatus.ALLOCATED:
        if directive.action != GovernorActionType.SET_PAPER_TARGET or not targets:
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_inconsistent")
        if any(target.action != GovernorActionType.SET_PAPER_TARGET for target in targets):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_inconsistent")
        if not (directive.total_weight > 0.0):
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_inconsistent")
        _validate_active_target_totals(directive, targets)
        return PortfolioGovernorLedgerStatus.RECORDED_ACTIVE
    if directive.status == AllocationStatus.BLOCKED:
        if directive.action != GovernorActionType.HOLD or targets:
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_inconsistent")
        if abs(directive.total_weight) > _TOLERANCE or abs(directive.total_notional) > _TOLERANCE:
            raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_inconsistent")
        return PortfolioGovernorLedgerStatus.RECORDED_BLOCKED
    raise PortfolioGovernorLedgerError("portfolio_governor_ledger:status_unknown")


def build_portfolio_governor_ledger_entry(
    directive: PortfolioGovernorDirective,
    *,
    correlation_id: str,
    previous_entry_digest: str | None = None,
) -> PortfolioGovernorLedgerEntry:
    """Project a paper-only ``PortfolioGovernorDirective`` into a deterministic audit ledger entry.

    Status, action, targets, weights, notionals and blockers are preserved verbatim from the
    directive. A malformed/non-paper directive, missing provenance, a digest that does not match
    the directive content (tampered), or a structurally inconsistent directive yields a fail-closed
    ``PortfolioGovernorLedgerError``. The upstream digests are preserved and bound as evidence refs,
    and the entry carries its own canonical digest. No order intent or live wiring is produced.
    """
    if not isinstance(directive, PortfolioGovernorDirective):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_malformed")
    if not isinstance(directive.status, AllocationStatus) or not isinstance(directive.action, GovernorActionType):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_malformed")
    is_paper = (
        directive.paper_only is True
        and directive.real_orders_enabled is False
        and directive.real_money_enabled is False
    )
    if not is_paper:
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:non_paper_directive_rejected")
    if not (
        _non_empty_str(directive.plan_id)
        and _sha256_hex_digest(directive.source_decision_digest)
        and _sha256_hex_digest(directive.view_digest)
        and _sha256_hex_digest(directive.record_digest)
        and _sha256_hex_digest(directive.directive_digest)
    ):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:provenance_missing")
    if not _non_empty_str(correlation_id):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:correlation_id_missing")
    if previous_entry_digest is not None and not _sha256_hex_digest(previous_entry_digest):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:previous_entry_digest_invalid")
    if not _is_non_negative_finite(directive.budget):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:budget_invalid")
    if not _is_positive_finite(directive.capital_base):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:capital_base_invalid")
    if not (_is_non_negative_finite(directive.total_weight) and _is_non_negative_finite(directive.total_notional)):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:totals_invalid")

    targets = _validate_directive_targets(directive)

    if not isinstance(directive.blockers, tuple) or any(not _non_empty_str(value) for value in directive.blockers):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:blockers_malformed")
    if directive.blockers != _sorted_unique(directive.blockers):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:blockers_not_canonical")

    # Integrity: the directive's own digest must match its content (tamper detection).
    if directive.directive_digest != _expected_directive_digest(directive):
        raise PortfolioGovernorLedgerError("portfolio_governor_ledger:directive_digest_mismatch")

    ledger_status = _resolve_ledger_status(directive, targets)

    evidence_refs = (
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_DECISION, digest=directive.source_decision_digest),
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_VIEW, digest=directive.view_digest),
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_RECORD, digest=directive.record_digest),
        DecisionEvidenceRef(source_type=_EVIDENCE_SOURCE_DIRECTIVE, digest=directive.directive_digest),
    )

    entry_payload: dict[str, object] = {
        "schema_version": _ENTRY_SCHEMA_VERSION,
        "status": ledger_status.value,
        "action": directive.action.value,
        "plan_id": directive.plan_id,
        "source_decision_digest": directive.source_decision_digest,
        "view_digest": directive.view_digest,
        "record_digest": directive.record_digest,
        "directive_digest": directive.directive_digest,
        "budget": directive.budget,
        "capital_base": directive.capital_base,
        "total_weight": directive.total_weight,
        "total_notional": directive.total_notional,
        "targets": _serialize_targets(targets),
        "blockers": list(directive.blockers),
        "evidence_refs": [[ref.source_type, ref.digest] for ref in evidence_refs],
        "correlation_id": correlation_id,
        "previous_entry_digest": previous_entry_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }

    return PortfolioGovernorLedgerEntry(
        schema_version=_ENTRY_SCHEMA_VERSION,
        status=ledger_status,
        action=directive.action,
        plan_id=directive.plan_id,
        source_decision_digest=directive.source_decision_digest,
        view_digest=directive.view_digest,
        record_digest=directive.record_digest,
        directive_digest=directive.directive_digest,
        budget=directive.budget,
        capital_base=directive.capital_base,
        total_weight=directive.total_weight,
        total_notional=directive.total_notional,
        targets=targets,
        blockers=directive.blockers,
        evidence_refs=evidence_refs,
        correlation_id=correlation_id,
        entry_digest=_canonical_digest(entry_payload),
        previous_entry_digest=previous_entry_digest,
    )


def portfolio_governor_ledger_entry_to_dict(entry: PortfolioGovernorLedgerEntry) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a governor ledger entry (deterministic key/value shape)."""
    return {
        "schema_version": entry.schema_version,
        "status": entry.status.value,
        "action": entry.action.value,
        "plan_id": entry.plan_id,
        "source_decision_digest": entry.source_decision_digest,
        "view_digest": entry.view_digest,
        "record_digest": entry.record_digest,
        "directive_digest": entry.directive_digest,
        "budget": entry.budget,
        "capital_base": entry.capital_base,
        "total_weight": entry.total_weight,
        "total_notional": entry.total_notional,
        "targets": _serialize_targets(entry.targets),
        "blockers": list(entry.blockers),
        "evidence_refs": [{"source_type": ref.source_type, "digest": ref.digest} for ref in entry.evidence_refs],
        "correlation_id": entry.correlation_id,
        "previous_entry_digest": entry.previous_entry_digest,
        "entry_digest": entry.entry_digest,
        "paper_only": entry.paper_only,
        "real_orders_enabled": entry.real_orders_enabled,
        "real_money_enabled": entry.real_money_enabled,
    }
