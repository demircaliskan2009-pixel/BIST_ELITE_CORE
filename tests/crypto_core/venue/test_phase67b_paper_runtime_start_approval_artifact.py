from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_start_approval import (
    DERIBIT_PHASE67_REVIEWED_AT_ISO,
    execute_deribit_paper_runtime_start_approval,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE66_PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_REVIEW_PROPOSAL_66B.json")
PHASE65_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json")
APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_APPROVAL_67B.json")
APPROVAL_METADATA = {
    "operator_id": "demir_operator",
    "reviewed_at_iso": DERIBIT_PHASE67_REVIEWED_AT_ISO,
    "approval_decision": "APPROVE_PAPER_RUNTIME_START_REVIEW",
}
APPROVAL_SCOPE_TRUE_FIELDS = tuple(
    "paper_only simulation_only deribit_public_market_data_only no_private_api no_credentials no_exchange_orders no_execution_adapter no_order_routing no_scheduler no_automatic_paper_loop no_strategy_signal no_shadow no_live".split()
)
PHASE66_FALSE_SOURCE_FIELDS = tuple(
    "runtime_start_approved runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
PHASE65_FALSE_SOURCE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
FALSE_APPROVAL_DISABLED_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase66_proposal() -> dict[str, object]:
    return _json(PHASE66_PROPOSAL)


def _phase65_execution() -> dict[str, object]:
    return _json(PHASE65_EXECUTION)


def _approval() -> dict[str, object]:
    return _json(APPROVAL)


def _expected_approval(
    phase66: dict[str, object] | None = None,
    phase65: dict[str, object] | None = None,
) -> dict[str, object]:
    return execute_deribit_paper_runtime_start_approval(
        copy.deepcopy(_phase66_proposal() if phase66 is None else phase66),
        copy.deepcopy(_phase65_execution() if phase65 is None else phase65),
        reviewed_at_iso=APPROVAL_METADATA["reviewed_at_iso"],
    ).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _is_utc_z(value: object) -> bool:
    if not isinstance(value, str) or not value.endswith("Z"):
        return False
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).tzinfo == timezone.utc
    except ValueError:
        return False


def test_phase67b_artifact_has_required_schema_and_source_references() -> None:
    approval = _approval()

    assert PHASE66_PROPOSAL.exists() and PHASE65_EXECUTION.exists() and APPROVAL.exists()
    assert approval["schema_version"] == "deribit_paper_runtime_start_operator_approval.v1"
    assert approval["phase"] == "67"
    assert approval["source"] == "deterministic_phase67_paper_runtime_start_approval"
    assert approval["source_phase66_runtime_start_proposal"] == str(PHASE66_PROPOSAL).replace("\\", "/")
    assert approval["source_phase65_runtime_enablement"] == str(PHASE65_EXECUTION).replace("\\", "/")


def test_phase67b_artifact_matches_runtime_output_and_approved_metadata() -> None:
    approval = _approval()

    assert approval == _expected_approval()
    assert approval["approval_status"] == "APPROVED"
    for field, expected in APPROVAL_METADATA.items():
        assert approval[field] == expected
    assert _is_utc_z(approval["reviewed_at_iso"])
    assert approval["runtime_start_approved"] is True
    assert approval["runtime_enabled"] is True
    assert approval["runtime_started"] is False


def test_phase67b_artifact_preserves_runtime_enabled_no_live_scope_and_chain_hashes() -> None:
    approval = _approval()

    assert len(connector_ready_dialects()) == 1 and approval["connector_ready_dialects_count"] == 1
    assert (
        approval["source_phase66_runtime_start_proposal_sha256"]
        == "a1d2f675177819fe1a9427785d42d735979a37b7212a430669e156552f18a53b"
    )
    assert (
        approval["source_phase65_runtime_enablement_sha256"]
        == "d60bfd007a2c2733a95c09d538abdeb9d253b4bb977e995e36fc7c729ee9c54d"
    )
    assert approval["source_phase66_proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert approval["source_phase66_approval_status"] == "NOT_APPROVED"
    assert approval["source_phase65_runtime_enablement_status"] == "EXECUTED"
    assert approval["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    for field in FALSE_APPROVAL_DISABLED_FIELDS:
        assert approval[field] is False
    for field in SAFETY_FLAGS:
        assert approval[field] is True
    for field in APPROVAL_SCOPE_TRUE_FIELDS:
        assert approval["approval_scope"][field] is True
