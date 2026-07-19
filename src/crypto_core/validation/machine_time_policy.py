"""Machine-time provenance policy artifact (MT-2 — abstract, pre-Deep-Research-safe).

This module pins the governance-owned STRUCTURE of the machine-time "sandwich" model that later
machine-time artifacts (MT-3 source registry, MT-4 anchor evidence, MT-5 machine-proven day, MT-6
machine-proven 30-day gate) must obey. A day's evidence is provably inside a real-time interval only when
it is sandwiched between two independent external time proofs:

* a **not_before** proof — an unpredictable public beacon value embedded INTO the attested-day metadata at
  seal time (the day digest cannot pre-date the beacon value); and
* a **not_after** proof — an external signed timestamp that COMMITS TO the day self-digest (the digest
  existed no later than the signed time),

with a QUORUM of at least two independent source classes on each side, and a SPACING rule so that >= 30
machine-proven days require >= 30 distinct sandwiches whose intervals are consistent with ~30 real elapsed
days.

MT-2 is deliberately ABSTRACT and pre-Deep-Research-safe: it pins the required roles, the quorum minimum,
abstract verification-policy identifiers, the spacing bounds, and the canonical proof-encoding and
digest-commitment policies, and it requires explicit governance approval of the numeric policy values. It
binds NO concrete provider name, endpoint, beacon format, signature scheme, timestamping-authority
semantic, clock-skew tolerance, or proof-format wire version — every such fact is Deep-Research-gated and
belongs to MT-3+. It consumes no attested day, no anchor, no episode, no runtime/live/venue state, and no
external fact. A READY policy proves only that the supplied structure metadata is well-formed and
governance-approved; it never proves that any machine-time anchor was verified, that time origin was
proven, or that injected/attested time may substitute for a machine proof.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
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

# Abstract, provider-agnostic structure identifiers. These describe the sandwich VERIFICATION APPROACH,
# never a concrete provider, endpoint, wire format, or Deep-Research fact.
_SANDWICH_MODEL = "not_before_beacon_and_not_after_signed_timestamp_sandwich.v1"
_REQUIRED_ROLES = ("not_before", "not_after")
_NOT_BEFORE_VERIFICATION_POLICY = "unpredictable_public_beacon_embedded_pre_seal.v1"
_NOT_AFTER_VERIFICATION_POLICY = "external_signed_timestamp_commits_to_day_self_digest.v1"
_QUORUM_MODEL = "independent_source_classes_per_role.v1"
_DIGEST_COMMITMENT_POLICY = "not_after_proof_commits_to_exact_day_self_digest.v1"
_PROOF_ENCODING_POLICY = "canonical_deterministic_proof_bytes_no_fetch_at_verify.v1"
_SPACING_POLICY = "consecutive_utc_days_monotonic_nonoverlapping_interval_consistent.v1"

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
    """Raised on malformed caller input for the MT-2 policy artifact."""


class MachineTimePolicyStatus(str, Enum):
    """MT-2 policy status. READY is policy-structure readiness only, never machine-time proof."""

    POLICY_READY = "POLICY_READY"
    POLICY_REJECTED = "POLICY_REJECTED"


@dataclass(frozen=True)
class MachineTimePolicy:
    """Immutable, digest-bound abstract machine-time sandwich policy (MT-2).

    READY only when governance approval metadata and the governance-approved structural values (quorum per
    role, required machine-proven day count, inter-day spacing bounds) are present and well-formed, and
    every pinned structure identifier matches. It binds no concrete provider fact and proves no machine
    time.
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
    digest_commitment_policy: str
    proof_encoding_policy: str
    spacing_policy: str
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
    reason_codes: tuple[str, ...]
    metadata: tuple[tuple[str, str], ...]
    policy_digest: str
    paper_only: bool = True
    policy_only: bool = True
    abstract_pre_deep_research: bool = True
    deep_research_facts_bound: bool = False
    concrete_sources_bound: bool = False
    machine_time_anchor_verified: bool = False
    machine_time_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    injected_time_accepted_as_proof: bool = False
    attested_time_accepted_as_proof: bool = False
    network_fetch_performed: bool = False
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


def _require_plain_non_empty_string(value: object, field_name: str) -> str:
    if not _is_plain_non_empty_string(value):
        raise MachineTimePolicyError(_reason(f"{field_name}_invalid"))
    return value  # type: ignore[return-value]


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
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


