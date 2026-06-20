"""Paper session realized-PnL aggregate — deterministic, paper-only aggregate over provenance-reconstructed
session realized-PnL bridges.

A small, immutable, fail-closed *aggregate artifact* that binds an ordered sequence of session realized-PnL
*bridge provenance bundles* into one frozen, digest-bound ``PaperSessionRealizedPnlAggregate``. Each bundle
pairs a supplied ``PaperSessionRealizedPnlBridge`` with the exact inputs it was built from (a
``PaperSessionSequenceProvenance`` session bundle and the ordered ``PaperRealizedPnlRollupInput`` event
bundles). The aggregate does **not** compute fills, positions, transitions, per-fill realized PnL, or
session/bridge artifacts — it only re-proves provenance, orders, de-duplicates, counts, and **sums the
already-computed gross realized PnL / closed units** of those reconstructed bridges. It is gross only: it
applies no fees and computes no unrealized PnL, total PnL, equity, capital, margin, or balances; it
reserves/mutates no capital; routes no order; creates no venue/exchange/client order id / route id /
execution instruction; calls no live/private API; schedules nothing; runs no auto-loop; and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal surface,
no Deribit, no BIST.

Provenance re-proof (per bundle): the supplied bridge self-digest is re-proven via the PUBLIC
``paper_session_realized_pnl_bridge_digest``; then the canonical bridge is **reconstructed** from the
supplied session provenance + rollup bundles via the PUBLIC ``build_paper_session_realized_pnl_bridge``
(which transitively reconstructs the canonical session from its episode artifacts and the realized-PnL
rollup from its event bundles, re-proving every upstream digest), and the supplied bridge must equal the
reconstruction exactly (digest + full serialized payload). This rejects a coordinated *resealed* bridge
whose totals/counts are internally self-consistent but do not follow from its inputs, and transitively
rejects coordinated resealed sessions / realized events. All bridges must share one ``market_symbol``;
duplicate ``bridge_digest`` / ``bridge_id`` / ``session_sequence_digest`` is rejected, and a duplicate
``source_event_digest`` across bridges is rejected (the same realized event must never be summed twice);
caller order is preserved and bound.

SCOPE / membership boundary: each session bridge is provenance-reconstructed (its session context from
episode artifacts and its realized rollup from event bundles), but this aggregate does **not** prove that
each rolled-up realized event belongs to a specific episode of its session — a ``PaperEpisodeRunResult``
and a ``PaperRealizedPnlEvent`` share no identifier the chain can cross-check. Event-to-episode membership
is intentionally NOT claimed here (no false membership proof).
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_realized_pnl_rollup import PaperRealizedPnlRollupInput
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionRealizedPnlBridge,
    PaperSessionRealizedPnlBridgeError,
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
    paper_session_realized_pnl_bridge_digest,
    paper_session_realized_pnl_bridge_to_dict,
)

_AGGREGATE_SCHEMA_VERSION = "paper-session-realized-pnl-aggregate.v1"

# Deterministic upper bound on the number of aggregated session bridges (fail-closed; not a tuning knob).
_MAX_BRIDGE_COUNT = 10_000

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional fraction.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling realized-PnL modules (word-bounded). Market-data terms scrubbed first.
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


class PaperSessionRealizedPnlAggregateError(RuntimeError):
    """Raised when aggregate/bridge inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperSessionRealizedPnlAggregateStatus(str, Enum):
    """Deterministic paper session realized-PnL aggregate outcome. Never an execution / capital / live action."""

    COMPUTED = "COMPUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperSessionRealizedPnlAggregateInput:
    """One bridge provenance bundle: a session realized-PnL bridge plus the exact inputs it was built from.

    The aggregate reconstructs the canonical bridge from these inputs and requires the supplied ``bridge``
    to match exactly, so a coordinated resealed bridge (totals/counts self-consistent but not produced by
    these inputs) cannot enter the aggregation. PAPER ONLY.
    """

    bridge: PaperSessionRealizedPnlBridge
    session_input: PaperSessionSequenceProvenance
    rollup_entries: tuple[PaperRealizedPnlRollupInput, ...]


