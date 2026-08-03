import copy
import hashlib
import inspect
import pickle

import pytest

from crypto_core.validation import machine_time_source_trust_snapshot as module

_OFFICIAL = b"official-evidence"
_REVOCATION = b"revocation-evidence"
_MISSING = object()


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


@pytest.mark.parametrize("field", module._ROW_FIELD_NAMES)
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
