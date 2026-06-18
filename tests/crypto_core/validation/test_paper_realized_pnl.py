"""Tests for the paper realized-PnL event — deterministic gross realized PnL, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_realized_pnl
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_simulation_result_digest,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    PaperPositionTransitionStatus,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
    paper_position_state_digest,
    paper_position_transition_result_digest,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlError,
    PaperRealizedPnlStatus,
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_digest,
    paper_realized_pnl_event_to_dict,
)

_HEX = "b" * 64

_BARE_FORBIDDEN_KEYS = (
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
    "order_id",
    "position_id",
    "unrealized_pnl",
    "total_pnl",
    "equity",
    "margin",
    "balance",
    "capital",
    "scheduler",
    "auto_loop",
    "connector",
    "fee_amount",
)

_SAFE_FALSE_FLAGS = (
    "fees_included",
    "unrealized_pnl_computed",
    "total_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "live_position_mutated",
    "real_money_enabled",
    "real_orders_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "live_api_called",
    "scheduler_enabled",
    "auto_loop_enabled",
    "connector_invoked",
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _long(*, signed: str = "10", abs_units: str = "10", avg: str = "100", market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_position_state(
        position_state_id="pos-1",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.LONG,
        signed_units=signed,
        abs_units=abs_units,
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-pos",
    )


def _short(*, signed: str = "-10", abs_units: str = "10", avg: str = "100", market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_position_state(
        position_state_id="pos-1",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.SHORT,
        signed_units=signed,
        abs_units=abs_units,
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-pos",
    )


def _flat(*, market_symbol: str = "BTC-PERPETUAL"):
    return build_flat_paper_position_state(
        position_state_id="pos-1", market_symbol=market_symbol, correlation_id="corr-pos"
    )


def _fill(
    side: str,
    filled_units: str,
    fill_price: str,
    *,
    status: PaperFillSimulationStatus = PaperFillSimulationStatus.FILLED,
    unfilled_units: str = "0",
    reason_codes: tuple[str, ...] = (),
    gross_notional: str = "1",
    market_symbol: str = "BTC-PERPETUAL",
) -> PaperFillSimulationResult:
    base = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=status,
        fill_simulation_id="fillsim-1",
        intent_digest=_HEX,
        market_snapshot_digest=_HEX,
        fill_policy_digest=_HEX,
        market_symbol=market_symbol,
        side=side,
        intent_type="MARKET",
        fill_price=fill_price,
        filled_units=filled_units,
        unfilled_units=unfilled_units,
        gross_notional=gross_notional,
        fee_amount="0",
        reason_codes=reason_codes,
        correlation_id="corr-fill",
        metadata=(),
        result_digest="",
    )
    return replace(base, result_digest=paper_fill_simulation_result_digest(base))


def _triple(prior, fill, suffix: str = "1"):
    return apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=f"trans-{suffix}",
        new_position_state_id=f"newpos-{suffix}",
        correlation_id="corr-apply",
    )


def _event(prior, fill, transition, **overrides: object):
    base: dict[str, object] = {"realized_pnl_event_id": "evt-1", "correlation_id": "corr-evt"}
    base.update(overrides)
    return compute_paper_realized_pnl_event(prior, fill, transition, **base)  # type: ignore[arg-type]


def _run(prior, fill, **overrides: object):
    transition, _ = _triple(prior, fill)
    return _event(prior, fill, transition, **overrides)


def _realized_oracle(prior_side: str, closed: str, avg0: str, fp: str) -> str:
    with localcontext() as ctx:
        ctx.prec = 200
        c, a, p = Decimal(closed), Decimal(avg0), Decimal(fp)
        result = c * (p - a) if prior_side == "LONG" else c * (a - p)
    rendered = format(result, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


# --------------------------------------------------------------------------------------------------
# No-realized cases
# --------------------------------------------------------------------------------------------------


def test_flat_buy_no_realized() -> None:
    event = _run(_flat(), _fill("BUY", "10", "100"))
    assert event.status is PaperRealizedPnlStatus.NO_REALIZED_PNL
    assert event.closed_units == "0"
    assert event.realized_pnl == "0"
    assert event.residual_open_units == "10"
    assert event.reason_codes == ("no_closed_units",)
    assert event.realized_pnl_computed is False


def test_flat_sell_no_realized() -> None:
    event = _run(_flat(), _fill("SELL", "10", "100"))
    assert event.status is PaperRealizedPnlStatus.NO_REALIZED_PNL
    assert event.realized_pnl == "0"
    assert event.residual_open_units == "10"


def test_long_buy_add_no_realized() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("BUY", "5", "120"))
    assert event.status is PaperRealizedPnlStatus.NO_REALIZED_PNL
    assert event.closed_units == "0"
    assert event.residual_open_units == "15"


def test_short_sell_add_no_realized() -> None:
    event = _run(_short(signed="-10", avg="100"), _fill("SELL", "5", "80"))
    assert event.status is PaperRealizedPnlStatus.NO_REALIZED_PNL
    assert event.closed_units == "0"
    assert event.residual_open_units == "15"


# --------------------------------------------------------------------------------------------------
# Realized cases
# --------------------------------------------------------------------------------------------------


def test_long_reduced_profitable() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("SELL", "4", "150"))
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "4"
    assert event.realized_pnl == "200"  # 4 * (150 - 100)
    assert event.residual_open_units == "6"
    assert event.realized_pnl_computed is True
    assert event.reason_codes == ()


def test_long_reduced_losing() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("SELL", "4", "80"))
    assert event.realized_pnl == "-80"  # 4 * (80 - 100)


def test_short_reduced_profitable() -> None:
    event = _run(_short(signed="-10", avg="100"), _fill("BUY", "4", "80"))
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.realized_pnl == "80"  # 4 * (100 - 80)
    assert event.residual_open_units == "6"


def test_short_reduced_losing() -> None:
    event = _run(_short(signed="-10", avg="100"), _fill("BUY", "4", "150"))
    assert event.realized_pnl == "-200"  # 4 * (100 - 150)


def test_long_exact_close() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("SELL", "10", "150"))
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "10"
    assert event.realized_pnl == "500"  # 10 * (150 - 100)
    assert event.residual_open_units == "0"


def test_short_exact_close() -> None:
    event = _run(_short(signed="-10", avg="100"), _fill("BUY", "10", "80"))
    assert event.closed_units == "10"
    assert event.realized_pnl == "200"  # 10 * (100 - 80)
    assert event.residual_open_units == "0"


def test_long_cross_through_realizes_only_prior_units() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("SELL", "15", "150"))
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "10"  # only the prior 10 long units realized
    assert event.realized_pnl == "500"  # 10 * (150 - 100)
    assert event.residual_open_units == "5"  # opened short, not realized


def test_short_cross_through_realizes_only_prior_units() -> None:
    event = _run(_short(signed="-10", avg="100"), _fill("BUY", "15", "80"))
    assert event.closed_units == "10"
    assert event.realized_pnl == "200"  # 10 * (100 - 80)
    assert event.residual_open_units == "5"


def test_partial_fill_uses_filled_units() -> None:
    fill = _fill(
        "SELL",
        "4",
        "150",
        status=PaperFillSimulationStatus.PARTIALLY_FILLED,
        unfilled_units="6",
        reason_codes=("partial_fill",),
    )
    event = _run(_long(signed="10", avg="100"), fill)
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "4"
    assert event.realized_pnl == "200"


def test_zero_realized_is_canonical_zero() -> None:
    event = _run(_long(signed="10", avg="100"), _fill("SELL", "4", "100"))  # fp == avg
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "4"
    assert event.realized_pnl == "0"  # canonical, no -0


def test_high_precision_realized_exact() -> None:
    avg = "100.0000000000000000000000000000000001"
    event = _run(_long(signed="10", avg=avg), _fill("SELL", "4", "150"))
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.realized_pnl == _realized_oracle("LONG", "4", avg, "150")
    # the high-precision tail survives (would be lost under default 28-digit context)
    assert event.realized_pnl == "199.9999999999999999999999999999999996"


# --------------------------------------------------------------------------------------------------
# Fail-closed: digest boundary
# --------------------------------------------------------------------------------------------------


def test_prior_state_digest_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(prior, position_state_digest="d" * 64)
    with pytest.raises(PaperRealizedPnlError, match="prior_state_digest_mismatch"):
        _event(forged, fill, transition)


def test_fill_result_digest_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(fill, result_digest="d" * 64)
    with pytest.raises(PaperRealizedPnlError, match="fill_result_digest_mismatch"):
        _event(prior, forged, transition)


def test_transition_digest_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(transition, transition_digest="d" * 64)
    with pytest.raises(PaperRealizedPnlError, match="transition_digest_mismatch"):
        _event(prior, fill, forged)


def test_transition_prior_digest_binding_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(transition, prior_position_state_digest="a" * 64)
    forged = replace(forged, transition_digest=paper_position_transition_result_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="transition_prior_digest_mismatch"):
        _event(prior, fill, forged)


def test_transition_fill_digest_binding_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(transition, fill_simulation_result_digest="a" * 64)
    forged = replace(forged, transition_digest=paper_position_transition_result_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="transition_fill_digest_mismatch"):
        _event(prior, fill, forged)


def test_symbol_mismatch_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged_prior = replace(prior, market_symbol="ETH-PERPETUAL")
    forged_prior = replace(forged_prior, position_state_digest=paper_position_state_digest(forged_prior))
    with pytest.raises(PaperRealizedPnlError, match="symbol_mismatch"):
        _event(forged_prior, fill, transition)


def test_rejected_fill_is_fail_closed() -> None:
    prior = _flat()
    rejected = _fill(
        "BUY",
        "0",
        "150",
        status=PaperFillSimulationStatus.REJECTED,
        gross_notional="0",
        reason_codes=("insufficient_liquidity",),
    )
    transition, _ = _triple(prior, rejected)
    assert transition.status is PaperPositionTransitionStatus.REJECTED
    with pytest.raises(PaperRealizedPnlError, match="fill_not_applicable"):
        _event(prior, rejected, transition)


def test_transition_not_applied_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(
        transition,
        status=PaperPositionTransitionStatus.REJECTED,
        new_position_state_digest=None,
        paper_position_state_updated=False,
        reason_codes=("fill_not_applied",),
    )
    forged = replace(forged, transition_digest=paper_position_transition_result_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="transition_not_applied"):
        _event(prior, fill, forged)


# --------------------------------------------------------------------------------------------------
# Fail-closed: forged self-consistent artifacts
# --------------------------------------------------------------------------------------------------


def test_forged_self_consistent_prior_state_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(prior, side=PaperPositionStateSide.SHORT)  # signed still > 0
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="prior_state_inconsistent"):
        _event(forged, fill, transition)


def test_forged_self_consistent_fill_result_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(fill, real_orders_enabled=True)
    forged = replace(forged, result_digest=paper_fill_simulation_result_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="fill_result_unsafe_flags"):
        _event(prior, forged, transition)


def test_forged_self_consistent_transition_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(transition, capital_mutated=True)
    forged = replace(forged, transition_digest=paper_position_transition_result_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="transition_unsafe_flags"):
        _event(prior, fill, forged)


def test_forged_unsafe_prior_state_rejected() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    forged = replace(prior, capital_mutated=True)
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperRealizedPnlError, match="prior_state_unsafe_flags"):
        _event(forged, fill, transition)


# --------------------------------------------------------------------------------------------------
# Fail-closed: scope / metadata
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("field,value", [("realized_pnl_event_id", "scheduler-1"), ("correlation_id", "live_feed")])
def test_scope_violation_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperRealizedPnlError, match="scope_violation"):
        _run(_long(), _fill("SELL", "4", "150"), **{field: value})


def test_metadata_malformed_rejected() -> None:
    with pytest.raises(PaperRealizedPnlError, match="metadata_malformed"):
        _run(_long(), _fill("SELL", "4", "150"), metadata={"k": 5})  # type: ignore[dict-item]


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_event_digest_deterministic() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    e1 = _event(prior, fill, transition)
    e2 = _event(prior, fill, transition)
    assert e1 == e2
    assert e1.realized_pnl_event_digest == e2.realized_pnl_event_digest
    assert paper_realized_pnl_event_digest(e1) == e1.realized_pnl_event_digest


def test_event_immutable() -> None:
    event = _run(_long(), _fill("SELL", "4", "150"))
    with pytest.raises(FrozenInstanceError):
        event.realized_pnl = "1"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        event.status = PaperRealizedPnlStatus.REJECTED  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    prior, fill = _long(), _fill("SELL", "4", "150")
    transition, _ = _triple(prior, fill)
    prior_before = paper_position_state_digest(prior)
    fill_before = paper_fill_simulation_result_digest(fill)
    transition_before = paper_position_transition_result_digest(transition)
    _event(prior, fill, transition)
    assert paper_position_state_digest(prior) == prior_before
    assert paper_fill_simulation_result_digest(fill) == fill_before
    assert paper_position_transition_result_digest(transition) == transition_before


def test_event_dict_safe_flags_and_no_forbidden_fields() -> None:
    payload = paper_realized_pnl_event_to_dict(_run(_long(), _fill("SELL", "4", "150")))
    assert payload["paper_only"] is True
    assert payload["realized_pnl_computed"] is True
    assert payload["fee_amount_applied"] is None
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_realized_pnl.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None and node.level == 0:
            imported.append(node.module)
    forbidden_prefixes = (
        "crypto_core.venue",
        "crypto_core.execution",
        "crypto_core.runtime",
        "crypto_core.service",
        "crypto_core.session",
        "crypto_core.data",
        "crypto_core.portfolio",
        "crypto_core.orchestrator",
        "crypto_core.temporal",
        "crypto_core.audit",
    )
    for module in imported:
        for prefix in forbidden_prefixes:
            assert module != prefix and not module.startswith(prefix + "."), f"forbidden import: {module}"
        if module.startswith("crypto_core"):
            assert module.startswith("crypto_core.validation"), f"unexpected crypto_core import: {module}"


# --------------------------------------------------------------------------------------------------
# End-to-end: real open then close realizes PnL
# --------------------------------------------------------------------------------------------------


def _make_draft() -> PaperAllocatorIntentDraft:
    fields: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": "a" * 64,
        "promotion_readiness_journal_entry_digest": "a" * 64,
        "promotion_readiness_payload_digest": "a" * 64,
        "promotion_candidate_journal_entry_digest": "a" * 64,
        "decision_journal_entry_digest": "a" * 64,
        "decision_journal_payload_digest": "a" * 64,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _intent(side: PaperOrderSide, *, suffix: str):
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="100000000",
        max_units="100000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(), cap_policy, requested_notional="100000", requested_units="10", correlation_id="corr-capacity"
    )
    request = build_paper_order_intent_request(
        request_id=f"req-{suffix}",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol="BTC-PERPETUAL",
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id=f"intent-{suffix}", correlation_id="corr-intent")


def test_end_to_end_open_then_close_realizes_pnl() -> None:
    policy = build_paper_fill_policy(policy_id="fill-pol", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False)

    # Open: BUY 10 @ 50 from flat.
    snap_open = build_paper_fill_market_snapshot(
        snapshot_id="snap-open", market_symbol="BTC-PERPETUAL", reference_price="50"
    )
    fill_open = simulate_paper_fill(
        _intent(PaperOrderSide.BUY, suffix="open"),
        snap_open,
        policy,
        fill_simulation_id="fill-open",
        correlation_id="corr-fill",
    )
    _, long_state = apply_paper_fill_to_position(
        _flat(), fill_open, transition_id="t-open", new_position_state_id="pos-long", correlation_id="corr-apply"
    )
    assert long_state is not None
    assert long_state.side is PaperPositionStateSide.LONG
    assert long_state.average_entry_price == "50"

    # Close: SELL 10 @ 70.
    snap_close = build_paper_fill_market_snapshot(
        snapshot_id="snap-close", market_symbol="BTC-PERPETUAL", reference_price="70"
    )
    fill_close = simulate_paper_fill(
        _intent(PaperOrderSide.SELL, suffix="close"),
        snap_close,
        policy,
        fill_simulation_id="fill-close",
        correlation_id="corr-fill",
    )
    transition_close, flat_again = apply_paper_fill_to_position(
        long_state, fill_close, transition_id="t-close", new_position_state_id="pos-flat", correlation_id="corr-apply"
    )
    assert flat_again is not None
    assert flat_again.side is PaperPositionStateSide.FLAT

    event = compute_paper_realized_pnl_event(
        long_state, fill_close, transition_close, realized_pnl_event_id="evt-e2e", correlation_id="corr-evt"
    )
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.closed_units == "10"
    assert event.realized_pnl == "200"  # 10 * (70 - 50)
    assert event.residual_open_units == "0"
    assert event.prior_position_state_digest == long_state.position_state_digest
    assert event.fill_simulation_result_digest == fill_close.result_digest
    assert event.position_transition_digest == transition_close.transition_digest
    assert event.new_position_state_digest == transition_close.new_position_state_digest
    assert paper_realized_pnl_event_digest(event) == event.realized_pnl_event_digest
