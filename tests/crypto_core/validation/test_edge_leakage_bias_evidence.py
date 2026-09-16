"""Tests for Edge Factory EF-5 ``crypto_core.validation.edge_leakage_bias_evidence``.

Every threshold, bound, window count and digest below is a synthetic test fixture, never an approved production value.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from functools import lru_cache
from pathlib import Path

import pytest

import crypto_core.validation.edge_leakage_bias_evidence as ledger_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_PERMANENT_NON_CLAIM_FLAGS,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_gate_claim_profile,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeEvaluationAssumption,
    EdgeLabelThresholdStructure,
    EdgeLeakageBiasEvidence,
    EdgeLeakageBiasEvidenceError,
    EdgeLeakageProof,
    EdgeParameterAssignment,
    EdgeParameterBound,
    EdgePreregisteredWindow,
    EdgePreregistrationPolicy,
    EdgePreregistrationPolicyStatus,
    EdgeUniverseMember,
    EdgeUniverseSnapshot,
    EdgeVariantRegistration,
    build_edge_leakage_bias_evidence,
    build_edge_preregistration_policy,
    edge_evaluation_assumptions_digest,
    edge_leakage_bias_evidence_digest,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    edge_parameter_bounds_digest,
    edge_preregistration_policy_digest,
    edge_preregistration_policy_from_payload,
    edge_preregistration_policy_to_dict,
    edge_universe_snapshot_set_digest,
    reprove_edge_admitted_chain,
    verify_edge_leakage_bias_evidence,
    verify_edge_preregistration_policy,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    build_edge_strategy_spec_admission,
    verify_edge_strategy_spec_admission,
)
from crypto_core.validation.leakage_bias_repaint import (
    ValidationFeatureTimestamp,
    ValidationFundingObservation,
    ValidationIndicatorPolicy,
)

_PREFIX = "edge_leakage_bias_evidence"
_UNSET = object()
_APPROVED = object()
_CRITERIA = (
    EdgeKillCriterion(
        "max_drawdown_breach",
        "max_drawdown",
        EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
        "0.250000000000000000",
        "rolling_30_utc_days",
    ),
    EdgeKillCriterion(
        "funding_flip_persistence",
        "negative_funding_hours",
        EdgeKillCriterionComparator.KILL_IF_ABOVE,
        "12.000000000000000000",
        "rolling_7_utc_days",
    ),
)
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
_BOUNDS = (
    EdgeParameterBound("entry_zscore", "1.000000000000000000", "3.000000000000000000"),
    EdgeParameterBound("lookback_days", "7.000000000000000000", "30.000000000000000000"),
)
_STRUCTURES = (
    EdgeLabelThresholdStructure("entry_threshold", "threshold", "enter above the entry zscore", ("entry_zscore",)),
)
_ASSUMPTIONS = (
    EdgeEvaluationAssumption("fee_model", "maker-taker-schedule-v1", "1" * 64),
    EdgeEvaluationAssumption("slippage_model", "book-impact-v1", "2" * 64),
    EdgeEvaluationAssumption("funding_model", "final-funding-cycles-v1", "3" * 64),
)
_SNAPSHOT = EdgeUniverseSnapshot(
    "universe-a",
    1_000,
    (EdgeUniverseMember("BTC-PERPETUAL", 100, None), EdgeUniverseMember("ETH-PERPETUAL", 200, None)),
    "listing-archive:a",
    "4" * 64,
)
_WINDOWS = (
    EdgePreregisteredWindow("w1", 2_000, 3_000, 3_000, 4_000, "universe-a"),
    EdgePreregisteredWindow("w2", 3_000, 4_000, 4_000, 5_000, "universe-a"),
)
_VARIANTS = (
    EdgeVariantRegistration(
        "v-primary",
        (
            EdgeParameterAssignment("entry_zscore", "2.000000000000000000"),
            EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
        ),
    ),
    EdgeVariantRegistration(
        "v-alt",
        (
            EdgeParameterAssignment("entry_zscore", "2.500000000000000000"),
            EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
        ),
    ),
)
_FEATURE = ValidationFeatureTimestamp("funding_zscore", 9_000, 9_500, 9_600, False, False)
_FUNDING = ValidationFundingObservation("perp-venue", 9_000, 9_100, 9_200, 0.0001)
_PROOF = EdgeLeakageProof(10_000, (_FEATURE,), (_FUNDING,), (), (), ())


@lru_cache(maxsize=None)
def _chain(
    intake_id: str = "intake-1", admission_state: str = "pass"
) -> tuple[object, object, EdgeStrategySpecAdmissionEvidence]:
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
    kill_policy = build_edge_kill_criteria_policy(
        policy_id="kill-policy-1",
        correlation_id="corr-1",
        kill_criteria=_CRITERIA,
        thresholds_approved=True,
        approval_reference="governance-review-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id=intake_id,
        correlation_id="corr-1",
        candidate_strategy_id="alpha-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Persistent positive funding pays passive carry holders.",
        data_requirement_keys=("funding_rate", "mark_price"),
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=_CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry()
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=(
            EdgeInputSeries(
                "funding-btc-eth",
                "funding_rate",
                "venue-archive:funding",
                "own_research",
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
                ("BTC-PERPETUAL", "ETH-PERPETUAL"),
            ),
        ),
    )
    spec_payload = dict(_SPEC_PAYLOAD)
    if admission_state == "fail":
        spec_payload["strategy_id"] = "beta-funding-carry"
    spec = validate_strategy_spec(spec_payload).spec
    with_policy = admission_state != "needs_governance"
    admission = build_edge_strategy_spec_admission(
        manifest,
        expected_predecessor_digest=manifest.source_packet_evidence_digest,
        expected_root_intake_digest=intake.intake_digest,
        strategy_spec=spec,
        expected_strategy_spec_digest="e" * 64 if admission_state == "rejected" else strategy_spec_digest(spec),
        admission_id="admission-1",
        correlation_id="corr-1",
        admitted_kill_criteria=_CRITERIA,
        kill_criteria_policy=kill_policy if with_policy else None,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest if with_policy else None,
    )
    return intake, manifest, admission


def _policy(variant_ledger_digest: str | None, **overrides: object) -> EdgePreregistrationPolicy:
    arguments: dict[str, object] = {
        "policy_id": "prereg-policy-1",
        "correlation_id": "corr-1",
        "candidate_strategy_id": "alpha-funding-carry",
        "parameter_bounds": _BOUNDS,
        "min_oos_window_count": 2,
        "approved_variant_ledger_digest": variant_ledger_digest,
        "approved": True,
        "approval_reference": "governance-prereg-1",
        "approval_digest": "f" * 64,
    }
    arguments.update(overrides)
    return build_edge_preregistration_policy(**arguments)  # type: ignore[arg-type]


def _ledger(
    *,
    admission: EdgeStrategySpecAdmissionEvidence | None = None,
    policy: object = _APPROVED,
    policy_digest: object = _UNSET,
    **overrides: object,
) -> EdgeLeakageBiasEvidence:
    intake, _, default_admission = _chain()
    admission = default_admission if admission is None else admission
    arguments: dict[str, object] = {
        "expected_predecessor_digest": admission.admission_digest,
        "expected_root_intake_digest": intake.intake_digest,  # type: ignore[attr-defined]
        "ledger_id": "ledger-1",
        "correlation_id": "corr-1",
        "parameter_bounds": _BOUNDS,
        "label_threshold_structures": _STRUCTURES,
        "evaluation_assumptions": _ASSUMPTIONS,
        "universe_snapshots": (_SNAPSHOT,),
        "windows": _WINDOWS,
        "variants": _VARIANTS,
        "primary_variant_id": "v-primary",
        "leakage_proof": _PROOF,
    }
    arguments.update(overrides)
    if policy is _APPROVED:
        draft = build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]
        policy = _policy(draft.variant_ledger_digest)
    arguments["preregistration_policy"] = policy
    arguments["expected_preregistration_policy_digest"] = (
        (None if policy is None else policy.policy_digest) if policy_digest is _UNSET else policy_digest  # type: ignore[attr-defined]
    )
    return build_edge_leakage_bias_evidence(admission, **arguments)  # type: ignore[arg-type]


def _redigest(evidence: EdgeLeakageBiasEvidence) -> EdgeLeakageBiasEvidence:
    return replace(evidence, ledger_digest=edge_leakage_bias_evidence_digest(evidence))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _flags(artifact: object) -> dict[str, bool]:
    return {name: getattr(artifact, name) for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}


def _assert_receipt_invariants(evidence: EdgeLeakageBiasEvidence) -> None:
    verification = verify_edge_leakage_bias_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.ledger_digest
    assert edge_leakage_bias_evidence_from_payload(json.loads(verification.canonical_json)) == evidence
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert evidence.preregistration_sealed is (evidence.status is EdgeEvidenceStatus.READY)
    assert evidence.performance_data_consumed is False
    assert evidence.multiple_testing_count == len(evidence.variants) == len(evidence.ledger_entries)
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
        assert evidence.approved_min_oos_window_count is None
    else:
        assert evidence.integrity_reason_codes == ()


def _verdict_codes(evidence: EdgeLeakageBiasEvidence) -> set[str]:
    return set(evidence.verdict_reason_codes)


# --- happy path and milestone profile -------------------------------------------------------------------------------


def test_pass_ledger_is_ready_sealed_advancing_and_re_proves() -> None:
    intake, manifest, admission = _chain()
    evidence = _ledger()
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert evidence.gate_id == "EF-5"
    assert evidence.predecessor_gate_id == "EF-4"
    assert evidence.root_intake_digest == intake.intake_digest  # type: ignore[attr-defined]
    assert evidence.predecessor_digest == admission.admission_digest
    assert evidence.candidate_strategy_id == evidence.strategy_id == "alpha-funding-carry"
    assert evidence.strategy_spec_digest == admission.strategy_spec_digest
    assert evidence.admitted_kill_criteria_digest == admission.admitted_kill_criteria_digest
    assert evidence.instrument_universe == ("BTC-PERPETUAL", "ETH-PERPETUAL")
    assert evidence.feature_set == ("funding_zscore",)
    assert evidence.parameter_bounds_digest == edge_parameter_bounds_digest(_BOUNDS)
    assert evidence.evaluation_assumptions_digest == edge_evaluation_assumptions_digest(_ASSUMPTIONS)
    assert evidence.universe_snapshot_set_digest == edge_universe_snapshot_set_digest((_SNAPSHOT,))
    assert evidence.primary_variant_id == "v-primary"
    assert evidence.multiple_testing_count == 2
    assert evidence.approved_min_oos_window_count == 2
    assert evidence.leakage_repaint_status == "PASS"
    assert evidence.survivorship_internal_consistency_proven is True
    assert evidence.survivorship_external_truth_basis == (
        "human_governance_attested_membership_evidence_not_machine_proven"
    )
    for entry in evidence.ledger_entries:
        assert entry.feature_set_digest == evidence.feature_set_digest
        assert entry.window_schedule_digest == evidence.window_schedule_digest
        assert entry.universe_snapshot_set_digest == evidence.universe_snapshot_set_digest
        assert entry.evaluation_assumptions_digest == evidence.evaluation_assumptions_digest
    assert len({entry.variant_registration_digest for entry in evidence.ledger_entries}) == 2
    _assert_receipt_invariants(evidence)
    assert edge_leakage_bias_evidence_payload_is_well_formed(edge_leakage_bias_evidence_to_dict(evidence)) is True
    assert manifest is not None


def test_ledger_is_deterministic_and_order_insensitive() -> None:
    reordered = _ledger(
        parameter_bounds=tuple(reversed(_BOUNDS)),
        windows=tuple(reversed(_WINDOWS)),
        variants=tuple(
            replace(variant, parameter_assignment=tuple(reversed(variant.parameter_assignment)))
            for variant in reversed(_VARIANTS)
        ),
        evaluation_assumptions=tuple(reversed(_ASSUMPTIONS)),
    )
    assert reordered == _ledger()


def test_milestone_profile_regression_through_ef5() -> None:
    intake, manifest, admission = _chain()
    for artifact, verify in (
        (intake, verify_edge_idea_intake_evidence),
        (manifest, verify_edge_source_packet_evidence),
        (admission, verify_edge_strategy_spec_admission),
    ):
        assert _flags(artifact) == dict(edge_gate_claim_profile(artifact.gate_id))  # type: ignore[attr-defined]
        assert artifact.preregistration_sealed is False  # type: ignore[attr-defined]
        assert artifact.performance_data_consumed is False  # type: ignore[attr-defined]
        assert verify(artifact).intact is True
    ready = _ledger()
    assert _flags(ready) == dict(edge_gate_claim_profile("EF-5"))
    assert (ready.preregistration_sealed, ready.performance_data_consumed) == (True, False)
    rejected = _ledger(expected_root_intake_digest="b" * 64, policy=None)
    assert rejected.status is EdgeEvidenceStatus.REJECTED
    assert (rejected.preregistration_sealed, rejected.performance_data_consumed) == (False, False)


# --- performance firewall (I5) --------------------------------------------------------------------------------------

_PERFORMANCE_TOKENS = (
    "pnl",
    "return",
    "sharpe",
    "hit_rate",
    "profit",
    "drawdown",
    "expectancy",
    "performance",
    "winner",
    "best",
    "selected",
    "walk_forward",
    "oos_result",
)
_INPUT_TYPES = (
    EdgeParameterBound,
    EdgeParameterAssignment,
    EdgeVariantRegistration,
    EdgeLabelThresholdStructure,
    EdgeEvaluationAssumption,
    EdgeUniverseMember,
    EdgeUniverseSnapshot,
    EdgePreregisteredWindow,
    EdgeLeakageProof,
)


def test_builders_and_input_types_accept_no_performance_surface() -> None:
    names = set(inspect.signature(build_edge_leakage_bias_evidence).parameters)
    names |= set(inspect.signature(build_edge_preregistration_policy).parameters)
    for cls in _INPUT_TYPES:
        names |= {field.name for field in fields(cls)}
    offending = {name for name in names if any(token in name for token in _PERFORMANCE_TOKENS)}
    assert offending == set()
    assert "multiple_testing_count" not in names
    assert "performance_data_consumed" not in names


def test_module_imports_no_performance_or_statistics_substrate() -> None:
    tree = ast.parse(Path(ledger_module.__file__).read_text(encoding="utf-8"))
    modules = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    forbidden = ("walk_forward", "pbo", "sharpe", "pnl", "return_series", "stage4", "metrics")
    assert not {module for module in modules if any(token in module for token in forbidden)}


# --- post-hoc selection / ledger immutability attack matrix ----------------------------------------------------------


def _forged(evidence: EdgeLeakageBiasEvidence, **changes: object) -> EdgeLeakageBiasEvidence:
    return _redigest(replace(evidence, **changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"primary_variant_id": "v-alt"},
        {
            "variants": (
                *_VARIANTS,
                EdgeVariantRegistration(
                    "v-winner",
                    (
                        EdgeParameterAssignment("entry_zscore", "2.900000000000000000"),
                        EdgeParameterAssignment("lookback_days", "7.000000000000000000"),
                    ),
                ),
            )
        },
        {"parameter_bounds": (replace(_BOUNDS[0], upper="9.000000000000000000"), _BOUNDS[1])},
        {"label_threshold_structures": (replace(_STRUCTURES[0], definition="enter above a tuned zscore"),)},
        {"evaluation_assumptions": (replace(_ASSUMPTIONS[0], model_id="cheaper-fee-model-v2"), *_ASSUMPTIONS[1:])},
        {"windows": (_WINDOWS[0],)},
        {"multiple_testing_count": 1},
        {"approved_min_oos_window_count": 1},
    ],
)
def test_post_seal_mutations_never_verify(changes: dict[str, object]) -> None:
    sealed = _ledger()
    verification = verify_edge_leakage_bias_evidence(_forged(sealed, **changes))
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize(
    ("overrides", "expected_need"),
    [
        ({"primary_variant_id": "v-alt"}, "preregistration_policy_variant_ledger_mismatch"),
        (
            {
                "variants": (
                    *_VARIANTS,
                    EdgeVariantRegistration(
                        "v-winner",
                        (
                            EdgeParameterAssignment("entry_zscore", "2.900000000000000000"),
                            EdgeParameterAssignment("lookback_days", "7.000000000000000000"),
                        ),
                    ),
                )
            },
            "preregistration_policy_variant_ledger_mismatch",
        ),
        (
            {"parameter_bounds": (replace(_BOUNDS[0], upper="9.000000000000000000"), _BOUNDS[1])},
            "preregistration_policy_parameter_bounds_mismatch",
        ),
        (
            {"label_threshold_structures": (replace(_STRUCTURES[0], definition="enter above a tuned zscore"),)},
            "preregistration_policy_variant_ledger_mismatch",
        ),
        (
            {"evaluation_assumptions": (replace(_ASSUMPTIONS[0], model_id="cheaper-fee-model-v2"), *_ASSUMPTIONS[1:])},
            "preregistration_policy_variant_ledger_mismatch",
        ),
    ],
)
def test_post_hoc_rebuild_under_the_original_approval_needs_new_governance(
    overrides: dict[str, object], expected_need: str
) -> None:
    approved_policy = _ledger().preregistration_policy_binding
    assert approved_policy is not None
    policy = edge_preregistration_policy_from_payload(json.loads(approved_policy.snapshot_json))
    rebuilt = _ledger(policy=policy, **overrides)
    assert rebuilt.status is EdgeEvidenceStatus.READY
    assert rebuilt.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert _code(expected_need) in rebuilt.verdict_reason_codes
    assert rebuilt.advances is False
    assert rebuilt.approved_min_oos_window_count is None


def test_multiple_testing_count_is_derived_and_duplicates_are_refused() -> None:
    assert _ledger(variants=_VARIANTS[:1], primary_variant_id="v-primary").multiple_testing_count == 1
    with pytest.raises(EdgeLeakageBiasEvidenceError, match="variant_id_duplicate"):
        _ledger(variants=(_VARIANTS[0], replace(_VARIANTS[1], variant_id="v-primary")), policy=None)
    with pytest.raises(EdgeLeakageBiasEvidenceError, match="variant_parameter_assignment_duplicate"):
        _ledger(variants=(_VARIANTS[0], replace(_VARIANTS[0], variant_id="v-copy")), policy=None)
    with pytest.raises(EdgeLeakageBiasEvidenceError, match="primary_variant_id_unregistered"):
        _ledger(primary_variant_id="v-winner", policy=None)


@pytest.mark.parametrize(
    ("assignment", "expected"),
    [
        ((EdgeParameterAssignment("entry_zscore", "2.000000000000000000"),), "variant_parameter_unassigned"),
        (
            (
                EdgeParameterAssignment("entry_zscore", "2.000000000000000000"),
                EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
                EdgeParameterAssignment("leverage", "2.000000000000000000"),
            ),
            "variant_parameter_unbound",
        ),
        (
            (
                EdgeParameterAssignment("entry_zscore", "3.000000000000000001"),
                EdgeParameterAssignment("lookback_days", "14.000000000000000000"),
            ),
            "variant_parameter_out_of_bounds",
        ),
    ],
)
def test_variant_assignments_outside_the_preregistered_bounds_fail(assignment: tuple, expected: str) -> None:
    evidence = _ledger(variants=(replace(_VARIANTS[0], parameter_assignment=assignment), _VARIANTS[1]))
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert any(code.startswith(_code(expected)) for code in evidence.verdict_reason_codes)
    _assert_receipt_invariants(evidence)


def test_label_threshold_structure_must_reference_bound_parameters() -> None:
    evidence = _ledger(label_threshold_structures=(replace(_STRUCTURES[0], parameter_ids=("exit_zscore",)),))
    assert _code("label_threshold_structure_parameter_unbound:entry_threshold:exit_zscore") in _verdict_codes(evidence)


# --- leakage / repaint matrix (I12) -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("proof", "expected"),
    [
        (
            replace(_PROOF, feature_timestamps=(replace(_FEATURE, event_time_ns=10_001),)),
            "feature_event_time_after_decision",
        ),
        (
            replace(_PROOF, feature_timestamps=(replace(_FEATURE, available_at_ns=10_001),)),
            "feature_available_at_after_decision",
        ),
        (
            replace(_PROOF, feature_timestamps=(replace(_FEATURE, uses_current_bar=True),)),
            "current_bar_usage_forbidden",
        ),
        (
            replace(
                _PROOF, feature_timestamps=(replace(_FEATURE, is_candle_or_bar_derived=True, finalized_at_ns=None),)
            ),
            "feature_finalized_at_missing",
        ),
        (
            replace(_PROOF, indicator_policies=(ValidationIndicatorPolicy("funding_zscore", True, None),)),
            "repaint_confirmation_rule_missing",
        ),
        (replace(_PROOF, funding_observations=(replace(_FUNDING, final_rate=None),)), "funding_final_rate_unavailable"),
        (
            replace(_PROOF, funding_observations=(replace(_FUNDING, finalized_at_ns=None),)),
            "funding_unfinalized_at_decision",
        ),
    ],
)
def test_structured_leakage_violations_are_machine_evaluated_negative_evidence(
    proof: EdgeLeakageProof, expected: str
) -> None:
    evidence = _ledger(leakage_proof=proof)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.leakage_repaint_status == "REJECT"
    assert _code(f"leakage_bias_repaint:{expected}") in _verdict_codes(evidence)
    _assert_receipt_invariants(evidence)


def test_confirmed_repaint_risk_indicator_passes() -> None:
    proof = replace(_PROOF, indicator_policies=(ValidationIndicatorPolicy("funding_zscore", True, "close_confirmed"),))
    assert _ledger(leakage_proof=proof).gate_verdict is EdgeGateVerdict.PASS


@pytest.mark.parametrize(
    ("proof", "status"),
    [
        (replace(_PROOF, needs_research_reasons=("funding-archive-completeness",)), "NEEDS_RESEARCH"),
        (replace(_PROOF, insufficient_evidence_reasons=("funding-sample-too-short",)), "INSUFFICIENT_EVIDENCE"),
    ],
)
def test_unresolved_leakage_proof_stays_an_external_fact_need(proof: EdgeLeakageProof, status: str) -> None:
    evidence = _ledger(leakage_proof=proof)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert evidence.leakage_repaint_status == status
    assert evidence.advances is False
    _assert_receipt_invariants(evidence)


@pytest.mark.parametrize(
    ("proof", "expected"),
    [
        (replace(_PROOF, feature_timestamps=()), "leakage_proof_feature_missing:funding_zscore"),
        (
            replace(_PROOF, feature_timestamps=(_FEATURE, replace(_FEATURE, feature_name="basis_zscore"))),
            "leakage_proof_feature_unregistered:basis_zscore",
        ),
        (
            replace(_PROOF, indicator_policies=(ValidationIndicatorPolicy("basis_zscore", False, None),)),
            "leakage_proof_indicator_unregistered:basis_zscore",
        ),
    ],
)
def test_proof_feature_set_must_equal_the_authenticated_spec_feature_set(
    proof: EdgeLeakageProof, expected: str
) -> None:
    evidence = _ledger(leakage_proof=proof)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code(expected) in _verdict_codes(evidence)


@pytest.mark.parametrize(
    ("assumptions", "expected"),
    [
        (_ASSUMPTIONS[1:], "leakage_bias_repaint:fee_assumption_missing"),
        ((_ASSUMPTIONS[0], _ASSUMPTIONS[2]), "leakage_bias_repaint:slippage_assumption_missing"),
        (_ASSUMPTIONS[:2], "leakage_bias_repaint:funding_assumption_missing"),
    ],
)
def test_required_cost_and_funding_assumptions_are_enforced(assumptions: tuple, expected: str) -> None:
    evidence = _ledger(evaluation_assumptions=assumptions)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code(expected) in _verdict_codes(evidence)


def test_unresolved_assumption_model_is_an_external_fact_need() -> None:
    evidence = _ledger(evaluation_assumptions=(replace(_ASSUMPTIONS[0], model_digest=None), *_ASSUMPTIONS[1:]))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert _code("evaluation_assumption_unresolved:fee_model") in _verdict_codes(evidence)


# --- survivorship matrix (I13) ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        (replace(_SNAPSHOT, as_of_ns=2_500), "window_universe_snapshot_after_window_start:w1"),
        (replace(_SNAPSHOT, members=_SNAPSHOT.members[:1]), "window_universe_missing_spec_instrument:w1:ETH-PERPETUAL"),
        (
            replace(_SNAPSHOT, members=(_SNAPSHOT.members[0], EdgeUniverseMember("ETH-PERPETUAL", 1_500, None))),
            "universe_member_listed_after_snapshot:universe-a:ETH-PERPETUAL",
        ),
        (
            replace(_SNAPSHOT, members=(_SNAPSHOT.members[0], EdgeUniverseMember("ETH-PERPETUAL", 200, 900))),
            "universe_member_delisted_before_snapshot:universe-a:ETH-PERPETUAL",
        ),
        (
            replace(_SNAPSHOT, members=(_SNAPSHOT.members[0], EdgeUniverseMember("ETH-PERPETUAL", 200, 4_500))),
            "spec_instrument_delisted_before_window_end:w2:ETH-PERPETUAL",
        ),
    ],
)
def test_point_in_time_universe_inconsistencies_are_negative_evidence(
    snapshot: EdgeUniverseSnapshot, expected: str
) -> None:
    evidence = _ledger(universe_snapshots=(snapshot,))
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code(expected) in _verdict_codes(evidence)
    assert evidence.survivorship_internal_consistency_proven is False
    assert evidence.survivorship_external_truth_basis == "external_membership_truth_unresolved"
    _assert_receipt_invariants(evidence)


def test_unbound_membership_evidence_is_never_claimed_proven() -> None:
    evidence = _ledger(universe_snapshots=(replace(_SNAPSHOT, membership_evidence_digest=None),))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert _code("survivorship_membership_evidence_unresolved:universe-a") in _verdict_codes(evidence)
    assert evidence.survivorship_internal_consistency_proven is True
    assert evidence.survivorship_external_truth_basis == "external_membership_truth_unresolved"


def test_bound_membership_evidence_without_approval_is_not_attested() -> None:
    evidence = _ledger(policy=None)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.survivorship_external_truth_basis == "external_membership_truth_unresolved"


def test_survivorship_proof_has_no_caller_boolean() -> None:
    for cls in (EdgeUniverseSnapshot, EdgeUniverseMember, EdgePreregisteredWindow):
        assert not [field.name for field in fields(cls) if field.type in ("bool", bool)]
    assert (
        "survivorship_internal_consistency_proven" not in inspect.signature(build_edge_leakage_bias_evidence).parameters
    )


# --- governance matrix (I9) --------------------------------------------------------------------------------------------


def _approved_digest() -> str:
    return _ledger(policy=None).variant_ledger_digest


@pytest.mark.parametrize(
    ("policy_factory", "expected"),
    [
        (lambda: None, {"preregistration_policy_missing"}),
        (lambda: _policy(_approved_digest(), approved=False), {"preregistration_policy_not_ready"}),
        (lambda: _policy(_approved_digest(), min_oos_window_count=None), {"preregistration_policy_not_ready"}),
        (lambda: _policy(None), {"preregistration_policy_not_ready", "preregistration_policy_variant_ledger_mismatch"}),
        (
            lambda: _policy(_approved_digest(), candidate_strategy_id="beta-funding-carry"),
            {"preregistration_policy_candidate_mismatch"},
        ),
        (lambda: _policy(_approved_digest(), correlation_id="corr-2"), {"preregistration_policy_correlation_mismatch"}),
        (
            lambda: _policy(_approved_digest(), parameter_bounds=_BOUNDS[:1]),
            {"preregistration_policy_parameter_bounds_mismatch"},
        ),
        (lambda: _policy("9" * 64), {"preregistration_policy_variant_ledger_mismatch"}),
    ],
)
def test_governance_gaps_are_needs_governance_approval(policy_factory: object, expected: set[str]) -> None:
    evidence = _ledger(policy=policy_factory())  # type: ignore[operator]
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert _verdict_codes(evidence) == {_code(code) for code in expected}
    assert evidence.approved_min_oos_window_count is None
    _assert_receipt_invariants(evidence)


def test_malformed_or_tampered_policy_is_an_integrity_rejection() -> None:
    wrong_anchor = _ledger(policy_digest="0" * 64)
    assert wrong_anchor.status is EdgeEvidenceStatus.REJECTED
    assert wrong_anchor.integrity_reason_codes == (_code("preregistration_policy_digest_mismatch"),)
    _assert_receipt_invariants(wrong_anchor)
    forged = replace(_policy(_approved_digest(), approved=False), approved=True)
    forged = replace(forged, policy_digest=edge_preregistration_policy_digest(forged))
    tampered = _ledger(policy=forged)
    assert tampered.status is EdgeEvidenceStatus.REJECTED
    assert any("preregistration_policy_integrity_failure" in code for code in tampered.integrity_reason_codes)
    _assert_receipt_invariants(tampered)


def test_policy_records_approval_only_and_rejects_every_missing_item() -> None:
    ready = _policy(_approved_digest())
    assert ready.status is EdgePreregistrationPolicyStatus.POLICY_READY
    assert verify_edge_preregistration_policy(ready).intact is True
    assert edge_preregistration_policy_from_payload(edge_preregistration_policy_to_dict(ready)) == ready
    empty = build_edge_preregistration_policy(
        policy_id="p", correlation_id="corr-1", candidate_strategy_id="alpha-funding-carry", parameter_bounds=()
    )
    assert empty.status is EdgePreregistrationPolicyStatus.POLICY_REJECTED
    assert {code.split(":", 1)[1] for code in empty.reason_codes} == {
        "approval_digest_missing",
        "approval_reference_missing",
        "min_oos_window_count_missing",
        "not_approved",
        "variant_ledger_approval_missing",
    }


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"min_oos_window_count": 0}, "preregistration_policy_min_oos_window_count_invalid"),
        ({"min_oos_window_count": True}, "preregistration_policy_min_oos_window_count_invalid"),
        ({"approved_variant_ledger_digest": "A" * 64}, "preregistration_policy_variant_ledger_digest_invalid"),
        ({"approved": "yes"}, "preregistration_policy_approved_invalid"),
        ({"approval_reference": "api_key approval"}, "forbidden_scope_token:preregistration_policy_approval_reference"),
    ],
)
def test_malformed_policy_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError, match=f"^{_code(code)}$"):
        _policy("a" * 64, **overrides)


# --- predecessor propagation and truthful receipts --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("state", "verdict"),
    [("needs_governance", EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL), ("fail", EdgeGateVerdict.FAIL)],
)
def test_non_advancing_admission_propagates_its_blocking_verdict(state: str, verdict: EdgeGateVerdict) -> None:
    intake, _, admission = _chain(admission_state=state)
    evidence = _ledger(admission=admission, policy=None, expected_root_intake_digest=intake.intake_digest)  # type: ignore[attr-defined]
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is verdict
    assert _code(f"predecessor_not_advanced:{verdict.value}") in _verdict_codes(evidence)
    _assert_receipt_invariants(evidence)


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"expected_predecessor_digest": "a" * 64}, "admission_digest_mismatch"),
        ({"correlation_id": "corr-2"}, "admission_correlation_mismatch"),
        ({"expected_root_intake_digest": "b" * 64}, "chain_splice_root_intake_mismatch"),
    ],
)
def test_chain_failures_are_truthful_rejected_receipts(overrides: dict[str, object], expected: str) -> None:
    evidence = _ledger(policy=None, **overrides)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code(expected),)
    _assert_receipt_invariants(evidence)


def test_rejected_admission_receipt_is_never_evaluated() -> None:
    intake, _, admission = _chain(admission_state="rejected")
    evidence = _ledger(admission=admission, policy=None)
    assert evidence.integrity_reason_codes == (_code("admission_rejected"),)
    assert intake is not None
    _assert_receipt_invariants(evidence)


def test_valid_admission_from_candidate_a_cannot_be_spliced_beneath_candidate_b() -> None:
    other_intake, _, _ = _chain(intake_id="intake-2")
    evidence = _ledger(policy=None, expected_root_intake_digest=other_intake.intake_digest)  # type: ignore[attr-defined]
    assert evidence.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)


def test_reprove_chain_detects_nested_splices_and_refuses_non_bindings() -> None:
    evidence = _ledger()
    codes, chain = reprove_edge_admitted_chain(
        evidence.predecessor_binding, root_intake_digest=evidence.root_intake_digest, correlation_id="corr-1"
    )
    assert codes == () and chain is not None
    payload = json.loads(evidence.predecessor_binding.snapshot_json)
    other_manifest = _chain(intake_id="intake-2")[1]
    payload["predecessor_binding"]["snapshot"] = json.loads(
        edge_canonical_json(edge_source_packet_evidence_to_dict(other_manifest))  # type: ignore[arg-type]
    )
    spliced = EdgeAuthorityBinding(
        snapshot_json=edge_canonical_json(payload), expected_digest=evidence.predecessor_digest
    )
    codes, chain = reprove_edge_admitted_chain(
        spliced, root_intake_digest=evidence.root_intake_digest, correlation_id="corr-1"
    )
    assert chain is None and codes
    with pytest.raises(EdgeLeakageBiasEvidenceError):
        reprove_edge_admitted_chain({"snapshot": {}}, root_intake_digest="a" * 64, correlation_id="corr-1")  # type: ignore[arg-type]


# --- construction errors ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"parameter_bounds": (replace(_BOUNDS[0], lower="4.000000000000000000"),)}, "parameter_bound_range_invalid"),
        ({"parameter_bounds": (replace(_BOUNDS[0], lower="1.0"),)}, "parameter_bound_lower_invalid"),
        ({"parameter_bounds": (_BOUNDS[0], _BOUNDS[0])}, "parameter_bound_duplicate"),
        ({"label_threshold_structures": ()}, "label_threshold_structures_empty"),
        (
            {"label_threshold_structures": (replace(_STRUCTURES[0], kind="signal"),)},
            "label_threshold_structure_kind_invalid",
        ),
        ({"evaluation_assumptions": (_ASSUMPTIONS[0], _ASSUMPTIONS[0])}, "evaluation_assumption_duplicate"),
        (
            {"evaluation_assumptions": (replace(_ASSUMPTIONS[0], model_digest="X"),)},
            "evaluation_assumption_model_digest_invalid",
        ),
        ({"universe_snapshots": ()}, "universe_snapshots_empty"),
        ({"universe_snapshots": (replace(_SNAPSHOT, members=()),)}, "universe_snapshot_members_empty"),
        (
            {"universe_snapshots": (replace(_SNAPSHOT, members=(EdgeUniverseMember("BTC-PERPETUAL", 500, 400),)),)},
            "universe_member_listing_interval_invalid",
        ),
        (
            {"universe_snapshots": (_SNAPSHOT, replace(_SNAPSHOT, snapshot_id="universe-b"))},
            "universe_snapshot_unreferenced",
        ),
        ({"windows": ()}, "windows_empty"),
        ({"windows": (replace(_WINDOWS[0], oos_start_ns=2_500),)}, "window_interval_invalid"),
        ({"windows": (_WINDOWS[0], replace(_WINDOWS[1], window_id="w1"))}, "window_id_duplicate"),
        (
            {"windows": (_WINDOWS[0], replace(_WINDOWS[1], in_sample_end_ns=3_400, oos_start_ns=3_500))},
            "window_oos_overlap",
        ),
        (
            {"windows": (replace(_WINDOWS[0], universe_snapshot_id="universe-z"),)},
            "window_universe_snapshot_unregistered",
        ),
        ({"windows": (replace(_WINDOWS[0], in_sample_start_ns=True),)}, "window_in_sample_start_ns_invalid"),
        ({"variants": ()}, "variants_empty"),
        ({"leakage_proof": {"decision_timestamp_ns": 1}}, "leakage_proof_malformed"),
        ({"leakage_proof": replace(_PROOF, decision_timestamp_ns=0)}, "leakage_proof_decision_timestamp_ns_invalid"),
        (
            {"leakage_proof": replace(_PROOF, funding_observations=(replace(_FUNDING, final_rate=float("nan")),))},
            "leakage_proof_funding_final_rate_invalid",
        ),
        (
            {"leakage_proof": replace(_PROOF, feature_timestamps=(_FEATURE, _FEATURE))},
            "leakage_proof_feature_duplicate",
        ),
        (
            {"leakage_proof": replace(_PROOF, feature_timestamps=(replace(_FEATURE, uses_current_bar=1),))},
            "leakage_proof_feature_current_bar_flag_invalid",
        ),
        (
            {"leakage_proof": replace(_PROOF, needs_research_reasons=("Needs Research",))},
            "leakage_proof_needs_research_reason_invalid",
        ),
        ({"ledger_id": "ledger scheduler"}, "forbidden_scope_token:ledger_id"),
        ({"expected_root_intake_digest": "B" * 64}, "root_intake_digest_invalid"),
        ({"expected_predecessor_digest": None}, "predecessor_expected_digest_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError, match=f"^{_code(code)}$"):
        _ledger(policy=None, **overrides)


@pytest.mark.parametrize(
    ("admission", "code"),
    [
        (None, "predecessor_malformed"),
        ({"admission_id": "admission-1"}, "predecessor_malformed"),
        (object.__new__(EdgeStrategySpecAdmissionEvidence), "predecessor_not_serializable"),
    ],
)
def test_malformed_predecessor_is_a_construction_error(admission: object, code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError, match=f"^{_code(code)}$"):
        build_edge_leakage_bias_evidence(
            admission,  # type: ignore[arg-type]
            expected_predecessor_digest="a" * 64,
            expected_root_intake_digest="a" * 64,
            ledger_id="ledger-1",
            correlation_id="corr-1",
            parameter_bounds=_BOUNDS,
            label_threshold_structures=_STRUCTURES,
            evaluation_assumptions=_ASSUMPTIONS,
            universe_snapshots=(_SNAPSHOT,),
            windows=_WINDOWS,
            variants=_VARIANTS,
            primary_variant_id="v-primary",
            leakage_proof=_PROOF,
        )


@pytest.mark.parametrize(
    ("policy", "policy_digest", "code"),
    [
        (None, "a" * 64, "preregistration_policy_expected_digest_unexpected"),
        ({"policy_id": "p"}, "a" * 64, "preregistration_policy_malformed"),
        (object.__new__(EdgePreregistrationPolicy), "a" * 64, "preregistration_policy_not_serializable"),
    ],
)
def test_malformed_policy_arguments_are_construction_errors(policy: object, policy_digest: object, code: str) -> None:
    with pytest.raises(EdgeLeakageBiasEvidenceError, match=f"^{_code(code)}$"):
        _ledger(policy=policy, policy_digest=policy_digest)


# --- RC1: builder domain equals verifier reassembly domain ------------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"predecessor_binding": EdgeAuthorityBinding(snapshot_json='{"a":1}', expected_digest="a" * 64)},
        {"predecessor_binding": None},
        {"preregistration_policy_binding": EdgeAuthorityBinding(snapshot_json="{}", expected_digest="a" * 64)},
        {"root_intake_digest": ""},
    ],
)
def test_partial_binding_and_anchor_states_never_verify(replacement: dict[str, object]) -> None:
    verification = verify_edge_leakage_bias_evidence(replace(_ledger(), **replacement))
    assert verification.intact is False
    assert len(verification.reason_codes) == 1


def _mutated_payload(path: tuple[object, ...], value: object) -> dict:
    payload = json.loads(edge_canonical_json(edge_leakage_bias_evidence_to_dict(_ledger())))
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
        (("preregistration_policy_binding", "snapshot", "approved"), "true"),
        (("windows", 0, "oos_start_ns"), "3000"),
        (("leakage_proof", "funding_observations", 0, "final_rate"), "0.0001"),
        (("leakage_proof", "feature_timestamps", 0, "uses_current_bar"), 0),
        (("ledger_entries", 0, "variant_registration_digest"), None),
        (("universe_snapshots", 0, "members", 0, "delisted_at_ns"), 1.5),
        (("multiple_testing_count",), "2"),
        (("preregistration_sealed",), 1),
        (("variants", 0, "parameter_assignment"), _UNSET),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    assert edge_leakage_bias_evidence_payload_is_well_formed(_mutated_payload(path, value)) is False


# --- RC2: public verifier totality ------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeLeakageBiasEvidence:
    copy = replace(_ledger())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    7,
    "ledger",
    object(),
    {},
    [],
    object.__new__(EdgeLeakageBiasEvidence),
    object.__new__(EdgePreregistrationPolicy),
    _corrupted(variants=None),
    _corrupted(leakage_proof={"decision_timestamp_ns": 1}),
    _corrupted(ledger_entries=(object(),)),
    _corrupted(predecessor_binding=object.__new__(EdgeAuthorityBinding)),
    _corrupted(multiple_testing_count=float("inf")),
    _corrupted(windows=(replace(_WINDOWS[0], oos_end_ns=float("nan")),)),
    _corrupted(primary_variant_id="v-winner"),
    _corrupted(status="SEALED"),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifiers_are_total_for_any_object(artifact: object) -> None:
    for verify, cls in (
        (verify_edge_leakage_bias_evidence, EdgeLeakageBiasEvidence),
        (verify_edge_preregistration_policy, EdgePreregistrationPolicy),
    ):
        verification = verify(artifact)
        assert type(verification) is EdgeEvidenceVerification
        if type(artifact) is not cls:
            assert verification.intact is False
    assert verify_edge_leakage_bias_evidence(artifact).intact is False


def test_policy_verifier_is_total_for_corrupted_policies() -> None:
    policy = _policy("a" * 64)
    for name, value in (("parameter_bounds", None), ("min_oos_window_count", "2"), ("reason_codes", 1)):
        copy = replace(policy)
        object.__setattr__(copy, name, value)
        assert verify_edge_preregistration_policy(copy).intact is False


# --- RC3: builder/verifier round trips for every state ----------------------------------------------------------------

_STATE_BUILDERS = {
    "pass": lambda: _ledger(),
    "fail": lambda: _ledger(leakage_proof=replace(_PROOF, feature_timestamps=())),
    "needs_external_facts": lambda: _ledger(universe_snapshots=(replace(_SNAPSHOT, membership_evidence_digest=None),)),
    "needs_governance_approval": lambda: _ledger(policy=None),
    "rejected_chain": lambda: _ledger(policy=None, correlation_id="corr-2"),
    "rejected_policy": lambda: _ledger(policy_digest="0" * 64),
}


@pytest.mark.parametrize("state", sorted(_STATE_BUILDERS))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _STATE_BUILDERS[state]()
    _assert_receipt_invariants(evidence)
    expected = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected


# --- RC4: binding canonicality ----------------------------------------------------------------------------------------


def test_bindings_are_canonical_and_noncanonical_in_memory_bindings_never_verify() -> None:
    evidence = _ledger()
    for binding in (evidence.predecessor_binding, evidence.preregistration_policy_binding):
        assert binding is not None
        assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = replace(
        evidence.predecessor_binding,
        snapshot_json=json.dumps(json.loads(evidence.predecessor_binding.snapshot_json), indent=1),
    )
    verification = verify_edge_leakage_bias_evidence(replace(evidence, predecessor_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- structural non-claims --------------------------------------------------------------------------------------------


def test_permanent_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    defaults = {field.name: field.default for field in fields(EdgeLeakageBiasEvidence)}
    assert {name: defaults[name] for name, _ in EDGE_PERMANENT_NON_CLAIM_FLAGS} == dict(EDGE_PERMANENT_NON_CLAIM_FLAGS)
    flag_names = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    for builder in (build_edge_leakage_bias_evidence, build_edge_preregistration_policy):
        assert not flag_names & set(inspect.signature(builder).parameters)


@pytest.mark.parametrize(
    ("flag", "value"),
    [
        ("edge_proven", True),
        ("candidate_admitted_to_paper", True),
        ("kill_criteria_sealed", True),
        ("performance_data_consumed", True),
        ("preregistration_sealed", False),
        ("oos_evidence_consumed", True),
    ],
)
def test_forged_claims_fail_verification(flag: str, value: bool) -> None:
    verification = verify_edge_leakage_bias_evidence(_forged(_ledger(), **{flag: value}))
    assert verification.intact is False


# --- structural purity ------------------------------------------------------------------------------------------------

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
    return ast.parse(Path(ledger_module.__file__).read_text(encoding="utf-8"))


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
        "crypto_core.strategy.spec",
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_source_packet_evidence",
        "crypto_core.validation.edge_strategy_spec_admission",
        "crypto_core.validation.leakage_bias_repaint",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    constructors = {"EdgeLeakageBiasEvidence": 0, "EdgePreregistrationPolicy": 0, "EdgeVariantLedgerEntry": 0}
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(_module_tree()) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        for name in constructors:
            constructors[name] += names.count(name)
    assert constructors == {"EdgeLeakageBiasEvidence": 1, "EdgePreregistrationPolicy": 1, "EdgeVariantLedgerEntry": 1}
    assert "EdgeLeakageBiasEvidence" in calls_by_function["_assemble_ledger"]
    assert "_assemble_ledger" in calls_by_function["build_edge_leakage_bias_evidence"]
    assert "_assemble_ledger" in calls_by_function["_reassemble_ledger"]
    assert "build_edge_preregistration_policy" in calls_by_function["_reassemble_policy"]
    assert "evaluate_leakage_bias_repaint" in calls_by_function["_leakage_reasons"]
