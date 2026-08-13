"""Permanent offline contract tests for the MT4 blst dependency-admission EVIDENCE slice.

These tests never build, attest, upload or reach the network.  They own the committed supply-chain
contract by inspecting the workflow, the manifest generator and the evidence fixture, so a moving
action tag, a widened permission, an attestation that could run before qualification, a circular
recipe digest, an uploadable raw-Quicknet path or any protected-flag promotion fails here rather
than only in CI.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_s3a_blst_qualification.yml"
_GENERATOR_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_blst_dependency_admission_manifest.py"
_FIXTURE_PATH = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "mt4_blst_dependency_admission_evidence_v1.json"

_UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"

_ACTION_PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/attest": "508db95dd578ae2727ebd6217d5ba78e4fbda05d",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
}

# The unprivileged job executes pull-request-controlled code; the privileged job holds the Sigstore
# credential.  Nothing may ever be in both sets.
_QUALIFY_JOB = "qualify"
_ATTEST_JOB = "attest-qualified-evidence"

# Only these trusted GitHub actions may appear inside the credential-bearing job.
_PRIVILEGED_JOB_ALLOWED_ACTIONS = ("actions/download-artifact", "actions/attest")

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

_FORBIDDEN_PERMISSIONS = (
    "packages",
    "pull-requests",
    "actions",
    "security-events",
    "artifact-metadata",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_read(_WORKFLOW_PATH))


def _fixture() -> dict:
    return json.loads(_read(_FIXTURE_PATH))


def _generator_module():
    sys.path.insert(0, str(_GENERATOR_PATH.parent))
    try:
        import mt4_blst_dependency_admission_manifest as module
    finally:
        sys.path.pop(0)
    return module


def _steps() -> list:
    return _workflow()["jobs"][_QUALIFY_JOB]["steps"]


def _attest_steps() -> list:
    return _workflow()["jobs"][_ATTEST_JOB]["steps"]


def _step_index(predicate) -> int:
    for index, step in enumerate(_steps()):
        if predicate(step):
            return index
    raise AssertionError("step not found")


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    """A moving tag would let an attested build's supply-chain identity change with no commit."""
    workflow = _read(_WORKFLOW_PATH)
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", workflow, re.MULTILINE)
    assert uses, "workflow declares no actions"
    for reference in uses:
        action, _, ref = reference.partition("@")
        assert re.fullmatch(r"[0-9a-f]{40}", ref), (action, ref)
        assert action in _ACTION_PINS, action
        assert ref == _ACTION_PINS[action], (action, ref, _ACTION_PINS[action])


def test_action_pins_match_the_controller_packet_and_fixture() -> None:
    pins = _fixture()["pinned_actions"]
    assert pins["actions_checkout"] == _ACTION_PINS["actions/checkout"]
    assert pins["actions_setup_python"] == _ACTION_PINS["actions/setup-python"]
    assert pins["actions_attest"] == _ACTION_PINS["actions/attest"]
    assert pins["actions_upload_artifact"] == _ACTION_PINS["actions/upload-artifact"]
    assert pins["actions_download_artifact"] == _ACTION_PINS["actions/download-artifact"]
    workflow = _read(_WORKFLOW_PATH)
    for name, sha in _ACTION_PINS.items():
        assert sha in workflow, name


def test_qualification_job_holds_no_attestation_credential() -> None:
    """P1-MT4-ATTESTATION-CREDENTIALS-EXPOSED-TO-PR-CODE.

    GitHub exposes the OIDC token at JOB scope.  The qualification job checks out and executes
    pull-request-controlled Python, C and shell, so granting it id-token would put untrusted
    execution in the same trust domain as the Sigstore signing identity.  Its entire privilege set
    must be exactly ``contents: read``.
    """
    workflow = _workflow()
    permissions = workflow["jobs"][_QUALIFY_JOB]["permissions"]
    assert permissions == {"contents": "read"}, permissions

    # Workflow scope must not hand the capability back in through the side door.
    assert workflow["permissions"] == {"contents": "read"}, workflow["permissions"]

    # No attestation may be minted from the job that runs PR-controlled code.
    for step in _steps():
        assert "actions/attest" not in step.get("uses", ""), step.get("name")


