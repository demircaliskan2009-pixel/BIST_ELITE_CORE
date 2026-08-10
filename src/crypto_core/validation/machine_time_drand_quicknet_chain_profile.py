"""Fail-closed structural Drand Quicknet chain-profile binding.

This module implements only the controller-authorized S2 structural artifact.  It binds one exact
S1 ``MachineTimeSourceTrustSnapshot``, one exact structurally READY MT-3 ``MachineTimeSourceRegistry``
record, and one caller-supplied plain chain-info mapping into a single deterministic self-digested
commitment.

PROVENANCE RULE.  Every provider/protocol fact this artifact publishes is traceable to an exact
serialized field of the merged upstream authority: the MT-3 Drand record ``fact_items`` inventory
(``chain_hash``, ``genesis_unix_seconds``, ``mainnet_documented``, ``period_seconds``, ``public_key``,
``scheme``), the MT-3 record identifiers, or the S1 eligible row.  ``public_key_encoded_length`` is
DERIVED from the digest-bound MT-3 ``public_key`` value, never hard-coded.  Facts that the accepted
upstream authority does NOT serialize -- beacon id, curve id, public-key group, signature group and
signature encoded length -- are deliberately NOT published, NOT accepted from the caller and NOT
inferred from the scheme identifier; they are deferred to a future, separately governed verifier or
protocol-profile slice.  ``groupHash`` is likewise neither accepted nor bound as a trust root here.

It verifies chain/profile IDENTITY ONLY.  It does not verify BLS, parse or verify a beacon signature,
select a cryptographic dependency or message encoding, load or verify a fixture corpus, admit a
provider operationally, claim source reachability, prove machine time or a timestamp origin, or promote
readiness, connectors, quorum countability or proof verification.  The public key is never restated
here: it is taken from the bound S1 trust material, and the caller-supplied encoding must equal both
that material and the MT-3 record value exactly.

The caller mapping is normalized EXACTLY ONCE per public build or reconstruction attempt, and only that
one private normalized copy is derived from and retained.
"""

from __future__ import annotations

import hashlib
import json
import weakref
from enum import Enum
from weakref import ReferenceType

from crypto_core.validation.machine_time_source_registry import (
    MachineTimeSourceRegistry,
    MachineTimeSourceRegistryError,
    MachineTimeSourceRegistryStatus,
    machine_time_source_registry_digest,
    machine_time_source_registry_to_dict,
)
from crypto_core.validation.machine_time_source_trust_snapshot import (
    MachineTimeSourceTrustSnapshot,
    MachineTimeSourceTrustSnapshotError,
)

MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA = "machine-time-drand-quicknet-chain-profile.v1"
MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID = "machine-time-drand-quicknet-chain-profile-structural.v1"

__all__ = (
    "MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA",
    "MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID",
    "MachineTimeDrandQuicknetChainProfile",
    "MachineTimeDrandQuicknetChainProfileError",
    "MachineTimeDrandQuicknetChainProfileReason",
    "build_machine_time_drand_quicknet_chain_profile",
    "machine_time_drand_quicknet_chain_profile_commitment_descriptor",
    "machine_time_drand_quicknet_chain_profile_self_digest",
)


_PROFILE_DIGEST_DOMAIN = b"machine-time-drand-quicknet-chain-profile.v1/self-digest\x00"
_CHAIN_INFO_DIGEST_DOMAIN = b"machine-time-drand-quicknet-chain-profile.v1/chain-info\x00"
_MAX_TEXT_CHARS = 256
_MAX_CANONICAL_INT = (1 << 63) - 1
_MAX_REPR_CHARS = 512
_HEX_CHARS = frozenset("0123456789abcdef")
_LINE_SEPARATORS = frozenset({"\u2028", "\u2029"})
_SEALED_ARTIFACT_MESSAGE = "MachineTimeDrandQuicknetChainProfile is sealed and cannot be subclassed"
_DIRECT_CONSTRUCTION_MESSAGE = "use build_machine_time_drand_quicknet_chain_profile"
_ERROR_CONSTRUCTION_MESSAGE = "reason must be an exact MachineTimeDrandQuicknetChainProfileReason"
_ERROR_IMMUTABLE_MESSAGE = "MachineTimeDrandQuicknetChainProfileError is immutable"
# The seal itself is protected: it can never be deleted, reassigned or weakened, so the diagnostic
# cannot be altered by first removing the marker that used to gate this protection.
_ERROR_IMMUTABLE_ATTRS = frozenset({"_reason", "reason", "args", "_sealed"})

