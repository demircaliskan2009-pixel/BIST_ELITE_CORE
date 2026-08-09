import copy
import gc
import hashlib
import inspect
import itertools
import json
import pickle
import weakref

import pytest

from crypto_core.validation import machine_time_source_trust_snapshot as module

_OFFICIAL = b"official-evidence"
_REVOCATION = b"revocation-evidence"
_MISSING = object()

# ---------------------------------------------------------------------------------------------
# Test-owned contracts.  These literals deliberately duplicate production inventories instead of
# importing them: a test that reads the production tuple cannot observe that tuple losing a member,
# so every contract that must not silently shrink is restated here in full.
# ---------------------------------------------------------------------------------------------
_EXPECTED_REASONS: tuple[tuple[str, str], ...] = (
    ("WRONG_INPUT_TYPE", "wrong_input_type"),
    ("FIELD_INVENTORY_INVALID", "field_inventory_invalid"),
    ("FIELD_TYPE_INVALID", "field_type_invalid"),
    ("CANONICAL_TEXT_INVALID", "canonical_text_invalid"),
    ("CLOSED_DOMAIN_VIOLATION", "closed_domain_violation"),
    ("MT3_CROSS_CONSISTENCY_VIOLATION", "mt3_cross_consistency_violation"),
    ("TRUST_MATERIAL_INVALID", "trust_material_invalid"),
    ("FINGERPRINT_INVALID", "fingerprint_invalid"),
    ("FINGERPRINT_MISMATCH", "fingerprint_mismatch"),
    ("EVIDENCE_DIGEST_INVALID", "evidence_digest_invalid"),
    ("EVIDENCE_DIGEST_MISMATCH", "evidence_digest_mismatch"),
    ("TEMPORAL_CONTRACT_VIOLATION", "temporal_contract_violation"),
    ("GOVERNANCE_STRUCTURAL_VIOLATION", "governance_structural_violation"),
    ("SUPERSESSION_INVALID", "supersession_invalid"),
    ("RESOURCE_BOUND_EXCEEDED", "resource_bound_exceeded"),
    ("SELF_DIGEST_INVALID", "self_digest_invalid"),
    ("SELF_DIGEST_MISMATCH", "self_digest_mismatch"),
    ("RECONSTRUCTION_INPUT_INVALID", "reconstruction_input_invalid"),
    ("COLLECTION_CANONICALITY_VIOLATION", "collection_canonicality_violation"),
    ("SNAPSHOT_ARTIFACT_INCONSISTENT", "snapshot_artifact_inconsistent"),
)
# A diagnostic is a closed identifier, never prose and never caller text.
_MAX_REASON_VALUE_CHARS = 48
_REASON_VALUE_ALPHABET = frozenset("abcdefghijklmnopqrstuvwxyz0123456789_")
_EXPECTED_ERROR_IMMUTABLE_ATTRS = frozenset(
    {"_reason", "reason", "args", "_sealed", "__class__", "__dict__", "__notes__"}
)
_EXPECTED_ROW_FIELD_NAMES: tuple[str, ...] = (
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
_EXPECTED_ELIGIBLE_ROW: tuple[str, ...] = (
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
_EXPECTED_REQUIRED_TEXT_FIELDS: tuple[str, ...] = (
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
_EXPECTED_OPTIONAL_TEXT_FIELDS: tuple[str, ...] = (
    "supersedes_snapshot_id",
    "supersedes_key_id",
    "revocation_evidence_digest",
    "approved_by",
)
_EXPECTED_PROTECTED_FALSE_FIELDS: tuple[str, ...] = (
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
)

_EXPECTED_SELF_DIGEST_DOMAIN = b"machine-time-source-trust-snapshot.v2/self-digest\x00"
_EXPECTED_SELF_DIGEST = "18496b4cc0d983006d044efced524111d874bb56ab57da76d55e92df88c1d5bc"
_EXPECTED_DESCRIPTOR: dict[str, object] = {
    "snapshot_schema": "machine-time-source-trust-snapshot.v2",
    "snapshot_id": "drand-snapshot-001",
    "source_id": "drand-quicknet-mainnet",
    "provider_id": "league-of-entropy",
    "source_class": "distributed-threshold-randomness-beacon",
    "recommended_role": "not_before",
    "protocol_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
    "protocol_wire_version": "drand-http-api-v2-with-chain-info",
    "independence_class": "threshold-bls-beacon",
    "trust_material_kind": "bls_group_public_key",
    "trust_material_encoding": "raw",
    "trust_material_fingerprint_algorithm": "sha256",
    "trust_material_fingerprint": "739b863c9892606af50c4a5a790d231ef852e52ed58c6dea7078e587d6b2b690",
    "valid_from": None,
    "valid_until": None,
    "supersedes_snapshot_id": None,
    "supersedes_key_id": None,
    "revocation_status": "revocation_evidence_absent",
    "revocation_evidence_digest": None,
    "official_evidence_packet_digest": "18719671d29bda67acfc0b4c88799a466342ec0839e17385b05a9530796495d1",
    "official_citation_ids": ["DRAND-DEVELOPER"],
    "dependency_profile_id": "D-DEP-02",
    "fixture_corpus_id": "FX-DRAND-QUICKNET.v1",
    "verification_policy_id": "deterministic_supplied_proof_verification_no_network.v1",
    "governance_decision_ids": [],
    "approved_by": None,
    "approved_at": None,
    "operational_use_approved": False,
    "quorum_countable": False,
    "source_reachable_proven": False,
    "proof_verified": False,
}
_EXPECTED_CANONICAL_JSON = (
    '{"approved_at":null,"approved_by":null,"dependency_profile_id":"D-DEP-02",'
    '"fixture_corpus_id":"FX-DRAND-QUICKNET.v1","governance_decision_ids":[],'
    '"independence_class":"threshold-bls-beacon","official_citation_ids":["DRAND-DEVELOPER"],'
    '"official_evidence_packet_digest":"18719671d29bda67acfc0b4c88799a466342ec0839e17385b05a9530796495d1",'
    '"operational_use_approved":false,"proof_verified":false,'
    '"protocol_profile_id":"drand-quicknet-signature-and-chain-info-offline.v1",'
    '"protocol_wire_version":"drand-http-api-v2-with-chain-info","provider_id":"league-of-entropy",'
    '"quorum_countable":false,"recommended_role":"not_before","revocation_evidence_digest":null,'
    '"revocation_status":"revocation_evidence_absent","snapshot_id":"drand-snapshot-001",'
    '"snapshot_schema":"machine-time-source-trust-snapshot.v2",'
    '"source_class":"distributed-threshold-randomness-beacon","source_id":"drand-quicknet-mainnet",'
    '"source_reachable_proven":false,"supersedes_key_id":null,"supersedes_snapshot_id":null,'
    '"trust_material_encoding":"raw",'
    '"trust_material_fingerprint":"739b863c9892606af50c4a5a790d231ef852e52ed58c6dea7078e587d6b2b690",'
    '"trust_material_fingerprint_algorithm":"sha256","trust_material_kind":"bls_group_public_key",'
    '"valid_from":null,"valid_until":null,'
    '"verification_policy_id":"deterministic_supplied_proof_verification_no_network.v1"}'
)

# Second known-answer vector.  The first vector is all-ASCII with every optional field null, so it
# cannot observe ensure_ascii.  This one carries non-ASCII BMP and non-BMP scalars and sets every
# optional field, which pins ensure_ascii=True, the escaped canonical form, and the non-null branches.
_UNICODE_TRUST_MATERIAL = b"drand-group-key-bytes-unicode"
_UNICODE_SNAPSHOT_ID = "é" * 8 + "\U0001f600"
_UNICODE_APPROVED_BY = "governor-ü"
_UNICODE_SUPERSEDES_SNAPSHOT_ID = "prior-é"
_UNICODE_SUPERSEDES_KEY_ID = "0052b1b3f2daec4e50338f81ab960028e6f07cae5c094793770b0cb29d35a605"
_UNICODE_TRUST_MATERIAL_FINGERPRINT = "9d00bd85a7ccea69f029fb91ea4cf13ecd5892b3211c81de78fa278932dd49df"
_UNICODE_REVOCATION_EVIDENCE_DIGEST = "5effa12b1a68fe32a2aa34bccc632fcfe9c18c66b29b0b056106ef28de7821a1"
_UNICODE_VALID_UNTIL = 9_223_372_036_854_775_807
_UNICODE_OFFICIAL_CITATION_IDS = (
    "DRAND-DEVELOPER",
    "DRAND-HTTP-API",
    "DRAND-QUICKNET-ANNOUNCEMENT",
    "DRAND-SPEC",
)
_UNICODE_GOVERNANCE_DECISION_IDS = ("GOV-MT4-01", "GOV-MT4-15")
_EXPECTED_UNICODE_SELF_DIGEST = "54fadca5b4c4f5e10358c88ef00c80dd1060781967309ffa3e7f798f6d71440d"
_EXPECTED_UNICODE_DESCRIPTOR: dict[str, object] = {
    "snapshot_schema": "machine-time-source-trust-snapshot.v2",
    "snapshot_id": _UNICODE_SNAPSHOT_ID,
    "source_id": "drand-quicknet-mainnet",
    "provider_id": "league-of-entropy",
    "source_class": "distributed-threshold-randomness-beacon",
    "recommended_role": "not_before",
    "protocol_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
    "protocol_wire_version": "drand-http-api-v2-with-chain-info",
    "independence_class": "threshold-bls-beacon",
    "trust_material_kind": "bls_group_public_key",
    "trust_material_encoding": "raw",
    "trust_material_fingerprint_algorithm": "sha256",
    "trust_material_fingerprint": _UNICODE_TRUST_MATERIAL_FINGERPRINT,
    "valid_from": 1,
    "valid_until": _UNICODE_VALID_UNTIL,
    "supersedes_snapshot_id": _UNICODE_SUPERSEDES_SNAPSHOT_ID,
    "supersedes_key_id": _UNICODE_SUPERSEDES_KEY_ID,
    "revocation_status": "revoked",
    "revocation_evidence_digest": _UNICODE_REVOCATION_EVIDENCE_DIGEST,
    "official_evidence_packet_digest": "18719671d29bda67acfc0b4c88799a466342ec0839e17385b05a9530796495d1",
    "official_citation_ids": list(_UNICODE_OFFICIAL_CITATION_IDS),
    "dependency_profile_id": "D-DEP-02",
    "fixture_corpus_id": "FX-DRAND-QUICKNET.v1",
    "verification_policy_id": "deterministic_supplied_proof_verification_no_network.v1",
    "governance_decision_ids": list(_UNICODE_GOVERNANCE_DECISION_IDS),
    "approved_by": _UNICODE_APPROVED_BY,
    "approved_at": 1,
    "operational_use_approved": False,
    "quorum_countable": False,
    "source_reachable_proven": False,
    "proof_verified": False,
}
_EXPECTED_UNICODE_CANONICAL_JSON = (
    '{"approved_at":1,"approved_by":"governor-\\u00fc","dependency_profile_id":"D-DEP-02","fixture_corpus_id":"FX-D'
    'RAND-QUICKNET.v1","governance_decision_ids":["GOV-MT4-01","GOV-MT4-15"],"independence_class":"threshold-bls-be'
    'acon","official_citation_ids":["DRAND-DEVELOPER","DRAND-HTTP-API","DRAND-QUICKNET-ANNOUNCEMENT","DRAND-SPEC"],'
    '"official_evidence_packet_digest":"18719671d29bda67acfc0b4c88799a466342ec0839e17385b05a9530796495d1","operatio'
    'nal_use_approved":false,"proof_verified":false,"protocol_profile_id":"drand-quicknet-signature-and-chain-info-'
    'offline.v1","protocol_wire_version":"drand-http-api-v2-with-chain-info","provider_id":"league-of-entropy","quo'
    'rum_countable":false,"recommended_role":"not_before","revocation_evidence_digest":"5effa12b1a68fe32a2aa34bccc6'
    '32fcfe9c18c66b29b0b056106ef28de7821a1","revocation_status":"revoked","snapshot_id":"\\u00e9\\u00e9\\u00e9'
    '\\u00e9\\u00e9\\u00e9\\u00e9\\u00e9\\ud83d\\ude00","snapshot_schema":"machine-time-source-trust-snapshot.v2","'
    'source_class":"distributed-threshold-randomness-beacon","source_id":"drand-quicknet-mainnet","source_reachable'
    '_proven":false,"supersedes_key_id":"0052b1b3f2daec4e50338f81ab960028e6f07cae5c094793770b0cb29d35a605","superse'
    'des_snapshot_id":"prior-\\u00e9","trust_material_encoding":"raw","trust_material_fingerprint":"9d00bd85a7ccea6'
    '9f029fb91ea4cf13ecd5892b3211c81de78fa278932dd49df","trust_material_fingerprint_algorithm":"sha256","trust_mate'
    'rial_kind":"bls_group_public_key","valid_from":1,"valid_until":9223372036854775807,"verification_policy_id":"d'
    'eterministic_supplied_proof_verification_no_network.v1"}'
)


def _official(raw: bytes = _OFFICIAL) -> str:
    return hashlib.sha256(b"machine-time-source-trust-snapshot.v2/official-evidence-packet\x00" + raw).hexdigest()


def _revocation(raw: bytes = _REVOCATION) -> str:
    return hashlib.sha256(b"machine-time-source-trust-snapshot.v2/revocation-evidence\x00" + raw).hexdigest()


def _wrong_domain(raw: bytes) -> str:
    return hashlib.sha256(b"wrong-domain\x00" + raw).hexdigest()


def _kwargs(**changes: object) -> dict[str, object]:
    raw = changes.pop("trust_material_bytes", b"drand-group-key-bytes")
    official_raw = changes.pop("official_evidence_packet_bytes", _MISSING)
    revocation_raw = changes.pop("revocation_evidence_bytes", _MISSING)
    official_digest = changes.pop("official_evidence_packet_digest", _MISSING)
    revocation_digest = changes.pop("revocation_evidence_digest", _MISSING)
    revocation_status = changes.get("revocation_status", "revocation_evidence_absent")
    if official_raw is _MISSING:
        official_raw = _OFFICIAL
    if revocation_raw is _MISSING:
        revocation_raw = None if revocation_status == "revocation_evidence_absent" else _REVOCATION
    if official_digest is _MISSING:
        official_digest = _official(official_raw) if type(official_raw) is bytes else _official()
    if revocation_digest is _MISSING:
        revocation_digest = None
        if revocation_status != "revocation_evidence_absent":
            revocation_digest = _revocation(revocation_raw) if type(revocation_raw) is bytes else _revocation()
    values: dict[str, object] = {
        "snapshot_schema": module.MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA,
        "snapshot_id": "drand-snapshot-001",
        "source_id": "drand-quicknet-mainnet",
        "provider_id": "league-of-entropy",
        "source_class": "distributed-threshold-randomness-beacon",
        "recommended_role": "not_before",
        "protocol_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
        "protocol_wire_version": "drand-http-api-v2-with-chain-info",
        "independence_class": "threshold-bls-beacon",
        "trust_material_kind": "bls_group_public_key",
        "trust_material_bytes": raw,
        "trust_material_encoding": "raw",
        "trust_material_fingerprint_algorithm": "sha256",
        "trust_material_fingerprint": hashlib.sha256(raw).hexdigest()
        if type(raw) is bytes
        else hashlib.sha256(b"").hexdigest(),
        "valid_from": None,
        "valid_until": None,
        "supersedes_snapshot_id": None,
        "supersedes_key_id": None,
        "revocation_status": revocation_status,
        "revocation_evidence_digest": revocation_digest,
        "official_evidence_packet_digest": official_digest,
        "official_citation_ids": ("DRAND-DEVELOPER",),
        "dependency_profile_id": "D-DEP-02",
        "fixture_corpus_id": "FX-DRAND-QUICKNET.v1",
        "verification_policy_id": "deterministic_supplied_proof_verification_no_network.v1",
        "governance_decision_ids": (),
        "approved_by": None,
        "approved_at": None,
        "operational_use_approved": False,
        "quorum_countable": False,
        "source_reachable_proven": False,
        "proof_verified": False,
        "official_evidence_packet_bytes": official_raw,
        "revocation_evidence_bytes": revocation_raw,
    }
    values.update(changes)
    return values


def _build(**changes: object) -> module.MachineTimeSourceTrustSnapshot:
    return module.build_machine_time_source_trust_snapshot(**_kwargs(**changes))


def _raises(reason: module.MachineTimeSourceTrustSnapshotReason, **changes: object) -> None:
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        _build(**changes)
    assert captured.value.reason is reason


def _linked(snapshot: module.MachineTimeSourceTrustSnapshot, *, revocation: bool = False) -> dict[str, bytes]:
    evidence = {"official_evidence_packet_digest": _OFFICIAL}
    if revocation:
        evidence["revocation_evidence_digest"] = _REVOCATION
    return evidence


def _successor(
    predecessor: module.MachineTimeSourceTrustSnapshot,
    *,
    snapshot_id: str,
    trust_material_bytes: bytes,
) -> module.MachineTimeSourceTrustSnapshot:
    return _build(
        snapshot_id=snapshot_id,
        trust_material_bytes=trust_material_bytes,
        trust_material_fingerprint=hashlib.sha256(trust_material_bytes).hexdigest(),
        supersedes_snapshot_id=predecessor.snapshot_id,
        supersedes_key_id=predecessor.trust_material_fingerprint,
    )


def _closure_registry(
    snapshot: module.MachineTimeSourceTrustSnapshot,
) -> dict[int, tuple[object, ...]]:
    candidates: list[dict[int, tuple[object, ...]]] = []
    visited: set[int] = set()

    def visit(value: object) -> None:
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if type(value) is dict:
            entry = value.get(id(snapshot))
            if (
                type(entry) is tuple
                and len(entry) == 2
                and type(entry[0]) is weakref.ReferenceType
                and entry[0]() is snapshot
                and type(entry[1]) is tuple
                and len(entry[1]) == len(module._INPUT_FIELD_NAMES) + 3
                and entry[1][0] is entry[0]
            ):
                candidates.append(value)
            return
        if inspect.isfunction(value) and value.__closure__ is not None:
            for cell in value.__closure__:
                try:
                    visit(cell.cell_contents)
                except ValueError:
                    continue

    visit(module._proven_snapshot_state)
    assert len(candidates) == 1
    return candidates[0]


def _assert_registry_unchanged(
    registry: dict[int, tuple[object, ...]],
    before: dict[int, tuple[object, ...]],
    anchor_key: int,
) -> None:
    """Prove a failed build or rebuild registered nothing and replaced no surviving entry.

    The key set may only SHRINK: entries belonging to artifacts created by earlier tests can be removed
    at any moment by the real weakref callback once those artifacts are collected, and deferred cyclic
    collection makes that timing unpredictable.  Whole-key-set equality would therefore assert something
    the contract never promised; the invariant that matters is that the registry never GROWS, the anchor
    entry survives, and every surviving entry is still the identical object.
    """
    assert registry.keys() <= before.keys()
    assert anchor_key in registry
    for key, entry in registry.items():
        assert entry is before[key]


def test_exact_public_contract_and_evidence_bound_builder() -> None:
    assert module.__all__ == (
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
    parameters = tuple(inspect.signature(module.build_machine_time_source_trust_snapshot).parameters)
    assert parameters[:32] == module._INPUT_FIELD_NAMES
    assert parameters[-2:] == ("official_evidence_packet_bytes", "revocation_evidence_bytes")
    assert len(parameters) == 34
    assert len(module._FIELD_NAMES) == 33
    assert len(module._INPUT_FIELD_NAMES) == 32
    assert len(module._DESCRIPTOR_FIELD_NAMES) == 31
    assert len(module.MachineTimeSourceTrustSnapshotReason) == 20
    assert len(module._DIGEST_DOMAIN) == 50
    assert tuple(inspect.signature(module.validate_machine_time_source_trust_snapshot_collection).parameters) == (
        "snapshots",
    )
    values = _kwargs()
    values.pop("official_evidence_packet_bytes")
    with pytest.raises(TypeError):
        module.build_machine_time_source_trust_snapshot(**values)
    snapshot = _build()
    assert snapshot.source_id == "drand-quicknet-mainnet"
    assert snapshot.operational_use_approved is False
    assert bool(snapshot) is True


def test_literal_descriptor_canonical_json_and_self_digest_known_answer() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)

    assert descriptor == _EXPECTED_DESCRIPTOR
    assert len(_EXPECTED_DESCRIPTOR) == 31
    assert set(_EXPECTED_DESCRIPTOR) == set(descriptor)
    assert "trust_material_bytes" not in _EXPECTED_DESCRIPTOR
    assert "snapshot_self_digest" not in _EXPECTED_DESCRIPTOR
    assert _EXPECTED_DESCRIPTOR["official_citation_ids"] == ["DRAND-DEVELOPER"]
    assert _EXPECTED_DESCRIPTOR["governance_decision_ids"] == []
    for optional in (
        "valid_from",
        "valid_until",
        "supersedes_snapshot_id",
        "supersedes_key_id",
        "revocation_evidence_digest",
        "approved_by",
        "approved_at",
    ):
        assert optional in _EXPECTED_DESCRIPTOR
        assert _EXPECTED_DESCRIPTOR[optional] is None

    canonical_json = json.dumps(
        _EXPECTED_DESCRIPTOR,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert canonical_json == _EXPECTED_CANONICAL_JSON
    assert len(_EXPECTED_SELF_DIGEST_DOMAIN) == 50
    independently_computed = hashlib.sha256(
        _EXPECTED_SELF_DIGEST_DOMAIN + _EXPECTED_CANONICAL_JSON.encode("utf-8")
    ).hexdigest()
    assert independently_computed == _EXPECTED_SELF_DIGEST
    assert snapshot.snapshot_self_digest == _EXPECTED_SELF_DIGEST
    assert module.machine_time_source_trust_snapshot_self_digest(snapshot) == _EXPECTED_SELF_DIGEST


def test_literal_non_ascii_descriptor_canonical_json_and_self_digest_known_answer() -> None:
    snapshot = _build(
        snapshot_id=_UNICODE_SNAPSHOT_ID,
        trust_material_bytes=_UNICODE_TRUST_MATERIAL,
        valid_from=1,
        valid_until=_UNICODE_VALID_UNTIL,
        supersedes_snapshot_id=_UNICODE_SUPERSEDES_SNAPSHOT_ID,
        supersedes_key_id=_UNICODE_SUPERSEDES_KEY_ID,
        revocation_status="revoked",
        official_citation_ids=_UNICODE_OFFICIAL_CITATION_IDS,
        governance_decision_ids=_UNICODE_GOVERNANCE_DECISION_IDS,
        approved_by=_UNICODE_APPROVED_BY,
        approved_at=1,
    )
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)

    assert descriptor == _EXPECTED_UNICODE_DESCRIPTOR
    assert len(_EXPECTED_UNICODE_DESCRIPTOR) == 31
    assert set(_EXPECTED_UNICODE_DESCRIPTOR) == set(_EXPECTED_DESCRIPTOR)
    assert "trust_material_bytes" not in _EXPECTED_UNICODE_DESCRIPTOR
    assert "snapshot_self_digest" not in _EXPECTED_UNICODE_DESCRIPTOR
    for optional in (
        "valid_from",
        "valid_until",
        "supersedes_snapshot_id",
        "supersedes_key_id",
        "revocation_evidence_digest",
        "approved_by",
        "approved_at",
    ):
        assert _EXPECTED_UNICODE_DESCRIPTOR[optional] is not None
    assert type(descriptor["official_citation_ids"]) is list
    assert type(descriptor["governance_decision_ids"]) is list
    assert descriptor["official_citation_ids"] == list(_UNICODE_OFFICIAL_CITATION_IDS)
    assert descriptor["governance_decision_ids"] == list(_UNICODE_GOVERNANCE_DECISION_IDS)
    assert hashlib.sha256(_UNICODE_TRUST_MATERIAL).hexdigest() == _UNICODE_TRUST_MATERIAL_FINGERPRINT

    canonical_json = json.dumps(
        _EXPECTED_UNICODE_DESCRIPTOR,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    assert canonical_json == _EXPECTED_UNICODE_CANONICAL_JSON
    assert _EXPECTED_UNICODE_CANONICAL_JSON.isascii()
    assert "\\u00e9" in _EXPECTED_UNICODE_CANONICAL_JSON
    assert "\\u00fc" in _EXPECTED_UNICODE_CANONICAL_JSON
    assert "\\ud83d\\ude00" in _EXPECTED_UNICODE_CANONICAL_JSON
    assert "é" not in _EXPECTED_UNICODE_CANONICAL_JSON
    assert "ü" not in _EXPECTED_UNICODE_CANONICAL_JSON
    assert "\U0001f600" not in _EXPECTED_UNICODE_CANONICAL_JSON

    assert len(_EXPECTED_SELF_DIGEST_DOMAIN) == 50
    assert _EXPECTED_SELF_DIGEST_DOMAIN.endswith(b"\x00")
    independently_computed = hashlib.sha256(
        _EXPECTED_SELF_DIGEST_DOMAIN + _EXPECTED_UNICODE_CANONICAL_JSON.encode("utf-8")
    ).hexdigest()
    assert independently_computed == _EXPECTED_UNICODE_SELF_DIGEST
    assert _EXPECTED_UNICODE_SELF_DIGEST != _EXPECTED_SELF_DIGEST
    assert snapshot.snapshot_self_digest == _EXPECTED_UNICODE_SELF_DIGEST
    assert module.machine_time_source_trust_snapshot_self_digest(snapshot) == _EXPECTED_UNICODE_SELF_DIGEST

    unescaped_form = json.dumps(
        _EXPECTED_UNICODE_DESCRIPTOR,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert not unescaped_form.isascii()
    unescaped_digest = hashlib.sha256(_EXPECTED_SELF_DIGEST_DOMAIN + unescaped_form.encode("utf-8")).hexdigest()
    assert unescaped_digest != _EXPECTED_UNICODE_SELF_DIGEST


def test_official_evidence_is_required_bounded_and_domain_bound() -> None:
    assert _build().snapshot_id == "drand-snapshot-001"
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH,
        official_evidence_packet_bytes=b"wrong-official",
        official_evidence_packet_digest=_official(),
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH,
        official_evidence_packet_digest=_wrong_domain(_OFFICIAL),
    )
    _raises(module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID, official_evidence_packet_bytes=b"")
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        official_evidence_packet_bytes=b"o" * 65_537,
    )

    class BytesSubclass(bytes):
        pass

    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        official_evidence_packet_bytes=BytesSubclass(_OFFICIAL),
    )


def test_revocation_evidence_presence_matrix_binds_exact_raw_bytes() -> None:
    assert _build(revocation_status="revoked").revocation_status == "revoked"
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revocation_evidence_absent",
        revocation_evidence_digest=_revocation(),
        revocation_evidence_bytes=_REVOCATION,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revoked",
        revocation_evidence_digest=None,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revoked",
        revocation_evidence_bytes=None,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH,
        revocation_status="revoked",
        revocation_evidence_bytes=b"wrong-revocation",
        revocation_evidence_digest=_revocation(),
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH,
        revocation_status="revoked",
        revocation_evidence_digest=_wrong_domain(_REVOCATION),
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revoked",
        revocation_evidence_bytes=b"",
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        revocation_status="revoked",
        revocation_evidence_bytes=b"r" * 65_537,
    )

    class BytesSubclass(bytes):
        pass

    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revoked",
        revocation_evidence_bytes=BytesSubclass(_REVOCATION),
    )


