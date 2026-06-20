"""Tests for the paper session realized-PnL aggregate — deterministic, paper-only, gross-only, provenance-bound."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_session_realized_pnl_aggregate
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
)
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import (
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.paper_realized_pnl_rollup import PaperRealizedPnlRollupInput
from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregateError,
    PaperSessionRealizedPnlAggregateInput,
    PaperSessionRealizedPnlAggregateStatus,
    build_paper_session_realized_pnl_aggregate,
    paper_session_realized_pnl_aggregate_digest,
    paper_session_realized_pnl_aggregate_to_dict,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
    paper_session_realized_pnl_bridge_digest,
)
from crypto_core.validation.paper_session_sequence import (
    build_paper_session_sequence,
    paper_session_sequence_result_digest,
)

_HEX = "b" * 64

_EXPECTED_KEYS = {
    "schema_version",
    "aggregate_id",
    "status",
    "market_symbol",
    "session_bridge_count",
    "session_sequence_digests",
    "bridge_digests",
    "rollup_digests",
    "source_event_digests",
    "episode_count_total",
    "event_count",
    "computed_event_count",
    "no_realized_event_count",
    "closed_units_total",
    "realized_pnl_total",
    "reason_codes",
    "correlation_id",
    "metadata",
    "aggregate_digest",
    "paper_only",
    "aggregate_computed",
    "gross_only",
    "fees_included",
    "unrealized_pnl_included",
    "total_pnl_computed",
    "equity_or_capital_computed",
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
}

_FORBIDDEN_VALUE_KEYS = {
    "unrealized_pnl",
    "unrealized_pnl_total",
    "total_pnl",
    "equity",
    "equity_total",
    "capital",
    "capital_total",
    "capital_balance",
    "margin",
    "balance",
    "fee_amount",
    "fees",
    "order_id",
    "venue_order_id",
    "exchange_order_id",
    "client_order_id",
    "route_id",
    "execution_instruction",
}

_SAFE_FALSE_FLAGS = (
    "fees_included",
    "unrealized_pnl_included",
    "total_pnl_computed",
    "equity_or_capital_computed",
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


# --------------------------------------------------------------------------------------------------
# Session-sequence fixtures (mirrors test_paper_session_sequence.py / bridge test)
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


def _intent(*, market_symbol: str = "BTC-PERPETUAL"):
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
        request_id="req-1",
        capacity_decision_digest=capacity.decision_digest,
        market_symbol=market_symbol,
        side=PaperOrderSide.BUY,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=capacity.requested_notional,
        requested_units=capacity.requested_units,
        limit_price=None,
        correlation_id="corr-req",
    )
    admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
    return build_paper_order_intent(admission, intent_id="intent-1", correlation_id="corr-intent")


def _episode(suffix: str, *, market_symbol: str = "BTC-PERPETUAL"):
    intent = _intent(market_symbol=market_symbol)
    prior = build_flat_paper_position_state(
        position_state_id=f"pos-{suffix}", market_symbol=market_symbol, correlation_id="corr-pos"
    )
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"snap-{suffix}", market_symbol=market_symbol, reference_price="50"
    )
    policy = build_paper_fill_policy(
        policy_id=f"fill-policy-{suffix}", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"mark-{suffix}", market_symbol=market_symbol, mark_price="60", correlation_id="corr-mark"
    )
    return run_paper_episode(
        intent,
        prior,
        snapshot,
        policy,
        mark,
        fill_simulation_id=f"fillsim-{suffix}",
        position_transition_id=f"trans-{suffix}",
        new_position_state_id=f"newpos-{suffix}",
        pnl_report_id=f"pnl-{suffix}",
        episode_run_id=f"ep-{suffix}",
        correlation_id="corr-ep",
    )


def _episode_list(suffixes=("1",), *, market_symbol: str = "BTC-PERPETUAL"):
    return [_episode(s, market_symbol=market_symbol) for s in suffixes]


def _session_result(episodes, *, paper_session_id: str, correlation_id: str):
    return build_paper_session_sequence(episodes, paper_session_id=paper_session_id, correlation_id=correlation_id)


def _prov_for(idx: str, *, market_symbol: str = "BTC-PERPETUAL") -> PaperSessionSequenceProvenance:
    eps = _episode_list((idx,), market_symbol=market_symbol)
    session = _session_result(eps, paper_session_id=f"sess-{idx}", correlation_id=f"corr-sess-{idx}")
    return PaperSessionSequenceProvenance(session_sequence=session, episodes=tuple(eps))


# --------------------------------------------------------------------------------------------------
# Realized-PnL provenance-bundle fixtures
# --------------------------------------------------------------------------------------------------


def _exact_gross(filled_units: str, fill_price: str) -> str:
    with localcontext() as ctx:
        ctx.prec = 400
        product = Decimal(filled_units) * Decimal(fill_price)
    rendered = format(product, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _long(*, avg: str = "100", market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_position_state(
        position_state_id="rpos-1",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price=avg,
        transition_count=0,
        correlation_id="corr-rpos",
    )


def _rflat(*, market_symbol: str = "BTC-PERPETUAL"):
    return build_flat_paper_position_state(
        position_state_id="rpos-1", market_symbol=market_symbol, correlation_id="corr-rpos"
    )


def _fill(side: str, filled: str, price: str, *, market_symbol: str = "BTC-PERPETUAL") -> PaperFillSimulationResult:
    base = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=PaperFillSimulationStatus.FILLED,
        fill_simulation_id="rfillsim-1",
        intent_digest=_HEX,
        market_snapshot_digest=_HEX,
        fill_policy_digest=_HEX,
        market_symbol=market_symbol,
        side=side,
        intent_type="MARKET",
        fill_price=price,
        filled_units=filled,
        unfilled_units="0",
        gross_notional=_exact_gross(filled, price),
        fee_amount="0",
        reason_codes=(),
        correlation_id="corr-rfill",
        metadata=(),
        result_digest="",
    )
    return replace(base, result_digest=paper_fill_simulation_result_digest(base))


def _bundle(
    event_id: str,
    *,
    prior_side: str = "LONG",
    avg: str = "100",
    price: str = "150",
    filled: str = "4",
    market_symbol: str = "BTC-PERPETUAL",
) -> PaperRealizedPnlRollupInput:
    if prior_side == "LONG":
        prior = _long(avg=avg, market_symbol=market_symbol)
        fill = _fill("SELL", filled, price, market_symbol=market_symbol)
    else:  # FLAT — open from flat (NO_REALIZED_PNL)
        prior = _rflat(market_symbol=market_symbol)
        fill = _fill("BUY", filled, price, market_symbol=market_symbol)
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=f"rtrans-{event_id}",
        new_position_state_id=f"rnewpos-{event_id}",
        correlation_id="corr-rapply",
    )
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id=event_id, correlation_id="corr-revt"
    )
    return PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )


def _no_realized(event_id: str, **kwargs: object) -> PaperRealizedPnlRollupInput:
    return _bundle(event_id, prior_side="FLAT", filled="10", price="100", **kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Aggregate-entry fixtures
# --------------------------------------------------------------------------------------------------


def _entry_from(prov, *, bridge_id: str, bundles, bridge_correlation: str = "corr-bridge"):
    ents = tuple(bundles)
    bridge = build_paper_session_realized_pnl_bridge(prov, ents, bridge_id=bridge_id, correlation_id=bridge_correlation)
    return PaperSessionRealizedPnlAggregateInput(bridge=bridge, session_input=prov, rollup_entries=ents)


def _entry(idx: str = "1", *, bridge_id: str | None = None, bundles=None, market_symbol: str = "BTC-PERPETUAL"):
    prov = _prov_for(idx, market_symbol=market_symbol)
    ents = tuple(bundles) if bundles is not None else (_bundle(f"e{idx}", market_symbol=market_symbol),)
    return _entry_from(prov, bridge_id=bridge_id or f"bridge-{idx}", bundles=ents)


def _forge_bridge(entry, *, reseal: bool = True, **bridge_overrides):
    """A bridge forged in place (optionally re-sealed self-consistent) while session/rollup inputs stay genuine."""
    forged = replace(entry.bridge, **bridge_overrides)
    if reseal:
        forged = replace(forged, bridge_digest=paper_session_realized_pnl_bridge_digest(forged))
    return replace(entry, bridge=forged)


def _aggregate(entries=None, **overrides):
    base: dict[str, object] = {"aggregate_id": "agg-1", "correlation_id": "corr-agg"}
    base.update(overrides)
    ents = entries if entries is not None else [_entry("1")]
    return build_paper_session_realized_pnl_aggregate(ents, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy paths / aggregation
# --------------------------------------------------------------------------------------------------


def test_valid_single_bridge_aggregate() -> None:
    entry = _entry("1")
    agg = _aggregate([entry])
    assert agg.status is PaperSessionRealizedPnlAggregateStatus.COMPUTED
    assert agg.market_symbol == "BTC-PERPETUAL"
    assert agg.session_bridge_count == 1
    assert agg.episode_count_total == 1
    assert agg.event_count == 1
    assert agg.computed_event_count == 1
    assert agg.no_realized_event_count == 0
    assert agg.realized_pnl_total == "200"
    assert agg.closed_units_total == "4"
    assert agg.bridge_digests == (entry.bridge.bridge_digest,)
    assert agg.session_sequence_digests == (entry.bridge.session_sequence_digest,)
    assert agg.rollup_digests == (entry.bridge.rollup_digest,)
    assert agg.source_event_digests == entry.bridge.source_event_digests
    assert agg.reason_codes == ()
    assert agg.gross_only is True
    assert _is_hex64(agg.aggregate_digest)
    assert paper_session_realized_pnl_aggregate_digest(agg) == agg.aggregate_digest


def test_valid_two_bridge_aggregate() -> None:
    e1, e2 = _entry("1"), _entry("2")
    agg = _aggregate([e1, e2])
    assert agg.session_bridge_count == 2
    assert agg.episode_count_total == 2
    assert agg.event_count == 2
    assert agg.computed_event_count == 2
    assert agg.realized_pnl_total == "400"  # 200 + 200
    assert agg.closed_units_total == "8"
    assert agg.bridge_digests == (e1.bridge.bridge_digest, e2.bridge.bridge_digest)
    assert agg.source_event_digests == (*e1.bridge.source_event_digests, *e2.bridge.source_event_digests)


def test_computed_plus_no_realized_counts_aggregate() -> None:
    e1 = _entry("1")  # one computed event (+200, closed 4)
    e2 = _entry("2", bundles=(_no_realized("n2"),))  # one no-realized event
    agg = _aggregate([e1, e2])
    assert agg.event_count == 2
    assert agg.computed_event_count == 1
    assert agg.no_realized_event_count == 1
    assert agg.realized_pnl_total == "200"
    assert agg.closed_units_total == "4"


def test_high_scale_realized_total_preserved() -> None:
    avg = "0." + "0" * 99 + "1"
    e1 = _entry("1", bundles=(_bundle("h1", avg=avg, price="1"),))  # realized 3.<99 9s>6
    e2 = _entry("2", bundles=(_bundle("h2", avg=avg, price="1"),))
    agg = _aggregate([e1, e2])
    assert agg.realized_pnl_total == "7." + "9" * 99 + "2"
    assert agg.realized_pnl_total != "8"
    assert "e" not in agg.realized_pnl_total.lower()
    assert agg.closed_units_total == "8"


def test_cancellation_to_canonical_zero() -> None:
    e1 = _entry("1", bundles=(_bundle("g1", price="150"),))  # +200
    e2 = _entry("2", bundles=(_bundle("l1", price="50"),))  # -200
    agg = _aggregate([e1, e2])
    assert agg.realized_pnl_total == "0"
    assert agg.closed_units_total == "8"


def test_aggregate_binds_context_not_episode_membership() -> None:
    # SCOPE: each bridge is provenance-reconstructed (session context + realized rollup), but the aggregate
    # does NOT prove that a rolled-up realized event belongs to a specific episode of its session (no shared
    # identifier exists to cross-check). The realized bundles share the market but are not derived from the
    # session episodes — accepted by design.
    entry = _entry("1")
    agg = _aggregate([entry])
    assert agg.market_symbol == entry.bridge.market_symbol
    assert agg.bridge_digests == (entry.bridge.bridge_digest,)


# --------------------------------------------------------------------------------------------------
# Determinism / digest binding
# --------------------------------------------------------------------------------------------------


def test_aggregate_digest_deterministic() -> None:
    entries = [_entry("1"), _entry("2")]
    a1 = build_paper_session_realized_pnl_aggregate(entries, aggregate_id="agg-1", correlation_id="corr-agg")
    a2 = build_paper_session_realized_pnl_aggregate(entries, aggregate_id="agg-1", correlation_id="corr-agg")
    assert a1.aggregate_digest == a2.aggregate_digest
    assert paper_session_realized_pnl_aggregate_digest(a1) == a1.aggregate_digest
    assert paper_session_realized_pnl_aggregate_to_dict(a1)["aggregate_digest"] == a1.aggregate_digest


def test_bridge_order_changes_aggregate_digest() -> None:
    a, b = _entry("1"), _entry("2")
    forward = build_paper_session_realized_pnl_aggregate([a, b], aggregate_id="agg-1", correlation_id="c")
    reverse = build_paper_session_realized_pnl_aggregate([b, a], aggregate_id="agg-1", correlation_id="c")
    assert forward.bridge_digests != reverse.bridge_digests
    assert forward.aggregate_digest != reverse.aggregate_digest
    assert forward.realized_pnl_total == reverse.realized_pnl_total  # sum order-independent


def test_session_context_changes_aggregate_digest() -> None:
    # Same bridge_id + same rollup events, but different session context -> different bridge -> different agg.
    prov1 = _prov_for("1")
    prov2 = _prov_for("2")
    e1 = _entry_from(prov1, bridge_id="bridge-x", bundles=(_bundle("e1"),))
    e2 = _entry_from(prov2, bridge_id="bridge-x", bundles=(_bundle("e1"),))
    a1 = build_paper_session_realized_pnl_aggregate([e1], aggregate_id="agg-1", correlation_id="c")
    a2 = build_paper_session_realized_pnl_aggregate([e2], aggregate_id="agg-1", correlation_id="c")
    assert a1.aggregate_digest != a2.aggregate_digest


def test_event_order_changes_aggregate_digest() -> None:
    prov = _prov_for("1")
    forward = _entry_from(prov, bridge_id="bridge-1", bundles=(_bundle("e1"), _bundle("e2", price="80")))
    reverse = _entry_from(prov, bridge_id="bridge-1", bundles=(_bundle("e2", price="80"), _bundle("e1")))
    a1 = build_paper_session_realized_pnl_aggregate([forward], aggregate_id="agg-1", correlation_id="c")
    a2 = build_paper_session_realized_pnl_aggregate([reverse], aggregate_id="agg-1", correlation_id="c")
    assert a1.source_event_digests != a2.source_event_digests
    assert a1.aggregate_digest != a2.aggregate_digest


# --------------------------------------------------------------------------------------------------
# Fail-closed: input shape
# --------------------------------------------------------------------------------------------------


def test_naked_bridge_input_rejected() -> None:
    # The public builder requires aggregate entries (bundles), not naked bridge artifacts.
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="entry_malformed"):
        _aggregate([_entry("1").bridge])


def test_wrong_typed_entry_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="entry_malformed"):
        _aggregate([{"not": "an-entry"}])


def test_empty_entries_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="entries_empty"):
        _aggregate([])


@pytest.mark.parametrize("bad", ["x", b"x", 5, {"e": 1}])
def test_non_sequence_entries_rejected(bad: object) -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="entries_malformed"):
        _aggregate(bad)  # type: ignore[arg-type]


def test_bridge_count_exceeds_max_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper_session_realized_pnl_aggregate, "_MAX_BRIDGE_COUNT", 1)
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_count_exceeds_max"):
        _aggregate([_entry("1"), _entry("2")])


def test_duplicate_bridge_digest_rejected() -> None:
    entry = _entry("1")
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="duplicate_bridge_digest"):
        _aggregate([entry, entry])


def test_duplicate_bridge_id_rejected() -> None:
    e1 = _entry("1", bridge_id="bridge-dup")
    e2 = _entry("2", bridge_id="bridge-dup")  # distinct session/digest, same bridge id
    assert e1.bridge.bridge_digest != e2.bridge.bridge_digest
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="duplicate_bridge_id"):
        _aggregate([e1, e2])


def test_duplicate_session_sequence_digest_rejected() -> None:
    prov = _prov_for("1")
    e1 = _entry_from(prov, bridge_id="bridge-1", bundles=(_bundle("ea"),))
    e2 = _entry_from(prov, bridge_id="bridge-2", bundles=(_bundle("eb"),))  # same session, different bridge
    assert e1.bridge.session_sequence_digest == e2.bridge.session_sequence_digest
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="duplicate_session_sequence_digest"):
        _aggregate([e1, e2])


def test_duplicate_source_event_across_bridges_rejected() -> None:
    # Codex P1: two distinct bridges (distinct bridge_id + session_sequence_digest) built from the SAME
    # realized event would double-count its realized PnL / closed units. The shared source event digest
    # must fail closed even though the bridge/session duplicate checks pass.
    shared = _bundle("shared-evt")
    e1 = _entry_from(_prov_for("1"), bridge_id="bridge-1", bundles=(shared,))
    e2 = _entry_from(_prov_for("2"), bridge_id="bridge-2", bundles=(shared,))
    assert e1.bridge.bridge_digest != e2.bridge.bridge_digest
    assert e1.bridge.session_sequence_digest != e2.bridge.session_sequence_digest
    assert e1.bridge.source_event_digests == e2.bridge.source_event_digests  # same realized event
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="duplicate_source_event_digest"):
        _aggregate([e1, e2])


def test_market_symbol_mismatch_rejected() -> None:
    btc = _entry("1", market_symbol="BTC-PERPETUAL")
    eth = _entry("2", market_symbol="ETH-PERPETUAL")
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="market_symbol_mismatch"):
        _aggregate([btc, eth])


# --------------------------------------------------------------------------------------------------
# Fail-closed: provenance
# --------------------------------------------------------------------------------------------------


def test_bridge_digest_mismatch_rejected() -> None:
    forged = _forge_bridge(_entry("1"), reseal=False, bridge_digest="d" * 64)
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_digest_mismatch"):
        _aggregate([forged])


def test_coordinated_resealed_bridge_rejected() -> None:
    # Bridge totals mutated and the bridge digest recomputed (self-consistent), but session/rollup inputs
    # are the genuine originals; reconstruction yields the canonical bridge (realized 200) -> mismatch.
    forged = _forge_bridge(_entry("1"), realized_pnl_total="999", closed_units_total="999")
    assert paper_session_realized_pnl_bridge_digest(forged.bridge) == forged.bridge.bridge_digest  # self-consistent
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_inconsistent"):
        _aggregate([forged])


def test_wrong_session_provenance_rejected() -> None:
    entry = _entry("1")
    other = _prov_for("2")
    swapped = replace(entry, session_input=other)  # reconstruction binds a different session digest
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_inconsistent"):
        _aggregate([swapped])


def test_wrong_rollup_provenance_rejected() -> None:
    entry = _entry("1")
    swapped = replace(entry, rollup_entries=(_bundle("z9", price="80"),))  # reconstruction binds a different rollup
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_inconsistent"):
        _aggregate([swapped])


def test_coordinated_resealed_session_rejected_through_aggregate() -> None:
    entry = _entry("1")
    prov = entry.session_input
    genuine = prov.session_sequence
    fake = "c" * 64
    forged_session = replace(
        genuine,
        episode_count=2,
        episode_run_digests=(genuine.episode_run_digests[0], fake),
        last_episode_run_digest=fake,
        computed_episode_count=2,
    )
    forged_session = replace(
        forged_session, paper_session_sequence_digest=paper_session_sequence_result_digest(forged_session)
    )
    bad = replace(entry, session_input=replace(prov, session_sequence=forged_session))
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_not_reproducible"):
        _aggregate([bad])


def test_coordinated_resealed_event_rejected_through_aggregate() -> None:
    entry = _entry("1")
    bundle = entry.rollup_entries[0]
    forged_event = replace(bundle.event, realized_pnl="999")
    forged_event = replace(forged_event, realized_pnl_event_digest=paper_realized_pnl_event_digest(forged_event))
    forged_bundle = replace(bundle, event=forged_event)
    bad = replace(entry, rollup_entries=(forged_bundle,))
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_not_reproducible"):
        _aggregate([bad])


def test_wrong_typed_session_member_rejected_through_aggregate() -> None:
    entry = _entry("1")
    bad = replace(entry, session_input={"not": "a-session"})  # type: ignore[arg-type]
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_not_reproducible"):
        _aggregate([bad])


def test_wrong_typed_rollup_entry_rejected_through_aggregate() -> None:
    entry = _entry("1")
    bad = replace(entry, rollup_entries=({"not": "a-bundle"},))  # type: ignore[arg-type]
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="bridge_not_reproducible"):
        _aggregate([bad])


# --------------------------------------------------------------------------------------------------
# Fail-closed: aggregate-level guards
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [("aggregate_id", "live_order"), ("aggregate_id", "bist"), ("correlation_id", "scheduler")],
)
def test_forbidden_token_in_ids_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="scope_violation"):
        _aggregate([_entry("1")], **{field: value})


def test_forbidden_token_in_metadata_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="scope_violation"):
        _aggregate([_entry("1")], metadata={"note": "place_order"})


def test_malformed_metadata_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlAggregateError, match="metadata_malformed"):
        _aggregate([_entry("1")], metadata={"k": 5})  # type: ignore[dict-item]


def test_safe_market_data_terms_allowed() -> None:
    agg = _aggregate([_entry("1")], metadata={"src": "order_book"})
    assert agg.metadata == (("src", "order_book"),)


# --------------------------------------------------------------------------------------------------
# Immutability / no-leak / no-mutation
# --------------------------------------------------------------------------------------------------


def test_inputs_not_mutated() -> None:
    entries = [_entry("1"), _entry("2")]
    bridges_before = [e.bridge.bridge_digest for e in entries]
    sessions_before = [e.session_input.session_sequence.paper_session_sequence_digest for e in entries]
    episodes_before = [tuple(ep.episode_run_digest for ep in e.session_input.episodes) for e in entries]
    events_before = [tuple(b.event.realized_pnl_event_digest for b in e.rollup_entries) for e in entries]
    build_paper_session_realized_pnl_aggregate(entries, aggregate_id="agg-1", correlation_id="c")
    assert [e.bridge.bridge_digest for e in entries] == bridges_before
    assert [e.session_input.session_sequence.paper_session_sequence_digest for e in entries] == sessions_before
    assert [tuple(ep.episode_run_digest for ep in e.session_input.episodes) for e in entries] == episodes_before
    assert [tuple(b.event.realized_pnl_event_digest for b in e.rollup_entries) for e in entries] == events_before


def test_output_immutable() -> None:
    agg = _aggregate()
    with pytest.raises(FrozenInstanceError):
        agg.realized_pnl_total = "1"  # type: ignore[misc]


def test_dict_keys_and_safe_flags_no_forbidden_value_fields() -> None:
    payload = paper_session_realized_pnl_aggregate_to_dict(_aggregate())
    assert set(payload) == _EXPECTED_KEYS
    assert payload["paper_only"] is True
    assert payload["aggregate_computed"] is True
    assert payload["gross_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert _FORBIDDEN_VALUE_KEYS.isdisjoint(payload.keys())


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_session_realized_pnl_aggregate.__file__).read_text(encoding="utf-8")
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
