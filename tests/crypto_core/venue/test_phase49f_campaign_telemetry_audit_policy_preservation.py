from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase49b_campaign_telemetry_audit_artifact import (
    _artifact,
    _phase47_approval,
    _phase48_artifact,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")
PHASE49_FILES = (
    Path("src/crypto_core/venue/deribit_campaign_telemetry_audit.py"),
    Path("docs/crypto_core/BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49A.md"),
    Path("docs/crypto_core/DERIBIT_BOUNDED_PAPER_CAMPAIGN_TELEMETRY_AUDIT_49B.json"),
    Path("docs/crypto_core/DERIBIT_NEXT_BLOCKER_SUMMARY_49H.md"),
)


def test_phase49f_approval_campaign_and_audit_bounds_are_preserved() -> None:
    approval = _phase47_approval()
    phase48 = _phase48_artifact()
    artifact = _artifact()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert approval["campaign_bounds"]["hard_cap"] == phase48["hard_cap"] == artifact["hard_cap"] == 3
    assert (
        approval["campaign_bounds"]["per_session_max_trades"]
        == phase48["per_session_max_trades"]
        == artifact["per_session_max_trades"]
        == 2
    )
    assert (
        approval["campaign_bounds"]["max_sessions_approved"]
        == phase48["max_campaign_sessions"]
        == artifact["max_campaign_sessions"]
        == 3
    )
    assert phase48["duplicate_mutation_blocked"] == artifact["duplicate_mutation_blocked"] is True


def test_phase49f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase49f_public_feed_registry_is_not_used_as_phase49_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase49" not in text.lower()
    assert "campaign_telemetry_audit" not in text.lower()
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000


def test_phase49f_no_bist_leakage_in_phase49_files() -> None:
    for path in PHASE49_FILES:
        text = path.read_text(encoding="utf-8").lower()

        for forbidden in ("bist", "ideal", "matriks", "kap", "viop"):
            assert forbidden not in text
