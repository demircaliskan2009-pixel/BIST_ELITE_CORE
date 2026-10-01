"""Tests for Edge Factory EF-8 kill / quarantine lifecycle (EF8_EDGE_KILL_QUARANTINE_LIFECYCLE_V1).

Fixtures are REAL authenticated chains. The admission is the EF-7 test module's governed PASS over world A (one
registered variant surviving three PRDV4 windows whose out-of-sample horizon ends on day 635). The revalidation is a
genuinely distinct EF-5-onward chain: the same sealed EF-5 re-proven unchanged, a NEW EF-6 over a new window frame shifted
by one funding cycle (horizon day 637) and a NEW governed EF-7. The authentic lifecycle is ACTIVE at the day-635 horizon,
DISABLED on day 636 (after the admission horizon, before the revalidation horizon), in QUARANTINE 31 days later and
re-admitted 14 days after that, so the re-admission rests on evaluation evidence the killed admission never had. A cheap
non-advancing lifecycle over the EF-7 module's governed FAIL admission exercises every transition's structure, parser and
verifier at small payload size. Every approval, observation and coordinate below is a SYNTHETIC TEST VALUE; EF-8 holds no
production threshold (its 30/14-day boundaries are the accepted Edge Factory design).

Every receipt is lifecycle HISTORY. Whatever its historical result, no receipt (a genesis, a second genesis over an
already killed EF-7, a stale ACTIVE receipt, one of several forked children or a governed re-admission) claims current
paper admission or the current lifecycle head; Astra's G0 → D1 → G0b reproduction is a direct regression.

The EF-7 and EF-6 test modules are imported under the module names pytest collects them with (basename import), so their
cached authentic worlds and memos are one object shared with their own tests.

CI budget: the required ``tests`` job runs under a 20-minute timeout, so rules that need PASS evidence run on the one
cached authentic lifecycle and everything structural runs on the cheap lifecycle; a NEEDS_EXTERNAL_FACTS admission world,
a second full kill cycle and the memo-free end-to-end re-proof are ``@pytest.mark.slow``.

Cost control: the pure public functions EF-8 calls to re-prove OTHER artifacts are memoized at EF-8's call site with the
EF-6 module's exact memo — the EF-7 verifier (exact key), the EF-7 and EF-6 strict parsers and the EF-7 shape predicate
(canonical JSON key), and, because every transition re-proves its prior recursively down to the genesis, EF-8's own public
verifier, strict parser and shape predicate as EF-8 resolves them for a PRIOR artifact. Every tampered, forged or
hostile object is verified by the real function imported below, and builder states are re-proven through the same
exact memo so a state already re-proven as a prior is not re-proven twice. A memo only returns the result of an identical
earlier real call (exact keys: a tampered artifact is always a miss), a raising call is never cached, and a slow test
re-proves the whole lifecycle with every memo disabled.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import importlib
import inspect
import json
from dataclasses import MISSING, FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.edge_kill_quarantine_decision as ef8_module
import crypto_core.validation.edge_paper_admission_decision as ef7_module
from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    edge_kill_criteria_digest,
    edge_kill_criterion_to_dict,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EDGE_KILL_OBSERVATION_STATUS,
    EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS,
    EDGE_KILL_QUARANTINE_RULE_SET_DIGEST,
    EDGE_RESULTING_LIFECYCLE_STATE_STATUS,
    EdgeKillEvaluation,
    EdgeKillObservation,
    EdgeKillQuarantineDecision,
    EdgeKillQuarantineDecisionError,
    EdgeLifecycleState,
    EdgeLifecycleTransition,
    EdgeReadmissionGovernance,
    build_edge_kill_quarantine_governed_readmission,
    build_edge_kill_quarantine_initial_activation,
    build_edge_kill_quarantine_kill_disable,
    build_edge_kill_quarantine_quarantine_entry,
    edge_kill_criterion_triggered,
    edge_kill_quarantine_decision_digest,
    edge_kill_quarantine_decision_from_payload,
    edge_kill_quarantine_decision_payload_is_well_formed,
    edge_kill_quarantine_decision_to_dict,
    edge_kill_quarantine_rule_set,
    verify_edge_kill_quarantine_decision,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS,
    EdgePaperAdmissionDecision,
    edge_paper_admission_decision_digest,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeVariantMetricsInput,
    EdgeWalkForwardOosEvidence,
    build_edge_walk_forward_oos_evidence,
)

try:  # the module objects pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_paper_admission_decision as ef7t
    import test_edge_walk_forward_oos_evidence as ef6t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t

_PREFIX = "edge_kill_quarantine_decision"
_SELF = "kill_quarantine_decision_digest"
_UNSET = object()
SLOW = pytest.mark.slow  # an extra authenticated world or a memo-free re-proof; see the module docstring
ACTIVE, DISABLED, QUARANTINE = EdgeLifecycleState.ACTIVE, EdgeLifecycleState.DISABLED, EdgeLifecycleState.QUARANTINE
T = EdgeLifecycleTransition
DAY, S0 = ef6t.DAY, ef6t.S0
CORR = "corr-1"
ADMISSION_HORIZON = S0 + 635 * DAY  # the latest OOS end of the admission's EF-6 frame (windows start on 0, 90, 180)
REVALIDATION_STARTS = (2, 92, 182)  # the same geometry shifted by one funding cycle: a new frame, OOS horizon day 637
REVALIDATION_HORIZON = S0 + 637 * DAY
T_ACTIVATE = ADMISSION_HORIZON
T_KILL = S0 + 636 * DAY
T_QUARANTINE = T_KILL + 31 * DAY
T_READMIT = T_QUARANTINE + 14 * DAY
DRAWDOWN = "max_drawdown_breach"  # max_drawdown kill_if_at_or_above 0.25 over rolling_30_utc_days
FUNDING_FLIP = "funding_flip_persistence"  # negative_funding_hours kill_if_above 12 over rolling_7_utc_days
_OBSERVED = {
    DRAWDOWN: ("max_drawdown", "rolling_30_utc_days"),
    FUNDING_FLIP: ("negative_funding_hours", "rolling_7_utc_days"),
}
COMMITMENTS = (
    "prior_lifecycle_digest",
    "lifecycle_subject_digest",
    "revalidation_decision_digest",
    "sealed_kill_criteria_digest",
    "effective_at_ns",
    "rule_set_digest",
)
SUBJECT_FIELDS = (
    "candidate_strategy_id",
    "edge_family",
    "strategy_id",
    "strategy_version",
    "strategy_spec_digest",
    "strategy_spec_admission_digest",
    "source_manifest_digest",
    "market_type",
    "pinned_instrument_universe",
    "paper_sleeve_id",
)
COMPUTED_FLAGS = (
    "kill_criteria_sealed",
    "preregistration_sealed",
    "performance_data_consumed",
    "oos_evidence_consumed",
)
# Only an accepted lifecycle-head authority could support these; a stateless receipt never claims them.
CURRENT_AUTHORITY_CLAIMS = ("candidate_admitted_to_paper", "current_lifecycle_head_proven", "auto_reactivation_enabled")

# --- memoized re-proof of other artifacts (see module docstring) ---------------------------------------------------------

_EF8_MEMOS = {
    "verify_edge_paper_admission_decision": ef6t._Memoized(
        ef8_module.verify_edge_paper_admission_decision, ef6t._exact_key
    ),
    "verify_edge_kill_quarantine_decision": ef6t._Memoized(verify_edge_kill_quarantine_decision, ef6t._exact_key),
    **{
        name: ef6t._Memoized(getattr(ef8_module, name), edge_canonical_json)
        for name in (
            "edge_paper_admission_decision_payload_is_well_formed",
            "edge_paper_admission_decision_from_payload",
            "edge_walk_forward_oos_evidence_from_payload",
            "edge_kill_quarantine_decision_payload_is_well_formed",
            "edge_kill_quarantine_decision_from_payload",
        )
    },
}


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        for (module, name), memo in ef6t._MEMOS.items():
            patch.setattr(module, name, memo)
        for name, memo in ef7t._EF7_MEMOS.items():
            patch.setattr(ef7_module, name, memo)
        for name, memo in _EF8_MEMOS.items():
            patch.setattr(ef8_module, name, memo)
        yield


# --- builders ------------------------------------------------------------------------------------------------------------


def _root() -> str:
    return ef6t.world()[0].intake_digest


def _common(overrides: dict[str, object]) -> dict[str, object]:
    arguments: dict[str, object] = {"expected_root_intake_digest": _root(), "correlation_id": CORR}
    arguments.update(overrides)
    return arguments


def observe(
    criterion_id: str = DRAWDOWN, value: str = "0.300000000000000000", **changes: object
) -> EdgeKillObservation:
    """SYNTHETIC TEST VALUES: one caller-declared paper-metric observation of one sealed criterion."""

    metric_id, basis = _OBSERVED.get(criterion_id, _OBSERVED[DRAWDOWN])
    arguments: dict[str, object] = {
        "criterion_id": criterion_id,
        "metric_id": metric_id,
        "evaluation_basis": basis,
        "observed_value": value,
        "observation_reference": "paper-metrics-report-1",
        "observation_source_digest": "a" * 64,
    }
    arguments.update(changes)
    return EdgeKillObservation(**arguments)  # type: ignore[arg-type]


def activate(admission: EdgePaperAdmissionDecision, **overrides: object) -> EdgeKillQuarantineDecision:
    arguments = _common(
        {
            "expected_admission_digest": admission.paper_admission_decision_digest,
            "effective_at_ns": T_ACTIVATE,
            "decision_id": "ef8-activate",
            "reason_reference": "admission-review-1",
            **overrides,
        }
    )
    return build_edge_kill_quarantine_initial_activation(admission, **arguments)  # type: ignore[arg-type]


def disable(
    prior: EdgeKillQuarantineDecision, observation: object = None, **overrides: object
) -> EdgeKillQuarantineDecision:
    arguments = _common(
        {
            "expected_prior_digest": prior.kill_quarantine_decision_digest,
            "kill_observation": observe() if observation is None else observation,
            "effective_at_ns": T_KILL,
            "decision_id": "ef8-disable",
            "reason_reference": "kill-review-1",
            **overrides,
        }
    )
    return build_edge_kill_quarantine_kill_disable(prior, **arguments)  # type: ignore[arg-type]


def quarantine(prior: EdgeKillQuarantineDecision, **overrides: object) -> EdgeKillQuarantineDecision:
    arguments = _common(
        {
            "expected_prior_digest": prior.kill_quarantine_decision_digest,
            "effective_at_ns": T_QUARANTINE,
            "decision_id": "ef8-quarantine",
            "reason_reference": "quarantine-review-1",
            **overrides,
        }
    )
    return build_edge_kill_quarantine_quarantine_entry(prior, **arguments)  # type: ignore[arg-type]


def approval_for(
    prior: EdgeKillQuarantineDecision,
    revalidation: EdgePaperAdmissionDecision,
    effective_at_ns: int = T_READMIT,
    **overrides: object,
) -> EdgeReadmissionGovernance:
    """SYNTHETIC TEST VALUES: the exact commitments a human reviews before approving one re-admission."""

    arguments: dict[str, object] = {
        "approval_reference": "governance-ef8-1",
        "approval_digest": "b" * 64,
        "approved_prior_lifecycle_digest": prior.kill_quarantine_decision_digest,
        "approved_lifecycle_subject_digest": prior.lifecycle_subject_digest or "0" * 64,
        "approved_revalidation_decision_digest": revalidation.paper_admission_decision_digest,
        "approved_sealed_kill_criteria_digest": prior.sealed_kill_criteria_digest or "0" * 64,
        "approved_effective_at_ns": effective_at_ns,
        "approved_rule_set_digest": EDGE_KILL_QUARANTINE_RULE_SET_DIGEST,
    }
    arguments.update(overrides)
    return EdgeReadmissionGovernance(**arguments)  # type: ignore[arg-type]


def readmit(
    prior: EdgeKillQuarantineDecision,
    revalidation: EdgePaperAdmissionDecision,
    *,
    governance: object = _UNSET,
    **overrides: object,
) -> EdgeKillQuarantineDecision:
    effective = overrides.get("effective_at_ns", T_READMIT)
    arguments = _common(
        {
            "expected_prior_digest": prior.kill_quarantine_decision_digest,
            "revalidation": revalidation,
            "expected_revalidation_digest": revalidation.paper_admission_decision_digest,
            "effective_at_ns": effective,
            "decision_id": "ef8-readmit",
            "reason_reference": "readmission-review-1",
            "governance": approval_for(prior, revalidation, effective) if governance is _UNSET else governance,  # type: ignore[arg-type]
            **overrides,
        }
    )
    return build_edge_kill_quarantine_governed_readmission(prior, **arguments)  # type: ignore[arg-type]


# --- authentic worlds ----------------------------------------------------------------------------------------------------


def admission() -> EdgePaperAdmissionDecision:
    return ef7t.admitted()


@functools.cache
def revalidation_evidence() -> EdgeWalkForwardOosEvidence:
    """A NEW governed EF-6 PASS over the same sealed EF-5 on a frame shifted by one funding cycle (horizon day 637)."""

    bundle = ef6t.mt.build(
        tuple(ef6t._window(index, start, ef6t.PA) for index, start in enumerate(REVALIDATION_STARTS)),
        result_id="wf-A-revalidation",
    )
    predecessor = ef6t.ef5("A")
    arguments = {
        "expected_predecessor_digest": predecessor.leakage_bias_evidence_digest,
        "expected_root_intake_digest": _root(),
        "variant_metrics": (EdgeVariantMetricsInput(bundle, bundle.result_digest),),
        "evidence_id": "ef6-revalidation",
        "correlation_id": CORR,
    }
    draft = build_edge_walk_forward_oos_evidence(predecessor, **arguments)  # type: ignore[arg-type]
    return build_edge_walk_forward_oos_evidence(predecessor, **arguments, governance=ef6t.governance_for(draft))  # type: ignore[arg-type]


@functools.cache
def revalidation_draft() -> EdgePaperAdmissionDecision:
    return ef7t.decide(revalidation_evidence(), decision_id="ef7-revalidation")


@functools.cache
def revalidation() -> EdgePaperAdmissionDecision:
    """The fresh EF-7 PASS: same subject and seal as the admission, new EF-6, new EF-7."""

    return ef7t.decide(
        revalidation_evidence(), decision_id="ef7-revalidation", governance=ef7t.approval_for(revalidation_draft())
    )


@functools.cache
def pre_kill_revalidation() -> EdgePaperAdmissionDecision:
    """A NEW EF-6/EF-7 pair over the admission's own frame (horizon day 635): new digests, no post-kill evidence.

    Its evaluation frame, subject and seal equal the admitted chain's, so that chain's approvals re-apply with only the
    new EF-6 digest re-committed.
    """

    predecessor = ef6t.ef5("A")
    arguments = {**ef6t.arguments_for(predecessor, ("A",)), "evidence_id": "ef6-pre-kill"}
    evidence = build_edge_walk_forward_oos_evidence(
        predecessor,
        **arguments,
        governance=ef6t.governance_for(ef6t.passed()),  # type: ignore[arg-type]
    )
    approval = ef7t.approval_for(admission(), approved_predecessor_digest=evidence.walk_forward_oos_evidence_digest)
    return ef7t.decide(evidence, decision_id="ef7-pre-kill", governance=approval)


@functools.cache
def genesis() -> EdgeKillQuarantineDecision:
    return activate(admission())


@functools.cache
def disabled() -> EdgeKillQuarantineDecision:
    return disable(genesis())


@functools.cache
def quarantined() -> EdgeKillQuarantineDecision:
    return quarantine(disabled())


@functools.cache
def second_genesis() -> EdgeKillQuarantineDecision:
    """Astra's G0b: INITIAL_ACTIVATION again over the SAME, already killed EF-7 at a coordinate after the disable."""

    return activate(admission(), effective_at_ns=T_KILL + DAY, decision_id="ef8-second-genesis")


