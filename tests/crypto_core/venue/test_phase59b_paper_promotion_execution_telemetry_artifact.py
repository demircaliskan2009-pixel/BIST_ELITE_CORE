from __future__ import annotations

import copy
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_promotion_telemetry_audit import (
    audit_deribit_paper_promotion_execution_telemetry,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

PHASE58_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PROMOTION_EXECUTION_58B.json")
PHASE55_READINESS = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
AUDIT = Path("docs/crypto_core/DERIBIT_PAPER_PROMOTION_EXECUTION_TELEMETRY_AUDIT_59B.json")
FALSE_EXECUTION_FLAGS = tuple(
    "live_ready shadow_ready scheduler_enabled auto_loop_enabled live_enabled shadow_enabled campaign_execution session_execution run_execution ledger_mutation ledger_mutated".split()
)
SAFETY_FLAGS = tuple(
    "no_private_api no_credentials no_exchange_orders no_execution_adapter no_strategy_signal no_order_routing no_scheduler no_automatic_paper_loop no_shadow no_live".split()
)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase58_execution() -> dict[str, object]:
    return _json(PHASE58_EXECUTION)


def _phase55_readiness() -> dict[str, object]:
    return _json(PHASE55_READINESS)


def _audit() -> dict[str, object]:
    return _json(AUDIT)


def _expected_audit() -> dict[str, object]:
    return audit_deribit_paper_promotion_execution_telemetry(
        _phase58_execution(), _phase55_readiness()
    ).artifact_payload


def _mutated(mapping: dict[str, object], **updates: object) -> dict[str, object]:
    next_mapping = copy.deepcopy(mapping)
    next_mapping.update(updates)
    return next_mapping


def test_phase59b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _audit()

    assert PHASE58_EXECUTION.exists() and PHASE55_READINESS.exists() and AUDIT.exists()
    assert artifact["schema_version"] == "deribit_paper_promotion_execution_telemetry_audit.v1"
    assert artifact["phase"] == "59"
    assert artifact["source"] == "deterministic_phase59_paper_promotion_execution_telemetry_audit"
    assert artifact["source_phase58_execution"] == str(PHASE58_EXECUTION).replace("\\", "/")
    assert artifact["source_phase55_promotion_readiness"] == str(PHASE55_READINESS).replace("\\", "/")


def test_phase59b_artifact_matches_runtime_output() -> None:
    artifact = _audit()

    assert artifact == _expected_audit()
    assert artifact["telemetry_audit_status"] == "AUDITED"
    assert artifact["telemetry_audit_verdict"] == "PASS"
    assert artifact["execution_verdict"] == "PASS"
    assert artifact["promotion_execution_status"] == "EXECUTED"
    assert artifact["promotion_granted"] is True
    assert artifact["paper_promoted"] is True
    assert artifact["report_only"] is True
    assert artifact["no_new_execution"] is True


def test_phase59b_artifact_preserves_no_live_scope_and_connector_count() -> None:
    artifact = _audit()

    assert len(connector_ready_dialects()) == 1 and artifact["connector_ready_dialects_count"] == 1
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert artifact["next_blocker"] == "PAPER_PROMOTION_EXECUTION_POST_AUDIT_NOT_READY"
