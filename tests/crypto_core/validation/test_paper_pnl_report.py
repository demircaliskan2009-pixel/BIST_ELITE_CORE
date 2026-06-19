"""Tests for the paper mark-to-market PnL report — deterministic, paper-only, fail-closed."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_pnl_report
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
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import (
    PaperMarkSnapshot,
    PaperPnlReportError,
    PaperPnlReportStatus,
    build_paper_mark_snapshot,
    compute_paper_pnl_report,
    paper_mark_snapshot_digest,
    paper_mark_snapshot_to_dict,
    paper_pnl_report_digest,
    paper_pnl_report_to_dict,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
    paper_position_state_digest,
)

_EXPECTED_MARK_KEYS = {
    "schema_version",
    "mark_snapshot_id",
    "market_symbol",
    "mark_price",
    "observed_at_ns",
    "mark_source_id",
    "correlation_id",
    "metadata",
    "mark_snapshot_digest",
}

_EXPECTED_REPORT_KEYS = {
    "schema_version",
    "pnl_report_id",
    "status",
    "position_state_digest",
    "mark_snapshot_digest",
    "market_symbol",
    "position_side",
    "signed_units",
    "abs_units",
    "average_entry_price",
    "mark_price",
    "mark_notional",
    "unrealized_pnl",
    "realized_pnl",
    "total_pnl",
    "reason_codes",
    "correlation_id",
    "metadata",
    "pnl_report_digest",
    "paper_only",
    "pnl_computed",
    "realized_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "position_mutated",
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
}

_SAFE_FALSE_REPORT_FLAGS = (
    "realized_pnl_computed",
    "capital_reserved",
    "capital_mutated",
    "balance_mutated",
    "position_mutated",
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
)

# Exact dict keys that must NEVER appear in the report payload (value fields, not the *_created/_mutated
# negative attestations which are allowed False booleans).
_BARE_FORBIDDEN_KEYS = (
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
    "order_id",
    "position_id",
    "realized_pnl_value",
    "total_pnl_value",
    "unrealized_pnl_value",
    "equity",
    "margin",
    "balance",
    "capital",
    "capital_balance",
    "fee",
    "fee_amount",
    "funding",
    "gross_notional",
)


def _is_hex64(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _position(**overrides: object):
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


def _flat_position(**overrides: object):
    base: dict[str, object] = {
        "position_state_id": "pos-flat",
        "market_symbol": "BTC-PERPETUAL",
        "correlation_id": "corr-pos",
    }
    base.update(overrides)
    return build_flat_paper_position_state(**base)  # type: ignore[arg-type]


def _mark(**overrides: object) -> PaperMarkSnapshot:
    base: dict[str, object] = {
        "mark_snapshot_id": "mark-1",
        "market_symbol": "BTC-PERPETUAL",
        "mark_price": "150",
        "correlation_id": "corr-mark",
    }
    base.update(overrides)
    return build_paper_mark_snapshot(**base)  # type: ignore[arg-type]


def _compute(position, mark, **overrides: object):
    base: dict[str, object] = {"pnl_report_id": "pnl-1", "correlation_id": "corr-pnl"}
    base.update(overrides)
    return compute_paper_pnl_report(position, mark, **base)  # type: ignore[arg-type]


def _mtm_oracle(side: str, abs_units: str, avg: str, mark: str) -> tuple[str, str]:
    """Independent exact MTM oracle (wide context). Mirrors the module's pure-product semantics."""

    def render(value: Decimal) -> str:
        rendered = format(value, "f")
        if "." in rendered:
            rendered = rendered.rstrip("0").rstrip(".")
        return "0" if rendered in {"", "-0"} else rendered

    if side == "FLAT":
        return "0", "0"
    with localcontext() as ctx:
        ctx.prec = 200  # wide enough to keep the products/differences exact for these test inputs
        a, m, v = Decimal(abs_units), Decimal(mark), Decimal(avg)
        notional = a * m
        unrealized = a * (m - v) if side == "LONG" else a * (v - m)
    return render(notional), render(unrealized)


