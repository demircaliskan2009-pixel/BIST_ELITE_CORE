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

# EXPECTED MEMBER COUNTS, exact per artifact class (V9 27.2).  Not "at most".
EXPECTED_MEMBERS = {
    CANDIDATE_ARTIFACT: (WORKER_BINARY_MEMBER, BUILD_MANIFEST_MEMBER),
    ELF_ARTIFACT: (ELF_RECORD_MEMBER,),
    OBSERVATION_ARTIFACT: (OBSERVATION_MEMBER,),
    RECEIPT_ARTIFACT: (RECEIPT_MEMBER,),
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

CANONICAL_INTERNAL_CBPF_INSTRUCTION_COUNT = 113

# The reconstruction below must reproduce these exactly.  They are asserted at import time, so a
# drift in the emitter or in any frozen constant is a hard failure of the gate itself rather than a
# silently different expectation.
EXPECTED_INTERNAL_POLICY_SHA256 = "ba8b6ca197472a8dada2d703d879bb104ebc73089de621f8695daf52795154d4"
EXPECTED_INTERNAL_CBPF_SHA256 = "dd044cda4588d641f6c57a27a64fb8d09eaf15ac7eb86622c047a2b4b4bf9d6d"
EXPECTED_INTERNAL_PROGRAM_BYTES_SHA256 = "129a4ee7f0265f0d150e7466b298b728d6572f73206fc0fc59f5f1459ed26cb6"

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


def _derive_internal_program():
    """Reconstruct the canonical internal classic-BPF program from the frozen constants alone."""
    out = []
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_OFFSET_ARCH, 0, 0))
    out.append((TRUSTED_OPCODE_JEQ_K, TRUSTED_AUDIT_ARCH_X86_64, 1, 0))
    out.append(("JA", "KILL"))
    out.append((TRUSTED_OPCODE_LD_W_ABS, TRUSTED_OFFSET_NR, 0, 0))
    out.append((TRUSTED_OPCODE_JGE_K, TRUSTED_X32_SYSCALL_BIT, 0, 1))
    out.append(("JA", "KILL"))

    for position, (name, number, _reason, rules) in enumerate(_TRUSTED_INTERNAL_INVENTORY):
        last_entry = position + 1 == len(_TRUSTED_INTERNAL_INVENTORY)
        next_entry = "KILL" if last_entry else (_TRUSTED_INTERNAL_INVENTORY[position + 1][0], "ENTRY")
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


def _derive_internal_semantic_preimage():
    """Reconstruct the canonical semantic policy document -- the POLICY BYTES, not just a digest."""
    entries = []
    for name, number, reason, rules in _TRUSTED_INTERNAL_INVENTORY:
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
        "schema": INTERNAL_POLICY_SCHEMA,
        "policy_domain": CANONICAL_INTERNAL_POLICY_ID,
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


def stage_c_canonical_internal_policy():
    """The Stage-C canonical internal policy: bytes, digests and program, all self-derived."""
    semantic = _derive_internal_semantic_preimage()
    semantic_bytes = canonical_json(semantic)
    program_bytes = _derive_internal_program()
    instruction_count = len(program_bytes) // 8
    if instruction_count != CANONICAL_INTERNAL_CBPF_INSTRUCTION_COUNT:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "instruction count")
    canonical = {
        "policy_id": CANONICAL_INTERNAL_POLICY_ID,
        "semantic_bytes": semantic_bytes,
        "policy_sha256": hashlib.sha256(INTERNAL_POLICY_DIGEST_DOMAIN + semantic_bytes).hexdigest(),
        "cbpf_instruction_count": instruction_count,
        "cbpf_program_bytes": program_bytes,
        "cbpf_sha256": cbpf_digest(program_bytes),
        "program_bytes_sha256": hashlib.sha256(program_bytes).hexdigest(),
    }
    # Drift in any frozen constant or in the emitter is a failure of THIS file, not of the candidate.
    if canonical["policy_sha256"] != EXPECTED_INTERNAL_POLICY_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "policy digest")
    if canonical["cbpf_sha256"] != EXPECTED_INTERNAL_CBPF_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "cbpf digest")
    if canonical["program_bytes_sha256"] != EXPECTED_INTERNAL_PROGRAM_BYTES_SHA256:
        fail("STAGE_C_CANONICAL_POLICY_DERIVATION_FAILED", "program bytes digest")
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


