"""Tests for the RF-6 regime filter admission decision (``regime_filter_admission_decision``).

Fixtures: ONE authentic EF-3 world shared by the Edge Factory chain and the regime chain — the EF-5 test module's EF-2 →
EF-4 chain over a final funding series and a final mark-price series (``mark-final``), both declared by the admitted
spec. The EF-5 preregistration (V2) registers the governed up/down RF-2 policy over ``mark-final``; RF-3 reads
authenticated PIT records of that series, RF-4 labels them, and RF-5 proves stability across two as-of coordinates. One
correlation (``corr-1``) runs through every artifact. Every close, threshold, approval and identifier is a SYNTHETIC TEST
VALUE; expected outcomes come from the move strings and the upstream artifacts themselves, never from RF-6.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import inspect
import json
import re
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.regime_filter_admission_decision as rf6_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeInputRegimeFilter,
    EdgeLeakageBiasEvidence,
    EdgeSurvivorshipClaimScope,
    edge_leakage_bias_evidence_digest,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_from_payload,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    RegimeFeatureClass,
    RegimeFeaturePolicy,
)
from crypto_core.validation.regime_feature_series_evidence import build_regime_feature_series_evidence
from crypto_core.validation.regime_filter_admission_decision import (
    REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS,
    REGIME_FILTER_ADMISSION_RULE_SET_DIGEST,
    RegimeFilterAdmissionDecision,
    RegimeFilterAdmissionError,
    RegimeFilterAdmissionInputs,
    build_regime_filter_admission_decision,
    regime_filter_admission_decision_digest,
    regime_filter_admission_decision_to_dict,
    regime_filter_admission_rule_set,
    verify_regime_filter_admission_decision,
)
from crypto_core.validation.regime_label_evidence import (
    RegimeLabelEvidence,
    RegimeLabelInputs,
    build_regime_label_evidence,
)
from crypto_core.validation.regime_stability_evidence import (
    RegimeStabilityEvidence,
    RegimeStabilityInputs,
    RegimeStabilityStatus,
    build_regime_stability_evidence,
    regime_stability_evidence_digest,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so cached fixtures are shared with their own tests
    import test_edge_leakage_bias_evidence as ef5t
    import test_regime_feature_policy as rf2t
    import test_regime_feature_series_evidence as rf3t
    import test_regime_label_evidence as rf4t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_leakage_bias_evidence as ef5t
    from tests.crypto_core.validation import test_regime_feature_policy as rf2t
    from tests.crypto_core.validation import test_regime_feature_series_evidence as rf3t
    from tests.crypto_core.validation import test_regime_label_evidence as rf4t

_PREFIX = "regime_filter_admission_decision"
SOURCE = Path(rf6_module.__file__).read_text(encoding="utf-8")
D0 = rf3t.D0
MARK = "mark-final"
CORRELATION = "corr-1"
F2 = RegimeFeatureClass.F2_DRAWDOWN_STATE
PASS, FAIL = EdgeGateVerdict.PASS, EdgeGateVerdict.FAIL
NEEDS_GOVERNANCE, NEEDS_EXTERNAL = EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
V1, V2 = "edge-leakage-bias-evidence.v1", "edge-leakage-bias-evidence.v2"


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RF-6 construction error."""

    return pytest.raises(RegimeFilterAdmissionError, match=f"^{re.escape(code(text))}$")


# --- the shared EF-3 world ------------------------------------------------------------------------------------------


def _input_series() -> tuple[object, ...]:
    return (ef5t._series("funding-final", "funding_rate"), ef5t._series(MARK, "mark_price"))


@functools.cache
def ef_world() -> tuple[object, object, object, EdgeSourcePacketEvidence]:
    """``(intake, admission, binding, manifest)``: the authentic chain whose spec declares funding and mark prices."""

    intake, admission, binding = ef5t._chain_with_series(_input_series(), ("funding_rate", "mark_price"))
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(admission.predecessor_binding))
    return intake, admission, binding, manifest


