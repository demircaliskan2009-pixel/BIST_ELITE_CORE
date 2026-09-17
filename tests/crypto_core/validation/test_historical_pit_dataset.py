"""Tests for the deterministic historical PIT dataset authority (DETERMINISTIC_HISTORICAL_SIGNAL_SPINE_V1, contract A).

Also the shared chain fixtures (EF-2 → EF-3 → EF-4, funding records) for the binding and decision-run tests.
"""

from __future__ import annotations

import ast
import inspect
import json
from dataclasses import fields, replace
from pathlib import Path

import pytest

import crypto_core.validation.historical_pit_dataset as dataset_module
from crypto_core.data.requirements import (
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeKillCriterion,
    EdgeKillCriterionComparator,
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_source_packet_evidence import EdgeInputSeries, build_edge_source_packet_evidence
from crypto_core.validation.edge_strategy_spec_admission import build_edge_strategy_spec_admission
from crypto_core.validation.historical_pit_dataset import (
    HISTORICAL_PIT_NON_CLAIM_FLAGS,
    HistoricalPitDataset,
    HistoricalPitDatasetError,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
    build_historical_pit_view,
    historical_pit_dataset_digest,
    historical_pit_dataset_from_payload,
    historical_pit_dataset_payload_is_well_formed,
    historical_pit_dataset_to_dict,
    historical_pit_record_digest,
    is_canonical_pit_decimal,
    select_visible_pit_records,
    verify_historical_pit_dataset,
)

_PREFIX = "historical_pit_dataset"
BTC = "BTC-PERPETUAL"
ETH = "ETH-PERPETUAL"
SERIES = "funding-final"

CRITERIA = (
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
SPEC = {
    "schema_version": "1.0",
    "strategy_id": "passive-funding-carry",
    "strategy_version": "1.0.0",
    "strategy_family": "carry",
    "edge_family": "funding_basis_carry",
    "instrument_universe": [BTC],
    "market_type": "inverse_perp",
    "venue_assumptions": ["perpetual_funding_windows"],
    "timeframe": "8h",
    "bar_definition": "funding_settlement_events",
    "entry_conditions": [
        "short_when_mean_final_funding_above_entry_threshold",
        "long_when_mean_final_funding_below_negative_entry_threshold",
    ],
    "exit_conditions": [
        "exit_on_mean_final_funding_sign_flip",
        "exit_when_abs_mean_final_funding_below_exit_threshold",
    ],
    "invalidation_conditions": ["no_action_without_n_final_funding_settlements"],
    "risk_caps": {"max_leverage": 1},
    "data_requirements": {"funding_rate": "8h"},
    "feature_requirements": {"final_funding_mean": "last_n_final_settlements"},
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
RATES = (
    "0.000200000000000000",
    "0.000300000000000000",
    "0.000100000000000000",
    "-0.000100000000000000",
    "-0.000300000000000000",
    "-0.000200000000000000",
)


def predicted_registry() -> DataRequirementRegistry:
    registry = default_perp_data_requirement_registry()
    funding = registry.requirements[DataRequirementKey.FUNDING_RATE]
    requirements = dict(registry.requirements)
    requirements[DataRequirementKey.FUNDING_RATE] = replace(funding, funding_semantics="predicted")
    return DataRequirementRegistry(schema_version=registry.schema_version, requirements=requirements)


def chain(
    *,
    intake_id: str = "intake-1",
    spec_changes: dict[str, object] | None = None,
    revision_policy: str = "immutable_after_finalization",
    registry: DataRequirementRegistry | None = None,
    correlation_id: str = "corr-1",
    finality: str = "finalized_only",
):
    """Accepted EF-2 → EF-3 → EF-4 chain; returns ``(intake, manifest, admission, registry)``."""

    packet = build_source_packet(
        packet_id="pkt-1",
        source_type="academic_paper",
        source_reference="doi:10.0/carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Funding pays passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    policy = build_edge_kill_criteria_policy(
        policy_id="kp-1",
        correlation_id=correlation_id,
        kill_criteria=CRITERIA,
        thresholds_approved=True,
        approval_reference="gov-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id=intake_id,
        correlation_id=correlation_id,
        candidate_strategy_id="passive-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Funding pays carry.",
        data_requirement_keys=("funding_rate",),
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=CRITERIA,
        kill_criteria_policy=policy,
        expected_kill_criteria_policy_digest=policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry() if registry is None else registry
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id=correlation_id,
        input_series=(
            EdgeInputSeries(
                SERIES,
                "funding_rate",
                "archive:funding",
                "own_research",
                "note-1",
                finality,
                revision_policy,
                (BTC, ETH),
            ),
        ),
    )
    spec = validate_strategy_spec({**SPEC, **(spec_changes or {})}).spec
    admission = build_edge_strategy_spec_admission(
        manifest,
        expected_predecessor_digest=manifest.source_packet_evidence_digest,
        expected_root_intake_digest=intake.intake_digest,
        strategy_spec=spec,
        expected_strategy_spec_digest=strategy_spec_digest(spec),
        admission_id="admission-1",
        correlation_id=correlation_id,
        admitted_kill_criteria=CRITERIA,
        kill_criteria_policy=policy,
        expected_kill_criteria_policy_digest=policy.policy_digest,
    )
    return intake, manifest, admission, registry


def funding(
    sequence_id: int,
    event_time_ns: int,
    rate: str,
    *,
    available_at_ns: int | None = None,
    finalized_at_ns: int | None | str = "default",
    instrument: str = BTC,
    vintage: str | None = None,
    series_id: str = SERIES,
    key: str = "funding_rate",
) -> HistoricalPitRecord:
    return build_historical_pit_record(
        series_id=series_id,
        data_requirement_key=key,
        instrument=instrument,
        sequence_id=sequence_id,
        event_time_ns=event_time_ns,
        available_at_ns=event_time_ns + 10 if available_at_ns is None else available_at_ns,
        finalized_at_ns=event_time_ns + 20 if finalized_at_ns == "default" else finalized_at_ns,  # type: ignore[arg-type]
        revision_vintage_id=vintage,
        values=(HistoricalPitValue("funding_rate", rate),),
    )


def records(rates: tuple[str, ...] = RATES, *, instrument: str = BTC) -> tuple[HistoricalPitRecord, ...]:
    return tuple(funding(index, 1_000 * (index + 1), rate, instrument=instrument) for index, rate in enumerate(rates))


def pit_dataset(manifest, registry, pit_records=None, **overrides) -> HistoricalPitDataset:
    arguments: dict[str, object] = {
        "expected_source_manifest_digest": manifest.source_packet_evidence_digest,
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry),
        "dataset_id": "dataset-1",
        "correlation_id": manifest.correlation_id,
        "source_reference": "archive:funding-history",
        "rights_status": "own_research",
        "rights_reference": "research-license-1",
        "records": records() if pit_records is None else pit_records,
    }
    arguments.update(overrides)
    return build_historical_pit_dataset(manifest, **arguments)  # type: ignore[arg-type]


def _base():
    _, manifest, _, registry = chain()
    return manifest, registry


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(dataset: HistoricalPitDataset, **changes: object) -> HistoricalPitDataset:
    changed = replace(dataset, **changes)
    return replace(changed, dataset_digest=historical_pit_dataset_digest(changed))


def _assert_receipt_invariants(dataset: HistoricalPitDataset) -> None:
    verification = verify_historical_pit_dataset(dataset)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == dataset.dataset_digest
    assert historical_pit_dataset_from_payload(json.loads(verification.canonical_json)) == dataset
    assert historical_pit_dataset_payload_is_well_formed(historical_pit_dataset_to_dict(dataset)) is True
    assert dataset.advances is (
        dataset.status is EdgeEvidenceStatus.READY and dataset.gate_verdict is EdgeGateVerdict.PASS
    )
    if dataset.status is EdgeEvidenceStatus.REJECTED:
        assert dataset.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert dataset.integrity_reason_codes
        assert dataset.verdict_reason_codes == ()
    else:
        assert dataset.integrity_reason_codes == ()


# --- happy path ---------------------------------------------------------------------------------------------------------


def test_pass_dataset_binds_authenticated_ef3_semantics_and_re_proves() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    _assert_receipt_invariants(dataset)
    assert (dataset.status, dataset.gate_verdict, dataset.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert dataset.source_manifest_digest == manifest.source_packet_evidence_digest
    assert dataset.data_requirement_registry_digest == data_requirement_registry_digest(registry)
    assert dataset.record_digests == tuple(record.record_digest for record in dataset.records)
    assert (dataset.series_ids, dataset.instruments) == ((SERIES,), (BTC,))
    assert (dataset.coverage_first_event_time_ns, dataset.coverage_last_event_time_ns) == (1_000, 6_000)
    (semantics,) = dataset.series_semantics
    assert semantics.final_required is True
    assert semantics.funding_semantics == "final"
    assert semantics.instrument_coverage == (BTC, ETH)


def test_record_digest_is_computed_and_covers_every_field() -> None:
    record = funding(0, 1_000, RATES[0])
    assert record.record_digest == historical_pit_record_digest(replace(record, record_digest=""))
    for change in (
        {"instrument": ETH},
        {"sequence_id": 1},
        {"available_at_ns": 1_011},
        {"finalized_at_ns": None},
        {"values": (HistoricalPitValue("funding_rate", RATES[1]),)},
    ):
        assert historical_pit_record_digest(replace(record, **change, record_digest="")) != record.record_digest


def test_dataset_is_deterministic_and_order_insensitive() -> None:
    manifest, registry = _base()
    first = pit_dataset(manifest, registry)
    second = pit_dataset(manifest, registry, pit_records=tuple(reversed(records())))
    assert historical_pit_dataset_to_dict(first) == historical_pit_dataset_to_dict(second)
    assert json.dumps(historical_pit_dataset_to_dict(first), sort_keys=True) == json.dumps(
        historical_pit_dataset_to_dict(second), sort_keys=True
    )


# --- PIT view semantics -------------------------------------------------------------------------------------------------


def test_view_requires_available_and_finalized_at_or_before_decision_time() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    view = build_historical_pit_view(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=3_020)
    assert [record.sequence_id for record in view.records] == [0, 1, 2]
    assert view.final_required is True
    assert view.dataset_digest == dataset.dataset_digest
    # sequence 2: available 3_010, finalized 3_020 — one nanosecond earlier it is not final yet
    before = select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=3_019)
    assert [record.sequence_id for record in before.records] == [0, 1]


def test_available_after_decision_time_is_invisible_even_when_finalized_earlier() -> None:
    manifest, registry = _base()
    late = funding(1, 2_000, RATES[1], available_at_ns=5_000, finalized_at_ns=2_020)
    dataset = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), late))
    assert [
        r.sequence_id
        for r in select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=4_999).records
    ] == [0]
    assert [
        r.sequence_id
        for r in select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=5_000).records
    ] == [0, 1]


