from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.deribit_paper_promotion_readiness import evaluate_deribit_paper_promotion_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_PERFORMANCE_PROMOTION_READINESS_EVALUATION_55B.json")
PHASE54_AUDIT = Path("docs/crypto_core/DERIBIT_APPROVED_PAPER_PERFORMANCE_EXECUTION_TELEMETRY_AUDIT_54B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _phase54_audit() -> dict[str, object]:
    return _json(PHASE54_AUDIT)


def _promotion_result():
    return evaluate_deribit_paper_promotion_readiness(_phase54_audit())


def _artifact() -> dict[str, object]:
    return _json(ARTIFACT)


def test_phase55b_artifact_has_required_schema_and_source_reference() -> None:
    artifact = _artifact()

    assert ARTIFACT.exists()
    assert PHASE54_AUDIT.exists()
    assert artifact["schema_version"] == "deribit_paper_performance_promotion_readiness_evaluation.v1"
    assert artifact["phase"] == "55"
    assert artifact["source"] == "deribit_paper_performance_promotion_readiness_evaluation_v1"
    assert artifact["source_phase54_telemetry_audit"] == str(PHASE54_AUDIT).replace("\\", "/")


def test_phase55b_artifact_matches_deterministic_readiness_output() -> None:
    result = _promotion_result()

    assert result.accepted is True
    assert _artifact() == result.artifact_payload


def test_phase55b_artifact_records_current_readiness_state() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    artifact = _artifact()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert readiness.deferred_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1
    assert artifact["promotion_readiness_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert artifact["ready_for_operator_promotion_review"] is True
    assert artifact["promotion_granted"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
