"""Edge Factory EF-2: deterministic edge idea intake evidence, the ROOT ANCHOR of the candidate admission spine.

EF-2 binds an accepted ``crypto_core.strategy.source_packet.SourcePacket`` to the hypothesis record of
``docs/crypto_core/edge_factory_design.md``: intake and candidate identity, edge family, economic rationale, data
requirements in the ``DataRequirementKey`` vocabulary, external-fact needs, a kill-criteria DRAFT and the declared
regime dependence. Its ``intake_digest`` is the root anchor every later gate carries.

Trust model (shared kernel ``edge_artifact_core``):

* SourcePacket authority is a required ``EdgeAuthorityBinding``. It is constructed only from a SourcePacket whose
  public serializer yields a well-formed snapshot (otherwise a construction error). Assembly re-proves it: the packet
  self-digest and the caller anchor, reconstruction through the public ``build_source_packet`` with canonical
  equality, and the Edge Factory scope policy over the authenticated packet text. Packet id, rights and
  usable-for-compilation are derived only from the reconstructed packet.
* Governance approval is an optional ``EdgeAuthorityBinding`` over a digest-bound ``EdgeKillCriteriaPolicy``.
  ``None`` means no policy (``NEEDS_GOVERNANCE_APPROVAL``). A present policy that fails its own re-proof or its anchor
  is an integrity rejection; an authentic policy that is not READY, belongs to another correlation or approves
  different criteria is a governance need. No threshold is held, defaulted or invented here.
* Every declared external-fact need stays ``NEEDS_EXTERNAL_FACTS``; no opaque resolution can discharge it.
* One assembly path serves the builder and verifier reassembly; ``verify_edge_idea_intake_evidence`` is total.
* ``status`` is integrity only and ``gate_verdict`` the outcome; REJECTED implies NOT_EVALUATED; only READY + PASS
  advances. The regime dependence is recorded with the digest-bound pending pattern (no RF label). Paper-only,
  deterministic, no IO/clock/network; every structural non-claim is a default no builder parameter can set.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import SourcePacket, build_source_packet, source_packet_to_dict
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

_SCHEMA_VERSION = "edge-idea-intake-evidence.v2"
_GATE_ID = "EF-2"
_REASON_PREFIX = "edge_idea_intake_evidence"
_SELF_DIGEST_FIELD = "intake_digest"
_POLICY_SCHEMA_VERSION = "edge-kill-criteria-policy.v1"
_POLICY_REASON_PREFIX = "edge_kill_criteria_policy"
_POLICY_SELF_DIGEST_FIELD = "policy_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "DRAFT"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"
_EXTERNAL_FACT_RESOLUTION_POLICY = "declared_needs_stay_pending_no_verifiable_resolution_contract.v1"
_KILL_CRITERION_KEYS = frozenset({"criterion_id", "metric_id", "comparator", "threshold", "evaluation_basis"})
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)
_SOURCE_PACKET_FIELDS = frozenset(field.name for field in fields(SourcePacket))
_SOURCE_PACKET_BOOL_FIELDS = frozenset(
    {"usable_for_compilation", "paper_only", "real_orders_enabled", "real_money_enabled"}
)
_SOURCE_PACKET_LIST_FIELDS = frozenset({"market_scope_tags", "data_requirement_hints", "risk_flags"})
_SOURCE_PACKET_TEXT_FIELDS = ("packet_id", "source_reference", "source_title", "edge_hypothesis")


class EdgeIdeaIntakeEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgeKillCriterionComparator(str, Enum):
    """Direction in which a governed metric value triggers the kill."""

    KILL_IF_ABOVE = "kill_if_above"
    KILL_IF_AT_OR_ABOVE = "kill_if_at_or_above"
    KILL_IF_BELOW = "kill_if_below"
    KILL_IF_AT_OR_BELOW = "kill_if_at_or_below"


class EdgeKillCriteriaPolicyStatus(str, Enum):
    """Kill-criteria policy status. READY records approval only; it never proves profitability or readiness."""

    POLICY_READY = "POLICY_READY"
    POLICY_REJECTED = "POLICY_REJECTED"


@dataclass(frozen=True)
class EdgeKillCriterion:
    """One kill criterion. ``threshold`` is a governance-owned 18-place decimal string, or None while pending."""

    criterion_id: str
    metric_id: str
    comparator: EdgeKillCriterionComparator
    threshold: str | None
    evaluation_basis: str


@dataclass(frozen=True)
class EdgeKillCriteriaPolicy:
    """Immutable, digest-bound record of human governance approval for one exact kill-criteria set. PAPER ONLY."""

    schema_version: str
    status: EdgeKillCriteriaPolicyStatus
    ready: bool
    policy_id: str
    correlation_id: str
    kill_criteria: tuple[EdgeKillCriterion, ...]
    kill_criteria_digest: str
    thresholds_approved: bool
    approval_reference: str | None
    approval_digest: str | None
    reason_codes: tuple[str, ...]
    policy_digest: str
    policy_only: bool = True
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


@dataclass(frozen=True)
class EdgeIdeaIntakeEvidence:
    """Immutable, digest-bound EF-2 intake evidence. PAPER ONLY; proves process intake, never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    intake_id: str
    correlation_id: str
    candidate_strategy_id: str
    edge_family: str
    economic_rationale: str
    source_packet_binding: EdgeAuthorityBinding
    source_packet_id: str
    source_packet_rights_status: str
    source_packet_usable_for_compilation: bool
    data_requirement_keys: tuple[str, ...]
    declared_regime_dependence: str
    regime_label_binding_status: str
    regime_evidence_status: str
    external_fact_needs: tuple[str, ...]
    external_fact_resolution_policy: str
    kill_criteria_draft: tuple[EdgeKillCriterion, ...]
    kill_criteria_digest: str
    kill_criteria_lifecycle_stage: str
    kill_criteria_combination_policy: str
    kill_criteria_policy_binding: EdgeAuthorityBinding | None
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    intake_digest: str
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