def test_finalized_after_decision_time_is_invisible_for_a_final_required_series() -> None:
    manifest, registry = _base()
    pending = funding(1, 2_000, RATES[1], available_at_ns=2_010, finalized_at_ns=9_000)
    dataset = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), pending))
    view = select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=8_999)
    assert [record.sequence_id for record in view.records] == [0]


def test_unfinalized_observation_never_becomes_final_by_caller_label() -> None:
    manifest, registry = _base()
    unfinalized = funding(1, 2_000, RATES[1], finalized_at_ns=None)
    dataset = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), unfinalized))
    assert dataset.advances is True
    view = select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=10**12)
    assert [record.sequence_id for record in view.records] == [0]


def test_predicted_funding_semantics_is_never_treated_as_final() -> None:
    registry = predicted_registry()
    _, manifest, _, _ = chain(registry=registry)
    dataset = pit_dataset(manifest, registry)
    _assert_receipt_invariants(dataset)
    (semantics,) = dataset.series_semantics
    assert semantics.final_required is False
    assert semantics.funding_semantics == "predicted"
    assert dataset.gate_verdict is EdgeGateVerdict.FAIL
    assert dataset.advances is False
    assert _code("source_manifest_not_advanced:FAIL") in dataset.verdict_reason_codes
    with pytest.raises(HistoricalPitDatasetError, match="view_dataset_not_verified_advancing"):
        build_historical_pit_view(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=10_000)