# Controller-approved MT4-S2 Quicknet identity.  EVERY constant below is an exact serialized value of
# the merged MT-3 Drand record or of the S1 eligible row (see the module PROVENANCE RULE).  No protocol
# fact that upstream does not serialize may be added here, and no fact may be inferred from another.
_SOURCE_ID = "drand-quicknet-mainnet"
_PROVIDER_ID = "league-of-entropy"
_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_SCHEME_ID = "bls-unchained-g1-rfc9380"
_PERIOD_SECONDS = 3
_GENESIS_TIME_SECONDS = 1_692_803_367
_PROTOCOL_PROFILE_ID = "drand-quicknet-signature-and-chain-info-offline.v1"
_WIRE_PROFILE_ID = "drand-http-api-v2-with-chain-info"
_DEPENDENCY_PROFILE_ID = "D-DEP-02"
_FIXTURE_CORPUS_ID = "FX-DRAND-QUICKNET.v1"
_VERIFICATION_POLICY_ID = "deterministic_supplied_proof_verification_no_network.v1"
_OFFICIAL_CITATION_IDS = (
    "DRAND-DEVELOPER",
    "DRAND-HTTP-API",
    "DRAND-QUICKNET-ANNOUNCEMENT",
    "DRAND-SPEC",
)
_SOURCE_CLASS = "distributed-threshold-randomness-beacon"
_RECOMMENDED_ROLE = "not_before"

# Exact S1 row this profile may bind.  It mirrors the COMPLETE S1 eligible row, in S1's order and with
# S1's values, so no independently valid cross-product can ever be wider here than upstream.  S1 already
# pins the same whole row, so a mismatch is DEFENSE IN DEPTH: it is unreachable with a valid S1 artifact
# and exists so a future S1 allowlist widening can never silently widen this profile.
_INDEPENDENCE_CLASS = "threshold-bls-beacon"
_SNAPSHOT_ROW_FIELDS = (
    "source_id",
    "provider_id",
    "source_class",
    "recommended_role",
    "protocol_profile_id",
    "protocol_wire_version",
    "independence_class",
    "trust_material_kind",
    "trust_material_encoding",
    "trust_material_fingerprint_algorithm",
    "dependency_profile_id",
    "fixture_corpus_id",
    "verification_policy_id",
)
_SNAPSHOT_ROW = (
    _SOURCE_ID,
    _PROVIDER_ID,
    _SOURCE_CLASS,
    _RECOMMENDED_ROLE,
    _PROTOCOL_PROFILE_ID,
    _WIRE_PROFILE_ID,
    _INDEPENDENCE_CLASS,
    "bls_group_public_key",
    "raw",
    "sha256",
    _DEPENDENCY_PROFILE_ID,
    _FIXTURE_CORPUS_ID,
    _VERIFICATION_POLICY_ID,
)
_UPSTREAM_FALSE_FIELDS = (
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
)
_SNAPSHOT_READ_FIELDS = (
    *_SNAPSHOT_ROW_FIELDS,
    *_UPSTREAM_FALSE_FIELDS,
    "snapshot_id",
    "snapshot_self_digest",
    "trust_material_bytes",
    "trust_material_fingerprint",
    "official_citation_ids",
)

# MT-3 registry-wide non-claims that must remain exactly False for a structural binding to be admitted.
_REGISTRY_FALSE_FIELDS = (
    "operationally_approved",
    "currently_reachable",
    "proof_acquired",
    "proof_verified",
    "quorum_approved",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "operational_quorum_ready",
    "source_reachable_proven",
    "readiness_promoted",
    "connector_promoted",
    "mt4_adapter_bound",
)
_REGISTRY_RECORD_TEXT_FIELDS = (
    ("provider_id", _PROVIDER_ID),
    ("source_class", _SOURCE_CLASS),
    ("recommended_role", _RECOMMENDED_ROLE),
    ("protocol_version", _WIRE_PROFILE_ID),
    ("verification_profile_id", _PROTOCOL_PROFILE_ID),
)
_REGISTRY_FACT_KEYS = (
    "chain_hash",
    "genesis_unix_seconds",
    "mainnet_documented",
    "period_seconds",
    "public_key",
    "scheme",
)

