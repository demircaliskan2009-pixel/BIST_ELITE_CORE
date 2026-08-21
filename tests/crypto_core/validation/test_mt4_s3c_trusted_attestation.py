"""Permanent offline contract tests for the MT4-S3C P0 trusted Stage-C attestation gate.

ARCHITECTURE: MT4-S3C-P0-STATIC-WORKER-QUALIFICATION-INFRA-V9, SECTIONS 22, 23, 24, 25, 26, 27.
PATH N21.  DELIBERATELY NOT A SOURCE-BUNDLE ENTRY.

WHY THE BEHAVIOURAL TESTS RUN IN A SUBPROCESS.  The gate performs TRUSTED_GATE_STARTUP_ATTESTATION_V1
in its FIRST executable statements, and that attestation is the whole point of V9 SECTION 26: it
proves the interpreter really started isolated, with site disabled, with no repository-controlled
directory on the import path, and with every module in sys.modules resolving to an allowed origin.
Importing the gate the ordinary way would either bypass that proof or fail it, so the tests instead
run the gate UNDER ITS OWN FROZEN INVOCATION CONTRACT -- an absolute interpreter, -I, -S, and a
digest-bound trusted entrypoint declaration -- and exercise its real functions there.  That is the
only way to test the shipped code rather than a weakened copy of it.

WHAT IS PROVEN HERE OFFLINE: the startup attestation itself, including its refusal of a
non-isolated invocation and of a PYTHON* environment; the bounded streaming ZIP policy Z1..Z20; the
complete-pagination and governed total_count rules; the qualification source bundle and compile
dependency inventory recomputation; and the Stage-C recomputation that makes A3 == A4 ==
STAGE_C_RECOMPUTED.  Nothing here touches the network.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

_REPO_ROOT = Path(__file__).resolve().parents[3]
TRUSTED_GATE = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_s3c_trusted_attestation_gate.py"
TRUSTED_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_s3c_trusted_attestation.yml"
S3B_GATE = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "mt4_trusted_attestation_gate.py"

# The declared DIRECT import set of the gate (V9 SECTION 26.5).  Transitive imports are deliberately
# NOT enumerated: the gate validates ORIGIN over the whole of sys.modules, which covers the
# transitive closure without the architecture having to guess it.
DECLARED_DIRECT_IMPORTS = {
    "argparse",
    "hashlib",
    "io",
    "json",
    "os",
    "pathlib",
    "sys",
    "urllib.error",
    "urllib.parse",
    "urllib.request",
    "zipfile",
}


def _gate_source():
    return TRUSTED_GATE.read_text(encoding="utf-8")


def _strip_python_prose(text):
    """Remove comments and triple-quoted prose, keeping every ordinary literal.

    Source-shape tests below must read CODE.  A file that merely SAYS a construct is forbidden
    must not thereby satisfy the test that the construct is absent, and the prose in this gate
    names every construct it forbids.
    """
    import io
    import tokenize

    lines = text.splitlines(keepends=True)
    for token in tokenize.generate_tokens(io.StringIO(text).readline):
        prose = token.type == tokenize.COMMENT or (
            token.type == tokenize.STRING and token.string.lstrip("rbfRBF")[:3] in ('"""', "'''")
        )
        if not prose:
            continue
        (start_row, start_column), (end_row, end_column) = token.start, token.end
        for row in range(start_row, end_row + 1):
            line = lines[row - 1]
            first = start_column if row == start_row else 0
            last = end_column if row == end_row else len(line)
            blanked = "".join(" " if character != "\n" else "\n" for character in line[first:last])
            lines[row - 1] = line[:first] + blanked + line[last:]
    return "".join(lines)


def _gate_code():
    return _strip_python_prose(_gate_source())


def _strip_yaml_prose(path):
    import re as _re

    return _re.sub(r"(?m)^\s*#.*$", " ", path.read_text(encoding="utf-8"))


# =================================================================================================
# SOURCE SHAPE  [PT-214, PT-244, PT-206, PT-331]
# =================================================================================================


def test_pt_214_the_gate_imports_exactly_the_declared_direct_set():
    tree = ast.parse(_gate_source())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import would reach the checkout"
            imported.add(node.module or "")
    imported.discard("__future__")
    assert imported == DECLARED_DIRECT_IMPORTS, sorted(imported ^ DECLARED_DIRECT_IMPORTS)