@dataclass(frozen=True)
class PaperSessionRealizedPnlAggregate:
    """Deterministic, immutable digest-bound aggregate over paper session realized-PnL bridges. Gross only.

    Sums the already-computed gross ``realized_pnl`` / ``closed_units`` and counts of an ordered,
    provenance-reconstructed sequence of session bridges. Never computes fills, positions, fees,
    unrealized/total PnL, equity, capital, margin, or balances. Does NOT assert per-episode membership
    (see module docstring). ``aggregate_computed`` is True; every hard-safety attestation is False and
    ``gross_only`` is True. PAPER ONLY.
    """

    schema_version: str
    aggregate_id: str
    status: PaperSessionRealizedPnlAggregateStatus
    market_symbol: str
    session_bridge_count: int
    session_sequence_digests: tuple[str, ...]
    bridge_digests: tuple[str, ...]
    rollup_digests: tuple[str, ...]
    source_event_digests: tuple[str, ...]
    episode_count_total: int
    event_count: int
    computed_event_count: int
    no_realized_event_count: int
    closed_units_total: str
    realized_pnl_total: str
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    aggregate_digest: str
    paper_only: bool = True
    aggregate_computed: bool = True
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

    Summing this span keeps the working precision wide enough that a running total that mixes
    normal-magnitude and tiny high-scale values stays exact instead of being silently context-rounded.
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
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:metadata_malformed")
        items.append((key, value))
    return tuple(sorted(items))


def _metadata_texts(metadata: tuple[tuple[str, str], ...]) -> tuple[str, ...]:
    return tuple(text for pair in metadata for text in pair)


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
# Bridge provenance re-proof
# --------------------------------------------------------------------------------------------------


def _reprove_entry(entry: PaperSessionRealizedPnlAggregateInput) -> PaperSessionRealizedPnlBridge:
    """Re-prove one bridge provenance bundle and return the canonical (reconstructed) bridge.

    The supplied bridge self-digest is verified, then the canonical bridge is reconstructed from the
    supplied session provenance + rollup bundles via the PUBLIC builder and required to match the supplied
    bridge exactly (digest + full serialized payload). A coordinated resealed bridge — totals/counts
    internally consistent but not the genuine result of the supplied inputs — fails closed here.
    """
    if not isinstance(entry, PaperSessionRealizedPnlAggregateInput):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:entry_malformed")
    bridge = entry.bridge
    if not isinstance(bridge, PaperSessionRealizedPnlBridge):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_malformed")

    # Digest boundary: the supplied bridge must be self-consistent (digest recomputed from its own payload).
    try:
        supplied_digest = paper_session_realized_pnl_bridge_digest(bridge)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:bridge_digest_mismatch"
        ) from exc
    if not isinstance(bridge.bridge_digest, str) or bridge.bridge_digest != supplied_digest:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_digest_mismatch")

    # Provenance: reconstruct the canonical bridge from the supplied session provenance + rollup bundles.
    # build_paper_session_realized_pnl_bridge transitively reconstructs the session (from its episode
    # artifacts) and the realized rollup (from its event bundles), re-proving every upstream digest; any
    # inconsistency raises.
    try:
        reconstructed = build_paper_session_realized_pnl_bridge(
            entry.session_input,
            entry.rollup_entries,
            bridge_id=bridge.bridge_id,
            correlation_id=bridge.correlation_id,
            metadata=dict(bridge.metadata),
        )
    except PaperSessionRealizedPnlBridgeError as exc:
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:bridge_not_reproducible"
        ) from exc

    # The supplied bridge must be EXACTLY the canonical reconstruction (digest + full serialized payload).
    if reconstructed.bridge_digest != bridge.bridge_digest or (
        paper_session_realized_pnl_bridge_to_dict(reconstructed) != paper_session_realized_pnl_bridge_to_dict(bridge)
    ):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent")
    return reconstructed


