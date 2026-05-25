from __future__ import annotations

from copy import deepcopy

from crypto_core.venue.deribit_paper_promotion_readiness import evaluate_deribit_paper_promotion_readiness
from tests.crypto_core.venue.test_phase55b_promotion_readiness_artifact import _phase54_audit


def _run_with(source: object):
    return evaluate_deribit_paper_promotion_readiness(source)


def test_phase55d_missing_or_malformed_phase54_artifact_fails_closed() -> None:
    missing = _run_with(None)
    malformed = _run_with([])

    assert missing.accepted is False
    assert malformed.accepted is False
    assert "deribit_paper_promotion_readiness:phase54_artifact_missing" in missing.rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_artifact_missing" in malformed.rejection_reasons


def test_phase55d_verdict_or_execution_drift_fails_closed() -> None:
    bad_audit = deepcopy(_phase54_audit())
    bad_audit["telemetry_audit_verdict"] = "FAIL"
    bad_execution = deepcopy(_phase54_audit())
    bad_execution["execution_verdict"] = "FAIL"

    assert "deribit_paper_promotion_readiness:phase54_metadata_invalid" in _run_with(bad_audit).rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_metadata_invalid" in _run_with(bad_execution).rejection_reasons


def test_phase55d_unsafe_scope_or_safety_flags_fail_closed() -> None:
    promoted = deepcopy(_phase54_audit())
    promoted["promotion_granted"] = True
    live_ready = deepcopy(_phase54_audit())
    live_ready["ready_for_live"] = True
    no_private = deepcopy(_phase54_audit())
    no_private["no_private_api"] = False
    not_report_only = deepcopy(_phase54_audit())
    not_report_only["report_only"] = False
    safety_metrics = deepcopy(_phase54_audit())
    safety_metrics["safety_metrics"]["live_scope"] = True

    assert "deribit_paper_promotion_readiness:phase54_scope_flags_invalid" in _run_with(promoted).rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_scope_flags_invalid" in _run_with(live_ready).rejection_reasons
    assert (
        "deribit_paper_promotion_readiness:phase54_scope_flags_invalid" in _run_with(not_report_only).rejection_reasons
    )
    assert "deribit_paper_promotion_readiness:phase54_safety_flags_invalid" in _run_with(no_private).rejection_reasons
    assert (
        "deribit_paper_promotion_readiness:phase54_safety_metrics_invalid"
        in _run_with(safety_metrics).rejection_reasons
    )


def test_phase55d_bounds_counts_and_metrics_drift_fail_closed() -> None:
    bad_connector = deepcopy(_phase54_audit())
    bad_connector["connector_ready_dialects_count"] = 0
    rejected = deepcopy(_phase54_audit())
    rejected["sessions_rejected"] = 1
    bad_metric = deepcopy(_phase54_audit())
    bad_metric["execution_metrics"]["fill_rate"] = 0.5
    bool_metrics = deepcopy(_phase54_audit())
    bool_metrics["execution_metrics"]["fill_rate"] = True
    bool_metrics["execution_metrics"]["rejection_rate"] = False

    assert "deribit_paper_promotion_readiness:phase54_bounds_invalid" in _run_with(bad_connector).rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_counts_invalid" in _run_with(rejected).rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_metrics_invalid" in _run_with(bad_metric).rejection_reasons
    assert "deribit_paper_promotion_readiness:phase54_metrics_invalid" in _run_with(bool_metrics).rejection_reasons