def _policy_reason(code: str) -> str:
    return f"{_POLICY_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeIdeaIntakeEvidenceError:
    return EdgeIdeaIntakeEvidenceError(_reason(code))


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


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _is_canonical_decimal(value: object) -> bool:
    if type(value) is not str or "." not in value:
        return False
    whole, _, fraction = value.lstrip("-").partition(".")
    if len(fraction) != 18 or not fraction.isdigit() or not whole.isdigit() or (len(whole) > 1 and whole[0] == "0"):
        return False
    if value.startswith("-") and value.count("-") != 1:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and not (value.startswith("-") and parsed == 0)


# --- kill criteria ------------------------------------------------------------------------------------------------


def edge_kill_criterion_to_dict(criterion: EdgeKillCriterion) -> dict[str, object]:
    """Canonical JSON-ready mapping for one kill criterion."""

    return {
        "criterion_id": criterion.criterion_id,
        "metric_id": criterion.metric_id,
        "comparator": criterion.comparator.value,
        "threshold": criterion.threshold,
        "evaluation_basis": criterion.evaluation_basis,
    }


def canonical_edge_kill_criteria(criteria: object) -> tuple[EdgeKillCriterion, ...]:
    """Validate kill criteria and return them ordered by ``criterion_id`` (raises on any malformed criterion)."""

    if type(criteria) not in (tuple, list):
        raise _fail("kill_criteria_malformed")
    canonical: dict[str, EdgeKillCriterion] = {}
    for item in criteria:  # type: ignore[union-attr]
        if type(item) is not EdgeKillCriterion:
            raise _fail("kill_criterion_malformed")
        criterion_id = _require_token(item.criterion_id, "kill_criterion_id")
        metric_id = _require_token(item.metric_id, "kill_criterion_metric_id")
        evaluation_basis = _require_token(item.evaluation_basis, "kill_criterion_evaluation_basis")
        if type(item.comparator) is not EdgeKillCriterionComparator:
            raise _fail("kill_criterion_comparator_invalid")
        if item.threshold is not None and not _is_canonical_decimal(item.threshold):
            raise _fail("kill_criterion_threshold_invalid")
        if criterion_id in canonical:
            raise _fail("kill_criterion_duplicate")
        canonical[criterion_id] = EdgeKillCriterion(
            criterion_id=criterion_id,
            metric_id=metric_id,
            comparator=item.comparator,
            threshold=item.threshold,
            evaluation_basis=evaluation_basis,
        )
    if not canonical:
        raise _fail("kill_criteria_empty")
    return tuple(canonical[criterion_id] for criterion_id in sorted(canonical))


