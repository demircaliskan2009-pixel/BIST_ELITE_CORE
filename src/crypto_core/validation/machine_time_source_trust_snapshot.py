"""Fail-closed structural machine-time source trust snapshots.

This module implements only the controller-authorized S1 structural artifact.
It permits exactly one Drand metadata row and binds caller-supplied raw group-key
bytes to SHA-256 commitments.  It does not verify BLS, admit a provider, fetch
data, use a clock, select a profile, or promote readiness/countability.
"""

from __future__ import annotations

import hashlib
import json
import weakref
from enum import Enum
from weakref import ReferenceType

MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA = "machine-time-source-trust-snapshot.v2"
MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_PROFILE_ID = "machine-time-source-trust-snapshot-structural.v2"

__all__ = (
    "MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA",
    "MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_PROFILE_ID",
    "MachineTimeSourceTrustSnapshot",
    "MachineTimeSourceTrustSnapshotError",
    "MachineTimeSourceTrustSnapshotReason",
    "build_machine_time_source_trust_snapshot",
    "machine_time_source_trust_snapshot_commitment_descriptor",
    "machine_time_source_trust_snapshot_self_digest",
    "reconstruct_machine_time_source_trust_snapshot",
    "validate_machine_time_source_trust_snapshot_collection",
)


_DIGEST_DOMAIN = b"machine-time-source-trust-snapshot.v2/self-digest\x00"
_REVOCATION_EVIDENCE_DOMAIN = b"machine-time-source-trust-snapshot.v2/revocation-evidence\x00"
_OFFICIAL_EVIDENCE_DOMAIN = b"machine-time-source-trust-snapshot.v2/official-evidence-packet\x00"
_MAX_TRUST_MATERIAL_BYTES = 65_536
_MAX_EVIDENCE_BYTES = 65_536
_MAX_TEXT_CHARS = 128
_MAX_TUPLE_LENGTH = 32
_MAX_COLLECTION_LENGTH = 256
_MAX_MAPPING_KEYS = 256
_MAX_CANONICAL_INT = (1 << 63) - 1
_MAX_REPR_CHARS = 512
_HEX_CHARS = frozenset("0123456789abcdef")
_SEALED_ARTIFACT_MESSAGE = "MachineTimeSourceTrustSnapshot is sealed and cannot be subclassed"
_SEALED_ARTIFACT_ATTR_MESSAGE = "MachineTimeSourceTrustSnapshot is immutable"
_SEALED_ERROR_MESSAGE = "MachineTimeSourceTrustSnapshotError is sealed and cannot be subclassed"
_DIRECT_CONSTRUCTION_MESSAGE = "use build_machine_time_source_trust_snapshot"
_ERROR_CONSTRUCTION_MESSAGE = "reason must be an exact MachineTimeSourceTrustSnapshotReason"
_ERROR_IMMUTABLE_MESSAGE = "MachineTimeSourceTrustSnapshotError is immutable"
_ERROR_UNSEALED_TEXT = "machine_time_source_trust_snapshot_error_unsealed"
# The seal itself is protected: it can never be deleted, reassigned or weakened, so the diagnostic
# cannot be altered by first removing the marker that used to gate this protection.  ``__class__``,
# ``__dict__`` and the note channel are guarded for the same reason: each is otherwise an ordinary
# writable path into visible diagnostic state.
_ERROR_IMMUTABLE_ATTRS = frozenset({"_reason", "reason", "args", "_sealed", "__class__", "__dict__", "__notes__"})

_FIELD_NAMES = (
    "snapshot_schema",
    "snapshot_id",
    "source_id",
    "provider_id",
    "source_class",
    "recommended_role",
    "protocol_profile_id",
    "protocol_wire_version",
    "independence_class",
    "trust_material_kind",
    "trust_material_bytes",
    "trust_material_encoding",
    "trust_material_fingerprint_algorithm",
    "trust_material_fingerprint",
    "valid_from",
    "valid_until",
    "supersedes_snapshot_id",
    "supersedes_key_id",
    "revocation_status",
    "revocation_evidence_digest",
    "official_evidence_packet_digest",
    "official_citation_ids",
    "dependency_profile_id",
    "fixture_corpus_id",
    "verification_policy_id",
    "governance_decision_ids",
    "approved_by",
    "approved_at",
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
    "snapshot_self_digest",
)
_INPUT_FIELD_NAMES = _FIELD_NAMES[:-1]
_DESCRIPTOR_FIELD_NAMES = tuple(name for name in _INPUT_FIELD_NAMES if name != "trust_material_bytes")
_DESCRIPTOR_FIELD_NAME_SET = frozenset(_DESCRIPTOR_FIELD_NAMES)
# A registry entry is exactly ``(owner_ref, state)`` and the registered state repeats the owner
# reference in its first slot, so an otherwise valid state belonging to a different artifact cannot be
# transplanted onto this artifact's key.
_REGISTRY_ENTRY_LENGTH = 2
_REGISTRY_STATE_LENGTH = len(_INPUT_FIELD_NAMES) + 3

