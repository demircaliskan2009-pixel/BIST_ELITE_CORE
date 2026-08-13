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
import yaml

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
_DRAND_CHAIN_HASH_REPOSITORY = "https://github.com/drand/drand"
_DRAND_CHAIN_HASH_COMMIT = "2363f3b9ba5fd6f14e0b84a096b248479790d75d"
_DRAND_CHAIN_HASH_PATH = "common/chain/info.go"
_DRAND_CHAIN_HASH_SYMBOL = "Info.Hash"

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
    "blst_p2_affine_generator",
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
    parsed = yaml.safe_load(workflow)
    # Explicit per-platform jobs rather than a matrix, so each build job can publish an unambiguous
    # artifact id output for its own qualification job to consume.
    runners = {job_id: job["runs-on"] for job_id, job in parsed["jobs"].items()}
    assert set(runners.values()) == {"windows-2022", "ubuntu-22.04"}, runners
    assert sum(1 for value in runners.values() if value == "windows-2022") == 2, runners
    assert sum(1 for value in runners.values() if value == "ubuntu-22.04") == 2, runners
    # Fixed runner families rather than "latest" for reproducible qualification evidence.
    assert "windows-latest" not in workflow
    assert "ubuntu-latest" not in workflow


def test_workflow_never_uploads_or_persists_lane_b_raw_material() -> None:
    """Lane-B raw material must never leave the runner.

    Uploads are no longer banned outright -- the admission-evidence slice uploads the qualified
    binary and its provenance manifest -- so this asserts the property that actually matters: every
    uploaded path is one of those two explicit files, with no directory or glob that could sweep up
    a fetched beacon.  The precise upload inventory is additionally owned by
    test_mt4_blst_dependency_admission_evidence.py.
    """
    workflow = _read(_WORKFLOW_PATH)
    assert "LANE_B_RAW_BYTES_PERSISTED=False" in workflow
    # Only digests and identities may be emitted for Lane B.
    assert "LANE_B_SIGNATURE_SHA256" in workflow
    for forbidden in ("print(signature", "print(beacon", 'print("%s" % signature', "echo ${signature"):
        assert forbidden not in workflow, forbidden

    parsed = yaml.safe_load(workflow)
    allowed_suffixes = (
        "libmt4_s3a_blst_quicknet_shim.so",
        "mt4_s3a_blst_quicknet_shim.dll",
        "mt4_blst_dependency_admission_manifest.json",
        "mt4_blst_qualification_receipt.json",
    )
    uploads = 0
    for job in parsed["jobs"].values():
        for step in job["steps"]:
            if "upload-artifact" not in step.get("uses", ""):
                continue
            uploads += 1
            paths = [line.strip() for line in str(step["with"]["path"]).strip().split("\n") if line.strip()]
            assert paths, step.get("name")
            for path in paths:
                assert path.endswith(allowed_suffixes), path
                assert "*" not in path, path
    # Two immutable candidate uploads plus two receipt uploads; nothing else may be published.
    assert uploads == 4, uploads


_UPSTREAM_NEGATIVE_SOURCE = "bindings/python/run.me"
_G1_LOW_ORDER_IDS = ("p11", "p10177", "p859267")
_G2_LOW_ORDER_IDS = ("p13", "p23", "p2713")


def test_workflow_executes_upstream_subgroup_vectors_rather_than_enumerating() -> None:
    """The subgroup step must EXECUTE official low-order vectors, not list candidate filenames."""
    workflow = _read(_WORKFLOW_PATH)
    assert _UPSTREAM_NEGATIVE_SOURCE in workflow
    for identifier in _G1_LOW_ORDER_IDS + _G2_LOW_ORDER_IDS:
        assert '"' + identifier + '"' in workflow, identifier
    # The vectors must be pushed through the real shim and reach EXACT bounded statuses.
    assert "probe.STATUS_SIG_NOT_IN_GROUP" in workflow
    assert "probe.STATUS_PK_NOT_IN_GROUP" in workflow
    assert "upstream_g1_low_order" in workflow
    assert "upstream_g2_low_order" in workflow
    assert "LANE_A_SUBGROUP_FAILURES" in workflow
    # The enumeration-only regression must never come back.
    assert "UPSTREAM_NEGATIVE_CANDIDATE" not in workflow
    assert "REPORTED_FOR_CONTROLLER_ADJUDICATION" not in workflow
    # The pinned commit is re-proven before the source file is trusted as authority.
    assert "PINNED_UPSTREAM_SOURCE_MISMATCH" in workflow
    assert "UPSTREAM_IDENTIFIER_NOT_UNIQUE" in workflow
    assert "UPSTREAM_VECTOR_MALFORMED" in workflow


