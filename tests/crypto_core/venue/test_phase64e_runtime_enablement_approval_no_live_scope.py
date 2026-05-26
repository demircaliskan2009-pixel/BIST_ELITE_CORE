from __future__ import annotations

import json

from tests.crypto_core.venue.test_phase64b_runtime_enablement_approval_artifact import (
    APPROVAL_SCOPE_TRUE_FLAGS,
    FALSE_RUNTIME_FIELDS,
    SAFETY_FLAGS,
    _approval,
)


def test_phase64e_approval_contains_no_live_or_execution_scope() -> None:
    approval = _approval()

    assert approval["runtime_enablement_approved"] is True
    for field in FALSE_RUNTIME_FIELDS:
        assert approval[field] is False
    for field in SAFETY_FLAGS:
        assert approval[field] is True
    for field in APPROVAL_SCOPE_TRUE_FLAGS:
        assert approval["approval_scope"][field] is True


def test_phase64e_serialized_output_has_no_live_private_or_order_objects() -> None:
    serialized = json.dumps(_approval(), sort_keys=True)

    for forbidden in (
        "private_api_call",
        "credential_value",
        "api_secret",
        "exchange_order_id",
        "execution_adapter_instance",
        "strategy_signal_payload",
        "scheduler_job",
        "live_order",
        "shadow_order",
    ):
        assert forbidden not in serialized
