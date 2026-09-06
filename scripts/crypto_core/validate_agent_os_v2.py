#!/usr/bin/env python3
"""Deterministic structural validator for the crypto_core Agent OS control plane.

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
  registry, in both directions so schema and registry cannot drift apart;
* an EXECUTABLE validator invocation inside the required CI job, not a mention of its path;
* the model-agnostic scan over the exact declared set;
* legacy retirement and CI wiring.

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
FRONTIER_LANE = "GPT-6 Astra"
FRONTIER_MODEL_ID = "gpt-6-astra"

# Lanes that must never appear in ANY active route row.
RETIRED_ROUTE_LANE_TOKENS = ("Fable", "Copilot", "Opus 4", "Sol")

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
    "ASTRA_REQUIRED_BUT_UNAVAILABLE",
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
BLOCK_EFFORT_ENUM = "REASONING_EFFORT_ENUM"
BLOCK_PROMPT_FIELDS = "PROMPT_COMPILER_V2_1_FIELDS"
BLOCK_EVIDENCE_CLASSES = "MODEL_EVIDENCE_CLASSES"
BLOCK_WORK_CONTRACT = "WORK_RETURN_CONTRACT"

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

    # 5) The protected frontier lane owns T4 outright.
    t4_rows = [row for row in parsed if row[0] == "T4"]
    if not t4_rows:
        failures.append(f"{CANONICAL}: no T4 protected route declared")
    for _cls, intents, lane, model_id, _effort, mutation in t4_rows:
        if FRONTIER_LANE not in lane:
            failures.append(f"{CANONICAL}: T4 route lane is {lane} but the protected frontier lane is {FRONTIER_LANE}")
        if model_id != FRONTIER_MODEL_ID:
            failures.append(f"{CANONICAL}: T4 route model id is {model_id} but must be {FRONTIER_MODEL_ID}")
        if mutation != "READ_ONLY":
            failures.append(f"{CANONICAL}: T4 route must be READ_ONLY, got {mutation}")
        for intent in intents:
            if intent != "CLASS_C_CROSS_CONTRACT":
                failures.append(f"{CANONICAL}: T4 route carries non-Class-C intent {intent}")

    # 6) Read-only families never carry mutation authority.
    for cls, _intents, _lane, _mid, _effort, mutation in parsed:
        if cls in {"T3C", "T3D", "T3E", "XR"} and mutation != "READ_ONLY":
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


def _check_continuity_fixtures(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Prove the manifest schema implements EXACTLY the registered proof-paired field set.

    The check runs in BOTH directions. Every registered field must have a value property, an
    ``_evidence`` companion, both in ``required``, and a conditional branch keyed on the companion.
    Every conditional branch in the schema must correspond to a registered field. That is what stops
    the registry and the schema drifting apart, which is the defect this replaced: a description that
    promised universal proof pairing while several live fields carried no companion at all.
    """
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    example_path = "docs/crypto_core/continuity/state_manifest.example.json"
    registered: list[str] = list(ctx["proof_paired"])  # type: ignore[arg-type]

    schema_raw = read_text(root, schema_path)
    if schema_raw is not None:
        try:
            schema = json.loads(schema_raw)
        except ValueError as exc:
            failures.append(f"{schema_path}: invalid JSON: {exc}")
        else:
            if schema.get("title") != "STATE_MANIFEST_V1":
                failures.append(f"{schema_path}: title must be STATE_MANIFEST_V1")

            properties = schema.get("properties") or {}
            required = set(schema.get("required") or [])
            for field in registered:
                evidence = f"{field}_evidence"
                if field not in properties:
                    failures.append(f"{schema_path}: registered proof-paired field has no property: {field}")
                if evidence not in properties:
                    failures.append(f"{schema_path}: registered proof-paired field has no companion: {evidence}")
                elif (properties[evidence] or {}).get("$ref") != "#/$defs/evidence_status":
                    failures.append(f"{schema_path}: {evidence} must reference the evidence_status enum")
                for name in (field, evidence):
                    if name not in required:
                        failures.append(f"{schema_path}: {name} must be a required field")

            branch_fields = set()
            for branch in schema.get("allOf") or []:
                keyed = list(((branch.get("if") or {}).get("properties") or {}).keys())
                if len(keyed) != 1 or not keyed[0].endswith("_evidence"):
                    failures.append(f"{schema_path}: proof-pair branch must key on exactly one _evidence field")
                    continue
                field = keyed[0][: -len("_evidence")]
                branch_fields.add(field)
                then_props = (branch.get("then") or {}).get("properties") or {}
                else_props = (branch.get("else") or {}).get("properties") or {}
                if field not in then_props:
                    failures.append(f"{schema_path}: PROVEN branch for {field} does not constrain the value")
                if (else_props.get(field) or {}).get("type") != "null":
                    failures.append(f"{schema_path}: UNKNOWN branch for {field} must require exactly null")

            missing = sorted(set(registered) - branch_fields)
            extra = sorted(branch_fields - set(registered))
            for field in missing:
                failures.append(f"{schema_path}: no proof-pair constraint for registered field: {field}")
            for field in extra:
                failures.append(f"{schema_path}: proof-pair constraint for unregistered field: {field}")

            effort = (schema.get("$defs") or {}).get("nullable_effort") or {}
            effort_values: list[object] = list(effort.get("enum") or [])
            for variant in effort.get("anyOf") or []:
                effort_values.extend(variant.get("enum") or [])
            if "ultra" in [str(v).lower() for v in effort_values if v is not None]:
                failures.append(f"{schema_path}: Ultra must not appear in the reasoning-effort enum")

    example_raw = read_text(root, example_path)
    if example_raw is not None:
        if "EXAMPLE_ONLY" not in example_raw:
            failures.append(f"{example_path}: a committed fixture must declare EXAMPLE_ONLY")
        try:
            example = json.loads(example_raw)
        except ValueError as exc:
            failures.append(f"{example_path}: invalid JSON: {exc}")
            return
        if example.get("schema") != "STATE_MANIFEST_V1":
            failures.append(f"{example_path}: schema field must be STATE_MANIFEST_V1")
        # The committed fixture is validated by the SAME deterministic relation checker the contract
        # uses, never by prose inspection.
        contracts, _contract_failures = manifest_field_contracts(root)
        failures.extend(manifest_relation_failures(example_path, example, contracts))