def test_view_is_foreign_instrument_and_unknown_series_safe() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    assert select_visible_pit_records(dataset, series_id=SERIES, instrument=ETH, decision_time_ns=10**9).records == ()
    with pytest.raises(HistoricalPitDatasetError, match="view_series_unknown"):
        select_visible_pit_records(dataset, series_id="funding-other", instrument=BTC, decision_time_ns=10**9)
    for bad_time in (0, -1, True, "10"):
        with pytest.raises(HistoricalPitDatasetError, match="view_decision_time_ns_invalid"):
            select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=bad_time)  # type: ignore[arg-type]


def test_view_builder_refuses_a_tampered_dataset() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    tampered = _reseal(
        dataset,
        records=(replace(dataset.records[0], values=(HistoricalPitValue("funding_rate", RATES[5]),)),)
        + dataset.records[1:],
    )
    with pytest.raises(HistoricalPitDatasetError, match="view_dataset_not_verified_advancing"):
        build_historical_pit_view(tampered, series_id=SERIES, instrument=BTC, decision_time_ns=10_000)


# --- revision vintages --------------------------------------------------------------------------------------------------


def test_point_in_time_vintages_show_only_the_latest_vintage_available() -> None:
    _, manifest, _, registry = chain(revision_policy="revised_with_point_in_time_vintages")
    first = funding(0, 1_000, RATES[0], vintage="v1")
    revised = funding(0, 1_000, RATES[1], available_at_ns=4_000, finalized_at_ns=4_000, vintage="v2")
    dataset = pit_dataset(manifest, registry, pit_records=(first, revised))
    _assert_receipt_invariants(dataset)
    assert dataset.advances is True
    early = select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=3_999)
    late = select_visible_pit_records(dataset, series_id=SERIES, instrument=BTC, decision_time_ns=4_000)
    assert [record.values[0].value for record in early.records] == [RATES[0]]
    assert [record.values[0].value for record in late.records] == [RATES[1]]


