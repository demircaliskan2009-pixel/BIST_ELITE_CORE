from __future__ import annotations

from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import (
    _promotion_readiness,
    _report_pack,
    _report_pack_rejection_reasons,
    _session_artifact,
)


def test_phase44c_phase42_artifact_exists_and_validates() -> None:
    session = _session_artifact()

    assert session["schema_version"] == "deribit_hard_capped_paper_session_artifact.v1"
    assert session["session_verdict"] == "PASS"
    assert session["hard_cap"] == 3
    assert session["max_session_trades"] == 2


def test_phase44c_phase43_promotion_readiness_exists_and_validates() -> None:
    promotion = _promotion_readiness()

    assert promotion["schema_version"] == "deribit_paper_session_promotion_readiness.v1"
    assert promotion["promotion_verdict"] == "NOT_READY"
    assert promotion["required_future_sessions_minimum"] == 3
    assert promotion["next_blocker"] == "REPEATED_DETERMINISTIC_SESSION_REPORT_PACK_NOT_READY"


def test_phase44c_report_pack_validates_and_keeps_promotion_blocked() -> None:
    pack = _report_pack()

    assert _report_pack_rejection_reasons(_session_artifact(), _promotion_readiness(), pack) == ()
    assert pack["session_count"] == 3
    assert pack["aggregate_trades_requested"] == 6
    assert pack["aggregate_trades_rejected"] == 0
    assert pack["promotion_granted"] is False
