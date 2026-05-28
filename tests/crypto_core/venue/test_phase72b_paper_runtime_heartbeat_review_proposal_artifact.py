from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    DERIBIT_PHASE72_NEXT_BLOCKER,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
EXPECTED_SHA256 = "24a20d61a317cc4c1685ee1bfcca1f6682912c79f482cddbfc9062c7e4506a25"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _canonical_sha256(d: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_phase72b_artifact_schema_version() -> None:
    art = _json(ARTIFACT)
    assert art["schema_version"] == "deribit_paper_runtime_heartbeat_review_proposal.v1"
    assert art["phase"] == "72"


def test_phase72b_artifact_sha256_stable() -> None:
    art = _json(ARTIFACT)
    assert _canonical_sha256(art) == EXPECTED_SHA256


def test_phase72b_artifact_parity_with_helper() -> None:
    phase71 = _json(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT))
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(phase71)
    artifact = _json(ARTIFACT)
    for key in (
        "schema_version",
        "phase",
        "proposal_status",
        "approval_status",
        "operator_id",
        "reviewed_at_iso",
        "approval_decision",
        "heartbeat_telemetry_status",
        "heartbeat_status",
        "heartbeat_mode",
        "next_blocker",
        "reason_code",
    ):
        assert r.artifact_payload[key] == artifact[key], f"mismatch on {key!r}"


def test_phase72b_artifact_next_blocker() -> None:
    art = _json(ARTIFACT)
    assert art["next_blocker"] == DERIBIT_PHASE72_NEXT_BLOCKER
