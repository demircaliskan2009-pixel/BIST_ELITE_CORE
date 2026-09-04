"""Permanent adversarial contract tests for the CRYPTO_CORE_AGENT_OS_V2 control plane.

These tests exercise real validator behavior, not static happy-path strings: the honest migrated
repository must pass, and every removed rail or reintroduced legacy/unsafe wording must fail.

The repository itself is never mutated. Negative cases run against a temporary clone of exactly the
file set the validator reads (``validator.SCANNED_FILES``).
"""

from __future__ import annotations

import importlib.util
import json
import re
import shutil
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
VALIDATOR_PATH = REPO_ROOT / "scripts" / "crypto_core" / "validate_agent_os_v2.py"


def _load_validator() -> ModuleType:
    spec = importlib.util.spec_from_file_location("validate_agent_os_v2", VALIDATOR_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load validator module from {VALIDATOR_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


validator = _load_validator()


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    """A read-only copy of every file the validator inspects. Mutating it never touches the repo."""
    root = tmp_path / "repo"
    for rel in validator.SCANNED_FILES:
        source = REPO_ROOT / rel
        if not source.is_file():
            continue
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return root


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text(encoding="utf-8")


def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _append_paragraph(root: Path, rel: str, paragraph: str) -> None:
    _write(root, rel, _read(root, rel) + "\n\n" + paragraph + "\n")


def _codes(violations: list[str]) -> set[str]:
    return {violation.split(":", 1)[0] for violation in violations}


# ---------------------------------------------------------------------------
# 1. Honest migrated repository passes
# ---------------------------------------------------------------------------


def test_honest_repository_passes() -> None:
    assert validator.validate(REPO_ROOT) == []


def test_clone_of_honest_repository_passes(clone: Path) -> None:
    assert validator.validate(clone) == []


def test_repository_files_are_never_mutated_by_the_clone(clone: Path) -> None:
    _append_paragraph(clone, "AGENTS.md", "Mutation confined to the temporary clone.")
    assert validator.validate(REPO_ROOT) == []


# ---------------------------------------------------------------------------
# 2. Missing canonical Agent OS V2 marker fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("surface", sorted(validator.CANONICAL_MARKERS))
def test_missing_canonical_marker_fails(clone: Path, surface: str) -> None:
    text = _read(clone, surface).replace("CRYPTO_CORE_AGENT_OS_V2", "CRYPTO_CORE_AGENT_OS_V1")
    _write(clone, surface, text)
    violations = validator.validate(clone)
    assert "C" in _codes(violations)
    assert any(surface in violation for violation in violations)


# ---------------------------------------------------------------------------
# 3. Reintroduced legacy surfaces fail
# ---------------------------------------------------------------------------


def test_reintroduced_legacy_system_instructions_fails(clone: Path) -> None:
    _write(clone, ".github/instructions/system.instructions.md", "# revived legacy control plane\n")
    violations = validator.validate(clone)
    assert "B" in _codes(violations)
    assert any(".github/instructions/system.instructions.md" in violation for violation in violations)


@pytest.mark.parametrize(
    "legacy_path",
    [
        ".github/prompts/crypto-pr-closeout.prompt.md",
        ".github/skills/crypto-scheduler/SKILL.md",
        ".github/hooks/hook-engine.md",
        "docs/crypto_core/CLAUDE_COLLABORATION_AND_PROJECT_GUIDE.md",
    ],
)
def test_reintroduced_legacy_path_fails(clone: Path, legacy_path: str) -> None:
    _write(clone, legacy_path, "# revived legacy surface\n")
    assert any(violation.startswith("B:") and legacy_path in violation for violation in validator.validate(clone))


# ---------------------------------------------------------------------------
# 4. Active Fable wording fails
# ---------------------------------------------------------------------------


def test_active_fable_wording_fails(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.AGENT_OS_V2_DOC,
        "Claude Fable 5 is an active premium surge lane and may be selected for heavy implementation.",
    )
    violations = validator.validate(clone)
    assert "D" in _codes(violations)


def test_retired_fable_wording_still_passes(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.AGENT_OS_V2_DOC,
        "Claude Fable 5 remains INACTIVE_EXPIRED_RETIRED and is never selected, never a fallback.",
    )
    assert validator.validate(clone) == []


def test_active_superseded_model_wording_fails(clone: Path) -> None:
    _append_paragraph(clone, "CLAUDE.md", "Claude Opus 4.8 is the default heavy executor for this repo.")
    assert "R" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# 5. Blanket autonomous mutation / restart-until-success wording fails
# ---------------------------------------------------------------------------


def test_restart_until_success_wording_fails(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.AGENT_OS_V2_DOC,
        "The executor should keep fixing until green and do everything automatically until CI is clean.",
    )
    assert "S" in _codes(validator.validate(clone))


def test_blanket_authority_wording_fails(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.COPILOT_SHIM,
        "The Copilot agent holds blanket GitHub authority and may merge when it thinks the PR is ready.",
    )
    assert _codes(validator.validate(clone)) & {"S", "U"}


def test_copilot_autonomous_executor_wording_fails(clone: Path) -> None:
    _append_paragraph(clone, validator.COPILOT_SHIM, "Copilot is an autonomous executor for crypto_core.")
    assert "E" in _codes(validator.validate(clone))


def test_copilot_shim_without_inactive_marker_fails(clone: Path) -> None:
    text = _read(clone, validator.COPILOT_SHIM).replace("INACTIVE_UNAVAILABLE", "ACTIVE_EXECUTION_LANE")
    _write(clone, validator.COPILOT_SHIM, text)
    assert "E" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# 6. State-manifest schema completeness
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["tree_sha", "open_pr_count", "model_runtime_proof", "invalidation_reasons"])
def test_removed_state_manifest_field_fails(clone: Path, field: str) -> None:
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    schema["properties"].pop(field, None)
    schema["required"] = [name for name in schema["required"] if name != field]
    _write(clone, validator.MANIFEST_SCHEMA, json.dumps(schema, indent=2))
    violations = validator.validate(clone)
    assert "N" in _codes(violations)
    assert any(field in violation for violation in violations)


def test_example_manifest_must_be_labelled_example_only(clone: Path) -> None:
    example = json.loads(_read(clone, validator.MANIFEST_EXAMPLE))
    example["example_only"] = False
    _write(clone, validator.MANIFEST_EXAMPLE, json.dumps(example, indent=2))
    assert "O" in _codes(validator.validate(clone))


def test_unparseable_example_manifest_fails(clone: Path) -> None:
    _write(clone, validator.MANIFEST_EXAMPLE, "{ not json ")
    assert "O" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# 7. Durable surfaces must not pin live state
# ---------------------------------------------------------------------------


def test_forbidden_start_sha_in_durable_continuity_fails(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.CONTINUITY_INDEX,
        f"Current main is pinned at {validator.FORBIDDEN_START_SHA} for all future sessions.",
    )
    violations = validator.validate(clone)
    assert "P" in _codes(violations)
    assert any(validator.FORBIDDEN_START_SHA in violation or "start SHA" in violation for violation in violations)


def test_any_durable_sha_pin_fails(clone: Path) -> None:
    _append_paragraph(clone, validator.CURRENT_STATE_DOC, "Merged at " + "a" * 7 + "1" * 33 + " last week.")
    assert "P" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# 8. Stale current-state wording fails
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "stale",
    [
        "Phase 16L Status: implemented, targeted tests pass.",
        "Implemented by Codex (GPT-5.5); rerun pytest on the Phase 16L branch.",
    ],
)
def test_stale_current_state_wording_fails(clone: Path, stale: str) -> None:
    _append_paragraph(clone, validator.CURRENT_STATE_DOC, stale)
    assert "Q" in _codes(validator.validate(clone))


