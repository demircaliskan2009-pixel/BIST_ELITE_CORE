from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_promoted_runtime_readiness import (
    evaluate_deribit_paper_promoted_runtime_readiness,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE60_POST_AUDIT = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json")
RUNTIME_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_61B.json")
FALSE_EXECUTION_FLAGS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase60_post_audit() -> dict[str, object]:
    return _json(PHASE60_POST_AUDIT)


def _runtime_readiness() -> dict[str, object]:
    return _json(RUNTIME_READINESS)


def _expected_runtime_readiness() -> dict[str, object]:
    return evaluate_deribit_paper_promoted_runtime_readiness(_phase60_post_audit()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def test_phase61b_artifact_has_required_schema_and_source_reference() -> None:
    artifact = _runtime_readiness()

    assert PHASE60_POST_AUDIT.exists() and RUNTIME_READINESS.exists()
    assert artifact["schema_version"] == "deribit_paper_promoted_runtime_readiness.v1"
    assert artifact["phase"] == "61"
    assert artifact["source"] == "deterministic_phase61_paper_promoted_runtime_readiness"
    assert artifact["source_phase60_post_audit"] == str(PHASE60_POST_AUDIT).replace("\\", "/")


def test_phase61b_artifact_matches_runtime_output() -> None:
    artifact = _runtime_readiness()

    assert artifact == _expected_runtime_readiness()
    assert artifact["runtime_readiness_verdict"] == "PASS"
    assert artifact["paper_promoted"] is True
    assert artifact["promotion_granted"] is True
    assert artifact["ready_for_paper_runtime"] is True
    assert artifact["runtime_enabled"] is False


def test_phase61b_artifact_preserves_no_live_scope_connector_count_and_chain_hash() -> None:
    artifact = _runtime_readiness()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert (
        artifact["source_phase60_post_audit_sha256"]
        == "44b13e4847a8bfcb358bbadd5219dcb93f8004d16f429e29c0ff6a72c08fae67"
    )
    assert artifact["readiness_checks"] == [
        "source_post_audit_passed",
        "promotion_scope_preserved",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "connector_ready_dialects_preserved",
        "deterministic_artifact_chain_preserved",
    ]
    assert artifact["next_blocker"] == "PAPER_PROMOTED_RUNTIME_WIRING_NOT_READY"
