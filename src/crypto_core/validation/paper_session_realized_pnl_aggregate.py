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

Single-read snapshots (two layers) + canonical primitives: each entry's ``rollup_entries`` is read EXACTLY
once into an immutable tuple, and each realized event in that tuple is serialized EXACTLY once (PUBLIC
``paper_realized_pnl_event_to_dict``) and then ROUND-TRIPPED through canonical JSON into a plain-primitive
payload (exact ``str``/builtins — no ``str`` subclass with custom hash/equality). Bridge reconstruction,
the recomputed-event-digest cross-check, AND action-identity extraction all read only those captured,
normalized snapshots — never the original Sequence or event objects again. So a stateful/mutable Sequence
cannot serve genuine bundles to reconstruction and fake identities to a later read; a stateful/adversarial
``PaperRealizedPnlEvent`` cannot return genuine attributes to the digest pass and fake identities to the
identity pass (digest and identity come from the same captured bytes); and a content-equal but
hash-divergent ``str`` subclass cannot slip a duplicate canonical action past set/tuple de-dup. The
realized economic action of every event (its event id, fill-simulation-result digest, position-transition
digest, and full prior/fill/transition/new-state identity tuple) is de-duplicated fail-closed across all
bridges so one real action is never summed twice.

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

from crypto_core.validation.paper_realized_pnl import paper_realized_pnl_event_to_dict
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
    fill_simulation_result_digests: tuple[str, ...]
    position_transition_digests: tuple[str, ...]
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


def _serialize_metadata(metadata: object) -> list[list[str]]:
    """Canonicalize aggregate metadata to a list of exact two-item ``[str, str]`` pairs, fail-closed.

    The dataclass field is ``tuple[tuple[str, str], ...]`` (the builder normalizes a ``Mapping`` to sorted
    unique-key pairs). A blind ``list(...)`` would LOSE data and let malformed containers masquerade as
    valid: ``{"li": "scheduler"}`` iterates to its key ``"li"`` and ``list("li")`` collapses to
    ``["l", "i"]`` (the hidden value is lost, and two different dicts collide on one snapshot/digest), while
    ``("ab",)`` collapses to ``["a", "b"]``. So the exact shape is enforced BEFORE canonicalization/digest: a
    ``tuple``/``list`` of exactly-two-item pairs whose key AND value are each an exact plain ``str``
    (``type() is str``), with unique keys. Anything else — dict/str/set, one-dimensional or wrong-length
    pairs, a non-string or nested dict/list/set key/value, or a duplicate key — raises
    ``PaperSessionRealizedPnlAggregateError`` (nested values are never stringified to be scanned).
    """
    if type(metadata) not in (tuple, list):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:metadata_malformed")
    pairs: list[list[str]] = []
    keys: list[str] = []
    for pair in metadata:
        if type(pair) not in (tuple, list) or len(pair) != 2 or type(pair[0]) is not str or type(pair[1]) is not str:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:metadata_malformed")
        keys.append(pair[0])
        pairs.append([pair[0], pair[1]])
    if len(set(keys)) != len(keys):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:metadata_malformed")
    return pairs


def _serialize_reason_codes(reason_codes: object) -> list[str]:
    """Canonicalize aggregate ``reason_codes`` fail-closed.

    The builder only ever emits a COMPUTED aggregate with ``reason_codes == ()``. A blind ``list(...)`` would
    collapse a lossy container — ``""``, ``{}``, ``set()`` all serialize to ``[]`` — into the valid empty
    state (a digest collision), and would also silently serialize a forged non-empty ``reason_codes``. So the
    exact canonical empty sequence is required: an empty ``tuple``/``list``. Any non-empty value (e.g.
    ``("scheduler",)``) or a non-tuple/list container raises ``PaperSessionRealizedPnlAggregateError``.
    """
    if type(reason_codes) not in (tuple, list) or len(reason_codes) != 0:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:reason_codes_malformed")
    return []


# --------------------------------------------------------------------------------------------------
# Bridge provenance re-proof
# --------------------------------------------------------------------------------------------------


def _snapshot_rollup_entries(
    entry: PaperSessionRealizedPnlAggregateInput,
) -> tuple[PaperRealizedPnlRollupInput, ...]:
    """Read ``entry.rollup_entries`` EXACTLY once and pin it to an immutable tuple.

    Materializing a single view defeats a stateful/mutable Sequence that would otherwise return genuine
    bundles to bridge reconstruction and adversarial (fake-identity) bundles to a later action-identity
    read — a TOCTOU double-read that could bypass economic-action dedup and double-count realized PnL.
    Contents are not validated here (the bridge reconstruction re-proves every bundle); only the container
    shape is guarded so a non-sequence fails closed with a typed error rather than an untyped exception.
    """
    raw = entry.rollup_entries
    if isinstance(raw, (str, bytes)) or not isinstance(raw, Sequence):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:rollup_entries_malformed")
    return tuple(raw)