def test_current_state_must_point_at_agent_os_v2(clone: Path) -> None:
    text = _read(clone, validator.CURRENT_STATE_DOC).replace("CRYPTO_CORE_AGENT_OS_V2", "the old protocol")
    _write(clone, validator.CURRENT_STATE_DOC, text)
    assert "Q" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# 9-13. Required rails cannot be removed
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("marker", "expected_code"),
    [
        ("BLOCKER_ESCAPE_PROTOCOL_V1", "J"),
        ("FIXED_POINT_STOP", "J"),
        ("EXPLICIT_HUMAN_MERGE_AUTHORIZATION", "H"),
        ("NO_SELF_APPROVAL", "V"),
        ("READINESS_AUTHORITY_NOT_INFERRED", "V"),
        ("SEMANTIC_BOUNDARY", "L"),
        ("PROMPT_COMPILER_V2", "L"),
        ("PROMPT_LANGUAGE_PROHIBITED", "L"),
        ("CHATGPT_WORK_LANE", "U"),
        ("WORK_LANE_BOUNDARIES", "U"),
        ("BLOCKER_ARTIFACT_MULTIPLICATION_PROHIBITED", "T"),
        ("CONTEXT_CONTINUITY_PROTOCOL_V1", "K"),
        ("ONE_REPOSITORY_WRITER", "F"),
        ("ONE_OPEN_PR", "G"),
        ("NO_DIRECT_MAIN_PUSH", "I"),
        ("MAX_SAFE_PR", "M"),
    ],
)
def test_removed_required_rail_fails(clone: Path, marker: str, expected_code: str) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace(marker, "REMOVED_RAIL")
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    violations = validator.validate(clone)
    assert expected_code in _codes(violations)
    assert any(marker in violation for violation in violations)