@functools.cache
def forked_disable() -> EdgeKillQuarantineDecision:
    """A second authentic child of the same genesis: another sealed criterion triggered at the same coordinate."""

    return disable(genesis(), observe(FUNDING_FLIP, "13.000000000000000000"), decision_id="ef8-disable-b")


@functools.cache
def readmission_draft() -> EdgeKillQuarantineDecision:
    return readmit(quarantined(), revalidation(), governance=None)


@functools.cache
def readmitted() -> EdgeKillQuarantineDecision:
    return readmit(quarantined(), revalidation())


# The cheap lifecycle: authentic, never advancing, small payloads (the EF-7 module's governed FAIL admission).
@functools.cache
def cheap_genesis() -> EdgeKillQuarantineDecision:
    return activate(ef7t.cheap_approved())


@functools.cache
def cheap_disable() -> EdgeKillQuarantineDecision:
    return disable(cheap_genesis())


@functools.cache
def cheap_quarantine() -> EdgeKillQuarantineDecision:
    return quarantine(cheap_genesis())


@functools.cache
def cheap_readmission() -> EdgeKillQuarantineDecision:
    return readmit(cheap_genesis(), ef7t.cheap_approved(), governance=None)


# --- assertions ----------------------------------------------------------------------------------------------------------


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _codes(*codes: str) -> tuple[str, ...]:
    return tuple(sorted(_code(code) for code in codes))


def _reseal(decision: EdgeKillQuarantineDecision, **changes: object) -> EdgeKillQuarantineDecision:
    changed = replace(decision, **changes)
    return replace(changed, kill_quarantine_decision_digest=edge_kill_quarantine_decision_digest(changed))


def _payload(decision: EdgeKillQuarantineDecision) -> dict:
    return json.loads(edge_canonical_json(edge_kill_quarantine_decision_to_dict(decision)))


def _resealed(payload: dict) -> EdgeKillQuarantineDecision:
    payload[_SELF] = edge_payload_digest(payload, _SELF)
    return edge_kill_quarantine_decision_from_payload(payload)


