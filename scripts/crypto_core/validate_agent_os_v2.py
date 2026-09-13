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
* ONE active projection per surface: exemption regions are parsed once, structurally, and every
  authority reading and every active scan consumes that projection; authority syntax may not appear
  inside an exemption region, and every canonical block is required in the active projection;
* ONE authority reading: a registered doctrine surface and an executable subordinate's module docstring
  pass through the same projection, marker collector, reference, declaration and routing checks;
* ONE file-access boundary: the status, discovery listing, read and decoding of every file the gate judges; a
  permission, I/O or decode failure is a structured rejection, never a traceback, a silent skip or "missing";
* the positive NON_APPLYING front-matter contract for a historical host surface;
* ACTIVE_AUTHORITY_STRUCTURAL_COMPLETENESS: authority syntax is recognized structurally rather than at
  column zero, a subordinate surface carries exactly one authority reference and it resolves to the
  canonical file, and a required authority block is its populated body rather than its markers;
* the canonical typed operational grammar, and that the committed manifest schema equals the
  schema generated from it;
* the strict JSON evidence boundary: every JSON document it judges - the committed schema, the
  committed example and a compiled ``--manifest`` - is parsed by ONE primitive, also used by the
  setup audit for workspace JSON, that refuses a repeated object member name at any depth
  (compared after escape decoding), a non-finite number, nesting too deep to evaluate and
  malformed JSON before any grammar, relation or comparison reads the document.

It does NOT and MUST NOT claim to: understand arbitrary English; detect an arbitrary natural-language
paraphrase that contradicts a declaration; know live GitHub state; know the runtime model; judge audit
correctness, readiness or capital safety. Arbitrary semantic contradiction is the responsibility of
the INDEPENDENT SEMANTIC AUDIT. Growing a synonym blacklist to chase paraphrase is an explicit
anti-pattern (``ROOT_CAUSE_MODE``, ``agent_os_v2.md`` section 13).

