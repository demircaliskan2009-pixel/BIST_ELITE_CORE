from __future__ import annotations

from pathlib import Path

from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase62b_paper_promoted_runtime_wiring_artifact import _runtime_wiring


def test_phase62f_connector_ready_dialects_count_is_preserved() -> None:
    artifact = _runtime_wiring()

    assert len(connector_ready_dialects()) == 1
    assert artifact["connector_ready_dialects_count"] == 1


def test_phase62f_public_feed_dialects_was_not_mutated_for_phase62() -> None:
    public_feed_dialects = Path("src/crypto_core/venue/public_feed_dialects.py").read_text(encoding="utf-8").lower()

    assert "phase62" not in public_feed_dialects
    assert "paper_promoted_runtime_wiring" not in public_feed_dialects


def test_phase62f_wiring_does_not_change_runtime_enablement_or_live_scope() -> None:
    artifact = _runtime_wiring()

    assert artifact["runtime_wiring_status"] == "WIRED"
    assert artifact["runtime_enabled"] is False
    assert artifact["runtime_started"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
