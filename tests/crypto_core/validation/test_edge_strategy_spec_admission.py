"""Adversarial contract tests for Edge Factory EF-4 StrategySpec admission and the EF-2 -> EF-3 -> EF-4 spine."""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from pathlib import Path

import pytest

from crypto_core.data.requirements import (
    DataRequirementKey,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import SourcePacketRightsStatus, build_source_packet
from crypto_core.strategy.spec import StrategySpec, StrategySpecMarketType, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import edge_idea_intake_evidence as intake_module
from crypto_core.validation import edge_source_packet_evidence as packet_module
from crypto_core.validation import edge_strategy_spec_admission as admission_module
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    EdgeKillCriteriaPolicy,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    edge_idea_intake_evidence_digest,
    edge_idea_intake_evidence_to_dict,
    edge_kill_criteria_policy_to_dict,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    EdgeSeriesFinality,
    EdgeSeriesRevisionPolicy,
    EdgeSourcePacketEvidence,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_digest,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmission,
    EdgeStrategySpecAdmissionError,
    build_edge_strategy_spec_admission,
    edge_strategy_spec_admission_digest,
    edge_strategy_spec_admission_to_dict,
    verify_edge_strategy_spec_admission,
)

_PREFIX = "edge_strategy_spec_admission:"
_FLAGS = dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_BTC = "BTC-PERPETUAL"
_ETH = "ETH-PERPETUAL"
_SOL = "SOL-PERPETUAL"
_CORRELATION = "corr-funding-carry-001"
_NEED = "venue_funding_interval_mechanics"
_DEFAULT = object()


def _criterion(
    criterion_id: str = "max_drawdown_breach",
    *,
    metric_id: str = "max_drawdown_fraction",
    comparator: EdgeKillCriterionComparator = EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
    threshold: str | None = "0.250000000000000000",
    evaluation_basis: str = "rolling_30_utc_days",
) -> EdgeKillCriterion:
    return EdgeKillCriterion(
        criterion_id=criterion_id,
        metric_id=metric_id,
        comparator=comparator,
        threshold=threshold,
        evaluation_basis=evaluation_basis,
    )


_MAX_DRAWDOWN = _criterion()
_FUNDING_FLIP = _criterion(
    "funding_flip_persistence",
    metric_id="negative_funding_interval_count",
    comparator=EdgeKillCriterionComparator.KILL_IF_ABOVE,
    threshold="12.000000000000000000",
    evaluation_basis="rolling_7_utc_days",
)
_BASIS_BLOWOUT = _criterion(
    "basis_blowout",
    metric_id="basis_spread_fraction",
    comparator=EdgeKillCriterionComparator.KILL_IF_ABOVE,
    threshold="0.050000000000000000",
    evaluation_basis="per_funding_interval",
)
_DRAFT = (_MAX_DRAWDOWN, _FUNDING_FLIP)

_SPEC_PAYLOAD: dict[str, object] = {
    "schema_version": "strategy-spec.v1",
    "strategy_id": "alpha-funding-carry",
    "strategy_version": "1.0.0",
    "strategy_family": "carry",
    "edge_family": "funding_basis_carry",
    "instrument_universe": [_BTC, _ETH],
    "market_type": "usdt_perp",
    "venue_assumptions": ["perp_linear"],
    "timeframe": "1h",
    "bar_definition": "time_1h",
    "entry_conditions": ["funding_positive"],
    "exit_conditions": ["funding_neutral"],
    "invalidation_conditions": ["regime_break"],
    "risk_caps": {"max_leverage": 2.0},
    "data_requirements": {"funding_rate": "1h", "mark_price": "1m"},
    "feature_requirements": {"funding_zscore": "rolling"},
    "latency_sensitivity": "low",
    "funding_sensitivity": "high",
    "fee_model_requirement": "taker_fee_model_required",
    "slippage_model_requirement": "depth_aware_book_impact",
    "expected_regime": "positive_funding_premium",
    "failure_modes": ["funding_flip"],
    "kill_switch_triggers": ["funding_flip_persistence", "max_drawdown_breach"],
    "telemetry_fields": ["funding"],
    "promotion_requirements": ["walk_forward"],
}


def _policy(criteria: object = _DRAFT, **overrides: object) -> EdgeKillCriteriaPolicy:
    kwargs: dict[str, object] = {
        "policy_id": "policy-kill-criteria-002",
        "correlation_id": _CORRELATION,
        "kill_criteria": criteria,
        "thresholds_approved": True,
        "approval_reference": "governance-kill-criteria-approval-002",
        "approval_digest": "b" * 64,
    }
    kwargs.update(overrides)
    return build_edge_kill_criteria_policy(**kwargs)  # type: ignore[arg-type]


def _intake(
    *, rights_status: str = "own_research", policy: object = _DEFAULT, **overrides: object
) -> EdgeIdeaIntakeEvidence:
    packet = build_source_packet(
        packet_id="pkt-funding-carry-001",
        source_type="academic_paper",
        source_reference="doi:10.0000/funding-carry",
        source_title="Perpetual funding premia persistence",
        rights_status=rights_status,
        edge_hypothesis="Perpetual funding premia persist long enough to pay a delta-neutral carry holder",
        content_digest="c" * 64,
        market_scope_tags=("perp", "btc", "eth"),
    )
    policy = _policy(policy_id="policy-kill-criteria-001") if policy is _DEFAULT else policy
    kwargs: dict[str, object] = {
        "expected_source_packet_digest": packet.packet_digest,
        "intake_id": "intake-funding-carry-001",
        "correlation_id": _CORRELATION,
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Leveraged long demand pays a persistent funding premium to delta-neutral carry",
        "data_requirement_keys": (DataRequirementKey.FUNDING_RATE, DataRequirementKey.MARK_PRICE),
        "declared_regime_dependence": "positive_funding_premium_regime",
        "kill_criteria_draft": _DRAFT,
    }
    if policy is not None:
        kwargs["kill_criteria_policy"] = policy
        kwargs["expected_kill_criteria_policy_digest"] = policy.policy_digest  # type: ignore[union-attr]
    kwargs.update(overrides)
    return build_edge_idea_intake_evidence(packet, **kwargs)  # type: ignore[arg-type]