def test_pt_214b_the_gate_contains_no_dynamic_import_machinery():
    code = _gate_code()
    for forbidden in ("importlib", "__import__", "exec(", "eval(", "compile(", "subprocess", "ctypes"):
        assert forbidden not in code, forbidden


def test_the_gate_imports_no_repository_module():
    code = _gate_code()
    # Repository PATHS appear as governed constants -- that is the bundle inventory the gate
    # verifies.  What must never appear is an IMPORT of a repository module, or any mutation of
    # the import path that could make one resolvable.
    for forbidden in ("from scripts", "import scripts", "sys.path.insert", "sys.path.append", "sys.path ="):
        assert forbidden not in code, forbidden


def test_pt_244_the_gate_never_reads_a_whole_archive_member():
    """archive.read(member) decompresses BEFORE any bound is consulted, and is forbidden outright."""
    code = _gate_code()
    assert "archive.read(" not in code
    assert ".read(name)" not in code
    assert "archive.open(" in code
    assert "CHUNK_BYTES" in code
    # The merged S3B gate is the NEGATIVE reference: it does exactly what S3C forbids.
    s3b = S3B_GATE.read_text(encoding="utf-8")
    assert "archive.read(name)" in s3b


def test_pt_206_the_gate_never_fabricates_a_total_count():
    source = _gate_code()
    assert "GOVERNED_TOTAL_COUNT_ENDPOINTS" in source
    assert "TOTAL_COUNT_MISSING" in source
    assert "len(items)" in source
    # A synthesised total is exactly what T5 forbids; there is no assignment that computes one.
    assert re.search(r"total_count[\"']?\s*[:=]\s*len\(", source) is None


def test_pt_331_run_attempt_is_never_read_from_the_event_payload():
    source = _gate_code()
    assert "workflow_run.run_attempt" not in source
    assert "RUN_ATTEMPT_UNAVAILABLE" in source
    assert "/attempts/" in source
    assert "ATTEMPT_JOBS_UNAVAILABLE" in source


def test_the_gate_declares_no_admission_and_creates_no_governed_row():
    source = _gate_source()
    assert '"admission": "NONE"' in source
    assert '"governed_worker_row_created": False' in source
    assert "ACTIVE_ROW_FORBIDDEN_IN_P0" in source
    for forbidden in ("custody_reproof", "prdv4_stage4_complete", "MachineTimeAnchor"):
        assert forbidden not in source, forbidden


def test_the_startup_attestation_is_the_first_executable_statement():
    tree = ast.parse(_gate_source())
    statements = [node for node in tree.body if not isinstance(node, ast.Expr)]
    assert isinstance(statements[0], ast.Import)
    assert [alias.name for alias in statements[0].names] == ["sys"]
    # Every other MODULE-LEVEL import must be EXECUTED after the attestation call, so nothing
    # filesystem-resolved is imported before sys.path has been proven clean.  The single import
    # inside the attestation itself is hashlib, which runs only after S-3 has measured the path.
    attestation_line = next(
        node.lineno
        for node in tree.body
        if isinstance(node, ast.Assign) and "_startup_attestation_first_pass" in ast.dump(node)
    )
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)) and node.lineno != statements[0].lineno:
            assert node.lineno > attestation_line, ast.dump(node)


# =================================================================================================
# THE TRUSTED WORKFLOW SHAPE  [PT-211, PT-221, PT-222]
# =================================================================================================


@pytest.fixture(scope="module")
def trusted_workflow():
    return yaml.safe_load(TRUSTED_WORKFLOW.read_text(encoding="utf-8"))


def test_the_trusted_workflow_is_anchored_to_the_default_branch(trusted_workflow):
    triggers = trusted_workflow[True] if True in trusted_workflow else trusted_workflow["on"]
    assert set(triggers) == {"workflow_run"}
    assert triggers["workflow_run"]["branches"] == ["main"]
    assert triggers["workflow_run"]["types"] == ["completed"]
    assert triggers["workflow_run"]["workflows"] == ["crypto_core mt4-s3c static worker qualification"]
    guard = trusted_workflow["jobs"]["s3c-attest-trusted-evidence"]["if"]
    for clause in (
        "workflow_run.conclusion == 'success'",
        "workflow_run.event == 'workflow_dispatch'",
        "workflow_run.head_branch == 'main'",
        "head_repository.full_name == github.repository",
    ):
        assert clause in guard, clause


