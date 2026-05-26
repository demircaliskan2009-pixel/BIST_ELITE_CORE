from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase59b_paper_promotion_execution_telemetry_artifact import _audit


def test_phase59e_artifact_has_no_live_or_new_execution_enablement() -> None:
    artifact = _audit()

    for field in (
        "live_ready",
        "shadow_ready",
        "scheduler_enabled",
        "auto_loop_enabled",
        "live_enabled",
        "shadow_enabled",
        "campaign_execution",
        "session_execution",
        "run_execution",
        "ledger_mutation",
        "ledger_mutated",
    ):
        assert artifact[field] is False
    assert artifact["no_new_execution"] is True
    assert artifact["report_only"] is True


def test_phase59e_artifact_does_not_contain_private_or_bist_payloads() -> None:
    serialized = json.dumps(_audit(), sort_keys=True).lower()

    for forbidden in ("api_key", "secret", "credential_value", "bist", "matriks", "kap", "viop"):
        assert forbidden not in serialized
