from __future__ import annotations

import hashlib
from dataclasses import dataclass

from crypto_core.venue.deribit_paper_feed import DeribitPaperFeedFrame
from crypto_core.venue.deribit_paper_fill_model import DeribitPaperFillRequest
from crypto_core.venue.deribit_paper_ledger import DeribitPaperLedgerState
from crypto_core.venue.deribit_paper_order_intent import DeribitPaperOrderIntent, DeribitPaperOrderIntentDecision
from crypto_core.venue.deribit_paper_trade_gate import (
    DeribitPaperTradeGateResult,
    DeribitPaperTradeOperatorTrigger,
    deribit_paper_trade_gate_result_to_dict,
    run_deribit_paper_trade_gate,
)
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_PAPER_RUN_HARNESS_ID = "deribit_paper_run_harness_v1"
PHASE38_PROOF_ARTIFACT = "docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_SMOKE_PROOF_38B.json"
PHASE39_AUDIT_REPORT = "docs/crypto_core/DERIBIT_FIRST_PAPER_TRADE_AUDIT_REPORT_39B.json"

_SCOPE_MARKERS = frozenset(
    {
        "account",
        "auth",
        "balance",
        "credential",
        "exchange_order",
        "execution",
        "live",
        "private",
        "route",
        "scheduler",
        "shadow",
        "signal",
        "strategy",
        "token",
        "withdraw",
    }
)
_POLICY_REFS = (
    "FIRST_PAPER_TRADE_GATE_37A.md",
    "FIRST_PAPER_TRADE_SMOKE_PROOF_38A.md",
    "PAPER_TRADE_AUDIT_REPORTING_GATE_39A.md",
    "BOUNDED_OPERATOR_PAPER_RUN_HARNESS_40A.md",
)


@dataclass(frozen=True)
class DeribitPaperRunOperatorRequest:
    operator_id: str
    run_id: str
    idempotency_key: str
    simulation_only: bool
    live_enabled: bool = False
    shadow_enabled: bool = False
    auto_loop_enabled: bool = False
    scheduler_enabled: bool = False
    max_trades: int = 1


@dataclass(frozen=True)
class DeribitPaperRunHarnessInputs:
    intent: DeribitPaperOrderIntent
    decision: DeribitPaperOrderIntentDecision
    fill_request: DeribitPaperFillRequest
    frame: DeribitPaperFeedFrame
    ledger_state: DeribitPaperLedgerState


@dataclass(frozen=True)
class DeribitPaperRunHarnessResult:
    accepted: bool
    run_id: str | None
    trade_count_attempted: int
    trade_count_accepted: int
    fill_count: int
    ledger_mutation_count: int
    reason_code: str
    rejection_reasons: tuple[str, ...]
    gate_result: DeribitPaperTradeGateResult | None
    artifact_payload: dict[str, object]