# Controller contract MT4-S1-DRAND-ONLY-STRUCTURAL-ELIGIBILITY-V1.  This is deliberately a whole row:
# independently valid values must never form an accepted cross-product.
_ELIGIBLE_ROW = (
    "drand-quicknet-mainnet",
    "league-of-entropy",
    "distributed-threshold-randomness-beacon",
    "not_before",
    "drand-quicknet-signature-and-chain-info-offline.v1",
    "drand-http-api-v2-with-chain-info",
    "threshold-bls-beacon",
    "bls_group_public_key",
    "raw",
    "sha256",
    "D-DEP-02",
    "FX-DRAND-QUICKNET.v1",
    "deterministic_supplied_proof_verification_no_network.v1",
)
_ROW_FIELD_NAMES = (
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
_DRAND_CITATION_IDS = frozenset(
    {
        "DRAND-DEVELOPER",
        "DRAND-HTTP-API",
        "DRAND-QUICKNET-ANNOUNCEMENT",
        "DRAND-SPEC",
    }
)
_REVOCATION_STATUSES = frozenset({"not_revoked_per_archived_snapshot", "revoked", "revocation_evidence_absent"})
_OFFICIAL_EVIDENCE_KEY = "official_evidence_packet_digest"
_REVOCATION_EVIDENCE_KEY = "revocation_evidence_digest"


class MachineTimeSourceTrustSnapshotReason(str, Enum):
    """Closed failure inventory; each validation surface owns its documented order."""

    WRONG_INPUT_TYPE = "wrong_input_type"
    FIELD_INVENTORY_INVALID = "field_inventory_invalid"
    FIELD_TYPE_INVALID = "field_type_invalid"
    CANONICAL_TEXT_INVALID = "canonical_text_invalid"
    CLOSED_DOMAIN_VIOLATION = "closed_domain_violation"
    MT3_CROSS_CONSISTENCY_VIOLATION = "mt3_cross_consistency_violation"
    TRUST_MATERIAL_INVALID = "trust_material_invalid"
    FINGERPRINT_INVALID = "fingerprint_invalid"
    FINGERPRINT_MISMATCH = "fingerprint_mismatch"
    EVIDENCE_DIGEST_INVALID = "evidence_digest_invalid"
    EVIDENCE_DIGEST_MISMATCH = "evidence_digest_mismatch"
    TEMPORAL_CONTRACT_VIOLATION = "temporal_contract_violation"
    GOVERNANCE_STRUCTURAL_VIOLATION = "governance_structural_violation"
    SUPERSESSION_INVALID = "supersession_invalid"
    RESOURCE_BOUND_EXCEEDED = "resource_bound_exceeded"
    SELF_DIGEST_INVALID = "self_digest_invalid"
    SELF_DIGEST_MISMATCH = "self_digest_mismatch"
    RECONSTRUCTION_INPUT_INVALID = "reconstruction_input_invalid"
    COLLECTION_CANONICALITY_VIOLATION = "collection_canonicality_violation"
    SNAPSHOT_ARTIFACT_INCONSISTENT = "snapshot_artifact_inconsistent"


def _sealed_error_reason(error: object) -> MachineTimeSourceTrustSnapshotReason | None:
    """Read the sealed authority slot directly; ``None`` means the diagnostic was never constructed."""
    try:
        reason = object.__getattribute__(error, "_reason")
    except AttributeError:
        return None
    return reason if type(reason) is MachineTimeSourceTrustSnapshotReason else None


def _sealed_error_text(error: object) -> str:
    reason = _sealed_error_reason(error)
    return _ERROR_UNSEALED_TEXT if reason is None else reason.value


class MachineTimeSourceTrustSnapshotError(RuntimeError):
    """Closed diagnostic carrying one exact reason and no caller-controlled message.

    The immutable private reason slot is the only authority.  ``reason``, ``args``, ``str`` and
    ``repr`` are derived from that slot on every read instead of trusting ``BaseException``'s mutable
    argument slot, so a second ``__init__``, a direct ``RuntimeError.__init__`` /
    ``BaseException.__init__`` call, an ordinary attribute write or delete, a class reassignment and
    the note channel all leave visible diagnostic state exactly where construction sealed it.
    """

    __slots__ = ("_reason", "_sealed")

    def __init__(self, reason: MachineTimeSourceTrustSnapshotReason) -> None:
        # Construction happens exactly once; re-initialization is refused before anything is written.
        if _sealed_error_reason(self) is not None:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        if type(reason) is not MachineTimeSourceTrustSnapshotReason:
            raise TypeError(_ERROR_CONSTRUCTION_MESSAGE)
        RuntimeError.__init__(self, reason.value)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_sealed", True)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(_SEALED_ERROR_MESSAGE)

    @property
    def reason(self) -> MachineTimeSourceTrustSnapshotReason:
        return self._reason

    @property
    def args(self) -> tuple[str, ...]:
        return (_sealed_error_text(self),)

    @property
    def __notes__(self) -> tuple[str, ...]:
        # Refusing the read closes the instance-dictionary note channel too: this data descriptor
        # shadows any ``__notes__`` entry an attacker writes into the instance dictionary.
        raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)

    def add_note(self, note: object) -> None:
        raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)

    def __str__(self) -> str:
        return _sealed_error_text(self)

    def __repr__(self) -> str:
        return f"MachineTimeSourceTrustSnapshotError({_sealed_error_text(self)})"

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