def stage_c_validate_filter_object(elf_record, canonical):
    """Bind the ELF-qualified canonical filter objects, and prove they ARE the canonical program.

    Repair 2B.  A captured address is accepted only when the AUTHENTICATED static analysis of the
    same digest-proven image places the canonical objects there, and only when the object the ELF
    record describes at that address carries exactly the canonical instruction count and exactly the
    canonical program bytes.  Hashing captured bytes correctly is not enough on its own: without
    this binding an arbitrary stack or heap address holding a copy would satisfy the digest.
    """
    objects = elf_record.get("canonical_internal_filter_object")
    if not isinstance(objects, dict):
        fail("FILTER_OBJECT_BINDING_INVALID", "missing object block")
    if objects.get("fprog_symbol") != INTERNAL_FPROG_SYMBOL:
        fail("FILTER_OBJECT_BINDING_INVALID", "fprog symbol")
    if objects.get("program_symbol") != INTERNAL_PROGRAM_SYMBOL:
        fail("FILTER_OBJECT_BINDING_INVALID", "program symbol")
    if require_int(objects.get("fprog_size_bytes"), "FILTER_OBJECT_BINDING_INVALID", 0) != INTERNAL_FPROG_SIZE_BYTES:
        fail("FILTER_OBJECT_BINDING_INVALID", "fprog size")
    if (
        require_int(objects.get("program_size_bytes"), "FILTER_OBJECT_BINDING_INVALID", 0)
        != INTERNAL_PROGRAM_SIZE_BYTES
    ):
        fail("FILTER_OBJECT_BINDING_INVALID", "program size")
    if (
        require_int(objects.get("program_instruction_count"), "FILTER_OBJECT_BINDING_INVALID", 0)
        != canonical["cbpf_instruction_count"]
    ):
        fail("FILTER_OBJECT_BINDING_INVALID", "program instruction count")
    if objects.get("program_bytes_sha256") != canonical["program_bytes_sha256"]:
        fail("FILTER_OBJECT_BINDING_INVALID", "program bytes are not the canonical program")
    fprog_va = require_int(objects.get("fprog_va_u64"), "FILTER_OBJECT_BINDING_INVALID", 1)
    program_va = require_int(objects.get("program_va_u64"), "FILTER_OBJECT_BINDING_INVALID", 1)
    for key in ("fprog_file_offset_u64", "program_file_offset_u64"):
        require_int(objects.get(key), "FILTER_OBJECT_BINDING_INVALID", 0)
    for key in ("fprog_segment_flags_u32", "program_segment_flags_u32"):
        flags = require_int(objects.get(key), "FILTER_OBJECT_BINDING_INVALID", 0, 0xFFFFFFFF)
        if flags & PF_W:
            fail("FILTER_OBJECT_BINDING_INVALID", "writable filter mapping")
        if not flags & PF_R:
            fail("FILTER_OBJECT_BINDING_INVALID", "unreadable filter mapping")
    return {"fprog_va_u64": fprog_va, "program_va_u64": program_va}


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


def _load_bounded_json(path, description):
    """Read one locally supplied JSON document under the governed local-input bound."""
    with open(path, "rb") as handle:
        body = handle.read(MAX_LOCAL_INPUT_BYTES + 1)
    if len(body) > MAX_LOCAL_INPUT_BYTES:
        fail("LOCAL_INPUT_BOUND_EXCEEDED", description)
    try:
        return json.loads(body.decode("utf-8"))
    except ValueError:
        fail("LOCAL_INPUT_MALFORMED", description)
    return None


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