@functools.cache
def other_manifest() -> EdgeSourcePacketEvidence:
    """A second authentic EF-3 manifest of the same intake and series under another manifest id: another source world."""

    intake = ef_world()[0]
    registry = default_perp_data_requirement_registry()
    return build_edge_source_packet_evidence(
        intake,  # type: ignore[arg-type]
        expected_root_intake_digest=intake.intake_digest,  # type: ignore[attr-defined]
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-2",
        correlation_id=CORRELATION,
        input_series=_input_series(),  # type: ignore[arg-type]
    )


def filter_policy(
    *, governed: bool = True, threshold: str = "0", approval: dict[str, object] | None = None
) -> RegimeFeaturePolicy:
    """The up/down regime policy over ``mark-final`` (STRESSED on a drop) with SYNTHETIC stability values.

    ``approval`` overrides fields of an approval built for the exact draft (for example its kind or reference).
    """

    values: dict[str, object] = {
        "features": [rf2t.feature(rf2t.DD, F2, lookback=2, series=MARK)],
        "rules": [
            rf2t.rule(1, "STRESSED", rf2t.predicate(rf2t.DD, rf4t.GT, rf2t.d(threshold))),
            rf2t.rule(2, "CALM", rf2t.predicate(rf2t.DD, rf4t.LTE, rf2t.d(threshold))),
        ],
        "stability_min_overlap_days": 3,
        "stability_min_asof_gap_days": 1,
        "distribution_drift_cap": rf2t.d("0.25"),
    }
    if approval is None:
        return rf4t.updown_policy(governed=governed, **values)
    draft = rf4t.updown_policy(governed=False, **values)
    return rf4t.updown_policy(governed=False, approval=rf2t.approval_for(draft, **approval), **values)


@functools.cache
def policy() -> RegimeFeaturePolicy:
    return filter_policy()


def preregistration(*policies: RegimeFeaturePolicy, **overrides: object) -> EdgeLeakageBiasEvidence:
    """EF-5 over the shared chain registering ``policies`` (V2); with none it is the accepted V1 artifact."""

    intake, admission, binding, _ = ef_world()
    regime_filters = tuple(EdgeInputRegimeFilter(item, item.regime_feature_policy_digest) for item in policies)
    return ef5t.prereg(admission=admission, binding=binding, intake=intake, regime_filters=regime_filters, **overrides)


@functools.cache
def sealed() -> EdgeLeakageBiasEvidence:
    return preregistration(policy())


def label_world(
    moves: str, *, policy_: RegimeFeaturePolicy, manifest: EdgeSourcePacketEvidence, correlation_id: str, label_id: str
) -> tuple[RegimeLabelInputs, RegimeLabelEvidence]:
    """RF-3 over authenticated ``mark-final`` records of the move string's closes, then RF-4 for D0+2 onwards."""

    closes = rf4t.moves_closes(moves)
    records = tuple(rf3t.pit_record(D0 + index, rf3t.price(close), series=MARK) for index, close in enumerate(closes))
    series_inputs = rf3t.series_inputs(
        policy=policy_, records=records, source_manifest=manifest, last=D0 + len(closes), first_feature_day=D0 + 2
    )
    inputs = RegimeLabelInputs(
        label_id, correlation_id, policy_, series_inputs, build_regime_feature_series_evidence(series_inputs)
    )
    return inputs, build_regime_label_evidence(inputs)


def stability_world(
    earlier: str = "UDUD",
    later: str = "UDUDU",
    *,
    policy_: RegimeFeaturePolicy | None = None,
    manifest: EdgeSourcePacketEvidence | None = None,
    label_correlations: tuple[str, str] = (CORRELATION, CORRELATION),
    stability_correlation: str = CORRELATION,
) -> tuple[RegimeStabilityInputs, RegimeStabilityEvidence]:
    """RF-5 over two as-of prefixes of the moves: labels D0+2 .. D0+1+len(moves), as of the start of the last day."""

    policy_ = policy() if policy_ is None else policy_
    manifest = ef_world()[3] if manifest is None else manifest
    sides = [
        label_world(moves, policy_=policy_, manifest=manifest, correlation_id=correlation, label_id=f"rf4-{name}")
        for moves, correlation, name in zip((earlier, later), label_correlations, ("earlier", "later"))
    ]
    inputs = RegimeStabilityInputs("rf5-1", stability_correlation, policy_, *sides[0], *sides[1])
    return inputs, build_regime_stability_evidence(inputs)