# ---------------------------------------------------------------------------
# MEANINGFUL_VALUE_CLASS_REGISTRY_V1
# ---------------------------------------------------------------------------
#
# `value is not None` was never a proof predicate. It answers a JSON TOPOLOGY question -
# "is the key populated" - while the contract asks an EVIDENTIAL one: "does this carry
# evidence". "" and "   " are populated and prove nothing, and that gap applied to every
# proof-paired field, not only to the ones a review happened to name.
#
# Meaningfulness is not blanket truthiness either: 0 open PRs, 0 unresolved threads and an
# empty completed-gates list are all legitimate PROVEN values. It is therefore
# TYPE-DEPENDENT, and the type is DECLARED per field in the canonical registry rather than
# inferred - so a new proof field cannot be added without saying how it is proven.

MEANINGFUL_VALUE_CLASSES = (
    "NONEMPTY_STRING",
    "HASH_IDENTIFIER",
    "NONNEGATIVE_INT",
    "POSITIVE_INT",
    "NORMALIZED_ENUM",
    "STRUCTURED_LIST",
)

# Git accepts object ids in any letter case; a lowercase-only rule was itself a bypass.
HASH_IDENTIFIER_RE = re.compile(r"\A[0-9a-fA-F]{40}\Z")
SCHEMA_HASH_PATTERN = "^[0-9a-fA-F]{40}$"

# The schema shape each declared class must correspond to, and the floor an integer class implies.
CLASS_SCHEMA_KIND = {
    "NONEMPTY_STRING": "nonempty_string",
    "HASH_IDENTIFIER": "hash",
    "NONNEGATIVE_INT": "int",
    "POSITIVE_INT": "int",
    "NORMALIZED_ENUM": "enum",
    "STRUCTURED_LIST": "list",
}
CLASS_INT_MINIMUM = {"NONNEGATIVE_INT": 0, "POSITIVE_INT": 1}


