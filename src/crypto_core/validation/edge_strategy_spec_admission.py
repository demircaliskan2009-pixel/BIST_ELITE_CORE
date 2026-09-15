"""Edge Factory EF-4: deterministic edge StrategySpec admission, closing the candidate admission spine.

EF-4 is the third gate of ``docs/crypto_core/edge_factory_design.md``. It binds an independently validated
``crypto_core.strategy.spec.StrategySpec`` to the EF-3 PIT data manifest (immediate predecessor) and, through that
manifest's authenticated root snapshot, to the EF-2 intake (root anchor).

Contract:

* Authority is carried, never copied. The artifact commits one canonical EF-3 snapshot and one canonical StrategySpec
  snapshot (plus, when supplied, one canonical ``EdgeKillCriteriaPolicy`` snapshot). The EF-3 predecessor is strictly
  reconstructed, re-proven by ``verify_edge_source_packet_evidence``, matched to the caller predecessor anchor, and must
  be READY + PASS. Its nested EF-2 root snapshot is strictly reconstructed, re-proven by
  ``verify_edge_idea_intake_evidence``, and independently matched to the caller root anchor (dual anchor: a packet
  from another root is a rejected splice), and must be READY + PASS. Every artifact carries the same correlation id.
* StrategySpec authority stays in ``strategy/spec.py``: the snapshot is parsed (NaN and Infinity never parse), its
  digest matched to the caller anchor, fully accepted by ``validate_strategy_spec``, and the validated spec must
  re-serialize to the exact snapshot, so a forged or non-canonical spec is REJECTED. Spec text is also scanned with the
  single Edge Factory scope policy, which the spec validator applies only to keys.
* Semantic admission (READY + FAIL when violated): ``strategy_id`` equals the root candidate strategy id and
  ``edge_family`` the root edge family; every ``instrument_universe`` member is inside the predecessor coverage; every
  spec data-requirement key, normalized as ``validation/pit_parity.py`` normalizes it, is a predecessor series key.
* Kill criteria may only strengthen. Every root draft criterion must be present and identical: a removal, or a changed
  (relaxed or tightened) threshold, comparator, metric or basis FAILs. New criteria may be added; under the
  "any single criterion kills" combination an addition can only make the kill set stricter. The spec's
  ``kill_switch_triggers`` must be exactly the admitted criterion ids. Governance approval for the admitted set comes
  only from a re-proven, anchored, READY ``EdgeKillCriteriaPolicy`` for this correlation and exactly this set; anything
  else is ``NEEDS_GOVERNANCE_APPROVAL``. Criteria are not sealed here (EF-7 seals).
* Every summary field (root identity, predecessor coverage and series keys, spec identity, data keys, triggers, cost
  requirements, regime) is derived from the authenticated objects. ``verify_edge_strategy_spec_admission`` strictly
  parses the carried artifact, re-runs the one assembly path and requires field-for-field equality, for READY and
  REJECTED artifacts alike.
* Fee, funding, slippage and latency requirements are recorded verbatim from the spec; no current venue fact is
  consumed. The spec's ``expected_regime`` is recorded with the EF-2 digest-bound pending pattern; no RF label exists.
* ``status`` (integrity) and ``gate_verdict`` (outcome) stay separate exactly as in EF-2; only READY + PASS advances.
  Paper-only, deterministic, immutable, and every structural non-claim of EF-2: admission of a specification into the
  process is never an edge, profitability, readiness, live, order or capital claim.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from dataclasses import dataclass, fields
from enum import Enum

from crypto_core.strategy.spec import (
    StrategySpec,
    canonical_strategy_spec_json,
    validate_strategy_spec,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    EdgeIdeaIntakeEvidence,
    EdgeIdeaIntakeEvidenceError,
    EdgeKillCriteriaPolicy,
    EdgeKillCriterion,
    canonical_edge_kill_criteria,
    edge_idea_intake_evidence_from_canonical_json,
    edge_kill_criteria_digest,
    edge_kill_criteria_from_payload,
    edge_kill_criteria_policy_snapshot,
    edge_kill_criterion_to_dict,
    edge_scope_violation,
    evaluate_edge_kill_criteria_policy_binding,
    require_edge_policy_binding_shape,
    resolve_edge_gate_verdict,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    edge_source_packet_evidence_from_canonical_json,
    edge_source_packet_evidence_to_dict,
    verify_edge_source_packet_evidence,
)

_SCHEMA_VERSION = "edge-strategy-spec-admission.v1"
_GATE_ID = "EF-4"
_ROOT_GATE_ID = "EF-2"
_PREDECESSOR_GATE_ID = "EF-3"
_REASON_PREFIX = "edge_strategy_spec_admission"
_SELF_DIGEST_FIELD = "admission_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "SPEC_BOUND_STRENGTHEN_ONLY"
_KILL_CRITERIA_LIFECYCLE_POLICY = "draft_criteria_preserved_exactly_additions_only.v1"
_SPEC_DATA_REQUIREMENT_KEY_NORMALIZATION = "strip_lower_as_validation_pit_parity.v1"
_COST_MODEL_BINDING = "strategy_spec_requirements_recorded_verbatim_no_venue_fact_values.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)


class EdgeStrategySpecAdmissionError(RuntimeError):
    """Raised on malformed caller input, a malformed carried artifact, or a forbidden scope token."""


@dataclass(frozen=True)
class EdgeStrategySpecAdmission:
    """Immutable, digest-bound EF-4 StrategySpec admission. PAPER ONLY; proves process survival, never an edge."""

    schema_version: str
    gate_id: str
    root_gate_id: str
    predecessor_gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    admission_id: str
    correlation_id: str
    predecessor_source_packet_snapshot_json: str
    expected_source_packet_evidence_digest: str
    verified_source_packet_evidence_digest: str
    expected_root_intake_digest: str
    verified_root_intake_digest: str
    strategy_spec_snapshot_json: str
    expected_strategy_spec_digest: str
    verified_strategy_spec_digest: str
    intake_candidate_strategy_id: str
    intake_edge_family: str
    packet_instrument_coverage: tuple[str, ...]
    packet_series_keys: tuple[str, ...]
    strategy_id: str
    strategy_version: str
    strategy_family: str
    edge_family: str
    market_type: str
    instrument_universe: tuple[str, ...]
    spec_data_requirement_keys: tuple[str, ...]
    spec_data_requirement_key_normalization: str
    spec_kill_switch_triggers: tuple[str, ...]
    fee_model_requirement: str
    funding_sensitivity: str
    slippage_model_requirement: str
    latency_sensitivity: str
    cost_model_binding: str
    expected_regime_declared: str
    regime_label_binding_status: str
    regime_evidence_status: str
    draft_kill_criteria: tuple[EdgeKillCriterion, ...]
    draft_kill_criteria_digest: str
    kill_criteria: tuple[EdgeKillCriterion, ...]
    kill_criteria_digest: str
    kill_criteria_added_ids: tuple[str, ...]
    kill_criteria_lifecycle_stage: str
    kill_criteria_lifecycle_policy: str
    kill_criteria_policy_snapshot_json: str
    expected_kill_criteria_policy_digest: str
    verified_kill_criteria_policy_digest: str
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


_ADMISSION_FIELD_KINDS: dict[str, object] = {
    "status": EdgeEvidenceStatus,
    "gate_verdict": EdgeGateVerdict,
    "advances": "bool",
    "packet_instrument_coverage": "str_tuple",
    "packet_series_keys": "str_tuple",
    "instrument_universe": "str_tuple",
    "spec_data_requirement_keys": "str_tuple",
    "spec_kill_switch_triggers": "str_tuple",
    "draft_kill_criteria": "criteria",
    "kill_criteria": "criteria",
    "kill_criteria_added_ids": "str_tuple",
    "integrity_reason_codes": "str_tuple",
    "verdict_reason_codes": "str_tuple",
    **dict.fromkeys(_FLAG_NAMES, "bool"),
}


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _is_plain_text(value: object) -> bool:
    return (
        type(value) is str
        and value != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeStrategySpecAdmissionError(_reason(f"{field_name}_invalid"))
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise EdgeStrategySpecAdmissionError(_reason(f"{violation}:{field_name}"))
    return value  # type: ignore[return-value]


def _collect_strings(value: object) -> list[str]:
    """Every string of a JSON snapshot (dict keys, values and list items), for the scope scan."""

    out: list[str] = []
    if type(value) is str:
        out.append(value)
    elif type(value) is list:
        for item in value:
            out.extend(_collect_strings(item))
    elif type(value) is dict:
        for key, item in value.items():
            out.append(key)
            out.extend(_collect_strings(item))
    return out


def _predecessor_authority(
    snapshot_json: str, expected_digest: str, correlation_id: str
) -> tuple[list[str], EdgeSourcePacketEvidence | None]:
    try:
        packet = edge_source_packet_evidence_from_canonical_json(snapshot_json)
    except Exception:  # noqa: BLE001 - an unparseable predecessor snapshot is a rejection, never a crash
        return [_reason("predecessor_source_packet_malformed_payload")], None
    verification = verify_edge_source_packet_evidence(packet)
    if not verification.intact:
        return [
            _reason(f"predecessor_source_packet_integrity_failure:{code}") for code in verification.reason_codes
        ], None
    if verification.recomputed_digest != expected_digest:
        return [_reason("predecessor_source_packet_digest_mismatch")], None
    codes: list[str] = []
    if (
        packet.status is not EdgeEvidenceStatus.READY
        or packet.gate_verdict is not EdgeGateVerdict.PASS
        or packet.advances is not True
    ):
        codes.append(_reason(f"predecessor_source_packet_not_passed:{packet.gate_verdict.value}"))
    if packet.correlation_id != correlation_id:
        codes.append(_reason("predecessor_source_packet_correlation_id_mismatch"))
    return codes, packet


def _root_authority(
    packet: EdgeSourcePacketEvidence | None, expected_root_digest: str, correlation_id: str
) -> tuple[list[str], EdgeIdeaIntakeEvidence | None]:
    """Independently re-prove the root carried inside the authenticated predecessor against the explicit root anchor."""

    if packet is None:
        return [], None
    try:
        root = edge_idea_intake_evidence_from_canonical_json(packet.root_intake_snapshot_json)
    except Exception:  # noqa: BLE001 - an unparseable nested root is a rejection, never a crash
        return [_reason("root_intake_malformed_payload")], None
    verification = verify_edge_idea_intake_evidence(root)
    if not verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in verification.reason_codes], None
    if (
        verification.recomputed_digest != expected_root_digest
        or packet.expected_root_intake_digest != expected_root_digest
    ):
        return [_reason("chain_splice_root_intake_mismatch")], None
    codes: list[str] = []
    if (
        root.status is not EdgeEvidenceStatus.READY
        or root.gate_verdict is not EdgeGateVerdict.PASS
        or root.advances is not True
    ):
        codes.append(_reason(f"root_intake_not_passed:{root.gate_verdict.value}"))
    if root.correlation_id != correlation_id:
        codes.append(_reason("root_intake_correlation_id_mismatch"))
    return codes, root


def _strategy_spec_authority(snapshot_json: str, expected_digest: str) -> tuple[list[str], StrategySpec | None]:
    """Re-prove the carried StrategySpec snapshot: anchor, public validation, exact canonical re-serialization, scope."""

    try:
        payload = json.loads(snapshot_json, parse_constant=_reject_json_constant)
    except Exception:  # noqa: BLE001 - an unparseable spec snapshot is a rejection, never a crash
        return [_reason("strategy_spec_malformed_payload")], None
    if type(payload) is not dict:
        return [_reason("strategy_spec_malformed_payload")], None
    codes: list[str] = []
    if _sha256(snapshot_json) != expected_digest:
        codes.append(_reason("strategy_spec_digest_mismatch"))
    if any(edge_scope_violation(text) is not None for text in _collect_strings(payload)):
        codes.append(_reason("strategy_spec_scope_violation"))
    try:
        validation = validate_strategy_spec(payload)
    except Exception:  # noqa: BLE001 - validation over a forged snapshot must fail closed
        validation = None
    if validation is None or validation.accepted is not True or type(validation.spec) is not StrategySpec:
        return [*codes, _reason("strategy_spec_invalid")], None
    if canonical_strategy_spec_json(validation.spec) != snapshot_json:
        codes.append(_reason("strategy_spec_noncanonical"))
    return codes, validation.spec


def _added_ids(draft: Sequence[EdgeKillCriterion], admitted: Sequence[EdgeKillCriterion]) -> tuple[str, ...]:
    draft_ids = {criterion.criterion_id for criterion in draft}
    return tuple(sorted(criterion.criterion_id for criterion in admitted if criterion.criterion_id not in draft_ids))


def _admission_verdict_reasons(
    *,
    root: EdgeIdeaIntakeEvidence,
    packet: EdgeSourcePacketEvidence,
    spec: StrategySpec,
    spec_data_requirement_keys: Sequence[str],
    packet_series_keys: Sequence[str],
    admitted: Sequence[EdgeKillCriterion],
    policy_needs: Sequence[str],
) -> tuple[list[str], list[str], list[str]]:
    fail: list[str] = []
    if spec.strategy_id != root.candidate_strategy_id:
        fail.append(_reason("candidate_strategy_id_mismatch"))
    if spec.edge_family != root.edge_family:
        fail.append(_reason("edge_family_mismatch"))
    fail.extend(
        _reason(f"instrument_outside_packet_coverage:{symbol}")
        for symbol in sorted(set(spec.instrument_universe))
        if symbol not in packet.packet_instrument_coverage
    )
    fail.extend(
        _reason(f"spec_data_requirement_not_in_packet:{key}")
        for key in spec_data_requirement_keys
        if key not in packet_series_keys
    )
    by_id = {criterion.criterion_id: criterion for criterion in admitted}
    if set(spec.kill_switch_triggers) != set(by_id):
        fail.append(_reason("spec_kill_switch_triggers_not_bound_to_kill_criteria"))
    for draft in root.kill_criteria_draft:
        current = by_id.get(draft.criterion_id)
        if current is None:
            fail.append(_reason(f"kill_criterion_removed:{draft.criterion_id}"))
        elif current != draft:
            fail.append(_reason(f"kill_criterion_modified:{draft.criterion_id}"))
    needs_governance = [
        _reason(f"kill_criterion_threshold_pending_governance:{criterion.criterion_id}")
        for criterion in admitted
        if criterion.threshold is None
    ]
    needs_governance.extend(_reason(f"kill_criteria_{code}") for code in policy_needs)
    return fail, [], needs_governance


def _assemble_admission(
    *,
    predecessor_source_packet_snapshot_json: object,
    expected_source_packet_evidence_digest: object,
    expected_root_intake_digest: object,
    strategy_spec_snapshot_json: object,
    expected_strategy_spec_digest: object,
    kill_criteria: object,
    admission_id: object,
    correlation_id: object,
    kill_criteria_policy_snapshot_json: object,
    expected_kill_criteria_policy_digest: object,
) -> EdgeStrategySpecAdmission:
    """The one assembly path of EF-4, shared by the builder and by reassembly-based verification."""

    if type(predecessor_source_packet_snapshot_json) is not str or type(strategy_spec_snapshot_json) is not str:
        raise EdgeStrategySpecAdmissionError(_reason("authority_snapshot_malformed"))
    for name, value in (
        ("expected_root_intake_digest", expected_root_intake_digest),
        ("expected_source_packet_evidence_digest", expected_source_packet_evidence_digest),
        ("expected_strategy_spec_digest", expected_strategy_spec_digest),
    ):
        if not _is_hex64(value):
            raise EdgeStrategySpecAdmissionError(_reason(f"{name}_invalid"))
    admission_id = _require_text(admission_id, "admission_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    try:
        admitted = canonical_edge_kill_criteria(kill_criteria)
    except EdgeIdeaIntakeEvidenceError as exc:
        raise EdgeStrategySpecAdmissionError(_reason(f"kill_criteria_invalid:{exc}")) from exc
    require_edge_policy_binding_shape(
        kill_criteria_policy_snapshot_json,
        expected_kill_criteria_policy_digest,
        EdgeStrategySpecAdmissionError,
        _REASON_PREFIX,
    )
    admitted_digest = edge_kill_criteria_digest(admitted)

    packet_codes, packet = _predecessor_authority(
        predecessor_source_packet_snapshot_json,
        expected_source_packet_evidence_digest,  # type: ignore[arg-type]
        correlation_id,
    )
    root_codes, root = _root_authority(packet, expected_root_intake_digest, correlation_id)  # type: ignore[arg-type]
    spec_codes, spec = _strategy_spec_authority(strategy_spec_snapshot_json, expected_strategy_spec_digest)  # type: ignore[arg-type]
    policy_integrity, policy_needs = evaluate_edge_kill_criteria_policy_binding(
        policy_snapshot_json=kill_criteria_policy_snapshot_json,  # type: ignore[arg-type]
        expected_policy_digest=expected_kill_criteria_policy_digest,  # type: ignore[arg-type]
        correlation_id=correlation_id,
        kill_criteria_digest=admitted_digest,
    )
    integrity = _sorted_unique(
        [*packet_codes, *root_codes, *spec_codes, *(_reason(f"kill_criteria_{code}") for code in policy_integrity)]
    )

    draft = () if root is None else root.kill_criteria_draft
    packet_series_keys = (
        () if packet is None else tuple(sorted(record.data_requirement_key for record in packet.series))
    )
    spec_keys = () if spec is None else tuple(sorted({key.strip().lower() for key in spec.data_requirements}))

    if integrity or root is None or packet is None or spec is None:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
        if not integrity:
            integrity = (_reason("authority_unavailable"),)
    else:
        fail, needs_external, needs_governance = _admission_verdict_reasons(
            root=root,
            packet=packet,
            spec=spec,
            spec_data_requirement_keys=spec_keys,
            packet_series_keys=packet_series_keys,
            admitted=admitted,
            policy_needs=policy_needs,
        )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    ready = status is EdgeEvidenceStatus.READY
    policy_present = kill_criteria_policy_snapshot_json != ""
    seed = EdgeStrategySpecAdmission(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        root_gate_id=_ROOT_GATE_ID,
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=ready and verdict is EdgeGateVerdict.PASS,
        admission_id=admission_id,
        correlation_id=correlation_id,
        predecessor_source_packet_snapshot_json=predecessor_source_packet_snapshot_json,
        expected_source_packet_evidence_digest=expected_source_packet_evidence_digest,  # type: ignore[arg-type]
        verified_source_packet_evidence_digest=expected_source_packet_evidence_digest if ready else "",  # type: ignore[arg-type]
        expected_root_intake_digest=expected_root_intake_digest,  # type: ignore[arg-type]
        verified_root_intake_digest=expected_root_intake_digest if ready else "",  # type: ignore[arg-type]
        strategy_spec_snapshot_json=strategy_spec_snapshot_json,
        expected_strategy_spec_digest=expected_strategy_spec_digest,  # type: ignore[arg-type]
        verified_strategy_spec_digest=expected_strategy_spec_digest if ready else "",  # type: ignore[arg-type]
        intake_candidate_strategy_id="" if root is None else root.candidate_strategy_id,
        intake_edge_family="" if root is None else root.edge_family,
        packet_instrument_coverage=() if packet is None else packet.packet_instrument_coverage,
        packet_series_keys=packet_series_keys,
        strategy_id="" if spec is None else spec.strategy_id,
        strategy_version="" if spec is None else spec.strategy_version,
        strategy_family="" if spec is None else spec.strategy_family,
        edge_family="" if spec is None else spec.edge_family,
        market_type="" if spec is None else spec.market_type.value,
        instrument_universe=() if spec is None else spec.instrument_universe,
        spec_data_requirement_keys=spec_keys,
        spec_data_requirement_key_normalization=_SPEC_DATA_REQUIREMENT_KEY_NORMALIZATION,
        spec_kill_switch_triggers=() if spec is None else spec.kill_switch_triggers,
        fee_model_requirement="" if spec is None else spec.fee_model_requirement,
        funding_sensitivity="" if spec is None else spec.funding_sensitivity,
        slippage_model_requirement="" if spec is None else spec.slippage_model_requirement,
        latency_sensitivity="" if spec is None else spec.latency_sensitivity,
        cost_model_binding=_COST_MODEL_BINDING,
        expected_regime_declared="" if spec is None else spec.expected_regime,
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        draft_kill_criteria=draft,
        draft_kill_criteria_digest="" if root is None else root.kill_criteria_digest,
        kill_criteria=admitted,
        kill_criteria_digest=admitted_digest,
        kill_criteria_added_ids=_added_ids(draft, admitted),
        kill_criteria_lifecycle_stage=_KILL_CRITERIA_LIFECYCLE_STAGE,
        kill_criteria_lifecycle_policy=_KILL_CRITERIA_LIFECYCLE_POLICY,
        kill_criteria_policy_snapshot_json=kill_criteria_policy_snapshot_json,  # type: ignore[arg-type]
        expected_kill_criteria_policy_digest=expected_kill_criteria_policy_digest,  # type: ignore[arg-type]
        verified_kill_criteria_policy_digest=(
            expected_kill_criteria_policy_digest if policy_present and ready else ""  # type: ignore[arg-type]
        ),
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        admission_digest="",
    )
    values = {field.name: getattr(seed, field.name) for field in fields(seed)}
    values[_SELF_DIGEST_FIELD] = edge_strategy_spec_admission_digest(seed)
    return EdgeStrategySpecAdmission(**values)  # type: ignore[arg-type]


def build_edge_strategy_spec_admission(
    source_packet_evidence: EdgeSourcePacketEvidence,
    strategy_spec: StrategySpec,
    *,
    expected_root_intake_digest: str,
    expected_source_packet_evidence_digest: str,
    expected_strategy_spec_digest: str,
    kill_criteria: Sequence[EdgeKillCriterion],
    admission_id: str,
    correlation_id: str,
    kill_criteria_policy: EdgeKillCriteriaPolicy | None = None,
    expected_kill_criteria_policy_digest: str | None = None,
) -> EdgeStrategySpecAdmission:
    """Build deterministic EF-4 admission of a validated StrategySpec against a re-proven EF-3 predecessor and its
    re-proven EF-2 root.

    Malformed caller input raises ``EdgeStrategySpecAdmissionError``. A predecessor, root, spec or policy that fails
    re-proof, a predecessor or root that is not READY + PASS, or a spliced chain yields ``REJECTED`` /
    ``NOT_EVALUATED``. Otherwise the admission is ``READY`` with a ``FAIL``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS``
    verdict.
    """

    if type(source_packet_evidence) is not EdgeSourcePacketEvidence:
        raise EdgeStrategySpecAdmissionError(_reason("source_packet_evidence_malformed"))
    if type(strategy_spec) is not StrategySpec:
        raise EdgeStrategySpecAdmissionError(_reason("strategy_spec_malformed"))
    policy_snapshot, policy_anchor = edge_kill_criteria_policy_snapshot(
        kill_criteria_policy, expected_kill_criteria_policy_digest, EdgeStrategySpecAdmissionError, _REASON_PREFIX
    )
    try:
        packet_snapshot = _canonical_json(edge_source_packet_evidence_to_dict(source_packet_evidence))
    except Exception:  # noqa: BLE001 - an unserializable predecessor is recorded as an empty snapshot and rejected
        packet_snapshot = ""
    try:
        spec_snapshot = canonical_strategy_spec_json(strategy_spec)
    except Exception:  # noqa: BLE001 - an unserializable spec is recorded as an empty snapshot and rejected
        spec_snapshot = ""
    return _assemble_admission(
        predecessor_source_packet_snapshot_json=packet_snapshot,
        expected_source_packet_evidence_digest=expected_source_packet_evidence_digest,
        expected_root_intake_digest=expected_root_intake_digest,
        strategy_spec_snapshot_json=spec_snapshot,
        expected_strategy_spec_digest=expected_strategy_spec_digest,
        kill_criteria=kill_criteria,
        admission_id=admission_id,
        correlation_id=correlation_id,
        kill_criteria_policy_snapshot_json=policy_snapshot,
        expected_kill_criteria_policy_digest=policy_anchor,
    )


def _serialize(value: object) -> object:
    if type(value) is EdgeKillCriterion:
        return edge_kill_criterion_to_dict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def edge_strategy_spec_admission_to_dict(admission: EdgeStrategySpecAdmission) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-4 admission evidence, including its self-digest."""

    return {field.name: _serialize(getattr(admission, field.name)) for field in fields(admission)}