Exit code 0 means every structural contract above holds. Any failure exits 1 with an itemised list.
"""

from __future__ import annotations

import argparse
import ast
import errno
import json
import os
import re
import sys
import unicodedata
import warnings
from pathlib import Path
from stat import S_ISREG
from typing import NamedTuple

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
BLOCK_PROOF_TARGETS = "PROOF_TARGET_BINDINGS"
BLOCK_CAPACITY_STATES = "PROVIDER_CAPACITY_STATES"
BLOCK_ROUTING_MODES = "CAPACITY_ROUTING_MODES"
BLOCK_HOST_DISCOVERY = "HOST_DISCOVERY_SCAN_PATHS"
BLOCK_HISTORICAL_HOST = "HISTORICAL_HOST_SURFACES"
BLOCK_HOST_NON_DISCOVERY = "HOST_NON_DISCOVERY_PATHS"
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

# ACTIVE_CONTROL_PLANE_SURFACE_SEMANTICS (agent_os_v2.md section 15). ONE answer to "is this content active
# authority?". The scans skipped exemption regions while every authority reader parsed the whole file, so a
# block, a declaration or a role marker wrapped in a region kept satisfying the contract while escaping every
# scan that binds active doctrine. Each surface is now parsed ONCE into a line-preserving active projection,
# and every reader - authority and scan alike - consumes that projection and nothing else.
#
# Every machine-readable block the canonical authority carries, in document order. Each must appear exactly
# once in the active projection, and a block marker missing from this inventory is undeclared authority.
CANONICAL_AUTHORITY_BLOCKS = (
    "ROLE_ROUTING_MATRIX",
    "FAMILY_SEMANTIC_CONTRACT",
    "LANE_CAPABILITY",
    "REASONING_EFFORT_ENUM",
    "INDEPENDENCE_VOCABULARY",
    "INTENT_FIRST_ROUTING",
    "MODEL_EVIDENCE_CLASSES",
    "PROMPT_COMPILER_V2_1_FIELDS",
    "WORK_RETURN_CONTRACT",
    "PROVIDER_CAPACITY_STATES",
    "CAPACITY_ROUTING_MODES",
    "TESTED_REVISION_EVIDENCE",
    "HOST_DISCOVERY_SCAN_PATHS",
    "HISTORICAL_HOST_SURFACES",
    "HOST_NON_DISCOVERY_PATHS",
    "ACTIVE_DOCTRINE_SURFACES",
    "REQUIRED_CONTROL_PLANE_ARTIFACTS",
    "DURABLE_SURFACES",
    "MODEL_AGNOSTIC_SURFACES",
    "VOLATILE_STATE_FIELDS",
    "MAX_EFFORT_FAMILY_TRIGGERS",
    "PROOF_PAIRED_MANIFEST_FIELDS",
    "PROOF_TARGET_BINDINGS",
    "RETIRED_CONTROL_PLANE_PATHS",
    "EXECUTABLE_NEGATIVE_BOUNDARY",
)
MISSING_ACTIVE_AUTHORITY = "MISSING_ACTIVE_AUTHORITY"

# A standalone block marker line, exactly as block_span reads one.
BLOCK_MARKER_LINE_RE = re.compile(r"\A<!-- ([A-Z0-9_]+)_(BEGIN|END) -->\Z")

# ACTIVE_AUTHORITY_STRUCTURAL_COMPLETENESS (agent_os_v2.md section 15). ONE matcher decides what an
# authority construct IS, and both the active readers and the reserved-syntax rule below use it. The active
# readers previously anchored a ROUTE row and a canonical declaration at column zero, so ordinary Markdown
# indentation hid a competing route or a rival declaration from the very checks that make routing and
# declaration authority singular - while the same indented line was already reserved syntax inside an
# exemption region. Each construct therefore has exactly one pattern, compiled twice: the exact-case reader
# for active authority, and a case-insensitive twin that keeps the reserved rule fail-closed.
DECLARATION_NAMES = tuple(name for name, _value in CANONICAL_DECLARATIONS) + ("MAX_EFFORT_CLASSES",)
_ROUTE_PATTERN = r"^\s*ROUTE\s*:"
_DECLARATION_PATTERN = (
    r"^\s*(?P<name>" + "|".join(re.escape(name) for name in DECLARATION_NAMES) + r")\s*:(?P<rest>.*)$"
)
ROUTE_LINE_RE = re.compile(_ROUTE_PATTERN)
ROUTE_ANY_SPELLING_RE = re.compile(_ROUTE_PATTERN, re.IGNORECASE)
DECLARATION_LINE_RE = re.compile(_DECLARATION_PATTERN)
DECLARATION_ANY_SPELLING_RE = re.compile(_DECLARATION_PATTERN, re.IGNORECASE)

# An authority reference is collected with its TARGET, so cardinality and value are judged instead of mere
# presence: keeping the expected marker and adding a second one naming another authority passed before.
#
# ONE_AUTHORITY_READING (agent_os_v2.md section 15). A role or authority-reference marker is RECOGNIZED by one
# prefix pattern in any spelling - the very pattern the reserved-syntax rule below uses - and READ by the exact
# form compiled from that same prefix. Every recognized marker counts, and one the exact form cannot read is a
# malformed marker, never an invisible one: a lowercase second reference or role marker used to be no marker
# at all to the active reader, while the same line was already reserved authority syntax inside a region.
_ROLE_MARKER_PATTERN = r"<!--\s*CONTROL_PLANE_ROLE\s*:"
_AUTHORITY_REF_PATTERN = r"<!--\s*CONTROL_PLANE_AUTHORITY_REF\s*:"
ROLE_MARKER_ANY_SPELLING_RE = re.compile(_ROLE_MARKER_PATTERN, re.IGNORECASE)
AUTHORITY_REF_ANY_SPELLING_RE = re.compile(_AUTHORITY_REF_PATTERN, re.IGNORECASE)
ROLE_MARKER_RE = re.compile(_ROLE_MARKER_PATTERN + r"\s*(?P<value>[A-Z_]+)\s*-->")
AUTHORITY_REF_RE = re.compile(_AUTHORITY_REF_PATTERN + r"\s*(?P<value>[^>]*?)\s*-->")
ROLE_MARKER = "CONTROL_PLANE_ROLE"
AUTHORITY_REF_MARKER = "CONTROL_PLANE_AUTHORITY_REF"
MARKER_GRAMMAR = {
    ROLE_MARKER: (ROLE_MARKER_ANY_SPELLING_RE, ROLE_MARKER_RE),
    AUTHORITY_REF_MARKER: (AUTHORITY_REF_ANY_SPELLING_RE, AUTHORITY_REF_RE),
}

# EXECUTABLE SUBORDINATE surfaces (agent_os_v2.md section 20.1). Their authority text is the module docstring as
# Python parses the module, and it is read through the SAME projection, marker collector and authority checks
# as a doctrine surface. A reader of their own - a raw substring count of one exact marker in a raw
# triple-quote span - certified a second authority, an exempted reference and a malformed exemption.
EXECUTABLE_SUBORDINATE_PATHS = (
    "scripts/crypto_core/validate_agent_os_v2.py",
    "tests/crypto_core/test_agent_os_v2_contract.py",
)
BLOCK_NEGATIVE_BOUNDARY = "EXECUTABLE_NEGATIVE_BOUNDARY"
EXECUTABLE_ROLE = "EXECUTABLE_SUBORDINATE"

# RESERVED authority syntax: everything the authority readers read. None of it may appear inside an exemption
# region, in any spelling, so historical or example prose describes an old block without reproducing it - and
# a reader that ever drifted back to the whole text would still find no authority inside a region.
RESERVED_AUTHORITY_SYNTAX = (
    ("a control-plane block marker", re.compile(r"<!--\s*[A-Za-z0-9_]+_(?:BEGIN|END)\s*-->", re.IGNORECASE)),
    ("a control-plane role or authority-reference marker", ROLE_MARKER_ANY_SPELLING_RE),
    ("a control-plane role or authority-reference marker", AUTHORITY_REF_ANY_SPELLING_RE),
    ("a canonical authority declaration", DECLARATION_ANY_SPELLING_RE),
    ("a routing-matrix ROUTE line", ROUTE_ANY_SPELLING_RE),
)

# The canonical independence vocabulary (agent_os_v2.md section 3.3). Its block has no other typed consumer,
# so without this contract its body could be emptied while the markers alone certified it.
INDEPENDENCE_STATES = (
    "SELF_AUDIT_ONLY_NOT_INDEPENDENT",
    "ORDINARY_INDEPENDENT_REVIEW",
    "PROTECTED_CLASS_C_AUDIT",
)
BLOCK_INDEPENDENCE_VOCABULARY = "INDEPENDENCE_VOCABULARY"
BLOCK_TESTED_REVISION_EVIDENCE = "TESTED_REVISION_EVIDENCE"

# An exemption marker in any other spelling - case, spacing, separators, surrounding text - is not read as a
# marker, so it would silently leave the region its author intended active. It fails instead.
EXEMPTION_MARKER_LIKE_RE = re.compile(
    r"<!--\s*(?:HISTORICAL[\s_-]*RECORD|EXAMPLE[\s_-]*ONLY)[\s_-]*(?:BEGIN|END)\s*-->", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# Small deterministic helpers
# ---------------------------------------------------------------------------


def _begin(name: str) -> str:
    return f"<!-- {name}_BEGIN -->"


def _end(name: str) -> str:
    return f"<!-- {name}_END -->"


# ONE FILE-ACCESS BOUNDARY (agent_os_v2.md section 15). Every file the control plane judges - its status, its
# listing in a host discovery location, its read and its decoding - is observed HERE and nowhere else. Decoding
# alone was not enough: `Path.is_file()` and `Path.exists()` re-raise a permission or I/O error, so an unreadable
# status escaped every entrypoint as a traceback, and `Path.glob` silently skipped a discovery directory it could
# not list, which accepted an unregistered host surface behind it. An observation has exactly four outcomes, and
# no filesystem failure is ever a traceback, a silent skip, or reported as missing.
FILE_PRESENT = "PRESENT"
FILE_MISSING = "MISSING"
FILE_NOT_REGULAR = "NOT_A_FILE"
FILE_UNREADABLE = "UNREADABLE"
UNREADABLE_FILE = "UNREADABLE_FILE"
UNREADABLE_TEXT = "UNREADABLE_TEXT"
# Exactly what pathlib itself treats as "does not exist". Every other OSError is an access failure, never absence.
_ABSENT_ERRNOS = frozenset({errno.ENOENT, errno.ENOTDIR, errno.EBADF, errno.ELOOP})
_ABSENT_WINERRORS = frozenset({21, 123, 1921})


class FileAccess(NamedTuple):
    """One observation of one file: ``text`` only from `read_file` when PRESENT, ``reason`` only when UNREADABLE."""

    status: str
    text: str | None = None
    reason: str | None = None


def _is_absence(exc: OSError) -> bool:
    return exc.errno in _ABSENT_ERRNOS or getattr(exc, "winerror", None) in _ABSENT_WINERRORS


def _os_reason(exc: OSError) -> str:
    return exc.strerror or type(exc).__name__


def file_status(path: Path) -> FileAccess:
    """The status of one path: PRESENT (a regular file), MISSING, NOT_A_FILE, or UNREADABLE with its reason."""
    try:
        mode = os.stat(path).st_mode
    except OSError as exc:
        if _is_absence(exc):
            return FileAccess(FILE_MISSING)
        return FileAccess(FILE_UNREADABLE, reason=f"{UNREADABLE_FILE}: status cannot be read ({_os_reason(exc)})")
    except ValueError:
        # A path the platform cannot even name (an embedded NUL) names no file, exactly as pathlib treats it.
        return FileAccess(FILE_MISSING)
    return FileAccess(FILE_PRESENT) if S_ISREG(mode) else FileAccess(FILE_NOT_REGULAR)


def read_file(path: Path) -> FileAccess:
    """Status, then read and decode as UTF-8 (a BOM is tolerated), as ONE observation.

    A failure after the status was read - the file vanished, became unreadable or became a directory - is
    UNREADABLE, never MISSING: the status already said the file was there, so the race fails closed.
    """
    observed = file_status(path)
    if observed.status != FILE_PRESENT:
        return observed
    try:
        return FileAccess(FILE_PRESENT, text=path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as exc:
        return FileAccess(
            FILE_UNREADABLE, reason=f"{UNREADABLE_TEXT}: not valid UTF-8 ({exc.reason} at byte {exc.start})"
        )
    except OSError as exc:
        return FileAccess(FILE_UNREADABLE, reason=f"{UNREADABLE_FILE}: cannot be read ({_os_reason(exc)})")


def discover_files(root: Path, pattern: str) -> tuple[list[str], list[str]]:
    """(regular files matching one discovery glob, access failures): a host location listed through the boundary.

    The fixed leading directories of the pattern are walked and every entry is matched by `host_glob_regex`, the
    same pathlib meaning of `*` and `**` the registries are classified with. A directory that cannot be listed and
    an entry whose status cannot be read are failures: an unlisted location cannot be proven free of unregistered
    surfaces. An absent location holds nothing.
    """
    segments = pattern.split("/")
    fixed: list[str] = []
    for segment in segments:
        if "*" in segment or "?" in segment:
            break
        fixed.append(segment)
    failures: list[str] = []
    candidates: list[str] = []
    if len(fixed) == len(segments):
        candidates.append(pattern)
    else:
        errors: list[OSError] = []
        for directory, _subdirectories, names in os.walk(root.joinpath(*fixed), onerror=errors.append):
            base = Path(directory).relative_to(root).as_posix()
            candidates.extend(name if base == "." else f"{base}/{name}" for name in names)
        for exc in errors:
            if _is_absence(exc):
                continue
            where = "/".join(fixed)
            if exc.filename is not None:
                listed = Path(os.fsdecode(exc.filename))
                where = listed.relative_to(root).as_posix() if listed.is_relative_to(root) else listed.as_posix()
            failures.append(
                f"host auto-discovery location cannot be listed: {where} (scanning {pattern}): {UNREADABLE_FILE}: "
                f"listing failed ({_os_reason(exc)}); an unlisted location cannot be proven free of unregistered "
                f"surfaces"
            )
    matcher = host_glob_regex(pattern)
    found: list[str] = []
    for rel in sorted(candidates):
        if not matcher.match(rel):
            continue
        observed = file_status(root / rel)
        if observed.status == FILE_PRESENT:
            found.append(rel)
        elif observed.status == FILE_UNREADABLE:
            failures.append(
                f"host auto-discovery surface status cannot be read: {rel} (matched {pattern}): {observed.reason}; "
                f"a surface whose status is unknown cannot be proven registered or absent"
            )
    return found, failures


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


class ActiveProjection(NamedTuple):
    """ONE structural reading of one control-plane surface (ACTIVE_CONTROL_PLANE_SURFACE_SEMANTICS).

    ``lines`` keeps every original line position: an exempt line - a region marker or anything inside a
    region - is None, so diagnostics keep their original line numbers, and ``text`` blanks exempt lines
    instead of dropping them. ``failures`` carries every structural violation found while building it.
    """

    failures: tuple[str, ...]
    lines: tuple[str | None, ...]

    @property
    def text(self) -> str:
        """The ACTIVE text. Nothing inside an exemption region can be read through it."""
        return "\n".join("" if line is None else line for line in self.lines)

    @property
    def numbered(self) -> list[tuple[int, str]]:
        """(1-based line number, text) for every ACTIVE line."""
        return [(lineno, line) for lineno, line in enumerate(self.lines, start=1) if line is not None]


def project_surface(rel: str, lines: list[str]) -> ActiveProjection:
    """The ONE exemption parser. Every consumer of a surface - authority readers and scans - uses its result.

    Region membership is decided by a TYPED STACK over the full text. A shared anonymous depth counter - one
    counter per region type, or worse one counter for all of them - lets one region type close another:
    opening HISTORICAL_RECORD, then EXAMPLE_ONLY, then closing HISTORICAL_RECORD would balance a naive
    counter while leaving the rest of the file exempt, which is exactly how a pinned value hides. A closer
    must therefore match the type on top. Failing shapes: a crossed pair in either direction, a stray
    closer, an unterminated region, and any nesting - the contract defines no nested combination.

    Three more rules keep the projection honest for every reader, present or future:

    * RESERVED authority syntax may not appear inside a region, so a region can never carry authority;
    * no exemption marker may open or close inside an active authority block, so a region can never remove
      part of a block from the projection while the block's own markers stay active;
    * an exemption marker in any other spelling fails, instead of silently leaving intended history active.

    Headings, section numbers and prose proximity are deliberately irrelevant: renaming or reformatting a
    heading cannot change which text is treated as active.
    """
    failures: list[str] = []
    stack: list[tuple[str, int]] = []
    open_blocks: dict[str, int] = {}
    projected: list[str | None] = []

    for lineno, raw_line in enumerate(lines, start=1):
        stripped = raw_line.strip()
        opened = next((name for name in EXEMPT_REGION_BLOCKS if stripped == _begin(name)), None)
        closed = next((name for name in EXEMPT_REGION_BLOCKS if stripped == _end(name)), None)

        if opened is not None or closed is not None:
            projected.append(None)
            if open_blocks:
                block, block_line = min(open_blocks.items(), key=lambda item: item[1])
                failures.append(
                    f"{rel}:{lineno}: exemption marker inside the active authority block {block} opened at "
                    f"line {block_line}; a region may never remove part of an authority block from the active "
                    f"projection"
                )
            if opened is not None:
                if stack:
                    failures.append(
                        f"{rel}:{lineno}: {opened}_BEGIN nested inside an open {stack[-1][0]} region; "
                        f"no nested exemption combination is defined"
                    )
                stack.append((opened, lineno))
            elif not stack:
                failures.append(f"{rel}:{lineno}: {closed}_END without a matching BEGIN")
            else:
                if stack[-1][0] != closed:
                    failures.append(
                        f"{rel}:{lineno}: crossed exemption regions - {closed}_END closes an open "
                        f"{stack[-1][0]} region opened at line {stack[-1][1]}"
                    )
                stack.pop()
            continue

        if EXEMPTION_MARKER_LIKE_RE.search(raw_line):
            failures.append(
                f"{rel}:{lineno}: malformed exemption marker; only an exact standalone marker line opens or "
                f"closes a region, and any other spelling would silently leave the intended region active"
            )
            projected.append(None if stack else raw_line)
            continue

        if stack:
            projected.append(None)
            region, region_line = stack[-1]
            reserved = next((label for label, pattern in RESERVED_AUTHORITY_SYNTAX if pattern.search(raw_line)), None)
            if reserved is not None:
                failures.append(
                    f"{rel}:{lineno}: {reserved} inside the {region} region opened at line {region_line}; "
                    f"authority syntax is reserved and never appears in an exemption region, so inert content "
                    f"can never satisfy active authority"
                )
            continue

        projected.append(raw_line)
        marker = BLOCK_MARKER_LINE_RE.match(stripped)
        if marker is not None:
            if marker.group(2) == "BEGIN":
                open_blocks.setdefault(marker.group(1), lineno)
            else:
                open_blocks.pop(marker.group(1), None)

    for name, lineno in stack:
        failures.append(
            f"{rel}: unterminated {name}_BEGIN at line {lineno} (the region would swallow the rest of the file)"
        )
    return ActiveProjection(tuple(failures), tuple(projected))


def exemption_scan(rel: str, lines: list[str]) -> tuple[list[str], list[tuple[int, str]]]:
    """(failures, active lines) from the ONE exemption parser."""
    projection = project_surface(rel, lines)
    return list(projection.failures), projection.numbered


def _docstring_expression(text: str) -> ast.Expr | None:
    """The module docstring statement as Python parses the module, or None (no docstring, or not Python)."""
    try:
        with warnings.catch_warnings():
            # A warning is not a verdict: the reading must not depend on the interpreter's warning filters.
            warnings.simplefilter("ignore")
            tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError):
        return None
    if not tree.body:
        return None
    first = tree.body[0]
    if not isinstance(first, ast.Expr) or not isinstance(first.value, ast.Constant):
        return None
    if not isinstance(first.value.value, str):
        return None
    return first


def module_docstring(text: str) -> str | None:
    """The module docstring as Python defines it - the first statement of the module - or None.

    The first triple-quoted span of the raw text is not the docstring: a module whose real docstring used other
    quotes and named a foreign authority was certified by a later string constant carrying the expected markers.
    """
    node = _docstring_expression(text)
    return None if node is None else str(node.value.value)


def read_projection(root: Path, rel: str) -> ActiveProjection | None:
    """Read and project one authority surface. None when the file is absent.

    A doctrine surface is projected whole. An executable subordinate is projected from its module docstring,
    padded so every line keeps its original number. A surface whose authority text cannot be obtained - a path
    that is not a regular file, a status, read or decode failure, or an executable with no docstring - is an EMPTY
    projection carrying that reason, so it fails structurally and no reader can find authority in it.
    """
    observed = read_file(root / rel)
    if observed.status == FILE_MISSING:
        return None
    if observed.status == FILE_NOT_REGULAR:
        return ActiveProjection((f"{rel}: not a regular file, so it carries no authority text",), ())
    if observed.text is None:
        return ActiveProjection((f"{rel}: {observed.reason}",), ())
    text = observed.text
    if rel not in EXECUTABLE_SUBORDINATE_PATHS:
        return project_surface(rel, text.splitlines())
    node = _docstring_expression(text)
    if node is None:
        return ActiveProjection(
            (f"{rel}: has no module docstring, as Python parses the module, to carry its role declaration",), ()
        )
    return project_surface(rel, [""] * (node.lineno - 1) + str(node.value.value).splitlines())


def surface_view(root: Path, ctx: dict[str, object], rel: str) -> ActiveProjection | None:
    """The one projection of a surface: built once per validation run and shared by every consumer."""
    views: dict[str, ActiveProjection | None] = ctx["views"]  # type: ignore[assignment]
    if rel not in views:
        views[rel] = read_projection(root, rel)
    return views[rel]


def authority_surfaces(ctx: dict[str, object]) -> list[tuple[str, str]]:
    """Every surface that carries authority markers, with the role it must declare.

    The registered doctrine surfaces and the executable subordinates. Every authority reader - roles and
    references, projection structure, declarations and routing rows - iterates THIS, so no kind of surface is
    judged by a reader of its own.
    """
    registered: list[tuple[str, str]] = list(ctx["surfaces"])  # type: ignore[arg-type]
    return registered + [(rel, EXECUTABLE_ROLE) for rel in EXECUTABLE_SUBORDINATE_PATHS]


def active_authority_failures(authority_text: str) -> list[str]:
    """Every canonical block exactly once in the ACTIVE projection, populated, and none undeclared.

    Marker presence was never authority: a block whose body was deleted, blanked or reduced to a comment
    still satisfied requiredness, because `block_span` only proves the markers are there. A required
    machine-readable block is its CONTENT, so an empty active body fails here for every block, and the two
    blocks with no other typed consumer get their own body contracts below.
    """
    lines = authority_text.splitlines()
    failures: list[str] = []
    for name in CANONICAL_AUTHORITY_BLOCKS:
        if block_span(lines, name) is None:
            failures.append(
                f"{CANONICAL}: {MISSING_ACTIVE_AUTHORITY}: {name} is not exactly one well-formed block in the "
                f"active authority; content inside HISTORICAL_RECORD or EXAMPLE_ONLY is inert and never "
                f"satisfies a requirement"
            )
        elif not block_lines(authority_text, name):
            failures.append(
                f"{CANONICAL}: {MISSING_ACTIVE_AUTHORITY}: {name} carries no active body; a required authority "
                f"block is its content, and markers alone declare nothing"
            )
    for lineno, line in enumerate(lines, start=1):
        marker = BLOCK_MARKER_LINE_RE.match(line.strip())
        if marker is not None and marker.group(1) not in CANONICAL_AUTHORITY_BLOCKS:
            failures.append(
                f"{CANONICAL}:{lineno}: {marker.group(1)} is not a declared canonical authority block; a block "
                f"the validator does not know is authority nothing requires"
            )
    return failures


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
    observed = read_file(root / CANONICAL)
    if observed.status == FILE_MISSING:
        failures.append(f"canonical authority missing: {CANONICAL}")
        return None
    if observed.status == FILE_NOT_REGULAR:
        failures.append(f"canonical authority is not a regular file: {CANONICAL}")
        return None
    if observed.text is None:
        failures.append(f"canonical authority unreadable: {CANONICAL}: {observed.reason}")
        return None
    raw_canonical = observed.text

    # The canonical structure is judged, and its ACTIVE projection derived, before any registry is read. No
    # authority reader below ever sees the raw text: an exempt block cannot satisfy anything.
    canonical = project_surface(CANONICAL, raw_canonical.splitlines())
    failures.extend(canonical.failures)
    authority_text = canonical.text
    failures.extend(active_authority_failures(authority_text))

    surfaces = parse_surface_registry(authority_text, BLOCK_ACTIVE_SURFACES)
    if surfaces is None:
        failures.append(f"{CANONICAL}: {BLOCK_ACTIVE_SURFACES} block missing or malformed")
        return None

    artifacts = parse_registry(authority_text, BLOCK_REQUIRED_ARTIFACTS)
    durable = parse_registry(authority_text, BLOCK_DURABLE_SURFACES)
    agnostic = parse_registry(authority_text, BLOCK_MODEL_AGNOSTIC)
    retired = parse_registry(authority_text, BLOCK_RETIRED_PATHS)
    volatile_pairs = parse_surface_registry(authority_text, BLOCK_VOLATILE_FIELDS)
    proof_paired = parse_surface_registry(authority_text, BLOCK_PROOF_PAIRED)
    host_globs = parse_registry(authority_text, BLOCK_HOST_DISCOVERY)
    historical_host = parse_surface_registry(authority_text, BLOCK_HISTORICAL_HOST)
    host_non_discovery = parse_registry(authority_text, BLOCK_HOST_NON_DISCOVERY)
    max_family = parse_registry(authority_text, BLOCK_MAX_FAMILY)
    for label, value in (
        (BLOCK_REQUIRED_ARTIFACTS, artifacts),
        (BLOCK_DURABLE_SURFACES, durable),
        (BLOCK_MODEL_AGNOSTIC, agnostic),
        (BLOCK_RETIRED_PATHS, retired),
        (BLOCK_VOLATILE_FIELDS, volatile_pairs),
        (BLOCK_PROOF_PAIRED, proof_paired),
        (BLOCK_HOST_DISCOVERY, host_globs),
        (BLOCK_HISTORICAL_HOST, historical_host),
        (BLOCK_HOST_NON_DISCOVERY, host_non_discovery),
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
        or historical_host is None
        or host_non_discovery is None
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
        (BLOCK_HISTORICAL_HOST, [p for p, _r in historical_host]),
        (BLOCK_HOST_NON_DISCOVERY, host_non_discovery),
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
        "authority_text": authority_text,
        "views": {CANONICAL: canonical},
        "surfaces": surfaces,
        "artifacts": artifacts,
        "durable": durable,
        "agnostic": agnostic,
        "retired": retired,
        "volatile_fields": [f for f, _c in volatile_pairs],
        "proof_paired": [f for f, _c in proof_paired],
        "proof_paired_classes": dict(proof_paired),
        "host_globs": host_globs,
        "historical_host": historical_host,
        "host_non_discovery": host_non_discovery,
        "max_family": max_family,
    }


def required_file_failures(root: Path, rel: str, label: str) -> list[str]:
    """A file required only to EXIST, judged by its status alone: its content is never read."""
    observed = file_status(root / rel)
    if observed.status == FILE_MISSING:
        return [f"{label} missing from the tree: {rel}"]
    if observed.status == FILE_NOT_REGULAR:
        return [f"{label} is not a regular file: {rel}"]
    if observed.status == FILE_UNREADABLE:
        return [f"{label} status cannot be read: {rel}: {observed.reason}"]
    return []


def _check_existence(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    # A doctrine surface's existence is judged on the SAME observation its content is read from, so no second
    # status can disagree with the read: a surface that vanishes in between still fails and is never skipped.
    for path, _role in surfaces:
        if surface_view(root, ctx, path) is None:
            failures.append(f"active doctrine surface missing from the tree: {path}")
    for path in ctx["artifacts"]:  # type: ignore[union-attr]
        failures.extend(required_file_failures(root, path, "required control-plane artifact"))
    for path in ctx["retired"]:  # type: ignore[union-attr]
        observed = file_status(root / path)
        if observed.status == FILE_UNREADABLE:
            failures.append(f"retired control-plane path cannot be proven absent: {path}: {observed.reason}")
        elif observed.status != FILE_MISSING:
            failures.append(f"retired control-plane path still present in the tree: {path}")

    # Anchored on a literal constant, NOT on the mutable required-artifact registry, so removing the
    # registry entry does not remove the requirement.
    if file_status(root / BOOTSTRAP_ORACLE_PATH).status == FILE_MISSING:
        failures.append(
            f"independent contract oracle missing: {BOOTSTRAP_ORACLE_PATH} "
            f"(required by the external bootstrap anchor, independently of any registry entry)"
        )
    else:
        failures.extend(required_file_failures(root, BOOTSTRAP_ORACLE_PATH, "independent contract oracle"))


def _check_roles(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Every authority surface - doctrine and executable alike - through the one marker reading."""
    for path, expected_role in ctx["surfaces"]:  # type: ignore[union-attr]
        if expected_role not in ROLE_VOCABULARY:
            failures.append(f"{path}: role {expected_role} is not in the role vocabulary")

    canonical_count = 0
    for path, expected_role in authority_surfaces(ctx):
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        found, role = authority_marker_failures(path, view.text, expected_role)
        failures.extend(found)
        if role == "CANONICAL_AUTHORITY":
            canonical_count += 1
            if path != CANONICAL:
                failures.append(f"{path}: only {CANONICAL} may declare CANONICAL_AUTHORITY")

    if canonical_count != 1:
        failures.append(f"expected exactly one CANONICAL_AUTHORITY surface, found {canonical_count}")


