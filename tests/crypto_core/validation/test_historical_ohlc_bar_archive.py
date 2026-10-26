"""Tests for the authenticated offline OHLC bar archive and the DEC-7 Wilder ATR (PROTECTIVE_POSITION_LIFECYCLE_V1).

SYNTHETIC TEST VALUES ONLY. Every bar, price, instant and source declaration here is a synthetic fixture that exercises
structure: none is a market observation, a qualified source or a venue fact.
"""

from __future__ import annotations

import ast
import decimal
from dataclasses import replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.historical_ohlc_bar_archive as ohlc_module
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import edge_canonical_json, edge_sha256_text
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount
from crypto_core.validation.historical_ohlc_bar_archive import (
    HISTORICAL_OHLC_NON_CLAIM_FLAGS,
    WILDER_ATR_METHOD_ID,
    HistoricalOhlcBar,
    HistoricalOhlcBarArchive,
    HistoricalOhlcBarArchiveError,
    HistoricalOhlcPriceSemantics,
    HistoricalOhlcSourceDeclaration,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
    canonical_historical_ohlc_source_declaration,
    historical_ohlc_bar_archive_digest,
    historical_ohlc_bar_archive_from_payload,
    historical_ohlc_bar_archive_payload_is_well_formed,
    historical_ohlc_bar_archive_to_dict,
    historical_ohlc_bar_digest,
    historical_ohlc_source_declaration_digest,
    historical_ohlc_wilder_atr,
    verify_historical_ohlc_bar_archive,
)

try:  # the module object pytest collects (basename import)
    import test_historical_pit_dataset as pit
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "historical_ohlc_bar_archive"
SECOND = 1_000_000_000
HOUR = 3_600 * SECOND
H4 = 4 * HOUR
DAY = 24 * HOUR
T0 = 19_000 * DAY  # SYNTHETIC: a UTC midnight
INS = "BTC-USDT-PERP"
PUBLICATION = SECOND  # SYNTHETIC publication delay after the close
MAX_AGE = 8 * HOUR  # SYNTHETIC governed maximum bar age


def d(value: object) -> str:
    rendered = historical_execution_render_amount(Fraction(value))  # type: ignore[arg-type]
    assert rendered is not None
    return rendered


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def source(**changes: object) -> HistoricalOhlcSourceDeclaration:
    base = HistoricalOhlcSourceDeclaration(
        source_id="synthetic-ohlc-1",
        source_reference="archive:synthetic-ohlc",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="license-1",
        instrument=INS,
        price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        bar_intervals_ns=(H4, DAY),
    )
    return replace(base, **changes)


def flat_bar(k: int, true_range: object, *, interval: int = H4, mid: object = 100, delay: int = PUBLICATION):
    """SYNTHETIC bar ``k`` of the 4 h grid: open == close == mid, so its TR is its range when the previous close is mid."""

    half = Fraction(true_range) / 2  # type: ignore[arg-type]
    opened = T0 + k * interval
    return build_historical_ohlc_bar(
        interval_ns=interval,
        open_time_ns=opened,
        open_price=d(mid),
        high_price=d(Fraction(mid) + half),  # type: ignore[arg-type]
        low_price=d(Fraction(mid) - half),  # type: ignore[arg-type]
        close_price=d(mid),
        available_at_ns=opened + interval + delay,
        finalized_at_ns=opened + interval + delay,
    )


def archive_of(*bars: HistoricalOhlcBar, archive_id: str = "ohlc-1") -> HistoricalOhlcBarArchive:
    return build_historical_ohlc_bar_archive(archive_id=archive_id, source=source(), bars=tuple(bars))


def run_of(ranges: tuple[object, ...], *, first: int = 0) -> tuple[HistoricalOhlcBar, ...]:
    """A contiguous run: bar ``first`` (no TR) followed by one bar per given true range."""

    return (flat_bar(first, 1), *(flat_bar(first + 1 + index, value) for index, value in enumerate(ranges)))


def after(bar: HistoricalOhlcBar) -> int:
    """The first instant ``bar`` is visible."""

    return max(bar.available_at_ns, bar.finalized_at_ns)


def atr(archive: HistoricalOhlcBarArchive, at_ns: int, **changes: object):  # noqa: ANN201
    arguments: dict[str, object] = {"interval_ns": H4, "at_ns": at_ns, "max_bar_age_ns": MAX_AGE}
    arguments.update(changes)
    return historical_ohlc_wilder_atr(archive, **arguments)  # type: ignore[arg-type]


