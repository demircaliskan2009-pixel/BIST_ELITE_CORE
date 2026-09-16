"""Edge Factory EF-4: deterministic StrategySpec admission over an authenticated EF-3 manifest and EF-2 root.

EF-4 binds one accepted ``crypto_core.strategy.spec.StrategySpec`` to the candidate chain: the spec must name the
intake candidate and edge family, trade only instruments inside the EF-3 manifest coverage, consume only data
requirements the manifest provides, and bind its kill-switch triggers to the admitted kill criteria. The admitted kill
criteria may only STRENGTHEN the EF-2 draft (additive superset; no removal or modification) and stay UNSEALED.

Trust model (shared kernel ``edge_artifact_core``):

* Dual anchor. The EF-3 predecessor is a required ``EdgeAuthorityBinding`` re-proven through
  ``verify_edge_source_packet_evidence`` against the caller's predecessor anchor. The EF-2 root anchor is an explicit
  caller field; the root nested in the predecessor is independently re-proven through
  ``verify_edge_idea_intake_evidence`` and must equal that anchor, so a predecessor spliced onto another root is a
  ``chain_splice_root_intake_mismatch`` rejection.
* The StrategySpec is a required ``EdgeAuthorityBinding`` over the public ``strategy_spec_to_dict`` snapshot. Assembly
  re-proves it through the public ``validate_strategy_spec`` (accepted), canonical re-serialization, the public
  ``strategy_spec_digest`` against the caller anchor and the Edge Factory scope policy. Every spec summary field is
  derived from the re-proven spec, never copied from the caller.
* Governance approval of the admitted criteria is the optional kill-criteria policy binding, evaluated by the one
  spine rule ``evaluate_edge_kill_criteria_policy_binding``.
* An authentic authority that fails re-proof, a correlation splice or an authentic REJECTED predecessor receipt
  yields ``REJECTED``/``NOT_EVALUATED``; a malformed or non-serializable caller object is a construction error.
* ``expected_regime`` is recorded verbatim under the digest-bound pending pattern; no RF label is claimed.
* One assembly path serves the builder and verifier reassembly; ``verify_edge_strategy_spec_admission`` is total.
  Paper-only, deterministic, no IO/clock/network; admission proves process survival only, never an edge.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, strategy_spec_to_dict, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
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
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EdgeIdeaIntakeEvidence,
    EdgeKillCriteriaPolicy,
    EdgeKillCriterion,
    build_edge_kill_criteria_policy_binding,
    canonical_edge_kill_criteria,
    edge_idea_intake_evidence_from_payload,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criteria_policy_payload_is_well_formed,
    edge_kill_criterion_to_dict,
    evaluate_edge_kill_criteria_policy_binding,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_SCHEMA_VERSION = "edge-strategy-spec-admission.v2"
_GATE_ID = "EF-4"
_PREDECESSOR_GATE_ID = "EF-3"
_REASON_PREFIX = "edge_strategy_spec_admission"
_SELF_DIGEST_FIELD = "admission_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "SUPERSET_STRENGTHENED_UNSEALED"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
_SPEC_FIELDS = frozenset(field.name for field in fields(StrategySpec))
_SPEC_LIST_FIELDS = frozenset(
    {
        "instrument_universe",
        "venue_assumptions",
        "entry_conditions",
        "exit_conditions",
        "invalidation_conditions",
        "failure_modes",
        "kill_switch_triggers",
        "telemetry_fields",
        "promotion_requirements",
    }
)
_SPEC_MAPPING_FIELDS = frozenset({"risk_caps", "data_requirements", "feature_requirements"})


class EdgeStrategySpecAdmissionError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


@dataclass(frozen=True)
class EdgeStrategySpecAdmissionEvidence:
    """Immutable, digest-bound EF-4 StrategySpec admission. PAPER ONLY; never admits a candidate to paper trading."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    admission_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    candidate_strategy_id: str
    edge_family: str
    packet_instrument_coverage: tuple[str, ...]
    packet_data_requirement_keys: tuple[str, ...]
    strategy_spec_binding: EdgeAuthorityBinding
    strategy_spec_digest: str
    strategy_id: str
    strategy_version: str
    strategy_family: str
    spec_edge_family: str
    instrument_universe: tuple[str, ...]
    market_type: str
    timeframe: str
    spec_data_requirement_keys: tuple[str, ...]
    spec_kill_switch_triggers: tuple[str, ...]
    fee_model_requirement: str
    slippage_model_requirement: str
    funding_sensitivity: str
    latency_sensitivity: str
    declared_expected_regime: str
    regime_label_binding_status: str
    regime_evidence_status: str
    root_kill_criteria_digest: str
    admitted_kill_criteria: tuple[EdgeKillCriterion, ...]
    admitted_kill_criteria_digest: str
    added_kill_criterion_ids: tuple[str, ...]
    kill_criteria_lifecycle_stage: str
    kill_criteria_combination_policy: str
    kill_criteria_policy_binding: EdgeAuthorityBinding | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    admission_digest: str
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


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeStrategySpecAdmissionError:
    return EdgeStrategySpecAdmissionError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value  # type: ignore[return-value]


