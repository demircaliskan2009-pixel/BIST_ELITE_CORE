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

# Exact command shapes. Exactness is deliberate: the previous lexical co-occurrence check accepted
# `echo <path>`, `<cmd> || true` and a disabled job, all of which contain the path while enforcing
# nothing. The validator does not try to understand arbitrary shell.
CI_VALIDATOR_COMMAND = "python scripts/crypto_core/validate_agent_os_v2.py"
CI_ORACLE_ANCHOR_COMMAND = "test -f tests/crypto_core/test_agent_os_v2_contract.py"

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
HEX_TOKEN_RE = re.compile(
    r"(?<![0-9a-zA-Z])(?=[0-9a-f]{7,40}(?![0-9a-zA-Z]))(?=[0-9a-f]*[0-9])(?=[0-9a-f]*[a-f])[0-9a-f]{7,40}"
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
    proof_paired = parse_registry(canonical_text, BLOCK_PROOF_PAIRED)
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
        (BLOCK_PROOF_PAIRED, proof_paired),
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
        "proof_paired": proof_paired,
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
        failures.extend(manifest_relation_failures(example_path, example, registered))


def proof_pair_failures(label: str, instance: dict, value_field: str, evidence_field: str) -> list[str]:
    """Prove one PROVEN/UNKNOWN proof pair.

    Valid:   a concrete value with PROVEN, or exactly null with UNKNOWN.
    Invalid: a value with UNKNOWN, null with PROVEN, or a missing member of the pair.
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


def _workflow_job_bodies(lines: list[str]) -> dict[str, list[str]]:
    """Split a workflow into {job name: body lines} using the YAML mapping shape, not prose."""
    job_key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    in_jobs = False
    current_job: str | None = None
    bodies: dict[str, list[str]] = {}
    for line in lines:
        if re.match(r"^jobs:\s*$", line):
            in_jobs = True
            continue
        if in_jobs and re.match(r"^\S", line):
            in_jobs = False
            current_job = None
            continue
        if not in_jobs:
            continue
        match = job_key_re.match(line)
        if match:
            current_job = match.group(1)
            bodies[current_job] = []
            continue
        if current_job is not None:
            bodies[current_job].append(line)
    return bodies


def _job_steps(job_lines: list[str]) -> list[list[str]]:
    """Split a job body into its ``steps:`` sequence items."""
    steps_indent: int | None = None
    start = 0
    for i, line in enumerate(job_lines):
        match = re.match(r"^(\s*)steps:\s*$", line)
        if match:
            steps_indent = len(match.group(1))
            start = i + 1
            break
    if steps_indent is None:
        return []

    steps: list[list[str]] = []
    current: list[str] | None = None
    item_re = re.compile(r"^(\s*)- ")
    for line in job_lines[start:]:
        if not line.strip():
            if current is not None:
                current.append(line)
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= steps_indent:
            break
        match = item_re.match(line)
        if match and len(match.group(1)) == indent:
            if current is not None:
                steps.append(current)
            current = [line]
        elif current is not None:
            current.append(line)
    if current is not None:
        steps.append(current)
    return steps


def _step_key(step_lines: list[str], key: str) -> tuple[str | None, list[str] | None]:
    """Return (inline value, block-scalar lines) for a top-level key of one step.

    A commented-out line is never a key: ``# run: ...`` does not match the key pattern, so a disabled
    step cannot satisfy a key requirement. Returns (None, None) when the key is absent.
    """
    dash = re.match(r"^(\s*)- (.*)$", step_lines[0])
    if dash is None:
        return (None, None)
    key_indent = len(dash.group(1)) + 2
    normalized = [" " * key_indent + dash.group(2)] + list(step_lines[1:])

    key_re = re.compile(r"^\s*([A-Za-z0-9_-]+):\s*(.*)$")
    for i, line in enumerate(normalized):
        if not line.strip():
            continue
        if len(line) - len(line.lstrip()) != key_indent:
            continue
        match = key_re.match(line)
        if match is None or match.group(1) != key:
            continue
        value = match.group(2).strip()
        if value in ("|", ">", "|-", ">-", "|+", ">+"):
            body: list[str] = []
            for nxt in normalized[i + 1 :]:
                if not nxt.strip():
                    body.append("")
                    continue
                if len(nxt) - len(nxt.lstrip()) <= key_indent:
                    break
                body.append(nxt.strip())
            return (None, body)
        return (value, None)
    return (None, None)


def _step_is_disabled(step_lines: list[str]) -> bool:
    inline, _block = _step_key(step_lines, "if")
    if inline is None:
        return False
    return inline.strip().lower().replace(" ", "") in ("false", "${{false}}")


def manifest_relation_failures(label: str, instance: dict, registered: list[str]) -> list[str]:
    """Prove the exact evidence/value SEMANTICS of an ephemeral manifest, not just its topology.

    Topology alone - "does a companion field exist" - let an inverted pair through: a value with
    UNKNOWN evidence, or null with PROVEN, or a continuation routing mode chosen while the capacity
    it depends on was never proven. These are the relations that make the manifest mean something.
    """
    failures: list[str] = []

    for field in registered:
        failures.extend(proof_pair_failures(label, instance, field, f"{field}_evidence"))

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
            if actual is None:
                failures.append(f"{label}: RUNTIME_TELEMETRY claims runtime proof but model_actual is null")
        elif source == "USER_ATTESTED_UI_SELECTION":
            if actual is None and host_raw is None:
                failures.append(
                    f"{label}: USER_ATTESTED_UI_SELECTION carries neither model_actual nor "
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

    if mode is None:
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
    authorization = instance.get("authorization") or {}
    if authorization.get("merge_authorized") is not False:
        failures.append(f"{label}: merge_authorized must be false; merge authority is never carried in state")

    return failures


def _step_executable_lines(step_lines: list[str]) -> list[str] | None:
    """Executable command lines of a step, comments and blanks removed. None when there is no run."""
    inline, block = _step_key(step_lines, "run")
    if inline is not None:
        return [inline.strip()]
    if block is None:
        return None
    return [ln.strip() for ln in block if ln.strip() and not ln.strip().startswith("#")]


def _step_is_fail_masked(step_lines: list[str]) -> bool:
    inline, _block = _step_key(step_lines, "continue-on-error")
    return inline is not None and inline.strip().lower() == "true"


def _find_exact_step(steps: list[list[str]], command: str) -> str | None:
    """Return None when an enabled step runs EXACTLY this command, else the reason it does not.

    Exactness is the whole point. The previous check accepted the path anywhere in the job body, so
    `echo <cmd>`, `<cmd> || true` and a disabled job all passed while enforcing nothing. Rather than
    trying to understand shell, the validator requires one dedicated step whose executable content is
    exactly the documented command - which rejects every prefix, suffix, wrapper and status mask
    without having to enumerate them.
    """
    saw_mention = False
    for step in steps:
        commands = _step_executable_lines(step)
        if commands is None:
            continue
        if any(command in line for line in commands):
            saw_mention = True
        if commands != [command]:
            continue
        if _step_is_disabled(step):
            return f"the step running {command!r} is disabled with 'if: false'"
        if _step_is_fail_masked(step):
            return f"the step running {command!r} sets continue-on-error, so its failure cannot fail the job"
        return None
    if saw_mention:
        return (
            f"{command!r} appears in the job but not as a dedicated step whose run is exactly that "
            f"command; a prefix, a wrapper, an appended '|| true' or extra commands do not satisfy it"
        )
    return f"no enabled step runs exactly {command!r}"


def _job_is_disabled(job_lines: list[str]) -> bool:
    """A job-level `if: false` disables every step inside it, however exact each step looks."""
    for line in job_lines:
        match = re.match(r"^    if:\s*(.+?)\s*$", line)
        if match:
            return match.group(1).strip().lower().replace(" ", "") in ("false", "${{false}}")
    return False


def _job_is_fail_masked(job_lines: list[str]) -> bool:
    for line in job_lines:
        match = re.match(r"^    continue-on-error:\s*(\S+)\s*$", line)
        if match:
            return match.group(1).strip().lower() == "true"
    return False


def _check_ci_wiring(root: Path, failures: list[str]) -> None:
    """Prove two EXACT, enabled, fail-propagating steps inside the required CI job.

    One runs the control-plane validator. The other is the external bootstrap anchor that proves the
    independent contract oracle exists - anchored here, outside the mutable artifact registry, so
    deleting the oracle and its registry entry together still fails.
    """
    ci_path = ".github/workflows/ci.yml"
    text = read_text(root, ci_path)
    if text is None:
        failures.append(f"{ci_path}: missing")
        return

    job_bodies = _workflow_job_bodies(text.splitlines())
    if "tests" not in job_bodies:
        failures.append(f"{ci_path}: required job 'tests' not found in the jobs mapping")
        return

    body = job_bodies["tests"]
    if _job_is_disabled(body):
        failures.append(f"{ci_path}: the required 'tests' job is disabled with 'if: false'")
        return
    if _job_is_fail_masked(body):
        failures.append(f"{ci_path}: the required 'tests' job sets continue-on-error, so it cannot fail")
        return

    steps = _job_steps(body)
    if not steps:
        failures.append(f"{ci_path}: the 'tests' job declares no steps")
        return

    for command, label in (
        (CI_VALIDATOR_COMMAND, "control-plane validator gate"),
        (CI_ORACLE_ANCHOR_COMMAND, "independent-oracle bootstrap anchor"),
    ):
        reason = _find_exact_step(steps, command)
        if reason is not None:
            failures.append(f"{ci_path}: {label} not enforced - {reason}")


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
    _check_ci_wiring(root, failures)
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
    args = parser.parse_args(argv)

    root = Path(args.root).resolve() if args.root else repo_root_from_here()
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
