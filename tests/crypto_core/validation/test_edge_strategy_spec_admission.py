"""Tests for Edge Factory EF-4 ``crypto_core.validation.edge_strategy_spec_admission``.

All kill-criterion thresholds below are synthetic test fixtures, never approved production thresholds.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.edge_strategy_spec_admission as admission_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, strategy_spec_to_dict, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    EdgeKillCriteriaPolicy,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    edge_kill_criteria_digest,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    EdgeSourcePacketEvidence,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_digest,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionError,
    EdgeStrategySpecAdmissionEvidence,
    build_edge_strategy_spec_admission,
    edge_strategy_spec_admission_digest,
    edge_strategy_spec_admission_from_payload,
    edge_strategy_spec_admission_payload_is_well_formed,
    edge_strategy_spec_admission_to_dict,
    verify_edge_strategy_spec_admission,
)

_PREFIX = "edge_strategy_spec_admission"
_UNSET = object()
_DRAWDOWN = EdgeKillCriterion(
    "max_drawdown_breach",
    "max_drawdown",
    EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
    "0.250000000000000000",
    "rolling_30_utc_days",
)
_FUNDING = EdgeKillCriterion(
    "funding_flip_persistence",
    "negative_funding_hours",
    EdgeKillCriterionComparator.KILL_IF_ABOVE,
    "12.000000000000000000",
    "rolling_7_utc_days",
)
_BASIS = EdgeKillCriterion(
    "basis_blowout",
    "basis_bps",
    EdgeKillCriterionComparator.KILL_IF_ABOVE,
    "150.000000000000000000",
    "rolling_1_utc_day",
)
_DRAFT = (_DRAWDOWN, _FUNDING)
_SPEC_PAYLOAD: dict[str, object] = {
    "schema_version": "1.0",
    "strategy_id": "alpha-funding-carry",
    "strategy_version": "1.0.0",
    "strategy_family": "carry",
    "edge_family": "funding_basis_carry",
    "instrument_universe": ["BTC-PERPETUAL", "ETH-PERPETUAL"],
    "market_type": "inverse_perp",
    "venue_assumptions": ["perpetual_funding_windows"],
    "timeframe": "1h",
    "bar_definition": "time_bars_utc",
    "entry_conditions": ["funding_positive_for_3_windows"],
    "exit_conditions": ["funding_non_positive"],
    "invalidation_conditions": ["basis_dislocation"],
    "risk_caps": {"max_leverage": 2},
    "data_requirements": {"funding_rate": "1h", "mark_price": "1m"},
    "feature_requirements": {"funding_zscore": "rolling_30d"},
    "latency_sensitivity": "low",
    "funding_sensitivity": "high",
    "fee_model_requirement": "maker_taker_schedule",
    "slippage_model_requirement": "book_impact_v1",
    "expected_regime": "positive_funding_regime",
    "failure_modes": ["funding_flip"],
    "kill_switch_triggers": ["funding_flip_persistence", "max_drawdown_breach"],
    "telemetry_fields": ["funding_rate"],
    "promotion_requirements": ["governance_review"],
}


def _policy(criteria: tuple[EdgeKillCriterion, ...] = _DRAFT, **overrides: object) -> EdgeKillCriteriaPolicy:
    arguments: dict[str, object] = {
        "policy_id": "policy-1",
        "correlation_id": "corr-1",
        "kill_criteria": criteria,
        "thresholds_approved": True,
        "approval_reference": "governance-review-1",
        "approval_digest": "d" * 64,
    }
    arguments.update(overrides)
    return build_edge_kill_criteria_policy(**arguments)  # type: ignore[arg-type]


def _intake(intake_id: str = "intake-1", **overrides: object) -> EdgeIdeaIntakeEvidence:
    packet = build_source_packet(
        packet_id="pkt-funding-carry-001",
        source_type="academic_paper",
        source_reference="doi:10.0000/funding-carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Persistent positive funding compensates passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    policy = _policy()
    arguments: dict[str, object] = {
        "expected_source_packet_digest": packet.packet_digest,
        "intake_id": intake_id,
        "correlation_id": "corr-1",
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Persistent positive funding pays passive carry holders.",
        "data_requirement_keys": ("funding_rate", "mark_price"),
        "declared_regime_dependence": "positive_funding_regime",
        "kill_criteria_draft": _DRAFT,
        "kill_criteria_policy": policy,
        "expected_kill_criteria_policy_digest": policy.policy_digest,
    }
    arguments.update(overrides)
    return build_edge_idea_intake_evidence(packet, **arguments)  # type: ignore[arg-type]


def _manifest(
    root: EdgeIdeaIntakeEvidence | None = None, *, funding_rights: str = "own_research", **overrides: object
) -> EdgeSourcePacketEvidence:
    root = _intake() if root is None else root
    registry = default_perp_data_requirement_registry()
    series = (
        EdgeInputSeries(
            "funding-btc-eth",
            "funding_rate",
            "venue-archive:funding",
            funding_rights,
            "research-note-1",
            "finalized_only",
            "immutable_after_finalization",
            ("BTC-PERPETUAL", "ETH-PERPETUAL"),
        ),
        EdgeInputSeries(
            "mark-majors",
            "mark_price",
            "venue-archive:mark",
            "own_research",
            "research-note-2",
            "finalized_only",
            "immutable_after_finalization",
            ("BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL"),
        ),
    )
    arguments: dict[str, object] = {
        "expected_root_intake_digest": root.intake_digest,
        "data_requirement_registry": registry,
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry),
        "manifest_id": "manifest-1",
        "correlation_id": "corr-1",
        "input_series": series,
    }
    arguments.update(overrides)
    return build_edge_source_packet_evidence(root, **arguments)  # type: ignore[arg-type]


def _spec(**changes: object) -> StrategySpec:
    result = validate_strategy_spec({**_SPEC_PAYLOAD, **changes})
    assert result.accepted, result.rejection_reasons
    return result.spec  # type: ignore[return-value]


def _admission(
    *,
    predecessor: object = _UNSET,
    predecessor_digest: object = _UNSET,
    root_digest: object = _UNSET,
    spec: object = _UNSET,
    spec_digest: object = _UNSET,
    criteria: object = _DRAFT,
    policy: object = _UNSET,
    policy_digest: object = _UNSET,
    **overrides: object,
) -> EdgeStrategySpecAdmissionEvidence:
    root = _intake()
    predecessor = _manifest(root) if predecessor is _UNSET else predecessor
    spec = _spec() if spec is _UNSET else spec
    policy = _policy(criteria) if policy is _UNSET else policy  # type: ignore[arg-type]
    arguments: dict[str, object] = {
        "expected_predecessor_digest": predecessor.source_packet_evidence_digest  # type: ignore[attr-defined]
        if predecessor_digest is _UNSET
        else predecessor_digest,
        "expected_root_intake_digest": root.intake_digest if root_digest is _UNSET else root_digest,
        "strategy_spec": spec,
        "expected_strategy_spec_digest": strategy_spec_digest(spec) if spec_digest is _UNSET else spec_digest,  # type: ignore[arg-type]
        "admission_id": "admission-1",
        "correlation_id": "corr-1",
        "admitted_kill_criteria": criteria,
        "kill_criteria_policy": policy,
        "expected_kill_criteria_policy_digest": (None if policy is None else policy.policy_digest)  # type: ignore[attr-defined]
        if policy_digest is _UNSET
        else policy_digest,
    }
    arguments.update(overrides)
    return build_edge_strategy_spec_admission(predecessor, **arguments)  # type: ignore[arg-type]


def _redigest(evidence: EdgeStrategySpecAdmissionEvidence) -> EdgeStrategySpecAdmissionEvidence:
    return replace(evidence, admission_digest=edge_strategy_spec_admission_digest(evidence))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _assert_receipt_invariants(evidence: EdgeStrategySpecAdmissionEvidence) -> None:
    verification = verify_edge_strategy_spec_admission(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.admission_digest
    assert edge_strategy_spec_admission_from_payload(json.loads(verification.canonical_json)) == evidence
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert evidence.predecessor_digest == evidence.predecessor_binding.expected_digest
    assert evidence.kill_criteria_sealed is False
    assert evidence.candidate_admitted_to_paper is False
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
    else:
        assert evidence.integrity_reason_codes == ()


# --- happy path -----------------------------------------------------------------------------------------------------


def test_pass_admission_is_ready_advances_and_re_proves() -> None:
    root = _intake()
    predecessor = _manifest(root)
    spec = _spec()
    evidence = _admission(predecessor=predecessor, spec=spec)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.advances is True
    assert evidence.gate_id == "EF-4"
    assert evidence.predecessor_gate_id == "EF-3"
    assert evidence.root_intake_digest == root.intake_digest == predecessor.root_intake_digest
    assert evidence.predecessor_digest == predecessor.source_packet_evidence_digest
    assert evidence.strategy_spec_digest == strategy_spec_digest(spec)
    assert json.loads(evidence.strategy_spec_binding.snapshot_json) == strategy_spec_to_dict(spec)
    assert evidence.candidate_strategy_id == evidence.strategy_id == "alpha-funding-carry"
    assert evidence.edge_family == evidence.spec_edge_family == "funding_basis_carry"
    assert evidence.packet_instrument_coverage == ("BTC-PERPETUAL", "ETH-PERPETUAL")
    assert evidence.packet_data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.instrument_universe == spec.instrument_universe
    assert evidence.market_type == "inverse_perp"
    assert evidence.spec_data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.spec_kill_switch_triggers == spec.kill_switch_triggers
    assert (evidence.fee_model_requirement, evidence.slippage_model_requirement) == (
        spec.fee_model_requirement,
        spec.slippage_model_requirement,
    )
    assert (evidence.funding_sensitivity, evidence.latency_sensitivity) == ("high", "low")
    assert evidence.declared_expected_regime == "positive_funding_regime"
    assert evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert evidence.root_kill_criteria_digest == root.kill_criteria_digest == evidence.admitted_kill_criteria_digest
    assert evidence.added_kill_criterion_ids == ()
    assert evidence.kill_criteria_lifecycle_stage == "SUPERSET_STRENGTHENED_UNSEALED"
    _assert_receipt_invariants(evidence)
    assert edge_strategy_spec_admission_payload_is_well_formed(edge_strategy_spec_admission_to_dict(evidence)) is True


def test_additive_strengthening_with_approved_policy_passes_unsealed() -> None:
    admitted = (*_DRAFT, _BASIS)
    spec = _spec(kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"])
    evidence = _admission(spec=spec, criteria=admitted)
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.added_kill_criterion_ids == ("basis_blowout",)
    assert evidence.admitted_kill_criteria_digest == edge_kill_criteria_digest(admitted)
    assert evidence.admitted_kill_criteria_digest != evidence.root_kill_criteria_digest
    _assert_receipt_invariants(evidence)


def test_admission_is_deterministic() -> None:
    assert _admission(criteria=tuple(reversed(_DRAFT))) == _admission()


# --- verdict states -------------------------------------------------------------------------------------------------

_ONE_TRIGGER = ["max_drawdown_breach"]


@pytest.mark.parametrize(
    ("kwargs", "expected_codes"),
    [
        ({"spec": _spec(strategy_id="beta-funding-carry")}, {"candidate_strategy_id_mismatch"}),
        ({"spec": _spec(edge_family="basis_mean_reversion")}, {"edge_family_mismatch"}),
        (
            {"spec": _spec(instrument_universe=["BTC-PERPETUAL", "SOL-PERPETUAL"])},
            {"instrument_outside_packet_coverage:SOL-PERPETUAL"},
        ),
        (
            {"spec": _spec(data_requirements={"funding_rate": "1h", "index_price": "1m"})},
            {"spec_data_requirement_not_in_packet:index_price"},
        ),
        (
            {"spec": _spec(data_requirements={"funding_rate": "1h", "open_interest": "1h"})},
            {"spec_data_requirement_not_in_packet:open_interest"},
        ),
        ({"spec": _spec(kill_switch_triggers=_ONE_TRIGGER)}, {"spec_kill_switch_triggers_not_bound_to_kill_criteria"}),
        (
            {"spec": _spec(kill_switch_triggers=_ONE_TRIGGER), "criteria": (_DRAWDOWN,)},
            {"kill_criterion_removed:funding_flip_persistence"},
        ),
        (
            {"criteria": (replace(_DRAWDOWN, threshold="0.300000000000000000"), _FUNDING)},
            {"kill_criterion_modified:max_drawdown_breach"},
        ),
        (
            {"criteria": (replace(_DRAWDOWN, comparator=EdgeKillCriterionComparator.KILL_IF_ABOVE), _FUNDING)},
            {"kill_criterion_modified:max_drawdown_breach"},
        ),
        ({"predecessor": _manifest(funding_rights="restricted")}, {"predecessor_not_advanced"}),
    ],
)
def test_contract_violations_are_valid_negative_evidence(kwargs: dict[str, object], expected_codes: set[str]) -> None:
    evidence = _admission(**kwargs)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected_codes}
    _assert_receipt_invariants(evidence)


@pytest.mark.parametrize(
    ("kwargs", "expected_codes"),
    [
        ({"policy": None}, {"kill_criteria_policy_missing"}),
        ({"policy": _policy(correlation_id="corr-2")}, {"kill_criteria_policy_correlation_mismatch"}),
        ({"policy": _policy(thresholds_approved=False)}, {"kill_criteria_policy_not_ready"}),
        (
            {
                "spec": _spec(
                    kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"]
                ),
                "criteria": (*_DRAFT, _BASIS),
                "policy": _policy(),
            },
            {"kill_criteria_policy_kill_criteria_mismatch"},
        ),
        (
            {
                "spec": _spec(
                    kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"]
                ),
                "criteria": (*_DRAFT, replace(_BASIS, threshold=None)),
            },
            {"kill_criterion_threshold_pending_governance:basis_blowout", "kill_criteria_policy_not_ready"},
        ),
    ],
)
def test_governance_needs_never_advance(kwargs: dict[str, object], expected_codes: set[str]) -> None:
    evidence = _admission(**kwargs)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected_codes}
    _assert_receipt_invariants(evidence)


def test_fail_dominates_governance_needs() -> None:
    evidence = _admission(spec=_spec(strategy_id="beta-funding-carry"), policy=None)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("kill_criteria_policy_missing") in evidence.verdict_reason_codes


# --- truthful REJECTED receipts -------------------------------------------------------------------------------------


def _forged_coverage_predecessor() -> EdgeSourcePacketEvidence:
    manifest = replace(_manifest(), instrument_coverage=("BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL"))
    return replace(manifest, source_packet_evidence_digest=edge_source_packet_evidence_digest(manifest))


def _spliced_predecessor() -> EdgeSourcePacketEvidence:
    return _manifest(_intake(intake_id="intake-2"))


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        (
            {"predecessor_digest": _manifest(manifest_id="manifest-2").source_packet_evidence_digest},
            "predecessor_digest_mismatch",
        ),
        ({"correlation_id": "corr-2"}, "predecessor_correlation_mismatch"),
        ({"predecessor": _manifest(expected_data_requirement_registry_digest="f" * 64)}, "predecessor_rejected"),
        ({"predecessor": _spliced_predecessor()}, "chain_splice_root_intake_mismatch"),
        ({"root_digest": "b" * 64}, "chain_splice_root_intake_mismatch"),
        (
            {"predecessor": _forged_coverage_predecessor()},
            "predecessor_integrity_failure:edge_source_packet_evidence:field_mismatch:instrument_coverage",
        ),
        ({"spec_digest": strategy_spec_digest(_spec(strategy_version="2.0.0"))}, "strategy_spec_digest_mismatch"),
        ({"spec": replace(_spec(), funding_sensitivity="unknown")}, "strategy_spec_not_accepted"),
        ({"spec": replace(_spec(), strategy_id=" alpha-funding-carry ")}, "strategy_spec_noncanonical"),
        ({"spec": _spec(venue_assumptions=["no live venue access"])}, "strategy_spec_scope_violation"),
        ({"policy_digest": _policy(policy_id="policy-2").policy_digest}, "kill_criteria_policy_digest_mismatch"),
    ],
)
def test_authentic_authorities_failing_re_proof_are_truthful_rejected_receipts(
    kwargs: dict[str, object], expected_code: str
) -> None:
    evidence = _admission(**kwargs)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _code(expected_code) in evidence.integrity_reason_codes
    assert evidence.advances is False
    _assert_receipt_invariants(evidence)


# --- negative-evidence regressions ----------------------------------------------------------------------------------


def test_predecessor_coverage_spoof_cannot_admit_an_uncovered_instrument() -> None:
    evidence = _admission(
        predecessor=_forged_coverage_predecessor(), spec=_spec(instrument_universe=["BTC-PERPETUAL", "SOL-PERPETUAL"])
    )
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.packet_instrument_coverage == ()
    assert evidence.advances is False


def test_splice_of_a_valid_predecessor_onto_another_root_is_rejected_and_carried_anchor_is_bound() -> None:
    spliced = _admission(predecessor=_spliced_predecessor())
    assert spliced.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)
    honest = _admission()
    forged = _redigest(replace(honest, root_intake_digest=_intake(intake_id="intake-2").intake_digest))
    verification = verify_edge_strategy_spec_admission(forged)
    assert verification.intact is False
    assert _code("field_mismatch:status") in verification.reason_codes


@pytest.mark.parametrize(
    "replacement",
    [
        {"strategy_id": "beta-funding-carry"},
        {"instrument_universe": ("BTC-PERPETUAL", "SOL-PERPETUAL")},
        {"spec_data_requirement_keys": ("funding_rate",)},
        {"declared_expected_regime": "RF_TRENDING"},
        {"regime_label_binding_status": "BOUND"},
        {"fee_model_requirement": "zero_fee"},
        {"packet_instrument_coverage": ("BTC-PERPETUAL", "ETH-PERPETUAL", "SOL-PERPETUAL")},
        {"added_kill_criterion_ids": ("basis_blowout",)},
    ],
)
def test_spec_and_packet_summary_copy_spoofs_fail_verification(replacement: dict[str, object]) -> None:
    verification = verify_edge_strategy_spec_admission(_redigest(replace(_admission(), **replacement)))
    assert verification.intact is False
    assert _code(f"field_mismatch:{next(iter(replacement))}") in verification.reason_codes


def test_builder_accepts_no_derived_summary_parameters() -> None:
    parameters = set(inspect.signature(build_edge_strategy_spec_admission).parameters)
    derived = {
        "strategy_id",
        "instrument_universe",
        "candidate_strategy_id",
        "edge_family",
        "packet_instrument_coverage",
        "declared_expected_regime",
        "added_kill_criterion_ids",
        "root_kill_criteria_digest",
    }
    assert not derived & parameters


def test_rejected_receipts_never_advance_and_cannot_be_promoted() -> None:
    rejected_predecessor = _manifest(expected_data_requirement_registry_digest="f" * 64)
    assert verify_edge_strategy_spec_admission(object()).intact is False
    evidence = _admission(predecessor=rejected_predecessor)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code("predecessor_rejected"),)
    promoted = _redigest(
        replace(
            evidence,
            status=EdgeEvidenceStatus.READY,
            gate_verdict=EdgeGateVerdict.PASS,
            advances=True,
            integrity_reason_codes=(),
        )
    )
    verification = verify_edge_strategy_spec_admission(promoted)
    assert verification.intact is False
    assert _code("field_mismatch:advances") in verification.reason_codes


# --- construction errors --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"predecessor": None, "predecessor_digest": "a" * 64}, "predecessor_malformed"),
        ({"predecessor": _intake(), "predecessor_digest": "a" * 64}, "predecessor_malformed"),
        (
            {"predecessor": object.__new__(EdgeSourcePacketEvidence), "predecessor_digest": "a" * 64},
            "predecessor_not_serializable",
        ),
        ({"predecessor": replace(_manifest(), series=None)}, "predecessor_not_serializable"),
        ({"predecessor_digest": "A" * 64}, "predecessor_expected_digest_invalid"),
        ({"root_digest": None}, "root_intake_digest_invalid"),
        ({"spec": None, "spec_digest": "a" * 64}, "strategy_spec_malformed"),
        ({"spec": dict(_SPEC_PAYLOAD), "spec_digest": "a" * 64}, "strategy_spec_malformed"),
        ({"spec": object.__new__(StrategySpec), "spec_digest": "a" * 64}, "strategy_spec_not_serializable"),
        (
            {"spec": replace(_spec(), risk_caps={"max_leverage": {2}}), "spec_digest": "a" * 64},
            "strategy_spec_not_serializable",
        ),
        (
            {"spec": replace(_spec(), market_type="inverse_perp"), "spec_digest": "a" * 64},
            "strategy_spec_not_serializable",
        ),
        (
            {"spec": replace(_spec(), instrument_universe=("BTC-PERPETUAL", 1)), "spec_digest": "a" * 64},
            "strategy_spec_not_serializable",
        ),
        ({"spec_digest": ""}, "strategy_spec_expected_digest_invalid"),
        ({"criteria": (), "policy": None}, "admitted_kill_criteria_invalid"),
        ({"criteria": ("max_drawdown_breach",), "policy": None}, "admitted_kill_criteria_invalid"),
        ({"admission_id": "admission order_router"}, "forbidden_scope_token:admission_id"),
        ({"correlation_id": ""}, "correlation_id_invalid"),
        ({"policy": None, "policy_digest": "a" * 64}, "kill_criteria_policy_expected_digest_unexpected"),
        ({"policy": {"policy_id": "policy-1"}, "policy_digest": "a" * 64}, "kill_criteria_policy_malformed"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeStrategySpecAdmissionError, match=f"^{_code(code)}$"):
        _admission(**kwargs)


# --- RC1: builder domain equals verifier reassembly domain ----------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json='{"a":1}', expected_digest="a" * 64)},
        {"predecessor_binding": None},
        {"strategy_spec_binding": EdgeAuthorityBinding(snapshot_json="{}", expected_digest="a" * 64)},
        {"strategy_spec_binding": None},
        {"kill_criteria_policy_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"root_intake_digest": ""},
    ],
)
def test_partial_binding_and_anchor_states_never_verify(replacement: dict[str, object]) -> None:
    verification = verify_edge_strategy_spec_admission(replace(_admission(), **replacement))
    assert verification.intact is False
    assert len(verification.reason_codes) == 1


def _mutated_payload(path: tuple[object, ...], value: object) -> dict:
    payload = json.loads(edge_canonical_json(edge_strategy_spec_admission_to_dict(_admission())))
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    return payload


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("predecessor_binding", "snapshot"), {}),
        (("predecessor_binding", "snapshot", "series"), None),
        (("predecessor_binding", "snapshot", "root_intake_binding", "snapshot", "gate_id"), 2),
        (("strategy_spec_binding", "snapshot", "risk_caps"), []),
        (("strategy_spec_binding", "snapshot", "instrument_universe"), "BTC-PERPETUAL"),
        (("strategy_spec_binding", "snapshot", "promotion_requirements"), _UNSET),
        (("kill_criteria_policy_binding", "snapshot", "ready"), "true"),
        (("admitted_kill_criteria",), [{"criterion_id": "x"}]),
        (("admitted_kill_criteria", 0, "threshold"), 0.25),
        (("status",), None),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    assert edge_strategy_spec_admission_payload_is_well_formed(_mutated_payload(path, value)) is False


# --- RC2: public verifier totality ----------------------------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeStrategySpecAdmissionEvidence:
    copy = replace(_admission())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    -1,
    "admission",
    object(),
    {},
    edge_strategy_spec_admission_to_dict(_admission()),
    _manifest(),
    _spec(),
    object.__new__(EdgeStrategySpecAdmissionEvidence),
    _corrupted(admitted_kill_criteria=None),
    _corrupted(admitted_kill_criteria=("max_drawdown_breach",)),
    _corrupted(strategy_spec_binding=EdgeAuthorityBinding(snapshot_json="{", expected_digest="a" * 64)),
    _corrupted(predecessor_binding=object.__new__(EdgeAuthorityBinding)),
    _corrupted(root_intake_digest=None),
    _corrupted(instrument_universe=None),
    _corrupted(admission_id="admission scheduler"),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_edge_strategy_spec_admission(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


# --- RC3: builder/verifier round trips for every state --------------------------------------------------------------

_STATE_BUILDERS = {
    "pass": lambda: _admission(),
    "fail": lambda: _admission(spec=_spec(strategy_id="beta-funding-carry")),
    "needs_governance_approval": lambda: _admission(policy=None),
    "rejected_splice": lambda: _admission(predecessor=_spliced_predecessor()),
    "rejected_spec": lambda: _admission(spec_digest="e" * 64),
    "rejected_predecessor_receipt": lambda: _admission(
        predecessor=_manifest(expected_data_requirement_registry_digest="f" * 64)
    ),
}


@pytest.mark.parametrize("state", sorted(_STATE_BUILDERS))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _STATE_BUILDERS[state]()
    _assert_receipt_invariants(evidence)
    expected = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected


# --- RC4: binding canonicality --------------------------------------------------------------------------------------


def test_bindings_are_canonical_and_noncanonical_in_memory_bindings_never_verify() -> None:
    evidence = _admission()
    for binding in (
        evidence.predecessor_binding,
        evidence.strategy_spec_binding,
        evidence.kill_criteria_policy_binding,
    ):
        assert binding is not None
        assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = replace(
        evidence.strategy_spec_binding,
        snapshot_json=json.dumps(json.loads(evidence.strategy_spec_binding.snapshot_json), sort_keys=True, indent=1),
    )
    verification = verify_edge_strategy_spec_admission(replace(evidence, strategy_spec_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- structural non-claims ------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flag_names = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    defaults = {
        field.name: field.default for field in fields(EdgeStrategySpecAdmissionEvidence) if field.name in flag_names
    }
    assert defaults == dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
    assert not flag_names & set(inspect.signature(build_edge_strategy_spec_admission).parameters)


@pytest.mark.parametrize("flag", ["candidate_admitted_to_paper", "kill_criteria_sealed", "preregistration_sealed"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_edge_strategy_spec_admission(_redigest(replace(_admission(), **{flag: True})))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


# --- structural purity ----------------------------------------------------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
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
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic", "getenv", "print"}
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(admission_module.__file__).read_text(encoding="utf-8"))


def test_module_has_no_io_clock_randomness_or_float() -> None:
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
            assert node.attr != "environ"


def test_module_consumes_only_public_substrate_names() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.data.requirements",
        "crypto_core.strategy.spec",
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_source_packet_evidence",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    tree = _module_tree()
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgeStrategySpecAdmissionEvidence")
    assert constructor_calls == 1
    assert "EdgeStrategySpecAdmissionEvidence" in calls_by_function["_assemble_admission"]
    assert "_assemble_admission" in calls_by_function["build_edge_strategy_spec_admission"]
    assert "_assemble_admission" in calls_by_function["_reassemble_admission"]
