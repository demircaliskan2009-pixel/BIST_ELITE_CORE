#!/usr/bin/env python3
"""Deterministic structural validator for the crypto_core Agent OS control plane.

<!-- CONTROL_PLANE_ROLE: EXECUTABLE_SUBORDINATE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

NEGATIVE_BOUNDARY: The repository validator proves repository-provable structure only. It does NOT prove that its own GitHub CI step executed, that GitHub will block a merge, or that a required status context identifies a particular workflow file or revision.

Scope and honest limits
-----------------------
This validator is stdlib-only, offline, deterministic, read-only and secret-free. It proves
STRUCTURE and BOUNDED LEXICAL CONTRACTS over the control-plane surfaces registered in
``docs/crypto_core/agent_os_v2.md`` section 20:

* exactly one canonical authority, and exactly one role marker per registered surface;
* exact membership of ``ACTIVE_DOCTRINE_SURFACES``, ``REQUIRED_CONTROL_PLANE_ARTIFACTS``,
  ``DURABLE_SURFACES``, ``MODEL_AGNOSTIC_SURFACES`` and ``RETIRED_CONTROL_PLANE_PATHS``;
* singularity and exact value of the canonical authority declarations;
* the machine-readable ``ROUTE:`` routing table and its internal consistency;
* the fixed marker blocks (effort enum, prompt-compiler fields, evidence classes, Work contract);
* the durable-surface volatile-state scan over the exact declared set - three literal pin forms
  plus an ASSIGNMENT to any field in the ``VOLATILE_STATE_FIELDS`` registry, and nothing else;
* the ephemeral-manifest proof-pairing contract against the ``PROOF_PAIRED_MANIFEST_FIELDS``
  registry, in both directions so the registry and the operational grammar cannot drift apart;
* the model-agnostic scan over the exact declared set;
* legacy retirement;
* the canonical typed operational grammar, and that the committed manifest schema equals the
  schema generated from it.

It does NOT and MUST NOT claim to: understand arbitrary English; detect an arbitrary natural-language
paraphrase that contradicts a declaration; know live GitHub state; know the runtime model; judge audit
correctness, readiness or capital safety. Arbitrary semantic contradiction is the responsibility of
the INDEPENDENT SEMANTIC AUDIT. Growing a synonym blacklist to chase paraphrase is an explicit
anti-pattern (``ROOT_CAUSE_MODE``, ``agent_os_v2.md`` section 13).

Exit code 0 means every structural contract above holds. Any failure exits 1 with an itemised list.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

CANONICAL = "docs/crypto_core/agent_os_v2.md"

# ---------------------------------------------------------------------------
# Vocabularies (bounded, explicit, and mirrored by an independent test oracle)
# ---------------------------------------------------------------------------

ROLE_VOCABULARY = frozenset(
    {
        "CANONICAL_AUTHORITY",
        "DURABLE_RAILS",
        "CLAUDE_ADAPTER",
        "CODEX_ADAPTER",
        "WORKFLOW_COMPANION",
        "AUTHORING_GUIDE",
        "COMPRESSION_GUIDE",
        "RESEARCH_ADAPTER",
        "CONTINUITY_INDEX",
        "LESSONS_COMPANION",
        "COPILOT_INACTIVE_SHIM",
        "DURABLE_STATE_POINTER",
    }
)

CANONICAL_DECLARATIONS = (
    ("MERGE_AUTHORITY_SOURCE", "HUMAN_ONLY_PER_PR"),
    ("PR_SIZING_AUTHORITY", "SEMANTIC_CLOSURE_ONLY"),
    ("TASK_FAMILY_AUTHORITY", "CANONICAL_ONLY"),
    ("EFFORT_AUTHORITY", "CANONICAL_ONLY"),
)

EFFORT_ENUM = ("low", "medium", "high", "xhigh", "max")

PROMPT_COMPILER_FIELDS = (
    "TASK_INTENT",
    "SEMANTIC_BOUNDARY",
    "STATE_PIN",
    "MODEL_RUNTIME_PROOF",
    "ALLOWED_FILES",
    "INVARIANTS",
    "BLOCKER_INVENTORY",
    "VALIDATION_MATRIX",
    "GITHUB_AUTHORIZATION",
    "FORBIDDEN",
    "STOP_CONDITIONS",
    "HANDOFF",
)

MODEL_EVIDENCE_CLASSES = (
    "RUNTIME_TELEMETRY",
    "USER_ATTESTED_UI_SELECTION",
    "CONFIGURATION_EVIDENCE_ONLY",
    "UNKNOWN",
    "CONTRADICTED",
)

WORK_RETURN_CONTRACT = (
    "TASK",
    "ENVIRONMENT",
    "SOURCE_REVISIONS",
    "CLAIM_SOURCE_MAP",
    "VERIFIED",
    "INFERENCE",
    "UNKNOWN",
    "DECISIONS_NEEDED",
    "ARTIFACTS",
    "VALIDATION_RUN",
    "MUTATIONS",
    "INVALIDATION",
    "NEXT_SAFE_ACTION",
)

TASK_INTENTS = frozenset(
    {
        "STATUS",
        "CLOSEOUT",
        "BOUNDED_READ",
        "IMPLEMENTATION",
        "REPAIR",
        "REVIEW",
        "ARCHITECTURE",
        "PROMPT_ARCHITECTURE",
        "CLASS_C_CROSS_CONTRACT",
        "EXTERNAL_RESEARCH",
    }
)

ROUTE_CLASSES = frozenset({"T0", "T1", "T2", "T3A", "T3B", "T3C", "T3D", "T3E", "T4", "XR"})

MUTATION_AUTHORITIES = frozenset(
    {
        "MECHANICAL_ONLY",
        "GOVERNED_CLOSEOUT",
        "BOUNDED_MUTATION",
        "HEAVY_MUTATION",
        "CAPABILITY_CRITICAL_MUTATION",
        "READ_ONLY",
    }
)

# T3B exists for mutation work only; absorbing a read-only reasoning family into it is the exact
# defect that made the documented T3D/T3E strong-effort branches unreachable in the previous regime.
T3B_ALLOWED_INTENTS = frozenset({"IMPLEMENTATION", "REPAIR"})

# The protected frontier lane. A T4 row that names anything else is a silent downgrade.
# The read-only reasoning families run on Claude Opus 5. Their legal efforts are exact sets, so a
# family cannot silently acquire a stronger effort: T3C in particular must never reach max, because
# max is reserved for the families whose per-family trigger table grants it.
# The read-only reasoning families, and the EXACT lanes each may run on. T3C is deliberately the
# only one with two: ordinary review is where cross-family independence is available and worth
# having, so a reviewer that is not the implementer can always be chosen. T3D architecture and T3E
# prompt architecture stay single-lane because nothing about them is an independence question.
READ_ONLY_REASONING_LANES = {
    "T3C": {"Claude Opus 5": "claude-opus-5", "Codex GPT-5.6 Sol": "gpt-5.6-sol"},
    "T3D": {"Claude Opus 5": "claude-opus-5"},
    "T3E": {"Claude Opus 5": "claude-opus-5"},
}
READ_ONLY_REASONING_EFFORTS = {
    "T3C": frozenset({"medium", "high", "xhigh"}),
    "T3D": frozenset({"high", "xhigh", "max"}),
    "T3E": frozenset({"high", "xhigh", "max"}),
}

# Ordinary review must have a cross-family option, or "prefer the lane that did not implement it"
# is advice nobody can follow. This is the number of DISTINCT lanes T3C must actually route.
MIN_REVIEW_LANES = 2
PROTECTED_FRONTIER_EFFORTS = frozenset({"xhigh", "max"})

# The protected intent and the protected family are one set. Neither may exist without the other.
CLASS_C_INTENT = "CLASS_C_CROSS_CONTRACT"

# INTENT_FIRST_ROUTING. Routing is a function OF the task intent, so nothing may rewrite an intent
# after the controller assigns it. Stating that a protected trigger "escalates review into T4" made
# the family selectable by something other than its intent, which is the contradiction this block
# closes. It is enforced as a POSITIVE fixed contract - the exact rules must be present, in order -
# rather than by hunting for phrasings that contradict it.
INTENT_FIRST_ROUTING_RULES = (
    "- TASK_INTENT is assigned at task creation and is never mutated afterwards.",
    "- A protected trigger never converts a task into another family; REVIEW stays REVIEW.",
    "- Protected Class-C assurance is a SEPARATE read-only CLASS_C_CROSS_CONTRACT task routed to T4.",
    "- Completing the ordinary task never satisfies the protected gate, and the gate never replaces it.",
    "- A risk CLASS decides whether that separate gate is REQUIRED; it never rewrites an intent.",
)

FRONTIER_LANE = "GPT-6 Astra"
FRONTIER_MODEL_ID = "gpt-6-astra"

# Lanes that must never appear in ANY active route row.
# Lanes that must never appear in an ACTIVE route. Sol is deliberately absent: it is not retired,
# it is the primary repo-native engineering accelerator. What keeps Sol out of the protected gate
# is the T4 lane pin below, not a retirement claim that would be untrue.
RETIRED_ROUTE_LANE_TOKENS = ("Fable", "Copilot", "Opus 4")

# Retired PR-sizing template fields and heuristics. This list is deliberately EXACT and CLOSED: it
# catches the machine-readable field names and the literal retired phrases, and nothing else. English
# paraphrase is the semantic auditor's job, by design.
PROHIBITED_SIZING_TOKENS = (
    "MAX_CHANGED_FILES",
    "MAX_FILES_PER_PR",
    "max_changed_files",
    "max-changed-files",
    "smallest additive change",
    "one artifact per PR",
    "one module per PR",
    "one test per PR",
    "one file per PR",
)

# Model identifiers forbidden in the ACTIVE region of a MODEL_AGNOSTIC surface. A surface that cannot
# name a model cannot own model routing, cannot make a model a lifecycle step and cannot assert
# per-model task-family ownership - which is the structural closure of the duplicated-routing defect.
MODEL_TOKENS_CASE_INSENSITIVE = (
    "claude",
    "opus",
    "sonnet",
    "haiku",
    "fable",
    "codex",
    "chatgpt",
    "copilot",
    "gemini",
    "llama",
    "mistral",
    "anthropic",
    "openai",
)
MODEL_TOKENS_CASE_SENSITIVE = ("Sol", "Terra", "Luna", "Astra", "Ultra")
MODEL_FAMILY_RE = re.compile(r"\bGPT-\d", re.IGNORECASE)

PROVIDER_CAPACITY_STATES = ("NORMAL", "CONSERVE", "CRITICAL", "EXHAUSTED", "UNKNOWN")

CAPACITY_ROUTING_MODES = (
    "QUALITY_OPTIMAL",
    "CLAUDE_FIRST_CONSERVATION",
    "OPENAI_FIRST_CONSERVATION",
    "CLAUDE_CONTINUITY",
    "OPENAI_CONTINUITY",
    "BOTH_EXHAUSTED_STOP",
)

# A provider ratio may be stated as a planning SLO. It may never be encoded as an enforced constraint.
# This list is deliberately EXACT and CLOSED: it catches the machine-readable field forms, and English
# paraphrase is the semantic auditor's job by design.
PROHIBITED_RATIO_TOKENS = (
    "PROVIDER_RATIO:",
    "PROVIDER_RATIO=",
    "RATIO_INVARIANT",
    "REQUIRED_CLAUDE_RATIO",
    "MIN_CLAUDE_RATIO",
    "MAX_OPENAI_RATIO",
    "CLAUDE_OPENAI_RATIO",
    "ENFORCED_PROVIDER_RATIO",
)

VALIDATOR_REL = "scripts/crypto_core/validate_agent_os_v2.py"

# The independent contract test is listed in REQUIRED_CONTROL_PLANE_ARTIFACTS, which is a MUTABLE
# registry. Deleting the test and its registry entry together would therefore leave a self-consistent
# control plane with no oracle at all. This literal constant, plus the CI anchor step below, closes
# that circle from OUTSIDE the registry: the requirement survives the registry entry being removed.
BOOTSTRAP_ORACLE_PATH = "tests/crypto_core/test_agent_os_v2_contract.py"

# Provider capacity vocabulary used by the manifest relation checker.
CAPACITY_AVAILABLE = frozenset({"NORMAL", "CONSERVE", "CRITICAL"})
CAPACITY_CONSTRAINED = frozenset({"CONSERVE", "CRITICAL"})

# `max` legality is per family. A restriction belonging to ONE family must never be written as a
# restriction on the effort itself - doing so silently made the documented T3D/T3E/T4 max branches
# unreachable. This closed list catches the machine-readable relapse forms only; English paraphrase
# stays the independent audit's responsibility.
PROHIBITED_GLOBAL_MAX_TOKENS = (
    "under the T3B contract",
    "max is only legal in T3B",
    "max only exists in T3B",
    "max only in T3B",
)
# A T3B-only MAX_EFFORT_CLASSES declaration is caught STRUCTURALLY by the class-vs-matrix
# cross-check in _check_effort_family_legality, not lexically: the literal would be a prefix of
# the legitimate multi-class declaration and would false-positive on it.

# Volatile current-state patterns forbidden in the ACTIVE region of a DURABLE surface.
# The hex rule requires both a digit and a hex letter so ordinary words and plain numbers cannot
# false-positive; a real commit hash effectively always satisfies it.
# Git accepts uppercase and mixed-case object ids, so this match is CASE-INSENSITIVE. A lowercase-only
# rule let an uppercase head pin sit in a durable surface completely undetected, which defeated the
# first of the four bounded forms the durable-state boundary claims to reject.
HEX_TOKEN_RE = re.compile(
    r"(?<![0-9a-zA-Z])(?=[0-9a-f]{7,40}(?![0-9a-zA-Z]))(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}",
    re.IGNORECASE,
)
PR_PIN_RE = re.compile(r"\bPR\s*#\s*\d+")
OPEN_PR_PIN_RE = re.compile(r"\bOPEN_PR_COUNT\s*[:=]\s*\d+")
MAIN_AT_RE = re.compile(r"\bmain\s*@\s*[0-9a-f]{7,40}\b", re.IGNORECASE)

# Tokens the canonical authority must carry, so that removing a whole contract is a hard failure
# rather than a silent capability loss.
REQUIRED_CANONICAL_TOKENS = (
    "CRYPTO_CORE_AGENT_OS_V2_1",
    "CRYPTO_CORE_DOMAIN_OPERATING_PROFILE",
    "MAX_SAFE_PR",
    "ALLOWED_FILES",
    "MUTATION AUTHORIZATION BOUNDARY",
    "SELF_AUDIT_ONLY_NOT_INDEPENDENT",
    "CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE",
    "CHATGPT_WORK_LANE",
    "WORK_LANE_BOUNDARIES",
    "WORK_PREPARED_NOT_AUTHORIZED",
    "PROMPT_COMPILER_V2_1",
    "VALIDATION_BUDGET",
    "DAILY_BATCH_MANIFEST",
    "BLOCKER_ESCAPE_PROTOCOL_V2",
    "ROOT_CAUSE_MODE",
    "FIXED_POINT_STOP",
    "FIXED_POINT_NOT_REACHED",
    "BLOCKER_IDENTITY_SURVIVES_RENAME",
    "LARGE_MILESTONE_PROTOCOL",
    "CONTEXT_CONTINUITY_PROTOCOL_V2",
    "ZERO_MATERIAL_OPERATIONAL_CONTEXT_LOSS",
    "FRESH_CHAT_BOOTSTRAP",
    "STATE_MANIFEST_V1",
    "CURRENT_HANDOFF_V2",
    "MODEL_CAPABILITY_REFRESH_GATE",
    "GITHUB_CONNECTOR_POLICY",
    "CLOSED_FROZEN",
    "DURABLE_STATE_CLAIM_BOUNDARY",
    "TASK_SPECIFIC_EFFORT_SELECTION",
    "LOWEST_SAFE_HOST_SETTING",
    "PROVIDER_CAPACITY_CONTINUATION_MODE_V1",
    "PROVIDER_EXHAUSTION_IS_NOT_PROJECT_STOP",
    "USAGE_AWARE_CAPACITY_ROUTER_V1",
    "OPENAI_SHARED_AGENTIC_POOL",
    "NONPROTECTED_PROVIDER_BIAS",
    "WORK_ENVIRONMENT_VALUE",
    "SHARED_OPENAI_POOL_COST",
    "AUDIT_WAIT_CONTINUATION",
    "PREPARED_NOT_REVIEWABLE_YET",
    "STALE_INVALIDATED",
    "CAPACITY_STOP",
    "Work is not a separate free provider",
    "There is no enforced provider ratio anywhere in this control plane.",
    "PER_FAMILY_EFFORT_LEGALITY",
    "HOST_DISCOVERY_BEATS_REGISTRY_ASSUMPTION",
    "TYPED_EXEMPTION_REGIONS",
    "ORACLE_EXTERNAL_BOOTSTRAP_ANCHOR",
)

REQUIRED_CONTINUITY_INDEX_TOKENS = (
    "FRESH_CHAT_BOOTSTRAP",
    "STATE_MANIFEST_V1",
    "CURRENT_HANDOFF_V2",
    "CLOSED_FROZEN",
)

# Registry block names.
BLOCK_ACTIVE_SURFACES = "ACTIVE_DOCTRINE_SURFACES"
BLOCK_REQUIRED_ARTIFACTS = "REQUIRED_CONTROL_PLANE_ARTIFACTS"
BLOCK_DURABLE_SURFACES = "DURABLE_SURFACES"
BLOCK_MODEL_AGNOSTIC = "MODEL_AGNOSTIC_SURFACES"
BLOCK_RETIRED_PATHS = "RETIRED_CONTROL_PLANE_PATHS"
BLOCK_VOLATILE_FIELDS = "VOLATILE_STATE_FIELDS"
BLOCK_PROOF_PAIRED = "PROOF_PAIRED_MANIFEST_FIELDS"
BLOCK_CAPACITY_STATES = "PROVIDER_CAPACITY_STATES"
BLOCK_ROUTING_MODES = "CAPACITY_ROUTING_MODES"
BLOCK_HOST_DISCOVERY = "HOST_DISCOVERY_SCAN_PATHS"
BLOCK_MAX_FAMILY = "MAX_EFFORT_FAMILY_TRIGGERS"
BLOCK_ROUTING_MATRIX = "ROLE_ROUTING_MATRIX"
BLOCK_FAMILY_CONTRACT = "FAMILY_SEMANTIC_CONTRACT"
BLOCK_LANE_CAPABILITY = "LANE_CAPABILITY"
BLOCK_EFFORT_ENUM = "REASONING_EFFORT_ENUM"
BLOCK_PROMPT_FIELDS = "PROMPT_COMPILER_V2_1_FIELDS"
BLOCK_EVIDENCE_CLASSES = "MODEL_EVIDENCE_CLASSES"
BLOCK_WORK_CONTRACT = "WORK_RETURN_CONTRACT"
BLOCK_INTENT_FIRST = "INTENT_FIRST_ROUTING"

EXEMPT_REGION_BLOCKS = ("HISTORICAL_RECORD", "EXAMPLE_ONLY")


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _begin(name: str) -> str:
    return f"<!-- {name}_BEGIN -->"


def _end(name: str) -> str:
    return f"<!-- {name}_END -->"


def read_text(root: Path, rel: str) -> str | None:
    """Read a repository-relative text file as UTF-8, tolerating a BOM. None when absent."""
    path = root / rel
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8-sig")


def block_span(lines: list[str], name: str) -> tuple[int, int] | None:
    """Return the exclusive interior span of a single marker block, or None when it is not exactly one."""
    begins = [i for i, ln in enumerate(lines) if ln.strip() == _begin(name)]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == _end(name)]
    if len(begins) != 1 or len(ends) != 1 or ends[0] <= begins[0]:
        return None
    return (begins[0] + 1, ends[0])


def block_lines(text: str, name: str) -> list[str] | None:
    lines = text.splitlines()
    span = block_span(lines, name)
    if span is None:
        return None
    return [ln.strip() for ln in lines[span[0] : span[1]] if ln.strip()]


def exemption_scan(rel: str, lines: list[str]) -> tuple[list[str], list[tuple[int, str]]]:
    """Parse exempt regions with a TYPED STACK and return (failures, active lines).

    A shared anonymous depth counter - one counter per region type, or worse one counter for all of
    them - lets one region type close another. Opening HISTORICAL_RECORD, then EXAMPLE_ONLY, then
    closing HISTORICAL_RECORD would balance a naive counter while leaving the rest of the file
    exempt, which is exactly how a pinned value hides. The stack therefore carries the exact type of
    every open region, and a closer must match the type on top.

    Failing shapes: a crossed pair in either direction, a stray closer, an unterminated region, and
    any nesting - the contract defines no nested combination, so nesting is a violation rather than
    a tolerated case.
    """
    failures: list[str] = []
    stack: list[tuple[str, int]] = []
    active: list[tuple[int, str]] = []

    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()

        opened = next((name for name in EXEMPT_REGION_BLOCKS if stripped == _begin(name)), None)
        if opened is not None:
            if stack:
                failures.append(
                    f"{rel}:{lineno}: {opened}_BEGIN nested inside an open {stack[-1][0]} region; "
                    f"no nested exemption combination is defined"
                )
            stack.append((opened, lineno))
            continue

        closed = next((name for name in EXEMPT_REGION_BLOCKS if stripped == _end(name)), None)
        if closed is not None:
            if not stack:
                failures.append(f"{rel}:{lineno}: {closed}_END without a matching BEGIN")
            elif stack[-1][0] != closed:
                failures.append(
                    f"{rel}:{lineno}: crossed exemption regions - {closed}_END closes an open "
                    f"{stack[-1][0]} region opened at line {stack[-1][1]}"
                )
                stack.pop()
            else:
                stack.pop()
            continue

        if not stack:
            active.append((lineno, raw_line))

    for name, lineno in stack:
        failures.append(
            f"{rel}: unterminated {name}_BEGIN at line {lineno} (the region would swallow the rest of the file)"
        )
    return failures, active


def marker_region_failures(rel: str, lines: list[str]) -> list[str]:
    """Structural failures from the typed exemption parse."""
    return exemption_scan(rel, lines)[0]


def active_lines(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, text) for every line OUTSIDE an exempt region.

    Region membership is decided by the typed structural parse in ``exemption_scan``. Headings,
    section numbers and prose proximity are deliberately irrelevant: renaming or reformatting a
    heading cannot change which text is treated as active.
    """
    return exemption_scan("<scan>", lines)[1]