def schema_value_shape(prop: object) -> tuple[str, object] | str:
    """Reduce a proof-paired schema property to (kind, detail), or return a failure string.

    Deliberately bounded to the constructs the manifest actually uses, and FAIL-CLOSED: a
    construct this reader does not recognize is an error, never a silent pass. This is not a
    JSON Schema engine and must never grow into one.
    """
    if not isinstance(prop, dict):
        return "property is not an object"
    branches = prop.get("anyOf")
    if not isinstance(branches, list) or len(branches) != 2:
        return "property must be anyOf[<value>, null]"
    value_branch: dict | None = None
    saw_null = False
    for branch in branches:
        if not isinstance(branch, dict):
            return "anyOf branch is not an object"
        if branch.get("type") == "null":
            saw_null = True
        else:
            value_branch = branch
    if not saw_null or value_branch is None:
        return "property must offer exactly one value branch and one null branch"

    if "enum" in value_branch:
        members = value_branch["enum"]
        if not isinstance(members, list) or not members or not all(isinstance(m, str) for m in members):
            return "enum must be a non-empty list of strings"
        return ("enum", frozenset(members))
    kind = value_branch.get("type")
    if kind == "string":
        if value_branch.get("pattern") == SCHEMA_HASH_PATTERN:
            return ("hash", None)
        if value_branch.get("minLength") == 1:
            return ("nonempty_string", None)
        return "string property must declare either the object-id pattern or minLength 1"
    if kind == "integer":
        minimum = value_branch.get("minimum")
        if minimum not in (0, 1):
            return "integer property must declare minimum 0 or 1"
        return ("int", minimum)
    if kind == "array":
        items = value_branch.get("items")
        if not isinstance(items, dict):
            return "array property must declare an items object"
        return ("list", items)
    return f"unsupported property type {kind!r}"


def _element_failures(index: int, element: object, items: object) -> list[str]:
    """Total element check for a STRUCTURED_LIST item, bounded to the shapes actually used."""
    if not isinstance(items, dict) or items.get("type") != "object" or items.get("additionalProperties") is not False:
        return [f"item {index} cannot be checked: the element schema is not a closed object schema"]
    if not isinstance(element, dict):
        return [f"item {index} must be an object"]
    properties = items.get("properties")
    required = items.get("required")
    if not isinstance(properties, dict) or not isinstance(required, list):
        return [f"item {index} cannot be checked: the element schema is malformed"]

    reasons: list[str] = []
    for key in required:
        if key not in element:
            reasons.append(f"item {index} is missing {key!r}")
    for key in element:
        if key not in properties:
            reasons.append(f"item {index} carries unknown key {key!r}")
    for key, spec in properties.items():
        if key not in element or not isinstance(spec, dict):
            continue
        value = element[key]
        if "enum" in spec:
            members = spec["enum"]
            if not isinstance(value, str) or value not in members:
                reasons.append(f"item {index} {key!r} is not one of {sorted(members)}")
        elif spec.get("type") == "string":
            if not isinstance(value, str):
                reasons.append(f"item {index} {key!r} must be a string")
            elif spec.get("minLength") == 1 and not _carries_visible_text(value):
                reasons.append(f"item {index} {key!r} carries no visible characters")
        elif spec.get("type") == "integer":
            if isinstance(value, bool) or not isinstance(value, int):
                reasons.append(f"item {index} {key!r} must be an integer")
            elif value < spec.get("minimum", 0):
                reasons.append(f"item {index} {key!r} is below its declared minimum")
        else:
            reasons.append(f"item {index} {key!r} uses an element schema this checker does not accept")
    return reasons


# Categories that render as nothing: control, format (zero-width space/joiner, BOM) and the
# separators. Closing over the CATEGORY rather than over a list of characters is what keeps this
# from becoming another enumeration - every present and future invisible code point is covered.
INVISIBLE_UNICODE_CATEGORIES = frozenset({"Cc", "Cf", "Zs", "Zl", "Zp"})


def _carries_visible_text(value: str) -> bool:
    """True when at least one character actually renders. `""`, `"   "` and `"​"` do not."""
    return any(unicodedata.category(ch) not in INVISIBLE_UNICODE_CATEGORIES for ch in value)


def meaningful_value_failures(value: object, value_class: str, detail: object) -> list[str]:
    """TOTAL. For ANY JSON value, say why it is not meaningful evidence, or return [].

    Never raises: a forged value produces an explicit reason, never an exception.
    """
    if value_class == "NONEMPTY_STRING":
        if not isinstance(value, str):
            return ["must be a string"]
        return [] if _carries_visible_text(value) else ["carries no visible characters, which is not evidence"]
    if value_class == "HASH_IDENTIFIER":
        if not isinstance(value, str):
            return ["must be a string"]
        return [] if HASH_IDENTIFIER_RE.match(value) else ["is not a 40-character hexadecimal object id"]
    if value_class in CLASS_INT_MINIMUM:
        minimum = CLASS_INT_MINIMUM[value_class]
        if isinstance(value, bool):
            return ["must be an integer, not a boolean"]
        if not isinstance(value, int):
            return ["must be an integer"]
        return [] if value >= minimum else [f"must be >= {minimum}"]
    if value_class == "NORMALIZED_ENUM":
        members = detail if isinstance(detail, frozenset) else frozenset()
        if not isinstance(value, str):
            return ["must be a string"]
        return [] if value in members else [f"is not one of {sorted(members)}"]
    if value_class == "STRUCTURED_LIST":
        if not isinstance(value, list):
            return ["must be an array"]
        # An empty list is a legitimate, meaningful PROVEN value: zero blockers is a fact.
        reasons: list[str] = []
        for index, element in enumerate(value):
            reasons.extend(_element_failures(index, element, detail))
        return reasons
    return [f"has no predicate for declared value class {value_class!r}"]


