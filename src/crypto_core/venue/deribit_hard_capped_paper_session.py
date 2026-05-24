from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, replace

from crypto_core.venue.deribit_paper_ledger import DeribitPaperLedgerState
from crypto_core.venue.deribit_paper_run_harness import (
    DeribitPaperRunHarnessInputs,
    DeribitPaperRunHarnessResult,
    DeribitPaperRunOperatorRequest,
    run_deribit_bounded_paper_run_harness,
)
from crypto_core.venue.deribit_paper_trade_gate import DeribitPaperTradeLedgerSummary
from crypto_core.venue.public_feed_dialects import connector_ready_dialects

DERIBIT_HARD_CAPPED_PAPER_SESSION_ID = "deribit_hard_capped_paper_session_v1"
DERIBIT_PAPER_SESSION_HARD_CAP = 3
PHASE40_RUN_ARTIFACT = "docs/crypto_core/DERIBIT_BOUNDED_OPERATOR_PAPER_RUN_ARTIFACT_40B.json"
PHASE41_TELEMETRY_REPORT = "docs/crypto_core/DERIBIT_BOUNDED_PAPER_RUN_TELEMETRY_REPORT_41B.json"

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
    "BOUNDED_OPERATOR_PAPER_RUN_HARNESS_40A.md",
    "PAPER_RUN_TELEMETRY_REPORTING_GATE_41A.md",
    "HARD_CAPPED_PAPER_SESSION_GATE_42A.md",
)


@dataclass(frozen=True)
class DeribitHardCappedPaperSessionRequest:
    operator_id: str
    session_id: str
    idempotency_key: str
    simulation_only: bool
    live_enabled: bool = False
    shadow_enabled: bool = False
    auto_loop_enabled: bool = False
    scheduler_enabled: bool = False
    max_session_trades: int = DERIBIT_PAPER_SESSION_HARD_CAP


@dataclass(frozen=True)
class DeribitHardCappedPaperSessionResult:
    accepted: bool
    session_id: str | None
    trades_requested: int
    trades_attempted: int
    trades_filled: int
    trades_rejected: int
    ledger_mutated: bool
    reason_code: str
    rejection_reasons: tuple[str, ...]
    run_results: tuple[DeribitPaperRunHarnessResult, ...]
    final_ledger_state: DeribitPaperLedgerState | None
    before_ledger_summary: dict[str, object] | None
    after_ledger_summary: dict[str, object] | None
    artifact_payload: dict[str, object]


def run_deribit_hard_capped_paper_session(
    request: object,
    trade_inputs: object,
    *,
    kill_switch_active: bool = False,
    now_ns: int | None = None,
) -> DeribitHardCappedPaperSessionResult:
    normalized_inputs = _normalized_trade_inputs(trade_inputs)
    request_reasons = list(_request_rejection_reasons(request))
    input_reasons = list(_trade_input_rejection_reasons(request, normalized_inputs, trade_inputs))
    kill_reasons = _kill_switch_rejection_reasons(kill_switch_active)
    reasons = tuple(dict.fromkeys((*request_reasons, *input_reasons, *kill_reasons)))
    initial_ledger = _initial_ledger(normalized_inputs)
    before_summary = _ledger_summary_to_dict(initial_ledger)
    if reasons:
        return _result(
            request=request,
            accepted=False,
            reason_code=reasons[0],
            rejection_reasons=reasons,
            run_results=(),
            final_ledger_state=initial_ledger,
            before_summary=before_summary,
            after_summary=before_summary,
            trades_requested=len(normalized_inputs),
        )

    assert isinstance(request, DeribitHardCappedPaperSessionRequest)
    assert normalized_inputs
    current_ledger = normalized_inputs[0].ledger_state
    run_results: list[DeribitPaperRunHarnessResult] = []
    trades_rejected = 0
    for trade_input in normalized_inputs:
        session_trade_input = replace(trade_input, ledger_state=current_ledger)
        run_request = DeribitPaperRunOperatorRequest(
            operator_id=request.operator_id,
            run_id=session_trade_input.fill_request.request_id,
            idempotency_key=session_trade_input.intent.idempotency_key,
            simulation_only=True,
        )
        run_result = run_deribit_bounded_paper_run_harness(
            run_request,
            session_trade_input,
            kill_switch_active=False,
            now_ns=now_ns,
        )
        run_results.append(run_result)
        if run_result.accepted is not True:
            trades_rejected = 1
            rejection_reasons = tuple(
                dict.fromkeys(
                    (
                        "deribit_hard_capped_paper_session:trade_rejected",
                        run_result.reason_code,
                        *run_result.rejection_reasons,
                    )
                )
            )
            return _result(
                request=request,
                accepted=False,
                reason_code=run_result.reason_code,
                rejection_reasons=rejection_reasons,
                run_results=tuple(run_results),
                final_ledger_state=initial_ledger,
                before_summary=before_summary,
                after_summary=before_summary,
                trades_requested=len(normalized_inputs),
                trades_rejected=trades_rejected,
            )
        if run_result.gate_result is not None and run_result.gate_result.ledger_state is not None:
            current_ledger = run_result.gate_result.ledger_state

    after_summary = _ledger_summary_to_dict(current_ledger)
    return _result(
        request=request,
        accepted=True,
        reason_code="deribit_hard_capped_paper_session:accepted",
        rejection_reasons=(),
        run_results=tuple(run_results),
        final_ledger_state=current_ledger,
        before_summary=before_summary,
        after_summary=after_summary,
        trades_requested=len(normalized_inputs),
    )


