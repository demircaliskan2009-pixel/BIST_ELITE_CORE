"""MT4-S3C P0 trusted default-branch attestation gate.  Qualification infrastructure only.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 16.4, 22, 23, 24, 25, 26,
27, 28.6.  PATH N03.  DELIBERATELY NOT A SOURCE-BUNDLE ENTRY: it carries its OWN separate commitment
APPROVED_S3C_TRUSTED_GATE_SHA256, and including it in the bundle it verifies would be circular.

WHERE THIS RUNS.  Only from .github/workflows/crypto_core_mt4_s3c_trusted_attestation.yml, which is
triggered by workflow_run restricted to the default branch.  A pull request can therefore never
cause this file to execute with credential-bearing authority: the workflow definition that grants
that authority must already exist on the default branch.

WHAT IT PROVES.  It re-derives, from scratch, every fact the attestation would assert -- the source
run identity and attempt, the complete paginated job and artifact enumerations with their governed
total_count reconciliation, the exact expected artifact set, every content digest, the qualification
source bundle digest, the compile dependency inventory, and every per-case internal filter
equivalence digest.  A3 == A4 == STAGE_C_RECOMPUTED, or the gate fails closed.

WHAT IT NEVER DOES.  It executes nothing from the source run.  Downloaded bytes are DATA ONLY.  It
imports no repository module.  It contains no importlib, no __import__, no exec, no eval, no
compile, no subprocess and no ctypes.  TRUSTED_STAGE_C = DATA_ONLY.

THE STARTUP ATTESTATION IS THE FIRST THING THAT RUNS, AND IT IS NOT CIRCULAR.  A Python startup
environment is itself an import surface: the working directory or script directory on sys.path, a
sitecustomize or usercustomize module, PYTHONPATH, PYTHONHOME or a startup hook can each cause a
CHECKOUT-CONTROLLED file to be imported in place of a standard-library module.  Because this gate
runs the checkout at the SOURCE-RUN HEAD, a file named json.py or zipfile.py landing anywhere on the
effective import path would execute with credential-bearing authority before any allowlist could
matter.  The AST allowlist governs which NAMES are imported; it says nothing about which FILES those
names resolve to.  The attestation below therefore runs BEFORE any further import, using ONLY the
built-in module sys -- chosen precisely because it is compiled into the interpreter and cannot be
shadowed by any file -- and it PROVES sys.path carries no repository-controlled directory before a
single filesystem-resolved module is imported.  Only then are the standard-library modules imported,
and their origins are validated explicitly, and validated again before the first untrusted byte is
parsed.
"""

import sys

# =================================================================================================
# TRUSTED_GATE_STARTUP_ATTESTATION_V1 (V9 SECTION 26.4) -- S-1 .. S-4, BEFORE ANY FURTHER IMPORT.
# Only `sys` is bound at this point.  Nothing below this block may move above it.
# =================================================================================================

MARKER_PYTHON_INVOCATION_VIOLATION = "TRUSTED_PYTHON_INVOCATION_VIOLATION"
MARKER_PYTHON_PATH_VIOLATION = "TRUSTED_PYTHON_PATH_VIOLATION"
MARKER_PYTHON_ORIGIN_VIOLATION = "TRUSTED_PYTHON_ORIGIN_VIOLATION"
MARKER_PYTHON_ENVIRONMENT_VIOLATION = "TRUSTED_PYTHON_ENVIRONMENT_VIOLATION"

ORIGIN_BUILTIN = "BUILTIN"
ORIGIN_FROZEN = "FROZEN"
ORIGIN_STDLIB_SOURCE = "STDLIB_SOURCE"
ORIGIN_STDLIB_EXTENSION = "STDLIB_EXTENSION"

# THE FIFTH ALLOWED ORIGIN CLASS, AND WHY IT MUST EXIST.
#
# The gate is a repo-resident file, and it executes as __main__.  An origin policy that allowed only
# built-in, frozen and standard-library origins would therefore reject the HONEST gate for the sole
# reason that it is the entry point -- a false positive, not a security property.  V9 SECTION 26
# closes that with an exact, DIGEST-BOUND entrypoint class rather than with a blanket exemption for
# __main__ or for the workspace.
#
# The class is granted to a module ONLY when both hold:
#   * the invoking trusted surface NAMED that absolute path as an entrypoint, and
#   * the file's SHA-256 equals the digest the trusted surface supplied alongside the path.
#
# The declaration comes from the credential-bearing default-branch workflow, which is the trust
# boundary itself; the CHECKOUT never contributes to it.  A checkout-controlled file cannot acquire
# the class, because it cannot make the trusted surface name it and cannot make its bytes hash to a
# digest the trusted surface already pinned.  A permanent test asserts the production workflow
# declares EXACTLY ONE entrypoint and that it is the gate path with the approved constant.
ORIGIN_DECLARED_ENTRYPOINT = "TRUSTED_ENTRYPOINT"

ALLOWED_ORIGIN_CLASSES = (
    ORIGIN_BUILTIN,
    ORIGIN_FROZEN,
    ORIGIN_STDLIB_SOURCE,
    ORIGIN_STDLIB_EXTENSION,
    ORIGIN_DECLARED_ENTRYPOINT,
)


# Every local file the gate reads is bounded.  The entrypoint source and the two inventories the
# trusted workflow supplies are all small, structured documents; an unbounded read would be a
# resource hazard whatever produced the bytes, and no read in this file is unbounded.
MAX_LOCAL_INPUT_BYTES = 4 * 1024 * 1024


def _attestation_failure(marker, detail):
    """Fail the attestation with a FROZEN marker and a FROZEN detail literal.

    Neither argument may ever carry environment-derived, path-derived or argument-derived
    text.  This channel runs on the credential-bearing trusted surface, and a failure
    message that echoed an environment variable name, a sys.path entry or a module origin
    would write attacker-influenced content into a log an operator reads.  The marker
    identifies the violation class exactly, which is what a fail-closed decision needs;
    the workflow log already carries the invocation context for everything else.
    """
    sys.stderr.write("MT4_S3C_TRUSTED_GATE_FAILED=" + marker + ":" + detail + "\n")
    raise SystemExit(3)


def _normalise_path(text):
    """Normalise separators without importing anything.  The gate runs on Linux x86_64."""
    if not isinstance(text, str):
        return ""
    normalised = text.replace("\\", "/")
    while "//" in normalised:
        normalised = normalised.replace("//", "/")
    if len(normalised) > 1 and normalised.endswith("/"):
        normalised = normalised[:-1]
    return normalised


def _is_contained(candidate, root):
    """True when `candidate` is `root` itself or lies strictly beneath it."""
    candidate = _normalise_path(candidate)
    root = _normalise_path(root)
    if not candidate or not root:
        return False
    return candidate == root or candidate.startswith(root + "/")


def _argument_value(name):
    """Read one frozen argument using sys.argv only.  No parser is imported yet."""
    argv = sys.argv
    index = 1
    while index + 1 < len(argv):
        if argv[index] == name:
            return argv[index + 1]
        index += 2
    return None


def _argument_values(name):
    """Read every occurrence of one repeatable frozen argument, using sys.argv only."""
    values = []
    argv = sys.argv
    index = 1
    while index + 1 < len(argv):
        if argv[index] == name:
            values.append(argv[index + 1])
        index += 2
    return values


def _resolve_declared_entrypoints():
    """Verify every declared entrypoint against the digest the trusted surface supplied.

    Each declaration has the frozen shape <64 lowercase hex>:<absolute path>.  The digest prefix is
    fixed-length, so the separator is unambiguous even for a path containing a colon.  Verification
    is by CONTENT: the file is read and hashed here, so naming a path is not enough -- the bytes
    must be the bytes the trusted surface already pinned.
    """
    import hashlib  # noqa: PLC0415 - imported only after S-3 proved sys.path carries no repo entry

    resolved = {}
    for declaration in _argument_values("--trusted-entrypoint"):
        if len(declaration) < 66 or declaration[64] != ":":
            _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "malformed entrypoint declaration")
        declared_digest = declaration[:64]
        declared_path = _normalise_path(declaration[65:])
        if any(character not in "0123456789abcdef" for character in declared_digest):
            _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "malformed entrypoint digest")
        if not declared_path.startswith("/") and not (len(declared_path) > 2 and declared_path[1] == ":"):
            _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "entrypoint path must be absolute")
        try:
            with open(declared_path, "rb") as handle:
                body = handle.read(MAX_LOCAL_INPUT_BYTES + 1)
            if len(body) > MAX_LOCAL_INPUT_BYTES:
                _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "entrypoint exceeds the governed bound")
            actual_digest = hashlib.sha256(body).hexdigest()
        except OSError:
            _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "entrypoint is unreadable")
            return {}
        if actual_digest != declared_digest:
            _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "entrypoint digest mismatch")
        resolved[declared_path] = declared_digest
    if not resolved:
        _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "--trusted-entrypoint is required")
    return resolved


def _startup_attestation_first_pass():
    # S-1.  This is the check that makes a plain `python gate.py` invocation fail the contract even
    # if the workflow text were changed: the flags are a REQUEST, and this is the PROOF.
    if int(getattr(sys.flags, "isolated", 0)) != 1:
        _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "isolated mode is not active")
    if int(getattr(sys.flags, "no_site", 0)) != 1:
        _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "site import is not disabled")

    # S-2.  APPROVED_STDLIB_ROOTS are derived FROM THE INTERPRETER ITSELF, never from the
    # environment: deriving them from an environment variable would reintroduce exactly the
    # influence isolated mode removes.
    roots = []
    for prefix in (sys.base_prefix, sys.base_exec_prefix):
        normalised = _normalise_path(prefix)
        if not normalised:
            _attestation_failure(MARKER_PYTHON_ORIGIN_VIOLATION, "interpreter reported no base prefix")
        if normalised not in roots:
            roots.append(normalised)

    # S-3.  Every sys.path entry must resolve OUTSIDE the repository workspace root and outside the
    # artifact/scratch directory.  This is the check that does not depend on the exact semantics of
    # any flag: whatever isolated mode and no-site do or do not do on the pinned interpreter, the
    # resulting path is MEASURED and must be clean.  It runs before any filesystem-resolved module
    # is imported, which is what makes the later imports non-circular.
    workspace = _normalise_path(_argument_value("--workspace-root") or "")
    scratch = _normalise_path(_argument_value("--work-dir") or "")
    if not workspace:
        _attestation_failure(MARKER_PYTHON_INVOCATION_VIOLATION, "--workspace-root is required")
    for entry in sys.path:
        normalised = _normalise_path(entry)
        if normalised in ("", "."):
            _attestation_failure(MARKER_PYTHON_PATH_VIOLATION, "the working directory is on sys.path")
        if _is_contained(normalised, workspace):
            _attestation_failure(MARKER_PYTHON_PATH_VIOLATION, "a repository-controlled directory is on sys.path")
        if scratch and _is_contained(normalised, scratch):
            _attestation_failure(MARKER_PYTHON_PATH_VIOLATION, "a scratch directory is on sys.path")

    # The entrypoint set is resolved and DIGEST-VERIFIED before origin validation, because origin
    # validation needs it: the honest gate's own module is a repo-resident file, and it must be
    # admitted by exact digest-bound identity rather than by a blanket workspace exemption.
    entrypoints = _resolve_declared_entrypoints()

    _validate_module_origins(roots, workspace, scratch, entrypoints)
    return roots, workspace, scratch, entrypoints


def _classify_origin(module, roots, entrypoints):
    """S-4 origin classification over ONE module."""
    spec = getattr(module, "__spec__", None)
    origin = getattr(spec, "origin", None) if spec is not None else getattr(module, "__file__", None)
    if origin in ("built-in", None) and getattr(module, "__file__", None) is None:
        return ORIGIN_BUILTIN, ""
    if origin == "frozen":
        return ORIGIN_FROZEN, ""
    location = _normalise_path(origin if isinstance(origin, str) else "")
    if not location:
        return ORIGIN_BUILTIN, ""
    if location in entrypoints:
        return ORIGIN_DECLARED_ENTRYPOINT, location
    for root in roots:
        if _is_contained(location, root):
            if location.endswith(".so") or location.endswith(".pyd") or location.endswith(".dylib"):
                return ORIGIN_STDLIB_EXTENSION, location
            return ORIGIN_STDLIB_SOURCE, location
    return "FOREIGN", location


def _validate_module_origins(roots, workspace, scratch, entrypoints):
    """S-4 and S-6.

    Validation covers EVERY module currently in sys.modules rather than an enumerated name list.
    That is deliberate: it covers every TRANSITIVE import without requiring the architecture to
    guess the transitive closure of urllib, ssl, http and email, which would be a guess and would
    rot.  Anything resolving under the repository workspace root is the exact hazard this exists to
    catch.
    """
    for name in sorted(sys.modules):
        module = sys.modules.get(name)
        if module is None:
            continue
        origin_class, location = _classify_origin(module, roots, entrypoints)
        if origin_class not in ALLOWED_ORIGIN_CLASSES:
            _attestation_failure(MARKER_PYTHON_ORIGIN_VIOLATION, "a module resolves to a disallowed origin class")
        if origin_class == ORIGIN_DECLARED_ENTRYPOINT:
            # Already admitted by exact digest-bound identity.  The workspace and scratch checks
            # below deliberately do NOT apply to it: the honest gate is a repo-resident file, and
            # rejecting it for that reason alone would be a false positive rather than a control.
            continue
        if location and workspace and _is_contained(location, workspace):
            _attestation_failure(
                MARKER_PYTHON_ORIGIN_VIOLATION,
                "a module resolves under the repository workspace root",
            )
        if location and scratch and _is_contained(location, scratch):
            _attestation_failure(MARKER_PYTHON_ORIGIN_VIOLATION, "a module resolves under the scratch directory")


(
    _APPROVED_STDLIB_ROOTS,
    _WORKSPACE_ROOT,
    _SCRATCH_ROOT,
    _DECLARED_ENTRYPOINTS,
) = _startup_attestation_first_pass()

# =================================================================================================
# DECLARED DIRECT IMPORT SET (V9 SECTION 26.5).
#
# A permanent test asserts the source imports EXACTLY this set and nothing else.  Transitive imports
# pulled in by these (for example the TLS, socket and HTTP machinery behind urllib) are deliberately
# NOT enumerated: S-4 validates ORIGIN over the whole of sys.modules, which covers the transitive
# closure without guessing it.  THE GATE IMPORTS NO REPOSITORY MODULE AT ALL.
# =================================================================================================

import argparse  # noqa: E402
import hashlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import pathlib  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402
import urllib.request  # noqa: E402
import zipfile  # noqa: E402
import zlib  # noqa: E402

# S-5.  A PREFIX rule rather than a list, so a future PYTHON* variable is forbidden by DEFAULT
# rather than by omission.  Presence of any such variable is a violation.
FORBIDDEN_ENVIRONMENT_PREFIX = "PYTHON"


def _environment_attestation():
    for name in sorted(os.environ):
        if name.startswith(FORBIDDEN_ENVIRONMENT_PREFIX):
            _attestation_failure(
                MARKER_PYTHON_ENVIRONMENT_VIOLATION,
                "an environment variable carrying the forbidden prefix is present",
            )


_environment_attestation()

# =================================================================================================
# FROZEN IDENTITIES AND GOVERNED BOUNDS
# =================================================================================================

PLATFORM_ID = "LINUX_X86_64"

SOURCE_BUNDLE_SCHEMA = "mt4-s3c-qualification-source-bundle.v1"
SOURCE_BUNDLE_DIGEST_DOMAIN = b"mt4-s3c-qualification-source-bundle.v1\x00"
DEPENDENCY_SCHEMA = "mt4-s3c-compile-dependency-inventory.v1"
DEPENDENCY_DIGEST_DOMAIN = b"mt4-s3c-compile-dependency-inventory.v1\x00"
INTERNAL_EQUIVALENCE_SCHEMA = "mt4-s3c-internal-filter-equivalence.v1"
INTERNAL_EQUIVALENCE_DIGEST_DOMAIN = b"mt4-s3c-internal-filter-equivalence.v1\x00"
PROGRAM_REPRESENTATION_VERSION = "mt4-s3c-cbpf-canonical.v1"
STAGE_C_PREDICATE_SCHEMA = "mt4-s3c-trusted-stage-c-predicate.v1"
STAGE_C_PREDICATE_DIGEST_DOMAIN = b"mt4-s3c-trusted-stage-c-predicate.v1\x00"

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

# Bundle entry 16.  The governed TEST-ONLY fixture, whose committed digest is the independent
# anchor for the protocol/case-plan identity chain.
GOVERNED_FIXTURE_PATH = "tests/crypto_core/fixtures/mt4_s3c_test_only_positive_vector_v1.json"

# =================================================================================================
# THE COMPILE INVENTORY CONTRACT, INDEPENDENTLY FROZEN ON THE TRUSTED SURFACE (repair 7F and 7G).
#
# A1, A2 and A4 all carry the inventory digest.  None of them is authority: the schema, the exact
# entry field set, the class-determined provenance, the uniqueness rule and the required
# translation-unit coverage are all pinned HERE, and the digest is recomputed from an inventory that
# satisfied them.  A build that silently drops the pinned upstream inputs, the observer translation
# unit or the probe translation unit therefore fails at the trust boundary, which is the only place
# the omission could not have been arranged.
# =================================================================================================

DEPENDENCY_ENTRY_FIELDS = ("class", "path", "provenance", "sha256")

CLASS_REPO_BUNDLED = "REPO_BUNDLED"
CLASS_UPSTREAM_PINNED = "UPSTREAM_PINNED"
CLASS_EXTERNAL_TOOLCHAIN = "EXTERNAL_TOOLCHAIN"
DEPENDENCY_CLASSES = (CLASS_REPO_BUNDLED, CLASS_UPSTREAM_PINNED, CLASS_EXTERNAL_TOOLCHAIN)

# Transcribed from the governing S3B verifier profile (V9 SECTION 9 R6).  A literal on the trusted
# surface: the gate imports no repository module, and a candidate-reported pin would be forgeable.
UPSTREAM_COMMIT = "54e6e55674722fc2797ebb4bbb71b26d881eb4b8"
UPSTREAM_SOURCE_TREE_DIGEST = "5a709c19ef7a1b9798ad58728fc5dd3b4d2026ecdd0342ebf8546c5950cea006"
UPSTREAM_RELEASE = "v0.3.17"
UPSTREAM_REPOSITORY = "https://github.com/supranational/blst"

PROVENANCE_REPO_BUNDLED = "QUALIFICATION_SOURCE_BUNDLE_V1"
PROVENANCE_UPSTREAM_PINNED = "BLST_PINNED_COMMIT_" + UPSTREAM_COMMIT + "_TREE_" + UPSTREAM_SOURCE_TREE_DIGEST
PROVENANCE_EXTERNAL_TOOLCHAIN = "UBUNTU_22_04_PINNED_RUNNER_TOOLCHAIN"

CLASS_PROVENANCE = {
    CLASS_REPO_BUNDLED: PROVENANCE_REPO_BUNDLED,
    CLASS_UPSTREAM_PINNED: PROVENANCE_UPSTREAM_PINNED,
    CLASS_EXTERNAL_TOOLCHAIN: PROVENANCE_EXTERNAL_TOOLCHAIN,
}

REQUIRED_TRANSLATION_UNITS = (
    "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
)
REQUIRED_UPSTREAM_INPUTS = ("src/server.c", "build/assembly.S")

# =================================================================================================
# THE ACTUAL COMPILE/LINK INSTANCE CONTRACT, FROZEN ON THE TRUSTED SURFACE (repair 8).
#
# Dependency evidence proves what a compilation INCLUDED.  It does not prove WHICH compilation made
# the artifact, so the instance inventory -- one record per real native invocation, with its tool,
# argument vector, inputs, flags and output -- is validated here too.  The required set is derived
# from the reviewed workflow, not from a count an earlier build reported.
# =================================================================================================

COMPILE_INSTANCE_SCHEMA = "mt4-s3c-compile-instance-inventory.v1"
COMPILE_INSTANCE_DIGEST_DOMAIN = b"mt4-s3c-compile-instance-inventory.v1\x00"

# The fields EVERY recorded invocation carries.  resolved_tool_path and working_directory are
# the wrapper's frozen execution boundary made evidence: the tool that actually ran and the
# directory it ran in, rather than a basename and an assumption.
# ONE exact instance schema, identical to the producer's (controller repair 1).  The producer and
# this consumer previously disagreed about job_id and raw_output, which meant the producer rejected
# its own honest record before the trust boundary ever saw it.
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

# The exact field set of ONE consumed input: canonical path, raw execution path, graph key, class.
COMPILE_INPUT_FIELDS = ("class", "graph_identity", "path", "raw_path")

# A TRANSFORM rewrites an artifact in place, so its record carries the two distinct graph
# STATES of the same path.  Without them the post-transform bytes would be indistinguishable
# from the pre-transform ones in the graph.
TRANSFORM_INSTANCE_FIELDS = tuple(
    sorted(COMPILE_INSTANCE_FIELDS + ("digest_after", "digest_before", "transform_target"))
)


def instance_fields_for(kind):
    """The exact field set one recorded invocation must carry, by operation class."""
    if kind == "TRANSFORM":
        return TRANSFORM_INSTANCE_FIELDS
    return COMPILE_INSTANCE_FIELDS


# THE COMPLETE GRAPH.  Fifteen compiles and five links, derived from the reviewed workflow's
# ACTUAL commands across all three jobs -- not from a count an earlier implementation reported, and
# not from a hand-written declaration list.  Every one of these is recorded by the build wrapper at
# the moment it runs.
REQUIRED_COMPILE_INSTANCES = (
    "adjudicate-policy",
    "adjudicate-probe",
    "blst-assembly",
    "blst-server",
    "observe-launcher",
    "observe-policy",
    "observe-probe",
    "observer-launcher",
    "observer-policy",
    "observer-probe",
    "worker-bootstrap",
    "worker-capability",
    "worker-policy",
    "worker-start",
    "worker-verify",
)
REQUIRED_LINK_INSTANCES = (
    "adjudicate-probe-link",
    "observe-observer-link",
    "observe-probe-link",
    "observer-link",
    "worker-link",
)
# Repair 5D: the two objcopy operations REWRITE the object bytes that are later linked and
# qualified.  A graph that called itself complete while omitting a step that changes the artifact
# was describing an intention, not the build.
REQUIRED_TRANSFORM_INSTANCES = (
    "blst-assembly-strip",
    "blst-server-strip",
)
EXPECTED_COMPILE_INSTANCE_COUNT = 15
EXPECTED_LINK_INSTANCE_COUNT = 5
EXPECTED_TRANSFORM_INSTANCE_COUNT = 2
EXPECTED_BUILD_OPERATION_COUNT = (
    EXPECTED_COMPILE_INSTANCE_COUNT + EXPECTED_LINK_INSTANCE_COUNT + EXPECTED_TRANSFORM_INSTANCE_COUNT
)

# Repair 5B and 5C: the EXACT producer of every object each real link consumes, in order.  Derived
# from the reviewed workflow's actual link commands.  The producer of a TRANSFORMED object is the
# transform, never the compile that preceded it: a consumer naming the compile would be claiming
# bytes that no longer exist.
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
    "observe-observer-link": ("observe-launcher", "observe-policy"),
    "observe-probe-link": ("observe-probe", "observe-policy"),
    "adjudicate-probe-link": ("adjudicate-probe", "adjudicate-policy"),
}

# The build job observes only its OWN invocations; the observe and adjudicate jobs record theirs and
# carry them in the artifacts they already upload.  The manifest digest therefore binds the build
# job's inventory, and the COMPLETE graph is required at the boundary from the union of all three.
BUILD_JOB_INSTANCES = (
    "blst-assembly",
    "blst-assembly-strip",
    "blst-server",
    "blst-server-strip",
    "observer-launcher",
    "observer-link",
    "observer-policy",
    "observer-probe",
    "worker-bootstrap",
    "worker-capability",
    "worker-link",
    "worker-policy",
    "worker-start",
    "worker-verify",
)
INSTANCE_LOG_SCHEMA = "mt4-s3c-build-instance-log.v1"
REQUIRED_SYSTEM_LIBRARIES = ("cap",)
# The approved tool for each governed operation class.  objcopy is the ONLY tool permitted to
# rewrite an artifact, and gcc the only one permitted to produce one.
APPROVED_BUILD_TOOL = "gcc"
APPROVED_TRANSFORM_TOOL = "objcopy"

