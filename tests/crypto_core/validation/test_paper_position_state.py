"""Tests for the paper position state transition — deterministic, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_position_state
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
    PaperPositionStateError,
    PaperPositionStateSide,
    PaperPositionTransitionStatus,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
    paper_position_state_digest,
    paper_position_state_to_dict,
    paper_position_transition_result_digest,
    paper_position_transition_result_to_dict,
)

_HEX = "b" * 64

_EXPECTED_STATE_KEYS = {
    "schema_version",
    "position_state_id",
    "market_symbol",
    "side",
    "signed_units",
    "abs_units",
    "average_entry_price",
    "last_fill_simulation_digest",
    "transition_count",
    "correlation_id",
    "metadata",
    "position_state_digest",
    "paper_only",
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
    "connector_invoked",
    "pnl_computed",
    "capital_reserved",
    "capital_mutated",
}

_EXPECTED_TRANSITION_KEYS = {
    "schema_version",
    "transition_id",
    "status",
    "prior_position_state_digest",
    "fill_simulation_result_digest",
    "new_position_state_digest",
    "market_symbol",
    "reason_codes",
    "correlation_id",
    "metadata",
    "transition_digest",
    "paper_only",
    "paper_position_state_updated",
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
    "connector_invoked",
    "pnl_computed",
    "capital_reserved",
    "capital_mutated",
}

_SAFE_FALSE_STATE_FLAGS = (
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
    "connector_invoked",
    "pnl_computed",
    "capital_reserved",
    "capital_mutated",
)

_BARE_FORBIDDEN_KEYS = (
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
    "order_id",
    "position_id",
    "pnl_value",
    "realized_pnl",
    "unrealized_pnl",
    "balance",
    "capital_balance",
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _flat(**overrides: object):
    base: dict[str, object] = {
        "position_state_id": "pos-1",
        "market_symbol": "BTC-PERPETUAL",
        "correlation_id": "corr-pos",
    }
    base.update(overrides)
    return build_flat_paper_position_state(**base)  # type: ignore[arg-type]


def _state(**overrides: object):
    base: dict[str, object] = {
        "position_state_id": "pos-1",
        "market_symbol": "BTC-PERPETUAL",
        "side": PaperPositionStateSide.LONG,
        "signed_units": "10",
        "abs_units": "10",
        "average_entry_price": "100",
        "transition_count": 0,
        "correlation_id": "corr-pos",
    }
    base.update(overrides)
    return build_paper_position_state(**base)  # type: ignore[arg-type]


def _fill(**overrides: object) -> PaperFillSimulationResult:
    base = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=PaperFillSimulationStatus.FILLED,
        fill_simulation_id="fillsim-1",
        intent_digest=_HEX,
        market_snapshot_digest=_HEX,
        fill_policy_digest=_HEX,
        market_symbol="BTC-PERPETUAL",
        side="BUY",
        intent_type="MARKET",
        fill_price="100",
        filled_units="10",
        unfilled_units="0",
        gross_notional="1000",
        fee_amount="0",
        reason_codes=(),
        correlation_id="corr-fill",
        metadata=(),
        result_digest="",
    )
    base = replace(base, **overrides)
    return replace(base, result_digest=paper_fill_simulation_result_digest(base))


def _apply(prior, fill, **overrides: object):
    base: dict[str, object] = {
        "transition_id": "trans-1",
        "new_position_state_id": "pos-2",
        "correlation_id": "corr-apply",
    }
    base.update(overrides)
    return apply_paper_fill_to_position(prior, fill, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------------------------------


def test_build_flat_state() -> None:
    state = _flat()
    assert state.side is PaperPositionStateSide.FLAT
    assert state.signed_units == "0"
    assert state.abs_units == "0"
    assert state.average_entry_price is None
    assert state.transition_count == 0
    assert _is_hex64(state.position_state_digest)
    assert paper_position_state_digest(state) == state.position_state_digest


def test_build_long_state() -> None:
    state = _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100")
    assert state.side is PaperPositionStateSide.LONG
    assert state.signed_units == "10"


def test_build_short_state() -> None:
    state = _state(side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100")
    assert state.side is PaperPositionStateSide.SHORT
    assert state.signed_units == "-10"
    assert state.abs_units == "10"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"side": PaperPositionStateSide.LONG, "signed_units": "-10", "abs_units": "10", "average_entry_price": "100"},
        {"side": PaperPositionStateSide.SHORT, "signed_units": "10", "abs_units": "10", "average_entry_price": "100"},
        {"side": PaperPositionStateSide.LONG, "signed_units": "10", "abs_units": "5", "average_entry_price": "100"},
        {"side": PaperPositionStateSide.FLAT, "signed_units": "0", "abs_units": "0", "average_entry_price": "100"},
        {"side": PaperPositionStateSide.LONG, "signed_units": "10", "abs_units": "10", "average_entry_price": None},
        {"side": PaperPositionStateSide.LONG, "signed_units": "0", "abs_units": "0", "average_entry_price": "100"},
        {"side": PaperPositionStateSide.LONG, "signed_units": "10", "abs_units": "10", "average_entry_price": "0"},
    ],
)
def test_build_inconsistent_state_rejected(kwargs: dict[str, object]) -> None:
    with pytest.raises(PaperPositionStateError):
        _state(**kwargs)


def test_build_transition_count_negative_rejected() -> None:
    with pytest.raises(PaperPositionStateError, match="transition_count_invalid"):
        _state(transition_count=-1)


# --------------------------------------------------------------------------------------------------
# Transition semantics
# --------------------------------------------------------------------------------------------------


def test_buy_from_flat_opens_long() -> None:
    transition, new_state = _apply(_flat(), _fill(side="BUY", filled_units="10", fill_price="100"))
    assert transition.status is PaperPositionTransitionStatus.APPLIED
    assert transition.reason_codes == ()
    assert transition.paper_position_state_updated is True
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "10"
    assert new_state.abs_units == "10"
    assert new_state.average_entry_price == "100"
    assert new_state.transition_count == 1
    assert new_state.last_fill_simulation_digest == _fill(side="BUY", filled_units="10", fill_price="100").result_digest
    assert transition.new_position_state_digest == new_state.position_state_digest


def test_sell_from_flat_opens_short() -> None:
    _, new_state = _apply(_flat(), _fill(side="SELL", filled_units="10", fill_price="100"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.SHORT
    assert new_state.signed_units == "-10"
    assert new_state.abs_units == "10"
    assert new_state.average_entry_price == "100"


def test_buy_adds_to_long_weighted_average() -> None:
    prior = _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="BUY", filled_units="10", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "20"
    assert new_state.average_entry_price == "150"  # (10*100 + 10*200)/20


def test_sell_adds_to_short_weighted_average() -> None:
    prior = _state(side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="SELL", filled_units="10", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.SHORT
    assert new_state.signed_units == "-20"
    assert new_state.average_entry_price == "150"


def test_sell_reduces_long_without_crossing_preserves_average() -> None:
    prior = _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="SELL", filled_units="4", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "6"
    assert new_state.average_entry_price == "100"  # preserved, no PnL


def test_buy_reduces_short_without_crossing_preserves_average() -> None:
    prior = _state(side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="BUY", filled_units="4", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.SHORT
    assert new_state.signed_units == "-6"
    assert new_state.average_entry_price == "100"


def test_fill_closes_long_to_flat() -> None:
    prior = _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="SELL", filled_units="10", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.FLAT
    assert new_state.signed_units == "0"
    assert new_state.abs_units == "0"
    assert new_state.average_entry_price is None


def test_fill_closes_short_to_flat() -> None:
    prior = _state(side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="BUY", filled_units="10", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.FLAT
    assert new_state.average_entry_price is None


def test_sell_crosses_long_to_short_sets_avg_to_fill() -> None:
    prior = _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="SELL", filled_units="15", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.SHORT
    assert new_state.signed_units == "-5"
    assert new_state.average_entry_price == "200"  # residual opened at fill price


def test_buy_crosses_short_to_long_sets_avg_to_fill() -> None:
    prior = _state(side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100")
    _, new_state = _apply(prior, _fill(side="BUY", filled_units="15", fill_price="200"))
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "5"
    assert new_state.average_entry_price == "200"


def test_partial_fill_applies_only_filled_units() -> None:
    transition, new_state = _apply(
        _flat(),
        _fill(status=PaperFillSimulationStatus.PARTIALLY_FILLED, side="BUY", filled_units="4", fill_price="100"),
    )
    assert transition.status is PaperPositionTransitionStatus.APPLIED
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "4"


def test_transition_count_increments_by_one() -> None:
    prior = _state(
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="100",
        transition_count=5,
    )
    _, new_state = _apply(prior, _fill(side="BUY", filled_units="2", fill_price="100"))
    assert new_state is not None
    assert new_state.transition_count == 6


# --------------------------------------------------------------------------------------------------
# REJECTED / fail-closed
# --------------------------------------------------------------------------------------------------


def test_rejected_fill_returns_rejected_transition() -> None:
    rejected_fill = _fill(
        status=PaperFillSimulationStatus.REJECTED,
        filled_units="0",
        gross_notional="0",
        reason_codes=("insufficient_liquidity",),
    )
    transition, new_state = _apply(_flat(), rejected_fill)
    assert transition.status is PaperPositionTransitionStatus.REJECTED
    assert transition.reason_codes == ("fill_not_applied",)
    assert transition.new_position_state_digest is None
    assert transition.paper_position_state_updated is False
    assert new_state is None


def test_symbol_mismatch_raises() -> None:
    with pytest.raises(PaperPositionStateError, match="symbol_mismatch"):
        _apply(_flat(market_symbol="BTC-PERPETUAL"), _fill(market_symbol="ETH-PERPETUAL"))


def test_prior_state_digest_mismatch_raises() -> None:
    prior = replace(_flat(), position_state_digest="d" * 64)
    with pytest.raises(PaperPositionStateError, match="prior_state_digest_mismatch"):
        _apply(prior, _fill())


def test_fill_result_digest_mismatch_raises() -> None:
    fill = replace(_fill(), result_digest="d" * 64)
    with pytest.raises(PaperPositionStateError, match="fill_result_digest_mismatch"):
        _apply(_flat(), fill)


def test_forged_self_consistent_prior_state_rejected() -> None:
    forged = replace(
        _state(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10", average_entry_price="100"),
        side=PaperPositionStateSide.SHORT,
    )
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperPositionStateError, match="prior_state_inconsistent"):
        _apply(forged, _fill())


def test_forged_unsafe_prior_state_rejected() -> None:
    forged = replace(_flat(), capital_mutated=True)
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperPositionStateError, match="prior_state_unsafe_flags"):
        _apply(forged, _fill())


def test_forged_unsafe_fill_result_rejected() -> None:
    forged = replace(_fill(), real_orders_enabled=True)
    forged = replace(forged, result_digest=paper_fill_simulation_result_digest(forged))
    with pytest.raises(PaperPositionStateError, match="fill_result_unsafe_flags"):
        _apply(_flat(), forged)


@pytest.mark.parametrize("override", [{"market_symbol": "place_order-PERP"}, {"correlation_id": "live_order"}])
def test_forged_fill_forbidden_token_rejected(override: dict[str, object]) -> None:
    forged = replace(_fill(), **override)
    forged = replace(forged, result_digest=paper_fill_simulation_result_digest(forged))
    # _reprove_fill_result scans the fill's own fields and raises before the symbol-match check.
    with pytest.raises(PaperPositionStateError):
        _apply(_flat(), forged)


def test_wrong_typed_inputs_raise() -> None:
    with pytest.raises(PaperPositionStateError, match="prior_state_malformed"):
        apply_paper_fill_to_position(
            {"x": 1}, _fill(), transition_id="t", new_position_state_id="p", correlation_id="c"
        )  # type: ignore[arg-type]
    with pytest.raises(PaperPositionStateError, match="fill_result_malformed"):
        apply_paper_fill_to_position(
            _flat(), {"x": 1}, transition_id="t", new_position_state_id="p", correlation_id="c"
        )  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    [("transition_id", "place_order"), ("new_position_state_id", "live_x"), ("correlation_id", "shadow")],
)
def test_apply_scope_violation_raises(field: str, value: str) -> None:
    with pytest.raises(PaperPositionStateError, match="scope_violation"):
        _apply(_flat(), _fill(), **{field: value})


def test_apply_metadata_malformed_raises() -> None:
    with pytest.raises(PaperPositionStateError, match="metadata_malformed"):
        _apply(_flat(), _fill(), metadata={"k": 5})  # type: ignore[dict-item]


# --------------------------------------------------------------------------------------------------
# Precision / determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_high_precision_values_preserved_exactly() -> None:
    high_units = "1.000000000000000000000000000000000000001"
    high_price = "2.000000000000000000000000000000000000001"
    _, new_state = _apply(_flat(), _fill(side="BUY", filled_units=high_units, fill_price=high_price))
    assert new_state is not None
    assert new_state.signed_units == high_units  # exact addition from flat, no rounding
    assert new_state.abs_units == high_units
    assert new_state.average_entry_price == high_price  # open-from-flat avg = fill price, exact


def test_digests_deterministic() -> None:
    prior, fill = _flat(), _fill()
    t1, s1 = _apply(prior, fill)
    t2, s2 = _apply(prior, fill)
    assert t1 == t2
    assert t1.transition_digest == t2.transition_digest
    assert s1 is not None and s2 is not None
    assert s1.position_state_digest == s2.position_state_digest
    assert paper_position_transition_result_digest(t1) == t1.transition_digest


def test_outputs_immutable() -> None:
    transition, new_state = _apply(_flat(), _fill())
    with pytest.raises(FrozenInstanceError):
        transition.status = PaperPositionTransitionStatus.REJECTED  # type: ignore[misc]
    assert new_state is not None
    with pytest.raises(FrozenInstanceError):
        new_state.signed_units = "1"  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    prior, fill = _flat(), _fill()
    prior_before = paper_position_state_digest(prior)
    fill_before = paper_fill_simulation_result_digest(fill)
    _apply(prior, fill)
    assert paper_position_state_digest(prior) == prior_before
    assert paper_fill_simulation_result_digest(fill) == fill_before
    assert prior.position_state_digest == prior_before


def test_reason_codes_status_consistent() -> None:
    applied, _ = _apply(_flat(), _fill())
    assert applied.status is PaperPositionTransitionStatus.APPLIED
    assert applied.reason_codes == ()
    rejected, _ = _apply(_flat(), _fill(status=PaperFillSimulationStatus.REJECTED, filled_units="0"))
    assert rejected.status is PaperPositionTransitionStatus.REJECTED
    assert rejected.reason_codes and list(rejected.reason_codes) == sorted(rejected.reason_codes)


def test_state_dict_keys_and_safe_flags() -> None:
    _, new_state = _apply(_flat(), _fill())
    assert new_state is not None
    payload = paper_position_state_to_dict(new_state)
    assert set(payload) == _EXPECTED_STATE_KEYS
    assert payload["paper_only"] is True
    for flag in _SAFE_FALSE_STATE_FLAGS:
        assert payload[flag] is False
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_transition_dict_keys_and_no_forbidden_fields() -> None:
    transition, _ = _apply(_flat(), _fill())
    payload = paper_position_transition_result_to_dict(transition)
    assert set(payload) == _EXPECTED_TRANSITION_KEYS
    assert payload["transition_digest"] == transition.transition_digest
    assert payload["paper_only"] is True
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_no_pnl_or_capital_value_fields() -> None:
    payload = paper_position_state_to_dict(_apply(_flat(), _fill())[1])
    # PnL/capital appear ONLY as False negative-attestation booleans, never as value fields.
    assert payload["pnl_computed"] is False
    assert payload["capital_reserved"] is False
    assert payload["capital_mutated"] is False
    for token in ("pnl_value", "realized_pnl", "unrealized_pnl", "balance", "capital_balance"):
        assert token not in payload


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_position_state.__file__).read_text(encoding="utf-8")
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
# End-to-end chain: intent -> fill -> position
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


def test_end_to_end_intent_fill_position_chain() -> None:
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="1000000",
        max_units="1000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(), cap_policy, requested_notional="100000", requested_units="10", correlation_id="corr-capacity"
    )
    request = build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol="BTC-PERPETUAL",
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    intent = build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id="snap-1", market_symbol="BTC-PERPETUAL", reference_price="50"
    )
    policy = build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    fill = simulate_paper_fill(intent, snapshot, policy, fill_simulation_id="fillsim-1", correlation_id="corr-fill")
    assert fill.status is PaperFillSimulationStatus.FILLED

    transition, new_state = apply_paper_fill_to_position(
        build_flat_paper_position_state(
            position_state_id="pos-1", market_symbol="BTC-PERPETUAL", correlation_id="corr-pos"
        ),
        fill,
        transition_id="trans-1",
        new_position_state_id="pos-2",
        correlation_id="corr-apply",
    )
    assert transition.status is PaperPositionTransitionStatus.APPLIED
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.signed_units == "10"
    assert new_state.average_entry_price == "50"
    assert new_state.last_fill_simulation_digest == fill.result_digest