def _request_rejection_reasons(request: object) -> tuple[str, ...]:
    if not isinstance(request, DeribitHardCappedPaperSessionRequest):
        return ("deribit_hard_capped_paper_session:request_malformed",)

    reasons: list[str] = []
    if not _non_empty(request.operator_id):
        reasons.append("deribit_hard_capped_paper_session:operator_id_missing")
    if not _non_empty(request.session_id):
        reasons.append("deribit_hard_capped_paper_session:session_id_missing")
    if not _non_empty(request.idempotency_key):
        reasons.append("deribit_hard_capped_paper_session:idempotency_key_missing")
    if request.simulation_only is not True:
        reasons.append("deribit_hard_capped_paper_session:not_simulation_only")
    if request.live_enabled is not False:
        reasons.append("deribit_hard_capped_paper_session:live_enabled")
    if request.shadow_enabled is not False:
        reasons.append("deribit_hard_capped_paper_session:shadow_enabled")
    if request.auto_loop_enabled is not False:
        reasons.append("deribit_hard_capped_paper_session:auto_loop_enabled")
    if request.scheduler_enabled is not False:
        reasons.append("deribit_hard_capped_paper_session:scheduler_enabled")
    if (
        not isinstance(request.max_session_trades, int)
        or isinstance(request.max_session_trades, bool)
        or request.max_session_trades <= 0
    ):
        reasons.append("deribit_hard_capped_paper_session:max_session_trades_invalid")
    elif request.max_session_trades > DERIBIT_PAPER_SESSION_HARD_CAP:
        reasons.append("deribit_hard_capped_paper_session:max_session_trades_exceeds_hard_cap")
    if (
        _contains_scope_marker(request.operator_id)
        or _contains_scope_marker(request.session_id)
        or _contains_scope_marker(request.idempotency_key)
    ):
        reasons.append("deribit_hard_capped_paper_session:operator_request_scope_invalid")
    return tuple(dict.fromkeys(reasons))


def _trade_input_rejection_reasons(
    request: object,
    normalized_inputs: tuple[DeribitPaperRunHarnessInputs, ...],
    raw_trade_inputs: object,
) -> tuple[str, ...]:
    if not isinstance(raw_trade_inputs, Sequence) or isinstance(raw_trade_inputs, str | bytes):
        return ("deribit_hard_capped_paper_session:trade_inputs_missing",)
    if not normalized_inputs:
        return ("deribit_hard_capped_paper_session:trade_inputs_missing",)

    reasons: list[str] = []
    if len(normalized_inputs) > DERIBIT_PAPER_SESSION_HARD_CAP:
        reasons.append("deribit_hard_capped_paper_session:trade_count_exceeds_hard_cap")
    if isinstance(request, DeribitHardCappedPaperSessionRequest):
        if len(normalized_inputs) > request.max_session_trades:
            reasons.append("deribit_hard_capped_paper_session:trade_count_exceeds_session_bound")
    if any(not isinstance(trade_input, DeribitPaperRunHarnessInputs) for trade_input in raw_trade_inputs):
        reasons.append("deribit_hard_capped_paper_session:trade_input_malformed")
    request_ids = tuple(trade_input.fill_request.request_id for trade_input in normalized_inputs)
    idempotency_keys = tuple(trade_input.intent.idempotency_key for trade_input in normalized_inputs)
    if len(set(request_ids)) != len(request_ids):
        reasons.append("deribit_hard_capped_paper_session:duplicate_trade_request_id")
    if len(set(idempotency_keys)) != len(idempotency_keys):
        reasons.append("deribit_hard_capped_paper_session:duplicate_trade_idempotency_key")
    initial_ledger = _initial_ledger(normalized_inputs)
    if isinstance(request, DeribitHardCappedPaperSessionRequest) and initial_ledger is not None:
        if request.session_id in initial_ledger.applied_request_ids:
            reasons.append("deribit_hard_capped_paper_session:duplicate_session_id")
        if request.idempotency_key in initial_ledger.applied_idempotency_keys:
            reasons.append("deribit_hard_capped_paper_session:duplicate_session_idempotency_key")
    return tuple(dict.fromkeys(reasons))


