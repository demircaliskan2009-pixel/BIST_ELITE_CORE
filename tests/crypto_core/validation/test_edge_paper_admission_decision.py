"""Tests for Edge Factory EF-7 v2 governed paper admission (EF7_EDGE_PAPER_ADMISSION_DECISION_V2).

Fixtures are REAL authenticated chains. The PASS chain is world P of the pre-paper validation module: a sealed
nine-variant ±20% / 5% star grid, its governed EF-6 PASS and its authentic pre-paper validation PASS (CSCV PBO 0, DSR
over the attested cumulative trial count, Monte Carlo, sensitivity and Stage-3 stress), which admits exactly the base
variant with the LIMITED_S1_PAPER_V1 cap fraction 1/4. Every other rule runs on the EF-6 module's cheap authentic chains
(world A: the cheap governed EF-6 over the same EF-5 shape with no bundle, READY + FAIL; the one-window NEEDS_GOVERNANCE
draft; a REJECTED state), each with its own authentic pre-paper evidence, which propagates the EF-6 verdict without
computing anything. World A's single-variant ledger can never pass the pre-paper gate. Both modules are imported under
the module names pytest collects them with (``tests/crypto_core/validation`` is not a package, so pytest imports test
files by basename); their ``functools`` caches and memos are therefore one object, and every world is built once per
process. Every governance, capacity and budget value below is a SYNTHETIC TEST VALUE; EF-7 holds no production number.

CI budget: decisions over the 46 MB PASS chain are limited to the draft, the approved PASS, one post-approval change and
the pre-paper propagation cases; every other rule is exercised on the cheap chain, whose reason codes expose each EF-7
rule even under the propagated FAIL. An extra authenticated world with synthetic facts is ``@pytest.mark.slow``.

Cost control: the pure public upstream functions EF-7 calls are memoized at EF-7's call site with the EF-6 module's memo:
the EF-6, EF-5, EF-4 and pre-paper evidence verifiers keyed exactly (exact type and every field value, so a str-enum
alias, ``True`` versus ``1`` and a tuple versus a list never collide) and the upstream strict parsers and shape predicates
keyed by the canonical JSON text of their argument (they only ever receive ``json.loads`` output here). The EF-6 and
pre-paper modules' own memos are applied so their worlds build once. EF-7's own code is never memoized.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import json
from dataclasses import MISSING, FrozenInstanceError, fields, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import crypto_core.validation.edge_paper_admission_decision as ef7_module
import crypto_core.validation.edge_walk_forward_oos_evidence as ef6_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_kill_criteria_policy,
    edge_kill_criteria_digest,
    edge_kill_criteria_policy_to_dict,
    edge_kill_criterion_to_dict,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EDGE_CAPACITY_EVIDENCE_STATUS,
    EDGE_PAPER_ADMISSION_HISTORICAL_SCHEMA_V1,
    EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS,
    EDGE_PAPER_ADMISSION_RULE_SET_DIGEST,
    EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING,
    EdgeAdmittedVariant,
    EdgeCapacityAssumption,
    EdgePaperAdmissionDecision,
    EdgePaperAdmissionDecisionError,
    EdgePaperAdmissionGovernance,
    build_edge_paper_admission_decision,
    edge_paper_admission_decision_digest,
    edge_paper_admission_decision_from_payload,
    edge_paper_admission_decision_payload_is_well_formed,
    edge_paper_admission_decision_to_dict,
    edge_paper_admission_rule_set,
    verify_edge_paper_admission_decision,
)
from crypto_core.validation.edge_pre_paper_validation_evidence import (
    edge_pre_paper_validation_evidence_digest,
    verify_edge_pre_paper_validation_evidence,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeWalkForwardOosEvidence,
    edge_walk_forward_oos_evidence_digest,
    edge_walk_forward_oos_evidence_from_payload,
    edge_walk_forward_oos_evidence_to_dict,
    verify_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetPolicy,
    build_paper_sleeve_risk_budget_policy,
    paper_sleeve_risk_budget_policy_digest,
)

try:  # the module objects pytest collects (basename import), so the authentic worlds and memos are built once
    import test_edge_pre_paper_validation_evidence as pret
    import test_edge_walk_forward_oos_evidence as ef6t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_pre_paper_validation_evidence as pret
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t

_PREFIX = "edge_paper_admission_decision"
_UNSET = object()
SLOW = pytest.mark.slow  # an extra authenticated economics world; see the module docstring
INS = ef6t.INS
OTHER_INS = "ETH-USDT-PERP"
SLEEVE = "carry-sleeve-1"
COMMITMENTS = (
    "predecessor_digest",
    "pre_paper_evidence_digest",
    "admission_subject_digest",
    "kill_criteria_record_digest",
    "risk_budget_policy_digest",
    "capacity_assumption_set_digest",
    "rule_set_digest",
)
# SYNTHETIC TEST VALUES: explicit bounded capacity assumptions, never venue facts.
CAPACITY = EdgeCapacityAssumption(
    assumption_id="capacity-notional",
    instrument=INS,
    capacity_measure_id="max_open_position_notional",
    unit_id="quote_currency_notional",
    scope_id="per_instrument_open_position",
    basis_id="governance_reviewed_assumption",
    max_value="250000.000000000000000000",
)
CAPACITY_OI = EdgeCapacityAssumption(
    assumption_id="capacity-open-interest",
    instrument=INS,
    capacity_measure_id="max_fraction_of_open_interest",
    unit_id="fraction",
    scope_id="per_instrument_open_position",
    basis_id="governance_reviewed_assumption",
    max_value="0.010000000000000000",
)
CAPACITY_OTHER = replace(CAPACITY, assumption_id="capacity-other", instrument=OTHER_INS)

# --- memoized pure upstream verifiers (see module docstring) -------------------------------------------------------------

# The EF-6 verifier memo is the pre-paper module's own: both call sites re-prove the same EF-6 objects.
_EF6_VERIFIER_MEMO = pret._PRE_MEMOS[(pret.ev_module, "verify_edge_walk_forward_oos_evidence")]
assert _EF6_VERIFIER_MEMO.real is verify_edge_walk_forward_oos_evidence  # type: ignore[attr-defined]
_EF7_MEMOS = {
    "verify_edge_walk_forward_oos_evidence": _EF6_VERIFIER_MEMO,
    "verify_edge_leakage_bias_evidence": ef6t._MEMOS[(ef6_module, "verify_edge_leakage_bias_evidence")],
    "verify_edge_strategy_spec_admission": ef6t._MEMOS[(ef6_module, "verify_edge_strategy_spec_admission")],
    "verify_edge_pre_paper_validation_evidence": pret._CallMemo(verify_edge_pre_paper_validation_evidence),
    **{
        name: ef6t._Memoized(getattr(ef7_module, name), edge_canonical_json)
        for name in (
            "edge_walk_forward_oos_evidence_payload_is_well_formed",
            "edge_walk_forward_oos_evidence_from_payload",
            "edge_pre_paper_validation_evidence_payload_is_well_formed",
            "edge_pre_paper_validation_evidence_from_payload",
            "edge_leakage_bias_evidence_from_payload",
            "edge_strategy_spec_admission_from_payload",
            "edge_source_packet_evidence_from_payload",
            "edge_idea_intake_evidence_from_payload",
            "edge_kill_criteria_policy_from_payload",
        )
    },
}


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        pret.apply_memos(patch)
        for name, memo in _EF7_MEMOS.items():
            patch.setattr(ef7_module, name, memo)
        yield


# --- fixtures ----------------------------------------------------------------------------------------------------------


@functools.cache
def budget_policy(sleeve_id: str = SLEEVE, total_budget: str = "1000") -> PaperSleeveRiskBudgetPolicy:
    """SYNTHETIC TEST VALUES: a paper-only intra-sleeve reservation policy (never an allocation)."""

    return build_paper_sleeve_risk_budget_policy(
        policy_id="paper-budget-1",
        sleeve_id=sleeve_id,
        total_budget=total_budget,
        per_intent_budget_cap="100",
        metadata={"review": "synthetic-test-value"},
    )


def arguments_for(predecessor: EdgeWalkForwardOosEvidence, **overrides: object) -> dict[str, object]:
    """Builder arguments over ``predecessor``, with its own default authentic pre-paper evidence unless overridden."""

    policy = budget_policy()
    evidence = overrides.pop("pre_paper_evidence", None) or pret.evidence_for(predecessor)
    arguments: dict[str, object] = {
        "expected_predecessor_digest": predecessor.walk_forward_oos_evidence_digest,
        "pre_paper_evidence": evidence,
        "expected_pre_paper_evidence_digest": evidence.pre_paper_validation_evidence_digest,  # type: ignore[attr-defined]
        "expected_root_intake_digest": ef6t.world()[0].intake_digest,
        "risk_budget_policy": policy,
        "expected_risk_budget_policy_digest": policy.policy_digest,
        "paper_sleeve_id": SLEEVE,
        "capacity_assumptions": (CAPACITY,),
        "decision_id": "ef7-1",
        "correlation_id": "corr-1",
    }
    arguments.update(overrides)
    return arguments


def decide(predecessor: EdgeWalkForwardOosEvidence, **overrides: object) -> EdgePaperAdmissionDecision:
    return build_edge_paper_admission_decision(predecessor, **arguments_for(predecessor, **overrides))  # type: ignore[arg-type]


def approval_for(decision: EdgePaperAdmissionDecision, **overrides: object) -> EdgePaperAdmissionGovernance:
    arguments: dict[str, object] = {
        "approval_reference": "governance-ef7-1",
        "approval_digest": "e" * 64,
        **{f"approved_{name}": getattr(decision, name) or "0" * 64 for name in COMMITMENTS},
    }
    arguments.update(overrides)
    return EdgePaperAdmissionGovernance(**arguments)  # type: ignore[arg-type]


def passing_chain() -> EdgeWalkForwardOosEvidence:
    """World P's governed EF-6 PASS: the chain whose pre-paper validation passes."""

    return pret.ef6_p()