def edge_kill_criteria_digest(criteria: object) -> str:
    """Canonical SHA-256 digest of a kill-criteria set (order-insensitive)."""

    ordered = canonical_edge_kill_criteria(criteria)
    return edge_sha256_text(edge_canonical_json([edge_kill_criterion_to_dict(item) for item in ordered]))


def edge_kill_criteria_from_payload(payload: object) -> tuple[EdgeKillCriterion, ...]:
    """Rebuild kill criteria from their serialized payload, requiring the payload to already be canonical."""

    if type(payload) is not list:
        raise _fail("kill_criteria_payload_malformed")
    items: list[EdgeKillCriterion] = []
    for entry in payload:
        if type(entry) is not dict or set(entry) != _KILL_CRITERION_KEYS or type(entry["comparator"]) is not str:
            raise _fail("kill_criteria_payload_malformed")
        try:
            comparator = EdgeKillCriterionComparator(entry["comparator"])
        except ValueError as exc:
            raise _fail("kill_criterion_comparator_invalid") from exc
        items.append(
            EdgeKillCriterion(
                criterion_id=entry["criterion_id"],
                metric_id=entry["metric_id"],
                comparator=comparator,
                threshold=entry["threshold"],
                evaluation_basis=entry["evaluation_basis"],
            )
        )
    canonical = canonical_edge_kill_criteria(items)
    if [edge_kill_criterion_to_dict(item) for item in canonical] != payload:
        raise _fail("kill_criteria_payload_noncanonical")
    return canonical


# --- strict field conversion (shared by the policy and intake parsers) --------------------------------------------


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


def _with_self_digest(seed: object, field_name: str) -> object:
    return replace(seed, **{field_name: edge_payload_digest(_to_payload(seed), field_name)})  # type: ignore[type-var]


def _is_well_formed(parse: Callable[[object], object], payload: object) -> bool:
    try:
        parse(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


# --- EdgeKillCriteriaPolicy --------------------------------------------------------------------------------------


def build_edge_kill_criteria_policy(
    *,
    policy_id: str,
    correlation_id: str,
    kill_criteria: Sequence[EdgeKillCriterion],
    thresholds_approved: bool = False,
    approval_reference: str | None = None,
    approval_digest: str | None = None,
) -> EdgeKillCriteriaPolicy:
    """Build a digest-bound governance approval record for one exact kill-criteria set.

    Malformed input raises. A missing approval flag, reference or digest, or any pending threshold, yields
    ``POLICY_REJECTED``; nothing is defaulted and no threshold is chosen here.
    """

    policy_id = _require_text(policy_id, "kill_criteria_policy_id")
    correlation_id = _require_text(correlation_id, "kill_criteria_policy_correlation_id")
    criteria = canonical_edge_kill_criteria(kill_criteria)
    if type(thresholds_approved) is not bool:
        raise _fail("kill_criteria_policy_thresholds_approved_invalid")
    if approval_reference is not None:
        approval_reference = _require_text(approval_reference, "kill_criteria_policy_approval_reference")
    if approval_digest is not None and not edge_is_hex64(approval_digest):
        raise _fail("kill_criteria_policy_approval_digest_invalid")
    reasons = [
        _policy_reason(f"kill_criterion_threshold_missing:{item.criterion_id}")
        for item in criteria
        if item.threshold is None
    ]
    if thresholds_approved is not True:
        reasons.append(_policy_reason("thresholds_not_approved"))
    if approval_reference is None:
        reasons.append(_policy_reason("approval_reference_missing"))
    if approval_digest is None:
        reasons.append(_policy_reason("approval_digest_missing"))
    reason_codes = _sorted_unique(reasons)
    status = EdgeKillCriteriaPolicyStatus.POLICY_REJECTED if reason_codes else EdgeKillCriteriaPolicyStatus.POLICY_READY
    seed = EdgeKillCriteriaPolicy(
        schema_version=_POLICY_SCHEMA_VERSION,
        status=status,
        ready=status is EdgeKillCriteriaPolicyStatus.POLICY_READY,
        policy_id=policy_id,
        correlation_id=correlation_id,
        kill_criteria=criteria,
        kill_criteria_digest=edge_kill_criteria_digest(criteria),
        thresholds_approved=thresholds_approved,
        approval_reference=approval_reference,
        approval_digest=approval_digest,
        reason_codes=reason_codes,
        policy_digest="",
    )
    return _with_self_digest(seed, _POLICY_SELF_DIGEST_FIELD)  # type: ignore[return-value]


def edge_kill_criteria_policy_to_dict(policy: EdgeKillCriteriaPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping for the kill-criteria policy, including its self-digest."""

    return _to_payload(policy)


def edge_kill_criteria_policy_digest(policy: EdgeKillCriteriaPolicy) -> str:
    """Recompute the canonical policy digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(policy), _POLICY_SELF_DIGEST_FIELD)


_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeKillCriteriaPolicyStatus),
    "ready": _as_bool,
    "kill_criteria": edge_kill_criteria_from_payload,
    "thresholds_approved": _as_bool,
    "approval_reference": _as_optional_str,
    "approval_digest": _as_optional_str,
    "reason_codes": _as_str_tuple,
    "policy_only": _as_bool,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_kill_criteria_policy_from_payload(payload: object) -> EdgeKillCriteriaPolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields and types; no semantic proof)."""

    return _parse_exact(EdgeKillCriteriaPolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def edge_kill_criteria_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a kill-criteria policy snapshot."""

    return _is_well_formed(edge_kill_criteria_policy_from_payload, payload)