def _kill_switch_rejection_reasons(kill_switch_active: object) -> tuple[str, ...]:
    if not isinstance(kill_switch_active, bool):
        return ("deribit_hard_capped_paper_session:kill_switch_flag_invalid",)
    if kill_switch_active is True:
        return ("deribit_hard_capped_paper_session:kill_switch_active",)
    return ()


def _normalized_trade_inputs(trade_inputs: object) -> tuple[DeribitPaperRunHarnessInputs, ...]:
    if not isinstance(trade_inputs, Sequence) or isinstance(trade_inputs, str | bytes):
        return ()
    return tuple(item for item in trade_inputs if isinstance(item, DeribitPaperRunHarnessInputs))


def _initial_ledger(trade_inputs: tuple[DeribitPaperRunHarnessInputs, ...]) -> DeribitPaperLedgerState | None:
    return trade_inputs[0].ledger_state if trade_inputs else None


def _result(
    *,
    request: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    run_results: tuple[DeribitPaperRunHarnessResult, ...],
    final_ledger_state: DeribitPaperLedgerState | None,
    before_summary: dict[str, object] | None,
    after_summary: dict[str, object] | None,
    trades_requested: int,
    trades_rejected: int = 0,
) -> DeribitHardCappedPaperSessionResult:
    session_id = request.session_id if isinstance(request, DeribitHardCappedPaperSessionRequest) else None
    trades_attempted = sum(result.trade_count_attempted for result in run_results)
    trades_filled = sum(result.fill_count for result in run_results)
    ledger_mutation_count = sum(result.ledger_mutation_count for result in run_results)
    ledger_mutated = accepted is True and ledger_mutation_count > 0
    artifact_payload = _artifact_payload(
        request=request,
        accepted=accepted,
        reason_code=reason_code,
        rejection_reasons=rejection_reasons,
        run_results=run_results,
        before_summary=before_summary,
        after_summary=after_summary,
        trades_requested=trades_requested,
        trades_attempted=trades_attempted,
        trades_filled=trades_filled,
        trades_rejected=trades_rejected,
        ledger_mutated=ledger_mutated,
    )
    return DeribitHardCappedPaperSessionResult(
        accepted=accepted,
        session_id=session_id,
        trades_requested=trades_requested,
        trades_attempted=trades_attempted,
        trades_filled=trades_filled,
        trades_rejected=trades_rejected,
        ledger_mutated=ledger_mutated,
        reason_code=reason_code,
        rejection_reasons=tuple(dict.fromkeys(rejection_reasons)),
        run_results=run_results,
        final_ledger_state=final_ledger_state if accepted else None,
        before_ledger_summary=before_summary,
        after_ledger_summary=after_summary,
        artifact_payload=artifact_payload,
    )


