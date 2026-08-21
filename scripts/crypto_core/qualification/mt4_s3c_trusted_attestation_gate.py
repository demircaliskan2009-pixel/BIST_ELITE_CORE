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

TRUSTED_PYTHON_INVOCATION_VIOLATION = "TRUSTED_PYTHON_INVOCATION_VIOLATION"
TRUSTED_PYTHON_PATH_VIOLATION = "TRUSTED_PYTHON_PATH_VIOLATION"
TRUSTED_PYTHON_ORIGIN_VIOLATION = "TRUSTED_PYTHON_ORIGIN_VIOLATION"
TRUSTED_PYTHON_ENVIRONMENT_VIOLATION = "TRUSTED_PYTHON_ENVIRONMENT_VIOLATION"

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
ORIGIN_TRUSTED_ENTRYPOINT = "TRUSTED_ENTRYPOINT"

ALLOWED_ORIGIN_CLASSES = (
    ORIGIN_BUILTIN,
    ORIGIN_FROZEN,
    ORIGIN_STDLIB_SOURCE,
    ORIGIN_STDLIB_EXTENSION,
    ORIGIN_TRUSTED_ENTRYPOINT,
)


# Every local file the gate reads is bounded.  The entrypoint source and the two inventories the
# trusted workflow supplies are all small, structured documents; an unbounded read would be a
# resource hazard whatever produced the bytes, and no read in this file is unbounded.
MAX_LOCAL_INPUT_BYTES = 4 * 1024 * 1024


def _attestation_failure(marker, detail):
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


def _resolve_trusted_entrypoints():
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
            _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "malformed entrypoint declaration")
        declared_digest = declaration[:64]
        declared_path = _normalise_path(declaration[65:])
        if any(character not in "0123456789abcdef" for character in declared_digest):
            _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "malformed entrypoint digest")
        if not declared_path.startswith("/") and not (len(declared_path) > 2 and declared_path[1] == ":"):
            _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "entrypoint path must be absolute")
        try:
            with open(declared_path, "rb") as handle:
                body = handle.read(MAX_LOCAL_INPUT_BYTES + 1)
            if len(body) > MAX_LOCAL_INPUT_BYTES:
                _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "entrypoint exceeds the governed bound")
            actual_digest = hashlib.sha256(body).hexdigest()
        except OSError:
            _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "entrypoint is unreadable")
            return {}
        if actual_digest != declared_digest:
            _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "entrypoint digest mismatch")
        resolved[declared_path] = declared_digest
    if not resolved:
        _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "--trusted-entrypoint is required")
    return resolved


def _startup_attestation_first_pass():
    # S-1.  This is the check that makes a plain `python gate.py` invocation fail the contract even
    # if the workflow text were changed: the flags are a REQUEST, and this is the PROOF.
    if int(getattr(sys.flags, "isolated", 0)) != 1:
        _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "isolated mode is not active")
    if int(getattr(sys.flags, "no_site", 0)) != 1:
        _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "site import is not disabled")

    # S-2.  APPROVED_STDLIB_ROOTS are derived FROM THE INTERPRETER ITSELF, never from the
    # environment: deriving them from an environment variable would reintroduce exactly the
    # influence isolated mode removes.
    roots = []
    for prefix in (sys.base_prefix, sys.base_exec_prefix):
        normalised = _normalise_path(prefix)
        if not normalised:
            _attestation_failure(TRUSTED_PYTHON_ORIGIN_VIOLATION, "interpreter reported no base prefix")
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
        _attestation_failure(TRUSTED_PYTHON_INVOCATION_VIOLATION, "--workspace-root is required")
    for entry in sys.path:
        normalised = _normalise_path(entry)
        if normalised in ("", "."):
            _attestation_failure(TRUSTED_PYTHON_PATH_VIOLATION, "the working directory is on sys.path")
        if _is_contained(normalised, workspace):
            _attestation_failure(TRUSTED_PYTHON_PATH_VIOLATION, normalised)
        if scratch and _is_contained(normalised, scratch):
            _attestation_failure(TRUSTED_PYTHON_PATH_VIOLATION, normalised)

    # The entrypoint set is resolved and DIGEST-VERIFIED before origin validation, because origin
    # validation needs it: the honest gate's own module is a repo-resident file, and it must be
    # admitted by exact digest-bound identity rather than by a blanket workspace exemption.
    entrypoints = _resolve_trusted_entrypoints()

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
        return ORIGIN_TRUSTED_ENTRYPOINT, location
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
            _attestation_failure(TRUSTED_PYTHON_ORIGIN_VIOLATION, name + " -> " + location)
        if origin_class == ORIGIN_TRUSTED_ENTRYPOINT:
            # Already admitted by exact digest-bound identity.  The workspace and scratch checks
            # below deliberately do NOT apply to it: the honest gate is a repo-resident file, and
            # rejecting it for that reason alone would be a false positive rather than a control.
            continue
        if location and workspace and _is_contained(location, workspace):
            _attestation_failure(TRUSTED_PYTHON_ORIGIN_VIOLATION, name + " -> " + location)
        if location and scratch and _is_contained(location, scratch):
            _attestation_failure(TRUSTED_PYTHON_ORIGIN_VIOLATION, name + " -> " + location)