def test_revision_without_vintage_authority_is_rejected() -> None:
    manifest, registry = _base()
    vintage_on_immutable = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0], vintage="v1"),))
    assert vintage_on_immutable.status is EdgeEvidenceStatus.REJECTED
    assert _code(f"record_revision_unsupported:{SERIES}:{BTC}:0") in vintage_on_immutable.integrity_reason_codes
    silent_revision = pit_dataset(
        manifest,
        registry,
        pit_records=(funding(0, 1_000, RATES[0]), funding(0, 1_000, RATES[1], available_at_ns=4_000)),
    )
    assert _code(f"record_identity_duplicate:{SERIES}:{BTC}:0") in silent_revision.integrity_reason_codes
    _, vintage_manifest, _, vintage_registry = chain(revision_policy="revised_with_point_in_time_vintages")
    unlabelled = pit_dataset(
        vintage_manifest,
        vintage_registry,
        pit_records=(funding(0, 1_000, RATES[0], vintage="v1"), funding(0, 1_000, RATES[1], available_at_ns=4_000)),
    )
    assert _code(f"record_identity_duplicate:{SERIES}:{BTC}:0") in unlabelled.integrity_reason_codes


# --- attack matrix ------------------------------------------------------------------------------------------------------


def test_attack_transplant_dataset_onto_another_ef3_manifest() -> None:
    manifest_a, registry = _base()
    _, manifest_b, _, _ = chain(intake_id="intake-2")
    dataset_a = pit_dataset(manifest_a, registry)
    dataset_b = pit_dataset(manifest_b, registry)
    assert dataset_a.dataset_digest != dataset_b.dataset_digest
    anchored_wrong = pit_dataset(
        manifest_a, registry, expected_source_manifest_digest=manifest_b.source_packet_evidence_digest
    )
    assert anchored_wrong.status is EdgeEvidenceStatus.REJECTED
    assert anchored_wrong.integrity_reason_codes == (_code("source_manifest_digest_mismatch"),)
    transplanted = _reseal(dataset_a, source_manifest_binding=dataset_b.source_manifest_binding)
    verification = verify_historical_pit_dataset(transplanted)
    assert verification.intact is False
    assert _code("field_mismatch:source_manifest_digest") in verification.reason_codes


