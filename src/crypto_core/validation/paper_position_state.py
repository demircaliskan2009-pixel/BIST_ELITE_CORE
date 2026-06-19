"""Paper position state transition — deterministic, paper-only signed-position update from a fill.

A small, immutable, fail-closed module that applies a ``FILLED`` / ``PARTIALLY_FILLED``
``PaperFillSimulationResult`` to a prior digest-bound ``PaperPositionState`` and emits a new immutable
digest-bound ``PaperPositionState`` plus a ``PaperPositionTransitionResult``. It tracks **signed paper
position state only** for one market symbol — it computes **no PnL**, tracks no capital/balances,
reserves/mutates no capital, routes no order, creates no venue/exchange/client order id, calls no
live/private API, and touches no connector/scheduler/runtime/venue/execution/service/session/portfolio
surface, no Deribit, no BIST. ``paper_position_state_updated`` refers to this paper artifact only;
``live_position_mutated`` is always False.

Transition semantics (exact ``Decimal``; ``q0`` = prior signed units, ``f`` = filled units > 0,
``p`` = fill price > 0; BUY ⇒ delta ``+f``, SELL ⇒ delta ``-f``; ``q1 = q0 + delta``):
  - prior FLAT ⇒ open at ``p`` (avg = p).
  - same sign (adding) ⇒ weighted average ``(|q0|*avg0 + |delta|*p) / |q1|``.
  - opposite sign, ``|delta| < |q0|`` (reduce, no cross) ⇒ preserve prior avg.
  - opposite sign, ``|delta| == |q0|`` (close) ⇒ FLAT, avg = None.
  - opposite sign, ``|delta| > |q0|`` (cross) ⇒ residual opened at ``p`` (avg = p).
  No realized/unrealized PnL is ever computed; no capital is touched.

Numeric discipline: signed-unit arithmetic (add/abs) and the open/cross/reduce/close average paths are
**exact** (computed under an input-derived ``localcontext`` precision, so high-precision inputs are
preserved). The *weighted-average division* (adding to a same-side position) is inherently a rational
that generally has no finite decimal form; it is computed under a **fixed** ``_WEIGHTED_AVERAGE_PRECISION``
with ``ROUND_HALF_EVEN`` so the result is deterministic per input *values* (representation-independent).
Rendering is context-independent (``format(…, "f")`` + manual trailing-zero strip — never
``Decimal.normalize()``); no scientific notation, no negative zero.

Fail closed: a wrong-typed/malformed/forged prior state or fill result, a digest mismatch, a symbol
mismatch, an unsafe flag, a forbidden token, an invalid decimal, or an inconsistent
side/signed/abs/avg raises ``PaperPositionStateError``. A well-formed but non-applicable fill (status
``REJECTED``) yields a ``PaperPositionTransitionResult`` with status ``REJECTED`` (reason
``fill_not_applied``) and no new state.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationResult,
    PaperFillSimulationStatus,
    paper_fill_simulation_result_digest,
)
from crypto_core.validation.paper_order_intent_admission import PaperOrderIntentType, PaperOrderSide

_STATE_SCHEMA_VERSION = "paper-position-state.v1"
_TRANSITION_SCHEMA_VERSION = "paper-position-transition.v1"
_EXPECTED_FILL_SCHEMA_VERSION = "paper-fill-simulation-result.v1"

# Fixed precision for the weighted-average division (a weighted mean is a rational with no exact finite
# decimal form). This is the DELIBERATE, declared deterministic paper average-entry precision standard
# for this generic simulator layer: a same-side add divides numerator/|q1| at exactly this many
# significant digits with ROUND_HALF_EVEN. It is fixed (not input-derived) so the rounded result is a
# pure function of the input *values* (representation-independent) and stable across callers/runs; a
# result needing more than this many significant digits is rounded HALF_EVEN here, never silently
# elsewhere. The open / reduce / close / cross paths stay exact (no division). Regression-tested so
# future PnL/report consumers cannot be surprised by where precision loss occurs.
_WEIGHTED_AVERAGE_PRECISION = 50

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Sign/positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling validation modules (word-bounded). A bare ``order``/``orders`` token
# is rejected while ``border``/``reorder`` are spared; market-data terms are scrubbed before the scan.
_BIST_PATTERN = re.compile(r"\b(?:bist\w*|borsa\w*|matriks\w*)|\bkap\b", re.IGNORECASE)
_FORBIDDEN_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])orders?(?![A-Za-z0-9])"
    r"|\b(?:private|order_router|place_order|live_order|auto_loop|connector_ready|credential|"
    r"credentials|scheduler|shadow)\w*"
    r"|\blive(?:\b|[_-]\w+)",
    re.IGNORECASE,
)
_SAFE_MARKET_DATA_TERMS = ("limit_order_book", "order_book", "order_flow")

_REASON_FILL_NOT_APPLIED = "fill_not_applied"

# Upstream reason emitted by the fill simulator for a genuine partial fill (mirrored, not imported, so a
# forged result claiming PARTIALLY_FILLED must carry exactly this reason to be re-proven).
_REASON_PARTIAL_FILL = "partial_fill"

_VALID_FILL_SIDES = frozenset(side.value for side in PaperOrderSide)
_VALID_FILL_INTENT_TYPES = frozenset(intent_type.value for intent_type in PaperOrderIntentType)


class PaperPositionStateError(RuntimeError):
    """Raised when position/transition inputs are wrong-typed/malformed/forged or fail re-proof."""


class PaperPositionStateSide(str, Enum):
    """Signed paper position side. Descriptor only — never a live position."""

    FLAT = "FLAT"
    LONG = "LONG"
    SHORT = "SHORT"


class PaperPositionTransitionStatus(str, Enum):
    """Paper position transition outcome. Never a live position / capital / execution action."""

    APPLIED = "APPLIED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperPositionState:
    """Deterministic, immutable signed paper position state for one market symbol. PAPER ONLY.

    Tracks signed/effective units and weighted average entry only — no PnL, no capital/balances. The
    negative attestations are always False; ``live_position_mutated`` is always False.
    """

    schema_version: str
    position_state_id: str
    market_symbol: str
    side: PaperPositionStateSide
    signed_units: str
    abs_units: str
    average_entry_price: str | None
    last_fill_simulation_digest: str | None
    transition_count: int
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    position_state_digest: str
    paper_only: bool = True
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
    connector_invoked: bool = False
    pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False


@dataclass(frozen=True)
class PaperPositionTransitionResult:
    """Deterministic, immutable digest-bound paper position transition record. PAPER ONLY.

    Binds the prior state, the applied fill, and (when APPLIED) the new state by digest. Never a live
    position / capital / execution action. The negative attestations are always False.
    """

    schema_version: str
    transition_id: str
    status: PaperPositionTransitionStatus
    prior_position_state_digest: str
    fill_simulation_result_digest: str
    new_position_state_digest: str | None
    market_symbol: str
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    transition_digest: str
    paper_only: bool = True
    paper_position_state_updated: bool = False
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
    connector_invoked: bool = False
    pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False


def _canonical_digest(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _is_non_empty_string(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_hex64_string(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(char in "0123456789abcdef" for char in value)


def _sorted_unique(reasons: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(sorted({reason for reason in reasons if isinstance(reason, str) and reason}))


def _is_sorted_unique_reasons(reasons: object) -> bool:
    """True iff ``reasons`` is a tuple of non-empty strings already in sorted, de-duplicated order."""
    if not isinstance(reasons, tuple):
        return False
    if not all(isinstance(reason, str) and reason != "" for reason in reasons):
        return False
    return list(reasons) == sorted(set(reasons))


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
    """Render an exact ``Decimal`` as a canonical plain-decimal string (context-independent).

    Uses ``format(…, "f")`` (exact fixed-point, never rounds to context precision, never scientific)
    plus manual trailing-zero stripping; signed/empty zero is pinned to ``"0"``. Never ``normalize()``.
    """
    rendered = format(value, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"", "-0"} else rendered


def _canonical_decimal(value: object) -> Decimal | None:
    """Parse a strict decimal string that is ALSO already in canonical render form, else ``None``.

    Rejects malformed *and* noncanonical strings (trailing zeros, ``-0``, redundant scale, scientific
    form) by requiring a ``_parse_decimal`` + ``_render_decimal`` round-trip fixpoint — exactly the
    canonical economics representation the fill simulator emits — so a forged fill cannot smuggle a
    noncanonical/negative-zero numeric field past digest re-proof.
    """
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _decimal_span(value: Decimal) -> int:
    """Positional span of an exact Decimal: significant digits PLUS the magnitude implied by the exponent.

    ``len(as_tuple().digits)`` counts only significant digits, never the exponent gap, so a value such as
    ``1e-100`` (one significant digit) would be sized as width 1 while it actually spans 101 fixed-point
    places. Summing this span keeps the working precision wide enough that products/sums over high-scale
    (many leading/trailing zero) inputs stay exact instead of being silently context-rounded.
    """
    tup = value.as_tuple()
    return len(tup.digits) + abs(int(tup.exponent))


def _arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal precision wide enough that every exact product/sum over the inputs is exact."""
    span = sum(_decimal_span(value) for value in operands)
    return max(28, span + 40)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperPositionStateError("paper_position_state:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperPositionStateError("paper_position_state:metadata_malformed")
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
# Position state construction
# --------------------------------------------------------------------------------------------------


def _state_payload(
    *,
    schema_version: str,
    position_state_id: str,
    market_symbol: str,
    side_value: str,
    signed_units: str,
    abs_units: str,
    average_entry_price: str | None,
    last_fill_simulation_digest: str | None,
    transition_count: int,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    live_position_mutated: bool,
    real_money_enabled: bool,
    real_orders_enabled: bool,
    order_routed: bool,
    venue_order_id_created: bool,
    exchange_order_id_created: bool,
    client_order_id_created: bool,
    route_id_created: bool,
    execution_instruction_created: bool,
    live_api_called: bool,
    scheduler_enabled: bool,
    connector_invoked: bool,
    pnl_computed: bool,
    capital_reserved: bool,
    capital_mutated: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "position_state_id": position_state_id,
        "market_symbol": market_symbol,
        "side": side_value,
        "signed_units": signed_units,
        "abs_units": abs_units,
        "average_entry_price": average_entry_price,
        "last_fill_simulation_digest": last_fill_simulation_digest,
        "transition_count": transition_count,
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "live_position_mutated": live_position_mutated,
        "real_money_enabled": real_money_enabled,
        "real_orders_enabled": real_orders_enabled,
        "order_routed": order_routed,
        "venue_order_id_created": venue_order_id_created,
        "exchange_order_id_created": exchange_order_id_created,
        "client_order_id_created": client_order_id_created,
        "route_id_created": route_id_created,
        "execution_instruction_created": execution_instruction_created,
        "live_api_called": live_api_called,
        "scheduler_enabled": scheduler_enabled,
        "connector_invoked": connector_invoked,
        "pnl_computed": pnl_computed,
        "capital_reserved": capital_reserved,
        "capital_mutated": capital_mutated,
    }


def build_paper_position_state(
    *,
    position_state_id: str,
    market_symbol: str,
    side: PaperPositionStateSide,
    signed_units: str,
    abs_units: str,
    average_entry_price: str | None,
    last_fill_simulation_digest: str | None = None,
    transition_count: int,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperPositionState:
    """Build a deterministic, immutable signed paper position state with a canonical digest.

    ``side``/``signed_units``/``abs_units``/``average_entry_price`` must be mutually consistent:
    FLAT ⇔ signed==0 ∧ abs==0 ∧ avg is None; LONG ⇔ signed>0 ∧ abs==signed ∧ avg>0; SHORT ⇔ signed<0 ∧
    abs==|signed| ∧ avg>0. Decimal strings are strict; ``transition_count`` a non-negative ``int``;
    ``last_fill_simulation_digest`` a 64-hex string or None. A malformed/inconsistent/forbidden field
    raises ``PaperPositionStateError``. PAPER ONLY — no PnL, no capital.
    """
    if not _is_non_empty_string(position_state_id):
        raise PaperPositionStateError("paper_position_state:position_state_id_invalid")
    if not _is_non_empty_string(market_symbol):
        raise PaperPositionStateError("paper_position_state:market_symbol_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperPositionStateError("paper_position_state:correlation_id_invalid")
    if not isinstance(side, PaperPositionStateSide):
        raise PaperPositionStateError("paper_position_state:side_invalid")
    if not _is_int(transition_count) or transition_count < 0:
        raise PaperPositionStateError("paper_position_state:transition_count_invalid")
    if last_fill_simulation_digest is not None and not _is_hex64_string(last_fill_simulation_digest):
        raise PaperPositionStateError("paper_position_state:last_fill_simulation_digest_invalid")

    signed = _parse_decimal(signed_units)
    if signed is None:
        raise PaperPositionStateError("paper_position_state:signed_units_not_decimal_string")
    abs_value = _parse_decimal(abs_units)
    if abs_value is None or abs_value < 0:
        raise PaperPositionStateError("paper_position_state:abs_units_invalid")
    if signed.copy_abs() != abs_value:  # copy_abs: context-independent, never rounds high precision
        raise PaperPositionStateError("paper_position_state:abs_units_inconsistent")

    average: Decimal | None = None
    if average_entry_price is not None:
        average = _parse_decimal(average_entry_price)
        if average is None or not average > 0:
            raise PaperPositionStateError("paper_position_state:average_entry_price_invalid")

    if side is PaperPositionStateSide.FLAT:
        if signed != 0 or abs_value != 0 or average is not None:
            raise PaperPositionStateError("paper_position_state:flat_state_inconsistent")
    elif side is PaperPositionStateSide.LONG:
        if not signed > 0 or average is None:
            raise PaperPositionStateError("paper_position_state:long_state_inconsistent")
    else:  # SHORT
        if not signed < 0 or average is None:
            raise PaperPositionStateError("paper_position_state:short_state_inconsistent")

    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(position_state_id, market_symbol, correlation_id, *_metadata_texts(metadata_pairs)):
        raise PaperPositionStateError("paper_position_state:scope_violation")

    canonical_signed = _render_decimal(signed)
    canonical_abs = _render_decimal(abs_value)
    canonical_avg = _render_decimal(average) if average is not None else None
    payload = _state_payload(
        schema_version=_STATE_SCHEMA_VERSION,
        position_state_id=position_state_id,
        market_symbol=market_symbol,
        side_value=side.value,
        signed_units=canonical_signed,
        abs_units=canonical_abs,
        average_entry_price=canonical_avg,
        last_fill_simulation_digest=last_fill_simulation_digest,
        transition_count=transition_count,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        paper_only=True,
        live_position_mutated=False,
        real_money_enabled=False,
        real_orders_enabled=False,
        order_routed=False,
        venue_order_id_created=False,
        exchange_order_id_created=False,
        client_order_id_created=False,
        route_id_created=False,
        execution_instruction_created=False,
        live_api_called=False,
        scheduler_enabled=False,
        connector_invoked=False,
        pnl_computed=False,
        capital_reserved=False,
        capital_mutated=False,
    )
    return PaperPositionState(
        schema_version=_STATE_SCHEMA_VERSION,
        position_state_id=position_state_id,
        market_symbol=market_symbol,
        side=side,
        signed_units=canonical_signed,
        abs_units=canonical_abs,
        average_entry_price=canonical_avg,
        last_fill_simulation_digest=last_fill_simulation_digest,
        transition_count=transition_count,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        position_state_digest=_canonical_digest(payload),
    )


def build_flat_paper_position_state(
    *,
    position_state_id: str,
    market_symbol: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperPositionState:
    """Build a deterministic FLAT paper position state (signed/abs 0, no average, transition_count 0)."""
    return build_paper_position_state(
        position_state_id=position_state_id,
        market_symbol=market_symbol,
        side=PaperPositionStateSide.FLAT,
        signed_units="0",
        abs_units="0",
        average_entry_price=None,
        last_fill_simulation_digest=None,
        transition_count=0,
        correlation_id=correlation_id,
        metadata=metadata,
    )


def paper_position_state_to_dict(state: PaperPositionState) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a position state (deterministic shape, includes self-digest)."""
    payload = _state_payload_from(state)
    payload["position_state_digest"] = state.position_state_digest
    return payload


def _state_payload_from(state: PaperPositionState) -> dict[str, object]:
    return _state_payload(
        schema_version=state.schema_version,
        position_state_id=state.position_state_id,
        market_symbol=state.market_symbol,
        side_value=state.side.value if isinstance(state.side, PaperPositionStateSide) else str(state.side),
        signed_units=state.signed_units,
        abs_units=state.abs_units,
        average_entry_price=state.average_entry_price,
        last_fill_simulation_digest=state.last_fill_simulation_digest,
        transition_count=state.transition_count,
        correlation_id=state.correlation_id,
        metadata=state.metadata,
        paper_only=state.paper_only,
        live_position_mutated=state.live_position_mutated,
        real_money_enabled=state.real_money_enabled,
        real_orders_enabled=state.real_orders_enabled,
        order_routed=state.order_routed,
        venue_order_id_created=state.venue_order_id_created,
        exchange_order_id_created=state.exchange_order_id_created,
        client_order_id_created=state.client_order_id_created,
        route_id_created=state.route_id_created,
        execution_instruction_created=state.execution_instruction_created,
        live_api_called=state.live_api_called,
        scheduler_enabled=state.scheduler_enabled,
        connector_invoked=state.connector_invoked,
        pnl_computed=state.pnl_computed,
        capital_reserved=state.capital_reserved,
        capital_mutated=state.capital_mutated,
    )


def paper_position_state_digest(state: PaperPositionState) -> str:
    """Recompute the canonical position-state digest from the serializer output, excluding self-digest."""
    return _canonical_digest(_state_payload_from(state))


# --------------------------------------------------------------------------------------------------
# Re-proof
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


def _reprove_prior_state(state: PaperPositionState) -> tuple[Decimal, Decimal | None]:
    """Re-prove a digest-valid prior state's structure/safety; return (signed_units, average)."""
    if state.schema_version != _STATE_SCHEMA_VERSION:
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if not isinstance(state.side, PaperPositionStateSide):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if not _state_is_paper_safe(state):
        raise PaperPositionStateError("paper_position_state:prior_state_unsafe_flags")
    if not _is_non_empty_string(state.position_state_id) or not _is_non_empty_string(state.correlation_id):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if not _is_non_empty_string(state.market_symbol):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if state.last_fill_simulation_digest is not None and not _is_hex64_string(state.last_fill_simulation_digest):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if not _is_int(state.transition_count) or state.transition_count < 0:
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    signed = _parse_decimal(state.signed_units)
    abs_value = _parse_decimal(state.abs_units)
    if signed is None or abs_value is None or abs_value < 0 or signed.copy_abs() != abs_value:
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    average: Decimal | None = None
    if state.average_entry_price is not None:
        average = _parse_decimal(state.average_entry_price)
        if average is None or not average > 0:
            raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if state.side is PaperPositionStateSide.FLAT:
        if signed != 0 or abs_value != 0 or average is not None:
            raise PaperPositionStateError("paper_position_state:prior_state_inconsistent")
    elif state.side is PaperPositionStateSide.LONG:
        if not signed > 0 or average is None:
            raise PaperPositionStateError("paper_position_state:prior_state_inconsistent")
    else:
        if not signed < 0 or average is None:
            raise PaperPositionStateError("paper_position_state:prior_state_inconsistent")
    if not _is_metadata_tuple(state.metadata):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if _has_scope_violation(
        state.position_state_id, state.market_symbol, state.correlation_id, *_metadata_texts(state.metadata)
    ):
        raise PaperPositionStateError("paper_position_state:prior_state_scope_violation")
    return signed, average


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


def _reprove_fill_result(fill: PaperFillSimulationResult) -> tuple[PaperFillSimulationStatus, str, Decimal, Decimal]:
    """Re-prove a digest-valid fill result's FULL structure/economics/safety; return (status, side, filled, price).

    Digest equality is necessary but NOT sufficient: a self-consistent forged result (digest recomputed
    over a tampered payload) must still fail if any structural or economic invariant the fill simulator
    promises is violated, otherwise it could drive an ``APPLIED`` position transition off malformed
    numbers. So after the identity checks every economics field is re-proven canonical and the
    status/economics/reason-code triad is re-proven against the upstream contract for *all* statuses.

    ``filled``/``price`` are meaningful only for FILLED/PARTIALLY_FILLED (proven positive there); for
    REJECTED they are returned as zero and the caller short-circuits with no position application.
    """
    if fill.schema_version != _EXPECTED_FILL_SCHEMA_VERSION:
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if not isinstance(fill.status, PaperFillSimulationStatus):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if not _fill_is_paper_safe(fill):
        raise PaperPositionStateError("paper_position_state:fill_result_unsafe_flags")
    if not _is_non_empty_string(fill.fill_simulation_id):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if not _is_non_empty_string(fill.market_symbol) or not _is_non_empty_string(fill.correlation_id):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if fill.side not in _VALID_FILL_SIDES or fill.intent_type not in _VALID_FILL_INTENT_TYPES:
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if not (
        _is_hex64_string(fill.intent_digest)
        and _is_hex64_string(fill.market_snapshot_digest)
        and _is_hex64_string(fill.fill_policy_digest)
    ):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if not _is_metadata_tuple(fill.metadata):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if _has_scope_violation(
        fill.fill_simulation_id, fill.market_symbol, fill.correlation_id, *_metadata_texts(fill.metadata)
    ):
        raise PaperPositionStateError("paper_position_state:fill_result_scope_violation")
    if not _is_sorted_unique_reasons(fill.reason_codes):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")

    # Economics: every field a strict, canonical decimal string; the magnitudes are never negative.
    fill_price = _canonical_decimal(fill.fill_price)
    filled = _canonical_decimal(fill.filled_units)
    unfilled = _canonical_decimal(fill.unfilled_units)
    gross = _canonical_decimal(fill.gross_notional)
    fee = _canonical_decimal(fill.fee_amount)
    if fill_price is None or filled is None or unfilled is None or gross is None or fee is None:
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")
    if filled < 0 or unfilled < 0 or gross < 0 or fee < 0:
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")

    zero = Decimal(0)
    if fill.status is PaperFillSimulationStatus.REJECTED:
        # A genuine rejection carries zero economics and at least one sorted/unique reason; no application.
        if filled != 0 or gross != 0 or fee != 0:
            raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
        if fill.reason_codes == ():
            raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
        return fill.status, fill.side, zero, zero

    # FILLED / PARTIALLY_FILLED: positive filled units, fill price, and gross notional.
    if not filled > 0 or not fill_price > 0 or not gross > 0:
        raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
    if fill.status is PaperFillSimulationStatus.FILLED:
        if unfilled != 0 or fill.reason_codes != ():
            raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
    else:  # PARTIALLY_FILLED
        if not unfilled > 0 or fill.reason_codes != (_REASON_PARTIAL_FILL,):
            raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
    # Economic integrity: gross_notional must be the EXACT product filled_units * fill_price (the fill
    # simulator's own invariant: ``gross = candidate * fill_price``). Digest validity proves identity,
    # not economics: a self-consistent forged result with an impossible gross (e.g. filled=1, price=100,
    # gross=1) would otherwise drive an APPLIED position transition off fabricated numbers. Computed under
    # a span-aware context so the product is exact (never default-context rounded); a mismatch fails closed.
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision((filled, fill_price))
        if filled * fill_price != gross:
            raise PaperPositionStateError("paper_position_state:fill_result_inconsistent")
    return fill.status, fill.side, filled, fill_price


# --------------------------------------------------------------------------------------------------
# Transition
# --------------------------------------------------------------------------------------------------


def _compute_new_position(
    *, q0: Decimal, avg0: Decimal | None, side: str, filled: Decimal, price: Decimal
) -> tuple[PaperPositionStateSide, Decimal, Decimal, Decimal | None]:
    """Pure exact position transition. Returns (new_side, signed_units, abs_units, average_or_none)."""
    # copy_negate (not unary ``-``) so the SELL sign flip is context-independent: unary minus rounds to
    # the active context precision and would silently truncate a high-precision filled-units tail.
    delta = filled if side == PaperOrderSide.BUY.value else filled.copy_negate()
    operands = (q0, filled, price, avg0 if avg0 is not None else Decimal(0))
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(operands)
        q1 = q0 + delta
        if q0 == 0:
            average: Decimal | None = price
        elif (q0 > 0) == (delta > 0):  # same sign — adding to the position
            numerator = q0.copy_abs() * avg0 + delta.copy_abs() * price  # avg0 present for a non-flat prior
            with localcontext() as div_ctx:
                div_ctx.prec = _WEIGHTED_AVERAGE_PRECISION
                div_ctx.rounding = ROUND_HALF_EVEN
                average = numerator / q1.copy_abs()
        elif delta.copy_abs() < q0.copy_abs():  # opposite sign — reduce without crossing
            average = avg0
        elif delta.copy_abs() == q0.copy_abs():  # opposite sign — close exactly to flat
            average = None
        else:  # opposite sign — cross through zero; residual opened at the fill price
            average = price
        abs_units = q1.copy_abs()

    if q1 == 0:
        return PaperPositionStateSide.FLAT, Decimal(0), Decimal(0), None
    if q1 > 0:
        return PaperPositionStateSide.LONG, q1, abs_units, average
    return PaperPositionStateSide.SHORT, q1, abs_units, average


def apply_paper_fill_to_position(
    prior_state: PaperPositionState,
    fill_result: PaperFillSimulationResult,
    *,
    transition_id: str,
    new_position_state_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> tuple[PaperPositionTransitionResult, PaperPositionState | None]:
    """Apply a FILLED/PARTIALLY_FILLED fill to a prior position state; return (transition, new_state).

    The ``prior_state`` and ``fill_result`` are re-proven via their PUBLIC digests (mismatch raises) and
    structurally re-proven (paper-safe, well-formed, token-clean). The market symbol must match. A
    ``REJECTED`` fill yields ``(REJECTED transition[fill_not_applied], None)``. A FILLED/PARTIALLY_FILLED
    fill applies signed units (BUY=+filled, SELL=-filled) with exact position arithmetic and emits a new
    digest-bound state (``transition_count`` += 1). Trading fields are copied from the fill; the caller
    supplies only ids/correlation/metadata. No PnL, no capital reservation/mutation, no order routing,
    no venue/order id, no live API; inputs are never mutated.
    """
    if not _is_non_empty_string(transition_id):
        raise PaperPositionStateError("paper_position_state:transition_id_invalid")
    if not _is_non_empty_string(new_position_state_id):
        raise PaperPositionStateError("paper_position_state:new_position_state_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperPositionStateError("paper_position_state:correlation_id_invalid")
    transition_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(
        transition_id, new_position_state_id, correlation_id, *_metadata_texts(transition_metadata)
    ):
        raise PaperPositionStateError("paper_position_state:scope_violation")
    if not isinstance(prior_state, PaperPositionState):
        raise PaperPositionStateError("paper_position_state:prior_state_malformed")
    if not isinstance(fill_result, PaperFillSimulationResult):
        raise PaperPositionStateError("paper_position_state:fill_result_malformed")

    # Digest boundaries: re-prove both upstream self-digests via their PUBLIC serializers.
    try:
        expected_prior_digest = paper_position_state_digest(prior_state)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperPositionStateError("paper_position_state:prior_state_malformed") from exc
    if not isinstance(prior_state.position_state_digest, str) or prior_state.position_state_digest != (
        expected_prior_digest
    ):
        raise PaperPositionStateError("paper_position_state:prior_state_digest_mismatch")
    try:
        expected_fill_digest = paper_fill_simulation_result_digest(fill_result)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperPositionStateError("paper_position_state:fill_result_malformed") from exc
    if not isinstance(fill_result.result_digest, str) or fill_result.result_digest != expected_fill_digest:
        raise PaperPositionStateError("paper_position_state:fill_result_digest_mismatch")

    q0, avg0 = _reprove_prior_state(prior_state)
    status, side, filled, price = _reprove_fill_result(fill_result)

    if fill_result.market_symbol != prior_state.market_symbol:
        raise PaperPositionStateError("paper_position_state:symbol_mismatch")

    if status is PaperFillSimulationStatus.REJECTED:
        transition = _finalize_transition(
            status=PaperPositionTransitionStatus.REJECTED,
            transition_id=transition_id,
            prior_state=prior_state,
            fill_result=fill_result,
            new_position_state=None,
            reasons=(_REASON_FILL_NOT_APPLIED,),
            correlation_id=correlation_id,
            metadata=transition_metadata,
        )
        return transition, None

    new_side, signed_units, abs_units, average = _compute_new_position(
        q0=q0, avg0=avg0, side=side, filled=filled, price=price
    )
    new_state = build_paper_position_state(
        position_state_id=new_position_state_id,
        market_symbol=prior_state.market_symbol,
        side=new_side,
        signed_units=_render_decimal(signed_units),
        abs_units=_render_decimal(abs_units),
        average_entry_price=_render_decimal(average) if average is not None else None,
        last_fill_simulation_digest=fill_result.result_digest,
        transition_count=prior_state.transition_count + 1,
        correlation_id=correlation_id,
        metadata=metadata,
    )
    transition = _finalize_transition(
        status=PaperPositionTransitionStatus.APPLIED,
        transition_id=transition_id,
        prior_state=prior_state,
        fill_result=fill_result,
        new_position_state=new_state,
        reasons=(),
        correlation_id=correlation_id,
        metadata=transition_metadata,
    )
    return transition, new_state


def _finalize_transition(
    *,
    status: PaperPositionTransitionStatus,
    transition_id: str,
    prior_state: PaperPositionState,
    fill_result: PaperFillSimulationResult,
    new_position_state: PaperPositionState | None,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperPositionTransitionResult:
    applied = status is PaperPositionTransitionStatus.APPLIED
    new_digest = new_position_state.position_state_digest if new_position_state is not None else None
    transition = PaperPositionTransitionResult(
        schema_version=_TRANSITION_SCHEMA_VERSION,
        transition_id=transition_id,
        status=status,
        prior_position_state_digest=prior_state.position_state_digest,
        fill_simulation_result_digest=fill_result.result_digest,
        new_position_state_digest=new_digest,
        market_symbol=prior_state.market_symbol,
        reason_codes=_sorted_unique(reasons),
        correlation_id=correlation_id,
        metadata=metadata,
        transition_digest="",
        paper_position_state_updated=applied,
    )
    object_digest = paper_position_transition_result_digest(transition)
    return PaperPositionTransitionResult(
        schema_version=transition.schema_version,
        transition_id=transition.transition_id,
        status=transition.status,
        prior_position_state_digest=transition.prior_position_state_digest,
        fill_simulation_result_digest=transition.fill_simulation_result_digest,
        new_position_state_digest=transition.new_position_state_digest,
        market_symbol=transition.market_symbol,
        reason_codes=transition.reason_codes,
        correlation_id=transition.correlation_id,
        metadata=transition.metadata,
        transition_digest=object_digest,
        paper_position_state_updated=transition.paper_position_state_updated,
    )


def _transition_payload(
    *,
    schema_version: str,
    transition_id: str,
    status_value: str,
    prior_position_state_digest: str,
    fill_simulation_result_digest: str,
    new_position_state_digest: str | None,
    market_symbol: str,
    reason_codes: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    paper_position_state_updated: bool,
    live_position_mutated: bool,
    real_money_enabled: bool,
    real_orders_enabled: bool,
    order_routed: bool,
    venue_order_id_created: bool,
    exchange_order_id_created: bool,
    client_order_id_created: bool,
    route_id_created: bool,
    execution_instruction_created: bool,
    live_api_called: bool,
    scheduler_enabled: bool,
    connector_invoked: bool,
    pnl_computed: bool,
    capital_reserved: bool,
    capital_mutated: bool,
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "transition_id": transition_id,
        "status": status_value,
        "prior_position_state_digest": prior_position_state_digest,
        "fill_simulation_result_digest": fill_simulation_result_digest,
        "new_position_state_digest": new_position_state_digest,
        "market_symbol": market_symbol,
        "reason_codes": list(reason_codes),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "paper_position_state_updated": paper_position_state_updated,
        "live_position_mutated": live_position_mutated,
        "real_money_enabled": real_money_enabled,
        "real_orders_enabled": real_orders_enabled,
        "order_routed": order_routed,
        "venue_order_id_created": venue_order_id_created,
        "exchange_order_id_created": exchange_order_id_created,
        "client_order_id_created": client_order_id_created,
        "route_id_created": route_id_created,
        "execution_instruction_created": execution_instruction_created,
        "live_api_called": live_api_called,
        "scheduler_enabled": scheduler_enabled,
        "connector_invoked": connector_invoked,
        "pnl_computed": pnl_computed,
        "capital_reserved": capital_reserved,
        "capital_mutated": capital_mutated,
    }


def _transition_payload_from(transition: PaperPositionTransitionResult) -> dict[str, object]:
    return _transition_payload(
        schema_version=transition.schema_version,
        transition_id=transition.transition_id,
        status_value=transition.status.value,
        prior_position_state_digest=transition.prior_position_state_digest,
        fill_simulation_result_digest=transition.fill_simulation_result_digest,
        new_position_state_digest=transition.new_position_state_digest,
        market_symbol=transition.market_symbol,
        reason_codes=transition.reason_codes,
        correlation_id=transition.correlation_id,
        metadata=transition.metadata,
        paper_only=transition.paper_only,
        paper_position_state_updated=transition.paper_position_state_updated,
        live_position_mutated=transition.live_position_mutated,
        real_money_enabled=transition.real_money_enabled,
        real_orders_enabled=transition.real_orders_enabled,
        order_routed=transition.order_routed,
        venue_order_id_created=transition.venue_order_id_created,
        exchange_order_id_created=transition.exchange_order_id_created,
        client_order_id_created=transition.client_order_id_created,
        route_id_created=transition.route_id_created,
        execution_instruction_created=transition.execution_instruction_created,
        live_api_called=transition.live_api_called,
        scheduler_enabled=transition.scheduler_enabled,
        connector_invoked=transition.connector_invoked,
        pnl_computed=transition.pnl_computed,
        capital_reserved=transition.capital_reserved,
        capital_mutated=transition.capital_mutated,
    )


def paper_position_transition_result_to_dict(transition: PaperPositionTransitionResult) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a transition result (deterministic shape, includes self-digest)."""
    payload = _transition_payload_from(transition)
    payload["transition_digest"] = transition.transition_digest
    return payload


def paper_position_transition_result_digest(transition: PaperPositionTransitionResult) -> str:
    """Recompute the canonical transition digest from the serializer output, excluding the self-digest."""
    return _canonical_digest(_transition_payload_from(transition))


__all__ = [
    "PaperPositionState",
    "PaperPositionStateError",
    "PaperPositionStateSide",
    "PaperPositionTransitionResult",
    "PaperPositionTransitionStatus",
    "apply_paper_fill_to_position",
    "build_flat_paper_position_state",
    "build_paper_position_state",
    "paper_position_state_digest",
    "paper_position_state_to_dict",
    "paper_position_transition_result_digest",
    "paper_position_transition_result_to_dict",
]
