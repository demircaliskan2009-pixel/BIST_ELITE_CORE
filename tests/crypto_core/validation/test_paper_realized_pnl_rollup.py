"""Tests for the paper realized-PnL rollup — deterministic, paper-only, gross-only, provenance-bound."""

from __future__ import annotations

import ast
from dataclasses import FrozenInstanceError, replace
from decimal import Decimal, localcontext
from pathlib import Path

import pytest

from crypto_core.validation import paper_realized_pnl_rollup
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlStatus,
    compute_paper_realized_pnl_event,
    paper_realized_pnl_event_digest,
)
from crypto_core.validation.paper_realized_pnl_rollup import (
    PaperRealizedPnlRollupError,
    PaperRealizedPnlRollupInput,
    PaperRealizedPnlRollupStatus,
    build_paper_realized_pnl_rollup,
    paper_realized_pnl_rollup_digest,
    paper_realized_pnl_rollup_to_dict,
)

_HEX = "b" * 64

_EXPECTED_KEYS = {
    "schema_version",
    "rollup_id",
    "status",
    "market_symbol",
    "event_count",
    "computed_event_count",
    "no_realized_event_count",
    "rejected_event_count",
    "closed_units_total",
    "realized_pnl_total",
    "source_event_digests",
    "reason_codes",
    "correlation_id",
    "metadata",
    "rollup_digest",
    "paper_only",
    "rollup_computed",
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
# ``total_pnl_computed`` / ``equity_or_capital_computed`` are allowed and asserted separately).
_FORBIDDEN_VALUE_KEYS = {
    "unrealized_pnl",
    "unrealized_pnl_total",
    "total_pnl",
    "total_pnl_value",
    "equity",
    "equity_total",
    "capital",
    "capital_total",
    "capital_balance",
    "margin",
    "balance",
    "fee_amount",
    "fee_amount_applied",
    "fees",
    "fee_total",
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


def _exact_gross(filled_units: str, fill_price: str) -> str:
    with localcontext() as ctx:
        ctx.prec = 400
        product = Decimal(filled_units) * Decimal(fill_price)
    rendered = format(product, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


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


def _fill(side: str, filled: str, price: str, *, market_symbol: str = "BTC-PERPETUAL") -> PaperFillSimulationResult:
    base = PaperFillSimulationResult(
        schema_version="paper-fill-simulation-result.v1",
        status=PaperFillSimulationStatus.FILLED,
        fill_simulation_id="fillsim-1",
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
        correlation_id="corr-fill",
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
    correlation_id: str = "corr-evt",
) -> PaperRealizedPnlRollupInput:
    """A genuine provenance bundle (event + the exact upstream artifacts) via the real per-fill flow."""
    if prior_side == "LONG":
        prior = _long(avg=avg, market_symbol=market_symbol)
        fill = _fill("SELL", filled, price, market_symbol=market_symbol)
    elif prior_side == "SHORT":
        prior = _short(avg=avg, market_symbol=market_symbol)
        fill = _fill("BUY", filled, price, market_symbol=market_symbol)
    else:  # FLAT — open from flat (NO_REALIZED_PNL)
        prior = _flat(market_symbol=market_symbol)
        fill = _fill("BUY", filled, price, market_symbol=market_symbol)
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=f"trans-{event_id}",
        new_position_state_id=f"newpos-{event_id}",
        correlation_id="corr-apply",
    )
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id=event_id, correlation_id=correlation_id
    )
    return PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )


def _computed(event_id: str, **kwargs: object) -> PaperRealizedPnlRollupInput:
    """A genuine COMPUTED bundle (LONG reduce by default)."""
    return _bundle(event_id, **kwargs)  # type: ignore[arg-type]


def _no_realized(event_id: str, **kwargs: object) -> PaperRealizedPnlRollupInput:
    """A genuine NO_REALIZED_PNL bundle (open from flat — nothing closed)."""
    return _bundle(event_id, prior_side="FLAT", filled="10", price="100", **kwargs)  # type: ignore[arg-type]


