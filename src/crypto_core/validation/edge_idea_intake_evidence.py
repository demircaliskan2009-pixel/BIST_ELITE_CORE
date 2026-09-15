"""Edge Factory EF-2: deterministic edge idea intake evidence, the root anchor of the candidate admission spine.

EF-2 is the first gate of ``docs/crypto_core/edge_factory_design.md``. It binds an already-merged
``crypto_core.strategy.source_packet.SourcePacket`` (idea provenance, rights posture, content digest) to the hypothesis
record the design requires: candidate strategy identity, edge family, economic rationale, data requirements in the
``crypto_core.data.requirements.DataRequirementKey`` vocabulary, external-fact needs, a kill-criteria DRAFT and the
declared regime dependence. Its ``intake_digest`` is the ROOT ANCHOR that every later Edge Factory gate carries.

Contract:

* ``status`` is evidence integrity only (``READY`` / ``REJECTED``). ``gate_verdict`` is the gate outcome (``PASS``,
  ``FAIL``, ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL``), and is ``NOT_EVALUATED`` exactly when the status
  is ``REJECTED``. READY + FAIL is valid negative evidence. Only READY + PASS ``advances``; a NEEDS_* verdict never does.
* Authority is carried, never copied. The artifact commits one canonical SourcePacket snapshot and, when supplied, one
  canonical ``EdgeKillCriteriaPolicy`` snapshot. Every SourcePacket-owned or policy-owned value is derived from those
  snapshots after they are re-proven: SourcePacket self-digest and caller anchor, reconstruction through the public
  ``build_source_packet`` with canonical equality, and this module's scope policy applied to the authenticated text.
* Verification is reassembly. ``verify_*`` strict-parses the carried artifact, re-runs the one assembly path over its
  carried snapshots, anchors and caller fields, and requires the result to equal the carried artifact field for field.
  READY and REJECTED artifacts are proven the same way, so an invented integrity reason code never verifies.
* Governance approval lives in a digest-bound ``EdgeKillCriteriaPolicy`` (modelled on ``secondary_metrics_policy``):
  it is accepted only when it re-verifies, matches the caller policy anchor, is ``POLICY_READY``, carries the same
  correlation id and exactly the draft criteria. Anything else is ``NEEDS_GOVERNANCE_APPROVAL``; a policy that fails
  re-proof is an integrity failure. No threshold is held or defaulted here; sealing belongs to EF-7.
* External facts: no verifiable resolution contract exists, so every declared need stays ``NEEDS_EXTERNAL_FACTS``.
* The regime-filter chain does not exist yet, so the regime dependence is recorded with the digest-bound pending
  pattern (``PENDING_RF_LABEL_ENUM_UNAVAILABLE`` / ``regime_evidence_unavailable``); no regime label is invented.
* Paper-only, deterministic, immutable: no clock, randomness, IO, network, environment or venue fact. The artifact
  proves intake of a candidate into the process only, never an edge, profitability, readiness, live, order or capital
  claim. ``edge_scope_violation`` is the single scope policy of the Edge Factory spine: the idea-intake vocabulary of
  ``strategy/source_packet.py`` (BIST markers, live/private/order/scheduler tokens) extended with order-identifier and
  key tokens and delimited so snake_case embeddings are caught.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import (
    SourcePacket,
    build_source_packet,
    source_packet_to_dict,
)

_SCHEMA_VERSION = "edge-idea-intake-evidence.v1"
_GATE_ID = "EF-2"
_REASON_PREFIX = "edge_idea_intake_evidence"
_SELF_DIGEST_FIELD = "intake_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "DRAFT"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"
_EXTERNAL_FACT_RESOLUTION_POLICY = "declared_needs_stay_pending_no_verifiable_resolution_contract.v1"
_POLICY_SCHEMA_VERSION = "edge-kill-criteria-policy.v1"
_POLICY_VERSION = "edge-kill-criteria-policy.v1"
_POLICY_REASON_PREFIX = "edge_kill_criteria_policy"
_POLICY_SELF_DIGEST_FIELD = "policy_digest"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_KILL_CRITERION_KEYS = frozenset({"criterion_id", "metric_id", "comparator", "threshold", "evaluation_basis"})
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
_SOURCE_PACKET_FIELDS = frozenset(field.name for field in fields(SourcePacket))
_SOURCE_PACKET_TEXT_FIELDS = ("packet_id", "source_reference", "source_title", "edge_hypothesis")
_SOURCE_PACKET_TAG_FIELDS = ("market_scope_tags", "data_requirement_hints", "risk_flags")

EDGE_REGIME_LABEL_BINDING_PENDING = "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
EDGE_REGIME_EVIDENCE_UNAVAILABLE = "regime_evidence_unavailable"

# Structural non-claims shared by every Edge Factory artifact. Each artifact declares them as dataclass defaults that
# no builder parameter can set, serializes them into its digest, and its verifier rejects any other value.
EDGE_STRUCTURAL_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("candidate_admitted_to_paper", False),
    ("preregistration_sealed", False),
    ("kill_criteria_sealed", False),
    ("performance_data_consumed", False),
    ("oos_evidence_consumed", False),
    ("regime_evidence_available", False),
    ("current_venue_facts_consumed", False),
    ("operational_readiness", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("deribit_ready", False),
    ("private_api_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS)

# Exactly 18 fractional digits: one approved number has exactly one digest-bound spelling.
_DECIMAL_PATTERN = re.compile(r"-?(?:0|[1-9][0-9]*)\.[0-9]{18}")
_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_.:-]{0,127}")
# Token starts are delimited by any non-alphanumeric character, underscore included, so snake_case embeddings
# ("carry_scheduler_loop", "funding_bist30") are caught; "kap" and "live" must stand alone ("kappa", "delivery" pass).
_BIST_PATTERN = re.compile(r"(?<![a-z0-9])(?:bist|borsa|matriks)|(?<![a-z0-9])kap(?![a-z0-9])", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:private_api|private_key|api_key|api_secret|credential|order_router|place_order|live_order"
    r"|real_order|order_id|auto_loop|shadow_live_execution|scheduler)"
    r"|(?<![a-z0-9])live(?![a-z0-9])",
    re.IGNORECASE,
)


class EdgeIdeaIntakeEvidenceError(RuntimeError):
    """Raised on malformed caller input, a malformed carried snapshot, or a forbidden scope token."""


class EdgeEvidenceStatus(str, Enum):
    """Evidence integrity of an Edge Factory artifact. Never a gate outcome."""

    READY = "READY"
    REJECTED = "REJECTED"


class EdgeGateVerdict(str, Enum):
    """Gate outcome of an Edge Factory artifact. Only PASS advances; NOT_EVALUATED is used exactly when REJECTED."""

    PASS = "PASS"  # noqa: S105 - gate verdict label, not a credential.
    FAIL = "FAIL"
    NEEDS_EXTERNAL_FACTS = "NEEDS_EXTERNAL_FACTS"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"
    NOT_EVALUATED = "NOT_EVALUATED"


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
class EdgeEvidenceVerification:
    """Result of re-proving one Edge Factory artifact.

    Consumers read ``canonical_json`` (an immutable, digest-bound snapshot) instead of re-reading the object, so a
    later mutation or a lying ``str`` subclass cannot diverge what was verified from what is consumed.
    """

    intact: bool
    reason_codes: tuple[str, ...]
    recomputed_digest: str
    canonical_json: str


@dataclass(frozen=True)
class EdgeKillCriteriaPolicy:
    """Immutable, digest-bound record of human governance approval for one exact kill-criteria set. PAPER ONLY."""

    schema_version: str
    policy_version: str
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
    source_packet_snapshot_json: str
    expected_source_packet_digest: str
    verified_source_packet_digest: str
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
    kill_criteria_policy_snapshot_json: str
    expected_kill_criteria_policy_digest: str
    verified_kill_criteria_policy_digest: str
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


_POLICY_FIELD_KINDS: dict[str, object] = {
    "status": EdgeKillCriteriaPolicyStatus,
    "ready": "bool",
    "kill_criteria": "criteria",
    "thresholds_approved": "bool",
    "approval_reference": "optional_str",
    "approval_digest": "optional_str",
    "reason_codes": "str_tuple",
    "policy_only": "bool",
    **dict.fromkeys(_FLAG_NAMES, "bool"),
}
_INTAKE_FIELD_KINDS: dict[str, object] = {
    "status": EdgeEvidenceStatus,
    "gate_verdict": EdgeGateVerdict,
    "advances": "bool",
    "source_packet_usable_for_compilation": "bool",
    "data_requirement_keys": "str_tuple",
    "external_fact_needs": "str_tuple",
    "kill_criteria_draft": "criteria",
    "integrity_reason_codes": "str_tuple",
    "verdict_reason_codes": "str_tuple",
    **dict.fromkeys(_FLAG_NAMES, "bool"),
}


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _policy_reason(code: str) -> str:
    return f"{_POLICY_REASON_PREFIX}:{code}"


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


def _is_token(value: object) -> bool:
    return type(value) is str and _TOKEN_PATTERN.fullmatch(value) is not None


def edge_scope_violation(text: str) -> str | None:
    """The single Edge Factory scope policy: ``bist_scope_leakage``, ``forbidden_scope_token`` or None."""

    if _BIST_PATTERN.search(text):
        return "bist_scope_leakage"
    if _FORBIDDEN_PATTERN.search(text):
        return "forbidden_scope_token"
    return None


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeIdeaIntakeEvidenceError(_reason(f"{field_name}_invalid"))
    violation = edge_scope_violation(value)  # type: ignore[arg-type]
    if violation is not None:
        raise EdgeIdeaIntakeEvidenceError(_reason(f"{violation}:{field_name}"))
    return value  # type: ignore[return-value]


def _require_token(value: object, field_name: str) -> str:
    if not _is_token(value):
        raise EdgeIdeaIntakeEvidenceError(_reason(f"{field_name}_invalid"))
    return _require_text(value, field_name)


def _is_canonical_decimal(value: object) -> bool:
    if type(value) is not str or _DECIMAL_PATTERN.fullmatch(value) is None:
        return False
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return False
    return parsed.is_finite() and not (value.startswith("-") and parsed == 0)


def _safe_canonical_snapshot(to_dict: Callable[[object], object], value: object) -> str:
    try:
        return _canonical_json(to_dict(value))
    except Exception:  # noqa: BLE001 - an unserializable input is recorded as an empty snapshot and fails re-proof
        return ""


def resolve_edge_gate_verdict(
    fail_reasons: Sequence[str],
    needs_external_fact_reasons: Sequence[str],
    needs_governance_reasons: Sequence[str],
) -> EdgeGateVerdict:
    """Verdict precedence shared by every Edge Factory gate.

    FAIL dominates (a definitive negative stays negative whatever else is missing); then NEEDS_EXTERNAL_FACTS (a
    governance number may depend on an external fact); then NEEDS_GOVERNANCE_APPROVAL; otherwise PASS.
    """

    if fail_reasons:
        return EdgeGateVerdict.FAIL
    if needs_external_fact_reasons:
        return EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    if needs_governance_reasons:
        return EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    return EdgeGateVerdict.PASS


# --- Kill criteria ------------------------------------------------------------------------------------------------


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
    """Validate kill criteria and return them ordered by ``criterion_id``.

    Raises ``EdgeIdeaIntakeEvidenceError`` on an empty set, a non-criterion item, a non-canonical token, an unknown
    comparator, a threshold that is not an 18-place decimal string (or None), or a duplicate ``criterion_id``.
    """

    if type(criteria) not in (tuple, list):
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_malformed"))
    canonical: dict[str, EdgeKillCriterion] = {}
    for item in criteria:  # type: ignore[union-attr]
        if type(item) is not EdgeKillCriterion:
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criterion_malformed"))
        criterion_id = _require_token(item.criterion_id, "kill_criterion_id")
        metric_id = _require_token(item.metric_id, "kill_criterion_metric_id")
        evaluation_basis = _require_token(item.evaluation_basis, "kill_criterion_evaluation_basis")
        if type(item.comparator) is not EdgeKillCriterionComparator:
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criterion_comparator_invalid"))
        if item.threshold is not None and not _is_canonical_decimal(item.threshold):
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criterion_threshold_invalid"))
        if criterion_id in canonical:
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criterion_duplicate"))
        canonical[criterion_id] = EdgeKillCriterion(
            criterion_id=criterion_id,
            metric_id=metric_id,
            comparator=item.comparator,
            threshold=item.threshold,
            evaluation_basis=evaluation_basis,
        )
    if not canonical:
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_empty"))
    return tuple(canonical[criterion_id] for criterion_id in sorted(canonical))


def edge_kill_criteria_digest(criteria: object) -> str:
    """Canonical SHA-256 digest of a kill-criteria set (order-insensitive: criteria are ordered by id first)."""

    return _sha256(
        _canonical_json([edge_kill_criterion_to_dict(item) for item in canonical_edge_kill_criteria(criteria)])
    )


def edge_kill_criteria_from_payload(payload: object) -> tuple[EdgeKillCriterion, ...]:
    """Rebuild kill criteria from their serialized payload, requiring the payload to already be canonical."""

    if type(payload) is not list:
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_payload_malformed"))
    items: list[EdgeKillCriterion] = []
    for entry in payload:
        if type(entry) is not dict or set(entry) != _KILL_CRITERION_KEYS or type(entry["comparator"]) is not str:
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_payload_malformed"))
        try:
            comparator = EdgeKillCriterionComparator(entry["comparator"])
        except ValueError as exc:
            raise EdgeIdeaIntakeEvidenceError(_reason("kill_criterion_comparator_invalid")) from exc
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
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_payload_noncanonical"))
    return canonical


# --- Strict canonical parsing (shared shape for both artifacts of this module) ------------------------------------


def _serialize(value: object) -> object:
    if type(value) is EdgeKillCriterion:
        return edge_kill_criterion_to_dict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _load_canonical_object(text: object, code: str) -> dict[str, object]:
    if type(text) is not str:
        raise EdgeIdeaIntakeEvidenceError(_reason(code))
    try:
        payload = json.loads(text, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise EdgeIdeaIntakeEvidenceError(_reason(code)) from exc
    if type(payload) is not dict or _canonical_json(payload) != text:
        raise EdgeIdeaIntakeEvidenceError(_reason(code))
    return payload


def _parse_field(kind: object, value: object, code: str) -> object:
    if kind == "bool":
        valid = type(value) is bool
    elif kind == "optional_str":
        valid = value is None or type(value) is str
    elif kind == "str_tuple":
        if type(value) is not list or any(type(item) is not str for item in value):
            raise EdgeIdeaIntakeEvidenceError(_reason(code))
        return tuple(value)
    elif kind == "criteria":
        return edge_kill_criteria_from_payload(value)
    elif isinstance(kind, type) and issubclass(kind, Enum):
        if type(value) is not str:
            raise EdgeIdeaIntakeEvidenceError(_reason(code))
        try:
            return kind(value)
        except ValueError as exc:
            raise EdgeIdeaIntakeEvidenceError(_reason(code)) from exc
    else:
        valid = type(value) is str
    if not valid:
        raise EdgeIdeaIntakeEvidenceError(_reason(code))
    return value


def _parse_exact(cls: type, kinds: Mapping[str, object], text: object, code: str) -> object:
    payload = _load_canonical_object(text, code)
    names = [field.name for field in fields(cls)]
    if set(payload) != set(names):
        raise EdgeIdeaIntakeEvidenceError(_reason(code))
    artifact = cls(**{name: _parse_field(kinds.get(name, "str"), payload[name], code) for name in names})
    if _canonical_json({field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}) != text:
        raise EdgeIdeaIntakeEvidenceError(_reason(code))
    return artifact


def _verify_by_reassembly(
    canonical: str,
    self_digest_field: str,
    parse: Callable[[str], object],
    reassemble: Callable[[object], object],
    reason: Callable[[str], str],
) -> EdgeEvidenceVerification:
    carried_payload = json.loads(canonical)
    body = dict(carried_payload)
    carried_digest = body.pop(self_digest_field, None)
    recomputed = _sha256(_canonical_json(body))
    failures: list[str] = []
    if carried_digest != recomputed:
        failures.append(reason("self_digest_mismatch"))
    try:
        expected = reassemble(parse(canonical))
        expected_payload = {field.name: _serialize(getattr(expected, field.name)) for field in fields(expected)}
    except Exception:  # noqa: BLE001 - carried semantics that cannot be reassembled fail closed, never crash
        failures.append(reason("evidence_semantics_malformed"))
    else:
        failures.extend(
            reason(f"field_mismatch:{name}")
            for name in sorted(expected_payload)
            if _canonical_json(expected_payload[name]) != _canonical_json(carried_payload.get(name))
        )
    codes = _sorted_unique(failures)
    return EdgeEvidenceVerification(
        intact=not codes, reason_codes=codes, recomputed_digest=recomputed, canonical_json=canonical
    )


def _verify_object(
    artifact: object,
    cls: type,
    enum_checks: Mapping[str, type],
    to_dict: Callable[[object], dict[str, object]],
    self_digest_field: str,
    parse: Callable[[str], object],
    reassemble: Callable[[object], object],
    reason: Callable[[str], str],
) -> EdgeEvidenceVerification:
    if type(artifact) is not cls or any(
        type(getattr(artifact, name)) is not enum for name, enum in enum_checks.items()
    ):
        return EdgeEvidenceVerification(False, (reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(to_dict(artifact))
    except Exception:  # noqa: BLE001 - a forged or non-serializable artifact must fail closed, never crash
        return EdgeEvidenceVerification(False, (reason("evidence_serialization_failed"),), "", "")
    return _verify_by_reassembly(canonical, self_digest_field, parse, reassemble, reason)


# --- EdgeKillCriteriaPolicy ---------------------------------------------------------------------------------------


def build_edge_kill_criteria_policy(
    *,
    policy_id: str,
    correlation_id: str,
    kill_criteria: Sequence[EdgeKillCriterion],
    thresholds_approved: bool = False,
    approval_reference: str | None = None,
    approval_digest: str | None = None,
) -> EdgeKillCriteriaPolicy:
    """Build a deterministic, digest-bound record of governance approval for one exact kill-criteria set.

    Malformed caller input raises. A missing approval flag, reference or digest, or any pending threshold, yields
    ``POLICY_REJECTED``; nothing is defaulted and no threshold is chosen here.
    """

    policy_id = _require_text(policy_id, "kill_criteria_policy_id")
    correlation_id = _require_text(correlation_id, "kill_criteria_policy_correlation_id")
    criteria = canonical_edge_kill_criteria(kill_criteria)
    if type(thresholds_approved) is not bool:
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_policy_thresholds_approved_invalid"))
    if approval_reference is not None:
        approval_reference = _require_text(approval_reference, "kill_criteria_policy_approval_reference")
    if approval_digest is not None and not _is_hex64(approval_digest):
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_policy_approval_digest_invalid"))

    reasons = [
        _policy_reason(f"kill_criterion_threshold_missing:{criterion.criterion_id}")
        for criterion in criteria
        if criterion.threshold is None
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
        policy_version=_POLICY_VERSION,
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
    payload = edge_kill_criteria_policy_to_dict(seed)
    return _with_field(seed, _POLICY_SELF_DIGEST_FIELD, _payload_digest(payload, _POLICY_SELF_DIGEST_FIELD))


def _with_field(artifact: object, name: str, value: object) -> object:
    values = {field.name: getattr(artifact, field.name) for field in fields(artifact)}
    values[name] = value
    return type(artifact)(**values)


def _payload_digest(payload: Mapping[str, object], self_digest_field: str) -> str:
    body = dict(payload)
    del body[self_digest_field]
    return _sha256(_canonical_json(body))


def edge_kill_criteria_policy_to_dict(policy: EdgeKillCriteriaPolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping for the kill-criteria policy, including its self-digest."""

    return {field.name: _serialize(getattr(policy, field.name)) for field in fields(policy)}


