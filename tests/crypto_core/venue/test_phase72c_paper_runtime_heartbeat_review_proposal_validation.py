from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256,
    DERIBIT_PHASE72_NEXT_BLOCKER,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_phase71() -> dict[str, object]:
    return _json(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT))


def test_phase72c_helper_accepts_valid_phase71_artifact() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    assert r.accepted is True
    assert r.rejection_reasons == ()
    assert r.reason_code == "deribit_paper_runtime_heartbeat_review_proposal:accepted"


def test_phase72c_artifact_proposal_fields() -> None:
    art = _json(ARTIFACT)
    assert art["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert art["approval_status"] == "NOT_APPROVED"
    assert art["operator_id"] is None
    assert art["reviewed_at_iso"] is None
    assert art["approval_decision"] is None
    assert art["next_blocker"] == DERIBIT_PHASE72_NEXT_BLOCKER


def test_phase72c_phase71_provenance_chain_enforced() -> None:
    artifact = _json(ARTIFACT)
    assert artifact["source_phase71_heartbeat_telemetry_audit"] == DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT
    assert (
        artifact["source_phase71_heartbeat_telemetry_audit_sha256"] == DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT_SHA256
    )


def test_phase72c_rejection_on_bad_phase71_schema() -> None:
    bad = dict(_load_phase71())
    bad["schema_version"] = "wrong.v1"
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(bad)
    assert r.accepted is False
    assert any("phase71_artifact_malformed" in rc for rc in r.rejection_reasons)


def test_phase72c_rejection_on_connector_dialect_mismatch(monkeypatch: object) -> None:
    import crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal as mod

    monkeypatch.setattr(mod, "_deribit_connector_ready", lambda: False)
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    assert r.accepted is False
    assert any("connector_ready_dialects_mismatch" in rc for rc in r.rejection_reasons)