# --------------------------------------------------------------------------------------------------
# Mark snapshot
# --------------------------------------------------------------------------------------------------


def test_build_mark_snapshot() -> None:
    mark = _mark(mark_price="150", observed_at_ns=123, mark_source_id="mark-src-1")
    assert mark.schema_version == "paper-mark-snapshot.v1"
    assert mark.market_symbol == "BTC-PERPETUAL"
    assert mark.mark_price == "150"
    assert mark.observed_at_ns == 123
    assert mark.mark_source_id == "mark-src-1"
    assert _is_hex64(mark.mark_snapshot_digest)
    assert paper_mark_snapshot_digest(mark) == mark.mark_snapshot_digest


@pytest.mark.parametrize("bad_price", ["0", "-5", "0.0", "abc", "1e3", "", "  ", "00", ".5", "1."])
def test_mark_snapshot_rejects_bad_mark_price(bad_price: str) -> None:
    with pytest.raises(PaperPnlReportError, match="mark_price_invalid"):
        _mark(mark_price=bad_price)


def test_mark_snapshot_to_dict_keys() -> None:
    payload = paper_mark_snapshot_to_dict(_mark(observed_at_ns=5, mark_source_id="src-1"))
    assert set(payload) == _EXPECTED_MARK_KEYS


def test_mark_snapshot_digest_deterministic() -> None:
    assert _mark().mark_snapshot_digest == _mark().mark_snapshot_digest


# --------------------------------------------------------------------------------------------------
# MTM semantics
# --------------------------------------------------------------------------------------------------


def test_flat_position_zero_pnl() -> None:
    report = _compute(_flat_position(), _mark(mark_price="150"))
    assert report.status is PaperPnlReportStatus.COMPUTED
    assert report.position_side is PaperPositionStateSide.FLAT
    assert report.signed_units == "0"
    assert report.abs_units == "0"
    assert report.average_entry_price is None
    assert report.mark_notional == "0"
    assert report.unrealized_pnl == "0"
    assert report.realized_pnl is None
    assert report.total_pnl is None


def test_long_positive_unrealized_pnl() -> None:
    report = _compute(_position(signed_units="10", abs_units="10", average_entry_price="100"), _mark(mark_price="150"))
    assert report.position_side is PaperPositionStateSide.LONG
    assert report.mark_notional == "1500"  # 10 * 150
    assert report.unrealized_pnl == "500"  # 10 * (150 - 100)


def test_long_negative_unrealized_pnl() -> None:
    report = _compute(_position(signed_units="10", abs_units="10", average_entry_price="100"), _mark(mark_price="80"))
    assert report.position_side is PaperPositionStateSide.LONG
    assert report.mark_notional == "800"  # 10 * 80
    assert report.unrealized_pnl == "-200"  # 10 * (80 - 100)


def test_short_positive_unrealized_pnl() -> None:
    position = _position(
        side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100"
    )
    report = _compute(position, _mark(mark_price="80"))
    assert report.position_side is PaperPositionStateSide.SHORT
    assert report.signed_units == "-10"
    assert report.mark_notional == "800"  # 10 * 80
    assert report.unrealized_pnl == "200"  # 10 * (100 - 80)


def test_short_negative_unrealized_pnl() -> None:
    position = _position(
        side=PaperPositionStateSide.SHORT, signed_units="-10", abs_units="10", average_entry_price="100"
    )
    report = _compute(position, _mark(mark_price="150"))
    assert report.position_side is PaperPositionStateSide.SHORT
    assert report.mark_notional == "1500"  # 10 * 150
    assert report.unrealized_pnl == "-500"  # 10 * (100 - 150)


def test_unrealized_pnl_zero_at_mark_equals_average() -> None:
    report = _compute(_position(average_entry_price="100"), _mark(mark_price="100"))
    assert report.unrealized_pnl == "0"  # no negative zero
    assert report.mark_notional == "1000"


