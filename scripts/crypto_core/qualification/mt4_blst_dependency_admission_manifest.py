"""Deterministic MT4 blst dependency-admission EVIDENCE manifest generator.

SCOPE.  This produces evidence for a FUTURE governed dependency-admission decision.  It admits no
dependency, selects no verifier profile, admits no fixture corpus, and promotes no readiness,
connector, proof, quorum or machine-time state.  Every protected field it emits is exactly ``false``.

DETERMINISM.  The manifest is a pure function of explicitly supplied metadata plus the content of
explicitly named files and one pinned upstream git commit.  There is no network access, no GitHub
API call, no wall-clock trust input, no environment scraping and no arbitrary JSON passthrough.
Re-running with identical inputs over the identical pinned commit yields byte-identical output.

The upstream source-tree digest is computed from the pinned GIT OBJECT inventory rather than from an
OS-materialised checkout, so Windows and Linux runners agree despite line-ending and filesystem
presentation differences.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

SCHEMA_VERSION = "mt4-blst-dependency-admission-evidence.v1"
EVIDENCE_STATUS = "ADMISSION_EVIDENCE_ONLY"

# Domain separators keep independently derived digests from ever colliding.
_SOURCE_TREE_DOMAIN = b"mt4-blst-dependency-admission-evidence.v1/upstream-source-tree\x00"
_BUILD_RECIPE_DOMAIN = b"mt4-blst-dependency-admission-evidence.v1/build-recipe\x00"

# Portability vocabulary.  PORTABILITY_UNPROVEN must never be presented as PORTABLE.
PORTABLE_MODES = ("PORTABLE", "TARGET_BOUND", "PORTABILITY_UNPROVEN")

# Protected state.  This slice may never flip any of these.
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

# Exactly the fields that define the RECIPE.  The output binary digest is deliberately excluded so
# the recipe digest can never be circular, and run ids / timestamps are excluded so it stays
# deterministic.
_BUILD_RECIPE_FIELDS = (
    "upstream_repository",
    "upstream_release",
    "upstream_commit",
    "upstream_license_sha256",
    "upstream_source_tree_digest_algorithm",
    "upstream_source_tree_digest",
    "shim_source_sha256",
    "probe_source_sha256",
    "qualification_workflow_sha256",
    "compiler_id",
    "compiler_version",
    "target_identity",
    "build_command",
    "build_flags",
    "portable_mode",
    "output_binary_name",
    "actions_checkout_commit",
    "actions_setup_python_commit",
    "actions_attest_commit",
    "actions_upload_artifact_commit",
    "actions_download_artifact_commit",
)


class ManifestError(RuntimeError):
    """Raised for any bounded input or upstream-inventory fault; never a partial manifest."""


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(str(path), "rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _git(checkout: Path, arguments: list, capture_binary: bool = False):
    command = ["git", "-C", str(checkout)] + arguments
    completed = subprocess.run(  # noqa: S603 - fixed argv, no shell, no caller-supplied binary
        command, capture_output=True, check=False
    )
    if completed.returncode != 0:
        raise ManifestError("git command failed: " + " ".join(arguments[:2]))
    return completed.stdout if capture_binary else completed.stdout.decode("utf-8")


def upstream_source_tree_digest(checkout: Path, commit: str) -> str:
    """Digest the pinned git object inventory: mode, type, path and blob content identity.

    Uses ``git ls-tree -r -z`` so paths are NUL-delimited and never ambiguous, and binds SHA-256 of
    the exact ``git cat-file`` blob bytes.  Trees are not emitted by ``-r``; submodule entries bind
    their commit oid because they have no content in this repository.  Symlinks are bound as blob
    content (their target text) and are never followed on the filesystem.
    """
    raw = _git(checkout, ["ls-tree", "-r", "-z", commit], capture_binary=True)
    entries = []
    for record in raw.split(b"\x00"):
        if not record:
            continue
        header, _, path_bytes = record.partition(b"\t")
        if not path_bytes:
            raise ManifestError("malformed ls-tree record: missing path separator")
        fields = header.decode("utf-8").split(" ")
        if len(fields) != 3:
            raise ManifestError("malformed ls-tree header")
        mode, object_type, oid = fields
        if object_type not in ("blob", "commit"):
            raise ManifestError("unexpected upstream object type: " + object_type)
        entries.append((path_bytes, mode, object_type, oid))
    if not entries:
        raise ManifestError("empty upstream inventory")

    paths = [entry[0] for entry in entries]
    if len(set(paths)) != len(paths):
        raise ManifestError("duplicate path in upstream inventory")
    entries.sort(key=lambda entry: entry[0])

    # One batched cat-file pass keeps this deterministic without spawning a process per blob.
    blob_oids = [entry[3] for entry in entries if entry[2] == "blob"]
    contents = _batch_blob_digests(checkout, blob_oids)

    digest = hashlib.sha256()
    digest.update(_SOURCE_TREE_DOMAIN)
    for path_bytes, mode, object_type, oid in entries:
        if object_type == "blob":
            identity = contents[oid]
        else:
            identity = "submodule:" + oid
        digest.update(mode.encode("ascii"))
        digest.update(b"\x00")
        digest.update(object_type.encode("ascii"))
        digest.update(b"\x00")
        digest.update(path_bytes)
        digest.update(b"\x00")
        digest.update(identity.encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def _batch_blob_digests(checkout: Path, oids: list) -> dict:
    """Return {oid: sha256(blob bytes)} using a single ``git cat-file --batch`` process."""
    unique = sorted(set(oids))
    if not unique:
        return {}
    command = ["git", "-C", str(checkout), "cat-file", "--batch"]
    process = subprocess.Popen(  # noqa: S603 - fixed argv, no shell
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    request = ("\n".join(unique) + "\n").encode("ascii")
    stdout, _ = process.communicate(request)
    if process.returncode != 0:
        raise ManifestError("git cat-file --batch failed")

    digests = {}
    offset = 0
    for oid in unique:
        newline = stdout.find(b"\n", offset)
        if newline < 0:
            raise ManifestError("truncated cat-file stream")
        header = stdout[offset:newline].decode("ascii").split(" ")
        if len(header) != 3 or header[0] != oid or header[1] != "blob":
            raise ManifestError("unexpected cat-file header for " + oid)
        size = int(header[2])
        start = newline + 1
        end = start + size
        if end > len(stdout):
            raise ManifestError("truncated blob payload")
        digests[oid] = hashlib.sha256(stdout[start:end]).hexdigest()
        offset = end + 1  # trailing newline after payload
    if len(digests) != len(unique):
        raise ManifestError("incomplete blob inventory")
    return digests


def canonical_json(payload: dict) -> str:
    """Stable serialization: sorted keys, fixed separators, ASCII-escaped, no NaN."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)