def edge_strategy_spec_admission_digest(admission: EdgeStrategySpecAdmission) -> str:
    """Recompute the canonical admission digest, excluding only the self-digest field."""

    payload = edge_strategy_spec_admission_to_dict(admission)
    del payload[_SELF_DIGEST_FIELD]
    return _sha256(_canonical_json(payload))


def _malformed() -> EdgeStrategySpecAdmissionError:
    return EdgeStrategySpecAdmissionError(_reason("admission_snapshot_malformed"))


def _parse_field(kind: object, value: object) -> object:
    if kind == "bool":
        if type(value) is not bool:
            raise _malformed()
        return value
    if kind == "str_tuple":
        if type(value) is not list or any(type(item) is not str for item in value):
            raise _malformed()
        return tuple(value)
    if kind == "criteria":
        return () if value == [] else edge_kill_criteria_from_payload(value)
    if isinstance(kind, type) and issubclass(kind, Enum):
        if type(value) is not str:
            raise _malformed()
        try:
            return kind(value)
        except ValueError as exc:
            raise _malformed() from exc
    if type(value) is not str:
        raise _malformed()
    return value


def _admission_from_canonical_json(text: str) -> EdgeStrategySpecAdmission:
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise _malformed() from exc
    names = [field.name for field in fields(EdgeStrategySpecAdmission)]
    if type(payload) is not dict or set(payload) != set(names) or _canonical_json(payload) != text:
        raise _malformed()
    admission = EdgeStrategySpecAdmission(
        **{name: _parse_field(_ADMISSION_FIELD_KINDS.get(name, "str"), payload[name]) for name in names}  # type: ignore[arg-type]
    )
    if _canonical_json(edge_strategy_spec_admission_to_dict(admission)) != text:
        raise _malformed()
    return admission


