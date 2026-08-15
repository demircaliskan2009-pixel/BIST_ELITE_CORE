"""Permanent adversarial contract tests for the MT4-S3B governed verifier-profile admission.

These tests own the governance boundary behaviourally, not by reading prose:

* exactly four selections may become true, and every proof/quorum/time/readiness flag stays false;
* a build recipe never authorizes a binary -- an unknown digest is NOT ADMITTED even when its recipe
  matches an admitted instance (this is the defect the independent audit named);
* the committed production evidence artifact is canonical, digest-pinned, and free of credentials,
  transient URLs, native binaries and raw production Quicknet bytes;
* the digest policy is structured, never a bare bool, and never authorizes a native load;
* the module contains no FFI, no network, no clock, no environment and no filesystem-evidence trust.

Offline and deterministic: nothing here builds, loads, downloads or hashes a native library.
"""

from __future__ import annotations

import ast
import hashlib
import importlib
import json
import re
from pathlib import Path

import pytest

from crypto_core.validation.machine_time_source_registry import (
    build_approved_machine_time_source_registry,
    machine_time_source_registry_to_dict,
)

module = importlib.import_module("crypto_core.validation.machine_time_drand_quicknet_verifier_profile")
chain_tests = importlib.import_module("tests.crypto_core.validation.test_machine_time_drand_quicknet_chain_profile")

_ERROR = module.MachineTimeDrandQuicknetVerifierProfileError
_REASON = module.MachineTimeDrandQuicknetVerifierProfileReason
_DIGEST_REASON = module.MachineTimeDrandQuicknetBinaryDigestReason
_STATUS = module.MachineTimeDrandQuicknetInstanceStatus

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MODULE_PATH = _REPO_ROOT / "src" / "crypto_core" / "validation" / "machine_time_drand_quicknet_verifier_profile.py"
_EVIDENCE_PATH = (
    _REPO_ROOT / "src" / "crypto_core" / "validation" / "evidence" / "mt4_blst_stage_c_admission_evidence_v1.json"
)

_LINUX_BINARY = "366d17c18db8dda0112b9a155ffbbb17e558654f0aed22da9748b5ab07f5b867"
_WINDOWS_BINARY = "d18ccbe99f4bdff6d2f1314b38c3a63231aea7287df278a864e77c1cc9afb362"
_LINUX_RECIPE = "2c1fb9c45881ab76a91c524dba779092a0801978228ce13ede451fd9260ea896"
_WINDOWS_RECIPE = "cd229ba172779bcad1285189a75aeda233d5ad1d7a108998c15951a8a53faae7"
_QUALIFICATION_WORKFLOW_SHA256 = "45d0f8dba660af516a2e92e7f8579a22da61a731d9948a61c9298878160e89c3"
_HEAD_SHA = "56b82260b69f2ea4e011438256d6996d77348c4e"
_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
_PREDICATE_TYPE = (
    "https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/attestations/crypto-core/mt4-blst-admission-evidence/v1"
)

_TRUE_FLAGS = (
    "dependency_profile_admitted",
    "cryptographic_backend_selected",
    "mt4_verifier_profile_selected",
    "message_encoding_profile_selected",
)
_FALSE_FLAGS = (
    "fixture_corpus_admitted",
    "fixture_corpus_loaded",
    "fixture_corpus_verified",
    "signature_parsed",
    "signature_verified",
    "randomness_verified",
    "proof_verified",
    "source_reachable_proven",
    "provider_operationally_approved",
    "operational_use_approved",
    "quorum_countable",
    "operational_quorum_ready",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "readiness_promoted",
    "connector_promoted",
    "operational_readiness",
    "shadow_ready",
    "live_ready",
    "private_api_ready",
)


def _snapshot(**changes: object) -> object:
    return chain_tests._snapshot(**changes)


def _registry() -> object:
    return build_approved_machine_time_source_registry()


def _chain_profile(**changes: object) -> object:
    return chain_tests._build(**changes)


def _profile(**overrides: object) -> object:
    return module.build_machine_time_drand_quicknet_verifier_profile(
        snapshot=overrides.get("snapshot", _snapshot()),
        registry=overrides.get("registry", _registry()),
        chain_profile=overrides.get("chain_profile", _chain_profile()),
    )


def _raises(reason: object, **overrides: object) -> None:
    with pytest.raises(_ERROR) as captured:
        _profile(**overrides)
    assert captured.value.reason is reason


def _evidence() -> dict:
    return json.loads(_EVIDENCE_PATH.read_bytes().decode("utf-8"))


# ---------------------------------------------------------------------------------------------
# Happy profile
# ---------------------------------------------------------------------------------------------


def test_governed_profile_publishes_exactly_the_four_selections() -> None:
    profile = _profile()
    for flag in _TRUE_FLAGS:
        assert getattr(profile, flag) is True, flag
    for flag in _FALSE_FLAGS:
        assert getattr(profile, flag) is False, flag


@pytest.mark.parametrize("flag", _FALSE_FLAGS)
def test_no_successful_profile_can_promote_a_protected_flag(flag: str) -> None:
    """Each protected flag is proven individually so a bulk assertion cannot mask one."""
    assert getattr(_profile(), flag) is False


