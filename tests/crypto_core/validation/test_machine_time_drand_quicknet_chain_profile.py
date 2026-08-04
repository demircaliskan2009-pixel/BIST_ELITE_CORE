import copy
import dataclasses
import gc
import hashlib
import inspect
import json
import pickle
import weakref

import pytest

from crypto_core.validation import machine_time_drand_quicknet_chain_profile as module
from crypto_core.validation import machine_time_source_trust_snapshot as s1_module
from crypto_core.validation.machine_time_source_registry import (
    build_approved_machine_time_source_registry,
    build_machine_time_source_registry,
    machine_time_source_registry_to_dict,
)
from crypto_core.validation.machine_time_source_trust_snapshot import (
    MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA,
    MachineTimeSourceTrustSnapshot,
    build_machine_time_source_trust_snapshot,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

_REASON = module.MachineTimeDrandQuicknetChainProfileReason
_ERROR = module.MachineTimeDrandQuicknetChainProfileError

_PUBLIC_KEY_HEX = (
    "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c"
    "8c4b450b6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb"
    "5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae8991ef5ece45a"
)
_PUBLIC_KEY = bytes.fromhex(_PUBLIC_KEY_HEX)
_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_SNAPSHOT_ID = "drand-quicknet-trust-001"
_UNICODE_SNAPSHOT_ID = "drand-" + chr(0xE9) * 4 + chr(0x1F600)
_OFFICIAL_RAW = b"drand-quicknet-official-evidence"
_S1_OFFICIAL_DOMAIN = b"machine-time-source-trust-snapshot.v2/official-evidence-packet\x00"
_CITATION_IDS = ("DRAND-DEVELOPER", "DRAND-HTTP-API", "DRAND-QUICKNET-ANNOUNCEMENT", "DRAND-SPEC")
_DEFERRED_FACTS = (
    "beacon_id",
    "curve_id",
    "public_key_group",
    "signature_group",
    "signature_encoded_length",
)
# The complete S1 eligible row, hand-written here so the S2 mirror is pinned by test-owned literals and
# not only by comparison against the upstream module.
_EXPECTED_SNAPSHOT_ROW_FIELDS = (
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
_EXPECTED_SNAPSHOT_ROW = (
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

# Known-answer vectors.  Every expected value below is a TEST-OWNED literal: the descriptors are
# hand-written and the canonical JSON strings and digests were derived from those literals with stdlib
# json/hashlib only.  No production-private helper (_canonical_descriptor, _canonical_text,
# _derive_from_normalized_chain_info) and no production output is used to establish an expectation.  The
# three upstream digests are the merged public S1/MT-3 values and are cross-checked against their own
# public APIs below.
_EXPECTED_SELF_DIGEST_DOMAIN = b"machine-time-drand-quicknet-chain-profile.v1/self-digest\x00"
_EXPECTED_CHAIN_INFO_DOMAIN = b"machine-time-drand-quicknet-chain-profile.v1/chain-info\x00"
_EXPECTED_PUBLIC_KEY_FINGERPRINT = "96e74fcdd3a118406d3800a4e4935e67450a6befde915d47a0d6a13519cee134"
_EXPECTED_BOUND_SNAPSHOT_SELF_DIGEST = "c1c4fbc8a1f6259fcb527fd082cdde18487cb7dce43aa3f2af7e41cf60539c9d"
_EXPECTED_UNICODE_SNAPSHOT_SELF_DIGEST = "913930a595fe522260d14a619b441f5edf1a707b3968c450336f89ecaae13686"
_EXPECTED_BOUND_REGISTRY_DIGEST = "1808874889aad3f671e481e69da3e725b5119c5dd915e802b66c40b37769dfce"
_EXPECTED_BOUND_ENTRY_DIGEST = "c3dae5eab6e5fb046d30e66f841804c95e2ecffb65efd8e77553ef096be6eb3c"
_EXPECTED_CHAIN_INFO_DIGEST = "8c15669e77d0da7250abf9247322e02a4acd8d2bc65d50578e32031ecc6ac5c1"
_EXPECTED_PROFILE_SELF_DIGEST = "588596a153eee002997cc172a9058ab055015fca5b27ab2ff3043ffac6762fef"
_EXPECTED_UNICODE_PROFILE_SELF_DIGEST = "3793b5a112c7e28919c0888843ee2af8d1adb952535d26bf5d9761e9ff6d3694"
_EXPECTED_UNESCAPED_UNICODE_DIGEST = "e47ddf32def56c0fbc68511cf3cceb8d8a9bc5953519b7cad44b3bcda655d203"

_EXPECTED_CHAIN_INFO: dict[str, object] = {
    "chain_hash": _CHAIN_HASH,
    "public_key": _PUBLIC_KEY_HEX,
    "scheme_id": "bls-unchained-g1-rfc9380",
    "genesis_time_seconds": 1_692_803_367,
    "period_seconds": 3,
}
_EXPECTED_FALSE_FLAGS = (
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


def _expected_descriptor(snapshot_id: str, snapshot_self_digest: str) -> dict[str, object]:
    values: dict[str, object] = {
        "profile_schema": "machine-time-drand-quicknet-chain-profile.v1",
        "profile_id": "machine-time-drand-quicknet-chain-profile-structural.v1",
        "source_id": "drand-quicknet-mainnet",
        "provider_id": "league-of-entropy",
        "chain_hash": _CHAIN_HASH,
        "scheme_id": "bls-unchained-g1-rfc9380",
        "period_seconds": 3,
        "genesis_time_seconds": 1_692_803_367,
        "public_key_encoded_length": 96,
        "public_key_fingerprint": _EXPECTED_PUBLIC_KEY_FINGERPRINT,
        "protocol_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
        "wire_profile_id": "drand-http-api-v2-with-chain-info",
        "dependency_profile_id": "D-DEP-02",
        "fixture_corpus_id": "FX-DRAND-QUICKNET.v1",
        "verification_policy_id": "deterministic_supplied_proof_verification_no_network.v1",
        "official_citation_ids": list(_CITATION_IDS),
        "bound_snapshot_id": snapshot_id,
        "bound_snapshot_self_digest": snapshot_self_digest,
        "bound_registry_digest": _EXPECTED_BOUND_REGISTRY_DIGEST,
        "bound_registry_source_entry_digest": _EXPECTED_BOUND_ENTRY_DIGEST,
        "chain_info_canonical_digest": _EXPECTED_CHAIN_INFO_DIGEST,
        "chain_profile_structurally_bound": True,
    }
    values.update(dict.fromkeys(_EXPECTED_FALSE_FLAGS, False))
    return values


_EXPECTED_DESCRIPTOR = _expected_descriptor(_SNAPSHOT_ID, _EXPECTED_BOUND_SNAPSHOT_SELF_DIGEST)
_EXPECTED_UNICODE_DESCRIPTOR = _expected_descriptor(_UNICODE_SNAPSHOT_ID, _EXPECTED_UNICODE_SNAPSHOT_SELF_DIGEST)
_EXPECTED_CHAIN_INFO_CANONICAL_JSON = (
    '{"chain_hash":"52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971","genesis_time_seconds":169280'
    '3367,"period_seconds":3,"public_key":"83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183c8c4b450b'
    "6a0a6c3ac6a5776a2d1064510d1fec758c921cc22b0e17e63aaf4bcb5ed66304de9cf809bd274ca73bab4af5a6e9c76a4bc09e76eae899"
    '1ef5ece45a","scheme_id":"bls-unchained-g1-rfc9380"}'
)
_EXPECTED_DESCRIPTOR_CANONICAL_JSON = (
    '{"bound_registry_digest":"1808874889aad3f671e481e69da3e725b5119c5dd915e802b66c40b37769dfce","bound_registry_so'
    'urce_entry_digest":"c3dae5eab6e5fb046d30e66f841804c95e2ecffb65efd8e77553ef096be6eb3c","bound_snapshot_id":"dra'
    'nd-quicknet-trust-001","bound_snapshot_self_digest":"c1c4fbc8a1f6259fcb527fd082cdde18487cb7dce43aa3f2af7e41cf6'
    '0539c9d","chain_hash":"52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971","chain_info_canonical'
    '_digest":"8c15669e77d0da7250abf9247322e02a4acd8d2bc65d50578e32031ecc6ac5c1","chain_profile_structurally_bound"'
    ':true,"connector_promoted":false,"cryptographic_backend_selected":false,"dependency_profile_admitted":false,"d'
    'ependency_profile_id":"D-DEP-02","fixture_corpus_id":"FX-DRAND-QUICKNET.v1","fixture_corpus_loaded":false,"fix'
    'ture_corpus_verified":false,"genesis_time_seconds":1692803367,"machine_time_origin_proven":false,"message_enco'
    'ding_profile_selected":false,"official_citation_ids":["DRAND-DEVELOPER","DRAND-HTTP-API","DRAND-QUICKNET-ANNOU'
    'NCEMENT","DRAND-SPEC"],"operational_quorum_ready":false,"operational_use_approved":false,"period_seconds":3,"p'
    'rofile_id":"machine-time-drand-quicknet-chain-profile-structural.v1","profile_schema":"machine-time-drand-quic'
    'knet-chain-profile.v1","proof_verified":false,"protocol_profile_id":"drand-quicknet-signature-and-chain-info-o'
    'ffline.v1","provider_id":"league-of-entropy","provider_operationally_approved":false,"public_key_encoded_lengt'
    'h":96,"public_key_fingerprint":"96e74fcdd3a118406d3800a4e4935e67450a6befde915d47a0d6a13519cee134","quorum_coun'
    'table":false,"randomness_verified":false,"readiness_promoted":false,"scheme_id":"bls-unchained-g1-rfc9380","si'
    'gnature_parsed":false,"signature_verified":false,"source_id":"drand-quicknet-mainnet","source_reachable_proven'
    '":false,"timestamp_origin_proven":false,"verification_policy_id":"deterministic_supplied_proof_verification_no'
    '_network.v1","wire_profile_id":"drand-http-api-v2-with-chain-info"}'
)
_EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON = (
    '{"bound_registry_digest":"1808874889aad3f671e481e69da3e725b5119c5dd915e802b66c40b37769dfce","bound_registry_so'
    'urce_entry_digest":"c3dae5eab6e5fb046d30e66f841804c95e2ecffb65efd8e77553ef096be6eb3c","bound_snapshot_id":"dra'
    'nd-\\u00e9\\u00e9\\u00e9\\u00e9\\ud83d\\ude00","bound_snapshot_self_digest":"913930a595fe522260d14a619b441f5ed'
    'f1a707b3968c450336f89ecaae13686","chain_hash":"52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e97'
    '1","chain_info_canonical_digest":"8c15669e77d0da7250abf9247322e02a4acd8d2bc65d50578e32031ecc6ac5c1","chain_pro'
    'file_structurally_bound":true,"connector_promoted":false,"cryptographic_backend_selected":false,"dependency_pr'
    'ofile_admitted":false,"dependency_profile_id":"D-DEP-02","fixture_corpus_id":"FX-DRAND-QUICKNET.v1","fixture_c'
    'orpus_loaded":false,"fixture_corpus_verified":false,"genesis_time_seconds":1692803367,"machine_time_origin_pro'
    'ven":false,"message_encoding_profile_selected":false,"official_citation_ids":["DRAND-DEVELOPER","DRAND-HTTP-AP'
    'I","DRAND-QUICKNET-ANNOUNCEMENT","DRAND-SPEC"],"operational_quorum_ready":false,"operational_use_approved":fal'
    'se,"period_seconds":3,"profile_id":"machine-time-drand-quicknet-chain-profile-structural.v1","profile_schema":'
    '"machine-time-drand-quicknet-chain-profile.v1","proof_verified":false,"protocol_profile_id":"drand-quicknet-si'
    'gnature-and-chain-info-offline.v1","provider_id":"league-of-entropy","provider_operationally_approved":false,"'
    'public_key_encoded_length":96,"public_key_fingerprint":"96e74fcdd3a118406d3800a4e4935e67450a6befde915d47a0d6a1'
    '3519cee134","quorum_countable":false,"randomness_verified":false,"readiness_promoted":false,"scheme_id":"bls-u'
    'nchained-g1-rfc9380","signature_parsed":false,"signature_verified":false,"source_id":"drand-quicknet-mainnet",'
    '"source_reachable_proven":false,"timestamp_origin_proven":false,"verification_policy_id":"deterministic_suppli'
    'ed_proof_verification_no_network.v1","wire_profile_id":"drand-http-api-v2-with-chain-info"}'
)
_CANONICAL_SETTINGS = {
    "sort_keys": True,
    "separators": (",", ":"),
    "ensure_ascii": True,
    "allow_nan": False,
}


def _official_digest(raw: bytes = _OFFICIAL_RAW) -> str:
    return hashlib.sha256(_S1_OFFICIAL_DOMAIN + raw).hexdigest()


def _snapshot(**changes: object) -> MachineTimeSourceTrustSnapshot:
    material = changes.pop("trust_material_bytes", _PUBLIC_KEY)
    values: dict[str, object] = {
        "snapshot_schema": MACHINE_TIME_SOURCE_TRUST_SNAPSHOT_SCHEMA,
        "snapshot_id": _SNAPSHOT_ID,
        "source_id": "drand-quicknet-mainnet",
        "provider_id": "league-of-entropy",
        "source_class": "distributed-threshold-randomness-beacon",
        "recommended_role": "not_before",
        "protocol_profile_id": "drand-quicknet-signature-and-chain-info-offline.v1",
        "protocol_wire_version": "drand-http-api-v2-with-chain-info",
        "independence_class": "threshold-bls-beacon",
        "trust_material_kind": "bls_group_public_key",
        "trust_material_bytes": material,
        "trust_material_encoding": "raw",
        "trust_material_fingerprint_algorithm": "sha256",
        "trust_material_fingerprint": hashlib.sha256(material).hexdigest(),
        "valid_from": None,
        "valid_until": None,
        "supersedes_snapshot_id": None,
        "supersedes_key_id": None,
        "revocation_status": "revocation_evidence_absent",
        "revocation_evidence_digest": None,
        "official_evidence_packet_digest": _official_digest(),
        "official_citation_ids": _CITATION_IDS,
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
        "official_evidence_packet_bytes": _OFFICIAL_RAW,
        "revocation_evidence_bytes": None,
    }
    values.update(changes)
    return build_machine_time_source_trust_snapshot(**values)


def _chain_info(**changes: object) -> dict[str, object]:
    values = dict(_EXPECTED_CHAIN_INFO)
    values.update(changes)
    return values


_DEFAULT = object()


def _build(**changes: object) -> object:
    snapshot = changes.pop("snapshot", _DEFAULT)
    registry = changes.pop("registry", _DEFAULT)
    chain_info = changes.pop("chain_info", _DEFAULT)
    return module.build_machine_time_drand_quicknet_chain_profile(
        snapshot=_snapshot() if snapshot is _DEFAULT else snapshot,
        registry=build_approved_machine_time_source_registry() if registry is _DEFAULT else registry,
        chain_info=_chain_info(**changes) if chain_info is _DEFAULT else chain_info,
    )


def _raises(reason: object, **changes: object) -> None:
    with pytest.raises(_ERROR) as captured:
        _build(**changes)
    assert captured.value.reason is reason


def _drand_record() -> dict[str, object]:
    payload = machine_time_source_registry_to_dict(build_approved_machine_time_source_registry())
    return next(item for item in payload["sources"] if item["source_id"] == "drand-quicknet-mainnet")


def _record_facts(record: dict[str, object]) -> dict[str, object]:
    return {pair[0]: pair[1] for pair in record["fact_items"]}


def _closure_registry(profile: object) -> dict[int, tuple[object, ...]]:
    candidates: list[dict[int, tuple[object, ...]]] = []
    visited: set[int] = set()

    def visit(value: object) -> None:
        identity = id(value)
        if identity in visited:
            return
        visited.add(identity)
        if type(value) is dict:
            entry = value.get(id(profile))
            if (
                type(entry) is tuple
                and len(entry) == 2
                and type(entry[0]) is weakref.ReferenceType
                and entry[0]() is profile
                and type(entry[1]) is tuple
                and len(entry[1]) == 3
            ):
                candidates.append(value)
            return
        if inspect.isfunction(value) and value.__closure__ is not None:
            for cell in value.__closure__:
                try:
                    visit(cell.cell_contents)
                except ValueError:
                    continue

    visit(module._proven_profile_state)
    assert len(candidates) == 1
    return candidates[0]


def _reduce_state(profile: object) -> tuple[object, ...]:
    return profile.__reduce__()[1][0]


def test_exact_public_api_field_inventory_and_digest_domains() -> None:
    assert module.__all__ == (
        "MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA",
        "MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID",
        "MachineTimeDrandQuicknetChainProfile",
        "MachineTimeDrandQuicknetChainProfileError",
        "MachineTimeDrandQuicknetChainProfileReason",
        "build_machine_time_drand_quicknet_chain_profile",
        "machine_time_drand_quicknet_chain_profile_commitment_descriptor",
        "machine_time_drand_quicknet_chain_profile_self_digest",
    )
    signature = inspect.signature(module.build_machine_time_drand_quicknet_chain_profile)
    assert tuple(signature.parameters) == ("snapshot", "registry", "chain_info")
    assert all(parameter.kind is inspect.Parameter.KEYWORD_ONLY for parameter in signature.parameters.values())
    assert len(module._FIELD_NAMES) == 41
    assert len(module._DESCRIPTOR_FIELD_NAMES) == 40
    assert module._FIELD_NAMES[-1] == "profile_self_digest"
    assert module._DESCRIPTOR_FIELD_NAMES == module._FIELD_NAMES[:-1]
    assert len(set(module._FIELD_NAMES)) == 41
    assert len(_REASON) == 16
    assert len(module._PROFILE_FALSE_FLAGS) == 18
    assert module._PROFILE_FALSE_FLAGS == _EXPECTED_FALSE_FLAGS
    assert module._CHAIN_INFO_FIELD_NAMES == (
        "chain_hash",
        "public_key",
        "scheme_id",
        "genesis_time_seconds",
        "period_seconds",
    )
    assert len(module._CHAIN_INFO_FIELD_NAMES) == 5
    assert module._PROFILE_DIGEST_DOMAIN == _EXPECTED_SELF_DIGEST_DOMAIN
    assert module._CHAIN_INFO_DIGEST_DOMAIN == _EXPECTED_CHAIN_INFO_DOMAIN
    assert len(_EXPECTED_SELF_DIGEST_DOMAIN) == 57
    assert len(_EXPECTED_CHAIN_INFO_DOMAIN) == 56
    assert _EXPECTED_SELF_DIGEST_DOMAIN.endswith(b"\x00")
    assert _EXPECTED_CHAIN_INFO_DOMAIN.endswith(b"\x00")
    assert module.MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_SCHEMA == _EXPECTED_DESCRIPTOR["profile_schema"]
    assert module.MACHINE_TIME_DRAND_QUICKNET_CHAIN_PROFILE_ID == _EXPECTED_DESCRIPTOR["profile_id"]


def test_removed_unsupported_protocol_facts_cannot_reenter_the_contract() -> None:
    assert module._DEFERRED_UNBOUND_PROTOCOL_FACTS == _DEFERRED_FACTS
    profile = _build()
    descriptor = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(profile)
    for name in _DEFERRED_FACTS:
        assert name not in module._FIELD_NAMES, name
        assert name not in module._DESCRIPTOR_FIELD_NAMES, name
        assert name not in module._CHAIN_INFO_FIELD_NAMES, name
        assert name not in descriptor, name
        assert not hasattr(profile, name), name
    assert set(_DEFERRED_FACTS).isdisjoint(module._DESCRIPTOR_FIELD_NAMES)
    for constant in (
        "_BEACON_ID",
        "_CURVE_ID",
        "_PUBLIC_KEY_GROUP",
        "_SIGNATURE_GROUP",
        "_SIGNATURE_ENCODED_LENGTH",
        "_PUBLIC_KEY_ENCODED_LENGTH",
    ):
        assert not hasattr(module, constant), constant
    # the caller cannot smuggle a deferred fact back in through the chain-info mapping
    for name in _DEFERRED_FACTS:
        smuggled = _chain_info()
        smuggled[name] = "quicknet"
        _raises(_REASON.FIELD_INVENTORY_INVALID, chain_info=smuggled)


def test_every_published_external_fact_has_exact_upstream_provenance() -> None:
    snapshot = _snapshot()
    registry = build_approved_machine_time_source_registry()
    profile = _build(snapshot=snapshot, registry=registry)
    payload = machine_time_source_registry_to_dict(registry)
    record = next(item for item in payload["sources"] if item["source_id"] == "drand-quicknet-mainnet")
    facts = _record_facts(record)

    mt3_facts = {
        "chain_hash": (profile.chain_hash, facts["chain_hash"]),
        "scheme_id": (profile.scheme_id, facts["scheme"]),
        "period_seconds": (profile.period_seconds, facts["period_seconds"]),
        "genesis_time_seconds": (profile.genesis_time_seconds, facts["genesis_unix_seconds"]),
        "public_key_encoded_length": (profile.public_key_encoded_length, len(bytes.fromhex(facts["public_key"]))),
    }
    for name, (published, upstream) in mt3_facts.items():
        assert published == upstream, name

    shared_identifiers = {
        "source_id": (profile.source_id, record["source_id"], snapshot.source_id),
        "provider_id": (profile.provider_id, record["provider_id"], snapshot.provider_id),
        "protocol_profile_id": (
            profile.protocol_profile_id,
            record["verification_profile_id"],
            snapshot.protocol_profile_id,
        ),
        "wire_profile_id": (profile.wire_profile_id, record["protocol_version"], snapshot.protocol_wire_version),
    }
    for name, (published, mt3_value, s1_value) in shared_identifiers.items():
        assert published == mt3_value == s1_value, name
    assert tuple(profile.official_citation_ids) == tuple(sorted(record["citation_ids"]))
    assert tuple(profile.official_citation_ids) == snapshot.official_citation_ids

    mt3_digests = {
        "bound_registry_digest": (profile.bound_registry_digest, payload["registry_digest"]),
        "bound_registry_source_entry_digest": (profile.bound_registry_source_entry_digest, record["entry_digest"]),
    }
    for name, (published, upstream) in mt3_digests.items():
        assert published == upstream, name

    s1_fields = {
        "dependency_profile_id": (profile.dependency_profile_id, snapshot.dependency_profile_id),
        "fixture_corpus_id": (profile.fixture_corpus_id, snapshot.fixture_corpus_id),
        "verification_policy_id": (profile.verification_policy_id, snapshot.verification_policy_id),
        "bound_snapshot_id": (profile.bound_snapshot_id, snapshot.snapshot_id),
        "bound_snapshot_self_digest": (profile.bound_snapshot_self_digest, snapshot.snapshot_self_digest),
        "public_key_fingerprint": (profile.public_key_fingerprint, snapshot.trust_material_fingerprint),
    }
    for name, (published, upstream) in s1_fields.items():
        assert published == upstream, name

    module_owned = {"profile_schema", "profile_id", "chain_profile_structurally_bound"}
    derived_from_caller_input = {"chain_info_canonical_digest"}
    partition = (
        set(mt3_facts)
        | set(shared_identifiers)
        | {"official_citation_ids"}
        | set(mt3_digests)
        | set(s1_fields)
        | module_owned
        | derived_from_caller_input
        | set(module._PROFILE_FALSE_FLAGS)
    )
    assert partition == set(module._DESCRIPTOR_FIELD_NAMES)
    assert len(partition) == 40


def test_public_key_encoded_length_is_derived_from_the_bound_registry_key() -> None:
    record = _drand_record()
    derived = len(bytes.fromhex(_record_facts(record)["public_key"]))
    assert derived == 96
    assert _build().public_key_encoded_length == derived
    int_constants = {name: value for name, value in vars(module).items() if type(value) is int and name.upper() == name}
    assert derived not in set(int_constants.values()), int_constants
    assert _EXPECTED_DESCRIPTOR["public_key_encoded_length"] == derived


def test_valid_structural_binding_and_literal_known_answer_vector() -> None:
    snapshot = _snapshot()
    registry = build_approved_machine_time_source_registry()
    profile = _build(snapshot=snapshot, registry=registry)

    assert snapshot.snapshot_self_digest == _EXPECTED_BOUND_SNAPSHOT_SELF_DIGEST
    assert registry.registry_digest == _EXPECTED_BOUND_REGISTRY_DIGEST
    assert _drand_record()["entry_digest"] == _EXPECTED_BOUND_ENTRY_DIGEST
    assert hashlib.sha256(_PUBLIC_KEY).hexdigest() == _EXPECTED_PUBLIC_KEY_FINGERPRINT
    assert len(_PUBLIC_KEY) == 96

    chain_canonical = json.dumps(_EXPECTED_CHAIN_INFO, **_CANONICAL_SETTINGS)
    assert chain_canonical == _EXPECTED_CHAIN_INFO_CANONICAL_JSON
    assert (
        hashlib.sha256(_EXPECTED_CHAIN_INFO_DOMAIN + _EXPECTED_CHAIN_INFO_CANONICAL_JSON.encode("utf-8")).hexdigest()
        == _EXPECTED_CHAIN_INFO_DIGEST
    )

    descriptor = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(profile)
    assert descriptor == _EXPECTED_DESCRIPTOR
    assert len(_EXPECTED_DESCRIPTOR) == 40
    assert "profile_self_digest" not in _EXPECTED_DESCRIPTOR
    assert type(descriptor["official_citation_ids"]) is list
    assert descriptor["official_citation_ids"] == list(_CITATION_IDS)
    assert descriptor["chain_info_canonical_digest"] == _EXPECTED_CHAIN_INFO_DIGEST

    descriptor_canonical = json.dumps(_EXPECTED_DESCRIPTOR, **_CANONICAL_SETTINGS)
    assert descriptor_canonical == _EXPECTED_DESCRIPTOR_CANONICAL_JSON
    assert _EXPECTED_DESCRIPTOR_CANONICAL_JSON.isascii()
    assert (
        hashlib.sha256(_EXPECTED_SELF_DIGEST_DOMAIN + _EXPECTED_DESCRIPTOR_CANONICAL_JSON.encode("utf-8")).hexdigest()
        == _EXPECTED_PROFILE_SELF_DIGEST
    )
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST
    assert module.machine_time_drand_quicknet_chain_profile_self_digest(profile) == _EXPECTED_PROFILE_SELF_DIGEST
    assert profile.chain_profile_structurally_bound is True
    assert bool(profile) is True


def test_literal_non_ascii_descriptor_canonical_json_and_self_digest_known_answer() -> None:
    assert not _UNICODE_SNAPSHOT_ID.isascii()
    assert chr(0xE9) in _UNICODE_SNAPSHOT_ID
    assert chr(0x1F600) in _UNICODE_SNAPSHOT_ID
    assert len(_UNICODE_SNAPSHOT_ID) == 11
    assert len(_UNICODE_SNAPSHOT_ID.encode("utf-8")) == 18

    snapshot = _snapshot(snapshot_id=_UNICODE_SNAPSHOT_ID)
    assert snapshot.snapshot_self_digest == _EXPECTED_UNICODE_SNAPSHOT_SELF_DIGEST
    profile = _build(snapshot=snapshot)
    assert profile.chain_profile_structurally_bound is True
    assert profile.bound_snapshot_id == _UNICODE_SNAPSHOT_ID

    descriptor = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(profile)
    assert descriptor == _EXPECTED_UNICODE_DESCRIPTOR
    assert len(_EXPECTED_UNICODE_DESCRIPTOR) == 40
    assert set(_EXPECTED_UNICODE_DESCRIPTOR) == set(_EXPECTED_DESCRIPTOR)
    assert set(_EXPECTED_UNICODE_DESCRIPTOR) == set(module._DESCRIPTOR_FIELD_NAMES)

    canonical_json = json.dumps(_EXPECTED_UNICODE_DESCRIPTOR, **_CANONICAL_SETTINGS)
    assert canonical_json == _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON
    assert _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON.isascii()
    assert "\\u00e9" in _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON
    assert "\\ud83d\\ude00" in _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON
    assert chr(0xE9) not in _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON
    assert chr(0x1F600) not in _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON

    assert len(_EXPECTED_SELF_DIGEST_DOMAIN) == 57
    assert _EXPECTED_SELF_DIGEST_DOMAIN.endswith(b"\x00")
    independently_computed = hashlib.sha256(
        _EXPECTED_SELF_DIGEST_DOMAIN + _EXPECTED_UNICODE_DESCRIPTOR_CANONICAL_JSON.encode("utf-8")
    ).hexdigest()
    assert independently_computed == _EXPECTED_UNICODE_PROFILE_SELF_DIGEST
    assert _EXPECTED_UNICODE_PROFILE_SELF_DIGEST != _EXPECTED_PROFILE_SELF_DIGEST
    assert profile.profile_self_digest == _EXPECTED_UNICODE_PROFILE_SELF_DIGEST
    assert (
        module.machine_time_drand_quicknet_chain_profile_self_digest(profile) == _EXPECTED_UNICODE_PROFILE_SELF_DIGEST
    )

    unescaped = json.dumps(
        _EXPECTED_UNICODE_DESCRIPTOR,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
    assert not unescaped.isascii()
    unescaped_digest = hashlib.sha256(_EXPECTED_SELF_DIGEST_DOMAIN + unescaped.encode("utf-8")).hexdigest()
    assert unescaped_digest == _EXPECTED_UNESCAPED_UNICODE_DIGEST
    assert unescaped_digest != _EXPECTED_UNICODE_PROFILE_SELF_DIGEST


def test_descriptor_output_is_isolated_and_key_order_of_input_is_free() -> None:
    profile = _build()
    descriptor = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(profile)
    descriptor["chain_hash"] = "tampered"
    descriptor["official_citation_ids"].append("EXTRA")
    assert profile.chain_hash == _CHAIN_HASH
    assert module.machine_time_drand_quicknet_chain_profile_self_digest(profile) == _EXPECTED_PROFILE_SELF_DIGEST

    reordered = {name: _EXPECTED_CHAIN_INFO[name] for name in reversed(module._CHAIN_INFO_FIELD_NAMES)}
    assert tuple(reordered) != module._CHAIN_INFO_FIELD_NAMES
    assert _build(chain_info=reordered).profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST

    caller_owned = _chain_info()
    other = _build(chain_info=caller_owned)
    caller_owned["chain_hash"] = "tampered-after-build"
    assert other.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST


def test_caller_chain_info_is_normalized_exactly_once_per_build(monkeypatch: pytest.MonkeyPatch) -> None:
    caller = _chain_info()
    real = module._validate_and_normalize_chain_info
    caller_reads: list[object] = []

    def counting(candidate: object) -> dict[str, object]:
        normalized = real(candidate)
        if candidate is caller:
            caller_reads.append(candidate)
            # hostile mutation immediately after the first (and only allowed) caller read
            caller["chain_hash"] = "0" * 64
            caller["public_key"] = "00" * 96
        return normalized

    monkeypatch.setattr(module, "_validate_and_normalize_chain_info", counting)
    profile = module.build_machine_time_drand_quicknet_chain_profile(
        snapshot=_snapshot(),
        registry=build_approved_machine_time_source_registry(),
        chain_info=caller,
    )

    assert len(caller_reads) == 1
    assert caller["chain_hash"] == "0" * 64
    assert bool(profile) is True
    assert profile.chain_hash == _CHAIN_HASH
    assert profile.chain_info_canonical_digest == _EXPECTED_CHAIN_INFO_DIGEST
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST

    registry = _closure_registry(profile)
    retained = registry[id(profile)][1][2]
    assert retained is not caller
    assert retained == _EXPECTED_CHAIN_INFO
    assert len(caller_reads) == 1

    caller["scheme_id"] = "mutated-again"
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST


def test_reconstruction_normalizes_the_incoming_mapping_exactly_once(monkeypatch: pytest.MonkeyPatch) -> None:
    profile = _build()
    state = _reduce_state(profile)
    incoming = state[2]
    real = module._validate_and_normalize_chain_info
    incoming_reads: list[object] = []

    def counting(candidate: object) -> dict[str, object]:
        normalized = real(candidate)
        if candidate is incoming:
            incoming_reads.append(candidate)
            incoming["chain_hash"] = "0" * 64
        return normalized

    monkeypatch.setattr(module, "_validate_and_normalize_chain_info", counting)
    rebuilt = module._rebuild_machine_time_drand_quicknet_chain_profile(state)
    assert len(incoming_reads) == 1
    assert rebuilt is not profile
    assert rebuilt.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST
    assert rebuilt.chain_hash == _CHAIN_HASH


@pytest.mark.parametrize("candidate", (object(), None, "snapshot", 7))
def test_wrong_snapshot_type_fails_closed(candidate: object) -> None:
    _raises(_REASON.SNAPSHOT_BINDING_INVALID, snapshot=candidate)


def test_hollow_snapshot_fails_through_the_s1_boundary() -> None:
    hollow = object.__new__(MachineTimeSourceTrustSnapshot)
    _raises(_REASON.SNAPSHOT_BINDING_INVALID, snapshot=hollow)


def test_snapshot_citation_basis_and_material_length_are_bound() -> None:
    _raises(_REASON.SNAPSHOT_BINDING_INVALID, snapshot=_snapshot(official_citation_ids=("DRAND-SPEC",)))
    _raises(
        _REASON.SNAPSHOT_BINDING_INVALID,
        snapshot=_snapshot(official_citation_ids=("DRAND-DEVELOPER", "DRAND-HTTP-API")),
    )
    _raises(_REASON.PUBLIC_KEY_LENGTH_INVALID, snapshot=_snapshot(trust_material_bytes=b"too-short"))
    _raises(_REASON.PUBLIC_KEY_LENGTH_INVALID, snapshot=_snapshot(trust_material_bytes=_PUBLIC_KEY + b"x"))


@pytest.mark.parametrize("candidate", (object(), None, 7))
def test_wrong_registry_type_fails_closed(candidate: object) -> None:
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=candidate)


def test_rejected_and_mutated_registry_fail_closed() -> None:
    rejected = build_machine_time_source_registry(packet={"packet_schema": "not-the-approved-packet"})
    assert rejected.ready is False
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=rejected)

    approved = build_approved_machine_time_source_registry()
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=dataclasses.replace(approved, ready=False))
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=dataclasses.replace(approved, registry_digest="0" * 64))
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=dataclasses.replace(approved, readiness_promoted=True))
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=dataclasses.replace(approved, sources=()))


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("chain_hash", "0" * 64),
        ("chain_hash", _CHAIN_HASH.upper()),
        ("scheme_id", "bls-unchained-on-g2-rfc9380"),
        ("period_seconds", 4),
        ("period_seconds", 30),
        ("genesis_time_seconds", 1_692_803_368),
    ),
)
def test_chain_identity_mismatch_matrix(field: str, value: object) -> None:
    _raises(_REASON.CHAIN_IDENTITY_MISMATCH, **{field: value})