# Repair 6C and 6D: the boundary validates the RESOLVED tool and the working directory, not a
# basename and an assumption.  Both are recorded by the wrapper's frozen execution boundary.
APPROVED_TOOLCHAIN_ROOTS = ("/usr/bin/", "/usr/local/bin/", "/bin/")
APPROVED_WORKING_DIRECTORY = "."

# Repair 5: the real workflow reuses pathnames across jobs, so graph identity carries the job.
GOVERNED_JOB_IDS = ("s3c-build-candidate", "s3c-observe", "s3c-adjudicate")

# Repair 6E: ONE libcap authority, agreed by producer and consumer.  The logical name is what the
# link requests; the resolved file is what the linker actually selected; both travel together.
GOVERNED_SYSTEM_LIBRARY_NAME = "cap"
APPROVED_SYSTEM_LIBRARY_ROOTS = ("/usr/lib/", "/lib/")
APPROVED_TOOL_BY_KIND = {
    "COMPILE": APPROVED_BUILD_TOOL,
    "LINK": APPROVED_BUILD_TOOL,
    "TRANSFORM": APPROVED_TRANSFORM_TOOL,
}

# =================================================================================================
# SYSTEM LIBRARY PROVENANCE (repair 11).
#
# `-lcap` is a NAME the linker resolves; it is not an identity.  The build records the file the
# linker actually selected, and the trusted surface requires that record to be complete and to sit
# in the pinned runner's own library directories -- a resolution that landed anywhere else is not
# the library this build contract describes.  The system library stays in its OWN provenance class
# and never enters the 16-entry repository bundle.
# =================================================================================================

SYSTEM_LIBRARY_FIELDS = ("digest_sha256", "name", "provenance", "resolved_path", "soname")
APPROVED_SYSTEM_LIBRARY_ROOTS = ("/usr/lib/", "/lib/")
PROVENANCE_SYSTEM_LIBRARY = "UBUNTU_22_04_PINNED_RUNNER_LIBRARY"


def validate_system_libraries(payload):
    """Repair 11.  A resolved file identity, not a bare token."""
    entries = payload.get("system_libraries")
    if not isinstance(entries, list) or not entries:
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "missing")
    names = []
    for entry in entries:
        if not isinstance(entry, dict) or tuple(sorted(entry)) != tuple(sorted(SYSTEM_LIBRARY_FIELDS)):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "field set")
        name = require_str(entry.get("name"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        resolved = require_str(entry.get("resolved_path"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        digest = require_str(entry.get("digest_sha256"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        require_str(entry.get("soname"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        if entry.get("provenance") != PROVENANCE_SYSTEM_LIBRARY:
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "provenance")
        if not is_hex64(digest):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "digest")
        if not any(resolved.startswith(root) for root in APPROVED_SYSTEM_LIBRARY_ROOTS):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "resolved outside the pinned library roots")
        if name in names:
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "duplicate library")
        names.append(name)
    for required in REQUIRED_SYSTEM_LIBRARIES:
        if required not in names:
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "missing required library")
    if sorted(names) != sorted(REQUIRED_SYSTEM_LIBRARIES):
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "unexpected library")
    return names


WORKING_DIRECTORY_CLASS = "GITHUB_WORKSPACE"

# The link flags the frozen build contract requires.  A link that drops one of these produces a
# different kind of image than the one this qualification describes.
REQUIRED_WORKER_LINK_FLAGS = (
    "-static",
    "-no-pie",
    "-nostdlib",
    "-nostartfiles",
    "-Wl,-z,defs",
    "-Wl,-z,noexecstack",
    "-Wl,-z,max-page-size=0x1000",
    "-Wl,--build-id=none",
    "-Wl,--fatal-warnings",
)


def recompute_compile_instance_digest(payload):
    """Validate the ACTUAL compile/link inventory and recompute its digest (repair 8A, 8B, 8E)."""
    if not isinstance(payload, dict):
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "type")
    if payload.get("schema") != COMPILE_INSTANCE_SCHEMA:
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "schema")
    if tuple(sorted(payload)) != ("instance_count", "instance_id_order", "instances", "schema", "system_libraries"):
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "document field set")
    instances = payload.get("instances")
    if not isinstance(instances, list) or not instances:
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "instances")

    identifiers = []
    seen = set()
    kinds = {}
    libraries = set()
    for instance in instances:
        if not isinstance(instance, dict):
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "instance type")
        if tuple(sorted(instance)) != tuple(sorted(instance_fields_for(instance.get("kind")))):
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "instance field set")
        identifier = require_str(instance.get("instance_id"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
        if identifier in seen:
            fail("COMPILE_INSTANCE_DUPLICATE")
        seen.add(identifier)
        identifiers.append(identifier)
        kind = require_str(instance.get("kind"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
        if kind not in ("COMPILE", "LINK", "TRANSFORM"):
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "kind")
        kinds[identifier] = kind
        expected_tool = APPROVED_TOOL_BY_KIND[kind]
        if require_str(instance.get("tool"), "COMPILE_INSTANCE_INVENTORY_MISMATCH") != expected_tool:
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "tool")
        # Repair 6C: the RESOLVED executable, not the basename, and it must live in an approved root.
        resolved = require_str(instance.get("resolved_tool_path"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
        if not any(resolved.startswith(root) for root in APPROVED_TOOLCHAIN_ROOTS):
            fail("BUILD_TOOL_PROVENANCE_INVALID", "resolved tool is outside the approved roots")
        if resolved.rsplit("/", 1)[-1] != expected_tool:
            fail("BUILD_TOOL_PROVENANCE_INVALID", "resolved tool is not the approved tool")
        # Repair 6D: the working directory is bound end to end.
        if require_str(instance.get("working_directory"), "COMPILE_INSTANCE_INVENTORY_MISMATCH") != (
            APPROVED_WORKING_DIRECTORY
        ):
            fail("BUILD_CWD_PROVENANCE_INVALID")
        if require_str(instance.get("job_id"), "COMPILE_INSTANCE_INVENTORY_MISMATCH") not in GOVERNED_JOB_IDS:
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "job id")
        if (
            require_str(instance.get("working_directory_class"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
            != WORKING_DIRECTORY_CLASS
        ):
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "working directory class")
        argv = instance.get("argv")
        if not isinstance(argv, list) or not argv or argv[0] != expected_tool:
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "argv")
        inputs = instance.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "inputs")
        for item in inputs:
            if not isinstance(item, dict) or tuple(sorted(item)) != COMPILE_INPUT_FIELDS:
                fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "input shape")
            item_class = require_str(item.get("class"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
            item_path = require_str(item.get("path"), "COMPILE_INSTANCE_INVENTORY_MISMATCH")
            if item_class not in DEPENDENCY_CLASSES:
                fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "input class")
            if item_class == CLASS_REPO_BUNDLED and item_path not in SOURCE_BUNDLE_PATHS:
                fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED")
        instance_libraries = instance.get("libraries")
        if not isinstance(instance_libraries, list):
            fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "libraries")
        if kind == "LINK":
            libraries.update(require_str(item, "COMPILE_INSTANCE_INVENTORY_MISMATCH") for item in instance_libraries)

    # The BUILD JOB's own inventory must be exactly the invocations that job performs.
    if sorted(seen) != sorted(BUILD_JOB_INSTANCES):
        fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", "build job graph is not the governed set")
    # Repair 8C: system libraries are their OWN provenance class and must be recorded, not silently
    # absorbed into the repository bundle.
    for required in REQUIRED_SYSTEM_LIBRARIES:
        if required not in libraries:
            fail("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", "system library")

    # Repair 6E: ONE libcap authority.  The link requests a NAME; the producer records the FILE the
    # linker actually selected.  Both sides are checked here so neither can compare half of it.
    resolved_libraries = payload.get("system_libraries")
    if not isinstance(resolved_libraries, list) or not resolved_libraries:
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "missing resolution")
    resolved_names = []
    for entry in resolved_libraries:
        if not isinstance(entry, dict) or tuple(sorted(entry)) != (
            "digest_sha256",
            "name",
            "provenance",
            "resolved_path",
            "soname",
        ):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "field set")
        name = require_str(entry.get("name"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        path = require_str(entry.get("resolved_path"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        soname = require_str(entry.get("soname"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")
        if not is_hex64(require_str(entry.get("digest_sha256"), "SYSTEM_LIBRARY_PROVENANCE_INVALID")):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "digest")
        if entry.get("provenance") != PROVENANCE_SYSTEM_LIBRARY:
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "provenance")
        if not any(path.startswith(root) for root in APPROVED_SYSTEM_LIBRARY_ROOTS):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "resolved path is outside the approved roots")
        # The resolved file must actually be the library the NAME requested: -lcap resolves to a
        # file called libcap.*, and a mapping that lost that link would be provenance for nothing.
        if soname != path.rsplit("/", 1)[-1]:
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "soname does not name the resolved file")
        if not soname.startswith("lib" + name + "."):
            fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "resolved file does not match the requested name")
        resolved_names.append(name)
    if sorted(resolved_names) != sorted(REQUIRED_SYSTEM_LIBRARIES):
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "resolution set")
    if len(set(resolved_names)) != len(resolved_names):
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "duplicate resolution")
    # Every library a link requested must have been resolved, and nothing extra.
    if sorted(libraries) != sorted(resolved_names):
        fail("SYSTEM_LIBRARY_PROVENANCE_INVALID", "requested and resolved sets differ")

    worker_link = [instance for instance in instances if instance["instance_id"] == "worker-link"][0]
    worker_flags = set(worker_link.get("flags") or ())
    for required in REQUIRED_WORKER_LINK_FLAGS:
        if required not in worker_flags:
            fail("COMPILE_INSTANCE_LINK_CONTRACT_VIOLATED")

    if identifiers != sorted(identifiers):
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "ordering")
    if require_int(payload.get("instance_count"), "COMPILE_INSTANCE_INVENTORY_MISMATCH", 1) != len(instances):
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "instance_count")
    if payload.get("instance_id_order") != identifiers:
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "instance_id_order")
    return domain_digest(COMPILE_INSTANCE_DIGEST_DOMAIN, payload)


def _instances_from_log(payload, marker):
    """Decode ONE job's observed invocation log."""
    if not isinstance(payload, dict) or payload.get("schema") != INSTANCE_LOG_SCHEMA:
        fail(marker, "schema")
    instances = payload.get("instances")
    if not isinstance(instances, list) or not instances:
        fail(marker, "instances")
    for instance in instances:
        if not isinstance(instance, dict):
            fail(marker, "instance type")
        if tuple(sorted(instance)) != tuple(sorted(instance_fields_for(instance.get("kind")))):
            fail(marker, "instance field set")
        if require_str(instance.get("tool"), marker) != APPROVED_BUILD_TOOL:
            fail(marker, "tool")
    return instances


def require_complete_build_graph(build_payload, observe_log, adjudicate_log):
    """Repair 10.  The UNION of the three job logs must be the exact governed build graph.

    The auditor independently derived fifteen compiles and five links from the workflow's actual
    commands; the previous inventory recorded nine and two hand-written declarations.  Every
    invocation is now recorded by the wrapper that runs it, and the three logs are unioned here, so
    a command that ran without the wrapper is simply absent -- and absence fails.
    """
    instances = list(build_payload.get("instances") or ())
    instances += _instances_from_log(observe_log, "BUILD_GRAPH_INCOMPLETE")
    instances += _instances_from_log(adjudicate_log, "BUILD_GRAPH_INCOMPLETE")

    identifiers = []
    kinds = {}
    for instance in instances:
        identifier = require_str(instance.get("instance_id"), "BUILD_GRAPH_INCOMPLETE")
        if identifier in kinds:
            fail("BUILD_GRAPH_DUPLICATE_INSTANCE")
        kinds[identifier] = require_str(instance.get("kind"), "BUILD_GRAPH_INCOMPLETE")
        identifiers.append(identifier)

    governed = REQUIRED_COMPILE_INSTANCES + REQUIRED_LINK_INSTANCES + REQUIRED_TRANSFORM_INSTANCES
    if sorted(identifiers) != sorted(governed):
        fail("BUILD_GRAPH_INCOMPLETE", "graph is not the governed set")
    for required in REQUIRED_COMPILE_INSTANCES:
        if kinds.get(required) != "COMPILE":
            fail("BUILD_GRAPH_INCOMPLETE", required)
    for required in REQUIRED_LINK_INSTANCES:
        if kinds.get(required) != "LINK":
            fail("BUILD_GRAPH_INCOMPLETE", required)
    for required in REQUIRED_TRANSFORM_INSTANCES:
        if kinds.get(required) != "TRANSFORM":
            fail("BUILD_GRAPH_INCOMPLETE", required)
    if sum(1 for value in kinds.values() if value == "COMPILE") != EXPECTED_COMPILE_INSTANCE_COUNT:
        fail("BUILD_GRAPH_INCOMPLETE", "compile count")
    if sum(1 for value in kinds.values() if value == "LINK") != EXPECTED_LINK_INSTANCE_COUNT:
        fail("BUILD_GRAPH_INCOMPLETE", "link count")
    if sum(1 for value in kinds.values() if value == "TRANSFORM") != EXPECTED_TRANSFORM_INSTANCE_COUNT:
        fail("BUILD_GRAPH_INCOMPLETE", "transform count")
    if len(identifiers) != EXPECTED_BUILD_OPERATION_COUNT:
        fail("BUILD_GRAPH_INCOMPLETE", "operation count")

    # Repair 5A and 5C: PRODUCER -> CONSUMER edges over the WHOLE graph, by PATH-SCOPED identity.
    #
    # A basename is not an identity: three different jobs each produce a policy.o, and reducing the
    # graph to basenames made every one of them satisfy every consumer.  A transform SUPERSEDES the
    # producer of the path it rewrites, so the map below records it last for that node.
    producers = {}
    for instance in instances:
        output = require_str(instance.get("output"), "BUILD_GRAPH_INCOMPLETE")
        # Repair 5A and 5B: identity is JOB + canonical path.  Three jobs each produce
        # obj/policy.o, and only the job distinguishes them; a path-only or basename-only key would
        # see three producers for one node and could never close.
        if ":" not in output or output.split(":", 1)[0] not in GOVERNED_JOB_IDS:
            fail("BUILD_GRAPH_INCOMPLETE", "output identity is not job-scoped")
        if instance["kind"] == "TRANSFORM":
            before = require_str(instance.get("digest_before"), "BUILD_GRAPH_INCOMPLETE")
            after = require_str(instance.get("digest_after"), "BUILD_GRAPH_INCOMPLETE")
            if not is_hex64(before) or not is_hex64(after):
                fail("BUILD_GRAPH_TRANSFORM_DIGEST_INVALID")
            if before == after:
                # A transform that changed nothing is either mis-recorded or was not the operation
                # the graph claims; either way the record does not describe what happened.
                fail("BUILD_GRAPH_TRANSFORM_INERT")
            if output not in producers:
                fail("BUILD_GRAPH_TRANSFORM_INPUT_UNPRODUCED")
            # Repair 6A and 6B: the transform is ONE atomic state transition, and its own consumed
            # input must be the node it rewrites -- so the PRE state is the thing that existed and
            # the POST state is what every later consumer sees.
            consumed = instance.get("inputs") or ()
            if len(consumed) != 1:
                fail("BUILD_GRAPH_TRANSFORM_ARITY")
            if require_str(consumed[0].get("graph_identity"), "BUILD_GRAPH_INCOMPLETE") != output:
                fail("BUILD_GRAPH_TRANSFORM_TARGET_MISMATCH")
            if require_str(instance.get("transform_target"), "BUILD_GRAPH_INCOMPLETE") != output:
                fail("BUILD_GRAPH_TRANSFORM_TARGET_MISMATCH")
            producers[output] = instance["instance_id"]
        elif output in producers:
            fail("BUILD_GRAPH_DUPLICATE_PRODUCER")
        else:
            producers[output] = instance["instance_id"]

    for instance in instances:
        if instance["kind"] != "LINK":
            continue
        expected = REQUIRED_LINK_INPUT_PRODUCERS.get(instance["instance_id"])
        if expected is None:
            fail("BUILD_GRAPH_INCOMPLETE", "unknown link")
        observed = []
        for item in instance.get("inputs") or ():
            identity = require_str(item.get("graph_identity"), "BUILD_GRAPH_INCOMPLETE")
            producer = producers.get(identity)
            if producer is None:
                fail("BUILD_GRAPH_LINK_INPUT_UNPRODUCED")
            observed.append(producer)
        if tuple(observed) != tuple(expected):
            fail("BUILD_GRAPH_LINK_INPUTS_MISMATCH")
    return len(identifiers)


def bind_pinned_upstream_identity(manifest):
    """Repair 8D.  The pinned upstream identity is compared to TRUSTED LITERALS, not to a shape.

    The gate previously accepted any syntactically valid 64-hex value as an upstream digest, which
    is not provenance at all.  The commit and source-tree digest below are the ones the governing
    S3B verifier profile pins, transcribed onto this trusted surface, so a producer that names a
    different upstream tree fails here rather than being believed.

    WHAT THIS DOES NOT YET PROVE, stated rather than implied: the per-file upstream digests are
    bound into the inventory digest and to this pinned tree identity, but Stage C does not hold an
    independent per-file digest table for blst v0.3.17 and cannot obtain one without external
    evidence.  The predicate records that explicitly instead of claiming a verification that did
    not happen.
    """
    if manifest.get("upstream_commit") != UPSTREAM_COMMIT:
        fail("PINNED_UPSTREAM_IDENTITY_MISMATCH", "commit")
    if manifest.get("upstream_source_tree_digest") != UPSTREAM_SOURCE_TREE_DIGEST:
        fail("PINNED_UPSTREAM_IDENTITY_MISMATCH", "source tree digest")
    if manifest.get("upstream_release") != UPSTREAM_RELEASE:
        fail("PINNED_UPSTREAM_IDENTITY_MISMATCH", "release")
    if manifest.get("upstream_repository") != UPSTREAM_REPOSITORY:
        fail("PINNED_UPSTREAM_IDENTITY_MISMATCH", "repository")
    return {
        "upstream_commit": UPSTREAM_COMMIT,
        "upstream_source_tree_digest": UPSTREAM_SOURCE_TREE_DIGEST,
        "pinned_upstream_per_file_digests_verified": False,
    }


REQUIRED_JOBS = (
    "s3c-build-candidate",
    "s3c-elf-qualify",
    "s3c-observe",
    "s3c-adjudicate",
)

EXPECTED_ARTIFACT_SET = (
    "mt4-s3c-candidate-linux-x86_64",
    "mt4-s3c-elf-qualification-record",
    "mt4-s3c-qualification-receipt",
    "mt4-s3c-raw-observation-record",
)

CANDIDATE_ARTIFACT = "mt4-s3c-candidate-linux-x86_64"
ELF_ARTIFACT = "mt4-s3c-elf-qualification-record"
OBSERVATION_ARTIFACT = "mt4-s3c-raw-observation-record"
RECEIPT_ARTIFACT = "mt4-s3c-qualification-receipt"

WORKER_BINARY_MEMBER = "mt4_s3c_static_worker"
BUILD_MANIFEST_MEMBER = "mt4_s3c_build_manifest.json"
ELF_RECORD_MEMBER = "mt4_s3c_elf_qualification_record.json"
OBSERVATION_MEMBER = "mt4_s3c_raw_observation_record.json"
RECEIPT_MEMBER = "mt4_s3c_qualification_receipt.json"
OBSERVE_INSTANCE_MEMBER = "mt4_s3c_observe_instances.json"
ADJUDICATE_INSTANCE_MEMBER = "mt4_s3c_adjudicate_instances.json"

# EXPECTED MEMBER COUNTS, exact per artifact class (V9 27.2).  Not "at most".
EXPECTED_MEMBERS = {
    CANDIDATE_ARTIFACT: (WORKER_BINARY_MEMBER, BUILD_MANIFEST_MEMBER),
    ELF_ARTIFACT: (ELF_RECORD_MEMBER,),
    OBSERVATION_ARTIFACT: (OBSERVATION_MEMBER, OBSERVE_INSTANCE_MEMBER),
    RECEIPT_ARTIFACT: (RECEIPT_MEMBER, ADJUDICATE_INSTANCE_MEMBER),
}

EXACT_CASE_COUNT = 25

# =================================================================================================
# TRUSTED_STAGE_C_SELF_ANCHORED_AUTHORITY_V1 (the Class-C P1-2 repair).
#
# THE DEFECT THIS CLOSES.  Stage C previously read the canonical internal policy id, the canonical
# policy digest, the canonical cBPF instruction count and the canonical cBPF digest OUT OF THE
# OBSERVATION RECORD, and then "verified" the captured program against those same values.  That is
# circular: an unprivileged run that reseals A3 and A4 together, declaring its own canonical values
# and capturing a program that matches them, satisfies every equality.  The check proved internal
# consistency of the claim, not conformance to the approved policy.
#
# THE REPAIR.  Every expected value below is reconstructed HERE, from constants frozen in this file,
# and this file's bytes are pinned by APPROVED_S3C_TRUSTED_GATE_SHA256 on the default-branch trusted
# workflow -- the one surface a pull request cannot reach.  A3 and A4 are compared AGAINST the
# reconstruction and never contribute to it.
#
# WHY THE UAPI VALUES ARE LITERAL HERE, AND WHY THAT IS NOT A WEAKENING.  The qualification jobs
# derive these values from the pinned kernel headers via the probe, deliberately, so that a header
# drift is DETECTED rather than assumed away.  Stage C needs the opposite property: an authority the
# measured environment cannot influence.  The two legs meet in the middle -- the build leg proves
# the compiled source agrees with the probe, and this leg proves the probe-derived result agrees
# with the approved x86_64 ABI.  A platform whose values differ is not the approved platform, and
# the correct outcome is a CLOSED FAILURE that returns to architecture, never a widened verifier.
# =================================================================================================

INTERNAL_POLICY_SCHEMA = "mt4-s3c-internal-containment-policy.v1"
INTERNAL_POLICY_DIGEST_DOMAIN = b"mt4-s3c-internal-containment-policy.v1\x00"
CANONICAL_INTERNAL_POLICY_ID = "MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64"

AUDIT_ARCHITECTURE_NAME = "AUDIT_ARCH_X86_64"
ALTERNATE_ABI_POLICY = "REJECT_ALL_NON_MATCHING_AUDIT_ARCH_KILL_PROCESS"
X32_POLICY = "REJECT_X32_MARKER_UNMASKED_UNSTRIPPED_KILL_PROCESS"
DEFAULT_ACTION = "SECCOMP_RET_KILL_PROCESS"
SECCOMP_OPERATION = "SECCOMP_SET_MODE_FILTER"
UNUSED_ARGUMENT_POLICY = "UNUSED_ARGUMENT_WORDS_MUST_BE_ZERO"

ARG_WORDS = 6
FD_REQUEST = 3
FD_RESPONSE = 4
REQUEST_FRAME_BYTES = 184
RESPONSE_FRAME_BYTES = 8