def _err(reason: MachineTimeSourceTrustSnapshotReason) -> MachineTimeSourceTrustSnapshotError:
    return MachineTimeSourceTrustSnapshotError(reason)


def _paired_values(
    names: tuple[str, ...],
    values: tuple[object, ...],
    reason: MachineTimeSourceTrustSnapshotReason,
) -> dict[str, object]:
    """Pair exactly equal-length sequences.

    Length-checked ``zip`` is Python 3.10+ and this project's floor is 3.8, so the exact-length
    invariant is proven explicitly here instead.  Every call site already proves the length, which
    makes this a fail-closed backstop rather than a new validation surface.
    """
    if len(names) != len(values):
        raise _err(reason)
    return dict(zip(names, values))


def _mapping_copy(mapping: dict[str, object]) -> dict[str, object]:
    """The single copy point for caller mappings, isolated so its failure path stays auditable."""
    return dict(mapping)


def _stable_mapping_snapshot(
    mapping: object,
    reason: MachineTimeSourceTrustSnapshotReason,
) -> dict[str, object]:
    """Bound a caller mapping cheaply, then take exactly one snapshot.

    Validation and consumption both read only the returned snapshot, so a caller mapping cannot be
    validated in one state and consumed in another.  Mutation during the snapshot fails closed
    instead of leaking ``RuntimeError``.
    """
    if type(mapping) is not dict:
        raise _err(reason)
    if len(mapping) > _MAX_MAPPING_KEYS:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    try:
        snapshot = _mapping_copy(mapping)
    except RuntimeError:
        raise _err(reason) from None
    if len(snapshot) > _MAX_MAPPING_KEYS:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    for key in snapshot:
        if type(key) is not str:
            raise _err(reason)
    return snapshot


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _text_is_canonical(value: str, *, allow_empty: bool = False) -> bool:
    if not allow_empty and not value:
        return False
    if value != value.strip():
        return False
    return all(ord(char) >= 32 and ord(char) != 127 and char not in {"\u2028", "\u2029"} for char in value)


def _check_text_bound(value: str) -> None:
    # Cheap character bound first: an oversized string is rejected before it is ever encoded.
    if len(value) > _MAX_TEXT_CHARS:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    try:
        encoded = value.encode("utf-8")
    except UnicodeEncodeError:
        raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID) from None
    if len(encoded) > _MAX_TEXT_CHARS:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)


def _check_tuple_bound(value: tuple[object, ...]) -> None:
    if len(value) > _MAX_TUPLE_LENGTH:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)


def _canonical_descriptor(values: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for name in _DESCRIPTOR_FIELD_NAMES:
        value = values[name]
        payload[name] = list(value) if type(value) is tuple else value
    return payload


def _canonical_descriptor_text(values: dict[str, object]) -> str:
    try:
        return json.dumps(
            _canonical_descriptor(values),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
            allow_nan=False,
        )
    except (TypeError, ValueError):
        raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT) from None