def _reassemble_policy(policy: object) -> EdgeKillCriteriaPolicy:
    return build_edge_kill_criteria_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        correlation_id=policy.correlation_id,  # type: ignore[attr-defined]
        kill_criteria=policy.kill_criteria,  # type: ignore[attr-defined]
        thresholds_approved=policy.thresholds_approved,  # type: ignore[attr-defined]
        approval_reference=policy.approval_reference,  # type: ignore[attr-defined]
        approval_digest=policy.approval_digest,  # type: ignore[attr-defined]
    )


def verify_edge_kill_criteria_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a kill-criteria policy by strict parse and reassembly through its builder. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=EdgeKillCriteriaPolicy,
        to_payload=_to_payload,
        parse_payload=edge_kill_criteria_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_POLICY_SELF_DIGEST_FIELD,
        reason=_policy_reason,
    )


def build_edge_kill_criteria_policy_binding(
    policy: object, expected_policy_digest: object, *, error: type[EdgeArtifactError], code: str
) -> EdgeAuthorityBinding | None:
    """Construct the optional policy binding: ``(None, None)`` → ``None``; a policy needs a hex64 anchor.

    Any mixed argument pair, a non-policy object, or a policy that does not serialize to a well-formed snapshot raises
    ``error``. ``code`` is the caller's reason prefix plus ``:kill_criteria_policy``.
    """

    if policy is None:
        if expected_policy_digest is not None:
            raise error(f"{code}_expected_digest_unexpected")
        return None
    if type(policy) is not EdgeKillCriteriaPolicy:
        raise error(f"{code}_malformed")
    try:
        payload = _to_payload(policy)
    except Exception as exc:  # noqa: BLE001 - a hollow policy object is a construction error, never a receipt
        raise error(f"{code}_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=expected_policy_digest,
        shape=edge_kill_criteria_policy_payload_is_well_formed,
        error=error,
        code=code,
    )


