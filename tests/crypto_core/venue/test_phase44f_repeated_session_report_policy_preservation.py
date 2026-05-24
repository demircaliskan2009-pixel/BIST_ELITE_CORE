from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import (
    _promotion_readiness,
    _report_pack,
    _session_artifact,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase44f_phase42_hard_cap_and_artifact_bound_are_not_changed() -> None:
    session = _session_artifact()
    promotion = _promotion_readiness()
    pack = _report_pack()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert session["hard_cap"] == promotion["hard_cap"] == pack["hard_cap"] == 3
    assert session["max_session_trades"] == promotion["evaluated_max_session_trades"] == 2
    assert pack["per_session_max_trades"] == 2


def test_phase44f_promotion_readiness_stays_not_ready_until_reevaluation() -> None:
    promotion = _promotion_readiness()
    pack = _report_pack()

    assert promotion["promotion_verdict"] == "NOT_READY"
    assert pack["report_pack_verdict"] == "PASS"
    assert pack["promotion_granted"] is False


def test_phase44f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase44f_public_feed_registry_was_not_used_as_phase44_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase44" not in text.lower()
    assert "repeated_session" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
