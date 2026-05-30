from __future__ import annotations

from tests.crypto_core.venue.test_phase66b_paper_runtime_start_proposal_artifact import (
    FALSE_PROPOSAL_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _proposal,
)


def test_phase66e_artifact_keeps_runtime_enabled_without_start_or_live_scope() -> None:
    proposal = _proposal()

    assert proposal["runtime_enabled"] is True
    assert proposal["runtime_started"] is False
    for field in FALSE_PROPOSAL_DISABLED_FIELDS:
        assert proposal[field] is False
    for field in SAFETY_FLAGS:
        assert proposal[field] is True


def test_phase66e_artifact_keeps_scheduler_loop_and_shadow_live_disabled() -> None:
    proposal = _proposal()

    assert proposal["scheduler_enabled"] is False
    assert proposal["auto_loop_enabled"] is False
    assert proposal["live_ready"] is False
    assert proposal["shadow_ready"] is False
