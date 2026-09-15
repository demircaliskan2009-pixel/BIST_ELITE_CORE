"""Adversarial contract tests for Edge Factory EF-2 edge idea intake evidence and its kill-criteria policy."""

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
    EdgeKillCriteriaPolicy,
    EdgeKillCriteriaPolicyStatus,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    canonical_edge_kill_criteria,
    edge_idea_intake_evidence_digest,
    edge_idea_intake_evidence_from_canonical_json,
    edge_idea_intake_evidence_to_dict,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criteria_policy_digest,
    edge_kill_criteria_policy_from_canonical_json,
    edge_kill_criteria_policy_to_dict,
    edge_kill_criterion_to_dict,
    edge_scope_violation,
    resolve_edge_gate_verdict,
    verify_edge_idea_intake_evidence,
    verify_edge_kill_criteria_policy,
)

_CONTENT_DIGEST = "c" * 64
_APPROVAL_DIGEST = "a" * 64
_PREFIX = "edge_idea_intake_evidence:"
_POLICY_PREFIX = "edge_kill_criteria_policy:"
_FLAGS = dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_NEED = "venue_funding_interval_mechanics"
_CORRELATION = "corr-funding-carry-001"
_DEFAULT = object()


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


def _policy(**overrides: object) -> EdgeKillCriteriaPolicy:
    kwargs: dict[str, object] = {
        "policy_id": "policy-kill-criteria-001",
        "correlation_id": _CORRELATION,
        "kill_criteria": _draft(),
        "thresholds_approved": True,
        "approval_reference": "governance-kill-criteria-approval-001",
        "approval_digest": _APPROVAL_DIGEST,
    }
    kwargs.update(overrides)
    return build_edge_kill_criteria_policy(**kwargs)  # type: ignore[arg-type]


def _kwargs(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "intake_id": "intake-funding-carry-001",
        "correlation_id": _CORRELATION,
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Leveraged long demand pays a persistent funding premium to delta-neutral carry",
        "data_requirement_keys": (DataRequirementKey.MARK_PRICE, DataRequirementKey.FUNDING_RATE),
        "declared_regime_dependence": "positive_funding_premium_regime",
        "kill_criteria_draft": _draft(),
    }
    kwargs.update(overrides)
    return kwargs


def _build(packet=None, policy: object = _DEFAULT, **overrides: object) -> EdgeIdeaIntakeEvidence:
    packet = _packet() if packet is None else packet
    kwargs = _kwargs(**overrides)
    kwargs.setdefault("expected_source_packet_digest", packet.packet_digest)
    policy = _policy() if policy is _DEFAULT else policy
    if policy is not None:
        kwargs.setdefault("kill_criteria_policy", policy)
        kwargs.setdefault("expected_kill_criteria_policy_digest", policy.policy_digest)  # type: ignore[union-attr]
    return build_edge_idea_intake_evidence(packet, **kwargs)  # type: ignore[arg-type]


def _reseal(evidence: EdgeIdeaIntakeEvidence, **changes: object) -> EdgeIdeaIntakeEvidence:
    forged = replace(evidence, **changes)
    return replace(forged, intake_digest=edge_idea_intake_evidence_digest(forged))


def _reseal_policy(policy: EdgeKillCriteriaPolicy, **changes: object) -> EdgeKillCriteriaPolicy:
    forged = replace(policy, **changes)
    return replace(forged, policy_digest=edge_kill_criteria_policy_digest(forged))


def _reseal_packet(packet, **changes: object):
    forged = replace(packet, **changes)
    body = source_packet_to_dict(forged)
    del body["packet_digest"]
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return replace(forged, packet_digest=hashlib.sha256(canonical.encode("utf-8")).hexdigest())


def _codes(evidence: object) -> tuple[str, ...]:
    return verify_edge_idea_intake_evidence(evidence).reason_codes


def _assert_ready(evidence: EdgeIdeaIntakeEvidence, verdict: EdgeGateVerdict, codes: tuple[str, ...]) -> None:
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is verdict
    assert evidence.advances is (verdict is EdgeGateVerdict.PASS)
    assert evidence.integrity_reason_codes == ()
    assert evidence.verdict_reason_codes == tuple(_PREFIX + code for code in codes)
    assert verify_edge_idea_intake_evidence(evidence).intact is True


