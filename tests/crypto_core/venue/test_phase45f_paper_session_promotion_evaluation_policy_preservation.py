from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.deribit_hard_capped_paper_session import DERIBIT_PAPER_SESSION_HARD_CAP
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase45b_paper_session_promotion_evaluation_artifact import (
    _evaluation,
    _promotion_readiness,
    _report_pack,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase45f_hard_cap_and_existing_artifacts_are_not_changed() -> None:
    promotion = _promotion_readiness()
    pack = _report_pack()
    evaluation = _evaluation()

    assert DERIBIT_PAPER_SESSION_HARD_CAP == 3
    assert pack["hard_cap"] == evaluation["hard_cap"] == 3
    assert promotion["required_future_sessions_minimum"] == evaluation["required_future_sessions_minimum"] == 3
    assert pack["per_session_max_trades"] == evaluation["evaluated_max_session_trades"] == 2
    assert pack["promotion_granted"] is False


def test_phase45f_evaluation_requires_operator_approval_before_promotion() -> None:
    evaluation = _evaluation()

    assert evaluation["promotion_verdict"] == "READY_FOR_OPERATOR_REVIEW"
    assert evaluation["promotion_granted"] is False
    assert evaluation["operator_approval_required"] is True
    assert evaluation["next_blocker"] == "OPERATOR_APPROVAL_FOR_BOUNDED_REPEATED_PAPER_CAMPAIGN"


def test_phase45f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase45f_public_feed_registry_was_not_used_as_phase45_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase45" not in text.lower()
    assert "promotion_evaluation" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