@functools.cache
def draft() -> EdgePaperAdmissionDecision:
    """The ungoverned decision over the authentic PASS chain (the record a human reviews before approving)."""

    return decide(passing_chain())


@functools.cache
def admitted() -> EdgePaperAdmissionDecision:
    return decide(passing_chain(), governance=approval_for(draft()))


@functools.cache
def cheap_draft() -> EdgePaperAdmissionDecision:
    return decide(ef6t.cheap())


@functools.cache
def cheap_approved() -> EdgePaperAdmissionDecision:
    """Governed decision over the cheap authentic chain: READY + FAIL with ONLY the propagated predecessor reason."""

    return decide(ef6t.cheap(), governance=approval_for(cheap_draft()))


@functools.cache
def ef6_needs_governance() -> EdgeWalkForwardOosEvidence:
    return ef6t._draft("A", ("A1",), "main")


@functools.cache
def ef6_rejected() -> EdgeWalkForwardOosEvidence:
    return ef6t.ef6("A", (), governance=None, correlation_id="corr-2")


@functools.cache
def ef6_two_registered() -> EdgeWalkForwardOosEvidence:
    """Sealed ledger AB with no bundle: two registered digests, authentic READY + FAIL, cheap."""

    return ef6t.ef6("AB", (), governance=None)


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(decision: EdgePaperAdmissionDecision, **changes: object) -> EdgePaperAdmissionDecision:
    changed = replace(decision, **changes)
    return replace(changed, paper_admission_decision_digest=edge_paper_admission_decision_digest(changed))


def _reseal_ef6(evidence: EdgeWalkForwardOosEvidence, **changes: object) -> EdgeWalkForwardOosEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, walk_forward_oos_evidence_digest=edge_walk_forward_oos_evidence_digest(changed))


def _payload(decision: EdgePaperAdmissionDecision) -> dict:
    return json.loads(edge_canonical_json(edge_paper_admission_decision_to_dict(decision)))


def _assert_not_intact(decision: object, *codes: str) -> EdgeEvidenceVerification:
    verification = verify_edge_paper_admission_decision(decision)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes
    assert {_code(code) for code in codes} <= set(verification.reason_codes), verification.reason_codes
    return verification


def _assert_shape(decision: EdgePaperAdmissionDecision) -> None:
    """Invariants every builder state satisfies (no re-proof)."""

    assert decision.paper_admission_decision_digest == edge_paper_admission_decision_digest(decision)
    ready = decision.status is EdgeEvidenceStatus.READY
    assert decision.advances is (ready and decision.gate_verdict is EdgeGateVerdict.PASS)
    assert decision.candidate_admitted_to_paper is decision.advances
    assert decision.kill_criteria_sealed is decision.advances
    assert {name: getattr(decision, name) for name, _ in EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS} == dict(
        EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS
    )
    assert decision.portfolio_risk_envelope_status == EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING
    assert decision.capacity_evidence_status == EDGE_CAPACITY_EVIDENCE_STATUS
    assert decision.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert decision.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert decision.rule_set_digest == EDGE_PAPER_ADMISSION_RULE_SET_DIGEST
    assert decision.admitted_variant_count == len(decision.admitted_variants)
    assert decision.predecessor_digest == decision.predecessor_binding.expected_digest
    assert decision.risk_budget_policy_digest == decision.risk_budget_policy_binding.expected_digest
    if decision.advances:
        assert decision.kill_criteria_lifecycle_stage == "SEALED"
        assert decision.sealed_kill_criteria_digest == decision.kill_criteria_record_digest != ""
        assert decision.admitted_variants
    else:
        assert decision.kill_criteria_lifecycle_stage != "SEALED"
        assert decision.sealed_kill_criteria_digest == ""
    if ready:
        assert decision.integrity_reason_codes == ()
        assert decision.preregistration_sealed is True
        assert decision.kill_criteria_record_digest and decision.admission_subject_digest
    else:
        assert decision.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert decision.integrity_reason_codes and decision.verdict_reason_codes == ()
        assert (decision.preregistration_sealed, decision.performance_data_consumed) == (False, False)
        assert decision.oos_evidence_consumed is False


def _assert_receipt_invariants(decision: EdgePaperAdmissionDecision) -> None:
    _assert_shape(decision)
    verification = verify_edge_paper_admission_decision(decision)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == decision.paper_admission_decision_digest
    assert edge_paper_admission_decision_payload_is_well_formed(json.loads(verification.canonical_json)) is True


def _expected_kill_criteria_record() -> dict[str, object]:
    """The seal record recomputed independently from the authentic EF-2 root and EF-4 admission of world A."""

    intake, _, admission, _, _ = ef6t.world()
    return {
        "root_intake_digest": intake.intake_digest,
        "strategy_spec_admission_digest": admission.admission_digest,
        "strategy_spec_digest": admission.strategy_spec_digest,
        "root_kill_criteria_digest": intake.kill_criteria_digest,
        "kill_criteria": [edge_kill_criterion_to_dict(item) for item in admission.admitted_kill_criteria],
        "kill_criteria_digest": admission.admitted_kill_criteria_digest,
        "added_kill_criterion_ids": list(admission.added_kill_criterion_ids),
        "combination_policy": "any_single_criterion_triggers_kill.v1",
        "kill_criteria_policy_digest": admission.kill_criteria_policy_binding.expected_digest,  # type: ignore[union-attr]
    }


def _expected_subject(predecessor: EdgeWalkForwardOosEvidence, sleeve: str = SLEEVE) -> dict[str, object]:
    ef5 = pret._ef5_of(predecessor)
    evidence = pret.evidence_for(predecessor)
    ids = {item.parameter_assignment_digest: item.variant_id for item in ef5.registered_variants}
    return {
        "root_intake_digest": ef6t.world()[0].intake_digest,
        "candidate_strategy_id": ef5.candidate_strategy_id,
        "edge_family": ef5.edge_family,
        "strategy_id": ef5.strategy_id,
        "strategy_version": ef5.strategy_version,
        "strategy_spec_digest": ef5.strategy_spec_digest,
        "executable_binding_digest": ef5.executable_binding_digest,
        "profile_semantics_digest": ef5.profile_semantics_digest,
        "market_type": predecessor.market_type,
        "pinned_instrument_universe": list(ef5.pinned_instrument_universe),
        "variant_ledger_digest": ef5.variant_ledger_digest,
        "multiple_testing_count": ef5.multiple_testing_count,
        "admitted_variants": [
            {"variant_id": ids[digest], "parameter_assignment_digest": digest}
            for digest in predecessor.surviving_assignment_digests
            if digest in evidence.admitted_assignment_digests
        ],
        "paper_sleeve_id": sleeve,
        "pre_paper_evidence_digest": evidence.pre_paper_validation_evidence_digest,
        "admission_cap_fraction": evidence.admission_cap_fraction or "",
        "admission_scope": "LIMITED_S1_PAPER_V1",
    }


# The cheap chain's EF-6 FAIL propagates through EF-7 and through its own pre-paper evidence.
CHEAP_FAILS = ("pre_paper_evidence_not_advanced:FAIL", "predecessor_not_advanced:FAIL")


def _cheap_codes(*codes: str) -> tuple[str, ...]:
    return tuple(sorted(_code(code) for code in (*CHEAP_FAILS, *codes)))


