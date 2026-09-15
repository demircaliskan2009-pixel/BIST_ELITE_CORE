"""Adversarial contract tests for Edge Factory EF-3 PIT-grade edge source packet evidence."""

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
    data_requirement_registry_from_dict,
    data_requirement_registry_to_dict,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import SourcePacketRightsStatus, build_source_packet
from crypto_core.validation import edge_source_packet_evidence as packet_module
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    edge_idea_intake_evidence_digest,
    edge_idea_intake_evidence_to_dict,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    EdgeSeriesFinality,
    EdgeSeriesRevisionPolicy,
    EdgeSourcePacketEvidence,
    EdgeSourcePacketEvidenceError,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_digest,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_PREFIX = "edge_source_packet_evidence:"
_FLAGS = dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_BTC = "BTC-PERPETUAL"
_ETH = "ETH-PERPETUAL"
_SOL = "SOL-PERPETUAL"
_CORRELATION = "corr-funding-carry-001"


def _intake(*, rights_status: str = "own_research", **overrides: object) -> EdgeIdeaIntakeEvidence:
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
    kwargs: dict[str, object] = {
        "expected_source_packet_digest": packet.packet_digest,
        "intake_id": "intake-funding-carry-001",
        "correlation_id": _CORRELATION,
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Leveraged long demand pays a persistent funding premium to delta-neutral carry",
        "data_requirement_keys": (DataRequirementKey.FUNDING_RATE, DataRequirementKey.MARK_PRICE),
        "declared_regime_dependence": "positive_funding_premium_regime",
        "kill_criteria_draft": (
            EdgeKillCriterion(
                criterion_id="max_drawdown_breach",
                metric_id="max_drawdown_fraction",
                comparator=EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
                threshold="0.250000000000000000",
                evaluation_basis="rolling_30_utc_days",
            ),
        ),
        "kill_criteria_thresholds_approved": True,
        "kill_criteria_approval_reference": "governance-kill-criteria-approval-001",
        "kill_criteria_approval_digest": "a" * 64,
    }
    kwargs.update(overrides)
    return build_edge_idea_intake_evidence(packet, **kwargs)  # type: ignore[arg-type]


def _series(
    series_id: object = "funding-rate-archive",
    key: object = DataRequirementKey.FUNDING_RATE,
    *,
    source_reference: object = "dataset:funding-history-v1",
    rights_status: object = SourcePacketRightsStatus.OWN_RESEARCH,
    rights_reference: object = "self-collected-public-archive",
    finality: object = EdgeSeriesFinality.FINALIZED_ONLY,
    revision_policy: object = EdgeSeriesRevisionPolicy.IMMUTABLE_AFTER_FINALIZATION,
    instrument_coverage: object = (_BTC, _ETH),
) -> EdgeInputSeries:
    return EdgeInputSeries(
        series_id=series_id,  # type: ignore[arg-type]
        data_requirement_key=key,  # type: ignore[arg-type]
        source_reference=source_reference,  # type: ignore[arg-type]
        rights_status=rights_status,  # type: ignore[arg-type]
        rights_reference=rights_reference,  # type: ignore[arg-type]
        finality=finality,  # type: ignore[arg-type]
        revision_policy=revision_policy,  # type: ignore[arg-type]
        instrument_coverage=instrument_coverage,  # type: ignore[arg-type]
    )


def _mark_series(**overrides: object) -> EdgeInputSeries:
    kwargs: dict[str, object] = {
        "source_reference": "dataset:mark-price-history-v1",
        "instrument_coverage": (_ETH, _BTC, _SOL),
    }
    kwargs.update(overrides)
    return _series("mark-price-archive", DataRequirementKey.MARK_PRICE, **kwargs)  # type: ignore[arg-type]


def _registry_payload() -> dict:
    return data_requirement_registry_to_dict(default_perp_data_requirement_registry())


def _parsed_registry(payload: dict):
    result = data_requirement_registry_from_dict(payload)
    assert result.accepted, result.rejection_reasons
    return result.registry


def _registry_with(key: DataRequirementKey, **changes: object):
    payload = _registry_payload()
    payload["requirements"][key.value].update(changes)
    return _parsed_registry(payload)


def _registry_without(key: DataRequirementKey):
    payload = _registry_payload()
    del payload["requirements"][key.value]
    return _parsed_registry(payload)


