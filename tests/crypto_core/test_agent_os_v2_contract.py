"""Contract tests for the crypto_core Agent OS control plane.

<!-- CONTROL_PLANE_ROLE: EXECUTABLE_SUBORDINATE -->
<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->

NEGATIVE_BOUNDARY: The repository validator proves repository-provable structure only. It does NOT prove that its own GitHub CI step executed, that GitHub will block a merge, or that a required status context identifies a particular workflow file or revision.

These tests carry an INDEPENDENT ORACLE. Every expected set below is written out literally here and
is never imported or derived from ``scripts/crypto_core/validate_agent_os_v2.py``. That separation is
the point: if a registry entry is deleted from the validator AND the corresponding file is deleted
from the tree, the validator alone would go quiet, but the oracle in this file still demands both, so
the contract still fails. Co-drift therefore requires editing this file too, which is a visible,
reviewable act rather than a silent one.

Adversarial coverage is behavioural: each probe copies the exact control-plane file set into a
sandbox, mutates one thing, and proves the validator rejects it. One strong test per distinct contract
failure - deliberately not several wordings of the same failure.
"""

from __future__ import annotations

import ast
import errno
import importlib.util
import io
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from stat import S_IFDIR, S_IFLNK, S_ISLNK
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "crypto_core" / "validate_agent_os_v2.py"
CANONICAL = "docs/crypto_core/agent_os_v2.md"


def _load_validator():
    spec = importlib.util.spec_from_file_location("crypto_core_agent_os_validator", VALIDATOR_PATH)
    if spec is None or spec.loader is None:  # pragma: no cover - defensive
        raise RuntimeError("cannot load the control-plane validator from {}".format(VALIDATOR_PATH))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


# ---------------------------------------------------------------------------
# INDEPENDENT ORACLE - literal, and never derived from the validator
# ---------------------------------------------------------------------------

ORACLE_ACTIVE_DOCTRINE_SURFACES = {
    "docs/crypto_core/agent_os_v2.md": "CANONICAL_AUTHORITY",
    "AGENTS.md": "DURABLE_RAILS",
    "CLAUDE.md": "CLAUDE_ADAPTER",
    ".claude/skills/crypto-core-token-efficient-loop/SKILL.md": "CLAUDE_ADAPTER",
    ".codex/skills/crypto-core-max-safe/SKILL.md": "CODEX_ADAPTER",
    "docs/crypto_core/agent_workflow.md": "WORKFLOW_COMPANION",
    "docs/crypto_core/model_prompting_guide.md": "AUTHORING_GUIDE",
    "docs/crypto_core/agent_prompts/opus5_prompting_playbook.md": "AUTHORING_GUIDE",
    "docs/crypto_core/agent_prompts/token_efficiency_v2.md": "COMPRESSION_GUIDE",
    "docs/crypto_core/token_efficiency_playbook.md": "COMPRESSION_GUIDE",
    "docs/crypto_core/deep_research_protocol.md": "RESEARCH_ADAPTER",
    "docs/crypto_core/continuity/CONTINUITY_INDEX.md": "CONTINUITY_INDEX",
    "docs/crypto_core/agent_lessons.md": "LESSONS_COMPANION",
    ".github/copilot-instructions.md": "COPILOT_INACTIVE_SHIM",
    "docs/crypto_core_current_state.md": "DURABLE_STATE_POINTER",
}

ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS = {
    "scripts/crypto_core/validate_agent_os_v2.py",
    "scripts/crypto_core/audit_agent_setup.ps1",
    "tests/crypto_core/test_agent_os_v2_contract.py",
    ".github/workflows/ci.yml",
    "docs/crypto_core/continuity/state_manifest.schema.json",
    "docs/crypto_core/continuity/state_manifest.example.json",
}

ORACLE_DURABLE_SURFACES = set(ORACLE_ACTIVE_DOCTRINE_SURFACES)

ORACLE_MODEL_AGNOSTIC_SURFACES = {
    "AGENTS.md",
    "docs/crypto_core/agent_workflow.md",
    "docs/crypto_core/agent_lessons.md",
    "docs/crypto_core_current_state.md",
}

ORACLE_EFFORT_ENUM = ["low", "medium", "high", "xhigh", "max"]

ORACLE_MAX_EFFORT_CLASSES = {"T3B", "T3D", "T3E", "T4"}

ORACLE_PROMPT_COMPILER_FIELDS = [
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
]

ORACLE_MODEL_EVIDENCE_CLASSES = [
    "RUNTIME_TELEMETRY",
    "USER_ATTESTED_UI_SELECTION",
    "CONFIGURATION_EVIDENCE_ONLY",
    "UNKNOWN",
    "CONTRADICTED",
]

ORACLE_WORK_RETURN_CONTRACT = [
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
]

# Every live-state field the durable-surface scan rejects on ASSIGNMENT. Written out literally here
# so the registry and the scanner cannot quietly shrink together.
ORACLE_VOLATILE_STATE_FIELDS = {
    "CURRENT_BRANCH",
    "BRANCH_REF",
    "HEAD_REF",
    "BASE_SHA",
    "HEAD_SHA",
    "MAIN_SHA",
    "CURRENT_HEAD",
    "MERGE_COMMIT",
    "BASE_TREE",
    "HEAD_TREE",
    "CURRENT_TREE",
    "PR_NUMBER",
    "PR_STATE",
    "CURRENT_PR",
    "OPEN_PR_COUNT",
    "CI_STATE",
    "CI_STATUS",
    "CURRENT_CI_STATE",
    "CHECKS_STATE",
    "CODEQL_STATE",
    "REVIEW_THREADS",
    "UNRESOLVED_THREADS",
    "REVIEW_THREADS_UNRESOLVED",
    "CURRENT_BLOCKER",
    "ACTIVE_BLOCKER",
    "BLOCKER_STATE",
    "COMPLETED_GATES",
    "GATE_STATE",
    "MERGE_AUTHORIZED",
    "MERGE_AUTHORIZATION",
    "AUTHORIZATION_STATE",
    "MODEL_ACTUAL",
    "MODEL_EFFORT_ACTUAL",
    "OBSERVED_EFFORT",
    "MODEL_FALLBACK",
    "OPENAI_AGENTIC_CAPACITY",
    "CLAUDE_CAPACITY",
    "CAPACITY_ROUTING_MODE",
    "CAPABILITY_MODE",
    "HOST_SETTING_RAW",
    "MODEL_EVIDENCE_SOURCE",
    "NEXT_SAFE_ACTION",
}

# MEANINGFUL_VALUE_CLASS_REGISTRY_V1, declared literally here and never derived from the validator.
# Order matters: it is the registry order, so a silent reordering is visible too.
ORACLE_PROOF_PAIRED_MANIFEST_FIELDS = [
    ("branch", "TOKEN_BRANCH"),
    ("base_sha", "HASH_IDENTIFIER"),
    ("base_tree", "HASH_IDENTIFIER"),
    ("head_sha", "HASH_IDENTIFIER"),
    ("head_tree", "HASH_IDENTIFIER"),
    ("pr_number", "POSITIVE_INT"),
    ("pr_state", "NORMALIZED_ENUM"),
    ("open_pr_count", "NONNEGATIVE_INT"),
    ("ci_state", "NORMALIZED_ENUM"),
    ("review_threads_unresolved", "NONNEGATIVE_INT"),
    ("completed_gates", "STRUCTURED_LIST"),
    ("blockers", "STRUCTURED_LIST"),
    ("openai_agentic_capacity", "NORMALIZED_ENUM"),
    ("claude_capacity", "NORMALIZED_ENUM"),
    ("capacity_routing_mode", "NORMALIZED_ENUM"),
    ("next_safe_action", "TEXT_EVIDENCE"),
]

ORACLE_PROOF_PAIRED_FIELD_NAMES = [field for field, _class in ORACLE_PROOF_PAIRED_MANIFEST_FIELDS]

ORACLE_MEANINGFUL_VALUE_CLASSES = [
    "TEXT_EVIDENCE",
    "TOKEN_REPO",
    "TOKEN_BRANCH",
    "HASH_IDENTIFIER",
    "NONNEGATIVE_INT",
    "POSITIVE_INT",
    "NORMALIZED_ENUM",
    "STRUCTURED_LIST",
]

ORACLE_PROVIDER_CAPACITY_STATES = ["NORMAL", "CONSERVE", "CRITICAL", "EXHAUSTED", "UNKNOWN"]

ORACLE_CAPACITY_ROUTING_MODES = [
    "QUALITY_OPTIMAL",
    "CLAUDE_FIRST_CONSERVATION",
    "OPENAI_FIRST_CONSERVATION",
    "CLAUDE_CONTINUITY",
    "OPENAI_CONTINUITY",
    "BOTH_EXHAUSTED_STOP",
]

# The seven GitHub host surfaces retired in the final consolidated repair. Held literally because
# registry membership does not control host discovery: a host loads these whatever a registry says.
ORACLE_FINAL_RETIRED_HOST_PATHS = {
    ".github/agents/forensic-debugger.agent.md",
    ".github/agents/prd-compliance-auditor.agent.md",
    ".github/prompts/edge-discovery.prompt.md",
    ".github/prompts/edge-validation.prompt.md",
    ".github/prompts/forensic-debug.prompt.md",
    ".github/prompts/safe-patch.prompt.md",
    ".github/skills/repo-hygiene-ci-guardian/SKILL.md",
}

ORACLE_HOST_DISCOVERY_GLOBS = [
    ".github/agents/**/*.agent.md",
    ".github/skills/**/SKILL.md",
    ".github/prompts/**/*.prompt.md",
    ".github/instructions/**/*.instructions.md",
    ".github/copilot-instructions.md",
    ".github/workflows/*",
    ".claude/skills/**/SKILL.md",
    ".codex/skills/**/SKILL.md",
    ".cursor/rules/**/*.mdc",
]

# HOST_DISCOVERY_CLOSED_WORLD: the one surface allowed to remain in a discovery location without an
# active role, and the registered host-directory paths that no host discovers.
ORACLE_HISTORICAL_HOST_SURFACES = {".cursor/rules/prdv3-constitution.mdc": "NON_APPLYING"}
ORACLE_HOST_NON_DISCOVERY_PATHS = [
    ".github/hooks/hook-engine.md",
    ".github/skills/_shared/references/contract-schema.md",
]
# HOST_EXECUTABLE_WORKFLOW_CLOSED_WORLD: every GitHub Actions workflow file, classified, granting no authority.
ORACLE_HOST_EXECUTABLE_WORKFLOWS = {
    ".github/workflows/ci.yml": "CONTROL_PLANE_CI",
    ".github/workflows/crypto_core_mt4_s3a_blst_qualification.yml": "HISTORICAL_MT4_CLOSED_FROZEN",
    ".github/workflows/crypto_core_mt4_s3c_static_worker_qualification.yml": "HISTORICAL_MT4_CLOSED_FROZEN",
    ".github/workflows/crypto_core_mt4_s3c_trusted_attestation.yml": "HISTORICAL_MT4_CLOSED_FROZEN",
    ".github/workflows/crypto_core_mt4_trusted_attestation.yml": "HISTORICAL_MT4_CLOSED_FROZEN",
    ".github/workflows/deribit-public-smoke.yml": "PUBLIC_SMOKE_NO_READINESS",
}

# PROOF_TARGET_BINDINGS, written out literally: what each proof-paired field is an observation OF.
ORACLE_PROOF_TARGET_BINDINGS = {
    "branch": "SELF",
    "base_sha": "SELF",
    "base_tree": "base_sha",
    "head_sha": "SELF",
    "head_tree": "head_sha",
    "pr_number": "SELF",
    "pr_state": "pr_number",
    "open_pr_count": "NONE",
    "ci_state": "head_sha",
    "review_threads_unresolved": "pr_number",
    "completed_gates": "head_sha",
    "blockers": "NONE",
    "openai_agentic_capacity": "NONE",
    "claude_capacity": "NONE",
    "capacity_routing_mode": "NONE",
    "next_safe_action": "NONE",
}

# `max` legality is PER FAMILY. Written out literally so a relapse to a single-family restriction
# cannot be hidden by editing the canonical table alone.
ORACLE_MAX_EFFORT_FAMILY_INTENTS = {
    "T3B": {"IMPLEMENTATION", "REPAIR"},
    "T3D": {"ARCHITECTURE"},
    "T3E": {"PROMPT_ARCHITECTURE"},
    "T4": {"CLASS_C_CROSS_CONTRACT"},
}

# The command shapes the committed workflow names, recorded as EVIDENCE only, and the oracle
# path anchored outside the mutable artifact registry.
ORACLE_CI_VALIDATOR_COMMAND = "python scripts/crypto_core/validate_agent_os_v2.py"
ORACLE_CI_ANCHOR_COMMAND = "test -f tests/crypto_core/test_agent_os_v2_contract.py"
ORACLE_BOOTSTRAP_PATH = "tests/crypto_core/test_agent_os_v2_contract.py"

ORACLE_FRONTIER_LANE = "GPT-6 Astra"
ORACLE_FRONTIER_MODEL_ID = "gpt-6-astra"

ORACLE_RETIRED_PATH_COUNT = 50

# Surfaces that must never be reachable as control-plane doctrine: product, legacy and protected runtime.
ORACLE_FORBIDDEN_REGISTRY_PREFIXES = ("src/", "tests/services/", "tests/brain/", ".github/hooks/")

SANDBOX_FILES = sorted(
    set(ORACLE_ACTIVE_DOCTRINE_SURFACES)
    | ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS
    | set(ORACLE_HOST_EXECUTABLE_WORKFLOWS)
)


# ---------------------------------------------------------------------------
# Sandbox helpers
# ---------------------------------------------------------------------------


def build_sandbox(tmp_path: Path) -> Path:
    """Copy exactly the registered control-plane file set into an isolated tree."""
    root = tmp_path / "repo"
    for rel in SANDBOX_FILES:
        src = REPO_ROOT / rel
        dst = root / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return root


def _normalized(path: Path) -> str:
    """File text with all runs of whitespace collapsed to single spaces.

    Prose assertions are about CONTENT. Matching raw text couples the assertion to where a
    paragraph happens to wrap, which then fails for a reason that has nothing to do with the
    contract being asserted.
    """
    return re.sub(r"\s+", " ", path.read_text(encoding="utf-8-sig"))


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8-sig")


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8", newline="\n")


def patch(root: Path, rel: str, old: str, new: str, *, count: int | None = 1) -> None:
    """Replace EVERY occurrence of ``old``, proving the anchor was there before mutating.

    ``count`` pins how many occurrences the probe expects, so a probe aimed at one exact site
    fails loudly if the anchor stops being unique. ``count=None`` is for an anchor doctrine may
    legitimately restate in several sections: the probe then proves only that it was present,
    and still removes all of it.
    """
    text = read(root, rel)
    found = text.count(old)
    if count is None:
        assert found, "sandbox anchor {!r} is absent from {}".format(old, rel)
    else:
        assert found == count, "sandbox anchor {!r} appeared {} times in {}".format(old, found, rel)
    write(root, rel, text.replace(old, new))


def failures(root: Path) -> list[str]:
    return validator.collect_failures(root)


def assert_rejects(root: Path, needle: str) -> None:
    found = failures(root)
    assert found, "the mutated control plane was accepted; expected a failure mentioning {!r}".format(needle)
    joined = "\n".join(found)
    assert needle in joined, "expected a failure mentioning {!r}, got:\n{}".format(needle, joined)


@pytest.fixture()
def sandbox(tmp_path: Path) -> Path:
    return build_sandbox(tmp_path)


# ---------------------------------------------------------------------------
# Anchors: the real tree, and the oracle itself
# ---------------------------------------------------------------------------


def test_real_control_plane_passes() -> None:
    """The committed control plane satisfies every structural contract."""
    found = validator.collect_failures(REPO_ROOT)
    assert found == [], "control-plane validation failed:\n" + "\n".join(found)


def test_pristine_sandbox_passes(sandbox: Path) -> None:
    """The sandbox is a faithful copy, so an unmutated sandbox must also pass."""
    assert failures(sandbox) == []


def test_oracle_matches_registered_active_surfaces() -> None:
    """Independent oracle vs the committed registry - neither may drift alone."""
    registry = validator.parse_surface_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "ACTIVE_DOCTRINE_SURFACES"
    )
    assert registry is not None
    assert dict(registry) == ORACLE_ACTIVE_DOCTRINE_SURFACES


def test_oracle_matches_registered_artifacts_and_scan_sets() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert set(validator.parse_registry(canonical_text, "REQUIRED_CONTROL_PLANE_ARTIFACTS")) == (
        ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS
    )
    assert set(validator.parse_registry(canonical_text, "DURABLE_SURFACES")) == ORACLE_DURABLE_SURFACES
    assert set(validator.parse_registry(canonical_text, "MODEL_AGNOSTIC_SURFACES")) == (ORACLE_MODEL_AGNOSTIC_SURFACES)
    assert len(validator.parse_registry(canonical_text, "RETIRED_CONTROL_PLANE_PATHS")) == (ORACLE_RETIRED_PATH_COUNT)


def test_oracle_matches_fixed_contract_blocks() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert validator.block_lines(canonical_text, "REASONING_EFFORT_ENUM") == ORACLE_EFFORT_ENUM
    assert validator.block_lines(canonical_text, "PROMPT_COMPILER_V2_1_FIELDS") == (ORACLE_PROMPT_COMPILER_FIELDS)
    assert validator.block_lines(canonical_text, "MODEL_EVIDENCE_CLASSES") == ORACLE_MODEL_EVIDENCE_CLASSES
    assert validator.block_lines(canonical_text, "WORK_RETURN_CONTRACT") == ORACLE_WORK_RETURN_CONTRACT


@pytest.mark.parametrize("rel", sorted(ORACLE_ACTIVE_DOCTRINE_SURFACES))
def test_every_oracle_surface_exists_with_its_role(rel: str) -> None:
    """Probe: removing a registry entry AND its file must still fail this independent oracle."""
    path = REPO_ROOT / rel
    assert path.is_file(), "active doctrine surface missing from the tree: {}".format(rel)
    markers = re.findall(r"<!--\s*CONTROL_PLANE_ROLE:\s*([A-Z_]+)\s*-->", path.read_text(encoding="utf-8-sig"))
    assert markers == [ORACLE_ACTIVE_DOCTRINE_SURFACES[rel]]


@pytest.mark.parametrize("rel", sorted(ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS))
def test_every_oracle_artifact_exists(rel: str) -> None:
    assert (REPO_ROOT / rel).is_file(), "required control-plane artifact missing: {}".format(rel)


def test_registry_never_reaches_into_product_or_protected_surfaces() -> None:
    for rel in set(ORACLE_ACTIVE_DOCTRINE_SURFACES) | ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS:
        for prefix in ORACLE_FORBIDDEN_REGISTRY_PREFIXES:
            assert not rel.startswith(prefix), "control plane must not register {}".format(rel)


def test_retired_paths_are_absent_from_the_tree() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    retired = validator.parse_registry(canonical_text, "RETIRED_CONTROL_PLANE_PATHS")
    assert retired is not None
    for rel in retired:
        assert not (REPO_ROOT / rel).exists(), "retired control-plane path still present: {}".format(rel)


# ---------------------------------------------------------------------------
# Probes 1-3: canonical authority and role markers
# ---------------------------------------------------------------------------


def test_second_canonical_authority_is_rejected(sandbox: Path) -> None:
    patch(
        sandbox,
        "AGENTS.md",
        "<!-- CONTROL_PLANE_ROLE: DURABLE_RAILS -->",
        "<!-- CONTROL_PLANE_ROLE: CANONICAL_AUTHORITY -->",
    )
    assert_rejects(sandbox, "only docs/crypto_core/agent_os_v2.md may declare CANONICAL_AUTHORITY")


def test_missing_subordinate_role_marker_is_rejected(sandbox: Path) -> None:
    patch(sandbox, "CLAUDE.md", "<!-- CONTROL_PLANE_ROLE: CLAUDE_ADAPTER -->\n", "")
    assert_rejects(sandbox, "CLAUDE.md: expected exactly one CONTROL_PLANE_ROLE marker, found 0")


def test_wrong_subordinate_role_is_rejected(sandbox: Path) -> None:
    patch(
        sandbox,
        "docs/crypto_core/agent_workflow.md",
        "<!-- CONTROL_PLANE_ROLE: WORKFLOW_COMPANION -->",
        "<!-- CONTROL_PLANE_ROLE: DURABLE_RAILS -->",
    )
    assert_rejects(sandbox, "the registry declares WORKFLOW_COMPANION")


def test_missing_authority_reference_marker_is_rejected(sandbox: Path) -> None:
    patch(
        sandbox,
        "docs/crypto_core/token_efficiency_playbook.md",
        "<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->\n",
        "",
    )
    assert_rejects(sandbox, "missing CONTROL_PLANE_AUTHORITY_REF marker")


# ---------------------------------------------------------------------------
# Probes 4-7: no second routing regime
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "docs/crypto_core/agent_workflow.md",
        "CLAUDE.md",
        "docs/crypto_core/agent_prompts/opus5_prompting_playbook.md",
    ],
)
def test_route_line_outside_the_canonical_matrix_is_rejected(sandbox: Path, rel: str) -> None:
    """Probe: a companion or adapter declaring routing authority."""
    text = read(sandbox, rel)
    write(sandbox, rel, text + "\nROUTE: T1 | BOUNDED_READ | GPT-5.6 Terra | - | high | READ_ONLY\n")
    assert_rejects(sandbox, "ROUTE line outside the canonical routing matrix")


@pytest.mark.parametrize(
    "injected",
    [
        "Terra owns T1 for every bounded read in this repository.",
        "The universal lifecycle is ChatGPT then Claude then Codex, in that order, for every task.",
        "Claude must always implement and Codex must always follow the implementation.",
    ],
)
def test_model_named_routing_in_a_companion_is_rejected(sandbox: Path, injected: str) -> None:
    """Probe: a model-agnostic companion regrowing a per-model routing regime."""
    text = read(sandbox, "docs/crypto_core/agent_workflow.md")
    marker = "<!-- HISTORICAL_RECORD_BEGIN -->"
    assert marker in text
    write(sandbox, "docs/crypto_core/agent_workflow.md", text.replace(marker, injected + "\n\n" + marker, 1))
    assert_rejects(sandbox, "in a MODEL_AGNOSTIC surface")


def test_model_name_inside_a_bounded_historical_region_is_allowed(sandbox: Path) -> None:
    """Probe 36: a dated historical record naming retired tooling must NOT fail."""
    text = read(sandbox, "docs/crypto_core/agent_workflow.md")
    end = "<!-- HISTORICAL_RECORD_END -->"
    assert text.count(end) == 1
    injected = "Historically the Class-C audit ran on Claude Opus 4.8 and surge work on Claude Fable 5.\n"
    write(sandbox, "docs/crypto_core/agent_workflow.md", text.replace(end, injected + end))
    assert failures(sandbox) == []


# ---------------------------------------------------------------------------
# Probes 5, 8-9, 13-16: family, effort and lane integrity
# ---------------------------------------------------------------------------


def test_adapter_declaring_task_family_authority_is_rejected(sandbox: Path) -> None:
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", text + "\nTASK_FAMILY_AUTHORITY: CLAUDE_ADAPTER_DECIDES\n")
    assert_rejects(sandbox, "TASK_FAMILY_AUTHORITY must be declared exactly once")


def test_adapter_declaring_effort_authority_is_rejected(sandbox: Path) -> None:
    text = read(sandbox, ".codex/skills/crypto-core-max-safe/SKILL.md")
    write(
        sandbox,
        ".codex/skills/crypto-core-max-safe/SKILL.md",
        text + "\nEFFORT_AUTHORITY: HOST_ADAPTER_DECIDES\n",
    )
    assert_rejects(sandbox, "EFFORT_AUTHORITY must be declared exactly once")


def test_t3b_absorbing_architecture_is_rejected(sandbox: Path) -> None:
    """Probe 8: the defect that made the documented strong-effort branches unreachable."""
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T3B | IMPLEMENTATION,REPAIR | Claude Opus 5",
        "ROUTE: T3B | IMPLEMENTATION,REPAIR,ARCHITECTURE | Claude Opus 5",
    )
    assert_rejects(sandbox, "T3B absorbs ARCHITECTURE")


def test_max_effort_declaration_and_matrix_must_agree(sandbox: Path) -> None:
    """Probe 9: claiming max belongs only to T3B while other families have a max branch."""
    patch(sandbox, CANONICAL, "MAX_EFFORT_CLASSES: T3B,T3D,T3E,T4", "MAX_EFFORT_CLASSES: T3B")
    assert_rejects(sandbox, "but the routing matrix grants max to")


def test_removing_a_declared_max_branch_is_rejected(sandbox: Path) -> None:
    """The same contract from the other direction: the matrix losing a declared max branch."""
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T3D | ARCHITECTURE | Claude Opus 5 | claude-opus-5 | max | READ_ONLY\n",
        "",
    )
    assert_rejects(sandbox, "MAX_EFFORT_CLASSES declares")


@pytest.mark.parametrize(
    ("lane", "model_id"),
    [
        ("GPT-5.6 Terra", "-"),
        ("Codex GPT-5.6 Sol", "gpt-5.6-sol"),
        ("Claude Opus 5", "claude-opus-5"),
    ],
)
def test_protected_audit_downgrade_is_rejected(sandbox: Path, lane: str, model_id: str) -> None:
    """Probes 13-15: a protected T4 gate silently rerouted to a cheaper or self-reviewing lane."""
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | {} | {} | xhigh | READ_ONLY".format(lane, model_id),
    )
    found = failures(sandbox)
    assert found, "a downgraded T4 route was accepted"


def test_self_audit_independence_rule_must_be_present(sandbox: Path) -> None:
    """Probe 15: the rule that a same-model self-review never satisfies Class C."""
    patch(sandbox, CANONICAL, "SELF_AUDIT_ONLY_NOT_INDEPENDENT", "SELF_REVIEW_IS_FINE", count=None)
    assert_rejects(sandbox, "SELF_AUDIT_ONLY_NOT_INDEPENDENT")


def test_class_c_unavailable_stop_token_must_be_present(sandbox: Path) -> None:
    """Probe 34: without this token there is no named stop, so a silent downgrade becomes possible."""
    patch(sandbox, CANONICAL, "CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE", "CLASS_C_LANE_OPTIONAL")
    assert_rejects(sandbox, "CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE")


def test_max_effort_classes_match_the_oracle() -> None:
    """The declared max-effort classes and the matrix agree, and both match the independent oracle."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    declared = re.search(r"(?m)^MAX_EFFORT_CLASSES:\s*(\S+)\s*$", canonical_text)
    assert declared is not None
    assert {part for part in declared.group(1).split(",") if part} == ORACLE_MAX_EFFORT_CLASSES

    rows = validator.block_lines(canonical_text, "ROLE_ROUTING_MATRIX")
    assert rows is not None
    matrix_max = set()
    for row in rows:
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        if fields[4] == "max":
            matrix_max.add(fields[0])
    assert matrix_max == ORACLE_MAX_EFFORT_CLASSES


def test_frontier_lane_identity_is_pinned() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    rows = validator.block_lines(canonical_text, "ROLE_ROUTING_MATRIX")
    assert rows is not None
    t4_rows = [row for row in rows if row.startswith("ROUTE: T4 ")]
    assert t4_rows, "no protected T4 route declared"
    for row in t4_rows:
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        assert fields[2] == ORACLE_FRONTIER_LANE
        assert fields[3] == ORACLE_FRONTIER_MODEL_ID
        assert fields[5] == "READ_ONLY"


@pytest.mark.parametrize(
    ("old", "new"),
    [
        (
            "ROUTE: T3D | ARCHITECTURE | Claude Opus 5 | claude-opus-5 | max | READ_ONLY",
            "ROUTE: T3D | ARCHITECTURE | Claude Opus 5 | claude-opus-5 | ultra | READ_ONLY",
        ),
        ("<!-- REASONING_EFFORT_ENUM_BEGIN -->\nlow", "<!-- REASONING_EFFORT_ENUM_BEGIN -->\nultra\nlow"),
    ],
)
def test_ultra_stored_as_a_reasoning_effort_is_rejected(sandbox: Path, old: str, new: str) -> None:
    """Probe 16: Ultra is a capability mode and must never enter the effort enum."""
    patch(sandbox, CANONICAL, old, new)
    found = failures(sandbox)
    assert found, "Ultra was accepted as a reasoning effort"


def test_effort_enum_membership_is_exact(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "<!-- REASONING_EFFORT_ENUM_BEGIN -->\nlow\n", "<!-- REASONING_EFFORT_ENUM_BEGIN -->\n")
    assert_rejects(sandbox, "REASONING_EFFORT_ENUM block must be exactly")


# ---------------------------------------------------------------------------
# Probes 10, 19: merge authority and the allowed-files boundary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "replacement",
    [
        "MERGE_AUTHORITY_SOURCE: CONTROLLER_DECIDES",
        "MERGE_AUTHORITY_SOURCE: CONNECTOR_AVAILABILITY",
        "MERGE_AUTHORITY_SOURCE: HUMAN_DELEGATED_STANDING",
    ],
)
def test_wrong_canonical_merge_authority_value_is_rejected(sandbox: Path, replacement: str) -> None:
    patch(sandbox, CANONICAL, "MERGE_AUTHORITY_SOURCE: HUMAN_ONLY_PER_PR", replacement)
    assert_rejects(sandbox, "MERGE_AUTHORITY_SOURCE must be HUMAN_ONLY_PER_PR")


def test_subordinate_surface_declaring_merge_authority_is_rejected(sandbox: Path) -> None:
    """A subordinate may reference merge authority; it may never declare it."""
    text = read(sandbox, "docs/crypto_core/agent_workflow.md")
    write(sandbox, "docs/crypto_core/agent_workflow.md", text + "\nMERGE_AUTHORITY_SOURCE: HUMAN_ONLY_PER_PR\n")
    assert_rejects(sandbox, "MERGE_AUTHORITY_SOURCE must be declared exactly once")


def test_missing_canonical_merge_authority_declaration_is_rejected(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "MERGE_AUTHORITY_SOURCE: HUMAN_ONLY_PER_PR\n", "")
    assert_rejects(sandbox, "MERGE_AUTHORITY_SOURCE must be declared exactly once")


def test_allowed_files_remains_an_authorization_boundary() -> None:
    """Probe 19: ALLOWED_FILES survives as a mutation boundary, not as a sizing ceiling."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert "ALLOWED_FILES" in canonical_text
    assert "MUTATION AUTHORIZATION BOUNDARY" in canonical_text
    assert "ALLOWED_FILES" in ORACLE_PROMPT_COMPILER_FIELDS


# ---------------------------------------------------------------------------
# Probes 11-12: runtime evidence classes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("USER_ATTESTED_UI_SELECTION", "RUNTIME_TELEMETRY_UI"),
        ("CONFIGURATION_EVIDENCE_ONLY\n", ""),
    ],
)
def test_runtime_evidence_class_tampering_is_rejected(sandbox: Path, old: str, new: str) -> None:
    """Probes 11-12: relabelling an attestation as telemetry, or dropping the config-only class."""
    text = read(sandbox, CANONICAL)
    begin = "<!-- MODEL_EVIDENCE_CLASSES_BEGIN -->"
    end = "<!-- MODEL_EVIDENCE_CLASSES_END -->"
    head, block, tail = text.partition(begin)
    body, endmarker, rest = tail.partition(end)
    assert block and endmarker
    write(sandbox, CANONICAL, head + begin + body.replace(old, new, 1) + endmarker + rest)
    assert_rejects(sandbox, "MODEL_EVIDENCE_CLASSES block must be exactly")


# ---------------------------------------------------------------------------
# Probes 17-18: PR sizing authority
# ---------------------------------------------------------------------------


def test_wrong_pr_sizing_authority_value_is_rejected(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "PR_SIZING_AUTHORITY: SEMANTIC_CLOSURE_ONLY", "PR_SIZING_AUTHORITY: MAX_FILE_COUNT")
    assert_rejects(sandbox, "PR_SIZING_AUTHORITY must be SEMANTIC_CLOSURE_ONLY")


@pytest.mark.parametrize(
    "injected",
    [
        "MAX_CHANGED_FILES: 6",
        "Prefer the smallest additive change that unlocks the next bridge.",
        "Exactly one artifact per PR keeps review cheap.",
        "one module per PR",
        "one test per PR",
    ],
)
def test_retired_sizing_heuristics_are_rejected(sandbox: Path, injected: str) -> None:
    """Probes 17-18: numeric ceilings and the retired minimal-diff heuristics."""
    text = read(sandbox, "docs/crypto_core/agent_workflow.md")
    marker = "<!-- HISTORICAL_RECORD_BEGIN -->"
    write(sandbox, "docs/crypto_core/agent_workflow.md", text.replace(marker, injected + "\n\n" + marker, 1))
    assert_rejects(sandbox, "retired PR-sizing heuristic")


# ---------------------------------------------------------------------------
# Probes 20-23: registry completeness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "docs/crypto_core/agent_lessons.md",
        "AGENTS.md",
        ".github/copilot-instructions.md",
        "docs/crypto_core/continuity/CONTINUITY_INDEX.md",
    ],
)
def test_removing_an_active_doctrine_surface_is_rejected(sandbox: Path, rel: str) -> None:
    """Probes 20-21: any registered doctrine surface, including the lessons companion."""
    (sandbox / rel).unlink()
    assert_rejects(sandbox, "active doctrine surface missing from the tree: {}".format(rel))


@pytest.mark.parametrize(
    "rel",
    [
        "scripts/crypto_core/audit_agent_setup.ps1",
        ".github/workflows/ci.yml",
        "tests/crypto_core/test_agent_os_v2_contract.py",
        "docs/crypto_core/continuity/state_manifest.schema.json",
        "docs/crypto_core/continuity/state_manifest.example.json",
    ],
)
def test_removing_a_required_artifact_is_rejected(sandbox: Path, rel: str) -> None:
    """Probes 22-23: a non-doctrine artifact is load-bearing too."""
    (sandbox / rel).unlink()
    assert_rejects(sandbox, "required control-plane artifact missing from the tree: {}".format(rel))


def test_removing_registry_entry_and_file_together_still_fails_the_oracle(sandbox: Path) -> None:
    """Probe 24: co-deletion goes quiet in the validator, so the independent oracle must catch it."""
    rel = "docs/crypto_core/agent_lessons.md"
    patch(sandbox, CANONICAL, "- {} :: LESSONS_COMPANION\n".format(rel), "")
    patch(sandbox, CANONICAL, "- {}\n".format(rel), "", count=2)
    (sandbox / rel).unlink()

    # The validator alone now sees a self-consistent control plane.
    assert failures(sandbox) == []

    # The oracle in this file does not, because it was never derived from the validator.
    registry = validator.parse_surface_registry(read(sandbox, CANONICAL), "ACTIVE_DOCTRINE_SURFACES")
    assert dict(registry or []) != ORACLE_ACTIVE_DOCTRINE_SURFACES
    assert not (sandbox / rel).is_file()


def test_retired_path_reappearing_is_rejected(sandbox: Path) -> None:
    revived = sandbox / ".github/skills/crypto-scheduler/SKILL.md"
    revived.parent.mkdir(parents=True, exist_ok=True)
    revived.write_text("# revived scheduler skill\n", encoding="utf-8", newline="\n")
    assert_rejects(sandbox, "retired control-plane path still present in the tree")


# ---------------------------------------------------------------------------
# Probes 26-29: durable-surface scan and structural regions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "rel",
    [
        "docs/crypto_core/agent_os_v2.md",
        "AGENTS.md",
        "CLAUDE.md",
        ".codex/skills/crypto-core-max-safe/SKILL.md",
        "docs/crypto_core/agent_workflow.md",
        "docs/crypto_core/model_prompting_guide.md",
        "docs/crypto_core/token_efficiency_playbook.md",
        "docs/crypto_core/deep_research_protocol.md",
        "docs/crypto_core/continuity/CONTINUITY_INDEX.md",
        "docs/crypto_core/agent_lessons.md",
        ".github/copilot-instructions.md",
        "docs/crypto_core_current_state.md",
    ],
)
def test_volatile_commit_hash_in_a_durable_surface_is_rejected(sandbox: Path, rel: str) -> None:
    """Probe 26: one representative of every durable-surface role class."""
    text = read(sandbox, rel)
    write(sandbox, rel, "Current head is 61cd4d6b960067ef4eaa5634fff10b6cecf72403.\n\n" + text)
    assert_rejects(sandbox, "volatile commit hash in a durable surface")


@pytest.mark.parametrize(
    "injected",
    [
        "The active blocker was introduced in PR #371.",
        "OPEN_PR_COUNT=0",
        "Base is main @ 61cd4d6b960067ef4eaa5634fff10b6cecf72403",
    ],
)
def test_other_volatile_state_pins_are_rejected(sandbox: Path, injected: str) -> None:
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", injected + "\n\n" + text)
    found = failures(sandbox)
    assert found, "a volatile state pin was accepted: {}".format(injected)


def test_commit_hash_inside_a_bounded_historical_record_is_allowed(sandbox: Path) -> None:
    """Probe 27: the exemption is structural, not proximity-based."""
    text = read(sandbox, "docs/crypto_core/agent_lessons.md")
    end = "<!-- HISTORICAL_RECORD_END -->"
    assert text.count(end) == 1
    injected = "Dated evidence: merge commit 61cd4d6b960067ef4eaa5634fff10b6cecf72403.\n"
    write(sandbox, "docs/crypto_core/agent_lessons.md", text.replace(end, injected + end))
    assert failures(sandbox) == []


def test_example_fixture_policy_requires_the_marker(sandbox: Path) -> None:
    """Probe 28: an example fixture may carry example hashes only while it declares EXAMPLE_ONLY."""
    rel = "docs/crypto_core/continuity/state_manifest.example.json"
    payload = json.loads(read(sandbox, rel))
    assert "EXAMPLE_ONLY" in payload["$comment"]
    assert re.fullmatch(r"[0-9a-f]{40}", payload["head_sha"])

    payload["$comment"] = "an ordinary fixture"
    payload["compiled_at_evidence"] = "an ordinary fixture"
    payload["task_boundary"] = "ORDINARY"
    payload["next_safe_action"] = "none"
    payload["authorization"]["mutation_scope"] = "none"
    payload["authorization"]["notes"] = "none"
    payload["invalidations"] = []
    payload["completed_gates"] = []
    payload["blockers"] = []
    payload["model_runtime"]["host_setting_raw"] = "none"
    payload["model_runtime"]["environment"] = "none"
    payload["model_runtime"]["client_version"] = "none"
    write(sandbox, rel, json.dumps(payload, indent=2) + "\n")
    assert_rejects(sandbox, "a committed fixture must declare EXAMPLE_ONLY")


def test_renaming_headings_does_not_hide_active_doctrine(sandbox: Path) -> None:
    """Probe 29: region logic is marker-based, so heading names are irrelevant to it."""
    rel = "docs/crypto_core/agent_workflow.md"
    text = read(sandbox, rel)
    renamed = re.sub(r"(?m)^## \d+\. .*$", "## Renamed Section", text)
    renamed = renamed.replace("<!-- HISTORICAL_RECORD_BEGIN -->", "<!-- HISTORICAL_RECORD_BEGIN -->", 1)
    write(sandbox, rel, renamed)
    assert failures(sandbox) == [], "renaming headings changed the verdict"

    # And the active region is genuinely still scanned after the rename.
    write(sandbox, rel, "Head 61cd4d6b960067ef4eaa5634fff10b6cecf72403\n\n" + renamed)
    assert_rejects(sandbox, "volatile commit hash in a durable surface")


def test_unterminated_exempt_region_fails_closed(sandbox: Path) -> None:
    """An unterminated exemption would swallow the rest of the file, so it must fail."""
    rel = "docs/crypto_core/agent_lessons.md"
    patch(sandbox, rel, "<!-- HISTORICAL_RECORD_END -->", "")
    assert_rejects(sandbox, "unterminated HISTORICAL_RECORD_BEGIN")


def test_orphan_region_end_marker_is_rejected(sandbox: Path) -> None:
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", text + "\n<!-- HISTORICAL_RECORD_END -->\n")
    assert_rejects(sandbox, "HISTORICAL_RECORD_END without a matching BEGIN")


# ---------------------------------------------------------------------------
# Probes 30-33: Work boundaries and blocker fixed point
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    ["CHATGPT_WORK_LANE", "WORK_LANE_BOUNDARIES", "WORK_PREPARED_NOT_AUTHORIZED"],
)
def test_work_lane_contract_tokens_must_be_present(sandbox: Path, token: str) -> None:
    """Probes 30-31: stale-snapshot and prepared-packet boundaries are contract, not advice."""
    text = read(sandbox, CANONICAL)
    write(sandbox, CANONICAL, text.replace(token, "WORK_LANE_UNBOUNDED"))
    assert_rejects(sandbox, "required contract token missing: {}".format(token))


def test_work_return_contract_membership_is_exact(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "SOURCE_REVISIONS\n", "")
    assert_rejects(sandbox, "WORK_RETURN_CONTRACT block must be exactly")


@pytest.mark.parametrize(
    "token",
    [
        "BLOCKER_ESCAPE_PROTOCOL_V2",
        "ROOT_CAUSE_MODE",
        "FIXED_POINT_STOP",
        "FIXED_POINT_NOT_REACHED",
        "BLOCKER_IDENTITY_SURVIVES_RENAME",
    ],
)
def test_blocker_escape_contract_tokens_must_be_present(sandbox: Path, token: str) -> None:
    """Probes 32-33: renaming a blocker never resets its budget, and the fixed point freezes."""
    text = read(sandbox, CANONICAL)
    write(sandbox, CANONICAL, text.replace(token, "BLOCKER_LOOP_FOREVER"))
    assert_rejects(sandbox, "required contract token missing: {}".format(token))


def _proven_variant(prop: dict) -> dict:
    """Return the non-null branch of a proof-paired property."""
    for variant in prop.get("anyOf") or []:
        if variant.get("type") != "null":
            return variant
    return prop


def test_blocker_state_vocabulary_carries_the_fixed_point() -> None:
    schema = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    )
    item = _proven_variant(schema["properties"]["blockers"])["items"]
    assert "FIXED_POINT_NOT_REACHED" in item["properties"]["state"]["enum"]
    assert item["properties"]["repair_count"]["type"] == "integer"
    assert "id" in item["required"]


# ---------------------------------------------------------------------------
# Probe 35: continuity without optional host context support
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "CONTEXT_CONTINUITY_PROTOCOL_V2",
        "ZERO_MATERIAL_OPERATIONAL_CONTEXT_LOSS",
        "FRESH_CHAT_BOOTSTRAP",
        "STATE_MANIFEST_V1",
        "CURRENT_HANDOFF_V2",
        "MODEL_CAPABILITY_REFRESH_GATE",
        "GITHUB_CONNECTOR_POLICY",
    ],
)
def test_continuity_and_gate_tokens_must_be_present(sandbox: Path, token: str) -> None:
    text = read(sandbox, CANONICAL)
    write(sandbox, CANONICAL, text.replace(token, "REMOVED_CONTRACT"))
    assert_rejects(sandbox, "required contract token missing: {}".format(token))


def test_continuity_index_carries_the_bootstrap_without_host_support(sandbox: Path) -> None:
    """Probe 35: the bootstrap chain is repository-only, so host context support is optional."""
    rel = "docs/crypto_core/continuity/CONTINUITY_INDEX.md"
    text = read(sandbox, rel)
    for step in ("AGENTS.md", CANONICAL, "STATE_MANIFEST", "re-proof"):
        assert step in text
    write(sandbox, rel, text.replace("FRESH_CHAT_BOOTSTRAP", "REMOVED"))
    assert_rejects(sandbox, "required continuity token missing: FRESH_CHAT_BOOTSTRAP")


# ---------------------------------------------------------------------------
# Prompt compiler: exactly one top-level template
# ---------------------------------------------------------------------------


def test_prompt_compiler_field_set_is_exact(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "BLOCKER_INVENTORY\n", "")
    assert_rejects(sandbox, "PROMPT_COMPILER_V2_1_FIELDS block must be exactly")


def test_second_top_level_prompt_template_is_rejected(sandbox: Path) -> None:
    rel = "docs/crypto_core/agent_prompts/opus5_prompting_playbook.md"
    text = read(sandbox, rel)
    competing = (
        "\n<!-- PROMPT_COMPILER_V2_1_FIELDS_BEGIN -->\n"
        "OBJECTIVE\nCONTEXT\nCONSTRAINTS\n"
        "<!-- PROMPT_COMPILER_V2_1_FIELDS_END -->\n"
    )
    write(sandbox, rel, text + competing)
    assert_rejects(sandbox, "exactly one top-level prompt-compiler field block")


# ---------------------------------------------------------------------------
# State manifest proof pairing
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "evidence", "expect_failure"),
    [
        (0, "PROVEN", False),
        (3, "PROVEN", False),
        (None, "UNKNOWN", False),
        (0, "UNKNOWN", True),
        (None, "PROVEN", True),
        (None, "ASSUMED", True),
    ],
)
def test_open_pr_count_proof_pairing(value: object, evidence: str, expect_failure: bool) -> None:
    instance = {"open_pr_count": value, "open_pr_count_evidence": evidence}
    found = validator.proof_pair_failures("fixture", instance, "open_pr_count", "open_pr_count_evidence")
    assert bool(found) is expect_failure


@pytest.mark.parametrize(
    "instance",
    [
        {"open_pr_count": 0},
        {"open_pr_count_evidence": "PROVEN"},
        {},
    ],
)
def test_missing_half_of_a_proof_pair_is_rejected(instance: dict) -> None:
    found = validator.proof_pair_failures("fixture", instance, "open_pr_count", "open_pr_count_evidence")
    assert found


def test_generated_schema_publishes_the_merge_authorized_constant() -> None:
    """The published specification states the constraint the grammar enforces behaviourally."""
    schema = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    )
    merge_authorized = schema["properties"]["authorization"]["properties"]["merge_authorized"]
    assert merge_authorized["const"] is False


def test_example_manifest_demonstrates_both_proof_states() -> None:
    example = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json").read_text(encoding="utf-8-sig")
    )
    assert example["open_pr_count_evidence"] == "PROVEN"
    assert isinstance(example["open_pr_count"], int)
    assert example["pr_number_evidence"] == "UNKNOWN"
    assert example["pr_number"] is None


# ---------------------------------------------------------------------------
# Validator honesty
# ---------------------------------------------------------------------------


ORACLE_FORBIDDEN_IMPORTS = ("subprocess", "requests", "urllib", "socket", "http", "ftplib", "telnetlib")
ORACLE_FORBIDDEN_CALLS = ("os.remove", "os.unlink", "os.rmdir", "shutil.rmtree", "Path.unlink", "Path.write_text")


def _imported_modules(source: str) -> set[str]:
    """Top-level module names the source actually imports, by AST - never by substring."""
    modules: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            modules.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module.split(".")[0])
    return modules


def _called_attributes(source: str) -> set[str]:
    """Dotted attribute calls, by AST, so a mention inside a comment or string is not a call."""
    calls: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            target = node.func
            parts = [target.attr]
            value = target.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            calls.add(".".join(reversed(parts)))
    return calls


def test_validator_is_read_only_offline_and_stdlib_only() -> None:
    """STRUCTURAL, not textual.

    The retired probe searched the raw source for the substring `requests`, so an ordinary English
    comment - "the controller requests a bounded report" - failed an offline dependency check while
    a real network import inside a string would have passed. Prose is not code: imports are read
    from the AST, and destructive calls are matched as calls rather than as mentions.
    """
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    imported = _imported_modules(source)
    for forbidden in ORACLE_FORBIDDEN_IMPORTS:
        assert forbidden not in imported, "validator must stay offline and read-only: imports {}".format(forbidden)
    called = _called_attributes(source)
    for forbidden in ORACLE_FORBIDDEN_CALLS:
        assert forbidden not in called, "validator must stay read-only: calls {}".format(forbidden)
    assert "def collect_failures(" in source


def test_control_plane_states_the_validator_limits() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert "It does NOT understand arbitrary English" in canonical_text
    assert "INDEPENDENT SEMANTIC AUDIT" in canonical_text


def test_control_plane_makes_no_forbidden_claim() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert "## 21. Non-claims" in canonical_text
    for claim in ("profitability", "live readiness", "capital safety", "zero literal model-memory loss"):
        assert claim in canonical_text


# ---------------------------------------------------------------------------
# Setup audit script: permanent guard against the previous fail-open shape
# ---------------------------------------------------------------------------

AUDIT_SCRIPT = REPO_ROOT / "scripts" / "crypto_core" / "audit_agent_setup.ps1"


def _audit_source() -> str:
    return AUDIT_SCRIPT.read_text(encoding="utf-8")


def test_setup_audit_delegates_the_deterministic_gate() -> None:
    """The audit must run the validator rather than re-implementing doctrine parsing."""
    source = _audit_source()
    assert "scripts/crypto_core/validate_agent_os_v2.py" in source
    assert "$validatorExit = $global:LASTEXITCODE" in source


def test_setup_audit_has_no_heading_name_region_heuristics() -> None:
    """The exact previous defect: heading-name parsing silently skipped active doctrine.

    Renaming or renumbering '## 24. Active' made the whole active region invisible to the audit. The
    audit now owns no region logic at all, so this guard asserts the heuristic never comes back.
    """
    body = _audit_source().split("#>", 1)[1]
    for heuristic in (
        "'^## 20",
        "'^## 24",
        "Get-ActiveDoctrineText",
        "Final durable model set",
    ):
        assert heuristic not in body, "heading-name region heuristic reintroduced: {}".format(heuristic)


def test_setup_audit_is_not_fail_open() -> None:
    """A deterministic failure must exit non-zero; the old script always exited 0.

    The behavioural proof is `test_setup_audit_fails_closed_when_the_validator_cannot_launch`.
    This probe only pins the structural pieces that behaviour depends on.
    """
    body = _audit_source().split("#>", 1)[1]
    assert "exit $exitCode" in body
    assert "$exitCode = 1" in body
    # Being unable to EXECUTE the gate is a failure, never a silent skip.
    assert "the control-plane contract could not be executed" in body
    assert "an absent exit status is never success" in body


def test_setup_audit_keeps_network_probes_informational() -> None:
    """Only offline deterministic checks may decide the exit code."""
    body = _audit_source().split("#>", 1)[1]
    open_pr_section = body.split("OPEN PRS (informational, best-effort)", 1)[1].split("Write-Section", 1)[0]
    assert "deterministicFailures" not in open_pr_section
    assert "OPEN_PR_COUNT=UNKNOWN" in open_pr_section


# ---------------------------------------------------------------------------
# Durable-state claim boundary (the guarantee must be true, not merely broad)
# ---------------------------------------------------------------------------


def test_volatile_state_field_registry_matches_the_oracle() -> None:
    registry = validator.parse_surface_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "VOLATILE_STATE_FIELDS"
    )
    assert registry is not None
    assert {field for field, _cls in registry} == ORACLE_VOLATILE_STATE_FIELDS


@pytest.mark.parametrize(
    "injected",
    [
        "CURRENT_CI_STATE=GREEN",
        "CI_STATE: GREEN",
        "CODEQL_STATE: SUCCESS",
        "CURRENT_BRANCH=chore/example-scope-pr1",
        "PR_STATE: OPEN",
        "HEAD_TREE: 6acb8d8da82d69fedc03494f47ebafb5d2888ecb",
        "UNRESOLVED_THREADS = 3",
        "CURRENT_BLOCKER: secondary-metrics",
        "COMPLETED_GATES: full_suite",
        "MERGE_AUTHORIZED: true",
        "MODEL_ACTUAL: claude-opus-5",
        "OPENAI_AGENTIC_CAPACITY: EXHAUSTED",
        "CAPACITY_ROUTING_MODE: CLAUDE_CONTINUITY",
    ],
)
def test_every_declared_volatile_state_class_is_rejected(sandbox: Path, injected: str) -> None:
    """The advertised guarantee must hold for every class the control plane claims, not just hashes."""
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", injected + "\n\n" + text)
    found = failures(sandbox)
    assert found, "a declared volatile-state class was accepted: {}".format(injected)


def test_naming_a_volatile_field_without_assigning_it_stays_legal(sandbox: Path) -> None:
    """Durable doctrine must still be able to EXPLAIN a live-state field."""
    text = read(sandbox, "CLAUDE.md")
    write(
        sandbox,
        "CLAUDE.md",
        "The handoff reports `CI_STATE`, `PR_STATE`, `OPEN_PR_COUNT` and `CLAUDE_CAPACITY` as proven "
        "facts, or as UNKNOWN.\n\n" + text,
    )
    assert failures(sandbox) == []


def test_registry_entry_separator_is_not_read_as_an_assignment(sandbox: Path) -> None:
    """The registry lists field names with ' :: ', which must not trip the scanner it feeds."""
    assert failures(sandbox) == []
    canonical = read(sandbox, CANONICAL)
    assert "- CI_STATE :: CI_STATUS" in canonical


def test_shrinking_the_volatile_registry_is_visible_to_the_oracle(sandbox: Path) -> None:
    """Dropping a field from the registry silences the scanner, so the oracle must catch the drift."""
    patch(sandbox, CANONICAL, "- CURRENT_CI_STATE :: CI_STATUS\n", "")
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", "CURRENT_CI_STATE=GREEN\n\n" + text)

    # The validator alone is now blind to this specific field.
    assert not any("CURRENT_CI_STATE" in f for f in failures(sandbox))

    # The independent oracle is not.
    registry = validator.parse_surface_registry(read(sandbox, CANONICAL), "VOLATILE_STATE_FIELDS")
    assert {field for field, _cls in (registry or [])} != ORACLE_VOLATILE_STATE_FIELDS


def test_control_plane_does_not_overclaim_the_scan(sandbox: Path) -> None:
    canonical = read(sandbox, CANONICAL)
    assert "DURABLE_STATE_CLAIM_BOUNDARY" in canonical
    flat = " ".join(canonical.split())
    assert "What this scan does NOT do" in flat
    patch(sandbox, CANONICAL, "DURABLE_STATE_CLAIM_BOUNDARY", "DURABLE_STATE_TOTAL_GUARANTEE")
    assert_rejects(sandbox, "required contract token missing: DURABLE_STATE_CLAIM_BOUNDARY")


# ---------------------------------------------------------------------------
# Manifest proof pairing (schema and registry may not drift apart)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value", "evidence"),
    [
        ("ci_state", "GREEN", "UNKNOWN"),
        ("pr_state", "OPEN", "UNKNOWN"),
        ("head_tree", None, "PROVEN"),
        ("review_threads_unresolved", 0, "UNKNOWN"),
        ("openai_agentic_capacity", "NORMAL", "UNKNOWN"),
    ],
)
def test_fixture_proof_pair_violations_are_rejected(sandbox: Path, field, value, evidence) -> None:
    example_path = "docs/crypto_core/continuity/state_manifest.example.json"
    example = json.loads(read(sandbox, example_path))
    example[field] = value
    example["{}_evidence".format(field)] = evidence
    write(sandbox, example_path, json.dumps(example, indent=2))
    found = failures(sandbox)
    assert found, "an unpaired live-state fact was accepted for {}".format(field)


def test_capacity_unknown_has_exactly_one_representation() -> None:
    """UNKNOWN is null plus UNKNOWN evidence, never also a literal enum member."""
    schema = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    )
    for field in ("openai_agentic_capacity", "claude_capacity"):
        variant = _proven_variant(schema["properties"][field])
        assert "UNKNOWN" not in variant["enum"], field
        assert set(variant["enum"]) == {"NORMAL", "CONSERVE", "CRITICAL", "EXHAUSTED"}


# ---------------------------------------------------------------------------
# Provider capacity: continuation, shared pool, and no enforced ratio
# ---------------------------------------------------------------------------


def test_capacity_vocabularies_match_the_oracle() -> None:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert validator.block_lines(canonical_text, "PROVIDER_CAPACITY_STATES") == ORACLE_PROVIDER_CAPACITY_STATES
    assert validator.block_lines(canonical_text, "CAPACITY_ROUTING_MODES") == ORACLE_CAPACITY_ROUTING_MODES


@pytest.mark.parametrize(
    ("scenario", "mode"),
    [
        ("openai exhausted, claude available", "CLAUDE_CONTINUITY"),
        ("claude exhausted, openai available", "OPENAI_CONTINUITY"),
        ("both exhausted", "BOTH_EXHAUSTED_STOP"),
    ],
)
def test_each_capacity_scenario_has_a_declared_mode(scenario: str, mode: str) -> None:
    """Continuation and stop are contract, not improvisation."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    declared = validator.block_lines(canonical_text, "CAPACITY_ROUTING_MODES") or []
    assert mode in declared, "no declared routing mode for the scenario {!r}".format(scenario)


@pytest.mark.parametrize("mode", ["CLAUDE_CONTINUITY", "OPENAI_CONTINUITY", "BOTH_EXHAUSTED_STOP"])
def test_removing_a_capacity_mode_is_rejected(sandbox: Path, mode: str) -> None:
    text = read(sandbox, CANONICAL)
    begin = "<!-- CAPACITY_ROUTING_MODES_BEGIN -->"
    end = "<!-- CAPACITY_ROUTING_MODES_END -->"
    head, _, tail = text.partition(begin)
    body, _, rest = tail.partition(end)
    assert mode + "\n" in body
    write(sandbox, CANONICAL, head + begin + body.replace(mode + "\n", "", 1) + end + rest)
    assert_rejects(sandbox, "CAPACITY_ROUTING_MODES block must be exactly")


def test_one_exhausted_provider_is_not_a_project_stop(sandbox: Path) -> None:
    canonical = read(sandbox, CANONICAL)
    assert "PROVIDER_EXHAUSTION_IS_NOT_PROJECT_STOP" in canonical
    write(
        sandbox,
        CANONICAL,
        canonical.replace("PROVIDER_EXHAUSTION_IS_NOT_PROJECT_STOP", "PROVIDER_EXHAUSTION_STOPS_PROJECT"),
    )
    assert_rejects(sandbox, "required contract token missing: PROVIDER_EXHAUSTION_IS_NOT_PROJECT_STOP")


def test_unavailable_frontier_lane_blocks_only_its_own_gate() -> None:
    """An exhausted shared pool blocks the protected gate; it never satisfies or waives it, and it
    never converts into a project-level stop."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    flat = " ".join(canonical_text.split())
    assert "CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE" in flat
    assert "PROVIDER_EXHAUSTION_IS_NOT_PROJECT_STOP" in flat
    assert "it never converts an unavailable protected lane into a satisfied one" in flat
    # The protected lane is still exclusively routed, whatever the capacity state.
    rows = validator.block_lines(canonical_text, "ROLE_ROUTING_MATRIX") or []
    for row in rows:
        if row.startswith("ROUTE: T4 "):
            assert ORACLE_FRONTIER_LANE in row


def test_work_is_not_represented_as_separate_free_capacity(sandbox: Path) -> None:
    canonical = read(sandbox, CANONICAL)
    flat = " ".join(canonical.split())
    assert "OPENAI_SHARED_AGENTIC_POOL" in flat
    assert "Work is not a separate free provider" in flat
    assert "WORK_ENVIRONMENT_VALUE" in flat
    assert "SHARED_OPENAI_POOL_COST" in flat
    patch(sandbox, CANONICAL, "Work is not a separate free provider", "Work is its own free pool")
    assert_rejects(sandbox, "required contract token missing: Work is not a separate free provider")


@pytest.mark.parametrize(
    "injected",
    [
        "PROVIDER_RATIO: 3:1",
        "REQUIRED_CLAUDE_RATIO=3",
        "MIN_CLAUDE_RATIO: 2",
        "RATIO_INVARIANT",
        "ENFORCED_PROVIDER_RATIO",
    ],
)
def test_hard_provider_ratio_is_rejected(sandbox: Path, injected: str) -> None:
    """A ratio may be a planning SLO. It may never be an enforced routing or correctness constraint."""
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", injected + "\n\n" + text)
    found = failures(sandbox)
    assert found, "a hard provider ratio was accepted: {}".format(injected)


def test_ratio_is_documented_as_an_slo_only() -> None:
    flat = " ".join((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig").split())
    assert "not a quota, not an invariant" in flat
    assert "There is no enforced provider ratio anywhere in this control plane." in flat


def test_capacity_reading_cannot_be_pinned_into_durable_doctrine() -> None:
    registry = validator.parse_surface_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "VOLATILE_STATE_FIELDS"
    )
    fields = {field for field, _cls in (registry or [])}
    for capacity_field in ("OPENAI_AGENTIC_CAPACITY", "CLAUDE_CAPACITY", "CAPACITY_ROUTING_MODE"):
        assert capacity_field in fields


def test_capacity_field_removed_from_the_volatile_registry_is_rejected(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "- CLAUDE_CAPACITY :: PROVIDER_CAPACITY\n", "")
    assert_rejects(sandbox, "CLAUDE_CAPACITY must be registered in VOLATILE_STATE_FIELDS")


# ---------------------------------------------------------------------------
# Task-specific effort and host selection
# ---------------------------------------------------------------------------


def test_effort_selection_stays_task_specific_and_canonical(sandbox: Path) -> None:
    canonical = read(sandbox, CANONICAL)
    flat = " ".join(canonical.split())
    assert "TASK_SPECIFIC_EFFORT_SELECTION" in flat
    assert "Do not choose effort by file count." in flat
    assert "De-escalation is mandatory" in flat
    patch(sandbox, CANONICAL, "TASK_SPECIFIC_EFFORT_SELECTION", "ALWAYS_MAXIMUM_EFFORT")
    assert_rejects(sandbox, "required contract token missing: TASK_SPECIFIC_EFFORT_SELECTION")


def test_host_selector_is_recorded_raw_and_kept_lowest_safe(sandbox: Path) -> None:
    canonical = read(sandbox, CANONICAL)
    flat = " ".join(canonical.split())
    assert "LOWEST_SAFE_HOST_SETTING" in flat
    assert "HOST_SETTING_RAW" in flat
    assert "Do NOT default every T4 audit to Ultra." in flat
    patch(sandbox, CANONICAL, "LOWEST_SAFE_HOST_SETTING", "HIGHEST_AVAILABLE_HOST_SETTING")
    assert_rejects(sandbox, "required contract token missing: LOWEST_SAFE_HOST_SETTING")


# ---------------------------------------------------------------------------
# Audit-wait continuation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "token",
    [
        "AUDIT_WAIT_CONTINUATION",
        "PREPARED_NOT_REVIEWABLE_YET",
        "STALE_INVALIDATED",
        "CAPACITY_STOP",
        "PROVIDER_CAPACITY_CONTINUATION_MODE_V1",
        "USAGE_AWARE_CAPACITY_ROUTER_V1",
        "OPENAI_SHARED_AGENTIC_POOL",
        "NONPROTECTED_PROVIDER_BIAS",
    ],
)
def test_capacity_contract_tokens_must_be_present(sandbox: Path, token: str) -> None:
    text = read(sandbox, CANONICAL)
    write(sandbox, CANONICAL, text.replace(token, "REMOVED_CONTRACT"))
    assert_rejects(sandbox, "required contract token missing: {}".format(token))


def test_audit_wait_continuation_preserves_the_writer_and_pr_invariants() -> None:
    flat = " ".join((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig").split())
    assert "The frozen audited head is IMMUTABLE while waiting." in flat
    assert "One repository writer remains absolute." in flat
    assert "One open PR remains the default." in flat
    assert "A second PR is NOT opened while the frozen PR is open." in flat
    assert "No mutation of the frozen PR merely to look busy." in flat
    assert "PREPARED_NOT_REVIEWABLE_YET" in flat
    assert "never silently promoted" in flat
    assert "Never create speculative work solely to appear busy." in flat


def test_prepared_work_is_not_execution_authority() -> None:
    """A prepared branch and a prepared Work packet both carry preparation, never authorization."""
    flat = " ".join((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig").split())
    assert "WORK_PREPARED_NOT_AUTHORIZED" in flat
    assert "prepared, not reviewable" in flat or "PREPARED_NOT_REVIEWABLE_YET" in flat
    assert "re-prove ancestry, base and dependencies BEFORE opening a PR" in flat


# ---------------------------------------------------------------------------
# P2-01  `max` legality is PER FAMILY, never a property of the effort itself
# ---------------------------------------------------------------------------


def _max_family_rows() -> list[str]:
    rows = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "MAX_EFFORT_FAMILY_TRIGGERS"
    )
    assert rows is not None
    return rows


def test_max_effort_family_table_matches_the_oracle() -> None:
    parsed = {}
    for row in _max_family_rows():
        parts = [p.strip() for p in row.split("::")]
        assert len(parts) == 3 and parts[2], row
        parsed[parts[0]] = {i.strip() for i in parts[1].split(",") if i.strip()}
    assert parsed == ORACLE_MAX_EFFORT_FAMILY_INTENTS
    assert set(parsed) == ORACLE_MAX_EFFORT_CLASSES


@pytest.mark.parametrize(
    ("task_class", "task_intent", "legal"),
    [
        ("T3B", "IMPLEMENTATION", True),
        ("T3B", "REPAIR", True),
        ("T3B", "ARCHITECTURE", False),
        ("T3B", "REVIEW", False),
        ("T3B", "PROMPT_ARCHITECTURE", False),
        ("T3D", "ARCHITECTURE", True),
        ("T3D", "IMPLEMENTATION", False),
        ("T3E", "PROMPT_ARCHITECTURE", True),
        ("T4", "CLASS_C_CROSS_CONTRACT", True),
        ("T3A", "IMPLEMENTATION", False),
        ("T3C", "REVIEW", False),
    ],
)
def test_max_effort_legality_is_decided_per_family(task_class: str, task_intent: str, legal: bool) -> None:
    """The defect made the documented T3D/T3E/T4 max branches unreachable; these prove they are not."""
    assert validator.max_effort_is_legal(_max_family_rows(), task_class, task_intent) is legal


def test_dropping_a_family_from_the_max_table_is_rejected(sandbox: Path) -> None:
    patch(
        sandbox,
        CANONICAL,
        "- T3D :: ARCHITECTURE :: named central capability-critical architecture reasoning problem\n",
        "",
    )
    assert_rejects(sandbox, "MAX_EFFORT_CLASSES declares")


def test_mutation_only_family_cannot_reach_max_through_a_read_only_intent(sandbox: Path) -> None:
    patch(
        sandbox,
        CANONICAL,
        "- T3B :: IMPLEMENTATION,REPAIR :: named capability-critical",
        "- T3B :: IMPLEMENTATION,REPAIR,REVIEW :: named capability-critical",
    )
    assert_rejects(sandbox, "T3B may not reach max")


@pytest.mark.parametrize(
    "injected",
    [
        "Effort note: max is only legal in T3B.",
        "Remember that max only exists in T3B.",
        "Escalation to max only in T3B, under the T3B contract.",
    ],
)
def test_restating_max_as_a_single_family_restriction_is_rejected(sandbox: Path, injected: str) -> None:
    write(sandbox, "CLAUDE.md", injected + "\n\n" + read(sandbox, "CLAUDE.md"))
    assert_rejects(sandbox, "max restricted globally")


# ---------------------------------------------------------------------------
# P2-02  Host discovery beats registry assumption
# ---------------------------------------------------------------------------


def test_host_discovery_globs_match_the_oracle() -> None:
    globs = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "HOST_DISCOVERY_SCAN_PATHS"
    )
    assert globs == ORACLE_HOST_DISCOVERY_GLOBS


@pytest.mark.parametrize("rel", sorted(ORACLE_FINAL_RETIRED_HOST_PATHS))
def test_final_legacy_host_surfaces_are_absent(rel: str) -> None:
    """Held literally: these must be gone from the tree, not merely unregistered."""
    assert not (REPO_ROOT / rel).exists(), "legacy host surface still present: {}".format(rel)


def test_every_declared_host_discovery_location_holds_only_registered_surfaces() -> None:
    """Closed world: a discovery location holds an active surface, the historical rule, or nothing."""
    allowed = (
        set(ORACLE_ACTIVE_DOCTRINE_SURFACES)
        | ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS
        | set(ORACLE_HISTORICAL_HOST_SURFACES)
        | set(ORACLE_HOST_EXECUTABLE_WORKFLOWS)
    )
    for pattern in ORACLE_HOST_DISCOVERY_GLOBS:
        found = sorted(p.relative_to(REPO_ROOT).as_posix() for p in REPO_ROOT.glob(pattern) if p.is_file())
        stray = [rel for rel in found if rel not in allowed]
        assert stray == [], "host auto-discovery location holds unregistered surfaces: {} -> {}".format(pattern, stray)


@pytest.mark.parametrize(
    "rel",
    [
        ".github/agents/revived.agent.md",
        ".github/skills/revived-skill/SKILL.md",
        ".github/prompts/revived.prompt.md",
        ".github/prompts/nested/revived.prompt.md",
        ".github/instructions/revived.instructions.md",
        ".github/instructions/nested/revived.instructions.md",
        ".claude/skills/revived-skill/SKILL.md",
        ".codex/skills/revived-skill/SKILL.md",
        ".cursor/rules/revived.mdc",
    ],
)
def test_a_new_auto_discovered_surface_is_rejected(sandbox: Path, rel: str) -> None:
    """Registry membership decides authority; it does not decide what a host loads."""
    target = sandbox / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# revived host surface\n", encoding="utf-8", newline="\n")
    assert_rejects(sandbox, "host auto-discovery surface present but not registered")


def test_retired_registry_contains_the_final_seven() -> None:
    retired = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "RETIRED_CONTROL_PLANE_PATHS"
    )
    assert retired is not None
    assert ORACLE_FINAL_RETIRED_HOST_PATHS <= set(retired)
    assert len(retired) == ORACLE_RETIRED_PATH_COUNT


# ---------------------------------------------------------------------------
# P2-03  The oracle cannot be its own only anchor
# ---------------------------------------------------------------------------


def test_oracle_bootstrap_path_is_a_literal_outside_the_registry() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    assert 'BOOTSTRAP_ORACLE_PATH = "{}"'.format(ORACLE_BOOTSTRAP_PATH) in source


def test_deleting_the_oracle_and_its_registry_entry_together_still_fails(sandbox: Path) -> None:
    """The exact reported hole: co-deletion previously left a self-consistent control plane."""
    patch(sandbox, CANONICAL, "- {}\n".format(ORACLE_BOOTSTRAP_PATH), "")
    (sandbox / ORACLE_BOOTSTRAP_PATH).unlink()
    assert_rejects(sandbox, "independent contract oracle missing")


def test_removing_the_ci_anchor_as_well_still_fails(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "- {}\n".format(ORACLE_BOOTSTRAP_PATH), "")
    (sandbox / ORACLE_BOOTSTRAP_PATH).unlink()
    patch(
        sandbox,
        ".github/workflows/ci.yml",
        "      - name: Agent OS contract oracle anchor\n        run: {}\n\n".format(ORACLE_CI_ANCHOR_COMMAND),
        "",
    )
    found = failures(sandbox)
    assert any("independent contract oracle missing" in f for f in found)
    assert any("bootstrap anchor" in f for f in found)


# ---------------------------------------------------------------------------
# P2-04  Complete ephemeral inventory + typed exemption regions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", ["CLAUDE.md", "AGENTS.md", "docs/crypto_core/agent_workflow.md"])
def test_next_safe_action_assignment_is_rejected(sandbox: Path, rel: str) -> None:
    """The reported gap: a next action pinned into durable doctrine passed the scan."""
    write(sandbox, rel, "NEXT_SAFE_ACTION: MERGE_PR\n\n" + read(sandbox, rel))
    assert_rejects(sandbox, "volatile state assigned in a durable surface: NEXT_SAFE_ACTION")


@pytest.mark.parametrize(
    "injected",
    ["CAPABILITY_MODE: Ultra", "HOST_SETTING_RAW: Extra High", "MODEL_EVIDENCE_SOURCE: RUNTIME_TELEMETRY"],
)
def test_runtime_model_state_assignment_is_rejected(sandbox: Path, injected: str) -> None:
    write(sandbox, "CLAUDE.md", injected + "\n\n" + read(sandbox, "CLAUDE.md"))
    assert_rejects(sandbox, "volatile state assigned in a durable surface")


def test_crossed_exemption_regions_cannot_hide_a_pin(sandbox: Path) -> None:
    """A shared depth counter would let one region type close another and exempt the remainder."""
    crossed = (
        "<!-- HISTORICAL_RECORD_BEGIN -->\n"
        "<!-- EXAMPLE_ONLY_BEGIN -->\n"
        "<!-- HISTORICAL_RECORD_END -->\n"
        "CURRENT_CI_STATE=GREEN\n"
        "<!-- EXAMPLE_ONLY_END -->\n\n"
    )
    write(sandbox, "CLAUDE.md", crossed + read(sandbox, "CLAUDE.md"))
    found = failures(sandbox)
    assert any("crossed exemption regions" in f or "nested inside an open" in f for f in found)


def test_reverse_crossed_exemption_regions_are_rejected(sandbox: Path) -> None:
    crossed = (
        "<!-- EXAMPLE_ONLY_BEGIN -->\n"
        "<!-- HISTORICAL_RECORD_BEGIN -->\n"
        "<!-- EXAMPLE_ONLY_END -->\n"
        "CURRENT_CI_STATE=GREEN\n"
        "<!-- HISTORICAL_RECORD_END -->\n\n"
    )
    write(sandbox, "CLAUDE.md", crossed + read(sandbox, "CLAUDE.md"))
    found = failures(sandbox)
    assert any("crossed exemption regions" in f or "nested inside an open" in f for f in found)


def test_typed_stack_reports_the_exact_region_type() -> None:
    lines = [
        "<!-- HISTORICAL_RECORD_BEGIN -->",
        "<!-- EXAMPLE_ONLY_END -->",
        "text",
    ]
    found, active = validator.exemption_scan("fixture", lines)
    assert any("crossed exemption regions" in f for f in found)
    assert ("HISTORICAL_RECORD" in " ".join(found)) and ("EXAMPLE_ONLY" in " ".join(found))
    # The crossed pair is reported, and the trailing line stays ACTIVE rather than being exempted by
    # the mismatched closer - which is the whole point of typing the stack.
    assert [text for _lineno, text in active] == ["text"]


def test_wellformed_historical_region_still_exempts() -> None:
    lines = [
        "active line",
        "<!-- HISTORICAL_RECORD_BEGIN -->",
        "CURRENT_CI_STATE=GREEN",
        "<!-- HISTORICAL_RECORD_END -->",
        "another active line",
    ]
    found, active = validator.exemption_scan("fixture", lines)
    assert found == []
    assert [text for _lineno, text in active] == ["active line", "another active line"]


# ---------------------------------------------------------------------------
# P2-05  Manifest evidence SEMANTICS, not just topology
# ---------------------------------------------------------------------------


def _example() -> dict:
    return json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json").read_text(encoding="utf-8-sig")
    )


# ---------------------------------------------------------------------------
# P2-06  The CI gate must be one exact, enabled, fail-propagating step
# ---------------------------------------------------------------------------


def test_required_ci_commands_match_the_oracle() -> None:
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8-sig")
    assert "        run: {}\n".format(ORACLE_CI_VALIDATOR_COMMAND) in text
    assert "        run: {}\n".format(ORACLE_CI_ANCHOR_COMMAND) in text


# ---------------------------------------------------------------------------
# K7 - the continuity index must not overclaim the finite scan
# ---------------------------------------------------------------------------


def test_continuity_index_does_not_overclaim_the_deterministic_scan() -> None:
    """The subordinate index may not promise detection the finite scan cannot deliver.

    Asserted literally against the contract LANGUAGE rather than by asking the validator, because the
    defect being closed is documentation describing the validator as broader than it is. Deriving the
    expectation from the validator would make the two drift together silently.
    """
    text = (REPO_ROOT / "docs/crypto_core/continuity/CONTINUITY_INDEX.md").read_text(encoding="utf-8-sig")
    assert "Anything in this list that appears in a durable surface is a defect, and" not in text, (
        "the continuity index still claims the scan fails on ANY appearance of a current fact"
    )
    assert "DURABLE_STATE_CLAIM_BOUNDARY" in text
    assert "INDEPENDENT SEMANTIC AUDIT" in text
    for bounded_form in ("`PR #<n>` pin", "`main @ <hash>` pin", "VOLATILE_STATE_FIELDS"):
        assert bounded_form in text, "the index does not name the bounded form {}".format(bounded_form)


def test_english_current_state_prose_is_honestly_outside_the_scan(sandbox: Path) -> None:
    """The narrower documented claim is the TRUE one.

    Current-state prose using no registered field name and no literal pin form is NOT caught. That is
    precisely why no surface may promise that it is, and why the fix was to correct the documentation
    rather than to grow the scanner toward natural language.
    """
    text = read(sandbox, "CLAUDE.md")
    write(sandbox, "CLAUDE.md", text + "\nThe current CI result is green.\n")
    assert failures(sandbox) == []


# ---------------------------------------------------------------------------
# K8 - EFFECTIVE CI EXECUTION CONTEXT
#
# Exact `run` content proves WHAT would run. It proves nothing about WHETHER it runs, or whether its
# failure can fail the job. Every attack below keeps the documented command byte-for-byte intact and
# defeats the gate purely through execution context.
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Pre-audit QA closures: case-insensitive object ids, reachable manifest relations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "token"),
    [
        ("uppercase", "AF4CB1361521AB962A6E29153847532C441026C2"),
        ("mixed case", "Af4Cb1361521ab962A6e29153847532c441026C2"),
        ("lowercase", "af4cb1361521ab962a6e29153847532c441026c2"),
    ],
    ids=["uppercase object id", "mixed-case object id", "lowercase object id"],
)
def test_durable_scan_rejects_an_object_id_in_any_letter_case(sandbox: Path, label: str, token: str) -> None:
    """Git accepts uppercase object ids, so a lowercase-only rule was a real head-pin bypass."""
    text = read(sandbox, "AGENTS.md")
    write(sandbox, "AGENTS.md", "Current head is {}.\n\n".format(token) + text)
    assert_rejects(sandbox, "AGENTS.md")


def test_ordinary_prose_is_not_mistaken_for_an_object_id(sandbox: Path) -> None:
    """Case-insensitivity must not turn ordinary words into false head pins."""
    text = read(sandbox, "AGENTS.md")
    write(sandbox, "AGENTS.md", text + "\nThe DECODED FACADE and the added cabbage are not object ids.\n")
    assert failures(sandbox) == []


# ---------------------------------------------------------------------------
# K5 - MEANINGFUL_VALUE_CLASS_REGISTRY_V1
#
# Derived from the CLASS vocabulary, not from the fields a past review happened to name.
# `value is not None` answered a topology question while the contract asks an evidential
# one, and that gap applied to every proof-paired field at once.
# ---------------------------------------------------------------------------


def _example_manifest() -> dict:
    return json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json").read_text(encoding="utf-8-sig")
    )


# ---------------------------------------------------------------------------
# K8 - CONTROLLER_EXACT_BYTE_PREMERGE_PROOF_V1
#
# These are CLAIM-BOUNDARY probes, not parser probes. The parser is retired: a repository
# cannot prove from its own bytes that its own CI step ran, so every spelling-of-YAML
# attack that used to matter is now out of scope by construction rather than by enumeration.
# ---------------------------------------------------------------------------

_RETIRED_PARSER_SYMBOLS = [
    "YAML_KEY_RE",
    "JOB_KEY_INDENT",
    "REQUIRED_CI_JOB",
    "FORBIDDEN_CI_JOB_KEYS",
    "FORBIDDEN_CI_GATE_STEP_KEYS",
    "_yaml_key",
    "_child_lines",
    "_defaults_declare_shell",
    "_job_has_key",
    "_step_has_key",
    "_step_key",
    "_step_executable_lines",
    "_find_exact_step",
    "_job_steps",
    "_workflow_job_bodies",
    "_check_ci_wiring",
]


@pytest.mark.parametrize("symbol", _RETIRED_PARSER_SYMBOLS)
def test_partial_yaml_parser_stays_retired(symbol: str) -> None:
    """Retired, not extended. Reintroducing any of these reopens the abstraction that failed."""
    source = VALIDATOR_PATH.read_text(encoding="utf-8-sig")
    assert symbol not in source, "the retired workflow parser reappeared: {}".format(symbol)
    assert not hasattr(validator, symbol), symbol


def test_validator_makes_no_self_enforcement_claim() -> None:
    """The validator must not assert a property about GitHub's runtime that it cannot hold.

    Compared on whitespace-normalized text: the claim is about content, and coupling an
    assertion to where a paragraph happens to wrap makes it fail for the wrong reason.
    """
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "CI_ENFORCEMENT_IS_NOT_SELF_PROVABLE" in canonical
    for claim in (
        "that the repository can prove its own CI step is executed",
        "that a required status context identifies any particular workflow file, path or revision",
        "that parsing a workflow's YAML establishes GitHub's runtime execution semantics",
        "that a repository-controlled digest or self-check is external acceptance or merge authority",
        "that premerge configuration re-proof is atomic",
    ):
        assert claim in canonical, claim


def test_controller_premerge_protocol_is_declared() -> None:
    """The property moved to the layer that can hold it, and the protocol is written down."""
    canonical = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert "CONTROLLER_EXACT_BYTE_PREMERGE_PROOF_V1" in canonical
    assert "WORKFLOW_CHANGE_INVALIDATES_ACCEPTANCE" in canonical
    assert "CONFIG_RACE_HONESTY" in canonical
    for duty in ("workflow inventory", "blob identity", "skipped", "branch-protection", "SAFETY_BLOCKER"):
        assert duty in canonical, duty


def test_status_context_is_not_treated_as_workflow_identity() -> None:
    """Both subordinate surfaces must state the limit, not imply the stronger property."""
    workflow_doc = _normalized(REPO_ROOT / "docs/crypto_core/agent_workflow.md")
    assert "no repository can establish its own CI execution from its own bytes" in workflow_doc
    assert "`skipped`, `neutral` and `cancelled` are never acceptance" in workflow_doc
    agents = _normalized(REPO_ROOT / "AGENTS.md")
    assert "cannot prove from its own bytes that its own CI step was executed" in agents


def test_committed_workflow_still_carries_the_gate_commands_as_evidence() -> None:
    """EVIDENCE, not enforcement.

    That the file names these commands is a fact about the file. It is NOT proof they ran; that is
    the controller's premerge duty against live GitHub evidence (canonical section 17.1).
    """
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8-sig")
    assert "        run: {}\n".format(ORACLE_CI_VALIDATOR_COMMAND) in text
    assert "        run: {}\n".format(ORACLE_CI_ANCHOR_COMMAND) in text


# ---------------------------------------------------------------------------
# The documented manifest gate runs BOTH halves: schema shape and semantic relations
# ---------------------------------------------------------------------------


def _gate(tmp_path: Path, instance: object) -> list:
    compiled = tmp_path / "state_manifest.json"
    compiled.write_text(json.dumps(instance), encoding="utf-8")
    return validator.check_manifest_file(REPO_ROOT, compiled)


def test_merge_gate_never_accepts_a_skipped_required_check() -> None:
    """One surface still said "accepted skip" while the canonical protocol forbids it."""
    workflow_doc = _normalized(REPO_ROOT / "docs/crypto_core/agent_workflow.md")
    assert "accepted skip" not in workflow_doc
    assert "`skipped`, `neutral` or `cancelled` load-bearing check is never acceptance" in workflow_doc


# ---------------------------------------------------------------------------
# P2-1  TEXT_EVIDENCE_LNPS_V1 and BOUNDED_REPO_BRANCH_IDENTIFIER_V1
#
# The contract is a POSITIVE acceptance rule over Unicode MAJOR general categories, so the
# probes are generated BY CATEGORY. No individual code point is the contract; the ones named
# below are representatives, and a code point assigned in a future Unicode version is covered
# on the day it is assigned.
# ---------------------------------------------------------------------------

ORACLE_TEXT_PAYLOAD_MAJORS = ("L", "N", "P", "S")
ORACLE_EMPTY_MAJORS = ("M", "Z", "C")


def _representatives(major: str, limit: int = 6) -> list[str]:
    """Sample real code points of one Unicode MAJOR class, spread across the space."""
    found = []
    for cp in range(0x110000):
        ch = chr(cp)
        if unicodedata.category(ch)[0] == major:
            found.append(ch)
            if len(found) == limit:
                break
    assert found, "no representative found for major class {}".format(major)
    return found


@pytest.mark.parametrize("major", ORACLE_TEXT_PAYLOAD_MAJORS)
def test_text_evidence_accepts_every_payload_major_class(major: str) -> None:
    for ch in _representatives(major):
        assert validator.carries_text_payload(ch), "{} rejected U+{:04X}".format(major, ord(ch))


@pytest.mark.parametrize("major", ORACLE_EMPTY_MAJORS)
def test_text_evidence_rejects_every_payload_empty_major_class(major: str) -> None:
    for ch in _representatives(major):
        assert not validator.carries_text_payload(ch), "{} accepted U+{:04X}".format(major, ord(ch))


def test_text_evidence_rejects_mixtures_of_payload_empty_classes() -> None:
    mixed = "".join(_representatives(major, 1)[0] for major in ORACLE_EMPTY_MAJORS)
    assert not validator.carries_text_payload(mixed)
    assert not validator.carries_text_payload("")


def test_text_evidence_accepts_payload_with_combining_marks() -> None:
    """A mark attached to a payload character does not remove the payload."""
    mark = _representatives("M", 1)[0]
    assert validator.carries_text_payload("a" + mark)


@pytest.mark.parametrize(
    ("label", "value", "accepted"),
    [
        ("valid slug", "demircaliskan2009-pixel/BIST_ELITE_CORE", True),
        ("no separator", "ownername", False),
        ("three segments", "a/b/c", False),
        ("trailing space", "owner/name ", False),
        ("empty", "", False),
        ("payload-empty", "​/​", False),
    ],
    ids=["valid slug", "no separator", "three segments", "trailing space", "empty", "payload-empty"],
)
def test_repo_identifier_grammar(label: str, value: str, accepted: bool) -> None:
    assert (not validator.repo_identifier_failures(value)) is accepted, label


@pytest.mark.parametrize(
    ("label", "value", "accepted"),
    [
        ("project branch", "chore/crypto-core-agent-os-v2-1-final-fixed-point-replacement-pr4", True),
        ("main", "main", True),
        ("leading slash", "/x", False),
        ("trailing slash", "x/", False),
        ("empty segment", "a//b", False),
        ("double dot", "a..b", False),
        ("reflog syntax", "a@{0}", False),
        ("trailing dot", "a.", False),
        ("lock suffix", "a.lock", False),
        ("zero-width contamination", "ma​in", False),
        ("payload-empty", "​", False),
        ("empty", "", False),
    ],
    ids=[
        "project branch",
        "main",
        "leading slash",
        "trailing slash",
        "empty segment",
        "double dot",
        "reflog syntax",
        "trailing dot",
        "lock suffix",
        "zero-width contamination",
        "payload-empty",
        "empty",
    ],
)
def test_branch_identifier_grammar(label: str, value: str, accepted: bool) -> None:
    assert (not validator.branch_identifier_failures(value)) is accepted, label


# ---------------------------------------------------------------------------
# P2-2  CANONICAL_TYPED_OPERATIONAL_GRAMMAR_V1 and GENERATED_STATE_MANIFEST_SCHEMA_V1
# ---------------------------------------------------------------------------

ORACLE_PROOF_PAIRED_GRAMMAR = {
    "branch": "TOKEN_BRANCH",
    "base_sha": "HASH_IDENTIFIER",
    "base_tree": "HASH_IDENTIFIER",
    "head_sha": "HASH_IDENTIFIER",
    "head_tree": "HASH_IDENTIFIER",
    "pr_number": "POSITIVE_INT",
    "pr_state": "NORMALIZED_ENUM",
    "open_pr_count": "NONNEGATIVE_INT",
    "ci_state": "NORMALIZED_ENUM",
    "review_threads_unresolved": "NONNEGATIVE_INT",
    "completed_gates": "STRUCTURED_LIST",
    "blockers": "STRUCTURED_LIST",
    "openai_agentic_capacity": "NORMALIZED_ENUM",
    "claude_capacity": "NORMALIZED_ENUM",
    "capacity_routing_mode": "NORMALIZED_ENUM",
    "next_safe_action": "OPERATIONAL_TEXT",
}

ORACLE_RETIRED_SCHEMA_INTERPRETER = (
    "_structure_failures",
    "manifest_structure_failures",
    "_resolve_ref",
    "_carries_visible_text",
    "INVISIBLE_UNICODE_CATEGORIES",
    "schema_value_shape",
    "meaningful_value_failures",
)


def test_registry_and_grammar_agree_in_both_directions() -> None:
    """The canonical registry declares the class; the grammar implements it. Neither may drift."""
    rows = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "PROOF_PAIRED_MANIFEST_FIELDS"
    )
    parsed = {}
    for row in rows or []:
        field, _sep, value_class = row.partition("::")
        parsed[field.strip()] = value_class.strip()
    assert parsed == ORACLE_PROOF_PAIRED_GRAMMAR
    assert {f: n["kind"] for f, n in validator.PROOF_PAIRED_GRAMMAR.items()} == ORACLE_PROOF_PAIRED_GRAMMAR
    for value_class in ORACLE_PROOF_PAIRED_GRAMMAR.values():
        assert value_class in validator.VALUE_CLASSES


@pytest.mark.parametrize("symbol", ORACLE_RETIRED_SCHEMA_INTERPRETER)
def test_partial_schema_interpreter_stays_retired(symbol: str) -> None:
    """Retired, not extended. Reintroducing any of these reopens the abstraction that failed."""
    source = VALIDATOR_PATH.read_text(encoding="utf-8-sig")
    assert symbol not in source, "the retired schema interpreter reappeared: {}".format(symbol)
    assert not hasattr(validator, symbol), symbol


def test_committed_schema_equals_the_generated_schema() -> None:
    committed = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    )
    assert committed == validator.emit_manifest_schema()
    assert committed["$schema"] == "https://json-schema.org/draft/2020-12/schema"


def test_hand_edited_schema_fails_the_equality_gate(sandbox: Path) -> None:
    """The schema is generated. Editing it by hand is the drift this gate exists to catch."""
    path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, path))
    schema["properties"]["repo"]["maxLength"] = 2
    write(sandbox, path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "does not equal the schema generated")


def test_schema_only_extra_requirement_fails_the_equality_gate(sandbox: Path) -> None:
    path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, path))
    schema["required"].append("ghost_field")
    write(sandbox, path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "does not equal the schema generated")


_GRAMMAR_SHAPES = [None, True, False, 0, 1, -1, 1.5, "", "  ", "x", [], [1], {}, {"a": 1}, "​", "͏"]


def test_operational_grammar_is_total() -> None:
    """Every attacker-controlled JSON value yields reasons or acceptance - never an exception."""
    example = _example_manifest()
    for field in list(example):
        for value in _GRAMMAR_SHAPES:
            probe = json.loads(json.dumps(example))
            probe[field] = value
            validator.check_manifest_instance("fuzz", probe)
    for block, key in (("model_runtime", "model_actual"), ("authorization", "mutation_scope")):
        for value in _GRAMMAR_SHAPES:
            probe = json.loads(json.dumps(example))
            probe[block][key] = value
            validator.check_manifest_instance("fuzz", probe)
    for value in _GRAMMAR_SHAPES:
        validator.check_manifest_instance("fuzz", value)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("unknown top-level field", lambda m: m.update({"surprise": 1})),
        ("unknown nested field", lambda m: m["model_runtime"].update({"surprise": 1})),
        ("missing required field", lambda m: m.pop("repo")),
        ("wrong nullability", lambda m: m.update({"repo": None})),
        ("invalid enum", lambda m: m.update({"ci_state": "MAUVE"})),
        ("invalid hash", lambda m: m.update({"head_sha": "zz", "head_sha_evidence": "PROVEN"})),
        ("invalid branch token", lambda m: m.update({"branch": "a..b"})),
        ("payload-empty text", lambda m: m.update({"next_safe_action": "​"})),
        ("boolean where integer expected", lambda m: m.update({"open_pr_count": True})),
        (
            "invalid list element",
            lambda m: m.update({"blockers": [{"id": "x", "severity": "P9", "state": "OPEN", "repair_count": 0}]}),
        ),
        ("wrong const", lambda m: m.update({"schema": "STATE_MANIFEST_V9"})),
    ],
    ids=[
        "unknown top-level field",
        "unknown nested field",
        "missing required field",
        "wrong nullability",
        "invalid enum",
        "invalid hash",
        "invalid branch token",
        "payload-empty text",
        "boolean where integer expected",
        "invalid list element",
        "wrong const",
    ],
)
def test_operational_grammar_is_closed_world(label: str, mutate) -> None:
    manifest = _example_manifest()
    mutate(manifest)
    assert validator.check_manifest_instance("probe", manifest), "the grammar accepted: {}".format(label)


@pytest.mark.parametrize(
    ("field", "value"),
    [("open_pr_count", 0), ("review_threads_unresolved", 0), ("completed_gates", []), ("blockers", [])],
    ids=["zero open PRs", "zero unresolved threads", "no completed gates", "no blockers"],
)
def test_legitimately_empty_facts_remain_provable(field: str, value: object) -> None:
    """The control that forbids a truthiness predicate: zero and [] are real, provable facts."""
    manifest = _example_manifest()
    manifest[field] = value
    manifest["{}_evidence".format(field)] = "PROVEN"
    if field == "review_threads_unresolved":
        # PROOF_TARGET_BINDINGS: an empty fact is still a fact ABOUT a pull request, so its target is proven.
        manifest.update(pr_number=7, pr_number_evidence="PROVEN")
    assert not [item for item in validator.check_manifest_instance("probe", manifest) if field in item]


def test_committed_example_passes_the_operational_gate() -> None:
    assert validator.check_manifest_instance("example", _example_manifest()) == []


@pytest.mark.parametrize(
    ("label", "evidence", "value", "accepted"),
    [
        ("proven value", "PROVEN", "main", True),
        ("proven null", "PROVEN", None, False),
        ("unknown null", "UNKNOWN", None, True),
        ("unknown value", "UNKNOWN", "main", False),
        ("bad evidence word", "MAYBE", "main", False),
    ],
    ids=["proven value", "proven null", "unknown null", "unknown value", "bad evidence word"],
)
def test_proof_pair_relations(label: str, evidence: str, value: object, accepted: bool) -> None:
    manifest = _example_manifest()
    manifest["branch"] = value
    manifest["branch_evidence"] = evidence
    found = [item for item in validator.check_manifest_instance("probe", manifest) if "branch" in item]
    assert (not found) is accepted, label


@pytest.mark.parametrize(
    ("source", "actual", "host_raw", "accepted"),
    [
        ("RUNTIME_TELEMETRY", "claude-opus-5", None, True),
        ("RUNTIME_TELEMETRY", None, None, False),
        ("RUNTIME_TELEMETRY", "​", None, False),
        ("USER_ATTESTED_UI_SELECTION", "claude-opus-5", "Opus 5 / Max", True),
        ("USER_ATTESTED_UI_SELECTION", None, "Max", False),
        ("USER_ATTESTED_UI_SELECTION", None, None, False),
        ("CONFIGURATION_EVIDENCE_ONLY", "claude-opus-5", None, False),
    ],
    ids=[
        "telemetry proven",
        "telemetry null",
        "telemetry payload-empty",
        "attested identity recorded",
        "attested only a shared host label",
        "attested nothing",
        "configuration claims execution",
    ],
)
def test_runtime_evidence_class_constrains_what_may_be_populated(
    source: str, actual: object, host_raw: object, accepted: bool
) -> None:
    """The identity DIMENSION, judged on its own evidence and its own observation."""
    manifest = _example_manifest()
    manifest["model_runtime"]["model_evidence_source"] = source
    manifest["model_runtime"]["model_actual"] = actual
    manifest["model_runtime"]["host_setting_raw"] = host_raw
    # Isolate the CLASS: the required identity agrees with the observation, so anything this probe
    # rejects is rejected by the evidence class and not by the separate identity relation.
    if isinstance(actual, str) and not validator.operational_text_failures(actual):
        manifest["model_runtime"]["model_id"] = actual
        manifest["model_runtime"]["model_requested"] = actual
    found = [
        item
        for item in validator.manifest_relation_failures("probe", manifest)
        if "model_" in item or "attested" in item
    ]
    assert (not found) is accepted


def test_manifest_never_carries_merge_authority() -> None:
    manifest = _example_manifest()
    manifest["authorization"]["merge_authorized"] = True
    assert [item for item in validator.check_manifest_instance("probe", manifest) if "merge_authorized" in item]


def test_ultra_is_never_an_effort_value_in_the_grammar() -> None:
    assert "ultra" not in [value.lower() for value in validator.EFFORT_VALUES]


# ---------------------------------------------------------------------------
# P2-3  EXECUTABLE_SUBORDINATE_AUTHORITY_BOUNDARY_V1
# ---------------------------------------------------------------------------

# Needles are built from fragments so the literal never appears contiguously in this file.
# Without that, this self-referential absence check could never be satisfied.
ORACLE_RETIRED_SELF_ENFORCEMENT = [
    (
        "scripts/crypto_core/validate_agent_os_v2.py",
        "an EXECUTABLE validator invocation inside the " + "required CI job, not a mention of its path",
    ),
    ("scripts/crypto_core/validate_agent_os_v2.py", "legacy retirement and " + "CI wiring"),
    ("tests/crypto_core/test_agent_os_v2_contract.py", "The exact command shapes the " + "required CI job must run"),
    ("tests/crypto_core/test_agent_os_v2_contract.py", "# CI" + " wiring\n"),
    ("tests/crypto_core/test_agent_os_v2_contract.py", "CI wiring must be an " + "executable step, not a mention"),
]


@pytest.mark.parametrize(
    "rel", ["scripts/crypto_core/validate_agent_os_v2.py", "tests/crypto_core/test_agent_os_v2_contract.py"]
)
def test_executables_declare_a_subordinate_role(rel: str) -> None:
    """Both executables were outside the marker system, which is how their prose drifted."""
    docstring = validator.module_docstring((REPO_ROOT / rel).read_text(encoding="utf-8-sig"))
    assert docstring is not None
    assert re.findall(r"<!--\s*CONTROL_PLANE_ROLE:\s*([A-Z_]+)\s*-->", docstring) == ["EXECUTABLE_SUBORDINATE"]
    assert docstring.count("<!-- CONTROL_PLANE_AUTHORITY_REF: {} -->".format(CANONICAL)) == 1


@pytest.mark.parametrize(
    "rel", ["scripts/crypto_core/validate_agent_os_v2.py", "tests/crypto_core/test_agent_os_v2_contract.py"]
)
def test_executables_reproduce_the_canonical_negative_boundary(rel: str) -> None:
    declared = validator.block_lines(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "EXECUTABLE_NEGATIVE_BOUNDARY"
    )
    assert declared is not None
    sentence = [line for line in declared if line.strip()]
    assert len(sentence) == 1, "canonical must declare exactly one boundary sentence"
    docstring = validator.module_docstring((REPO_ROOT / rel).read_text(encoding="utf-8-sig")) or ""
    assert re.sub(r"\s+", " ", sentence[0].strip()) in re.sub(r"\s+", " ", docstring)


@pytest.mark.parametrize(
    ("rel", "needle"),
    ORACLE_RETIRED_SELF_ENFORCEMENT,
    ids=[str(i) for i in range(len(ORACLE_RETIRED_SELF_ENFORCEMENT))],
)
def test_known_retired_self_enforcement_claims_stay_removed(rel: str, needle: str) -> None:
    """A historical REMOVAL RECEIPT, closed at five entries by construction.

    It names statements deleted in this change, so it refers to the past and cannot grow. It is
    NOT a forbidden-phrase vocabulary, and nothing here detects a newly-worded equivalent claim.
    """
    assert needle not in (REPO_ROOT / rel).read_text(encoding="utf-8-sig")


def test_architecture_states_that_paraphrase_is_not_mechanically_detectable() -> None:
    """The finite mechanism must describe its own finite limit, as K7 established."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "EXECUTABLE_SUBORDINATE" in canonical
    assert "REMOVAL RECEIPT" in canonical
    assert "nothing here detects a newly-worded equivalent claim" in canonical
    assert "INDEPENDENT SEMANTIC AUDIT" in canonical


# ---------------------------------------------------------------------------
# P2-4  TESTED_REVISION_BINDING_V1
# ---------------------------------------------------------------------------

_ORACLE_BASE = "1" * 40
_ORACLE_HEAD = "2" * 40
_ORACLE_TREE = "3" * 40
_ORACLE_MERGE = "4" * 40


def _revision_evidence(**overrides: object) -> dict:
    evidence = {
        "event": "pull_request",
        "audited_pr_head": _ORACLE_HEAD,
        "audited_head_tree": _ORACLE_TREE,
        "current_base": _ORACLE_BASE,
        "workflow_run_id": 1,
        "workflow_path": ".github/workflows/ci.yml",
        "run_reported_head": _ORACLE_HEAD,
        "actual_checkout_revision": _ORACLE_MERGE,
        "tested_revision_parents": [_ORACLE_BASE, _ORACLE_HEAD],
        "tested_revision_tree": _ORACLE_TREE,
        "checkout_ref_override": False,
        "tests_job_conclusion": "success",
        "agent_os_gate_step_conclusions": {
            "Agent OS control-plane contract": "success",
            "Agent OS contract oracle anchor": "success",
        },
        "required_contexts": ["tests", "CodeQL", "codeql"],
    }
    evidence.update(overrides)
    return evidence


@pytest.mark.parametrize(
    ("label", "overrides", "accepted"),
    [
        ("valid pull_request tuple", {}, True),
        ("base moved", {"tested_revision_parents": ["f" * 40, _ORACLE_HEAD]}, False),
        ("head moved", {"tested_revision_parents": [_ORACLE_BASE, "f" * 40]}, False),
        ("not a merge revision", {"tested_revision_parents": [_ORACLE_BASE]}, False),
        ("tested tree differs from audited tree", {"tested_revision_tree": "9" * 40}, False),
        ("checkout revision unprovable", {"actual_checkout_revision": None}, False),
        ("checkout ref overridden", {"checkout_ref_override": True}, False),
        ("tests job skipped", {"tests_job_conclusion": "skipped"}, False),
        ("tests job neutral", {"tests_job_conclusion": "neutral"}, False),
        (
            "gate step cancelled",
            {
                "agent_os_gate_step_conclusions": {
                    "Agent OS control-plane contract": "cancelled",
                    "Agent OS contract oracle anchor": "success",
                }
            },
            False,
        ),
        ("gate steps absent", {"agent_os_gate_step_conclusions": {}}, False),
        ("workflow source unproven", {"workflow_path": ""}, False),
        ("event not accepted", {"event": "workflow_dispatch"}, False),
        (
            "push tuple",
            {"event": "push", "actual_checkout_revision": _ORACLE_HEAD, "tested_revision_parents": []},
            True,
        ),
        (
            "push against another revision",
            {"event": "push", "actual_checkout_revision": "9" * 40, "tested_revision_parents": []},
            False,
        ),
        ("parents not a list", {"tested_revision_parents": "nope"}, False),
    ],
    ids=[
        "valid pull_request tuple",
        "base moved",
        "head moved",
        "not a merge revision",
        "tested tree differs from audited tree",
        "checkout revision unprovable",
        "checkout ref overridden",
        "tests job skipped",
        "tests job neutral",
        "gate step cancelled",
        "gate steps absent",
        "workflow source unproven",
        "event not accepted",
        "push tuple",
        "push against another revision",
        "parents not a list",
    ],
)
def test_tested_revision_binding(label: str, overrides: dict, accepted: bool) -> None:
    result = validator.tested_revision_failures(_revision_evidence(**overrides))
    assert (not result) is accepted, "{}: {}".format(label, result)


def test_tested_revision_evidence_is_total() -> None:
    for value in [None, True, 0, "", [], {}, {"event": "pull_request"}]:
        validator.tested_revision_failures(value)


def test_run_reported_head_is_not_assumed_to_be_the_tested_revision() -> None:
    """Proven on real evidence: for a pull_request the run reports the PR head while GitHub
    checks out a synthetic merge revision. Treating them as one was the P2-4 root."""
    evidence = _revision_evidence()
    assert evidence["run_reported_head"] != evidence["actual_checkout_revision"]
    assert validator.tested_revision_failures(evidence) == []


def test_canonical_declares_the_tested_revision_evidence_set() -> None:
    declared = validator.block_lines(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "TESTED_REVISION_EVIDENCE"
    )
    assert declared is not None
    fields = {line.lstrip("- ").strip() for line in declared if line.strip()}
    assert fields == set(validator.TESTED_REVISION_EVIDENCE_FIELDS)


# ---------------------------------------------------------------------------
# Pre-audit closures on this candidate
# ---------------------------------------------------------------------------


def test_run_provenance_requires_the_expected_workflow() -> None:
    """A sibling workflow can publish a green `tests` context, so a non-empty path proves nothing."""
    assert validator.tested_revision_failures(_revision_evidence(workflow_path=".github/workflows/other.yml"))
    assert validator.tested_revision_failures(_revision_evidence(workflow_path=""))
    assert validator.tested_revision_failures(_revision_evidence()) == []


@pytest.mark.parametrize(
    ("label", "conclusions"),
    [
        ("only one gate reported", {"Agent OS control-plane contract": "success"}),
        ("only the oracle reported", {"Agent OS contract oracle anchor": "success"}),
        ("an unrelated successful key", {"unrelated": "success"}),
        ("no gates reported", {}),
    ],
    ids=["only one gate reported", "only the oracle reported", "an unrelated successful key", "no gates reported"],
)
def test_every_expected_gate_step_must_report(label: str, conclusions: dict) -> None:
    """An absent entry is indistinguishable from a gate that never ran, so absence must fail."""
    assert validator.tested_revision_failures(_revision_evidence(agent_os_gate_step_conclusions=conclusions)), label


def test_expected_gate_step_names_are_declared() -> None:
    assert set(validator.REQUIRED_AGENT_OS_GATE_STEPS) == {
        "Agent OS control-plane contract",
        "Agent OS contract oracle anchor",
    }


def test_runtime_block_requires_the_whole_field_set() -> None:
    """The block's own contract says absence is never the same statement as UNKNOWN."""
    manifest = _example_manifest()
    manifest["model_runtime"] = {"model_evidence_source": "UNKNOWN"}
    assert validator.check_manifest_instance("probe", manifest)
    for field in validator.MODEL_RUNTIME_GRAMMAR["fields"]:
        stripped = _example_manifest()
        stripped["model_runtime"].pop(field)
        assert validator.check_manifest_instance("probe", stripped), field


@pytest.mark.parametrize(
    ("source", "actual", "accepted"),
    [
        ("CONTRADICTED", "claude-sonnet-5", True),
        ("CONTRADICTED", None, False),
        ("CONFIGURATION_EVIDENCE_ONLY", "claude-sonnet-5", False),
        ("UNKNOWN", "claude-sonnet-5", False),
    ],
    ids=[
        "contradicted records what ran",
        "contradicted without an observation",
        "configuration claims execution",
        "unknown claims execution",
    ],
)
def test_contradicted_records_the_conflicting_execution(source: str, actual: object, accepted: bool) -> None:
    """CONTRADICTED is contradictory runtime PROOF: something ran, and it was not what was asked for.

    Forcing the observation to null would leave the manifest unable to record the very identity
    that triggered STOP_MODEL_MISMATCH.
    """
    manifest = _example_manifest()
    manifest["model_runtime"]["model_evidence_source"] = source
    manifest["model_runtime"]["model_actual"] = actual
    found = [item for item in validator.manifest_relation_failures("probe", manifest) if "model_actual" in item]
    assert (not found) is accepted


def test_canonical_vocabulary_matches_the_executable_grammar() -> None:
    """Prose that names classes the grammar rejects would send an author down a dead end."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    for value_class in validator.VALUE_CLASSES:
        assert value_class in canonical, value_class
    assert "NONEMPTY_STRING" not in canonical


# ---------------------------------------------------------------------------
# Routing authority: the read-only reasoning families and the protected lane
#
# Probes are literal and independent: the expected lanes, model ids and effort sets are
# written out here and never imported from the validator.
# ---------------------------------------------------------------------------

ORACLE_READ_ONLY_REASONING_LANE = "Claude Opus 5"
ORACLE_READ_ONLY_REASONING_MODEL_ID = "claude-opus-5"
# Ordinary review is the one read-only family with a cross-family option, so a reviewer that did
# not implement the work can always be chosen. Architecture and prompt architecture are not
# independence questions and stay single-lane.
ORACLE_READ_ONLY_REASONING_LANES = {
    "T3C": {"Claude Opus 5": "claude-opus-5", "Codex GPT-5.6 Sol": "gpt-5.6-sol"},
    "T3D": {"Claude Opus 5": "claude-opus-5"},
    "T3E": {"Claude Opus 5": "claude-opus-5"},
}
ORACLE_READ_ONLY_REASONING_EFFORTS = {
    "T3C": {"medium", "high", "xhigh"},
    "T3D": {"high", "xhigh", "max"},
    "T3E": {"high", "xhigh", "max"},
}
ORACLE_PROTECTED_FRONTIER_EFFORTS = {"xhigh", "max"}


def _routes() -> list[list[str]]:
    rows = validator.block_lines((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "ROLE_ROUTING_MATRIX")
    parsed = []
    for row in rows or []:
        if row.startswith("ROUTE:"):
            parsed.append([f.strip() for f in row[len("ROUTE:") :].split("|")])
    return parsed


@pytest.mark.parametrize("family", ["T3C", "T3D", "T3E"])
def test_read_only_reasoning_family_lane_and_efforts(family: str) -> None:
    rows = [r for r in _routes() if r[0] == family]
    assert rows, family
    legal = ORACLE_READ_ONLY_REASONING_LANES[family]
    assert {r[2] for r in rows} == set(legal)
    assert {(r[2], r[3]) for r in rows} == set(legal.items())
    assert {r[5] for r in rows} == {"READ_ONLY"}
    # EVERY legal lane offers the family's whole effort set, or "prefer the other lane" silently
    # fails at the effort the work actually needs.
    for lane in legal:
        assert {r[4] for r in rows if r[2] == lane} == ORACLE_READ_ONLY_REASONING_EFFORTS[family], lane


def test_t3c_never_reaches_max() -> None:
    """max is reserved for the families whose per-family trigger table grants it."""
    assert "max" not in {r[4] for r in _routes() if r[0] == "T3C"}
    rows = validator.block_lines((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "MAX_EFFORT_FAMILY_TRIGGERS")
    assert not any(row.lstrip("- ").startswith("T3C ") for row in rows or [])


def test_protected_frontier_lane_owns_class_c() -> None:
    rows = [r for r in _routes() if r[0] == "T4"]
    assert rows
    assert {r[2] for r in rows} == {ORACLE_FRONTIER_LANE}
    assert {r[3] for r in rows} == {ORACLE_FRONTIER_MODEL_ID}
    assert {r[4] for r in rows} == ORACLE_PROTECTED_FRONTIER_EFFORTS
    assert {r[5] for r in rows} == {"READ_ONLY"}
    assert {r[1] for r in rows} == {"CLASS_C_CROSS_CONTRACT"}


@pytest.mark.parametrize(
    ("label", "row"),
    [
        # The protected gate reassigned to every lane that could plausibly absorb it.
        (
            "T4 on the busiest engineering lane",
            "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Codex GPT-5.6 Sol | gpt-5.6-sol | xhigh | READ_ONLY",
        ),
        ("T4 on Claude", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | xhigh | READ_ONLY"),
        ("T4 on Terra", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-5.6 Terra | - | xhigh | READ_ONLY"),
        ("T4 on Luna", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-5.6 Luna | - | xhigh | READ_ONLY"),
        (
            "T4 on a retired lane",
            "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Claude Fable 5 | claude-fable-5 | xhigh | READ_ONLY",
        ),
        (
            "T4 on an unknown lane",
            "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-7 Nova | gpt-7-nova | xhigh | READ_ONLY",
        ),
        # The protected gate kept on its own lane but weakened.
        ("T4 at high", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | high | READ_ONLY"),
        ("T4 at medium", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | medium | READ_ONLY"),
        ("T4 at low", "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | low | READ_ONLY"),
        (
            "T4 mutating",
            "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | BOUNDED_MUTATION",
        ),
        ("T4 with a non-Class-C intent", "ROUTE: T4 | REVIEW | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY"),
        # The read-only reasoning families pulled back onto the protected lane, or off Claude entirely.
        ("T3C on the protected lane", "ROUTE: T3C | REVIEW | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY"),
        (
            "T3D on the protected lane",
            "ROUTE: T3D | ARCHITECTURE | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        ),
        (
            "T3E on the protected lane",
            "ROUTE: T3E | PROMPT_ARCHITECTURE | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        ),
        ("T3C on Terra", "ROUTE: T3C | REVIEW | GPT-5.6 Terra | - | high | READ_ONLY"),
        ("T3C at max", "ROUTE: T3C | REVIEW | Claude Opus 5 | claude-opus-5 | max | READ_ONLY"),
    ],
    ids=[
        "T4 on the busiest engineering lane",
        "T4 on Claude",
        "T4 on Terra",
        "T4 on Luna",
        "T4 on a retired lane",
        "T4 on an unknown lane",
        "T4 at high",
        "T4 at medium",
        "T4 at low",
        "T4 mutating",
        "T4 with a non-Class-C intent",
        "T3C on the protected lane",
        "T3D on the protected lane",
        "T3E on the protected lane",
        "T3C on Terra",
        "T3C at max",
    ],
)
def test_routing_authority_rejects_a_substituted_lane(sandbox: Path, label: str, row: str) -> None:
    """Every way the protected or read-only authority could be quietly reassigned."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert failures(sandbox), "the routing matrix accepted: {}".format(label)


def test_class_c_cannot_be_satisfied_by_a_claude_or_codex_session() -> None:
    """Neither the lane that implements most of the work nor the lane that reviews it is Class C."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert (
        "No Claude lane, no Codex GPT-5.6 Sol lane, no Terra lane, no Luna lane and no controller "
        "read-only pass satisfies Class C" in canonical
    )
    assert "An ordinary Codex review is NOT a Class-C audit" in canonical
    assert "SELF_AUDIT_ONLY_NOT_INDEPENDENT" in canonical


def test_provider_capacity_never_reassigns_protected_authority() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "Temporary provider capacity NEVER reassigns protected authority" in canonical
    assert "CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE" in canonical


def test_the_protected_lane_is_not_declared_retired() -> None:
    """A retirement claim about an ACTIVE lane would be a false statement the validator enforces."""
    for token in validator.RETIRED_ROUTE_LANE_TOKENS:
        assert token not in ORACLE_FRONTIER_LANE, token
        assert token not in ORACLE_READ_ONLY_REASONING_LANE, token
    assert "Sol" not in validator.RETIRED_ROUTE_LANE_TOKENS


def test_the_protected_gate_is_pinned_to_exactly_two_rows() -> None:
    """The POSITIVE side: xhigh is the working effort, max exists and needs a named trigger."""
    rows = sorted(" | ".join(r) for r in _routes() if r[0] == "T4")
    assert rows == [
        "T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | max | READ_ONLY",
        "T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
    ]
    triggers = validator.block_lines(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "MAX_EFFORT_FAMILY_TRIGGERS"
    )
    t4 = [row for row in triggers or [] if row.lstrip("- ").startswith("T4 ")]
    assert len(t4) == 1, t4
    assert "CLASS_C_CROSS_CONTRACT" in t4[0]


def test_temporary_unavailability_cannot_reassign_the_protected_gate(sandbox: Path) -> None:
    """Capacity is a reason to WAIT for the gate, never a reason to hand it to another lane."""
    text = read(sandbox, CANONICAL)
    moved = text.replace(
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Codex GPT-5.6 Sol | gpt-5.6-sol | xhigh | READ_ONLY",
        1,
    ).replace(
        "return\n`CLASS_C_LANE_REQUIRED_BUT_UNAVAILABLE` to the controller and stop",
        "reroute the gate to the next available lane",
        1,
    )
    assert moved != text, "neither capacity-argument anchor matched; the probe would prove nothing"
    write(sandbox, CANONICAL, moved)
    assert_rejects(sandbox, "the protected frontier lane is exactly")


# ===========================================================================================
# Root-cause closures for the eight findings of the independent Class-C audit of PR #375.
#
# Every counterexample the audit reported is represented here as an executed regression, not as
# an assertion about source text. Where behaviour can be run, it is run.
# ===========================================================================================


def _revision(seed: str) -> str:
    return (seed * 40)[:40]


def _good_revision_evidence() -> dict:
    """The exact synthetic-merge shape a real `pull_request` run produces. Must always PASS."""
    return {
        "event": "pull_request",
        "audited_pr_head": _revision("a"),
        "audited_head_tree": _revision("b"),
        "current_base": _revision("c"),
        "workflow_run_id": 34193462435,
        "workflow_path": ".github/workflows/ci.yml",
        "run_reported_head": _revision("a"),
        "actual_checkout_revision": _revision("d"),
        "tested_revision_parents": [_revision("c"), _revision("a")],
        "tested_revision_tree": _revision("b"),
        "checkout_ref_override": False,
        "tests_job_conclusion": "success",
        "agent_os_gate_step_conclusions": {
            "Agent OS control-plane contract": "success",
            "Agent OS contract oracle anchor": "success",
        },
        "required_contexts": ["tests", "codeql", "CodeQL"],
    }


# --- RC-01  STRICT_TESTED_REVISION_EVIDENCE ---------------------------------------------------


def test_the_valid_synthetic_merge_bundle_still_passes() -> None:
    """The POSITIVE anchor. A strictness fix that rejects real evidence has closed nothing."""
    assert validator.tested_revision_failures(_good_revision_evidence()) == []


@pytest.mark.parametrize(
    ("label", "patch"),
    [
        ("actual_checkout_revision is an empty list", {"actual_checkout_revision": []}),
        (
            "current_base and its parent are both None",
            {"current_base": None, "tested_revision_parents": [None, _revision("a")]},
        ),
        (
            "audited head and its parent are both None",
            {"audited_pr_head": None, "tested_revision_parents": [_revision("c"), None]},
        ),
        (
            "every revision identity is None",
            {"current_base": None, "audited_pr_head": None, "tested_revision_parents": [None, None]},
        ),
        ("both trees are None", {"tested_revision_tree": None, "audited_head_tree": None}),
        ("the run identity is None", {"workflow_run_id": None}),
        ("the run identity is a bool", {"workflow_run_id": True}),
        ("the run identity is zero", {"workflow_run_id": 0}),
        (
            "every revision identity is blank",
            {
                "current_base": "   ",
                "audited_pr_head": "   ",
                "tested_revision_parents": ["   ", "   "],
                "tested_revision_tree": "  ",
                "audited_head_tree": "  ",
            },
        ),
        (
            "every revision identity is malformed",
            {
                "current_base": "not-a-sha",
                "audited_pr_head": "zzzz",
                "tested_revision_parents": ["not-a-sha", "zzzz"],
                "tested_revision_tree": "!!!",
                "audited_head_tree": "!!!",
            },
        ),
        ("a revision identity is truncated", {"actual_checkout_revision": _revision("d")[:39]}),
        ("the required-context inventory is empty", {"required_contexts": []}),
        ("the required-context inventory is None", {"required_contexts": None}),
        ("the required-context inventory is a bare string", {"required_contexts": "tests"}),
        ("a required context is filler only", {"required_contexts": ["\u3164"]}),
        ("the parents are not a container", {"tested_revision_parents": _revision("c")}),
        (
            "the parents are integers",
            {"tested_revision_parents": [1, 2], "current_base": 1, "audited_pr_head": 2},
        ),
        ("the trees are integers", {"tested_revision_tree": 5, "audited_head_tree": 5}),
        ("the gate conclusions are not a map", {"agent_os_gate_step_conclusions": []}),
        ("a gate conclusion is None", {"agent_os_gate_step_conclusions": {"Agent OS control-plane contract": None}}),
        ("the workflow path is blank", {"workflow_path": "   "}),
        ("the checkout state is unknown", {"checkout_ref_override": "UNKNOWN"}),
        ("the checkout state is a truthy string", {"checkout_ref_override": "refs/heads/main"}),
        ("the checkout state is None", {"checkout_ref_override": None}),
    ],
    ids=[
        "actual_checkout_revision is an empty list",
        "current_base and its parent are both None",
        "audited head and its parent are both None",
        "every revision identity is None",
        "both trees are None",
        "the run identity is None",
        "the run identity is a bool",
        "the run identity is zero",
        "every revision identity is blank",
        "every revision identity is malformed",
        "a revision identity is truncated",
        "the required-context inventory is empty",
        "the required-context inventory is None",
        "the required-context inventory is a bare string",
        "a required context is filler only",
        "the parents are not a container",
        "the parents are integers",
        "the trees are integers",
        "the gate conclusions are not a map",
        "a gate conclusion is None",
        "the workflow path is blank",
        "the checkout state is unknown",
        "the checkout state is a truthy string",
        "the checkout state is None",
    ],
)
def test_malformed_revision_evidence_never_establishes_provenance(label: str, patch: dict) -> None:
    """P1-01. Two absent facts compare equal, so a relation over unvalidated values is not a proof."""
    evidence = _good_revision_evidence()
    evidence.update(patch)
    found = validator.tested_revision_failures(evidence)
    assert found, "malformed evidence established provenance: {}".format(label)
    assert any("SAFETY_BLOCKER" in item for item in found), found


def test_shape_is_proven_before_any_relation_runs() -> None:
    """The ordering IS the fix: a shape failure short-circuits, so no relation sees a bad value."""
    evidence = _good_revision_evidence()
    evidence["current_base"] = None
    found = validator.tested_revision_failures(evidence)
    assert all("not well-formed" in item for item in found), found
    assert not any("the base moved" in item for item in found), found


def test_every_declared_evidence_field_has_a_shape() -> None:
    """A field with no shape contract is a field the relations may read unvalidated."""
    assert set(validator.TESTED_REVISION_SHAPES) == set(validator.TESTED_REVISION_EVIDENCE_FIELDS)


# --- RC-08  CHECKOUT_OVERRIDE_CONTRACT --------------------------------------------------------


def test_checkout_override_is_unsupported_and_says_so() -> None:
    """P2-07. The doctrine described an accepting branch no code implemented."""
    evidence = _good_revision_evidence()
    evidence["checkout_ref_override"] = True
    assert validator.tested_revision_failures(evidence)
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "`checkout_ref_override` must be exactly `false`" in canonical
    assert "there is no branch that accepts one" in canonical
    assert "The controller must then prove `actual_checkout_revision` from" not in canonical


# --- RC-02  CLASS_C_INTENT_EXCLUSIVITY --------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "row"),
    [
        ("T0", "ROUTE: T0 | CLASS_C_CROSS_CONTRACT | GPT-5.6 Luna | - | low | MECHANICAL_ONLY"),
        ("T1", "ROUTE: T1 | CLASS_C_CROSS_CONTRACT | GPT-5.6 Luna | - | low | GOVERNED_CLOSEOUT"),
        ("T2", "ROUTE: T2 | CLASS_C_CROSS_CONTRACT | GPT-5.6 Terra | - | medium | BOUNDED_MUTATION"),
        ("T3A", "ROUTE: T3A | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | xhigh | HEAVY_MUTATION"),
        ("T3C", "ROUTE: T3C | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | xhigh | READ_ONLY"),
        ("T3D", "ROUTE: T3D | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | max | READ_ONLY"),
        (
            "T3C alongside its own intent",
            "ROUTE: T3C | REVIEW,CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | high | READ_ONLY",
        ),
        (
            "a second Astra row outside T4",
            "ROUTE: T3D | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        ),
    ],
    ids=[
        "T0",
        "T1",
        "T2",
        "T3A",
        "T3C",
        "T3D",
        "T3C alongside its own intent",
        "a second Astra row outside T4",
    ],
)
def test_class_c_intent_belongs_to_t4_alone(sandbox: Path, label: str, row: str) -> None:
    """P2-01. The correct T4 rows stay in place; the parallel authority must still be rejected."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert_rejects(sandbox, "belongs to the protected T4 family alone")


def test_class_c_and_t4_are_the_same_set() -> None:
    """Both directions, read off the committed matrix."""
    rows = _routes()
    t4 = {tuple(r) for r in rows if r[0] == "T4"}
    class_c = {tuple(r) for r in rows if validator.CLASS_C_INTENT in r[1]}
    assert t4 == class_c
    assert t4, "no protected route declared"


# --- RC-03  INTENT_PRESERVING_PROTECTED_GATE --------------------------------------------------


def test_intent_first_routing_is_declared_exactly(sandbox: Path) -> None:
    """P2-02. A positive contract, pinned - not a hunt for phrasings that contradict it."""
    rows = validator.block_lines((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "INTENT_FIRST_ROUTING")
    assert rows == list(validator.INTENT_FIRST_ROUTING_RULES)
    patch(sandbox, CANONICAL, validator.INTENT_FIRST_ROUTING_RULES[0], "- The intent may be revised later.")
    assert_rejects(sandbox, "INTENT_FIRST_ROUTING")


def test_review_stays_review_under_a_protected_trigger() -> None:
    """The retired sentence said a protected trigger 'escalates the work to T4'."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "A protected trigger escalates the work to T4" not in canonical
    assert "A protected trigger does NOT convert this task into T4" in canonical
    assert "a `REVIEW` task stays `REVIEW`" in canonical
    assert "the controller creates a SEPARATE read-only `CLASS_C_CROSS_CONTRACT` task" in canonical


def test_a_risk_class_requires_a_gate_rather_than_rewriting_an_intent() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "Any uncertainty escalates to Class C." not in canonical
    assert "not a change to this task's intent" in canonical


# --- RC-04  OPERATIONAL_TEXT_EVIDENCE ---------------------------------------------------------

ORACLE_FILLER = ("\u3164", "\u2800", "\u3164\u2800", "\u2800" * 12, "\u200b", "", "   ")


@pytest.mark.parametrize("filler", ORACLE_FILLER)
def test_filler_never_satisfies_a_load_bearing_field(filler: str) -> None:
    """P2-03. `next_safe_action` is acted on by a human; filler is not an action."""
    manifest = _example_manifest()
    manifest["next_safe_action"] = filler
    assert [item for item in validator.check_manifest_instance("probe", manifest) if "next_safe_action" in item]


@pytest.mark.parametrize("action", ["open one replacement PR", "run the ladder", "audit head 6200a10", "1"])
def test_a_real_action_still_passes(action: str) -> None:
    manifest = _example_manifest()
    manifest["next_safe_action"] = action
    assert not [item for item in validator.check_manifest_instance("probe", manifest) if "next_safe_action" in item]


@pytest.mark.parametrize(
    "field,key", [("completed_gates", "gate"), ("completed_gates", "evidence_key"), ("blockers", "id")]
)
def test_filler_never_satisfies_a_compared_identity(field: str, key: str) -> None:
    """Sibling of P2-03: names and keys the control plane COMPARES are load-bearing too."""
    manifest = _example_manifest()
    assert manifest[field], field
    manifest[field][0][key] = "\u3164"
    assert [item for item in validator.check_manifest_instance("probe", manifest) if field in item]


def test_free_form_observational_text_stays_permissive() -> None:
    """`host_setting_raw` copies an operator's UI label verbatim and may be any script."""
    assert validator.text_evidence_failures("Opus 5 \u2014 \u6700\u5927") == []
    manifest = _example_manifest()
    manifest["model_runtime"]["host_setting_raw"] = "\u6700\u5927"
    assert not [item for item in validator.check_manifest_instance("probe", manifest) if "host_setting_raw" in item]


def test_the_text_grammars_state_their_real_claims() -> None:
    """The retired note claimed future Unicode assignments were covered. They are not."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "at least one ASCII letter or digit" in canonical
    assert "compiled into the RUNNING interpreter" in canonical
    assert "no claim is made about code points assigned in a newer Unicode version" in canonical
    assert "no list of forbidden characters exists anywhere in this control plane" in canonical
    assert "a code point assigned in a future Unicode version is covered on the day" not in canonical


def test_no_forbidden_character_list_exists() -> None:
    """The closure must not have become the blacklist it replaced.

    Prose may NAME the two reported code points: explaining why a general Unicode category test
    cannot decide them is the honest documentation of a limit, not an enumeration the code acts on.
    What must not exist is EXECUTABLE code that lists them, so comments are stripped before the scan
    and the predicate is proven to be a POSITIVE match rather than a membership test.
    """
    source = (REPO_ROOT / "scripts/crypto_core/validate_agent_os_v2.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for filler in ("\u3164", "\u2800", "\\u3164", "\\u2800", "HANGUL", "BRAILLE", "FILLER"):
        assert filler not in code, filler
    assert validator.OPERATIONAL_TOKEN_RE.pattern == "[A-Za-z0-9]"
    assert "OPERATIONAL_TOKEN_RE.search(value)" in code


# --- RC-05  TYPE_STRICT_GENERATED_SCHEMA_EQUALITY ---------------------------------------------


def test_schema_equality_is_json_type_strict() -> None:
    """P2-04. Python says `0 == False`; JSON does not, and a schema bound is not a boolean."""
    assert {"minimum": 0} == {"minimum": False}
    assert validator.canonical_json({"minimum": 0}) != validator.canonical_json({"minimum": False})
    assert validator.canonical_json({"a": 1}) != validator.canonical_json({"a": 1.0})
    assert validator.canonical_json({"a": True}) != validator.canonical_json({"a": 1})


def test_a_bound_replaced_by_a_boolean_is_rejected(sandbox: Path) -> None:
    """The exact reported counterexample, executed against the real gate."""
    rel = "docs/crypto_core/continuity/state_manifest.schema.json"
    committed = json.loads(read(sandbox, rel))
    replaced = 0

    def flip(node: object) -> object:
        nonlocal replaced
        if isinstance(node, dict):
            out = {}
            for key, value in node.items():
                if key == "minimum" and value == 0 and not replaced:
                    out[key] = False
                    replaced = 1
                else:
                    out[key] = flip(value)
            return out
        if isinstance(node, list):
            return [flip(item) for item in node]
        return node

    mutated = flip(committed)
    assert replaced, "no integer bound of 0 in the generated schema to flip"
    assert mutated == committed, "the mutation must be INVISIBLE to Python equality"
    write(sandbox, rel, json.dumps(mutated, indent=2) + "\n")
    assert_rejects(sandbox, "does not equal the schema generated")


def test_the_generated_schema_equals_the_committed_one() -> None:
    committed = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text("utf-8-sig")
    )
    assert validator.canonical_json(committed) == validator.canonical_json(validator.emit_manifest_schema())


def test_nan_and_infinity_are_not_a_specification() -> None:
    for value in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValueError):
            validator.canonical_json({"a": value})


# --- RC-06  DIMENSIONAL_RUNTIME_PROOF ---------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "runtime"),
    [
        (
            "identity unknown while the effort was observed",
            {
                "model_evidence_source": "UNKNOWN",
                "model_actual": None,
                "effort_evidence_source": "RUNTIME_TELEMETRY",
                "observed_effort": "xhigh",
            },
        ),
        (
            "a conflicting identity was observed while the effort is unknown",
            {
                "model_evidence_source": "CONTRADICTED",
                "model_actual": "claude-sonnet-5",
                "effort_evidence_source": "UNKNOWN",
                "observed_effort": None,
            },
        ),
        (
            "the identity matches while the effort conflicts",
            {
                "model_evidence_source": "RUNTIME_TELEMETRY",
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": "claude-opus-5",
                "effort_evidence_source": "CONTRADICTED",
                "observed_effort": "high",
                "effort_mismatch_waiver": {"status": "NOT_GRANTED", "evidence": None},
            },
        ),
        ("thinking is unknown", {"thinking_actual": "UNKNOWN"}),
        ("thinking is enabled", {"thinking_actual": "ENABLED"}),
        ("thinking is disabled", {"thinking_actual": "DISABLED"}),
    ],
    ids=[
        "identity unknown while the effort was observed",
        "a conflicting identity was observed while the effort is unknown",
        "the identity matches while the effort conflicts",
        "thinking is unknown",
        "thinking is enabled",
        "thinking is disabled",
    ],
)
def test_partial_runtime_observations_are_representable(label: str, runtime: dict) -> None:
    """P2-05. A contradiction in one dimension must not erase valid evidence in another."""
    manifest = _example_manifest()
    manifest["model_runtime"].update(runtime)
    assert validator.check_manifest_instance("probe", manifest) == [], label


@pytest.mark.parametrize(
    ("label", "runtime"),
    [
        (
            "telemetry identity with nothing observed",
            {"model_evidence_source": "RUNTIME_TELEMETRY", "model_actual": None},
        ),
        (
            "telemetry identity observing filler",
            {"model_evidence_source": "RUNTIME_TELEMETRY", "model_actual": "\u3164"},
        ),
        (
            "telemetry effort with nothing observed",
            {"effort_evidence_source": "RUNTIME_TELEMETRY", "observed_effort": None},
        ),
        (
            "an unknown effort that claims an observation",
            {"effort_evidence_source": "UNKNOWN", "observed_effort": "max"},
        ),
        (
            "a configuration-only effort that claims an observation",
            {"effort_evidence_source": "CONFIGURATION_EVIDENCE_ONLY", "observed_effort": "max"},
        ),
        (
            "a contradicted effort recording nothing",
            {"effort_evidence_source": "CONTRADICTED", "observed_effort": None},
        ),
        ("thinking outside its enum", {"thinking_actual": "MAYBE"}),
        ("thinking absent", {"thinking_actual": None}),
    ],
    ids=[
        "telemetry identity with nothing observed",
        "telemetry identity observing filler",
        "telemetry effort with nothing observed",
        "an unknown effort that claims an observation",
        "a configuration-only effort that claims an observation",
        "a contradicted effort recording nothing",
        "thinking outside its enum",
        "thinking absent",
    ],
)
def test_each_runtime_dimension_is_judged_on_its_own_evidence(label: str, runtime: dict) -> None:
    manifest = _example_manifest()
    manifest["model_runtime"].update(runtime)
    assert validator.check_manifest_instance("probe", manifest), label


def test_the_runtime_block_declares_both_evidence_dimensions() -> None:
    fields = validator.MODEL_RUNTIME_GRAMMAR["fields"]
    for field in ("model_evidence_source", "effort_evidence_source", "thinking_actual"):
        assert field in fields, field
        assert field in validator.MODEL_RUNTIME_GRAMMAR["required"], field
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "effort_evidence_source" in canonical
    assert "thinking_actual" in canonical


# --- RC-07  FAIL_CLOSED_SETUP_AUDIT_EXECUTION -------------------------------------------------


def _powershell() -> str | None:
    for candidate in ("pwsh", "powershell"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


def _run_validator_only(extra: list[str], seed_stale_success: bool) -> subprocess.CompletedProcess:
    shell = _powershell()
    assert shell
    script = str(REPO_ROOT / "scripts" / "crypto_core" / "audit_agent_setup.ps1")
    seed = "& cmd /c 'exit 0'; " if seed_stale_success and os.name == "nt" else ""
    # A parameter NAME is not a value: quoting `-PythonExe` turns it into a positional argument,
    # which silently bound the interpreter path to the wrong parameter once a second one existed.
    args = " ".join(item if item.startswith("-") else "'{}'".format(item) for item in extra)
    command = "{}& '{}' -ValidatorOnly {}; exit $LASTEXITCODE".format(seed, script, args)
    return subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [shell, "-NoProfile", "-Command", command],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_fails_closed_when_the_validator_cannot_launch() -> None:
    """P2-06, EXECUTED. A stale success is seeded, then the interpreter cannot launch.

    `$LASTEXITCODE` is a global that a failed launch never sets, so the previous 0 was being read
    as 'the validator passed'. Source inspection cannot prove this; only running it can.
    """
    done = _run_validator_only(["-PythonExe", "C:\\definitely\\missing\\python.exe"], seed_stale_success=True)
    assert done.returncode != 0, done.stdout + done.stderr
    assert "VALIDATOR_EXIT=NO_EXIT_STATUS" in done.stdout, done.stdout
    assert "NOT EXECUTED" in done.stdout, done.stdout


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_still_passes_when_the_validator_runs() -> None:
    """The POSITIVE anchor: a fail-closed gate that always fails has closed nothing."""
    done = _run_validator_only([], seed_stale_success=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "VALIDATOR_EXIT=0" in done.stdout, done.stdout


def _run_audit_against_a_substitute_validator(workdir: Path, body: str) -> subprocess.CompletedProcess:
    """Run the REAL audit against a validator that is genuinely found and genuinely launched.

    The script resolves the validator at the fixed repo-relative path, so planting a substitute at
    that exact path inside a scratch working directory exercises the real branch end to end: the
    path exists, the interpreter launches it, and its exit status is what the audit reads. An
    earlier version of this regression wrote a `fake.py` the script never opened and ran from a
    directory with no validator at all, so it passed through `VALIDATOR=MISSING` and proved nothing
    about nonzero propagation.
    """
    planted = workdir / "scripts" / "crypto_core" / "validate_agent_os_v2.py"
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_text(body, encoding="utf-8")
    shell = _powershell()
    assert shell
    interpreter = shutil.which("python") or shutil.which("python3")
    assert interpreter
    script = str(REPO_ROOT / "scripts" / "crypto_core" / "audit_agent_setup.ps1")
    return subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [
            shell,
            "-NoProfile",
            "-Command",
            "& '{}' -ValidatorOnly -PythonExe '{}'; exit $LASTEXITCODE".format(script, interpreter),
        ],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_propagates_the_exact_nonzero_validator_status(tmp_path: Path) -> None:
    """A nonzero validator verdict must reach the exit code, by the intended path.

    The assertions pin the EXACT status, so deleting the nonzero propagation branch fails this
    test rather than letting some other failure keep it green.
    """
    done = _run_audit_against_a_substitute_validator(tmp_path, "import sys\n\nsys.exit(3)\n")
    assert "VALIDATOR=MISSING" not in done.stdout, done.stdout
    assert "VALIDATOR_EXIT=3" in done.stdout, done.stdout
    assert "validator exit 3" in done.stdout, done.stdout
    assert done.returncode != 0, done.stdout + done.stderr


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_fails_when_the_validator_raises(tmp_path: Path) -> None:
    """A validator that throws is a validator that did not pass."""
    done = _run_audit_against_a_substitute_validator(tmp_path, "raise SystemError('control plane exploded')\n")
    assert "VALIDATOR=MISSING" not in done.stdout, done.stdout
    assert "VALIDATOR_EXIT=1" in done.stdout, done.stdout
    assert done.returncode != 0, done.stdout + done.stderr


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_accepts_a_substitute_validator_that_succeeds(tmp_path: Path) -> None:
    """The POSITIVE anchor for the substitution harness itself.

    Without this, a harness that always failed for an unrelated reason would look like proof.
    """
    done = _run_audit_against_a_substitute_validator(tmp_path, "import sys\n\nsys.exit(0)\n")
    assert "VALIDATOR=MISSING" not in done.stdout, done.stdout
    assert "VALIDATOR_EXIT=0" in done.stdout, done.stdout
    assert done.returncode == 0, done.stdout + done.stderr


# --- Phase-4 siblings: same abstractions, defects nobody reported ------------------------------


@pytest.mark.parametrize(
    ("label", "patch"),
    [
        ("one parent on a pull_request", {"tested_revision_parents": [_revision("c")]}),
        (
            "three parents on a pull_request",
            {"tested_revision_parents": [_revision("c"), _revision("a"), _revision("e")]},
        ),
        ("an unaccepted event", {"event": "workflow_dispatch"}),
        ("a skipped tests job", {"tests_job_conclusion": "skipped"}),
        (
            "a gate step that never reported",
            {"agent_os_gate_step_conclusions": {"Agent OS control-plane contract": "success"}},
        ),
        ("a sibling workflow", {"workflow_path": ".github/workflows/other.yml"}),
        ("a filler workflow path", {"workflow_path": "\u3164"}),
        (
            "a filler gate conclusion",
            {
                "agent_os_gate_step_conclusions": {
                    "Agent OS control-plane contract": "\u3164",
                    "Agent OS contract oracle anchor": "success",
                }
            },
        ),
    ],
    ids=[
        "one parent on a pull_request",
        "three parents on a pull_request",
        "an unaccepted event",
        "a skipped tests job",
        "a gate step that never reported",
        "a sibling workflow",
        "a filler workflow path",
        "a filler gate conclusion",
    ],
)
def test_revision_evidence_siblings_fail_closed(label: str, patch: dict) -> None:
    evidence = _good_revision_evidence()
    evidence.update(patch)
    assert validator.tested_revision_failures(evidence), label


def test_a_push_bundle_is_judged_on_its_own_relation() -> None:
    """`push` had no tree relation at all, so CI could have compiled a different tree."""
    evidence = _good_revision_evidence()
    evidence.update(
        event="push",
        tested_revision_parents=[],
        actual_checkout_revision=evidence["audited_pr_head"],
        tested_revision_tree=evidence["audited_head_tree"],
    )
    assert validator.tested_revision_failures(evidence) == []
    drifted = dict(evidence, tested_revision_tree=_revision("f"))
    assert any("SAFETY_BLOCKER" in item for item in validator.tested_revision_failures(drifted))


def test_evidence_judging_is_total_on_hostile_values() -> None:
    """TOTAL means total: no input shape may raise instead of returning reasons."""
    for hostile in (None, "x", [], 0, {k: object() for k in validator.TESTED_REVISION_EVIDENCE_FIELDS}):
        assert validator.tested_revision_failures(hostile)


@pytest.mark.parametrize(
    ("label", "row"),
    [
        ("XR", "ROUTE: XR | CLASS_C_CROSS_CONTRACT | Deep Research | - | - | READ_ONLY"),
        (
            "T3B",
            "ROUTE: T3B | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | max | CAPABILITY_CRITICAL_MUTATION",
        ),
    ],
    ids=["XR", "T3B"],
)
def test_class_c_exclusivity_covers_every_other_family(sandbox: Path, label: str, row: str) -> None:
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert_rejects(sandbox, "belongs to the protected T4 family alone")


def test_t4_cannot_quietly_lose_its_protected_intent(sandbox: Path) -> None:
    """Exclusivity must not be satisfiable by emptying the protected set."""
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        "ROUTE: T4 | REVIEW | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
    )
    assert failures(sandbox)


@pytest.mark.parametrize("field", ["observed_effort", "requested_effort"])
def test_ultra_never_enters_an_effort_dimension(field: str) -> None:
    manifest = _example_manifest()
    manifest["model_runtime"][field] = "ultra"
    assert validator.check_manifest_instance("probe", manifest)


# --- Pre-audit consolidated repair: three findings automated review reproduced on df165dd -------


def test_one_attestation_cannot_prove_two_dimensions() -> None:
    """A single untyped host label satisfied identity AND effort while both observations were null.

    That is the dimensional collapse the split exists to prevent, reintroduced through a shared
    fallback. An attestation attests ONE dimension and must record it in that dimension's field.
    """
    manifest = _example_manifest()
    manifest["model_runtime"].update(
        model_evidence_source="USER_ATTESTED_UI_SELECTION",
        model_actual=None,
        effort_evidence_source="USER_ATTESTED_UI_SELECTION",
        observed_effort=None,
        host_setting_raw="Max",
    )
    assert validator.check_manifest_instance("probe", manifest)


def test_an_attestation_that_records_its_own_dimension_is_accepted() -> None:
    """The POSITIVE anchor: attestation stays a usable evidence class."""
    manifest = _example_manifest()
    manifest["model_runtime"].update(
        model_evidence_source="USER_ATTESTED_UI_SELECTION",
        model_id="claude-opus-5",
        model_requested="claude-opus-5",
        model_actual="claude-opus-5",
        effort_evidence_source="USER_ATTESTED_UI_SELECTION",
        requested_effort="max",
        observed_effort="max",
        host_setting_raw="Opus 5 / Max",
    )
    assert validator.check_manifest_instance("probe", manifest) == []


@pytest.mark.parametrize("field", ["compiled_at_evidence", "task_boundary"])
@pytest.mark.parametrize("filler", ["\u3164", "\u2800", "\u3164\u2800"])
def test_state_proof_and_scope_are_load_bearing(field: str, filler: str) -> None:
    """When live-state proof and the authorization boundary are filler, the manifest records nothing."""
    manifest = _example_manifest()
    manifest[field] = filler
    assert [item for item in validator.check_manifest_instance("probe", manifest) if field in item]


def test_free_form_commentary_stays_free_form() -> None:
    """`$comment` is prose about the artifact; nothing compares it, so it keeps the weak grammar."""
    manifest = _example_manifest()
    manifest["$comment"] = "\u6ce8\u91c8"
    assert not [item for item in validator.check_manifest_instance("probe", manifest) if "$comment" in item]


@pytest.mark.parametrize(
    ("label", "old", "new"),
    [
        ("the whole T0 STATUS row", "ROUTE: T0 | STATUS | GPT-5.6 Luna | - | low | MECHANICAL_ONLY\n", ""),
        ("the whole XR row", "ROUTE: XR | EXTERNAL_RESEARCH | Deep Research | - | - | READ_ONLY\n", ""),
        ("the intent list of a row", "ROUTE: T0 | STATUS |", "ROUTE: T0 |  |"),
    ],
    ids=["the whole T0 STATUS row", "the whole XR row", "the intent list of a row"],
)
def test_the_routing_matrix_must_cover_every_class_and_intent(sandbox: Path, label: str, old: str, new: str) -> None:
    """Judging the rows that remain is not coverage: a deleted family is silently unrouted."""
    patch(sandbox, CANONICAL, old, new)
    assert failures(sandbox), "the matrix accepted a gap: {}".format(label)


def test_every_declared_class_and_intent_is_routed() -> None:
    rows = _routes()
    assert {r[0] for r in rows} == set(validator.ROUTE_CLASSES)
    routed = {intent.strip() for r in rows for intent in r[1].split(",") if intent.strip()}
    assert routed == set(validator.TASK_INTENTS)


# ===========================================================================================
# Final Class-C findings on c628faec: operational authorization text, routing ownership,
# protected-lane exactness, stale prose. Every reported counterexample is executed here.
# ===========================================================================================

ORACLE_OPERATIONAL_FILLER = ("ㅤ", "⠀", "ㅤ⠀", "   ", "​", "")


@pytest.mark.parametrize("filler", ORACLE_OPERATIONAL_FILLER)
def test_authorized_mutation_scope_is_load_bearing(filler: str) -> None:
    """P1-01. mutation_scope IS the authorization a human reads before touching anything."""
    manifest = _example_manifest()
    manifest["authorization"]["mutation_scope"] = filler
    assert [item for item in validator.check_manifest_instance("probe", manifest) if "mutation_scope" in item]


@pytest.mark.parametrize("filler", ORACLE_OPERATIONAL_FILLER)
def test_invalidations_are_load_bearing(filler: str) -> None:
    """P1-01. An invalidation names a fact that must not be reused; filler names nothing."""
    manifest = _example_manifest()
    manifest["invalidations"] = [filler]
    assert [item for item in validator.check_manifest_instance("probe", manifest) if "invalidations" in item]


def test_a_real_scope_and_a_real_invalidation_still_pass() -> None:
    """The POSITIVE anchor for the operational grammar."""
    manifest = _example_manifest()
    manifest["authorization"]["mutation_scope"] = "scripts/crypto_core/validate_agent_os_v2.py"
    manifest["invalidations"] = ["the ruff gate was dropped: its evidence key changed"]
    assert validator.check_manifest_instance("probe", manifest) == []


def test_every_free_form_text_field_is_free_form_by_classification() -> None:
    """The remaining TEXT_EVIDENCE fields are the ones no authorization or provenance decision reads.

    This is the WHOLE inventory, so a load-bearing field cannot later be added as free-form text by
    accident: a new one would appear here and fail.
    """
    found = []

    def walk(node: dict, path: list[str]) -> None:
        kind = node.get("kind")
        if kind == "OBJECT":
            for key, sub in node["fields"].items():
                walk(sub, [*path, key])
        elif kind == "STRUCTURED_LIST":
            walk(node["item"], [*path, "[]"])
        elif kind == "TEXT_EVIDENCE":
            found.append(".".join(path))

    walk(validator.MANIFEST_GRAMMAR, [])
    assert sorted(found) == [
        "$comment",
        "authorization.notes",
        "model_runtime.host_setting_raw",
    ]


@pytest.mark.parametrize(
    ("label", "row"),
    [
        (
            "a contradictory second mutation authority for T0",
            "ROUTE: T0 | STATUS | GPT-5.6 Luna | - | low | HEAVY_MUTATION",
        ),
        (
            "REVIEW routed through a mutation family",
            "ROUTE: T2 | REVIEW | GPT-5.6 Terra | - | medium | BOUNDED_MUTATION",
        ),
        (
            "STATUS routed through an unrelated family",
            "ROUTE: T3A | STATUS | Claude Opus 5 | claude-opus-5 | xhigh | HEAVY_MUTATION",
        ),
        (
            "ARCHITECTURE routed through an implementation family",
            "ROUTE: T3A | ARCHITECTURE | Claude Opus 5 | claude-opus-5 | xhigh | HEAVY_MUTATION",
        ),
        (
            "an exact duplicate of a committed row",
            "ROUTE: T0 | STATUS | GPT-5.6 Luna | - | low | MECHANICAL_ONLY",
        ),
        (
            "an alternate mutation authority for a read-only family",
            "ROUTE: T3C | REVIEW | Claude Opus 5 | claude-opus-5 | medium | BOUNDED_MUTATION",
        ),
        (
            "CLOSEOUT smuggled into a heavy family",
            "ROUTE: T3A | CLOSEOUT | Claude Opus 5 | claude-opus-5 | xhigh | HEAVY_MUTATION",
        ),
    ],
    ids=[
        "a contradictory second mutation authority for T0",
        "REVIEW routed through a mutation family",
        "STATUS routed through an unrelated family",
        "ARCHITECTURE routed through an implementation family",
        "an exact duplicate of a committed row",
        "an alternate mutation authority for a read-only family",
        "CLOSEOUT smuggled into a heavy family",
    ],
)
def test_family_ownership_rejects_a_second_authority_for_an_intent(sandbox: Path, label: str, row: str) -> None:
    """P2-01. Coverage proved every intent was routed; it never said WHICH family may own it."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert failures(sandbox), "the matrix accepted: {}".format(label)


def test_the_family_contract_and_the_matrix_cannot_drift() -> None:
    """One authority, two views, checked in both directions - now over all three legal columns."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    rows, problems = validator.parse_columns(canonical_text, "FAMILY_SEMANTIC_CONTRACT", 4)
    assert rows and not problems, problems
    owned: dict[str, set[str]] = {}
    for cls, intents, _authority, _efforts in rows:
        owned[cls.strip()] = {i.strip() for i in intents.split(",") if i.strip()}
    assert set(owned) == set(validator.ROUTE_CLASSES)
    assert {i for members in owned.values() for i in members} == set(validator.TASK_INTENTS)
    routed: dict[str, set[str]] = {}
    for cls, intents, *_rest in _routes():
        routed.setdefault(cls, set()).update(i.strip() for i in intents.split(",") if i.strip())
    assert routed == owned


def test_declared_ownership_must_be_reachable(sandbox: Path) -> None:
    """An owned intent nothing routes is a claim the matrix does not honour."""
    patch(sandbox, CANONICAL, "- T0 :: STATUS", "- T0 :: STATUS,BOUNDED_READ")
    assert_rejects(sandbox, "no T0 route accepts it")


def test_removing_the_family_contract_block_is_rejected(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "<!-- FAMILY_SEMANTIC_CONTRACT_BEGIN -->", "<!-- CONTRACT_RETIRED -->")
    assert_rejects(sandbox, "FAMILY_SEMANTIC_CONTRACT")


def test_removing_the_lane_capability_block_is_rejected(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "<!-- LANE_CAPABILITY_BEGIN -->", "<!-- CAPABILITY_RETIRED -->")
    assert_rejects(sandbox, "LANE_CAPABILITY")


@pytest.mark.parametrize(
    "lane",
    [
        "GPT-6 Astra or GPT-5.6 Terra",
        "foo GPT-6 Astra",
        "GPT-6 Astra backup",
        "GPT-6 Astra / Terra",
        "gpt-6 astra",
        "GPT-6  Astra",
    ],
)
def test_the_protected_lane_is_matched_exactly(sandbox: Path, lane: str) -> None:
    """P2-02. A containment test cannot tell an identity from a label that merely mentions it."""
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | GPT-6 Astra | gpt-6-astra | xhigh | READ_ONLY",
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | {} | gpt-6-astra | xhigh | READ_ONLY".format(lane),
    )
    assert failures(sandbox), "an ambiguous protected lane label was accepted: {!r}".format(lane)


def test_the_canonical_protected_lane_still_passes() -> None:
    rows = [r for r in _routes() if r[0] == "T4"]
    assert rows
    assert {r[2] for r in rows} == {validator.FRONTIER_LANE}
    assert {r[3] for r in rows} == {validator.FRONTIER_MODEL_ID}
    assert validator.collect_failures(REPO_ROOT) == []


def test_authority_identity_comparisons_are_exact_not_containment() -> None:
    """Both authority-bearing lane comparisons use equality; the retired scan stays containment.

    The retired-lane rule is an EXCLUSION, where matching a mention is the correct behaviour, so it
    deliberately keeps its word-boundary search.
    """
    source = (REPO_ROOT / "scripts/crypto_core/validate_agent_os_v2.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert "lane != FRONTIER_LANE" in code
    assert "FRONTIER_LANE not in lane" not in code
    # The read-only reasoning comparison is exact SET MEMBERSHIP plus an exact model id, never a
    # containment test over the lane string.
    assert "lane not in legal_lanes" in code
    assert "model_id != legal_lanes[lane]" in code
    # No authority comparison may test whether a pinned name is CONTAINED in the routed label:
    # "GPT-6 Astra backup" contains "GPT-6 Astra" and is not that lane.
    for containment in (
        "FRONTIER_LANE in lane",
        "FRONTIER_LANE not in lane",
        "READ_ONLY_REASONING_LANE in lane",
        "READ_ONLY_REASONING_LANE not in lane",
        "legal_lanes in lane",
    ):
        assert containment not in code, containment
    assert "RETIRED_ROUTE_LANE_TOKENS" in code


def test_the_runtime_description_matches_the_enforced_attestation_rule() -> None:
    """P3-01. The description promised a host-selector fallback the contract no longer has."""
    description = validator.MODEL_RUNTIME_GRAMMAR["description"]
    assert "meaningful attested value or host selector" not in description
    assert "own observation field" in description
    assert "never a fallback proof" in description


def test_the_example_comment_describes_the_example_payload() -> None:
    """P3-01. The fixture's own commentary named an evidence class the payload does not use."""
    example = _example_manifest()
    comment = example["$comment"]
    assert "CONFIGURATION_EVIDENCE_ONLY" not in comment
    assert example["model_runtime"]["model_evidence_source"] in comment
    assert "thinking_actual" in comment


# ===========================================================================================
# FAMILY_MUTATION_AUTHORITY_LEGALITY. The retired validator proved a family AGREED WITH ITSELF
# and called that legality: replacing T0's sole MECHANICAL_ONLY with HEAVY_MUTATION left every row
# consistent and the whole plane still passed. 25 of 50 authority substitutions were accepted, and
# lane, model id and effort were unpinned for every family the earlier work had not covered.
#
# These regressions are GENERATED from the canonical contract rather than hand-listed, so a family
# added later is attacked automatically instead of being silently exempt.
# ===========================================================================================


def _family_contract() -> dict[str, tuple[set[str], str, set[str]]]:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    rows, problems = validator.parse_columns(canonical_text, "FAMILY_SEMANTIC_CONTRACT", 4)
    assert rows and not problems, problems
    return {
        cls: (
            {i.strip() for i in intents.split(",") if i.strip()},
            authority,
            {e.strip() for e in efforts.split(",") if e.strip()},
        )
        for cls, intents, authority, efforts in rows
    }


def _lane_capability() -> dict[str, tuple[str, set[str]]]:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    rows, problems = validator.parse_columns(canonical_text, "LANE_CAPABILITY", 3)
    assert rows and not problems, problems
    return {lane: (model, {a.strip() for a in auth.split(",") if a.strip()}) for lane, model, auth in rows}


def _swap(row: str, index: int, value: str) -> str:
    fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
    fields[index] = value
    return "ROUTE: " + " | ".join(fields)


def _matrix_rows() -> list[str]:
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    return [r for r in (validator.block_lines(canonical_text, "ROLE_ROUTING_MATRIX") or []) if r.startswith("ROUTE:")]


_AUTHORITY_CASES = [
    (cls, legal, candidate)
    for cls, (_intents, legal, _efforts) in sorted(_family_contract().items())
    for candidate in sorted(validator.MUTATION_AUTHORITIES)
    if candidate != legal
]


@pytest.mark.parametrize(
    ("family", "legal", "illegal"),
    _AUTHORITY_CASES,
    ids=["{} {}->{}".format(f, legal, bad) for f, legal, bad in _AUTHORITY_CASES],
)
def test_no_family_may_carry_an_authority_it_does_not_own(sandbox: Path, family: str, legal: str, illegal: str) -> None:
    """The whole matrix, generated: every family against every other known authority.

    Every row of the family is replaced together, so the result is INTERNALLY consistent - which is
    exactly the state the retired check accepted.
    """
    text = read(sandbox, CANONICAL)
    mutated = text
    for row in _matrix_rows():
        if row[len("ROUTE:") :].split("|")[0].strip() == family:
            mutated = mutated.replace(row, _swap(row, 5, illegal), 1)
    assert mutated != text, family
    write(sandbox, CANONICAL, mutated)
    assert_rejects(sandbox, "the canonical mutation authority for {} is {}".format(family, legal))


def test_the_canonical_authority_of_every_family_is_accepted() -> None:
    """The POSITIVE anchor. A legality rule that rejects the canonical plane has closed nothing."""
    assert validator.collect_failures(REPO_ROOT) == []
    contract = _family_contract()
    routed: dict[str, set[str]] = {}
    for row in _matrix_rows():
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        routed.setdefault(fields[0], set()).add(fields[5])
    assert set(routed) == set(contract)
    for cls, authorities in routed.items():
        assert authorities == {contract[cls][1]}, cls


_LANE_CASES = [(cls, lane) for cls in sorted(_family_contract()) for lane in sorted(_lane_capability())]


@pytest.mark.parametrize(
    ("family", "lane"),
    _LANE_CASES,
    ids=["{} on {}".format(f, lane) for f, lane in _LANE_CASES],
)
def test_work_never_moves_to_a_lane_that_may_not_carry_it(sandbox: Path, family: str, lane: str) -> None:
    """A family can keep its correct authority while the WORK moves to a lane that must not have it."""
    contract = _family_contract()
    capability = _lane_capability()
    authority = contract[family][1]
    model_id = capability[lane][0]
    text = read(sandbox, CANONICAL)
    mutated = text
    for row in _matrix_rows():
        fields = [f.strip() for f in row[len("ROUTE:") :].split("|")]
        if fields[0] != family:
            continue
        mutated = mutated.replace(row, _swap(_swap(row, 2, lane), 3, model_id), 1)
    if mutated == text:
        pytest.skip("the family already routes exactly this lane")
    write(sandbox, CANONICAL, mutated)
    legal_here = authority in capability[lane][1]
    if legal_here:
        return  # a lane trusted with this authority is not, by itself, a violation
    assert failures(sandbox), "{} was allowed to run on {}, which may only carry {}".format(
        family, lane, sorted(capability[lane][1])
    )


@pytest.mark.parametrize("family", sorted(_family_contract()))
def test_no_lane_may_be_used_with_a_model_id_that_is_not_its_own(sandbox: Path, family: str) -> None:
    text = read(sandbox, CANONICAL)
    mutated = text
    for row in _matrix_rows():
        if row[len("ROUTE:") :].split("|")[0].strip() == family:
            mutated = mutated.replace(row, _swap(row, 3, "totally-made-up"), 1)
    assert mutated != text, family
    write(sandbox, CANONICAL, mutated)
    assert_rejects(sandbox, "canonical identity")


@pytest.mark.parametrize("family", sorted(_family_contract()))
def test_no_family_may_route_at_an_effort_it_is_not_legal_at(sandbox: Path, family: str) -> None:
    contract = _family_contract()
    legal = contract[family][2]
    illegal = next(e for e in ("low", "medium", "high", "xhigh", "max") if e not in legal)
    text = read(sandbox, CANONICAL)
    mutated = text
    for row in _matrix_rows():
        if row[len("ROUTE:") :].split("|")[0].strip() == family:
            mutated = mutated.replace(row, _swap(row, 4, illegal), 1)
    assert mutated != text, family
    write(sandbox, CANONICAL, mutated)
    assert failures(sandbox), "{} was allowed at illegal effort {}".format(family, illegal)


def test_an_undeclared_lane_is_not_a_routable_lane(sandbox: Path) -> None:
    patch(
        sandbox,
        CANONICAL,
        "ROUTE: T0 | STATUS | GPT-5.6 Luna | - | low | MECHANICAL_ONLY",
        "ROUTE: T0 | STATUS | GPT-9 Vega | - | low | MECHANICAL_ONLY",
    )
    assert_rejects(sandbox, "does not declare")


def test_a_declared_lane_nothing_routes_is_rejected(sandbox: Path) -> None:
    """The other direction: the capability block may not carry a lane the matrix never uses."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- LANE_CAPABILITY_END -->"
    write(sandbox, CANONICAL, text.replace(marker, "- GPT-9 Vega :: - :: READ_ONLY\n" + marker, 1))
    assert_rejects(sandbox, "no route uses")


def test_the_read_only_family_set_is_derived_not_restated() -> None:
    """The retired check hardcoded {T3C, T3D, T3E, XR}; a family could be read-only in one place
    and mutating in another. The set now comes from the canonical contract."""
    source = (REPO_ROOT / "scripts/crypto_core/validate_agent_os_v2.py").read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    assert '{"T3C", "T3D", "T3E", "XR"}' not in code
    assert "read_only_families = {" in code
    contract = _family_contract()
    derived = {cls for cls, (_i, authority, _e) in contract.items() if authority == "READ_ONLY"}
    assert derived == {"T3C", "T3D", "T3E", "T4", "XR"}


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("a malformed contract row", ("- T0 :: STATUS :: MECHANICAL_ONLY :: low", "- T0 :: STATUS :: low")),
        ("an unknown authority", ("- T0 :: STATUS :: MECHANICAL_ONLY :: low", "- T0 :: STATUS :: OMNIPOTENT :: low")),
        (
            "an unknown effort",
            ("- T0 :: STATUS :: MECHANICAL_ONLY :: low", "- T0 :: STATUS :: MECHANICAL_ONLY :: turbo"),
        ),
        ("a dropped family", ("- T0 :: STATUS :: MECHANICAL_ONLY :: low\n", "")),
        (
            "a malformed lane row",
            ("- GPT-6 Astra :: gpt-6-astra :: T4", "- GPT-6 Astra :: T4"),
        ),
        (
            "a lane trusted with an unknown family",
            ("- GPT-5.6 Terra :: - :: T2", "- GPT-5.6 Terra :: - :: T9"),
        ),
    ],
    ids=[
        "a malformed contract row",
        "an unknown authority",
        "an unknown effort",
        "a dropped family",
        "a malformed lane row",
        "a lane trusted with an unknown family",
    ],
)
def test_the_contract_blocks_are_themselves_validated(sandbox: Path, label: str, mutate: tuple) -> None:
    old, new = mutate
    patch(sandbox, CANONICAL, old, new)
    assert failures(sandbox), "the contract accepted: {}".format(label)


# ===========================================================================================
# ACTIVE_ROUTING_SEMANTIC_ALIGNMENT. The terminal Astra audit of #377 found ACTIVE prose promising
# work the executable authority prohibited: canonical 3.4 gave Codex GPT-5.6 Sol bounded
# implementation, bounded repair and ordinary review while Sol appeared in neither LANE_CAPABILITY
# nor the ROUTE matrix, and three surfaces gave GPT-5.6 Terra ordinary independent review while
# Terra carries BOUNDED_MUTATION only. Prose that promises a route nobody can legally take is not a
# documentation defect - it is an instruction to do something the gate will refuse.
# ===========================================================================================

ORACLE_SOL_LANE = "Codex GPT-5.6 Sol"
ORACLE_SOL_MODEL_ID = "gpt-5.6-sol"
ORACLE_SOL_FAMILIES = {"T2", "T3C"}


def test_the_sol_lane_is_declared_with_exactly_its_two_duties() -> None:
    rows, problems = validator.parse_columns(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "LANE_CAPABILITY", 3
    )
    assert rows and not problems, problems
    declared = {lane: (model, {f.strip() for f in fams.split(",")}) for lane, model, fams in rows}
    assert ORACLE_SOL_LANE in declared, "the prose gives Sol duties; the lane must exist"
    model_id, families = declared[ORACLE_SOL_LANE]
    assert model_id == ORACLE_SOL_MODEL_ID
    assert families == ORACLE_SOL_FAMILIES, "Sol carries bounded implementation and review, nothing else"


@pytest.mark.parametrize(
    "row",
    [
        "ROUTE: T2 | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5.6-sol | medium | BOUNDED_MUTATION",
        "ROUTE: T3C | REVIEW | Codex GPT-5.6 Sol | gpt-5.6-sol | medium | READ_ONLY",
        "ROUTE: T3C | REVIEW | Codex GPT-5.6 Sol | gpt-5.6-sol | high | READ_ONLY",
        "ROUTE: T3C | REVIEW | Codex GPT-5.6 Sol | gpt-5.6-sol | xhigh | READ_ONLY",
    ],
    ids=["T2 bounded implementation", "T3C review medium", "T3C review high", "T3C review xhigh"],
)
def test_every_duty_the_prose_gives_sol_has_a_legal_route(row: str) -> None:
    """The POSITIVE side of the Astra finding: a promised duty must be expressible."""
    canonical_text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    rows = validator.block_lines(canonical_text, "ROLE_ROUTING_MATRIX") or []
    assert row in rows, "prose promises this duty but the matrix does not route it"


@pytest.mark.parametrize(
    ("label", "row"),
    [
        (
            "Sol on capability-critical implementation",
            "ROUTE: T3B | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5.6-sol | max | CAPABILITY_CRITICAL_MUTATION",
        ),
        (
            "Sol on the protected gate",
            "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Codex GPT-5.6 Sol | gpt-5.6-sol | xhigh | READ_ONLY",
        ),
        (
            "Sol on heavy implementation",
            "ROUTE: T3A | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5.6-sol | xhigh | HEAVY_MUTATION",
        ),
        (
            "Sol carrying an authority it does not have",
            "ROUTE: T2 | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5.6-sol | medium | CAPABILITY_CRITICAL_MUTATION",
        ),
        (
            "Sol under a wrong model id",
            "ROUTE: T2 | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5-6-sol | medium | BOUNDED_MUTATION",
        ),
        (
            "Sol at an illegal T2 effort",
            "ROUTE: T2 | IMPLEMENTATION,REPAIR | Codex GPT-5.6 Sol | gpt-5.6-sol | max | BOUNDED_MUTATION",
        ),
        (
            "Sol at an illegal review effort",
            "ROUTE: T3C | REVIEW | Codex GPT-5.6 Sol | gpt-5.6-sol | low | READ_ONLY",
        ),
        ("Sol on architecture", "ROUTE: T3D | ARCHITECTURE | Codex GPT-5.6 Sol | gpt-5.6-sol | high | READ_ONLY"),
        (
            "Sol on prompt architecture",
            "ROUTE: T3E | PROMPT_ARCHITECTURE | Codex GPT-5.6 Sol | gpt-5.6-sol | high | READ_ONLY",
        ),
        ("Terra given ordinary review", "ROUTE: T3C | REVIEW | GPT-5.6 Terra | - | medium | READ_ONLY"),
        (
            "Terra given read-only authority",
            "ROUTE: T2 | IMPLEMENTATION,REPAIR | GPT-5.6 Terra | - | medium | READ_ONLY",
        ),
        (
            "Sonnet given ordinary review",
            "ROUTE: T3C | REVIEW | Claude Sonnet 5 | claude-sonnet-5 | medium | READ_ONLY",
        ),
    ],
    ids=[
        "Sol on capability-critical implementation",
        "Sol on the protected gate",
        "Sol on heavy implementation",
        "Sol carrying an authority it does not have",
        "Sol under a wrong model id",
        "Sol at an illegal T2 effort",
        "Sol at an illegal review effort",
        "Sol on architecture",
        "Sol on prompt architecture",
        "Terra given ordinary review",
        "Terra given read-only authority",
        "Sonnet given ordinary review",
    ],
)
def test_a_limited_lane_stays_limited(sandbox: Path, label: str, row: str) -> None:
    """Adding a lane for two duties must not quietly make it a general lane."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert failures(sandbox), "the matrix accepted: {}".format(label)


def test_ordinary_review_keeps_a_cross_family_option(sandbox: Path) -> None:
    """Independence means a reviewer that did not implement the work EXISTS, not that it is wished for."""
    lanes = {r[2] for r in _routes() if r[0] == "T3C"}
    assert lanes == {"Claude Opus 5", ORACLE_SOL_LANE}
    text = read(sandbox, CANONICAL)
    stripped = text
    for row in validator.block_lines(text, "ROLE_ROUTING_MATRIX") or []:
        if row.startswith("ROUTE: T3C ") and ORACLE_SOL_LANE in row:
            stripped = stripped.replace(row + "\n", "", 1)
    assert stripped != text
    write(sandbox, CANONICAL, stripped)
    assert_rejects(sandbox, "at least")


def test_the_independence_rule_is_stated_where_routing_is_decided() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "CROSS_FAMILY_REVIEW_PREFERENCE" in canonical
    assert (
        "When Opus implemented the work, prefer Sol for the ordinary review; when Sol implemented it, prefer Opus"
        in canonical
    )
    assert "A same-model review remains `SELF_AUDIT_ONLY_NOT_INDEPENDENT` whichever lane it runs on" in canonical


def test_no_active_surface_assigns_review_to_a_lane_that_cannot_review() -> None:
    """The Astra finding, generalised: every ACTIVE review claim is checked against LANE_CAPABILITY.

    Historical regions are excluded by construction - a dated record of a retired regime is evidence,
    not an instruction.
    """
    rows, problems = validator.parse_columns(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "LANE_CAPABILITY", 3
    )
    assert rows and not problems, problems
    cannot_review = {
        lane.replace("Codex ", "")
        for lane, _model, families in rows
        if "T3C" not in {f.strip() for f in families.split(",")}
    }
    assert cannot_review, "the probe would prove nothing if every lane could review"
    review_claim = re.compile(r"(ordinary[- ](?:fresh-context )?(?:independent )?review|independent review)", re.I)
    for rel in (
        CANONICAL,
        "docs/crypto_core/model_prompting_guide.md",
        ".codex/skills/crypto-core-max-safe/SKILL.md",
        ".claude/skills/crypto-core-token-efficient-loop/SKILL.md",
        "CLAUDE.md",
        "AGENTS.md",
    ):
        body = (REPO_ROOT / rel).read_text(encoding="utf-8-sig").split("<!-- HISTORICAL_RECORD_BEGIN -->")[0]
        for number, line in enumerate(body.splitlines(), 1):
            if not review_claim.search(line):
                continue
            for lane in cannot_review:
                assert lane not in line, "{}:{} assigns review to {}: {}".format(rel, number, lane, line.strip())


def test_terra_and_sonnet_profiles_no_longer_claim_review() -> None:
    """The three exact surfaces the audit named, pinned so the claim cannot come back."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "Bounded profile (Terra).** Bounded implementation or ordinary independent review" not in canonical
    assert "GPT-5.6 Terra is a BOUNDED IMPLEMENTATION lane only" in canonical
    guide = (REPO_ROOT / "docs/crypto_core/model_prompting_guide.md").read_text(encoding="utf-8-sig")
    assert "### 4.3 Bounded implementation profile (Terra, Claude Sonnet 5)" in guide
    assert "ordinary review profile (Terra" not in guide
    adapter = (REPO_ROOT / ".codex/skills/crypto-core-max-safe/SKILL.md").read_text(encoding="utf-8-sig")
    assert "Terra carries no review duty." in adapter
    assert "Repo-native lane (Codex GPT-5.6 Sol)" in adapter


# ===========================================================================================
# RELATIONAL_IDENTITY_PROOF and CONTINUITY_REQUIREDNESS.
#
# A populated `model_actual` proved only that SOMETHING was observed, never that it was the runtime
# the route required: a manifest requesting `gpt-6-astra` while telemetry reported `gpt-5.6-terra`
# passed as ordinary matching evidence, so work - or a protected audit - performed by the wrong
# runtime looked valid and STOP_MODEL_MISMATCH never fired. Separately, `invalidations` was added to
# the manifest field map and never to `required`, so the record of facts that must not be reused
# could be omitted entirely and stale completed-gate evidence stayed quietly reusable.
#
# The identity cases are generated over real lane identities from BOTH providers, because a relation
# that only works for the protected lane is not a relation.
# ===========================================================================================

ORACLE_LANE_IDENTITIES = ("claude-opus-5", "claude-sonnet-5", "gpt-5.6-sol", "gpt-6-astra")
ORACLE_EXECUTION_PROVING_CLASSES = {"RUNTIME_TELEMETRY", "USER_ATTESTED_UI_SELECTION"}


def _runtime(**overrides: object) -> dict:
    manifest = _example_manifest()
    manifest["model_runtime"].update(overrides)
    return manifest


_MISMATCH_CASES = [
    (required, observed, source)
    for required in ORACLE_LANE_IDENTITIES
    for observed in ORACLE_LANE_IDENTITIES
    if observed != required
    for source in sorted(ORACLE_EXECUTION_PROVING_CLASSES)
]


@pytest.mark.parametrize(
    ("required", "observed", "source"),
    _MISMATCH_CASES,
    ids=["{} ran {} under {}".format(r, o, s) for r, o, s in _MISMATCH_CASES],
)
def test_an_observed_runtime_that_is_not_the_required_one_is_never_matching_evidence(
    required: str, observed: str, source: str
) -> None:
    """B1. Every ordered pair of real lane identities, in both providers, under both proving classes."""
    manifest = _runtime(
        model_id=required, model_requested=required, model_actual=observed, model_evidence_source=source
    )
    found = validator.check_manifest_instance("probe", manifest)
    assert found, "{} claimed a clean match while {} actually ran".format(source, observed)
    assert any("CONTRADICTED" in item for item in found), found


@pytest.mark.parametrize("identity", ORACLE_LANE_IDENTITIES)
@pytest.mark.parametrize("source", sorted(ORACLE_EXECUTION_PROVING_CLASSES))
def test_an_observed_runtime_that_matches_still_passes(identity: str, source: str) -> None:
    """The POSITIVE anchor: a relation that rejects the correct runtime has closed nothing."""
    manifest = _runtime(
        model_id=identity, model_requested=identity, model_actual=identity, model_evidence_source=source
    )
    assert validator.check_manifest_instance("probe", manifest) == []


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        (
            "telemetry claiming proof with nothing observed",
            {
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": None,
                "model_evidence_source": "RUNTIME_TELEMETRY",
            },
        ),
        (
            "an unknown class carrying an observation",
            {
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": "claude-opus-5",
                "model_evidence_source": "UNKNOWN",
            },
        ),
        (
            "configuration evidence dressed as execution",
            {
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": "claude-opus-5",
                "model_evidence_source": "CONFIGURATION_EVIDENCE_ONLY",
            },
        ),
        (
            "CONTRADICTED that contradicts nothing",
            {
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": "claude-opus-5",
                "model_evidence_source": "CONTRADICTED",
            },
        ),
        (
            "two different requests recorded at once",
            {
                "model_id": "claude-opus-5",
                "model_requested": "gpt-6-astra",
                "model_actual": "claude-opus-5",
                "model_evidence_source": "RUNTIME_TELEMETRY",
            },
        ),
        (
            "an observed fallback beside a clean-match claim",
            {
                "model_id": "claude-opus-5",
                "model_requested": "claude-opus-5",
                "model_actual": "claude-opus-5",
                "model_evidence_source": "RUNTIME_TELEMETRY",
                "model_fallback": "fell back to claude-sonnet-5",
            },
        ),
        (
            "a lane with no API id whose observation differs",
            {
                "model_id": None,
                "model_requested": "GPT-5.6 Terra",
                "model_actual": "GPT-5.6 Luna",
                "model_evidence_source": "RUNTIME_TELEMETRY",
            },
        ),
    ],
    ids=[
        "telemetry claiming proof with nothing observed",
        "an unknown class carrying an observation",
        "configuration evidence dressed as execution",
        "CONTRADICTED that contradicts nothing",
        "two different requests recorded at once",
        "an observed fallback beside a clean-match claim",
        "a lane with no API id whose observation differs",
    ],
)
def test_identity_evidence_siblings_fail_closed(label: str, overrides: dict) -> None:
    assert validator.check_manifest_instance("probe", _runtime(**overrides)), label


def test_an_honestly_recorded_fallback_is_representable() -> None:
    """A fallback must be RECORDABLE, or a session that hit one could not describe it truthfully."""
    manifest = _runtime(
        model_id="claude-opus-5",
        model_requested="claude-opus-5",
        model_actual="claude-sonnet-5",
        model_evidence_source="CONTRADICTED",
        model_fallback="fell back to claude-sonnet-5",
    )
    assert validator.check_manifest_instance("probe", manifest) == []


@pytest.mark.parametrize(
    ("label", "overrides"),
    [
        (
            "a contradicted identity keeps a proven effort",
            {
                "model_actual": "claude-sonnet-5",
                "model_evidence_source": "CONTRADICTED",
                "effort_evidence_source": "RUNTIME_TELEMETRY",
                "observed_effort": "xhigh",
            },
        ),
        (
            "a proven identity keeps an unknown effort",
            {"effort_evidence_source": "UNKNOWN", "observed_effort": None},
        ),
        (
            "an unknown identity keeps a proven effort",
            {
                "model_actual": None,
                "model_evidence_source": "UNKNOWN",
                "effort_evidence_source": "RUNTIME_TELEMETRY",
                "requested_effort": "max",
                "observed_effort": "max",
            },
        ),
        ("a proven identity keeps an unknown thinking state", {"thinking_actual": "UNKNOWN"}),
        (
            "a contradicted effort keeps a proven identity",
            {
                "effort_evidence_source": "CONTRADICTED",
                "observed_effort": "high",
                "effort_mismatch_waiver": {"status": "NOT_GRANTED", "evidence": None},
            },
        ),
    ],
    ids=[
        "a contradicted identity keeps a proven effort",
        "a proven identity keeps an unknown effort",
        "an unknown identity keeps a proven effort",
        "a proven identity keeps an unknown thinking state",
        "a contradicted effort keeps a proven identity",
    ],
)
def test_a_contradiction_in_one_dimension_never_erases_another(label: str, overrides: dict) -> None:
    """R2. The identity relation must not have quietly collapsed the dimensional split."""
    manifest = _example_manifest()
    manifest["model_runtime"].update(
        model_id="claude-opus-5", model_requested="claude-opus-5", model_actual="claude-opus-5"
    )
    manifest["model_runtime"].update(overrides)
    assert validator.check_manifest_instance("probe", manifest) == [], label


def test_the_authoritative_identity_is_documented_and_implemented() -> None:
    """R3. Two names that look equivalent must not be compared inconsistently."""
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "`MODEL_ID` is the AUTHORITATIVE exact identity" in canonical
    assert "where both carry a payload they must agree" in canonical
    assert validator.EXECUTION_PROVING_CLASSES == frozenset(ORACLE_EXECUTION_PROVING_CLASSES)
    runtime = {"model_id": "claude-opus-5", "model_requested": "gpt-6-astra"}
    assert validator.required_model_identity(runtime) == "claude-opus-5"
    assert validator.required_model_identity({"model_id": None, "model_requested": "GPT-5.6 Terra"}) == "GPT-5.6 Terra"
    assert validator.required_model_identity({"model_id": None, "model_requested": None}) is None


# --- CONTINUITY_REQUIREDNESS ------------------------------------------------------------------


def test_invalidations_is_required() -> None:
    """B2. An absent record is indistinguishable from 'the producer never said'."""
    assert "invalidations" in validator.MANIFEST_REQUIRED
    manifest = _example_manifest()
    manifest.pop("invalidations")
    assert validator.check_manifest_instance("probe", manifest)


def test_an_empty_invalidation_list_is_truthful_and_valid() -> None:
    """R5. Nothing was invalidated is a real answer; never fabricate an entry to satisfy shape."""
    manifest = _example_manifest()
    manifest["invalidations"] = []
    assert validator.check_manifest_instance("probe", manifest) == []


@pytest.mark.parametrize(
    ("label", "value"),
    [
        ("a bare string", "none"),
        ("an object", {}),
        ("null", None),
        ("a filler entry", ["ㅤ"]),
        ("a null entry", [None]),
        ("a numeric entry", [7]),
    ],
    ids=["a bare string", "an object", "null", "a filler entry", "a null entry", "a numeric entry"],
)
def test_invalidations_must_be_a_list_of_operational_facts(label: str, value: object) -> None:
    manifest = _example_manifest()
    manifest["invalidations"] = value
    assert validator.check_manifest_instance("probe", manifest), label


def test_every_field_the_example_carries_is_required() -> None:
    """CLOSED-WORLD: no load-bearing field may be omittable, and requiredness has ONE source.

    `$comment` is the single documented exception - it is documentation about the artifact.
    """
    example = _example_manifest()
    omittable = sorted(set(example) - set(validator.MANIFEST_REQUIRED) - {"$comment"})
    assert omittable == [], "these load-bearing fields may be omitted entirely: {}".format(omittable)
    for field in sorted(set(example) - {"$comment"}):
        probe = _example_manifest()
        probe.pop(field)
        assert validator.check_manifest_instance("probe", probe), field


def test_requiredness_agrees_with_the_generated_schema_in_both_directions() -> None:
    schema = validator.emit_manifest_schema()
    assert set(schema["required"]) == set(validator.MANIFEST_REQUIRED)
    committed = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text("utf-8-sig")
    )
    assert set(committed["required"]) == set(validator.MANIFEST_REQUIRED)
    assert "invalidations" in committed["required"]


def test_continuity_requiredness_is_documented() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "CONTINUITY_REQUIREDNESS" in canonical
    assert "An EMPTY list is the truthful way to record that nothing was invalidated" in canonical
    assert 'An omitted load-bearing field never means "unknown but safe"' in canonical


# ===========================================================================================
# TRUST-BOUNDARY TOTALITY. The protected audit of #378 returned P2=4, P3=1, all of them failures
# of three underlying contracts rather than five isolated bugs:
#
#   RC1  shape must be established BEFORE relational logic consumes a value
#   RC2  a process exit status has an exact TYPE; coercion is not a status
#   RC3  a lane's duty boundary is the ROUTE FAMILY, never the mutation authority
#
# plus RC4 (independence is canonical policy, not adapter policy) and RC5 (a dependency probe reads
# import STRUCTURE, not prose).
# ===========================================================================================

ORACLE_JSON_SHAPES = [
    ("null", None),
    ("bool", True),
    ("int", 7),
    ("float", 1.5),
    ("string", "x"),
    ("list", []),
    ("object", {}),
    ("nested list", [[]]),
    ("list of objects", [{}]),
]

ORACLE_RELATION_RUNTIME_FIELDS = (
    "model_evidence_source",
    "effort_evidence_source",
    "model_id",
    "model_requested",
    "model_actual",
    "model_fallback",
    "thinking_actual",
    "observed_effort",
    "requested_effort",
    "host_setting_raw",
    "capability_mode",
)

ORACLE_RELATION_TOP_FIELDS = (
    "openai_agentic_capacity",
    "claude_capacity",
    "capacity_routing_mode",
    "authorization",
    "model_runtime",
    "invalidations",
    "completed_gates",
    "blockers",
    "next_safe_action",
    "head_sha",
    "pr_number",
    "open_pr_count",
    "ci_state",
    "branch_evidence",
)

_TOTALITY_CASES = [
    ("model_runtime." + f, s_label, s) for f in ORACLE_RELATION_RUNTIME_FIELDS for s_label, s in ORACLE_JSON_SHAPES
] + [(f, s_label, s) for f in ORACLE_RELATION_TOP_FIELDS for s_label, s in ORACLE_JSON_SHAPES]


@pytest.mark.parametrize(
    ("field", "shape_label", "shape"),
    _TOTALITY_CASES,
    ids=["{} = {}".format(f, s) for f, s, _v in _TOTALITY_CASES],
)
def test_no_json_shape_can_crash_the_manifest_gate(field: str, shape_label: str, shape: object) -> None:
    """RC1. `x in some_set` hashes x, so a list or dict crashed the PUBLIC gate with TypeError.

    Both the public boundary AND the relation function are exercised, because the relation is part
    of the published contract and a caller may reach it directly.
    """
    manifest = _example_manifest()
    if field.startswith("model_runtime."):
        manifest["model_runtime"][field.split(".", 1)[1]] = shape
    else:
        manifest[field] = shape
    for judge in (validator.check_manifest_instance, validator.manifest_relation_failures):
        result = judge("probe", manifest)  # must not raise
        assert isinstance(result, list)


@pytest.mark.parametrize(("shape_label", "shape"), ORACLE_JSON_SHAPES, ids=[s for s, _v in ORACLE_JSON_SHAPES])
def test_the_whole_manifest_may_be_any_json_value(shape_label: str, shape: object) -> None:
    for judge in (validator.check_manifest_instance, validator.manifest_relation_failures):
        assert isinstance(judge("probe", shape), list)


def test_the_evidence_source_shapes_the_audit_reported_are_rejected_not_raised() -> None:
    """The two exact minimal reproductions from the protected audit."""
    for shape in ([], {}):
        manifest = _example_manifest()
        manifest["model_runtime"]["model_evidence_source"] = shape
        found = validator.check_manifest_instance("probe", manifest)
        assert found, shape
        assert isinstance(found, list)


def test_membership_is_total_by_construction_not_by_catching() -> None:
    """The guard on the public gate is defence in depth; the primitive is why totality holds."""
    assert validator.is_vocabulary_member("RUNTIME_TELEMETRY", validator.MODEL_EVIDENCE_CLASSES) is True
    for hostile in ([], {}, None, 7, 1.5, True, [[]]):
        assert validator.is_vocabulary_member(hostile, validator.MODEL_EVIDENCE_CLASSES) is False
        assert validator.is_vocabulary_member(hostile, validator.EXECUTION_PROVING_CLASSES) is False
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
    for raw in (
        "in EXECUTION_PROVING_CLASSES",
        "in CAPACITY_AVAILABLE",
        "in CAPACITY_CONSTRAINED",
        "in MODEL_EVIDENCE_CLASSES",
        "in THINKING_STATES",
    ):
        for line in code.splitlines():
            if raw in line:
                assert "is_vocabulary_member" in line, line.strip()


def test_the_cli_fails_closed_on_a_malformed_manifest(tmp_path: Path) -> None:
    """RC1. `--manifest --json` must never escape as an uncaught traceback."""
    manifest = _example_manifest()
    manifest["model_runtime"]["model_evidence_source"] = []
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    done = subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [sys.executable, str(VALIDATOR_PATH), "--manifest", str(path), "--json"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode != 0, done.stdout + done.stderr
    assert "Traceback" not in done.stderr, done.stderr
    json.loads(done.stdout)


# --- RC2  exact execution status type ---------------------------------------------------------

ORACLE_EXIT_STATUS_MATRIX = [
    ("0", 0, "VALIDATOR_EXIT=0"),
    ("3", 1, "VALIDATOR_EXIT=3"),
    ("$null", 1, "NO_EXIT_STATUS"),
    ("$false", 1, "INVALID_EXIT_STATUS_TYPE"),
    ("$true", 1, "INVALID_EXIT_STATUS_TYPE"),
    ("'0'", 1, "INVALID_EXIT_STATUS_TYPE"),
    ("0.0", 1, "INVALID_EXIT_STATUS_TYPE"),
    ("@()", 1, "INVALID_EXIT_STATUS_TYPE"),
    ("@{}", 1, "INVALID_EXIT_STATUS_TYPE"),
]


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
@pytest.mark.parametrize(
    ("literal", "expected_code", "expected_marker"),
    ORACLE_EXIT_STATUS_MATRIX,
    ids=[lit for lit, _c, _m in ORACLE_EXIT_STATUS_MATRIX],
)
def test_only_a_real_integer_exit_status_can_mean_success(
    literal: str, expected_code: int, expected_marker: str
) -> None:
    """RC2, EXECUTED. `-ne 0` coerces: '0', 0.0 and $false all compare equal to zero, and
    `@() -ne 0` yields an empty array whose falsiness skips the failure branch - four non-process
    values readable as a successful validator run. The literals are evaluated IN PROCESS, because
    `powershell -File` stringifies every argument and would test nothing.
    """
    shell = _powershell()
    assert shell
    script = str(REPO_ROOT / "scripts" / "crypto_core" / "audit_agent_setup.ps1")
    command = "& '{}' -ExitStatusProbe -ProbeExitStatus {}; exit $LASTEXITCODE".format(script, literal)
    done = subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [shell, "-NoProfile", "-Command", command],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )
    assert done.returncode == expected_code, done.stdout + done.stderr
    assert expected_marker in done.stdout, done.stdout


def test_the_exit_status_type_is_established_before_any_comparison() -> None:
    body = _audit_source().split("#>", 1)[1]
    assert "$validatorExit -is [int]" in body
    assert "INVALID_EXIT_STATUS_TYPE" in body
    assert "NO_EXIT_STATUS" in body


# --- RC3  lane duty is the route family -------------------------------------------------------


def _lane_families() -> dict[str, tuple[str, set[str]]]:
    rows, problems = validator.parse_columns(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "LANE_CAPABILITY", 3
    )
    assert rows and not problems, problems
    return {lane: (model, {f.strip() for f in fams.split(",") if f.strip()}) for lane, model, fams in rows}


ORACLE_LANE_FAMILIES = {
    "Claude Opus 5": {"T3A", "T3B", "T3C", "T3D", "T3E"},
    "Claude Sonnet 5": {"T1", "T2"},
    "Codex GPT-5.6 Sol": {"T2", "T3C"},
    "GPT-5.6 Terra": {"T2"},
    "GPT-5.6 Luna": {"T0", "T1"},
    "GPT-6 Astra": {"T4"},
    "Deep Research": {"XR"},
}


def test_lane_capability_declares_families_not_mutation_authorities() -> None:
    """RC3. READ_ONLY conflates review, architecture, prompt architecture, Class C and research."""
    declared = {lane: families for lane, (_model, families) in _lane_families().items()}
    assert declared == ORACLE_LANE_FAMILIES
    for _lane, families in declared.items():
        assert not families & set(validator.MUTATION_AUTHORITIES), "duty must not be an authority"


_FAMILY_LANE_CASES = [
    (family, lane)
    for family in sorted(ORACLE_LANE_FAMILIES["Claude Opus 5"] | {"T0", "T1", "T2", "T4", "XR"})
    for lane in sorted(ORACLE_LANE_FAMILIES)
]


@pytest.mark.parametrize(
    ("family", "lane"),
    _FAMILY_LANE_CASES,
    ids=["{} on {}".format(f, lane) for f, lane in _FAMILY_LANE_CASES],
)
def test_every_family_lane_pair_matches_the_declared_duty(sandbox: Path, family: str, lane: str) -> None:
    """The whole matrix, generated: a lane may carry a family only if it is trusted with it."""
    capability = _lane_families()
    model_id = capability[lane][0]
    legal = family in capability[lane][1]
    contract = {
        cls: (intents, authority, efforts)
        for cls, intents, authority, efforts in (
            validator.parse_columns(read(sandbox, CANONICAL), "FAMILY_SEMANTIC_CONTRACT", 4)[0] or []
        )
    }
    intents, authority, efforts = contract[family]
    effort = sorted(e.strip() for e in efforts.split(","))[0]
    row = "ROUTE: {} | {} | {} | {} | {} | {}".format(family, intents, lane, model_id, effort, authority)
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    found = failures(sandbox)
    if legal:
        # A duty-legal pair must not be rejected FOR THE DUTY; other contracts may still object.
        assert not any("is trusted only with" in item for item in found), found
    else:
        assert any("is trusted only with" in item for item in found), "{} on {} was accepted".format(family, lane)


@pytest.mark.parametrize(
    ("label", "row"),
    [
        (
            "XR on the repo-native lane",
            "ROUTE: XR | EXTERNAL_RESEARCH | Codex GPT-5.6 Sol | gpt-5.6-sol | - | READ_ONLY",
        ),
        ("XR on the protected lane", "ROUTE: XR | EXTERNAL_RESEARCH | GPT-6 Astra | gpt-6-astra | - | READ_ONLY"),
        ("XR on the heavy lane", "ROUTE: XR | EXTERNAL_RESEARCH | Claude Opus 5 | claude-opus-5 | - | READ_ONLY"),
        (
            "architecture on the protected lane",
            "ROUTE: T3D | ARCHITECTURE | GPT-6 Astra | gpt-6-astra | high | READ_ONLY",
        ),
        ("review on the research lane", "ROUTE: T3C | REVIEW | Deep Research | - | medium | READ_ONLY"),
        (
            "architecture on the repo-native lane",
            "ROUTE: T3D | ARCHITECTURE | Codex GPT-5.6 Sol | gpt-5.6-sol | high | READ_ONLY",
        ),
        (
            "bounded work on the mechanical lane",
            "ROUTE: T2 | IMPLEMENTATION,REPAIR | GPT-5.6 Luna | - | medium | BOUNDED_MUTATION",
        ),
        ("review on the bounded lane", "ROUTE: T3C | REVIEW | GPT-5.6 Terra | - | medium | READ_ONLY"),
    ],
    ids=[
        "XR on the repo-native lane",
        "XR on the protected lane",
        "XR on the heavy lane",
        "architecture on the protected lane",
        "review on the research lane",
        "architecture on the repo-native lane",
        "bounded work on the mechanical lane",
        "review on the bounded lane",
    ],
)
def test_the_historical_counterexamples_are_rejected(sandbox: Path, label: str, row: str) -> None:
    """Every route the coarse READ_ONLY boundary used to let through."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(sandbox, CANONICAL, text.replace(marker, row + "\n" + marker, 1))
    assert failures(sandbox), "the matrix accepted: {}".format(label)


def test_no_lane_carries_a_family_it_never_routes(sandbox: Path) -> None:
    """No dead reserve: a declared duty must correspond to a real canonical route."""
    text = read(sandbox, CANONICAL)
    marker = "- Deep Research :: - :: XR"
    write(sandbox, CANONICAL, text.replace(marker, "- Deep Research :: - :: XR,T3D", 1))
    assert_rejects(sandbox, "the declared duty is unreachable")


# --- RC4  independence is canonical policy ----------------------------------------------------


def test_the_independence_vocabulary_is_canonical_and_exact() -> None:
    rows = validator.parse_registry((REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "INDEPENDENCE_VOCABULARY")
    assert rows
    states = {row.split("::")[0].strip() for row in rows}
    assert states == {
        "SELF_AUDIT_ONLY_NOT_INDEPENDENT",
        "ORDINARY_INDEPENDENT_REVIEW",
        "PROTECTED_CLASS_C_AUDIT",
    }
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "Claude Opus 5 reviewing Codex GPT-5.6 Sol's implementation IS ordinary independent review" in canonical
    assert "Neither lane is ever the protected gate" in canonical


def test_no_active_adapter_denies_a_route_canonical_doctrine_grants() -> None:
    """RC4. The retired line said 'No Claude session satisfies an independent audit' - overbroad,
    because Opus reviewing Sol-authored work is exactly ordinary independent review."""
    for rel in (
        ".claude/skills/crypto-core-token-efficient-loop/SKILL.md",
        "CLAUDE.md",
        ".codex/skills/crypto-core-max-safe/SKILL.md",
        "AGENTS.md",
        "docs/crypto_core/model_prompting_guide.md",
    ):
        body = (REPO_ROOT / rel).read_text(encoding="utf-8-sig").split("<!-- HISTORICAL_RECORD_BEGIN -->")[0]
        for number, line in enumerate(body.splitlines(), 1):
            flat = " ".join(line.split()).lower()
            for overbroad in (
                "no claude session satisfies an independent audit",
                "no codex session satisfies an independent audit",
                "a claude session never satisfies an independent audit",
            ):
                assert overbroad not in flat, "{}:{} denies a canonical route: {}".format(rel, number, line.strip())


def test_the_claude_adapter_defers_independence_to_canonical() -> None:
    adapter = (REPO_ROOT / ".claude/skills/crypto-core-token-efficient-loop/SKILL.md").read_text("utf-8-sig")
    flat = " ".join(adapter.split())
    assert "Independence credit is decided ONLY by canonical Agent OS routing and independence rules" in flat
    assert "no Claude lane satisfies protected Class C" in flat


# --- RC5  the dependency probe reads structure ------------------------------------------------


def test_the_import_probe_reads_structure_not_prose() -> None:
    """RC5. Prose is not code, and a string is not an import."""
    harmless = "# The controller requests a bounded report.\nimport json\n"
    assert _imported_modules(harmless) == {"json"}
    assert "requests" not in _imported_modules(harmless)
    assert _called_attributes(harmless) == set()
    assert "requests" in _imported_modules("import requests\n")
    assert "requests" in _imported_modules("from requests import get\n")
    assert "socket" in _imported_modules("import socket.socket\n")
    assert "shutil.rmtree" in _called_attributes("import shutil\nshutil.rmtree('/x')\n")
    assert _called_attributes('x = "shutil.rmtree(1)"\n') == set()


# ===========================================================================================
# EFFORT_RELATION_PROOF and EFFORT_MISMATCH_WAIVER.
#
# Effort has exactly the requested/observed shape identity has and was never given the relation:
# RUNTIME_TELEMETRY reporting `high` against a requested `xhigh` passed as ordinary matching
# evidence, and CONTRADICTED could claim a conflict that did not exist. Canonical doctrine also lets
# a human waive an effort mismatch for a specific task, which the manifest could not represent at
# all. Every matrix below is GENERATED from the effort enum and the evidence classes, so no effort
# value is special-cased.
# ===========================================================================================

ORACLE_EFFORTS = ("low", "medium", "high", "xhigh", "max")
ORACLE_WAIVER_STATUSES = ("NOT_APPLICABLE", "NOT_GRANTED", "HUMAN_GRANTED")
ORACLE_WAIVER_TEXT = "Human waived the xhigh->high effort mismatch for task PR9-EFFORT-WAIVER at head abc123"
ORACLE_CLEAN_IDENTITY = {
    "model_id": "claude-opus-5",
    "model_requested": "claude-opus-5",
    "model_actual": "claude-opus-5",
    "model_evidence_source": "RUNTIME_TELEMETRY",
    "model_fallback": None,
}


def _effort_manifest(requested: object, observed: object, source: object, status: object, evidence: object) -> dict:
    manifest = _example_manifest()
    runtime = manifest["model_runtime"]
    runtime.update(ORACLE_CLEAN_IDENTITY)
    runtime.update(requested_effort=requested, observed_effort=observed, effort_evidence_source=source)
    runtime["effort_mismatch_waiver"] = {"status": status, "evidence": evidence}
    return manifest


_EFFORT_MATRIX = [
    (requested, observed, source)
    for source in (
        "RUNTIME_TELEMETRY",
        "USER_ATTESTED_UI_SELECTION",
        "CONTRADICTED",
        "CONFIGURATION_EVIDENCE_ONLY",
        "UNKNOWN",
    )
    for requested in ORACLE_EFFORTS
    for observed in ORACLE_EFFORTS
]


@pytest.mark.parametrize(
    ("requested", "observed", "source"),
    _EFFORT_MATRIX,
    ids=["{} req={} obs={}".format(s, r, o) for r, o, s in _EFFORT_MATRIX],
)
def test_the_effort_relation_holds_across_the_whole_enum(requested: str, observed: str, source: str) -> None:
    """R1/R2, generated: 5 requested x 5 observed x 5 evidence classes.

    A proving class accepts only a match. CONTRADICTED accepts only a real mismatch, and then the
    waiver must say whether a human granted it. Classes that prove no observation reject any
    populated observed effort.
    """
    mismatch = requested != observed
    if source in ("RUNTIME_TELEMETRY", "USER_ATTESTED_UI_SELECTION"):
        expect_accept = not mismatch
        status = "NOT_APPLICABLE"
    elif source == "CONTRADICTED":
        expect_accept = mismatch
        status = "NOT_GRANTED" if mismatch else "NOT_APPLICABLE"
    else:
        expect_accept = False
        status = "NOT_APPLICABLE"
    found = validator.check_manifest_instance("probe", _effort_manifest(requested, observed, source, status, None))
    assert (found == []) is expect_accept, found


@pytest.mark.parametrize(
    ("label", "requested", "observed", "source", "status", "evidence", "accept"),
    [
        ("match + NOT_APPLICABLE", "xhigh", "xhigh", "RUNTIME_TELEMETRY", "NOT_APPLICABLE", None, True),
        ("match + NOT_GRANTED", "xhigh", "xhigh", "RUNTIME_TELEMETRY", "NOT_GRANTED", None, False),
        ("match + HUMAN_GRANTED", "xhigh", "xhigh", "RUNTIME_TELEMETRY", "HUMAN_GRANTED", ORACLE_WAIVER_TEXT, False),
        ("mismatch under a proving class", "xhigh", "high", "RUNTIME_TELEMETRY", "NOT_APPLICABLE", None, False),
        (
            "mismatch under a proving class with a waiver",
            "xhigh",
            "high",
            "RUNTIME_TELEMETRY",
            "HUMAN_GRANTED",
            ORACLE_WAIVER_TEXT,
            False,
        ),
        ("CONTRADICTED mismatch + NOT_GRANTED", "xhigh", "high", "CONTRADICTED", "NOT_GRANTED", None, True),
        (
            "CONTRADICTED mismatch + HUMAN_GRANTED + exact evidence",
            "xhigh",
            "high",
            "CONTRADICTED",
            "HUMAN_GRANTED",
            ORACLE_WAIVER_TEXT,
            True,
        ),
        (
            "CONTRADICTED mismatch + HUMAN_GRANTED + null evidence",
            "xhigh",
            "high",
            "CONTRADICTED",
            "HUMAN_GRANTED",
            None,
            False,
        ),
        (
            "CONTRADICTED mismatch + HUMAN_GRANTED + filler evidence",
            "xhigh",
            "high",
            "CONTRADICTED",
            "HUMAN_GRANTED",
            "ㅤ⠀",
            False,
        ),
        (
            "CONTRADICTED mismatch + HUMAN_GRANTED + whitespace evidence",
            "xhigh",
            "high",
            "CONTRADICTED",
            "HUMAN_GRANTED",
            "   ",
            False,
        ),
        ("CONTRADICTED mismatch + NOT_APPLICABLE", "xhigh", "high", "CONTRADICTED", "NOT_APPLICABLE", None, False),
        (
            "CONTRADICTED mismatch + NOT_GRANTED + evidence",
            "xhigh",
            "high",
            "CONTRADICTED",
            "NOT_GRANTED",
            ORACLE_WAIVER_TEXT,
            False,
        ),
        (
            "NOT_APPLICABLE + evidence",
            "xhigh",
            "xhigh",
            "RUNTIME_TELEMETRY",
            "NOT_APPLICABLE",
            ORACLE_WAIVER_TEXT,
            False,
        ),
        ("CONTRADICTED with nothing to contradict", "xhigh", "xhigh", "CONTRADICTED", "NOT_APPLICABLE", None, False),
        ("CONTRADICTED with no requested effort", None, "high", "CONTRADICTED", "NOT_GRANTED", None, False),
        ("unknown effort + NOT_APPLICABLE", "xhigh", None, "UNKNOWN", "NOT_APPLICABLE", None, True),
        (
            "unknown effort + a standing HUMAN_GRANTED",
            "xhigh",
            None,
            "UNKNOWN",
            "HUMAN_GRANTED",
            ORACLE_WAIVER_TEXT,
            False,
        ),
        # TARGET_BOUND_EXECUTION_PROOF: telemetry with no requested effort has nothing to prove against.
        ("no request + telemetry observation", None, "high", "RUNTIME_TELEMETRY", "NOT_APPLICABLE", None, False),
        ("unknown waiver status", "xhigh", "high", "CONTRADICTED", "WAIVED_FOREVER", ORACLE_WAIVER_TEXT, False),
    ],
    ids=lambda value: value if isinstance(value, str) and " " in value else None,
)
def test_the_effort_mismatch_waiver_matrix(
    label: str, requested: object, observed: object, source: str, status: str, evidence: object, accept: bool
) -> None:
    """R3/R8. A waiver exists only for a truthfully recorded CONTRADICTED mismatch, never rewrites
    either effort, and HUMAN_GRANTED needs the exact waiver as operational text."""
    found = validator.check_manifest_instance("probe", _effort_manifest(requested, observed, source, status, evidence))
    assert (found == []) is accept, "{}: {}".format(label, found)


def test_a_waiver_never_rewrites_the_true_observed_effort() -> None:
    """R3. Restating the actual as the requested value leaves nothing to waive, so it is rejected."""
    rewritten = _effort_manifest("xhigh", "xhigh", "CONTRADICTED", "HUMAN_GRANTED", ORACLE_WAIVER_TEXT)
    assert validator.check_manifest_instance("probe", rewritten)
    truthful = _effort_manifest("xhigh", "high", "CONTRADICTED", "HUMAN_GRANTED", ORACLE_WAIVER_TEXT)
    assert validator.check_manifest_instance("probe", truthful) == []
    assert truthful["model_runtime"]["observed_effort"] == "high"


@pytest.mark.parametrize(
    ("label", "identity", "effort"),
    [
        (
            "model match + effort mismatch",
            ORACLE_CLEAN_IDENTITY,
            ("xhigh", "high", "CONTRADICTED", "NOT_GRANTED", None),
        ),
        (
            "model mismatch + effort match",
            dict(ORACLE_CLEAN_IDENTITY, model_actual="claude-sonnet-5", model_evidence_source="CONTRADICTED"),
            ("high", "high", "RUNTIME_TELEMETRY", "NOT_APPLICABLE", None),
        ),
        (
            "both mismatch",
            dict(ORACLE_CLEAN_IDENTITY, model_actual="claude-sonnet-5", model_evidence_source="CONTRADICTED"),
            ("xhigh", "high", "CONTRADICTED", "NOT_GRANTED", None),
        ),
        (
            "model unknown + effort known",
            dict(ORACLE_CLEAN_IDENTITY, model_actual=None, model_evidence_source="UNKNOWN"),
            ("max", "max", "RUNTIME_TELEMETRY", "NOT_APPLICABLE", None),
        ),
        (
            "model known + effort unknown",
            ORACLE_CLEAN_IDENTITY,
            ("xhigh", None, "UNKNOWN", "NOT_APPLICABLE", None),
        ),
    ],
    ids=[
        "model match + effort mismatch",
        "model mismatch + effort match",
        "both mismatch",
        "model unknown + effort known",
        "model known + effort unknown",
    ],
)
@pytest.mark.parametrize("thinking", ["ENABLED", "DISABLED", "UNKNOWN"])
def test_model_and_effort_stay_dimensionally_independent(
    label: str, identity: dict, effort: tuple, thinking: str
) -> None:
    """R5. Each dimension keeps its own truthful state; thinking is independent of both."""
    requested, observed, source, status, evidence = effort
    manifest = _effort_manifest(requested, observed, source, status, evidence)
    manifest["model_runtime"].update(identity)
    manifest["model_runtime"]["thinking_actual"] = thinking
    assert validator.check_manifest_instance("probe", manifest) == [], label


def test_a_human_effort_waiver_never_repairs_a_model_mismatch() -> None:
    """R4/R6. The identity relation never reads the waiver."""
    manifest = _effort_manifest("xhigh", "high", "CONTRADICTED", "HUMAN_GRANTED", ORACLE_WAIVER_TEXT)
    manifest["model_runtime"].update(model_actual="claude-sonnet-5", model_evidence_source="RUNTIME_TELEMETRY")
    found = validator.check_manifest_instance("probe", manifest)
    assert any("model_actual" in item and "CONTRADICTED" in item for item in found), found


def test_a_human_effort_waiver_never_legitimizes_a_fallback() -> None:
    """R6. An observed fallback stays a model contradiction whatever the effort waiver says."""
    manifest = _effort_manifest("xhigh", "high", "CONTRADICTED", "HUMAN_GRANTED", ORACLE_WAIVER_TEXT)
    manifest["model_runtime"]["model_fallback"] = "fell back to claude-sonnet-5"
    found = validator.check_manifest_instance("probe", manifest)
    assert any("model_fallback" in item for item in found), found


def test_a_waiver_cannot_reach_route_effort_legality(sandbox: Path) -> None:
    """R7. Route effort legality lives in the routing matrix, which the runtime block cannot reach.

    The waiver carries exactly a status and an evidence text - no route, family, intent or effort-set
    field exists for it to override - and the canonical matrix still rejects an illegal family effort.
    """
    assert set(validator.EFFORT_MISMATCH_WAIVER_GRAMMAR["fields"]) == {"status", "evidence"}
    runtime_fields = set(validator.MODEL_RUNTIME_GRAMMAR["fields"])
    for forbidden in ("route", "family", "intent", "lane", "legal"):
        assert not any(forbidden in name for name in runtime_fields), forbidden
    text = read(sandbox, CANONICAL)
    marker = "<!-- ROLE_ROUTING_MATRIX_END -->"
    write(
        sandbox,
        CANONICAL,
        text.replace(marker, "ROUTE: T3C | REVIEW | Claude Opus 5 | claude-opus-5 | max | READ_ONLY\n" + marker, 1),
    )
    assert failures(sandbox), "an illegal family effort was accepted"


def test_the_waiver_block_is_required_and_closed_world() -> None:
    """R8. No omission ambiguity."""
    assert "effort_mismatch_waiver" in validator.MODEL_RUNTIME_GRAMMAR["required"]
    assert tuple(validator.EFFORT_WAIVER_STATUSES) == ORACLE_WAIVER_STATUSES
    for mutate in ("delete", None, [], "NOT_APPLICABLE", {"status": "NOT_APPLICABLE"}, {"evidence": None}):
        manifest = _example_manifest()
        if mutate == "delete":
            manifest["model_runtime"].pop("effort_mismatch_waiver")
        else:
            manifest["model_runtime"]["effort_mismatch_waiver"] = mutate
        assert validator.check_manifest_instance("probe", manifest), mutate


_WAIVER_TOTALITY = [
    (target, shape_label, shape)
    for target in ("effort_mismatch_waiver", "effort_mismatch_waiver.status", "effort_mismatch_waiver.evidence")
    for shape_label, shape in ORACLE_JSON_SHAPES
]


@pytest.mark.parametrize(
    ("target", "shape_label", "shape"),
    _WAIVER_TOTALITY,
    ids=["{} = {}".format(t, s) for t, s, _v in _WAIVER_TOTALITY],
)
def test_no_json_shape_in_the_waiver_can_crash_the_gate(target: str, shape_label: str, shape: object) -> None:
    """R9. The new fields keep RC1's totality: both the public gate and the relation are total."""
    manifest = _effort_manifest("xhigh", "high", "CONTRADICTED", "NOT_GRANTED", None)
    runtime = manifest["model_runtime"]
    if target == "effort_mismatch_waiver":
        runtime["effort_mismatch_waiver"] = shape
    else:
        runtime["effort_mismatch_waiver"][target.split(".", 1)[1]] = shape
    for judge in (validator.check_manifest_instance, validator.manifest_relation_failures):
        assert isinstance(judge("probe", manifest), list)


def test_the_effort_contract_is_documented() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    assert "`EFFORT_RELATION_PROOF`" in canonical
    assert "`EFFORT_MISMATCH_WAIVER`" in canonical
    assert "it does NOT prove that a human actually issued the waiver" in canonical
    assert "it cannot make an ILLEGAL requested effort legal" in canonical


# ===========================================================================================
# STRICT_JSON_EVIDENCE_BOUNDARY
#
# `json.loads` keeps the LAST occurrence of a repeated member name. A compiled manifest repeating
# `head_sha` - an invalid value first, a valid one last - was certified STATE_MANIFEST: PASS; a
# committed schema could hide a duplicate whose last value equalled the generated one; and the setup
# audit reported such workspace JSON valid and counted a server list hidden behind a later duplicate
# as zero. Every expected refusal and acceptance below is written out literally and never derived
# from the validator.
# ===========================================================================================

_STRICT_SCHEMA_REL = "docs/crypto_core/continuity/state_manifest.schema.json"
_STRICT_EXAMPLE_REL = "docs/crypto_core/continuity/state_manifest.example.json"
_STRICT_WORKSPACE_JSON = (".vscode/settings.json", ".vscode/extensions.json", ".vscode/mcp.json")

ORACLE_STRICT_JSON_REFUSALS = [
    (
        "repeated top-level member",
        '{"head_sha":"SHADOW","head_sha":"VALID"}',
        "duplicate object member name 'head_sha'",
    ),
    (
        "repeated nested member",
        '{"model_runtime":{"model_fallback":null,"model_fallback":"x"}}',
        "duplicate object member name 'model_fallback'",
    ),
    ("repeated member of a nested object", '{"outer":{"x":1,"x":2}}', "duplicate object member name 'x'"),
    ("repeated member inside a list object", '{"items":[{"x":1,"x":2}]}', "duplicate object member name 'x'"),
    (
        "repeated member spelled with an escape",
        '{"head_sha":"A","\\u0068ead_sha":"B"}',
        "duplicate object member name 'head_sha'",
    ),
    ("NaN", '{"x": NaN}', "non-finite number NaN is not JSON"),
    ("Infinity", '{"x": Infinity}', "non-finite number Infinity is not JSON"),
    ("-Infinity", '{"x": -Infinity}', "non-finite number -Infinity is not JSON"),
    ("numeral overflowing to infinity", '{"x": 1e999}', "overflows to a non-finite value"),
    ("negative numeral overflowing to infinity", '{"x": -1e999}', "overflows to a non-finite value"),
    ("trailing comma", '{"x": 1,}', "malformed JSON"),
    ("truncated document", '{"x": ', "malformed JSON"),
    ("empty document", "", "malformed JSON"),
    ("nesting too deep to evaluate", "[" * 100000 + "]" * 100000, "nesting is too deep to evaluate"),
]

ORACLE_STRICT_JSON_ACCEPTANCES = [
    ("empty object", "{}", {}),
    ("empty list", "[]", []),
    ("empty containers as members", '{"a": [], "b": {}}', {"a": [], "b": {}}),
    ("one name in sibling objects", '{"a": {"x": 1}, "b": {"x": 2}}', {"a": {"x": 1}, "b": {"x": 2}}),
    ("one name in each object of a list", '[{"x": 1}, {"x": 2}]', [{"x": 1}, {"x": 2}]),
    ("distinct non-ASCII names", '{"\\u015f": 1, "\\u015e": 2}', {"\u015f": 1, "\u015e": 2}),
    ("canonically equivalent but distinct names", '{"\\u00e9": 1, "e\\u0301": 2}', {"\u00e9": 1, "e\u0301": 2}),
    ("large finite numbers", '{"x": 1e308, "y": -1e308, "z": 1e-999}', {"x": 1e308, "y": -1e308, "z": 0.0}),
]

ORACLE_REPEATED_MEMBER_MANIFESTS = [
    ("top-level member", "{", '{"head_sha": "SHADOW",', "'head_sha'"),
    ("nested member", '"model_runtime": {', '"model_runtime": {"model_fallback": "SHADOW",', "'model_fallback'"),
    ("member inside a list object", '"result": "PASS"', '"result": "SHADOW", "result": "PASS"', "'result'"),
    ("member spelled with an escape", "{", '{"\\u0068ead_sha": "SHADOW",', "'head_sha'"),
]


def _strict_example_text() -> str:
    return (REPO_ROOT / _STRICT_EXAMPLE_REL).read_text(encoding="utf-8-sig")


def _repeated_member_manifest(anchor: str, replacement: str) -> str:
    text = _strict_example_text()
    if anchor != "{":
        assert text.count(anchor) == 1, anchor
    return text.replace(anchor, replacement, 1)


def _run_manifest_gate(path: Path, *extra: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [sys.executable, str(VALIDATOR_PATH), "--manifest", str(path), *extra],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        check=False,
        env=env,
    )


def _refused_at(found: list[str], prefix: str, needle: str) -> bool:
    return any(item.startswith(prefix + ": STRICT_JSON_REJECTED: ") and needle in item for item in found)


@pytest.mark.parametrize(
    ("label", "text", "needle"),
    ORACLE_STRICT_JSON_REFUSALS,
    ids=[case[0] for case in ORACLE_STRICT_JSON_REFUSALS],
)
def test_the_strict_json_primitive_refuses_ambiguous_or_non_json_documents(label: str, text: str, needle: str) -> None:
    """J1. One refusal type, a stable condition, and a message that is ASCII and carries no value."""
    with pytest.raises(validator.StrictJsonError) as caught:
        validator.load_strict_json(text)
    message = str(caught.value)
    assert needle in message, message
    assert message.isascii(), message
    assert "SHADOW" not in message


@pytest.mark.parametrize(
    ("label", "text", "expected"),
    ORACLE_STRICT_JSON_ACCEPTANCES,
    ids=[case[0] for case in ORACLE_STRICT_JSON_ACCEPTANCES],
)
def test_the_strict_json_primitive_accepts_unambiguous_json(label: str, text: str, expected: object) -> None:
    """The POSITIVE anchor. Names are compared exactly after decoding - never normalized - so two
    canonically equivalent spellings are two names, while two spellings of one name are one."""
    parsed = validator.load_strict_json(text)
    assert json.dumps(parsed, sort_keys=True) == json.dumps(expected, sort_keys=True)


def test_the_strict_parse_preserves_json_types() -> None:
    """J6. Strict parsing happens before semantic validation and changes no JSON type."""
    parsed = validator.load_strict_json('{"t": true, "f": false, "one": 1, "real": 1.0, "none": null}')
    assert parsed["t"] is True and parsed["f"] is False and parsed["none"] is None
    assert type(parsed["one"]) is int and type(parsed["real"]) is float


@pytest.mark.parametrize(
    ("label", "text", "needle"),
    ORACLE_STRICT_JSON_REFUSALS,
    ids=[case[0] for case in ORACLE_STRICT_JSON_REFUSALS],
)
def test_every_json_entry_point_turns_a_refusal_into_a_verdict(
    sandbox: Path, tmp_path: Path, label: str, text: str, needle: str
) -> None:
    """J2 + J4. The compiled manifest, the committed schema and the committed example all refuse
    the same documents, each as a named failure and never as an exception."""
    manifest = tmp_path / "refused.json"
    manifest.write_text(text, encoding="utf-8")
    assert _refused_at(validator.check_manifest_file(REPO_ROOT, manifest), str(manifest), needle)

    schema = sandbox / _STRICT_SCHEMA_REL
    committed_schema = schema.read_text(encoding="utf-8")
    schema.write_text(text, encoding="utf-8")
    assert _refused_at(failures(sandbox), _STRICT_SCHEMA_REL, needle), failures(sandbox)
    schema.write_text(committed_schema, encoding="utf-8")

    (sandbox / _STRICT_EXAMPLE_REL).write_text(text, encoding="utf-8")
    assert _refused_at(failures(sandbox), _STRICT_EXAMPLE_REL, needle), failures(sandbox)


@pytest.mark.parametrize(
    ("label", "anchor", "replacement", "name"),
    ORACLE_REPEATED_MEMBER_MANIFESTS,
    ids=[case[0] for case in ORACLE_REPEATED_MEMBER_MANIFESTS],
)
def test_a_manifest_repeating_a_member_is_never_certified(
    tmp_path: Path, label: str, anchor: str, replacement: str, name: str
) -> None:
    """J3, the reported reproduction: each of these returned STATE_MANIFEST: PASS with exit 0.

    Plain and --json output are both a deterministic refusal naming the decoded member - never the
    value it carried - and never a traceback.
    """
    path = tmp_path / "repeated.json"
    path.write_text(_repeated_member_manifest(anchor, replacement), encoding="utf-8")
    plain = _run_manifest_gate(path)
    assert plain.returncode == 1, plain.stdout + plain.stderr
    assert "STATE_MANIFEST: PASS" not in plain.stdout
    assert "Traceback" not in plain.stderr, plain.stderr
    assert "{}: STRICT_JSON_REJECTED: duplicate object member name {}".format(path, name) in plain.stdout, plain.stdout
    assert "SHADOW" not in plain.stdout
    assert _run_manifest_gate(path).stdout == plain.stdout, "the refusal must be deterministic"
    report = _run_manifest_gate(path, "--json")
    assert report.returncode == 1, report.stdout + report.stderr
    assert "Traceback" not in report.stderr, report.stderr
    verdict = json.loads(report.stdout)
    assert verdict["ok"] is False
    assert any("duplicate object member name " + name in item for item in verdict["failures"]), verdict


def test_the_manifest_gate_refuses_before_any_grammar_or_relation_reads_the_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """J3. Ambiguity is refused BEFORE evaluation: no last-wins value ever reaches the grammar."""
    path = tmp_path / "repeated.json"
    path.write_text(_repeated_member_manifest("{", '{"head_sha": "SHADOW",'), encoding="utf-8")

    def must_not_run(*_args: object, **_kwargs: object) -> list[str]:
        raise AssertionError("grammar or relations evaluated an ambiguous document")

    for name in ("check_manifest_instance", "manifest_grammar_failures", "manifest_relation_failures"):
        monkeypatch.setattr(validator, name, must_not_run)
    found = validator.check_manifest_file(REPO_ROOT, path)
    assert len(found) == 1 and "STRICT_JSON_REJECTED: duplicate object member name 'head_sha'" in found[0], found


def test_unambiguous_compiled_manifests_still_pass(tmp_path: Path) -> None:
    """The POSITIVE anchor: a strict gate that refuses everything has closed nothing."""
    compact = tmp_path / "compact.json"
    compact.write_text(json.dumps(_example_manifest(), separators=(",", ":")), encoding="utf-8")
    with_bom = tmp_path / "with-bom.json"
    with_bom.write_bytes(b"\xef\xbb\xbf" + _strict_example_text().encode("utf-8"))
    for path in (REPO_ROOT / _STRICT_EXAMPLE_REL, compact, with_bom):
        done = _run_manifest_gate(path)
        assert done.returncode == 0, done.stdout + done.stderr
        assert "STATE_MANIFEST: PASS" in done.stdout, done.stdout


def test_a_committed_schema_duplicate_is_refused_even_when_last_wins_equals_generated(sandbox: Path) -> None:
    """J4. Generated-schema equality must never be proven on an ambiguous committed document."""
    schema = sandbox / _STRICT_SCHEMA_REL
    committed = schema.read_text(encoding="utf-8")
    shadowed = committed.replace("{", '{"$schema": "SHADOW",', 1)
    # The premise: a last-wins parse of the shadowed text IS the committed schema.
    assert json.loads(shadowed) == json.loads(committed)
    schema.write_text(shadowed, encoding="utf-8")
    assert_rejects(sandbox, _STRICT_SCHEMA_REL + ": STRICT_JSON_REJECTED: duplicate object member name '$schema'")


def test_a_committed_example_duplicate_is_refused(sandbox: Path) -> None:
    """J4. The committed fixture is judged by the strict boundary too."""
    example = sandbox / _STRICT_EXAMPLE_REL
    example.write_text(_repeated_member_manifest("{", '{"head_sha": "SHADOW",'), encoding="utf-8")
    assert_rejects(sandbox, _STRICT_EXAMPLE_REL + ": STRICT_JSON_REJECTED: duplicate object member name 'head_sha'")


def test_an_unreadable_manifest_is_a_refusal_not_a_traceback(tmp_path: Path) -> None:
    undecodable = tmp_path / "undecodable.json"
    undecodable.write_bytes(b"\xff\xfe{}")
    for path in (undecodable, tmp_path):
        found = validator.check_manifest_file(REPO_ROOT, path)
        assert len(found) == 1 and "STRICT_JSON_REJECTED: cannot be read as UTF-8 text" in found[0], found


def test_a_refusal_never_echoes_bulk_content() -> None:
    """J5. The offending decoded name is reported bounded, so a huge name cannot flood a diagnostic."""
    name = "n" * 10000
    with pytest.raises(validator.StrictJsonError) as caught:
        validator.load_strict_json('{"' + name + '": 1, "' + name + '": 2}')
    assert len(str(caught.value)) < 200, len(str(caught.value))


def test_a_diagnostic_can_never_crash_on_the_output_encoding(tmp_path: Path) -> None:
    """A non-ASCII member name reached `print` and raised UnicodeEncodeError on a cp1252 stream, so
    the gate ended in a traceback instead of a verdict."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    for label, prefix, needle in (
        ("repeated non-ASCII name", '{"\\u015f": 1, "\\u015f": 2,', "STRICT_JSON_REJECTED"),
        ("unknown non-ASCII field", '{"\\u015f\\u3164": 1,', "unknown field"),
    ):
        path = tmp_path / "encoding.json"
        path.write_text(_strict_example_text().replace("{", prefix, 1), encoding="utf-8")
        done = _run_manifest_gate(path, env=env)
        assert done.returncode == 1, (label, done.stdout, done.stderr)
        assert "Traceback" not in done.stderr, (label, done.stderr)
        assert needle in done.stdout, (label, done.stdout)


def test_every_validator_json_parse_goes_through_the_one_primitive() -> None:
    """J2, by AST. One call site, so a new loader cannot quietly be duplicate-blind."""
    tree = ast.parse(VALIDATOR_PATH.read_text(encoding="utf-8"))

    def parse_calls(node: ast.AST) -> list[ast.Call]:
        return [
            call
            for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in ("loads", "load", "raw_decode", "JSONDecoder")
        ]

    primitive = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "load_strict_json"
    ]
    assert len(primitive) == 1
    everywhere = parse_calls(tree)
    inside = parse_calls(primitive[0])
    assert len(everywhere) == 1 and len(inside) == 1, [ast.dump(call.func) for call in everywhere]
    call = inside[0]
    assert isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Name)
    assert (call.func.value.id, call.func.attr) == ("json", "loads")
    assert {keyword.arg for keyword in call.keywords} == {"object_pairs_hook", "parse_constant", "parse_float"}


def test_the_setup_audit_parses_workspace_json_only_through_the_strict_primitive() -> None:
    """J2. `python -m json.tool` and `json.load` are the duplicate-blind parsers this replaced."""
    body = _audit_source().split("#>", 1)[1]
    code = "\n".join(line for line in body.splitlines() if not line.lstrip().startswith("#"))
    for blind in ("json.tool", "json.load(", "json.loads(", "ConvertFrom-Json"):
        assert blind not in code, blind
    assert code.count("agent_os.load_strict_json_file(") == 2
    # Every python invocation the audit makes goes through the one shared agent_os prelude: the two
    # strict JSON parses and the NON_APPLYING front-matter contract.
    assert code.count("& $python -B -c ($agentOs + ") == 3


def _oracle_strict_parse(text: str) -> object:
    """The oracle's OWN strict parse of a committed artifact - deliberately not the validator's."""

    def members(pairs: list[tuple[str, object]]) -> dict[str, object]:
        names = [name for name, _value in pairs]
        assert len(names) == len(set(names)), "repeated member name among {}".format(sorted(names))
        return dict(pairs)

    def constant(token: str) -> object:
        raise AssertionError("non-finite constant {}".format(token))

    def finite(token: str) -> float:
        value = float(token)
        assert abs(value) != float("inf"), "numeral {} overflows".format(token)
        return value

    return json.loads(text, object_pairs_hook=members, parse_constant=constant, parse_float=finite)


@pytest.mark.parametrize("rel", [_STRICT_SCHEMA_REL, _STRICT_EXAMPLE_REL, *_STRICT_WORKSPACE_JSON])
def test_committed_json_artifacts_are_unambiguous_by_an_independent_parse(rel: str) -> None:
    """J4. The gate is never proven on a duplicate-blind specification fixture."""
    _oracle_strict_parse((REPO_ROOT / rel).read_text(encoding="utf-8-sig"))


def _run_setup_audit_offline(workdir: Path) -> subprocess.CompletedProcess:
    shell = _powershell()
    assert shell
    script = str(REPO_ROOT / "scripts" / "crypto_core" / "audit_agent_setup.ps1")
    return subprocess.run(  # noqa: S603 - repo-local script, locally built argv, no shell
        [
            shell,
            "-NoProfile",
            "-Command",
            "& '{}' -Offline -PythonExe '{}'; exit $LASTEXITCODE".format(script, sys.executable),
        ],
        cwd=str(workdir),
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_refuses_ambiguous_workspace_json(tmp_path: Path) -> None:
    """EXECUTED. Each file below was VALID to `python -m json.tool`, and the MCP file counted zero
    servers because its later, empty duplicate hid the first. The strict import must also leave no
    bytecode behind."""
    planted = tmp_path / "scripts" / "crypto_core" / "validate_agent_os_v2.py"
    planted.parent.mkdir(parents=True)
    shutil.copyfile(VALIDATOR_PATH, planted)
    workspace = tmp_path / ".vscode"
    workspace.mkdir()
    (workspace / "settings.json").write_text('{"editor.tabSize": 4, "editor.tabSize": 2}', encoding="utf-8")
    (workspace / "extensions.json").write_text('{"recommendations": [], "weight": NaN}', encoding="utf-8")
    (workspace / "mcp.json").write_text(
        '{"servers": {"shadow": {"command": "shadow"}}, "servers": {}}', encoding="utf-8"
    )
    done = _run_setup_audit_offline(tmp_path)
    for rel in _STRICT_WORKSPACE_JSON:
        assert "{} : INVALID JSON".format(rel) in done.stdout, done.stdout
    assert "MCP_SERVER_COUNT=UNPARSEABLE" in done.stdout, done.stdout
    assert "OPEN_PR_COUNT=UNKNOWN (offline run" in done.stdout, done.stdout
    assert done.returncode != 0, done.stdout + done.stderr
    assert not (planted.parent / "__pycache__").exists(), "the strict import wrote bytecode"


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
def test_setup_audit_still_passes_on_the_committed_workspace_json() -> None:
    """The POSITIVE anchor, from the real repository and offline."""
    done = _run_setup_audit_offline(REPO_ROOT)
    for rel in _STRICT_WORKSPACE_JSON:
        assert "{} : VALID JSON".format(rel) in done.stdout, done.stdout
    assert "MCP_SERVER_COUNT=0" in done.stdout, done.stdout
    assert done.returncode == 0, done.stdout + done.stderr


# ===========================================================================================
# CLOSED_WORLD_CONTROL_PLANE_BINDING
#
# A field with a valid shape proved nothing when no relation bound it to what it claimed to be
# evidence OF: execution proof with no target, a proven tree with no proven commit, a workflow run
# attributed to another head, and a host root no scan covered. Every expected verdict below is
# written out literally and never derived from the validator.
# ===========================================================================================

ORACLE_PROVING_EVIDENCE = ("RUNTIME_TELEMETRY", "USER_ATTESTED_UI_SELECTION")
ORACLE_ALL_EVIDENCE = ORACLE_PROVING_EVIDENCE + ("CONFIGURATION_EVIDENCE_ONLY", "UNKNOWN", "CONTRADICTED")
ORACLE_IDENTITY_TARGETS = {
    "absent": {"model_id": None, "model_requested": None},
    "api identity": {"model_id": "claude-opus-5", "model_requested": "claude-opus-5"},
    "requested only": {"model_id": None, "model_requested": "claude-opus-5"},
    "filler": {"model_id": "   ", "model_requested": None},
}
ORACLE_IDENTITY_OBSERVATIONS = {"absent": None, "match": "claude-opus-5", "mismatch": "gpt-6-astra", "filler": "   "}
ORACLE_EFFORT_TARGETS = {"absent": None, "present": "xhigh", "outside the enum": "ultra"}
ORACLE_EFFORT_OBSERVATIONS = {"absent": None, "match": "xhigh", "mismatch": "high", "outside the enum": "ultra"}


def _oracle_target_bound_verdict(evidence: str, target_valid: bool, target_malformed: bool, observation: str) -> bool:
    """The literal contract. True means the manifest must be accepted."""
    if target_malformed or observation in ("filler", "outside the enum"):
        return False
    if evidence in ORACLE_PROVING_EVIDENCE:
        return target_valid and observation == "match"
    if evidence == "CONTRADICTED":
        return target_valid and observation == "mismatch"
    return observation == "absent"


_IDENTITY_TARGET_CASES = [
    (evidence, target, observation)
    for evidence in ORACLE_ALL_EVIDENCE
    for target in ORACLE_IDENTITY_TARGETS
    for observation in ORACLE_IDENTITY_OBSERVATIONS
]


@pytest.mark.parametrize(
    ("evidence", "target", "observation"),
    _IDENTITY_TARGET_CASES,
    ids=["{} / target {} / observation {}".format(*case) for case in _IDENTITY_TARGET_CASES],
)
def test_identity_execution_proof_needs_a_target(evidence: str, target: str, observation: str) -> None:
    """F1. Telemetry or an attestation with neither model_id nor model_requested was accepted, and so
    was CONTRADICTED: each claimed a comparison with nothing to compare against."""
    manifest = _runtime(
        model_actual=ORACLE_IDENTITY_OBSERVATIONS[observation],
        model_evidence_source=evidence,
        model_fallback=None,
        **ORACLE_IDENTITY_TARGETS[target],
    )
    found = validator.check_manifest_instance("probe", manifest)
    expected = _oracle_target_bound_verdict(
        evidence, target in ("api identity", "requested only"), target == "filler", observation
    )
    assert (not found) is expected, found


_EFFORT_TARGET_CASES = [
    (evidence, target, observation)
    for evidence in ORACLE_ALL_EVIDENCE
    for target in ORACLE_EFFORT_TARGETS
    for observation in ORACLE_EFFORT_OBSERVATIONS
]


@pytest.mark.parametrize(
    ("evidence", "target", "observation"),
    _EFFORT_TARGET_CASES,
    ids=["{} / target {} / observation {}".format(*case) for case in _EFFORT_TARGET_CASES],
)
def test_effort_execution_proof_needs_a_target(evidence: str, target: str, observation: str) -> None:
    """F1. Telemetry reporting an observed effort with no requested effort was accepted."""
    contradicted_mismatch = evidence == "CONTRADICTED" and target == "present" and observation == "mismatch"
    manifest = _runtime(
        requested_effort=ORACLE_EFFORT_TARGETS[target],
        observed_effort=ORACLE_EFFORT_OBSERVATIONS[observation],
        effort_evidence_source=evidence,
        effort_mismatch_waiver={
            "status": "NOT_GRANTED" if contradicted_mismatch else "NOT_APPLICABLE",
            "evidence": None,
        },
    )
    found = validator.check_manifest_instance("probe", manifest)
    expected = _oracle_target_bound_verdict(evidence, target == "present", target == "outside the enum", observation)
    assert (not found) is expected, found


def test_a_human_waiver_never_manufactures_an_effort_target() -> None:
    manifest = _runtime(
        requested_effort=None,
        observed_effort="high",
        effort_evidence_source="CONTRADICTED",
        effort_mismatch_waiver={
            "status": "HUMAN_GRANTED",
            "evidence": "Human waived the observed high effort for this task",
        },
    )
    assert validator.check_manifest_instance("probe", manifest)


ORACLE_TARGET_DEPENDENT_FIELDS = [
    ("base_tree", "base_sha"),
    ("head_tree", "head_sha"),
    ("pr_state", "pr_number"),
    ("review_threads_unresolved", "pr_number"),
    ("ci_state", "head_sha"),
    ("completed_gates", "head_sha"),
]


def _target_manifest(field: str, target: str, target_proven: bool) -> dict:
    manifest = _example_manifest()
    manifest.update(
        pr_number=7,
        pr_number_evidence="PROVEN",
        pr_state="CLOSED",
        pr_state_evidence="PROVEN",
        review_threads_unresolved=0,
        review_threads_unresolved_evidence="PROVEN",
    )
    if not target_proven:
        for dependent, dependent_target in ORACLE_TARGET_DEPENDENT_FIELDS:
            if dependent_target == target and dependent != field:
                manifest.update({dependent: None, dependent + "_evidence": "UNKNOWN"})
        manifest.update({target: None, target + "_evidence": "UNKNOWN"})
    return manifest


@pytest.mark.parametrize(
    ("field", "target"),
    ORACLE_TARGET_DEPENDENT_FIELDS,
    ids=["{} needs {}".format(*case) for case in ORACLE_TARGET_DEPENDENT_FIELDS],
)
def test_a_proven_observation_needs_its_proven_target(field: str, target: str) -> None:
    """A PROVEN tree without its commit, or a PROVEN thread count without its pull request, passed."""
    assert validator.check_manifest_instance("probe", _target_manifest(field, target, True)) == []
    found = validator.check_manifest_instance("probe", _target_manifest(field, target, False))
    assert any("{} is PROVEN but its target {} is not".format(field, target) in item for item in found), found


_GATE_KEY_CASES = [
    ("the proven head", lambda m: "head={}|paths=p|cmd=c|env=e|id=1".format(m["head_sha"]), True),
    ("the proven tree", lambda m: "tree={}|paths=p|cmd=c|env=e|id=1".format(m["head_tree"]), True),
    ("the proven head in upper case", lambda m: "head={}|id=1".format(m["head_sha"].upper()), True),
    ("the proven head beside a stale one", lambda m: "head={}|was={}".format(m["head_sha"], "c" * 40), True),
    ("only a stale head", lambda m: "head={}|paths=p".format("c" * 40), False),
    ("no revision at all", lambda m: "paths=p|cmd=c|env=e|id=1", False),
    ("the proven head inside a longer hex run", lambda m: "head={}ab|id=1".format(m["head_sha"]), False),
]


@pytest.mark.parametrize(
    ("label", "build", "accepted"),
    _GATE_KEY_CASES,
    ids=[case[0] for case in _GATE_KEY_CASES],
)
def test_a_completed_gate_is_bound_to_the_proven_revision(label: str, build: object, accepted: bool) -> None:
    """VALIDATION_BUDGET: a gate proven at another revision is invalidated, never completed here."""
    manifest = _example_manifest()
    manifest["completed_gates"] = [dict(manifest["completed_gates"][0], evidence_key=build(manifest))]  # type: ignore[operator]
    found = validator.check_manifest_instance("probe", manifest)
    assert (not found) is accepted, found


_OPEN_SET_CASES = [
    ("OPEN", 0, False),
    ("DRAFT", 0, False),
    ("OPEN", 1, True),
    ("DRAFT", 2, True),
    ("CLOSED", 0, True),
    ("MERGED", 0, True),
]


@pytest.mark.parametrize(
    ("state", "count", "accepted"),
    _OPEN_SET_CASES,
    ids=["{} with {} open".format(state, count) for state, count, _a in _OPEN_SET_CASES],
)
def test_a_proven_open_pull_request_is_a_member_of_the_open_set(state: str, count: int, accepted: bool) -> None:
    manifest = _example_manifest()
    manifest.update(
        pr_number=7,
        pr_number_evidence="PROVEN",
        pr_state=state,
        pr_state_evidence="PROVEN",
        open_pr_count=count,
        open_pr_count_evidence="PROVEN",
    )
    found = validator.check_manifest_instance("probe", manifest)
    assert (not found) is accepted, found


def test_proof_target_registry_matches_the_oracle() -> None:
    rows = validator.parse_surface_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "PROOF_TARGET_BINDINGS"
    )
    assert rows is not None
    assert dict(rows) == ORACLE_PROOF_TARGET_BINDINGS
    assert set(ORACLE_PROOF_TARGET_BINDINGS) == set(ORACLE_PROOF_PAIRED_FIELD_NAMES)


_TARGET_REGISTRY_MUTATIONS = [
    (
        "a proof field that declares no target",
        "- ci_state :: head_sha\n",
        "",
        "proof-paired field ci_state declares no target",
    ),
    (
        "a target that is not an identity",
        "- head_tree :: head_sha\n",
        "- head_tree :: ci_state\n",
        "head_tree is bound to 'ci_state', which is not a proof-paired identity",
    ),
    (
        "a binding for a field that is not proof-paired",
        "- next_safe_action :: NONE\n",
        "- next_safe_action :: NONE\n- task_boundary :: NONE\n",
        "binds task_boundary, which is not proof-paired",
    ),
    (
        "a registry that drifts from the executable relation",
        "- ci_state :: head_sha\n",
        "- ci_state :: NONE\n",
        "does not equal the executable proof-target bindings",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new", "needle"),
    _TARGET_REGISTRY_MUTATIONS,
    ids=[case[0] for case in _TARGET_REGISTRY_MUTATIONS],
)
def test_the_proof_target_registry_is_closed_and_executable(
    sandbox: Path, label: str, old: str, new: str, needle: str
) -> None:
    canonical = sandbox / CANONICAL
    text = canonical.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    canonical.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    assert_rejects(sandbox, needle)


def test_host_registries_match_the_oracle() -> None:
    text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert (
        dict(validator.parse_surface_registry(text, "HISTORICAL_HOST_SURFACES") or [])
        == ORACLE_HISTORICAL_HOST_SURFACES
    )
    assert validator.parse_registry(text, "HOST_NON_DISCOVERY_PATHS") == ORACLE_HOST_NON_DISCOVERY_PATHS


def test_a_rogue_always_applied_instruction_file_is_rejected(sandbox: Path) -> None:
    """F3, the reported reproduction: this file left the control plane PASS on the prior bytes."""
    target = sandbox / ".github/instructions/rogue.instructions.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        '---\napplyTo: "**"\n---\nCompeting always-applied instruction surface.\n', encoding="utf-8", newline="\n"
    )
    assert_rejects(
        sandbox, "host auto-discovery surface present but not registered: .github/instructions/rogue.instructions.md"
    )


@pytest.mark.parametrize("rel", ["docs/crypto_core/rogue-notes.md", ".github/hooks/rogue.json"])
def test_a_file_outside_every_discovery_location_is_not_a_false_positive(sandbox: Path, rel: str) -> None:
    target = sandbox / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("not a host surface\n", encoding="utf-8", newline="\n")
    assert failures(sandbox) == []


def test_a_restored_retired_instruction_file_is_rejected(sandbox: Path) -> None:
    target = sandbox / ".github/instructions/system.instructions.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("# restored\n", encoding="utf-8", newline="\n")
    assert_rejects(
        sandbox, "retired control-plane path still present in the tree: .github/instructions/system.instructions.md"
    )


_ORACLE_HISTORICAL_RULE = ".cursor/rules/prdv3-constitution.mdc"


@pytest.mark.parametrize(
    ("label", "content", "needle"),
    [
        (
            "declares alwaysApply true",
            "---\ndescription: historical\nalwaysApply: true\n---\nbody\n",
            "declares alwaysApply: true",
        ),
        (
            "never closes its front matter",
            "---\ndescription: historical\nalwaysApply: false\n",
            "front matter never closes",
        ),
    ],
    ids=["declares alwaysApply true", "never closes its front matter"],
)
def test_a_historical_host_rule_that_could_apply_is_rejected(
    sandbox: Path, label: str, content: str, needle: str
) -> None:
    target = sandbox / _ORACLE_HISTORICAL_RULE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    assert_rejects(sandbox, needle)


def test_the_non_applying_historical_host_rule_is_accepted(sandbox: Path) -> None:
    """The POSITIVE anchor: the real historical rule, exactly as committed, passes."""
    target = sandbox / _ORACLE_HISTORICAL_RULE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / _ORACLE_HISTORICAL_RULE, target)
    assert failures(sandbox) == []


_HOST_CLOSURE_MUTATIONS = [
    (
        "a known host root left unscanned",
        "- .github/instructions/**/*.instructions.md\n",
        "",
        "lies in no declared discovery location and is not declared in HOST_NON_DISCOVERY_PATHS",
    ),
    (
        "a non-discovery declaration removed",
        "- .github/hooks/hook-engine.md\n- .github/skills/_shared/references/contract-schema.md\n<!-- HOST_NON_DISCOVERY_PATHS_END -->",
        "- .github/skills/_shared/references/contract-schema.md\n<!-- HOST_NON_DISCOVERY_PATHS_END -->",
        ".github/hooks/hook-engine.md is named by a registry inside host directory .github/",
    ),
    (
        "a discoverable path declared non-discoverable",
        "<!-- HOST_NON_DISCOVERY_PATHS_BEGIN -->\n",
        "<!-- HOST_NON_DISCOVERY_PATHS_BEGIN -->\n- .github/prompts/forensic-debug.prompt.md\n",
        "is declared in HOST_NON_DISCOVERY_PATHS but lies in the discovery location",
    ),
    (
        "a declaration no registry names",
        "<!-- HOST_NON_DISCOVERY_PATHS_BEGIN -->\n",
        "<!-- HOST_NON_DISCOVERY_PATHS_BEGIN -->\n- .github/hooks/pre-response.json\n",
        "declares .github/hooks/pre-response.json, which no registry names",
    ),
    (
        "a historical surface outside every discovery location",
        "- .cursor/rules/prdv3-constitution.mdc :: NON_APPLYING\n",
        "- .cursor/rules/prdv3-constitution.mdc :: NON_APPLYING\n- docs/crypto_core/legacy.md :: NON_APPLYING\n",
        "historical host surface docs/crypto_core/legacy.md lies in no declared discovery location",
    ),
    (
        "a historical surface in an unknown role",
        "- .cursor/rules/prdv3-constitution.mdc :: NON_APPLYING\n",
        "- .cursor/rules/prdv3-constitution.mdc :: ADVISORY\n",
        "carries role 'ADVISORY'",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new", "needle"),
    _HOST_CLOSURE_MUTATIONS,
    ids=[case[0] for case in _HOST_CLOSURE_MUTATIONS],
)
def test_host_discovery_is_closed_in_both_directions(
    sandbox: Path, label: str, old: str, new: str, needle: str
) -> None:
    canonical = sandbox / CANONICAL
    text = canonical.read_text(encoding="utf-8")
    assert text.count(old) == 1, old
    canonical.write_text(text.replace(old, new), encoding="utf-8", newline="\n")
    assert_rejects(sandbox, needle)


ORACLE_GLOB_MATCHES = [
    (".github/prompts/**/*.prompt.md", ".github/prompts/a.prompt.md", True),
    (".github/prompts/**/*.prompt.md", ".github/prompts/deep/er/a.prompt.md", True),
    (".github/prompts/**/*.prompt.md", ".github/promptsx/a.prompt.md", False),
    (".github/prompts/**/*.prompt.md", ".github/prompts/a.prompt.mdx", False),
    (".claude/skills/**/SKILL.md", ".claude/skills/one/SKILL.md", True),
    (".claude/skills/**/SKILL.md", ".claude/skills/SKILL.md", True),
    (".claude/skills/**/SKILL.md", ".claude/skillsSKILL.md", False),
    (".github/copilot-instructions.md", ".github/copilot-instructions.md", True),
    (".github/copilot-instructions.md", ".github/copilot-instructionsXmd", False),
    (".cursor/rules/**/*.mdc", ".cursor/rules/a/b.mdc", True),
    (".github/skills/**/SKILL.md", ".github/skills/_shared/references/contract-schema.md", False),
]


@pytest.mark.parametrize(
    ("pattern", "path", "matches"),
    ORACLE_GLOB_MATCHES,
    ids=["{} vs {}".format(pattern, path) for pattern, path, _m in ORACLE_GLOB_MATCHES],
)
def test_registry_classification_uses_the_scan_glob_meaning(
    tmp_path: Path, pattern: str, path: str, matches: bool
) -> None:
    """Registry paths are classified by regex and files by pathlib glob; the two must never disagree."""
    assert bool(validator.host_glob_regex(pattern).match(path)) is matches
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")
    found = {p.relative_to(tmp_path).as_posix() for p in tmp_path.glob(pattern) if p.is_file()}
    assert (path in found) is matches


_ORACLE_OTHER_REVISION = "5" * 40
ORACLE_PROVENANCE_MUTATIONS = [
    ("valid pull_request bundle", {}, True),
    ("run attributed to another head", {"run_reported_head": _ORACLE_OTHER_REVISION}, False),
    ("run attributed to the base", {"run_reported_head": _ORACLE_BASE}, False),
    ("run attributed to the synthetic merge", {"run_reported_head": _ORACLE_MERGE}, False),
    ("checkout is the audited head", {"actual_checkout_revision": _ORACLE_HEAD}, False),
    ("checkout is the base", {"actual_checkout_revision": _ORACLE_BASE}, False),
    (
        "base equals the audited head",
        {"current_base": _ORACLE_HEAD, "tested_revision_parents": [_ORACLE_HEAD, _ORACLE_HEAD]},
        False,
    ),
    ("wrong base", {"current_base": _ORACLE_OTHER_REVISION}, False),
    ("wrong audited head", {"audited_pr_head": _ORACLE_OTHER_REVISION}, False),
    ("parents in the wrong order", {"tested_revision_parents": [_ORACLE_HEAD, _ORACLE_BASE]}, False),
    ("wrong tested tree", {"tested_revision_tree": _ORACLE_OTHER_REVISION}, False),
    ("wrong audited tree", {"audited_head_tree": _ORACLE_OTHER_REVISION}, False),
    ("run id zero", {"workflow_run_id": 0}, False),
    ("run id boolean", {"workflow_run_id": True}, False),
    ("run id text", {"workflow_run_id": "1"}, False),
    ("sibling workflow", {"workflow_path": ".github/workflows/other.yml"}, False),
    ("no required contexts", {"required_contexts": []}, False),
    ("required contexts without tests", {"required_contexts": ["codeql", "CodeQL"]}, False),
    ("required contexts naming tests among others", {"required_contexts": ["codeql", "tests", "CodeQL"]}, True),
    (
        "a gate step failed",
        {
            "agent_os_gate_step_conclusions": {
                "Agent OS control-plane contract": "failure",
                "Agent OS contract oracle anchor": "success",
            }
        },
        False,
    ),
    ("checkout override true", {"checkout_ref_override": True}, False),
    ("checkout override text", {"checkout_ref_override": "false"}, False),
    ("push bundle", {"event": "push", "actual_checkout_revision": _ORACLE_HEAD, "tested_revision_parents": []}, True),
    (
        "push run attributed to another head",
        {
            "event": "push",
            "actual_checkout_revision": _ORACLE_HEAD,
            "tested_revision_parents": [],
            "run_reported_head": _ORACLE_OTHER_REVISION,
        },
        False,
    ),
    (
        "push checkout is another revision",
        {"event": "push", "actual_checkout_revision": _ORACLE_OTHER_REVISION, "tested_revision_parents": []},
        False,
    ),
    ("unsupported event merge_group", {"event": "merge_group"}, False),
    ("unsupported event pull_request_target", {"event": "pull_request_target"}, False),
    ("unsupported event workflow_dispatch", {"event": "workflow_dispatch"}, False),
    ("unsupported event schedule", {"event": "schedule"}, False),
]


@pytest.mark.parametrize(
    ("label", "overrides", "accepted"),
    ORACLE_PROVENANCE_MUTATIONS,
    ids=[case[0] for case in ORACLE_PROVENANCE_MUTATIONS],
)
def test_the_tested_revision_is_a_complete_identity_graph(label: str, overrides: dict, accepted: bool) -> None:
    """F2. Changing only run_reported_head to another valid revision left a real bundle accepted."""
    result = validator.tested_revision_failures(_revision_evidence(**overrides))
    assert (not result) is accepted, "{}: {}".format(label, result)


_PROVENANCE_TOTALITY_CASES = [
    (field, label, shape)
    for field in ("run_reported_head", "actual_checkout_revision", "current_base", "required_contexts", "event")
    for label, shape in ORACLE_JSON_SHAPES
]


@pytest.mark.parametrize(
    ("field", "shape_label", "shape"),
    _PROVENANCE_TOTALITY_CASES,
    ids=["{} = {}".format(f, s) for f, s, _v in _PROVENANCE_TOTALITY_CASES],
)
def test_no_json_shape_can_crash_the_run_head_binding(field: str, shape_label: str, shape: object) -> None:
    result = validator.tested_revision_failures(_revision_evidence(**{field: shape}))
    assert isinstance(result, list)


ORACLE_BINDING_INPUT_FIELDS = (
    "base_sha_evidence",
    "base_tree_evidence",
    "head_sha_evidence",
    "head_tree",
    "head_tree_evidence",
    "pr_number_evidence",
    "pr_state",
    "pr_state_evidence",
    "open_pr_count",
    "open_pr_count_evidence",
    "review_threads_unresolved_evidence",
    "ci_state_evidence",
    "completed_gates",
    "completed_gates_evidence",
)
_BINDING_TOTALITY_CASES = (
    [(field, label, shape) for field in ORACLE_BINDING_INPUT_FIELDS for label, shape in ORACLE_JSON_SHAPES]
    + [("completed_gates[0]", label, shape) for label, shape in ORACLE_JSON_SHAPES]
    + [("completed_gates[0].evidence_key", label, shape) for label, shape in ORACLE_JSON_SHAPES]
)


@pytest.mark.parametrize(
    ("field", "shape_label", "shape"),
    _BINDING_TOTALITY_CASES,
    ids=["{} = {}".format(f, s) for f, s, _v in _BINDING_TOTALITY_CASES],
)
def test_no_json_shape_can_crash_the_binding_relations(field: str, shape_label: str, shape: object) -> None:
    manifest = _example_manifest()
    if field == "completed_gates[0]":
        manifest["completed_gates"] = [shape]
    elif field == "completed_gates[0].evidence_key":
        manifest["completed_gates"] = [dict(manifest["completed_gates"][0], evidence_key=shape)]
    else:
        manifest[field] = shape
    for judge in (validator.check_manifest_instance, validator.manifest_relation_failures):
        assert isinstance(judge("probe", manifest), list)


def test_the_closed_world_binding_is_documented() -> None:
    text = _normalized(REPO_ROOT / CANONICAL)
    for token in (
        "TARGET_BOUND_EXECUTION_PROOF",
        "PROOF_TARGET_BINDINGS",
        "RUN_HEAD_BINDING",
        "HOST_DISCOVERY_CLOSED_WORLD",
        "HISTORICAL_HOST_SURFACES",
        "HOST_NON_DISCOVERY_PATHS",
    ):
        assert token in text, token
    assert "it must equal `audited_pr_head` for every accepted event" in text
    assert "`required_contexts` must include `tests`" in text
    assert "currently EMPTY" not in text


# ===========================================================================================
# ACTIVE_CONTROL_PLANE_SURFACE_SEMANTICS
#
# The scans treated HISTORICAL_RECORD and EXAMPLE_ONLY as exempt while every authority reader parsed the
# whole file, so a block, a declaration, a role marker or a required token wrapped in a region kept
# satisfying the contract while escaping every scan. NON_APPLYING was granted by the absence of one unsafe
# spelling. Every expected verdict below is written out literally and never derived from the validator.
# ===========================================================================================

ORACLE_EXEMPTION_REGION_TYPES = ("HISTORICAL_RECORD", "EXAMPLE_ONLY")
ORACLE_CANONICAL_AUTHORITY_BLOCKS = [
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
    "HOST_EXECUTABLE_WORKFLOWS",
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
]

# What each authority READER reports when its block is absent from the active projection. A reader that
# drifted back to the whole text would find the exempt copy and go quiet, so every needle is load-bearing.
ORACLE_ACTIVE_READER_NEEDLES = {
    "ROLE_ROUTING_MATRIX": ("ROLE_ROUTING_MATRIX block missing or malformed", "which T3B does not route in section 3"),
    "FAMILY_SEMANTIC_CONTRACT": ("FAMILY_SEMANTIC_CONTRACT block missing or malformed",),
    "LANE_CAPABILITY": ("LANE_CAPABILITY block missing or malformed",),
    "REASONING_EFFORT_ENUM": ("REASONING_EFFORT_ENUM block missing or malformed",),
    "INDEPENDENCE_VOCABULARY": (),
    "INTENT_FIRST_ROUTING": ("INTENT_FIRST_ROUTING block missing or malformed",),
    "MODEL_EVIDENCE_CLASSES": ("MODEL_EVIDENCE_CLASSES block missing or malformed",),
    "PROMPT_COMPILER_V2_1_FIELDS": (
        "PROMPT_COMPILER_V2_1_FIELDS block missing or malformed",
        "exactly one top-level prompt-compiler field block must exist",
    ),
    "WORK_RETURN_CONTRACT": ("WORK_RETURN_CONTRACT block missing or malformed",),
    "PROVIDER_CAPACITY_STATES": (
        "PROVIDER_CAPACITY_STATES block missing or malformed",
        "provider capacity must admit UNKNOWN",
    ),
    "CAPACITY_ROUTING_MODES": (
        "CAPACITY_ROUTING_MODES block missing or malformed",
        "capacity routing mode missing: CLAUDE_CONTINUITY",
    ),
    "TESTED_REVISION_EVIDENCE": (),
    "HOST_DISCOVERY_SCAN_PATHS": ("HOST_DISCOVERY_SCAN_PATHS block missing or malformed",),
    "HISTORICAL_HOST_SURFACES": ("HISTORICAL_HOST_SURFACES block missing or malformed",),
    "HOST_NON_DISCOVERY_PATHS": ("HOST_NON_DISCOVERY_PATHS block missing or malformed",),
    "HOST_EXECUTABLE_WORKFLOWS": ("HOST_EXECUTABLE_WORKFLOWS block missing or malformed",),
    "ACTIVE_DOCTRINE_SURFACES": ("ACTIVE_DOCTRINE_SURFACES block missing or malformed",),
    "REQUIRED_CONTROL_PLANE_ARTIFACTS": ("REQUIRED_CONTROL_PLANE_ARTIFACTS block missing or malformed",),
    "DURABLE_SURFACES": ("DURABLE_SURFACES block missing or malformed",),
    "MODEL_AGNOSTIC_SURFACES": ("MODEL_AGNOSTIC_SURFACES block missing or malformed",),
    "VOLATILE_STATE_FIELDS": ("VOLATILE_STATE_FIELDS block missing or malformed",),
    "MAX_EFFORT_FAMILY_TRIGGERS": ("MAX_EFFORT_FAMILY_TRIGGERS block missing or malformed",),
    "PROOF_PAIRED_MANIFEST_FIELDS": ("PROOF_PAIRED_MANIFEST_FIELDS block missing or malformed",),
    "PROOF_TARGET_BINDINGS": ("PROOF_TARGET_BINDINGS block missing or malformed",),
    "RETIRED_CONTROL_PLANE_PATHS": ("RETIRED_CONTROL_PLANE_PATHS block missing or malformed",),
    "EXECUTABLE_NEGATIVE_BOUNDARY": ("EXECUTABLE_NEGATIVE_BOUNDARY must declare exactly one boundary sentence",),
}


def _authority_bounds(text: str, name: str) -> tuple[int, int]:
    lines = text.split("\n")
    begins = [index for index, line in enumerate(lines) if line == "<!-- {}_BEGIN -->".format(name)]
    ends = [index for index, line in enumerate(lines) if line == "<!-- {}_END -->".format(name)]
    assert len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0], name
    return begins[0], ends[0]


def _wrap_lines(text: str, first: int, last: int, region: str) -> str:
    lines = text.split("\n")
    return "\n".join(
        lines[:first]
        + ["<!-- {}_BEGIN -->".format(region)]
        + lines[first : last + 1]
        + ["<!-- {}_END -->".format(region)]
        + lines[last + 1 :]
    )


def test_every_canonical_block_is_an_inventoried_authority_block() -> None:
    text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    discovered = [
        match.group(1)
        for match in re.finditer(r"(?m)^<!-- ([A-Z0-9_]+)_BEGIN -->$", text)
        if match.group(1) not in ORACLE_EXEMPTION_REGION_TYPES
    ]
    assert discovered == ORACLE_CANONICAL_AUTHORITY_BLOCKS
    assert list(validator.CANONICAL_AUTHORITY_BLOCKS) == ORACLE_CANONICAL_AUTHORITY_BLOCKS
    assert tuple(validator.EXEMPT_REGION_BLOCKS) == ORACLE_EXEMPTION_REGION_TYPES
    assert set(ORACLE_ACTIVE_READER_NEEDLES) == set(ORACLE_CANONICAL_AUTHORITY_BLOCKS)


def test_an_undeclared_canonical_block_is_rejected(sandbox: Path) -> None:
    """The inventory is closed: a block nothing requires is undeclared authority, never a silent addition."""
    text = read(sandbox, CANONICAL)
    anchor = "<!-- HISTORICAL_RECORD_BEGIN -->"
    assert text.count(anchor) == 1
    shadow = "<!-- SHADOW_ROUTING_BEGIN -->\n- T4 :: Claude Opus 5\n<!-- SHADOW_ROUTING_END -->\n\n"
    write(sandbox, CANONICAL, text.replace(anchor, shadow + anchor))
    assert_rejects(sandbox, "SHADOW_ROUTING is not a declared canonical authority block")


_AUTHORITY_REGION_CASES = [
    (name, region) for name in ORACLE_CANONICAL_AUTHORITY_BLOCKS for region in ORACLE_EXEMPTION_REGION_TYPES
]


@pytest.mark.parametrize(
    ("name", "region"),
    _AUTHORITY_REGION_CASES,
    ids=["{} inside {}".format(*case) for case in _AUTHORITY_REGION_CASES],
)
def test_an_exempted_authority_block_never_satisfies_active_authority(sandbox: Path, name: str, region: str) -> None:
    """F-A, the reported reproduction: the ONLY copy of a block inside a region left the control plane PASS."""
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, name)
    write(sandbox, CANONICAL, _wrap_lines(text, first, last, region))
    joined = "\n".join(failures(sandbox))
    assert "MISSING_ACTIVE_AUTHORITY: {} ".format(name) in joined, joined
    assert "a control-plane block marker inside the {} region".format(region) in joined, joined
    for needle in ORACLE_ACTIVE_READER_NEEDLES[name]:
        assert needle in joined, "{} was read from inactive content: {}".format(name, joined)


@pytest.mark.parametrize(
    ("name", "region"),
    _AUTHORITY_REGION_CASES,
    ids=["{} copy inside {}".format(*case) for case in _AUTHORITY_REGION_CASES],
)
def test_an_exempt_copy_beside_the_active_block_fails_only_as_reserved_syntax(
    sandbox: Path, name: str, region: str
) -> None:
    """No reader ever sees the exempt copy: the ONLY failures are the reserved-syntax ones."""
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, name)
    copy = "\n".join(text.split("\n")[first : last + 1])
    write(
        sandbox, CANONICAL, text.rstrip("\n") + "\n\n<!-- {0}_BEGIN -->\n{1}\n<!-- {0}_END -->\n".format(region, copy)
    )
    found = failures(sandbox)
    assert found, "an exempt copy of {} was accepted".format(name)
    reserved = "inside the {} region".format(region)
    assert all(reserved in item and "authority syntax is reserved" in item for item in found), found


@pytest.mark.parametrize(
    ("name", "region"),
    _AUTHORITY_REGION_CASES,
    ids=["{} body inside {}".format(*case) for case in _AUTHORITY_REGION_CASES],
)
def test_an_exemption_inside_an_active_authority_block_is_rejected(sandbox: Path, name: str, region: str) -> None:
    """Markers active, body wrapped: no region may remove part of a block from the active projection."""
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, name)
    write(sandbox, CANONICAL, _wrap_lines(text, first + 1, last - 1, region))
    assert_rejects(sandbox, "exemption marker inside the active authority block {} opened at".format(name))


_AUTHORITY_MARKER_CASES = [
    (name, region, side)
    for name in ORACLE_CANONICAL_AUTHORITY_BLOCKS
    for region in ORACLE_EXEMPTION_REGION_TYPES
    for side in ("BEGIN", "END")
]


@pytest.mark.parametrize(
    ("name", "region", "side"),
    _AUTHORITY_MARKER_CASES,
    ids=["{} {} marker inside {}".format(name, side, region) for name, region, side in _AUTHORITY_MARKER_CASES],
)
def test_one_exempted_block_marker_leaves_the_block_missing(sandbox: Path, name: str, region: str, side: str) -> None:
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, name)
    line = first if side == "BEGIN" else last
    write(sandbox, CANONICAL, _wrap_lines(text, line, line, region))
    joined = "\n".join(failures(sandbox))
    assert "MISSING_ACTIVE_AUTHORITY: {} ".format(name) in joined, joined
    assert "a control-plane block marker inside the {} region".format(region) in joined, joined


ORACLE_CANONICAL_DECLARATION_LINES = [
    "MERGE_AUTHORITY_SOURCE: HUMAN_ONLY_PER_PR",
    "PR_SIZING_AUTHORITY: SEMANTIC_CLOSURE_ONLY",
    "TASK_FAMILY_AUTHORITY: CANONICAL_ONLY",
    "EFFORT_AUTHORITY: CANONICAL_ONLY",
    "MAX_EFFORT_CLASSES: T3B,T3D,T3E,T4",
]
_DECLARATION_CASES = [
    (line, region) for line in ORACLE_CANONICAL_DECLARATION_LINES for region in ORACLE_EXEMPTION_REGION_TYPES
]


@pytest.mark.parametrize(
    ("line", "region"),
    _DECLARATION_CASES,
    ids=["{} inside {}".format(line.split(":")[0], region) for line, region in _DECLARATION_CASES],
)
def test_an_exempted_declaration_is_not_a_declaration(sandbox: Path, line: str, region: str) -> None:
    text = read(sandbox, CANONICAL)
    index = text.split("\n").index(line)
    write(sandbox, CANONICAL, _wrap_lines(text, index, index, region))
    joined = "\n".join(failures(sandbox))
    name = line.split(":")[0]
    assert "a canonical authority declaration inside the {} region".format(region) in joined, joined
    if name == "MAX_EFFORT_CLASSES":
        assert "MAX_EFFORT_CLASSES must be declared exactly once, found 0" in joined, joined
    else:
        assert "{} must be declared exactly once across active doctrine surfaces, found 0".format(name) in joined, (
            joined
        )


_MARKER_CASES = [
    (rel, kind, region)
    for rel in sorted(ORACLE_ACTIVE_DOCTRINE_SURFACES)
    for kind in ("ROLE", "REF")
    for region in ORACLE_EXEMPTION_REGION_TYPES
    if not (kind == "REF" and rel == CANONICAL)
]


@pytest.mark.parametrize(
    ("rel", "kind", "region"),
    _MARKER_CASES,
    ids=["{} {} inside {}".format(*case) for case in _MARKER_CASES],
)
def test_an_exempted_role_or_reference_marker_is_not_a_marker(sandbox: Path, rel: str, kind: str, region: str) -> None:
    text = read(sandbox, rel)
    opening = "<!-- CONTROL_PLANE_ROLE:" if kind == "ROLE" else "<!-- CONTROL_PLANE_AUTHORITY_REF:"
    indexes = [index for index, line in enumerate(text.split("\n")) if line.startswith(opening)]
    assert len(indexes) == 1, rel
    write(sandbox, rel, _wrap_lines(text, indexes[0], indexes[0], region))
    joined = "\n".join(failures(sandbox))
    assert "a control-plane role or authority-reference marker inside the {} region".format(region) in joined, joined
    if kind == "ROLE":
        assert "{}: expected exactly one CONTROL_PLANE_ROLE marker, found 0".format(rel) in joined, joined
    else:
        assert "{}: missing CONTROL_PLANE_AUTHORITY_REF marker".format(rel) in joined, joined


def _token_pattern(token: str) -> re.Pattern[str]:
    return re.compile(r"\s+".join(re.escape(word) for word in token.split()))


ORACLE_TOKENS_READ_FROM_THE_ACTIVE_PROJECTION = [
    "ORACLE_EXTERNAL_BOOTSTRAP_ANCHOR",
    "TYPED_EXEMPTION_REGIONS",
    "HOST_DISCOVERY_BEATS_REGISTRY_ASSUMPTION",
    "ROOT_CAUSE_MODE",
    "CLOSED_FROZEN",
    "SELF_AUDIT_ONLY_NOT_INDEPENDENT",
    "Work is not a separate free provider",
    "There is no enforced provider ratio anywhere in this control plane.",
]


@pytest.mark.parametrize("token", ORACLE_TOKENS_READ_FROM_THE_ACTIVE_PROJECTION)
def test_a_required_token_only_inside_history_is_missing(sandbox: Path, token: str) -> None:
    text = _token_pattern(token).sub("REDACTED_TOKEN", read(sandbox, CANONICAL))
    end = "<!-- HISTORICAL_RECORD_END -->"
    assert text.count(end) == 1
    write(sandbox, CANONICAL, text.replace(end, token + "\n" + end))
    assert_rejects(sandbox, "required contract token missing: {}".format(token))


@pytest.mark.parametrize("token", ["FRESH_CHAT_BOOTSTRAP", "STATE_MANIFEST_V1", "CURRENT_HANDOFF_V2", "CLOSED_FROZEN"])
def test_a_continuity_token_only_inside_history_is_missing(sandbox: Path, token: str) -> None:
    rel = "docs/crypto_core/continuity/CONTINUITY_INDEX.md"
    text = _token_pattern(token).sub("REDACTED_TOKEN", read(sandbox, rel))
    write(
        sandbox,
        rel,
        text.rstrip("\n") + "\n\n<!-- HISTORICAL_RECORD_BEGIN -->\n{}\n<!-- HISTORICAL_RECORD_END -->\n".format(token),
    )
    assert_rejects(sandbox, "required continuity token missing: {}".format(token))


def test_the_copilot_shim_status_only_inside_history_is_missing(sandbox: Path) -> None:
    rel = ".github/copilot-instructions.md"
    text = read(sandbox, rel).replace("INACTIVE_UNAVAILABLE", "REDACTED_TOKEN")
    end = "<!-- HISTORICAL_RECORD_END -->"
    assert text.count(end) == 1
    write(sandbox, rel, text.replace(end, "INACTIVE_UNAVAILABLE\n" + end))
    assert_rejects(sandbox, "must declare INACTIVE_UNAVAILABLE")


ORACLE_RESERVED_SYNTAX_CASES = [
    ("a block marker", "<!-- ROLE_ROUTING_MATRIX_BEGIN -->", "a control-plane block marker"),
    ("a block marker in another spelling", "<!--role_routing_matrix_end-->", "a control-plane block marker"),
    ("an inline block marker", "Old text <!-- DURABLE_SURFACES_BEGIN --> quoted.", "a control-plane block marker"),
    (
        "a role marker",
        "<!-- CONTROL_PLANE_ROLE: CANONICAL_AUTHORITY -->",
        "a control-plane role or authority-reference marker",
    ),
    (
        "a reference marker",
        "<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->",
        "a control-plane role or authority-reference marker",
    ),
    ("a declaration", "MERGE_AUTHORITY_SOURCE: CONTROLLER_DECIDES", "a canonical authority declaration"),
    ("an indented lower-case declaration", "  max_effort_classes : T3B", "a canonical authority declaration"),
    (
        "a route row",
        "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | xhigh | READ_ONLY",
        "a routing-matrix ROUTE line",
    ),
]


@pytest.mark.parametrize(
    ("label", "line", "needle"),
    ORACLE_RESERVED_SYNTAX_CASES,
    ids=[case[0] for case in ORACLE_RESERVED_SYNTAX_CASES],
)
def test_reserved_authority_syntax_never_appears_inside_an_exemption_region(
    sandbox: Path, label: str, line: str, needle: str
) -> None:
    text = read(sandbox, "CLAUDE.md")
    write(
        sandbox,
        "CLAUDE.md",
        text + "\n<!-- HISTORICAL_RECORD_BEGIN -->\n{}\n<!-- HISTORICAL_RECORD_END -->\n".format(line),
    )
    assert_rejects(sandbox, "{} inside the HISTORICAL_RECORD region".format(needle))


def test_history_that_describes_a_block_without_reproducing_it_stays_legal(sandbox: Path) -> None:
    """The POSITIVE control: history may name an old block and an old declaration, just never reproduce them."""
    rel = "docs/crypto_core/agent_lessons.md"
    text = read(sandbox, rel)
    end = "<!-- HISTORICAL_RECORD_END -->"
    assert text.count(end) == 1
    injected = (
        "The retired `ROLE_ROUTING_MATRIX` block once named another lane, and the old `MAX_EFFORT_CLASSES` "
        "declaration listed a single family.\n"
    )
    write(sandbox, rel, text.replace(end, injected + end))
    assert failures(sandbox) == []


ORACLE_MALFORMED_EXEMPTION_MARKERS = [
    "<!-- historical_record_begin -->",
    "<!--HISTORICAL_RECORD_BEGIN-->",
    "<!-- HISTORICAL_RECORD_BEGIN --> dated notes",
    "<!-- HISTORICAL RECORD BEGIN -->",
    "<!-- EXAMPLE-ONLY-END -->",
]


@pytest.mark.parametrize("marker", ORACLE_MALFORMED_EXEMPTION_MARKERS)
def test_an_exemption_marker_in_another_spelling_is_rejected(sandbox: Path, marker: str) -> None:
    write(sandbox, "CLAUDE.md", marker + "\n\n" + read(sandbox, "CLAUDE.md"))
    assert_rejects(sandbox, "CLAUDE.md:1: malformed exemption marker")


def test_the_active_projection_preserves_every_line_position() -> None:
    lines = ["one", "<!-- HISTORICAL_RECORD_BEGIN -->", "dated pin", "<!-- HISTORICAL_RECORD_END -->", "", "six"]
    projection = validator.project_surface("fixture", lines)
    assert projection.failures == ()
    assert projection.lines == ("one", None, None, None, "", "six")
    assert projection.text.split("\n") == ["one", "", "", "", "", "six"]
    assert projection.numbered == [(1, "one"), (5, ""), (6, "six")]


def test_scan_exemption_and_authority_inertness_are_one_decision(sandbox: Path) -> None:
    """A5. The region that exempts a pin from the durable scan is the region that makes a block inert."""
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, "LANE_CAPABILITY")
    lines = text.split("\n")
    lines.insert(last + 1, "Dated evidence: merge commit 61cd4d6b960067ef4eaa5634fff10b6cecf72403.")
    write(sandbox, CANONICAL, _wrap_lines("\n".join(lines), first, last + 1, "HISTORICAL_RECORD"))
    joined = "\n".join(failures(sandbox))
    assert "volatile commit hash" not in joined, joined
    assert "MISSING_ACTIVE_AUTHORITY: LANE_CAPABILITY " in joined, joined


def test_only_the_registry_check_reads_the_raw_canonical_text() -> None:
    """A1/A2, structural: one raw read of the canonical authority, immediately projected; no second reader."""
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    readers = []
    for function in ast.parse(source).body:
        if not isinstance(function, ast.FunctionDef):
            continue
        for node in ast.walk(function):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "text"
                and any(
                    isinstance(name, ast.Name) and name.id == "CANONICAL" for arg in node.args for name in ast.walk(arg)
                )
            ):
                readers.append(function.name)
    assert readers == ["_check_registries"]
    assert "canonical_text" not in source


_ORACLE_RULE_DESCRIPTION = (
    "description: HISTORICAL BIST / PRDV3 reference only \u2014 NOT active crypto_core doctrine. Does not auto-apply."
)


def _rule(*entries: str) -> str:
    return "---\n" + "".join(entry + "\n" for entry in entries) + "---\n\n# body\n"


ORACLE_NON_APPLYING_CASES = [
    ("alwaysApply true", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: true"), False),
    ("alwaysApply true without a space", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply:true"), False),
    ("alwaysApply true with a comment", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: true # comment"), False),
    ("alwaysApply double-quoted true", _rule(_ORACLE_RULE_DESCRIPTION, 'alwaysApply: "true"'), False),
    ("alwaysApply single-quoted true", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: 'true'"), False),
    ("alwaysApply yes", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: yes"), False),
    ("alwaysApply on", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: on"), False),
    ("alwaysApply 1", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: 1"), False),
    ("alwaysApply double-quoted false", _rule(_ORACLE_RULE_DESCRIPTION, 'alwaysApply: "false"'), False),
    ("alwaysApply false with a comment", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false # comment"), False),
    ("alwaysApply missing", _rule(_ORACLE_RULE_DESCRIPTION), False),
    ("alwaysApply repeated false", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "alwaysApply: false"), False),
    ("alwaysApply false then true", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "alwaysApply: true"), False),
    ("alwaysApply true then false", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: true", "alwaysApply: false"), False),
    ("no front matter", "# body only\n\nalwaysApply: false\n", False),
    ("unclosed front matter", "---\n" + _ORACLE_RULE_DESCRIPTION + "\nalwaysApply: false\n", False),
    ("empty front matter", "---\n---\n\n# body\n", False),
    ("globs everything", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", 'globs: "**"'), False),
    ("globs empty", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "globs:"), False),
    ("globs with a value", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "globs: src/**/*.py"), False),
    ("alwaysApply False", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: False"), False),
    ("alwaysApply FALSE", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: FALSE"), False),
    ("alwaysApply no", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: no"), False),
    ("alwaysApply off", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: off"), False),
    ("alwaysApply 0", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: 0"), False),
    ("alwaysApply null", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: null"), False),
    ("alwaysApply tilde", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: ~"), False),
    ("alwaysApply empty", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply:"), False),
    ("alwaysApply after a tab", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply:\tfalse"), False),
    ("alwaysApply anchored", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: &flag false"), False),
    ("alwaysApply tagged", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: !!bool false"), False),
    ("indented entry", _rule(_ORACLE_RULE_DESCRIPTION, "  alwaysApply: false"), False),
    ("unknown key", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "priority: 1"), False),
    ("key in another case", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", "AlwaysApply: true"), False),
    ("quoted key", _rule(_ORACLE_RULE_DESCRIPTION, '"alwaysApply": false'), False),
    ("comment line", _rule(_ORACLE_RULE_DESCRIPTION, "# note", "alwaysApply: false"), False),
    ("blank line", _rule(_ORACLE_RULE_DESCRIPTION, "", "alwaysApply: false"), False),
    ("flow mapping", "---\n{alwaysApply: true}\n---\n\n# body\n", False),
    (
        "block scalar swallowing the flag",
        '---\ndescription: >\n  alwaysApply: false\nglobs: "**"\n---\n\n# body\n',
        False,
    ),
    ("document end marker", "---\n" + _ORACLE_RULE_DESCRIPTION + "\nalwaysApply: false\n...\n---\n\n# body\n", False),
    ("blank line before the header", "\n" + _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false"), False),
    (
        "header with a trailing space",
        "--- \n" + _ORACLE_RULE_DESCRIPTION + "\nalwaysApply: false\n---\n\n# body\n",
        False,
    ),
    ("quoted description", _rule('description: "historical"', "alwaysApply: false"), False),
    ("repeated description", _rule(_ORACLE_RULE_DESCRIPTION, _ORACLE_RULE_DESCRIPTION, "alwaysApply: false"), False),
    ("description with mapping syntax", _rule("description: old: rule", "alwaysApply: false"), False),
    ("description with a comment", _rule("description: old #rule", "alwaysApply: false"), False),
    (
        "line separator inside an entry",
        _rule(_ORACLE_RULE_DESCRIPTION + "\u2028globs: '**'", "alwaysApply: false"),
        False,
    ),
    (
        "line separator inside a description",
        _rule(_ORACLE_RULE_DESCRIPTION + "\u2028note", "alwaysApply: false"),
        False,
    ),
    (
        "zero-width character inside a description",
        _rule("description: historical\u200brule", "alwaysApply: false"),
        False,
    ),
    ("the committed shape", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false"), True),
    ("a manual rule with no description", _rule("alwaysApply: false"), True),
    ("the flag before the description", _rule("alwaysApply: false", _ORACLE_RULE_DESCRIPTION), True),
    ("trailing spaces after false", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false   "), True),
    ("CRLF line endings", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false").replace("\n", "\r\n"), True),
    ("a byte-order mark", "\ufeff" + _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false"), True),
]


@pytest.mark.parametrize(
    ("label", "content", "accepted"),
    ORACLE_NON_APPLYING_CASES,
    ids=[case[0] for case in ORACLE_NON_APPLYING_CASES],
)
def test_non_applying_is_positive_proof_within_a_bounded_subset(label: str, content: str, accepted: bool) -> None:
    """F-B. Anything outside the exact safe subset loses NON_APPLYING; nothing is decided by guessing."""
    found = validator.non_applying_failures(_ORACLE_HISTORICAL_RULE, content)
    assert (not found) is accepted, found


def test_the_committed_historical_rule_is_the_positive_control() -> None:
    text = (REPO_ROOT / _ORACLE_HISTORICAL_RULE).read_text(encoding="utf-8-sig")
    assert validator.non_applying_failures(_ORACLE_HISTORICAL_RULE, text) == []
    header = text.replace("\r\n", "\n").split("\n")[:4]
    assert header[0] == "---" and header[3] == "---"
    assert header[1].startswith("description: ")
    assert header[2] == "alwaysApply: false"


_ORACLE_REPORTED_RULE_BYPASSES = [
    ("true with a comment", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: true # comment")),
    ("quoted true", _rule(_ORACLE_RULE_DESCRIPTION, 'alwaysApply: "true"')),
    ("yes", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: yes")),
    ("no alwaysApply", _rule(_ORACLE_RULE_DESCRIPTION)),
    ("no front matter", "# body only\n\nalwaysApply: false\n"),
    ("globs auto-attach", _rule(_ORACLE_RULE_DESCRIPTION, "alwaysApply: false", 'globs: "**"')),
]


@pytest.mark.parametrize(
    ("label", "content"),
    _ORACLE_REPORTED_RULE_BYPASSES,
    ids=[case[0] for case in _ORACLE_REPORTED_RULE_BYPASSES],
)
def test_the_reported_non_applying_bypasses_fail_the_control_plane(sandbox: Path, label: str, content: str) -> None:
    """F-B, the reported reproduction: each of these left the control plane PASS on the prior bytes."""
    target = sandbox / _ORACLE_HISTORICAL_RULE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")
    assert_rejects(sandbox, "{}: NON_APPLYING is not proven".format(_ORACLE_HISTORICAL_RULE))


ORACLE_UNCONTRACTED_HISTORICAL_SURFACES = [
    (".github/instructions/legacy.instructions.md", '---\napplyTo: "**"\n---\nlegacy\n'),
    (".github/instructions/legacy.instructions.md", "---\ndescription: legacy\nalwaysApply: false\n---\nlegacy\n"),
    (".github/prompts/legacy.prompt.md", "---\nmode: agent\n---\nlegacy\n"),
    (".github/agents/legacy.agent.md", "---\nname: legacy\n---\nlegacy\n"),
    (".claude/skills/legacy/SKILL.md", "---\nname: legacy\ndescription: legacy skill\n---\nlegacy\n"),
    (".codex/skills/legacy/SKILL.md", "---\nname: legacy\ndescription: legacy skill\n---\nlegacy\n"),
]


def _register_historical_surface(root: Path, rel: str, content: str) -> None:
    canonical = root / CANONICAL
    text = canonical.read_text(encoding="utf-8")
    row = "- .cursor/rules/prdv3-constitution.mdc :: NON_APPLYING\n"
    assert text.count(row) == 1
    canonical.write_text(text.replace(row, row + "- {} :: NON_APPLYING\n".format(rel)), encoding="utf-8", newline="\n")
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8", newline="\n")


@pytest.mark.parametrize(
    ("rel", "content"),
    ORACLE_UNCONTRACTED_HISTORICAL_SURFACES,
    ids=["{} #{}".format(rel, index) for index, (rel, _c) in enumerate(ORACLE_UNCONTRACTED_HISTORICAL_SURFACES)],
)
def test_a_non_applying_label_without_a_location_contract_fails(sandbox: Path, rel: str, content: str) -> None:
    """INERT_BY_LABEL_BUT_ACTIVE_BY_HOST: these were accepted with any metadata at all."""
    _register_historical_surface(sandbox, rel, content)
    assert_rejects(sandbox, "{}: NON_APPLYING is not proven - no non-application contract exists".format(rel))


def test_the_contract_follows_the_cursor_location_not_one_file_name(sandbox: Path) -> None:
    _register_historical_surface(
        sandbox, ".cursor/rules/legacy/old.mdc", "---\ndescription: legacy\nalwaysApply: false\n---\nlegacy\n"
    )
    assert failures(sandbox) == []


def test_the_setup_audit_owns_no_non_applying_judgement() -> None:
    body = _audit_source().split("#>", 1)[1]
    section = body.split("LEGACY BIST CURSOR RULE (deterministic)", 1)[1].split("Write-Section", 1)[0]
    code = "\n".join(line for line in section.splitlines() if not line.lstrip().startswith("#"))
    assert "agent_os.non_applying_failures" in code
    assert "Select-String" not in code
    assert "alwaysApply" not in code


@pytest.mark.skipif(_powershell() is None, reason="no PowerShell host available")
@pytest.mark.parametrize(
    ("label", "content"),
    [*_ORACLE_REPORTED_RULE_BYPASSES, ("the committed rule", None)],
    ids=[case[0] for case in _ORACLE_REPORTED_RULE_BYPASSES] + ["the committed rule"],
)
def test_the_setup_audit_reports_the_one_non_applying_contract(tmp_path: Path, label: str, content: object) -> None:
    """EXECUTED. The audit's own lexical search printed OK for each reported bypass on the prior bytes."""
    planted = tmp_path / "scripts" / "crypto_core" / "validate_agent_os_v2.py"
    planted.parent.mkdir(parents=True)
    shutil.copyfile(VALIDATOR_PATH, planted)
    rule = tmp_path / _ORACLE_HISTORICAL_RULE
    rule.parent.mkdir(parents=True)
    if content is None:
        shutil.copyfile(REPO_ROOT / _ORACLE_HISTORICAL_RULE, rule)
    else:
        rule.write_text(str(content), encoding="utf-8", newline="\n")
    done = _run_setup_audit_offline(tmp_path)
    if content is None:
        assert "{} : NON_APPLYING (".format(_ORACLE_HISTORICAL_RULE) in done.stdout, done.stdout
    else:
        assert "{} : NOT_PROVEN_NON_APPLYING".format(_ORACLE_HISTORICAL_RULE) in done.stdout, done.stdout
        assert "NON_APPLYING is not proven" in done.stdout, done.stdout
        assert done.returncode != 0, done.stdout + done.stderr
    assert not (planted.parent / "__pycache__").exists(), "the contract import wrote bytecode"


def test_the_active_surface_semantics_are_documented() -> None:
    text = _normalized(REPO_ROOT / CANONICAL)
    for token in (
        "ACTIVE_CONTROL_PLANE_SURFACE_SEMANTICS",
        "MISSING_ACTIVE_AUTHORITY",
        "NON_APPLYING_FRONT_MATTER_CONTRACT",
    ):
        assert token in text, token
    assert "Authority syntax is RESERVED" in text
    assert "it is POSITIVE PROOF, never the absence of a known unsafe spelling" in text
    assert "rejects the surface the moment its front matter declares" not in text


# ===========================================================================================
# ACTIVE_AUTHORITY_STRUCTURAL_COMPLETENESS
#
# A control-plane authority construct is valid only when its complete active structural form is uniquely
# present and populated. Three sibling failures, closed together: a ROUTE row and a canonical declaration
# recognized only at column zero, an authority reference proven by presence instead of cardinality and
# value, and a required block accepted for its markers alone. Every expected verdict below is written out
# literally and never derived from the validator.
# ===========================================================================================

ORACLE_AUTHORITY_INDENTS = [
    ("column zero", ""),
    ("two spaces", "  "),
    ("four spaces", "    "),
    ("a tab", chr(9)),
    ("a space and a tab", " " + chr(9)),
]
ORACLE_EXTERNAL_ROUTE = "ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | low | READ_ONLY"
ORACLE_ROUTE_SURFACES = ["CLAUDE.md", "docs/crypto_core/model_prompting_guide.md"]
ORACLE_INDEPENDENCE_STATES = [
    "SELF_AUDIT_ONLY_NOT_INDEPENDENT",
    "ORDINARY_INDEPENDENT_REVIEW",
    "PROTECTED_CLASS_C_AUDIT",
]
ORACLE_TESTED_REVISION_FIELDS = [
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
]

_ROUTE_INDENT_CASES = [
    (rel, label, indent) for rel in ORACLE_ROUTE_SURFACES for label, indent in ORACLE_AUTHORITY_INDENTS
]


@pytest.mark.parametrize(
    ("rel", "label", "indent"),
    _ROUTE_INDENT_CASES,
    ids=["{} with {}".format(rel, label) for rel, label, _indent in _ROUTE_INDENT_CASES],
)
def test_an_external_route_line_is_rejected_at_any_indentation(
    sandbox: Path, rel: str, label: str, indent: str
) -> None:
    """P1-01: a competing route hid behind ordinary Markdown indentation; only column zero was rejected."""
    write(sandbox, rel, read(sandbox, rel) + "\n" + indent + ORACLE_EXTERNAL_ROUTE + "\n")
    assert_rejects(sandbox, "ROUTE line outside the canonical routing matrix")


def test_an_external_route_line_with_a_spaced_colon_is_rejected(sandbox: Path) -> None:
    write(
        sandbox,
        "CLAUDE.md",
        read(sandbox, "CLAUDE.md") + "\n  ROUTE : T4 | REVIEW | Claude Opus 5 | claude-opus-5 | low | READ_ONLY\n",
    )
    assert_rejects(sandbox, "ROUTE line outside the canonical routing matrix")


def test_the_canonical_matrix_rows_remain_legal(sandbox: Path) -> None:
    """The POSITIVE anchor: the canonical matrix is full of ROUTE rows and must stay valid."""
    rows = [line for line in read(sandbox, CANONICAL).split("\n") if line.startswith("ROUTE:")]
    assert len(rows) >= 20
    assert failures(sandbox) == []


_DECLARATION_INDENT_CASES = [
    ("MERGE_AUTHORITY_SOURCE: CONTROLLER_DECIDES", "MERGE_AUTHORITY_SOURCE must be declared exactly once"),
    ("PR_SIZING_AUTHORITY: MAX_FILE_COUNT", "PR_SIZING_AUTHORITY must be declared exactly once"),
    ("TASK_FAMILY_AUTHORITY: ADAPTER_DECIDES", "TASK_FAMILY_AUTHORITY must be declared exactly once"),
    ("EFFORT_AUTHORITY: HOST_DECIDES", "EFFORT_AUTHORITY must be declared exactly once"),
    ("MAX_EFFORT_CLASSES: T0,T1,T2", "MAX_EFFORT_CLASSES must be declared exactly once"),
]
_DECLARATION_CASES_WITH_INDENT = [
    (line, needle, label, indent)
    for line, needle in _DECLARATION_INDENT_CASES
    for label, indent in ORACLE_AUTHORITY_INDENTS[1:]
]


@pytest.mark.parametrize(
    ("line", "needle", "label", "indent"),
    _DECLARATION_CASES_WITH_INDENT,
    ids=["{} with {}".format(case[0].split(":")[0], case[2]) for case in _DECLARATION_CASES_WITH_INDENT],
)
def test_an_indented_declaration_in_a_subordinate_is_still_a_declaration(
    sandbox: Path, line: str, needle: str, label: str, indent: str
) -> None:
    """P1-01 sibling: the declaration reader used the same column-zero anchor as the ROUTE reader."""
    write(sandbox, "CLAUDE.md", read(sandbox, "CLAUDE.md") + "\n" + indent + line + "\n")
    assert_rejects(sandbox, needle)


def test_a_declaration_carrying_more_than_one_value_token_is_rejected(sandbox: Path) -> None:
    write(sandbox, "CLAUDE.md", read(sandbox, "CLAUDE.md") + "\n  EFFORT_AUTHORITY: HOST ADAPTER DECIDES\n")
    assert_rejects(sandbox, "a canonical declaration carries exactly one value token")


ORACLE_CANONICAL_REF = "<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->"
ORACLE_FOREIGN_REF = "<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/shadow_authority.md -->"
_AUTHORITY_REF_CASES = [
    (
        "a foreign marker beside the canonical one",
        "append",
        ORACLE_FOREIGN_REF,
        "expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found 2",
    ),
    (
        "the canonical marker duplicated",
        "append",
        ORACLE_CANONICAL_REF,
        "expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found 2",
    ),
    (
        "an indented duplicate",
        "append",
        "   " + ORACLE_CANONICAL_REF,
        "expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found 2",
    ),
    (
        "a spaced-out duplicate",
        "append",
        "<!--   CONTROL_PLANE_AUTHORITY_REF :  docs/crypto_core/agent_os_v2.md   -->",
        "expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found 2",
    ),
    (
        "a foreign marker instead of the canonical one",
        "replace",
        ORACLE_FOREIGN_REF,
        "CONTROL_PLANE_AUTHORITY_REF names",
    ),
    ("no marker at all", "remove", "", "missing CONTROL_PLANE_AUTHORITY_REF marker"),
    ("the marker only inside history", "exempt", "", "missing CONTROL_PLANE_AUTHORITY_REF marker"),
]


@pytest.mark.parametrize(
    ("label", "mode", "payload", "needle"),
    _AUTHORITY_REF_CASES,
    ids=[case[0] for case in _AUTHORITY_REF_CASES],
)
def test_the_authority_reference_is_unique_and_canonical(
    sandbox: Path, label: str, mode: str, payload: str, needle: str
) -> None:
    """P1-02: presence of the expected marker proved one exists, never that it is the only one."""
    rel = "CLAUDE.md"
    text = read(sandbox, rel)
    assert text.count(ORACLE_CANONICAL_REF) == 1
    if mode == "append":
        text = text + "\n" + payload + "\n"
    elif mode == "replace":
        text = text.replace(ORACLE_CANONICAL_REF, payload, 1)
    elif mode == "remove":
        text = text.replace(ORACLE_CANONICAL_REF + "\n", "", 1)
    else:
        text = text.replace(
            ORACLE_CANONICAL_REF,
            "<!-- HISTORICAL_RECORD_BEGIN -->\n" + ORACLE_CANONICAL_REF + "\n<!-- HISTORICAL_RECORD_END -->",
            1,
        )
    write(sandbox, rel, text)
    assert_rejects(sandbox, needle)


def test_the_canonical_authority_references_no_other_authority(sandbox: Path) -> None:
    """P1-02 sibling: the canonical file itself could carry a marker naming another authority."""
    text = read(sandbox, CANONICAL)
    marker = "<!-- CONTROL_PLANE_ROLE: CANONICAL_AUTHORITY -->"
    assert text.count(marker) == 1
    write(sandbox, CANONICAL, text.replace(marker, marker + "\n" + ORACLE_FOREIGN_REF, 1))
    assert_rejects(sandbox, "the canonical authority references no other authority")


@pytest.mark.parametrize("rel", sorted(set(ORACLE_ACTIVE_DOCTRINE_SURFACES) - {CANONICAL}))
def test_every_subordinate_surface_carries_exactly_one_canonical_reference(rel: str) -> None:
    """The POSITIVE anchor, on the real tree: one marker, resolving to the canonical authority."""
    text = (REPO_ROOT / rel).read_text(encoding="utf-8-sig")
    targets = re.findall(r"<!--\s*CONTROL_PLANE_AUTHORITY_REF\s*:\s*([^>]*?)\s*-->", text)
    assert targets == [CANONICAL], targets


_BLOCK_BODY_SHAPES = [
    ("an empty body", []),
    ("a whitespace-only body", ["   "]),
    ("a comment-only body", ["<!-- retired -->"]),
]
_BLOCK_BODY_CASES = [
    (name, shape, filler) for name in ORACLE_CANONICAL_AUTHORITY_BLOCKS for shape, filler in _BLOCK_BODY_SHAPES
]


@pytest.mark.parametrize(
    ("name", "shape", "filler"),
    _BLOCK_BODY_CASES,
    ids=["{} with {}".format(name, shape) for name, shape, _f in _BLOCK_BODY_CASES],
)
def test_a_required_authority_block_must_carry_a_body(sandbox: Path, name: str, shape: str, filler: list) -> None:
    """P2-01: markers alone certified a block; emptying two of the 25 left the whole gate green."""
    text = read(sandbox, CANONICAL)
    first, last = _authority_bounds(text, name)
    lines = text.split("\n")
    write(sandbox, CANONICAL, "\n".join(lines[: first + 1] + filler + lines[last:]))
    found = failures(sandbox)
    assert found, "{} was accepted with {}".format(name, shape)


def test_the_inventory_itself_rejects_an_empty_block_body() -> None:
    """The floor under every block: the inventory refuses an empty body even where a consumer would not."""
    text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    first, last = _authority_bounds(text, "MODEL_AGNOSTIC_SURFACES")
    lines = text.split(chr(10))
    emptied = chr(10).join(lines[: first + 1] + lines[last:])
    # The inventory reads the ACTIVE projection, exactly as the validator feeds it.
    emptied_view = validator.project_surface(CANONICAL, emptied.split(chr(10)))
    found = validator.active_authority_failures(emptied_view.text)
    assert any("MODEL_AGNOSTIC_SURFACES carries no active body" in item for item in found), found
    committed_view = validator.project_surface(CANONICAL, text.split(chr(10)))
    assert validator.active_authority_failures(committed_view.text) == []


def test_the_independence_vocabulary_body_matches_canonical_doctrine(sandbox: Path) -> None:
    rows = validator.parse_surface_registry(read(sandbox, CANONICAL), "INDEPENDENCE_VOCABULARY")
    assert [state for state, _description in rows or []] == ORACLE_INDEPENDENCE_STATES
    assert all(description for _state, description in rows or [])
    assert failures(sandbox) == []


_INDEPENDENCE_MUTATIONS = [
    (
        "a missing state",
        "- ORDINARY_INDEPENDENT_REVIEW :: fresh-context T3C review by a permitted family that did not implement it\n",
        "",
    ),
    (
        "a duplicated state",
        "- PROTECTED_CLASS_C_AUDIT :: fresh-context GPT-6 Astra T4 only, and nothing else ever satisfies it\n",
        "- PROTECTED_CLASS_C_AUDIT :: fresh-context GPT-6 Astra T4 only, and nothing else ever satisfies it\n- PROTECTED_CLASS_C_AUDIT :: again\n",
    ),
    ("a foreign state", "- PROTECTED_CLASS_C_AUDIT ::", "- CONTROLLER_SUFFICIENT_AUDIT ::"),
    (
        "a reordered vocabulary",
        "- SELF_AUDIT_ONLY_NOT_INDEPENDENT :: the same model family reviewing its own implementation\n",
        "",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new"),
    _INDEPENDENCE_MUTATIONS,
    ids=[case[0] for case in _INDEPENDENCE_MUTATIONS],
)
def test_the_independence_vocabulary_is_enforced_not_merely_present(
    sandbox: Path, label: str, old: str, new: str
) -> None:
    text = read(sandbox, CANONICAL)
    assert text.count(old) == 1, old
    write(sandbox, CANONICAL, text.replace(old, new, 1))
    assert_rejects(sandbox, "INDEPENDENCE_VOCABULARY")


_TESTED_REVISION_MUTATIONS = [
    ("a missing evidence field", "- run_reported_head\n", ""),
    ("a duplicated evidence field", "- workflow_run_id\n", "- workflow_run_id\n- workflow_run_id\n"),
    ("a foreign evidence field", "- checkout_ref_override\n", "- checkout_ref_override\n- checkout_ref_trusted\n"),
    ("a reordered bundle", "- event\n- audited_pr_head\n", "- audited_pr_head\n- event\n"),
]


@pytest.mark.parametrize(
    ("label", "old", "new"),
    _TESTED_REVISION_MUTATIONS,
    ids=[case[0] for case in _TESTED_REVISION_MUTATIONS],
)
def test_the_tested_revision_bundle_declaration_is_enforced(sandbox: Path, label: str, old: str, new: str) -> None:
    text = read(sandbox, CANONICAL)
    assert text.count(old) == 1, old
    write(sandbox, CANONICAL, text.replace(old, new, 1))
    assert_rejects(sandbox, "TESTED_REVISION_EVIDENCE must declare exactly")


def test_the_tested_revision_declaration_matches_the_executable_bundle() -> None:
    declared = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "TESTED_REVISION_EVIDENCE"
    )
    assert declared == ORACLE_TESTED_REVISION_FIELDS
    assert list(validator.TESTED_REVISION_EVIDENCE_FIELDS) == ORACLE_TESTED_REVISION_FIELDS


def test_one_matcher_decides_what_an_authority_construct_is() -> None:
    """F1 structurally: the active reader and the reserved rule share one pattern per construct."""
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    assert 'line.startswith("ROUTE:")' not in source
    assert "ref_marker not in text" not in source
    for indent in ("", "  ", "    ", chr(9), " " + chr(9)):
        assert validator.ROUTE_LINE_RE.match(indent + "ROUTE: T0 | STATUS | x | - | low | MECHANICAL_ONLY")
        assert validator.DECLARATION_LINE_RE.match(indent + "MERGE_AUTHORITY_SOURCE: HUMAN_ONLY_PER_PR")
    assert not validator.ROUTE_LINE_RE.match("ROUTES: not a row")
    assert not validator.DECLARATION_LINE_RE.match("MERGE_AUTHORITY_SOURCE_REF: x")


def test_the_structural_completeness_rules_are_documented() -> None:
    text = _normalized(REPO_ROOT / CANONICAL)
    assert "ACTIVE_AUTHORITY_STRUCTURAL_COMPLETENESS" in text
    assert "regardless of indentation" in text
    assert "exactly one authority reference" in text


# ===========================================================================================
# ONE_AUTHORITY_READING and the ONE FILE-TO-TEXT BOUNDARY
#
# Two root causes, closed together. The executable subordinates had a reader of their own - a raw count of one
# exact marker string inside the first raw triple-quote span - so a second authority, a reference that existed
# only inside an exemption region, a malformed exemption and a decoy string were all certified. And a committed
# file carrying a byte that is not UTF-8 raised past the gate instead of producing a verdict. Every expected
# verdict below is written out literally and never derived from the validator.
# ===========================================================================================

ORACLE_EXECUTABLE_SUBORDINATES = [
    "scripts/crypto_core/validate_agent_os_v2.py",
    "tests/crypto_core/test_agent_os_v2_contract.py",
]
ORACLE_CANONICAL_REF = "<!-- CONTROL_PLANE_AUTHORITY_REF: docs/crypto_core/agent_os_v2.md -->"
ORACLE_FOREIGN_TARGET = "docs/crypto_core/shadow_authority.md"
ORACLE_FOREIGN_REF = "<!-- CONTROL_PLANE_AUTHORITY_REF: " + ORACLE_FOREIGN_TARGET + " -->"
ORACLE_BOUNDARY_OPENING = "NEGATIVE_BOUNDARY: The repository validator proves repository-provable structure only."
# One doctrine surface beside the two executables: the same mutation must earn the same verdict whichever KIND of
# surface carries it. That is what "one reading" means, and a per-kind reader cannot pass it.
ORACLE_AUTHORITY_SURFACE_ROLES = {
    "CLAUDE.md": "CLAUDE_ADAPTER",
    "scripts/crypto_core/validate_agent_os_v2.py": "EXECUTABLE_SUBORDINATE",
    "tests/crypto_core/test_agent_os_v2_contract.py": "EXECUTABLE_SUBORDINATE",
}


def _authority_span(rel: str, text: str) -> tuple[int, int]:
    """Where a surface's authority text lives, by the oracle's own reading of the committed layout.

    The whole file for a doctrine surface; the leading triple-quoted module docstring for an executable.
    """
    if rel not in ORACLE_EXECUTABLE_SUBORDINATES:
        return 0, len(text)
    start = text.index('"""')
    return start, text.index('"""', start + 3) + 3


def _mutate_authority_text(root: Path, rel: str, old: str, new: str) -> None:
    """Replace ``old`` exactly once inside the surface's authority text, proving it was there first."""
    text = read(root, rel)
    start, end = _authority_span(rel, text)
    region = text[start:end]
    assert region.count(old) == 1, (rel, old)
    write(root, rel, text[:start] + region.replace(old, new) + text[end:])


def _role_line(rel: str) -> str:
    return "<!-- CONTROL_PLANE_ROLE: {} -->".format(ORACLE_AUTHORITY_SURFACE_ROLES[rel])


def _assert_names(found: list[str], rel: str, fragment: str) -> None:
    joined = "\n".join(found)
    assert any(rel in item and fragment in item for item in found), "{} / {}:\n{}".format(rel, fragment, joined)


_REF = ORACLE_CANONICAL_REF
_HR = ("<!-- HISTORICAL_RECORD_BEGIN -->", "<!-- HISTORICAL_RECORD_END -->")
_EO = ("<!-- EXAMPLE_ONLY_BEGIN -->", "<!-- EXAMPLE_ONLY_END -->")
_FOUND_TWO_REFS = "expected exactly one CONTROL_PLANE_AUTHORITY_REF marker, found 2"
_NAMES_FOREIGN = "CONTROL_PLANE_AUTHORITY_REF names '" + ORACLE_FOREIGN_TARGET + "'"
_MISSING_REF = "missing CONTROL_PLANE_AUTHORITY_REF marker to docs/crypto_core/agent_os_v2.md"
_RESERVED_IN = "a control-plane role or authority-reference marker inside the {} region"

# (label, anchor kind, replacement builder, required failure fragments). The anchor is the surface's own
# canonical reference ("REF") or its own role marker ("ROLE").
ORACLE_ONE_READING_MUTATIONS = [
    (
        "canonical plus foreign reference",
        "REF",
        lambda a: a + "\n" + ORACLE_FOREIGN_REF,
        [_FOUND_TWO_REFS, _NAMES_FOREIGN],
    ),
    ("duplicate canonical reference", "REF", lambda a: a + "\n" + a, [_FOUND_TWO_REFS]),
    ("foreign reference only", "REF", lambda a: ORACLE_FOREIGN_REF, [_NAMES_FOREIGN]),
    ("missing reference", "REF", lambda a: "", [_MISSING_REF]),
    ("indented duplicate reference", "REF", lambda a: a + "\n    " + a, [_FOUND_TWO_REFS]),
    (
        "spaced duplicate reference",
        "REF",
        lambda a: a + "\n<!--  CONTROL_PLANE_AUTHORITY_REF:  docs/crypto_core/agent_os_v2.md  -->",
        [_FOUND_TWO_REFS],
    ),
    (
        "lowercase foreign reference beside the canonical one",
        "REF",
        lambda a: a + "\n" + ORACLE_FOREIGN_REF.lower(),
        ["malformed CONTROL_PLANE_AUTHORITY_REF marker"],
    ),
    (
        "reference only inside HISTORICAL_RECORD",
        "REF",
        lambda a: _HR[0] + "\n" + a + "\n" + _HR[1],
        [_RESERVED_IN.format("HISTORICAL_RECORD"), _MISSING_REF],
    ),
    (
        "reference only inside EXAMPLE_ONLY",
        "REF",
        lambda a: _EO[0] + "\n" + a + "\n" + _EO[1],
        [_RESERVED_IN.format("EXAMPLE_ONLY"), _MISSING_REF],
    ),
    (
        "foreign reference inside an exemption beside the canonical one",
        "REF",
        lambda a: a + "\n" + _HR[0] + "\n" + ORACLE_FOREIGN_REF + "\n" + _HR[1],
        [_RESERVED_IN.format("HISTORICAL_RECORD")],
    ),
    (
        "malformed exemption marker",
        "REF",
        lambda a: a + "\n<!--HISTORICAL_RECORD_BEGIN-->",
        ["malformed exemption marker"],
    ),
    ("unterminated exemption region", "REF", lambda a: a + "\n" + _EO[0], ["unterminated EXAMPLE_ONLY_BEGIN"]),
    (
        "role marker only inside HISTORICAL_RECORD",
        "ROLE",
        lambda a: _HR[0] + "\n" + a + "\n" + _HR[1],
        ["expected exactly one CONTROL_PLANE_ROLE marker, found 0"],
    ),
    (
        "lowercase second role marker",
        "ROLE",
        lambda a: a + "\n<!-- control_plane_role: CANONICAL_AUTHORITY -->",
        ["malformed CONTROL_PLANE_ROLE marker"],
    ),
    (
        "second role marker with a lowercase value",
        "ROLE",
        lambda a: a + "\n<!-- CONTROL_PLANE_ROLE: canonical_authority -->",
        ["malformed CONTROL_PLANE_ROLE marker"],
    ),
    (
        "indented rival canonical declaration",
        "REF",
        lambda a: a + "\n  MERGE_AUTHORITY_SOURCE: AGENT_SELF",
        ["MERGE_AUTHORITY_SOURCE must be declared exactly once"],
    ),
    (
        "indented competing routing row",
        "REF",
        lambda a: a + "\n  ROUTE: T4 | CLASS_C_CROSS_CONTRACT | Claude Opus 5 | claude-opus-5 | low | READ_ONLY",
        ["ROUTE line outside the canonical routing matrix"],
    ),
]

_ONE_READING_CASES = [
    (rel, label, kind, build, fragments)
    for rel in ORACLE_AUTHORITY_SURFACE_ROLES
    for label, kind, build, fragments in ORACLE_ONE_READING_MUTATIONS
]


@pytest.mark.parametrize(
    ("rel", "label", "kind", "build", "fragments"),
    _ONE_READING_CASES,
    ids=["{} - {}".format(case[0], case[1]) for case in _ONE_READING_CASES],
)
def test_authority_reading_gives_every_surface_kind_the_same_verdict(
    sandbox: Path, rel: str, label: str, kind: str, build, fragments: list[str]
) -> None:
    """P2-01 at its root: an executable docstring and a doctrine surface are judged by ONE reading."""
    anchor = _REF if kind == "REF" else _role_line(rel)
    _mutate_authority_text(sandbox, rel, anchor + ("\n" if label == "missing reference" else ""), build(anchor))
    found = failures(sandbox)
    for fragment in fragments:
        _assert_names(found, rel, fragment)


@pytest.mark.parametrize("rel", sorted(ORACLE_AUTHORITY_SURFACE_ROLES))
def test_authority_reading_accepts_every_committed_surface_kind(rel: str) -> None:
    """The POSITIVE anchor of the matrix: each committed surface reads cleanly through the one reading."""
    view = validator.read_projection(REPO_ROOT, rel)
    assert view is not None and view.failures == (), view
    found, role = validator.authority_marker_failures(rel, view.text, ORACLE_AUTHORITY_SURFACE_ROLES[rel])
    assert (found, role) == ([], ORACLE_AUTHORITY_SURFACE_ROLES[rel])


@pytest.mark.parametrize("rel", ORACLE_EXECUTABLE_SUBORDINATES)
def test_authority_reading_keeps_an_executable_line_numbers(rel: str) -> None:
    """The docstring projection is line-preserving, so every diagnostic names the real source line."""
    view = validator.read_projection(REPO_ROOT, rel)
    assert view is not None
    source_lines = (REPO_ROOT / rel).read_text(encoding="utf-8-sig").split("\n")
    expected = [index + 1 for index, line in enumerate(source_lines) if line == ORACLE_CANONICAL_REF]
    assert len(expected) == 1, expected
    assert [lineno for lineno, line in view.numbered if line == ORACLE_CANONICAL_REF] == expected


@pytest.mark.parametrize("rel", ORACLE_EXECUTABLE_SUBORDINATES)
def test_authority_reading_requires_an_active_boundary_sentence(sandbox: Path, rel: str) -> None:
    """The canonical boundary sentence inside EXAMPLE_ONLY is inert and never satisfies the requirement."""
    text = read(sandbox, rel)
    start, end = _authority_span(rel, text)
    line = next(item for item in text[start:end].split("\n") if item.startswith(ORACLE_BOUNDARY_OPENING))
    _mutate_authority_text(sandbox, rel, line, _EO[0] + "\n" + line + "\n" + _EO[1])
    _assert_names(
        failures(sandbox), rel, "does not reproduce the canonical EXECUTABLE_NEGATIVE_BOUNDARY declaration verbatim"
    )


@pytest.mark.parametrize("rel", ORACLE_EXECUTABLE_SUBORDINATES)
def test_authority_reading_uses_the_real_docstring_not_a_decoy(sandbox: Path, rel: str) -> None:
    """The real docstring, quoted differently, names a foreign authority; a later string carries the markers."""
    text = read(sandbox, rel)
    start, end = _authority_span(rel, text)
    docstring = text[start + 3 : end - 3]
    boundary = next(item for item in docstring.split("\n") if item.startswith(ORACLE_BOUNDARY_OPENING))
    rest = text[end:]
    future = "from __future__ import annotations\n"
    assert rest.count(future) == 1
    decoy = '\n_DECOY = """\n' + _role_line(rel) + "\n" + _REF + "\n\n" + boundary + '\n"""\n'
    rest = rest.replace(future, future + decoy)
    write(sandbox, rel, text[:start] + "'''" + docstring.replace(_REF, ORACLE_FOREIGN_REF) + "'''" + rest)
    _assert_names(failures(sandbox), rel, _NAMES_FOREIGN)


@pytest.mark.parametrize("rel", ORACLE_EXECUTABLE_SUBORDINATES)
def test_authority_reading_refuses_an_executable_without_a_module_docstring(sandbox: Path, rel: str) -> None:
    text = read(sandbox, rel)
    start, _end = _authority_span(rel, text)
    write(sandbox, rel, text[:start] + "_DEMOTED = " + text[start:])
    _assert_names(failures(sandbox), rel, "has no module docstring, as Python parses the module")


def test_authority_reading_recognizes_a_marker_with_the_reserved_rule_pattern() -> None:
    """One prefix recognizes a marker for the active reader AND for the reserved-syntax rule."""
    reserved = [pattern for _label, pattern in validator.RESERVED_AUTHORITY_SYNTAX]
    assert validator.ROLE_MARKER_ANY_SPELLING_RE in reserved
    assert validator.AUTHORITY_REF_ANY_SPELLING_RE in reserved
    for spelling in ("<!-- CONTROL_PLANE_ROLE: X -->", "<!-- control_plane_role: X -->", "<!--Control_Plane_Role:X-->"):
        assert validator.ROLE_MARKER_ANY_SPELLING_RE.match(spelling), spelling
    assert validator.ROLE_MARKER_RE.match("<!-- CONTROL_PLANE_ROLE: CLAUDE_ADAPTER -->")
    assert not validator.ROLE_MARKER_RE.match("<!-- control_plane_role: CLAUDE_ADAPTER -->")
    assert not validator.ROLE_MARKER_RE.match("<!-- CONTROL_PLANE_ROLE: claude_adapter -->")
    assert validator.AUTHORITY_REF_ANY_SPELLING_RE.match(ORACLE_FOREIGN_REF.lower())
    assert not validator.AUTHORITY_REF_RE.match(ORACLE_FOREIGN_REF.lower())


def test_authority_reading_is_shared_by_every_surface_kind() -> None:
    """STRUCTURAL: the executable check keeps no marker reader of its own, and both executables are surfaces."""
    registered = [("CLAUDE.md", "CLAUDE_ADAPTER")]
    assert validator.authority_surfaces({"surfaces": registered}) == registered + [
        (rel, "EXECUTABLE_SUBORDINATE") for rel in ORACLE_EXECUTABLE_SUBORDINATES
    ]
    tree = ast.parse(VALIDATOR_PATH.read_text(encoding="utf-8"))
    function = next(
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_check_executable_subordinates"
    )
    code = "\n".join(
        ast.unparse(statement)
        for statement in function.body
        if not (isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Constant))
    )
    for retired in (
        "module_docstring",
        "role_re",
        ".count(",
        "CONTROL_PLANE_AUTHORITY_REF",
        "CONTROL_PLANE_ROLE",
        "read_text",
    ):
        assert retired not in code, retired


ORACLE_TEXT_READ_SURFACES = sorted(
    set(ORACLE_ACTIVE_DOCTRINE_SURFACES)
    | set(ORACLE_EXECUTABLE_SUBORDINATES)
    | {_STRICT_SCHEMA_REL, _STRICT_EXAMPLE_REL, _ORACLE_HISTORICAL_RULE}
)
ORACLE_EXISTENCE_ONLY_ARTIFACTS = sorted(ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS - set(ORACLE_TEXT_READ_SURFACES))
ORACLE_UNDECODABLE = "UNREADABLE_TEXT: not valid UTF-8"


def _stray_byte(data: bytes) -> bytes:
    return data[:40] + b"\xff" + data[40:]


def _utf16(data: bytes) -> bytes:
    return data.decode("utf-8-sig").encode("utf-16")


def _undecodable_prefix(rel: str) -> str:
    if rel == CANONICAL:
        return "canonical authority unreadable: {}: {}".format(CANONICAL, ORACLE_UNDECODABLE)
    if rel in (_STRICT_SCHEMA_REL, _STRICT_EXAMPLE_REL):
        return "{}: STRICT_JSON_REJECTED: {}".format(rel, ORACLE_UNDECODABLE)
    return "{}: {}".format(rel, ORACLE_UNDECODABLE)


_UNDECODABLE_CASES = [
    (rel, label, corrupt)
    for rel in ORACLE_TEXT_READ_SURFACES
    for label, corrupt in (("a stray 0xFF byte", _stray_byte), ("UTF-16", _utf16))
]


@pytest.mark.parametrize(
    ("rel", "label", "corrupt"),
    _UNDECODABLE_CASES,
    ids=["{} as {}".format(rel, label) for rel, label, _corrupt in _UNDECODABLE_CASES],
)
def test_text_boundary_makes_an_undecodable_file_a_structured_rejection(
    sandbox: Path, rel: str, label: str, corrupt
) -> None:
    """P2-02 at its root: every file the gate reads yields a verdict naming it, never a traceback."""
    target = sandbox / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(corrupt((REPO_ROOT / rel).read_bytes()))
    found = failures(sandbox)
    prefix = _undecodable_prefix(rel)
    assert any(item.startswith(prefix) for item in found), "{}:\n{}".format(prefix, "\n".join(found))


@pytest.mark.parametrize("rel", ORACLE_EXISTENCE_ONLY_ARTIFACTS)
def test_text_boundary_never_raises_for_an_existence_only_artifact(sandbox: Path, rel: str) -> None:
    """An artifact whose existence alone is required is not read, so its bytes can neither raise nor fail."""
    target = sandbox / rel
    target.write_bytes(_stray_byte(target.read_bytes()))
    assert failures(sandbox) == []


def test_text_boundary_names_a_missing_or_utf16_compiled_manifest(tmp_path: Path) -> None:
    absent = validator.check_manifest_file(REPO_ROOT, tmp_path / "absent.json")
    assert len(absent) == 1 and "STRICT_JSON_REJECTED: cannot be read as UTF-8 text (missing" in absent[0], absent
    utf16 = tmp_path / "utf16.json"
    utf16.write_bytes(_utf16((REPO_ROOT / _STRICT_EXAMPLE_REL).read_bytes()))
    found = validator.check_manifest_file(REPO_ROOT, utf16)
    assert len(found) == 1 and ORACLE_UNDECODABLE in found[0], found


ORACLE_COMMITTED_JSON_REFUSALS = [
    ("a stray 0xFF byte", _stray_byte, "STRICT_JSON_REJECTED: " + ORACLE_UNDECODABLE),
    ("UTF-16", _utf16, "STRICT_JSON_REJECTED: " + ORACLE_UNDECODABLE),
    ("malformed JSON", lambda data: data.replace(b"{", b"{,", 1), "STRICT_JSON_REJECTED: malformed JSON"),
    (
        "a duplicate member",
        lambda data: data.replace(b"{", b'{"title": "x", "title": "y",', 1),
        "STRICT_JSON_REJECTED: duplicate object member name 'title'",
    ),
    (
        "NaN",
        lambda data: data.replace(b"{", b'{"nan_probe": NaN,', 1),
        "STRICT_JSON_REJECTED: non-finite number NaN is not JSON",
    ),
]
_COMMITTED_JSON_CASES = [
    (rel, label, corrupt, fragment)
    for rel in (_STRICT_SCHEMA_REL, _STRICT_EXAMPLE_REL)
    for label, corrupt, fragment in ORACLE_COMMITTED_JSON_REFUSALS
]


@pytest.mark.parametrize(
    ("rel", "label", "corrupt", "fragment"),
    _COMMITTED_JSON_CASES,
    ids=["{} with {}".format(rel, label) for rel, label, _c, _f in _COMMITTED_JSON_CASES],
)
def test_text_boundary_refuses_a_committed_json_artifact_exactly_once(
    sandbox: Path, rel: str, label: str, corrupt, fragment: str
) -> None:
    target = sandbox / rel
    target.write_bytes(corrupt(target.read_bytes()))
    found = failures(sandbox)
    assert len(found) == 1 and found[0].startswith(rel + ": " + fragment), found


def test_text_boundary_keeps_a_bool_out_of_an_integer_field(sandbox: Path) -> None:
    target = sandbox / _STRICT_EXAMPLE_REL
    text = target.read_text(encoding="utf-8")
    mutated, count = re.subn(r'("open_pr_count":\s*)\d+', r"\1true", text, count=1)
    assert count == 1
    target.write_text(mutated, encoding="utf-8")
    assert_rejects(sandbox, "open_pr_count: must be an integer")


# ===========================================================================================
# FILESYSTEM_ACCESS_AUTHORITY - FILESYSTEM_PATH_TRUST_BOUNDARY_TOTALITY and HOST_EXECUTABLE_DISCOVERY_CLOSED_WORLD
#
# Two root families, closed together. The filesystem authority checked only a path's LEAF, so a junction ancestor
# supplied authority bytes from outside the tree; it matched discovery names case-sensitively, so a `skill.md` that
# a case-insensitive host loads as `SKILL.md` stayed invisible; and it let a path the filesystem cannot encode escape
# as a raw UnicodeEncodeError or read as "missing". Separately, the discovery closed world never modelled GitHub
# Actions, so six executable workflows sat outside it and a rogue workflow passed. Faults are injected at the seams
# the authority itself observes through (os.scandir listings, DirEntry.stat, io.open, os.stat for operator paths), so
# the tests judge behaviour, not call names. Every expected verdict is written out literally.
# ===========================================================================================

ORACLE_FS_TOUCHING_FUNCTIONS = {"observe_status", "read_observed_text", "list_directory", "classify_entry"}
ORACLE_FS_HANDLING_FUNCTIONS = ORACLE_FS_TOUCHING_FUNCTIONS | {"observe_root"}
ORACLE_FS_CALLS = (
    "stat",
    "lstat",
    "is_file",
    "is_dir",
    "is_symlink",
    "exists",
    "read_text",
    "read_bytes",
    "open",
    "glob",
    "rglob",
    "iterdir",
    "scandir",
    "walk",
    "listdir",
    "access",
    "resolve",
    "realpath",
)
ORACLE_FS_ERRORS = {
    "OSError",
    "PermissionError",
    "FileNotFoundError",
    "IsADirectoryError",
    "NotADirectoryError",
    "UnicodeDecodeError",
    "UnicodeEncodeError",
    "UnicodeError",
    "ValueError",
}
ORACLE_ORACLE_REL = "tests/crypto_core/test_agent_os_v2_contract.py"
ORACLE_EXISTENCE_ONLY = ".github/workflows/ci.yml"
ORACLE_RETIRED_PROBE = ".github/prompts/edge-discovery.prompt.md"
ORACLE_ROGUE_DIR = ".claude/skills/zz-oracle-rogue"
ORACLE_ROGUE = ORACLE_ROGUE_DIR + "/SKILL.md"
ORACLE_SURROGATE = chr(0xD800)
ORACLE_FILE_MODE = 0o100644
ORACLE_FIFO_MODE = 0o010644


def _fs_name(path) -> str:
    return os.fsdecode(path).replace("\\", "/") if isinstance(path, (str, bytes, os.PathLike)) else ""


def _same_path(path, target: Path) -> bool:
    if not isinstance(path, (str, bytes, os.PathLike)):
        return False
    return os.path.normcase(os.path.abspath(os.fsdecode(path))) == os.path.normcase(os.path.abspath(target))


def _open_fault(monkeypatch, target: str, make_error) -> None:
    real = io.open

    def faulty(path, *args, **kwargs):
        if _fs_name(path).endswith("/" + target):
            raise make_error(_fs_name(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(io, "open", faulty)


def _eacces(path: str) -> OSError:
    return PermissionError(errno.EACCES, "Permission denied (injected)", path)


def _eio(path: str) -> OSError:
    return OSError(errno.EIO, "Input/output error (injected)", path)


def _vanished(path: str) -> OSError:
    return FileNotFoundError(errno.ENOENT, "No such file or directory (injected)", path)


def _windows_error(klass, code: int, winerror: int) -> OSError:
    """The exception Windows raises for ``winerror``: built natively there, and with the same attributes elsewhere."""
    if sys.platform == "win32":
        return OSError(None, "injected", None, winerror)
    exc = klass(code, "injected")
    exc.winerror = winerror
    return exc


def _fs_root(sandbox: Path) -> Path:
    """The registered file set plus the historical host rule, so every category is really present and PASSES."""
    target = sandbox / _ORACLE_HISTORICAL_RULE
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(REPO_ROOT / _ORACLE_HISTORICAL_RULE, target)
    assert failures(sandbox) == []
    return sandbox


def _names(found: list[str], fragment: str, forbidden: tuple[str, ...] = ()) -> None:
    joined = "\n".join(found)
    assert any(fragment in item for item in found), "{}:\n{}".format(fragment, joined)
    for wrong in forbidden:
        assert wrong not in joined, "a filesystem fault was reported as {!r}:\n{}".format(wrong, joined)


class _FakeEntry:
    """A listed entry the host filesystem cannot produce here: a link, a junction, a collision, a special file."""

    def __init__(self, directory: str, name: str, mode: int, tag: int = 0) -> None:
        self.name = name
        self.path = os.path.join(directory, name)
        self._info = SimpleNamespace(st_mode=mode, st_reparse_tag=tag)

    def stat(self, *, follow_symlinks: bool = True):
        return self._info

    def is_symlink(self) -> bool:
        return S_ISLNK(self._info.st_mode)


class _EntryProxy:
    def __init__(self, entry, behaviour: dict) -> None:
        self._entry = entry
        self._behaviour = behaviour

    def __getattr__(self, name):
        return getattr(self._entry, name)

    def stat(self, *, follow_symlinks: bool = True):
        if "stat_error" in self._behaviour:
            shared = self._behaviour.get("first_calls")
            if shared is None:
                raise self._behaviour["stat_error"]
            shared[0] += 1
            if shared[0] == 1:
                raise self._behaviour["stat_error"]
        if "fake_mode" in self._behaviour:
            return SimpleNamespace(st_mode=self._behaviour["fake_mode"], st_reparse_tag=self._behaviour.get("tag", 0))
        return self._entry.stat(follow_symlinks=follow_symlinks)

    def is_dir(self, *, follow_symlinks: bool = True):
        if "is_dir_error" in self._behaviour:
            raise self._behaviour["is_dir_error"]
        return self._entry.is_dir(follow_symlinks=follow_symlinks)

    def is_file(self, *, follow_symlinks: bool = True):
        if "is_file_error" in self._behaviour:
            raise self._behaviour["is_file_error"]
        return self._entry.is_file(follow_symlinks=follow_symlinks)

    def is_symlink(self):
        if "is_symlink_error" in self._behaviour:
            raise self._behaviour["is_symlink_error"]
        return self._entry.is_symlink()


class _ListingProxy:
    def __init__(self, inner, entry_name, behaviour: dict, iteration_error, extras: list) -> None:
        self._inner = inner
        self._name = entry_name
        self._behaviour = behaviour
        self._iteration_error = iteration_error
        self._extras = extras

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._inner.close()
        return False

    def __iter__(self):
        return self

    def __next__(self):
        if self._iteration_error is not None:
            raise self._iteration_error
        try:
            entry = next(self._inner)
        except StopIteration:
            if self._extras:
                return self._extras.pop(0)
            raise
        return _EntryProxy(entry, self._behaviour) if entry.name == self._name else entry

    def close(self):
        self._inner.close()


def _listing_fault(
    monkeypatch, directory: str, entry_name=None, behaviour=None, iteration_error=None, extras=(), exact=None
) -> None:
    """Wrap the listing of one directory - by path suffix, or by ``exact`` absolute path for the root."""
    real = os.scandir

    def faulty(path=".", *args, **kwargs):
        inner = real(path, *args, **kwargs)
        hit = _same_path(path, exact) if exact is not None else _fs_name(path).endswith("/" + directory)
        if hit:
            fakes = [_FakeEntry(os.fsdecode(path), name, mode, tag) for name, mode, tag in extras]
            return _ListingProxy(inner, entry_name, behaviour or {}, iteration_error, fakes)
        return inner

    monkeypatch.setattr(os, "scandir", faulty)


def _scandir_raises(monkeypatch, target: Path, make_error) -> None:
    real = os.scandir

    def faulty(path=".", *args, **kwargs):
        if _same_path(path, target):
            raise make_error(os.fsdecode(path))
        return real(path, *args, **kwargs)

    monkeypatch.setattr(os, "scandir", faulty)


def _entry_fault(monkeypatch, root: Path, rel: str, error: OSError, *, first_only: bool = False) -> None:
    """Make the ONE classification of ``rel``'s entry fail (only its first call when ``first_only``)."""
    directory, _separator, name = rel.rpartition("/")
    behaviour: dict = {"stat_error": error}
    if first_only:
        behaviour["first_calls"] = [0]
    _listing_fault(monkeypatch, directory, name, behaviour, exact=root / directory if directory else root)


def _rename_case(path: Path, new_name: str) -> None:
    """Change only the case of a name, in two steps so a case-insensitive filesystem really renames it."""
    staging = path.with_name(path.name + ".case-staging")
    path.rename(staging)
    staging.rename(path.with_name(new_name))


def _symlink_or_skip(target: Path | str, link: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip("symbolic links cannot be created on this host: {}".format(type(exc).__name__))


def _directory_redirect_or_skip(target: Path, link: Path) -> str:
    """A directory redirect the host can really make: a junction on Windows, a symbolic link elsewhere."""
    if sys.platform == "win32":
        try:
            import _winapi

            _winapi.CreateJunction(str(target), str(link))
            return "junction"
        except (ImportError, AttributeError, OSError) as exc:
            pytest.skip("a junction cannot be created on this host: {}".format(type(exc).__name__))
    _symlink_or_skip(target, link, directory=True)
    return "symbolic link"


# --- ONE_PATH_VALIDATION_BOUNDARY: the portable Unicode path domain ----------------------------------------------

ORACLE_INVALID_REPOSITORY_PATHS = [
    "",
    "a" + chr(0) + "b",
    "a" + chr(9) + "b",
    "a" + chr(0xD800) + ".md",
    "a" + chr(0xDFFF) + ".md",
    "/absolute.md",
    "a//b.md",
    "./a.md",
    "a/../b.md",
    "..",
    "a\\b.md",
    "C:/x.md",
    "a:b.md",
    "a<b.md",
    "a>b.md",
    'a"b.md',
    "a|b.md",
    "a?b.md",
    "a*b.md",
    "trailing.",
    "trailing ",
    "CON",
    "con.md",
    "dir/LPT1.txt",
    "dir/NUL/child.md",
]
ORACLE_VALID_REPOSITORY_PATHS = [
    "AGENTS.md",
    ".github/skills/_shared/references/contract-schema.md",
    ".cursor/rules/prdv3-constitution.mdc",
    "docs/crypto_core/continuity/CONTINUITY_INDEX.md",
    "CONSOLE.md",
    "a.b.c",
    "docs/r" + chr(0xE9) + "sum" + chr(0xE9) + ".md",
    chr(0x65E5) + chr(0x672C) + "/notes.md",
]


@pytest.mark.parametrize(
    "value", ORACLE_INVALID_REPOSITORY_PATHS, ids=[ascii(v) for v in ORACLE_INVALID_REPOSITORY_PATHS]
)
def test_fs_authority_path_grammar_refuses_a_path_no_platform_should_be_asked_about(value: str) -> None:
    assert validator.repository_path_failure(value) is not None


@pytest.mark.parametrize("value", ORACLE_VALID_REPOSITORY_PATHS, ids=[ascii(v) for v in ORACLE_VALID_REPOSITORY_PATHS])
def test_fs_authority_path_grammar_accepts_a_portable_repository_path(value: str) -> None:
    assert validator.repository_path_failure(value) is None


def test_fs_authority_pattern_grammar_allows_only_glob_wildcards() -> None:
    for good in (".claude/skills/**/SKILL.md", ".github/agents/**/*.agent.md", "a/?.md", ".github/workflows/*"):
        assert validator.repository_path_failure(good, pattern=True) is None, good
    for bad in ("a\\*.md", "C:/**/x.md", "a/../*.md", "a/" + chr(0) + "*.md", "a/" + ORACLE_SURROGATE + "*.md"):
        assert validator.repository_path_failure(bad, pattern=True) is not None, bad
    assert validator.repository_path_failure("a/*.md") is not None


def test_fs_authority_an_invalid_path_is_never_observed(monkeypatch, tmp_path: Path) -> None:
    """INVALID_PATH is decided before any filesystem call, and it is never absence."""

    def forbidden(*args, **kwargs):
        raise AssertionError("the filesystem was asked about an invalid path")

    for name in ("scandir", "lstat", "stat"):
        monkeypatch.setattr(os, name, forbidden)
    ledger = validator.FileLedger(tmp_path)
    for value in ("a" + chr(0) + "b", "CON", "../x", "a" + ORACLE_SURROGATE + ".md"):
        observed = ledger.status(value)
        assert observed.status == "INVALID_PATH" and "INVALID_PATH" in observed.reason, observed


@pytest.mark.parametrize(
    "registry,entry",
    [
        ("RETIRED_CONTROL_PLANE_PATHS", ".github/agents/zz" + chr(0) + "oracle.agent.md"),
        ("RETIRED_CONTROL_PLANE_PATHS", "../outside.agent.md"),
        ("RETIRED_CONTROL_PLANE_PATHS", ".github/agents/NUL.agent.md"),
        ("REQUIRED_CONTROL_PLANE_ARTIFACTS", "docs/crypto_core/zz" + chr(0) + "oracle.md"),
    ],
    ids=["retired NUL", "retired escape", "retired device name", "artifact NUL"],
)
def test_fs_authority_an_invalid_registry_path_fails_and_is_never_absence(
    sandbox: Path, registry: str, entry: str
) -> None:
    text = read(sandbox, CANONICAL)
    begin = "<!-- {}_BEGIN -->\n".format(registry)
    assert text.count(begin) == 1
    write(sandbox, CANONICAL, text.replace(begin, begin + "- " + entry + "\n"))
    found = failures(sandbox)
    _names(found, "{}: {} entry {!r}: INVALID_PATH".format(CANONICAL, registry, entry))
    if registry == "RETIRED_CONTROL_PLANE_PATHS":
        _names(found, "retired control-plane path cannot be proven absent: " + entry)


def test_fs_authority_an_invalid_discovery_pattern_fails(sandbox: Path) -> None:
    text = read(sandbox, CANONICAL)
    begin = "<!-- HOST_DISCOVERY_SCAN_PATHS_BEGIN -->\n"
    write(sandbox, CANONICAL, text.replace(begin, begin + "- .claude/../*.md\n"))
    _names(failures(sandbox), "HOST_DISCOVERY_SCAN_PATHS entry '.claude/../*.md': INVALID_PATH")


@pytest.mark.parametrize("bad", [chr(0), ORACLE_SURROGATE], ids=["NUL", "U+D800"])
def test_fs_authority_operator_paths_are_validated_before_the_filesystem(capsys, tmp_path: Path, bad: str) -> None:
    """P2-PATH-ENCODING at the entrypoints: never a raw exception, never "missing"."""
    assert validator.main(["--root", str(REPO_ROOT) + bad, "--json"]) == 1
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["ok"] is False and "INVALID_PATH" in verdict["failures"][0], verdict
    probe = tmp_path / "probe.json"
    shutil.copyfile(REPO_ROOT / _STRICT_EXAMPLE_REL, probe)
    assert validator.main(["--root", str(REPO_ROOT), "--manifest", str(probe) + bad, "--json"]) == 1
    verdict = json.loads(capsys.readouterr().out)
    assert "INVALID_PATH" in verdict["failures"][0] and "(missing" not in verdict["failures"][0], verdict
    assert "INVALID_PATH" in validator.collect_failures(Path("repo" + bad))[0]
    found = validator.check_manifest_file(REPO_ROOT, Path(str(probe) + bad))
    assert len(found) == 1 and "INVALID_PATH" in found[0], found


def test_fs_authority_a_path_the_filesystem_cannot_encode_is_structured(monkeypatch, capsys, tmp_path: Path) -> None:
    """POSIX converts a path with utf-8 and surrogateescape, which cannot encode U+D800; the authority types it."""
    with pytest.raises(UnicodeEncodeError):
        ORACLE_SURROGATE.encode("utf-8", "surrogateescape")
    bad = tmp_path / ("x" + ORACLE_SURROGATE)

    def encoding(real):
        def converted(path=".", *args, **kwargs):
            if isinstance(path, (str, os.PathLike)) and not isinstance(path, bytes):
                os.fspath(path).encode("utf-8", "surrogateescape")
            return real(path, *args, **kwargs)

        return converted

    for name in ("stat", "scandir"):
        monkeypatch.setattr(os, name, encoding(getattr(os, name)))
    monkeypatch.setattr(io, "open", encoding(io.open))
    assert validator.observe_status(bad).status == "INVALID_PATH"
    entries, status, reason = validator.list_directory(bad)
    assert entries is None and status == "INVALID_PATH" and "not encodable" in reason
    present = validator.FileObservation("PRESENT", kind="file")
    assert validator.read_observed_text(bad, present).status == "INVALID_PATH"
    assert validator.main(["--root", str(bad), "--json"]) == 1
    assert "INVALID_PATH" in json.loads(capsys.readouterr().out)["failures"][0]


def test_fs_authority_a_root_that_is_not_a_directory_is_structured(capsys, tmp_path: Path) -> None:
    afile = tmp_path / "file.txt"
    afile.write_text("x", encoding="utf-8")
    for root, fragment in ((afile, "not a directory"), (tmp_path / "absent", "missing")):
        assert validator.main(["--root", str(root), "--json"]) == 1
        verdict = json.loads(capsys.readouterr().out)
        assert fragment in verdict["failures"][0], verdict


# --- conservative absence ----------------------------------------------------------------------------------------

ORACLE_ABSENCE = [
    ("ENOENT", lambda: FileNotFoundError(errno.ENOENT, "injected"), "MISSING"),
    ("ENOTDIR", lambda: NotADirectoryError(errno.ENOTDIR, "injected"), "MISSING"),
    ("WinError 2", lambda: _windows_error(FileNotFoundError, errno.ENOENT, 2), "MISSING"),
    ("WinError 3", lambda: _windows_error(FileNotFoundError, errno.ENOENT, 3), "MISSING"),
    ("WinError 267", lambda: _windows_error(NotADirectoryError, errno.ENOTDIR, 267), "MISSING"),
    ("EACCES", lambda: PermissionError(errno.EACCES, "injected"), "UNREADABLE"),
    ("EIO", lambda: OSError(errno.EIO, "injected"), "UNREADABLE"),
    ("ELOOP", lambda: OSError(errno.ELOOP, "injected"), "UNREADABLE"),
    ("EBADF", lambda: OSError(errno.EBADF, "injected"), "UNREADABLE"),
    ("WinError 21 device not ready", lambda: _windows_error(PermissionError, errno.EACCES, 21), "UNREADABLE"),
    ("WinError 53 network path", lambda: _windows_error(FileNotFoundError, errno.ENOENT, 53), "UNREADABLE"),
    ("WinError 67 network name", lambda: _windows_error(FileNotFoundError, errno.ENOENT, 67), "UNREADABLE"),
    ("WinError 123 invalid name", lambda: _windows_error(OSError, errno.EINVAL, 123), "UNREADABLE"),
    ("WinError 161 bad pathname", lambda: _windows_error(FileNotFoundError, errno.ENOENT, 161), "UNREADABLE"),
    ("WinError 1921 unresolvable", lambda: _windows_error(OSError, errno.EINVAL, 1921), "UNREADABLE"),
]


@pytest.mark.parametrize(("label", "make", "expected"), ORACLE_ABSENCE, ids=[case[0] for case in ORACLE_ABSENCE])
def test_fs_authority_operator_absence_is_only_what_is_positively_established(
    monkeypatch, tmp_path: Path, label: str, make, expected: str
) -> None:
    def raising(path, *args, **kwargs):
        raise make()

    monkeypatch.setattr(os, "stat", raising)
    assert validator.observe_status(tmp_path / "any.md").status == expected


ORACLE_UNAVAILABLE_LISTINGS = [
    ("ELOOP", lambda p: OSError(errno.ELOOP, "injected", p)),
    ("EBADF", lambda p: OSError(errno.EBADF, "injected", p)),
    ("WinError 21", lambda p: _windows_error(PermissionError, errno.EACCES, 21)),
    ("WinError 53", lambda p: _windows_error(FileNotFoundError, errno.ENOENT, 53)),
    ("WinError 161", lambda p: _windows_error(FileNotFoundError, errno.ENOENT, 161)),
    ("EACCES", _eacces),
    ("EIO", _eio),
]


@pytest.mark.parametrize(
    ("label", "make"), ORACLE_UNAVAILABLE_LISTINGS, ids=[c[0] for c in ORACLE_UNAVAILABLE_LISTINGS]
)
def test_fs_authority_a_listing_failure_is_never_absence(monkeypatch, sandbox: Path, label: str, make) -> None:
    """A retired path is proven absent only by a listing that succeeded; a failed listing proves nothing."""
    root = _fs_root(sandbox)
    _scandir_raises(monkeypatch, root / ".github", make)
    _names(failures(root), "retired control-plane path cannot be proven absent: " + ORACLE_RETIRED_PROBE)


def test_fs_authority_native_statuses(tmp_path: Path) -> None:
    (tmp_path / "f.md").write_text("x", encoding="utf-8")
    (tmp_path / "d").mkdir()
    ledger = validator.FileLedger(tmp_path)
    assert ledger.status("f.md").status == "PRESENT"
    assert ledger.status("absent.md").status == "MISSING"
    assert ledger.status("f.md/child.md").status == "MISSING"
    assert ledger.status("d/absent.md").status == "MISSING"
    directory = ledger.status("d")
    assert (directory.status, directory.kind) == ("NOT_A_FILE", "directory")


# --- STATIC_ANCESTOR_TRUST and the symbolic-link policy ----------------------------------------------------------


def test_fs_authority_native_symbolic_links_are_never_followed(tmp_path: Path) -> None:
    """Native: a file link, directory link, broken link and loop are never regular files, and never ancestors."""
    (tmp_path / "real.md").write_text("x", encoding="utf-8")
    (tmp_path / "real_dir").mkdir()
    (tmp_path / "real_dir" / "inner.md").write_text("x", encoding="utf-8")
    _symlink_or_skip(tmp_path / "real.md", tmp_path / "file_link.md")
    _symlink_or_skip(tmp_path / "real_dir", tmp_path / "dir_link", directory=True)
    _symlink_or_skip(tmp_path / "gone.md", tmp_path / "broken_link.md")
    _symlink_or_skip("loop_b", tmp_path / "loop_a")
    _symlink_or_skip("loop_a", tmp_path / "loop_b")
    ledger = validator.FileLedger(tmp_path)
    for name in ("file_link.md", "dir_link", "broken_link.md", "loop_a"):
        observed = ledger.status(name)
        assert (observed.status, observed.kind) == ("NOT_A_FILE", "symbolic link or junction"), (name, observed)
    through = ledger.status("dir_link/inner.md")
    assert through.status == "UNREADABLE" and "UNTRUSTED_ANCESTOR: dir_link" in through.reason, through


def test_fs_authority_native_directory_redirect_ancestor_is_untrusted(tmp_path: Path) -> None:
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "inner.md").write_text("x", encoding="utf-8")
    _directory_redirect_or_skip(tmp_path / "outside", tmp_path / "redirect")
    observed = validator.FileLedger(tmp_path).status("redirect/inner.md")
    assert observed.status == "UNREADABLE" and "UNTRUSTED_ANCESTOR: redirect" in observed.reason, observed


@pytest.mark.parametrize(
    "rel", ["docs", "docs/crypto_core/continuity"], ids=["canonical through docs", "continuity through its directory"]
)
def test_fs_authority_external_authority_through_a_redirected_ancestor_is_refused(
    sandbox: Path, tmp_path: Path, rel: str
) -> None:
    """P2-STATIC-ANCESTOR, native: the frozen candidate read authority bytes through a junction and PASSED."""
    external = tmp_path / "external"
    external.mkdir()
    shutil.move(str(sandbox / rel), str(external / "moved"))
    _directory_redirect_or_skip(external / "moved", sandbox / rel)
    found = failures(sandbox)
    _names(found, "UNTRUSTED_ANCESTOR: {} is a symbolic link or junction".format(rel))


ORACLE_ANCESTOR_SEAMS = [
    ("symbolic link", S_IFLNK | 0o777, 0),
    ("junction", S_IFDIR | 0o777, 0xA0000003),
]


@pytest.mark.parametrize(("label", "mode", "tag"), ORACLE_ANCESTOR_SEAMS, ids=[c[0] for c in ORACLE_ANCESTOR_SEAMS])
def test_fs_authority_a_linked_ancestor_is_untrusted_on_every_platform(
    monkeypatch, sandbox: Path, label: str, mode: int, tag: int
) -> None:
    _listing_fault(monkeypatch, "", "docs", {"fake_mode": mode, "tag": tag}, exact=sandbox)
    _names(
        failures(sandbox),
        "canonical authority unreadable: docs/crypto_core/agent_os_v2.md: UNTRUSTED_ANCESTOR: docs is a symbolic link",
    )


@pytest.mark.parametrize(("label", "make"), [("EACCES", _eacces), ("EIO", _eio)], ids=["EACCES", "EIO"])
def test_fs_authority_an_unclassifiable_ancestor_is_unreadable(monkeypatch, sandbox: Path, label: str, make) -> None:
    _entry_fault(monkeypatch, sandbox, "docs", make("docs"))
    _names(
        failures(sandbox),
        "canonical authority unreadable: docs/crypto_core/agent_os_v2.md: UNREADABLE_FILE: entry cannot be classified",
        ("canonical authority missing",),
    )


def test_fs_authority_a_linked_discovery_prefix_fails(monkeypatch, sandbox: Path) -> None:
    _listing_fault(monkeypatch, "", ".claude", {"fake_mode": S_IFLNK | 0o777}, exact=sandbox)
    assert_rejects(
        sandbox,
        "host auto-discovery location cannot be observed: .claude/skills (scanning .claude/skills/**/SKILL.md): "
        "UNTRUSTED_ANCESTOR: .claude",
    )


def test_fs_authority_native_symbolic_links_in_a_discovery_location_fail(tmp_path: Path) -> None:
    skills = tmp_path / ".claude" / "skills"
    (skills / "real").mkdir(parents=True)
    (skills / "real" / "SKILL.md").write_text("x", encoding="utf-8")
    _symlink_or_skip(skills / "real", skills / "linked", directory=True)
    _symlink_or_skip(skills / "gone.md", skills / "real" / "broken.md")
    found, problems = validator.discover_files(tmp_path, ".claude/skills/**/SKILL.md")
    assert found == [".claude/skills/real/SKILL.md"]
    joined = "\n".join(problems)
    assert "symbolic link or junction: .claude/skills/linked" in joined, joined
    assert "symbolic link or junction: .claude/skills/real/broken.md" in joined, joined


# --- category matrix through the real gate ----------------------------------------------------------------------

ORACLE_FS_MATRIX = {
    "canonical": (
        CANONICAL,
        "canonical authority unreadable: docs/crypto_core/agent_os_v2.md: UNREADABLE_FILE: entry cannot be classified",
        "canonical authority unreadable: docs/crypto_core/agent_os_v2.md: UNREADABLE_FILE: cannot be read",
        ("canonical authority missing",),
    ),
    "doctrine": (
        "CLAUDE.md",
        "CLAUDE.md: UNREADABLE_FILE: entry cannot be classified",
        "CLAUDE.md: UNREADABLE_FILE: cannot be read",
        ("active doctrine surface missing from the tree: CLAUDE.md",),
    ),
    "executable": (
        ORACLE_ORACLE_REL,
        "required control-plane artifact status cannot be proven: " + ORACLE_ORACLE_REL + ": UNREADABLE_FILE",
        ORACLE_ORACLE_REL + ": UNREADABLE_FILE: cannot be read",
        ("missing from the tree: " + ORACLE_ORACLE_REL, "independent contract oracle missing"),
    ),
    "historical host": (
        _ORACLE_HISTORICAL_RULE,
        _ORACLE_HISTORICAL_RULE + ": UNREADABLE_FILE: entry cannot be classified",
        _ORACLE_HISTORICAL_RULE + ": UNREADABLE_FILE: cannot be read",
        (),
    ),
    "committed schema": (
        _STRICT_SCHEMA_REL,
        _STRICT_SCHEMA_REL + ": STRICT_JSON_REJECTED: UNREADABLE_FILE: entry cannot be classified",
        _STRICT_SCHEMA_REL + ": STRICT_JSON_REJECTED: UNREADABLE_FILE: cannot be read",
        (_STRICT_SCHEMA_REL + ": missing",),
    ),
    "committed example": (
        _STRICT_EXAMPLE_REL,
        _STRICT_EXAMPLE_REL + ": STRICT_JSON_REJECTED: UNREADABLE_FILE: entry cannot be classified",
        _STRICT_EXAMPLE_REL + ": STRICT_JSON_REJECTED: UNREADABLE_FILE: cannot be read",
        (_STRICT_EXAMPLE_REL + ": missing",),
    ),
    "existence-only artifact": (
        ORACLE_EXISTENCE_ONLY,
        "required control-plane artifact status cannot be proven: .github/workflows/ci.yml: UNREADABLE_FILE",
        None,
        ("missing from the tree: .github/workflows/ci.yml",),
    ),
}
ORACLE_FS_CONTENT = [name for name, spec in ORACLE_FS_MATRIX.items() if spec[2] is not None]
_FS_STATUS_MATRIX = [
    (name, label, make) for name in ORACLE_FS_MATRIX for label, make in (("EACCES", _eacces), ("EIO", _eio))
]


@pytest.mark.parametrize(
    ("category", "label", "make"), _FS_STATUS_MATRIX, ids=["{} {}".format(c, lab) for c, lab, _ in _FS_STATUS_MATRIX]
)
def test_fs_authority_a_classification_fault_is_structured_and_never_missing(
    monkeypatch, sandbox: Path, category: str, label: str, make
) -> None:
    root = _fs_root(sandbox)
    rel, fragment, _read, missing = ORACLE_FS_MATRIX[category]
    _entry_fault(monkeypatch, root, rel, make(rel))
    _names(failures(root), fragment, missing)


_FS_READ_MATRIX = [
    (name, label, make)
    for name in ORACLE_FS_CONTENT
    for label, make in (("EACCES", _eacces), ("EIO", _eio), ("vanished after its status", _vanished))
]


@pytest.mark.parametrize(
    ("category", "label", "make"), _FS_READ_MATRIX, ids=["{} {}".format(c, lab) for c, lab, _ in _FS_READ_MATRIX]
)
def test_fs_authority_a_read_fault_after_a_good_status_is_unreadable(
    monkeypatch, sandbox: Path, category: str, label: str, make
) -> None:
    root = _fs_root(sandbox)
    rel, _status, fragment, missing = ORACLE_FS_MATRIX[category]
    _open_fault(monkeypatch, rel, make)
    _names(failures(root), fragment, missing)


def test_fs_authority_an_existence_only_artifact_is_never_read(monkeypatch, sandbox: Path) -> None:
    root = _fs_root(sandbox)
    _open_fault(monkeypatch, ORACLE_EXISTENCE_ONLY, _eacces)
    assert failures(root) == []


ORACLE_FS_NOT_A_FILE = {
    "canonical": "canonical authority is not a regular file: docs/crypto_core/agent_os_v2.md (directory)",
    "doctrine": "CLAUDE.md: not a regular file (directory)",
    "executable": "required control-plane artifact is not a regular file: " + ORACLE_ORACLE_REL + " (directory)",
    "committed schema": _STRICT_SCHEMA_REL + ": STRICT_JSON_REJECTED: not a regular file (directory)",
    "committed example": _STRICT_EXAMPLE_REL + ": STRICT_JSON_REJECTED: not a regular file (directory)",
    "existence-only artifact": "required control-plane artifact is not a regular file: .github/workflows/ci.yml (directory)",
}


@pytest.mark.parametrize("category", sorted(ORACLE_FS_NOT_A_FILE))
def test_fs_authority_a_directory_where_a_file_is_required_is_named(sandbox: Path, category: str) -> None:
    rel, _status, _read, missing = ORACLE_FS_MATRIX[category]
    target = sandbox / rel
    target.unlink()
    target.mkdir()
    _names(failures(sandbox), ORACLE_FS_NOT_A_FILE[category], missing)


def test_fs_authority_a_retired_path_that_is_a_directory_is_still_present(sandbox: Path) -> None:
    (sandbox / ORACLE_RETIRED_PROBE).mkdir(parents=True)
    _names(failures(sandbox), "retired control-plane path still present in the tree: " + ORACLE_RETIRED_PROBE)


@pytest.mark.parametrize("category", ORACLE_FS_CONTENT)
def test_fs_authority_a_file_that_vanishes_after_its_one_status_fails_closed(
    monkeypatch, sandbox: Path, category: str
) -> None:
    root = _fs_root(sandbox)
    rel = ORACLE_FS_MATRIX[category][0]
    _open_fault(monkeypatch, rel, _vanished)
    found = failures(root)
    assert any(rel in item for item in found), "\n".join(found)


# --- ONE_OBSERVATION_SEMANTIC -------------------------------------------------------------------------------------


def test_fs_authority_every_directory_is_listed_once_and_no_path_is_stat_ed(monkeypatch, sandbox: Path) -> None:
    """Every repository decision comes from ONE listing per directory; no leaf status is ever taken beside it."""
    root = _fs_root(sandbox)
    inside = os.path.normcase(os.path.abspath(root))
    listed: list[str] = []
    stated: list[str] = []
    real_scandir = os.scandir

    def counting(path=".", *args, **kwargs):
        listed.append(os.path.normcase(os.path.abspath(os.fsdecode(path))))
        return real_scandir(path, *args, **kwargs)

    def recording(real_call):
        # Record rather than raise: an exception here would also fire inside pytest's own failure reporting.
        def observed(path, *args, **kwargs):
            if isinstance(path, (str, bytes, os.PathLike)):
                name = os.path.normcase(os.path.abspath(os.fsdecode(path)))
                if name == inside or name.startswith(inside + os.sep):
                    stated.append(name)
            return real_call(path, *args, **kwargs)

        return observed

    monkeypatch.setattr(os, "scandir", counting)
    monkeypatch.setattr(os, "stat", recording(os.stat))
    monkeypatch.setattr(os, "lstat", recording(os.lstat))
    found = failures(root)
    monkeypatch.undo()
    assert found == [], found
    assert stated == [], "a repository path was observed outside its directory listing: {}".format(stated)
    repeated = {path: listed.count(path) for path in set(listed) if listed.count(path) > 1}
    assert repeated == {}, repeated
    for rel in ("", "docs/crypto_core", "tests/crypto_core", ".github/workflows", "docs/crypto_core/continuity"):
        assert os.path.normcase(os.path.abspath(root / rel if rel else root)) in listed, rel


def test_fs_authority_the_bootstrap_oracle_keeps_its_one_observation(monkeypatch, sandbox: Path) -> None:
    """P2-BOOTSTRAP regression: the first classification fails and a later one would succeed; the failure stays."""
    root = _fs_root(sandbox)
    patch(root, CANONICAL, "- {}\n".format(ORACLE_ORACLE_REL), "")
    assert failures(root) == []
    _entry_fault(monkeypatch, root, ORACLE_ORACLE_REL, _eacces(ORACLE_ORACLE_REL), first_only=True)
    _names(
        failures(root),
        "independent contract oracle status cannot be proven: " + ORACLE_ORACLE_REL + ": UNREADABLE_FILE",
    )


def test_fs_authority_a_shared_ancestor_is_classified_once_for_every_descendant(monkeypatch, sandbox: Path) -> None:
    """The first classification of a shared ancestor fails and a later one would succeed: every path beneath it
    carries the retained failure - never one failing descendant beside passing siblings."""
    root = _fs_root(sandbox)
    ancestor = "docs/crypto_core/continuity"
    _entry_fault(monkeypatch, root, ancestor, _eacces(ancestor), first_only=True)
    found = failures(root)
    joined = "\n".join(found)
    for rel in (_STRICT_SCHEMA_REL, _STRICT_EXAMPLE_REL):
        assert any(rel in item and "entry cannot be classified" in item for item in found), "{}:\n{}".format(
            rel, joined
        )


def test_fs_authority_a_retained_failure_is_never_erased(tmp_path: Path) -> None:
    (tmp_path / "Real.md").write_text("x", encoding="utf-8")
    ledger = validator.FileLedger(tmp_path)
    first = ledger.status("real.md")
    assert first.status == "INVALID_PATH" and "case alias" in first.reason, first
    _rename_case(tmp_path / "Real.md", "real.md")
    assert ledger.status("real.md") is first
    assert ledger.text("real.md").status == "INVALID_PATH"


# --- ONE_DISCOVERY_BOUNDARY ---------------------------------------------------------------------------------------


def _plant_rogue(root: Path, name: str = "SKILL.md") -> None:
    rogue = root / ORACLE_ROGUE_DIR / name
    rogue.parent.mkdir(parents=True, exist_ok=True)
    rogue.write_text("# rogue\n", encoding="utf-8", newline="\n")


def test_fs_authority_discovery_refuses_a_planted_host_surface(sandbox: Path) -> None:
    _plant_rogue(sandbox)
    assert_rejects(sandbox, "host auto-discovery surface present but not registered: " + ORACLE_ROGUE)


ORACLE_CLASSIFICATION_FAULTS = [
    (
        "DirEntry.stat raises",
        {"stat_error": PermissionError(errno.EACCES, "injected")},
        "entry cannot be classified: " + ORACLE_ROGUE_DIR,
    ),
    ("DirEntry.is_dir raises", {"is_dir_error": PermissionError(errno.EACCES, "injected")}, None),
    ("DirEntry.is_file raises", {"is_file_error": OSError(errno.EIO, "injected")}, None),
    ("DirEntry.is_symlink raises", {"is_symlink_error": OSError(errno.EIO, "injected")}, None),
    (
        "DirEntry reports a symbolic link",
        {"fake_mode": S_IFLNK | 0o777},
        "symbolic link or junction: " + ORACLE_ROGUE_DIR,
    ),
    (
        "DirEntry reports a junction",
        {"fake_mode": S_IFDIR | 0o777, "tag": 0xA0000003},
        "symbolic link or junction: " + ORACLE_ROGUE_DIR,
    ),
]


@pytest.mark.parametrize(
    ("label", "behaviour", "fragment"), ORACLE_CLASSIFICATION_FAULTS, ids=[c[0] for c in ORACLE_CLASSIFICATION_FAULTS]
)
def test_fs_authority_an_unclassifiable_directory_never_hides_its_descendants(
    monkeypatch, sandbox: Path, label: str, behaviour: dict, fragment
) -> None:
    _plant_rogue(sandbox)
    _listing_fault(monkeypatch, ".claude/skills", "zz-oracle-rogue", behaviour)
    found = failures(sandbox)
    assert found, "an unclassifiable discovery entry was accepted"
    if fragment is None:
        joined = "\n".join(found)
        assert ORACLE_ROGUE_DIR in joined, joined
    else:
        _names(found, fragment)


_FS_LISTING = [
    (where, label, make)
    for where in (".claude/skills", ORACLE_ROGUE_DIR)
    for label, make in (("EACCES", _eacces), ("EIO", _eio))
]


@pytest.mark.parametrize(
    ("where", "label", "make"), _FS_LISTING, ids=["{} {}".format(w, lab) for w, lab, _ in _FS_LISTING]
)
def test_fs_authority_an_unlistable_discovery_location_fails(
    monkeypatch, sandbox: Path, where: str, label: str, make
) -> None:
    _plant_rogue(sandbox)
    _scandir_raises(monkeypatch, sandbox / where, make)
    assert_rejects(sandbox, "host auto-discovery location cannot be listed: {} (scanning".format(where))


def test_fs_authority_an_iteration_error_during_listing_fails(monkeypatch, sandbox: Path) -> None:
    _plant_rogue(sandbox)
    _listing_fault(monkeypatch, ".claude/skills", iteration_error=OSError(errno.EIO, "injected"))
    assert_rejects(sandbox, "host auto-discovery location cannot be listed: .claude/skills (scanning")


def test_fs_authority_a_matching_special_file_fails(monkeypatch, sandbox: Path) -> None:
    _plant_rogue(sandbox)
    _listing_fault(monkeypatch, ORACLE_ROGUE_DIR, "SKILL.md", {"fake_mode": ORACLE_FIFO_MODE})
    assert_rejects(
        sandbox,
        "host auto-discovery entry " + ORACLE_ROGUE + " (matched .claude/skills/**/SKILL.md) is not a regular file",
    )


def test_fs_authority_an_entry_outside_the_portable_domain_fails(monkeypatch, sandbox: Path) -> None:
    name = "zz" + chr(0xDC80)
    _listing_fault(monkeypatch, ".claude/skills", extras=[(name, S_IFDIR | 0o755, 0)])
    assert_rejects(sandbox, "is outside the portable path domain")


@pytest.mark.parametrize(
    ("pattern", "path", "matches"),
    ORACLE_GLOB_MATCHES,
    ids=["{} vs {}".format(pattern, path) for pattern, path, _m in ORACLE_GLOB_MATCHES],
)
def test_fs_authority_discovery_lists_what_the_scan_glob_meaning_lists(
    tmp_path: Path, pattern: str, path: str, matches: bool
) -> None:
    target = tmp_path / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("x", encoding="utf-8")
    found, problems = validator.discover_files(tmp_path, pattern)
    assert problems == []
    assert (path in found) is matches


# --- ONE_PATH_IDENTITY --------------------------------------------------------------------------------------------


def test_fs_authority_path_identity_is_nfc_and_case_folded() -> None:
    assert validator.path_identity("SKILL.md") == validator.path_identity("skill.md")
    assert validator.path_identity("e" + chr(0x301) + ".md") == validator.path_identity(chr(0xE9) + ".md")
    assert validator.path_identity("a.md") != validator.path_identity("b.md")


def test_fs_authority_a_case_alias_host_surface_is_discovered(sandbox: Path) -> None:
    """P2-NATIVE-CASE: `skill.md` is loaded as `SKILL.md` by a case-insensitive host, and used to stay invisible."""
    _plant_rogue(sandbox, "skill.md")
    assert_rejects(sandbox, "host auto-discovery surface present but not registered: " + ORACLE_ROGUE_DIR + "/skill.md")


def test_fs_authority_a_case_alias_of_a_registered_discovered_surface_fails(sandbox: Path) -> None:
    registered = sandbox / ".claude/skills/crypto-core-token-efficient-loop/SKILL.md"
    _rename_case(registered, "Skill.md")
    found = failures(sandbox)
    _names(
        found,
        "host auto-discovery surface .claude/skills/crypto-core-token-efficient-loop/Skill.md is a case alias of the "
        "registered .claude/skills/crypto-core-token-efficient-loop/SKILL.md",
    )
    _names(found, ".claude/skills/crypto-core-token-efficient-loop/SKILL.md: INVALID_PATH: case alias")


def test_fs_authority_a_case_alias_of_a_registered_leaf_fails_on_every_platform(sandbox: Path) -> None:
    _rename_case(sandbox / "CLAUDE.md", "claude.md")
    _names(
        failures(sandbox),
        "CLAUDE.md: INVALID_PATH: case alias",
        ("active doctrine surface missing from the tree: CLAUDE.md",),
    )


def test_fs_authority_a_case_alias_in_an_ancestor_fails_on_every_platform(sandbox: Path) -> None:
    _rename_case(sandbox / "docs", "Docs")
    _names(
        failures(sandbox), "canonical authority unreadable: docs/crypto_core/agent_os_v2.md: INVALID_PATH: case alias"
    )


def test_fs_authority_a_case_collision_fails_on_every_platform(monkeypatch, sandbox: Path) -> None:
    _listing_fault(monkeypatch, "", extras=[("claude.md", ORACLE_FILE_MODE, 0)], exact=sandbox)
    _names(failures(sandbox), "CLAUDE.md: INVALID_PATH: case collision")


def test_fs_authority_a_case_collision_in_a_discovery_location_fails(monkeypatch, sandbox: Path) -> None:
    _plant_rogue(sandbox)
    _listing_fault(monkeypatch, ORACLE_ROGUE_DIR, extras=[("skill.md", ORACLE_FILE_MODE, 0)])
    assert_rejects(sandbox, "host auto-discovery location " + ORACLE_ROGUE_DIR + " holds a case collision")


def test_fs_authority_registries_cannot_name_one_identity_twice(sandbox: Path) -> None:
    patch(
        sandbox,
        CANONICAL,
        "<!-- RETIRED_CONTROL_PLANE_PATHS_BEGIN -->\n",
        "<!-- RETIRED_CONTROL_PLANE_PATHS_BEGIN -->\n- claude.md\n",
    )
    assert_rejects(
        sandbox, "the registries name one path identity in more than one spelling: ['CLAUDE.md', 'claude.md']"
    )


# --- HOST_EXECUTABLE_WORKFLOW_CLOSED_WORLD -------------------------------------------------------------------------


def test_workflow_registry_matches_the_oracle() -> None:
    text = (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig")
    assert (
        dict(validator.parse_surface_registry(text, "HOST_EXECUTABLE_WORKFLOWS") or [])
        == ORACLE_HOST_EXECUTABLE_WORKFLOWS
    )
    assert ".github/workflows/ci.yml" not in (validator.parse_registry(text, "HOST_NON_DISCOVERY_PATHS") or [])


def test_workflow_every_committed_workflow_is_classified() -> None:
    committed = sorted(".github/workflows/" + name for name in os.listdir(REPO_ROOT / ".github" / "workflows"))
    assert committed == sorted(ORACLE_HOST_EXECUTABLE_WORKFLOWS)


def _workflows(root: Path) -> Path:
    return root / ".github" / "workflows"


ORACLE_WORKFLOW_BODY = "name: rogue\non: pull_request\njobs: {}\n"


def _add_workflow(name: str):
    def mutate(root: Path) -> None:
        (_workflows(root) / name).write_text(ORACLE_WORKFLOW_BODY, encoding="utf-8", newline="\n")

    return mutate


def _remove_workflow(root: Path) -> None:
    (_workflows(root) / "deribit-public-smoke.yml").unlink()


def _rename_to_yaml(root: Path) -> None:
    (_workflows(root) / "deribit-public-smoke.yml").rename(_workflows(root) / "deribit-public-smoke.yaml")


def _alias_workflow(root: Path) -> None:
    _rename_case(_workflows(root) / "deribit-public-smoke.yml", "Deribit-Public-Smoke.yml")


def _nest_workflow(root: Path) -> None:
    (_workflows(root) / "nested").mkdir()
    (_workflows(root) / "nested" / "inner.yml").write_text(ORACLE_WORKFLOW_BODY, encoding="utf-8", newline="\n")


ORACLE_WORKFLOW_MUTATIONS = [
    ("unregistered rogue.yml", _add_workflow("rogue.yml"), ["unregistered workflow file: .github/workflows/rogue.yml"]),
    (
        "unregistered rogue.yaml",
        _add_workflow("rogue.yaml"),
        ["unregistered workflow file: .github/workflows/rogue.yaml"],
    ),
    ("a non-workflow file", _add_workflow("README.md"), ["unregistered workflow file: .github/workflows/README.md"]),
    (
        "a registered workflow removed",
        _remove_workflow,
        ["registered workflow .github/workflows/deribit-public-smoke.yml is not present as a regular file: missing"],
    ),
    (
        "a registered workflow renamed to .yaml",
        _rename_to_yaml,
        [
            "registered workflow .github/workflows/deribit-public-smoke.yml is not present as a regular file: missing",
            "unregistered workflow file: .github/workflows/deribit-public-smoke.yaml",
        ],
    ),
    (
        "a case alias of a registered workflow",
        _alias_workflow,
        [
            "workflow location entry .github/workflows/Deribit-Public-Smoke.yml is a case alias of the registered "
            "workflow .github/workflows/deribit-public-smoke.yml",
            "registered workflow .github/workflows/deribit-public-smoke.yml is not present as a regular file: "
            "INVALID_PATH: case alias",
        ],
    ),
    ("a subdirectory", _nest_workflow, ["workflow location entry .github/workflows/nested is a directory"]),
]


@pytest.mark.parametrize(
    ("label", "mutate", "needles"), ORACLE_WORKFLOW_MUTATIONS, ids=[case[0] for case in ORACLE_WORKFLOW_MUTATIONS]
)
def test_workflow_location_is_closed_world(sandbox: Path, label: str, mutate, needles: list[str]) -> None:
    """P1-WORKFLOW-DISCOVERY: an unregistered workflow and an undeclared rename used to PASS."""
    assert failures(sandbox) == []
    mutate(sandbox)
    found = failures(sandbox)
    for needle in needles:
        _names(found, needle)


ORACLE_WORKFLOW_SHAPES = [
    ("a case collision", "CI.yml", ORACLE_FILE_MODE, 0, "workflow location .github/workflows holds a case collision"),
    (
        "a symbolic link",
        "linked.yml",
        S_IFLNK | 0o777,
        0,
        "workflow location entry .github/workflows/linked.yml is a symbolic link or junction",
    ),
    (
        "a junction",
        "junction.yml",
        S_IFDIR | 0o777,
        0xA0000003,
        "workflow location entry .github/workflows/junction.yml is a symbolic link or junction",
    ),
    (
        "a special file",
        "fifo.yml",
        ORACLE_FIFO_MODE,
        0,
        "workflow location entry .github/workflows/fifo.yml is a special file",
    ),
]


@pytest.mark.parametrize(
    ("label", "name", "mode", "tag", "needle"), ORACLE_WORKFLOW_SHAPES, ids=[case[0] for case in ORACLE_WORKFLOW_SHAPES]
)
def test_workflow_location_refuses_every_unexpected_shape(
    monkeypatch, sandbox: Path, label: str, name: str, mode: int, tag: int, needle: str
) -> None:
    _listing_fault(monkeypatch, ".github/workflows", extras=[(name, mode, tag)])
    assert_rejects(sandbox, needle)


ORACLE_WORKFLOW_REGISTRY_MUTATIONS = [
    (
        "an entry outside the workflow location",
        "- .github/workflows/ci.yml :: CONTROL_PLANE_CI\n",
        "- .github/workflows/ci.yml :: CONTROL_PLANE_CI\n- .github/scripts/x.yml :: PUBLIC_SMOKE_NO_READINESS\n",
        "entry .github/scripts/x.yml is not an immediate .yml or .yaml file of .github/workflows",
    ),
    (
        "an entry with another suffix",
        "- .github/workflows/ci.yml :: CONTROL_PLANE_CI\n",
        "- .github/workflows/ci.yml :: CONTROL_PLANE_CI\n- .github/workflows/x.txt :: PUBLIC_SMOKE_NO_READINESS\n",
        "entry .github/workflows/x.txt is not an immediate .yml or .yaml file of .github/workflows",
    ),
    (
        "an unknown class",
        "- .github/workflows/deribit-public-smoke.yml :: PUBLIC_SMOKE_NO_READINESS\n",
        "- .github/workflows/deribit-public-smoke.yml :: LIVE_TRADING\n",
        "classifies .github/workflows/deribit-public-smoke.yml as 'LIVE_TRADING'",
    ),
    (
        "a second control-plane CI workflow",
        "- .github/workflows/deribit-public-smoke.yml :: PUBLIC_SMOKE_NO_READINESS\n",
        "- .github/workflows/deribit-public-smoke.yml :: CONTROL_PLANE_CI\n",
        "must classify exactly one CONTROL_PLANE_CI workflow",
    ),
]


@pytest.mark.parametrize(
    ("label", "old", "new", "needle"),
    ORACLE_WORKFLOW_REGISTRY_MUTATIONS,
    ids=[case[0] for case in ORACLE_WORKFLOW_REGISTRY_MUTATIONS],
)
def test_workflow_registry_rules_fail_closed(sandbox: Path, label: str, old: str, new: str, needle: str) -> None:
    patch(sandbox, CANONICAL, old, new)
    assert_rejects(sandbox, needle)


def test_workflow_registration_grants_no_authority_and_is_documented() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    for token in (
        "HOST_EXECUTABLE_WORKFLOW_CLOSED_WORLD",
        "A registration grants ZERO Agent OS authority",
        "it does not reopen MT4",
        "it implies no Deribit readiness and no live authorization",
        "GitHub discovers every workflow file",
    ):
        assert token in canonical, token
    for path in ORACLE_HOST_EXECUTABLE_WORKFLOWS:
        assert path not in ORACLE_ACTIVE_DOCTRINE_SURFACES, path


# --- structural single authority ---------------------------------------------------------------------------------


def _functions(source: str) -> list[ast.FunctionDef]:
    return [node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef)]


def test_fs_authority_is_the_single_filesystem_authority() -> None:
    """STRUCTURAL: only the authority touches the filesystem or handles a filesystem or path-encoding error."""
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    touching: set[str] = set()
    handling: set[str] = set()
    for function in _functions(source):
        for node in ast.walk(function):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute) and node.func.attr in ORACLE_FS_CALLS:
                    touching.add(function.name)
                if isinstance(node.func, ast.Name) and node.func.id == "open":
                    touching.add(function.name)
            if isinstance(node, ast.ExceptHandler) and node.type is not None:
                names = {name.id for name in ast.walk(node.type) if isinstance(name, ast.Name)}
                if names & (ORACLE_FS_ERRORS - {"ValueError"}):
                    handling.add(function.name)
                if "ValueError" in names and function.name in ORACLE_FS_HANDLING_FUNCTIONS:
                    handling.add(function.name + " (ValueError)")
    assert touching == ORACLE_FS_TOUCHING_FUNCTIONS, touching
    assert handling <= ORACLE_FS_HANDLING_FUNCTIONS, handling
    for retired in (
        "def file_status",
        "def read_file",
        "class FileAccess",
        "_ABSENT_ERRNOS",
        "os.walk(",
        ".glob(",
        "os.lstat(",
    ):
        assert retired not in source, retired


def test_fs_authority_path_identity_is_the_single_case_policy() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    folding = {
        function.name
        for function in _functions(source)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "casefold"
    }
    assert folding == {"path_identity"}, folding


def test_workflow_inventory_is_the_single_workflow_registry() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    assert source.count('".github/workflows"') == 1
    assert source.count('".github/workflows/ci.yml"') == 1
    assert source.count("BLOCK_HOST_WORKFLOWS = ") == 1


# --- doctrine and CI -----------------------------------------------------------------------------------------------


def test_fs_authority_and_the_replacement_doctrine_are_documented() -> None:
    canonical = _normalized(REPO_ROOT / CANONICAL)
    for token in (
        "FILESYSTEM_ACCESS_AUTHORITY",
        "ONE_PATH_VALIDATION_BOUNDARY",
        "ONE_FILE_STATUS_BOUNDARY",
        "STATIC_ANCESTOR_TRUST",
        "UNTRUSTED_ANCESTOR",
        "ONE_PATH_IDENTITY",
        "unpaired surrogate",
        "ONE_READ_DECODE_BOUNDARY",
        "ONE_DISCOVERY_BOUNDARY",
        "ONE_OBSERVATION_SEMANTIC",
        "INVALID_PATH",
        "UNREADABLE_FILE",
        "UNREADABLE_TEXT",
        "never reported as missing",
        "HOST_UI_LABELS_ARE_LITERAL",
        "xhighultracode",
        "LARGEST_SAFE_SEMANTIC_CLOSURE",
        "CLEAN_REPLACEMENT_CYCLE",
        "execution environment and specialist lane",
        "never a governance authority",
        "never becomes canonical state",
        "Fresh proof overrides a stale handoff",
    ):
        assert token in canonical, token
    for field in (
        "TARGET_END_STATE",
        "DEPENDENCY_GRAPH",
        "SEMANTIC_CONTRACTS",
        "PROTECTED_BOUNDARIES",
        "EXPECTED_PR_SEQUENCE",
        "MERGE_ORDER",
        "EXIT_CRITERIA",
        "ROLLBACK_BOUNDARY",
    ):
        assert "`{}`".format(field) in canonical, field
    for stale in ("CAPABILITY_OBJECTIVE", "MILESTONE_PR_MAP", "preparation, research and synthesis lane"):
        assert stale not in canonical, stale


def test_fs_authority_ci_runs_one_pytest_pass_with_headroom() -> None:
    workflow = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    tests_job = workflow.split("\n  slow-tests:", 1)[0]
    assert tests_job.count("python -m pytest") == 1, "the tests job must run the suite once"
    assert "--cov-fail-under=70" in tests_job and "-W error" in tests_job
    minutes = [
        int(line.split(":", 1)[1]) for line in tests_job.splitlines() if line.strip().startswith("timeout-minutes:")
    ]
    assert minutes and minutes[0] >= 30, minutes
    assert "if: github.event_name == 'schedule'" in workflow.split("\n  slow-tests:", 1)[1].split("\n  codeql:", 1)[0]
    assert "needs: tests" in workflow.split("\n  codeql:", 1)[1]


# --- STRICT JSON: the top-level document type -------------------------------------------------------------------

ORACLE_NON_OBJECT_DOCUMENTS = [
    ("[]", []),
    ("[1]", [1]),
    ('"x"', "x"),
    ("1", 1),
    ("1.5", 1.5),
    ("true", True),
    ("null", None),
]


@pytest.mark.parametrize(
    ("text", "value"), ORACLE_NON_OBJECT_DOCUMENTS, ids=[case[0] for case in ORACLE_NON_OBJECT_DOCUMENTS]
)
def test_strict_json_a_manifest_that_is_not_a_json_object_is_rejected(tmp_path: Path, text: str, value: object) -> None:
    """J: the totality fuzz proves no exception; this proves the wrong top-level type is REFUSED, not merely survived."""
    assert "probe: a manifest must be a JSON object" in validator.check_manifest_instance("probe", value)
    compiled = tmp_path / "top.json"
    compiled.write_text(text, encoding="utf-8")
    found = validator.check_manifest_file(REPO_ROOT, compiled)
    assert any(item.endswith("a manifest must be a JSON object") for item in found), found


def test_strict_json_a_committed_example_that_is_not_an_object_is_rejected(sandbox: Path) -> None:
    write(sandbox, _STRICT_EXAMPLE_REL, "[]")
    assert_rejects(sandbox, _STRICT_EXAMPLE_REL + ": a manifest must be a JSON object")