# Caller-supplied chain-info inventory.  Exactly the five values that the MT-3 record independently
# serializes, so every caller value can be bound against digest-bound upstream authority.  Nothing that
# upstream does not serialize is accepted here.  Caller KEY ORDER IS FREE (exact set + exact length
# equality, and the canonical serializer sorts keys); the inventory itself is exact.
_CHAIN_INFO_TEXT_FIELDS = ("chain_hash", "public_key", "scheme_id")
_CHAIN_INFO_INT_FIELDS = ("genesis_time_seconds", "period_seconds")
_CHAIN_INFO_FIELD_NAMES = (*_CHAIN_INFO_TEXT_FIELDS, *_CHAIN_INFO_INT_FIELDS)
_CHAIN_INFO_FIELD_NAME_SET = frozenset(_CHAIN_INFO_FIELD_NAMES)
_CHAIN_INFO_FIELD_COUNT = len(_CHAIN_INFO_FIELD_NAMES)
# A caller mapping is advanced at most one entry past the exact inventory: the sixth observed entry
# proves the mapping grew during consumption and rejects immediately.
_MAX_CHAIN_INFO_ADVANCES = _CHAIN_INFO_FIELD_COUNT + 1

# Non-claims this artifact publishes as exactly False.  A structural chain-profile binding proves
# identity only; every capability, admission, verification and promotion statement stays False.
_PROFILE_FALSE_FLAGS = (
    "dependency_profile_admitted",
    "cryptographic_backend_selected",
    "fixture_corpus_loaded",
    "fixture_corpus_verified",
    "message_encoding_profile_selected",
    "signature_parsed",
    "signature_verified",
    "randomness_verified",
    "source_reachable_proven",
    "provider_operationally_approved",
    "operational_use_approved",
    "proof_verified",
    "quorum_countable",
    "operational_quorum_ready",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "readiness_promoted",
    "connector_promoted",
)

# Deferred to a future separately governed slice because the accepted S1/MT-3 authority does not
# serialize them.  They must never re-enter this contract without new governed provenance.
_DEFERRED_UNBOUND_PROTOCOL_FACTS = (
    "beacon_id",
    "curve_id",
    "public_key_group",
    "signature_group",
    "signature_encoded_length",
)

_DESCRIPTOR_FIELD_NAMES = (
    "profile_schema",
    "profile_id",
    "source_id",
    "provider_id",
    "chain_hash",
    "scheme_id",
    "period_seconds",
    "genesis_time_seconds",
    "public_key_encoded_length",
    "public_key_fingerprint",
    "protocol_profile_id",
    "wire_profile_id",
    "dependency_profile_id",
    "fixture_corpus_id",
    "verification_policy_id",
    "official_citation_ids",
    "bound_snapshot_id",
    "bound_snapshot_self_digest",
    "bound_registry_digest",
    "bound_registry_source_entry_digest",
    "chain_info_canonical_digest",
    "chain_profile_structurally_bound",
    *_PROFILE_FALSE_FLAGS,
)
_FIELD_NAMES = (*_DESCRIPTOR_FIELD_NAMES, "profile_self_digest")
_PROFILE_FALSE_FLAG_INDEXES = tuple(_DESCRIPTOR_FIELD_NAMES.index(name) for name in _PROFILE_FALSE_FLAGS)

# A registry entry is exactly ``(owner_ref, state)`` and the registered state repeats that same owner
# reference object in its first slot, so an otherwise valid state belonging to a different profile
# cannot be transplanted beneath this profile's legitimate entry.  The retained bindings therefore
# live at state[1:4]; the owner reference never leaves this module's private registry.
_REGISTRY_ENTRY_LENGTH = 2
_REGISTRY_STATE_LENGTH = 4


class MachineTimeDrandQuicknetChainProfileReason(str, Enum):
    """Closed failure inventory; each validation surface owns its documented order."""

    WRONG_INPUT_TYPE = "wrong_input_type"
    FIELD_INVENTORY_INVALID = "field_inventory_invalid"
    FIELD_TYPE_INVALID = "field_type_invalid"
    CANONICAL_TEXT_INVALID = "canonical_text_invalid"
    RESOURCE_BOUND_EXCEEDED = "resource_bound_exceeded"
    SNAPSHOT_BINDING_INVALID = "snapshot_binding_invalid"
    REGISTRY_BINDING_INVALID = "registry_binding_invalid"
    CHAIN_IDENTITY_MISMATCH = "chain_identity_mismatch"
    PUBLIC_KEY_ENCODING_INVALID = "public_key_encoding_invalid"
    PUBLIC_KEY_LENGTH_INVALID = "public_key_length_invalid"
    PUBLIC_KEY_MISMATCH = "public_key_mismatch"
    GOVERNANCE_STRUCTURAL_VIOLATION = "governance_structural_violation"
    SELF_DIGEST_INVALID = "self_digest_invalid"
    SELF_DIGEST_MISMATCH = "self_digest_mismatch"
    RECONSTRUCTION_INPUT_INVALID = "reconstruction_input_invalid"
    ARTIFACT_INCONSISTENT = "artifact_inconsistent"