# The approved x86_64 Linux ABI values.  Frozen literals on the trusted surface.
TRUSTED_AUDIT_ARCH_X86_64 = 0xC000003E
TRUSTED_X32_SYSCALL_BIT = 0x40000000
TRUSTED_SECCOMP_RET_ALLOW = 0x7FFF0000
TRUSTED_SECCOMP_RET_KILL_PROCESS = 0x80000000
TRUSTED_OFFSET_NR = 0
TRUSTED_OFFSET_ARCH = 4
TRUSTED_ARG_LO_OFFSETS = (16, 24, 32, 40, 48, 56)
TRUSTED_ARG_HI_OFFSETS = (20, 28, 36, 44, 52, 60)
TRUSTED_SYSCALL_NR_READ = 0
TRUSTED_SYSCALL_NR_WRITE = 1
TRUSTED_SYSCALL_NR_EXIT_GROUP = 231
TRUSTED_OPCODE_LD_W_ABS = 0x20
TRUSTED_OPCODE_JEQ_K = 0x15
TRUSTED_OPCODE_JGE_K = 0x35
TRUSTED_OPCODE_JGT_K = 0x25
TRUSTED_OPCODE_JA = 0x05
TRUSTED_OPCODE_RET_K = 0x06

CAT_EXACT = "EXACT"
CAT_RANGE = "RANGE"
CAT_POINTER = "UNCONSTRAINED_POINTER"
CAT_SCALAR = "UNCONSTRAINED_SCALAR"
CAT_ZERO = "ZERO_REQUIRED"

# The internal containment inventory: exactly three syscalls, in ascending dispatch order.  Each
# rule classifies all six argument words, which is what makes the emitted layout deterministic.
_TRUSTED_INTERNAL_INVENTORY = (
    (
        "read",
        TRUSTED_SYSCALL_NR_READ,
        "CANDIDATE_VERIFY",
        (
            (
                (CAT_EXACT, FD_REQUEST, 0),
                (CAT_POINTER, 0, 0),
                (CAT_RANGE, 1, REQUEST_FRAME_BYTES),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
            ),
        ),
    ),
    (
        "write",
        TRUSTED_SYSCALL_NR_WRITE,
        "CANDIDATE_RESPONSE",
        (
            (
                (CAT_EXACT, FD_RESPONSE, 0),
                (CAT_POINTER, 0, 0),
                (CAT_RANGE, 1, RESPONSE_FRAME_BYTES),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
            ),
        ),
    ),
    (
        "exit_group",
        TRUSTED_SYSCALL_NR_EXIT_GROUP,
        "PROCESS_EXIT",
        (
            (
                (CAT_SCALAR, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
                (CAT_ZERO, 0, 0),
            ),
        ),
    ),
)

OUTER_POLICY_SCHEMA = "mt4-s3c-outer-containment-policy.v1"
OUTER_POLICY_DIGEST_DOMAIN = b"mt4-s3c-outer-containment-policy.v1\x00"
CANONICAL_OUTER_POLICY_ID = "MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"

TRUSTED_SYSCALL_NR_CLOSE = 3
TRUSTED_SYSCALL_NR_EXECVE = 59
TRUSTED_SYSCALL_NR_PRCTL = 157
TRUSTED_SYSCALL_NR_SECCOMP = 317
TRUSTED_SYSCALL_NR_CLOSE_RANGE = 436

TRUSTED_PR_SET_DUMPABLE = 4
TRUSTED_PR_SET_NO_NEW_PRIVS = 38
TRUSTED_SECCOMP_SET_MODE_FILTER = 1
CLOSE_RANGE_FIRST_FD = 5
CLOSE_RANGE_MAX_FD = 4294967295
CLOSE_LEGAL_FDS = (0, 1, 2)


def _rule(*classified):
    """Build one six-word rule, defaulting every unnamed index to ZERO_REQUIRED."""
    spec = [(CAT_ZERO, 0, 0)] * ARG_WORDS
    for index, category, low, high in classified:
        spec[index] = (category, low, high)
    return tuple(spec)


# The OUTER containment inventory: eight syscalls in the frozen ascending dispatch order, with the
# ordered alternative tuples that close/prctl require.  Reconstructed here so that A3's and A4's
# outer policy and cBPF claims are compared against Stage C's own derivation rather than adopted.
_TRUSTED_OUTER_INVENTORY = (
    (
        "read",
        TRUSTED_SYSCALL_NR_READ,
        "CANDIDATE_VERIFY",
        ((_rule((0, CAT_EXACT, FD_REQUEST, 0), (1, CAT_POINTER, 0, 0), (2, CAT_RANGE, 1, REQUEST_FRAME_BYTES))),),
    ),
    (
        "write",
        TRUSTED_SYSCALL_NR_WRITE,
        "CANDIDATE_RESPONSE",
        ((_rule((0, CAT_EXACT, FD_RESPONSE, 0), (1, CAT_POINTER, 0, 0), (2, CAT_RANGE, 1, RESPONSE_FRAME_BYTES))),),
    ),
    (
        "close",
        TRUSTED_SYSCALL_NR_CLOSE,
        "CANDIDATE_BOOTSTRAP",
        tuple(_rule((0, CAT_EXACT, descriptor, 0)) for descriptor in CLOSE_LEGAL_FDS),
    ),
    (
        "execve",
        TRUSTED_SYSCALL_NR_EXECVE,
        "LAUNCH_TRANSITION",
        ((_rule((0, CAT_POINTER, 0, 0), (1, CAT_POINTER, 0, 0), (2, CAT_POINTER, 0, 0))),),
    ),
    (
        "prctl",
        TRUSTED_SYSCALL_NR_PRCTL,
        "CANDIDATE_BOOTSTRAP",
        (
            _rule((0, CAT_EXACT, TRUSTED_PR_SET_DUMPABLE, 0), (1, CAT_EXACT, 0, 0)),
            _rule((0, CAT_EXACT, TRUSTED_PR_SET_NO_NEW_PRIVS, 0), (1, CAT_EXACT, 1, 0)),
        ),
    ),
    (
        "exit_group",
        TRUSTED_SYSCALL_NR_EXIT_GROUP,
        "PROCESS_EXIT",
        ((_rule((0, CAT_SCALAR, 0, 0))),),
    ),
    (
        "seccomp",
        TRUSTED_SYSCALL_NR_SECCOMP,
        "CANDIDATE_BOOTSTRAP",
        (
            (
                _rule(
                    (0, CAT_EXACT, TRUSTED_SECCOMP_SET_MODE_FILTER, 0),
                    (1, CAT_EXACT, 0, 0),
                    (2, CAT_POINTER, 0, 0),
                )
            ),
        ),
    ),
    (
        "close_range",
        TRUSTED_SYSCALL_NR_CLOSE_RANGE,
        "CANDIDATE_BOOTSTRAP",
        (
            (
                _rule(
                    (0, CAT_EXACT, CLOSE_RANGE_FIRST_FD, 0),
                    (1, CAT_EXACT, CLOSE_RANGE_MAX_FD, 0),
                    (2, CAT_EXACT, 0, 0),
                )
            ),
        ),
    ),
)

CANONICAL_OUTER_CBPF_INSTRUCTION_COUNT = 400
CANONICAL_INTERNAL_CBPF_INSTRUCTION_COUNT = 113

# The reconstruction below must reproduce these exactly.  They are asserted at import time, so a
# drift in the emitter or in any frozen constant is a hard failure of the gate itself rather than a
# silently different expectation.
EXPECTED_INTERNAL_POLICY_SHA256 = "ba8b6ca197472a8dada2d703d879bb104ebc73089de621f8695daf52795154d4"
EXPECTED_INTERNAL_CBPF_SHA256 = "dd044cda4588d641f6c57a27a64fb8d09eaf15ac7eb86622c047a2b4b4bf9d6d"
EXPECTED_INTERNAL_PROGRAM_BYTES_SHA256 = "129a4ee7f0265f0d150e7466b298b728d6572f73206fc0fc59f5f1459ed26cb6"

EXPECTED_OUTER_POLICY_SHA256 = "2b8a65d835debfee798e0cef09369509d84fca01fff8e821494b7d1582efbdd3"
EXPECTED_OUTER_GOVERNED_SHA256 = "e65c5e5b8a03a60aea092b745021d87c974234b84329c160b2f9001db492adcb"
EXPECTED_OUTER_CBPF_SHA256 = "630cfe5b3b90d582b0d43493cb7774d978bb75a276f246324c12483f97c5e6cd"

INTERNAL_FPROG_SYMBOL = "mt4_s3c_internal_filter_fprog"
INTERNAL_PROGRAM_SYMBOL = "mt4_s3c_internal_filter_program"
INTERNAL_FPROG_SIZE_BYTES = 16
INTERNAL_PROGRAM_SIZE_BYTES = CANONICAL_INTERNAL_CBPF_INSTRUCTION_COUNT * 8

# ELF segment flag values.  A filter object must live in a NON-WRITABLE, file-backed mapping.
PF_X = 0x1
PF_W = 0x2
PF_R = 0x4


def _pack_instruction(code, k, jt, jf):
    return (
        (code & 0xFFFF).to_bytes(2, "little") + bytes((jt & 0xFF, jf & 0xFF)) + (k & 0xFFFFFFFF).to_bytes(4, "little")
    )


def _emit_argument_check(out, target, index, category, low, high):
    """One argument-word check.  The HIGH word is always compared before the low word."""
    if category in (CAT_POINTER, CAT_SCALAR):
        return
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_ARG_HI_OFFSETS[index], 0, 0))
    out.append((TRUSTED_OPCODE_JEQ_K, 0, 1, 0))
    out.append(("JA", target))
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_ARG_LO_OFFSETS[index], 0, 0))
    if category == CAT_RANGE:
        out.append((TRUSTED_OPCODE_JGE_K, low, 1, 0))
        out.append(("JA", target))
        out.append((TRUSTED_OPCODE_JGT_K, high, 0, 1))
        out.append(("JA", target))
    else:
        out.append((TRUSTED_OPCODE_JEQ_K, 0 if category == CAT_ZERO else low, 1, 0))
        out.append(("JA", target))


def _derive_program(inventory):
    """Reconstruct one canonical classic-BPF program from the frozen constants alone."""
    out = []
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_OFFSET_ARCH, 0, 0))
    out.append((TRUSTED_OPCODE_JEQ_K, TRUSTED_AUDIT_ARCH_X86_64, 1, 0))
    out.append(("JA", "KILL"))
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_OFFSET_NR, 0, 0))
    out.append((TRUSTED_OPCODE_JGE_K, TRUSTED_X32_SYSCALL_BIT, 0, 1))
    out.append(("JA", "KILL"))

    for position, (name, number, _reason, rules) in enumerate(inventory):
        last_entry = position + 1 == len(inventory)
        next_entry = "KILL" if last_entry else (inventory[position + 1][0], "ENTRY")
        out.append((name, "ENTRY"))
        out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_OFFSET_NR, 0, 0))
        out.append((TRUSTED_OPCODE_JEQ_K, number, 1, 0))
        out.append(("JA", next_entry))
        for rule_position, rule in enumerate(rules):
            last_rule = rule_position + 1 == len(rules)
            target = "KILL" if last_rule else (name, rule_position + 1)
            out.append((name, rule_position))
            for index in range(ARG_WORDS):
                category, low, high = rule[index]
                _emit_argument_check(out, target, index, category, low, high)
            out.append((TRUSTED_OPCODE_RET_K, TRUSTED_SECCOMP_RET_ALLOW, 0, 0))

    out.append("KILL")
    out.append((TRUSTED_OPCODE_RET_K, TRUSTED_SECCOMP_RET_KILL_PROCESS, 0, 0))

    labels = {}
    index = 0
    for item in out:
        if isinstance(item, tuple) and len(item) == 4:
            index += 1
        elif isinstance(item, tuple) and len(item) == 2 and item[0] == "JA":
            index += 1
        else:
            labels[item] = index
    total = index

    program = []
    index = 0
    for item in out:
        if isinstance(item, tuple) and len(item) == 4:
            program.append(_pack_instruction(item[0], item[1], item[2], item[3]))
            index += 1
        elif isinstance(item, tuple) and len(item) == 2 and item[0] == "JA":
            distance = labels[item[1]] - index - 1
            if distance < 0:
                fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "backward jump")
            program.append(_pack_instruction(TRUSTED_OPCODE_JA, distance, 0, 0))
            index += 1
    if len(program) != total:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "instruction count")
    return b"".join(program)


def _argument_rule_to_canonical(rule):
    exact = {}
    pointers = []
    scalars = []
    zeros = []
    ranges = {}
    for index in range(ARG_WORDS):
        category, low, high = rule[index]
        if category == CAT_EXACT:
            exact[str(index)] = int(low)
        elif category == CAT_RANGE:
            ranges[str(index)] = {"min_u64": int(low), "max_u64": int(high)}
        elif category == CAT_POINTER:
            pointers.append(index)
        elif category == CAT_SCALAR:
            scalars.append(index)
        else:
            zeros.append(index)
    kind = "ARG_EXACT_AND_ARG_RANGE_WITH_ZERO_TAIL" if ranges else "ARGS_EXACT_WITH_ZERO_TAIL"
    return {
        "kind": kind,
        "exact_u64": exact,
        "range_u64": ranges,
        "unconstrained_pointer_indices": pointers,
        "unconstrained_scalar_indices": scalars,
        "zero_indices": zeros,
    }


def _derive_semantic_preimage(inventory, schema, policy_domain):
    """Reconstruct one canonical semantic policy document -- the POLICY BYTES, not just a digest."""
    entries = []
    for name, number, reason, rules in inventory:
        entries.append(
            {
                "name": name,
                "nr_u32": number,
                "reason_class": reason,
                "argument_rule_count": len(rules),
                "argument_rules": [_argument_rule_to_canonical(rule) for rule in rules],
            }
        )
    entries.sort(key=lambda entry: entry["nr_u32"])
    return {
        "schema": schema,
        "policy_domain": policy_domain,
        "audit_architecture_name": AUDIT_ARCHITECTURE_NAME,
        "audit_architecture_value_u32": TRUSTED_AUDIT_ARCH_X86_64,
        "alternate_abi_policy": ALTERNATE_ABI_POLICY,
        "x32_policy": X32_POLICY,
        "x32_syscall_bit_u32": TRUSTED_X32_SYSCALL_BIT,
        "default_action": DEFAULT_ACTION,
        "seccomp_operation": SECCOMP_OPERATION,
        "seccomp_flags_u32": 0,
        "seccomp_flags_names": [],
        "unused_argument_policy": UNUSED_ARGUMENT_POLICY,
        "reason_classes": sorted({entry["reason_class"] for entry in entries}),
        "syscall_inventory_count": len(entries),
        "syscall_inventory": entries,
        "program_representation_version": PROGRAM_REPRESENTATION_VERSION,
    }


def _stage_c_canonical_policy(inventory, schema, digest_domain, policy_domain, expected_count):
    """One self-derived canonical policy: semantic bytes, digests, program bytes and program digest.

    The GOVERNED digest adds the emitted program identity to the SEMANTIC document, exactly as the
    bundled qualifier's build_policy_record does, and the two must differ -- a policy whose semantic
    and governed digests collided would have lost the separation that lets a program change be
    detected independently of a rule change.
    """
    semantic = _derive_semantic_preimage(inventory, schema, policy_domain)
    semantic_bytes = canonical_json(semantic)
    program_bytes = _derive_program(inventory)
    instruction_count = len(program_bytes) // 8
    if instruction_count != expected_count:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "instruction count")
    governed = dict(semantic)
    governed["emitted_cbpf_instruction_count"] = instruction_count
    governed["emitted_cbpf_sha256"] = cbpf_digest(program_bytes)
    semantic_digest = hashlib.sha256(digest_domain + semantic_bytes).hexdigest()
    governed_digest = hashlib.sha256(digest_domain + canonical_json(governed)).hexdigest()
    if semantic_digest == governed_digest:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "digest separation lost")
    return {
        "policy_id": policy_domain,
        "semantic_bytes": semantic_bytes,
        "policy_sha256": semantic_digest,
        "governed_sha256": governed_digest,
        "cbpf_instruction_count": instruction_count,
        "cbpf_program_bytes": program_bytes,
        "cbpf_sha256": governed["emitted_cbpf_sha256"],
        "program_bytes_sha256": hashlib.sha256(program_bytes).hexdigest(),
    }


def stage_c_canonical_internal_policy():
    """The Stage-C canonical internal policy: bytes, digests and program, all self-derived."""
    canonical = _stage_c_canonical_policy(
        _TRUSTED_INTERNAL_INVENTORY,
        INTERNAL_POLICY_SCHEMA,
        INTERNAL_POLICY_DIGEST_DOMAIN,
        CANONICAL_INTERNAL_POLICY_ID,
        CANONICAL_INTERNAL_CBPF_INSTRUCTION_COUNT,
    )
    # Drift in any frozen constant or in the emitter is a failure of THIS file, not of the candidate.
    if canonical["policy_sha256"] != EXPECTED_INTERNAL_POLICY_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "policy digest")
    if canonical["cbpf_sha256"] != EXPECTED_INTERNAL_CBPF_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "cbpf digest")
    if canonical["program_bytes_sha256"] != EXPECTED_INTERNAL_PROGRAM_BYTES_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "program bytes digest")
    return canonical


def stage_c_canonical_outer_policy():
    """The Stage-C canonical OUTER policy (repair 1C).

    A3 and A4 both carry an outer containment policy digest.  Comparing them to each other proves
    only that the unprivileged job agreed with itself, which is the same circularity the internal
    policy repair closed; the outer policy is therefore reconstructed here too.
    """
    canonical = _stage_c_canonical_policy(
        _TRUSTED_OUTER_INVENTORY,
        OUTER_POLICY_SCHEMA,
        OUTER_POLICY_DIGEST_DOMAIN,
        CANONICAL_OUTER_POLICY_ID,
        CANONICAL_OUTER_CBPF_INSTRUCTION_COUNT,
    )
    if canonical["policy_sha256"] != EXPECTED_OUTER_POLICY_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "outer policy digest")
    if canonical["governed_sha256"] != EXPECTED_OUTER_GOVERNED_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "outer governed digest")
    if canonical["cbpf_sha256"] != EXPECTED_OUTER_CBPF_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "outer cbpf digest")
    return canonical


# =================================================================================================
# THE CANONICAL 25-CASE INVENTORY, RECONSTRUCTED ON THE TRUSTED SURFACE (the Class-C P1-2C repair).
#
# The observation and the receipt both carry an observation_case_set_digest.  Comparing them to each
# other proves only that the unprivileged job was self-consistent.  The literal table below is the
# THIRD authority: Stage C rebuilds the exact canonical preimage from it and recomputes the digest,
# and A3 and A4 must both equal that recomputation.  A permanent test proves this table is exactly
# the inventory the adjudicator DERIVES from its executable rules, so the two can never diverge
# silently; here it is a literal precisely so that no candidate input can reshape it.
# =================================================================================================

CASE_SET_SCHEMA = "mt4-s3c-observation-case-set.v2"
CASE_SET_DIGEST_DOMAIN = b"mt4-s3c-observation-case-set.v2\x00"

TRUSTED_CASE_INVENTORY = (
    (1, "C01_POSITIVE_EXACT_FIXTURE", "CRYPTO_POSITIVE", "RT_VERIFIER_STATUS_FRAME", 1, 0, 0, "V5_INHERITED"),
    (2, "C02_DETERMINISM_EXACT_REPEAT", "CRYPTO_POSITIVE", "RT_VERIFIER_STATUS_FRAME", 1, 0, 0, "V5_INHERITED"),
    (3, "C03_PK_BAD_ENCODING", "CRYPTO_NEGATIVE_PUBLIC_KEY", "RT_VERIFIER_STATUS_FRAME", 1, 3, 0, "V5_INHERITED"),
    (4, "C04_PK_NON_CANONICAL", "CRYPTO_NEGATIVE_PUBLIC_KEY", "RT_VERIFIER_STATUS_FRAME", 1, 4, 0, "V5_INHERITED"),
    (5, "C05_PK_INFINITY", "CRYPTO_NEGATIVE_PUBLIC_KEY", "RT_VERIFIER_STATUS_FRAME", 1, 5, 0, "V5_INHERITED"),
    (6, "C06_PK_NOT_IN_GROUP", "CRYPTO_NEGATIVE_PUBLIC_KEY", "RT_VERIFIER_STATUS_FRAME", 1, 6, 0, "V5_INHERITED"),
    (7, "C07_SIG_BAD_ENCODING", "CRYPTO_NEGATIVE_SIGNATURE", "RT_VERIFIER_STATUS_FRAME", 1, 7, 0, "V5_INHERITED"),
    (8, "C08_SIG_NON_CANONICAL", "CRYPTO_NEGATIVE_SIGNATURE", "RT_VERIFIER_STATUS_FRAME", 1, 8, 0, "V5_INHERITED"),
    (9, "C09_SIG_INFINITY", "CRYPTO_NEGATIVE_SIGNATURE", "RT_VERIFIER_STATUS_FRAME", 1, 9, 0, "V5_INHERITED"),
    (10, "C10_SIG_NOT_IN_GROUP", "CRYPTO_NEGATIVE_SIGNATURE", "RT_VERIFIER_STATUS_FRAME", 1, 10, 0, "V5_INHERITED"),
    (
        11,
        "C11_VERIFY_FAILED_WRONG_DIGEST",
        "CRYPTO_NEGATIVE_VERIFY",
        "RT_VERIFIER_STATUS_FRAME",
        1,
        11,
        0,
        "V5_INHERITED",
    ),
    (
        12,
        "C12_VERIFY_FAILED_WRONG_PUBLIC_KEY",
        "CRYPTO_NEGATIVE_PUBLIC_KEY",
        "RT_VERIFIER_STATUS_FRAME",
        1,
        11,
        0,
        "V5_INHERITED",
    ),
    (13, "C13_WRONG_MAGIC", "REQUEST_PROTOCOL_STIMULUS", "RT_REQUEST_PROTOCOL_ERROR_FRAME", 2, 1, 0, "V5_INHERITED"),
    (14, "C14_WRONG_VERSION", "REQUEST_PROTOCOL_STIMULUS", "RT_REQUEST_PROTOCOL_ERROR_FRAME", 2, 2, 0, "V5_INHERITED"),
    (15, "C15_WRONG_OPCODE", "REQUEST_PROTOCOL_STIMULUS", "RT_REQUEST_PROTOCOL_ERROR_FRAME", 2, 3, 0, "V5_INHERITED"),
    (
        16,
        "C16_RESERVED_NONZERO",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        4,
        0,
        "V5_INHERITED",
    ),
    (
        17,
        "C17_SHORT_FRAME_EOF_EMPTY",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        5,
        0,
        "V5_INHERITED",
    ),
    (
        18,
        "C18_SHORT_FRAME_EOF_PARTIAL_HEADER",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        5,
        0,
        "V5_INHERITED",
    ),
    (
        19,
        "C19_SHORT_FRAME_EOF_ONE_SHORT",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        5,
        0,
        "V5_INHERITED",
    ),
    (
        20,
        "C20_TRAILING_INPUT_ONE_BYTE",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        6,
        0,
        "V5_INHERITED",
    ),
    (
        21,
        "C21_TRAILING_INPUT_SECOND_FRAME",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        6,
        0,
        "V5_INHERITED",
    ),
    (
        22,
        "C22_ORDER_TRAILING_BEFORE_MAGIC",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        6,
        0,
        "V9_STRENGTHENING_CASE",
    ),
    (
        23,
        "C23_ORDER_SHORT_BEFORE_MAGIC",
        "REQUEST_PROTOCOL_STIMULUS",
        "RT_REQUEST_PROTOCOL_ERROR_FRAME",
        2,
        5,
        0,
        "V9_STRENGTHENING_CASE",
    ),
    (24, "C24_CRASH_MID_REQUEST", "PROCESS_STIMULUS", "RT_PROCESS_TERMINATED_BY_SIGNAL", 0, -1, -1, "V5_INHERITED"),
    (25, "C25_TIMEOUT_WRITER_WITHHOLDS", "PROCESS_STIMULUS", "RT_DEADLINE_EXPIRED", 0, -1, -1, "V5_INHERITED"),
)

TRUSTED_CASE_IDS = tuple(row[1] for row in TRUSTED_CASE_INVENTORY)

EXPECTED_CASE_SET_DIGEST = "b760154fdfff540e6d66b97b45f200d6a4f132583a462da8a962b0bd79c3e1de"


