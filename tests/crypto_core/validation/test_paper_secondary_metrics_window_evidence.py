"""Tests for digest-bound SM reconciliation membership in one exact UTC gate window."""

from __future__ import annotations

import inspect
from dataclasses import FrozenInstanceError, fields, replace
from enum import Enum

import pytest

import crypto_core.validation.paper_secondary_metrics_window_evidence as window_module
from crypto_core.validation.paper_episode_runner import paper_episode_run_result_digest
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationStatus,
    paper_fill_market_snapshot_digest,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_secondary_metrics_window_evidence import (
    PaperSecondaryMetricsWindowEvidence,
    PaperSecondaryMetricsWindowEvidenceError,
    PaperSecondaryMetricsWindowEvidenceStatus,
    PaperSecondaryMetricsWindowRecordInput,
    build_paper_secondary_metrics_window_evidence,
    paper_secondary_metrics_window_evidence_digest,
    paper_secondary_metrics_window_evidence_to_dict,
)
from tests.crypto_core.validation import test_paper_stage4_comparison_evidence_v2 as support

_DAY_NS = 86_400_000_000_000
_HEX_A = "a" * 64
_FIELD_ORDER = (
    "schema_version",
    "evidence_version",
    "status",
    "ready",
    "window_evidence_id",
    "correlation_id",
    "policy_id",
    "market_symbol",
    "window_id",
    "reconciliation_id",
    "gate_id",
    "expected_reconciliation_digest",
    "verified_reconciliation_digest",
    "expected_gate_decision_digest",
    "verified_gate_decision_digest",
    "verified_policy_digest",
    "verified_metrics_evidence_digest",
    "verified_session_sequence_digest",
    "gate_window_start_ns",
    "gate_window_end_ns",
    "gate_window_start_utc_day_index",
    "gate_window_end_utc_day_index",
    "gate_utc_day_indices",
    "observed_at_ns",
    "observed_utc_day_indices",
    "record_digests",
    "episode_run_digests",
    "fill_result_digests",
    "market_snapshot_digests",
    "record_count",
    "reason_codes",
    "metadata",
    "window_evidence_digest",
    "paper_only",
    "validation_only",
    "reconciliation_consumed",
    "gate_decision_consumed",
    "exact_window_bound",
    "record_set_reconciled",
    "timestamps_digest_bound",
    "stage4_comparator_invoked",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "operational_readiness",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "real_wall_clock_used",
)
_ALWAYS_FALSE = (
    "stage4_comparator_invoked",
    "secondary_metrics_enforced",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "operational_readiness",
    "production_execution",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "private_api_ready",
    "live_api_called",
    "real_wall_clock_used",
)


def _rc(code: str) -> str:
    return f"paper_secondary_metrics_window_evidence:{code}"


def _build(chain: support._Chain | None = None, **overrides: object) -> PaperSecondaryMetricsWindowEvidence:
    chain = chain or support._chain()
    reconciliation = overrides.pop("reconciliation", chain.reconciliation)
    gate_decision = overrides.pop("gate_decision", chain.gate)
    record_inputs = overrides.pop("record_inputs", chain.window_inputs)
    payload: dict[str, object] = {
        "expected_reconciliation_digest": getattr(reconciliation, "reconciliation_digest", _HEX_A),
        "expected_gate_decision_digest": getattr(gate_decision, "decision_digest", _HEX_A),
        "window_evidence_id": "window-evidence-test",
        "correlation_id": support._CORRELATION,
        "metadata": {"purpose": "exact UTC membership"},
    }
    payload.update(overrides)
    return build_paper_secondary_metrics_window_evidence(
        reconciliation,  # type: ignore[arg-type]
        gate_decision,  # type: ignore[arg-type]
        record_inputs,  # type: ignore[arg-type]
        **payload,  # type: ignore[arg-type]
    )


def _reseal(evidence: PaperSecondaryMetricsWindowEvidence, **changes: object) -> PaperSecondaryMetricsWindowEvidence:
    seed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(seed, window_evidence_digest=paper_secondary_metrics_window_evidence_digest(seed))


def _snapshot_input_with_observed_at(
    chain: support._Chain, index: int, observed_at_ns: object
) -> PaperSecondaryMetricsWindowRecordInput:
    original = chain.window_inputs[index]
    snapshot_seed = replace(original.market_snapshot, observed_at_ns=observed_at_ns)  # type: ignore[arg-type]
    snapshot = replace(
        snapshot_seed,
        snapshot_digest=paper_fill_market_snapshot_digest(snapshot_seed),
    )
    return replace(original, market_snapshot=snapshot)