class MachineTimeDrandQuicknetChainProfileError(RuntimeError):
    """Closed diagnostic carrying one exact reason and no caller-controlled message."""

    __slots__ = ("_reason", "_sealed")

    def __init__(self, reason: MachineTimeDrandQuicknetChainProfileReason) -> None:
        if type(reason) is not MachineTimeDrandQuicknetChainProfileReason:
            raise TypeError(_ERROR_CONSTRUCTION_MESSAGE)
        RuntimeError.__init__(self, reason.value)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_sealed", True)

    @property
    def reason(self) -> MachineTimeDrandQuicknetChainProfileReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        # Unconditional: the guard must not depend on a marker that ordinary code could remove first.
        # The constructor populates its slots through ``object.__setattr__``, so construction is
        # unaffected and every post-construction ordinary assignment is refused.
        if name in _ERROR_IMMUTABLE_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_IMMUTABLE_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        object.__delattr__(self, name)


def _err(reason: MachineTimeDrandQuicknetChainProfileReason) -> MachineTimeDrandQuicknetChainProfileError:
    return MachineTimeDrandQuicknetChainProfileError(reason)


def _paired_values(names: tuple[str, ...], values: tuple[object, ...]) -> dict[str, object]:
    """Pair exactly equal-length sequences.

    Length-checked ``zip`` is Python 3.10+ and this project's floor is 3.8, so the exact-length
    invariant is proven explicitly here instead.  Every call site already derives ``values`` from
    ``_DESCRIPTOR_FIELD_NAMES`` plus the digest, which makes this a fail-closed backstop rather than
    a new validation surface.
    """
    if len(names) != len(values):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
    return dict(zip(names, values))


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _is_lower_hex(value: str) -> bool:
    return bool(value) and len(value) % 2 == 0 and all(char in _HEX_CHARS for char in value)


def _text_is_canonical(value: str) -> bool:
    if not value or value != value.strip():
        return False
    return all(ord(char) >= 32 and ord(char) != 127 and char not in _LINE_SEPARATORS for char in value)


def _check_text_bound(value: str) -> None:
    """Bound the cheap character count BEFORE encoding.

    ``str`` length is O(1), so an oversized caller string is rejected without ever materializing its
    UTF-8 encoding.  Only a string already known to be within the character bound is encoded, and the
    encoded byte length is then bounded separately because multi-byte text can exceed the cap while
    the character count does not.
    """
    if len(value) > _MAX_TEXT_CHARS:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RESOURCE_BOUND_EXCEEDED)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.CANONICAL_TEXT_INVALID) from None
    if len(encoded) > _MAX_TEXT_CHARS:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RESOURCE_BOUND_EXCEEDED)


def _chain_info_items(mapping: dict[str, object]) -> object:
    """The single point where caller-controlled iteration begins.

    In production this is a plain ``iter`` call; isolating it keeps bounded consumption and the
    mutation-during-iteration failure path auditable and directly testable.
    """
    return iter(mapping.items())


def _bounded_chain_info_snapshot(chain_info: object) -> dict[str, object]:
    """Consume a caller mapping ONCE, bounded, into a fresh private snapshot.

    ``dict`` cardinality is O(1), so a mapping of the wrong size is rejected without traversing it at
    all.  A correctly sized mapping is then advanced at most ``_MAX_CHAIN_INFO_ADVANCES`` entries: a
    caller that grows the mapping after that O(1) observation cannot force an unbounded traversal,
    because the sixth observed entry rejects immediately.  Keys are typed and matched against the
    exact inventory while being consumed -- the exact-``str`` check precedes any set membership, so a
    hostile key subclass never gets equality or hash dispatch -- and mutation during iteration fails
    closed instead of leaking ``RuntimeError`` or ``KeyError``.  The caller mapping is never read
    again: everything downstream reads only the returned private copy.
    """
    if type(chain_info) is not dict:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    if len(chain_info) != _CHAIN_INFO_FIELD_COUNT:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)

    snapshot: dict[str, object] = {}
    advances = 0
    items = _chain_info_items(chain_info)
    while True:
        try:
            item = next(items)
        except StopIteration:
            break
        except RuntimeError:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID) from None
        advances += 1
        if advances > _CHAIN_INFO_FIELD_COUNT:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)
        key, value = item
        if type(key) is not str or key not in _CHAIN_INFO_FIELD_NAME_SET or key in snapshot:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)
        snapshot[key] = value
    if len(snapshot) != _CHAIN_INFO_FIELD_COUNT:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)
    return {name: snapshot[name] for name in _CHAIN_INFO_FIELD_NAMES}


