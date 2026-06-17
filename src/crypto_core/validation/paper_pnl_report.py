"""Paper mark-to-market PnL report — deterministic, paper-only unrealized PnL over a position state.

A small, immutable, fail-closed module that consumes a digest-bound ``PaperPositionState`` plus a
caller-supplied point-in-time ``PaperMarkSnapshot`` and emits a frozen, digest-bound
``PaperPnlReport``. It computes **unrealized / mark-to-market PnL only**. It does **not** compute
realized PnL, total PnL, equity, margin, balance, capital, funding, fees, or liquidation; it does not
mutate the position state, capital, or balances; it routes no order, creates no venue/exchange/client
order id / route id / execution instruction, calls no live/private API, and touches no
connector/scheduler/runtime/venue/execution/service/session/data/portfolio/orchestrator/temporal
surface, no Deribit, no BIST.

Per the PR #278 connector P3 note, this consumer re-derives its own economics: mark-to-market is
computed directly from the position's ``signed_units`` / ``abs_units`` / ``average_entry_price`` and the
snapshot's ``mark_price`` — never from any upstream gross-notional / fee field.

MTM semantics (exact ``Decimal``; ``q`` = signed units, ``|q|`` = abs units, ``avg`` = average entry,
``m`` = mark price > 0):
  - FLAT  ⇒ ``mark_notional = 0``, ``unrealized_pnl = 0`` (avg is None).
  - LONG  ⇒ ``mark_notional = |q| * m``, ``unrealized_pnl = |q| * (m - avg)``.
  - SHORT ⇒ ``mark_notional = |q| * m``, ``unrealized_pnl = |q| * (avg - m)``.
No realized PnL is ever computed; ``realized_pnl`` / ``total_pnl`` are always ``None``; no capital is
touched. The loss sign comes from an *ordered subtraction* (``m - avg`` / ``avg - m``), never a
context-affected unary minus.

Numeric discipline: every product/subtraction runs under an input-derived ``localcontext`` precision so
the result is exact (no division anywhere — MTM is a pure product, so no rounding). Rendering is
context-independent (``format(…, "f")`` + manual trailing-zero strip — never ``Decimal.normalize()``);
abs via ``copy_abs`` (never ``abs(Decimal)``); no scientific notation, no negative zero.

Fail closed: a wrong-typed/malformed/forged position state or mark snapshot, a digest mismatch, a
symbol mismatch, an unsafe flag, a forbidden token, an invalid/noncanonical decimal, or an inconsistent
side/signed/abs/avg raises ``PaperPnlReportError``. Every valid input produces a ``COMPUTED`` report.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, localcontext
from enum import Enum

from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    PaperPositionStateSide,
    paper_position_state_digest,
)

_MARK_SNAPSHOT_SCHEMA_VERSION = "paper-mark-snapshot.v1"
_REPORT_SCHEMA_VERSION = "paper-pnl-report.v1"
_EXPECTED_POSITION_SCHEMA_VERSION = "paper-position-state.v1"

# Strict decimal-string grammar: optional sign, no leading zeros (except a bare ``0``), optional
# fraction. Rejects ``""``, ``"1."``, ``".5"``, ``"00"``, ``"1e5"``, ``"NaN"``, ``"inf"``, whitespace,
# and underscores. Sign/positivity is enforced separately below.
_DECIMAL_PATTERN = re.compile(r"^-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?$")

# Scope guard mirrors the sibling validation modules (word-bounded) and additionally rejects bare
# ``connector``/``route_id``/``execution_instruction``/``deribit``/``venue|exchange|client_order_id``
# tokens relevant to this report. Market-data terms are scrubbed before the scan.
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


class PaperPnlReportError(RuntimeError):
    """Raised when PnL-report inputs are wrong-typed/malformed/forged or fail re-proof (fail-closed)."""


class PaperPnlReportStatus(str, Enum):
    """Deterministic paper PnL report outcome. Never an execution / capital / realized-settlement action."""

    COMPUTED = "COMPUTED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class PaperMarkSnapshot:
    """Deterministic, immutable point-in-time mark snapshot for paper MTM. PAPER ONLY.

    A caller-supplied mark input only — never a live/private data feed. ``mark_price`` is a strict,
    strictly-positive decimal string.
    """

    schema_version: str
    mark_snapshot_id: str
    market_symbol: str
    mark_price: str
    observed_at_ns: int | None
    mark_source_id: str | None
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    mark_snapshot_digest: str


@dataclass(frozen=True)
class PaperPnlReport:
    """Deterministic, immutable digest-bound paper mark-to-market PnL report. PAPER ONLY.

    Reports unrealized / MTM PnL over one position state at one mark only — never realized PnL, total
    PnL, equity, margin, capital/balance, or any live/execution action. ``pnl_computed`` is the one
    positive attestation (this layer does compute unrealized PnL); every other attestation is False and
    ``realized_pnl`` / ``total_pnl`` are always None.
    """

    schema_version: str
    pnl_report_id: str
    status: PaperPnlReportStatus
    position_state_digest: str
    mark_snapshot_digest: str
    market_symbol: str
    position_side: PaperPositionStateSide
    signed_units: str
    abs_units: str
    average_entry_price: str | None
    mark_price: str
    mark_notional: str
    unrealized_pnl: str
    reason_codes: tuple[str, ...]
    correlation_id: str
    metadata: tuple[tuple[str, str], ...]
    pnl_report_digest: str
    realized_pnl: str | None = None
    total_pnl: str | None = None
    paper_only: bool = True
    pnl_computed: bool = True
    realized_pnl_computed: bool = False
    capital_reserved: bool = False
    capital_mutated: bool = False
    balance_mutated: bool = False
    position_mutated: bool = False
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
    form) via a ``_parse_decimal`` + ``_render_decimal`` round-trip fixpoint, so a forged upstream
    cannot smuggle a noncanonical/negative-zero numeric field past digest re-proof.
    """
    parsed = _parse_decimal(value)
    if parsed is None or _render_decimal(parsed) != value:
        return None
    return parsed