def _digest(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


# --- A. happy path and negative gate outcomes ----------------------------------------------------------------------------


def test_governed_passing_chain_is_admitted_and_seals_the_exact_final_kill_criteria() -> None:
    decision = admitted()
    predecessor = passing_chain()
    evidence = pret.passed()
    intake, manifest, admission, _, binding = ef6t.world()
    ef5 = pret.ef5_p()
    _assert_receipt_invariants(decision)
    assert (decision.status, decision.gate_verdict, decision.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (decision.integrity_reason_codes, decision.verdict_reason_codes) == ((), ())
    assert (decision.candidate_admitted_to_paper, decision.kill_criteria_sealed) == (True, True)
    assert (decision.preregistration_sealed, decision.performance_data_consumed, decision.oos_evidence_consumed) == (
        True,
        True,
        True,
    )
    # The dual anchor and every chain identity come from authenticated authority.
    assert decision.predecessor_digest == predecessor.walk_forward_oos_evidence_digest
    assert (decision.predecessor_gate_id, decision.predecessor_gate_verdict) == ("EF-6", "PASS")
    assert decision.root_intake_digest == intake.intake_digest
    assert decision.preregistration_digest == ef5.leakage_bias_evidence_digest == predecessor.predecessor_digest
    assert decision.strategy_spec_admission_digest == admission.admission_digest
    assert decision.source_manifest_digest == manifest.source_packet_evidence_digest
    assert decision.strategy_spec_digest == admission.strategy_spec_digest == ef5.strategy_spec_digest
    assert decision.executable_binding_digest == binding.binding_digest
    assert decision.pinned_instrument_universe == (INS,)
    assert (decision.multiple_testing_count, decision.registered_variant_count) == (9, 9)
    assert decision.evaluation_frame_digest == predecessor.evaluation_frame_digest
    assert decision.oos_governance_digest == predecessor.governance_digest
    # The pre-paper evidence is re-proven and carried exactly: LIMITED_S1_PAPER_V1, cap 1/4, regime PBO unproven.
    assert decision.pre_paper_evidence_digest == evidence.pre_paper_validation_evidence_digest
    assert (decision.pre_paper_evidence_gate_verdict, decision.pre_paper_validation_passed) == ("PASS", True)
    assert (decision.pre_paper_policy_digest, decision.trial_chain_digest) == (
        evidence.policy_digest,
        evidence.trial_chain_digest,
    )
    assert (decision.pbo, decision.pbo_band) == ("0.000000000000000000", "NORMAL")
    assert decision.admission_cap_fraction == "0.250000000000000000" == evidence.admission_cap_fraction
    assert (decision.admission_scope, decision.regime_conditional_pbo_status) == ("LIMITED_S1_PAPER_V1", "UNPROVEN")
    assert (decision.pbo_passed, decision.stress_passed) == (False, False)
    # Exactly the EF-6 survivors that passed every pre-paper gate, mapped through the EF-5 ledger; no selection.
    assert decision.admitted_variants == (
        EdgeAdmittedVariant(pret.BASE_VARIANT, evidence.admitted_assignment_digests[0]),
    )
    assert decision.admission_subject_digest == _digest(_expected_subject(predecessor))
    # The seal is exactly the authentic EF-4 admitted criteria with their lineage.
    assert decision.final_kill_criteria == admission.admitted_kill_criteria
    assert decision.final_kill_criteria_digest == admission.admitted_kill_criteria_digest
    assert decision.final_kill_criteria_digest == edge_kill_criteria_digest(admission.admitted_kill_criteria)
    assert decision.root_kill_criteria_digest == intake.kill_criteria_digest
    assert decision.kill_criteria_record_digest == _digest(_expected_kill_criteria_record())
    assert decision.sealed_kill_criteria_digest == decision.kill_criteria_record_digest
    assert decision.kill_criteria_lifecycle_stage == "SEALED"
    # Linkage is identity only.
    assert (decision.risk_budget_policy_id, decision.risk_budget_policy_digest) == (
        "paper-budget-1",
        budget_policy().policy_digest,
    )
    assert decision.capacity_assumptions == (CAPACITY,)
    assert decision.governance == approval_for(draft())


def test_missing_governance_on_a_passing_chain_needs_approval_and_seals_nothing() -> None:
    decision = draft()
    _assert_shape(decision)
    assert (decision.status, decision.gate_verdict) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
    )
    assert decision.verdict_reason_codes == (_code("admission_governance_missing"),)
    assert (decision.advances, decision.candidate_admitted_to_paper, decision.kill_criteria_sealed) == (
        False,
        False,
        False,
    )
    assert decision.sealed_kill_criteria_digest == ""
    assert decision.kill_criteria_lifecycle_stage == "SUPERSET_STRENGTHENED_UNSEALED"
    # Everything a reviewer approves is already committed and identical to the admitted decision.
    for name in COMMITMENTS:
        assert getattr(decision, name) == getattr(admitted(), name)
    assert decision.governance is None and decision.governance_digest == ""


def test_changed_capacity_after_approval_cannot_authorize_the_admission() -> None:
    changed = replace(CAPACITY, max_value="500000.000000000000000000")
    decision = decide(passing_chain(), capacity_assumptions=(changed,), governance=approval_for(draft()))
    _assert_shape(decision)
    assert decision.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert decision.verdict_reason_codes == (_code("admission_governance_capacity_assumption_set_digest_mismatch"),)
    assert decision.kill_criteria_sealed is False


def test_predecessor_fail_is_valid_negative_evidence_that_is_never_admitted() -> None:
    decision = cheap_approved()
    _assert_receipt_invariants(decision)
    assert (decision.status, decision.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    assert decision.verdict_reason_codes == _cheap_codes()
    assert decision.predecessor_gate_verdict == "FAIL"
    assert (decision.pre_paper_evidence_gate_verdict, decision.admission_cap_fraction) == ("FAIL", "")
    assert (decision.admitted_variants, decision.admitted_variant_count) == ((), 0)
    assert (decision.performance_data_consumed, decision.oos_evidence_consumed) == (False, False)
    assert decision.kill_criteria_record_digest == admitted().kill_criteria_record_digest
    assert decision.admission_subject_digest == _digest(_expected_subject(ef6t.cheap()))


def test_predecessor_needing_governance_propagates_and_is_never_admitted() -> None:
    predecessor = ef6_needs_governance()
    assert predecessor.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    decision = decide(predecessor)
    _assert_receipt_invariants(decision)
    assert decision.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert decision.verdict_reason_codes == (
        _code("admission_governance_missing"),
        _code("pre_paper_evidence_not_advanced:NEEDS_GOVERNANCE_APPROVAL"),
        _code("predecessor_not_advanced:NEEDS_GOVERNANCE_APPROVAL"),
    )
    assert (decision.candidate_admitted_to_paper, decision.kill_criteria_sealed, decision.admitted_variants) == (
        False,
        False,
        (),
    )


@SLOW
def test_predecessor_needing_external_facts_propagates_and_is_never_admitted() -> None:
    predecessor = ef6t.ef6("A", ("Asyn1",))
    assert predecessor.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    first = decide(predecessor)
    decision = decide(predecessor, governance=approval_for(first))
    _assert_receipt_invariants(decision)
    assert decision.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert decision.verdict_reason_codes == (
        _code("pre_paper_evidence_not_advanced:NEEDS_EXTERNAL_FACTS"),
        _code("predecessor_not_advanced:NEEDS_EXTERNAL_FACTS"),
    )
    assert decision.candidate_admitted_to_paper is False


def test_rejected_predecessor_is_rejected() -> None:
    decision = decide(ef6_rejected(), correlation_id="corr-2")
    _assert_receipt_invariants(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert decision.integrity_reason_codes == (_code("predecessor_rejected"),)
    assert decision.kill_criteria_record_digest == decision.admission_subject_digest == ""
    assert decision.final_kill_criteria == () and decision.kill_criteria_lifecycle_stage == ""


def test_every_survivor_passing_every_pre_paper_gate_is_admitted_in_ef6_order_without_selection() -> None:
    """The admitted set is the EF-6 canonical order of the evidence's admitted assignments, whatever their order."""

    survivors = passing_chain().surviving_assignment_digests
    chain = SimpleNamespace(ef5=pret.ef5_p(), ef6=passing_chain())
    ids = {item.parameter_assignment_digest: item.variant_id for item in pret.ef5_p().registered_variants}
    for chosen in (survivors[:1], survivors[2:5], tuple(reversed(survivors))):
        result = ef7_module._admitted_variants(chain, SimpleNamespace(admitted_assignment_digests=chosen))
        expected = tuple(EdgeAdmittedVariant(ids[digest], digest) for digest in survivors if digest in set(chosen))
        assert result == expected


# --- B2. the pre-paper validation precondition --------------------------------------------------------------------------


def _v1_payload(decision: EdgePaperAdmissionDecision) -> dict:
    """A payload in the historical v1 shape: the v1 schema id and none of the v2 pre-paper fields."""

    payload = _payload(decision)
    for name in (
        "pre_paper_evidence_binding",
        "pre_paper_evidence_digest",
        "pre_paper_evidence_gate_verdict",
        "pre_paper_policy_digest",
        "trial_chain_digest",
        "pbo",
        "pbo_band",
        "admission_scope",
        "regime_conditional_pbo_status",
        "admission_cap_fraction",
        "pre_paper_validation_passed",
    ):
        del payload[name]
    del payload["governance"]["approved_pre_paper_evidence_digest"]
    payload["schema_version"] = EDGE_PAPER_ADMISSION_HISTORICAL_SCHEMA_V1
    return payload


def test_a_historical_v1_decision_is_refused_and_never_becomes_v2_authority() -> None:
    payload = _v1_payload(cheap_approved())
    with pytest.raises(EdgePaperAdmissionDecisionError, match="schema_superseded_v1_historical_only"):
        edge_paper_admission_decision_from_payload(payload)
    assert edge_paper_admission_decision_payload_is_well_formed(payload) is False
    relabelled = _payload(cheap_approved())
    relabelled["schema_version"] = EDGE_PAPER_ADMISSION_HISTORICAL_SCHEMA_V1
    assert edge_paper_admission_decision_payload_is_well_formed(relabelled) is False
    _assert_not_intact(_reseal(cheap_approved(), schema_version=EDGE_PAPER_ADMISSION_HISTORICAL_SCHEMA_V1))
    assert cheap_approved().schema_version == "edge-paper-admission-decision.v2"


def test_pre_paper_evidence_needing_governance_propagates_and_admits_nothing() -> None:
    decision = decide(passing_chain(), pre_paper_evidence=pret.draft(), governance=approval_for(draft()))
    _assert_shape(decision)
    assert decision.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert _code("pre_paper_evidence_not_advanced:NEEDS_GOVERNANCE_APPROVAL") in decision.verdict_reason_codes
    assert (decision.admitted_variants, decision.admission_cap_fraction, decision.candidate_admitted_to_paper) == (
        (),
        "",
        False,
    )


@functools.cache
def _failing_evidence():
    record = pret.genesis(10**15)
    chain = pret.chain_for((pret.ef5_p(),), record)
    return pret.build(
        passing_chain(), chain=chain, policy=pret.policy(approved_trial_chain_genesis_digest=record.genesis_digest)
    )


def test_a_failing_pre_paper_evidence_propagates_fail_and_is_never_admitted() -> None:
    evidence = _failing_evidence()
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    decision = decide(passing_chain(), pre_paper_evidence=evidence)
    _assert_receipt_invariants(decision)
    assert decision.gate_verdict is EdgeGateVerdict.FAIL
    assert decision.verdict_reason_codes == (
        _code("admission_governance_missing"),
        _code("pre_paper_evidence_not_advanced:FAIL"),
    )
    assert decision.kill_criteria_sealed is False and decision.pre_paper_validation_passed is False


def test_a_foreign_or_tampered_pre_paper_evidence_is_rejected() -> None:
    foreign = decide(passing_chain(), pre_paper_evidence=pret.evidence_for(ef6t.cheap()))
    _assert_shape(foreign)
    assert foreign.status is EdgeEvidenceStatus.REJECTED
    assert any(
        code.startswith(_code("pre_paper_evidence_integrity_failure:")) for code in foreign.integrity_reason_codes
    )
    evidence = pret.passed()
    changed = replace(evidence, admission_cap_fraction="0.500000000000000000")
    forged = replace(changed, pre_paper_validation_evidence_digest=edge_pre_paper_validation_evidence_digest(changed))
    tampered = decide(passing_chain(), pre_paper_evidence=forged)
    assert tampered.status is EdgeEvidenceStatus.REJECTED
    assert any(
        code.startswith(_code("pre_paper_evidence_integrity_failure:")) for code in tampered.integrity_reason_codes
    )
    mismatch = decide(passing_chain(), pre_paper_evidence=evidence, expected_pre_paper_evidence_digest="0" * 64)
    assert mismatch.integrity_reason_codes == (_code("pre_paper_evidence_digest_mismatch"),)


def test_a_missing_or_malformed_pre_paper_evidence_is_a_construction_error() -> None:
    arguments = arguments_for(ef6t.cheap())
    for value, code in (
        (None, "pre_paper_evidence_malformed"),
        (ef6t.cheap(), "pre_paper_evidence_malformed"),
        (object.__new__(type(pret.passed())), "pre_paper_evidence_not_serializable"),
    ):
        with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
            build_edge_paper_admission_decision(ef6t.cheap(), **{**arguments, "pre_paper_evidence": value})  # type: ignore[arg-type]
    with pytest.raises(EdgePaperAdmissionDecisionError, match="pre_paper_evidence_expected_digest_invalid"):
        build_edge_paper_admission_decision(
            ef6t.cheap(),
            **{**arguments, "expected_pre_paper_evidence_digest": "x"},  # type: ignore[arg-type]
        )


# --- B. EF-6 authority and the back-chain --------------------------------------------------------------------------------


def test_wrong_expected_predecessor_digest_is_rejected() -> None:
    decision = decide(ef6t.cheap(), expected_predecessor_digest="0" * 64)
    _assert_receipt_invariants(decision)
    assert decision.integrity_reason_codes == (_code("predecessor_digest_mismatch"),)


def test_tampered_predecessor_is_rejected() -> None:
    tampered = replace(ef6t.cheap(), evidence_id="ef6-tampered")
    decision = decide(tampered)
    _assert_shape(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert (
        _code("predecessor_integrity_failure:edge_walk_forward_oos_evidence:self_digest_mismatch")
        in decision.integrity_reason_codes
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"gate_verdict": EdgeGateVerdict.PASS, "advances": True},
        {"surviving_assignment_digests": ("f" * 64,), "surviving_variant_count": 1},
        {"performance_data_consumed": True, "oos_evidence_consumed": True},
        {"root_intake_digest": "f" * 64},
    ],
)
def test_tampered_and_resealed_predecessor_is_rejected(changes: dict[str, object]) -> None:
    forged = _reseal_ef6(ef6t.cheap(), **changes)
    decision = decide(forged, expected_root_intake_digest=forged.root_intake_digest)
    _assert_shape(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("predecessor_integrity_failure:")) for code in decision.integrity_reason_codes)
    assert decision.candidate_admitted_to_paper is False


def test_reversed_registered_set_in_a_resealed_predecessor_is_rejected() -> None:
    genuine = ef6_two_registered()
    assert len(genuine.registered_parameter_assignment_digests) == 2
    forged = _reseal_ef6(
        genuine,
        registered_parameter_assignment_digests=tuple(reversed(genuine.registered_parameter_assignment_digests)),
    )
    decision = decide(forged)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("predecessor_integrity_failure:")) for code in decision.integrity_reason_codes)
    assert decide(genuine).status is EdgeEvidenceStatus.READY


