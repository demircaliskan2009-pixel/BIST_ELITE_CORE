from __future__ import annotations

from tests.crypto_core.venue.test_phase69b_paper_runtime_start_telemetry_artifact import (
    FALSE_SCOPE_FIELDS,
    SAFETY_FLAGS,
    _artifact,
)


def test_phase69e_no_live_scope_flags_remain_disabled() -> None:
    artifact = _artifact()

    assert artifact["runtime_mode"] == "PAPER_ONLY_PASSIVE_STARTED"
    for field in FALSE_SCOPE_FIELDS:
        assert artifact[field] is False


def test_phase69e_safety_flags_remain_true() -> None:
    artifact = _artifact()

    for field in SAFETY_FLAGS:
        assert artifact[field] is True


def test_phase69e_order_routing_and_loop_remain_disabled() -> None:
    artifact = _artifact()

    assert artifact["runtime_loop_started"] is False
    assert artifact["runtime_order_routing_enabled"] is False
    assert artifact["run_execution"] is False