def _assert_rejected(evidence: EdgeIdeaIntakeEvidence, codes: tuple[str, ...]) -> None:
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.advances is False
    assert evidence.verdict_reason_codes == ()
    assert evidence.integrity_reason_codes == tuple(_PREFIX + code for code in codes)
    assert verify_edge_idea_intake_evidence(evidence).intact is True


# --- 1. Happy path and determinism ---------------------------------------------------------------------------


def test_happy_path_is_ready_pass_and_advances_with_authenticated_snapshots() -> None:
    packet = _packet()
    policy = _policy()
    evidence = _build(packet, policy)
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert evidence.verified_source_packet_digest == evidence.expected_source_packet_digest == packet.packet_digest
    assert json.loads(evidence.source_packet_snapshot_json) == source_packet_to_dict(packet)
    assert evidence.source_packet_id == "pkt-funding-carry-001"
    assert evidence.source_packet_rights_status == "own_research"
    assert evidence.source_packet_usable_for_compilation is True
    assert json.loads(evidence.kill_criteria_policy_snapshot_json) == edge_kill_criteria_policy_to_dict(policy)
    assert evidence.verified_kill_criteria_policy_digest == policy.policy_digest
    assert evidence.data_requirement_keys == ("funding_rate", "mark_price")
    assert [item.criterion_id for item in evidence.kill_criteria_draft] == [
        "funding_flip_persistence",
        "max_drawdown_breach",
    ]
    assert evidence.kill_criteria_lifecycle_stage == "DRAFT"
    assert evidence.kill_criteria_sealed is False
    assert evidence.kill_criteria_digest == edge_kill_criteria_digest(_draft()) == policy.kill_criteria_digest
    assert verify_edge_idea_intake_evidence(evidence).recomputed_digest == evidence.intake_digest


def test_digest_is_canonical_sha256_of_public_payload_without_self_digest() -> None:
    evidence = _build()
    payload = edge_idea_intake_evidence_to_dict(evidence)
    carried = payload.pop("intake_digest")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert (
        carried == hashlib.sha256(canonical.encode("utf-8")).hexdigest() == edge_idea_intake_evidence_digest(evidence)
    )


def test_identical_semantic_input_yields_identical_bytes_and_order_irrelevant_input_cannot_change_identity() -> None:
    base = _build(external_fact_needs=(_NEED, "venue_fee_schedule"))
    permuted = _build(
        data_requirement_keys=("funding_rate", DataRequirementKey.MARK_PRICE),
        kill_criteria_draft=tuple(reversed(_draft())),
        external_fact_needs=["venue_fee_schedule", _NEED],
        policy=_policy(kill_criteria=list(reversed(_draft()))),
    )
    assert base == _build(external_fact_needs=(_NEED, "venue_fee_schedule"))
    assert base.intake_digest == permuted.intake_digest
    assert _build().intake_digest != _build(edge_family="funding_basis_carry_v2").intake_digest


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _build().advances = False  # type: ignore[misc]


def test_strict_parser_reconstructs_exactly_and_rejects_unknown_or_noncanonical_input() -> None:
    evidence = _build()
    canonical = verify_edge_idea_intake_evidence(evidence).canonical_json
    assert edge_idea_intake_evidence_from_canonical_json(canonical) == evidence
    payload = json.loads(canonical)
    for text in (
        json.dumps({**payload, "extra": True}, sort_keys=True, separators=(",", ":")),
        json.dumps(payload, sort_keys=True),
        json.dumps({**payload, "advances": "true"}, sort_keys=True, separators=(",", ":")),
        json.dumps({**payload, "gate_verdict": "MAYBE"}, sort_keys=True, separators=(",", ":")),
        canonical.replace('"advances":true', '"advances":NaN'),
    ):
        with pytest.raises(EdgeIdeaIntakeEvidenceError, match="intake_snapshot_malformed"):
            edge_idea_intake_evidence_from_canonical_json(text)


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
        ({"expected_kill_criteria_policy_digest": "z" * 64}, "expected_kill_criteria_policy_digest_invalid"),
        ({"kill_criteria_policy": {"policy_id": "policy-1"}}, "kill_criteria_policy_malformed"),
    ],
)
def test_malformed_input_raises(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match=re.escape(_PREFIX + code)):
        _build(**overrides)


def test_policy_argument_misuse_raises() -> None:
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="expected_kill_criteria_policy_digest_unexpected"):
        _build(policy=None, expected_kill_criteria_policy_digest="b" * 64)
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="expected_kill_criteria_policy_digest_invalid"):
        _build(policy=None, kill_criteria_policy=_policy())