def _canonical_admitted_criteria(criteria: object) -> tuple[EdgeKillCriterion, ...]:
    try:
        return canonical_edge_kill_criteria(criteria)
    except EdgeArtifactError as exc:
        raise _fail("admitted_kill_criteria_invalid") from exc


# --- strict field conversion ----------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
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


def _as_kill_criteria(value: object) -> tuple[EdgeKillCriterion, ...]:
    try:
        return edge_kill_criteria_from_payload(value)
    except EdgeArtifactError as exc:
        raise _fail("payload_field_malformed") from exc


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) is EdgeKillCriterion:
        return edge_kill_criterion_to_dict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


# --- upstream authorities -------------------------------------------------------------------------------------------


def _strategy_spec_snapshot_is_well_formed(snapshot: object) -> bool:
    """Binding shape predicate: the exact structure ``strategy_spec_to_dict`` produces."""

    if type(snapshot) is not dict or set(snapshot) != _SPEC_FIELDS:
        return False
    for name, value in snapshot.items():
        if name in _SPEC_LIST_FIELDS:
            valid = type(value) is list and all(type(item) is str for item in value)
        elif name in _SPEC_MAPPING_FIELDS:
            valid = type(value) is dict
        else:
            valid = type(value) is str
        if not valid:
            return False
    return True


def _snapshot_texts(node: object) -> Iterator[str]:
    if type(node) is dict:
        for key, value in node.items():
            yield key
            yield from _snapshot_texts(value)
    elif type(node) is list:
        for item in node:
            yield from _snapshot_texts(item)
    elif type(node) is str:
        yield node


def _strategy_spec_authority(binding: EdgeAuthorityBinding) -> tuple[list[str], StrategySpec | None]:
    snapshot = edge_authority_binding_snapshot(binding)
    try:
        result = validate_strategy_spec(snapshot)
    except Exception:  # noqa: BLE001 - the public validator refusing authenticated fields is a truthful rejection
        result = None
    if result is None or result.accepted is not True or type(result.spec) is not StrategySpec:
        codes = [_reason("strategy_spec_not_accepted")]
        if edge_sha256_text(edge_canonical_json(snapshot)) != binding.expected_digest:
            codes.append(_reason("strategy_spec_digest_mismatch"))
        return codes, None
    spec = result.spec
    codes = []
    if strategy_spec_to_dict(spec) != snapshot:
        codes.append(_reason("strategy_spec_noncanonical"))
    if strategy_spec_digest(spec) != binding.expected_digest:
        codes.append(_reason("strategy_spec_digest_mismatch"))
    if any(edge_scope_violation(text) is not None for text in _snapshot_texts(snapshot)):
        codes.append(_reason("strategy_spec_scope_violation"))
    return codes, spec


def _chain_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], EdgeSourcePacketEvidence | None, EdgeIdeaIntakeEvidence | None]:
    predecessor = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_source_packet_evidence(predecessor)
    if not verification.intact:
        return [_reason(f"predecessor_integrity_failure:{code}") for code in verification.reason_codes], None, None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("predecessor_digest_mismatch")], None, None
    if predecessor.correlation_id != correlation_id:
        return [_reason("predecessor_correlation_mismatch")], None, None
    if predecessor.status is not EdgeEvidenceStatus.READY:
        return [_reason("predecessor_rejected")], None, None
    root = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(predecessor.root_intake_binding))
    root_verification = verify_edge_idea_intake_evidence(root)
    if not root_verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in root_verification.reason_codes], None, None
    if (
        root_verification.recomputed_digest != root_intake_digest
        or predecessor.root_intake_digest != root_intake_digest
    ):
        return [_reason("chain_splice_root_intake_mismatch")], None, None
    return [], predecessor, root