def wilder_oracle(bars: tuple[HistoricalOhlcBar, ...]) -> Fraction:
    """INDEPENDENT ORACLE: the literal DEC-7 recurrence, in Fraction arithmetic, over EVERY true range of ``bars``.

    ``bars`` is one contiguous run. The seed is the mean of its first 14 true ranges and every later true range is
    smoothed by ``(13 * ATR + TR) / 14``: no window, no re-seed.
    """

    ranges = [
        max(
            Fraction(bar.high_price) - Fraction(bar.low_price),
            abs(Fraction(bar.high_price) - Fraction(previous.close_price)),
            abs(Fraction(bar.low_price) - Fraction(previous.close_price)),
        )
        for previous, bar in zip(bars, bars[1:], strict=False)
    ]
    value = sum(ranges[:14], Fraction(0)) / 14
    for item in ranges[14:]:
        value = (13 * value + item) / 14
    return value


def window_of(bars: tuple[HistoricalOhlcBar, ...]) -> str:
    return edge_sha256_text(edge_canonical_json([item.bar_digest for item in bars]))


def unit_bar(k: int, units: int) -> HistoricalOhlcBar:
    """SYNTHETIC bar ``k`` whose true range is ``units`` scale-18 units: open == high == close == 100, the low below."""

    opened = T0 + k * H4
    return build_historical_ohlc_bar(
        interval_ns=H4,
        open_time_ns=opened,
        open_price=d(100),
        high_price=d(100),
        low_price=d(Fraction(100) - Fraction(units, 10**18)),
        close_price=d(100),
        available_at_ns=opened + H4 + PUBLICATION,
        finalized_at_ns=opened + H4 + PUBLICATION,
    )


def unit_run(units: tuple[int, ...]) -> tuple[HistoricalOhlcBar, ...]:
    """A contiguous run of unit bars: bar 0 (no true range) followed by one bar per given unit count."""

    return (unit_bar(0, 0), *(unit_bar(1 + index, value) for index, value in enumerate(units)))


# --- A. the Wilder ATR: golden exact vectors ------------------------------------------------------------------------------


def test_the_seed_is_the_mean_of_the_first_14_true_ranges() -> None:
    bars = run_of(tuple(range(1, 15)))
    reading = atr(archive_of(*bars), after(bars[-1]))
    assert reading.available and reading.reason == ""
    assert reading.value == Fraction(15, 2)  # (1 + 2 + ... + 14) / 14, by hand
    assert reading.rendered_value == "7.500000000000000000"
    assert (reading.method_id, reading.run_bar_count, reading.latest_bar_close_ns) == (
        WILDER_ATR_METHOD_ID,
        15,
        bars[-1].close_time_ns,
    )


def test_every_later_true_range_is_wilder_smoothed_exactly() -> None:
    bars = run_of((*range(1, 15), 15, 1))
    first = atr(archive_of(*bars[:-1]), after(bars[-2]))
    second = atr(archive_of(*bars), after(bars[-1]))
    assert first.value == (Fraction(15, 2) * 13 + 15) / 14 == Fraction(225, 28)  # by hand: 112.5 / 14
    assert second.value == (Fraction(225, 28) * 13 + 1) / 14 == Fraction(2953, 392)
    assert second.rendered_value == "7.533163265306122449"  # ROUND_HALF_EVEN of 2953/392 at scale 18


def test_the_true_range_reaches_the_previous_close_across_a_price_gap() -> None:
    base = run_of(tuple([2] * 14))
    opened = T0 + 15 * H4
    gap = build_historical_ohlc_bar(
        interval_ns=H4,
        open_time_ns=opened,
        open_price=d(103),
        high_price=d(105),
        low_price=d(102),
        close_price=d(104),
        available_at_ns=opened + H4 + PUBLICATION,
        finalized_at_ns=opened + H4 + PUBLICATION,
    )
    reading = atr(archive_of(*base, gap), after(gap))
    # TR = max(105 - 102, |105 - 100|, |102 - 100|) = 5: the previous close, never the bar's own range
    assert reading.value == (Fraction(2) * 13 + 5) / 14


