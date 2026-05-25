from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_operator_promotion_approval import (
    DERIBIT_PHASE57_APPROVAL_DECISION,
    DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    DERIBIT_PHASE57_OPERATOR_ID,
    execute_deribit_operator_promotion_approval,
)

PHASE56_PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_REVIEW_PROPOSAL_56B.json")
PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
REVIEWED_AT_ISO = "2026-05-25T21:34:05Z"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase56_proposal() -> dict[str, object]:
    return _json(PHASE56_PROPOSAL)


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _approval_result():
    return execute_deribit_operator_promotion_approval(
        _phase56_proposal(),
        _phase55_readiness(),
        reviewed_at_iso=REVIEWED_AT_ISO,
        merge_policy_note=DERIBIT_PHASE57_MERGE_POLICY_NOTE,
    )


def test_phase57c_phase56_and_phase55_sources_validate() -> None:
    phase56 = _phase56_proposal()
    phase55 = _phase55_readiness()

    assert phase56["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase56["approval_status"] == "NOT_APPROVED"
    assert phase56["operator_metadata_required"] is True
    assert phase56["promotion_granted"] is False
    assert phase56["ready_for_live"] is False
    assert phase56["ready_for_shadow"] is False
    assert phase56["ready_for_operator_promotion_review"] is True
    assert phase56["connector_ready_dialects_count"] == 1
    assert phase55["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase55["ready_for_operator_promotion_review"] is True


def test_phase57c_operator_promotion_approval_validates_without_promotion_or_live_scope() -> None:
    result = _approval_result()
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["approval_status"] == "APPROVED"
    assert artifact["operator_id"] == DERIBIT_PHASE57_OPERATOR_ID
    assert artifact["reviewed_at_iso"] == REVIEWED_AT_ISO
    assert artifact["approval_decision"] == DERIBIT_PHASE57_APPROVAL_DECISION
    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
    assert artifact["campaign_execution"] is False
    assert artifact["session_execution"] is False
    assert artifact["run_execution"] is False
    assert artifact["ledger_mutated"] is False
    assert artifact["merge_policy_note"] == DERIBIT_PHASE57_MERGE_POLICY_NOTE
    assert artifact["next_blocker"] == "APPROVED_PROMOTION_EXECUTION_NOT_READY"


def test_phase57c_approval_preserves_no_live_and_safety_scope() -> None:
    artifact = _approval_result().artifact_payload

    for field in (
        "scheduler_enabled",
        "auto_loop_enabled",
        "live_enabled",
        "shadow_enabled",
    ):
        assert artifact[field] is False
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_strategy_signal",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        assert artifact[field] is True
    assert artifact["connector_ready_dialects_count"] == 1