def parse_columns(text: str, name: str, columns: int) -> tuple[list[list[str]] | None, list[str]]:
    """Parse a ``- a :: b :: c`` registry into fixed-width rows. TOTAL: malformed rows are reported.

    Returns (rows, problems). `rows` is None only when the block itself is missing or malformed,
    which is a different failure from a block whose rows are wrong.
    """
    raw = parse_registry(text, name)
    if raw is None:
        return None, [f"{CANONICAL}: {name} block missing or malformed"]
    rows: list[list[str]] = []
    problems: list[str] = []
    for line in raw:
        cells = [cell.strip() for cell in line.split("::")]
        if len(cells) != columns or not all(cells):
            problems.append(f"{CANONICAL}: {name} row must have {columns} non-empty ':: '-separated columns: {line}")
            continue
        rows.append(cells)
    return rows, problems


def parse_registry(text: str, name: str) -> list[str] | None:
    """Parse a ``- <value>`` registry block."""
    raw = block_lines(text, name)
    if raw is None:
        return None
    values: list[str] = []
    for line in raw:
        if not line.startswith("- "):
            return None
        values.append(line[2:].strip())
    return values


def parse_surface_registry(text: str, name: str) -> list[tuple[str, str]] | None:
    """Parse a ``- <path> :: <ROLE>`` registry block."""
    raw = parse_registry(text, name)
    if raw is None:
        return None
    pairs: list[tuple[str, str]] = []
    for entry in raw:
        if " :: " not in entry:
            return None
        path, role = entry.split(" :: ", 1)
        pairs.append((path.strip(), role.strip()))
    return pairs


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def _check_registries(root: Path, failures: list[str]) -> dict[str, object] | None:
    canonical_text = read_text(root, CANONICAL)
    if canonical_text is None:
        failures.append(f"canonical authority missing: {CANONICAL}")
        return None

    surfaces = parse_surface_registry(canonical_text, BLOCK_ACTIVE_SURFACES)
    if surfaces is None:
        failures.append(f"{CANONICAL}: {BLOCK_ACTIVE_SURFACES} block missing or malformed")
        return None

    artifacts = parse_registry(canonical_text, BLOCK_REQUIRED_ARTIFACTS)
    durable = parse_registry(canonical_text, BLOCK_DURABLE_SURFACES)
    agnostic = parse_registry(canonical_text, BLOCK_MODEL_AGNOSTIC)
    retired = parse_registry(canonical_text, BLOCK_RETIRED_PATHS)
    volatile_pairs = parse_surface_registry(canonical_text, BLOCK_VOLATILE_FIELDS)
    proof_paired = parse_surface_registry(canonical_text, BLOCK_PROOF_PAIRED)
    host_globs = parse_registry(canonical_text, BLOCK_HOST_DISCOVERY)
    max_family = parse_registry(canonical_text, BLOCK_MAX_FAMILY)
    for label, value in (
        (BLOCK_REQUIRED_ARTIFACTS, artifacts),
        (BLOCK_DURABLE_SURFACES, durable),
        (BLOCK_MODEL_AGNOSTIC, agnostic),
        (BLOCK_RETIRED_PATHS, retired),
        (BLOCK_VOLATILE_FIELDS, volatile_pairs),
        (BLOCK_PROOF_PAIRED, proof_paired),
        (BLOCK_HOST_DISCOVERY, host_globs),
        (BLOCK_MAX_FAMILY, max_family),
    ):
        if value is None:
            failures.append(f"{CANONICAL}: {label} block missing or malformed")
    if (
        artifacts is None
        or durable is None
        or agnostic is None
        or retired is None
        or volatile_pairs is None
        or proof_paired is None
        or host_globs is None
        or max_family is None
    ):
        return None

    surface_paths = [p for p, _ in surfaces]
    for label, values in (
        (BLOCK_ACTIVE_SURFACES, surface_paths),
        (BLOCK_REQUIRED_ARTIFACTS, artifacts),
        (BLOCK_DURABLE_SURFACES, durable),
        (BLOCK_MODEL_AGNOSTIC, agnostic),
        (BLOCK_RETIRED_PATHS, retired),
        (BLOCK_VOLATILE_FIELDS, [f for f, _c in volatile_pairs]),
        (BLOCK_PROOF_PAIRED, [f for f, _c in proof_paired]),
        (BLOCK_HOST_DISCOVERY, host_globs),
        (BLOCK_MAX_FAMILY, max_family),
    ):
        if not values:
            failures.append(f"{CANONICAL}: {label} registry is empty")
        if len(set(values)) != len(values):
            failures.append(f"{CANONICAL}: {label} registry has duplicate entries")

    if CANONICAL not in surface_paths:
        failures.append(f"{CANONICAL} does not register itself in {BLOCK_ACTIVE_SURFACES}")

    for label, values in ((BLOCK_DURABLE_SURFACES, durable), (BLOCK_MODEL_AGNOSTIC, agnostic)):
        extra = sorted(set(values) - set(surface_paths))
        for path in extra:
            failures.append(f"{CANONICAL}: {label} entry is not an active doctrine surface: {path}")

    return {
        "canonical_text": canonical_text,
        "surfaces": surfaces,
        "artifacts": artifacts,
        "durable": durable,
        "agnostic": agnostic,
        "retired": retired,
        "volatile_fields": [f for f, _c in volatile_pairs],
        "proof_paired": [f for f, _c in proof_paired],
        "proof_paired_classes": dict(proof_paired),
        "host_globs": host_globs,
        "max_family": max_family,
    }