def test_fewer_than_15_contiguous_bars_is_an_unavailable_warmup() -> None:
    bars = run_of(tuple(range(1, 14)))
    reading = atr(archive_of(*bars), after(bars[-1]))
    assert (reading.available, reading.reason, reading.value, reading.rendered_value) == (
        False,
        "atr_warmup_insufficient",
        None,
        None,
    )
    assert reading.run_bar_count == 14 and reading.window_digest is None


def test_a_missing_bar_restarts_the_warmup_after_the_gap() -> None:
    early = run_of(tuple(range(1, 15)))  # bars 0..14
    late = tuple(flat_bar(16 + index, 3) for index in range(14))  # bar 15 missing: bars 16..29 (14 bars)
    archive = archive_of(*early, *late)
    assert atr(archive, after(early[-1])).value == Fraction(15, 2)
    blocked = atr(archive, after(late[-1]))
    assert (blocked.available, blocked.reason, blocked.run_bar_count) == (False, "atr_warmup_insufficient", 14)
    one_more = flat_bar(30, 3)
    resumed = atr(archive_of(*early, *late, one_more), after(one_more))
    assert resumed.value == 3 and resumed.run_bar_count == 15  # only the post-gap run, never smoothed across the gap


def test_every_true_range_of_the_run_is_smoothed_from_the_original_seed() -> None:
    # 400 contiguous bars, 399 true ranges: the seed is the first 14 (9), and each of the 385 after it is smoothed in
    ranges = (9,) * 119 + (2,) * 14 + (3,) * 266
    bars = run_of(ranges)
    reading = atr(archive_of(*bars), after(bars[-1]))
    expected = Fraction(9)
    for value in ranges[14:]:
        expected = (expected * 13 + value) / 14
    assert reading.value == expected == wilder_oracle(bars)
    assert (reading.run_bar_count, reading.window_digest) == (400, window_of(bars))  # every bar of the run is bound
    assert reading.rendered_value == d(expected)
    # a 280-true-range re-seed would forget the 9s and smooth only the last 280 (2 then 3): another, wrong, number
    reseeded = Fraction(2)
    for _ in range(266):
        reseeded = (reseeded * 13 + 3) / 14
    assert reading.value != reseeded


@pytest.mark.parametrize(
    ("first", "rendered"),
    [(0, "1.999999999635588982"), (198, "2.000000035712279796")],
)
def test_the_audited_282_bar_counterexample_keeps_its_first_true_range(first: int, rendered: str) -> None:
    """P2-DEC7-280-TR-RESEED: 281 true ranges, the first ``first`` and the 280 after it 2; a re-seed reads exactly 2."""

    bars = run_of((first,) + (2,) * 280)
    reading = atr(archive_of(*bars), after(bars[-1]))
    assert reading.value == wilder_oracle(bars) and reading.value != 2
    assert (reading.available, reading.rendered_value, reading.run_bar_count) == (True, rendered, 282)
    assert reading.window_digest == window_of(bars)


def test_every_historical_prefix_changes_the_reading_exactly_as_the_oracle_does() -> None:
    tail = (2,) * 280  # a 280-true-range re-seed reads exactly 2 for every one of these runs
    values = []
    for prefix in ((), (5,), (5, 3) * 25, tuple(k % 9 + 1 for k in range(300)), (1,) * 1000):
        bars = run_of(prefix + tail)
        reading = atr(archive_of(*bars), after(bars[-1]))
        assert (reading.value, reading.run_bar_count) == (wilder_oracle(bars), len(bars))
        values.append(reading.value)
    assert values[0] == 2 and len(set(values)) == len(values)  # the prefix is never erased, however long the tail


def test_a_long_history_is_exact_over_thousands_of_updates_and_its_rendering_needs_no_integer_text() -> None:
    ranges = tuple(Fraction((k * 7919) % 400, 100) for k in range(6000))  # SYNTHETIC deterministic true ranges
    bars = run_of(ranges)
    archive = archive_of(*bars)
    reading = atr(archive, after(bars[-1]))
    expected = wilder_oracle(bars)
    assert (reading.value, reading.run_bar_count, reading.window_digest) == (expected, 6001, window_of(bars))
    assert reading.rendered_value == d(expected)
    # 5,986 smoothing steps: the exact denominator holds more digits than the integer-to-text limit (4,300), and the
    # reading is still exact and rendered, because nothing ever turns the exact value into text
    assert reading.value.denominator > 10**4_300
    assert atr(archive, after(bars[-1])) == reading  # deterministic
    with decimal.localcontext() as context:
        context.prec = 2
        assert atr(archive, after(bars[-1])) == reading