def test_non_source_packet_raises() -> None:
    kwargs = _kwargs(expected_source_packet_digest=_packet().packet_digest)
    with pytest.raises(EdgeIdeaIntakeEvidenceError, match="source_packet_malformed"):
        build_edge_idea_intake_evidence(source_packet_to_dict(_packet()), **kwargs)  # type: ignore[arg-type]


# --- 3. B1: SourcePacket authority ---------------------------------------------------------------------------


def test_source_packet_anchor_mismatch_is_a_truthful_rejected_receipt() -> None:
    evidence = _build(expected_source_packet_digest="0" * 64)
    _assert_rejected(evidence, ("source_packet_digest_mismatch",))
    assert evidence.verified_source_packet_digest == ""


def test_tampered_source_packet_without_reseal_is_rejected() -> None:
    packet = replace(_packet(), edge_hypothesis="A different hypothesis entirely")
    _assert_rejected(
        _build(packet, expected_source_packet_digest=packet.packet_digest),
        ("source_packet_digest_mismatch", "source_packet_noncanonical"),
    )


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
    _assert_rejected(_build(packet, expected_source_packet_digest=packet.packet_digest), (code,))


def test_non_serializable_source_packet_is_rejected_without_raw_error() -> None:
    evidence = _build(
        replace(_packet(), source_type="academic_paper"), expected_source_packet_digest=_packet().packet_digest
    )
    _assert_rejected(evidence, ("source_packet_malformed_payload",))
    assert evidence.source_packet_snapshot_json == ""


def test_restricted_source_rights_are_ready_fail_valid_negative_evidence() -> None:
    evidence = _build(_packet(rights_status=SourcePacketRightsStatus.RESTRICTED))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("source_packet_not_usable_for_compilation",))
    assert evidence.source_packet_usable_for_compilation is False
    assert evidence.source_packet_rights_status == "restricted"


@pytest.mark.parametrize(
    "changes",
    [
        {"source_packet_rights_status": "own_research", "source_packet_usable_for_compilation": True},
        {"source_packet_id": "pkt-other-001"},
        {"verified_source_packet_digest": ""},
    ],
)
def test_resealed_copies_of_source_packet_owned_values_are_checked_against_the_snapshot(changes: dict) -> None:
    restricted = _build(_packet(rights_status="restricted"))
    forged = _reseal(restricted, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=(), **changes)
    codes = _codes(forged)
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert all(_PREFIX + f"field_mismatch:{name}" in codes for name in changes)
    assert _PREFIX + "field_mismatch:gate_verdict" in codes


def test_swapped_source_packet_snapshot_cannot_keep_a_passing_verdict() -> None:
    evidence = _build()
    restricted_snapshot = _build(_packet(rights_status="restricted")).source_packet_snapshot_json
    forged = _reseal(evidence, source_packet_snapshot_json=restricted_snapshot)
    assert _PREFIX + "field_mismatch:status" in _codes(forged)


# --- 4. B8: scope policy applies to authenticated SourcePacket text ------------------------------------------


@pytest.mark.parametrize(
    "overrides",
    [
        {"edge_hypothesis": "Funding carry rotates the api_key per venue"},
        {"edge_hypothesis": "Harvest carry through a carry_scheduler_loop"},
        {"source_title": "Carry through place_order hooks"},
        {"market_scope_tags": ("perp", "client_order_id")},
        {"data_requirement_hints": ("funding_bist30_feed",)},
    ],
)
def test_source_packet_text_accepted_by_source_packet_but_outside_edge_scope_is_rejected(overrides: dict) -> None:
    packet = _packet(**overrides)
    assert packet.paper_only is True
    _assert_rejected(_build(packet), ("source_packet_scope_violation",))


# --- 5. Scope leakage in EF-2 caller text --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"edge_family": "funding_bist30_carry"}, "edge_family"),
        ({"economic_rationale": "Borsa Istanbul carry transfer"}, "economic_rationale"),
        ({"candidate_strategy_id": "matriks-carry"}, "candidate_strategy_id"),
        ({"declared_regime_dependence": "kap disclosure regime"}, "declared_regime_dependence"),
        ({"kill_criteria_draft": (_criterion(metric_id="bist_drawdown_fraction"),)}, "kill_criterion_metric_id"),
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
    assert edge_scope_violation("Short-lived delivery basis in kappa-weighted perpetual funding") is None
    _assert_ready(
        _build(economic_rationale="Short-lived delivery basis in kappa-weighted perpetual funding"),
        EdgeGateVerdict.PASS,
        (),
    )