def _build(intake=None, registry=None, **overrides: object) -> EdgeSourcePacketEvidence:
    intake = _intake() if intake is None else intake
    registry = default_perp_data_requirement_registry() if registry is None else registry
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


def _reseal(evidence: EdgeSourcePacketEvidence, **changes: object) -> EdgeSourcePacketEvidence:
    forged = replace(evidence, **changes)
    return replace(forged, packet_evidence_digest=edge_source_packet_evidence_digest(forged))


def _codes(evidence: object) -> tuple[str, ...]:
    return verify_edge_source_packet_evidence(evidence).reason_codes


def _assert_ready(evidence: EdgeSourcePacketEvidence, verdict: EdgeGateVerdict, codes: tuple[str, ...]) -> None:
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is verdict
    assert evidence.advances is (verdict is EdgeGateVerdict.PASS)
    assert evidence.verdict_reason_codes == tuple(_PREFIX + code for code in codes)
    assert verify_edge_source_packet_evidence(evidence).intact is True


def _assert_rejected(evidence: EdgeSourcePacketEvidence, *codes: str) -> None:
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.advances is False
    assert evidence.verdict_reason_codes == ()
    for code in codes:
        assert _PREFIX + code in evidence.integrity_reason_codes, evidence.integrity_reason_codes
    assert verify_edge_source_packet_evidence(evidence).intact is True


# --- 1. Valid PIT packet and determinism ---------------------------------------------------------------------


def test_valid_pit_packet_is_ready_pass_and_advances() -> None:
    evidence = _build()
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert [record.series_id for record in evidence.series] == ["funding-rate-archive", "mark-price-archive"]
    assert evidence.packet_instrument_coverage == (_BTC, _ETH)
    assert evidence.declared_data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.verified_root_intake_digest == _intake().intake_digest
    assert evidence.verified_data_requirement_registry_digest == data_requirement_registry_digest(
        default_perp_data_requirement_registry()
    )
    assert evidence.registry_keys == tuple(sorted(key.value for key in DataRequirementKey))
    assert evidence.data_requirement_registry_schema_version == "1.0"
    assert verify_edge_source_packet_evidence(evidence).recomputed_digest == evidence.packet_evidence_digest


def test_every_series_carries_registry_owned_event_available_finalized_semantics() -> None:
    registry = default_perp_data_requirement_registry()
    for record in _build().series:
        requirement = registry.requirements[DataRequirementKey(record.data_requirement_key)]
        assert record.event_time_policy == requirement.event_time_policy != ""
        assert record.available_at_policy == requirement.available_at_policy != ""
        assert record.finalized_at_policy == requirement.finalized_at_policy != ""
        assert record.finality_policy == requirement.finality_policy
        assert record.funding_semantics == requirement.funding_semantics
        assert record.availability_mode == requirement.availability_mode.value == "paper_parity"
    declared_fields = {field.name for field in fields(EdgeInputSeries)}
    assert declared_fields.isdisjoint(
        {"event_time_policy", "available_at_policy", "finalized_at_policy", "finality_policy", "funding_semantics"}
    )


def test_digest_is_canonical_sha256_of_public_payload_without_self_digest() -> None:
    evidence = _build()
    payload = edge_source_packet_evidence_to_dict(evidence)
    carried = payload.pop("packet_evidence_digest")
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    assert (
        carried == hashlib.sha256(canonical.encode("utf-8")).hexdigest() == edge_source_packet_evidence_digest(evidence)
    )


def test_series_and_coverage_order_cannot_change_identity() -> None:
    base = _build()
    permuted = _build(
        series=[_mark_series(instrument_coverage=[_SOL, _BTC, _ETH]), _series(instrument_coverage=(_ETH, _BTC))]
    )
    assert base.packet_evidence_digest == permuted.packet_evidence_digest
    assert (
        verify_edge_source_packet_evidence(base).canonical_json
        == verify_edge_source_packet_evidence(permuted).canonical_json
    )


def test_semantic_change_changes_digest() -> None:
    changed = _build(series=(_series(source_reference="dataset:funding-history-v2"), _mark_series()))
    assert changed.packet_evidence_digest != _build().packet_evidence_digest


def test_output_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        _build().advances = False  # type: ignore[misc]