def declaration_sites(root: Path, ctx: dict[str, object], failures: list[str]) -> dict[str, list[tuple[str, str]]]:
    """Every ACTIVE canonical declaration, recognized structurally: name -> [(surface, value)].

    Anchoring the name at column zero meant ordinary Markdown indentation hid a rival declaration from the
    singularity check, so a subordinate surface could declare merge, sizing, family, effort or max-effort
    authority invisibly. Recognition now uses the one declaration matcher, and the value must still be the
    single token the contract compares.
    """
    sites: dict[str, list[tuple[str, str]]] = {name: [] for name in DECLARATION_NAMES}
    for path, _role in authority_surfaces(ctx):
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
            match = DECLARATION_LINE_RE.match(line)
            if match is None:
                continue
            value = match.group("rest").strip()
            if len(value.split()) != 1:
                failures.append(
                    f"{path}:{lineno}: {match.group('name')} declares {value!r}; a canonical declaration "
                    f"carries exactly one value token"
                )
                continue
            sites[match.group("name")].append((path, value))
    return sites


def marker_values(rel: str, active_text: str, marker: str) -> tuple[list[str], list[str]]:
    """(values, failures) for every ACTIVE marker of one kind: the ONE marker collector of the control plane.

    Every marker the any-spelling recognizer finds counts, and each is read by the exact form. A marker the exact
    form cannot read is refused as malformed rather than ignored, so a second role or authority reference can
    never hide behind a spelling.
    """
    recognizer, reader = MARKER_GRAMMAR[marker]
    values: list[str] = []
    failures: list[str] = []
    for hit in recognizer.finditer(active_text):
        exact = reader.match(active_text, hit.start())
        if exact is None:
            lineno = active_text.count("\n", 0, hit.start()) + 1
            failures.append(
                f"{rel}:{lineno}: malformed {marker} marker; a marker is read in its one exact spelling, and "
                f"any other spelling is refused rather than silently ignored"
            )
        else:
            values.append(exact.group("value"))
    return values, failures


