from __future__ import annotations

from copy import deepcopy

from crypto_core.venue.deribit_approved_execution_telemetry_audit import (
    audit_deribit_approved_execution_telemetry,
)
from tests.crypto_core.venue.test_phase54b_approved_execution_telemetry_artifact import (
    _phase52_approval,
    _phase53_execution,
)

_UNSET = object()


def _run_with(*, phase53: object = _UNSET, phase52: object = _UNSET):
    return audit_deribit_approved_execution_telemetry(
        _phase53_execution() if phase53 is _UNSET else phase53,
        _phase52_approval() if phase52 is _UNSET else phase52,
    )


def test_phase54d_missing_or_malformed_phase53_artifact_fails_closed() -> None:
    missing = _run_with(phase53=None)
    malformed = _run_with(phase53=[])

    assert missing.accepted is False
    assert malformed.accepted is False
    assert "deribit_approved_execution_telemetry_audit:phase53_artifact_missing" in missing.rejection_reasons
    assert "deribit_approved_execution_telemetry_audit:phase53_artifact_missing" in malformed.rejection_reasons


def test_phase54d_execution_status_or_verdict_drift_fails_closed() -> None:
    bad_status = deepcopy(_phase53_execution())
    bad_status["campaign_execution_status"] = "NOT_EXECUTED"
    bad_mode = deepcopy(_phase53_execution())
    bad_mode["execution_mode"] = "LIVE"
    bad_verdict = deepcopy(_phase53_execution())
    bad_verdict["execution_verdict"] = "FAIL"

    assert (
        "deribit_approved_execution_telemetry_audit:phase53_metadata_invalid"
        in _run_with(phase53=bad_status).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase53_metadata_invalid"
        in _run_with(phase53=bad_mode).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase53_metadata_invalid"
        in _run_with(phase53=bad_verdict).rejection_reasons
    )


def test_phase54d_count_and_session_shape_drift_fails_closed() -> None:
    rejected = deepcopy(_phase53_execution())
    rejected["sessions_rejected"] = 1
    ledger_mismatch = deepcopy(_phase53_execution())
    ledger_mismatch["aggregate_ledger_mutations"] = 5
    aggregate_mismatch = deepcopy(_phase53_execution())
    aggregate_mismatch["aggregate_trades_filled"] = 5
    aggregate_mismatch["aggregate_ledger_mutations"] = 5
    non_dict_session = deepcopy(_phase53_execution())
    non_dict_session["session_results"] = ["bad"]

    assert (
        "deribit_approved_execution_telemetry_audit:phase53_counts_invalid"
        in _run_with(phase53=rejected).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase53_counts_invalid"
        in _run_with(phase53=ledger_mismatch).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase53_counts_invalid"
        in _run_with(phase53=aggregate_mismatch).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase53_session_results_invalid"
        in _run_with(phase53=non_dict_session).rejection_reasons
    )


def test_phase54d_promotion_or_live_scope_drift_fails_closed() -> None:
    for field in ("promotion_granted", "live_ready", "shadow_ready", "live_enabled", "shadow_enabled"):
        source = deepcopy(_phase53_execution())
        source[field] = True
        reasons = _run_with(phase53=source).rejection_reasons

        assert "deribit_approved_execution_telemetry_audit:phase53_scope_flags_invalid" in reasons


def test_phase54d_private_execution_safety_drift_fails_closed() -> None:
    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        source = deepcopy(_phase53_execution())
        source[field] = False
        reasons = _run_with(phase53=source).rejection_reasons

        assert "deribit_approved_execution_telemetry_audit:phase53_safety_flags_invalid" in reasons


def test_phase54d_phase52_approval_drift_fails_closed() -> None:
    bad_approval = deepcopy(_phase52_approval())
    bad_approval["approval_status"] = "NOT_APPROVED"
    bad_connector = deepcopy(_phase52_approval())
    bad_connector["connector_ready_dialects_count"] = 0

    assert (
        "deribit_approved_execution_telemetry_audit:phase52_metadata_invalid"
        in _run_with(phase52=bad_approval).rejection_reasons
    )
    assert (
        "deribit_approved_execution_telemetry_audit:phase52_connector_ready_dialects_invalid"
        in _run_with(phase52=bad_connector).rejection_reasons
    )