def test_pt_211_the_gate_is_never_invoked_through_a_bare_interpreter():
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    invocation = [line for line in raw.splitlines() if "-I -S" in line]
    assert len(invocation) == 1, invocation
    assert "${TRUSTED_PYTHON}" in invocation[0]
    assert "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}" in invocation[0]
    # A bare token would be an uncontrolled PATH lookup, and a relative gate path would resolve
    # against the process working directory.  Neither may appear anywhere in the invocation.
    assert not re.search(r"(?m)^\s*python3?\s+\S*mt4_s3c_trusted_attestation_gate\.py", raw)


def test_pt_221_and_pt_222_the_invocation_carries_both_isolation_flags():
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    assert " -I -S " in raw
    assert "env -i" in raw  # the sanitized environment allowlist, not the ambient environment


def test_the_environment_passed_to_the_gate_is_an_exact_allowlist():
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    block = raw[raw.index("env -i") : raw.index("--workspace-root")]
    exported = re.findall(r"(?m)^\s*([A-Z_][A-Z0-9_]*)=", block)
    assert sorted(exported) == ["GITHUB_API_URL", "GITHUB_REPOSITORY", "GITHUB_RUN_ID", "GITHUB_TOKEN"]
    assert not any(name.startswith("PYTHON") for name in exported)


def test_exactly_one_digest_bound_trusted_entrypoint_is_declared():
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    declarations = re.findall(r"--trusted-entrypoint\s+\"([^\"]+)\"", raw)
    assert len(declarations) == 1, declarations
    assert declarations[0] == "${APPROVED_S3C_TRUSTED_GATE_SHA256}:${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"


def test_no_step_is_interposed_between_the_gate_digest_check_and_the_gate_run(trusted_workflow):
    steps = trusted_workflow["jobs"]["s3c-attest-trusted-evidence"]["steps"]
    names = [step.get("name", "") for step in steps]
    check = next(index for index, name in enumerate(names) if "approved digest" in name)
    run = next(index for index, name in enumerate(names) if "frozen isolated invocation" in name)
    interposed = names[check + 1 : run]
    # Only steps that cannot influence the gate's own bytes may appear between the two.
    for name in interposed:
        assert "gate" not in name.lower(), name


def test_the_trusted_workflow_holds_no_signing_capability(trusted_workflow):
    permissions = trusted_workflow["jobs"]["s3c-attest-trusted-evidence"]["permissions"]
    assert permissions == {"actions": "read", "contents": "read"}
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    assert "id-token" not in raw
    assert "attestations: write" not in raw


def test_the_approved_constants_live_only_on_the_trusted_surface():
    raw = TRUSTED_WORKFLOW.read_text(encoding="utf-8")
    for constant in (
        "APPROVED_S3C_QUALIFICATION_WORKFLOW_SHA256",
        "APPROVED_S3C_QUALIFICATION_SOURCE_BUNDLE_SHA256",
        "APPROVED_S3C_TRUSTED_GATE_SHA256",
    ):
        assert constant in raw, constant
        # A self-referential digest could not exist, and a candidate-reported one could be forged,
        # so the constant must appear nowhere the measured set can reach.  Prose that NAMES the
        # constant is not a definition of it, so both scans run against code.
        assert constant not in _gate_code(), constant
        qualification = _strip_yaml_prose(
            _REPO_ROOT / ".github" / "workflows" / "crypto_core_mt4_s3c_static_worker_qualification.yml"
        )
        assert constant not in qualification, constant


# =================================================================================================
# THE ISOLATED DRIVER.  The gate's real functions, under the gate's real invocation contract.
# =================================================================================================