def test_public_key_encoding_length_and_mismatch() -> None:
    _raises(_REASON.PUBLIC_KEY_ENCODING_INVALID, public_key="z" * 192)
    _raises(_REASON.PUBLIC_KEY_ENCODING_INVALID, public_key=_PUBLIC_KEY_HEX.upper())
    _raises(_REASON.PUBLIC_KEY_ENCODING_INVALID, public_key=_PUBLIC_KEY_HEX[:-1])
    _raises(_REASON.PUBLIC_KEY_ENCODING_INVALID, public_key="g" * 192)
    _raises(_REASON.PUBLIC_KEY_LENGTH_INVALID, public_key=_PUBLIC_KEY_HEX[:-2])
    _raises(_REASON.PUBLIC_KEY_LENGTH_INVALID, public_key=_PUBLIC_KEY_HEX + "ab")
    _raises(_REASON.PUBLIC_KEY_MISMATCH, public_key="00" * 96)
    # the supplied encoding must equal the S1 trust material itself, not merely the MT-3 record value
    _raises(_REASON.PUBLIC_KEY_MISMATCH, snapshot=_snapshot(trust_material_bytes=bytes(96)))
    _raises(_REASON.PUBLIC_KEY_MISMATCH, snapshot=_snapshot(trust_material_bytes=b"\x01" * 96))
    flipped = "83cf0f2896adee7eb8b5f01fcad3912212c437e0073e911fb90022d3e760183d" + _PUBLIC_KEY_HEX[64:]
    assert flipped != _PUBLIC_KEY_HEX
    _raises(_REASON.PUBLIC_KEY_MISMATCH, public_key=flipped)


