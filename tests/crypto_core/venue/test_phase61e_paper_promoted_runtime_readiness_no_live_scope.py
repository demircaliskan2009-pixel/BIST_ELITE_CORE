from __future__ import annotations

from tests.crypto_core.venue.test_phase61b_paper_promoted_runtime_readiness_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _runtime_readiness,
)


def test_phase61e_artifact_preserves_no_live_private_execution_scope() -> None:
    artifact = _runtime_readiness()

    assert artifact["runtime_enabled"] is False
    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True


def test_phase61e_artifact_disables_scheduler_loop_and_shadow_live_readiness() -> None:
    artifact = _runtime_readiness()

    assert artifact["scheduler_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