def _forge_event(bundle: PaperRealizedPnlRollupInput, *, reseal: bool = True, **event_overrides: object):
    """Return a bundle whose EVENT is forged (optionally re-sealed self-consistent) while the upstream
    artifacts stay the genuine originals — the coordinated-reseal threat model."""
    forged_event = replace(bundle.event, **event_overrides)
    if reseal:
        forged_event = replace(forged_event, realized_pnl_event_digest=paper_realized_pnl_event_digest(forged_event))
    return replace(bundle, event=forged_event)


def _rollup(entries, **overrides):
    base: dict[str, object] = {"rollup_id": "rollup-1", "correlation_id": "corr-rollup"}
    base.update(overrides)
    return build_paper_realized_pnl_rollup(entries, **base)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------------------
# Sanity on the genuine bundles the rollup consumes
# --------------------------------------------------------------------------------------------------


def test_fixture_bundle_is_computed_with_expected_realized() -> None:
    event = _computed("e1").event  # LONG avg 100, SELL 4 @ 150 -> +200, closed 4
    assert event.status is PaperRealizedPnlStatus.COMPUTED
    assert event.realized_pnl == "200"
    assert event.closed_units == "4"
    assert paper_realized_pnl_event_digest(event) == event.realized_pnl_event_digest


def test_genuine_bundle_accepted() -> None:
    bundle = _computed("e1")
    rollup = _rollup([bundle])
    assert rollup.status is PaperRealizedPnlRollupStatus.COMPUTED
    assert rollup.realized_pnl_total == "200"
    assert rollup.closed_units_total == "4"
    assert rollup.source_event_digests == (bundle.event.realized_pnl_event_digest,)


# --------------------------------------------------------------------------------------------------
# Aggregation
# --------------------------------------------------------------------------------------------------


def test_single_computed_event_rollup() -> None:
    bundle = _computed("e1")
    rollup = _rollup([bundle])
    assert rollup.status is PaperRealizedPnlRollupStatus.COMPUTED
    assert rollup.market_symbol == "BTC-PERPETUAL"
    assert rollup.event_count == 1
    assert rollup.computed_event_count == 1
    assert rollup.no_realized_event_count == 0
    assert rollup.rejected_event_count == 0
    assert rollup.realized_pnl_total == "200"
    assert rollup.closed_units_total == "4"
    assert rollup.source_event_digests == (bundle.event.realized_pnl_event_digest,)
    assert rollup.reason_codes == ()
    assert rollup.gross_only is True
    assert _is_hex64(rollup.rollup_digest)
    assert paper_realized_pnl_rollup_digest(rollup) == rollup.rollup_digest


def test_multiple_computed_positive_and_negative() -> None:
    gain = _computed("e1", price="150")  # +200
    loss = _computed("e2", price="80")  # 4 * (80 - 100) = -80
    rollup = _rollup([gain, loss])
    assert rollup.computed_event_count == 2
    assert rollup.realized_pnl_total == "120"  # 200 + (-80)
    assert rollup.closed_units_total == "8"
    assert rollup.source_event_digests == (gain.event.realized_pnl_event_digest, loss.event.realized_pnl_event_digest)


def test_computed_plus_no_realized_counts() -> None:
    computed = _computed("e1")  # +200, closed 4
    none = _no_realized("e2")  # opens from flat, closed 0, realized 0
    rollup = _rollup([computed, none])
    assert rollup.event_count == 2
    assert rollup.computed_event_count == 1
    assert rollup.no_realized_event_count == 1
    assert rollup.rejected_event_count == 0
    assert rollup.realized_pnl_total == "200"
    assert rollup.closed_units_total == "4"


def test_long_gain_and_short_loss_signs_preserved() -> None:
    long_gain = _computed("e1", prior_side="LONG", price="150")  # 4 * (150 - 100) = +200
    assert _rollup([long_gain]).realized_pnl_total == "200"
    short_loss = _computed("e2", prior_side="SHORT", price="150")  # 4 * (100 - 150) = -200
    assert _rollup([short_loss]).realized_pnl_total == "-200"