def _check_existence(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    for path, _role in surfaces:
        if not (root / path).is_file():
            failures.append(f"active doctrine surface missing from the tree: {path}")
    for path in ctx["artifacts"]:  # type: ignore[union-attr]
        if not (root / path).is_file():
            failures.append(f"required control-plane artifact missing from the tree: {path}")
    for path in ctx["retired"]:  # type: ignore[union-attr]
        if (root / path).exists():
            failures.append(f"retired control-plane path still present in the tree: {path}")

    # Anchored on a literal constant, NOT on the mutable required-artifact registry, so removing the
    # registry entry does not remove the requirement.
    if not (root / BOOTSTRAP_ORACLE_PATH).is_file():
        failures.append(
            f"independent contract oracle missing: {BOOTSTRAP_ORACLE_PATH} "
            f"(required by the external bootstrap anchor, independently of any registry entry)"
        )


def _check_roles(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    role_re = re.compile(r"<!--\s*CONTROL_PLANE_ROLE:\s*([A-Z_]+)\s*-->")
    ref_marker = f"<!-- CONTROL_PLANE_AUTHORITY_REF: {CANONICAL} -->"

    canonical_count = 0
    for path, expected_role in surfaces:
        if expected_role not in ROLE_VOCABULARY:
            failures.append(f"{path}: role {expected_role} is not in the role vocabulary")
        text = read_text(root, path)
        if text is None:
            continue
        found = role_re.findall(text)
        if len(found) != 1:
            failures.append(f"{path}: expected exactly one CONTROL_PLANE_ROLE marker, found {len(found)}")
            continue
        if found[0] != expected_role:
            failures.append(
                f"{path}: CONTROL_PLANE_ROLE marker is {found[0]} but the registry declares {expected_role}"
            )
        if found[0] == "CANONICAL_AUTHORITY":
            canonical_count += 1
            if path != CANONICAL:
                failures.append(f"{path}: only {CANONICAL} may declare CANONICAL_AUTHORITY")
        elif ref_marker not in text:
            failures.append(f"{path}: missing CONTROL_PLANE_AUTHORITY_REF marker to {CANONICAL}")

    if canonical_count != 1:
        failures.append(f"expected exactly one CANONICAL_AUTHORITY surface, found {canonical_count}")


def _check_declarations(root: Path, ctx: dict[str, object], failures: list[str]) -> frozenset[str]:
    """Authority declarations are singular and canonical-only."""
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    max_effort_classes: frozenset[str] = frozenset()

    for name, expected_value in CANONICAL_DECLARATIONS:
        pattern = re.compile(rf"^{re.escape(name)}:\s*(\S+)\s*$", re.MULTILINE)
        sites: list[tuple[str, str]] = []
        for path, _role in surfaces:
            text = read_text(root, path)
            if text is None:
                continue
            for value in pattern.findall(text):
                sites.append((path, value))
        if len(sites) != 1:
            failures.append(
                "{} must be declared exactly once across active doctrine surfaces, found {} ({})".format(
                    name, len(sites), ", ".join(sorted({p for p, _ in sites})) or "none"
                )
            )
            continue
        site_path, site_value = sites[0]
        if site_path != CANONICAL:
            failures.append(f"{name} declared outside the canonical authority, in {site_path}")
        if site_value != expected_value:
            failures.append(f"{name} must be {expected_value} but the declaration says {site_value}")

    pattern = re.compile(r"^MAX_EFFORT_CLASSES:\s*(\S+)\s*$", re.MULTILINE)
    sites = []
    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        for value in pattern.findall(text):
            sites.append((path, value))
    if len(sites) != 1:
        failures.append(f"MAX_EFFORT_CLASSES must be declared exactly once, found {len(sites)}")
    else:
        site_path, site_value = sites[0]
        if site_path != CANONICAL:
            failures.append(f"MAX_EFFORT_CLASSES declared outside the canonical authority, in {site_path}")
        max_effort_classes = frozenset(part.strip() for part in site_value.split(",") if part.strip())
        unknown = sorted(max_effort_classes - ROUTE_CLASSES)
        for cls in unknown:
            failures.append(f"MAX_EFFORT_CLASSES names an unknown class: {cls}")

    return max_effort_classes


def _check_routing(root: Path, ctx: dict[str, object], max_effort_classes: frozenset[str], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]

    # 1) No ROUTE: line may exist outside the canonical routing-matrix block.
    canonical_lines = canonical_text.splitlines()
    span = block_span(canonical_lines, BLOCK_ROUTING_MATRIX)
    if span is None:
        failures.append(f"{CANONICAL}: {BLOCK_ROUTING_MATRIX} block missing or malformed")
        return
    allowed = set(range(span[0], span[1]))

    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        for idx, line in enumerate(text.splitlines()):
            if not line.startswith("ROUTE:"):
                continue
            if path != CANONICAL or idx not in allowed:
                failures.append(
                    f"{path}:{idx + 1}: ROUTE line outside the canonical routing matrix "
                    "(task-family and effort authority is CANONICAL_ONLY)"
                )

    # 2) Parse and check the matrix itself.
    rows = [ln.strip() for ln in canonical_lines[span[0] : span[1]] if ln.strip()]
    if not rows:
        failures.append(f"{CANONICAL}: routing matrix is empty")
        return

    parsed: list[tuple[str, list[str], str, str, str, str]] = []
    for row in rows:
        if not row.startswith("ROUTE:"):
            failures.append(f"{CANONICAL}: non-ROUTE line inside the routing matrix: {row}")
            continue
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        if len(fields) != 6:
            failures.append(f"{CANONICAL}: routing row must have 6 fields, got {len(fields)}: {row}")
            continue
        cls, intents_raw, lane, model_id, effort, mutation = fields
        intents = [i.strip() for i in intents_raw.split(",") if i.strip()]
        parsed.append((cls, intents, lane, model_id, effort, mutation))

        if cls not in ROUTE_CLASSES:
            failures.append(f"{CANONICAL}: unknown routing class {cls}")
        for intent in intents:
            if intent not in TASK_INTENTS:
                failures.append(f"{CANONICAL}: unknown TASK_INTENT {intent} in class {cls}")
        if effort != "-" and effort not in EFFORT_ENUM:
            failures.append(f"{CANONICAL}: class {cls} uses effort {effort} which is not in the effort enum")
        if effort.lower() == "ultra":
            failures.append(
                f"{CANONICAL}: class {cls} stores Ultra as a reasoning effort; Ultra is a capability mode only"
            )
        if mutation not in MUTATION_AUTHORITIES:
            failures.append(f"{CANONICAL}: class {cls} uses unknown mutation authority {mutation}")
        for token in RETIRED_ROUTE_LANE_TOKENS:
            if re.search(rf"\b{re.escape(token)}\b", lane):
                failures.append(f"{CANONICAL}: class {cls} routes to a retired lane: {lane}")

    # 3) T3B must stay an implementation/repair family.
    for cls, intents, _lane, _mid, _effort, _mut in parsed:
        if cls != "T3B":
            continue
        illegal = sorted(set(intents) - T3B_ALLOWED_INTENTS)
        for intent in illegal:
            failures.append(f"{CANONICAL}: T3B absorbs {intent} but T3B accepts IMPLEMENTATION/REPAIR only")

    # 4) The declared max-effort classes and the matrix must agree in both directions.
    matrix_max = frozenset(cls for cls, _i, _l, _m, effort, _mut in parsed if effort == "max")
    if max_effort_classes and matrix_max != max_effort_classes:
        failures.append(
            "MAX_EFFORT_CLASSES declares {} but the routing matrix grants max to {}".format(
                ",".join(sorted(max_effort_classes)) or "none", ",".join(sorted(matrix_max)) or "none"
            )
        )

    # 4a) Coverage: every declared class and every declared intent must actually be routed, and a
    # row must route at least one intent.
    for cls, intents, _lane, _mid, _effort, _mut in parsed:
        if not intents:
            failures.append(f"{CANONICAL}: class {cls} declares an empty intent list, so it routes nothing")
    routed_classes = {cls for cls, *_rest in parsed}
    for cls in sorted(set(ROUTE_CLASSES) - routed_classes):
        failures.append(
            f"{CANONICAL}: class {cls} is declared but has no route; a family with no row is "
            f"unrouted while the gate would otherwise still report PASS"
        )
    routed_intents = {intent for _c, intents, *_rest in parsed for intent in intents}
    for intent in sorted(set(TASK_INTENTS) - routed_intents):
        failures.append(f"{CANONICAL}: TASK_INTENT {intent} is declared but no route accepts it")

    # 4b) FAMILY SEMANTICS: what each family may own, what authority it may carry, and at which
    # efforts. Internal consistency was never legality: every T0 row agreeing on HEAVY_MUTATION is
    # still every T0 row carrying an authority T0 must never have. Each column is checked against
    # the matrix in BOTH directions, so the contract and the matrix cannot drift apart.
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    contract_rows, problems = parse_columns(canonical_text, BLOCK_FAMILY_CONTRACT, 4)
    failures.extend(problems)
    contract: dict[str, tuple[set[str], str, set[str]]] = {}
    if contract_rows is not None:
        for cls, intents_raw, authority, efforts_raw in contract_rows:
            if cls in contract:
                failures.append(f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} declares class {cls} more than once")
            if cls not in ROUTE_CLASSES:
                failures.append(f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} declares unknown class {cls}")
            intents = {i.strip() for i in intents_raw.split(",") if i.strip()}
            for intent in sorted(intents - set(TASK_INTENTS)):
                failures.append(f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} class {cls} owns unknown intent {intent}")
            if authority not in MUTATION_AUTHORITIES:
                failures.append(
                    f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} class {cls} declares unknown mutation authority {authority}"
                )
            efforts = {e.strip() for e in efforts_raw.split(",") if e.strip()}
            for effort in sorted(efforts - set(EFFORT_ENUM) - {"-"}):
                failures.append(f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} class {cls} declares unknown effort {effort}")
            contract[cls] = (intents, authority, efforts)
        for cls in sorted(set(ROUTE_CLASSES) - set(contract)):
            failures.append(f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} does not declare the contract for class {cls}")

        for cls, intents, lane, _mid, effort, mutation in parsed:
            declared = contract.get(cls)
            if declared is None:
                continue
            legal_intents, legal_authority, legal_efforts = declared
            for intent in sorted(set(intents) - legal_intents):
                failures.append(
                    f"{CANONICAL}: class {cls} routes {intent} through {lane}, but {cls} owns only "
                    f"{sorted(legal_intents)}; routing an intent through a family that does not own "
                    f"it creates a second authority for that intent"
                )
            if mutation != legal_authority:
                failures.append(
                    f"{CANONICAL}: class {cls} routes with {mutation} but the canonical mutation "
                    f"authority for {cls} is {legal_authority}; a family agreeing with itself is not "
                    f"the same as a family carrying the authority it is allowed to carry"
                )
            if effort not in legal_efforts:
                failures.append(
                    f"{CANONICAL}: class {cls} routes at effort {effort} but {cls} is legal only at "
                    f"{sorted(legal_efforts)}"
                )

        # The other direction: a declared contract nothing routes is an unreachable claim.
        for cls, (legal_intents, _authority, legal_efforts) in sorted(contract.items()):
            rows_for = [row for row in parsed if row[0] == cls]
            actual_intents = {intent for row in rows_for for intent in row[1]}
            for intent in sorted(legal_intents - actual_intents):
                failures.append(
                    f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} gives {cls} the intent {intent} but no "
                    f"{cls} route accepts it, so the declared ownership is unreachable"
                )
            actual_efforts = {row[4] for row in rows_for}
            for effort in sorted(legal_efforts - actual_efforts):
                failures.append(
                    f"{CANONICAL}: {BLOCK_FAMILY_CONTRACT} gives {cls} the effort {effort} but no "
                    f"{cls} route uses it, so the declared effort set is unreachable"
                )

    # 4b-ii) LANE CAPABILITY: a family can keep its correct authority while the WORK moves to a
    # lane that must never carry it. The lane's identity and its trusted authorities are one fact.
    lane_rows, lane_problems = parse_columns(canonical_text, BLOCK_LANE_CAPABILITY, 3)
    failures.extend(lane_problems)
    if lane_rows is not None:
        lanes: dict[str, tuple[str, set[str]]] = {}
        for lane_name, model_id, authorities_raw in lane_rows:
            if lane_name in lanes:
                failures.append(f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} declares lane {lane_name!r} more than once")
            authorities = {a.strip() for a in authorities_raw.split(",") if a.strip()}
            for authority in sorted(authorities - set(MUTATION_AUTHORITIES)):
                failures.append(
                    f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} lane {lane_name!r} declares unknown "
                    f"mutation authority {authority}"
                )
            lanes[lane_name] = (model_id, authorities)

        for cls, _intents, lane, model_id, _effort, mutation in parsed:
            declared_lane = lanes.get(lane)
            if declared_lane is None:
                failures.append(
                    f"{CANONICAL}: class {cls} routes to lane {lane!r}, which {BLOCK_LANE_CAPABILITY} "
                    f"does not declare; an undeclared lane has no proven identity and no proven capability"
                )
                continue
            declared_model, declared_authorities = declared_lane
            if model_id != declared_model:
                failures.append(
                    f"{CANONICAL}: class {cls} routes lane {lane!r} with model id {model_id!r}, but "
                    f"that lane's canonical identity is {declared_model!r}"
                )
            if mutation not in declared_authorities:
                failures.append(
                    f"{CANONICAL}: class {cls} asks lane {lane!r} to carry {mutation}, but that lane "
                    f"is trusted only with {sorted(declared_authorities)}"
                )

        for lane_name in sorted(set(lanes) - {row[2] for row in parsed}):
            failures.append(
                f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} declares lane {lane_name!r} but no route uses "
                f"it, so the declared capability is unreachable"
            )

    # 4c) One family, one mutation authority - and no two rows that address the same lane at the
    # same effort. A second row for an already-routed (class, lane, model, effort) is either an
    # exact duplicate or a contradiction, and both leave the authority ambiguous.
    authorities: dict[str, set[str]] = {}
    for cls, _intents, _lane, _mid, _effort, mutation in parsed:
        authorities.setdefault(cls, set()).add(mutation)
    for cls, found_authorities in sorted(authorities.items()):
        if len(found_authorities) > 1:
            failures.append(
                f"{CANONICAL}: class {cls} declares more than one mutation authority "
                f"({sorted(found_authorities)}); a family has exactly one, or its authority is ambiguous"
            )
    seen: set[tuple[str, str, str, str]] = set()
    for cls, _intents, lane, model_id, effort, _mut in parsed:
        key = (cls, lane, model_id, effort)
        if key in seen:
            failures.append(
                f"{CANONICAL}: class {cls} routes {lane} at {effort} more than once; a repeated "
                f"(class, lane, model, effort) row is either redundant or a contradiction"
            )
        seen.add(key)

    # 5) Class C and T4 are the SAME set, in both directions.
    #
    # "T4 carries only CLASS_C_CROSS_CONTRACT" was enforced; "only T4 carries
    # CLASS_C_CROSS_CONTRACT" was not. One direction leaves the protected intent free to be
    # attached to an unprotected family, which creates a second, cheaper Class-C authority
    # alongside the real one while every existing check still passes.
    for cls, intents, lane, _mid, effort, mutation in parsed:
        if cls == "T4" or CLASS_C_INTENT not in intents:
            continue
        failures.append(
            f"{CANONICAL}: class {cls} carries {CLASS_C_INTENT} but that intent belongs to the "
            f"protected T4 family alone; routing it through {lane} at {effort} with {mutation} "
            f"would create a parallel Class-C authority"
        )

    # 5a) The protected frontier lane owns T4 outright.
    t4_rows = [row for row in parsed if row[0] == "T4"]
    if not t4_rows:
        failures.append(f"{CANONICAL}: no T4 protected route declared")
    for _cls, intents, lane, model_id, _effort, mutation in t4_rows:
        if lane != FRONTIER_LANE:
            failures.append(
                f"{CANONICAL}: T4 route lane is {lane!r} but the protected frontier lane is exactly "
                f"{FRONTIER_LANE!r}; a label that merely mentions it is not that lane"
            )
        if model_id != FRONTIER_MODEL_ID:
            failures.append(f"{CANONICAL}: T4 route model id is {model_id} but must be {FRONTIER_MODEL_ID}")
        if mutation != "READ_ONLY":
            failures.append(f"{CANONICAL}: T4 route must be READ_ONLY, got {mutation}")
        for intent in intents:
            if intent != CLASS_C_INTENT:
                failures.append(f"{CANONICAL}: T4 route carries non-Class-C intent {intent}")

    t4_efforts = frozenset(effort for _c, _i, _l, _m, effort, _mut in t4_rows)
    if t4_rows and t4_efforts != PROTECTED_FRONTIER_EFFORTS:
        failures.append(
            f"{CANONICAL}: T4 declares efforts {sorted(t4_efforts)} but the protected frontier lane "
            f"runs exactly {sorted(PROTECTED_FRONTIER_EFFORTS)}"
        )

    # 5b) Each read-only reasoning family runs on exactly its legal lanes, and EVERY one of those
    # lanes offers the family's whole effort set - otherwise "prefer the other lane" silently fails
    # at the effort the work actually needs.
    for family, legal in READ_ONLY_REASONING_EFFORTS.items():
        legal_lanes = READ_ONLY_REASONING_LANES[family]
        rows_for = [row for row in parsed if row[0] == family]
        if not rows_for:
            failures.append(f"{CANONICAL}: no {family} route declared")
            continue
        for _cls, _intents, lane, model_id, _effort, _mut in rows_for:
            if lane not in legal_lanes:
                failures.append(f"{CANONICAL}: {family} routes to {lane} but its legal lanes are {sorted(legal_lanes)}")
            elif model_id != legal_lanes[lane]:
                failures.append(
                    f"{CANONICAL}: {family} routes lane {lane} with model id {model_id} but that "
                    f"lane's identity for {family} is {legal_lanes[lane]}"
                )
        routed_lanes = {lane for _c, _i, lane, _m, _e, _mut in rows_for}
        for lane in sorted(set(legal_lanes) - routed_lanes):
            failures.append(
                f"{CANONICAL}: {family} declares lane {lane} as legal but routes no {family} row to "
                f"it, so the declared option does not exist"
            )
        for lane in sorted(routed_lanes & set(legal_lanes)):
            declared = frozenset(effort for _c, _i, row_lane, _m, effort, _mut in rows_for if row_lane == lane)
            if declared != legal:
                failures.append(
                    f"{CANONICAL}: {family} on {lane} declares efforts {sorted(declared)} but its "
                    f"legal set is {sorted(legal)}"
                )

    # 5c) Ordinary review keeps a cross-family option. Independence is a property of HAVING a
    # reviewer that is not the implementer, so the alternative must exist in the matrix itself.
    review_lanes = {lane for cls, _i, lane, _m, _e, _mut in parsed if cls == "T3C"}
    if len(review_lanes) < MIN_REVIEW_LANES:
        failures.append(
            f"{CANONICAL}: T3C routes only {sorted(review_lanes)}; ordinary review needs at least "
            f"{MIN_REVIEW_LANES} lanes so a reviewer that did not implement the work can be chosen"
        )

    # 6) Read-only families never carry mutation authority. The set is DERIVED from the canonical
    # family contract rather than restated here, so a family cannot become read-only in one place
    # and mutating in another.
    read_only_families = {cls for cls, (_i, authority, _e) in contract.items() if authority == "READ_ONLY"}
    for cls, _intents, _lane, _mid, _effort, mutation in parsed:
        if cls in read_only_families and mutation != "READ_ONLY":
            failures.append(f"{CANONICAL}: class {cls} is a read-only family but declares {mutation}")


