"""Edge Factory trust kernel shared by the EF-2, EF-3 and EF-4 evidence gates.

This module is deliberately small. It holds only the shared trust concepts whose duplication across gates produced
repeated authority-binding and verifier-boundary defects:

* ``EdgeEvidenceStatus`` (trust/integrity only) and ``EdgeGateVerdict`` (gate outcome only), with one verdict
  precedence rule;
* ``EdgeEvidenceVerification``, the result of re-proving an artifact;
* ``EdgeAuthorityBinding`` — the one typed representation of consumed upstream authority. A PRESENT binding holds
  the canonical JSON of a non-empty upstream snapshot object together with the caller's lowercase hex64 anchor, and
  that snapshot must satisfy the owning authority's strict shape predicate. Absent optional authority is ``None``;
  there is no empty or partially populated binding. The SAME shape predicate gates construction (a construction
  error) and parsing (a verification failure), so ``BUILDER_DOMAIN_EQ_VERIFIER_REASSEMBLY_DOMAIN`` holds for every
  binding;
* ``verify_edge_artifact_total`` — the one verifier boundary. Exact-type checking, attribute extraction,
  serialization, strict parsing, self-digest recomputation, reassembly and field comparison all run inside it, so a
  public ``verify_edge_*`` returns an ``EdgeEvidenceVerification`` for ANY Python object
  (``VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT``);
* canonical JSON and SHA-256 primitives, the structural non-claim flags, the regime pending pattern and the single
  Edge Factory scope policy.

Gate-specific business semantics stay in the gate modules. No IO, clock, randomness, network or environment access;
paper-only.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum

SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")
_BINDING_KEYS = frozenset({"expected_digest", "snapshot"})

EDGE_REGIME_LABEL_BINDING_PENDING = "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
EDGE_REGIME_EVIDENCE_UNAVAILABLE = "regime_evidence_unavailable"

# Structural non-claims shared by every Edge Factory artifact: declared as dataclass defaults that no builder
# parameter can set, serialized into the digest, and re-proven by reassembly.
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

# Token starts are delimited by any non-alphanumeric character, underscore included, so snake_case embeddings
# ("carry_scheduler_loop", "funding_bist30") are caught; "kap" and "live" must stand alone ("kappa", "delivery" pass).
_BIST_PATTERN = re.compile(r"(?<![a-z0-9])(?:bist|borsa|matriks)|(?<![a-z0-9])kap(?![a-z0-9])", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![a-z0-9])(?:private_api|private_key|api_key|api_secret|credential|order_router|place_order|live_order"
    r"|real_order|order_id|auto_loop|shadow_live_execution|scheduler)"
    r"|(?<![a-z0-9])live(?![a-z0-9])",
    re.IGNORECASE,
)


class EdgeArtifactError(RuntimeError):
    """Base construction error of the Edge Factory gates; each gate raises its own subclass."""


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


@dataclass(frozen=True)
class EdgeEvidenceVerification:
    """Result of re-proving one Edge Factory artifact.

    Consumers read ``canonical_json`` (an immutable, digest-bound snapshot) instead of re-reading the object.
    """

    intact: bool
    reason_codes: tuple[str, ...]
    recomputed_digest: str
    canonical_json: str


@dataclass(frozen=True)
class EdgeAuthorityBinding:
    """One consumed upstream authority: canonical snapshot JSON of a non-empty object plus its expected digest.

    Only ``build_edge_authority_binding`` and ``parse_edge_authority_binding`` produce accepted bindings; both
    enforce canonical form, a lowercase hex64 anchor and the owning authority's shape predicate.
    """

    snapshot_json: str
    expected_digest: str


def edge_canonical_json(payload: object) -> str:
    """Canonical JSON: sorted keys, compact separators, ASCII-safe, no NaN or Infinity."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def edge_sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def edge_payload_digest(payload: Mapping[str, object], self_digest_field: str) -> str:
    """SHA-256 of the canonical payload with only its self-digest field removed."""

    body = dict(payload)
    del body[self_digest_field]
    return edge_sha256_text(edge_canonical_json(body))


