from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import _runtime_wiring


def test_phase62e_artifact_has_no_live_shadow_or_runtime_enablement() -> None:
    artifact = _runtime_wiring()

    for field in (
        "runtime_enabled",
        "runtime_started",
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
    for field in (
        "no_private_api",
        "no_credentials",
        "no_exchange_orders",
        "no_execution_adapter",
        "no_strategy_signal",
        "no_order_routing",
        "no_scheduler",
        "no_automatic_paper_loop",
        "no_shadow",
        "no_live",
    ):
        assert artifact[field] is True


def test_phase62e_artifact_does_not_contain_private_or_bist_payloads() -> None:
    serialized = json.dumps(_runtime_wiring(), sort_keys=True).lower()

    for forbidden in ("api_key", "secret", "credential_value", "bist", "matriks", "kap", "viop"):
        assert forbidden not in serialized
