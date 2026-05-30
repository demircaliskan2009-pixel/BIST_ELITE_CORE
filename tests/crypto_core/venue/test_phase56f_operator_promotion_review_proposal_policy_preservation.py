from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase56b_operator_promotion_review_proposal_artifact import (
    _phase54_telemetry,
    _phase55_readiness,
    _proposal,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase56f_phase54_phase55_policy_and_proposal_state_are_preserved() -> None:
    phase55 = _phase55_readiness()
    phase54 = _phase54_telemetry()
    proposal = _proposal()

    assert phase55["ready_for_operator_promotion_review"] is True
    assert phase55["promotion_granted"] is False
    assert phase54["telemetry_audit_verdict"] == "PASS"
    assert phase54["execution_verdict"] == "PASS"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["operator_metadata_required"] is True
    assert proposal["promotion_granted"] is False
    assert proposal["ready_for_live"] is False
    assert proposal["ready_for_shadow"] is False
    assert proposal["connector_ready_dialects_count"] == phase55["connector_ready_dialects_count"] == 1


def test_phase56f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase56f_public_feed_registry_was_not_used_as_phase56_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase56" not in text.lower()
    assert "operator_promotion_review_proposal" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
