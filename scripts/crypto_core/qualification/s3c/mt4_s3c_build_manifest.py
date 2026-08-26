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
# Repair 5D: objcopy REWRITES the bytes that are later linked and qualified.  A graph that called
# itself complete while omitting a step that changes the artifact was not describing the build.
INSTANCE_KIND_TRANSFORM = "TRANSFORM"
INSTANCE_KINDS = (INSTANCE_KIND_COMPILE, INSTANCE_KIND_LINK, INSTANCE_KIND_TRANSFORM)

# =================================================================================================
# THE FROZEN EXECUTION BOUNDARY (repairs 3D, 3E, 3F, 3G and 4).
#
# The wrapper is the ONLY place in the bundle that may start a process, so everything about that
# process is pinned here rather than inherited:
#
#   TOOL         an exact basename from a closed set, resolved to an absolute path inside an
#                approved toolchain directory.  The caller supplies metadata, never an executable:
#                a path, a shell, an interpreter or a repository script cannot become the tool.
#   CWD          explicit and governed.  Inheriting the ambient directory would let the caller
#                change what a relative input means after validation.
#   ENVIRONMENT  built from nothing.  CC, CFLAGS, LDFLAGS, CPATH, LIBRARY_PATH, LD_PRELOAD and
#                PYTHONPATH all change what a compiler does; an allowlist that starts empty
#                excludes them by construction rather than by remembering to name them.
# =================================================================================================

APPROVED_TOOLCHAIN_ROOTS = ("/usr/bin", "/usr/local/bin", "/bin")
APPROVED_TOOLS = {
    INSTANCE_KIND_COMPILE: ("gcc",),
    INSTANCE_KIND_LINK: ("gcc",),
    INSTANCE_KIND_TRANSFORM: ("objcopy",),
}
FORBIDDEN_BUILD_ENVIRONMENT = (
    "CC",
    "CXX",
    "CFLAGS",
    "CPATH",
    "CPPFLAGS",
    "C_INCLUDE_PATH",
    "GCC_EXEC_PREFIX",
    "LDFLAGS",
    "LD_LIBRARY_PATH",
    "LD_PRELOAD",
    "LD_RUN_PATH",
    "LIBRARY_PATH",
    "PYTHONPATH",
    "PYTHONSTARTUP",
)
GOVERNED_BUILD_ENVIRONMENT = {
    "PATH": "/usr/local/bin:/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
}


def require_governed_tool_name(kind, name):
    """The frozen half of tool identity: WHICH tool this operation class may run.

    This is a property of the contract, so it holds on every host and is checked before anything
    else looks at the command.  Where that executable actually lives is a property of the machine
    and is proven separately, immediately before exec.
    """
    if kind not in APPROVED_TOOLS:
        _fail("BUILD_COMMAND_REJECTED", "operation class")
    if name not in APPROVED_TOOLS[kind]:
        _fail("BUILD_COMMAND_REJECTED", "tool is not approved for this operation")
    if os.sep in name or (os.altsep and os.altsep in name):
        _fail("BUILD_COMMAND_REJECTED", "tool must be a bare approved name")
    return name


def resolve_governed_tool(kind, name):
    """Deterministically resolve a tool basename inside the approved toolchain roots.

    PATH is not consulted: PATH is an uncontrolled lookup, and "the basename was gcc" is not an
    identity.  Exactly one approved directory must hold an executable regular file of that name.
    """
    require_governed_tool_name(kind, name)
    resolved = [
        os.path.join(root, name)
        for root in APPROVED_TOOLCHAIN_ROOTS
        if os.path.isfile(os.path.join(root, name)) and os.access(os.path.join(root, name), os.X_OK)
    ]
    if not resolved:
        _fail("BUILD_TOOL_UNRESOLVED", name)
    real = os.path.realpath(resolved[0])
    if not any(real.startswith(root + os.sep) for root in APPROVED_TOOLCHAIN_ROOTS):
        _fail("BUILD_TOOL_OUT_OF_ROOT", name)
    return real


def governed_build_environment():
    """The exact environment a governed build runs under, built from nothing."""
    environment = dict(GOVERNED_BUILD_ENVIRONMENT)
    for name in FORBIDDEN_BUILD_ENVIRONMENT:
        if name in environment:
            _fail("BUILD_ENVIRONMENT_REJECTED", name)
    return environment


