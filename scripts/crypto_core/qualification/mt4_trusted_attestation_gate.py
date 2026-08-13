"""Trusted default-branch gate for MT4 blst dependency-admission EVIDENCE.

WHERE THIS RUNS.  Only from ``.github/workflows/crypto_core_mt4_trusted_attestation.yml``, which is
triggered by ``workflow_run`` restricted to the default branch.  A pull request can therefore never
cause this file to execute with the Sigstore signing capability: the workflow definition that grants
that capability must already exist on ``main``.

WHAT IT PROVES.  It re-derives, from scratch, every fact the later attestation will assert:

  * the source qualification run is THIS repository's expected workflow, dispatched on ``main``,
    at the expected head SHA, and it succeeded;
  * the four expected qualification jobs exist and succeeded;
  * exactly one candidate artifact and exactly one qualification receipt exist per platform;
  * the candidate artifact contains exactly the two expected files and nothing else;
  * the binary and manifest digests recomputed here match each other, the manifest's own claim,
    and the receipt;
  * the receipt names the same artifact id, the same service-reported archive digest, the same
    source run and the same source head SHA;
  * the qualification workflow blob at the source head matches the digest approved on ``main``;
  * every protected flag is still ``false``.

WHAT IT DOES NOT PROVE.  It does not execute, sandbox or analyse the candidate binary, and it makes
no claim that the build was reproducible or that the build code is non-malicious.  The downloaded
binary and manifest are DATA ONLY and are never executed here.

The receipt is a structured record, never a trust anchor: every value it carries is independently
re-derived above before it is believed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

PREDICATE_TYPE = (
    "https://github.com/demircaliskan2009-pixel/BIST_ELITE_CORE/attestations/crypto-core/mt4-blst-admission-evidence/v1"
)

MANIFEST_NAME = "mt4_blst_dependency_admission_manifest.json"
RECEIPT_NAME = "mt4_blst_qualification_receipt.json"

# Exactly the jobs the trusted gate requires to have succeeded in the source run.
REQUIRED_JOBS = (
    "build-linux-candidate",
    "build-windows-candidate",
    "qualify-linux-candidate",
    "qualify-windows-candidate",
)

# platform -> (candidate artifact name, receipt artifact name, native binary name)
PLATFORMS = {
    "linux-x64": (
        "mt4-blst-candidate-linux-x64",
        "mt4-blst-qualification-receipt-linux-x64",
        "libmt4_s3a_blst_quicknet_shim.so",
    ),
    "windows-x64": (
        "mt4-blst-candidate-windows-x64",
        "mt4-blst-qualification-receipt-windows-x64",
        "mt4_s3a_blst_quicknet_shim.dll",
    ),
}

PROTECTED_FLAGS = (
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

RECEIPT_LANE_FLAGS = (
    "lane_a_structural_pass",
    "lane_a_upstream_subgroup_pass",
    "lane_a_g1_decode_subgroup_pass",
    "lane_b_chain_root_binding_pass",
    "lane_b_real_quicknet_pass",
)

# A zip member must be a plain file name: no traversal, no absolute path, no directory component.
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class TrustedGateError(RuntimeError):
    """Any failure to prove a required binding.  There is no partial success."""


class _StripAuthOnRedirect(urllib.request.HTTPRedirectHandler):
    """Never forward the API credential if an ordinary API metadata request redirects."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if redirected is None:
            return None
        if urllib.parse.urlsplit(newurl).netloc != urllib.parse.urlsplit(req.full_url).netloc:
            redirected.headers = {
                name: value for name, value in redirected.headers.items() if name.lower() != "authorization"
            }
            redirected.unredirected_hdrs.pop("Authorization", None)
        return redirected


def _opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_StripAuthOnRedirect())


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Expose a redirect response to the caller instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _authenticated_redirect_opener() -> urllib.request.OpenerDirector:
    return urllib.request.build_opener(_NoRedirect())


def _storage_download_opener() -> urllib.request.OpenerDirector:
    # A storage redirect is unexpected.  Refusing it keeps the artifact source exactly equal to
    # the HTTPS Location selected by GitHub's authenticated artifact endpoint.
    return urllib.request.build_opener(_NoRedirect())


def _request(url: str, token: str, accept: str) -> urllib.request.Request:
    request = urllib.request.Request(url)  # noqa: S310 - fixed https API base, no user-supplied scheme
    request.add_header("Accept", accept)
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    # The ephemeral job token is used read-only and is never printed or persisted.
    request.add_header("Authorization", "Bearer " + token)
    return request