def test_removed_file_or_loc_sizing_prohibition_fails(clone: Path) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace(
        "never by file count, LOC count", "sized by file count and LOC count"
    )
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    assert "M" in _codes(validator.validate(clone))


def test_work_lane_converted_to_blanket_authority_fails(clone: Path) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace(
        "Work never\nreceives blanket write authority",
        "Work receives blanket write authority",
    )
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    assert "U" in _codes(validator.validate(clone))


@pytest.mark.parametrize(
    ("check_code", "phrase"),
    sorted((code, phrase) for code, phrases in validator.AGENT_OS_V2_REQUIRED_PHRASES.items() for phrase in phrases),
)
def test_removed_required_rule_phrase_fails(clone: Path, check_code: str, phrase: str) -> None:
    """A load-bearing rule cannot be deleted or inverted, even if the surrounding paragraph still hedges."""
    original = _read(clone, validator.AGENT_OS_V2_DOC)
    pattern = r"\s+".join(re.escape(word) for word in phrase.split())
    text, replaced = re.subn(pattern, "RULE_DELETED", original)
    if not replaced:
        pytest.fail(f"required phrase not present verbatim or line-wrapped: {phrase}")
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    violations = validator.validate(clone)
    assert check_code in _codes(violations)
    assert any(phrase in violation for violation in violations)


def test_removed_continuity_bootstrap_fails(clone: Path) -> None:
    text = _read(clone, validator.CONTINUITY_INDEX).replace("MODE=READ_ONLY", "MODE=WRITE")
    _write(clone, validator.CONTINUITY_INDEX, text)
    assert "K" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# Routing matrix integrity
# ---------------------------------------------------------------------------


def test_unsupported_routing_lane_fails(clone: Path) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace(
        validator.ROUTING_MATRIX_END,
        "| Autonomous Swarm Daemon | runs itself | everything | nothing |\n\n" + validator.ROUTING_MATRIX_END,
    )
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    violations = validator.validate(clone)
    assert "R" in _codes(violations)
    assert any("Autonomous Swarm Daemon" in violation for violation in violations)


