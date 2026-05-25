from __future__ import annotations

from dataclasses import replace

from crypto_core.venue.deribit_approved_paper_performance_campaign import (
    run_deribit_approved_paper_performance_campaign,
)
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact as _phase50_artifact,
)
from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import _approval as _phase52_approval
from tests.crypto_core.venue.test_phase53c_approved_campaign_execution_contract import (
    _phase48_execution,
    _phase53_request,
    _phase53_sessions,
    _run_phase53,
)


def test_phase53e_duplicate_campaign_request_id_cannot_double_mutate_ledger() -> None:
    initial = _run_phase53()
    rerun = run_deribit_approved_paper_performance_campaign(
        _phase53_request(),
        _phase52_approval(),
        _phase50_artifact(),
        _phase48_execution(),
        _phase53_sessions(),
        initial.final_ledger_state,
    )

    assert rerun.accepted is False
    assert rerun.ledger_mutated is False
    assert rerun.before_ledger_summary == rerun.after_ledger_summary
    assert "deribit_bounded_paper_campaign:duplicate_campaign_id" in rerun.rejection_reasons


def test_phase53e_duplicate_idempotency_key_cannot_double_mutate_ledger() -> None:
    initial = _run_phase53()
    rerun = run_deribit_approved_paper_performance_campaign(
        replace(
            _phase53_request(),
            campaign_request_id="phase53-approved-paper-performance-campaign-retry",
            idempotency_key="idem-phase53-approved-paper-performance-campaign",
        ),
        _phase52_approval(),
        _phase50_artifact(),
        _phase48_execution(),
        _phase53_sessions(),
        initial.final_ledger_state,
    )

    assert rerun.accepted is False
    assert rerun.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:duplicate_campaign_idempotency_key" in rerun.rejection_reasons
