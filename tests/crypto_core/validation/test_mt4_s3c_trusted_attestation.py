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
import copy
import hashlib
import importlib.util
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
    "zlib",
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
    """archive.read(member) decompresses BEFORE any bound is consulted, and is forbidden outright.

    The reader now goes further than avoiding that call: it does not use zipfile's member reader at
    all.  Z18's frozen semantic is CONSUMED compressed bytes, and zipfile exposes no trustworthy
    count of them, so the gate feeds a zlib decompressor itself from the raw compressed range and
    counts what it actually consumes.
    """
    code = _gate_code()
    assert "archive.read(" not in code
    assert ".read(name)" not in code
    assert "archive.open(" not in code
    assert "zlib.decompressobj(-15)" in code
    assert "CHUNK_BYTES" in code
    assert "consumed_compressed" in code
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


# =================================================================================================
# THE TRUSTED-WORKFLOW CONTIGUITY ORACLE (repair 1).
#
# The invariant is CAUSAL, not cosmetic:
#
#   FINAL_GATE_BYTES_VERIFIED -> (no checkout-controlled execution) -> EXACT_ISOLATED_INVOCATION
#
# so the validator below parses the workflow semantically enough to prove it, and every mutant that
# reintroduces an escape must fail it.  The grammar is defined HERE, independently, rather than
# derived from anything the workflow itself declares -- a validator that took its rules from the
# thing it validates proves nothing.
# =================================================================================================

CONTIGUITY_MEASUREMENT = 'if [ "${ACTUAL_GATE_SHA256}" != "${APPROVED_S3C_TRUSTED_GATE_SHA256}" ]; then'
CONTIGUITY_INVOCATION = "env -i "

# Between the measurement and the invocation only these forms may appear.  Anything else -- an
# interpreter, a checkout script, a variable assignment, a command substitution -- is an escape.
_CONTIGUITY_ALLOWED = (
    re.compile(r"^\s*$"),
    re.compile(r"^\s*#"),
    re.compile(r"^\s*fi\s*$"),
    re.compile(r'^\s*echo "S3C_[A-Z0-9_]+(=(\$\{[A-Z_]+\}|[A-Z_]+))?"\s*$'),
    re.compile(r"^\s*exit 1\s*$"),
)

# Forms that may not appear ANYWHERE in the trusted workflow.
_TRUSTED_WORKFLOW_FORBIDDEN = (
    ("an interpreter reading stdin", re.compile(r"python3?\s+-\s")),
    ("inline interpreter code", re.compile(r"python3?\s+-c\b")),
    ("a sourced script", re.compile(r"^\s*(source|\.)\s+\S", re.MULTILINE)),
    ("a repo-local action", re.compile(r"uses:\s*\./")),
    ("cross-step state mutation", re.compile(r">>\s*\$\{?GITHUB_(ENV|PATH)")),
)

# A shell CASE PATTERN is not pathname expansion: it matches a variable's value and touches no
# filesystem.  The glob rule therefore applies to command arguments, which is where an unquoted `*`
# would let the filesystem choose what a command operates on.
# Quoted spans are removed before the glob check, so a `*` inside a string is not a glob.
# The two patterns are kept separate because a single regex would have to embed both quote
# characters in one literal, which is exactly the kind of quoting knot this file should not have.
_DOUBLE_QUOTED = re.compile(r'"[^"]*"')
_SINGLE_QUOTED = re.compile(r"'[^']*'")
_EMPTY = ""

_CASE_OPEN = re.compile(r"^\s*case\s+.*\sin\s*$")
_CASE_CLOSE = re.compile(r"^\s*esac\s*$")


def _unquoted_glob(script):
    """Return the first line whose COMMAND ARGUMENTS contain an unquoted `*`, or None.

    A shell CASE PATTERN is not pathname expansion: it matches a variable's value and touches no
    filesystem.  Inside a case block the pattern prefix is therefore removed before the line is
    inspected, so `*)` is allowed while `rm ${DIR}/*` is not.
    """
    inside_case = False
    for line in script.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _CASE_OPEN.match(line):
            inside_case = True
            continue
        if _CASE_CLOSE.match(line):
            inside_case = False
            continue
        body = line
        if inside_case and ")" in body:
            body = body.split(")", 1)[1]
        without_quotes = _SINGLE_QUOTED.sub(_EMPTY, _DOUBLE_QUOTED.sub(_EMPTY, body))
        if "*" in without_quotes:
            return line
    return None


def _final_transition_step(workflow):
    steps = workflow["jobs"]["s3c-attest-trusted-evidence"]["steps"]
    matching = [step for step in steps if CONTIGUITY_MEASUREMENT in (step.get("run") or "")]
    assert len(matching) == 1, "exactly one step may measure the gate"
    return steps, matching[0]


