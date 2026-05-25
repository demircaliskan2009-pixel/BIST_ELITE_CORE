from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase51b_operator_review_proposal_artifact import (
    _phase50_evaluation,
    _proposal,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase51f_phase50_policy_and_proposal_state_are_preserved() -> None:
    source = _phase50_evaluation()
    proposal = _proposal()

    assert source["performance_evaluation_verdict"] == "PASS"
    assert source["ready_for_operator_review"] is True
    assert source["promotion_granted"] is False
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["promotion_granted"] is False
    assert proposal["connector_ready_dialects_count"] == source["connector_ready_dialects_count"] == 1


def test_phase51f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase51f_public_feed_registry_was_not_used_as_phase51_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase51" not in text.lower()
    assert "operator_review_proposal" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