# --- 2. Finality, revisions and PIT ---------------------------------------------------------------------------


def test_unfinalized_series_is_fail_and_cannot_advance() -> None:
    evidence = _build(series=(_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series()))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("series_unfinalized_feature_input:funding-rate-archive",))


def test_predicted_funding_semantics_are_unfinalized_even_when_declared_finalized() -> None:
    evidence = _build(registry=_registry_with(DataRequirementKey.FUNDING_RATE, funding_semantics="predicted"))
    _assert_ready(
        evidence, EdgeGateVerdict.FAIL, ("series_funding_semantics_predicted_unfinalized:funding-rate-archive",)
    )


def test_unknown_finality_or_revision_behaviour_needs_external_facts() -> None:
    unknown_finality = _build(series=(_series(finality=EdgeSeriesFinality.UNKNOWN), _mark_series()))
    _assert_ready(
        unknown_finality, EdgeGateVerdict.NEEDS_EXTERNAL_FACTS, ("series_finality_unknown:funding-rate-archive",)
    )
    unknown_revision = _build(series=(_series(), _mark_series(revision_policy=EdgeSeriesRevisionPolicy.UNKNOWN)))
    _assert_ready(
        unknown_revision, EdgeGateVerdict.NEEDS_EXTERNAL_FACTS, ("series_revision_policy_unknown:mark-price-archive",)
    )


def test_revisions_without_point_in_time_vintages_fail_but_vintaged_revisions_pass() -> None:
    overwritten = _build(
        series=(_series(revision_policy=EdgeSeriesRevisionPolicy.REVISED_WITHOUT_VINTAGES), _mark_series())
    )
    _assert_ready(
        overwritten, EdgeGateVerdict.FAIL, ("series_revised_without_point_in_time_vintages:funding-rate-archive",)
    )
    vintaged = _build(
        series=(_series(revision_policy=EdgeSeriesRevisionPolicy.REVISED_WITH_POINT_IN_TIME_VINTAGES), _mark_series())
    )
    _assert_ready(vintaged, EdgeGateVerdict.PASS, ())


def test_fail_dominates_needs_in_the_packet_verdict() -> None:
    evidence = _build(
        series=(
            _series(finality=EdgeSeriesFinality.UNKNOWN),
            _mark_series(rights_status=SourcePacketRightsStatus.RESTRICTED),
        )
    )
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert len(evidence.verdict_reason_codes) == 2


# --- 3. DataRequirement coverage and instrument coverage -----------------------------------------------------


def test_declared_requirement_not_covered_by_any_series_fails() -> None:
    _assert_ready(
        _build(series=(_series(),)), EdgeGateVerdict.FAIL, ("declared_data_requirement_not_covered:mark_price",)
    )


def test_series_not_declared_in_the_intake_fails() -> None:
    index = _series("index-price-archive", DataRequirementKey.INDEX_PRICE, source_reference="dataset:index-history-v1")
    evidence = _build(series=(_series(), _mark_series(), index))
    _assert_ready(
        evidence, EdgeGateVerdict.FAIL, ("series_data_requirement_not_declared_in_intake:index-price-archive",)
    )


def test_series_key_missing_from_the_registry_fails_and_records_no_invented_policy() -> None:
    evidence = _build(registry=_registry_without(DataRequirementKey.MARK_PRICE))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("series_data_requirement_not_in_registry:mark-price-archive",))
    mark = evidence.series[1]
    assert (mark.event_time_policy, mark.available_at_policy, mark.finalized_at_policy, mark.availability_mode) == (
        "",
        "",
        "",
        "",
    )
    assert "mark_price" not in evidence.registry_keys


def test_historical_only_series_without_paper_parity_fails() -> None:
    registry = _registry_with(
        DataRequirementKey.MARK_PRICE, availability_mode="historical_only", paper_observation_source=None
    )
    _assert_ready(
        _build(registry=registry), EdgeGateVerdict.FAIL, ("series_paper_parity_unavailable:mark-price-archive",)
    )


def test_disjoint_instrument_coverage_leaves_an_empty_packet_that_fails() -> None:
    evidence = _build(series=(_series(instrument_coverage=(_BTC,)), _mark_series(instrument_coverage=(_ETH,))))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("packet_instrument_coverage_empty",))
    assert evidence.packet_instrument_coverage == ()


