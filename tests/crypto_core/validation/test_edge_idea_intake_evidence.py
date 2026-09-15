"""Adversarial contract tests for Edge Factory EF-2 edge idea intake evidence."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from enum import Enum
from pathlib import Path

import pytest

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import SourcePacketRightsStatus, build_source_packet, source_packet_to_dict
from crypto_core.validation import edge_idea_intake_evidence as intake_module
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    EdgeIdeaIntakeEvidenceError,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    canonical_edge_kill_criteria,
    edge_idea_intake_evidence_digest,
    edge_idea_intake_evidence_to_dict,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criterion_to_dict,
    resolve_edge_gate_verdict,
    verify_edge_idea_intake_evidence,
)

_CONTENT_DIGEST = "c" * 64
_APPROVAL_DIGEST = "a" * 64
_RESOLUTION_DIGEST = "d" * 64
_PREFIX = "edge_idea_intake_evidence:"
_FLAGS = dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_NEED = "venue_funding_interval_mechanics"


def _packet(**overrides: object):
    kwargs: dict[str, object] = {
        "packet_id": "pkt-funding-carry-001",
        "source_type": "academic_paper",
        "source_reference": "doi:10.0000/funding-carry",
        "source_title": "Perpetual funding premia persistence",
        "rights_status": "own_research",
        "edge_hypothesis": "Perpetual funding premia persist long enough to pay a delta-neutral carry holder",
        "content_digest": _CONTENT_DIGEST,
        "market_scope_tags": ("perp", "btc", "eth"),
        "data_requirement_hints": ("funding_rate", "mark_price"),
    }
    kwargs.update(overrides)
    return build_source_packet(**kwargs)  # type: ignore[arg-type]


def _criterion(
    criterion_id: str = "max_drawdown_breach",
    *,
    metric_id: object = "max_drawdown_fraction",
    comparator: object = EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
    threshold: object = "0.250000000000000000",
    evaluation_basis: object = "rolling_30_utc_days",
) -> EdgeKillCriterion:
    return EdgeKillCriterion(
        criterion_id=criterion_id,
        metric_id=metric_id,  # type: ignore[arg-type]
        comparator=comparator,  # type: ignore[arg-type]
        threshold=threshold,  # type: ignore[arg-type]
        evaluation_basis=evaluation_basis,  # type: ignore[arg-type]
    )


def _draft() -> tuple[EdgeKillCriterion, ...]:
    return (
        _criterion(),
        _criterion(
            "funding_flip_persistence",
            metric_id="negative_funding_interval_count",
            comparator=EdgeKillCriterionComparator.KILL_IF_ABOVE,
            threshold="12.000000000000000000",
            evaluation_basis="rolling_7_utc_days",
        ),
    )


def _kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "intake_id": "intake-funding-carry-001",
        "correlation_id": "corr-funding-carry-001",
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Leveraged long demand pays a persistent funding premium to delta-neutral carry",
        "data_requirement_keys": (DataRequirementKey.MARK_PRICE, DataRequirementKey.FUNDING_RATE),
        "declared_regime_dependence": "positive_funding_premium_regime",
        "kill_criteria_draft": _draft(),
        "kill_criteria_thresholds_approved": True,
        "kill_criteria_approval_reference": "governance-kill-criteria-approval-001",
        "kill_criteria_approval_digest": _APPROVAL_DIGEST,
    }
    kwargs.update(overrides)
    return kwargs


def _build(packet=None, **overrides: object) -> EdgeIdeaIntakeEvidence:
    packet = _packet() if packet is None else packet
    kwargs = _kwargs(**overrides)
    kwargs.setdefault("expected_source_packet_digest", packet.packet_digest)
    return build_edge_idea_intake_evidence(packet, **kwargs)  # type: ignore[arg-type]


def _reseal(evidence: EdgeIdeaIntakeEvidence, **changes: object) -> EdgeIdeaIntakeEvidence:
    forged = replace(evidence, **changes)
    return replace(forged, intake_digest=edge_idea_intake_evidence_digest(forged))


def _reseal_packet(packet, **changes: object):
    forged = replace(packet, **changes)
    body = source_packet_to_dict(forged)
    del body["packet_digest"]
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(forged, packet_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _codes(evidence: EdgeIdeaIntakeEvidence) -> tuple[str, ...]:
    return verify_edge_idea_intake_evidence(evidence).reason_codes


# --- 1. Happy path and determinism ---------------------------------------------------------------------------


def test_happy_path_is_ready_pass_and_advances() -> None:
    evidence = _build()
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.advances is True
    assert evidence.integrity_reason_codes == ()
    assert evidence.verdict_reason_codes == ()
    assert evidence.verified_source_packet_digest == evidence.expected_source_packet_digest == _packet().packet_digest
    assert evidence.source_packet_id == "pkt-funding-carry-001"
    assert evidence.source_packet_usable_for_compilation is True
    assert evidence.data_requirement_keys == ("funding_rate", "mark_price")
    assert [item.criterion_id for item in evidence.kill_criteria_draft] == [
        "funding_flip_persistence",
        "max_drawdown_breach",
    ]
    assert evidence.kill_criteria_lifecycle_stage == "DRAFT"
    assert evidence.kill_criteria_sealed is False
    assert evidence.kill_criteria_digest == edge_kill_criteria_digest(_draft())
    verification = verify_edge_idea_intake_evidence(evidence)
    assert verification.intact is True
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == evidence.intake_digest


def test_digest_is_canonical_sha256_of_public_payload_without_self_digest() -> None:
    evidence = _build()
    payload = edge_idea_intake_evidence_to_dict(evidence)
    carried = payload.pop("intake_digest")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert carried == hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    assert carried == edge_idea_intake_evidence_digest(evidence)
    assert json.loads(verify_edge_idea_intake_evidence(evidence).canonical_json) == edge_idea_intake_evidence_to_dict(
        evidence
    )


def test_identical_semantic_input_yields_identical_bytes_and_digest() -> None:
    first, second = _build(), _build()
    assert first == second
    assert (
        verify_edge_idea_intake_evidence(first).canonical_json
        == verify_edge_idea_intake_evidence(second).canonical_json
    )


def test_order_irrelevant_inputs_cannot_change_identity() -> None:
    fee_need, interval_need = "venue_fee_schedule", _NEED
    base = _build(
        external_fact_needs=(interval_need, fee_need),
        external_fact_resolutions={interval_need: _RESOLUTION_DIGEST, fee_need: "e" * 64},
    )
    permuted = _build(
        data_requirement_keys=("funding_rate", DataRequirementKey.MARK_PRICE),
        kill_criteria_draft=tuple(reversed(_draft())),
        external_fact_needs=[fee_need, interval_need],
        external_fact_resolutions={fee_need: "e" * 64, interval_need: _RESOLUTION_DIGEST},
    )
    assert base.intake_digest == permuted.intake_digest
    assert base.gate_verdict is EdgeGateVerdict.PASS


def test_semantic_change_changes_digest() -> None:
    assert _build().intake_digest != _build(edge_family="funding_basis_carry_v2").intake_digest
    assert _build().intake_digest != _build(correlation_id="corr-funding-carry-002").intake_digest


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _build().advances = False  # type: ignore[misc]


# --- 2. Malformed input --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"expected_source_packet_digest": "A" * 64}, "expected_source_packet_digest_invalid"),
        ({"intake_id": ""}, "intake_id_invalid"),
        ({"intake_id": " intake-001"}, "intake_id_invalid"),
        ({"candidate_strategy_id": 7}, "candidate_strategy_id_invalid"),
        ({"economic_rationale": "line\nbreak"}, "economic_rationale_invalid"),
        ({"data_requirement_keys": ()}, "data_requirement_keys_empty"),
        ({"data_requirement_keys": "funding_rate"}, "data_requirement_keys_malformed"),
        ({"data_requirement_keys": ("price",)}, "data_requirement_key_unknown"),
        (
            {"data_requirement_keys": (DataRequirementKey.FUNDING_RATE, "funding_rate")},
            "data_requirement_key_duplicate",
        ),
        ({"kill_criteria_draft": ()}, "kill_criteria_empty"),
        ({"kill_criteria_draft": ({"criterion_id": "max_drawdown_breach"},)}, "kill_criterion_malformed"),
        ({"kill_criteria_draft": (_criterion(), _criterion())}, "kill_criterion_duplicate"),
        ({"kill_criteria_draft": (_criterion("Max Drawdown"),)}, "kill_criterion_id_invalid"),
        ({"kill_criteria_draft": (_criterion(metric_id="max drawdown"),)}, "kill_criterion_metric_id_invalid"),
        ({"kill_criteria_draft": (_criterion(evaluation_basis=""),)}, "kill_criterion_evaluation_basis_invalid"),
        ({"kill_criteria_draft": (_criterion(threshold="0.25"),)}, "kill_criterion_threshold_invalid"),
        ({"kill_criteria_draft": (_criterion(threshold=0.25),)}, "kill_criterion_threshold_invalid"),
        ({"kill_criteria_draft": (_criterion(threshold="-0.000000000000000000"),)}, "kill_criterion_threshold_invalid"),
        ({"kill_criteria_draft": (_criterion(threshold="NaN"),)}, "kill_criterion_threshold_invalid"),
        ({"kill_criteria_draft": (_criterion(comparator="kill_if_above"),)}, "kill_criterion_comparator_invalid"),
        ({"external_fact_needs": (_NEED, _NEED)}, "external_fact_need_duplicate"),
        ({"external_fact_needs": ("Venue Fees",)}, "external_fact_need_invalid"),
        ({"external_fact_resolutions": {"undeclared_need": _RESOLUTION_DIGEST}}, "external_fact_resolution_undeclared"),
        (
            {"external_fact_needs": (_NEED,), "external_fact_resolutions": {_NEED: "not-a-digest"}},
            "external_fact_resolution_digest_invalid",
        ),
        ({"external_fact_resolutions": [(_NEED, _RESOLUTION_DIGEST)]}, "external_fact_resolutions_malformed"),
        ({"kill_criteria_thresholds_approved": "yes"}, "kill_criteria_thresholds_approved_invalid"),
        ({"kill_criteria_approval_digest": "z" * 64}, "kill_criteria_approval_digest_invalid"),
        ({"kill_criteria_approval_reference": ""}, "kill_criteria_approval_reference_invalid"),
    ],
)
def test_malformed_input_raises(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=re.escape(_PREFIX + code)):
        _build(**overrides)


def test_non_source_packet_raises() -> None:
    kwargs = _kwargs(expected_source_packet_digest=_packet().packet_digest)
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="source_packet_malformed"):
        build_edge_idea_intake_evidence(source_packet_to_dict(_packet()), **kwargs)  # type: ignore[arg-type]


# --- 3. SourcePacket provenance re-proof ---------------------------------------------------------------------


def test_source_packet_anchor_mismatch_is_rejected_not_evaluated() -> None:
    evidence = _build(expected_source_packet_digest="0" * 64)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.advances is False
    assert evidence.integrity_reason_codes == (_PREFIX + "source_packet_digest_mismatch",)
    assert evidence.verdict_reason_codes == ()
    assert evidence.verified_source_packet_digest == ""
    assert verify_edge_idea_intake_evidence(evidence).intact is True


def test_tampered_source_packet_without_reseal_is_rejected() -> None:
    packet = replace(_packet(), edge_hypothesis="A different hypothesis entirely")
    evidence = _build(packet, expected_source_packet_digest=packet.packet_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _PREFIX + "source_packet_digest_mismatch" in evidence.integrity_reason_codes


@pytest.mark.parametrize(
    ("packet_factory", "code"),
    [
        (
            lambda: _reseal_packet(_packet(rights_status="restricted"), usable_for_compilation=True, risk_flags=()),
            "source_packet_noncanonical",
        ),
        (lambda: _reseal_packet(_packet(), market_scope_tags=("perp", "btc")), "source_packet_noncanonical"),
        (lambda: _reseal_packet(_packet(), real_orders_enabled=True), "source_packet_noncanonical"),
        (lambda: _reseal_packet(_packet(), schema_version="source-packet.v0"), "source_packet_noncanonical"),
        (lambda: _reseal_packet(_packet(), edge_hypothesis="BIST30 momentum carry"), "source_packet_rebuild_failed"),
        (lambda: _reseal_packet(_packet(), content_digest="short"), "source_packet_rebuild_failed"),
    ],
)
def test_resealed_source_packet_breaking_builder_invariants_is_rejected(packet_factory, code: str) -> None:
    packet = packet_factory()
    evidence = _build(packet, expected_source_packet_digest=packet.packet_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.integrity_reason_codes == (_PREFIX + code,)


def test_non_serializable_source_packet_is_rejected_without_raw_error() -> None:
    packet = replace(_packet(), source_type="academic_paper")
    evidence = _build(packet, expected_source_packet_digest=_packet().packet_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_PREFIX + "source_packet_malformed_payload",)


def test_restricted_source_rights_are_ready_fail_valid_negative_evidence() -> None:
    evidence = _build(_packet(rights_status=SourcePacketRightsStatus.RESTRICTED))
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.advances is False
    assert evidence.source_packet_usable_for_compilation is False
    assert evidence.verdict_reason_codes == (_PREFIX + "source_packet_not_usable_for_compilation",)
    assert verify_edge_idea_intake_evidence(evidence).intact is True


# --- 4. Scope leakage ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"edge_family": "funding_bist30_carry"}, "edge_family"),
        ({"economic_rationale": "Borsa Istanbul carry transfer"}, "economic_rationale"),
        ({"candidate_strategy_id": "matriks-carry"}, "candidate_strategy_id"),
        ({"declared_regime_dependence": "kap disclosure regime"}, "declared_regime_dependence"),
        ({"kill_criteria_draft": (_criterion(metric_id="bist_drawdown_fraction"),)}, "kill_criterion_metric_id"),
        ({"kill_criteria_approval_reference": "bist-governance-approval"}, "kill_criteria_approval_reference"),
    ],
)
def test_bist_leakage_raises(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=re.escape(f"bist_scope_leakage:{field}")):
        _build(**overrides)


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"economic_rationale": "Switch to live trading after the paper window"}, "economic_rationale"),
        ({"economic_rationale": "Carry harvested through a private_api funding endpoint"}, "economic_rationale"),
        ({"intake_id": "intake-place_order-001"}, "intake_id"),
        ({"edge_family": "carry_scheduler_loop"}, "edge_family"),
        ({"declared_regime_dependence": "regime tracked by client_order_id"}, "declared_regime_dependence"),
        ({"correlation_id": "corr-credentials-001"}, "correlation_id"),
        (
            {"kill_criteria_draft": (_criterion(evaluation_basis="go-live_rolling_window"),)},
            "kill_criterion_evaluation_basis",
        ),
    ],
)
def test_forbidden_live_private_order_scheduler_tokens_raise(overrides: dict[str, object], field: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=re.escape(f"forbidden_scope_token:{field}")):
        _build(**overrides)


def test_ordinary_words_containing_forbidden_fragments_are_not_leakage() -> None:
    evidence = _build(economic_rationale="Short-lived delivery basis in kappa-weighted perpetual funding")
    assert evidence.gate_verdict is EdgeGateVerdict.PASS


# --- 5. Governance -------------------------------------------------------------------------------------------


def test_missing_governance_approval_needs_governance_and_never_advances() -> None:
    kwargs = _kwargs()
    for name in (
        "kill_criteria_thresholds_approved",
        "kill_criteria_approval_reference",
        "kill_criteria_approval_digest",
    ):
        del kwargs[name]
    packet = _packet()
    evidence = build_edge_idea_intake_evidence(packet, expected_source_packet_digest=packet.packet_digest, **kwargs)  # type: ignore[arg-type]
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.advances is False
    assert evidence.verdict_reason_codes == (_PREFIX + "kill_criteria_thresholds_not_approved",)
    assert evidence.kill_criteria_approval_reference is None
    assert evidence.kill_criteria_approval_digest is None


def test_incomplete_approval_needs_governance() -> None:
    evidence = _build(kill_criteria_approval_reference=None)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_PREFIX + "kill_criteria_approval_incomplete",)


def test_pending_threshold_needs_governance_even_when_approval_is_recorded() -> None:
    evidence = _build(kill_criteria_draft=(_criterion(threshold=None),))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (
        _PREFIX + "kill_criterion_threshold_pending_governance:max_drawdown_breach",
    )


def test_governance_defaults_are_fail_closed_and_module_holds_no_governance_number() -> None:
    parameters = inspect.signature(build_edge_idea_intake_evidence).parameters
    assert parameters["kill_criteria_thresholds_approved"].default is False
    assert parameters["kill_criteria_approval_reference"].default is None
    assert parameters["kill_criteria_approval_digest"].default is None
    source = Path(intake_module.__file__).read_text(encoding="utf-8")
    assert re.search(r"\d\.\d{18}", source) is None
    assert not any(isinstance(node, ast.Constant) and type(node.value) is float for node in ast.walk(ast.parse(source)))


# --- 6. External facts ---------------------------------------------------------------------------------------


def test_unresolved_external_fact_need_is_needs_external_facts_not_guessed() -> None:
    evidence = _build(external_fact_needs=(_NEED,))
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert evidence.advances is False
    assert evidence.unresolved_external_fact_needs == (_NEED,)
    assert evidence.verdict_reason_codes == (_PREFIX + f"external_fact_need_unresolved:{_NEED}",)
    assert evidence.external_fact_resolution_trust == "controller_attested_opaque_resolution_digest.v1"


def test_resolved_external_fact_need_passes_with_attested_digest_recorded() -> None:
    evidence = _build(external_fact_needs=(_NEED,), external_fact_resolutions={_NEED: _RESOLUTION_DIGEST})
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.external_fact_resolutions == ((_NEED, _RESOLUTION_DIGEST),)
    assert evidence.unresolved_external_fact_needs == ()


def test_verdict_precedence_is_fail_then_external_facts_then_governance() -> None:
    everything = _build(
        _packet(rights_status="restricted"),
        external_fact_needs=(_NEED,),
        kill_criteria_thresholds_approved=False,
    )
    assert everything.gate_verdict is EdgeGateVerdict.FAIL
    assert len(everything.verdict_reason_codes) == 3
    needs_both = _build(external_fact_needs=(_NEED,), kill_criteria_thresholds_approved=False)
    assert needs_both.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert _PREFIX + "kill_criteria_thresholds_not_approved" in needs_both.verdict_reason_codes
    assert resolve_edge_gate_verdict([], [], []) is EdgeGateVerdict.PASS
    assert resolve_edge_gate_verdict([], [], ["g"]) is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert resolve_edge_gate_verdict([], ["e"], ["g"]) is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert resolve_edge_gate_verdict(["f"], ["e"], ["g"]) is EdgeGateVerdict.FAIL


# --- 7. Kill-criteria canonical helpers ----------------------------------------------------------------------


def test_kill_criteria_digest_is_order_insensitive_and_payload_roundtrips() -> None:
    draft = _draft()
    assert edge_kill_criteria_digest(draft) == edge_kill_criteria_digest(list(reversed(draft)))
    payload = [edge_kill_criterion_to_dict(item) for item in canonical_edge_kill_criteria(draft)]
    assert edge_kill_criteria_from_payload(payload) == canonical_edge_kill_criteria(draft)
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="kill_criteria_payload_noncanonical"):
        edge_kill_criteria_from_payload(list(reversed(payload)))
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="kill_criteria_payload_malformed"):
        edge_kill_criteria_from_payload([{**payload[0], "sealed": True}])
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="kill_criterion_comparator_invalid"):
        edge_kill_criteria_from_payload([{**payload[0], "comparator": "kill_if_sideways"}])


# --- 8. Digest tamper and re-derivation ----------------------------------------------------------------------


def test_field_tamper_without_reseal_fails_verification() -> None:
    forged = replace(_build(), edge_family="momentum")
    assert _PREFIX + "self_digest_mismatch" in _codes(forged)


def test_resealed_needs_verdict_upgraded_to_pass_fails_rederivation() -> None:
    forged = _reseal(
        _build(external_fact_needs=(_NEED,)),
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    codes = _codes(forged)
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert _PREFIX + "verdict_rederivation_mismatch" in codes


def test_resealed_erasure_of_unresolved_needs_fails() -> None:
    forged = _reseal(
        _build(external_fact_needs=(_NEED,)),
        unresolved_external_fact_needs=(),
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    assert _PREFIX + "unresolved_external_fact_needs_mismatch" in _codes(forged)


def test_resealed_restricted_posture_flip_fails() -> None:
    forged = _reseal(
        _build(_packet(rights_status="restricted")),
        source_packet_usable_for_compilation=True,
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    assert _PREFIX + "source_packet_posture_inconsistent" in _codes(forged)


def test_resealed_approval_forgery_and_pending_threshold_erasure_fail() -> None:
    pending = _build(kill_criteria_draft=(_criterion(threshold=None),))
    forged = _reseal(pending, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "verdict_rederivation_mismatch" in _codes(forged)
    criteria_swap = _reseal(_build(), kill_criteria_draft=(_criterion(threshold="0.990000000000000000"),))
    assert _PREFIX + "kill_criteria_digest_mismatch" in _codes(criteria_swap)


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_resealed_structural_claim_fails_verification(flag: str) -> None:
    forged = _reseal(_build(), **{flag: not _FLAGS[flag]})
    assert _PREFIX + "structural_non_claim_violation" in _codes(forged)


@pytest.mark.parametrize(
    "changes",
    [
        {"status": EdgeEvidenceStatus.REJECTED},
        {"gate_verdict": EdgeGateVerdict.NOT_EVALUATED},
        {"advances": False},
        {"integrity_reason_codes": (_PREFIX + "source_packet_digest_mismatch",)},
    ],
)
def test_resealed_status_verdict_conflation_fails(changes: dict[str, object]) -> None:
    assert _PREFIX + "status_verdict_incoherent" in _codes(_reseal(_build(), **changes))


@pytest.mark.parametrize(
    "changes",
    [
        {"regime_label_binding_status": "RF_LABEL_BOUND"},
        {"regime_evidence_status": "regime_evidence_available"},
        {"kill_criteria_lifecycle_stage": "SEALED"},
        {"external_fact_resolution_trust": "reproven"},
    ],
)
def test_resealed_constant_tamper_fails(changes: dict[str, object]) -> None:
    assert _PREFIX + "constant_field_mismatch" in _codes(_reseal(_build(), **changes))


def test_forged_or_non_serializable_evidence_never_raises() -> None:
    assert _codes(replace(_build(), kill_criteria_draft=(object(),))) == (_PREFIX + "evidence_serialization_failed",)  # type: ignore[arg-type]
    assert _codes(replace(_build(), status="READY")) == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]
    assert _codes("not evidence") == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]
    malformed = _reseal(_build(), kill_criteria_draft=("max_drawdown_breach",))
    assert _PREFIX + "evidence_semantics_malformed" in _codes(malformed)


# --- 9. Structural non-overclaim, vocabulary and source surface ----------------------------------------------


def test_structural_non_claims_are_defaults_and_cannot_be_set_by_the_builder() -> None:
    evidence = _build()
    for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is expected
    defaults = {field.name: field.default for field in fields(EdgeIdeaIntakeEvidence) if field.name in _FLAGS}
    assert defaults == _FLAGS
    parameters = set(inspect.signature(build_edge_idea_intake_evidence).parameters)
    assert parameters.isdisjoint(_FLAGS)
    assert parameters.isdisjoint({"regime_label_binding_status", "regime_evidence_status", "status", "gate_verdict"})
    assert _FLAGS["paper_only"] is True
    assert all(value is False for name, value in _FLAGS.items() if name != "paper_only")


def test_regime_dependence_uses_the_pending_pattern_and_invents_no_label() -> None:
    evidence = _build()
    assert evidence.declared_regime_dependence == "positive_funding_premium_regime"
    assert (
        evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING == "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
    )
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE == "regime_evidence_unavailable"
    assert evidence.regime_evidence_available is False
    regime_enums = [
        name
        for name, value in vars(intake_module).items()
        if isinstance(value, type) and issubclass(value, Enum) and "regime" in name.lower()
    ]
    assert regime_enums == []


def test_status_and_verdict_vocabularies_are_disjoint() -> None:
    assert {item.value for item in EdgeEvidenceStatus}.isdisjoint({item.value for item in EdgeGateVerdict})


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    for evidence in (
        _build(
            _packet(rights_status="restricted"), external_fact_needs=(_NEED,), kill_criteria_thresholds_approved=False
        ),
        _build(expected_source_packet_digest="0" * 64),
    ):
        for codes in (evidence.integrity_reason_codes, evidence.verdict_reason_codes):
            assert list(codes) == sorted(set(codes))
            assert all(code.startswith(_PREFIX) for code in codes)


_FORBIDDEN_MODULES = (
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "socket",
    "requests",
    "httpx",
    "aiohttp",
    "threading",
    "asyncio",
    "multiprocessing",
    "subprocess",
    "os",
    "pathlib",
    "shutil",
    "sqlite3",
    "crypto_core.service",
    "crypto_core.execution",
    "crypto_core.venue",
    "crypto_core.runtime",
    "crypto_core.orchestrator",
    "crypto_core.temporal",
    "crypto_core.session",
    "crypto_core.portfolio",
)
_FORBIDDEN_CALLS = {"open", "Path", "float", "now", "utcnow", "time", "time_ns", "perf_counter", "monotonic", "getenv"}


def test_source_has_no_forbidden_runtime_surfaces_and_imports_only_public_names() -> None:
    tree = ast.parse(Path(intake_module.__file__).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
            if node.module.startswith("crypto_core.data"):
                assert node.module == "crypto_core.data.requirements"
            if node.module.startswith("crypto_core"):
                assert all(not alias.name.startswith("_") for alias in node.names)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS


def test_ready_evidence_with_substrate_owned_inner_whitespace_still_reverifies() -> None:
    evidence = _build(_packet(packet_id="pkt\tfunding-carry-001"))
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.source_packet_id == "pkt\tfunding-carry-001"
    assert verify_edge_idea_intake_evidence(evidence).intact is True


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(intake_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_edge_idea_intake_evidence(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["edge_idea_intake_evidence.py"]