@pytest.mark.parametrize(
    ("predecessor", "code"),
    [
        (lambda: object.__new__(EdgeWalkForwardOosEvidence), "predecessor_not_serializable"),
        (lambda: ef6t.ef5("A"), "predecessor_malformed"),
        (lambda: None, "predecessor_malformed"),
        (lambda: edge_walk_forward_oos_evidence_to_dict(ef6t.cheap()), "predecessor_malformed"),
    ],
)
def test_malformed_or_hollow_predecessor_is_a_construction_error(predecessor, code: str) -> None:
    value = predecessor()
    arguments = arguments_for(ef6t.cheap())
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        build_edge_paper_admission_decision(value, **arguments)  # type: ignore[arg-type]


def test_root_anchor_splice_is_rejected() -> None:
    decision = decide(ef6t.cheap(), expected_root_intake_digest="f" * 64)
    _assert_receipt_invariants(decision)
    assert decision.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)


def test_correlation_splice_is_rejected() -> None:
    decision = decide(ef6t.cheap(), correlation_id="corr-2")
    _assert_receipt_invariants(decision)
    assert decision.integrity_reason_codes == (_code("predecessor_correlation_mismatch"),)


def test_strategy_splice_cannot_reuse_an_approval_granted_to_another_spec() -> None:
    other = ef6t.ef6("A", (), world_name="spec", governance=ef6t.governance_for(ef6t._draft("A", (), "spec")))
    assert other.root_intake_digest == ef6t.cheap().root_intake_digest
    assert other.strategy_spec_digest != ef6t.cheap().strategy_spec_digest
    decision = decide(other, governance=approval_for(cheap_draft()))
    _assert_shape(decision)
    assert decision.status is EdgeEvidenceStatus.READY
    mismatched = {
        _code(f"admission_governance_{name}_mismatch")
        for name in ("predecessor_digest", "admission_subject_digest", "kill_criteria_record_digest")
    }
    assert mismatched <= set(decision.verdict_reason_codes)
    assert _code("admission_governance_risk_budget_policy_digest_mismatch") not in decision.verdict_reason_codes
    assert decision.kill_criteria_sealed is False


def _kill_criteria_entries(ef4: dict) -> list[dict]:
    return ef4["admitted_kill_criteria"]


def _redigest_criteria(ef4: dict) -> None:
    ef4["admitted_kill_criteria_digest"] = _digest(ef4["admitted_kill_criteria"])


def _remove_criterion(ef4: dict) -> None:
    del _kill_criteria_entries(ef4)[0]
    _redigest_criteria(ef4)


def _weaken_threshold(ef4: dict) -> None:
    (entry,) = [item for item in _kill_criteria_entries(ef4) if item["criterion_id"] == "max_drawdown_breach"]
    entry["threshold"] = "0.500000000000000000"
    _redigest_criteria(ef4)


def _change_comparator(ef4: dict) -> None:
    _kill_criteria_entries(ef4)[0]["comparator"] = "kill_if_below"
    _redigest_criteria(ef4)


def _add_post_performance_criterion(ef4: dict) -> None:
    _kill_criteria_entries(ef4).append(
        {
            "criterion_id": "zz_post_oos_criterion",
            "metric_id": "max_drawdown",
            "comparator": "kill_if_above",
            "threshold": "0.900000000000000000",
            "evaluation_basis": "rolling_30_utc_days",
        }
    )
    _redigest_criteria(ef4)


def _change_combination_policy(ef4: dict) -> None:
    ef4["kill_criteria_combination_policy"] = "all_criteria_must_trigger_kill.v1"


def _forge_criteria_digest(ef4: dict) -> None:
    ef4["admitted_kill_criteria_digest"] = "0" * 64


def _forge_policy_binding(ef4: dict) -> None:
    """An authentic policy approving a weakened (one-criterion) set, re-bound into EF-4 with the weakened criteria."""

    _remove_criterion(ef4)
    weakened = tuple(
        EdgeKillCriterion(
            entry["criterion_id"],
            entry["metric_id"],
            EdgeKillCriterionComparator(entry["comparator"]),
            entry["threshold"],
            entry["evaluation_basis"],
        )
        for entry in _kill_criteria_entries(ef4)
    )
    policy = build_edge_kill_criteria_policy(
        policy_id="kp-forged",
        correlation_id="corr-1",
        kill_criteria=weakened,
        thresholds_approved=True,
        approval_reference="gov-forged",
        approval_digest="d" * 64,
    )
    ef4["kill_criteria_policy_binding"] = {
        "expected_digest": policy.policy_digest,
        "snapshot": edge_kill_criteria_policy_to_dict(policy),
    }


def _forged_chain(mutate) -> EdgeWalkForwardOosEvidence:
    """Mutate the EF-4 nested in the cheap EF-6 and re-seal every link's digest (without re-running any governance)."""

    ef6 = json.loads(edge_canonical_json(edge_walk_forward_oos_evidence_to_dict(ef6t.cheap())))
    ef5 = ef6["predecessor_binding"]["snapshot"]
    ef4 = ef5["predecessor_binding"]["snapshot"]
    mutate(ef4)
    ef4["admission_digest"] = edge_payload_digest(ef4, "admission_digest")
    ef5["predecessor_binding"]["expected_digest"] = ef5["predecessor_digest"] = ef4["admission_digest"]
    ef5["leakage_bias_evidence_digest"] = edge_payload_digest(ef5, "leakage_bias_evidence_digest")
    ef6["predecessor_binding"]["expected_digest"] = ef6["predecessor_digest"] = ef5["leakage_bias_evidence_digest"]
    ef6["admission_digest"] = ef4["admission_digest"]
    ef6["walk_forward_oos_evidence_digest"] = edge_payload_digest(ef6, "walk_forward_oos_evidence_digest")
    return edge_walk_forward_oos_evidence_from_payload(ef6)


