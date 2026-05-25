from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_campaign_performance_evaluation import evaluate_deribit_campaign_performance
from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

ARTIFACT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_PERFORMANCE_EVALUATION_50B.json")
PHASE49_AUDIT = Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json")
PHASE48_EXECUTION = Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase49_audit() -> dict[str, object]:
    return _json(PHASE49_AUDIT)


def _performance_result():
    return evaluate_deribit_campaign_performance(_phase49_audit())


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def test_phase50b_artifact_has_required_schema_and_source_references() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE49_AUDIT.exists()
    assert PHASE48_EXECUTION.exists()
    assert artifact["schema_version"] == "deribit_bounded_paper_campaign_performance_evaluation.v1"
    assert artifact["phase"] == "50"
    assert artifact["source"] == "deribit_bounded_paper_campaign_performance_evaluation_v1"
    assert artifact["source_phase49_audit"] == str(PHASE49_AUDIT).replace("\\", "/")
    assert artifact["source_phase48_campaign_execution"] == str(PHASE48_EXECUTION).replace("\\", "/")


def test_phase50b_artifact_matches_deterministic_evaluation_output() -> None:
    result = _performance_result()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase50b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1
    assert artifact["performance_evaluation_verdict"] == "PASS"
    assert artifact["ready_for_operator_review"] is True
    assert artifact["promotion_granted"] is False
    assert artifact["ready_for_live"] is False
    assert artifact["ready_for_shadow"] is False