(
    _APPROVED_STDLIB_ROOTS,
    _WORKSPACE_ROOT,
    _SCRATCH_ROOT,
    _TRUSTED_ENTRYPOINTS,
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

# S-5.  A PREFIX rule rather than a list, so a future PYTHON* variable is forbidden by DEFAULT
# rather than by omission.  Presence of any such variable is a violation.
FORBIDDEN_ENVIRONMENT_PREFIX = "PYTHON"


def _environment_attestation():
    for name in sorted(os.environ):
        if name.startswith(FORBIDDEN_ENVIRONMENT_PREFIX):
            _attestation_failure(TRUSTED_PYTHON_ENVIRONMENT_VIOLATION, name)


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
TRUSTED_PREDICATE_SCHEMA = "mt4-s3c-trusted-stage-c-predicate.v1"
TRUSTED_PREDICATE_DIGEST_DOMAIN = b"mt4-s3c-trusted-stage-c-predicate.v1\x00"

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


def _request(url, credential, accept):
    request = urllib.request.Request(url)  # noqa: S310 - fixed https API base, no user-supplied scheme
    request.add_header("Accept", accept)
    request.add_header("X-GitHub-Api-Version", "2022-11-28")
    request.add_header("Authorization", "Bearer " + credential)
    return request


def api_json(api_url, path, credential):
    url = api_url.rstrip("/") + path
    if not url.startswith("https://"):
        fail("API_URL_INVALID")
    opener = urllib.request.build_opener(_StripAuthOnRedirect())
    try:
        with opener.open(_request(url, credential, "application/vnd.github+json"), timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        fail("GITHUB_API_FAILED", path + " status " + str(error.code))
    except urllib.error.URLError:
        fail("GITHUB_API_FAILED", path)
    return None


# =================================================================================================
# MT4_S3C_COMPLETE_ENUMERATION_V1 (V9 22.2) AND THE TOTAL_COUNT CONTRACT (V9 SECTION 23)
# =================================================================================================


def enumerate_collection(api_url, base_path, item_key, credential, endpoint_name):
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
        payload = api_json(
            api_url, base_path + separator + "per_page=" + str(PER_PAGE) + "&page=" + str(page), credential
        )
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


def download_artifact(api_url, repository, artifact_id, credential):
    url = api_url.rstrip("/") + "/repos/" + repository + "/actions/artifacts/" + str(artifact_id) + "/zip"
    if not url.startswith("https://"):
        fail("API_URL_INVALID")
    opener = urllib.request.build_opener(_NoRedirect())
    location = None
    try:
        response = opener.open(_request(url, credential, "application/vnd.github+json"), timeout=60)
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
    """Z1..Z13, run entirely from the central directory BEFORE any member is opened."""
    if len(payload) > MAX_ARCHIVE_BYTES:
        fail("ZIP_ARCHIVE_BYTES", str(len(payload)))  # Z1
    infos = archive.infolist()
    names = [info.filename for info in infos]
    if len(infos) != len(expected_members):
        fail("ZIP_MEMBER_COUNT", str(len(infos)))  # Z2
    if sorted(names) != sorted(expected_members):
        fail("ZIP_MEMBER_NAME_SET", ",".join(sorted(names)))  # Z3
    if len(names) != len(set(names)):
        # Z4: a ZIP central directory can legally carry two entries with the same name, and a
        # set-equality check alone would not see it.
        fail("ZIP_DUPLICATE_MEMBER")
    aggregate_declared = 0
    for info in infos:
        name = info.filename
        if name.endswith("/") or info.is_dir():
            fail("ZIP_UNSAFE_MEMBER", "directory entry " + name)  # Z5
        # Z6: path traversal, absolute paths and non-basenames.
        if name in ("", ".", "..") or "/" in name or "\\" in name or ":" in name:
            fail("ZIP_UNSAFE_MEMBER", "path " + name)
        if any(ord(character) < 32 or ord(character) == 127 for character in name):
            fail("ZIP_UNSAFE_MEMBER", "control character")
        # Z7: where the entry carries Unix mode bits, the file type must be regular.
        mode = info.external_attr >> 16
        if mode and (mode & 0o170000) not in (0, 0o100000):
            fail("ZIP_UNSAFE_MEMBER", "non-regular type " + name)
        if info.flag_bits & 0x1:
            fail("ZIP_ENCRYPTED_MEMBER", name)  # Z8
        if info.compress_type not in ALLOWED_COMPRESSION_METHODS:
            fail("ZIP_COMPRESSION_METHOD", name)  # Z9
        cap = _member_cap(name)
        if info.file_size > cap:
            fail("ZIP_DECLARED_SIZE", name)  # Z10
        if info.compress_size > MAX_MEMBER_COMPRESSED:
            fail("ZIP_COMPRESSED_SIZE", name)  # Z11
        aggregate_declared += info.file_size
        if info.file_size // max(info.compress_size, 1) > MAX_RATIO:
            fail("ZIP_DECLARED_RATIO", name)  # Z13
    if aggregate_declared > MAX_AGGREGATE_UNCOMPRESSED:
        fail("ZIP_DECLARED_AGGREGATE", str(aggregate_declared))  # Z12
    return infos


def stream_member(archive, info, aggregate_state):
    """Z14..Z20.  A member is NEVER read whole."""
    cap = _member_cap(info.filename)
    digest = hashlib.sha256()
    chunks = []
    streamed = 0
    with archive.open(info, "r") as handle:  # Z14
        while True:
            chunk = handle.read(CHUNK_BYTES)
            if not chunk:
                break
            streamed += len(chunk)
            if streamed > cap:
                fail("ZIP_MEMBER_STREAM_OVERRUN", info.filename)  # Z15
            if streamed > info.file_size:
                # Z16: the check that catches a lying central directory, mid-stream.
                fail("ZIP_DECLARED_SIZE_UNDERSTATED", info.filename)
            aggregate_state["streamed"] += len(chunk)
            if aggregate_state["streamed"] > MAX_AGGREGATE_UNCOMPRESSED:
                fail("ZIP_AGGREGATE_OVERRUN", info.filename)  # Z17
            if streamed // max(info.compress_size, 1) > MAX_RATIO:
                fail("ZIP_RATIO_EXCEEDED", info.filename)  # Z18
            digest.update(chunk)
            chunks.append(chunk)
        # Z20: the member is read to EOF so the library verifies its CRC.  A CRC failure raises.
    if streamed != info.file_size:
        fail("ZIP_DECLARED_SIZE_OVERSTATED", info.filename)  # Z19
    return b"".join(chunks), digest.hexdigest()


def extract_artifact(payload, expected_members):
    """Decode one artifact archive entirely under the bounded streaming policy."""
    aggregate_state = {"streamed": 0}
    contents = {}
    digests = {}
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            infos = pre_decompression_gate(archive, payload, expected_members)
            for info in infos:
                body, digest = stream_member(archive, info, aggregate_state)
                contents[info.filename] = body
                digests[info.filename] = digest
    except zipfile.BadZipFile:
        fail("ZIP_ARCHIVE_MALFORMED")
    except (OSError, ValueError) as error:
        fail("ZIP_CRC_INVALID", str(error))
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
    """V9 28.6 leg D-5, recomputed at the trust boundary rather than trusted from the job."""
    if not isinstance(inventory_payload, dict):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "type")
    if inventory_payload.get("schema") != DEPENDENCY_SCHEMA:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "schema")
    entries = inventory_payload.get("entries")
    if not isinstance(entries, list):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entries")
    committed = {entry["path"]: entry["sha256"] for entry in bundle_entries}
    paths = []
    for entry in entries:
        if not isinstance(entry, dict):
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entry type")
        path = require_str(entry.get("path"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        kind = require_str(entry.get("class"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        digest = require_str(entry.get("sha256"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH")
        if kind not in ("REPO_BUNDLED", "UPSTREAM_PINNED", "EXTERNAL_TOOLCHAIN"):
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "class " + path)
        if kind == "REPO_BUNDLED":
            # Every REPO_BUNDLED path must be a bundle entry, and its content digest must equal the
            # digest re-derived from the git object store at the proven source head.
            if path not in SOURCE_BUNDLE_PATHS:
                fail("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", path)
            if committed.get(path) != digest:
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "content digest " + path)
        elif kind == "EXTERNAL_TOOLCHAIN":
            if digest != "":
                fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "external entry carries a digest")
        elif not is_hex64(digest):
            fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "upstream digest " + path)
        paths.append(path)
    if paths != sorted(paths):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "ordering")
    if require_int(inventory_payload.get("entry_count"), "COMPILE_DEPENDENCY_INVENTORY_MISMATCH", 0) != len(entries):
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "entry_count")
    if inventory_payload.get("path_order") != paths:
        fail("COMPILE_DEPENDENCY_INVENTORY_MISMATCH", "path_order")
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


