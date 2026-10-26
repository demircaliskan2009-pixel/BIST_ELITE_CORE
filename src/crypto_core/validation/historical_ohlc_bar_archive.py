"""Authenticated offline OHLC bar archive and the Wilder ATR (PROTECTIVE_POSITION_LIFECYCLE_V1, DEC-7).

A ``HistoricalOhlcBarArchive`` binds one declared offline OHLC source to an ordered set of immutable, fully completed,
UTC-aligned bars of one instrument. It is a pure offline observation contract: it never fetches, schedules or reads a
clock, and a synthetic archive proves construction only, never a real market observation.

Source declaration (``HistoricalOhlcSourceDeclaration``). The source identity, the rights posture, the instrument, the
declared price semantics of the bars (``last_trade``, ``mark_price`` or ``index_price``; never guessed) and the
declared bar intervals, each a whole divisor of the UTC day. Its digest is the identity a position-management approval
adopts; an archive of another source never substitutes for it.

Bars. ``open_time_ns`` is a whole multiple of the interval (UTC-aligned: the epoch is a UTC midnight) and the close is
``open + interval``. Prices are canonical scale-18 decimals with ``0 < low <= min(open, close) <= max(open, close) <=
high``. A bar is published once: its availability (the original publication receipt) and its finality are at or after
its close, so only a fully completed bar can be recorded, and its point-in-time visibility is
``max(available_at_ns, finalized_at_ns)``. There is one bar per (interval, open time); a revision is refused.

Wilder ATR (``WILDER_ATR_14_EXACT_OVER_THE_FULL_CONTIGUOUS_RUN_V1``, the human-approved DEC-7 method). At an instant
``t``, over the bars of one interval that are visible at ``t``:

* the run is the maximal sequence of consecutive bars ending at the visible bar with the latest open time. A missing or
  not-yet-visible bar ends it, so a gap restarts the warmup;
* ``TR_i = max(high_i - low_i, |high_i - close_{i-1}|, |low_i - close_{i-1}|)`` for every bar with its predecessor in
  the run;
* the seed is the arithmetic mean of the first 14 true ranges of the run, and ``ATR_n = (13 * ATR_{n-1} + TR_n) / 14``
  for EVERY later true range of the run. There is no window bound and no re-seed: the reading at ``t`` smooths every
  true range of the run, from its original seed on.

The arithmetic is exact integer arithmetic, with no float, no ``decimal`` context and no rounding. Prices are counted in
scale-18 units and the ATR is carried as ``N / (P * 10^18)``. The seed has ``N`` equal to the sum of the first 14 true
ranges and ``P = 14``; each later true range ``u`` maps ``(N, P)`` to ``(13 * N + P * u, 14 * P)``, which is exactly
``(13 * ATR + TR) / 14``. The exact value gains about 3.8 bits per smoothing step and is never serialized or turned into
text: ``rendered_value`` is its one ROUND_HALF_EVEN scale-18 rendering by integer division, so no integer-to-text limit
applies, and a reading costs a deterministic O(n^2) bit operations over a run of n bars, with no bound on n.

A reading is unavailable, never estimated, when no bar is visible, when the run holds fewer than 15 bars, when the
latest bar closed more than the governed maximum bar age before ``t``, or when the ATR is not positive. A positive
exact ATR below half a scale-18 unit renders as zero, which is no usable positive observation, so it is unavailable
too (``atr_rounds_to_zero``): an available reading always carries a positive canonical rendering, and every consumer
(the engine's entry admission and the paper entry gate) refuses an unavailable one with its reason.

Non-claims: the source is not qualified (M1), its rights are not verified, its historical coverage and the origin of
its publication times are not proven, and nothing here is a venue fact (D1) or a human adoption (C1). Real paper use
stays blocked until those exist. Exact, deterministic and pure: no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    verify_edge_artifact_total,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HISTORICAL_EXECUTION_NUMERIC_POLICY_V1,
    historical_execution_decimal_is_canonical,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)

_SCHEMA_VERSION = "historical-ohlc-bar-archive.v1"
_PREFIX = "historical_ohlc_bar_archive"
_ARCHIVE_DIGEST_FIELD = "archive_digest"
_BAR_DIGEST_FIELD = "bar_digest"
_UTC_DAY_NS = 86_400_000_000_000
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_ATR_PERIOD = 14
_PRICE_SCALE = HISTORICAL_EXECUTION_NUMERIC_POLICY_V1.decimal_scale
_UNITS_PER_ONE = 10**_PRICE_SCALE
_ZERO_RENDERING = historical_execution_render_amount(Fraction(0))

WILDER_ATR_METHOD_ID = "WILDER_ATR_14_EXACT_OVER_THE_FULL_CONTIGUOUS_RUN_V1"

HISTORICAL_OHLC_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("source_qualified", False),
    ("source_rights_verified", False),
    ("historical_coverage_proven", False),
    ("publication_time_origin_proven", False),
    ("real_market_observation_proven", False),
    ("venue_facts_proven", False),
    ("live_ready", False),
)


class HistoricalOhlcBarArchiveError(EdgeArtifactError):
    """Malformed input or a forbidden scope token: an archive is never represented over it."""


class HistoricalOhlcPriceSemantics(str, Enum):
    """The declared price series a bar aggregates. Unknown semantics are refused, never guessed."""

    LAST_TRADE = "last_trade"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"


@dataclass(frozen=True)
class HistoricalOhlcSourceDeclaration:
    """One declared offline OHLC source: identity, rights, instrument, price semantics and bar intervals."""

    source_id: str
    source_reference: str
    rights_status: SourcePacketRightsStatus
    rights_reference: str
    instrument: str
    price_semantics: HistoricalOhlcPriceSemantics
    bar_intervals_ns: tuple[int, ...]


@dataclass(frozen=True)
class HistoricalOhlcBar:
    """One fully completed UTC-aligned bar, published once; ``bar_digest`` covers every other field."""

    interval_ns: int
    open_time_ns: int
    close_time_ns: int
    open_price: str
    high_price: str
    low_price: str
    close_price: str
    available_at_ns: int
    finalized_at_ns: int
    bar_digest: str


@dataclass(frozen=True)
class HistoricalOhlcBarArchive:
    """Immutable, digest-bound offline OHLC archive of one declared source. Never a qualified source or venue fact."""

    schema_version: str
    archive_id: str
    source: HistoricalOhlcSourceDeclaration
    source_digest: str
    bars: tuple[HistoricalOhlcBar, ...]
    bar_count: int
    archive_digest: str
    paper_only: bool = True
    source_qualified: bool = False
    source_rights_verified: bool = False
    historical_coverage_proven: bool = False
    publication_time_origin_proven: bool = False
    real_market_observation_proven: bool = False
    venue_facts_proven: bool = False
    live_ready: bool = False


@dataclass(frozen=True)
class HistoricalOhlcAtrReading:
    """One Wilder ATR reading at an instant: the exact value (never serialized) and its rendered evidence.

    ``value`` is the exact ATR when ``available``; ``rendered_value`` is its one ROUND_HALF_EVEN scale-18 rendering
    (artifact output only), a positive canonical decimal whenever the reading is available. ``window_digest`` commits
    the ordered digests of every bar of the run, all of which the reading smoothed.
    """

    method_id: str
    interval_ns: int
    at_ns: int
    available: bool
    reason: str
    value: Fraction | None
    rendered_value: str | None
    run_bar_count: int
    latest_bar_close_ns: int | None
    window_digest: str | None


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> HistoricalOhlcBarArchiveError:
    return HistoricalOhlcBarArchiveError(_reason(code))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_instrument(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail("instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("instrument_invalid")
    return _require_text(value, "instrument")


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=minimum):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_price(value: object, field_name: str) -> Fraction:
    if not historical_execution_decimal_is_canonical(value) or Fraction(value) <= 0:  # type: ignore[arg-type]
        raise _fail(f"{field_name}_invalid")
    return Fraction(value)  # type: ignore[arg-type]


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _visibility(bar: HistoricalOhlcBar) -> int:
    return max(bar.available_at_ns, bar.finalized_at_ns)


# --- the source declaration --------------------------------------------------------------------------------------------


def canonical_historical_ohlc_source_declaration(value: object) -> HistoricalOhlcSourceDeclaration:
    """Validate one source declaration exactly (types, tokens, rights, semantics and UTC-day-divisor intervals)."""

    if type(value) is not HistoricalOhlcSourceDeclaration:
        raise _fail("source_declaration_malformed")
    if type(value.rights_status) is not SourcePacketRightsStatus:
        raise _fail("rights_status_invalid")
    if type(value.price_semantics) is not HistoricalOhlcPriceSemantics:
        raise _fail("price_semantics_invalid")
    intervals = value.bar_intervals_ns
    if type(intervals) is not tuple or not intervals:
        raise _fail("bar_intervals_invalid")
    for interval in intervals:
        if not historical_execution_wire_int_is_valid(interval, minimum=1) or _UTC_DAY_NS % interval != 0:
            raise _fail("bar_interval_not_a_utc_day_divisor")
    if any(later <= earlier for earlier, later in zip(intervals, intervals[1:], strict=False)):
        raise _fail("bar_intervals_not_strictly_increasing")
    return HistoricalOhlcSourceDeclaration(
        source_id=_require_text(value.source_id, "source_id"),
        source_reference=_require_text(value.source_reference, "source_reference"),
        rights_status=value.rights_status,
        rights_reference=_require_text(value.rights_reference, "rights_reference"),
        instrument=_require_instrument(value.instrument),
        price_semantics=value.price_semantics,
        bar_intervals_ns=intervals,
    )


def historical_ohlc_source_declaration_digest(source: HistoricalOhlcSourceDeclaration) -> str:
    """The identity digest of one validated source declaration."""

    return edge_sha256_text(edge_canonical_json(_to_payload(canonical_historical_ohlc_source_declaration(source))))


# --- bars --------------------------------------------------------------------------------------------------------------


def _canonical_bar_body(bar: object) -> HistoricalOhlcBar:
    if type(bar) is not HistoricalOhlcBar:
        raise _fail("bar_malformed")
    interval = _require_int(bar.interval_ns, "interval_ns", minimum=1)
    opened = _require_int(bar.open_time_ns, "open_time_ns", minimum=0)
    closed = _require_int(bar.close_time_ns, "close_time_ns", minimum=0)
    if opened % interval != 0:
        raise _fail("bar_not_utc_aligned")
    if closed != opened + interval:
        raise _fail("bar_close_not_open_plus_interval")
    open_price = _require_price(bar.open_price, "open_price")
    high = _require_price(bar.high_price, "high_price")
    low = _require_price(bar.low_price, "low_price")
    close = _require_price(bar.close_price, "close_price")
    if not low <= min(open_price, close) <= max(open_price, close) <= high:
        raise _fail("bar_prices_inconsistent")
    available = _require_int(bar.available_at_ns, "available_at_ns", minimum=0)
    finalized = _require_int(bar.finalized_at_ns, "finalized_at_ns", minimum=0)
    if available < closed or finalized < closed:
        raise _fail("bar_not_completed_at_publication")
    return replace(bar, bar_digest="")


def build_historical_ohlc_bar(
    *,
    interval_ns: int,
    open_time_ns: int,
    open_price: str,
    high_price: str,
    low_price: str,
    close_price: str,
    available_at_ns: int,
    finalized_at_ns: int,
) -> HistoricalOhlcBar:
    """Build one fully completed UTC-aligned bar and its digest; malformed input raises."""

    if not historical_execution_wire_int_is_valid(interval_ns, minimum=1):
        raise _fail("interval_ns_invalid")
    if not historical_execution_wire_int_is_valid(open_time_ns, minimum=0):
        raise _fail("open_time_ns_invalid")
    close_time = open_time_ns + interval_ns
    if not historical_execution_wire_int_is_valid(close_time, minimum=0):
        raise _fail("close_time_ns_invalid")
    body = _canonical_bar_body(
        HistoricalOhlcBar(
            interval_ns=interval_ns,
            open_time_ns=open_time_ns,
            close_time_ns=close_time,
            open_price=open_price,
            high_price=high_price,
            low_price=low_price,
            close_price=close_price,
            available_at_ns=available_at_ns,
            finalized_at_ns=finalized_at_ns,
            bar_digest="",
        )
    )
    return replace(body, bar_digest=edge_payload_digest(_to_payload(body), _BAR_DIGEST_FIELD))


def historical_ohlc_bar_digest(bar: HistoricalOhlcBar) -> str:
    """Recompute one bar's digest, excluding only ``bar_digest``."""

    return edge_payload_digest(_to_payload(bar), _BAR_DIGEST_FIELD)


