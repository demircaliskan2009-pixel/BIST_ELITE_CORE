from __future__ import annotations

from tests.crypto_core.venue.test_phase67b_paper_runtime_start_approval_artifact import (
    APPROVAL_SCOPE_TRUE_FIELDS,
    FALSE_APPROVAL_DISABLED_FIELDS,
    SAFETY_FLAGS,
    _approval,
)


def test_phase67e_artifact_keeps_runtime_enabled_without_start_or_live_scope() -> None:
    approval = _approval()

    assert approval["runtime_start_approved"] is True
    assert approval["runtime_enabled"] is True
    assert approval["runtime_started"] is False
    for field in FALSE_APPROVAL_DISABLED_FIELDS:
        assert approval[field] is False
    for field in SAFETY_FLAGS:
        assert approval[field] is True


def test_phase67e_artifact_keeps_scheduler_loop_and_shadow_live_disabled() -> None:
    approval = _approval()

    assert approval["scheduler_enabled"] is False
    assert approval["auto_loop_enabled"] is False
    assert approval["live_ready"] is False
    assert approval["shadow_ready"] is False
    for field in APPROVAL_SCOPE_TRUE_FIELDS:
        assert approval["approval_scope"][field] is True