def test_workflow_lane_a_covers_the_mandatory_negative_matrix() -> None:
    workflow = _read(_WORKFLOW_PATH)
    required = {
        "malformed_public_key": "probe.STATUS_PK_BAD_ENCODING",
        "malformed_signature": "probe.STATUS_SIG_BAD_ENCODING",
        "public_key_infinity": "probe.STATUS_PK_INFINITY",
        "signature_infinity": "probe.STATUS_SIG_INFINITY",
        "truncated_signature": "probe.STATUS_BAD_LENGTH",
        "overlong_signature": "probe.STATUS_BAD_LENGTH",
        "truncated_public_key": "probe.STATUS_BAD_LENGTH",
        "overlong_public_key": "probe.STATUS_BAD_LENGTH",
        "truncated_message_digest": "probe.STATUS_BAD_LENGTH",
    }
    for label, expected_status in required.items():
        assert label in workflow, label
        assert expected_status in workflow, expected_status
    # The four rejection classes must stay distinguishable, never collapsed into "not OK".
    for status in (
        "probe.STATUS_PK_BAD_ENCODING",
        "probe.STATUS_SIG_BAD_ENCODING",
        "probe.STATUS_PK_INFINITY",
        "probe.STATUS_SIG_INFINITY",
        "probe.STATUS_PK_NOT_IN_GROUP",
        "probe.STATUS_SIG_NOT_IN_GROUP",
        "probe.STATUS_BAD_LENGTH",
    ):
        assert status in workflow, status


def test_workflow_lane_b_enforces_randomness_and_scheme_consistency() -> None:
    """Defensive randomness consistency and the exact scheme gate remain enforced.

    Current Drand v2 does not define a required round `randomness` field, so the consistency check
    is conditional; the scheme gate is unconditional because v2 requires `scheme`.
    """
    workflow = _read(_WORKFLOW_PATH)
    assert "OPTIONAL_EXTRA_RANDOMNESS_CONSISTENCY=PASS" in workflow
    assert "LANE_B_RANDOMNESS_INCONSISTENT" in workflow
    assert "LANE_B_RANDOMNESS_NOT_HEX" in workflow
    assert "hashlib.sha256(signature).digest()" in workflow
    assert "LANE_B_SCHEME_MISMATCH" in workflow
    assert "LANE_B_SCHEME_MISSING" in workflow
    assert "bls-unchained-g1-rfc9380" in workflow


def test_scaffolding_generator_uses_the_stable_public_accessor() -> None:
    """The generator must come from blst_p2_affine_generator(), not the raw exported datum.

    This is a project-side encapsulation choice, not an upstream constraint: the pinned header
    declares both BLS12_381_G2 and blst_p2_affine_generator(), and upstream itself casts the datum
    directly in more than one internal path outside the accessor (src/aggregate.c). No claim is made
    that only the accessor performs this reinterpretation, or that the datum is undeclared, aux-only,
    experimental or unsupported.
    """
    shim = _read(_SHIM_PATH)
    helper = shim.split("MT4_S3A_EXPORT int mt4_s3a_qualification_g2_generator_compressed", 1)[1]
    helper = helper.split("\n}", 1)[0]
    assert "blst_p2_affine_generator()" in helper
    assert "blst_p2_affine_compress(out, generator)" in helper
    # The raw datum must not be addressed anywhere in the executable body.
    assert "BLS12_381_G2" not in helper
    assert "&BLS12_381_G2" not in shim
    # Bounded NULL / exact-length gates, and a fail-closed accessor result.
    assert "if (out == NULL)" in helper
    assert "MT4_S3A_NULL_INPUT" in helper
    assert "out_len != MT4_S3A_PUBLIC_KEY_LEN" in helper
    assert "MT4_S3A_BAD_LENGTH" in helper
    assert "if (generator == NULL)" in helper