# =================================================================================================
# THE EXACT PER-INVOCATION COMMAND CONTRACT (repair 4).
#
# "This looks like a gcc compile" is not a contract.  The audit showed an out-of-contract external
# input, an external output and a plugin flag all reaching the child-execution sentinel, because
# validation only recognised the SHAPE of a command rather than the exact command each governed
# instance is allowed to run.
#
# The allowlist below is POSITIVE.  A flag that is not named is refused -- which is the only form
# that stays correct as toolchains grow new options, where an endless denylist does not.
# =================================================================================================

# Flags that change WHERE a tool looks or WHAT CODE it loads.  None of them is governed, and each
# would let a caller extend the compiler's behaviour past the reviewed build contract.
FORBIDDEN_FLAG_PREFIXES = (
    "-B",
    "-fplugin",
    "-specs",
    "-Xlinker",
    "-Wl,-plugin",
    "-Wl,--plugin",
    "-idirafter",
    "-isystem",
    "-iquote",
    "-iprefix",
    "-L",
    "-Wp,",
    "-Wa,",
    "@",
)

# The exact flag set each operation class may carry, beyond the frozen per-instance requirements.
# BUILD_TO_PROVE run 32993250008 proved the launcher's own #define _GNU_SOURCE collides with a CLI
# -D_GNU_SOURCE under -Werror ("_GNU_SOURCE" redefined).  No other governed translation unit ever
# carried this flag, so it is not a generic allowance -- it is removed outright, and reintroducing
# it on any compile is rejected the same way any other unlisted flag is.
ALLOWED_COMPILE_FLAGS = frozenset(
    {
        "-c",
        "-O2",
        "-std=c11",
        "-ffreestanding",
        "-fno-pic",
        "-fno-builtin",
        "-fno-stack-protector",
        "-fno-asynchronous-unwind-tables",
        "-fcf-protection=none",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-MD",
        "-D__BLST_PORTABLE__",
        "-D__BLST_NO_CPUID__",
    }
)
ALLOWED_LINK_FLAGS = frozenset(
    {
        "-O2",
        "-static",
        "-no-pie",
        "-nostdlib",
        "-nostartfiles",
        "-Wl,-e,_start",
        "-Wl,--build-id=none",
        "-Wl,-z,noexecstack",
        "-Wl,-z,noseparate-code",
        "-Wl,-z,max-page-size=0x1000",
        "-Wl,--no-eh-frame-hdr",
        "-Wl,-z,defs",
        "-Wl,--fatal-warnings",
    }
)
ALLOWED_TRANSFORM_FLAGS = frozenset({"--remove-section=.note.gnu.property"})

ALLOWED_FLAGS_BY_KIND = {
    INSTANCE_KIND_COMPILE: ALLOWED_COMPILE_FLAGS,
    INSTANCE_KIND_LINK: ALLOWED_LINK_FLAGS,
    INSTANCE_KIND_TRANSFORM: ALLOWED_TRANSFORM_FLAGS,
}

# The exact governed primary input of each instance, and the output directory class it may write.
# An instance may read only what its own contract names, and may write only inside the build area.
INSTANCE_PRIMARY_INPUT = {
    "worker-bootstrap": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "worker-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "worker-capability": "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "worker-verify": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
    "worker-start": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "observer-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "observer-launcher": "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "observer-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "observe-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "observe-launcher": "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "observe-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "adjudicate-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "adjudicate-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "blst-server": "src/server.c",
    "blst-assembly": "build/assembly.S",
}


