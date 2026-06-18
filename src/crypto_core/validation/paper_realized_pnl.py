"""Paper realized-PnL event — deterministic gross realized PnL for one paper fill/transition.

A small, immutable, fail-closed module that consumes a prior digest-bound ``PaperPositionState``, the
``PaperFillSimulationResult`` applied to it, and the corresponding ``PaperPositionTransitionResult`` and
emits a frozen, digest-bound ``PaperRealizedPnlEvent``. It computes **gross realized PnL for the
closed/reduced/crossed-through prior units only** — it does **not** compute unrealized PnL, total PnL,
equity, margin, capital, or balances; it applies no fees (this slice); it reserves/mutates no capital;
routes no order; creates no venue/exchange/client order id / route id / execution instruction; calls no
live/private API; schedules nothing; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST.

Realized PnL semantics (exact ``Decimal``; ``q0`` = prior signed units, ``avg0`` = prior average entry,
``fp`` = fill price > 0, ``f`` = filled units > 0; BUY ⇒ delta ``+f``, SELL ⇒ delta ``-f``;
``closed = min(f, |q0|)`` for an opposite-side fill):
  - prior FLAT, or same-side add (LONG+BUY / SHORT+SELL) ⇒ realized = 0, closed = 0, NO_REALIZED_PNL.
  - opposite-side reduce / exact close (``f <= |q0|``) ⇒ closed = f (= |q0| at exact close);
    LONG: realized = closed * (fp - avg0); SHORT: realized = closed * (avg0 - fp); COMPUTED.
  - opposite-side cross-through (``f > |q0|``) ⇒ closed = |q0| (only the prior position is realized; the
    residual is opened at ``fp`` and is NOT realized here); same per-side formula; COMPUTED.
Gross only: ``fees_included`` is always False and ``fee_amount_applied`` is always None.

Numeric discipline: realized PnL is a pure product/difference (no division), computed under an
input-derived ``localcontext`` precision so it is exact; the loss sign comes from an ordered subtraction
(``fp - avg0`` / ``avg0 - fp``), never a context-affected unary minus; abs via ``copy_abs`` and the SELL
sign flip via ``copy_negate`` (never ``abs()`` / unary ``-`` / ``Decimal.normalize()``); rendering is
context-independent fixed-point; no scientific notation, no negative zero.

Fail closed: wrong-typed/malformed/forged prior/fill/transition, a digest mismatch, a symbol mismatch, a
transition that does not bind the exact prior/fill digests, a non-``APPLIED`` transition, a non-applied
(``REJECTED``) fill, an unsafe flag, a forbidden token, an invalid/noncanonical decimal, or an
inconsistent side/signed/abs/avg raises ``PaperRealizedPnlError``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_order_intent_admission import PaperOrderIntentType, PaperOrderSide
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    PaperPositionStateError,
    PaperPositionStateSide,
    PaperPositionTransitionResult,
    PaperPositionTransitionStatus,
    apply_paper_fill_to_position,
    paper_position_state_digest,
    paper_position_transition_result_digest,
)

_EVENT_SCHEMA_VERSION = "paper-realized-pnl-event.v1"
_EXPECTED_STATE_SCHEMA_VERSION = "paper-position-state.v1"
_EXPECTED_FILL_SCHEMA_VERSION = "paper-fill-simulation-result.v1"
_EXPECTED_TRANSITION_SCHEMA_VERSION = "paper-position-transition.v1"

_REASON_NO_CLOSED_UNITS = "no_closed_units"
_REASON_PARTIAL_FILL = "partial_fill"

_VALID_FILL_SIDES = frozenset(side.value for side in PaperOrderSide)
_VALID_INTENT_TYPES = frozenset(intent_type.value for intent_type in PaperOrderIntentType)

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling validation modules (word-bounded).
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector|connector_ready|"
    r"credential|credentials|scheduler|shadow|route_id|execution_instruction|deribit|"
    r"venue_order_id|exchange_order_id|client_order_id)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")


class PaperRealizedPnlError(RuntimeError):
    """Raised when realized-PnL inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperRealizedPnlStatus(str, Enum):
    """Deterministic paper realized-PnL outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    NO_REALIZED_PNL = "NO_REALIZED_PNL"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperRealizedPnlEvent:
    """Deterministic, immutable digest-bound paper realized-PnL event. Gross only. PAPER ONLY.

    Reports realized PnL for the closed/reduced/crossed prior units of one fill/transition — never
    unrealized/total PnL, equity, margin, capital, or balances; applies no fees. ``realized_pnl_computed``
    is True only when ``COMPUTED``; every other attestation is False.
    """

    schema_version: str
    realized_pnl_event_id: str
    status: PaperRealizedPnlStatus
    market_symbol: str
    prior_position_state_digest: str
    fill_simulation_result_digest: str
    position_transition_digest: str
    new_position_state_digest: str | None
    prior_side: str
    fill_side: str
    prior_signed_units: str
    filled_units: str
    closed_units: str
    residual_open_units: str
    average_entry_price: str | None
    fill_price: str
    realized_pnl: str
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    realized_pnl_event_digest: str
    fee_amount_applied: str | None = None
    paper_only: bool = True
    realized_pnl_computed: bool = False
    fees_included: bool = False
    unrealized_pnl_computed: bool = False
    total_pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    live_position_mutated: bool = False
    real_money_enabled: bool = False
    real_orders_enabled: bool = False
    order_routed: bool = False
    venue_order_id_created: bool = False
    exchange_order_id_created: bool = False
    client_order_id_created: bool = False
    route_id_created: bool = False
    execution_instruction_created: bool = False
    live_api_called: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    connector_invoked: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _is_sorted_unique_reasons(reasons: object) -> bool:
    if not isinstance(reasons, tuple):
        return False
    if not all(isinstance(reason, str) and reason != "" for reason in reasons):
        return False
    return list(reasons) == sorted(set(reasons))


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _parse_decimal(value: object) -> Decimal | None:
    """Return an exact finite ``Decimal`` for a strict decimal string, else ``None`` (no float/bool path)."""
    if not isinstance(value, str) or not _DECIMAL_PATTERN.fullmatch(value):
        return None
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def _render_decimal(value: Decimal) -> str:
    """Render an exact ``Decimal`` as a canonical plain-decimal string (context-independent). Never normalize()."""
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    """Parse a strict decimal string that is ALSO already in canonical render form, else ``None``."""
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _decimal_span(value: Decimal) -> int:
    """Positional span of an exact Decimal: significant digits PLUS the magnitude implied by the exponent.

    ``len(as_tuple().digits)`` counts only significant digits, never the exponent gap, so a value such as
    ``1e-100`` (one significant digit) would be sized as width 1 while it actually spans 101 fixed-point
    places. Summing this span keeps the working precision wide enough that products/differences over
    high-scale (many leading/trailing zero) inputs stay exact instead of being silently context-rounded.
    """
    tup = value.as_tuple()
    return len(tup.digits) + abs(int(tup.exponent))


def _arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal precision wide enough that every exact product/difference over the inputs is exact."""
    span = sum(_decimal_span(value) for value in operands)
    return max(28, span + 40)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperRealizedPnlError("paper_realized_pnl:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperRealizedPnlError("paper_realized_pnl:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


def _is_metadata_tuple(metadata: object) -> bool:
    if not isinstance(metadata, tuple):
        return False
    for pair in metadata:
        if (
            not isinstance(pair, tuple)
            or len(pair) != 2
            or not isinstance(pair[0], str)
            or not isinstance(pair[1], str)
        ):
            return False
    keys = [pair[0] for pair in metadata]
    if len(set(keys)) != len(keys):
        return False
    return metadata == tuple(sorted(metadata))


def _has_scope_violation(*texts: object) -> bool:
    for text in texts:
        if not isinstance(text, str) or text == "":
            continue
        if _BIST_PATTERN.search(text):
            return True
        scrubbed = text
        for safe_term in _SAFE_MARKET_DATA_TERMS:
            scrubbed = re.sub(re.escape(safe_term), " ", scrubbed, flags=re.IGNORECASE)
        if _FORBIDDEN_PATTERN.search(scrubbed):
            return True
    return False


# --------------------------------------------------------------------------------------------------
# Upstream re-proof
# --------------------------------------------------------------------------------------------------


def _state_is_paper_safe(state: PaperPositionState) -> bool:
    return (
        state.paper_only is True
        and state.live_position_mutated is False
        and state.real_money_enabled is False
        and state.real_orders_enabled is False
        and state.order_routed is False
        and state.venue_order_id_created is False
        and state.exchange_order_id_created is False
        and state.client_order_id_created is False
        and state.route_id_created is False
        and state.execution_instruction_created is False
        and state.live_api_called is False
        and state.scheduler_enabled is False
        and state.connector_invoked is False
        and state.pnl_computed is False
        and state.capital_reserved is False
        and state.capital_mutated is False
    )


def _reprove_prior_state(state: PaperPositionState) -> tuple[PaperPositionStateSide, Decimal, Decimal | None]:
    """Re-prove a digest-valid prior position state's structure/safety; return (side, signed_units, average)."""
    if state.schema_version != _EXPECTED_STATE_SCHEMA_VERSION:
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if not isinstance(state.side, PaperPositionStateSide):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if not _state_is_paper_safe(state):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_unsafe_flags")
    if not _is_non_empty_string(state.position_state_id) or not _is_non_empty_string(state.correlation_id):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if not _is_non_empty_string(state.market_symbol):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if state.last_fill_simulation_digest is not None and not _is_hex64_string(state.last_fill_simulation_digest):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if not _is_int(state.transition_count) or state.transition_count < 0:
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    signed = _canonical_decimal(state.signed_units)
    abs_value = _canonical_decimal(state.abs_units)
    if signed is None or abs_value is None or abs_value < 0 or signed.copy_abs() != abs_value:
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    average: Decimal | None = None
    if state.average_entry_price is not None:
        average = _canonical_decimal(state.average_entry_price)
        if average is None or not average > 0:
            raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if state.side is PaperPositionStateSide.FLAT:
        if signed != 0 or abs_value != 0 or average is not None:
            raise PaperRealizedPnlError("paper_realized_pnl:prior_state_inconsistent")
    elif state.side is PaperPositionStateSide.LONG:
        if not signed > 0 or average is None:
            raise PaperRealizedPnlError("paper_realized_pnl:prior_state_inconsistent")
    else:  # SHORT
        if not signed < 0 or average is None:
            raise PaperRealizedPnlError("paper_realized_pnl:prior_state_inconsistent")
    if not _is_metadata_tuple(state.metadata):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if _has_scope_violation(
        state.position_state_id, state.market_symbol, state.correlation_id, *_metadata_texts(state.metadata)
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_scope_violation")
    return state.side, signed, average


def _fill_is_paper_safe(fill: PaperFillSimulationResult) -> bool:
    return (
        fill.paper_only is True
        and fill.real_orders_enabled is False
        and fill.real_money_enabled is False
        and fill.order_routed is False
        and fill.venue_order_id_created is False
        and fill.exchange_order_id_created is False
        and fill.client_order_id_created is False
        and fill.route_id_created is False
        and fill.execution_instruction_created is False
        and fill.execution_authorized is False
        and fill.live_api_called is False
        and fill.scheduler_enabled is False
        and fill.connector_invoked is False
        and fill.position_mutated is False
        and fill.pnl_computed is False
        and fill.capital_reserved is False
    )


def _reprove_fill_result(fill: PaperFillSimulationResult) -> tuple[str, Decimal, Decimal]:
    """Re-prove a digest-valid fill result's full structure/economics; return (side, filled_units, fill_price).

    Realized PnL requires an applied fill: a ``REJECTED`` fill fails closed here. A self-consistent forged
    result (digest recomputed over a tampered payload) is still rejected on the structural checks.
    """
    if fill.schema_version != _EXPECTED_FILL_SCHEMA_VERSION:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not isinstance(fill.status, PaperFillSimulationStatus):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not _fill_is_paper_safe(fill):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_unsafe_flags")
    if not _is_non_empty_string(fill.fill_simulation_id):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not _is_non_empty_string(fill.market_symbol) or not _is_non_empty_string(fill.correlation_id):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if fill.side not in _VALID_FILL_SIDES or fill.intent_type not in _VALID_INTENT_TYPES:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not (
        _is_hex64_string(fill.intent_digest)
        and _is_hex64_string(fill.market_snapshot_digest)
        and _is_hex64_string(fill.fill_policy_digest)
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not _is_metadata_tuple(fill.metadata):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if _has_scope_violation(
        fill.fill_simulation_id, fill.market_symbol, fill.correlation_id, *_metadata_texts(fill.metadata)
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_scope_violation")
    if not _is_sorted_unique_reasons(fill.reason_codes):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")

    fill_price = _canonical_decimal(fill.fill_price)
    filled = _canonical_decimal(fill.filled_units)
    unfilled = _canonical_decimal(fill.unfilled_units)
    gross = _canonical_decimal(fill.gross_notional)
    fee = _canonical_decimal(fill.fee_amount)
    if fill_price is None or filled is None or unfilled is None or gross is None or fee is None:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if filled < 0 or unfilled < 0 or gross < 0 or fee < 0:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")

    if fill.status is PaperFillSimulationStatus.REJECTED:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_not_applicable")
    if not filled > 0 or not fill_price > 0 or not gross > 0:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_inconsistent")
    if fill.status is PaperFillSimulationStatus.FILLED:
        if unfilled != 0 or fill.reason_codes != ():
            raise PaperRealizedPnlError("paper_realized_pnl:fill_result_inconsistent")
    else:  # PARTIALLY_FILLED
        if not unfilled > 0 or fill.reason_codes != (_REASON_PARTIAL_FILL,):
            raise PaperRealizedPnlError("paper_realized_pnl:fill_result_inconsistent")
    # Economic integrity: gross_notional must be the EXACT product filled_units * fill_price (the fill
    # simulator's own invariant). Computed under a span-aware context so the product is exact (no
    # default-context rounding); a digest-valid forged fill with an impossible gross is rejected.
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision((filled, fill_price))
        if filled * fill_price != gross:
            raise PaperRealizedPnlError("paper_realized_pnl:fill_result_inconsistent")
    return fill.side, filled, fill_price


def _transition_is_paper_safe(transition: PaperPositionTransitionResult) -> bool:
    return (
        transition.paper_only is True
        and transition.live_position_mutated is False
        and transition.real_money_enabled is False
        and transition.real_orders_enabled is False
        and transition.order_routed is False
        and transition.venue_order_id_created is False
        and transition.exchange_order_id_created is False
        and transition.client_order_id_created is False
        and transition.route_id_created is False
        and transition.execution_instruction_created is False
        and transition.live_api_called is False
        and transition.scheduler_enabled is False
        and transition.connector_invoked is False
        and transition.pnl_computed is False
        and transition.capital_reserved is False
        and transition.capital_mutated is False
    )


def _reprove_transition(transition: PaperPositionTransitionResult) -> None:
    """Re-prove a digest-valid transition's structure/safety/status-consistency (fail-closed)."""
    if transition.schema_version != _EXPECTED_TRANSITION_SCHEMA_VERSION:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not isinstance(transition.status, PaperPositionTransitionStatus):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not _transition_is_paper_safe(transition):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_unsafe_flags")
    if not _is_non_empty_string(transition.transition_id) or not _is_non_empty_string(transition.correlation_id):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not _is_non_empty_string(transition.market_symbol):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not (
        _is_hex64_string(transition.prior_position_state_digest)
        and _is_hex64_string(transition.fill_simulation_result_digest)
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if transition.new_position_state_digest is not None and not _is_hex64_string(transition.new_position_state_digest):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not _is_metadata_tuple(transition.metadata):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not _is_sorted_unique_reasons(transition.reason_codes):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if _has_scope_violation(
        transition.transition_id,
        transition.market_symbol,
        transition.correlation_id,
        *_metadata_texts(transition.metadata),
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_scope_violation")
    if transition.status is PaperPositionTransitionStatus.APPLIED:
        if not _is_hex64_string(transition.new_position_state_digest) or transition.reason_codes != ():
            raise PaperRealizedPnlError("paper_realized_pnl:transition_inconsistent")
        if transition.paper_position_state_updated is not True:
            raise PaperRealizedPnlError("paper_realized_pnl:transition_inconsistent")
    else:  # REJECTED
        if transition.new_position_state_digest is not None or transition.paper_position_state_updated is not False:
            raise PaperRealizedPnlError("paper_realized_pnl:transition_inconsistent")


# --------------------------------------------------------------------------------------------------
# Realized PnL computation
# --------------------------------------------------------------------------------------------------


def _compute_realized(
    *,
    prior_side: PaperPositionStateSide,
    q0: Decimal,
    avg0: Decimal | None,
    fill_side: str,
    filled: Decimal,
    fill_price: Decimal,
) -> tuple[PaperRealizedPnlStatus, Decimal, Decimal, Decimal]:
    """Pure exact realized PnL. Returns (status, closed_units, residual_open_units, realized_pnl)."""
    delta = filled if fill_side == PaperOrderSide.BUY.value else filled.copy_negate()
    operands = (q0, filled, fill_price, avg0 if avg0 is not None else Decimal(0))
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(operands)
        q1 = q0 + delta
        residual = q1.copy_abs()
        if prior_side is PaperPositionStateSide.FLAT or (q0 > 0) == (delta > 0):
            # flat open or same-side add — nothing closed, nothing realized
            return PaperRealizedPnlStatus.NO_REALIZED_PNL, Decimal(0), residual, Decimal(0)
        abs_q0 = q0.copy_abs()
        closed = filled if filled < abs_q0 else abs_q0  # min(filled, |q0|); avg0 present for non-flat prior
        if prior_side is PaperPositionStateSide.LONG:  # SELL closes a long
            realized = closed * (fill_price - avg0)
        else:  # SHORT — BUY closes a short
            realized = closed * (avg0 - fill_price)
    return PaperRealizedPnlStatus.COMPUTED, closed, residual, realized


def compute_paper_realized_pnl_event(
    prior_state: PaperPositionState,
    fill_result: PaperFillSimulationResult,
    transition: PaperPositionTransitionResult,
    new_position_state: PaperPositionState,
    *,
    realized_pnl_event_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperRealizedPnlEvent:
    """Compute a deterministic gross realized-PnL event for one applied fill/transition.

    The ``prior_state``, ``fill_result``, ``transition``, and the transition's resulting
    ``new_position_state`` are re-proven via their PUBLIC digests (mismatch raises) and structurally
    re-proven; the market symbol must match; the transition must be ``APPLIED`` and bind the exact
    prior/fill digests; the fill must be ``FILLED``/``PARTIALLY_FILLED``. The transition + new state are
    additionally re-proven to be the genuine deterministic result of applying THIS fill to THIS prior by
    re-running the canonical ``apply_paper_fill_to_position`` and requiring identical transition and
    new-state digests — so a self-consistent forged transition cannot bind an unrelated new-state digest
    into the audit chain. Realized PnL is computed from the PRIOR average and the fill price for the
    closed/crossed prior units only (gross; no fees). No unrealized/total PnL, no capital/balance, no
    order routing, no live API; inputs are never mutated.
    """
    if not _is_non_empty_string(realized_pnl_event_id):
        raise PaperRealizedPnlError("paper_realized_pnl:realized_pnl_event_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperRealizedPnlError("paper_realized_pnl:correlation_id_invalid")
    event_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(realized_pnl_event_id, correlation_id, *_metadata_texts(event_metadata)):
        raise PaperRealizedPnlError("paper_realized_pnl:scope_violation")
    if not isinstance(prior_state, PaperPositionState):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed")
    if not isinstance(fill_result, PaperFillSimulationResult):
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed")
    if not isinstance(transition, PaperPositionTransitionResult):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed")
    if not isinstance(new_position_state, PaperPositionState):
        raise PaperRealizedPnlError("paper_realized_pnl:new_state_malformed")

    # Digest boundaries: re-prove every input artifact's self-digest via its PUBLIC serializer.
    try:
        expected_state_digest = paper_position_state_digest(prior_state)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_malformed") from exc
    if not isinstance(prior_state.position_state_digest, str) or prior_state.position_state_digest != (
        expected_state_digest
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:prior_state_digest_mismatch")
    try:
        expected_fill_digest = paper_fill_simulation_result_digest(fill_result)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_malformed") from exc
    if not isinstance(fill_result.result_digest, str) or fill_result.result_digest != expected_fill_digest:
        raise PaperRealizedPnlError("paper_realized_pnl:fill_result_digest_mismatch")
    try:
        expected_transition_digest = paper_position_transition_result_digest(transition)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperRealizedPnlError("paper_realized_pnl:transition_malformed") from exc
    if not isinstance(transition.transition_digest, str) or transition.transition_digest != expected_transition_digest:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_digest_mismatch")
    try:
        expected_new_state_digest = paper_position_state_digest(new_position_state)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperRealizedPnlError("paper_realized_pnl:new_state_malformed") from exc
    if not isinstance(new_position_state.position_state_digest, str) or new_position_state.position_state_digest != (
        expected_new_state_digest
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:new_state_digest_mismatch")

    prior_side, signed, average = _reprove_prior_state(prior_state)
    fill_side, filled, fill_price = _reprove_fill_result(fill_result)
    _reprove_transition(transition)

    if not (prior_state.market_symbol == fill_result.market_symbol == transition.market_symbol):
        raise PaperRealizedPnlError("paper_realized_pnl:symbol_mismatch")
    if transition.prior_position_state_digest != prior_state.position_state_digest:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_prior_digest_mismatch")
    if transition.fill_simulation_result_digest != fill_result.result_digest:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_fill_digest_mismatch")
    if transition.status is not PaperPositionTransitionStatus.APPLIED:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_not_applied")
    if not _is_hex64_string(transition.new_position_state_digest):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_new_state_missing")
    if transition.new_position_state_digest != new_position_state.position_state_digest:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_new_state_digest_mismatch")

    # Economic re-proof: the transition + new state must be the genuine deterministic result of applying
    # THIS fill to THIS prior. Re-run the canonical producer with the transition's own ids/metadata and
    # require identical transition and new-state digests — closes any self-consistent forged transition
    # that binds an unrelated (even individually valid) new-state digest.
    try:
        recomputed_transition, recomputed_new_state = apply_paper_fill_to_position(
            prior_state,
            fill_result,
            transition_id=transition.transition_id,
            new_position_state_id=new_position_state.position_state_id,
            correlation_id=transition.correlation_id,
            metadata=dict(transition.metadata),
        )
    except PaperPositionStateError as exc:
        raise PaperRealizedPnlError("paper_realized_pnl:transition_not_reproducible") from exc
    if (
        recomputed_new_state is None
        or recomputed_transition.transition_digest != transition.transition_digest
        or recomputed_new_state.position_state_digest != new_position_state.position_state_digest
    ):
        raise PaperRealizedPnlError("paper_realized_pnl:transition_not_reproducible")

    status, closed, residual, realized = _compute_realized(
        prior_side=prior_side, q0=signed, avg0=average, fill_side=fill_side, filled=filled, fill_price=fill_price
    )
    reasons: tuple[str, ...] = () if status is PaperRealizedPnlStatus.COMPUTED else (_REASON_NO_CLOSED_UNITS,)

    return _finalize_event(
        realized_pnl_event_id=realized_pnl_event_id,
        status=status,
        prior_state=prior_state,
        fill_result=fill_result,
        transition=transition,
        fill_side=fill_side,
        closed_units=_render_decimal(closed),
        residual_open_units=_render_decimal(residual),
        realized_pnl=_render_decimal(realized),
        reasons=reasons,
        correlation_id=correlation_id,
        metadata=event_metadata,
    )


def _finalize_event(
    *,
    realized_pnl_event_id: str,
    status: PaperRealizedPnlStatus,
    prior_state: PaperPositionState,
    fill_result: PaperFillSimulationResult,
    transition: PaperPositionTransitionResult,
    fill_side: str,
    closed_units: str,
    residual_open_units: str,
    realized_pnl: str,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperRealizedPnlEvent:
    computed = status is PaperRealizedPnlStatus.COMPUTED
    fields: dict[str, object] = {
        "schema_version": _EVENT_SCHEMA_VERSION,
        "realized_pnl_event_id": realized_pnl_event_id,
        "status": status,
        "market_symbol": prior_state.market_symbol,
        "prior_position_state_digest": prior_state.position_state_digest,
        "fill_simulation_result_digest": fill_result.result_digest,
        "position_transition_digest": transition.transition_digest,
        "new_position_state_digest": transition.new_position_state_digest,
        "prior_side": prior_state.side.value,
        "fill_side": fill_side,
        "prior_signed_units": prior_state.signed_units,
        "filled_units": fill_result.filled_units,
        "closed_units": closed_units,
        "residual_open_units": residual_open_units,
        "average_entry_price": prior_state.average_entry_price,
        "fill_price": fill_result.fill_price,
        "realized_pnl": realized_pnl,
        "reason_codes": _sorted_unique(reasons),
        "correlation_id": correlation_id,
        "metadata": metadata,
        "realized_pnl_computed": computed,
    }
    seed = PaperRealizedPnlEvent(realized_pnl_event_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_realized_pnl_event_digest(seed))


def _replace_digest(event: PaperRealizedPnlEvent, digest: str) -> PaperRealizedPnlEvent:
    fields = _event_fields(event)
    fields["realized_pnl_event_digest"] = digest
    return PaperRealizedPnlEvent(**fields)  # type: ignore[arg-type]


def _event_fields(event: PaperRealizedPnlEvent) -> dict[str, object]:
    return {
        "schema_version": event.schema_version,
        "realized_pnl_event_id": event.realized_pnl_event_id,
        "status": event.status,
        "market_symbol": event.market_symbol,
        "prior_position_state_digest": event.prior_position_state_digest,
        "fill_simulation_result_digest": event.fill_simulation_result_digest,
        "position_transition_digest": event.position_transition_digest,
        "new_position_state_digest": event.new_position_state_digest,
        "prior_side": event.prior_side,
        "fill_side": event.fill_side,
        "prior_signed_units": event.prior_signed_units,
        "filled_units": event.filled_units,
        "closed_units": event.closed_units,
        "residual_open_units": event.residual_open_units,
        "average_entry_price": event.average_entry_price,
        "fill_price": event.fill_price,
        "realized_pnl": event.realized_pnl,
        "reason_codes": event.reason_codes,
        "correlation_id": event.correlation_id,
        "metadata": event.metadata,
        "realized_pnl_computed": event.realized_pnl_computed,
    }


def _event_payload_from(event: PaperRealizedPnlEvent) -> dict[str, object]:
    return {
        "schema_version": event.schema_version,
        "realized_pnl_event_id": event.realized_pnl_event_id,
        "status": event.status.value,
        "market_symbol": event.market_symbol,
        "prior_position_state_digest": event.prior_position_state_digest,
        "fill_simulation_result_digest": event.fill_simulation_result_digest,
        "position_transition_digest": event.position_transition_digest,
        "new_position_state_digest": event.new_position_state_digest,
        "prior_side": event.prior_side,
        "fill_side": event.fill_side,
        "prior_signed_units": event.prior_signed_units,
        "filled_units": event.filled_units,
        "closed_units": event.closed_units,
        "residual_open_units": event.residual_open_units,
        "average_entry_price": event.average_entry_price,
        "fill_price": event.fill_price,
        "realized_pnl": event.realized_pnl,
        "fee_amount_applied": event.fee_amount_applied,
        "reason_codes": list(event.reason_codes),
        "correlation_id": event.correlation_id,
        "metadata": [list(pair) for pair in event.metadata],
        "paper_only": event.paper_only,
        "realized_pnl_computed": event.realized_pnl_computed,
        "fees_included": event.fees_included,
        "unrealized_pnl_computed": event.unrealized_pnl_computed,
        "total_pnl_computed": event.total_pnl_computed,
        "capital_reserved": event.capital_reserved,
        "capital_mutated": event.capital_mutated,
        "balance_mutated": event.balance_mutated,
        "live_position_mutated": event.live_position_mutated,
        "real_money_enabled": event.real_money_enabled,
        "real_orders_enabled": event.real_orders_enabled,
        "order_routed": event.order_routed,
        "venue_order_id_created": event.venue_order_id_created,
        "exchange_order_id_created": event.exchange_order_id_created,
        "client_order_id_created": event.client_order_id_created,
        "route_id_created": event.route_id_created,
        "execution_instruction_created": event.execution_instruction_created,
        "live_api_called": event.live_api_called,
        "scheduler_enabled": event.scheduler_enabled,
        "auto_loop_enabled": event.auto_loop_enabled,
        "connector_invoked": event.connector_invoked,
    }


def paper_realized_pnl_event_to_dict(event: PaperRealizedPnlEvent) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a realized-PnL event (deterministic shape, includes self-digest)."""
    payload = _event_payload_from(event)
    payload["realized_pnl_event_digest"] = event.realized_pnl_event_digest
    return payload


def paper_realized_pnl_event_digest(event: PaperRealizedPnlEvent) -> str:
    """Recompute the canonical realized-PnL-event digest from the serializer output, excluding self-digest."""
    return _canonical_digest(_event_payload_from(event))


__all__ = [
    "PaperRealizedPnlError",
    "PaperRealizedPnlEvent",
    "PaperRealizedPnlStatus",
    "compute_paper_realized_pnl_event",
    "paper_realized_pnl_event_digest",
    "paper_realized_pnl_event_to_dict",
]