def run_deribit_bounded_paper_run_harness(
    request: object,
    inputs: object,
    *,
    kill_switch_active: bool = False,
    now_ns: int | None = None,
) -> DeribitPaperRunHarnessResult:
    request_reasons = list(_request_rejection_reasons(request))
    input_reasons = list(_input_rejection_reasons(inputs))
    reasons = tuple(dict.fromkeys((*request_reasons, *input_reasons)))
    if reasons:
        return _result(
            request=request,
            accepted=False,
            reason_code=reasons[0],
            rejection_reasons=reasons,
            gate_result=None,
        )

    assert isinstance(request, DeribitPaperRunOperatorRequest)
    assert isinstance(inputs, DeribitPaperRunHarnessInputs)
    trigger = DeribitPaperTradeOperatorTrigger(
        operator_id=request.operator_id,
        run_id=request.run_id,
        idempotency_key=request.idempotency_key,
        simulation_only=True,
        live_enabled=False,
        shadow_enabled=False,
        auto_loop_enabled=False,
    )
    gate_result = run_deribit_paper_trade_gate(
        trigger,
        inputs.intent,
        inputs.decision,
        inputs.fill_request,
        inputs.frame,
        inputs.ledger_state,
        kill_switch_active=kill_switch_active,
        now_ns=now_ns,
    )
    if gate_result.accepted is not True:
        rejection_reasons = tuple(
            dict.fromkeys(
                (
                    "deribit_paper_run_harness:gate_rejected",
                    gate_result.reason_code,
                    *gate_result.rejection_reasons,
                )
            )
        )
        return _result(
            request=request,
            accepted=False,
            reason_code=gate_result.reason_code,
            rejection_reasons=rejection_reasons,
            gate_result=gate_result,
        )
    return _result(
        request=request,
        accepted=True,
        reason_code="deribit_paper_run_harness:accepted",
        rejection_reasons=(),
        gate_result=gate_result,
    )


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    if not isinstance(request, DeribitPaperRunOperatorRequest):
        return ("deribit_paper_run_harness:request_malformed",)

    reasons: list[str] = []
    if not _non_empty(request.operator_id):
        reasons.append("deribit_paper_run_harness:operator_id_missing")
    if not _non_empty(request.run_id):
        reasons.append("deribit_paper_run_harness:run_id_missing")
    if not _non_empty(request.idempotency_key):
        reasons.append("deribit_paper_run_harness:idempotency_key_missing")
    if request.simulation_only is not True:
        reasons.append("deribit_paper_run_harness:not_simulation_only")
    if request.live_enabled is not False:
        reasons.append("deribit_paper_run_harness:live_enabled")
    if request.shadow_enabled is not False:
        reasons.append("deribit_paper_run_harness:shadow_enabled")
    if request.auto_loop_enabled is not False:
        reasons.append("deribit_paper_run_harness:auto_loop_enabled")
    if request.scheduler_enabled is not False:
        reasons.append("deribit_paper_run_harness:scheduler_enabled")
    if not isinstance(request.max_trades, int) or isinstance(request.max_trades, bool) or request.max_trades <= 0:
        reasons.append("deribit_paper_run_harness:max_trades_invalid")
    elif request.max_trades > 1:
        reasons.append("deribit_paper_run_harness:max_trades_exceeds_phase40_bound")
    if (
        _contains_scope_marker(request.operator_id)
        or _contains_scope_marker(request.run_id)
        or _contains_scope_marker(request.idempotency_key)
    ):
        reasons.append("deribit_paper_run_harness:operator_request_scope_invalid")
    return tuple(dict.fromkeys(reasons))


def _input_rejection_reasons(inputs: object) -> tuple[str, ...]:
    if not isinstance(inputs, DeribitPaperRunHarnessInputs):
        return ("deribit_paper_run_harness:inputs_missing",)

    reasons: list[str] = []
    if not isinstance(inputs.intent, DeribitPaperOrderIntent):
        reasons.append("deribit_paper_run_harness:intent_missing")
    if not isinstance(inputs.decision, DeribitPaperOrderIntentDecision):
        reasons.append("deribit_paper_run_harness:decision_missing")
    if not isinstance(inputs.fill_request, DeribitPaperFillRequest):
        reasons.append("deribit_paper_run_harness:fill_request_missing")
    if not isinstance(inputs.frame, DeribitPaperFeedFrame):
        reasons.append("deribit_paper_run_harness:frame_missing")
    if not isinstance(inputs.ledger_state, DeribitPaperLedgerState):
        reasons.append("deribit_paper_run_harness:ledger_state_missing")
    if reasons:
        return tuple(dict.fromkeys(reasons))

    if inputs.decision.fill_request != inputs.fill_request:
        reasons.append("deribit_paper_run_harness:fill_request_mismatch")
    if inputs.fill_request.request_id != inputs.intent.intent_id:
        reasons.append("deribit_paper_run_harness:request_id_intent_mismatch")
    if (
        inputs.ledger_state.symbol != inputs.intent.symbol
        or inputs.ledger_state.canonical_symbol != inputs.intent.canonical_symbol
    ):
        reasons.append("deribit_paper_run_harness:ledger_intent_instrument_mismatch")
    return tuple(dict.fromkeys(reasons))