def stage_c_case_set_digest():
    """Rebuild the canonical case-set preimage from the trusted table and digest it."""
    if len(TRUSTED_CASE_INVENTORY) != EXACT_CASE_COUNT:
        fail("STAGE_C_CANONICAL_CASE_SET_DERIVATION_FAILED", "case count")
    if len(set(TRUSTED_CASE_IDS)) != EXACT_CASE_COUNT:
        fail("STAGE_C_CANONICAL_CASE_SET_DERIVATION_FAILED", "duplicate case id")
    preimage = {
        "schema": CASE_SET_SCHEMA,
        "case_count": EXACT_CASE_COUNT,
        "cases": [
            {
                "case_index": row[0],
                "case_id": row[1],
                "stimulus_class": row[2],
                "expected_result_type": row[3],
                "expected_result_class": row[4],
                "expected_result_code": row[5],
                "expected_exit_status": row[6],
                "case_origin": row[7],
            }
            for row in TRUSTED_CASE_INVENTORY
        ],
        "case_id_order": list(TRUSTED_CASE_IDS),
    }
    digest = domain_digest(CASE_SET_DIGEST_DOMAIN, preimage)
    if digest != EXPECTED_CASE_SET_DIGEST:
        fail("STAGE_C_CANONICAL_CASE_SET_DERIVATION_FAILED", "digest")
    return digest


ELF_RECORD_SCHEMA = "mt4-s3c-elf-qualification-record.v1"
ELF_RECORD_DIGEST_DOMAIN = b"mt4-s3c-elf-qualification-record.v1\x00"

# Section header types and flags Stage C reasons about.  Frozen here so the trusted surface does not
# have to believe A2's own description of what a section IS.
SHT_NULL = 0
SHT_NOBITS = 8
SHF_ALLOC = 0x2
SHN_LORESERVE = 0xFF00

# The sock_fprog object layout on x86_64: u16 len, six padding bytes, u64 filter pointer.
FPROG_LAYOUT_BYTES = 16
FPROG_POINTER_OFFSET = 8


# =================================================================================================
# THE TRUSTED WORKER-ELF RECONSTRUCTION (repair 1B).
#
# THE DEFECT THIS CLOSES.  Stage C used to hash the A2 dictionary and then check that the
# coordinates A2 CHOSE were internally consistent with each other.  That is self-anchoring: a
# truncated A2, or one that relocates an object and reseals itself, is internally perfect and was
# accepted.  A2 is a CLAIM about a binary; the binary is the fact.
#
# Stage C therefore parses the authenticated candidate bytes itself -- the same bytes whose digest
# the manifest, the ELF record, the observation and the receipt are all bound to -- and derives the
# governed coordinates from them.  A2 is then compared, field for field, against that
# reconstruction.  A truncated A2 fails on the exact-schema check below; a relocated A2 fails
# because the worker bytes do not put the object where A2 says.
#
# This parser is DELIBERATELY MINIMAL and independent: it reads only what the governed decision
# needs, bounds every read, and shares no code with the unprivileged qualifier.
# =================================================================================================

ELF_MAGIC = bytes((0x7F, 0x45, 0x4C, 0x46))
ELFCLASS64 = 2
ELFDATA2LSB = 1
EV_CURRENT = 1
ET_EXEC = 2
EM_X86_64 = 62
PT_LOAD = 1
SHT_STRTAB = 3
SHT_SYMTAB = 2
STB_GLOBAL = 1
STV_HIDDEN = 2
STT_OBJECT = 1
# =================================================================================================
# THE FROZEN PHDR / SECTION / RESOURCE POLICY (repair 1).
#
# THE DEFECT THIS CLOSES.  Stage C parsed the candidate's headers but then compared only a handful
# of A2's claims against them, so a coherently resealed A2 could carry a forbidden PT_DYNAMIC or a
# PT_LOAD claiming 32 MiB of mapped memory and still be accepted: the fields that would have caught
# it were simply never compared.  Every decision-bearing header field is now reconstructed from the
# authenticated bytes and required to match, and the policy below is applied to the RECONSTRUCTION
# rather than to anything A2 asserts.
# =================================================================================================

PT_INTERP = 3
PT_DYNAMIC = 2
PT_SHLIB = 5
PT_TLS = 7
PT_GNU_STACK = 0x6474E551
PT_PHDR = 6
PT_NOTE = 4

# A dynamic surface of any kind contradicts the static non-PIE contract outright.
ALWAYS_FORBIDDEN_PHDR_TYPES = (PT_INTERP, PT_DYNAMIC, PT_SHLIB, PT_TLS)

# The exact expected inventory, identical to the reviewed qualifier's and to the literal pinned in
# both workflows: type, flags and alignment for every segment the image may carry.
EXPECTED_PHDR_INVENTORY = (
    (PT_LOAD, 5, 0x1000),
    (PT_LOAD, 6, 0x1000),
    (PT_GNU_STACK, 6, 0x10),
)

PAGE_SIZE_REQUIRED = 4096
MAX_PT_LOAD_EFFECTIVE_BYTES = 16 * 1024 * 1024
MAX_AGGREGATE_EFFECTIVE_BYTES = 32 * 1024 * 1024
STACK_RESERVE_BYTES = 8 * 1024 * 1024
GOVERNED_HEADROOM_BYTES = 24 * 1024 * 1024
RLIMIT_AS_BYTES = MAX_AGGREGATE_EFFECTIVE_BYTES + STACK_RESERVE_BYTES + GOVERNED_HEADROOM_BYTES

MAX_PHNUM = 64
MAX_SECTION_COUNT = 128
MAX_SYMBOL_COUNT = 65536
SHN_UNDEF = 0

BLST_PLATFORM_CAP_SYMBOL = "__blst_platform_cap"
BLST_PLATFORM_CAP_SIZE_BYTES = 4

# The OUTER governed filter objects.  They live in the same linked image as the internal ones, so
# Stage C can and does reconstruct them from the candidate bytes rather than trusting an address.
OUTER_FPROG_SYMBOL = "mt4_s3c_outer_filter_fprog"
OUTER_PROGRAM_SYMBOL = "mt4_s3c_outer_filter_program"
OUTER_FPROG_SIZE_BYTES = 16
OUTER_PROGRAM_SIZE_BYTES = CANONICAL_OUTER_CBPF_INSTRUCTION_COUNT * 8

# REPAIR 1D: the EXACT identity every governed filter symbol must carry.  The previous code read
# st_info and st_other and then only enforced them for the capability object, so a filter descriptor
# could have been weak, local, internal or the wrong symbol type and still bind.  All four filter
# objects are declared with hidden visibility in bundle entry 10 and are non-static, so the frozen
# contract is the same one the capability object already carries.
GOVERNED_SYMBOL_IDENTITY = {
    "binding": STB_GLOBAL,
    "visibility": STV_HIDDEN,
    "symbol_type": STT_OBJECT,
}


def _bounded(data, offset, length, marker):
    if offset < 0 or length < 0 or offset + length > len(data):
        fail(marker, "read beyond the image")
    return bytes(data[offset : offset + length])


def _u16(data, offset, marker):
    return int.from_bytes(_bounded(data, offset, 2, marker), "little")


def _u32(data, offset, marker):
    return int.from_bytes(_bounded(data, offset, 4, marker), "little")


def _u64(data, offset, marker):
    return int.from_bytes(_bounded(data, offset, 8, marker), "little")


def _cstring(blob, offset, marker):
    if offset >= len(blob):
        fail(marker, "string offset beyond the table")
    end = blob.find(b"\x00", offset)
    if end < 0:
        fail(marker, "unterminated string")
    try:
        return blob[offset:end].decode("ascii")
    except UnicodeDecodeError:
        fail(marker, "non-ascii string")
        return ""


