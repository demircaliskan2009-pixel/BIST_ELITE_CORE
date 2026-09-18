"""Tests for the deterministic historical decision run (DETERMINISTIC_HISTORICAL_SIGNAL_SPINE_V1, contract D + H1/H2)."""

from __future__ import annotations

import decimal
import inspect
import json
from dataclasses import fields, replace

import pytest

import crypto_core.validation.historical_decision_run as run_module
import crypto_core.validation.strategy_executable_profiles as profiles_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.historical_decision_run import (
    HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS,
    HistoricalDecisionRecord,
    HistoricalDecisionRun,
    HistoricalDecisionRunError,
    build_historical_decision_run,
    historical_decision_run_digest,
    historical_decision_run_from_payload,
    historical_decision_run_payload_is_well_formed,
    historical_decision_run_to_dict,
    verify_historical_decision_run,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitValue,
    build_historical_pit_record,
    historical_pit_record_digest,
)
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    ProfileParameterAssignment,
    evaluate_strategy_executable_profile,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit
from tests.crypto_core.validation import test_strategy_executable_binding as bind
from tests.crypto_core.validation import test_strategy_executable_profiles as prof

_PREFIX = "historical_decision_run"
BTC = pit.BTC
ETH = pit.ETH
PARAMS = prof.params()


def _world(**chain_kwargs: object):
    _, manifest, admission, registry = pit.chain(**chain_kwargs)  # type: ignore[arg-type]
    return manifest, admission, registry


def decision_run(dataset, binding, **overrides) -> HistoricalDecisionRun:
    """Build a run; unless overridden, with the exact parameter approval for the assignment and binding used."""

    if "parameter_approval" not in overrides:
        overrides["parameter_approval"] = bind.parameter_approval_for(
            binding, overrides.get("parameter_assignment", PARAMS)
        )
    arguments: dict[str, object] = {
        "expected_dataset_digest": dataset.dataset_digest,
        "expected_executable_binding_digest": binding.binding_digest,
        "run_id": "run-1",
        "correlation_id": "corr-1",
        "parameter_assignment": PARAMS,
        "instrument": BTC,
        "evaluation_start_ns": 1,
        "evaluation_end_ns": 10**12,
    }
    arguments.update(overrides)
    return build_historical_decision_run(dataset, binding, **arguments)  # type: ignore[arg-type]


def _standard(records=None, **overrides):
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry, records)
    binding = bind.executable_binding(admission)
    return decision_run(dataset, binding, **overrides), dataset, binding


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(run: HistoricalDecisionRun, **changes: object) -> HistoricalDecisionRun:
    changed = replace(run, **changes)
    return replace(changed, run_digest=historical_decision_run_digest(changed))


def _redigest_decision(decision: HistoricalDecisionRecord, **changes: object) -> HistoricalDecisionRecord:
    changed = replace(decision, **changes, decision_digest="")
    payload = {field.name: getattr(changed, field.name) for field in fields(changed)}
    payload = json.loads(json.dumps(payload))
    return replace(changed, decision_digest=edge_payload_digest(payload, "decision_digest"))


def _fully_resealed_trace(run: HistoricalDecisionRun, decisions: tuple[HistoricalDecisionRecord, ...]):
    trace = [json.loads(json.dumps({f.name: getattr(d, f.name) for f in fields(d)})) for d in decisions]
    return _reseal(
        run,
        decisions=decisions,
        decision_count=len(decisions),
        decision_trace_digest=edge_sha256_text(edge_canonical_json(trace)),
    )


def _assert_receipt_invariants(run: HistoricalDecisionRun) -> None:
    verification = verify_historical_decision_run(run)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == run.run_digest
    assert historical_decision_run_from_payload(json.loads(verification.canonical_json)) == run
    assert historical_decision_run_payload_is_well_formed(historical_decision_run_to_dict(run)) is True
    assert run.advances is (run.status is EdgeEvidenceStatus.READY and run.gate_verdict is EdgeGateVerdict.PASS)
    assert run.decision_count == len(run.decisions)
    if not run.advances:
        assert run.decisions == ()
    if run.status is EdgeEvidenceStatus.REJECTED:
        assert run.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert run.integrity_reason_codes
        assert run.verdict_reason_codes == ()
    else:
        assert run.integrity_reason_codes == ()


def _trace(run: HistoricalDecisionRun) -> list[tuple[object, ...]]:
    return [
        (d.decision_time_ns, d.action, d.prior_direction, d.resulting_direction, d.target_units, d.feature_mean)
        for d in run.decisions
    ]


# --- H1/H2 semantics ----------------------------------------------------------------------------------------------------