def test_privileged_attestation_job_permissions_are_least_privilege() -> None:
    job = _workflow()["jobs"][_ATTEST_JOB]
    permissions = job["permissions"]
    assert permissions == {
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }, permissions
    # artifact-metadata is only needed for storage records, which this workflow does not create.
    for forbidden in _FORBIDDEN_PERMISSIONS:
        assert forbidden not in permissions, forbidden


def test_privileged_job_executes_no_pull_request_controlled_code() -> None:
    """The credential-bearing job is an envelope: trusted pinned actions and nothing else."""
    job = _workflow()["jobs"][_ATTEST_JOB]
    assert job["needs"] == _QUALIFY_JOB

    for step in _attest_steps():
        name = step.get("name", "")
        # No shell of any kind, and therefore no repository script, install or gh/curl/git call.
        assert "run" not in step, name
        assert "shell" not in step, name
        uses = step.get("uses", "")
        assert uses, name
        # No local action: ./ would execute repository-controlled action code.
        assert not uses.startswith("./"), name
        action, _, ref = uses.partition("@")
        assert action in _PRIVILEGED_JOB_ALLOWED_ACTIONS, action
        assert ref == _ACTION_PINS[action], (action, ref)
        assert action != "actions/checkout"


def test_privileged_job_downloads_exactly_one_named_artifact_fail_closed() -> None:
    steps = _attest_steps()
    downloads = [s for s in steps if "download-artifact" in s.get("uses", "")]
    assert len(downloads) == 1, [s.get("name") for s in steps]
    with_block = downloads[0]["with"]

    # Exact artifact name from the matrix row; never a glob or a whole-run download.
    assert with_block["name"] == "${{ matrix.artifact_name }}"
    assert "pattern" not in with_block
    assert "merge-multiple" not in with_block
    # Corrupted transport must fail closed rather than be attested.
    assert with_block["digest-mismatch"] == "error"
    # Same repository, same run: the pinned action needs no token, so none is granted.
    assert "github-token" not in with_block
    assert "repository" not in with_block
    assert "run-id" not in with_block


def test_privileged_matrix_rows_are_platform_distinct_and_non_colliding() -> None:
    matrix = _workflow()["jobs"][_ATTEST_JOB]["strategy"]["matrix"]["include"]
    assert len(matrix) == 2, matrix
    by_platform = {row["platform"]: row for row in matrix}
    assert set(by_platform) == {"windows-x64", "linux-x64"}
    assert by_platform["windows-x64"]["artifact_name"] == "mt4-blst-admission-evidence-windows-x64"
    assert by_platform["linux-x64"]["artifact_name"] == "mt4-blst-admission-evidence-linux-x64"
    assert by_platform["windows-x64"]["binary_name"] == "mt4_s3a_blst_quicknet_shim.dll"
    assert by_platform["linux-x64"]["binary_name"] == "libmt4_s3a_blst_quicknet_shim.so"
    # An artifact name reused across rows would attest one platform's bytes under the other.
    assert len({row["artifact_name"] for row in matrix}) == 2
    assert len({row["binary_name"] for row in matrix}) == 2


def test_attestation_cannot_run_before_qualification_passes() -> None:
    """Ordering is the whole safety property: never attest a binary that was not just qualified.

    The gate is now the job boundary itself.  ``needs: qualify`` skips the privileged job unless
    every member of the qualification matrix succeeded, so a failed Lane A or Lane B can never be
    followed by an attestation.
    """
    workflow = _workflow()
    assert workflow["jobs"][_ATTEST_JOB]["needs"] == _QUALIFY_JOB

    names = [step.get("name", "") for step in _steps()]
    lane_a_structural = _step_index(lambda s: "Lane A offline structural" in s.get("name", ""))
    lane_a_subgroup = _step_index(lambda s: "Lane A upstream" in s.get("name", ""))
    lane_b = _step_index(lambda s: "Lane B transient" in s.get("name", ""))
    manifest = _step_index(lambda s: "Generate canonical build-provenance manifest" in s.get("name", ""))
    subject_proof = _step_index(lambda s: "Prove the attestation subject" in s.get("name", ""))
    upload = _step_index(lambda s: "Upload admission evidence" in s.get("name", ""))

    # The complete Lane A and Lane B suite must precede the manifest, the subject proof and the
    # upload that hands the bytes across the trust boundary.
    assert lane_a_structural < lane_a_subgroup < lane_b < manifest, names
    assert manifest < subject_proof < upload, names

    # Nothing between qualification and the handoff may rebuild or move the binary.
    for name in names[lane_b + 1 : upload]:
        lowered = name.lower()
        assert "build" not in lowered or "provenance" in lowered, name