def _stage_c_parse_worker(data):
    """Parse exactly what the governed decision needs, with every read bounded."""
    marker = "TRUSTED_ELF_RECONSTRUCTION_FAILED"
    if len(data) < 64 or len(data) > MAX_WORKER_BINARY_BYTES:
        fail(marker, "image size")
    if _bounded(data, 0, 4, marker) != ELF_MAGIC:
        fail(marker, "magic")
    if data[4] != ELFCLASS64 or data[5] != ELFDATA2LSB or data[6] != EV_CURRENT:
        fail(marker, "identification")
    if _u16(data, 16, marker) != ET_EXEC:
        fail(marker, "type")
    if _u16(data, 18, marker) != EM_X86_64:
        fail(marker, "machine")

    e_entry = _u64(data, 24, marker)
    e_phoff = _u64(data, 32, marker)
    e_shoff = _u64(data, 40, marker)
    e_phentsize = _u16(data, 54, marker)
    e_phnum = _u16(data, 56, marker)
    e_shentsize = _u16(data, 58, marker)
    e_shnum = _u16(data, 60, marker)
    e_shstrndx = _u16(data, 62, marker)
    if e_phentsize != 56 or e_shentsize != 64:
        fail(marker, "table geometry")
    if e_phnum == 0 or e_phnum > MAX_PHNUM or e_shnum == 0 or e_shnum > MAX_SECTION_COUNT:
        fail(marker, "table count")
    if e_phoff + e_phnum * e_phentsize > len(data) or e_shoff + e_shnum * e_shentsize > len(data):
        fail(marker, "table extent")
    if e_shstrndx >= e_shnum:
        fail(marker, "shstrndx")

    segments = []
    for index in range(e_phnum):
        base = e_phoff + index * e_phentsize
        segments.append(
            {
                "index": index,
                "p_type": _u32(data, base + 0, marker),
                "p_flags": _u32(data, base + 4, marker),
                "p_offset": _u64(data, base + 8, marker),
                "p_vaddr": _u64(data, base + 16, marker),
                "p_filesz": _u64(data, base + 32, marker),
                "p_memsz": _u64(data, base + 40, marker),
                "p_align": _u64(data, base + 48, marker),
            }
        )

    sections = []
    for index in range(e_shnum):
        base = e_shoff + index * e_shentsize
        sections.append(
            {
                "index": index,
                "sh_name": _u32(data, base + 0, marker),
                "sh_type": _u32(data, base + 4, marker),
                "sh_flags": _u64(data, base + 8, marker),
                "sh_addr": _u64(data, base + 16, marker),
                "sh_offset": _u64(data, base + 24, marker),
                "sh_size": _u64(data, base + 32, marker),
                "sh_link": _u32(data, base + 40, marker),
                "sh_entsize": _u64(data, base + 56, marker),
                "name": "",
            }
        )

    strings_section = sections[e_shstrndx]
    if strings_section["sh_type"] != SHT_STRTAB:
        fail(marker, "shstrtab type")
    name_blob = _bounded(data, strings_section["sh_offset"], strings_section["sh_size"], marker)
    for section in sections:
        section["name"] = _cstring(name_blob, section["sh_name"], marker)

    # REPAIR 1B and 1E: the FULL program-header policy, applied to the reconstruction.
    inventory = []
    aggregate_effective = 0
    for segment in segments:
        if segment["p_type"] in ALWAYS_FORBIDDEN_PHDR_TYPES:
            fail("TRUSTED_ELF_FORBIDDEN_SEGMENT", str(segment["p_type"]))
        if segment["p_filesz"] > segment["p_memsz"]:
            fail(marker, "segment file size exceeds its memory size")
        if segment["p_offset"] + segment["p_filesz"] > len(data):
            fail(marker, "segment file range escapes the image")
        if segment["p_vaddr"] + segment["p_memsz"] >= 2**64:
            fail(marker, "segment address range overflows")
        if segment["p_type"] == PT_LOAD:
            if segment["p_align"] < PAGE_SIZE_REQUIRED or segment["p_align"] & (segment["p_align"] - 1):
                fail(marker, "PT_LOAD alignment")
            if (segment["p_vaddr"] - segment["p_offset"]) % segment["p_align"] != 0:
                fail(marker, "PT_LOAD congruence")
            # REPAIR 1D: the effective mapped size, recomputed, against the frozen ceiling.  A
            # producer claiming 32 MiB for one segment cannot pass a 16 MiB bound it never met.
            low = (segment["p_vaddr"] // PAGE_SIZE_REQUIRED) * PAGE_SIZE_REQUIRED
            high = (
                (segment["p_vaddr"] + segment["p_memsz"] + PAGE_SIZE_REQUIRED - 1) // PAGE_SIZE_REQUIRED
            ) * PAGE_SIZE_REQUIRED
            effective = high - low
            if effective > MAX_PT_LOAD_EFFECTIVE_BYTES:
                fail("TRUSTED_ELF_MEMORY_CEILING_EXCEEDED", "segment")
            aggregate_effective += effective
        inventory.append((segment["p_type"], segment["p_flags"], segment["p_align"]))
    if aggregate_effective > MAX_AGGREGATE_EFFECTIVE_BYTES:
        fail("TRUSTED_ELF_MEMORY_CEILING_EXCEEDED", "aggregate")
    # EXACT multiset equality: a missing, extra or duplicated governed segment all fail here.
    if sorted(inventory) != sorted(EXPECTED_PHDR_INVENTORY):
        fail("TRUSTED_ELF_PHDR_INVENTORY_MISMATCH")
    loads = [segment for segment in segments if segment["p_type"] == PT_LOAD]
    if [segment["p_vaddr"] for segment in loads] != sorted(segment["p_vaddr"] for segment in loads):
        fail(marker, "PT_LOAD segments are not in ascending address order")

    symbol_tables = [section for section in sections if section["sh_type"] == SHT_SYMTAB]
    if len(symbol_tables) != 1:
        fail(marker, "symbol table count")
    symbol_table = symbol_tables[0]
    if symbol_table["sh_entsize"] != 24:
        fail(marker, "symbol entry size")
    if symbol_table["sh_link"] >= len(sections):
        fail(marker, "symbol string table link")
    string_table = sections[symbol_table["sh_link"]]
    if string_table["sh_type"] != SHT_STRTAB:
        fail(marker, "symbol string table type")
    symbol_blob = _bounded(data, string_table["sh_offset"], string_table["sh_size"], marker)

    count = symbol_table["sh_size"] // 24
    if count == 0 or count > MAX_SYMBOL_COUNT:
        fail(marker, "symbol count")
    symbols = []
    for index in range(count):
        base = symbol_table["sh_offset"] + index * 24
        name_offset = _u32(data, base + 0, marker)
        symbols.append(
            {
                "index": index,
                "name_offset": name_offset,
                "name": _cstring(symbol_blob, name_offset, marker) if name_offset else "",
                "info": _bounded(data, base + 4, 1, marker)[0],
                "other": _bounded(data, base + 5, 1, marker)[0],
                "shndx": _u16(data, base + 6, marker),
                "value": _u64(data, base + 8, marker),
                "size": _u64(data, base + 16, marker),
            }
        )

    # REPAIR 14: the reserved null entry has ONE canonical shape, and every field of it is checked.
    null_entry = symbols[0]
    for field in ("name_offset", "info", "other", "shndx", "value", "size"):
        if null_entry[field] != 0:
            fail("TRUSTED_ELF_NULL_SYMBOL_INVALID", field)

    # REPAIR 1: the closure runs over EVERY entry, by index, so an anonymous or duplicate-named
    # undefined symbol cannot disappear into a name-keyed collection.
    for symbol in symbols[1:]:
        if symbol["shndx"] == SHN_UNDEF:
            fail("TRUSTED_ELF_UNDEFINED_SYMBOL_PRESENT")

    return {
        "entry": e_entry,
        "aggregate_effective": aggregate_effective,
        "segments": segments,
        "sections": sections,
        "symbols": symbols,
        "symbol_table_entry_count": count,
    }


def _require_governed_symbol_identity(symbol, name):
    """Repair 1D.  Binding, type and visibility, enforced for EVERY governed filter symbol."""
    if symbol["info"] >> 4 != GOVERNED_SYMBOL_IDENTITY["binding"]:
        fail("TRUSTED_ELF_SYMBOL_IDENTITY_INVALID", name + " binding")
    if symbol["info"] & 0x0F != GOVERNED_SYMBOL_IDENTITY["symbol_type"]:
        fail("TRUSTED_ELF_SYMBOL_IDENTITY_INVALID", name + " type")
    if symbol["other"] & 0x03 != GOVERNED_SYMBOL_IDENTITY["visibility"]:
        fail("TRUSTED_ELF_SYMBOL_IDENTITY_INVALID", name + " visibility")
    return symbol


def _stage_c_locate(parsed, data, name, expected_size):
    """Locate ONE governed object and derive its coordinates two independent ways (repair 13).

    The file offset is derived from the DECLARED SECTION and again from the PT_LOAD that maps it,
    and the two must agree exactly.  A shifted sh_offset changes only the first derivation, a
    shifted p_offset only the second, so requiring equality catches either on its own -- which is
    what the previous single-derivation check could not do.
    """
    marker = "TRUSTED_ELF_RECONSTRUCTION_FAILED"
    matches = [symbol for symbol in parsed["symbols"] if symbol["name"] == name]
    if len(matches) != 1:
        fail(marker, "symbol multiplicity")
    symbol = matches[0]
    if symbol["size"] != expected_size:
        fail(marker, "symbol size")
    if symbol["shndx"] == SHN_UNDEF or symbol["shndx"] >= SHN_LORESERVE or symbol["shndx"] >= len(parsed["sections"]):
        fail(marker, "section index")
    section = parsed["sections"][symbol["shndx"]]
    if section["sh_type"] in (SHT_NULL, SHT_NOBITS):
        fail(marker, "declared section holds no file bytes")
    if not section["sh_flags"] & SHF_ALLOC:
        fail(marker, "declared section is not allocated")
    if (
        symbol["value"] < section["sh_addr"]
        or symbol["value"] + expected_size > section["sh_addr"] + section["sh_size"]
    ):
        fail(marker, "symbol escapes its declared section")

    loads = [
        segment
        for segment in parsed["segments"]
        if segment["p_type"] == PT_LOAD
        and segment["p_vaddr"] <= section["sh_addr"]
        and section["sh_addr"] + section["sh_size"] <= segment["p_vaddr"] + segment["p_filesz"]
    ]
    if len(loads) != 1:
        fail(marker, "declared section is not inside exactly one file-backed PT_LOAD")
    load = loads[0]
    if load["p_flags"] & PF_W:
        fail(marker, "writable mapping")
    if not load["p_flags"] & PF_R:
        fail(marker, "unreadable mapping")

    _require_governed_symbol_identity(symbol, name)
    section_derived = section["sh_offset"] + (symbol["value"] - section["sh_addr"])
    load_derived = load["p_offset"] + (symbol["value"] - load["p_vaddr"])
    if section_derived != load_derived:
        fail("TRUSTED_ELF_FILE_OFFSET_DERIVATION_DISAGREEMENT", name)
    if section["sh_offset"] - load["p_offset"] != section["sh_addr"] - load["p_vaddr"]:
        fail("TRUSTED_ELF_FILE_OFFSET_DERIVATION_DISAGREEMENT", "section within mapping")
    if section_derived + expected_size > section["sh_offset"] + section["sh_size"]:
        fail(marker, "object escapes the declared section file extent")
    if section_derived + expected_size > load["p_offset"] + load["p_filesz"]:
        fail(marker, "object escapes the mapping file extent")

    return {
        "symbol": symbol,
        "section": section,
        "load": load,
        "file_offset": section_derived,
        "bytes": _bounded(data, section_derived, expected_size, marker),
    }


def stage_c_reconstruct_worker_authority(data, canonical, outer_canonical):
    """Rebuild the governed ELF authority from the CANDIDATE BYTES (repair 1B and 1C).

    Returns exactly the canonical sub-record A2 must match.  Nothing here reads A2.
    """
    parsed = _stage_c_parse_worker(data)
    capability = _stage_c_locate(parsed, data, BLST_PLATFORM_CAP_SYMBOL, BLST_PLATFORM_CAP_SIZE_BYTES)
    fprog = _stage_c_locate(parsed, data, INTERNAL_FPROG_SYMBOL, INTERNAL_FPROG_SIZE_BYTES)
    program = _stage_c_locate(parsed, data, INTERNAL_PROGRAM_SYMBOL, INTERNAL_PROGRAM_SIZE_BYTES)
    # REPAIR 2C: the OUTER objects are reconstructed too, so the trusted verification path no longer
    # receives None for the outer object and observed outer addresses are bound to real coordinates.
    outer_fprog = _stage_c_locate(parsed, data, OUTER_FPROG_SYMBOL, OUTER_FPROG_SIZE_BYTES)
    outer_program = _stage_c_locate(parsed, data, OUTER_PROGRAM_SYMBOL, OUTER_PROGRAM_SIZE_BYTES)

    # The capability object's EXACT identity, checked against the frozen authority.
    cap_symbol = capability["symbol"]
    if cap_symbol["info"] >> 4 != STB_GLOBAL:
        fail("TRUSTED_ELF_CAPABILITY_IDENTITY_INVALID", "binding")
    if cap_symbol["other"] & 0x03 != STV_HIDDEN:
        fail("TRUSTED_ELF_CAPABILITY_IDENTITY_INVALID", "visibility")
    if cap_symbol["info"] & 0x0F != STT_OBJECT:
        fail("TRUSTED_ELF_CAPABILITY_IDENTITY_INVALID", "type")
    if capability["bytes"] != bytes(BLST_PLATFORM_CAP_SIZE_BYTES):
        fail("TRUSTED_ELF_CAPABILITY_IDENTITY_INVALID", "value")

    # THE NON-CIRCULAR ANCHOR: the object at the reconstructed address must BE the canonical
    # internal program, and the fprog descriptor must point at it.
    if hashlib.sha256(program["bytes"]).hexdigest() != canonical["program_bytes_sha256"]:
        fail("TRUSTED_ELF_PROGRAM_NOT_CANONICAL")
    expected_fprog = (
        canonical["cbpf_instruction_count"].to_bytes(2, "little")
        + bytes(FPROG_POINTER_OFFSET - 2)
        + program["symbol"]["value"].to_bytes(8, "little")
    )
    if fprog["bytes"] != expected_fprog:
        fail("TRUSTED_ELF_FPROG_NOT_CANONICAL")

    def block(prefix, located, size):
        symbol = located["symbol"]
        section = located["section"]
        load = located["load"]
        return {
            prefix + "_va_u64": symbol["value"],
            prefix + "_file_offset_u64": located["file_offset"],
            prefix + "_size_bytes": size,
            prefix + "_segment_flags_u32": load["p_flags"],
            prefix + "_section_index": symbol["shndx"],
            prefix + "_section_name": section["name"],
            prefix + "_section_addr_u64": section["sh_addr"],
            prefix + "_section_size_bytes": section["sh_size"],
            prefix + "_section_file_offset_u64": section["sh_offset"],
            prefix + "_section_type_u32": section["sh_type"],
            prefix + "_section_flags_u64": section["sh_flags"],
            prefix + "_section_file_offset_of_symbol_u64": located["file_offset"],
            prefix + "_load_index": load["index"],
            prefix + "_load_vaddr_u64": load["p_vaddr"],
            prefix + "_load_filesz_u64": load["p_filesz"],
            prefix + "_load_file_offset_u64": load["p_offset"],
            prefix + "_load_flags_u32": load["p_flags"],
        }

    filter_object = {"fprog_symbol": INTERNAL_FPROG_SYMBOL, "program_symbol": INTERNAL_PROGRAM_SYMBOL}
    filter_object.update(block("fprog", fprog, INTERNAL_FPROG_SIZE_BYTES))
    filter_object.update(block("program", program, INTERNAL_PROGRAM_SIZE_BYTES))
    filter_object["fprog_bytes_sha256"] = hashlib.sha256(fprog["bytes"]).hexdigest()
    filter_object["program_bytes_sha256"] = hashlib.sha256(program["bytes"]).hexdigest()
    filter_object["program_instruction_count"] = canonical["cbpf_instruction_count"]

    cap_block = {
        "symbol": BLST_PLATFORM_CAP_SYMBOL,
        "governed_size_bytes": BLST_PLATFORM_CAP_SIZE_BYTES,
        "observed_size_bytes": cap_symbol["size"],
        "va_u64": cap_symbol["value"],
        "file_offset_u64": capability["file_offset"],
        "value_hex": capability["bytes"].hex(),
        "segment_flags_u32": capability["load"]["p_flags"],
        "size_authority": "APPROVED_SOURCE_BUILD_CONTRACT_BUNDLE_ENTRY_2",
        "binding": "STB_GLOBAL",
        "visibility": "STV_HIDDEN",
        "symbol_type": "STT_OBJECT",
        "section_index": cap_symbol["shndx"],
        "section_name": capability["section"]["name"],
        "section_addr_u64": capability["section"]["sh_addr"],
        "section_size_bytes": capability["section"]["sh_size"],
        "section_file_offset_u64": capability["section"]["sh_offset"],
        "section_type_u32": capability["section"]["sh_type"],
        "section_flags_u64": capability["section"]["sh_flags"],
        "section_file_offset_of_symbol_u64": capability["file_offset"],
        "load_index": capability["load"]["index"],
        "load_vaddr_u64": capability["load"]["p_vaddr"],
        "load_filesz_u64": capability["load"]["p_filesz"],
        "load_memsz_u64": capability["load"]["p_memsz"],
        "load_file_offset_u64": capability["load"]["p_offset"],
        "load_flags_u32": capability["load"]["p_flags"],
    }

    if hashlib.sha256(outer_program["bytes"]).hexdigest() != outer_canonical["program_bytes_sha256"]:
        fail("TRUSTED_ELF_OUTER_PROGRAM_NOT_CANONICAL")
    expected_outer_fprog = (
        outer_canonical["cbpf_instruction_count"].to_bytes(2, "little")
        + bytes(FPROG_POINTER_OFFSET - 2)
        + outer_program["symbol"]["value"].to_bytes(8, "little")
    )
    if outer_fprog["bytes"] != expected_outer_fprog:
        fail("TRUSTED_ELF_OUTER_FPROG_NOT_CANONICAL")

    phdr_records = [
        {
            "index": segment["index"],
            "type": _PT_NAME.get(segment["p_type"], "PT_" + str(segment["p_type"])),
            "flags_u32": segment["p_flags"],
            "offset_u64": segment["p_offset"],
            "vaddr_u64": segment["p_vaddr"],
            "filesz_u64": segment["p_filesz"],
            "memsz_u64": segment["p_memsz"],
            "align_u64": segment["p_align"],
        }
        for segment in parsed["segments"]
    ]
    section_records = [
        {
            "index": section["index"],
            "name": section["name"],
            "type_u32": section["sh_type"],
            "flags_u64": section["sh_flags"],
            "addr_u64": section["sh_addr"],
            "offset_u64": section["sh_offset"],
            "size_bytes": section["sh_size"],
        }
        for section in parsed["sections"]
    ]

    return {
        "program_headers": phdr_records,
        "sections": section_records,
        "candidate_binary_bytes": len(data),
        "aggregate_effective_bytes": parsed["aggregate_effective"],
        "rlimit_as_bytes": RLIMIT_AS_BYTES,
        "page_size": PAGE_SIZE_REQUIRED,
        "outer_filter_object": {
            "fprog_va_u64": outer_fprog["symbol"]["value"],
            "program_va_u64": outer_program["symbol"]["value"],
            "fprog_file_offset_u64": outer_fprog["file_offset"],
            "program_file_offset_u64": outer_program["file_offset"],
            "program_bytes_sha256": hashlib.sha256(outer_program["bytes"]).hexdigest(),
            "program_instruction_count": outer_canonical["cbpf_instruction_count"],
        },
        "entry_va_u64": parsed["entry"],
        "program_header_count": len(parsed["segments"]),
        "section_header_count": len(parsed["sections"]),
        "symbol_table_entry_count": parsed["symbol_table_entry_count"],
        "observed_phdr_inventory": ",".join(
            _PT_NAME.get(segment["p_type"], "PT_" + str(segment["p_type"]))
            + ":"
            + str(segment["p_flags"])
            + ":"
            + hex(segment["p_align"])
            for segment in sorted(
                parsed["segments"], key=lambda item: (item["p_type"], item["p_flags"], item["p_align"])
            )
        ),
        "blst_platform_cap": cap_block,
        "canonical_internal_filter_object": filter_object,
    }


_PT_NAME = {1: "PT_LOAD", 0x6474E551: "PT_GNU_STACK", 4: "PT_NOTE", 6: "PT_PHDR"}


def recompute_elf_record_digest(elf_record):
    """Repair 1B.  The A2 digest is RECOMPUTED from the full canonical record, never compared.

    A2 and A4 both carry an ELF qualification digest, and the previous gate only checked that they
    matched each other -- which one unprivileged job can arrange trivially.  The digest is the
    domain-separated canonical hash of the whole record minus the digest field itself, so Stage C
    can and now does derive it.
    """
    if not isinstance(elf_record, dict):
        fail("ELF_RECORD_MALFORMED", "type")
    if elf_record.get("schema") != ELF_RECORD_SCHEMA:
        fail("ELF_RECORD_MALFORMED", "schema")
    claimed = require_str(elf_record.get("elf_qualification_digest_sha256"), "ELF_RECORD_MALFORMED")
    if not is_hex64(claimed):
        fail("ELF_RECORD_MALFORMED", "digest shape")
    preimage = {key: value for key, value in elf_record.items() if key != "elf_qualification_digest_sha256"}
    recomputed = domain_digest(ELF_RECORD_DIGEST_DOMAIN, preimage)
    if recomputed != claimed:
        fail("ELF_QUALIFICATION_DIGEST_MISMATCH", "A2 self-digest")
    return recomputed


# =================================================================================================
# THE EXACT A2 AND A4 SCHEMAS (repair 1A and 2).
#
# A truncated record is not a "smaller" record, it is a DIFFERENT record: every field the governed
# decision reads is mandatory, and a field nobody expected is a record this contract does not
# describe.  Both directions are enforced -- no missing field, no extra field -- so a producer can
# neither withhold evidence nor smuggle in an unreviewed one.
# =================================================================================================

A2_TOP_LEVEL_FIELDS = (
    "authority_non_transition",
    "blst_platform_cap",
    "candidate_binary_bytes",
    "candidate_binary_sha256",
    "canonical_internal_filter_object",
    "compile_dependency_inventory_digest_sha256",
    "elf",
    "elf_qualification_digest_sha256",
    "expected_phdr_inventory",
    "expected_phdr_inventory_schema",
    "memory",
    "observed_phdr_inventory",
    "page_size",
    "platform_id",
    "program_headers",
    "schema",
    "sections",
    "undefined_symbol_closure",
)

A2_ELF_FIELDS = (
    "class",
    "endianness",
    "entry_symbol",
    "entry_va_u64",
    "machine",
    "program_header_count",
    "section_header_count",
    "type",
)

A2_CAPABILITY_FIELDS = (
    "binding",
    "file_offset_u64",
    "governed_size_bytes",
    "load_file_offset_u64",
    "load_filesz_u64",
    "load_flags_u32",
    "load_index",
    "load_memsz_u64",
    "load_vaddr_u64",
    "observed_size_bytes",
    "section_addr_u64",
    "section_file_offset_of_symbol_u64",
    "section_file_offset_u64",
    "section_flags_u64",
    "section_index",
    "section_name",
    "section_size_bytes",
    "section_type_u32",
    "segment_flags_u32",
    "size_authority",
    "symbol",
    "symbol_type",
    "va_u64",
    "value_hex",
    "visibility",
)

_FILTER_OBJECT_PREFIX_FIELDS = (
    "_file_offset_u64",
    "_load_file_offset_u64",
    "_load_filesz_u64",
    "_load_flags_u32",
    "_load_index",
    "_load_vaddr_u64",
    "_section_addr_u64",
    "_section_file_offset_of_symbol_u64",
    "_section_file_offset_u64",
    "_section_flags_u64",
    "_section_index",
    "_section_name",
    "_section_size_bytes",
    "_section_type_u32",
    "_segment_flags_u32",
    "_size_bytes",
    "_va_u64",
)

A2_FILTER_OBJECT_FIELDS = tuple(
    sorted(
        ["fprog_symbol", "program_symbol", "fprog_bytes_sha256", "program_bytes_sha256", "program_instruction_count"]
        + [prefix + suffix for prefix in ("fprog", "program") for suffix in _FILTER_OBJECT_PREFIX_FIELDS]
    )
)

A2_UNDEFINED_CLOSURE_FIELDS = ("approved_inventory", "observed_inventory", "symbol_table_entry_count")

# The A2 fields Stage C RECONSTRUCTS and therefore compares rather than believes.
A2_RECONSTRUCTED_TOP_LEVEL = (
    "observed_phdr_inventory",
    "candidate_binary_bytes",
    "page_size",
)
A2_RECONSTRUCTED_ELF = ("entry_va_u64", "program_header_count", "section_header_count")

# The EXACT field set of one A2 program-header record and one A2 section record.  A record missing a
# field, or carrying an extra one, is not a smaller or larger record -- it is a different record
# than the contract describes, and it is refused in both directions.
A2_PHDR_RECORD_FIELDS = (
    "align_u64",
    "filesz_u64",
    "flags_u32",
    "index",
    "memsz_u64",
    "offset_u64",
    "type",
    "vaddr_u64",
)
A2_SECTION_RECORD_FIELDS = (
    "addr_u64",
    "flags_u64",
    "index",
    "name",
    "offset_u64",
    "size_bytes",
    "type_u32",
)
A2_MEMORY_FIELDS = (
    "aggregate_effective_bytes",
    "governed_headroom_bytes",
    "max_aggregate_effective_bytes",
    "max_pt_load_effective_bytes",
    "rlimit_as_bytes",
    "stack_reserve_bytes",
)

A4_REQUIRED_POLICY_FIELDS = (
    "canonical_internal_cbpf_instruction_count",
    "canonical_internal_cbpf_sha256",
    "canonical_internal_policy_id",
    "canonical_internal_policy_sha256",
    "canonical_outer_cbpf_instruction_count",
    "canonical_outer_cbpf_sha256",
    "canonical_outer_policy_id",
    "canonical_outer_policy_sha256",
    "outer_containment_policy_digest_sha256",
)


def _require_exact_fields(payload, expected, marker, detail):
    if not isinstance(payload, dict):
        fail(marker, detail + " type")
    observed = tuple(sorted(payload))
    if observed != tuple(sorted(expected)):
        missing = sorted(set(expected) - set(payload))
        if missing:
            fail(marker, detail + " is missing a mandatory field")
        fail(marker, detail + " carries an unexpected field")
    return payload


def validate_a2_schema(elf_record):
    """Repair 1A.  The EXACT A2 shape, enforced before a single value is trusted."""
    _require_exact_fields(elf_record, A2_TOP_LEVEL_FIELDS, "ELF_RECORD_SCHEMA_INVALID", "record")
    if elf_record.get("schema") != ELF_RECORD_SCHEMA:
        fail("ELF_RECORD_SCHEMA_INVALID", "schema id")
    if elf_record.get("platform_id") != PLATFORM_ID:
        fail("ELF_RECORD_SCHEMA_INVALID", "platform id")
    _require_exact_fields(elf_record.get("elf"), A2_ELF_FIELDS, "ELF_RECORD_SCHEMA_INVALID", "elf block")
    _require_exact_fields(
        elf_record.get("blst_platform_cap"), A2_CAPABILITY_FIELDS, "ELF_RECORD_SCHEMA_INVALID", "capability block"
    )
    _require_exact_fields(
        elf_record.get("canonical_internal_filter_object"),
        A2_FILTER_OBJECT_FIELDS,
        "ELF_RECORD_SCHEMA_INVALID",
        "filter object block",
    )
    _require_exact_fields(
        elf_record.get("undefined_symbol_closure"),
        A2_UNDEFINED_CLOSURE_FIELDS,
        "ELF_RECORD_SCHEMA_INVALID",
        "undefined symbol closure",
    )
    # REPAIR 1A: "nonempty list" is not a schema.  EVERY entry of both nested tables carries the
    # exact field set, and the tables are indexed in ascending order with no duplicate index.
    for key, expected, label in (
        ("program_headers", A2_PHDR_RECORD_FIELDS, "program header"),
        ("sections", A2_SECTION_RECORD_FIELDS, "section"),
    ):
        table = elf_record.get(key)
        if not isinstance(table, list) or not table:
            fail("ELF_RECORD_SCHEMA_INVALID", label + " table")
        indexes = []
        for entry in table:
            _require_exact_fields(entry, expected, "ELF_RECORD_SCHEMA_INVALID", label + " record")
            indexes.append(require_int(entry.get("index"), "ELF_RECORD_SCHEMA_INVALID", 0))
        if indexes != sorted(indexes) or len(set(indexes)) != len(indexes):
            fail("ELF_RECORD_SCHEMA_INVALID", label + " table ordering")
    _require_exact_fields(elf_record.get("memory"), A2_MEMORY_FIELDS, "ELF_RECORD_SCHEMA_INVALID", "memory block")
    return elf_record


def bind_a2_to_reconstruction(elf_record, reconstructed):
    """Repair 1B and 1C.  A2 must AGREE with the bytes, field for field.

    Nothing here reads a coordinate out of A2 and then checks it against another A2 coordinate.
    Every expected value comes from stage_c_reconstruct_worker_authority, which parsed the
    authenticated candidate image.
    """
    for field in A2_RECONSTRUCTED_TOP_LEVEL:
        if elf_record.get(field) != reconstructed[field]:
            fail("ELF_RECORD_CONTRADICTS_CANDIDATE", field)
    elf_block = elf_record["elf"]
    for field in A2_RECONSTRUCTED_ELF:
        if elf_block.get(field) != reconstructed[field]:
            fail("ELF_RECORD_CONTRADICTS_CANDIDATE", "elf." + field)
    if (
        require_int(
            elf_record["undefined_symbol_closure"].get("symbol_table_entry_count"), "ELF_RECORD_SCHEMA_INVALID", 1
        )
        != reconstructed["symbol_table_entry_count"]
    ):
        fail("ELF_RECORD_CONTRADICTS_CANDIDATE", "symbol table entry count")
    if elf_record["undefined_symbol_closure"].get("observed_inventory") != []:
        fail("ELF_RECORD_CONTRADICTS_CANDIDATE", "undefined symbol inventory")

    # REPAIR 1B and 1C: EVERY nested program-header and section record must equal the record Stage
    # C derived from the bytes.  Comparing a digest of A2's own dictionaries proved only that A2 was
    # internally consistent, which is exactly how a resealed PT_DYNAMIC and a 32 MiB memory claim
    # both survived.
    for key, label in (("program_headers", "program header"), ("sections", "section")):
        claimed = elf_record[key]
        derived = reconstructed[key]
        if len(claimed) != len(derived):
            fail("ELF_RECORD_CONTRADICTS_CANDIDATE", label + " count")
        for position, (entry, expected_entry) in enumerate(zip(claimed, derived)):
            for field, value in sorted(expected_entry.items()):
                if entry.get(field) != value:
                    fail("ELF_RECORD_CONTRADICTS_CANDIDATE", label + " " + str(position) + "." + field)

    # REPAIR 1D: the resource claims are RECOMPUTED, not read.
    memory = elf_record["memory"]
    for field, value in (
        ("aggregate_effective_bytes", reconstructed["aggregate_effective_bytes"]),
        ("rlimit_as_bytes", reconstructed["rlimit_as_bytes"]),
        ("max_pt_load_effective_bytes", MAX_PT_LOAD_EFFECTIVE_BYTES),
        ("max_aggregate_effective_bytes", MAX_AGGREGATE_EFFECTIVE_BYTES),
        ("stack_reserve_bytes", STACK_RESERVE_BYTES),
        ("governed_headroom_bytes", GOVERNED_HEADROOM_BYTES),
    ):
        if memory.get(field) != value:
            fail("ELF_RECORD_CONTRADICTS_CANDIDATE", "memory." + field)

    for block, expected, label in (
        (elf_record["blst_platform_cap"], reconstructed["blst_platform_cap"], "capability"),
        (
            elf_record["canonical_internal_filter_object"],
            reconstructed["canonical_internal_filter_object"],
            "filter object",
        ),
    ):
        for field, value in sorted(expected.items()):
            if block.get(field) != value:
                fail("ELF_RECORD_CONTRADICTS_CANDIDATE", label + "." + field)
    return reconstructed["canonical_internal_filter_object"]


def validate_a4_policy_authority(receipt, canonical, outer_canonical):
    """Repair 2.  A4 carries FULL outer and internal policy authority, and none of it is an oracle."""
    for field in A4_REQUIRED_POLICY_FIELDS:
        if field not in receipt:
            fail("RECEIPT_POLICY_AUTHORITY_INCOMPLETE", field)
    expected = {
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "canonical_outer_policy_id": outer_canonical["policy_id"],
        "canonical_outer_policy_sha256": outer_canonical["policy_sha256"],
        "canonical_outer_cbpf_instruction_count": outer_canonical["cbpf_instruction_count"],
        "canonical_outer_cbpf_sha256": outer_canonical["cbpf_sha256"],
        "outer_containment_policy_digest_sha256": outer_canonical["governed_sha256"],
    }
    for field, value in sorted(expected.items()):
        if receipt.get(field) != value:
            fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "A4 " + field)
    return expected


# =================================================================================================
# THE OUTER FILTER AUTHORITY CLASS (repair 2).
#
# THE CATEGORY ERROR THIS CLOSES.  The observed OUTER filter is installed by the LAUNCHER, which is
# a separately linked binary.  Comparing the launcher's runtime addresses against symbols
# reconstructed from the WORKER ELF asserted a cross-link virtual-address equality that V9 never
# defines and that no correct build has to satisfy: two independently linked images place their own
# copies of the same object wherever their own link decides.
#
# V9 SECTION 13.4 states the authority exactly.  The trusted observer S is already the tracer when
# the launcher installs its own filter, and at the launcher's seccomp syscall-ENTRY stop it:
#   * confirms the register file carries SECCOMP_SET_MODE_FILTER, flags 0 and a zero argument tail;
#   * reads the struct sock_fprog at arg2 and the len*8 instruction bytes it points at;
#   * computes CBPF_DIGEST over those captured bytes -- THAT digest is the authoritative
#     emitted_cbpf_sha256, not anything the launcher says about itself;
#   * at the syscall-EXIT stop confirms the return value is 0 AND performs measurement M-3, the
#     0 -> 1 filter-count transition, because SECTION 11.1 says a zero return is not sufficient;
#   * requires the captured bytes to equal the canonical outer program that bundle entry 12
#     derives independently from the reviewed policy source.
#
# The captured addresses are evidence of ONE launcher execution.  They are checked for internal
# coherence -- the descriptor and the program it points at are distinct, non-overlapping, and the
# descriptor's length field is the captured length -- and they are NOT compared to any worker
# address, because the two images are not the same image.
# =================================================================================================

OUTER_AUTHORITY_CLASS = "TRUSTED_LAUNCHER_CAPTURE"

# The register-file discipline V9 13.4 requires at the launcher's seccomp entry stop.
SECCOMP_SET_MODE_FILTER_VALUE = 1


def bind_observed_outer_program(case, outer_canonical):
    """Bind the observed outer filter to the V9 13.4 trusted-capture authority."""
    capture = case.get("outer_capture")
    if not isinstance(capture, dict):
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "capture block")
    if not capture.get("valid"):
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "not captured")

    program_bytes = decode_hex(
        require_str(capture.get("program_bytes_hex"), "OBSERVATION_MALFORMED"), "OBSERVATION_MALFORMED"
    )
    captured_digest = cbpf_digest(program_bytes)
    # THE AUTHORITATIVE COMPARISON: the captured program must BE the canonical outer program that
    # Stage C derived for itself from its own frozen constants.
    if captured_digest != outer_canonical["cbpf_sha256"]:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "captured differs from the Stage-C canonical program")
    captured_length = require_int(capture.get("length"), "OBSERVATION_MALFORMED", 1, 512)
    if captured_length != outer_canonical["cbpf_instruction_count"]:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "captured length")
    if len(program_bytes) != captured_length * 8:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "captured byte count")
    if require_int(capture.get("install_return_i32"), "OBSERVATION_MALFORMED") != 0:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "install return")

    # The register file at the entry stop: operation, flags and the zero argument tail.
    if require_int(capture.get("operation_u32"), "OBSERVATION_MALFORMED", 0) != SECCOMP_SET_MODE_FILTER_VALUE:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "seccomp operation")
    if require_int(capture.get("flags_u32"), "OBSERVATION_MALFORMED", 0) != 0:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "seccomp flags")
    tail = capture.get("argument_tail_u64")
    if not isinstance(tail, list) or len(tail) != 3:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "argument tail shape")
    for word in tail:
        if require_int(word, "OBSERVATION_MALFORMED", 0) != 0:
            fail("OUTER_FILTER_EQUIVALENCE_FAILED", "argument tail is not zero")

    # LAUNCHER-PROCESS addresses.  Coherent with each other, never compared to worker addresses.
    descriptor = require_int(capture.get("fprog_va_u64"), "OBSERVATION_MALFORMED", 1)
    program = require_int(capture.get("filter_va_u64"), "OBSERVATION_MALFORMED", 1)
    if descriptor == program:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "descriptor and program share an address")
    if descriptor < program + len(program_bytes) and program < descriptor + FPROG_LAYOUT_BYTES:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "descriptor and program overlap")

    # M-3, from the SECCOMP_STACK_BASELINE measurements: the authoritative 0 -> 1 transition.
    baseline = case.get("seccomp_baseline")
    if not isinstance(baseline, dict):
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "baseline block")
    if require_int(baseline.get("supervisor_filters"), "OBSERVATION_MALFORMED", 0) != 0:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "M-3 pre-state")
    if require_int(baseline.get("outer_post_filters"), "OBSERVATION_MALFORMED", 0) != 1:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "M-3 transition")
    if require_int(baseline.get("outer_post_seccomp"), "OBSERVATION_MALFORMED", 0) != 2:
        fail("OUTER_FILTER_EQUIVALENCE_FAILED", "M-3 seccomp mode")
    return captured_digest


# =================================================================================================
# ZIP_RESOURCE_POLICY (V9 SECTION 27) -- OPTION A, LITERAL AND JUSTIFIED CONSTANTS.
#
# DERIVATION INPUTS, all design facts and none a runtime candidate-provided size:
#   the candidate archive has exactly two members, the worker binary and the build manifest JSON;
#   the observation record is the largest JSON, bounded by the governed case count of 25, the
#   governed per-case event bound, and the two captured cBPF programs;
#   MAX_FILTER_INSTRUCTIONS is 512 and each instruction serialises to 8 bytes.
#
# SCHEMA-DERIVED WORST CASE for the observation record:
#   per case      = MAX_SYSCALL_EVENTS_PER_CASE * MAX_EVENT_RECORD_BYTES + MAX_CASE_FIXED_FIELD_BYTES
#                 = 256 * 256 + 1024                      =    66 560 bytes
#   all cases     = 66 560 * 25                           = 1 664 000 bytes
#   captured cBPF = 2 * (512 * 8 * 2 hex chars + framing) <=    20 000 bytes
#   envelope                                              =    32 768 bytes
#   TOTAL                                                 <= 1 716 768 bytes  (about 1.64 MiB)
#
# These are LITERAL FROZEN CONSTANTS.  There is no runtime derivation, no headroom multiplier
# applied to an observed value, and no DESIGN_TO_FREEZE remainder.  If a future artifact schema grows
# past a bound, the correct response is to re-derive and re-freeze the constant in a new architecture
# revision, never to widen it at run time.
# =================================================================================================

MAX_SYSCALL_EVENTS_PER_CASE = 256
MAX_EVENT_RECORD_BYTES = 256
MAX_CASE_FIXED_FIELD_BYTES = 1024
MAX_RECORD_ENVELOPE_BYTES = 32768

