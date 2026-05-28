from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_approval import (
    DERIBIT_PHASE73_APPROVAL_DECISION,
    DERIBIT_PHASE73_APPROVAL_SCOPE,
    DERIBIT_PHASE73_OPERATOR_ID,
    DERIBIT_PHASE73_REVIEWED_AT_ISO,
    execute_deribit_paper_runtime_heartbeat_approval,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_APPROVAL_73B.json")
P72 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
P71 = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_TELEMETRY_AUDIT_71B.json")
EXPECTED_SHA256 = "482be64bad44824f970672f12bcd8418ccafb51df76945c3df4af58a057abfcb"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def test_phase73b_artifact_schema_and_phase() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_operator_approval.v1"
    assert art["phase"] == "73"


def test_phase73b_artifact_sha256_stable() -> None:
    art = _json(ARTIFACT)
    assert _canonical_sha256(art) == EXPECTED_SHA256


def test_phase73b_artifact_parity_with_helper() -> None:
    r = execute_deribit_paper_runtime_heartbeat_approval(
        _json(P72),
        _json(P71),
        operator_id=DERIBIT_PHASE73_OPERATOR_ID,
        approval_decision=DERIBIT_PHASE73_APPROVAL_DECISION,
        reviewed_at_iso=DERIBIT_PHASE73_REVIEWED_AT_ISO,
        approval_scope=DERIBIT_PHASE73_APPROVAL_SCOPE,
    )
    art = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "approval_status",
        "operator_id",
        "reviewed_at_iso",
        "approval_decision",
        "approval_scope",
        "next_blocker",
        "reason_code",
    ):
        assert r.artifact_payload[key] == art[key], f"mismatch on {key!r}"