def test_public_contract_exact() -> None:
    assert window_module.__all__ == [
        "PaperSecondaryMetricsWindowEvidence",
        "PaperSecondaryMetricsWindowEvidenceError",
        "PaperSecondaryMetricsWindowEvidenceStatus",
        "PaperSecondaryMetricsWindowRecordInput",
        "build_paper_secondary_metrics_window_evidence",
        "paper_secondary_metrics_window_evidence_digest",
        "paper_secondary_metrics_window_evidence_to_dict",
    ]
    assert [status.value for status in PaperSecondaryMetricsWindowEvidenceStatus] == ["WINDOW_READY", "REJECTED"]
    assert tuple(field.name for field in fields(PaperSecondaryMetricsWindowEvidence)) == _FIELD_ORDER
    assert len(_FIELD_ORDER) == 61


def test_builder_signature_exact() -> None:
    parameters = inspect.signature(build_paper_secondary_metrics_window_evidence).parameters
    assert list(parameters) == [
        "reconciliation",
        "gate_decision",
        "record_inputs",
        "expected_reconciliation_digest",
        "expected_gate_decision_digest",
        "window_evidence_id",
        "correlation_id",
        "metadata",
    ]
    assert all(parameters[name].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD for name in list(parameters)[:3])
    assert all(parameters[name].kind is inspect.Parameter.KEYWORD_ONLY for name in list(parameters)[3:])


def test_ready_binds_exact_reconciliation_gate_and_snapshot_lineage() -> None:
    chain = support._chain()
    evidence = _build(chain)
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.WINDOW_READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert evidence.expected_reconciliation_digest == chain.reconciliation.reconciliation_digest
    assert evidence.verified_reconciliation_digest == chain.reconciliation.reconciliation_digest
    assert evidence.expected_gate_decision_digest == chain.gate.decision_digest
    assert evidence.verified_gate_decision_digest == chain.gate.decision_digest
    assert evidence.verified_metrics_evidence_digest == chain.metrics.evidence_digest
    assert evidence.verified_session_sequence_digest == chain.session.paper_session_sequence_digest
    assert evidence.gate_window_start_ns == _DAY_NS
    assert evidence.gate_window_end_ns == 31 * _DAY_NS
    assert evidence.gate_utc_day_indices == tuple(range(1, 31))
    assert evidence.observed_at_ns == (2 * _DAY_NS, 3 * _DAY_NS)
    assert evidence.observed_utc_day_indices == (2, 3)
    assert evidence.record_digests == chain.reconciliation.reconciled_record_digests
    assert evidence.episode_run_digests == chain.reconciliation.reconciled_episode_run_digests
    assert evidence.reconciliation_consumed is True
    assert evidence.gate_decision_consumed is True
    assert evidence.exact_window_bound is True
    assert evidence.record_set_reconciled is True
    assert evidence.timestamps_digest_bound is True


def test_output_and_record_input_are_frozen() -> None:
    evidence = _build()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        support._chain().window_inputs[0].record = support._chain().records[1]  # type: ignore[misc]


def test_digest_and_serializer_are_deterministic_complete_and_metadata_order_independent() -> None:
    first = _build(metadata={"b": "2", "a": "1"})
    second = _build(metadata={"a": "1", "b": "2"})
    changed = _build(metadata={"a": "1", "b": "3"})
    payload = paper_secondary_metrics_window_evidence_to_dict(first)
    assert first.window_evidence_digest == second.window_evidence_digest
    assert changed.window_evidence_digest != first.window_evidence_digest
    assert first.window_evidence_digest == paper_secondary_metrics_window_evidence_digest(first)
    assert set(payload) == set(_FIELD_ORDER)
    assert payload["status"] == "WINDOW_READY"
    assert payload["metadata"] == [["a", "1"], ["b", "2"]]
    assert payload["gate_utc_day_indices"] == list(range(1, 31))
    assert payload["observed_at_ns"] == [2 * _DAY_NS, 3 * _DAY_NS]
    assert (
        paper_secondary_metrics_window_evidence_digest(replace(first, window_evidence_digest="0" * 64))
        == first.window_evidence_digest
    )


