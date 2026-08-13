"""Permanent offline contract tests for the MT4 blst dependency-admission EVIDENCE pipeline.

These tests never build, attest, upload or reach the network.  They own three committed contracts:

1. the pull-request-triggered qualification workflow is ENTIRELY unprivileged -- a pull request
   authors its own workflow definition, so it may not define any credential-bearing job at all;
2. the candidate artifact is the immutability boundary -- it is uploaded BEFORE qualification and
   qualification consumes a fresh download of it, never a mutable build-workspace path;
3. the trusted attestation workflow is anchored to the default branch through workflow_run, and its
   gate independently re-derives every digest rather than believing a qualification receipt.

The gate's fail-closed behaviour is exercised directly against synthetic evidence, so a regression
that would only surface after a merge fails here instead.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_s3a_blst_qualification.yml"
_TRUSTED_WORKFLOW_PATH = _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_trusted_attestation.yml"
_GENERATOR_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_blst_dependency_admission_manifest.py"
_GATE_PATH = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_trusted_attestation_gate.py"
_FIXTURE_PATH = _REPO_ROOT / "tests" / "crypto_core" / "fixtures" / "mt4_blst_dependency_admission_evidence_v1.json"
_DOC_PATH = _REPO_ROOT / "docs" / "crypto_core" / "mt4_s3a_blst_v0317_qualification.md"

_UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
_QUICKNET_CHAIN_HASH = "52db9ba70e0cc0f6eaf7803dd07447a1f5477735fd3f661792ba94600c84e971"

_ACTION_PINS = {
    "actions/checkout": "11d5960a326750d5838078e36cf38b85af677262",
    "actions/setup-python": "a26af69be951a213d495a4c3e4e4022e16d87065",
    "actions/attest": "508db95dd578ae2727ebd6217d5ba78e4fbda05d",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
}

_BUILD_JOBS = ("build-linux-candidate", "build-windows-candidate")
_QUALIFY_JOBS = ("qualify-linux-candidate", "qualify-windows-candidate")
_TRUSTED_JOB = "attest-trusted-evidence"

_PLATFORM_BINARIES = {
    "linux-x64": "libmt4_s3a_blst_quicknet_shim.so",
    "windows-x64": "mt4_s3a_blst_quicknet_shim.dll",
}

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

# Anything that would hand the pull-request workflow a capability it must never hold.
_PRIVILEGED_PERMISSIONS = (
    "id-token",
    "attestations",
    "artifact-metadata",
    "packages",
    "pull-requests",
    "actions",
    "security-events",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _workflow() -> dict:
    return yaml.safe_load(_read(_WORKFLOW_PATH))


def _trusted_workflow() -> dict:
    return yaml.safe_load(_read(_TRUSTED_WORKFLOW_PATH))


def _triggers(workflow: dict) -> dict:
    """PyYAML resolves the bare ``on:`` key to boolean True."""
    return workflow[True] if True in workflow else workflow["on"]


def _fixture() -> dict:
    return json.loads(_read(_FIXTURE_PATH))


def _load(path: Path):
    sys.path.insert(0, str(path.parent))
    try:
        module = __import__(path.stem)
    finally:
        sys.path.pop(0)
    return module


def _generator_module():
    return _load(_GENERATOR_PATH)


def _gate_module():
    return _load(_GATE_PATH)


def _steps(job: str) -> list:
    return _workflow()["jobs"][job]["steps"]


def _step_index(job: str, predicate) -> int:
    for index, step in enumerate(_steps(job)):
        if predicate(step):
            return index
    raise AssertionError("step not found in " + job)


# ---------------------------------------------------------------------------------------------
# P1 -- the pull-request workflow may hold no credential at all
# ---------------------------------------------------------------------------------------------


def test_pull_request_workflow_defines_no_privileged_capability() -> None:
    """P1-MT4-ATTESTATION-WORKFLOW-DEFINITION-PR-CONTROLLED.

    A pull request authors this file.  Isolating the credential into a separate job here would
    still let the pull request define the grant, so the whole workflow must be unprivileged.
    """
    workflow = _workflow()
    assert workflow["permissions"] == {"contents": "read"}, workflow["permissions"]

    for job_id, job in workflow["jobs"].items():
        assert job["permissions"] == {"contents": "read"}, (job_id, job["permissions"])
        for forbidden in _PRIVILEGED_PERMISSIONS:
            assert forbidden not in job["permissions"], (job_id, forbidden)
        for step in job["steps"]:
            assert "actions/attest" not in step.get("uses", ""), (job_id, step.get("name"))

    # Not a single occurrence anywhere in the file, including comments that could become real.
    text = _read(_WORKFLOW_PATH)
    for forbidden in ("id-token:", "attestations:", "artifact-metadata:"):
        assert forbidden not in text, forbidden


def test_pull_request_workflow_jobs_are_exactly_the_four_unprivileged_stages() -> None:
    jobs = _workflow()["jobs"]
    assert sorted(jobs) == sorted(_BUILD_JOBS + _QUALIFY_JOBS), sorted(jobs)
    for qualify_job, build_job in zip(sorted(_QUALIFY_JOBS), sorted(_BUILD_JOBS)):
        assert jobs[qualify_job]["needs"] == build_job, qualify_job


def test_every_action_is_pinned_to_a_full_commit_sha() -> None:
    """A moving tag would let an attested build's supply-chain identity change with no commit."""
    for path in (_WORKFLOW_PATH, _TRUSTED_WORKFLOW_PATH):
        workflow = _read(path)
        uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", workflow, re.MULTILINE)
        assert uses, path.name
        for reference in uses:
            action, _, ref = reference.partition("@")
            assert re.fullmatch(r"[0-9a-f]{40}", ref), (path.name, action, ref)
            assert action in _ACTION_PINS, (path.name, action)
            assert ref == _ACTION_PINS[action], (path.name, action, ref)


def test_action_pins_match_the_controller_packet_and_fixture() -> None:
    pins = _fixture()["pinned_actions"]
    assert pins["actions_checkout"] == _ACTION_PINS["actions/checkout"]
    assert pins["actions_setup_python"] == _ACTION_PINS["actions/setup-python"]
    assert pins["actions_attest"] == _ACTION_PINS["actions/attest"]
    assert pins["actions_upload_artifact"] == _ACTION_PINS["actions/upload-artifact"]
    assert pins["actions_download_artifact"] == _ACTION_PINS["actions/download-artifact"]


# ---------------------------------------------------------------------------------------------
# P2 -- immutable candidate artifact, then fresh-download qualification
# ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize("job", _BUILD_JOBS)
def test_candidate_artifact_is_uploaded_before_any_qualification(job: str) -> None:
    """P2-MT4-QUALIFIED-SUBJECT-TOCTOU-NOT-FAIL-CLOSED.

    The build job must upload and stop.  If it also ran Lane A/Lane B it would be qualifying a
    mutable local path, which is exactly the finding.
    """
    steps = _steps(job)
    names = [step.get("name", "") for step in steps]
    assert not any("Lane A" in name or "Lane B" in name for name in names), names

    upload = next(s for s in steps if "upload-artifact" in s.get("uses", ""))
    with_block = upload["with"]
    assert with_block["overwrite"] is False
    assert with_block["if-no-files-found"] == "error"
    paths = [line.strip() for line in str(with_block["path"]).strip().split("\n") if line.strip()]
    assert len(paths) == 2, paths
    for path in paths:
        assert "*" not in path, path
    assert any(path.endswith(".so") or path.endswith(".dll") for path in paths)
    assert any(path.endswith("mt4_blst_dependency_admission_manifest.json") for path in paths)

    # The upload must be the last meaningful act: nothing may rewrite the bytes afterwards.
    upload_index = steps.index(upload)
    for step in steps[upload_index + 1 :]:
        assert "upload-artifact" not in step.get("uses", ""), step.get("name")
        assert "cl " not in str(step.get("run", "")), step.get("name")

    job_definition = _workflow()["jobs"][job]
    assert job_definition["outputs"]["artifact-id"].endswith("outputs.artifact-id }}")
    assert job_definition["outputs"]["artifact-digest"].endswith("outputs.artifact-digest }}")