def test_descriptor_reconstruction_preserves_hidden_evidence_anchors_and_input() -> None:
    snapshot = _build(revocation_status="revoked")
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    descriptor_before = copy.deepcopy(descriptor)
    linked = _linked(snapshot, revocation=True)
    linked_before = dict(linked)
    assert type(descriptor) is dict
    assert len(descriptor) == 31
    assert "trust_material_bytes" not in descriptor
    assert "snapshot_self_digest" not in descriptor
    rebuilt = module.reconstruct_machine_time_source_trust_snapshot(
        descriptor,
        trust_material_bytes=b"drand-group-key-bytes",
        carried_snapshot_self_digest=snapshot.snapshot_self_digest,
        linked_evidence=linked,
    )
    assert rebuilt is not snapshot
    assert rebuilt.snapshot_self_digest == snapshot.snapshot_self_digest
    assert descriptor == descriptor_before
    assert linked == linked_before
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence=None,
        )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence={"official_evidence_packet_digest": _OFFICIAL},
        )


@pytest.mark.parametrize("field", _EXPECTED_ROW_FIELD_NAMES)
def test_every_eligible_row_field_is_whole_row_bound(field: str) -> None:
    changed = _kwargs()
    changed[field] = changed[field] + "-changed"
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.build_machine_time_source_trust_snapshot(**changed)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION


@pytest.mark.parametrize(
    "source_id",
    (
        "nist-randomness-beacon-v2-beta",
        "curby-public-beacon",
        "digicert-rfc3161-tsa",
        "opentimestamps-bitcoin",
        "cloudflare-roughtime-beta",
        "deribit-public-get-time",
        "unknown-source",
    ),
)
def test_all_non_drand_sources_and_cross_products_fail_closed(source_id: str) -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION, source_id=source_id)
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION,
        source_id=source_id,
        independence_class="threshold-bls-beacon",
        trust_material_kind="bls_group_public_key",
    )


@pytest.mark.parametrize(
    "field",
    ("operational_use_approved", "quorum_countable", "source_reachable_proven", "proof_verified"),
)
def test_permanent_false_booleans_are_exact_and_precedence_is_stable(field: str) -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.GOVERNANCE_STRUCTURAL_VIOLATION, **{field: True})
    _raises(module.MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID, **{field: "false"})
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.FIELD_TYPE_INVALID,
        snapshot_id=7,
        trust_material_bytes=b"",
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        snapshot_id="x\u2028y",
        trust_material_bytes=b"x" * 65_537,
    )


def test_raw_trust_fingerprint_text_and_evidence_precedence() -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID, trust_material_bytes=b"")
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        trust_material_bytes=b"x" * 65_537,
    )

    class BytesSubclass(bytes):
        pass

    _raises(
        module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID,
        trust_material_bytes=BytesSubclass(b"drand-group-key-bytes"),
    )
    assert _build(snapshot_id="\u00e9" * 64).snapshot_id == "\u00e9" * 64
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, snapshot_id="\u00e9" * 65)
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, snapshot_id="x\u2028y")
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, snapshot_id="x\u2029y")
    _raises(module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_INVALID, trust_material_fingerprint="A" * 64)
    _raises(module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH, trust_material_fingerprint="0" * 64)
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID, official_evidence_packet_digest="A" * 64
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID,
        revocation_status="revoked",
        revocation_evidence_digest="A" * 64,
    )


def test_diagnostic_seal_is_permanent_under_ordinary_attribute_operations() -> None:
    reasons = tuple(module.MachineTimeSourceTrustSnapshotReason)
    assert len(reasons) == 20
    assert module._ERROR_IMMUTABLE_ATTRS == _EXPECTED_ERROR_IMMUTABLE_ATTRS

    for reason in reasons:
        constructed = module.MachineTimeSourceTrustSnapshotError(reason)
        assert constructed.reason is reason
        assert constructed.args == (reason.value,)
        assert str(constructed) == reason.value
        # Authority is external: the instance itself carries no reason state at all.
        assert vars(constructed) == {}

    for wrong in ("wrong_input_type", 0, None, object(), module.MachineTimeSourceTrustSnapshotReason):
        with pytest.raises(TypeError):
            module.MachineTimeSourceTrustSnapshotError(wrong)
    with pytest.raises(TypeError) as captured_type:
        module.MachineTimeSourceTrustSnapshotError("caller-controlled-secret")
    assert "caller-controlled-secret" not in str(captured_type.value)

    first = module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE
    other = module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH
    error = module.MachineTimeSourceTrustSnapshotError(first)
    baseline_args = error.args
    baseline_text = str(error)
    assert baseline_args == (first.value,)
    assert baseline_text == first.value

    def assert_diagnostic_intact() -> None:
        assert error.reason is first
        assert error.args == baseline_args
        assert str(error) == baseline_text
        assert repr(error) == f"MachineTimeSourceTrustSnapshotError({first.value})"

    for name, value in (
        ("_reason", other),
        ("reason", other),
        ("args", ("tampered-diagnostic",)),
        ("_sealed", False),
        ("_sealed", True),
        ("_sealed", None),
    ):
        with pytest.raises(AttributeError):
            setattr(error, name, value)
        assert_diagnostic_intact()

    for name in ("_reason", "reason", "args", "_sealed"):
        with pytest.raises(AttributeError):
            delattr(error, name)
        assert_diagnostic_intact()

    # a failed attempt must never weaken the seal for a later attempt (the reproduced bypass was
    # exactly "delete the marker first, then mutate the diagnostic")
    for _ in range(2):
        with pytest.raises(AttributeError):
            error._sealed = False
        with pytest.raises(AttributeError):
            del error._sealed
        with pytest.raises(AttributeError):
            error._reason = other
        with pytest.raises(AttributeError):
            error.args = ("tampered-diagnostic",)
        assert_diagnostic_intact()
    assert "tampered" not in str(error)
    assert other.value not in str(error)


def test_diagnostic_raised_by_production_is_sealed_and_reason_stays_exact() -> None:
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        _build(trust_material_bytes=b"")
    caught = captured.value
    assert caught.reason is module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID
    assert caught.args == ("trust_material_invalid",)
    assert str(caught) == "trust_material_invalid"

    for name in ("_reason", "reason", "args", "_sealed"):
        with pytest.raises(AttributeError):
            delattr(caught, name)
    with pytest.raises(AttributeError):
        caught._sealed = False
    with pytest.raises(AttributeError):
        caught._reason = module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH

    assert caught.reason is module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID
    assert str(caught) == "trust_material_invalid"
    assert caught.args == ("trust_material_invalid",)
    assert vars(caught) == {}


@pytest.mark.parametrize("surrogate", (chr(0xD800), chr(0xDFFF)))
def test_required_text_surrogates_reject_through_closed_reason(surrogate: str) -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, snapshot_id=surrogate)


def test_optional_and_tuple_text_surrogates_reject_through_closed_reason() -> None:
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID,
        approved_by=chr(0xDC00),
        approved_at=1,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID,
        official_citation_ids=("DRAND-DEVELOPER", chr(0xD800)),
    )


def test_reconstruction_and_rebuild_surrogates_close_without_unicode_error() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    descriptor["snapshot_id"] = "prefix" + chr(0xD800) + "suffix"
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence=_linked(snapshot),
        )
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID

    state = snapshot.__reduce__()[1][0]
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._rebuild_machine_time_source_trust_snapshot(state[:1] + (chr(0xDFFF),) + state[2:])
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID


def test_valid_unicode_scalars_bounds_and_precedence_remain_exact() -> None:
    scalar = chr(0x1F600)
    assert _build(snapshot_id=scalar * 32).snapshot_id == scalar * 32
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, snapshot_id=scalar * 33)
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        snapshot_id=chr(0xD800),
        trust_material_bytes=b"x" * 65_537,
    )