def verify_edge_strategy_spec_admission(admission: object) -> EdgeEvidenceVerification:
    """Re-prove EF-4 evidence by strict parse and reassembly from its carried predecessor, spec and policy snapshots,
    anchors and caller fields. READY and REJECTED artifacts alike must match field for field. Never raises."""

    if (
        type(admission) is not EdgeStrategySpecAdmission
        or type(admission.status) is not EdgeEvidenceStatus
        or type(admission.gate_verdict) is not EdgeGateVerdict
    ):
        return EdgeEvidenceVerification(False, (_reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(edge_strategy_spec_admission_to_dict(admission))
    except Exception:  # noqa: BLE001 - a forged or non-serializable artifact must fail closed, never crash
        return EdgeEvidenceVerification(False, (_reason("evidence_serialization_failed"),), "", "")
    carried_payload = json.loads(canonical)
    body = dict(carried_payload)
    carried_digest = body.pop(_SELF_DIGEST_FIELD)
    recomputed = _sha256(_canonical_json(body))
    failures: list[str] = []
    if carried_digest != recomputed:
        failures.append(_reason("self_digest_mismatch"))
    try:
        parsed = _admission_from_canonical_json(canonical)
        expected_payload = edge_strategy_spec_admission_to_dict(
            _assemble_admission(
                predecessor_source_packet_snapshot_json=parsed.predecessor_source_packet_snapshot_json,
                expected_source_packet_evidence_digest=parsed.expected_source_packet_evidence_digest,
                expected_root_intake_digest=parsed.expected_root_intake_digest,
                strategy_spec_snapshot_json=parsed.strategy_spec_snapshot_json,
                expected_strategy_spec_digest=parsed.expected_strategy_spec_digest,
                kill_criteria=parsed.kill_criteria,
                admission_id=parsed.admission_id,
                correlation_id=parsed.correlation_id,
                kill_criteria_policy_snapshot_json=parsed.kill_criteria_policy_snapshot_json,
                expected_kill_criteria_policy_digest=parsed.expected_kill_criteria_policy_digest,
            )
        )
    except Exception:  # noqa: BLE001 - carried semantics that cannot be reassembled fail closed, never crash
        failures.append(_reason("evidence_semantics_malformed"))
    else:
        failures.extend(
            _reason(f"field_mismatch:{name}")
            for name in sorted(expected_payload)
            if _canonical_json(expected_payload[name]) != _canonical_json(carried_payload.get(name))
        )
    codes = _sorted_unique(failures)
    return EdgeEvidenceVerification(
        intact=not codes, reason_codes=codes, recomputed_digest=recomputed, canonical_json=canonical
    )


__all__ = [
    "EdgeStrategySpecAdmission",
    "EdgeStrategySpecAdmissionError",
    "build_edge_strategy_spec_admission",
    "edge_strategy_spec_admission_digest",
    "edge_strategy_spec_admission_to_dict",
    "verify_edge_strategy_spec_admission",
]