def _independent_digest(payload: dict, self_field: str) -> str:
    body = {key: value for key, value in payload.items() if key != self_field}
    text = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _subject_digest(source: object) -> str:
    """The lifecycle subject recomputed independently of the module."""

    subject: dict[str, object] = {"root_intake_digest": _root(), "correlation_id": CORR}
    for name in SUBJECT_FIELDS:
        value = getattr(source, name)
        subject[name] = list(value) if isinstance(value, tuple) else value
    text = json.dumps(subject, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _assert_not_intact(decision: object, *codes: str) -> EdgeEvidenceVerification:
    verification = verify_edge_kill_quarantine_decision(decision)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes
    assert {_code(code) for code in codes} <= set(verification.reason_codes), verification.reason_codes
    return verification


def _assert_shape(decision: EdgeKillQuarantineDecision) -> None:
    """Invariants every builder state satisfies (no re-proof)."""

    assert decision.kill_quarantine_decision_digest == edge_kill_quarantine_decision_digest(decision)
    ready = decision.status is EdgeEvidenceStatus.READY
    assert decision.advances is (ready and decision.gate_verdict is EdgeGateVerdict.PASS)
    target = {
        T.INITIAL_ACTIVATION: ACTIVE,
        T.KILL_DISABLE: DISABLED,
        T.QUARANTINE_ENTRY: QUARANTINE,
        T.GOVERNED_READMISSION: ACTIVE,
    }[decision.transition]
    assert decision.resulting_lifecycle_state is (target if decision.advances else None)
    assert decision.resulting_lifecycle_state_status == EDGE_RESULTING_LIFECYCLE_STATE_STATUS
    assert decision.kill_criteria_sealed is (ready and decision.sealed_kill_criteria_digest != "")
    assert decision.kill_criteria_lifecycle_stage == ("IMMUTABLE" if decision.sealed_kill_criteria_digest else "")
    assert {name: getattr(decision, name) for name, _ in EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS} == dict(
        EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS
    )
    assert decision.kill_observation_status == EDGE_KILL_OBSERVATION_STATUS
    assert decision.rule_set_digest == EDGE_KILL_QUARANTINE_RULE_SET_DIGEST
    assert decision.prior_digest == ("" if decision.prior_binding is None else decision.prior_binding.expected_digest)
    assert decision.admission_decision_digest == (
        "" if decision.admission_binding is None else decision.admission_binding.expected_digest
    )
    if ready:
        assert decision.integrity_reason_codes == ()
        assert decision.lifecycle_subject_digest == _subject_digest(decision)
    else:
        assert decision.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert decision.integrity_reason_codes and decision.verdict_reason_codes == ()
        assert (decision.lifecycle_subject_digest, decision.sealed_kill_criteria, decision.lifecycle_sequence) == (
            "",
            (),
            0,
        )
        assert not any(getattr(decision, name) for name in COMPUTED_FLAGS)


def _assert_receipt(decision: EdgeKillQuarantineDecision) -> None:
    """Shape plus a public re-proof, through the exact memo so a builder state already re-proven as a prior is not
    re-proven twice (the memo only ever returns the real verifier's result for this exact object)."""

    _assert_shape(decision)
    verification = _EF8_MEMOS["verify_edge_kill_quarantine_decision"](decision)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == decision.kill_quarantine_decision_digest
    assert edge_kill_quarantine_decision_payload_is_well_formed(json.loads(verification.canonical_json)) is True


def _assert_history_only(decision: EdgeKillQuarantineDecision) -> None:
    """Whatever its historical result, a receipt claims neither current paper admission nor the current head."""

    assert decision.resulting_lifecycle_state_status == EDGE_RESULTING_LIFECYCLE_STATE_STATUS
    assert {name: getattr(decision, name) for name in CURRENT_AUTHORITY_CLAIMS} == dict.fromkeys(
        CURRENT_AUTHORITY_CLAIMS, False
    )


# --- A. initial activation -----------------------------------------------------------------------------------------------


def test_authentic_passing_admission_records_a_historical_active_genesis_receipt() -> None:
    decision = genesis()
    ef7 = admission()
    _assert_receipt(decision)
    assert (decision.status, decision.gate_verdict, decision.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (decision.integrity_reason_codes, decision.verdict_reason_codes) == ((), ())
    assert (decision.transition, decision.prior_lifecycle_state, decision.resulting_lifecycle_state) == (
        T.INITIAL_ACTIVATION,
        None,
        ACTIVE,
    )
    assert (decision.prior_binding, decision.prior_digest, decision.prior_effective_at_ns) == (None, "", None)
    assert (decision.lifecycle_sequence, decision.lifecycle_cycle) == (0, 1)
    # The admission authority is the actual EF-7 decision, re-proven, and its authenticated EF-6 horizon.
    assert decision.admission_decision_digest == ef7.paper_admission_decision_digest
    assert decision.admission_decision_digest == edge_paper_admission_decision_digest(ef7)
    assert decision.admission_walk_forward_evidence_digest == ef6t.passed().walk_forward_oos_evidence_digest
    assert decision.admission_evaluation_horizon_end_ns == ADMISSION_HORIZON
    assert (
        decision.cycle_admission_decision_digest,
        decision.cycle_activated_at_ns,
        decision.cycle_disabled_at_ns,
    ) == (
        ef7.paper_admission_decision_digest,
        T_ACTIVATE,
        None,
    )
    assert decision.consumed_admission_decision_digests == (ef7.paper_admission_decision_digest,)
    assert decision.consumed_walk_forward_evidence_digests == (ef6t.passed().walk_forward_oos_evidence_digest,)
    # The immutable kill policy is exactly the EF-7 seal, recomputed independently.
    assert decision.sealed_kill_criteria == ef7.final_kill_criteria
    assert decision.final_kill_criteria_digest == edge_kill_criteria_digest(ef7.final_kill_criteria)
    assert decision.sealed_kill_criteria_digest == ef7.sealed_kill_criteria_digest
    assert decision.sealed_kill_criteria_digest == ef7t._digest(ef7t._expected_kill_criteria_record())
    assert decision.kill_criteria_combination_policy == "any_single_criterion_triggers_kill.v1"
    assert (decision.kill_criteria_lifecycle_stage, decision.kill_criteria_sealed) == ("IMMUTABLE", True)
    # The subject is the stable candidate identity of the EF-7 admission.
    for name in SUBJECT_FIELDS:
        assert getattr(decision, name) == getattr(ef7, name)
    assert decision.lifecycle_subject_digest == _subject_digest(ef7)
    assert decision.transition_reason_code == "initial_activation:authenticated_ef7_admission_with_sealed_kill_criteria"
    assert decision.transition_reason_reference == "admission-review-1"
    assert (decision.kill_observation, decision.kill_evaluation, decision.governance) == (None, None, None)
    # Lifecycle history only: the nested EF-7 is the historical admission evidence and EF-8 never re-grants it.
    assert ef7.candidate_admitted_to_paper is True
    _assert_history_only(decision)
    assert (decision.preregistration_sealed, decision.performance_data_consumed, decision.oos_evidence_consumed) == (
        True,
        True,
        True,
    )
    for flag in ("paper_performance_proven", "edge_proven", "profitability_proven", "capital_allocated", "live_ready"):
        assert getattr(decision, flag) is False
    assert decision.paper_only is True


def test_activation_is_deterministic_and_idempotent() -> None:
    again = activate(admission())
    assert again == genesis()
    assert edge_kill_quarantine_decision_to_dict(again) == edge_kill_quarantine_decision_to_dict(genesis())


@pytest.mark.parametrize(
    ("ef7", "verdict"),
    [
        (ef7t.cheap_approved, EdgeGateVerdict.FAIL),
        (ef7t.draft, EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL),
    ],
)
def test_non_advancing_admission_propagates_its_verdict_and_never_activates(ef7, verdict: EdgeGateVerdict) -> None:
    decision = activate(ef7())
    _assert_receipt(decision)
    assert (decision.status, decision.gate_verdict) == (EdgeEvidenceStatus.READY, verdict)
    assert decision.verdict_reason_codes == _codes(f"admission_not_advanced:{verdict.value}")
    assert (decision.resulting_lifecycle_state, decision.lifecycle_cycle, decision.candidate_admitted_to_paper) == (
        None,
        0,
        False,
    )
    assert (decision.sealed_kill_criteria, decision.sealed_kill_criteria_digest, decision.kill_criteria_sealed) == (
        (),
        "",
        False,
    )
    assert decision.consumed_admission_decision_digests == ()


@SLOW
def test_admission_needing_external_facts_propagates_and_never_activates() -> None:
    predecessor = ef6t.ef6("A", ("Asyn1",))
    first = ef7t.decide(predecessor)
    ef7 = ef7t.decide(predecessor, governance=ef7t.approval_for(first))
    assert ef7.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    decision = activate(ef7)
    _assert_receipt(decision)
    assert decision.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert decision.verdict_reason_codes == _codes("admission_not_advanced:NEEDS_EXTERNAL_FACTS")
    assert decision.resulting_lifecycle_state is None


def test_rejected_admission_is_rejected() -> None:
    rejected = ef7t.decide(ef6t.cheap(), correlation_id="corr-2")
    assert rejected.status is EdgeEvidenceStatus.REJECTED
    decision = activate(rejected, correlation_id="corr-2")
    _assert_receipt(decision)
    assert (decision.status, decision.integrity_reason_codes) == (
        EdgeEvidenceStatus.REJECTED,
        _codes("admission_rejected"),
    )


@pytest.mark.parametrize(
    ("overrides", "codes"),
    [
        ({"expected_admission_digest": "0" * 64}, ("admission_digest_mismatch",)),
        ({"expected_root_intake_digest": "f" * 64}, ("chain_splice_root_intake_mismatch",)),
        ({"correlation_id": "corr-2"}, ("admission_correlation_mismatch",)),
    ],
)
def test_admission_anchor_root_and_correlation_splices_are_rejected(
    overrides: dict[str, object], codes: tuple[str, ...]
) -> None:
    decision = activate(ef7t.cheap_approved(), **overrides)
    _assert_receipt(decision)
    assert decision.integrity_reason_codes == _codes(*codes)


def test_tampered_or_resealed_forged_admission_is_rejected() -> None:
    tampered = replace(ef7t.cheap_approved(), decision_id="ef7-tampered")
    decision = activate(tampered)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert _code("admission_integrity_failure:edge_paper_admission_decision:self_digest_mismatch") in (
        decision.integrity_reason_codes
    )
    genuine = ef7t.cheap_approved()
    forged = ef7t._reseal(
        genuine,
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
        candidate_admitted_to_paper=True,
        kill_criteria_sealed=True,
        kill_criteria_lifecycle_stage="SEALED",
        sealed_kill_criteria_digest=genuine.kill_criteria_record_digest,
    )
    decision = activate(forged)
    _assert_receipt(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("admission_integrity_failure:")) for code in decision.integrity_reason_codes)
    assert (decision.resulting_lifecycle_state, decision.candidate_admitted_to_paper) == (None, False)


def test_ef8_recomputes_the_seal_even_if_the_upstream_verifier_were_fooled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Defense in depth: a forged seal whose EF-7 digest is recomputed is refused by EF-8's own seal recomputation."""

    genuine = admission()
    weakened = tuple(replace(item, threshold="0.990000000000000000") for item in genuine.final_kill_criteria)
    forged = ef7t._reseal(
        genuine, final_kill_criteria=weakened, final_kill_criteria_digest=edge_kill_criteria_digest(weakened)
    )

    def fooled(decision: object) -> EdgeEvidenceVerification:
        return EdgeEvidenceVerification(True, (), edge_paper_admission_decision_digest(decision), "")  # type: ignore[arg-type]

    monkeypatch.setattr(ef8_module, "verify_edge_paper_admission_decision", fooled)
    decision = activate(forged)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert {
        _code("admission_sealed_kill_criteria_inconsistent:kill_criteria_record_digest"),
        _code("admission_sealed_kill_criteria_inconsistent:seal"),
    } <= set(decision.integrity_reason_codes)
    assert decision.sealed_kill_criteria == ()


def test_activation_cannot_precede_the_admission_evaluation_horizon() -> None:
    early = activate(admission(), effective_at_ns=ADMISSION_HORIZON - 1)
    _assert_shape(early)
    assert (early.gate_verdict, early.verdict_reason_codes) == (
        EdgeGateVerdict.FAIL,
        _codes("activation_before_admission_evaluation_horizon"),
    )
    assert early.resulting_lifecycle_state is None
    assert genesis().effective_at_ns == ADMISSION_HORIZON and genesis().advances is True


_BUILDER_PARAMETERS = {
    build_edge_kill_quarantine_initial_activation: {
        "admission",
        "expected_admission_digest",
        "expected_root_intake_digest",
        "effective_at_ns",
        "decision_id",
        "correlation_id",
        "reason_reference",
    },
    build_edge_kill_quarantine_kill_disable: {
        "prior",
        "expected_prior_digest",
        "expected_root_intake_digest",
        "kill_observation",
        "effective_at_ns",
        "decision_id",
        "correlation_id",
        "reason_reference",
    },
    build_edge_kill_quarantine_quarantine_entry: {
        "prior",
        "expected_prior_digest",
        "expected_root_intake_digest",
        "effective_at_ns",
        "decision_id",
        "correlation_id",
        "reason_reference",
    },
    build_edge_kill_quarantine_governed_readmission: {
        "prior",
        "expected_prior_digest",
        "expected_root_intake_digest",
        "revalidation",
        "expected_revalidation_digest",
        "effective_at_ns",
        "decision_id",
        "correlation_id",
        "reason_reference",
        "governance",
    },
}


@pytest.mark.parametrize("builder", list(_BUILDER_PARAMETERS))
def test_builders_accept_no_state_flag_criteria_or_threshold_input(builder) -> None:
    parameters = inspect.signature(builder).parameters
    assert set(parameters) == _BUILDER_PARAMETERS[builder]
    optional = {name for name, parameter in parameters.items() if parameter.default is not inspect.Parameter.empty}
    assert optional == ({"governance"} if builder is build_edge_kill_quarantine_governed_readmission else set())
    forbidden = ("state", "active", "flag", "criteria", "criterion", "threshold", "trigger", "sequence", "cycle")
    assert not [name for name in parameters if any(token in name for token in forbidden)]


def test_only_initial_activation_and_governed_readmission_can_ever_establish_active() -> None:
    matrix = edge_kill_quarantine_rule_set()["transition_matrix"]
    assert matrix == [
        "INITIAL_ACTIVATION:NONE->ACTIVE",
        "KILL_DISABLE:ACTIVE->DISABLED",
        "QUARANTINE_ENTRY:DISABLED->QUARANTINE",
        "GOVERNED_READMISSION:QUARANTINE->ACTIVE",
    ]
    assert [entry for entry in matrix if entry.endswith("->ACTIVE")] == [
        "INITIAL_ACTIVATION:NONE->ACTIVE",
        "GOVERNED_READMISSION:QUARANTINE->ACTIVE",
    ]
    assert set(inspect.signature(build_edge_kill_quarantine_initial_activation).parameters).isdisjoint(
        {"prior", "expected_prior_digest"}
    )


# --- B. kill evaluation and disable ------------------------------------------------------------------------------------


def _criterion(comparator: EdgeKillCriterionComparator, threshold: object) -> EdgeKillCriterion:
    return EdgeKillCriterion("c1", "max_drawdown", comparator, threshold, "rolling_30_utc_days")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("comparator", "expected"),
    [
        (EdgeKillCriterionComparator.KILL_IF_ABOVE, (False, False, True)),
        (EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE, (False, True, True)),
        (EdgeKillCriterionComparator.KILL_IF_BELOW, (True, False, False)),
        (EdgeKillCriterionComparator.KILL_IF_AT_OR_BELOW, (True, True, False)),
    ],
)
@pytest.mark.parametrize(
    ("below", "threshold", "above"),
    [
        ("0.249999999999999999", "0.250000000000000000", "0.250000000000000001"),
        ("-3.500000000000000001", "-3.500000000000000000", "-3.499999999999999999"),
        ("-0.000000000000000001", "0.000000000000000000", "0.000000000000000001"),
        ("9" * 41 + ".999999999999999997", "9" * 41 + ".999999999999999998", "9" * 41 + ".999999999999999999"),
    ],
)
def test_every_comparator_is_exact_just_below_at_and_just_above_the_threshold(
    comparator: EdgeKillCriterionComparator, expected: tuple[bool, bool, bool], below: str, threshold: str, above: str
) -> None:
    criterion = _criterion(comparator, threshold)
    assert (
        edge_kill_criterion_triggered(criterion, below),
        edge_kill_criterion_triggered(criterion, threshold),
        edge_kill_criterion_triggered(criterion, above),
    ) == expected