def edge_kill_criteria_policy_digest(policy: EdgeKillCriteriaPolicy) -> str:
    """Recompute the canonical policy digest, excluding only the self-digest field."""

    return _payload_digest(edge_kill_criteria_policy_to_dict(policy), _POLICY_SELF_DIGEST_FIELD)


def edge_kill_criteria_policy_from_canonical_json(text: str) -> EdgeKillCriteriaPolicy:
    """Strictly reconstruct a policy from its canonical JSON (exact fields, exact types, canonical reserialization)."""

    return _parse_exact(EdgeKillCriteriaPolicy, _POLICY_FIELD_KINDS, text, "kill_criteria_policy_snapshot_malformed")  # type: ignore[return-value]


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
    """Re-prove a kill-criteria policy by strict parse and reassembly through its builder. Never raises."""

    return _verify_object(
        policy,
        EdgeKillCriteriaPolicy,
        {"status": EdgeKillCriteriaPolicyStatus},
        edge_kill_criteria_policy_to_dict,  # type: ignore[arg-type]
        _POLICY_SELF_DIGEST_FIELD,
        edge_kill_criteria_policy_from_canonical_json,
        _reassemble_policy,
        _policy_reason,
    )


def evaluate_edge_kill_criteria_policy_binding(
    *,
    policy_snapshot_json: str,
    expected_policy_digest: str,
    correlation_id: str,
    kill_criteria_digest: str,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The one governance-binding rule of the Edge Factory spine.

    Returns ``(integrity_codes, governance_needs)`` as unprefixed codes. An absent policy is a governance need. A
    supplied policy that does not re-prove or does not match its anchor is an integrity failure. An authentic policy
    that is not READY, belongs to another correlation or approves a different criteria set is a governance need.
    """

    if policy_snapshot_json == "" and expected_policy_digest == "":
        return (), ("policy_missing",)
    try:
        policy = edge_kill_criteria_policy_from_canonical_json(policy_snapshot_json)
    except Exception:  # noqa: BLE001 - a malformed carried policy snapshot is an integrity failure, never a crash
        return ("policy_malformed_payload",), ()
    verification = verify_edge_kill_criteria_policy(policy)
    if not verification.intact:
        return tuple(f"policy_integrity_failure:{code}" for code in verification.reason_codes), ()
    if verification.recomputed_digest != expected_policy_digest:
        return ("policy_digest_mismatch",), ()
    needs: list[str] = []
    if policy.status is not EdgeKillCriteriaPolicyStatus.POLICY_READY or policy.ready is not True:
        needs.append("policy_not_ready")
    if policy.correlation_id != correlation_id:
        needs.append("policy_correlation_mismatch")
    if policy.kill_criteria_digest != kill_criteria_digest:
        needs.append("policy_kill_criteria_mismatch")
    return (), tuple(needs)


def edge_kill_criteria_policy_snapshot(
    policy: object, expected_policy_digest: object, error: type[Exception], code_prefix: str
) -> tuple[str, str]:
    """Validate a caller policy argument pair and return ``(policy_snapshot_json, expected_policy_digest)``.

    ``(None, None)`` means no policy (``("", "")``). A policy must be an exact ``EdgeKillCriteriaPolicy`` with a hex64
    anchor; any other combination raises ``error``.
    """

    if policy is None:
        if expected_policy_digest is not None:
            raise error(f"{code_prefix}:expected_kill_criteria_policy_digest_unexpected")
        return "", ""
    if type(policy) is not EdgeKillCriteriaPolicy:
        raise error(f"{code_prefix}:kill_criteria_policy_malformed")
    if not _is_hex64(expected_policy_digest):
        raise error(f"{code_prefix}:expected_kill_criteria_policy_digest_invalid")
    return _safe_canonical_snapshot(edge_kill_criteria_policy_to_dict, policy), expected_policy_digest  # type: ignore[arg-type,return-value]


def require_edge_policy_binding_shape(
    policy_snapshot_json: object, expected_policy_digest: object, error: type[Exception], code_prefix: str
) -> None:
    """Reject a carried policy binding whose shape no builder could have produced."""

    if (
        type(policy_snapshot_json) is not str
        or type(expected_policy_digest) is not str
        or (expected_policy_digest != "" and not _is_hex64(expected_policy_digest))
        or (expected_policy_digest == "" and policy_snapshot_json != "")
    ):
        raise error(f"{code_prefix}:kill_criteria_policy_binding_malformed")


# --- EF-2 intake --------------------------------------------------------------------------------------------------


def _canonical_data_requirement_keys(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise EdgeIdeaIntakeEvidenceError(_reason("data_requirement_keys_malformed"))
    keys: list[str] = []
    for item in values:  # type: ignore[union-attr]
        if type(item) is DataRequirementKey:
            key = item.value
        elif type(item) is str and item in _DATA_REQUIREMENT_KEY_VALUES:
            key = item
        else:
            raise EdgeIdeaIntakeEvidenceError(_reason("data_requirement_key_unknown"))
        if key in keys:
            raise EdgeIdeaIntakeEvidenceError(_reason("data_requirement_key_duplicate"))
        keys.append(key)
    if not keys:
        raise EdgeIdeaIntakeEvidenceError(_reason("data_requirement_keys_empty"))
    return tuple(sorted(keys))


def _canonical_needs(values: object) -> tuple[str, ...]:
    if type(values) not in (tuple, list):
        raise EdgeIdeaIntakeEvidenceError(_reason("external_fact_needs_malformed"))
    needs: list[str] = []
    for item in values:  # type: ignore[union-attr]
        need = _require_token(item, "external_fact_need")
        if need in needs:
            raise EdgeIdeaIntakeEvidenceError(_reason("external_fact_need_duplicate"))
        needs.append(need)
    return tuple(sorted(needs))


def _source_packet_authority(snapshot_json: str, expected_digest: str) -> tuple[list[str], SourcePacket | None]:
    """Re-prove the carried SourcePacket snapshot: canonical form, self-digest, anchor, public rebuild, scope."""

    try:
        payload = json.loads(snapshot_json, parse_constant=_reject_json_constant)
    except Exception:  # noqa: BLE001 - an unparseable snapshot is a rejection, never a crash
        return [_reason("source_packet_malformed_payload")], None
    if type(payload) is not dict or set(payload) != _SOURCE_PACKET_FIELDS:
        return [_reason("source_packet_malformed_payload")], None
    codes: list[str] = []
    if _canonical_json(payload) != snapshot_json:
        codes.append(_reason("source_packet_snapshot_noncanonical"))
    body = dict(payload)
    carried = body.pop("packet_digest")
    if carried != _sha256(_canonical_json(body)) or carried != expected_digest:
        codes.append(_reason("source_packet_digest_mismatch"))
    try:
        rebuilt = build_source_packet(
            packet_id=payload["packet_id"],  # type: ignore[arg-type]
            source_type=payload["source_type"],
            source_reference=payload["source_reference"],  # type: ignore[arg-type]
            source_title=payload["source_title"],  # type: ignore[arg-type]
            rights_status=payload["rights_status"],
            edge_hypothesis=payload["edge_hypothesis"],  # type: ignore[arg-type]
            content_digest=payload["content_digest"],  # type: ignore[arg-type]
            market_scope_tags=payload["market_scope_tags"],  # type: ignore[arg-type]
            data_requirement_hints=payload["data_requirement_hints"],  # type: ignore[arg-type]
            risk_flags=payload["risk_flags"],  # type: ignore[arg-type]
        )
    except Exception:  # noqa: BLE001 - the public builder refusing the carried fields is a rejection, never a crash
        return list(_sorted_unique([*codes, _reason("source_packet_rebuild_failed")])), None
    if source_packet_to_dict(rebuilt) != payload:
        codes.append(_reason("source_packet_noncanonical"))
    texts = [getattr(rebuilt, name) for name in _SOURCE_PACKET_TEXT_FIELDS]
    texts.extend(tag for name in _SOURCE_PACKET_TAG_FIELDS for tag in getattr(rebuilt, name))
    if any(edge_scope_violation(text) is not None for text in texts):
        codes.append(_reason("source_packet_scope_violation"))
    return list(_sorted_unique(codes)), rebuilt


def _assemble_intake(
    *,
    source_packet_snapshot_json: object,
    expected_source_packet_digest: object,
    intake_id: object,
    correlation_id: object,
    candidate_strategy_id: object,
    edge_family: object,
    economic_rationale: object,
    data_requirement_keys: object,
    declared_regime_dependence: object,
    kill_criteria_draft: object,
    external_fact_needs: object,
    kill_criteria_policy_snapshot_json: object,
    expected_kill_criteria_policy_digest: object,
) -> EdgeIdeaIntakeEvidence:
    """The one assembly path of EF-2, shared by the builder and by reassembly-based verification."""

    if type(source_packet_snapshot_json) is not str:
        raise EdgeIdeaIntakeEvidenceError(_reason("source_packet_snapshot_malformed"))
    if not _is_hex64(expected_source_packet_digest):
        raise EdgeIdeaIntakeEvidenceError(_reason("expected_source_packet_digest_invalid"))
    intake_id = _require_text(intake_id, "intake_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    candidate_strategy_id = _require_text(candidate_strategy_id, "candidate_strategy_id")
    edge_family = _require_text(edge_family, "edge_family")
    economic_rationale = _require_text(economic_rationale, "economic_rationale")
    declared_regime_dependence = _require_text(declared_regime_dependence, "declared_regime_dependence")
    keys = _canonical_data_requirement_keys(data_requirement_keys)
    criteria = canonical_edge_kill_criteria(kill_criteria_draft)
    needs = _canonical_needs(external_fact_needs)
    require_edge_policy_binding_shape(
        kill_criteria_policy_snapshot_json,
        expected_kill_criteria_policy_digest,
        EdgeIdeaIntakeEvidenceError,
        _REASON_PREFIX,
    )
    criteria_digest = edge_kill_criteria_digest(criteria)

    packet_codes, packet = _source_packet_authority(source_packet_snapshot_json, expected_source_packet_digest)  # type: ignore[arg-type]
    policy_integrity, policy_needs = evaluate_edge_kill_criteria_policy_binding(
        policy_snapshot_json=kill_criteria_policy_snapshot_json,  # type: ignore[arg-type]
        expected_policy_digest=expected_kill_criteria_policy_digest,  # type: ignore[arg-type]
        correlation_id=correlation_id,
        kill_criteria_digest=criteria_digest,
    )
    integrity = _sorted_unique([*packet_codes, *(_reason(f"kill_criteria_{code}") for code in policy_integrity)])
    usable = packet is not None and packet.usable_for_compilation is True

    if integrity:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
    else:
        fail = [] if usable else [_reason("source_packet_not_usable_for_compilation")]
        needs_external = [_reason(f"external_fact_need_unresolved:{need}") for need in needs]
        needs_governance = [
            _reason(f"kill_criterion_threshold_pending_governance:{criterion.criterion_id}")
            for criterion in criteria
            if criterion.threshold is None
        ]
        needs_governance.extend(_reason(f"kill_criteria_{code}") for code in policy_needs)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    policy_present = kill_criteria_policy_snapshot_json != ""
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
        source_packet_snapshot_json=source_packet_snapshot_json,
        expected_source_packet_digest=expected_source_packet_digest,  # type: ignore[arg-type]
        verified_source_packet_digest="" if packet_codes else expected_source_packet_digest,  # type: ignore[arg-type]
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
        kill_criteria_policy_snapshot_json=kill_criteria_policy_snapshot_json,  # type: ignore[arg-type]
        expected_kill_criteria_policy_digest=expected_kill_criteria_policy_digest,  # type: ignore[arg-type]
        verified_kill_criteria_policy_digest=(
            expected_kill_criteria_policy_digest if policy_present and not policy_integrity else ""  # type: ignore[arg-type]
        ),
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        intake_digest="",
    )
    return _with_field(seed, _SELF_DIGEST_FIELD, edge_idea_intake_evidence_digest(seed))  # type: ignore[return-value]


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

    Malformed caller input raises ``EdgeIdeaIntakeEvidenceError``. A SourcePacket or policy that fails re-proof yields
    ``REJECTED`` / ``NOT_EVALUATED``. Otherwise the evidence is ``READY`` with a verdict: ``FAIL`` when the source is
    not usable for compilation, ``NEEDS_EXTERNAL_FACTS`` for any declared need, ``NEEDS_GOVERNANCE_APPROVAL`` for a
    missing, non-READY or non-matching policy or a pending threshold, else ``PASS``. No governance value is defaulted.
    """

    if type(source_packet) is not SourcePacket:
        raise EdgeIdeaIntakeEvidenceError(_reason("source_packet_malformed"))
    policy_snapshot, policy_anchor = edge_kill_criteria_policy_snapshot(
        kill_criteria_policy, expected_kill_criteria_policy_digest, EdgeIdeaIntakeEvidenceError, _REASON_PREFIX
    )
    return _assemble_intake(
        source_packet_snapshot_json=_safe_canonical_snapshot(source_packet_to_dict, source_packet),  # type: ignore[arg-type]
        expected_source_packet_digest=expected_source_packet_digest,
        intake_id=intake_id,
        correlation_id=correlation_id,
        candidate_strategy_id=candidate_strategy_id,
        edge_family=edge_family,
        economic_rationale=economic_rationale,
        data_requirement_keys=data_requirement_keys,
        declared_regime_dependence=declared_regime_dependence,
        kill_criteria_draft=kill_criteria_draft,
        external_fact_needs=external_fact_needs,
        kill_criteria_policy_snapshot_json=policy_snapshot,
        expected_kill_criteria_policy_digest=policy_anchor,
    )


def edge_idea_intake_evidence_to_dict(evidence: EdgeIdeaIntakeEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-2 intake evidence, including its self-digest."""

    return {field.name: _serialize(getattr(evidence, field.name)) for field in fields(evidence)}


def edge_idea_intake_evidence_digest(evidence: EdgeIdeaIntakeEvidence) -> str:
    """Recompute the canonical intake digest, excluding only the self-digest field."""

    return _payload_digest(edge_idea_intake_evidence_to_dict(evidence), _SELF_DIGEST_FIELD)


def edge_idea_intake_evidence_from_canonical_json(text: str) -> EdgeIdeaIntakeEvidence:
    """Strictly reconstruct EF-2 evidence from its canonical JSON (exact fields and types, canonical reserialization).

    Reconstruction is not verification: downstream gates call ``verify_edge_idea_intake_evidence`` on the result.
    """

    return _parse_exact(EdgeIdeaIntakeEvidence, _INTAKE_FIELD_KINDS, text, "intake_snapshot_malformed")  # type: ignore[return-value]


def _reassemble_intake(evidence: object) -> EdgeIdeaIntakeEvidence:
    return _assemble_intake(
        source_packet_snapshot_json=evidence.source_packet_snapshot_json,  # type: ignore[attr-defined]
        expected_source_packet_digest=evidence.expected_source_packet_digest,  # type: ignore[attr-defined]
        intake_id=evidence.intake_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        candidate_strategy_id=evidence.candidate_strategy_id,  # type: ignore[attr-defined]
        edge_family=evidence.edge_family,  # type: ignore[attr-defined]
        economic_rationale=evidence.economic_rationale,  # type: ignore[attr-defined]
        data_requirement_keys=evidence.data_requirement_keys,  # type: ignore[attr-defined]
        declared_regime_dependence=evidence.declared_regime_dependence,  # type: ignore[attr-defined]
        kill_criteria_draft=evidence.kill_criteria_draft,  # type: ignore[attr-defined]
        external_fact_needs=evidence.external_fact_needs,  # type: ignore[attr-defined]
        kill_criteria_policy_snapshot_json=evidence.kill_criteria_policy_snapshot_json,  # type: ignore[attr-defined]
        expected_kill_criteria_policy_digest=evidence.expected_kill_criteria_policy_digest,  # type: ignore[attr-defined]
    )


def verify_edge_idea_intake_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-2 evidence by strict parse and reassembly from its carried snapshots, anchors and caller fields.

    READY and REJECTED artifacts alike must equal the reassembled artifact field for field. Never raises.
    """

    return _verify_object(
        evidence,
        EdgeIdeaIntakeEvidence,
        {"status": EdgeEvidenceStatus, "gate_verdict": EdgeGateVerdict},
        edge_idea_intake_evidence_to_dict,  # type: ignore[arg-type]
        _SELF_DIGEST_FIELD,
        edge_idea_intake_evidence_from_canonical_json,
        _reassemble_intake,
        _reason,
    )


__all__ = [
    "EDGE_REGIME_EVIDENCE_UNAVAILABLE",
    "EDGE_REGIME_LABEL_BINDING_PENDING",
    "EDGE_STRUCTURAL_NON_CLAIM_FLAGS",
    "EdgeEvidenceStatus",
    "EdgeEvidenceVerification",
    "EdgeGateVerdict",
    "EdgeIdeaIntakeEvidence",
    "EdgeIdeaIntakeEvidenceError",
    "EdgeKillCriteriaPolicy",
    "EdgeKillCriteriaPolicyStatus",
    "EdgeKillCriterion",
    "EdgeKillCriterionComparator",
    "build_edge_idea_intake_evidence",
    "build_edge_kill_criteria_policy",
    "canonical_edge_kill_criteria",
    "edge_idea_intake_evidence_digest",
    "edge_idea_intake_evidence_from_canonical_json",
    "edge_idea_intake_evidence_to_dict",
    "edge_kill_criteria_digest",
    "edge_kill_criteria_from_payload",
    "edge_kill_criteria_policy_digest",
    "edge_kill_criteria_policy_from_canonical_json",
    "edge_kill_criteria_policy_snapshot",
    "edge_kill_criteria_policy_to_dict",
    "edge_kill_criterion_to_dict",
    "edge_scope_violation",
    "evaluate_edge_kill_criteria_policy_binding",
    "require_edge_policy_binding_shape",
    "resolve_edge_gate_verdict",
    "verify_edge_idea_intake_evidence",
    "verify_edge_kill_criteria_policy",
]