def test_high_scale_leading_zero_realized_exact_sum() -> None:
    # avg = 1e-100: realized per event = 4 * (1 - 1e-100) = "3.<99 nines>6". Two events sum to
    # 8 - 8e-100 = "7.<99 nines>2"; coefficient-only/default-context precision would round to "8".
    avg = "0." + "0" * 99 + "1"
    e1 = _computed("e1", avg=avg, price="1")
    e2 = _computed("e2", avg=avg, price="1")
    assert e1.event.realized_pnl == "3." + "9" * 99 + "6"
    rollup = _rollup([e1, e2])
    assert rollup.realized_pnl_total == "7." + "9" * 99 + "2"
    assert rollup.realized_pnl_total != "8"
    assert "e" not in rollup.realized_pnl_total.lower()
    assert rollup.closed_units_total == "8"


def test_cancellation_to_canonical_zero_no_negative_zero() -> None:
    gain = _computed("e1", price="150")  # +200
    loss = _computed("e2", price="50")  # 4 * (50 - 100) = -200
    rollup = _rollup([gain, loss])
    assert rollup.realized_pnl_total == "0"  # canonical zero, never "-0"
    assert rollup.closed_units_total == "8"


# --------------------------------------------------------------------------------------------------
# Fail-closed: input shape
# --------------------------------------------------------------------------------------------------


def test_empty_entries_rejected() -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="entries_empty"):
        _rollup([])


@pytest.mark.parametrize("bad", ["evt", b"evt", 5, {"e": 1}])
def test_non_sequence_entries_rejected(bad: object) -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="entries_malformed"):
        _rollup(bad)  # type: ignore[arg-type]


def test_non_bundle_member_rejected() -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="entry_malformed"):
        _rollup([{"not": "a-bundle"}])  # type: ignore[list-item]


def test_naked_event_input_rejected() -> None:
    # The public builder requires provenance bundles; a naked event is not a bundle.
    with pytest.raises(PaperRealizedPnlRollupError, match="entry_malformed"):
        _rollup([_computed("e1").event])


def test_event_count_exceeds_max_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(paper_realized_pnl_rollup, "_MAX_EVENT_COUNT", 2)
    entries = [_computed("e1"), _computed("e2"), _computed("e3")]
    with pytest.raises(PaperRealizedPnlRollupError, match="event_count_exceeds_max"):
        _rollup(entries)


def test_symbol_mismatch_rejected() -> None:
    e1 = _computed("e1", market_symbol="BTC-PERPETUAL")
    e2 = _computed("e2", market_symbol="ETH-PERPETUAL")
    with pytest.raises(PaperRealizedPnlRollupError, match="symbol_mismatch"):
        _rollup([e1, e2])


def test_duplicate_event_digest_rejected() -> None:
    bundle = _computed("e1")
    with pytest.raises(PaperRealizedPnlRollupError, match="duplicate_event_digest"):
        _rollup([bundle, bundle])


def test_duplicate_event_id_rejected() -> None:
    # Same id, different economics -> distinct digests but a duplicate id must still fail closed.
    e1 = _computed("dup", price="150")
    e2 = _computed("dup", price="80")
    assert e1.event.realized_pnl_event_digest != e2.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="duplicate_event_id"):
        _rollup([e1, e2])


# --------------------------------------------------------------------------------------------------
# Fail-closed: event shape / safety re-proof (precise errors before reconstruction)
# --------------------------------------------------------------------------------------------------


def test_event_digest_mismatch_rejected() -> None:
    forged = _forge_event(_computed("e1"), reseal=False, realized_pnl_event_digest="d" * 64)
    with pytest.raises(PaperRealizedPnlRollupError, match="event_digest_mismatch"):
        _rollup([forged])


def test_forged_self_consistent_unsafe_flag_rejected() -> None:
    forged = _forge_event(_computed("e1"), capital_mutated=True)
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest  # self-consistent
    with pytest.raises(PaperRealizedPnlRollupError, match="event_unsafe_flags"):
        _rollup([forged])


def test_forged_reserved_rejected_status_rejected() -> None:
    # The reserved REJECTED realized status is never emitted by the producer; a forged self-consistent
    # event claiming it must fail closed at the rollup boundary.
    forged = _forge_event(_computed("e1"), status=PaperRealizedPnlStatus.REJECTED)
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="event_status_invalid"):
        _rollup([forged])


def test_forged_fee_applied_event_rejected() -> None:
    # gross-only: an event carrying an applied fee must fail closed.
    forged = _forge_event(_computed("e1"), fee_amount_applied="1")
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="event_inconsistent"):
        _rollup([forged])