def _result(
    *,
    request: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    gate_result: DeribitPaperTradeGateResult | None,
) -> DeribitPaperRunHarnessResult:
    run_id = request.run_id if isinstance(request, DeribitPaperRunOperatorRequest) else None
    trade_count_attempted = 1 if isinstance(gate_result, DeribitPaperTradeGateResult) else 0
    trade_count_accepted = 1 if isinstance(gate_result, DeribitPaperTradeGateResult) and gate_result.accepted else 0
    fill_count = 1 if isinstance(gate_result, DeribitPaperTradeGateResult) and gate_result.filled else 0
    ledger_mutation_count = (
        1 if isinstance(gate_result, DeribitPaperTradeGateResult) and gate_result.ledger_mutated else 0
    )
    artifact_payload = _artifact_payload(
        request=request,
        accepted=accepted,
        reason_code=reason_code,
        rejection_reasons=rejection_reasons,
        gate_result=gate_result,
        trade_count_attempted=trade_count_attempted,
        trade_count_accepted=trade_count_accepted,
        fill_count=fill_count,
        ledger_mutation_count=ledger_mutation_count,
    )
    return DeribitPaperRunHarnessResult(
        accepted=accepted,
        run_id=run_id,
        trade_count_attempted=trade_count_attempted,
        trade_count_accepted=trade_count_accepted,
        fill_count=fill_count,
        ledger_mutation_count=ledger_mutation_count,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        gate_result=gate_result,
        artifact_payload=artifact_payload,
    )


def _artifact_payload(
    *,
    request: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    gate_result: DeribitPaperTradeGateResult | None,
    trade_count_attempted: int,
    trade_count_accepted: int,
    fill_count: int,
    ledger_mutation_count: int,
) -> dict[str, object]:
    request_is_valid = isinstance(request, DeribitPaperRunOperatorRequest)
    gate_payload = None if gate_result is None else deribit_paper_trade_gate_result_to_dict(gate_result)
    return {
        "schema_version": "deribit_bounded_operator_paper_run_artifact.v1",
        "phase": "40",
        "source": DERIBIT_PAPER_RUN_HARNESS_ID,
        "source_phase38_proof_artifact": PHASE38_PROOF_ARTIFACT,
        "source_phase39_audit_report": PHASE39_AUDIT_REPORT,
        "accepted": accepted,
        "run_id": request.run_id if request_is_valid else None,
        "operator_id": request.operator_id if request_is_valid else None,
        "idempotency_key_sha256": _sha256(request.idempotency_key) if request_is_valid else None,
        "simulation_only": request.simulation_only if request_is_valid else None,
        "live_enabled": request.live_enabled if request_is_valid else None,
        "shadow_enabled": request.shadow_enabled if request_is_valid else None,
        "auto_loop_enabled": request.auto_loop_enabled if request_is_valid else None,
        "scheduler_enabled": request.scheduler_enabled if request_is_valid else None,
        "max_trades": request.max_trades if request_is_valid else None,
        "trade_count_attempted": trade_count_attempted,
        "trade_count_accepted": trade_count_accepted,
        "fill_count": fill_count,
        "ledger_mutation_count": ledger_mutation_count,
        "reason_code": reason_code,
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "gate_result": gate_payload,
        "before_ledger_summary": None if gate_payload is None else gate_payload["before_ledger_summary"],
        "after_ledger_summary": None if gate_payload is None else gate_payload["after_ledger_summary"],
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "policy_refs": list(_POLICY_REFS),
        "safety_invariants": {
            "no_private_api": True,
            "no_credentials": True,
            "no_exchange_orders": True,
            "no_execution_adapter": True,
            "no_order_routing": True,
            "no_strategy_signal": True,
            "no_scheduler": True,
            "no_automatic_paper_loop": True,
            "no_shadow": True,
            "no_live": True,
            "no_ci_live_network_dependency": True,
        },
    }


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contains_scope_marker(value: object) -> bool:
    return isinstance(value, str) and any(marker in value.lower() for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


__all__ = [
    "DERIBIT_PAPER_RUN_HARNESS_ID",
    "DeribitPaperRunHarnessInputs",
    "DeribitPaperRunHarnessResult",
    "DeribitPaperRunOperatorRequest",
    "run_deribit_bounded_paper_run_harness",
]
