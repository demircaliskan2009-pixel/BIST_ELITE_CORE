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
import subprocess
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

# =================================================================================================
# THE ACTUAL COMPILE/LINK INSTANCE INVENTORY (repair 8A and 8B).
#
# WHAT WAS MISSING.  Dependency-file evidence proves what a compilation INCLUDED; it does not prove
# WHICH compilation produced the artifact.  A separate dependency-only compile can differ from the
# real one in flags, include roots or inputs and still emit an identical .d file, so the two are not
# the same claim.  Every native invocation that actually contributes to the qualification artifacts
# is therefore recorded here as an INSTANCE, with its tool, its exact argument vector, its inputs,
# its flags and its output.
#
# A SYSTEM LIBRARY IS NOT A BUNDLE ENTRY (repair 8C).  -lcap resolves to a file from the pinned
# runner image, which is neither repository-controlled nor pinned-upstream source.  Pretending it
# belongs to the 16-entry bundle would be false; it gets its own provenance class instead, and its
# identity is the pinned toolchain contract rather than a repo digest.
# =================================================================================================

COMPILE_INSTANCE_SCHEMA = "mt4-s3c-compile-instance-inventory.v1"
COMPILE_INSTANCE_DIGEST_DOMAIN = b"mt4-s3c-compile-instance-inventory.v1\x00"

INSTANCE_KIND_COMPILE = "COMPILE"
INSTANCE_KIND_LINK = "LINK"
INSTANCE_KINDS = (INSTANCE_KIND_COMPILE, INSTANCE_KIND_LINK)

CLASS_SYSTEM_LIBRARY = "SYSTEM_LIBRARY"
PROVENANCE_SYSTEM_LIBRARY = "UBUNTU_22_04_PINNED_RUNNER_LIBRARY"
APPROVED_SYSTEM_LIBRARY_ROOTS = ("/usr/lib/", "/lib/")


def resolve_system_library(name, compiler):
    """Repair 11.  Ask the LINKER which file it selects for -l<name>, then identify that file.

    `-lcap` is a search request; the answer depends on the search path, so the name alone is not
    provenance.  The compiler's own --print-file-name gives the file it would link, which is the
    only answer that describes this build.  An unresolved or out-of-root answer fails closed rather
    than being recorded as a guess.
    """
    for candidate in ("lib" + name + ".so", "lib" + name + ".a"):
        completed = subprocess.run(  # noqa: S603 - fixed argument vector, no shell
            [compiler, "--print-file-name=" + candidate], check=False, capture_output=True, text=True
        )
        resolved = completed.stdout.strip()
        if completed.returncode != 0 or not resolved or resolved == candidate:
            continue
        resolved = os.path.realpath(resolved)
        if not os.path.isfile(resolved):
            continue
        if not any(resolved.startswith(root) for root in APPROVED_SYSTEM_LIBRARY_ROOTS):
            _fail("SYSTEM_LIBRARY_RESOLUTION_OUT_OF_ROOT", resolved)
        return {
            "name": name,
            "resolved_path": resolved,
            "soname": os.path.basename(resolved),
            "digest_sha256": _sha256_file(resolved),
            "provenance": PROVENANCE_SYSTEM_LIBRARY,
        }
    _fail("SYSTEM_LIBRARY_UNRESOLVED", name)
    return None


COMPILE_INSTANCE_FIELDS = (
    "argv",
    "flags",
    "include_roots",
    "inputs",
    "instance_id",
    "kind",
    "libraries",
    "output",
    "tool",
    "working_directory_class",
)

# =================================================================================================
# THE OBSERVED BUILD GRAPH (repair 10).
#
# WHAT WAS WRONG.  The inventory was a HAND-WRITTEN list of declarations passed on the command line.
# A declaration is a claim about a build, not a record of one: it can drift from the commands that
# actually ran, and an auditor counting real invocations in the workflow got a different number.
#
# The build now goes through a WRAPPER.  Every gcc invocation the workflow makes is executed by
# mt4_s3c_build_manifest.py itself, which records the exact argv it is about to run, runs it, and
# appends one canonical instance record on success.  The inventory is therefore an OBSERVATION of
# the real graph rather than a description of an intended one, and a command the workflow runs
# without the wrapper simply does not appear -- which the coverage rules below then reject.
#
# PRODUCER -> CONSUMER EDGES are explicit: every link instance names the object files it consumes,
# and every one of those must be the output of a recorded compile instance.
# =================================================================================================