def _self_digest(values: dict[str, object]) -> str:
    canonical = _canonical_descriptor_text(values)
    return hashlib.sha256(_DIGEST_DOMAIN + canonical.encode("utf-8")).hexdigest()


def _validate_values(values: object) -> tuple[dict[str, object], str]:
    """Perform the total S1 precedence over one exact 32-field construction view."""
    if type(values) is not dict:
        raise _err(MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)
    if tuple(values) != _INPUT_FIELD_NAMES:
        raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID)

    required_str = (
        "snapshot_schema",
        "snapshot_id",
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
        "trust_material_fingerprint",
        "revocation_status",
        "official_evidence_packet_digest",
        "dependency_profile_id",
        "fixture_corpus_id",
        "verification_policy_id",
    )
    optional_str = ("supersedes_snapshot_id", "supersedes_key_id", "revocation_evidence_digest", "approved_by")
    optional_int = ("valid_from", "valid_until", "approved_at")
    for name in required_str:
        if type(values[name]) is not str:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
    for name in optional_str:
        if values[name] is not None and type(values[name]) is not str:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
    for name in optional_int:
        if values[name] is not None and type(values[name]) is not int:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
    for name in ("official_citation_ids", "governance_decision_ids"):
        if type(values[name]) is not tuple:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
    for name in ("operational_use_approved", "quorum_countable", "source_reachable_proven", "proof_verified"):
        if type(values[name]) is not bool:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
    if type(values["trust_material_bytes"]) is not bytes:
        raise _err(MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID)

    trust_material = values["trust_material_bytes"]
    if not trust_material:
        raise _err(MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID)
    if len(trust_material) > _MAX_TRUST_MATERIAL_BYTES:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    for name in required_str:
        _check_text_bound(values[name])
    for name in optional_str:
        value = values[name]
        if value is not None:
            _check_text_bound(value)
    for name in ("official_citation_ids", "governance_decision_ids"):
        _check_tuple_bound(values[name])
    for name in optional_int:
        value = values[name]
        if value is not None and (value < 1 or value > _MAX_CANONICAL_INT):
            raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)

    for name in required_str:
        if not _text_is_canonical(values[name]):
            raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID)
    for name in optional_str:
        value = values[name]
        if value is not None and not _text_is_canonical(value):
            raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID)
    for name in ("official_citation_ids", "governance_decision_ids"):
        value = values[name]
        if not all(type(item) is str for item in value):
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
        # Cheap per-item character bound before canonical scanning, sorting and encoding: cardinality
        # was already bounded above, so no oversized item reaches the expensive canonical work.
        for item in value:
            if len(item) > _MAX_TEXT_CHARS:
                raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
        if not all(_text_is_canonical(item) for item in value):
            raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID)
        if tuple(sorted(value)) != value or len(set(value)) != len(value):
            raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID)
        for item in value:
            _check_text_bound(item)
    if not values["official_citation_ids"]:
        raise _err(MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID)

    if values["snapshot_schema"] != MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA:
        raise _err(MachineTimeSourceTrustSnapshotReason.CLOSED_DOMAIN_VIOLATION)
    if values["revocation_status"] not in _REVOCATION_STATUSES:
        raise _err(MachineTimeSourceTrustSnapshotReason.CLOSED_DOMAIN_VIOLATION)
    if not values["official_citation_ids"] or not set(values["official_citation_ids"]).issubset(_DRAND_CITATION_IDS):
        raise _err(MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION)
    if any(
        type(item) is not str
        or len(item) != 10
        or not item.startswith("GOV-MT4-")
        or not item[-2:].isdigit()
        or not 1 <= int(item[-2:]) <= 15
        for item in values["governance_decision_ids"]
    ):
        raise _err(MachineTimeSourceTrustSnapshotReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if tuple(values[name] for name in _ROW_FIELD_NAMES) != _ELIGIBLE_ROW:
        raise _err(MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION)

    valid_from = values["valid_from"]
    valid_until = values["valid_until"]
    if valid_from is not None and valid_until is not None and valid_from >= valid_until:
        raise _err(MachineTimeSourceTrustSnapshotReason.TEMPORAL_CONTRACT_VIOLATION)
    if (values["approved_by"] is None) != (values["approved_at"] is None):
        raise _err(MachineTimeSourceTrustSnapshotReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if values["supersedes_snapshot_id"] == values["snapshot_id"]:
        raise _err(MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID)
    if values["supersedes_snapshot_id"] is None:
        if values["supersedes_key_id"] is not None:
            raise _err(MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID)
    elif values["supersedes_key_id"] is None or not _is_hex64(values["supersedes_key_id"]):
        raise _err(MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID)
    if not all(
        values[name] is False
        for name in ("operational_use_approved", "quorum_countable", "source_reachable_proven", "proof_verified")
    ):
        raise _err(MachineTimeSourceTrustSnapshotReason.GOVERNANCE_STRUCTURAL_VIOLATION)

    if not _is_hex64(values["trust_material_fingerprint"]):
        raise _err(MachineTimeSourceTrustSnapshotReason.FINGERPRINT_INVALID)
    fingerprint = hashlib.sha256(trust_material).hexdigest()
    if values["trust_material_fingerprint"] != fingerprint:
        raise _err(MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH)
    if not _is_hex64(values["official_evidence_packet_digest"]):
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)
    revocation_digest = values["revocation_evidence_digest"]
    if values["revocation_status"] == "revocation_evidence_absent":
        if revocation_digest is not None:
            raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)
    elif not _is_hex64(revocation_digest):
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)

    validated = dict(values)
    return validated, _self_digest(validated)


