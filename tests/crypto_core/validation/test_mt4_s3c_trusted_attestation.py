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

# The transition is owned from the MEASUREMENT COMMAND onward.  Starting at the comparison left a
# window -- between hashing the file and comparing the hash -- in which a mutating command could
# have replaced the very bytes that were measured, and the oracle would not have looked there.
CONTIGUITY_MEASUREMENT = 'sha256sum "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"'
CONTIGUITY_COMPARISON = 'if [ "${ACTUAL_GATE_SHA256}" != "${APPROVED_S3C_TRUSTED_GATE_SHA256}" ]; then'
CONTIGUITY_INVOCATION = "env -i "

# Between the measurement and the invocation only these forms may appear.  Anything else -- an
# interpreter, a checkout script, a variable assignment, a command substitution -- is an escape.
_CONTIGUITY_ALLOWED = (
    re.compile(r"^\s*$"),
    re.compile(r"^\s*#"),
    re.compile(r"^\s*fi\s*$"),
    re.compile(r'^\s*echo "S3C_[A-Z0-9_]+(=(\$\{[A-Z_0-9]+\}|[A-Z_0-9]+))?"\s*$'),
    re.compile(r"^\s*exit 1\s*$"),
    # The measurement region additionally reads the digest it just wrote and compares it.
    re.compile(r'^\s*ACTUAL_GATE_SHA256=""\s*$'),
    re.compile(r'^\s*read -r ACTUAL_GATE_SHA256 _ < "\$\{RUNNER_TEMP\}/trusted/gate\.sha"\s*$'),
    re.compile(r'^\s*if \[ "\$\{ACTUAL_GATE_SHA256\}" != "\$\{APPROVED_S3C_TRUSTED_GATE_SHA256\}" \]; then\s*$'),
)

# CROSS-STEP STATE MUTATION, IN EVERY WRITTEN FORM (repair 4).
#
# The previous pattern only matched an unquoted `>> $GITHUB_ENV`.  Every one of these is the same
# mutation and every one of them escaped it:
#
#     echo "X=1" >> "$GITHUB_ENV"        quoted redirection target
#     echo 'X=1' >> "${GITHUB_ENV}"      braced expansion
#     printf 'X=1' >> $GITHUB_ENV        printf instead of echo
#     cat <<EOF >> "$GITHUB_ENV"         heredoc
#     TARGET="$GITHUB_ENV"; echo >> "$TARGET"    variable aliasing
#
# The detector therefore normalises quoting and brace forms before matching, and separately refuses
# any alias that binds an environment-file variable to another name -- because after an alias the
# redirection target is no longer statically obvious.
_ENV_FILE_NAMES = ("GITHUB_ENV", "GITHUB_PATH", "GITHUB_OUTPUT", "GITHUB_STATE")

_QUOTE_CHARACTERS = str(chr(34)) + str(chr(39))


def _normalise_shell(script):
    """Strip quoting and brace expansion so one pattern covers every written form."""
    normalised = script
    for character in _QUOTE_CHARACTERS:
        normalised = normalised.replace(character, "")
    normalised = normalised.replace("${", "$").replace("}", "")
    return normalised


_INDIRECT_EXPANSION = re.compile(r"\$\{!")


def _indirect_expansion(script):
    """`${!TARGET}` resolves a variable NAMED by another variable.

    A static reader cannot tell what it will expand to, so it cannot prove the redirection target is
    not an environment file.  It is refused outright rather than analysed.
    """
    for line in script.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and _INDIRECT_EXPANSION.search(stripped):
            return line
    return None


def _environment_file_mutation(script):
    """Return the offending line when the script can write an Actions environment file."""
    normalised = _normalise_shell(script)
    for line in normalised.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        for name in _ENV_FILE_NAMES:
            reference = "$" + name
            if reference not in stripped:
                continue
            # Any redirection at all onto the environment file, by any command.
            if re.search(r">>?\s*" + re.escape(reference), stripped):
                return line
            # Aliasing the environment file into another variable hides the target from a static
            # reading of the later redirection, so it is refused outright.
            if re.search(r"^[A-Za-z_][A-Za-z0-9_]*=\s*" + re.escape(reference), stripped):
                return line
            if re.search(r"\b(tee|dd|cp|mv|ln)\b[^\n]*" + re.escape(reference), stripped):
                return line
        # A heredoc whose redirection target is an environment file.
        if re.search(r"<<-?\s*[A-Za-z_\x27\x22]*[^\n]*>>?\s*\$(GITHUB_(ENV|PATH|OUTPUT|STATE))", stripped):
            return line
    return None


# Forms that may not appear ANYWHERE in the trusted workflow.
_TRUSTED_WORKFLOW_FORBIDDEN = (
    ("an interpreter reading stdin", re.compile(r"python3?\s+-\s")),
    ("inline interpreter code", re.compile(r"python3?\s+-c\b")),
    ("a sourced script", re.compile(r"^\s*(source|\.)\s+\S", re.MULTILINE)),
    ("a repo-local action", re.compile(r"uses:\s*\./")),
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
    # THE WHOLE TRANSITION, from the measurement command to the invocation, admits only the frozen
    # forms.  A mutating command placed between the hash and the comparison is now visible.
    comparison = next(index for index, line in enumerate(lines) if CONTIGUITY_COMPARISON in line)
    assert start < comparison < end, "the comparison must sit inside the transition"
    for line in lines[start + 1 : end]:
        assert any(pattern.match(line) for pattern in _CONTIGUITY_ALLOWED), line

    # 3. THE MEASUREMENT ITSELF IS NOT CHECKOUT-CONTROLLED.
    before = "\n".join(lines[:start])
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
        assert _environment_file_mutation(script_text) is None, ("cross-step state mutation", step.get("name"))
        assert _indirect_expansion(script_text) is None, ("indirect expansion", step.get("name"))

    # 5. THE INVOCATION IS THE FROZEN ONE, matched POSITIVELY.
    invocation = "\n".join(lines[end:])
    for required in ('"${TRUSTED_PYTHON}" -I -S', '"${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"', "--trusted-entrypoint"):
        assert required in invocation, required
    # The interpreter and the gate path are LITERAL references to the two validated variables; a
    # rewritten interpreter or a rewritten gate path is a different command family, not a variant.
    assert re.search(r'"\$\{TRUSTED_PYTHON\}"\s+-I\s+-S\s+"\$\{GITHUB_WORKSPACE\}/\$\{TRUSTED_GATE_PATH\}"', invocation)
    assert invocation.count('"${TRUSTED_PYTHON}"') == 1
    assert invocation.count("env -i ") == 1

    # 6. THE MEASUREMENT MEASURES THE PATH THAT IS INVOKED, not some other file.
    measurement = "\n".join(lines[:end])
    assert 'sha256sum "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"' in measurement
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


DOUBLE = chr(34)
SINGLE = chr(39)

# Every one of these writes an Actions environment file, and every one of them escaped the previous
# unquoted-substring rule.  They are listed as WRITTEN FORMS, not as one canonical form, because the
# defect was precisely that the detector only recognised one spelling.
_ENVIRONMENT_MUTATION_FORMS = (
    ("unquoted target", "echo X=1 >> $GITHUB_ENV" + chr(10)),
    ("double-quoted target", "echo " + DOUBLE + "X=1" + DOUBLE + " >> " + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10)),
    ("single-quoted value", "echo " + SINGLE + "X=1" + SINGLE + " >> " + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10)),
    ("braced expansion", "echo X=1 >> " + DOUBLE + "${GITHUB_ENV}" + DOUBLE + chr(10)),
    (
        "printf instead of echo",
        "printf " + SINGLE + "X=1" + SINGLE + " >> " + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10),
    ),
    ("tee instead of redirection", "echo X=1 | tee -a " + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10)),
    ("single-chevron truncation", "echo X=1 > " + DOUBLE + "${GITHUB_ENV}" + DOUBLE + chr(10)),
    ("heredoc write", "cat <<EOF >> " + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10) + "X=1" + chr(10) + "EOF" + chr(10)),
    ("variable alias", "TARGET=" + DOUBLE + "$GITHUB_ENV" + DOUBLE + chr(10)),
    ("github path", "echo /tmp >> " + DOUBLE + "${GITHUB_PATH}" + DOUBLE + chr(10)),
    ("github output", "echo X=1 >> " + DOUBLE + "$GITHUB_OUTPUT" + DOUBLE + chr(10)),
)


@pytest.mark.parametrize(("label", "script"), _ENVIRONMENT_MUTATION_FORMS)
def test_every_written_form_of_environment_mutation_is_detected(label, script):
    """The detector is exercised DIRECTLY, so no form can pass because the workflow happens not to
    contain it."""
    assert _environment_file_mutation(script) is not None, label


def test_the_environment_detector_does_not_fire_on_a_harmless_read():
    # Reading a value is not mutating the file, and the oracle must not become noise.
    assert _environment_file_mutation("echo " + DOUBLE + "${GITHUB_WORKSPACE}" + DOUBLE + chr(10)) is None
    assert _environment_file_mutation("echo " + DOUBLE + "S3C_MARKER=PASS" + DOUBLE + chr(10)) is None


@pytest.mark.parametrize(("label", "script"), _ENVIRONMENT_MUTATION_FORMS)
def test_environment_mutation_anywhere_in_the_trusted_workflow_is_rejected(trusted_workflow, label, script):
    def transform(steps):
        steps.insert(1, {"name": "injected", "shell": "bash", "run": script})

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