# --- 6. B5: governance approval lives in a digest-bound policy ------------------------------------------------


def test_policy_is_ready_digest_bound_and_reverifies() -> None:
    policy = _policy()
    assert policy.status is EdgeKillCriteriaPolicyStatus.POLICY_READY
    assert policy.ready is True
    assert policy.reason_codes == ()
    assert policy.kill_criteria_digest == edge_kill_criteria_digest(_draft())
    assert policy.policy_digest == edge_kill_criteria_policy_digest(policy)
    verification = verify_edge_kill_criteria_policy(policy)
    assert verification.intact is True
    assert edge_kill_criteria_policy_from_canonical_json(verification.canonical_json) == policy
    assert policy.policy_only is True
    assert all(getattr(policy, name) is expected for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)


@pytest.mark.parametrize(
    ("overrides", "codes"),
    [
        ({"thresholds_approved": False}, ("thresholds_not_approved",)),
        ({"approval_reference": None}, ("approval_reference_missing",)),
        ({"approval_digest": None}, ("approval_digest_missing",)),
        (
            {"kill_criteria": (_criterion(threshold=None),)},
            ("kill_criterion_threshold_missing:max_drawdown_breach",),
        ),
    ],
)
def test_policy_without_complete_approval_is_rejected_and_never_defaults(overrides: dict, codes: tuple) -> None:
    policy = _policy(**overrides)
    assert policy.status is EdgeKillCriteriaPolicyStatus.POLICY_REJECTED
    assert policy.ready is False
    assert policy.reason_codes == tuple(_POLICY_PREFIX + code for code in codes)
    assert verify_edge_kill_criteria_policy(policy).intact is True


def test_missing_policy_needs_governance_and_never_advances() -> None:
    evidence = _build(policy=None)
    _assert_ready(evidence, EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, ("kill_criteria_policy_missing",))
    assert (evidence.kill_criteria_policy_snapshot_json, evidence.expected_kill_criteria_policy_digest) == ("", "")


@pytest.mark.parametrize(
    ("policy_factory", "code"),
    [
        (lambda: _policy(thresholds_approved=False), "kill_criteria_policy_not_ready"),
        (lambda: _policy(correlation_id="corr-other-001"), "kill_criteria_policy_correlation_mismatch"),
        (lambda: _policy(kill_criteria=(_criterion(),)), "kill_criteria_policy_kill_criteria_mismatch"),
        (
            lambda: _policy(kill_criteria=(_criterion(threshold="0.300000000000000000"), _draft()[1])),
            "kill_criteria_policy_kill_criteria_mismatch",
        ),
    ],
)
def test_authentic_but_inapplicable_policy_needs_governance(policy_factory, code: str) -> None:
    _assert_ready(_build(policy=policy_factory()), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, (code,))


def test_pending_draft_threshold_cannot_be_approved() -> None:
    draft = (_criterion(threshold=None),)
    evidence = _build(kill_criteria_draft=draft, policy=_policy(kill_criteria=draft))
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert _PREFIX + "kill_criterion_threshold_pending_governance:max_drawdown_breach" in evidence.verdict_reason_codes
    assert _PREFIX + "kill_criteria_policy_not_ready" in evidence.verdict_reason_codes


def test_policy_anchor_mismatch_is_rejected() -> None:
    evidence = _build(expected_kill_criteria_policy_digest="0" * 64)
    _assert_rejected(evidence, ("kill_criteria_policy_digest_mismatch",))
    assert evidence.verified_kill_criteria_policy_digest == ""


def test_tampered_policy_without_reseal_is_rejected() -> None:
    policy = replace(_policy(), approval_digest="f" * 64)
    evidence = _build(policy=policy)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert (
        _PREFIX + "kill_criteria_policy_integrity_failure:edge_kill_criteria_policy:self_digest_mismatch"
        in evidence.integrity_reason_codes
    )
    assert verify_edge_idea_intake_evidence(evidence).intact is True


def test_resealed_forged_ready_policy_is_rejected() -> None:
    rejected = _policy(thresholds_approved=False)
    forged = _reseal_policy(rejected, status=EdgeKillCriteriaPolicyStatus.POLICY_READY, ready=True, reason_codes=())
    policy_codes = verify_edge_kill_criteria_policy(forged).reason_codes
    assert _POLICY_PREFIX + "self_digest_mismatch" not in policy_codes
    assert _POLICY_PREFIX + "field_mismatch:status" in policy_codes
    evidence = _build(policy=forged)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert any(
        code.startswith(_PREFIX + "kill_criteria_policy_integrity_failure:") for code in evidence.integrity_reason_codes
    )