def assert_contiguous(workflow):
    """The oracle.  Raises AssertionError when the contiguity invariant is broken."""
    steps, final = _final_transition_step(workflow)
    script = final["run"]
    assert CONTIGUITY_INVOCATION in script, "the measuring step must also invoke the gate"

    # 1. MEASUREMENT AND INVOCATION SHARE A STEP.  There is no step boundary to interpose at.
    others = [step for step in steps if step is not final and CONTIGUITY_INVOCATION in (step.get("run") or "")]
    assert others == [], "the gate is invoked outside the measuring step"

    # 2. NOTHING EXECUTABLE LIES BETWEEN THEM.
    lines = script.splitlines()
    start = next(index for index, line in enumerate(lines) if CONTIGUITY_MEASUREMENT in line)
    end = next(index for index, line in enumerate(lines) if line.lstrip().startswith(CONTIGUITY_INVOCATION))
    assert start < end, "the measurement must precede the invocation"
    for line in lines[start + 1 : end]:
        assert any(pattern.match(line) for pattern in _CONTIGUITY_ALLOWED), line

    # 3. THE MEASUREMENT ITSELF IS NOT CHECKOUT-CONTROLLED.
    before = "\n".join(lines[:start])
    assert "sha256sum" in before, "the gate bytes must be measured by a trusted system tool"
    # No INTERPRETER INVOCATION may run before the measurement.  Naming ${TRUSTED_PYTHON} while
    # validating it is not an invocation; executing python is.
    interpreter = re.compile(r"(^|[;&|]|\s)(python[0-9.]*|perl|ruby|node)\s")
    assert interpreter.search(before) is None, "no interpreter may produce the measurement"

    # 4. NO STEP ANYWHERE MAY MUTATE CROSS-STEP STATE OR RUN CHECKOUT CODE.
    for step in steps:
        script_text = step.get("run") or ""
        uses = step.get("uses") or ""
        for label, pattern in _TRUSTED_WORKFLOW_FORBIDDEN:
            assert not pattern.search(script_text), (label, step.get("name"))
            assert not pattern.search("uses: " + uses if uses else ""), (label, step.get("name"))
        assert _unquoted_glob(script_text) is None, ("a glob", step.get("name"))

    # 5. THE INVOCATION IS THE FROZEN ONE.
    invocation = "\n".join(lines[end:])
    for required in ('"${TRUSTED_PYTHON}" -I -S', '"${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"', "--trusted-entrypoint"):
        assert required in invocation, required
    return True


def test_the_final_gate_verification_is_contiguous_with_the_gate_invocation(trusted_workflow):
    assert assert_contiguous(trusted_workflow)


def _mutate(workflow, transform):
    mutant = copy.deepcopy(workflow)
    transform(mutant["jobs"]["s3c-attest-trusted-evidence"]["steps"])
    return mutant


def _insert_after_measurement(steps, injected):
    """Split the contiguous step so `injected` lands between measurement and invocation."""
    for index, step in enumerate(steps):
        script = step.get("run") or ""
        if CONTIGUITY_MEASUREMENT not in script:
            continue
        lines = script.splitlines()
        cut = next(position for position, line in enumerate(lines) if line.lstrip().startswith(CONTIGUITY_INVOCATION))
        steps[index] = dict(step, run="\n".join(lines[:cut]) + "\n")
        steps.insert(index + 1, {"name": "injected", "shell": "bash", "run": injected})
        steps.insert(index + 2, dict(step, run="\n".join(lines[cut:]) + "\n"))
        return
    raise AssertionError("no measuring step")


@pytest.mark.parametrize(
    ("label", "injected"),
    (
        ("checkout sibling json.py before gate", 'printf "" > "${GITHUB_WORKSPACE}/json.py"\n'),
        ("checkout sibling hashlib.py before gate", 'printf "" > "${GITHUB_WORKSPACE}/hashlib.py"\n'),
        ("checkout sibling subprocess.py before gate", 'printf "" > "${GITHUB_WORKSPACE}/subprocess.py"\n'),
        ("interposed python3 -", "python3 - <<'EOF'\nprint(1)\nEOF\n"),
        ("interposed checkout script", 'bash "${GITHUB_WORKSPACE}/scripts/helper.sh"\n'),
        ("post-digest gate mutation", 'printf "x" >> "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"\n'),
        ("GITHUB_ENV overrides the interpreter", 'echo "TRUSTED_PYTHON=/tmp/py" >> "${GITHUB_ENV}"\n'),
        ("GITHUB_ENV overrides the gate path", 'echo "TRUSTED_GATE_PATH=evil.py" >> "${GITHUB_ENV}"\n'),
        (
            "GITHUB_ENV overrides a security-critical value",
            'echo "APPROVED_S3C_TRUSTED_GATE_SHA256=0" >> "${GITHUB_ENV}"\n',
        ),
        ("an extra executable step", 'ls -la "${GITHUB_WORKSPACE}"\n'),
    ),
)
def test_an_interposed_step_between_verification_and_invocation_is_rejected(trusted_workflow, label, injected):
    mutant = _mutate(trusted_workflow, lambda steps: _insert_after_measurement(steps, injected))
    with pytest.raises(AssertionError):
        assert_contiguous(mutant)