@functools.cache
def default_stability() -> tuple[RegimeStabilityInputs, RegimeStabilityEvidence]:
    return stability_world()


def admission_inputs(
    *,
    stability: tuple[RegimeStabilityInputs, RegimeStabilityEvidence] | None = None,
    prereg: EdgeLeakageBiasEvidence | None = None,
    policy_: RegimeFeaturePolicy | None = None,
    **overrides: object,
) -> RegimeFilterAdmissionInputs:
    stability_inputs, stability_evidence = default_stability() if stability is None else stability
    prereg = sealed() if prereg is None else prereg
    values: dict[str, object] = {
        "admission_id": "rf6-1",
        "correlation_id": CORRELATION,
        "policy": policy() if policy_ is None else policy_,
        "preregistration": prereg,
        "expected_preregistration_digest": prereg.leakage_bias_evidence_digest,
        "expected_root_intake_digest": ef_world()[0].intake_digest,  # type: ignore[attr-defined]
        "stability_inputs": stability_inputs,
        "stability": stability_evidence,
    }
    values.update(overrides)
    return RegimeFilterAdmissionInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> RegimeFilterAdmissionDecision:
    return build_regime_filter_admission_decision(inputs)  # type: ignore[arg-type]


def decide(inputs: RegimeFilterAdmissionInputs) -> RegimeFilterAdmissionDecision:
    """Build, then re-prove by reconstruction: every decision a test reads is intact."""

    decision = build(inputs)
    verification = verify_regime_filter_admission_decision(decision, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == decision.regime_filter_admission_digest
    assert json.loads(verification.canonical_json) == regime_filter_admission_decision_to_dict(decision)
    assert {name: getattr(decision, name) for name, _ in REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS} == dict(
        REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS
    )
    assert decision.regime_filter_admitted is decision.advances is (decision.gate_verdict is PASS)
    return decision


@functools.cache
def default_decision() -> RegimeFilterAdmissionDecision:
    return decide(admission_inputs())


def reseal(decision: RegimeFilterAdmissionDecision, **changes: object) -> RegimeFilterAdmissionDecision:
    changed = replace(decision, **changes)  # type: ignore[arg-type]
    return replace(changed, regime_filter_admission_digest=regime_filter_admission_decision_digest(changed))


# --- admission ------------------------------------------------------------------------------------------------------


def test_an_exactly_preregistered_stable_filter_is_admitted_for_its_exact_spec() -> None:
    decision, ef5, rf2 = default_decision(), sealed(), policy()
    stability_inputs, stability = default_stability()
    intake, _, _, manifest = ef_world()
    assert (ef5.schema_version, ef5.gate_verdict, ef5.preregistration_sealed) == (V2, PASS, True)
    assert stability.status is RegimeStabilityStatus.STABILITY_PROVEN
    assert (decision.gate_verdict, decision.advances, decision.regime_filter_admitted) == (PASS, True, True)
    assert decision.verdict_reason_codes == ()
    assert (
        decision.preregistration_id,
        decision.preregistration_digest,
        decision.preregistration_schema_version,
        decision.preregistration_verdict,
        decision.preregistration_sealed,
    ) == (ef5.preregistration_id, ef5.leakage_bias_evidence_digest, V2, "PASS", True)
    for name in (
        "root_intake_digest",
        "candidate_strategy_id",
        "edge_family",
        "strategy_spec_digest",
        "strategy_id",
        "strategy_version",
        "pinned_instrument_universe",
        "source_manifest_digest",
        "regime_filter_set_digest",
        "registered_regime_policy_digests",
    ):
        assert getattr(decision, name) == getattr(ef5, name), name
    assert decision.root_intake_digest == intake.intake_digest  # type: ignore[attr-defined]
    assert decision.source_manifest_digest == manifest.source_packet_evidence_digest
    assert (decision.candidate_strategy_id, decision.strategy_id) == ("passive-funding-carry", "passive-funding-carry")
    assert (
        decision.policy_id,
        decision.policy_version,
        decision.policy_digest,
        decision.regime_feature_policy_digest,
        decision.policy_governed,
        decision.policy_preregistered,
    ) == (rf2.policy_id, rf2.policy_version, rf2.policy_digest, rf2.regime_feature_policy_digest, True, True)
    assert decision.registered_regime_policy_digests == (rf2.regime_feature_policy_digest,)
    assert (decision.stability_evidence_id, decision.stability_evidence_digest, decision.stability_status) == (
        stability.stability_evidence_id,
        stability.stability_evidence_digest,
        RegimeStabilityStatus.STABILITY_PROVEN,
    )
    assert (decision.earlier_as_of_ns, decision.later_as_of_ns) == (
        stability.earlier_as_of_ns,
        stability.later_as_of_ns,
    )
    sides = (stability_inputs.earlier_label_inputs, stability_inputs.later_label_inputs)
    assert decision.label_evidence_digests == (
        stability.earlier_label_evidence_digest,
        stability.later_label_evidence_digest,
    )
    assert decision.feature_series_digests == tuple(side.feature_series.feature_series_digest for side in sides)
    assert decision.pit_dataset_digests == tuple(side.feature_series_inputs.pit_dataset_digest for side in sides)
    assert all(side.feature_series.source_manifest_digest == decision.source_manifest_digest for side in sides)
    assert (decision.rule_set_id, decision.rule_set_digest) == (
        "regime_filter_admission_decision_rules.v1",
        REGIME_FILTER_ADMISSION_RULE_SET_DIGEST,
    )
    assert decision.correlation_id == ef5.correlation_id == stability.correlation_id == CORRELATION


def test_replay_of_unchanged_inputs_is_deterministic_and_never_mutates_them() -> None:
    inputs = admission_inputs()
    before = (
        edge_leakage_bias_evidence_digest(inputs.preregistration),
        regime_stability_evidence_digest(inputs.stability),
        inputs.policy.regime_feature_policy_digest,
    )
    first, second = build(inputs), build(admission_inputs())
    assert first == second == default_decision()
    assert regime_filter_admission_decision_digest(first) == first.regime_filter_admission_digest
    assert (
        edge_leakage_bias_evidence_digest(inputs.preregistration),
        regime_stability_evidence_digest(inputs.stability),
        inputs.policy.regime_feature_policy_digest,
    ) == before


# --- membership: exact, preregistered, never inferred ---------------------------------------------------------------


def test_a_v1_preregistration_never_admits_a_filter() -> None:
    v1 = preregistration()
    assert (v1.schema_version, v1.preregistration_sealed, v1.registered_regime_policy_digests) == (V1, True, ())
    decision = decide(admission_inputs(prereg=v1))
    assert (decision.gate_verdict, decision.policy_preregistered) == (FAIL, False)
    assert decision.verdict_reason_codes == (code("preregistration_has_no_regime_filter_ledger"),)
    assert (decision.preregistration_schema_version, decision.registered_regime_policy_digests) == (V1, ())
    # A V1 object that carries a regime filter ledger cannot even serialize: it never reaches membership.
    forged = replace(v1, registered_regime_policy_digests=(policy().regime_feature_policy_digest,))
    with refused("preregistration_not_serializable"):
        build(admission_inputs(prereg=forged, expected_preregistration_digest=v1.leakage_bias_evidence_digest))


def test_an_unregistered_policy_is_never_admitted() -> None:
    other = filter_policy(threshold="0.005")
    ledger = preregistration(other)
    assert (ledger.preregistration_sealed, ledger.registered_regime_policy_digests) == (
        True,
        (other.regime_feature_policy_digest,),
    )
    decision = decide(admission_inputs(prereg=ledger))
    assert (decision.gate_verdict, decision.policy_preregistered) == (FAIL, False)
    assert decision.verdict_reason_codes == (code("regime_policy_not_preregistered"),)
    admitted = decide(admission_inputs(prereg=ledger, policy_=other, stability=stability_world(policy_=other)))
    assert admitted.regime_filter_admitted is True  # the ledger admits exactly the policy it registered


def test_membership_is_the_exact_policy_self_digest_never_an_id_feature_or_content_digest() -> None:
    twin = filter_policy(approval={"approval_reference": "governance-record-2"})
    assert twin.advances is True
    assert (twin.policy_id, twin.policy_version, twin.policy_digest) == (
        policy().policy_id,
        policy().policy_version,
        policy().policy_digest,
    )
    assert [item.feature_id for item in twin.features] == [item.feature_id for item in policy().features]
    assert twin.regime_feature_policy_digest != policy().regime_feature_policy_digest
    decision = decide(admission_inputs(policy_=twin, stability=stability_world(policy_=twin)))
    assert decision.verdict_reason_codes == (code("regime_policy_not_preregistered"),)
    tighter = filter_policy(threshold="0.005")  # same feature id, policy id and version, another threshold
    assert [item.feature_id for item in tighter.features] == [item.feature_id for item in policy().features]
    decision = decide(admission_inputs(policy_=tighter, stability=stability_world(policy_=tighter)))
    assert decision.verdict_reason_codes == (code("regime_policy_not_preregistered"),)
    tree = ast.parse(SOURCE)
    membership = [
        ast.unparse(node)
        for node in ast.walk(tree)
        if isinstance(node, ast.Compare) and "registered_regime_policy_digests" in ast.unparse(node)
    ]
    assert membership == ["policy.regime_feature_policy_digest in preregistration.registered_regime_policy_digests"]


def test_a_retrospectively_attached_policy_or_approval_never_seals_or_admits() -> None:
    v1 = preregistration()
    late = preregistration(policy(), approval=v1.approval)  # the V1 approval reused for the extended ledger
    assert (late.schema_version, late.gate_verdict, late.preregistration_sealed) == (V2, NEEDS_GOVERNANCE, False)
    assert late.verdict_reason_codes == (ef5t._code("preregistration_approval_decision_structure_digest_mismatch"),)
    decision = decide(admission_inputs(prereg=late))
    assert decision.gate_verdict is NEEDS_GOVERNANCE
    assert decision.verdict_reason_codes == (code("preregistration_not_sealed:NEEDS_GOVERNANCE_APPROVAL"),)
    assert decision.policy_preregistered is True  # registered, but in no sealed preregistration


# --- governance ------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "approval",
    [
        None,  # no RF-2 approval
        {"approval_kind": rf2t.SYNTHETIC},  # TEST_ONLY_SYNTHETIC
        {"approved_policy_digest": "e" * 64},  # stale
    ],
)
def test_an_ungoverned_rf2_policy_never_admits(approval: dict[str, object] | None) -> None:
    ungoverned = filter_policy(governed=False) if approval is None else filter_policy(approval=approval)
    assert ungoverned.advances is False
    ledger = preregistration(ungoverned)
    assert (ledger.gate_verdict, ledger.preregistration_sealed) == (NEEDS_GOVERNANCE, False)
    assert ledger.verdict_reason_codes == (
        ef5t._code(f"regime_filter_policy_not_governed:{ungoverned.regime_feature_policy_digest}"),
    )
    world = stability_world(policy_=ungoverned)
    assert world[1].status is RegimeStabilityStatus.NEEDS_GOVERNANCE_APPROVAL
    decision = decide(admission_inputs(prereg=ledger, policy_=ungoverned, stability=world))
    assert (decision.gate_verdict, decision.policy_governed, decision.policy_preregistered) == (
        NEEDS_GOVERNANCE,
        False,
        True,
    )
    assert decision.verdict_reason_codes == (
        code("policy_needs_governance_approval"),
        code("preregistration_not_sealed:NEEDS_GOVERNANCE_APPROVAL"),
        code("stability_needs_governance_approval"),
    )