# --------------------------------------------------------------------------------------------------
# High precision / no context rounding
# --------------------------------------------------------------------------------------------------


def test_high_precision_long_exact_no_context_rounding() -> None:
    # mark - avg differs only at the 40th significant digit; a default 28-digit context would lose it.
    mark_price = "1." + "0" * 39 + "1"
    position = _position(signed_units="1", abs_units="1", average_entry_price="1")
    report = _compute(position, _mark(mark_price=mark_price))
    expected_notional, expected_unrealized = _mtm_oracle("LONG", "1", "1", mark_price)
    assert report.mark_notional == expected_notional == mark_price
    assert report.unrealized_pnl == expected_unrealized == "0." + "0" * 39 + "1"


def test_high_precision_short_exact_no_context_rounding() -> None:
    abs_units = "1.000000000000000000000000000001"  # 31 significant digits
    mark_price = "1.000000000000000000000000000001"
    position = _position(
        side=PaperPositionStateSide.SHORT,
        signed_units="-1.000000000000000000000000000001",
        abs_units=abs_units,
        average_entry_price="1",
    )
    report = _compute(position, _mark(mark_price=mark_price))
    expected_notional, expected_unrealized = _mtm_oracle("SHORT", abs_units, "1", mark_price)
    assert report.mark_notional == expected_notional
    assert report.unrealized_pnl == expected_unrealized
    # The product genuinely exceeds default precision, proving input-derived context arithmetic.
    assert len(report.mark_notional.replace(".", "").lstrip("0")) > 28


def test_high_precision_report_digest_deterministic() -> None:
    mark_price = "1." + "0" * 39 + "1"
    position = _position(signed_units="1", abs_units="1", average_entry_price="1")
    r1 = _compute(position, _mark(mark_price=mark_price))
    r2 = _compute(position, _mark(mark_price=mark_price))
    assert r1.unrealized_pnl == r2.unrealized_pnl
    assert r1.pnl_report_digest == r2.pnl_report_digest
    assert paper_pnl_report_digest(r1) == r1.pnl_report_digest


def test_high_scale_long_mtm_exponent_gap_exact() -> None:
    # avg = 1e-61 (one significant digit, 61-place exponent gap), mark = 1. unrealized = 1*(1 - 1e-61).
    # Coefficient-only precision (+40 guard) rounds the difference to 1; span-aware keeps it exact.
    avg = "0." + "0" * 60 + "1"
    report = _compute(_position(signed_units="1", abs_units="1", average_entry_price=avg), _mark(mark_price="1"))
    expected_notional, expected_unrealized = _mtm_oracle("LONG", "1", avg, "1")
    assert report.unrealized_pnl == expected_unrealized
    assert report.unrealized_pnl == "0." + "9" * 61  # 1 - 1e-61, exact
    assert report.unrealized_pnl != "1"
    assert report.mark_notional == expected_notional == "1"


def test_high_scale_short_mtm_exponent_gap_exact() -> None:
    # SHORT: unrealized = abs*(avg - mark); mark = 1e-61, avg = 1 ⇒ 1*(1 - 1e-61). mark_notional = 1e-61.
    mark_price = "0." + "0" * 60 + "1"
    position = _position(side=PaperPositionStateSide.SHORT, signed_units="-1", abs_units="1", average_entry_price="1")
    report = _compute(position, _mark(mark_price=mark_price))
    expected_notional, expected_unrealized = _mtm_oracle("SHORT", "1", "1", mark_price)
    assert report.unrealized_pnl == expected_unrealized
    assert report.unrealized_pnl == "0." + "9" * 61
    assert report.unrealized_pnl != "1"
    assert report.mark_notional == expected_notional == mark_price  # 1 * 1e-61, exact, no scientific
    assert "e" not in report.mark_notional.lower()


# --------------------------------------------------------------------------------------------------
# Digest boundary / fail-closed
# --------------------------------------------------------------------------------------------------