# --------------------------------------------------------------------------------------------------
# Aggregate construction
# --------------------------------------------------------------------------------------------------


def build_paper_session_realized_pnl_aggregate(
    entries: Sequence[PaperSessionRealizedPnlAggregateInput],
    *,
    aggregate_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperSessionRealizedPnlAggregate:
    """Build a deterministic, digest-bound aggregate over an ordered sequence of bridge provenance bundles.

    Each bundle's bridge is re-proven via the PUBLIC ``paper_session_realized_pnl_bridge_digest`` and
    reconstructed from its supplied session provenance + rollup bundles via the PUBLIC
    ``build_paper_session_realized_pnl_bridge`` (which transitively reconstructs the session and realized
    rollup); the supplied bridge must match the reconstruction exactly. All bridges must share one
    ``market_symbol`` and have unique ``bridge_digest`` / ``bridge_id`` / ``session_sequence_digest``;
    caller order is preserved and bound. The non-empty, bounded sequence's gross ``realized_pnl`` and
    ``closed_units`` totals (and counts) are summed exactly (span-aware ``Decimal``; gross only — no fees,
    no unrealized/total PnL, no equity/capital/margin/balance). Wrong-typed/malformed/forged/coordinated-
    resealed inputs raise ``PaperSessionRealizedPnlAggregateError``; inputs are never mutated; no order
    routing, no live API, no scheduler/auto-loop, no connector/readiness transition.
    """
    if not _is_non_empty_string(aggregate_id):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:aggregate_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:correlation_id_invalid")
    aggregate_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(aggregate_id, correlation_id, *_metadata_texts(aggregate_metadata)):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:scope_violation")
    if isinstance(entries, (str, bytes)) or not isinstance(entries, Sequence):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:entries_malformed")
    entry_tuple = tuple(entries)
    if not entry_tuple:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:entries_empty")
    if len(entry_tuple) > _MAX_BRIDGE_COUNT:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_count_exceeds_max")

    market_symbol: str | None = None
    bridge_digests: list[str] = []
    bridge_ids: list[str] = []
    session_digests: list[str] = []
    rollup_digests: list[str] = []
    source_event_digests: list[str] = []
    closed_values: list[Decimal] = []
    realized_values: list[Decimal] = []
    episode_count_total = 0
    event_count = 0
    computed_event_count = 0
    no_realized_event_count = 0

    for entry in entry_tuple:
        bridge = _reprove_entry(entry)

        if market_symbol is None:
            market_symbol = bridge.market_symbol
        elif bridge.market_symbol != market_symbol:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:market_symbol_mismatch")

        closed = _canonical_decimal(bridge.closed_units_total)
        realized = _canonical_decimal(bridge.realized_pnl_total)
        if closed is None or realized is None or closed < 0:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_malformed")

        bridge_digests.append(bridge.bridge_digest)
        bridge_ids.append(bridge.bridge_id)
        session_digests.append(bridge.session_sequence_digest)
        rollup_digests.append(bridge.rollup_digest)
        source_event_digests.extend(bridge.source_event_digests)
        closed_values.append(closed)
        realized_values.append(realized)
        episode_count_total += bridge.episode_count
        event_count += bridge.event_count
        computed_event_count += bridge.computed_event_count
        no_realized_event_count += bridge.no_realized_event_count

    if len(set(bridge_digests)) != len(bridge_digests):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:duplicate_bridge_digest")
    if len(set(bridge_ids)) != len(bridge_ids):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:duplicate_bridge_id")
    if len(set(session_digests)) != len(session_digests):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_session_sequence_digest"
        )
    # A realized event proves a unique closed/realized economic action; the SAME event digest appearing in
    # two bridges (even with distinct bridge_id / session_sequence_digest) would double-count its realized
    # PnL / closed units in the totals. Reject any duplicate source event digest across all bridges.
    if len(set(source_event_digests)) != len(source_event_digests):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_source_event_digest"
        )

    operands = tuple(closed_values) + tuple(realized_values)
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(operands)
        closed_total = Decimal(0)
        for value in closed_values:
            closed_total = closed_total + value
        realized_total = Decimal(0)
        for value in realized_values:
            realized_total = realized_total + value
        closed_total_str = _render_decimal(closed_total)
        realized_total_str = _render_decimal(realized_total)

    assert market_symbol is not None  # noqa: S101 - guaranteed non-empty by the loop above
    return _finalize_aggregate(
        aggregate_id=aggregate_id,
        market_symbol=market_symbol,
        session_bridge_count=len(entry_tuple),
        session_sequence_digests=tuple(session_digests),
        bridge_digests=tuple(bridge_digests),
        rollup_digests=tuple(rollup_digests),
        source_event_digests=tuple(source_event_digests),
        episode_count_total=episode_count_total,
        event_count=event_count,
        computed_event_count=computed_event_count,
        no_realized_event_count=no_realized_event_count,
        closed_units_total=closed_total_str,
        realized_pnl_total=realized_total_str,
        correlation_id=correlation_id,
        metadata=aggregate_metadata,
    )