def test_moving_the_invocation_into_a_separate_step_is_rejected(trusted_workflow):
    def transform(steps):
        _insert_after_measurement(steps, 'echo "S3C_HARMLESS"\n')

    mutant = _mutate(trusted_workflow, transform)
    # Even a harmless-looking echo in its OWN step breaks contiguity, because a step boundary is
    # precisely the place another change can later be inserted.
    with pytest.raises(AssertionError):
        assert_contiguous(mutant)


def test_a_repo_local_action_anywhere_in_the_trusted_workflow_is_rejected(trusted_workflow):
    def transform(steps):
        steps.insert(1, {"name": "local action", "uses": "./.github/actions/helper"})

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


def test_an_interpreter_producing_the_measurement_is_rejected(trusted_workflow):
    def transform(steps):
        for index, step in enumerate(steps):
            script = step.get("run") or ""
            if CONTIGUITY_MEASUREMENT in script:
                steps[index] = dict(
                    step,
                    run=script.replace(
                        'sha256sum "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"',
                        'python3 -c "import hashlib" && sha256sum "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"',
                    ),
                )
                return
        raise AssertionError("no measuring step")

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


def test_the_bundle_inventory_is_built_without_any_interpreter(trusted_workflow):
    """The `python3 -` helper that built the inventory WAS the pre-gate import surface.

    Its sys.path[0] is the working directory, so a checkout sibling named json.py, hashlib.py or
    subprocess.py would have been imported by it -- before the gate's own origin attestation could
    possibly run.  The inventory is now built with git and sha256sum alone.
    """
    steps = trusted_workflow["jobs"]["s3c-attest-trusted-evidence"]["steps"]
    inventory = [step for step in steps if "source bundle inventory" in (step.get("name") or "")]
    assert len(inventory) == 1
    script = inventory[0]["run"]
    assert "python" not in script.lower()
    assert "git ls-tree" in script and "git cat-file" in script and "sha256sum" in script
    # Arithmetic expansion $((...)) is not command substitution; only $(cmd) is.
    assert re.search(r"\$\((?!\()", script) is None, "no command substitution"
    assert "`" not in script, "no backtick substitution"


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


def _bundle_entries():
    return [
        {"path": path, "mode": "100644", "type": "blob", "sha256": format(index, "064x")}
        for index, path in enumerate(gate.SOURCE_BUNDLE_PATHS)
    ]


def _complete_inventory():
    # A COMPLETE, well-formed compile inventory: every required translation unit and both pinned
    # upstream inputs, each with its class-determined provenance.
    bundle = {entry["path"]: entry["sha256"] for entry in _bundle_entries()}
    entries = [
        {
            "path": path,
            "class": "REPO_BUNDLED",
            "provenance": gate.PROVENANCE_REPO_BUNDLED,
            "sha256": bundle[path],
        }
        for path in gate.REQUIRED_TRANSLATION_UNITS
    ]
    entries += [
        {
            "path": path,
            "class": "UPSTREAM_PINNED",
            "provenance": gate.PROVENANCE_UPSTREAM_PINNED,
            "sha256": format(700 + index, "064x"),
        }
        for index, path in enumerate(gate.REQUIRED_UPSTREAM_INPUTS)
    ]
    entries.append(
        {
            "path": "usr/include/stdio.h",
            "class": "EXTERNAL_TOOLCHAIN",
            "provenance": gate.PROVENANCE_EXTERNAL_TOOLCHAIN,
            "sha256": "",
        }
    )
    entries.sort(key=lambda entry: entry["path"])
    return {
        "schema": gate.DEPENDENCY_SCHEMA,
        "entry_count": len(entries),
        "entries": entries,
        "path_order": [entry["path"] for entry in entries],
    }