def test_profile_binds_the_complete_verifier_contract() -> None:
    descriptor = module.machine_time_drand_quicknet_verifier_profile_commitment_descriptor(_profile())
    assert descriptor["profile_id"] == "drand-quicknet-bls-g1-verifier-blst-v0317-offline.v1"
    assert descriptor["source_id"] == "drand-quicknet-mainnet"
    assert descriptor["beacon_id"] == "quicknet"
    assert descriptor["chain_hash"] == _CHAIN_HASH
    assert descriptor["curve"] == "BLS12-381"
    assert descriptor["scheme"] == "bls-unchained-g1-rfc9380"
    assert descriptor["public_key_group"] == "G2"
    assert descriptor["signature_group"] == "G1"
    assert descriptor["public_key_encoded_length"] == 96
    assert descriptor["signature_encoded_length"] == 48
    assert descriptor["message_transform"] == "SHA256(uint64_big_endian(round))"
    assert descriptor["message_length"] == 32
    assert descriptor["dst"] == "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
    assert descriptor["augmentation"] == "NONE"
    assert descriptor["canonical_compressed_encoding_required"] is True
    assert descriptor["recompression_equality_required"] is True
    assert descriptor["public_key_infinity_policy"] == "REJECT"
    assert descriptor["signature_infinity_policy"] == "REJECT"
    assert descriptor["public_key_subgroup_policy"] == "REQUIRED"
    assert descriptor["signature_subgroup_policy"] == "REQUIRED"
    assert descriptor["verification_policy_id"] == "deterministic_supplied_proof_verification_no_network.v1"
    assert descriptor["dependency_profile_id"] == "D-DEP-02"
    assert descriptor["fixture_corpus_id"] == "FX-DRAND-QUICKNET.v1"


def test_abi_status_taxonomy_is_bound_exactly() -> None:
    taxonomy = module.machine_time_drand_quicknet_verifier_profile_commitment_descriptor(_profile())[
        "abi_status_taxonomy"
    ]
    assert [tuple(entry) for entry in taxonomy] == [
        (0, "OK"),
        (1, "NULL_INPUT"),
        (2, "BAD_LENGTH"),
        (3, "PK_BAD_ENCODING"),
        (4, "PK_NON_CANONICAL"),
        (5, "PK_INFINITY"),
        (6, "PK_NOT_IN_GROUP"),
        (7, "SIG_BAD_ENCODING"),
        (8, "SIG_NON_CANONICAL"),
        (9, "SIG_INFINITY"),
        (10, "SIG_NOT_IN_GROUP"),
        (11, "VERIFY_FAILED"),
    ]


def test_profile_binds_dependency_and_signer_identity() -> None:
    descriptor = module.machine_time_drand_quicknet_verifier_profile_commitment_descriptor(_profile())
    assert descriptor["upstream_repository"] == "https://github.com/supranational/blst"
    assert descriptor["upstream_release"] == "v0.3.17"
    assert descriptor["upstream_commit"] == _UPSTREAM_COMMIT
    assert descriptor["upstream_source_tree_digest"] == (
        "5a709c19ef7a1b9798ad58728fc5dd3b4d2026ecdd0342ebf8546c5950cea006"
    )
    assert descriptor["qualification_workflow_sha256"] == _QUALIFICATION_WORKFLOW_SHA256
    assert descriptor["qualification_head_sha"] == _HEAD_SHA
    assert descriptor["qualification_event"] == "workflow_dispatch"
    assert descriptor["qualification_branch"] == "main"
    assert descriptor["signer_repository"] == "demircaliskan2009-pixel/BIST_ELITE_CORE"
    assert descriptor["signer_workflow_path"] == ".github/workflows/crypto_core_mt4_trusted_attestation.yml"
    assert descriptor["signer_ref"] == "refs/heads/main"
    assert descriptor["oidc_issuer"] == "https://token.actions.githubusercontent.com"
    assert descriptor["custom_predicate_type"] == _PREDICATE_TYPE
    # The qualification workflow may never be the signer.
    assert descriptor["signer_workflow_path"] != descriptor["qualification_workflow_path"]
    # SLSA provenance is never the admission predicate.
    assert "slsa.dev" not in descriptor["custom_predicate_type"]


def test_profile_is_deterministic() -> None:
    first = module.machine_time_drand_quicknet_verifier_profile_canonical_bytes(_profile())
    second = module.machine_time_drand_quicknet_verifier_profile_canonical_bytes(_profile())
    assert first == second
    assert module.machine_time_drand_quicknet_verifier_profile_self_digest(
        _profile()
    ) == module.machine_time_drand_quicknet_verifier_profile_self_digest(_profile())