def test_attack_instrument_change_with_resealed_record_digest() -> None:
    manifest, registry = _base()
    foreign = replace(records()[0], instrument="SOL-PERPETUAL")
    resealed = replace(foreign, record_digest=historical_pit_record_digest(replace(foreign, record_digest="")))
    dataset = pit_dataset(manifest, registry, pit_records=(resealed,) + records()[1:])
    assert dataset.status is EdgeEvidenceStatus.REJECTED
    assert _code("record_instrument_foreign:funding-final:SOL-PERPETUAL:0") in dataset.integrity_reason_codes
    original = pit_dataset(manifest, registry)
    unresealed = _reseal(original, records=(replace(original.records[0], instrument=ETH),) + original.records[1:])
    assert _code("field_mismatch:integrity_reason_codes") in verify_historical_pit_dataset(unresealed).reason_codes


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"series_id": "funding-other"}, "record_series_unknown:funding-other"),
        ({"key": "mark_price"}, f"record_data_requirement_key_mismatch:{SERIES}:{BTC}:0"),
    ],
)
def test_attack_series_or_data_requirement_key_change(change: dict[str, object], code: str) -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0], **change),) + records()[1:])  # type: ignore[arg-type]
    assert dataset.status is EdgeEvidenceStatus.REJECTED
    assert _code(code) in dataset.integrity_reason_codes


def test_attack_ordering_tamper() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    reordered = _reseal(dataset, records=tuple(reversed(dataset.records)))
    assert _code("field_mismatch:records") in verify_historical_pit_dataset(reordered).reason_codes
    backwards = pit_dataset(manifest, registry, pit_records=(funding(0, 2_000, RATES[0]), funding(1, 1_000, RATES[1])))
    assert _code(f"sequence_non_monotonic:{SERIES}:{BTC}") in backwards.integrity_reason_codes


def test_attack_available_or_finalized_before_event_time() -> None:
    manifest, registry = _base()
    early = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0], available_at_ns=999),))
    finalized_early = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0], finalized_at_ns=999),))
    for dataset in (early, finalized_early):
        assert _code(f"record_time_order_invalid:{SERIES}:{BTC}:0") in dataset.integrity_reason_codes


def test_attack_foreign_or_non_ready_ef3_authority() -> None:
    manifest, registry = _base()
    other = pit_dataset(manifest, registry, correlation_id="corr-2")
    assert other.integrity_reason_codes == (_code("source_manifest_correlation_mismatch"),)
    tampered_manifest = replace(manifest, manifest_id="manifest-forged")
    forged = pit_dataset(tampered_manifest, registry)
    assert forged.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("source_manifest_integrity_failure:")) for code in forged.integrity_reason_codes)


def test_attack_foreign_data_requirement_registry() -> None:
    manifest, registry = _base()
    foreign = pit_dataset(manifest, registry, expected_data_requirement_registry_digest="f" * 64)
    assert foreign.integrity_reason_codes == (_code("data_requirement_registry_mismatch"),)
    predicted = predicted_registry()
    assert (
        pit_dataset(
            manifest, registry, expected_data_requirement_registry_digest=data_requirement_registry_digest(predicted)
        ).status
        is EdgeEvidenceStatus.REJECTED
    )