def manifest_field_contracts(root: Path) -> tuple[dict[str, tuple[str, object]], list[str]]:
    """Build field -> (VALUE_CLASS, detail) from the canonical registry PLUS the schema.

    The canonical registry declares the CLASS; the schema declares the SHAPE. Neither
    duplicates the other, and the two are cross-checked in both directions so they cannot
    drift apart: a class with no matching schema shape fails, and so does a shape whose
    declared class does not match it.
    """
    failures: list[str] = []
    canonical_text = read_text(root, CANONICAL)
    if canonical_text is None:
        return {}, [f"{CANONICAL}: missing; manifest contracts cannot be built"]
    rows = parse_surface_registry(canonical_text, BLOCK_PROOF_PAIRED)
    if rows is None:
        return {}, [f"{CANONICAL}: {BLOCK_PROOF_PAIRED} block missing or malformed"]

    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema_raw = read_text(root, schema_path)
    if schema_raw is None:
        return {}, [f"{schema_path}: missing; manifest contracts cannot be built"]
    try:
        schema = json.loads(schema_raw)
    except ValueError as exc:
        return {}, [f"{schema_path}: invalid JSON: {exc}"]
    properties = schema.get("properties") or {}

    contracts: dict[str, tuple[str, object]] = {}
    for field, value_class in rows:
        if field in contracts:
            failures.append(f"{CANONICAL}: {BLOCK_PROOF_PAIRED} declares {field!r} more than once")
            continue
        if value_class not in MEANINGFUL_VALUE_CLASSES:
            failures.append(
                f"{CANONICAL}: {field} declares unknown value class {value_class!r}; "
                f"known classes are {list(MEANINGFUL_VALUE_CLASSES)}"
            )
            continue
        shape = schema_value_shape(properties.get(field))
        if isinstance(shape, str):
            failures.append(f"{schema_path}: {field}: {shape}")
            continue
        kind, detail = shape
        if kind != CLASS_SCHEMA_KIND[value_class]:
            failures.append(
                f"{field} is declared {value_class} but its schema shape is {kind!r}; "
                f"the registry class and the schema shape must agree"
            )
            continue
        if value_class in CLASS_INT_MINIMUM and detail != CLASS_INT_MINIMUM[value_class]:
            failures.append(
                f"{field} is declared {value_class} but the schema minimum is {detail!r}, "
                f"expected {CLASS_INT_MINIMUM[value_class]}"
            )
            continue
        contracts[field] = (value_class, detail)

    # Both directions: every known class must have a predicate, and every predicate a class.
    for value_class in MEANINGFUL_VALUE_CLASSES:
        if value_class not in CLASS_SCHEMA_KIND:
            failures.append(f"value class {value_class!r} has no schema-shape mapping")
        probe = meaningful_value_failures(object(), value_class, None)
        if not probe:
            failures.append(f"value class {value_class!r} accepted an opaque value; its predicate is not total")
    for value_class in CLASS_SCHEMA_KIND:
        if value_class not in MEANINGFUL_VALUE_CLASSES:
            failures.append(f"schema-shape mapping declares unknown value class {value_class!r}")

    return contracts, failures