@pytest.mark.parametrize(
    "mutate",
    [
        _remove_criterion,
        _weaken_threshold,
        _change_comparator,
        _add_post_performance_criterion,
        _change_combination_policy,
        _forge_criteria_digest,
        _forge_policy_binding,
    ],
)
def test_nested_ef4_kill_criteria_tamper_resealed_through_the_chain_is_rejected(mutate) -> None:
    forged = _forged_chain(mutate)
    decision = decide(forged)
    _assert_shape(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("predecessor_integrity_failure:")) for code in decision.integrity_reason_codes)
    assert (decision.final_kill_criteria, decision.kill_criteria_sealed) == ((), False)


def test_public_ef6_verifier_agrees_with_the_memo() -> None:
    memo = _EF7_MEMOS["verify_edge_walk_forward_oos_evidence"]
    assert memo.real(ef6t.cheap()) == memo(ef6t.cheap())
    assert ef7_module.verify_edge_walk_forward_oos_evidence is memo
    assert memo.real is verify_edge_walk_forward_oos_evidence


# --- C. the kill-criteria seal -------------------------------------------------------------------------------------------


def test_builder_accepts_no_kill_criteria_variant_choice_ranking_or_flag_input() -> None:
    parameters = inspect.signature(build_edge_paper_admission_decision).parameters
    assert set(parameters) == {
        "predecessor",
        "expected_predecessor_digest",
        "pre_paper_evidence",
        "expected_pre_paper_evidence_digest",
        "expected_root_intake_digest",
        "risk_budget_policy",
        "expected_risk_budget_policy_digest",
        "paper_sleeve_id",
        "capacity_assumptions",
        "decision_id",
        "correlation_id",
        "governance",
    }
    assert parameters["governance"].default is None
    assert all(
        parameter.default is inspect.Parameter.empty for name, parameter in parameters.items() if name != "governance"
    )


def test_the_seal_record_commits_exactly_the_authentic_final_criteria_and_their_lineage() -> None:
    decision = cheap_approved()
    _, _, admission, _, _ = ef6t.world()
    assert decision.final_kill_criteria == admission.admitted_kill_criteria == ef6t.ef5t.support.CRITERIA[::-1]
    assert decision.kill_criteria_record_digest == _digest(_expected_kill_criteria_record())
    assert decision.added_kill_criterion_ids == admission.added_kill_criterion_ids
    assert decision.kill_criteria_combination_policy == "any_single_criterion_triggers_kill.v1"
    assert decision.kill_criteria_lifecycle_stage == "SUPERSET_STRENGTHENED_UNSEALED"
    assert decision.sealed_kill_criteria_digest == "" and decision.kill_criteria_sealed is False


def _weakened(criteria: tuple[EdgeKillCriterion, ...]) -> tuple[EdgeKillCriterion, ...]:
    return tuple(replace(item, threshold="0.990000000000000000") for item in criteria)


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: {"final_kill_criteria": d.final_kill_criteria[1:]},
        lambda d: {"final_kill_criteria": _weakened(d.final_kill_criteria)},
        lambda d: {
            "final_kill_criteria": (
                replace(d.final_kill_criteria[0], comparator=EdgeKillCriterionComparator.KILL_IF_BELOW),
                *d.final_kill_criteria[1:],
            )
        },
        lambda d: {
            "final_kill_criteria": (*d.final_kill_criteria, replace(d.final_kill_criteria[0], criterion_id="zz_new"))
        },
        lambda d: {"final_kill_criteria_digest": "0" * 64},
        lambda d: {"kill_criteria_combination_policy": "all_criteria_must_trigger_kill.v1"},
        lambda d: {"kill_criteria_record_digest": "0" * 64},
        lambda d: {"sealed_kill_criteria_digest": d.kill_criteria_record_digest},
        lambda d: {"kill_criteria_lifecycle_stage": "SEALED"},
        lambda d: {"kill_criteria_sealed": True},
        lambda d: {"added_kill_criterion_ids": ("zz_new",)},
        lambda d: {"kill_criteria_policy_digest": "0" * 64},
    ],
)
def test_resealed_kill_criteria_fields_never_verify(tamper) -> None:
    decision = cheap_approved()
    _assert_not_intact(_reseal(decision, **tamper(decision)))


@pytest.mark.parametrize("attack", ["reorder", "duplicate", "missing_key", "bool_threshold"])
def test_noncanonical_kill_criteria_payloads_are_refused_by_the_strict_parser(attack: str) -> None:
    payload = _payload(cheap_approved())
    criteria = payload["final_kill_criteria"]
    if attack == "reorder":
        criteria.reverse()
    elif attack == "duplicate":
        criteria.append(dict(criteria[0]))
    elif attack == "missing_key":
        del criteria[0]["evaluation_basis"]
    else:
        criteria[0]["threshold"] = True
    assert edge_paper_admission_decision_payload_is_well_formed(payload) is False


def test_every_non_pass_outcome_keeps_the_kill_criteria_unsealed() -> None:
    for decision in (
        draft(),
        cheap_draft(),
        cheap_approved(),
        decide(ef6t.cheap(), correlation_id="corr-2"),
        decide(ef6t.cheap(), capacity_assumptions=()),
    ):
        _assert_shape(decision)
        assert decision.gate_verdict is not EdgeGateVerdict.PASS
        assert (decision.kill_criteria_sealed, decision.sealed_kill_criteria_digest) == (False, "")
        assert decision.candidate_admitted_to_paper is False


# --- D. governance -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("name", COMMITMENTS)
def test_each_approval_commitment_must_match_exactly(name: str) -> None:
    decision = decide(ef6t.cheap(), governance=approval_for(cheap_draft(), **{f"approved_{name}": "a" * 64}))
    _assert_shape(decision)
    assert decision.verdict_reason_codes == _cheap_codes(f"admission_governance_{name}_mismatch")


def test_approval_of_weakened_kill_criteria_cannot_authorize_the_authentic_seal() -> None:
    weakened_record = {**_expected_kill_criteria_record()}
    weakened_record["kill_criteria"] = weakened_record["kill_criteria"][1:]  # type: ignore[index]
    approval = approval_for(cheap_draft(), approved_kill_criteria_record_digest=_digest(weakened_record))
    decision = decide(ef6t.cheap(), governance=approval)
    assert _code("admission_governance_kill_criteria_record_digest_mismatch") in decision.verdict_reason_codes
    assert decision.kill_criteria_sealed is False


def test_old_approval_cannot_authorize_a_changed_rule_set(monkeypatch: pytest.MonkeyPatch) -> None:
    approval = approval_for(cheap_draft())
    monkeypatch.setattr(ef7_module, "EDGE_PAPER_ADMISSION_RULE_SET_DIGEST", _digest({"rule_set_id": "rules.v3"}))
    decision = decide(ef6t.cheap(), governance=approval)
    assert _code("admission_governance_rule_set_digest_mismatch") in decision.verdict_reason_codes


def test_approval_with_every_commitment_changed_needs_approval_for_each() -> None:
    approval = approval_for(cheap_draft(), **{f"approved_{name}": "b" * 64 for name in COMMITMENTS})
    decision = decide(ef6t.cheap(), governance=approval)
    assert {_code(f"admission_governance_{name}_mismatch") for name in COMMITMENTS} <= set(
        decision.verdict_reason_codes
    )


def test_governance_digest_commits_the_exact_approval_record() -> None:
    decision = cheap_approved()
    assert decision.governance_digest == _digest(
        {field.name: getattr(decision.governance, field.name) for field in fields(EdgePaperAdmissionGovernance)}
    )
    other = decide(ef6t.cheap(), governance=approval_for(cheap_draft(), approval_reference="governance-ef7-2"))
    assert other.governance_digest != decision.governance_digest
    assert other.verdict_reason_codes == decision.verdict_reason_codes


@pytest.mark.parametrize(
    ("governance", "code"),
    [
        (lambda: object(), "governance_malformed"),
        (lambda: approval_for(cheap_draft(), approval_digest="E" * 64), "governance_approval_digest_invalid"),
        (lambda: approval_for(cheap_draft(), approval_reference=""), "governance_approval_reference_invalid"),
        (lambda: approval_for(cheap_draft(), approval_reference="live approval"), "forbidden_scope_token"),
        (
            lambda: approval_for(cheap_draft(), approved_rule_set_digest=True),
            "governance_approved_rule_set_digest_invalid",
        ),
        (
            lambda: approval_for(cheap_draft(), approved_capacity_assumption_set_digest=None),
            "governance_approved_capacity_assumption_set_digest_invalid",
        ),
    ],
)
def test_malformed_governance_is_a_construction_error(governance, code: str) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), governance=governance())


# --- E. capacity assumptions ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ("0.000000000000000000", "capacity_assumption_max_value_not_positive"),
        ("-1.000000000000000000", "capacity_assumption_max_value_not_positive"),
        ("-0.000000000000000000", "capacity_assumption_max_value_invalid"),
        (1.5, "capacity_assumption_max_value_invalid"),
        (True, "capacity_assumption_max_value_invalid"),
        (250000, "capacity_assumption_max_value_invalid"),
        (None, "capacity_assumption_max_value_invalid"),
        ("NaN", "capacity_assumption_max_value_invalid"),
        ("Infinity", "capacity_assumption_max_value_invalid"),
        ("inf", "capacity_assumption_max_value_invalid"),
        ("1e5", "capacity_assumption_max_value_invalid"),
        ("1.000000000000000000e5", "capacity_assumption_max_value_invalid"),
        (" 1.000000000000000000", "capacity_assumption_max_value_invalid"),
        ("1.000000000000000000 ", "capacity_assumption_max_value_invalid"),
        ("1_000.000000000000000000", "capacity_assumption_max_value_invalid"),
        ("1.00", "capacity_assumption_max_value_invalid"),
        ("1", "capacity_assumption_max_value_invalid"),
        ("01.000000000000000000", "capacity_assumption_max_value_invalid"),
        ("+1.000000000000000000", "capacity_assumption_max_value_invalid"),
        ("١.000000000000000000", "capacity_assumption_max_value_invalid"),
        ("1" * 42 + "." + "0" * 18, "capacity_assumption_max_value_invalid"),
        ("unlimited", "capacity_assumption_max_value_invalid"),
    ],
)
def test_capacity_value_must_be_a_strictly_positive_canonical_finite_bound(value: object, code: str) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, max_value=value),))


