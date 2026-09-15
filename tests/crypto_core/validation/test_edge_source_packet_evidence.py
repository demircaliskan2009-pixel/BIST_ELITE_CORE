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
    build_edge_kill_criteria_policy,
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
    edge_source_packet_evidence_from_canonical_json,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_PREFIX = "edge_source_packet_evidence:"
_FLAGS = dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_BTC = "BTC-PERPETUAL"
_ETH = "ETH-PERPETUAL"
_SOL = "SOL-PERPETUAL"
_CORRELATION = "corr-funding-carry-001"
_CRITERIA = (
    EdgeKillCriterion(
        criterion_id="max_drawdown_breach",
        metric_id="max_drawdown_fraction",
        comparator=EdgeKillCriterionComparator.KILL_IF_AT_OR_ABOVE,
        threshold="0.250000000000000000",
        evaluation_basis="rolling_30_utc_days",
    ),
)


def _intake(
    *, rights_status: str = "own_research", approved: bool = True, **overrides: object
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
    policy = build_edge_kill_criteria_policy(
        policy_id="policy-kill-criteria-001",
        correlation_id=_CORRELATION,
        kill_criteria=_CRITERIA,
        thresholds_approved=approved,
        approval_reference="governance-kill-criteria-approval-001",
        approval_digest="a" * 64,
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
        "kill_criteria_draft": _CRITERIA,
        "kill_criteria_policy": policy,
        "expected_kill_criteria_policy_digest": policy.policy_digest,
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


def _parsed_registry(payload: dict):
    result = data_requirement_registry_from_dict(payload)
    assert result.accepted, result.rejection_reasons
    return result.registry


def _registry_with(key: DataRequirementKey, **changes: object):
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    payload["requirements"][key.value].update(changes)
    return _parsed_registry(payload)


def _registry_without(key: DataRequirementKey):
    payload = data_requirement_registry_to_dict(default_perp_data_requirement_registry())
    del payload["requirements"][key.value]
    return _parsed_registry(payload)


def _build(intake=None, registry=None, **overrides: object) -> EdgeSourcePacketEvidence:
    intake = _intake() if intake is None else intake
    registry = default_perp_data_requirement_registry() if registry is None else registry
    kwargs: dict[str, object] = {
        "expected_root_intake_digest": intake.intake_digest,
        "data_requirement_registry": registry,
        "series": (_series(), _mark_series()),
        "packet_evidence_id": "packet-funding-carry-001",
        "correlation_id": _CORRELATION,
    }
    kwargs.update(overrides)
    if "expected_data_requirement_registry_digest" not in kwargs:
        kwargs["expected_data_requirement_registry_digest"] = data_requirement_registry_digest(registry)
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
    assert evidence.integrity_reason_codes == ()
    assert evidence.verdict_reason_codes == tuple(_PREFIX + code for code in codes)
    assert verify_edge_source_packet_evidence(evidence).intact is True


def _assert_rejected(evidence: EdgeSourcePacketEvidence, *codes: str) -> None:
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.advances is False
    assert evidence.verdict_reason_codes == ()
    assert (evidence.verified_root_intake_digest, evidence.verified_data_requirement_registry_digest) == ("", "")
    for code in codes:
        assert _PREFIX + code in evidence.integrity_reason_codes, evidence.integrity_reason_codes
    assert verify_edge_source_packet_evidence(evidence).intact is True


# --- 1. Valid PIT packet and determinism ---------------------------------------------------------------------


def test_valid_pit_packet_is_ready_pass_and_carries_authenticated_snapshots() -> None:
    intake = _intake()
    registry = default_perp_data_requirement_registry()
    evidence = _build(intake, registry)
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert json.loads(evidence.root_intake_snapshot_json) == edge_idea_intake_evidence_to_dict(intake)
    assert json.loads(evidence.data_requirement_registry_snapshot_json) == data_requirement_registry_to_dict(registry)
    assert [record.series_id for record in evidence.series] == ["funding-rate-archive", "mark-price-archive"]
    assert evidence.packet_instrument_coverage == (_BTC, _ETH)
    assert evidence.declared_data_requirement_keys == intake.data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.verified_root_intake_digest == intake.intake_digest
    assert evidence.verified_data_requirement_registry_digest == data_requirement_registry_digest(registry)
    assert evidence.registry_keys == tuple(sorted(key.value for key in DataRequirementKey))
    assert evidence.data_requirement_registry_schema_version == "1.0"


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
    assert {field.name for field in fields(EdgeInputSeries)}.isdisjoint(
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
    assert (
        verify_edge_source_packet_evidence(base).canonical_json
        == verify_edge_source_packet_evidence(permuted).canonical_json
    )
    assert _build(series=(_series(source_reference="dataset:funding-history-v2"), _mark_series())) != base


def test_output_is_frozen_and_strict_parser_reconstructs_exactly() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.advances = False  # type: ignore[misc]
    canonical = verify_edge_source_packet_evidence(evidence).canonical_json
    assert edge_source_packet_evidence_from_canonical_json(canonical) == evidence
    payload = json.loads(canonical)
    for text in (
        json.dumps({**payload, "extra": 1}, sort_keys=True, separators=(",", ":")),
        json.dumps(payload),
        json.dumps(
            {**payload, "series": [{**payload["series"][0], "unknown": 1}]}, sort_keys=True, separators=(",", ":")
        ),
        json.dumps({**payload, "status": "ACCEPTED"}, sort_keys=True, separators=(",", ":")),
    ):
        with pytest.raises(EdgeSourcePacketEvidenceError, match="packet_snapshot_malformed"):
            edge_source_packet_evidence_from_canonical_json(text)


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
    _assert_ready(
        _build(series=(_series(finality=EdgeSeriesFinality.UNKNOWN), _mark_series())),
        EdgeGateVerdict.NEEDS_EXTERNAL_FACTS,
        ("series_finality_unknown:funding-rate-archive",),
    )
    _assert_ready(
        _build(series=(_series(), _mark_series(revision_policy=EdgeSeriesRevisionPolicy.UNKNOWN))),
        EdgeGateVerdict.NEEDS_EXTERNAL_FACTS,
        ("series_revision_policy_unknown:mark-price-archive",),
    )


def test_revisions_without_point_in_time_vintages_fail_but_vintaged_revisions_pass() -> None:
    _assert_ready(
        _build(series=(_series(revision_policy=EdgeSeriesRevisionPolicy.REVISED_WITHOUT_VINTAGES), _mark_series())),
        EdgeGateVerdict.FAIL,
        ("series_revised_without_point_in_time_vintages:funding-rate-archive",),
    )
    _assert_ready(
        _build(
            series=(
                _series(revision_policy=EdgeSeriesRevisionPolicy.REVISED_WITH_POINT_IN_TIME_VINTAGES),
                _mark_series(),
            )
        ),
        EdgeGateVerdict.PASS,
        (),
    )


def test_fail_dominates_needs_in_the_packet_verdict() -> None:
    evidence = _build(
        series=(
            _series(finality=EdgeSeriesFinality.UNKNOWN),
            _mark_series(rights_status=SourcePacketRightsStatus.RESTRICTED),
        )
    )
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert len(evidence.verdict_reason_codes) == 2


# --- 3. DataRequirement coverage, rights and instrument coverage ---------------------------------------------


def test_declared_requirement_not_covered_by_any_series_fails() -> None:
    _assert_ready(
        _build(series=(_series(),)), EdgeGateVerdict.FAIL, ("declared_data_requirement_not_covered:mark_price",)
    )


def test_series_not_declared_in_the_root_fails() -> None:
    index = _series("index-price-archive", DataRequirementKey.INDEX_PRICE, source_reference="dataset:index-history-v1")
    _assert_ready(
        _build(series=(_series(), _mark_series(), index)),
        EdgeGateVerdict.FAIL,
        ("series_data_requirement_not_declared_in_intake:index-price-archive",),
    )


def test_series_key_missing_from_the_registry_fails_and_records_no_invented_policy() -> None:
    evidence = _build(registry=_registry_without(DataRequirementKey.MARK_PRICE))
    _assert_ready(evidence, EdgeGateVerdict.FAIL, ("series_data_requirement_not_in_registry:mark-price-archive",))
    mark = evidence.series[1]
    assert (mark.event_time_policy, mark.available_at_policy, mark.finalized_at_policy, mark.availability_mode) == (
        "",
    ) * 4
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


def test_restricted_series_rights_fail_and_usable_rights_reuse_the_source_packet_vocabulary() -> None:
    _assert_ready(
        _build(series=(_series(rights_status=SourcePacketRightsStatus.RESTRICTED), _mark_series())),
        EdgeGateVerdict.FAIL,
        ("series_rights_restricted:funding-rate-archive",),
    )
    for status in SourcePacketRightsStatus:
        if status is not SourcePacketRightsStatus.RESTRICTED:
            _assert_ready(_build(series=(_series(rights_status=status), _mark_series())), EdgeGateVerdict.PASS, ())


# --- 4. B2: EF-2 root authority ------------------------------------------------------------------------------


def test_root_anchor_mismatch_is_a_truthful_rejected_receipt() -> None:
    evidence = _build(expected_root_intake_digest="0" * 64)
    _assert_rejected(evidence, "root_intake_digest_mismatch")
    assert evidence.declared_data_requirement_keys == ()


def test_chain_splice_with_another_valid_root_is_rejected() -> None:
    other = _intake(intake_id="intake-funding-carry-002")
    assert other.gate_verdict is EdgeGateVerdict.PASS
    _assert_rejected(_build(_intake(), expected_root_intake_digest=other.intake_digest), "root_intake_digest_mismatch")


def test_tampered_root_without_reseal_is_rejected() -> None:
    intake = replace(_intake(), edge_family="momentum_trend")
    _assert_rejected(
        _build(intake, expected_root_intake_digest=intake.intake_digest),
        "root_intake_integrity_failure:edge_idea_intake_evidence:self_digest_mismatch",
    )


def test_resealed_root_with_forged_pass_verdict_is_rejected() -> None:
    needs = _intake(approved=False)
    forged = replace(needs, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    forged = replace(forged, intake_digest=edge_idea_intake_evidence_digest(forged))
    _assert_rejected(
        _build(forged, expected_root_intake_digest=forged.intake_digest),
        "root_intake_integrity_failure:edge_idea_intake_evidence:field_mismatch:gate_verdict",
    )


def test_correlation_mismatch_with_the_root_is_rejected() -> None:
    _assert_rejected(_build(correlation_id="corr-funding-carry-999"), "correlation_id_mismatch")


@pytest.mark.parametrize(
    ("intake_factory", "verdict"),
    [
        (lambda: _intake(approved=False), "NEEDS_GOVERNANCE_APPROVAL"),
        (lambda: _intake(external_fact_needs=("venue_funding_interval_mechanics",)), "NEEDS_EXTERNAL_FACTS"),
        (lambda: _intake(rights_status="restricted"), "FAIL"),
        (lambda: _intake(expected_source_packet_digest="0" * 64), "NOT_EVALUATED"),
    ],
)
def test_non_passing_root_can_never_advance(intake_factory, verdict: str) -> None:
    evidence = _build(intake_factory())
    _assert_rejected(evidence, f"root_intake_not_passed:{verdict}")
    assert evidence.integrity_reason_codes == (_PREFIX + f"root_intake_not_passed:{verdict}",)


@pytest.mark.parametrize(
    "changes",
    [
        {"declared_data_requirement_keys": ("funding_rate",)},
        {"verified_root_intake_digest": "f" * 64},
        {"root_intake_snapshot_json": ""},
    ],
)
def test_resealed_root_owned_copies_are_checked_against_the_authenticated_root(changes: dict) -> None:
    forged = _reseal(_build(), **changes)
    codes = _codes(forged)
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert codes and all(code.startswith(_PREFIX + "field_mismatch:") for code in codes)


def test_resealed_correlation_relabel_cannot_keep_the_root_binding() -> None:
    forged = _reseal(_build(), correlation_id="corr-funding-carry-999")
    assert _PREFIX + "field_mismatch:status" in _codes(forged)


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


# --- 5. B3: DataRequirementRegistry authority ----------------------------------------------------------------


def test_registry_anchor_mismatch_is_rejected() -> None:
    _assert_rejected(
        _build(expected_data_requirement_registry_digest="0" * 64), "data_requirement_registry_digest_mismatch"
    )


def test_forged_registry_requirement_is_rejected_even_with_a_matching_anchor() -> None:
    registry = default_perp_data_requirement_registry()
    requirement = replace(registry.requirements[DataRequirementKey.FUNDING_RATE], finalized_at_policy="")
    forged = replace(registry, requirements={**registry.requirements, DataRequirementKey.FUNDING_RATE: requirement})
    _assert_rejected(_build(registry=forged), "data_requirement_registry_invalid")


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
    assert evidence.data_requirement_registry_snapshot_json == ""


def test_resealed_paper_parity_upgrade_of_a_historical_only_series_fails_verification() -> None:
    registry = _registry_with(
        DataRequirementKey.MARK_PRICE, availability_mode="historical_only", paper_observation_source=None
    )
    failing = _build(registry=registry)
    forged_mark = replace(
        failing.series[1], availability_mode="paper_parity", paper_observation_source="invented_stream_v1"
    )
    forged = _reseal(
        failing,
        series=(failing.series[0], forged_mark),
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    codes = _codes(forged)
    assert _PREFIX + "self_digest_mismatch" not in codes
    assert _PREFIX + "field_mismatch:series" in codes
    assert _PREFIX + "field_mismatch:gate_verdict" in codes


@pytest.mark.parametrize(
    "record_changes",
    [
        {"event_time_policy": "caller_declared_event_ns"},
        {"finalized_at_policy": "trade_finalized_ns"},
        {"funding_semantics": "final_by_assertion"},
        {"finality_policy": None},
    ],
)
def test_resealed_registry_owned_series_policies_fail_verification(record_changes: dict) -> None:
    evidence = _build()
    forged = _reseal(evidence, series=(replace(evidence.series[0], **record_changes), evidence.series[1]))
    assert _PREFIX + "field_mismatch:series" in _codes(forged)


@pytest.mark.parametrize(
    "changes",
    [
        {"registry_keys": ("funding_rate", "mark_price")},
        {"data_requirement_registry_schema_version": "2.0"},
        {"packet_instrument_coverage": (_BTC, _ETH, _SOL)},
    ],
)
def test_resealed_registry_and_coverage_summaries_fail_verification(changes: dict) -> None:
    (name,) = changes
    assert _PREFIX + f"field_mismatch:{name}" in _codes(_reseal(_build(), **changes))


def test_swapped_registry_snapshot_cannot_keep_a_ready_packet() -> None:
    other = _registry_with(
        DataRequirementKey.MARK_PRICE, availability_mode="historical_only", paper_observation_source=None
    )
    forged = _reseal(
        _build(),
        data_requirement_registry_snapshot_json=json.dumps(
            data_requirement_registry_to_dict(other), sort_keys=True, separators=(",", ":")
        ),
    )
    assert _PREFIX + "field_mismatch:status" in _codes(forged)


def test_ready_packet_with_registry_owned_text_outside_the_caller_vocabulary_still_reverifies() -> None:
    registry = _registry_with(
        DataRequirementKey.FUNDING_RATE,
        event_time_policy="funding_window\topen_ns",
        available_at_policy="order_id_sequence_published_ns",
    )
    evidence = _build(registry=registry)
    _assert_ready(evidence, EdgeGateVerdict.PASS, ())
    assert evidence.series[0].available_at_policy == "order_id_sequence_published_ns"


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


# --- 7. B7: truthful READY and REJECTED receipts -------------------------------------------------------------


def test_field_tamper_without_reseal_fails_verification() -> None:
    assert _PREFIX + "self_digest_mismatch" in _codes(replace(_build(), packet_instrument_coverage=(_BTC, _ETH, _SOL)))


def test_resealed_fail_verdict_upgraded_to_pass_fails_reassembly() -> None:
    failing = _build(series=(_series(finality=EdgeSeriesFinality.INCLUDES_UNFINALIZED), _mark_series()))
    forged = _reseal(failing, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert _PREFIX + "field_mismatch:gate_verdict" in _codes(forged)


@pytest.mark.parametrize(
    "changes",
    [
        {"integrity_reason_codes": (_PREFIX + "root_intake_digest_mismatch", _PREFIX + "invented_reason")},
        {"integrity_reason_codes": (_PREFIX + "data_requirement_registry_digest_mismatch",)},
    ],
)
def test_rejected_receipt_with_inconsistent_reason_codes_does_not_verify(changes: dict) -> None:
    rejected = _build(expected_root_intake_digest="0" * 64)
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in _codes(_reseal(rejected, **changes))


def test_passing_packet_forged_into_a_rejected_receipt_does_not_verify() -> None:
    forged = _reseal(
        _build(),
        status=EdgeEvidenceStatus.REJECTED,
        gate_verdict=EdgeGateVerdict.NOT_EVALUATED,
        advances=False,
        integrity_reason_codes=(_PREFIX + "root_intake_digest_mismatch",),
    )
    assert _PREFIX + "field_mismatch:integrity_reason_codes" in _codes(forged)


def test_malformed_rejected_semantics_do_not_verify() -> None:
    rejected = _build(expected_root_intake_digest="0" * 64)
    assert _PREFIX + "evidence_semantics_malformed" in _codes(_reseal(rejected, expected_root_intake_digest="short"))
    bad_record = replace(rejected.series[0], finality="sometimes")
    assert _PREFIX + "evidence_semantics_malformed" in _codes(
        _reseal(rejected, series=(bad_record, rejected.series[1]))
    )


@pytest.mark.parametrize("flag", sorted(_FLAGS))
def test_resealed_structural_claim_fails_verification(flag: str) -> None:
    assert _PREFIX + f"field_mismatch:{flag}" in _codes(_reseal(_build(), **{flag: not _FLAGS[flag]}))


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
    (name,) = changes
    assert _PREFIX + f"field_mismatch:{name}" in _codes(_reseal(_build(), **changes))


def test_forged_or_non_serializable_evidence_never_raises() -> None:
    assert _codes(replace(_build(), series=(object(),))) == (_PREFIX + "evidence_serialization_failed",)  # type: ignore[arg-type]
    assert _codes(replace(_build(), gate_verdict="PASS")) == (_PREFIX + "evidence_type_invalid",)  # type: ignore[arg-type]
    assert _codes(_intake()) == (_PREFIX + "evidence_type_invalid",)


# --- 8. Structural non-overclaim and source surface ----------------------------------------------------------


def test_structural_non_claims_are_defaults_and_cannot_be_set_by_the_builder() -> None:
    evidence = _build()
    for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is expected
    assert {field.name: field.default for field in fields(EdgeSourcePacketEvidence) if field.name in _FLAGS} == _FLAGS
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


def test_source_has_no_forbidden_runtime_surfaces_imports_only_public_names_and_no_own_scanner() -> None:
    source = Path(packet_module.__file__).read_text(encoding="utf-8")
    assert "re.compile" not in source
    for node in ast.walk(ast.parse(source)):
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
    validation_dir = Path(packet_module.__file__).parent
    builders = sorted(
        path.name
        for path in validation_dir.glob("*.py")
        if "def build_edge_source_packet_evidence(" in path.read_text(encoding="utf-8")
    )
    assert builders == ["edge_source_packet_evidence.py"]