def test_chain_info_inventory_and_hostile_keys_reject_before_comparison() -> None:
    _raises(_REASON.WRONG_INPUT_TYPE, chain_info=[])
    _raises(_REASON.WRONG_INPUT_TYPE, chain_info=None)

    class DictSubclass(dict[str, object]):
        pass

    _raises(_REASON.WRONG_INPUT_TYPE, chain_info=DictSubclass(_chain_info()))

    missing = _chain_info()
    missing.pop("scheme_id")
    _raises(_REASON.FIELD_INVENTORY_INVALID, chain_info=missing)
    extra = _chain_info()
    extra["group_hash"] = "deadbeef"
    _raises(_REASON.FIELD_INVENTORY_INVALID, chain_info=extra)

    class ExplosiveStr(str):
        compared = False

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            raise AssertionError("caller equality must not run")

        __hash__ = str.__hash__

    class HostileKey:
        compared = False

        def __hash__(self) -> int:
            return hash("scheme_id")

        def __eq__(self, other: object) -> bool:
            type(self).compared = True
            raise AssertionError("caller equality must not run")

    subclass_key = _chain_info()
    subclass_key[ExplosiveStr("scheme_id")] = subclass_key.pop("scheme_id")
    _raises(_REASON.FIELD_INVENTORY_INVALID, chain_info=subclass_key)
    assert ExplosiveStr.compared is False

    hostile = _chain_info()
    hostile[HostileKey()] = hostile.pop("scheme_id")
    _raises(_REASON.FIELD_INVENTORY_INVALID, chain_info=hostile)
    assert HostileKey.compared is False