# --- 4. Rights -----------------------------------------------------------------------------------------------


def test_restricted_series_rights_fail_and_never_silently_pass() -> None:
    evidence = _build(series=(_series(rights_status=SourcePacketRightsStatus.RESTRICTED), _mark_series()))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("series_rights_restricted:funding-rate-archive",))


@pytest.mark.parametrize(
    "rights_status",
    [status for status in SourcePacketRightsStatus if status is not SourcePacketRightsStatus.RESTRICTED],
)
def test_usable_rights_reuse_the_source_packet_vocabulary(rights_status: SourcePacketRightsStatus) -> None:
    evidence = _build(series=(_series(rights_status=rights_status), _mark_series()))
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert evidence.series[0].rights_status == rights_status.value
    assert evidence.rights_vocabulary == "crypto_core.strategy.source_packet.SourcePacketRightsStatus"


# --- 5. Root anchor, registry anchor and splicing ------------------------------------------------------------


def test_root_anchor_mismatch_is_rejected() -> None:
    evidence = _build(expected_root_intake_digest="0" * 64)
    _assert_rejected(evidence, "root_intake_digest_mismatch")
    assert evidence.verified_root_intake_digest == ""
    assert evidence.declared_data_requirement_keys == ()


def test_chain_splice_with_another_valid_root_is_rejected() -> None:
    other = _intake(intake_id="intake-funding-carry-002")
    assert other.gate_verdict is EdgeGateVerdict.PASS
    _assert_rejected(_build(_intake(), expected_root_intake_digest=other.intake_digest), "root_intake_digest_mismatch")


def test_tampered_root_without_reseal_is_rejected() -> None:
    intake = replace(_intake(), edge_family="momentum_trend")
    evidence = _build(intake, expected_root_intake_digest=intake.intake_digest)
    _assert_rejected(evidence, "root_intake_integrity_failure:edge_idea_intake_evidence:self_digest_mismatch")


