from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_operator_promotion_review_proposal import propose_deribit_operator_promotion_review

PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
PHASE54_TELEMETRY = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _phase54_telemetry() -> dict[str, object]:
    return _json(PHASE54_TELEMETRY)


def _proposal_result():
    return propose_deribit_operator_promotion_review(_phase55_readiness(), _phase54_telemetry())


def test_phase56c_phase55_and_phase54_sources_validate() -> None:
    phase55 = _phase55_readiness()
    phase54 = _phase54_telemetry()

    assert phase55["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert phase55["ready_for_operator_promotion_review"] is True
    assert phase55["promotion_granted"] is False
    assert phase54["telemetry_audit_verdict"] == "PASS"
    assert phase54["execution_verdict"] == "PASS"
    assert phase54["promotion_granted"] is False


def test_phase56c_operator_promotion_review_proposal_validates_without_approval_or_live_scope() -> None:
    result = _proposal_result()
    artifact = result.artifact_payload

    assert result.accepted is True
    assert result.rejection_reasons == ()
    assert artifact["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert artifact["proposal_type"] == "OPERATOR_PROMOTION_REVIEW"
    assert artifact["approval_status"] == "NOT_APPROVED"
    assert artifact["operator_metadata_required"] is True
    assert artifact["promotion_granted"] is False
    assert artifact["ready_for_live"] is False
    assert artifact["ready_for_shadow"] is False
    assert artifact["ready_for_operator_promotion_review"] is True
    assert artifact["next_blocker"] == "OPERATOR_PROMOTION_APPROVAL_NOT_READY"


def test_phase56c_proposal_preserves_source_scope_and_flags() -> None:
    artifact = _proposal_result().artifact_payload

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