def test_attested_subject_is_the_exact_downloaded_artifact_path() -> None:
    """Qualified, hashed, uploaded, downloaded and attested bytes must be the same file."""
    canonical = "${{ runner.temp }}/shim/${{ matrix.library_name }}"
    lane_b = next(s for s in _steps() if "Lane B transient" in s.get("name", ""))
    assert lane_b["env"]["MT4_S3A_LIBRARY"] == canonical

    attest_steps = _attest_steps()
    download = next(s for s in attest_steps if "download-artifact" in s.get("uses", ""))
    destination = download["with"]["path"]
    assert destination == "${{ runner.temp }}/admission-evidence"

    attest = next(s for s in attest_steps if s.get("name", "") == "Attest the qualified native binary")
    # The attested path must be the downloaded artifact's binary, exact and non-globbed.
    assert attest["with"]["subject-path"] == destination + "/${{ matrix.binary_name }}"
    assert "*" not in attest["with"]["subject-path"]
    assert attest["with"]["create-storage-record"] is False

    manifest_attest = next(s for s in attest_steps if s.get("name", "") == "Attest the canonical provenance manifest")
    assert manifest_attest["with"]["subject-path"] == (destination + "/mt4_blst_dependency_admission_manifest.json")
    assert "*" not in manifest_attest["with"]["subject-path"]
    assert manifest_attest["with"]["create-storage-record"] is False

    # Every attestation in the workflow must decline the storage record.
    for step in attest_steps:
        if "actions/attest@" in step.get("uses", ""):
            assert step["with"]["create-storage-record"] is False, step.get("name")


def test_subject_identity_is_proven_before_the_bytes_leave_the_runner() -> None:
    """The manifest-vs-binary equality gate must still run inside the unprivileged job."""
    steps = _steps()
    proof = next(s for s in steps if "Prove the attestation subject" in s.get("name", ""))
    assert "TOCTOU_BINARY_IDENTITY_MISMATCH" in proof["run"]
    assert "SUBJECT_NAME_MISMATCH" in proof["run"]
    assert "PROTECTED_FLAG_NOT_FALSE" in proof["run"]
    assert "SUBJECT_IDENTITY_PROVEN=PASS" in proof["run"]


def test_upload_is_restricted_to_binary_and_manifest_only() -> None:
    upload = next(s for s in _steps() if "Upload admission evidence" in s.get("name", ""))
    paths = [line.strip() for line in upload["with"]["path"].strip().split("\n") if line.strip()]
    assert len(paths) == 2, paths
    assert any(path.endswith("${{ matrix.library_name }}") for path in paths)
    assert any(path.endswith("mt4_blst_dependency_admission_manifest.json") for path in paths)
    # No directory-wide or wildcard upload may leak raw Quicknet material or intermediates.
    for path in paths:
        assert "*" not in path, path
        assert not path.rstrip("/").endswith("shim"), path
    assert upload["with"]["if-no-files-found"] == "error"
    # Platform-distinct artifact names: Windows and Linux evidence must never collide.
    assert "windows-x64" in upload["with"]["name"]
    assert "linux-x64" in upload["with"]["name"]