def _series(
    series_id: str = "funding-rate-archive",
    key: DataRequirementKey = DataRequirementKey.FUNDING_RATE,
    *,
    finality: EdgeSeriesFinality = EdgeSeriesFinality.FINALIZED_ONLY,
    instrument_coverage: tuple[str, ...] = (_BTC, _ETH),
) -> EdgeInputSeries:
    return EdgeInputSeries(
        series_id=series_id,
        data_requirement_key=key,
        source_reference=f"dataset:{series_id}-v1",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="self-collected-public-archive",
        finality=finality,
        revision_policy=EdgeSeriesRevisionPolicy.IMMUTABLE_AFTER_FINALIZATION,
        instrument_coverage=instrument_coverage,
    )


def _mark_series(instrument_coverage: tuple[str, ...] = (_ETH, _BTC, _SOL)) -> EdgeInputSeries:
    return _series("mark-price-archive", DataRequirementKey.MARK_PRICE, instrument_coverage=instrument_coverage)


def _packet_evidence(intake: EdgeIdeaIntakeEvidence | None = None, **overrides: object) -> EdgeSourcePacketEvidence:
    intake = _intake() if intake is None else intake
    registry = default_perp_data_requirement_registry()
    kwargs: dict[str, object] = {
        "expected_root_intake_digest": intake.intake_digest,
        "data_requirement_registry": registry,
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry),
        "series": (_series(), _mark_series()),
        "packet_evidence_id": "packet-funding-carry-001",
        "correlation_id": _CORRELATION,
    }
    kwargs.update(overrides)
    return build_edge_source_packet_evidence(intake, **kwargs)  # type: ignore[arg-type]


def _spec(**overrides: object) -> StrategySpec:
    payload = json.loads(json.dumps(_SPEC_PAYLOAD))
    payload.update(overrides)
    result = validate_strategy_spec(payload)
    assert result.accepted, result.rejection_reasons + result.needs_research_reasons
    assert result.spec is not None
    return result.spec


def _build(
    packet=None, spec=None, *, intake=None, policy: object = _DEFAULT, **overrides: object
) -> EdgeStrategySpecAdmission:
    intake = _intake() if intake is None else intake
    packet = _packet_evidence(intake) if packet is None else packet
    spec = _spec() if spec is None else spec
    kwargs: dict[str, object] = {
        "expected_root_intake_digest": intake.intake_digest,
        "expected_source_packet_evidence_digest": packet.packet_evidence_digest,
        "kill_criteria": _DRAFT,
        "admission_id": "admission-funding-carry-001",
        "correlation_id": _CORRELATION,
    }
    kwargs.update(overrides)
    policy = _policy(kwargs["kill_criteria"]) if policy is _DEFAULT else policy
    if policy is not None:
        kwargs.setdefault("kill_criteria_policy", policy)
        kwargs.setdefault("expected_kill_criteria_policy_digest", policy.policy_digest)  # type: ignore[union-attr]
    if "expected_strategy_spec_digest" not in kwargs:
        kwargs["expected_strategy_spec_digest"] = strategy_spec_digest(spec)
    return build_edge_strategy_spec_admission(packet, spec, **kwargs)  # type: ignore[arg-type]


def _reseal(admission: EdgeStrategySpecAdmission, **changes: object) -> EdgeStrategySpecAdmission:
    forged = replace(admission, **changes)
    return replace(forged, admission_digest=edge_strategy_spec_admission_digest(forged))


def _reseal_packet(packet: EdgeSourcePacketEvidence, **changes: object) -> EdgeSourcePacketEvidence:
    forged = replace(packet, **changes)
    return replace(forged, packet_evidence_digest=edge_source_packet_evidence_digest(forged))


def _codes(admission: object) -> tuple[str, ...]:
    return verify_edge_strategy_spec_admission(admission).reason_codes


def _assert_ready(admission: EdgeStrategySpecAdmission, verdict: EdgeGateVerdict, codes: tuple[str, ...]) -> None:
    assert admission.status is EdgeEvidenceStatus.READY
    assert admission.gate_verdict is verdict
    assert admission.advances is (verdict is EdgeGateVerdict.PASS)
    assert admission.integrity_reason_codes == ()
    assert admission.verdict_reason_codes == tuple(_PREFIX + code for code in codes)
    assert verify_edge_strategy_spec_admission(admission).intact is True


def _assert_rejected(admission: EdgeStrategySpecAdmission, *codes: str) -> None:
    assert admission.status is EdgeEvidenceStatus.REJECTED
    assert admission.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert admission.advances is False
    assert admission.verdict_reason_codes == ()
    assert (admission.verified_root_intake_digest, admission.verified_strategy_spec_digest) == ("", "")
    for code in codes:
        assert _PREFIX + code in admission.integrity_reason_codes, admission.integrity_reason_codes
    assert verify_edge_strategy_spec_admission(admission).intact is True


# --- 1. Valid StrategySpec binding ---------------------------------------------------------------------------