def _finalize_aggregate(
    *,
    aggregate_id: str,
    market_symbol: str,
    session_bridge_count: int,
    session_sequence_digests: tuple[str, ...],
    bridge_digests: tuple[str, ...],
    rollup_digests: tuple[str, ...],
    source_event_digests: tuple[str, ...],
    episode_count_total: int,
    event_count: int,
    computed_event_count: int,
    no_realized_event_count: int,
    closed_units_total: str,
    realized_pnl_total: str,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperSessionRealizedPnlAggregate:
    fields: dict[str, object] = {
        "schema_version": _AGGREGATE_SCHEMA_VERSION,
        "aggregate_id": aggregate_id,
        "status": PaperSessionRealizedPnlAggregateStatus.COMPUTED,
        "market_symbol": market_symbol,
        "session_bridge_count": session_bridge_count,
        "session_sequence_digests": session_sequence_digests,
        "bridge_digests": bridge_digests,
        "rollup_digests": rollup_digests,
        "source_event_digests": source_event_digests,
        "episode_count_total": episode_count_total,
        "event_count": event_count,
        "computed_event_count": computed_event_count,
        "no_realized_event_count": no_realized_event_count,
        "closed_units_total": closed_units_total,
        "realized_pnl_total": realized_pnl_total,
        "reason_codes": (),
        "correlation_id": correlation_id,
        "metadata": metadata,
    }
    seed = PaperSessionRealizedPnlAggregate(aggregate_digest="", **fields)  # type: ignore[arg-type]
    return _replace_digest(seed, paper_session_realized_pnl_aggregate_digest(seed))


def _replace_digest(aggregate: PaperSessionRealizedPnlAggregate, digest: str) -> PaperSessionRealizedPnlAggregate:
    fields = _aggregate_fields(aggregate)
    fields["aggregate_digest"] = digest
    return PaperSessionRealizedPnlAggregate(**fields)  # type: ignore[arg-type]


def _aggregate_fields(aggregate: PaperSessionRealizedPnlAggregate) -> dict[str, object]:
    return {
        "schema_version": aggregate.schema_version,
        "aggregate_id": aggregate.aggregate_id,
        "status": aggregate.status,
        "market_symbol": aggregate.market_symbol,
        "session_bridge_count": aggregate.session_bridge_count,
        "session_sequence_digests": aggregate.session_sequence_digests,
        "bridge_digests": aggregate.bridge_digests,
        "rollup_digests": aggregate.rollup_digests,
        "source_event_digests": aggregate.source_event_digests,
        "episode_count_total": aggregate.episode_count_total,
        "event_count": aggregate.event_count,
        "computed_event_count": aggregate.computed_event_count,
        "no_realized_event_count": aggregate.no_realized_event_count,
        "closed_units_total": aggregate.closed_units_total,
        "realized_pnl_total": aggregate.realized_pnl_total,
        "reason_codes": aggregate.reason_codes,
        "correlation_id": aggregate.correlation_id,
        "metadata": aggregate.metadata,
    }


def _aggregate_payload_from(aggregate: PaperSessionRealizedPnlAggregate) -> dict[str, object]:
    return {
        "schema_version": aggregate.schema_version,
        "aggregate_id": aggregate.aggregate_id,
        "status": aggregate.status.value,
        "market_symbol": aggregate.market_symbol,
        "session_bridge_count": aggregate.session_bridge_count,
        "session_sequence_digests": list(aggregate.session_sequence_digests),
        "bridge_digests": list(aggregate.bridge_digests),
        "rollup_digests": list(aggregate.rollup_digests),
        "source_event_digests": list(aggregate.source_event_digests),
        "episode_count_total": aggregate.episode_count_total,
        "event_count": aggregate.event_count,
        "computed_event_count": aggregate.computed_event_count,
        "no_realized_event_count": aggregate.no_realized_event_count,
        "closed_units_total": aggregate.closed_units_total,
        "realized_pnl_total": aggregate.realized_pnl_total,
        "reason_codes": list(aggregate.reason_codes),
        "correlation_id": aggregate.correlation_id,
        "metadata": [list(pair) for pair in aggregate.metadata],
        "paper_only": aggregate.paper_only,
        "aggregate_computed": aggregate.aggregate_computed,
        "gross_only": aggregate.gross_only,
        "fees_included": aggregate.fees_included,
        "unrealized_pnl_included": aggregate.unrealized_pnl_included,
        "total_pnl_computed": aggregate.total_pnl_computed,
        "equity_or_capital_computed": aggregate.equity_or_capital_computed,
        "capital_reserved": aggregate.capital_reserved,
        "capital_mutated": aggregate.capital_mutated,
        "balance_mutated": aggregate.balance_mutated,
        "live_position_mutated": aggregate.live_position_mutated,
        "real_money_enabled": aggregate.real_money_enabled,
        "real_orders_enabled": aggregate.real_orders_enabled,
        "order_routed": aggregate.order_routed,
        "venue_order_id_created": aggregate.venue_order_id_created,
        "exchange_order_id_created": aggregate.exchange_order_id_created,
        "client_order_id_created": aggregate.client_order_id_created,
        "route_id_created": aggregate.route_id_created,
        "execution_instruction_created": aggregate.execution_instruction_created,
        "live_api_called": aggregate.live_api_called,
        "scheduler_enabled": aggregate.scheduler_enabled,
        "auto_loop_enabled": aggregate.auto_loop_enabled,
        "connector_invoked": aggregate.connector_invoked,
    }


def paper_session_realized_pnl_aggregate_to_dict(aggregate: PaperSessionRealizedPnlAggregate) -> dict[str, object]:
    """Canonical, JSON-ready mapping for an aggregate (deterministic shape, includes self-digest)."""
    payload = _aggregate_payload_from(aggregate)
    payload["aggregate_digest"] = aggregate.aggregate_digest
    return payload


def paper_session_realized_pnl_aggregate_digest(aggregate: PaperSessionRealizedPnlAggregate) -> str:
    """Recompute the canonical aggregate digest from the serializer output, excluding the self-digest field."""
    return _canonical_digest(_aggregate_payload_from(aggregate))


__all__ = [
    "PaperSessionRealizedPnlAggregate",
    "PaperSessionRealizedPnlAggregateError",
    "PaperSessionRealizedPnlAggregateInput",
    "PaperSessionRealizedPnlAggregateStatus",
    "build_paper_session_realized_pnl_aggregate",
    "paper_session_realized_pnl_aggregate_digest",
    "paper_session_realized_pnl_aggregate_to_dict",
]
