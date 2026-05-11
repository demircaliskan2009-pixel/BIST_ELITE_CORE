"""Phase 25B — Deribit human-review readiness validator tests.

Proves:
1. Current worksheets are not ready (accepted=False, ready_for_engineering_patch=False).
2. Missing reviewer metadata fails closed.
3. Pending rows fail closed.
4. Rejected/deferred rows fail closed.
5. No runtime connector readiness changes.
6. connector_ready_dialects() == ().
7. Validator imports only inert modules.
"""

from __future__ import annotations

import ast
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import (
    CLAIM_WORKSHEET_PATH,
    MANIFEST_PATH,
    POLICY_WORKSHEET_PATH,
    DeribitManualReviewReadinessResult,
    DeribitReviewRowResult,
    _validate_claims,
    _validate_policies,
    evaluate_deribit_manual_review_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

REPO_ROOT = Path(__file__).resolve().parents[3]
VALIDATOR_SRC = REPO_ROOT / "src" / "crypto_core" / "venue" / "deribit_manual_review_readiness.py"

# ---------------------------------------------------------------------------
# Allowed imports for the validator module — must be inert only
# ---------------------------------------------------------------------------

_ALLOWED_IMPORTS = frozenset(
    {
        "__future__",
        "dataclasses",
        "pathlib",
        "field",
        "crypto_core",
    }
)

_FORBIDDEN_IMPORT_PATTERNS = (
    "requests",
    "httpx",
    "aiohttp",
    "websocket",
    "socket",
    "subprocess",
    "os.system",
    "asyncio",
    "threading",
    "multiprocessing",
)


# ---------------------------------------------------------------------------
# 1. Current repo state: worksheets not ready
# ---------------------------------------------------------------------------


def test_current_worksheets_are_not_ready():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert isinstance(result, DeribitManualReviewReadinessResult)
    assert result.accepted is False
    assert result.ready_for_engineering_patch is False


def test_current_worksheets_have_pending_rows():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert len(result.pending_rows) > 0, "Expected pending rows in unreviewed worksheets"


def test_current_b1_b5_all_blocked():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    for blocker in ("B1", "B2", "B3", "B4", "B5"):
        assert result.b1_b5_status[blocker] == "BLOCKED", f"{blocker} must be BLOCKED in current repo state"


def test_current_worksheets_have_rejection_reasons():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert len(result.rejection_reasons) > 0


def test_current_worksheets_have_missing_metadata():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert len(result.missing_metadata) > 0


# ---------------------------------------------------------------------------
# 2. Missing reviewer metadata fails closed
# ---------------------------------------------------------------------------


def test_claim_rows_with_pending_reviewer_fail_closed():
    # Simulate a claim table where reviewer_id is PENDING
    pending_table = (
        "| claim_id | source_id | official_url | source_sha256 | doc_section_or_anchor"
        " | claim_text_or_paraphrase | review_status | reviewer_id | reviewed_at_iso"
        " | decision | operational_readiness_effect | rejection_reason_if_pending |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| `public_websocket_availability` | `DERIBIT_ENVIRONMENT`"
        " | `https://docs.deribit.com/` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`"
        " | `#section` | text | `PENDING` | `PENDING` | `PENDING` | `PENDING`"
        " | `LEAVES_BLOCKER` | `reason` |\n"
    )
    rows = _validate_claims(pending_table)
    public_ws = next((r for r in rows if r.row_id == "public_websocket_availability"), None)
    assert public_ws is not None
    assert public_ws.accepted is False if hasattr(public_ws, "accepted") else public_ws.status != "APPROVED"
    assert public_ws.status == "PENDING"
    assert any("reviewer_id_pending" in m or "pending" in m for m in public_ws.missing_metadata)


def test_claim_rows_with_pending_reviewed_at_fail_closed():
    pending_table = (
        "| claim_id | source_id | official_url | source_sha256 | doc_section_or_anchor"
        " | claim_text_or_paraphrase | review_status | reviewer_id | reviewed_at_iso"
        " | decision | operational_readiness_effect | rejection_reason_if_pending |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| `change_id` | `DERIBIT_NOTIFICATIONS`"
        " | `https://docs.deribit.com/` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`"
        " | `#section` | text | `APPROVED` | `reviewer-01` | `PENDING` | `APPROVE`"
        " | `CLEARS_BLOCKER` | `` |\n"
    )
    rows = _validate_claims(pending_table)
    r = next((x for x in rows if x.row_id == "change_id"), None)
    assert r is not None
    assert r.status == "PENDING"
    assert any("reviewed_at_iso" in m for m in r.missing_metadata)


def test_policy_rows_with_missing_reviewer_fail_closed():
    pending_table = (
        "| policy_id | venue_id | policy_status | policy_blocker_status"
        " | reviewer_id | reviewed_at_iso | source_refs | claim_refs"
        " | engineering_policy_required | legal_review_required"
        " | manual_approval_required | decision | rejection_reason_if_pending"
        " | operational_readiness_effect |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| `checksum_decision` | `deribit` | `PENDING` | `PENDING_MANUAL_REVIEW`"
        " | `PENDING` | `PENDING` | `DERIBIT_NOTIFICATIONS` | `checksum_decision`"
        " | `YES` | `NO` | `YES` | `PENDING` | `reason` | `LEAVES_BLOCKER` |\n"
    )
    rows = _validate_policies(pending_table)
    r = next((x for x in rows if x.row_id == "checksum_decision"), None)
    assert r is not None
    assert r.status == "PENDING"
    assert len(r.missing_metadata) > 0


# ---------------------------------------------------------------------------
# 3. Pending rows fail closed
# ---------------------------------------------------------------------------


def test_pending_claim_rows_fail_closed():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    # All 23 claim rows must appear as pending
    claim_pending = [r for r in result.pending_rows if r.startswith("claim_review:")]
    assert len(claim_pending) == 23, f"Expected 23 pending claim rows, got {len(claim_pending)}: {claim_pending}"


def test_pending_policy_rows_fail_closed():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    policy_pending = [r for r in result.pending_rows if r.startswith("policy_review:")]
    assert len(policy_pending) == 7, f"Expected 7 pending policy rows, got {len(policy_pending)}: {policy_pending}"


# ---------------------------------------------------------------------------
# 4. Rejected / deferred rows fail closed
# ---------------------------------------------------------------------------


def test_rejected_claim_row_fails_closed():
    rejected_table = (
        "| claim_id | source_id | official_url | source_sha256 | doc_section_or_anchor"
        " | claim_text_or_paraphrase | review_status | reviewer_id | reviewed_at_iso"
        " | decision | operational_readiness_effect | rejection_reason_if_pending |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| `public_websocket_availability` | `DERIBIT_ENVIRONMENT`"
        " | `https://docs.deribit.com/` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`"
        " | `#section` | text | `REJECTED` | `reviewer-01` | `2026-05-11T00:00:00Z` | `REJECT`"
        " | `LEAVES_BLOCKER` | `rejected` |\n"
    )
    rows = _validate_claims(rejected_table)
    r = next((x for x in rows if x.row_id == "public_websocket_availability"), None)
    assert r is not None
    assert r.status == "REJECTED"


def test_deferred_policy_row_fails_closed():
    deferred_table = (
        "| policy_id | venue_id | policy_status | policy_blocker_status"
        " | reviewer_id | reviewed_at_iso | source_refs | claim_refs"
        " | engineering_policy_required | legal_review_required"
        " | manual_approval_required | decision | rejection_reason_if_pending"
        " | operational_readiness_effect |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        "| `checksum_decision` | `deribit` | `DEFERRED` | `DEFERRED`"
        " | `reviewer-01` | `2026-05-11T00:00:00Z` | `DERIBIT_NOTIFICATIONS` | `checksum_decision`"
        " | `YES` | `NO` | `YES` | `DEFER` | `` | `LEAVES_BLOCKER` |\n"
    )
    rows = _validate_policies(deferred_table)
    r = next((x for x in rows if x.row_id == "checksum_decision"), None)
    assert r is not None
    assert r.status == "DEFERRED"


def test_mixed_approved_and_pending_still_fails_closed():
    # Even if one row is approved, pending rows must keep accepted=False
    mixed_claim = (
        "| claim_id | source_id | official_url | source_sha256 | doc_section_or_anchor"
        " | claim_text_or_paraphrase | review_status | reviewer_id | reviewed_at_iso"
        " | decision | operational_readiness_effect | rejection_reason_if_pending |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|\n"
        # approved row
        "| `public_websocket_availability` | `DERIBIT_ENVIRONMENT`"
        " | `https://docs.deribit.com/` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`"
        " | `#section` | text | `APPROVED` | `reviewer-01` | `2026-05-11T00:00:00Z` | `APPROVE`"
        " | `CLEARS_BLOCKER` | `` |\n"
        # pending row
        "| `change_id` | `DERIBIT_NOTIFICATIONS`"
        " | `https://docs.deribit.com/` | `a5770fc45864cfd78af47d9ec49047ebe4cd5a51a46f65943025a5140cccfccd`"
        " | `#section` | text | `PENDING` | `PENDING` | `PENDING` | `PENDING`"
        " | `LEAVES_BLOCKER` | `reason` |\n"
    )
    rows = _validate_claims(mixed_claim)
    statuses = {r.row_id: r.status for r in rows}
    assert statuses.get("public_websocket_availability") == "APPROVED"
    assert statuses.get("change_id") == "PENDING"


# ---------------------------------------------------------------------------
# 5 & 6. Runtime gate: connector_ready_dialects unchanged and empty
# ---------------------------------------------------------------------------


def test_connector_ready_dialects_remains_empty():
    dialects = connector_ready_dialects()
    assert dialects == (), f"connector_ready_dialects() must return () but got {dialects}"


def test_evaluate_does_not_mutate_connector_ready_dialects():
    before = connector_ready_dialects()
    evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    after = connector_ready_dialects()
    assert before == after == ()


# ---------------------------------------------------------------------------
# 7. Validator imports only inert modules
# ---------------------------------------------------------------------------


def test_validator_module_has_no_forbidden_imports():
    src = VALIDATOR_SRC.read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            if isinstance(node, ast.ImportFrom):
                module = node.module or ""
            else:
                module = ""
                for alias in node.names:
                    module = alias.name
            for pattern in _FORBIDDEN_IMPORT_PATTERNS:
                assert pattern not in module, f"Forbidden import pattern '{pattern}' found in validator module"


def test_validator_result_type_is_correct():
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=REPO_ROOT / MANIFEST_PATH,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert isinstance(result.accepted, bool)
    assert isinstance(result.ready_for_engineering_patch, bool)
    assert isinstance(result.b1_b5_status, dict)
    assert isinstance(result.pending_rows, tuple)
    assert isinstance(result.rejected_rows, tuple)
    assert isinstance(result.deferred_rows, tuple)
    assert isinstance(result.missing_metadata, tuple)
    assert isinstance(result.rejection_reasons, tuple)
    assert isinstance(result.row_results, tuple)
    for rr in result.row_results:
        assert isinstance(rr, DeribitReviewRowResult)


def test_missing_worksheet_file_fails_closed(tmp_path: Path):
    nonexistent = tmp_path / "does_not_exist.md"
    result = evaluate_deribit_manual_review_readiness(
        manifest_path=nonexistent,
        claim_worksheet_path=REPO_ROOT / CLAIM_WORKSHEET_PATH,
        policy_worksheet_path=REPO_ROOT / POLICY_WORKSHEET_PATH,
    )
    assert result.accepted is False
    assert result.ready_for_engineering_patch is False
    assert any("worksheet_missing" in r for r in result.rejection_reasons)
