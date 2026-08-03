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
_MAX_TEXT_CHARS = 128
_MAX_TUPLE_LENGTH = 32
_MAX_COLLECTION_LENGTH = 256
_MAX_CANONICAL_INT = (1 << 63) - 1
_MAX_REPR_CHARS = 512
_HEX_CHARS = frozenset("0123456789abcdef")
_SEALED_ARTIFACT_MESSAGE = "MachineTimeSourceTrustSnapshot is sealed and cannot be subclassed"
_DIRECT_CONSTRUCTION_MESSAGE = "use build_machine_time_source_trust_snapshot"
_ERROR_CONSTRUCTION_MESSAGE = "reason must be an exact MachineTimeSourceTrustSnapshotReason"

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


class MachineTimeSourceTrustSnapshotReason(str, Enum):
    """Closed failure inventory in the implementation's total precedence order."""

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
    TEMPORAL_CONTRACT_VIOLATION = "temporal_contract_violation"
    GOVERNANCE_STRUCTURAL_VIOLATION = "governance_structural_violation"
    SUPERSESSION_INVALID = "supersession_invalid"
    RESOURCE_BOUND_EXCEEDED = "resource_bound_exceeded"
    SERIALIZATION_FAILED = "serialization_failed"
    SELF_DIGEST_INVALID = "self_digest_invalid"
    SELF_DIGEST_MISMATCH = "self_digest_mismatch"
    RECONSTRUCTION_INPUT_INVALID = "reconstruction_input_invalid"
    COLLECTION_CANONICALITY_VIOLATION = "collection_canonicality_violation"
    SNAPSHOT_ARTIFACT_INCONSISTENT = "snapshot_artifact_inconsistent"


class MachineTimeSourceTrustSnapshotError(RuntimeError):
    """Closed diagnostic carrying one exact reason and no caller-controlled message."""

    __slots__ = ("_reason", "_sealed")

    def __init__(self, reason: MachineTimeSourceTrustSnapshotReason) -> None:
        if type(reason) is not MachineTimeSourceTrustSnapshotReason:
            raise TypeError(_ERROR_CONSTRUCTION_MESSAGE)
        RuntimeError.__init__(self, reason.value)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_sealed", True)

    @property
    def reason(self) -> MachineTimeSourceTrustSnapshotReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_sealed", False) and name in {"_reason", "reason", "args"}:
            raise AttributeError("MachineTimeSourceTrustSnapshotError is immutable")
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in {"_reason", "reason", "args"}:
            raise AttributeError("MachineTimeSourceTrustSnapshotError is immutable")
        object.__delattr__(self, name)


def _err(reason: MachineTimeSourceTrustSnapshotReason) -> MachineTimeSourceTrustSnapshotError:
    return MachineTimeSourceTrustSnapshotError(reason)


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _text_is_canonical(value: str, *, allow_empty: bool = False) -> bool:
    if not allow_empty and not value:
        return False
    if value != value.strip():
        return False
    return all(ord(char) >= 32 and ord(char) != 127 and char not in {"\u2028", "\u2029"} for char in value)


def _check_text_bound(value: str) -> None:
    if len(value) > _MAX_TEXT_CHARS or len(value.encode("utf-8")) > _MAX_TEXT_CHARS:
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
        raise _err(MachineTimeSourceTrustSnapshotReason.SERIALIZATION_FAILED) from None


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
    if values["supersedes_snapshot_id"] is None and values["supersedes_key_id"] is not None:
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


def _validate_linked_evidence(values: dict[str, object], linked_evidence: object) -> None:
    if type(linked_evidence) is not dict:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    expected = {"official_evidence_packet_digest"}
    if values["revocation_evidence_digest"] is not None:
        expected.add("revocation_evidence_digest")
    if set(linked_evidence) != expected or not all(type(key) is str for key in linked_evidence):
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    for key in expected:
        raw = linked_evidence[key]
        if type(raw) is not bytes:
            raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
        domain = _OFFICIAL_EVIDENCE_DOMAIN if key == "official_evidence_packet_digest" else _REVOCATION_EVIDENCE_DOMAIN
        if hashlib.sha256(domain + raw).hexdigest() != values[key]:
            raise _err(MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID)