def stage_c_equivalence_digest(observation, case, receipt_digest):
    """Reconstruct the raw A3 preimage from observation fields and recompute the digest."""
    capture = case.get("internal_capture")
    baseline = case.get("seccomp_baseline")
    dump = case.get("dump_leg")
    if not isinstance(capture, dict) or not isinstance(baseline, dict) or not isinstance(dump, dict):
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "observation shape")
    program_bytes = bytes.fromhex(require_str(capture.get("program_bytes_hex"), "OBSERVATION_MALFORMED"))
    available = dump.get("availability") == "AVAILABLE"
    record = {
        "schema": INTERNAL_EQUIVALENCE_SCHEMA,
        "canonical_internal_policy_id": require_str(
            observation.get("canonical_internal_policy_id"), "OBSERVATION_MALFORMED"
        ),
        "canonical_internal_policy_sha256": require_str(
            observation.get("canonical_internal_policy_sha256"), "OBSERVATION_MALFORMED"
        ),
        "program_representation_version": PROGRAM_REPRESENTATION_VERSION,
        "canonical_internal_cbpf_instruction_count": require_int(
            observation.get("canonical_internal_cbpf_instruction_count"), "OBSERVATION_MALFORMED", 1, 512
        ),
        "canonical_internal_cbpf_sha256": require_str(
            observation.get("canonical_internal_cbpf_sha256"), "OBSERVATION_MALFORMED"
        ),
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
        "dump_leg_index0_sha256": cbpf_digest(bytes.fromhex(dump.get("index0_bytes_hex", ""))) if available else "",
        "dump_leg_index1_sha256": cbpf_digest(bytes.fromhex(dump.get("index1_bytes_hex", ""))) if available else "",
        "dump_leg_terminates_at_index": require_int(dump.get("terminates_at_index"), "OBSERVATION_MALFORMED", -1)
        if available
        else -1,
        "case_id": require_str(case.get("case_id"), "OBSERVATION_MALFORMED"),
        "source_run_id": require_int(observation.get("source_run_id"), "OBSERVATION_MALFORMED", 1),
        "source_run_attempt": require_int(observation.get("source_run_attempt"), "OBSERVATION_MALFORMED", 1),
        "source_head_sha": require_str(observation.get("source_head_sha"), "OBSERVATION_MALFORMED"),
        "candidate_binary_sha256": require_str(observation.get("candidate_binary_sha256"), "OBSERVATION_MALFORMED"),
    }
    for field, expected in INTERNAL_EQUIVALENCE_REQUIRED_VALUES.items():
        if record[field] != expected:
            fail("INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED", field)
    if record["captured_internal_cbpf_sha256"] != record["canonical_internal_cbpf_sha256"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured differs from canonical")
    if record["captured_internal_len_u32"] != record["canonical_internal_cbpf_instruction_count"]:
        fail("INTERNAL_FILTER_EQUIVALENCE_FAILED", "captured length differs from canonical")

    recomputed = domain_digest(INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, record)
    a3_digest = require_str(case.get("internal_filter_equivalence", {}).get("digest_sha256"), "OBSERVATION_MALFORMED")
    if a3_digest != recomputed:
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "A3 vs Stage C for " + record["case_id"])
    if receipt_digest != recomputed:
        fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "A4 vs Stage C for " + record["case_id"])
    return recomputed