def test_capacity_value_length_bound_is_the_committed_rule() -> None:
    rules = edge_paper_admission_rule_set()
    assert (rules["capacity_value_scale"], rules["capacity_value_max_text_length"]) == (18, 60)
    longest = "9" * 41 + "." + "0" * 18
    assert len(longest) == 60
    decision = decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, max_value=longest),))
    assert decision.capacity_assumptions[0].max_value == longest
    smallest = "0.000000000000000001"
    assert decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, max_value=smallest),)).status is (
        EdgeEvidenceStatus.READY
    )


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"unit_id": ""}, "capacity_assumption_unit_id_invalid"),
        ({"scope_id": None}, "capacity_assumption_scope_id_invalid"),
        ({"basis_id": "Governance"}, "capacity_assumption_basis_id_invalid"),
        ({"capacity_measure_id": "max notional"}, "capacity_assumption_capacity_measure_id_invalid"),
        ({"assumption_id": "_capacity"}, "capacity_assumption_id_invalid"),
        ({"instrument": ""}, "capacity_assumption_instrument_invalid"),
        ({"instrument": " BTC-USDT-PERP"}, "capacity_assumption_instrument_invalid"),
        ({"unit_id": "unlimited_notional"}, "capacity_assumption_unbounded_declaration"),
        ({"capacity_measure_id": "asymptotic_capacity"}, "capacity_assumption_unbounded_declaration"),
        ({"basis_id": "infinite_depth"}, "capacity_assumption_unbounded_declaration"),
        ({"scope_id": "uncapped"}, "capacity_assumption_unbounded_declaration"),
        ({"basis_id": "scheduler_review"}, "forbidden_scope_token:capacity_assumption_basis_id"),
        ({"instrument": "BIST30"}, "bist_scope_leakage:capacity_assumption_instrument"),
    ],
)
def test_capacity_assumption_must_declare_unit_scope_and_basis_and_never_be_unbounded(
    change: dict[str, object], code: str
) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, **change),))


@pytest.mark.parametrize(
    ("assumptions", "code"),
    [
        (lambda: {CAPACITY}, "capacity_assumptions_malformed"),
        (lambda: CAPACITY, "capacity_assumptions_malformed"),
        (lambda: (object(),), "capacity_assumption_malformed"),
        (
            lambda: (CAPACITY, replace(CAPACITY_OI, assumption_id=CAPACITY.assumption_id)),
            "capacity_assumption_duplicate",
        ),
        (lambda: (CAPACITY, replace(CAPACITY, assumption_id="capacity-2")), "capacity_assumption_ambiguous"),
    ],
)
def test_capacity_set_structure_is_validated(assumptions, code: str) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), capacity_assumptions=assumptions())


def test_missing_capacity_assumptions_need_governance_approval() -> None:
    decision = decide(ef6t.cheap(), capacity_assumptions=(), governance=approval_for(cheap_draft()))
    _assert_receipt_invariants(decision)
    assert _code("capacity_assumptions_missing") in decision.verdict_reason_codes
    assert _code("admission_governance_capacity_assumption_set_digest_mismatch") in decision.verdict_reason_codes


def test_capacity_outside_the_pinned_universe_fails_and_the_pinned_instrument_still_needs_one() -> None:
    both = decide(ef6t.cheap(), capacity_assumptions=(CAPACITY, CAPACITY_OTHER))
    assert _code("capacity_assumption_instrument_outside_pinned_universe:capacity-other") in both.verdict_reason_codes
    only_other = decide(ef6t.cheap(), capacity_assumptions=(CAPACITY_OTHER,))
    assert {
        _code("capacity_assumption_instrument_outside_pinned_universe:capacity-other"),
        _code(f"capacity_assumption_missing_for_instrument:{INS}"),
    } <= set(only_other.verdict_reason_codes)


def test_resealed_forged_capacity_never_verifies() -> None:
    decision = cheap_approved()
    changed = (replace(CAPACITY, max_value="999999.000000000000000000"),)
    _assert_not_intact(_reseal(decision, capacity_assumptions=changed), "field_mismatch:capacity_assumption_set_digest")
    coherent = decide(ef6t.cheap(), capacity_assumptions=changed, governance=decision.governance)
    _assert_not_intact(
        _reseal(
            decision,
            capacity_assumptions=changed,
            capacity_assumption_set_digest=coherent.capacity_assumption_set_digest,
        ),
        "field_mismatch:verdict_reason_codes",
    )


def test_capacity_and_risk_budget_stay_separate_with_no_arithmetic_between_them() -> None:
    tiny = decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, max_value="0.000000000000000001"),))
    huge = decide(ef6t.cheap(), capacity_assumptions=(replace(CAPACITY, max_value="9" * 41 + "." + "0" * 18),))
    assert tiny.verdict_reason_codes == huge.verdict_reason_codes == cheap_draft().verdict_reason_codes
    assert tiny.risk_budget_policy_digest == huge.risk_budget_policy_digest
    assert tiny.capacity_assumption_set_digest != huge.capacity_assumption_set_digest
    richer = budget_policy(total_budget="1000000")
    other_budget = decide(
        ef6t.cheap(), risk_budget_policy=richer, expected_risk_budget_policy_digest=richer.policy_digest
    )
    assert other_budget.capacity_assumption_set_digest == cheap_draft().capacity_assumption_set_digest
    assert other_budget.verdict_reason_codes == cheap_draft().verdict_reason_codes


def test_capacity_set_digest_commits_the_governed_assumption_status() -> None:
    decision = cheap_draft()
    assert decision.capacity_assumption_set_digest == _digest(
        {
            "capacity_rule_id": edge_paper_admission_rule_set()["capacity_rule_id"],
            "evidence_status": "GOVERNED_ASSUMPTION_NOT_EMPIRICALLY_PROVEN",
            "assumptions": [
                {field.name: getattr(CAPACITY, field.name) for field in fields(EdgeCapacityAssumption)},
            ],
        }
    )
    assert decision.capacity_empirically_proven is False
    assert decision.current_venue_facts_consumed is False


# --- F. risk-budget linkage ----------------------------------------------------------------------------------------------


def _policy_variant(**changes: object) -> PaperSleeveRiskBudgetPolicy:
    changed = replace(budget_policy(), **changes)
    return replace(changed, policy_digest=paper_sleeve_risk_budget_policy_digest(changed))


def test_tampered_policy_is_rejected() -> None:
    tampered = replace(budget_policy(), total_budget="999999")
    decision = decide(ef6t.cheap(), risk_budget_policy=tampered)
    _assert_receipt_invariants(decision)
    assert set(decision.integrity_reason_codes) == {
        _code("risk_budget_policy_digest_mismatch"),
        _code("risk_budget_policy_noncanonical"),
    }
    assert decision.risk_budget_policy_id == ""


def test_tampered_and_resealed_policy_is_rejected_against_the_original_anchor_and_unapproved_otherwise() -> None:
    resealed = _policy_variant(total_budget="999999")
    against_original = decide(ef6t.cheap(), risk_budget_policy=resealed)
    assert against_original.integrity_reason_codes == (_code("risk_budget_policy_digest_mismatch"),)
    reanchored = decide(
        ef6t.cheap(),
        risk_budget_policy=resealed,
        expected_risk_budget_policy_digest=resealed.policy_digest,
        governance=approval_for(cheap_draft()),
    )
    assert reanchored.status is EdgeEvidenceStatus.READY
    assert _code("admission_governance_risk_budget_policy_digest_mismatch") in reanchored.verdict_reason_codes


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"paper_only": False}, "risk_budget_policy_noncanonical"),
        ({"real_orders_enabled": True}, "risk_budget_policy_noncanonical"),
        ({"real_money_enabled": True}, "risk_budget_policy_noncanonical"),
        ({"schema_version": "paper-sleeve-risk-budget-policy.v0"}, "risk_budget_policy_noncanonical"),
        ({"metadata": (("z", "1"), ("a", "2"))}, "risk_budget_policy_noncanonical"),
        ({"total_budget": "1e5"}, "risk_budget_policy_rebuild_failed"),
        ({"total_budget": "0"}, "risk_budget_policy_rebuild_failed"),
        ({"require_journal_bound": False}, "risk_budget_policy_rebuild_failed"),
        ({"metadata": (("source", "api_key_vault"),)}, "risk_budget_policy_scope_violation"),
    ],
)
def test_resealed_malformed_or_unsafe_policy_is_rejected(changes: dict[str, object], code: str) -> None:
    policy = _policy_variant(**changes)
    decision = decide(ef6t.cheap(), risk_budget_policy=policy, expected_risk_budget_policy_digest=policy.policy_digest)
    _assert_receipt_invariants(decision)
    assert _code(code) in decision.integrity_reason_codes
    assert decision.risk_budget_policy_id == ""


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        (lambda: {"risk_budget_policy": None}, "risk_budget_policy_malformed"),
        (lambda: {"risk_budget_policy": budget_policy().policy_digest}, "risk_budget_policy_malformed"),
        (
            lambda: {"risk_budget_policy": object.__new__(PaperSleeveRiskBudgetPolicy)},
            "risk_budget_policy_not_serializable",
        ),
        (
            lambda: {"risk_budget_policy": replace(budget_policy(), metadata=(("k", 1),))},
            "risk_budget_policy_not_serializable",
        ),
        (
            lambda: {"risk_budget_policy": replace(budget_policy(), total_budget=1000.0)},
            "risk_budget_policy_not_serializable",
        ),
        (lambda: {"expected_risk_budget_policy_digest": "xyz"}, "risk_budget_policy_expected_digest_invalid"),
        (lambda: {"expected_risk_budget_policy_digest": None}, "risk_budget_policy_expected_digest_invalid"),
    ],
)
def test_digest_only_or_malformed_policy_input_is_a_construction_error(overrides, code: str) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), **overrides())