def test_pass_run_executes_the_bound_profile_over_pit_views() -> None:
    run, dataset, binding = _standard()
    _assert_receipt_invariants(run)
    assert (run.status, run.gate_verdict, run.advances) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.PASS, True)
    profile = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    assert run.dataset_digest == dataset.dataset_digest
    assert run.executable_binding_digest == binding.binding_digest
    assert run.source_manifest_digest == dataset.source_manifest_digest == binding.source_manifest_digest
    assert (run.admission_digest, run.strategy_spec_digest) == (binding.admission_digest, binding.strategy_spec_digest)
    assert (run.profile_id, run.profile_version, run.profile_semantics_digest) == (
        PASSIVE_FUNDING_CARRY_V1,
        "1",
        profile.profile_semantics_digest,
    )
    assert run.parameter_assignment_digest == profile_parameter_assignment_digest(PARAMS)
    assert run.funding_series_id == pit.SERIES
    one = "1.000000000000000000"
    zero = "0.000000000000000000"
    assert _trace(run) == [
        (1_020, "NO_ACTION", "FLAT", "FLAT", None, None),
        (2_020, "SHORT", "FLAT", "SHORT", one, "0.000250000000000000"),
        (3_020, "HOLD", "SHORT", "SHORT", None, "0.000200000000000000"),
        (4_020, "EXIT", "SHORT", "FLAT", zero, zero),
        (5_020, "LONG", "FLAT", "LONG", one, "-0.000200000000000000"),
        (6_020, "HOLD", "LONG", "LONG", None, "-0.000250000000000000"),
    ]
    assert [d.decision_sequence for d in run.decisions] == list(range(6))
    assert [d.reason for d in run.decisions] == [
        "invalidation_insufficient_final_history",
        "entry_short_on_positive_mean",
        "hold_position",
        "exit_below_exit_threshold",
        "entry_long_on_negative_mean",
        "hold_position",
    ]
    digests = dataset.record_digests
    assert run.decisions[0].input_record_digests == (digests[0],)
    assert run.decisions[0].used_observation_count == 1
    for index, decision in enumerate(run.decisions[1:], start=1):
        assert decision.input_record_digests == (digests[index - 1], digests[index])
        assert decision.trigger_record_digests == (digests[index],)
        assert decision.instrument == BTC
        assert decision.profile_id == PASSIVE_FUNDING_CARRY_V1


def test_decision_time_is_exactly_max_available_finalized() -> None:
    later_available = pit.funding(0, 1_000, pit.RATES[0], available_at_ns=1_030, finalized_at_ns=1_020)
    later_finalized = pit.funding(1, 2_000, pit.RATES[1], available_at_ns=2_010, finalized_at_ns=2_040)
    run, _, _ = _standard((later_available, later_finalized))
    assert [d.decision_time_ns for d in run.decisions] == [1_030, 2_040]
    same_instant = (
        pit.funding(0, 1_000, pit.RATES[0], finalized_at_ns=1_500),
        pit.funding(1, 1_200, pit.RATES[1], available_at_ns=1_500, finalized_at_ns=1_400),
    )
    run, dataset, _ = _standard(same_instant)
    (decision,) = run.decisions
    assert decision.decision_time_ns == 1_500
    assert decision.trigger_record_digests == tuple(sorted(dataset.record_digests))
    assert decision.action == "SHORT"


def test_sign_flip_exit_precedes_reentry_at_a_later_instant() -> None:
    rates = ("0.000300000000000000", "0.000300000000000000", "-0.000300000000000000", "-0.000300000000000000")
    run, _, _ = _standard(pit.records(rates), parameter_assignment=prof.params(n="1"))
    assert [(d.action, d.reason) for d in run.decisions] == [
        ("SHORT", "entry_short_on_positive_mean"),
        ("HOLD", "hold_position"),
        ("EXIT", "exit_on_sign_flip"),
        ("LONG", "entry_long_on_negative_mean"),
    ]
    assert [d.resulting_direction for d in run.decisions] == ["SHORT", "SHORT", "FLAT", "LONG"]


def test_insufficient_n_never_invents_a_signal() -> None:
    run, _, _ = _standard(parameter_assignment=prof.params(n="7"))
    assert run.advances is True
    assert {(d.action, d.target_units, d.feature_mean, d.resulting_direction) for d in run.decisions} == {
        ("NO_ACTION", None, None, "FLAT")
    }
    assert [d.used_observation_count for d in run.decisions] == [1, 2, 3, 4, 5, 6]


def test_unfinalized_record_is_excluded_from_schedule_and_inputs() -> None:
    records = pit.records()
    unfinalized = pit.funding(2, 3_000, "0.900000000000000000", finalized_at_ns=None)
    run, dataset, _ = _standard(records[:2] + (unfinalized,) + records[3:])
    assert 3_020 not in [d.decision_time_ns for d in run.decisions]
    assert all(unfinalized.record_digest not in d.input_record_digests for d in run.decisions)
    assert run.decisions[2].decision_time_ns == 4_020
    assert run.decisions[2].input_record_digests == (records[1].record_digest, records[3].record_digest)


def test_predicted_funding_series_is_excluded_and_blocks_the_run() -> None:
    registry = pit.predicted_registry()
    manifest, admission, _ = _world(registry=registry)
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    run = decision_run(dataset, binding)
    _assert_receipt_invariants(run)
    assert (run.status, run.gate_verdict, run.decisions) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL, ())
    assert {
        _code("dataset_not_advanced:FAIL"),
        _code("executable_binding_not_advanced:FAIL"),
        _code("required_final_series_missing"),
    } <= set(run.verdict_reason_codes)