def _reprove_entry(
    entry: PaperSessionRealizedPnlAggregateInput,
    rollup_entries_snapshot: tuple[PaperRealizedPnlRollupInput, ...],
) -> PaperSessionRealizedPnlBridge:
    """Re-prove one bridge provenance bundle against a single immutable rollup snapshot; return the
    canonical (reconstructed) bridge.

    ``rollup_entries_snapshot`` is the caller's one-and-only read of ``entry.rollup_entries`` — it (never
    ``entry.rollup_entries``) is fed to the PUBLIC builder, so a stateful/mutable Sequence cannot serve
    genuine bundles to reconstruction here and adversarial bundles to a later read. The supplied bridge
    self-digest is verified, then the canonical bridge is reconstructed from the supplied session
    provenance + that snapshot via the PUBLIC builder and required to match the supplied bridge exactly
    (digest + full serialized payload). A coordinated resealed bridge — totals/counts internally consistent
    but not the genuine result of the supplied inputs — fails closed here. The caller validates that
    ``entry`` is a ``PaperSessionRealizedPnlAggregateInput`` before taking the snapshot.
    """
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
            rollup_entries_snapshot,
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


# Event-identity fields the aggregate dedups on; all must be present in a captured event payload.
_EVENT_IDENTITY_KEYS = (
    "realized_pnl_event_id",
    "prior_position_state_digest",
    "fill_simulation_result_digest",
    "position_transition_digest",
    "new_position_state_digest",
)


def _capture_event_payload(event: object) -> dict[str, object]:
    """Serialize one realized event to an exact canonical plain-primitive payload EXACTLY once.

    The PUBLIC serializer is called a single time; the payload is then ROUND-TRIPPED through canonical JSON
    (``json.loads(json.dumps(...))`` with the same settings as ``_canonical_digest``) so every value becomes
    an exact plain builtin — a plain ``str``, never a ``str`` subclass with custom ``__hash__``/``__eq__`` or
    any other custom hash/equality object. This single normalized dict is the ONLY source for the recomputed
    digest AND every action-identity field, so neither a stateful event (which cannot then diverge digest
    from identity) nor a content-equal but hash-divergent ``str`` subclass (which cannot then slip past the
    set/tuple dedup) can double-count an action. Fails closed (typed error) on a serializer error, a
    non-mapping or non-canonical/non-serializable payload, or any identity field that is not an exact plain
    ``str``.
    """
    try:
        raw = paper_realized_pnl_event_to_dict(event)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent") from exc
    if not isinstance(raw, dict):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent")
    try:
        payload = json.loads(json.dumps(raw, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False))
    except (TypeError, ValueError) as exc:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent") from exc
    # Strict exact-primitive identity guard: every dedup/output identity field must be a plain ``str`` (not a
    # subclass), so set/tuple membership uses standard string hashing/equality.
    if not isinstance(payload, dict) or any(type(payload.get(key)) is not str for key in _EVENT_IDENTITY_KEYS):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent")
    return payload