def evaluate_edge_kill_criteria_policy_binding(
    binding: EdgeAuthorityBinding | None, *, correlation_id: str, kill_criteria_digest: str
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The one governance-binding rule of the spine; returns unprefixed ``(integrity_codes, governance_needs)``."""

    if binding is None:
        return (), ("policy_missing",)
    policy = edge_kill_criteria_policy_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_kill_criteria_policy(policy)
    if not verification.intact:
        return tuple(f"policy_integrity_failure:{code}" for code in verification.reason_codes), ()
    if verification.recomputed_digest != binding.expected_digest:
        return ("policy_digest_mismatch",), ()
    needs: list[str] = []
    if policy.status is not EdgeKillCriteriaPolicyStatus.POLICY_READY:
        needs.append("policy_not_ready")
    if policy.correlation_id != correlation_id:
        needs.append("policy_correlation_mismatch")
    if policy.kill_criteria_digest != kill_criteria_digest:
        needs.append("policy_kill_criteria_mismatch")
    return (), tuple(needs)


# --- SourcePacket authority ---------------------------------------------------------------------------------------


def _source_packet_snapshot_is_well_formed(snapshot: object) -> bool:
    if type(snapshot) is not dict or set(snapshot) != _SOURCE_PACKET_FIELDS:
        return False
    for name, value in snapshot.items():
        if name in _SOURCE_PACKET_BOOL_FIELDS:
            valid = type(value) is bool
        elif name in _SOURCE_PACKET_LIST_FIELDS:
            valid = type(value) is list and all(type(item) is str for item in value)
        else:
            valid = type(value) is str
        if not valid:
            return False
    return True


def _source_packet_authority(binding: EdgeAuthorityBinding) -> tuple[list[str], SourcePacket | None]:
    snapshot = edge_authority_binding_snapshot(binding)
    codes: list[str] = []
    body = dict(snapshot)
    carried = body.pop("packet_digest")
    if carried != edge_sha256_text(edge_canonical_json(body)) or carried != binding.expected_digest:
        codes.append(_reason("source_packet_digest_mismatch"))
    try:
        rebuilt = build_source_packet(
            packet_id=snapshot["packet_id"],
            source_type=snapshot["source_type"],
            source_reference=snapshot["source_reference"],
            source_title=snapshot["source_title"],
            rights_status=snapshot["rights_status"],
            edge_hypothesis=snapshot["edge_hypothesis"],
            content_digest=snapshot["content_digest"],
            market_scope_tags=snapshot["market_scope_tags"],
            data_requirement_hints=snapshot["data_requirement_hints"],
            risk_flags=snapshot["risk_flags"],
        )
    except Exception:  # noqa: BLE001 - the public builder refusing authenticated fields is a truthful rejection
        return [*codes, _reason("source_packet_rebuild_failed")], None
    if source_packet_to_dict(rebuilt) != snapshot:
        codes.append(_reason("source_packet_noncanonical"))
    texts = [getattr(rebuilt, name) for name in _SOURCE_PACKET_TEXT_FIELDS]
    texts.extend([*rebuilt.market_scope_tags, *rebuilt.data_requirement_hints, *rebuilt.risk_flags])
    if any(edge_scope_violation(text) is not None for text in texts):
        codes.append(_reason("source_packet_scope_violation"))
    return codes, rebuilt


# --- EF-2 intake ---------------------------------------------------------------------------------------------------


def _canonical_data_requirement_keys(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise _fail("data_requirement_keys_malformed")
    keys: list[str] = []
    for item in values:  # type: ignore[union-attr]
        if type(item) is DataRequirementKey:
            key = item.value
        elif type(item) is str and item in _DATA_REQUIREMENT_KEY_VALUES:
            key = item
        else:
            raise _fail("data_requirement_key_unknown")
        if key in keys:
            raise _fail("data_requirement_key_duplicate")
        keys.append(key)
    if not keys:
        raise _fail("data_requirement_keys_empty")
    return tuple(sorted(keys))


def _canonical_needs(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise _fail("external_fact_needs_malformed")
    needs: list[str] = []
    for item in values:  # type: ignore[union-attr]
        need = _require_token(item, "external_fact_need")
        if need in needs:
            raise _fail("external_fact_need_duplicate")
        needs.append(need)
    return tuple(sorted(needs))


def _assemble_intake(
    *,
    source_packet_binding: object,
    kill_criteria_policy_binding: object,
    intake_id: object,
    correlation_id: object,
    candidate_strategy_id: object,
    edge_family: object,
    economic_rationale: object,
    data_requirement_keys: object,
    declared_regime_dependence: object,
    kill_criteria_draft: object,
    external_fact_needs: object,
) -> EdgeIdeaIntakeEvidence:
    """The one EF-2 assembly path, shared by the builder and verifier reassembly."""

    packet_binding = require_edge_authority_binding(
        source_packet_binding,
        shape=_source_packet_snapshot_is_well_formed,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("source_packet"),
        optional=False,
    )
    policy_binding = require_edge_authority_binding(
        kill_criteria_policy_binding,
        shape=edge_kill_criteria_policy_payload_is_well_formed,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("kill_criteria_policy"),
        optional=True,
    )
    intake_id = _require_text(intake_id, "intake_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    candidate_strategy_id = _require_text(candidate_strategy_id, "candidate_strategy_id")
    edge_family = _require_text(edge_family, "edge_family")
    economic_rationale = _require_text(economic_rationale, "economic_rationale")
    declared_regime_dependence = _require_text(declared_regime_dependence, "declared_regime_dependence")
    keys = _canonical_data_requirement_keys(data_requirement_keys)
    criteria = canonical_edge_kill_criteria(kill_criteria_draft)
    needs = _canonical_needs(external_fact_needs)
    criteria_digest = edge_kill_criteria_digest(criteria)

    packet_codes, packet = _source_packet_authority(packet_binding)  # type: ignore[arg-type]
    policy_integrity, policy_needs = evaluate_edge_kill_criteria_policy_binding(
        policy_binding, correlation_id=correlation_id, kill_criteria_digest=criteria_digest
    )
    integrity = _sorted_unique([*packet_codes, *(_reason(f"kill_criteria_{code}") for code in policy_integrity)])
    usable = packet is not None and packet.usable_for_compilation is True

    if integrity:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail = [] if usable else [_reason("source_packet_not_usable_for_compilation")]
        needs_external = [_reason(f"external_fact_need_unresolved:{need}") for need in needs]
        needs_governance = [
            _reason(f"kill_criterion_threshold_pending_governance:{item.criterion_id}")
            for item in criteria
            if item.threshold is None
        ]
        needs_governance.extend(_reason(f"kill_criteria_{code}") for code in policy_needs)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    seed = EdgeIdeaIntakeEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        intake_id=intake_id,
        correlation_id=correlation_id,
        candidate_strategy_id=candidate_strategy_id,
        edge_family=edge_family,
        economic_rationale=economic_rationale,
        source_packet_binding=packet_binding,  # type: ignore[arg-type]
        source_packet_id="" if packet is None else packet.packet_id,
        source_packet_rights_status="" if packet is None else packet.rights_status.value,
        source_packet_usable_for_compilation=usable,
        data_requirement_keys=keys,
        declared_regime_dependence=declared_regime_dependence,
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        external_fact_needs=needs,
        external_fact_resolution_policy=_EXTERNAL_FACT_RESOLUTION_POLICY,
        kill_criteria_draft=criteria,
        kill_criteria_digest=criteria_digest,
        kill_criteria_lifecycle_stage=_KILL_CRITERIA_LIFECYCLE_STAGE,
        kill_criteria_combination_policy=_KILL_CRITERIA_COMBINATION_POLICY,
        kill_criteria_policy_binding=policy_binding,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        intake_digest="",
    )
    return _with_self_digest(seed, _SELF_DIGEST_FIELD)  # type: ignore[return-value]


def build_edge_idea_intake_evidence(
    source_packet: SourcePacket,
    *,
    expected_source_packet_digest: str,
    intake_id: str,
    correlation_id: str,
    candidate_strategy_id: str,
    edge_family: str,
    economic_rationale: str,
    data_requirement_keys: Sequence[DataRequirementKey | str],
    declared_regime_dependence: str,
    kill_criteria_draft: Sequence[EdgeKillCriterion],
    external_fact_needs: Sequence[str] = (),
    kill_criteria_policy: EdgeKillCriteriaPolicy | None = None,
    expected_kill_criteria_policy_digest: str | None = None,
) -> EdgeIdeaIntakeEvidence:
    """Build deterministic EF-2 intake evidence, the root anchor of the Edge Factory chain.

    Malformed caller input or a non-serializable upstream object raises ``EdgeIdeaIntakeEvidenceError``. An
    authenticated SourcePacket or policy that fails re-proof yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the
    evidence is ``READY`` with ``FAIL`` (source not usable), ``NEEDS_EXTERNAL_FACTS`` (any declared need),
    ``NEEDS_GOVERNANCE_APPROVAL`` (missing, non-READY or non-matching policy, or a pending threshold) or ``PASS``.
    """

    if type(source_packet) is not SourcePacket:
        raise _fail("source_packet_malformed")
    try:
        packet_payload = source_packet_to_dict(source_packet)
    except Exception as exc:  # noqa: BLE001 - a hollow packet object is a construction error, never a receipt
        raise _fail("source_packet_not_serializable") from exc
    packet_binding = build_edge_authority_binding(
        snapshot_payload=packet_payload,
        expected_digest=expected_source_packet_digest,
        shape=_source_packet_snapshot_is_well_formed,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("source_packet"),
    )
    policy_binding = build_edge_kill_criteria_policy_binding(
        kill_criteria_policy,
        expected_kill_criteria_policy_digest,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("kill_criteria_policy"),
    )
    return _assemble_intake(
        source_packet_binding=packet_binding,
        kill_criteria_policy_binding=policy_binding,
        intake_id=intake_id,
        correlation_id=correlation_id,
        candidate_strategy_id=candidate_strategy_id,
        edge_family=edge_family,
        economic_rationale=economic_rationale,
        data_requirement_keys=data_requirement_keys,
        declared_regime_dependence=declared_regime_dependence,
        kill_criteria_draft=kill_criteria_draft,
        external_fact_needs=external_fact_needs,
    )


def edge_idea_intake_evidence_to_dict(evidence: EdgeIdeaIntakeEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-2 intake evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_idea_intake_evidence_digest(evidence: EdgeIdeaIntakeEvidence) -> str:
    """Recompute the canonical intake digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def _parse_source_packet_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=_source_packet_snapshot_is_well_formed,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("source_packet"),
        optional=False,
    )