def test_unavailable_record_is_invisible_until_available() -> None:
    records = pit.records()
    late = pit.funding(1, 2_000, pit.RATES[1], available_at_ns=3_500)
    run, _, _ = _standard((records[0], late) + records[2:])
    by_time = {d.decision_time_ns: d for d in run.decisions}
    assert 2_020 not in by_time
    assert late.record_digest not in by_time[3_020].input_record_digests
    assert by_time[3_020].input_record_digests == (records[0].record_digest, records[2].record_digest)
    assert by_time[3_500].input_record_digests == (late.record_digest, records[2].record_digest)
    assert by_time[3_500].trigger_record_digests == (late.record_digest,)


def test_evaluation_bounds_are_half_open() -> None:
    run, _, _ = _standard(evaluation_start_ns=2_020, evaluation_end_ns=5_020)
    assert [d.decision_time_ns for d in run.decisions] == [2_020, 3_020, 4_020]
    assert run.decisions[0].prior_direction == "FLAT"
    empty, _, _ = _standard(evaluation_start_ns=6_021, evaluation_end_ns=7_000)
    assert (empty.advances, empty.decisions, empty.decision_count) == (True, (), 0)


def test_non_advancing_upstream_propagates_without_decisions() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    unapproved = decision_run(dataset, bind.executable_binding(admission, approve=False))
    _assert_receipt_invariants(unapproved)
    assert unapproved.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert unapproved.verdict_reason_codes == (_code("executable_binding_not_advanced:NEEDS_GOVERNANCE_APPROVAL"),)
    restricted = pit.pit_dataset(manifest, registry, rights_status="restricted")
    blocked = decision_run(restricted, bind.executable_binding(admission))
    _assert_receipt_invariants(blocked)
    assert blocked.verdict_reason_codes == (_code("dataset_not_advanced:FAIL"),)


def test_instrument_outside_strategy_universe_fails() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry, pit.records() + pit.records(instrument=ETH))
    run = decision_run(dataset, bind.executable_binding(admission), instrument=ETH)
    _assert_receipt_invariants(run)
    assert run.gate_verdict is EdgeGateVerdict.FAIL
    assert run.verdict_reason_codes == (_code("instrument_outside_strategy_universe"),)


def test_required_value_missing_fails() -> None:
    renamed = tuple(
        build_historical_pit_record(
            series_id=record.series_id,
            data_requirement_key=record.data_requirement_key,
            instrument=record.instrument,
            sequence_id=record.sequence_id,
            event_time_ns=record.event_time_ns,
            available_at_ns=record.available_at_ns,
            finalized_at_ns=record.finalized_at_ns,
            revision_vintage_id=None,
            values=(HistoricalPitValue("predicted_rate", record.values[0].value),),
        )
        for record in pit.records()[:2]
    )
    run, _, _ = _standard(renamed)
    assert run.gate_verdict is EdgeGateVerdict.FAIL
    assert set(run.verdict_reason_codes) == {
        _code(f"required_value_missing:{record.record_digest}") for record in renamed
    }


# --- attack matrix ------------------------------------------------------------------------------------------------------


def test_attack_dataset_transplant_from_another_chain() -> None:
    run, dataset, binding = _standard()
    manifest_b, _, registry_b = _world(intake_id="intake-2")
    dataset_b = pit.pit_dataset(manifest_b, registry_b)
    spliced = decision_run(dataset_b, binding)
    _assert_receipt_invariants(spliced)
    assert spliced.integrity_reason_codes == (_code("dataset_binding_chain_mismatch"),)
    carried = _reseal(run, dataset_binding=spliced.dataset_binding, dataset_digest=dataset_b.dataset_digest)
    verification = verify_historical_decision_run(carried)
    assert verification.intact is False
    assert _code("field_mismatch:status") in verification.reason_codes


def test_attack_binding_transplant_from_another_chain() -> None:
    run, dataset, _ = _standard()
    _, admission_b, _ = _world(intake_id="intake-2")
    binding_b = bind.executable_binding(admission_b)
    spliced = decision_run(dataset, binding_b)
    assert spliced.integrity_reason_codes == (_code("dataset_binding_chain_mismatch"),)
    carried = _reseal(
        run, executable_binding=spliced.executable_binding, executable_binding_digest=binding_b.binding_digest
    )
    assert verify_historical_decision_run(carried).intact is False


def test_attack_spec_transplant() -> None:
    run, dataset, _ = _standard()
    _, changed_admission, _ = _world(spec_changes={"latency_sensitivity": "medium"})
    changed_binding = bind.executable_binding(changed_admission)
    other = decision_run(dataset, changed_binding)
    assert other.advances is True
    assert other.strategy_spec_digest != run.strategy_spec_digest
    assert other.run_digest != run.run_digest
    carried = _reseal(run, strategy_spec_digest=other.strategy_spec_digest)
    assert _code("field_mismatch:strategy_spec_digest") in verify_historical_decision_run(carried).reason_codes
    reused = decision_run(
        dataset, bind.executable_binding(changed_admission, approval=bind.approval_for(bind._admission()))
    )
    assert reused.advances is False
    assert reused.decisions == ()