def test_scaffolding_generator_is_declared_non_load_bearing() -> None:
    shim = _read(_SHIM_PATH)
    probe_source = _read(_PROBE_PATH)
    assert "mt4_s3a_qualification_g2_generator_compressed" in shim
    assert "QUALIFICATION SCAFFOLDING -- NOT part of the verification contract." in shim
    assert "GENERATOR_ENTRY_POINT" in probe_source
    # The scaffolding must not decode caller material or reach any verification branch.
    helper = shim.split("MT4_S3A_EXPORT int mt4_s3a_qualification_g2_generator_compressed", 1)[1]
    helper = helper.split("\n}", 1)[0]
    for forbidden in ("uncompress", "in_g1", "in_g2", "core_verify", "memcmp", "hash_to"):
        assert forbidden not in helper, forbidden
    # No new ABI status may be introduced by the scaffolding.
    statuses = set(re.findall(r"MT4_S3A_([A-Z_]+)", helper))
    assert statuses <= {"EXPORT", "NULL_INPUT", "BAD_LENGTH", "PUBLIC_KEY_LEN", "OK", "VERIFY_FAILED"}, statuses


def test_generator_provenance_wording_is_accurate_not_overclaimed() -> None:
    """The tracked record must not overclaim upstream facts about BLS12_381_G2.

    Narrow, structured checks rather than a broad language ban: this asserts the specific false
    claims are absent and the specific corrected facts are present, so corrective historical
    explanations or exact-evidence quotations elsewhere are never accidentally rejected.
    """
    shim = _read(_SHIM_PATH)
    doc = _read(_DOC_PATH)
    manifest_text = _read(_MANIFEST_PATH)
    manifest = _manifest()

    forbidden_claims = (
        "only the accessor performs the reinterpretation",
        "only the accessor reinterprets",
    )
    for text, name in ((shim, "shim"), (doc, "doc")):
        for claim in forbidden_claims:
            assert claim not in text, (name, claim)

    # The corrected record must state the two upstream facts that make the old claim false.
    for text, name in ((shim, "shim"), (doc, "doc")):
        assert "aggregate.c" in text, name
        assert "outside the accessor" in text, name
        assert "declares both" in text or "declares BOTH" in text, name

    rejected_reason = manifest["scaffolding_generator_source"]["rejected_reason"]
    assert "unsupportedness" in rejected_reason or "unsupported" in rejected_reason
    assert "exclusivity" in rejected_reason
    assert "undeclared" not in manifest_text.lower()
    assert "aux-only" not in manifest_text.lower()
    assert "experimental" not in rejected_reason.lower()


def test_workflow_qualifies_the_exact_head_not_the_synthetic_merge_ref() -> None:
    """Qualification evidence must describe code that exists on the branch under audit."""
    workflow = _read(_WORKFLOW_PATH)
    assert "github.event.pull_request.head.sha" in workflow
    assert "persist-credentials: false" in workflow
    # Runtime proof that the worktree really is that head, with an explicit fail-closed marker.
    assert "QUALIFICATION_EXPECTED_HEAD" in workflow
    assert "QUALIFICATION_CHECKOUT_HEAD" in workflow
    assert "QUALIFICATION_EXACT_HEAD=PASS" in workflow
    assert "QUALIFICATION_SOURCE_HEAD_MISMATCH" in workflow
    assert 'ACTUAL_SOURCE_HEAD="$(git rev-parse HEAD)"' in workflow

    # Structural, not textual: the explanatory comment may name refs/pull while no step is allowed
    # to actually check it out.
    parsed = yaml.safe_load(workflow)
    # Every job in the pipeline checks out the exact head and proves it before doing anything else.
    assert parsed["jobs"], "workflow declares no jobs"
    for job_id, job in parsed["jobs"].items():
        steps = job["steps"]
        checkout = steps[0]
        assert checkout["uses"].startswith("actions/checkout@"), job_id
        assert "head.sha" in checkout["with"]["ref"], job_id
        assert checkout["with"]["persist-credentials"] is False, job_id

        for step in steps:
            ref = (step.get("with") or {}).get("ref")
            if ref is not None:
                assert "refs/pull" not in ref, (job_id, step.get("name"))
        # The head assertion must run immediately after checkout, before any build or
        # qualification step consumes the worktree.
        names = [step.get("name", "") for step in steps]
        assertion_index = next(i for i, n in enumerate(names) if n.startswith("Prove the checked-out worktree"))
        assert assertion_index == 1, (job_id, names[:3])