def test_attack_duplicate_sequence_and_duplicate_logical_record() -> None:
    manifest, registry = _base()
    same_sequence = pit_dataset(
        manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), funding(0, 1_000, RATES[1]))
    )
    assert _code(f"record_identity_duplicate:{SERIES}:{BTC}:0") in same_sequence.integrity_reason_codes
    same_logical = pit_dataset(
        manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), funding(1, 1_000, RATES[0]))
    )
    assert _code(f"record_logical_duplicate:{SERIES}:{BTC}") in same_logical.integrity_reason_codes
    gap = pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0]), funding(2, 3_000, RATES[2])))
    assert _code(f"sequence_gap:{SERIES}:{BTC}") in gap.integrity_reason_codes
    with pytest.raises(HistoricalPitDatasetError, match="record_value_name_duplicate"):
        build_historical_pit_record(
            series_id=SERIES,
            data_requirement_key="funding_rate",
            instrument=BTC,
            sequence_id=0,
            event_time_ns=1_000,
            available_at_ns=1_010,
            finalized_at_ns=1_020,
            revision_vintage_id=None,
            values=(HistoricalPitValue("funding_rate", RATES[0]), HistoricalPitValue("funding_rate", RATES[1])),
        )


@pytest.mark.parametrize(
    "value",
    [
        "０.000200000000000000",
        "0.٠٠٠200000000000000",
        "2e-4",
        "+0.000200000000000000",
        "-0.000000000000000000",
        "0.0002",
        "00.000200000000000000",
        " 0.000200000000000000",
        "NaN",
        "Infinity",
        "-inf",
        True,
        0.0002,
        2,
        None,
        b"0.000200000000000000",
    ],
)
def test_attack_noncanonical_numeric_aliases_are_construction_errors(value: object) -> None:
    assert is_canonical_pit_decimal(value) is False
    with pytest.raises(HistoricalPitDatasetError, match="record_value_noncanonical"):
        funding(0, 1_000, value)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("field_name", "value"),
    [
        ("event_time_ns", True),
        ("event_time_ns", 1_000.0),
        ("event_time_ns", 0),
        ("available_at_ns", False),
        ("available_at_ns", "1010"),
        ("finalized_at_ns", True),
        ("sequence_id", True),
        ("sequence_id", -1),
    ],
)
def test_attack_malformed_timestamps_and_bool_as_int(field_name: str, value: object) -> None:
    arguments: dict[str, object] = {
        "series_id": SERIES,
        "data_requirement_key": "funding_rate",
        "instrument": BTC,
        "sequence_id": 0,
        "event_time_ns": 1_000,
        "available_at_ns": 1_010,
        "finalized_at_ns": 1_020,
        "revision_vintage_id": None,
        "values": (HistoricalPitValue("funding_rate", RATES[0]),),
    }
    arguments[field_name] = value
    with pytest.raises(HistoricalPitDatasetError, match=f"record_{field_name}_invalid"):
        build_historical_pit_record(**arguments)  # type: ignore[arg-type]


def test_attack_value_tamper_with_locally_recomputed_digests_changes_the_anchor() -> None:
    manifest, registry = _base()
    dataset = pit_dataset(manifest, registry)
    tampered_record = replace(dataset.records[0], values=(HistoricalPitValue("funding_rate", RATES[5]),))
    carried_old_digest = _reseal(dataset, records=(tampered_record,) + dataset.records[1:])
    verification = verify_historical_pit_dataset(carried_old_digest)
    assert verification.intact is False
    assert _code("field_mismatch:integrity_reason_codes") in verification.reason_codes
    redigested = replace(
        tampered_record, record_digest=historical_pit_record_digest(replace(tampered_record, record_digest=""))
    )
    rebuilt = pit_dataset(manifest, registry, pit_records=(redigested,) + dataset.records[1:])
    assert verify_historical_pit_dataset(rebuilt).intact is True
    assert rebuilt.dataset_digest != dataset.dataset_digest  # a downstream anchor on the original digest refuses it
    fully_resealed = _reseal(dataset, records=(redigested,) + dataset.records[1:])
    assert verify_historical_pit_dataset(fully_resealed).intact is False