def test_attack_parameter_transplant() -> None:
    run, _, _ = _standard()
    carried = _reseal(run, parameter_assignment=prof.params(n="3"))
    verification = verify_historical_decision_run(carried)
    assert verification.intact is False
    assert {_code("field_mismatch:decisions"), _code("field_mismatch:parameter_assignment_digest")} <= set(
        verification.reason_codes
    )


def test_attack_window_transplant() -> None:
    run, _, _ = _standard()
    carried = _reseal(run, evaluation_start_ns=3_000)
    assert _code("field_mismatch:decisions") in verify_historical_decision_run(carried).reason_codes


def test_attack_instrument_transplant() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry, pit.records() + pit.records(instrument=ETH))
    run = decision_run(dataset, bind.executable_binding(admission))
    carried = _reseal(run, instrument=ETH)
    verification = verify_historical_decision_run(carried)
    assert verification.intact is False
    assert {_code("field_mismatch:decisions"), _code("field_mismatch:gate_verdict")} <= set(verification.reason_codes)


def test_attack_decision_record_reorder() -> None:
    run, _, _ = _standard()
    reordered = _fully_resealed_trace(run, tuple(reversed(run.decisions)))
    assert _code("field_mismatch:decisions") in verify_historical_decision_run(reordered).reason_codes


@pytest.mark.parametrize(
    "change",
    [
        {"action": "LONG", "resulting_direction": "LONG"},
        {"decision_time_ns": 2_019},
        {"input_record_digests": ("0" * 64, "1" * 64)},
        {"trigger_record_digests": ("2" * 64,)},
        {"feature_mean": "0.000900000000000000"},
        {"target_units": "5.000000000000000000"},
    ],
)
def test_attack_changed_decision_with_fully_resealed_trace_never_verifies(change: dict[str, object]) -> None:
    run, _, _ = _standard()
    forged = _redigest_decision(run.decisions[1], **change)
    carried_old = _reseal(run, decisions=(run.decisions[0], forged) + run.decisions[2:])
    assert verify_historical_decision_run(carried_old).intact is False
    resealed = _fully_resealed_trace(run, (run.decisions[0], forged) + run.decisions[2:])
    verification = verify_historical_decision_run(resealed)
    assert verification.intact is False
    assert {_code("field_mismatch:decisions"), _code("field_mismatch:decision_trace_digest")} <= set(
        verification.reason_codes
    )


def test_attack_copied_trace_from_another_run_never_verifies() -> None:
    run, _, _ = _standard()
    other, _, _ = _standard(parameter_assignment=prof.params(n="1"))
    assert other.decisions != run.decisions
    copied = _fully_resealed_trace(run, other.decisions)
    assert _code("field_mismatch:decisions") in verify_historical_decision_run(copied).reason_codes


def test_attack_tampered_dataset_with_locally_recomputed_digests_is_refused_by_the_anchor() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    tampered = replace(dataset.records[1], values=(HistoricalPitValue("funding_rate", "-0.900000000000000000"),))
    tampered = replace(tampered, record_digest=historical_pit_record_digest(replace(tampered, record_digest="")))
    rebuilt = pit.pit_dataset(manifest, registry, (dataset.records[0], tampered) + dataset.records[2:])
    refused = decision_run(rebuilt, binding, expected_dataset_digest=dataset.dataset_digest)
    _assert_receipt_invariants(refused)
    assert refused.integrity_reason_codes == (_code("dataset_digest_mismatch"),)
    wrong_binding_anchor = decision_run(dataset, binding, expected_executable_binding_digest="a" * 64)
    assert wrong_binding_anchor.integrity_reason_codes == (_code("executable_binding_digest_mismatch"),)
    wrong_correlation = decision_run(dataset, binding, correlation_id="corr-2")
    assert wrong_correlation.integrity_reason_codes == (
        _code("dataset_correlation_mismatch"),
        _code("executable_binding_correlation_mismatch"),
    )


def test_attack_forged_upstream_objects_are_rejected_receipts() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    forged_dataset = replace(dataset, dataset_id="dataset-forged")
    run = decision_run(forged_dataset, binding, expected_dataset_digest=dataset.dataset_digest)
    assert run.status is EdgeEvidenceStatus.REJECTED
    assert all(code.startswith(_code("dataset_integrity_failure:")) for code in run.integrity_reason_codes)
    forged_binding = replace(binding, gate_verdict=EdgeGateVerdict.PASS, approval=None)
    run = decision_run(dataset, forged_binding, expected_executable_binding_digest=binding.binding_digest)
    assert run.status is EdgeEvidenceStatus.REJECTED
    assert all(code.startswith(_code("executable_binding_integrity_failure:")) for code in run.integrity_reason_codes)
    rejected_binding = bind.executable_binding(admission, profile_id="passive_funding_carry.v2")
    run = decision_run(dataset, rejected_binding)
    assert run.integrity_reason_codes == (_code("executable_binding_rejected"),)