def test_workflow_uses_only_current_drand_v2_fields() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "/v2/chains/" in workflow
    # v2-native names are required.
    assert 'info.get("scheme")' in workflow
    assert 'info.get("chain_hash")' in workflow
    assert '"genesis_seed"' in workflow
    assert '"genesis_time"' in workflow
    # No v1 alias may be load-bearing.  Matching against accessor forms keeps the explanatory
    # comment that names the rejected aliases from producing a false positive.
    for legacy in (
        'info["hash"]',
        'info.get("hash"',
        'info["schemeID"]',
        'info.get("schemeID"',
        'info["groupHash"]',
        'info.get("groupHash"',
        'info["metadata"]',
        'info.get("metadata"',
    ):
        assert legacy not in workflow, legacy


def test_workflow_binds_the_public_key_to_the_pinned_quicknet_root() -> None:
    """The relay supplies the verification key, so its self-reported identity cannot be the root."""
    workflow = _read(_WORKFLOW_PATH)
    # Canonical recomputation with every load-bearing component present.
    assert 'struct.pack(">I", period)' in workflow
    assert 'struct.pack(">q", genesis_time)' in workflow
    assert "+ public_key" in workflow
    assert "+ genesis_seed" in workflow
    assert "+ QUICKNET_BEACON_ID" in workflow
    assert 'QUICKNET_BEACON_ID = b"quicknet"' in workflow
    assert "computed_chain_hash = hashlib.sha256(canonical_input).hexdigest()" in workflow
    assert "LANE_B_CANONICAL_CHAIN_HASH_MISMATCH" in workflow
    assert "LANE_B_CHAIN_ROOT_BINDING=PASS" in workflow
    assert "LANE_B_CHAIN_HASH_RECOMPUTED" in workflow

    # The generic v2 schema may make genesis_seed optional, but this Quicknet root binding may
    # not proceed with it absent or empty.
    assert 'genesis_seed = exact_hex(info, "genesis_seed", "LANE_B_GENESIS_SEED_INVALID")' in workflow
    assert "if not genesis_seed:" in workflow
    assert 'raise SystemExit("LANE_B_GENESIS_SEED_INVALID")' in workflow

    # Ordering: the root binding must precede any BLS verification of the fetched key.
    binding_at = workflow.index("LANE_B_CANONICAL_CHAIN_HASH_MISMATCH")
    verify_at = workflow.index('check("real_quicknet_verify"')
    assert binding_at < verify_at, "root binding must gate BLS verification"

    # The pinned root and immutable identity constants must not be relay-selected.
    assert "QUICKNET_PERIOD_SECONDS = 3" in workflow
    assert "QUICKNET_GENESIS_TIME = 1692803367" in workflow
    assert 'QUICKNET_SCHEME = "bls-unchained-g1-rfc9380"' in workflow


def test_workflow_round_contract_does_not_require_randomness() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "V2_RANDOMNESS_FIELD_POLICY=NOT_REQUIRED" in workflow
    assert "OPTIONAL_EXTRA_RANDOMNESS_CONSISTENCY=FIELD_ABSENT_V2_EXPECTED" in workflow
    assert "OPTIONAL_EXTRA_RANDOMNESS_CONSISTENCY=PASS" in workflow
    # A present-but-inconsistent randomness value still fails closed.
    assert "LANE_B_RANDOMNESS_INCONSISTENT" in workflow
    # Unchained profile: a non-empty previous_signature contradicts pinned Quicknet.
    assert "LANE_B_UNEXPECTED_PREVIOUS_SIGNATURE" in workflow
    # round and signature remain required.
    assert 'exact_int(beacon, "round"' in workflow
    assert 'exact_hex(beacon, "signature"' in workflow


