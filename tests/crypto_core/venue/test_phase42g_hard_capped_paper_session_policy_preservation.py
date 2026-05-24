from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase41b_paper_run_telemetry_report_artifact import _report as _phase41_report
from tests.crypto_core.venue.test_phase42b_hard_capped_paper_session_artifact import (
    PHASE40_ARTIFACT,
    _artifact,
    _json,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase42g_phase40_and_phase41_artifacts_remain_present_and_bounded() -> None:
    phase40 = _json(PHASE40_ARTIFACT)
    phase41 = _phase41_report()

    assert phase40["max_trades"] == 1
    assert phase41["report_verdict"] == "PASS"
    assert phase41["next_blocker"] == "HARD_CAPPED_MULTI_RUN_SESSION_NOT_READY"


def test_phase42g_session_hard_cap_is_conservative_and_artifact_stays_within_it() -> None:
    artifact = _artifact()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert artifact["hard_cap"] == 3
    assert artifact["max_session_trades"] == 2
    assert artifact["trades_requested"] <= artifact["max_session_trades"] <= artifact["hard_cap"]


def test_phase42g_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase42g_public_feed_registry_was_not_used_as_phase42_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase42" not in text.lower()
    assert "paper_session" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