def test_chain_info_value_types_bounds_and_canonical_text() -> None:
    class StrSubclass(str):
        pass

    class IntSubclass(int):
        pass

    _raises(_REASON.FIELD_TYPE_INVALID, scheme_id=StrSubclass("bls-unchained-g1-rfc9380"))
    _raises(_REASON.FIELD_TYPE_INVALID, period_seconds=IntSubclass(3))
    _raises(_REASON.FIELD_TYPE_INVALID, period_seconds=True)
    _raises(_REASON.FIELD_TYPE_INVALID, period_seconds="3")
    _raises(_REASON.FIELD_TYPE_INVALID, genesis_time_seconds=1_692_803_367.0)
    _raises(_REASON.FIELD_TYPE_INVALID, chain_hash=None)

    _raises(_REASON.RESOURCE_BOUND_EXCEEDED, scheme_id="q" * 257)
    _raises(_REASON.RESOURCE_BOUND_EXCEEDED, scheme_id=chr(0xE9) * 129)
    _raises(_REASON.RESOURCE_BOUND_EXCEEDED, period_seconds=0)
    _raises(_REASON.RESOURCE_BOUND_EXCEEDED, period_seconds=-3)
    _raises(_REASON.RESOURCE_BOUND_EXCEEDED, genesis_time_seconds=1 << 63)

    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls" + chr(7) + "scheme")
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls" + chr(127))
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls" + chr(0x2028) + "scheme")
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls" + chr(0x2029) + "scheme")
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id=" bls-unchained-g1-rfc9380")
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls-unchained-g1-rfc9380" + chr(10))
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="bls-unchained-g1-rfc9380" + chr(9))
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id="")
    _raises(_REASON.CANONICAL_TEXT_INVALID, scheme_id=chr(0xD800))
    _raises(_REASON.CANONICAL_TEXT_INVALID, chain_hash="prefix" + chr(0xDFFF) + "suffix")