def dependency_inventory_recomputation():
    bundle = _bundle_entries()
    payload = _complete_inventory()
    digest = gate.recompute_dependency_inventory_digest(payload, bundle)
    assert len(digest) == 64

    def mutate(transform):
        mutant = json.loads(json.dumps(payload))
        transform(mutant)
        mutant["entry_count"] = len(mutant["entries"])
        mutant["path_order"] = [entry["path"] for entry in mutant["entries"]]
        return mutant

    def tamper_digest(mutant):
        for entry in mutant["entries"]:
            if entry["class"] == "REPO_BUNDLED":
                entry["sha256"] = format(999, "064x")
                return

    expect(
        "COMPILE_DEPENDENCY_INVENTORY_MISMATCH",
        lambda: gate.recompute_dependency_inventory_digest(mutate(tamper_digest), bundle),
    )

    def add_unbundled(mutant):
        mutant["entries"].append(
            {
                "path": "src/crypto_core/__init__.py",
                "class": "REPO_BUNDLED",
                "provenance": gate.PROVENANCE_REPO_BUNDLED,
                "sha256": format(3, "064x"),
            }
        )
        mutant["entries"].sort(key=lambda entry: entry["path"])

    expect(
        "SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED",
        lambda: gate.recompute_dependency_inventory_digest(mutate(add_unbundled), bundle),
    )

    # Repair 7E, at the boundary: dropping the observer translation unit, the probe translation
    # unit or a pinned upstream input makes the inventory incomplete.
    for missing in (
        "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
        "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
        "src/server.c",
        "build/assembly.S",
    ):

        def drop(mutant, path=missing):
            mutant["entries"] = [entry for entry in mutant["entries"] if entry["path"] != path]

        expect(
            "COMPILE_INVENTORY_INCOMPLETE",
            lambda transform=drop: gate.recompute_dependency_inventory_digest(mutate(transform), bundle),
        )

    # Repair 7F: weak or missing provenance, a duplicate row, an extra field and a wrong order.
    def weaken_provenance(mutant):
        mutant["entries"][0]["provenance"] = "DEPENDENCY_EXISTS"

    expect(
        "COMPILE_DEPENDENCY_PROVENANCE_INVALID",
        lambda: gate.recompute_dependency_inventory_digest(mutate(weaken_provenance), bundle),
    )

    def duplicate_row(mutant):
        mutant["entries"].append(json.loads(json.dumps(mutant["entries"][0])))
        mutant["entries"].sort(key=lambda entry: entry["path"])

    expect(
        "COMPILE_DEPENDENCY_DUPLICATE_PATH",
        lambda: gate.recompute_dependency_inventory_digest(mutate(duplicate_row), bundle),
    )

    def extra_field(mutant):
        mutant["entries"][0]["note"] = "extra"

    expect(
        "COMPILE_DEPENDENCY_INVENTORY_MISMATCH",
        lambda: gate.recompute_dependency_inventory_digest(mutate(extra_field), bundle),
    )

    reordered = json.loads(json.dumps(payload))
    reordered["entries"] = list(reversed(reordered["entries"]))
    expect(
        "COMPILE_DEPENDENCY_INVENTORY_MISMATCH",
        lambda: gate.recompute_dependency_inventory_digest(reordered, bundle),
    )

    # A substituted inventory digest cannot survive, because the digest is RECOMPUTED here.
    substituted = json.loads(json.dumps(payload))
    substituted["entry_count"] = len(substituted["entries"]) + 1
    expect(
        "COMPILE_DEPENDENCY_INVENTORY_MISMATCH",
        lambda: gate.recompute_dependency_inventory_digest(substituted, bundle),
    )


# =================================================================================================
# THE SELF-ANCHORED STAGE-C AUTHORITY (repair 2).
# =================================================================================================

_FPROG_VA = 0x4016A0
_PROGRAM_VA = 0x401700


def _canonical():
    return gate.stage_c_canonical_internal_policy()


def _elf_record(canonical, **overrides):
    objects = {
        "fprog_symbol": "mt4_s3c_internal_filter_fprog",
        "fprog_va_u64": _FPROG_VA,
        "fprog_file_offset_u64": 0x16A0,
        "fprog_size_bytes": 16,
        "fprog_segment_flags_u32": 5,
        "program_symbol": "mt4_s3c_internal_filter_program",
        "program_va_u64": _PROGRAM_VA,
        "program_file_offset_u64": 0x1700,
        "program_size_bytes": canonical["cbpf_instruction_count"] * 8,
        "program_segment_flags_u32": 5,
        "program_instruction_count": canonical["cbpf_instruction_count"],
        "program_bytes_sha256": canonical["program_bytes_sha256"],
    }
    objects.update(overrides)
    return {"canonical_internal_filter_object": objects}


def _observation(canonical, **overrides):
    record = {
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "source_run_id": 4242,
        "source_run_attempt": 1,
        "source_head_sha": "c" * 40,
        "candidate_binary_sha256": "d" * 64,
    }
    record.update(overrides)
    return record