def _parse_policy_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_kill_criteria_policy_payload_is_well_formed,
        error=EdgeIdeaIntakeEvidenceError,
        code=_reason("kill_criteria_policy"),
        optional=True,
    )


_INTAKE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "source_packet_binding": _parse_source_packet_binding,
    "source_packet_usable_for_compilation": _as_bool,
    "data_requirement_keys": _as_str_tuple,
    "external_fact_needs": _as_str_tuple,
    "kill_criteria_draft": edge_kill_criteria_from_payload,
    "kill_criteria_policy_binding": _parse_policy_binding,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_idea_intake_evidence_from_payload(payload: object) -> EdgeIdeaIntakeEvidence:
    """Strictly reconstruct EF-2 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_idea_intake_evidence`` on the result.
    """

    return _parse_exact(EdgeIdeaIntakeEvidence, payload, _INTAKE_CONVERTERS)  # type: ignore[return-value]


def edge_idea_intake_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-2 root snapshot."""

    return _is_well_formed(edge_idea_intake_evidence_from_payload, payload)


def _reassemble_intake(evidence: object) -> EdgeIdeaIntakeEvidence:
    return _assemble_intake(
        source_packet_binding=evidence.source_packet_binding,  # type: ignore[attr-defined]
        kill_criteria_policy_binding=evidence.kill_criteria_policy_binding,  # type: ignore[attr-defined]
        intake_id=evidence.intake_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        candidate_strategy_id=evidence.candidate_strategy_id,  # type: ignore[attr-defined]
        edge_family=evidence.edge_family,  # type: ignore[attr-defined]
        economic_rationale=evidence.economic_rationale,  # type: ignore[attr-defined]
        data_requirement_keys=evidence.data_requirement_keys,  # type: ignore[attr-defined]
        declared_regime_dependence=evidence.declared_regime_dependence,  # type: ignore[attr-defined]
        kill_criteria_draft=evidence.kill_criteria_draft,  # type: ignore[attr-defined]
        external_fact_needs=evidence.external_fact_needs,  # type: ignore[attr-defined]
    )


def verify_edge_idea_intake_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-2 evidence by strict parse and reassembly from its carried bindings and caller fields.

    READY and builder-produced REJECTED artifacts alike must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeIdeaIntakeEvidence,
        to_payload=_to_payload,
        parse_payload=edge_idea_intake_evidence_from_payload,
        reassemble=_reassemble_intake,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EdgeIdeaIntakeEvidence",
    "EdgeIdeaIntakeEvidenceError",
    "EdgeKillCriteriaPolicy",
    "EdgeKillCriteriaPolicyStatus",
    "EdgeKillCriterion",
    "EdgeKillCriterionComparator",
    "build_edge_idea_intake_evidence",
    "build_edge_kill_criteria_policy",
    "build_edge_kill_criteria_policy_binding",
    "canonical_edge_kill_criteria",
    "edge_idea_intake_evidence_digest",
    "edge_idea_intake_evidence_from_payload",
    "edge_idea_intake_evidence_payload_is_well_formed",
    "edge_idea_intake_evidence_to_dict",
    "edge_kill_criteria_digest",
    "edge_kill_criteria_from_payload",
    "edge_kill_criteria_policy_digest",
    "edge_kill_criteria_policy_from_payload",
    "edge_kill_criteria_policy_payload_is_well_formed",
    "edge_kill_criteria_policy_to_dict",
    "edge_kill_criterion_to_dict",
    "evaluate_edge_kill_criteria_policy_binding",
    "verify_edge_idea_intake_evidence",
    "verify_edge_kill_criteria_policy",
]
