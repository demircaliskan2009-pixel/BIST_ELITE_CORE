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
    "CAPABILITY_MODE",
    "HOST_SETTING_RAW",
    "MODEL_EVIDENCE_SOURCE",
    "NEXT_SAFE_ACTION",
}

# MEANINGFUL_VALUE_CLASS_REGISTRY_V1, declared literally here and never derived from the validator.
# Order matters: it is the registry order, so a silent reordering is visible too.
ORACLE_PROOF_PAIRED_MANIFEST_FIELDS = [
    ("branch", "NONEMPTY_STRING"),
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
    ("next_safe_action", "NONEMPTY_STRING"),
]

ORACLE_PROOF_PAIRED_FIELD_NAMES = [field for field, _class in ORACLE_PROOF_PAIRED_MANIFEST_FIELDS]

ORACLE_MEANINGFUL_VALUE_CLASSES = [
    "NONEMPTY_STRING",
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
    ".github/prompts/*.prompt.md",
]

# `max` legality is PER FAMILY. Written out literally so a relapse to a single-family restriction
# cannot be hidden by editing the canonical table alone.
ORACLE_MAX_EFFORT_FAMILY_INTENTS = {
    "T3B": {"IMPLEMENTATION", "REPAIR"},
    "T3D": {"ARCHITECTURE"},
    "T3E": {"PROMPT_ARCHITECTURE"},
    "T4": {"CLASS_C_CROSS_CONTRACT"},
}

# The exact command shapes the required CI job must run, and the oracle path anchored outside the
# mutable artifact registry.
ORACLE_CI_VALIDATOR_COMMAND = "python scripts/crypto_core/validate_agent_os_v2.py"
ORACLE_CI_ANCHOR_COMMAND = "test -f tests/crypto_core/test_agent_os_v2_contract.py"
ORACLE_BOOTSTRAP_PATH = "tests/crypto_core/test_agent_os_v2_contract.py"

ORACLE_FRONTIER_LANE = "GPT-6 Astra"
ORACLE_FRONTIER_MODEL_ID = "gpt-6-astra"

ORACLE_RETIRED_PATH_COUNT = 50

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


def contracts() -> dict:
    """Field contracts as the validator builds them, for BEHAVIOURAL probes.

    Independence is preserved by ORACLE_PROOF_PAIRED_MANIFEST_FIELDS above, which is literal and
    asserted separately; a behavioural probe still has to exercise the real contract to mean anything.
    """
    built, failures = validator.manifest_field_contracts(REPO_ROOT)
    assert failures == [], failures
    return built


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
    rows = validator.parse_registry(
        (REPO_ROOT / CANONICAL).read_text(encoding="utf-8-sig"), "PROOF_PAIRED_MANIFEST_FIELDS"
    )
    parsed = [tuple(part.strip() for part in row.split("::")) for row in rows or []]
    assert parsed == [tuple(row) for row in ORACLE_PROOF_PAIRED_MANIFEST_FIELDS]
    for _field, value_class in parsed:
        assert value_class in ORACLE_MEANINGFUL_VALUE_CLASSES, value_class


@pytest.mark.parametrize("field", ORACLE_PROOF_PAIRED_FIELD_NAMES)
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
    patch(sandbox, CANONICAL, "- T3B :: IMPLEMENTATION,REPAIR ::", "- T3B :: IMPLEMENTATION,REPAIR,REVIEW ::")
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


def test_every_declared_host_discovery_location_is_empty() -> None:
    for pattern in ORACLE_HOST_DISCOVERY_GLOBS:
        found = sorted(p.relative_to(REPO_ROOT).as_posix() for p in REPO_ROOT.glob(pattern) if p.is_file())
        assert found == [], "host auto-discovery location is not empty: {} -> {}".format(pattern, found)