def test_valid_strategy_spec_binding_is_ready_pass_and_carries_linear_authority_snapshots() -> None:
    intake = _intake()
    packet = _packet_evidence(intake)
    spec = _spec()
    policy = _policy()
    admission = _build(packet, spec, intake=intake, policy=policy)
    _assert_ready(admission, EdgeGateVerdict.PASS, ())
    assert json.loads(admission.predecessor_source_packet_snapshot_json) == edge_source_packet_evidence_to_dict(packet)
    assert json.loads(admission.strategy_spec_snapshot_json) == json.loads(json.dumps(_SPEC_PAYLOAD))
    assert json.loads(admission.kill_criteria_policy_snapshot_json) == edge_kill_criteria_policy_to_dict(policy)
    assert not any("root_intake_snapshot" in field.name for field in fields(EdgeStrategySpecAdmission))
    assert admission.verified_root_intake_digest == intake.intake_digest
    assert admission.verified_source_packet_evidence_digest == packet.packet_evidence_digest
    assert admission.verified_strategy_spec_digest == strategy_spec_digest(spec)
    assert admission.verified_kill_criteria_policy_digest == policy.policy_digest
    assert admission.strategy_id == admission.intake_candidate_strategy_id == "alpha-funding-carry"
    assert admission.edge_family == admission.intake_edge_family == "funding_basis_carry"
    assert admission.instrument_universe == (_BTC, _ETH)
    assert admission.packet_instrument_coverage == (_BTC, _ETH)
    assert admission.packet_series_keys == admission.spec_data_requirement_keys == ("funding_rate", "mark_price")
    assert admission.market_type == "usdt_perp"
    assert admission.draft_kill_criteria == admission.kill_criteria == intake.kill_criteria_draft
    assert admission.draft_kill_criteria_digest == admission.kill_criteria_digest == intake.kill_criteria_digest
    assert admission.kill_criteria_added_ids == ()
    assert admission.kill_criteria_lifecycle_stage == "SPEC_BOUND_STRENGTHEN_ONLY"
    assert admission.kill_criteria_sealed is False


def test_fee_funding_slippage_latency_requirements_are_recorded_verbatim_not_replaced() -> None:
    admission = _build()
    assert (
        admission.fee_model_requirement,
        admission.funding_sensitivity,
        admission.slippage_model_requirement,
        admission.latency_sensitivity,
    ) == ("taker_fee_model_required", "high", "depth_aware_book_impact", "low")
    assert admission.cost_model_binding == "strategy_spec_requirements_recorded_verbatim_no_venue_fact_values.v1"
    assert admission.current_venue_facts_consumed is False


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _build().advances = False  # type: ignore[misc]


# --- 2. StrategySpec authority -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("spec_factory", "code"),
    [
        (lambda: replace(_spec(), risk_caps={"max_leverage": 10.0}), "strategy_spec_invalid"),
        (lambda: replace(_spec(), market_type=StrategySpecMarketType.SPOT), "strategy_spec_invalid"),
        (lambda: replace(_spec(), funding_sensitivity="unknown"), "strategy_spec_invalid"),
        (lambda: replace(_spec(), instrument_universe=()), "strategy_spec_invalid"),
        (lambda: replace(_spec(), risk_caps={"max_leverage": float("nan")}), "strategy_spec_malformed_payload"),
    ],
)
def test_strategy_spec_failing_public_validation_is_rejected(spec_factory, code: str) -> None:
    _assert_rejected(_build(spec=spec_factory()), code)


def test_non_serializable_spec_is_rejected_without_raw_error() -> None:
    admission = _build(spec=replace(_spec(), market_type="usdt_perp"), expected_strategy_spec_digest="e" * 64)
    _assert_rejected(admission, "strategy_spec_malformed_payload")
    assert admission.strategy_spec_snapshot_json == ""


def test_strategy_spec_anchor_mismatch_and_post_pin_tamper_are_rejected() -> None:
    _assert_rejected(_build(expected_strategy_spec_digest="0" * 64), "strategy_spec_digest_mismatch")
    spec = _spec()
    forged = replace(spec, instrument_universe=(_BTC, _ETH, _SOL))
    _assert_rejected(
        _build(spec=forged, expected_strategy_spec_digest=strategy_spec_digest(spec)), "strategy_spec_digest_mismatch"
    )


def test_resealed_noncanonical_spec_is_rejected() -> None:
    _assert_rejected(_build(spec=replace(_spec(), strategy_family=" carry ")), "strategy_spec_noncanonical")


@pytest.mark.parametrize(
    "changes",
    [
        {"entry_conditions": ("enter on live funding print",)},
        {"failure_modes": ("carry_scheduler_stall",)},
        {"exit_conditions": ("exit via place_order hook",)},
        {"invalidation_conditions": ("borsa_signal_break",)},
    ],
)
def test_spec_with_forbidden_or_bist_values_is_rejected(changes: dict[str, object]) -> None:
    _assert_rejected(_build(spec=replace(_spec(), **changes)), "strategy_spec_scope_violation")


# --- 3. Semantic admission -----------------------------------------------------------------------------------


def test_instrument_universe_outside_packet_coverage_fails() -> None:
    # SOL is covered by the mark-price series but not by the funding series, so it is outside the intersection.
    _assert_ready(
        _build(spec=_spec(instrument_universe=[_BTC, _SOL])),
        EdgeGateVerdict.FAIL,
        ("instrument_outside_packet_coverage:SOL-PERPETUAL",),
    )


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"edge_family": "momentum_trend"}, "edge_family_mismatch"),
        ({"strategy_id": "beta-funding-carry"}, "candidate_strategy_id_mismatch"),
    ],
)
def test_edge_family_or_candidate_identity_mismatch_fails(overrides: dict[str, object], code: str) -> None:
    _assert_ready(_build(spec=_spec(**overrides)), EdgeGateVerdict.FAIL, (code,))


