"""Governed MT4-S3B Drand Quicknet verifier-profile admission.

This is the slice that turns Stage-C EVIDENCE into a GOVERNED DECISION.  It binds one exact S1
``MachineTimeSourceTrustSnapshot``, one structurally READY MT-3 ``MachineTimeSourceRegistry``, and one
exact S2 ``MachineTimeDrandQuicknetChainProfile``, and publishes the governed selection of the blst
v0.3.17 backend and the Drand Quicknet verifier contract.

WHAT A SUCCESSFUL PROFILE MEANS.  Exactly four selections have been governed: the dependency profile
is admitted, the cryptographic backend is selected, the verifier profile is selected, and the message
encoding profile is selected.  Nothing else.  It does NOT mean a binary exists, is installed, is
loadable or has been loaded; it does NOT mean the source is reachable, the provider is approved, a
proof is verified, a quorum exists, machine time or a timestamp origin is proven, or that readiness or
a connector has been promoted.  Every one of those stays structurally False.

RECIPE NON-TRANSITIVITY (the core rule).  A build-recipe digest classifies governed evidence; it never
authorizes a binary.  Two binaries produced by the identical recipe are still two different governed
decisions, because the recipe does not bind the whole build execution environment.  ``same recipe +
unknown digest`` therefore resolves to NOT ADMITTED, structurally, with no "recipe-compatible" path.
Windows proves why this matters: three qualification runs of unchanged source produced three different
digests, so no Windows bit-for-bit reproducibility is claimed anywhere here.

DURABLE AUTHORITY.  The Stage-C cryptographic evidence lives in a production-owned committed artifact,
``evidence/mt4_blst_stage_c_admission_evidence_v1.json``, which embeds both offline-verified Sigstore
bundles and the trusted-root material used to re-prove them.  The governance binding is the expected
digest constant below, NOT the file's location: this module never opens that file, so no filesystem
path can influence a protected decision.  Tests own the equality between the committed bytes and the
constant.

NO NATIVE LOADING.  This module imports no FFI, opens no binary and hashes nothing from disk.  The
digest policy is POLICY ONLY and always reports ``authorizes_native_load=False``; only a future
race-safe loader slice may create load-bound authority, under the contract published here.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum

from crypto_core.validation.machine_time_drand_quicknet_chain_profile import (
    MachineTimeDrandQuicknetChainProfile,
    MachineTimeDrandQuicknetChainProfileError,
    machine_time_drand_quicknet_chain_profile_commitment_descriptor,
    machine_time_drand_quicknet_chain_profile_self_digest,
)
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

MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_SCHEMA = "machine-time-drand-quicknet-verifier-profile.v1"
MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_ID = "drand-quicknet-bls-g1-verifier-blst-v0317-offline.v1"

# Governance binding to the committed production Stage-C evidence artifact.  The artifact is durable
# audit evidence; THIS constant is the authority.  Nothing here reads the file.
MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256 = "0df341f9d5bbdb06ebe64822623814b018f5cf5b0b36c28b0eadc70d85bcec2f"

MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_RELATIVE_PATH = (
    "src/crypto_core/validation/evidence/mt4_blst_stage_c_admission_evidence_v1.json"
)

__all__ = (
    "MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_SCHEMA",
    "MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_ID",
    "MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256",
    "MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_RELATIVE_PATH",
    "MachineTimeDrandQuicknetVerifierProfile",
    "MachineTimeDrandQuicknetVerifierProfileError",
    "MachineTimeDrandQuicknetVerifierProfileReason",
    "MachineTimeDrandQuicknetBinaryDigestDecision",
    "MachineTimeDrandQuicknetBinaryDigestReason",
    "MachineTimeDrandQuicknetInstanceStatus",
    "build_machine_time_drand_quicknet_verifier_profile",
    "machine_time_drand_quicknet_verifier_profile_commitment_descriptor",
    "machine_time_drand_quicknet_verifier_profile_self_digest",
    "machine_time_drand_quicknet_verifier_profile_canonical_bytes",
    "reconstruct_machine_time_drand_quicknet_verifier_profile",
    "evaluate_machine_time_drand_quicknet_binary_digest",
)

_PROFILE_DIGEST_DOMAIN = b"machine-time-drand-quicknet-verifier-profile.v1/self-digest\x00"
_HEX_CHARS = frozenset("0123456789abcdef")
_MAX_CANONICAL_BYTES = 1 << 20
_MAX_REPR_CHARS = 512
_SEALED_MESSAGE = "MachineTimeDrandQuicknetVerifierProfile is sealed and cannot be subclassed"
_DIRECT_CONSTRUCTION_MESSAGE = "use build_machine_time_drand_quicknet_verifier_profile"
_IMMUTABLE_MESSAGE = "MachineTimeDrandQuicknetVerifierProfile is immutable"
_ERROR_CONSTRUCTION_MESSAGE = "reason must be an exact MachineTimeDrandQuicknetVerifierProfileReason"
_ERROR_IMMUTABLE_MESSAGE = "MachineTimeDrandQuicknetVerifierProfileError is immutable"
_ERROR_IMMUTABLE_ATTRS = frozenset({"_reason", "reason", "args", "_sealed"})
_DECISION_IMMUTABLE_MESSAGE = "MachineTimeDrandQuicknetBinaryDigestDecision is immutable"

# ---------------------------------------------------------------------------------------------
# Governed source / S1 row
# ---------------------------------------------------------------------------------------------
_SOURCE_ID = "drand-quicknet-mainnet"
_PROVIDER_ID = "league-of-entropy"
_SOURCE_CLASS = "distributed-threshold-randomness-beacon"
_RECOMMENDED_ROLE = "not_before"
_PROTOCOL_PROFILE_ID = "drand-quicknet-signature-and-chain-info-offline.v1"
_WIRE_PROFILE_ID = "drand-http-api-v2-with-chain-info"
_INDEPENDENCE_CLASS = "threshold-bls-beacon"
_DEPENDENCY_PROFILE_ID = "D-DEP-02"
_FIXTURE_CORPUS_ID = "FX-DRAND-QUICKNET.v1"
_VERIFICATION_POLICY_ID = "deterministic_supplied_proof_verification_no_network.v1"

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
_SNAPSHOT_FALSE_FIELDS = (
    "operational_use_approved",
    "quorum_countable",
    "source_reachable_proven",
    "proof_verified",
)
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

# ---------------------------------------------------------------------------------------------
# Governed verifier contract.  S3A/Stage-C evidence is what permits the facts S2 deferred.
# ---------------------------------------------------------------------------------------------
_BEACON_ID = "quicknet"
_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"
_CURVE = "BLS12-381"
_SCHEME = "bls-unchained-g1-rfc9380"
_PUBLIC_KEY_GROUP = "G2"
_SIGNATURE_GROUP = "G1"
_PUBLIC_KEY_ENCODED_LENGTH = 96
_SIGNATURE_ENCODED_LENGTH = 48
_MESSAGE_TRANSFORM = "SHA256(uint64_big_endian(round))"
_MESSAGE_LENGTH = 32
_DST = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
_AUGMENTATION = "NONE"

_ABI_STATUS_TAXONOMY = (
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
)

# ---------------------------------------------------------------------------------------------
# Governed dependency identity
# ---------------------------------------------------------------------------------------------
_UPSTREAM_REPOSITORY = "https://github.com/supranational/blst"
_UPSTREAM_RELEASE = "v0.3.17"
_UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
_UPSTREAM_SOURCE_TREE_DIGEST = "5a709c19ef7a1b9798ad58728fc5dd3b4d2026ecdd0342ebf8546c5950cea006"
_UPSTREAM_LICENSE = "Apache-2.0"

_QUALIFICATION_REPOSITORY = "demircaliskan2009-pixel/BIST_ELITE_CORE"
_QUALIFICATION_EVENT = "workflow_dispatch"
_QUALIFICATION_BRANCH = "main"
_QUALIFICATION_HEAD_SHA = "56b82260b69f2ea4e011438256d6996d77348c4e"
_QUALIFICATION_WORKFLOW_PATH = ".github/workflows/crypto_core_mt4_s3a_blst_qualification.yml"
_QUALIFICATION_WORKFLOW_SHA256 = "45d0f8dba660af516a2e92e7f8579a22da61a731d9948a61c9298878160e89c3"

_SIGNER_REPOSITORY = "demircaliskan2009-pixel/BIST_ELITE_CORE"
_SIGNER_WORKFLOW_PATH = ".github/workflows/crypto_core_mt4_trusted_attestation.yml"
_SIGNER_REF = "refs/heads/main"
_OIDC_ISSUER = "https://token.actions.githubusercontent.com"
_CUSTOM_PREDICATE_TYPE = (
    "https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/attestations/crypto-core/mt4-blst-admission-evidence/v1"
)
_TRUSTED_ROOT_SHA256 = "65ca537f6ed8a47fd0e560c421baa1f6c1efb8b25fc200d8c5c02c0e92eb2b9c"


class MachineTimeDrandQuicknetInstanceStatus(str, Enum):
    """Governed lifecycle of one enumerated native-binary instance.

    Absence from the table is NEVER_ADMITTED and is deliberately not a member here: an unknown digest
    must not be representable as a lifecycle value.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    REVOKED = "revoked"