@pytest.mark.parametrize(
    "overrides",
    [
        {"approve": False},
        {"approval": "mismatched"},
    ],
)
def test_a_missing_or_mismatched_preregistration_approval_never_admits(overrides: dict[str, object]) -> None:
    if overrides.get("approval") == "mismatched":
        overrides = {"approval": ef5t.approval_for(sealed(), approved_variant_ledger_digest="e" * 64)}
    ledger = preregistration(policy(), **overrides)
    assert (ledger.gate_verdict, ledger.preregistration_sealed) == (NEEDS_GOVERNANCE, False)
    decision = decide(admission_inputs(prereg=ledger))
    assert decision.verdict_reason_codes == (code("preregistration_not_sealed:NEEDS_GOVERNANCE_APPROVAL"),)


@pytest.mark.parametrize(
    ("overrides", "verdict"),
    [
        ({"variants": ef5t.variants()[:1]}, FAIL),  # searched bound values no registered variant exercises
        ({"survivorship_claim_scope": EdgeSurvivorshipClaimScope.EDGE_FAMILY_CROSS_SECTION}, NEEDS_EXTERNAL),
    ],
)
def test_an_unsealed_preregistration_never_admits(overrides: dict[str, object], verdict: EdgeGateVerdict) -> None:
    ledger = preregistration(policy(), **overrides)
    assert (ledger.status, ledger.gate_verdict, ledger.preregistration_sealed) == (
        EdgeEvidenceStatus.READY,
        verdict,
        False,
    )
    decision = decide(admission_inputs(prereg=ledger))
    assert (decision.gate_verdict, decision.regime_filter_admitted) == (verdict, False)
    assert decision.verdict_reason_codes == (code(f"preregistration_not_sealed:{verdict.value}"),)