def _check_manifest_contracts(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Prove the typed proof-paired registry and the schema agree, in both directions."""
    _contracts, contract_failures = manifest_field_contracts(root)
    failures.extend(contract_failures)


def proof_pair_failures(
    label: str,
    instance: dict,
    value_field: str,
    evidence_field: str,
    contract: tuple[str, object] | None = None,
) -> list[str]:
    """Prove one PROVEN/UNKNOWN proof pair, including that a PROVEN value is MEANINGFUL.

    Valid:   a meaningful value with PROVEN, or exactly null with UNKNOWN.
    Invalid: a value with UNKNOWN, null with PROVEN, a missing member of the pair, or a
             populated-but-semantically-empty value presented as proof.
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
        elif contract is not None:
            value_class, detail = contract
            for reason in meaningful_value_failures(value, value_class, detail):
                failures.append(f"{label}: {value_field} {reason} while {evidence_field} says PROVEN")
    elif evidence == "UNKNOWN":
        if value is not None:
            failures.append(f"{label}: {value_field} carries a value while {evidence_field} says UNKNOWN")
    else:
        failures.append(f"{label}: {evidence_field} must be PROVEN or UNKNOWN, got {evidence!r}")
    return failures


def manifest_relation_failures(label: str, instance: dict, contracts: dict[str, tuple[str, object]]) -> list[str]:
    """Prove the exact evidence/value SEMANTICS of an ephemeral manifest, not just its topology.

    Topology alone - "does a companion field exist" - let an inverted pair through: a value with
    UNKNOWN evidence, or null with PROVEN, or a continuation routing mode chosen while the capacity
    it depends on was never proven. These are the relations that make the manifest mean something.
    """
    failures: list[str] = []

    for field, contract in contracts.items():
        failures.extend(proof_pair_failures(label, instance, field, f"{field}_evidence", contract))

    # --- runtime proof ------------------------------------------------------------------------
    runtime = instance.get("model_runtime")
    if not isinstance(runtime, dict):
        failures.append(
            f"{label}: model_runtime is missing; a manifest that participates in routing or audit "
            f"must carry a runtime-proof block with an explicit evidence class"
        )
    else:
        source = runtime.get("model_evidence_source")
        actual = runtime.get("model_actual")
        observed = runtime.get("observed_effort")
        host_raw = runtime.get("host_setting_raw")
        if source not in MODEL_EVIDENCE_CLASSES:
            failures.append(
                f"{label}: model_evidence_source must be one of {list(MODEL_EVIDENCE_CLASSES)}, got {source!r}"
            )
        elif source == "RUNTIME_TELEMETRY":
            if meaningful_value_failures(actual, "NONEMPTY_STRING", None):
                failures.append(
                    f"{label}: RUNTIME_TELEMETRY claims runtime proof but model_actual carries no meaningful value"
                )
        elif source == "USER_ATTESTED_UI_SELECTION":
            attested = [
                candidate
                for candidate in (actual, host_raw)
                if not meaningful_value_failures(candidate, "NONEMPTY_STRING", None)
            ]
            if not attested:
                failures.append(
                    f"{label}: USER_ATTESTED_UI_SELECTION carries no meaningful model_actual or "
                    f"host_setting_raw, so nothing was actually attested"
                )
        else:
            # CONFIGURATION_EVIDENCE_ONLY, UNKNOWN and CONTRADICTED prove no execution. Populating an
            # actual/observed value under them would present configuration or a contradiction as proof.
            if actual is not None:
                failures.append(f"{label}: {source} must not populate model_actual as proven execution")
            if observed is not None:
                failures.append(f"{label}: {source} must not populate observed_effort as proven execution")

    # --- provider capacity --------------------------------------------------------------------
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

    # --- authority never travels in state -------------------------------------------------------
    authorization = instance.get("authorization")
    if not isinstance(authorization, dict):
        failures.append(f"{label}: authorization must be an object carrying the declared mutation scope")
    else:
        if authorization.get("merge_authorized") is not False:
            failures.append(f"{label}: merge_authorized must be false; merge authority is never carried in state")
        for reason in meaningful_value_failures(authorization.get("mutation_scope"), "NONEMPTY_STRING", None):
            failures.append(f"{label}: authorization.mutation_scope {reason}")

    return failures


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
    _check_effort_family_legality(root, ctx, max_effort_classes, failures)
    _check_capacity_contract(root, ctx, failures)
    _check_continuity_fixtures(root, ctx, failures)
    _check_manifest_contracts(root, ctx, failures)
    return failures


def check_manifest_file(root: Path, manifest_path: Path) -> list[str]:
    """Run the manifest SEMANTIC relations over a compiled operational manifest.

    Schema validation alone is necessary and NOT sufficient. JSON Schema constrains each field
    independently, so `CONFIGURATION_EVIDENCE_ONLY` beside a populated `model_actual` satisfies the
    schema while claiming a runtime identity that was never proven - and routing and audit decisions
    are taken from exactly that block. The relations already existed; they were only reachable for the
    committed fixture. This is the executable path that makes them reachable for a real manifest.
    """
    contracts, contract_failures = manifest_field_contracts(root)
    if contract_failures:
        return contract_failures
    try:
        instance = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        return [f"{manifest_path}: cannot be read as JSON ({exc})"]
    if not isinstance(instance, dict):
        return [f"{manifest_path}: a manifest must be a JSON object"]
    return manifest_relation_failures(str(manifest_path), instance, contracts)


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
