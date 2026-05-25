from __future__ import annotations

from copy import deepcopy

from crypto_core.venue.deribit_campaign_performance_evaluation import evaluate_deribit_campaign_performance
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import _phase49_audit


def test_phase50d_missing_or_malformed_phase49_artifact_fails_closed() -> None:
    result = evaluate_deribit_campaign_performance(None)

    assert result.accepted is False
    assert "deribit_campaign_performance_evaluation:phase49_artifact_missing" in result.rejection_reasons

    malformed = deepcopy(_phase49_audit())
    malformed["policy_refs"] = [{"not": "a string"}]
    malformed_result = evaluate_deribit_campaign_performance(malformed)

    assert malformed_result.accepted is False
    assert "deribit_campaign_performance_evaluation:phase49_policy_refs_invalid" in malformed_result.rejection_reasons


def test_phase50d_non_pass_verdicts_fail_closed() -> None:
    for field in ("audit_verdict", "campaign_execution_verdict"):
        artifact = deepcopy(_phase49_audit())
        artifact[field] = "FAIL"
        result = evaluate_deribit_campaign_performance(artifact)

        assert result.accepted is False
        assert "deribit_campaign_performance_evaluation:phase49_metadata_invalid" in result.rejection_reasons


def test_phase50d_unsafe_scope_or_safety_flag_drift_fails_closed() -> None:
    for field in ("live_enabled", "shadow_enabled", "scheduler_enabled", "auto_loop_enabled"):
        artifact = deepcopy(_phase49_audit())
        artifact[field] = True
        result = evaluate_deribit_campaign_performance(artifact)

        assert result.accepted is False
        assert "deribit_campaign_performance_evaluation:phase49_scope_flags_invalid" in result.rejection_reasons

    for field in ("no_private_api", "no_credentials", "no_exchange_orders", "no_execution_adapter"):
        artifact = deepcopy(_phase49_audit())
        artifact[field] = False
        result = evaluate_deribit_campaign_performance(artifact)

        assert result.accepted is False
        assert "deribit_campaign_performance_evaluation:phase49_scope_flags_invalid" in result.rejection_reasons


def test_phase50d_missing_safety_flags_and_bad_connector_count_fail_closed() -> None:
    missing = deepcopy(_phase49_audit())
    missing.pop("no_order_routing")
    bad_connector = deepcopy(_phase49_audit())
    bad_connector["connector_ready_dialects_count"] = 2

    missing_result = evaluate_deribit_campaign_performance(missing)
    bad_connector_result = evaluate_deribit_campaign_performance(bad_connector)

    assert missing_result.accepted is False
    assert "deribit_campaign_performance_evaluation:phase49_scope_flags_invalid" in missing_result.rejection_reasons
    assert bad_connector_result.accepted is False
    assert "deribit_campaign_performance_evaluation:phase49_bounds_invalid" in bad_connector_result.rejection_reasons


def test_phase50d_malformed_counts_fail_closed() -> None:
    artifact = deepcopy(_phase49_audit())
    artifact["aggregate_trades_filled"] = "6"

    result = evaluate_deribit_campaign_performance(artifact)

    assert result.accepted is False
    assert "deribit_campaign_performance_evaluation:phase49_counts_invalid" in result.rejection_reasons