# --- stability -------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("earlier", "later", "status", "reason"),
    [
        ("UDDU", "UUDUUDU", RegimeStabilityStatus.STABILITY_REJECTED, "stability_rejected"),  # a repainted history
        ("UD", "UDUDU", RegimeStabilityStatus.INSUFFICIENT_OVERLAP, "stability_insufficient_overlap"),
    ],
)
def test_unproven_stability_never_admits(earlier: str, later: str, status: RegimeStabilityStatus, reason: str) -> None:
    world = stability_world(earlier, later)
    assert world[1].status is status
    decision = decide(admission_inputs(stability=world))
    assert (decision.gate_verdict, decision.stability_status, decision.regime_filter_admitted) == (FAIL, status, False)
    assert decision.verdict_reason_codes == (code(reason),)


# --- identity, correlation and source --------------------------------------------------------------------------------


def test_a_wrong_candidate_root_or_preregistration_anchor_is_refused() -> None:
    other_intake, _, other_admission, other_binding = ef5t._other_chain()
    with refused("preregistration_root_intake_mismatch"):
        build(admission_inputs(expected_root_intake_digest=other_intake.intake_digest))
    with refused("preregistration_digest_mismatch"):
        build(admission_inputs(expected_preregistration_digest=preregistration().leakage_bias_evidence_digest))
    # Another candidate's sealed preregistration, even one registering this exact policy, reads another source world.
    foreign = ef5t.prereg(
        admission=other_admission,
        binding=other_binding,
        intake=other_intake,
        regime_filters=(EdgeInputRegimeFilter(policy(), policy().regime_feature_policy_digest),),
    )
    assert (foreign.preregistration_sealed, foreign.registered_regime_policy_digests) == (
        True,
        (policy().regime_feature_policy_digest,),
    )
    assert foreign.root_intake_digest != sealed().root_intake_digest
    with refused("earlier_feature_series_source_manifest_mismatch"):
        build(admission_inputs(prereg=foreign, expected_root_intake_digest=other_intake.intake_digest))