def _artifact_payload(
    *,
    request: object,
    accepted: bool,
    reason_code: str,
    rejection_reasons: tuple[str, ...],
    run_results: tuple[DeribitPaperRunHarnessResult, ...],
    before_summary: dict[str, object] | None,
    after_summary: dict[str, object] | None,
    trades_requested: int,
    trades_attempted: int,
    trades_filled: int,
    trades_rejected: int,
    ledger_mutated: bool,
) -> dict[str, object]:
    request_is_valid = isinstance(request, DeribitHardCappedPaperSessionRequest)
    return {
        "schema_version": "deribit_hard_capped_paper_session_artifact.v1",
        "phase": "42",
        "source": DERIBIT_HARD_CAPPED_PAPER_SESSION_ID,
        "source_phase40_artifact": PHASE40_RUN_ARTIFACT,
        "source_phase41_telemetry_report": PHASE41_TELEMETRY_REPORT,
        "accepted": accepted,
        "session_id": request.session_id if request_is_valid else None,
        "operator_id": request.operator_id if request_is_valid else None,
        "idempotency_key_sha256": _sha256(request.idempotency_key) if request_is_valid else None,
        "simulation_only": request.simulation_only if request_is_valid else None,
        "live_enabled": request.live_enabled if request_is_valid else None,
        "shadow_enabled": request.shadow_enabled if request_is_valid else None,
        "auto_loop_enabled": request.auto_loop_enabled if request_is_valid else None,
        "scheduler_enabled": request.scheduler_enabled if request_is_valid else None,
        "hard_cap": DERIBIT_PAPER_SESSION_HARD_CAP,
        "max_session_trades": request.max_session_trades if request_is_valid else None,
        "trades_requested": trades_requested,
        "trades_attempted": trades_attempted,
        "trades_filled": trades_filled,
        "trades_rejected": trades_rejected,
        "ledger_mutated": ledger_mutated,
        "duplicate_mutation_blocked": True,
        "reason_code": reason_code,
        "rejection_reasons": list(dict.fromkeys(rejection_reasons)),
        "trade_results": [_run_result_summary(result) for result in run_results],
        "before_ledger_summary": before_summary,
        "after_ledger_summary": after_summary,
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
        "connector_ready_dialects_count": len(connector_ready_dialects()),
        "policy_refs": list(_POLICY_REFS),
        "session_verdict": "PASS" if accepted else "FAIL_CLOSED",
        "next_blocker": "PAPER_SESSION_PROMOTION_CRITERIA_NOT_READY",
    }


def _run_result_summary(result: DeribitPaperRunHarnessResult) -> dict[str, object]:
    gate = result.gate_result
    return {
        "run_id": result.run_id,
        "accepted": result.accepted,
        "trade_count_attempted": result.trade_count_attempted,
        "trade_count_accepted": result.trade_count_accepted,
        "fill_count": result.fill_count,
        "ledger_mutation_count": result.ledger_mutation_count,
        "reason_code": result.reason_code,
        "rejection_reasons": list(result.rejection_reasons),
        "fill_id": None if gate is None else gate.fill_id,
    }


def _ledger_summary_to_dict(summary: object) -> dict[str, object] | None:
    if isinstance(summary, DeribitPaperLedgerState):
        return {
            "ledger_id": summary.ledger_id,
            "symbol": summary.symbol,
            "canonical_symbol": summary.canonical_symbol,
            "cash_balance": summary.cash_balance,
            "position_qty": summary.position_qty,
            "average_entry_price": summary.average_entry_price,
            "realized_pnl": summary.realized_pnl,
            "applied_fill_count": len(summary.applied_fill_ids),
            "applied_request_count": len(summary.applied_request_ids),
            "applied_idempotency_count": len(summary.applied_idempotency_keys),
            "audit_entry_count": len(summary.audit_entries),
        }
    if isinstance(summary, DeribitPaperTradeLedgerSummary):
        return {
            "ledger_id": summary.ledger_id,
            "symbol": summary.symbol,
            "canonical_symbol": summary.canonical_symbol,
            "cash_balance": summary.cash_balance,
            "position_qty": summary.position_qty,
            "average_entry_price": summary.average_entry_price,
            "realized_pnl": summary.realized_pnl,
            "applied_fill_count": summary.applied_fill_count,
            "applied_request_count": summary.applied_request_count,
            "applied_idempotency_count": summary.applied_idempotency_count,
            "audit_entry_count": summary.audit_entry_count,
        }
    return None


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _contains_scope_marker(value: object) -> bool:
    return isinstance(value, str) and any(marker in value.lower() for marker in _SCOPE_MARKERS)


def _non_empty(value: object) -> bool:
    return isinstance(value, str) and bool(value)


__all__ = [
    "DERIBIT_HARD_CAPPED_PAPER_SESSION_ID",
    "DERIBIT_PAPER_SESSION_HARD_CAP",
    "DeribitHardCappedPaperSessionRequest",
    "DeribitHardCappedPaperSessionResult",
    "run_deribit_hard_capped_paper_session",
]