_DRIVER = """
import hashlib
import io
import json
import sys
import zipfile

GATE = sys.argv[sys.argv.index("--gate-module") + 1]

import importlib.util

specification = importlib.util.spec_from_file_location("mt4_s3c_trusted_gate", GATE)
gate = importlib.util.module_from_spec(specification)
specification.loader.exec_module(gate)

results = {}


def check(name, function):
    try:
        function()
        results[name] = "PASS"
    except AssertionError as error:
        results[name] = "FAIL: " + str(error)
    except BaseException as error:  # noqa: BLE001 - the driver reports, it never masks
        results[name] = "ERROR: " + type(error).__name__ + ": " + str(error)


def expect(marker, function):
    try:
        function()
    except gate.TrustedGateError as error:
        assert marker in str(error), marker + " not in " + str(error)
        return
    raise AssertionError("did not raise " + marker)


def build_archive(members, method=zipfile.ZIP_DEFLATED):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", method) as archive:
        for name, body in members:
            archive.writestr(name, body)
    return buffer.getvalue()


CANDIDATE = "mt4-s3c-candidate-linux-x86_64"
WORKER = "mt4_s3c_static_worker"
MANIFEST = "mt4_s3c_build_manifest.json"


def z_reference():
    payload = build_archive([(WORKER, b"A" * 64), (MANIFEST, b"{}")])
    contents, digests = gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE])
    assert contents[WORKER] == b"A" * 64
    assert digests[WORKER] == hashlib.sha256(b"A" * 64).hexdigest()


def z2_member_count():
    payload = build_archive([(WORKER, b"A")])
    expect("ZIP_MEMBER_COUNT", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z3_member_name_set():
    payload = build_archive([(WORKER, b"A"), ("unexpected.json", b"{}")])
    expect("ZIP_MEMBER_NAME_SET", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z6_path_traversal():
    payload = build_archive([("../escape", b"A"), (MANIFEST, b"{}")])
    expect("ZIP_", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z9_compression_method():
    payload = build_archive([(WORKER, b"A" * 64), (MANIFEST, b"{}")], zipfile.ZIP_BZIP2)
    expect("ZIP_COMPRESSION_METHOD", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z10_declared_size():
    body = b"B" * (gate.MAX_MEMBER_UNCOMPRESSED_JSON + 1)
    payload = build_archive([(WORKER, b"A"), (MANIFEST, body)])
    expect("ZIP_DECLARED_SIZE", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z13_declared_ratio():
    body = b"\\x00" * (gate.MAX_RATIO * 4096)
    payload = build_archive([(WORKER, b"A"), (MANIFEST, body)])
    expect("ZIP_", lambda: gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE]))


def z16_declared_size_understated():
    payload = bytearray(build_archive([(WORKER, b"A" * 4096), (MANIFEST, b"{}")]))
    marker = payload.find(b"PK\\x01\\x02")
    assert marker > 0
    # Understate the central-directory uncompressed size so the stream overruns it mid-read.
    payload[marker + 24 : marker + 28] = (16).to_bytes(4, "little")
    expect(
        "ZIP_",
        lambda: gate.extract_artifact(bytes(payload), gate.EXPECTED_MEMBERS[CANDIDATE]),
    )


def z_constants_are_literal():
    assert gate.MAX_MEMBER_UNCOMPRESSED_JSON == 4 * 1024 * 1024
    assert gate.MAX_WORKER_BINARY_BYTES == 8 * 1024 * 1024
    assert gate.MAX_MEMBER_UNCOMPRESSED_BINARY == gate.MAX_WORKER_BINARY_BYTES
    assert gate.MAX_AGGREGATE_UNCOMPRESSED == 16 * 1024 * 1024
    assert gate.MAX_MEMBER_COMPRESSED == 16 * 1024 * 1024
    assert gate.MAX_ARCHIVE_BYTES == 16 * 1024 * 1024
    assert gate.MAX_RATIO == 100
    assert gate.CHUNK_BYTES == 65536
    assert gate.MAX_SYSCALL_EVENTS_PER_CASE == 256
    assert gate.MAX_EVENT_RECORD_BYTES == 256
    assert gate.MAX_CASE_FIXED_FIELD_BYTES == 1024
    assert gate.MAX_RECORD_ENVELOPE_BYTES == 32768
    worst = (
        gate.MAX_SYSCALL_EVENTS_PER_CASE * gate.MAX_EVENT_RECORD_BYTES + gate.MAX_CASE_FIXED_FIELD_BYTES
    ) * 25 + 20000 + gate.MAX_RECORD_ENVELOPE_BYTES
    assert worst <= gate.MAX_MEMBER_UNCOMPRESSED_JSON
    assert gate.EXPECTED_MEMBERS[CANDIDATE] == (WORKER, MANIFEST)
    for name, members in gate.EXPECTED_MEMBERS.items():
        assert len(members) == (2 if name == CANDIDATE else 1)


def total_count_all_four_conditions():
    gate.reconcile_total_count([2], [{"id": 1}, {"id": 2}], {1, 2}, True, "attempt_jobs")
    expect("TOTAL_COUNT_MISSING", lambda: gate.reconcile_total_count([], [], set(), True, "attempt_jobs"))
    expect(
        "TOTAL_COUNT_INCONSISTENT",
        lambda: gate.reconcile_total_count([2, 3], [{"id": 1}, {"id": 2}], {1, 2}, True, "attempt_jobs"),
    )
    expect(
        "TOTAL_COUNT_INCONSISTENT",
        lambda: gate.reconcile_total_count([3], [{"id": 1}, {"id": 2}], {1, 2}, True, "attempt_jobs"),
    )
    expect(
        "TOTAL_COUNT_INCONSISTENT",
        lambda: gate.reconcile_total_count([2], [{"id": 1}, {"id": 1}], {1}, True, "attempt_jobs"),
    )
    expect(
        "TOTAL_COUNT_INCONSISTENT",
        lambda: gate.reconcile_total_count([2], [{"id": 1}, {"id": 2}], {1, 2}, False, "attempt_jobs"),
    )


def source_bundle_recomputation():
    entries = [
        {"path": path, "mode": "100644", "type": "blob", "sha256": format(index, "064x")}
        for index, path in enumerate(gate.SOURCE_BUNDLE_PATHS)
    ]
    digest, normalised = gate.recompute_source_bundle_digest({"entries": entries})
    assert len(digest) == 64
    assert len(normalised) == 16
    expect(
        "SOURCE_BUNDLE_CONTRADICTION",
        lambda: gate.recompute_source_bundle_digest({"entries": entries[:-1]}),
    )
    swapped = list(entries)
    swapped[0] = dict(swapped[0], type="commit")
    expect("SOURCE_BUNDLE_CONTRADICTION", lambda: gate.recompute_source_bundle_digest({"entries": swapped}))
    reordered = list(reversed(entries))
    expect("SOURCE_BUNDLE_CONTRADICTION", lambda: gate.recompute_source_bundle_digest({"entries": reordered}))


def dependency_inventory_recomputation():
    bundle = [
        {"path": path, "mode": "100644", "type": "blob", "sha256": format(index, "064x")}
        for index, path in enumerate(gate.SOURCE_BUNDLE_PATHS)
    ]
    entries = [
        {"path": gate.SOURCE_BUNDLE_PATHS[9], "class": "REPO_BUNDLED", "sha256": format(9, "064x")},
        {"path": "usr/include/stdio.h", "class": "EXTERNAL_TOOLCHAIN", "sha256": ""},
    ]
    entries.sort(key=lambda entry: entry["path"])
    payload = {
        "schema": gate.DEPENDENCY_SCHEMA,
        "entry_count": len(entries),
        "entries": entries,
        "path_order": [entry["path"] for entry in entries],
    }
    digest = gate.recompute_dependency_inventory_digest(payload, bundle)
    assert len(digest) == 64
    tampered = json.loads(json.dumps(payload))
    tampered["entries"][0]["sha256"] = format(1, "064x") if tampered["entries"][0]["sha256"] else ""
    expect(
        "COMPILE_DEPENDENCY_INVENTORY_MISMATCH",
        lambda: gate.recompute_dependency_inventory_digest(tampered, bundle),
    )
    unbundled = json.loads(json.dumps(payload))
    unbundled["entries"].append(
        {"path": "src/crypto_core/__init__.py", "class": "REPO_BUNDLED", "sha256": format(3, "064x")}
    )
    unbundled["entries"].sort(key=lambda entry: entry["path"])
    unbundled["entry_count"] = len(unbundled["entries"])
    unbundled["path_order"] = [entry["path"] for entry in unbundled["entries"]]
    expect(
        "SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED",
        lambda: gate.recompute_dependency_inventory_digest(unbundled, bundle),
    )


def stage_c_equivalence_recomputation():
    program = bytes(113 * 8)
    canonical = gate.cbpf_digest(program)
    observation = {
        "canonical_internal_policy_id": "MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64",
        "canonical_internal_policy_sha256": "a" * 64,
        "canonical_internal_cbpf_instruction_count": 113,
        "canonical_internal_cbpf_sha256": canonical,
        "source_run_id": 4242,
        "source_run_attempt": 1,
        "source_head_sha": "c" * 40,
        "candidate_binary_sha256": "d" * 64,
    }
    case = {
        "case_id": "C01_POSITIVE_EXACT_FIXTURE",
        "internal_capture": {
            "program_bytes_hex": program.hex(),
            "fprog_va_u64": 0x401600,
            "length": 113,
            "install_return_i32": 0,
        },
        "seccomp_baseline": {
            "supervisor_seccomp": 0,
            "supervisor_filters": 0,
            "child_seccomp": 0,
            "child_filters": 0,
            "outer_post_filters": 1,
            "internal_post_filters": 2,
            "internal_post_seccomp": 2,
            "revalidated_filters": 2,
        },
        "dump_leg": {"availability": "UNAVAILABLE_IN_PINNED_ENVIRONMENT", "terminates_at_index": -1},
        "internal_filter_equivalence": {"digest_sha256": ""},
    }
    # Compute the honest value first, then require A3 and A4 to equal it.
    honest = None
    try:
        gate.stage_c_equivalence_digest(observation, case, "")
    except gate.TrustedGateError as error:
        assert "A3 vs Stage C" in str(error)
    reference = gate.domain_digest(
        gate.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN,
        {
            "schema": gate.INTERNAL_EQUIVALENCE_SCHEMA,
            "canonical_internal_policy_id": observation["canonical_internal_policy_id"],
            "canonical_internal_policy_sha256": observation["canonical_internal_policy_sha256"],
            "program_representation_version": gate.PROGRAM_REPRESENTATION_VERSION,
            "canonical_internal_cbpf_instruction_count": 113,
            "canonical_internal_cbpf_sha256": canonical,
            "captured_internal_cbpf_sha256": canonical,
            "captured_internal_uargs_va_u64": 0x401600,
            "captured_internal_len_u32": 113,
            "install_exit_return_i32": 0,
            "baseline_supervisor_seccomp": 0,
            "baseline_supervisor_filters": 0,
            "baseline_child_seccomp": 0,
            "baseline_child_filters": 0,
            "pre_install_filters": 1,
            "post_install_filters": 2,
            "post_install_seccomp_mode": 2,
            "revalidated_filters": 2,
            "dump_leg_availability": "UNAVAILABLE_IN_PINNED_ENVIRONMENT",
            "dump_leg_index0_sha256": "",
            "dump_leg_index1_sha256": "",
            "dump_leg_terminates_at_index": -1,
            "case_id": "C01_POSITIVE_EXACT_FIXTURE",
            "source_run_id": 4242,
            "source_run_attempt": 1,
            "source_head_sha": "c" * 40,
            "candidate_binary_sha256": "d" * 64,
        },
    )
    honest = reference
    case["internal_filter_equivalence"]["digest_sha256"] = honest
    assert gate.stage_c_equivalence_digest(observation, case, honest) == honest
    # A4 alone changed -> mismatch.  A3 alone changed -> mismatch.  Both are required to agree.
    expect("INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH", lambda: gate.stage_c_equivalence_digest(observation, case, "e" * 64))
    tampered = json.loads(json.dumps(case))
    tampered["internal_filter_equivalence"]["digest_sha256"] = "f" * 64
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH",
        lambda: gate.stage_c_equivalence_digest(observation, tampered, honest),
    )
    # A baseline that violates a governed constraint is never digested at all.
    broken = json.loads(json.dumps(case))
    broken["seccomp_baseline"]["child_filters"] = 1
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED",
        lambda: gate.stage_c_equivalence_digest(observation, broken, honest),
    )


def startup_attestation_state():
    assert sys.flags.isolated == 1
    assert sys.flags.no_site == 1
    assert gate.ORIGIN_TRUSTED_ENTRYPOINT in gate.ALLOWED_ORIGIN_CLASSES
    assert len(gate._TRUSTED_ENTRYPOINTS) == 2
    for entry in sys.path:
        assert not entry.replace(chr(92), "/").startswith(gate._WORKSPACE_ROOT)


check("z_reference", z_reference)
check("z2_member_count", z2_member_count)
check("z3_member_name_set", z3_member_name_set)
check("z6_path_traversal", z6_path_traversal)
check("z9_compression_method", z9_compression_method)
check("z10_declared_size", z10_declared_size)
check("z13_declared_ratio", z13_declared_ratio)
check("z16_declared_size_understated", z16_declared_size_understated)
check("z_constants_are_literal", z_constants_are_literal)
check("total_count_all_four_conditions", total_count_all_four_conditions)
check("source_bundle_recomputation", source_bundle_recomputation)
check("dependency_inventory_recomputation", dependency_inventory_recomputation)
check("stage_c_equivalence_recomputation", stage_c_equivalence_recomputation)
check("startup_attestation_state", startup_attestation_state)

sys.stdout.write("MT4_S3C_DRIVER_RESULTS=" + json.dumps(results) + chr(10))
"""