def test_manifest_records_v2_contract_root_binding_and_exact_head() -> None:
    manifest = _manifest()

    api = manifest["drand_api_contract"]
    assert api["version"] == "v2"
    assert api["v2_chain_hash_field"] == "chain_hash"
    assert api["v2_scheme_field"] == "scheme"
    assert api["legacy_v1_aliases_accepted"] is False
    assert api["v2_round_randomness_field_required"] is False
    assert set(api["v2_required_round_fields"]) == {"round", "signature"}
    for legacy in ("hash", "groupHash", "schemeID", "metadata.beaconID"):
        assert legacy in api["legacy_v1_alias_names_rejected"], legacy

    root = manifest["quicknet_root_of_trust"]
    assert root["root_type"] == "canonical_drand_chain_info_hash"
    assert root["expected_chain_hash"] == _QUICKNET_CHAIN_HASH
    assert root["period_seconds"] == 3
    assert root["genesis_unix_seconds"] == 1692803367
    assert root["beacon_id"] == "quicknet"
    assert root["beacon_id_is_non_default"] is True
    assert root["self_reported_chain_hash_is_sufficient"] is False
    assert root["public_key_accepted_only_after_root_binding"] is True

    head = manifest["exact_head_qualification"]
    assert head["required"] is True
    assert head["pull_request_source"] == "github.event.pull_request.head.sha"
    assert head["runtime_git_head_assertion"] is True
    assert head["synthetic_merge_ref_is_execution_authority"] is False
    assert head["persist_credentials"] is False

    # The corrected randomness record must not imply v2 returns or requires it.
    assert "randomness_derivation" not in manifest["quicknet_contract"]


def test_manifest_distinguishes_drand_v2_schema_from_quicknet_root_policy() -> None:
    api = _manifest()["drand_api_contract"]

    generic_required = tuple(api["v2_schema_required_info_fields"])
    generic_optional = tuple(api["v2_schema_optional_info_fields"])
    quicknet_required = tuple(api["quicknet_qualification_required_info_fields"])
    assert generic_required == ("public_key", "period", "genesis_time", "scheme")
    assert generic_optional == ("genesis_seed", "chain_hash", "beacon_id")
    assert set(quicknet_required) == {
        "public_key",
        "period",
        "genesis_time",
        "genesis_seed",
        "scheme",
    }
    assert "genesis_seed" not in generic_required
    assert "v2_required_info_fields" not in api

    authority = api["canonical_chain_hash_authority"]
    assert authority["repository"] == _DRAND_CHAIN_HASH_REPOSITORY
    assert authority["commit"] == _DRAND_CHAIN_HASH_COMMIT
    assert authority["path"] == _DRAND_CHAIN_HASH_PATH
    assert authority["symbol"] == _DRAND_CHAIN_HASH_SYMBOL
    algorithm = authority["algorithm"]
    components = (
        "period_seconds",
        "genesis_time",
        "public_key_marshaled_bytes",
        "genesis_seed_bytes",
        "non_default_beacon_id_bytes",
    )
    positions = [algorithm.index(component) for component in components]
    assert positions == sorted(positions)


def test_document_distinguishes_schema_requiredness_from_project_policy() -> None:
    doc = _read(_DOC_PATH)
    for marker in (
        "generic /v2/chains/<chain_hash>/info schema",
        "this Quicknet qualification's root-binding policy",
        "The official generic Drand v2 schema makes `genesis_seed` optional.",
        "fails closed when Quicknet `genesis_seed` is missing or empty",
        "`chain_hash` is schema-optional and is only a self-reported cross-check",
        "`beacon_id` is also schema-optional",
        _DRAND_CHAIN_HASH_REPOSITORY,
        _DRAND_CHAIN_HASH_COMMIT,
        _DRAND_CHAIN_HASH_PATH,
        _DRAND_CHAIN_HASH_SYMBOL,
        "upstream Drand's `Info.UnmarshalJSON` retains compatibility",
        "That is a project policy, not an assertion\nabout upstream parser capability",
    ):
        assert marker in doc, marker