def _validate_evidence_anchors(
    values: dict[str, object],
    official_evidence_packet_bytes: object,
    revocation_evidence_bytes: object,
) -> tuple[bytes, bytes | None]:
    if type(official_evidence_packet_bytes) is not bytes or not official_evidence_packet_bytes:
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)
    if len(official_evidence_packet_bytes) > _MAX_EVIDENCE_BYTES:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    official_digest = hashlib.sha256(_OFFICIAL_EVIDENCE_DOMAIN + official_evidence_packet_bytes).hexdigest()
    if official_digest != values[_OFFICIAL_EVIDENCE_KEY]:
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH)

    if values["revocation_status"] == "revocation_evidence_absent":
        if revocation_evidence_bytes is not None:
            raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)
        return official_evidence_packet_bytes, None
    if type(revocation_evidence_bytes) is not bytes or not revocation_evidence_bytes:
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)
    if len(revocation_evidence_bytes) > _MAX_EVIDENCE_BYTES:
        raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
    revocation_digest = hashlib.sha256(_REVOCATION_EVIDENCE_DOMAIN + revocation_evidence_bytes).hexdigest()
    if revocation_digest != values[_REVOCATION_EVIDENCE_KEY]:
        raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH)
    return official_evidence_packet_bytes, revocation_evidence_bytes


def _descriptor_values(descriptor: object) -> dict[str, object]:
    # One bounded snapshot is validated and returned; the caller mapping is never read again, so an
    # added unknown key or a removed required key cannot slip between validation and consumption.
    values = _stable_mapping_snapshot(descriptor, MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    if len(values) != len(_DESCRIPTOR_FIELD_NAMES) or frozenset(values) != _DESCRIPTOR_FIELD_NAME_SET:
        raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID)
    return values


def _linked_evidence_anchors(values: dict[str, object], linked_evidence: object) -> tuple[bytes, bytes | None]:
    evidence = _stable_mapping_snapshot(
        linked_evidence, MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    )
    expected = {_OFFICIAL_EVIDENCE_KEY}
    if values["revocation_status"] != "revocation_evidence_absent":
        expected.add(_REVOCATION_EVIDENCE_KEY)
    if len(evidence) != len(expected) or frozenset(evidence) != expected:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    for key in evidence:
        if type(evidence[key]) is not bytes:
            raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    official = evidence[_OFFICIAL_EVIDENCE_KEY]
    revocation = evidence.get(_REVOCATION_EVIDENCE_KEY)
    return _validate_evidence_anchors(values, official, revocation)