def _sanitised_environment():
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("PYTHON") and name not in ("VIRTUAL_ENV",)
    }
    return environment


@pytest.fixture(scope="module")
def driver_results(tmp_path_factory):
    """Run the gate under its own frozen isolated invocation contract and collect the results."""
    workspace = tmp_path_factory.mktemp("s3c_driver")
    driver = workspace / "mt4_s3c_gate_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")

    def declaration(path):
        return hashlib.sha256(path.read_bytes()).hexdigest() + ":" + str(path).replace("\\", "/")

    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        [
            sys.executable,
            "-I",
            "-S",
            str(driver),
            "--gate-module",
            str(TRUSTED_GATE),
            "--workspace-root",
            str(_REPO_ROOT),
            "--work-dir",
            str(workspace),
            "--trusted-entrypoint",
            declaration(driver),
            "--trusted-entrypoint",
            declaration(TRUSTED_GATE),
        ],
        capture_output=True,
        text=True,
        cwd=str(workspace),
        env=_sanitised_environment(),
        timeout=180,
        check=False,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    marker = "MT4_S3C_DRIVER_RESULTS="
    line = next(line for line in completed.stdout.splitlines() if line.startswith(marker))
    return json.loads(line[len(marker) :])


@pytest.mark.parametrize(
    "check_name",
    (
        "z_reference",
        "z2_member_count",
        "z3_member_name_set",
        "z6_path_traversal",
        "z9_compression_method",
        "z10_declared_size",
        "z13_declared_ratio",
        "z16_declared_size_understated",
        "z_constants_are_literal",
        "total_count_all_four_conditions",
        "source_bundle_recomputation",
        "dependency_inventory_recomputation",
        "stage_c_equivalence_recomputation",
        "startup_attestation_state",
    ),
)
def test_the_gate_behaves_as_governed_under_its_frozen_invocation(driver_results, check_name):
    assert driver_results.get(check_name) == "PASS", driver_results.get(check_name)


