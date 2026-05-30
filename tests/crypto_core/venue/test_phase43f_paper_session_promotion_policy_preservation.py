from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase43b_paper_session_promotion_artifact import (
    _phase41_report,
    _promotion_report,
    _session_artifact,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase43f_phase42_hard_cap_and_artifact_bound_are_not_changed() -> None:
    session = _session_artifact()
    report = _promotion_report()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert session["hard_cap"] == report["hard_cap"] == 3
    assert session["max_session_trades"] == report["evaluated_max_session_trades"] == 2
    assert report["evaluated_sessions"] == 1


def test_phase43f_phase41_report_still_passes_but_promotion_stays_not_ready() -> None:
    phase41 = _phase41_report()
    report = _promotion_report()

    assert phase41["report_verdict"] == "PASS"
    assert report["promotion_verdict"] == "NOT_READY"
    assert report["repeated_session_campaign_ready"] is False


def test_phase43f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase43f_public_feed_registry_was_not_used_as_phase43_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase43" not in text.lower()
    assert "promotion_readiness" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
