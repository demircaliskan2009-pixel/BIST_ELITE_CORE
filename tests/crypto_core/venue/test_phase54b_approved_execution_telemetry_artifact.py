from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_approved_execution_telemetry_audit import (
    audit_deribit_approved_execution_telemetry,
)
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

ARTIFACT = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json")
PHASE53_EXECUTION = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53B.json")
PHASE52_APPROVAL = Path("docs/crypto_core/DERIBIT_PAPER_CAMPAIGN_PERFORMANCE_OPERATOR_APPROVAL_52B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase53_execution() -> dict[str, object]:
    return _json(PHASE53_EXECUTION)


def _phase52_approval() -> dict[str, object]:
    return _json(PHASE52_APPROVAL)


def _telemetry_result():
    return audit_deribit_approved_execution_telemetry(_phase53_execution(), _phase52_approval())


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def test_phase54b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE53_EXECUTION.exists()
    assert PHASE52_APPROVAL.exists()
    assert artifact["schema_version"] == "deribit_approved_paper_performance_execution_telemetry_audit.v1"
    assert artifact["phase"] == "54"
    assert artifact["source"] == "deribit_approved_paper_performance_execution_telemetry_audit_v1"
    assert artifact["source_phase53_execution"] == str(PHASE53_EXECUTION).replace("\\", "/")
    assert artifact["source_phase52_approval"] == str(PHASE52_APPROVAL).replace("\\", "/")


def test_phase54b_artifact_matches_deterministic_telemetry_output() -> None:
    result = _telemetry_result()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase54b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1
    assert artifact["telemetry_audit_verdict"] == "PASS"
    assert artifact["promotion_granted"] is False
    assert artifact["ready_for_live"] is False
    assert artifact["ready_for_shadow"] is False