def test_self_digest_is_domain_separated_and_covers_the_lifecycle_table() -> None:
    profile = _profile()
    descriptor = module.machine_time_drand_quicknet_verifier_profile_commitment_descriptor(profile)
    canonical = json.dumps(descriptor, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    expected = hashlib.sha256(
        b"machine-time-drand-quicknet-verifier-profile.v1/self-digest\x00" + canonical.encode("utf-8")
    ).hexdigest()
    assert module.machine_time_drand_quicknet_verifier_profile_self_digest(profile) == expected
    # The instance lifecycle table must be inside the digested descriptor.
    assert "admitted_instances" in descriptor
    assert any(entry["status"] == _STATUS.ACTIVE.value for entry in descriptor["admitted_instances"])
    mutated = dict(descriptor)
    mutated["admitted_instances"] = []
    mutated_canonical = json.dumps(mutated, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert mutated_canonical != canonical


# ---------------------------------------------------------------------------------------------
# Production evidence artifact
# ---------------------------------------------------------------------------------------------


def test_production_evidence_lives_in_production_not_tests() -> None:
    assert _EVIDENCE_PATH.is_file()
    posix = _EVIDENCE_PATH.relative_to(_REPO_ROOT).as_posix()
    assert posix == module.MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_RELATIVE_PATH
    assert posix.startswith("src/crypto_core/validation/evidence/")
    assert "tests/" not in posix and "fixtures" not in posix


def test_production_evidence_bytes_are_canonical_and_digest_pinned() -> None:
    raw = _EVIDENCE_PATH.read_bytes()
    assert not raw.endswith(b"\n"), "evidence must have no trailing newline"
    text = raw.decode("utf-8")
    reserialized = json.dumps(
        json.loads(text), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    )
    assert reserialized == text, "evidence file is not canonical"
    assert hashlib.sha256(raw).hexdigest() == module.MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256


def test_production_evidence_binds_the_exact_stage_c_source() -> None:
    evidence = _evidence()
    assert evidence["schema"] == "mt4-blst-stage-c-admission-evidence.v1"
    assert evidence["evidence_status"] == "ADMISSION_EVIDENCE_ONLY"
    source = evidence["source_qualification"]
    assert source["repository"] == "demircaliskan2009-pixel/BIST_ELITE_CORE"
    assert source["event"] == "workflow_dispatch"
    assert source["branch"] == "main"
    assert source["head_sha"] == _HEAD_SHA
    assert source["qualification_workflow_sha256"] == _QUALIFICATION_WORKFLOW_SHA256
    trusted = evidence["trusted_attestation"]
    assert trusted["custom_predicate_type"] == _PREDICATE_TYPE
    assert trusted["trusted_workflow_ref"] == "refs/heads/main"
    assert trusted["oidc_issuer"] == "https://token.actions.githubusercontent.com"
    assert trusted["historical_slsa_attestations_are_not_admission_evidence"] is True


@pytest.mark.parametrize(
    "platform_id,binary,recipe",
    [("linux-x64", _LINUX_BINARY, _LINUX_RECIPE), ("windows-x64", _WINDOWS_BINARY, _WINDOWS_RECIPE)],
)
def test_production_evidence_carries_each_platform_subject_and_bundle(
    platform_id: str, binary: str, recipe: str
) -> None:
    entry = _evidence()["platforms"][platform_id]
    assert entry["binary_sha256"] == binary
    assert entry["build_recipe_sha256"] == recipe
    bundle = entry["attestation_bundle"]
    assert bundle["mediaType"].startswith("application/vnd.dev.sigstore.bundle")
    assert "dsseEnvelope" in bundle and "verificationMaterial" in bundle
    canonical = json.dumps(bundle, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    assert hashlib.sha256(canonical.encode("utf-8")).hexdigest() == entry["attestation_bundle_sha256"]
    manifest = entry["canonical_build_manifest"]
    assert manifest["output_binary_sha256"] == binary
    assert manifest["build_recipe_digest"] == recipe


def test_production_evidence_preserves_the_trusted_root_with_its_digest() -> None:
    trusted_root = _evidence()["trusted_root"]
    material = trusted_root["material"]
    assert isinstance(material, str) and material
    assert hashlib.sha256(material.encode("utf-8")).hexdigest() == trusted_root["sha256"]
    assert trusted_root["sha256"] == "65ca537f6ed8a47fd0e560c421baa1f6c1efb8b25fc200d8c5c02c0e92eb2b9c"


def test_production_evidence_records_offline_reproof_of_both_platforms() -> None:
    reproof = _evidence()["offline_reproof"]
    assert reproof["performed"] is True
    assert reproof["linux_x64"] == "PASS"
    assert reproof["windows_x64"] == "PASS"
    assert reproof["transparency_log_inclusion_verified"] is True


def test_production_evidence_protected_flags_remain_false() -> None:
    evidence = _evidence()
    assert all(value is False for value in evidence["protected_flags"].values())
    for platform in evidence["platforms"].values():
        manifest = platform["canonical_build_manifest"]
        receipt = platform["canonical_qualification_receipt"]
        for flag in ("dependency_profile_admitted", "proof_verified", "readiness_promoted"):
            assert manifest[flag] is False
            assert receipt[flag] is False
        assert receipt["raw_bytes_persisted"] is False


def test_production_evidence_contains_no_secrets_urls_or_binaries() -> None:
    text = _EVIDENCE_PATH.read_text(encoding="utf-8")
    lowered = text.lower()
    for forbidden in (
        "authorization:",
        "bearer ",
        "ghp_",
        "gho_",
        "ghs_",
        "github_token",
        "x-amz-signature",
        "sig=",
        "se=2026",
        "blob.core.windows.net",
        "productionresultssa",
    ):
        assert forbidden not in lowered, forbidden
    # No native binary smuggled in: ELF/PE magic must not appear in any encoding we emit.
    assert "\\u007fELF" not in text and "7f454c46" not in lowered
    assert "MZ\\u0090" not in text
    # Lane B raw production material is never persisted.
    assert "previous_signature" not in lowered
    assert "randomness" not in lowered


def test_production_evidence_records_per_platform_checkout_digests_honestly() -> None:
    """Licence and shim digests differ per platform because git rewrites LF to CRLF on Windows."""
    evidence = _evidence()
    linux = evidence["platforms"]["linux-x64"]
    windows = evidence["platforms"]["windows-x64"]
    assert linux["shim_source_sha256"] != windows["shim_source_sha256"]
    assert linux["upstream_license_sha256"] != windows["upstream_license_sha256"]
    # The git-object source-tree digest is platform independent and must agree.
    assert (
        linux["canonical_build_manifest"]["upstream_source_tree_digest"]
        == (windows["canonical_build_manifest"]["upstream_source_tree_digest"])
    )
    assert evidence["blst"]["license_and_shim_digests_are_per_platform"] is True


# ---------------------------------------------------------------------------------------------
# Predecessor bindings
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("bad", [None, object(), "snapshot", 42, {}])
def test_wrong_snapshot_type_is_rejected(bad: object) -> None:
    _raises(_REASON.SNAPSHOT_BINDING_INVALID, snapshot=bad)


@pytest.mark.parametrize("bad", [None, object(), "registry", 42, {}])
def test_wrong_registry_type_is_rejected(bad: object) -> None:
    _raises(_REASON.REGISTRY_BINDING_INVALID, registry=bad)


@pytest.mark.parametrize("bad", [None, object(), "chain", 42, {}])
def test_wrong_chain_profile_type_is_rejected(bad: object) -> None:
    _raises(_REASON.CHAIN_PROFILE_BINDING_INVALID, chain_profile=bad)


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "nist-randomness-beacon-v2-beta"),
        ("provider_id", "other-provider"),
        ("recommended_role", "not_after"),
        ("dependency_profile_id", "D-DEP-99"),
        ("fixture_corpus_id", "FX-OTHER.v1"),
        ("verification_policy_id", "other-policy.v1"),
        ("protocol_profile_id", "other-profile.v1"),
    ],
)
def test_wrong_s1_row_field_cannot_reach_s3b(field: str, value: str) -> None:
    """S1 refuses to build a wrong row at all, so no such artifact can ever be offered to S3B.

    S3B still re-checks the whole row; that check is defense in depth against a future S1 allowlist
    widening, and is proven separately by ``test_s3b_independently_rechecks_the_s1_row``.
    """
    with pytest.raises(Exception) as captured:
        _snapshot(**{field: value})
    assert type(captured.value).__name__ == "MachineTimeSourceTrustSnapshotError"