def test_policy_for_another_sleeve_fails_the_linkage() -> None:
    other = budget_policy(sleeve_id="basis-sleeve-2")
    decision = decide(ef6t.cheap(), risk_budget_policy=other, expected_risk_budget_policy_digest=other.policy_digest)
    _assert_receipt_invariants(decision)
    assert _code("risk_budget_policy_sleeve_mismatch") in decision.verdict_reason_codes
    relinked = decide(
        ef6t.cheap(),
        risk_budget_policy=other,
        expected_risk_budget_policy_digest=other.policy_digest,
        paper_sleeve_id="basis-sleeve-2",
        governance=approval_for(cheap_draft()),
    )
    assert _code("risk_budget_policy_sleeve_mismatch") not in relinked.verdict_reason_codes
    assert {
        _code("admission_governance_admission_subject_digest_mismatch"),
        _code("admission_governance_risk_budget_policy_digest_mismatch"),
    } <= set(relinked.verdict_reason_codes)


def test_budget_linkage_is_identity_only_never_allocation_execution_or_capital() -> None:
    decision = admitted()
    assert decision.advances is True
    names = {field.name for field in fields(EdgePaperAdmissionDecision)}
    assert {name for name in names if "budget" in name} == {
        "risk_budget_policy_binding",
        "risk_budget_policy_id",
        "risk_budget_policy_digest",
    }
    for flag in (
        "portfolio_allocation_approved",
        "capital_allocated",
        "execution_authorized",
        "real_capital_reserved",
        "real_orders_enabled",
        "real_money_enabled",
    ):
        assert getattr(decision, flag) is False
    assert decision.portfolio_risk_envelope_status == "PENDING_RG_PORTFOLIO_RISK_ENVELOPE_UNAVAILABLE"


def test_future_portfolio_rg_is_an_honest_pending_marker_never_a_fabricated_envelope() -> None:
    for decision in (cheap_draft(), cheap_approved(), decide(ef6t.cheap(), correlation_id="corr-2")):
        assert decision.portfolio_risk_envelope_status == EDGE_PORTFOLIO_RISK_ENVELOPE_PENDING
    assert "portfolio_risk_rule_id" in edge_paper_admission_rule_set()
    closure = _import_closure()
    assert not [name for name in closure if "portfolio" in name or "allocation" in name]


# --- G. the selection firewall -------------------------------------------------------------------------------------------


def test_admitted_set_is_exactly_the_pre_paper_admitted_ef6_survivors_and_carries_no_ranking() -> None:
    decision = admitted()
    predecessor = passing_chain()
    admitted_digests = tuple(item.parameter_assignment_digest for item in decision.admitted_variants)
    assert admitted_digests == pret.passed().admitted_assignment_digests
    assert set(admitted_digests) < set(predecessor.surviving_assignment_digests)
    assert set(admitted_digests) <= set(pret.ef5_p().registered_parameter_assignment_digests)
    names = {field.name for field in fields(EdgePaperAdmissionDecision)} | {
        field.name for field in fields(EdgeAdmittedVariant)
    }
    tokens = ("best", "winner", "rank", "select", "score", "sharpe", "pnl", "profit_factor", "preferred")
    assert not [name for name in names if any(token in name for token in tokens)]


def test_unregistered_or_reordered_admitted_variants_never_verify() -> None:
    decision = cheap_approved()
    injected = (EdgeAdmittedVariant("variant-z", "f" * 64),)
    _assert_not_intact(_reseal(decision, admitted_variants=injected, admitted_variant_count=1))
    two = decide(ef6_two_registered())
    assert two.admitted_variants == ()
    _assert_not_intact(_reseal(two, pinned_instrument_universe=(OTHER_INS, INS)))


def test_equivalent_input_permutations_produce_the_identical_decision() -> None:
    forward = decide(ef6t.cheap(), capacity_assumptions=(CAPACITY, CAPACITY_OI))
    backward = decide(ef6t.cheap(), capacity_assumptions=[CAPACITY_OI, CAPACITY])
    assert edge_paper_admission_decision_to_dict(forward) == edge_paper_admission_decision_to_dict(backward)
    assert tuple(item.assumption_id for item in forward.capacity_assumptions) == (
        "capacity-notional",
        "capacity-open-interest",
    )


# --- H. status and flags -------------------------------------------------------------------------------------------------


def test_non_claim_flags_are_structural_defaults_no_builder_parameter_can_set() -> None:
    defaults = {
        field.name: field.default
        for field in fields(EdgePaperAdmissionDecision)
        if field.name in dict(EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS)
    }
    assert defaults == dict(EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS)
    structural = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    computed = {
        "candidate_admitted_to_paper",
        "kill_criteria_sealed",
        "preregistration_sealed",
        "performance_data_consumed",
        "oos_evidence_consumed",
        "pre_paper_validation_passed",
    }
    assert structural - computed <= set(defaults)
    assert all(field.default is MISSING for field in fields(EdgePaperAdmissionDecision) if field.name in computed)
    assert set(inspect.signature(build_edge_paper_admission_decision).parameters).isdisjoint(defaults.keys() | computed)


@pytest.mark.parametrize(
    "changes",
    [
        {"edge_proven": True},
        {"profitability_proven": True},
        {"live_ready": True},
        {"prdv4_stage4_complete": True},
        {"portfolio_allocation_approved": True},
        {"execution_authorized": True},
        {"capacity_empirically_proven": True},
        {"regime_evidence_available": True},
        {"performance_data_consumed": True},
        {"oos_evidence_consumed": True},
        {"candidate_admitted_to_paper": True},
        {"preregistration_sealed": False},
        {"portfolio_risk_envelope_status": "RG_ENVELOPE_APPROVED"},
        {"capacity_evidence_status": "EMPIRICALLY_PROVEN"},
        {"predecessor_gate_verdict": "PASS"},
        {"pre_paper_validation_passed": True},
        {"pre_paper_evidence_gate_verdict": "PASS"},
        {"admission_cap_fraction": "1.000000000000000000"},
        {"admission_scope": "FULL_PRDV4_COMPLIANT"},
        {"regime_conditional_pbo_status": "PROVEN"},
        {"pbo_band": "NORMAL"},
        {"pbo_passed": True},
        {"stress_passed": True},
    ],
)
def test_forged_flags_or_claims_never_verify(changes: dict[str, object]) -> None:
    _assert_not_intact(_reseal(cheap_approved(), **changes))


@pytest.mark.parametrize(
    "state",
    ["fail", "fail_governed", "rejected", "policy_rejected", "capacity_missing"],
)
def test_every_cheap_builder_state_round_trips_through_the_verifier(state: str) -> None:
    builders = {
        "fail": cheap_draft,
        "fail_governed": cheap_approved,
        "rejected": lambda: decide(ef6t.cheap(), correlation_id="corr-2"),
        "policy_rejected": lambda: decide(ef6t.cheap(), risk_budget_policy=replace(budget_policy(), total_budget="1")),
        "capacity_missing": lambda: decide(ef6t.cheap(), capacity_assumptions=()),
    }
    decision = builders[state]()
    _assert_receipt_invariants(decision)
    assert decision.advances is False and decision.candidate_admitted_to_paper is False


# --- I. serialization and totality ---------------------------------------------------------------------------------------


def test_round_trip_and_digest_determinism() -> None:
    decision = cheap_approved()
    assert edge_paper_admission_decision_from_payload(_payload(decision)) == decision
    again = decide(ef6t.cheap(), governance=approval_for(cheap_draft()))
    assert again == decision
    assert edge_paper_admission_decision_digest(again) == decision.paper_admission_decision_digest


def test_decision_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cheap_approved().status = EdgeEvidenceStatus.READY  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        CAPACITY.max_value = "1.000000000000000000"  # type: ignore[misc]


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), None),
        (("status",), "ready"),
        (("advances",), 1),
        (("multiple_testing_count",), True),
        (("multiple_testing_count",), -1),
        (("multiple_testing_count",), 1.0),
        (("admitted_variant_count",), "0"),
        (("admitted_variants",), {}),
        (("capacity_assumptions",), [{}]),
        (("capacity_assumptions", 0, "max_value"), 250000.0),
        (("capacity_assumptions", 0, "extra"), "x"),
        (("governance",), {}),
        (("governance", "approval_digest"), 1),
        (("pinned_instrument_universe",), "BTC-USDT-PERP"),
        (("risk_budget_policy_binding", "snapshot"), {}),
        (("risk_budget_policy_binding", "snapshot", "paper_only"), "true"),
        (("risk_budget_policy_binding", "snapshot", "metadata"), [["k"]]),
        (("risk_budget_policy_binding", "expected_digest"), "A" * 64),
        (("predecessor_binding", "snapshot"), {}),
        (("predecessor_binding", "snapshot", "status"), "WINNER"),
        (("pre_paper_evidence_binding", "snapshot"), {}),
        (("pre_paper_evidence_binding", "snapshot", "pbo_band"), "PASSED"),
        (("pre_paper_validation_passed",), "true"),
        (("governance", "approved_pre_paper_evidence_digest"), _UNSET),
        (("candidate_admitted_to_paper",), 1),
        (("kill_criteria_sealed",), _UNSET),
        (("unexpected_field",), "x"),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = _payload(cheap_approved())
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    assert edge_paper_admission_decision_payload_is_well_formed(payload) is False