def test_a_late_bar_inside_a_long_run_cuts_it_until_it_is_published_and_nothing_leaks_before() -> None:
    bars = run_of(tuple((k % 7) + 1 for k in range(600)))  # bars 0..600
    late = replace_publication(bars[581], 100 * HOUR)  # 19 bars before the end; visible 24 h after the last bar
    archive = archive_of(*bars[:581], late, *bars[582:])
    cut = atr(archive, after(bars[-1]))
    assert (cut.value, cut.run_bar_count, cut.window_digest) == (wilder_oracle(bars[582:]), 19, window_of(bars[582:]))
    assert atr(archive, after(late) - 1, max_bar_age_ns=30 * HOUR) == replace(cut, at_ns=after(late) - 1)
    joined = atr(archive, after(late), max_bar_age_ns=30 * HOUR)
    assert (joined.value, joined.run_bar_count) == (wilder_oracle((*bars[:581], late, *bars[582:])), 601)
    assert joined.value == wilder_oracle(bars)  # the late bar's prices are the same: only its publication moved


def test_a_positive_atr_that_rounds_to_zero_at_scale_18_is_unavailable() -> None:
    """P2-POSITIVE-ATR-RENDER-ZERO: a positive exact ATR below half a scale-18 unit has no positive observation."""

    for units, available in (((7,), False), ((8,), True), ((1,), False)):  # seed means 0.5, 0.571.. and 0.071.. units
        bars = unit_run(units + (0,) * 13)
        reading = atr(archive_of(*bars), after(bars[-1]))
        assert wilder_oracle(bars) > 0  # the exact ATR is strictly positive in every case
        if available:
            assert (reading.available, reading.rendered_value) == (True, "0.000000000000000001")
            assert reading.value == wilder_oracle(bars) and reading.window_digest == window_of(bars)
        else:  # 0.5 units rounds half-even to 0: no positive rendering
            assert (
                reading.available,
                reading.reason,
                reading.value,
                reading.rendered_value,
                reading.window_digest,
                reading.latest_bar_close_ns,
                reading.run_bar_count,
            ) == (False, "atr_rounds_to_zero", None, None, None, None, 15)
    # decay: a seed of one unit smoothed by zero true ranges is (13/14)^k units, 0.5136 at k = 9 and 0.4769 at k = 10
    bars = unit_run((14,) + (0,) * 13 + (0,) * 10)
    archive = archive_of(*bars)
    still = atr(archive, after(bars[-2]))
    assert (still.available, still.rendered_value) == (True, "0.000000000000000001")
    assert still.value == Fraction(13, 14) ** 9 / 10**18 == wilder_oracle(bars[:-1])
    gone = atr(archive, after(bars[-1]))
    assert (gone.available, gone.reason, gone.rendered_value) == (False, "atr_rounds_to_zero", None)
    assert wilder_oracle(bars) == Fraction(13, 14) ** 10 / 10**18 > 0


def test_a_forged_unverified_price_is_refused_and_never_mis_scaled() -> None:
    bars = run_of(tuple(range(1, 15)))
    archive = archive_of(*bars)
    forged = replace(archive, bars=(*archive.bars[:-1], replace(archive.bars[-1], high_price="101.5")))
    assert not verify_historical_ohlc_bar_archive(forged).intact
    with pytest.raises(HistoricalOhlcBarArchiveError, match=f"^{code('atr_bar_price_malformed')}$"):
        atr(forged, after(bars[-1]))


def test_only_bars_visible_at_the_instant_are_read_and_a_late_publication_cuts_the_run() -> None:
    bars = run_of(tuple(range(1, 16)))  # bars 0..15
    late = replace_publication(bars[15], 10 * HOUR)
    archive = archive_of(*bars[:15], late)
    at = after(bars[15])  # bar 15 completed and its normal publication would be visible
    reading = atr(archive, at, max_bar_age_ns=16 * HOUR)
    assert reading.value == Fraction(15, 2) and reading.latest_bar_close_ns == bars[14].close_time_ns
    assert atr(archive, after(late), max_bar_age_ns=16 * HOUR).value == (Fraction(15, 2) * 13 + 15) / 14
    # a future bar (visible after the instant) never contributes, whatever its prices
    assert atr(archive, after(late) - 1, max_bar_age_ns=16 * HOUR).value == Fraction(15, 2)