@pytest.mark.parametrize(
    ("criterion", "value", "code"),
    [
        (lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, None), "1.000000000000000000", "not_evaluable"),
        (lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.5"), "1.000000000000000000", "not_evaluable"),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "١.000000000000000000"),
            "1.000000000000000000",
            "not_evaluable",
        ),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "9" * 42 + "." + "0" * 18),
            "1.000000000000000000",
            "not_evaluable",
        ),
        (lambda: _criterion("kill_if_above", "1.000000000000000000"), "1.000000000000000000", "not_evaluable"),  # type: ignore[arg-type]
        (lambda: object.__new__(EdgeKillCriterion), "1.000000000000000000", "not_evaluable"),
        (object, "1.000000000000000000", "not_evaluable"),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.000000000000000000"),
            1.5,
            "observed_value_invalid",
        ),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.000000000000000000"),
            True,
            "observed_value_invalid",
        ),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.000000000000000000"),
            "1e5",
            "observed_value_invalid",
        ),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.000000000000000000"),
            "-0.000000000000000000",
            "observed_value_invalid",
        ),
        (
            lambda: _criterion(EdgeKillCriterionComparator.KILL_IF_ABOVE, "1.000000000000000000"),
            "NaN",
            "observed_value_invalid",
        ),
    ],
)
def test_the_evaluator_never_defaults_an_unevaluable_threshold_or_value(criterion, value: object, code: str) -> None:
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        edge_kill_criterion_triggered(criterion(), value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("criterion_id", "value", "triggered"),
    [
        (DRAWDOWN, "0.249999999999999999", False),
        (DRAWDOWN, "0.250000000000000000", True),
        (DRAWDOWN, "0.250000000000000001", True),
        (FUNDING_FLIP, "11.999999999999999999", False),
        (FUNDING_FLIP, "12.000000000000000000", False),
        (FUNDING_FLIP, "12.000000000000000001", True),
    ],
)
def test_a_sealed_criterion_disables_exactly_when_its_comparator_triggers(
    criterion_id: str, value: str, triggered: bool
) -> None:
    decision = disable(genesis(), observe(criterion_id, value))
    _assert_shape(decision)
    (criterion,) = [item for item in genesis().sealed_kill_criteria if item.criterion_id == criterion_id]
    evaluation = decision.kill_evaluation
    assert evaluation is not None
    assert (evaluation.criterion_id, evaluation.metric_id, evaluation.evaluation_basis) == (
        criterion.criterion_id,
        criterion.metric_id,
        criterion.evaluation_basis,
    )
    assert (evaluation.comparator, evaluation.threshold, evaluation.observed_value, evaluation.triggered) == (
        criterion.comparator,
        criterion.threshold,
        value,
        triggered,
    )
    assert evaluation.observation_digest == decision.kill_observation_digest
    if triggered:
        assert (decision.gate_verdict, decision.resulting_lifecycle_state) == (EdgeGateVerdict.PASS, DISABLED)
    else:
        assert decision.verdict_reason_codes == _codes(f"kill_criterion_not_triggered:{criterion_id}")
        assert (decision.gate_verdict, decision.resulting_lifecycle_state) == (EdgeGateVerdict.FAIL, None)
        assert decision.cycle_disabled_at_ns is None


def test_a_triggered_kill_disables_and_binds_the_exact_evaluation() -> None:
    decision = disabled()
    _assert_receipt(decision)
    assert (decision.gate_verdict, decision.transition, decision.prior_lifecycle_state) == (
        EdgeGateVerdict.PASS,
        T.KILL_DISABLE,
        ACTIVE,
    )
    assert (decision.resulting_lifecycle_state, decision.lifecycle_sequence, decision.lifecycle_cycle) == (
        DISABLED,
        1,
        1,
    )
    assert (decision.prior_digest, decision.prior_effective_at_ns) == (
        genesis().kill_quarantine_decision_digest,
        T_ACTIVATE,
    )
    assert (decision.cycle_activated_at_ns, decision.cycle_disabled_at_ns) == (T_ACTIVATE, T_KILL)
    assert decision.kill_observation == observe()
    observation_payload = {field.name: getattr(observe(), field.name) for field in fields(EdgeKillObservation)}
    assert decision.kill_observation_digest == _independent_digest({**observation_payload, "_": 0}, "_")
    assert decision.kill_evaluation == EdgeKillEvaluation(
        DRAWDOWN,
        "max_drawdown",
        "rolling_30_utc_days",
        EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
        "0.250000000000000000",
        "0.300000000000000000",
        decision.kill_observation_digest,
        True,
    )
    assert decision.transition_reason_code == f"kill_disable:sealed_kill_criterion_observation:{DRAWDOWN}"
    # The seal, subject and cycle authority are carried unchanged; nothing is admitted.
    for name in ("sealed_kill_criteria", "sealed_kill_criteria_digest", "lifecycle_subject_digest"):
        assert getattr(decision, name) == getattr(genesis(), name)
    assert decision.consumed_admission_decision_digests == genesis().consumed_admission_decision_digests
    assert (decision.candidate_admitted_to_paper, decision.kill_observation_verified) == (False, False)
    assert (decision.admission_binding, decision.admission_decision_digest) == (None, "")


@pytest.mark.parametrize(
    ("observation", "code"),
    [
        (
            lambda: observe("zz_unregistered_criterion"),
            "kill_observation_criterion_not_sealed:zz_unregistered_criterion",
        ),
        (lambda: observe(metric_id="negative_funding_hours"), f"kill_observation_metric_mismatch:{DRAWDOWN}"),
        (
            lambda: observe(evaluation_basis="rolling_7_utc_days"),
            f"kill_observation_evaluation_basis_mismatch:{DRAWDOWN}",
        ),
    ],
)
def test_no_unsealed_criterion_metric_or_basis_can_be_substituted(observation, code: str) -> None:
    decision = disable(genesis(), observation())
    _assert_shape(decision)
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (EdgeGateVerdict.FAIL, _codes(code))
    assert (decision.kill_evaluation, decision.resulting_lifecycle_state) == (None, None)


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"observed_value": "0.3"}, "kill_observation_observed_value_invalid"),
        ({"observed_value": 0.3}, "kill_observation_observed_value_invalid"),
        ({"observed_value": True}, "kill_observation_observed_value_invalid"),
        ({"observed_value": "+0.300000000000000000"}, "kill_observation_observed_value_invalid"),
        ({"observed_value": " 0.300000000000000000"}, "kill_observation_observed_value_invalid"),
        ({"observed_value": "Infinity"}, "kill_observation_observed_value_invalid"),
        ({"observed_value": "1" * 42 + "." + "0" * 18}, "kill_observation_observed_value_invalid"),
        ({"criterion_id": "Max_Drawdown"}, "kill_observation_criterion_id_invalid"),
        ({"metric_id": ""}, "kill_observation_metric_id_invalid"),
        ({"evaluation_basis": None}, "kill_observation_evaluation_basis_invalid"),
        ({"observation_reference": ""}, "kill_observation_reference_invalid"),
        ({"observation_reference": " report"}, "kill_observation_reference_invalid"),
        ({"observation_reference": "report\n1"}, "kill_observation_reference_invalid"),
        ({"observation_reference": "r" * 257}, "kill_observation_reference_invalid"),
        ({"observation_reference": "live venue feed"}, "forbidden_scope_token:kill_observation_reference"),
        ({"observation_reference": "bist report"}, "bist_scope_leakage:kill_observation_reference"),
        ({"observation_source_digest": "A" * 64}, "kill_observation_source_digest_invalid"),
    ],
)
def test_malformed_kill_observation_is_a_construction_error(changes: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        disable(cheap_genesis(), observe(**changes))


@pytest.mark.parametrize("observation", [lambda: None, object, lambda: object.__new__(EdgeKillObservation)])
def test_missing_or_hollow_observation_never_disables(observation) -> None:
    arguments = _common(
        {
            "expected_prior_digest": cheap_genesis().kill_quarantine_decision_digest,
            "kill_observation": observation(),
            "effective_at_ns": T_KILL,
            "decision_id": "ef8-disable",
            "reason_reference": "kill-review-1",
        }
    )
    with pytest.raises(EdgeKillQuarantineDecisionError, match="kill_observation"):
        build_edge_kill_quarantine_kill_disable(cheap_genesis(), **arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: {"kill_observation": replace(d.kill_observation, observed_value="0.100000000000000000")},
        lambda d: {"kill_evaluation": replace(d.kill_evaluation, triggered=False)},
        lambda d: {
            "sealed_kill_criteria": tuple(replace(c, threshold="0.990000000000000000") for c in d.sealed_kill_criteria)
        },
        lambda d: {"resulting_lifecycle_state": ACTIVE, "candidate_admitted_to_paper": True},
    ],
)
def test_resealed_kill_observation_evaluation_seal_or_state_never_verifies(tamper) -> None:
    """The authentic tampers that need a real triggered kill; the other derived fields are tampered on the cheap chain."""

    decision = disabled()
    _assert_not_intact(_reseal(decision, **tamper(decision)))


# --- C. the elapsed-time boundaries --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("elapsed", "passes"),
    [(29 * DAY, False), (30 * DAY, False), (30 * DAY + 1, True), (31 * DAY, True)],
)
def test_quarantine_needs_strictly_more_than_30_utc_days_since_the_disable(elapsed: int, passes: bool) -> None:
    decision = quarantine(disabled(), effective_at_ns=T_KILL + elapsed)
    _assert_shape(decision)
    if passes:
        assert (decision.gate_verdict, decision.resulting_lifecycle_state) == (EdgeGateVerdict.PASS, QUARANTINE)
    else:
        assert decision.verdict_reason_codes == _codes("quarantine_elapsed_not_more_than_30_utc_days")
        assert decision.resulting_lifecycle_state is None


def test_quarantine_entry_carries_the_disable_and_grants_nothing() -> None:
    decision = quarantined()
    _assert_receipt(decision)
    assert (decision.prior_lifecycle_state, decision.resulting_lifecycle_state) == (DISABLED, QUARANTINE)
    assert (decision.lifecycle_sequence, decision.lifecycle_cycle) == (2, 1)
    assert (decision.prior_effective_at_ns, decision.cycle_disabled_at_ns) == (T_KILL, T_KILL)
    assert decision.transition_reason_code == "quarantine_entry:disabled_more_than_30_utc_days"
    assert (decision.candidate_admitted_to_paper, decision.kill_observation, decision.governance) == (False, None, None)
    assert decision.sealed_kill_criteria_digest == genesis().sealed_kill_criteria_digest


@pytest.mark.parametrize(
    ("elapsed", "passes"),
    [(13 * DAY, False), (14 * DAY, True), (15 * DAY, True)],
)
def test_readmission_needs_at_least_14_utc_days_of_quarantine(elapsed: int, passes: bool) -> None:
    decision = (
        readmitted()
        if elapsed == 14 * DAY
        else readmit(quarantined(), revalidation(), effective_at_ns=T_QUARANTINE + elapsed)
    )
    _assert_shape(decision)
    if passes:
        assert (decision.gate_verdict, decision.resulting_lifecycle_state) == (EdgeGateVerdict.PASS, ACTIVE)
    else:
        assert decision.verdict_reason_codes == _codes("readmission_elapsed_less_than_14_utc_days")
        assert (decision.resulting_lifecycle_state, decision.candidate_admitted_to_paper) == (None, False)


