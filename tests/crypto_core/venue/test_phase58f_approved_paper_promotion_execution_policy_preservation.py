from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase58b_approved_paper_promotion_execution_artifact import _execution


def test_phase58f_connector_ready_dialects_count_is_preserved() -> None:
    execution = _execution()

    assert len(connector_ready_dialects()) == 1
    assert execution["connector_ready_dialects_count"] == 1


def test_phase58f_public_feed_dialects_was_not_mutated_for_phase58() -> None:
    public_feed_dialects = Path("src/crypto_core/venue/public_feed_dialects.py").read_text(encoding="utf-8").lower()

    assert "phase58" not in public_feed_dialects
    assert "approved_paper_promotion" not in public_feed_dialects


def test_phase58f_promotion_does_not_change_live_or_shadow_readiness() -> None:
    execution = _execution()

    assert execution["promotion_granted"] is True
    assert execution["promotion_scope"] == "PAPER_ONLY_SIMULATION_ONLY"
    assert execution["live_ready"] is False
    assert execution["shadow_ready"] is False
