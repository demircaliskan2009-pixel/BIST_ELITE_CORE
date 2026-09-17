"""Deterministic historical decision run: PIT dataset × executable binding × parameters → decision trace.

A ``HistoricalDecisionRun`` is the first executable-strategy authority of the historical evaluation substrate. It
binds an authenticated ``HistoricalPitDataset`` and an authenticated ``StrategyExecutableBinding`` (both re-proven
through their public verifiers against caller anchors, same correlation, READY), requires both to come from the same
EF-3 source manifest, validates the exact governed parameter assignment against the code-defined profile schema, and
re-executes the registered profile over PIT views for one instrument inside ``[evaluation_start_ns,
evaluation_end_ns)``.

Decision schedule (H2): one decision per distinct ``max(available_at_ns, finalized_at_ns)`` of a final funding record
of the profile's required series for the instrument. At each decision instant the PIT view exposes only final records
available and finalized at or before that instant (latest vintage only), and the profile decides from the last N final
funding rates. Every run starts FLAT and threads the resulting direction through the ordered decisions.

Each decision record carries only what a later execution-economics layer needs: sequence, time, instrument, profile,
action, prior and resulting direction, target units where applicable, the exact feature mean, the digests of the
input records used and of the records that triggered the instant, and a decision digest. There is no order, fill,
execution price, position, PnL or performance metric. The verifier re-executes the complete run, so a copied or
resealed decision trace never becomes authoritative.

Status is integrity only; REJECTED implies NOT_EVALUATED; a non-advancing dataset or binding propagates its verdict and
produces no decisions; only READY + PASS advances. Deterministic, historical-evaluation only: no IO, clock, randomness,
network or environment; proves no edge, profitability or readiness.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    historical_pit_dataset_from_payload,
    historical_pit_dataset_payload_is_well_formed,
    historical_pit_dataset_to_dict,
    select_visible_pit_records,
    verify_historical_pit_dataset,
)
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableBinding,
    strategy_executable_binding_from_payload,
    strategy_executable_binding_payload_is_well_formed,
    strategy_executable_binding_to_dict,
    verify_strategy_executable_binding,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileDirection,
    ProfileParameterAssignment,
    StrategyExecutableProfile,
    StrategyExecutableProfileError,
    canonical_profile_parameter_assignment,
    evaluate_strategy_executable_profile,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)

_SCHEMA_VERSION = "historical-decision-run.v1"
_REASON_PREFIX = "historical_decision_run"
_SELF_DIGEST_FIELD = "run_digest"
_DECISION_DIGEST_FIELD = "decision_digest"
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")

HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("pbo_passed", False),
    ("stress_passed", False),
    ("external_archive_truth_proven", False),
    ("semantic_equivalence_machine_proven", False),
    ("orders_created", False),
    ("fills_simulated", False),
    ("positions_mutated", False),
    ("pnl_computed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS)


class HistoricalDecisionRunError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class HistoricalDecisionRecord:
    """One deterministic profile decision; ``decision_digest`` covers every other field. Never an order."""

    decision_sequence: int
    decision_time_ns: int
    instrument: str
    profile_id: str
    action: str
    prior_direction: str
    resulting_direction: str
    target_units: str | None
    feature_mean: str | None
    used_observation_count: int
    input_record_digests: tuple[str, ...]
    trigger_record_digests: tuple[str, ...]
    reason: str
    decision_digest: str


@dataclass(frozen=True)
class HistoricalDecisionRun:
    """Immutable, digest-bound historical decision trace. Historical evaluation only; proves no edge."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    run_id: str
    correlation_id: str
    dataset_binding: EdgeAuthorityBinding
    dataset_digest: str
    executable_binding: EdgeAuthorityBinding
    executable_binding_digest: str
    source_manifest_digest: str
    admission_digest: str
    strategy_spec_digest: str
    profile_id: str
    profile_version: str
    profile_semantics_digest: str
    parameter_assignment: tuple[ProfileParameterAssignment, ...]
    parameter_assignment_digest: str
    instrument: str
    evaluation_start_ns: int
    evaluation_end_ns: int
    funding_series_id: str
    decisions: tuple[HistoricalDecisionRecord, ...]
    decision_count: int
    decision_trace_digest: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    run_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
    performance_data_consumed: bool = False
    oos_evidence_consumed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    pbo_passed: bool = False
    stress_passed: bool = False
    external_archive_truth_proven: bool = False
    semantic_equivalence_machine_proven: bool = False
    orders_created: bool = False
    fills_simulated: bool = False
    positions_mutated: bool = False
    pnl_computed: bool = False
    performance_metrics_computed: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> HistoricalDecisionRunError:
    return HistoricalDecisionRunError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_instrument(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail("instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("instrument_invalid")
    return _require_text(value, "instrument")


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise _fail(f"{field_name}_invalid")
    return value


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


def _structural_parameter_assignment(values: object) -> tuple[ProfileParameterAssignment, ...]:
    if type(values) not in (tuple, list):
        raise _fail("parameter_assignment_malformed")
    entries: list[ProfileParameterAssignment] = []
    for item in values:  # type: ignore[union-attr]
        if type(item) is not ProfileParameterAssignment or type(item.parameter_id) is not str:
            raise _fail("parameter_assignment_entry_malformed")
        if type(item.value) is not str:
            raise _fail("parameter_assignment_entry_malformed")
        entries.append(ProfileParameterAssignment(parameter_id=item.parameter_id, value=item.value))
    if len({entry.parameter_id for entry in entries}) != len(entries):
        raise _fail("parameter_assignment_duplicate")
    return tuple(sorted(entries, key=lambda entry: entry.parameter_id))


# --- authorities -------------------------------------------------------------------------------------------------------


def _dataset_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str
) -> tuple[list[str], HistoricalPitDataset | None]:
    dataset = historical_pit_dataset_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_pit_dataset(dataset)
    if not verification.intact:
        return [_reason(f"dataset_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("dataset_digest_mismatch")], None
    if dataset.correlation_id != correlation_id:
        return [_reason("dataset_correlation_mismatch")], None
    if dataset.status is not EdgeEvidenceStatus.READY:
        return [_reason("dataset_rejected")], None
    return [], dataset


def _binding_authority(
    binding: EdgeAuthorityBinding, *, correlation_id: str
) -> tuple[list[str], StrategyExecutableBinding | None]:
    executable = strategy_executable_binding_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_strategy_executable_binding(executable)
    if not verification.intact:
        return [_reason(f"executable_binding_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("executable_binding_digest_mismatch")], None
    if executable.correlation_id != correlation_id:
        return [_reason("executable_binding_correlation_mismatch")], None
    if executable.status is not EdgeEvidenceStatus.READY:
        return [_reason("executable_binding_rejected")], None
    return [], executable


def _propagate(code_prefix: str, verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"{code_prefix}_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


def _required_series(
    dataset: HistoricalPitDataset, profile: StrategyExecutableProfile, instrument: str
) -> tuple[list[str], str]:
    candidates = [
        series
        for series in dataset.series_semantics
        if series.data_requirement_key in profile.required_data_requirement_keys
        and series.funding_semantics == profile.required_funding_semantics
        and series.final_required
        and instrument in series.instrument_coverage
    ]
    if not candidates:
        return [_reason("required_final_series_missing")], ""
    if len(candidates) > 1:
        return [_reason("required_final_series_ambiguous")], ""
    series_id = candidates[0].series_id
    missing_values = sorted(
        record.record_digest
        for record in dataset.records
        if record.series_id == series_id
        and record.instrument == instrument
        and not set(profile.required_value_names) <= {value.name for value in record.values}
    )
    return [_reason(f"required_value_missing:{digest}") for digest in missing_values], series_id


def _decision_trace(
    dataset: HistoricalPitDataset,
    profile: StrategyExecutableProfile,
    parameters: Sequence[ProfileParameterAssignment],
    *,
    series_id: str,
    instrument: str,
    start_ns: int,
    end_ns: int,
) -> tuple[HistoricalDecisionRecord, ...]:
    """Re-execute the registered profile at every scheduled decision instant (H2) in ``[start_ns, end_ns)``."""

    lookback = int({item.parameter_id: item.value for item in parameters}["final_funding_lookback_count"])
    value_name = profile.required_value_names[0]
    triggers: dict[int, list[str]] = {}
    for record in dataset.records:
        if record.series_id != series_id or record.instrument != instrument or record.finalized_at_ns is None:
            continue
        decision_time = max(record.available_at_ns, record.finalized_at_ns)
        if start_ns <= decision_time < end_ns:
            triggers.setdefault(decision_time, []).append(record.record_digest)
    direction = ProfileDirection.FLAT
    decisions: list[HistoricalDecisionRecord] = []
    for sequence, decision_time in enumerate(sorted(triggers)):
        view = select_visible_pit_records(
            dataset, series_id=series_id, instrument=instrument, decision_time_ns=decision_time
        )
        rates = [next(value.value for value in record.values if value.name == value_name) for record in view.records]
        decision = evaluate_strategy_executable_profile(
            profile, final_funding_rates=rates, parameter_assignment=parameters, prior_direction=direction
        )
        used = view.records[-lookback:] if len(view.records) >= lookback else view.records
        seed = HistoricalDecisionRecord(
            decision_sequence=sequence,
            decision_time_ns=decision_time,
            instrument=instrument,
            profile_id=profile.profile_id,
            action=decision.action.value,
            prior_direction=decision.prior_direction.value,
            resulting_direction=decision.resulting_direction.value,
            target_units=decision.target_units,
            feature_mean=decision.feature_mean,
            used_observation_count=decision.used_observation_count,
            input_record_digests=tuple(record.record_digest for record in used),
            trigger_record_digests=tuple(sorted(triggers[decision_time])),
            reason=decision.reason,
            decision_digest="",
        )
        decisions.append(replace(seed, decision_digest=edge_payload_digest(_to_payload(seed), _DECISION_DIGEST_FIELD)))
        direction = decision.resulting_direction
    return tuple(decisions)


# --- run ---------------------------------------------------------------------------------------------------------------


def _assemble_run(
    *,
    dataset_binding: object,
    executable_binding: object,
    run_id: object,
    correlation_id: object,
    parameter_assignment: object,
    instrument: object,
    evaluation_start_ns: object,
    evaluation_end_ns: object,
) -> HistoricalDecisionRun:
    """The one decision-run assembly path, shared by the builder and verifier re-execution."""

    dataset_ref = require_edge_authority_binding(
        dataset_binding,
        shape=historical_pit_dataset_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("dataset"),
        optional=False,
    )
    binding_ref = require_edge_authority_binding(
        executable_binding,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("executable_binding"),
        optional=False,
    )
    run_id = _require_text(run_id, "run_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    instrument = _require_instrument(instrument)
    start_ns = _require_positive_int(evaluation_start_ns, "evaluation_start_ns")
    end_ns = _require_positive_int(evaluation_end_ns, "evaluation_end_ns")
    if start_ns >= end_ns:
        raise _fail("evaluation_bounds_invalid")
    parameters = _structural_parameter_assignment(parameter_assignment)

    dataset_codes, dataset = _dataset_authority(dataset_ref, correlation_id=correlation_id)  # type: ignore[arg-type]
    binding_codes, executable = _binding_authority(binding_ref, correlation_id=correlation_id)  # type: ignore[arg-type]
    codes = [*dataset_codes, *binding_codes]
    if (
        dataset is not None
        and executable is not None
        and dataset.source_manifest_digest != (executable.source_manifest_digest)
    ):
        codes.append(_reason("dataset_binding_chain_mismatch"))
    profile: StrategyExecutableProfile | None = None
    if executable is not None:
        try:
            profile = get_strategy_executable_profile(executable.profile_id)
        except StrategyExecutableProfileError:
            codes.append(_reason("profile_unknown"))
        if profile is not None and profile.profile_semantics_digest != executable.registered_profile_semantics_digest:
            codes.append(_reason("profile_semantics_digest_mismatch"))
    if profile is not None:
        try:
            parameters = canonical_profile_parameter_assignment(profile, parameters)
        except StrategyExecutableProfileError as exc:
            raise _fail("parameter_assignment_invalid") from exc
    integrity = _sorted_unique(codes)

    series_id = ""
    decisions: tuple[HistoricalDecisionRecord, ...] = ()
    if integrity or dataset is None or executable is None or profile is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        buckets: tuple[list[str], list[str], list[str]] = ([], [], [])
        if dataset.advances is not True:
            _propagate("dataset", dataset.gate_verdict, buckets)
        if executable.advances is not True:
            _propagate("executable_binding", executable.gate_verdict, buckets)
        if instrument not in executable.instrument_universe:
            buckets[0].append(_reason("instrument_outside_strategy_universe"))
        series_codes, series_id = _required_series(dataset, profile, instrument)
        buckets[0].extend(series_codes)
        fail, needs_external, needs_governance = buckets
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)
        if verdict is EdgeGateVerdict.PASS:
            decisions = _decision_trace(
                dataset,
                profile,
                parameters,
                series_id=series_id,
                instrument=instrument,
                start_ns=start_ns,
                end_ns=end_ns,
            )

    seed = HistoricalDecisionRun(
        schema_version=_SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        run_id=run_id,
        correlation_id=correlation_id,
        dataset_binding=dataset_ref,  # type: ignore[arg-type]
        dataset_digest=dataset_ref.expected_digest,  # type: ignore[union-attr]
        executable_binding=binding_ref,  # type: ignore[arg-type]
        executable_binding_digest=binding_ref.expected_digest,  # type: ignore[union-attr]
        source_manifest_digest="" if dataset is None else dataset.source_manifest_digest,
        admission_digest="" if executable is None else executable.admission_digest,
        strategy_spec_digest="" if executable is None else executable.strategy_spec_digest,
        profile_id="" if profile is None else profile.profile_id,
        profile_version="" if profile is None else profile.profile_version,
        profile_semantics_digest="" if profile is None else profile.profile_semantics_digest,
        parameter_assignment=parameters,
        parameter_assignment_digest=profile_parameter_assignment_digest(parameters),
        instrument=instrument,
        evaluation_start_ns=start_ns,
        evaluation_end_ns=end_ns,
        funding_series_id=series_id,
        decisions=decisions,
        decision_count=len(decisions),
        decision_trace_digest=edge_sha256_text(edge_canonical_json([_to_payload(item) for item in decisions])),
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        run_digest="",
    )
    return replace(seed, run_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_historical_decision_run(
    dataset: HistoricalPitDataset,
    executable_binding: StrategyExecutableBinding,
    *,
    expected_dataset_digest: str,
    expected_executable_binding_digest: str,
    run_id: str,
    correlation_id: str,
    parameter_assignment: Sequence[ProfileParameterAssignment],
    instrument: str,
    evaluation_start_ns: int,
    evaluation_end_ns: int,
) -> HistoricalDecisionRun:
    """Build a deterministic historical decision run by executing the bound profile over PIT views.

    Malformed caller input, an invalid parameter assignment or a non-serializable upstream object raises
    ``HistoricalDecisionRunError``. A dataset or binding that fails re-proof, or a cross-chain splice, yields
    ``REJECTED``/``NOT_EVALUATED``. Non-advancing upstream authority propagates without decisions.
    """

    if type(dataset) is not HistoricalPitDataset:
        raise _fail("dataset_malformed")
    if type(executable_binding) is not StrategyExecutableBinding:
        raise _fail("executable_binding_malformed")
    try:
        dataset_payload = historical_pit_dataset_to_dict(dataset)
    except Exception as exc:  # noqa: BLE001 - a hollow dataset object is a construction error, never a receipt
        raise _fail("dataset_not_serializable") from exc
    try:
        binding_payload = strategy_executable_binding_to_dict(executable_binding)
    except Exception as exc:  # noqa: BLE001 - a hollow binding object is a construction error, never a receipt
        raise _fail("executable_binding_not_serializable") from exc
    dataset_ref = build_edge_authority_binding(
        snapshot_payload=dataset_payload,
        expected_digest=expected_dataset_digest,
        shape=historical_pit_dataset_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("dataset"),
    )
    binding_ref = build_edge_authority_binding(
        snapshot_payload=binding_payload,
        expected_digest=expected_executable_binding_digest,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("executable_binding"),
    )
    return _assemble_run(
        dataset_binding=dataset_ref,
        executable_binding=binding_ref,
        run_id=run_id,
        correlation_id=correlation_id,
        parameter_assignment=parameter_assignment,
        instrument=instrument,
        evaluation_start_ns=evaluation_start_ns,
        evaluation_end_ns=evaluation_end_ns,
    )


def historical_decision_run_to_dict(run: HistoricalDecisionRun) -> dict[str, object]:
    """Canonical JSON-ready mapping for a decision run, including its self-digest."""

    return _to_payload(run)


def historical_decision_run_digest(run: HistoricalDecisionRun) -> str:
    """Recompute the canonical run digest, excluding only ``run_digest``."""

    return edge_payload_digest(_to_payload(run), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int:
        raise _fail("payload_field_malformed")
    return value


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _parse_dataset_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=historical_pit_dataset_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("dataset"),
        optional=False,
    )


def _parse_executable_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=strategy_executable_binding_payload_is_well_formed,
        error=HistoricalDecisionRunError,
        code=_reason("executable_binding"),
        optional=False,
    )


_DECISION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "decision_sequence": _as_int,
    "decision_time_ns": _as_int,
    "target_units": _as_optional_str,
    "feature_mean": _as_optional_str,
    "used_observation_count": _as_int,
    "input_record_digests": _as_str_tuple,
    "trigger_record_digests": _as_str_tuple,
}
_RUN_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "dataset_binding": _parse_dataset_binding,
    "executable_binding": _parse_executable_binding,
    "parameter_assignment": _as_records(ProfileParameterAssignment, {}),
    "evaluation_start_ns": _as_int,
    "evaluation_end_ns": _as_int,
    "decisions": _as_records(HistoricalDecisionRecord, _DECISION_CONVERTERS),
    "decision_count": _as_int,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def historical_decision_run_from_payload(payload: object) -> HistoricalDecisionRun:
    """Strictly reconstruct a decision run from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(HistoricalDecisionRun, payload, _RUN_CONVERTERS)  # type: ignore[return-value]


def historical_decision_run_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a decision-run snapshot."""

    try:
        historical_decision_run_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_run(run: object) -> HistoricalDecisionRun:
    return _assemble_run(
        dataset_binding=run.dataset_binding,  # type: ignore[attr-defined]
        executable_binding=run.executable_binding,  # type: ignore[attr-defined]
        run_id=run.run_id,  # type: ignore[attr-defined]
        correlation_id=run.correlation_id,  # type: ignore[attr-defined]
        parameter_assignment=run.parameter_assignment,  # type: ignore[attr-defined]
        instrument=run.instrument,  # type: ignore[attr-defined]
        evaluation_start_ns=run.evaluation_start_ns,  # type: ignore[attr-defined]
        evaluation_end_ns=run.evaluation_end_ns,  # type: ignore[attr-defined]
    )


def verify_historical_decision_run(run: object) -> EdgeEvidenceVerification:
    """Re-prove a run by strict parse, dataset and binding re-proof and full profile re-execution. Total."""

    return verify_edge_artifact_total(
        run,
        cls=HistoricalDecisionRun,
        to_payload=_to_payload,
        parse_payload=historical_decision_run_from_payload,
        reassemble=_reassemble_run,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "HISTORICAL_DECISION_RUN_NON_CLAIM_FLAGS",
    "HistoricalDecisionRecord",
    "HistoricalDecisionRun",
    "HistoricalDecisionRunError",
    "build_historical_decision_run",
    "historical_decision_run_digest",
    "historical_decision_run_from_payload",
    "historical_decision_run_payload_is_well_formed",
    "historical_decision_run_to_dict",
    "verify_historical_decision_run",
]