def test_a_regime_world_over_another_source_manifest_is_refused() -> None:
    world = stability_world(manifest=other_manifest())
    assert world[1].status is RegimeStabilityStatus.STABILITY_PROVEN  # an authentic world, but not EF-5's
    assert other_manifest().source_packet_evidence_digest != sealed().source_manifest_digest
    with refused("earlier_feature_series_source_manifest_mismatch"):
        build(admission_inputs(stability=world))


@pytest.mark.parametrize(
    ("world", "overrides", "reason"),
    [
        ({}, {"correlation_id": "corr-2"}, "preregistration_correlation_mismatch"),
        ({"stability_correlation": "corr-2"}, {}, "stability_correlation_mismatch"),
        ({"label_correlations": ("corr-2", CORRELATION)}, {}, "earlier_labels_correlation_mismatch"),
        ({"label_correlations": (CORRELATION, "corr-2")}, {}, "later_labels_correlation_mismatch"),
    ],
)
def test_one_correlation_runs_through_the_whole_admission_world(
    world: dict[str, object], overrides: dict[str, object], reason: str
) -> None:
    with refused(reason):
        build(admission_inputs(stability=stability_world(**world) if world else None, **overrides))  # type: ignore[arg-type]


# --- malformed, corrupted and mismatched inputs ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"admission_id": ""}, "admission_id_invalid"),
        ({"admission_id": "rf6 live"}, "forbidden_scope_token:admission_id"),
        ({"correlation_id": None}, "correlation_id_invalid"),
        ({"policy": None}, "policy_malformed"),
        ({"preregistration": None}, "preregistration_malformed"),
        ({"expected_preregistration_digest": "A" * 64}, "preregistration_expected_digest_invalid"),
        ({"expected_root_intake_digest": None}, "expected_root_intake_digest_invalid"),
        ({"stability_inputs": None}, "stability_inputs_malformed"),
        ({"stability": None}, "stability_malformed"),
    ],
)
def test_malformed_inputs_are_refused(overrides: dict[str, object], reason: str) -> None:
    with refused(reason):
        build(replace(admission_inputs(), **overrides))
    with refused("inputs_malformed"):
        build(None)


