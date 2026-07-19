"""Machine-time provenance policy artifact (MT-2 — abstract, pre-Deep-Research-safe).

This module pins the governance-owned STRUCTURE of the machine-time "sandwich" model that later
machine-time artifacts (MT-3 source registry, MT-4 anchor evidence, MT-5 machine-proven day, MT-6
machine-proven 30-day gate) must obey. A day's evidence is provably inside a real-time interval only when
it is sandwiched between two independent external time proofs:

* a **not_before** proof — an unpredictable public beacon value embedded INTO the attested-day metadata at
  seal time (the day digest cannot pre-date the beacon value); and
* a **not_after** proof — an external signed timestamp that COMMITS TO the day self-digest (the digest
  existed no later than the signed time),

with a QUORUM of at least two independent source classes on each side, ROLE SEPARATION between the two
sides, EXACT digest commitment, DETERMINISTIC OFFLINE verification of supplied proofs (no network fetch in
any builder), a UTC-day identity + proof-replay policy (one distinct sandwich per UTC day, proof identities
never reused across days), and a SPACING rule so that >= 30 machine-proven days require >= 30 distinct
sandwiches whose intervals are consistent with ~30 real elapsed days.

MT-2 is deliberately ABSTRACT and pre-Deep-Research-safe: it pins the required roles, the quorum minimum,
abstract verification/independence/offline/day-identity/replay/source-registry policy identifiers, the
spacing bounds, and the canonical proof-encoding and digest-commitment policies, and it requires explicit
governance approval of the numeric policy values. It binds NO concrete provider name, endpoint, beacon
format, signature scheme, timestamping-authority semantic, clock-skew tolerance, or proof-format wire
version — every such fact is Deep-Research-gated and belongs to MT-3+ (the concrete source registry). It
consumes no attested day, no anchor, no external proof, and no runtime/live/venue state. A READY policy
proves only that the supplied structure metadata is well-formed and governance-approved; it never proves
that any machine-time anchor was verified, that time origin was proven, that a concrete source registry was
bound, or that injected/attested time may substitute for a machine proof.

Trust-boundary discipline: no caller-carried value participates in equality, ordering, arithmetic, sorting,
set construction, hashing, scope scanning, output projection, or serialization until its exact expected
built-in type and canonical representation have been proven. A JSON-serializable ``str``/``int`` subclass
with lying equality can never satisfy a protected comparison; a malformed value is safely projected to a
deterministic JSON-only built-in so every REJECTED artifact still serializes and self-digests.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, fields
from enum import Enum

_SCHEMA_VERSION = "machine-time-policy.v1"
_POLICY_VERSION = "machine-time-policy.v1"
_REASON_PREFIX = "machine_time_policy"
_SHA256_HEX_LENGTH = 64
_HEX_CHARS = frozenset("0123456789abcdef")

# One UTC day in nanoseconds. Used only as a structural sanity bound: the governance-approved spacing
# window must actually contain one real day, so that a "30-day" gate can never be satisfied by 30
# sandwiches compressed into a single afternoon.
_DAY_NS = 86_400_000_000_000

# Structural minimums pinned by the sandwich model. Governance may approve stricter values but never
# weaker ones.
_MIN_QUORUM_PER_ROLE = 2
_MIN_MACHINE_PROVEN_DAY_COUNT = 30

# Abstract, provider-free structure identifiers. These describe the sandwich VERIFICATION APPROACH, never a
# concrete provider, endpoint, wire format, or Deep-Research fact.
_SANDWICH_MODEL = "not_before_beacon_and_not_after_signed_timestamp_sandwich.v1"
_REQUIRED_ROLES = ("not_before", "not_after")
_NOT_BEFORE_VERIFICATION_POLICY = "unpredictable_public_beacon_embedded_pre_seal.v1"
_NOT_AFTER_VERIFICATION_POLICY = "external_signed_timestamp_commits_to_day_self_digest.v1"
_QUORUM_MODEL = "independent_source_classes_per_role.v1"
_INDEPENDENCE_POLICY_ID = "minimum_two_independent_source_classes_per_role.v1"
_DIGEST_COMMITMENT_POLICY = "not_after_proof_commits_to_exact_day_self_digest.v1"
_PROOF_ENCODING_POLICY = "canonical_deterministic_proof_bytes_no_fetch_at_verify.v1"
_OFFLINE_VERIFICATION_POLICY_ID = "deterministic_supplied_proof_verification_no_network.v1"
_UTC_DAY_IDENTITY_POLICY_ID = "distinct_consecutive_utc_day_identity.v1"
_PROOF_REPLAY_POLICY_ID = "proof_identity_reuse_across_days_forbidden.v1"
_SPACING_POLICY = "consecutive_utc_days_monotonic_nonoverlapping_interval_consistent.v1"
_SOURCE_REGISTRY_POLICY_ID = "concrete_source_registry_required_post_deep_research.v1"

_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id|readiness|service|real_money|paper_adapter|"
    r"capital|margin|balance|reservation|real_account_equity|account_equity|real_equity)\w*"
    r"|crypto_core\.(?:service|execution|venue|runtime|orchestrator|temporal|session|data|portfolio)\b"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")
# Live wall-clock / ambient-time tokens forbidden in caller-supplied identifiers and metadata: MT proves
# time EXISTENCE from external cryptographic proofs supplied as inputs, never from a runtime clock read.
_CLOCK_TOKENS = (
    "wall_clock",
    "wall-clock",
    "wallclock",
    "datetime.now",
    "datetime.utcnow",
    "utcnow",
    "time.time_ns",
    "time.time",
    "perf_counter",
    "monotonic",
    "server_time",
    "exchange_time",
    "live_time",
    "real_time",
    "realtime",
    "system_time",
    "now()",
)


class MachineTimePolicyError(RuntimeError):
    """Raised on malformed caller input or a malformed artifact at the MT-2 public boundary."""


class MachineTimePolicyStatus(str, Enum):
    """MT-2 policy status. READY is policy-structure readiness only, never machine-time proof."""

    POLICY_READY = "POLICY_READY"
    POLICY_REJECTED = "POLICY_REJECTED"


@dataclass(frozen=True)
class MachineTimePolicy:
    """Immutable, digest-bound abstract machine-time sandwich policy (MT-2).

    READY only when governance approval metadata and the governance-approved structural values (quorum per
    role, required machine-proven day count, inter-day spacing bounds) are present and well-formed, and
    every pinned structure identifier matches exactly. It binds no concrete provider fact, consumes no
    external proof, and proves no machine time.
    """

    schema_version: str
    policy_version: str
    status: MachineTimePolicyStatus
    ready: bool
    policy_id: str
    correlation_id: str
    sandwich_model: str
    required_roles: tuple[str, ...]
    not_before_verification_policy: str
    not_after_verification_policy: str
    quorum_model: str
    independence_policy_id: str
    digest_commitment_policy: str
    proof_encoding_policy: str
    offline_verification_policy_id: str
    utc_day_identity_policy_id: str
    proof_replay_policy_id: str
    spacing_policy: str
    source_registry_policy_id: str
    min_quorum_per_role: int
    min_machine_proven_day_count: int
    utc_day_ns: int
    approved_quorum_per_role: int | None
    approved_required_machine_proven_day_count: int | None
    approved_min_inter_day_spacing_ns: int | None
    approved_max_inter_day_spacing_ns: int | None
    approval_reference: str | None
    approval_digest: str | None
    policy_approved: bool
    source_registry_digest: str | None
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    policy_only: bool = True
    abstract_pre_deep_research: bool = True
    independent_source_classes_required: bool = True
    role_separation_required: bool = True
    exact_digest_commitment_required: bool = True
    deterministic_offline_verification_required: bool = True
    network_fetch_in_builder_forbidden: bool = True
    distinct_sandwich_per_utc_day_required: bool = True
    proof_reuse_across_days_forbidden: bool = True
    consecutive_utc_days_required: bool = True
    interval_consistency_required: bool = True
    concrete_source_registry_required: bool = True
    concrete_source_registry_bound: bool = False
    source_registry_consumed: bool = False
    deep_research_facts_bound: bool = False
    concrete_sources_bound: bool = False
    machine_time_anchor_verified: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    injected_time_accepted_as_proof: bool = False
    attested_time_accepted_as_proof: bool = False
    external_proofs_consumed: bool = False
    operational_days_consumed: bool = False
    machine_proven_days_consumed: bool = False
    network_fetch_performed: bool = False
    real_wall_clock_used: bool = False
    thirty_day_gate_decided: bool = False
    stage4_completion_decided: bool = False
    prdv4_stage4_complete: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    capital_mutation_enabled: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_plain_non_empty_string(value: object) -> bool:
    return (
        type(value) is str
        and value.strip() != ""
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _is_exact_int(value: object) -> bool:
    return type(value) is int and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return type(value) is str and len(value) == _SHA256_HEX_LENGTH and all(char in _HEX_CHARS for char in value)


def _is_plain_string_tuple(value: object) -> bool:
    return type(value) is tuple and all(_is_plain_non_empty_string(item) for item in value)


# Exact-type-before-operation helpers. Each proves the exact built-in type BEFORE any equality, so a lying
# ``str``/``int`` subclass or an equality/hash/order-raising object can never have its custom operation
# invoked from a protected comparison.


def _eq_plain_str(value: object, expected: str) -> bool:
    return type(value) is str and value == expected


def _eq_exact_int(value: object, expected: int) -> bool:
    return _is_exact_int(value) and value == expected


def _safe_pinned_string(value: object) -> str:
    """A valid exact plain string may remain visible (even if it mismatches); anything else projects to ``""``."""

    return value if _is_plain_non_empty_string(value) else ""  # type: ignore[return-value]


def _safe_roles(value: object) -> tuple[str, ...]:
    return value if _is_plain_string_tuple(value) else ()  # type: ignore[return-value]


def _safe_optional_int(value: object) -> int | None:
    return value if _is_exact_int(value) else None  # type: ignore[return-value]


def _safe_optional_reference(value: object) -> str | None:
    return value if _is_plain_non_empty_string(value) else None  # type: ignore[return-value]


def _safe_optional_digest(value: object) -> str | None:
    return value if _is_hex64_string(value) else None  # type: ignore[return-value]


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise MachineTimePolicyError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _is_canonical_text(value: object) -> bool:
    """Exact built-in ``str`` that is stripped and free of ASCII control/DEL characters (empty allowed)."""

    return (
        type(value) is str and value == value.strip() and not any(ord(char) < 32 or ord(char) == 127 for char in value)
    )


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    # Exact-container-before-operation: the metadata mapping must be exactly ``None`` or a built-in ``dict``
    # BEFORE any ``.items()`` / iteration / sort. A custom ``Mapping``, ``Mapping`` subclass, or ``dict``
    # subclass with overridden iteration must never have its caller-controlled methods invoked here.
    if metadata is None:
        return ()
    if type(metadata) is not dict:
        raise MachineTimePolicyError(_reason("metadata_malformed"))
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if type(key) is not str or type(value) is not str:
            raise MachineTimePolicyError(_reason("metadata_malformed"))
        if key != key.strip() or value != value.strip() or any(ord(char) < 32 or ord(char) == 127 for char in key):
            raise MachineTimePolicyError(_reason("metadata_malformed"))
        if any(ord(char) < 32 or ord(char) == 127 for char in value):
            raise MachineTimePolicyError(_reason("metadata_malformed"))
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _serialize_metadata(metadata: tuple[tuple[str, str], ...]) -> list[list[str]]:
    return [[key, value] for key, value in metadata]


def _has_bist_token(*texts: object) -> bool:
    return any(type(text) is str and text != "" and _BIST_PATTERN.search(text) for text in texts)


def _has_clock_token(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        lowered = text.lower()
        if any(token in lowered for token in _CLOCK_TOKENS):
            return True
    return False


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if type(text) is not str or text == "":
            continue
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


# Every caller-exposed pinned structure identifier and its precise, stable mismatch reason. Precise
# per-field reasons (never a single ``structure_mismatch``) keep later MT diagnostics actionable.
_PINNED_STRING_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("sandwich_model", _SANDWICH_MODEL, "sandwich_model_mismatch"),
    ("not_before_verification_policy", _NOT_BEFORE_VERIFICATION_POLICY, "not_before_verification_policy_mismatch"),
    ("not_after_verification_policy", _NOT_AFTER_VERIFICATION_POLICY, "not_after_verification_policy_mismatch"),
    ("quorum_model", _QUORUM_MODEL, "quorum_model_mismatch"),
    ("independence_policy_id", _INDEPENDENCE_POLICY_ID, "independence_policy_mismatch"),
    ("digest_commitment_policy", _DIGEST_COMMITMENT_POLICY, "digest_commitment_policy_mismatch"),
    ("proof_encoding_policy", _PROOF_ENCODING_POLICY, "proof_encoding_policy_mismatch"),
    ("offline_verification_policy_id", _OFFLINE_VERIFICATION_POLICY_ID, "offline_verification_policy_mismatch"),
    ("utc_day_identity_policy_id", _UTC_DAY_IDENTITY_POLICY_ID, "utc_day_identity_policy_mismatch"),
    ("proof_replay_policy_id", _PROOF_REPLAY_POLICY_ID, "proof_replay_policy_mismatch"),
    ("spacing_policy", _SPACING_POLICY, "spacing_policy_mismatch"),
    ("source_registry_policy_id", _SOURCE_REGISTRY_POLICY_ID, "source_registry_policy_mismatch"),
)


def _pinned_string_failure(value: object, expected: str, mismatch_reason: str) -> str | None:
    """Exact-type gate: a non-exact-plain-string is a type defect; a valid exact string may only mismatch."""

    if not _is_plain_non_empty_string(value):
        return _reason("policy_field_type_invalid")
    if value != expected:  # safe: exact ``str`` proven, builtin ``str.__eq__`` only
        return _reason(mismatch_reason)
    return None


def _required_roles_failure(value: object) -> str | None:
    if not _is_plain_string_tuple(value):
        return _reason("policy_field_type_invalid")
    if value != _REQUIRED_ROLES:  # safe: exact tuple of exact ``str`` proven
        return _reason("required_roles_mismatch")
    return None


def _quorum_failures(value: object) -> list[str]:
    if value is None:
        return [_reason("approved_quorum_per_role_missing")]
    if not _is_exact_int(value) or value < _MIN_QUORUM_PER_ROLE:
        return [_reason("approved_quorum_per_role_invalid")]
    return []


def _day_count_failures(value: object) -> list[str]:
    if value is None:
        return [_reason("approved_required_machine_proven_day_count_missing")]
    if not _is_exact_int(value) or value < _MIN_MACHINE_PROVEN_DAY_COUNT:
        return [_reason("approved_required_machine_proven_day_count_invalid")]
    return []


def _spacing_failures(min_value: object, max_value: object) -> list[str]:
    """Governance-approved inter-day spacing bounds must be positive ints that straddle one real UTC day.

    Requiring ``min <= _DAY_NS <= max`` makes the spacing window actually admit ~1 elapsed day per step, so
    a later 30-day gate cannot be satisfied by 30 sandwiches compressed into far less than 30 real days.
    """

    hard: list[str] = []
    min_ok = _is_exact_int(min_value) and min_value > 0
    max_ok = _is_exact_int(max_value)
    if min_value is None:
        hard.append(_reason("approved_min_inter_day_spacing_ns_missing"))
    elif not min_ok:
        hard.append(_reason("approved_min_inter_day_spacing_ns_invalid"))
    if max_value is None:
        hard.append(_reason("approved_max_inter_day_spacing_ns_missing"))
    elif not max_ok:
        hard.append(_reason("approved_max_inter_day_spacing_ns_invalid"))
    if min_ok and max_ok and max_value < min_value:
        hard.append(_reason("approved_max_inter_day_spacing_ns_invalid"))
    if min_ok and max_ok and max_value >= min_value and not (min_value <= _DAY_NS <= max_value):
        hard.append(_reason("spacing_window_excludes_utc_day"))
    return hard


def _sorted_unique(reasons: list[str]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def build_machine_time_policy(
    *,
    policy_id: str,
    correlation_id: str,
    approved_quorum_per_role: int | None = None,
    approved_required_machine_proven_day_count: int | None = None,
    approved_min_inter_day_spacing_ns: int | None = None,
    approved_max_inter_day_spacing_ns: int | None = None,
    approval_reference: str | None = None,
    approval_digest: str | None = None,
    policy_approved: bool = False,
    sandwich_model: str = _SANDWICH_MODEL,
    required_roles: tuple[str, ...] = _REQUIRED_ROLES,
    not_before_verification_policy: str = _NOT_BEFORE_VERIFICATION_POLICY,
    not_after_verification_policy: str = _NOT_AFTER_VERIFICATION_POLICY,
    quorum_model: str = _QUORUM_MODEL,
    independence_policy_id: str = _INDEPENDENCE_POLICY_ID,
    digest_commitment_policy: str = _DIGEST_COMMITMENT_POLICY,
    proof_encoding_policy: str = _PROOF_ENCODING_POLICY,
    offline_verification_policy_id: str = _OFFLINE_VERIFICATION_POLICY_ID,
    utc_day_identity_policy_id: str = _UTC_DAY_IDENTITY_POLICY_ID,
    proof_replay_policy_id: str = _PROOF_REPLAY_POLICY_ID,
    spacing_policy: str = _SPACING_POLICY,
    source_registry_policy_id: str = _SOURCE_REGISTRY_POLICY_ID,
    metadata: dict[str, str] | None = None,
) -> MachineTimePolicy:
    """Build a deterministic abstract MT-2 machine-time policy artifact (fail-closed, trust-boundary hardened).

    Governance-owned structural values are accepted only when explicitly supplied with approval metadata and
    an approval flag; missing, malformed, or unapproved values produce ``POLICY_REJECTED`` rather than
    defaults, and every safely handleable malformed value is projected to a deterministic JSON-only built-in
    so the REJECTED artifact still serializes and self-digests. Only wrong-typed ``policy_id`` /
    ``correlation_id`` / ``policy_approved`` / ``metadata`` raise ``MachineTimePolicyError``; every structure
    or value failure maps to ``status=POLICY_REJECTED``. No caller value participates in a protected
    equality before its exact built-in type is proven, so a lying ``str``/``int`` subclass can never forge
    READY and an equality/hash/order-raising object never has its custom operation invoked.
    """

    policy_id = _require_plain_non_empty_string(policy_id, "policy_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    if type(policy_approved) is not bool:
        raise MachineTimePolicyError(_reason("policy_approved_invalid"))

    metadata_pairs = _normalize_metadata(metadata)
    hard: list[str] = []

    if policy_approved is not True:
        hard.append(_reason("policy_not_approved"))

    supplied_pinned = {
        "sandwich_model": sandwich_model,
        "not_before_verification_policy": not_before_verification_policy,
        "not_after_verification_policy": not_after_verification_policy,
        "quorum_model": quorum_model,
        "independence_policy_id": independence_policy_id,
        "digest_commitment_policy": digest_commitment_policy,
        "proof_encoding_policy": proof_encoding_policy,
        "offline_verification_policy_id": offline_verification_policy_id,
        "utc_day_identity_policy_id": utc_day_identity_policy_id,
        "proof_replay_policy_id": proof_replay_policy_id,
        "spacing_policy": spacing_policy,
        "source_registry_policy_id": source_registry_policy_id,
    }
    for field_name, expected, mismatch_reason in _PINNED_STRING_FIELDS:
        failure = _pinned_string_failure(supplied_pinned[field_name], expected, mismatch_reason)
        if failure is not None:
            hard.append(failure)
    roles_failure = _required_roles_failure(required_roles)
    if roles_failure is not None:
        hard.append(roles_failure)

    hard.extend(_quorum_failures(approved_quorum_per_role))
    hard.extend(_day_count_failures(approved_required_machine_proven_day_count))
    hard.extend(_spacing_failures(approved_min_inter_day_spacing_ns, approved_max_inter_day_spacing_ns))

    if not _is_plain_non_empty_string(approval_reference):
        hard.append(_reason("approval_reference_missing"))
    if not _is_hex64_string(approval_digest):
        hard.append(_reason("approval_digest_invalid"))

    scope_texts = (policy_id, correlation_id, approval_reference, *_metadata_texts(metadata_pairs))
    if _has_bist_token(*scope_texts):
        hard.append(_reason("bist_token_forbidden"))
    if _has_clock_token(*scope_texts):
        hard.append(_reason("clock_token_forbidden"))
    if _has_scope_violation(*scope_texts):
        hard.append(_reason("scope_violation"))

    reason_codes = _sorted_unique(hard)
    ready = not reason_codes

    # Defensive READY invariant: READY is impossible unless every pinned structure identifier equals its
    # constant, the required roles match, and every approved value is present, exact-typed, and within its
    # governance floor. This re-proves the safety conclusion on the ORIGINAL caller inputs.
    if ready and not (
        _eq_plain_str(sandwich_model, _SANDWICH_MODEL)
        and _eq_plain_str(not_before_verification_policy, _NOT_BEFORE_VERIFICATION_POLICY)
        and _eq_plain_str(not_after_verification_policy, _NOT_AFTER_VERIFICATION_POLICY)
        and _eq_plain_str(quorum_model, _QUORUM_MODEL)
        and _eq_plain_str(independence_policy_id, _INDEPENDENCE_POLICY_ID)
        and _eq_plain_str(digest_commitment_policy, _DIGEST_COMMITMENT_POLICY)
        and _eq_plain_str(proof_encoding_policy, _PROOF_ENCODING_POLICY)
        and _eq_plain_str(offline_verification_policy_id, _OFFLINE_VERIFICATION_POLICY_ID)
        and _eq_plain_str(utc_day_identity_policy_id, _UTC_DAY_IDENTITY_POLICY_ID)
        and _eq_plain_str(proof_replay_policy_id, _PROOF_REPLAY_POLICY_ID)
        and _eq_plain_str(spacing_policy, _SPACING_POLICY)
        and _eq_plain_str(source_registry_policy_id, _SOURCE_REGISTRY_POLICY_ID)
        and _is_plain_string_tuple(required_roles)
        and required_roles == _REQUIRED_ROLES
        and _is_exact_int(approved_quorum_per_role)
        and approved_quorum_per_role >= _MIN_QUORUM_PER_ROLE
        and _is_exact_int(approved_required_machine_proven_day_count)
        and approved_required_machine_proven_day_count >= _MIN_MACHINE_PROVEN_DAY_COUNT
        and _is_exact_int(approved_min_inter_day_spacing_ns)
        and _is_exact_int(approved_max_inter_day_spacing_ns)
        and _is_plain_non_empty_string(approval_reference)
        and _is_hex64_string(approval_digest)
        and policy_approved is True
    ):
        reason_codes = (_reason("ready_invariant_failed"),)
        ready = False

    status = MachineTimePolicyStatus.POLICY_READY if ready else MachineTimePolicyStatus.POLICY_REJECTED

    policy_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "policy_version": _POLICY_VERSION,
        "status": status,
        "ready": ready,
        "policy_id": policy_id,
        "correlation_id": correlation_id,
        "sandwich_model": _safe_pinned_string(sandwich_model),
        "required_roles": _safe_roles(required_roles),
        "not_before_verification_policy": _safe_pinned_string(not_before_verification_policy),
        "not_after_verification_policy": _safe_pinned_string(not_after_verification_policy),
        "quorum_model": _safe_pinned_string(quorum_model),
        "independence_policy_id": _safe_pinned_string(independence_policy_id),
        "digest_commitment_policy": _safe_pinned_string(digest_commitment_policy),
        "proof_encoding_policy": _safe_pinned_string(proof_encoding_policy),
        "offline_verification_policy_id": _safe_pinned_string(offline_verification_policy_id),
        "utc_day_identity_policy_id": _safe_pinned_string(utc_day_identity_policy_id),
        "proof_replay_policy_id": _safe_pinned_string(proof_replay_policy_id),
        "spacing_policy": _safe_pinned_string(spacing_policy),
        "source_registry_policy_id": _safe_pinned_string(source_registry_policy_id),
        "min_quorum_per_role": _MIN_QUORUM_PER_ROLE,
        "min_machine_proven_day_count": _MIN_MACHINE_PROVEN_DAY_COUNT,
        "utc_day_ns": _DAY_NS,
        "approved_quorum_per_role": _safe_optional_int(approved_quorum_per_role),
        "approved_required_machine_proven_day_count": _safe_optional_int(approved_required_machine_proven_day_count),
        "approved_min_inter_day_spacing_ns": _safe_optional_int(approved_min_inter_day_spacing_ns),
        "approved_max_inter_day_spacing_ns": _safe_optional_int(approved_max_inter_day_spacing_ns),
        "approval_reference": _safe_optional_reference(approval_reference),
        "approval_digest": _safe_optional_digest(approval_digest),
        "policy_approved": policy_approved,
        "source_registry_digest": None,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = MachineTimePolicy(policy_digest="", **policy_fields)  # type: ignore[arg-type]
    return _replace_policy_digest(seed, machine_time_policy_digest(seed))


def _replace_policy_digest(policy: MachineTimePolicy, digest: str) -> MachineTimePolicy:
    values = {field.name: getattr(policy, field.name) for field in fields(policy) if field.name != "policy_digest"}
    values["policy_digest"] = digest
    return MachineTimePolicy(**values)  # type: ignore[arg-type]


# Structural marker flags that must be exactly ``True`` on every legitimate artifact, and non-claim /
# capability flags that must be exactly ``False`` on every legitimate artifact. Any deviation on a forged
# exact dataclass is a malformed artifact — this is what closes the structural-overclaim reseal path: the
# public digest rejects (never reseals) a digest-valid, status-READY policy carrying a forbidden overclaim.
_ARTIFACT_TRUE_FLAGS = (
    "paper_only",
    "policy_only",
    "abstract_pre_deep_research",
    "independent_source_classes_required",
    "role_separation_required",
    "exact_digest_commitment_required",
    "deterministic_offline_verification_required",
    "network_fetch_in_builder_forbidden",
    "distinct_sandwich_per_utc_day_required",
    "proof_reuse_across_days_forbidden",
    "consecutive_utc_days_required",
    "interval_consistency_required",
    "concrete_source_registry_required",
)
_ARTIFACT_FALSE_FLAGS = (
    "concrete_source_registry_bound",
    "source_registry_consumed",
    "deep_research_facts_bound",
    "concrete_sources_bound",
    "machine_time_anchor_verified",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "injected_time_accepted_as_proof",
    "attested_time_accepted_as_proof",
    "external_proofs_consumed",
    "operational_days_consumed",
    "machine_proven_days_consumed",
    "network_fetch_performed",
    "real_wall_clock_used",
    "thirty_day_gate_decided",
    "stage4_completion_decided",
    "prdv4_stage4_complete",
    "operational_readiness",
    "live_ready",
    "shadow_ready",
    "deribit_ready",
    "private_api_ready",
    "live_api_called",
    "real_orders_enabled",
    "real_money_enabled",
    "real_capital_reserved",
    "capital_mutation_enabled",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
    "edge_proven",
    "profitability_proven",
)
# Pinned policy-string fields: an exact built-in ``str`` that is either canonical non-empty (a valid or a
# rejected-but-visible mismatch) or ``""`` (a safely projected malformed value). Never coerced to a pinned
# value at the serialization boundary.
_ARTIFACT_POLICY_STRING_FIELDS = tuple(name for name, _, _ in _PINNED_STRING_FIELDS)


def _is_canonical_or_empty_string(value: object) -> bool:
    return type(value) is str and (value == "" or _is_plain_non_empty_string(value))


def _is_canonical_metadata_pairs(value: object) -> bool:
    if type(value) is not tuple:
        return False
    keys: list[str] = []
    for pair in value:
        if type(pair) is not tuple or len(pair) != 2:
            return False
        key, item = pair
        if not (_is_canonical_text(key) and _is_canonical_text(item)):
            return False
        keys.append(key)
    return value == tuple(sorted(value)) and len(set(keys)) == len(keys)


def _is_canonical_reason_codes(value: object) -> bool:
    if type(value) is not tuple:
        return False
    for reason in value:
        if not _is_plain_non_empty_string(reason) or not reason.startswith(f"{_REASON_PREFIX}:"):
            return False
    return list(value) == sorted(value) and len(set(value)) == len(value)


def _validate_machine_time_policy_artifact(policy: object, *, require_populated_self_digest: bool) -> MachineTimePolicy:
    """Prove the COMPLETE exact runtime + canonical contract of every public field before any traversal.

    Returns the same artifact when it is fully canonical; otherwise raises ``MachineTimePolicyError`` with
    the single deterministic ``malformed_artifact`` reason. No caller-carried field is compared, iterated,
    unpacked, sorted, hashed, or serialized until its exact contract is proven here, so a forged exact
    dataclass can never produce a raw ``AttributeError`` / ``TypeError`` / ``ValueError`` / JSON / unpacking
    / custom-operation exception, and a structural overclaim can never be resealed.
    """

    if type(policy) is not MachineTimePolicy:
        raise MachineTimePolicyError(_reason("malformed_artifact"))

    def _fail() -> None:
        raise MachineTimePolicyError(_reason("malformed_artifact"))

    # Identity / version.
    if not (
        _eq_plain_str(policy.schema_version, _SCHEMA_VERSION)
        and _eq_plain_str(policy.policy_version, _POLICY_VERSION)
        and _is_plain_non_empty_string(policy.policy_id)
        and _is_plain_non_empty_string(policy.correlation_id)
    ):
        _fail()

    # Status / ready / reason coherence.
    if type(policy.status) is not MachineTimePolicyStatus or type(policy.ready) is not bool:
        _fail()
    if not _is_canonical_reason_codes(policy.reason_codes):
        _fail()
    if policy.status is MachineTimePolicyStatus.POLICY_READY:
        if policy.ready is not True or policy.reason_codes != ():
            _fail()
    elif policy.status is MachineTimePolicyStatus.POLICY_REJECTED:
        if policy.ready is not False or policy.reason_codes == ():
            _fail()
    else:  # pragma: no cover - the enum has exactly two members
        _fail()

    # Pinned policy strings (canonical or safely projected "") and required roles.
    for field_name in _ARTIFACT_POLICY_STRING_FIELDS:
        if not _is_canonical_or_empty_string(getattr(policy, field_name)):
            _fail()
    roles = policy.required_roles
    if type(roles) is not tuple or not all(_is_plain_non_empty_string(role) for role in roles):
        _fail()

    # Fixed structural integers.
    if not (
        _eq_exact_int(policy.min_quorum_per_role, _MIN_QUORUM_PER_ROLE)
        and _eq_exact_int(policy.min_machine_proven_day_count, _MIN_MACHINE_PROVEN_DAY_COUNT)
        and _eq_exact_int(policy.utc_day_ns, _DAY_NS)
    ):
        _fail()

    # Optional approved integers (exact int or None; bool / int subclasses excluded).
    for field_name in (
        "approved_quorum_per_role",
        "approved_required_machine_proven_day_count",
        "approved_min_inter_day_spacing_ns",
        "approved_max_inter_day_spacing_ns",
    ):
        value = getattr(policy, field_name)
        if value is not None and not _is_exact_int(value):
            _fail()

    # Approval fields.
    if not (policy.approval_reference is None or _is_plain_non_empty_string(policy.approval_reference)):
        _fail()
    if not (policy.approval_digest is None or _is_hex64_string(policy.approval_digest)):
        _fail()
    if type(policy.policy_approved) is not bool:
        _fail()

    # Source-registry boundary (structurally unbound in MT-2).
    if policy.source_registry_digest is not None:
        _fail()

    # Metadata canonical representation.
    if not _is_canonical_metadata_pairs(policy.metadata):
        _fail()

    # Structural true / false flag identity (closes overclaim reseal + required-invariant weakening).
    for field_name in _ARTIFACT_TRUE_FLAGS:
        if getattr(policy, field_name) is not True:
            _fail()
    for field_name in _ARTIFACT_FALSE_FLAGS:
        if getattr(policy, field_name) is not False:
            _fail()

    # Self-digest: "" only for the internal builder seed (digest path); lowercase hex64 for a built artifact.
    if require_populated_self_digest:
        if not _is_hex64_string(policy.policy_digest):
            _fail()
    elif not (policy.policy_digest == "" or _is_hex64_string(policy.policy_digest)):
        _fail()

    return policy


def _policy_payload_from(policy: MachineTimePolicy) -> dict[str, object]:
    """Build the canonical payload. Callers MUST pass an artifact already proven by the validator."""

    payload: dict[str, object] = {}
    for field in fields(policy):
        if field.name == "policy_digest":
            continue
        value = getattr(policy, field.name)
        if field.name == "status":
            payload[field.name] = policy.status.value
        elif field.name == "metadata":
            payload[field.name] = _serialize_metadata(policy.metadata)
        elif type(value) is tuple:
            payload[field.name] = list(value)
        else:
            payload[field.name] = value
    return payload


def machine_time_policy_to_dict(policy: MachineTimePolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping for the MT-2 policy, including its self-digest.

    Requires an exact ``MachineTimePolicy`` whose every public field is canonical and whose self-digest is a
    populated lowercase hex64; any wrong-typed or malformed artifact raises ``MachineTimePolicyError``
    (``malformed_artifact``) rather than returning a non-JSON mapping or leaking a raw exception. The
    returned mapping always succeeds under the canonical ``json.dumps`` contract.
    """

    validated = _validate_machine_time_policy_artifact(policy, require_populated_self_digest=True)
    payload = _policy_payload_from(validated)
    payload["policy_digest"] = validated.policy_digest
    return payload


def machine_time_policy_digest(policy: MachineTimePolicy) -> str:
    """Recompute the canonical policy digest over every public field except the self-digest.

    Requires an exact ``MachineTimePolicy`` whose every public field is canonical; the builder's
    empty-self-digest seed is supported (``policy_digest == ""`` allowed, and excluded from its own
    payload). A forged exact dataclass with a malformed field or a structural overclaim raises
    ``MachineTimePolicyError`` (``malformed_artifact``) instead of resealing a digest.
    """

    validated = _validate_machine_time_policy_artifact(policy, require_populated_self_digest=False)
    return _canonical_digest(_policy_payload_from(validated))


__all__ = [
    "MachineTimePolicyError",
    "MachineTimePolicyStatus",
    "MachineTimePolicy",
    "build_machine_time_policy",
    "machine_time_policy_to_dict",
    "machine_time_policy_digest",
]
