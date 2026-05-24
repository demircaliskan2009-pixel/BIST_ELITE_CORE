from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase41b_paper_run_telemetry_report_artifact import (
    _report,
    _run_artifact,
    _telemetry_rejection_reasons,
)


def test_phase41g_telemetry_validation_is_deterministic() -> None:
    run = _run_artifact()
    report = _report()

    first = _telemetry_rejection_reasons(run, report)
    second = _telemetry_rejection_reasons(run, report)

    assert first == second == ()


def test_phase41g_report_json_round_trip_is_deterministic() -> None:
    report = _report()

    first = json.dumps(report, sort_keys=True, separators=(",", ":"))
    second = json.dumps(json.loads(first), sort_keys=True, separators=(",", ":"))

    assert first == second