def test_shim_preserves_the_g1_decode_time_subgroup_status() -> None:
    """Pinned blst distinguishes two G1 decode failures; the ABI must not collapse them.

    src/e1.c POINTonE1_Uncompress_Z returns BLST_POINT_NOT_IN_GROUP for the canonical X=0 edge
    (the curve points (0, +/-2)) after a SUCCESSFUL reconstruction.  That is a subgroup verdict, so
    it must reach SIG_NOT_IN_GROUP, while genuine encoding/curve failures stay SIG_BAD_ENCODING.
    """
    shim = _read(_SHIM_PATH)

    # The exact upstream result must be captured, not tested inline against BLST_SUCCESS.
    assert "BLST_ERROR signature_decode;" in shim
    assert "signature_decode = blst_p1_uncompress(&signature_affine, signature);" in shim
    assert "if (signature_decode == BLST_POINT_NOT_IN_GROUP) {" in shim
    assert "return MT4_S3A_SIG_NOT_IN_GROUP;" in shim
    assert "if (signature_decode != BLST_SUCCESS) {" in shim
    assert "return MT4_S3A_SIG_BAD_ENCODING;" in shim

    # The collapsed form must never come back.
    assert "if (blst_p1_uncompress(&signature_affine, signature) != BLST_SUCCESS) {" not in shim

    # Ordering: the subgroup verdict is decided before the generic bad-encoding fallback.
    not_in_group_at = shim.index("if (signature_decode == BLST_POINT_NOT_IN_GROUP)")
    bad_encoding_at = shim.index("if (signature_decode != BLST_SUCCESS)")
    assert not_in_group_at < bad_encoding_at

    # Route B must survive: a point that decodes cleanly still faces the explicit subgroup gate.
    assert "!blst_p1_affine_in_g1(&signature_affine)" in shim
    gate_at = shim.index("!blst_p1_affine_in_g1(&signature_affine)")
    assert bad_encoding_at < gate_at