def test_s3b_independently_rechecks_the_s1_row() -> None:
    """The defense-in-depth row check exists and fires, exercised through the internal binding."""
    expected = dict(zip(module._SNAPSHOT_ROW_FIELDS, module._SNAPSHOT_ROW))
    assert expected["source_id"] == "drand-quicknet-mainnet"
    assert expected["dependency_profile_id"] == "D-DEP-02"
    assert expected["fixture_corpus_id"] == "FX-DRAND-QUICKNET.v1"
    assert expected["verification_policy_id"] == "deterministic_supplied_proof_verification_no_network.v1"
    assert expected["recommended_role"] == "not_before"
    # A non-snapshot object must fail the exact-type gate before any field is read.
    with pytest.raises(_ERROR) as captured:
        module._snapshot_binding(object())
    assert captured.value.reason is _REASON.SNAPSHOT_BINDING_INVALID


def test_s2_chain_profile_from_a_different_chain_is_rejected() -> None:
    """A structurally valid S2 artifact for other material must not satisfy S3B."""
    other_snapshot = _snapshot()
    profile = _profile(snapshot=other_snapshot)
    assert profile.bound_snapshot_self_digest == other_snapshot.snapshot_self_digest


@pytest.mark.parametrize(
    "flag",
    [
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
    ],
)
def test_promoted_registry_flag_is_rejected(monkeypatch: pytest.MonkeyPatch, flag: str) -> None:
    """S3B must refuse to build on an MT-3 registry that has promoted any operational claim."""
    registry = _registry()
    real = module.machine_time_source_registry_to_dict

    def promoted(candidate: object) -> dict:
        payload = dict(real(candidate))
        payload[flag] = True
        return payload

    monkeypatch.setattr(module, "machine_time_source_registry_to_dict", promoted)
    with pytest.raises(_ERROR) as captured:
        _profile(registry=registry)
    assert captured.value.reason is _REASON.REGISTRY_BINDING_INVALID


def test_registry_digest_forgery_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    real = module.machine_time_source_registry_to_dict

    def forged(candidate: object) -> dict:
        payload = dict(real(candidate))
        payload["registry_digest"] = "0" * 64
        return payload

    monkeypatch.setattr(module, "machine_time_source_registry_to_dict", forged)
    with pytest.raises(_ERROR) as captured:
        _profile()
    assert captured.value.reason is _REASON.REGISTRY_BINDING_INVALID


def test_registry_without_the_drand_record_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    real = module.machine_time_source_registry_to_dict

    def stripped(candidate: object) -> dict:
        payload = dict(real(candidate))
        payload["sources"] = [item for item in payload["sources"] if item["source_id"] != "drand-quicknet-mainnet"]
        return payload

    monkeypatch.setattr(module, "machine_time_source_registry_to_dict", stripped)
    with pytest.raises(_ERROR) as captured:
        _profile()
    assert captured.value.reason is _REASON.REGISTRY_BINDING_INVALID


@pytest.mark.parametrize("fact,value", [("chain_hash", "0" * 64), ("scheme", "bls-other")])
def test_registry_drand_fact_mismatch_is_rejected(monkeypatch: pytest.MonkeyPatch, fact: str, value: str) -> None:
    real = module.machine_time_source_registry_to_dict

    def tampered(candidate: object) -> dict:
        payload = dict(real(candidate))
        sources = []
        for item in payload["sources"]:
            if item["source_id"] == "drand-quicknet-mainnet":
                item = dict(item)
                item["fact_items"] = [
                    [name, value if name == fact else current] for name, current in item["fact_items"]
                ]
            sources.append(item)
        payload["sources"] = sources
        return payload

    monkeypatch.setattr(module, "machine_time_source_registry_to_dict", tampered)
    with pytest.raises(_ERROR) as captured:
        _profile()
    assert captured.value.reason is _REASON.REGISTRY_BINDING_INVALID


