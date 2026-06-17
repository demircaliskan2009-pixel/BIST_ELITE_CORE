"""Tests for the deterministic paper fill simulator — generic, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from crypto_core.validation import paper_fill_simulator
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
    PaperFillSimulationError,
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_market_snapshot_digest,
    paper_fill_policy_digest,
    paper_fill_simulation_result_digest,
    paper_fill_simulation_result_to_dict,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import (
    PaperOrderIntent,
    build_paper_order_intent,
    paper_order_intent_digest,
)
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)

_DRAFT_HEX = "a" * 64

_EXPECTED_RESULT_KEYS = {
    "schema_version",
    "status",
    "fill_simulation_id",
    "intent_digest",
    "market_snapshot_digest",
    "fill_policy_digest",
    "market_symbol",
    "side",
    "intent_type",
    "fill_price",
    "filled_units",
    "unfilled_units",
    "gross_notional",
    "fee_amount",
    "reason_codes",
    "correlation_id",
    "metadata",
    "paper_only",
    "real_orders_enabled",
    "real_money_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "execution_authorized",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
    "position_mutated",
    "pnl_computed",
    "capital_reserved",
    "result_digest",
}

_SAFE_FALSE_FLAGS = (
    "real_orders_enabled",
    "real_money_enabled",
    "order_routed",
    "venue_order_id_created",
    "exchange_order_id_created",
    "client_order_id_created",
    "route_id_created",
    "execution_instruction_created",
    "execution_authorized",
    "live_api_called",
    "scheduler_enabled",
    "connector_invoked",
    "position_mutated",
    "pnl_computed",
    "capital_reserved",
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _make_draft() -> PaperAllocatorIntentDraft:
    fields: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": "sleeve-alpha",
        "policy_id": "policy-alpha",
        "readiness_digest": _DRAFT_HEX,
        "promotion_readiness_journal_entry_digest": _DRAFT_HEX,
        "promotion_readiness_payload_digest": _DRAFT_HEX,
        "promotion_candidate_journal_entry_digest": _DRAFT_HEX,
        "decision_journal_entry_digest": _DRAFT_HEX,
        "decision_journal_payload_digest": _DRAFT_HEX,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": "corr-draft",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def _intent(
    *,
    notional: str = "100000",
    units: str = "10",
    limit_price: str | None = "100",
    intent_type: PaperOrderIntentType = PaperOrderIntentType.LIMIT,
    side: PaperOrderSide = PaperOrderSide.BUY,
    market_symbol: str = "BTC-PERPETUAL",
) -> PaperOrderIntent:
    cap_policy = build_paper_capacity_gate_policy(
        policy_id="policy-alpha",
        sleeve_id="sleeve-alpha",
        max_notional="1000000",
        max_units="1000",
        max_open_intents=5,
    )
    capacity = evaluate_paper_capacity_gate(
        _make_draft(),
        cap_policy,
        requested_notional=notional,
        requested_units=units,
        correlation_id="corr-capacity",
    )
    request = build_paper_order_intent_request(
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=market_symbol,
        side=side,
        intent_type=intent_type,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=(limit_price if intent_type is PaperOrderIntentType.LIMIT else None),
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    assert admission.status.value == "ADMITTED"
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _snapshot(**overrides: object):
    base: dict[str, object] = {
        "snapshot_id": "snap-1",
        "market_symbol": "BTC-PERPETUAL",
        "reference_price": "50",
    }
    base.update(overrides)
    return build_paper_fill_market_snapshot(**base)  # type: ignore[arg-type]


def _policy(**overrides: object):
    base: dict[str, object] = {
        "policy_id": "fill-policy-1",
        "slippage_bps": "0",
        "fee_rate_bps": "0",
        "allow_partial_fill": False,
    }
    base.update(overrides)
    return build_paper_fill_policy(**base)  # type: ignore[arg-type]


def _simulate(intent, snapshot, policy, **overrides: object):
    base: dict[str, object] = {"fill_simulation_id": "fillsim-1", "correlation_id": "corr-fill"}
    base.update(overrides)
    return simulate_paper_fill(intent, snapshot, policy, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy paths
# --------------------------------------------------------------------------------------------------


def test_market_buy_full_fill() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy())
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.reason_codes == ()
    assert result.side == "BUY"
    assert result.intent_type == "MARKET"
    assert result.fill_price == "50"
    assert result.filled_units == "10"
    assert result.unfilled_units == "0"
    assert result.gross_notional == "500"
    assert result.fee_amount == "0"
    assert result.intent_digest == intent.intent_digest
    assert _is_hex64(result.result_digest)
    assert paper_fill_simulation_result_digest(result) == result.result_digest


def test_market_sell_full_fill() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.SELL, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy())
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.side == "SELL"
    assert result.fill_price == "50"
    assert result.filled_units == "10"


def test_fee_and_slippage_deterministic() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy(slippage_bps="100", fee_rate_bps="10"))
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.fill_price == "50.5"  # 50 * (1 + 100/10000)
    assert result.gross_notional == "505"  # 10 * 50.5
    assert result.fee_amount == "0.505"  # 505 * 10/10000


# --------------------------------------------------------------------------------------------------
# Limit semantics
# --------------------------------------------------------------------------------------------------


def test_limit_buy_rejected_when_price_exceeds_limit() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.LIMIT, side=PaperOrderSide.BUY, limit_price="100")
    result = _simulate(intent, _snapshot(reference_price="100"), _policy(slippage_bps="200"))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("limit_not_marketable",)
    assert result.filled_units == "0"
    assert result.gross_notional == "0"
    assert result.fee_amount == "0"


def test_limit_sell_rejected_when_price_below_limit() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.LIMIT, side=PaperOrderSide.SELL, limit_price="100")
    result = _simulate(intent, _snapshot(reference_price="100"), _policy(slippage_bps="200"))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("limit_not_marketable",)


def test_limit_buy_marketable_fills() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.LIMIT, side=PaperOrderSide.BUY, limit_price="100")
    result = _simulate(intent, _snapshot(reference_price="90"), _policy(slippage_bps="100"))
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.fill_price == "90.9"  # 90 * 1.01 <= 100


def test_limit_buy_equality_marketable() -> None:
    # fill_price == limit_price is marketable (reject only on strictly greater).
    intent = _intent(intent_type=PaperOrderIntentType.LIMIT, side=PaperOrderSide.BUY, limit_price="100")
    result = _simulate(intent, _snapshot(reference_price="100"), _policy(slippage_bps="0"))
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.fill_price == "100"


def test_limit_sell_equality_marketable() -> None:
    # fill_price == limit_price is marketable (reject only on strictly less).
    intent = _intent(intent_type=PaperOrderIntentType.LIMIT, side=PaperOrderSide.SELL, limit_price="100")
    result = _simulate(intent, _snapshot(reference_price="100"), _policy(slippage_bps="0"))
    assert result.status is PaperFillSimulationStatus.FILLED
    assert result.fill_price == "100"


# --------------------------------------------------------------------------------------------------
# Liquidity / partial / min-fill / notional cap
# --------------------------------------------------------------------------------------------------


def test_partial_fill_allowed() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50", available_units="4"), _policy(allow_partial_fill=True))
    assert result.status is PaperFillSimulationStatus.PARTIALLY_FILLED
    assert "partial_fill" in result.reason_codes
    assert result.filled_units == "4"
    assert result.unfilled_units == "6"
    assert result.gross_notional == "200"


def test_insufficient_liquidity_rejected_when_partial_disabled() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50", available_units="4"), _policy(allow_partial_fill=False))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("insufficient_liquidity",)


def test_zero_liquidity_rejected_even_with_partial() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50", available_units="0"), _policy(allow_partial_fill=True))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("insufficient_liquidity",)


def test_min_fill_not_met_rejected() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.BUY, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy(min_fill_units="20"))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert "min_fill_not_met" in result.reason_codes


def test_gross_notional_over_request_rejected() -> None:
    intent = _intent(notional="100", units="10", intent_type=PaperOrderIntentType.MARKET, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy())  # 10 * 50 = 500 > 100
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert "gross_notional_exceeds_request" in result.reason_codes
    assert result.filled_units == "0"
    assert result.gross_notional == "0"


def test_high_precision_reference_price_not_rounded_down_past_notional_cap() -> None:
    intent = _intent(notional="1", units="1", intent_type=PaperOrderIntentType.MARKET, limit_price=None)
    snapshot = _snapshot(reference_price="1.000000000000000000000000000000000000001")

    result = _simulate(intent, snapshot, _policy())

    assert snapshot.reference_price == "1.000000000000000000000000000000000000001"
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("gross_notional_exceeds_request",)
    assert result.filled_units == "0"
    assert result.gross_notional == "0"


def test_reason_codes_deterministic_and_sorted() -> None:
    # min_fill_not_met AND gross_notional_exceeds_request both fire on the same candidate.
    intent = _intent(notional="100", units="10", intent_type=PaperOrderIntentType.MARKET, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy(min_fill_units="20"))
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("gross_notional_exceeds_request", "min_fill_not_met")
    assert list(result.reason_codes) == sorted(result.reason_codes)


def test_non_positive_fill_price_rejected() -> None:
    intent = _intent(intent_type=PaperOrderIntentType.MARKET, side=PaperOrderSide.SELL, limit_price=None)
    result = _simulate(intent, _snapshot(reference_price="50"), _policy(slippage_bps="10000"))  # 1 - 1 = 0
    assert result.status is PaperFillSimulationStatus.REJECTED
    assert result.reason_codes == ("non_positive_fill_price",)


# --------------------------------------------------------------------------------------------------
# Fail-closed (typed errors)
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_intent_rejected() -> None:
    with pytest.raises(PaperFillSimulationError, match="intent_malformed"):
        simulate_paper_fill(
            {"not": "intent"},  # type: ignore[arg-type]
            _snapshot(),
            _policy(),
            fill_simulation_id="f",
            correlation_id="c",
        )


def test_intent_digest_mismatch_rejected() -> None:
    intent = replace(_intent(), intent_digest="d" * 64)
    with pytest.raises(PaperFillSimulationError, match="intent_digest_mismatch"):
        _simulate(intent, _snapshot(), _policy())


@pytest.mark.parametrize(
    "flag",
    ["real_orders_enabled", "capital_reserved", "order_routed", "fill_created", "position_mutated", "live_api_called"],
)
def test_forged_self_consistent_unsafe_intent_rejected(flag: str) -> None:
    intent = replace(_intent(), **{flag: True})
    intent = replace(intent, intent_digest=paper_order_intent_digest(intent))
    with pytest.raises(PaperFillSimulationError, match="intent_unsafe_flags"):
        _simulate(intent, _snapshot(), _policy())


@pytest.mark.parametrize(
    "override",
    [
        {"correlation_id": "live_order"},
        {"market_symbol": "place_order-PERP"},
        {"market_symbol": "bist100"},
        {"metadata": (("note", "place_order"),)},
    ],
)
def test_forged_intent_forbidden_token_rejected(override: dict[str, object]) -> None:
    intent = replace(_intent(), **override)
    intent = replace(intent, intent_digest=paper_order_intent_digest(intent))
    # _reprove_intent scans the intent's own fields and raises before the snapshot symbol-match check.
    with pytest.raises(PaperFillSimulationError, match="intent_scope_violation"):
        _simulate(intent, _snapshot(), _policy())


def test_forged_intent_not_created_rejected() -> None:
    # A LIMIT-with-no-limit_price forged intent is structurally malformed.
    intent = replace(_intent(intent_type=PaperOrderIntentType.LIMIT, limit_price="100"), limit_price=None)
    intent = replace(intent, intent_digest=paper_order_intent_digest(intent))
    with pytest.raises(PaperFillSimulationError, match="intent_malformed"):
        _simulate(intent, _snapshot(), _policy())


def test_malformed_snapshot_rejected() -> None:
    forged = replace(_snapshot(), reference_price="0")
    forged = replace(forged, snapshot_digest=paper_fill_market_snapshot_digest(forged))
    with pytest.raises(PaperFillSimulationError, match="snapshot_malformed"):
        _simulate(_intent(), forged, _policy())


def test_snapshot_digest_mismatch_rejected() -> None:
    forged = replace(_snapshot(), snapshot_digest="d" * 64)
    with pytest.raises(PaperFillSimulationError, match="snapshot_digest_mismatch"):
        _simulate(_intent(), forged, _policy())


def test_malformed_policy_rejected() -> None:
    forged = replace(_policy(), slippage_bps="-1")
    forged = replace(forged, policy_digest=paper_fill_policy_digest(forged))
    with pytest.raises(PaperFillSimulationError, match="policy_malformed"):
        _simulate(_intent(), _snapshot(), forged)


def test_policy_digest_mismatch_rejected() -> None:
    forged = replace(_policy(), policy_digest="d" * 64)
    with pytest.raises(PaperFillSimulationError, match="policy_digest_mismatch"):
        _simulate(_intent(), _snapshot(), forged)


def test_snapshot_symbol_mismatch_rejected() -> None:
    intent = _intent(market_symbol="BTC-PERPETUAL")
    snapshot = _snapshot(market_symbol="ETH-PERPETUAL")
    with pytest.raises(PaperFillSimulationError, match="snapshot_symbol_mismatch"):
        _simulate(intent, snapshot, _policy())


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_fill_simulation_id_rejected(bad: str) -> None:
    with pytest.raises(PaperFillSimulationError, match="fill_simulation_id_invalid"):
        _simulate(_intent(), _snapshot(), _policy(), fill_simulation_id=bad)


def test_gate_forbidden_correlation_rejected() -> None:
    with pytest.raises(PaperFillSimulationError, match="scope_violation"):
        _simulate(_intent(), _snapshot(), _policy(), correlation_id="live_order")


def test_gate_metadata_malformed_rejected() -> None:
    with pytest.raises(PaperFillSimulationError, match="metadata_malformed"):
        _simulate(_intent(), _snapshot(), _policy(), metadata={"k": 5})  # type: ignore[dict-item]


@pytest.mark.parametrize("bad", ["0", "-1", "abc", "1e5", ""])
def test_build_snapshot_rejects_bad_reference_price(bad: str) -> None:
    with pytest.raises(PaperFillSimulationError, match="reference_price"):
        _snapshot(reference_price=bad)


@pytest.mark.parametrize("bad", ["-1", "abc", "1e5"])
def test_build_policy_rejects_negative_bps(bad: str) -> None:
    with pytest.raises(PaperFillSimulationError, match="slippage_bps"):
        _policy(slippage_bps=bad)


def test_build_policy_rejects_non_bool_partial() -> None:
    with pytest.raises(PaperFillSimulationError, match="allow_partial_fill_not_bool"):
        _policy(allow_partial_fill="yes")


def test_policy_high_precision_bps_are_not_context_rounded() -> None:
    high_precision = "1.000000000000000000000000000000000000001"
    policy = _policy(slippage_bps=high_precision, fee_rate_bps=high_precision)

    assert policy.slippage_bps == high_precision
    assert policy.fee_rate_bps == high_precision


def test_build_policy_rejects_forbidden_token() -> None:
    with pytest.raises(PaperFillSimulationError, match="policy_scope_violation"):
        _policy(policy_id="place_order")


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-mutation / no-leak / chain
# --------------------------------------------------------------------------------------------------


def test_result_digest_deterministic() -> None:
    intent, snapshot, policy = _intent(), _snapshot(), _policy()
    first = _simulate(intent, snapshot, policy)
    second = _simulate(intent, snapshot, policy)
    assert first == second
    assert first.result_digest == second.result_digest


def test_result_is_immutable() -> None:
    result = _simulate(_intent(), _snapshot(), _policy())
    with pytest.raises(FrozenInstanceError):
        result.fill_price = "1"  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    intent, snapshot, policy = _intent(), _snapshot(), _policy()
    intent_before = paper_order_intent_digest(intent)
    snapshot_before = paper_fill_market_snapshot_digest(snapshot)
    policy_before = paper_fill_policy_digest(policy)
    _simulate(intent, snapshot, policy)
    assert paper_order_intent_digest(intent) == intent_before
    assert paper_fill_market_snapshot_digest(snapshot) == snapshot_before
    assert paper_fill_policy_digest(policy) == policy_before


def test_to_dict_roundtrips_digest_and_keys() -> None:
    result = _simulate(_intent(), _snapshot(), _policy())
    payload = paper_fill_simulation_result_to_dict(result)
    assert set(payload) == _EXPECTED_RESULT_KEYS
    assert payload["result_digest"] == result.result_digest
    assert payload["paper_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False


def test_no_forbidden_value_fields_in_result_payload() -> None:
    payload = paper_fill_simulation_result_to_dict(_simulate(_intent(), _snapshot(), _policy()))
    # Forbidden execution/routing concepts must NOT appear as bare id/value keys — only as False booleans.
    bare_forbidden = (
        "venue_order_id",
        "exchange_order_id",
        "client_order_id",
        "route_id",
        "execution_instruction",
        "order_id",
        "position_id",
        "pnl_value",
    )
    for token in bare_forbidden:
        assert token not in payload, f"bare forbidden field {token!r} present in payload"


def test_chain_digests_echoed() -> None:
    intent, snapshot, policy = _intent(), _snapshot(), _policy()
    result = _simulate(intent, snapshot, policy)
    assert result.intent_digest == intent.intent_digest
    assert result.market_snapshot_digest == snapshot.snapshot_digest
    assert result.fill_policy_digest == policy.policy_digest
    assert result.market_symbol == intent.market_symbol


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_fill_simulator.__file__).read_text(encoding="utf-8")
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