def _validate_and_normalize_chain_info(chain_info: object) -> dict[str, object]:
    """Prove a mapping is exact plain data before any comparison, ordering or hashing, and normalize it.

    Returns a FRESH plain dict.  Public entry points call this EXACTLY ONCE on the caller-owned mapping
    and then pass only the returned private copy onward, so no caller mapping is ever read twice and the
    artifact never retains a caller-owned mutable object.  Revalidation calls it again on the artifact's
    own private copy, which is tamper detection rather than a caller read.
    """
    values = _bounded_chain_info_snapshot(chain_info)
    for name in _CHAIN_INFO_TEXT_FIELDS:
        if type(values[name]) is not str:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_TYPE_INVALID)
    for name in _CHAIN_INFO_INT_FIELDS:
        if type(values[name]) is not int:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_TYPE_INVALID)
    for name in _CHAIN_INFO_TEXT_FIELDS:
        _check_text_bound(values[name])
    for name in _CHAIN_INFO_INT_FIELDS:
        if values[name] < 1 or values[name] > _MAX_CANONICAL_INT:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.RESOURCE_BOUND_EXCEEDED)
    for name in _CHAIN_INFO_TEXT_FIELDS:
        if not _text_is_canonical(values[name]):
            raise _err(MachineTimeDrandQuicknetChainProfileReason.CANONICAL_TEXT_INVALID)
    return values


def _snapshot_binding(snapshot: object) -> dict[str, object]:
    """Read the S1 artifact only through its own public fail-closed boundary."""
    if type(snapshot) is not MachineTimeSourceTrustSnapshot:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    try:
        read = {name: getattr(snapshot, name) for name in _SNAPSHOT_READ_FIELDS}
    except MachineTimeSourceTrustSnapshotError:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID) from None

    if tuple(read[name] for name in _SNAPSHOT_ROW_FIELDS) != _SNAPSHOT_ROW:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    if any(read[name] is not False for name in _UPSTREAM_FALSE_FIELDS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    if type(read["official_citation_ids"]) is not tuple or read["official_citation_ids"] != _OFFICIAL_CITATION_IDS:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    if not _is_hex64(read["snapshot_self_digest"]) or not _is_hex64(read["trust_material_fingerprint"]):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    if type(read["snapshot_id"]) is not str or not _text_is_canonical(read["snapshot_id"]):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    material = read["trust_material_bytes"]
    if type(material) is not bytes or not material:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    if hashlib.sha256(material).hexdigest() != read["trust_material_fingerprint"]:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SNAPSHOT_BINDING_INVALID)
    return read


