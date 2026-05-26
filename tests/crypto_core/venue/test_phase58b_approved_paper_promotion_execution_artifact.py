from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_promotion_execution import (
    DERIBIT_PHASE58_APPROVED_ACTION,
    DERIBIT_PHASE58_PROMOTION_SCOPE,
    execute_deribit_approved_paper_promotion,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE57_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_OPERATOR_PROMOTION_APPROVAL_57B.json")
PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json")
FALSE_EXECUTION_FLAGS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase57_approval() -> dict[str, object]:
    return _json(PHASE57_APPROVAL)


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _execution() -> dict[str, object]:
    return _json(EXECUTION)


def _expected_execution() -> dict[str, object]:
    return execute_deribit_approved_paper_promotion(_phase57_approval(), _phase55_readiness()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping["approval_scope"] = dict(next_mapping["approval_scope"], **updates)
    return next_mapping


def test_phase58b_artifact_has_required_schema_and_source_references() -> None:
    execution = _execution()

    assert PHASE57_APPROVAL.exists() and PHASE55_READINESS.exists() and EXECUTION.exists()
    assert execution["schema_version"] == "deribit_approved_paper_promotion_execution.v1"
    assert execution["phase"] == "58"
    assert execution["source"] == "deterministic_phase58_approved_paper_promotion_execution"
    assert execution["source_phase57_operator_promotion_approval"] == str(PHASE57_APPROVAL).replace("\\", "/")
    assert execution["source_phase55_promotion_readiness"] == str(PHASE55_READINESS).replace("\\", "/")


def test_phase58b_artifact_matches_runtime_output_and_executes_paper_promotion_only() -> None:
    execution = _execution()

    assert execution == _expected_execution()
    assert execution["promotion_execution_status"] == "EXECUTED"
    assert execution["approved_action"] == DERIBIT_PHASE58_APPROVED_ACTION
    assert execution["promotion_granted"] is True
    assert execution["promotion_scope"] == DERIBIT_PHASE58_PROMOTION_SCOPE
    assert execution["paper_promoted"] is True
    assert execution["approval_status"] == "APPROVED"
    assert execution["approval_decision"] == "APPROVE_PAPER_PROMOTION_REVIEW"
    assert execution["operator_id"] == "demir_operator"


def test_phase58b_artifact_preserves_no_live_no_execution_scope() -> None:
    execution = _execution()

    assert len(connector_ready_dialects()) == 1 and execution["connector_ready_dialects_count"] == 1
    for field in FALSE_EXECUTION_FLAGS:
        assert execution[field] is False
    for field in SAFETY_FLAGS:
        assert execution[field] is True
    assert execution["next_blocker"] == "PAPER_PROMOTION_EXECUTION_TELEMETRY_NOT_READY"