def decode_json(body, marker):
    """Decode one UNTRUSTED JSON document.  No exception text ever escapes."""
    if not isinstance(body, (bytes, bytearray)):
        fail(marker, "body type")
    try:
        decoded = bytes(body).decode("utf-8")
    except UnicodeDecodeError:
        fail(marker, "not valid utf-8")
        return None
    try:
        return json.loads(decoded)
    except ValueError:
        fail(marker, "not valid json")
    return None


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
    except urllib.error.HTTPError as error:
        fail("GITHUB_API_FAILED", path + " status " + str(error.code))
    except urllib.error.URLError:
        fail("GITHUB_API_FAILED", path)
    if body is None or len(body) > MAX_API_RESPONSE_BYTES:
        fail("GITHUB_API_RESPONSE_BOUND_EXCEEDED", path)
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
                fail("PAGINATION_REPEATED_RECORD", endpoint_name + " id " + str(identifier))
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
            fail("ARTIFACT_REDIRECT_FAILED", str(artifact_id))
        location = error.headers.get("Location")
        error.close()
    except urllib.error.URLError:
        fail("ARTIFACT_REDIRECT_FAILED", str(artifact_id))
    else:
        with response:
            if response.getcode() not in REDIRECT_STATUS_CODES:
                fail("ARTIFACT_REDIRECT_REQUIRED", str(artifact_id))
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
        fail("ARTIFACT_DOWNLOAD_FAILED", str(artifact_id))
    except urllib.error.URLError:
        fail("ARTIFACT_DOWNLOAD_FAILED", str(artifact_id))
    # Z1 is enforced again below from the central directory; this bound stops the read itself.
    if len(payload) > MAX_ARCHIVE_BYTES:
        fail("ZIP_ARCHIVE_BYTES", str(artifact_id))
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
        fail("ZIP_ARCHIVE_BYTES", str(len(payload)))  # Z1
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(infos) != len(expected_members):
        fail("ZIP_MEMBER_COUNT", str(len(infos)))  # Z2
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
        fail("ZIP_DECLARED_AGGREGATE", str(aggregate_declared))  # Z12
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
                consumed_compressed += len(chunk)
                pending = chunk
            produced = decompressor.decompress(pending, CHUNK_BYTES)
            pending = decompressor.unconsumed_tail
            account(produced)
            if decompressor.eof:
                consumed_compressed -= len(decompressor.unused_data)
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
            fail("SOURCE_BUNDLE_CONTRADICTION", "mode " + path)
        if kind != "blob":
            fail("SOURCE_BUNDLE_CONTRADICTION", "type " + path)
        if not is_hex64(digest):
            fail("SOURCE_BUNDLE_CONTRADICTION", "digest " + path)
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
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "class " + path)
        # A generic "this dependency exists" row is not accepted: provenance is class-determined and
        # the upstream class is bound to the exact pinned commit and source-tree digest.
        if provenance != CLASS_PROVENANCE[kind]:
            fail("COMPILE_DEPENDENCY_PROVENANCE_INVALID", path)
        if path in seen:
            fail("COMPILE_DEPENDENCY_DUPLICATE_PATH", path)
        seen.add(path)
        if kind == CLASS_REPO_BUNDLED:
            # Every REPO_BUNDLED path must be a bundle entry, and its content digest must equal the
            # digest re-derived from the git object store at the proven source head.
            if path not in SOURCE_BUNDLE_PATHS:
                fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", path)
            if committed.get(path) != digest:
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "content digest " + path)
            bundled.add(path)
        elif kind == CLASS_EXTERNAL_TOOLCHAIN:
            if digest != "":
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "external entry carries a digest")
        else:
            if not is_hex64(digest):
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "upstream digest " + path)
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
        fail("CBPF_REPRESENTATION_INVALID", str(len(program_bytes)))
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
    names = [require_str(job.get("name"), "JOB_RECORD_MALFORMED") for job in jobs]
    for required in REQUIRED_JOBS:
        occurrences = names.count(required)
        if occurrences == 0:
            fail("REQUIRED_JOB_MISSING", required)
        if occurrences > 1:
            fail("REQUIRED_JOB_DUPLICATE", required)
    for job in jobs:
        if job.get("name") in REQUIRED_JOBS and job.get("conclusion") != "success":
            fail("REQUIRED_JOB_NOT_SUCCESSFUL", str(job.get("name")))
    return jobs