def authority_marker_failures(rel: str, active_text: str, expected_role: str) -> tuple[list[str], str | None]:
    """ONE reading of a surface's role and authority reference: (failures, the single role read, or None)."""
    roles, failures = marker_values(rel, active_text, ROLE_MARKER)
    role = roles[0] if len(roles) == 1 else None
    if role is None:
        failures.append(f"{rel}: expected exactly one {ROLE_MARKER} marker, found {len(roles)}")
    elif role != expected_role:
        failures.append(f"{rel}: {ROLE_MARKER} marker is {role} but the registry declares {expected_role}")
    failures.extend(authority_reference_failures(rel, active_text))
    return failures, role


def authority_reference_failures(rel: str, active_text: str) -> list[str]:
    """Exactly one ACTIVE authority reference per subordinate surface, and it resolves to the canonical file.

    Presence of the expected marker was never uniqueness: a surface could keep it and add a second marker
    naming another authority, so the gate certified this file as exclusive while an active adapter
    advertised a rival. Markers are collected structurally - indentation and inner spacing are irrelevant -
    and the canonical authority itself references no other authority.
    """
    targets, failures = marker_values(rel, active_text, AUTHORITY_REF_MARKER)
    if rel == CANONICAL:
        if targets:
            failures.append(
                f"{rel}: carries {len(targets)} CONTROL_PLANE_AUTHORITY_REF marker(s); the canonical "
                f"authority references no other authority"
            )
        return failures
    if not targets:
        failures.append(f"{rel}: missing CONTROL_PLANE_AUTHORITY_REF marker to {CANONICAL}")
    elif len(targets) != 1:
        failures.append(
            f"{rel}: expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found {len(targets)}; a "
            f"subordinate surface names exactly one authority"
        )
    for target in targets:
        if target != CANONICAL:
            failures.append(
                f"{rel}: CONTROL_PLANE_AUTHORITY_REF names {target!r}, but the canonical authority is {CANONICAL}"
            )
    return failures


def _check_declarations(root: Path, ctx: dict[str, object], failures: list[str]) -> frozenset[str]:
    """Authority declarations are singular and canonical-only, at any indentation."""
    max_effort_classes: frozenset[str] = frozenset()
    declared = declaration_sites(root, ctx, failures)

    for name, expected_value in CANONICAL_DECLARATIONS:
        sites = declared[name]
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

    sites = declared["MAX_EFFORT_CLASSES"]
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
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]

    # 1) No ROUTE: line may exist outside the canonical routing-matrix block. A ROUTE line inside an
    # exemption region is reserved syntax and already failed in the projection, so only active lines count.
    canonical_lines = authority_text.splitlines()
    span = block_span(canonical_lines, BLOCK_ROUTING_MATRIX)
    if span is None:
        failures.append(f"{CANONICAL}: {BLOCK_ROUTING_MATRIX} block missing or malformed")
        return
    allowed = set(range(span[0], span[1]))

    for path, _role in authority_surfaces(ctx):
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
            if not ROUTE_LINE_RE.match(line):
                continue
            if path != CANONICAL or lineno - 1 not in allowed:
                failures.append(
                    f"{path}:{lineno}: ROUTE line outside the canonical routing matrix "
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
    contract_rows, problems = parse_columns(authority_text, BLOCK_FAMILY_CONTRACT, 4)
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
    lane_rows, lane_problems = parse_columns(authority_text, BLOCK_LANE_CAPABILITY, 3)
    failures.extend(lane_problems)
    if lane_rows is not None:
        # DUTY, not mutation authority. READ_ONLY conflates review, architecture, prompt
        # architecture, protected Class-C and external research, so a lane trusted for one of them
        # was trusted for all five - which is how XR could be routed to the protected lane. A family
        # is exactly the thing a lane is or is not trusted with.
        lanes: dict[str, tuple[str, set[str]]] = {}
        for lane_name, model_id, families_raw in lane_rows:
            if lane_name in lanes:
                failures.append(f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} declares lane {lane_name!r} more than once")
            families = {f.strip() for f in families_raw.split(",") if f.strip()}
            for family in sorted(families - set(ROUTE_CLASSES)):
                failures.append(
                    f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} lane {lane_name!r} declares unknown route family {family}"
                )
            lanes[lane_name] = (model_id, families)

        for cls, _intents, lane, model_id, _effort, _mutation in parsed:
            declared_lane = lanes.get(lane)
            if declared_lane is None:
                failures.append(
                    f"{CANONICAL}: class {cls} routes to lane {lane!r}, which {BLOCK_LANE_CAPABILITY} "
                    f"does not declare; an undeclared lane has no proven identity and no proven capability"
                )
                continue
            declared_model, declared_families = declared_lane
            if model_id != declared_model:
                failures.append(
                    f"{CANONICAL}: class {cls} routes lane {lane!r} with model id {model_id!r}, but "
                    f"that lane's canonical identity is {declared_model!r}"
                )
            if cls not in declared_families:
                failures.append(
                    f"{CANONICAL}: class {cls} asks lane {lane!r} to carry {cls} work, but that lane "
                    f"is trusted only with {sorted(declared_families)}"
                )

        for lane_name in sorted(set(lanes) - {row[2] for row in parsed}):
            failures.append(
                f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} declares lane {lane_name!r} but no route uses "
                f"it, so the declared capability is unreachable"
            )
        # No dead reserve: a family a lane is trusted with must actually be routed to it.
        routed_pairs = {(row[2], row[0]) for row in parsed}
        for lane_name, (_model, families) in sorted(lanes.items()):
            for family in sorted(families):
                if (lane_name, family) not in routed_pairs:
                    failures.append(
                        f"{CANONICAL}: {BLOCK_LANE_CAPABILITY} trusts lane {lane_name!r} with {family} "
                        f"but no {family} route uses that lane, so the declared duty is unreachable"
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
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]
    for name, expected in (
        (BLOCK_EFFORT_ENUM, list(EFFORT_ENUM)),
        (BLOCK_PROMPT_FIELDS, list(PROMPT_COMPILER_FIELDS)),
        (BLOCK_EVIDENCE_CLASSES, list(MODEL_EVIDENCE_CLASSES)),
        (BLOCK_WORK_CONTRACT, list(WORK_RETURN_CONTRACT)),
        (BLOCK_CAPACITY_STATES, list(PROVIDER_CAPACITY_STATES)),
        (BLOCK_ROUTING_MODES, list(CAPACITY_ROUTING_MODES)),
        (BLOCK_INTENT_FIRST, list(INTENT_FIRST_ROUTING_RULES)),
    ):
        found = block_lines(authority_text, name)
        if found is None:
            failures.append(f"{CANONICAL}: {name} block missing or malformed")
            continue
        if found != expected:
            failures.append(f"{CANONICAL}: {name} block must be exactly {expected} in order, got {found}")


def _check_unconsumed_block_bodies(ctx: dict[str, object], failures: list[str]) -> None:
    """Body contracts for the two required blocks no other typed parser reads.

    Every other canonical block is already content-checked by the parser that consumes it - a registry, a
    fixed block, a column table or the boundary sentence. These two were required by their markers alone,
    so their declared bodies get the minimum deterministic contract canonical doctrine already states:
    the exact independence vocabulary (section 3.3) and the exact tested-revision evidence bundle
    (section 17.2). Nothing new is invented here.
    """
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]

    rows = parse_surface_registry(authority_text, BLOCK_INDEPENDENCE_VOCABULARY)
    if rows is None:
        failures.append(f"{CANONICAL}: {BLOCK_INDEPENDENCE_VOCABULARY} block missing or malformed")
    else:
        # An entry with no sentence after the separator is already malformed to parse_surface_registry,
        # so the states themselves are what this contract adds.
        states = [state for state, _description in rows]
        if states != list(INDEPENDENCE_STATES):
            failures.append(
                f"{CANONICAL}: {BLOCK_INDEPENDENCE_VOCABULARY} must declare exactly "
                f"{list(INDEPENDENCE_STATES)} in order, got {states}"
            )

    declared = block_lines(authority_text, BLOCK_TESTED_REVISION_EVIDENCE)
    expected = [f"- {field}" for field in TESTED_REVISION_EVIDENCE_FIELDS]
    if declared is None:
        failures.append(f"{CANONICAL}: {BLOCK_TESTED_REVISION_EVIDENCE} block missing or malformed")
    elif declared != expected:
        failures.append(
            f"{CANONICAL}: {BLOCK_TESTED_REVISION_EVIDENCE} must declare exactly {expected} in order, got {declared}"
        )


