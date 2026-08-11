"""Permanent offline contract tests for the MT4-S3A blst v0.3.17 qualification slice.

These tests never build, load or execute native code and never touch the network.  They own the
committed qualification contract by inspecting the six authorized files, so that removing a
subgroup gate, widening the ABI, admitting a dependency, promoting readiness or committing raw
production beacon bytes fails here rather than only in CI.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]

_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_s3a_blst_qualification.yml"
_SHIM_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_s3a_blst_quicknet_shim.c"
_PROBE_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_s3a_blst_quicknet_probe.py"
_MANIFEST_PATH = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "mt4_s3a_blst_v0317_qualification_v2.json"
_TEST_PATH = Path(__file__).resolve()
_DOC_PATH = _REPO_ROOT / "docs" / "crypto_core" / "mt4_s3a_blst_v0317_qualification.md"

_AUTHORIZED_FILES = (_WORKFLOW_PATH, _SHIM_PATH, _PROBE_PATH, _MANIFEST_PATH, _TEST_PATH, _DOC_PATH)

_UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
_UPSTREAM_RELEASE = "v0.3.17"
_QUICKNET_DST = "BLS_SIG_BLS12381G1_XMD:SHA-256_SSWU_RO_NUL_"
_QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"

_PROTECTED_FLAGS = (
    "dependency_profile_admitted",
    "fixture_corpus_admitted",
    "mt4_verifier_profile_selected",
    "proof_verified",
    "quorum_countable",
    "operational_quorum_ready",
    "machine_time_origin_proven",
    "timestamp_origin_proven",
    "readiness_promoted",
    "connector_promoted",
)

_STATUS_INVENTORY = {
    "0": "OK",
    "1": "NULL_INPUT",
    "2": "BAD_LENGTH",
    "3": "PK_BAD_ENCODING",
    "4": "PK_NON_CANONICAL",
    "5": "PK_INFINITY",
    "6": "PK_NOT_IN_GROUP",
    "7": "SIG_BAD_ENCODING",
    "8": "SIG_NON_CANONICAL",
    "9": "SIG_INFINITY",
    "10": "SIG_NOT_IN_GROUP",
    "11": "VERIFY_FAILED",
}

_STABLE_SYMBOLS = (
    "blst_p2_uncompress",
    "blst_p2_affine_in_g2",
    "blst_p2_affine_is_inf",
    "blst_p2_affine_compress",
    "blst_p1_uncompress",
    "blst_p1_affine_in_g1",
    "blst_p1_affine_is_inf",
    "blst_p1_affine_compress",
    "blst_core_verify_pk_in_g2",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _manifest() -> dict:
    return json.loads(_read(_MANIFEST_PATH))


def test_every_authorized_qualification_file_exists() -> None:
    for path in _AUTHORIZED_FILES:
        assert path.is_file(), path


def test_manifest_schema_upstream_pinning_and_license() -> None:
    manifest = _manifest()
    assert manifest["schema"] == "mt4-s3a-blst-qualification.v2"
    assert manifest["architecture_id"] == "MT4-S3A-BLST-V0317-NARROW-C-ABI-CTYPES-V2"
    assert manifest["status"] == "ARCHITECTURE_CANDIDATE"
    assert manifest["upstream_repository"] == "https://github.com/supranational/blst"
    assert manifest["upstream_release"] == _UPSTREAM_RELEASE
    assert manifest["upstream_commit"] == _UPSTREAM_COMMIT
    assert manifest["upstream_license"] == "Apache-2.0"
    # Historical V1 is referenced as immutable evidence, never rewritten.
    assert manifest["supersedes"] == "mt4-s3a-drand-quicknet-qualification.v1"


def test_manifest_pins_exact_quicknet_orientation() -> None:
    contract = _manifest()["quicknet_contract"]
    assert contract["scheme"] == "bls-unchained-g1-rfc9380"
    assert contract["curve"] == "BLS12-381"
    assert contract["chain_hash"] == _QUICKNET_CHAIN_HASH
    assert contract["genesis_unix_seconds"] == 1692803367
    assert contract["period_seconds"] == 3
    assert contract["public_key_group"] == "G2"
    assert contract["public_key_compressed_bytes"] == 96
    assert contract["signature_group"] == "G1"
    assert contract["signature_compressed_bytes"] == 48
    assert contract["message_digest_bytes"] == 32
    assert contract["message_derivation"] == "SHA256(uint64_big_endian(round))"
    assert contract["dst"] == _QUICKNET_DST
    assert contract["augmentation"] == "none"


def test_manifest_abi_is_bounded_and_not_caller_configurable() -> None:
    abi = _manifest()["abi"]
    assert abi["entry_point"] == "mt4_s3a_verify_quicknet_bls"
    assert abi["status_codes"] == _STATUS_INVENTORY
    assert len(abi["status_codes"]) == 12
    for flag in (
        "caller_selectable_dst",
        "caller_selectable_curve_or_group",
        "caller_selectable_hash_mode",
        "caller_selectable_augmentation",
        "heap_owned_across_abi",
        "blst_object_crosses_abi",
        "mutable_global_state",
        "upstream_blst_error_exposed",
    ):
        assert abi[flag] is False, flag


def test_manifest_uses_only_stable_api_and_no_blst_aux() -> None:
    manifest = _manifest()
    assert tuple(manifest["stable_c_api_symbols"]) == _STABLE_SYMBOLS
    assert manifest["blst_aux_used"] is False
    assert manifest["experimental_api_used"] is False


@pytest.mark.parametrize("flag", _PROTECTED_FLAGS)
def test_every_protected_flag_is_false_in_the_manifest(flag: str) -> None:
    assert _manifest()["protected_flags"][flag] is False


def test_manifest_admits_nothing_and_marks_cross_platform_pending() -> None:
    manifest = _manifest()
    assert manifest["raw_production_bytes_committed"] is False
    assert manifest["windows_execution_proof"] == "PENDING_CI"
    assert manifest["linux_execution_proof"] == "PENDING_CI"
    assert manifest["python38_execution_proof"] == "PENDING_CI"
    determinism = manifest["runtime_determinism"]
    assert determinism["native_library_filesystem_load_at_init"] is True
    for key in (
        "filesystem_required_per_verify_call",
        "network_required_per_verify_call",
        "clock_required_per_verify_call",
        "randomness_required_per_verify_call",
        "environment_required_per_verify_call",
    ):
        assert determinism[key] is False, key


def test_dual_lane_policy_is_explicit() -> None:
    manifest = _manifest()
    lane_a = manifest["lane_a_policy"]
    lane_b = manifest["lane_b_policy"]
    assert lane_a["name"] == "LANE_A_COMMITTED_OFFLINE_CORPUS"
    assert lane_a["committed"] is True
    assert lane_a["network_at_test_time"] is False
    assert lane_a["raw_production_response_bytes_permitted"] is False
    assert lane_a["generated_bytes_may_be_labelled_upstream_vector"] is False

    assert lane_b["name"] == "LANE_B_TRANSIENT_PRODUCTION_COMPATIBILITY"
    assert lane_b["committed"] is False
    assert lane_b["raw_bytes_committed"] is False
    assert lane_b["raw_bytes_uploaded_as_artifact"] is False
    assert lane_b["raw_bytes_printed_to_logs"] is False
    # Lane B is evidence only: it admits no operational or readiness consequence.
    for denied in (
        "provider_reachability",
        "machine_time_origin",
        "timestamp_origin",
        "provider_operational_approval",
        "source_quorum_countability",
        "readiness_promotion",
        "connector_promotion",
    ):
        assert denied in lane_b["does_not_admit"], denied


def test_shim_uses_only_stable_blst_surface() -> None:
    source = _read(_SHIM_PATH)
    # Compare actual include directives, so the docstring may name blst_aux.h to explain its
    # exclusion while an added dependency on it still fails here.
    includes = re.findall(r'^\s*#\s*include\s*[<"]([^">]+)[">]', source, re.MULTILINE)
    assert "blst.h" in includes
    assert "blst_aux.h" not in includes
    assert not any(name.startswith("blst_aux") for name in includes), includes
    for symbol in _STABLE_SYMBOLS:
        assert symbol in source, symbol


def test_shim_enforces_exact_quicknet_sizes_and_fixed_dst() -> None:
    source = _read(_SHIM_PATH)
    assert "#define MT4_S3A_PUBLIC_KEY_LEN 96" in source
    assert "#define MT4_S3A_SIGNATURE_LEN 48" in source
    assert "#define MT4_S3A_MESSAGE_DIGEST_LEN 32" in source
    # The DST is a file-scope constant, never a parameter.
    assert 'static const byte MT4_S3A_QUICKNET_DST[] = "' + _QUICKNET_DST + '";' in source
    assert "MT4_S3A_QUICKNET_DST_LEN" in source
    signature_block = source.split("int mt4_s3a_verify_quicknet_bls(", 1)[1].split(")", 1)[0]
    for forbidden in ("dst", "DST", "hash_or_encode", "aug", "curve", "group"):
        assert forbidden not in signature_block, forbidden


def test_shim_has_explicit_subgroup_infinity_and_canonicality_gates() -> None:
    source = _read(_SHIM_PATH)
    # Public key: decode, canonical recompress, infinity, explicit G2 subgroup.
    assert "blst_p2_uncompress(&public_key_affine, public_key)" in source
    assert "blst_p2_affine_compress(public_key_recompressed, &public_key_affine)" in source
    assert "memcmp(public_key_recompressed, public_key, MT4_S3A_PUBLIC_KEY_LEN)" in source
    assert "blst_p2_affine_is_inf(&public_key_affine)" in source
    assert "!blst_p2_affine_in_g2(&public_key_affine)" in source
    # Signature: decode, canonical recompress, infinity, explicit G1 subgroup.
    assert "blst_p1_uncompress(&signature_affine, signature)" in source
    assert "blst_p1_affine_compress(signature_recompressed, &signature_affine)" in source
    assert "memcmp(signature_recompressed, signature, MT4_S3A_SIGNATURE_LEN)" in source
    assert "blst_p1_affine_is_inf(&signature_affine)" in source
    assert "!blst_p1_affine_in_g1(&signature_affine)" in source


def test_shim_status_inventory_is_exact_and_bounded() -> None:
    source = _read(_SHIM_PATH)
    defined = dict(re.findall(r"#define MT4_S3A_([A-Z_]+) (\d+)\n", source))
    for code, name in _STATUS_INVENTORY.items():
        assert defined.get(name) == code, name
    # No upstream BLST_ERROR value may be forwarded as the public status.
    assert "return err" not in source
    assert "return verify_result" not in source
    assert "return (int)" not in source


def test_shim_declares_no_runtime_ambient_dependency() -> None:
    source = _read(_SHIM_PATH)
    for forbidden in (
        "stdio.h",
        "stdlib.h",
        "time.h",
        "malloc(",
        "calloc(",
        "free(",
        "getenv(",
        "fopen(",
        "rand(",
        "socket",
        "static blst_",
    ):
        assert forbidden not in source, forbidden


def test_probe_is_stdlib_only_and_imports_no_network_capability() -> None:
    source = _read(_PROBE_PATH)
    imports = set(re.findall(r"^import ([a-z_][a-z0-9_]*)", source, re.MULTILINE))
    imports |= set(re.findall(r"^from ([a-z_][a-z0-9_.]*) import", source, re.MULTILINE))
    assert imports == {"ctypes", "hashlib", "__future__"}, imports
    for forbidden in ("urllib", "requests", "socket", "http", "asyncio", "subprocess", "os.system"):
        assert forbidden not in source, forbidden


def test_probe_pins_the_same_bounded_abi_contract() -> None:
    source = _read(_PROBE_PATH)
    assert "PUBLIC_KEY_LEN = 96" in source
    assert "SIGNATURE_LEN = 48" in source
    assert "MESSAGE_DIGEST_LEN = 32" in source
    assert 'ENTRY_POINT = "mt4_s3a_verify_quicknet_bls"' in source
    assert 'QUICKNET_DST = b"' + _QUICKNET_DST + '"' in source
    assert "NATIVE_LIBRARY_FILESYSTEM_LOAD_AT_INIT = True" in source
    assert "FILESYSTEM_REQUIRED_PER_VERIFY_CALL = False" in source
    # Exact ctypes argtypes/restype must be declared, not left to default marshalling.
    assert "entry.argtypes = (" in source
    assert "entry.restype = ctypes.c_int" in source
    assert source.count("ctypes.c_size_t") >= 3
    assert source.count("ctypes.c_char_p") >= 3


def test_probe_status_names_match_the_manifest_inventory() -> None:
    source = _read(_PROBE_PATH)
    for code, name in _STATUS_INVENTORY.items():
        assert "STATUS_" + name + " = " + code in source, name


def test_workflow_pins_upstream_commit_and_requires_python_38() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "BLST_COMMIT: " + _UPSTREAM_COMMIT in workflow
    assert "BLST_RELEASE: " + _UPSTREAM_RELEASE in workflow
    assert "repository: supranational/blst" in workflow
    assert "ref: ${{ env.BLST_COMMIT }}" in workflow
    # The pinned commit is re-proven at runtime, not merely requested.
    assert "BLST_TAG_COMMIT_MISMATCH" in workflow
    assert 'python-version: "3.8"' in workflow
    assert "PYTHON_38_REQUIRED" in workflow


def test_workflow_covers_windows_and_linux_x64() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "os: windows-2022" in workflow
    assert "os: ubuntu-22.04" in workflow
    assert "fail-fast: false" in workflow
    # Fixed runner families rather than "latest" for reproducible qualification evidence.
    assert "windows-latest" not in workflow
    assert "ubuntu-latest" not in workflow


def test_workflow_never_uploads_or_persists_lane_b_raw_material() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "upload-artifact" not in workflow
    assert "LANE_B_RAW_BYTES_PERSISTED=False" in workflow
    # Only digests and identities may be emitted for Lane B.
    assert "LANE_B_SIGNATURE_SHA256" in workflow
    for forbidden in ("print(signature", "print(beacon", 'print("%s" % signature', "echo ${signature"):
        assert forbidden not in workflow, forbidden


def test_workflow_admits_nothing_and_promotes_nothing() -> None:
    workflow = _read(_WORKFLOW_PATH)
    for statement in (
        "DEPENDENCY_PROFILE_ADMITTED=false",
        "FIXTURE_CORPUS_ADMITTED=false",
        "MT4_VERIFIER_PROFILE_SELECTED=false",
        "READINESS_PROMOTED=false",
        "CONNECTOR_PROMOTED=false",
    ):
        assert statement in workflow, statement
    assert "permissions:\n  contents: read" in workflow
    # Qualification must never install project runtime dependencies or a third-party toolchain.
    assert "pip install" not in workflow
    assert "requirements.txt" not in workflow


def test_no_raw_production_signature_material_is_committed() -> None:
    """No committed qualification file may carry a compressed G1 signature literal.

    A Quicknet signature is 48 bytes -- exactly 96 hex characters.  Asserting that no run of 96 or
    more hex characters exists proves the round-42 production signature (and any other beacon
    signature or 96-byte public key) is absent, without embedding the value here to search for it.
    """
    pattern = re.compile(r"[0-9a-fA-F]{96,}")
    for path in _AUTHORIZED_FILES:
        found = pattern.findall(_read(path))
        assert found == [], (path.name, [run[:16] + "..." for run in found])


def test_qualification_code_is_not_reachable_from_product_modules() -> None:
    product_root = _REPO_ROOT / "src" / "crypto_core"
    offenders = []
    for path in product_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "mt4_s3a" in text or "qualification" in text.lower() and "blst" in text.lower():
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == [], offenders


def test_no_bls_dependency_is_admitted_and_python_floor_is_unchanged() -> None:
    pyproject = _read(_REPO_ROOT / "pyproject.toml")
    assert 'requires-python = ">=3.8"' in pyproject
    assert 'target-version = "py38"' in pyproject
    for forbidden in ("blst", "pyblst", "py_ecc", "py-ecc", "blsttc", "milagro", "swig"):
        assert forbidden not in pyproject.lower(), forbidden


def test_document_separates_candidate_admission_profile_and_readiness() -> None:
    doc = _read(_DOC_PATH)
    for concept in (
        "ARCHITECTURE_CANDIDATE",
        "DEPENDENCY_ADMISSION",
        "VERIFIER_PROFILE_SELECTION",
        "READINESS",
    ):
        assert concept in doc, concept
    assert "PENDING_CI" in doc
    assert _UPSTREAM_COMMIT in doc
    assert "Apache-2.0" in doc
    # Historical V1 must be described as preserved evidence, never as rewritten.
    assert "wip/crypto-core-mt4-s3a-drand-quicknet-qualification" in doc


def test_contract_tests_kill_the_intended_semantic_mutants() -> None:
    """Documents which committed test fails for each mutation this slice must not survive.

    The native shim cannot be compiled on the local workstation, so the C contract is owned by
    source-level assertions above; this test pins the mapping so the coverage intent is explicit.
    """
    mutant_to_guard = {
        "remove G2 public-key subgroup gate": "test_shim_has_explicit_subgroup_infinity_and_canonicality_gates",
        "remove G1 signature subgroup gate": "test_shim_has_explicit_subgroup_infinity_and_canonicality_gates",
        "remove canonical recompress comparison": "test_shim_has_explicit_subgroup_infinity_and_canonicality_gates",
        "remove infinity rejection": "test_shim_has_explicit_subgroup_infinity_and_canonicality_gates",
        "make DST caller-controlled": "test_shim_enforces_exact_quicknet_sizes_and_fixed_dst",
        "remove exact length gate": "test_shim_enforces_exact_quicknet_sizes_and_fixed_dst",
        "expose upstream BLST_ERROR": "test_shim_status_inventory_is_exact_and_bounded",
        "depend on blst_aux.h": "test_shim_uses_only_stable_blst_surface",
        "commit a production signature literal": "test_no_raw_production_signature_material_is_committed",
        "set a protected flag true": "test_every_protected_flag_is_false_in_the_manifest",
        "admit a BLS dependency": "test_no_bls_dependency_is_admitted_and_python_floor_is_unchanged",
        "unpin the upstream commit": "test_workflow_pins_upstream_commit_and_requires_python_38",
        "drop Windows or Linux coverage": "test_workflow_covers_windows_and_linux_x64",
        "upload Lane-B raw material": "test_workflow_never_uploads_or_persists_lane_b_raw_material",
        "give the probe network capability": "test_probe_is_stdlib_only_and_imports_no_network_capability",
    }
    module_source = _read(_TEST_PATH)
    for mutant, guard in mutant_to_guard.items():
        assert "def " + guard + "(" in module_source, (mutant, guard)
    assert len(mutant_to_guard) >= 15