MAX_MEMBER_UNCOMPRESSED_JSON = 4 * 1024 * 1024
MAX_WORKER_BINARY_BYTES = 8 * 1024 * 1024
MAX_MEMBER_UNCOMPRESSED_BINARY = MAX_WORKER_BINARY_BYTES
MAX_AGGREGATE_UNCOMPRESSED = 16 * 1024 * 1024
MAX_MEMBER_COMPRESSED = 16 * 1024 * 1024
MAX_ARCHIVE_BYTES = 16 * 1024 * 1024
MAX_RATIO = 100
CHUNK_BYTES = 65536

# Repair 6D: EVERY external response body is bounded, not just archive members.  A metadata endpoint
# that returned an unbounded stream would be exactly as effective a resource attack as a zip bomb.
# LIMIT+1 is requested so that reaching the limit is DETECTED rather than silently truncated.
MAX_API_RESPONSE_BYTES = 4 * 1024 * 1024

ZIP_STORED = 0
ZIP_DEFLATED = 8
ALLOWED_COMPRESSION_METHODS = (ZIP_STORED, ZIP_DEFLATED)

# =================================================================================================
# GITHUB ENUMERATION BOUNDS (V9 SECTION 22.2 and SECTION 23)
# =================================================================================================

PER_PAGE = 100
MAX_PAGES_PER_COLLECTION = 50
MAX_RECORDS_PER_COLLECTION = 5000

# The endpoints whose service contract INCLUDES total_count, frozen at design time.  For an endpoint
# inside this set total_count is MANDATORY SERVICE EVIDENCE and there is no "the endpoint might not
# provide it" path (V9 23.2 T2).
GOVERNED_TOTAL_COUNT_ENDPOINTS = ("attempt_jobs", "run_artifacts")

REDIRECT_STATUS_CODES = frozenset((301, 302, 303, 307, 308))


class TrustedGateError(RuntimeError):
    """Any failure to prove a required binding.  There is no partial success."""


def fail(marker, detail=""):
    raise TrustedGateError(marker if not detail else marker + ": " + detail)


# =================================================================================================
# CANONICAL ENCODING
# =================================================================================================


def canonical_json(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode(
        "utf-8"
    )


def domain_digest(domain, payload):
    return hashlib.sha256(domain + canonical_json(payload)).hexdigest()


def is_hex64(value):
    return isinstance(value, str) and len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def require_int(value, marker, low=None, high=None):
    if isinstance(value, bool) or not isinstance(value, int):
        fail(marker, "value must be a JSON integer")
    if low is not None and value < low:
        fail(marker, "value below the governed bound")
    if high is not None and value > high:
        fail(marker, "value above the governed bound")
    return value


def require_str(value, marker):
    if not isinstance(value, str):
        fail(marker, "value must be a JSON string")
    return value


# EVERY decoder below converts a malformed UNTRUSTED input into an exact frozen failure reason.  A
# raw traceback or an exception string would put attacker-influenced bytes into a log an operator
# reads, and would describe the input rather than naming the rule it violated.
def decode_hex(value, marker):
    if not isinstance(value, str):
        fail(marker, "hex must be a JSON string")
    if len(value) % 2 != 0:
        fail(marker, "hex length is odd")
    for character in value:
        if character not in "0123456789abcdef":
            fail(marker, "hex alphabet")
    try:
        return bytes.fromhex(value)
    except ValueError:
        fail(marker, "hex decode")
    return b""


# The governed structural bound for any trusted JSON document.  Every document this gate reads is a
# flat-to-shallow record; a deeply nested one is not a schema variation, it is a resource attack, and
# a RecursionError escaping as a traceback would be exactly the unfrozen failure channel the policy
# forbids.  The depth is measured BEFORE parsing, from the text, so the parser is never asked to
# descend at all.
MAX_JSON_DEPTH = 32


def _json_structure_status(decoded):
    """Bounded structural scan over the raw text.  String contents are skipped.

    Returns "" when the document is balanced and within the depth bound, otherwise the exact frozen
    reason -- an over-deep document and an unbalanced one are different defects and are named
    differently, so a truncated record is not reported as a depth attack.
    """
    depth = 0
    inside_string = False
    escaped = False
    for character in decoded:
        if inside_string:
            if escaped:
                escaped = False
            elif character == chr(92):
                escaped = True
            elif character == '"':
                inside_string = False
            continue
        if character == '"':
            inside_string = True
        elif character in "[{":
            depth += 1
            if depth > MAX_JSON_DEPTH:
                return "structure exceeds the governed depth bound"
        elif character in "]}":
            depth -= 1
            if depth < 0:
                return "unbalanced structure"
    if inside_string or depth != 0:
        return "unbalanced structure"
    return ""


def _reject_duplicate_keys(pairs):
    """Repair 6B.  Last-key-wins silently normalises a malformed document; this refuses it."""
    seen = set()
    for key, _value in pairs:
        if key in seen:
            raise _StrictJsonError("duplicate key")
        seen.add(key)
    return dict(pairs)


def _reject_non_standard_constant(_text):
    """NaN, Infinity and -Infinity are not JSON, and none of them is a governed value."""
    raise _StrictJsonError("non-standard constant")


class _StrictJsonError(ValueError):
    """Raised inside the parser hooks; converted to a frozen reason by decode_json."""


def decode_json(body, marker):
    """Decode one UNTRUSTED JSON document STRICTLY.  No exception text ever escapes.

    Repair 6B and 6C.  Duplicate object keys fail rather than resolving to last-key-wins; NaN,
    Infinity and -Infinity fail rather than becoming floats no governed comparison expects; and a
    deeply nested document is refused by the depth scan before the parser can raise RecursionError.
    Every failure below is a frozen reason class and none of them echoes the input.
    """
    if not isinstance(body, (bytes, bytearray)):
        fail(marker, "body type")
    try:
        decoded = bytes(body).decode("utf-8")
    except UnicodeDecodeError:
        fail(marker, "not valid utf-8")
        return None
    structure = _json_structure_status(decoded)
    if structure:
        fail(marker, structure)
    try:
        return json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_keys,
            parse_constant=_reject_non_standard_constant,
        )
    except _StrictJsonError:
        fail(marker, "document violates the strict json contract")
    except RecursionError:
        fail(marker, "structure exceeds the governed depth bound")
    except (ValueError, OverflowError):
        fail(marker, "not valid json")
    return None


def _load_bounded_json(path, description):
    """Read one locally supplied JSON document under the governed local-input bound.

    REPAIR 7.  A local file is not a trusted file: the two inventories arrive here from a workflow
    step, and the artifact-derived one was produced by an unprivileged job.  This used to call
    json.loads directly, which meant duplicate keys resolved to last-key-wins, NaN became a float,
    and a deeply nested document raised RecursionError as a traceback -- exactly the three defects
    the strict decoder exists to prevent.  There is now ONE decoder and every untrusted JSON input
    goes through it.
    """
    with open(path, "rb") as handle:
        body = handle.read(MAX_LOCAL_INPUT_BYTES + 1)
    if len(body) > MAX_LOCAL_INPUT_BYTES:
        fail("LOCAL_INPUT_BOUND_EXCEEDED", description)
    return decode_json(body, "LOCAL_INPUT_MALFORMED")


# =================================================================================================
# AUTHENTICATED API ACCESS
# =================================================================================================


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


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Expose a redirect response to the caller instead of following it."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _authorization_header():
    """Build the Authorization header value, and confine the credential to this function.

    The credential is deliberately NOT threaded through the call graph as a parameter.  It
    is read here, consumed here, and never bound to a name that any other function can
    reach, so it cannot flow into the trusted predicate this gate writes to disk, into a
    log line, or into any error marker.  It is never printed and never persisted.
    """
    value = os.environ.get("GITHUB_TOKEN") or ""
    if not value:
        fail("CREDENTIAL_UNAVAILABLE")
    return "Bearer " + value


def _request(url, accept):
    request = urllib.request.Request(url)  # noqa: S310 - fixed https API base, no user-supplied scheme
    request.add_header("Accept", accept)
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("Authorization", _authorization_header())
    return request


def api_json(api_url, path):
    url = api_url.rstrip("/") + path
    if not url.startswith("https://"):
        fail("API_URL_INVALID")
    opener = urllib.request.build_opener(_StripAuthOnRedirect())
    body = None
    try:
        with opener.open(_request(url, "application/vnd.github+json"), timeout=60) as response:
            body = response.read(MAX_API_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError:
        # The PATH carries a run id and an artifact id.  A frozen endpoint label is enough for a
        # fail-closed decision and leaks nothing the service supplied.
        fail("GITHUB_API_FAILED")
    except urllib.error.URLError:
        fail("GITHUB_API_FAILED")
    if body is None or len(body) > MAX_API_RESPONSE_BYTES:
        fail("GITHUB_API_RESPONSE_BOUND_EXCEEDED")
    return decode_json(body, "GITHUB_API_RESPONSE_MALFORMED")


# =================================================================================================
# MT4_S3C_COMPLETE_ENUMERATION_V1 (V9 22.2) AND THE TOTAL_COUNT CONTRACT (V9 SECTION 23)
# =================================================================================================


def enumerate_collection(api_url, base_path, item_key, endpoint_name):
    """Enumerate EVERY page.  The first page is NEVER assumed complete (P7).

    No selection, duplicate check or existence check may run until enumeration has terminated by the
    short-final-page rule and been reconciled against the governed total_count.
    """
    items = []
    identifiers = set()
    totals = []
    page = 1
    terminated_by_short_page = False

    while True:
        if page > MAX_PAGES_PER_COLLECTION:
            fail("PAGINATION_BOUND_EXCEEDED", endpoint_name + " pages")
        separator = "&" if "?" in base_path else "?"
        payload = api_json(api_url, base_path + separator + "per_page=" + str(PER_PAGE) + "&page=" + str(page))
        if not isinstance(payload, dict):
            fail("PAGINATION_MALFORMED", endpoint_name)
        batch = payload.get(item_key)
        if not isinstance(batch, list):
            fail("PAGINATION_MALFORMED", endpoint_name + " missing " + item_key)
        # P4: a page whose item array length EXCEEDS per_page is malformed.
        if len(batch) > PER_PAGE:
            fail("PAGINATION_MALFORMED", endpoint_name + " oversized page")
        if "total_count" in payload:
            totals.append(
                require_int(payload.get("total_count"), "TOTAL_COUNT_MALFORMED", 0, MAX_RECORDS_PER_COLLECTION)
            )
        elif endpoint_name in GOVERNED_TOTAL_COUNT_ENDPOINTS:
            # T2: for a governed endpoint total_count is MANDATORY SERVICE EVIDENCE.  A future
            # contract change that removes it is TOTAL_COUNT_MISSING and returns to architecture; it
            # is never resolved by the gate degrading at run time.
            fail("TOTAL_COUNT_MISSING", endpoint_name)

        for item in batch:
            if not isinstance(item, dict):
                fail("PAGINATION_MALFORMED", endpoint_name + " item type")
            identifier = require_int(item.get("id"), "PAGINATION_MALFORMED", 0)
            # P5: an id seen on more than one page fails closed.
            if identifier in identifiers:
                fail("PAGINATION_REPEATED_RECORD", endpoint_name)
            identifiers.add(identifier)
            items.append(item)
        if len(items) > MAX_RECORDS_PER_COLLECTION:
            fail("PAGINATION_BOUND_EXCEEDED", endpoint_name + " records")
        # P2: continue while a full page comes back; stop on the first short page.
        if len(batch) < PER_PAGE:
            terminated_by_short_page = True
            break
        page += 1

    if endpoint_name in GOVERNED_TOTAL_COUNT_ENDPOINTS:
        reconcile_total_count(totals, items, identifiers, terminated_by_short_page, endpoint_name)
    elif totals:
        # T5: a total_count is never fabricated, synthesised from a page count, or inferred for an
        # endpoint outside the governed set.  Where one happens to be present it must still be
        # self-consistent across pages.
        if len(set(totals)) != 1:
            fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " differs between pages")
    return items


def reconcile_total_count(totals, items, identifiers, terminated_by_short_page, endpoint_name):
    """T3 and T4.  All four consistency conditions are required TOGETHER."""
    if not totals:
        fail("TOTAL_COUNT_MISSING", endpoint_name)
    # T4: no page's total_count is privileged, and a value that changes between pages means the
    # collection mutated underneath a multi-page read.
    if len(set(totals)) != 1:
        fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " differs between pages")
    total = totals[0]
    # C-a detects a truncated or over-long enumeration.
    if len(items) != total:
        fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " accumulated " + str(len(items)) + " vs " + str(total))
    # C-b is P5 restated as an equality, so a repeated record cannot silently inflate C-a.
    if len(identifiers) != len(items):
        fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " unique ids differ from records")
    # C-c detects duplicate ids padding the enumeration to the right total.
    if len(identifiers) != total:
        fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " unique ids differ from total_count")
    # C-d: termination by a short final page, not by exhausting the page bound.
    if not terminated_by_short_page:
        fail("TOTAL_COUNT_INCONSISTENT", endpoint_name + " did not terminate on a short page")


# =================================================================================================
# ARTIFACT DOWNLOAD: authenticated resolve, then a wholly credential-free storage download.
# =================================================================================================


def _validated_storage_url(location):
    """Accept only an absolute, credential-free-to-call HTTPS storage URL.

    The URL itself can carry temporary authorization material in its query string, so no error
    marker ever interpolates it.
    """
    if not isinstance(location, str) or not location or location != location.strip():
        fail("ARTIFACT_REDIRECT_MALFORMED")
    if any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in location):
        fail("ARTIFACT_REDIRECT_MALFORMED")
    try:
        parsed = urllib.parse.urlsplit(location)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        fail("ARTIFACT_REDIRECT_MALFORMED")
        return ""
    if parsed.scheme.lower() != "https":
        fail("ARTIFACT_REDIRECT_MALFORMED", "scheme")
    if parsed.username is not None or parsed.password is not None:
        fail("ARTIFACT_REDIRECT_MALFORMED", "userinfo")
    if not parsed.netloc or not hostname or port == 0:
        fail("ARTIFACT_REDIRECT_MALFORMED", "authority")
    return location


def download_artifact(api_url, repository, artifact_id):
    url = api_url.rstrip("/") + "/repos/" + repository + "/actions/artifacts/" + str(artifact_id) + "/zip"
    if not url.startswith("https://"):
        fail("API_URL_INVALID")
    opener = urllib.request.build_opener(_NoRedirect())
    location = None
    try:
        response = opener.open(_request(url, "application/vnd.github+json"), timeout=60)
    except urllib.error.HTTPError as error:
        if error.code not in REDIRECT_STATUS_CODES:
            fail("ARTIFACT_REDIRECT_FAILED")
        location = error.headers.get("Location")
        error.close()
    except urllib.error.URLError:
        fail("ARTIFACT_REDIRECT_FAILED")
    else:
        with response:
            if response.getcode() not in REDIRECT_STATUS_CODES:
                fail("ARTIFACT_REDIRECT_REQUIRED")
            location = response.headers.get("Location")
    if not location:
        fail("ARTIFACT_REDIRECT_MALFORMED", "missing Location")

    storage_url = _validated_storage_url(location)
    request = urllib.request.Request(storage_url)  # noqa: S310 - validated HTTPS redirect target
    storage_opener = urllib.request.build_opener(_NoRedirect())
    try:
        with storage_opener.open(request, timeout=300) as response:
            payload = response.read(MAX_ARCHIVE_BYTES + 1)
    except urllib.error.HTTPError:
        fail("ARTIFACT_DOWNLOAD_FAILED")
    except urllib.error.URLError:
        fail("ARTIFACT_DOWNLOAD_FAILED")
    # Z1 is enforced again below from the central directory; this bound stops the read itself.
    if len(payload) > MAX_ARCHIVE_BYTES:
        fail("ZIP_ARCHIVE_BYTES")
    return payload


# =================================================================================================
# THE BOUNDED STREAMING ARCHIVE READER (V9 SECTION 27.3 and 27.4).
#
# archive.read(member) is FORBIDDEN in S3C and appears nowhere in this file: it decompresses the
# whole member into memory BEFORE any bound is consulted, which is exactly the merged S3B defect
# this policy exists to avoid.
# =================================================================================================


def _member_cap(name):
    return MAX_MEMBER_UNCOMPRESSED_BINARY if name == WORKER_BINARY_MEMBER else MAX_MEMBER_UNCOMPRESSED_JSON


def pre_decompression_gate(archive, payload, expected_members):
    """Z1..Z13, run entirely from the central directory BEFORE any member is opened.

    RULE ORDER IS PART OF THE CONTRACT (repair 6A).  Every rule must own a REACHABLE violation
    class.  Z4 previously sat behind Z3's sorted-name-set equality, which a duplicated member
    already fails, so the duplicate class could never be observed; the duplicate check therefore now
    runs BEFORE the name-set comparison, and Z3 keeps the genuinely distinct wrong-name class.  No
    failure detail interpolates a member name: names come from the archive and are untrusted.
    """
    if len(payload) > MAX_ARCHIVE_BYTES:
        fail("ZIP_ARCHIVE_BYTES")  # Z1
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(infos) != len(expected_members):
        fail("ZIP_MEMBER_COUNT")  # Z2
    # Z4: a ZIP central directory can legally carry two entries with the same name.  Checked here,
    # ahead of the set comparison, so a duplicate is reported as a duplicate.
    if len(names) != len(set(names)):
        fail("ZIP_DUPLICATE_MEMBER")
    if sorted(names) != sorted(expected_members):
        fail("ZIP_MEMBER_NAME_SET")  # Z3
    aggregate_declared = 0
    for info in infos:
        name = info.filename
        if name.endswith("/") or info.is_dir():
            fail("ZIP_UNSAFE_MEMBER", "directory entry")  # Z5
        # Z6: path traversal, absolute paths and non-basenames.
        if name in ("", ".", "..") or "/" in name or "\\" in name or ":" in name:
            fail("ZIP_UNSAFE_MEMBER", "path")
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            fail("ZIP_UNSAFE_MEMBER", "control character")
        # Z7: where the entry carries Unix mode bits, the file type must be regular.
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) not in (0, 0o100000):
            fail("ZIP_UNSAFE_MEMBER", "non-regular type")
        if info.flag_bits & 0x1:
            fail("ZIP_ENCRYPTED_MEMBER")  # Z8
        if info.compress_type not in ALLOWED_COMPRESSION_METHODS:
            fail("ZIP_COMPRESSION_METHOD")  # Z9
        cap = _member_cap(name)
        if info.file_size > cap:
            fail("ZIP_DECLARED_SIZE")  # Z10
        if info.compress_size > MAX_MEMBER_COMPRESSED:
            fail("ZIP_COMPRESSED_SIZE")  # Z11
        aggregate_declared += info.file_size
        # Z13: EXACT integer inequality.  Floor division under-detects -- 201 // 2 is 100, which is
        # not greater than a limit of 100, while the true ratio 100.5 already exceeds it.  A zero
        # declared compressed size carrying content is a ratio no bound can express and is rejected
        # outright.  No float arithmetic appears anywhere in this comparison.
        if info.compress_size == 0:
            if info.file_size != 0:
                fail("ZIP_DECLARED_RATIO")
        elif info.file_size > MAX_RATIO * info.compress_size:
            fail("ZIP_DECLARED_RATIO")
    if aggregate_declared > MAX_AGGREGATE_UNCOMPRESSED:
        fail("ZIP_DECLARED_AGGREGATE")  # Z12
    return infos


def _member_data_start(payload, info):
    """Locate a member's COMPRESSED byte range from the archive structure itself.

    Z18's frozen contract is runtime CONSUMPTION, not the central directory's declaration, so the
    streaming reader must feed the decompressor itself and count what it actually consumes.  The
    local file header is parsed here for exactly that purpose: its name and extra lengths give the
    offset at which the compressed stream starts.  The DECLARED sizes in the local header are
    deliberately ignored -- with a data descriptor they are legally zero, and either way they are a
    claim rather than an observation.
    """
    header_offset = info.header_offset
    if not isinstance(header_offset, int) or header_offset < 0 or header_offset + 30 > len(payload):
        fail("ZIP_LOCAL_HEADER_INVALID")
    header = payload[header_offset : header_offset + 30]
    # The local file header signature, written as bytes so no escape sequence can be mis-read.
    if bytes(header[0:4]) != bytes((0x50, 0x4B, 0x03, 0x04)):
        fail("ZIP_LOCAL_HEADER_INVALID")
    name_length = int.from_bytes(header[26:28], "little")
    extra_length = int.from_bytes(header[28:30], "little")
    data_start = header_offset + 30 + name_length + extra_length
    if data_start > len(payload):
        fail("ZIP_LOCAL_HEADER_INVALID")
    local_name = bytes(payload[header_offset + 30 : header_offset + 30 + name_length])
    try:
        decoded_name = local_name.decode("utf-8")
    except UnicodeDecodeError:
        fail("ZIP_LOCAL_HEADER_INVALID")
        return 0
    if decoded_name != info.filename:
        fail("ZIP_LOCAL_HEADER_NAME_MISMATCH")
    return data_start


def stream_member(archive, info, aggregate_state, payload):
    """Z14..Z20.  A member is NEVER read whole, and Z18 counts REAL consumed compressed bytes.

    zipfile's own reader is not used for the member body: it exposes no trustworthy count of the
    compressed bytes it has consumed, and Z18's frozen semantic is exactly that quantity.  The raw
    compressed range is therefore fed to a zlib decompressor here in bounded chunks, with production
    per call capped, so the ratio bound is enforced against bytes ACTUALLY consumed rather than
    against a number the central directory supplied.  The CRC is verified from the decompressed
    bytes, which makes Z20 proven rather than delegated.
    """
    del archive
    cap = _member_cap(info.filename)
    data_start = _member_data_start(payload, info)
    limit = data_start + min(MAX_MEMBER_COMPRESSED, len(payload) - data_start)
    digest = hashlib.sha256()
    chunks = []
    streamed = 0
    consumed_compressed = 0
    position = data_start

    def account(produced):
        """Apply Z15, Z16, Z17 and Z18 to one production step."""
        nonlocal streamed
        streamed += len(produced)
        if streamed > cap:
            fail("ZIP_MEMBER_STREAM_OVERRUN")  # Z15
        if streamed > info.file_size:
            # Z16: the check that catches a lying central directory, mid-stream.
            fail("ZIP_DECLARED_SIZE_UNDERSTATED")
        aggregate_state["streamed"] += len(produced)
        if aggregate_state["streamed"] > MAX_AGGREGATE_UNCOMPRESSED:
            fail("ZIP_AGGREGATE_OVERRUN")  # Z17
        # Z18 against CONSUMED compressed bytes.  Zero consumption with any production is a ratio no
        # bound can express.
        if consumed_compressed == 0:
            if streamed != 0:
                fail("ZIP_RATIO_EXCEEDED")
        elif streamed > MAX_RATIO * consumed_compressed:
            fail("ZIP_RATIO_EXCEEDED")
        if consumed_compressed > MAX_MEMBER_COMPRESSED:
            fail("ZIP_COMPRESSED_SIZE")  # Z11 restated against real consumption
        digest.update(produced)
        chunks.append(produced)

    if info.compress_type == ZIP_STORED:
        while streamed < info.file_size:
            if position >= limit:
                fail("ZIP_MEMBER_STREAM_TRUNCATED")
            take = min(CHUNK_BYTES, info.file_size - streamed, limit - position)
            produced = bytes(payload[position : position + take])
            position += take
            consumed_compressed += take
            account(produced)
    else:
        decompressor = zlib.decompressobj(-15)
        pending = b""
        while True:
            if not pending:
                if position >= limit:
                    fail("ZIP_MEMBER_STREAM_TRUNCATED")
                chunk = bytes(payload[position : min(position + CHUNK_BYTES, limit)])
                position += len(chunk)
                pending = chunk
            # EXACT CONSUMPTION (repair 6A), measured PER CALL.  Counting bytes FED is not the
            # same quantity: a bounded decompress call leaves whatever it could not turn into
            # output in unconsumed_tail, and at end-of-stream everything after the deflate stream
            # lands in unused_data.  Neither has been consumed.  Consumption for this call is
            # therefore exactly what was offered minus what came back unconsumed, and because the
            # tail is re-offered on the next iteration and measured again the same way, nothing is
            # double-counted.  Every Z18 decision below uses the real consumed count rather than an
            # over-count that would make the ratio bound more permissive than it is meant to be.
            offered = len(pending)
            produced = decompressor.decompress(pending, CHUNK_BYTES)
            leftover = len(decompressor.unconsumed_tail)
            if decompressor.eof:
                # AT END-OF-STREAM THE TWO BUFFERS DESCRIBE THE SAME BYTES.  Once the deflate stream
                # has ended every byte still held is post-stream data, so CPython reports it in
                # unused_data AND mirrors it in unconsumed_tail.  Adding them is the double-count
                # this rule exists to avoid -- it silently understates consumption, which makes the
                # ratio bound more permissive and breaks reconciliation against the declared size.
                leftover = max(leftover, len(decompressor.unused_data))
            if leftover > offered:
                fail("ZIP_CONSUMPTION_ACCOUNTING_INVALID")
            consumed_compressed += offered - leftover
            pending = decompressor.unconsumed_tail
            account(produced)
            if decompressor.eof:
                break

    # Z18 restated on the FINAL corrected consumption.  The per-step check runs before the trailing
    # bytes after the deflate stream are subtracted, so it can only ever be MORE permissive; this is
    # the exact one.
    if consumed_compressed == 0:
        if streamed != 0:
            fail("ZIP_RATIO_EXCEEDED")
    elif streamed > MAX_RATIO * consumed_compressed:
        fail("ZIP_RATIO_EXCEEDED")
    if streamed != info.file_size:
        fail("ZIP_DECLARED_SIZE_OVERSTATED")  # Z19
    if consumed_compressed != info.compress_size:
        fail("ZIP_COMPRESSED_SIZE_MISDECLARED")
    body = b"".join(chunks)
    # Z20: the CRC is PROVEN here from the decompressed bytes rather than delegated.
    if (zlib.crc32(body) & 0xFFFFFFFF) != (info.CRC & 0xFFFFFFFF):
        fail("ZIP_CRC_INVALID")
    return body, digest.hexdigest()