@pytest.mark.parametrize(
    "rel",
    [
        ".github/agents/revived.agent.md",
        ".github/skills/revived-skill/SKILL.md",
        ".github/prompts/revived.prompt.md",
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


def test_committed_example_satisfies_the_relation_checker() -> None:
    """The fixture is validated by the same deterministic checker, never by prose inspection."""
    assert validator.manifest_relation_failures("example", _example(), contracts()) == []


@pytest.mark.parametrize(
    ("mutation", "needle"),
    [
        ({"ci_state": "GREEN", "ci_state_evidence": "UNKNOWN"}, "carries a value while"),
        ({"head_tree": None, "head_tree_evidence": "PROVEN"}, "is null while"),
        ({"next_safe_action": "MERGE", "next_safe_action_evidence": "UNKNOWN"}, "carries a value while"),
        ({"pr_state": "OPEN", "pr_state_evidence": "UNKNOWN"}, "carries a value while"),
    ],
)
def test_manifest_evidence_inversion_is_rejected(mutation: dict, needle: str) -> None:
    instance = _example()
    instance.update(mutation)
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    assert any(needle in f for f in found), found


def test_missing_runtime_proof_block_is_rejected() -> None:
    """Absence must never be a quieter way of saying UNKNOWN."""
    instance = _example()
    instance.pop("model_runtime")
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    assert any("model_runtime is missing" in f for f in found)


@pytest.mark.parametrize(
    ("source", "mutation", "should_fail"),
    [
        ("CONFIGURATION_EVIDENCE_ONLY", {"model_actual": "claude-opus-5"}, True),
        ("CONFIGURATION_EVIDENCE_ONLY", {"observed_effort": "xhigh"}, True),
        ("CONFIGURATION_EVIDENCE_ONLY", {}, False),
        ("UNKNOWN", {"model_actual": "claude-opus-5"}, True),
        ("CONTRADICTED", {"model_actual": "claude-opus-5"}, True),
        ("RUNTIME_TELEMETRY", {}, True),
        ("RUNTIME_TELEMETRY", {"model_actual": "claude-opus-5"}, False),
        ("USER_ATTESTED_UI_SELECTION", {"model_actual": None, "host_setting_raw": None}, True),
        ("USER_ATTESTED_UI_SELECTION", {"host_setting_raw": "Extra High"}, False),
    ],
)
def test_runtime_evidence_class_constrains_what_may_be_populated(source, mutation, should_fail) -> None:
    instance = _example()
    instance["model_runtime"]["model_evidence_source"] = source
    instance["model_runtime"].update(mutation)
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    runtime_failures = [f for f in found if "model_" in f or "must not populate" in f]
    assert bool(runtime_failures) is should_fail, found


@pytest.mark.parametrize(
    ("openai", "claude", "mode", "legal"),
    [
        ("EXHAUSTED", "NORMAL", "CLAUDE_CONTINUITY", True),
        ("EXHAUSTED", "CRITICAL", "CLAUDE_CONTINUITY", True),
        ("NORMAL", "NORMAL", "CLAUDE_CONTINUITY", False),
        ("EXHAUSTED", "EXHAUSTED", "CLAUDE_CONTINUITY", False),
        ("NORMAL", "EXHAUSTED", "OPENAI_CONTINUITY", True),
        ("EXHAUSTED", "EXHAUSTED", "OPENAI_CONTINUITY", False),
        ("EXHAUSTED", "EXHAUSTED", "BOTH_EXHAUSTED_STOP", True),
        ("EXHAUSTED", "NORMAL", "BOTH_EXHAUSTED_STOP", False),
        ("NORMAL", "NORMAL", "QUALITY_OPTIMAL", True),
        ("CONSERVE", "NORMAL", "QUALITY_OPTIMAL", False),
        ("CONSERVE", "NORMAL", "CLAUDE_FIRST_CONSERVATION", True),
        ("NORMAL", "CONSERVE", "OPENAI_FIRST_CONSERVATION", True),
        ("NORMAL", "NORMAL", "CLAUDE_FIRST_CONSERVATION", False),
    ],
)
def test_capacity_routing_mode_must_match_the_proven_capacities(openai, claude, mode, legal) -> None:
    instance = _example()
    instance.update(
        {
            "openai_agentic_capacity": openai,
            "openai_agentic_capacity_evidence": "PROVEN",
            "claude_capacity": claude,
            "claude_capacity_evidence": "PROVEN",
            "capacity_routing_mode": mode,
            "capacity_routing_mode_evidence": "PROVEN",
        }
    )
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    capacity_failures = [f for f in found if "capacity_routing_mode" in f]
    assert bool(capacity_failures) is (not legal), found


def test_unknown_capacity_can_never_become_a_guessed_continuation_mode() -> None:
    """The reported inversion: a continuation mode chosen while the capacity it needs was unproven."""
    instance = _example()
    instance.update({"claude_capacity": None, "claude_capacity_evidence": "UNKNOWN"})
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    assert any("provider capacity is" in f and "UNKNOWN" in f for f in found), found


def test_manifest_never_carries_merge_authority_through_the_relation_checker() -> None:
    instance = _example()
    instance["authorization"]["merge_authorized"] = True
    found = validator.manifest_relation_failures("fixture", instance, contracts())
    assert any("merge_authorized must be false" in f for f in found)


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


def test_compiled_manifest_relations_are_reachable_for_a_real_manifest(tmp_path: Path) -> None:
    """The relations existed but ran only over the committed fixture, so a compiled operational
    manifest could satisfy the published schema while contradicting itself. They are now executable.
    """
    source = REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json"
    instance = json.loads(source.read_text(encoding="utf-8-sig"))
    assert instance["model_runtime"]["model_evidence_source"] == "CONFIGURATION_EVIDENCE_ONLY"
    assert instance["model_runtime"]["model_actual"] is None

    instance["model_runtime"]["model_actual"] = "claude-opus-5"
    compiled = tmp_path / "state_manifest.json"
    compiled.write_text(json.dumps(instance), encoding="utf-8")

    found = validator.check_manifest_file(REPO_ROOT, compiled)
    assert any("must not populate model_actual" in item for item in found), found


def test_committed_manifest_example_passes_the_reachable_checker() -> None:
    """The control: the committed fixture satisfies the same executable gate."""
    source = REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json"
    assert validator.check_manifest_file(REPO_ROOT, source) == []


def test_manifest_schema_states_it_is_not_sufficient_alone() -> None:
    """Literal and independent: the schema must not imply it can enforce cross-field relations."""
    text = (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.schema.json").read_text(encoding="utf-8-sig")
    assert "NECESSARY BUT NOT SUFFICIENT" in text
    assert "--manifest" in text


# ---------------------------------------------------------------------------
# K5 - MEANINGFUL_VALUE_CLASS_REGISTRY_V1
#
# Derived from the CLASS vocabulary, not from the fields a past review happened to name.
# `value is not None` answered a topology question while the contract asks an evidential
# one, and that gap applied to every proof-paired field at once.
# ---------------------------------------------------------------------------

_SEMANTICALLY_EMPTY = [
    ("empty string", ""),
    ("whitespace only", "   "),
    ("empty object", {}),
    ("boolean", True),
]


def _example_manifest() -> dict:
    return json.loads(
        (REPO_ROOT / "docs/crypto_core/continuity/state_manifest.example.json").read_text(encoding="utf-8-sig")
    )


def test_every_registered_field_declares_a_known_value_class() -> None:
    """A proof field cannot exist without saying HOW it is proven."""
    built = contracts()
    assert sorted(built) == sorted(ORACLE_PROOF_PAIRED_FIELD_NAMES)
    for field, value_class in ORACLE_PROOF_PAIRED_MANIFEST_FIELDS:
        assert built[field][0] == value_class, field


@pytest.mark.parametrize(
    ("field", "value_class"),
    ORACLE_PROOF_PAIRED_MANIFEST_FIELDS,
    ids=[f"{f}:{c}" for f, c in ORACLE_PROOF_PAIRED_MANIFEST_FIELDS],
)
@pytest.mark.parametrize(("label", "empty"), _SEMANTICALLY_EMPTY, ids=[c[0] for c in _SEMANTICALLY_EMPTY])
def test_semantically_empty_values_are_never_proof(field: str, value_class: str, label: str, empty: object) -> None:
    """The whole category, every field at once - not the three a review happened to name."""
    instance = _example_manifest()
    instance[field] = empty
    instance["{}_evidence".format(field)] = "PROVEN"
    found = validator.manifest_relation_failures("probe", instance, contracts())
    assert [item for item in found if field in item], "{} accepted {} as PROVEN".format(field, label)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("open_pr_count", 0),
        ("review_threads_unresolved", 0),
        ("completed_gates", []),
        ("blockers", []),
    ],
    ids=["zero open PRs", "zero unresolved threads", "no completed gates", "no blockers"],
)
def test_legitimately_empty_facts_remain_provable(field: str, value: object) -> None:
    """The control that forbids a blanket truthiness predicate: zero and [] are real facts."""
    instance = _example_manifest()
    instance[field] = value
    instance["{}_evidence".format(field)] = "PROVEN"
    found = validator.manifest_relation_failures("probe", instance, contracts())
    assert not [item for item in found if field in item], found


@pytest.mark.parametrize(
    ("label", "value", "accepted"),
    [
        ("lowercase", "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678", True),
        ("uppercase", "A1B2C3D4E5F60718293A4B5C6D7E8F9012345678", True),
        ("mixed case", "a1B2c3D4e5F60718293a4B5c6D7e8F9012345678", True),
        ("too short", "a1b2c3d", False),
        ("non hex", "z1b2c3d4e5f60718293a4b5c6d7e8f9012345678", False),
        ("padded", " a1b2c3d4e5f60718293a4b5c6d7e8f9012345678 ", False),
    ],
    ids=["lowercase", "uppercase", "mixed case", "too short", "non hex", "padded"],
)
def test_hash_identifier_accepts_any_letter_case_and_nothing_malformed(label: str, value: str, accepted: bool) -> None:
    """Git accepts object ids in any case; a lowercase-only rule was itself a bypass."""
    instance = _example_manifest()
    instance["head_sha"] = value
    instance["head_sha_evidence"] = "PROVEN"
    found = [
        item for item in validator.manifest_relation_failures("probe", instance, contracts()) if "head_sha" in item
    ]
    assert (not found) is accepted, "{}: {}".format(label, found)


def test_meaningful_value_predicates_are_total() -> None:
    """No JSON shape may raise. A forged value produces a reason, never an exception."""
    built = contracts()
    shapes = [None, True, False, 0, 1, -1, 1.5, "", "  ", "x", [], [1], {}, {"a": 1}, [{"a": 1}]]
    for field in built:
        for value in shapes:
            for evidence in ("PROVEN", "UNKNOWN", "", None, 7):
                instance = _example_manifest()
                instance[field] = value
                instance["{}_evidence".format(field)] = evidence
                validator.manifest_relation_failures("fuzz", instance, built)


@pytest.mark.parametrize(
    ("source", "actual", "host_raw", "accepted"),
    [
        ("RUNTIME_TELEMETRY", "claude-opus-5", None, True),
        ("RUNTIME_TELEMETRY", "", None, False),
        ("RUNTIME_TELEMETRY", "   ", None, False),
        ("USER_ATTESTED_UI_SELECTION", None, "Max", True),
        ("USER_ATTESTED_UI_SELECTION", "", "   ", False),
        ("CONFIGURATION_EVIDENCE_ONLY", "claude-opus-5", None, False),
    ],
    ids=[
        "telemetry proven",
        "telemetry empty",
        "telemetry whitespace",
        "attested host",
        "attested empty",
        "config claims execution",
    ],
)
def test_runtime_evidence_requires_meaningful_values(
    source: str, actual: object, host_raw: object, accepted: bool
) -> None:
    """A configuration pin can never present itself as proven execution, and "" is not evidence."""
    instance = _example_manifest()
    instance["model_runtime"]["model_evidence_source"] = source
    instance["model_runtime"]["model_actual"] = actual
    instance["model_runtime"]["host_setting_raw"] = host_raw
    found = [
        item
        for item in validator.manifest_relation_failures("probe", instance, contracts())
        if "model_" in item or "attested" in item
    ]
    assert (not found) is accepted, found


@pytest.mark.parametrize(
    ("label", "authorization", "accepted"),
    [
        ("valid", {"mutation_scope": "the exact allowed files", "merge_authorized": False}, True),
        ("empty scope", {"mutation_scope": "   ", "merge_authorized": False}, False),
        ("merge authorized", {"mutation_scope": "x", "merge_authorized": True}, False),
        ("not an object", "NONE", False),
    ],
    ids=["valid", "empty scope", "merge authorized", "not an object"],
)
def test_authorization_block_requires_meaningful_proof(label: str, authorization: object, accepted: bool) -> None:
    instance = _example_manifest()
    instance["authorization"] = authorization
    found = [
        item
        for item in validator.manifest_relation_failures("probe", instance, contracts())
        if "authoriz" in item or "merge_auth" in item
    ]
    assert (not found) is accepted, found


def test_registry_class_must_be_known(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "- branch :: NONEMPTY_STRING", "- branch :: ANYTHING_GOES")
    assert_rejects(sandbox, "unknown value class")


def test_registry_class_must_agree_with_the_schema_shape(sandbox: Path) -> None:
    """The registry declares intent, the schema declares shape; drift between them fails."""
    patch(sandbox, CANONICAL, "- open_pr_count :: NONNEGATIVE_INT", "- open_pr_count :: NONEMPTY_STRING")
    assert_rejects(sandbox, "schema shape")


def test_registry_field_must_declare_a_class(sandbox: Path) -> None:
    patch(sandbox, CANONICAL, "- next_safe_action :: NONEMPTY_STRING", "- next_safe_action")
    assert failures(sandbox), "a classless proof field was accepted"


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


@pytest.mark.parametrize(
    ("label", "value", "meaningful"),
    [
        ("empty", "", False),
        ("spaces", "   ", False),
        ("tab and newline", "\t\n", False),
        ("non-breaking space", " ", False),
        ("zero-width space", "​", False),
        ("zero-width joiner", "‍", False),
        ("left-to-right mark", "‎", False),
        ("word joiner", "⁠", False),
        ("byte-order mark", "﻿", False),
        ("ideographic space", "　", False),
        ("ordinary text", "main", True),
        ("text containing a zero-width space", "ma​in", True),
        ("non-ascii text", "dal-ç", True),
    ],
    ids=[
        "empty",
        "spaces",
        "tab and newline",
        "non-breaking space",
        "zero-width space",
        "zero-width joiner",
        "left-to-right mark",
        "word joiner",
        "byte-order mark",
        "ideographic space",
        "ordinary text",
        "text containing a zero-width space",
        "non-ascii text",
    ],
)
def test_nonempty_string_requires_a_visible_character(label: str, value: str, meaningful: bool) -> None:
    """Closed over Unicode CATEGORY, not over a list of characters.

    `.strip()` alone let zero-width and format code points through: they survive stripping and
    render as nothing, so an invisible string could stand as proof. Requiring at least one
    character outside the control, format and separator categories covers every such code point,
    including ones not enumerated here, while leaving ordinary text untouched.
    """
    instance = _example_manifest()
    instance["branch"] = value
    instance["branch_evidence"] = "PROVEN"
    found = [item for item in validator.manifest_relation_failures("probe", instance, contracts()) if "branch" in item]
    assert (not found) is meaningful, "{}: {}".format(label, found)


# ---------------------------------------------------------------------------
# The documented manifest gate runs BOTH halves: schema shape and semantic relations
# ---------------------------------------------------------------------------


def _gate(tmp_path: Path, instance: object) -> list:
    compiled = tmp_path / "state_manifest.json"
    compiled.write_text(json.dumps(instance), encoding="utf-8")
    return validator.check_manifest_file(REPO_ROOT, compiled)


@pytest.mark.parametrize(
    "field",
    ["schema", "repo", "compiled_at_evidence", "task_boundary", "model_runtime", "authorization"],
)
def test_manifest_gate_rejects_a_missing_required_field(tmp_path: Path, field: str) -> None:
    """A gate that ran only the relations let an incomplete manifest through.

    The declared split is schema=shape, checker=relations. The GATE has to run both halves, or
    routing and audit can proceed from a manifest that never carried the facts at all.
    """
    instance = _example_manifest()
    instance.pop(field, None)
    assert _gate(tmp_path, instance), "a manifest missing {} passed the gate".format(field)


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("forbidden extra top-level key", lambda m: m.update({"surprise_key": "x"})),
        ("wrong schema constant", lambda m: m.update({"schema": "STATE_MANIFEST_V9"})),
        ("forbidden nested key", lambda m: m["model_runtime"].update({"nope": 1})),
        ("wrong nested item type", lambda m: m.update({"invalidations": [1]})),
        ("effort outside the enum", lambda m: m["model_runtime"].update({"requested_effort": "ultra"})),
    ],
    ids=[
        "forbidden extra top-level key",
        "wrong schema constant",
        "forbidden nested key",
        "wrong nested item type",
        "effort outside the enum",
    ],
)
def test_manifest_gate_enforces_the_schema_shape(tmp_path: Path, label: str, mutate) -> None:
    instance = _example_manifest()
    mutate(instance)
    assert _gate(tmp_path, instance), "the gate accepted: {}".format(label)


def test_manifest_gate_accepts_the_committed_example(tmp_path: Path) -> None:
    """The control: enforcing the shape must not reject the fixture the contract publishes."""
    assert _gate(tmp_path, _example_manifest()) == []


def test_structure_checker_fails_closed_on_an_unknown_construct() -> None:
    """Unrecognized schema constructs are failures, never silent passes.

    This is what stops the bounded reader from quietly degrading into "accept anything I do not
    understand", which is how a shape gate becomes decoration.
    """
    schema = {"type": "object", "properties": {"x": {"multipleOf": 3}}, "required": ["x"]}
    assert validator.manifest_structure_failures("probe", {"x": 9}, schema)


def test_merge_gate_never_accepts_a_skipped_required_check() -> None:
    """One surface still said "accepted skip" while the canonical protocol forbids it."""
    workflow_doc = _normalized(REPO_ROOT / "docs/crypto_core/agent_workflow.md")
    assert "accepted skip" not in workflow_doc
    assert "`skipped`, `neutral` or `cancelled` load-bearing check is never acceptance" in workflow_doc