def test_hidden_bound_state_tampering_closes_every_public_surface() -> None:
    profile = _build()
    registry = _closure_registry(profile)
    key = id(profile)
    valid_entry = registry[key]
    tampered_chain = dict(valid_entry[1][2])
    tampered_chain["chain_hash"] = "0" * 64
    registry[key] = (valid_entry[0], (valid_entry[1][0], valid_entry[1][1], tampered_chain))
    try:
        for consume in (
            lambda value: value.profile_self_digest,
            lambda value: module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(value),
            lambda value: module.machine_time_drand_quicknet_chain_profile_self_digest(value),
            repr,
            str,
            bool,
            lambda value: value == value,
            copy.copy,
            pickle.dumps,
        ):
            with pytest.raises(_ERROR) as captured:
                consume(profile)
            assert captured.value.reason is _REASON.ARTIFACT_INCONSISTENT
    finally:
        registry[key] = valid_entry
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST

    registry[key] = (valid_entry[0], valid_entry[1][:2])
    try:
        with pytest.raises(_ERROR) as captured:
            bool(profile)
        assert captured.value.reason is _REASON.ARTIFACT_INCONSISTENT
    finally:
        registry[key] = valid_entry
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST


def test_sealing_hollow_impostor_equality_and_hash_contract() -> None:
    profile = _build()
    with pytest.raises(TypeError):
        module.MachineTimeDrandQuicknetChainProfile()
    with pytest.raises(TypeError):
        type("Child", (module.MachineTimeDrandQuicknetChainProfile,), {})
    assert module.MachineTimeDrandQuicknetChainProfile.__slots__ == ("__weakref__",)
    assert module.MachineTimeDrandQuicknetChainProfile.__hash__ is None
    with pytest.raises(TypeError):
        hash(profile)

    hollow = object.__new__(module.MachineTimeDrandQuicknetChainProfile)
    for consume in (bool, repr, str, lambda value: value.source_id):
        with pytest.raises(_ERROR) as captured:
            consume(hollow)
        assert captured.value.reason is _REASON.ARTIFACT_INCONSISTENT
    with pytest.raises(_ERROR) as captured:
        module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(object())
    assert captured.value.reason is _REASON.WRONG_INPUT_TYPE
    with pytest.raises(_ERROR) as captured:
        module.machine_time_drand_quicknet_chain_profile_self_digest(object())
    assert captured.value.reason is _REASON.WRONG_INPUT_TYPE

    other = _build()
    assert profile == profile
    assert profile != other
    assert (profile == other) is False

    class HostileOperand:
        inspected = False

        def __eq__(self, other: object) -> bool:
            type(self).inspected = True
            raise AssertionError("comparison operand must not be inspected")

    hostile = HostileOperand()
    assert (profile == hostile) is False
    assert (profile != hostile) is True
    assert HostileOperand.inspected is False