def test_run_is_byte_identical_deterministic() -> None:
    first, _, _ = _standard()
    second, _, _ = _standard()
    assert edge_canonical_json(historical_decision_run_to_dict(first)) == edge_canonical_json(
        historical_decision_run_to_dict(second)
    )
    assert verify_historical_decision_run(first).canonical_json == verify_historical_decision_run(second).canonical_json
    shuffled, _, _ = _standard(tuple(reversed(pit.records())), parameter_assignment=tuple(reversed(PARAMS)))
    assert shuffled.run_digest == first.run_digest


# --- malformed input ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"evaluation_start_ns": 5_000, "evaluation_end_ns": 5_000}, "evaluation_bounds_invalid"),
        ({"evaluation_start_ns": 0}, "evaluation_start_ns_invalid"),
        ({"evaluation_start_ns": True}, "evaluation_start_ns_invalid"),
        ({"evaluation_end_ns": 10.0}, "evaluation_end_ns_invalid"),
        ({"instrument": "BTC PERPETUAL"}, "instrument_invalid"),
        ({"instrument": "ＢTC-PERPETUAL"}, "instrument_invalid"),
        ({"instrument": None}, "instrument_invalid"),
        ({"run_id": "run scheduler"}, "run_id"),
        ({"correlation_id": ""}, "correlation_id_invalid"),
        ({"parameter_assignment": PARAMS[:3]}, "parameter_assignment_invalid"),
        ({"parameter_assignment": prof.params(n="0")}, "parameter_assignment_invalid"),
        ({"parameter_assignment": PARAMS + PARAMS[:1]}, "parameter_assignment_duplicate"),
        ({"parameter_assignment": {"unit_size": "1"}}, "parameter_assignment_malformed"),
        ({"parameter_assignment": (("unit_size", "1"),)}, "parameter_assignment_entry_malformed"),
        ({"expected_dataset_digest": "x"}, "dataset_expected_digest_invalid"),
        ({"expected_executable_binding_digest": None}, "executable_binding_expected_digest_invalid"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    with pytest.raises(HistoricalDecisionRunError, match=code):
        _standard(**overrides)


def test_foreign_upstream_objects_are_construction_errors() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)

    def build(candidate_dataset: object, candidate_binding: object) -> None:
        build_historical_decision_run(
            candidate_dataset,  # type: ignore[arg-type]
            candidate_binding,  # type: ignore[arg-type]
            expected_dataset_digest=dataset.dataset_digest,
            expected_executable_binding_digest=binding.binding_digest,
            run_id="run-1",
            correlation_id="corr-1",
            parameter_assignment=PARAMS,
            instrument=BTC,
            evaluation_start_ns=1,
            evaluation_end_ns=10**12,
        )

    for foreign in (manifest, None, historical_decision_run_to_dict(decision_run(dataset, binding))):
        with pytest.raises(HistoricalDecisionRunError, match="dataset_malformed"):
            build(foreign, binding)
    for foreign in (admission, None, dataset):
        with pytest.raises(HistoricalDecisionRunError, match="executable_binding_malformed"):
            build(dataset, foreign)
    with pytest.raises(HistoricalDecisionRunError, match="dataset_not_serializable"):
        build(object.__new__(type(dataset)), binding)
    with pytest.raises(HistoricalDecisionRunError, match="executable_binding_not_serializable"):
        build(dataset, object.__new__(type(binding)))


# --- totality and parity ------------------------------------------------------------------------------------------------


def _corrupted(**changes: object) -> HistoricalDecisionRun:
    copy = replace(_standard()[0])
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


_TOTALITY_OBJECTS: list[object] = [
    None,
    5,
    "run",
    b"run",
    {},
    object(),
    object.__new__(HistoricalDecisionRun),
    _corrupted(decisions=None),
    _corrupted(decisions=({"action": "LONG"},)),
    _corrupted(decisions=(object.__new__(HistoricalDecisionRecord),)),
    _corrupted(parameter_assignment=None),
    _corrupted(parameter_assignment=({"parameter_id": "unit_size"},)),
    _corrupted(dataset_binding=None),
    _corrupted(executable_binding="binding"),
    _corrupted(evaluation_start_ns=True),
    _corrupted(status="ACCEPTED"),
    _corrupted(pnl_computed=True),
    _corrupted(parameter_approval="approved"),
    _corrupted(parameter_approval=None),
    _corrupted(evaluation_end_ns=10**5000),
]


@pytest.mark.parametrize("artifact", _TOTALITY_OBJECTS)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify_historical_decision_run(artifact)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


def test_foreign_dataclasses_and_payloads_are_not_runs() -> None:
    run, dataset, binding = _standard()
    for foreign in (dataset, binding, run.decisions[0], historical_decision_run_to_dict(run)):
        assert verify_historical_decision_run(foreign).intact is False


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("status",), "ACCEPTED"),
        (("decisions",), {}),
        (("decisions", 0, "decision_time_ns"), "1020"),
        (("decisions", 0, "input_record_digests"), "a" * 64),
        (("decisions", 0, "feature_mean"), 0.0),
        (("parameter_assignment", 0, "value"), 1),
        (("dataset_binding",), None),
        (("executable_binding", "snapshot"), {}),
        (("evaluation_end_ns",), True),
        (("orders_created",), 0),
    ],
)
def test_parser_refuses_states_the_builder_cannot_produce(path: tuple[object, ...], value: object) -> None:
    payload = historical_decision_run_to_dict(_standard()[0])
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert historical_decision_run_payload_is_well_formed(payload) is False


