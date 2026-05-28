from __future__ import annotations

import json
from pathlib import Path

FALSE_SCOPE = tuple(
    "runtime_loop_started runtime_order_routing_enabled live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation strategy_signal_generated order_intent_generated".split()
)
TRUE_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_70B.json")


def test_phase70e_artifact_preserves_no_live_and_no_order_routing_scope() -> None:
    artifact = json.loads(ARTIFACT.read_text(encoding="utf-8"))

    for field in FALSE_SCOPE:
        assert artifact[field] is False
    for field in TRUE_FLAGS:
        assert artifact[field] is True
