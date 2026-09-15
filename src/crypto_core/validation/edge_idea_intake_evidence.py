"""Edge Factory EF-2: deterministic edge idea intake evidence, the root anchor of the candidate admission spine.

EF-2 is the first gate of ``docs/crypto_core/edge_factory_design.md``. It binds an already-merged, digest-proven
``crypto_core.strategy.source_packet.SourcePacket`` (idea provenance, rights posture, content digest) to the hypothesis
record the design requires: candidate strategy identity, edge family, economic rationale, data requirements in the
``crypto_core.data.requirements.DataRequirementKey`` vocabulary, external-fact needs, a kill-criteria DRAFT and the
declared regime dependence. Its ``intake_digest`` is the ROOT ANCHOR that every later Edge Factory gate carries.

Contract:

* ``status`` is evidence integrity only (``READY`` / ``REJECTED``). ``gate_verdict`` is the gate outcome (``PASS``,
  ``FAIL``, ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL``), and is ``NOT_EVALUATED`` exactly when the status
  is ``REJECTED``. READY + FAIL is valid negative evidence. Only READY + PASS ``advances``; a NEEDS_* verdict never does.
* The SourcePacket is re-proven, never trusted: one canonical snapshot through its public serializer, the self-digest
  recomputed and matched to the caller anchor, and the packet rebuilt through the public ``build_source_packet`` so a
  resealed packet that breaks the builder invariants (restricted rights marked usable, non-canonical tags, forced
  paper flags) is REJECTED.
* Kill criteria are a DRAFT: canonical tokens, unique ids, ordered by id, combined as "any single criterion kills".
  Thresholds are governance-owned. This module holds no threshold value; a missing threshold or a missing approval
  yields ``NEEDS_GOVERNANCE_APPROVAL``. Sealing belongs to EF-7.
* An external-fact need without a resolution yields ``NEEDS_EXTERNAL_FACTS``; nothing is guessed. A resolution is a
  controller-attested opaque digest and is labelled as such.
* The regime-filter chain does not exist yet, so the regime dependence is recorded with the digest-bound pending
  pattern (``PENDING_RF_LABEL_ENUM_UNAVAILABLE`` / ``regime_evidence_unavailable``); no regime label is invented.
* Consumers re-prove an artifact through ``verify_edge_idea_intake_evidence``, which recomputes the self-digest and
  re-derives the verdict from the carried fields, and then read the verified ``canonical_json`` snapshot.
* Paper-only, deterministic, immutable: no clock, randomness, IO, network, environment or venue fact. The artifact
  proves intake of a candidate into the process only, never an edge, profitability, readiness, live, order or
  capital claim. Caller text is scanned with the idea-intake vocabulary of ``strategy/source_packet.py`` (BIST markers
  and live/private/order/scheduler tokens) extended with order-identifier and key tokens.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import Decimal, InvalidOperation
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import (
    SourcePacket,
    SourcePacketRightsStatus,
    build_source_packet,
    source_packet_to_dict,
)

_SCHEMA_VERSION = "edge-idea-intake-evidence.v1"
_GATE_ID = "EF-2"
_REASON_PREFIX = "edge_idea_intake_evidence"
_SELF_DIGEST_FIELD = "intake_digest"
_KILL_CRITERIA_LIFECYCLE_STAGE = "DRAFT"
_KILL_CRITERIA_COMBINATION_POLICY = "any_single_criterion_triggers_kill.v1"
_EXTERNAL_FACT_RESOLUTION_TRUST = "controller_attested_opaque_resolution_digest.v1"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_KILL_CRITERION_KEYS = frozenset({"criterion_id", "metric_id", "comparator", "threshold", "evaluation_basis"})
_DATA_REQUIREMENT_KEY_VALUES = frozenset(key.value for key in DataRequirementKey)
_RIGHTS_STATUS_VALUES = frozenset(status.value for status in SourcePacketRightsStatus)

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
    """Raised on malformed caller input or a forbidden BIST/live/private/order/scheduler token."""


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
    source_packet_id: str
    source_packet_rights_status: str
    source_packet_usable_for_compilation: bool
    expected_source_packet_digest: str
    verified_source_packet_digest: str
    data_requirement_keys: tuple[str, ...]
    declared_regime_dependence: str
    regime_label_binding_status: str
    regime_evidence_status: str
    external_fact_needs: tuple[str, ...]
    external_fact_resolutions: tuple[tuple[str, str], ...]
    unresolved_external_fact_needs: tuple[str, ...]
    external_fact_resolution_trust: str
    kill_criteria_draft: tuple[EdgeKillCriterion, ...]
    kill_criteria_digest: str
    kill_criteria_lifecycle_stage: str
    kill_criteria_combination_policy: str
    kill_criteria_thresholds_approved: bool
    kill_criteria_approval_reference: str | None
    kill_criteria_approval_digest: str | None
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


_CONSTANT_FIELDS: tuple[tuple[str, str], ...] = (
    ("schema_version", _SCHEMA_VERSION),
    ("gate_id", _GATE_ID),
    ("regime_label_binding_status", EDGE_REGIME_LABEL_BINDING_PENDING),
    ("regime_evidence_status", EDGE_REGIME_EVIDENCE_UNAVAILABLE),
    ("external_fact_resolution_trust", _EXTERNAL_FACT_RESOLUTION_TRUST),
    ("kill_criteria_lifecycle_stage", _KILL_CRITERIA_LIFECYCLE_STAGE),
    ("kill_criteria_combination_policy", _KILL_CRITERIA_COMBINATION_POLICY),
)
# Caller text scanned at build time; the verifier re-scans exactly this set so a READY artifact always re-verifies.
_TEXT_FIELDS = (
    "intake_id",
    "correlation_id",
    "candidate_strategy_id",
    "edge_family",
    "economic_rationale",
    "declared_regime_dependence",
)


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_json(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


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


def _scope_violation(text: str) -> str | None:
    if _BIST_PATTERN.search(text):
        return "bist_scope_leakage"
    if _FORBIDDEN_PATTERN.search(text):
        return "forbidden_scope_token"
    return None


def _require_text(value: object, field_name: str) -> str:
    if not _is_plain_text(value):
        raise EdgeIdeaIntakeEvidenceError(_reason(f"{field_name}_invalid"))
    violation = _scope_violation(value)  # type: ignore[arg-type]
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


def _is_canonical_reason_list(value: object) -> bool:
    return (
        type(value) is list
        and all(type(code) is str and code.startswith(f"{_REASON_PREFIX}:") for code in value)
        and value == sorted(set(value))
    )


def _is_canonical_token_list(value: object) -> bool:
    return type(value) is list and all(_is_token(item) for item in value) and value == sorted(set(value))


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


def _canonical_resolutions(resolutions: object, needs: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    if resolutions is None:
        return ()
    if not isinstance(resolutions, Mapping):
        raise EdgeIdeaIntakeEvidenceError(_reason("external_fact_resolutions_malformed"))
    pairs: list[tuple[str, str]] = []
    for need, digest in resolutions.items():
        if type(need) is not str or need not in needs:
            raise EdgeIdeaIntakeEvidenceError(_reason("external_fact_resolution_undeclared"))
        if not _is_hex64(digest):
            raise EdgeIdeaIntakeEvidenceError(_reason("external_fact_resolution_digest_invalid"))
        pairs.append((need, digest))
    return tuple(sorted(pairs))


def _intake_verdict_reasons(
    *,
    source_packet_usable_for_compilation: object,
    unresolved_external_fact_needs: Sequence[str],
    kill_criteria: Sequence[EdgeKillCriterion],
    thresholds_approved: object,
    approval_reference: object,
    approval_digest: object,
) -> tuple[list[str], list[str], list[str]]:
    fail: list[str] = []
    if source_packet_usable_for_compilation is not True:
        fail.append(_reason("source_packet_not_usable_for_compilation"))
    needs_external = [_reason(f"external_fact_need_unresolved:{need}") for need in unresolved_external_fact_needs]
    needs_governance = [
        _reason(f"kill_criterion_threshold_pending_governance:{criterion.criterion_id}")
        for criterion in kill_criteria
        if criterion.threshold is None
    ]
    if thresholds_approved is not True:
        needs_governance.append(_reason("kill_criteria_thresholds_not_approved"))
    elif not _is_plain_text(approval_reference) or not _is_hex64(approval_digest):
        needs_governance.append(_reason("kill_criteria_approval_incomplete"))
    return fail, needs_external, needs_governance


def _source_packet_proof(packet: SourcePacket, expected_digest: str) -> tuple[list[str], dict[str, object] | None]:
    """Re-prove a SourcePacket from ONE canonical snapshot: self-digest, caller anchor, and public-builder rebuild."""

    try:
        snapshot = json.loads(_canonical_json(source_packet_to_dict(packet)))
    except Exception:  # noqa: BLE001 - a forged or non-serializable packet must fail closed, never crash
        return [_reason("source_packet_malformed_payload")], None
    if type(snapshot) is not dict:
        return [_reason("source_packet_malformed_payload")], None
    failures: list[str] = []
    body = dict(snapshot)
    carried = body.pop("packet_digest", None)
    recomputed = _sha256(_canonical_json(body))
    if carried != recomputed or recomputed != expected_digest:
        failures.append(_reason("source_packet_digest_mismatch"))
    try:
        rebuilt = source_packet_to_dict(
            build_source_packet(
                packet_id=body["packet_id"],  # type: ignore[arg-type]
                source_type=body["source_type"],
                source_reference=body["source_reference"],  # type: ignore[arg-type]
                source_title=body["source_title"],  # type: ignore[arg-type]
                rights_status=body["rights_status"],
                edge_hypothesis=body["edge_hypothesis"],  # type: ignore[arg-type]
                content_digest=body["content_digest"],  # type: ignore[arg-type]
                market_scope_tags=body["market_scope_tags"],  # type: ignore[arg-type]
                data_requirement_hints=body["data_requirement_hints"],  # type: ignore[arg-type]
                risk_flags=body["risk_flags"],  # type: ignore[arg-type]
            )
        )
    except Exception:  # noqa: BLE001 - the public builder refusing the carried fields is a rejection, never a crash
        failures.append(_reason("source_packet_rebuild_failed"))
    else:
        if rebuilt != snapshot:
            failures.append(_reason("source_packet_noncanonical"))
    return list(_sorted_unique(failures)), snapshot


def _snapshot_text(snapshot: Mapping[str, object] | None, key: str) -> str:
    if snapshot is None:
        return ""
    value = snapshot.get(key)
    return value if type(value) is str else ""


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
    external_fact_resolutions: Mapping[str, str] | None = None,
    kill_criteria_thresholds_approved: bool = False,
    kill_criteria_approval_reference: str | None = None,
    kill_criteria_approval_digest: str | None = None,
) -> EdgeIdeaIntakeEvidence:
    """Build deterministic EF-2 intake evidence, the root anchor of the Edge Factory chain.

    Malformed caller input raises ``EdgeIdeaIntakeEvidenceError``. A SourcePacket that fails re-proof yields
    ``REJECTED`` / ``NOT_EVALUATED``. Otherwise the evidence is ``READY`` with a verdict: ``FAIL`` when the source is
    not usable for compilation, ``NEEDS_EXTERNAL_FACTS`` for an unresolved need, ``NEEDS_GOVERNANCE_APPROVAL`` for a
    pending threshold or a missing approval, else ``PASS``. No governance value is defaulted.
    """

    if type(source_packet) is not SourcePacket:
        raise EdgeIdeaIntakeEvidenceError(_reason("source_packet_malformed"))
    if not _is_hex64(expected_source_packet_digest):
        raise EdgeIdeaIntakeEvidenceError(_reason("expected_source_packet_digest_invalid"))
    intake_id = _require_text(intake_id, "intake_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    candidate_strategy_id = _require_text(candidate_strategy_id, "candidate_strategy_id")
    edge_family = _require_text(edge_family, "edge_family")
    economic_rationale = _require_text(economic_rationale, "economic_rationale")
    declared_regime_dependence = _require_text(declared_regime_dependence, "declared_regime_dependence")
    keys = _canonical_data_requirement_keys(data_requirement_keys)
    kill_criteria = canonical_edge_kill_criteria(kill_criteria_draft)
    needs = _canonical_needs(external_fact_needs)
    resolutions = _canonical_resolutions(external_fact_resolutions, needs)
    if type(kill_criteria_thresholds_approved) is not bool:
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_thresholds_approved_invalid"))
    if kill_criteria_approval_reference is not None:
        kill_criteria_approval_reference = _require_text(
            kill_criteria_approval_reference, "kill_criteria_approval_reference"
        )
    if kill_criteria_approval_digest is not None and not _is_hex64(kill_criteria_approval_digest):
        raise EdgeIdeaIntakeEvidenceError(_reason("kill_criteria_approval_digest_invalid"))

    integrity, snapshot = _source_packet_proof(source_packet, expected_source_packet_digest)
    resolved = {need for need, _ in resolutions}
    unresolved = tuple(need for need in needs if need not in resolved)
    usable = snapshot is not None and snapshot.get("usable_for_compilation") is True

    if integrity:
        status = EdgeEvidenceStatus.REJECTED
        verdict = EdgeGateVerdict.NOT_EVALUATED
        verdict_reasons: tuple[str, ...] = ()
        verified_source_packet_digest = ""
    else:
        fail, needs_external, needs_governance = _intake_verdict_reasons(
            source_packet_usable_for_compilation=usable,
            unresolved_external_fact_needs=unresolved,
            kill_criteria=kill_criteria,
            thresholds_approved=kill_criteria_thresholds_approved,
            approval_reference=kill_criteria_approval_reference,
            approval_digest=kill_criteria_approval_digest,
        )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)
        verified_source_packet_digest = expected_source_packet_digest

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
        source_packet_id=_snapshot_text(snapshot, "packet_id"),
        source_packet_rights_status=_snapshot_text(snapshot, "rights_status"),
        source_packet_usable_for_compilation=usable,
        expected_source_packet_digest=expected_source_packet_digest,
        verified_source_packet_digest=verified_source_packet_digest,
        data_requirement_keys=keys,
        declared_regime_dependence=declared_regime_dependence,
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        external_fact_needs=needs,
        external_fact_resolutions=resolutions,
        unresolved_external_fact_needs=unresolved,
        external_fact_resolution_trust=_EXTERNAL_FACT_RESOLUTION_TRUST,
        kill_criteria_draft=kill_criteria,
        kill_criteria_digest=edge_kill_criteria_digest(kill_criteria),
        kill_criteria_lifecycle_stage=_KILL_CRITERIA_LIFECYCLE_STAGE,
        kill_criteria_combination_policy=_KILL_CRITERIA_COMBINATION_POLICY,
        kill_criteria_thresholds_approved=kill_criteria_thresholds_approved,
        kill_criteria_approval_reference=kill_criteria_approval_reference,
        kill_criteria_approval_digest=kill_criteria_approval_digest,
        integrity_reason_codes=tuple(integrity),
        verdict_reason_codes=verdict_reasons,
        intake_digest="",
    )
    return replace(seed, intake_digest=edge_idea_intake_evidence_digest(seed))


def _serialize(value: object) -> object:
    if type(value) is EdgeKillCriterion:
        return edge_kill_criterion_to_dict(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def edge_idea_intake_evidence_to_dict(evidence: EdgeIdeaIntakeEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-2 intake evidence, including its self-digest."""

    return {field.name: _serialize(getattr(evidence, field.name)) for field in fields(evidence)}


