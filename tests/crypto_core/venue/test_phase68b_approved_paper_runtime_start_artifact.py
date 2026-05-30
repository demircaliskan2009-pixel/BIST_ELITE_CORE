from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_approved_paper_runtime_start import execute_deribit_approved_paper_runtime_start
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE67_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_APPROVAL_67B.json")
PHASE65_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json")
EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")
PHASE67_FALSE_SOURCE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
PHASE65_FALSE_SOURCE_FIELDS = tuple(
    "runtime_started live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
FALSE_EXECUTION_DISABLED_FIELDS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase67_approval() -> dict[str, object]:
    return _json(PHASE67_APPROVAL)


def _phase65_execution() -> dict[str, object]:
    return _json(PHASE65_EXECUTION)


def _execution() -> dict[str, object]:
    return _json(EXECUTION)


def _expected_execution(
    phase67: dict[str, object] | None = None,
    phase65: dict[str, object] | None = None,
) -> dict[str, object]:
    return execute_deribit_approved_paper_runtime_start(
        copy.deepcopy(_phase67_approval() if phase67 is None else phase67),
        copy.deepcopy(_phase65_execution() if phase65 is None else phase65),
    ).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def _mutated_scope(approval: dict[str, object], **updates: object) -> dict[str, object]:
    next_approval = copy.deepcopy(approval)
    next_approval["approval_scope"] = dict(next_approval["approval_scope"], **updates)
    return next_approval


def test_phase68b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _execution()

    assert PHASE67_APPROVAL.exists() and PHASE65_EXECUTION.exists() and EXECUTION.exists()
    assert artifact["schema_version"] == "deribit_approved_paper_runtime_start_execution.v1"
    assert artifact["phase"] == "68"
    assert artifact["source"] == "deterministic_phase68_approved_paper_runtime_start_execution"
    assert artifact["source_phase67_runtime_start_approval"] == str(PHASE67_APPROVAL).replace("\\", "/")
    assert artifact["source_phase65_runtime_enablement_execution"] == str(PHASE65_EXECUTION).replace("\\", "/")


def test_phase68b_artifact_matches_runtime_output_and_starts_runtime_without_scope_widening() -> None:
    artifact = _execution()

    assert artifact == _expected_execution()
    assert artifact["approval_status"] == "APPROVED"
    assert artifact["runtime_start_approved"] is True
    assert artifact["runtime_start_execution_status"] == "EXECUTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is True
    assert artifact["paper_promoted"] is True
    assert artifact["promotion_granted"] is True


def test_phase68b_artifact_preserves_no_live_scope_connector_count_and_chain_hashes() -> None:
    artifact = _execution()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    assert (
        artifact["source_phase67_runtime_start_approval_sha256"]
        == "04d4603923a12d518bc49c95800f439558bfb35460f91ff2d6f28b45fd49e5ef"
    )
    assert (
        artifact["source_phase65_runtime_enablement_execution_sha256"]
        == "d60bfd007a2c2733a95c09d538abdeb9d253b4bb977e995e36fc7c729ee9c54d"
    )
    assert (
        artifact["source_phase66_runtime_start_proposal_sha256"]
        == "a1d2f675177819fe1a9427785d42d735979a37b7212a430669e156552f18a53b"
    )
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is True
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert artifact["execution_checks"] == [
        "source_phase67_runtime_start_approval_exists",
        "phase67_runtime_start_approved",
        "phase67_runtime_enabled",
        "phase67_runtime_not_started",
        "source_phase65_runtime_enablement_exists",
        "phase65_runtime_enablement_executed",
        "source_chain_stable",
        "runtime_started_without_scope_widening",
        "no_live_scope_preserved",
        "no_private_execution_scope_preserved",
        "no_scheduler_loop_scope_preserved",
        "connector_ready_dialects_preserved",
    ]
    assert artifact["next_blocker"] == "PAPER_RUNTIME_START_TELEMETRY_NOT_READY"
