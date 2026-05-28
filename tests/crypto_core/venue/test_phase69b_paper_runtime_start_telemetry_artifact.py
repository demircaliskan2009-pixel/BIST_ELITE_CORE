from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_start_telemetry import (
    audit_deribit_paper_runtime_start_telemetry,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE68_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_START_EXECUTION_68B.json")
PHASE67_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_OPERATOR_APPROVAL_67B.json")
PHASE65_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_RUNTIME_ENABLEMENT_EXECUTION_65B.json")
ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_START_TELEMETRY_AUDIT_69B.json")

FALSE_SCOPE_FIELDS = tuple(
    "runtime_loop_started runtime_order_routing_enabled live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase68_execution() -> dict[str, object]:
    return _json(PHASE68_EXECUTION)


def _phase67_approval() -> dict[str, object]:
    return _json(PHASE67_APPROVAL)


def _phase65_execution() -> dict[str, object]:
    return _json(PHASE65_EXECUTION)


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def _expected_artifact(
    phase68: dict[str, object] | None = None,
    phase67: dict[str, object] | None = None,
    phase65: dict[str, object] | None = None,
) -> dict[str, object]:
    return audit_deribit_paper_runtime_start_telemetry(
        copy.deepcopy(_phase68_execution() if phase68 is None else phase68),
        copy.deepcopy(_phase67_approval() if phase67 is None else phase67),
        copy.deepcopy(_phase65_execution() if phase65 is None else phase65),
    ).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def test_phase69b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists() and PHASE68_EXECUTION.exists() and PHASE67_APPROVAL.exists() and PHASE65_EXECUTION.exists()
    assert artifact["schema_version"] == "deribit_paper_runtime_start_telemetry_audit.v1"
    assert artifact["phase"] == "69"
    assert artifact["source"] == "deterministic_phase69_paper_runtime_start_telemetry"
    assert artifact["source_phase68_runtime_start_execution"] == str(PHASE68_EXECUTION).replace("\\", "/")


def test_phase69b_artifact_matches_runtime_output_and_required_fields() -> None:
    artifact = _artifact()

    assert artifact == _expected_artifact()
    assert artifact["source_phase68_runtime_start_execution_status"] == "EXECUTED"
    assert artifact["runtime_start_telemetry_status"] == "PASS"
    assert artifact["runtime_mode"] == "PAPER_ONLY_PASSIVE_STARTED"
    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is True
    assert artifact["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"


def test_phase69b_artifact_preserves_no_live_scope_and_connector_state() -> None:
    artifact = _artifact()

    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1
    for field in FALSE_SCOPE_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert artifact["next_blocker"] == "PAPER_RUNTIME_OPERATOR_TRIGGERED_HEARTBEAT_NOT_READY"