@pytest.mark.parametrize("job", _QUALIFY_JOBS)
def test_qualification_consumes_a_fresh_download_addressed_by_artifact_id(job: str) -> None:
    steps = _steps(job)
    download = next(s for s in steps if "download-artifact" in s.get("uses", ""))
    with_block = download["with"]

    # Addressed by the exact immutable artifact id emitted by the build job -- never by wildcard.
    assert "artifact-ids" in with_block, with_block
    assert with_block["artifact-ids"].startswith("${{ needs.build-")
    assert with_block["artifact-ids"].endswith("outputs.artifact-id }}")
    assert "pattern" not in with_block
    assert "name" not in with_block
    assert with_block["digest-mismatch"] == "error"
    assert "github-token" not in with_block
    assert "repository" not in with_block
    assert "run-id" not in with_block

    # Download must precede every lane, and the lanes must run against the downloaded bytes.
    download_index = steps.index(download)
    bind_index = _step_index(job, lambda s: "Bind the downloaded candidate identity" in s.get("name", ""))
    lane_a = _step_index(job, lambda s: "Lane A offline structural" in s.get("name", ""))
    lane_a_subgroup = _step_index(job, lambda s: "Lane A upstream" in s.get("name", ""))
    lane_b = _step_index(job, lambda s: "Lane B transient" in s.get("name", ""))
    receipt = _step_index(job, lambda s: "Generate qualification receipt" in s.get("name", ""))
    assert download_index < bind_index < lane_a < lane_a_subgroup < lane_b < receipt

    # No compiler may run in a qualification job: it must not be able to produce its own subject.
    for step in steps:
        body = str(step.get("run", ""))
        assert "build.sh" not in body, step.get("name")
        assert "build.bat" not in body, step.get("name")


@pytest.mark.parametrize("job", _QUALIFY_JOBS)
def test_downloaded_candidate_identity_is_bound_fail_closed(job: str) -> None:
    bind = next(s for s in _steps(job) if "Bind the downloaded candidate identity" in s.get("name", ""))
    body = bind["run"]
    for guard in (
        "CANDIDATE_ARTIFACT_INVENTORY_MISMATCH",
        "CANDIDATE_BINARY_DIGEST_MISMATCH",
        "CANDIDATE_BINARY_NAME_MISMATCH",
        "CANDIDATE_SOURCE_HEAD_MISMATCH",
        "PROTECTED_FLAG_NOT_FALSE",
    ):
        assert guard in body, guard
    # An unexpected third file in the artifact must fail, so the inventory is compared exactly.
    assert "sorted([binary_name, manifest_name])" in body
    assert "QUALIFICATION_INPUT_SOURCE=github_artifact_fresh_download" in body


@pytest.mark.parametrize("job", _QUALIFY_JOBS)
def test_receipt_is_uploaded_separately_and_never_re_uploads_the_binary(job: str) -> None:
    steps = _steps(job)
    uploads = [s for s in steps if "upload-artifact" in s.get("uses", "")]
    assert len(uploads) == 1, [s.get("name") for s in uploads]
    with_block = uploads[0]["with"]
    assert with_block["name"].startswith("mt4-blst-qualification-receipt-")
    assert str(with_block["path"]).strip().endswith("mt4_blst_qualification_receipt.json")
    assert "\n" not in str(with_block["path"]).strip()
    assert with_block["overwrite"] is False
    assert with_block["if-no-files-found"] == "error"


def test_the_two_qualification_jobs_run_identical_lane_logic() -> None:
    """Duplicated crypto logic across platforms would be a drift vector, so equality is enforced."""
    lane_names = (
        "Lane A offline structural and negative vectors",
        "Lane A upstream Apache-2.0 subgroup-invalid vectors",
        "Lane B transient Quicknet compatibility",
        "Bind the downloaded candidate identity",
    )
    for lane in lane_names:
        bodies = set()
        for job in _QUALIFY_JOBS:
            step = next(s for s in _steps(job) if s.get("name") == lane)
            bodies.add(step["run"])
        assert len(bodies) == 1, lane


def test_artifact_names_are_platform_distinct_and_non_colliding() -> None:
    names = []
    for job in _BUILD_JOBS + _QUALIFY_JOBS:
        for step in _steps(job):
            if "upload-artifact" in step.get("uses", ""):
                names.append(step["with"]["name"])
    assert len(names) == 4, names
    assert len(set(names)) == 4, names
    assert set(names) == set(_fixture()["upload_contract"]["artifact_names"])


# ---------------------------------------------------------------------------------------------
# Trusted default-branch attestation workflow
# ---------------------------------------------------------------------------------------------


def test_trusted_workflow_is_default_branch_anchored_only() -> None:
    triggers = _triggers(_trusted_workflow())
    assert set(triggers) == {"workflow_run"}, triggers
    for forbidden in ("pull_request", "pull_request_target", "workflow_dispatch", "repository_dispatch"):
        assert forbidden not in triggers, forbidden

    workflow_run = triggers["workflow_run"]
    assert workflow_run["workflows"] == ["crypto_core mt4-s3a blst qualification"]
    assert workflow_run["types"] == ["completed"]
    assert workflow_run["branches"] == ["main"]


def test_trusted_workflow_guard_rejects_fork_pr_and_non_main_sources() -> None:
    job = _trusted_workflow()["jobs"][_TRUSTED_JOB]
    guard = " ".join(job["if"].split())
    assert "github.event.workflow_run.conclusion == 'success'" in guard
    assert "github.event.workflow_run.event == 'workflow_dispatch'" in guard
    assert "github.event.workflow_run.head_branch == 'main'" in guard
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in guard


def test_trusted_workflow_permissions_are_bounded() -> None:
    workflow = _trusted_workflow()
    assert workflow["permissions"] == {"contents": "read"}
    permissions = workflow["jobs"][_TRUSTED_JOB]["permissions"]
    assert permissions == {
        "actions": "read",
        "contents": "read",
        "id-token": "write",
        "attestations": "write",
    }, permissions
    for forbidden in ("packages", "pull-requests", "security-events", "artifact-metadata"):
        assert forbidden not in permissions, forbidden
    assert permissions["contents"] != "write"


def test_trusted_workflow_checks_out_the_source_head_not_a_pull_request_ref() -> None:
    steps = _trusted_workflow()["jobs"][_TRUSTED_JOB]["steps"]
    checkout = next(s for s in steps if "actions/checkout" in s.get("uses", ""))
    assert checkout["with"]["ref"] == "${{ github.event.workflow_run.head_sha }}"
    assert checkout["with"]["persist-credentials"] is False
    text = _read(_TRUSTED_WORKFLOW_PATH)
    assert "pull_request.head.sha" not in text
    assert "refs/pull" not in text