def test_unicode_normalization_is_strict_and_not_broadly_caught() -> None:
    source = inspect.getsource(module)
    assert "except UnicodeEncodeError:" in source
    assert "except Exception" not in source
    assert 'errors="ignore"' not in source
    assert 'errors="replace"' not in source
    assert "surrogatepass" not in source
    assert "surrogateescape" not in source


def test_lifecycle_copy_deepcopy_pickle_and_malformed_hidden_state() -> None:
    snapshot = _build(revocation_status="revoked")
    with pytest.raises(TypeError):
        module.MachineTimeSourceTrustSnapshot()
    with pytest.raises(TypeError):
        type("Child", (module.MachineTimeSourceTrustSnapshot,), {})
    hollow = object.__new__(module.MachineTimeSourceTrustSnapshot)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        bool(hollow)
    duplicate = copy.copy(snapshot)
    deep = copy.deepcopy(snapshot)
    restored = pickle.loads(pickle.dumps(snapshot))  # noqa: S301 - validating local round-trip
    assert duplicate is not snapshot and deep is not snapshot and restored is not snapshot
    assert snapshot != duplicate
    assert restored.__reduce__()[1][0][-2:] == (_OFFICIAL, _REVOCATION)
    with pytest.raises(TypeError):
        hash(snapshot)
    state = snapshot.__reduce__()[1][0]
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module._rebuild_machine_time_source_trust_snapshot(state[:-1])
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._rebuild_machine_time_source_trust_snapshot(state[:-2] + (b"wrong", state[-1]))
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module._rebuild_machine_time_source_trust_snapshot(state[:32] + (object(),) + state[33:])


def test_failed_builds_and_rebuilds_leave_the_closure_registry_unchanged() -> None:
    anchor = _build(revocation_status="revoked")
    registry = _closure_registry(anchor)
    anchor_key = id(anchor)
    before = dict(registry)

    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        _build(trust_material_bytes=b"")
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID
    _assert_registry_unchanged(registry, before, anchor_key)

    state = anchor.__reduce__()[1][0]
    malformed_states = (
        (state[:-1], module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID),
        (
            state[:-2] + (b"wrong", state[-1]),
            module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_MISMATCH,
        ),
        (
            state[: len(module._INPUT_FIELD_NAMES)] + (object(),) + state[len(module._INPUT_FIELD_NAMES) + 1 :],
            module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_INVALID,
        ),
    )
    for malformed_state, reason in malformed_states:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module._rebuild_machine_time_source_trust_snapshot(malformed_state)
        assert captured.value.reason is reason
        _assert_registry_unchanged(registry, before, anchor_key)

    hollow = object.__new__(module.MachineTimeSourceTrustSnapshot)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        bool(hollow)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    _assert_registry_unchanged(registry, before, anchor_key)


def test_registry_removes_only_the_exact_collected_owner() -> None:
    snapshot = _build()
    registry = _closure_registry(snapshot)
    key = id(snapshot)
    registered_ref = registry[key][0]
    assert type(registered_ref) is weakref.ReferenceType
    assert registered_ref() is snapshot

    del snapshot
    gc.collect()

    assert registered_ref() is None
    assert key not in registry


def test_registry_rejects_mismatched_owners_and_stale_callbacks_preserve_replacements() -> None:
    owner = _build()
    registry = _closure_registry(owner)
    owner_key = id(owner)
    owner_entry = registry[owner_key]

    impostor = object.__new__(module.MachineTimeSourceTrustSnapshot)
    impostor_key = id(impostor)
    registry[impostor_key] = (weakref.ref(owner), owner_entry[1])
    try:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            bool(impostor)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    finally:
        registry.pop(impostor_key, None)

    original_ref = owner_entry[0]
    replacement_owner = _build(snapshot_id="replacement-owner")
    replacement_ref = weakref.ref(replacement_owner)
    registry[owner_key] = (replacement_ref, owner_entry[1])
    try:
        del owner
        gc.collect()
        assert original_ref() is None
        assert registry[owner_key][0] is replacement_ref
        assert replacement_ref() is replacement_owner
    finally:
        registry.pop(owner_key, None)


def test_reduce_ex_protocols_rebuild_fresh_valid_artifacts_with_hidden_evidence() -> None:
    snapshot = _build(revocation_status="revoked")
    expected_state = snapshot.__reduce__()[1][0]
    assert pickle.HIGHEST_PROTOCOL >= 5

    for protocol in range(6):
        reducer = snapshot.__reduce_ex__(protocol)
        assert type(reducer) is tuple and len(reducer) == 2
        assert reducer[0] is module._rebuild_machine_time_source_trust_snapshot
        assert type(reducer[1]) is tuple and len(reducer[1]) == 1
        assert reducer[1][0] == expected_state
        assert len(reducer[1][0]) == len(module._FIELD_NAMES) + 2
        assert reducer[1][0][-2:] == (_OFFICIAL, _REVOCATION)

        directly_rebuilt = reducer[0](*reducer[1])
        round_tripped = pickle.loads(pickle.dumps(snapshot, protocol=protocol))  # noqa: S301
        for rebuilt in (directly_rebuilt, round_tripped):
            assert rebuilt is not snapshot
            assert bool(rebuilt) is True
            assert rebuilt.snapshot_self_digest == snapshot.snapshot_self_digest
            assert rebuilt.__reduce__()[1][0][-2:] == (_OFFICIAL, _REVOCATION)


def test_public_consumption_rehashes_hidden_evidence_on_every_surface(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _build()
    monkeypatch.setattr(module, "_OFFICIAL_EVIDENCE_DOMAIN", b"wrong-domain\x00")
    for field in module._FIELD_NAMES:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            getattr(snapshot, field)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    consumers = (
        lambda value: module.machine_time_source_trust_snapshot_commitment_descriptor(value),
        lambda value: module.machine_time_source_trust_snapshot_self_digest(value),
        repr,
        str,
        bool,
        lambda value: value == value,
        lambda value: value != value,
        copy.copy,
        copy.deepcopy,
        pickle.dumps,
        lambda value: module.validate_machine_time_source_trust_snapshot_collection((value,)),
    )
    for consume in consumers:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            consume(snapshot)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT


def test_repr_str_are_redacted_ascii_single_line_and_bounded() -> None:
    snapshot = _build(snapshot_id="x" * 128, revocation_status="revoked")
    rendered = repr(snapshot)
    assert str(snapshot) == rendered
    assert rendered.isascii()
    assert "\n" not in rendered and "\r" not in rendered
    assert len(rendered) <= 512
    assert "x" * 32 not in rendered
    assert b"drand-group-key-bytes" not in rendered.encode()
    assert _OFFICIAL not in rendered.encode() and _REVOCATION not in rendered.encode()
    assert "D-DEP-02" not in rendered


# COLLECTION_TESTS_FOLLOW


def test_descriptor_and_linked_evidence_reject_hostile_keys_before_comparison() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)

    class ExplosiveStr(str):
        compared = False

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            raise AssertionError("caller equality must not run")

        __hash__ = str.__hash__

    class HostileKey:
        compared = False

        def __hash__(self) -> int:
            return hash("snapshot_schema")

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            raise AssertionError("caller equality must not run")

    def reconstruct(candidate: dict[object, object], evidence: object = None) -> None:
        linked = {"official_evidence_packet_digest": _OFFICIAL} if evidence is None else evidence
        module.reconstruct_machine_time_source_trust_snapshot(
            candidate, trust_material_bytes=b"drand-group-key-bytes", linked_evidence=linked
        )

    str_subclass_descriptor = dict(descriptor)
    str_subclass_descriptor[ExplosiveStr("snapshot_schema")] = str_subclass_descriptor.pop("snapshot_schema")
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(str_subclass_descriptor)
    assert ExplosiveStr.compared is False

    hostile_descriptor = dict(descriptor)
    hostile_key = HostileKey()
    hostile_descriptor[hostile_key] = hostile_descriptor.pop("snapshot_schema")
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(hostile_descriptor)
    assert HostileKey.compared is False

    missing_descriptor = dict(descriptor)
    missing_descriptor.pop("snapshot_schema")
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        reconstruct(missing_descriptor)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID
    extra_descriptor = dict(descriptor)
    extra_descriptor["extra"] = "x"
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        reconstruct(extra_descriptor)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID

    evidence_subclass_key = {ExplosiveStr("official_evidence_packet_digest"): _OFFICIAL}
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(descriptor, evidence_subclass_key)
    assert ExplosiveStr.compared is False
    hostile_evidence_key = HostileKey()
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(descriptor, {hostile_evidence_key: _OFFICIAL})
    assert HostileKey.compared is False
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(descriptor, {})
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(descriptor, {"official_evidence_packet_digest": _OFFICIAL, "extra": b"x"})

    class BytesSubclass(bytes):
        pass

    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        reconstruct(descriptor, {"official_evidence_packet_digest": BytesSubclass(_OFFICIAL)})