# --- verdicts -----------------------------------------------------------------------------------------------------------


def test_restricted_rights_fail_and_non_advancing_manifest_propagates() -> None:
    manifest, registry = _base()
    restricted = pit_dataset(manifest, registry, rights_status="restricted")
    _assert_receipt_invariants(restricted)
    assert restricted.gate_verdict is EdgeGateVerdict.FAIL
    assert restricted.verdict_reason_codes == (_code("dataset_rights_restricted"),)
    _, unknown_manifest, _, unknown_registry = chain(revision_policy="unknown")
    needs = pit_dataset(unknown_manifest, unknown_registry)
    _assert_receipt_invariants(needs)
    assert needs.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert needs.verdict_reason_codes == (_code("source_manifest_not_advanced:NEEDS_EXTERNAL_FACTS"),)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"records": ()}, "records_empty"),
        ({"records": None}, "records_malformed"),
        ({"records": ({"series_id": SERIES},)}, "record_malformed"),
        ({"rights_status": "public"}, "rights_status_invalid"),
        ({"dataset_id": ""}, "dataset_id_invalid"),
        ({"dataset_id": "dataset scheduler"}, "dataset_id"),
        ({"expected_data_requirement_registry_digest": "F" * 64}, "expected_data_requirement_registry_digest_invalid"),
        ({"expected_source_manifest_digest": "x"}, "source_manifest_expected_digest_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    manifest, registry = _base()
    with pytest.raises(HistoricalPitDatasetError, match=code):
        pit_dataset(manifest, registry, **overrides)


def test_carried_record_digest_must_be_hex64() -> None:
    manifest, registry = _base()
    with pytest.raises(HistoricalPitDatasetError, match="record_digest_invalid"):
        pit_dataset(manifest, registry, pit_records=(replace(records()[0], record_digest="z"),))
    for foreign in (object(), historical_pit_dataset_to_dict(pit_dataset(manifest, registry)), None):
        with pytest.raises(HistoricalPitDatasetError, match="source_manifest_malformed"):
            build_historical_pit_dataset(
                foreign,  # type: ignore[arg-type]
                expected_source_manifest_digest=manifest.source_packet_evidence_digest,
                expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
                dataset_id="dataset-1",
                correlation_id="corr-1",
                source_reference="archive:funding-history",
                rights_status="own_research",
                rights_reference="research-license-1",
                records=records(),
            )


# --- totality and parity ------------------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> HistoricalPitDataset:
    manifest, registry = _base()
    copy = replace(pit_dataset(manifest, registry))
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    7,
    "dataset",
    b"dataset",
    {},
    object(),
    object.__new__(HistoricalPitDataset),
    _corrupted(records=None),
    _corrupted(records=({"series_id": SERIES},)),
    _corrupted(series_semantics="final"),
    _corrupted(source_manifest_binding=None),
    _corrupted(status="ACCEPTED"),
    _corrupted(coverage_first_event_time_ns=True),
    _corrupted(dataset_id="dataset scheduler"),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_historical_pit_dataset(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


def test_foreign_dataclass_and_payload_are_not_datasets() -> None:
    manifest, registry = _base()
    assert verify_historical_pit_dataset(manifest).intact is False
    assert (
        verify_historical_pit_dataset(historical_pit_dataset_to_dict(pit_dataset(manifest, registry))).intact is False
    )


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "ACCEPTED"),
        (("advances",), 1),
        (("records",), {}),
        (("records", 0, "sequence_id"), True),
        (("records", 0, "values", 0, "value"), 0.0002),
        (("source_manifest_binding",), None),
        (("source_manifest_binding", "snapshot"), {}),
        (("coverage_first_event_time_ns",), "1000"),
        (("series_semantics", 0, "final_required"), "true"),
        (("external_archive_truth_proven",), None),
    ],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    manifest, registry = _base()
    payload = historical_pit_dataset_to_dict(pit_dataset(manifest, registry))
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert historical_pit_dataset_payload_is_well_formed(payload) is False
    extra = historical_pit_dataset_to_dict(pit_dataset(manifest, registry))
    extra["unexpected"] = 1
    assert historical_pit_dataset_payload_is_well_formed(extra) is False