def _case(canonical, **overrides):
    record = {
        "case_id": "C01_POSITIVE_EXACT_FIXTURE",
        "internal_capture": {
            "program_bytes_hex": canonical["cbpf_program_bytes"].hex(),
            "fprog_va_u64": _FPROG_VA,
            "filter_va_u64": _PROGRAM_VA,
            "length": canonical["cbpf_instruction_count"],
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
        "internal_filter_equivalence": {"valid": True, "digest_sha256": ""},
    }
    record.update(overrides)
    return record


def stage_c_self_anchored_authority():
    # Stage C derives the canonical policy from its OWN constants, never from A3.
    canonical = _canonical()
    assert canonical["policy_id"] == "MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64"
    assert canonical["cbpf_instruction_count"] == 113
    assert canonical["policy_sha256"] == gate.EXPECTED_INTERNAL_POLICY_SHA256
    assert canonical["cbpf_sha256"] == gate.EXPECTED_INTERNAL_CBPF_SHA256
    # The POLICY BYTES exist, not merely a pinned digest: the document is reconstructed.
    assert canonical["semantic_bytes"].startswith(b'{"alternate_abi_policy"')
    assert b'"policy_domain":"MT4_S3C_INTERNAL_CONTAINMENT_P0_LINUX_X86_64"' in canonical["semantic_bytes"]
    assert len(canonical["cbpf_program_bytes"]) == 113 * 8
    # And the case-set inventory is reconstructed and digested here too.
    assert gate.stage_c_case_set_digest() == gate.EXPECTED_CASE_SET_DIGEST
    assert len(gate.TRUSTED_CASE_IDS) == 25


def stage_c_equivalence_recomputation():
    canonical = _canonical()
    elf_record = _elf_record(canonical)
    filter_object = gate.stage_c_validate_filter_object(elf_record, canonical)
    observation = _observation(canonical)
    case = _case(canonical)

    # The honest digest, discovered by asking Stage C what it recomputes.
    try:
        gate.stage_c_equivalence_digest(observation, case, "", canonical, filter_object)
        raise AssertionError("an empty A3 digest must not pass")
    except gate.TrustedGateError as error:
        assert "A3 vs Stage C" in str(error)

    honest = gate.domain_digest(
        gate.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN,
        {
            "schema": gate.INTERNAL_EQUIVALENCE_SCHEMA,
            "canonical_internal_policy_id": canonical["policy_id"],
            "canonical_internal_policy_sha256": canonical["policy_sha256"],
            "program_representation_version": gate.PROGRAM_REPRESENTATION_VERSION,
            "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
            "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
            "captured_internal_cbpf_sha256": canonical["cbpf_sha256"],
            "captured_internal_uargs_va_u64": _FPROG_VA,
            "captured_internal_len_u32": canonical["cbpf_instruction_count"],
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
    case["internal_filter_equivalence"]["digest_sha256"] = honest
    assert gate.stage_c_equivalence_digest(observation, case, honest, canonical, filter_object) == honest

    # A4 alone changed -> mismatch.  A3 alone changed -> mismatch.  Both must agree with Stage C.
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH",
        lambda: gate.stage_c_equivalence_digest(observation, case, "e" * 64, canonical, filter_object),
    )
    tampered = json.loads(json.dumps(case))
    tampered["internal_filter_equivalence"]["digest_sha256"] = "f" * 64
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_DIGEST_MISMATCH",
        lambda: gate.stage_c_equivalence_digest(observation, tampered, honest, canonical, filter_object),
    )
    broken = json.loads(json.dumps(case))
    broken["seccomp_baseline"]["child_filters"] = 1
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_CONSTRAINT_VIOLATED",
        lambda: gate.stage_c_equivalence_digest(observation, broken, honest, canonical, filter_object),
    )