def _require_governed_paths(kind, instance_id, record, repository_root, upstream_root):
    """Repair 4C and 4D.  Every input and the output resolve to a governed location."""
    declared_build_root = os.environ.get("RUNNER_TEMP")
    if not declared_build_root:
        # Fail closed.  Defaulting to the filesystem root would make "inside the build area" true
        # of every path on the machine, which is the opposite of what the check exists to prove.
        _fail("BUILD_AREA_UNDECLARED")
    build_root = os.path.normpath(os.path.abspath(declared_build_root))
    workspace = os.path.normpath(os.path.abspath(repository_root))
    upstream = os.path.normpath(os.path.abspath(upstream_root))

    expected_primary = INSTANCE_PRIMARY_INPUT.get(instance_id)
    if kind == INSTANCE_KIND_COMPILE:
        if expected_primary is None:
            _fail("BUILD_COMMAND_REJECTED", "unknown compile instance")
        sources = [item for item in record["inputs"] if item["class"] in (CLASS_REPO_BUNDLED, CLASS_UPSTREAM_PINNED)]
        if len(sources) != 1 or sources[0]["path"] != expected_primary:
            _fail("BUILD_COMMAND_REJECTED", "input is not the governed source for this instance")

    for item in record["inputs"]:
        # The RAW execution path is the only value with filesystem meaning.  Resolving the graph
        # identity here was the defect: "s3c-build-candidate:obj/policy.o" is a key, and abspath
        # turns it into a path under the working directory that no build ever writes -- so the
        # containment check was passing or failing for reasons unrelated to where the file is.
        absolute = os.path.normpath(os.path.abspath(item["raw_path"]))
        if item["class"] == CLASS_REPO_BUNDLED:
            if item["path"] not in SOURCE_BUNDLE_PATHS:
                _fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", item["path"])
            continue
        if item["class"] == CLASS_UPSTREAM_PINNED:
            if not absolute.startswith(upstream + os.sep):
                _fail("BUILD_COMMAND_REJECTED", "upstream input escapes the pinned root")
            continue
        # Everything else is an intermediate object, which must live in the build area.
        if not absolute.startswith(build_root + os.sep):
            _fail("BUILD_COMMAND_REJECTED", "input escapes the governed build area")

    output = os.path.normpath(os.path.abspath(record["raw_output"]))
    if output.startswith(workspace + os.sep):
        _fail("BUILD_COMMAND_REJECTED", "output would write into the repository")
    if not output.startswith(build_root + os.sep):
        _fail("BUILD_COMMAND_REJECTED", "output escapes the governed build area")
    # The VALIDATED absolute path of the artifact this invocation writes.  Repair 3 hashes exactly
    # this after execution: it is the path the contract just proved governed, so no later step has
    # to rebuild it from evidence that was never a path.
    return output