INSTANCE_LOG_SCHEMA = "mt4-s3c-build-instance-log.v1"

# The instances that MUST be present.  Derived from the reviewed workflow's actual commands, not
# from a count reported by an earlier implementation.
REQUIRED_COMPILE_INSTANCES = (
    "blst-server",
    "blst-assembly",
    "worker-bootstrap",
    "worker-policy",
    "worker-capability",
    "worker-verify",
    "worker-start",
    "observer-probe",
    "observer-launcher",
)
REQUIRED_LINK_INSTANCES = ("worker-link", "observer-link")

# The system libraries the real link commands consume.  -lcap is resolved from the pinned runner
# image, so it is recorded as a SYSTEM_LIBRARY rather than pretended into the repository bundle.
REQUIRED_SYSTEM_LIBRARIES = ("cap",)

WORKING_DIRECTORY_CLASS = "GITHUB_WORKSPACE"


def _shell_split(argv_text):
    """Split one recorded argument vector.  The workflow supplies it already space-separated with
    no embedded quoting, which the validation below enforces rather than assumes."""
    if not isinstance(argv_text, str) or not argv_text.strip():
        _fail("COMPILE_INSTANCE_MALFORMED", "empty argv")
    for character in (chr(34), chr(39), "`", "$"):
        if character in argv_text:
            _fail("COMPILE_INSTANCE_MALFORMED", "argv carries shell metacharacters")
    return argv_text.split()


def parse_compile_instance(declaration, repository_root, upstream_root):
    """Parse one `<kind>:<instance_id>:<argv>` declaration into a governed instance record."""
    if not isinstance(declaration, str):
        _fail("COMPILE_INSTANCE_MALFORMED", "type")
    kind, _sep, remainder = declaration.partition(":")
    instance_id, _sep2, argv_text = remainder.partition(":")
    if kind not in INSTANCE_KINDS:
        _fail("COMPILE_INSTANCE_MALFORMED", "kind")
    if not instance_id:
        _fail("COMPILE_INSTANCE_MALFORMED", "instance id")
    argv = _shell_split(argv_text)

    tool = argv[0]
    flags = []
    include_roots = []
    inputs = []
    libraries = []
    output = ""
    index = 1
    while index < len(argv):
        word = argv[index]
        if word == "-o":
            index += 1
            if index >= len(argv):
                _fail("COMPILE_INSTANCE_MALFORMED", "missing output")
            output = argv[index]
        elif word == "-I":
            index += 1
            if index >= len(argv):
                _fail("COMPILE_INSTANCE_MALFORMED", "missing include root")
            include_roots.append(argv[index])
        elif word in ("-MF",):
            index += 1
        elif word.startswith("-l"):
            libraries.append(word[2:])
        elif word.startswith("-"):
            flags.append(word)
        else:
            inputs.append(word)
        index += 1

    if not output:
        _fail("COMPILE_INSTANCE_MALFORMED", "no output artifact")
    if not inputs:
        _fail("COMPILE_INSTANCE_MALFORMED", "no inputs")

    classified = []
    for item in inputs:
        kind_of_input, normalised = classify_dependency(item, repository_root, upstream_root)
        classified.append({"path": normalised, "class": kind_of_input})
    return {
        "instance_id": instance_id,
        "kind": kind,
        "tool": tool,
        "argv": argv,
        "flags": sorted(flags),
        "include_roots": sorted(include_roots),
        "inputs": classified,
        "libraries": sorted(libraries),
        "output": os.path.basename(output),
        "working_directory_class": WORKING_DIRECTORY_CLASS,
    }


