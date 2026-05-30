from __future__ import annotations

import copy

from crypto_core.venue.deribit_paper_promotion_post_audit import (
    audit_deribit_paper_promotion_execution_post_audit,
)
from tests.crypto_core.venue.test_phase60b_paper_promotion_post_audit_artifact import (
    _expected_post_audit,
    _phase58_execution,
    _phase59_audit,
    _post_audit,
)


def test_phase60g_runtime_output_is_deterministic() -> None:
    first = audit_deribit_paper_promotion_execution_post_audit(
        copy.deepcopy(_phase59_audit()), copy.deepcopy(_phase58_execution())
    ).artifact_payload
    second = audit_deribit_paper_promotion_execution_post_audit(
        copy.deepcopy(_phase59_audit()), copy.deepcopy(_phase58_execution())
    ).artifact_payload

    assert first == second == _expected_post_audit()


def test_phase60g_checked_in_artifact_is_deterministic_snapshot() -> None:
    assert _post_audit() == _expected_post_audit()