def _check_single_prompt_template(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Exactly one top-level prompt template exists, and it lives in the canonical authority."""
    surfaces: list[tuple[str, str]] = ctx["surfaces"]  # type: ignore[assignment]
    holders = []
    for path, _role in surfaces:
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        if _begin(BLOCK_PROMPT_FIELDS) in view.text:
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
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]
    canonical_flat = _normalize_ws(authority_text)
    for token in REQUIRED_CANONICAL_TOKENS:
        if _normalize_ws(token) not in canonical_flat:
            failures.append(f"{CANONICAL}: required contract token missing: {token}")

    index_path = "docs/crypto_core/continuity/CONTINUITY_INDEX.md"
    index_view = surface_view(root, ctx, index_path)
    if index_view is not None:
        for token in REQUIRED_CONTINUITY_INDEX_TOKENS:
            if token not in index_view.text:
                failures.append(f"{index_path}: required continuity token missing: {token}")

    shim_path = ".github/copilot-instructions.md"
    shim_view = surface_view(root, ctx, shim_path)
    if shim_view is not None and "INACTIVE_UNAVAILABLE" not in shim_view.text:
        failures.append(f"{shim_path}: must declare INACTIVE_UNAVAILABLE")


def _check_marker_regions(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Structural failures of every authority surface's one projection, doctrine and executable alike.

    The canonical authority's own were reported by _check_registries, before any registry was read from it.
    An unreadable surface, or an executable without a docstring, reports its reason here too.
    """
    for path, _role in authority_surfaces(ctx):
        if path == CANONICAL:
            continue
        view = surface_view(root, ctx, path)
        if view is not None:
            failures.extend(view.failures)


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
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
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
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
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
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
            for token in PROHIBITED_SIZING_TOKENS:
                if token in line:
                    failures.append(
                        f"{path}:{lineno}: retired PR-sizing heuristic '{token}' "
                        "(PR_SIZING_AUTHORITY is SEMANTIC_CLOSURE_ONLY)"
                    )


def _check_executable_subordinates(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """Both executables exist and reproduce the exact canonical boundary in their ACTIVE module docstring.

    Their role marker, authority reference, exemption structure, declarations and routing rows are judged with
    every other authority surface, over the one projection of the docstring (`authority_surfaces`). Only the
    module DOCSTRING is authority text. This module also mentions these marker strings in its own code, and
    scanning the whole file would let it satisfy the check trivially - a presence check that cannot fail is not
    a check.

    This proves the declaration is present. It does NOT and cannot prove that no differently-worded
    self-enforcement claim appears elsewhere in the prose; that is the independent semantic audit's
    responsibility (section 20.1).
    """
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]
    declared = block_lines(authority_text, BLOCK_NEGATIVE_BOUNDARY)
    if declared is None or len([ln for ln in declared if ln.strip()]) != 1:
        failures.append(f"{CANONICAL}: {BLOCK_NEGATIVE_BOUNDARY} must declare exactly one boundary sentence")
        return
    boundary = declared[0].strip()

    for rel in EXECUTABLE_SUBORDINATE_PATHS:
        view = surface_view(root, ctx, rel)
        if view is None:
            failures.append(f"executable surface missing: {rel}")
            continue
        if _normalize_ws(boundary) not in _normalize_ws(view.text):
            failures.append(f"{rel}: does not reproduce the canonical {BLOCK_NEGATIVE_BOUNDARY} declaration verbatim")


# HOST_DISCOVERY_CLOSED_WORLD (agent_os_v2.md section 20). A historical host surface may remain only in a
# role that cannot apply it.
HISTORICAL_HOST_ROLES = ("NON_APPLYING",)

# NON_APPLYING_FRONT_MATTER_CONTRACT (agent_os_v2.md section 20). NON_APPLYING is POSITIVE PROOF. Matching one
# known unsafe spelling - a whole-line `alwaysApply: true` - certified `true # comment`, a quoted "true", yes,
# a missing flag, no front matter at all and a `globs` auto-attach as non-applying. The contract is a bounded
# SAFE SUBSET, deliberately not a YAML parser: whatever falls outside it loses the status, and the validator
# never decides whether an unfamiliar spelling would actually apply.
CURSOR_RULE_LOCATION = ".cursor/rules/**/*.mdc"
FRONT_MATTER_DELIMITER = "---"
CURSOR_RULE_SAFE_KEYS = ("description", "alwaysApply")
CURSOR_RULE_NON_APPLYING_VALUE = "false"
FRONT_MATTER_ENTRY_RE = re.compile(r"\A(?P<key>[A-Za-z][A-Za-z0-9_-]*): +(?P<value>\S(?:.*\S)?) *\Z")
YAML_PLAIN_SCALAR_INDICATORS = frozenset("-?:,[]{}#&*!|>'\"%@`")


def host_glob_regex(pattern: str) -> re.Pattern[str]:
    """One declared discovery glob as an anchored path regex, with pathlib's meaning of `**`.

    Registry entries are paths, not files on disk, so classifying them needs the same matching the
    filesystem scan uses: `**` is zero or more whole directories, `*` and `?` never cross a `/`.
    """
    parts: list[str] = []
    for segment in pattern.split("/"):
        if segment == "**":
            parts.append("(?:[^/]+/)*")
            continue
        body = "".join("[^/]*" if ch == "*" else "[^/]" if ch == "?" else re.escape(ch) for ch in segment)
        parts.append(body + "/")
    return re.compile("^" + "".join(parts).rstrip("/") + "$")


def _front_matter_structure_character(entry: str) -> bool:
    """A control, format or line-separator code point, which a host may read as structure."""
    return any(unicodedata.category(ch)[0] == "C" or unicodedata.category(ch) in ("Zl", "Zp") for ch in entry)


def cursor_rule_non_applying_failures(rel: str, text: str) -> list[str]:
    """The Cursor rule contract: proven never applied automatically, or not NON_APPLYING at all.

    Holds exactly when the text opens with a `---` line and the next `---` line closes the front matter;
    every line between them is one plain `key: value` entry - no indentation, comment, quoting, anchor, tag,
    flow syntax, control or line-separator character; no key repeats; the only keys are `description` and
    `alwaysApply`, so `globs` - which attaches a rule by file pattern - or any other key fails; `alwaysApply`
    is present with exactly the bare lowercase value `false`; and `description`, when present, is a plain
    scalar.
    """
    prefix = f"{rel}: NON_APPLYING is not proven -"
    body = text[1:] if text.startswith("\ufeff") else text
    lines = body.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines[0] != FRONT_MATTER_DELIMITER:
        return [f"{prefix} the file does not open with a --- front-matter line, so nothing states it never applies"]
    if FRONT_MATTER_DELIMITER not in lines[1:]:
        return [f"{prefix} its front matter never closes"]
    failures: list[str] = []
    seen: dict[str, int] = {}
    for lineno, entry in enumerate(lines[1 : lines.index(FRONT_MATTER_DELIMITER, 1)], start=2):
        match = FRONT_MATTER_ENTRY_RE.match(entry)
        if match is None or _front_matter_structure_character(entry):
            failures.append(
                f"{prefix} front-matter line {lineno} is not one plain key: value entry of the bounded contract "
                f"(no indentation, comment, quoting, flow syntax, control or line-separator character)"
            )
            continue
        key, value = match.group("key"), match.group("value")
        if key in seen:
            failures.append(f"{prefix} front-matter key {key!r} repeats (lines {seen[key]} and {lineno})")
            continue
        seen[key] = lineno
        if key not in CURSOR_RULE_SAFE_KEYS:
            failures.append(
                f"{prefix} front-matter key {key!r} is not a proven-safe key; only {list(CURSOR_RULE_SAFE_KEYS)} "
                f"are, and globs would attach the rule by file pattern"
            )
        elif key == "alwaysApply" and value != CURSOR_RULE_NON_APPLYING_VALUE:
            failures.append(
                f"{prefix} it declares alwaysApply: {value}; only the bare lowercase value "
                f"{CURSOR_RULE_NON_APPLYING_VALUE} proves a host will not apply the rule to every request"
            )
        elif key == "description" and (
            value[0] in YAML_PLAIN_SCALAR_INDICATORS or ": " in value or " #" in value or value.endswith(":")
        ):
            failures.append(
                f"{prefix} description is not a plain scalar; indicator, mapping or comment syntax can "
                f"restructure the front matter a host reads"
            )
    if "alwaysApply" not in seen:
        failures.append(f"{prefix} alwaysApply is absent; an unstated flag never proves the rule is not applied")
    return failures


# Host locations for which a non-application contract exists. A NON_APPLYING surface anywhere else is a label
# with nothing behind it.
NON_APPLYING_CONTRACTS = ((CURSOR_RULE_LOCATION, cursor_rule_non_applying_failures),)


def non_applying_failures(rel: str, text: str) -> list[str]:
    """ONE answer to "is this host-discoverable surface provably non-applying?", shared by every consumer."""
    for location, contract in NON_APPLYING_CONTRACTS:
        if host_glob_regex(location).match(rel):
            return contract(rel, text)
    return [
        f"{rel}: NON_APPLYING is not proven - no non-application contract exists for its host location, and a "
        f"label never proves that a host will not load a surface"
    ]


def _check_host_discovery(root: Path, ctx: dict[str, object], failures: list[str]) -> None:
    """A host auto-discovery location holds registered, historical non-applying, or no surfaces.

    Registry membership decides AUTHORITY; it does not decide what a host LOADS. The declared
    locations are derived from this control plane's own registries, and the declaration is closed in
    both directions: every path a registry names inside a host configuration directory must lie in a
    declared location or be declared non-discoverable, so no registered or retired surface can sit in
    a host root nobody scans. The scan claims nothing about host conventions no registry names. A
    historical surface is non-applying only when the NON_APPLYING contract for its location holds.
    """
    globs: list[str] = list(ctx["host_globs"])  # type: ignore[arg-type]
    historical: list[tuple[str, str]] = list(ctx["historical_host"])  # type: ignore[arg-type]
    non_discovery: list[str] = list(ctx["host_non_discovery"])  # type: ignore[arg-type]
    historical_paths = {path for path, _role in historical}
    registered = (
        {path for path, _role in ctx["surfaces"]}  # type: ignore[union-attr]
        | set(ctx["artifacts"])  # type: ignore[arg-type]
        | historical_paths
    )

    discovered: set[str] = set()
    for pattern in globs:
        found, unlisted = discover_files(root, pattern)
        failures.extend(unlisted)
        discovered.update(found)
        for rel in found:
            if rel in registered:
                continue
            failures.append(
                f"host auto-discovery surface present but not registered: {rel} "
                f"(matched {pattern}; a discoverable path must be registered with a safe role or absent)"
            )

    matchers = [(pattern, host_glob_regex(pattern)) for pattern in globs]

    def locations(path: str) -> list[str]:
        return [pattern for pattern, matcher in matchers if matcher.match(path)]

    for path, role in historical:
        if role not in HISTORICAL_HOST_ROLES:
            failures.append(
                f"{CANONICAL}: historical host surface {path} carries role {role!r}; the only role is "
                f"{list(HISTORICAL_HOST_ROLES)}"
            )
        if not locations(path):
            failures.append(
                f"{CANONICAL}: historical host surface {path} lies in no declared discovery location, so "
                f"its allowance is not scoped to a scanned host root"
            )
        observed = read_file(root / path)
        if observed.status == FILE_UNREADABLE:
            failures.append(
                f"{path}: {observed.reason}; an unreadable host surface proves nothing, so it is not non-applying"
            )
            continue
        if observed.text is None and path in discovered:
            failures.append(
                f"{path}: discovered as a present file but no longer readable as one; its NON_APPLYING proof was "
                f"never read"
            )
            continue
        if observed.text is None or role != "NON_APPLYING":
            continue
        failures.extend(non_applying_failures(path, observed.text))

    host_directories = {pattern.split("/", 1)[0] for pattern in globs if "/" in pattern}
    named = registered | set(ctx["retired"])  # type: ignore[arg-type]
    for path in sorted(named):
        directory = path.split("/", 1)[0]
        if directory not in host_directories:
            continue
        inside = locations(path)
        declared = path in non_discovery
        if inside and declared:
            failures.append(
                f"{CANONICAL}: {path} is declared in {BLOCK_HOST_NON_DISCOVERY} but lies in the discovery "
                f"location {inside[0]}"
            )
        elif not inside and not declared:
            failures.append(
                f"{CANONICAL}: {path} is named by a registry inside host directory {directory}/ but lies in no "
                f"declared discovery location and is not declared in {BLOCK_HOST_NON_DISCOVERY}; a known "
                f"host root cannot be left unscanned"
            )
    for path in non_discovery:
        if path not in named:
            failures.append(f"{CANONICAL}: {BLOCK_HOST_NON_DISCOVERY} declares {path}, which no registry names")
        elif path.split("/", 1)[0] not in host_directories:
            failures.append(
                f"{CANONICAL}: {BLOCK_HOST_NON_DISCOVERY} declares {path}, which is outside every host directory"
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
    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]
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
    for row in block_lines(authority_text, BLOCK_ROUTING_MATRIX) or []:
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
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
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
        view = surface_view(root, ctx, path)
        if view is None:
            continue
        for lineno, line in view.numbered:
            for token in PROHIBITED_RATIO_TOKENS:
                if token in line:
                    failures.append(
                        f"{path}:{lineno}: provider ratio encoded as an enforced constraint: {token} "
                        f"(a ratio is a planning SLO only, never a routing or correctness invariant)"
                    )

    authority_text: str = ctx["authority_text"]  # type: ignore[assignment]
    states = block_lines(authority_text, BLOCK_CAPACITY_STATES) or []
    if "UNKNOWN" not in states:
        failures.append(f"{CANONICAL}: provider capacity must admit UNKNOWN rather than a fabricated value")
    modes = block_lines(authority_text, BLOCK_ROUTING_MODES) or []
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
EFFORT_WAIVER_STATUSES = ("NOT_APPLICABLE", "NOT_GRANTED", "HUMAN_GRANTED")


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
    "Every proof-paired field is also bound to its TARGET by the PROOF_TARGET_BINDINGS registry "
    "(agent_os_v2.md section 20): a PROVEN observation whose target is not PROVEN is rejected, and a "
    "completed gate's evidence key must name the proven head_sha or head_tree. "
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
                    "unchanged, so the key must name this manifest's proven head_sha or head_tree; a key "
                    "naming another revision is invalidated evidence."
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

EFFORT_MISMATCH_WAIVER_GRAMMAR = _object(
    {
        "status": _enum(EFFORT_WAIVER_STATUSES),
        "evidence": _op("The exact task-specific HUMAN waiver, verbatim. Null unless status is HUMAN_GRANTED."),
    },
    required=("status", "evidence"),
    description=(
        "EFFORT_MISMATCH_WAIVER (agent_os_v2.md section 4.1). A human may waive an observed effort "
        "mismatch for a SPECIFIC task, and this block records that without erasing the mismatch. "
        "NOT_APPLICABLE: no effort mismatch is truthfully recorded, evidence null. NOT_GRANTED: a "
        "CONTRADICTED effort mismatch is recorded and no human waived it, evidence null, and the task "
        "stops. HUMAN_GRANTED: a CONTRADICTED effort mismatch is recorded and a human waived it for this "
        "task, evidence is the exact waiver. A waiver never changes requested_effort or "
        "observed_effort and exists only while they differ. It is not authority: it grants no merge, "
        "waives no T4 gate, repairs no model mismatch or fallback and cannot make an illegal requested "
        "effort legal. The validator checks representation only; live controller evidence must prove a "
        "human actually issued it."
    ),
)

MODEL_RUNTIME_GRAMMAR = _object(
    {
        "model_id": _op(),
        "model_requested": _op(),
        "model_actual": _op(),
        "model_evidence_source": _enum(MODEL_EVIDENCE_CLASSES),
        "requested_effort": _enum(EFFORT_VALUES),
        "observed_effort": _enum(EFFORT_VALUES),
        "effort_evidence_source": _enum(MODEL_EVIDENCE_CLASSES),
        "effort_mismatch_waiver": EFFORT_MISMATCH_WAIVER_GRAMMAR,
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
        "effort_mismatch_waiver",
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
        "host_setting_raw stores the operator UI choice verbatim without inventing an API mapping. "
        "Effort is RELATIONAL like identity: under an execution-proving class an observed_effort that "
        "differs from requested_effort is CONTRADICTED, CONTRADICTED requires a real effort conflict, "
        "and effort_mismatch_waiver records whether a human waived that exact mismatch without ever "
        "rewriting the true observed effort. Execution proof is TARGET-BOUND: RUNTIME_TELEMETRY, "
        "USER_ATTESTED_UI_SELECTION and CONTRADICTED need a required identity (model_id, or "
        "model_requested where no API identity applies) in the identity dimension and a requested_effort "
        "in the effort dimension, because an observation with nothing to compare against proves "
        "nothing."
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
        "Facts that stopped being true during this session and must not be reused. REQUIRED and never "
        "omitted: an absent list cannot be distinguished from 'the producer never said', which would "
        "leave stale completed-gate evidence quietly reusable. An EMPTY list is the truthful way to "
        "say nothing was invalidated, and is always valid - never fabricate an entry to satisfy "
        "shape. It is deliberately NOT proof-paired: this is a session narrative rather than an "
        "external fact, so pairing it would be ceremony, not proof.",
    )
    fields["model_runtime"] = MODEL_RUNTIME_GRAMMAR
    fields["authorization"] = AUTHORIZATION_GRAMMAR
    required.extend(("invalidations", "model_runtime", "authorization"))
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
    "evidence",
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


# --- STRICT_JSON_EVIDENCE_BOUNDARY ------------------------------------------------------------
#
# `json.loads` keeps the LAST occurrence of a repeated member name. A compiled manifest repeating
# `head_sha` - an invalid value first, a valid one last - was therefore certified PASS while a reader
# taking the first occurrence saw a different document, and a committed schema could hide a
# duplicate whose last value happened to equal the generated one. It also accepts NaN, Infinity and
# a numeral that overflows to infinity, none of which is JSON. Every Agent OS evidence or
# specification document is parsed HERE, once, and anything ambiguous or non-JSON is refused before
# any grammar, relation or comparison reads it. Nothing is ever resolved by picking one occurrence.

STRICT_JSON_REJECTED = "STRICT_JSON_REJECTED"
STRICT_JSON_NAME_LIMIT = 80


class StrictJsonError(ValueError):
    """A document the strict JSON evidence boundary refuses to interpret."""


def _strict_json_name(name: str) -> str:
    """A member name escaped to ASCII and bounded, so a diagnostic never carries bulk content."""
    shown = ascii(name[:STRICT_JSON_NAME_LIMIT])
    return shown + "..." if len(name) > STRICT_JSON_NAME_LIMIT else shown


def _strict_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    # The hook receives DECODED names, so an escaped spelling of an earlier name IS that name.
    members: dict[str, object] = {}
    for name, value in pairs:
        if name in members:
            raise StrictJsonError(f"duplicate object member name {_strict_json_name(name)}")
        members[name] = value
    return members


def _strict_json_constant(token: str) -> object:
    raise StrictJsonError(f"non-finite number {token} is not JSON")


def _strict_json_float(token: str) -> float:
    value = float(token)
    if abs(value) == float("inf"):
        raise StrictJsonError(f"number {token[:STRICT_JSON_NAME_LIMIT]} overflows to a non-finite value")
    return value


def load_strict_json(text: str) -> object:
    """Parse one Agent OS JSON document, or raise StrictJsonError. Never returns an ambiguous value.

    Refused: a repeated object member name at any depth, including one spelled with escapes; NaN,
    Infinity, -Infinity and a numeral that overflows to infinity; nesting too deep to evaluate; and
    malformed JSON. A parse that cannot complete is a refusal, never a traceback.
    """
    try:
        return json.loads(
            text,
            object_pairs_hook=_strict_json_object,
            parse_constant=_strict_json_constant,
            parse_float=_strict_json_float,
        )
    except StrictJsonError:
        raise
    except RecursionError:
        raise StrictJsonError("nesting is too deep to evaluate") from None
    except ValueError as exc:
        raise StrictJsonError(f"malformed JSON ({exc})") from None


def load_strict_json_file(path: Path | str) -> object:
    """Read a JSON file through the one file-access boundary and parse it through `load_strict_json`."""
    observed = read_file(Path(path))
    if observed.status == FILE_MISSING:
        raise StrictJsonError("cannot be read as UTF-8 text (missing: not an existing file)")
    if observed.status == FILE_NOT_REGULAR:
        raise StrictJsonError("cannot be read as UTF-8 text (not a regular file)")
    if observed.text is None:
        raise StrictJsonError(f"cannot be read as UTF-8 text ({observed.reason})")
    return load_strict_json(observed.text)


def committed_json(root: Path, rel: str, failures: list[str]) -> tuple[str, object] | None:
    """A committed Agent OS JSON artifact through the text and strict JSON boundaries: (raw text, value).

    None after exactly one structured failure - missing, unreadable or refused - so no committed document can
    reach a comparison or a relation, or raise past the gate, without a verdict.
    """
    observed = read_file(root / rel)
    if observed.status == FILE_MISSING:
        failures.append(f"{rel}: missing")
        return None
    if observed.status == FILE_NOT_REGULAR:
        failures.append(f"{rel}: {STRICT_JSON_REJECTED}: not a regular file")
        return None
    if observed.text is None:
        failures.append(f"{rel}: {STRICT_JSON_REJECTED}: {observed.reason}")
        return None
    raw = observed.text
    try:
        return raw, load_strict_json(raw)
    except StrictJsonError as exc:
        failures.append(f"{rel}: {STRICT_JSON_REJECTED}: {exc}")
        return None


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


# The classes that assert an execution was OBSERVED. Under these, a recorded identity is a claim
# about what actually ran, so it must equal the identity the route required.
EXECUTION_PROVING_CLASSES = frozenset({"RUNTIME_TELEMETRY", "USER_ATTESTED_UI_SELECTION"})

# TARGET_BOUND_EXECUTION_PROOF (agent_os_v2.md section 4.1). Every class that claims an execution was
# OBSERVED in a dimension - including the class that claims the observation CONTRADICTED the request -
# is a comparison, and a comparison needs a target. Without one the observation proves nothing.
TARGET_BOUND_CLASSES = EXECUTION_PROVING_CLASSES | {"CONTRADICTED"}

# PROOF_TARGET_BINDINGS (agent_os_v2.md section 20). Every proof-paired field declares what it is an
# observation OF. SELF marks an identity; NONE marks a field with no revision or pull-request target.
# A PROVEN observation whose target is not PROVEN observes nothing identified.
PROOF_TARGET_SELF = "SELF"
PROOF_TARGET_NONE = "NONE"
PROOF_TARGET_BINDINGS: dict[str, str] = {
    "branch": PROOF_TARGET_SELF,
    "base_sha": PROOF_TARGET_SELF,
    "base_tree": "base_sha",
    "head_sha": PROOF_TARGET_SELF,
    "head_tree": "head_sha",
    "pr_number": PROOF_TARGET_SELF,
    "pr_state": "pr_number",
    "open_pr_count": PROOF_TARGET_NONE,
    "ci_state": "head_sha",
    "review_threads_unresolved": "pr_number",
    "completed_gates": "head_sha",
    "blockers": PROOF_TARGET_NONE,
    "openai_agentic_capacity": PROOF_TARGET_NONE,
    "claude_capacity": PROOF_TARGET_NONE,
    "capacity_routing_mode": PROOF_TARGET_NONE,
    "next_safe_action": PROOF_TARGET_NONE,
}

# Pull-request states GitHub counts as open. A proven open pull request is a member of the open set.
OPEN_PR_STATES = frozenset({"OPEN", "DRAFT"})


def names_revision(text: str, revision: str) -> bool:
    """Does `text` carry `revision` as a whole object name, never as part of a longer hex run?"""
    pattern = re.compile(r"(?<![0-9A-Fa-f])" + re.escape(revision) + r"(?![0-9A-Fa-f])", re.IGNORECASE)
    return pattern.search(text) is not None


def required_model_identity(runtime: dict) -> object:
    """The identity runtime equality is judged against.

    `model_id` is AUTHORITATIVE: it is the exact API identity the routing matrix pins for the lane.
    `model_requested` is the same request recorded as the controller asked for it, and is used only
    when no API identity applies - some lanes route with no API id at all. Where both carry a
    payload they must agree, because two different values name two different required runtimes.
    """
    model_id = runtime.get("model_id")
    if not operational_text_failures(model_id):
        return model_id
    requested = runtime.get("model_requested")
    return requested if not operational_text_failures(requested) else None


def is_vocabulary_member(value: object, vocabulary: object) -> bool:
    """TOTAL membership of an UNTRUSTED value in a string vocabulary.

    SHAPE BEFORE RELATION. `x in some_set` hashes `x`, so a list or dict arriving from a manifest
    raised `TypeError: unhashable type` from inside relational logic and the PUBLIC gate crashed
    instead of reporting. Tuple vocabularies happened to survive only because `in` over a tuple
    compares by equality - which made totality an accident of which container a constant was
    written with, not a property of the contract. Every vocabulary here is a set of STRINGS, so a
    value that is not a string is never a member and never needs hashing. That is the whole rule,
    and it needs no exception handling.
    """
    return isinstance(value, str) and value in vocabulary  # type: ignore[operator]


def _is_operational_observation(value: object) -> bool:
    """A recorded identity must be an operational token, not merely non-null."""
    return value is not None and not operational_text_failures(value)


def _is_effort_observation(value: object) -> bool:
    """A recorded effort must be a member of the effort enum, not merely non-null."""
    return is_vocabulary_member(value, EFFORT_VALUES)


def manifest_relation_failures(label: str, instance: object) -> list[str]:
    """Cross-field semantics. TOTAL: any JSON value yields reasons, never an exception."""
    if not isinstance(instance, dict):
        return [f"{label}: a manifest must be a JSON object"]

    failures: list[str] = []
    for field in PROOF_PAIRED_GRAMMAR:
        failures.extend(proof_pair_failures(label, instance, field, f"{field}_evidence"))

    # --- PROOF_TARGET_BINDINGS ----------------------------------------------------------------
    # Proof pairing proves a field's value is evidenced. It never proved WHAT the value is evidence
    # OF: a PROVEN head_tree beside an UNKNOWN head_sha, or a PROVEN thread count beside an UNKNOWN
    # pull-request number, observed nothing identified and still passed.
    for field, target in PROOF_TARGET_BINDINGS.items():
        if target in (PROOF_TARGET_SELF, PROOF_TARGET_NONE):
            continue
        if instance.get(f"{field}_evidence") == "PROVEN" and instance.get(f"{target}_evidence") != "PROVEN":
            failures.append(
                f"{label}: {field} is PROVEN but its target {target} is not; an observation of an "
                f"unidentified {target} proves nothing about any identified one"
            )

    # A completed gate is completed only at its evidence key (VALIDATION_BUDGET, section 9). A key
    # that names neither this manifest's proven head nor its proven tree is a gate from another
    # revision - invalidated evidence - presented as completed.
    gates = instance.get("completed_gates")
    if instance.get("completed_gates_evidence") == "PROVEN" and isinstance(gates, list):
        revisions = [
            value
            for value, evidence in (
                (instance.get("head_sha"), instance.get("head_sha_evidence")),
                (instance.get("head_tree"), instance.get("head_tree_evidence")),
            )
            if evidence == "PROVEN" and isinstance(value, str) and HASH_IDENTIFIER_RE.match(value)
        ]
        if revisions:
            for index, gate in enumerate(gates):
                key = gate.get("evidence_key") if isinstance(gate, dict) else None
                if isinstance(key, str) and not any(names_revision(key, revision) for revision in revisions):
                    failures.append(
                        f"{label}: completed_gates[{index}] evidence_key names neither the proven head_sha "
                        f"nor the proven head_tree; a gate proven at another revision is invalidated "
                        f"evidence under VALIDATION_BUDGET, never a completed gate for this one"
                    )

    pr_state = instance.get("pr_state")
    open_count = instance.get("open_pr_count")
    if (
        instance.get("pr_state_evidence") == "PROVEN"
        and is_vocabulary_member(pr_state, OPEN_PR_STATES)
        and instance.get("open_pr_count_evidence") == "PROVEN"
        and isinstance(open_count, int)
        and not isinstance(open_count, bool)
        and open_count < 1
    ):
        failures.append(
            f"{label}: pr_state is PROVEN {pr_state} but open_pr_count is PROVEN {open_count}; the proven "
            f"open pull request is itself a member of the open set"
        )

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
            if not is_vocabulary_member(source, MODEL_EVIDENCE_CLASSES):
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

        # --- identity RELATION: observed vs required -----------------------------------------
        # Everything here stays inside the identity dimension. An identity contradiction never
        # touches the effort or thinking observations, which carry their own evidence.
        model_id = runtime.get("model_id")
        requested = runtime.get("model_requested")
        actual = runtime.get("model_actual")
        source = runtime.get("model_evidence_source")
        fallback = runtime.get("model_fallback")

        if (
            not operational_text_failures(model_id)
            and not operational_text_failures(requested)
            and model_id != requested
        ):
            failures.append(
                f"{label}: model_id {model_id!r} and model_requested {requested!r} disagree, so the "
                f"manifest names two different required runtimes; model_id is the authoritative identity"
            )

        required_identity = required_model_identity(runtime)
        observed_identity = actual if _is_operational_observation(actual) else None
        # TARGET_BOUND_EXECUTION_PROOF. The comparison below only ran when a required identity
        # existed, so a proving class - or CONTRADICTED - with no target skipped it and passed.
        if is_vocabulary_member(source, TARGET_BOUND_CLASSES) and required_identity is None:
            failures.append(
                f"{label}: {source} claims an observed runtime, but neither model_id nor model_requested "
                f"names the required identity, so model_actual has nothing to be compared with; "
                f"execution proof without a target proves nothing"
            )
        if required_identity is not None and observed_identity is not None:
            matches = observed_identity == required_identity
            if is_vocabulary_member(source, EXECUTION_PROVING_CLASSES) and not matches:
                failures.append(
                    f"{label}: {source} reports model_actual {observed_identity!r} but the required "
                    f"identity is {required_identity!r}; a runtime that is not the one the route "
                    f"required is CONTRADICTED, never ordinary matching execution evidence"
                )
            if source == "CONTRADICTED" and matches:
                failures.append(
                    f"{label}: CONTRADICTED claims a conflicting runtime, but model_actual "
                    f"{observed_identity!r} equals the required identity, so nothing is contradicted"
                )

        # An observed fallback IS a conflicting execution: the lane that ran is not the lane asked
        # for. Recording one while the identity class claims a clean match states both at once.
        if not operational_text_failures(fallback) and source != "CONTRADICTED":
            failures.append(
                f"{label}: model_fallback records {fallback!r}, so a runtime other than the requested "
                f"one executed; the identity evidence class must be CONTRADICTED, not {source!r}"
            )

        # --- effort RELATION: observed vs requested -------------------------------------------
        # Effort has exactly the requested/observed shape identity has and was never given the
        # relation, so telemetry reporting `high` against a requested `xhigh` passed as matching
        # evidence and CONTRADICTED could claim a conflict that did not exist. Everything here stays
        # inside the effort dimension and names no effort value.
        requested_effort = runtime.get("requested_effort")
        observed_effort = runtime.get("observed_effort")
        effort_source = runtime.get("effort_evidence_source")
        effort_pair_known = _is_effort_observation(requested_effort) and _is_effort_observation(observed_effort)
        effort_mismatch = effort_pair_known and observed_effort != requested_effort
        if is_vocabulary_member(effort_source, EXECUTION_PROVING_CLASSES) and not _is_effort_observation(
            requested_effort
        ):
            failures.append(
                f"{label}: {effort_source} claims an observed effort, but requested_effort "
                f"{requested_effort!r} names no target, so observed_effort has nothing to be compared "
                f"with; execution proof without a target proves nothing"
            )
        if is_vocabulary_member(effort_source, EXECUTION_PROVING_CLASSES) and effort_mismatch:
            failures.append(
                f"{label}: {effort_source} reports observed_effort {observed_effort!r} but requested_effort "
                f"is {requested_effort!r}; an effort that is not the one requested is CONTRADICTED, never "
                f"ordinary matching execution evidence"
            )
        if effort_source == "CONTRADICTED":
            if not _is_effort_observation(requested_effort):
                failures.append(
                    f"{label}: CONTRADICTED effort needs a requested_effort to contradict, got {requested_effort!r}"
                )
            elif effort_pair_known and not effort_mismatch:
                failures.append(
                    f"{label}: CONTRADICTED claims a conflicting effort, but observed_effort "
                    f"{observed_effort!r} equals requested_effort, so nothing is contradicted"
                )

        # --- EFFORT_MISMATCH_WAIVER ------------------------------------------------------------
        # A waiver exists only for a truthfully recorded CONTRADICTED effort mismatch. It never
        # rewrites either effort, and the identity relation above never reads it, so it cannot
        # repair a model mismatch or an observed fallback. Shape-safe: the grammar reports a
        # malformed block; this relation reads only a well-typed one.
        waiver = runtime.get("effort_mismatch_waiver")
        if isinstance(waiver, dict):
            waiver_status = waiver.get("status")
            waiver_evidence = waiver.get("evidence")
            waivable = effort_source == "CONTRADICTED" and effort_mismatch
            if is_vocabulary_member(waiver_status, EFFORT_WAIVER_STATUSES):
                if not waivable:
                    if waiver_status != "NOT_APPLICABLE":
                        failures.append(
                            f"{label}: effort_mismatch_waiver is {waiver_status} but no CONTRADICTED effort "
                            f"mismatch is recorded, so there is nothing to waive; status must be NOT_APPLICABLE"
                        )
                    elif waiver_evidence is not None:
                        failures.append(f"{label}: effort_mismatch_waiver NOT_APPLICABLE must carry no evidence")
                elif waiver_status == "NOT_APPLICABLE":
                    failures.append(
                        f"{label}: a CONTRADICTED effort mismatch is recorded, so effort_mismatch_waiver must "
                        f"say NOT_GRANTED or HUMAN_GRANTED, never NOT_APPLICABLE"
                    )
                elif waiver_status == "NOT_GRANTED" and waiver_evidence is not None:
                    failures.append(
                        f"{label}: effort_mismatch_waiver NOT_GRANTED must carry no evidence; waiver text "
                        f"without a grant is ambiguous"
                    )
                elif waiver_status == "HUMAN_GRANTED" and not _is_operational_observation(waiver_evidence):
                    failures.append(
                        f"{label}: effort_mismatch_waiver HUMAN_GRANTED must record the exact task-specific "
                        f"human waiver as operational text"
                    )

        thinking = runtime.get("thinking_actual")
        if not is_vocabulary_member(thinking, THINKING_STATES):
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
            "CLAUDE_CONTINUITY": (
                openai_capacity == "EXHAUSTED" and is_vocabulary_member(claude_capacity, CAPACITY_AVAILABLE)
            ),
            "OPENAI_CONTINUITY": (
                claude_capacity == "EXHAUSTED" and is_vocabulary_member(openai_capacity, CAPACITY_AVAILABLE)
            ),
            "BOTH_EXHAUSTED_STOP": (openai_capacity == "EXHAUSTED" and claude_capacity == "EXHAUSTED"),
            "QUALITY_OPTIMAL": (openai_capacity == "NORMAL" and claude_capacity == "NORMAL"),
            "CLAUDE_FIRST_CONSERVATION": (
                is_vocabulary_member(openai_capacity, CAPACITY_CONSTRAINED)
                and is_vocabulary_member(claude_capacity, CAPACITY_AVAILABLE)
            ),
            "OPENAI_FIRST_CONSERVATION": (
                is_vocabulary_member(claude_capacity, CAPACITY_CONSTRAINED)
                and is_vocabulary_member(openai_capacity, CAPACITY_AVAILABLE)
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
    """The whole operational gate: grammar SHAPE plus cross-field RELATIONS. TOTAL over any JSON.

    The shape-before-relation rule above makes this total by CONSTRUCTION. The guard is defence in
    depth ONLY - so a future relation written without `is_vocabulary_member` degrades to a
    fail-closed report rather than a traceback escaping a trust boundary. It is never the reason
    totality holds, and the totality suite asserts the underlying functions do not raise either.
    """
    try:
        failures = manifest_grammar_failures(label, instance)
        failures.extend(manifest_relation_failures(label, instance))
        return failures
    except Exception as exc:  # noqa: BLE001 - a crash at a trust boundary must fail CLOSED
        return [
            f"{label}: SAFETY_BLOCKER: validation could not complete on this input "
            f"({type(exc).__name__}: {exc}); a manifest that cannot be judged is never accepted"
        ]


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

# The one job whose conclusion the bundle carries (section 17.1 (G)). Its conclusion is merge-gate
# evidence only while its context is among the contexts the protected branch requires.
REQUIRED_TESTS_CONTEXT = "tests"

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
            if not is_vocabulary_member(value, ACCEPTED_TESTED_EVENTS):
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
    head = evidence["audited_pr_head"]

    # RUN_HEAD_BINDING. GitHub attributes every run to exactly one head. A bundle whose run is
    # attributed to any other revision cites a run of THAT revision, so none of its conclusions are
    # evidence for the audited one - for every accepted event, not only for pull_request.
    if evidence["run_reported_head"] != head:
        failures.append(
            "run_reported_head is not audited_pr_head; the cited workflow run belongs to another revision, "
            "so none of its conclusions are evidence for the audited head"
        )

    if event == "pull_request":
        if evidence["current_base"] == head:
            failures.append("current_base equals audited_pr_head; a synthetic merge revision has two distinct parents")
        if checkout in (head, evidence["current_base"]):
            failures.append(
                "a pull_request tested revision must be the synthetic merge revision itself, never the "
                "audited head or the base it merges"
            )
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
    if REQUIRED_TESTS_CONTEXT not in evidence["required_contexts"]:
        failures.append(
            f"required_contexts does not include {REQUIRED_TESTS_CONTEXT!r}, the context whose job conclusion "
            f"this bundle proves; a job no required context names gates nothing"
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

    bindings = parse_surface_registry(ctx["authority_text"], BLOCK_PROOF_TARGETS)  # type: ignore[arg-type]
    if bindings is None:
        failures.append(f"{CANONICAL}: {BLOCK_PROOF_TARGETS} block missing or malformed")
    else:
        bound = dict(bindings)
        if len(bound) != len(bindings):
            failures.append(f"{CANONICAL}: {BLOCK_PROOF_TARGETS} binds a field more than once")
        for field in declared:
            if field not in bound:
                failures.append(
                    f"{CANONICAL}: proof-paired field {field} declares no target in {BLOCK_PROOF_TARGETS}; "
                    f"every proven observation must say what it is an observation OF"
                )
        for field, target in bound.items():
            if field not in declared:
                failures.append(f"{CANONICAL}: {BLOCK_PROOF_TARGETS} binds {field}, which is not proof-paired")
            elif target not in (PROOF_TARGET_SELF, PROOF_TARGET_NONE) and bound.get(target) != PROOF_TARGET_SELF:
                failures.append(
                    f"{CANONICAL}: {field} is bound to {target!r}, which is not a proof-paired identity (SELF)"
                )
        if bound != PROOF_TARGET_BINDINGS:
            failures.append(
                f"{CANONICAL}: {BLOCK_PROOF_TARGETS} does not equal the executable proof-target bindings; "
                f"the registry and the relation must agree"
            )

    # The committed specification must equal what the grammar generates, as a parsed object. It is
    # parsed STRICTLY first: a duplicate member whose last occurrence happens to equal the generated
    # value is still an ambiguous document, and equality must never be proven on one.
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    loaded = committed_json(root, schema_path, failures)
    if loaded is None:
        return
    try:
        committed_text = canonical_json(loaded[1])
    except (ValueError, RecursionError) as exc:
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
    loaded = committed_json(root, example_path, failures)
    if loaded is None:
        return
    raw, example = loaded
    if "EXAMPLE_ONLY" not in raw:
        failures.append(f"{example_path}: a committed fixture must declare EXAMPLE_ONLY")
    failures.extend(check_manifest_instance(example_path, example))


def check_manifest_file(root: Path, manifest_path: Path) -> list[str]:
    """Validate a COMPILED operational manifest against the canonical grammar and relations.

    This is the executable acceptance path. The published JSON Schema is a generated
    specification artifact and is never interpreted here. The compiled manifest is ADVERSARIAL
    evidence: the strict JSON boundary refuses an ambiguous or non-JSON document before any
    grammar or relation runs, so a repeated member can never be resolved and then certified.
    """
    try:
        instance = load_strict_json_file(manifest_path)
    except StrictJsonError as exc:
        return [f"{manifest_path}: {STRICT_JSON_REJECTED}: {exc}; an ambiguous or non-JSON manifest is never judged"]
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
    _check_unconsumed_block_bodies(ctx, failures)
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


def _emit(line: str) -> None:
    """Write one output line that can never raise on the stream's encoding.

    A compiled manifest is adversarial evidence, so a member name or value it carries can reach a
    diagnostic. On a stream whose encoding cannot represent a character, `print` raised
    UnicodeEncodeError and the gate ended in a traceback instead of a verdict. Such characters are
    written as backslash escapes instead.
    """
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    print(line.encode(encoding, "backslashreplace").decode(encoding))


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
        _emit(json.dumps(emit_manifest_schema(), indent=2, ensure_ascii=False, sort_keys=False))
        return 0

    if args.manifest is not None:
        manifest_failures = check_manifest_file(root, Path(args.manifest))
        if args.json:
            _emit(
                json.dumps(
                    {"manifest": args.manifest, "ok": not manifest_failures, "failures": manifest_failures},
                    indent=2,
                    sort_keys=True,
                )
            )
        elif manifest_failures:
            _emit(f"STATE_MANIFEST: FAIL ({len(manifest_failures)} issue(s))")
            for item in manifest_failures:
                _emit(f"  - {item}")
        else:
            _emit("STATE_MANIFEST: PASS")
            _emit(f"  manifest: {args.manifest}")
        return 1 if manifest_failures else 0

    failures = collect_failures(root)

    if args.json:
        _emit(json.dumps({"root": str(root), "ok": not failures, "failures": failures}, indent=2, sort_keys=True))
    elif failures:
        _emit(f"AGENT_OS_CONTROL_PLANE: FAIL ({len(failures)} issue(s))")
        for item in failures:
            _emit(f"  - {item}")
    else:
        _emit("AGENT_OS_CONTROL_PLANE: PASS")
        _emit(f"  root: {root}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