# =================================================================================================
# SOURCE RUN BINDING (V9 SECTION 24) AND CANDIDATE/RECEIPT BINDING (V9 SECTION 25)
# =================================================================================================


def authenticate_source_run(api_url, repository, run_id, arguments, credential):
    run = api_json(api_url, "/repos/" + repository + "/actions/runs/" + str(run_id), credential)
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


def authenticate_jobs(api_url, repository, run_id, attempt, credential):
    jobs = enumerate_collection(
        api_url,
        "/repos/" + repository + "/actions/runs/" + str(run_id) + "/attempts/" + str(attempt) + "/jobs",
        "jobs",
        credential,
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


def select_artifacts(api_url, repository, run_id, credential):
    artifacts = enumerate_collection(
        api_url,
        "/repos/" + repository + "/actions/runs/" + str(run_id) + "/artifacts",
        "artifacts",
        credential,
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


def run_gate(arguments, credential):
    api_url = arguments.api_url
    repository = arguments.repository
    run_id = arguments.source_run_id

    # --- SOURCE_RUN_AUTHENTICATED -> RUN_ATTEMPT_AUTHENTICATED ---
    attempt = authenticate_source_run(api_url, repository, run_id, arguments, credential)

    # --- EXPECTED_JOBS_AUTHENTICATED -> JOBS_TOTAL_COUNT_RECONCILED ---
    authenticate_jobs(api_url, repository, run_id, attempt, credential)

    # --- COMPLETE_ARTIFACT_ENUMERATION_PROVEN -> ARTIFACTS_TOTAL_COUNT_RECONCILED ---
    # --- -> UNIQUE_EXPECTED_ARTIFACTS_SELECTED ---
    artifacts = select_artifacts(api_url, repository, run_id, credential)

    # --- CANDIDATE_SERVICE_IDENTITY_AUTHENTICATED / RECEIPT_SERVICE_IDENTITY_AUTHENTICATED ---
    payloads = {}
    member_digests = {}
    for name in EXPECTED_ARTIFACT_SET:
        artifact = artifacts[name]
        artifact_id = require_int(artifact.get("id"), "ARTIFACT_RECORD_MALFORMED", 1)
        payload = download_artifact(api_url, repository, artifact_id, credential)
        contents, digests = extract_artifact(payload, EXPECTED_MEMBERS[name])
        payloads[name] = contents
        member_digests[name] = digests

    manifest = json.loads(payloads[CANDIDATE_ARTIFACT][BUILD_MANIFEST_MEMBER].decode("utf-8"))
    elf_record = json.loads(payloads[ELF_ARTIFACT][ELF_RECORD_MEMBER].decode("utf-8"))
    observation = json.loads(payloads[OBSERVATION_ARTIFACT][OBSERVATION_MEMBER].decode("utf-8"))
    receipt = json.loads(payloads[RECEIPT_ARTIFACT][RECEIPT_MEMBER].decode("utf-8"))

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

    # --- ENVIRONMENT_DIGESTS_BOUND ---
    if receipt.get("outer_containment_policy_digest_sha256") != observation.get(
        "outer_containment_policy_digest_sha256"
    ):
        fail("OUTER_POLICY_DIGEST_MISMATCH", "A3 vs A4")
    if receipt.get("observation_case_set_digest_sha256") != observation.get("observation_case_set_digest_sha256"):
        fail("OBSERVATION_CASE_SET_DIGEST_MISMATCH", "A3 vs A4")

    cases = observation.get("cases")
    if not isinstance(cases, list) or len(cases) != EXACT_CASE_COUNT:
        fail("OBSERVATION_CASE_COUNT_MISMATCH", str(len(cases) if isinstance(cases, list) else -1))
    if require_int(receipt.get("case_count"), "OBSERVATION_CASE_COUNT_MISMATCH", 0) != EXACT_CASE_COUNT:
        fail("OBSERVATION_CASE_COUNT_MISMATCH", "receipt")

    receipt_digests = {}
    for item in receipt.get("internal_filter_equivalence_digests", []):
        if not isinstance(item, dict):
            fail("RECEIPT_BINDING_MISMATCH", "equivalence digest shape")
        receipt_digests[require_str(item.get("case_id"), "RECEIPT_BINDING_MISMATCH")] = item.get("digest_sha256")

    recomputed = []
    for case in cases:
        if not isinstance(case, dict):
            fail("OBSERVATION_MALFORMED", "case type")
        case_id = require_str(case.get("case_id"), "OBSERVATION_MALFORMED")
        if case_id not in receipt_digests:
            fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "receipt lacks " + case_id)
        equivalence = case.get("internal_filter_equivalence")
        if not isinstance(equivalence, dict):
            fail("OBSERVATION_MALFORMED", "equivalence block")
        if not equivalence.get("valid"):
            # A case with no proven internal installation carries no equivalence, and the receipt
            # must not claim one for it either.
            if receipt_digests[case_id]:
                fail("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", "claimed for an unproven case " + case_id)
            recomputed.append({"case_id": case_id, "digest_sha256": ""})
            continue
        recomputed.append(
            {
                "case_id": case_id,
                "digest_sha256": stage_c_equivalence_digest(observation, case, receipt_digests[case_id]),
            }
        )

    if not receipt.get("all_cases_conform"):
        fail("QUALIFICATION_NOT_CONFORMANT")
    if receipt.get("evidence_status") != "ADMISSION_EVIDENCE_ONLY":
        fail("RECEIPT_IS_EVIDENCE_ONLY", "evidence_status")
    if receipt.get("governed_worker_row_created") is not False:
        fail("ACTIVE_ROW_FORBIDDEN_IN_P0")

    predicate = {
        "schema": TRUSTED_PREDICATE_SCHEMA,
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
        "observation_case_set_digest_sha256": receipt.get("observation_case_set_digest_sha256"),
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
    predicate["trusted_predicate_digest_sha256"] = domain_digest(TRUSTED_PREDICATE_DIGEST_DOMAIN, predicate)
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
    _validate_module_origins(_APPROVED_STDLIB_ROOTS, _WORKSPACE_ROOT, _SCRATCH_ROOT, _TRUSTED_ENTRYPOINTS)
    _environment_attestation()

    credential = os.environ.get("GITHUB_TOKEN") or ""
    if not credential:
        fail("CREDENTIAL_UNAVAILABLE")

    predicate = run_gate(arguments, credential)
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