def test_collection_has_no_policy_switch_and_enforces_exact_bound() -> None:
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.validate_machine_time_source_trust_snapshot_collection([])  # type: ignore[arg-type]
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE
    with pytest.raises(TypeError):
        module.validate_machine_time_source_trust_snapshot_collection((), require_single_active_per_profile_key=False)  # type: ignore[call-arg]
    accepted = tuple(
        _build(
            snapshot_id=f"drand-{index:03d}",
            trust_material_bytes=f"raw-{index}".encode(),
            trust_material_fingerprint=hashlib.sha256(f"raw-{index}".encode()).hexdigest(),
        )
        for index in range(256)
    )
    assert module.validate_machine_time_source_trust_snapshot_collection(accepted) == accepted
    rejected = accepted + (
        _build(
            snapshot_id="drand-257",
            trust_material_bytes=b"raw-257",
            trust_material_fingerprint=hashlib.sha256(b"raw-257").hexdigest(),
        ),
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.validate_machine_time_source_trust_snapshot_collection(rejected)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION


def test_collection_empty_singleton_and_corrupt_singleton_semantics() -> None:
    empty: tuple[module.MachineTimeSourceTrustSnapshot, ...] = ()
    assert module.validate_machine_time_source_trust_snapshot_collection(empty) is empty

    snapshot = _build()
    singleton = (snapshot,)
    result = module.validate_machine_time_source_trust_snapshot_collection(singleton)
    assert result is singleton
    assert result[0] is snapshot
    assert snapshot.operational_use_approved is False
    assert snapshot.quorum_countable is False
    assert snapshot.source_reachable_proven is False
    assert snapshot.proof_verified is False

    registry = _closure_registry(snapshot)
    key = id(snapshot)
    valid_entry = registry[key]
    registry[key] = (valid_entry[0], valid_entry[1][:-1])
    try:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module.validate_machine_time_source_trust_snapshot_collection(singleton)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    finally:
        registry[key] = valid_entry


def test_collection_rejects_duplicate_targets_forks_cycles_and_bad_f18() -> None:
    first = _build(
        snapshot_id="first",
        trust_material_bytes=b"first",
        trust_material_fingerprint=hashlib.sha256(b"first").hexdigest(),
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((first, first))
    orphan = _build(
        snapshot_id="orphan",
        trust_material_bytes=b"orphan",
        trust_material_fingerprint=hashlib.sha256(b"orphan").hexdigest(),
        supersedes_snapshot_id="missing",
        supersedes_key_id=hashlib.sha256(b"missing").hexdigest(),
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((orphan,))
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID,
        supersedes_snapshot_id="drand-snapshot-001",
        supersedes_key_id=hashlib.sha256(b"drand-group-key-bytes").hexdigest(),
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID,
        supersedes_snapshot_id="predecessor",
        supersedes_key_id=None,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID,
        supersedes_snapshot_id="predecessor",
        supersedes_key_id="A" * 64,
    )
    wrong_f18 = _build(
        snapshot_id="wrong-f18",
        trust_material_bytes=b"wrong-f18",
        trust_material_fingerprint=hashlib.sha256(b"wrong-f18").hexdigest(),
        supersedes_snapshot_id=first.snapshot_id,
        supersedes_key_id=hashlib.sha256(b"not-first").hexdigest(),
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((first, wrong_f18))

    fork_left = _successor(first, snapshot_id="fork-left", trust_material_bytes=b"fork-left")
    fork_right = _successor(first, snapshot_id="fork-right", trust_material_bytes=b"fork-right")
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((first, fork_left, fork_right))

    a_fingerprint = hashlib.sha256(b"cycle-a").hexdigest()
    b_fingerprint = hashlib.sha256(b"cycle-b").hexdigest()
    cycle_a = _build(
        snapshot_id="cycle-a",
        trust_material_bytes=b"cycle-a",
        trust_material_fingerprint=a_fingerprint,
        supersedes_snapshot_id="cycle-b",
        supersedes_key_id=b_fingerprint,
    )
    cycle_b = _build(
        snapshot_id="cycle-b",
        trust_material_bytes=b"cycle-b",
        trust_material_fingerprint=b_fingerprint,
        supersedes_snapshot_id="cycle-a",
        supersedes_key_id=a_fingerprint,
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((cycle_a, cycle_b))

    c_fingerprint = hashlib.sha256(b"cycle-c").hexdigest()
    long_a = _build(
        snapshot_id="long-a",
        trust_material_bytes=b"cycle-a",
        trust_material_fingerprint=a_fingerprint,
        supersedes_snapshot_id="long-b",
        supersedes_key_id=b_fingerprint,
    )
    long_b = _build(
        snapshot_id="long-b",
        trust_material_bytes=b"cycle-b",
        trust_material_fingerprint=b_fingerprint,
        supersedes_snapshot_id="long-c",
        supersedes_key_id=c_fingerprint,
    )
    long_c = _build(
        snapshot_id="long-c",
        trust_material_bytes=b"cycle-c",
        trust_material_fingerprint=c_fingerprint,
        supersedes_snapshot_id="long-a",
        supersedes_key_id=a_fingerprint,
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection((long_a, long_b, long_c))


def test_nested_missing_targets_close_identically_for_all_tuple_orders() -> None:
    nested_b_raw = b"nested-b"
    nested_b = _build(
        snapshot_id="nested-b",
        trust_material_bytes=nested_b_raw,
        trust_material_fingerprint=hashlib.sha256(nested_b_raw).hexdigest(),
        supersedes_snapshot_id="missing",
        supersedes_key_id=hashlib.sha256(b"missing").hexdigest(),
    )
    nested_c = _successor(nested_b, snapshot_id="nested-c", trust_material_bytes=b"nested-c")
    nested_d = _successor(nested_c, snapshot_id="nested-d", trust_material_bytes=b"nested-d")

    cases = (
        (nested_b,),
        (nested_b, nested_c),
        (nested_c, nested_b),
        (nested_b, nested_c, nested_d),
        (nested_d, nested_c, nested_b),
        (nested_c, nested_b, nested_d),
    )
    for snapshots in cases:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module.validate_machine_time_source_trust_snapshot_collection(snapshots)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION


def test_collection_uses_f14_not_f18_as_current_active_key() -> None:
    predecessor = _build(
        snapshot_id="predecessor",
        trust_material_bytes=b"predecessor",
        trust_material_fingerprint=hashlib.sha256(b"predecessor").hexdigest(),
    )
    successor = _successor(predecessor, snapshot_id="successor", trust_material_bytes=b"current")
    duplicate_active = _build(
        snapshot_id="duplicate-active",
        trust_material_bytes=b"current",
        trust_material_fingerprint=hashlib.sha256(b"current").hexdigest(),
    )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.validate_machine_time_source_trust_snapshot_collection((predecessor, successor, duplicate_active))
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION


def _captured_reason(call: object) -> module.MachineTimeSourceTrustSnapshotReason:
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        call()
    return captured.value.reason


def test_every_retained_closed_reason_is_behaviorally_reachable() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    observed = {
        _captured_reason(lambda: module.machine_time_source_trust_snapshot_self_digest(object())),
        _captured_reason(
            lambda: module.reconstruct_machine_time_source_trust_snapshot(
                {}, trust_material_bytes=b"drand-group-key-bytes", linked_evidence={}
            )
        ),
        _captured_reason(lambda: _build(snapshot_id=1)),
        _captured_reason(lambda: _build(snapshot_id="")),
        _captured_reason(lambda: _build(snapshot_schema="other")),
        _captured_reason(lambda: _build(source_id="unknown-source")),
        _captured_reason(lambda: _build(trust_material_bytes=b"")),
        _captured_reason(lambda: _build(trust_material_fingerprint="A" * 64)),
        _captured_reason(lambda: _build(trust_material_fingerprint="0" * 64)),
        _captured_reason(lambda: _build(official_evidence_packet_digest="A" * 64)),
        _captured_reason(
            lambda: _build(
                official_evidence_packet_bytes=b"wrong-official",
                official_evidence_packet_digest=_official(),
            )
        ),
        _captured_reason(lambda: _build(valid_from=2, valid_until=1)),
        _captured_reason(lambda: _build(proof_verified=True)),
        _captured_reason(lambda: _build(supersedes_snapshot_id="prior", supersedes_key_id=None)),
        _captured_reason(lambda: _build(trust_material_bytes=b"x" * 65_537)),
        _captured_reason(
            lambda: module.reconstruct_machine_time_source_trust_snapshot(
                descriptor,
                trust_material_bytes=b"drand-group-key-bytes",
                carried_snapshot_self_digest="A" * 64,
                linked_evidence=_linked(snapshot),
            )
        ),
        _captured_reason(
            lambda: module.reconstruct_machine_time_source_trust_snapshot(
                descriptor,
                trust_material_bytes=b"drand-group-key-bytes",
                carried_snapshot_self_digest="0" * 64,
                linked_evidence=_linked(snapshot),
            )
        ),
        _captured_reason(
            lambda: module.reconstruct_machine_time_source_trust_snapshot(
                descriptor, trust_material_bytes=b"drand-group-key-bytes", linked_evidence=None
            )
        ),
        _captured_reason(lambda: module.validate_machine_time_source_trust_snapshot_collection((snapshot, snapshot))),
        _captured_reason(lambda: bool(object.__new__(module.MachineTimeSourceTrustSnapshot))),
    }
    assert observed == set(module.MachineTimeSourceTrustSnapshotReason)


def test_no_product_io_or_prohibited_runtime_import_surface() -> None:
    import ast

    source = inspect.getsource(module)
    parsed = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module.split(".", maxsplit=1)[0])
    prohibited = {
        "asyncio",
        "datetime",
        "http",
        "os",
        "pathlib",
        "random",
        "requests",
        "socket",
        "subprocess",
        "time",
        "urllib",
    }
    assert not imports & prohibited
    assert {"bls", "connector", "readiness", "requests", "socket", "subprocess"}.isdisjoint(module.__dict__)
    called_names = {
        node.func.id for node in ast.walk(parsed) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called_names & {"open", "input", "exec", "eval"}
    assert not called_attributes & {"now", "utcnow", "sleep", "Popen", "run", "request", "urlopen"}


def test_public_mapping_requires_exact_builtin_dict_and_equality_ignores_hostile_operands() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)

    class DictSubclass(dict[str, object]):
        pass

    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            DictSubclass(descriptor),
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence={"official_evidence_packet_digest": _OFFICIAL},
        )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence=DictSubclass({"official_evidence_packet_digest": _OFFICIAL}),
        )

    class HostileOperand:
        inspected = False

        def __eq__(self, other: object) -> bool:
            type(self).inspected = True
            raise AssertionError("comparison operand must not be inspected")

    hostile = HostileOperand()
    assert (snapshot == hostile) is False
    assert (snapshot != hostile) is True
    assert HostileOperand.inspected is False


# ---------------------------------------------------------------------------------------------
# P2-S1-TEST-CAUSALITY-06 — test-owned inventories
# ---------------------------------------------------------------------------------------------


def test_reason_inventory_names_values_and_text_bounds_are_test_owned() -> None:
    observed = tuple((member.name, member.value) for member in module.MachineTimeSourceTrustSnapshotReason)
    assert observed == _EXPECTED_REASONS
    assert len(_EXPECTED_REASONS) == 20
    assert len({name for name, _ in _EXPECTED_REASONS}) == 20
    assert len({value for _, value in _EXPECTED_REASONS}) == 20

    for name, value in _EXPECTED_REASONS:
        member = module.MachineTimeSourceTrustSnapshotReason[name]
        assert member.value == value
        assert type(member) is module.MachineTimeSourceTrustSnapshotReason
        # Each diagnostic stays a bounded closed identifier: never prose, never caller text.
        assert value.isascii()
        assert 0 < len(value) <= _MAX_REASON_VALUE_CHARS
        assert set(value) <= _REASON_VALUE_ALPHABET
        assert value == value.strip()
        error = module.MachineTimeSourceTrustSnapshotError(member)
        assert error.reason is member
        assert error.args == (value,)
        assert str(error) == value
        assert len(str(error)) <= _MAX_REASON_VALUE_CHARS
        assert repr(error) == f"MachineTimeSourceTrustSnapshotError({value})"


def test_eligible_row_inventory_and_values_are_test_owned() -> None:
    assert module._ROW_FIELD_NAMES == _EXPECTED_ROW_FIELD_NAMES
    assert module._ELIGIBLE_ROW == _EXPECTED_ELIGIBLE_ROW
    assert len(_EXPECTED_ROW_FIELD_NAMES) == 13
    assert len(_EXPECTED_ELIGIBLE_ROW) == 13
    assert len(set(_EXPECTED_ROW_FIELD_NAMES)) == 13
    assert set(_EXPECTED_ROW_FIELD_NAMES) <= set(module._INPUT_FIELD_NAMES)

    # Structural-only identifiers must stay inside the whole-row contract; losing either from the
    # inventory would silently stop binding it.
    assert "dependency_profile_id" in _EXPECTED_ROW_FIELD_NAMES
    assert "fixture_corpus_id" in _EXPECTED_ROW_FIELD_NAMES
    assert _EXPECTED_ELIGIBLE_ROW[_EXPECTED_ROW_FIELD_NAMES.index("dependency_profile_id")] == "D-DEP-02"
    assert _EXPECTED_ELIGIBLE_ROW[_EXPECTED_ROW_FIELD_NAMES.index("fixture_corpus_id")] == "FX-DRAND-QUICKNET.v1"

    snapshot = _build()
    assert tuple(getattr(snapshot, name) for name in _EXPECTED_ROW_FIELD_NAMES) == _EXPECTED_ELIGIBLE_ROW
    for name in _EXPECTED_PROTECTED_FALSE_FIELDS:
        assert getattr(snapshot, name) is False


@pytest.mark.parametrize("field", _EXPECTED_ROW_FIELD_NAMES)
def test_test_owned_row_fields_reject_every_independent_substitution(field: str) -> None:
    baseline = _kwargs()[field]
    assert type(baseline) is str
    _raises(module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION, **{field: baseline + "-x"})
    for other in _EXPECTED_ELIGIBLE_ROW:
        if other != baseline:
            _raises(module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION, **{field: other})


@pytest.mark.parametrize("field", _EXPECTED_REQUIRED_TEXT_FIELDS + _EXPECTED_OPTIONAL_TEXT_FIELDS)
def test_every_textual_field_is_unicode_and_bound_checked(field: str) -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, **{field: "x" * 129})
    # 65 non-ASCII BMP scalars stay under the character bound but exceed the byte bound.
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, **{field: "é" * 65})
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, **{field: "x" + chr(0xD800)})
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, **{field: "x\ty"})
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, **{field: " padded"})