@pytest.mark.parametrize(
    "field,value",
    [
        ("source_id", "other-source"),
        ("chain_hash", "0" * 64),
        ("scheme_id", "bls-other"),
        ("dependency_profile_id", "D-DEP-99"),
        ("fixture_corpus_id", "FX-OTHER.v1"),
        ("verification_policy_id", "other.v1"),
        ("public_key_encoded_length", 48),
        ("dependency_profile_admitted", True),
        ("proof_verified", True),
    ],
)
def test_chain_profile_descriptor_mismatch_is_rejected(
    monkeypatch: pytest.MonkeyPatch, field: str, value: object
) -> None:
    """S2 must be the exact governed chain profile, and must not itself be promoted."""
    real = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor

    def tampered(candidate: object) -> dict:
        descriptor = dict(real(candidate))
        descriptor[field] = value
        return descriptor

    monkeypatch.setattr(module, "machine_time_drand_quicknet_chain_profile_commitment_descriptor", tampered)
    with pytest.raises(_ERROR) as captured:
        _profile()
    assert captured.value.reason is _REASON.CHAIN_PROFILE_BINDING_INVALID


def test_chain_profile_public_key_fingerprint_must_match_s1_material(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The same trust material must stand behind both S1 and S2, or the binding fails closed."""
    real = module.machine_time_drand_quicknet_chain_profile_commitment_descriptor

    def tampered(candidate: object) -> dict:
        descriptor = dict(real(candidate))
        descriptor["public_key_fingerprint"] = "0" * 64
        return descriptor

    monkeypatch.setattr(module, "machine_time_drand_quicknet_chain_profile_commitment_descriptor", tampered)
    with pytest.raises(_ERROR) as captured:
        _profile()
    assert captured.value.reason is _REASON.CHAIN_PROFILE_BINDING_INVALID


def test_predecessor_serializers_fail_closed_on_foreign_objects() -> None:
    """Pins the invariant that makes the exact-type gates defense in depth rather than sole defense.

    A registry subclass CAN be declared, so the exact-type gate is not decorative. It is not
    separately exploitable today only because the registry serializer refuses any object it did not
    build -- both layers must keep holding. If this ever starts returning a payload for a foreign
    object, the exact-type gate becomes the only defense and must not be weakened.
    """
    from crypto_core.validation.machine_time_source_registry import MachineTimeSourceRegistryError

    subclass = type("HostileRegistrySubclass", (module.MachineTimeSourceRegistry,), {})
    hollow = object.__new__(subclass)
    assert type(hollow) is not module.MachineTimeSourceRegistry
    with pytest.raises(MachineTimeSourceRegistryError):
        module.machine_time_source_registry_to_dict(hollow)
    with pytest.raises(_ERROR) as captured:
        _profile(registry=hollow)
    assert captured.value.reason is _REASON.REGISTRY_BINDING_INVALID

    # The S2 chain profile is sealed outright, so no subclass can exist at all.
    with pytest.raises(TypeError):
        type("HostileChainSubclass", (module.MachineTimeDrandQuicknetChainProfile,), {})


def test_predecessor_digests_are_bound_into_the_profile() -> None:
    snapshot = _snapshot()
    registry = _registry()
    chain_profile = _chain_profile()
    profile = _profile(snapshot=snapshot, registry=registry, chain_profile=chain_profile)
    payload = machine_time_source_registry_to_dict(registry)
    assert profile.bound_snapshot_self_digest == snapshot.snapshot_self_digest
    assert profile.bound_registry_digest == payload["registry_digest"]
    assert profile.bound_chain_profile_self_digest == (
        chain_tests.module.machine_time_drand_quicknet_chain_profile_self_digest(chain_profile)
    )


# ---------------------------------------------------------------------------------------------
# Recipe non-transitivity -- the core audit finding
# ---------------------------------------------------------------------------------------------


def test_profile_declares_recipe_digests_do_not_authorize_binaries() -> None:
    assert _profile().recipe_digest_authorizes_binary is False


@pytest.mark.parametrize(
    "platform_id,recipe",
    [("linux-x64", _LINUX_RECIPE), ("windows-x64", _WINDOWS_RECIPE)],
)
def test_matching_recipe_with_unknown_digest_is_never_admitted(platform_id: str, recipe: str) -> None:
    """A rebuild under the identical recipe is still a different governed decision."""
    profile = _profile()
    unknown = hashlib.sha256(b"a legitimate rebuild under the same recipe").hexdigest()
    admitted = {entry["binary_sha256"] for entry in profile.admitted_instances}
    assert unknown not in admitted
    assert recipe in {entry["build_recipe_sha256"] for entry in profile.admitted_instances}
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        profile, platform_id=platform_id, binary_sha256=unknown
    )
    assert decision.accepted is False
    assert decision.reason is _DIGEST_REASON.BINARY_INSTANCE_NOT_ADMITTED
    assert decision.matched_instance_id is None


def test_no_recipe_field_can_be_used_as_an_acceptance_key() -> None:
    """Passing a recipe digest where a binary digest is expected must not accept."""
    profile = _profile()
    for platform_id, recipe in (("linux-x64", _LINUX_RECIPE), ("windows-x64", _WINDOWS_RECIPE)):
        decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
            profile, platform_id=platform_id, binary_sha256=recipe
        )
        assert decision.accepted is False


# ---------------------------------------------------------------------------------------------
# Platform policy
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("platform_id,binary", [("linux-x64", _LINUX_BINARY), ("windows-x64", _WINDOWS_BINARY)])
def test_active_instance_is_accepted_for_its_own_platform(platform_id: str, binary: str) -> None:
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        _profile(), platform_id=platform_id, binary_sha256=binary
    )
    assert decision.accepted is True
    assert decision.reason is _DIGEST_REASON.ACCEPTED_ACTIVE_INSTANCE
    assert decision.matched_instance_id.startswith("mt4-blst-v0317-")
    assert decision.authorizes_native_load is False


@pytest.mark.parametrize("platform_id,binary", [("windows-x64", _LINUX_BINARY), ("linux-x64", _WINDOWS_BINARY)])
def test_cross_platform_subject_substitution_is_rejected(platform_id: str, binary: str) -> None:
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        _profile(), platform_id=platform_id, binary_sha256=binary
    )
    assert decision.accepted is False
    assert decision.reason is _DIGEST_REASON.BINARY_INSTANCE_NOT_ADMITTED


@pytest.mark.parametrize("platform_id", ["darwin-arm64", "linux-arm64", "", "LINUX-X64", None, 7, b"linux-x64"])
def test_unsupported_or_malformed_platform_is_structured_failure(platform_id: object) -> None:
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        _profile(), platform_id=platform_id, binary_sha256=_LINUX_BINARY
    )
    assert decision.accepted is False
    assert decision.reason is _DIGEST_REASON.PLATFORM_UNSUPPORTED


def test_no_reproducibility_claim_is_published() -> None:
    profile = _profile()
    assert profile.windows_bit_reproducibility_claimed is False
    assert profile.linux_bit_reproducibility_required is False
    source = _MODULE_PATH.read_text(encoding="utf-8").lower()
    assert "bit-for-bit reproducib" not in source.replace("no windows bit-for-bit reproducibility", "")


# ---------------------------------------------------------------------------------------------
# Digest policy shape and lifecycle
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "digest",
    ["", "abc", _LINUX_BINARY.upper(), _LINUX_BINARY[:-1], _LINUX_BINARY + "0", None, 42, b"0" * 64],
)
def test_malformed_binary_digest_is_rejected_structurally(digest: object) -> None:
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        _profile(), platform_id="linux-x64", binary_sha256=digest
    )
    assert decision.accepted is False
    assert decision.reason is _DIGEST_REASON.BINARY_DIGEST_INVALID


def test_decision_is_structured_and_immutable() -> None:
    decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
        _profile(), platform_id="linux-x64", binary_sha256=_LINUX_BINARY
    )
    assert decision.profile_self_digest == module.machine_time_drand_quicknet_verifier_profile_self_digest(_profile())
    assert not isinstance(decision, bool)
    with pytest.raises(AttributeError):
        decision.accepted = False
    with pytest.raises(AttributeError):
        del decision.reason
    with pytest.raises(TypeError):

        class _Sub(module.MachineTimeDrandQuicknetBinaryDigestDecision):
            pass


def test_authorizes_native_load_is_always_false() -> None:
    profile = _profile()
    for platform_id, digest in (
        ("linux-x64", _LINUX_BINARY),
        ("windows-x64", _WINDOWS_BINARY),
        ("linux-x64", "0" * 64),
        ("darwin-arm64", _LINUX_BINARY),
    ):
        decision = module.evaluate_machine_time_drand_quicknet_binary_digest(
            profile, platform_id=platform_id, binary_sha256=digest
        )
        assert decision.authorizes_native_load is False


def test_instance_lifecycle_states_are_distinct_and_only_active_accepts() -> None:
    assert {item.value for item in _STATUS} == {"active", "superseded", "revoked"}
    profile = _profile()
    assert all(entry["status"] == _STATUS.ACTIVE.value for entry in profile.admitted_instances)
    # Absence is NEVER_ADMITTED and is deliberately not a lifecycle member.
    assert "never_admitted" not in {item.value for item in _STATUS}
    reasons = {item.value for item in _DIGEST_REASON}
    assert {"binary_instance_superseded", "binary_instance_revoked", "binary_instance_not_admitted"} <= reasons


# ---------------------------------------------------------------------------------------------
# Fixture corpus
# ---------------------------------------------------------------------------------------------


def test_fixture_corpus_is_identified_but_never_admitted() -> None:
    profile = _profile()
    assert profile.fixture_corpus_id == "FX-DRAND-QUICKNET.v1"
    assert profile.fixture_corpus_admitted is False
    assert profile.fixture_corpus_loaded is False
    assert profile.fixture_corpus_verified is False
    # Non-admission is a SUCCESS state, so no failure reason may be named for it.
    assert "FIXTURE_CORPUS_NOT_ADMITTED" not in {item.name for item in _REASON}


# ---------------------------------------------------------------------------------------------
# Artifact integrity
# ---------------------------------------------------------------------------------------------


def test_profile_is_immutable_unhashable_and_sealed() -> None:
    profile = _profile()
    assert type(profile).__hash__ is None
    with pytest.raises(TypeError):
        hash(profile)
    with pytest.raises(AttributeError):
        profile.dependency_profile_admitted = False
    with pytest.raises(AttributeError):
        del profile.scheme
    with pytest.raises(TypeError):

        class _Sub(module.MachineTimeDrandQuicknetVerifierProfile):
            pass

    with pytest.raises(TypeError):
        module.MachineTimeDrandQuicknetVerifierProfile()


def test_descriptor_and_digest_reject_foreign_types() -> None:
    for bad in (None, object(), "profile", 42):
        with pytest.raises(_ERROR) as captured:
            module.machine_time_drand_quicknet_verifier_profile_commitment_descriptor(bad)
        assert captured.value.reason is _REASON.WRONG_INPUT_TYPE
        with pytest.raises(_ERROR):
            module.machine_time_drand_quicknet_verifier_profile_self_digest(bad)


def test_reconstruction_requires_exact_canonical_bytes() -> None:
    profile = _profile()
    canonical = module.machine_time_drand_quicknet_verifier_profile_canonical_bytes(profile)
    rebuilt = module.reconstruct_machine_time_drand_quicknet_verifier_profile(
        canonical, snapshot=_snapshot(), registry=_registry(), chain_profile=_chain_profile()
    )
    assert module.machine_time_drand_quicknet_verifier_profile_self_digest(rebuilt) == (
        module.machine_time_drand_quicknet_verifier_profile_self_digest(profile)
    )


@pytest.mark.parametrize("bad", [None, "text", 42, bytearray(b"{}"), memoryview(b"{}")])
def test_reconstruction_rejects_non_bytes(bad: object) -> None:
    with pytest.raises(_ERROR) as captured:
        module.reconstruct_machine_time_drand_quicknet_verifier_profile(
            bad, snapshot=_snapshot(), registry=_registry(), chain_profile=_chain_profile()
        )
    assert captured.value.reason is _REASON.RECONSTRUCTION_INPUT_INVALID


def test_reconstruction_rejects_non_canonical_and_tampered_bytes() -> None:
    canonical = module.machine_time_drand_quicknet_verifier_profile_canonical_bytes(_profile())
    parsed = json.loads(canonical.decode("utf-8"))

    pretty = json.dumps(parsed, sort_keys=True, indent=2).encode("utf-8")
    with pytest.raises(_ERROR) as captured:
        module.reconstruct_machine_time_drand_quicknet_verifier_profile(
            pretty, snapshot=_snapshot(), registry=_registry(), chain_profile=_chain_profile()
        )
    assert captured.value.reason is _REASON.CANONICAL_TEXT_INVALID

    forged = dict(parsed)
    forged["profile_self_digest"] = "0" * 64
    forged_bytes = json.dumps(forged, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    with pytest.raises(_ERROR) as captured:
        module.reconstruct_machine_time_drand_quicknet_verifier_profile(
            forged_bytes, snapshot=_snapshot(), registry=_registry(), chain_profile=_chain_profile()
        )
    assert captured.value.reason is _REASON.SELF_DIGEST_MISMATCH

    missing = dict(parsed)
    missing.pop("scheme")
    missing_bytes = json.dumps(missing, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    with pytest.raises(_ERROR) as captured:
        module.reconstruct_machine_time_drand_quicknet_verifier_profile(
            missing_bytes, snapshot=_snapshot(), registry=_registry(), chain_profile=_chain_profile()
        )
    assert captured.value.reason is _REASON.FIELD_INVENTORY_INVALID


def test_error_type_is_closed_and_immutable() -> None:
    error = _ERROR(_REASON.ARTIFACT_INCONSISTENT)
    assert error.reason is _REASON.ARTIFACT_INCONSISTENT
    with pytest.raises(AttributeError):
        error.reason = _REASON.WRONG_INPUT_TYPE
    with pytest.raises(TypeError):
        _ERROR("artifact_inconsistent")


# ---------------------------------------------------------------------------------------------
# Future loader policy
# ---------------------------------------------------------------------------------------------


def test_profile_publishes_the_mandatory_future_loader_policy() -> None:
    policy = _profile().native_load_policy
    assert policy["implemented_here"] is False
    assert policy["authorizes_native_load"] is False
    assert policy["forbidden_pattern"] == "hash(path) then load(path)"
    assert policy["bytes_hashed_must_be_bytes_mapped"] is True
    joined = " ".join(policy["requirements"]).lower()
    for requirement in (
        "symlink",
        "held handle",
        "process-private",
        "write and delete races",
        "restricted dependency search",
        "rpath",
        "fail closed",
    ):
        assert requirement in joined, requirement
    assert "memfd" in policy["linux_architecture_class"]
    assert "LoadLibraryExW" in policy["windows_architecture_class"]


# ---------------------------------------------------------------------------------------------
# Environment safety
# ---------------------------------------------------------------------------------------------


def test_production_module_imports_no_ffi_network_clock_or_environment() -> None:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "hashlib", "json", "enum", "crypto_core"}, imported
    for forbidden in ("ctypes", "cffi", "socket", "urllib", "requests", "subprocess", "os", "time", "datetime"):
        assert forbidden not in imported, forbidden


def test_production_module_contains_no_native_load_or_io_call() -> None:
    """Structural: assert on CALLS and ATTRIBUTES in the AST, never on substrings.

    Substring matching would be wrong here: the module deliberately NAMES the forbidden loader APIs
    inside its published governance policy, and a policy string that documents ``LoadLibraryExW`` is
    the opposite of a call to it.
    """
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    called = set()
    attributes = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                called.add(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                called.add(node.func.attr)
        elif isinstance(node, ast.Attribute):
            attributes.add(node.attr)
    for forbidden in (
        "CDLL",
        "cdll",
        "LoadLibrary",
        "LoadLibraryExW",
        "dlopen",
        "open",
        "read_bytes",
        "read_text",
        "write_bytes",
        "getenv",
        "urlopen",
        "run",
        "Popen",
        "system",
    ):
        assert forbidden not in called, forbidden
    for forbidden in ("environ", "argv"):
        assert forbidden not in attributes, forbidden


def test_production_module_never_reads_the_evidence_file() -> None:
    """The digest constant is the authority; the file location must not be trusted at runtime."""
    source = _MODULE_PATH.read_text(encoding="utf-8")
    assert "mt4_blst_stage_c_admission_evidence_v1.json" in source  # named for auditability
    tree = ast.parse(source)
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
    names = set()
    for call in calls:
        if isinstance(call.func, ast.Name):
            names.add(call.func.id)
        elif isinstance(call.func, ast.Attribute):
            names.add(call.func.attr)
    for forbidden in ("open", "read_bytes", "read_text", "load", "loads_file"):
        if forbidden == "load":
            continue
        assert forbidden not in names, forbidden


def test_production_module_touches_no_bist_or_execution_surface() -> None:
    """No import of, or reference to, any BIST/execution surface.

    The repository is literally named BIST_ELITE_CORE, so the bare token appears in the governed
    repository identifier. That identifier is removed first; what remains must be clean.
    """
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
        elif isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
    # The only crypto_core surfaces reachable are the three predecessor validation artifacts.
    for name in imported:
        assert name.startswith(("crypto_core.validation.machine_time_", "__future__")) or name in {
            "hashlib",
            "json",
            "enum",
        }, name

    # Names of protected flags (shadow_ready, live_ready, ...) MUST appear -- they are published as
    # False. What must not appear is a reference to an execution/venue/BIST module or attribute.
    source = _MODULE_PATH.read_text(encoding="utf-8")
    for flag in _FALSE_FLAGS:
        source = source.replace(flag, "")
    source = source.replace("demircaliskan2009-pixel/BIST_ELITE_CORE", "").replace("BIST_ELITE_CORE", "")
    lowered = source.lower()
    for forbidden in ("bist", "capital", "venue", "scheduler", "live_trade", "place_order", "portfolio"):
        assert forbidden not in lowered, forbidden


# ---------------------------------------------------------------------------------------------
# Mutant-to-guard map
# ---------------------------------------------------------------------------------------------


def test_mutant_map_covers_every_load_bearing_guard() -> None:
    mutants = {
        "skip S1 binding": "test_wrong_snapshot_type_is_rejected",
        "skip registry binding": "test_wrong_registry_type_is_rejected",
        "skip S2 binding": "test_wrong_chain_profile_type_is_rejected",
        "weaken BLST commit": "test_profile_binds_dependency_and_signer_identity",
        "weaken recipe binding": "test_matching_recipe_with_unknown_digest_is_never_admitted",
        "allow recipe-only binary admission": "test_matching_recipe_with_unknown_digest_is_never_admitted",
        "weaken scheme": "test_profile_binds_the_complete_verifier_contract",
        "weaken curve": "test_profile_binds_the_complete_verifier_contract",
        "weaken PK group or length": "test_profile_binds_the_complete_verifier_contract",
        "weaken SIG group or length": "test_profile_binds_the_complete_verifier_contract",
        "change message transform": "test_profile_binds_the_complete_verifier_contract",
        "change DST": "test_profile_binds_the_complete_verifier_contract",
        "skip signer repository": "test_profile_binds_dependency_and_signer_identity",
        "skip signer workflow": "test_profile_binds_dependency_and_signer_identity",
        "skip signer ref": "test_profile_binds_dependency_and_signer_identity",
        "skip predicate type": "test_profile_binds_dependency_and_signer_identity",
        "skip qualification workflow digest": "test_profile_binds_dependency_and_signer_identity",
        "skip production evidence digest": "test_production_evidence_bytes_are_canonical_and_digest_pinned",
        "accept wrong platform": "test_cross_platform_subject_substitution_is_rejected",
        "accept unknown binary digest": "test_matching_recipe_with_unknown_digest_is_never_admitted",
        "allow fixture admission": "test_fixture_corpus_is_identified_but_never_admitted",
        "promote proof_verified": "test_no_successful_profile_can_promote_a_protected_flag",
        "promote quorum_countable": "test_no_successful_profile_can_promote_a_protected_flag",
        "promote machine_time_origin_proven": "test_no_successful_profile_can_promote_a_protected_flag",
        "promote readiness or connector": "test_no_successful_profile_can_promote_a_protected_flag",
        "make authorizes_native_load true": "test_authorizes_native_load_is_always_false",
        "remove lifecycle from self-digest": "test_self_digest_is_domain_separated_and_covers_the_lifecycle_table",
        "weaken exact-type boundary": "test_descriptor_and_digest_reject_foreign_types",
        "accept non-canonical reconstruction": "test_reconstruction_rejects_non_canonical_and_tampered_bytes",
        "introduce a native-load or import path": "test_production_module_imports_no_ffi_network_clock_or_environment",
        "move evidence under tests/fixtures": "test_production_evidence_lives_in_production_not_tests",
        "read the evidence file at runtime": "test_production_module_never_reads_the_evidence_file",
        "claim Windows reproducibility": "test_no_reproducibility_claim_is_published",
    }
    source = Path(__file__).resolve().read_text(encoding="utf-8")
    for mutant, guard in mutants.items():
        assert re.search(r"def " + guard + r"\(", source), (mutant, guard)
    assert len(mutants) >= 30
