from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase44b_repeated_session_report_pack_artifact import _report_pack
from tests.crypto_core.venue.test_phase47b_operator_approval_artifact import _approval as _phase47_approval
from tests.crypto_core.venue.test_phase48b_campaign_execution_artifact import _artifact

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")
PHASE48_FILES = (
    Path("src/crypto_core/venue/deribit_bounded_paper_campaign.py"),
    Path("docs/crypto_core/BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_GATE_48A.md"),
    Path("docs/crypto_core/DERIBIT_BOUNDED_REPEATED_PAPER_CAMPAIGN_EXECUTION_48B.json"),
    Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_48H.md"),
)


def test_phase48g_approval_and_session_bounds_are_not_changed() -> None:
    approval = _phase47_approval()
    report_pack = _report_pack()
    artifact = _artifact()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert approval["campaign_bounds"]["hard_cap"] == report_pack["hard_cap"] == artifact["hard_cap"] == 3
    assert approval["campaign_bounds"]["per_session_max_trades"] == report_pack["per_session_max_trades"] == 2
    assert artifact["per_session_max_trades"] == 2
    assert approval["campaign_bounds"]["max_sessions_approved"] == artifact["max_campaign_sessions"] == 3


def test_phase48g_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase48g_public_feed_registry_is_not_used_as_phase48_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase48" not in text.lower()
    assert "bounded_paper_campaign" not in text.lower()
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000


def test_phase48g_no_bist_leakage_in_phase48_files() -> None:
    for path in PHASE48_FILES:
        text = path.read_text(encoding="utf-8").lower()

        for forbidden in ("bist", "ideal", "matriks", "kap", "viop"):
            assert forbidden not in text