def test_spec_data_requirement_outside_the_packet_fails_and_keys_normalize_like_pit_parity() -> None:
    _assert_ready(
        _build(spec=_spec(data_requirements={"funding_rate": "1h", "order_book": "l2"})),
        EdgeGateVerdict.FAIL,
        ("spec_data_requirement_not_in_packet:order_book",),
    )
    normalized = _build(spec=_spec(data_requirements={" Funding_Rate ": "1h", "MARK_PRICE": "1m"}))
    _assert_ready(normalized, EdgeGateVerdict.PASS, ())
    assert normalized.spec_data_requirement_keys == ("funding_rate", "mark_price")


def test_spec_kill_switch_triggers_must_be_exactly_the_admitted_criteria() -> None:
    code = ("spec_kill_switch_triggers_not_bound_to_kill_criteria",)
    _assert_ready(_build(spec=_spec(kill_switch_triggers=["max_drawdown_breach"])), EdgeGateVerdict.FAIL, code)
    extra = _spec(kill_switch_triggers=["max_drawdown_breach", "funding_flip_persistence", "manual_halt"])
    _assert_ready(_build(spec=extra), EdgeGateVerdict.FAIL, code)


# --- 4. Kill-criteria lifecycle: strengthen only -------------------------------------------------------------


def test_kill_criteria_exact_preservation_passes_in_any_order() -> None:
    reordered = _build(kill_criteria=[_FUNDING_FLIP, _MAX_DRAWDOWN])
    _assert_ready(reordered, EdgeGateVerdict.PASS, ())
    assert reordered.admission_digest == _build().admission_digest


