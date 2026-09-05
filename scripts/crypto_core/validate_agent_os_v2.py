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
* the durable-surface volatile-state scan over the exact declared set;
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


def marker_region_failures(rel: str, lines: list[str]) -> list[str]:
    """Prove every exempt-region marker pair is balanced, ordered and non-nested.

    An unterminated exemption would silently swallow the rest of a file, which is exactly the
    fail-open shape this control plane exists to remove. Unbalanced markers therefore FAIL rather
    than being tolerated.
    """
    failures: list[str] = []
    for name in EXEMPT_REGION_BLOCKS:
        depth = 0
        for lineno, raw in enumerate(lines, start=1):
            stripped = raw.strip()
            if stripped == _begin(name):
                if depth:
                    failures.append(f"{rel}: nested {name}_BEGIN at line {lineno}")
                depth += 1
            elif stripped == _end(name):
                if depth == 0:
                    failures.append(f"{rel}: {name}_END without BEGIN at line {lineno}")
                else:
                    depth -= 1
        if depth:
            failures.append(f"{rel}: unterminated {name}_BEGIN (region would swallow the rest of the file)")
    return failures


def active_lines(lines: list[str]) -> list[tuple[int, str]]:
    """Return (1-based line number, text) for every line OUTSIDE an exempt region.

    Region membership is decided by explicit structural markers only. Headings, section numbers and
    prose proximity are deliberately irrelevant: renaming or reformatting a heading can no longer
    change which text is treated as active.
    """
    out: list[tuple[int, str]] = []
    depth = 0
    for lineno, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if any(stripped == _begin(name) for name in EXEMPT_REGION_BLOCKS):
            depth += 1
            continue
        if any(stripped == _end(name) for name in EXEMPT_REGION_BLOCKS):
            depth = max(0, depth - 1)
            continue
        if depth == 0:
            out.append((lineno, raw))
    return out


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
    for label, value in (
        (BLOCK_REQUIRED_ARTIFACTS, artifacts),
        (BLOCK_DURABLE_SURFACES, durable),
        (BLOCK_MODEL_AGNOSTIC, agnostic),
        (BLOCK_RETIRED_PATHS, retired),
    ):
        if value is None:
            failures.append(f"{CANONICAL}: {label} block missing or malformed")
    if artifacts is None or durable is None or agnostic is None or retired is None:
        return None

    surface_paths = [p for p, _ in surfaces]
    for label, values in (
        (BLOCK_ACTIVE_SURFACES, surface_paths),
        (BLOCK_REQUIRED_ARTIFACTS, artifacts),
        (BLOCK_DURABLE_SURFACES, durable),
        (BLOCK_MODEL_AGNOSTIC, agnostic),
        (BLOCK_RETIRED_PATHS, retired),
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
    for cls, _intents, lane, model_id, _effort, mutation in t4_rows:
        if FRONTIER_LANE not in lane:
            failures.append(f"{CANONICAL}: T4 route lane is {lane} but the protected frontier lane is {FRONTIER_LANE}")
        if model_id != FRONTIER_MODEL_ID:
            failures.append(f"{CANONICAL}: T4 route model id is {model_id} but must be {FRONTIER_MODEL_ID}")
        if mutation != "READ_ONLY":
            failures.append(f"{CANONICAL}: T4 route must be READ_ONLY, got {mutation}")
        for intent in _intents:
            if intent != "CLASS_C_CROSS_CONTRACT":
                failures.append(f"{CANONICAL}: T4 route carries non-Class-C intent {intent}")
        del cls

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


def _check_required_tokens(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    canonical_text: str = ctx["canonical_text"]  # type: ignore[assignment]
    for token in REQUIRED_CANONICAL_TOKENS:
        if token not in canonical_text:
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


def _check_durable_surfaces(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Scan exactly the declared DURABLE_SURFACES set for volatile current state."""
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


def _check_continuity_fixtures(root: Path, failures: list[str]) -> None:
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    example_path = "docs/crypto_core/continuity/state_manifest.example.json"

    schema_raw = read_text(root, schema_path)
    if schema_raw is not None:
        try:
            schema = json.loads(schema_raw)
        except ValueError as exc:
            failures.append(f"{schema_path}: invalid JSON: {exc}")
        else:
            if schema.get("title") != "STATE_MANIFEST_V1":
                failures.append(f"{schema_path}: title must be STATE_MANIFEST_V1")
            required = schema.get("required") or []
            for field in ("open_pr_count", "open_pr_count_evidence"):
                if field not in required:
                    failures.append(f"{schema_path}: {field} must be a required field")
            effort_enum = ((schema.get("$defs") or {}).get("nullable_effort") or {}).get("enum") or []
            if "ultra" in [str(v).lower() for v in effort_enum if v is not None]:
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
        for value_field, evidence_field in (
            ("branch", "branch_evidence"),
            ("base_sha", "base_sha_evidence"),
            ("head_sha", "head_sha_evidence"),
            ("pr_number", "pr_number_evidence"),
            ("open_pr_count", "open_pr_count_evidence"),
        ):
            failures.extend(proof_pair_failures(example_path, example, value_field, evidence_field))
        authorization = example.get("authorization") or {}
        if authorization.get("merge_authorized") is not False:
            failures.append(
                f"{example_path}: merge_authorized must be false; merge authority is never carried in state"
            )


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


def _check_ci_wiring(root: Path, failures: list[str]) -> None:
    """The validator must run inside the required CI job.

    The job name is read from the YAML mapping structure (``jobs:`` then a two-space job key), not
    from a prose heading, so renaming a comment or reordering steps cannot silently skip the gate.
    """
    ci_path = ".github/workflows/ci.yml"
    text = read_text(root, ci_path)
    if text is None:
        failures.append(f"{ci_path}: missing")
        return

    lines = text.splitlines()
    job_key_re = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
    in_jobs = False
    current_job: str | None = None
    job_bodies: dict[str, list[str]] = {}
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
            job_bodies[current_job] = []
            continue
        if current_job is not None:
            job_bodies[current_job].append(line)

    if "tests" not in job_bodies:
        failures.append(f"{ci_path}: required job 'tests' not found in the jobs mapping")
        return
    body = "\n".join(job_bodies["tests"])
    if "scripts/crypto_core/validate_agent_os_v2.py" not in body:
        failures.append(f"{ci_path}: the 'tests' job does not run scripts/crypto_core/validate_agent_os_v2.py")


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
    _check_continuity_fixtures(root, failures)
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