@pytest.mark.parametrize(
    ("build", "codes"),
    [
        (lambda: disable(genesis(), effective_at_ns=T_ACTIVATE), ("transition_time_not_after_prior",)),
        (lambda: disable(genesis(), effective_at_ns=T_ACTIVATE - DAY), ("transition_time_not_after_prior",)),
        (
            lambda: quarantine(disabled(), effective_at_ns=T_KILL - DAY),
            ("quarantine_elapsed_not_more_than_30_utc_days", "transition_time_not_after_prior"),
        ),
    ],
)
def test_equal_or_reversed_coordinates_never_advance(build, codes: tuple[str, ...]) -> None:
    decision = build()
    _assert_shape(decision)
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (EdgeGateVerdict.FAIL, _codes(*codes))


@pytest.mark.parametrize("value", [True, False, -1, 2**63, 1.0 * T_KILL, str(T_KILL), None])
def test_coordinates_must_be_exact_int64_utc_nanoseconds(value: object) -> None:
    with pytest.raises(EdgeKillQuarantineDecisionError, match="effective_at_ns_invalid"):
        disable(cheap_genesis(), effective_at_ns=value)
    with pytest.raises(EdgeKillQuarantineDecisionError, match="effective_at_ns_invalid"):
        activate(ef7t.cheap_approved(), effective_at_ns=value)


def test_the_boundaries_are_committed_code_defined_rules() -> None:
    rules = edge_kill_quarantine_rule_set()
    assert EDGE_KILL_QUARANTINE_RULE_SET_DIGEST == ef7t._digest(rules)
    assert (rules["quarantine_min_elapsed_days_exclusive"], rules["readmission_min_elapsed_days_inclusive"]) == (30, 14)
    assert rules["utc_day_ns"] == DAY == 86_400_000_000_000
    assert (rules["observed_value_scale"], rules["observed_value_max_text_length"]) == (18, 60)
    assert rules["kill_criteria_combination_policy"] == "any_single_criterion_triggers_kill.v1"
    rules["quarantine_min_elapsed_days_exclusive"] = 0
    rules["transition_matrix"].append("KILL_DISABLE:DISABLED->ACTIVE")  # type: ignore[union-attr]
    assert edge_kill_quarantine_rule_set()["quarantine_min_elapsed_days_exclusive"] == 30
    assert len(edge_kill_quarantine_rule_set()["transition_matrix"]) == 4  # type: ignore[arg-type]
    assert genesis().rule_set_id == "edge_kill_quarantine_rules.v1"


def test_the_rule_set_commits_that_a_receipt_is_history_never_current_authority() -> None:
    rules = edge_kill_quarantine_rule_set()
    assert EDGE_KILL_QUARANTINE_RULE_SET_DIGEST == ef7t._digest(rules)
    assert rules["receipt_authority_rule_id"] == (
        "stateless_historical_transition_receipt_never_current_paper_admission_or_head.v1"
    )
    assert rules["resulting_lifecycle_state_status"] == EDGE_RESULTING_LIFECYCLE_STATE_STATUS
    assert rules["advances_rule_id"] == (
        "advances_is_valid_predecessor_for_the_next_receipt_of_this_exact_chain_never_current_head.v1"
    )
    assert (
        rules["lifecycle_head_rule_id"]
        == "no_head_authority_here_head_never_inferred_from_sequence_state_or_verdict.v1"
    )
    assert (
        rules["no_auto_reactivation_rule_id"] == "bound_chain_active_only_by_genesis_or_governed_fresh_readmission.v1"
    )
    # The committed current-authority claims are exactly the structural False non-claims every receipt carries.
    assert rules["current_authority_non_claims"] == list(CURRENT_AUTHORITY_CLAIMS)
    assert {
        name: dict(EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)[name] for name in CURRENT_AUTHORITY_CLAIMS
    } == dict.fromkeys(CURRENT_AUTHORITY_CLAIMS, False)
    assert "highest_sequence" not in edge_canonical_json(rules)


# --- D. no auto-reactivation, and a receipt is history, never current authority ---------------------------------------


def test_disabled_can_never_return_to_active_directly() -> None:
    decision = readmit(disabled(), revalidation())
    _assert_shape(decision)
    assert decision.verdict_reason_codes == _codes("transition_not_allowed:DISABLED->ACTIVE")
    assert (decision.resulting_lifecycle_state, decision.candidate_admitted_to_paper) == (None, False)


@pytest.mark.parametrize("effective", [T_READMIT, T_QUARANTINE + 1000 * DAY])
def test_the_killed_admission_can_never_readmit_even_with_approval_and_any_elapsed_time(effective: int) -> None:
    decision = readmit(quarantined(), admission(), effective_at_ns=effective)
    _assert_shape(decision)
    assert decision.verdict_reason_codes == _codes(
        "revalidation_admission_reused",
        "revalidation_horizon_not_after_disable",
        "revalidation_walk_forward_evidence_reused",
    )
    assert (decision.gate_verdict, decision.resulting_lifecycle_state) == (EdgeGateVerdict.FAIL, None)


@pytest.mark.parametrize(
    ("build", "codes"),
    [
        (
            lambda: disable(disabled(), observe(value="0.100000000000000000"), effective_at_ns=T_KILL + DAY),
            ("transition_not_allowed:DISABLED->DISABLED", f"kill_criterion_not_triggered:{DRAWDOWN}"),
        ),
        (
            lambda: disable(quarantined(), observe(value="0.100000000000000000"), effective_at_ns=T_QUARANTINE + DAY),
            ("transition_not_allowed:QUARANTINE->DISABLED", f"kill_criterion_not_triggered:{DRAWDOWN}"),
        ),
        (
            lambda: quarantine(quarantined(), effective_at_ns=T_QUARANTINE + 1000 * DAY),
            ("transition_not_allowed:QUARANTINE->QUARANTINE",),
        ),
    ],
)
def test_metric_recovery_or_elapsed_time_alone_never_reactivates(build, codes: tuple[str, ...]) -> None:
    decision = build()
    _assert_shape(decision)
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (EdgeGateVerdict.FAIL, _codes(*codes))
    assert (decision.resulting_lifecycle_state, decision.candidate_admitted_to_paper) == (None, False)


@pytest.mark.parametrize(
    ("revalidation", "code"),
    [
        (lambda: None, "revalidation_malformed"),
        (lambda: ef7t.admitted().paper_admission_decision_digest, "revalidation_malformed"),
        (ef6t.cheap, "revalidation_malformed"),
        (lambda: object.__new__(EdgePaperAdmissionDecision), "revalidation_not_serializable"),
    ],
)
def test_readmission_requires_an_actual_revalidation_decision(revalidation, code: str) -> None:
    arguments = _common(
        {
            "expected_prior_digest": cheap_genesis().kill_quarantine_decision_digest,
            "revalidation": revalidation(),
            "expected_revalidation_digest": "c" * 64,
            "effective_at_ns": T_READMIT,
            "decision_id": "ef8-readmit",
            "reason_reference": "readmission-review-1",
        }
    )
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        build_edge_kill_quarantine_governed_readmission(cheap_genesis(), **arguments)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "changes",
    [
        {"resulting_lifecycle_state": ACTIVE},
        {"gate_verdict": EdgeGateVerdict.PASS, "advances": True, "verdict_reason_codes": ()},
        {"candidate_admitted_to_paper": True},
        {"transition": T.GOVERNED_READMISSION},
    ],
)
def test_a_caller_can_never_forge_an_active_state(changes: dict[str, object]) -> None:
    _assert_not_intact(_reseal(cheap_genesis(), **changes))


def test_a_second_genesis_after_a_kill_over_the_old_admission_grants_no_current_authority() -> None:
    """Astra P1 EF8_POSITIVE_ACTIVATION_WITHOUT_AUTHORITATIVE_LIFECYCLE_CONTEXT: G0 → D1, then G0b over the SAME EF-7.

    Stateless EF-8 cannot see D1, so G0b stays a deterministic historical INITIAL_ACTIVATION receipt. It never becomes
    current paper admission or the current head, and it is no successor of the kill, so it bypasses no revalidation.
    """

    g0, d1, g0b = genesis(), disabled(), second_genesis()
    assert (d1.resulting_lifecycle_state, d1.prior_digest) == (DISABLED, g0.kill_quarantine_decision_digest)
    _assert_receipt(g0b)
    assert (g0b.status, g0b.gate_verdict, g0b.advances, g0b.resulting_lifecycle_state) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
        ACTIVE,
    )
    # No current authority: not paper admission, not the head, not a reactivation; forging either never verifies.
    _assert_history_only(g0b)
    _assert_not_intact(
        _reseal(g0b, candidate_admitted_to_paper=True, current_lifecycle_head_proven=True),
        "field_mismatch:candidate_admitted_to_paper",
        "field_mismatch:current_lifecycle_head_proven",
    )
    # No successor of D1: no prior, sequence 0, the same subject, and nothing but its coordinate and id differs from G0,
    # so nothing in either receipt can say which one is current.
    assert (g0b.prior_binding, g0b.prior_digest, g0b.prior_lifecycle_state, g0b.lifecycle_sequence) == (
        None,
        "",
        None,
        0,
    )
    assert g0b.lifecycle_subject_digest == g0.lifecycle_subject_digest == d1.lifecycle_subject_digest
    differing = {
        item.name for item in fields(EdgeKillQuarantineDecision) if getattr(g0b, item.name) != getattr(g0, item.name)
    }
    assert differing == {"decision_id", "effective_at_ns", "cycle_activated_at_ns", _SELF}
    # Reusing the old EF-7 bypasses no governed revalidation: any chain from G0b has already consumed it, and the
    # killed chain re-admits only on a fresh revalidation.
    assert g0b.consumed_admission_decision_digests == (admission().paper_admission_decision_digest,)
    reused = readmit(quarantined(), admission())
    assert reused.verdict_reason_codes == _codes(
        "revalidation_admission_reused",
        "revalidation_horizon_not_after_disable",
        "revalidation_walk_forward_evidence_reused",
    )
    assert (reused.advances, reused.resulting_lifecycle_state) == (False, None)


def test_a_genesis_over_a_passing_revalidation_is_no_governed_readmission_and_grants_nothing() -> None:
    """The same P1 through the fresh EF-7: rerooting on it skips quarantine and governance, so it re-admits nothing."""

    rerooted = activate(revalidation(), effective_at_ns=T_READMIT, decision_id="ef8-reroot")
    _assert_receipt(rerooted)
    assert (rerooted.transition, rerooted.advances, rerooted.resulting_lifecycle_state) == (
        T.INITIAL_ACTIVATION,
        True,
        ACTIVE,
    )
    _assert_history_only(rerooted)
    # It binds neither the kill nor the quarantine, carries no approval and opens its own first cycle.
    assert (rerooted.prior_digest, rerooted.governance, rerooted.lifecycle_sequence, rerooted.lifecycle_cycle) == (
        "",
        None,
        0,
        1,
    )
    assert rerooted.consumed_admission_decision_digests == (revalidation().paper_admission_decision_digest,)
    assert rerooted.lifecycle_subject_digest == quarantined().lifecycle_subject_digest


def test_the_stale_original_genesis_stays_valid_history_after_its_disable_and_proves_no_current_state() -> None:
    g0, d1 = genesis(), disabled()
    assert (d1.prior_digest, d1.advances, d1.resulting_lifecycle_state) == (
        g0.kill_quarantine_decision_digest,
        True,
        DISABLED,
    )
    # Presented after D1, G0 still re-proves: a successor never rewrites history ...
    _assert_receipt(g0)
    assert (g0.advances, g0.resulting_lifecycle_state, g0.lifecycle_sequence) == (True, ACTIVE, 0)
    # ... but G0's ACTIVE is the historical result of its own transition; neither G0 nor D1 is proven current.
    for receipt in (g0, d1):
        _assert_history_only(receipt)