@pytest.mark.parametrize("anchor", ["reconciliation", "gate"])
@pytest.mark.parametrize("mode", ["stale_expected", "tampered_carried", "resealed"])
def test_direct_anchor_digest_triples_fail_closed(anchor: str, mode: str) -> None:
    chain = support._chain()
    overrides: dict[str, object] = {}
    artifact_name = "reconciliation" if anchor == "reconciliation" else "gate_decision"
    expected_name = "expected_reconciliation_digest" if anchor == "reconciliation" else "expected_gate_decision_digest"
    digest_name = "reconciliation_digest" if anchor == "reconciliation" else "decision_digest"
    original = getattr(chain, "reconciliation" if anchor == "reconciliation" else "gate")
    if mode == "stale_expected":
        overrides[expected_name] = "0" * 64
    elif mode == "tampered_carried":
        overrides[artifact_name] = replace(original, **{digest_name: "f" * 64})
        overrides[expected_name] = "f" * 64
    else:
        if anchor == "reconciliation":
            resealed = support._reseal_reconciliation(original, metadata=(("z", "reseal"),))
        else:
            resealed = support._reseal_gate(original, metadata=(("z", "reseal"),))
        overrides[artifact_name] = resealed
        overrides[expected_name] = getattr(original, digest_name)
    evidence = _build(chain, **overrides)
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    reason = "reconciliation_digest_mismatch" if anchor == "reconciliation" else "gate_decision_digest_mismatch"
    assert _rc(reason) in evidence.reason_codes
    assert evidence.ready is False


@pytest.mark.parametrize(
    ("record_inputs", "reason"),
    [
        (lambda chain: chain.window_inputs[:1], "reconciliation_record_inventory_mismatch"),
        (lambda chain: tuple(reversed(chain.window_inputs)), "reconciliation_episode_inventory_mismatch"),
        (lambda chain: (*chain.window_inputs, chain.window_inputs[0]), "reconciliation_record_inventory_mismatch"),
    ],
)
def test_record_inventory_must_exactly_equal_reconciliation(record_inputs, reason: str) -> None:
    chain = support._chain()
    evidence = _build(chain, record_inputs=record_inputs(chain))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc(reason) in evidence.reason_codes
    assert evidence.record_set_reconciled is False


def test_episode_inventory_and_member_bijection_reject_substitution() -> None:
    chain = support._chain()
    substituted = (
        replace(chain.window_inputs[0], episode_run=chain.window_inputs[1].episode_run),
        chain.window_inputs[1],
    )
    evidence = _build(chain, record_inputs=substituted)
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc("record_episode_binding_mismatch") in evidence.reason_codes
    assert _rc("reconciliation_episode_inventory_mismatch") in evidence.reason_codes


def test_fill_and_snapshot_substitution_rejected() -> None:
    chain = support._chain()
    fill_substituted = replace(chain.window_inputs[0], fill_result=chain.window_inputs[1].fill_result)
    snapshot_substituted = replace(chain.window_inputs[0], market_snapshot=chain.window_inputs[1].market_snapshot)
    fill_evidence = _build(chain, record_inputs=(fill_substituted, chain.window_inputs[1]))
    snapshot_evidence = _build(chain, record_inputs=(snapshot_substituted, chain.window_inputs[1]))
    assert _rc("episode_fill_binding_mismatch") in fill_evidence.reason_codes
    assert _rc("snapshot_binding_mismatch") in snapshot_evidence.reason_codes
    assert fill_evidence.ready is snapshot_evidence.ready is False


@pytest.mark.parametrize(
    "observed_at_ns",
    [
        None,
        True,
        "172800000000000",
        -1,
    ],
)
def test_missing_or_malformed_snapshot_timestamp_rejects_without_raw_exception(observed_at_ns: object) -> None:
    chain = support._chain()
    malformed = _snapshot_input_with_observed_at(chain, 0, observed_at_ns)
    evidence = _build(chain, record_inputs=(malformed, chain.window_inputs[1]))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc("snapshot_timestamp_missing_or_invalid") in evidence.reason_codes
    assert evidence.timestamps_digest_bound is False