def _kill_criteria_reasons(
    draft: Sequence[EdgeKillCriterion], admitted: Sequence[EdgeKillCriterion]
) -> tuple[list[str], list[str]]:
    admitted_by_id = {item.criterion_id: item for item in admitted}
    draft_ids = {item.criterion_id for item in draft}
    fail: list[str] = []
    for item in draft:
        carried = admitted_by_id.get(item.criterion_id)
        if carried is None:
            fail.append(_reason(f"kill_criterion_removed:{item.criterion_id}"))
        elif edge_kill_criterion_to_dict(carried) != edge_kill_criterion_to_dict(item):
            fail.append(_reason(f"kill_criterion_modified:{item.criterion_id}"))
    needs_governance = [
        _reason(f"kill_criterion_threshold_pending_governance:{item.criterion_id}")
        for item in admitted
        if item.criterion_id not in draft_ids and item.threshold is None
    ]
    return fail, needs_governance


def _spec_reasons(
    spec: StrategySpec,
    root: EdgeIdeaIntakeEvidence,
    predecessor: EdgeSourcePacketEvidence,
    admitted: Sequence[EdgeKillCriterion],
) -> list[str]:
    fail: list[str] = []
    if predecessor.advances is not True:
        fail.append(_reason("predecessor_not_advanced"))
    if spec.strategy_id != root.candidate_strategy_id:
        fail.append(_reason("candidate_strategy_id_mismatch"))
    if spec.edge_family != root.edge_family:
        fail.append(_reason("edge_family_mismatch"))
    fail.extend(
        _reason(f"instrument_outside_packet_coverage:{instrument}")
        for instrument in spec.instrument_universe
        if instrument not in predecessor.instrument_coverage
    )
    packet_keys = {record.data_requirement_key for record in predecessor.series}
    fail.extend(
        _reason(f"spec_data_requirement_not_in_packet:{key}")
        for key in spec.data_requirements
        if key not in _DATA_REQUIREMENT_KEY_VALUES or key not in packet_keys
    )
    if set(spec.kill_switch_triggers) != {item.criterion_id for item in admitted}:
        fail.append(_reason("spec_kill_switch_triggers_not_bound_to_kill_criteria"))
    return fail


# --- EF-4 admission -------------------------------------------------------------------------------------------------