# --- the archive -------------------------------------------------------------------------------------------------------


def _assemble_archive(*, archive_id: object, source: object, bars: object) -> HistoricalOhlcBarArchive:
    """The one archive assembly path, shared by the builder and the verifier."""

    archive_id = _require_text(archive_id, "archive_id")
    source = canonical_historical_ohlc_source_declaration(source)
    if type(bars) is not tuple:
        raise _fail("bars_malformed")
    canonical: list[HistoricalOhlcBar] = []
    for bar in bars:
        body = _canonical_bar_body(bar)
        if bar.bar_digest != edge_payload_digest(_to_payload(body), _BAR_DIGEST_FIELD):  # type: ignore[attr-defined]
            raise _fail("bar_digest_mismatch")
        if body.interval_ns not in source.bar_intervals_ns:
            raise _fail("bar_interval_not_declared")
        canonical.append(bar)  # type: ignore[arg-type]
    keys = [(bar.interval_ns, bar.open_time_ns) for bar in canonical]
    if any(later <= earlier for earlier, later in zip(keys, keys[1:], strict=False)):
        raise _fail("bars_not_strictly_ordered_by_interval_and_open_time")
    seed = HistoricalOhlcBarArchive(
        schema_version=_SCHEMA_VERSION,
        archive_id=archive_id,
        source=source,
        source_digest=historical_ohlc_source_declaration_digest(source),
        bars=tuple(canonical),
        bar_count=len(canonical),
        archive_digest="",
    )
    return replace(seed, archive_digest=edge_payload_digest(_to_payload(seed), _ARCHIVE_DIGEST_FIELD))