@pytest.mark.parametrize(
    ("observed_at_ns", "ready"),
    [
        (_DAY_NS, True),
        (31 * _DAY_NS - 1, True),
        (31 * _DAY_NS, False),
    ],
)
def test_gate_window_is_start_inclusive_end_exclusive(observed_at_ns: int, ready: bool) -> None:
    chain = support._Chain(
        observed_at_ns=(observed_at_ns, 2 * _DAY_NS),
        expect_window_ready=ready,
    )
    evidence = chain.window_evidence
    assert evidence.ready is ready
    if ready:
        assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.WINDOW_READY
    else:
        assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
        assert _rc("snapshot_outside_gate_window") in evidence.reason_codes


def test_observed_day_index_is_derived_not_caller_supplied() -> None:
    evidence = _build()
    substituted = _reseal(
        evidence,
        observed_utc_day_indices=(evidence.observed_utc_day_indices[0] + 1, evidence.observed_utc_day_indices[1]),
    )
    assert substituted.window_evidence_digest != evidence.window_evidence_digest
    assert substituted.observed_at_ns == evidence.observed_at_ns
    assert substituted.observed_utc_day_indices != tuple(value // _DAY_NS for value in substituted.observed_at_ns)


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("reconciliation", object(), "reconciliation_malformed"),
        ("gate_decision", object(), "gate_decision_malformed"),
        ("record_inputs", "not-a-sequence", "record_inputs_malformed"),
        ("record_inputs", (), "record_inputs_malformed"),
    ],
)
def test_malformed_top_level_inputs_raise_domain_error(field_name: str, value: object, reason: str) -> None:
    with pytest.raises(PaperSecondaryMetricsWindowEvidenceError, match=reason):
        _build(**{field_name: value})


def test_wrong_typed_record_member_raises_domain_error() -> None:
    chain = support._chain()
    malformed = PaperSecondaryMetricsWindowRecordInput(
        object(),  # type: ignore[arg-type]
        chain.window_inputs[0].episode_run,
        chain.window_inputs[0].fill_result,
        chain.window_inputs[0].market_snapshot,
    )
    with pytest.raises(PaperSecondaryMetricsWindowEvidenceError, match="window_record_input_malformed"):
        _build(chain, record_inputs=(malformed, chain.window_inputs[1]))


@pytest.mark.parametrize(
    ("field_name", "value", "reason"),
    [
        ("expected_reconciliation_digest", "bad", "expected_reconciliation_digest_invalid"),
        ("expected_gate_decision_digest", True, "expected_gate_decision_digest_invalid"),
        ("window_evidence_id", " window ", "window_evidence_id_invalid"),
        ("correlation_id", "", "correlation_id_invalid"),
        ("metadata", {"": "value"}, "metadata_malformed"),
    ],
)
def test_malformed_identity_and_serialization_inputs_raise_domain_error(
    field_name: str, value: object, reason: str
) -> None:
    with pytest.raises(PaperSecondaryMetricsWindowEvidenceError, match=reason):
        _build(**{field_name: value})


def test_scope_and_clock_tokens_raise_before_artifact_creation() -> None:
    with pytest.raises(PaperSecondaryMetricsWindowEvidenceError, match="scope_violation"):
        _build(metadata={"purpose": "enable live orders"})
    with pytest.raises(PaperSecondaryMetricsWindowEvidenceError, match="clock_token_forbidden"):
        _build(metadata={"purpose": "datetime utcnow"})


class _ForeignFillStatus(str, Enum):
    """A foreign str-enum whose ``.value`` matches a real member — digest-equivalent, type-distinct."""

    FILLED = "FILLED"


class _RaisingStatus:
    """Equality-raising status object: any equality use before the exact-type gate would crash."""

    def __eq__(self, other: object) -> bool:  # pragma: no cover - must never be invoked
        raise AssertionError("equality on a malformed status must never be invoked")

    __hash__ = None  # type: ignore[assignment]


class _EqualityTrueStatus:
    """Equality-true status object with a plausible ``.value`` — only an exact-type gate rejects it."""

    value = "FILLED"

    def __eq__(self, other: object) -> bool:
        return True

    __hash__ = None  # type: ignore[assignment]


_MALFORMED_FILL_STATUSES = (
    None,
    7,
    True,
    "FILLED",
    _ForeignFillStatus.FILLED,
    _RaisingStatus(),
    _EqualityTrueStatus(),
)