def _build_snapshot_class() -> tuple[type, object, object]:
    registry: dict[int, tuple[ReferenceType, tuple[object, ...]]] = {}

    def register(artifact: object, state: tuple[object, ...]) -> None:
        key = id(artifact)

        def forget(dead: ReferenceType, key: int = key) -> None:
            current = registry.get(key)
            if current is not None and current[0] is dead:
                del registry[key]

        registry[key] = (weakref.ref(artifact, forget), state)

    def proven_state(artifact: object) -> tuple[object, ...]:
        if type(artifact) is not MachineTimeSourceTrustSnapshot:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        entry = registry.get(id(artifact))
        if entry is None or entry[0]() is not artifact:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        state = entry[1]
        if type(state) is not tuple or len(state) != len(_INPUT_FIELD_NAMES):
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT)
        try:
            values = dict(zip(_INPUT_FIELD_NAMES, state, strict=True))
        except (TypeError, ValueError):
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT) from None
        try:
            _, digest = _validate_values(values)
        except MachineTimeSourceTrustSnapshotError:
            raise _err(MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT) from None
        return state + (digest,)

    def create(values: dict[str, object]) -> MachineTimeSourceTrustSnapshot:
        validated, _ = _validate_values(values)
        artifact = object.__new__(MachineTimeSourceTrustSnapshot)
        register(artifact, tuple(validated[name] for name in _INPUT_FIELD_NAMES))
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

        def __repr__(self) -> str:
            state = proven_state(self)
            values = dict(zip(_FIELD_NAMES, state, strict=True))
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
            return (_rebuild_machine_time_source_trust_snapshot, (proven_state(self),))

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


def _create_from_values(values: dict[str, object]) -> MachineTimeSourceTrustSnapshot:
    return _create_snapshot(values)  # type: ignore[operator]


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
) -> MachineTimeSourceTrustSnapshot:
    """Build the one public raw-data S1 artifact; no provider verification occurs."""
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
        }
    )


def machine_time_source_trust_snapshot_commitment_descriptor(
    snapshot: MachineTimeSourceTrustSnapshot,
) -> dict[str, object]:
    if type(snapshot) is not MachineTimeSourceTrustSnapshot:
        raise _err(MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)
    state = _proven_snapshot_state(snapshot)  # type: ignore[operator]
    values = dict(zip(_FIELD_NAMES, state, strict=True))
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
    """Reconstruct only with raw trust bytes and every raw linked-evidence input."""
    if type(descriptor) is not dict or type(trust_material_bytes) is not bytes:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    if len(descriptor) != len(_DESCRIPTOR_FIELD_NAMES) or set(descriptor) != set(_DESCRIPTOR_FIELD_NAMES):
        raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID)
    if carried_snapshot_self_digest is not None and type(carried_snapshot_self_digest) is not str:
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    values = dict(descriptor)
    for name in ("official_citation_ids", "governance_decision_ids"):
        if type(values[name]) is not list:
            raise _err(MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID)
        values[name] = tuple(values[name])
    values["trust_material_bytes"] = trust_material_bytes
    ordered = {name: values[name] for name in _INPUT_FIELD_NAMES}
    validated, digest = _validate_values(ordered)
    _validate_linked_evidence(validated, linked_evidence)
    if carried_snapshot_self_digest is not None:
        if not _is_hex64(carried_snapshot_self_digest):
            raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_INVALID)
        if carried_snapshot_self_digest != digest:
            raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH)
    return _create_from_values(validated)


def _rebuild_machine_time_source_trust_snapshot(state: object) -> MachineTimeSourceTrustSnapshot:
    if type(state) is not tuple or len(state) != len(_FIELD_NAMES):
        raise _err(MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID)
    values = dict(zip(_INPUT_FIELD_NAMES, state[:-1], strict=True))
    validated, digest = _validate_values(values)
    if type(state[-1]) is not str or state[-1] != digest:
        raise _err(MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH)
    return _create_from_values(validated)


def validate_machine_time_source_trust_snapshot_collection(
    snapshots: tuple[MachineTimeSourceTrustSnapshot, ...],
    *,
    require_single_active_per_profile_key: bool,
) -> tuple[MachineTimeSourceTrustSnapshot, ...]:
    if type(snapshots) is not tuple or type(require_single_active_per_profile_key) is not bool:
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
    superseded = {view[16] for view in views if view[16] is not None}
    for view in views:
        target = view[16]
        if target is not None and target not in by_id:
            raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
        seen: set[str] = set()
        while target is not None:
            if target in seen:
                raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
            seen.add(target)
            target = by_id[target][16]
    if require_single_active_per_profile_key:
        active_keys: set[tuple[object, object, object]] = set()
        for view in views:
            if view[1] in superseded:
                continue
            key = (view[6], view[2], view[13])
            if key in active_keys:
                raise _err(MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION)
            active_keys.add(key)
    return snapshots