# Enumerated governed instances.  Each entry is one separately governed decision; adding a row is a
# reviewed governance change, never an inference from a matching recipe.
_INSTANCES = (
    {
        "instance_id": "mt4-blst-v0317-linux-x64.1",
        "platform_id": "linux-x64",
        "target_identity": "x86_64-unknown-linux-gnu",
        "binary_name": "libmt4_s3a_blst_quicknet_shim.so",
        "binary_sha256": "366d17c18db8dda0112b9a155ffbbb17e558654f0aed22da9748b5ab07f5b867",
        "manifest_sha256": "14b6f426ba0b08e4355d2b31fef78ba22ed3fdbf865011cb32702cda26db9d73",
        "qualification_receipt_sha256": "3ec4d7250117323035330443d272b2b82f9f22b748e9f758408946d71b9a7e1a",
        "build_recipe_sha256": "2c1fb9c45881ab76a91c524dba779092a0801978228ce13ede451fd9260ea896",
        "attestation_bundle_sha256": "eb8e35d52f1276fc63946fe0b29dfab33ef16f7dd08353e5fbf5ef114332d337",
        # Checkout-normalised digests: git rewrites LF to CRLF on the Windows checkout, so the same
        # logical source hashes differently per platform.  Never treat these as content digests.
        "upstream_license_sha256": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
        "shim_source_sha256": "87e38a708682aa58c5e01aa8ab72721d25289e5b49fe71f2999ce0de28214932",
        "portable_mode": "PORTABLE",
        "status": MachineTimeDrandQuicknetInstanceStatus.ACTIVE.value,
    },
    {
        "instance_id": "mt4-blst-v0317-windows-x64.1",
        "platform_id": "windows-x64",
        "target_identity": "x86_64-pc-windows-msvc",
        "binary_name": "mt4_s3a_blst_quicknet_shim.dll",
        "binary_sha256": "d18ccbe99f4bdff6d2f1314b38c3a63231aea7287df278a864e77c1cc9afb362",
        "manifest_sha256": "09484f268ad31c83d52870ba85c5dfe556d231604cd160156020c524f596ea9b",
        "qualification_receipt_sha256": "1dc0a293e523dd084ee255023e29fab0ebc83e831b4c76848d9a51bce3dc2f95",
        "build_recipe_sha256": "cd229ba172779bcad1285189a75aeda233d5ad1d7a108998c15951a8a53faae7",
        "attestation_bundle_sha256": "03222bee6e610049c5bd34b83dee210c0a66e6794cc3eb395a47fc414d134c05",
        "upstream_license_sha256": "1eb85fc97224598dad1852b5d6483bbcf0aa8608790dcc657a5a2a761ae9c8c6",
        "shim_source_sha256": "7255e343984ba3b4bb4f399cdeb68855833acddea51b37aceb977aad3360ee17",
        "portable_mode": "PORTABLE",
        "status": MachineTimeDrandQuicknetInstanceStatus.ACTIVE.value,
    },
)
_SUPPORTED_PLATFORMS = ("linux-x64", "windows-x64")