def test_registry_entry_with_a_foreign_weakref_fails_closed() -> None:
    owner = _build()
    registry = _closure_registry(owner)
    impostor = object.__new__(module.MachineTimeDrandQuicknetChainProfile)
    impostor_key = id(impostor)
    baseline = set(registry)
    registry[impostor_key] = (weakref.ref(owner), registry[id(owner)][1])
    try:
        for consume in (bool, repr, lambda value: value.source_id):
            with pytest.raises(_ERROR) as captured:
                consume(impostor)
            assert captured.value.reason is _REASON.ARTIFACT_INCONSISTENT
    finally:
        registry.pop(impostor_key, None)
    assert set(registry) == baseline
    assert bool(owner) is True


def test_dead_owner_entry_is_removed_by_the_production_weakref_callback() -> None:
    profile = _build()
    registry = _closure_registry(profile)
    key = id(profile)
    registered_ref = registry[key][0]
    assert type(registered_ref) is weakref.ReferenceType
    assert registered_ref() is profile
    baseline = set(registry) - {key}

    del profile
    gc.collect()

    assert registered_ref() is None
    assert key not in registry
    # no entry may be added by the cleanup; other live artifacts may legitimately also have been
    # collected between the baseline snapshot and here, so the invariant is "never grows".
    assert set(registry) <= baseline


def test_stale_weakref_callback_cannot_delete_a_replacement_entry() -> None:
    owner = _build()
    registry = _closure_registry(owner)
    owner_key = id(owner)
    owner_entry = registry[owner_key]
    original_ref = owner_entry[0]

    replacement_owner = _build()
    replacement_ref = weakref.ref(replacement_owner)
    registry[owner_key] = (replacement_ref, owner_entry[1])
    try:
        del owner
        gc.collect()
        assert original_ref() is None
        assert owner_key in registry
        assert registry[owner_key][0] is replacement_ref
        assert replacement_ref() is replacement_owner
    finally:
        registry.pop(owner_key, None)
    assert bool(replacement_owner) is True