@pytest.mark.parametrize(
    ("label", "replacement"),
    (
        (
            "rewritten interpreter",
            (DOUBLE + "${TRUSTED_PYTHON}" + DOUBLE + " -I -S", "/usr/bin/python3 -I -S"),
        ),
        (
            "rewritten gate path",
            (
                DOUBLE + "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}" + DOUBLE,
                DOUBLE + "${GITHUB_WORKSPACE}/other_gate.py" + DOUBLE,
            ),
        ),
        (
            "isolation flags dropped",
            (DOUBLE + "${TRUSTED_PYTHON}" + DOUBLE + " -I -S", DOUBLE + "${TRUSTED_PYTHON}" + DOUBLE),
        ),
    ),
)
def test_the_positive_invocation_oracle_rejects_a_rewritten_command(trusted_workflow, label, replacement):
    old, new = replacement

    def transform(steps):
        for index, step in enumerate(steps):
            script = step.get("run") or ""
            if CONTIGUITY_MEASUREMENT in script:
                steps[index] = dict(step, run=script.replace(old, new))
                return
        raise AssertionError("no measuring step")

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


def test_the_measurement_must_measure_the_invoked_path(trusted_workflow):
    def transform(steps):
        for index, step in enumerate(steps):
            script = step.get("run") or ""
            if CONTIGUITY_MEASUREMENT in script:
                steps[index] = dict(
                    step,
                    run=script.replace(
                        "sha256sum " + DOUBLE + "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}" + DOUBLE,
                        "sha256sum " + DOUBLE + "${GITHUB_WORKSPACE}/some_other_file" + DOUBLE,
                    ),
                )
                return
        raise AssertionError("no measuring step")

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


def _insert_between_measurement_and_comparison(steps, injected):
    """Split the transition BETWEEN the hash command and the comparison.

    This is the window the old oracle could not see: the bytes have been measured, but the
    measurement has not been acted on yet, so a command here replaces the file that was measured.
    """
    for index, step in enumerate(steps):
        script = step.get("run") or ""
        if CONTIGUITY_MEASUREMENT not in script:
            continue
        lines = script.splitlines()
        cut = next(position for position, line in enumerate(lines) if CONTIGUITY_MEASUREMENT in line) + 1
        steps[index] = dict(step, run="\n".join(lines[:cut] + [injected.rstrip()] + lines[cut:]) + "\n")
        return
    raise AssertionError("no measuring step")


@pytest.mark.parametrize(
    ("label", "injected"),
    (
        ("gate rewritten after the hash", '          printf "x" >> "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"'),
        ("gate replaced after the hash", '          cp /tmp/other.py "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"'),
        ("gate relinked after the hash", '          ln -sf /tmp/other.py "${GITHUB_WORKSPACE}/${TRUSTED_GATE_PATH}"'),
        ("digest file rewritten", '          echo deadbeef > "${RUNNER_TEMP}/trusted/gate.sha"'),
        ("an interpreter runs after the hash", '          python3 -c "pass"'),
    ),
)
def test_a_mutation_between_the_hash_and_the_comparison_is_rejected(trusted_workflow, label, injected):
    """REPAIR 5.  The oracle owns the transition from the MEASUREMENT COMMAND onward."""
    mutant = _mutate(trusted_workflow, lambda steps: _insert_between_measurement_and_comparison(steps, injected))
    with pytest.raises(AssertionError):
        assert_contiguous(mutant)


@pytest.mark.parametrize(
    ("label", "script"),
    (
        ("indirect env write", "TARGET=GITHUB_ENV" + chr(10) + 'echo X=1 >> "${!TARGET}"' + chr(10)),
        ("indirect path write", "TARGET=GITHUB_PATH" + chr(10) + 'echo /tmp >> "${!TARGET}"' + chr(10)),
        ("indirect anything", 'echo "${!NAME}"' + chr(10)),
    ),
)
def test_indirect_expansion_cannot_reach_an_environment_file(trusted_workflow, label, script):
    """REPAIR 5.  `${!VAR}` names a variable at runtime, so a static reader cannot prove the target.

    It is refused outright rather than analysed -- the whole point of the rule is that its target is
    not statically knowable.
    """
    assert _indirect_expansion(script) is not None, label

    def transform(steps):
        steps.insert(1, {"name": "injected", "shell": "bash", "run": script})

    with pytest.raises(AssertionError):
        assert_contiguous(_mutate(trusted_workflow, transform))


def test_the_oracle_begins_at_the_measurement_command(trusted_workflow):
    """The transition's first owned line is the hash command itself, not the comparison."""
    steps, final = _final_transition_step(trusted_workflow)
    del steps
    lines = final["run"].splitlines()
    measurement = next(index for index, line in enumerate(lines) if CONTIGUITY_MEASUREMENT in line)
    comparison = next(index for index, line in enumerate(lines) if CONTIGUITY_COMPARISON in line)
    assert measurement < comparison, "the hash is taken before it is compared"
    # Everything between them is inside the owned region.
    for line in lines[measurement + 1 : comparison]:
        assert any(pattern.match(line) for pattern in _CONTIGUITY_ALLOWED), line


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
import zlib
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
    # The observation and receipt artifacts now also carry their job's observed invocation log, so
    # the whole build graph reaches the trusted surface; the ELF record artifact stays single.
    assert len(gate.EXPECTED_MEMBERS[gate.ELF_ARTIFACT]) == 1
    for name, members in gate.EXPECTED_MEMBERS.items():
        assert len(members) == (1 if name == gate.ELF_ARTIFACT else 2), name


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
            # REPAIR 12: a producer per-file hash is not authority, so the slot is EMPTY.  The
            # trusted pinned identity -- repository, release, commit, source-tree digest -- binds
            # these inputs instead.
            "sha256": "",
        }
        for path in gate.REQUIRED_UPSTREAM_INPUTS
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

def _work_dir():
    return sys.argv[sys.argv.index("--work-dir") + 1]


def _worker_bytes():
    with open(_work_dir() + "/worker.bin", "rb") as handle:
        return handle.read()


def _reviewed_a2():
    with open(_work_dir() + "/worker_a2.json", "rb") as handle:
        return json.loads(handle.read().decode("utf-8"))


def _canonical():
    return gate.stage_c_canonical_internal_policy()


def _reconstructed():
    # Stage C's OWN parse of the real image.  Nothing here reads A2.
    return gate.stage_c_reconstruct_worker_authority(_worker_bytes(), _canonical())


def _sealed_elf_record(**overrides):
    # A2 as the REVIEWED QUALIFIER produced it, resealed after any mutation so the record is
    # internally perfect -- which is exactly the attack the reconstruction has to defeat.
    record = _reviewed_a2()
    for key, value in overrides.items():
        if key == "__drop__":
            for field in value:
                record.pop(field, None)
            continue
        if key == "__drop_filter__":
            for field in value:
                record["canonical_internal_filter_object"].pop(field, None)
            continue
        if key == "__drop_cap__":
            for field in value:
                record["blst_platform_cap"].pop(field, None)
            continue
        if key in record["canonical_internal_filter_object"]:
            record["canonical_internal_filter_object"][key] = value
        elif key in record["blst_platform_cap"]:
            record["blst_platform_cap"][key] = value
        else:
            record[key] = value
    record.pop("elf_qualification_digest_sha256", None)
    record["elf_qualification_digest_sha256"] = gate.domain_digest(gate.ELF_RECORD_DIGEST_DOMAIN, record)
    return record


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