def coordinated_reseal_is_rejected():
    # THE CENTRAL REPAIR-2 ORACLE.
    #
    # A3 and A4 are resealed TOGETHER and CONSISTENTLY with the same false value, so every
    # cross-record equality the old gate relied on still holds.  Each substitution must still fail,
    # because the authority it contradicts is Stage C's own reconstruction rather than anything the
    # unprivileged job supplied.
    #
    canonical = _canonical()
    elf_record = _elf_record(canonical)
    filter_object = gate.stage_c_validate_filter_object(elf_record, canonical)

    def sealed(observation, case):
        # Recompute the digest the way a resealing attacker would, then present it as A3 AND A4.
        # The attacker cannot know Stage C's expected digest, but can make A3 and A4 agree with
        # each other perfectly.  That agreement is what must stop being sufficient.
        forged = "9" * 64
        case = json.loads(json.dumps(case))
        case["internal_filter_equivalence"]["digest_sha256"] = forged
        return lambda: gate.stage_c_equivalence_digest(observation, case, forged, canonical, filter_object)

    # 1. A false internal policy ID, declared consistently.
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(_observation(canonical, canonical_internal_policy_id="ATTACKER_POLICY"), _case(canonical)),
    )
    # 2. A false internal policy digest.
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(_observation(canonical, canonical_internal_policy_sha256="a" * 64), _case(canonical)),
    )
    # 3. A false cBPF instruction count.
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(_observation(canonical, canonical_internal_cbpf_instruction_count=112), _case(canonical)),
    )
    # 4. A false cBPF digest, with a capture that matches it -- the fully consistent reseal.
    weaker = bytes(113 * 8)
    coordinated_case = _case(canonical)
    coordinated_case["internal_capture"]["program_bytes_hex"] = weaker.hex()
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(_observation(canonical, canonical_internal_cbpf_sha256=gate.cbpf_digest(weaker)), coordinated_case),
    )
    # 5. A capture at an address the authenticated ELF record does not place the object at.
    moved = _case(canonical)
    moved["internal_capture"]["fprog_va_u64"] = 0x7FFF00000000
    expect("INTERNAL_FILTER_EQUIVALENCE_FAILED", sealed(_observation(canonical), moved))
    moved_filter = _case(canonical)
    moved_filter["internal_capture"]["filter_va_u64"] = 0x7FFF00000000
    expect("INTERNAL_FILTER_EQUIVALENCE_FAILED", sealed(_observation(canonical), moved_filter))
    # 6. An ELF record that claims a DIFFERENT program at the same address.
    expect(
        "FILTER_OBJECT_BINDING_INVALID",
        lambda: gate.stage_c_validate_filter_object(_elf_record(canonical, program_bytes_sha256="b" * 64), canonical),
    )
    expect(
        "FILTER_OBJECT_BINDING_INVALID",
        lambda: gate.stage_c_validate_filter_object(_elf_record(canonical, program_instruction_count=112), canonical),
    )
    # 7. A writable filter mapping is never an acceptable home for the canonical object.
    expect(
        "FILTER_OBJECT_BINDING_INVALID",
        lambda: gate.stage_c_validate_filter_object(_elf_record(canonical, program_segment_flags_u32=6), canonical),
    )
    # 8. A false case-set digest cannot be adopted: Stage C recomputes it from its own table.
    assert gate.stage_c_case_set_digest() != "0" * 64


def zip_runtime_consumption_and_reachable_rules():
    # Z13 and Z18 are DIFFERENT rules, and Z18 counts real consumed compressed bytes.
    body = bytes((index * 7 + (index >> 3)) & 0xFF for index in range(40000))
    payload = build_archive([(WORKER, body), (MANIFEST, b"{}")])
    contents, _digests = gate.extract_artifact(payload, gate.EXPECTED_MEMBERS[CANDIDATE])
    assert contents[WORKER] == body

    # A STORED member round-trips through the same accounting path.
    stored = build_archive([(WORKER, body), (MANIFEST, b"{}")], zipfile.ZIP_STORED)
    contents, _digests = gate.extract_artifact(stored, gate.EXPECTED_MEMBERS[CANDIDATE])
    assert contents[WORKER] == body

    # Z13 owns the DECLARED ratio.  201 / 2 is 100.5, which floor division reported as exactly 100
    # and therefore missed; the exact inequality catches it.
    class _Info:
        filename = WORKER
        file_size = 201
        compress_size = 2
        compress_type = 8
        flag_bits = 0
        external_attr = 0

        def is_dir(self):
            return False

    class _Archive:
        def infolist(self):
            return [_Info(), _Info2()]

    class _Info2(_Info):
        filename = MANIFEST
        file_size = 2
        compress_size = 2

    expect(
        "ZIP_DECLARED_RATIO",
        lambda: gate.pre_decompression_gate(_Archive(), b"x" * 100, gate.EXPECTED_MEMBERS[CANDIDATE]),
    )

    # A zero declared compressed size carrying content is a ratio no bound can express.
    class _Zero(_Info):
        file_size = 10
        compress_size = 0

    class _ZeroArchive:
        def infolist(self):
            return [_Zero(), _Info2()]

    expect(
        "ZIP_DECLARED_RATIO",
        lambda: gate.pre_decompression_gate(_ZeroArchive(), b"x" * 100, gate.EXPECTED_MEMBERS[CANDIDATE]),
    )

    # Z4 is REACHABLE: a duplicated member reaches the duplicate rule, not the name-set rule.
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(WORKER, b"a")
        archive.writestr(WORKER, b"b")
    expect(
        "ZIP_DUPLICATE_MEMBER",
        lambda: gate.extract_artifact(buffer.getvalue(), gate.EXPECTED_MEMBERS[CANDIDATE]),
    )

    # Z18 against REAL consumption: a central directory that understates compress_size is caught
    # by the consumed-byte reconciliation rather than believed.
    honest = build_archive([(WORKER, body), (MANIFEST, b"{}")])
    lied = bytearray(honest)
    marker = honest.find(b"PK\x01\x02")
    assert marker > 0
    # compress_size lives at offset 20 of a central directory entry.
    original = int.from_bytes(lied[marker + 20 : marker + 24], "little")
    lied[marker + 20 : marker + 24] = (original - 1).to_bytes(4, "little")
    expect(
        "ZIP_COMPRESSED_SIZE_MISDECLARED",
        lambda: gate.extract_artifact(bytes(lied), gate.EXPECTED_MEMBERS[CANDIDATE]),
    )