def _check_fixed_blocks(ctx: dict[str, object], failures: list[str]) -> None:
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    for name, expected in (
        (BLOCK_EFFORT_ENUM, list(EFFORT_ENUM)),
        (BLOCK_PROMPT_FIELDS, list(PROMPT_COMPILER_FIELDS)),
        (BLOCK_EVIDENCE_CLASSES, list(MODEL_EVIDENCE_CLASSES)),
        (BLOCK_WORK_CONTRACT, list(WORK_RETURN_CONTRACT)),
        (BLOCK_CAPACITY_STATES, list(PROVIDER_CAPACITY_STATES)),
        (BLOCK_ROUTING_MODES, list(CAPACITY_ROUTING_MODES)),
        (BLOCK_INTENT_FIRST, list(INTENT_FIRST_ROUTING_RULES)),
    ):
        found = block_lines(canonical_text, name)
        if found is None:
            failures.append(f"{CANONICAL}: {name} block missing or malformed")
            continue
        if found != expected:
            failures.append(f"{CANONICAL}: {name} block must be exactly {expected} in order, got {found}")


def _check_single_prompt_template(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Exactly one top-level prompt template exists, and it lives in the canonical authority."""
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    holders = []
    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        if _begin(BLOCK_PROMPT_FIELDS) in text:
            holders.append(path)
    if holders != [CANONICAL]:
        failures.append(
            "exactly one top-level prompt-compiler field block must exist and it must be in {}; found in {}".format(
                CANONICAL, ", ".join(holders) or "no surface"
            )
        )


def _normalize_ws(text: str) -> str:
    """Collapse runs of whitespace so a required phrase survives markdown line wrapping."""
    return " ".join(text.split())


def _check_required_tokens(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    canonical_flat = _normalize_ws(canonical_text)
    for token in REQUIRED_CANONICAL_TOKENS:
        if _normalize_ws(token) not in canonical_flat:
            failures.append(f"{CANONICAL}: required contract token missing: {token}")

    index_path = "docs/crypto_core/continuity/CONTINUITY_INDEX.md"
    index_text = read_text(root, index_path)
    if index_text is not None:
        for token in REQUIRED_CONTINUITY_INDEX_TOKENS:
            if token not in index_text:
                failures.append(f"{index_path}: required continuity token missing: {token}")

    shim_path = ".github/copilot-instructions.md"
    shim_text = read_text(root, shim_path)
    if shim_text is not None and "INACTIVE_UNAVAILABLE" not in shim_text:
        failures.append(f"{shim_path}: must declare INACTIVE_UNAVAILABLE")


def _check_marker_regions(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        failures.extend(marker_region_failures(path, text.splitlines()))


def volatile_assignment_re(field: str) -> re.Pattern[str]:
    """Match an ASSIGNMENT to a live-state field, but never a mere mention of its name.

    A durable surface may NAME a field to explain it, and may register it with the `` :: ``
    separator. It may not write ``FIELD: value`` or ``FIELD=value``. The negative lookahead after the
    colon is what keeps the registry block itself legal, and optional trailing backticks or asterisks
    let the rule survive ordinary markdown emphasis around the field name.
    """
    return re.compile(r"\b" + re.escape(field) + r"\b[`*]*\s*(?::(?!:)|=)\s*\S", re.IGNORECASE)


def _check_durable_surfaces(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Scan exactly the declared DURABLE_SURFACES set for volatile current state.

    Enforced, and claimed, are exactly four things: a commit or tree hash token, a ``PR #n`` pin, a
    ``main @ hash`` pin, and an assignment to a field registered in ``VOLATILE_STATE_FIELDS``.
    Arbitrary English that conveys current state without any of those forms is NOT detected here and
    is the independent semantic audit's responsibility - see agent_os_v2.md section 15.
    """
    field_patterns = [(field, volatile_assignment_re(field)) for field in ctx["volatile_fields"]]  # type: ignore[union-attr]
    for path in ctx["durable"]:  # type: ignore[union-attr]
        text = read_text(root, path)
        if text is None:
            continue
        for lineno, line in active_lines(text.splitlines()):
            for match in HEX_TOKEN_RE.finditer(line):
                failures.append(f"{path}:{lineno}: volatile commit hash in a durable surface: {match.group(0)}")
            if PR_PIN_RE.search(line):
                failures.append(f"{path}:{lineno}: volatile PR number pinned in a durable surface")
            if OPEN_PR_PIN_RE.search(line):
                failures.append(f"{path}:{lineno}: volatile open-PR count pinned in a durable surface")
            if MAIN_AT_RE.search(line):
                failures.append(f"{path}:{lineno}: volatile main head pinned in a durable surface")
            for field, pattern in field_patterns:
                if pattern.search(line):
                    failures.append(
                        f"{path}:{lineno}: volatile state assigned in a durable surface: {field} "
                        f"(durable doctrine may name a live-state field, never assign it)"
                    )


def _check_model_agnostic(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """A model-agnostic companion may not name a model in its active region."""
    for path in ctx["agnostic"]:  # type: ignore[union-attr]
        text = read_text(root, path)
        if text is None:
            continue
        for lineno, line in active_lines(text.splitlines()):
            lowered = line.lower()
            for token in MODEL_TOKENS_CASE_INSENSITIVE:
                if re.search(rf"\b{re.escape(token)}\b", lowered):
                    failures.append(
                        f"{path}:{lineno}: model identifier '{token}' in a MODEL_AGNOSTIC surface "
                        "(routing authority is CANONICAL_ONLY)"
                    )
            for token in MODEL_TOKENS_CASE_SENSITIVE:
                if re.search(rf"\b{re.escape(token)}\b", line):
                    failures.append(
                        f"{path}:{lineno}: model identifier '{token}' in a MODEL_AGNOSTIC surface "
                        "(routing authority is CANONICAL_ONLY)"
                    )
            if MODEL_FAMILY_RE.search(line):
                failures.append(f"{path}:{lineno}: model family identifier in a MODEL_AGNOSTIC surface")


def _check_prohibited_sizing(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        for lineno, line in active_lines(text.splitlines()):
            for token in PROHIBITED_SIZING_TOKENS:
                if token in line:
                    failures.append(
                        f"{path}:{lineno}: retired PR-sizing heuristic '{token}' "
                        "(PR_SIZING_AUTHORITY is SEMANTIC_CLOSURE_ONLY)"
                    )


EXECUTABLE_SUBORDINATE_PATHS = (
    "scripts/crypto_core/validate_agent_os_v2.py",
    "tests/crypto_core/test_agent_os_v2_contract.py",
)
BLOCK_NEGATIVE_BOUNDARY = "EXECUTABLE_NEGATIVE_BOUNDARY"
EXECUTABLE_ROLE = "EXECUTABLE_SUBORDINATE"


def module_docstring(text: str) -> str | None:
    """The first triple-quoted block of a Python source file, or None."""
    opening = text.find('"""')
    if opening == -1:
        return None
    closing = text.find('"""', opening + 3)
    if closing == -1:
        return None
    return text[opening + 3 : closing]


def _check_executable_subordinates(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Both executables declare a subordinate role, an authority reference and the exact boundary.

    Only the module DOCSTRING is scanned. This module also mentions these marker strings in its own
    code, and scanning the whole file would let it satisfy the check trivially - a presence check
    that cannot fail is not a check.

    This proves the declaration is present. It does NOT and cannot prove that no differently-worded
    self-enforcement claim appears elsewhere in the prose; that is the independent semantic audit's
    responsibility (section 20.1).
    """
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    declared = block_lines(canonical_text, BLOCK_NEGATIVE_BOUNDARY)
    if declared is None or len([ln for ln in declared if ln.strip()]) != 1:
        failures.append(f"{CANONICAL}: {BLOCK_NEGATIVE_BOUNDARY} must declare exactly one boundary sentence")
        return
    boundary = declared[0].strip()

    role_re = re.compile(r"<!--\s*CONTROL_PLANE_ROLE:\s*([A-Z_]+)\s*-->")
    ref_marker = f"<!-- CONTROL_PLANE_AUTHORITY_REF: {CANONICAL} -->"
    for rel in EXECUTABLE_SUBORDINATE_PATHS:
        text = read_text(root, rel)
        if text is None:
            failures.append(f"executable surface missing: {rel}")
            continue
        docstring = module_docstring(text)
        if docstring is None:
            failures.append(f"{rel}: has no module docstring to carry its role declaration")
            continue
        roles = role_re.findall(docstring)
        if len(roles) != 1:
            failures.append(f"{rel}: expected exactly one CONTROL_PLANE_ROLE marker, found {len(roles)}")
        elif roles[0] != EXECUTABLE_ROLE:
            failures.append(f"{rel}: CONTROL_PLANE_ROLE is {roles[0]}, expected {EXECUTABLE_ROLE}")
        if docstring.count(ref_marker) != 1:
            failures.append(f"{rel}: expected exactly one CONTROL_PLANE_AUTHORITY_REF marker to {CANONICAL}")
        if _normalize_ws(boundary) not in _normalize_ws(docstring):
            failures.append(f"{rel}: does not reproduce the canonical {BLOCK_NEGATIVE_BOUNDARY} declaration verbatim")


def _check_host_discovery(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """A host auto-discovery location must be registered or empty - never merely unregistered.

    Registry membership decides AUTHORITY; it does not decide what a host LOADS. An agent, skill or
    prompt file sitting in a conventional discovery directory gets loaded whatever the registry says,
    so "unregistered therefore inert" was false. The allowed set in each declared location is
    currently empty, and this scan claims nothing about host conventions outside that declared list.
    """
    registered = {path for path, _role in ctx["surfaces"]} | set(ctx["artifacts"])  # type: ignore[union-attr]
    for pattern in ctx["host_globs"]:  # type: ignore[union-attr]
        for found in sorted(root.glob(pattern)):
            if not found.is_file():
                continue
            rel = found.relative_to(root).as_posix()
            if rel in registered:
                continue
            failures.append(
                f"host auto-discovery surface present but not registered: {rel} "
                f"(matched {pattern}; a discoverable path must be registered with a safe role or absent)"
            )


def max_effort_is_legal(family_rows: list[str], task_class: str, task_intent: str) -> bool:
    """Is `max` legal for this exact (class, intent) pair, per the canonical per-family table?"""
    for raw_row in family_rows:
        row = raw_row.strip()
        if row.startswith("- "):
            row = row[2:]
        parts = [part.strip() for part in row.split("::")]
        if len(parts) != 3 or parts[0] != task_class:
            continue
        return task_intent in {i.strip() for i in parts[1].split(",") if i.strip()}
    return False


def _check_effort_family_legality(
    root: Path, ctx: dict[str, object], max_effort_classes: frozenset[str], failures: list[str]
) -> None:
    """`max` legality is per family, and the table must agree with the routing matrix."""
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    rows: list[str] = list(ctx["max_family"])  # type: ignore[arg-type]

    parsed: dict[str, set[str]] = {}
    for row in rows:
        parts = [part.strip() for part in row.split("::")]
        if len(parts) != 3 or not parts[2]:
            failures.append(f"{CANONICAL}: malformed {BLOCK_MAX_FAMILY} row (need CLASS :: INTENTS :: trigger): {row}")
            continue
        task_class, intents_raw, _trigger = parts
        if task_class in parsed:
            failures.append(f"{CANONICAL}: duplicate {BLOCK_MAX_FAMILY} row for {task_class}")
        parsed[task_class] = {i.strip() for i in intents_raw.split(",") if i.strip()}

    if max_effort_classes and set(parsed) != set(max_effort_classes):
        failures.append(
            f"{CANONICAL}: MAX_EFFORT_CLASSES declares "
            f"{','.join(sorted(max_effort_classes)) or 'none'} but {BLOCK_MAX_FAMILY} covers "
            f"{','.join(sorted(parsed)) or 'none'}"
        )

    # Each family may only reach max through an intent it actually routes.
    routed: dict[str, set[str]] = {}
    for row in block_lines(canonical_text, BLOCK_ROUTING_MATRIX) or []:
        if not row.startswith("ROUTE:"):
            continue
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        if len(fields) != 6:
            continue
        routed.setdefault(fields[0], set()).update(i.strip() for i in fields[1].split(",") if i.strip())

    for task_class, intents in parsed.items():
        illegal = sorted(intents - routed.get(task_class, set()))
        for intent in illegal:
            failures.append(
                f"{CANONICAL}: {BLOCK_MAX_FAMILY} lets {task_class} reach max through {intent}, "
                f"which {task_class} does not route in section 3"
            )

    # The mutation-only family stays mutation-only even at max.
    illegal_t3b = sorted(parsed.get("T3B", set()) - T3B_ALLOWED_INTENTS)
    for intent in illegal_t3b:
        failures.append(f"{CANONICAL}: T3B may not reach max through {intent}; T3B is IMPLEMENTATION/REPAIR only")

    # A one-family restriction must never be restated as a restriction on the effort itself.
    for path, _role in ctx["surfaces"]:  # type: ignore[union-attr]
        text = read_text(root, path)
        if text is None:
            continue
        for lineno, line in active_lines(text.splitlines()):
            for token in PROHIBITED_GLOBAL_MAX_TOKENS:
                if token.rstrip("\n") in line:
                    failures.append(
                        f"{path}:{lineno}: max restricted globally to one family ({token.strip()!r}); "
                        f"legality is per family - see {BLOCK_MAX_FAMILY}"
                    )


def _check_capacity_contract(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Provider capacity is a routing input, never a durable pin and never an enforced ratio.

    Capacity stays out of durable doctrine because its fields are registered volatile-state fields,
    which the durable scan already rejects on assignment. What this check adds is the other half: the
    vocabulary must admit UNKNOWN rather than force a fabricated reading, the continuity and stop
    modes must exist, and a provider ratio may be stated as a planning SLO but never encoded as a
    constraint an agent could be routed to satisfy.
    """
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    for path, _role in surfaces:
        text = read_text(root, path)
        if text is None:
            continue
        for lineno, line in active_lines(text.splitlines()):
            for token in PROHIBITED_RATIO_TOKENS:
                if token in line:
                    failures.append(
                        f"{path}:{lineno}: provider ratio encoded as an enforced constraint: {token} "
                        f"(a ratio is a planning SLO only, never a routing or correctness invariant)"
                    )

    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    states = block_lines(canonical_text, BLOCK_CAPACITY_STATES) or []
    if "UNKNOWN" not in states:
        failures.append(f"{CANONICAL}: provider capacity must admit UNKNOWN rather than a fabricated value")
    modes = block_lines(canonical_text, BLOCK_ROUTING_MODES) or []
    for required_mode in ("CLAUDE_CONTINUITY", "OPENAI_CONTINUITY", "BOTH_EXHAUSTED_STOP"):
        if required_mode not in modes:
            failures.append(f"{CANONICAL}: capacity routing mode missing: {required_mode}")

    volatile_fields = {f.upper() for f in ctx["volatile_fields"]}  # type: ignore[union-attr]
    for capacity_field in ("OPENAI_AGENTIC_CAPACITY", "CLAUDE_CAPACITY", "CAPACITY_ROUTING_MODE"):
        if capacity_field not in volatile_fields:
            failures.append(
                f"{CANONICAL}: {capacity_field} must be registered in {BLOCK_VOLATILE_FIELDS} so a "
                f"capacity reading can never be pinned into durable doctrine"
            )


# ---------------------------------------------------------------------------
# CANONICAL_TYPED_OPERATIONAL_GRAMMAR_V1
# ---------------------------------------------------------------------------
#
# ONE executable authority for the operational manifest. The previous design kept three
# overlapping authorities - JSON Schema semantics, a hand-written subset interpreter of
# that schema, and direct field validation - and the interpreter silently ignored the
# schema's own `allOf`/`if`/`then`/`else` proof-pair branches while claiming to enforce it.
# A subset interpreter cannot fail safely on a language it only partly implements: an
# unimplemented keyword is indistinguishable from an absent one.
#
# So no code here reads a JSON Schema keyword to decide whether an instance is valid. The
# grammar below IS the shape authority; `docs/crypto_core/continuity/state_manifest.schema.json`
# is GENERATED from it and is a published specification artifact, never a runtime authority.
#
# Two text grammars, because two different jobs were previously asked of one predicate.
#
# TEXT_EVIDENCE_LNPS_V1 is for FREE-FORM OBSERVATIONAL text - a value copied from somewhere
# else and stored verbatim, in whatever script the source used. It holds when at least one code
# point has a Unicode general category whose MAJOR class is L, N, P or S; a string drawn
# entirely from M, Z and C carries none. The claim is deliberately weak and is stated exactly:
# the value is a string and is not composed solely of marks, separators and other-category code
# points. It does NOT prove the value is meaningful, true, current or well-sourced, and it
# cannot: `U+3164 HANGUL FILLER` is category Lo and `U+2800 BRAILLE PATTERN BLANK` is category
# So, so both legitimately satisfy it while conveying nothing to a reader. That is not a defect
# in the rule - it is the limit of what any general Unicode category test can decide.
#
# The classification comes from the `unicodedata` database COMPILED INTO THE RUNNING PYTHON, so
# a code point assigned in a newer Unicode version than this interpreter ships is classified by
# this interpreter's table, not by the newer standard. No claim is made about future assignments.
#
# OPERATIONAL_TEXT_V1 is for LOAD-BEARING OPERATIONAL values - the ones a human acts on or the
# control plane compares: a next action, a gate name, an evidence key, a blocker id, a model
# identity. Those are written in this project's operational language, which is ASCII, so the
# grammar is the bounded, positive one the control plane actually uses: at least one ASCII
# letter or digit. That is a LEXICAL claim only - it proves the value is written in the
# operational character set, never that the action is correct, current or achievable. Filler
# code points carry no ASCII alphanumeric and are therefore rejected from these fields without
# any list of forbidden characters existing anywhere.

TEXT_PAYLOAD_MAJOR_CLASSES = frozenset({"L", "N", "P", "S"})
OPERATIONAL_TOKEN_RE = re.compile(r"[A-Za-z0-9]")
SCHEMA_OPERATIONAL_PATTERN = "[A-Za-z0-9]"

HASH_IDENTIFIER_RE = re.compile(r"\A[0-9a-fA-F]{40}\Z")
SCHEMA_HASH_PATTERN = "^[0-9a-fA-F]{40}$"

# Bounded, project-scoped identifier grammars. These are deliberately NOT complete
# implementations of GitHub naming or of `git check-ref-format`; they are the syntax this
# control plane actually compares against `gh` and `git` output, and they say so.
REPO_SEGMENT_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")
BRANCH_SEGMENT_RE = re.compile(r"\A[A-Za-z0-9._-]+\Z")

VALUE_CLASSES = (
    "TEXT_EVIDENCE",
    "OPERATIONAL_TEXT",
    "TOKEN_REPO",
    "TOKEN_BRANCH",
    "HASH_IDENTIFIER",
    "NONNEGATIVE_INT",
    "POSITIVE_INT",
    "NORMALIZED_ENUM",
    "STRUCTURED_LIST",
)

EVIDENCE_STATUS = ("PROVEN", "UNKNOWN")
PR_STATES = ("OPEN", "CLOSED", "MERGED", "DRAFT")
CI_STATES = ("GREEN", "FAILING", "PENDING", "NO_CHECKS")
CAPACITY_STATES = ("NORMAL", "CONSERVE", "CRITICAL", "EXHAUSTED")
ROUTING_MODES = (
    "QUALITY_OPTIMAL",
    "CLAUDE_FIRST_CONSERVATION",
    "OPENAI_FIRST_CONSERVATION",
    "CLAUDE_CONTINUITY",
    "OPENAI_CONTINUITY",
    "BOTH_EXHAUSTED_STOP",
)
GATE_RESULTS = ("PASS", "FAIL", "UNKNOWN")
BLOCKER_SEVERITIES = ("P1", "P2", "P3")
BLOCKER_STATES = ("OPEN", "REPAIRED_PENDING_REAUDIT", "CLOSED", "FIXED_POINT_NOT_REACHED")
EFFORT_VALUES = ("low", "medium", "high", "xhigh", "max")
THINKING_STATES = ("ENABLED", "DISABLED", "UNKNOWN")


def carries_text_payload(value: str) -> bool:
    """True when at least one code point is a Letter, Number, Punctuation or Symbol."""
    return any(unicodedata.category(ch)[0] in TEXT_PAYLOAD_MAJOR_CLASSES for ch in value)


def text_evidence_failures(value: object) -> list[str]:
    """Free-form observational text. See the TEXT_EVIDENCE_LNPS_V1 note for the exact claim."""
    if not isinstance(value, str):
        return ["must be a string"]
    if not carries_text_payload(value):
        return ["carries no token payload (only marks, separators or other-category code points)"]
    return []


def operational_text_failures(value: object) -> list[str]:
    """Load-bearing operational text: written in the operational character set, ASCII.

    The rule is positive and bounded, so a value carrying no ASCII alphanumeric is rejected without
    any forbidden code point being named. See the grammar note above for what this does NOT prove.
    """
    if not isinstance(value, str):
        return ["must be a string"]
    if not OPERATIONAL_TOKEN_RE.search(value):
        return [
            "carries no operational token (a load-bearing value must contain at least one ASCII "
            "letter or digit; filler code points alone are not an action, a name or an identity)"
        ]
    return []


def repo_identifier_failures(value: object) -> list[str]:
    """`owner/name`, each segment in the bounded token set this control plane compares."""
    reasons = text_evidence_failures(value)
    if reasons:
        return reasons
    segments = value.split("/")
    if len(segments) != 2:
        return ["must be exactly owner/name"]
    for label, segment in zip(("owner", "name"), segments, strict=True):
        if not REPO_SEGMENT_RE.match(segment):
            return [f"{label} segment is outside the supported repository token set"]
    return []


def branch_identifier_failures(value: object) -> list[str]:
    """Bounded project branch grammar - NOT a complete `git check-ref-format` implementation."""
    reasons = text_evidence_failures(value)
    if reasons:
        return reasons
    if value.startswith("/") or value.endswith("/"):
        return ["must not start or end with '/'"]
    if "//" in value:
        return ["must not contain an empty path segment"]
    if ".." in value:
        return ["must not contain '..'"]
    if "@{" in value:
        return ["must not contain '@{'"]
    if value.endswith(".") or value.endswith(".lock"):
        return ["must not end with '.' or '.lock'"]
    for segment in value.split("/"):
        if not BRANCH_SEGMENT_RE.match(segment):
            return ["contains a segment outside the supported branch token set"]
    return []


# --- grammar nodes -----------------------------------------------------------------------
#
# A node is a small dict with a "kind". Every kind is handled by both the checker and the
# schema emitter; a kind either exists in both or in neither, which is what stops the two
# from drifting.


def _text(description: str = "") -> dict:
    """FREE-FORM observational text. Use `_op` for anything load-bearing."""
    return {"kind": "TEXT_EVIDENCE", "description": description}


def _op(description: str = "") -> dict:
    """LOAD-BEARING operational text: an action, a name, a key, an identity."""
    return {"kind": "OPERATIONAL_TEXT", "description": description}


def _repo(description: str = "") -> dict:
    return {"kind": "TOKEN_REPO", "description": description}


def _branch(description: str = "") -> dict:
    return {"kind": "TOKEN_BRANCH", "description": description}


def _hash(description: str = "") -> dict:
    return {"kind": "HASH_IDENTIFIER", "description": description}


def _int(minimum: int, description: str = "") -> dict:
    kind = "NONNEGATIVE_INT" if minimum == 0 else "POSITIVE_INT"
    return {"kind": kind, "minimum": minimum, "description": description}


def _enum(members: tuple[str, ...], description: str = "") -> dict:
    return {"kind": "NORMALIZED_ENUM", "members": members, "description": description}


def _const(value: object, description: str = "") -> dict:
    return {"kind": "CONST", "value": value, "description": description}


def _list(item: dict, description: str = "") -> dict:
    return {"kind": "STRUCTURED_LIST", "item": item, "description": description}


def _object(fields: dict, required: tuple[str, ...], description: str = "") -> dict:
    return {"kind": "OBJECT", "fields": fields, "required": required, "description": description}


MANIFEST_SCHEMA_ID = "https://crypto-core.local/schemas/state_manifest_v1.json"
MANIFEST_SCHEMA_DRAFT = "https://json-schema.org/draft/2020-12/schema"
MANIFEST_TITLE = "STATE_MANIFEST_V1"
MANIFEST_DESCRIPTION = (
    "Ephemeral per-session state manifest for crypto_core (CONTEXT_CONTINUITY_PROTOCOL_V2 layer 3, "
    "docs/crypto_core/agent_os_v2.md section 15). Compiled from live proof at the start of a session. "
    "NEVER committed as durable doctrine and never read as current truth by a later session. Every "
    "field listed in the PROOF_PAIRED_MANIFEST_FIELDS registry (agent_os_v2.md section 20) is "
    "proof-paired: the value is present and MEANINGFUL only when its _evidence companion says PROVEN, "
    "and is exactly null when the companion says UNKNOWN. A missing value, a missing companion, a "
    "value with UNKNOWN, null with PROVEN, or a populated-but-payload-empty value are all invalid. "
    "Fields NOT in that registry are static or descriptive metadata and are deliberately not paired. "
    "UNKNOWN is a first-class, expected outcome; it is never replaced by a plausible guess. "
    "THIS FILE IS GENERATED from the canonical typed operational grammar in "
    "scripts/crypto_core/validate_agent_os_v2.py and is a published SPECIFICATION artifact: it is "
    "never executed as a runtime validation authority, and hand edits are rejected because the "
    "committed object must equal the generated object."
)

# Fields that are proof-paired: value node plus a `<field>_evidence` companion.
PROOF_PAIRED_GRAMMAR: dict[str, dict] = {
    "branch": _branch("Current checked-out branch."),
    "base_sha": _hash("Base commit this work was cut from."),
    "base_tree": _hash("Tree of the base commit."),
    "head_sha": _hash("Current head commit."),
    "head_tree": _hash("Tree of the current head commit."),
    "pr_number": _int(1, "Current pull-request number."),
    "pr_state": _enum(PR_STATES, "Current PR state."),
    "open_pr_count": _int(0, "Live open-PR count for the repository."),
    "ci_state": _enum(
        CI_STATES, "Terminal CI verdict. PENDING and NO_CHECKS both mean NOT_READY; only GREEN is a pass."
    ),
    "review_threads_unresolved": _int(0, "Count of currently unresolved review threads."),
    "completed_gates": _list(
        _object(
            {
                "gate": _op(),
                "evidence_key": _op(
                    "VALIDATION_BUDGET reuse key: head/tree + relevant path set + command/config + "
                    "environment/toolchain + evidence id. A gate may be reused only while this key is "
                    "unchanged."
                ),
                "result": _enum(GATE_RESULTS),
            },
            required=("gate", "evidence_key", "result"),
        ),
        "Deterministic gates already proven at the current evidence key. An empty array means 'proven "
        "that none are complete', which is why it is proof-paired rather than merely optional.",
    ),
    "blockers": _list(
        _object(
            {
                "id": _op(
                    "Stable blocker identity. It survives renaming and re-phasing; renaming a blocker "
                    "never resets repair_count (agent_os_v2.md section 13)."
                ),
                "severity": _enum(BLOCKER_SEVERITIES),
                "state": _enum(BLOCKER_STATES),
                "repair_count": _int(0),
            },
            required=("id", "severity", "state", "repair_count"),
        ),
        "Current blocker set. An empty array means 'proven that none are open', not 'not checked'.",
    ),
    "openai_agentic_capacity": _enum(
        CAPACITY_STATES,
        "Shared OpenAI agentic pool state (Codex, the frontier audit lane and Work all draw on it). The "
        "conceptual UNKNOWN state is encoded structurally as null plus UNKNOWN evidence, never as a "
        "literal string, so a capacity fact has exactly one representation.",
    ),
    "claude_capacity": _enum(
        CAPACITY_STATES, "Claude capacity state. UNKNOWN is encoded as null plus UNKNOWN evidence."
    ),
    "capacity_routing_mode": _enum(
        ROUTING_MODES,
        "Routing mode selected by USAGE_AWARE_CAPACITY_ROUTER_V1 (agent_os_v2.md section 10.2). It must "
        "be consistent with the two proven capacity values; an unproven capacity leaves this null.",
    ),
    "next_safe_action": _op(
        "Exactly one concrete next action. It is a live decision, not static metadata, so it is "
        "proof-paired: an action nobody has proven is UNKNOWN rather than a plausible suggestion."
    ),
}

MODEL_RUNTIME_GRAMMAR = _object(
    {
        "model_id": _op(),
        "model_requested": _op(),
        "model_actual": _op(),
        "model_evidence_source": _enum(MODEL_EVIDENCE_CLASSES),
        "requested_effort": _enum(EFFORT_VALUES),
        "observed_effort": _enum(EFFORT_VALUES),
        "effort_evidence_source": _enum(MODEL_EVIDENCE_CLASSES),
        "thinking_actual": _enum(THINKING_STATES),
        "capability_mode": _op(),
        "host_setting_raw": _text(),
        "environment": _op(),
        "client_version": _op(),
        "model_fallback": _op(),
    },
    required=(
        "model_id",
        "model_requested",
        "model_actual",
        "model_evidence_source",
        "requested_effort",
        "observed_effort",
        "effort_evidence_source",
        "thinking_actual",
        "capability_mode",
        "host_setting_raw",
        "environment",
        "client_version",
        "model_fallback",
    ),
    description=(
        "Runtime-proof block (agent_os_v2.md section 4). ALWAYS present, because a manifest that omits "
        "it entirely could silently satisfy a task claiming runtime proof. A host that exposes no "
        "runtime metadata says so with an UNKNOWN evidence source and null observations - absence is "
        "never the same statement as UNKNOWN. The block is DIMENSIONAL: model identity, effort and "
        "thinking are observed by different mechanisms and are known independently, so each carries "
        "its own evidence and a contradiction in one never erases valid evidence from another. A host "
        "that reports its model but exposes no effort setting records RUNTIME_TELEMETRY identity "
        "alongside UNKNOWN effort - truthfully, and without inventing telemetry. Within each "
        "dimension the class constrains what may be populated: RUNTIME_TELEMETRY requires a "
        "meaningful observation; USER_ATTESTED_UI_SELECTION requires the attested value in THAT "
        "dimension's own observation field and stays labelled an attestation, because one host "
        "selector string cannot attest two independent dimensions - host_setting_raw is verbatim "
        "context, never a fallback proof; CONTRADICTED is explicit contradictory "
        "runtime proof, so it records what actually ran or what effort actually applied; "
        "CONFIGURATION_EVIDENCE_ONLY and UNKNOWN prove no execution and leave that dimension's "
        "observation null. thinking_actual is its own dimension with an explicit UNKNOWN. Ultra is "
        "recorded in capability_mode ONLY and is never written into an effort field, and "
        "host_setting_raw stores the operator UI choice verbatim without inventing an API mapping."
    ),
)

AUTHORIZATION_GRAMMAR = _object(
    {
        "mutation_scope": _op("Exact authorized mutation scope, or NONE."),
        "merge_authorized": _const(
            False,
            "A manifest never records merge authority. MERGE_AUTHORITY_SOURCE is HUMAN_ONLY_PER_PR and "
            "lives only in docs/crypto_core/agent_os_v2.md section 2.1; an authorization is granted per "
            "PR and per head by the human at the moment of merge, and is never carried in durable or "
            "ephemeral state.",
        ),
        "notes": _text(),
    },
    required=("mutation_scope", "merge_authorized"),
)


def _manifest_fields() -> tuple[dict, tuple[str, ...]]:
    """The whole manifest: static metadata, every proof pair, and the two nested blocks."""
    fields: dict[str, dict] = {
        "$comment": _text(
            "Optional documentation field. A committed fixture that is illustrative rather than real "
            "state MUST declare EXAMPLE_ONLY here."
        ),
        "schema": _const(MANIFEST_TITLE),
        "repo": _repo("owner/name of the repository."),
        "compiled_at_evidence": _op(
            "How this manifest was compiled, for example the exact git and gh commands run. Free text, "
            "but it must describe real executed proof, never an assumption."
        ),
        "task_boundary": _op("The SEMANTIC_BOUNDARY of the work this session is authorized to do."),
    }
    required = ["schema", "repo", "compiled_at_evidence", "task_boundary"]

    for field, node in PROOF_PAIRED_GRAMMAR.items():
        fields[field] = node
        fields[f"{field}_evidence"] = _enum(EVIDENCE_STATUS)
        required.extend((field, f"{field}_evidence"))

    fields["invalidations"] = _list(
        _op(),
        "Facts that stopped being true during this session and must not be reused. This is a session "
        "narrative rather than an external fact, so it is deliberately NOT proof-paired: pairing it "
        "would be ceremony, not proof.",
    )
    fields["model_runtime"] = MODEL_RUNTIME_GRAMMAR
    fields["authorization"] = AUTHORIZATION_GRAMMAR
    required.extend(("model_runtime", "authorization"))
    return fields, tuple(sorted(required))


MANIFEST_FIELDS, MANIFEST_REQUIRED = _manifest_fields()
MANIFEST_GRAMMAR = _object(MANIFEST_FIELDS, required=MANIFEST_REQUIRED, description=MANIFEST_DESCRIPTION)

# Fields whose value may be exactly null. A proof pair's value is nullable (null + UNKNOWN); every
# non-required nested runtime/authorization field is nullable so a host can say "not exposed".
NULLABLE_FIELDS = frozenset(PROOF_PAIRED_GRAMMAR) | {
    "model_id",
    "model_requested",
    "model_actual",
    "requested_effort",
    "observed_effort",
    "capability_mode",
    "host_setting_raw",
    "environment",
    "client_version",
    "model_fallback",
    "notes",
}


def _node_failures(path: str, value: object, node: dict, nullable: bool) -> list[str]:
    """TOTAL. Any JSON value against any grammar node yields reasons, never an exception."""
    if value is None:
        return [] if nullable else [f"{path}: must not be null"]

    kind = node["kind"]
    if kind == "TEXT_EVIDENCE":
        return [f"{path}: {reason}" for reason in text_evidence_failures(value)]
    if kind == "OPERATIONAL_TEXT":
        return [f"{path}: {reason}" for reason in operational_text_failures(value)]
    if kind == "TOKEN_REPO":
        return [f"{path}: {reason}" for reason in repo_identifier_failures(value)]
    if kind == "TOKEN_BRANCH":
        return [f"{path}: {reason}" for reason in branch_identifier_failures(value)]
    if kind == "HASH_IDENTIFIER":
        if not isinstance(value, str):
            return [f"{path}: must be a string"]
        if not HASH_IDENTIFIER_RE.match(value):
            return [f"{path}: is not a 40-character hexadecimal object id"]
        return []
    if kind in ("NONNEGATIVE_INT", "POSITIVE_INT"):
        if isinstance(value, bool) or not isinstance(value, int):
            return [f"{path}: must be an integer"]
        if value < node["minimum"]:
            return [f"{path}: must be >= {node['minimum']}"]
        return []
    if kind == "NORMALIZED_ENUM":
        if not isinstance(value, str) or value not in node["members"]:
            return [f"{path}: is not one of {list(node['members'])}"]
        return []
    if kind == "CONST":
        return [] if value == node["value"] else [f"{path}: must be {node['value']!r}"]
    if kind == "STRUCTURED_LIST":
        if not isinstance(value, list):
            return [f"{path}: must be an array"]
        # An empty array is a legitimate, meaningful PROVEN value: zero blockers is a fact.
        reasons: list[str] = []
        for index, element in enumerate(value):
            reasons.extend(_node_failures(f"{path}[{index}]", element, node["item"], nullable=False))
        return reasons
    if kind == "OBJECT":
        if not isinstance(value, dict):
            return [f"{path}: must be an object"]
        fields = node["fields"]
        reasons = []
        for key in node["required"]:
            if key not in value:
                reasons.append(f"{path}: missing required field {key!r}")
        for key in value:
            if key not in fields:
                reasons.append(f"{path}: carries unknown field {key!r}")
        for key, sub in fields.items():
            if key in value:
                child = f"{path}.{key}" if path else key
                reasons.extend(_node_failures(child, value[key], sub, key in NULLABLE_FIELDS))
        return reasons
    return [f"{path}: grammar node kind {kind!r} has no checker"]


def manifest_grammar_failures(label: str, instance: object) -> list[str]:
    """The SHAPE half of the operational gate, from the canonical grammar alone."""
    return _node_failures(label, instance, MANIFEST_GRAMMAR, nullable=False)


# --- schema emission ---------------------------------------------------------------------


def _schema_for(node: dict, nullable: bool) -> dict:
    """Render one grammar node as JSON Schema. Every kind the checker handles is handled here."""
    kind = node["kind"]
    if kind in ("TEXT_EVIDENCE", "TOKEN_REPO", "TOKEN_BRANCH"):
        body: dict = {"type": "string", "minLength": 1}
    elif kind == "OPERATIONAL_TEXT":
        body = {"type": "string", "pattern": SCHEMA_OPERATIONAL_PATTERN}
    elif kind == "HASH_IDENTIFIER":
        body = {"type": "string", "pattern": SCHEMA_HASH_PATTERN}
    elif kind in ("NONNEGATIVE_INT", "POSITIVE_INT"):
        body = {"type": "integer", "minimum": node["minimum"]}
    elif kind == "NORMALIZED_ENUM":
        body = {"type": "string", "enum": list(node["members"])}
    elif kind == "CONST":
        body = {"const": node["value"]}
    elif kind == "STRUCTURED_LIST":
        body = {"type": "array", "items": _schema_for(node["item"], nullable=False)}
    elif kind == "OBJECT":
        body = {
            "type": "object",
            "additionalProperties": False,
            "required": list(node["required"]),
            "properties": {key: _schema_for(sub, key in NULLABLE_FIELDS) for key, sub in node["fields"].items()},
        }
    else:  # pragma: no cover - defended by the kind-coverage contract test
        raise ValueError(f"no schema rendering for grammar node kind {kind!r}")

    rendered = {"anyOf": [body, {"type": "null"}]} if nullable else body
    if node.get("description"):
        rendered = dict(rendered)
        rendered["description"] = node["description"]
    return rendered


def _reject_json_constant(name: str) -> object:  # pragma: no cover - defended by test
    raise ValueError(f"{name} is not valid JSON for a specification artifact")


def canonical_json(value: object) -> str:
    """One canonical text for one JSON value. TYPE-STRICT by construction.

    Python's `==` conflates `False` with `0` and `True` with `1`, so `{"minimum": 0}` and
    `{"minimum": false}` compare EQUAL as dicts while being different JSON schemas - a hand edit
    changing a bound into a boolean would have been accepted as "equal to generated". Comparing
    the serialized text instead keeps the JSON type: `0` and `false` are different characters.
    `allow_nan=False` rejects NaN and Infinity, which are not JSON at all.
    """
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


def emit_manifest_schema() -> dict:
    """Render the published specification from the grammar. Deterministic and offline."""
    schema = {
        "$schema": MANIFEST_SCHEMA_DRAFT,
        "$id": MANIFEST_SCHEMA_ID,
        "title": MANIFEST_TITLE,
        "description": MANIFEST_DESCRIPTION,
        "type": "object",
        "additionalProperties": False,
        "required": list(MANIFEST_REQUIRED),
        "properties": {key: _schema_for(node, key in NULLABLE_FIELDS) for key, node in MANIFEST_FIELDS.items()},
        "allOf": [],
    }
    for field, node in PROOF_PAIRED_GRAMMAR.items():
        evidence = f"{field}_evidence"
        schema["allOf"].append(
            {
                "if": {"required": [evidence], "properties": {evidence: {"const": "PROVEN"}}},
                "then": {"required": [field], "properties": {field: _schema_for(node, nullable=False)}},
                "else": {"required": [field], "properties": {field: {"type": "null"}}},
            }
        )
    return schema


# --- cross-field semantics ---------------------------------------------------------------
#
# The grammar owns SHAPE. This owns RELATIONS: the facts a per-field check cannot see.


def proof_pair_failures(label: str, instance: dict, value_field: str, evidence_field: str) -> list[str]:
    """Prove one PROVEN/UNKNOWN proof pair.

    Valid:   a value with PROVEN, or exactly null with UNKNOWN.
    Invalid: a value with UNKNOWN, null with PROVEN, or a missing member of the pair.
    Whether a PROVEN value is well-formed is the grammar's job, not this one's.
    """
    failures: list[str] = []
    if value_field not in instance:
        failures.append(f"{label}: {value_field} is missing")
    if evidence_field not in instance:
        failures.append(f"{label}: {evidence_field} is missing")
    if failures:
        return failures

    value = instance[value_field]
    evidence = instance[evidence_field]
    if evidence == "PROVEN":
        if value is None:
            failures.append(f"{label}: {value_field} is null while {evidence_field} says PROVEN")
    elif evidence == "UNKNOWN":
        if value is not None:
            failures.append(f"{label}: {value_field} carries a value while {evidence_field} says UNKNOWN")
    else:
        failures.append(f"{label}: {evidence_field} must be PROVEN or UNKNOWN, got {evidence!r}")
    return failures


def _is_operational_observation(value: object) -> bool:
    """A recorded identity must be an operational token, not merely non-null."""
    return value is not None and not operational_text_failures(value)


def _is_effort_observation(value: object) -> bool:
    """A recorded effort must be a member of the effort enum, not merely non-null."""
    return value in EFFORT_VALUES


def manifest_relation_failures(label: str, instance: object) -> list[str]:
    """Cross-field semantics. TOTAL: any JSON value yields reasons, never an exception."""
    if not isinstance(instance, dict):
        return [f"{label}: a manifest must be a JSON object"]

    failures: list[str] = []
    for field in PROOF_PAIRED_GRAMMAR:
        failures.extend(proof_pair_failures(label, instance, field, f"{field}_evidence"))

    # --- runtime proof ----------------------------------------------------------------------
    runtime = instance.get("model_runtime")
    if not isinstance(runtime, dict):
        failures.append(
            f"{label}: model_runtime is missing; a manifest that participates in routing or audit "
            f"must carry a runtime-proof block with an explicit evidence class"
        )
    else:
        # Each dimension is judged on its OWN evidence. Identity and effort are observed by
        # different mechanisms - a host can report the model while exposing no effort setting at
        # all - so collapsing them into one evidence state forced at least one of them to be a lie.
        for dimension, source_field, observation_field, meaningful in (
            ("model identity", "model_evidence_source", "model_actual", _is_operational_observation),
            ("effort", "effort_evidence_source", "observed_effort", _is_effort_observation),
        ):
            source = runtime.get(source_field)
            observation = runtime.get(observation_field)
            if source not in MODEL_EVIDENCE_CLASSES:
                failures.append(
                    f"{label}: {source_field} must be one of {list(MODEL_EVIDENCE_CLASSES)}, got {source!r}"
                )
            elif source == "RUNTIME_TELEMETRY":
                if not meaningful(observation):
                    failures.append(
                        f"{label}: RUNTIME_TELEMETRY claims {dimension} was observed but "
                        f"{observation_field} carries no observation"
                    )
            elif source == "USER_ATTESTED_UI_SELECTION":
                if not meaningful(observation):
                    failures.append(
                        f"{label}: USER_ATTESTED_UI_SELECTION must record the attested {dimension} in "
                        f"{observation_field}; host_setting_raw is verbatim context for one host "
                        f"selector and cannot attest two independent dimensions at once"
                    )
            elif source == "CONTRADICTED":
                # CONTRADICTED is explicit contradictory runtime PROOF: something WAS observed, and
                # it was not what was requested. Forcing the observation to null would make the
                # manifest unable to record the very value that triggered the stop.
                if not meaningful(observation):
                    failures.append(
                        f"{label}: CONTRADICTED means a conflicting {dimension} was observed, so "
                        f"{observation_field} must record what actually applied"
                    )
            else:
                # CONFIGURATION_EVIDENCE_ONLY and UNKNOWN prove no observation in THIS dimension.
                if observation is not None:
                    failures.append(f"{label}: {source} must not populate {observation_field} as a proven {dimension}")

        thinking = runtime.get("thinking_actual")
        if thinking not in THINKING_STATES:
            failures.append(f"{label}: thinking_actual must be one of {list(THINKING_STATES)}, got {thinking!r}")

    # --- provider capacity ------------------------------------------------------------------
    openai_capacity = instance.get("openai_agentic_capacity")
    claude_capacity = instance.get("claude_capacity")
    mode = instance.get("capacity_routing_mode")

    if not all(v is None or isinstance(v, str) for v in (openai_capacity, claude_capacity, mode)):
        failures.append(f"{label}: capacity fields must be strings or null before a routing mode can be judged")
    elif mode is None:
        pass
    elif openai_capacity is None or claude_capacity is None:
        failures.append(
            f"{label}: capacity_routing_mode {mode!r} was selected while a provider capacity is "
            f"UNKNOWN; an unproven capacity must leave the routing mode null, never guess a mode"
        )
    else:
        requirement = {
            "CLAUDE_CONTINUITY": (openai_capacity == "EXHAUSTED" and claude_capacity in CAPACITY_AVAILABLE),
            "OPENAI_CONTINUITY": (claude_capacity == "EXHAUSTED" and openai_capacity in CAPACITY_AVAILABLE),
            "BOTH_EXHAUSTED_STOP": (openai_capacity == "EXHAUSTED" and claude_capacity == "EXHAUSTED"),
            "QUALITY_OPTIMAL": (openai_capacity == "NORMAL" and claude_capacity == "NORMAL"),
            "CLAUDE_FIRST_CONSERVATION": (
                openai_capacity in CAPACITY_CONSTRAINED and claude_capacity in CAPACITY_AVAILABLE
            ),
            "OPENAI_FIRST_CONSERVATION": (
                claude_capacity in CAPACITY_CONSTRAINED and openai_capacity in CAPACITY_AVAILABLE
            ),
        }.get(mode)
        if requirement is None:
            failures.append(f"{label}: unknown capacity_routing_mode {mode!r}")
        elif not requirement:
            failures.append(
                f"{label}: capacity_routing_mode {mode!r} contradicts the proven capacities "
                f"(openai={openai_capacity!r}, claude={claude_capacity!r})"
            )

    # --- authority never travels in state ------------------------------------------------------
    authorization = instance.get("authorization")
    if not isinstance(authorization, dict):
        failures.append(f"{label}: authorization must be an object carrying the declared mutation scope")
    elif authorization.get("merge_authorized") is not False:
        failures.append(f"{label}: merge_authorized must be false; merge authority is never carried in state")

    return failures


def check_manifest_instance(label: str, instance: object) -> list[str]:
    """The whole operational gate: grammar SHAPE plus cross-field RELATIONS."""
    failures = manifest_grammar_failures(label, instance)
    failures.extend(manifest_relation_failures(label, instance))
    return failures


# --- TESTED_REVISION_BINDING_V1 ------------------------------------------------------------
#
# A repository cannot prove that its own CI step ran; that is GitHub's property. What a
# repository CAN do is state, executably, the relation the controller must satisfy with live
# evidence before a merge-readiness verdict - so the rule is reviewable and testable rather
# than prose. This function judges SUPPLIED EVIDENCE. It contacts nothing and parses no
# workflow: run provenance is established by the controller from authenticated GitHub reads.

TESTED_REVISION_EVIDENCE_FIELDS = (
    "event",
    "audited_pr_head",
    "audited_head_tree",
    "current_base",
    "workflow_run_id",
    "workflow_path",
    "run_reported_head",
    "actual_checkout_revision",
    "tested_revision_parents",
    "tested_revision_tree",
    "checkout_ref_override",
    "tests_job_conclusion",
    "agent_os_gate_step_conclusions",
    "required_contexts",
)

ACCEPTED_TESTED_EVENTS = ("pull_request", "push")
TERMINAL_SUCCESS = "success"

# The run must come from THIS workflow. A sibling workflow can publish a green `tests` context,
# so a non-empty path proves nothing: the observed path is compared to the expected one.
EXPECTED_CI_WORKFLOW_PATH = ".github/workflows/ci.yml"

# The exact gate steps that must be present AND successful. Checking only the values supplied
# let a bundle omit a gate entirely, and a missing entry is indistinguishable from a gate that
# never ran.
REQUIRED_AGENT_OS_GATE_STEPS = (
    "Agent OS control-plane contract",
    "Agent OS contract oracle anchor",
)

# STRICT_TESTED_REVISION_EVIDENCE_V1.
#
# The previous implementation compared evidence values to each other before establishing that the
# values were revision identities at all. Python's `!=` is happy to compare two unknowns: with
# `current_base` and `tested_revision_parents[0]` both None, `parents[0] != current_base` is False
# and the relation "the base did not move" was reported as SATISFIED by two absent facts. The same
# held for the head, for both trees, and for an empty checkout revision inside a list.
#
# The root cause is an ordering one, so the fix is an ordering one: NOTHING is compared until every
# field has passed an explicit typed shape contract. A relation over unvalidated values is not a
# weaker proof, it is not a proof.
#
# `_shape` names a total predicate per field. bool is excluded from the integer shapes on purpose:
# `isinstance(True, int)` is True in Python, so a run id of `True` would otherwise be accepted.

TESTED_REVISION_SHAPES: dict[str, str] = {
    "event": "EVENT",
    "audited_pr_head": "REVISION",
    "audited_head_tree": "REVISION",
    "current_base": "REVISION",
    "workflow_run_id": "RUN_ID",
    "workflow_path": "OPERATIONAL",
    "run_reported_head": "REVISION",
    "actual_checkout_revision": "REVISION",
    "tested_revision_parents": "REVISION_LIST",
    "tested_revision_tree": "REVISION",
    "checkout_ref_override": "OVERRIDE_FLAG",
    "tests_job_conclusion": "OPERATIONAL",
    "agent_os_gate_step_conclusions": "CONCLUSION_MAP",
    "required_contexts": "CONTEXT_LIST",
}


def _revision_shape_failure(value: object) -> str | None:
    """A revision identity is a 40-character hex object name. Nothing else is one."""
    if not isinstance(value, str):
        return f"must be a revision identity string, got {type(value).__name__}"
    if not value.strip():
        return "is blank; a blank value is not a revision identity"
    if not HASH_IDENTIFIER_RE.match(value):
        return "is not a 40-character hexadecimal object name"
    return None


def tested_revision_shape_failures(evidence: dict) -> list[str]:
    """Prove every field IS what the relations are about to assume. TOTAL: never raises."""
    failures: list[str] = []
    for field, shape in TESTED_REVISION_SHAPES.items():
        value = evidence[field]
        if shape == "REVISION":
            reason = _revision_shape_failure(value)
            if reason:
                failures.append(f"{field} {reason}")
        elif shape == "REVISION_LIST":
            if not isinstance(value, (list, tuple)):
                failures.append(f"{field} must be a list of revision identities")
                continue
            for index, item in enumerate(value):
                reason = _revision_shape_failure(item)
                if reason:
                    failures.append(f"{field}[{index}] {reason}")
        elif shape == "RUN_ID":
            if isinstance(value, bool) or not isinstance(value, int):
                failures.append(f"{field} must be an integer run identity, got {value!r}")
            elif value <= 0:
                failures.append(f"{field} must be a positive run identity, got {value!r}")
        elif shape == "OPERATIONAL":
            for reason in operational_text_failures(value):
                failures.append(f"{field} {reason}")
        elif shape == "EVENT":
            if value not in ACCEPTED_TESTED_EVENTS:
                failures.append(
                    f"event {value!r} is not accepted as merge-gate evidence without a separate audited design"
                )
        elif shape == "OVERRIDE_FLAG":
            # RC-08: this control plane accepts exactly one checkout contract - the default one.
            if value is not False:
                failures.append(
                    f"checkout_ref_override must be exactly false; {value!r} is not accepted "
                    f"merge-gate evidence in this control plane"
                )
        elif shape == "CONCLUSION_MAP":
            if not isinstance(value, dict):
                failures.append(f"{field} must be an object mapping step name to conclusion")
            else:
                for key, item in value.items():
                    if not isinstance(key, str) or operational_text_failures(item):
                        failures.append(f"{field}[{key!r}] must map a step name to a reported conclusion")
        elif shape == "CONTEXT_LIST":
            if not isinstance(value, (list, tuple)):
                failures.append(f"{field} must be a list of required status context names")
            elif not value:
                failures.append(f"{field} is empty; an empty required-context inventory proves no context was required")
            else:
                for index, item in enumerate(value):
                    for reason in operational_text_failures(item):
                        failures.append(f"{field}[{index}] {reason}")
    return failures


def tested_revision_failures(evidence: object) -> list[str]:
    """Judge one premerge evidence bundle. TOTAL: never raises on malformed input.

    An empty result means the SUPPLIED evidence satisfies the relation - not that the evidence
    is true. Establishing it is the controller's duty (agent_os_v2.md section 17.1).
    """
    if not isinstance(evidence, dict):
        return ["tested-revision evidence must be an object"]

    failures = [
        f"tested-revision evidence is missing {f!r}" for f in TESTED_REVISION_EVIDENCE_FIELDS if f not in evidence
    ]
    if failures:
        return failures

    # ORDERING IS THE CONTRACT: no relation runs over a value whose shape is unproven, because
    # two absent facts compare equal and would report the relation as satisfied.
    shape_failures = tested_revision_shape_failures(evidence)
    if shape_failures:
        return [f"SAFETY_BLOCKER: the tested-revision evidence is not well-formed: {r}" for r in shape_failures]

    event = evidence["event"]
    checkout = evidence["actual_checkout_revision"]
    parents = evidence["tested_revision_parents"]

    if event == "pull_request":
        if len(parents) != 2:
            failures.append(
                f"a pull_request tested revision must be a two-parent merge revision, got {len(parents)} parent(s)"
            )
        else:
            if parents[0] != evidence["current_base"]:
                failures.append("tested revision parent 1 is not the current base; the base moved")
            if parents[1] != evidence["audited_pr_head"]:
                failures.append("tested revision parent 2 is not the audited head; the head moved")
        if evidence["tested_revision_tree"] != evidence["audited_head_tree"]:
            failures.append(
                "SAFETY_BLOCKER: the tested tree differs from the audited head tree, so CI tested "
                "content the independent audit never accepted"
            )
    else:  # push
        if checkout != evidence["audited_pr_head"]:
            failures.append("a push tested revision must equal the audited revision")
        if parents:
            failures.append("a push tested revision has no synthetic merge relation")
        if evidence["tested_revision_tree"] != evidence["audited_head_tree"]:
            failures.append(
                "SAFETY_BLOCKER: the tested tree differs from the audited head tree, so CI tested "
                "content the independent audit never accepted"
            )

    if evidence["tests_job_conclusion"] != TERMINAL_SUCCESS:
        failures.append(
            f"the required tests job concluded {evidence['tests_job_conclusion']!r}; only "
            f"{TERMINAL_SUCCESS!r} is acceptance - skipped, neutral and cancelled are not"
        )
    steps = evidence["agent_os_gate_step_conclusions"]
    for step in REQUIRED_AGENT_OS_GATE_STEPS:
        if step not in steps:
            failures.append(
                f"Agent OS gate step {step!r} has no reported conclusion; an absent entry is not "
                f"evidence that the gate ran"
            )
    for step, conclusion in steps.items():
        if conclusion != TERMINAL_SUCCESS:
            failures.append(
                f"Agent OS gate step {step!r} concluded {conclusion!r}; only {TERMINAL_SUCCESS!r} is acceptance"
            )

    # A required context name is not a workflow identity, so the run's own source path must be
    # the expected workflow - a sibling workflow publishing a green context is not a substitute.
    if evidence["workflow_path"] != EXPECTED_CI_WORKFLOW_PATH:
        failures.append(
            f"the run's source workflow is {evidence['workflow_path']!r}, not "
            f"{EXPECTED_CI_WORKFLOW_PATH!r}; a required status context does not identify a workflow "
            f"file or revision, so a sibling workflow cannot supply this provenance"
        )
    return failures


# --- registry, schema and fixture agreement -------------------------------------------------


def _check_manifest_grammar(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Registry, grammar and generated schema must agree, in both directions."""
    declared: dict[str, str] = dict(ctx["proof_paired_classes"])  # type: ignore[arg-type]

    for field, value_class in declared.items():
        if value_class not in VALUE_CLASSES:
            failures.append(
                f"{CANONICAL}: {field} declares unknown value class {value_class!r}; "
                f"known classes are {list(VALUE_CLASSES)}"
            )
        elif field not in PROOF_PAIRED_GRAMMAR:
            failures.append(f"{CANONICAL}: {field} is registered proof-paired but the grammar has no node")
        elif PROOF_PAIRED_GRAMMAR[field]["kind"] != value_class:
            failures.append(
                f"{field} is registered {value_class} but the grammar node is "
                f"{PROOF_PAIRED_GRAMMAR[field]['kind']}; the registry and the grammar must agree"
            )
    for field in PROOF_PAIRED_GRAMMAR:
        if field not in declared:
            failures.append(f"{CANONICAL}: the grammar proof-pairs {field} but the registry does not")

    # The committed specification must equal what the grammar generates, as a parsed object.
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    raw = read_text(root, schema_path)
    if raw is None:
        failures.append(f"{schema_path}: missing")
        return
    try:
        committed = json.loads(raw, parse_constant=_reject_json_constant)
    except ValueError as exc:
        failures.append(f"{schema_path}: invalid JSON: {exc}")
        return
    try:
        committed_text = canonical_json(committed)
    except ValueError as exc:
        failures.append(f"{schema_path}: not a JSON specification artifact: {exc}")
        return
    if committed_text != canonical_json(emit_manifest_schema()):
        failures.append(
            f"{schema_path}: does not equal the schema generated from the canonical operational "
            f"grammar; it is a GENERATED artifact - regenerate it with --emit-schema rather than "
            f"editing it by hand"
        )


def _check_continuity_example(root: Path, failures: list[str]) -> None:
    """The committed fixture is judged by the SAME executable gate the contract publishes."""
    example_path = "docs/crypto_core/continuity/state_manifest.example.json"
    raw = read_text(root, example_path)
    if raw is None:
        failures.append(f"{example_path}: missing")
        return
    if "EXAMPLE_ONLY" not in raw:
        failures.append(f"{example_path}: a committed fixture must declare EXAMPLE_ONLY")
    try:
        example = json.loads(raw)
    except ValueError as exc:
        failures.append(f"{example_path}: invalid JSON: {exc}")
        return
    failures.extend(check_manifest_instance(example_path, example))


def check_manifest_file(root: Path, manifest_path: Path) -> list[str]:
    """Validate a COMPILED operational manifest against the canonical grammar and relations.

    This is the executable acceptance path. The published JSON Schema is a generated
    specification artifact and is never interpreted here.
    """
    try:
        instance = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [f"{manifest_path}: cannot be read as JSON ({exc})"]
    return check_manifest_instance(str(manifest_path), instance)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def collect_failures(root: Path) -> list[str]:
    """Run every structural check and return an ordered list of failure strings."""
    failures: list[str] = []
    ctx = _check_registries(root, failures)
    if ctx is None:
        return failures

    _check_existence(root, ctx, failures)
    _check_marker_regions(root, ctx, failures)
    _check_roles(root, ctx, failures)
    max_effort_classes = _check_declarations(root, ctx, failures)
    _check_routing(root, ctx, max_effort_classes, failures)
    _check_fixed_blocks(ctx, failures)
    _check_single_prompt_template(root, ctx, failures)
    _check_required_tokens(root, ctx, failures)
    _check_durable_surfaces(root, ctx, failures)
    _check_model_agnostic(root, ctx, failures)
    _check_prohibited_sizing(root, ctx, failures)
    _check_host_discovery(root, ctx, failures)
    _check_executable_subordinates(root, ctx, failures)
    _check_effort_family_legality(root, ctx, max_effort_classes, failures)
    _check_capacity_contract(root, ctx, failures)
    _check_manifest_grammar(root, ctx, failures)
    _check_continuity_example(root, failures)
    return failures


def repo_root_from_here() -> Path:
    return Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Deterministic structural validator for the crypto_core Agent OS control plane. "
            "Read-only, stdlib-only, offline. Structure and bounded lexical contracts only - "
            "arbitrary semantic contradiction is the independent audit's responsibility."
        )
    )
    parser.add_argument(
        "--root",
        default=None,
        help="Repository root to validate (default: the repository containing this script).",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON output.")
    parser.add_argument(
        "--emit-schema",
        action="store_true",
        help=(
            "Render docs/crypto_core/continuity/state_manifest.schema.json from the canonical typed "
            "operational grammar and print it. Read-only: it writes nothing."
        ),
    )
    parser.add_argument(
        "--manifest",
        default=None,
        metavar="PATH",
        help=(
            "Validate a COMPILED ephemeral state manifest against the proof-pairing and runtime "
            "relations. Schema validation alone is not sufficient; this is the executable gate."
        ),
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root_from_here()

    if args.emit_schema:
        print(json.dumps(emit_manifest_schema(), indent=2, ensure_ascii=False, sort_keys=False))
        return 0

    if args.manifest is not None:
        manifest_failures = check_manifest_file(root, Path(args.manifest))
        if args.json:
            print(
                json.dumps(
                    {"manifest": args.manifest, "ok": not manifest_failures, "failures": manifest_failures},
                    indent=2,
                    sort_keys=True,
                )
            )
        elif manifest_failures:
            print(f"STATE_MANIFEST: FAIL ({len(manifest_failures)} issue(s))")
            for item in manifest_failures:
                print(f"  - {item}")
        else:
            print("STATE_MANIFEST: PASS")
            print(f"  manifest: {args.manifest}")
        return 1 if manifest_failures else 0

    failures = collect_failures(root)

    if args.json:
        print(json.dumps({"root": str(root), "ok": not failures, "failures": failures}, indent=2, sort_keys=True))
    elif failures:
        print(f"AGENT_OS_CONTROL_PLANE: FAIL ({len(failures)} issue(s))")
        for item in failures:
            print(f"  - {item}")
    else:
        print("AGENT_OS_CONTROL_PLANE: PASS")
        print(f"  root: {root}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