def _assemble_admission(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    strategy_spec_binding: object,
    kill_criteria_policy_binding: object,
    admission_id: object,
    correlation_id: object,
    admitted_kill_criteria: object,
) -> EdgeStrategySpecAdmissionEvidence:
    """The one EF-4 assembly path, shared by the builder and verifier reassembly."""

    chain_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("predecessor"),
        optional=False,
    )
    spec_binding = require_edge_authority_binding(
        strategy_spec_binding,
        shape=_strategy_spec_snapshot_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("strategy_spec"),
        optional=False,
    )
    policy_binding = require_edge_authority_binding(
        kill_criteria_policy_binding,
        shape=edge_kill_criteria_policy_payload_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("kill_criteria_policy"),
        optional=True,
    )
    if not edge_is_hex64(root_intake_digest):
        raise _fail("root_intake_digest_invalid")
    admission_id = _require_text(admission_id, "admission_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    admitted = _canonical_admitted_criteria(admitted_kill_criteria)
    admitted_digest = edge_kill_criteria_digest(admitted)

    chain_codes, predecessor, root = _chain_authority(
        chain_binding,  # type: ignore[arg-type]
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        correlation_id=correlation_id,
    )
    spec_codes, spec = _strategy_spec_authority(spec_binding)  # type: ignore[arg-type]
    policy_integrity, policy_needs = evaluate_edge_kill_criteria_policy_binding(
        policy_binding, correlation_id=correlation_id, kill_criteria_digest=admitted_digest
    )
    integrity = _sorted_unique(
        [*chain_codes, *spec_codes, *(_reason(f"kill_criteria_{code}") for code in policy_integrity)]
    )

    if integrity or predecessor is None or root is None or spec is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        criteria_fail, needs_governance = _kill_criteria_reasons(root.kill_criteria_draft, admitted)
        fail = _spec_reasons(spec, root, predecessor, admitted) + criteria_fail
        needs_governance.extend(_reason(f"kill_criteria_{code}") for code in policy_needs)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, (), needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_governance)

    draft_ids = set() if root is None else {item.criterion_id for item in root.kill_criteria_draft}
    seed = EdgeStrategySpecAdmissionEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        admission_id=admission_id,
        correlation_id=correlation_id,
        root_intake_digest=root_intake_digest,  # type: ignore[arg-type]
        predecessor_binding=chain_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=chain_binding.expected_digest,  # type: ignore[union-attr]
        candidate_strategy_id="" if root is None else root.candidate_strategy_id,
        edge_family="" if root is None else root.edge_family,
        packet_instrument_coverage=() if predecessor is None else predecessor.instrument_coverage,
        packet_data_requirement_keys=()
        if predecessor is None
        else _sorted_unique([record.data_requirement_key for record in predecessor.series]),
        strategy_spec_binding=spec_binding,  # type: ignore[arg-type]
        strategy_spec_digest=spec_binding.expected_digest,  # type: ignore[union-attr]
        strategy_id="" if spec is None else spec.strategy_id,
        strategy_version="" if spec is None else spec.strategy_version,
        strategy_family="" if spec is None else spec.strategy_family,
        spec_edge_family="" if spec is None else spec.edge_family,
        instrument_universe=() if spec is None else spec.instrument_universe,
        market_type="" if spec is None else spec.market_type.value,
        timeframe="" if spec is None else spec.timeframe,
        spec_data_requirement_keys=() if spec is None else tuple(sorted(spec.data_requirements)),
        spec_kill_switch_triggers=() if spec is None else spec.kill_switch_triggers,
        fee_model_requirement="" if spec is None else spec.fee_model_requirement,
        slippage_model_requirement="" if spec is None else spec.slippage_model_requirement,
        funding_sensitivity="" if spec is None else spec.funding_sensitivity,
        latency_sensitivity="" if spec is None else spec.latency_sensitivity,
        declared_expected_regime="" if spec is None else spec.expected_regime,
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        root_kill_criteria_digest="" if root is None else root.kill_criteria_digest,
        admitted_kill_criteria=admitted,
        admitted_kill_criteria_digest=admitted_digest,
        added_kill_criterion_ids=()
        if root is None
        else tuple(item.criterion_id for item in admitted if item.criterion_id not in draft_ids),
        kill_criteria_lifecycle_stage=_KILL_CRITERIA_LIFECYCLE_STAGE,
        kill_criteria_combination_policy=_KILL_CRITERIA_COMBINATION_POLICY,
        kill_criteria_policy_binding=policy_binding,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        admission_digest="",
    )
    return replace(seed, admission_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_strategy_spec_admission(
    predecessor: EdgeSourcePacketEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    strategy_spec: StrategySpec,
    expected_strategy_spec_digest: str,
    admission_id: str,
    correlation_id: str,
    admitted_kill_criteria: Sequence[EdgeKillCriterion],
    kill_criteria_policy: EdgeKillCriteriaPolicy | None = None,
    expected_kill_criteria_policy_digest: str | None = None,
) -> EdgeStrategySpecAdmissionEvidence:
    """Build deterministic EF-4 StrategySpec admission evidence over an EF-3 manifest and its EF-2 root.

    Malformed caller input or a non-serializable upstream object raises ``EdgeStrategySpecAdmissionError``. An
    authentic predecessor, root, spec or policy that fails re-proof, a chain splice or a REJECTED predecessor yields
    ``REJECTED``/``NOT_EVALUATED``. Otherwise the admission is ``READY`` with ``FAIL``, ``NEEDS_GOVERNANCE_APPROVAL``
    (missing, non-READY or non-matching policy, or a pending added threshold) or ``PASS``.
    """

    if type(predecessor) is not EdgeSourcePacketEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_source_packet_evidence_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    chain_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("predecessor"),
    )
    if type(strategy_spec) is not StrategySpec:
        raise _fail("strategy_spec_malformed")
    try:
        spec_payload = strategy_spec_to_dict(strategy_spec)
    except Exception as exc:  # noqa: BLE001 - a hollow spec object is a construction error, never a receipt
        raise _fail("strategy_spec_not_serializable") from exc
    spec_binding = build_edge_authority_binding(
        snapshot_payload=spec_payload,
        expected_digest=expected_strategy_spec_digest,
        shape=_strategy_spec_snapshot_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("strategy_spec"),
    )
    policy_binding = build_edge_kill_criteria_policy_binding(
        kill_criteria_policy,
        expected_kill_criteria_policy_digest,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("kill_criteria_policy"),
    )
    return _assemble_admission(
        predecessor_binding=chain_binding,
        root_intake_digest=expected_root_intake_digest,
        strategy_spec_binding=spec_binding,
        kill_criteria_policy_binding=policy_binding,
        admission_id=admission_id,
        correlation_id=correlation_id,
        admitted_kill_criteria=admitted_kill_criteria,
    )


