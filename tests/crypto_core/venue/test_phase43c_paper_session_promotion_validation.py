from __future__ import annotations

from tests.crypto_core.venue.test_phase43b_paper_session_promotion_artifact import (
    _phase41_report,
    _promotion_rejection_reasons,
    _promotion_report,
    _session_artifact,
)


def test_phase43c_phase42_artifact_exists_and_validates() -> None:
    session = _session_artifact()

    assert session["schema_version"] == "deribit_hard_capped_paper_session_artifact.v1"
    assert session["session_verdict"] == "PASS"
    assert session["hard_cap"] == 3
    assert session["max_session_trades"] == 2
    assert session["trades_requested"] == 2
    assert session["trades_rejected"] == 0


def test_phase43c_phase41_report_exists_and_validates() -> None:
    phase41 = _phase41_report()

    assert phase41["schema_version"] == "deribit_bounded_paper_run_telemetry_report.v1"
    assert phase41["report_verdict"] == "PASS"
    assert phase41["next_blocker"] == "HARD_CAPPED_MULTI_RUN_SESSION_NOT_READY"


def test_phase43c_not_ready_is_expected_until_repeated_evidence_exists() -> None:
    report = _promotion_report()

    assert report["evaluated_sessions"] == 1
    assert report["required_future_sessions_minimum"] == 3
    assert report["repeated_session_campaign_ready"] is False
    assert report["promotion_reason"] == "PAPER_PROMOTION_REQUIRES_REPEATED_SESSION_EVIDENCE"
    assert _promotion_rejection_reasons(_session_artifact(), _phase41_report(), report) == ()