def test_forked_children_are_each_valid_history_and_none_alone_proves_the_current_head() -> None:
    """Stateless evidence admits siblings: two kills of one genesis, and two genesis receipts over one EF-7."""

    first, second = disabled(), forked_disable()
    for child in (first, second):
        _assert_receipt(child)
        assert (child.prior_digest, child.lifecycle_sequence, child.resulting_lifecycle_state) == (
            genesis().kill_quarantine_decision_digest,
            1,
            DISABLED,
        )
        _assert_history_only(child)
    assert first.kill_quarantine_decision_digest != second.kill_quarantine_decision_digest
    triggered = {child.kill_evaluation.criterion_id for child in (first, second)}  # type: ignore[union-attr]
    assert triggered == {DRAWDOWN, FUNDING_FLIP}
    for sibling in (genesis(), second_genesis()):
        _assert_receipt(sibling)
        assert (sibling.prior_digest, sibling.lifecycle_sequence, sibling.resulting_lifecycle_state) == ("", 0, ACTIVE)
        _assert_history_only(sibling)
    assert genesis().kill_quarantine_decision_digest != second_genesis().kill_quarantine_decision_digest


# --- E. governed revalidation from EF-5 onward ---------------------------------------------------------------------------


def test_governed_fresh_revalidation_readmits_as_a_new_cycle_under_the_same_seal() -> None:
    decision = readmitted()
    reval = revalidation()
    _assert_receipt(decision)
    assert (decision.gate_verdict, decision.transition) == (EdgeGateVerdict.PASS, T.GOVERNED_READMISSION)
    assert (decision.prior_lifecycle_state, decision.resulting_lifecycle_state) == (QUARANTINE, ACTIVE)
    assert (decision.lifecycle_sequence, decision.lifecycle_cycle) == (3, 2)
    assert (decision.prior_digest, decision.prior_effective_at_ns) == (
        quarantined().kill_quarantine_decision_digest,
        T_QUARANTINE,
    )
    # The revalidation is genuinely new evidence from EF-5 onward.
    assert reval.preregistration_digest == admission().preregistration_digest  # EF-5 re-proven unchanged
    assert reval.predecessor_digest != admission().predecessor_digest  # a new EF-6
    assert reval.evaluation_frame_digest != admission().evaluation_frame_digest  # a new frame
    assert reval.paper_admission_decision_digest != admission().paper_admission_decision_digest  # a new EF-7
    assert decision.admission_decision_digest == reval.paper_admission_decision_digest
    assert decision.admission_walk_forward_evidence_digest == revalidation_evidence().walk_forward_oos_evidence_digest
    assert decision.admission_evaluation_horizon_end_ns == REVALIDATION_HORIZON
    assert T_KILL < REVALIDATION_HORIZON <= T_READMIT
    assert (
        decision.cycle_admission_decision_digest,
        decision.cycle_activated_at_ns,
        decision.cycle_disabled_at_ns,
    ) == (
        reval.paper_admission_decision_digest,
        T_READMIT,
        None,
    )
    assert decision.consumed_admission_decision_digests == (
        admission().paper_admission_decision_digest,
        reval.paper_admission_decision_digest,
    )
    assert decision.consumed_walk_forward_evidence_digests == (
        ef6t.passed().walk_forward_oos_evidence_digest,
        revalidation_evidence().walk_forward_oos_evidence_digest,
    )
    # The killed candidate's seal is never replaced.
    for name in ("sealed_kill_criteria", "final_kill_criteria_digest", "sealed_kill_criteria_digest"):
        assert getattr(decision, name) == getattr(genesis(), name)
    assert reval.sealed_kill_criteria_digest == genesis().sealed_kill_criteria_digest
    assert decision.lifecycle_subject_digest == genesis().lifecycle_subject_digest == _subject_digest(reval)
    assert decision.governance == approval_for(quarantined(), reval)
    # A valid historical re-admission receipt: never current paper admission or the current head.
    _assert_history_only(decision)
    assert decision.transition_reason_code.startswith("governed_readmission:quarantine_at_least_14_utc_days")


def test_a_governed_readmission_is_valid_history_that_never_proves_current_authority() -> None:
    decision = readmitted()
    _assert_receipt(decision)
    assert (decision.advances, decision.resulting_lifecycle_state, decision.lifecycle_cycle) == (True, ACTIVE, 2)
    _assert_history_only(decision)
    # Its quarantine prior stays valid history after the re-admission and claims nothing current either.
    _assert_receipt(quarantined())
    _assert_history_only(quarantined())
    # Forging current paper admission or the current head onto the authentic re-admission never verifies.
    _assert_not_intact(
        _reseal(decision, candidate_admitted_to_paper=True, current_lifecycle_head_proven=True),
        "field_mismatch:candidate_admitted_to_paper",
        "field_mismatch:current_lifecycle_head_proven",
    )


def test_readmission_without_governance_needs_approval_and_grants_nothing() -> None:
    decision = readmission_draft()
    _assert_shape(decision)  # a READY non-advancing readmission is re-proven on the cheap lifecycle
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        _codes("readmission_governance_missing"),
    )
    assert (decision.resulting_lifecycle_state, decision.lifecycle_cycle, decision.candidate_admitted_to_paper) == (
        None,
        1,
        False,
    )
    assert decision.consumed_admission_decision_digests == quarantined().consumed_admission_decision_digests
    assert (decision.governance, decision.governance_digest) == (None, "")


def test_pre_kill_evaluation_evidence_cannot_readmit_even_under_new_digests() -> None:
    stale = pre_kill_revalidation()
    assert stale.gate_verdict is EdgeGateVerdict.PASS
    assert stale.paper_admission_decision_digest not in quarantined().consumed_admission_decision_digests
    assert stale.predecessor_digest not in quarantined().consumed_walk_forward_evidence_digests
    decision = readmit(quarantined(), stale)
    _assert_shape(decision)
    assert decision.verdict_reason_codes == _codes("revalidation_horizon_not_after_disable")
    assert decision.resulting_lifecycle_state is None


def test_non_passing_revalidation_propagates_and_cannot_readmit() -> None:
    decision = readmit(quarantined(), revalidation_draft())
    _assert_shape(decision)
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        _codes("revalidation_not_advanced:NEEDS_GOVERNANCE_APPROVAL"),
    )
    assert decision.resulting_lifecycle_state is None


def _other_spec_revalidation() -> EdgePaperAdmissionDecision:
    other = ef6t.ef6("A", (), world_name="spec", governance=ef6t.governance_for(ef6t._draft("A", (), "spec")))
    return ef7t.decide(other)


def _other_sleeve_revalidation() -> EdgePaperAdmissionDecision:
    policy = ef7t.budget_policy(sleeve_id="basis-sleeve-2")
    return ef7t.decide(
        ef6t.cheap(),
        paper_sleeve_id="basis-sleeve-2",
        risk_budget_policy=policy,
        expected_risk_budget_policy_digest=policy.policy_digest,
    )


@pytest.mark.parametrize(
    ("revalidation", "overrides", "codes"),
    [
        (
            _other_spec_revalidation,
            {},
            (
                "revalidation_identity_mismatch:strategy_spec_admission_digest",
                "revalidation_identity_mismatch:strategy_spec_digest",
                "revalidation_identity_mismatch:strategy_version",
                "revalidation_sealed_kill_criteria_mismatch",
            ),
        ),
        (_other_sleeve_revalidation, {}, ("revalidation_identity_mismatch:paper_sleeve_id",)),
        (lambda: ef7t.decide(ef7t.ef6_rejected(), correlation_id="corr-2"), {}, ("revalidation_correlation_mismatch",)),
        (revalidation, {"expected_revalidation_digest": "0" * 64}, ("revalidation_digest_mismatch",)),
    ],
)
def test_a_revalidation_of_another_subject_chain_or_anchor_is_rejected(
    revalidation, overrides: dict[str, object], codes: tuple[str, ...]
) -> None:
    decision = readmit(quarantined(), revalidation(), **overrides)
    _assert_shape(decision)
    assert (decision.status, decision.integrity_reason_codes) == (EdgeEvidenceStatus.REJECTED, _codes(*codes))
    assert decision.resulting_lifecycle_state is None


def test_a_tampered_revalidation_is_rejected() -> None:
    tampered = replace(ef7t.cheap_approved(), decision_id="ef7-tampered")
    decision = readmit(cheap_genesis(), tampered, governance=None)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert _code("revalidation_integrity_failure:edge_paper_admission_decision:self_digest_mismatch") in (
        decision.integrity_reason_codes
    )


@SLOW
def test_the_readmitted_cycle_is_killed_by_the_same_seal_and_its_revalidation_is_then_consumed() -> None:
    killed = disable(readmitted(), effective_at_ns=T_READMIT + DAY, decision_id="ef8-disable-2")
    _assert_receipt(killed)
    assert (killed.resulting_lifecycle_state, killed.lifecycle_sequence, killed.lifecycle_cycle) == (DISABLED, 4, 2)
    assert killed.sealed_kill_criteria_digest == genesis().sealed_kill_criteria_digest
    again = quarantine(killed, effective_at_ns=T_READMIT + 40 * DAY, decision_id="ef8-quarantine-2")
    assert again.resulting_lifecycle_state is QUARANTINE
    reused = readmit(again, revalidation(), effective_at_ns=T_READMIT + 60 * DAY)
    assert reused.verdict_reason_codes == _codes(
        "revalidation_admission_reused",
        "revalidation_horizon_not_after_disable",
        "revalidation_walk_forward_evidence_reused",
    )


# --- F. governance -------------------------------------------------------------------------------------------------------


def test_every_approval_commitment_must_match_exactly() -> None:
    wrong: dict[str, object] = {f"approved_{name}": "a" * 64 for name in COMMITMENTS if name != "effective_at_ns"}
    wrong["approved_effective_at_ns"] = T_READMIT + 1
    decision = readmit(quarantined(), revalidation(), governance=approval_for(quarantined(), revalidation(), **wrong))
    _assert_shape(decision)
    assert (decision.gate_verdict, decision.verdict_reason_codes) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        _codes(*(f"readmission_governance_{name}_mismatch" for name in COMMITMENTS)),
    )
    assert decision.resulting_lifecycle_state is None


def test_an_approval_from_another_lifecycle_chain_cannot_be_replayed() -> None:
    fork = quarantine(forked_disable(), decision_id="ef8-quarantine-b")
    assert fork.resulting_lifecycle_state is QUARANTINE
    assert fork.lifecycle_subject_digest == quarantined().lifecycle_subject_digest
    decision = readmit(fork, revalidation(), governance=approval_for(quarantined(), revalidation()))
    _assert_shape(decision)
    assert decision.verdict_reason_codes == _codes("readmission_governance_prior_lifecycle_digest_mismatch")
    assert decision.resulting_lifecycle_state is None


