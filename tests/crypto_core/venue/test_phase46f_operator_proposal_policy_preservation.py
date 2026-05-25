from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase46b_operator_proposal_artifact import _phase44_report_pack, _proposal

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase46f_hard_cap_and_trade_bounds_are_not_changed() -> None:
    report_pack = _phase44_report_pack()
    proposal = _proposal()
    bounds = proposal["campaign_bounds"]

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert report_pack["hard_cap"] == bounds["hard_cap"] == 3
    assert report_pack["per_session_max_trades"] == bounds["per_session_max_trades"] == 2
    assert bounds["max_sessions_proposed"] == 3
    assert bounds["max_total_paper_trades_proposed"] == 6


def test_phase46f_proposal_does_not_approve_or_promote() -> None:
    proposal = _proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["promotion_granted"] is False
    assert proposal["operator_approval_required"] is True


def test_phase46f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase46f_public_feed_registry_was_not_used_as_phase46_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase46" not in text.lower()
    assert "operator_proposal" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