def test_strengthening_by_adding_a_criterion_is_accepted() -> None:
    spec = _spec(kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"])
    admission = _build(spec=spec, kill_criteria=(*_DRAFT, _BASIS_BLOWOUT))
    _assert_ready(admission, EdgeGateVerdict.PASS, ())
    assert admission.kill_criteria_added_ids == ("basis_blowout",)
    assert admission.draft_kill_criteria_digest == _intake().kill_criteria_digest != admission.kill_criteria_digest


def test_one_item_weakening_by_removal_is_refused() -> None:
    admission = _build(spec=_spec(kill_switch_triggers=["max_drawdown_breach"]), kill_criteria=(_MAX_DRAWDOWN,))
    _assert_ready(admission, EdgeGateVerdict.FAIL, ("kill_criterion_removed:funding_flip_persistence",))


def test_removal_hidden_behind_a_strengthening_addition_is_still_refused() -> None:
    spec = _spec(kill_switch_triggers=["basis_blowout", "max_drawdown_breach"])
    admission = _build(spec=spec, kill_criteria=(_MAX_DRAWDOWN, _BASIS_BLOWOUT))
    _assert_ready(admission, EdgeGateVerdict.FAIL, ("kill_criterion_removed:funding_flip_persistence",))


@pytest.mark.parametrize(
    "changes",
    [
        {"threshold": "0.300000000000000000"},  # relaxed: the drawdown kill fires later
        {"threshold": "0.200000000000000000"},  # tightened: still a changed governance number, not an addition
        {"comparator": EdgeKillCriterionComparator.KILL_IF_ABOVE},  # relaxed boundary
        {"evaluation_basis": "rolling_90_utc_days"},
        {"metric_id": "peak_to_trough_fraction"},
    ],
)
def test_changed_or_relaxed_draft_criterion_is_refused_even_with_a_matching_policy(changes: dict[str, object]) -> None:
    admission = _build(kill_criteria=(replace(_MAX_DRAWDOWN, **changes), _FUNDING_FLIP))
    _assert_ready(admission, EdgeGateVerdict.FAIL, ("kill_criterion_modified:max_drawdown_breach",))


def test_threshold_erased_back_to_pending_is_refused_as_a_modification() -> None:
    admission = _build(kill_criteria=(replace(_MAX_DRAWDOWN, threshold=None), _FUNDING_FLIP))
    assert admission.gate_verdict is EdgeGateVerdict.FAIL
    assert _PREFIX + "kill_criterion_modified:max_drawdown_breach" in admission.verdict_reason_codes
    assert _PREFIX + "kill_criterion_threshold_pending_governance:max_drawdown_breach" in admission.verdict_reason_codes


# --- 5. B5: governance approval at admission ----------------------------------------------------------------


def test_missing_admission_policy_needs_governance_and_raw_approval_parameters_are_gone() -> None:
    _assert_ready(_build(policy=None), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, ("kill_criteria_policy_missing",))
    parameters = set(inspect.signature(build_edge_strategy_spec_admission).parameters)
    assert parameters.isdisjoint(
        {"kill_criteria_thresholds_approved", "kill_criteria_approval_reference", "kill_criteria_approval_digest"}
    )


@pytest.mark.parametrize(
    ("policy_factory", "code"),
    [
        (lambda: _policy(thresholds_approved=False), "kill_criteria_policy_not_ready"),
        (lambda: _policy(correlation_id="corr-other-001"), "kill_criteria_policy_correlation_mismatch"),
        (lambda: _policy((_MAX_DRAWDOWN,)), "kill_criteria_policy_kill_criteria_mismatch"),
    ],
)
def test_authentic_but_inapplicable_policy_needs_governance(policy_factory, code: str) -> None:
    _assert_ready(_build(policy=policy_factory()), EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, (code,))


def test_draft_policy_does_not_approve_a_strengthened_set() -> None:
    spec = _spec(kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"])
    admission = _build(spec=spec, kill_criteria=(*_DRAFT, _BASIS_BLOWOUT), policy=_policy(_DRAFT))
    _assert_ready(
        admission, EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, ("kill_criteria_policy_kill_criteria_mismatch",)
    )


def test_added_criterion_with_pending_threshold_needs_governance() -> None:
    spec = _spec(kill_switch_triggers=["basis_blowout", "funding_flip_persistence", "max_drawdown_breach"])
    admission = _build(spec=spec, kill_criteria=(*_DRAFT, replace(_BASIS_BLOWOUT, threshold=None)))
    _assert_ready(
        admission,
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        ("kill_criteria_policy_not_ready", "kill_criterion_threshold_pending_governance:basis_blowout"),
    )


def test_policy_anchor_mismatch_or_tampered_policy_is_rejected() -> None:
    _assert_rejected(_build(expected_kill_criteria_policy_digest="0" * 64), "kill_criteria_policy_digest_mismatch")
    tampered = replace(_policy(), approval_digest="f" * 64)
    _assert_rejected(
        _build(policy=tampered),
        "kill_criteria_policy_integrity_failure:edge_kill_criteria_policy:self_digest_mismatch",
    )


# --- 6. B4: dual anchor, predecessor and nested root authority -----------------------------------------------


def test_root_anchor_that_differs_from_the_authenticated_nested_root_is_a_splice() -> None:
    admission = _build(expected_root_intake_digest="0" * 64)
    _assert_rejected(admission, "chain_splice_root_intake_mismatch")
    assert admission.integrity_reason_codes == (_PREFIX + "chain_splice_root_intake_mismatch",)


def test_packet_from_another_valid_root_is_a_rejected_chain_splice() -> None:
    root_b = _intake(intake_id="intake-funding-carry-002")
    assert root_b.gate_verdict is EdgeGateVerdict.PASS
    _assert_rejected(_build(_packet_evidence(_intake()), intake=root_b), "chain_splice_root_intake_mismatch")


def test_predecessor_anchor_mismatch_and_unresealed_tamper_are_rejected() -> None:
    _assert_rejected(
        _build(expected_source_packet_evidence_digest="0" * 64), "predecessor_source_packet_digest_mismatch"
    )
    packet = replace(_packet_evidence(), packet_instrument_coverage=(_BTC, _ETH, _SOL))
    _assert_rejected(
        _build(packet), "predecessor_source_packet_integrity_failure:edge_source_packet_evidence:self_digest_mismatch"
    )


def test_resealed_predecessor_with_foreign_root_owned_requirements_is_rejected() -> None:
    packet = _packet_evidence()
    forged = _reseal_packet(
        packet,
        declared_data_requirement_keys=("funding_rate",),
        series=(packet.series[0],),
        packet_instrument_coverage=packet.series[0].instrument_coverage,
    )
    _assert_rejected(
        _build(forged),
        "predecessor_source_packet_integrity_failure:edge_source_packet_evidence:field_mismatch:declared_data_requirement_keys",
    )


def test_resealed_predecessor_carrying_a_forged_passing_root_is_rejected() -> None:
    needs = _intake(external_fact_needs=(_NEED,))
    forged_root = replace(needs, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    forged_root = replace(forged_root, intake_digest=edge_idea_intake_evidence_digest(forged_root))
    genuine_packet = _packet_evidence()
    forged_packet = _reseal_packet(
        genuine_packet,
        root_intake_snapshot_json=verify_edge_idea_intake_evidence(forged_root).canonical_json,
        expected_root_intake_digest=forged_root.intake_digest,
        verified_root_intake_digest=forged_root.intake_digest,
    )
    admission = _build(forged_packet, intake=forged_root)
    assert admission.status is EdgeEvidenceStatus.REJECTED
    assert any(
        code.startswith(_PREFIX + "predecessor_source_packet_integrity_failure:")
        for code in admission.integrity_reason_codes
    )


def test_nested_root_is_proven_against_the_explicit_anchor_even_when_the_packet_claims_that_anchor() -> None:
    # The packet carries root A but claims anchor B; its own receipt is REJECTED. EF-4 anchored to B must still report
    # that the authenticated nested root is not B, not merely that the predecessor did not pass.
    root_a = _intake()
    root_b = _intake(intake_id="intake-funding-carry-002")
    packet = _packet_evidence(root_a, expected_root_intake_digest=root_b.intake_digest)
    assert packet.status is EdgeEvidenceStatus.REJECTED
    assert packet.expected_root_intake_digest == root_b.intake_digest
    _assert_rejected(
        _build(packet, intake=root_b),
        "predecessor_source_packet_not_passed:NOT_EVALUATED",
        "chain_splice_root_intake_mismatch",
    )


def test_correlation_mismatch_is_rejected_for_both_anchors() -> None:
    _assert_rejected(
        _build(correlation_id="corr-funding-carry-999", policy=_policy(correlation_id="corr-funding-carry-999")),
        "root_intake_correlation_id_mismatch",
        "predecessor_source_packet_correlation_id_mismatch",
    )


@pytest.mark.parametrize(
    ("series", "verdict"),
    [
        ((_series(finality=EdgeSeriesFinality.UNKNOWN), _mark_series()), "NEEDS_EXTERNAL_FACTS"),
        ((_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series()), "FAIL"),
    ],
)
def test_non_passing_predecessor_packet_cannot_advance(series, verdict: str) -> None:
    intake = _intake()
    admission = _build(_packet_evidence(intake, series=series), intake=intake)
    _assert_rejected(admission, f"predecessor_source_packet_not_passed:{verdict}")
    assert admission.integrity_reason_codes == (_PREFIX + f"predecessor_source_packet_not_passed:{verdict}",)


def test_needs_root_cannot_advance_even_through_its_own_rejected_packet() -> None:
    intake = _intake(policy=None)
    _assert_rejected(
        _build(_packet_evidence(intake), intake=intake),
        "root_intake_not_passed:NEEDS_GOVERNANCE_APPROVAL",
        "predecessor_source_packet_not_passed:NOT_EVALUATED",
    )


def test_resealed_forged_pass_packet_cannot_manufacture_admission() -> None:
    intake = _intake()
    failing = _packet_evidence(
        intake, series=(_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series())
    )
    forged = _reseal_packet(failing, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    _assert_rejected(
        _build(forged, intake=intake),
        "predecessor_source_packet_integrity_failure:edge_source_packet_evidence:field_mismatch:gate_verdict",
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"intake_candidate_strategy_id": "beta-funding-carry"},
        {"intake_edge_family": "momentum_trend"},
        {"packet_instrument_coverage": (_BTC, _ETH, _SOL)},
        {"packet_series_keys": ("funding_rate",)},
        {"strategy_id": "beta-funding-carry"},
        {"instrument_universe": (_BTC,)},
        {"spec_data_requirement_keys": ("funding_rate",)},
        {"spec_kill_switch_triggers": ("max_drawdown_breach",)},
        {"fee_model_requirement": "maker_rebate_assumed"},
        {"funding_sensitivity": "none"},
        {"expected_regime_declared": "any_regime"},
        {"market_type": "spot"},
        {"draft_kill_criteria": (_MAX_DRAWDOWN,)},
        {"draft_kill_criteria_digest": "d" * 64},
        {"kill_criteria_added_ids": ("phantom",)},
        {"verified_kill_criteria_policy_digest": ""},
    ],
)
def test_resealed_predecessor_or_spec_derived_summaries_fail_verification(changes: dict[str, object]) -> None:
    (name,) = changes
    codes = _codes(_reseal(_build(), **changes))
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert _PREFIX + f"field_mismatch:{name}" in codes


def test_resealed_coverage_widening_of_a_failing_admission_fails_verification() -> None:
    failing = _build(spec=_spec(instrument_universe=[_BTC, _SOL]))
    forged = _reseal(
        failing,
        packet_instrument_coverage=(_BTC, _ETH, _SOL),
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    codes = _codes(forged)
    assert _PREFIX + "field_mismatch:packet_instrument_coverage" in codes
    assert _PREFIX + "field_mismatch:gate_verdict" in codes


def test_swapped_spec_snapshot_cannot_keep_a_passing_admission() -> None:
    other = json.dumps(
        json.loads(json.dumps({**_SPEC_PAYLOAD, "edge_family": "momentum_trend"})),
        sort_keys=True,
        separators=(",", ":"),
    )
    forged = _reseal(_build(), strategy_spec_snapshot_json=other)
    assert _PREFIX + "field_mismatch:status" in _codes(forged)


# --- 7. Regime pending pattern -------------------------------------------------------------------------------


def test_expected_regime_uses_the_pending_pattern_and_binds_no_rf_label() -> None:
    admission = _build()
    assert admission.expected_regime_declared == "positive_funding_premium"
    assert admission.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert admission.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert admission.regime_evidence_available is False
    other = _build(spec=_spec(expected_regime="high_volatility_trend"))
    assert other.gate_verdict is EdgeGateVerdict.PASS
    assert other.admission_digest != admission.admission_digest
    assert not any("regime" in name for name in inspect.signature(build_edge_strategy_spec_admission).parameters)
    for changes in (
        {"regime_label_binding_status": "RF_LABEL_BOUND"},
        {"regime_evidence_status": "regime_evidence_available"},
        {"regime_evidence_available": True},
    ):
        (name,) = changes
        assert _PREFIX + f"field_mismatch:{name}" in _codes(_reseal(admission, **changes))


# --- 8. Malformed input --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"expected_root_intake_digest": "0" * 63}, "expected_root_intake_digest_invalid"),
        ({"expected_source_packet_evidence_digest": None}, "expected_source_packet_evidence_digest_invalid"),
        ({"expected_strategy_spec_digest": "G" * 64}, "expected_strategy_spec_digest_invalid"),
        ({"admission_id": ""}, "admission_id_invalid"),
        ({"correlation_id": "corr-live-001"}, "forbidden_scope_token:correlation_id"),
        ({"admission_id": "admission-borsa-001"}, "bist_scope_leakage:admission_id"),
        ({"kill_criteria": ()}, "kill_criteria_invalid"),
        ({"kill_criteria": (_MAX_DRAWDOWN, _MAX_DRAWDOWN)}, "kill_criteria_invalid"),
        ({"kill_criteria": (replace(_MAX_DRAWDOWN, threshold="0.3"),)}, "kill_criteria_invalid"),
        ({"expected_kill_criteria_policy_digest": "b" * 10}, "expected_kill_criteria_policy_digest_invalid"),
        ({"kill_criteria_policy": {"policy_id": "policy-1"}}, "kill_criteria_policy_malformed"),
    ],
)
def test_malformed_input_raises(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeStrategySpecAdmissionError, match=re.escape(_PREFIX + code)):
        _build(policy=None, **overrides) if "kill_criteria" in overrides else _build(**overrides)


def test_wrong_artifact_types_and_policy_misuse_raise() -> None:
    intake = _intake()
    packet = _packet_evidence(intake)
    spec = _spec()
    kwargs: dict[str, object] = {
        "expected_root_intake_digest": intake.intake_digest,
        "expected_source_packet_evidence_digest": packet.packet_evidence_digest,
        "expected_strategy_spec_digest": strategy_spec_digest(spec),
        "kill_criteria": _DRAFT,
        "admission_id": "admission-funding-carry-001",
        "correlation_id": _CORRELATION,
    }
    with pytest.raises(EdgeStrategySpecAdmissionError, match="source_packet_evidence_malformed"):
        build_edge_strategy_spec_admission(intake, spec, **kwargs)  # type: ignore[arg-type]
    with pytest.raises(EdgeStrategySpecAdmissionError, match="strategy_spec_malformed"):
        build_edge_strategy_spec_admission(packet, dict(_SPEC_PAYLOAD), **kwargs)  # type: ignore[arg-type]
    with pytest.raises(EdgeStrategySpecAdmissionError, match="expected_kill_criteria_policy_digest_unexpected"):
        build_edge_strategy_spec_admission(packet, spec, expected_kill_criteria_policy_digest="b" * 64, **kwargs)  # type: ignore[arg-type]
    assert "intake" not in inspect.signature(build_edge_strategy_spec_admission).parameters


# --- 9. B7: truthful READY and REJECTED receipts -------------------------------------------------------------


def test_field_tamper_without_reseal_fails_verification() -> None:
    assert _PREFIX + "self_digest_mismatch" in _codes(replace(_build(), strategy_id="beta-funding-carry"))


def test_resealed_weakening_upgraded_to_pass_fails_reassembly() -> None:
    weakened = _build(spec=_spec(kill_switch_triggers=["max_drawdown_breach"]), kill_criteria=(_MAX_DRAWDOWN,))
    forged = _reseal(weakened, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "field_mismatch:gate_verdict" in _codes(forged)


@pytest.mark.parametrize(
    "changes",
    [
        {"integrity_reason_codes": (_PREFIX + "strategy_spec_digest_mismatch", _PREFIX + "invented_reason")},
        {"integrity_reason_codes": (_PREFIX + "chain_splice_root_intake_mismatch",)},
    ],
)
def test_rejected_receipt_with_inconsistent_reason_codes_does_not_verify(changes: dict) -> None:
    rejected = _build(expected_strategy_spec_digest="0" * 64)
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in _codes(_reseal(rejected, **changes))


def test_passing_admission_forged_into_a_rejected_receipt_does_not_verify() -> None:
    forged = _reseal(
        _build(),
        status=EdgeEvidenceStatus.REJECTED,
        gate_verdict=EdgeGateVerdict.NOT_EVALUATED,
        advances=False,
        verified_root_intake_digest="",
        verified_source_packet_evidence_digest="",
        verified_strategy_spec_digest="",
        verified_kill_criteria_policy_digest="",
        integrity_reason_codes=(_PREFIX + "strategy_spec_digest_mismatch",),
    )
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in _codes(forged)


def test_malformed_rejected_semantics_do_not_verify() -> None:
    rejected = _build(expected_strategy_spec_digest="0" * 64)
    assert _PREFIX + "evidence_semantics_malformed" in _codes(_reseal(rejected, expected_strategy_spec_digest="short"))
    assert _PREFIX + "evidence_semantics_malformed" in _codes(_reseal(rejected, kill_criteria=("max_drawdown_breach",)))


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_resealed_structural_claim_fails_verification(flag: str) -> None:
    assert _PREFIX + f"field_mismatch:{flag}" in _codes(_reseal(_build(), **{flag: not _FLAGS[flag]}))


@pytest.mark.parametrize(
    "changes",
    [
        {"kill_criteria_lifecycle_stage": "SEALED"},
        {"cost_model_binding": "venue_fee_schedule_applied"},
        {"spec_data_requirement_key_normalization": "none"},
        {"root_gate_id": "EF-3"},
    ],
)
def test_resealed_constant_tamper_fails(changes: dict[str, object]) -> None:
    (name,) = changes
    assert _PREFIX + f"field_mismatch:{name}" in _codes(_reseal(_build(), **changes))


def test_forged_or_non_serializable_admission_never_raises() -> None:
    assert _codes(replace(_build(), kill_criteria=(object(),))) == (_PREFIX + "evidence_serialization_failed",)  # type: ignore[arg-type]
    assert _codes(replace(_build(), status="READY")) == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]


# --- 10. Cross-contract spine properties ---------------------------------------------------------------------


def _chain() -> tuple[EdgeIdeaIntakeEvidence, EdgeSourcePacketEvidence, EdgeStrategySpecAdmission]:
    intake = _intake()
    packet = _packet_evidence(intake)
    return intake, packet, _build(packet, _spec(), intake=intake)


_VERIFIERS = (
    verify_edge_idea_intake_evidence,
    verify_edge_source_packet_evidence,
    verify_edge_strategy_spec_admission,
)


def test_identical_semantic_input_yields_identical_canonical_bytes_across_the_spine() -> None:
    for verify, first, second in zip(_VERIFIERS, _chain(), _chain()):
        assert verify(first).intact is True
        assert verify(first).canonical_json == verify(second).canonical_json


def test_order_irrelevant_permutations_cannot_change_any_spine_identity() -> None:
    base_intake, base_packet, base_admission = _chain()
    intake = _intake(
        kill_criteria_draft=[_FUNDING_FLIP, _MAX_DRAWDOWN],
        data_requirement_keys=(DataRequirementKey.MARK_PRICE, DataRequirementKey.FUNDING_RATE),
        policy=_policy([_FUNDING_FLIP, _MAX_DRAWDOWN], policy_id="policy-kill-criteria-001"),
    )
    packet = _packet_evidence(
        intake, series=[_mark_series(instrument_coverage=(_SOL, _ETH, _BTC)), _series(instrument_coverage=(_ETH, _BTC))]
    )
    admission = _build(packet, _spec(), intake=intake, kill_criteria=[_FUNDING_FLIP, _MAX_DRAWDOWN])
    assert intake.intake_digest == base_intake.intake_digest
    assert packet.packet_evidence_digest == base_packet.packet_evidence_digest
    assert admission.admission_digest == base_admission.admission_digest


def test_order_sensitive_spec_fields_stay_order_sensitive_under_spec_authority() -> None:
    forward = _build(spec=_spec(instrument_universe=[_BTC, _ETH]))
    backward = _build(spec=_spec(instrument_universe=[_ETH, _BTC]))
    assert forward.gate_verdict is backward.gate_verdict is EdgeGateVerdict.PASS
    assert forward.verified_strategy_spec_digest != backward.verified_strategy_spec_digest
    assert forward.admission_digest != backward.admission_digest
    assert backward.instrument_universe == (_ETH, _BTC)
    assert strategy_spec_digest(
        _spec(data_requirements={"mark_price": "1m", "funding_rate": "1h"})
    ) == strategy_spec_digest(_spec())


def test_status_and_gate_verdict_are_never_conflated_across_outcomes() -> None:
    artifacts = (
        *_chain(),
        _build(expected_root_intake_digest="0" * 64),
        _build(spec=_spec(edge_family="momentum_trend")),
        _build(policy=None),
        _intake(external_fact_needs=(_NEED,)),
        _intake(expected_source_packet_digest="0" * 64),
        _packet_evidence(series=(_series(finality=EdgeSeriesFinality.UNKNOWN), _mark_series())),
        _packet_evidence(expected_root_intake_digest="0" * 64),
    )
    status_values = {item.value for item in EdgeEvidenceStatus}
    for artifact in artifacts:
        assert (artifact.status is EdgeEvidenceStatus.REJECTED) is (
            artifact.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        )
        assert artifact.advances is (
            artifact.status is EdgeEvidenceStatus.READY and artifact.gate_verdict is EdgeGateVerdict.PASS
        )
        assert artifact.gate_verdict.value not in status_values


def test_no_later_gate_manufactures_ready_admission_from_malformed_predecessors() -> None:
    intake, packet, _ = _chain()
    rejected_root = _intake(expected_source_packet_digest="0" * 64)
    scenarios = (
        _build(replace(packet, packet_instrument_coverage=()), intake=intake),
        _build(packet, intake=intake, expected_source_packet_evidence_digest=intake.intake_digest),
        _build(packet, intake=intake, expected_root_intake_digest=packet.packet_evidence_digest),
        _build(_packet_evidence(rejected_root), intake=rejected_root),
        _build(replace(packet, series=(object(),)), intake=intake),  # type: ignore[arg-type]
    )
    for admission in scenarios:
        assert admission.status is EdgeEvidenceStatus.REJECTED
        assert admission.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert admission.advances is False
        assert verify_edge_strategy_spec_admission(admission).intact is True


def test_verifiers_reject_each_others_artifacts() -> None:
    intake, packet, admission = _chain()
    assert verify_edge_idea_intake_evidence(packet).intact is False
    assert verify_edge_source_packet_evidence(admission).intact is False
    assert verify_edge_strategy_spec_admission(intake).intact is False


def test_every_spine_artifact_shares_the_same_structural_non_claims() -> None:
    for cls in (EdgeIdeaIntakeEvidence, EdgeSourcePacketEvidence, EdgeStrategySpecAdmission, EdgeKillCriteriaPolicy):
        assert {field.name: field.default for field in fields(cls) if field.name in _FLAGS} == _FLAGS
    assert set(inspect.signature(build_edge_strategy_spec_admission).parameters).isdisjoint(_FLAGS)


def test_public_digests_follow_the_digest_boundary_rule_for_every_spine_artifact() -> None:
    intake, packet, admission = _chain()
    for artifact, to_dict, self_field in (
        (intake, edge_idea_intake_evidence_to_dict, "intake_digest"),
        (packet, edge_source_packet_evidence_to_dict, "packet_evidence_digest"),
        (admission, edge_strategy_spec_admission_to_dict, "admission_digest"),
    ):
        payload = to_dict(artifact)
        carried = payload.pop(self_field)
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
        assert carried == hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    for admission in (
        _build(spec=_spec(edge_family="momentum_trend", instrument_universe=[_BTC, _SOL]), policy=None),
        _build(expected_root_intake_digest="0" * 64, expected_strategy_spec_digest="0" * 64),
    ):
        for codes in (admission.integrity_reason_codes, admission.verdict_reason_codes):
            assert list(codes) == sorted(set(codes))
            assert all(code.startswith(_PREFIX) for code in codes)


def test_ready_admission_with_spec_owned_inner_whitespace_still_reverifies() -> None:
    admission = _build(spec=_spec(expected_regime="positive\tfunding_premium", strategy_family="funding carry"))
    _assert_ready(admission, EdgeGateVerdict.PASS, ())
    assert admission.expected_regime_declared == "positive\tfunding_premium"


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


@pytest.mark.parametrize("module", [intake_module, packet_module, admission_module])
def test_spine_modules_have_no_runtime_surfaces_import_only_public_names_and_share_one_scanner(module) -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")
    if module is not intake_module:
        assert "re.compile" not in source
        assert "edge_scope_violation" in source
    assert re.search(r"\d\.\d{18}", source) is None
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
            if node.module.startswith("crypto_core.data"):
                assert node.module == "crypto_core.data.requirements"
            if node.module.startswith("crypto_core"):
                assert all(not alias.name.startswith("_") for alias in node.names), node.module
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS
        assert not (isinstance(node, ast.Constant) and type(node.value) is float)


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(admission_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_edge_strategy_spec_admission(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["edge_strategy_spec_admission.py"]