def test_raw_approval_metadata_can_no_longer_create_pass() -> None:
    parameters = set(inspect.signature(build_edge_idea_intake_evidence).parameters)
    assert parameters.isdisjoint(
        {"kill_criteria_thresholds_approved", "kill_criteria_approval_reference", "kill_criteria_approval_digest"}
    )
    needs = _build(policy=None)
    forged = _reseal(needs, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "field_mismatch:gate_verdict" in _codes(forged)
    source = Path(intake_module.__file__).read_text(encoding="utf-8")
    assert re.search(r"\d\.\d{18}", source) is None
    assert not any(isinstance(node, ast.Constant) and type(node.value) is float for node in ast.walk(ast.parse(source)))


# --- 7. B6: external facts stay pending ----------------------------------------------------------------------


def test_no_external_fact_need_evaluates_normally() -> None:
    evidence = _build(external_fact_needs=())
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert (
        evidence.external_fact_resolution_policy == "declared_needs_stay_pending_no_verifiable_resolution_contract.v1"
    )


def test_declared_external_fact_need_always_stays_needs_external_facts() -> None:
    evidence = _build(external_fact_needs=(_NEED,))
    _assert_ready(evidence, EdgeGateVerdict.NEEDS_EXTERNAL_FACTS, (f"external_fact_need_unresolved:{_NEED}",))


def test_opaque_resolution_metadata_cannot_discharge_a_need() -> None:
    assert "external_fact_resolutions" not in inspect.signature(build_edge_idea_intake_evidence).parameters
    with pytest.raises(TypeError):
        _build(external_fact_needs=(_NEED,), external_fact_resolutions={_NEED: "d" * 64})
    assert not any(
        "resolution" in field.name and field.name != "external_fact_resolution_policy"
        for field in fields(EdgeIdeaIntakeEvidence)
    )
    # Upgrading the verdict while keeping the declared need is caught by reassembly. Erasing the declared need itself
    # is a different caller input: it yields a different intake digest, which the root anchor of every later gate binds.
    needs = _build(external_fact_needs=(_NEED,))
    upgraded = _reseal(needs, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "field_mismatch:gate_verdict" in _codes(upgraded)
    erased = _reseal(
        needs, external_fact_needs=(), gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=()
    )
    assert erased.intake_digest != needs.intake_digest


def test_verdict_precedence_is_fail_then_external_facts_then_governance() -> None:
    everything = _build(_packet(rights_status="restricted"), policy=None, external_fact_needs=(_NEED,))
    assert everything.gate_verdict is EdgeGateVerdict.FAIL
    assert len(everything.verdict_reason_codes) == 3
    needs_both = _build(policy=None, external_fact_needs=(_NEED,))
    assert needs_both.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert _PREFIX + "kill_criteria_policy_missing" in needs_both.verdict_reason_codes
    assert resolve_edge_gate_verdict([], [], []) is EdgeGateVerdict.PASS
    assert resolve_edge_gate_verdict([], [], ["g"]) is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert resolve_edge_gate_verdict([], ["e"], ["g"]) is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert resolve_edge_gate_verdict(["f"], ["e"], ["g"]) is EdgeGateVerdict.FAIL


# --- 8. Kill-criteria canonical helpers ----------------------------------------------------------------------


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


# --- 9. B7: truthful READY and REJECTED receipts -------------------------------------------------------------


def test_field_tamper_without_reseal_fails_verification() -> None:
    assert _PREFIX + "self_digest_mismatch" in _codes(replace(_build(), edge_family="momentum"))


def test_resealed_needs_verdict_upgraded_to_pass_fails_reassembly() -> None:
    forged = _reseal(
        _build(external_fact_needs=(_NEED,)), gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=()
    )
    codes = _codes(forged)
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert _PREFIX + "field_mismatch:gate_verdict" in codes


@pytest.mark.parametrize(
    "changes",
    [
        {"integrity_reason_codes": (_PREFIX + "source_packet_digest_mismatch",)},
        {"integrity_reason_codes": (_PREFIX + "invented_reason",)},
        {"integrity_reason_codes": ()},
    ],
)
def test_rejected_receipt_with_inconsistent_reason_codes_does_not_verify(changes: dict) -> None:
    rejected = _build(expected_kill_criteria_policy_digest="0" * 64)
    assert verify_edge_idea_intake_evidence(rejected).intact is True
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in _codes(_reseal(rejected, **changes))


def test_passing_evidence_forged_into_a_rejected_receipt_does_not_verify() -> None:
    forged = _reseal(
        _build(),
        status=EdgeEvidenceStatus.REJECTED,
        gate_verdict=EdgeGateVerdict.NOT_EVALUATED,
        advances=False,
        integrity_reason_codes=(_PREFIX + "source_packet_digest_mismatch",),
    )
    codes = _codes(forged)
    assert _PREFIX + "field_mismatch:status" in codes
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in codes


def test_malformed_rejected_semantics_do_not_verify() -> None:
    rejected = _build(expected_source_packet_digest="0" * 64)
    assert _PREFIX + "evidence_semantics_malformed" in _codes(
        _reseal(rejected, expected_source_packet_digest="not-a-digest")
    )
    assert _PREFIX + "evidence_semantics_malformed" in _codes(
        _reseal(rejected, kill_criteria_draft=("max_drawdown_breach",))
    )


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_resealed_structural_claim_fails_verification(flag: str) -> None:
    assert _PREFIX + f"field_mismatch:{flag}" in _codes(_reseal(_build(), **{flag: not _FLAGS[flag]}))


@pytest.mark.parametrize(
    "changes",
    [
        {"regime_label_binding_status": "RF_LABEL_BOUND"},
        {"regime_evidence_status": "regime_evidence_available"},
        {"kill_criteria_lifecycle_stage": "SEALED"},
        {"external_fact_resolution_policy": "resolved_by_attestation"},
    ],
)
def test_resealed_constant_tamper_fails(changes: dict[str, object]) -> None:
    (name,) = changes
    assert _PREFIX + f"field_mismatch:{name}" in _codes(_reseal(_build(), **changes))


def test_forged_or_non_serializable_evidence_never_raises() -> None:
    assert _codes(replace(_build(), kill_criteria_draft=(object(),))) == (_PREFIX + "evidence_serialization_failed",)  # type: ignore[arg-type]
    assert _codes(replace(_build(), status="READY")) == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]
    assert _codes("not evidence") == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]