def edge_idea_intake_evidence_digest(evidence: EdgeIdeaIntakeEvidence) -> str:
    """Recompute the canonical intake digest, excluding only the self-digest field."""

    payload = edge_idea_intake_evidence_to_dict(evidence)
    del payload[_SELF_DIGEST_FIELD]
    return _sha256(_canonical_json(payload))


def _envelope_failures(body: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    if any(body.get(name) != expected for name, expected in _CONSTANT_FIELDS):
        failures.append(_reason("constant_field_mismatch"))
    if any(body.get(name) is not expected for name, expected in EDGE_STRUCTURAL_NON_CLAIM_FLAGS):
        failures.append(_reason("structural_non_claim_violation"))
    integrity = body.get("integrity_reason_codes")
    verdict_codes = body.get("verdict_reason_codes")
    if not _is_canonical_reason_list(integrity) or not _is_canonical_reason_list(verdict_codes):
        failures.append(_reason("reason_codes_noncanonical"))
    status = body.get("status")
    verdict = body.get("gate_verdict")
    if status == EdgeEvidenceStatus.READY.value:
        coherent = verdict != EdgeGateVerdict.NOT_EVALUATED.value and integrity == []
    elif status == EdgeEvidenceStatus.REJECTED.value:
        coherent = verdict == EdgeGateVerdict.NOT_EVALUATED.value and bool(integrity) and verdict_codes == []
    else:
        coherent = False
    advances = status == EdgeEvidenceStatus.READY.value and verdict == EdgeGateVerdict.PASS.value
    if not coherent or body.get("advances") is not advances:
        failures.append(_reason("status_verdict_incoherent"))
    return failures


def _intake_semantic_failures(body: Mapping[str, object]) -> list[str]:
    failures: list[str] = []
    for name in _TEXT_FIELDS:
        value = body.get(name)
        if not _is_plain_text(value) or _scope_violation(value) is not None:  # type: ignore[arg-type]
            failures.append(_reason(f"text_field_invalid:{name}"))
    expected_digest = body.get("expected_source_packet_digest")
    if not _is_hex64(expected_digest) or body.get("verified_source_packet_digest") != expected_digest:
        failures.append(_reason("verified_source_packet_digest_mismatch"))
    rights = body.get("source_packet_rights_status")
    usable = body.get("source_packet_usable_for_compilation")
    # source_packet_id is SourcePacket-owned text: its canonical form is the builder's, so only presence is re-checked.
    if (
        type(body.get("source_packet_id")) is not str
        or body.get("source_packet_id") == ""
        or rights not in _RIGHTS_STATUS_VALUES
        or usable is not (rights != SourcePacketRightsStatus.RESTRICTED.value)
    ):
        failures.append(_reason("source_packet_posture_inconsistent"))
    keys = body.get("data_requirement_keys")
    if type(keys) is not list or not keys or keys != sorted(set(keys)) or not set(keys) <= _DATA_REQUIREMENT_KEY_VALUES:
        failures.append(_reason("data_requirement_keys_noncanonical"))
    needs = body.get("external_fact_needs")
    resolutions = body.get("external_fact_resolutions")
    if not _is_canonical_token_list(needs):
        failures.append(_reason("external_fact_needs_noncanonical"))
        needs = []
    if (
        type(resolutions) is not list
        or any(type(pair) is not list or len(pair) != 2 for pair in resolutions)
        or [pair[0] for pair in resolutions] != sorted({pair[0] for pair in resolutions})
        or any(pair[0] not in needs or not _is_hex64(pair[1]) for pair in resolutions)
    ):
        failures.append(_reason("external_fact_resolutions_noncanonical"))
        resolutions = []
    resolved = {pair[0] for pair in resolutions}  # type: ignore[union-attr]
    unresolved = [need for need in needs if need not in resolved]  # type: ignore[union-attr]
    if body.get("unresolved_external_fact_needs") != unresolved:
        failures.append(_reason("unresolved_external_fact_needs_mismatch"))
    criteria = edge_kill_criteria_from_payload(body.get("kill_criteria_draft"))
    if edge_kill_criteria_digest(criteria) != body.get("kill_criteria_digest"):
        failures.append(_reason("kill_criteria_digest_mismatch"))
    approved = body.get("kill_criteria_thresholds_approved")
    reference = body.get("kill_criteria_approval_reference")
    approval_digest = body.get("kill_criteria_approval_digest")
    if (
        type(approved) is not bool
        or (reference is not None and (not _is_plain_text(reference) or _scope_violation(reference) is not None))  # type: ignore[arg-type]
        or (approval_digest is not None and not _is_hex64(approval_digest))
    ):
        failures.append(_reason("kill_criteria_approval_malformed"))
    fail, needs_external, needs_governance = _intake_verdict_reasons(
        source_packet_usable_for_compilation=usable,
        unresolved_external_fact_needs=unresolved,
        kill_criteria=criteria,
        thresholds_approved=approved,
        approval_reference=reference,
        approval_digest=approval_digest,
    )
    rederived = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
    if list(_sorted_unique(fail + needs_external + needs_governance)) != body.get(
        "verdict_reason_codes"
    ) or rederived.value != body.get("gate_verdict"):
        failures.append(_reason("verdict_rederivation_mismatch"))
    return failures


def verify_edge_idea_intake_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-2 intake evidence: exact type, self-digest, constants, non-claims, status/verdict coherence, and
    (when READY) the verdict re-derived from the carried fields. Never raises on forged input."""

    if (
        type(evidence) is not EdgeIdeaIntakeEvidence
        or type(evidence.status) is not EdgeEvidenceStatus
        or type(evidence.gate_verdict) is not EdgeGateVerdict
    ):
        return EdgeEvidenceVerification(False, (_reason("evidence_type_invalid"),), "", "")
    try:
        canonical = _canonical_json(edge_idea_intake_evidence_to_dict(evidence))
        snapshot = json.loads(canonical)
    except Exception:  # noqa: BLE001 - a forged or non-serializable artifact must fail closed, never crash
        return EdgeEvidenceVerification(False, (_reason("evidence_serialization_failed"),), "", "")
    body = dict(snapshot)
    carried = body.pop(_SELF_DIGEST_FIELD, None)
    recomputed = _sha256(_canonical_json(body))
    failures: list[str] = []
    if carried != recomputed:
        failures.append(_reason("self_digest_mismatch"))
    failures.extend(_envelope_failures(body))
    if body.get("status") == EdgeEvidenceStatus.READY.value:
        try:
            failures.extend(_intake_semantic_failures(body))
        except Exception:  # noqa: BLE001 - malformed carried semantics fail closed
            failures.append(_reason("evidence_semantics_malformed"))
    codes = _sorted_unique(failures)
    return EdgeEvidenceVerification(
        intact=not codes, reason_codes=codes, recomputed_digest=recomputed, canonical_json=canonical
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
    "EdgeKillCriterion",
    "EdgeKillCriterionComparator",
    "build_edge_idea_intake_evidence",
    "canonical_edge_kill_criteria",
    "edge_idea_intake_evidence_digest",
    "edge_idea_intake_evidence_to_dict",
    "edge_kill_criteria_digest",
    "edge_kill_criteria_from_payload",
    "edge_kill_criterion_to_dict",
    "resolve_edge_gate_verdict",
    "verify_edge_idea_intake_evidence",
]
