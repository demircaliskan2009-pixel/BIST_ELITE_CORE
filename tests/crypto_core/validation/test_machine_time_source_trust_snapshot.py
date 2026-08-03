import copy
import hashlib
import inspect
import pickle

import pytest

from crypto_core.validation import machine_time_source_trust_snapshot as module


def _official(raw: bytes = b"official-evidence") -> str:
    return hashlib.sha256(b"machine-time-source-trust-snapshot.v2/official-evidence-packet\x00" + raw).hexdigest()


def _kwargs(**changes: object) -> dict[str, object]:
    raw = changes.pop("trust_material_bytes", b"drand-group-key-bytes")
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
        "trust_material_fingerprint": hashlib.sha256(raw).hexdigest(),
        "valid_from": None,
        "valid_until": None,
        "supersedes_snapshot_id": None,
        "supersedes_key_id": None,
        "revocation_status": "revocation_evidence_absent",
        "revocation_evidence_digest": None,
        "official_evidence_packet_digest": _official(),
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
    }
    values.update(changes)
    return values


def _build(**changes: object) -> module.MachineTimeSourceTrustSnapshot:
    return module.build_machine_time_source_trust_snapshot(**_kwargs(**changes))


def _raises_reason(reason: module.MachineTimeSourceTrustSnapshotReason, **changes: object) -> None:
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError) as captured:
        _build(**changes)
    assert captured.value.reason is reason


def test_exact_public_contract_and_eligible_snapshot() -> None:
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
    assert len(inspect.signature(module.build_machine_time_source_trust_snapshot).parameters) == 32
    snapshot = _build()
    assert tuple(name for name in module._FIELD_NAMES) == tuple(
        snapshot.__class__.__dict__[name].fget.__name__ and name for name in module._FIELD_NAMES
    )
    assert snapshot.source_id == "drand-quicknet-mainnet"
    assert snapshot.operational_use_approved is False
    assert bool(snapshot) is True


def test_descriptor_digest_and_reconstruction_require_exact_raw_evidence() -> None:
    snapshot = _build()
    descriptor = module.machine_time_source_trust_snapshot_commitment_descriptor(snapshot)
    assert type(descriptor) is dict
    assert len(descriptor) == 31
    assert "trust_material_bytes" not in descriptor
    assert "snapshot_self_digest" not in descriptor
    assert module.machine_time_source_trust_snapshot_self_digest(snapshot) == snapshot.snapshot_self_digest
    rebuilt = module.reconstruct_machine_time_source_trust_snapshot(
        descriptor,
        trust_material_bytes=b"drand-group-key-bytes",
        carried_snapshot_self_digest=snapshot.snapshot_self_digest,
        linked_evidence={"official_evidence_packet_digest": b"official-evidence"},
    )
    assert rebuilt is not snapshot
    assert rebuilt.snapshot_self_digest == snapshot.snapshot_self_digest
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor, trust_material_bytes=b"drand-group-key-bytes", linked_evidence={}
        )
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.reconstruct_machine_time_source_trust_snapshot(
            descriptor,
            trust_material_bytes=b"drand-group-key-bytes",
            carried_snapshot_self_digest="0" * 64,
            linked_evidence={"official_evidence_packet_digest": b"official-evidence"},
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
def test_all_non_drand_sources_fail_closed(source_id: str) -> None:
    _raises_reason(module.MachineTimeSourceTrustSnapshotReason.MT3_CROSS_CONSISTENCY_VIOLATION, source_id=source_id)


def test_cross_product_boolean_bytes_and_text_fail_closed() -> None:
    _raises_reason(module.MachineTimeSourceTrustSnapshotReason.GOVERNANCE_STRUCTURAL_VIOLATION, proof_verified=True)
    _raises_reason(module.MachineTimeSourceTrustSnapshotReason.TRUST_MATERIAL_INVALID, trust_material_bytes=b"")
    _raises_reason(
        module.MachineTimeSourceTrustSnapshotReason.RESOURCE_BOUND_EXCEEDED, trust_material_bytes=b"x" * 65537
    )
    _raises_reason(module.MachineTimeSourceTrustSnapshotReason.CANONICAL_TEXT_INVALID, snapshot_id="x\u2028y")
    _raises_reason(module.MachineTimeSourceTrustSnapshotReason.FINGERPRINT_INVALID, trust_material_fingerprint="A" * 64)


def test_sealed_lifecycle_copy_pickle_identity_and_hash() -> None:
    snapshot = _build()
    with pytest.raises(TypeError):
        module.MachineTimeSourceTrustSnapshot()
    with pytest.raises(TypeError):
        type("Child", (module.MachineTimeSourceTrustSnapshot,), {})
    hollow = object.__new__(module.MachineTimeSourceTrustSnapshot)
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        bool(hollow)
    duplicate = copy.copy(snapshot)
    deep = copy.deepcopy(snapshot)
    restored = pickle.loads(pickle.dumps(snapshot))  # noqa: S301 - explicit local validating round-trip test
    assert duplicate is not snapshot and deep is not snapshot and restored is not snapshot
    assert snapshot != duplicate
    with pytest.raises(TypeError):
        hash(snapshot)


def test_repr_is_redacted_ascii_single_line_and_bounded() -> None:
    snapshot = _build(snapshot_id="x" * 128)
    rendered = repr(snapshot)
    assert str(snapshot) == rendered
    assert rendered.isascii()
    assert "\n" not in rendered and "\r" not in rendered
    assert len(rendered) <= 512
    assert "x" * 32 not in rendered
    assert "drand-group-key-bytes" not in rendered
    assert "D-DEP-02" not in rendered


def test_collection_uses_current_fingerprint_not_predecessor_key_and_has_bound() -> None:
    first = _build(
        snapshot_id="drand-snapshot-a",
        trust_material_bytes=b"a",
        trust_material_fingerprint=hashlib.sha256(b"a").hexdigest(),
    )
    second = _build(
        snapshot_id="drand-snapshot-b",
        trust_material_bytes=b"b",
        trust_material_fingerprint=hashlib.sha256(b"b").hexdigest(),
    )
    assert module.validate_machine_time_source_trust_snapshot_collection(
        (first, second), require_single_active_per_profile_key=True
    ) == (first, second)
    many = tuple(_build(snapshot_id=f"drand-{index:03d}") for index in range(257))
    with pytest.raises(module.MachineTimeSourceTrustSnapshotError):
        module.validate_machine_time_source_trust_snapshot_collection(many, require_single_active_per_profile_key=False)


def test_no_bls_fixture_or_provider_implementation_surface() -> None:
    assert "bls" not in module.__dict__
    assert "fixture" not in "\n".join(module.__all__)
    assert "socket" not in module.__dict__ and "subprocess" not in module.__dict__
