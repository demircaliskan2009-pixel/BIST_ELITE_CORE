"""Deterministic CRYPTO_CORE_AGENT_OS_V2 control-plane validator.

Enforcement for the Agent OS v2 control plane described in ``docs/crypto_core/agent_os_v2.md``.

Properties (deliberate and load-bearing):

* stdlib only, deterministic, no network calls, no secret reads, no mutation;
* returns a non-zero exit code on any violation, with concise actionable messages;
* every check is repo-root relative so tests can run it against a temporary copy.

This validator governs the control plane only. It proves no repository, PR or CI state, grants no
readiness/connector/live/capital authority, and satisfies no independent audit.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Canonical surfaces
# ---------------------------------------------------------------------------

AGENT_OS_V2_DOC = "docs/crypto_core/agent_os_v2.md"
CONTINUITY_INDEX = "docs/crypto_core/continuity/CONTINUITY_INDEX.md"
MANIFEST_SCHEMA = "docs/crypto_core/continuity/state_manifest.schema.json"
MANIFEST_EXAMPLE = "docs/crypto_core/continuity/state_manifest.example.json"
CURRENT_STATE_DOC = "docs/crypto_core_current_state.md"
COPILOT_SHIM = ".github/copilot-instructions.md"
WORKFLOW_DOC = "docs/crypto_core/agent_workflow.md"
CODEX_SKILL = ".codex/skills/crypto-core-max-safe/SKILL.md"
CLAUDE_SKILL = ".claude/skills/crypto-core-token-efficient-loop/SKILL.md"

# Check A - every file the v2 control plane requires to exist.
REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    AGENT_OS_V2_DOC,
    WORKFLOW_DOC,
    CONTINUITY_INDEX,
    MANIFEST_SCHEMA,
    MANIFEST_EXAMPLE,
    CODEX_SKILL,
    CLAUDE_SKILL,
    CURRENT_STATE_DOC,
    COPILOT_SHIM,
    "scripts/crypto_core/validate_agent_os_v2.py",
    "tests/crypto_core/test_agent_os_v2_contract.py",
)

# Check B - exact legacy control-plane paths retired by the v2 migration. Reintroduction is a violation.
RETIRED_PATHS = (
    ".github/instructions/crypto-high-throughput.instructions.md",
    ".github/instructions/product-value-implementation.instructions.md",
    ".github/instructions/system.instructions.md",
    ".github/instructions/toolchain.instructions.md",
    ".github/agents/crypto-core-engineer.agent.md",
    ".github/agents/crypto-product-auditor.agent.md",
    ".github/agents/crypto-throughput-commander.agent.md",
    ".github/prompts/crypto-current-branch-triage.prompt.md",
    ".github/prompts/crypto-error-to-protocol-update.prompt.md",
    ".github/prompts/crypto-four-day-sprint-dispatch.prompt.md",
    ".github/prompts/crypto-model-escalation-policy.prompt.md",
    ".github/prompts/crypto-next-phase-planner.prompt.md",
    ".github/prompts/crypto-phase-runner-high-throughput.prompt.md",
    ".github/prompts/crypto-post-pr-retrospective.prompt.md",
    ".github/prompts/crypto-pr-closeout.prompt.md",
    ".github/prompts/crypto-product-layer-audit.prompt.md",
    ".github/prompts/crypto-product-pr-closeout.prompt.md",
    ".github/prompts/crypto-product-slice-runner.prompt.md",
    ".github/prompts/crypto-review-thread-resolver.prompt.md",
    ".github/skills/crypto-data-pipeline/SKILL.md",
    ".github/skills/crypto-deployment-pipeline/SKILL.md",
    ".github/skills/crypto-edge-discovery/SKILL.md",
    ".github/skills/crypto-edge-engine/SKILL.md",
    ".github/skills/crypto-event-orchestrator/SKILL.md",
    ".github/skills/crypto-experiment-tracker/SKILL.md",
    ".github/skills/crypto-failure-replay/SKILL.md",
    ".github/skills/crypto-feature-store/SKILL.md",
    ".github/skills/crypto-knowledge-memory/SKILL.md",
    ".github/skills/crypto-message-bus/SKILL.md",
    ".github/skills/crypto-portfolio-simulator/SKILL.md",
    ".github/skills/crypto-resource-manager/SKILL.md",
    ".github/skills/crypto-risk-execution/SKILL.md",
    ".github/skills/crypto-sandbox/SKILL.md",
    ".github/skills/crypto-scheduler/SKILL.md",
    ".github/skills/crypto-state-store/SKILL.md",
    ".github/skills/crypto-system-orchestrator/SKILL.md",
    ".github/skills/crypto-test-fixtures/SKILL.md",
    ".github/skills/crypto-walk-forward-shadow/SKILL.md",
    ".github/skills/_shared/references/contract-schema.md",
    ".github/hooks/hook-engine.md",
    "docs/crypto_core/COPILOT_HIGH_THROUGHPUT_OPERATING_PROTOCOL.md",
    "docs/crypto_core/COPILOT_CUSTOM_AGENT_CRYPTO_THROUGHPUT_COMMANDER.md",
    "docs/crypto_core/CLAUDE_COLLABORATION_AND_PROJECT_GUIDE.md",
)

# Check C - canonical v2 markers that must appear in each active control-plane surface.
CANONICAL_MARKERS = {
    "AGENTS.md": ("CRYPTO_CORE_AGENT_OS_V2", AGENT_OS_V2_DOC),
    "CLAUDE.md": ("CRYPTO_CORE_AGENT_OS_V2", AGENT_OS_V2_DOC),
    AGENT_OS_V2_DOC: ("CRYPTO_CORE_AGENT_OS_V2",),
    WORKFLOW_DOC: ("CRYPTO_CORE_AGENT_OS_V2",),
    CODEX_SKILL: ("CRYPTO_CORE_AGENT_OS_V2", AGENT_OS_V2_DOC),
    CLAUDE_SKILL: ("CRYPTO_CORE_AGENT_OS_V2", AGENT_OS_V2_DOC),
}

# Checks F-V - required identifier rails inside the canonical control plane, keyed by check letter.
AGENT_OS_V2_REQUIRED_MARKERS = {
    "F": ("ONE_REPOSITORY_WRITER",),
    "G": ("ONE_OPEN_PR",),
    "H": ("EXPLICIT_HUMAN_MERGE_AUTHORIZATION",),
    "I": ("NO_DIRECT_MAIN_PUSH",),
    "J": ("BLOCKER_ESCAPE_PROTOCOL_V1", "FIXED_POINT_STOP", "ONE_CONSOLIDATED_REPAIR"),
    "K": ("CONTEXT_CONTINUITY_PROTOCOL_V1", "STATE_MANIFEST_V1", "CURRENT_HANDOFF_V2"),
    "L": ("PROMPT_COMPILER_V2", "SEMANTIC_BOUNDARY", "STOP_CONDITIONS", "PROMPT_LANGUAGE_PROHIBITED"),
    "M": ("MAX_SAFE_PR",),
    "T": ("BLOCKER_ARTIFACT_MULTIPLICATION_PROHIBITED",),
    "U": ("CHATGPT_WORK_LANE", "WORK_LANE_BOUNDARIES"),
    "V": ("EXPLICIT_HUMAN_MERGE_AUTHORIZATION", "NO_SELF_APPROVAL", "READINESS_AUTHORITY_NOT_INFERRED"),
}

# Required prose whose MEANING is load-bearing. Matched against whitespace-normalized text so that
# rewrapping a paragraph is harmless but deleting or inverting the rule is a violation. A paragraph-level
# forbidden-wording scan cannot catch an inversion like "Work receives blanket write authority" inside a
# paragraph that still says "never" elsewhere - these positive phrases can.
AGENT_OS_V2_REQUIRED_PHRASES = {
    "F": ("one repository writer at a time",),
    "G": ("exactly one open PR by default",),
    "M": ("semantic closure", "never by file count, LOC count"),
    "U": (
        "Work never receives blanket write authority",
        "never mutates the repository",
    ),
    "V": ("merge remains explicit per-PR human authority",),
}

CONTINUITY_INDEX_REQUIRED_MARKERS = (
    "CONTEXT_CONTINUITY_PROTOCOL_V1",
    "STATE_MANIFEST_V1",
    "CURRENT_HANDOFF_V2",
    "MODE=READ_ONLY",
)

# Check R - the exact active lane set. No other lane may appear in the canonical routing matrix.
EXPECTED_ROUTING_LANES = (
    "ChatGPT GPT-5.6 Thinking (controller)",
    "ChatGPT Work (Local / Cloud)",
    "GitHub connector",
    "Deep Research",
    "Claude Opus 5",
    "Claude Sonnet 5",
    "Codex GPT-5.6 Sol",
    "Codex GPT-5.6 Terra",
    "Codex GPT-5.6 Luna",
)
ROUTING_MATRIX_BEGIN = "<!-- ROLE_ROUTING_MATRIX_V2:BEGIN -->"
ROUTING_MATRIX_END = "<!-- ROLE_ROUTING_MATRIX_V2:END -->"

# Checks D/E/R/S/U - forbidden active wording. The negation is bound to the ASSERTION that carries the
# forbidden phrase - the sentence or table cell it appears in - never to the surrounding block. A
# block-scoped check is unsound: an unrelated "never ..." sentence elsewhere in the same paragraph would
# mask a reactivation such as "Claude Fable 5 is an active default executor." and let the CI gate stay
# green. The only exemption is an explicitly fenced prohibited-wording inventory (see
# INVENTORY_FENCE_BEGIN), which may exist only in the files listed in INVENTORY_FENCE_ALLOWED_FILES.
RETIREMENT_MARKERS = (
    "never",
    "not an active",
    "no active",
    "must not",
    "do not",
    "does not",
    "prohibit",
    "forbidden",
    "deprecated",
    "retired",
    "historical",
    "superseded",
    "archival",
    "inactive",
    "removed",
    "no lane",
    "no prompt",
)

FABLE_TOKENS = ("fable",)
COPILOT_AUTONOMY_PHRASES = (
    "copilot autonomous",
    "autonomous executor",
    "copilot agent is an execution host",
    "copilot is an execution host",
)
RESTART_UNTIL_SUCCESS_PHRASES = (
    "continue until done",
    "keep fixing until green",
    "restart until success",
    "do everything automatically",
    "approve your own work",
    "merge when you think ready",
    "ignore scope if needed",
    "retry until it passes",
)
BLANKET_AUTHORITY_PHRASES = (
    "blanket write",
    "blanket writes",
    "blanket mutation",
    "blanket github authority",
    "blanket merge authority",
    "blanket authority",
)
SUPERSEDED_MODEL_PHRASES = ("opus 4.8", "claude-opus-4-8", "claude-fable-5")

# An explicitly fenced inventory of prohibited wording. Text inside the fence is a list of phrases that
# must NOT be used, so the phrases themselves are expected there and are exempt from the assertion scan.
# The fence is not a general escape hatch: it is honoured only in these files, and its presence anywhere
# else is itself a violation.
INVENTORY_FENCE_BEGIN = "<!-- PROHIBITED_WORDING_INVENTORY:BEGIN -->"
INVENTORY_FENCE_END = "<!-- PROHIBITED_WORDING_INVENTORY:END -->"
INVENTORY_FENCE_ALLOWED_FILES = (AGENT_OS_V2_DOC, COPILOT_SHIM)

# Surfaces scanned for forbidden active wording.
V2_CONTROL_SURFACES = (
    "AGENTS.md",
    "CLAUDE.md",
    AGENT_OS_V2_DOC,
    CONTINUITY_INDEX,
    CODEX_SKILL,
    CLAUDE_SKILL,
    CURRENT_STATE_DOC,
    COPILOT_SHIM,
)

# Check P - durable surfaces that must never pin a live commit sha.
DURABLE_SURFACES = (
    "AGENTS.md",
    "CLAUDE.md",
    AGENT_OS_V2_DOC,
    CONTINUITY_INDEX,
    MANIFEST_EXAMPLE,
    CURRENT_STATE_DOC,
)
FORBIDDEN_START_SHA = "61cd4d6b960067ef4eaa5634fff10b6cecf72403"
SHA40_RE = re.compile(r"\b[0-9a-f]{40}\b")

# Check Q - stale current-state wording that the migration removed.
STALE_CURRENT_STATE_PHRASES = (
    "phase 16l",
    "phase16l",
    "gpt-5.5",
    "rerun `pytest",
    "rerun pytest",
)

# Check N - required STATE_MANIFEST_V1 concepts.
REQUIRED_MANIFEST_FIELDS = (
    "schema_version",
    "generated_at",
    "repo",
    "branch",
    "base_sha",
    "head_sha",
    "tree_sha",
    "worktree_state",
    "changed_files",
    "pr_number",
    "pr_state",
    "open_pr_count",
    "ci_runs",
    "reviews",
    "threads",
    "readiness_fingerprint",
    "connector_fingerprint",
    "model_runtime_proof",
    "task_intent",
    "semantic_boundary",
    "invalidation_reasons",
)

# Every repo-relative path this validator reads. Tests clone exactly this set into a temp directory.
SCANNED_FILES = tuple(dict.fromkeys(REQUIRED_FILES + V2_CONTROL_SURFACES + DURABLE_SURFACES))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_text(repo_root: Path, rel: str) -> str | None:
    """Return file text, or None when the file is absent or unreadable."""
    path = repo_root / rel
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _strip_inventory_fences(text: str) -> str:
    """Remove explicitly fenced prohibited-wording inventories; keep everything else intact."""
    pattern = re.escape(INVENTORY_FENCE_BEGIN) + r".*?" + re.escape(INVENTORY_FENCE_END)
    return re.sub(pattern, "", text, flags=re.DOTALL)


def _assertions(text: str) -> list[str]:
    """Split into individual assertions.

    An assertion is the unit a reader would judge true or false on its own: one table cell, or one
    sentence/clause of prose. Wrapped lines are rejoined first so rewrapping never changes the result.
    Splitting happens only on sentence terminators and semicolons - never on a dash or colon, which
    usually separate a subject from the predicate that retires it ("Claude Fable 5 - INACTIVE...").
    """
    units: list[str] = []
    paragraph_lines: list[str] = []

    def flush() -> None:
        if paragraph_lines:
            joined = " ".join(paragraph_lines)
            units.extend(re.split(r"(?<=[.!?;])\s+", joined))
            paragraph_lines.clear()

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            flush()
            continue
        if line.startswith("|"):
            flush()
            units.extend(cell for cell in line.strip("|").split("|"))
            continue
        paragraph_lines.append(line)
    flush()
    return [unit for unit in units if unit.strip()]


def _has_marker(assertion: str) -> bool:
    lowered = assertion.lower()
    return any(marker in lowered for marker in RETIREMENT_MARKERS)


def _forbidden_wording(repo_root: Path, rel: str, phrases: tuple[str, ...], label: str) -> list[str]:
    text = _read_text(repo_root, rel)
    if text is None:
        return []
    if rel in INVENTORY_FENCE_ALLOWED_FILES:
        text = _strip_inventory_fences(text)
    violations = []
    for assertion in _assertions(text):
        lowered = assertion.lower()
        for phrase in phrases:
            if phrase in lowered and not _has_marker(assertion):
                snippet = " ".join(assertion.split())[:120]
                violations.append(f"{label}: '{phrase}' stated as active authority in {rel}: {snippet}")
    return violations


def _check_inventory_fence_placement(repo_root: Path) -> list[str]:
    """The inventory fence must never appear outside the files allowed to carry it."""
    violations = []
    for rel in V2_CONTROL_SURFACES:
        if rel in INVENTORY_FENCE_ALLOWED_FILES:
            continue
        text = _read_text(repo_root, rel)
        if text is not None and INVENTORY_FENCE_BEGIN in text:
            violations.append(f"S: prohibited-wording inventory fence is not allowed in {rel}")
    return violations


def _routing_lanes(text: str) -> list[str] | None:
    """Extract the first-column lane names from the canonical routing matrix block."""
    start = text.find(ROUTING_MATRIX_BEGIN)
    end = text.find(ROUTING_MATRIX_END)
    if start < 0 or end < 0 or end < start:
        return None
    block = text[start + len(ROUTING_MATRIX_BEGIN) : end]
    lanes = []
    for line in block.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or not cells[0]:
            continue
        if cells[0] == "Lane" or set(cells[0]) <= {"-", ":"}:
            continue
        lanes.append(cells[0])
    return lanes


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_required_files(repo_root: Path) -> list[str]:
    return [f"A: required Agent OS v2 file missing: {rel}" for rel in REQUIRED_FILES if not (repo_root / rel).is_file()]


def _check_retired_paths(repo_root: Path) -> list[str]:
    return [
        f"B: retired legacy control-plane path present: {rel}" for rel in RETIRED_PATHS if (repo_root / rel).exists()
    ]


def _check_canonical_markers(repo_root: Path) -> list[str]:
    violations = []
    for rel, markers in CANONICAL_MARKERS.items():
        text = _read_text(repo_root, rel)
        if text is None:
            violations.append(f"C: cannot read control-plane surface: {rel}")
            continue
        violations.extend(f"C: canonical Agent OS v2 marker '{m}' missing in {rel}" for m in markers if m not in text)
    return violations


def _check_forbidden_active_wording(repo_root: Path) -> list[str]:
    violations = []
    for rel in V2_CONTROL_SURFACES:
        violations.extend(_forbidden_wording(repo_root, rel, FABLE_TOKENS, "D"))
        violations.extend(_forbidden_wording(repo_root, rel, COPILOT_AUTONOMY_PHRASES, "E"))
        violations.extend(_forbidden_wording(repo_root, rel, RESTART_UNTIL_SUCCESS_PHRASES, "S"))
        violations.extend(_forbidden_wording(repo_root, rel, BLANKET_AUTHORITY_PHRASES, "U"))
        violations.extend(_forbidden_wording(repo_root, rel, SUPERSEDED_MODEL_PHRASES, "R"))
    violations.extend(_check_inventory_fence_placement(repo_root))
    shim = _read_text(repo_root, COPILOT_SHIM)
    if shim is None:
        violations.append(f"E: cannot read {COPILOT_SHIM}")
    else:
        for marker in ("INACTIVE_UNAVAILABLE", "CRYPTO_CORE_AGENT_OS_V2"):
            if marker not in shim:
                violations.append(f"E: Copilot shim marker '{marker}' missing in {COPILOT_SHIM}")
    return violations


def _check_agent_os_v2_rails(repo_root: Path) -> list[str]:
    text = _read_text(repo_root, AGENT_OS_V2_DOC)
    if text is None:
        return [f"F-V: cannot read {AGENT_OS_V2_DOC}"]
    normalized = " ".join(text.split())
    violations = []
    for check, markers in AGENT_OS_V2_REQUIRED_MARKERS.items():
        violations.extend(
            f"{check}: required rail '{m}' missing in {AGENT_OS_V2_DOC}" for m in markers if m not in text
        )
    for check, phrases in AGENT_OS_V2_REQUIRED_PHRASES.items():
        violations.extend(
            f"{check}: required rule '{p}' missing or inverted in {AGENT_OS_V2_DOC}"
            for p in phrases
            if " ".join(p.split()) not in normalized
        )
    return violations


def _check_continuity_index(repo_root: Path) -> list[str]:
    text = _read_text(repo_root, CONTINUITY_INDEX)
    if text is None:
        return [f"K: cannot read {CONTINUITY_INDEX}"]
    return [
        f"K: continuity marker '{m}' missing in {CONTINUITY_INDEX}"
        for m in CONTINUITY_INDEX_REQUIRED_MARKERS
        if m not in text
    ]


def _check_routing_lanes(repo_root: Path) -> list[str]:
    text = _read_text(repo_root, AGENT_OS_V2_DOC)
    if text is None:
        return [f"R: cannot read {AGENT_OS_V2_DOC}"]
    lanes = _routing_lanes(text)
    if lanes is None:
        return [f"R: canonical ROLE_ROUTING_MATRIX_V2 block missing in {AGENT_OS_V2_DOC}"]
    violations = []
    expected = set(EXPECTED_ROUTING_LANES)
    seen = set()
    for lane in lanes:
        if lane not in expected:
            violations.append(f"R: unsupported lane in canonical routing matrix: {lane}")
        elif lane in seen:
            violations.append(f"R: duplicate lane in canonical routing matrix: {lane}")
        seen.add(lane)
    violations.extend(
        f"R: required lane missing from canonical routing matrix: {lane}"
        for lane in EXPECTED_ROUTING_LANES
        if lane not in seen
    )
    return violations


def _check_manifest_schema(repo_root: Path) -> list[str]:
    raw = _read_text(repo_root, MANIFEST_SCHEMA)
    if raw is None:
        return [f"N: cannot read {MANIFEST_SCHEMA}"]
    try:
        schema = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"N: {MANIFEST_SCHEMA} is not valid JSON: {exc}"]
    if not isinstance(schema, dict):
        return [f"N: {MANIFEST_SCHEMA} must be a JSON object"]
    properties = schema.get("properties")
    required = schema.get("required")
    if not isinstance(properties, dict):
        return [f"N: {MANIFEST_SCHEMA} has no 'properties' object"]
    if not isinstance(required, list):
        return [f"N: {MANIFEST_SCHEMA} has no 'required' array"]
    violations = []
    if schema.get("title") != "STATE_MANIFEST_V1":
        violations.append(f"N: {MANIFEST_SCHEMA} title must be 'STATE_MANIFEST_V1'")
    for field in REQUIRED_MANIFEST_FIELDS:
        if field not in properties:
            violations.append(f"N: state manifest schema property missing: {field}")
        if field not in required:
            violations.append(f"N: state manifest schema required field missing: {field}")
    return violations


def _check_manifest_example(repo_root: Path) -> list[str]:
    raw = _read_text(repo_root, MANIFEST_EXAMPLE)
    if raw is None:
        return [f"O: cannot read {MANIFEST_EXAMPLE}"]
    try:
        example = json.loads(raw)
    except json.JSONDecodeError as exc:
        return [f"O: {MANIFEST_EXAMPLE} is not valid JSON: {exc}"]
    if not isinstance(example, dict):
        return [f"O: {MANIFEST_EXAMPLE} must be a JSON object"]
    violations = []
    if example.get("example_only") is not True:
        violations.append(f'O: {MANIFEST_EXAMPLE} must set "example_only": true')
    if "EXAMPLE_ONLY" not in raw:
        violations.append(f"O: {MANIFEST_EXAMPLE} must be explicitly labelled EXAMPLE_ONLY")
    if example.get("schema_version") != "STATE_MANIFEST_V1":
        violations.append(f"O: {MANIFEST_EXAMPLE} schema_version must be 'STATE_MANIFEST_V1'")
    violations.extend(
        f"O: example manifest missing required field: {f}" for f in REQUIRED_MANIFEST_FIELDS if f not in example
    )
    return violations


def _check_durable_state_pins(repo_root: Path) -> list[str]:
    violations = []
    for rel in DURABLE_SURFACES:
        text = _read_text(repo_root, rel)
        if text is None:
            continue
        if FORBIDDEN_START_SHA in text:
            violations.append(f"P: durable surface {rel} pins the migration start SHA as project state")
        for match in SHA40_RE.findall(text):
            if match != FORBIDDEN_START_SHA:
                violations.append(f"P: durable surface {rel} pins a mutable 40-hex commit sha: {match}")
    return violations


def _check_current_state_doc(repo_root: Path) -> list[str]:
    text = _read_text(repo_root, CURRENT_STATE_DOC)
    if text is None:
        return [f"Q: cannot read {CURRENT_STATE_DOC}"]
    lowered = text.lower()
    violations = [
        f"Q: stale current-state wording '{phrase}' present in {CURRENT_STATE_DOC}"
        for phrase in STALE_CURRENT_STATE_PHRASES
        if phrase in lowered
    ]
    for marker in ("CRYPTO_CORE_AGENT_OS_V2", "CONTINUITY_INDEX"):
        if marker not in text:
            violations.append(f"Q: durable pointer '{marker}' missing in {CURRENT_STATE_DOC}")
    return violations


CHECKS = (
    _check_required_files,
    _check_retired_paths,
    _check_canonical_markers,
    _check_forbidden_active_wording,
    _check_agent_os_v2_rails,
    _check_continuity_index,
    _check_routing_lanes,
    _check_manifest_schema,
    _check_manifest_example,
    _check_durable_state_pins,
    _check_current_state_doc,
)


def validate(repo_root: Path) -> list[str]:
    """Return a deterministic, sorted list of control-plane violations (empty means PASS)."""
    violations: list[str] = []
    for check in CHECKS:
        violations.extend(check(repo_root))
    return sorted(dict.fromkeys(violations))


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate the CRYPTO_CORE_AGENT_OS_V2 control plane.")
    parser.add_argument("--repo-root", default=None, help="Repository root to validate (default: this checkout).")
    args = parser.parse_args(argv)

    repo_root = Path(args.repo_root).resolve() if args.repo_root else repo_root_from_here()
    violations = validate(repo_root)
    if violations:
        print(f"AGENT_OS_V2_VALIDATION: FAIL ({len(violations)} violation(s))")
        for violation in violations:
            print(f"  - {violation}")
        return 1
    print("AGENT_OS_V2_VALIDATION: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