def _arithmetic_precision(operands: tuple[Decimal, ...]) -> int:
    """Decimal precision wide enough that every exact product/difference over the inputs is exact."""
    digits = sum(len(value.as_tuple().digits) for value in operands)
    return max(28, digits + 40)


def _normalize_metadata(metadata: object) -> tuple[tuple[str, str], ...]:
    if metadata is None:
        return ()
    if not isinstance(metadata, Mapping):
        raise PaperPnlReportError("paper_pnl_report:metadata_malformed")
    items: list[tuple[str, str]] = []
    for key, value in metadata.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise PaperPnlReportError("paper_pnl_report:metadata_malformed")
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
# Mark snapshot
# --------------------------------------------------------------------------------------------------


def _mark_payload(
    *,
    schema_version: str,
    mark_snapshot_id: str,
    market_symbol: str,
    mark_price: str,
    observed_at_ns: int | None,
    mark_source_id: str | None,
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "mark_snapshot_id": mark_snapshot_id,
        "market_symbol": market_symbol,
        "mark_price": mark_price,
        "observed_at_ns": observed_at_ns,
        "mark_source_id": mark_source_id,
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
    }


def build_paper_mark_snapshot(
    *,
    mark_snapshot_id: str,
    market_symbol: str,
    mark_price: str,
    observed_at_ns: int | None = None,
    mark_source_id: str | None = None,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperMarkSnapshot:
    """Build a deterministic, immutable PIT mark snapshot with a canonical ``mark_snapshot_digest``.

    ``mark_snapshot_id``/``market_symbol``/``correlation_id`` must be non-empty token-clean strings;
    ``mark_price`` a strict, strictly-positive decimal string; ``observed_at_ns`` (if given) a
    non-negative ``int`` (not ``bool``); ``mark_source_id`` (if given) a non-empty token-clean string. A
    malformed or forbidden-token field raises ``PaperPnlReportError``. PAPER ONLY — caller-supplied
    mark, never a live feed.
    """
    if not _is_non_empty_string(mark_snapshot_id):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_id_invalid")
    if not _is_non_empty_string(market_symbol):
        raise PaperPnlReportError("paper_pnl_report:mark_market_symbol_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperPnlReportError("paper_pnl_report:correlation_id_invalid")
    mark = _parse_decimal(mark_price)
    if mark is None or not mark > 0:
        raise PaperPnlReportError("paper_pnl_report:mark_price_invalid")
    if observed_at_ns is not None and (not _is_int(observed_at_ns) or observed_at_ns < 0):
        raise PaperPnlReportError("paper_pnl_report:observed_at_ns_invalid")
    if mark_source_id is not None and not _is_non_empty_string(mark_source_id):
        raise PaperPnlReportError("paper_pnl_report:mark_source_id_invalid")
    metadata_pairs = _normalize_metadata(metadata)
    if _has_scope_violation(
        mark_snapshot_id, market_symbol, correlation_id, mark_source_id, *_metadata_texts(metadata_pairs)
    ):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_scope_violation")
    canonical_mark = _render_decimal(mark)
    payload = _mark_payload(
        schema_version=_MARK_SNAPSHOT_SCHEMA_VERSION,
        mark_snapshot_id=mark_snapshot_id,
        market_symbol=market_symbol,
        mark_price=canonical_mark,
        observed_at_ns=observed_at_ns,
        mark_source_id=mark_source_id,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
    )
    return PaperMarkSnapshot(
        schema_version=_MARK_SNAPSHOT_SCHEMA_VERSION,
        mark_snapshot_id=mark_snapshot_id,
        market_symbol=market_symbol,
        mark_price=canonical_mark,
        observed_at_ns=observed_at_ns,
        mark_source_id=mark_source_id,
        correlation_id=correlation_id,
        metadata=metadata_pairs,
        mark_snapshot_digest=_canonical_digest(payload),
    )


def _mark_payload_from(snapshot: PaperMarkSnapshot) -> dict[str, object]:
    return _mark_payload(
        schema_version=snapshot.schema_version,
        mark_snapshot_id=snapshot.mark_snapshot_id,
        market_symbol=snapshot.market_symbol,
        mark_price=snapshot.mark_price,
        observed_at_ns=snapshot.observed_at_ns,
        mark_source_id=snapshot.mark_source_id,
        correlation_id=snapshot.correlation_id,
        metadata=snapshot.metadata,
    )


def paper_mark_snapshot_to_dict(snapshot: PaperMarkSnapshot) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a mark snapshot (deterministic shape, includes self-digest)."""
    payload = _mark_payload_from(snapshot)
    payload["mark_snapshot_digest"] = snapshot.mark_snapshot_digest
    return payload


def paper_mark_snapshot_digest(snapshot: PaperMarkSnapshot) -> str:
    """Recompute the canonical mark-snapshot digest from the serializer output, excluding self-digest."""
    return _canonical_digest(_mark_payload_from(snapshot))


# --------------------------------------------------------------------------------------------------
# Re-proof
# --------------------------------------------------------------------------------------------------


def _position_is_paper_safe(state: PaperPositionState) -> bool:
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


def _reprove_position_state(
    state: PaperPositionState,
) -> tuple[PaperPositionStateSide, Decimal, Decimal, Decimal | None]:
    """Re-prove a digest-valid position state's structure/safety; return (side, signed, abs, average).

    Digest equality is necessary but not sufficient: a self-consistent forged state (digest recomputed
    over a tampered payload) must still fail if any structural/economic invariant is violated.
    """
    if state.schema_version != _EXPECTED_POSITION_SCHEMA_VERSION:
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if not isinstance(state.side, PaperPositionStateSide):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if not _position_is_paper_safe(state):
        raise PaperPnlReportError("paper_pnl_report:position_state_unsafe_flags")
    if not _is_non_empty_string(state.position_state_id) or not _is_non_empty_string(state.correlation_id):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if not _is_non_empty_string(state.market_symbol):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if state.last_fill_simulation_digest is not None and not _is_hex64_string(state.last_fill_simulation_digest):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if not _is_int(state.transition_count) or state.transition_count < 0:
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    signed = _canonical_decimal(state.signed_units)
    abs_value = _canonical_decimal(state.abs_units)
    if signed is None or abs_value is None or abs_value < 0 or signed.copy_abs() != abs_value:
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    average: Decimal | None = None
    if state.average_entry_price is not None:
        average = _canonical_decimal(state.average_entry_price)
        if average is None or not average > 0:
            raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if state.side is PaperPositionStateSide.FLAT:
        if signed != 0 or abs_value != 0 or average is not None:
            raise PaperPnlReportError("paper_pnl_report:position_state_inconsistent")
    elif state.side is PaperPositionStateSide.LONG:
        if not signed > 0 or average is None:
            raise PaperPnlReportError("paper_pnl_report:position_state_inconsistent")
    else:  # SHORT
        if not signed < 0 or average is None:
            raise PaperPnlReportError("paper_pnl_report:position_state_inconsistent")
    if not _is_metadata_tuple(state.metadata):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if _has_scope_violation(
        state.position_state_id, state.market_symbol, state.correlation_id, *_metadata_texts(state.metadata)
    ):
        raise PaperPnlReportError("paper_pnl_report:position_state_scope_violation")
    return state.side, signed, abs_value, average


def _reprove_mark_snapshot(snapshot: PaperMarkSnapshot) -> Decimal:
    """Re-prove a digest-valid mark snapshot's structure; return the strictly-positive mark price."""
    if snapshot.schema_version != _MARK_SNAPSHOT_SCHEMA_VERSION:
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if not _is_non_empty_string(snapshot.mark_snapshot_id) or not _is_non_empty_string(snapshot.market_symbol):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if not _is_non_empty_string(snapshot.correlation_id):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    mark = _canonical_decimal(snapshot.mark_price)
    if mark is None or not mark > 0:
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if snapshot.observed_at_ns is not None and (not _is_int(snapshot.observed_at_ns) or snapshot.observed_at_ns < 0):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if snapshot.mark_source_id is not None and not _is_non_empty_string(snapshot.mark_source_id):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if not _is_metadata_tuple(snapshot.metadata):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")
    if _has_scope_violation(
        snapshot.mark_snapshot_id,
        snapshot.market_symbol,
        snapshot.correlation_id,
        snapshot.mark_source_id,
        *_metadata_texts(snapshot.metadata),
    ):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_scope_violation")
    return mark


# --------------------------------------------------------------------------------------------------
# Mark-to-market computation
# --------------------------------------------------------------------------------------------------


def _compute_mtm(
    *, side: PaperPositionStateSide, abs_value: Decimal, average: Decimal | None, mark: Decimal
) -> tuple[Decimal, Decimal]:
    """Pure exact mark-to-market. Returns (mark_notional, unrealized_pnl). No division, no rounding."""
    if side is PaperPositionStateSide.FLAT:
        return Decimal(0), Decimal(0)
    operands = (abs_value, mark, average if average is not None else Decimal(0))
    with localcontext() as ctx:
        ctx.prec = _arithmetic_precision(operands)
        mark_notional = abs_value * mark
        if side is PaperPositionStateSide.LONG:  # average is non-None for a non-flat re-proven state
            unrealized = abs_value * (mark - average)
        else:  # SHORT — ordered subtraction (avg - m), never a context-affected unary minus
            unrealized = abs_value * (average - mark)
    return mark_notional, unrealized


def compute_paper_pnl_report(
    position_state: PaperPositionState,
    mark_snapshot: PaperMarkSnapshot,
    *,
    pnl_report_id: str,
    correlation_id: str,
    metadata: Mapping[str, str] | None = None,
) -> PaperPnlReport:
    """Compute a deterministic unrealized / mark-to-market PnL report over a position state.

    The ``position_state`` and ``mark_snapshot`` are re-proven via their PUBLIC digests (mismatch
    raises) and structurally re-proven (paper-safe, well-formed, token-clean). The market symbol must
    match. MTM is computed directly from the position's units/average and the snapshot's mark price
    (never from any upstream gross/fee). Position fields are copied from the position state and the mark
    price from the snapshot; the caller supplies only ids/correlation/metadata. Always returns a
    ``COMPUTED`` report for valid inputs. No realized/total PnL, no equity/margin/capital/balance, no
    mutation of inputs, no order routing, no live API. Wrong-typed/malformed/forged inputs raise
    ``PaperPnlReportError``.
    """
    if not _is_non_empty_string(pnl_report_id):
        raise PaperPnlReportError("paper_pnl_report:pnl_report_id_invalid")
    if not _is_non_empty_string(correlation_id):
        raise PaperPnlReportError("paper_pnl_report:correlation_id_invalid")
    report_metadata = _normalize_metadata(metadata)
    if _has_scope_violation(pnl_report_id, correlation_id, *_metadata_texts(report_metadata)):
        raise PaperPnlReportError("paper_pnl_report:scope_violation")
    if not isinstance(position_state, PaperPositionState):
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed")
    if not isinstance(mark_snapshot, PaperMarkSnapshot):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed")

    # Digest boundaries: re-prove both upstream self-digests via their PUBLIC serializers.
    try:
        expected_position_digest = paper_position_state_digest(position_state)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperPnlReportError("paper_pnl_report:position_state_malformed") from exc
    if not isinstance(position_state.position_state_digest, str) or position_state.position_state_digest != (
        expected_position_digest
    ):
        raise PaperPnlReportError("paper_pnl_report:position_state_digest_mismatch")
    try:
        expected_mark_digest = paper_mark_snapshot_digest(mark_snapshot)
    except Exception as exc:  # noqa: BLE001 - re-raise as a typed error; BaseException not caught
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_malformed") from exc
    if not isinstance(mark_snapshot.mark_snapshot_digest, str) or mark_snapshot.mark_snapshot_digest != (
        expected_mark_digest
    ):
        raise PaperPnlReportError("paper_pnl_report:mark_snapshot_digest_mismatch")

    side, _signed, abs_value, average = _reprove_position_state(position_state)
    mark = _reprove_mark_snapshot(mark_snapshot)

    if mark_snapshot.market_symbol != position_state.market_symbol:
        raise PaperPnlReportError("paper_pnl_report:symbol_mismatch")

    mark_notional, unrealized = _compute_mtm(side=side, abs_value=abs_value, average=average, mark=mark)

    return _finalize_report(
        pnl_report_id=pnl_report_id,
        position_state=position_state,
        mark_snapshot=mark_snapshot,
        mark_notional=_render_decimal(mark_notional),
        unrealized_pnl=_render_decimal(unrealized),
        reasons=(),
        correlation_id=correlation_id,
        metadata=report_metadata,
    )


def _finalize_report(
    *,
    pnl_report_id: str,
    position_state: PaperPositionState,
    mark_snapshot: PaperMarkSnapshot,
    mark_notional: str,
    unrealized_pnl: str,
    reasons: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
) -> PaperPnlReport:
    report = PaperPnlReport(
        schema_version=_REPORT_SCHEMA_VERSION,
        pnl_report_id=pnl_report_id,
        status=PaperPnlReportStatus.COMPUTED,
        position_state_digest=position_state.position_state_digest,
        mark_snapshot_digest=mark_snapshot.mark_snapshot_digest,
        market_symbol=position_state.market_symbol,
        position_side=position_state.side,
        signed_units=position_state.signed_units,
        abs_units=position_state.abs_units,
        average_entry_price=position_state.average_entry_price,
        mark_price=mark_snapshot.mark_price,
        mark_notional=mark_notional,
        unrealized_pnl=unrealized_pnl,
        reason_codes=_sorted_unique(reasons),
        correlation_id=correlation_id,
        metadata=metadata,
        pnl_report_digest="",
    )
    object_digest = paper_pnl_report_digest(report)
    return PaperPnlReport(
        schema_version=report.schema_version,
        pnl_report_id=report.pnl_report_id,
        status=report.status,
        position_state_digest=report.position_state_digest,
        mark_snapshot_digest=report.mark_snapshot_digest,
        market_symbol=report.market_symbol,
        position_side=report.position_side,
        signed_units=report.signed_units,
        abs_units=report.abs_units,
        average_entry_price=report.average_entry_price,
        mark_price=report.mark_price,
        mark_notional=report.mark_notional,
        unrealized_pnl=report.unrealized_pnl,
        reason_codes=report.reason_codes,
        correlation_id=report.correlation_id,
        metadata=report.metadata,
        pnl_report_digest=object_digest,
    )


def _report_payload(
    *,
    schema_version: str,
    pnl_report_id: str,
    status_value: str,
    position_state_digest: str,
    mark_snapshot_digest: str,
    market_symbol: str,
    position_side_value: str,
    signed_units: str,
    abs_units: str,
    average_entry_price: str | None,
    mark_price: str,
    mark_notional: str,
    unrealized_pnl: str,
    realized_pnl: str | None,
    total_pnl: str | None,
    reason_codes: tuple[str, ...],
    correlation_id: str,
    metadata: tuple[tuple[str, str], ...],
    paper_only: bool,
    pnl_computed: bool,
    realized_pnl_computed: bool,
    capital_reserved: bool,
    capital_mutated: bool,
    balance_mutated: bool,
    position_mutated: bool,
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
) -> dict[str, object]:
    return {
        "schema_version": schema_version,
        "pnl_report_id": pnl_report_id,
        "status": status_value,
        "position_state_digest": position_state_digest,
        "mark_snapshot_digest": mark_snapshot_digest,
        "market_symbol": market_symbol,
        "position_side": position_side_value,
        "signed_units": signed_units,
        "abs_units": abs_units,
        "average_entry_price": average_entry_price,
        "mark_price": mark_price,
        "mark_notional": mark_notional,
        "unrealized_pnl": unrealized_pnl,
        "realized_pnl": realized_pnl,
        "total_pnl": total_pnl,
        "reason_codes": list(reason_codes),
        "correlation_id": correlation_id,
        "metadata": [list(pair) for pair in metadata],
        "paper_only": paper_only,
        "pnl_computed": pnl_computed,
        "realized_pnl_computed": realized_pnl_computed,
        "capital_reserved": capital_reserved,
        "capital_mutated": capital_mutated,
        "balance_mutated": balance_mutated,
        "position_mutated": position_mutated,
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
    }


def _report_payload_from(report: PaperPnlReport) -> dict[str, object]:
    return _report_payload(
        schema_version=report.schema_version,
        pnl_report_id=report.pnl_report_id,
        status_value=report.status.value,
        position_state_digest=report.position_state_digest,
        mark_snapshot_digest=report.mark_snapshot_digest,
        market_symbol=report.market_symbol,
        position_side_value=(
            report.position_side.value
            if isinstance(report.position_side, PaperPositionStateSide)
            else str(report.position_side)
        ),
        signed_units=report.signed_units,
        abs_units=report.abs_units,
        average_entry_price=report.average_entry_price,
        mark_price=report.mark_price,
        mark_notional=report.mark_notional,
        unrealized_pnl=report.unrealized_pnl,
        realized_pnl=report.realized_pnl,
        total_pnl=report.total_pnl,
        reason_codes=report.reason_codes,
        correlation_id=report.correlation_id,
        metadata=report.metadata,
        paper_only=report.paper_only,
        pnl_computed=report.pnl_computed,
        realized_pnl_computed=report.realized_pnl_computed,
        capital_reserved=report.capital_reserved,
        capital_mutated=report.capital_mutated,
        balance_mutated=report.balance_mutated,
        position_mutated=report.position_mutated,
        live_position_mutated=report.live_position_mutated,
        real_money_enabled=report.real_money_enabled,
        real_orders_enabled=report.real_orders_enabled,
        order_routed=report.order_routed,
        venue_order_id_created=report.venue_order_id_created,
        exchange_order_id_created=report.exchange_order_id_created,
        client_order_id_created=report.client_order_id_created,
        route_id_created=report.route_id_created,
        execution_instruction_created=report.execution_instruction_created,
        live_api_called=report.live_api_called,
        scheduler_enabled=report.scheduler_enabled,
        connector_invoked=report.connector_invoked,
    )


def paper_pnl_report_to_dict(report: PaperPnlReport) -> dict[str, object]:
    """Canonical, JSON-ready mapping for a PnL report (deterministic shape, includes self-digest)."""
    payload = _report_payload_from(report)
    payload["pnl_report_digest"] = report.pnl_report_digest
    return payload


def paper_pnl_report_digest(report: PaperPnlReport) -> str:
    """Recompute the canonical PnL-report digest from the serializer output, excluding the self-digest."""
    return _canonical_digest(_report_payload_from(report))


__all__ = [
    "PaperMarkSnapshot",
    "PaperPnlReport",
    "PaperPnlReportError",
    "PaperPnlReportStatus",
    "build_paper_mark_snapshot",
    "compute_paper_pnl_report",
    "paper_mark_snapshot_digest",
    "paper_mark_snapshot_to_dict",
    "paper_pnl_report_digest",
    "paper_pnl_report_to_dict",
]