def test_position_digest_mismatch_raises() -> None:
    position = replace(_position(), position_state_digest="d" * 64)
    with pytest.raises(PaperPnlReportError, match="position_state_digest_mismatch"):
        _compute(position, _mark())


def test_mark_snapshot_digest_mismatch_raises() -> None:
    mark = replace(_mark(), mark_snapshot_digest="d" * 64)
    with pytest.raises(PaperPnlReportError, match="mark_snapshot_digest_mismatch"):
        _compute(_position(), mark)


def test_symbol_mismatch_raises() -> None:
    with pytest.raises(PaperPnlReportError, match="symbol_mismatch"):
        _compute(_position(market_symbol="BTC-PERPETUAL"), _mark(market_symbol="ETH-PERPETUAL"))


def test_forged_self_consistent_inconsistent_position_rejected() -> None:
    forged = replace(
        _position(side=PaperPositionStateSide.LONG, signed_units="10", abs_units="10"),
        side=PaperPositionStateSide.SHORT,
    )
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperPnlReportError, match="position_state_inconsistent"):
        _compute(forged, _mark())


def test_forged_self_consistent_noncanonical_position_rejected() -> None:
    forged = replace(_position(), signed_units="10.0", abs_units="10.0")
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperPnlReportError, match="position_state_malformed"):
        _compute(forged, _mark())


def test_forged_unsafe_position_rejected() -> None:
    forged = replace(_position(), capital_mutated=True)
    forged = replace(forged, position_state_digest=paper_position_state_digest(forged))
    with pytest.raises(PaperPnlReportError, match="position_state_unsafe_flags"):
        _compute(forged, _mark())


def test_forged_self_consistent_mark_snapshot_rejected() -> None:
    forged = replace(_mark(), mark_price="0")
    forged = replace(forged, mark_snapshot_digest=paper_mark_snapshot_digest(forged))
    with pytest.raises(PaperPnlReportError, match="mark_snapshot_malformed"):
        _compute(_position(), forged)


def test_forged_mark_snapshot_forbidden_token_rejected() -> None:
    forged = replace(_mark(), mark_source_id="connector-1")
    forged = replace(forged, mark_snapshot_digest=paper_mark_snapshot_digest(forged))
    with pytest.raises(PaperPnlReportError, match="mark_snapshot_scope_violation"):
        _compute(_position(), forged)


def test_wrong_typed_inputs_raise() -> None:
    with pytest.raises(PaperPnlReportError, match="position_state_malformed"):
        compute_paper_pnl_report({"x": 1}, _mark(), pnl_report_id="p", correlation_id="c")  # type: ignore[arg-type]
    with pytest.raises(PaperPnlReportError, match="mark_snapshot_malformed"):
        compute_paper_pnl_report(_position(), {"x": 1}, pnl_report_id="p", correlation_id="c")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "field,value",
    [
        ("mark_source_id", "deribit-mark"),
        ("correlation_id", "live_feed"),
        ("market_symbol", "order-PERP"),
        ("mark_snapshot_id", "route_id-1"),
    ],
)
def test_build_mark_snapshot_forbidden_token_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperPnlReportError, match="scope_violation"):
        _mark(**{field: value})


@pytest.mark.parametrize(
    "field,value",
    [("pnl_report_id", "place_order"), ("correlation_id", "scheduler-x")],
)
def test_compute_scope_violation_raises(field: str, value: str) -> None:
    with pytest.raises(PaperPnlReportError, match="scope_violation"):
        _compute(_position(), _mark(), **{field: value})


def test_mark_snapshot_metadata_malformed_raises() -> None:
    with pytest.raises(PaperPnlReportError, match="metadata_malformed"):
        _mark(metadata={"k": 5})  # type: ignore[dict-item]


