from __future__ import annotations

from tests.crypto_core.venue.test_phase65b_approved_paper_runtime_enablement_artifact import (
    FALSE_EXECUTION_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _execution,
)


def test_phase65e_artifact_enables_runtime_without_live_or_private_execution_scope() -> None:
    artifact = _execution()

    assert artifact["runtime_enabled"] is True
    assert artifact["runtime_started"] is False
    for field in FALSE_EXECUTION_DISABLED_FIELDS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True


def test_phase65e_artifact_keeps_scheduler_loop_and_shadow_live_disabled() -> None:
    artifact = _execution()

    assert artifact["scheduler_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