def record_invocation(log_path, instance_id, kind, argv, repository_root, upstream_root):
    """Run ONE real native invocation and append its observed record.

    The wrapper is the single point at which a build command becomes evidence: the argv recorded is
    the argv executed, because the same list is used for both.
    """
    completed = subprocess.run(argv, check=False)  # noqa: S603 - argv is a fixed list, no shell
    if completed.returncode != 0:
        _fail("BUILD_INVOCATION_FAILED", instance_id)
    record = parse_compile_instance(kind + ":" + instance_id + ":" + " ".join(argv), repository_root, upstream_root)
    entries = []
    if os.path.exists(log_path):
        with open(log_path, "rb") as handle:
            entries = json.loads(handle.read().decode("utf-8"))["instances"]
    entries.append(record)
    with open(log_path, "wb") as handle:
        handle.write(canonical_json({"schema": INSTANCE_LOG_SCHEMA, "instances": entries}))
    return record


def load_observed_instances(log_path):
    """Read the OBSERVED invocation log the wrapper produced."""
    if not os.path.exists(log_path):
        _fail("BUILD_INSTANCE_LOG_MISSING")
    with open(log_path, "rb") as handle:
        payload = json.loads(handle.read().decode("utf-8"))
    if not isinstance(payload, dict) or payload.get("schema") != INSTANCE_LOG_SCHEMA:
        _fail("BUILD_INSTANCE_LOG_MALFORMED", "schema")
    instances = payload.get("instances")
    if not isinstance(instances, list) or not instances:
        _fail("BUILD_INSTANCE_LOG_MALFORMED", "instances")
    validate_compile_instances(instances)
    return sorted(instances, key=lambda instance: instance["instance_id"])


def build_compile_instance_inventory(declarations, repository_root, upstream_root):
    instances = [parse_compile_instance(item, repository_root, upstream_root) for item in declarations]
    validate_compile_instances(instances)
    return sorted(instances, key=lambda instance: instance["instance_id"])


def validate_compile_instances(instances):
    """Exact schema, unique ids, and COMPLETE coverage of the real build."""
    seen = set()
    for instance in instances:
        if tuple(sorted(instance)) != tuple(sorted(COMPILE_INSTANCE_FIELDS)):
            _fail("COMPILE_INSTANCE_MALFORMED", "field set")
        if instance["instance_id"] in seen:
            _fail("COMPILE_INSTANCE_DUPLICATE", instance["instance_id"])
        seen.add(instance["instance_id"])
        if instance["working_directory_class"] != WORKING_DIRECTORY_CLASS:
            _fail("COMPILE_INSTANCE_MALFORMED", "working directory class")
        for item in instance["inputs"]:
            if item["class"] not in (CLASS_REPO_BUNDLED, CLASS_UPSTREAM_PINNED, CLASS_EXTERNAL_TOOLCHAIN):
                _fail("COMPILE_INSTANCE_MALFORMED", "input class")
            if item["class"] == CLASS_REPO_BUNDLED and item["path"] not in SOURCE_BUNDLE_PATHS:
                _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", item["path"])
    for required in REQUIRED_COMPILE_INSTANCES:
        if required not in seen:
            _fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", required)
    for required in REQUIRED_LINK_INSTANCES:
        if required not in seen:
            _fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", required)
    links = [instance for instance in instances if instance["kind"] == INSTANCE_KIND_LINK]
    if len(links) != len(REQUIRED_LINK_INSTANCES):
        _fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", "link instance count")
    # Repair 8C: every system library the real link commands consume is RECORDED, in its own class.
    observed_libraries = set()
    for instance in links:
        observed_libraries.update(instance["libraries"])
    for required in REQUIRED_SYSTEM_LIBRARIES:
        if required not in observed_libraries:
            _fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", "system library " + required)

    # Repair 10: PRODUCER -> CONSUMER edges.  Every object a link consumes must be the recorded
    # output of a recorded compile, so a link cannot quietly consume an object nobody observed
    # being built.
    produced = {instance["output"] for instance in instances if instance["kind"] == INSTANCE_KIND_COMPILE}
    for instance in links:
        for item in instance["inputs"]:
            consumed = os.path.basename(item["path"])
            if consumed.endswith(".o") and consumed not in produced:
                _fail("COMPILE_INSTANCE_LINK_INPUT_UNPRODUCED", consumed)
    return instances


