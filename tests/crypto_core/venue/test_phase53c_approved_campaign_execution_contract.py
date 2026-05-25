from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_performance_campaign import (
    DeribitApprovedPaperPerformanceCampaignRequest,
    DeribitApprovedPaperPerformanceCampaignSessionFixture,
    run_deribit_approved_paper_performance_campaign,
)
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase48c_campaign_execution_contract import _ledger, _trade_input
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact as _phase50_artifact,
)
from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import _approval as _phase52_approval

PHASE48_EXECUTION = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase48_execution() -> dict[str, object]:
    return _json(PHASE48_EXECUTION)


def _session_fixture(session_id: str, suffix: str) -> DeribitApprovedPaperPerformanceCampaignSessionFixture:
    return DeribitApprovedPaperPerformanceCampaignSessionFixture(
        session_id=session_id,
        idempotency_key=f"idem-{session_id}",
        trade_inputs=(
            _trade_input(f"phase53-{suffix}-trade-1"),
            _trade_input(f"phase53-{suffix}-trade-2"),
        ),
    )


def _phase53_request(**overrides: object) -> DeribitApprovedPaperPerformanceCampaignRequest:
    values = {
        "operator_id": "demir_operator",
        "campaign_request_id": "phase53-approved-paper-performance-campaign",
        "idempotency_key": "idem-phase53-approved-paper-performance-campaign",
        "simulation_only": True,
        "hard_cap": 3,
        "per_session_max_trades": 2,
        "max_campaign_sessions": 3,
    }
    values.update(overrides)
    return DeribitApprovedPaperPerformanceCampaignRequest(**values)


def _phase53_sessions() -> tuple[DeribitApprovedPaperPerformanceCampaignSessionFixture, ...]:
    return (
        _session_fixture("phase53-session-1", "session-1"),
        _session_fixture("phase53-session-2", "session-2"),
        _session_fixture("phase53-session-3", "session-3"),
    )


def _run_phase53():
    return run_deribit_approved_paper_performance_campaign(
        _phase53_request(),
        _phase52_approval(),
        _phase50_artifact(),
        _phase48_execution(),
        _phase53_sessions(),
        _ledger(),
    )


def test_phase53c_current_readiness_preconditions_hold() -> None:
    readiness = evaluate_deribit_manual_review_readiness()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1


def test_phase53c_approved_paper_performance_campaign_executes_offline_deterministic_sessions() -> None:
    result = _run_phase53()

    assert result.accepted is True
    assert result.campaign_request_id == "phase53-approved-paper-performance-campaign"
    assert result.sessions_requested == 3
    assert result.sessions_attempted == 3
    assert result.sessions_accepted == 3
    assert result.sessions_rejected == 0
    assert result.aggregate_trades_requested == 6
    assert result.aggregate_trades_filled == 6
    assert result.aggregate_ledger_mutations == 6
    assert result.ledger_mutated is True
    assert result.reason_code == "deribit_approved_paper_performance_campaign:accepted"
    assert len(result.session_results) == 3
    assert result.final_ledger_state is not None


def test_phase53c_execution_preserves_phase52_boundary_and_source_caps() -> None:
    result = _run_phase53()
    artifact = result.artifact_payload

    assert artifact["execution_mode"] == "OFFLINE_DETERMINISTIC_PAPER_ONLY"
    assert artifact["approval_status"] == "APPROVED"
    assert artifact["approval_decision"] == "APPROVE_PAPER_CAMPAIGN_PERFORMANCE"
    assert artifact["simulation_only"] is True
    assert artifact["live_enabled"] is False
    assert artifact["shadow_enabled"] is False
    assert artifact["scheduler_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["hard_cap"] == 3
    assert artifact["per_session_max_trades"] == 2
    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
    assert artifact["connector_ready_dialects_count"] == 1
    assert artifact["execution_verdict"] == "PASS"
    assert artifact["next_blocker"] == "APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_NOT_READY"