# Mandatory future-loader contract.  Published as governed policy so the deferral is machine-readable
# rather than prose.  The forbidden pattern is named explicitly because it is the exact defect the
# independent audit identified: hashing a path and then loading that path is two different objects.
_NATIVE_LOAD_POLICY = {
    "policy_id": "mt4-blst-native-load-policy.v1",
    "implemented_here": False,
    "authorizes_native_load": False,
    "forbidden_pattern": "hash(path) then load(path)",
    "bytes_hashed_must_be_bytes_mapped": True,
    "requirements": (
        "derive OS and architecture internally, never from a caller string",
        "open the candidate without symlink or reparse-point substitution",
        "require a bounded regular native file",
        "hash from that exact held handle or object",
        "copy verified bytes to an exclusively created process-private target, "
        "or hold an equivalently protected immutable object",
        "re-prove digest and file identity while preventing write and delete races",
        "load only that protected verified object while protection is still held",
        "use restricted dependency search",
        "validate format, architecture, required exports, import/DT_NEEDED allowlist "
        "and unsafe RPATH/RUNPATH search behaviour",
        "fail closed on any path, identity, digest, metadata, dependency or post-load mismatch",
    ),
    "linux_architecture_class": "sealed memfd or equivalently protected held inode",
    "windows_architecture_class": (
        "CREATE_NEW with private ACL and no write/delete sharing, LoadLibraryExW restricted search, "
        "file-id and digest reproof"
    ),
}

# Exactly the four selections S3B may govern.
_TRUE_GOVERNANCE_FLAGS = (
    "dependency_profile_admitted",
    "cryptographic_backend_selected",
    "mt4_verifier_profile_selected",
    "message_encoding_profile_selected",
)