# --------------------------------------------------------------------------------------------------
# Fail-closed: provenance — coordinated resealed event + wrong upstream artifacts (Codex P1)
# --------------------------------------------------------------------------------------------------


def test_coordinated_resealed_event_rejected() -> None:
    # Codex P1: the event's scalar economics are internally consistent (a q0=2 cross: closed 2, residual 2,
    # realized 100, self-digest recomputed) but the upstream artifact digest references still point at the
    # genuine q0=10 chain. Reconstruction from the genuine upstream yields the canonical q0=10 event
    # (realized 200) whose digest/payload differs, so the resealed forgery fails closed (never summed).
    genuine = _computed("e1")  # LONG q0=10, SELL 4 @ 150 -> closed 4, residual 6, realized 200
    forged = _forge_event(
        genuine,
        prior_signed_units="2",
        closed_units="2",
        residual_open_units="2",
        realized_pnl="100",
    )
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest  # self-consistent
    with pytest.raises(PaperRealizedPnlRollupError, match="event_inconsistent"):
        _rollup([forged])


def test_forged_self_consistent_realized_amount_rejected() -> None:
    # Tampered realized_pnl (true 200 -> 999) re-sealed; reconstruction from genuine upstream gives 200.
    forged = _forge_event(_computed("e1"), realized_pnl="999")
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="event_inconsistent"):
        _rollup([forged])


def test_forged_self_consistent_closed_units_rejected() -> None:
    forged = _forge_event(_computed("e1"), closed_units="999")  # true closed is 4
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="event_inconsistent"):
        _rollup([forged])


def test_forged_high_scale_realized_amount_rejected() -> None:
    # 1e-100-scale tamper (true tail ...6, forged ...5) is caught by exact reconstruction.
    avg = "0." + "0" * 99 + "1"
    forged = _forge_event(_computed("e1", avg=avg, price="1"), realized_pnl="3." + "9" * 99 + "5")
    assert paper_realized_pnl_event_digest(forged.event) == forged.event.realized_pnl_event_digest
    with pytest.raises(PaperRealizedPnlRollupError, match="event_inconsistent"):
        _rollup([forged])


def test_wrong_prior_state_rejected() -> None:
    bundle = _computed("e1", avg="100")
    other = _computed("e2", avg="120")
    swapped = replace(bundle, prior_state=other.prior_state)
    with pytest.raises(PaperRealizedPnlRollupError, match="event_not_reproducible"):
        _rollup([swapped])


def test_wrong_fill_result_rejected() -> None:
    bundle = _computed("e1", price="150")
    other = _computed("e2", price="80")
    swapped = replace(bundle, fill_result=other.fill_result)
    with pytest.raises(PaperRealizedPnlRollupError, match="event_not_reproducible"):
        _rollup([swapped])


def test_wrong_transition_rejected() -> None:
    bundle = _computed("e1", avg="100")
    other = _computed("e2", avg="120")
    swapped = replace(bundle, transition=other.transition)
    with pytest.raises(PaperRealizedPnlRollupError, match="event_not_reproducible"):
        _rollup([swapped])


def test_wrong_new_position_state_rejected() -> None:
    bundle = _computed("e1", avg="100")
    other = _computed("e2", avg="120")
    swapped = replace(bundle, new_position_state=other.new_position_state)
    with pytest.raises(PaperRealizedPnlRollupError, match="event_not_reproducible"):
        _rollup([swapped])


@pytest.mark.parametrize(
    "field",
    ["prior_state", "fill_result", "transition", "new_position_state"],
)
def test_wrong_typed_upstream_artifact_rejected(field: str) -> None:
    bundle = _computed("e1")
    swapped = replace(bundle, **{field: {"not": "an-artifact"}})  # type: ignore[arg-type]
    with pytest.raises(PaperRealizedPnlRollupError):
        _rollup([swapped])


# --------------------------------------------------------------------------------------------------
# Fail-closed: rollup-level guards
# --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [("rollup_id", "live_order"), ("rollup_id", "bist"), ("correlation_id", "scheduler")],
)
def test_forbidden_token_in_ids_rejected(field: str, value: str) -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="scope_violation"):
        _rollup([_computed("e1")], **{field: value})