def validate_build_command(kind, command, repository_root, upstream_root, instance_id=None, job_id=None):
    """Repair 3C.  COMPLETE validation, BEFORE any child process exists.

    An invocation that fails here starts nothing at all; the previous ordering ran the command and
    then asked whether it had been allowed, which is not a gate.
    """
    if kind not in INSTANCE_KINDS:
        _fail("BUILD_COMMAND_REJECTED", "operation class")
    if not isinstance(command, list) or not command:
        _fail("BUILD_COMMAND_REJECTED", "empty command")
    for word in command:
        if not isinstance(word, str) or not word:
            _fail("BUILD_COMMAND_REJECTED", "argument type")
        for character in (chr(34), chr(39), "`", "$", ";", "|", "&", "\n"):
            if character in word:
                _fail("BUILD_COMMAND_REJECTED", "argument carries a shell metacharacter")
    # FIRST: the tool this operation class is allowed to run.  A command whose tool is /bin/sh or
    # python3 is out of contract no matter what the rest of its argv looks like, and saying so here
    # means the refusal names the real reason instead of whatever the parser trips over first.
    require_governed_tool_name(kind, command[0])

    # The command must parse into the governed shape for its operation class, and every input must
    # classify.  parse_compile_instance performs that classification and fails closed on an
    # unbundled repository input.
    record = parse_compile_instance(
        kind + ":" + (instance_id or "validation") + ":" + " ".join(command), repository_root, upstream_root, job_id
    )
    if kind == INSTANCE_KIND_TRANSFORM and record["inputs"] and len(record["inputs"]) != 1:
        _fail("BUILD_COMMAND_REJECTED", "a transform takes exactly one artifact")

    # REPAIR 4B: a POSITIVE flag allowlist, plus the forbidden-prefix families that would extend the
    # tool's search or load behaviour.  Both directions are checked, so a novel flag is refused by
    # default rather than by having been anticipated.
    allowed = ALLOWED_FLAGS_BY_KIND[kind]
    for flag in record["flags"]:
        for prefix in FORBIDDEN_FLAG_PREFIXES:
            if flag.startswith(prefix):
                _fail("BUILD_COMMAND_REJECTED", "forbidden flag family")
        if flag not in allowed:
            _fail("BUILD_COMMAND_REJECTED", "flag is not on the governed allowlist")
    for word in command[1:]:
        for prefix in FORBIDDEN_FLAG_PREFIXES:
            if word.startswith(prefix):
                _fail("BUILD_COMMAND_REJECTED", "forbidden argument family")

    # Include roots are governed: exactly the pinned upstream tree or the S3C script directory.
    check_include_roots(record["include_roots"], repository_root, upstream_root)

    # The VALIDATED absolute filesystem path of this invocation's output artifact, captured here
    # and returned so that no later step has to reconstruct a path from graph evidence.
    validated_output_path = None
    if instance_id is not None:
        validated_output_path = _require_governed_paths(kind, instance_id, record, repository_root, upstream_root)

    # LAST: resolve the tool.  Everything above is a property of the frozen contract and holds on
    # any host; this one depends on the machine, so it runs after the contract has been proven.
    executable = resolve_governed_tool(kind, command[0])
    return executable, record, validated_output_path


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
    executable = resolve_governed_tool(INSTANCE_KIND_LINK, compiler)
    environment = governed_build_environment()
    for candidate in ("lib" + name + ".so", "lib" + name + ".a"):
        completed = subprocess.run(  # noqa: S603 - frozen executable, fixed argument vector, no shell
            [executable, "--print-file-name=" + candidate],
            check=False,
            shell=False,
            cwd=os.sep,
            env=environment,
            capture_output=True,
            text=True,
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


# The fields EVERY recorded invocation carries.  resolved_tool_path and working_directory are
# the wrapper's frozen execution boundary made evidence: the tool that actually ran and the
# directory it ran in, rather than a basename and an assumption.
COMPILE_INSTANCE_FIELDS = (
    "argv",
    "flags",
    "include_roots",
    "inputs",
    "instance_id",
    "job_id",
    "kind",
    "libraries",
    "output",
    "output_path",
    "raw_output",
    "resolved_tool_path",
    "tool",
    "working_directory",
    "working_directory_class",
)

# The exact field set of ONE consumed input, carrying the same three path concepts as the record.
COMPILE_INPUT_FIELDS = ("class", "graph_identity", "path", "raw_path")

# A TRANSFORM rewrites an artifact in place, so its record carries the two distinct graph
# STATES of the same path.  Without them the post-transform bytes would be indistinguishable
# from the pre-transform ones in the graph.
TRANSFORM_INSTANCE_FIELDS = tuple(
    sorted(COMPILE_INSTANCE_FIELDS + ("digest_after", "digest_before", "transform_target"))
)


def instance_fields_for(kind):
    """The exact field set one recorded invocation must carry, by operation class."""
    if kind == INSTANCE_KIND_TRANSFORM:
        return TRANSFORM_INSTANCE_FIELDS
    return COMPILE_INSTANCE_FIELDS


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
    "observer-policy",
)
REQUIRED_LINK_INSTANCES = ("worker-link", "observer-link")

# Repair 5D: the two objcopy operations REWRITE bytes that are later linked and qualified, so they
# are governed build operations with their own class rather than invisible side effects.
REQUIRED_TRANSFORM_INSTANCES = ("blst-assembly-strip", "blst-server-strip")

# Repair 5B: the EXACT objects each real link consumes, derived from the reviewed workflow's actual
# link commands rather than from a simplified test model.  A link that silently dropped an input
# would otherwise still satisfy a partial expectation.
REQUIRED_LINK_INPUT_PRODUCERS = {
    "worker-link": (
        "worker-start",
        "worker-bootstrap",
        "worker-verify",
        "worker-policy",
        "worker-capability",
        "blst-server-strip",
        "blst-assembly-strip",
    ),
    "observer-link": ("observer-launcher", "observer-policy"),
}

# The system libraries the real link commands consume.  -lcap is resolved from the pinned runner
# image, so it is recorded as a SYSTEM_LIBRARY rather than pretended into the repository bundle.
REQUIRED_SYSTEM_LIBRARIES = ("cap",)

WORKING_DIRECTORY_CLASS = "GITHUB_WORKSPACE"

# =================================================================================================
# GRAPH IDENTITY IS JOB + PATH + STATE (repair 5).
#
# The real workflow REUSES pathnames.  $RUNNER_TEMP/obj/policy.o is produced by worker-policy in the
# build job, by observe-policy in the observation job and by adjudicate-policy in the adjudication
# job; $RUNNER_TEMP/obj/probe.o and $RUNNER_TEMP/mt4_s3c_policy_probe are reused the same way.  That
# is legitimate -- each job has its own runner and its own temporary tree -- but it means a
# path-only identity sees three producers for one node and cannot close, while a basename-only
# identity is worse still.  Identity therefore carries the job, and an in-place transform is a
# distinct STATE of the same node rather than a second producer of it.
# =================================================================================================