def _registry_binding(registry: object) -> dict[str, object]:
    """Recompute the MT-3 digest through the public serializer and bind the exact Drand record."""
    if type(registry) is not MachineTimeSourceRegistry:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    try:
        payload = machine_time_source_registry_to_dict(registry)
        recomputed = machine_time_source_registry_digest(registry)
    except MachineTimeSourceRegistryError:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID) from None

    if not _is_hex64(payload["registry_digest"]) or payload["registry_digest"] != recomputed:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if payload["status"] != MachineTimeSourceRegistryStatus.REGISTRY_READY.value or payload["ready"] is not True:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if any(payload[name] is not False for name in _REGISTRY_FALSE_FIELDS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)

    matches = tuple(record for record in payload["sources"] if record["source_id"] == _SOURCE_ID)
    if len(matches) != 1:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    record = matches[0]
    if any(record[name] != expected for name, expected in _REGISTRY_RECORD_TEXT_FIELDS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if any(record[name] is not False for name in _UPSTREAM_FALSE_FIELDS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if tuple(sorted(record["citation_ids"])) != _OFFICIAL_CITATION_IDS:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if not _is_hex64(record["entry_digest"]):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)

    facts: dict[str, object] = {}
    for item in record["fact_items"]:
        if type(item) is not list or len(item) != 2 or type(item[0]) is not str:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
        facts[item[0]] = item[1]
    if len(facts) != len(_REGISTRY_FACT_KEYS) or frozenset(facts) != frozenset(_REGISTRY_FACT_KEYS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    if (
        facts["chain_hash"] != _CHAIN_HASH
        or facts["genesis_unix_seconds"] != _GENESIS_TIME_SECONDS
        or facts["period_seconds"] != _PERIOD_SECONDS
        or facts["scheme"] != _SCHEME_ID
        or facts["mainnet_documented"] is not True
    ):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    registry_public_key = facts["public_key"]
    if type(registry_public_key) is not str or not _is_lower_hex(registry_public_key):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    # The expected key length is DERIVED from this digest-bound MT-3 value; it is never a local constant.
    registry_public_key_bytes = bytes.fromhex(registry_public_key)
    if not registry_public_key_bytes:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    return {
        "registry_digest": payload["registry_digest"],
        "entry_digest": record["entry_digest"],
        "public_key": registry_public_key,
        "public_key_bytes": registry_public_key_bytes,
        "public_key_encoded_length": len(registry_public_key_bytes),
    }


def _canonical_text(payload: dict[str, object]) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT) from None


def _canonical_descriptor(values: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in _DESCRIPTOR_FIELD_NAMES:
        value = values[name]
        payload[name] = list(value) if type(value) is tuple else value
    return payload


def _derive_from_normalized_chain_info(
    snapshot: object, registry: object, normalized_chain_info: object
) -> tuple[dict[str, object], str]:
    """Total S2 precedence; the single derivation of every public value.

    ``normalized_chain_info`` must already be the output of ``_validate_and_normalize_chain_info``.  It is
    re-proven here on every call because that is the revalidation guarantee for the artifact's own
    private retained state; no caller-owned mapping is read by this function.
    """
    chain = _validate_and_normalize_chain_info(normalized_chain_info)
    bound_snapshot = _snapshot_binding(snapshot)
    bound_registry = _registry_binding(registry)

    if (
        chain["chain_hash"] != _CHAIN_HASH
        or chain["scheme_id"] != _SCHEME_ID
        or chain["period_seconds"] != _PERIOD_SECONDS
        or chain["genesis_time_seconds"] != _GENESIS_TIME_SECONDS
    ):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.CHAIN_IDENTITY_MISMATCH)

    expected_length = bound_registry["public_key_encoded_length"]
    if len(bound_snapshot["trust_material_bytes"]) != expected_length:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_LENGTH_INVALID)
    supplied_key = chain["public_key"]
    if not _is_lower_hex(supplied_key):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_ENCODING_INVALID)
    decoded = bytes.fromhex(supplied_key)
    if len(decoded) != expected_length:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_LENGTH_INVALID)
    if decoded != bound_snapshot["trust_material_bytes"] or decoded != bound_registry["public_key_bytes"]:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_MISMATCH)

    values: dict[str, object] = {
        "profile_schema": MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA,
        "profile_id": MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID,
        "source_id": _SOURCE_ID,
        "provider_id": _PROVIDER_ID,
        "chain_hash": _CHAIN_HASH,
        "scheme_id": _SCHEME_ID,
        "period_seconds": _PERIOD_SECONDS,
        "genesis_time_seconds": _GENESIS_TIME_SECONDS,
        "public_key_encoded_length": expected_length,
        "public_key_fingerprint": bound_snapshot["trust_material_fingerprint"],
        "protocol_profile_id": _PROTOCOL_PROFILE_ID,
        "wire_profile_id": _WIRE_PROFILE_ID,
        "dependency_profile_id": _DEPENDENCY_PROFILE_ID,
        "fixture_corpus_id": _FIXTURE_CORPUS_ID,
        "verification_policy_id": _VERIFICATION_POLICY_ID,
        "official_citation_ids": _OFFICIAL_CITATION_IDS,
        "bound_snapshot_id": bound_snapshot["snapshot_id"],
        "bound_snapshot_self_digest": bound_snapshot["snapshot_self_digest"],
        "bound_registry_digest": bound_registry["registry_digest"],
        "bound_registry_source_entry_digest": bound_registry["entry_digest"],
        "chain_info_canonical_digest": hashlib.sha256(
            _CHAIN_INFO_DIGEST_DOMAIN + _canonical_text(chain).encode("utf-8")
        ).hexdigest(),
        "chain_profile_structurally_bound": True,
    }
    for name in _PROFILE_FALSE_FLAGS:
        values[name] = False

    if values["chain_profile_structurally_bound"] is not True or any(
        values[name] is not False for name in _PROFILE_FALSE_FLAGS
    ):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if tuple(values) != _DESCRIPTOR_FIELD_NAMES:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)

    canonical = _canonical_text(_canonical_descriptor(values))
    return values, hashlib.sha256(_PROFILE_DIGEST_DOMAIN + canonical.encode("utf-8")).hexdigest()