def extract_artifact(payload, expected_members):
    """Decode one artifact archive entirely under the bounded streaming policy."""
    aggregate_state = {"streamed": 0}
    contents = {}
    digests = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = pre_decompression_gate(archive, payload, expected_members)
            for info in infos:
                body, digest = stream_member(archive, info, aggregate_state, payload)
                contents[info.filename] = body
                digests[info.filename] = digest
    except zipfile.BadZipFile:
        fail("ZIP_ARCHIVE_MALFORMED")
    except zlib.error:
        # A frozen class, never the library's message: the bytes that produced it are untrusted.
        fail("ZIP_DEFLATE_STREAM_INVALID")
    except (OSError, ValueError):
        fail("ZIP_ARCHIVE_MALFORMED")
    return contents, digests


# =================================================================================================
# THE QUALIFICATION SOURCE BUNDLE (V9 SECTION 8)
#
# The gate NEVER shells out and NEVER imports a repository module, so the committed-bytes inventory
# is produced by the trusted workflow itself, inside the same trusted job, from the checkout already
# PROVEN to be the exact source-run head.  The gate then validates that inventory exhaustively and
# recomputes the bundle digest from it.  The APPROVED constant lives ONLY on the trusted surface, so
# the thing being measured cannot change the measuring constant.
# =================================================================================================


def recompute_source_bundle_digest(inventory_payload):
    if not isinstance(inventory_payload, dict):
        fail("SOURCE_BUNDLE_CONTRADICTION", "inventory type")
    entries = inventory_payload.get("entries")
    if not isinstance(entries, list) or len(entries) != SOURCE_BUNDLE_ENTRY_COUNT:
        fail("SOURCE_BUNDLE_CONTRADICTION", "entry count")
    normalised = []
    for entry in entries:
        if not isinstance(entry, dict):
            fail("SOURCE_BUNDLE_CONTRADICTION", "entry type")
        path = require_str(entry.get("path"), "SOURCE_BUNDLE_CONTRADICTION")
        mode = require_str(entry.get("mode"), "SOURCE_BUNDLE_CONTRADICTION")
        kind = require_str(entry.get("type"), "SOURCE_BUNDLE_CONTRADICTION")
        digest = require_str(entry.get("sha256"), "SOURCE_BUNDLE_CONTRADICTION")
        if mode not in ("100644", "100755"):
            fail("SOURCE_BUNDLE_CONTRADICTION", "mode")
        if kind != "blob":
            fail("SOURCE_BUNDLE_CONTRADICTION", "type")
        if not is_hex64(digest):
            fail("SOURCE_BUNDLE_CONTRADICTION", "digest")
        normalised.append({"path": path, "mode": mode, "type": kind, "sha256": digest})
    paths = [entry["path"] for entry in normalised]
    if paths != sorted(paths):
        fail("SOURCE_BUNDLE_CONTRADICTION", "ordering")
    if tuple(paths) != SOURCE_BUNDLE_PATHS:
        fail("SOURCE_BUNDLE_CONTRADICTION", "inventory differs from the frozen sixteen")
    preimage = {
        "schema": SOURCE_BUNDLE_SCHEMA,
        "entry_count": len(normalised),
        "entries": normalised,
        "path_order": paths,
    }
    return domain_digest(SOURCE_BUNDLE_DIGEST_DOMAIN, preimage), normalised


def recompute_dependency_inventory_digest(inventory_payload, bundle_entries):
    """V9 28.6 leg D-5, recomputed at the trust boundary rather than trusted from the job.

    Repair 7F and 7G.  The schema, the exact entry field set, the class-determined provenance, path
    uniqueness and the required translation-unit coverage are all enforced HERE before the digest is
    recomputed, so an inventory that omits a load-bearing native input cannot produce a digest that
    any downstream record can match.
    """
    if not isinstance(inventory_payload, dict):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "type")
    if inventory_payload.get("schema") != DEPENDENCY_SCHEMA:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "schema")
    entries = inventory_payload.get("entries")
    if not isinstance(entries, list) or not entries:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entries")
    committed = {entry["path"]: entry["sha256"] for entry in bundle_entries}
    paths = []
    seen = set()
    bundled = set()
    upstream = set()
    for entry in entries:
        if not isinstance(entry, dict):
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entry type")
        if tuple(sorted(entry)) != tuple(sorted(DEPENDENCY_ENTRY_FIELDS)):
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entry field set")
        path = require_str(entry.get("path"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        kind = require_str(entry.get("class"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        provenance = require_str(entry.get("provenance"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        digest = require_str(entry.get("sha256"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        if kind not in DEPENDENCY_CLASSES:
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "class")
        # A generic "this dependency exists" row is not accepted: provenance is class-determined and
        # the upstream class is bound to the exact pinned commit and source-tree digest.
        if provenance != CLASS_PROVENANCE[kind]:
            fail("COMPILE_DEPENDENCY_PROVENANCE_INVALID")
        if path in seen:
            fail("COMPILE_DEPENDENCY_DUPLICATE_PATH")
        seen.add(path)
        if kind == CLASS_REPO_BUNDLED:
            # Every REPO_BUNDLED path must be a bundle entry, and its content digest must equal the
            # digest re-derived from the git object store at the proven source head.
            if path not in SOURCE_BUNDLE_PATHS:
                fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED")
            if committed.get(path) != digest:
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "content digest")
            bundled.add(path)
        elif kind == CLASS_EXTERNAL_TOOLCHAIN:
            if digest != "":
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "external entry carries a digest")
        else:
            # REPAIR 12, OPTION B.  Stage C holds no independent per-file digest table for blst
            # v0.3.17 and cannot obtain one without external evidence, so a producer-supplied
            # per-file hash is NOT authority and must not sit inside a trusted equality chain
            # pretending to be one.  The pinned upstream identity that IS trusted -- repository,
            # release, commit and source-tree digest, all compared against literals on this
            # surface -- is what binds these inputs; the per-file value is carried as
            # non-authoritative metadata and is required to be EMPTY so it cannot be mistaken for
            # a verified one.
            if digest != "":
                fail("PINNED_UPSTREAM_PER_FILE_DIGEST_NOT_AUTHORITATIVE", path)
            upstream.add(path)
        paths.append(path)

    # Repair 7E, enforced at the boundary: the complete set of load-bearing native inputs.
    for required in REQUIRED_TRANSLATION_UNITS:
        if required not in bundled:
            fail("COMPILE_INVENTORY_INCOMPLETE", required)
    for required in REQUIRED_UPSTREAM_INPUTS:
        if required not in upstream:
            fail("COMPILE_INVENTORY_INCOMPLETE", required)

    if paths != sorted(paths):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "ordering")
    if require_int(inventory_payload.get("entry_count"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH", 0) != len(entries):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entry_count")
    if inventory_payload.get("path_order") != paths:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "path_order")
    if tuple(sorted(inventory_payload)) != ("entries", "entry_count", "path_order", "schema"):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "document field set")
    return domain_digest(DEPENDENCY_DIGEST_DOMAIN, inventory_payload)


# =================================================================================================
# STAGE-C RECOMPUTATION OF THE INTERNAL FILTER EQUIVALENCE DIGEST (V9 SECTION 16.4).
#
# This is the THIRD independent computation.  The trusted observer computed it into A3 from the live
# observation; the adjudicator recomputed it into A4 from the raw observation fields; Stage C
# reconstructs the canonical internal policy reference, the canonical cBPF reference, the RAW
# TRUSTED A3 PREIMAGE, and the digest itself, and then requires
#
#     A3 == A4 == STAGE_C_RECOMPUTED
#
# Unprivileged B2 can never be the final authority, and receipt equality alone is insufficient.
# =================================================================================================

DUMP_AVAILABLE = "AVAILABLE"
DUMP_UNAVAILABLE = "UNAVAILABLE_IN_PINNED_ENVIRONMENT"

INTERNAL_EQUIVALENCE_REQUIRED_VALUES = {
    "install_exit_return_i32": 0,
    "baseline_supervisor_seccomp": 0,
    "baseline_supervisor_filters": 0,
    "baseline_child_seccomp": 0,
    "baseline_child_filters": 0,
    "pre_install_filters": 1,
    "post_install_filters": 2,
    "post_install_seccomp_mode": 2,
    "revalidated_filters": 2,
}


def cbpf_digest(program_bytes):
    if len(program_bytes) % 8 != 0:
        fail("CBPF_REPRESENTATION_INVALID")
    count = len(program_bytes) // 8
    preimage = PROGRAM_REPRESENTATION_VERSION.encode("ascii") + b"\x00" + count.to_bytes(4, "little") + program_bytes
    return hashlib.sha256(preimage).hexdigest()


def stage_c_equivalence_digest(observation, case, receipt_digest, canonical, filter_object):
    """Reconstruct the raw A3 preimage and recompute the digest against STAGE-C's OWN authority.

    Repair 2A and 2B.  Every canonical field below comes from `canonical`, which
    stage_c_canonical_internal_policy() derived from this file's frozen constants.  A3's own
    declared canonical values are read only to be COMPARED against that reconstruction, and the
    captured filter addresses are required to be the ELF-qualified link-time addresses of the
    canonical objects.  A coordinated reseal of A3 and A4 therefore cannot choose its own authority:
    to pass it would have to produce a program that hashes to the digest Stage C derived, placed at
    the address the authenticated static analysis of the digest-proven image reports.
    """
    capture = case.get("internal_capture")
    baseline = case.get("seccomp_baseline")
    dump = case.get("dump_leg")
    if not isinstance(capture, dict) or not isinstance(baseline, dict) or not isinstance(dump, dict):
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "observation shape")

    # A3's DECLARED canonical values are claims.  They must equal Stage C's reconstruction before
    # anything else is considered, so a substituted policy identity fails with its own marker rather
    # than surfacing later as a confusing capture mismatch.
    declared_policy_id = require_str(observation.get("canonical_internal_policy_id"), "OBSERVATION_MALFORMED")
    declared_policy_digest = require_str(observation.get("canonical_internal_policy_sha256"), "OBSERVATION_MALFORMED")
    declared_count = require_int(
        observation.get("canonical_internal_cbpf_instruction_count"), "OBSERVATION_MALFORMED", 1, 512
    )
    declared_cbpf_digest = require_str(observation.get("canonical_internal_cbpf_sha256"), "OBSERVATION_MALFORMED")
    if declared_policy_id != canonical["policy_id"]:
        fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "policy id")
    if declared_policy_digest != canonical["policy_sha256"]:
        fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "policy digest")
    if declared_count != canonical["cbpf_instruction_count"]:
        fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "cbpf instruction count")
    if declared_cbpf_digest != canonical["cbpf_sha256"]:
        fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "cbpf digest")

    program_hex = require_str(capture.get("program_bytes_hex"), "OBSERVATION_MALFORMED")
    program_bytes = decode_hex(program_hex, "OBSERVATION_MALFORMED")
    available = dump.get("availability") == "AVAILABLE"
    record = {
        "schema": INTERNAL_EQUIVALENCE_SCHEMA,
        # STAGE-C AUTHORITY, not the record's own claim.  The equality above already proved the
        # record agrees; using the reconstruction here means the digest is anchored even if a future
        # edit weakened that equality.
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "program_representation_version": PROGRAM_REPRESENTATION_VERSION,
        "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "captured_internal_cbpf_sha256": cbpf_digest(program_bytes),
        "captured_internal_uargs_va_u64": require_int(capture.get("fprog_va_u64"), "OBSERVATION_MALFORMED", 0),
        "captured_internal_len_u32": require_int(capture.get("length"), "OBSERVATION_MALFORMED", 0, 512),
        "install_exit_return_i32": require_int(capture.get("install_return_i32"), "OBSERVATION_MALFORMED"),
        "baseline_supervisor_seccomp": require_int(baseline.get("supervisor_seccomp"), "OBSERVATION_MALFORMED", 0),
        "baseline_supervisor_filters": require_int(baseline.get("supervisor_filters"), "OBSERVATION_MALFORMED", 0),
        "baseline_child_seccomp": require_int(baseline.get("child_seccomp"), "OBSERVATION_MALFORMED", 0),
        "baseline_child_filters": require_int(baseline.get("child_filters"), "OBSERVATION_MALFORMED", 0),
        "pre_install_filters": require_int(baseline.get("outer_post_filters"), "OBSERVATION_MALFORMED", 0),
        "post_install_filters": require_int(baseline.get("internal_post_filters"), "OBSERVATION_MALFORMED", 0),
        "post_install_seccomp_mode": require_int(baseline.get("internal_post_seccomp"), "OBSERVATION_MALFORMED", 0),
        "revalidated_filters": require_int(baseline.get("revalidated_filters"), "OBSERVATION_MALFORMED", 0),
        "dump_leg_availability": require_str(dump.get("availability"), "OBSERVATION_MALFORMED"),
        "dump_leg_index0_sha256": cbpf_digest(decode_hex(dump.get("index0_bytes_hex", ""), "OBSERVATION_MALFORMED"))
        if available
        else "",
        "dump_leg_index1_sha256": cbpf_digest(decode_hex(dump.get("index1_bytes_hex", ""), "OBSERVATION_MALFORMED"))
        if available
        else "",
        "dump_leg_terminates_at_index": require_int(dump.get("terminates_at_index"), "OBSERVATION_MALFORMED", -1)
        if available
        else -1,
        "case_id": require_str(case.get("case_id"), "OBSERVATION_MALFORMED"),
        "source_run_id": require_int(observation.get("source_run_id"), "OBSERVATION_MALFORMED", 1),
        "source_run_attempt": require_int(observation.get("source_run_attempt"), "OBSERVATION_MALFORMED", 1),
        "source_head_sha": require_str(observation.get("source_head_sha"), "OBSERVATION_MALFORMED"),
        "candidate_binary_sha256": require_str(observation.get("candidate_binary_sha256"), "OBSERVATION_MALFORMED"),
    }
    if record["dump_leg_availability"] not in (DUMP_AVAILABLE, DUMP_UNAVAILABLE):
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "dump availability enum")
    for field, expected in INTERNAL_EQUIVALENCE_REQUIRED_VALUES.items():
        if record[field] != expected:
            fail("INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED", field)
    if record["captured_internal_cbpf_sha256"] != canonical["cbpf_sha256"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured differs from the Stage-C canonical program")
    if record["captured_internal_len_u32"] != canonical["cbpf_instruction_count"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured length differs from the Stage-C canonical count")
    if record["captured_internal_uargs_va_u64"] != filter_object["fprog_va_u64"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "uargs is not the ELF-qualified fprog address")
    captured_filter_va = require_int(capture.get("filter_va_u64"), "OBSERVATION_MALFORMED", 0)
    if captured_filter_va != filter_object["program_va_u64"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "filter is not the ELF-qualified program address")
    if available and record["dump_leg_index0_sha256"] != canonical["cbpf_sha256"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "dump index 0 differs from the Stage-C canonical program")

    recomputed = domain_digest(INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, record)
    equivalence = case.get("internal_filter_equivalence")
    if not isinstance(equivalence, dict):
        fail("OBSERVATION_MALFORMED", "equivalence block")
    a3_digest = require_str(equivalence.get("digest_sha256"), "OBSERVATION_MALFORMED")
    if a3_digest != recomputed:
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "A3 vs Stage C")
    if receipt_digest != recomputed:
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "A4 vs Stage C")
    return recomputed


# =================================================================================================
# SOURCE RUN BINDING (V9 SECTION 24) AND CANDIDATE/RECEIPT BINDING (V9 SECTION 25)
# =================================================================================================


def authenticate_source_run(api_url, repository, run_id, arguments):
    run = api_json(api_url, "/repos/" + repository + "/actions/runs/" + str(run_id))
    if not isinstance(run, dict):
        fail("SOURCE_RUN_MALFORMED")
    # run_attempt is NEVER taken from the event payload; the SERVICE response is the authority, and
    # its absence has no permissive fallback and no "assume attempt 1" path.
    if "run_attempt" not in run:
        fail("RUN_ATTEMPT_UNAVAILABLE")
    attempt = require_int(run.get("run_attempt"), "RUN_ATTEMPT_UNAVAILABLE", 1)
    if require_str(run.get("head_sha"), "SOURCE_RUN_MALFORMED") != arguments.expected_head_sha:
        fail("SOURCE_HEAD_MISMATCH")
    if require_str(run.get("head_branch"), "SOURCE_RUN_MALFORMED") != arguments.default_branch:
        fail("SOURCE_BRANCH_MISMATCH")
    if require_str(run.get("event"), "SOURCE_RUN_MALFORMED") != "workflow_dispatch":
        fail("SOURCE_EVENT_MISMATCH")
    if require_str(run.get("status"), "SOURCE_RUN_MALFORMED") != "completed":
        fail("SOURCE_RUN_NOT_COMPLETED")
    if require_str(run.get("conclusion"), "SOURCE_RUN_MALFORMED") != "success":
        fail("SOURCE_RUN_NOT_SUCCESSFUL")
    if require_str(run.get("path"), "SOURCE_RUN_MALFORMED") != arguments.expected_workflow_path:
        fail("SOURCE_WORKFLOW_PATH_MISMATCH")
    if require_str(run.get("name"), "SOURCE_RUN_MALFORMED") != arguments.expected_workflow_name:
        fail("SOURCE_WORKFLOW_NAME_MISMATCH")
    repository_block = run.get("repository")
    if not isinstance(repository_block, dict) or repository_block.get("full_name") != repository:
        fail("SOURCE_REPOSITORY_MISMATCH")
    return attempt


def authenticate_jobs(api_url, repository, run_id, attempt):
    jobs = enumerate_collection(
        api_url,
        "/repos/" + repository + "/actions/runs/" + str(run_id) + "/attempts/" + str(attempt) + "/jobs",
        "jobs",
        "attempt_jobs",
    )
    if jobs is None:
        # Falling back to the run-level jobs collection is FORBIDDEN: run-level jobs mix attempts and
        # would silently accept a job from a previous attempt.
        fail("ATTEMPT_JOBS_UNAVAILABLE")
    # REPAIR 4: the identity invariants are proven BEFORE anything keyed by name is built, so a
    # duplicate can never be normalised away by the map that would have held it.
    names = [require_str(job.get("name"), "JOB_RECORD_MALFORMED") for job in jobs]
    governed = [name for name in names if name in REQUIRED_JOBS]
    if len(set(governed)) != len(governed):
        fail("REQUIRED_JOB_DUPLICATE")
    for required in REQUIRED_JOBS:
        occurrences = names.count(required)
        if occurrences == 0:
            fail("REQUIRED_JOB_MISSING", required)
        if occurrences > 1:
            fail("REQUIRED_JOB_DUPLICATE", required)
    if len(governed) != len(REQUIRED_JOBS):
        fail("REQUIRED_JOB_MISSING", "governed job count")
    for job in jobs:
        if job.get("name") in REQUIRED_JOBS and job.get("conclusion") != "success":
            fail("REQUIRED_JOB_NOT_SUCCESSFUL")
    return jobs


def select_artifacts(api_url, repository, run_id):
    artifacts = enumerate_collection(
        api_url,
        "/repos/" + repository + "/actions/runs/" + str(run_id) + "/artifacts",
        "artifacts",
        "run_artifacts",
    )
    # REPAIR 4: the expected NAMES are validated as a list first -- exact count, uniqueness, exact
    # set -- and only then is the keyed map built.  Assigning into a dictionary as you go lets a
    # duplicate overwrite its predecessor before any rule has looked at it.
    governed = [
        artifact
        for artifact in artifacts
        if require_str(artifact.get("name"), "ARTIFACT_RECORD_MALFORMED") in EXPECTED_ARTIFACT_SET
    ]
    governed_names = [artifact["name"] for artifact in governed]
    if len(set(governed_names)) != len(governed_names):
        fail("DUPLICATE_EXPECTED_ARTIFACT_NAME")
    if len(governed_names) != len(EXPECTED_ARTIFACT_SET):
        fail("EXPECTED_ARTIFACT_MISSING", "governed artifact count")
    if sorted(governed_names) != sorted(EXPECTED_ARTIFACT_SET):
        fail("EXPECTED_ARTIFACT_MISSING", "governed artifact set")

    selected = {}
    service_ids = []
    for artifact in governed:
        name = artifact["name"]
        if artifact.get("expired") is True:
            fail("EXPIRED_ARTIFACT")
        if name in selected:
            # Unreachable once the list-level uniqueness rule above holds; kept as the assertion
            # that the map construction itself never resolves a collision.
            fail("DUPLICATE_EXPECTED_ARTIFACT_NAME")
        selected[name] = artifact
        # Every expected artifact must carry a well-formed service id.  Uniqueness ACROSS the whole
        # enumeration is already owned by the pagination layer's repeated-record rule (P5), which
        # sees every record rather than only the expected ones, so it is not restated here: a second
        # rule that can never fire is not defence in depth, it is dead code.
        service_ids.append(require_int(artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1))
    for name in EXPECTED_ARTIFACT_SET:
        if name not in selected:
            fail("EXPECTED_ARTIFACT_MISSING")
    return selected


def normalise_archive_digest(value):
    """Canonicalise the artifact ARCHIVE digest to sha256:<64 hex>."""
    text = require_str(value, "ARTIFACT_DIGEST_MALFORMED").strip().lower()
    if text.startswith("sha256:"):
        text = text[len("sha256:") :]
    if not is_hex64(text):
        fail("ARTIFACT_DIGEST_MALFORMED")
    return "sha256:" + text


# =================================================================================================
# THE GATE
# =================================================================================================


