from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT,
    DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT_SHA256,
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")


def _load_phase71() -> dict[str, object]:
    return json.loads(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT).read_text(encoding="utf-8"))


def test_phase72f_policy_preserves_phase71_source_chain() -> None:
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert art["source_phase71_heartbeat_telemetry_audit"] == DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT
    assert art["source_phase71_heartbeat_telemetry_audit_sha256"] == DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256


def test_phase72f_policy_preserves_phase70_source_chain() -> None:
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert art["source_phase70_operator_triggered_heartbeat"] == DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT
    assert (
        art["source_phase70_operator_triggered_heartbeat_sha256"] == DERIBIT_PHASE70_OPERATOR_TRIGGERED_HEARTBEAT_SHA256
    )


def test_phase72f_policy_rejects_phase70_source_chain_drift() -> None:
    bad = dict(_load_phase71())
    bad["source_phase70_operator_triggered_heartbeat_sha256"] = "0" * 64
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(bad)
    assert r.accepted is False
    assert any("phase70_source_chain_drift" in rc for rc in r.rejection_reasons)


def test_phase72f_policy_rejects_phase69_source_chain_drift() -> None:
    bad = dict(_load_phase71())
    bad["source_phase69_runtime_start_telemetry_sha256"] = "0" * 64
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(bad)
    assert r.accepted is False
    assert any("phase69_source_chain_drift" in rc for rc in r.rejection_reasons)


def test_phase72f_proposal_scope_preserved() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    assert r.artifact_payload["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert r.artifact_payload["approval_status"] == "NOT_APPROVED"
    assert r.artifact_payload["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
