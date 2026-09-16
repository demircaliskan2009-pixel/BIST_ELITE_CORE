"""Tests for Edge Factory EF-3 ``crypto_core.validation.edge_source_packet_evidence``.

All kill-criterion thresholds below are synthetic test fixtures, never approved production thresholds.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.edge_source_packet_evidence as packet_module
from crypto_core.data.requirements import (
    DataAvailabilityMode,
    DataRequirement,
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import build_source_packet
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
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
    edge_idea_intake_evidence_digest,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    EdgeSeriesFinality,
    EdgeSourcePacketEvidence,
    EdgeSourcePacketEvidenceError,
    EdgeSourceSeriesRecord,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_digest,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_PREFIX = "edge_source_packet_evidence"
_UNSET = object()
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
_REGISTRY_OWNED_FIELDS = tuple(field.name for field in fields(DataRequirement) if field.name != "key")


def _intake(*, with_policy: bool = True, intake_id: str = "intake-1", **overrides: object) -> EdgeIdeaIntakeEvidence:
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
    policy = build_edge_kill_criteria_policy(
        policy_id="policy-1",
        correlation_id="corr-1",
        kill_criteria=_CRITERIA,
        thresholds_approved=True,
        approval_reference="governance-review-1",
        approval_digest="d" * 64,
    )
    arguments: dict[str, object] = {
        "expected_source_packet_digest": packet.packet_digest,
        "intake_id": intake_id,
        "correlation_id": "corr-1",
        "candidate_strategy_id": "alpha-funding-carry",
        "edge_family": "funding_basis_carry",
        "economic_rationale": "Persistent positive funding pays passive carry holders.",
        "data_requirement_keys": ("funding_rate", "mark_price"),
        "declared_regime_dependence": "positive_funding_regime",
        "kill_criteria_draft": _CRITERIA,
        "kill_criteria_policy": policy if with_policy else None,
        "expected_kill_criteria_policy_digest": policy.policy_digest if with_policy else None,
    }
    arguments.update(overrides)
    return build_edge_idea_intake_evidence(packet, **arguments)  # type: ignore[arg-type]


def _registry(
    changes: dict[str, dict[str, object]] | None = None, *, without: tuple[str, ...] = ()
) -> DataRequirementRegistry:
    base = default_perp_data_requirement_registry()
    requirements = {key: value for key, value in base.requirements.items() if key.value not in without}
    for key_name, replacement in (changes or {}).items():
        key = DataRequirementKey(key_name)
        requirements[key] = replace(requirements[key], **replacement)
    return replace(base, requirements=requirements)


_SERIES_DEFAULTS: dict[str, dict[str, object]] = {
    "funding-btc-eth": {
        "data_requirement_key": "funding_rate",
        "source_reference": "venue-archive:funding",
        "instrument_coverage": ("BTC-PERPETUAL", "ETH-PERPETUAL"),
    },
    "mark-majors": {
        "data_requirement_key": DataRequirementKey.MARK_PRICE,
        "source_reference": "venue-archive:mark",
        "instrument_coverage": ("ETH-PERPETUAL", "BTC-PERPETUAL", "SOL-PERPETUAL"),
    },
    "index-btc": {
        "data_requirement_key": "index_price",
        "source_reference": "venue-archive:index",
        "instrument_coverage": ("BTC-PERPETUAL",),
    },
}


def _series(series_id: str = "funding-btc-eth", **overrides: object) -> EdgeInputSeries:
    arguments: dict[str, object] = {
        "series_id": series_id,
        "rights_status": "own_research",
        "rights_reference": "research-note-1",
        "finality": EdgeSeriesFinality.FINALIZED_ONLY,
        "revision_policy": "immutable_after_finalization",
        **_SERIES_DEFAULTS.get(series_id, _SERIES_DEFAULTS["funding-btc-eth"]),
    }
    arguments.update(overrides)
    return EdgeInputSeries(**arguments)  # type: ignore[arg-type]


def _manifest(
    *,
    root: object = _UNSET,
    root_digest: object = _UNSET,
    registry: object = _UNSET,
    registry_digest: object = _UNSET,
    series: object = _UNSET,
    **overrides: object,
) -> EdgeSourcePacketEvidence:
    root = _intake() if root is _UNSET else root
    registry = default_perp_data_requirement_registry() if registry is _UNSET else registry
    arguments: dict[str, object] = {
        "expected_root_intake_digest": root.intake_digest if root_digest is _UNSET else root_digest,  # type: ignore[attr-defined]
        "data_requirement_registry": registry,
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry)  # type: ignore[arg-type]
        if registry_digest is _UNSET
        else registry_digest,
        "manifest_id": "manifest-1",
        "correlation_id": "corr-1",
        "input_series": (_series("mark-majors"), _series()) if series is _UNSET else series,
    }
    arguments.update(overrides)
    return build_edge_source_packet_evidence(root, **arguments)  # type: ignore[arg-type]


def _redigest(evidence: EdgeSourcePacketEvidence) -> EdgeSourcePacketEvidence:
    return replace(evidence, source_packet_evidence_digest=edge_source_packet_evidence_digest(evidence))


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _assert_receipt_invariants(evidence: EdgeSourcePacketEvidence) -> None:
    verification = verify_edge_source_packet_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.source_packet_evidence_digest
    assert edge_source_packet_evidence_from_payload(json.loads(verification.canonical_json)) == evidence
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert evidence.root_intake_digest == evidence.predecessor_digest == evidence.root_intake_binding.expected_digest
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes
        assert evidence.verdict_reason_codes == ()
        if any(code.startswith(_code("root_intake")) for code in evidence.integrity_reason_codes):
            assert evidence.candidate_strategy_id == evidence.edge_family == ""
            assert evidence.intake_data_requirement_keys == ()
    else:
        assert evidence.integrity_reason_codes == ()


# --- happy path -----------------------------------------------------------------------------------------------------


def test_pass_manifest_is_ready_advances_and_re_proves() -> None:
    root = _intake()
    registry = default_perp_data_requirement_registry()
    evidence = _manifest(root=root, registry=registry)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.advances is True
    assert evidence.gate_id == "EF-3"
    assert evidence.predecessor_gate_id == "EF-2"
    assert evidence.root_intake_digest == root.intake_digest
    assert evidence.candidate_strategy_id == "alpha-funding-carry"
    assert evidence.edge_family == "funding_basis_carry"
    assert evidence.intake_data_requirement_keys == ("funding_rate", "mark_price")
    assert evidence.data_requirement_registry_digest == data_requirement_registry_digest(registry)
    assert evidence.data_requirement_registry_schema_version == registry.schema_version
    assert [record.series_id for record in evidence.series] == ["funding-btc-eth", "mark-majors"]
    assert evidence.instrument_coverage == ("BTC-PERPETUAL", "ETH-PERPETUAL")
    assert evidence.feature_input_series_ids == ("funding-btc-eth", "mark-majors")
    assert evidence.regime_label_binding_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    _assert_receipt_invariants(evidence)
    assert edge_source_packet_evidence_payload_is_well_formed(edge_source_packet_evidence_to_dict(evidence)) is True


def test_manifest_is_deterministic_and_series_order_insensitive() -> None:
    assert _manifest(series=(_series(), _series("mark-majors"))) == _manifest()


def test_every_registry_owned_series_property_is_derived_never_declared() -> None:
    assert not {field.name for field in fields(EdgeInputSeries)} & set(_REGISTRY_OWNED_FIELDS)
    registry = default_perp_data_requirement_registry()
    for record in _manifest(registry=registry).series:
        requirement = registry.requirements[DataRequirementKey(record.data_requirement_key)]
        assert record.registry_requirement_bound is True
        for name in _REGISTRY_OWNED_FIELDS:
            expected = getattr(requirement, name)
            assert getattr(record, name) == (expected.value if name == "availability_mode" else expected)


def test_coverage_is_per_requirement_union_intersected_across_requirements() -> None:
    series = (
        _series("funding-btc", data_requirement_key="funding_rate", instrument_coverage=("BTC-PERPETUAL",)),
        _series("funding-eth", data_requirement_key="funding_rate", instrument_coverage=("ETH-PERPETUAL",)),
        _series("mark-majors"),
    )
    evidence = _manifest(series=series)
    assert evidence.instrument_coverage == ("BTC-PERPETUAL", "ETH-PERPETUAL")
    assert evidence.gate_verdict is EdgeGateVerdict.PASS


# --- verdict states -------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "expected_codes"),
    [
        (
            {"series": (_series("mark-majors"), _series(finality="includes_unfinalized"))},
            {"series_unfinalized:funding-btc-eth"},
        ),
        (
            {"series": (_series("mark-majors"), _series(revision_policy="revised_without_vintages"))},
            {"series_revision_without_point_in_time_vintages:funding-btc-eth"},
        ),
        (
            {"series": (_series("mark-majors"), _series(rights_status="restricted"))},
            {"series_rights_restricted:funding-btc-eth"},
        ),
        ({"series": (_series(),)}, {"intake_data_requirement_without_series:mark_price"}),
        (
            {"series": (_series("mark-majors"), _series(), _series("index-btc"))},
            {"series_data_requirement_not_in_intake:index-btc"},
        ),
        ({"registry": _registry(without=("mark_price",))}, {"series_data_requirement_not_in_registry:mark-majors"}),
        (
            {"registry": _registry({"funding_rate": {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY}})},
            {"series_paper_parity_unavailable:funding-btc-eth"},
        ),
        (
            {"registry": _registry({"funding_rate": {"paper_observation_source": None}})},
            {"series_paper_parity_unavailable:funding-btc-eth"},
        ),
        (
            {"registry": _registry({"funding_rate": {"finality_policy": None}})},
            {"series_registry_finality_policy_missing:funding-btc-eth"},
        ),
        (
            {"registry": _registry({"funding_rate": {"funding_semantics": "predicted"}})},
            {"series_registry_funding_semantics_unfinalized:funding-btc-eth"},
        ),
        (
            {"series": (_series("mark-majors", instrument_coverage=("SOL-PERPETUAL",)), _series())},
            {"instrument_coverage_empty"},
        ),
        ({"root": _intake(with_policy=False)}, {"root_intake_not_advanced"}),
    ],
)
def test_pit_violations_are_valid_negative_evidence(kwargs: dict[str, object], expected_codes: set[str]) -> None:
    evidence = _manifest(**kwargs)
    assert evidence.status is EdgeEvidenceStatus.READY
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected_codes}
    _assert_receipt_invariants(evidence)


def test_registry_unbound_series_carries_no_derived_properties() -> None:
    evidence = _manifest(registry=_registry(without=("mark_price",)))
    record = next(record for record in evidence.series if record.series_id == "mark-majors")
    assert record.registry_requirement_bound is False
    assert all(getattr(record, name) is None for name in _REGISTRY_OWNED_FIELDS)
    assert record.feature_input_eligible is False
    assert evidence.feature_input_series_ids == ("funding-btc-eth",)


@pytest.mark.parametrize(
    ("series", "expected_codes"),
    [
        ((_series("mark-majors"), _series(finality="unknown")), {"series_finality_unknown:funding-btc-eth"}),
        (
            (_series("mark-majors"), _series(revision_policy="unknown")),
            {"series_revision_policy_unknown:funding-btc-eth"},
        ),
    ],
)
def test_unknown_series_facts_stay_external_needs(series: tuple, expected_codes: set[str]) -> None:
    evidence = _manifest(series=series)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert set(evidence.verdict_reason_codes) == {_code(code) for code in expected_codes}
    _assert_receipt_invariants(evidence)


def test_fail_dominates_external_needs() -> None:
    evidence = _manifest(series=(_series("mark-majors", finality="unknown"), _series(rights_status="restricted")))
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("series_finality_unknown:mark-majors") in evidence.verdict_reason_codes


_NOT_FEATURE_READY = [
    ({"finality": "includes_unfinalized"}, None),
    ({"finality": "unknown"}, None),
    ({"revision_policy": "revised_without_vintages"}, None),
    ({"revision_policy": "unknown"}, None),
    ({"rights_status": "restricted"}, None),
    ({}, {"funding_semantics": "predicted"}),
    ({}, {"finality_policy": None}),
    ({}, {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY}),
]


@pytest.mark.parametrize(("series_changes", "registry_changes"), _NOT_FEATURE_READY)
def test_no_unfinalized_or_non_pit_series_is_ever_feature_ready(
    series_changes: dict[str, object], registry_changes: dict[str, object] | None
) -> None:
    registry = _registry({"funding_rate": registry_changes} if registry_changes else None)
    evidence = _manifest(registry=registry, series=(_series("mark-majors"), _series(**series_changes)))
    record = next(record for record in evidence.series if record.series_id == "funding-btc-eth")
    assert record.feature_input_eligible is False
    assert "funding-btc-eth" not in evidence.feature_input_series_ids
    assert evidence.gate_verdict is not EdgeGateVerdict.PASS
    assert evidence.advances is False


def test_revised_series_with_point_in_time_vintages_is_feature_ready() -> None:
    evidence = _manifest(
        series=(_series("mark-majors"), _series(revision_policy="revised_with_point_in_time_vintages"))
    )
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    assert evidence.feature_input_series_ids == ("funding-btc-eth", "mark-majors")


# --- truthful REJECTED receipts -------------------------------------------------------------------------------------


def _forged_root() -> EdgeIdeaIntakeEvidence:
    root = replace(_intake(), source_packet_rights_status="restricted")
    return replace(root, intake_digest=edge_idea_intake_evidence_digest(root))


@pytest.mark.parametrize(
    ("kwargs", "expected_code"),
    [
        ({"root_digest": _intake(intake_id="intake-2").intake_digest}, "root_intake_digest_mismatch"),
        ({"correlation_id": "corr-2"}, "root_intake_correlation_mismatch"),
        (
            {"root": _intake(expected_source_packet_digest="e" * 64)},
            "root_intake_rejected",
        ),
        (
            {"root": _forged_root()},
            "root_intake_integrity_failure:edge_idea_intake_evidence:field_mismatch:source_packet_rights_status",
        ),
        (
            {"registry_digest": data_requirement_registry_digest(_registry(without=("liquidation",)))},
            "data_requirement_registry_digest_mismatch",
        ),
        (
            {"registry": _registry({"funding_rate": {"historical_source": "live_funding_history"}})},
            "data_requirement_registry_not_accepted",
        ),
        (
            {"registry": _registry({"funding_rate": {"historical_source": " funding_history_v1 "}})},
            "data_requirement_registry_noncanonical",
        ),
    ],
)
def test_authentic_authorities_failing_re_proof_are_truthful_rejected_receipts(
    kwargs: dict[str, object], expected_code: str
) -> None:
    evidence = _manifest(**kwargs)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert _code(expected_code) in evidence.integrity_reason_codes
    assert evidence.advances is False
    _assert_receipt_invariants(evidence)


# --- negative-evidence regression: registry PAPER_PARITY spoof ------------------------------------------------------


def test_historical_only_series_cannot_be_declared_paper_parity() -> None:
    with pytest.raises(TypeError):
        EdgeInputSeries(**{**vars(_series()), "availability_mode": "paper_parity"})  # type: ignore[arg-type]
    evidence = _manifest(
        registry=_registry({"funding_rate": {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY}})
    )
    record = next(record for record in evidence.series if record.series_id == "funding-btc-eth")
    assert record.availability_mode == "historical_only"
    assert record.paper_parity_available is False


def test_manifest_level_paper_parity_spoof_fails_verification() -> None:
    evidence = _manifest(
        registry=_registry({"funding_rate": {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY}})
    )
    forged_series = tuple(
        replace(record, availability_mode="paper_parity", paper_parity_available=True, feature_input_eligible=True)
        for record in evidence.series
    )
    forged = _redigest(
        replace(
            evidence,
            series=forged_series,
            feature_input_series_ids=("funding-btc-eth", "mark-majors"),
            gate_verdict=EdgeGateVerdict.PASS,
            advances=True,
            verdict_reason_codes=(),
        )
    )
    verification = verify_edge_source_packet_evidence(forged)
    assert verification.intact is False
    assert _code("field_mismatch:series") in verification.reason_codes
    assert _code("field_mismatch:gate_verdict") in verification.reason_codes


def test_registry_object_that_differs_from_its_anchor_is_rejected() -> None:
    historical = _registry({"funding_rate": {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY}})
    evidence = _manifest(
        registry=historical, registry_digest=data_requirement_registry_digest(default_perp_data_requirement_registry())
    )
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.integrity_reason_codes == (_code("data_requirement_registry_digest_mismatch"),)


def test_registry_snapshot_swapped_under_a_carried_anchor_fails_verification() -> None:
    payload = json.loads(edge_canonical_json(edge_source_packet_evidence_to_dict(_manifest())))
    payload["data_requirement_registry_binding"]["snapshot"]["requirements"]["funding_rate"]["availability_mode"] = (
        "historical_only"
    )
    verification = verify_edge_source_packet_evidence(edge_source_packet_evidence_from_payload(payload))
    assert verification.intact is False
    assert _code("field_mismatch:status") in verification.reason_codes


# --- construction errors --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("kwargs", "code"),
    [
        ({"root": None, "root_digest": "a" * 64}, "root_intake_malformed"),
        ({"root": {"intake_id": "intake-1"}, "root_digest": "a" * 64}, "root_intake_malformed"),
        ({"root": object.__new__(EdgeIdeaIntakeEvidence), "root_digest": "a" * 64}, "root_intake_not_serializable"),
        ({"root": replace(_intake(), kill_criteria_draft=None)}, "root_intake_not_serializable"),
        ({"root_digest": "A" * 64}, "root_intake_expected_digest_invalid"),
        ({"registry": None, "registry_digest": "a" * 64}, "data_requirement_registry_malformed"),
        (
            {"registry": object.__new__(DataRequirementRegistry), "registry_digest": "a" * 64},
            "data_requirement_registry_not_serializable",
        ),
        (
            {"registry": replace(_registry(), requirements={}), "registry_digest": "a" * 64},
            "data_requirement_registry_not_serializable",
        ),
        (
            {"registry": _registry({"order_book": {"order_book_depth": "50"}}), "registry_digest": "a" * 64},
            "data_requirement_registry_not_serializable",
        ),
        (
            {"registry": replace(_registry(), requirements={"funding_rate": None}), "registry_digest": "a" * 64},
            "data_requirement_registry_not_serializable",
        ),
        ({"registry_digest": None}, "data_requirement_registry_expected_digest_invalid"),
        ({"manifest_id": "manifest scheduler"}, "forbidden_scope_token:manifest_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"series": ()}, "input_series_empty"),
        ({"series": "funding-btc-eth"}, "input_series_malformed"),
        ({"series": ({"series_id": "funding-btc-eth"},)}, "input_series_entry_malformed"),
        ({"series": (_series(), _series())}, "series_id_duplicate"),
        ({"series": (_series(series_id="Funding"),)}, "series_id_invalid"),
        ({"series": (_series(data_requirement_key="open_interest"),)}, "series_data_requirement_key_invalid"),
        ({"series": (_series(rights_status="licensed"),)}, "series_rights_status_invalid"),
        ({"series": (_series(finality="final"),)}, "series_finality_invalid"),
        ({"series": (_series(revision_policy=None),)}, "series_revision_policy_invalid"),
        ({"series": (_series(source_reference="live feed capture"),)}, "forbidden_scope_token:series_source_reference"),
        ({"series": (_series(rights_reference=""),)}, "series_rights_reference_invalid"),
        ({"series": (_series(instrument_coverage=()),)}, "series_instrument_coverage_empty"),
        ({"series": (_series(instrument_coverage="BTC-PERPETUAL"),)}, "series_instrument_coverage_malformed"),
        ({"series": (_series(instrument_coverage=("BTC PERPETUAL",)),)}, "series_instrument_invalid"),
        ({"series": (_series(instrument_coverage=("BTC-PERPETUAL", "BTC-PERPETUAL")),)}, "series_instrument_duplicate"),
        ({"series": (_series(instrument_coverage=("BIST30-FUT",)),)}, "bist_scope_leakage:series_instrument"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(kwargs: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeSourcePacketEvidenceError, match=f"^{_code(code)}$"):
        _manifest(**kwargs)


# --- RC1: builder domain equals verifier reassembly domain ----------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        {"root_intake_binding": EdgeAuthorityBinding(snapshot_json="", expected_digest="")},
        {"root_intake_binding": EdgeAuthorityBinding(snapshot_json='{"a":1}', expected_digest="a" * 64)},
        {"root_intake_binding": None},
        {"data_requirement_registry_binding": EdgeAuthorityBinding(snapshot_json="{}", expected_digest="a" * 64)},
        {"data_requirement_registry_binding": None},
    ],
)
def test_partial_binding_states_never_verify(replacement: dict[str, object]) -> None:
    verification = verify_edge_source_packet_evidence(replace(_manifest(), **replacement))
    assert verification.intact is False
    assert len(verification.reason_codes) == 1


def _mutated_payload(path: tuple[object, ...], value: object) -> dict:
    payload = json.loads(edge_canonical_json(edge_source_packet_evidence_to_dict(_manifest())))
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
        (("root_intake_binding", "snapshot"), {}),
        (("root_intake_binding", "snapshot", "source_packet_binding"), None),
        (("root_intake_binding", "snapshot", "status"), "ACCEPTED"),
        (("data_requirement_registry_binding", "snapshot", "requirements"), {}),
        (("data_requirement_registry_binding", "snapshot", "requirements", "order_book", "order_book_depth"), "50"),
        (("data_requirement_registry_binding", "snapshot", "requirements", "funding_rate", "key"), None),
        (("data_requirement_registry_binding", "snapshot", "requirements", "funding_rate", "extra"), "x"),
        (("series", 0, "order_book_depth"), True),
        (("series", 0, "feature_input_eligible"), _UNSET),
        (("series",), {}),
        (("gate_verdict",), "MAYBE"),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    assert edge_source_packet_evidence_payload_is_well_formed(_mutated_payload(path, value)) is False


# --- RC2: public verifier totality ----------------------------------------------------------------------------------


def _corrupted(**changes: object) -> EdgeSourcePacketEvidence:
    copy = replace(_manifest())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    1,
    "manifest",
    object(),
    {},
    edge_source_packet_evidence_to_dict(_manifest()),
    _intake(),
    object.__new__(EdgeSourcePacketEvidence),
    _corrupted(series=None),
    _corrupted(series=(object.__new__(EdgeSourceSeriesRecord),)),
    _corrupted(series=({"series_id": "funding-btc-eth"},)),
    _corrupted(root_intake_binding=EdgeAuthorityBinding(snapshot_json="[", expected_digest="a" * 64)),
    _corrupted(data_requirement_registry_binding="registry"),
    _corrupted(instrument_coverage="BTC-PERPETUAL"),
    _corrupted(manifest_id="manifest scheduler"),
    _corrupted(source_packet_evidence_digest=7),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_edge_source_packet_evidence(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


# --- RC3: builder/verifier round trips for every state --------------------------------------------------------------

_STATE_BUILDERS = {
    "pass": lambda: _manifest(),
    "fail": lambda: _manifest(series=(_series("mark-majors"), _series(rights_status="restricted"))),
    "needs_external_facts": lambda: _manifest(series=(_series("mark-majors"), _series(finality="unknown"))),
    "rejected_root": lambda: _manifest(correlation_id="corr-2"),
    "rejected_registry": lambda: _manifest(registry_digest="f" * 64),
    "rejected_root_receipt": lambda: _manifest(root=_intake(expected_source_packet_digest="e" * 64)),
}


@pytest.mark.parametrize("state", sorted(_STATE_BUILDERS))
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    evidence = _STATE_BUILDERS[state]()
    _assert_receipt_invariants(evidence)
    expected = EdgeEvidenceStatus.REJECTED if state.startswith("rejected") else EdgeEvidenceStatus.READY
    assert evidence.status is expected


# --- RC4: binding canonicality --------------------------------------------------------------------------------------


def test_bindings_are_canonical_and_noncanonical_in_memory_bindings_never_verify() -> None:
    evidence = _manifest()
    for binding in (evidence.root_intake_binding, evidence.data_requirement_registry_binding):
        assert binding.snapshot_json == edge_canonical_json(json.loads(binding.snapshot_json))
    pretty = replace(
        evidence.data_requirement_registry_binding,
        snapshot_json=json.dumps(json.loads(evidence.data_requirement_registry_binding.snapshot_json), indent=1),
    )
    verification = verify_edge_source_packet_evidence(replace(evidence, data_requirement_registry_binding=pretty))
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


# --- structural non-claims ------------------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flag_names = {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
    defaults = {field.name: field.default for field in fields(EdgeSourcePacketEvidence) if field.name in flag_names}
    assert defaults == dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
    parameters = set(inspect.signature(build_edge_source_packet_evidence).parameters)
    assert not flag_names & parameters
    assert not set(_REGISTRY_OWNED_FIELDS) & parameters


@pytest.mark.parametrize("flag", ["edge_proven", "performance_data_consumed", "current_venue_facts_consumed"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_edge_source_packet_evidence(_redigest(replace(_manifest(), **{flag: True})))
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
    return ast.parse(Path(packet_module.__file__).read_text(encoding="utf-8"))


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
        "crypto_core.strategy.source_packet",
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    tree = _module_tree()
    constructors = {"EdgeSourcePacketEvidence": 0, "EdgeSourceSeriesRecord": 0}
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        for name in constructors:
            constructors[name] += names.count(name)
    assert constructors == {"EdgeSourcePacketEvidence": 1, "EdgeSourceSeriesRecord": 1}
    assert "EdgeSourcePacketEvidence" in calls_by_function["_assemble_source_packet_evidence"]
    assert "_assemble_source_packet_evidence" in calls_by_function["build_edge_source_packet_evidence"]
    assert "_assemble_source_packet_evidence" in calls_by_function["_reassemble_source_packet_evidence"]