def test_every_builder_state_round_trips_through_the_verifier() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    _, admission_b, _ = _world(intake_id="intake-2")
    for run in (
        decision_run(dataset, binding),
        decision_run(dataset, bind.executable_binding(admission, approve=False)),
        decision_run(dataset, binding, instrument=ETH),
        decision_run(dataset, bind.executable_binding(admission_b)),
        decision_run(dataset, binding, correlation_id="corr-2"),
        decision_run(dataset, binding, evaluation_start_ns=10**11),
        decision_run(dataset, binding, parameter_approval=None),
        decision_run(dataset, binding, parameter_assignment=prof.params(n="3"), parameter_approval=None),
    ):
        _assert_receipt_invariants(run)


# --- non-claims and purity ----------------------------------------------------------------------------------------------


def test_decision_records_carry_no_order_fill_price_or_pnl_fields() -> None:
    assert [field.name for field in fields(HistoricalDecisionRecord)] == [
        "decision_sequence",
        "decision_time_ns",
        "instrument",
        "profile_id",
        "action",
        "prior_direction",
        "resulting_direction",
        "target_units",
        "feature_mean",
        "used_observation_count",
        "input_record_digests",
        "trigger_record_digests",
        "reason",
        "decision_digest",
    ]
    flags = dict(HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS)
    run_fields = {field.name for field in fields(HistoricalDecisionRun)} - set(flags)
    for token in ("order", "fill", "price", "pnl", "position", "metric", "sharpe", "return", "equity", "fee"):
        assert not [name for name in run_fields if token in name]


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    flags = dict(HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS)
    assert set(dict(EDGE_STRUCTURAL_NON_CLAIM_FLAGS)) <= set(flags)
    for name in (
        "orders_created",
        "fills_simulated",
        "positions_mutated",
        "pnl_computed",
        "performance_metrics_computed",
        "semantic_equivalence_machine_proven",
        "external_archive_truth_proven",
        "pbo_passed",
        "stress_passed",
        "edge_proven",
        "live_ready",
    ):
        assert flags[name] is False
    defaults = {field.name: field.default for field in fields(HistoricalDecisionRun) if field.name in flags}
    assert defaults == flags
    assert not set(flags) & set(inspect.signature(build_historical_decision_run).parameters)


@pytest.mark.parametrize("flag", ["orders_created", "fills_simulated", "pnl_computed", "edge_proven", "live_ready"])
def test_forged_non_claim_flags_fail_verification(flag: str) -> None:
    verification = verify_historical_decision_run(_reseal(_standard()[0], **{flag: True}))
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_module_is_pure_and_consumes_only_public_substrate() -> None:
    pit.assert_module_is_pure(
        run_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.historical_pit_dataset",
            "crypto_core.validation.strategy_executable_binding",
            "crypto_core.validation.strategy_executable_profiles",
        },
    )


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        run_module, "HistoricalDecisionRun", "_assemble_run", "build_historical_decision_run", "_reassemble_run"
    )


def test_parameter_assignment_entries_are_the_profile_type() -> None:
    run, _, _ = _standard()
    assert all(type(item) is ProfileParameterAssignment for item in run.parameter_assignment)


# --- F5: exact parameter governance precedes execution -----------------------------------------------------------------