def test_a_rule_set_change_invalidates_old_approvals_and_old_artifacts(monkeypatch: pytest.MonkeyPatch) -> None:
    approval = approval_for(quarantined(), revalidation())
    # The prior re-proven under the rules that governed it (served by the exact memo below, as a later chain would).
    assert _EF8_MEMOS["verify_edge_kill_quarantine_decision"](quarantined()).intact is True
    monkeypatch.setattr(ef8_module, "EDGE_KILL_QUARANTINE_RULE_SET_DIGEST", ef7t._digest({"rule_set_id": "rules.v2"}))
    decision = readmit(quarantined(), revalidation(), governance=approval)
    assert _code("readmission_governance_rule_set_digest_mismatch") in decision.verdict_reason_codes
    assert decision.resulting_lifecycle_state is None
    # Re-proven for real under the changed rules, an artifact committed to the old rule set never verifies.
    _assert_not_intact(quarantined(), "field_mismatch:rule_set_digest")


def test_governance_digest_commits_the_exact_approval_record() -> None:
    decision = readmitted()
    record = {field.name: getattr(decision.governance, field.name) for field in fields(EdgeReadmissionGovernance)}
    assert decision.governance_digest == ef7t._digest(record)


@pytest.mark.parametrize(
    ("governance", "code"),
    [
        (object, "governance_malformed"),
        (lambda: object.__new__(EdgeReadmissionGovernance), "governance_approval_reference_invalid"),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approval_digest="E" * 64),
            "governance_approval_digest_invalid",
        ),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approval_reference=""),
            "governance_approval_reference_invalid",
        ),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approval_reference="live approval"),
            "forbidden_scope_token:governance_approval_reference",
        ),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approved_effective_at_ns=True),
            "governance_approved_effective_at_ns_invalid",
        ),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approved_effective_at_ns=-1),
            "governance_approved_effective_at_ns_invalid",
        ),
        (
            lambda: approval_for(cheap_genesis(), ef7t.cheap_approved(), approved_rule_set_digest=None),
            "governance_approved_rule_set_digest_invalid",
        ),
    ],
)
def test_malformed_governance_is_a_construction_error(governance, code: str) -> None:
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        readmit(cheap_genesis(), ef7t.cheap_approved(), governance=governance())


# --- G. the lifecycle chain ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "codes"),
    [
        ({"expected_prior_digest": "0" * 64}, ("prior_lifecycle_digest_mismatch",)),
        ({"expected_root_intake_digest": "f" * 64}, ("chain_splice_root_intake_mismatch",)),
        ({"correlation_id": "corr-2"}, ("prior_lifecycle_correlation_mismatch",)),
    ],
)
def test_prior_anchor_root_and_correlation_splices_are_rejected(
    overrides: dict[str, object], codes: tuple[str, ...]
) -> None:
    decision = quarantine(cheap_genesis(), **overrides)
    _assert_receipt(decision)
    assert decision.integrity_reason_codes == _codes(*codes)


def test_a_tampered_prior_is_rejected_and_a_rejected_prior_propagates_rejection() -> None:
    tampered = replace(cheap_genesis(), decision_id="ef8-tampered")
    decision = quarantine(tampered)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert _code("prior_lifecycle_integrity_failure:edge_kill_quarantine_decision:self_digest_mismatch") in (
        decision.integrity_reason_codes
    )
    rejected = activate(ef7t.cheap_approved(), correlation_id="corr-2")
    assert rejected.status is EdgeEvidenceStatus.REJECTED
    successor = quarantine(rejected, correlation_id="corr-2")
    _assert_receipt(successor)
    assert successor.integrity_reason_codes == _codes("prior_lifecycle_rejected")


def test_a_resealed_forged_prior_state_cannot_skip_the_quarantine_clock() -> None:
    forged = _reseal(disabled(), resulting_lifecycle_state=QUARANTINE)
    decision = readmit(forged, revalidation())
    _assert_shape(decision)
    assert decision.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("prior_lifecycle_integrity_failure:")) for code in decision.integrity_reason_codes)


def test_a_prior_forged_into_another_transition_type_is_refused_at_construction() -> None:
    forged = _reseal(disabled(), transition=T.QUARANTINE_ENTRY, resulting_lifecycle_state=QUARANTINE)
    with pytest.raises(EdgeKillQuarantineDecisionError, match="prior_lifecycle_not_serializable"):
        readmit(forged, revalidation())


def test_a_nested_prior_mutation_resealed_through_the_chain_is_re_judged() -> None:
    """A resealed nested disable moved later is itself valid, so the outer quarantine is re-judged as too early."""

    payload = _payload(quarantined())
    nested = payload["prior_binding"]["snapshot"]
    nested["effective_at_ns"] = T_KILL + 5 * DAY
    nested["cycle_disabled_at_ns"] = T_KILL + 5 * DAY
    nested[_SELF] = edge_payload_digest(nested, _SELF)
    payload["prior_binding"]["expected_digest"] = payload["prior_digest"] = nested[_SELF]
    _assert_not_intact(_resealed(payload), "field_mismatch:gate_verdict", "field_mismatch:resulting_lifecycle_state")


def test_a_nested_seal_mutation_resealed_through_the_chain_never_verifies() -> None:
    payload = _payload(disabled())
    nested = payload["prior_binding"]["snapshot"]
    for criterion in nested["sealed_kill_criteria"]:
        criterion["threshold"] = "0.990000000000000000"
    nested[_SELF] = edge_payload_digest(nested, _SELF)
    payload["prior_binding"]["expected_digest"] = payload["prior_digest"] = nested[_SELF]
    _assert_not_intact(_resealed(payload), "field_mismatch:status")


def test_a_nested_revalidation_mutation_resealed_through_the_chain_never_verifies() -> None:
    payload = _payload(cheap_readmission())
    ef7 = payload["admission_binding"]["snapshot"]
    ef7["paper_sleeve_id"] = "basis-sleeve-2"
    ef7["paper_admission_decision_digest"] = edge_payload_digest(ef7, "paper_admission_decision_digest")
    payload["admission_binding"]["expected_digest"] = ef7["paper_admission_decision_digest"]
    payload["admission_decision_digest"] = ef7["paper_admission_decision_digest"]
    _assert_not_intact(_resealed(payload), "field_mismatch:status")


@pytest.mark.parametrize(
    "tamper",
    [
        lambda d: {"transition_reason_code": "kill_disable:sealed_kill_criterion_observation:other"},
        lambda d: {"lifecycle_sequence": 7},
        lambda d: {"lifecycle_cycle": 1},
        lambda d: {"lifecycle_subject_digest": "0" * 64},
        lambda d: {"candidate_strategy_id": "other-candidate"},
        lambda d: {"pinned_instrument_universe": ("ETH-USDT-PERP",)},
        lambda d: {"prior_effective_at_ns": T_KILL},
        lambda d: {"consumed_admission_decision_digests": ("c" * 64,)},
        lambda d: {"verdict_reason_codes": ()},
        lambda d: {"integrity_reason_codes": (_code("forged"),)},
        lambda d: {"kill_criteria_sealed": True},
        lambda d: {"rule_set_digest": "0" * 64},
        lambda d: {"kill_observation_status": "VERIFIED_PERFORMANCE"},
        lambda d: {"resulting_lifecycle_state_status": "CURRENT_LIFECYCLE_HEAD"},
        lambda d: {"kill_observation_digest": "0" * 64},
        lambda d: {"sealed_kill_criteria_digest": "0" * 64},
        lambda d: {"cycle_disabled_at_ns": T_KILL},
        lambda d: {"effective_at_ns": T_ACTIVATE},
        lambda d: {
            "kill_evaluation": EdgeKillEvaluation(
                DRAWDOWN,
                "max_drawdown",
                "rolling_30_utc_days",
                EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
                "0.250000000000000000",
                "0.300000000000000000",
                d.kill_observation_digest,
                True,
            )
        },
    ],
)
def test_resealed_derived_fields_never_verify(tamper) -> None:
    decision = cheap_disable()
    _assert_not_intact(_reseal(decision, **tamper(decision)))


def test_self_digest_or_reason_tamper_without_reseal_never_verifies() -> None:
    _assert_not_intact(replace(cheap_disable(), kill_quarantine_decision_digest="0" * 64), "self_digest_mismatch")
    _assert_not_intact(replace(cheap_disable(), transition_reason_reference="kill-review-2"), "self_digest_mismatch")


def test_a_successor_binds_the_exact_prior_including_its_reason() -> None:
    """A resealed prior with another reason is a different artifact: the original anchor refuses it."""

    other = _reseal(cheap_genesis(), transition_reason_reference="admission-review-2")
    assert verify_edge_kill_quarantine_decision(other).intact is True
    decision = quarantine(other, expected_prior_digest=cheap_genesis().kill_quarantine_decision_digest)
    assert decision.integrity_reason_codes == _codes("prior_lifecycle_digest_mismatch")


@pytest.mark.parametrize(
    ("prior", "code"),
    [
        (lambda: object.__new__(EdgeKillQuarantineDecision), "prior_lifecycle_not_serializable"),
        (ef7t.cheap_approved, "prior_lifecycle_malformed"),
        (lambda: None, "prior_lifecycle_malformed"),
        (lambda: edge_kill_quarantine_decision_to_dict(cheap_genesis()), "prior_lifecycle_malformed"),
    ],
)
def test_malformed_or_hollow_prior_is_a_construction_error(prior, code: str) -> None:
    arguments = _common(
        {
            "expected_prior_digest": cheap_genesis().kill_quarantine_decision_digest,
            "effective_at_ns": T_QUARANTINE,
            "decision_id": "ef8-quarantine",
            "reason_reference": "quarantine-review-1",
        }
    )
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        build_edge_kill_quarantine_quarantine_entry(prior(), **arguments)  # type: ignore[arg-type]


# --- H. the cheap lifecycle: every transition's non-advancing structure --------------------------------------------------


@pytest.mark.parametrize(
    ("build", "codes"),
    [
        (cheap_genesis, ("admission_not_advanced:FAIL",)),
        (
            cheap_disable,
            ("kill_observation_criterion_not_sealed:max_drawdown_breach", "prior_lifecycle_not_advanced:FAIL"),
        ),
        (cheap_quarantine, ("prior_lifecycle_not_advanced:FAIL",)),
        (
            cheap_readmission,
            ("prior_lifecycle_not_advanced:FAIL", "readmission_governance_missing", "revalidation_not_advanced:FAIL"),
        ),
    ],
)
def test_a_non_advancing_prior_is_never_a_lifecycle_state(build, codes: tuple[str, ...]) -> None:
    decision = build()
    _assert_receipt(decision)
    assert (decision.status, decision.gate_verdict, decision.verdict_reason_codes) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.FAIL,
        _codes(*codes),
    )
    assert (decision.resulting_lifecycle_state, decision.sealed_kill_criteria) == (None, ())
    if decision.prior_binding is not None:
        assert decision.prior_lifecycle_state is None
        assert decision.lifecycle_sequence == 1


# --- I. serialization and totality ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("build", [cheap_genesis, cheap_disable, cheap_quarantine, cheap_readmission, genesis])
def test_round_trip_and_independent_digest_for_every_transition(build) -> None:
    decision = build()
    payload = _payload(decision)
    assert edge_kill_quarantine_decision_from_payload(payload) == decision
    assert edge_kill_quarantine_decision_payload_is_well_formed(payload) is True
    assert payload[_SELF] == _independent_digest(payload, _SELF) == decision.kill_quarantine_decision_digest


def test_decision_and_records_are_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        cheap_genesis().status = EdgeEvidenceStatus.READY  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        observe().observed_value = "1.000000000000000000"  # type: ignore[misc]


