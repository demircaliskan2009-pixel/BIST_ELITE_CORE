"""Paper realized-PnL rollup — deterministic, paper-only aggregation of realized-PnL events.

A small, immutable, fail-closed *rollup artifact* that binds an ordered sequence of already-produced
``PaperRealizedPnlEvent`` records into one frozen, digest-bound ``PaperRealizedPnlRollup``. It does
**not** compute fills, positions, transitions, or per-fill realized PnL — it only re-proves, orders,
de-duplicates, counts, and **sums the already-computed gross realized PnL** of existing realized-PnL
events. It is gross only: it applies no fees and computes no unrealized PnL, total PnL, equity, capital,
margin, or balances; it reserves/mutates no capital; routes no order; creates no venue/exchange/client
order id / route id / execution instruction; calls no live/private API; schedules nothing; runs no
auto-loop; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST.

Each input ``PaperRealizedPnlEvent`` is re-proven at the boundary via the PUBLIC
``paper_realized_pnl_event_digest`` (mismatch fails closed) and then structurally re-proven for rollup
consumption (schema, status enum, ids, paper-safe flags, gross-only attestations, status/reason/closed
consistency, canonical decimal values). Digest equality alone is not trusted: a self-consistent forged
event (digest recomputed over a tampered payload) is still rejected. All events must share one
``market_symbol``; duplicate ``realized_pnl_event_digest`` or ``realized_pnl_event_id`` is rejected; the
reserved ``REJECTED`` realized status (never emitted by the producer) is rejected fail-closed; caller
order is preserved exactly and bound into the rollup digest.

Rollup semantics: ``COMPUTED`` events add their exact gross ``realized_pnl`` and ``closed_units`` and
increment the computed count; ``NO_REALIZED_PNL`` events add zero (and must carry zero closed units /
zero realized PnL) and increment the no-realized count. Totals are summed under an input-derived,
positional-span-aware ``localcontext`` so high-scale leading-zero values stay exact (no float, no
``Decimal.normalize()``, no scientific notation, no negative zero); the canonical zero is ``"0"``.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_realized_pnl import (
    PaperRealizedPnlEvent,
    PaperRealizedPnlStatus,
    paper_realized_pnl_event_digest,
)

_ROLLUP_SCHEMA_VERSION = "paper-realized-pnl-rollup.v1"
_EXPECTED_EVENT_SCHEMA_VERSION = "paper-realized-pnl-event.v1"

_REASON_NO_CLOSED_UNITS = "no_closed_units"

# Deterministic upper bound on the number of rolled-up events (fail-closed; not a tuning knob).
_MAX_EVENT_COUNT = 10_000

_VALID_PRIOR_SIDES = frozenset({"FLAT", "LONG", "SHORT"})
_VALID_FILL_SIDES = frozenset({"BUY", "SELL"})

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling realized-PnL module (word-bounded) and rejects bare
# ``connector``/``route_id``/``execution_instruction``/``deribit``/``venue|exchange|client_order_id``
# tokens. Market-data terms are scrubbed before the scan.
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


class PaperRealizedPnlRollupError(RuntimeError):
    """Raised when rollup/event inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperRealizedPnlRollupStatus(str, Enum):
    """Deterministic paper realized-PnL rollup outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperRealizedPnlRollup:
    """Deterministic, immutable digest-bound rollup of paper realized-PnL events. Gross only. PAPER ONLY.

    Sums the already-computed gross ``realized_pnl`` and ``closed_units`` of an ordered, digest-bound
    sequence of ``PaperRealizedPnlEvent`` records and counts them by status. Never computes fills,
    positions, fees, unrealized/total PnL, equity, capital, margin, or balances. ``rollup_computed`` is
    True; every hard-safety attestation is False and ``gross_only`` is True.
    """

    schema_version: str
    rollup_id: str
    status: PaperRealizedPnlRollupStatus
    market_symbol: str
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    rejected_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    source_event_digests: tuple[str, ...]
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    rollup_digest: str
    paper_only: bool = True
    rollup_computed: bool = True
    gross_only: bool = True
    fees_included: bool = False
    unrealized_pnl_included: bool = False
    total_pnl_computed: bool = False
    equity_or_capital_computed: bool = False
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
    places. Summing this span keeps the working precision wide enough that a running realized-PnL sum that
    mixes normal-magnitude and tiny high-scale values stays exact instead of being silently rounded.
    """
    tup = value.as_tuple()
    return len(tup.digits) + abs(int(tup.exponent))