def build_recipe_digest(manifest: dict) -> str:
    recipe = {name: manifest[name] for name in _BUILD_RECIPE_FIELDS}
    return hashlib.sha256(_BUILD_RECIPE_DOMAIN + canonical_json(recipe).encode("utf-8")).hexdigest()


def _require_hex(value: str, name: str, length: int) -> str:
    if type(value) is not str or len(value) != length:
        raise ManifestError(name + " must be " + str(length) + " hex characters")
    if any(char not in "0123456789abcdef" for char in value):
        raise ManifestError(name + " must be lowercase hex")
    return value


def build_manifest(arguments: argparse.Namespace) -> dict:
    if arguments.portable_mode not in PORTABLE_MODES:
        raise ManifestError("portable_mode must be one of " + ", ".join(PORTABLE_MODES))

    upstream_checkout = Path(arguments.upstream_checkout)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "evidence_status": EVIDENCE_STATUS,
        "repository": arguments.repository,
        "source_head_sha": _require_hex(arguments.source_head_sha, "source_head_sha", 40),
        "upstream_repository": arguments.upstream_repository,
        "upstream_release": arguments.upstream_release,
        "upstream_commit": _require_hex(arguments.upstream_commit, "upstream_commit", 40),
        "upstream_license": arguments.upstream_license,
        "upstream_license_sha256": _sha256_file(Path(arguments.upstream_license_path)),
        "upstream_source_tree_digest_algorithm": (
            "sha256-over-git-ls-tree-r-z-inventory-binding-mode-type-path-and-blob-sha256"
        ),
        "upstream_source_tree_digest": upstream_source_tree_digest(upstream_checkout, arguments.upstream_commit),
        "runner_os": arguments.runner_os,
        "runner_arch": arguments.runner_arch,
        "runner_image": arguments.runner_image,
        "runner_image_version": arguments.runner_image_version,
        "compiler_id": arguments.compiler_id,
        "compiler_version": arguments.compiler_version,
        "target_identity": arguments.target_identity,
        "build_command": arguments.build_command,
        "build_flags": arguments.build_flags,
        "portable_mode": arguments.portable_mode,
        "portability_evidence": arguments.portability_evidence,
        "blst_static_library_sha256": _sha256_file(Path(arguments.blst_static_library)),
        "shim_source_sha256": _sha256_file(Path(arguments.shim_source)),
        "probe_source_sha256": _sha256_file(Path(arguments.probe_source)),
        "qualification_workflow_sha256": _sha256_file(Path(arguments.qualification_workflow)),
        "output_binary_name": arguments.output_binary_name,
        "output_binary_sha256": _sha256_file(Path(arguments.output_binary)),
        "actions_checkout_commit": _require_hex(arguments.actions_checkout_commit, "checkout pin", 40),
        "actions_setup_python_commit": _require_hex(arguments.actions_setup_python_commit, "setup-python pin", 40),
        "actions_attest_commit": _require_hex(arguments.actions_attest_commit, "attest pin", 40),
        "actions_upload_artifact_commit": _require_hex(
            arguments.actions_upload_artifact_commit, "upload-artifact pin", 40
        ),
        # download-artifact carries the evidence across the credential trust boundary from the
        # unprivileged qualification job to the privileged attestation job, so it is recipe input.
        "actions_download_artifact_commit": _require_hex(
            arguments.actions_download_artifact_commit, "download-artifact pin", 40
        ),
        "quicknet_chain_hash": arguments.quicknet_chain_hash,
        "quicknet_scheme": arguments.quicknet_scheme,
        "dependency_profile_id": arguments.dependency_profile_id,
        "fixture_corpus_id": arguments.fixture_corpus_id,
        "verification_policy_id": arguments.verification_policy_id,
        "qualification_required": True,
        "artifact_attestation_required": True,
    }

    # The recipe digest is derived from recipe fields only: never from the output digest, a run id
    # or a wall clock, so it identifies the recipe rather than one execution of it.
    manifest["build_recipe_digest"] = build_recipe_digest(manifest)

    for flag in PROTECTED_FLAGS:
        manifest[flag] = False

    # Operational, non-trust metadata is recorded OUTSIDE the recipe digest.
    manifest["operational_metadata"] = {
        "workflow_run_id": arguments.workflow_run_id,
        "workflow_run_attempt": arguments.workflow_run_attempt,
        "ci_workflow_identity": arguments.ci_workflow_identity,
        "note": "operational only; excluded from build_recipe_digest and never trust evidence",
    }
    return manifest


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate the MT4 blst admission-evidence manifest.")
    for name in (
        "--output",
        "--repository",
        "--source-head-sha",
        "--upstream-repository",
        "--upstream-release",
        "--upstream-commit",
        "--upstream-license",
        "--upstream-license-path",
        "--upstream-checkout",
        "--runner-os",
        "--runner-arch",
        "--runner-image",
        "--runner-image-version",
        "--compiler-id",
        "--compiler-version",
        "--target-identity",
        "--build-command",
        "--build-flags",
        "--portable-mode",
        "--portability-evidence",
        "--blst-static-library",
        "--shim-source",
        "--probe-source",
        "--qualification-workflow",
        "--output-binary",
        "--output-binary-name",
        "--actions-checkout-commit",
        "--actions-setup-python-commit",
        "--actions-attest-commit",
        "--actions-upload-artifact-commit",
        "--actions-download-artifact-commit",
        "--quicknet-chain-hash",
        "--quicknet-scheme",
        "--dependency-profile-id",
        "--fixture-corpus-id",
        "--verification-policy-id",
        "--workflow-run-id",
        "--workflow-run-attempt",
        "--ci-workflow-identity",
    ):
        parser.add_argument(name, required=True)
    return parser


def main(argv: list) -> int:
    arguments = _parser().parse_args(argv)
    manifest = build_manifest(arguments)
    serialized = canonical_json(manifest)
    Path(arguments.output).write_bytes(serialized.encode("utf-8"))
    print("MT4_BLST_MANIFEST_PATH=" + str(arguments.output))
    print("MT4_BLST_MANIFEST_SHA256=" + hashlib.sha256(serialized.encode("utf-8")).hexdigest())
    print("MT4_BLST_OUTPUT_BINARY_SHA256=" + manifest["output_binary_sha256"])
    print("MT4_BLST_BUILD_RECIPE_DIGEST=" + manifest["build_recipe_digest"])
    print("MT4_BLST_UPSTREAM_SOURCE_TREE_DIGEST=" + manifest["upstream_source_tree_digest"])
    print("MT4_BLST_PORTABLE_MODE=" + manifest["portable_mode"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
