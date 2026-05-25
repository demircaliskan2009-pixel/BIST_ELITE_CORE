from __future__ import annotations

import json
from pathlib import Path

from crypto_core.venue.contracts import VenueId
from crypto_core.venue.public_feed_dialects import connector_ready_dialects
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact as _phase50_artifact,
)
from tests.crypto_core.venue.test_phase53b_approved_campaign_execution_artifact import _artifact
from tests.crypto_core.venue.test_phase53c_approved_campaign_execution_contract import _phase48_execution

DOC = Path("docs/crypto_core/APPROVED_PAPER_PERFORMANCE_CAMPAIGN_EXECUTION_53A.md")


def test_phase53g_preserves_source_bounds_and_connector_count() -> None:
    artifact = _artifact()
    phase50 = _phase50_artifact()
    phase48 = _phase48_execution()
    ready = connector_ready_dialects()

    assert artifact["hard_cap"] == phase50["hard_cap"] == phase48["hard_cap"] == 3
    assert (
        artifact["per_session_max_trades"]
        == phase50["per_session_max_trades"]
        == phase48["per_session_max_trades"]
        == 2
    )
    assert artifact["connector_ready_dialects_count"] == 1
    assert len(ready) == 1
    assert all(spec.venue_id is VenueId.DERIBIT for spec in ready)


def test_phase53g_artifact_and_doc_have_no_bist_leakage() -> None:
    assert "BIST" not in json.dumps(_artifact(), sort_keys=True)
    assert "BIST" not in DOC.read_text(encoding="utf-8")