def startup_attestation_state():
    assert sys.flags.isolated == 1
    assert sys.flags.no_site == 1
    assert gate.ORIGIN_DECLARED_ENTRYPOINT in gate.ALLOWED_ORIGIN_CLASSES
    assert len(gate._DECLARED_ENTRYPOINTS) == 2
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
check("stage_c_self_anchored_authority", stage_c_self_anchored_authority)
check("stage_c_equivalence_recomputation", stage_c_equivalence_recomputation)
check("coordinated_reseal_is_rejected", coordinated_reseal_is_rejected)
check("zip_runtime_consumption_and_reachable_rules", zip_runtime_consumption_and_reachable_rules)
check("startup_attestation_state", startup_attestation_state)

canonical = gate.stage_c_canonical_internal_policy()
values = {
    "policy_id": canonical["policy_id"],
    "policy_sha256": canonical["policy_sha256"],
    "cbpf_sha256": canonical["cbpf_sha256"],
    "cbpf_instruction_count": canonical["cbpf_instruction_count"],
    "case_set_digest": gate.stage_c_case_set_digest(),
    "case_ids": list(gate.TRUSTED_CASE_IDS),
    "required_translation_units": list(gate.REQUIRED_TRANSLATION_UNITS),
    "source_bundle_paths": list(gate.SOURCE_BUNDLE_PATHS),
}
sys.stdout.write("MT4_S3C_DRIVER_VALUES=" + json.dumps(values) + chr(10))
sys.stdout.write("MT4_S3C_DRIVER_RESULTS=" + json.dumps(results) + chr(10))
"""


def _sanitised_environment():
    environment = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith("PYTHON") and name not in ("VIRTUAL_ENV",)
    }
    return environment


_DRIVER_VALUES = []


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
    values_marker = "MT4_S3C_DRIVER_VALUES="
    values_line = next(line for line in completed.stdout.splitlines() if line.startswith(values_marker))
    _DRIVER_VALUES.append(json.loads(values_line[len(values_marker) :]))
    marker = "MT4_S3C_DRIVER_RESULTS="
    line = next(line for line in completed.stdout.splitlines() if line.startswith(marker))
    return json.loads(line[len(marker) :])


@pytest.fixture(scope="module")
def driver_values(driver_results):
    """The values Stage C DERIVED, exported from the same isolated run."""
    del driver_results
    return _DRIVER_VALUES[0]


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
        "stage_c_self_anchored_authority",
        "stage_c_equivalence_recomputation",
        "coordinated_reseal_is_rejected",
        "zip_runtime_consumption_and_reachable_rules",
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


def test_no_read_anywhere_in_the_gate_is_unbounded():
    """Repair 6D.  EVERY read is bounded -- archive members, local files AND API responses.

    "The producer is trusted" is not a bound, which is the same reason the ZIP policy exists at
    all.  An unbounded metadata response is exactly as effective a resource attack as a zip bomb.
    """
    code = _gate_code()
    unbounded = [
        line
        for line in code.splitlines()
        if re.search(r"\.read\(\s*\)", line) and "read(MAX" not in line and "read(CHUNK" not in line
    ]
    assert unbounded == [], unbounded
    assert "MAX_LOCAL_INPUT_BYTES" in code
    assert "LOCAL_INPUT_BOUND_EXCEEDED" in code
    # The API body is read at LIMIT+1 so that reaching the limit is DETECTED, not truncated.
    assert "response.read(MAX_API_RESPONSE_BYTES + 1)" in code
    assert "GITHUB_API_RESPONSE_BOUND_EXCEEDED" in code
    assert "handle.read(MAX_LOCAL_INPUT_BYTES + 1)" in code


def test_malformed_untrusted_input_never_escapes_as_an_exception_string():
    """Repair 6E.  Malformed JSON, UTF-8 or hex becomes a FROZEN reason class.

    A raw traceback or an exception message would put attacker-influenced bytes into an operator's
    log and would describe the input rather than naming the rule it violated.
    """
    code = _gate_code()
    # Every untrusted decode goes through the frozen decoders.
    assert "def decode_json(body, marker):" in code
    assert "def decode_hex(value, marker):" in code
    assert "json.loads(payloads[" not in code
    assert "bytes.fromhex(require_str(" not in code
    # No failure detail interpolates a caught exception's text.
    assert "str(error))" not in code.replace("str(error) + ", "")
    for frozen in ("ZIP_DEFLATE_STREAM_INVALID", "ZIP_ARCHIVE_MALFORMED", "OBSERVATION_MALFORMED"):
        assert frozen in code, frozen
    # And no member NAME is echoed: names come from the archive and are untrusted.
    assert 'fail("ZIP_UNSAFE_MEMBER", "path " + name)' not in code
    assert 'fail("ZIP_MEMBER_NAME_SET", ",".join(sorted(names)))' not in code


# =================================================================================================
# THE THREE INDEPENDENT COMPUTATIONS MUST AGREE.
#
# Stage C reconstructs the canonical internal policy and the canonical case inventory from its OWN
# frozen constants, which is what makes it an authority A3 and A4 cannot choose.  That independence
# would be worthless if the three implementations were allowed to drift apart, so the agreement is
# asserted here, permanently, against the derivations the bundled modules actually perform.
# =================================================================================================

_S3C_SCRIPTS = _REPO_ROOT / "scripts" / "crypto_core" / "qualification" / "s3c"


def _load_bundled(name, filename):
    specification = importlib.util.spec_from_file_location(name, _S3C_SCRIPTS / filename)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


_X86_64_UAPI = {
    "audit_architecture_value_u32": 0xC000003E,
    "x32_syscall_bit_u32": 0x40000000,
    "seccomp_set_mode_filter_u32": 1,
    "seccomp_ret_allow_u32": 0x7FFF0000,
    "seccomp_ret_kill_process_u32": 0x80000000,
    "pr_set_dumpable_u32": 4,
    "pr_set_no_new_privs_u32": 38,
    "seccomp_data_offset_nr_u32": 0,
    "seccomp_data_offset_arch_u32": 4,
    "seccomp_data_offset_arg_lo_u32": (16, 24, 32, 40, 48, 56),
    "seccomp_data_offset_arg_hi_u32": (20, 28, 36, 44, 52, 60),
    "syscall_nr_u32": {
        "read": 0,
        "write": 1,
        "close": 3,
        "execve": 59,
        "prctl": 157,
        "exit_group": 231,
        "seccomp": 317,
        "close_range": 436,
    },
    "bpf_opcode_u16": {
        "ld_w_abs": 0x20,
        "jmp_jeq_k": 0x15,
        "jmp_jge_k": 0x35,
        "jmp_jgt_k": 0x25,
        "jmp_ja": 0x05,
        "ret_k": 0x06,
    },
}


def test_stage_c_reconstruction_equals_the_bundled_policy_derivation(driver_values):
    """Stage C's independent emitter reproduces the bundled qualifier's canonical internal policy."""
    qualifier = _load_bundled("mt4_s3c_policy_qualifier_consistency", "mt4_s3c_sandbox_policy_qualifier.py")
    qualifier._validate_constant_relations(_X86_64_UAPI)
    program = qualifier.derive_program(_X86_64_UAPI, qualifier._INTERNAL_INVENTORY)
    record = qualifier.build_policy_record(
        _X86_64_UAPI,
        qualifier._INTERNAL_INVENTORY,
        qualifier.INTERNAL_POLICY_SCHEMA,
        qualifier.INTERNAL_POLICY_DIGEST_DOMAIN,
        qualifier.INTERNAL_POLICY_DOMAIN,
        program,
    )
    assert driver_values["policy_id"] == qualifier.INTERNAL_POLICY_DOMAIN
    assert driver_values["policy_sha256"] == record["semantic_digest_sha256"]
    assert driver_values["cbpf_sha256"] == record["emitted_cbpf_sha256"]
    assert driver_values["cbpf_instruction_count"] == qualifier.FROZEN_INTERNAL_PROGRAM_LEN


def test_stage_c_case_inventory_equals_the_adjudicator_derivation(driver_values):
    """The trusted table is exactly the inventory the adjudicator DERIVES from its executable rules.

    The table is a literal on the trusted surface precisely so that no candidate input can reshape
    it; this test is what stops that literal from quietly diverging from the rules it mirrors.
    """
    adjudicator = _load_bundled("mt4_s3c_adjudicator_consistency", "mt4_s3c_observation_adjudicator.py")
    assert driver_values["case_ids"] == list(adjudicator.FROZEN_CASE_IDS)
    assert driver_values["case_set_digest"] == adjudicator.observation_case_set_digest()
    assert len(driver_values["case_ids"]) == adjudicator.EXACT_CASE_COUNT


def test_stage_c_and_the_build_manifest_agree_on_the_required_inventory(driver_values):
    manifest = _load_bundled("mt4_s3c_build_manifest_consistency", "mt4_s3c_build_manifest.py")
    assert driver_values["required_translation_units"] == list(manifest.REQUIRED_TRANSLATION_UNITS)
    assert driver_values["source_bundle_paths"] == list(manifest.SOURCE_BUNDLE_PATHS)