def replace_publication(bar: HistoricalOhlcBar, delay: int) -> HistoricalOhlcBar:
    return build_historical_ohlc_bar(
        interval_ns=bar.interval_ns,
        open_time_ns=bar.open_time_ns,
        open_price=bar.open_price,
        high_price=bar.high_price,
        low_price=bar.low_price,
        close_price=bar.close_price,
        available_at_ns=bar.close_time_ns + delay,
        finalized_at_ns=bar.close_time_ns + delay,
    )


def test_a_stale_latest_bar_is_unavailable_and_the_age_bound_is_inclusive() -> None:
    bars = run_of(tuple(range(1, 15)))
    archive = archive_of(*bars)
    close = bars[-1].close_time_ns
    assert atr(archive, close + MAX_AGE).available
    stale = atr(archive, close + MAX_AGE + 1)
    assert (stale.available, stale.reason) == (False, "atr_bar_stale")


def test_no_visible_bar_and_a_zero_atr_are_unavailable() -> None:
    bars = run_of(tuple(range(1, 15)))
    assert atr(archive_of(*bars), T0).reason == "atr_no_visible_bar"
    flat = run_of(tuple([0] * 14))
    zero = atr(archive_of(*flat), after(flat[-1]))
    assert (zero.available, zero.reason) == (False, "atr_not_positive")


def test_each_interval_is_read_alone() -> None:
    four_hour = run_of(tuple(range(1, 15)))
    daily = tuple(flat_bar(index, 9 if index else 1, interval=DAY) for index in range(15))
    archive = archive_of(*four_hour, *daily)
    assert atr(archive, after(daily[-1]), interval_ns=DAY, max_bar_age_ns=DAY).value == 9
    assert atr(archive, after(four_hour[-1])).value == Fraction(15, 2)
    with pytest.raises(HistoricalOhlcBarArchiveError, match=code("atr_interval_not_declared")):
        atr(archive, after(four_hour[-1]), interval_ns=HOUR)


def test_the_window_digest_commits_the_ordered_bars_of_the_run() -> None:
    bars = run_of(tuple(range(1, 15)))
    reading = atr(archive_of(*bars), after(bars[-1]))
    assert reading.window_digest == edge_sha256_text(edge_canonical_json([item.bar_digest for item in bars]))


def test_the_reading_is_independent_of_the_ambient_decimal_context() -> None:
    bars = run_of((*range(1, 15), 15, 1))
    archive = archive_of(*bars)
    baseline = atr(archive, after(bars[-1]))
    with decimal.localcontext() as context:
        context.prec = 3
        context.rounding = decimal.ROUND_UP
        assert atr(archive, after(bars[-1])) == baseline


# --- B. bars, declarations and the archive --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"open_time_ns": T0 + 1}, "bar_not_utc_aligned"),
        ({"available_at_ns": T0 + H4 - 1}, "bar_not_completed_at_publication"),
        ({"finalized_at_ns": T0 + H4 - 1}, "bar_not_completed_at_publication"),
        ({"low_price": d(101)}, "bar_prices_inconsistent"),
        ({"high_price": d(99)}, "bar_prices_inconsistent"),
        ({"low_price": d(0)}, "low_price_invalid"),
        ({"close_price": "100.0"}, "close_price_invalid"),
        ({"interval_ns": 0}, "interval_ns_invalid"),
        ({"open_time_ns": True}, "open_time_ns_invalid"),
    ],
)
def test_a_malformed_or_incomplete_bar_is_never_built(changes: dict[str, object], reason: str) -> None:
    arguments: dict[str, object] = {
        "interval_ns": H4,
        "open_time_ns": T0,
        "open_price": d(100),
        "high_price": d(101),
        "low_price": d(99),
        "close_price": d(100),
        "available_at_ns": T0 + H4,
        "finalized_at_ns": T0 + H4,
    }
    arguments.update(changes)
    with pytest.raises(HistoricalOhlcBarArchiveError, match=f"^{code(reason)}$"):
        build_historical_ohlc_bar(**arguments)  # type: ignore[arg-type]