class EvaluationSpy:
    """Counts profile evaluations performed by the decision-run module, delegating to the real evaluator."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, *args: object, **kwargs: object):
        self.calls += 1
        return evaluate_strategy_executable_profile(*args, **kwargs)  # type: ignore[arg-type]


def _spy(monkeypatch: pytest.MonkeyPatch) -> EvaluationSpy:
    spy = EvaluationSpy()
    monkeypatch.setattr(run_module, "evaluate_strategy_executable_profile", spy)
    return spy


def _assert_governance_blocked(run: HistoricalDecisionRun, codes: set[str], spy: EvaluationSpy) -> None:
    _assert_receipt_invariants(run)
    assert (run.status, run.gate_verdict, run.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
    )
    assert set(run.verdict_reason_codes) == {_code(code) for code in codes}
    assert (run.decisions, run.decision_count) == ((), 0)
    assert spy.calls == 0


def test_exact_parameter_approval_executes_and_is_carried(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _spy(monkeypatch)
    run, _, binding = _standard()
    assert run.advances is True
    assert run.parameter_approval == bind.parameter_approval_for(binding, PARAMS)
    assert run.decision_count == 6
    assert spy.calls == 6
    _assert_receipt_invariants(run)
    assert spy.calls == 12  # verification re-executes; nothing else evaluates


def test_missing_parameter_approval_needs_governance_without_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = _spy(monkeypatch)
    run, _, _ = _standard(parameter_approval=None)
    _assert_governance_blocked(run, {"parameter_approval_missing"}, spy)


@pytest.mark.parametrize(
    "changed",
    [
        {"n": "3"},
        {"entry": "0.000200000000000000"},
        {"exit_": "0.000010000000000000"},
        {"unit": "2.000000000000000000"},
    ],
    ids=["lookback", "entry_threshold", "exit_threshold", "unit_size"],
)
def test_changed_parameter_under_the_original_approval_never_executes(
    changed: dict[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    original_approval = bind.parameter_approval_for(binding, PARAMS)
    spy = _spy(monkeypatch)
    run = decision_run(
        dataset, binding, parameter_assignment=prof.params(**changed), parameter_approval=original_approval
    )
    _assert_governance_blocked(run, {"parameter_approval_parameter_assignment_digest_mismatch"}, spy)
    approved = decision_run(dataset, binding, parameter_assignment=prof.params(**changed))
    assert approved.advances is True
    assert spy.calls > 0


def test_approval_for_spec_a_never_executes_under_spec_b(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, admission_a, registry = _world()
    _, admission_b, _ = _world(spec_changes={"latency_sensitivity": "medium"})
    dataset = pit.pit_dataset(manifest, registry)
    approval_a = bind.parameter_approval_for(bind.executable_binding(admission_a), PARAMS)
    binding_b = bind.executable_binding(admission_b)
    assert binding_b.advances is True
    spy = _spy(monkeypatch)
    run = decision_run(dataset, binding_b, parameter_approval=approval_a)
    _assert_governance_blocked(
        run,
        {
            "parameter_approval_executable_binding_digest_mismatch",
            "parameter_approval_strategy_spec_digest_mismatch",
        },
        spy,
    )


def test_approval_for_binding_a_never_executes_under_binding_b(monkeypatch: pytest.MonkeyPatch) -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    approval_a = bind.parameter_approval_for(bind.executable_binding(admission), PARAMS)
    binding_b = bind.executable_binding(admission, binding_id="binding-2")
    spy = _spy(monkeypatch)
    run = decision_run(dataset, binding_b, parameter_approval=approval_a)
    _assert_governance_blocked(run, {"parameter_approval_executable_binding_digest_mismatch"}, spy)


@pytest.mark.parametrize(
    "drift",
    [
        {"numeric_policy_id": "passive_funding_carry_numeric_policy.v2"},
        {"max_decimal_text_length": 59},
        {"max_positive_integer": 2**31 - 1},
        {"mean_output_scale": 8},
    ],
    ids=lambda drift: next(iter(drift)),
)
def test_approval_from_old_profile_semantics_never_executes_after_numeric_policy_drift(
    drift: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    old_approval = bind.parameter_approval_for(bind.executable_binding(admission), PARAMS)
    drifted = bind.drifted_registry_profile(**drift)
    monkeypatch.setitem(profiles_module._REGISTRY, PASSIVE_FUNDING_CARRY_V1, drifted)
    rebound = bind.executable_binding(admission, expected_profile_semantics_digest=drifted.profile_semantics_digest)
    assert rebound.advances is True
    spy = _spy(monkeypatch)
    run = decision_run(dataset, rebound, parameter_approval=old_approval)
    assert spy.calls == 0
    assert {
        _code("parameter_approval_executable_binding_digest_mismatch"),
        _code("parameter_approval_profile_semantics_digest_mismatch"),
    } <= set(run.verdict_reason_codes)
    assert run.advances is False
    assert run.decisions == ()


def test_copied_or_resealed_run_cannot_substitute_the_parameter_approval() -> None:
    run, _, binding = _standard()
    for substitute in (None, bind.parameter_approval_for(binding, prof.params(n="3"))):
        forged = _reseal(run, parameter_approval=substitute)
        verification = verify_historical_decision_run(forged)
        assert verification.intact is False
        assert {_code("field_mismatch:gate_verdict"), _code("field_mismatch:decisions")} <= set(
            verification.reason_codes
        )
    blocked, _, _ = _standard(parameter_approval=None)
    promoted = _fully_resealed_trace(
        _reseal(blocked, parameter_approval=run.parameter_approval, gate_verdict=EdgeGateVerdict.PASS, advances=True),
        run.decisions,
    )
    assert verify_historical_decision_run(promoted).intact is False


@pytest.mark.parametrize(
    "approval",
    ["approved", {"approval_reference": "x"}, "bad_hex"],
    ids=["string", "mapping", "bad_hex"],
)
def test_malformed_parameter_approval_is_a_construction_error(approval: object) -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    binding = bind.executable_binding(admission)
    if approval == "bad_hex":
        approval = bind.parameter_approval_for(binding, PARAMS, approved_parameter_assignment_digest="Z" * 64)
    with pytest.raises(HistoricalDecisionRunError, match="parameter_approval_malformed"):
        decision_run(dataset, binding, parameter_approval=approval)


# --- F1/F2: representation safety at the run boundary -------------------------------------------------------------------


@pytest.mark.parametrize(
    "override",
    [
        {"entry": prof.OVER_POSITIVE_SCALE18},
        {"entry": prof.EIGHTY_DIGIT_SCALE18},
        {"exit_": prof.OVER_POSITIVE_SCALE18},
        {"unit": prof.EIGHTY_DIGIT_SCALE18},
        {"n": "1" * 4301},
        {"n": "9223372036854775808"},
    ],
    ids=["entry_61", "entry_80_digits", "exit_61", "unit_80_digits", "lookback_4301_digits", "lookback_int64_plus_one"],
)
def test_oversized_parameters_are_run_domain_errors(override: dict[str, str]) -> None:
    with pytest.raises(HistoricalDecisionRunError, match="parameter_assignment_invalid"):
        _standard(parameter_assignment=prof.params(**override))


def test_boundary_representations_run_end_to_end() -> None:
    rates = (prof.MAX_POSITIVE_SCALE18,) * 3
    run, _, _ = _standard(
        pit.records(rates),
        parameter_assignment=prof.params(entry=prof.TINY, exit_="0.000000000000000000", unit=prof.MAX_POSITIVE_SCALE18),
    )
    assert run.advances is True
    assert [d.feature_mean for d in run.decisions] == [None, prof.MAX_POSITIVE_SCALE18, prof.MAX_POSITIVE_SCALE18]
    assert run.decisions[1].target_units == prof.MAX_POSITIVE_SCALE18
    lookback_max, _, _ = _standard(parameter_assignment=prof.params(n=prof.INT64_MAX_TEXT))
    assert lookback_max.advances is True
    assert {d.action for d in lookback_max.decisions} == {"NO_ACTION"}
    far_end, _, _ = _standard(evaluation_end_ns=9223372036854775807)
    assert far_end.decision_count == 6


def test_forged_dataset_with_an_oversized_value_is_a_domain_error() -> None:
    manifest, admission, registry = _world()
    dataset = pit.pit_dataset(manifest, registry)
    forged_record = replace(dataset.records[0], values=(HistoricalPitValue("funding_rate", prof.EIGHTY_DIGIT_SCALE18),))
    forged = replace(dataset, records=(forged_record,) + dataset.records[1:])
    with pytest.raises(HistoricalDecisionRunError, match="dataset_not_serializable"):
        decision_run(forged, bind.executable_binding(admission), expected_dataset_digest=dataset.dataset_digest)


@pytest.mark.parametrize(
    ("field_name", "magnitude"),
    [
        ("evaluation_start_ns", "int64_plus_one"),
        ("evaluation_end_ns", "int64_plus_one"),
        ("evaluation_end_ns", "ten_pow_5000"),
    ],
    ids=["start_int64_plus_one", "end_int64_plus_one", "end_ten_pow_5000"],
)
def test_oversized_evaluation_bounds_are_domain_errors(field_name: str, magnitude: str) -> None:
    with pytest.raises(HistoricalDecisionRunError, match=f"{field_name}_invalid"):
        _standard(**{field_name: pit._huge(magnitude)})


@pytest.mark.parametrize(
    ("path", "value"),
    [
        (("decisions", 0, "decision_time_ns"), 9223372036854775808),
        (("decisions", 0, "decision_sequence"), -1),
        (("evaluation_end_ns",), 9223372036854775808),
        (("parameter_approval",), {"approval_reference": "governance-parameters-1"}),
        (("parameter_approval", "approval_digest"), 7),
    ],
    ids=["time_over", "sequence_negative", "end_over", "approval_partial", "approval_digest_int"],
)
def test_parser_refuses_out_of_domain_integers_and_approvals(path: tuple[object, ...], value: object) -> None:
    payload = historical_decision_run_to_dict(_standard()[0])
    target: object = payload
    for step in path[:-1]:
        target = target[step]  # type: ignore[index]
    target[path[-1]] = value  # type: ignore[index]
    assert historical_decision_run_payload_is_well_formed(payload) is False


def test_verifier_is_total_for_oversized_carried_integers() -> None:
    run, _, _ = _standard()
    for name, value in (("evaluation_end_ns", 10**5000), ("decision_count", 10**5000), ("evaluation_start_ns", -5)):
        copy = replace(run)
        object.__setattr__(copy, name, value)
        verification = verify_historical_decision_run(copy)
        assert verification.intact is False
        assert verification.reason_codes


# --- F3: ambient Decimal context independence of the whole run ---------------------------------------------------------


def _astra_run() -> HistoricalDecisionRun:
    tiny = prof.TINY
    return _standard(
        pit.records((tiny, tiny, "0.000000000000000002")),
        parameter_assignment=prof.params(entry=tiny, exit_="0.000000000000000000", n="3"),
    )[0]


@pytest.mark.parametrize("context_name", sorted(prof._AMBIENT_CONTEXTS))
def test_run_digest_is_independent_of_the_ambient_decimal_context(context_name: str) -> None:
    baseline = _astra_run()
    assert baseline.decisions[-1].feature_mean == prof.TINY
    with decimal.localcontext(prof._AMBIENT_CONTEXTS[context_name]()) as active:
        before = prof.context_state(active)
        run = _astra_run()
        verification = verify_historical_decision_run(run)
        assert prof.context_state(decimal.getcontext()) == before
    assert run.run_digest == baseline.run_digest
    assert run.decision_trace_digest == baseline.decision_trace_digest
    assert verification.intact is True
    assert verification.canonical_json == verify_historical_decision_run(baseline).canonical_json
