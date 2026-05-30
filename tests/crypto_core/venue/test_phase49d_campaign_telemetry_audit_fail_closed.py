from __future__ import annotations

from copy import deepcopy

from crypto_core.venue.deribit_campaign_telemetry_audit import run_deribit_campaign_telemetry_audit
from tests.crypto_core.venue.test_phase49b_campaign_telemetry_audit_artifact import (
    _phase47_approval,
    _phase48_artifact,
)


def test_phase49d_missing_phase48_artifact_fails_closed() -> None:
    result = run_deribit_campaign_telemetry_audit(None, _phase47_approval())

    assert result.accepted is False
    assert "deribit_campaign_telemetry_audit:phase48_artifact_missing" in result.rejection_reasons


def test_phase49d_unsafe_scope_flag_fails_closed() -> None:
    artifact = deepcopy(_phase48_artifact())
    artifact["live_enabled"] = True

    result = run_deribit_campaign_telemetry_audit(artifact, _phase47_approval())

    assert result.accepted is False
    assert "deribit_campaign_telemetry_audit:phase48_scope_flags_invalid" in result.rejection_reasons


def test_phase49d_malformed_counts_and_approval_bounds_fail_closed() -> None:
    artifact = deepcopy(_phase48_artifact())
    approval = deepcopy(_phase47_approval())
    artifact["aggregate_trades_filled"] = "6"
    approval["campaign_bounds"]["hard_cap"] = "3"

    result = run_deribit_campaign_telemetry_audit(artifact, approval)

    assert result.accepted is False
    assert "deribit_campaign_telemetry_audit:phase48_counts_invalid" in result.rejection_reasons
    assert "deribit_campaign_telemetry_audit:approval_bounds_invalid" in result.rejection_reasons


def test_phase49d_tampered_no_safety_flags_fail_closed() -> None:
    for field in (
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        artifact = deepcopy(_phase48_artifact())
        artifact[field] = False

        artifact_result = run_deribit_campaign_telemetry_audit(artifact, _phase47_approval())

        assert artifact_result.accepted is False
        assert "deribit_campaign_telemetry_audit:phase48_scope_flags_invalid" in artifact_result.rejection_reasons

    approval = deepcopy(_phase47_approval())
    approval["safety_flags"]["no_order_routing"] = False

    approval_result = run_deribit_campaign_telemetry_audit(_phase48_artifact(), approval)

    assert approval_result.accepted is False
    assert "deribit_campaign_telemetry_audit:approval_safety_flags_invalid" in approval_result.rejection_reasons
