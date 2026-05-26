from __future__ import annotations

from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import (
    FALSE_EXECUTION_FLAGS,
    SAFETY_FLAGS,
    _post_audit,
)


def test_phase60e_artifact_preserves_no_live_private_execution_scope() -> None:
    artifact = _post_audit()

    for field in FALSE_EXECUTION_FLAGS:
        assert artifact[field] is False
    for field in SAFETY_FLAGS:
        assert artifact[field] is True
    assert artifact["report_only"] is True
    assert artifact["no_new_execution"] is True


def test_phase60e_artifact_disables_scheduler_and_loop_readiness() -> None:
    artifact = _post_audit()

    assert artifact["scheduler_enabled"] is False
    assert artifact["auto_loop_enabled"] is False
    assert artifact["live_ready"] is False
    assert artifact["shadow_ready"] is False