def test_workflow_still_proves_exact_head_and_pinned_upstream() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "github.event.pull_request.head.sha" in workflow
    assert "QUALIFICATION_EXACT_HEAD=PASS" in workflow
    assert "QUALIFICATION_SOURCE_HEAD_MISMATCH" in workflow
    assert "BLST_COMMIT: " + _UPSTREAM_COMMIT in workflow
    assert "BLST_TAG_COMMIT_MISMATCH" in workflow


def test_workflow_emits_evidence_markers_and_never_admission_claims() -> None:
    workflow = _read(_WORKFLOW_PATH)
    # The old MT4_BLST_*_ATTESTATION=CREATED echoes are deliberately gone: they lived in the job
    # that now holds no credential, and the privileged job may not run any shell step.  The pinned
    # attestation action succeeding is the execution proof, and only GitHub's cryptographic
    # verification is authoritative anyway -- never a log string.
    for marker in (
        "MT4_BLST_BUILD_PROVENANCE=PASS",
        "SUBJECT_IDENTITY_PROVEN=PASS",
        "DEPENDENCY_ADMISSION_EVIDENCE=COLLECTED",
        "DEPENDENCY_PROFILE_ADMITTED=false",
        "MT4_VERIFIER_PROFILE_SELECTED=false",
        "READINESS_PROMOTED=false",
        "CONNECTOR_PROMOTED=false",
    ):
        assert marker in workflow, marker
    for forbidden in (
        "DEPENDENCY_ADMITTED=true",
        "VERIFIER_SELECTED",
        "PROOF_VERIFIED=true",
        "QUORUM_READY",
    ):
        assert forbidden not in workflow, forbidden


def test_linux_portable_recipe_is_explicit_and_windows_invents_no_flag() -> None:
    workflow = _read(_WORKFLOW_PATH)
    # Linux must neutralise build.sh's host-CPU ADX specialisation.
    assert "./build.sh -D__BLST_PORTABLE__" in workflow
    # Windows build.bat has no portable flag upstream; none may be invented.
    assert "build.bat -D__BLST_PORTABLE__" not in workflow
    assert "/D__BLST_PORTABLE__" not in workflow
    assert "MT4_PORTABLE_MODE=PORTABLE" in workflow

    portability = _fixture()["portability"]
    assert portability["vocabulary"] == ["PORTABLE", "TARGET_BOUND", "PORTABILITY_UNPROVEN"]
    assert portability["unproven_must_not_be_presented_as_portable"] is True
    assert portability["linux"]["recipe"] == "./build.sh -D__BLST_PORTABLE__"
    assert "__ADX__" in portability["linux"]["evidence"]
    assert portability["windows"]["recipe"] == "build.bat (unmodified)"
    assert "host cpu feature detection" in portability["windows"]["evidence"].lower()
    assert "__ADX__" in portability["windows"]["evidence"]
    assert "caveat" in portability["windows"]


@pytest.mark.parametrize("flag", _PROTECTED_FLAGS)
def test_every_protected_flag_is_false_in_the_fixture(flag: str) -> None:
    assert _fixture()["protected_flags"][flag] is False


def test_generator_emits_all_protected_flags_false() -> None:
    module = _generator_module()
    assert set(module.PROTECTED_FLAGS) == set(_PROTECTED_FLAGS)
    assert module.EVIDENCE_STATUS == "ADMISSION_EVIDENCE_ONLY"
    assert module.SCHEMA_VERSION == "mt4-blst-dependency-admission-evidence.v1"


def test_build_recipe_digest_is_not_circular_and_excludes_runtime_noise() -> None:
    """The recipe digest identifies the recipe, never one execution of it."""
    module = _generator_module()
    recipe_fields = set(module._BUILD_RECIPE_FIELDS)
    for excluded in (
        "output_binary_sha256",
        "workflow_run_id",
        "workflow_run_attempt",
        "operational_metadata",
        "runner_image",
        "runner_image_version",
        "build_recipe_digest",
    ):
        assert excluded not in recipe_fields, excluded
    for required in (
        "upstream_commit",
        "upstream_source_tree_digest",
        "shim_source_sha256",
        "compiler_id",
        "compiler_version",
        "target_identity",
        "build_command",
        "build_flags",
        "portable_mode",
        "actions_attest_commit",
        # download-artifact is the transport across the credential trust boundary, so its exact
        # identity is security-relevant recipe input.
        "actions_download_artifact_commit",
    ):
        assert required in recipe_fields, required

    fixture = _fixture()["build_recipe_digest_contract"]
    assert fixture["circular_output_digest"] is False
    assert "output_binary_sha256" in fixture["excludes"]
    assert set(fixture["binds"]) == recipe_fields