def test_trusted_workflow_never_executes_the_candidate_binary_or_source_scripts() -> None:
    steps = _trusted_workflow()["jobs"][_TRUSTED_JOB]["steps"]
    for step in steps:
        body = str(step.get("run", ""))
        # The only script the trusted job may run is the gate, from the trusted main checkout.
        for forbidden in (
            "mt4_s3a_blst_quicknet_shim",
            "ctypes",
            "candidate/",
            "chmod +x",
            "./mt4",
        ):
            assert forbidden not in body, (step.get("name"), forbidden)
    run_steps = [s for s in steps if "run" in s]
    scripts = re.findall(r"python (\S+)", " ".join(str(s["run"]) for s in run_steps))
    assert scripts == ["scripts/crypto_core/qualification/mt4_trusted_attestation_gate.py"], scripts


def test_trusted_attestation_signs_validated_checksums_with_a_truthful_predicate() -> None:
    steps = _trusted_workflow()["jobs"][_TRUSTED_JOB]["steps"]
    attests = [s for s in steps if "actions/attest@" in s.get("uses", "")]
    assert len(attests) == 2, [s.get("name") for s in attests]

    seen = set()
    for step in attests:
        with_block = step["with"]
        # subject-checksums, never subject-path: the action must not re-resolve a mutable path.
        assert "subject-checksums" in with_block, with_block
        assert "subject-path" not in with_block
        assert with_block["create-storage-record"] is False
        assert with_block["predicate-type"].endswith("/mt4-blst-admission-evidence/v1")
        assert with_block["predicate-path"].endswith(".predicate.json")
        platform = with_block["subject-checksums"].rsplit("/", 1)[-1].split(".")[0]
        assert platform in _PLATFORM_BINARIES, platform
        assert with_block["predicate-path"].rsplit("/", 1)[-1].startswith(platform)
        seen.add(platform)
    assert seen == set(_PLATFORM_BINARIES)


def test_approved_qualification_workflow_digest_matches_the_committed_workflow() -> None:
    """The trusted gate fails closed unless the qualification workflow is the approved one."""
    text = _read(_TRUSTED_WORKFLOW_PATH)
    declared = re.search(r"APPROVED_QUALIFICATION_WORKFLOW_SHA256:\s*([0-9a-f]{64})", text)
    assert declared, "approved qualification workflow digest is missing or malformed"
    actual = hashlib.sha256(_WORKFLOW_PATH.read_bytes()).hexdigest()
    assert declared.group(1) == actual, (
        "the approved digest must be updated in the trusted workflow whenever the qualification "
        "workflow changes -- that coupling is the fail-closed property"
    )
    # It must live on the trusted surface, never inside the file it approves (which is circular).
    assert "APPROVED_QUALIFICATION_WORKFLOW_SHA256" not in _read(_WORKFLOW_PATH)


# ---------------------------------------------------------------------------------------------
# Trusted gate behaviour -- exercised directly, fail-closed
# ---------------------------------------------------------------------------------------------

_SOURCE_RUN_ID = "31686183920"
_SOURCE_HEAD = "6ce0ae0433cf31a5f82d59a309f904dfdf562512"
_REPOSITORY = "demircaliskan2009-pixel/BIST_ELITE_CORE"
_WORKFLOW_RELPATH = ".github/workflows/crypto_core_mt4_s3a_blst_qualification.yml"
_WORKFLOW_NAME = "crypto_core mt4-s3a blst qualification"