# --- 10. Structural non-overclaim, vocabulary and source surface ---------------------------------------------


def test_structural_non_claims_are_defaults_and_cannot_be_set_by_the_builder() -> None:
    evidence = _build()
    for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is expected
    for cls in (EdgeIdeaIntakeEvidence, EdgeKillCriteriaPolicy):
        assert {field.name: field.default for field in fields(cls) if field.name in _FLAGS} == _FLAGS
    parameters = set(inspect.signature(build_edge_idea_intake_evidence).parameters)
    assert parameters.isdisjoint(_FLAGS)
    assert parameters.isdisjoint({"regime_label_binding_status", "regime_evidence_status", "status", "gate_verdict"})
    assert set(inspect.signature(build_edge_kill_criteria_policy).parameters).isdisjoint({*_FLAGS, "status", "ready"})


def test_regime_dependence_uses_the_pending_pattern_and_invents_no_label() -> None:
    evidence = _build()
    assert evidence.declared_regime_dependence == "positive_funding_premium_regime"
    assert (
        evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING == "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
    )
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE == "regime_evidence_unavailable"
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
        _build(_packet(rights_status="restricted"), policy=None, external_fact_needs=(_NEED,)),
        _build(expected_source_packet_digest="0" * 64, expected_kill_criteria_policy_digest="0" * 64),
    ):
        for codes in (evidence.integrity_reason_codes, evidence.verdict_reason_codes):
            assert list(codes) == sorted(set(codes))
            assert all(code.startswith(_PREFIX) for code in codes)


def test_ready_evidence_with_substrate_owned_inner_whitespace_still_reverifies() -> None:
    evidence = _build(_packet(packet_id="pkt\tfunding-carry-001"))
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert evidence.source_packet_id == "pkt\tfunding-carry-001"


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


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(intake_module.__file__).parent
    for builder, owner in (
        ("def build_edge_idea_intake_evidence(", "edge_idea_intake_evidence.py"),
        ("def build_edge_kill_criteria_policy(", "edge_idea_intake_evidence.py"),
    ):
        owners = sorted(
            path.name for path in validation_dir.glob("*.py") if builder in path.read_text(encoding="utf-8")
        )
        assert owners == [owner]