@pytest.mark.parametrize(
    "malformed_status",
    _MALFORMED_FILL_STATUSES,
    ids=["none", "int", "bool", "plain_string", "foreign_enum", "equality_raising", "equality_true"],
)
def test_window_evidence_rejects_malformed_fill_status_without_raw_exception(malformed_status: object) -> None:
    chain = support._chain()
    original = chain.window_inputs[0]
    forged_fill = replace(original.fill_result, status=malformed_status)  # type: ignore[arg-type]
    forged_input = replace(original, fill_result=forged_fill)
    evidence = _build(chain, record_inputs=(forged_input, chain.window_inputs[1]))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert evidence.ready is False
    assert _rc("fill_status_contract_invalid") in evidence.reason_codes
    assert evidence.secondary_metrics_enforced is False
    assert evidence.stage4_comparator_invoked is False
    assert evidence.exact_window_bound is False
    payload = paper_secondary_metrics_window_evidence_to_dict(evidence)
    assert payload["status"] == "REJECTED"
    assert paper_secondary_metrics_window_evidence_digest(evidence) == evidence.window_evidence_digest


def test_foreign_enum_fill_status_is_digest_equivalent_but_type_gate_rejects() -> None:
    # The upstream fill serializer emits ``status.value``, so a foreign str-enum with a matching value
    # recomputes to the SAME carried digest: digest validity must never substitute for the exact-type gate.
    chain = support._chain()
    original = chain.window_inputs[0]
    forged_fill = replace(original.fill_result, status=_ForeignFillStatus.FILLED)  # type: ignore[arg-type]
    assert original.fill_result.status is PaperFillSimulationStatus.FILLED
    assert paper_fill_simulation_result_digest(forged_fill) == original.fill_result.result_digest
    forged_input = replace(original, fill_result=forged_fill)
    evidence = _build(chain, record_inputs=(forged_input, chain.window_inputs[1]))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc("fill_status_contract_invalid") in evidence.reason_codes
    assert _rc("fill_result_digest_mismatch") not in evidence.reason_codes


def test_malformed_episode_fill_status_echo_rejects_without_raw_exception() -> None:
    chain = support._chain()
    original = chain.window_inputs[0]
    episode_seed = replace(original.episode_run, fill_status=None)  # type: ignore[arg-type]
    resealed_episode = replace(episode_seed, episode_run_digest=paper_episode_run_result_digest(episode_seed))
    forged_input = replace(original, episode_run=resealed_episode)
    evidence = _build(chain, record_inputs=(forged_input, chain.window_inputs[1]))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc("fill_status_contract_invalid") in evidence.reason_codes
    assert _rc("episode_run_digest_mismatch") not in evidence.reason_codes
    assert paper_secondary_metrics_window_evidence_digest(evidence) == evidence.window_evidence_digest


def test_exact_valid_fill_status_control_remains_window_ready() -> None:
    chain = support._chain()
    original = chain.window_inputs[0]
    control_fill = replace(original.fill_result, status=PaperFillSimulationStatus.FILLED)
    control_input = replace(original, fill_result=control_fill)
    evidence = _build(chain, record_inputs=(control_input, chain.window_inputs[1]))
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.WINDOW_READY, evidence.reason_codes
    assert evidence.ready is True


def test_rejected_reconciliation_contract_cannot_reach_window_ready() -> None:
    chain = support._chain()
    reconciliation = support._reseal_reconciliation(chain.reconciliation, ready=False)
    evidence = _build(
        chain,
        reconciliation=reconciliation,
        expected_reconciliation_digest=reconciliation.reconciliation_digest,
    )
    assert evidence.status is PaperSecondaryMetricsWindowEvidenceStatus.REJECTED
    assert _rc("reconciliation_contract_invalid") in evidence.reason_codes
    assert evidence.reconciliation_consumed is False


def test_ready_and_rejected_outputs_keep_all_unsafe_claims_structurally_false() -> None:
    ready = _build()
    rejected = _build(expected_reconciliation_digest="0" * 64)
    defaults = {field.name: field.default for field in fields(PaperSecondaryMetricsWindowEvidence)}
    for flag in _ALWAYS_FALSE:
        assert getattr(ready, flag) is False, flag
        assert getattr(rejected, flag) is False, flag
        assert defaults[flag] is False, flag
    assert ready.paper_only is rejected.paper_only is True
    assert ready.validation_only is rejected.validation_only is True
    assert rejected.reconciliation_consumed is False
    assert rejected.gate_decision_consumed is False
    assert rejected.exact_window_bound is False
    assert rejected.record_set_reconciled is False
    assert rejected.timestamps_digest_bound is False
