"""MT4-S3C P0 build manifest and compile dependency inventory.  Qualification only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 8, 24, 28.6.
BUNDLE ENTRY 3 of the exact 16-entry qualification source bundle (V9 SECTION 8).

WHAT THIS MODULE OWNS.

  1. THE BUILD MANIFEST -- the second member of the candidate artifact (artifact class A1).  It
     records the worker binary identity, the pinned upstream dependency identity, the frozen build
     recipe, and the source-run identity, all as DATA.

  2. THE COMPILE DEPENDENCY INVENTORY -- V9 SECTION 28.6 leg D, and the V9-7 repair.  V8 collected
     compiler dependency evidence and then DISCARDED it as a local build check.  Here the normalized
     inventory is digested under a frozen schema, carried in the manifest, echoed into the ELF
     record and bound in the receipt, and RECOMPUTED by the trusted Stage-C gate against the git
     object store at the proven source head.  Modified or omitted dependency evidence therefore
     fails at the TRUST BOUNDARY, not merely inside the untrusted job.

WHY THE EVIDENCE IS NOT SELF-VALIDATING (V9 28.7 leg E).  The dependency output is produced by the
COMPILER, not by a repository script that could be rewritten to lie about itself.  The compiler is
classified EXTERNAL_TOOLCHAIN and is outside the set being measured, and the bundle digest constant
lives only on the trusted surface, so the thing being measured cannot change the measuring constant.

SELF-CONTAINED.  This module imports no repository module and contains no dynamic import machinery.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys

# =================================================================================================
# FROZEN IDENTITIES
# =================================================================================================

MANIFEST_SCHEMA = "mt4-s3c-build-manifest.v1"
MANIFEST_DIGEST_DOMAIN = b"mt4-s3c-build-manifest.v1\x00"
DEPENDENCY_SCHEMA = "mt4-s3c-compile-dependency-inventory.v1"
DEPENDENCY_DIGEST_DOMAIN = b"mt4-s3c-compile-dependency-inventory.v1\x00"
SOURCE_BUNDLE_SCHEMA = "mt4-s3c-qualification-source-bundle.v1"
SOURCE_BUNDLE_DIGEST_DOMAIN = b"mt4-s3c-qualification-source-bundle.v1\x00"
PLATFORM_ID = "LINUX_X86_64"

# Pinned upstream identity, transcribed from the governing S3B verifier profile (V9 SECTION 9 R6).
UPSTREAM_REPOSITORY = "https://github.com/supranational/blst"
UPSTREAM_RELEASE = "v0.3.17"
UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
UPSTREAM_SOURCE_TREE_DIGEST = "5a709c19ef7a1b9798ad58728fc5dd3b4d2026ecdd0342ebf8546c5950cea006"

# The frozen build orientation.  Both macros are MANDATORY (V9 SECTION 30 point 1).
REQUIRED_BUILD_MACROS = ("__BLST_PORTABLE__", "__BLST_NO_CPUID__")

MAX_WORKER_BINARY_BYTES = 8 * 1024 * 1024

# =================================================================================================
# THE EXACT 16-ENTRY SOURCE BUNDLE (V9 SECTION 8).
#
# Ordered byte-wise ascending by path.  V9 adds none and removes none, and no implementation may
# widen it: a genuine need for a seventeenth path is a SOURCE_BUNDLE_CONTRADICTION that returns to
# architecture, never a quiet addition here.
# =================================================================================================

SOURCE_BUNDLE_PATHS = (
    ".github/workflows/crypto_core_mt4_s3c_static_worker_qualification.yml",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_build_manifest.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_elf_qualify.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_observation_adjudicator.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_observation_parser.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_protocol_qualifier.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_receipt_generator.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_qualifier.py",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
    "tests/crypto_core/fixtures/mt4_s3c_test_only_positive_vector_v1.json",
)
SOURCE_BUNDLE_ENTRY_COUNT = 16

# V9 28.6 rule D-4: include search roots restricted to an EXACT allowlist.
ALLOWED_INCLUDE_ROOT_KINDS = ("UPSTREAM_PINNED_ROOT", "S3C_SCRIPT_DIRECTORY")

# Dependency classification (V9 28.6 rule D-2).
CLASS_REPO_BUNDLED = "REPO_BUNDLED"
CLASS_UPSTREAM_PINNED = "UPSTREAM_PINNED"
CLASS_EXTERNAL_TOOLCHAIN = "EXTERNAL_TOOLCHAIN"
DEPENDENCY_CLASSES = (CLASS_REPO_BUNDLED, CLASS_UPSTREAM_PINNED, CLASS_EXTERNAL_TOOLCHAIN)

# =================================================================================================
# THE COMPLETE COMPILE INVENTORY (repair 7E) AND ITS FROZEN SCHEMA (repair 7F).
#
# WHAT WAS MISSING.  The inventory covered only the five freestanding worker translation units.  The
# two pinned upstream blst inputs were compiled with no dependency evidence at all, and so were the
# observer and probe translation units, even though all four are load-bearing for the qualification
# result: the upstream inputs are linked into the very binary being qualified, and the observer and
# probe produce the evidence everything downstream is derived from.  An inventory that omits them
# cannot claim source closure over the build.
#
# EVERY entry now also carries PROVENANCE, and provenance is class-determined rather than free text.
# A REPO_BUNDLED row is provable only as one of the sixteen bundle entries; an UPSTREAM_PINNED row
# is bound to the exact pinned blst commit and source-tree digest; an EXTERNAL_TOOLCHAIN row names
# the pinned runner image and carries no digest, which is what keeps leg E non-circular.
# =================================================================================================

REQUIRED_TRANSLATION_UNITS = (
    "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
)

# The two pinned upstream native inputs that are linked into the qualified image.  Their presence in
# the inventory is MANDATORY; a build that omits their dependency evidence is not source-closed.
REQUIRED_UPSTREAM_INPUTS = ("src/server.c", "build/assembly.S")

PROVENANCE_REPO_BUNDLED = "QUALIFICATION_SOURCE_BUNDLE_V1"
PROVENANCE_UPSTREAM_PINNED = "BLST_PINNED_COMMIT_" + UPSTREAM_COMMIT + "_TREE_" + UPSTREAM_SOURCE_TREE_DIGEST
PROVENANCE_EXTERNAL_TOOLCHAIN = "UBUNTU_22_04_PINNED_RUNNER_TOOLCHAIN"

CLASS_PROVENANCE = {
    CLASS_REPO_BUNDLED: PROVENANCE_REPO_BUNDLED,
    CLASS_UPSTREAM_PINNED: PROVENANCE_UPSTREAM_PINNED,
    CLASS_EXTERNAL_TOOLCHAIN: PROVENANCE_EXTERNAL_TOOLCHAIN,
}

DEPENDENCY_ENTRY_FIELDS = ("class", "path", "provenance", "sha256")


class BuildManifestError(RuntimeError):
    """Any failure to prove a required build property.  There is no partial success."""


def _fail(marker, detail=""):
    raise BuildManifestError(marker if not detail else marker + ": " + detail)


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def _is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _sha256_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# =================================================================================================
# COMPILER DEPENDENCY PARSING (V9 28.6 rule D-1)
# =================================================================================================


def parse_dependency_file(text):
    """Parse one make-style dependency file into a list of prerequisite paths.

    The grammar accepted is exactly what the compiler emits: a target, a colon, and a
    whitespace-separated prerequisite list with backslash line continuations.  Nothing else is
    accepted; an unparseable dependency file is a hard failure, never a silently empty result.
    """
    if ":" not in text:
        _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "no target separator")
    joined = text.replace("\\\n", " ").replace("\\\r\n", " ")
    prerequisites = []
    for line in joined.splitlines():
        if ":" not in line:
            continue
        _target, _separator, remainder = line.partition(":")
        for prerequisite in remainder.split():
            if prerequisite and prerequisite != "\\":
                prerequisites.append(prerequisite)
    if not prerequisites:
        _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "empty prerequisite list")
    return prerequisites


def classify_dependency(path, repository_root, upstream_root):
    """V9 28.6 rule D-2: normalise to repo-relative POSIX and classify.

    Classification is by CONTAINMENT under a normalised absolute root, so a path that merely starts
    with a matching prefix string but escapes the root cannot be misclassified.
    """
    absolute = os.path.normpath(os.path.abspath(path))
    repository_root = os.path.normpath(os.path.abspath(repository_root))
    upstream_root = os.path.normpath(os.path.abspath(upstream_root))

    if absolute == upstream_root or absolute.startswith(upstream_root + os.sep):
        return CLASS_UPSTREAM_PINNED, os.path.relpath(absolute, upstream_root).replace(os.sep, "/")
    if absolute == repository_root or absolute.startswith(repository_root + os.sep):
        return CLASS_REPO_BUNDLED, os.path.relpath(absolute, repository_root).replace(os.sep, "/")
    return CLASS_EXTERNAL_TOOLCHAIN, absolute.replace(os.sep, "/")


def build_dependency_inventory(dependency_files, repository_root, upstream_root):
    """Collect, normalise, de-duplicate and sort the compile dependency inventory."""
    entries = {}
    for dependency_path in dependency_files:
        with open(dependency_path, encoding="utf-8") as handle:
            text = handle.read()
        for prerequisite in parse_dependency_file(text):
            kind, normalised = classify_dependency(prerequisite, repository_root, upstream_root)
            if kind == CLASS_REPO_BUNDLED:
                # D-3: EVERY repo-local dependency must be one of the sixteen bundle entries.
                if normalised not in SOURCE_BUNDLE_PATHS:
                    _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", normalised)
                digest = _sha256_file(os.path.join(repository_root, normalised))
            elif kind == CLASS_UPSTREAM_PINNED:
                digest = _sha256_file(os.path.join(upstream_root, normalised))
            else:
                # An external toolchain path carries no content digest by design: the toolchain is
                # outside the measured set, which is exactly what makes leg E non-circular.
                digest = ""
            key = (normalised, kind)
            if key in entries and entries[key] != digest:
                _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "conflicting digest for " + normalised)
            entries[key] = digest

    ordered = sorted(entries.items(), key=lambda item: (item[0][0], item[0][1]))
    inventory = [
        {"path": path, "class": kind, "provenance": CLASS_PROVENANCE[kind], "sha256": digest}
        for (path, kind), digest in ordered
    ]
    validate_dependency_inventory(inventory)
    return inventory


def validate_dependency_inventory(inventory):
    """The frozen inventory schema (repair 7F).  Exact fields, unique paths, complete coverage."""
    seen = set()
    for entry in inventory:
        if tuple(sorted(entry)) != tuple(sorted(DEPENDENCY_ENTRY_FIELDS)):
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "entry field set")
        if entry["class"] not in DEPENDENCY_CLASSES:
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", entry["class"])
        if entry["provenance"] != CLASS_PROVENANCE[entry["class"]]:
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_PROVENANCE_INVALID", entry["path"])
        # A path may appear once and once only.  Two rows for one path, even in different classes,
        # would make the inventory ambiguous about which bytes were actually compiled.
        if entry["path"] in seen:
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_DUPLICATE", entry["path"])
        seen.add(entry["path"])
        if entry["class"] == CLASS_EXTERNAL_TOOLCHAIN:
            if entry["sha256"] != "":
                _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "external entry carries a digest")
        elif not _is_hex64(entry["sha256"]):
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "missing digest for " + entry["path"])
        if entry["class"] == CLASS_REPO_BUNDLED and entry["path"] not in SOURCE_BUNDLE_PATHS:
            _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", entry["path"])

    bundled = {entry["path"] for entry in inventory if entry["class"] == CLASS_REPO_BUNDLED}
    for required in REQUIRED_TRANSLATION_UNITS:
        if required not in bundled:
            _fail("SOURCE_CLOSURE_COMPILE_INVENTORY_INCOMPLETE", required)
    upstream = {entry["path"] for entry in inventory if entry["class"] == CLASS_UPSTREAM_PINNED}
    for required in REQUIRED_UPSTREAM_INPUTS:
        if required not in upstream:
            _fail("SOURCE_CLOSURE_COMPILE_INVENTORY_INCOMPLETE", required)
    paths = [entry["path"] for entry in inventory]
    if paths != sorted(paths):
        _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "ordering")
    return inventory


def dependency_inventory_preimage(inventory):
    return {
        "schema": DEPENDENCY_SCHEMA,
        "entry_count": len(inventory),
        "entries": inventory,
        "path_order": [entry["path"] for entry in inventory],
    }


def dependency_inventory_digest(inventory):
    return hashlib.sha256(
        DEPENDENCY_DIGEST_DOMAIN + canonical_json(dependency_inventory_preimage(inventory))
    ).hexdigest()


def check_include_roots(include_roots, repository_root, upstream_root):
    """V9 28.6 rule D-4: an include root outside the exact allowlist FAILS."""
    repository_root = os.path.normpath(os.path.abspath(repository_root))
    upstream_root = os.path.normpath(os.path.abspath(upstream_root))
    script_directory = os.path.normpath(os.path.join(repository_root, "scripts/crypto_core/qualification/s3c"))
    classified = []
    for root in include_roots:
        absolute = os.path.normpath(os.path.abspath(root))
        if absolute == upstream_root or absolute.startswith(upstream_root + os.sep):
            classified.append({"root": absolute.replace(os.sep, "/"), "kind": "UPSTREAM_PINNED_ROOT"})
        elif absolute == script_directory:
            classified.append({"root": absolute.replace(os.sep, "/"), "kind": "S3C_SCRIPT_DIRECTORY"})
        else:
            _fail("INCLUDE_ROOT_VIOLATION", absolute)
    return classified


# =================================================================================================
# THE SOURCE BUNDLE DIGEST (V9 SECTION 8)
# =================================================================================================


def source_bundle_preimage(entries):
    return {
        "schema": SOURCE_BUNDLE_SCHEMA,
        "entry_count": len(entries),
        "entries": entries,
        "path_order": [entry["path"] for entry in entries],
    }


def source_bundle_digest(entries):
    """QUALIFICATION_SOURCE_BUNDLE_DIGEST.

    Every field is load-bearing: mode kills an executable-bit change; type "blob" makes a path that
    becomes a symlink or a gitlink an immediate mismatch; entry_count kills silent deletion;
    path_order kills reordering.  Together they kill silent injection.
    """
    if len(entries) != SOURCE_BUNDLE_ENTRY_COUNT:
        _fail("SOURCE_BUNDLE_CONTRADICTION", str(len(entries)))
    paths = [entry["path"] for entry in entries]
    if paths != sorted(paths):
        _fail("SOURCE_BUNDLE_CONTRADICTION", "entries are not byte-wise ascending by path")
    if tuple(paths) != SOURCE_BUNDLE_PATHS:
        _fail("SOURCE_BUNDLE_CONTRADICTION", "inventory differs from the frozen sixteen")
    for entry in entries:
        if entry["type"] != "blob":
            _fail("SOURCE_BUNDLE_CONTRADICTION", "non-blob entry " + entry["path"])
        if entry["mode"] not in ("100644", "100755"):
            _fail("SOURCE_BUNDLE_CONTRADICTION", "unexpected mode for " + entry["path"])
        if not _is_hex64(entry["sha256"]):
            _fail("SOURCE_BUNDLE_CONTRADICTION", "malformed digest for " + entry["path"])
    return hashlib.sha256(SOURCE_BUNDLE_DIGEST_DOMAIN + canonical_json(source_bundle_preimage(entries))).hexdigest()


# =================================================================================================
# THE BUILD MANIFEST
# =================================================================================================


def build_manifest(arguments, inventory, include_roots):
    binary_digest = _sha256_file(arguments.worker_binary)
    binary_bytes = os.path.getsize(arguments.worker_binary)
    if binary_bytes <= 0 or binary_bytes > MAX_WORKER_BINARY_BYTES:
        _fail("WORKER_BINARY_SIZE_INVALID", str(binary_bytes))

    macros = tuple(arguments.build_macro or ())
    for required in REQUIRED_BUILD_MACROS:
        if required not in macros:
            _fail("BUILD_MACRO_MISSING", required)

    manifest = {
        "schema": MANIFEST_SCHEMA,
        "platform_id": PLATFORM_ID,
        "worker_binary_name": os.path.basename(arguments.worker_binary),
        "worker_binary_sha256": binary_digest,
        "worker_binary_bytes": binary_bytes,
        "upstream_repository": UPSTREAM_REPOSITORY,
        "upstream_release": UPSTREAM_RELEASE,
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_source_tree_digest": UPSTREAM_SOURCE_TREE_DIGEST,
        "build_macros": sorted(macros),
        "compiler_identity": arguments.compiler_identity,
        "linker_identity": arguments.linker_identity,
        "include_roots": include_roots,
        "compile_dependency_inventory_schema": DEPENDENCY_SCHEMA,
        "compile_dependency_entry_count": len(inventory),
        "compile_dependency_inventory_digest_sha256": dependency_inventory_digest(inventory),
        "source_run_id": arguments.source_run_id,
        "source_run_attempt": arguments.source_run_attempt,
        "source_head_sha": arguments.source_head_sha,
        "qualification_source_bundle_schema": SOURCE_BUNDLE_SCHEMA,
        "qualification_source_bundle_entry_count": SOURCE_BUNDLE_ENTRY_COUNT,
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "authority_non_transition": {
            "readiness_transition": "NONE",
            "connector_transition": "NONE",
            "product_native_execution": "NO",
            "machine_time_authority": "NONE",
            "mt5_mt6_authority": "NONE",
            "stage4_authority": "NONE",
            "dependency_profile_admitted": False,
            "fixture_corpus_admitted": False,
            "proof_verified": False,
        },
    }
    manifest["build_manifest_digest_sha256"] = hashlib.sha256(
        MANIFEST_DIGEST_DOMAIN + canonical_json(manifest)
    ).hexdigest()
    return manifest


def emit_manifest_environment(manifest_path, env_path):
    """Re-read a committed manifest and export its governed identity values, validated first.

    The exported values are a CLAIM that every later stage checks independently: the trusted
    observer recomputes the candidate digest from the bytes it materialises inside the private root,
    the ELF qualifier recomputes it from the downloaded archive member, and the trusted Stage-C gate
    recomputes it a third time from the artifact archive.  Exporting them here exists solely so the
    workflow needs no command substitution to move a value between steps (V9 SECTION 28.3 leg A).
    """
    with open(manifest_path, "rb") as handle:
        manifest = json.loads(handle.read().decode("utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema") != MANIFEST_SCHEMA:
        _fail("BUILD_MANIFEST_MALFORMED", "schema")
    digest = manifest.get("worker_binary_sha256")
    dependency_digest = manifest.get("compile_dependency_inventory_digest_sha256")
    size = manifest.get("worker_binary_bytes")
    if not _is_hex64(digest) or not _is_hex64(dependency_digest):
        _fail("BUILD_MANIFEST_MALFORMED", "digest")
    if isinstance(size, bool) or not isinstance(size, int) or size <= 0 or size > MAX_WORKER_BINARY_BYTES:
        _fail("BUILD_MANIFEST_MALFORMED", "worker_binary_bytes")
    with open(env_path, "a", encoding="ascii") as handle:
        handle.write("S3C_WORKER_SHA256=" + digest + "\n")
        handle.write("S3C_WORKER_BYTES=" + str(size) + "\n")
        handle.write("S3C_DEPENDENCY_DIGEST=" + dependency_digest + "\n")


_REQUIRED_BUILD_ARGUMENTS = (
    "worker_binary",
    "repository_root",
    "upstream_root",
    "dependency_file",
    "include_root",
    "build_macro",
    "compiler_identity",
    "linker_identity",
    "source_run_id",
    "source_run_attempt",
    "source_head_sha",
    "inventory_out",
    "out",
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MT4-S3C build manifest and compile dependency inventory")
    parser.add_argument("--emit-env-from-manifest")
    parser.add_argument("--emit-env")
    parser.add_argument("--worker-binary")
    parser.add_argument("--repository-root")
    parser.add_argument("--upstream-root")
    parser.add_argument("--dependency-file", action="append")
    parser.add_argument("--include-root", action="append")
    parser.add_argument("--build-macro", action="append")
    parser.add_argument("--compiler-identity")
    parser.add_argument("--linker-identity")
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--source-run-attempt", type=int)
    parser.add_argument("--source-head-sha")
    parser.add_argument("--inventory-out")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    if args.emit_env_from_manifest:
        if not args.emit_env:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "--emit-env")
        emit_manifest_environment(args.emit_env_from_manifest, args.emit_env)
        return 0
    for name in _REQUIRED_BUILD_ARGUMENTS:
        if getattr(args, name) is None:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", name)

    include_roots = check_include_roots(args.include_root, args.repository_root, args.upstream_root)
    inventory = build_dependency_inventory(args.dependency_file, args.repository_root, args.upstream_root)
    manifest = build_manifest(args, inventory, include_roots)

    with open(args.inventory_out, "wb") as handle:
        handle.write(canonical_json(dependency_inventory_preimage(inventory)))
    with open(args.out, "wb") as handle:
        handle.write(canonical_json(manifest))
    sys.stdout.write("MT4_S3C_WORKER_BINARY_SHA256=" + manifest["worker_binary_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_WORKER_BINARY_BYTES=" + str(manifest["worker_binary_bytes"]) + "\n")
    sys.stdout.write(
        "MT4_S3C_COMPILE_DEPENDENCY_INVENTORY_DIGEST=" + manifest["compile_dependency_inventory_digest_sha256"] + "\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
