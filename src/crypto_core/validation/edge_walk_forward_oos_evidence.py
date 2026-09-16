"""Edge Factory EF-6: registered-only walk-forward/OOS evidence over a sealed EF-5 preregistration ledger.

EF-6 is the first Edge Factory gate that consumes performance data, and it interprets that data only against the
exact sealed EF-5 ledger: results must map to preregistered ``(variant_id, window_id)`` pairs carrying the variant's
ledger registration digest, every registered variant must report every preregistered window, the run must declare
exactly the preregistered evaluation assumption identities, and only the preregistered primary variant is
interpreted — through the accepted ``walk_forward.validate_walk_forward`` with the human-approved minimum OOS window
count passed explicitly, never its default.

Trust model (shared kernel ``edge_artifact_core``):

* Full back-chain re-proof. The EF-5 ledger is a required ``EdgeAuthorityBinding`` re-proven through
  ``verify_edge_leakage_bias_evidence`` against the caller anchor; its EF-4 → EF-3 → EF-2 chain is re-proven again
  independently through ``reprove_edge_admitted_chain`` with the explicit EF-2 root anchor, so a foreign artifact at
  any level is an integrity rejection.
* No performance interpretation without a sealed, advancing ledger: a READY ledger that does not advance propagates
  its blocking verdict class and no result is interpreted.
* The raw ``WalkForwardWindow`` evidence is canonically bound (finite numbers only) and the validator result is
  recomputed on every reassembly; a copied supportive summary can never override it. ``supportive=False`` is valid
  negative evidence (READY + FAIL).
* Regime evidence is not available: ``regime_split_report`` is the digest-bound ``regime_evidence_unavailable``.
* A READY EF-6 claims ``preregistration_sealed``; ``performance_data_consumed`` is True exactly when the primary
  variant was interpreted. Supportive OOS evidence is process evidence only: no edge, profitability, paper admission,
  readiness or capital claim, and EF-7 authority is untouched.
* One assembly path serves the builder and verifier reassembly; ``verify_edge_walk_forward_oos_evidence`` is total.
  Paper-only, deterministic, no IO/clock/network.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EDGE_PERMANENT_NON_CLAIM_FLAGS,
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_gate_milestone_claims,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeAdmittedChain,
    EdgeEvaluationAssumption,
    EdgeEvaluationAssumptionKind,
    EdgeLeakageBiasEvidence,
    canonical_edge_evaluation_assumptions,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    reprove_edge_admitted_chain,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.walk_forward import (
    WalkForwardValidationResult,
    WalkForwardWindow,
    WalkForwardWindowResult,
    validate_walk_forward,
)

_SCHEMA_VERSION = "edge-walk-forward-oos-evidence.v1"
_GATE_ID = "EF-6"
_PREDECESSOR_GATE_ID = "EF-5"
_REASON_PREFIX = "edge_walk_forward_oos_evidence"
_SELF_DIGEST_FIELD = "evaluation_digest"
_PERMANENT_FLAG_NAMES = frozenset(name for name, _ in EDGE_PERMANENT_NON_CLAIM_FLAGS)
_WINDOW_METRIC_FIELDS = (
    "in_sample_sharpe",
    "out_of_sample_sharpe",
    "oos_expectancy",
    "in_sample_hit_rate",
    "out_of_sample_hit_rate",
    "in_sample_max_drawdown",
    "oos_max_drawdown",
    "oos_profit_factor",
)
_WINDOW_COUNT_FIELDS = ("trade_count", "evidence_count")


class EdgeWalkForwardOOSEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class EdgeVariantWindowResult:
    """One walk-forward window result of one preregistered variant, bound to that variant's ledger digest."""

    variant_id: str
    variant_registration_digest: str
    window: WalkForwardWindow


