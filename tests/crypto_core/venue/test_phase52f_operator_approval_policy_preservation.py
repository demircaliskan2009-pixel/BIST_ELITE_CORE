from __future__ import annotations

from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects, dialects_for_venue
from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import (
    _approval,
    _phase49_audit,
    _phase50_evaluation,
)

PUBLIC_FEED_DIALECTS = Path("src/crypto_core/venue/public_feed_dialects.py")


def test_phase52f_hard_cap_and_trade_cap_are_not_changed() -> None:
    evaluation = _phase50_evaluation()
    audit = _phase49_audit()
    approval = _approval()
    scope = approval["approval_scope"]

    assert isinstance(scope, dict)
    assert audit["hard_cap"] == evaluation["hard_cap"] == 3
    assert audit["per_session_max_trades"] == evaluation["per_session_max_trades"] == 2
    assert scope["hard_cap_unchanged"] is True
    assert scope["per_session_max_trades_unchanged"] is True
    assert approval["promotion_granted"] is False


def test_phase52f_connector_ready_dialects_remains_one_deribit_public_dialect() -> None:
    ready = connector_ready_dialects()

    assert len(ready) == 1
    assert ready[0].venue_id is VenueId.DERIBIT


def test_phase52f_public_feed_registry_was_not_used_as_phase52_state_storage() -> None:
    text = PUBLIC_FEED_DIALECTS.read_text(encoding="utf-8")
    deribit = dialects_for_venue(VenueId.DERIBIT)[0]

    assert "phase52" not in text.lower()
    assert "operator_approval" not in text
    assert deribit.supports_checksum is False
    assert deribit.max_gap_tolerance == 0
    assert deribit.max_staleness_ns == 2_000_000_000
    assert deribit.max_receive_lag_ns == 1_000_000_000