def test_canonical_serialization_is_deterministic() -> None:
    module = _generator_module()
    payload = {"b": 2, "a": 1, "nested": {"z": True, "y": None}}
    first = module.canonical_json(payload)
    second = module.canonical_json(dict(reversed(list(payload.items()))))
    assert first == second
    assert first == '{"a":1,"b":2,"nested":{"y":null,"z":true}}'
    # A stable serialization means a stable digest.
    assert hashlib.sha256(first.encode()).hexdigest() == hashlib.sha256(second.encode()).hexdigest()


def test_generator_rejects_unknown_portable_mode_and_bad_hex() -> None:
    module = _generator_module()
    assert module.PORTABLE_MODES == ("PORTABLE", "TARGET_BOUND", "PORTABILITY_UNPROVEN")
    with pytest.raises(module.ManifestError):
        module._require_hex("nothex", "pin", 40)
    with pytest.raises(module.ManifestError):
        module._require_hex("ABCDEF" + "0" * 34, "pin", 40)
    with pytest.raises(module.ManifestError):
        module._require_hex("abc", "pin", 40)
    assert module._require_hex(_UPSTREAM_COMMIT, "pin", 40) == _UPSTREAM_COMMIT


def test_generator_is_stdlib_only_and_reaches_no_network_or_github_api() -> None:
    source = _read(_GENERATOR_PATH)
    imports = set(re.findall(r"^import ([a-z_][a-z0-9_]*)", source, re.MULTILINE))
    imports |= set(re.findall(r"^from ([a-z_][a-z0-9_.]*) import", source, re.MULTILINE))
    assert imports <= {"argparse", "hashlib", "json", "subprocess", "sys", "pathlib", "__future__"}, imports
    for forbidden in ("urllib", "requests", "socket", "http.client", "gh ", "api.github.com", "time."):
        assert forbidden not in source, forbidden
    # No wall clock may become trust evidence and no environment scraping is permitted.
    assert "datetime" not in source
    assert "os.environ" not in source


def test_upstream_source_tree_digest_uses_git_objects_not_the_filesystem() -> None:
    """Windows and Linux must agree, so the digest binds git object bytes, not a checkout."""
    source = _read(_GENERATOR_PATH)
    assert '"ls-tree", "-r", "-z"' in source
    assert "cat-file" in source
    assert "--batch" in source
    # Malformed or unexpected inventory must fail closed rather than silently degrade.
    for guard in (
        "malformed ls-tree record",
        "malformed ls-tree header",
        "unexpected upstream object type",
        "duplicate path in upstream inventory",
        "empty upstream inventory",
    ):
        assert guard in source, guard

    contract = _fixture()["upstream_source_tree_digest_contract"]
    assert contract["inventory_command"] == "git ls-tree -r -z <upstream_commit>"
    assert contract["platform_independent"] is True
    assert contract["symlinks_followed_on_filesystem"] is False
    assert "blob sha256 of exact git cat-file bytes" in contract["binds"]


def test_fixture_records_evidence_only_status_and_pending_execution() -> None:
    fixture = _fixture()
    assert fixture["schema"] == "mt4-blst-dependency-admission-evidence.v1"
    assert fixture["evidence_status"] == "ADMISSION_EVIDENCE_ONLY"
    assert fixture["upstream"]["commit"] == _UPSTREAM_COMMIT
    assert fixture["upstream"]["license"] == "Apache-2.0"
    proofs = fixture["execution_proofs"]
    assert proofs["windows_attested_build"] == "PENDING_CI"
    assert proofs["linux_attested_build"] == "PENDING_CI"
    assert proofs["artifact_attestation"] == "PENDING_CI"
    for denied in (
        "dependency admission",
        "verifier profile selection",
        "fixture corpus admission",
        "readiness promotion",
        "connector promotion",
    ):
        assert denied in fixture["explicitly_not_established"], denied