def _shim_executable_source() -> str:
    """Return the shim with C comments removed, so prose cannot satisfy a code assertion."""
    source = _read(_SHIM_PATH)
    source = re.sub(r"/\*.*?\*/", " ", source, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", " ", source)


def test_g2_decode_mapping_is_not_symmetrised_without_evidence() -> None:
    """Pinned src/e2.c has no decode-time BLST_POINT_NOT_IN_GROUP, so G2 must NOT mirror G1."""
    code = _shim_executable_source()
    assert "if (blst_p2_uncompress(&public_key_affine, public_key) != BLST_SUCCESS) {" in code
    # Exactly one executable mention of the upstream subgroup result: the G1 decode mapping.
    assert code.count("BLST_POINT_NOT_IN_GROUP") == 1
    assert "signature_decode == BLST_POINT_NOT_IN_GROUP" in code
    # The explicit G2 subgroup gate remains the authority for G2.
    assert "!blst_p2_affine_in_g2(&public_key_affine)" in code
    assert "return MT4_S3A_PK_NOT_IN_GROUP;" in code


def test_workflow_executes_the_g1_decode_time_edge_on_both_platforms() -> None:
    workflow = _read(_WORKFLOW_PATH)
    # The proven canonical encoding: compressed bit set, infinity bit clear, X == 0.
    assert "g1_decode_edge_positive_sign = bytes([0x80]) + bytes(47)" in workflow
    assert "g1_decode_edge_negative_sign = bytes([0xA0]) + bytes(47)" in workflow
    assert "g1_decode_time_not_in_group_x0" in workflow
    assert "probe.STATUS_SIG_NOT_IN_GROUP" in workflow
    assert "LANE_A_G1_DECODE_SUBGROUP_RESULT=SIG_NOT_IN_GROUP" in workflow

    # It must run inside the aggregate Lane-A step that fails closed, and before the PASS marker.
    edge_at = workflow.index("g1_decode_time_not_in_group_x0")
    failure_at = workflow.index("LANE_A_SUBGROUP_FAILURES")
    pass_at = workflow.index("LANE_A_UPSTREAM_SUBGROUP_RESULT=PASS")
    assert edge_at < failure_at < pass_at

    # The pre-existing upstream run.me families must remain, unreplaced.
    for identifier in _G1_LOW_ORDER_IDS + _G2_LOW_ORDER_IDS:
        assert '"' + identifier + '"' in workflow, identifier
    assert "probe.STATUS_PK_NOT_IN_GROUP" in workflow


def test_g1_decode_edge_provenance_is_e1_source_not_run_me() -> None:
    """The X=0 edge derives from src/e1.c semantics and must never be labelled a run.me vector."""
    manifest = _manifest()
    edge = manifest["g1_decode_time_subgroup_edge"]
    assert edge["source_path"] == "src/e1.c"
    assert edge["source_symbol"] == "POINTonE1_Uncompress_Z"
    assert edge["upstream_commit"] == _UPSTREAM_COMMIT
    assert edge["upstream_result"] == "BLST_POINT_NOT_IN_GROUP"
    assert edge["project_abi_result"] == "SIG_NOT_IN_GROUP"
    assert edge["is_run_me_vector"] is False
    assert edge["source_class"] != "UPSTREAM_LIBRARY_VECTOR"

    # The run.me family keeps its own distinct provenance record.
    assert manifest["upstream_negative_vector_source"]["path"] == _UPSTREAM_NEGATIVE_SOURCE

    # Two bounded causal routes to the same status are recorded.
    routes = manifest["g1_subgroup_status_routes"]
    assert len(routes) == 2
    assert any("blst_p1_uncompress" in route for route in routes)
    assert any("blst_p1_affine_in_g1" in route for route in routes)


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
        "remove G1 upstream vector execution": "test_workflow_executes_upstream_subgroup_vectors_rather_than_enumerating",
        "remove G2 upstream vector execution": "test_workflow_executes_upstream_subgroup_vectors_rather_than_enumerating",
        "replace exact subgroup status with generic not-OK": "test_workflow_lane_a_covers_the_mandatory_negative_matrix",
        "restore enumeration-only subgroup step": "test_workflow_executes_upstream_subgroup_vectors_rather_than_enumerating",
        "remove malformed G1 case": "test_workflow_lane_a_covers_the_mandatory_negative_matrix",
        "remove G1 Lane-A infinity case": "test_workflow_lane_a_covers_the_mandatory_negative_matrix",
        "remove randomness-consistency gate": "test_workflow_lane_b_enforces_randomness_and_scheme_consistency",
        "let scaffolding perform verification": "test_scaffolding_generator_is_declared_non_load_bearing",
        "replace stable generator accessor with the raw exported datum": "test_scaffolding_generator_uses_the_stable_public_accessor",
        "reintroduce the exclusivity overclaim about the accessor": "test_generator_provenance_wording_is_accurate_not_overclaimed",
        "restore default PR merge-ref checkout": "test_workflow_qualifies_the_exact_head_not_the_synthetic_merge_ref",
        "remove the runtime exact-HEAD assertion": "test_workflow_qualifies_the_exact_head_not_the_synthetic_merge_ref",
        "restore the v1 info[hash] alias": "test_workflow_uses_only_current_drand_v2_fields",
        "restore the v1 schemeID fallback": "test_workflow_uses_only_current_drand_v2_fields",
        "remove the exact scheme check": "test_workflow_uses_only_current_drand_v2_fields",
        "remove canonical chain-hash recomputation": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "trust the self-reported chain_hash only": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "misstate generic v2 genesis_seed requiredness": "test_manifest_distinguishes_drand_v2_schema_from_quicknet_root_policy",
        "omit canonical Drand hash provenance": "test_manifest_distinguishes_drand_v2_schema_from_quicknet_root_policy",
        "drop public key from the canonical hash": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "drop genesis seed from the canonical hash": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "drop the quicknet beacon id from the canonical hash": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "switch canonical packing to little-endian": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "verify BLS before the root binding gate": "test_workflow_binds_the_public_key_to_the_pinned_quicknet_root",
        "require a v2 randomness field": "test_workflow_round_contract_does_not_require_randomness",
        "accept a non-empty previous_signature": "test_workflow_round_contract_does_not_require_randomness",
        "unpin the upstream negative source path": "test_workflow_executes_upstream_subgroup_vectors_rather_than_enumerating",
    }
    module_source = _read(_TEST_PATH)
    for mutant, guard in mutant_to_guard.items():
        assert "def " + guard + "(" in module_source, (mutant, guard)
    assert len(mutant_to_guard) >= 15