@dataclass(frozen=True)
class EdgeWalkForwardOOSEvidence:
    """Immutable, digest-bound EF-6 walk-forward/OOS evidence. PAPER ONLY; process evidence, never an edge claim."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    evaluation_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    source_packet_digest: str
    admission_digest: str
    candidate_strategy_id: str
    strategy_id: str
    primary_variant_id: str
    multiple_testing_count: int
    variant_ledger_digest: str
    window_schedule_digest: str
    evaluation_assumptions_digest: str
    approved_min_oos_window_count: int | None
    evaluation_assumptions: tuple[EdgeEvaluationAssumption, ...]
    window_results: tuple[EdgeVariantWindowResult, ...]
    walk_forward_result: WalkForwardValidationResult | None
    regime_split_report: str
    regime_label_binding_status: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    evaluation_digest: str
    preregistration_sealed: bool
    performance_data_consumed: bool
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    kill_criteria_sealed: bool = False
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


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeWalkForwardOOSEvidenceError:
    return EdgeWalkForwardOOSEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _is_finite_number(value: object) -> bool:
    return type(value) in (int, float) and value - value == 0  # type: ignore[operator]


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


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _canonical_assumptions(values: object) -> tuple[EdgeEvaluationAssumption, ...]:
    try:
        return canonical_edge_evaluation_assumptions(values)
    except EdgeArtifactError as exc:
        raise _fail("evaluation_assumptions_invalid") from exc


def _canonical_window_results(values: object) -> tuple[EdgeVariantWindowResult, ...]:
    if type(values) not in (tuple, list):
        raise _fail("window_results_malformed")
    canonical: dict[tuple[str, str], EdgeVariantWindowResult] = {}
    for item in values:  # type: ignore[union-attr]
        if type(item) is not EdgeVariantWindowResult:
            raise _fail("window_result_malformed")
        variant_id = _require_token(item.variant_id, "window_result_variant_id")
        if not edge_is_hex64(item.variant_registration_digest):
            raise _fail("window_result_variant_registration_digest_invalid")
        window = item.window
        if type(window) is not WalkForwardWindow:
            raise _fail("window_result_window_malformed")
        window_id = _require_token(window.window_id, "window_result_window_id")
        for name in _WINDOW_METRIC_FIELDS:
            if not _is_finite_number(getattr(window, name)):
                raise _fail(f"window_result_metric_invalid:{name}")
        for name in _WINDOW_COUNT_FIELDS:
            if type(getattr(window, name)) is not int:
                raise _fail(f"window_result_count_invalid:{name}")
        key = (variant_id, window_id)
        if key in canonical:
            raise _fail("window_result_duplicate")
        canonical[key] = EdgeVariantWindowResult(
            variant_id=variant_id,
            variant_registration_digest=item.variant_registration_digest,
            window=WalkForwardWindow(
                **{field.name: getattr(window, field.name) for field in fields(WalkForwardWindow)}
            ),
        )
    if not canonical:
        raise _fail("window_results_empty")
    return tuple(canonical[key] for key in sorted(canonical))


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


# --- back-chain authority and interpretation ---------------------------------------------------------------------------


def _chain_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], EdgeLeakageBiasEvidence | None, EdgeAdmittedChain | None]:
    ledger = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_leakage_bias_evidence(ledger)
    if not verification.intact:
        return [f"ledger_integrity_failure:{code}" for code in verification.reason_codes], None, None
    if verification.recomputed_digest != binding.expected_digest:
        return ["ledger_digest_mismatch"], None, None
    if ledger.correlation_id != correlation_id:
        return ["ledger_correlation_mismatch"], None, None
    if ledger.status is not EdgeEvidenceStatus.READY or ledger.preregistration_sealed is not True:
        return ["ledger_rejected"], None, None
    if ledger.root_intake_digest != root_intake_digest:
        return ["chain_splice_root_intake_mismatch"], None, None
    chain_codes, chain = reprove_edge_admitted_chain(
        ledger.predecessor_binding, root_intake_digest=root_intake_digest, correlation_id=correlation_id
    )
    if chain is None:
        return list(chain_codes), None, None
    if ledger.predecessor_digest != chain.admission.admission_digest:
        return ["chain_splice_admission_mismatch"], None, None
    return [], ledger, chain


def _predecessor_reasons(ledger: EdgeLeakageBiasEvidence) -> tuple[list[str], list[str], list[str]]:
    code = [_reason(f"predecessor_not_advanced:{ledger.gate_verdict.value}")]
    if ledger.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        return [], code, []
    if ledger.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        return [], [], code
    return code, [], []


def _interpret(
    ledger: EdgeLeakageBiasEvidence,
    assumptions: Sequence[EdgeEvaluationAssumption],
    results: Sequence[EdgeVariantWindowResult],
) -> tuple[list[str], WalkForwardValidationResult | None]:
    """Registered-only interpretation of a sealed, advancing ledger. Only the primary variant is interpreted."""

    fail: list[str] = []
    if [_to_payload(item) for item in assumptions] != [_to_payload(item) for item in ledger.evaluation_assumptions]:
        fail.append(_reason("evaluation_assumptions_mismatch"))
    entries = {entry.variant_id: entry for entry in ledger.ledger_entries}
    schedule = [window.window_id for window in ledger.windows]
    by_key: dict[tuple[str, str], EdgeVariantWindowResult] = {}
    for result in results:
        variant_id, window_id = result.variant_id, result.window.window_id
        entry = entries.get(variant_id)
        if entry is None:
            fail.append(_reason(f"unregistered_variant_result:{variant_id}"))
        elif window_id not in schedule:
            fail.append(_reason(f"unregistered_window_result:{variant_id}:{window_id}"))
        else:
            by_key[(variant_id, window_id)] = result
            if result.variant_registration_digest != entry.variant_registration_digest:
                fail.append(_reason(f"variant_registration_digest_mismatch:{variant_id}:{window_id}"))
    fail.extend(
        _reason(f"variant_window_result_missing:{variant_id}:{window_id}")
        for variant_id in sorted(entries)
        for window_id in schedule
        if (variant_id, window_id) not in by_key
    )
    if ledger.approved_min_oos_window_count is None:
        fail.append(_reason("approved_min_oos_window_count_unavailable"))
        return fail, None
    primary_windows = [
        by_key[(ledger.primary_variant_id, window_id)].window
        for window_id in schedule
        if (ledger.primary_variant_id, window_id) in by_key
    ]
    walk_forward = validate_walk_forward(primary_windows, min_oos_windows=ledger.approved_min_oos_window_count)
    if not walk_forward.supportive:
        fail.append(_reason("walk_forward_not_supportive"))
        fail.extend(_reason(f"walk_forward:{code}") for code in walk_forward.rejection_reasons)
    return fail, walk_forward


# --- EF-6 evidence ----------------------------------------------------------------------------------------------------


def _assemble_evaluation(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    evaluation_id: object,
    correlation_id: object,
    evaluation_assumptions: object,
    window_results: object,
) -> EdgeWalkForwardOOSEvidence:
    """The one EF-6 assembly path, shared by the builder and verifier reassembly."""

    ledger_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOOSEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )
    if not edge_is_hex64(root_intake_digest):
        raise _fail("root_intake_digest_invalid")
    evaluation_id = _require_text(evaluation_id, "evaluation_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    assumptions = _canonical_assumptions(evaluation_assumptions)
    results = _canonical_window_results(window_results)

    chain_codes, ledger, chain = _chain_authority(
        ledger_binding,  # type: ignore[arg-type]
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        correlation_id=correlation_id,
    )
    integrity = _sorted_unique([_reason(code) for code in chain_codes])
    walk_forward: WalkForwardValidationResult | None = None
    if integrity or ledger is None or chain is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        if ledger.advances is True:
            fail, walk_forward = _interpret(ledger, assumptions, results)
            needs_external: list[str] = []
            needs_governance: list[str] = []
        else:
            fail, needs_external, needs_governance = _predecessor_reasons(ledger)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = EdgeWalkForwardOOSEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        evaluation_id=evaluation_id,
        correlation_id=correlation_id,
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        predecessor_binding=ledger_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=ledger_binding.expected_digest,  # type: ignore[union-attr]
        source_packet_digest="" if chain is None else chain.admission.predecessor_digest,
        admission_digest="" if chain is None else chain.admission.admission_digest,
        candidate_strategy_id="" if ledger is None else ledger.candidate_strategy_id,
        strategy_id="" if ledger is None else ledger.strategy_id,
        primary_variant_id="" if ledger is None else ledger.primary_variant_id,
        multiple_testing_count=0 if ledger is None else ledger.multiple_testing_count,
        variant_ledger_digest="" if ledger is None else ledger.variant_ledger_digest,
        window_schedule_digest="" if ledger is None else ledger.window_schedule_digest,
        evaluation_assumptions_digest="" if ledger is None else ledger.evaluation_assumptions_digest,
        approved_min_oos_window_count=None if ledger is None else ledger.approved_min_oos_window_count,
        evaluation_assumptions=assumptions,
        window_results=results,
        walk_forward_result=walk_forward,
        regime_split_report=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        evaluation_digest="",
        **edge_gate_milestone_claims(
            _GATE_ID,
            preregistration_sealed=status is EdgeEvidenceStatus.READY,
            performance_data_consumed=walk_forward is not None,
        ),
    )
    return replace(seed, evaluation_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_walk_forward_oos_evidence(
    predecessor: EdgeLeakageBiasEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    evaluation_id: str,
    correlation_id: str,
    evaluation_assumptions: Sequence[EdgeEvaluationAssumption],
    window_results: Sequence[EdgeVariantWindowResult],
) -> EdgeWalkForwardOOSEvidence:
    """Build deterministic EF-6 walk-forward/OOS evidence over a sealed EF-5 preregistration ledger.

    Malformed caller input, non-finite window metrics or a non-serializable upstream object raise
    ``EdgeWalkForwardOOSEvidenceError``. An authentic chain that fails re-proof at any level (or a splice) yields
    ``REJECTED``/``NOT_EVALUATED``. A READY ledger that does not advance propagates its blocking verdict class without
    interpreting any result. Otherwise the evidence is ``READY`` with ``FAIL`` (registration, completeness,
    assumption or walk-forward failure) or ``PASS``.
    """

    if type(predecessor) is not EdgeLeakageBiasEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_leakage_bias_evidence_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    ledger_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOOSEvidenceError,
        code=_reason("predecessor"),
    )
    return _assemble_evaluation(
        predecessor_binding=ledger_binding,
        root_intake_digest=expected_root_intake_digest,
        evaluation_id=evaluation_id,
        correlation_id=correlation_id,
        evaluation_assumptions=evaluation_assumptions,
        window_results=window_results,
    )


def edge_walk_forward_oos_evidence_to_dict(evidence: EdgeWalkForwardOOSEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-6 evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_walk_forward_oos_evidence_digest(evidence: EdgeWalkForwardOOSEvidence) -> str:
    """Recompute the canonical EF-6 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict payload conversion ---------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_number(value: object) -> object:
    if not _is_finite_number(value):
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


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOOSEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )


_WINDOW_CONVERTERS: dict[str, Callable[[object], object]] = {
    **dict.fromkeys(_WINDOW_METRIC_FIELDS, _as_number),
    **dict.fromkeys(_WINDOW_COUNT_FIELDS, _as_int),
}
_WINDOW_RESULT_SUMMARY_CONVERTERS: dict[str, Callable[[object], object]] = {
    **dict.fromkeys(
        ("valid", "supportive", "expectancy_supportive", "drawdown_safe", "profit_factor_supportive"), _as_bool
    ),
    "rejection_reasons": _as_str_tuple,
}
_WALK_FORWARD_CONVERTERS: dict[str, Callable[[object], object]] = {
    "supportive": _as_bool,
    **dict.fromkeys(
        (
            "total_window_count",
            "valid_oos_window_count",
            "supportive_window_count",
            "positive_expectancy_window_count",
            "required_positive_expectancy_window_count",
            "drawdown_safe_window_count",
            "positive_profit_factor_window_count",
            "required_positive_profit_factor_window_count",
        ),
        _as_int,
    ),
    "rejection_reasons": _as_str_tuple,
    "window_results": _as_records(WalkForwardWindowResult, _WINDOW_RESULT_SUMMARY_CONVERTERS),
}


def _as_window_result(value: object) -> object:
    return _parse_exact(
        EdgeVariantWindowResult,
        value,
        {"window": lambda window: _parse_exact(WalkForwardWindow, window, _WINDOW_CONVERTERS)},
    )