def api_json(api_url: str, path: str, token: str) -> dict:
    url = api_url.rstrip("/") + path
    if not url.startswith("https://"):
        raise TrustedGateError("api url must be https")
    try:
        with _opener().open(_request(url, token, "application/vnd.github+json"), timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:  # pragma: no cover - network failure path
        raise TrustedGateError(f"github api failed for {path} (status {error.code})") from error


_REDIRECT_STATUS_CODES = frozenset((301, 302, 303, 307, 308))


def _validated_storage_url(location: str) -> str:
    """Accept only an absolute, credential-free-to-call HTTPS storage URL.

    The URL itself can contain temporary authorization material in its query string.  Error
    markers therefore never interpolate it.
    """
    if not isinstance(location, str) or not location or location != location.strip():
        raise TrustedGateError("artifact redirect Location is malformed")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in location):
        raise TrustedGateError("artifact redirect Location is malformed")
    try:
        parsed = urllib.parse.urlsplit(location)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise TrustedGateError("artifact redirect Location is malformed") from None
    if parsed.scheme.lower() != "https":
        raise TrustedGateError("artifact redirect Location must be https")
    if parsed.username is not None or parsed.password is not None:
        raise TrustedGateError("artifact redirect Location must not contain userinfo")
    if not parsed.netloc or not hostname:
        raise TrustedGateError("artifact redirect Location must contain a hostname")
    if port == 0:
        raise TrustedGateError("artifact redirect Location is malformed")
    return location


def _resolve_artifact_redirect(api_url: str, repository: str, artifact_id: int, token: str) -> str:
    """Use the GitHub credential only to resolve the artifact's signed storage URL.

    The authenticated response body is intentionally never read.  A no-redirect opener makes the
    transition explicit and prevents a token-bearing Request from reaching the storage host.
    """
    url = f"{api_url.rstrip('/')}/repos/{repository}/actions/artifacts/{artifact_id}/zip"
    if not url.startswith("https://"):
        raise TrustedGateError("api url must be https")
    request = _request(url, token, "application/vnd.github+json")
    try:
        response = _authenticated_redirect_opener().open(request, timeout=60)
    except urllib.error.HTTPError as error:
        if error.code not in _REDIRECT_STATUS_CODES:
            raise TrustedGateError(
                f"artifact redirect resolution failed for {artifact_id} (status {error.code})"
            ) from None
        location = error.headers.get("Location")
        error.close()
    except urllib.error.URLError:
        raise TrustedGateError(f"artifact redirect resolution failed for {artifact_id}") from None
    else:
        with response:
            status = response.getcode()
            if status not in _REDIRECT_STATUS_CODES:
                raise TrustedGateError(f"artifact redirect required for {artifact_id}")
            location = response.headers.get("Location")
    if not location:
        raise TrustedGateError(f"artifact redirect Location missing for {artifact_id}")
    return _validated_storage_url(location)


def _download_signed_artifact(storage_url: str, artifact_id: int) -> bytes:
    """Download bytes from GitHub-selected storage with a wholly credential-free request."""
    storage_url = _validated_storage_url(storage_url)
    request = urllib.request.Request(storage_url)  # noqa: S310 - validated HTTPS GitHub redirect target
    try:
        with _storage_download_opener().open(request, timeout=300) as response:
            payload = response.read(_MAX_ARTIFACT_BYTES + 1)
    except urllib.error.HTTPError as error:  # pragma: no cover - network failure path
        raise TrustedGateError(f"artifact storage download failed for {artifact_id} (status {error.code})") from None
    except urllib.error.URLError:  # pragma: no cover - network failure path
        raise TrustedGateError(f"artifact storage download failed for {artifact_id}") from None
    if len(payload) > _MAX_ARTIFACT_BYTES:
        raise TrustedGateError("artifact exceeds bounded size")
    return payload


def download_artifact_zip(api_url: str, repository: str, artifact_id: int, token: str) -> bytes:
    """Resolve with GitHub authentication, then download from storage without credentials."""
    storage_url = _resolve_artifact_redirect(api_url, repository, artifact_id, token)
    return _download_signed_artifact(storage_url, artifact_id)