def _arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal precision wide enough that every exact sum over the inputs is exact (input-derived)."""
    span = sum(_decimal_span(value) for value in operands)
    return max(28, span + 40)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:metadata_malformed")
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
    if len(set(keys)) != len(keys):  # metadata is conceptually a mapping — duplicate keys are forged/ambiguous
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
# Event re-proof
# --------------------------------------------------------------------------------------------------


def _event_is_paper_safe(event: PaperRealizedPnlEvent) -> bool:
    return (
        event.paper_only is True
        and event.fees_included is False
        and event.unrealized_pnl_computed is False
        and event.total_pnl_computed is False
        and event.capital_reserved is False
        and event.capital_mutated is False
        and event.balance_mutated is False
        and event.live_position_mutated is False
        and event.real_money_enabled is False
        and event.real_orders_enabled is False
        and event.order_routed is False
        and event.venue_order_id_created is False
        and event.exchange_order_id_created is False
        and event.client_order_id_created is False
        and event.route_id_created is False
        and event.execution_instruction_created is False
        and event.live_api_called is False
        and event.scheduler_enabled is False
        and event.auto_loop_enabled is False
        and event.connector_invoked is False
    )


def _reprove_event(event: PaperRealizedPnlEvent) -> tuple[PaperRealizedPnlStatus, Decimal, Decimal]:
    """Re-prove a digest-valid realized-PnL event's structure/safety/consistency; return (status, realized, closed).

    A self-consistent forged event (digest recomputed over a tampered payload) must still fail here. The
    reserved ``REJECTED`` realized status is never emitted by the producer and is rejected fail-closed.
    """
    if event.schema_version != _EXPECTED_EVENT_SCHEMA_VERSION:
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if not isinstance(event.status, PaperRealizedPnlStatus):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if event.status not in (PaperRealizedPnlStatus.COMPUTED, PaperRealizedPnlStatus.NO_REALIZED_PNL):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_status_invalid")
    if not (
        _is_non_empty_string(event.realized_pnl_event_id)
        and _is_non_empty_string(event.market_symbol)
        and _is_non_empty_string(event.correlation_id)
    ):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if not _event_is_paper_safe(event):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_unsafe_flags")
    if event.fee_amount_applied is not None:  # gross only — no fee may be applied to a rolled-up event
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_inconsistent")
    if event.prior_side not in _VALID_PRIOR_SIDES or event.fill_side not in _VALID_FILL_SIDES:
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if not (
        _is_hex64_string(event.prior_position_state_digest)
        and _is_hex64_string(event.fill_simulation_result_digest)
        and _is_hex64_string(event.position_transition_digest)
        and _is_hex64_string(event.new_position_state_digest)
    ):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if not _is_metadata_tuple(event.metadata):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if not _is_sorted_unique_reasons(event.reason_codes):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
    if _has_scope_violation(
        event.realized_pnl_event_id, event.market_symbol, event.correlation_id, *_metadata_texts(event.metadata)
    ):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_scope_violation")

    realized = _canonical_decimal(event.realized_pnl)
    closed = _canonical_decimal(event.closed_units)
    if realized is None or closed is None or closed < 0:
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")

    if event.status is PaperRealizedPnlStatus.COMPUTED:
        if event.realized_pnl_computed is not True or event.reason_codes != ():
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_inconsistent")
        if not closed > 0:  # a COMPUTED event closed strictly positive units
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_inconsistent")
    else:  # NO_REALIZED_PNL
        if event.realized_pnl_computed is not False or event.reason_codes != (_REASON_NO_CLOSED_UNITS,):
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_inconsistent")
        if closed != 0 or realized != 0:  # nothing closed ⇒ exactly zero closed units and zero realized PnL
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_inconsistent")
    return event.status, realized, closed


# --------------------------------------------------------------------------------------------------
# Rollup construction
# --------------------------------------------------------------------------------------------------


def build_paper_realized_pnl_rollup(
    events: Sequence[PaperRealizedPnlEvent],
    *,
    rollup_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperRealizedPnlRollup:
    """Build a deterministic, immutable digest-bound rollup from an ordered sequence of realized-PnL events.

    Each event is re-proven via the PUBLIC ``paper_realized_pnl_event_digest`` (mismatch raises) and
    structurally re-proven for rollup consumption; all events must share one ``market_symbol`` and have
    unique ``realized_pnl_event_digest`` / ``realized_pnl_event_id``; caller order is preserved and bound.
    The non-empty, bounded sequence's gross ``realized_pnl`` and ``closed_units`` are summed exactly
    (span-aware ``Decimal``; gross only — no fees, no unrealized/total PnL, no equity/capital/margin/
    balance). Wrong-typed/malformed/forged inputs raise ``PaperRealizedPnlRollupError``; inputs are never
    mutated; no order routing, no live API, no scheduler/auto-loop, no connector/readiness transition.
    """
    if not _is_non_empty_string(rollup_id):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:rollup_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:correlation_id_invalid")
    rollup_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(rollup_id, correlation_id, *_metadata_texts(rollup_metadata)):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:scope_violation")
    if isinstance(events, (str, bytes)) or not isinstance(events, Sequence):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:events_malformed")
    event_tuple = tuple(events)
    if not event_tuple:
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:events_empty")
    if len(event_tuple) > _MAX_EVENT_COUNT:
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_count_exceeds_max")

    market_symbol: str | None = None
    digests: list[str] = []
    ids: list[str] = []
    realized_values: list[Decimal] = []
    closed_values: list[Decimal] = []
    computed = 0
    no_realized = 0

    for event in event_tuple:
        if not isinstance(event, PaperRealizedPnlEvent):
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_malformed")
        try:
            expected_digest = paper_realized_pnl_event_digest(event)
        except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
            # A non-serializable / forged event cannot produce a recomputable canonical digest, so its
            # stored digest cannot be proven equal — a digest-boundary rejection (mismatch), per the
            # AGENTS.md digest-boundary rule.
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_digest_mismatch") from exc
        if not isinstance(event.realized_pnl_event_digest, str) or event.realized_pnl_event_digest != expected_digest:
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:event_digest_mismatch")

        status, realized, closed = _reprove_event(event)

        if market_symbol is None:
            market_symbol = event.market_symbol
        elif event.market_symbol != market_symbol:
            raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:symbol_mismatch")

        digests.append(event.realized_pnl_event_digest)
        ids.append(event.realized_pnl_event_id)
        realized_values.append(realized)
        closed_values.append(closed)
        if status is PaperRealizedPnlStatus.COMPUTED:
            computed += 1
        else:  # NO_REALIZED_PNL (REJECTED already rejected by _reprove_event)
            no_realized += 1

    if len(set(digests)) != len(digests):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:duplicate_event_digest")
    if len(set(ids)) != len(ids):
        raise PaperRealizedPnlRollupError("paper_realized_pnl_rollup:duplicate_event_id")

    operands = tuple(realized_values) + tuple(closed_values)
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(operands)
        realized_total = Decimal(0)
        for value in realized_values:
            realized_total = realized_total + value
        closed_total = Decimal(0)
        for value in closed_values:
            closed_total = closed_total + value
        realized_total_str = _render_decimal(realized_total)
        closed_total_str = _render_decimal(closed_total)

    event_count = len(event_tuple)
    assert market_symbol is not None  # noqa: S101 - guaranteed non-empty by the loop above
    return _finalize_rollup(
        rollup_id=rollup_id,
        market_symbol=market_symbol,
        event_count=event_count,
        computed_event_count=computed,
        no_realized_event_count=no_realized,
        rejected_event_count=event_count - computed - no_realized,
        closed_units_total=closed_total_str,
        realized_pnl_total=realized_total_str,
        source_event_digests=tuple(digests),
        correlation_id=correlation_id,
        metadata=rollup_metadata,
    )


def _finalize_rollup(
    *,
    rollup_id: str,
    market_symbol: str,
    event_count: int,
    computed_event_count: int,
    no_realized_event_count: int,
    rejected_event_count: int,
    closed_units_total: str,
    realized_pnl_total: str,
    source_event_digests: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperRealizedPnlRollup:
    fields: dict[str, object] = {
        "schema_version": _ROLLUP_SCHEMA_VERSION,
        "rollup_id": rollup_id,
        "status": PaperRealizedPnlRollupStatus.COMPUTED,
        "market_symbol": market_symbol,
        "event_count": event_count,
        "computed_event_count": computed_event_count,
        "no_realized_event_count": no_realized_event_count,
        "rejected_event_count": rejected_event_count,
        "closed_units_total": closed_units_total,
        "realized_pnl_total": realized_pnl_total,
        "source_event_digests": source_event_digests,
        "reason_codes": (),
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperRealizedPnlRollup(rollup_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_realized_pnl_rollup_digest(seed))


def _replace_digest(rollup: PaperRealizedPnlRollup, digest: str) -> PaperRealizedPnlRollup:
    fields = _rollup_fields(rollup)
    fields["rollup_digest"] = digest
    return PaperRealizedPnlRollup(**fields)  # type: ignore[arg-type]


def _rollup_fields(rollup: PaperRealizedPnlRollup) -> dict[str, object]:
    return {
        "schema_version": rollup.schema_version,
        "rollup_id": rollup.rollup_id,
        "status": rollup.status,
        "market_symbol": rollup.market_symbol,
        "event_count": rollup.event_count,
        "computed_event_count": rollup.computed_event_count,
        "no_realized_event_count": rollup.no_realized_event_count,
        "rejected_event_count": rollup.rejected_event_count,
        "closed_units_total": rollup.closed_units_total,
        "realized_pnl_total": rollup.realized_pnl_total,
        "source_event_digests": rollup.source_event_digests,
        "reason_codes": rollup.reason_codes,
        "correlation_id": rollup.correlation_id,
        "metadata": rollup.metadata,
    }


def _rollup_payload_from(rollup: PaperRealizedPnlRollup) -> dict[str, object]:
    return {
        "schema_version": rollup.schema_version,
        "rollup_id": rollup.rollup_id,
        "status": rollup.status.value,
        "market_symbol": rollup.market_symbol,
        "event_count": rollup.event_count,
        "computed_event_count": rollup.computed_event_count,
        "no_realized_event_count": rollup.no_realized_event_count,
        "rejected_event_count": rollup.rejected_event_count,
        "closed_units_total": rollup.closed_units_total,
        "realized_pnl_total": rollup.realized_pnl_total,
        "source_event_digests": list(rollup.source_event_digests),
        "reason_codes": list(rollup.reason_codes),
        "correlation_id": rollup.correlation_id,
        "metadata": [list(pair) for pair in rollup.metadata],
        "paper_only": rollup.paper_only,
        "rollup_computed": rollup.rollup_computed,
        "gross_only": rollup.gross_only,
        "fees_included": rollup.fees_included,
        "unrealized_pnl_included": rollup.unrealized_pnl_included,
        "total_pnl_computed": rollup.total_pnl_computed,
        "equity_or_capital_computed": rollup.equity_or_capital_computed,
        "capital_reserved": rollup.capital_reserved,
        "capital_mutated": rollup.capital_mutated,
        "balance_mutated": rollup.balance_mutated,
        "live_position_mutated": rollup.live_position_mutated,
        "real_money_enabled": rollup.real_money_enabled,
        "real_orders_enabled": rollup.real_orders_enabled,
        "order_routed": rollup.order_routed,
        "venue_order_id_created": rollup.venue_order_id_created,
        "exchange_order_id_created": rollup.exchange_order_id_created,
        "client_order_id_created": rollup.client_order_id_created,
        "route_id_created": rollup.route_id_created,
        "execution_instruction_created": rollup.execution_instruction_created,
        "live_api_called": rollup.live_api_called,
        "scheduler_enabled": rollup.scheduler_enabled,
        "auto_loop_enabled": rollup.auto_loop_enabled,
        "connector_invoked": rollup.connector_invoked,
    }


def paper_realized_pnl_rollup_to_dict(rollup: PaperRealizedPnlRollup) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a realized-PnL rollup (deterministic shape, includes self-digest)."""
    payload = _rollup_payload_from(rollup)
    payload["rollup_digest"] = rollup.rollup_digest
    return payload


def paper_realized_pnl_rollup_digest(rollup: PaperRealizedPnlRollup) -> str:
    """Recompute the canonical rollup digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_rollup_payload_from(rollup))


__all__ = [
    "PaperRealizedPnlRollup",
    "PaperRealizedPnlRollupError",
    "PaperRealizedPnlRollupStatus",
    "build_paper_realized_pnl_rollup",
    "paper_realized_pnl_rollup_digest",
    "paper_realized_pnl_rollup_to_dict",
]
