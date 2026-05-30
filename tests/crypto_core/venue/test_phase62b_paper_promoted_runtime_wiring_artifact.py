from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_promoted_runtime_wiring import wire_deribit_paper_promoted_runtime
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE61_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_READINESS_61B.json")
RUNTIME_WIRING = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json")
FALSE_RUNTIME_FIELDS = tuple(
    "runtime_started runtime_enabled live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase61_readiness() -> dict[str, object]:
    return _json(PHASE61_READINESS)


def _runtime_wiring() -> dict[str, object]:
    return _json(RUNTIME_WIRING)


def _expected_runtime_wiring() -> dict[str, object]:
    return wire_deribit_paper_promoted_runtime(_phase61_readiness()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def test_phase62b_artifact_has_required_schema_and_source_reference() -> None:
    artifact = _runtime_wiring()

    assert PHASE61_READINESS.exists() and RUNTIME_WIRING.exists()
    assert artifact["schema_version"] == "deribit_paper_promoted_runtime_wiring.v1"
    assert artifact["phase"] == "62"
    assert artifact["source"] == "deterministic_phase62_paper_promoted_runtime_wiring"
    assert artifact["source_phase61_runtime_readiness"] == str(PHASE61_READINESS).replace("\\", "/")
    assert (
        artifact["source_phase60_post_audit"]
        == "docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_POST_AUDIT_60B.json"
    )


def test_phase62b_artifact_matches_runtime_output_and_wires_without_enabling_runtime() -> None:
    artifact = _runtime_wiring()

    assert artifact == _expected_runtime_wiring()
    assert artifact["runtime_wiring_status"] == "WIRED"
    assert artifact["ready_for_paper_runtime"] is True
    assert artifact["paper_promoted"] is True
    assert artifact["promotion_granted"] is True
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert artifact["runtime_enabled"] is False
    assert artifact["runtime_started"] is False


def test_phase62b_artifact_preserves_no_live_scope_connector_count_and_chain_hash() -> None:
    artifact = _runtime_wiring()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    for field in FALSE_RUNTIME_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert (
        artifact["source_phase61_runtime_readiness_sha256"]
        == "c99038090b76261f7dc64a568995f87ddf4a0764f25704d9f60c99dff747dffb"
    )
    assert artifact["wiring_checks"] == [
        "source_readiness_passed",
        "promotion_scope_preserved",
        "runtime_not_started",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]
    assert artifact["next_blocker"] == "PAPER_PROMOTED_RUNTIME_ENABLEMENT_APPROVAL_NOT_READY"