def _recompute_event_digest(payload: dict[str, object]) -> str:
    """Recompute the canonical realized-event digest from a captured payload (no event-object read).

    Uses the SAME digest contract as the event module's PUBLIC ``paper_realized_pnl_event_digest``: SHA-256
    over the canonical JSON of the event payload EXCLUDING the self-digest field. Recomputing from the
    captured payload guarantees the exact bytes proven against the bridge digest are the bytes the identity
    fields are read from. Fails closed on a non-serializable payload.
    """
    digest_input = {key: value for key, value in payload.items() if key != "realized_pnl_event_digest"}
    try:
        return _canonical_digest(digest_input)
    except (TypeError, ValueError) as exc:
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent") from exc


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
    event_ids: list[str] = []
    fill_digests: list[str] = []
    transition_digests: list[str] = []
    action_keys: list[tuple[str, str, str, str | None]] = []
    closed_values: list[Decimal] = []
    realized_values: list[Decimal] = []
    episode_count_total = 0
    event_count = 0
    computed_event_count = 0
    no_realized_event_count = 0

    for entry in entry_tuple:
        if not isinstance(entry, PaperSessionRealizedPnlAggregateInput):
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:entry_malformed")
        # Single-snapshot rule: read entry.rollup_entries EXACTLY once into an immutable tuple and feed that
        # one snapshot to every consumer (bridge reconstruction, event-digest cross-check, and action-
        # identity extraction). entry.rollup_entries is never read again, so a stateful/mutable Sequence
        # cannot serve genuine bundles to reconstruction and adversarial (fake-identity) bundles to a later
        # read — closing the TOCTOU double-read that could bypass economic-action dedup and double-count.
        rollup_entries_snapshot = _snapshot_rollup_entries(entry)
        bridge = _reprove_entry(entry, rollup_entries_snapshot)

        if market_symbol is None:
            market_symbol = bridge.market_symbol
        elif bridge.market_symbol != market_symbol:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:market_symbol_mismatch")

        closed = _canonical_decimal(bridge.closed_units_total)
        realized = _canonical_decimal(bridge.realized_pnl_total)
        if closed is None or realized is None or closed < 0:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_malformed")

        # Canonical event-payload snapshot (single source of digest AND identity): serialize each event to a
        # plain dict EXACTLY once and derive both its recomputed digest and every action-identity field from
        # that same captured payload — the event object is never read again. This closes an event-object
        # TOCTOU where a stateful PaperRealizedPnlEvent returns genuine values to the digest/bridge pass and
        # fake unique identities to a later attribute read. The recompute (same contract as the PUBLIC event
        # digest, which binds the full action identity) must equal the reconstructed bridge's bound
        # source_event_digests, so a divergent capture fails closed here instead of bypassing dedup.
        event_payloads = tuple(_capture_event_payload(bundle.event) for bundle in rollup_entries_snapshot)
        if tuple(_recompute_event_digest(payload) for payload in event_payloads) != bridge.source_event_digests:
            raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:bridge_inconsistent")

        bridge_digests.append(bridge.bridge_digest)
        bridge_ids.append(bridge.bridge_id)
        session_digests.append(bridge.session_sequence_digest)
        rollup_digests.append(bridge.rollup_digest)
        source_event_digests.extend(bridge.source_event_digests)
        for payload in event_payloads:
            event_ids.append(payload["realized_pnl_event_id"])
            fill_digests.append(payload["fill_simulation_result_digest"])
            transition_digests.append(payload["position_transition_digest"])
            action_keys.append(
                (
                    payload["prior_position_state_digest"],
                    payload["fill_simulation_result_digest"],
                    payload["position_transition_digest"],
                    payload["new_position_state_digest"],
                )
            )
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
    # Economic-action dedup across ALL events of ALL bridges. A realized event proves a unique
    # closed/realized economic action; the same action must never be summed twice. Exact event-digest
    # dedup is necessary but insufficient (the same action re-emitted with a different
    # ``realized_pnl_event_id`` yields a different event digest), so the action identity — its event id,
    # fill-simulation-result digest, position-transition digest, and the full
    # (prior, fill, transition, new-state) tuple — is also deduped fail-closed.
    if len(set(source_event_digests)) != len(source_event_digests):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_source_event_digest"
        )
    if len(set(event_ids)) != len(event_ids):
        raise PaperSessionRealizedPnlAggregateError("paper_session_realized_pnl_aggregate:duplicate_source_event_id")
    if len(set(fill_digests)) != len(fill_digests):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_fill_simulation_result_digest"
        )
    if len(set(transition_digests)) != len(transition_digests):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_position_transition_digest"
        )
    if len(set(action_keys)) != len(action_keys):
        raise PaperSessionRealizedPnlAggregateError(
            "paper_session_realized_pnl_aggregate:duplicate_source_action_identity"
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
        fill_simulation_result_digests=tuple(fill_digests),
        position_transition_digests=tuple(transition_digests),
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
    fill_simulation_result_digests: tuple[str, ...],
    position_transition_digests: tuple[str, ...],
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
        "fill_simulation_result_digests": fill_simulation_result_digests,
        "position_transition_digests": position_transition_digests,
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
        "fill_simulation_result_digests": aggregate.fill_simulation_result_digests,
        "position_transition_digests": aggregate.position_transition_digests,
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
        "fill_simulation_result_digests": list(aggregate.fill_simulation_result_digests),
        "position_transition_digests": list(aggregate.position_transition_digests),
        "episode_count_total": aggregate.episode_count_total,
        "event_count": aggregate.event_count,
        "computed_event_count": aggregate.computed_event_count,
        "no_realized_event_count": aggregate.no_realized_event_count,
        "closed_units_total": aggregate.closed_units_total,
        "realized_pnl_total": aggregate.realized_pnl_total,
        "reason_codes": _serialize_reason_codes(aggregate.reason_codes),
        "correlation_id": aggregate.correlation_id,
        "metadata": _serialize_metadata(aggregate.metadata),
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
    """Canonical, JSON-ready mapping for an aggregate (deterministic shape, includes self-digest).

    Fail-closed: ``metadata`` and ``reason_codes`` are canonicalized by exact-shape validators (no blind
    ``list(...)``), so a lossy/malformed container (e.g. ``metadata={"li": "scheduler"}`` or
    ``reason_codes=""``) raises ``PaperSessionRealizedPnlAggregateError`` BEFORE any snapshot/digest is
    produced, instead of silently collapsing into a valid-looking — and collision-prone — payload.
    """
    payload = _aggregate_payload_from(aggregate)
    payload["aggregate_digest"] = aggregate.aggregate_digest
    return payload


def paper_session_realized_pnl_aggregate_digest(aggregate: PaperSessionRealizedPnlAggregate) -> str:
    """Recompute the canonical aggregate digest from the serializer output, excluding the self-digest field.

    Shares the serializer's exact-shape validation, so a lossy/malformed ``metadata`` / ``reason_codes``
    container raises ``PaperSessionRealizedPnlAggregateError`` before a digest can be computed (no two
    distinct hidden values can collapse to one digest).
    """
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