# =================================================================================================
# THE ATTESTATION REFUSES A BROKEN INVOCATION  [PT-217..PT-222]
# =================================================================================================


def _run_gate(extra_flags, environment_overrides=None, workspace=None):
    environment = _sanitised_environment()
    if environment_overrides:
        environment.update(environment_overrides)
    argv = [sys.executable]
    argv.extend(extra_flags)
    argv.append(str(TRUSTED_GATE))
    argv.extend(
        [
            "--workspace-root",
            str(workspace or _REPO_ROOT),
            "--work-dir",
            str(workspace or _REPO_ROOT),
            "--trusted-entrypoint",
            hashlib.sha256(TRUSTED_GATE.read_bytes()).hexdigest() + ":" + str(TRUSTED_GATE).replace("\\", "/"),
        ]
    )
    return subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        argv, capture_output=True, text=True, env=environment, timeout=120, check=False
    )


def test_pt_221_an_invocation_without_isolated_mode_is_refused():
    completed = _run_gate(["-S"])
    assert completed.returncode == 3
    assert "TRUSTED_PYTHON_INVOCATION_VIOLATION" in completed.stderr


def test_pt_222_an_invocation_without_no_site_is_refused():
    completed = _run_gate([])
    assert completed.returncode == 3
    assert "TRUSTED_PYTHON_INVOCATION_VIOLATION" in completed.stderr