def test_every_builder_state_round_trips_through_the_verifier() -> None:
    manifest, registry = _base()
    for dataset in (
        pit_dataset(manifest, registry),
        pit_dataset(manifest, registry, rights_status="restricted"),
        pit_dataset(manifest, registry, correlation_id="corr-2"),
        pit_dataset(manifest, registry, pit_records=(funding(0, 1_000, RATES[0], instrument="SOL-PERPETUAL"),)),
    ):
        _assert_receipt_invariants(dataset)


# --- structural non-claims and purity -----------------------------------------------------------------------------------


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(HISTORICAL_PIT_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    defaults = {field.name: field.default for field in fields(HistoricalPitDataset) if field.name in flags}
    assert defaults == flags
    assert flags["external_archive_truth_proven"] is False
    assert not set(flags) & set(inspect.signature(build_historical_pit_dataset).parameters)


@pytest.mark.parametrize("flag", ["external_archive_truth_proven", "edge_proven", "pnl_computed", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    manifest, registry = _base()
    verification = verify_historical_pit_dataset(_reseal(pit_dataset(manifest, registry), **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


FORBIDDEN_MODULES = (
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
    "concurrent",
    "sched",
    "subprocess",
    "os",
    "sys",
    "io",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
    "importlib",
    "pkgutil",
    "pickle",
)
FORBIDDEN_CALLS = frozenset(
    {
        "open",
        "Path",
        "float",
        "now",
        "utcnow",
        "time",
        "time_ns",
        "perf_counter",
        "monotonic",
        "getenv",
        "print",
        "import_module",
        "entry_points",
    }
)
FORBIDDEN_BUILTINS = frozenset({"eval", "exec", "compile", "__import__", "globals", "locals", "setattr"})
FORBIDDEN_IDENTIFIERS = (
    "bist",
    "borsa",
    "paperorderintent",
    "fill_price",
    "realized_pnl",
    "place_order",
    "submit_order",
)


def assert_module_is_pure(module: object, allowed_crypto_modules: set[str]) -> None:
    source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
    crypto_imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in FORBIDDEN_MODULES)
                assert not alias.name.startswith("crypto_core")
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in FORBIDDEN_MODULES)
            if node.module.startswith("crypto_core"):
                crypto_imports.add(node.module)
                assert not {alias.name for alias in node.names if alias.name.startswith("_")}
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in FORBIDDEN_CALLS, name
            assert not (isinstance(node.func, ast.Name) and name in FORBIDDEN_BUILTINS), name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "__globals__", "__code__"}
    assert crypto_imports == allowed_crypto_modules
    lowered = source.lower()
    assert not [token for token in FORBIDDEN_IDENTIFIERS if token in lowered]


def assert_single_assembly_path(module: object, cls_name: str, assemble: str, build: str, reassemble: str) -> None:
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count(cls_name)
    assert constructor_calls == 1
    assert cls_name in calls_by_function[assemble]
    assert assemble in calls_by_function[build]
    assert assemble in calls_by_function[reassemble]


def test_module_is_pure_deterministic_and_consumes_only_public_substrate() -> None:
    assert_module_is_pure(
        dataset_module,
        {
            "crypto_core.data.requirements",
            "crypto_core.strategy.source_packet",
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_source_packet_evidence",
        },
    )


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    assert_single_assembly_path(
        dataset_module,
        "HistoricalPitDataset",
        "_assemble_dataset",
        "build_historical_pit_dataset",
        "_reassemble_dataset",
    )