def _build_profile_class() -> tuple[type, object, object]:
    registry: dict[int, tuple[ReferenceType, tuple[object, ...]]] = {}

    def entry_is_well_formed(entry: object) -> bool:
        """Prove the exact entry shape before anything is indexed or dereferenced."""
        if type(entry) is not tuple or len(entry) != _REGISTRY_ENTRY_LENGTH:
            return False
        return type(entry[0]) is ReferenceType

    def register_proven_profile(artifact: object, state: tuple[object, ...]) -> None:
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            current = registry.get(key)
            # A replacement entry must survive a stale callback, and a corrupted entry must not
            # raise IndexError/TypeError inside a weakref callback.
            if entry_is_well_formed(current) and current[0] is dead:
                del registry[key]

        owner = weakref.ref(artifact, forget)
        # The SAME reference object is stored in both slots; identity is what binds them.
        registry[key] = (owner, (owner,) + state)

    def proven_parts(artifact: object) -> tuple[tuple[object, ...], tuple[object, ...]]:
        if type(artifact) is not MachineTimeDrandQuicknetChainProfile:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        key = id(artifact)
        entry = registry.get(key)
        if not entry_is_well_formed(entry):
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        owner = entry[0]
        state = entry[1]
        if owner() is not artifact:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        # The retained state carries its own owner reference, so a coherent state donated by another
        # profile fails closed here instead of being derived under this profile's identity.  Identity
        # (``is``), never equality: a distinct reference to the same artifact must not satisfy it.
        if type(state) is not tuple or len(state) != _REGISTRY_STATE_LENGTH or state[0] is not owner:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        # The owner reference is deliberately excluded from the returned bindings so it can never
        # reach a public surface, a digest input or a serialization payload.
        bound = (state[1], state[2], state[3])
        try:
            values, digest = _derive_from_normalized_chain_info(bound[0], bound[1], bound[2])
        except MachineTimeDrandQuicknetChainProfileError:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT) from None
        # Recheck the exact entry identity before returning trusted state: nothing may have replaced
        # the entry while it was being proven.
        if registry.get(key) is not entry:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        return tuple(values[name] for name in _DESCRIPTOR_FIELD_NAMES) + (digest,), bound

    def proven_state(artifact: object) -> tuple[object, ...]:
        return proven_parts(artifact)[0]

    def create_from_normalized(
        snapshot: object, registry_artifact: object, normalized_chain_info: dict[str, object]
    ) -> MachineTimeDrandQuicknetChainProfile:
        """Register ONE artifact over the exact private normalized mapping that passed validation.

        The mapping must already be a private normalized copy; this function never reads a
        caller-owned mapping, and it registers the identical object it validated.
        """
        _derive_from_normalized_chain_info(snapshot, registry_artifact, normalized_chain_info)
        artifact = object.__new__(MachineTimeDrandQuicknetChainProfile)
        register_proven_profile(artifact, (snapshot, registry_artifact, normalized_chain_info))
        return artifact

    class MachineTimeDrandQuicknetChainProfile:
        """Sealed S2 structural binding of the controller-approved Drand Quicknet chain identity.

        The artifact binds one S1 trust snapshot, one structurally READY MT-3 registry and one exact
        caller-supplied chain-info mapping.  It establishes NO BLS validity, signature or randomness
        verification, dependency admission, fixture state, provider approval, source reachability,
        proof verification, quorum countability, machine-time or timestamp origin, readiness, or
        connector state.
        """

        __slots__ = ("__weakref__",)
        __hash__ = None

        def __new__(cls, *args: object, **kwargs: object) -> MachineTimeDrandQuicknetChainProfile:
            raise TypeError(_DIRECT_CONSTRUCTION_MESSAGE)

        def __init_subclass__(cls, **kwargs: object) -> None:
            raise TypeError(_SEALED_ARTIFACT_MESSAGE)

        def __repr__(self) -> str:
            state = proven_state(self)
            values = _paired_values(_FIELD_NAMES, state)
            rendered = (
                "MachineTimeDrandQuicknetChainProfile("
                f"source_id={values['source_id']}, "
                f"scheme_id={values['scheme_id']}, "
                f"chain_hash=<str len={len(values['chain_hash'])}>, "
                f"public_key=<redacted len={values['public_key_encoded_length']} "
                f"fingerprint={values['public_key_fingerprint']}>, "
                f"snapshot_id=<str len={len(values['bound_snapshot_id'])}>, "
                f"registry_digest=<str len={len(values['bound_registry_digest'])}>, "
                f"chain_profile_structurally_bound={values['chain_profile_structurally_bound']}, "
                f"self_digest={values['profile_self_digest']})"
            )
            if not rendered.isascii() or "\n" in rendered or "\r" in rendered or len(rendered) > _MAX_REPR_CHARS:
                raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
            return rendered

        def __str__(self) -> str:
            return self.__repr__()

        def __bool__(self) -> bool:
            proven_state(self)
            return True

        def __eq__(self, other: object) -> bool:
            proven_state(self)
            if type(other) is not MachineTimeDrandQuicknetChainProfile:
                return False
            if self is other:
                return True
            proven_state(other)
            return False

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple[object, tuple[tuple[object, ...]]]:
            public_state, bound = proven_parts(self)
            flags = tuple(public_state[index] for index in _PROFILE_FALSE_FLAG_INDEXES)
            return (
                _rebuild_machine_time_drand_quicknet_chain_profile,
                ((bound[0], bound[1], dict(bound[2]), flags, public_state[-1]),),
            )

    def make_property(index: int):
        def getter(self: MachineTimeDrandQuicknetChainProfile) -> object:
            return proven_state(self)[index]

        return property(getter)

    for index, name in enumerate(_FIELD_NAMES):
        setattr(MachineTimeDrandQuicknetChainProfile, name, make_property(index))
    MachineTimeDrandQuicknetChainProfile.__qualname__ = "MachineTimeDrandQuicknetChainProfile"
    MachineTimeDrandQuicknetChainProfile.__module__ = __name__
    return MachineTimeDrandQuicknetChainProfile, create_from_normalized, proven_state