def select_artifacts(api_url, repository, run_id):
    artifacts = enumerate_collection(
        api_url,
        "/repos/" + repository + "/actions/runs/" + str(run_id) + "/artifacts",
        "artifacts",
        "run_artifacts",
    )
    selected = {}
    for artifact in artifacts:
        name = require_str(artifact.get("name"), "ARTIFACT_RECORD_MALFORMED")
        if name not in EXPECTED_ARTIFACT_SET:
            # Outside the expected set: IGNORED for selection, but still counted for enumeration.
            continue
        if artifact.get("expired") is True:
            fail("EXPIRED_ARTIFACT", name)
        if name in selected:
            # A stale sibling left by a previous attempt under the same name BLOCKS, on any page.
            fail("DUPLICATE_EXPECTED_ARTIFACT_NAME", name)
        selected[name] = artifact
    for name in EXPECTED_ARTIFACT_SET:
        if name not in selected:
            fail("EXPECTED_ARTIFACT_MISSING", name)
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
            fail("RUN_ATTEMPT_MISMATCH", label + " run id")
        if require_int(record.get("source_run_attempt"), "RUN_ATTEMPT_MISMATCH", 1) != attempt:
            fail("RUN_ATTEMPT_MISMATCH", label + " run attempt")
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

    # --- SOURCE_BUNDLE_DIGEST_AUTHENTICATED ---
    bundle_payload = _load_bounded_json(arguments.source_bundle_inventory, "source bundle inventory")
    bundle_digest, bundle_entries = recompute_source_bundle_digest(bundle_payload)
    if bundle_digest != arguments.approved_source_bundle_sha256:
        fail("SOURCE_BUNDLE_DIGEST_NOT_APPROVED", bundle_digest)

    # --- the qualification workflow BYTES at the source head ---
    workflow_entry = [entry for entry in bundle_entries if entry["path"] == arguments.expected_workflow_path]
    if len(workflow_entry) != 1:
        fail("QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED", "workflow is not a bundle entry")
    if workflow_entry[0]["sha256"] != arguments.approved_qualification_workflow_sha256:
        fail("QUALIFICATION_WORKFLOW_DIGEST_NOT_APPROVED", workflow_entry[0]["sha256"])

    # --- COMPILE_DEPENDENCY_INVENTORY_AUTHENTICATED ---
    dependency_payload = _load_bounded_json(arguments.compile_dependency_inventory, "compile dependency inventory")
    dependency_digest = recompute_dependency_inventory_digest(dependency_payload, bundle_entries)
    if manifest.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "manifest")
    if elf_record.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "elf record")
    if receipt.get("compile_dependency_inventory_digest_sha256") != dependency_digest:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "receipt")

    # --- QUALIFICATION_DIGESTS_BOUND ---
    if receipt.get("elf_qualification_digest_sha256") != elf_record.get("elf_qualification_digest_sha256"):
        fail("ELF_QUALIFICATION_DIGEST_MISMATCH")
    if not is_hex64(receipt.get("protocol_conformance_digest_sha256")):
        fail("PROTOCOL_CONFORMANCE_DIGEST_MISMATCH")
    if not is_hex64(receipt.get("sandbox_policy_digest_sha256")):
        fail("SANDBOX_POLICY_DIGEST_MISMATCH")

    # --- STAGE_C_SELF_ANCHORED_AUTHORITY_RECONSTRUCTED (repair 2A, 2B, 2C) ---
    #
    # Everything Stage C is about to require is derived HERE, before a single claimed value is read.
    # A3 and A4 are then compared against it.  Nothing below adopts an expected value from either.
    canonical = stage_c_canonical_internal_policy()
    filter_object = stage_c_validate_filter_object(elf_record, canonical)
    case_set_digest = stage_c_case_set_digest()

    # --- ENVIRONMENT_DIGESTS_BOUND ---
    if receipt.get("outer_containment_policy_digest_sha256") != observation.get(
        "outer_containment_policy_digest_sha256"
    ):
        fail("OUTER_POLICY_DIGEST_MISMATCH", "A3 vs A4")
    # The case-set digest is RECOMPUTED, not merely cross-compared.  A3 == A4 proves only that the
    # unprivileged job agreed with itself about which 25 cases it claims to have run.
    if observation.get("observation_case_set_digest_sha256") != case_set_digest:
        fail("OBSERVATION_CASE_SET_DIGEST_MISMATCH", "A3 vs Stage C")
    if receipt.get("observation_case_set_digest_sha256") != case_set_digest:
        fail("OBSERVATION_CASE_SET_DIGEST_MISMATCH", "A4 vs Stage C")

    cases = observation.get("cases")
    if not isinstance(cases, list) or len(cases) != EXACT_CASE_COUNT:
        fail("OBSERVATION_CASE_COUNT_MISMATCH", str(len(cases) if isinstance(cases, list) else -1))
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
            fail("OBSERVATION_CASE_MISSING", identifier)
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
            fail("RECEIPT_DUPLICATE_CASE_IDENTITY", identifier)
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
        "worker_binary_sha256": worker_digest,
        "build_manifest_sha256": member_digests[CANDIDATE_ARTIFACT][BUILD_MANIFEST_MEMBER],
        "elf_qualification_digest_sha256": elf_record.get("elf_qualification_digest_sha256"),
        "protocol_conformance_digest_sha256": receipt.get("protocol_conformance_digest_sha256"),
        "sandbox_policy_digest_sha256": receipt.get("sandbox_policy_digest_sha256"),
        "outer_containment_policy_digest_sha256": receipt.get("outer_containment_policy_digest_sha256"),
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