def test_manifest_binds_the_exact_download_artifact_identity() -> None:
    """The transport action is part of the evidence, so the manifest must carry its exact pin."""
    module = _generator_module()
    assert "actions_download_artifact_commit" in module._BUILD_RECIPE_FIELDS
    generator_source = _read(_GENERATOR_PATH)
    assert "--actions-download-artifact-commit" in generator_source
    # The workflow must actually supply it, from the pinned env identity.
    workflow_text = _read(_WORKFLOW_PATH)
    assert "ACTIONS_DOWNLOAD_ARTIFACT_COMMIT: " + _ACTION_PINS["actions/download-artifact"] in workflow_text
    assert '--actions-download-artifact-commit "${ACTIONS_DOWNLOAD_ARTIFACT_COMMIT}"' in workflow_text


def test_fixture_records_the_credential_isolation_repair() -> None:
    contract = _fixture()["credential_isolation_contract"]
    assert contract["finding_repaired"] == "P1-MT4-ATTESTATION-CREDENTIALS-EXPOSED-TO-PR-CODE"

    unprivileged = contract["unprivileged_job"]
    assert unprivileged["id"] == _QUALIFY_JOB
    assert unprivileged["executes_pull_request_controlled_code"] is True
    assert unprivileged["permissions"] == {"contents": "read"}
    assert unprivileged["id_token"] is False
    assert unprivileged["attestations"] is False
    assert unprivileged["attest_action_present"] is False

    privileged = contract["privileged_job"]
    assert privileged["id"] == _ATTEST_JOB
    assert privileged["needs"] == _QUALIFY_JOB
    assert privileged["executes_pull_request_controlled_code"] is False
    assert privileged["checkout_present"] is False
    assert privileged["run_step_present"] is False
    assert privileged["local_action_present"] is False
    assert privileged["executes_downloaded_binary"] is False
    assert list(privileged["allowed_actions"]) == list(_PRIVILEGED_JOB_ALLOWED_ACTIONS)

    transport = contract["transport"]
    assert transport["same_workflow_run_only"] is True
    assert transport["github_token_supplied"] is False
    assert transport["digest_mismatch"] == "error"
    assert transport["external_artifact_url"] is False
    assert transport["cache_based_handoff"] is False
    # The claim must stay honest about what job isolation does and does not establish.
    assert "credential isolation" in contract["proves"]
    assert "non-malicious" in contract["does_not_prove"]


def test_attestation_contract_matches_the_pinned_action_semantics() -> None:
    contract = _fixture()["attestation_contract"]
    assert contract["action"] == "actions/attest"
    assert contract["mode"] == "provenance"
    assert contract["create_storage_record"] is False
    assert contract["push_to_registry"] is False
    assert "artifact-metadata: write" in contract["forbidden_permissions"]
    assert "id-token: write" in contract["required_permissions"]
    assert "attestations: write" in contract["required_permissions"]
    assert "gh attestation verify" in contract["verification_authority"]
    # The credential may exist only on the privileged job, never on qualification or workflow scope.
    scope = contract["required_permissions_scope"]
    assert "attest-qualified-evidence" in scope
    assert "never on the qualification job" in scope