(
    MachineTimeDrandQuicknetChainProfile,
    _create_profile_from_normalized,
    _proven_profile_state,
) = _build_profile_class()


def build_machine_time_drand_quicknet_chain_profile(
    *,
    snapshot: MachineTimeSourceTrustSnapshot,
    registry: MachineTimeSourceRegistry,
    chain_info: dict[str, object],
) -> MachineTimeDrandQuicknetChainProfile:
    """Bind one structural Quicknet chain profile; no provider verification or admission occurs.

    The caller mapping is normalized EXACTLY ONCE here; every later step, including registration, uses
    only that one private normalized copy.
    """
    normalized = _validate_and_normalize_chain_info(chain_info)
    return _create_profile_from_normalized(snapshot, registry, normalized)  # type: ignore[operator]


def machine_time_drand_quicknet_chain_profile_commitment_descriptor(
    profile: MachineTimeDrandQuicknetChainProfile,
) -> dict[str, object]:
    if type(profile) is not MachineTimeDrandQuicknetChainProfile:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    state = _proven_profile_state(profile)  # type: ignore[operator]
    values = _paired_values(_FIELD_NAMES, state)
    return _canonical_descriptor(values)


def machine_time_drand_quicknet_chain_profile_self_digest(profile: MachineTimeDrandQuicknetChainProfile) -> str:
    if type(profile) is not MachineTimeDrandQuicknetChainProfile:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    return _proven_profile_state(profile)[-1]  # type: ignore[index,operator]


def _rebuild_machine_time_drand_quicknet_chain_profile(state: object) -> MachineTimeDrandQuicknetChainProfile:
    """Reconstruct only from the exact retained bindings, re-proving non-claims and the carried digest.

    The incoming mapping is normalized EXACTLY ONCE; the carried digest is compared against a digest
    derived from that same normalized copy, and that same copy is the one registered.
    """
    if type(state) is not tuple or len(state) != 5:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RECONSTRUCTION_INPUT_INVALID)
    flags = state[3]
    if type(flags) is not tuple or len(flags) != len(_PROFILE_FALSE_FLAGS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RECONSTRUCTION_INPUT_INVALID)
    if any(flag is not False for flag in flags):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    normalized = _validate_and_normalize_chain_info(state[2])
    _, digest = _derive_from_normalized_chain_info(state[0], state[1], normalized)
    carried = state[4]
    if not _is_hex64(carried):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_INVALID)
    if carried != digest:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_MISMATCH)
    return _create_profile_from_normalized(state[0], state[1], normalized)  # type: ignore[operator]