def test_missing_routing_lane_fails(clone: Path) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace("| Codex GPT-5.6 Sol |", "| Codex Sol Renamed |")
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    violations = validator.validate(clone)
    assert "R" in _codes(violations)
    assert any("Codex GPT-5.6 Sol" in violation for violation in violations)


def test_missing_routing_matrix_block_fails(clone: Path) -> None:
    text = _read(clone, validator.AGENT_OS_V2_DOC).replace(validator.ROUTING_MATRIX_BEGIN, "")
    _write(clone, validator.AGENT_OS_V2_DOC, text)
    assert "R" in _codes(validator.validate(clone))


# ---------------------------------------------------------------------------
# Required files and exit code
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("required", sorted(validator.REQUIRED_FILES))
def test_missing_required_file_fails(clone: Path, required: str) -> None:
    (clone / required).unlink()
    violations = validator.validate(clone)
    assert any(violation.startswith("A:") and required in violation for violation in violations)


def test_main_returns_zero_on_the_honest_repository(capsys: pytest.CaptureFixture[str]) -> None:
    assert validator.main(["--repo-root", str(REPO_ROOT)]) == 0
    assert "AGENT_OS_V2_VALIDATION: PASS" in capsys.readouterr().out


def test_main_returns_nonzero_on_violation(clone: Path, capsys: pytest.CaptureFixture[str]) -> None:
    (clone / validator.AGENT_OS_V2_DOC).unlink()
    assert validator.main(["--repo-root", str(clone)]) == 1
    assert "AGENT_OS_V2_VALIDATION: FAIL" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# Regressions for the PR #371 independent-review findings
# ---------------------------------------------------------------------------

BIST_RUNTIME_HOOK_FILES = (
    ".github/hooks/pre-response.json",
    ".github/hooks/post-response.json",
)


@pytest.mark.parametrize("runtime_file", BIST_RUNTIME_HOOK_FILES)
def test_bist_runtime_hook_files_are_not_retired(runtime_file: str) -> None:
    """P1 regression: these are loaded by src/bist_core/hooks/hook_engine.py, not control-plane docs.

    Retiring them would make every run_pre_hooks / run_post_hooks call fail closed, so the validator must
    never demand their absence and they must still exist in the tree.
    """
    assert runtime_file not in validator.RETIRED_PATHS
    assert (REPO_ROOT / runtime_file).is_file()


def test_bist_hook_engine_still_reads_the_preserved_files() -> None:
    """The retirement decision stays bound to the actual runtime reader, not to a directory name."""
    engine = (REPO_ROOT / "src" / "bist_core" / "hooks" / "hook_engine.py").read_text(encoding="utf-8")
    for runtime_file in BIST_RUNTIME_HOOK_FILES:
        name = runtime_file.rsplit("/", 1)[-1]
        assert name in engine


def test_retired_hook_surface_is_documentation_only() -> None:
    retired_hooks = [path for path in validator.RETIRED_PATHS if path.startswith(".github/hooks/")]
    assert retired_hooks == [".github/hooks/hook-engine.md"]


def test_unrelated_negation_in_the_same_block_does_not_mask_a_reactivation(clone: Path) -> None:
    """P2 regression: the negation binds to the assertion, not to the blank-line block around it."""
    _append_paragraph(
        clone,
        validator.AGENT_OS_V2_DOC,
        "Claude Fable 5 is an active default executor. Copilot is never active.",
    )
    violations = validator.validate(clone)
    assert "D" in _codes(violations)
    assert any("active default executor" in violation for violation in violations)


def test_unrelated_negation_does_not_mask_blanket_authority(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.AGENT_OS_V2_DOC,
        "The implementer holds blanket GitHub authority. Deep Research is never an executor lane.",
    )
    assert "U" in _codes(validator.validate(clone))


