"""Source-pinned offline build of fresh qualification candidates, never admission.

Build tooling must be provisioned by the operator/runner. This script installs
nothing, fetches nothing, writes only the explicit output directory and refuses
to reuse one. A receipt binds actual artifacts and command results; it is not a
trusted attestation and cannot authorize operational native loading.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

from scripts.crypto_core.qualification.c_native_formats import QualificationError, inspect_image
from scripts.crypto_core.qualification.c_rfc3161_probe import EXPORTS
from scripts.crypto_core.qualification.mt4_blst_dependency_admission_manifest import upstream_source_tree_digest

OPENSSL_SOURCE = "603f5602e2eef00d77fbd429d34dcd5822bb301757a1bc9cdb24c670f1eb859a"
BLST_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
BLST_TREE = "5a709c19ef7a1b9798ad58728fc5dd3b4d2026ecdd0342ebf8546c5950cea006"


def run(args, cwd, records):
    completed = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)  # noqa: S603 -- operator-provisioned compiler, fixed argument arrays
    records.append(
        {"command": list(map(str, args)), "cwd": str(cwd), "exit": completed.returncode, "output": completed.stdout}
    )
    if completed.returncode:
        raise QualificationError("BUILD_COMMAND_FAILED:" + str(args[0]))
    return completed.stdout.strip()


def build(archive, blst, output):
    archive, blst, output = Path(archive).resolve(), Path(blst).resolve(), Path(output).absolute()
    repo = Path(__file__).resolve().parents[3]
    if hashlib.sha256(archive.read_bytes()).hexdigest() != OPENSSL_SOURCE:
        raise QualificationError("OPENSSL_SOURCE_DIGEST")
    records = []
    if run(["git", "rev-parse", "HEAD"], blst, records) != BLST_COMMIT:
        raise QualificationError("BLST_SOURCE_CHECKOUT")
    if upstream_source_tree_digest(blst, BLST_COMMIT) != BLST_TREE:
        raise QualificationError("BLST_SOURCE_TREE")
    # No checkout byte is executed: only the verified immutable git archive is exported below.
    if output.exists():
        raise QualificationError("FRESH_OUTPUT_DIRECTORY_REQUIRED")
    output.mkdir(parents=True)
    receipt = {
        "evidence_class": "CANDIDATE_TEST_EVIDENCE_ONLY",
        "operational_use_approved": False,
        "source_authentication": "PREVIOUSLY_AUTHENTICATED_EXACT_ARCHIVE_DIGEST",
        "openssl_source_sha256": OPENSSL_SOURCE,
        "blst_commit": BLST_COMMIT,
        "blst_source_tree_sha256": BLST_TREE,
        "host": platform.platform(),
        "python": sys.version,
        "commands": records,
        "artifacts": {},
        "status": "BUILD_INCOMPLETE",
    }
    try:
        required_tools = ("cl", "nmake", "perl", "nasm") if os.name == "nt" else ("cc", "make", "perl")
        missing = [tool for tool in required_tools if not shutil.which(tool)]
        receipt["missing_build_tools"] = missing
        if missing:
            raise QualificationError("BUILD_TOOLS_UNAVAILABLE:" + ",".join(missing))
        with tarfile.open(archive, "r:gz") as source:
            members = source.getmembers()
            for member in members:
                target = (output / member.name).resolve()
                if output.resolve() not in target.parents or not (member.isfile() or member.isdir()):
                    raise QualificationError("SOURCE_ARCHIVE_MEMBER")
            # All members were validated; no links, devices or escaping names are permitted.
            source.extractall(output, members=members, filter="data")  # noqa: S202 -- explicit complete member validation
        openssl = output / "openssl-3.5.9"
        local_blst = output / "blst"
        # Export immutable git objects; never execute checkout bytes or copy ignored files.
        git_executable = shutil.which("git")
        if git_executable is None:
            raise QualificationError("BUILD_TOOL_UNAVAILABLE:git")
        exported = subprocess.run(  # noqa: S603 -- fixed git archive of the pinned commit, resolved operator tool
            [git_executable, "archive", "--format=tar", BLST_COMMIT], cwd=blst, capture_output=True, check=True
        ).stdout
        receipt["blst_source_archive_sha256"] = hashlib.sha256(exported).hexdigest()
        local_blst.mkdir()
        with tarfile.open(fileobj=io.BytesIO(exported)) as source:
            for member in source.getmembers():
                target = (local_blst / member.name).resolve()
                if local_blst.resolve() not in target.parents or not (member.isfile() or member.isdir()):
                    raise QualificationError("BLST_ARCHIVE_MEMBER")
            source.extractall(local_blst, filter="data")  # noqa: S202 -- pinned git objects with complete member validation
        shim = repo / "scripts/crypto_core/qualification"
        is_windows = os.name == "nt"
        options = ["no-shared", "no-module", "no-dso", "no-engine", "no-tests"]
        if is_windows:
            for tool in ("cl", "nmake", "perl", "nasm"):
                if not shutil.which(tool):
                    raise QualificationError("BUILD_TOOL_UNAVAILABLE:" + tool)
            run(["perl", "Configure", "VC-WIN64A", *options, "--release"], openssl, records)
            run(["nmake", "build_libs"], openssl, records)
            run(["cmd.exe", "/d", "/c", "build.bat"], local_blst, records)
            target = output / "c_rfc3161.dll"
            run(
                [
                    "cl",
                    "/nologo",
                    "/O2",
                    "/MT",
                    "/LD",
                    "/I" + str(openssl / "include"),
                    str(shim / "c_rfc3161_backend.c"),
                    str(shim / "c_rfc3161_test_vectors.c"),
                    str(openssl / "libcrypto.lib"),
                    "/Fe:" + str(target),
                    "/link",
                    "ws2_32.lib",
                    "advapi32.lib",
                    "crypt32.lib",
                    "user32.lib",
                    "bcrypt.lib",
                ],
                output,
                records,
            )
            blst_target = output / "c_blst.dll"
            run(
                [
                    "cl",
                    "/nologo",
                    "/O2",
                    "/MT",
                    "/LD",
                    "/I" + str(local_blst / "bindings"),
                    str(shim / "mt4_s3a_blst_quicknet_shim.c"),
                    str(local_blst / "blst.lib"),
                    "/Fe:" + str(blst_target),
                ],
                output,
                records,
            )
        else:
            for tool in ("cc", "make", "perl"):
                if not shutil.which(tool):
                    raise QualificationError("BUILD_TOOL_UNAVAILABLE:" + tool)
            run(["cc", "--version"], output, records)
            run(["perl", "Configure", "linux-x86_64", *options, "-fPIC", "-fvisibility=hidden"], openssl, records)
            run(["make", "-j2", "build_libs"], openssl, records)
            run(["sh", "build.sh", "-D__BLST_PORTABLE__", "-fPIC"], local_blst, records)
            target = output / "c_rfc3161.so"
            flags = [
                "-O2",
                "-fPIC",
                "-fvisibility=hidden",
                "-shared",
                "-Wl,--exclude-libs,ALL",
                "-Wl,-z,now,-z,relro,-z,noexecstack",
            ]
            run(
                [
                    "cc",
                    *flags,
                    "-I" + str(openssl / "include"),
                    str(shim / "c_rfc3161_backend.c"),
                    str(shim / "c_rfc3161_test_vectors.c"),
                    str(openssl / "libcrypto.a"),
                    "-pthread",
                    "-o",
                    str(target),
                ],
                output,
                records,
            )
            blst_target = output / "c_blst.so"
            run(
                [
                    "cc",
                    *flags,
                    "-I" + str(local_blst / "bindings"),
                    str(shim / "mt4_s3a_blst_quicknet_shim.c"),
                    str(local_blst / "libblst.a"),
                    "-o",
                    str(blst_target),
                ],
                output,
                records,
            )
        for name, file, exports in (
            ("openssl", target, EXPORTS + ("cqual_generate_test_vectors",)),
            ("blst", blst_target, ("mt4_s3a_verify_quicknet_bls", "mt4_s3a_qualification_g2_generator_compressed")),
        ):
            content = file.read_bytes()
            image = inspect_image(content, exports)
            receipt["artifacts"][name] = {
                "path": str(file),
                "sha256": hashlib.sha256(content).hexdigest(),
                "platform": image.platform,
                "exports": list(image.exports),
                "dependencies": list(image.dependencies),
            }
        receipt["qualification_sources"] = {
            name: hashlib.sha256((shim / name).read_bytes()).hexdigest()
            for name in ("c_rfc3161_backend.c", "c_rfc3161_test_vectors.c", "mt4_s3a_blst_quicknet_shim.c")
        }
        receipt["status"] = "BUILT_NOT_QUALIFIED_NOT_ADMITTED"
    finally:
        (output / "build-receipt.json").write_text(json.dumps(receipt, indent=2, sort_keys=True), encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--openssl-archive", required=True)
    parser.add_argument("--blst-checkout", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    build(args.openssl_archive, args.blst_checkout, args.output)