def test_resealed_root_with_forged_pass_verdict_is_rejected() -> None:
    needs = _intake(kill_criteria_thresholds_approved=False)
    forged = replace(needs, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    forged = replace(forged, intake_digest=edge_idea_intake_evidence_digest(forged))
    evidence = _build(forged, expected_root_intake_digest=forged.intake_digest)
    _assert_rejected(evidence, "root_intake_integrity_failure:edge_idea_intake_evidence:verdict_rederivation_mismatch")


def test_correlation_mismatch_with_the_root_is_rejected() -> None:
    _assert_rejected(_build(correlation_id="corr-funding-carry-999"), "correlation_id_mismatch")


@pytest.mark.parametrize(
    ("intake_factory", "verdict"),
    [
        (lambda: _intake(kill_criteria_thresholds_approved=False), "NEEDS_GOVERNANCE_APPROVAL"),
        (lambda: _intake(external_fact_needs=("venue_funding_interval_mechanics",)), "NEEDS_EXTERNAL_FACTS"),
        (lambda: _intake(rights_status="restricted"), "FAIL"),
        (lambda: _intake(expected_source_packet_digest="0" * 64), "NOT_EVALUATED"),
    ],
)
def test_non_passing_root_can_never_advance(intake_factory, verdict: str) -> None:
    evidence = _build(intake_factory())
    _assert_rejected(evidence, f"root_intake_not_passed:{verdict}")
    assert evidence.integrity_reason_codes == (_PREFIX + f"root_intake_not_passed:{verdict}",)


def test_registry_anchor_mismatch_is_rejected() -> None:
    _assert_rejected(
        _build(expected_data_requirement_registry_digest="0" * 64), "data_requirement_registry_digest_mismatch"
    )


def test_forged_registry_requirement_is_rejected_even_with_a_matching_anchor() -> None:
    registry = default_perp_data_requirement_registry()
    requirement = replace(registry.requirements[DataRequirementKey.FUNDING_RATE], finalized_at_policy="")
    forged = replace(registry, requirements={**registry.requirements, DataRequirementKey.FUNDING_RATE: requirement})
    evidence = _build(registry=forged)
    assert evidence.expected_data_requirement_registry_digest == data_requirement_registry_digest(forged)
    _assert_rejected(evidence, "data_requirement_registry_invalid")


def test_noncanonical_registry_is_rejected() -> None:
    registry = default_perp_data_requirement_registry()
    requirement = replace(
        registry.requirements[DataRequirementKey.FUNDING_RATE], event_time_policy=" funding_window_open_ns "
    )
    forged = replace(registry, requirements={**registry.requirements, DataRequirementKey.FUNDING_RATE: requirement})
    _assert_rejected(_build(registry=forged), "data_requirement_registry_noncanonical")


def test_non_serializable_registry_is_rejected_without_raw_error() -> None:
    registry = default_perp_data_requirement_registry()
    forged = replace(registry, requirements={"funding_rate": registry.requirements[DataRequirementKey.FUNDING_RATE]})
    evidence = _build(registry=registry, data_requirement_registry=forged)
    _assert_rejected(evidence, "data_requirement_registry_malformed_payload")


# --- 6. Malformed input --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"series": ()}, "series_empty"),
        ({"series": _series()}, "series_malformed"),
        ({"series": ({"series_id": "funding-rate-archive"},)}, "series_item_malformed"),
        ({"series": (_series(), _series())}, "series_id_duplicate"),
        ({"series": (_series(), _series("funding-rate-mirror"))}, "series_data_requirement_key_duplicate"),
        ({"series": (_series(key="funding_rate"),)}, "series_data_requirement_key_invalid"),
        ({"series": (_series(rights_status="own_research"),)}, "series_rights_status_invalid"),
        ({"series": (_series(finality="finalized_only"),)}, "series_finality_invalid"),
        ({"series": (_series(revision_policy="unknown"),)}, "series_revision_policy_invalid"),
        ({"series": (_series(instrument_coverage=()),)}, "instrument_coverage_empty"),
        ({"series": (_series(instrument_coverage=(_BTC, _BTC)),)}, "instrument_symbol_duplicate"),
        ({"series": (_series(instrument_coverage=_BTC),)}, "instrument_coverage_malformed"),
        ({"series": (_series(instrument_coverage=(" " + _BTC,)),)}, "instrument_symbol_invalid"),
        ({"series": (_series(""),)}, "series_id_invalid"),
        ({"series": (_series(rights_reference=None),)}, "series_rights_reference_invalid"),
        ({"series": (_series(source_reference="borsa-istanbul-feed"),)}, "bist_scope_leakage:series_source_reference"),
        (
            {"series": (_series(rights_reference="licensed via private_api terms"),)},
            "forbidden_scope_token:series_rights_reference",
        ),
        ({"series": (_series("funding-live-feed"),)}, "forbidden_scope_token:series_id"),
        ({"series": (_series(instrument_coverage=("BIST30-PERP",)),)}, "bist_scope_leakage:instrument_symbol"),
        ({"expected_root_intake_digest": "x"}, "expected_root_intake_digest_invalid"),
        ({"expected_data_requirement_registry_digest": None}, "expected_data_requirement_registry_digest_invalid"),
        ({"data_requirement_registry": {"schema_version": "1.0"}}, "data_requirement_registry_malformed"),
        ({"packet_evidence_id": 5}, "packet_evidence_id_invalid"),
        ({"correlation_id": "corr-scheduler-001"}, "forbidden_scope_token:correlation_id"),
    ],
)
def test_malformed_input_raises(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeSourcePacketEvidenceError, match=re.escape(_PREFIX + code)):
        _build(**overrides)


def test_non_intake_root_raises() -> None:
    registry = default_perp_data_requirement_registry()
    with pytest.raises(EdgeSourcePacketEvidenceError, match="root_intake_malformed"):
        build_edge_source_packet_evidence(
            edge_idea_intake_evidence_to_dict(_intake()),  # type: ignore[arg-type]
            expected_root_intake_digest=_intake().intake_digest,
            data_requirement_registry=registry,
            expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
            series=(_series(), _mark_series()),
            packet_evidence_id="packet-funding-carry-001",
            correlation_id=_CORRELATION,
        )


# --- 7. Verification of carried packet evidence --------------------------------------------------------------


def test_field_tamper_without_reseal_fails_verification() -> None:
    forged = replace(_build(), packet_instrument_coverage=(_BTC, _ETH, _SOL))
    assert _PREFIX + "self_digest_mismatch" in _codes(forged)