def test_inventory_fence_is_rejected_outside_the_allowed_files(clone: Path) -> None:
    """The fence must not become a general escape hatch for reactivating a retired lane."""
    _append_paragraph(
        clone,
        validator.CONTINUITY_INDEX,
        f"{validator.INVENTORY_FENCE_BEGIN}\n\nanything at all\n\n{validator.INVENTORY_FENCE_END}",
    )
    violations = validator.validate(clone)
    assert any("inventory fence is not allowed" in violation for violation in violations)


def test_fenced_inventory_still_permits_the_prohibited_wording_list(clone: Path) -> None:
    """The honest repository keeps its prohibited-wording inventory and still passes."""
    doc = _read(clone, validator.AGENT_OS_V2_DOC)
    assert validator.INVENTORY_FENCE_BEGIN in doc
    assert "keep fixing until green" in doc
    assert validator.validate(clone) == []


def test_state_manifest_allows_an_explicit_unknown_open_pr_count(clone: Path) -> None:
    """P2 regression: the fail-closed OPEN_PR_COUNT=UNKNOWN case must be representable, not fabricated."""
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    open_pr_count = schema["properties"]["open_pr_count"]
    assert "null" in open_pr_count["type"]
    assert "UNKNOWN" in open_pr_count["description"]
    evidence = schema["properties"]["open_pr_count_evidence"]
    assert set(evidence["enum"]) == {"PROVEN", "UNKNOWN"}


def test_example_manifest_declares_its_open_pr_count_evidence(clone: Path) -> None:
    example = json.loads(_read(clone, validator.MANIFEST_EXAMPLE))
    assert example["open_pr_count_evidence"] in {"PROVEN", "UNKNOWN"}


# ---------------------------------------------------------------------------
# Regressions for the six-P2 fixed-point set (PR #371 reaudit)
# ---------------------------------------------------------------------------

# --- P2-1: exactly one active routing authority -----------------------------


def test_canonical_routing_matrix_lives_only_in_agent_os_v2(clone: Path) -> None:
    holders = [rel for rel in validator.ACTIVE_SURFACES if validator.ROUTING_MATRIX_BEGIN in _read(clone, rel)]
    assert holders == [validator.AGENT_OS_V2_DOC]


@pytest.mark.parametrize(
    "surface",
    ["CLAUDE.md", "AGENTS.md", validator.WORKFLOW_DOC, validator.CLAUDE_SKILL],
)
def test_second_routing_authority_declaration_fails(clone: Path, surface: str) -> None:
    _append_paragraph(clone, surface, "The single authoritative routing matrix is agent_workflow.md section 24.3.")
    violations = validator.validate(clone)
    assert "W" in _codes(violations)
    assert any(surface in violation for violation in violations)


def test_duplicated_routing_matrix_block_fails(clone: Path) -> None:
    _append_paragraph(
        clone,
        validator.WORKFLOW_DOC,
        f"{validator.ROUTING_MATRIX_BEGIN}\n\n| Lane |\n|---|\n\n{validator.ROUTING_MATRIX_END}",
    )
    assert any("second ROLE_ROUTING_MATRIX_V2" in violation for violation in validator.validate(clone))


def test_pointing_at_the_canonical_authority_is_allowed(clone: Path) -> None:
    _append_paragraph(
        clone,
        "CLAUDE.md",
        "The canonical routing authority is `docs/crypto_core/agent_os_v2.md` section 3.",
    )
    assert validator.validate(clone) == []


def test_disclaiming_authority_is_allowed(clone: Path) -> None:
    _append_paragraph(clone, "AGENTS.md", "This companion is never a routing authority.")
    assert validator.validate(clone) == []


# --- P2-2: relational open-PR evidence --------------------------------------