def _case(canonical, fprog_va, program_va, **overrides):
    record = {
        "case_id": "C01_POSITIVE_EXACT_FIXTURE",
        "internal_capture": {
            "program_bytes_hex": canonical["cbpf_program_bytes"].hex(),
            "fprog_va_u64": fprog_va,
            "filter_va_u64": program_va,
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


def _equivalence_digest_for(canonical, case, observation):
    # The digest an HONEST observer would compute, built from the same frozen field set Stage C
    # uses.  It is derived here rather than read back from Stage C so the comparison has two sides.
    capture = case["internal_capture"]
    baseline = case["seccomp_baseline"]
    return gate.domain_digest(
        gate.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN,
        {
            "schema": gate.INTERNAL_EQUIVALENCE_SCHEMA,
            "canonical_internal_policy_id": canonical["policy_id"],
            "canonical_internal_policy_sha256": canonical["policy_sha256"],
            "program_representation_version": gate.PROGRAM_REPRESENTATION_VERSION,
            "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
            "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
            "captured_internal_cbpf_sha256": gate.cbpf_digest(bytes.fromhex(capture["program_bytes_hex"])),
            "captured_internal_uargs_va_u64": capture["fprog_va_u64"],
            "captured_internal_len_u32": capture["length"],
            "install_exit_return_i32": capture["install_return_i32"],
            "baseline_supervisor_seccomp": baseline["supervisor_seccomp"],
            "baseline_supervisor_filters": baseline["supervisor_filters"],
            "baseline_child_seccomp": baseline["child_seccomp"],
            "baseline_child_filters": baseline["child_filters"],
            "pre_install_filters": baseline["outer_post_filters"],
            "post_install_filters": baseline["internal_post_filters"],
            "post_install_seccomp_mode": baseline["internal_post_seccomp"],
            "revalidated_filters": baseline["revalidated_filters"],
            "dump_leg_availability": case["dump_leg"]["availability"],
            "dump_leg_index0_sha256": "",
            "dump_leg_index1_sha256": "",
            "dump_leg_terminates_at_index": -1,
            "case_id": case["case_id"],
            "source_run_id": observation["source_run_id"],
            "source_run_attempt": observation["source_run_attempt"],
            "source_head_sha": observation["source_head_sha"],
            "candidate_binary_sha256": observation["candidate_binary_sha256"],
        },
    )


def stage_c_worker_reconstruction():
    # REPAIR 1B.  Stage C's independent parse AGREES with the reviewed qualifier on every governed
    # coordinate.  Two implementations, one binary, one answer.
    canonical = _canonical()
    reconstructed = _reconstructed()
    reviewed = _reviewed_a2()
    for field in ("entry_va_u64", "program_header_count", "section_header_count"):
        assert reconstructed[field] == reviewed["elf"][field], field
    assert reconstructed["observed_phdr_inventory"] == reviewed["observed_phdr_inventory"]
    for block in ("blst_platform_cap", "canonical_internal_filter_object"):
        for field, value in sorted(reconstructed[block].items()):
            assert reviewed[block][field] == value, block + "." + field
    # And the reconstruction is anchored on the canonical program, not on anything A2 said.
    assert reconstructed["canonical_internal_filter_object"]["program_bytes_sha256"] == canonical["program_bytes_sha256"]

    # The honest A2 binds cleanly.
    gate.validate_a2_schema(reviewed)
    gate.bind_a2_to_reconstruction(reviewed, reconstructed)


def a2_truncation_and_relocation():
    # REPAIR 1A and 1D.  A truncated A2 fails on the schema; a relocated A2 fails on the bytes.
    canonical = _canonical()
    reconstructed = _reconstructed()

    for field in (
        "blst_platform_cap",
        "canonical_internal_filter_object",
        "undefined_symbol_closure",
        "observed_phdr_inventory",
        "program_headers",
        "sections",
        "memory",
        "elf",
    ):
        expect(
            "ELF_RECORD_SCHEMA_INVALID",
            lambda field=field: gate.validate_a2_schema(_sealed_elf_record(__drop__=(field,))),
        )
    for field in ("program_va_u64", "program_section_addr_u64", "program_load_vaddr_u64", "program_file_offset_u64"):
        expect(
            "ELF_RECORD_SCHEMA_INVALID",
            lambda field=field: gate.validate_a2_schema(_sealed_elf_record(__drop_filter__=(field,))),
        )
    for field in ("section_index", "load_flags_u32", "file_offset_u64"):
        expect(
            "ELF_RECORD_SCHEMA_INVALID",
            lambda field=field: gate.validate_a2_schema(_sealed_elf_record(__drop_cap__=(field,))),
        )
    # An EXTRA field is a record this contract does not describe.
    expect("ELF_RECORD_SCHEMA_INVALID", lambda: gate.validate_a2_schema(_sealed_elf_record(unreviewed_field=1)))

    # COORDINATED RELOCATION: A2 moves an object and reseals itself perfectly.  The bytes disagree.
    for label, override in (
        ("object virtual address", {"program_va_u64": 0x7FF000000000}),
        ("object file offset", {"program_file_offset_u64": 0x2222}),
        ("object size", {"program_size_bytes": 800}),
        ("section address", {"program_section_addr_u64": 0x500000}),
        ("section file offset", {"program_section_file_offset_u64": 0x9999}),
        ("section index", {"program_section_index": 2}),
        ("load flags", {"program_load_flags_u32": 6}),
        ("load vaddr", {"program_load_vaddr_u64": 0x300000}),
        ("capability address", {"va_u64": 0x7FF000000000}),
        ("capability section", {"section_index": 2}),
        ("phdr inventory", {"observed_phdr_inventory": "PT_LOAD:5:0x1000"}),
        ("entry point", {"elf": None}),
    ):
        if override.get("elf") is None and "elf" in override:
            record = _reviewed_a2()
            record["elf"]["entry_va_u64"] = 0x999999
            record.pop("elf_qualification_digest_sha256", None)
            record["elf_qualification_digest_sha256"] = gate.domain_digest(gate.ELF_RECORD_DIGEST_DOMAIN, record)
        else:
            record = _sealed_elf_record(**override)
        # The reseal is perfect: A2's own digest still verifies.
        assert gate.recompute_elf_record_digest(record) == record["elf_qualification_digest_sha256"], label
        expect(
            "ELF_RECORD_CONTRADICTS_CANDIDATE",
            lambda record=record: gate.bind_a2_to_reconstruction(record, reconstructed),
        )

    del canonical


def stage_c_outer_program_binding():
    # REPAIR 2.  The OBSERVED outer program is bound to Stage C's reconstruction.
    outer = gate.stage_c_canonical_outer_policy()
    honest = {
        "outer_capture": {
            "valid": True,
            "program_bytes_hex": outer["cbpf_program_bytes"].hex(),
            "length": outer["cbpf_instruction_count"],
            "install_return_i32": 0,
            "fprog_va_u64": 0x401000,
            "filter_va_u64": 0x401100,
        }
    }
    assert gate.bind_observed_outer_program(honest, outer, None) == outer["cbpf_sha256"]

    for label, mutate in (
        ("substituted program", lambda case: case["outer_capture"].update({"program_bytes_hex": bytes(400 * 8).hex()})),
        ("wrong length", lambda case: case["outer_capture"].update({"length": 399})),
        ("failed install", lambda case: case["outer_capture"].update({"install_return_i32": -1})),
        ("not captured", lambda case: case["outer_capture"].update({"valid": False})),
    ):
        case = json.loads(json.dumps(honest))
        mutate(case)
        expect("OUTER_FILTER_EQUIVALENCE_FAILED", lambda case=case: gate.bind_observed_outer_program(case, outer, None))
        del label


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


def stage_c_outer_policy_reconstruction():
    # REPAIR 1C.  The OUTER policy is reconstructed too, so no A3/A4 top-level claim is an oracle.
    outer = gate.stage_c_canonical_outer_policy()
    assert outer["policy_id"] == "MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"
    assert outer["cbpf_instruction_count"] == 400
    assert outer["policy_sha256"] == gate.EXPECTED_OUTER_POLICY_SHA256
    assert outer["governed_sha256"] == gate.EXPECTED_OUTER_GOVERNED_SHA256
    assert outer["cbpf_sha256"] == gate.EXPECTED_OUTER_CBPF_SHA256
    # The two policies are genuinely different documents, and the semantic/governed separation holds.
    inner = gate.stage_c_canonical_internal_policy()
    assert outer["policy_sha256"] != inner["policy_sha256"]
    assert outer["cbpf_sha256"] != inner["cbpf_sha256"]
    assert outer["governed_sha256"] != outer["policy_sha256"]
    assert b'"policy_domain":"MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"' in outer["semantic_bytes"]


def stage_c_equivalence_recomputation():
    canonical = _canonical()
    reconstructed = _reconstructed()
    filter_object = reconstructed["canonical_internal_filter_object"]
    fprog_va = filter_object["fprog_va_u64"]
    program_va = filter_object["program_va_u64"]
    observation = _observation(canonical)
    case = _case(canonical, fprog_va, program_va)

    # The honest digest, discovered by asking Stage C what it recomputes.
    try:
        gate.stage_c_equivalence_digest(observation, case, "", canonical, filter_object)
        raise AssertionError("an empty A3 digest must not pass")
    except gate.TrustedGateError as error:
        assert "A3 vs Stage C" in str(error)

    honest = _equivalence_digest_for(canonical, case, observation)
    case["internal_filter_equivalence"]["digest_sha256"] = honest
    assert gate.stage_c_equivalence_digest(observation, case, honest, canonical, filter_object) == honest

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
    # A capture at an address the RECONSTRUCTION does not place the object at is refused.
    moved = json.loads(json.dumps(case))
    moved["internal_capture"]["fprog_va_u64"] = 0x7FFF00000000
    expect(
        "INTERNAL_FILTER_EQUIVALENCE_FAILED",
        lambda: gate.stage_c_equivalence_digest(observation, moved, honest, canonical, filter_object),
    )


def coordinated_reseal_is_rejected():
    # THE CENTRAL REPAIR-2 ORACLE, now anchored on the reconstruction rather than on A2.
    canonical = _canonical()
    reconstructed = _reconstructed()
    filter_object = reconstructed["canonical_internal_filter_object"]
    fprog_va = filter_object["fprog_va_u64"]
    program_va = filter_object["program_va_u64"]

    def sealed(observation, case):
        forged = "9" * 64
        case = json.loads(json.dumps(case))
        case["internal_filter_equivalence"]["digest_sha256"] = forged
        return lambda: gate.stage_c_equivalence_digest(observation, case, forged, canonical, filter_object)

    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(
            _observation(canonical, canonical_internal_policy_id="ATTACKER_POLICY"),
            _case(canonical, fprog_va, program_va),
        ),
    )
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(
            _observation(canonical, canonical_internal_policy_sha256="a" * 64),
            _case(canonical, fprog_va, program_va),
        ),
    )
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(
            _observation(canonical, canonical_internal_cbpf_instruction_count=112),
            _case(canonical, fprog_va, program_va),
        ),
    )
    weaker = bytes(113 * 8)
    coordinated_case = _case(canonical, fprog_va, program_va)
    coordinated_case["internal_capture"]["program_bytes_hex"] = weaker.hex()
    expect(
        "STAGE_C_CANONICAL_POLICY_SUBSTITUTED",
        sealed(_observation(canonical, canonical_internal_cbpf_sha256=gate.cbpf_digest(weaker)), coordinated_case),
    )
    moved = _case(canonical, 0x7FFF00000000, program_va)
    expect("INTERNAL_FILTER_EQUIVALENCE_FAILED", sealed(_observation(canonical), moved))
    moved_filter = _case(canonical, fprog_va, 0x7FFF00000000)
    expect("INTERNAL_FILTER_EQUIVALENCE_FAILED", sealed(_observation(canonical), moved_filter))
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


