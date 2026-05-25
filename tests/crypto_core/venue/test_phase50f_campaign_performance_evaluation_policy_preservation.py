from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact,
    _phase49_audit,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase50f_hard_cap_and_phase49_policy_are_preserved() -> None:
    phase49 = _phase49_audit()
    artifact = _artifact()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert phase49["hard_cap"] == artifact["hard_cap"] == 3
    assert phase49["per_session_max_trades"] == artifact["per_session_max_trades"] == 2
    assert phase49["connector_ready_dialects_count"] == artifact["connector_ready_dialects_count"] == 1
    assert artifact["promotion_granted"] is False
    assert artifact["ready_for_live"] is False
    assert artifact["ready_for_shadow"] is False


def test_phase50f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase50f_public_feed_registry_was_not_used_as_phase50_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase50" not in text.lower()
    assert "performance_evaluation" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