@pytest.mark.parametrize(
    ("manifest", "valid"),
    [
        ({"open_pr_count": 0, "open_pr_count_evidence": "PROVEN"}, True),
        ({"open_pr_count": 3, "open_pr_count_evidence": "PROVEN"}, True),
        ({"open_pr_count": None, "open_pr_count_evidence": "UNKNOWN"}, True),
        ({"open_pr_count": 1, "open_pr_count_evidence": "UNKNOWN"}, False),
        ({"open_pr_count": None, "open_pr_count_evidence": "PROVEN"}, False),
        ({"open_pr_count": 1}, False),
        ({"open_pr_count_evidence": "PROVEN"}, False),
        ({"open_pr_count": 1, "open_pr_count_evidence": "MAYBE"}, False),
    ],
)
def test_open_pr_evidence_relation(manifest: dict, valid: bool) -> None:
    violations = validator.validate_state_manifest(manifest)
    assert (violations == []) is valid


def test_schema_requires_the_evidence_field(clone: Path) -> None:
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    assert "open_pr_count_evidence" in schema["required"]


def test_schema_binds_the_relation_structurally_not_in_prose(clone: Path) -> None:
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    branches = {
        branch["properties"]["open_pr_count_evidence"]["const"]: branch["properties"]["open_pr_count"]["type"]
        for branch in schema["oneOf"]
    }
    assert branches == {"PROVEN": "integer", "UNKNOWN": "null"}


def test_integer_only_open_pr_count_schema_regression_fails(clone: Path) -> None:
    """The pre-repair schema shape - integer-only, no relation - must not validate."""
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    schema["properties"]["open_pr_count"]["type"] = "integer"
    schema.pop("oneOf", None)
    schema["required"] = [name for name in schema["required"] if name != "open_pr_count_evidence"]
    _write(clone, validator.MANIFEST_SCHEMA, json.dumps(schema, indent=2))
    assert "N" in _codes(validator.validate(clone))


def test_removed_oneof_branch_fails(clone: Path) -> None:
    schema = json.loads(_read(clone, validator.MANIFEST_SCHEMA))
    schema["oneOf"] = schema["oneOf"][:1]
    _write(clone, validator.MANIFEST_SCHEMA, json.dumps(schema, indent=2))
    assert "N" in _codes(validator.validate(clone))


def test_example_manifest_with_fabricated_count_fails(clone: Path) -> None:
    example = json.loads(_read(clone, validator.MANIFEST_EXAMPLE))
    example["open_pr_count"] = 0
    example["open_pr_count_evidence"] = "UNKNOWN"
    _write(clone, validator.MANIFEST_EXAMPLE, json.dumps(example, indent=2))
    assert "O" in _codes(validator.validate(clone))


# --- P2-3: validator coverage and bypass resistance -------------------------


def test_every_active_surface_is_enforced(clone: Path) -> None:
    """Coverage is the complete active set, not a subset: each surface rejects an activation."""
    for surface in validator.ACTIVE_SURFACES:
        original = _read(clone, surface)
        _write(clone, surface, original + "\n\nClaude Fable 5 is the default executor.\n")
        violations = validator.validate(clone)
        _write(clone, surface, original)
        assert any(surface in violation for violation in violations), surface


@pytest.mark.parametrize(
    ("name", "addition"),
    [
        ("multi_space", "Claude    Fable    5    is   the   default   executor."),
        ("line_wrapped", "Claude Fable\n5 is the default executor for heavy implementation."),
        ("colon", "Claude Fable 5: the active default executor for heavy work."),
        ("dash", "Claude Fable 5 - the active heavy implementation lane."),
        (
            "adjacent_retired",
            "Claude Fable 5 is the default executor. Claude Fable 5 is INACTIVE_EXPIRED_RETIRED.",
        ),
    ],
)
def test_textual_variation_cannot_evade_detection(clone: Path, name: str, addition: str) -> None:
    _append_paragraph(clone, validator.AGENT_OS_V2_DOC, addition)
    assert "D" in _codes(validator.validate(clone)), name