def extract_exact(payload: bytes, destination: Path, expected: tuple) -> dict:
    """Extract a zip whose member list must equal ``expected`` exactly.  Returns {name: bytes}."""
    destination.mkdir(parents=True, exist_ok=True)
    contents = {}
    with zipfile.ZipFile(_BytesReader(payload)) as archive:
        names = sorted(info.filename for info in archive.infolist())
        if names != sorted(expected):
            raise TrustedGateError("artifact inventory mismatch: " + ",".join(names))
        for name in names:
            # Reject anything that is not a plain file name in the archive root.
            if name != os.path.basename(name) or name in ("", ".", ".."):
                raise TrustedGateError("unsafe archive member: " + name)
            data = archive.read(name)
            if len(data) > _MAX_ARTIFACT_BYTES:
                raise TrustedGateError("archive member exceeds bounded size")
            (destination / name).write_bytes(data)
            contents[name] = data
    return contents


class _BytesReader:
    """Minimal seekable in-memory file so zipfile never touches an intermediate temp path."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._offset = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            chunk = self._data[self._offset :]
            self._offset = len(self._data)
            return chunk
        chunk = self._data[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._offset = offset
        elif whence == 1:
            self._offset += offset
        else:
            self._offset = len(self._data) + offset
        return self._offset

    def tell(self) -> int:
        return self._offset

    def seekable(self) -> bool:
        return True


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalise_artifact_digest(value: str) -> str:
    """Canonicalise the artifact ARCHIVE digest to ``sha256:<64 hex>``.

    The same bytes are reported in two encodings: ``actions/upload-artifact``'s ``artifact-digest``
    output is bare hex, while the artifacts REST API prefixes it with ``sha256:``.  Comparing raw
    strings would therefore fail-open on a representation difference rather than a real mismatch,
    so both sides are normalised before any equality check.
    """
    if not isinstance(value, str):
        raise TrustedGateError("artifact digest must be a string")
    body = value[len("sha256:") :] if value.startswith("sha256:") else value
    if len(body) != 64 or any(character not in "0123456789abcdef" for character in body):
        raise TrustedGateError("artifact digest must be 64 lowercase hex characters")
    return "sha256:" + body


def _require(condition: bool, marker: str) -> None:
    if not condition:
        raise TrustedGateError(marker)


def verify_source_run(run: dict, arguments: argparse.Namespace) -> None:
    """Bindings 1-7: the source run must be exactly the expected trusted main qualification run."""
    _require(run.get("repository", {}).get("full_name") == arguments.repository, "SOURCE_RUN_REPOSITORY_MISMATCH")
    _require(
        run.get("head_repository", {}).get("full_name") == arguments.repository,
        "SOURCE_RUN_HEAD_REPOSITORY_MISMATCH",
    )
    _require(run.get("path") == arguments.expected_workflow_path, "SOURCE_RUN_WORKFLOW_PATH_MISMATCH")
    _require(run.get("name") == arguments.expected_workflow_name, "SOURCE_RUN_WORKFLOW_NAME_MISMATCH")
    _require(run.get("event") == "workflow_dispatch", "SOURCE_RUN_EVENT_NOT_WORKFLOW_DISPATCH")
    _require(run.get("head_branch") == arguments.default_branch, "SOURCE_RUN_BRANCH_NOT_DEFAULT")
    _require(run.get("head_sha") == arguments.expected_head_sha, "SOURCE_RUN_HEAD_SHA_MISMATCH")
    _require(run.get("status") == "completed", "SOURCE_RUN_NOT_COMPLETED")
    _require(run.get("conclusion") == "success", "SOURCE_RUN_NOT_SUCCESSFUL")


def verify_jobs(jobs_payload: dict) -> None:
    """Binding 8: every required qualification job must exist and have succeeded."""
    by_name = {}
    for job in jobs_payload.get("jobs", []):
        by_name.setdefault(job.get("name"), []).append(job.get("conclusion"))
    for name in REQUIRED_JOBS:
        _require(name in by_name, "REQUIRED_JOB_MISSING:" + name)
        _require(by_name[name] == ["success"], "REQUIRED_JOB_NOT_SUCCESSFUL:" + name)


def select_artifacts(artifacts_payload: dict) -> dict:
    """Bindings 9-13: exactly one live artifact per expected name, with unique ids."""
    wanted = set()
    for candidate_name, receipt_name, _binary in PLATFORMS.values():
        wanted.add(candidate_name)
        wanted.add(receipt_name)

    selected = {}
    for artifact in artifacts_payload.get("artifacts", []):
        name = artifact.get("name")
        if name not in wanted:
            continue
        _require(name not in selected, "DUPLICATE_ARTIFACT_NAME:" + str(name))
        _require(artifact.get("expired") is False, "ARTIFACT_EXPIRED:" + str(name))
        digest = artifact.get("digest")
        _require(isinstance(digest, str) and digest.startswith("sha256:"), "ARTIFACT_DIGEST_MISSING:" + str(name))
        selected[name] = artifact

    missing = sorted(wanted - set(selected))
    _require(not missing, "EXPECTED_ARTIFACT_MISSING:" + ",".join(missing))

    identifiers = [artifact["id"] for artifact in selected.values()]
    _require(len(set(identifiers)) == len(identifiers), "ARTIFACT_ID_NOT_UNIQUE")
    return selected


def fetch_platform_archives(platform: str, selected: dict, arguments: argparse.Namespace, token: str) -> tuple:
    """Fetch both archives across the explicit authenticated-to-storage boundary.

    Authentication resolves only GitHub's signed redirect.  The bytes come from a distinct request
    that cannot receive the token.  Verification below remains a pure function of those bytes.
    """
    candidate_name, receipt_artifact_name, _binary = PLATFORMS[platform]
    return (
        download_artifact_zip(arguments.api_url, arguments.repository, selected[candidate_name]["id"], token),
        download_artifact_zip(arguments.api_url, arguments.repository, selected[receipt_artifact_name]["id"], token),
    )


def verify_platform(
    platform: str,
    selected: dict,
    arguments: argparse.Namespace,
    candidate_archive: bytes,
    receipt_archive: bytes,
    work_dir: Path,
) -> dict:
    """Bindings 14-27 for one platform.  Pure: no credential, no network.

    Returns the validated evidence record.
    """
    candidate_name, receipt_artifact_name, binary_name = PLATFORMS[platform]
    candidate = selected[candidate_name]
    receipt_artifact = selected[receipt_artifact_name]

    candidate_files = extract_exact(
        candidate_archive,
        work_dir / platform / "candidate",
        (binary_name, MANIFEST_NAME),
    )
    receipt_files = extract_exact(
        receipt_archive,
        work_dir / platform / "receipt",
        (RECEIPT_NAME,),
    )

    binary_sha256 = _sha256(candidate_files[binary_name])
    manifest_sha256 = _sha256(candidate_files[MANIFEST_NAME])
    manifest = json.loads(candidate_files[MANIFEST_NAME].decode("utf-8"))
    receipt = json.loads(receipt_files[RECEIPT_NAME].decode("utf-8"))

    # 17: the manifest must describe the exact bytes shipped beside it.
    _require(manifest.get("output_binary_sha256") == binary_sha256, "MANIFEST_BINARY_DIGEST_MISMATCH:" + platform)
    _require(manifest.get("output_binary_name") == binary_name, "MANIFEST_BINARY_NAME_MISMATCH:" + platform)

    # 18-19: the receipt must describe the same independently recomputed digests.
    _require(receipt.get("binary_sha256") == binary_sha256, "RECEIPT_BINARY_DIGEST_MISMATCH:" + platform)
    _require(receipt.get("manifest_sha256") == manifest_sha256, "RECEIPT_MANIFEST_DIGEST_MISMATCH:" + platform)
    _require(receipt.get("binary_name") == binary_name, "RECEIPT_BINARY_NAME_MISMATCH:" + platform)
    _require(receipt.get("platform") == platform, "RECEIPT_PLATFORM_MISMATCH:" + platform)

    # 20-21: the receipt must name the real artifact identity reported by the artifact service.
    _require(
        receipt.get("candidate_artifact_id") == str(candidate["id"]),
        "RECEIPT_ARTIFACT_ID_MISMATCH:" + platform,
    )
    _require(
        receipt.get("candidate_artifact_name") == candidate_name,
        "RECEIPT_ARTIFACT_NAME_MISMATCH:" + platform,
    )
    _require(
        normalise_artifact_digest(receipt.get("candidate_artifact_digest", ""))
        == normalise_artifact_digest(candidate["digest"]),
        "RECEIPT_ARTIFACT_DIGEST_MISMATCH:" + platform,
    )

    # 22-24: source run and head must match the trusted workflow_run event, not self-report.
    _require(receipt.get("source_run_id") == str(arguments.source_run_id), "RECEIPT_SOURCE_RUN_MISMATCH:" + platform)
    _require(
        receipt.get("source_head_sha") == arguments.expected_head_sha,
        "RECEIPT_SOURCE_HEAD_MISMATCH:" + platform,
    )
    _require(
        manifest.get("source_head_sha") == arguments.expected_head_sha,
        "MANIFEST_SOURCE_HEAD_MISMATCH:" + platform,
    )

    # 25: every qualification lane must be recorded as passed.
    for flag in RECEIPT_LANE_FLAGS:
        _require(receipt.get(flag) is True, "RECEIPT_LANE_NOT_PASSED:" + platform + ":" + flag)
    _require(receipt.get("raw_bytes_persisted") is False, "RECEIPT_RAW_BYTES_PERSISTED:" + platform)
    _require(
        receipt.get("qualification_input_source") == "github_artifact_fresh_download",
        "RECEIPT_QUALIFICATION_INPUT_NOT_FRESH_DOWNLOAD:" + platform,
    )

    # 26: no protected state may have been promoted anywhere in the evidence.
    for flag in PROTECTED_FLAGS:
        _require(manifest.get(flag) is False, "MANIFEST_PROTECTED_FLAG_NOT_FALSE:" + platform + ":" + flag)
        _require(receipt.get(flag) is False, "RECEIPT_PROTECTED_FLAG_NOT_FALSE:" + platform + ":" + flag)

    # 27: the pinned cryptographic identities must be untouched.
    _require(manifest.get("upstream_commit") == arguments.blst_commit, "MANIFEST_BLST_COMMIT_MISMATCH:" + platform)
    _require(receipt.get("blst_commit") == arguments.blst_commit, "RECEIPT_BLST_COMMIT_MISMATCH:" + platform)
    _require(
        manifest.get("quicknet_chain_hash") == arguments.quicknet_chain_hash,
        "MANIFEST_QUICKNET_ROOT_MISMATCH:" + platform,
    )
    _require(
        receipt.get("quicknet_chain_hash") == arguments.quicknet_chain_hash,
        "RECEIPT_QUICKNET_ROOT_MISMATCH:" + platform,
    )

    # The receipt's own view of the qualification workflow must equal the digest approved on main.
    _require(
        receipt.get("qualification_workflow_sha256") == arguments.approved_qualification_workflow_sha256,
        "RECEIPT_QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED:" + platform,
    )

    return {
        "platform": platform,
        "binary_name": binary_name,
        "binary_sha256": binary_sha256,
        "manifest_sha256": manifest_sha256,
        "candidate_artifact_id": str(candidate["id"]),
        "candidate_artifact_name": candidate_name,
        "candidate_artifact_digest": normalise_artifact_digest(candidate["digest"]),
        "receipt_artifact_id": str(receipt_artifact["id"]),
        "receipt_artifact_name": receipt_artifact_name,
        "receipt_artifact_digest": normalise_artifact_digest(receipt_artifact["digest"]),
        "receipt_sha256": _sha256(receipt_files[RECEIPT_NAME]),
        "upstream_source_tree_digest": manifest.get("upstream_source_tree_digest"),
        "build_recipe_digest": manifest.get("build_recipe_digest"),
    }


def write_subject_checksums(record: dict, path: Path) -> None:
    """shasum-compatible: '<hex><space><flag><name>'.  Text mode flag is a single space."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        record["binary_sha256"] + "  " + record["binary_name"],
        record["manifest_sha256"] + "  " + MANIFEST_NAME,
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_predicate(record: dict, arguments: argparse.Namespace) -> dict:
    """Truthful cross-workflow evidence.

    This deliberately does NOT claim SLSA build provenance: the attesting workflow did not build the
    binary, it validated an immutable artifact produced by a separate unprivileged qualification run.
    """
    return {
        "evidenceStatus": "ADMISSION_EVIDENCE_ONLY",
        "attestationSource": "trusted_default_branch_workflow_run",
        "attestingWorkflow": arguments.trusted_workflow_identity,
        "sourceQualification": {
            "workflowPath": arguments.expected_workflow_path,
            "workflowName": arguments.expected_workflow_name,
            "workflowSha256": arguments.approved_qualification_workflow_sha256,
            "workflowDigestApprovedOnDefaultBranch": True,
            "runId": str(arguments.source_run_id),
            "headSha": arguments.expected_head_sha,
            "headBranch": arguments.default_branch,
            "event": "workflow_dispatch",
            "repository": arguments.repository,
        },
        "candidateArtifact": {
            "id": record["candidate_artifact_id"],
            "name": record["candidate_artifact_name"],
            "archiveDigest": record["candidate_artifact_digest"],
            "immutable": True,
        },
        "qualificationReceiptArtifact": {
            "id": record["receipt_artifact_id"],
            "name": record["receipt_artifact_name"],
            "archiveDigest": record["receipt_artifact_digest"],
            "receiptSha256": record["receipt_sha256"],
        },
        "subjects": {
            "binaryName": record["binary_name"],
            "binarySha256": record["binary_sha256"],
            "manifestName": MANIFEST_NAME,
            "manifestSha256": record["manifest_sha256"],
        },
        "upstream": {
            "blstRelease": arguments.blst_release,
            "blstCommit": arguments.blst_commit,
            "sourceTreeDigest": record["upstream_source_tree_digest"],
            "buildRecipeDigest": record["build_recipe_digest"],
        },
        "quicknet": {"chainHash": arguments.quicknet_chain_hash},
        "qualificationOutcomes": dict.fromkeys(RECEIPT_LANE_FLAGS, True),
        "qualificationInputSource": "github_artifact_fresh_download",
        "rawProductionBytesPersisted": False,
        "protectedFlags": dict.fromkeys(PROTECTED_FLAGS, False),
        "dependencyAdmissionPerformed": False,
        "notProven": [
            "the qualification build code is non-malicious",
            "the build is bit-for-bit reproducible",
            "SLSA build level of the attesting workflow",
        ],
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Trusted default-branch MT4 blst attestation gate.")
    for name in (
        "--repository",
        "--source-run-id",
        "--expected-head-sha",
        "--expected-workflow-path",
        "--expected-workflow-name",
        "--trusted-workflow-identity",
        "--approved-qualification-workflow-sha256",
        "--qualification-workflow",
        "--blst-release",
        "--blst-commit",
        "--quicknet-chain-hash",
        "--work-dir",
    ):
        parser.add_argument(name, required=True)
    parser.add_argument("--default-branch", default="main")
    parser.add_argument("--api-url", default="https://api.github.com")
    return parser


def main(argv: list) -> int:
    arguments = _parser().parse_args(argv)
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise TrustedGateError("GITHUB_TOKEN_REQUIRED")

    # The qualification workflow definition at the source head must be the one approved on main.
    # This is what stops a pull request from changing qualification semantics and forging a PASS.
    actual_workflow_digest = _sha256(Path(arguments.qualification_workflow).read_bytes())
    print("QUALIFICATION_WORKFLOW_SHA256_ACTUAL=" + actual_workflow_digest)
    print("QUALIFICATION_WORKFLOW_SHA256_APPROVED=" + arguments.approved_qualification_workflow_sha256)
    _require(
        actual_workflow_digest == arguments.approved_qualification_workflow_sha256,
        "QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED",
    )

    base = "/repos/" + arguments.repository + "/actions/runs/" + str(arguments.source_run_id)
    run = api_json(arguments.api_url, base, token)
    verify_source_run(run, arguments)
    print("SOURCE_RUN_BINDING=PASS")

    verify_jobs(api_json(arguments.api_url, base + "/jobs?per_page=100", token))
    print("SOURCE_RUN_JOBS=PASS")

    selected = select_artifacts(api_json(arguments.api_url, base + "/artifacts?per_page=100", token))
    print("SOURCE_RUN_ARTIFACTS=PASS")

    work_dir = Path(arguments.work_dir)
    for platform in sorted(PLATFORMS):
        candidate_archive, receipt_archive = fetch_platform_archives(platform, selected, arguments, token)
        record = verify_platform(platform, selected, arguments, candidate_archive, receipt_archive, work_dir)
        checksums_path = work_dir / "attest" / (platform + ".checksums.txt")
        predicate_path = work_dir / "attest" / (platform + ".predicate.json")
        write_subject_checksums(record, checksums_path)
        predicate_path.write_text(
            json.dumps(build_predicate(record, arguments), sort_keys=True, separators=(",", ":")),
            encoding="utf-8",
        )
        print("TRUSTED_PLATFORM_VALIDATED=" + platform)
        print(f"  binary={record['binary_name']} sha256={record['binary_sha256']}")
        print(f"  manifest_sha256={record['manifest_sha256']}")
        print(f"  candidate_artifact_id={record['candidate_artifact_id']} digest={record['candidate_artifact_digest']}")
        print(f"  receipt_artifact_id={record['receipt_artifact_id']} digest={record['receipt_artifact_digest']}")

    print("TRUSTED_ATTESTATION_GATE=PASS")
    print("DEPENDENCY_PROFILE_ADMITTED=false")
    print("READINESS_PROMOTED=false")
    print("CONNECTOR_PROMOTED=false")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