def build_historical_ohlc_bar_archive(
    *,
    archive_id: str,
    source: HistoricalOhlcSourceDeclaration,
    bars: tuple[HistoricalOhlcBar, ...],
) -> HistoricalOhlcBarArchive:
    """Build one archive: bars of declared intervals, strictly ordered by (interval, open time), one per slot.

    Bars are given in canonical order; a duplicate slot (a revision), an undeclared interval, an incomplete or
    misaligned bar, a tampered bar digest or a malformed declaration raises ``HistoricalOhlcBarArchiveError``. Pure.
    """

    return _assemble_archive(archive_id=archive_id, source=source, bars=bars)


def historical_ohlc_bar_archive_to_dict(archive: HistoricalOhlcBarArchive) -> dict[str, object]:
    """Canonical JSON-ready mapping of an archive, including its self-digest."""

    return _to_payload(archive)


def historical_ohlc_bar_archive_digest(archive: HistoricalOhlcBarArchive) -> str:
    """Recompute the canonical archive digest, excluding only ``archive_digest``."""

    return edge_payload_digest(_to_payload(archive), _ARCHIVE_DIGEST_FIELD)


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_int_tuple(value: object) -> tuple[int, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_int(item) for item in value)


_SOURCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "rights_status": _as_enum(SourcePacketRightsStatus),
    "price_semantics": _as_enum(HistoricalOhlcPriceSemantics),
    "bar_intervals_ns": _as_int_tuple,
}
_BAR_CONVERTERS: dict[str, Callable[[object], object]] = {
    "interval_ns": _as_int,
    "open_time_ns": _as_int,
    "close_time_ns": _as_int,
    "available_at_ns": _as_int,
    "finalized_at_ns": _as_int,
}