@pytest.mark.parametrize("position", ["before", "after"])
def test_active_assertion_around_the_permitted_fence_is_caught(clone: Path, position: str) -> None:
    fence = f'{validator.INVENTORY_FENCE_BEGIN}\n\n- "keep fixing until green"\n\n{validator.INVENTORY_FENCE_END}'
    active = "Claude Fable 5 is the default executor."
    block = f"{active}\n\n{fence}" if position == "before" else f"{fence}\n\n{active}"
    _append_paragraph(clone, validator.AGENT_OS_V2_DOC, block)
    assert "D" in _codes(validator.validate(clone))


@pytest.mark.parametrize(
    "surface",
    [rel for rel in validator.ACTIVE_SURFACES if rel not in validator.INVENTORY_FENCE_ALLOWED_FILES],
)
def test_fence_is_rejected_in_every_non_permitted_active_surface(clone: Path, surface: str) -> None:
    _append_paragraph(
        clone, surface, f"{validator.INVENTORY_FENCE_BEGIN}\n\nanything\n\n{validator.INVENTORY_FENCE_END}"
    )
    assert any("inventory fence is not allowed" in violation for violation in validator.validate(clone))


def test_historical_workflow_sections_stay_readable_as_history(clone: Path) -> None:
    """Sections 20-23 record superseded eras verbatim; enforcement must not treat them as active."""
    workflow = _read(clone, validator.WORKFLOW_DOC)
    assert "## 20. HISTORICAL" in workflow
    assert "Fable 5" in workflow
    assert validator.validate(clone) == []


# --- P2-4: PROMPT_COMPILER_V2 template completeness -------------------------


@pytest.mark.parametrize("surface", sorted(validator.PROMPT_TEMPLATE_SURFACES))
def test_active_template_surface_enumerates_all_twelve_fields(clone: Path, surface: str) -> None:
    text = _read(clone, surface)
    start = text.index(validator.PROMPT_FIELDS_FENCE_BEGIN)
    end = text.index(validator.PROMPT_FIELDS_FENCE_END)
    block = text[start:end]
    assert len(validator.PROMPT_COMPILER_FIELDS) == 12
    for field in validator.PROMPT_COMPILER_FIELDS:
        assert field in block, (surface, field)


@pytest.mark.parametrize("surface", sorted(validator.PROMPT_TEMPLATE_SURFACES))
def test_removed_prompt_compiler_field_fails(clone: Path, surface: str) -> None:
    text = _read(clone, surface)
    start = text.index(validator.PROMPT_FIELDS_FENCE_BEGIN)
    end = text.index(validator.PROMPT_FIELDS_FENCE_END)
    block = text[start:end].replace("`BLOCKER_INVENTORY`", "(removed)")
    _write(clone, surface, text[:start] + block + text[end:])
    violations = validator.validate(clone)
    assert "Y" in _codes(violations)
    assert any("BLOCKER_INVENTORY" in violation for violation in violations)


@pytest.mark.parametrize("surface", sorted(validator.PROMPT_TEMPLATE_SURFACES))
def test_removed_prompt_compiler_field_block_fails(clone: Path, surface: str) -> None:
    _write(clone, surface, _read(clone, surface).replace(validator.PROMPT_FIELDS_FENCE_BEGIN, "(removed)"))
    assert "Y" in _codes(validator.validate(clone))


# --- P2-5: semantic-only MAX_SAFE_PR sizing ---------------------------------


def test_no_active_max_changed_files_cap(clone: Path) -> None:
    for surface in validator.ACTIVE_SURFACES:
        for line in _read(clone, surface).splitlines():
            if "MAX_CHANGED_FILES" in line:
                assert validator._has_marker(line), (surface, line)


@pytest.mark.parametrize("surface", sorted(validator.PROMPT_TEMPLATE_SURFACES))
def test_reintroduced_max_changed_files_cap_fails(clone: Path, surface: str) -> None:
    _append_paragraph(clone, surface, "AUTHORIZED SCOPE: <exact files>; MAX_CHANGED_FILES: 5")
    violations = validator.validate(clone)
    assert "X" in _codes(violations)
    assert any(surface in violation for violation in violations)