def test_compute_metadata_malformed_raises() -> None:
    with pytest.raises(PaperPnlReportError, match="metadata_malformed"):
        _compute(_position(), _mark(), metadata={"k": 5})  # type: ignore[dict-item]


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_report_digest_deterministic() -> None:
    position, mark = _position(), _mark()
    r1 = _compute(position, mark)
    r2 = _compute(position, mark)
    assert r1 == r2
    assert r1.pnl_report_digest == r2.pnl_report_digest
    assert paper_pnl_report_digest(r1) == r1.pnl_report_digest


def test_report_immutable() -> None:
    report = _compute(_position(), _mark())
    with pytest.raises(FrozenInstanceError):
        report.unrealized_pnl = "1"  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        report.status = PaperPnlReportStatus.REJECTED  # type: ignore[misc]


def test_inputs_not_mutated() -> None:
    position, mark = _position(), _mark()
    position_before = paper_position_state_digest(position)
    mark_before = paper_mark_snapshot_digest(mark)
    _compute(position, mark)
    assert paper_position_state_digest(position) == position_before
    assert paper_mark_snapshot_digest(mark) == mark_before
    assert position.position_state_digest == position_before
    assert mark.mark_snapshot_digest == mark_before


def test_reason_codes_status_consistent() -> None:
    report = _compute(_position(), _mark())
    assert report.status is PaperPnlReportStatus.COMPUTED
    assert report.reason_codes == ()


def test_report_dict_keys_and_safe_flags() -> None:
    payload = paper_pnl_report_to_dict(_compute(_position(), _mark()))
    assert set(payload) == _EXPECTED_REPORT_KEYS
    assert payload["pnl_report_digest"] == _compute(_position(), _mark()).pnl_report_digest
    assert payload["paper_only"] is True
    assert payload["pnl_computed"] is True
    for flag in _SAFE_FALSE_REPORT_FLAGS:
        assert payload[flag] is False
    assert payload["position_side"] == "LONG"
    assert payload["status"] == "COMPUTED"


def test_report_dict_has_no_realized_or_total_pnl_value() -> None:
    payload = paper_pnl_report_to_dict(_compute(_position(), _mark()))
    assert payload["realized_pnl"] is None
    assert payload["total_pnl"] is None
    assert payload["realized_pnl_computed"] is False


def test_report_dict_has_no_capital_or_venue_value_fields() -> None:
    payload = paper_pnl_report_to_dict(_compute(_position(), _mark()))
    for token in _BARE_FORBIDDEN_KEYS:
        assert token not in payload


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_pnl_report.__file__).read_text(encoding="utf-8")
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
# End-to-end chain: intent -> fill -> position -> PnL report
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


def test_end_to_end_intent_fill_position_pnl_chain() -> None:
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
    fill_policy = build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    fill = simulate_paper_fill(
        intent, snapshot, fill_policy, fill_simulation_id="fillsim-1", correlation_id="corr-fill"
    )
    assert fill.status is PaperFillSimulationStatus.FILLED

    _, new_state = apply_paper_fill_to_position(
        build_flat_paper_position_state(
            position_state_id="pos-1", market_symbol="BTC-PERPETUAL", correlation_id="corr-pos"
        ),
        fill,
        transition_id="trans-1",
        new_position_state_id="pos-2",
        correlation_id="corr-apply",
    )
    assert new_state is not None
    assert new_state.side is PaperPositionStateSide.LONG
    assert new_state.average_entry_price == "50"

    mark = build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol="BTC-PERPETUAL", mark_price="60", correlation_id="corr-mark"
    )
    report = compute_paper_pnl_report(new_state, mark, pnl_report_id="pnl-1", correlation_id="corr-pnl")
    assert report.status is PaperPnlReportStatus.COMPUTED
    assert report.position_side is PaperPositionStateSide.LONG
    assert report.mark_notional == "600"  # 10 * 60
    assert report.unrealized_pnl == "100"  # 10 * (60 - 50)
    assert report.position_state_digest == new_state.position_state_digest
    assert report.mark_snapshot_digest == mark.mark_snapshot_digest
    assert report.realized_pnl is None