def test_forbidden_token_in_metadata_rejected() -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="scope_violation"):
        _rollup([_computed("e1")], metadata={"note": "place_order"})


def test_malformed_metadata_rejected() -> None:
    with pytest.raises(PaperRealizedPnlRollupError, match="metadata_malformed"):
        _rollup([_computed("e1")], metadata={"k": 5})  # type: ignore[dict-item]


def test_safe_market_data_terms_allowed() -> None:
    rollup = _rollup([_computed("e1")], metadata={"src": "order_book"})
    assert rollup.metadata == (("src", "order_book"),)


# --------------------------------------------------------------------------------------------------
# Determinism / immutability / no-leak
# --------------------------------------------------------------------------------------------------


def test_rollup_digest_deterministic() -> None:
    entries = [_computed("e1"), _computed("e2", price="80")]
    r1 = _rollup(entries)
    r2 = _rollup(entries)
    assert r1.rollup_digest == r2.rollup_digest
    assert paper_realized_pnl_rollup_digest(r1) == r1.rollup_digest
    assert paper_realized_pnl_rollup_to_dict(r1)["rollup_digest"] == r1.rollup_digest


def test_order_is_bound_into_digest() -> None:
    a, b = _computed("e1"), _computed("e2", price="80")
    forward = _rollup([a, b])
    reverse = _rollup([b, a])
    assert forward.source_event_digests == (a.event.realized_pnl_event_digest, b.event.realized_pnl_event_digest)
    assert reverse.source_event_digests == (b.event.realized_pnl_event_digest, a.event.realized_pnl_event_digest)
    assert forward.rollup_digest != reverse.rollup_digest  # order is bound
    assert forward.realized_pnl_total == reverse.realized_pnl_total  # but the sum is order-independent


def test_inputs_not_mutated() -> None:
    entries = [_computed("e1"), _computed("e2", price="80")]
    before = [e.event.realized_pnl_event_digest for e in entries]
    _rollup(entries)
    assert [e.event.realized_pnl_event_digest for e in entries] == before
    assert [paper_realized_pnl_event_digest(e.event) for e in entries] == before


def test_output_immutable() -> None:
    rollup = _rollup([_computed("e1")])
    with pytest.raises(FrozenInstanceError):
        rollup.realized_pnl_total = "1"  # type: ignore[misc]


def test_dict_keys_and_safe_flags_no_forbidden_value_fields() -> None:
    payload = paper_realized_pnl_rollup_to_dict(_rollup([_computed("e1")]))
    assert set(payload) == _EXPECTED_KEYS
    assert payload["paper_only"] is True
    assert payload["rollup_computed"] is True
    assert payload["gross_only"] is True
    for flag in _SAFE_FALSE_FLAGS:
        assert payload[flag] is False
    assert _FORBIDDEN_VALUE_KEYS.isdisjoint(payload.keys())


def test_module_imports_only_validation_layer() -> None:
    source = Path(paper_realized_pnl_rollup.__file__).read_text(encoding="utf-8")
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
# Compatibility smoke: consume bundles produced by the genuine per-fill flow
# --------------------------------------------------------------------------------------------------


def test_rollup_consumes_genuine_per_fill_bundles() -> None:
    # Each bundle is produced through the real apply_paper_fill_to_position -> compute_paper_realized_pnl_event
    # path (no session-sequence source touched). A rollup over that per-fill flow aggregates cleanly.
    long_reduce = _computed("evt-long", prior_side="LONG", avg="100", price="150", filled="4")  # +200
    short_reduce = _computed("evt-short", prior_side="SHORT", avg="100", price="80", filled="5")  # 5*(100-80)=+100
    opened = _no_realized("evt-open")  # opens from flat -> NO_REALIZED_PNL
    rollup = _rollup([long_reduce, short_reduce, opened], rollup_id="session-rollup-1")
    assert rollup.event_count == 3
    assert rollup.computed_event_count == 2
    assert rollup.no_realized_event_count == 1
    assert rollup.realized_pnl_total == "300"  # 200 + 100 + 0
    assert rollup.closed_units_total == "9"  # 4 + 5 + 0
    assert paper_realized_pnl_rollup_digest(rollup) == rollup.rollup_digest
