from __future__ import annotations

import hashlib
import json
from pathlib import Path

from crypto_core.venue.deribit_paper_runtime_heartbeat_review_proposal import (
    DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT,
    evaluate_deribit_paper_runtime_heartbeat_review_proposal,
)

ARTIFACT = Path("docs/crypto_core/DERIBIT_PAPER_RUNTIME_HEARTBEAT_OPERATOR_REVIEW_PROPOSAL_72B.json")
EXPECTED_SHA256 = "24a20d61a317cc4c1685ee1bfcca1f6682912c79f482cddbfc9062c7e4506a25"


def _load_phase71() -> dict[str, object]:
    return json.loads(Path(DERIBIT_PHASE71_HEARTBEAT_TELEMETRY_AUDIT).read_text(encoding="utf-8"))


def _canonical_sha256(d: dict[str, object]) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def test_phase72g_helper_output_is_deterministic() -> None:
    r1 = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    r2 = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    assert r1 == r2


def test_phase72g_artifact_sha256_stable() -> None:
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert _canonical_sha256(art) == EXPECTED_SHA256


def test_phase72g_helper_and_artifact_sha256_match() -> None:
    r = evaluate_deribit_paper_runtime_heartbeat_review_proposal(_load_phase71())
    art = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    assert _canonical_sha256(r.artifact_payload) == _canonical_sha256(art)