def test_closure_registry_has_no_cross_test_state_leak() -> None:
    anchor = _build()
    anchor_key = id(anchor)
    registry = _closure_registry(anchor)
    baseline = set(registry)

    transient = _build()
    transient_key = id(transient)
    assert transient_key in registry
    assert set(registry) == baseline | {transient_key}
    del transient
    gc.collect()
    assert transient_key not in registry
    # the registry may only shrink as unrelated artifacts die; it must never grow or lose the anchor
    assert set(registry) <= baseline
    assert anchor_key in registry

    with pytest.raises(_ERROR):
        _build(chain_hash="0" * 64)
    gc.collect()
    assert set(registry) <= baseline
    assert anchor_key in registry
    assert bool(anchor) is True


def test_copy_deepcopy_and_reduce_ex_protocols_rebuild_fresh_valid_identities() -> None:
    profile = _build()
    assert pickle.HIGHEST_PROTOCOL >= 5
    expected_state = _reduce_state(profile)
    assert len(expected_state) == 5
    assert expected_state[3] == tuple([False] * 18)
    assert expected_state[4] == _EXPECTED_PROFILE_SELF_DIGEST
    assert expected_state[2] == _EXPECTED_CHAIN_INFO

    duplicate = copy.copy(profile)
    deep = copy.deepcopy(profile)
    for rebuilt in (duplicate, deep):
        assert rebuilt is not profile
        assert bool(rebuilt) is True
        assert rebuilt.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST

    for protocol in range(6):
        reducer = profile.__reduce_ex__(protocol)
        assert type(reducer) is tuple and len(reducer) == 2
        assert reducer[0] is module._rebuild_machine_time_drand_quicknet_chain_profile
        assert type(reducer[1]) is tuple and len(reducer[1]) == 1
        directly_rebuilt = reducer[0](*reducer[1])
        round_tripped = pickle.loads(pickle.dumps(profile, protocol=protocol))  # noqa: S301
        for rebuilt in (directly_rebuilt, round_tripped):
            assert rebuilt is not profile
            assert bool(rebuilt) is True
            assert rebuilt.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST
            assert rebuilt.chain_profile_structurally_bound is True


def test_reconstruction_reproves_nonclaims_and_the_carried_digest() -> None:
    profile = _build()
    state = _reduce_state(profile)
    rebuild = module._rebuild_machine_time_drand_quicknet_chain_profile

    for malformed, reason in (
        (state[:-1], _REASON.RECONSTRUCTION_INPUT_INVALID),
        (list(state), _REASON.RECONSTRUCTION_INPUT_INVALID),
        (state[:3] + (list(state[3]), state[4]), _REASON.RECONSTRUCTION_INPUT_INVALID),
        (state[:3] + (state[3][:-1], state[4]), _REASON.RECONSTRUCTION_INPUT_INVALID),
        (state[:3] + ((True,) + state[3][1:], state[4]), _REASON.GOVERNANCE_STRUCTURAL_VIOLATION),
        (state[:3] + (state[3][:-1] + (True,), state[4]), _REASON.GOVERNANCE_STRUCTURAL_VIOLATION),
        (state[:3] + ((None,) + state[3][1:], state[4]), _REASON.GOVERNANCE_STRUCTURAL_VIOLATION),
        (state[:4] + ("A" * 64,), _REASON.SELF_DIGEST_INVALID),
        (state[:4] + (None,), _REASON.SELF_DIGEST_INVALID),
        (state[:4] + ("0" * 64,), _REASON.SELF_DIGEST_MISMATCH),
        ((object(), state[1], state[2], state[3], state[4]), _REASON.SNAPSHOT_BINDING_INVALID),
        ((state[0], object(), state[2], state[3], state[4]), _REASON.REGISTRY_BINDING_INVALID),
        ((state[0], state[1], {}, state[3], state[4]), _REASON.FIELD_INVENTORY_INVALID),
    ):
        with pytest.raises(_ERROR) as captured:
            rebuild(malformed)
        assert captured.value.reason is reason

    assert rebuild(state).profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST


def test_failed_build_and_rebuild_leave_the_closure_registry_unchanged() -> None:
    anchor = _build()
    registry = _closure_registry(anchor)
    before = dict(registry)

    def assert_unchanged() -> None:
        assert registry.keys() == before.keys()
        for key, entry in before.items():
            assert registry[key] is entry

    with pytest.raises(_ERROR):
        _build(chain_hash="0" * 64)
    assert_unchanged()
    with pytest.raises(_ERROR):
        _build(snapshot=object())
    assert_unchanged()
    with pytest.raises(_ERROR):
        _build(registry=object())
    assert_unchanged()

    state = _reduce_state(anchor)
    for malformed in (state[:-1], state[:4] + ("0" * 64,), state[:3] + ((True,) + state[3][1:], state[4])):
        with pytest.raises(_ERROR):
            module._rebuild_machine_time_drand_quicknet_chain_profile(malformed)
        assert_unchanged()

    hollow = object.__new__(module.MachineTimeDrandQuicknetChainProfile)
    with pytest.raises(_ERROR):
        bool(hollow)
    assert_unchanged()


def test_repr_and_str_are_redacted_ascii_single_line_and_bounded() -> None:
    profile = _build()
    rendered = repr(profile)
    assert str(profile) == rendered
    assert rendered.isascii()
    assert "\n" not in rendered and "\r" not in rendered
    assert len(rendered) <= 512
    assert len(rendered) == 411
    assert _PUBLIC_KEY_HEX not in rendered
    assert _PUBLIC_KEY_HEX[:32] not in rendered
    assert _PUBLIC_KEY not in rendered.encode()
    assert _CHAIN_HASH not in rendered
    assert _EXPECTED_BOUND_REGISTRY_DIGEST not in rendered
    assert "public_key=<redacted len=96" in rendered
    assert _EXPECTED_PUBLIC_KEY_FINGERPRINT in rendered
    assert _EXPECTED_PROFILE_SELF_DIGEST in rendered
    assert "chain_profile_structurally_bound=True" in rendered
    for forbidden in ("ready=", "verified=True", "admitted=True", "approved=True", "operational=True"):
        assert forbidden not in rendered
    for deferred in _DEFERRED_FACTS:
        assert deferred not in rendered

    unicode_rendered = repr(_build(snapshot=_snapshot(snapshot_id=_UNICODE_SNAPSHOT_ID)))
    assert unicode_rendered.isascii()
    assert _UNICODE_SNAPSHOT_ID not in unicode_rendered
    assert "snapshot_id=<str len=11>" in unicode_rendered


def test_every_protected_promotion_flag_is_exactly_false() -> None:
    profile = _build()
    descriptor = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor(profile)
    for name in _EXPECTED_FALSE_FLAGS:
        value = getattr(profile, name)
        assert value is False, name
        assert descriptor[name] is False, name
    assert profile.chain_profile_structurally_bound is True
    for absent in ("ready", "verified", "admitted", "operational", "approved"):
        assert not hasattr(profile, absent)
    assert set(_EXPECTED_FALSE_FLAGS).isdisjoint({"chain_profile_structurally_bound"})
    assert len(_EXPECTED_FALSE_FLAGS) == 18