# Everything a successful profile must still publish as exactly False.
_FALSE_GOVERNANCE_FLAGS = (
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

_DESCRIPTOR_FIELD_NAMES = (
    "profile_schema",
    "profile_id",
    "architecture_id",
    "source_id",
    "beacon_id",
    "chain_hash",
    "curve",
    "scheme",
    "public_key_group",
    "signature_group",
    "public_key_encoded_length",
    "signature_encoded_length",
    "message_transform",
    "message_length",
    "dst",
    "augmentation",
    "canonical_compressed_encoding_required",
    "recompression_equality_required",
    "public_key_infinity_policy",
    "signature_infinity_policy",
    "public_key_subgroup_policy",
    "signature_subgroup_policy",
    "abi_status_taxonomy",
    "verification_policy_id",
    "dependency_profile_id",
    "fixture_corpus_id",
    "upstream_repository",
    "upstream_release",
    "upstream_commit",
    "upstream_source_tree_digest",
    "upstream_license",
    "qualification_repository",
    "qualification_event",
    "qualification_branch",
    "qualification_head_sha",
    "qualification_workflow_path",
    "qualification_workflow_sha256",
    "signer_repository",
    "signer_workflow_path",
    "signer_ref",
    "oidc_issuer",
    "custom_predicate_type",
    "trusted_root_sha256",
    "stage_c_evidence_sha256",
    "stage_c_evidence_relative_path",
    "supported_platform_ids",
    "admitted_instances",
    "recipe_digest_authorizes_binary",
    "windows_bit_reproducibility_claimed",
    "linux_bit_reproducibility_required",
    "native_load_policy",
    "bound_snapshot_id",
    "bound_snapshot_self_digest",
    "bound_registry_digest",
    "bound_registry_source_entry_digest",
    "bound_chain_profile_id",
    "bound_chain_profile_self_digest",
    *_TRUE_GOVERNANCE_FLAGS,
    *_FALSE_GOVERNANCE_FLAGS,
)
_FIELD_NAMES = (*_DESCRIPTOR_FIELD_NAMES, "profile_self_digest")


class MachineTimeDrandQuicknetVerifierProfileReason(str, Enum):
    """Closed construction-failure inventory with deterministic precedence."""

    WRONG_INPUT_TYPE = "wrong_input_type"
    FIELD_INVENTORY_INVALID = "field_inventory_invalid"
    FIELD_TYPE_INVALID = "field_type_invalid"
    CANONICAL_TEXT_INVALID = "canonical_text_invalid"
    RESOURCE_BOUND_EXCEEDED = "resource_bound_exceeded"
    SNAPSHOT_BINDING_INVALID = "snapshot_binding_invalid"
    REGISTRY_BINDING_INVALID = "registry_binding_invalid"
    CHAIN_PROFILE_BINDING_INVALID = "chain_profile_binding_invalid"
    GOVERNANCE_EVIDENCE_BINDING_INVALID = "governance_evidence_binding_invalid"
    DEPENDENCY_IDENTITY_MISMATCH = "dependency_identity_mismatch"
    VERIFIER_CONTRACT_MISMATCH = "verifier_contract_mismatch"
    GOVERNANCE_STRUCTURAL_VIOLATION = "governance_structural_violation"
    SELF_DIGEST_INVALID = "self_digest_invalid"
    SELF_DIGEST_MISMATCH = "self_digest_mismatch"
    RECONSTRUCTION_INPUT_INVALID = "reconstruction_input_invalid"
    ARTIFACT_INCONSISTENT = "artifact_inconsistent"


class MachineTimeDrandQuicknetBinaryDigestReason(str, Enum):
    """Closed digest-policy outcome inventory.  Never a bare boolean."""

    ACCEPTED_ACTIVE_INSTANCE = "accepted_active_instance"
    PROFILE_REVOKED = "profile_revoked"
    PLATFORM_UNSUPPORTED = "platform_unsupported"
    BINARY_DIGEST_INVALID = "binary_digest_invalid"
    BINARY_INSTANCE_NOT_ADMITTED = "binary_instance_not_admitted"
    BINARY_INSTANCE_SUPERSEDED = "binary_instance_superseded"
    BINARY_INSTANCE_REVOKED = "binary_instance_revoked"


class MachineTimeDrandQuicknetVerifierProfileError(RuntimeError):
    """Closed diagnostic carrying one exact reason and no caller-controlled message."""

    __slots__ = ("_reason", "_sealed")

    def __init__(self, reason: MachineTimeDrandQuicknetVerifierProfileReason) -> None:
        if type(reason) is not MachineTimeDrandQuicknetVerifierProfileReason:
            raise TypeError(_ERROR_CONSTRUCTION_MESSAGE)
        RuntimeError.__init__(self, reason.value)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_sealed", True)

    @property
    def reason(self) -> MachineTimeDrandQuicknetVerifierProfileReason:
        return self._reason

    def __setattr__(self, name: str, value: object) -> None:
        if name in _ERROR_IMMUTABLE_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        object.__setattr__(self, name, value)

    def __delattr__(self, name: str) -> None:
        if name in _ERROR_IMMUTABLE_ATTRS:
            raise AttributeError(_ERROR_IMMUTABLE_MESSAGE)
        object.__delattr__(self, name)


def _err(
    reason: MachineTimeDrandQuicknetVerifierProfileReason,
) -> MachineTimeDrandQuicknetVerifierProfileError:
    return MachineTimeDrandQuicknetVerifierProfileError(reason)


class MachineTimeDrandQuicknetBinaryDigestDecision:
    """Structured, immutable digest-policy outcome.

    ``authorizes_native_load`` is always False in this slice; it exists so the deferral of native
    loading is mechanically explicit rather than a documentation promise.
    """

    __slots__ = ("_accepted", "_reason", "_matched_instance_id", "_platform_id", "_profile_self_digest")

    def __init__(
        self,
        *,
        accepted: bool,
        reason: MachineTimeDrandQuicknetBinaryDigestReason,
        matched_instance_id: object,
        platform_id: object,
        profile_self_digest: str,
    ) -> None:
        if type(accepted) is not bool or type(reason) is not MachineTimeDrandQuicknetBinaryDigestReason:
            raise TypeError(_DECISION_IMMUTABLE_MESSAGE)
        object.__setattr__(self, "_accepted", accepted)
        object.__setattr__(self, "_reason", reason)
        object.__setattr__(self, "_matched_instance_id", matched_instance_id)
        object.__setattr__(self, "_platform_id", platform_id)
        object.__setattr__(self, "_profile_self_digest", profile_self_digest)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(_DECISION_IMMUTABLE_MESSAGE)

    @property
    def accepted(self) -> bool:
        return self._accepted

    @property
    def reason(self) -> MachineTimeDrandQuicknetBinaryDigestReason:
        return self._reason

    @property
    def matched_instance_id(self) -> object:
        return self._matched_instance_id

    @property
    def platform_id(self) -> object:
        return self._platform_id

    @property
    def profile_self_digest(self) -> str:
        return self._profile_self_digest

    @property
    def authorizes_native_load(self) -> bool:
        """Always False in S3B.  Acceptance is a policy statement, never load authority."""
        return False

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(_DECISION_IMMUTABLE_MESSAGE)

    def __delattr__(self, name: str) -> None:
        raise AttributeError(_DECISION_IMMUTABLE_MESSAGE)

    def __repr__(self) -> str:
        return (
            "MachineTimeDrandQuicknetBinaryDigestDecision("
            f"accepted={self._accepted}, reason={self._reason.value}, "
            f"matched_instance_id={self._matched_instance_id!r}, "
            f"platform_id={self._platform_id!r}, authorizes_native_load=False)"
        )


def _is_hex64(value: object) -> bool:
    return type(value) is str and len(value) == 64 and all(char in _HEX_CHARS for char in value)


def _is_hex40(value: object) -> bool:
    return type(value) is str and len(value) == 40 and all(char in _HEX_CHARS for char in value)


def _canonical_text(payload: object) -> str:
    try:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    except (TypeError, ValueError):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.ARTIFACT_INCONSISTENT) from None


def _jsonable(value: object) -> object:
    if type(value) is tuple:
        return [_jsonable(item) for item in value]
    if type(value) is dict:
        return {key: _jsonable(item) for key, item in value.items()}
    return value


