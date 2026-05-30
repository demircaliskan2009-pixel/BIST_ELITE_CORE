from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_start_proposal import propose_deribit_paper_runtime_start
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE65_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json")
PHASE64_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_ENABLEMENT_OPERATOR_APPROVAL_64B.json")
PROPOSAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_REVIEW_PROPOSAL_66B.json")
PHASE64_FALSE_SOURCE_FIELDS = tuple(
    "runtime_enabled runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
PHASE65_FALSE_SOURCE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
FALSE_PROPOSAL_DISABLED_FIELDS = tuple(
    "runtime_start_approved runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase65_execution() -> dict[str, object]:
    return _json(PHASE65_EXECUTION)


def _phase64_approval() -> dict[str, object]:
    return _json(PHASE64_APPROVAL)


def _proposal() -> dict[str, object]:
    return _json(PROPOSAL)


def _expected_proposal() -> dict[str, object]:
    return propose_deribit_paper_runtime_start(_phase65_execution(), _phase64_approval()).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    next_approval["approval_scope"] = dict(next_approval["approval_scope"], **updates)
    return next_approval


def test_phase66b_artifact_has_required_schema_and_source_references() -> None:
    proposal = _proposal()

    assert PHASE65_EXECUTION.exists() and PHASE64_APPROVAL.exists() and PROPOSAL.exists()
    assert proposal["schema_version"] == "deribit_paper_runtime_start_operator_review_proposal.v1"
    assert proposal["phase"] == "66"
    assert proposal["source"] == "deterministic_phase66_paper_runtime_start_proposal"
    assert proposal["source_phase65_runtime_enablement"] == str(PHASE65_EXECUTION).replace("\\", "/")
    assert proposal["source_phase64_runtime_enablement_approval"] == str(PHASE64_APPROVAL).replace("\\", "/")


def test_phase66b_artifact_matches_runtime_output_and_preserves_enabled_not_started_state() -> None:
    proposal = _proposal()

    assert proposal == _expected_proposal()
    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["proposal_type"] == "OPERATOR_PAPER_RUNTIME_START_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["runtime_start_approved"] is False
    assert proposal["runtime_enabled"] is True
    assert proposal["runtime_started"] is False
    assert proposal["paper_promoted"] is True
    assert proposal["promotion_granted"] is True


def test_phase66b_artifact_preserves_no_live_scope_connector_count_and_chain_hashes() -> None:
    proposal = _proposal()

    assert len(connector_ready_dialects()) == 1 and proposal["connector_ready_dialects_count"] == 1
    assert (
        proposal["source_phase65_runtime_enablement_sha256"]
        == "d60bfd007a2c2733a95c09d538abdeb9d253b4bb977e995e36fc7c729ee9c54d"
    )
    assert (
        proposal["source_phase64_runtime_enablement_approval_sha256"]
        == "b5eeb636b0f83ec43b9a17106d2f14055fd40513fc89e8d613cbf8ef64f4d9eb"
    )
    assert proposal["runtime_enabled"] is True
    for field in FALSE_PROPOSAL_DISABLED_FIELDS:
        assert proposal[field] is False
    for field in SAFETY_FLAGS:
        assert proposal[field] is True
    assert proposal["proposal_checks"] == [
        "source_runtime_enablement_executed",
        "runtime_enabled_but_not_started",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]
    assert proposal["reviewer_id"] == "<OPERATOR_REQUIRED>"
    assert proposal["approval_decision"] == "PLACEHOLDER_ONLY"
    assert proposal["next_blocker"] == "OPERATOR_PAPER_RUNTIME_START_APPROVAL_NOT_READY"