def test_no_product_source_or_dependency_file_is_touched_by_this_slice() -> None:
    """This slice is qualification/provenance infrastructure only."""
    pyproject = _read(_REPO_ROOT / "pyproject.toml")
    assert 'requires-python = ">=3.8"' in pyproject
    for forbidden in ("blst", "pyblst", "py_ecc", "sigstore", "in-toto"):
        assert forbidden not in pyproject.lower(), forbidden
    product_root = _REPO_ROOT / "src" / "crypto_core"
    offenders = [
        str(path.relative_to(_REPO_ROOT))
        for path in product_root.rglob("*.py")
        if "mt4_blst_dependency_admission" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders


def test_contract_tests_kill_the_intended_supply_chain_mutants() -> None:
    mutant_to_guard = {
        "replace a pinned SHA with a moving tag": "test_every_action_is_pinned_to_a_full_commit_sha",
        "swap an action pin for a different commit": "test_action_pins_match_the_controller_packet_and_fixture",
        "grant id-token to the job that runs PR code": "test_qualification_job_holds_no_attestation_credential",
        "grant attestations:write to the qualification job": "test_qualification_job_holds_no_attestation_credential",
        "re-add an attest step to the qualification job": "test_qualification_job_holds_no_attestation_credential",
        "hand the credential back at workflow scope": "test_qualification_job_holds_no_attestation_credential",
        "add artifact-metadata or contents write": "test_privileged_attestation_job_permissions_are_least_privilege",
        "widen privileged job permissions": "test_privileged_attestation_job_permissions_are_least_privilege",
        "check out the repository in the privileged job": "test_privileged_job_executes_no_pull_request_controlled_code",
        "add a run/shell step to the privileged job": "test_privileged_job_executes_no_pull_request_controlled_code",
        "run a local ./ action in the privileged job": "test_privileged_job_executes_no_pull_request_controlled_code",
        "introduce an untrusted action into the privileged job": "test_privileged_job_executes_no_pull_request_controlled_code",
        "drop needs: qualify so attestation runs regardless": "test_attestation_cannot_run_before_qualification_passes",
        "downgrade digest-mismatch from error": "test_privileged_job_downloads_exactly_one_named_artifact_fail_closed",
        "download by pattern or whole-run instead of exact name": "test_privileged_job_downloads_exactly_one_named_artifact_fail_closed",
        "download from another run or repository": "test_privileged_job_downloads_exactly_one_named_artifact_fail_closed",
        "collide the two platform artifact names": "test_privileged_matrix_rows_are_platform_distinct_and_non_colliding",
        "attest before Lane A/Lane B complete": "test_attestation_cannot_run_before_qualification_passes",
        "attest a different path than the downloaded binary": "test_attested_subject_is_the_exact_downloaded_artifact_path",
        "enable create-storage-record": "test_attested_subject_is_the_exact_downloaded_artifact_path",
        "drop the manifest-vs-binary identity gate": "test_subject_identity_is_proven_before_the_bytes_leave_the_runner",
        "unpin the download-artifact transport identity": "test_manifest_binds_the_exact_download_artifact_identity",
        "widen the upload path to a directory or glob": "test_upload_is_restricted_to_binary_and_manifest_only",
        "collide Windows and Linux artifact names": "test_upload_is_restricted_to_binary_and_manifest_only",
        "drop the exact-head assertion": "test_workflow_still_proves_exact_head_and_pinned_upstream",
        "change the pinned blst commit": "test_workflow_still_proves_exact_head_and_pinned_upstream",
        "emit an admission claim from CI": "test_workflow_emits_evidence_markers_and_never_admission_claims",
        "drop the Linux portable flag": "test_linux_portable_recipe_is_explicit_and_windows_invents_no_flag",
        "invent a Windows portable flag": "test_linux_portable_recipe_is_explicit_and_windows_invents_no_flag",
        "flip a protected flag true": "test_every_protected_flag_is_false_in_the_fixture",
        "make the recipe digest circular": "test_build_recipe_digest_is_not_circular_and_excludes_runtime_noise",
        "put a run id or clock in the recipe": "test_build_recipe_digest_is_not_circular_and_excludes_runtime_noise",
        "give the generator network access": "test_generator_is_stdlib_only_and_reaches_no_network_or_github_api",
        "hash a filesystem tree instead of git objects": "test_upstream_source_tree_digest_uses_git_objects_not_the_filesystem",
        "self-promote execution proof in source": "test_fixture_records_evidence_only_status_and_pending_execution",
    }
    module_source = _read(Path(__file__).resolve())
    for mutant, guard in mutant_to_guard.items():
        assert "def " + guard + "(" in module_source, (mutant, guard)
    assert len(mutant_to_guard) >= 19