def _as_bars(value: object) -> tuple[HistoricalOhlcBar, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_parse_exact(HistoricalOhlcBar, item, _BAR_CONVERTERS) for item in value)  # type: ignore[misc]


_ARCHIVE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "source": lambda value: _parse_exact(HistoricalOhlcSourceDeclaration, value, _SOURCE_CONVERTERS),
    "bars": _as_bars,
    "bar_count": _as_int,
    **{name: _as_bool for name, _ in HISTORICAL_OHLC_NON_CLAIM_FLAGS},
}


def historical_ohlc_bar_archive_from_payload(payload: object) -> HistoricalOhlcBarArchive:
    """Strictly reconstruct an archive from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(HistoricalOhlcBarArchive, payload, _ARCHIVE_CONVERTERS)  # type: ignore[return-value]


def historical_ohlc_bar_archive_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an archive snapshot."""

    try:
        historical_ohlc_bar_archive_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_archive(archive: object) -> HistoricalOhlcBarArchive:
    return _assemble_archive(
        archive_id=archive.archive_id,  # type: ignore[attr-defined]
        source=archive.source,  # type: ignore[attr-defined]
        bars=archive.bars,  # type: ignore[attr-defined]
    )


def verify_historical_ohlc_bar_archive(archive: object) -> EdgeEvidenceVerification:
    """Re-prove an archive by strict parse, digest recomputation and reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        archive,
        cls=HistoricalOhlcBarArchive,
        to_payload=_to_payload,
        parse_payload=historical_ohlc_bar_archive_from_payload,
        reassemble=_reassemble_archive,
        self_digest_field=_ARCHIVE_DIGEST_FIELD,
        reason=_reason,
    )


# --- the Wilder ATR (DEC-7) --------------------------------------------------------------------------------------------


def _unavailable(interval_ns: int, at_ns: int, reason: str, count: int = 0) -> HistoricalOhlcAtrReading:
    return HistoricalOhlcAtrReading(
        WILDER_ATR_METHOD_ID, interval_ns, at_ns, False, reason, None, None, count, None, None
    )


def _price_units(price: str) -> int:
    """The exact scale-18 unit count of one canonical bar price (a verified archive holds no other)."""

    whole, dot, decimals = price.partition(".")
    if not (dot and len(decimals) == _PRICE_SCALE and price.isascii() and whole.isdigit() and decimals.isdigit()):
        raise _fail("atr_bar_price_malformed")
    return int(whole + decimals)


def historical_ohlc_wilder_atr(
    archive: HistoricalOhlcBarArchive,
    *,
    interval_ns: int,
    at_ns: int,
    max_bar_age_ns: int,
) -> HistoricalOhlcAtrReading:
    """The DEC-7 Wilder ATR(14) of ``archive`` at ``at_ns`` over the bars of ``interval_ns`` visible then.

    ``archive`` must be the canonical, verified archive (callers verify once); malformed arguments raise. An unavailable
    reading carries its reason (``atr_no_visible_bar``, ``atr_warmup_insufficient``, ``atr_bar_stale``,
    ``atr_not_positive``, ``atr_unrepresentable`` or ``atr_rounds_to_zero``) and no value, rendering or window. An
    available reading carries the exact ATR over the whole run, its positive rendering and the run's window digest. Pure.
    """

    if type(archive) is not HistoricalOhlcBarArchive:
        raise _fail("atr_archive_malformed")
    if interval_ns not in archive.source.bar_intervals_ns:
        raise _fail("atr_interval_not_declared")
    if not historical_execution_wire_int_is_valid(at_ns, minimum=0):
        raise _fail("atr_instant_invalid")
    if not historical_execution_wire_int_is_valid(max_bar_age_ns, minimum=1):
        raise _fail("atr_max_bar_age_invalid")
    visible = {
        bar.open_time_ns: bar for bar in archive.bars if bar.interval_ns == interval_ns and _visibility(bar) <= at_ns
    }
    if not visible:
        return _unavailable(interval_ns, at_ns, "atr_no_visible_bar")
    latest = visible[max(visible)]
    run = [latest]
    while run[-1].open_time_ns - interval_ns in visible:
        run.append(visible[run[-1].open_time_ns - interval_ns])
    run.reverse()
    if len(run) < _ATR_PERIOD + 1:
        return _unavailable(interval_ns, at_ns, "atr_warmup_insufficient", len(run))
    if at_ns - latest.close_time_ns > max_bar_age_ns:
        return _unavailable(interval_ns, at_ns, "atr_bar_stale", len(run))
    ranges: list[int] = []  # every true range of the run, in scale-18 units
    for previous, bar in zip(run, run[1:], strict=False):
        high, low = _price_units(bar.high_price), _price_units(bar.low_price)
        prior_close = _price_units(previous.close_price)
        ranges.append(max(high - low, abs(high - prior_close), abs(low - prior_close)))
    # ATR == numerator / (power * 10^18): the seed, then (13 * ATR + TR) / 14 for every later true range of the run
    numerator, power = sum(ranges[:_ATR_PERIOD]), _ATR_PERIOD
    for value in ranges[_ATR_PERIOD:]:
        numerator, power = (_ATR_PERIOD - 1) * numerator + power * value, _ATR_PERIOD * power
    if numerator <= 0:
        return _unavailable(interval_ns, at_ns, "atr_not_positive", len(run))
    atr = Fraction(numerator, power * _UNITS_PER_ONE)
    rendered = historical_execution_render_amount(atr)
    if rendered is None:
        return _unavailable(interval_ns, at_ns, "atr_unrepresentable", len(run))
    if rendered == _ZERO_RENDERING:
        return _unavailable(interval_ns, at_ns, "atr_rounds_to_zero", len(run))
    window = edge_sha256_text(edge_canonical_json([bar.bar_digest for bar in run]))
    return HistoricalOhlcAtrReading(
        WILDER_ATR_METHOD_ID, interval_ns, at_ns, True, "", atr, rendered, len(run), latest.close_time_ns, window
    )


__all__ = [
    "HISTORICAL_OHLC_NON_CLAIM_FLAGS",
    "WILDER_ATR_METHOD_ID",
    "HistoricalOhlcAtrReading",
    "HistoricalOhlcBar",
    "HistoricalOhlcBarArchive",
    "HistoricalOhlcBarArchiveError",
    "HistoricalOhlcPriceSemantics",
    "HistoricalOhlcSourceDeclaration",
    "build_historical_ohlc_bar",
    "build_historical_ohlc_bar_archive",
    "canonical_historical_ohlc_source_declaration",
    "historical_ohlc_bar_archive_digest",
    "historical_ohlc_bar_archive_from_payload",
    "historical_ohlc_bar_archive_payload_is_well_formed",
    "historical_ohlc_bar_archive_to_dict",
    "historical_ohlc_bar_digest",
    "historical_ohlc_source_declaration_digest",
    "historical_ohlc_wilder_atr",
    "verify_historical_ohlc_bar_archive",
]
