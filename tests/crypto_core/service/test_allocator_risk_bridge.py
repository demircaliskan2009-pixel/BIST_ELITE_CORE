"""Tests for Phase 16A — allocator <-> risk bridge.

Covers ``build_allocation_decision``: turning an evidence-backed paper/shadow activation plan plus
per-sleeve risk decisions into a deterministic, risk-bounded, fail-closed paper allocation decision.

  1. Plan not READY -> every sleeve blocked, nothing allocated
  2. No eligible (active) sleeves -> blocked
  3. Missing risk input for an active sleeve -> blocked (fail-closed, not permissive)
  4. Risk-blocked sleeve -> zero allocation, reason surfaced
  5. Total allocation respects the budget cap
  6. Per-sleeve allocation respects the PBO cap
  7. Non-positive PBO cap -> blocked
  8. Deterministic repeated output (including the canonical digest)
  9. Blockers are sorted-unique and auditable
 10. Happy path -> bounded paper allocation, paper-only invariants
 11. Malformed plan -> AllocatorRiskBridgeError
 12. Invalid budget -> AllocatorRiskBridgeError
 13. Risk decisions for non-active sleeves are ignored (only evidence-backed sleeves are eligible)

PRD reference: §1.14-§1.28 Risk, §7 Execution Engine, Phase 16A.
"""

from __future__ import annotations

import pytest

from crypto_core.service.allocator_risk_bridge import (
    AllocationStatus,
    AllocatorRiskBridgeError,
    SleeveRiskDecision,
    build_allocation_decision,
)
from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    PaperShadowSourceManifestStatus,
)

_EPS = 1e-9


def _ready_plan(active=("micro-1", "micro-2"), caps=(("micro-1", 0.5), ("micro-2", 0.5))):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:deadbeef",
        activation_status=PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW,
        source_manifest_status=PaperShadowSourceManifestStatus.READY,
        active_sleeves=active,
        pbo_allocation_caps=caps,
    )


def _blocked_plan(active=("micro-1",), evidence_blockers=("sleeve_admission_evidence:currentness_missing",)):
    return PaperShadowActivationPlan(
        plan_id="paper-shadow-activation:blocked",
        activation_status=PaperShadowActivationStatus.BLOCKED,
        source_manifest_status=PaperShadowSourceManifestStatus.BLOCKED,
        active_sleeves=active,
        evidence_blockers=evidence_blockers,
    )


def _approved(sleeve_id):
    return SleeveRiskDecision(sleeve_id=sleeve_id, approved=True)


def _alloc_by_id(decision):
    return {allocation.sleeve_id: allocation for allocation in decision.allocations}