def _as_window_results(value: object) -> tuple[object, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_window_result(entry) for entry in value)


def _as_walk_forward_result(value: object) -> object:
    return None if value is None else _parse_exact(WalkForwardValidationResult, value, _WALK_FORWARD_CONVERTERS)


_EVALUATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "multiple_testing_count": _as_int,
    "approved_min_oos_window_count": _as_optional_int,
    "evaluation_assumptions": _as_records(
        EdgeEvaluationAssumption,
        {
            "kind": _as_enum(EdgeEvaluationAssumptionKind),
            "model_digest": lambda digest: None if digest is None else _as_str(digest),
        },
    ),
    "window_results": _as_window_results,
    "walk_forward_result": _as_walk_forward_result,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    "preregistration_sealed": _as_bool,
    "performance_data_consumed": _as_bool,
    **dict.fromkeys(_PERMANENT_FLAG_NAMES, _as_bool),
}


def edge_walk_forward_oos_evidence_from_payload(payload: object) -> EdgeWalkForwardOOSEvidence:
    """Strictly reconstruct EF-6 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_walk_forward_oos_evidence`` on the result.
    """

    return _parse_exact(EdgeWalkForwardOOSEvidence, payload, _EVALUATION_CONVERTERS)  # type: ignore[return-value]


def edge_walk_forward_oos_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-6 snapshot."""

    try:
        edge_walk_forward_oos_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_evaluation(evidence: object) -> EdgeWalkForwardOOSEvidence:
    return _assemble_evaluation(
        predecessor_binding=evidence.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=evidence.root_intake_digest,  # type: ignore[attr-defined]
        evaluation_id=evidence.evaluation_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        evaluation_assumptions=evidence.evaluation_assumptions,  # type: ignore[attr-defined]
        window_results=evidence.window_results,  # type: ignore[attr-defined]
    )


def verify_edge_walk_forward_oos_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-6 evidence by strict parse, full back-chain re-proof and recomputation of the validator result.

    READY and builder-produced REJECTED artifacts alike must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeWalkForwardOOSEvidence,
        to_payload=_to_payload,
        parse_payload=edge_walk_forward_oos_evidence_from_payload,
        reassemble=_reassemble_evaluation,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EdgeVariantWindowResult",
    "EdgeWalkForwardOOSEvidence",
    "EdgeWalkForwardOOSEvidenceError",
    "build_edge_walk_forward_oos_evidence",
    "edge_walk_forward_oos_evidence_digest",
    "edge_walk_forward_oos_evidence_from_payload",
    "edge_walk_forward_oos_evidence_payload_is_well_formed",
    "edge_walk_forward_oos_evidence_to_dict",
    "verify_edge_walk_forward_oos_evidence",
]