GOVERNED_JOB_IDS = ("s3c-build-candidate", "s3c-observe", "s3c-adjudicate")

# =================================================================================================
# THREE PATH CONCEPTS, DELIBERATELY DISTINCT (controller repair 2).
#
# These were conflated, and the conflation was load-bearing: a GRAPH IDENTITY was being handed to
# os.path.abspath and to os.path.join, which silently produces a path that cannot exist.
#
#   RAW_EXECUTION_PATH        exactly what the command line said, e.g.
#                             /home/runner/work/_temp/obj/policy.o
#                             The ONLY value that may touch the filesystem.
#   CANONICAL_FILESYSTEM_PATH the same file named relative to its governed root, e.g. obj/policy.o
#                             Deterministic across runners.  Evidence, never a filesystem operand.
#   GRAPH_IDENTITY            the node key, e.g. s3c-build-candidate:obj/policy.o
#                             A KEY.  Never a pathname, never joined, opened, resolved or hashed.
#
# The direction of derivation is one-way: raw -> canonical -> graph identity.  Nothing reverses it,
# because a graph identity cannot be turned back into a file and must never be asked to be.
# =================================================================================================


def _shell_split(argv_text):
    """Split one recorded argument vector.  The workflow supplies it already space-separated with
    no embedded quoting, which the validation below enforces rather than assumes."""
    if not isinstance(argv_text, str) or not argv_text.strip():
        _fail("COMPILE_INSTANCE_MALFORMED", "empty argv")
    for character in (chr(34), chr(39), "`", "$"):
        if character in argv_text:
            _fail("COMPILE_INSTANCE_MALFORMED", "argv carries shell metacharacters")
    return argv_text.split()


def parse_compile_instance(declaration, repository_root, upstream_root, job_id=None):
    """Parse one `<kind>:<instance_id>:<argv>` declaration into a governed instance record."""
    if not isinstance(declaration, str):
        _fail("COMPILE_INSTANCE_MALFORMED", "type")
    kind, _sep, remainder = declaration.partition(":")
    instance_id, _sep2, argv_text = remainder.partition(":")
    if job_id is None:
        job_id = GOVERNED_JOB_IDS[0]
    if job_id not in GOVERNED_JOB_IDS:
        _fail("COMPILE_INSTANCE_MALFORMED", "job id")
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

    if not inputs:
        _fail("COMPILE_INSTANCE_MALFORMED", "no inputs")
    if kind == INSTANCE_KIND_TRANSFORM:
        # An in-place transform names one artifact and rewrites it; the same path is both the
        # consumed PRE state and the produced POST state, which the two digests below distinguish.
        if output:
            _fail("COMPILE_INSTANCE_MALFORMED", "a transform does not redirect its output")
        if len(inputs) != 1:
            _fail("COMPILE_INSTANCE_MALFORMED", "a transform takes exactly one artifact")
        output = inputs[0]
    if not output:
        _fail("COMPILE_INSTANCE_MALFORMED", "no output artifact")

    classified = []
    for item in inputs:
        kind_of_input, normalised = classify_dependency(item, repository_root, upstream_root)
        classified.append(
            {
                # CANONICAL: named relative to its governed root, deterministic across runners.
                "path": normalised,
                "class": kind_of_input,
                # RAW: exactly what the command line said.  The only field with filesystem meaning.
                "raw_path": item,
                # GRAPH KEY: names the exact producer node, so a same-basename artifact from another
                # job can never satisfy this edge.  Never resolved, joined, opened or hashed.
                "graph_identity": _graph_identity(item, repository_root, job_id),
            }
        )
    return {
        "instance_id": instance_id,
        "kind": kind,
        "tool": tool,
        "argv": argv,
        "flags": sorted(flags),
        "include_roots": sorted(include_roots),
        "inputs": classified,
        "libraries": sorted(libraries),
        # Repair 5A: the graph node identity is the CANONICAL PATH, never the basename.  Two jobs
        # can each produce a policy.o, and a basename cannot say which one a link consumed.
        "job_id": job_id,
        # GRAPH KEY / CANONICAL / RAW, in that order.  All three are recorded because all three are
        # different facts, and the previous single "output" had to serve as whichever one the
        # reading code happened to want.
        "output": _graph_identity(output, repository_root, job_id),
        "output_path": _canonical_path(output, repository_root),
        "raw_output": output,
        "working_directory_class": WORKING_DIRECTORY_CLASS,
    }