def edge_is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def edge_scope_violation(text: str) -> str | None:
    """The single Edge Factory scope policy: ``bist_scope_leakage``, ``forbidden_scope_token`` or None."""

    if _BIST_PATTERN.search(text):
        return "bist_scope_leakage"
    if _FORBIDDEN_PATTERN.search(text):
        return "forbidden_scope_token"
    return None


def resolve_edge_gate_verdict(
    fail_reasons: Sequence[str],
    needs_external_fact_reasons: Sequence[str],
    needs_governance_reasons: Sequence[str],
) -> EdgeGateVerdict:
    """FAIL dominates, then NEEDS_EXTERNAL_FACTS, then NEEDS_GOVERNANCE_APPROVAL; otherwise PASS."""

    if fail_reasons:
        return EdgeGateVerdict.FAIL
    if needs_external_fact_reasons:
        return EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    if needs_governance_reasons:
        return EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    return EdgeGateVerdict.PASS


def _reject_json_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON constant {value}")


def _shape_holds(shape: Callable[[dict], bool], snapshot: object) -> bool:
    try:
        return type(snapshot) is dict and bool(snapshot) and shape(snapshot) is True
    except Exception:  # noqa: BLE001 - a shape predicate that cannot evaluate a snapshot rejects it
        return False


def build_edge_authority_binding(
    *,
    snapshot_payload: object,
    expected_digest: object,
    shape: Callable[[dict], bool],
    error: type[EdgeArtifactError],
    code: str,
) -> EdgeAuthorityBinding:
    """Construct a PRESENT binding from an upstream JSON-ready snapshot and the caller's anchor.

    Raises ``error`` with ``<code>_expected_digest_invalid`` for a non-hex64 anchor and ``<code>_not_serializable`` for
    a snapshot that is not a canonical-serializable non-empty object satisfying ``shape``.
    """

    if not edge_is_hex64(expected_digest):
        raise error(f"{code}_expected_digest_invalid")
    try:
        snapshot_json = edge_canonical_json(snapshot_payload)
        snapshot = json.loads(snapshot_json, parse_constant=_reject_json_constant)
    except Exception as exc:  # noqa: BLE001 - a malformed upstream object is a construction error, never a receipt
        raise error(f"{code}_not_serializable") from exc
    if not _shape_holds(shape, snapshot):
        raise error(f"{code}_not_serializable")
    return EdgeAuthorityBinding(snapshot_json=snapshot_json, expected_digest=expected_digest)  # type: ignore[arg-type]


def require_edge_authority_binding(
    binding: object,
    *,
    shape: Callable[[dict], bool],
    error: type[EdgeArtifactError],
    code: str,
    optional: bool,
) -> EdgeAuthorityBinding | None:
    """Return ``binding`` only when it is exactly a state the construction rules can produce; raise otherwise."""

    if binding is None:
        if optional:
            return None
        raise error(f"{code}_binding_missing")
    if type(binding) is not EdgeAuthorityBinding:
        raise error(f"{code}_binding_malformed")
    snapshot_json = getattr(binding, "snapshot_json", None)
    if type(snapshot_json) is not str or not edge_is_hex64(getattr(binding, "expected_digest", None)):
        raise error(f"{code}_binding_malformed")
    try:
        snapshot = json.loads(snapshot_json, parse_constant=_reject_json_constant)
    except ValueError as exc:
        raise error(f"{code}_binding_malformed") from exc
    if not _shape_holds(shape, snapshot) or edge_canonical_json(snapshot) != snapshot_json:
        raise error(f"{code}_binding_malformed")
    return binding


def edge_authority_binding_snapshot(binding: EdgeAuthorityBinding) -> dict:
    """The snapshot object of a binding already accepted by ``require_edge_authority_binding``."""

    return json.loads(binding.snapshot_json)