def _snapshot_binding(snapshot: object) -> dict:
    """Bind S1 through its own public fail-closed boundary; re-prove current content."""
    if type(snapshot) is not MachineTimeSourceTrustSnapshot:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    fields = (
        *_SNAPSHOT_ROW_FIELDS,
        *_SNAPSHOT_FALSE_FIELDS,
        "snapshot_id",
        "snapshot_self_digest",
        "trust_material_bytes",
        "trust_material_fingerprint",
    )
    try:
        read = {name: getattr(snapshot, name) for name in fields}
    except MachineTimeSourceTrustSnapshotError:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID) from None

    if tuple(read[name] for name in _SNAPSHOT_ROW_FIELDS) != _SNAPSHOT_ROW:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    if any(read[name] is not False for name in _SNAPSHOT_FALSE_FIELDS):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    if not _is_hex64(read["snapshot_self_digest"]) or not _is_hex64(read["trust_material_fingerprint"]):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    if type(read["snapshot_id"]) is not str or not read["snapshot_id"]:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    material = read["trust_material_bytes"]
    if type(material) is not bytes or len(material) != _PUBLIC_KEY_ENCODED_LENGTH:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    if hashlib.sha256(material).hexdigest() != read["trust_material_fingerprint"]:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SNAPSHOT_BINDING_INVALID)
    return {
        "snapshot_id": read["snapshot_id"],
        "snapshot_self_digest": read["snapshot_self_digest"],
        "trust_material_bytes": material,
    }


def _registry_binding(registry: object) -> dict:
    """Recompute the MT-3 digest through the public serializer and bind the exact Drand record."""
    if type(registry) is not MachineTimeSourceRegistry:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    try:
        payload = machine_time_source_registry_to_dict(registry)
        recomputed = machine_time_source_registry_digest(registry)
    except MachineTimeSourceRegistryError:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID) from None

    if not _is_hex64(payload["registry_digest"]) or payload["registry_digest"] != recomputed:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    if payload["status"] != MachineTimeSourceRegistryStatus.REGISTRY_READY.value or payload["ready"] is not True:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    if any(payload[name] is not False for name in _REGISTRY_FALSE_FIELDS):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)

    matches = tuple(record for record in payload["sources"] if record["source_id"] == _SOURCE_ID)
    if len(matches) != 1:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    record = matches[0]
    if record["provider_id"] != _PROVIDER_ID or record["recommended_role"] != _RECOMMENDED_ROLE:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    if not _is_hex64(record["entry_digest"]):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)

    facts = {}
    for item in record["fact_items"]:
        if type(item) is not list or len(item) != 2 or type(item[0]) is not str:
            raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
        facts[item[0]] = item[1]
    if facts.get("chain_hash") != _CHAIN_HASH or facts.get("scheme") != _SCHEME:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.REGISTRY_BINDING_INVALID)
    return {"registry_digest": payload["registry_digest"], "entry_digest": record["entry_digest"]}


def _chain_profile_binding(chain_profile: object, trust_material: bytes) -> dict:
    """Bind the exact current S2 artifact and re-prove its own commitment."""
    if type(chain_profile) is not MachineTimeDrandQuicknetChainProfile:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    try:
        descriptor = machine_time_drand_quicknet_chain_profile_commitment_descriptor(chain_profile)
        self_digest = machine_time_drand_quicknet_chain_profile_self_digest(chain_profile)
    except MachineTimeDrandQuicknetChainProfileError:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID) from None

    if not _is_hex64(self_digest):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("source_id") != _SOURCE_ID or descriptor.get("chain_hash") != _CHAIN_HASH:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("scheme_id") != _SCHEME or descriptor.get("provider_id") != _PROVIDER_ID:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("dependency_profile_id") != _DEPENDENCY_PROFILE_ID:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("fixture_corpus_id") != _FIXTURE_CORPUS_ID:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("verification_policy_id") != _VERIFICATION_POLICY_ID:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("public_key_encoded_length") != _PUBLIC_KEY_ENCODED_LENGTH:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    # S2 published the key fingerprint; the same trust material must be behind both artifacts.
    if descriptor.get("public_key_fingerprint") != hashlib.sha256(trust_material).hexdigest():
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    # S2 must still be publishing its own non-claims; S3B may not build on a promoted S2.
    if descriptor.get("dependency_profile_admitted") is not False:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    if descriptor.get("proof_verified") is not False:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CHAIN_PROFILE_BINDING_INVALID)
    return {"chain_profile_id": descriptor.get("profile_id"), "chain_profile_self_digest": self_digest}


def _governance_evidence_binding() -> dict:
    """Prove the governed Stage-C evidence identity is internally consistent.

    The digest constant IS the authority.  No file is opened, so no filesystem location can influence
    this decision; committed-bytes equality is owned by the permanent tests.
    """
    if not _is_hex64(MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    if not _is_hex64(_TRUSTED_ROOT_SHA256):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    if not _is_hex64(_QUALIFICATION_WORKFLOW_SHA256) or not _is_hex40(_QUALIFICATION_HEAD_SHA):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    if _SIGNER_WORKFLOW_PATH == _QUALIFICATION_WORKFLOW_PATH:
        # The unprivileged qualification workflow may never be accepted as the signer.
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    if _SIGNER_REF != "refs/heads/main" or not _CUSTOM_PREDICATE_TYPE.endswith("/mt4-blst-admission-evidence/v1"):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    if "slsa.dev" in _CUSTOM_PREDICATE_TYPE:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_EVIDENCE_BINDING_INVALID)
    return {"stage_c_evidence_sha256": MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_SHA256}