def test_a_bar_digest_covers_every_field_and_a_tampered_bar_never_enters_an_archive() -> None:
    bar = flat_bar(0, 2)
    assert bar.bar_digest == historical_ohlc_bar_digest(bar)
    tampered = replace(bar, close_price=d(Fraction(1001, 10)))
    with pytest.raises(HistoricalOhlcBarArchiveError, match=code("bar_digest_mismatch")):
        archive_of(tampered)
    resealed = replace(tampered, bar_digest=historical_ohlc_bar_digest(tampered))
    assert archive_of(resealed).bars == (resealed,)  # a resealed bar is another bar, with another digest


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"bar_intervals_ns": (H4 + 1,)}, "bar_interval_not_a_utc_day_divisor"),
        ({"bar_intervals_ns": (DAY, H4)}, "bar_intervals_not_strictly_increasing"),
        ({"bar_intervals_ns": ()}, "bar_intervals_invalid"),
        ({"rights_status": "own_research"}, "rights_status_invalid"),
        ({"price_semantics": "mark_price"}, "price_semantics_invalid"),
        ({"instrument": "btc usdt"}, "instrument_invalid"),
        ({"source_reference": "bist:archive"}, "bist_scope_leakage:source_reference"),
    ],
)
def test_a_malformed_source_declaration_is_refused(changes: dict[str, object], reason: str) -> None:
    with pytest.raises(HistoricalOhlcBarArchiveError, match=f"^{code(reason)}$"):
        canonical_historical_ohlc_source_declaration(source(**changes))


def test_an_archive_refuses_duplicates_disorder_and_undeclared_intervals() -> None:
    first, second = flat_bar(0, 1), flat_bar(1, 1)
    with pytest.raises(
        HistoricalOhlcBarArchiveError, match=code("bars_not_strictly_ordered_by_interval_and_open_time")
    ):
        archive_of(second, first)
    with pytest.raises(
        HistoricalOhlcBarArchiveError, match=code("bars_not_strictly_ordered_by_interval_and_open_time")
    ):
        archive_of(first, first)
    hourly = flat_bar(0, 1, interval=HOUR)
    with pytest.raises(HistoricalOhlcBarArchiveError, match=code("bar_interval_not_declared")):
        archive_of(hourly)


def test_the_archive_is_digest_bound_and_reverifies_totally() -> None:
    archive = archive_of(*run_of(tuple(range(1, 15))))
    verification = verify_historical_ohlc_bar_archive(archive)
    assert verification.intact and verification.recomputed_digest == archive.archive_digest
    assert archive.archive_digest == historical_ohlc_bar_archive_digest(archive)
    assert archive.source_digest == historical_ohlc_source_declaration_digest(source())
    assert archive.bar_count == 15
    payload = historical_ohlc_bar_archive_to_dict(archive)
    assert historical_ohlc_bar_archive_payload_is_well_formed(payload)
    assert historical_ohlc_bar_archive_from_payload(payload) == archive
    flags = dict(HISTORICAL_OHLC_NON_CLAIM_FLAGS)
    assert {name: getattr(archive, name) for name in flags} == flags


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("archive_id", "ohlc-2"),
        ("bar_count", 14),
        ("source_qualified", True),
        ("publication_time_origin_proven", True),
        ("schema_version", "historical-ohlc-bar-archive.v2"),
    ],
)
def test_a_resealed_archive_change_never_verifies(name: str, value: object) -> None:
    archive = archive_of(*run_of(tuple(range(1, 15))))
    forged = replace(archive, **{name: value})
    forged = replace(forged, archive_digest=historical_ohlc_bar_archive_digest(forged))
    if name == "archive_id":  # a renamed archive is another authentic archive: only its anchor can refuse it
        assert verify_historical_ohlc_bar_archive(forged).intact
        assert forged.archive_digest != archive.archive_digest
    else:
        assert not verify_historical_ohlc_bar_archive(forged).intact


def test_the_verifier_is_total_and_the_parser_is_strict() -> None:
    for value in (None, "archive", 1, object()):
        assert not verify_historical_ohlc_bar_archive(value).intact
    payload = historical_ohlc_bar_archive_to_dict(archive_of(flat_bar(0, 1)))
    for broken in ({**payload, "extra": 1}, {key: value for key, value in payload.items() if key != "bars"}):
        assert not historical_ohlc_bar_archive_payload_is_well_formed(broken)


def test_the_module_is_pure_exact_and_offline() -> None:
    source_text = Path(ohlc_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source_text)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(alias.name.split(".")[0] in pit.FORBIDDEN_MODULES for alias in node.names)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.split(".")[0] not in pit.FORBIDDEN_MODULES and node.module != "decimal"
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
    assert "bist" not in source_text.lower()