@pytest.mark.parametrize(
    ("test_id", "variable"),
    (
        ("PT-217", "PYTHONPATH"),
        ("PT-218", "PYTHONHOME"),
        ("PT-219", "PYTHONSTARTUP"),
        ("PT-219b", "PYTHONINSPECT"),
    ),
)
def test_a_python_prefixed_environment_variable_is_refused(test_id, variable, tmp_path):
    completed = _run_gate(["-I", "-S"], {variable: str(tmp_path)})
    assert completed.returncode == 3, test_id
    # -I already ignores the variable's EFFECT; the gate additionally refuses its PRESENCE, because
    # the rule is a PREFIX rule and a future PYTHON* variable must be forbidden by default.
    assert "TRUSTED_PYTHON_ENVIRONMENT_VIOLATION" in completed.stderr, test_id


def test_an_undeclared_entrypoint_is_refused():
    environment = _sanitised_environment()
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        [
            sys.executable,
            "-I",
            "-S",
            str(TRUSTED_GATE),
            "--workspace-root",
            str(_REPO_ROOT),
            "--work-dir",
            str(_REPO_ROOT),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 3
    assert "TRUSTED_PYTHON_INVOCATION_VIOLATION" in completed.stderr


def test_an_entrypoint_declared_with_the_wrong_digest_is_refused():
    environment = _sanitised_environment()
    completed = subprocess.run(  # noqa: S603 - fixed interpreter, fixed argument vector
        [
            sys.executable,
            "-I",
            "-S",
            str(TRUSTED_GATE),
            "--workspace-root",
            str(_REPO_ROOT),
            "--work-dir",
            str(_REPO_ROOT),
            "--trusted-entrypoint",
            "0" * 64 + ":" + str(TRUSTED_GATE).replace("\\", "/"),
        ],
        capture_output=True,
        text=True,
        env=environment,
        timeout=120,
        check=False,
    )
    assert completed.returncode == 3
    assert "entrypoint digest mismatch" in completed.stderr


def test_the_gate_refuses_to_run_without_a_credential():
    environment = _sanitised_environment()
    environment.pop("GITHUB_TOKEN", None)
    completed = _run_gate(["-I", "-S"], environment)
    # The attestation passes; the run then fails closed on the missing credential rather than
    # proceeding with an anonymous request.
    assert completed.returncode != 0
    assert "CREDENTIAL_UNAVAILABLE" in completed.stderr or "required" in completed.stderr


def test_the_zip_streaming_policy_is_expressed_as_governed_constants_not_derivations():
    source = _gate_code()
    for constant in (
        "MAX_MEMBER_UNCOMPRESSED_JSON = 4 * 1024 * 1024",
        "MAX_WORKER_BINARY_BYTES = 8 * 1024 * 1024",
        "MAX_AGGREGATE_UNCOMPRESSED = 16 * 1024 * 1024",
        "MAX_MEMBER_COMPRESSED = 16 * 1024 * 1024",
        "MAX_ARCHIVE_BYTES = 16 * 1024 * 1024",
        "MAX_RATIO = 100",
        "CHUNK_BYTES = 65536",
    ):
        assert constant in source, constant
    # No runtime derivation and no headroom multiplier applied to an observed value.
    assert "headroom factor" not in source
    assert "DESIGN_TO_FREEZE" not in source
    # Every one of Z1..Z20 is named in the enforcing source, so a rule cannot quietly disappear.
    annotated = _gate_source()
    for rule in range(1, 21):
        assert "Z" + str(rule) in annotated, rule


def test_every_zip_rule_carries_a_distinct_failure_reason():
    source = _gate_code()
    for reason in (
        "ZIP_ARCHIVE_BYTES",
        "ZIP_MEMBER_COUNT",
        "ZIP_MEMBER_NAME_SET",
        "ZIP_DUPLICATE_MEMBER",
        "ZIP_UNSAFE_MEMBER",
        "ZIP_ENCRYPTED_MEMBER",
        "ZIP_COMPRESSION_METHOD",
        "ZIP_DECLARED_SIZE",
        "ZIP_COMPRESSED_SIZE",
        "ZIP_DECLARED_AGGREGATE",
        "ZIP_DECLARED_RATIO",
        "ZIP_MEMBER_STREAM_OVERRUN",
        "ZIP_DECLARED_SIZE_UNDERSTATED",
        "ZIP_AGGREGATE_OVERRUN",
        "ZIP_RATIO_EXCEEDED",
        "ZIP_DECLARED_SIZE_OVERSTATED",
        "ZIP_CRC_INVALID",
    ):
        assert reason in source, reason


def test_the_archive_reader_is_never_given_an_unbounded_read(tmp_path):
    # A defensive structural check that complements the behavioural ones: the only read call in the
    # streaming path is bounded by the frozen chunk size.
    code = _gate_code()
    assert "handle.read(CHUNK_BYTES)" in code
    # NO read anywhere in the gate is unbounded.  "The producer is trusted" is not a bound, which
    # is the same reason the ZIP policy exists at all.
    unbounded = [line for line in code.splitlines() if "handle.read()" in line]
    assert unbounded == [], unbounded
    assert "MAX_LOCAL_INPUT_BYTES" in code
    assert "LOCAL_INPUT_BOUND_EXCEEDED" in code
    del tmp_path
