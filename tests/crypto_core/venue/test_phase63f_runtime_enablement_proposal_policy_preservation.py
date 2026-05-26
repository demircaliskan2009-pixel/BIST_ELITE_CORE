from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase63b_runtime_enablement_proposal_artifact import _proposal


def test_phase63f_connector_ready_dialects_count_is_preserved() -> None:
    proposal = _proposal()

    assert len(connector_ready_dialects()) == 1
    assert proposal["connector_ready_dialects_count"] == 1


def test_phase63f_public_feed_dialects_was_not_mutated_for_phase63() -> None:
    public_feed_dialects = Path("src/crypto_core/venue/public_feed_dialects.py").read_text(encoding="utf-8").lower()

    assert "phase63" not in public_feed_dialects
    assert "runtime_enablement_proposal" not in public_feed_dialects


def test_phase63f_proposal_does_not_change_runtime_enablement_or_live_scope() -> None:
    proposal = _proposal()

    assert proposal["proposal_status"] == "READY_FOR_OPERATOR_REVIEW"
    assert proposal["approval_status"] == "NOT_APPROVED"
    assert proposal["runtime_enabled"] is False
    assert proposal["runtime_started"] is False
    assert proposal["live_ready"] is False
    assert proposal["shadow_ready"] is False