def _gate_arguments(**overrides):
    values = {
        "repository": _REPOSITORY,
        "source_run_id": _SOURCE_RUN_ID,
        "expected_head_sha": _SOURCE_HEAD,
        "expected_workflow_path": _WORKFLOW_RELPATH,
        "expected_workflow_name": _WORKFLOW_NAME,
        "trusted_workflow_identity": "trusted",
        "approved_qualification_workflow_sha256": "a" * 64,
        "qualification_workflow": str(_WORKFLOW_PATH),
        "blst_release": "v0.3.17",
        "blst_commit": _UPSTREAM_COMMIT,
        "quicknet_chain_hash": _QUICKNET_CHAIN_HASH,
        "work_dir": "unused",
        "default_branch": "main",
        "api_url": "https://api.github.com",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _valid_run(**overrides) -> dict:
    run = {
        "repository": {"full_name": _REPOSITORY},
        "head_repository": {"full_name": _REPOSITORY},
        "path": _WORKFLOW_RELPATH,
        "name": _WORKFLOW_NAME,
        "event": "workflow_dispatch",
        "head_branch": "main",
        "head_sha": _SOURCE_HEAD,
        "status": "completed",
        "conclusion": "success",
    }
    run.update(overrides)
    return run


@pytest.mark.parametrize(
    "mutation",
    [
        {"repository": {"full_name": "attacker/other"}},
        {"head_repository": {"full_name": "fork/other"}},
        {"path": ".github/workflows/other.yml"},
        {"name": "other workflow"},
        {"event": "pull_request"},
        {"event": "workflow_run"},
        {"head_branch": "feature/attack"},
        {"head_sha": "0" * 40},
        {"status": "in_progress"},
        {"conclusion": "failure"},
    ],
)
def test_gate_rejects_every_source_run_substitution(mutation: dict) -> None:
    gate = _gate_module()
    with pytest.raises(gate.TrustedGateError):
        gate.verify_source_run(_valid_run(**mutation), _gate_arguments())


def test_gate_accepts_the_exact_expected_source_run() -> None:
    gate = _gate_module()
    gate.verify_source_run(_valid_run(), _gate_arguments())


def test_gate_requires_every_qualification_job_to_have_succeeded() -> None:
    gate = _gate_module()
    good = {"jobs": [{"name": name, "conclusion": "success"} for name in gate.REQUIRED_JOBS]}
    gate.verify_jobs(good)

    for index in range(len(gate.REQUIRED_JOBS)):
        missing = {
            "jobs": [
                {"name": name, "conclusion": "success"}
                for position, name in enumerate(gate.REQUIRED_JOBS)
                if position != index
            ]
        }
        with pytest.raises(gate.TrustedGateError):
            gate.verify_jobs(missing)

    failed = {"jobs": [{"name": name, "conclusion": "success"} for name in gate.REQUIRED_JOBS]}
    failed["jobs"][0]["conclusion"] = "failure"
    with pytest.raises(gate.TrustedGateError):
        gate.verify_jobs(failed)


def _artifact(name: str, identifier: int, digest: str = None) -> dict:
    return {
        "name": name,
        "id": identifier,
        "expired": False,
        "digest": digest or ("sha256:" + "b" * 64),
    }


def _artifacts_payload() -> dict:
    gate = _gate_module()
    artifacts = []
    identifier = 100
    for candidate_name, receipt_name, _binary in gate.PLATFORMS.values():
        artifacts.append(_artifact(candidate_name, identifier))
        artifacts.append(_artifact(receipt_name, identifier + 1))
        identifier += 2
    return {"artifacts": artifacts}


def test_gate_requires_exactly_one_live_artifact_per_expected_name() -> None:
    gate = _gate_module()
    selected = gate.select_artifacts(_artifacts_payload())
    assert len(selected) == 4

    duplicated = _artifacts_payload()
    duplicated["artifacts"].append(_artifact("mt4-blst-candidate-linux-x64", 999))
    with pytest.raises(gate.TrustedGateError):
        gate.select_artifacts(duplicated)

    expired = _artifacts_payload()
    expired["artifacts"][0]["expired"] = True
    with pytest.raises(gate.TrustedGateError):
        gate.select_artifacts(expired)

    undigested = _artifacts_payload()
    undigested["artifacts"][0]["digest"] = None
    with pytest.raises(gate.TrustedGateError):
        gate.select_artifacts(undigested)

    missing = {"artifacts": _artifacts_payload()["artifacts"][:-1]}
    with pytest.raises(gate.TrustedGateError):
        gate.select_artifacts(missing)


def _zip_bytes(members: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in members.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class _SyntheticEvidence:
    """A complete, internally consistent evidence set that individual tests then corrupt."""

    def __init__(self, gate, platform: str = "linux-x64") -> None:
        self.gate = gate
        self.platform = platform
        candidate_name, receipt_name, binary_name = gate.PLATFORMS[platform]
        self.candidate_name = candidate_name
        self.receipt_name = receipt_name
        self.binary_name = binary_name

        self.binary = b"\x7fELF synthetic candidate bytes"
        self.binary_sha256 = hashlib.sha256(self.binary).hexdigest()
        self.manifest = {
            "output_binary_sha256": self.binary_sha256,
            "output_binary_name": binary_name,
            "source_head_sha": _SOURCE_HEAD,
            "upstream_commit": _UPSTREAM_COMMIT,
            "quicknet_chain_hash": _QUICKNET_CHAIN_HASH,
            "upstream_source_tree_digest": "c" * 64,
            "build_recipe_digest": "d" * 64,
        }
        for flag in _PROTECTED_FLAGS:
            self.manifest[flag] = False
        self.manifest_bytes = json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()
        self.manifest_sha256 = hashlib.sha256(self.manifest_bytes).hexdigest()

        self.candidate_artifact = _artifact(candidate_name, 4242, "sha256:" + "e" * 64)
        self.receipt_artifact = _artifact(receipt_name, 4243, "sha256:" + "f" * 64)

        self.receipt = {
            "platform": platform,
            "binary_name": binary_name,
            "binary_sha256": self.binary_sha256,
            "manifest_sha256": self.manifest_sha256,
            "candidate_artifact_id": str(self.candidate_artifact["id"]),
            "candidate_artifact_name": candidate_name,
            "candidate_artifact_digest": self.candidate_artifact["digest"],
            "source_run_id": _SOURCE_RUN_ID,
            "source_head_sha": _SOURCE_HEAD,
            "raw_bytes_persisted": False,
            "qualification_input_source": "github_artifact_fresh_download",
            "blst_commit": _UPSTREAM_COMMIT,
            "quicknet_chain_hash": _QUICKNET_CHAIN_HASH,
            "qualification_workflow_sha256": "a" * 64,
        }
        for flag in gate.RECEIPT_LANE_FLAGS:
            self.receipt[flag] = True
        for flag in _PROTECTED_FLAGS:
            self.receipt[flag] = False

    def selected(self) -> dict:
        return {
            self.candidate_name: self.candidate_artifact,
            self.receipt_name: self.receipt_artifact,
        }

    def _manifest_bytes(self) -> bytes:
        return json.dumps(self.manifest, sort_keys=True, separators=(",", ":")).encode()

    def candidate_archive(self) -> bytes:
        return _zip_bytes({self.binary_name: self.binary, self.gate.MANIFEST_NAME: self._manifest_bytes()})

    def receipt_archive(self) -> bytes:
        return _zip_bytes({self.gate.RECEIPT_NAME: json.dumps(self.receipt, sort_keys=True).encode()})

    def run(self, tmp_path: Path, candidate_archive: bytes = None):
        """Verification is a pure function of bytes: no credential, no download to stub."""
        return self.gate.verify_platform(
            self.platform,
            self.selected(),
            _gate_arguments(),
            self.candidate_archive() if candidate_archive is None else candidate_archive,
            self.receipt_archive(),
            tmp_path,
        )


class _FakeUrlResponse:
    def __init__(self, payload=b"", *, status=200, headers=None, fail_on_read=False):
        self.payload = payload
        self.status = status
        self.headers = {} if headers is None else headers
        self.fail_on_read = fail_on_read
        self.read_calls = 0
        self.read_limits = []
        self.closed = False

    def getcode(self):
        return self.status

    def read(self, limit=-1):
        self.read_calls += 1
        self.read_limits.append(limit)
        if self.fail_on_read:
            raise AssertionError("authenticated redirect response body must not be read")
        return self.payload if limit < 0 else self.payload[:limit]

    def close(self):
        self.closed = True

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()


class _FakeUrlOpener:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []
        self.timeouts = []

    def open(self, request, timeout):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if not self.responses:
            raise AssertionError("unexpected additional urllib request")
        return self.responses.pop(0)


def test_verification_is_separated_from_the_credential_bearing_fetch() -> None:
    """The token must not reach any value later written to disk."""
    gate = _gate_module()
    import inspect

    verify_parameters = set(inspect.signature(gate.verify_platform).parameters)
    assert "token" not in verify_parameters, verify_parameters
    assert {"candidate_archive", "receipt_archive"} <= verify_parameters, verify_parameters
    # The orchestration receives the token, but its storage-only byte producer cannot receive it.
    fetch_parameters = set(inspect.signature(gate.fetch_platform_archives).parameters)
    assert "token" in fetch_parameters, fetch_parameters
    storage_parameters = set(inspect.signature(gate._download_signed_artifact).parameters)
    assert "token" not in storage_parameters, storage_parameters
    storage_source = inspect.getsource(gate._download_signed_artifact)
    assert "Authorization" not in storage_source
    assert "_request(" not in storage_source
    source = _read(_GATE_PATH)
    assert "def build_predicate(record: dict, arguments" in source
    assert "token" not in inspect.signature(gate.build_predicate).parameters


def test_authenticated_phase_sends_authorization_but_never_reads_artifact_bytes(monkeypatch) -> None:
    gate = _gate_module()
    api_header_value = "github-credential-must-stop-at-api"
    signed_url = "https://storage.example.invalid/artifact.zip?signature=temporary"
    response = _FakeUrlResponse(status=302, headers={"Location": signed_url}, fail_on_read=True)
    opener = _FakeUrlOpener(response)
    monkeypatch.setattr(gate, "_authenticated_redirect_opener", lambda: opener)

    actual = gate._resolve_artifact_redirect("https://api.github.com", _REPOSITORY, 4242, api_header_value)

    assert actual == signed_url
    assert len(opener.requests) == 1
    request = opener.requests[0]
    assert request.full_url == f"https://api.github.com/repos/{_REPOSITORY}/actions/artifacts/4242/zip"
    assert request.get_header("Authorization") == "Bearer " + api_header_value
    assert response.read_calls == 0


def test_authenticated_phase_cannot_automatically_follow_the_redirect() -> None:
    gate = _gate_module()
    request = gate.urllib.request.Request("https://api.github.com/repos/example/actions/artifacts/1/zip")
    signed_url = "https://storage.example.invalid/artifact.zip?signature=temporary"
    handler = gate._NoRedirect()

    assert handler.redirect_request(request, None, 302, "Found", {"Location": signed_url}, signed_url) is None
    assert any(isinstance(item, gate._NoRedirect) for item in gate._authenticated_redirect_opener().handlers)


def test_authenticated_phase_requires_a_redirect_response(monkeypatch) -> None:
    gate = _gate_module()
    response = _FakeUrlResponse(
        status=200,
        headers={"Location": "https://storage.example.invalid/artifact.zip"},
        fail_on_read=True,
    )
    monkeypatch.setattr(gate, "_authenticated_redirect_opener", lambda: _FakeUrlOpener(response))

    with pytest.raises(gate.TrustedGateError, match="redirect required"):
        gate._resolve_artifact_redirect("https://api.github.com", _REPOSITORY, 4242, "token")
    assert response.read_calls == 0


@pytest.mark.parametrize(
    "location,marker",
    [
        (None, "Location missing"),
        ("https://[malformed", "Location is malformed"),
        ("http://storage.example.invalid/artifact.zip", "must be https"),
        ("https://temporary-user@storage.example.invalid/artifact.zip", "must not contain userinfo"),
        ("https:///artifact.zip", "must contain a hostname"),
    ],
)
def test_authenticated_phase_rejects_an_unsafe_redirect_location(monkeypatch, location, marker) -> None:
    gate = _gate_module()
    headers = {} if location is None else {"Location": location}
    response = _FakeUrlResponse(status=302, headers=headers, fail_on_read=True)
    monkeypatch.setattr(gate, "_authenticated_redirect_opener", lambda: _FakeUrlOpener(response))

    with pytest.raises(gate.TrustedGateError, match=marker):
        gate._resolve_artifact_redirect("https://api.github.com", _REPOSITORY, 4242, "token")
    assert response.read_calls == 0


def test_storage_phase_is_credential_free_and_returns_bounded_bytes(monkeypatch) -> None:
    gate = _gate_module()
    forbidden_header_value = "github-credential-must-not-reach-storage"
    signed_url = "https://storage.example.invalid/artifact.zip?signature=temporary"
    payload = b"bounded artifact bytes"
    response = _FakeUrlResponse(payload=payload)
    opener = _FakeUrlOpener(response)
    monkeypatch.setattr(gate, "_storage_download_opener", lambda: opener)

    assert gate._download_signed_artifact(signed_url, 4242) == payload

    assert len(opener.requests) == 1
    request = opener.requests[0]
    headers = {name.lower(): value for name, value in request.header_items()}
    assert "authorization" not in headers
    assert all("github_token" not in name for name in headers)
    assert all(forbidden_header_value not in value for value in headers.values())
    assert response.read_limits == [gate._MAX_ARTIFACT_BYTES + 1]
    assert gate._MAX_ARTIFACT_BYTES == 64 * 1024 * 1024


def test_storage_phase_rejects_an_oversized_response(monkeypatch) -> None:
    gate = _gate_module()
    monkeypatch.setattr(gate, "_MAX_ARTIFACT_BYTES", 8)
    response = _FakeUrlResponse(payload=b"123456789")
    monkeypatch.setattr(gate, "_storage_download_opener", lambda: _FakeUrlOpener(response))

    with pytest.raises(gate.TrustedGateError, match="artifact exceeds bounded size"):
        gate._download_signed_artifact("https://storage.example.invalid/artifact.zip", 4242)
    assert response.read_limits == [9]


def test_signed_storage_urls_are_never_printed_or_persisted(monkeypatch, tmp_path: Path, capsys) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    signed_urls = (
        "https://storage.example.invalid/candidate.zip?signature=candidate-secret",
        "https://storage.example.invalid/receipt.zip?signature=receipt-secret",
    )
    redirect_opener = _FakeUrlOpener(
        *(_FakeUrlResponse(status=302, headers={"Location": url}, fail_on_read=True) for url in signed_urls)
    )
    storage_opener = _FakeUrlOpener(
        _FakeUrlResponse(payload=evidence.candidate_archive()),
        _FakeUrlResponse(payload=evidence.receipt_archive()),
    )
    monkeypatch.setattr(gate, "_authenticated_redirect_opener", lambda: redirect_opener)
    monkeypatch.setattr(gate, "_storage_download_opener", lambda: storage_opener)

    candidate_archive, receipt_archive = gate.fetch_platform_archives(
        evidence.platform,
        evidence.selected(),
        _gate_arguments(),
        "github-token-must-stop-at-api",
    )
    record = gate.verify_platform(
        evidence.platform,
        evidence.selected(),
        _gate_arguments(),
        candidate_archive,
        receipt_archive,
        tmp_path,
    )
    checksums_path = tmp_path / "attest" / "linux-x64.checksums.txt"
    predicate_path = tmp_path / "attest" / "linux-x64.predicate.json"
    gate.write_subject_checksums(record, checksums_path)
    predicate_path.write_text(json.dumps(gate.build_predicate(record, _gate_arguments())), encoding="utf-8")

    captured = capsys.readouterr()
    persisted = "\n".join(
        (
            json.dumps(record, sort_keys=True),
            checksums_path.read_text(encoding="utf-8"),
            predicate_path.read_text(encoding="utf-8"),
        )
    )
    for signed_url in signed_urls:
        assert signed_url not in captured.out
        assert signed_url not in captured.err
        assert signed_url not in persisted


def test_gate_accepts_consistent_synthetic_evidence(tmp_path: Path) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    record = evidence.run(tmp_path)
    assert record["binary_sha256"] == evidence.binary_sha256
    assert record["candidate_artifact_id"] == str(evidence.candidate_artifact["id"])
    assert record["candidate_artifact_digest"] == evidence.candidate_artifact["digest"]


def test_gate_rejects_an_unexpected_third_file_in_the_candidate_artifact(tmp_path: Path) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    smuggled = _zip_bytes(
        {
            evidence.binary_name: evidence.binary,
            gate.MANIFEST_NAME: evidence._manifest_bytes(),
            "unexpected_extra_payload.bin": b"smuggled",
        }
    )
    with pytest.raises(gate.TrustedGateError):
        evidence.run(tmp_path, candidate_archive=smuggled)


@pytest.mark.parametrize(
    "field,value",
    [
        ("binary_sha256", "0" * 64),
        ("manifest_sha256", "0" * 64),
        ("candidate_artifact_id", "999999"),
        ("candidate_artifact_digest", "sha256:" + "0" * 64),
        ("candidate_artifact_name", "mt4-blst-candidate-elsewhere"),
        ("source_run_id", "1"),
        ("source_head_sha", "0" * 40),
        ("platform", "windows-x64"),
        ("binary_name", "other.so"),
        ("raw_bytes_persisted", True),
        ("qualification_input_source", "local_build_workspace"),
        ("blst_commit", "0" * 40),
        ("quicknet_chain_hash", "0" * 64),
        ("qualification_workflow_sha256", "9" * 64),
        ("lane_a_structural_pass", False),
        ("lane_b_real_quicknet_pass", False),
        ("readiness_promoted", True),
        ("dependency_profile_admitted", True),
    ],
)
def test_gate_rejects_every_receipt_forgery(tmp_path: Path, field, value) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    evidence.receipt[field] = value
    with pytest.raises(gate.TrustedGateError):
        evidence.run(tmp_path)


@pytest.mark.parametrize(
    "field,value",
    [
        ("output_binary_sha256", "0" * 64),
        ("output_binary_name", "other.so"),
        ("source_head_sha", "0" * 40),
        ("upstream_commit", "0" * 40),
        ("quicknet_chain_hash", "0" * 64),
        ("connector_promoted", True),
        ("proof_verified", True),
    ],
)
def test_gate_rejects_every_manifest_forgery(tmp_path: Path, field, value) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    evidence.manifest[field] = value
    with pytest.raises(gate.TrustedGateError):
        evidence.run(tmp_path)


def test_gate_writes_shasum_compatible_checksums_and_a_truthful_predicate(tmp_path: Path) -> None:
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    record = evidence.run(tmp_path)

    checksums = tmp_path / "linux-x64.checksums.txt"
    gate.write_subject_checksums(record, checksums)
    lines = checksums.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    for line in lines:
        digest, _, name = line.partition("  ")
        assert re.fullmatch(r"[0-9a-f]{64}", digest), line
        assert name in (evidence.binary_name, gate.MANIFEST_NAME), line

    predicate = gate.build_predicate(record, _gate_arguments())
    assert predicate["attestationSource"] == "trusted_default_branch_workflow_run"
    assert predicate["sourceQualification"]["event"] == "workflow_dispatch"
    assert predicate["sourceQualification"]["headBranch"] == "main"
    assert predicate["candidateArtifact"]["immutable"] is True
    assert predicate["dependencyAdmissionPerformed"] is False
    assert all(value is False for value in predicate["protectedFlags"].values())
    # The predicate must not overclaim what a cross-workflow attestation establishes.
    joined = " ".join(predicate["notProven"])
    assert "non-malicious" in joined
    assert "reproducible" in joined
    assert "SLSA" in joined


def test_predicate_does_not_duplicate_the_attesting_workflow_identity(tmp_path: Path) -> None:
    """The signer workflow identity is the certificate's job, not this predicate's.

    GitHub's artifact attestation authenticates the attesting workflow in the Sigstore certificate.
    Restating it as unauthenticated JSON inside a project-owned predicate adds no trust, and the
    value (GITHUB_WORKFLOW_REF) is a public workflow reference that static analysis classifies as a
    credential -- so it is omitted entirely rather than suppressed or renamed.
    """
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    record = evidence.run(tmp_path)

    predicate = gate.build_predicate(record, _gate_arguments())
    assert "attestingWorkflow" not in predicate, sorted(predicate)


def test_predicate_is_non_interfering_with_the_trusted_workflow_identity_argument(tmp_path: Path) -> None:
    """No value of that argument may change a single byte of the serialized predicate."""
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    record = evidence.run(tmp_path)

    def serialize(identity: str) -> str:
        arguments = _gate_arguments(trusted_workflow_identity=identity)
        return json.dumps(gate.build_predicate(record, arguments), sort_keys=True, separators=(",", ":"))

    baseline = serialize("trusted")
    for identity in (
        "owner/repo/.github/workflows/x.yml@refs/heads/main",
        "ghp_000000000000000000000000000000000000",
        "",
        "totally-different-value",
    ):
        assert serialize(identity) == baseline, identity
        assert identity not in baseline or identity == ""


def test_predicate_retains_every_real_evidence_field(tmp_path: Path) -> None:
    """Removing the redundant field must not quietly drop any actual evidence."""
    gate = _gate_module()
    evidence = _SyntheticEvidence(gate)
    record = evidence.run(tmp_path)
    predicate = gate.build_predicate(record, _gate_arguments())

    assert predicate["evidenceStatus"] == "ADMISSION_EVIDENCE_ONLY"
    assert predicate["attestationSource"] == "trusted_default_branch_workflow_run"
    source = predicate["sourceQualification"]
    for key in (
        "workflowPath",
        "workflowName",
        "workflowSha256",
        "workflowDigestApprovedOnDefaultBranch",
        "runId",
        "headSha",
        "headBranch",
        "event",
        "repository",
    ):
        assert key in source, key
    for key in (
        "candidateArtifact",
        "qualificationReceiptArtifact",
        "subjects",
        "upstream",
        "quicknet",
        "qualificationOutcomes",
        "qualificationInputSource",
        "rawProductionBytesPersisted",
        "protectedFlags",
        "dependencyAdmissionPerformed",
        "notProven",
    ):
        assert key in predicate, key
    assert predicate["rawProductionBytesPersisted"] is False
    assert predicate["dependencyAdmissionPerformed"] is False
    assert set(predicate["protectedFlags"]) == set(_PROTECTED_FLAGS)
    assert all(value is False for value in predicate["protectedFlags"].values())
    assert predicate["quicknet"]["chainHash"] == _QUICKNET_CHAIN_HASH
    assert predicate["upstream"]["blstCommit"] == _UPSTREAM_COMMIT


def test_repair_uses_no_suppression_marker_and_no_identifier_rename() -> None:
    """The fix must be structural: no scanner suppression, no cosmetic rename."""
    source = _read(_GATE_PATH)
    for suppression in ("# codeql", "codeql[", "lgtm[", "nosec", "# noqa: S105", "# type: ignore"):
        assert suppression not in source.lower(), suppression
    # The argument keeps its original name and is still accepted from the trusted workflow, so the
    # workflow file needs no change and the fix cannot be mistaken for a rename-to-evade.
    assert "--trusted-workflow-identity" in source
    gate = _gate_module()
    dests = {action.dest for action in gate._parser()._actions}
    assert "trusted_workflow_identity" in dests, sorted(dests)
    # But its value must never be written, logged or otherwise persisted.
    assert "arguments.trusted_workflow_identity" not in source


def test_gate_strips_the_api_credential_when_a_download_redirects_offsite() -> None:
    """A signed storage redirect must never receive the GitHub token."""
    gate = _gate_module()
    source = _read(_GATE_PATH)
    assert "class _StripAuthOnRedirect" in source
    assert "authorization" in source.lower()
    handler = gate._StripAuthOnRedirect()
    assert isinstance(handler, gate.urllib.request.HTTPRedirectHandler)


def test_gate_is_stdlib_only_and_never_executes_the_candidate() -> None:
    source = _read(_GATE_PATH)
    imports = set(re.findall(r"^import ([a-z_][a-z0-9_.]*)", source, re.MULTILINE))
    imports |= set(re.findall(r"^from ([a-z_][a-z0-9_.]*) import", source, re.MULTILINE))
    allowed = {
        "argparse",
        "hashlib",
        "json",
        "os",
        "sys",
        "urllib.error",
        "urllib.parse",
        "urllib.request",
        "zipfile",
        "pathlib",
        "__future__",
    }
    assert imports <= allowed, imports
    for forbidden in ("subprocess", "ctypes", "CDLL", "exec(", "eval("):
        assert forbidden not in source, forbidden
    # The token is read but never echoed.
    assert "print(token" not in source
    assert "GITHUB_TOKEN" in source


# ---------------------------------------------------------------------------------------------
# Receipt generator
# ---------------------------------------------------------------------------------------------


def test_receipt_records_a_lane_only_on_the_exact_success_token() -> None:
    module = _generator_module()
    assert module.LANE_SUCCESS_MARKER == "PASS"
    assert module._require_lane_pass("PASS", "lane") is True
    for bad in ("pass", "FAIL", "", "TRUE", "SKIPPED"):
        with pytest.raises(module.ManifestError):
            module._require_lane_pass(bad, "lane")


def test_receipt_canonicalises_both_artifact_digest_encodings() -> None:
    """upload-artifact emits bare hex; the REST API prefixes it. Both mean the same bytes."""
    module = _generator_module()
    canonical = "sha256:" + "a" * 64
    assert module._require_artifact_digest(canonical) == canonical
    assert module._require_artifact_digest("a" * 64) == canonical
    for bad in ("sha512:" + "a" * 64, "sha256:zz", "", "A" * 64, "a" * 63):
        with pytest.raises(module.ManifestError):
            module._require_artifact_digest(bad)


def test_gate_normalises_artifact_digests_before_comparing() -> None:
    """A representation difference must never be mistaken for a real digest match or mismatch."""
    gate = _gate_module()
    canonical = "sha256:" + "b" * 64
    assert gate.normalise_artifact_digest(canonical) == canonical
    assert gate.normalise_artifact_digest("b" * 64) == canonical
    for bad in ("sha256:zz", "", "B" * 64, "b" * 63, None):
        with pytest.raises(gate.TrustedGateError):
            gate.normalise_artifact_digest(bad)


def test_receipt_rejects_malformed_artifact_identity() -> None:
    module = _generator_module()
    assert module._require_decimal("123", "id") == "123"
    for bad in ("12a", "-1", ""):
        with pytest.raises(module.ManifestError):
            module._require_decimal(bad, "id")


def test_receipt_emits_all_protected_flags_false_and_post_merge_status() -> None:
    module = _generator_module()
    arguments = argparse.Namespace(
        receipt_schema_version="mt4-blst-qualification-receipt.v1",
        platform="linux-x64",
        source_run_id="1",
        source_run_attempt="1",
        source_head_sha="0" * 40,
        candidate_artifact_id="2",
        candidate_artifact_name="mt4-blst-candidate-linux-x64",
        candidate_artifact_digest="sha256:" + "a" * 64,
        binary_name="libmt4_s3a_blst_quicknet_shim.so",
        binary_sha256="b" * 64,
        manifest_sha256="c" * 64,
        qualification_workflow_identity="identity",
        qualification_workflow=str(_WORKFLOW_PATH),
        blst_release="v0.3.17",
        blst_commit=_UPSTREAM_COMMIT,
        quicknet_chain_hash=_QUICKNET_CHAIN_HASH,
        upstream_source_tree_digest="d" * 64,
        build_recipe_digest="e" * 64,
        lane_a_structural="PASS",
        lane_a_upstream_subgroup="PASS",
        lane_a_g1_decode_subgroup="PASS",
        lane_b_chain_root_binding="PASS",
        lane_b_real_quicknet="PASS",
    )
    receipt = module.build_receipt(arguments)
    for flag in _PROTECTED_FLAGS:
        assert receipt[flag] is False, flag
    assert receipt["raw_bytes_persisted"] is False
    assert receipt["attestation_execution_status"] == "POST_MERGE_REQUIRED"
    assert receipt["qualification_input_source"] == "github_artifact_fresh_download"
    assert receipt["candidate_artifact_immutable"] is True
    # The receipt binds the qualification workflow it was produced under.
    assert receipt["qualification_workflow_sha256"] == hashlib.sha256(_WORKFLOW_PATH.read_bytes()).hexdigest()


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
    for forbidden in ("urllib", "requests", "socket", "http.client", "api.github.com", "time."):
        assert forbidden not in source, forbidden
    assert "datetime" not in source
    assert "os.environ" not in source


def test_upstream_source_tree_digest_uses_git_objects_not_the_filesystem() -> None:
    """Windows and Linux must agree, so the digest binds git object bytes, not a checkout."""
    source = _read(_GENERATOR_PATH)
    assert '"ls-tree", "-r", "-z"' in source
    assert "cat-file" in source
    assert "--batch" in source
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


# ---------------------------------------------------------------------------------------------
# Committed claims must match reality
# ---------------------------------------------------------------------------------------------


def test_workflow_still_proves_exact_head_and_pinned_upstream() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "github.event.pull_request.head.sha" in workflow
    assert "QUALIFICATION_EXACT_HEAD=PASS" in workflow
    assert "QUALIFICATION_SOURCE_HEAD_MISMATCH" in workflow
    assert "BLST_COMMIT: " + _UPSTREAM_COMMIT in workflow
    assert "BLST_TAG_COMMIT_MISMATCH" in workflow
    assert "QUICKNET_CHAIN_HASH: " + _QUICKNET_CHAIN_HASH in workflow


def test_workflow_emits_evidence_markers_and_never_admission_claims() -> None:
    workflow = _read(_WORKFLOW_PATH)
    for marker in (
        "MT4_BLST_BUILD_PROVENANCE=PASS",
        "LANE_A_STRUCTURAL_RESULT=PASS",
        "LANE_A_UPSTREAM_SUBGROUP_RESULT=PASS",
        "LANE_B_CHAIN_ROOT_BINDING=PASS",
        "LANE_B_REAL_QUICKNET_VERIFY=PASS",
        "LANE_B_RAW_BYTES_PERSISTED=False",
        "QUALIFICATION_INPUT_SOURCE=github_artifact_fresh_download",
        "TRUSTED_ATTESTATION_EXECUTION=POST_MERGE_REQUIRED",
        "DEPENDENCY_PROFILE_ADMITTED=false",
        "READINESS_PROMOTED=false",
        "CONNECTOR_PROMOTED=false",
    ):
        assert marker in workflow, marker
    for forbidden in ("DEPENDENCY_ADMITTED=true", "VERIFIER_SELECTED", "PROOF_VERIFIED=true", "QUORUM_READY"):
        assert forbidden not in workflow, forbidden


def test_committed_evidence_never_self_promotes_pre_merge_attestation() -> None:
    fixture = _fixture()
    proofs = fixture["execution_proofs"]
    assert proofs["trusted_attestation_execution"] == "POST_MERGE_REQUIRED"
    assert proofs["attestation_verified"] == "POST_MERGE_REQUIRED"
    for key in (
        "windows_candidate_build",
        "linux_candidate_build",
        "windows_fresh_download_qualification",
        "linux_fresh_download_qualification",
    ):
        assert proofs[key] == "PENDING_CI", key
    # Attestations from the superseded pre-repair heads are historical only.
    superseded = proofs["superseded_attestations"]
    assert superseded["status"] == "HISTORICAL_ONLY"
    assert "6ce0ae0433cf31a5f82d59a309f904dfdf562512" in superseded["heads"]


def test_fixture_drops_the_overstated_same_binary_claim() -> None:
    ordering = _fixture()["ordering_contract"]
    assert "same_binary_throughout" not in ordering
    assert ordering["same_binary_throughout_claimed"] is False
    assert ordering["candidate_artifact_immutable"] is True
    assert ordering["qualification_input_source"] == "github_artifact_fresh_download"
    assert ordering["candidate_artifact_id_required"] is True
    assert ordering["candidate_artifact_digest_required"] is True
    assert ordering["artifact_uploaded_before_qualification"] is True
    assert ordering["artifact_overwrite_permitted"] is False
    assert ordering["attestation_execution_status"] == "POST_MERGE_REQUIRED"
    # The raw JSON must not carry the retired claim anywhere.
    assert '"same_binary_throughout": true' not in _read(_FIXTURE_PATH)


def test_fixture_records_the_trusted_attestation_architecture() -> None:
    contract = _fixture()["credential_isolation_contract"]
    assert "P1-MT4-ATTESTATION-WORKFLOW-DEFINITION-PR-CONTROLLED" in contract["findings_repaired"]
    assert "P2-MT4-QUALIFIED-SUBJECT-TOCTOU-NOT-FAIL-CLOSED" in contract["findings_repaired"]

    pull_request_workflow = contract["pull_request_workflow"]
    assert pull_request_workflow["definition_is_pull_request_controlled"] is True
    assert pull_request_workflow["privileged_job_present"] is False
    assert pull_request_workflow["id_token_present"] is False
    assert pull_request_workflow["attestations_present"] is False
    assert pull_request_workflow["attest_action_present"] is False
    assert sorted(pull_request_workflow["jobs"]) == sorted(_BUILD_JOBS + _QUALIFY_JOBS)

    trusted = contract["trusted_workflow"]
    assert trusted["trigger"] == "workflow_run"
    assert trusted["branch_filter"] == ["main"]
    assert trusted["executes_during_pull_request"] is False
    assert trusted["checks_out_pull_request_head"] is False
    assert trusted["executes_downloaded_binary"] is False
    assert trusted["executes_source_artifact_scripts"] is False
    for forbidden in ("pull_request", "pull_request_target", "workflow_dispatch", "repository_dispatch"):
        assert forbidden in trusted["forbidden_triggers"], forbidden

    approved = contract["approved_qualification_workflow_digest"]
    assert approved["stored_in_qualification_workflow_itself"] is False
    assert approved["circular"] is False
    assert approved["candidate_self_reported_digest_can_override"] is False

    assert "non-malicious" in contract["does_not_prove"]


def test_distinct_digest_vocabulary_is_recorded_and_not_conflated() -> None:
    digests = _fixture()["distinct_digests"]
    for key in (
        "artifact_archive_digest",
        "binary_digest",
        "manifest_digest",
        "qualification_receipt_digest",
    ):
        assert key in digests, key
    assert digests["attestation_subject_digests"] == ["binary_digest", "manifest_digest"]


def test_documentation_drops_the_no_window_overclaim_and_states_the_real_chain() -> None:
    doc = _read(_DOC_PATH)
    assert "no window exists" not in doc
    # Hyphenation varies between prose and identifiers, so compare on a normalised form.
    normalised = doc.lower().replace("-", " ")
    for required in (
        "immutable",
        "fresh download",
        "workflow_run",
        "post_merge_required",
        "artifact archive digest",
        "does not prove",
    ):
        assert required.replace("-", " ") in normalised, required


@pytest.mark.parametrize("flag", _PROTECTED_FLAGS)
def test_every_protected_flag_is_false_in_the_fixture(flag: str) -> None:
    assert _fixture()["protected_flags"][flag] is False


def test_generator_emits_all_protected_flags_false() -> None:
    module = _generator_module()
    assert set(module.PROTECTED_FLAGS) == set(_PROTECTED_FLAGS)
    assert module.EVIDENCE_STATUS == "ADMISSION_EVIDENCE_ONLY"
    assert module.SCHEMA_VERSION == "mt4-blst-dependency-admission-evidence.v1"


def test_linux_portable_recipe_is_explicit_and_windows_invents_no_flag() -> None:
    workflow = _read(_WORKFLOW_PATH)
    assert "./build.sh -D__BLST_PORTABLE__" in workflow
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
    assert "caveat" in portability["windows"]


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
        or "mt4_trusted_attestation" in path.read_text(encoding="utf-8")
    ]
    assert offenders == [], offenders


def test_contract_tests_kill_the_intended_supply_chain_mutants() -> None:
    mutant_to_guard = {
        # P1 -- trust boundary
        "grant a privileged permission in the pull_request workflow": "test_pull_request_workflow_defines_no_privileged_capability",
        "add id-token to the qualification workflow": "test_pull_request_workflow_defines_no_privileged_capability",
        "add attestations:write to the qualification workflow": "test_pull_request_workflow_defines_no_privileged_capability",
        "add actions/attest to the PR qualification workflow": "test_pull_request_workflow_defines_no_privileged_capability",
        "replace a pinned SHA with a moving tag": "test_every_action_is_pinned_to_a_full_commit_sha",
        "swap an action pin for a different commit": "test_action_pins_match_the_controller_packet_and_fixture",
        "trigger the trusted workflow from pull_request": "test_trusted_workflow_is_default_branch_anchored_only",
        "trigger the trusted workflow from pull_request_target": "test_trusted_workflow_is_default_branch_anchored_only",
        "trigger privileged attestation from workflow_dispatch": "test_trusted_workflow_is_default_branch_anchored_only",
        "drop workflow_run from the trusted workflow": "test_trusted_workflow_is_default_branch_anchored_only",
        "drop branches:[main] from the trusted workflow": "test_trusted_workflow_is_default_branch_anchored_only",
        "accept a non-main source run": "test_trusted_workflow_guard_rejects_fork_pr_and_non_main_sources",
        "accept a non-workflow_dispatch source run": "test_trusted_workflow_guard_rejects_fork_pr_and_non_main_sources",
        "accept a fork source run": "test_trusted_workflow_guard_rejects_fork_pr_and_non_main_sources",
        "substitute the source run identity": "test_gate_rejects_every_source_run_substitution",
        "check out a pull request head in the trusted workflow": "test_trusted_workflow_checks_out_the_source_head_not_a_pull_request_ref",
        "execute the untrusted candidate binary in the trusted workflow": "test_trusted_workflow_never_executes_the_candidate_binary_or_source_scripts",
        "execute a source-artifact script in the trusted workflow": "test_trusted_workflow_never_executes_the_candidate_binary_or_source_scripts",
        "widen trusted workflow permissions": "test_trusted_workflow_permissions_are_bounded",
        "forward the API token to a storage redirect": "test_gate_strips_the_api_credential_when_a_download_redirects_offsite",
        "let the API token reach a value written to disk": "test_verification_is_separated_from_the_credential_bearing_fetch",
        # P2 -- immutability and identity
        "qualify the local build output instead of a fresh download": "test_qualification_consumes_a_fresh_download_addressed_by_artifact_id",
        "wildcard the candidate artifact download": "test_qualification_consumes_a_fresh_download_addressed_by_artifact_id",
        "stop binding the candidate artifact id": "test_qualification_consumes_a_fresh_download_addressed_by_artifact_id",
        "overwrite the immutable artifact": "test_candidate_artifact_is_uploaded_before_any_qualification",
        "upload the artifact after qualification rather than before": "test_candidate_artifact_is_uploaded_before_any_qualification",
        "let a binary digest disagree with the manifest": "test_gate_rejects_every_manifest_forgery",
        "forge a receipt digest": "test_gate_rejects_every_receipt_forgery",
        "forge a receipt artifact id": "test_gate_rejects_every_receipt_forgery",
        "forge the source run in the receipt": "test_gate_rejects_every_receipt_forgery",
        "forge the source head in the receipt": "test_gate_rejects_every_receipt_forgery",
        "bypass the approved qualification workflow digest": "test_approved_qualification_workflow_digest_matches_the_committed_workflow",
        "promote a protected flag": "test_gate_rejects_every_receipt_forgery",
        "smuggle a third file into the candidate artifact": "test_gate_rejects_an_unexpected_third_file_in_the_candidate_artifact",
        "drop the fresh-download inventory gate": "test_downloaded_candidate_identity_is_bound_fail_closed",
        "sign subject-path instead of the validated checksums": "test_trusted_attestation_signs_validated_checksums_with_a_truthful_predicate",
        "claim SLSA build provenance for a cross-workflow attestation": "test_gate_writes_shasum_compatible_checksums_and_a_truthful_predicate",
        "restore the redundant attestingWorkflow predicate field": "test_predicate_does_not_duplicate_the_attesting_workflow_identity",
        "let the trusted-workflow-identity argument influence the predicate": "test_predicate_is_non_interfering_with_the_trusted_workflow_identity_argument",
        "drop a real evidence field while removing the redundant one": "test_predicate_retains_every_real_evidence_field",
        "silence the scanner with a suppression marker or a rename": "test_repair_uses_no_suppression_marker_and_no_identifier_rename",
        "keep the retired same_binary_throughout claim": "test_fixture_drops_the_overstated_same_binary_claim",
        "keep the 'no window exists' documentation overclaim": "test_documentation_drops_the_no_window_overclaim_and_states_the_real_chain",
        "record a lane as passed without its success token": "test_receipt_records_a_lane_only_on_the_exact_success_token",
        "compare artifact digests across encodings without normalising": "test_gate_normalises_artifact_digests_before_comparing",
        "reject the bare-hex artifact digest upload-artifact actually emits": "test_receipt_canonicalises_both_artifact_digest_encodings",
        "let the two platforms drift apart in lane logic": "test_the_two_qualification_jobs_run_identical_lane_logic",
        "collide the platform artifact names": "test_artifact_names_are_platform_distinct_and_non_colliding",
        "self-promote pre-merge attestation": "test_committed_evidence_never_self_promotes_pre_merge_attestation",
    }
    module_source = _read(Path(__file__).resolve())
    for mutant, guard in mutant_to_guard.items():
        assert "def " + guard + "(" in module_source, (mutant, guard)
    assert len(mutant_to_guard) >= 40