def test_corrupted_or_rejected_upstream_evidence_fails_closed() -> None:
    with refused("policy_not_intact"):
        build(admission_inputs(policy_=replace(policy(), distribution_drift_cap=rf2t.d("0.9"))))
    with refused("preregistration_not_intact"):
        build(admission_inputs(prereg=replace(sealed(), preregistration_id="prereg-x")))
    tampered = replace(sealed(), registered_regime_policy_digests=("e" * 64,))
    resealed = replace(tampered, leakage_bias_evidence_digest=edge_leakage_bias_evidence_digest(tampered))
    with refused("preregistration_not_intact"):
        build(admission_inputs(prereg=resealed))
    intake, admission, binding, _ = ef_world()
    rejected = ef5t.prereg(
        admission=admission,
        binding=binding,
        intake=intake,
        approve=False,
        regime_filters=(EdgeInputRegimeFilter(policy(), "e" * 64),),  # an anchor its snapshot never re-proves to
    )
    assert (rejected.status, rejected.gate_verdict) == (EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED)
    with refused("preregistration_rejected"):
        build(admission_inputs(prereg=rejected))
    stability_inputs, stability = default_stability()
    forged = replace(stability, overlap_day_count=99)
    forged = replace(forged, stability_evidence_digest=regime_stability_evidence_digest(forged))
    with refused("stability_not_reconstructed"):
        build(admission_inputs(stability=(stability_inputs, forged)))
    with refused("stability_reconstruction_failed"):
        build(admission_inputs(stability=(replace(stability_inputs, stability_evidence_id=""), stability)))
    twin = filter_policy(approval={"approval_reference": "governance-record-2"})
    with refused("stability_policy_mismatch"):
        build(admission_inputs(policy_=twin))


# --- the verifier ----------------------------------------------------------------------------------------------------


def test_every_field_is_digest_bound_and_reproven() -> None:
    inputs, decision = admission_inputs(), default_decision()
    for changes in (
        {"gate_verdict": FAIL},
        {"policy_preregistered": False},
        {"registered_regime_policy_digests": ()},
        {"preregistration_digest": "e" * 64},
        {"source_manifest_digest": "e" * 64},
        {"stability_status": RegimeStabilityStatus.STABILITY_REJECTED},
        {"feature_series_digests": ("e" * 64, "f" * 64)},
        {"verdict_reason_codes": (code("regime_policy_not_preregistered"),)},
    ):
        name = next(iter(changes))
        assert set(verify_regime_filter_admission_decision(reseal(decision, **changes), inputs).reason_codes) == {
            code(f"field_mismatch:{name}"),
            code("field_mismatch:regime_filter_admission_digest"),
        }
    stale = verify_regime_filter_admission_decision(replace(decision, admission_id="rf6-2"), inputs)
    assert stale.reason_codes == (code("field_mismatch:admission_id"), code("self_digest_mismatch"))
    refused_admission = decide(admission_inputs(prereg=preregistration()))
    forced = reseal(refused_admission, gate_verdict=PASS, advances=True, regime_filter_admitted=True)
    assert {
        code("field_mismatch:gate_verdict"),
        code("field_mismatch:advances"),
        code("field_mismatch:regime_filter_admitted"),
    } <= set(verify_regime_filter_admission_decision(forced, admission_inputs(prereg=preregistration())).reason_codes)
    for name, default in REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS:
        flipped = reseal(decision, **{name: not default})
        assert set(verify_regime_filter_admission_decision(flipped, inputs).reason_codes) == {
            code(f"field_mismatch:{name}"),
            code("field_mismatch:regime_filter_admission_digest"),
        }