def test_optional_text_fields_are_all_covered_and_structurally_optional() -> None:
    # Guards the parametrisation above against silently losing a field.
    assert set(_EXPECTED_REQUIRED_TEXT_FIELDS + _EXPECTED_OPTIONAL_TEXT_FIELDS) <= set(module._INPUT_FIELD_NAMES)
    assert len(_EXPECTED_REQUIRED_TEXT_FIELDS) == 18
    assert len(_EXPECTED_OPTIONAL_TEXT_FIELDS) == 4
    assert not set(_EXPECTED_REQUIRED_TEXT_FIELDS) & set(_EXPECTED_OPTIONAL_TEXT_FIELDS)
    snapshot = _build()
    for field in _EXPECTED_OPTIONAL_TEXT_FIELDS:
        assert getattr(snapshot, field) is None
    for field in _EXPECTED_REQUIRED_TEXT_FIELDS:
        assert type(getattr(snapshot, field)) is str


def test_valid_non_null_supersession_chain_is_accepted_in_every_input_order() -> None:
    root = _build(
        snapshot_id="chain-root",
        trust_material_bytes=b"chain-root",
        trust_material_fingerprint=hashlib.sha256(b"chain-root").hexdigest(),
    )
    middle = _successor(root, snapshot_id="chain-middle", trust_material_bytes=b"chain-middle")
    head = _successor(middle, snapshot_id="chain-head", trust_material_bytes=b"chain-head")

    assert middle.supersedes_snapshot_id == "chain-root"
    assert middle.supersedes_key_id == root.trust_material_fingerprint
    assert head.supersedes_snapshot_id == "chain-middle"
    assert head.supersedes_key_id == middle.trust_material_fingerprint

    for order in itertools.permutations((root, middle, head)):
        assert module.validate_machine_time_source_trust_snapshot_collection(order) is order
    for order in itertools.permutations((root, middle)):
        assert module.validate_machine_time_source_trust_snapshot_collection(order) is order
    assert module.validate_machine_time_source_trust_snapshot_collection((root,)) is not None


def test_distinct_artifacts_sharing_one_snapshot_id_are_rejected() -> None:
    twin_a = _build(
        snapshot_id="twin",
        trust_material_bytes=b"twin-a",
        trust_material_fingerprint=hashlib.sha256(b"twin-a").hexdigest(),
    )
    twin_b = _build(
        snapshot_id="twin",
        trust_material_bytes=b"twin-b",
        trust_material_fingerprint=hashlib.sha256(b"twin-b").hexdigest(),
    )
    # Distinct objects with distinct fingerprints: only snapshot_id collides, so an identity-based
    # duplicate check would accept this pair.
    assert twin_a is not twin_b
    assert twin_a.snapshot_id == twin_b.snapshot_id == "twin"
    assert twin_a.trust_material_fingerprint != twin_b.trust_material_fingerprint
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.validate_machine_time_source_trust_snapshot_collection((twin_a, twin_b))
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.COLLECTION_CANONICALITY_VIOLATION


def test_repr_redacts_every_populated_optional_caller_text() -> None:
    approver_text = "governor-private-approver"
    predecessor_text = "prior-private-snapshot"
    predecessor_key = hashlib.sha256(b"predecessor-key").hexdigest()
    snapshot = _build(
        snapshot_id="private-snapshot-identifier",
        valid_from=1,
        valid_until=2,
        supersedes_snapshot_id=predecessor_text,
        supersedes_key_id=predecessor_key,
        revocation_status="revoked",
        approved_by=approver_text,
        approved_at=1,
        official_citation_ids=_UNICODE_OFFICIAL_CITATION_IDS,
        governance_decision_ids=_UNICODE_GOVERNANCE_DECISION_IDS,
    )
    rendered = repr(snapshot)

    assert str(snapshot) == rendered
    assert rendered.isascii()
    assert "\n" not in rendered and "\r" not in rendered
    assert len(rendered) <= 512
    for private_value in (
        approver_text,
        predecessor_text,
        predecessor_key,
        "private-snapshot-identifier",
        "revoked",
        "D-DEP-02",
        "FX-DRAND-QUICKNET.v1",
        "deterministic_supplied_proof_verification_no_network.v1",
        "DRAND-QUICKNET-ANNOUNCEMENT",
        "GOV-MT4-15",
        _revocation(),
    ):
        assert private_value not in rendered
    assert b"drand-group-key-bytes" not in rendered.encode()
    # The values are retained on the artifact; only the rendering is redacted.
    assert snapshot.approved_by == approver_text
    assert snapshot.supersedes_snapshot_id == predecessor_text


def test_artifact_attributes_cannot_be_set_or_deleted() -> None:
    snapshot = _build(revocation_status="revoked")
    digest_before = snapshot.snapshot_self_digest
    descriptor_before = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)

    for name in module._FIELD_NAMES + ("unknown_attribute", "__class__", "__dict__", "__weakref__"):
        with pytest.raises((AttributeError, TypeError)):
            setattr(snapshot, name, "tampered")
        with pytest.raises((AttributeError, TypeError)):
            delattr(snapshot, name)

    with pytest.raises(TypeError):
        vars(snapshot)
    assert snapshot.snapshot_self_digest == digest_before
    assert module.machine_time_source_trust_snapshot_self_digest(snapshot) == digest_before
    assert module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot) == descriptor_before
    assert repr(snapshot) == str(snapshot)


# ---------------------------------------------------------------------------------------------
# P2-S1-DIAGNOSTIC-REINIT-02 — the sealed reason is the only diagnostic authority
# ---------------------------------------------------------------------------------------------


def test_diagnostic_cannot_be_reinitialized_after_construction() -> None:
    first = module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE
    other = module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH
    error = module.MachineTimeSourceTrustSnapshotError(first)
    baseline_args = error.args
    baseline_text = str(error)
    baseline_repr = repr(error)

    with pytest.raises(AttributeError):
        error.__init__(other)
    with pytest.raises(AttributeError):
        module.MachineTimeSourceTrustSnapshotError.__init__(error, other)
    with pytest.raises(AttributeError):
        error.__init__(first)
    with pytest.raises(AttributeError):
        module.MachineTimeSourceTrustSnapshotError.__init__(error, "caller-controlled-secret")

    assert error.reason is first
    assert error.args == baseline_args == (first.value,)
    assert str(error) == baseline_text == first.value
    assert repr(error) == baseline_repr
    assert other.value not in str(error)
    assert "caller-controlled-secret" not in str(error)
    assert "caller-controlled-secret" not in repr(error)


def test_base_initializers_cannot_move_visible_diagnostic_state() -> None:
    for reason in module.MachineTimeSourceTrustSnapshotReason:
        error = module.MachineTimeSourceTrustSnapshotError(reason)
        # Both base initializers write BaseException's argument slot directly; visible state must be
        # derived from the sealed reason instead, so neither call can move it.
        RuntimeError.__init__(error, "tampered-diagnostic")
        BaseException.__init__(error, "tampered-diagnostic", 2, 3)
        assert error.reason is reason
        assert error.args == (reason.value,)
        assert str(error) == reason.value
        assert repr(error) == f"MachineTimeSourceTrustSnapshotError({reason.value})"
        assert "tampered-diagnostic" not in str(error)
        assert "tampered-diagnostic" not in repr(error)
        assert "tampered-diagnostic" not in "".join(str(item) for item in error.args)


def test_diagnostic_note_channel_admits_no_caller_content() -> None:
    error = module.MachineTimeSourceTrustSnapshotError(
        module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID
    )
    with pytest.raises(AttributeError):
        error.add_note("caller-controlled-note")
    with pytest.raises(AttributeError):
        error.__notes__ = ["caller-controlled-note"]
    with pytest.raises(AttributeError):
        del error.__notes__

    # Even a direct instance-dictionary injection stays invisible: the class data descriptor shadows
    # it, so the value the traceback machinery reads is still absent.
    error.__dict__["__notes__"] = ["caller-controlled-note"]
    assert getattr(error, "__notes__", None) is None
    assert "caller-controlled-note" not in str(error)
    assert "caller-controlled-note" not in repr(error)
    assert error.args == ("trust_material_invalid",)
    assert error.reason is module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID


def test_diagnostic_class_cannot_be_reassigned_or_subclassed() -> None:
    error = module.MachineTimeSourceTrustSnapshotError(module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID)
    with pytest.raises(AttributeError):
        error.__class__ = RuntimeError
    with pytest.raises(AttributeError):
        del error.__class__
    with pytest.raises(AttributeError):
        error.__dict__ = {}
    assert type(error) is module.MachineTimeSourceTrustSnapshotError
    assert error.reason is module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID
    assert str(error) == "supersession_invalid"

    with pytest.raises(TypeError) as captured_subclass:
        type("ErrorChild", (module.MachineTimeSourceTrustSnapshotError,), {})
    assert str(captured_subclass.value) == module._SEALED_ERROR_MESSAGE


def test_diagnostic_remains_ordinary_exception_machinery() -> None:
    # Sealing must not break normal raising, catching or reason inspection.
    with pytest.raises(RuntimeError):
        raise module.MachineTimeSourceTrustSnapshotError(
            module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH
        )
    try:
        raise module.MachineTimeSourceTrustSnapshotError(
            module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH
        )
    except module.MachineTimeSourceTrustSnapshotError as caught:
        assert caught.reason is module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH
        assert isinstance(caught, RuntimeError)
        assert caught.__traceback__ is not None
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError, match="fingerprint_mismatch"):
        raise module.MachineTimeSourceTrustSnapshotError(
            module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH
        )


# ---------------------------------------------------------------------------------------------
# P2-S1-MUTABLE-MAPPING-TOCTOU-03 — one bounded snapshot per caller mapping
# ---------------------------------------------------------------------------------------------


def test_stable_mapping_snapshot_bounds_type_cardinality_and_keys() -> None:
    reason = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    source = {"a": 1}
    taken = module._stable_mapping_snapshot(source, reason)
    assert taken == {"a": 1}
    source["b"] = 2
    assert taken == {"a": 1}

    class DictSubclass(dict):
        pass

    for wrong in (None, [], (), "mapping", 7, DictSubclass({"a": 1})):
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module._stable_mapping_snapshot(wrong, reason)
        assert captured.value.reason is reason

    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._stable_mapping_snapshot({7: "x"}, reason)
    assert captured.value.reason is reason

    assert len(module._stable_mapping_snapshot({f"k{index}": index for index in range(256)}, reason)) == 256
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._stable_mapping_snapshot({f"k{index}": index for index in range(257)}, reason)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED


def test_caller_mapping_mutation_after_consumption_is_invisible(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _build(revocation_status="revoked")
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    linked = _linked(snapshot, revocation=True)
    original = module._iter_source
    mutated: list[int] = []

    dict_items_type = type({}.items())

    def draining(source: object) -> object:
        # Drain the caller view, then mutate that mapping: adding an unknown key and removing a
        # required one would both be rejected if anything reread the caller mapping afterwards.
        # reconstruct consumes the descriptor mapping first, then the linked-evidence mapping.
        consumed = list(original(source))
        if type(source) is not dict_items_type:
            return iter(consumed)
        caller = descriptor if not mutated else linked
        caller["unexpected_key_after_snapshot"] = b"injected"
        caller.pop(consumed[0][0], None)
        mutated.append(len(caller))
        return iter(consumed)

    monkeypatch.setattr(module, "_iter_source", draining)
    rebuilt = module.reconstruct_machine_time_source_trust_snapshot(
        descriptor,
        trust_material_bytes=b"drand-group-key-bytes",
        carried_snapshot_self_digest=snapshot.snapshot_self_digest,
        linked_evidence=linked,
    )
    assert len(mutated) == 2
    assert rebuilt.snapshot_self_digest == snapshot.snapshot_self_digest
    assert "unexpected_key_after_snapshot" in descriptor
    assert "unexpected_key_after_snapshot" in linked


def test_mapping_mutation_during_iteration_closes_without_raw_runtime_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID

    # Control: growing a dict while its iterator is live is a genuine CPython RuntimeError.
    control = {f"key-{index:03d}": index for index in range(8)}
    with pytest.raises(RuntimeError) as raw:
        for index, _ in enumerate(control):
            control[f"added-{index}"] = index
    assert type(raw.value) is RuntimeError
    assert "changed size during iteration" in str(raw.value)

    # The same real failure inside bounded consumption closes through the module's reason instead.
    caller = {f"key-{index:03d}": index for index in range(8)}
    original = module._iter_source

    def grow_after_iterator(source: object) -> object:
        iterator = original(source)
        caller["grown-during-iteration"] = 1
        return iterator

    monkeypatch.setattr(module, "_iter_source", grow_after_iterator)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._stable_mapping_snapshot(caller, reason)
    assert type(captured.value) is module.MachineTimeSourceTrustSnapshotError
    assert captured.value.reason is reason


def test_descriptor_and_evidence_key_set_changes_are_rejected_not_ignored() -> None:
    snapshot = _build(revocation_status="revoked")
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    linked = _linked(snapshot, revocation=True)

    def reconstruct(candidate: dict, evidence: dict) -> module.MachineTimeSourceTrustSnapshot:
        return module.reconstruct_machine_time_source_trust_snapshot(
            candidate, trust_material_bytes=b"drand-group-key-bytes", linked_evidence=evidence
        )

    assert reconstruct(dict(descriptor), dict(linked)).snapshot_self_digest == snapshot.snapshot_self_digest

    inventory = module.MachineTimeSourceTrustSnapshotReason.FIELD_INVENTORY_INVALID
    reconstruction = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    added_field = dict(descriptor)
    added_field["unknown_field"] = "x"
    removed_field = dict(descriptor)
    removed_field.pop("dependency_profile_id")
    added_evidence = dict(linked)
    added_evidence["unknown_evidence"] = b"x"
    removed_revocation = dict(linked)
    removed_revocation.pop("revocation_evidence_digest")
    removed_official = dict(linked)
    removed_official.pop("official_evidence_packet_digest")

    cases = (
        (added_field, dict(linked), inventory),
        (removed_field, dict(linked), inventory),
        (dict(descriptor), added_evidence, reconstruction),
        (dict(descriptor), removed_revocation, reconstruction),
        (dict(descriptor), removed_official, reconstruction),
    )
    for candidate, evidence, reason in cases:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            reconstruct(candidate, evidence)
        # A removed required key must never surface as a raw KeyError.
        assert type(captured.value) is module.MachineTimeSourceTrustSnapshotError
        assert captured.value.reason is reason


def test_oversized_caller_mappings_are_bounded_before_inventory_comparison() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    oversized_descriptor = {f"field-{index:04d}": index for index in range(257)}
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.reconstruct_machine_time_source_trust_snapshot(
            oversized_descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            linked_evidence=_linked(snapshot),
        )
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED

    oversized_evidence = {f"evidence-{index:04d}": b"x" for index in range(257)}
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor, trust_material_bytes=b"drand-group-key-bytes", linked_evidence=oversized_evidence
        )
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED


def test_mapping_consumption_is_capped_even_when_the_caller_grows_without_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Bounded consumption, proven by counting what the caller was actually asked for.

    The hostile source would yield a million entries.  A design that observes a length and then
    copies would traverse all of them; bounded consumption must stop at _MAX_MAPPING_KEYS + 1.
    """
    reason = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    served = []

    def unbounded_source(source: object) -> object:
        def generate():
            for index in range(100_000):
                served.append(index)
                yield (f"grown-{index:07d}", index)

        return generate()

    monkeypatch.setattr(module, "_iter_source", unbounded_source)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._stable_mapping_snapshot({"snapshot_schema": "x"}, reason)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED
    assert len(served) == module._MAX_MAPPING_KEYS + 1 == 257


def test_list_consumption_is_capped_even_when_the_caller_grows_without_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    reason = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    served = []

    def unbounded_source(source: object) -> object:
        def generate():
            for index in range(100_000):
                served.append(index)
                yield f"GOV-MT4-{index:02d}"

        return generate()

    monkeypatch.setattr(module, "_iter_source", unbounded_source)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module._bounded_list_snapshot(["GOV-MT4-01"], reason)
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED
    assert len(served) == module._MAX_TUPLE_LENGTH + 1 == 33


# ---------------------------------------------------------------------------------------------
# P2-PR354-DIAGNOSTIC-CLEVEL-SEAL-BYPASS — authority outside caller-writable instance state
# ---------------------------------------------------------------------------------------------


def _diagnostic_authority() -> dict:
    """Locate the closure-private diagnostic authority store without any module-level accessor."""
    visited: set[int] = set()
    candidates: list[dict] = []

    def visit(value: object) -> None:
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if type(value) is dict:
            candidates.append(value)
            return
        if inspect.isfunction(value) and value.__closure__ is not None:
            for cell in value.__closure__:
                try:
                    visit(cell.cell_contents)
                except ValueError:
                    continue

    visit(module.MachineTimeSourceTrustSnapshotError.__init__)
    assert len(candidates) == 1
    return candidates[0]


def _diagnostic_surfaces() -> tuple:
    return (
        lambda error: error.reason,
        lambda error: error.args,
        str,
        repr,
        lambda error: error.__reduce__(),
    )


def test_diagnostic_authority_is_not_stored_in_instance_state() -> None:
    reason = module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID
    error = module.MachineTimeSourceTrustSnapshotError(reason)

    # Nothing authoritative is reachable through ordinary instance state.
    assert vars(error) == {}
    assert module.MachineTimeSourceTrustSnapshotError.__slots__ == ("__weakref__",)
    authority = _diagnostic_authority()
    assert id(error) in authority
    entry = authority[id(error)]
    assert type(entry) is tuple
    assert len(entry) == module._ERROR_AUTHORITY_ENTRY_LENGTH == 2
    assert type(entry[0]) is weakref.ReferenceType
    assert entry[0]() is error
    assert entry[1] is reason


@pytest.mark.parametrize(
    "attack",
    (
        "object_setattr_reason",
        "object_setattr_private_reason",
        "object_setattr_sealed",
        "object_setattr_args",
        "base_setattr_private_reason",
        "base_setattr_args_name",
        "object_delattr_private_reason",
        "base_delattr_private_reason",
        "dict_injection",
        "dict_clear",
        "base_args_descriptor",
        "base_init_caller_text",
        "runtime_init_caller_text",
    ),
)
def test_raw_slot_wrappers_cannot_move_supported_diagnostic_state(attack: str) -> None:
    first = module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE
    other = module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH
    error = module.MachineTimeSourceTrustSnapshotError(first)
    caller_text = "caller-controlled-diagnostic-text"

    attacks = {
        "object_setattr_reason": lambda: object.__setattr__(error, "reason", other),
        "object_setattr_private_reason": lambda: object.__setattr__(error, "_reason", other),
        "object_setattr_sealed": lambda: object.__setattr__(error, "_sealed", False),
        "object_setattr_args": lambda: object.__setattr__(error, "args", (caller_text,)),
        "base_setattr_private_reason": lambda: BaseException.__setattr__(error, "_reason", other),
        "base_setattr_args_name": lambda: BaseException.__setattr__(error, "_sealed", None),
        "object_delattr_private_reason": lambda: object.__delattr__(error, "_reason"),
        "base_delattr_private_reason": lambda: BaseException.__delattr__(error, "_reason"),
        "dict_injection": lambda: error.__dict__.update({"_reason": other, "_sealed": False, "args": (caller_text,)}),
        "dict_clear": lambda: error.__dict__.clear(),
        "base_args_descriptor": lambda: BaseException.args.__set__(error, (caller_text, 2)),
        "base_init_caller_text": lambda: BaseException.__init__(error, caller_text),
        "runtime_init_caller_text": lambda: RuntimeError.__init__(error, caller_text),
    }

    # Some wrappers legitimately succeed (they write the instance dictionary or BaseException's own
    # argument slot); others raise.  Either way, no supported surface may move.
    try:
        attacks[attack]()
    except (AttributeError, TypeError):
        pass

    assert error.reason is first
    assert error.args == (first.value,)
    assert str(error) == first.value
    assert repr(error) == f"MachineTimeSourceTrustSnapshotError({first.value})"
    assert error.__reduce__() == (module.MachineTimeSourceTrustSnapshotError, (first,))
    for surface in _diagnostic_surfaces():
        assert caller_text not in str(surface(error))
        assert other.value not in str(surface(error))

    # Raising and catching after the attack still carries the sealed reason.
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        raise error
    assert captured.value.reason is first
    assert str(captured.value) == first.value


def test_raw_base_argument_slot_is_the_documented_boundary() -> None:
    reason = module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_MISMATCH
    error = module.MachineTimeSourceTrustSnapshotError(reason)
    caller_text = "caller-controlled-raw-args"
    assert BaseException.args.__get__(error) == (reason.value,)

    BaseException.args.__set__(error, (caller_text,))

    # Raw BaseException internals are writable and Python offers no way to freeze them; that read is
    # the explicitly documented boundary.
    assert BaseException.args.__get__(error) == (caller_text,)
    # Every supported project surface remains sealed, including serialization.
    assert error.args == (reason.value,)
    assert error.reason is reason
    assert str(error) == reason.value
    assert repr(error) == f"MachineTimeSourceTrustSnapshotError({reason.value})"
    assert error.__reduce__() == (module.MachineTimeSourceTrustSnapshotError, (reason,))
    restored = pickle.loads(pickle.dumps(error))  # noqa: S301 - local round-trip of a sealed diagnostic
    assert type(restored) is module.MachineTimeSourceTrustSnapshotError
    assert restored.reason is reason
    assert restored.args == (reason.value,)
    assert caller_text not in str(restored)
    assert caller_text not in repr(restored)
    assert caller_text.encode() not in pickle.dumps(error)


def test_hollow_diagnostic_fails_closed_without_leaking_caller_content() -> None:
    unsealed = module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    hollow = BaseException.__new__(module.MachineTimeSourceTrustSnapshotError)
    assert id(hollow) not in _diagnostic_authority()

    # Deterministic, bounded, no raw AttributeError from any supported surface.
    assert hollow.reason is unsealed
    assert hollow.args == (unsealed.value,)
    assert str(hollow) == unsealed.value
    assert repr(hollow) == f"MachineTimeSourceTrustSnapshotError({unsealed.value})"
    assert hollow.__reduce__() == (module.MachineTimeSourceTrustSnapshotError, (unsealed,))

    caller_text = "injected-hollow-caller-text"
    BaseException.__init__(hollow, caller_text, 2, 3)
    BaseException.args.__set__(hollow, (caller_text,))
    for surface in _diagnostic_surfaces():
        assert caller_text not in str(surface(hollow))
    assert hollow.reason is unsealed
    assert hollow.args == (unsealed.value,)
    assert str(hollow) == unsealed.value

    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        raise hollow
    assert captured.value.reason is unsealed
    assert caller_text not in str(captured.value)

    # A hollow diagnostic can still be sealed exactly once by ordinary construction.
    hollow.__init__(module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID)
    assert hollow.reason is module.MachineTimeSourceTrustSnapshotReason.SUPERSESSION_INVALID
    with pytest.raises(AttributeError):
        hollow.__init__(module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE)


def test_diagnostic_authority_is_owner_bound_and_lifecycle_bounded() -> None:
    authority = _diagnostic_authority()
    reason = module.MachineTimeSourceTrustSnapshotReason.EVIDENCE_DIGEST_INVALID
    error = module.MachineTimeSourceTrustSnapshotError(reason)
    key = id(error)
    entry = authority[key]

    # Donor substitution: another diagnostic's authority cannot be transplanted onto this identity.
    donor = module.MachineTimeSourceTrustSnapshotError(module.MachineTimeSourceTrustSnapshotReason.SELF_DIGEST_MISMATCH)
    donor_entry = authority[id(donor)]
    authority[key] = donor_entry
    try:
        assert error.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
        assert error.args == ("snapshot_artifact_inconsistent",)
    finally:
        authority[key] = entry
    assert error.reason is reason

    # Malformed authority entries fail closed rather than raising raw IndexError/TypeError.
    for malformed in ((), (entry[0],), (entry[0], "not-a-reason"), ("not-a-ref", reason), 7, None):
        authority[key] = malformed
        try:
            assert error.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
            assert str(error) == "snapshot_artifact_inconsistent"
        finally:
            authority[key] = entry
    assert error.reason is reason

    # Lifecycle: entries are dropped as the diagnostics die, so the store cannot grow without bound.
    del donor
    gc.collect()
    baseline = len(authority)
    for _ in range(2000):
        transient = module.MachineTimeSourceTrustSnapshotError(
            module.MachineTimeSourceTrustSnapshotReason.WRONG_INPUT_TYPE
        )
        del transient
    gc.collect()
    assert len(authority) <= baseline
    assert key in authority
    assert error.reason is reason

    del error
    gc.collect()
    assert key not in authority


# ---------------------------------------------------------------------------------------------
# P2-S1-REGISTRY-INTEGRITY-04 — malformed entries and owner binding
# ---------------------------------------------------------------------------------------------


def _registry_dependent_surfaces() -> tuple:
    return (
        bool,
        repr,
        str,
        lambda value: value.snapshot_id,
        lambda value: value.snapshot_self_digest,
        module.machine_time_source_trust_snapshot_self_digest,
        module.machine_time_source_trust_snapshot_commitment_descriptor,
        lambda value: value.__reduce__(),
        lambda value: value == value,
        copy.copy,
        copy.deepcopy,
        pickle.dumps,
        lambda value: module.validate_machine_time_source_trust_snapshot_collection((value,)),
    )


def test_malformed_registry_entries_fail_closed_on_every_surface() -> None:
    anchor = _build(revocation_status="revoked")
    registry = _closure_registry(anchor)
    key = id(anchor)
    valid_entry = registry[key]
    valid_ref, valid_state = valid_entry
    donor = _build(
        snapshot_id="donor-artifact",
        trust_material_bytes=b"donor-artifact",
        trust_material_fingerprint=hashlib.sha256(b"donor-artifact").hexdigest(),
    )
    donor_entry = registry[id(donor)]

    malformed = (
        ("empty_entry", ()),
        ("short_entry", (valid_ref,)),
        ("long_entry", (valid_ref, valid_state, valid_ref)),
        ("non_tuple_entry", "not-an-entry"),
        ("integer_entry", 7),
        ("none_entry", None),
        ("list_entry", [valid_ref, valid_state]),
        ("non_reference_head", ("not-a-weakref", valid_state)),
        ("callable_head", (lambda: anchor, valid_state)),
        ("foreign_reference_head", (weakref.ref(donor), valid_state)),
        ("non_tuple_state", (valid_ref, "not-a-state")),
        ("short_state", (valid_ref, valid_state[:-1])),
        ("long_state", (valid_ref, valid_state + (None,))),
        ("state_without_owner", (valid_ref, valid_state[1:] + (None,))),
        ("foreign_owner_inside_state", (valid_ref, (donor_entry[0],) + valid_state[1:])),
        ("donor_state", (valid_ref, donor_entry[1])),
    )
    for label, entry in malformed:
        registry[key] = entry
        try:
            for surface in _registry_dependent_surfaces():
                with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
                    surface(anchor)
                # No raw IndexError/TypeError may escape a malformed entry.
                assert type(captured.value) is module.MachineTimeSourceTrustSnapshotError, label
                assert (
                    captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
                ), label
        finally:
            registry[key] = valid_entry

    assert anchor.snapshot_id == "drand-snapshot-001"
    assert donor.snapshot_id == "donor-artifact"


def test_coherent_donor_state_cannot_report_another_artifacts_identity() -> None:
    owner = _build(
        snapshot_id="owner-artifact",
        trust_material_bytes=b"owner-artifact",
        trust_material_fingerprint=hashlib.sha256(b"owner-artifact").hexdigest(),
    )
    donor = _build(
        snapshot_id="donor-artifact",
        trust_material_bytes=b"donor-artifact",
        trust_material_fingerprint=hashlib.sha256(b"donor-artifact").hexdigest(),
    )
    registry = _closure_registry(owner)
    owner_key = id(owner)
    owner_entry = registry[owner_key]
    donor_entry = registry[id(donor)]

    # The donated state is entirely valid on its own owner.
    assert donor.snapshot_id == "donor-artifact"
    assert donor_entry[1][0] is donor_entry[0]
    donor_digest = donor.snapshot_self_digest
    donor_fingerprint = donor.trust_material_fingerprint

    registry[owner_key] = (owner_entry[0], donor_entry[1])
    try:
        for surface in _registry_dependent_surfaces():
            with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
                surface(owner)
            assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    finally:
        registry[owner_key] = owner_entry

    assert owner.snapshot_id == "owner-artifact"
    assert owner.trust_material_fingerprint != donor_fingerprint
    assert owner.snapshot_self_digest != donor_digest
    assert donor.snapshot_self_digest == donor_digest


def test_registry_entry_replaced_during_proof_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    owner = _build()
    registry = _closure_registry(owner)
    owner_key = id(owner)
    owner_entry = registry[owner_key]
    original = module._validate_evidence_anchors

    def swapping(values: dict, official: object, revocation: object) -> tuple:
        # Replace the entry with an equal-content but distinct object while the proof is in flight.
        registry[owner_key] = (owner_entry[0], owner_entry[1])
        return original(values, official, revocation)

    monkeypatch.setattr(module, "_validate_evidence_anchors", swapping)
    try:
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            bool(owner)
        assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    finally:
        monkeypatch.undo()
        registry[owner_key] = owner_entry
    assert bool(owner) is True


def test_registered_state_embeds_its_owner_reference() -> None:
    snapshot = _build()
    registry = _closure_registry(snapshot)
    entry = registry[id(snapshot)]
    assert type(entry) is tuple
    assert len(entry) == 2
    assert type(entry[0]) is weakref.ReferenceType
    assert entry[0]() is snapshot
    assert type(entry[1]) is tuple
    assert len(entry[1]) == len(module._INPUT_FIELD_NAMES) + 3
    assert entry[1][0] is entry[0]
    # The owner reference stays private: it never reaches public state.
    assert entry[0] not in snapshot.__reduce__()[1][0]
    assert len(snapshot.__reduce__()[1][0]) == len(module._FIELD_NAMES) + 2


# ---------------------------------------------------------------------------------------------
# P2-S1-BOUND-ORDER-05 — cheap bounds precede expensive work
# ---------------------------------------------------------------------------------------------


def test_text_character_bound_is_checked_before_utf8_encoding() -> None:
    # Oversized AND unencodable: the character bound must win, which is only possible when the
    # count is checked before the encode is attempted.
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, snapshot_id=chr(0xD800) * 4096)
    # A short unencodable string still closes through the unicode reason (historical closure).
    _raises(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, snapshot_id=chr(0xD800))

    assert module._check_text_bound("x" * 128) is None
    for oversized, reason in (
        ("x" * 129, module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED),
        (chr(0xD800) * 129, module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED),
        ("é" * 65, module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED),
        (chr(0xD800), module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID),
    ):
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module._check_text_bound(oversized)
        assert captured.value.reason is reason


def test_tuple_bounds_precede_canonical_scanning_and_sorting() -> None:
    # Unsorted AND oversized item: the cheap per-item character bound must win over canonicality.
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, official_citation_ids=("Z" * 200, "A"))
    # Cardinality is bounded before any sorting work happens.
    oversized = tuple(f"DRAND-{index:04d}" for index in range(33))[::-1]
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, official_citation_ids=oversized)
    # Ordinary unsorted tuples still close on canonicality, so the bound did not swallow that path.
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID,
        official_citation_ids=("DRAND-SPEC", "DRAND-DEVELOPER"),
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        governance_decision_ids=tuple(f"GOV-MT4-{index:02d}" for index in range(1, 34)),
    )


def test_reconstruction_bounds_caller_lists_before_any_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    descriptor["governance_decision_ids"] = ["GOV-MT4-01"] * 33

    def explode(values: dict) -> tuple:
        raise AssertionError("validation must not run on an oversized caller list")

    monkeypatch.setattr(module, "_validate_values", explode)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor, trust_material_bytes=b"drand-group-key-bytes", linked_evidence=_linked(snapshot)
        )
    assert captured.value.reason is module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED


def test_trust_material_bound_precedes_fingerprint_hashing() -> None:
    _raises(module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, trust_material_bytes=b"x" * 65_537)
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        official_evidence_packet_bytes=b"o" * 65_537,
    )
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        revocation_status="revoked",
        revocation_evidence_bytes=b"r" * 65_537,
    )
    # Oversized trust material is rejected even when the fingerprint field is itself malformed,
    # proving the size bound precedes fingerprint work.
    _raises(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED,
        trust_material_bytes=b"x" * 65_537,
        trust_material_fingerprint="A" * 64,
    )


# ---------------------------------------------------------------------------------------------
# P2-S1-PY38-COMPAT-07 — no Python 3.10+ only runtime API
# ---------------------------------------------------------------------------------------------


def test_module_uses_no_python_310_only_zip_strict() -> None:
    import ast

    source = inspect.getsource(module)
    assert "strict=True" not in source
    assert "strict =" not in source
    parsed = ast.parse(source)
    zip_calls = 0
    for node in ast.walk(parsed):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "zip":
            zip_calls += 1
            assert [keyword.arg for keyword in node.keywords] == []
    assert zip_calls >= 1
    # The module must also still parse under the declared 3.8 floor.
    assert ast.parse(source, feature_version=(3, 8)) is not None


def test_exact_length_pairing_helper_is_fail_closed() -> None:
    reconstruction = module.MachineTimeSourceTrustSnapshotReason.RECONSTRUCTION_INPUT_INVALID
    inconsistent = module.MachineTimeSourceTrustSnapshotReason.SNAPSHOT_ARTIFACT_INCONSISTENT
    assert module._paired_values(("a", "b"), (1, 2), reconstruction) == {"a": 1, "b": 2}
    assert module._paired_values((), (), reconstruction) == {}
    for names, values, reason in (
        (("a", "b"), (1,), reconstruction),
        (("a",), (1, 2), inconsistent),
        ((), (1,), inconsistent),
    ):
        with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
            module._paired_values(names, values, reason)
        assert captured.value.reason is reason


def test_pairing_dependent_surfaces_retain_exact_semantics() -> None:
    snapshot = _build(revocation_status="revoked")
    state = snapshot.__reduce__()[1][0]
    assert len(state) == len(module._FIELD_NAMES) + 2

    for index, name in enumerate(module._FIELD_NAMES):
        assert getattr(snapshot, name) == state[index]

    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    assert tuple(sorted(descriptor)) == tuple(sorted(module._DESCRIPTOR_FIELD_NAMES))
    assert descriptor["snapshot_id"] == snapshot.snapshot_id

    rendered = repr(snapshot)
    assert rendered.startswith("MachineTimeSourceTrustSnapshot(")
    assert rendered.endswith(f"self_digest={snapshot.snapshot_self_digest})")

    rebuilt = module._rebuild_machine_time_source_trust_snapshot(state)
    assert rebuilt is not snapshot
    assert rebuilt.snapshot_self_digest == snapshot.snapshot_self_digest
    assert rebuilt.__reduce__()[1][0] == state

    assert module.validate_machine_time_source_trust_snapshot_collection((snapshot,)) == (snapshot,)
    assert module.machine_time_source_trust_snapshot_self_digest(snapshot) == snapshot.snapshot_self_digest