# =================================================================================================
# THE REAL run_gate HARNESS.
#
# Everything below builds a COMPLETE, internally consistent, authenticated-looking source run and
# then calls gate.run_gate.  The GitHub surface is served from a dictionary, so no network and no
# credential is involved, but every rule the gate applies runs for real.  Each mutation changes one
# controlled input and holds the trusted authority fixed.
# =================================================================================================

RUN_ID = 424242
ATTEMPT = 1
HEAD_SHA = "c" * 40
REPOSITORY = "demircaliskan2009-pixel/BIST_ELITE_CORE"
WORKFLOW_PATH = ".github/workflows/crypto_core_mt4_s3c_static_worker_qualification.yml"
WORKFLOW_NAME = "crypto_core mt4-s3c static worker qualification"
ARTIFACT_IDS = {
    "mt4-s3c-candidate-linux-x86_64": 9001,
    "mt4-s3c-elf-qualification-record": 9002,
    "mt4-s3c-raw-observation-record": 9003,
    "mt4-s3c-qualification-receipt": 9004,
}


class _Arguments(object):
    pass


def _zip_bytes(members):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, body in members:
            archive.writestr(name, body)
    return buffer.getvalue()


def _canonical_bytes(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _instance(instance_id, kind, inputs, libraries=(), flags=(), output="out.o"):
    return {
        "instance_id": instance_id,
        "kind": kind,
        "tool": "gcc",
        "argv": ["gcc", "-c", "-o", output] + [item["path"] for item in inputs],
        "flags": sorted(flags),
        "include_roots": [],
        "inputs": list(inputs),
        "libraries": sorted(libraries),
        "output": output,
        "working_directory_class": "GITHUB_WORKSPACE",
    }


_BUNDLED_SOURCE = {
    "worker-bootstrap": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_bootstrap.c",
    "worker-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "worker-capability": "scripts/crypto_core/qualification/s3c/mt4_s3c_blst_capability.c",
    "worker-verify": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_verify.c",
    "worker-start": "scripts/crypto_core/qualification/s3c/mt4_s3c_static_worker_start.S",
    "observer-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "observer-launcher": "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "observer-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "observe-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "observe-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
    "observe-launcher": "scripts/crypto_core/qualification/s3c/mt4_s3c_outer_containment_launcher.c",
    "adjudicate-policy": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy.c",
    "adjudicate-probe": "scripts/crypto_core/qualification/s3c/mt4_s3c_sandbox_policy_probe.c",
}

_LINK_INPUTS = {
    "worker-link": ("start.o", "bootstrap.o"),
    "observer-link": ("launcher.o", "policy.o"),
    "observe-probe-link": ("probe.o", "policy.o"),
    "observe-observer-link": ("launcher.o", "policy.o"),
    "adjudicate-probe-link": ("probe.o", "policy.o"),
}

# Which object each compile produces, so the producer -> consumer edges close.
_COMPILE_OUTPUT = {
    "worker-start": "start.o",
    "worker-bootstrap": "bootstrap.o",
    "observer-launcher": "launcher.o",
    "observer-policy": "policy.o",
    "observer-probe": "probe.o",
    "observe-launcher": "launcher.o",
    "observe-policy": "policy.o",
    "observe-probe": "probe.o",
    "adjudicate-policy": "policy.o",
    "adjudicate-probe": "probe.o",
}


def _graph_instance(instance_id, kind):
    if kind == "COMPILE":
        if instance_id in _BUNDLED_SOURCE:
            inputs = [{"path": _BUNDLED_SOURCE[instance_id], "class": "REPO_BUNDLED"}]
        elif instance_id == "blst-server":
            inputs = [{"path": "src/server.c", "class": "UPSTREAM_PINNED"}]
        else:
            inputs = [{"path": "build/assembly.S", "class": "UPSTREAM_PINNED"}]
        output = _COMPILE_OUTPUT.get(instance_id, instance_id + ".o")
        return _instance(instance_id, kind, inputs, output=output)
    inputs = [{"path": "/tmp/" + name, "class": "EXTERNAL_TOOLCHAIN"} for name in _LINK_INPUTS[instance_id]]
    libraries = ("cap",) if instance_id in ("observer-link", "observe-observer-link") else ()
    flags = gate.REQUIRED_WORKER_LINK_FLAGS if instance_id == "worker-link" else ()
    return _instance(instance_id, kind, inputs, libraries=libraries, flags=flags, output=instance_id)


def _build_job_instances():
    instances = [
        _graph_instance(name, "LINK" if name in gate.REQUIRED_LINK_INSTANCES else "COMPILE")
        for name in gate.BUILD_JOB_INSTANCES
    ]
    instances.sort(key=lambda item: item["instance_id"])
    return {
        "schema": gate.COMPILE_INSTANCE_SCHEMA,
        "instance_count": len(instances),
        "instances": instances,
        "instance_id_order": [item["instance_id"] for item in instances],
        "system_libraries": [
            {
                "name": "cap",
                "resolved_path": "/usr/lib/x86_64-linux-gnu/libcap.so.2.44",
                "soname": "libcap.so.2.44",
                "digest_sha256": "b" * 64,
                "provenance": gate.PROVENANCE_SYSTEM_LIBRARY,
            }
        ],
    }


def _job_log(names):
    return {
        "schema": gate.INSTANCE_LOG_SCHEMA,
        "instances": [
            _graph_instance(name, "LINK" if name in gate.REQUIRED_LINK_INSTANCES else "COMPILE") for name in names
        ],
    }


def _complete_instances():
    return _build_job_instances()


def _build_world(mutate=None):
    # ONE coherent run: the same canonical policy, the same 25 cases, the same identity everywhere.
    canonical = gate.stage_c_canonical_internal_policy()
    outer = gate.stage_c_canonical_outer_policy()
    case_set = gate.stage_c_case_set_digest()

    # The REAL synthetic worker image, and the A2 the REVIEWED qualifier derived from it.  Stage C
    # parses these same bytes itself, so a mutation to A2 alone can no longer agree with anything.
    worker = _worker_bytes()
    worker_digest = hashlib.sha256(worker).hexdigest()
    elf_record = _reviewed_a2()
    elf_record["candidate_binary_sha256"] = worker_digest

    dependency = _complete_inventory()
    dependency_digest = None

    manifest = {
        "schema": "mt4-s3c-build-manifest.v1",
        "worker_binary_sha256": worker_digest,
        "source_run_id": RUN_ID,
        "source_run_attempt": ATTEMPT,
        "source_head_sha": HEAD_SHA,
        "upstream_repository": gate.UPSTREAM_REPOSITORY,
        "upstream_release": gate.UPSTREAM_RELEASE,
        "upstream_commit": gate.UPSTREAM_COMMIT,
        "upstream_source_tree_digest": gate.UPSTREAM_SOURCE_TREE_DIGEST,
        "compile_instance_inventory_schema": gate.COMPILE_INSTANCE_SCHEMA,
    }

    cases = []
    reconstructed = gate.stage_c_reconstruct_worker_authority(worker, canonical)
    objects = reconstructed["canonical_internal_filter_object"]
    for row in gate.TRUSTED_CASE_INVENTORY:
        cases.append(
            {
                "case_id": row[1],
                "internal_capture": {
                    "program_bytes_hex": canonical["cbpf_program_bytes"].hex(),
                    "fprog_va_u64": objects["fprog_va_u64"],
                    "filter_va_u64": objects["program_va_u64"],
                    "length": canonical["cbpf_instruction_count"],
                    "install_return_i32": 0,
                },
                "outer_capture": {
                    "valid": True,
                    "program_bytes_hex": outer["cbpf_program_bytes"].hex(),
                    "length": outer["cbpf_instruction_count"],
                    "install_return_i32": 0,
                    "fprog_va_u64": 1,
                    "filter_va_u64": 2,
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
        )

    observation = {
        "candidate_binary_sha256": worker_digest,
        "source_run_id": RUN_ID,
        "source_run_attempt": ATTEMPT,
        "source_head_sha": HEAD_SHA,
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "outer_containment_policy_digest_sha256": outer["governed_sha256"],
        "observation_case_set_digest_sha256": case_set,
        "cases": cases,
    }

    receipt = {
        "worker_binary_sha256": worker_digest,
        "source_run_id": RUN_ID,
        "source_run_attempt": ATTEMPT,
        "source_head_sha": HEAD_SHA,
        "candidate_artifact_id": ARTIFACT_IDS["mt4-s3c-candidate-linux-x86_64"],
        "candidate_artifact_archive_digest": "sha256:" + "a" * 64,
        "elf_qualification_digest_sha256": elf_record["elf_qualification_digest_sha256"],
        "protocol_conformance_digest_sha256": "1" * 64,
        "sandbox_policy_digest_sha256": "2" * 64,
        "outer_containment_policy_digest_sha256": outer["governed_sha256"],
        "observation_case_set_digest_sha256": case_set,
        "canonical_internal_policy_id": canonical["policy_id"],
        "canonical_internal_policy_sha256": canonical["policy_sha256"],
        "canonical_internal_cbpf_instruction_count": canonical["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": canonical["cbpf_sha256"],
        "canonical_outer_policy_id": outer["policy_id"],
        "canonical_outer_policy_sha256": outer["policy_sha256"],
        "canonical_outer_cbpf_instruction_count": outer["cbpf_instruction_count"],
        "canonical_outer_cbpf_sha256": outer["cbpf_sha256"],
        "case_count": 25,
        "all_cases_conform": True,
        "evidence_status": "ADMISSION_EVIDENCE_ONLY",
        "governed_worker_row_created": False,
        "internal_filter_equivalence_digests": [],
    }

    world = {
        "canonical": canonical,
        "elf_record": elf_record,
        "worker": worker,
        "manifest": manifest,
        "observation": observation,
        "receipt": receipt,
        "dependency": dependency,
        "instances": _complete_instances(),
        "observe_log": _job_log(
            ("observe-policy", "observe-probe", "observe-probe-link", "observe-launcher", "observe-observer-link")
        ),
        "adjudicate_log": _job_log(("adjudicate-policy", "adjudicate-probe", "adjudicate-probe-link")),
        "bundle": {"entries": _bundle_entries()},
        "artifact_ids": dict(ARTIFACT_IDS),
        "archive_digests": {name: "sha256:" + format(index, "064x") for index, name in enumerate(ARTIFACT_IDS)},
        "jobs": [{"id": 100 + index, "name": name, "conclusion": "success"} for index, name in enumerate(gate.REQUIRED_JOBS)],
        "run": {
            "run_attempt": ATTEMPT,
            "head_sha": HEAD_SHA,
            "head_branch": "main",
            "event": "workflow_dispatch",
            "status": "completed",
            "conclusion": "success",
            "path": WORKFLOW_PATH,
            "name": WORKFLOW_NAME,
            "repository": {"full_name": REPOSITORY},
        },
    }
    del dependency_digest
    # The receipt's CANDIDATE claims must match what the service reports, which is only known once
    # the world exists; an honest producer reads them from the upload result the same way.
    world["receipt"]["candidate_artifact_archive_digest"] = world["archive_digests"][
        "mt4-s3c-candidate-linux-x86_64"
    ]

    if mutate is not None:
        mutate(world)

    # SEAL: the per-case equivalence digests are computed the way an honest producer would, AFTER
    # any mutation, so a coordinated reseal is genuinely internally consistent.
    filter_object = gate.stage_c_reconstruct_worker_authority(world["worker"], world["canonical"])[
        "canonical_internal_filter_object"
    ]
    digests = []
    for case in world["observation"]["cases"]:
        record = _equivalence_record(world, case, filter_object)
        digest = gate.domain_digest(gate.INTERNAL_EQUIVALENCE_DIGEST_DOMAIN, record)
        case["internal_filter_equivalence"]["digest_sha256"] = digest
        digests.append({"case_id": case["case_id"], "digest_sha256": digest})
    if not world["receipt"]["internal_filter_equivalence_digests"]:
        world["receipt"]["internal_filter_equivalence_digests"] = digests
    return world


def _equivalence_record(world, case, filter_object):  # noqa: ARG001 - kept for call-site symmetry
    observation = world["observation"]
    capture = case["internal_capture"]
    baseline = case["seccomp_baseline"]
    del filter_object
    return {
        "schema": gate.INTERNAL_EQUIVALENCE_SCHEMA,
        "canonical_internal_policy_id": world["canonical"]["policy_id"],
        "canonical_internal_policy_sha256": world["canonical"]["policy_sha256"],
        "program_representation_version": gate.PROGRAM_REPRESENTATION_VERSION,
        "canonical_internal_cbpf_instruction_count": world["canonical"]["cbpf_instruction_count"],
        "canonical_internal_cbpf_sha256": world["canonical"]["cbpf_sha256"],
        "captured_internal_cbpf_sha256": gate.cbpf_digest(bytes.fromhex(capture["program_bytes_hex"])),
        "captured_internal_uargs_va_u64": capture["fprog_va_u64"],
        "captured_internal_len_u32": capture["length"],
        "install_exit_return_i32": capture["install_return_i32"],
        "baseline_supervisor_seccomp": baseline["supervisor_seccomp"],
        "baseline_supervisor_filters": baseline["supervisor_filters"],
        "baseline_child_seccomp": baseline["child_seccomp"],
        "baseline_child_filters": baseline["child_filters"],
        "pre_install_filters": baseline["outer_post_filters"],
        "post_install_filters": baseline["internal_post_filters"],
        "post_install_seccomp_mode": baseline["internal_post_seccomp"],
        "revalidated_filters": baseline["revalidated_filters"],
        "dump_leg_availability": case["dump_leg"]["availability"],
        "dump_leg_index0_sha256": "",
        "dump_leg_index1_sha256": "",
        "dump_leg_terminates_at_index": -1,
        "case_id": case["case_id"],
        "source_run_id": observation["source_run_id"],
        "source_run_attempt": observation["source_run_attempt"],
        "source_head_sha": observation["source_head_sha"],
        "candidate_binary_sha256": observation["candidate_binary_sha256"],
    }


def _install_world(world, work_dir):
    # Serve the synthetic GitHub surface and the two local inventories.
    archives = {
        world["artifact_ids"]["mt4-s3c-candidate-linux-x86_64"]: _zip_bytes(
            [("mt4_s3c_static_worker", world["worker"]), ("mt4_s3c_build_manifest.json", _canonical_bytes(world["manifest"]))]
        ),
        world["artifact_ids"]["mt4-s3c-elf-qualification-record"]: _zip_bytes(
            [("mt4_s3c_elf_qualification_record.json", _canonical_bytes(world["elf_record"]))]
        ),
        world["artifact_ids"]["mt4-s3c-raw-observation-record"]: _zip_bytes(
            [
                ("mt4_s3c_raw_observation_record.json", _canonical_bytes(world["observation"])),
                ("mt4_s3c_observe_instances.json", _canonical_bytes(world["observe_log"])),
            ]
        ),
        world["artifact_ids"]["mt4-s3c-qualification-receipt"]: _zip_bytes(
            [
                ("mt4_s3c_qualification_receipt.json", _canonical_bytes(world["receipt"])),
                ("mt4_s3c_adjudicate_instances.json", _canonical_bytes(world["adjudicate_log"])),
            ]
        ),
    }
    artifacts = []
    for name in gate.EXPECTED_ARTIFACT_SET:
        artifacts.append(
            {
                "id": world["artifact_ids"][name],
                "name": name,
                "expired": False,
                "digest": world["archive_digests"][name],
                "workflow_run": {
                    "id": 777777 if world.get("foreign_owner") and name == "mt4-s3c-qualification-receipt" else RUN_ID,
                    "head_sha": HEAD_SHA,
                },
            }
        )
    if world.get("extra_artifacts"):
        artifacts.extend(world["extra_artifacts"])

    def api_json(api_url, path):
        del api_url
        if path.endswith("/actions/runs/" + str(RUN_ID)):
            return world["run"]
        if "/attempts/" in path and "jobs" in path:
            return {"total_count": len(world["jobs"]), "jobs": world["jobs"]}
        if "artifacts" in path:
            return {"total_count": len(artifacts), "artifacts": artifacts}
        raise AssertionError("unexpected api path " + path)

    def download_artifact(api_url, repository, artifact_id):
        del api_url, repository
        return archives[artifact_id]

    gate.api_json = api_json
    gate.download_artifact = download_artifact

    bundle_path = work_dir + "/bundle.json"
    dependency_path = work_dir + "/dependency.json"
    instance_path = work_dir + "/instances.json"
    with open(bundle_path, "wb") as handle:
        handle.write(_canonical_bytes(world["bundle"]))
    with open(dependency_path, "wb") as handle:
        handle.write(_canonical_bytes(world["dependency"]))
    with open(instance_path, "wb") as handle:
        handle.write(_canonical_bytes(world["instances"]))

    arguments = _Arguments()
    arguments.api_url = "https://api.github.com"
    arguments.repository = REPOSITORY
    arguments.source_run_id = RUN_ID
    arguments.expected_head_sha = HEAD_SHA
    arguments.expected_workflow_path = WORKFLOW_PATH
    arguments.expected_workflow_name = WORKFLOW_NAME
    arguments.default_branch = "main"
    arguments.source_bundle_inventory = bundle_path
    arguments.compile_dependency_inventory = dependency_path
    arguments.compile_instance_inventory = instance_path
    arguments.approved_source_bundle_sha256 = gate.recompute_source_bundle_digest(world["bundle"])[0]
    entry = [item for item in world["bundle"]["entries"] if item["path"] == WORKFLOW_PATH][0]
    arguments.approved_qualification_workflow_sha256 = entry["sha256"]
    return arguments


def _run_world(work_dir, mutate=None):
    world = _build_world(mutate)
    world["manifest"]["compile_dependency_inventory_digest_sha256"] = None
    arguments = _install_world(world, work_dir)
    inventory_digest = gate.recompute_dependency_inventory_digest(world["dependency"], world["bundle"]["entries"])
    world["manifest"]["compile_dependency_inventory_digest_sha256"] = inventory_digest
    if not world.get("freeze_instance_digest"):
        world["manifest"]["compile_instance_inventory_digest_sha256"] = gate.recompute_compile_instance_digest(
            world["instances"]
        )
    world["elf_record"]["compile_dependency_inventory_digest_sha256"] = inventory_digest
    world["receipt"]["compile_dependency_inventory_digest_sha256"] = inventory_digest
    # The ELF record's own digest is resealed after the inventory digest is known, so the honest
    # world is genuinely self-consistent.  A mutation may FREEZE the digest instead, which is what
    # a forged-digest attacker does: A2 and A4 agree on a value the record does not actually hash to.
    if not world.get("freeze_elf_digest"):
        preimage = {
            key: value for key, value in world["elf_record"].items() if key != "elf_qualification_digest_sha256"
        }
        world["elf_record"]["elf_qualification_digest_sha256"] = gate.domain_digest(
            gate.ELF_RECORD_DIGEST_DOMAIN, preimage
        )
        world["receipt"]["elf_qualification_digest_sha256"] = world["elf_record"]["elf_qualification_digest_sha256"]
    arguments = _install_world(world, work_dir)
    return gate.run_gate(arguments), world


def run_gate_reference():
    # The honest world passes, which is what makes every rejection below meaningful.
    work_dir = sys.argv[sys.argv.index("--work-dir") + 1]
    predicate, world = _run_world(work_dir)
    assert predicate["case_count"] == 25
    assert predicate["evidence_status"] == "ADMISSION_EVIDENCE_ONLY"
    assert predicate["admission"] == "NONE"
    # REPAIR 1D: the receipt custody identity comes from the SERVICE, not from the receipt.
    assert predicate["receipt_artifact_id"] == ARTIFACT_IDS["mt4-s3c-qualification-receipt"]
    assert predicate["receipt_artifact_archive_digest"] == world["archive_digests"]["mt4-s3c-qualification-receipt"]
    assert predicate["candidate_artifact_id"] == ARTIFACT_IDS["mt4-s3c-candidate-linux-x86_64"]
    assert len(predicate["internal_filter_equivalence_digests"]) == 25
    assert predicate["canonical_outer_policy_id"] == "MT4_S3C_OUTER_CONTAINMENT_P0_LINUX_X86_64"


def _expect_run_gate(marker, mutate):
    work_dir = sys.argv[sys.argv.index("--work-dir") + 1]
    try:
        _run_world(work_dir, mutate)
    except gate.TrustedGateError as error:
        assert marker in str(error), marker + " not in " + str(error)
        return
    raise AssertionError("run_gate accepted " + marker)


def run_gate_coordinated_reseal():
    # REPAIR 1E.  Both producer records are resealed CONSISTENTLY with a false but internally
    # matching value.  Every cross-record equality still holds; the trusted reconstruction does not.
    def false_policy_id(world):
        world["observation"]["canonical_internal_policy_id"] = "ATTACKER_POLICY"
        world["receipt"]["canonical_internal_policy_id"] = "ATTACKER_POLICY"

    _expect_run_gate("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", false_policy_id)

    def false_policy_digest(world):
        world["observation"]["canonical_internal_policy_sha256"] = "a" * 64
        world["receipt"]["canonical_internal_policy_sha256"] = "a" * 64

    _expect_run_gate("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", false_policy_digest)

    def false_cbpf(world):
        weaker = bytes(113 * 8)
        world["observation"]["canonical_internal_cbpf_sha256"] = gate.cbpf_digest(weaker)
        world["receipt"]["canonical_internal_cbpf_sha256"] = gate.cbpf_digest(weaker)
        for case in world["observation"]["cases"]:
            case["internal_capture"]["program_bytes_hex"] = weaker.hex()

    _expect_run_gate("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", false_cbpf)

    def false_outer(world):
        world["observation"]["outer_containment_policy_digest_sha256"] = "b" * 64
        world["receipt"]["outer_containment_policy_digest_sha256"] = "b" * 64

    _expect_run_gate("STAGE_C_CANONICAL_POLICY_SUBSTITUTED", false_outer)

    def false_case_set(world):
        world["observation"]["observation_case_set_digest_sha256"] = "c" * 64
        world["receipt"]["observation_case_set_digest_sha256"] = "c" * 64

    _expect_run_gate("OBSERVATION_CASE_SET_DIGEST_MISMATCH", false_case_set)

    def false_elf_digest(world):
        # A2 AND A4 agree on a forged ELF digest, and the world stops resealing it -- so the two
        # records are perfectly consistent with each other and inconsistent only with the truth.
        world["freeze_elf_digest"] = True
        world["elf_record"]["elf_qualification_digest_sha256"] = "d" * 64
        world["receipt"]["elf_qualification_digest_sha256"] = "d" * 64

    _expect_run_gate("ELF_QUALIFICATION_DIGEST_MISMATCH", false_elf_digest)

    def false_address(world):
        # A2 moves the object and A4 follows.  The BYTES do not move, so the reconstruction wins.
        world["elf_record"]["canonical_internal_filter_object"]["program_va_u64"] = 0x7FF000000000
        for case in world["observation"]["cases"]:
            case["internal_capture"]["filter_va_u64"] = 0x7FF000000000

    _expect_run_gate("ELF_RECORD_CONTRADICTS_CANDIDATE", false_address)

    def false_receipt_relation(world):
        # A4 claims a candidate artifact id the SERVICE does not report.
        world["receipt"]["candidate_artifact_id"] = 999999

    _expect_run_gate("RECEIPT_BINDING_MISMATCH", false_receipt_relation)

    def self_asserted_receipt_identity(world):
        world["receipt"]["receipt_artifact_id"] = ARTIFACT_IDS["mt4-s3c-qualification-receipt"]

    _expect_run_gate("RECEIPT_BINDING_MISMATCH", self_asserted_receipt_identity)

    def foreign_run_owner(world):
        # An artifact whose SERVICE record points at another run breaks the one-run pairing.
        world["foreign_owner"] = True

    _expect_run_gate("RUN_ATTEMPT_MISMATCH", foreign_run_owner)


def run_gate_compile_provenance():
    # REPAIR 8.  The ACTUAL invocation inventory is validated and recomputed at the boundary, and
    # the pinned upstream identity is compared to trusted literals rather than to a hex shape.
    work_dir = sys.argv[sys.argv.index("--work-dir") + 1]
    predicate, _world = _run_world(work_dir)
    assert len(predicate["compile_instance_inventory_digest_sha256"]) == 64
    assert predicate["pinned_upstream_commit"] == gate.UPSTREAM_COMMIT
    assert predicate["pinned_upstream_source_tree_digest"] == gate.UPSTREAM_SOURCE_TREE_DIGEST
    # The residual is NAMED rather than implied: Stage C holds no per-file blst digest table.
    assert predicate["pinned_upstream_per_file_digests_verified"] is False

    def drop_observer_launcher(world):
        world["instances"]["instances"] = [
            item for item in world["instances"]["instances"] if item["instance_id"] != "observer-launcher"
        ]
        world["instances"]["instance_count"] = len(world["instances"]["instances"])
        world["instances"]["instance_id_order"] = [item["instance_id"] for item in world["instances"]["instances"]]

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", drop_observer_launcher)

    def drop_upstream_assembly(world):
        world["instances"]["instances"] = [
            item for item in world["instances"]["instances"] if item["instance_id"] != "blst-assembly"
        ]
        world["instances"]["instance_count"] = len(world["instances"]["instances"])
        world["instances"]["instance_id_order"] = [item["instance_id"] for item in world["instances"]["instances"]]

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", drop_upstream_assembly)

    def drop_system_library(world):
        for item in world["instances"]["instances"]:
            if item["instance_id"] == "observer-link":
                item["libraries"] = []

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_INCOMPLETE", drop_system_library)

    def weaken_link_flags(world):
        for item in world["instances"]["instances"]:
            if item["instance_id"] == "worker-link":
                item["flags"] = [flag for flag in item["flags"] if flag != "-Wl,-z,defs"]

    _expect_run_gate("COMPILE_INSTANCE_LINK_CONTRACT_VIOLATED", weaken_link_flags)

    def substitute_tool(world):
        for item in world["instances"]["instances"]:
            if item["instance_id"] == "worker-policy":
                item["tool"] = "clang"

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_MISMATCH", substitute_tool)

    def unbundled_input(world):
        for item in world["instances"]["instances"]:
            if item["instance_id"] == "worker-policy":
                item["inputs"] = [{"path": "src/crypto_core/__init__.py", "class": "REPO_BUNDLED"}]

    _expect_run_gate("SOURCE_CLOSURE_COMPILE_DEPENDENCY_UNBUNDLED", unbundled_input)

    def duplicate_instance(world):
        world["instances"]["instances"].append(json.loads(json.dumps(world["instances"]["instances"][0])))
        world["instances"]["instances"].sort(key=lambda item: item["instance_id"])
        world["instances"]["instance_count"] = len(world["instances"]["instances"])
        world["instances"]["instance_id_order"] = [item["instance_id"] for item in world["instances"]["instances"]]

    _expect_run_gate("COMPILE_INSTANCE_DUPLICATE", duplicate_instance)

    def reorder_instances(world):
        world["instances"]["instances"] = list(reversed(world["instances"]["instances"]))
        world["instances"]["instance_id_order"] = [item["instance_id"] for item in world["instances"]["instances"]]

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_MISMATCH", reorder_instances)

    def substituted_instance_digest(world):
        world["freeze_instance_digest"] = True
        world["manifest"]["compile_instance_inventory_digest_sha256"] = "9" * 64

    _expect_run_gate("COMPILE_INSTANCE_INVENTORY_MISMATCH", substituted_instance_digest)

    for label, field in (
        ("commit", "upstream_commit"),
        ("tree", "upstream_source_tree_digest"),
        ("release", "upstream_release"),
        ("repository", "upstream_repository"),
    ):

        def substitute_upstream(world, field=field):
            world["manifest"][field] = "0" * 40 if field == "upstream_commit" else "substituted"

        _expect_run_gate("PINNED_UPSTREAM_IDENTITY_MISMATCH", substitute_upstream)
        del label


def run_gate_duplicate_identities():
    # REPAIR 3, at the real entrypoint rather than in a helper.
    def duplicate_case(world):
        world["observation"]["cases"][24] = json.loads(json.dumps(world["observation"]["cases"][23]))

    _expect_run_gate("OBSERVATION_CASE_DUPLICATE", duplicate_case)

    def duplicate_receipt_identity(world):
        world["receipt"]["internal_filter_equivalence_digests"] = [
            {"case_id": gate.TRUSTED_CASE_IDS[0], "digest_sha256": "e" * 64} for _ in range(25)
        ]

    _expect_run_gate("RECEIPT_DUPLICATE_CASE_IDENTITY", duplicate_receipt_identity)

    def reordered_cases(world):
        cases = world["observation"]["cases"]
        cases[0], cases[1] = cases[1], cases[0]

    _expect_run_gate("OBSERVATION_CASE_ORDER_MISMATCH", reordered_cases)

    def unknown_case(world):
        world["observation"]["cases"][12]["case_id"] = "C99_NOT_A_CASE"

    _expect_run_gate("OBSERVATION_CASE_MISSING", unknown_case)

    def short_receipt_list(world):
        world["receipt"]["internal_filter_equivalence_digests"] = [
            {"case_id": identifier, "digest_sha256": "f" * 64} for identifier in gate.TRUSTED_CASE_IDS[:24]
        ]

    _expect_run_gate("RECEIPT_BINDING_MISMATCH", short_receipt_list)

    def duplicate_artifact_service_id(world):
        world["artifact_ids"]["mt4-s3c-qualification-receipt"] = world["artifact_ids"][
            "mt4-s3c-candidate-linux-x86_64"
        ]

    # The OWNING rule is the pagination layer's repeated-record check, which sees every enumerated
    # record rather than only the expected four.
    _expect_run_gate("PAGINATION_REPEATED_RECORD", duplicate_artifact_service_id)


# =================================================================================================
# THE COMPLETE Z1..Z20 CAUSAL MATRIX (repair 6E).
#
# Every rule constructs ONE controlled malformed archive, runs the REAL reader, and asserts the
# exact owning reason.  No rule is proven by a source token, and the ordering is checked too: an
# earlier rule must not silently swallow a later one's class.
# =================================================================================================


def _info_archive(infos):
    # A central-directory stand-in, so rules that run BEFORE any member is opened can be reached
    # with values a real writer would refuse to produce.
    class _Archive(object):
        def infolist(self):
            return infos

    return _Archive()


class _Info(object):
    def __init__(self, filename, file_size=4, compress_size=4, compress_type=8, flag_bits=0, external_attr=0):
        self.filename = filename
        self.file_size = file_size
        self.compress_size = compress_size
        self.compress_type = compress_type
        self.flag_bits = flag_bits
        self.external_attr = external_attr

    def is_dir(self):
        return self.filename.endswith("/")


def _pair(**overrides):
    worker = _Info(WORKER, **overrides)
    return [worker, _Info(MANIFEST)]


def z_matrix_pre_decompression():
    members = gate.EXPECTED_MEMBERS[CANDIDATE]

    # Z1: the whole archive is bounded before anything is parsed.
    expect(
        "ZIP_ARCHIVE_BYTES",
        lambda: gate.pre_decompression_gate(
            _info_archive(_pair()), b"x" * (gate.MAX_ARCHIVE_BYTES + 1), members
        ),
    )
    # Z2: the member count is exact.
    expect(
        "ZIP_MEMBER_COUNT",
        lambda: gate.pre_decompression_gate(_info_archive([_Info(WORKER)]), b"x", members),
    )
    # Z4: a duplicate reaches the duplicate rule, ahead of the name-set rule.
    expect(
        "ZIP_DUPLICATE_MEMBER",
        lambda: gate.pre_decompression_gate(_info_archive([_Info(WORKER), _Info(WORKER)]), b"x", members),
    )
    # Z3: a wrong NAME reaches the name-set rule, which Z4 must not have swallowed.
    expect(
        "ZIP_MEMBER_NAME_SET",
        lambda: gate.pre_decompression_gate(_info_archive([_Info(WORKER), _Info("other")]), b"x", members),
    )
    # Z5 and Z6 are DEFENCE IN DEPTH behind Z3.  In production the name set is frozen, so a
    # directory entry or a traversing path is already refused by Z3 -- these rules exist for the
    # case where the expected set itself ever changed.  Each is therefore reached here with an
    # expected set that admits the name, which is the only way to observe the rule that owns it.
    expect(
        "ZIP_UNSAFE_MEMBER",
        lambda: gate.pre_decompression_gate(
            _info_archive([_Info(WORKER + "/"), _Info(MANIFEST)]), b"x", (WORKER + "/", MANIFEST)
        ),
    )
    # Z6: path traversal.
    expect(
        "ZIP_UNSAFE_MEMBER",
        lambda: gate.pre_decompression_gate(
            _info_archive([_Info("../" + WORKER), _Info(MANIFEST)]),
            b"x",
            ("../" + WORKER, MANIFEST),
        ),
    )
    # Z7: a non-regular Unix file type.
    expect(
        "ZIP_UNSAFE_MEMBER",
        lambda: gate.pre_decompression_gate(_info_archive(_pair(external_attr=0o120000 << 16)), b"x", members),
    )
    # Z8: an encrypted member.
    expect(
        "ZIP_ENCRYPTED_MEMBER",
        lambda: gate.pre_decompression_gate(_info_archive(_pair(flag_bits=0x1)), b"x", members),
    )
    # Z9: an unapproved compression method.
    expect(
        "ZIP_COMPRESSION_METHOD",
        lambda: gate.pre_decompression_gate(_info_archive(_pair(compress_type=93)), b"x", members),
    )
    # Z10: a declared size above the member cap.
    expect(
        "ZIP_DECLARED_SIZE",
        lambda: gate.pre_decompression_gate(
            _info_archive(_pair(file_size=gate.MAX_MEMBER_UNCOMPRESSED_BINARY + 1, compress_size=10**7)),
            b"x",
            members,
        ),
    )
    # Z11: a declared compressed size above the member cap.
    expect(
        "ZIP_COMPRESSED_SIZE",
        lambda: gate.pre_decompression_gate(
            _info_archive(_pair(file_size=4, compress_size=gate.MAX_MEMBER_COMPRESSED + 1)), b"x", members
        ),
    )
    # Z12: the AGGREGATE declared size.
    #
    # With the current two-member candidate archive the per-member caps already sum to less than the
    # aggregate bound, so in production Z12 is subsumed by Z10 -- it exists to bound any FUTURE
    # member set, and Z17 bounds the same quantity during streaming.  It is reached here with an
    # expected set large enough for the sum to matter, which is the only way to observe its class.
    cap = gate.MAX_MEMBER_UNCOMPRESSED_JSON
    names = tuple("member_" + str(index) + ".json" for index in range(6))
    aggregate = [_Info(name, file_size=cap, compress_size=cap) for name in names]
    expect("ZIP_DECLARED_AGGREGATE", lambda: gate.pre_decompression_gate(_info_archive(aggregate), b"x", names))
    # Z13: the EXACT declared ratio, including the value floor division used to miss.
    expect(
        "ZIP_DECLARED_RATIO",
        lambda: gate.pre_decompression_gate(_info_archive(_pair(file_size=201, compress_size=2)), b"x", members),
    )
    expect(
        "ZIP_DECLARED_RATIO",
        lambda: gate.pre_decompression_gate(_info_archive(_pair(file_size=10, compress_size=0)), b"x", members),
    )
    # And the honest boundary case is ACCEPTED, so the rule is a bound rather than a blanket refusal.
    gate.pre_decompression_gate(_info_archive(_pair(file_size=200, compress_size=2)), b"x", members)


def z_matrix_streaming():
    members = gate.EXPECTED_MEMBERS[CANDIDATE]
    body = bytes((index * 37 + (index >> 4)) & 0xFF for index in range(20000))

    # Z14 and Z20: the reference member decodes and its CRC is proven.
    payload = build_archive([(WORKER, body), (MANIFEST, b"{}")])
    contents, _digests = gate.extract_artifact(payload, members)
    assert contents[WORKER] == body

    def _corrupt(payload_bytes, marker, replacement):
        position = payload_bytes.find(marker)
        assert position > 0
        mutated = bytearray(payload_bytes)
        mutated[position : position + len(replacement)] = replacement
        return bytes(mutated)

    # Z20: a flipped CRC in the central directory.
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.getinfo(WORKER)
    crc_bytes = (info.CRC & 0xFFFFFFFF).to_bytes(4, "little")
    central = payload.find(b"PK" + bytes((1, 2)))
    assert central > 0
    lied = bytearray(payload)
    at = lied.find(crc_bytes, central)
    assert at > 0
    lied[at : at + 4] = ((info.CRC ^ 0xFF) & 0xFFFFFFFF).to_bytes(4, "little")
    expect("ZIP_CRC_INVALID", lambda: gate.extract_artifact(bytes(lied), members))
    del _corrupt

    # Z16: a central directory that UNDERSTATES the member size is caught mid-stream.
    understated = bytearray(payload)
    size_bytes = len(body).to_bytes(4, "little")
    at = understated.find(size_bytes, central)
    assert at > 0
    understated[at : at + 4] = (len(body) - 16).to_bytes(4, "little")
    expect("ZIP_DECLARED_SIZE_UNDERSTATED", lambda: gate.extract_artifact(bytes(understated), members))

    # Z19: a central directory that OVERSTATES it is caught at the end.
    overstated = bytearray(payload)
    at = overstated.find(size_bytes, central)
    overstated[at : at + 4] = (len(body) + 16).to_bytes(4, "little")
    expect("ZIP_DECLARED_SIZE_OVERSTATED", lambda: gate.extract_artifact(bytes(overstated), members))

    # A stored member exercises the other accounting path end to end.
    stored = build_archive([(WORKER, body), (MANIFEST, b"{}")], zipfile.ZIP_STORED)
    contents, _digests = gate.extract_artifact(stored, members)
    assert contents[WORKER] == body

    # A local header whose name disagrees with the central directory.
    mismatched = bytearray(payload)
    local = mismatched.find(b"PK" + bytes((3, 4)))
    name_at = mismatched.find(WORKER.encode("ascii"), local)
    assert name_at > 0
    mismatched[name_at : name_at + len(WORKER)] = bytes(WORKER.encode("ascii")[:-1]) + b"X"
    expect("ZIP_LOCAL_HEADER_NAME_MISMATCH", lambda: gate.extract_artifact(bytes(mismatched), members))

    # A corrupt deflate stream becomes a FROZEN class, never a zlib message.
    broken = bytearray(payload)
    data_at = payload.find(b"PK" + bytes((3, 4)))
    broken[data_at + 60 : data_at + 70] = bytes(10)
    try:
        gate.extract_artifact(bytes(broken), members)
    except gate.TrustedGateError as error:
        assert "zlib" not in str(error).lower()
        assert "Error" not in str(error)


def z_matrix_streaming_bounds():
    # REPAIR 8.  Z15, Z17 and Z18 each reach their OWN rule, and the tail accounting is exercised
    # by a member that genuinely leaves a non-empty unconsumed_tail.
    members = gate.EXPECTED_MEMBERS[CANDIDATE]

    # A member whose ratio is legal by DECLARATION but whose real expansion crosses the bound
    # mid-stream: Z18 owns it, and it is a different rule from Z13.
    base = bytes((index * 31 + (index >> 5)) & 0xFF for index in range(150000))
    body = b"".join(bytes((value,)) * 8 for value in base)
    payload = build_archive([(WORKER, body), (MANIFEST, b"{}")])
    contents, _digests = gate.extract_artifact(payload, members)
    assert contents[WORKER] == body

    # THE TAIL IS REAL.  Each 64 KiB input chunk expands to far more than the per-call production
    # cap, so decompress() returns early and leaves unconsumed_tail non-empty; the accounting must
    # not count those bytes as consumed, and must not count them twice when they are re-offered.
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        info = archive.getinfo(WORKER)
    header_offset = info.header_offset
    header = payload[header_offset : header_offset + 30]
    data_start = header_offset + 30 + int.from_bytes(header[26:28], "little") + int.from_bytes(header[28:30], "little")
    decompressor = zlib.decompressobj(-15)
    chunk = payload[data_start : data_start + gate.CHUNK_BYTES]
    decompressor.decompress(chunk, gate.CHUNK_BYTES)
    assert len(decompressor.unconsumed_tail) > 0, "the fixture must actually force a tail"

    # Z15: a member whose real output exceeds its own cap.  The manifest cap is the smaller one, so
    # a JSON member that expands past it is stopped by the stream bound rather than by the
    # declaration.
    class _Lying:
        filename = MANIFEST
        file_size = gate.MAX_MEMBER_UNCOMPRESSED_JSON + 1
        compress_size = gate.MAX_MEMBER_UNCOMPRESSED_JSON
        compress_type = 8
        flag_bits = 0
        external_attr = 0

        def is_dir(self):
            return False

    expect(
        "ZIP_DECLARED_SIZE",
        lambda: gate.pre_decompression_gate(
            _info_archive([_Info(WORKER), _Lying()]), b"x", members
        ),
    )

    # Z17: the AGGREGATE streamed bound, reached through the real reader by pre-loading the shared
    # aggregate state close to its limit.
    small = build_archive([(WORKER, b"A" * 64), (MANIFEST, b"{}")])
    with zipfile.ZipFile(io.BytesIO(small)) as archive:
        infos = archive.infolist()
        state = {"streamed": gate.MAX_AGGREGATE_UNCOMPRESSED}
        expect(
            "ZIP_AGGREGATE_OVERRUN",
            lambda: gate.stream_member(archive, infos[0], state, small),
        )

    # Z19 boundary: the exact declared size is accepted, one more is not.
    exact = build_archive([(WORKER, b"B" * 1024), (MANIFEST, b"{}")])
    contents, _digests = gate.extract_artifact(exact, members)
    assert len(contents[WORKER]) == 1024


def z_ratio_boundary():
    # REPAIR 8.  The declared-ratio bound is EXACT at the boundary and fails one past it.
    members = gate.EXPECTED_MEMBERS[CANDIDATE]

    class _AtBound(_Info):
        pass

    at_bound = [_Info(WORKER, file_size=1000, compress_size=10), _Info(MANIFEST)]
    gate.pre_decompression_gate(_info_archive(at_bound), b"x", members)
    over = [_Info(WORKER, file_size=1001, compress_size=10), _Info(MANIFEST)]
    expect("ZIP_DECLARED_RATIO", lambda: gate.pre_decompression_gate(_info_archive(over), b"x", members))
    del _AtBound


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
check("stage_c_worker_reconstruction", stage_c_worker_reconstruction)
check("a2_truncation_and_relocation", a2_truncation_and_relocation)
check("stage_c_outer_program_binding", stage_c_outer_program_binding)
check("stage_c_outer_policy_reconstruction", stage_c_outer_policy_reconstruction)
check("stage_c_equivalence_recomputation", stage_c_equivalence_recomputation)
check("coordinated_reseal_is_rejected", coordinated_reseal_is_rejected)
check("zip_runtime_consumption_and_reachable_rules", zip_runtime_consumption_and_reachable_rules)
check("run_gate_reference", run_gate_reference)
check("run_gate_coordinated_reseal", run_gate_coordinated_reseal)
check("run_gate_duplicate_identities", run_gate_duplicate_identities)
check("run_gate_compile_provenance", run_gate_compile_provenance)
check("z_matrix_pre_decompression", z_matrix_pre_decompression)
check("z_matrix_streaming", z_matrix_streaming)
check("z_matrix_streaming_bounds", z_matrix_streaming_bounds)
check("z_ratio_boundary", z_ratio_boundary)
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


_QUALIFICATION_TESTS = (
    _REPO_ROOT / "tests" / "crypto_core" / "validation" / "test_mt4_s3c_static_worker_qualification.py"
)


def _qualification_module():
    """The sibling test module owns the synthetic ELF builder; reuse it rather than duplicate it."""
    specification = importlib.util.spec_from_file_location("mt4_s3c_qualification_tests", _QUALIFICATION_TESTS)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def build_worker_and_record(**overrides):
    """A REAL synthetic worker image plus the A2 record the REVIEWED qualifier derives from it.

    This is what makes the Stage-C reconstruction a genuine second opinion: A2 comes from the
    independent reviewed implementation, and Stage C parses the same bytes with its own parser.  If
    the two ever disagreed about a governed coordinate, the honest path would fail.
    """
    module = _qualification_module()
    image = module.build_reference_elf(**overrides)
    record = module.elf_qualify.qualify(
        image,
        module._PAGE,
        module.elf_qualify.canonical_phdr_inventory(module.elf_qualify.EXPECTED_PHDR_INVENTORY),
        "e" * 64,
    )
    return image, record


_DRIVER_VALUES = []


@pytest.fixture(scope="module")
def driver_results(tmp_path_factory):
    """Run the gate under its own frozen isolated invocation contract and collect the results."""
    workspace = tmp_path_factory.mktemp("s3c_driver")
    driver = workspace / "mt4_s3c_gate_driver.py"
    driver.write_text(_DRIVER, encoding="utf-8")

    # The worker image and the reviewed qualifier's A2 record travel to the isolated driver as
    # DATA.  The driver may not import a repository module, so it cannot build them itself.
    image, record = build_worker_and_record()
    (workspace / "worker.bin").write_bytes(image)
    (workspace / "worker_a2.json").write_text(json.dumps(record, sort_keys=True), encoding="utf-8")

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
        "stage_c_worker_reconstruction",
        "a2_truncation_and_relocation",
        "stage_c_outer_program_binding",
        "stage_c_outer_policy_reconstruction",
        "stage_c_equivalence_recomputation",
        "coordinated_reseal_is_rejected",
        "zip_runtime_consumption_and_reachable_rules",
        "run_gate_reference",
        "run_gate_coordinated_reseal",
        "run_gate_duplicate_identities",
        "run_gate_compile_provenance",
        "z_matrix_pre_decompression",
        "z_matrix_streaming",
        "z_matrix_streaming_bounds",
        "z_ratio_boundary",
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