def test_builder_and_verifier_share_one_policy_shape_domain() -> None:
    policy = replace(budget_policy(), metadata=(("k", 1),))
    with pytest.raises(EdgePaperAdmissionDecisionError, match="risk_budget_policy_not_serializable"):
        decide(ef6t.cheap(), risk_budget_policy=policy)
    payload = _payload(cheap_approved())
    payload["risk_budget_policy_binding"]["snapshot"]["metadata"] = [["k", 1]]
    assert edge_paper_admission_decision_payload_is_well_formed(payload) is False


def _corrupted(**changes: object) -> EdgePaperAdmissionDecision:
    copy = replace(cheap_approved())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def _cyclic() -> list:
    loop: list = []
    loop.append(loop)
    return loop


class _HostileMapping(dict):
    def __getitem__(self, key: object) -> object:
        raise RuntimeError("hostile mapping")


class _Exploding:
    def __getattr__(self, name: str) -> object:
        raise RuntimeError("exploding attribute")


@pytest.mark.parametrize(
    "decision",
    [
        lambda: None,
        lambda: 0,
        lambda: "ef7",
        lambda: {},
        lambda: [],
        lambda: object(),
        lambda: ValueError("x"),
        lambda: _HostileMapping(a=1),
        lambda: _Exploding(),
        lambda: object.__new__(EdgePaperAdmissionDecision),
        lambda: ef6t.cheap(),
        lambda: _corrupted(predecessor_binding=None),
        lambda: _corrupted(pre_paper_evidence_binding=None),
        lambda: _corrupted(risk_budget_policy_binding=object()),
        lambda: _corrupted(capacity_assumptions=_cyclic()),
        lambda: _corrupted(capacity_assumptions=(object(),)),
        lambda: _corrupted(governance=object()),
        lambda: _corrupted(final_kill_criteria=(object(),)),
        lambda: _corrupted(admitted_variants=None),
        lambda: _corrupted(multiple_testing_count="1"),
        lambda: _corrupted(status="READY"),
        lambda: _corrupted(gate_verdict="FAIL"),
        lambda: _corrupted(decision_id="ef7 scheduler"),
        lambda: _corrupted(paper_sleeve_id=_HostileMapping()),
    ],
)
def test_public_verifier_is_total_for_any_object(decision) -> None:
    _assert_not_intact(decision())


def test_str_enum_alias_is_never_intact() -> None:
    alias = _corrupted(status="READY", gate_verdict="FAIL")
    verification = _assert_not_intact(alias)
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- J. determinism, scope and static purity -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"decision_id": ""}, "decision_id_invalid"),
        ({"decision_id": "live-ef7"}, "forbidden_scope_token:decision_id"),
        ({"decision_id": "bist-ef7"}, "bist_scope_leakage:decision_id"),
        ({"decision_id": "ef7 order_id 1"}, "forbidden_scope_token:decision_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"correlation_id": "kap"}, "bist_scope_leakage:correlation_id"),
        ({"paper_sleeve_id": ""}, "paper_sleeve_id_invalid"),
        ({"paper_sleeve_id": "private_api-sleeve"}, "forbidden_scope_token:paper_sleeve_id"),
        ({"paper_sleeve_id": "auto_loop-sleeve"}, "forbidden_scope_token:paper_sleeve_id"),
        ({"expected_root_intake_digest": "A" * 64}, "root_intake_digest_invalid"),
        ({"expected_predecessor_digest": "a" * 63}, "predecessor_expected_digest_invalid"),
    ],
)
def test_malformed_or_out_of_scope_caller_input_is_a_construction_error(
    overrides: dict[str, object], code: str
) -> None:
    with pytest.raises(EdgePaperAdmissionDecisionError, match=code):
        decide(ef6t.cheap(), **overrides)


def test_rule_set_digest_commits_the_code_defined_rules() -> None:
    rules = edge_paper_admission_rule_set()
    assert EDGE_PAPER_ADMISSION_RULE_SET_DIGEST == _digest(rules)
    rules["capacity_value_scale"] = 2
    assert edge_paper_admission_rule_set()["capacity_value_scale"] == 18
    assert cheap_draft().rule_set_id == "edge_paper_admission_rules.v2"
    assert (rules["admission_scope"], rules["regime_conditional_pbo_status"]) == ("LIMITED_S1_PAPER_V1", "UNPROVEN")


_FORBIDDEN_MODULES = (
    "math",
    "decimal",
    "fractions",
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "threading",
    "asyncio",
    "multiprocessing",
    "subprocess",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
    "importlib",
    "pickle",
    "functools",
    "bist_core",
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "eval", "exec", "compile", "__import__", "now", "utcnow", "time_ns", "getenv", "print"}
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(ef7_module.__file__).read_text(encoding="utf-8"))


@functools.cache
def _import_closure() -> frozenset[str]:
    closure: set[str] = set()
    pending = {ef7_module.__name__}
    while pending:
        name = pending.pop()
        closure.add(name)
        source = Path(importlib.import_module(name).__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        pending |= {
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core")
        } - closure
    return frozenset(closure)


def test_module_has_no_io_clock_randomness_float_cache_or_dynamic_execution() -> None:
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "system", "popen"}


def test_module_consumes_only_public_authenticated_substrate() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_leakage_bias_evidence",
        "crypto_core.validation.edge_pre_paper_validation_evidence",
        "crypto_core.validation.edge_pre_paper_validation_policy",
        "crypto_core.validation.edge_source_packet_evidence",
        "crypto_core.validation.edge_strategy_spec_admission",
        "crypto_core.validation.edge_walk_forward_oos_evidence",
        "crypto_core.validation.paper_sleeve_risk_budget_decision",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}
    assert crypto_imports["crypto_core.validation.paper_sleeve_risk_budget_decision"] == {
        "PaperSleeveRiskBudgetPolicy",
        "build_paper_sleeve_risk_budget_policy",
        "paper_sleeve_risk_budget_policy_digest",
        "paper_sleeve_risk_budget_policy_to_dict",
    }


# EF-5 V2 (EF5_RF6_REGIME_POLICY_PREREGISTRATION_ADMISSION_V1) re-proves every registered regime filter policy through the
# public RF-2 verifier, so exactly that policy-only preregistration authority joins this closure. The exemption is ONE
# exact module name, compared by equality: RF-3..RF-6 regime evidence and decisions, the runtime ``crypto_core.regime``
# package, every other regime-named module, and every prefix, suffix or near-miss of the exact name stay forbidden, as
# does every other surface token.
_RF2_POLICY_AUTHORITY = "crypto_core.validation.regime_feature_policy"
_SURFACE_TOKENS = (
    "kill_quarantine",
    "portfolio",
    "regime",
    "pbo",
    "stress",
    "service",
    "venue",
    "execution.",
    "live",
    "order",
    "connector",
    "scheduler",
)


def _forbidden_surface(closure: frozenset[str]) -> list[str]:
    """Every closure member naming a forbidden surface, except exactly the RF-2 policy authority."""

    return sorted(
        name for name in closure if name != _RF2_POLICY_AUTHORITY and any(token in name for token in _SURFACE_TOKENS)
    )


def test_no_ef8_rg_regime_service_venue_live_order_or_capital_surface() -> None:
    closure = _import_closure()
    assert _forbidden_surface(closure) == []
    # The exemption is in use, and the exempt module stays a policy-only authority reaching no other module.
    assert _RF2_POLICY_AUTHORITY in closure
    rf2_source = Path(importlib.import_module(_RF2_POLICY_AUTHORITY).__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
    rf2_imports = {
        node.module
        for node in ast.walk(ast.parse(rf2_source))
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core")
    }
    assert rf2_imports == {"crypto_core.validation.edge_artifact_core"}
    names = {field.name for field in fields(EdgePaperAdmissionDecision)} - dict(
        EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS
    ).keys()
    forbidden = (
        "order",
        "route",
        "venue",
        "credential",
        "api_key",
        "margin",
        "equity",
        "balance",
        "reservation",
        "ef8",
    )
    assert not [name for name in names if any(token in name for token in forbidden)]


@pytest.mark.parametrize(
    "name",
    [
        "crypto_core.validation.regime_feature_series_evidence",
        "crypto_core.validation.regime_label_evidence",
        "crypto_core.validation.regime_stability_evidence",
        "crypto_core.validation.regime_filter_admission_decision",
        "crypto_core.regime",
        "crypto_core.regime.tracker",
        "crypto_core.execution.regime_contracts",
        "crypto_core.service.external_regime",
        "crypto_core.validation.regime_feature_policy_v2",
        "crypto_core.validation.regime_feature_policy.extension",
        "crypto_core.validation.regime_feature_polic",
        "tests.crypto_core.validation.regime_feature_policy",
        "crypto_core.validation.paper_portfolio_performance_path_policy",
        "crypto_core.service.anything",
        "crypto_core.execution.order_router",
    ],
)
def test_the_closure_guard_exempts_only_the_exact_rf2_policy_authority(name: str) -> None:
    """EF-7: any other regime, runtime or surface module, or any variant of the exempt name, is still flagged."""

    assert _forbidden_surface(frozenset({_RF2_POLICY_AUTHORITY})) == []
    assert _forbidden_surface(frozenset({_RF2_POLICY_AUTHORITY, name})) == [name]


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(_module_tree()) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgePaperAdmissionDecision")
    assert constructor_calls == 1
    assert "EdgePaperAdmissionDecision" in calls_by_function["_assemble_decision"]
    assert "_assemble_decision" in calls_by_function["build_edge_paper_admission_decision"]
    assert "_assemble_decision" in calls_by_function["_reassemble_decision"]