def _dependency_identity_binding() -> None:
    if not _is_hex40(_UPSTREAM_COMMIT) or not _is_hex64(_UPSTREAM_SOURCE_TREE_DIGEST):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
    if _UPSTREAM_REPOSITORY != "https://github.com/supranational/blst" or _UPSTREAM_RELEASE != "v0.3.17":
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
    seen_ids = set()
    seen_digests = set()
    for instance in _INSTANCES:
        if instance["platform_id"] not in _SUPPORTED_PLATFORMS:
            raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
        for key in (
            "binary_sha256",
            "manifest_sha256",
            "qualification_receipt_sha256",
            "build_recipe_sha256",
            "attestation_bundle_sha256",
            "upstream_license_sha256",
            "shim_source_sha256",
        ):
            if not _is_hex64(instance[key]):
                raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
        if instance["instance_id"] in seen_ids or instance["binary_sha256"] in seen_digests:
            raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
        if instance["status"] not in tuple(item.value for item in MachineTimeDrandQuicknetInstanceStatus):
            raise _err(MachineTimeDrandQuicknetVerifierProfileReason.DEPENDENCY_IDENTITY_MISMATCH)
        seen_ids.add(instance["instance_id"])
        seen_digests.add(instance["binary_sha256"])


def _verifier_contract_binding() -> None:
    if _PUBLIC_KEY_GROUP != "G2" or _SIGNATURE_GROUP != "G1" or _CURVE != "BLS12-381":
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.VERIFIER_CONTRACT_MISMATCH)
    if _PUBLIC_KEY_ENCODED_LENGTH != 96 or _SIGNATURE_ENCODED_LENGTH != 48 or _MESSAGE_LENGTH != 32:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.VERIFIER_CONTRACT_MISMATCH)
    if _AUGMENTATION != "NONE" or not _DST.startswith("BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_"):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.VERIFIER_CONTRACT_MISMATCH)
    if tuple(code for code, _name in _ABI_STATUS_TAXONOMY) != tuple(range(12)):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.VERIFIER_CONTRACT_MISMATCH)


def _derive_values(snapshot: object, registry: object, chain_profile: object) -> tuple:
    """Single derivation of every published value; re-run on every public read."""
    bound_snapshot = _snapshot_binding(snapshot)
    bound_registry = _registry_binding(registry)
    bound_chain = _chain_profile_binding(chain_profile, bound_snapshot["trust_material_bytes"])
    evidence = _governance_evidence_binding()
    _dependency_identity_binding()
    _verifier_contract_binding()

    values = {
        "profile_schema": MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_SCHEMA,
        "profile_id": MACHINE_TIME_DRAND_QUICKNET_VERIFIER_PROFILE_ID,
        "architecture_id": "MT4-S3B-DRAND-QUICKNET-VERIFIER-PROFILE-CONTRACT-ADMISSION-V2",
        "source_id": _SOURCE_ID,
        "beacon_id": _BEACON_ID,
        "chain_hash": _CHAIN_HASH,
        "curve": _CURVE,
        "scheme": _SCHEME,
        "public_key_group": _PUBLIC_KEY_GROUP,
        "signature_group": _SIGNATURE_GROUP,
        "public_key_encoded_length": _PUBLIC_KEY_ENCODED_LENGTH,
        "signature_encoded_length": _SIGNATURE_ENCODED_LENGTH,
        "message_transform": _MESSAGE_TRANSFORM,
        "message_length": _MESSAGE_LENGTH,
        "dst": _DST,
        "augmentation": _AUGMENTATION,
        "canonical_compressed_encoding_required": True,
        "recompression_equality_required": True,
        "public_key_infinity_policy": "REJECT",
        "signature_infinity_policy": "REJECT",
        "public_key_subgroup_policy": "REQUIRED",
        "signature_subgroup_policy": "REQUIRED",
        "abi_status_taxonomy": _ABI_STATUS_TAXONOMY,
        "verification_policy_id": _VERIFICATION_POLICY_ID,
        "dependency_profile_id": _DEPENDENCY_PROFILE_ID,
        "fixture_corpus_id": _FIXTURE_CORPUS_ID,
        "upstream_repository": _UPSTREAM_REPOSITORY,
        "upstream_release": _UPSTREAM_RELEASE,
        "upstream_commit": _UPSTREAM_COMMIT,
        "upstream_source_tree_digest": _UPSTREAM_SOURCE_TREE_DIGEST,
        "upstream_license": _UPSTREAM_LICENSE,
        "qualification_repository": _QUALIFICATION_REPOSITORY,
        "qualification_event": _QUALIFICATION_EVENT,
        "qualification_branch": _QUALIFICATION_BRANCH,
        "qualification_head_sha": _QUALIFICATION_HEAD_SHA,
        "qualification_workflow_path": _QUALIFICATION_WORKFLOW_PATH,
        "qualification_workflow_sha256": _QUALIFICATION_WORKFLOW_SHA256,
        "signer_repository": _SIGNER_REPOSITORY,
        "signer_workflow_path": _SIGNER_WORKFLOW_PATH,
        "signer_ref": _SIGNER_REF,
        "oidc_issuer": _OIDC_ISSUER,
        "custom_predicate_type": _CUSTOM_PREDICATE_TYPE,
        "trusted_root_sha256": _TRUSTED_ROOT_SHA256,
        "stage_c_evidence_sha256": evidence["stage_c_evidence_sha256"],
        "stage_c_evidence_relative_path": MT4_BLST_STAGE_C_ADMISSION_EVIDENCE_RELATIVE_PATH,
        "supported_platform_ids": _SUPPORTED_PLATFORMS,
        "admitted_instances": _INSTANCES,
        # Structural, machine-readable statements of the two policies the audit demanded.
        "recipe_digest_authorizes_binary": False,
        "windows_bit_reproducibility_claimed": False,
        "linux_bit_reproducibility_required": False,
        "native_load_policy": _NATIVE_LOAD_POLICY,
        "bound_snapshot_id": bound_snapshot["snapshot_id"],
        "bound_snapshot_self_digest": bound_snapshot["snapshot_self_digest"],
        "bound_registry_digest": bound_registry["registry_digest"],
        "bound_registry_source_entry_digest": bound_registry["entry_digest"],
        "bound_chain_profile_id": bound_chain["chain_profile_id"],
        "bound_chain_profile_self_digest": bound_chain["chain_profile_self_digest"],
    }
    for name in _TRUE_GOVERNANCE_FLAGS:
        values[name] = True
    for name in _FALSE_GOVERNANCE_FLAGS:
        values[name] = False

    if any(values[name] is not True for name in _TRUE_GOVERNANCE_FLAGS):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if any(values[name] is not False for name in _FALSE_GOVERNANCE_FLAGS):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if values["recipe_digest_authorizes_binary"] is not False:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if values["windows_bit_reproducibility_claimed"] is not False:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if _NATIVE_LOAD_POLICY["authorizes_native_load"] is not False:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.GOVERNANCE_STRUCTURAL_VIOLATION)
    if tuple(values) != _DESCRIPTOR_FIELD_NAMES:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.ARTIFACT_INCONSISTENT)

    canonical = _canonical_text({name: _jsonable(values[name]) for name in _DESCRIPTOR_FIELD_NAMES})
    digest = hashlib.sha256(_PROFILE_DIGEST_DOMAIN + canonical.encode("utf-8")).hexdigest()
    return values, digest


