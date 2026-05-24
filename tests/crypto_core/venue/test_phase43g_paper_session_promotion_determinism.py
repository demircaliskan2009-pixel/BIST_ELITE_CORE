from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase43b_paper_session_promotion_artifact import (
    _phase41_report,
    _promotion_rejection_reasons,
    _promotion_report,
    _session_artifact,
)


def test_phase43g_promotion_validation_is_deterministic() -> None:
    session = _session_artifact()
    phase41 = _phase41_report()
    report = _promotion_report()

    first = _promotion_rejection_reasons(session, phase41, report)
    second = _promotion_rejection_reasons(session, phase41, report)

    assert first == second == ()


def test_phase43g_report_json_round_trip_is_deterministic() -> None:
    report = _promotion_report()

    first = json.dumps(report, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