def _build_snapshot_class() -> tuple[type, object, object]:
    registry: dict[int, tuple[object, ...]] = {}

    def entry_is_well_formed(entry: object) -> bool:
        """Prove the exact entry shape before anything is indexed or dereferenced."""
        if type(entry) is not tuple or len(entry) != _REGISTRY_ENTRY_LENGTH:
            return False
        return type(entry[0]) is ReferenceType

    def register(artifact: object, state: tuple[object, ...]) -> None:
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            current = registry.get(key)
            # A corrupted entry must not raise IndexError/TypeError inside a weakref callback, and a
            # replacement entry must survive a stale callback from the artifact it replaced.
            if entry_is_well_formed(current) and current[0] is dead:
                del registry[key]

        owner = weakref.ref(artifact, forget)
        registry[key] = (owner, (owner,) + state)

    def proven_parts(artifact: object) -> tuple[tuple[object, ...], bytes, bytes | None]:
        if type(artifact) is not MachineTimeSourceTrustSnapshot:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        key = id(artifact)
        entry = registry.get(key)
        if not entry_is_well_formed(entry):
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        owner = entry[0]
        state = entry[1]
        if owner() is not artifact:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        # The state carries its own owner reference, so a coherent state donated by another artifact
        # fails closed here instead of being reported under this artifact's identity.
        if type(state) is not tuple or len(state) != _REGISTRY_STATE_LENGTH or state[0] is not owner:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        values = _paired_values(
            _INPUT_FIELD_NAMES,
            state[1 : len(_INPUT_FIELD_NAMES) + 1],
            MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT,
        )
        try:
            validated, digest = _validate_values(values)
            official, revocation = _validate_evidence_anchors(
                validated,
                state[len(_INPUT_FIELD_NAMES) + 1],
                state[len(_INPUT_FIELD_NAMES) + 2],
            )
        except MachineTimeSourceTrustSnapshotError:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT) from None
        # Recheck the exact entry identity before returning trusted state: nothing may have replaced
        # the entry while it was being proven.
        if registry.get(key) is not entry:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        public_state = tuple(validated[name] for name in _INPUT_FIELD_NAMES) + (digest,)
        return public_state, official, revocation

    def proven_state(artifact: object) -> tuple[object, ...]:
        return proven_parts(artifact)[0]

    def proven_rebuild_state(artifact: object) -> tuple[object, ...]:
        public_state, official, revocation = proven_parts(artifact)
        return public_state + (official, revocation)

    def create(
        values: dict[str, object],
        official_evidence_packet_bytes: object,
        revocation_evidence_bytes: object,
    ) -> MachineTimeSourceTrustSnapshot:
        validated, _ = _validate_values(values)
        official, revocation = _validate_evidence_anchors(
            validated, official_evidence_packet_bytes, revocation_evidence_bytes
        )
        artifact = object.__new__(MachineTimeSourceTrustSnapshot)
        register(artifact, tuple(validated[name] for name in _INPUT_FIELD_NAMES) + (official, revocation))
        return artifact

    class MachineTimeSourceTrustSnapshot:
        """Sealed S1 structural binding for exactly one controller-allowlisted Drand row.

        The artifact binds caller-supplied bytes and structural references only.  It does not establish
        provider identity, BLS validity, source reachability, proof verification, time truth, readiness,
        countability, quorum, or any operational approval.
        """

        __slots__ = ("__weakref__",)
        __hash__ = None

        def __new__(cls, *args: object, **kwargs: object) -> MachineTimeSourceTrustSnapshot:
            raise TypeError(_DIRECT_CONSTRUCTION_MESSAGE)

        def __init_subclass__(cls, **kwargs: object) -> None:
            raise TypeError(_SEALED_ARTIFACT_MESSAGE)

        def __setattr__(self, name: str, value: object) -> None:
            raise AttributeError(_SEALED_ARTIFACT_ATTR_MESSAGE)

        def __delattr__(self, name: str) -> None:
            raise AttributeError(_SEALED_ARTIFACT_ATTR_MESSAGE)

        def __repr__(self) -> str:
            state = proven_state(self)
            values = _paired_values(
                _FIELD_NAMES, state, MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
            )
            rendered = (
                "MachineTimeSourceTrustSnapshot("
                f"snapshot_id=<str len={len(values['snapshot_id'])}>, "
                f"source_id=<str len={len(values['source_id'])}>, "
                f"provider_id=<str len={len(values['provider_id'])}>, "
                f"protocol_profile_id=<str len={len(values['protocol_profile_id'])}>, "
                f"trust_material=<bytes len={len(values['trust_material_bytes'])} "
                f"fingerprint={values['trust_material_fingerprint']}>, "
                f"citations=<tuple count={len(values['official_citation_ids'])}>, "
                f"governance_decisions=<tuple count={len(values['governance_decision_ids'])}>, "
                f"self_digest={values['snapshot_self_digest']})"
            )
            if not rendered.isascii() or "\n" in rendered or "\r" in rendered or len(rendered) > _MAX_REPR_CHARS:
                raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
            return rendered

        def __str__(self) -> str:
            return self.__repr__()

        def __bool__(self) -> bool:
            proven_state(self)
            return True

        def __eq__(self, other: object) -> bool:
            proven_state(self)
            if type(other) is not MachineTimeSourceTrustSnapshot:
                return False
            if self is other:
                return True
            proven_state(other)
            return False

        def __ne__(self, other: object) -> bool:
            return not self.__eq__(other)

        def __reduce__(self) -> tuple[object, tuple[tuple[object, ...]]]:
            return (_rebuild_machine_time_source_trust_snapshot, (proven_rebuild_state(self),))

    def make_property(index: int):
        def getter(self: MachineTimeSourceTrustSnapshot) -> object:
            return proven_state(self)[index]

        return property(getter)

    for index, name in enumerate(_FIELD_NAMES):
        setattr(MachineTimeSourceTrustSnapshot, name, make_property(index))
    MachineTimeSourceTrustSnapshot.__qualname__ = "MachineTimeSourceTrustSnapshot"
    MachineTimeSourceTrustSnapshot.__module__ = __name__
    return MachineTimeSourceTrustSnapshot, create, proven_state