class MachineTimeDrandQuicknetVerifierProfile:
    """Sealed governed S3B admission artifact.

    Existence of this artifact IS the selection: there is no second "closed" success state.  Every
    public read re-derives from the bound predecessors, so a predecessor tampered with after
    construction fails closed instead of being trusted from construction origin.
    """

    __slots__ = ("_snapshot", "_registry", "_chain_profile")
    __hash__ = None

    def __new__(cls, *args: object, **kwargs: object) -> MachineTimeDrandQuicknetVerifierProfile:
        raise TypeError(_DIRECT_CONSTRUCTION_MESSAGE)

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(_SEALED_MESSAGE)

    def __setattr__(self, name: str, value: object) -> None:
        raise AttributeError(_IMMUTABLE_MESSAGE)

    def __delattr__(self, name: str) -> None:
        raise AttributeError(_IMMUTABLE_MESSAGE)

    def _state(self) -> tuple:
        return _derive_values(
            object.__getattribute__(self, "_snapshot"),
            object.__getattribute__(self, "_registry"),
            object.__getattribute__(self, "_chain_profile"),
        )

    def __repr__(self) -> str:
        values, digest = self._state()
        rendered = (
            "MachineTimeDrandQuicknetVerifierProfile("
            f"profile_id={values['profile_id']}, "
            f"source_id={values['source_id']}, "
            f"scheme={values['scheme']}, "
            f"admitted_instances={len(values['admitted_instances'])}, "
            f"dependency_profile_admitted={values['dependency_profile_admitted']}, "
            f"proof_verified={values['proof_verified']}, "
            f"self_digest={digest})"
        )
        if not rendered.isascii() or len(rendered) > _MAX_REPR_CHARS:
            raise _err(MachineTimeDrandQuicknetVerifierProfileReason.ARTIFACT_INCONSISTENT)
        return rendered

    def __str__(self) -> str:
        return self.__repr__()

    def __bool__(self) -> bool:
        self._state()
        return True

    def __eq__(self, other: object) -> bool:
        self._state()
        if type(other) is not MachineTimeDrandQuicknetVerifierProfile:
            return False
        if self is other:
            return True
        return machine_time_drand_quicknet_verifier_profile_self_digest(
            self
        ) == machine_time_drand_quicknet_verifier_profile_self_digest(other)

    def __ne__(self, other: object) -> bool:
        return not self.__eq__(other)


def _make_property(name: str):
    def getter(self: MachineTimeDrandQuicknetVerifierProfile) -> object:
        values, digest = self._state()
        if name == "profile_self_digest":
            return digest
        return _jsonable(values[name])

    return property(getter)


for _name in _FIELD_NAMES:
    setattr(MachineTimeDrandQuicknetVerifierProfile, _name, _make_property(_name))


def build_machine_time_drand_quicknet_verifier_profile(
    *,
    snapshot: MachineTimeSourceTrustSnapshot,
    registry: MachineTimeSourceRegistry,
    chain_profile: MachineTimeDrandQuicknetChainProfile,
) -> MachineTimeDrandQuicknetVerifierProfile:
    """Govern the S3B admission.  No caller-supplied evidence mapping is accepted, by design."""
    _derive_values(snapshot, registry, chain_profile)
    artifact = object.__new__(MachineTimeDrandQuicknetVerifierProfile)
    object.__setattr__(artifact, "_snapshot", snapshot)
    object.__setattr__(artifact, "_registry", registry)
    object.__setattr__(artifact, "_chain_profile", chain_profile)
    return artifact


def machine_time_drand_quicknet_verifier_profile_commitment_descriptor(
    profile: MachineTimeDrandQuicknetVerifierProfile,
) -> dict:
    if type(profile) is not MachineTimeDrandQuicknetVerifierProfile:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.WRONG_INPUT_TYPE)
    values, _digest = profile._state()
    return {name: _jsonable(values[name]) for name in _DESCRIPTOR_FIELD_NAMES}


