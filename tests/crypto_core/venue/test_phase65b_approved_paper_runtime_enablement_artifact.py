from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_enablement import (
    execute_deribit_approved_paper_runtime_enablement,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE64_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_64B.json")
PHASE62_WIRING = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTED_RUNTIME_WIRING_62B.json")
EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json")
PHASE64_FALSE_SOURCE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
FALSE_EXECUTION_DISABLED_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase64_approval() -> dict[str, object]:
    return _json(PHASE64_APPROVAL)


def _phase62_wiring() -> dict[str, object]:
    return _json(PHASE62_WIRING)


def _execution() -> dict[str, object]:
    return _json(EXECUTION)


def _expected_execution() -> dict[str, object]:
    return execute_deribit_approved_paper_runtime_enablement(_phase64_approval(), _phase62_wiring()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    next_approval["approval_scope"] = dict(next_approval["approval_scope"], **updates)
    return next_approval


def test_phase65b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _execution()

    assert PHASE64_APPROVAL.exists() and PHASE62_WIRING.exists() and EXECUTION.exists()
    assert artifact["schema_version"] == "deribit_approved_paper_runtime_enablement_execution.v1"
    assert artifact["phase"] == "65"
    assert artifact["source"] == "deterministic_phase65_approved_paper_runtime_enablement_execution"
    assert artifact["source_phase64_runtime_enablement_approval"] == str(PHASE64_APPROVAL).replace("\\", "/")
    assert artifact["source_phase62_runtime_wiring"] == str(PHASE62_WIRING).replace("\\", "/")


def test_phase65b_artifact_matches_runtime_output_and_enables_runtime_without_start() -> None:
    artifact = _execution()

    assert artifact == _expected_execution()
    assert artifact["approval_status"] == "APPROVED"
    assert artifact["runtime_enablement_approved"] is True
    assert artifact["runtime_enablement_execution_status"] == "EXECUTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    assert artifact["paper_promoted"] is True
    assert artifact["promotion_granted"] is True


def test_phase65b_artifact_preserves_no_live_scope_connector_count_and_chain_hashes() -> None:
    artifact = _execution()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    assert artifact["runtime_enabled"] is True
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert (
        artifact["source_phase64_runtime_enablement_approval_sha256"]
        == "b5eeb636b0f83ec43b9a17106d2f14055fd40513fc89e8d613cbf8ef64f4d9eb"
    )
    assert (
        artifact["source_phase62_runtime_wiring_sha256"]
        == "23f20a820aed0c2d947de8a50ea278e975536ea8057db8990e5231d2fc9ad436"
    )
    assert artifact["execution_checks"] == [
        "source_phase64_runtime_enablement_approval_exists",
        "phase64_runtime_enablement_approved",
        "phase64_runtime_not_started",
        "source_phase62_runtime_wiring_exists",
        "phase62_runtime_wiring_wired",
        "source_chain_stable",
        "runtime_enabled_without_runtime_start",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]
    assert artifact["next_blocker"] == "PAPER_RUNTIME_START_PROPOSAL_NOT_READY"
