"""Tests for the paper session realized-PnL bridge — deterministic, paper-only, gross-only, provenance-bound."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_session_realized_pnl_bridge
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
from crypto_core.validation.paper_realized_pnl_rollup import (
    PaperRealizedPnlRollupInput,
    build_paper_realized_pnl_rollup,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionRealizedPnlBridgeError,
    PaperSessionRealizedPnlBridgeStatus,
    build_paper_session_realized_pnl_bridge,
    paper_session_realized_pnl_bridge_digest,
    paper_session_realized_pnl_bridge_to_dict,
)
from crypto_core.validation.paper_session_sequence import (
    PaperSessionSequenceStatus,
    build_paper_session_sequence,
    paper_session_sequence_result_digest,
)

_HEX = "b" * 64

_EXPECTED_KEYS = {
    "schema_version",
    "bridge_id",
    "status",
    "market_symbol",
    "paper_session_id",
    "session_sequence_digest",
    "rollup_digest",
    "episode_count",
    "event_count",
    "computed_event_count",
    "no_realized_event_count",
    "closed_units_total",
    "realized_pnl_total",
    "source_event_digests",
    "reason_codes",
    "correlation_id",
    "metadata",
    "bridge_digest",
    "paper_only",
    "bridge_computed",
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

# Value-field names for forbidden concepts (exact keys; the negative-attestation booleans such as
# ``total_pnl_computed`` / ``equity_or_capital_computed`` / ``route_id_created`` are allowed).
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
# Session-sequence fixtures (mirrors test_paper_session_sequence.py)
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


def _session(episodes=None, *, market_symbol: str = "BTC-PERPETUAL", **overrides: object):
    base: dict[str, object] = {"paper_session_id": "sess-1", "correlation_id": "corr-sess"}
    base.update(overrides)
    eps = episodes if episodes is not None else [_episode("1", market_symbol=market_symbol)]
    return build_paper_session_sequence(eps, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Realized-PnL provenance-bundle fixtures (mirrors test_paper_realized_pnl_rollup.py)
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


def _short(*, avg: str = "100", market_symbol: str = "BTC-PERPETUAL"):
    return build_paper_position_state(
        position_state_id="rpos-1",
        market_symbol=market_symbol,
        side=PaperPositionStateSide.SHORT,
        signed_units="-10",
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
    correlation_id: str = "corr-revt",
) -> PaperRealizedPnlRollupInput:
    if prior_side == "LONG":
        prior = _long(avg=avg, market_symbol=market_symbol)
        fill = _fill("SELL", filled, price, market_symbol=market_symbol)
    elif prior_side == "SHORT":
        prior = _short(avg=avg, market_symbol=market_symbol)
        fill = _fill("BUY", filled, price, market_symbol=market_symbol)
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
        prior, fill, transition, new_state, realized_pnl_event_id=event_id, correlation_id=correlation_id
    )
    return PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )


def _no_realized(event_id: str, **kwargs: object) -> PaperRealizedPnlRollupInput:
    return _bundle(event_id, prior_side="FLAT", filled="10", price="100", **kwargs)  # type: ignore[arg-type]


def _forge_event(bundle: PaperRealizedPnlRollupInput, *, reseal: bool = True, **event_overrides: object):
    forged_event = replace(bundle.event, **event_overrides)
    if reseal:
        forged_event = replace(forged_event, realized_pnl_event_digest=paper_realized_pnl_event_digest(forged_event))
    return replace(bundle, event=forged_event)


def _bridge(session=None, entries=None, **overrides):
    base: dict[str, object] = {"bridge_id": "bridge-1", "correlation_id": "corr-bridge"}
    base.update(overrides)
    sess = session if session is not None else _session()
    ents = entries if entries is not None else [_bundle("e1")]
    return build_paper_session_realized_pnl_bridge(sess, ents, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Happy paths / binding
# --------------------------------------------------------------------------------------------------


def test_valid_single_event_bridge() -> None:
    session = _session()
    bundle = _bundle("e1")  # LONG avg 100, SELL 4 @ 150 -> +200, closed 4
    bridge = _bridge(session=session, entries=[bundle])
    assert bridge.status is PaperSessionRealizedPnlBridgeStatus.COMPUTED
    assert bridge.market_symbol == "BTC-PERPETUAL"
    assert bridge.paper_session_id == session.paper_session_id
    assert bridge.session_sequence_digest == session.paper_session_sequence_digest
    assert bridge.episode_count == session.episode_count
    assert bridge.event_count == 1
    assert bridge.computed_event_count == 1
    assert bridge.no_realized_event_count == 0
    assert bridge.realized_pnl_total == "200"
    assert bridge.closed_units_total == "4"
    assert bridge.source_event_digests == (bundle.event.realized_pnl_event_digest,)
    assert bridge.gross_only is True
    assert _is_hex64(bridge.bridge_digest)
    assert paper_session_realized_pnl_bridge_digest(bridge) == bridge.bridge_digest


def test_bridge_binds_rollup_digest() -> None:
    session = _session()
    bundle = _bundle("e1")
    bridge = _bridge(session=session, entries=[bundle])
    # rollup is built internally with rollup_id == bridge_id and the bridge's correlation_id.
    rollup = build_paper_realized_pnl_rollup([bundle], rollup_id="bridge-1", correlation_id="corr-bridge")
    assert bridge.rollup_digest == rollup.rollup_digest


def test_multiple_events_same_session() -> None:
    gain = _bundle("e1", price="150")  # +200
    loss = _bundle("e2", price="80")  # -80
    bridge = _bridge(entries=[gain, loss])
    assert bridge.event_count == 2
    assert bridge.computed_event_count == 2
    assert bridge.realized_pnl_total == "120"
    assert bridge.closed_units_total == "8"
    assert bridge.source_event_digests == (gain.event.realized_pnl_event_digest, loss.event.realized_pnl_event_digest)


def test_computed_plus_no_realized_counts_copied() -> None:
    bridge = _bridge(entries=[_bundle("e1"), _no_realized("e2")])
    assert bridge.event_count == 2
    assert bridge.computed_event_count == 1
    assert bridge.no_realized_event_count == 1
    assert bridge.realized_pnl_total == "200"
    assert bridge.closed_units_total == "4"


def test_high_scale_realized_total_preserved() -> None:
    avg = "0." + "0" * 99 + "1"
    e1 = _bundle("e1", avg=avg, price="1")
    e2 = _bundle("e2", avg=avg, price="1")
    bridge = _bridge(entries=[e1, e2])
    assert bridge.realized_pnl_total == "7." + "9" * 99 + "2"
    assert bridge.realized_pnl_total != "8"
    assert "e" not in bridge.realized_pnl_total.lower()


def test_cancellation_to_canonical_zero_preserved() -> None:
    bridge = _bridge(entries=[_bundle("e1", price="150"), _bundle("e2", price="50")])  # +200, -200
    assert bridge.realized_pnl_total == "0"
    assert bridge.closed_units_total == "8"


def test_bridge_binds_context_not_episode_membership() -> None:
    # SCOPE: the bridge binds session CONTEXT (digest) + market to a provenance-bound rollup; it does NOT
    # claim each rolled-up event was an episode of this session (a PaperSessionSequenceResult does not
    # expose per-episode fill/transition provenance). The realized bundles below are genuine and share the
    # session market but are not derived from the session episode — the bridge intentionally accepts this.
    session = _session()
    bridge = _bridge(session=session, entries=[_bundle("e1")])
    assert bridge.market_symbol == session.market_symbol
    assert bridge.session_sequence_digest == session.paper_session_sequence_digest


# --------------------------------------------------------------------------------------------------
# Determinism / digest binding
# --------------------------------------------------------------------------------------------------


def test_bridge_digest_deterministic() -> None:
    session = _session()
    entries = [_bundle("e1"), _bundle("e2", price="80")]
    b1 = build_paper_session_realized_pnl_bridge(session, entries, bridge_id="bridge-1", correlation_id="corr-bridge")
    b2 = build_paper_session_realized_pnl_bridge(session, entries, bridge_id="bridge-1", correlation_id="corr-bridge")
    assert b1.bridge_digest == b2.bridge_digest
    assert paper_session_realized_pnl_bridge_digest(b1) == b1.bridge_digest
    assert paper_session_realized_pnl_bridge_to_dict(b1)["bridge_digest"] == b1.bridge_digest


def test_rollup_order_changes_bridge_digest() -> None:
    session = _session()
    a, b = _bundle("e1"), _bundle("e2", price="80")
    forward = build_paper_session_realized_pnl_bridge(session, [a, b], bridge_id="bridge-1", correlation_id="c")
    reverse = build_paper_session_realized_pnl_bridge(session, [b, a], bridge_id="bridge-1", correlation_id="c")
    assert forward.source_event_digests != reverse.source_event_digests
    assert forward.bridge_digest != reverse.bridge_digest
    assert forward.realized_pnl_total == reverse.realized_pnl_total  # sum order-independent


def test_session_context_changes_bridge_digest() -> None:
    entries = [_bundle("e1")]
    s1 = _session(paper_session_id="sess-1")
    s2 = _session(paper_session_id="sess-2")
    assert s1.paper_session_sequence_digest != s2.paper_session_sequence_digest
    b1 = build_paper_session_realized_pnl_bridge(s1, entries, bridge_id="bridge-1", correlation_id="c")
    b2 = build_paper_session_realized_pnl_bridge(s2, entries, bridge_id="bridge-1", correlation_id="c")
    assert b1.bridge_digest != b2.bridge_digest


# --------------------------------------------------------------------------------------------------
# Fail-closed: session binding
# --------------------------------------------------------------------------------------------------


def test_wrong_typed_session_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_malformed"):
        _bridge(session={"not": "a-session"})


def test_session_digest_mismatch_rejected() -> None:
    forged = replace(_session(), paper_session_sequence_digest="d" * 64)
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_digest_mismatch"):
        _bridge(session=forged)


def test_forged_session_unsafe_flag_rejected() -> None:
    forged = replace(_session(), capital_mutated=True)
    forged = replace(forged, paper_session_sequence_digest=paper_session_sequence_result_digest(forged))
    assert paper_session_sequence_result_digest(forged) == forged.paper_session_sequence_digest  # self-consistent
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_unsafe_flags"):
        _bridge(session=forged)


def test_forged_session_status_rejected() -> None:
    forged = replace(_session(), status=PaperSessionSequenceStatus.REJECTED)
    forged = replace(forged, paper_session_sequence_digest=paper_session_sequence_result_digest(forged))
    assert paper_session_sequence_result_digest(forged) == forged.paper_session_sequence_digest
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_status_invalid"):
        _bridge(session=forged)


def test_forged_session_episode_count_rejected() -> None:
    # Codex P1: a self-consistent forged session (episode_count mutated to 0 on a one-episode session,
    # digest recomputed) must fail closed — its episode_count no longer matches episode_run_digests.
    forged = replace(_session(), episode_count=0)
    forged = replace(forged, paper_session_sequence_digest=paper_session_sequence_result_digest(forged))
    assert paper_session_sequence_result_digest(forged) == forged.paper_session_sequence_digest  # self-consistent
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_inconsistent"):
        _bridge(session=forged)


def test_forged_session_count_sum_rejected() -> None:
    forged = replace(_session(), computed_episode_count=5)  # 5 + 0 + 0 != episode_count 1
    forged = replace(forged, paper_session_sequence_digest=paper_session_sequence_result_digest(forged))
    assert paper_session_sequence_result_digest(forged) == forged.paper_session_sequence_digest
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_inconsistent"):
        _bridge(session=forged)


def test_forged_session_first_digest_rejected() -> None:
    forged = replace(_session(), first_episode_run_digest="d" * 64)  # no longer matches episode_run_digests[0]
    forged = replace(forged, paper_session_sequence_digest=paper_session_sequence_result_digest(forged))
    assert paper_session_sequence_result_digest(forged) == forged.paper_session_sequence_digest
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="session_inconsistent"):
        _bridge(session=forged)


def test_market_symbol_mismatch_rejected() -> None:
    session = _session(market_symbol="BTC-PERPETUAL")
    eth = _bundle("e1", market_symbol="ETH-PERPETUAL")
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="market_symbol_mismatch"):
        _bridge(session=session, entries=[eth])


# --------------------------------------------------------------------------------------------------
# Fail-closed: rollup provenance propagation
# --------------------------------------------------------------------------------------------------


def test_event_only_input_rejected() -> None:
    # rollup_entries must be provenance bundles, not naked events.
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[_bundle("e1").event])


def test_naked_rollup_object_rejected() -> None:
    # A prebuilt rollup object is not a sequence of provenance bundles.
    rollup = build_paper_realized_pnl_rollup([_bundle("e1")], rollup_id="r", correlation_id="c")
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=rollup)


def test_empty_entries_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[])


def test_coordinated_resealed_event_rejected_through_bridge() -> None:
    # The #284 coordinated-reseal exploit must still fail closed via the bridge's rollup build.
    forged = _forge_event(
        _bundle("e1"),
        prior_signed_units="2",
        closed_units="2",
        residual_open_units="2",
        realized_pnl="100",
    )
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[forged])


def test_forged_realized_amount_rejected_through_bridge() -> None:
    forged = _forge_event(_bundle("e1"), realized_pnl="999")
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[forged])


def test_wrong_upstream_artifact_rejected_through_bridge() -> None:
    bundle = _bundle("e1", avg="100")
    other = _bundle("e2", avg="120")
    swapped = replace(bundle, prior_state=other.prior_state)
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[swapped])


def test_duplicate_event_rejected_through_bridge() -> None:
    bundle = _bundle("e1")
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="rollup_invalid"):
        _bridge(entries=[bundle, bundle])


# --------------------------------------------------------------------------------------------------
# Fail-closed: bridge-level guards
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [("bridge_id", "live_order"), ("bridge_id", "bist"), ("correlation_id", "scheduler")],
)
def test_forbidden_token_in_ids_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="scope_violation"):
        _bridge(**{field: value})


def test_forbidden_token_in_metadata_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="scope_violation"):
        _bridge(metadata={"note": "place_order"})


def test_malformed_metadata_rejected() -> None:
    with pytest.raises(PaperSessionRealizedPnlBridgeError, match="metadata_malformed"):
        _bridge(metadata={"k": 5})  # type: ignore[dict-item]


def test_safe_market_data_terms_allowed() -> None:
    bridge = _bridge(metadata={"src": "order_book"})
    assert bridge.metadata == (("src", "order_book"),)


# --------------------------------------------------------------------------------------------------
# Immutability / no-leak / no-mutation
# --------------------------------------------------------------------------------------------------


def test_inputs_not_mutated() -> None:
    session = _session()
    entries = [_bundle("e1"), _bundle("e2", price="80")]
    session_before = session.paper_session_sequence_digest
    events_before = [e.event.realized_pnl_event_digest for e in entries]
    build_paper_session_realized_pnl_bridge(session, entries, bridge_id="bridge-1", correlation_id="c")
    assert session.paper_session_sequence_digest == session_before
    assert paper_session_sequence_result_digest(session) == session_before
    assert [e.event.realized_pnl_event_digest for e in entries] == events_before


def test_output_immutable() -> None:
    bridge = _bridge()
    with pytest.raises(FrozenInstanceError):
        bridge.realized_pnl_total = "1"  # type: ignore[misc]


def test_dict_keys_and_safe_flags_no_forbidden_value_fields() -> None:
    payload = paper_session_realized_pnl_bridge_to_dict(_bridge())
    assert set(payload) == _EXPECTED_KEYS
    assert payload["paper_only"] is True
    assert payload["bridge_computed"] is True
    assert payload["gross_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert _FORBIDDEN_VALUE_KEYS.isdisjoint(payload.keys())


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_session_realized_pnl_bridge.__file__).read_text(encoding="utf-8")
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
