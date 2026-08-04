"""Fail-closed structural Drand Quicknet chain-profile binding.

This module implements only the controller-authorized S2 structural artifact.  It binds one exact
S1 ``MachineTimeSourceTrustSnapshot``, one exact structurally READY MT-3 ``MachineTimeSourceRegistry``,
the controller-approved Quicknet chain-identity constants, and one caller-supplied plain chain-info
mapping into a single deterministic self-digested commitment.

It verifies chain/profile IDENTITY ONLY.  It does not verify BLS, parse or verify a beacon signature,
select a cryptographic dependency or message encoding, load or verify a fixture corpus, admit a
provider operationally, claim source reachability, prove machine time or a timestamp origin, or promote
readiness, connectors, quorum countability or proof verification.  ``groupHash`` is deliberately NOT
accepted and NOT bound as a trust root in this slice.  The public key is never restated here: it is
taken from the bound S1 trust material and the caller-supplied encoding must equal it exactly.
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

# Controller-approved MT4-S2 Quicknet chain identity.  Every value is already carried by the merged
# MT-3 registry record (citation-backed) or by the S1 eligible row; nothing here is a new provider fact.
_SOURCE_ID = "drand-quicknet-mainnet"
_PROVIDER_ID = "league-of-entropy"
_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_BEACON_ID = "quicknet"
_SCHEME_ID = "bls-unchained-g1-rfc9380"
_CURVE_ID = "bls12-381"
_PERIOD_SECONDS = 3
_GENESIS_TIME_SECONDS = 1_692_803_367
_PUBLIC_KEY_GROUP = "g2"
_SIGNATURE_GROUP = "g1"
_PUBLIC_KEY_ENCODED_LENGTH = 96
_SIGNATURE_ENCODED_LENGTH = 48
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

# Exact S1 row this profile may bind.  S1 already pins the same whole row, so a row mismatch is
# DEFENSE IN DEPTH: it is unreachable with a valid S1 artifact and exists so a future S1 allowlist
# widening can never silently widen this profile.
_SNAPSHOT_ROW_FIELDS = (
    "source_id",
    "provider_id",
    "source_class",
    "recommended_role",
    "protocol_profile_id",
    "protocol_wire_version",
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

# Caller-supplied chain-info inventory.  Exactly the venue-documented values; every other structural
# fact (curve, groups, encoded lengths, profile ids) is pinned here and never caller-controlled.
_CHAIN_INFO_TEXT_FIELDS = ("beacon_id", "chain_hash", "public_key", "scheme_id")
_CHAIN_INFO_INT_FIELDS = ("genesis_time_seconds", "period_seconds")
_CHAIN_INFO_FIELD_NAMES = (*_CHAIN_INFO_TEXT_FIELDS, *_CHAIN_INFO_INT_FIELDS)
_CHAIN_INFO_FIELD_NAME_SET = frozenset(_CHAIN_INFO_FIELD_NAMES)

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

_DESCRIPTOR_FIELD_NAMES = (
    "profile_schema",
    "profile_id",
    "source_id",
    "provider_id",
    "chain_hash",
    "beacon_id",
    "scheme_id",
    "curve_id",
    "period_seconds",
    "genesis_time_seconds",
    "public_key_group",
    "signature_group",
    "public_key_encoded_length",
    "signature_encoded_length",
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
        if getattr(self, "_sealed", False) and name in {"_reason", "reason", "args"}:
            raise AttributeError("MachineTimeDrandQuicknetChainProfileError is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in {"_reason", "reason", "args"}:
            raise AttributeError("MachineTimeDrandQuicknetChainProfileError is immutable")
        object.__delattr__(self, name)


def _err(reason: MachineTimeDrandQuicknetChainProfileReason) -> MachineTimeDrandQuicknetChainProfileError:
    return MachineTimeDrandQuicknetChainProfileError(reason)


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _is_lower_hex(value: str) -> bool:
    return bool(value) and len(value) % 2 == 0 and all(char in _HEX_CHARS for char in value)


def _text_is_canonical(value: str) -> bool:
    if not value or value != value.strip():
        return False
    return all(ord(char) >= 32 and ord(char) != 127 and char not in _LINE_SEPARATORS for char in value)


def _check_text_bound(value: str) -> None:
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.CANONICAL_TEXT_INVALID) from None
    if len(value) > _MAX_TEXT_CHARS or len(encoded) > _MAX_TEXT_CHARS:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RESOURCE_BOUND_EXCEEDED)


def _validated_chain_info(chain_info: object) -> dict[str, object]:
    """Prove the caller mapping is exact plain data before any comparison, ordering or hashing.

    Returns a FRESH plain dict, so the artifact never retains a caller-owned mutable mapping.
    """
    if type(chain_info) is not dict:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    for key in chain_info:
        if type(key) is not str:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)
    if len(chain_info) != len(_CHAIN_INFO_FIELD_NAMES) or frozenset(chain_info) != _CHAIN_INFO_FIELD_NAME_SET:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.FIELD_INVENTORY_INVALID)

    values = {name: chain_info[name] for name in _CHAIN_INFO_FIELD_NAMES}
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
    if len(material) != _PUBLIC_KEY_ENCODED_LENGTH:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_LENGTH_INVALID)
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
    if len(bytes.fromhex(registry_public_key)) != _PUBLIC_KEY_ENCODED_LENGTH:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.REGISTRY_BINDING_INVALID)
    return {
        "registry_digest": payload["registry_digest"],
        "entry_digest": record["entry_digest"],
        "public_key": registry_public_key,
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


def _derive(snapshot: object, registry: object, chain_info: object) -> tuple[dict[str, object], str]:
    """Total S2 precedence over the three exact inputs; the single derivation of every public value."""
    chain = _validated_chain_info(chain_info)
    bound_snapshot = _snapshot_binding(snapshot)
    bound_registry = _registry_binding(registry)

    if (
        chain["chain_hash"] != _CHAIN_HASH
        or chain["beacon_id"] != _BEACON_ID
        or chain["scheme_id"] != _SCHEME_ID
        or chain["period_seconds"] != _PERIOD_SECONDS
        or chain["genesis_time_seconds"] != _GENESIS_TIME_SECONDS
    ):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.CHAIN_IDENTITY_MISMATCH)

    supplied_key = chain["public_key"]
    if not _is_lower_hex(supplied_key):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_ENCODING_INVALID)
    decoded = bytes.fromhex(supplied_key)
    if len(decoded) != _PUBLIC_KEY_ENCODED_LENGTH:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_LENGTH_INVALID)
    if decoded != bound_snapshot["trust_material_bytes"] or supplied_key != bound_registry["public_key"]:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.PUBLIC_KEY_MISMATCH)

    values: dict[str, object] = {
        "profile_schema": MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA,
        "profile_id": MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID,
        "source_id": _SOURCE_ID,
        "provider_id": _PROVIDER_ID,
        "chain_hash": _CHAIN_HASH,
        "beacon_id": _BEACON_ID,
        "scheme_id": _SCHEME_ID,
        "curve_id": _CURVE_ID,
        "period_seconds": _PERIOD_SECONDS,
        "genesis_time_seconds": _GENESIS_TIME_SECONDS,
        "public_key_group": _PUBLIC_KEY_GROUP,
        "signature_group": _SIGNATURE_GROUP,
        "public_key_encoded_length": _PUBLIC_KEY_ENCODED_LENGTH,
        "signature_encoded_length": _SIGNATURE_ENCODED_LENGTH,
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

    def register(artifact: object, state: tuple[object, ...]) -> None:
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            current = registry.get(key)
            if current is not None and current[0] is dead:
                del registry[key]

        registry[key] = (weakref.ref(artifact, forget), state)

    def proven_parts(artifact: object) -> tuple[tuple[object, ...], tuple[object, ...]]:
        if type(artifact) is not MachineTimeDrandQuicknetChainProfile:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None or entry[0]() is not artifact:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        state = entry[1]
        if type(state) is not tuple or len(state) != 3:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT)
        try:
            values, digest = _derive(state[0], state[1], state[2])
        except MachineTimeDrandQuicknetChainProfileError:
            raise _err(MachineTimeDrandQuicknetChainProfileReason.ARTIFACT_INCONSISTENT) from None
        return tuple(values[name] for name in _DESCRIPTOR_FIELD_NAMES) + (digest,), state

    def proven_state(artifact: object) -> tuple[object, ...]:
        return proven_parts(artifact)[0]

    def create(snapshot: object, registry_artifact: object, chain_info: object) -> MachineTimeDrandQuicknetChainProfile:
        _derive(snapshot, registry_artifact, chain_info)
        artifact = object.__new__(MachineTimeDrandQuicknetChainProfile)
        register(artifact, (snapshot, registry_artifact, _validated_chain_info(chain_info)))
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
            values = dict(zip(_FIELD_NAMES, state, strict=True))
            rendered = (
                "MachineTimeDrandQuicknetChainProfile("
                f"source_id={values['source_id']}, "
                f"beacon_id={values['beacon_id']}, "
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
    return MachineTimeDrandQuicknetChainProfile, create, proven_state


(
    MachineTimeDrandQuicknetChainProfile,
    _create_profile,
    _proven_profile_state,
) = _build_profile_class()


def build_machine_time_drand_quicknet_chain_profile(
    *,
    snapshot: MachineTimeSourceTrustSnapshot,
    registry: MachineTimeSourceRegistry,
    chain_info: dict[str, object],
) -> MachineTimeDrandQuicknetChainProfile:
    """Bind one structural Quicknet chain profile; no provider verification or admission occurs."""
    return _create_profile(snapshot, registry, chain_info)  # type: ignore[operator]


def machine_time_drand_quicknet_chain_profile_commitment_descriptor(
    profile: MachineTimeDrandQuicknetChainProfile,
) -> dict[str, object]:
    if type(profile) is not MachineTimeDrandQuicknetChainProfile:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    state = _proven_profile_state(profile)  # type: ignore[operator]
    values = dict(zip(_FIELD_NAMES, state, strict=True))
    return _canonical_descriptor(values)


def machine_time_drand_quicknet_chain_profile_self_digest(profile: MachineTimeDrandQuicknetChainProfile) -> str:
    if type(profile) is not MachineTimeDrandQuicknetChainProfile:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE)
    return _proven_profile_state(profile)[-1]  # type: ignore[index,operator]


def _rebuild_machine_time_drand_quicknet_chain_profile(state: object) -> MachineTimeDrandQuicknetChainProfile:
    """Reconstruct only from the exact retained bindings, re-proving non-claims and the carried digest."""
    if type(state) is not tuple or len(state) != 5:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RECONSTRUCTION_INPUT_INVALID)
    flags = state[3]
    if type(flags) is not tuple or len(flags) != len(_PROFILE_FALSE_FLAGS):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.RECONSTRUCTION_INPUT_INVALID)
    if any(flag is not False for flag in flags):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    _, digest = _derive(state[0], state[1], state[2])
    carried = state[4]
    if not _is_hex64(carried):
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_INVALID)
    if carried != digest:
        raise _err(MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_MISMATCH)
    return _create_profile(state[0], state[1], state[2])  # type: ignore[operator]