def _structure_failures(
    *,
    sandwich_model: object,
    not_before_verification_policy: object,
    not_after_verification_policy: object,
    quorum_model: object,
    digest_commitment_policy: object,
    proof_encoding_policy: object,
    spacing_policy: object,
) -> list[str]:
    """Every pinned structural identifier must equal its governance-fixed constant exactly."""

    if (
        sandwich_model != _SANDWICH_MODEL
        or not_before_verification_policy != _NOT_BEFORE_VERIFICATION_POLICY
        or not_after_verification_policy != _NOT_AFTER_VERIFICATION_POLICY
        or quorum_model != _QUORUM_MODEL
        or digest_commitment_policy != _DIGEST_COMMITMENT_POLICY
        or proof_encoding_policy != _PROOF_ENCODING_POLICY
        or spacing_policy != _SPACING_POLICY
    ):
        return [_reason("structure_mismatch")]
    return []


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
    not_before_verification_policy: str = _NOT_BEFORE_VERIFICATION_POLICY,
    not_after_verification_policy: str = _NOT_AFTER_VERIFICATION_POLICY,
    quorum_model: str = _QUORUM_MODEL,
    digest_commitment_policy: str = _DIGEST_COMMITMENT_POLICY,
    proof_encoding_policy: str = _PROOF_ENCODING_POLICY,
    spacing_policy: str = _SPACING_POLICY,
    metadata: Mapping[str, str] | None = None,
) -> MachineTimePolicy:
    """Build a deterministic abstract MT-2 machine-time policy artifact.

    Governance-owned structural values are accepted only when explicitly supplied with approval metadata and
    an approval flag; missing, malformed, or unapproved values produce ``POLICY_REJECTED`` rather than
    defaults. Wrong-typed identifiers/approval flag raise ``MachineTimePolicyError``; every structure/value
    failure maps to ``status=POLICY_REJECTED``.
    """

    policy_id = _require_plain_non_empty_string(policy_id, "policy_id")
    correlation_id = _require_plain_non_empty_string(correlation_id, "correlation_id")
    if type(policy_approved) is not bool:
        raise MachineTimePolicyError(_reason("policy_approved_invalid"))

    metadata_pairs = _normalize_metadata(metadata)
    hard: list[str] = []

    if policy_approved is not True:
        hard.append(_reason("policy_not_approved"))

    hard.extend(_quorum_failures(approved_quorum_per_role))
    hard.extend(_day_count_failures(approved_required_machine_proven_day_count))
    hard.extend(_spacing_failures(approved_min_inter_day_spacing_ns, approved_max_inter_day_spacing_ns))

    if not _is_plain_non_empty_string(approval_reference):
        hard.append(_reason("approval_reference_missing"))
    if not _is_hex64_string(approval_digest):
        hard.append(_reason("approval_digest_invalid"))

    hard.extend(
        _structure_failures(
            sandwich_model=sandwich_model,
            not_before_verification_policy=not_before_verification_policy,
            not_after_verification_policy=not_after_verification_policy,
            quorum_model=quorum_model,
            digest_commitment_policy=digest_commitment_policy,
            proof_encoding_policy=proof_encoding_policy,
            spacing_policy=spacing_policy,
        )
    )

    scope_texts = (policy_id, correlation_id, approval_reference, *_metadata_texts(metadata_pairs))
    if _has_bist_token(*scope_texts):
        hard.append(_reason("bist_token_forbidden"))
    if _has_clock_token(*scope_texts):
        hard.append(_reason("clock_token_forbidden"))
    if _has_scope_violation(*scope_texts):
        hard.append(_reason("scope_violation"))

    reason_codes = _sorted_unique(hard)
    status = MachineTimePolicyStatus.POLICY_REJECTED if reason_codes else MachineTimePolicyStatus.POLICY_READY
    ready = status is MachineTimePolicyStatus.POLICY_READY

    policy_fields: dict[str, object] = {
        "schema_version": _SCHEMA_VERSION,
        "policy_version": _POLICY_VERSION,
        "status": status,
        "ready": ready,
        "policy_id": policy_id,
        "correlation_id": correlation_id,
        "sandwich_model": sandwich_model,
        "required_roles": _REQUIRED_ROLES,
        "not_before_verification_policy": not_before_verification_policy,
        "not_after_verification_policy": not_after_verification_policy,
        "quorum_model": quorum_model,
        "digest_commitment_policy": digest_commitment_policy,
        "proof_encoding_policy": proof_encoding_policy,
        "spacing_policy": spacing_policy,
        "min_quorum_per_role": _MIN_QUORUM_PER_ROLE,
        "min_machine_proven_day_count": _MIN_MACHINE_PROVEN_DAY_COUNT,
        "utc_day_ns": _DAY_NS,
        "approved_quorum_per_role": approved_quorum_per_role,
        "approved_required_machine_proven_day_count": approved_required_machine_proven_day_count,
        "approved_min_inter_day_spacing_ns": approved_min_inter_day_spacing_ns,
        "approved_max_inter_day_spacing_ns": approved_max_inter_day_spacing_ns,
        "approval_reference": approval_reference,
        "approval_digest": approval_digest,
        "policy_approved": policy_approved,
        "reason_codes": reason_codes,
        "metadata": metadata_pairs,
    }
    seed = MachineTimePolicy(policy_digest="", **policy_fields)  # type: ignore[arg-type]
    return _replace_policy_digest(seed, machine_time_policy_digest(seed))


def _replace_policy_digest(policy: MachineTimePolicy, digest: str) -> MachineTimePolicy:
    values = _policy_fields(policy)
    values["policy_digest"] = digest
    return MachineTimePolicy(**values)  # type: ignore[arg-type]


def _policy_fields(policy: MachineTimePolicy) -> dict[str, object]:
    return {field.name: getattr(policy, field.name) for field in fields(policy) if field.name != "policy_digest"}


def _policy_payload_from(policy: MachineTimePolicy) -> dict[str, object]:
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
    """Canonical JSON-ready mapping for the MT-2 policy, including its self-digest."""

    payload = _policy_payload_from(policy)
    payload["policy_digest"] = policy.policy_digest
    return payload


def machine_time_policy_digest(policy: MachineTimePolicy) -> str:
    """Recompute the canonical policy digest over every public field except the self-digest."""

    return _canonical_digest(_policy_payload_from(policy))


__all__ = [
    "MachineTimePolicy",
    "MachineTimePolicyError",
    "MachineTimePolicyStatus",
    "build_machine_time_policy",
    "machine_time_policy_digest",
    "machine_time_policy_to_dict",
]