(
    MachineTimeSourceTrustSnapshot,
    _create_snapshot,
    _proven_snapshot_state,
) = _build_snapshot_class()


def _create_from_values(
    values: dict[str, object],
    official_evidence_packet_bytes: object,
    revocation_evidence_bytes: object,
) -> MachineTimeSourceTrustSnapshot:
    return _create_snapshot(values, official_evidence_packet_bytes, revocation_evidence_bytes)  # type: ignore[operator]


def build_machine_time_source_trust_snapshot(
    *,
    snapshot_schema: str,
    snapshot_id: str,
    source_id: str,
    provider_id: str,
    source_class: str,
    recommended_role: str,
    protocol_profile_id: str,
    protocol_wire_version: str,
    independence_class: str,
    trust_material_kind: str,
    trust_material_bytes: bytes,
    trust_material_encoding: str,
    trust_material_fingerprint_algorithm: str,
    trust_material_fingerprint: str,
    valid_from: int | None,
    valid_until: int | None,
    supersedes_snapshot_id: str | None,
    supersedes_key_id: str | None,
    revocation_status: str,
    revocation_evidence_digest: str | None,
    official_evidence_packet_digest: str,
    official_citation_ids: tuple[str, ...],
    dependency_profile_id: str,
    fixture_corpus_id: str,
    verification_policy_id: str,
    governance_decision_ids: tuple[str, ...],
    approved_by: str | None,
    approved_at: int | None,
    operational_use_approved: bool,
    quorum_countable: bool,
    source_reachable_proven: bool,
    proof_verified: bool,
    official_evidence_packet_bytes: bytes,
    revocation_evidence_bytes: bytes | None,
) -> MachineTimeSourceTrustSnapshot:
    """Build one fully evidence-bound raw-data S1 artifact; no provider verification occurs."""
    return _create_from_values(
        {
            "snapshot_schema": snapshot_schema,
            "snapshot_id": snapshot_id,
            "source_id": source_id,
            "provider_id": provider_id,
            "source_class": source_class,
            "recommended_role": recommended_role,
            "protocol_profile_id": protocol_profile_id,
            "protocol_wire_version": protocol_wire_version,
            "independence_class": independence_class,
            "trust_material_kind": trust_material_kind,
            "trust_material_bytes": trust_material_bytes,
            "trust_material_encoding": trust_material_encoding,
            "trust_material_fingerprint_algorithm": trust_material_fingerprint_algorithm,
            "trust_material_fingerprint": trust_material_fingerprint,
            "valid_from": valid_from,
            "valid_until": valid_until,
            "supersedes_snapshot_id": supersedes_snapshot_id,
            "supersedes_key_id": supersedes_key_id,
            "revocation_status": revocation_status,
            "revocation_evidence_digest": revocation_evidence_digest,
            "official_evidence_packet_digest": official_evidence_packet_digest,
            "official_citation_ids": official_citation_ids,
            "dependency_profile_id": dependency_profile_id,
            "fixture_corpus_id": fixture_corpus_id,
            "verification_policy_id": verification_policy_id,
            "governance_decision_ids": governance_decision_ids,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "operational_use_approved": operational_use_approved,
            "quorum_countable": quorum_countable,
            "source_reachable_proven": source_reachable_proven,
            "proof_verified": proof_verified,
        },
        official_evidence_packet_bytes,
        revocation_evidence_bytes,
    )