def test_snapshot_eligible_row_mirrors_the_complete_s1_eligible_row() -> None:
    assert module._SNAPSHOT_ROW_FIELDS == _EXPECTED_SNAPSHOT_ROW_FIELDS
    assert module._SNAPSHOT_ROW == _EXPECTED_SNAPSHOT_ROW
    assert len(module._SNAPSHOT_ROW_FIELDS) == 13
    assert len(module._SNAPSHOT_ROW) == 13
    assert len(set(module._SNAPSHOT_ROW_FIELDS)) == 13
    assert module._SNAPSHOT_ROW_FIELDS.count("independence_class") == 1
    assert module._SNAPSHOT_ROW_FIELDS.index("independence_class") == 6
    assert module._SNAPSHOT_ROW[6] == "threshold-bls-beacon"
    assert module._INDEPENDENCE_CLASS == "threshold-bls-beacon"

    # the row is READ through the S1 public boundary exactly once
    assert "independence_class" in module._SNAPSHOT_READ_FIELDS
    assert module._SNAPSHOT_READ_FIELDS.count("independence_class") == 1
    assert module._SNAPSHOT_READ_FIELDS[: len(module._SNAPSHOT_ROW_FIELDS)] == module._SNAPSHOT_ROW_FIELDS

    # the S2 contract must mirror the COMPLETE upstream S1 eligible row, in S1's order with S1's values,
    # so no independently valid cross-product can ever be accepted here that S1 would reject
    assert module._SNAPSHOT_ROW_FIELDS == s1_module._ROW_FIELD_NAMES
    assert module._SNAPSHOT_ROW == s1_module._ELIGIBLE_ROW
    assert set(s1_module._ROW_FIELD_NAMES) - set(module._SNAPSHOT_ROW_FIELDS) == set()
    assert len(s1_module._ROW_FIELD_NAMES) == len(module._SNAPSHOT_ROW_FIELDS)

    # a valid S1 artifact really does carry that independence class, and binding still succeeds
    snapshot = _snapshot()
    assert snapshot.independence_class == "threshold-bls-beacon"
    profile = _build(snapshot=snapshot)
    assert bool(profile) is True
    assert profile.profile_self_digest == _EXPECTED_PROFILE_SELF_DIGEST

    # it is a verification input only: it is never published and cannot change any digest
    assert "independence_class" not in module._DESCRIPTOR_FIELD_NAMES
    assert "independence_class" not in module._FIELD_NAMES
    assert not hasattr(profile, "independence_class")


def test_diagnostic_seal_is_permanent_under_ordinary_attribute_operations() -> None:
    reasons = tuple(module.MachineTimeDrandQuicknetChainProfileReason)
    assert len(reasons) == 16
    assert module._ERROR_IMMUTABLE_ATTRS == frozenset({"_reason", "reason", "args", "_sealed"})

    for reason in reasons:
        constructed = module.MachineTimeDrandQuicknetChainProfileError(reason)
        assert constructed.reason is reason
        assert constructed.args == (reason.value,)
        assert str(constructed) == reason.value
        assert constructed._sealed is True

    for wrong in ("wrong_input_type", 0, None, object(), module.MachineTimeDrandQuicknetChainProfileReason):
        with pytest.raises(TypeError):
            module.MachineTimeDrandQuicknetChainProfileError(wrong)
    with pytest.raises(TypeError) as captured_type:
        module.MachineTimeDrandQuicknetChainProfileError("caller-controlled-secret")
    assert "caller-controlled-secret" not in str(captured_type.value)

    first = module.MachineTimeDrandQuicknetChainProfileReason.WRONG_INPUT_TYPE
    other = module.MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_MISMATCH
    error = module.MachineTimeDrandQuicknetChainProfileError(first)
    baseline_args = error.args
    baseline_text = str(error)
    assert baseline_args == (first.value,)
    assert baseline_text == first.value

    def assert_diagnostic_intact() -> None:
        assert error.reason is first
        assert error._reason is first
        assert error.args == baseline_args
        assert str(error) == baseline_text
        assert error._sealed is True

    for name, value in (
        ("_reason", other),
        ("reason", other),
        ("args", ("tampered",)),
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
            error.args = ("tampered",)
        assert_diagnostic_intact()
    assert "tampered" not in str(error)
    assert other.value not in str(error)


def test_diagnostic_raised_by_production_is_sealed_and_reason_stays_exact() -> None:
    with pytest.raises(module.MachineTimeDrandQuicknetChainProfileError) as captured:
        _build(chain_hash="0" * 64)
    caught = captured.value
    assert caught.reason is module.MachineTimeDrandQuicknetChainProfileReason.CHAIN_IDENTITY_MISMATCH
    assert caught.args == ("chain_identity_mismatch",)
    assert str(caught) == "chain_identity_mismatch"

    for name in ("_reason", "reason", "args", "_sealed"):
        with pytest.raises(AttributeError):
            delattr(caught, name)
    with pytest.raises(AttributeError):
        caught._sealed = False
    with pytest.raises(AttributeError):
        caught._reason = module.MachineTimeDrandQuicknetChainProfileReason.SELF_DIGEST_MISMATCH

    assert caught.reason is module.MachineTimeDrandQuicknetChainProfileReason.CHAIN_IDENTITY_MISMATCH
    assert str(caught) == "chain_identity_mismatch"
    assert caught._sealed is True


def test_connector_ready_dialect_projection_is_unchanged() -> None:
    assert tuple(spec.dialect_id for spec in connector_ready_dialects()) == (
        "deribit:l2_orderbook:book_instrument_interval",
    )


def test_every_retained_closed_reason_is_behaviorally_reachable() -> None:
    profile = _build()
    state = _reduce_state(profile)
    rebuild = module._rebuild_machine_time_drand_quicknet_chain_profile

    def reason_of(call: object) -> object:
        with pytest.raises(_ERROR) as captured:
            call()
        return captured.value.reason

    observed = {
        reason_of(lambda: module.machine_time_drand_quicknet_chain_profile_self_digest(object())),
        reason_of(lambda: _build(chain_info=[])),
        reason_of(lambda: _build(chain_info={})),
        reason_of(lambda: _build(period_seconds="3")),
        reason_of(lambda: _build(scheme_id="bls" + chr(7))),
        reason_of(lambda: _build(scheme_id="q" * 257)),
        reason_of(lambda: _build(snapshot=object())),
        reason_of(lambda: _build(registry=object())),
        reason_of(lambda: _build(chain_hash="0" * 64)),
        reason_of(lambda: _build(public_key="z" * 192)),
        reason_of(lambda: _build(public_key=_PUBLIC_KEY_HEX[:-2])),
        reason_of(lambda: _build(public_key="00" * 96)),
        reason_of(lambda: rebuild(state[:3] + ((True,) + state[3][1:], state[4]))),
        reason_of(lambda: rebuild(state[:4] + ("A" * 64,))),
        reason_of(lambda: rebuild(state[:4] + ("0" * 64,))),
        reason_of(lambda: rebuild(state[:-1])),
        reason_of(lambda: bool(object.__new__(module.MachineTimeDrandQuicknetChainProfile))),
    }
    assert observed == set(_REASON)
    assert len(observed) == 16


def test_no_product_io_network_clock_or_prohibited_import_surface() -> None:
    import ast

    source = inspect.getsource(module)
    parsed = ast.parse(source)
    imports: set[str] = set()
    for node in ast.walk(parsed):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".", maxsplit=1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.add(node.module.split(".", maxsplit=1)[0])
    assert imports == {"__future__", "hashlib", "json", "weakref", "enum", "crypto_core"}
    prohibited = {
        "aiohttp",
        "asyncio",
        "datetime",
        "http",
        "httpx",
        "os",
        "pathlib",
        "random",
        "requests",
        "socket",
        "subprocess",
        "time",
        "urllib",
        "websockets",
    }
    assert not imports & prohibited
    assert {"bls", "blspy", "py_ecc", "connector", "readiness", "requests", "socket"}.isdisjoint(module.__dict__)
    called_names = {
        node.func.id for node in ast.walk(parsed) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    called_attributes = {
        node.func.attr
        for node in ast.walk(parsed)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert not called_names & {"open", "input", "exec", "eval", "compile", "__import__"}
    assert not called_attributes & {"now", "utcnow", "today", "sleep", "Popen", "run", "request", "urlopen", "getenv"}
    assert "except Exception" not in source
    assert 'errors="ignore"' not in source
    assert 'errors="replace"' not in source
    assert "surrogatepass" not in source