def machine_time_drand_quicknet_verifier_profile_self_digest(
    profile: MachineTimeDrandQuicknetVerifierProfile,
) -> str:
    if type(profile) is not MachineTimeDrandQuicknetVerifierProfile:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.WRONG_INPUT_TYPE)
    return profile._state()[1]


def machine_time_drand_quicknet_verifier_profile_canonical_bytes(
    profile: MachineTimeDrandQuicknetVerifierProfile,
) -> bytes:
    """Canonical serialization used for reconstruction; the digest is carried alongside."""
    if type(profile) is not MachineTimeDrandQuicknetVerifierProfile:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.WRONG_INPUT_TYPE)
    values, digest = profile._state()
    payload = {name: _jsonable(values[name]) for name in _DESCRIPTOR_FIELD_NAMES}
    payload["profile_self_digest"] = digest
    return _canonical_text(payload).encode("utf-8")


def reconstruct_machine_time_drand_quicknet_verifier_profile(
    canonical_bytes: bytes,
    *,
    snapshot: MachineTimeSourceTrustSnapshot,
    registry: MachineTimeSourceRegistry,
    chain_profile: MachineTimeDrandQuicknetChainProfile,
) -> MachineTimeDrandQuicknetVerifierProfile:
    """Reconstruct only from exact canonical bytes re-proven against current builder semantics."""
    if type(canonical_bytes) is not bytes:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.RECONSTRUCTION_INPUT_INVALID)
    if not canonical_bytes or len(canonical_bytes) > _MAX_CANONICAL_BYTES:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.RESOURCE_BOUND_EXCEEDED)
    try:
        text = canonical_bytes.decode("utf-8")
    except UnicodeDecodeError:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CANONICAL_TEXT_INVALID) from None
    try:
        parsed = json.loads(text)
    except ValueError:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.RECONSTRUCTION_INPUT_INVALID) from None
    if type(parsed) is not dict:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.RECONSTRUCTION_INPUT_INVALID)
    if tuple(sorted(parsed)) != tuple(sorted((*_DESCRIPTOR_FIELD_NAMES, "profile_self_digest"))):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.FIELD_INVENTORY_INVALID)
    # Canonical byte equality: a semantically equal but non-canonical encoding is rejected.
    if _canonical_text(parsed) != text:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.CANONICAL_TEXT_INVALID)

    carried = parsed["profile_self_digest"]
    if not _is_hex64(carried):
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SELF_DIGEST_INVALID)

    artifact = build_machine_time_drand_quicknet_verifier_profile(
        snapshot=snapshot, registry=registry, chain_profile=chain_profile
    )
    if machine_time_drand_quicknet_verifier_profile_self_digest(artifact) != carried:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SELF_DIGEST_MISMATCH)
    if machine_time_drand_quicknet_verifier_profile_canonical_bytes(artifact) != canonical_bytes:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.SELF_DIGEST_MISMATCH)
    return artifact


def evaluate_machine_time_drand_quicknet_binary_digest(
    profile: MachineTimeDrandQuicknetVerifierProfile,
    *,
    platform_id: object,
    binary_sha256: object,
) -> MachineTimeDrandQuicknetBinaryDigestDecision:
    """POLICY ONLY.  Never loads, never reads the filesystem, never inspects PATH.

    An unknown digest is NOT ADMITTED even when its recipe matches an admitted instance: the recipe
    classifies evidence, it does not confer authority.  Acceptance here is a governance statement and
    explicitly does not authorize a native load.
    """
    if type(profile) is not MachineTimeDrandQuicknetVerifierProfile:
        raise _err(MachineTimeDrandQuicknetVerifierProfileReason.WRONG_INPUT_TYPE)
    values, digest = profile._state()

    def decide(accepted: bool, reason: MachineTimeDrandQuicknetBinaryDigestReason, instance_id: object):
        return MachineTimeDrandQuicknetBinaryDigestDecision(
            accepted=accepted,
            reason=reason,
            matched_instance_id=instance_id,
            platform_id=platform_id if type(platform_id) is str else None,
            profile_self_digest=digest,
        )

    # Exact built-in type gate before any comparison, membership or projection.
    if type(platform_id) is not str or platform_id not in _SUPPORTED_PLATFORMS:
        return decide(False, MachineTimeDrandQuicknetBinaryDigestReason.PLATFORM_UNSUPPORTED, None)
    if not _is_hex64(binary_sha256):
        return decide(False, MachineTimeDrandQuicknetBinaryDigestReason.BINARY_DIGEST_INVALID, None)

    for instance in values["admitted_instances"]:
        if instance["binary_sha256"] != binary_sha256:
            continue
        # A digest admitted for another platform must never be accepted here.
        if instance["platform_id"] != platform_id:
            return decide(False, MachineTimeDrandQuicknetBinaryDigestReason.BINARY_INSTANCE_NOT_ADMITTED, None)
        status = instance["status"]
        if status == MachineTimeDrandQuicknetInstanceStatus.ACTIVE.value:
            return decide(
                True,
                MachineTimeDrandQuicknetBinaryDigestReason.ACCEPTED_ACTIVE_INSTANCE,
                instance["instance_id"],
            )
        if status == MachineTimeDrandQuicknetInstanceStatus.SUPERSEDED.value:
            return decide(
                False,
                MachineTimeDrandQuicknetBinaryDigestReason.BINARY_INSTANCE_SUPERSEDED,
                instance["instance_id"],
            )
        return decide(
            False,
            MachineTimeDrandQuicknetBinaryDigestReason.BINARY_INSTANCE_REVOKED,
            instance["instance_id"],
        )

    return decide(False, MachineTimeDrandQuicknetBinaryDigestReason.BINARY_INSTANCE_NOT_ADMITTED, None)