def test_plan_not_ready_blocks_all():
    plan = _blocked_plan(active=("micro-1", "micro-2"))
    decision = build_allocation_decision(plan, {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")})
    assert decision.status == AllocationStatus.BLOCKED
    assert decision.total_allocated == 0.0
    allocs = _alloc_by_id(decision)
    assert all(a.status == AllocationStatus.BLOCKED and a.weight == 0.0 for a in allocs.values())
    assert "allocator_risk:plan_not_ready" in decision.blockers
    # Plan's own upstream blockers are surfaced for auditability.
    assert "sleeve_admission_evidence:currentness_missing" in decision.blockers


def test_no_eligible_sleeves_blocked():
    plan = _ready_plan(active=(), caps=())
    decision = build_allocation_decision(plan, {})
    assert decision.status == AllocationStatus.BLOCKED
    assert decision.allocations == ()
    assert "allocator_risk:no_eligible_sleeves" in decision.blockers


def test_missing_risk_input_blocks_sleeve():
    plan = _ready_plan()
    # Only micro-1 has a risk decision; micro-2 is missing -> fail closed.
    decision = build_allocation_decision(plan, {"micro-1": _approved("micro-1")})
    allocs = _alloc_by_id(decision)
    assert allocs["micro-2"].status == AllocationStatus.BLOCKED
    assert allocs["micro-2"].weight == 0.0
    assert "allocator_risk:risk_input_missing" in allocs["micro-2"].block_reasons
    assert allocs["micro-1"].status == AllocationStatus.ALLOCATED


def test_risk_blocked_sleeve_zero_allocation():
    plan = _ready_plan()
    risk = {
        "micro-1": _approved("micro-1"),
        "micro-2": SleeveRiskDecision("micro-2", approved=False, block_reasons=("ks_blocked",)),
    }
    decision = build_allocation_decision(plan, risk)
    allocs = _alloc_by_id(decision)
    assert allocs["micro-2"].status == AllocationStatus.BLOCKED
    assert allocs["micro-2"].weight == 0.0
    assert "allocator_risk:risk_blocked" in allocs["micro-2"].block_reasons
    assert "ks_blocked" in allocs["micro-2"].block_reasons
    assert allocs["micro-1"].status == AllocationStatus.ALLOCATED


def test_budget_cap_respected():
    plan = _ready_plan(caps=(("micro-1", 1.0), ("micro-2", 1.0)))
    decision = build_allocation_decision(
        plan, {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}, budget=1.0
    )
    assert decision.total_allocated <= 1.0 + _EPS
    assert abs(decision.total_allocated - 1.0) < _EPS  # equal split fully uses budget when caps allow


def test_per_sleeve_pbo_cap_respected():
    plan = _ready_plan(caps=(("micro-1", 0.2), ("micro-2", 0.2)))
    decision = build_allocation_decision(
        plan, {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}, budget=1.0
    )
    allocs = _alloc_by_id(decision)
    assert allocs["micro-1"].weight <= 0.2 + _EPS
    assert allocs["micro-2"].weight <= 0.2 + _EPS
    assert decision.total_allocated <= 1.0 + _EPS
    assert abs(decision.total_allocated - 0.4) < _EPS


def test_zero_cap_blocks():
    plan = _ready_plan(caps=(("micro-1", 0.0), ("micro-2", 0.5)))
    decision = build_allocation_decision(plan, {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")})
    allocs = _alloc_by_id(decision)
    assert allocs["micro-1"].status == AllocationStatus.BLOCKED
    assert "allocator_risk:zero_allocation_cap" in allocs["micro-1"].block_reasons
    assert allocs["micro-2"].status == AllocationStatus.ALLOCATED


def test_deterministic_repeated_output():
    plan = _ready_plan()
    risk = {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}
    first = build_allocation_decision(plan, risk, budget=1.0)
    second = build_allocation_decision(plan, risk, budget=1.0)
    assert first == second
    assert first.decision_digest == second.decision_digest
    assert len(first.decision_digest) == 64


def test_blockers_sorted_and_auditable():
    plan = _ready_plan()
    risk = {
        "micro-1": SleeveRiskDecision("micro-1", approved=False, block_reasons=("z_reason", "a_reason")),
        # micro-2 missing -> risk_input_missing
    }
    decision = build_allocation_decision(plan, risk)
    assert decision.blockers == tuple(sorted(set(decision.blockers)))
    assert "allocator_risk:risk_blocked" in decision.blockers
    assert "a_reason" in decision.blockers
    assert "z_reason" in decision.blockers
    assert "allocator_risk:risk_input_missing" in decision.blockers


def test_happy_path_bounded_paper_allocation():
    plan = _ready_plan(caps=(("micro-1", 0.6), ("micro-2", 0.6)))
    decision = build_allocation_decision(
        plan, {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}, budget=1.0
    )
    assert decision.status == AllocationStatus.ALLOCATED
    assert all(a.status == AllocationStatus.ALLOCATED for a in decision.allocations)
    assert decision.total_allocated > 0.0
    assert decision.total_allocated <= 1.0 + _EPS
    assert decision.plan_id == "paper-shadow-activation:deadbeef"
    assert decision.paper_only is True
    assert decision.real_orders_enabled is False
    assert decision.real_money_enabled is False
    assert decision.decision_digest


def test_malformed_plan_raises():
    with pytest.raises(AllocatorRiskBridgeError):
        build_allocation_decision({"not": "a plan"}, {})


def test_invalid_budget_raises():
    plan = _ready_plan()
    risk = {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}
    with pytest.raises(AllocatorRiskBridgeError):
        build_allocation_decision(plan, risk, budget=-1.0)
    with pytest.raises(AllocatorRiskBridgeError):
        build_allocation_decision(plan, risk, budget=float("nan"))
    with pytest.raises(AllocatorRiskBridgeError):
        build_allocation_decision(plan, risk, budget=True)


def test_risk_for_non_active_sleeve_is_ignored():
    plan = _ready_plan(active=("micro-1",), caps=(("micro-1", 0.5),))
    # A risk decision for micro-2 (not in the plan's active sleeves) must not create an allocation.
    risk = {"micro-1": _approved("micro-1"), "micro-2": _approved("micro-2")}
    decision = build_allocation_decision(plan, risk, budget=1.0)
    allocs = _alloc_by_id(decision)
    assert set(allocs) == {"micro-1"}
    assert allocs["micro-1"].status == AllocationStatus.ALLOCATED


def test_budget_safe_when_equal_share_rounds_up():
    # Regression (P2): six approved sleeves at budget=1.0 -> equal share 0.166666666667 would sum to
    # 1.000000000002 without clamping. Summed weights must stay within budget.
    sleeves = tuple(f"micro-{i}" for i in range(1, 7))
    plan = _ready_plan(active=sleeves, caps=())  # uncapped -> equal-share path
    risk = {sleeve: _approved(sleeve) for sleeve in sleeves}
    decision = build_allocation_decision(plan, risk, budget=1.0)

    weights = [allocation.weight for allocation in decision.allocations]
    assert all(allocation.status == AllocationStatus.ALLOCATED for allocation in decision.allocations)
    assert sum(weights) <= 1.0
    assert decision.total_allocated <= 1.0
    assert decision.total_allocated == round(sum(weights), 12)
    # Deterministic and digest-stable across repeated calls.
    again = build_allocation_decision(plan, risk, budget=1.0)
    assert decision == again
    assert decision.decision_digest == again.decision_digest


def test_risk_decision_must_bind_to_sleeve():
    # Regression (P2): a risk decision stored under the wrong key (sleeve_id != map key) must NOT
    # approve the keyed sleeve. Fail closed with an auditable mismatch blocker.
    plan = _ready_plan(active=("micro-1",), caps=(("micro-1", 0.5),))
    risk = {"micro-1": SleeveRiskDecision("micro-2", approved=True)}
    decision = build_allocation_decision(plan, risk, budget=1.0)
    allocs = _alloc_by_id(decision)
    assert allocs["micro-1"].status == AllocationStatus.BLOCKED
    assert allocs["micro-1"].weight == 0.0
    assert "allocator_risk:risk_sleeve_mismatch" in allocs["micro-1"].block_reasons
    assert decision.status == AllocationStatus.BLOCKED
    assert "allocator_risk:risk_sleeve_mismatch" in decision.blockers