def test_the_verifier_is_total() -> None:
    inputs, decision = admission_inputs(), default_decision()
    for value in (
        None,
        {},
        "decision",
        sealed(),
        replace(decision, gate_verdict="PASS"),
        replace(decision, stability_status="STABILITY_PROVEN"),
        replace(decision, earlier_as_of_ns=-1),
        replace(decision, label_evidence_digests=list(decision.label_evidence_digests)),
    ):
        verification = verify_regime_filter_admission_decision(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in (
            (code("decision_type_invalid"),),
            (code("decision_serialization_failed"),),
        )
    for broken in (None, replace(inputs, expected_root_intake_digest="e" * 64)):
        verification = verify_regime_filter_admission_decision(decision, broken)  # type: ignore[arg-type]
        assert verification.reason_codes == (code("decision_reconstruction_failed"),)


# --- static discipline, rule set and API ----------------------------------------------------------------------------


def test_the_module_is_pure_and_never_imports_the_runtime_regime_package() -> None:
    pit.assert_module_is_pure(
        rf6_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_leakage_bias_evidence",
            "crypto_core.validation.regime_feature_policy",
            "crypto_core.validation.regime_stability_evidence",
        },
    )
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE
    tree = ast.parse(SOURCE)
    constructors = [
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RegimeFilterAdmissionDecision"
    ]
    assert constructors == ["build_regime_filter_admission_decision"]


def test_admission_names_only_structural_false_flags_and_no_builder_can_set_them() -> None:
    flags = dict(REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS)
    assert set(flags) == ({name for name, _ in REGIME_NON_CLAIM_FLAGS} - {"regime_filter_admitted"}) | {
        "chronological_ordering_proven"
    }
    assert (flags["chronological_ordering_proven"], flags["regime_conditioned_performance_proven"]) == (False, False)
    assert {item.name: item.default for item in fields(RegimeFilterAdmissionDecision) if item.name in flags} == flags
    assert all(
        item.default is dataclasses.MISSING for item in fields(RegimeFilterAdmissionDecision) if item.name not in flags
    )
    assert all(item.default is dataclasses.MISSING for item in fields(RegimeFilterAdmissionInputs))
    assert set(inspect.signature(build_regime_filter_admission_decision).parameters) == {"inputs"}
    names = {node.id for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Attribute)}
    risky = {
        name
        for name in names
        if re.search(r"(^|_)(live|orders?|capital|scheduler|connector|shadow|execution)(_|$)", name)
    }
    assert risky <= set(flags)


def test_the_rule_set_commits_the_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_filter_admission_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_FILTER_ADMISSION_RULE_SET_DIGEST
    assert rule_set["contract_id"] == "EF5_RF6_REGIME_POLICY_PREREGISTRATION_ADMISSION_V1"
    assert "never_by_any_id" in str(rule_set["membership_rule_id"])
    assert "chronology" in str(rule_set["ordering_nonclaim_rule_id"])
    rule_set["contract_id"] = "OTHER"
    assert regime_filter_admission_rule_set()["contract_id"] == "EF5_RF6_REGIME_POLICY_PREREGISTRATION_ADMISSION_V1"


def test_the_public_api_is_exact() -> None:
    assert set(rf6_module.__all__) == {
        "REGIME_FILTER_ADMISSION_NON_CLAIM_FLAGS",
        "REGIME_FILTER_ADMISSION_RULE_SET_DIGEST",
        "RegimeFilterAdmissionDecision",
        "RegimeFilterAdmissionError",
        "RegimeFilterAdmissionInputs",
        "build_regime_filter_admission_decision",
        "regime_filter_admission_decision_digest",
        "regime_filter_admission_decision_to_dict",
        "regime_filter_admission_rule_set",
        "verify_regime_filter_admission_decision",
    }
