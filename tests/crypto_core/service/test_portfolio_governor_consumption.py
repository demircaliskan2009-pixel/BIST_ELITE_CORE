"""Tests for Phase 16D — portfolio governor consumption.

Covers ``consume_portfolio_allocation``: consuming a paper-only ``PortfolioAllocationRecord``
into a deterministic, fail-closed paper-governor lifecycle directive (per-sleeve
``SET_PAPER_TARGET`` directives) with an independent apply-time operational gate.

  1. Malformed record -> error (fail-closed)
  2. Non-paper record -> rejected (fail-closed)
  3. Missing provenance -> rejected (fail-closed)
  4. Invalid budget / capital_base -> rejected (fail-closed)
  5. BLOCKED record -> no effective governor action (HOLD)
  6. Operational halt blocker -> zeroed directive, halt blocker surfaced
  7. Non-allowed NoTradeDecision -> zeroed directive, no-trade blocker surfaced
  8. Allowed NoTradeDecision -> does not block
  9. Happy path -> deterministic SET_PAPER_TARGET directives, weights+notionals verbatim
 10. Provenance preserved (plan_id, source_decision_digest, view_digest, record_digest)
 11. Tampered aggregate totals / inconsistent target totals -> fail closed
 12. Totals bounded by record budget / capital
 13. Blockers sorted-unique and auditable
 14. Deterministic repeated output (including directive digest)
 15. Paper-only invariants; no order/route/scheduler/venue field produced

PRD reference: §1.14-§1.28 Risk/Governance, §1.21 No-Trade, §7 Execution Engine, Phase 16D.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import fields, replace

import pytest

from crypto_core.guard.models import NoTradeDecision, NoTradeReason
from crypto_core.service.allocation_governor_view import govern_allocation_decision
from crypto_core.service.allocator_risk_bridge import (
    AllocationStatus,
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.portfolio_allocation_projection import (
    SleeveTarget,
    project_governed_allocation,
)
from crypto_core.service.portfolio_governor_consumption import (
    GovernorActionType,
    PortfolioGovernorError,
    consume_portfolio_allocation,
)
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_EPS = 1e-9
_CAPITAL = 10_000.0
_RECORD_SCHEMA_VERSION = "portfolio-allocation-record.v1"


def _ready_plan(active=("micro-1", "micro-2"), caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:deadbeef",
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=active,
        pbo_allocation_caps=caps,
    )


def _allocated_record(budget=1.0, capital_base=_CAPITAL):
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=True),
        "micro-2": SleeveRiskDecision("micro-2", approved=True),
    }
    view = govern_allocation_decision(build_allocation_decision(_ready_plan(), risk, budget=budget))
    return project_governed_allocation(view, capital_base=capital_base)


def _blocked_record():
    plan = PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=("micro-1",),
        evidence_blockers=("sleeve_admission_evidence:currentness_missing",),
    )
    decision = build_allocation_decision(plan, {"micro-1": SleeveRiskDecision("micro-1", approved=True)})
    view = govern_allocation_decision(decision)
    return project_governed_allocation(view, capital_base=_CAPITAL)


def _record_digest(record) -> str:
    payload = {
        "schema_version": _RECORD_SCHEMA_VERSION,
        "plan_id": record.plan_id,
        "status": record.status.value,
        "budget": record.budget,
        "capital_base": record.capital_base,
        "total_weight": record.total_weight,
        "total_notional": record.total_notional,
        "targets": [[target.sleeve_id, target.weight, target.notional] for target in record.targets],
        "blockers": list(record.blockers),
        "source_decision_digest": record.source_decision_digest,
        "view_digest": record.view_digest,
        "paper_only": True,
        "real_orders_enabled": False,
        "real_money_enabled": False,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _with_recomputed_record_digest(record):
    return replace(record, record_digest=_record_digest(record))


def test_malformed_record_raises():
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation({"not": "a record"})


def test_non_paper_record_rejected():
    record = _allocated_record()
    for bad in (
        replace(record, real_orders_enabled=True),
        replace(record, real_money_enabled=True),
        replace(record, paper_only=False),
    ):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(bad)


def test_missing_provenance_rejected():
    record = _allocated_record()
    for bad in (
        replace(record, plan_id=""),
        replace(record, source_decision_digest=""),
        replace(record, view_digest=""),
        replace(record, record_digest=""),
    ):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(bad)


def test_invalid_budget_or_capital_rejected():
    for bad in (
        replace(_allocated_record(), budget=-1.0),
        replace(_allocated_record(), budget=float("nan")),
        replace(_allocated_record(), budget=True),
        replace(_allocated_record(), capital_base=0.0),
        replace(_allocated_record(), capital_base=-1.0),
        replace(_allocated_record(), capital_base=float("inf")),
        replace(_allocated_record(), capital_base=True),
    ):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(bad)


def test_blocked_record_yields_hold():
    directive = consume_portfolio_allocation(_blocked_record())
    assert directive.status == AllocationStatus.BLOCKED
    assert directive.action == GovernorActionType.HOLD
    assert directive.targets == ()
    assert directive.total_weight == 0.0
    assert directive.total_notional == 0.0
    assert "portfolio_governor:record_blocked" in directive.blockers


def test_operational_halt_zeroes_directive():
    directive = consume_portfolio_allocation(
        _allocated_record(),
        operational_blockers=("kill_switch:ks_blocked", "no_trade:active", "operator_halt:manual"),
    )
    assert directive.status == AllocationStatus.BLOCKED
    assert directive.action == GovernorActionType.HOLD
    assert directive.targets == ()
    assert directive.total_notional == 0.0
    assert "portfolio_governor:operational_halt" in directive.blockers
    assert "kill_switch:ks_blocked" in directive.blockers
    assert "no_trade:active" in directive.blockers
    assert "operator_halt:manual" in directive.blockers


def test_no_trade_decision_block_zeroes_directive():
    blocked = NoTradeDecision.block(NoTradeReason.KS_ACTIVE, {"rule": "NT-R01"})
    directive = consume_portfolio_allocation(_allocated_record(), no_trade_decision=blocked)
    assert directive.status == AllocationStatus.BLOCKED
    assert directive.action == GovernorActionType.HOLD
    assert directive.targets == ()
    assert "portfolio_governor:no_trade_block:NT-R01_ks_active" in directive.blockers


def test_no_trade_decision_allow_does_not_block():
    allowed = NoTradeDecision.allow({"symbol": "BTCUSDT"})
    directive = consume_portfolio_allocation(_allocated_record(), no_trade_decision=allowed)
    assert directive.status == AllocationStatus.ALLOCATED
    assert directive.action == GovernorActionType.SET_PAPER_TARGET
    assert not any(blocker.startswith("portfolio_governor:no_trade_block:") for blocker in directive.blockers)


def test_malformed_no_trade_decision_rejected():
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(_allocated_record(), no_trade_decision="blocked")  # type: ignore[arg-type]


def test_malformed_blocked_no_trade_reason_rejected():
    for reason in (None, "", object()):
        blocked = NoTradeDecision(allowed=False, reason=reason, severity=None, evidence={})  # type: ignore[arg-type]
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(_allocated_record(), no_trade_decision=blocked)


def test_happy_path_sets_paper_targets():
    record = _allocated_record(budget=1.0)
    directive = consume_portfolio_allocation(record)
    assert directive.status == AllocationStatus.ALLOCATED
    assert directive.action == GovernorActionType.SET_PAPER_TARGET
    by_sleeve = {target.sleeve_id: target for target in directive.targets}
    assert set(by_sleeve) == {"micro-1", "micro-2"}
    for target in directive.targets:
        assert target.action == GovernorActionType.SET_PAPER_TARGET
    assert by_sleeve["micro-1"].weight == 0.5
    assert abs(by_sleeve["micro-1"].notional - 5_000.0) < _EPS
    assert abs(directive.total_notional - 10_000.0) < _EPS


def test_weights_and_notionals_verbatim():
    record = _allocated_record(budget=1.0)
    directive = consume_portfolio_allocation(record)
    record_targets = {target.sleeve_id: target for target in record.targets}
    directive_targets = {target.sleeve_id: target for target in directive.targets}
    assert set(record_targets) == set(directive_targets)
    for sleeve_id, record_target in record_targets.items():
        assert directive_targets[sleeve_id].weight == record_target.weight
        assert directive_targets[sleeve_id].notional == record_target.notional
    assert directive.total_weight == record.total_weight
    assert directive.total_notional == record.total_notional


def test_totals_bounded_by_record_budget_and_capital():
    record = _allocated_record(budget=1.0)
    directive = consume_portfolio_allocation(record)
    assert directive.total_weight <= record.budget + _EPS
    assert directive.total_notional <= record.budget * record.capital_base + _EPS


def test_provenance_preserved():
    record = _allocated_record()
    directive = consume_portfolio_allocation(record)
    assert directive.plan_id == record.plan_id
    assert directive.source_decision_digest == record.source_decision_digest
    assert directive.view_digest == record.view_digest
    assert directive.record_digest == record.record_digest
    assert len(directive.directive_digest) == 64


def test_valid_projected_record_passes_record_digest_verification():
    record = _allocated_record()
    directive = consume_portfolio_allocation(record)
    assert directive.record_digest == record.record_digest


def test_stale_record_digest_rejects_tampered_sleeve_id():
    record = _allocated_record()
    first, *rest = record.targets
    tampered = replace(
        record,
        targets=(SleeveTarget(sleeve_id="forged-sleeve", weight=first.weight, notional=first.notional), *rest),
    )
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_stale_record_digest_rejects_tampered_target_weight_or_notional():
    record = _allocated_record()
    first, *rest = record.targets
    tampered_weight = replace(
        record,
        targets=(SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight + 0.1, notional=first.notional), *rest),
    )
    tampered_notional = replace(
        record,
        targets=(SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight, notional=first.notional + 1.0), *rest),
    )
    for tampered in (tampered_weight, tampered_notional):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(tampered)


def test_stale_record_digest_rejects_tampered_blockers_or_provenance():
    record = _allocated_record()
    for tampered in (
        replace(record, blockers=("forged:blocker",)),
        replace(record, source_decision_digest="forged-source-digest"),
        replace(record, view_digest="forged-view-digest"),
    ):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(tampered)


def test_self_consistent_redistributed_target_notional_fails_closed():
    record = _allocated_record(budget=1.0)
    first, second = record.targets
    tampered = _with_recomputed_record_digest(
        replace(
            record,
            targets=(
                SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight, notional=0.0),
                SleeveTarget(sleeve_id=second.sleeve_id, weight=second.weight, notional=record.total_notional),
            ),
        )
    )
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_positive_weight_zero_notional_fails_closed():
    record = _allocated_record(budget=1.0)
    first, *rest = record.targets
    tampered = _with_recomputed_record_digest(
        replace(
            record,
            targets=(SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight, notional=0.0), *rest),
        )
    )
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_duplicate_sleeve_ids_fail_closed():
    record = _allocated_record(budget=1.0)
    first, second = record.targets
    tampered = _with_recomputed_record_digest(
        replace(
            record,
            targets=(
                SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight, notional=first.notional),
                SleeveTarget(sleeve_id=first.sleeve_id, weight=second.weight, notional=second.notional),
            ),
        )
    )
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_large_notional_budget_does_not_expand_tolerance():
    record = _allocated_record(budget=1.0, capital_base=1_000_000_000_000.0)
    tampered = _with_recomputed_record_digest(replace(record, total_notional=record.total_notional + 500.0))
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_tiny_capital_valid_rounding_passes():
    record = _allocated_record(budget=1.0, capital_base=0.000001)
    directive = consume_portfolio_allocation(record)
    assert directive.status == AllocationStatus.ALLOCATED
    assert directive.total_notional == record.total_notional


def test_malformed_operational_blockers_rejected():
    for blockers in (("",), (123,)):
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(_allocated_record(), operational_blockers=blockers)  # type: ignore[arg-type]


def test_malformed_record_blockers_rejected():
    record = _allocated_record()
    for blockers in (("",), (123,)):
        tampered = _with_recomputed_record_digest(replace(record, blockers=blockers))  # type: ignore[arg-type]
        with pytest.raises(PortfolioGovernorError):
            consume_portfolio_allocation(tampered)


def test_tampered_total_weight_fails_closed():
    record = _allocated_record(budget=1.0)
    tampered = replace(record, total_weight=record.total_weight + 0.25)
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_tampered_total_notional_fails_closed():
    record = _allocated_record(budget=1.0)
    tampered = replace(record, total_notional=record.total_notional + 1_000.0)
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_tampered_target_notional_fails_closed():
    record = _allocated_record(budget=1.0)
    first, *rest = record.targets
    bumped = SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight, notional=first.notional + 1_000.0)
    tampered = replace(record, targets=(bumped, *rest))
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_tampered_target_weight_fails_closed():
    record = _allocated_record(budget=1.0)
    first, *rest = record.targets
    bumped = SleeveTarget(sleeve_id=first.sleeve_id, weight=first.weight + 0.25, notional=first.notional)
    tampered = replace(record, targets=(bumped, *rest))
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_allocated_without_targets_fails_closed():
    record = _allocated_record(budget=1.0)
    tampered = replace(record, targets=(), total_weight=0.0, total_notional=0.0)
    with pytest.raises(PortfolioGovernorError):
        consume_portfolio_allocation(tampered)


def test_blockers_sorted_and_unique():
    directive = consume_portfolio_allocation(
        _blocked_record(),
        operational_blockers=("z", "a", "z"),
    )
    assert directive.blockers == tuple(sorted(set(directive.blockers)))


def test_deterministic_repeated_output():
    record = _allocated_record()
    first = consume_portfolio_allocation(record)
    second = consume_portfolio_allocation(record)
    assert first == second
    assert first.directive_digest == second.directive_digest


def test_paper_only_invariants_and_no_order_fields():
    directive = consume_portfolio_allocation(_allocated_record())
    assert directive.paper_only is True
    assert directive.real_orders_enabled is False
    assert directive.real_money_enabled is False
    # No order/route/venue/scheduler surface may leak into the governor directive contract.
    field_names = {field.name for field in fields(directive)}
    forbidden = {"order", "order_intent", "route", "venue", "exchange", "schedule", "scheduler", "live"}
    assert field_names.isdisjoint(forbidden)
    target_field_names = {field.name for field in fields(directive.targets[0])}
    assert target_field_names.isdisjoint(forbidden)
    for action in (directive.action, *(target.action for target in directive.targets)):
        assert action in {GovernorActionType.SET_PAPER_TARGET, GovernorActionType.HOLD}