def edge_authority_binding_to_payload(binding: EdgeAuthorityBinding | None) -> dict | None:
    """Serialized form: ``{"expected_digest": <hex64>, "snapshot": <object>}`` or ``None``.

    Only a canonical binding serializes; any other state raises ``ValueError`` instead of being silently canonicalized.
    """

    if binding is None:
        return None
    if (
        type(binding) is not EdgeAuthorityBinding
        or type(binding.snapshot_json) is not str
        or not edge_is_hex64(binding.expected_digest)
    ):
        raise ValueError("edge authority binding is not canonical")
    snapshot = json.loads(binding.snapshot_json, parse_constant=_reject_json_constant)
    if type(snapshot) is not dict or not snapshot or edge_canonical_json(snapshot) != binding.snapshot_json:
        raise ValueError("edge authority binding is not canonical")
    return {"expected_digest": binding.expected_digest, "snapshot": snapshot}


def parse_edge_authority_binding(
    value: object,
    *,
    shape: Callable[[dict], bool],
    error: type[EdgeArtifactError],
    code: str,
    optional: bool,
) -> EdgeAuthorityBinding | None:
    """Strictly parse a serialized binding: exact keys, hex64 anchor, non-empty object snapshot satisfying ``shape``."""

    if value is None:
        if optional:
            return None
        raise error(f"{code}_binding_missing")
    if type(value) is not dict or set(value) != _BINDING_KEYS or not edge_is_hex64(value["expected_digest"]):
        raise error(f"{code}_binding_malformed")
    snapshot = value["snapshot"]
    if not _shape_holds(shape, snapshot):
        raise error(f"{code}_binding_malformed")
    try:
        snapshot_json = edge_canonical_json(snapshot)
    except ValueError as exc:
        raise error(f"{code}_binding_malformed") from exc
    return EdgeAuthorityBinding(snapshot_json=snapshot_json, expected_digest=value["expected_digest"])


def verify_edge_artifact_total(
    artifact: object,
    *,
    cls: type,
    to_payload: Callable[[object], dict],
    parse_payload: Callable[[dict], object],
    reassemble: Callable[[object], object],
    self_digest_field: str,
    reason: Callable[[str], str],
) -> EdgeEvidenceVerification:
    """The total verifier boundary: returns a verification for ANY object and never raises.

    Stages (each failing closed with its own reason code): exact type → serialization → strict parse → self-digest
    recomputation → reassembly through the gate's single assembly path → field-by-field canonical comparison.
    """

    stage = "evidence_type_invalid"
    try:
        if type(artifact) is not cls:
            return EdgeEvidenceVerification(False, (reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        canonical = edge_canonical_json(to_payload(artifact))
        carried = json.loads(canonical)
        stage = "evidence_parse_failed"
        parsed = parse_payload(carried)
        recomputed = edge_payload_digest(carried, self_digest_field)
        stage = "evidence_reassembly_failed"
        expected = json.loads(edge_canonical_json(to_payload(reassemble(parsed))))
        codes: set[str] = set()
        if carried[self_digest_field] != recomputed:
            codes.add(reason("self_digest_mismatch"))
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(
            intact=not reason_codes, reason_codes=reason_codes, recomputed_digest=recomputed, canonical_json=canonical
        )
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (reason(stage),), "", "")


__all__ = [
    "EDGE_REGIME_EVIDENCE_UNAVAILABLE",
    "EDGE_REGIME_LABEL_BINDING_PENDING",
    "EDGE_STRUCTURAL_NON_CLAIM_FLAGS",
    "SHA256_HEX_LENGTH",
    "EdgeArtifactError",
    "EdgeAuthorityBinding",
    "EdgeEvidenceStatus",
    "EdgeEvidenceVerification",
    "EdgeGateVerdict",
    "build_edge_authority_binding",
    "edge_authority_binding_snapshot",
    "edge_authority_binding_to_payload",
    "edge_canonical_json",
    "edge_is_hex64",
    "edge_payload_digest",
    "edge_scope_violation",
    "edge_sha256_text",
    "parse_edge_authority_binding",
    "require_edge_authority_binding",
    "resolve_edge_gate_verdict",
    "verify_edge_artifact_total",
]
