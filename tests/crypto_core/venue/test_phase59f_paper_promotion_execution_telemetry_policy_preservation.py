from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase59b_paper_promotion_execution_telemetry_artifact import _audit


def test_phase59f_connector_ready_dialects_count_is_preserved() -> None:
    artifact = _audit()

    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1


def test_phase59f_public_feed_dialects_was_not_mutated_for_phase59() -> None:
    public_feed_dialects = Path("src/crypto_core/venue/public_feed_dialects.py").read_text(encoding="utf-8").lower()

    assert "phase59" not in public_feed_dialects
    assert "paper_promotion_telemetry_audit" not in public_feed_dialects


def test_phase59f_promotion_state_remains_no_live_and_report_only() -> None:
    artifact = _audit()

    assert artifact["promotion_granted"] is True
    assert artifact["paper_promoted"] is True
    assert artifact["report_only"] is True
    assert artifact["no_new_execution"] is True
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