def edge_strategy_spec_admission_to_dict(evidence: EdgeStrategySpecAdmissionEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-4 admission evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_strategy_spec_admission_digest(evidence: EdgeStrategySpecAdmissionEvidence) -> str:
    """Recompute the canonical EF-4 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_source_packet_evidence_payload_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("predecessor"),
        optional=False,
    )


def _parse_strategy_spec_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=_strategy_spec_snapshot_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("strategy_spec"),
        optional=False,
    )


def _parse_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_kill_criteria_policy_payload_is_well_formed,
        error=EdgeStrategySpecAdmissionError,
        code=_reason("kill_criteria_policy"),
        optional=True,
    )


_ADMISSION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "packet_instrument_coverage": _as_str_tuple,
    "packet_data_requirement_keys": _as_str_tuple,
    "strategy_spec_binding": _parse_strategy_spec_binding,
    "instrument_universe": _as_str_tuple,
    "spec_data_requirement_keys": _as_str_tuple,
    "spec_kill_switch_triggers": _as_str_tuple,
    "admitted_kill_criteria": _as_kill_criteria,
    "added_kill_criterion_ids": _as_str_tuple,
    "kill_criteria_policy_binding": _parse_policy_binding,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_strategy_spec_admission_from_payload(payload: object) -> EdgeStrategySpecAdmissionEvidence:
    """Strictly reconstruct EF-4 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_strategy_spec_admission`` on the result.
    """

    return _parse_exact(EdgeStrategySpecAdmissionEvidence, payload, _ADMISSION_CONVERTERS)  # type: ignore[return-value]


def edge_strategy_spec_admission_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-4 predecessor snapshot."""

    try:
        edge_strategy_spec_admission_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_admission(evidence: object) -> EdgeStrategySpecAdmissionEvidence:
    return _assemble_admission(
        predecessor_binding=evidence.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=evidence.root_intake_digest,  # type: ignore[attr-defined]
        strategy_spec_binding=evidence.strategy_spec_binding,  # type: ignore[attr-defined]
        kill_criteria_policy_binding=evidence.kill_criteria_policy_binding,  # type: ignore[attr-defined]
        admission_id=evidence.admission_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        admitted_kill_criteria=evidence.admitted_kill_criteria,  # type: ignore[attr-defined]
    )


def verify_edge_strategy_spec_admission(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-4 evidence by strict parse and reassembly from its carried bindings, anchors and declarations.

    READY and builder-produced REJECTED artifacts alike must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeStrategySpecAdmissionEvidence,
        to_payload=_to_payload,
        parse_payload=edge_strategy_spec_admission_from_payload,
        reassemble=_reassemble_admission,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EdgeStrategySpecAdmissionError",
    "EdgeStrategySpecAdmissionEvidence",
    "build_edge_strategy_spec_admission",
    "edge_strategy_spec_admission_digest",
    "edge_strategy_spec_admission_from_payload",
    "edge_strategy_spec_admission_payload_is_well_formed",
    "edge_strategy_spec_admission_to_dict",
    "verify_edge_strategy_spec_admission",
]