def _canonical_path(path, repository_root):
    absolute = os.path.normpath(os.path.abspath(path))
    root = os.path.normpath(os.path.abspath(repository_root))
    if absolute == root or absolute.startswith(root + os.sep):
        return os.path.relpath(absolute, root).replace(os.sep, "/")
    build_root = os.environ.get("RUNNER_TEMP")
    if build_root:
        build_root = os.path.normpath(os.path.abspath(build_root))
        if absolute.startswith(build_root + os.sep):
            # Relative to the build area, so the identity does not carry a runner-specific prefix
            # that differs between jobs for reasons unrelated to what the artifact IS.
            return os.path.relpath(absolute, build_root).replace(os.sep, "/")
    return absolute.replace(os.sep, "/")


def _graph_identity(path, repository_root, job_id):
    """One canonical JOB-scoped identity for a build artifact node."""
    return job_id + ":" + _canonical_path(path, repository_root)


def record_invocation(log_path, instance_id, kind, argv, repository_root, upstream_root, job_id, digest_before=None):
    """Validate, THEN run ONE real native invocation, then append its observed record.

    The wrapper is the single point at which a build command becomes evidence: the argv recorded is
    the argv executed, because the same list is used for both.  The ordering below is the contract --
    PARSE, then COMPLETE VALIDATION, then EXECUTE.  An invalid invocation produces no child process
    at all, which is what makes this a gate rather than an audit trail.
    """
    executable, _preview, validated_output_path = validate_build_command(
        kind, argv, repository_root, upstream_root, instance_id, job_id
    )
    working_directory = os.path.normpath(os.path.abspath(repository_root))
    if not os.path.isdir(working_directory):
        _fail("BUILD_COMMAND_REJECTED", "working directory")
    environment = governed_build_environment()
    # The resolved absolute executable replaces the caller's basename, so the process that runs is
    # the one that was validated rather than whatever PATH would have found at exec time.
    resolved_argv = [executable] + list(argv[1:])
    completed = subprocess.run(  # noqa: S603 - validated argv list, frozen executable, no shell
        resolved_argv,
        check=False,
        shell=False,
        cwd=working_directory,
        env=environment,
    )
    if completed.returncode != 0:
        _fail("BUILD_INVOCATION_FAILED", instance_id)
    record = parse_compile_instance(
        kind + ":" + instance_id + ":" + " ".join(argv), repository_root, upstream_root, job_id
    )
    record["resolved_tool_path"] = executable
    record["working_directory"] = _canonical_path(working_directory, repository_root)
    if kind == INSTANCE_KIND_TRANSFORM:
        # An in-place transform has two distinct graph STATES even though the path is unchanged, so
        # both digests are bound and downstream consumers must name the post state.
        #
        # CONTROLLER REPAIR 3: digest_after hashes VALIDATED_OUTPUT_PATH -- the exact absolute file
        # the pre-execution contract proved governed.  The previous line joined the working
        # directory to a GRAPH IDENTITY ("s3c-build-candidate:obj/blst_server.o"), naming a file
        # that no build ever writes, so the honest objcopy path could not produce evidence at all.
        record["transform_target"] = record["inputs"][0]["graph_identity"]
        record["digest_before"] = digest_before or ""
        record["digest_after"] = _sha256_file(validated_output_path)
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
        if tuple(sorted(instance)) != tuple(sorted(instance_fields_for(instance.get("kind")))):
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
    for required in REQUIRED_TRANSFORM_INSTANCES:
        if required not in seen:
            _fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", required)

    validate_build_graph(instances)

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

    # CONTROLLER REPAIR 4: the legacy basename producer/consumer check is GONE.
    #
    # It compared two domains that cannot meet: `produced` held job-scoped graph identities like
    # "s3c-build-candidate:obj/policy.o" while `consumed` held bare basenames like "policy.o", so
    # no honest link could ever satisfy it.  validate_build_graph above is the ONE authoritative
    # producer/consumer model -- job, canonical path, state and producing operation -- and adding a
    # second partial verifier alongside it is what let this one rot unnoticed.
    return instances