def _governance_payload() -> dict:
    return {
        field.name: getattr(approval_for(cheap_genesis(), ef7t.cheap_approved()), field.name)
        for field in fields(EdgeReadmissionGovernance)
    }


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), None),
        (("status",), "ready"),
        (("advances",), 1),
        (("transition",), "RESUME"),
        (("transition",), "INITIAL_ACTIVATION"),
        (("prior_lifecycle_state",), "LIVE"),
        (("resulting_lifecycle_state",), 1),
        (("resulting_lifecycle_state_status",), None),
        (("resulting_lifecycle_state_status",), _UNSET),
        (("effective_at_ns",), True),
        (("effective_at_ns",), -1),
        (("effective_at_ns",), 2**63),
        (("effective_at_ns",), 1.0),
        (("effective_at_ns",), "1"),
        (("prior_effective_at_ns",), False),
        (("lifecycle_sequence",), True),
        (("lifecycle_cycle",), -1),
        (("pinned_instrument_universe",), "BTC-USDT-PERP"),
        (("consumed_admission_decision_digests",), "x"),
        (("sealed_kill_criteria",), [{}]),
        (("kill_observation",), None),
        (("kill_observation",), {}),
        (("kill_observation", "observed_value"), 0.3),
        (("kill_observation", "extra"), "x"),
        (("kill_evaluation",), {"triggered": True}),
        (("governance",), "_governance"),
        (("admission_binding",), "_admission"),
        (("prior_binding",), None),
        (("prior_binding", "snapshot"), {}),
        (("prior_binding", "snapshot", "status"), "WINNER"),
        (("prior_binding", "expected_digest"), "A" * 64),
        (("paper_only",), "true"),
        (("candidate_admitted_to_paper",), 0),
        (("current_lifecycle_head_proven",), _UNSET),
        (("unexpected_field",), "x"),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = _payload(cheap_disable())
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    elif value == "_governance":
        node[path[-1]] = _governance_payload()
    elif value == "_admission":
        node[path[-1]] = _payload(cheap_genesis())["admission_binding"]
    else:
        node[path[-1]] = value
    assert edge_kill_quarantine_decision_payload_is_well_formed(payload) is False


def test_noncanonical_sealed_criteria_order_is_refused_by_the_strict_parser() -> None:
    payload = _payload(cheap_disable())
    criteria = [edge_kill_criterion_to_dict(item) for item in genesis().sealed_kill_criteria]
    payload["sealed_kill_criteria"] = criteria
    assert edge_kill_quarantine_decision_payload_is_well_formed(payload) is True
    payload["sealed_kill_criteria"] = list(reversed(criteria))
    assert edge_kill_quarantine_decision_payload_is_well_formed(payload) is False


def _corrupted(**changes: object) -> EdgeKillQuarantineDecision:
    copy = replace(cheap_disable())
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
        lambda: "ef8",
        lambda: {},
        lambda: [],
        object,
        lambda: ValueError("x"),
        lambda: _HostileMapping(a=1),
        _Exploding,
        lambda: object.__new__(EdgeKillQuarantineDecision),
        ef7t.cheap_approved,
        lambda: edge_kill_quarantine_decision_to_dict(cheap_disable()),
        lambda: _corrupted(prior_binding=None),
        lambda: _corrupted(prior_binding=object()),
        lambda: _corrupted(kill_observation=object()),
        lambda: _corrupted(kill_observation=None),
        lambda: _corrupted(governance=object()),
        lambda: _corrupted(sealed_kill_criteria=(object(),)),
        lambda: _corrupted(sealed_kill_criteria=_cyclic()),
        lambda: _corrupted(consumed_admission_decision_digests=None),
        lambda: _corrupted(effective_at_ns=True),
        lambda: _corrupted(effective_at_ns=2**70),
        lambda: _corrupted(lifecycle_sequence="1"),
        lambda: _corrupted(status="READY"),
        lambda: _corrupted(transition="KILL_DISABLE"),
        lambda: _corrupted(resulting_lifecycle_state="ACTIVE"),
        lambda: _corrupted(decision_id="ef8 scheduler"),
        lambda: _corrupted(transition_reason_reference=_HostileMapping()),
    ],
)
def test_public_verifier_is_total_for_any_object(decision) -> None:
    _assert_not_intact(decision())


@pytest.mark.parametrize("name", ["status", "transition", "prior_lifecycle_state"])
def test_str_enum_alias_is_never_intact(name: str) -> None:
    alias = {"status": "READY", "transition": "KILL_DISABLE", "prior_lifecycle_state": "ACTIVE"}[name]
    verification = _assert_not_intact(_corrupted(**{name: alias}))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- J. non-claims -------------------------------------------------------------------------------------------------------


_ALL_FLAGS = (*(name for name, _ in EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS), *COMPUTED_FLAGS)


def test_non_claim_flags_are_structural_literal_defaults_no_builder_can_set() -> None:
    defaults = {
        field.name: field.default
        for field in fields(EdgeKillQuarantineDecision)
        if field.name in dict(EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)
    }
    assert defaults == dict(EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)
    assert set(EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS) <= set(EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)
    assert all(field.default is MISSING for field in fields(EdgeKillQuarantineDecision) if field.name in COMPUTED_FLAGS)
    for builder in _BUILDER_PARAMETERS:
        assert set(inspect.signature(builder).parameters).isdisjoint(set(_ALL_FLAGS))
    (klass,) = [
        node
        for node in ast.walk(_module_tree())
        if isinstance(node, ast.ClassDef) and node.name == "EdgeKillQuarantineDecision"
    ]
    literal = {
        node.target.id: node.value.value  # type: ignore[union-attr]
        for node in klass.body
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None
    }
    assert literal == dict(EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS)
    assert [name for name, value in literal.items() if value is not False] == ["paper_only"]


@pytest.mark.parametrize("name", _ALL_FLAGS)
def test_every_flipped_claim_or_computed_flag_never_verifies(name: str) -> None:
    payload = _payload(cheap_genesis())
    payload[name] = not payload[name]
    _assert_not_intact(_resealed(payload), f"field_mismatch:{name}")


def test_the_lifecycle_never_claims_readiness_allocation_or_live_authority() -> None:
    for decision in (genesis(), disabled(), quarantined(), readmitted()):
        for flag, value in EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS:
            assert getattr(decision, flag) is value
        assert decision.paper_only is True


# --- K. static purity, scope and memo transparency -----------------------------------------------------------------------


_FORBIDDEN_MODULES = (
    "math",
    "decimal",
    "fractions",
    "time",
    "datetime",
    "calendar",
    "zoneinfo",
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
    "websocket",
    "websockets",
    "threading",
    "asyncio",
    "multiprocessing",
    "concurrent",
    "subprocess",
    "sched",
    "os",
    "sys",
    "io",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
    "importlib",
    "pickle",
    "functools",
    "json",
    "bist_core",
)
_FORBIDDEN_CALLS = frozenset(
    {
        "open",
        "Path",
        "float",
        "eval",
        "exec",
        "compile",
        "__import__",
        "now",
        "utcnow",
        "today",
        "time_ns",
        "monotonic",
        "perf_counter",
        "sleep",
        "getenv",
        "urandom",
        "uuid4",
        "print",
    }
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(ef8_module.__file__).read_text(encoding="utf-8"))


@functools.cache
def _import_closure() -> frozenset[str]:
    closure: set[str] = set()
    pending = {ef8_module.__name__}
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


def test_module_has_no_io_clock_randomness_float_network_or_dynamic_execution() -> None:
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
            assert node.attr not in {"environ", "system", "popen", "global"}
        assert not isinstance(node, ast.Global)


def test_module_consumes_only_public_authenticated_substrate() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_paper_admission_decision",
        "crypto_core.validation.edge_walk_forward_oos_evidence",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}
    assert crypto_imports["crypto_core.validation.edge_paper_admission_decision"] == {
        "EDGE_PAPER_ADMISSION_NON_CLAIM_FLAGS",
        "EdgePaperAdmissionDecision",
        "edge_paper_admission_decision_from_payload",
        "edge_paper_admission_decision_payload_is_well_formed",
        "edge_paper_admission_decision_to_dict",
        "verify_edge_paper_admission_decision",
    }


def test_no_rg_allocator_regime_service_venue_live_order_or_capital_surface() -> None:
    offending = [
        name
        for name in _import_closure()
        if any(
            token in name
            for token in (
                "portfolio",
                "allocat",
                "regime",
                "service",
                "venue",
                "execution.",
                "live",
                "order",
                "connector",
                "scheduler",
                "strategy_signal",
            )
        )
    ]
    assert offending == []
    names = {field.name for field in fields(EdgeKillQuarantineDecision)} - dict(
        EDGE_KILL_QUARANTINE_NON_CLAIM_FLAGS
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
        "allocation",
        "position",
        "fill",
        "best",
        "rank",
        "select",
        "score",
        "winner",
    )
    assert not [name for name in names if any(token in name for token in forbidden)]


def test_single_assembly_path_serves_every_builder_and_verifier() -> None:
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(_module_tree()) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgeKillQuarantineDecision")
    assert constructor_calls == 1
    assert "EdgeKillQuarantineDecision" in calls_by_function["_assemble_decision"]
    for builder in _BUILDER_PARAMETERS:
        assert "_assemble_decision" in calls_by_function[builder.__name__]
    assert "_assemble_decision" in calls_by_function["_reassemble_decision"]
    assert "edge_kill_criterion_triggered" in calls_by_function["_kill_evaluation"]


def test_memoized_reproof_agrees_with_the_real_functions() -> None:
    for name in ("verify_edge_kill_quarantine_decision", "verify_edge_paper_admission_decision"):
        memo = _EF8_MEMOS[name]
        assert getattr(ef8_module, name) is memo
    kill_memo = _EF8_MEMOS["verify_edge_kill_quarantine_decision"]
    assert kill_memo.real is verify_edge_kill_quarantine_decision
    for decision in (genesis(), cheap_readmission()):
        assert kill_memo.real(decision) == kill_memo(decision)
    admission_memo = _EF8_MEMOS["verify_edge_paper_admission_decision"]
    assert admission_memo.real(ef7t.cheap_approved()) == admission_memo(ef7t.cheap_approved())


@SLOW
def test_the_whole_lifecycle_re_proves_with_every_memo_disabled() -> None:
    chain = (genesis(), disabled(), quarantined(), readmitted())
    ef6t._MEMO_ENABLED[0] = False
    try:
        for decision in chain:
            verification = verify_edge_kill_quarantine_decision(decision)
            assert verification.intact is True, verification.reason_codes
            assert verification.recomputed_digest == decision.kill_quarantine_decision_digest
    finally:
        ef6t._MEMO_ENABLED[0] = True


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"decision_id": ""}, "decision_id_invalid"),
        ({"decision_id": "live-ef8"}, "forbidden_scope_token:decision_id"),
        ({"decision_id": "bist-ef8"}, "bist_scope_leakage:decision_id"),
        ({"decision_id": "ef8 order_id 1"}, "forbidden_scope_token:decision_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"reason_reference": ""}, "reason_reference_invalid"),
        ({"reason_reference": "review\t1"}, "reason_reference_invalid"),
        ({"reason_reference": "x" * 257}, "reason_reference_invalid"),
        ({"reason_reference": "auto_loop restart"}, "forbidden_scope_token:reason_reference"),
        ({"reason_reference": "kap review"}, "bist_scope_leakage:reason_reference"),
        ({"expected_root_intake_digest": "A" * 64}, "root_intake_digest_invalid"),
        ({"expected_prior_digest": "a" * 63}, "prior_lifecycle_expected_digest_invalid"),
    ],
)
def test_malformed_or_out_of_scope_caller_input_is_a_construction_error(
    overrides: dict[str, object], code: str
) -> None:
    with pytest.raises(EdgeKillQuarantineDecisionError, match=code):
        quarantine(cheap_genesis(), **overrides)