def compile_instance_preimage(instances, system_libraries=()):
    return {
        "schema": COMPILE_INSTANCE_SCHEMA,
        "instance_count": len(instances),
        "instances": instances,
        "instance_id_order": [instance["instance_id"] for instance in instances],
        "system_libraries": sorted(system_libraries, key=lambda entry: entry["name"]),
    }


def compile_instance_digest(instances, system_libraries=()):
    return hashlib.sha256(
        COMPILE_INSTANCE_DIGEST_DOMAIN + canonical_json(compile_instance_preimage(instances, system_libraries))
    ).hexdigest()


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
                # REPAIR 12.  The trusted surface holds no independent per-file table for the pinned
                # upstream tree, so a per-file hash computed here would be a producer claim sitting
                # inside a trusted equality chain while proving nothing.  The pinned identity that
                # IS trusted -- repository, release, commit and source-tree digest -- binds these
                # inputs instead, and the per-file slot is left empty so it cannot be mistaken for
                # a verified value.
                digest = ""
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
        elif entry["class"] == CLASS_UPSTREAM_PINNED:
            if entry["sha256"] != "":
                _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_MALFORMED", "upstream entry carries a per-file digest")
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


def build_manifest(arguments, inventory, include_roots, instances, system_libraries=()):
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
        "compile_instance_inventory_schema": COMPILE_INSTANCE_SCHEMA,
        "compile_instance_count": len(instances),
        "compile_instance_inventory_digest_sha256": compile_instance_digest(instances, system_libraries),
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
    "instance_log",
    "system_library",
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
    parser.add_argument("--compile-instance", action="append")
    # THE BUILD WRAPPER (repair 10).  The workflow runs every native command through this, so the
    # recorded argv is the executed argv and the inventory is an observation rather than a claim.
    parser.add_argument("--run-invocation")
    parser.add_argument("--invocation-kind")
    parser.add_argument("--instance-log")
    parser.add_argument("--system-library", action="append")
    parser.add_argument("--compiler", default="gcc")
    parser.add_argument("--include-root", action="append")
    parser.add_argument("--build-macro", action="append")
    parser.add_argument("--compiler-identity")
    parser.add_argument("--linker-identity")
    parser.add_argument("--source-run-id", type=int)
    parser.add_argument("--source-run-attempt", type=int)
    parser.add_argument("--source-head-sha")
    parser.add_argument("--inventory-out")
    parser.add_argument("--instance-out")
    parser.add_argument("--out")
    args = parser.parse_args(argv)

    if args.run_invocation:
        if not args.instance_log or not args.invocation_kind or not args.repository_root or not args.upstream_root:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "--run-invocation")
        separator = argv.index("--") if argv is not None and "--" in argv else sys.argv.index("--")
        command = (argv if argv is not None else sys.argv)[separator + 1 :]
        if not command:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "invocation argv")
        record_invocation(
            args.instance_log,
            args.run_invocation,
            args.invocation_kind,
            command,
            args.repository_root,
            args.upstream_root,
        )
        sys.stdout.write("MT4_S3C_BUILD_INSTANCE_RECORDED=" + args.run_invocation + "\n")
        return 0

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
    # REPAIR 10: the inventory comes from the OBSERVED invocation log the wrapper wrote.
    instances = load_observed_instances(args.instance_log)
    # REPAIR 11: every system library the links consumed is resolved to an actual file identity.
    system_libraries = [resolve_system_library(name, args.compiler) for name in sorted(set(args.system_library or ()))]
    manifest = build_manifest(args, inventory, include_roots, instances, system_libraries)

    with open(args.inventory_out, "wb") as handle:
        handle.write(canonical_json(dependency_inventory_preimage(inventory)))
    if args.instance_out:
        with open(args.instance_out, "wb") as handle:
            handle.write(canonical_json(compile_instance_preimage(instances, system_libraries)))
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
