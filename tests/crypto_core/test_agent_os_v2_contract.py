"""Contract tests for the crypto_core Agent OS control plane.

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

import importlib.util
import json
import re
import shutil
from pathlib import Path

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
}

ORACLE_PROOF_PAIRED_MANIFEST_FIELDS = [
    "branch",
    "base_sha",
    "base_tree",
    "head_sha",
    "head_tree",
    "pr_number",
    "pr_state",
    "open_pr_count",
    "ci_state",
    "review_threads_unresolved",
    "completed_gates",
    "blockers",
    "openai_agentic_capacity",
    "claude_capacity",
    "capacity_routing_mode",
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

ORACLE_FRONTIER_LANE = "GPT-6 Astra"
ORACLE_FRONTIER_MODEL_ID = "gpt-6-astra"

ORACLE_RETIRED_PATH_COUNT = 43

# Surfaces that must never be reachable as control-plane doctrine: product, legacy and protected runtime.
ORACLE_FORBIDDEN_REGISTRY_PREFIXES = ("src/", "tests/services/", "tests/brain/", ".github/hooks/")

SANDBOX_FILES = sorted(set(ORACLE_ACTIVE_DOCTRINE_SURFACES) | ORACLE_REQUIRED_CONTROL_PLANE_ARTIFACTS)


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


def read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8-sig")


def write(root: Path, rel: str, text: str) -> None:
    (root / rel).write_text(text, encoding="utf-8", newline="\n")


def patch(root: Path, rel: str, old: str, new: str, *, count: int = 1) -> None:
    """Replace ``old`` with ``new``, proving the anchor was unique before mutating."""
    text = read(root, rel)
    assert text.count(old) == count, "sandbox anchor {!r} appeared {} times in {}".format(old, text.count(old), rel)
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
    injected = "Historically the Class-C audit ran on Codex GPT-5.6 Sol and surge work on Claude Fable 5.\n"
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
        "ROUTE: T3D | ARCHITECTURE | GPT-6 Astra | gpt-6-astra | max | READ_ONLY\n",
        "",
    )
    assert_rejects(sandbox, "MAX_EFFORT_CLASSES declares")


@pytest.mark.parametrize(
    ("lane", "model_id"),
    [
        ("GPT-5.6 Terra", "-"),
        ("GPT-5.6 Sol", "gpt-5-6-sol"),
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
    patch(sandbox, CANONICAL, "SELF_AUDIT_ONLY_NOT_INDEPENDENT", "SELF_REVIEW_IS_FINE")
    assert_rejects(sandbox, "SELF_AUDIT_ONLY_NOT_INDEPENDENT")


def test_astra_unavailable_stop_token_must_be_present(sandbox: Path) -> None:
    """Probe 34: without this token there is no named stop, so a silent downgrade becomes possible."""
    patch(sandbox, CANONICAL, "ASTRA_REQUIRED_BUT_UNAVAILABLE", "ASTRA_OPTIONAL")
    assert_rejects(sandbox, "ASTRA_REQUIRED_BUT_UNAVAILABLE")


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
            "ROUTE: T3D | ARCHITECTURE | GPT-6 Astra | gpt-6-astra | max | READ_ONLY",
            "ROUTE: T3D | ARCHITECTURE | GPT-6 Astra | gpt-6-astra | ultra | READ_ONLY",
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
    assert_rejects(sandbox, "HISTORICAL_RECORD_END without BEGIN")


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


def test_manifest_never_carries_merge_authority() -> None:
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
# CI wiring
# ---------------------------------------------------------------------------


def test_validator_runs_in_the_required_ci_job(sandbox: Path) -> None:
    patch(
        sandbox,
        ".github/workflows/ci.yml",
        "      - name: Agent OS control-plane contract\n        run: python scripts/crypto_core/validate_agent_os_v2.py\n\n",
        "",
    )
    assert_rejects(sandbox, "no enabled step in the 'tests' job executes")


def test_ci_job_detection_is_structural_not_positional(sandbox: Path) -> None:
    """Moving the gate into a different job must not satisfy the required job."""
    text = read(sandbox, ".github/workflows/ci.yml")
    step = (
        "      - name: Agent OS control-plane contract\n"
        "        run: python scripts/crypto_core/validate_agent_os_v2.py\n\n"
    )
    assert step in text
    text = text.replace(step, "", 1)
    text = text.replace(
        "  codeql:\n    name: codeql\n",
        "  codeql:\n    name: codeql\n    # " + step.strip().replace("\n", " ") + "\n",
        1,
    )
    write(sandbox, ".github/workflows/ci.yml", text)
    assert_rejects(sandbox, "no enabled step in the 'tests' job executes")


# ---------------------------------------------------------------------------
# Validator honesty
# ---------------------------------------------------------------------------


def test_validator_is_read_only_offline_and_stdlib_only() -> None:
    source = VALIDATOR_PATH.read_text(encoding="utf-8")
    for forbidden in ("subprocess", "requests", "urllib.request", "socket", "os.remove", "shutil.rmtree"):
        assert forbidden not in source, "validator must stay offline and read-only: found {}".format(forbidden)
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
    assert "$validatorExit = $LASTEXITCODE" in source


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
    """A deterministic failure must exit non-zero; the old script always exited 0."""
    body = _audit_source().split("#>", 1)[1]
    assert "exit $exitCode" in body
    assert "exit 0" not in body
    assert "$exitCode = 1" in body
    # Being unable to EXECUTE the gate is a failure, never a silent skip.
    assert "the control-plane contract could not be executed" in body


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


def test_proof_paired_registry_matches_the_oracle() -> None:
    registry = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "PROOF_PAIRED_MANIFEST_FIELDS"
    )
    assert registry == ORACLE_PROOF_PAIRED_MANIFEST_FIELDS


@pytest.mark.parametrize("field", ORACLE_PROOF_PAIRED_MANIFEST_FIELDS)
def test_every_registered_field_is_proof_paired_in_the_schema(field: str) -> None:
    schema = json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    )
    evidence = "{}_evidence".format(field)
    assert field in schema["properties"], field
    assert evidence in schema["properties"], evidence
    assert field in schema["required"]
    assert evidence in schema["required"]
    branches = [branch for branch in schema["allOf"] if evidence in (branch.get("if") or {}).get("properties", {})]
    assert len(branches) == 1, "expected exactly one proof-pair branch for {}".format(field)
    assert branches[0]["else"]["properties"][field]["type"] == "null"


@pytest.mark.parametrize("field", ["ci_state", "pr_state", "head_tree", "review_threads_unresolved"])
def test_dropping_a_proof_pair_constraint_is_rejected(sandbox: Path, field: str) -> None:
    """The exact reported defect: a live field carrying a value with no evidence relation."""
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, schema_path))
    evidence = "{}_evidence".format(field)
    schema["allOf"] = [b for b in schema["allOf"] if evidence not in b["if"]["properties"]]
    write(sandbox, schema_path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "no proof-pair constraint for registered field: {}".format(field))


def test_dropping_an_evidence_companion_is_rejected(sandbox: Path) -> None:
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, schema_path))
    del schema["properties"]["ci_state_evidence"]
    schema["required"] = [r for r in schema["required"] if r != "ci_state_evidence"]
    write(sandbox, schema_path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "has no companion: ci_state_evidence")


def test_proof_pair_constraint_for_an_unregistered_field_is_rejected(sandbox: Path) -> None:
    """Drift in the other direction: the schema constraining something the registry never claimed."""
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, schema_path))
    schema["allOf"].append(
        {
            "if": {"required": ["invented_evidence"], "properties": {"invented_evidence": {"const": "PROVEN"}}},
            "then": {"required": ["invented"], "properties": {"invented": {"type": "string"}}},
            "else": {"required": ["invented"], "properties": {"invented": {"type": "null"}}},
        }
    )
    write(sandbox, schema_path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "proof-pair constraint for unregistered field: invented")


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
# CI wiring must be an executable step, not a mention
# ---------------------------------------------------------------------------

_REAL_CI_STEP = (
    "      - name: Agent OS control-plane contract\n        run: python scripts/crypto_core/validate_agent_os_v2.py\n\n"
)


@pytest.mark.parametrize(
    ("label", "replacement"),
    [
        (
            "yaml comment only",
            "      # - name: Agent OS control-plane contract\n"
            "      #   run: python scripts/crypto_core/validate_agent_os_v2.py\n\n",
        ),
        (
            "shell comment inside a run block",
            "      - name: Agent OS control-plane contract\n"
            "        run: |\n"
            "          # python scripts/crypto_core/validate_agent_os_v2.py\n"
            "          echo skipped\n\n",
        ),
        (
            "step disabled with if false",
            "      - name: Agent OS control-plane contract\n"
            "        if: false\n"
            "        run: python scripts/crypto_core/validate_agent_os_v2.py\n\n",
        ),
        (
            "path only in the step name",
            "      - name: scripts/crypto_core/validate_agent_os_v2.py\n        run: echo skipped\n\n",
        ),
        ("step removed entirely", ""),
    ],
)
def test_ci_gate_requires_an_executable_step(sandbox: Path, label: str, replacement: str) -> None:
    """The exact reported defect: the path present without the gate actually running."""
    patch(sandbox, ".github/workflows/ci.yml", _REAL_CI_STEP, replacement)
    found = failures(sandbox)
    assert found, "the CI hard gate was defeated by: {}".format(label)
    assert any("no enabled step in the 'tests' job executes" in item for item in found), (
        "wrong rejection reason for {}: {}".format(label, found)
    )


def test_ci_gate_accepts_the_real_step_in_a_block_scalar(sandbox: Path) -> None:
    """A legitimate multi-line run block must still satisfy the gate."""
    patch(
        sandbox,
        ".github/workflows/ci.yml",
        _REAL_CI_STEP,
        "      - name: Agent OS control-plane contract\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        "          # the control-plane contract is a hard gate\n"
        "          python scripts/crypto_core/validate_agent_os_v2.py\n\n",
    )
    assert failures(sandbox) == []


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
    assert "ASTRA_REQUIRED_BUT_UNAVAILABLE" in flat
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


def test_ultra_is_never_an_effort_in_the_manifest_schema(sandbox: Path) -> None:
    schema_path = "docs/crypto_core/continuity/state_manifest.schema.json"
    schema = json.loads(read(sandbox, schema_path))
    schema["$defs"]["nullable_effort"]["anyOf"][0]["enum"].append("ultra")
    write(sandbox, schema_path, json.dumps(schema, indent=2))
    assert_rejects(sandbox, "Ultra must not appear in the reasoning-effort enum")


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
