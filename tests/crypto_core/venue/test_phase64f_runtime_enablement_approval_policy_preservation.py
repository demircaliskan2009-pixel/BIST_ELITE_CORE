from __future__ import annotations

import json

from crypto_core.venue.deribit_manual_review_readiness import evaluate_deribit_manual_review_readiness
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase64b_runtime_enablement_approval_artifact import (
    _approval,
    _phase62_wiring,
    _phase63_proposal,
)


def test_phase64f_readiness_connector_and_source_policy_are_preserved() -> None:
    readiness = evaluate_deribit_manual_review_readiness()
    proposal = _phase63_proposal()
    wiring = _phase62_wiring()
    approval = _approval()

    assert readiness.accepted is True
    assert readiness.pending_rows == ()
    assert len(connector_ready_dialects()) == 1
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert wiring["runtime_enabled"] is False
    assert wiring["runtime_started"] is False
    assert approval["connector_ready_dialects_count"] == 1
    assert (
        approval["source_phase62_runtime_wiring_sha256"]
        == "23f20a820aed0c2d947de8a50ea278e975536ea8057db8990e5231d2fc9ad436"
    )


def test_phase64f_no_bist_leakage() -> None:
    serialized = json.dumps(_approval(), sort_keys=True)

    for forbidden in ("BIST", "Matriks", "VIOP", "KAP", "iDeal"):
        assert forbidden not in serialized