def test_resealed_fail_verdict_upgraded_to_pass_fails_rederivation() -> None:
    failing = _build(series=(_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series()))
    forged = _reseal(failing, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "verdict_rederivation_mismatch" in _codes(forged)


def test_resealed_coverage_widening_fails() -> None:
    forged = _reseal(_build(), packet_instrument_coverage=(_BTC, _ETH, _SOL))
    assert _PREFIX + "packet_instrument_coverage_mismatch" in _codes(forged)


def test_resealed_series_finality_flip_fails_rederivation() -> None:
    failing = _build(series=(_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series()))
    flipped = replace(failing.series[0], finality=EdgeSeriesFinality.FINALIZED_ONLY.value)
    forged = _reseal(failing, series=(flipped, failing.series[1]))
    assert _PREFIX + "verdict_rederivation_mismatch" in _codes(forged)


def test_resealed_pit_policy_erasure_or_unsorted_series_fail() -> None:
    evidence = _build()
    erased = replace(evidence.series[0], finalized_at_policy="")
    assert _PREFIX + "series_noncanonical" in _codes(_reseal(evidence, series=(erased, evidence.series[1])))
    assert _PREFIX + "series_noncanonical" in _codes(_reseal(evidence, series=tuple(reversed(evidence.series))))


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_resealed_structural_claim_fails_verification(flag: str) -> None:
    assert _PREFIX + "structural_non_claim_violation" in _codes(_reseal(_build(), **{flag: not _FLAGS[flag]}))


@pytest.mark.parametrize(
    "changes",
    [
        {"anchor_policy": "independent_predecessor"},
        {"feature_input_finality_rule": "unfinalized_allowed"},
        {"coverage_policy": "union_of_series_coverage.v1"},
        {"pit_policy_source": "caller_declared"},
    ],
)
def test_resealed_constant_tamper_fails(changes: dict[str, object]) -> None:
    assert _PREFIX + "constant_field_mismatch" in _codes(_reseal(_build(), **changes))


def test_resealed_status_verdict_conflation_fails() -> None:
    evidence = _build()
    for changes in ({"status": EdgeEvidenceStatus.REJECTED}, {"advances": False}):
        assert _PREFIX + "status_verdict_incoherent" in _codes(_reseal(evidence, **changes))


def test_forged_or_non_serializable_evidence_never_raises() -> None:
    assert _codes(replace(_build(), series=(object(),))) == (_PREFIX + "evidence_serialization_failed",)  # type: ignore[arg-type]
    assert _codes(replace(_build(), gate_verdict="PASS")) == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]
    assert _codes(_intake()) == (_PREFIX + "evidence_type_invalid",)


# --- 8. Structural non-overclaim and source surface ----------------------------------------------------------


def test_structural_non_claims_are_defaults_and_cannot_be_set_by_the_builder() -> None:
    evidence = _build()
    for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is expected
    defaults = {field.name: field.default for field in fields(EdgeSourcePacketEvidence) if field.name in _FLAGS}
    assert defaults == _FLAGS
    assert set(inspect.signature(build_edge_source_packet_evidence).parameters).isdisjoint(_FLAGS)


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    for evidence in (
        _build(
            series=(
                _series(finality=EdgeSeriesFinality.UNKNOWN),
                _mark_series(rights_status=SourcePacketRightsStatus.RESTRICTED),
            )
        ),
        _build(expected_root_intake_digest="0" * 64, expected_data_requirement_registry_digest="0" * 64),
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
    tree = ast.parse(Path(packet_module.__file__).read_text(encoding="utf-8"))
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


def test_ready_packet_with_registry_owned_text_outside_the_caller_vocabulary_still_reverifies() -> None:
    # Registry text is validated by data/requirements.py, not by the EF caller-text vocabulary or plain-text rule.
    registry = _registry_with(
        DataRequirementKey.FUNDING_RATE,
        event_time_policy="funding_window\topen_ns",
        available_at_policy="order_id_sequence_published_ns",
    )
    evidence = _build(registry=registry)
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert evidence.series[0].available_at_policy == "order_id_sequence_published_ns"


def test_no_equivalent_builder_exists() -> None:
    validation_dir = Path(packet_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_edge_source_packet_evidence(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["edge_source_packet_evidence.py"]
