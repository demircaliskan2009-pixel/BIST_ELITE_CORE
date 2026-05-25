from __future__ import annotations

from copy import deepcopy
from dataclasses import replace

from crypto_core.venue.deribit_approved_paper_performance_campaign import (
    run_deribit_approved_paper_performance_campaign,
)
from tests.crypto_core.venue.test_phase50b_campaign_performance_evaluation_artifact import (
    _artifact as _phase50_artifact,
)
from tests.crypto_core.venue.test_phase52b_operator_approval_artifact import _approval as _phase52_approval
from tests.crypto_core.venue.test_phase53c_approved_campaign_execution_contract import (
    _ledger,
    _phase48_execution,
    _phase53_request,
    _phase53_sessions,
)

_UNSET = object()


def _run_with(
    *,
    request=_UNSET,
    approval=_UNSET,
    evaluation=_UNSET,
    phase48=_UNSET,
    sessions=_UNSET,
):
    return run_deribit_approved_paper_performance_campaign(
        _phase53_request() if request is _UNSET else request,
        _phase52_approval() if approval is _UNSET else approval,
        _phase50_artifact() if evaluation is _UNSET else evaluation,
        _phase48_execution() if phase48 is _UNSET else phase48,
        _phase53_sessions() if sessions is _UNSET else sessions,
        _ledger(),
    )


def test_phase53d_missing_or_invalid_phase52_approval_fails_closed() -> None:
    missing = _run_with(approval=None)
    wrong_status = _run_with(approval=deepcopy({**_phase52_approval(), "approval_status": "NOT_APPROVED"}))
    wrong_operator = _run_with(approval=deepcopy({**_phase52_approval(), "operator_id": "other_operator"}))
    wrong_decision = _run_with(approval=deepcopy({**_phase52_approval(), "approval_decision": "APPROVE_LIVE_TRADING"}))

    assert missing.accepted is False
    assert "deribit_approved_paper_performance_campaign:phase52_approval_missing" in missing.rejection_reasons
    assert (
        "deribit_approved_paper_performance_campaign:phase52_approval_metadata_invalid"
        in wrong_status.rejection_reasons
    )
    assert (
        "deribit_approved_paper_performance_campaign:phase52_approval_metadata_invalid"
        in wrong_operator.rejection_reasons
    )
    assert (
        "deribit_approved_paper_performance_campaign:phase52_approval_metadata_invalid"
        in wrong_decision.rejection_reasons
    )


def test_phase53d_request_scope_drift_fails_closed() -> None:
    no_campaign_id = _run_with(request=replace(_phase53_request(), campaign_request_id=""))
    no_idempotency = _run_with(request=replace(_phase53_request(), idempotency_key=""))
    not_sim = _run_with(request=replace(_phase53_request(), simulation_only=False))
    live = _run_with(request=replace(_phase53_request(), live_enabled=True))
    shadow = _run_with(request=replace(_phase53_request(), shadow_enabled=True))
    loop = _run_with(request=replace(_phase53_request(), auto_loop_enabled=True))
    scheduler = _run_with(request=replace(_phase53_request(), scheduler_enabled=True))

    assert "deribit_approved_paper_performance_campaign:campaign_request_id_missing" in no_campaign_id.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:idempotency_key_missing" in no_idempotency.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:not_simulation_only" in not_sim.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:live_enabled" in live.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:shadow_enabled" in shadow.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:auto_loop_enabled" in loop.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:scheduler_enabled" in scheduler.rejection_reasons


def test_phase53d_unsafe_safety_flags_or_source_drift_fail_closed() -> None:
    bad_safety = deepcopy(_phase52_approval())
    bad_safety["no_order_routing"] = False
    bad_connector = deepcopy(_phase52_approval())
    bad_connector["connector_ready_dialects_count"] = 0
    bad_phase50 = deepcopy(_phase50_artifact())
    bad_phase50["performance_evaluation_verdict"] = "FAIL"
    bad_phase48 = deepcopy(_phase48_execution())
    bad_phase48["campaign_execution_verdict"] = "FAIL"

    safety_result = _run_with(approval=bad_safety)
    connector_result = _run_with(approval=bad_connector)
    phase50_result = _run_with(evaluation=bad_phase50)
    phase48_result = _run_with(phase48=bad_phase48)

    assert (
        "deribit_approved_paper_performance_campaign:phase52_approval_safety_flags_invalid"
        in safety_result.rejection_reasons
    )
    assert (
        "deribit_approved_paper_performance_campaign:phase52_connector_ready_dialects_invalid"
        in connector_result.rejection_reasons
    )
    assert "deribit_approved_paper_performance_campaign:phase50_metadata_invalid" in phase50_result.rejection_reasons
    assert "deribit_approved_paper_performance_campaign:phase48_metadata_invalid" in phase48_result.rejection_reasons


def test_phase53d_session_rejection_fails_closed() -> None:
    sessions = list(_phase53_sessions())
    sessions[0] = replace(sessions[0], trade_inputs=sessions[0].trade_inputs + (sessions[0].trade_inputs[0],))
    result = _run_with(sessions=tuple(sessions))

    assert result.accepted is False
    assert result.ledger_mutated is False
    assert "deribit_bounded_paper_campaign:duplicate_trade_request_id" in result.rejection_reasons