def machine_time_source_trust_snapshot_commitment_descriptor(
    snapshot: MachineTimeSourceTrustSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not MachineTimeSourceTrustSnapshot:
        raise _err(MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)
    state = _proven_snapshot_state(snapshot)  # type: ignore[operator]
    values = _paired_values(_FIELD_NAMES, state, MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
    return _canonical_descriptor(values)


def machine_time_source_trust_snapshot_self_digest(snapshot: MachineTimeSourceTrustSnapshot) -> str:
    if type(snapshot) is not MachineTimeSourceTrustSnapshot:
        raise _err(MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)
    return _proven_snapshot_state(snapshot)[-1]  # type: ignore[index,operator]


def reconstruct_machine_time_source_trust_snapshot(
    descriptor: dict[str, object],
    *,
    trust_material_bytes: bytes,
    carried_snapshot_self_digest: str | None = None,
    linked_evidence: dict[str, bytes] | None = None,
) -> MachineTimeSourceTrustSnapshot:
    """Reconstruct only with raw trust bytes and retained raw evidence anchors."""
    if type(trust_material_bytes) is not bytes:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    if carried_snapshot_self_digest is not None and type(carried_snapshot_self_digest) is not str:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    values = _descriptor_values(descriptor)
    for name in ("official_citation_ids", "governance_decision_ids"):
        value = values[name]
        if type(value) is not list:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
        # Cardinality before conversion: an oversized caller list is rejected without materializing a
        # second container of the same size.
        if len(value) > _MAX_TUPLE_LENGTH:
            raise _err(MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED)
        values[name] = tuple(value)
    values["trust_material_bytes"] = trust_material_bytes
    ordered = {name: values[name] for name in _INPUT_FIELD_NAMES}
    validated, digest = _validate_values(ordered)
    official, revocation = _linked_evidence_anchors(validated, linked_evidence)
    if carried_snapshot_self_digest is not None:
        if not _is_hex64(carried_snapshot_self_digest):
            raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_INVALID)
        if carried_snapshot_self_digest != digest:
            raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH)
    return _create_from_values(validated, official, revocation)


def _rebuild_machine_time_source_trust_snapshot(state: object) -> MachineTimeSourceTrustSnapshot:
    if type(state) is not tuple or len(state) != len(_FIELD_NAMES) + 2:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    values = _paired_values(
        _INPUT_FIELD_NAMES,
        state[: len(_INPUT_FIELD_NAMES)],
        MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID,
    )
    validated, digest = _validate_values(values)
    carried_digest = state[len(_INPUT_FIELD_NAMES)]
    if type(carried_digest) is not str or not _is_hex64(carried_digest):
        raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_INVALID)
    if carried_digest != digest:
        raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH)
    official = state[len(_FIELD_NAMES)]
    revocation = state[len(_FIELD_NAMES) + 1]
    _validate_evidence_anchors(validated, official, revocation)
    return _create_from_values(validated, official, revocation)


def validate_machine_time_source_trust_snapshot_collection(
    snapshots: tuple[MachineTimeSourceTrustSnapshot, ...],
) -> tuple[MachineTimeSourceTrustSnapshot, ...]:
    if type(snapshots) is not tuple:
        raise _err(MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)
    if len(snapshots) > _MAX_COLLECTION_LENGTH:
        raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
    if not all(type(snapshot) is MachineTimeSourceTrustSnapshot for snapshot in snapshots):
        raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
    views = [_proven_snapshot_state(snapshot) for snapshot in snapshots]  # type: ignore[operator]
    ids = [view[1] for view in views]
    if len(set(ids)) != len(ids):
        raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
    by_id = {view[1]: view for view in views}

    successor_counts: dict[object, int] = {}
    superseded: set[object] = set()
    for view in views:
        snapshot_id = view[1]
        target = view[16]
        predecessor_key_id = view[17]
        if target is None:
            if predecessor_key_id is not None:
                raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
            continue
        predecessor = by_id.get(target)
        if predecessor is None or target == snapshot_id or predecessor_key_id != predecessor[13]:
            raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
        successor_counts[target] = successor_counts.get(target, 0) + 1
        if successor_counts[target] > 1:
            raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
        superseded.add(target)

    for view in views:
        seen: set[object] = {view[1]}
        target = view[16]
        while target is not None:
            if target in seen:
                raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
            seen.add(target)
            target = by_id[target][16]

    active_keys: set[tuple[object, object, object]] = set()
    for view in views:
        if view[1] in superseded:
            continue
        key = (view[2], view[6], view[13])
        if key in active_keys:
            raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
        active_keys.add(key)
    return snapshots
