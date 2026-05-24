from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase39b_paper_trade_audit_report_artifact import (
    _audit_rejection_reasons,
    _proof,
    _report,
)


def test_phase39g_audit_validation_is_deterministic_across_repeated_runs() -> None:
    proof = _proof()
    report = _report()

    first = _audit_rejection_reasons(proof, report)
    second = _audit_rejection_reasons(proof, report)

    assert first == second == ()


def test_phase39g_audit_report_json_is_deterministic_after_round_trip() -> None:
    report = _report()

    first = json.dumps(report, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