def run_gate(arguments):
    api_url = arguments.api_url
    repository = arguments.repository
    run_id = arguments.source_run_id

    # --- SOURCE_RUN_AUTHENTICATED -> RUN_ATTEMPT_AUTHENTICATED ---
    attempt = authenticate_source_run(api_url, repository, run_id, arguments)

    # --- EXPECTED_JOBS_AUTHENTICATED -> JOBS_TOTAL_COUNT_RECONCILED ---
    authenticate_jobs(api_url, repository, run_id, attempt)

    # --- COMPLETE_ARTIFACT_ENUMERATION_PROVEN -> ARTIFACTS_TOTAL_COUNT_RECONCILED ---
    # --- -> UNIQUE_EXPECTED_ARTIFACTS_SELECTED ---
    artifacts = select_artifacts(api_url, repository, run_id)

    # --- CANDIDATE_SERVICE_IDENTITY_AUTHENTICATED / RECEIPT_SERVICE_IDENTITY_AUTHENTICATED ---
    payloads = {}
    member_digests = {}
    for name in EXPECTED_ARTIFACT_SET:
        artifact = artifacts[name]
        artifact_id = require_int(artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1)
        payload = download_artifact(api_url, repository, artifact_id)
        contents, digests = extract_artifact(payload, EXPECTED_MEMBERS[name])
        payloads[name] = contents
        member_digests[name] = digests

    manifest = decode_json(payloads[CANDIDATE_ARTIFACT][BUILD_MANIFEST_MEMBER], "BUILD_MANIFEST_MALFORMED")
    elf_record = decode_json(payloads[ELF_ARTIFACT][ELF_RECORD_MEMBER], "ELF_RECORD_MALFORMED")
    observation = decode_json(payloads[OBSERVATION_ARTIFACT][OBSERVATION_MEMBER], "OBSERVATION_MALFORMED")
    receipt = decode_json(payloads[RECEIPT_ARTIFACT][RECEIPT_MEMBER], "RECEIPT_MALFORMED")
    for record, marker in (
        (manifest, "BUILD_MANIFEST_MALFORMED"),
        (elf_record, "ELF_RECORD_MALFORMED"),
        (observation, "OBSERVATION_MALFORMED"),
        (receipt, "RECEIPT_MALFORMED"),
    ):
        if not isinstance(record, dict):
            fail(marker, "document type")

    # --- CONTENT_DIGESTS_REDERIVED ---
    worker_digest = member_digests[CANDIDATE_ARTIFACT][WORKER_BINARY_MEMBER]
    if manifest.get("worker_binary_sha256") != worker_digest:
        fail("CANDIDATE_IDENTITY_MISMATCH", "manifest vs recomputed binary digest")
    if elf_record.get("candidate_binary_sha256") != worker_digest:
        fail("CANDIDATE_IDENTITY_MISMATCH", "elf record")
    if observation.get("candidate_binary_sha256") != worker_digest:
        fail("CANDIDATE_IDENTITY_MISMATCH", "observation record")
    if receipt.get("worker_binary_sha256") != worker_digest:
        fail("CANDIDATE_IDENTITY_MISMATCH", "receipt")

    # --- no cross-run and no cross-attempt mixing ---
    for record, label in ((manifest, "manifest"), (observation, "observation"), (receipt, "receipt")):
        if require_int(record.get("source_run_id"), "RUN_ATTEMPT_MISMATCH", 1) != run_id:
            fail("RUN_ATTEMPT_MISMATCH", "run id")
        if require_int(record.get("source_run_attempt"), "RUN_ATTEMPT_MISMATCH", 1) != attempt:
            fail("RUN_ATTEMPT_MISMATCH", "run attempt")
        if require_str(record.get("source_head_sha"), "SOURCE_HEAD_MISMATCH") != arguments.expected_head_sha:
            fail("SOURCE_HEAD_MISMATCH", label)

    # --- the receipt's CANDIDATE service claims are cross-checked; its own id is not claimed ---
    candidate_artifact = artifacts[CANDIDATE_ARTIFACT]
    if require_int(receipt.get("candidate_artifact_id"), "RECEIPT_BINDING_MISMATCH", 1) != require_int(
        candidate_artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1
    ):
        fail("RECEIPT_BINDING_MISMATCH", "candidate artifact id")
    if normalise_archive_digest(receipt.get("candidate_artifact_archive_digest")) != normalise_archive_digest(
        candidate_artifact.get("digest")
    ):
        fail("RECEIPT_BINDING_MISMATCH", "candidate archive digest")
    if "receipt_artifact_id" in receipt:
        fail("RECEIPT_BINDING_MISMATCH", "the receipt must not claim its own artifact id")
    if "receipt_artifact_archive_digest" in receipt:
        fail("RECEIPT_BINDING_MISMATCH", "the receipt must not claim its own archive digest")

    # --- A5 RECEIPT CUSTODY IDENTITY (repair 1D) ---
    #
    # The receipt's own service identity CANNOT come from the receipt: that id does not exist until
    # after upload.  Stage C therefore takes it from the authenticated artifact enumeration, and
    # binds the candidate and the receipt to ONE run: two artifacts produced by different runs, or
    # an artifact whose service record points at another run, break the pairing.
    receipt_artifact = artifacts[RECEIPT_ARTIFACT]
    receipt_artifact_id = require_int(receipt_artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1)
    receipt_archive_digest = normalise_archive_digest(receipt_artifact.get("digest"))
    if not receipt_archive_digest:
        fail("RECEIPT_BINDING_MISMATCH", "receipt archive digest")
    if receipt_artifact_id == require_int(candidate_artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1):
        fail("RECEIPT_BINDING_MISMATCH", "candidate and receipt share a service id")
    for name in EXPECTED_ARTIFACT_SET:
        record = artifacts[name]
        owner = record.get("workflow_run")
        if not isinstance(owner, dict):
            fail("RECEIPT_BINDING_MISMATCH", "artifact carries no owning run")
        if require_int(owner.get("id"), "RUN_ATTEMPT_MISMATCH", 1) != run_id:
            fail("RUN_ATTEMPT_MISMATCH", "artifact belongs to a different run")
        if require_str(owner.get("head_sha"), "SOURCE_HEAD_MISMATCH") != arguments.expected_head_sha:
            fail("SOURCE_HEAD_MISMATCH", "artifact owning run head")

    # --- SOURCE_BUNDLE_DIGEST_AUTHENTICATED ---
    bundle_payload = _load_bounded_json(arguments.source_bundle_inventory, "source bundle inventory")
    bundle_digest, bundle_entries = recompute_source_bundle_digest(bundle_payload)
    if bundle_digest != arguments.approved_source_bundle_sha256:
        fail("SOURCE_BUNDLE_DIGEST_NOT_APPROVED")

    # --- the qualification workflow BYTES at the source head ---
    workflow_entry = [entry for entry in bundle_entries if entry["path"] == arguments.expected_workflow_path]
    if len(workflow_entry) != 1:
        fail("QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED", "workflow is not a bundle entry")
    if workflow_entry[0]["sha256"] != arguments.approved_qualification_workflow_sha256:
        fail("QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED")

    # --- COMPILE_DEPENDENCY_INVENTORY_AUTHENTICATED ---
    dependency_payload = _load_bounded_json(arguments.compile_dependency_inventory, "compile dependency inventory")
    dependency_digest = recompute_dependency_inventory_digest(dependency_payload, bundle_entries)
    if manifest.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "manifest")
    if elf_record.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "elf record")
    if receipt.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "receipt")

    # --- ACTUAL_COMPILE_LINK_INSTANCES_AUTHENTICATED (repair 8A, 8B, 8C, 8E) ---
    instance_payload = _load_bounded_json(arguments.compile_instance_inventory, "compile instance inventory")
    instance_digest = recompute_compile_instance_digest(instance_payload)
    if manifest.get("compile_instance_inventory_digest_sha256") != instance_digest:
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "manifest")
    if manifest.get("compile_instance_inventory_schema") != COMPILE_INSTANCE_SCHEMA:
        fail("COMPILE_INSTANCE_INVENTORY_MISMATCH", "manifest schema")
    # REPAIR 11: the system libraries the links actually resolved.
    validate_system_libraries(instance_payload)
    # REPAIR 10: the COMPLETE graph, from the union of all three job logs.
    build_graph_size = require_complete_build_graph(
        instance_payload,
        decode_json(payloads[OBSERVATION_ARTIFACT][OBSERVE_INSTANCE_MEMBER], "BUILD_GRAPH_INCOMPLETE"),
        decode_json(payloads[RECEIPT_ARTIFACT][ADJUDICATE_INSTANCE_MEMBER], "BUILD_GRAPH_INCOMPLETE"),
    )

    # --- PINNED_UPSTREAM_IDENTITY_BOUND (repair 8D) ---
    upstream = bind_pinned_upstream_identity(manifest)

    # --- QUALIFICATION_DIGESTS_BOUND ---
    #
    # Repair 1B: the A2 digest is RECOMPUTED from A2's own canonical record, and A2, A4 and the
    # recomputation must all agree.  A2 == A4 alone proved only that one unprivileged job was
    # self-consistent.
    validate_a2_schema(elf_record)
    elf_digest = recompute_elf_record_digest(elf_record)
    if receipt.get("elf_qualification_digest_sha256") != elf_digest:
        fail("ELF_QUALIFICATION_DIGEST_MISMATCH", "A4 vs Stage C")
    # REPAIR 3: the protocol-conformance AGGREGATE leaves the trusted chain, and a real anchor
    # takes its place.
    #
    # WHY IT CANNOT BE RECOMPUTED.  The protocol record is mostly frozen constants -- the V5 wire
    # layout, both taxonomies, the validation order, the exit codes, the case-id order -- but its
    # digest also covers fixture_material_state and the two generator digests, which Stage C never
    # downloads and has no authority over.  A syntactic hex check on a producer-selected value is
    # not authority, and copying it into the trusted predicate gave it a standing it never earned.
    #
    # WHAT REPLACES IT.  The record's only run-varying anchors that matter are the FIXTURE identity
    # and the case plan derived from it, and Stage C can prove the first outright: the governed
    # TEST-ONLY fixture is bundle entry 16, so its committed digest is already in the source-bundle
    # inventory Stage C recomputes from the git object store at the proven source head.  V9
    # SECTION 25 requires these to bind to ONE run identity, and that is what the checks below do.
    fixture_entry = [entry for entry in bundle_entries if entry["path"] == GOVERNED_FIXTURE_PATH]
    if len(fixture_entry) != 1:
        fail("FIXTURE_IDENTITY_UNBOUND", "fixture is not a bundle entry")
    fixture_digest = fixture_entry[0]["sha256"]
    for record, label in ((observation, "A3"), (receipt, "A4")):
        if require_str(record.get("fixture_sha256"), "FIXTURE_IDENTITY_UNBOUND") != fixture_digest:
            fail("FIXTURE_IDENTITY_UNBOUND", label + " fixture digest")
    # CONTROLLER REPAIR 6 (option D): case_plan_sha256 is NOT trusted authority and is no longer
    # read, compared or emitted.
    #
    # V9 SECTION 25 lists seventeen bindings that must agree on one authenticated run identity; a
    # case-plan digest is not one of them, and the token case_plan does not appear anywhere in V9.
    # What the gate used to do here was require A3 and A4 to agree -- which is not authority at all,
    # because both are unprivileged producer records and two of them can agree on any value they
    # like.  A false digest satisfying that check then entered the trusted predicate.
    #
    # Removing it costs nothing that was ever proven.  build_case_plan is a pure function of frozen
    # constants and the governed fixture bytes, and BOTH are independently anchored here already:
    # the fixture by its committed bundle-entry-16 digest recomputed from the git object store just
    # above, and the case set by the frozen 25-case inventory and the reconstructed case-set digest.
    # The primitive properties remain the authority; the aggregate was only ever a restatement.
    # REPAIR 2B: the sandbox-policy AGGREGATE leaves the trust chain.
    #
    # It is a digest over the whole unprivileged sandbox-policy record, INCLUDING that record's own
    # mutant matrix, so Stage C cannot reconstruct it from anything it independently knows.  A
    # shape check on a producer-supplied 64-hex value is not authority, and copying it into the
    # trusted predicate gave it a standing it never earned.  The properties it was standing in for
    # ARE independently established elsewhere: both canonical policies, both cBPF programs and both
    # governed digests are reconstructed by Stage C and required to match A3 and A4 exactly.  The
    # field is therefore no longer read, no longer compared and no longer emitted.

    # --- STAGE_C_SELF_ANCHORED_AUTHORITY_RECONSTRUCTED (repair 1A, 1C, 2A, 2B, 2C) ---
    #
    # Everything Stage C is about to require is derived HERE, before a single claimed value is read.
    # A3 and A4 are then compared against it.  Nothing below adopts an expected value from either.
    canonical = stage_c_canonical_internal_policy()
    outer_canonical = stage_c_canonical_outer_policy()
    # REPAIR 1B: the worker ELF is parsed from the AUTHENTICATED CANDIDATE BYTES, and A2 is then
    # required to agree with that reconstruction.  A2 no longer supplies any expected coordinate.
    reconstructed = stage_c_reconstruct_worker_authority(
        payloads[CANDIDATE_ARTIFACT][WORKER_BINARY_MEMBER], canonical, outer_canonical
    )
    filter_object = bind_a2_to_reconstruction(elf_record, reconstructed)
    validate_a4_policy_authority(receipt, canonical, outer_canonical)
    case_set_digest = stage_c_case_set_digest()

    # Repair 1C: A3's and A4's TOP-LEVEL policy and cBPF claims are compared against Stage C's own
    # reconstruction of BOTH policies.  Neither record supplies an expected value.
    for record, label in ((observation, "A3"),):
        if record.get("canonical_internal_policy_id") != canonical["policy_id"]:
            fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", label + " internal policy id")
        if record.get("canonical_internal_policy_sha256") != canonical["policy_sha256"]:
            fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", label + " internal policy digest")
        if record.get("canonical_internal_cbpf_sha256") != canonical["cbpf_sha256"]:
            fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", label + " internal cbpf digest")
        if record.get("outer_containment_policy_digest_sha256") != outer_canonical["governed_sha256"]:
            fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", label + " outer governed digest")
    if (
        require_int(observation.get("canonical_internal_cbpf_instruction_count"), "OBSERVATION_MALFORMED", 1, 512)
        != canonical["cbpf_instruction_count"]
    ):
        fail("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", "A3 internal cbpf instruction count")

    # --- ENVIRONMENT_DIGESTS_BOUND ---
    # The outer policy digest is now recomputed above rather than cross-compared, so A3 == A4 here
    # is a consequence rather than the proof.
    # The case-set digest is RECOMPUTED, not merely cross-compared.  A3 == A4 proves only that the
    # unprivileged job agreed with itself about which 25 cases it claims to have run.
    if observation.get("observation_case_set_digest_sha256") != case_set_digest:
        fail("OBSERVATION_CASE_SET_DIGEST_MISMATCH", "A3 vs Stage C")
    if receipt.get("observation_case_set_digest_sha256") != case_set_digest:
        fail("OBSERVATION_CASE_SET_DIGEST_MISMATCH", "A4 vs Stage C")

    cases = observation.get("cases")
    if not isinstance(cases, list) or len(cases) != EXACT_CASE_COUNT:
        fail("OBSERVATION_CASE_COUNT_MISMATCH")
    if require_int(receipt.get("case_count"), "OBSERVATION_CASE_COUNT_MISMATCH", 0) != EXACT_CASE_COUNT:
        fail("OBSERVATION_CASE_COUNT_MISMATCH", "receipt")

    # The observed case identities must be EXACTLY the canonical inventory, in canonical order.  A
    # duplicate, a missing id, an extra id or a reordering each fails with its own marker, and none
    # of them is allowed to be normalised away by building a map first.
    observed_ids = []
    for case in cases:
        if not isinstance(case, dict):
            fail("OBSERVATION_MALFORMED", "case type")
        observed_ids.append(require_str(case.get("case_id"), "OBSERVATION_MALFORMED"))
    if len(set(observed_ids)) != len(observed_ids):
        fail("OBSERVATION_CASE_DUPLICATE")
    for identifier in TRUSTED_CASE_IDS:
        if identifier not in observed_ids:
            fail("OBSERVATION_CASE_MISSING")
    for identifier in observed_ids:
        if identifier not in TRUSTED_CASE_IDS:
            fail("OBSERVATION_CASE_UNKNOWN")
    if tuple(observed_ids) != TRUSTED_CASE_IDS:
        fail("OBSERVATION_CASE_ORDER_MISMATCH")

    # Repair 2D.  A keyed map built by assignment lets a duplicate id silently overwrite its
    # predecessor, so the count and the identity set are proven BEFORE the map exists.
    claimed = receipt.get("internal_filter_equivalence_digests")
    if not isinstance(claimed, list) or len(claimed) != EXACT_CASE_COUNT:
        fail("RECEIPT_BINDING_MISMATCH", "equivalence digest count")
    claimed_ids = []
    receipt_digests = {}
    for item in claimed:
        if not isinstance(item, dict):
            fail("RECEIPT_BINDING_MISMATCH", "equivalence digest shape")
        identifier = require_str(item.get("case_id"), "RECEIPT_BINDING_MISMATCH")
        claimed_ids.append(identifier)
        if identifier in receipt_digests:
            fail("RECEIPT_DUPLICATE_CASE_IDENTITY")
        receipt_digests[identifier] = require_str(item.get("digest_sha256"), "RECEIPT_BINDING_MISMATCH")
    if tuple(claimed_ids) != TRUSTED_CASE_IDS:
        fail("RECEIPT_BINDING_MISMATCH", "equivalence digest identity order")

    # Repair 4.  EVERY case binds the same filter-equivalence authority.  The internal filter is
    # installed during candidate bootstrap, BEFORE any stimulus is consumed, so a case that ends in
    # a signal or a deadline has exactly the same installation evidence as one that answers a frame.
    # Letting the two process cases carry an empty sentinel gave them an unbound trust path and made
    # A3 and A4 disagree by construction; there is no empty-digest branch here any more.
    recomputed = []
    for case in cases:
        equivalence = case.get("internal_filter_equivalence")
        if not isinstance(equivalence, dict):
            fail("OBSERVATION_MALFORMED", "equivalence block")
        if not equivalence.get("valid"):
            fail(
                "INTERNAL_FILTER_EQUIVALENCE_FAILED",
                "absent for " + require_str(case.get("case_id"), "OBSERVATION_MALFORMED"),
            )
        case_id = require_str(case.get("case_id"), "OBSERVATION_MALFORMED")
        # REPAIR 2: the observed OUTER program is bound to the Stage-C reconstruction too, so a
        # synthetic A3/A4 pair cannot invent its own outer authority.
        bind_observed_outer_program(case, outer_canonical)
        digest = stage_c_equivalence_digest(observation, case, receipt_digests[case_id], canonical, filter_object)
        if not is_hex64(digest):
            fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "digest shape")
        recomputed.append({"case_id": case_id, "digest_sha256": digest})
    if len(recomputed) != EXACT_CASE_COUNT:
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "recomputed count")

    if not receipt.get("all_cases_conform"):
        fail("QUALIFICATION_NOT_CONFORMANT")
    if receipt.get("evidence_status") != "ADMISSION_EVIDENCE_ONLY":
        fail("RECEIPT_IS_EVIDENCE_ONLY", "evidence_status")
    if receipt.get("governed_worker_row_created") is not False:
        fail("ACTIVE_ROW_FORBIDDEN_IN_P0")

    predicate = {
        "schema": STAGE_C_PREDICATE_SCHEMA,
        "platform_id": PLATFORM_ID,
        "repository": repository,
        "source_run_id": run_id,
        "source_run_attempt": attempt,
        "source_head_sha": arguments.expected_head_sha,
        "source_branch": arguments.default_branch,
        "qualification_workflow_path": arguments.expected_workflow_path,
        "qualification_workflow_sha256": arguments.approved_qualification_workflow_sha256,
        "qualification_source_bundle_sha256": bundle_digest,
        "compile_dependency_inventory_digest_sha256": dependency_digest,
        "compile_instance_inventory_digest_sha256": instance_digest,
        "build_graph_instance_count": build_graph_size,
        "pinned_upstream_commit": upstream["upstream_commit"],
        "pinned_upstream_source_tree_digest": upstream["upstream_source_tree_digest"],
        "pinned_upstream_per_file_digests_verified": upstream["pinned_upstream_per_file_digests_verified"],
        "worker_binary_sha256": worker_digest,
        "candidate_artifact_id": require_int(candidate_artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1),
        "candidate_artifact_archive_digest": normalise_archive_digest(candidate_artifact.get("digest")),
        "receipt_artifact_id": receipt_artifact_id,
        "receipt_artifact_archive_digest": receipt_archive_digest,
        "build_manifest_sha256": member_digests[CANDIDATE_ARTIFACT][BUILD_MANIFEST_MEMBER],
        "elf_qualification_digest_sha256": elf_digest,
        "governed_fixture_sha256": fixture_digest,
        "outer_containment_policy_digest_sha256": outer_canonical["governed_sha256"],
        "canonical_outer_policy_id": outer_canonical["policy_id"],
        "canonical_outer_cbpf_sha256": outer_canonical["cbpf_sha256"],
        "observation_case_set_digest_sha256": case_set_digest,
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "canonical_internal_filter_fprog_va_u64": filter_object["fprog_va_u64"],
        "canonical_internal_filter_program_va_u64": filter_object["program_va_u64"],
        "internal_filter_equivalence_digests": recomputed,
        "case_count": EXACT_CASE_COUNT,
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "admission": "NONE",
        "authority_non_transition": {
            "machine_time_authority": "NONE",
            "mt5_mt6_authority": "NONE",
            "stage4_authority": "NONE",
            "readiness_transition": "NONE",
            "connector_transition": "NONE",
            "product_native_execution": "NO",
            "custody_artifact": "NONE",
            "governed_worker_row_created": False,
        },
    }
    predicate["trusted_predicate_digest_sha256"] = domain_digest(STAGE_C_PREDICATE_DIGEST_DOMAIN, predicate)
    return predicate


def build_parser():
    parser = argparse.ArgumentParser(description="MT4-S3C trusted default-branch attestation gate")
    parser.add_argument("--workspace-root", required=True)
    parser.add_argument("--trusted-entrypoint", action="append", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-run-id", required=True, type=int)
    parser.add_argument("--expected-head-sha", required=True)
    parser.add_argument("--expected-workflow-path", required=True)
    parser.add_argument("--expected-workflow-name", required=True)
    parser.add_argument("--approved-qualification-workflow-sha256", required=True)
    parser.add_argument("--approved-source-bundle-sha256", required=True)
    parser.add_argument("--source-bundle-inventory", required=True)
    parser.add_argument("--compile-dependency-inventory", required=True)
    parser.add_argument("--compile-instance-inventory", required=True)
    parser.add_argument("--default-branch", required=True)
    parser.add_argument("--out", required=True)
    return parser


def main(argv=None):
    arguments = build_parser().parse_args(argv)

    # S-6: the attestation is REPEATED immediately before the first byte of untrusted content is
    # parsed, so a module imported lazily between startup and use is also covered.  Both runs must
    # pass; this is the second.
    _validate_module_origins(_APPROVED_STDLIB_ROOTS, _WORKSPACE_ROOT, _SCRATCH_ROOT, _DECLARED_ENTRYPOINTS)
    _environment_attestation()

    # Presence only.  The value itself is never bound here: it is read, used and discarded
    # inside _authorization_header, which is the only function that ever sees it.
    if not os.environ.get("GITHUB_TOKEN"):
        fail("CREDENTIAL_UNAVAILABLE")

    predicate = run_gate(arguments)
    output = pathlib.Path(arguments.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(canonical_json(predicate))
    sys.stdout.write("MT4_S3C_TRUSTED_PREDICATE_DIGEST=" + predicate["trusted_predicate_digest_sha256"] + "\n")
    sys.stdout.write("MT4_S3C_TRUSTED_GATE_RESULT=PASS\n")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except TrustedGateError as error:
        sys.stderr.write("MT4_S3C_TRUSTED_GATE_FAILED=" + str(error) + "\n")
        raise SystemExit(1) from None