def validate_build_graph(instances):
    """Repair 5A and 5C.  Every consumed artifact has EXACTLY ONE recorded producer.

    Identity is the canonical path, never the basename: two jobs can each produce a policy.o, and a
    basename cannot say which one a link consumed.  A transform makes the same path carry two
    distinct graph STATES, so the producer of a transformed object is the TRANSFORM, not the compile
    that preceded it -- a downstream consumer that named the pre-transform producer would be
    consuming bytes that no longer exist.
    """
    producers = {}
    for instance in instances:
        identity = instance["output"]
        if instance["kind"] == INSTANCE_KIND_TRANSFORM:
            # The transform SUPERSEDES the earlier producer of the same path.
            producers[identity] = instance["instance_id"]
        elif identity in producers:
            _fail("BUILD_GRAPH_DUPLICATE_PRODUCER", identity)
        else:
            producers[identity] = instance["instance_id"]

    # A transform must consume something a recorded operation actually produced.
    for instance in instances:
        if instance["kind"] != INSTANCE_KIND_TRANSFORM:
            continue
        if instance.get("digest_before") == instance.get("digest_after"):
            _fail("BUILD_GRAPH_TRANSFORM_INERT", instance["instance_id"])
        for field in ("digest_before", "digest_after"):
            value = instance.get(field)
            if not _is_hex64(value):
                _fail("BUILD_GRAPH_TRANSFORM_DIGEST_INVALID", instance["instance_id"])

    for instance in instances:
        if instance["kind"] != INSTANCE_KIND_LINK:
            continue
        expected = REQUIRED_LINK_INPUT_PRODUCERS.get(instance["instance_id"])
        if expected is None:
            _fail("BUILD_GRAPH_UNKNOWN_LINK", instance["instance_id"])
        observed = []
        for item in instance["inputs"]:
            identity = item["graph_identity"]
            producer = producers.get(identity)
            if producer is None:
                _fail("BUILD_GRAPH_UNPRODUCED_INPUT", identity)
            observed.append(producer)
        if tuple(observed) != tuple(expected):
            _fail("BUILD_GRAPH_LINK_INPUTS_MISMATCH", instance["instance_id"])
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


def split_command_tail(raw):
    """Repair 3A.  Extract the governed command tail BEFORE any wrapper option is parsed.

    argparse cannot be allowed to see `-- gcc -c ...`: it treats the tail as unrecognised
    positionals and exits 2, which under `set -euo pipefail` terminated the very first governed
    build command.  The separator is therefore located first, and the parser only ever sees the
    wrapper's own options.
    """
    if raw is None:
        raw = list(sys.argv[1:])
    raw = list(raw)
    separators = [index for index, word in enumerate(raw) if word == "--"]
    if len(separators) > 1:
        _fail("BUILD_INVOCATION_SEPARATOR_AMBIGUOUS", str(len(separators)))
    if not separators:
        return raw, None
    index = separators[0]
    return raw[:index], raw[index + 1 :]


def main(argv=None):
    wrapper_argv, command_argv = split_command_tail(argv)
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
    parser.add_argument("--digest-before")
    parser.add_argument("--job-id")
    parser.add_argument("--system-library", action="append")
    # Repair 3D: this names a TOOL for library resolution, never a path.  An arbitrary
    # executable, a shell, an interpreter or a repository script cannot be selected through it.
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
    args = parser.parse_args(wrapper_argv)

    if args.run_invocation:
        if not args.instance_log or not args.invocation_kind or not args.repository_root or not args.upstream_root:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "--run-invocation")
        if not args.job_id:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "--job-id")
        if command_argv is None:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "command separator")
        if not command_argv:
            _fail("BUILD_MANIFEST_ARGUMENT_MISSING", "invocation argv")
        record_invocation(
            args.instance_log,
            args.run_invocation,
            args.invocation_kind,
            command_argv,
            args.repository_root,
            args.upstream_root,
            args.job_id,
            args.digest_before,
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
    # A governed failure reaches the workflow as a FROZEN marker on stderr and a nonzero exit,
    # not as a traceback: under `set -euo pipefail` the exit code is what stops the build, and
    # the marker is what an operator reads.
    try:
        raise SystemExit(main())
    except BuildManifestError as error:
        sys.stderr.write("MT4_S3C_BUILD_MANIFEST_FAILED=" + str(error) + chr(10))
        raise SystemExit(1) from None
