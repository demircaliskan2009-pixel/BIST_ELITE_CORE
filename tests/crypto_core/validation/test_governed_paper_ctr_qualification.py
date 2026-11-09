"""Governed paper CTR source qualification tests (CTR_SOURCE_QUALIFICATION_V1 consumer of
S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1).

SYNTHETIC TEST VALUES ONLY. Every qualification, licence digest, approver reference, source record, count and order
book here is a synthetic fixture that exercises structure. No real source is qualified (X-M1-C), no provider is
asserted, and the TEST-ONLY qualification table is installed by these tests alone; the PRODUCTION table admits no
qualification. The approved companion's acceptance criteria (§10.4, T-CTR-01..10) are covered, with sequence progression
judged in the capture's receipt order, never by a sort (Sol B2), and the depth index re-proving its whole dataset before
it reads a book (Sol B1).
"""

from __future__ import annotations

import ast
import contextlib
import inspect
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_ctr_qualification as ctr
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus
from crypto_core.validation.governed_paper_ctr_qualification import (
    GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE,
    GOVERNED_PAPER_CTR_REQUIRED_USE,
    GovernedPaperCtrApprovalKind,
    GovernedPaperCtrApprovalTable,
    GovernedPaperCtrCancelDefinition,
    GovernedPaperCtrCoverageMethod,
    GovernedPaperCtrDepthStatus,
    GovernedPaperCtrError,
    GovernedPaperCtrRecordKind,
    GovernedPaperCtrRevocationKind,
    GovernedPaperCtrSourceClass,
    GovernedPaperCtrSourceContext,
    GovernedPaperCtrSourceRecord,
    GovernedPaperCtrTradeDefinition,
    GovernedPaperDepthIndex,
    GovernedPaperVisibleDepth,
    build_governed_paper_ctr_qualification_revocation,
    build_governed_paper_ctr_source_capture,
    build_governed_paper_ctr_source_qualification,
    evaluate_governed_paper_ctr_depth,
    governed_paper_ctr_admission,
    governed_paper_ctr_canonical_context,
    governed_paper_ctr_depth_cap,
    governed_paper_ctr_reading,
    verify_governed_paper_ctr_qualification_revocation,
    verify_governed_paper_ctr_source_capture,
    verify_governed_paper_ctr_source_qualification,
)
from crypto_core.validation.governed_paper_regime_state import governed_paper_order_book_series
from crypto_core.validation.historical_execution_economics import HistoricalExecutionSide
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitValue,
    build_historical_pit_dataset,
    historical_pit_dataset_digest,
    historical_pit_record_digest,
    verify_historical_pit_dataset,
)

try:  # the module objects pytest collects (basename import): the shared synthetic depth-50 tips
    import test_governed_paper_regime_state as rst
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst

SECOND = 1_000_000_000
T = 100_000 * SECOND  # SYNTHETIC reading instant
WINDOW = 60 * SECOND
INS = rst.INS
SYNTHETIC = GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC
HUMAN = GovernedPaperCtrApprovalKind.HUMAN_GOVERNANCE
TEST_ONLY_TABLE = GovernedPaperCtrApprovalTable("test_only", SYNTHETIC, ())
K = GovernedPaperCtrRecordKind
BUY, SELL = HistoricalExecutionSide.BUY, HistoricalExecutionSide.SELL
D_PASS, D_FAIL, D_BLOCKED = (
    GovernedPaperCtrDepthStatus.PASS,
    GovernedPaperCtrDepthStatus.FAIL,
    GovernedPaperCtrDepthStatus.BLOCKED,
)


@contextlib.contextmanager
def ctr_table(table: GovernedPaperCtrApprovalTable) -> Iterator[None]:
    assert ctr._APPROVAL_TABLE is GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE  # noqa: SLF001
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctr, "_APPROVAL_TABLE", table)
        yield


@pytest.fixture
def test_only() -> Iterator[None]:
    with ctr_table(TEST_ONLY_TABLE):
        yield


def qualification(**changes: object):  # noqa: ANN201
    arguments: dict[str, object] = {
        "qualification_id": "synthetic-ctr-qualification-1",
        "revision": "r1",
        "provider": "synthetic-provider",
        "dataset_channel": "synthetic-order-events",
        "venue": "synthetic-venue",
        "instrument": INS,
        "source_version": "v1",
        "source_class": GovernedPaperCtrSourceClass.ORDER_LEVEL_EVENTS,
        "licence_reference": "synthetic-licence-1",
        "licence_digest": "1" * 64,
        "permitted_uses": (GOVERNED_PAPER_CTR_REQUIRED_USE,),
        "processing_by_this_system_permitted": True,
        "cancel_definition": GovernedPaperCtrCancelDefinition.FULL_CANCEL_AND_PARTIAL_REDUCTION,
        "trade_definition": GovernedPaperCtrTradeDefinition.PER_MATCH,
        "coverage_method": GovernedPaperCtrCoverageMethod.SEQUENCE_CONTINUITY,
        "heartbeat_max_interval_ns": None,
        "approval_kind": SYNTHETIC,
        "approver_reference": "synthetic-test-fixture",
        "approval_time_ns": 0,
    }
    arguments.update(changes)
    return build_governed_paper_ctr_source_qualification(**arguments)  # type: ignore[arg-type]


def record(sequence: int, kind: GovernedPaperCtrRecordKind, published: int, received: int | None = None, **counts: int):  # noqa: ANN201
    return GovernedPaperCtrSourceRecord(
        sequence_id=sequence,
        kind=kind,
        publication_time_ns=published,
        receipt_time_ns=published if received is None else received,
        **counts,  # type: ignore[arg-type]
    )


def window_events(
    cancels: int, trades: int, *, anchor: int = T - WINDOW - SECOND
) -> list[GovernedPaperCtrSourceRecord]:
    """An anchor before the window, then ``cancels`` full cancels and ``trades`` trades inside it, contiguous."""

    rows = [record(0, K.ORDER_ADD, anchor)]
    instants = [T - WINDOW + SECOND + index * SECOND for index in range(cancels + trades)]
    kinds = [K.ORDER_CANCEL_FULL] * cancels + [K.TRADE] * trades
    rows.extend(record(index + 1, kind, at) for index, (kind, at) in enumerate(zip(kinds, instants, strict=True)))
    return rows


def context(rows: list | tuple, *, through: int = T, revocations: tuple = (), **changes: object):  # noqa: ANN201
    q = qualification(**changes)
    ordered = tuple(sorted(rows, key=lambda item: item.receipt_time_ns))
    return GovernedPaperCtrSourceContext(
        qualification=q,
        revocations=revocations,
        capture=build_governed_paper_ctr_source_capture(
            capture_id="synthetic-capture-1", qualification=q, complete_through_receipt_ns=through, records=ordered
        ),
    )


def read(source: object, at: int = T):  # noqa: ANN201
    return governed_paper_ctr_reading(source, instrument=INS, time_ns=at)  # type: ignore[arg-type]


# --- A. the qualification record and the tables ----------------------------------------------------------------------------


def test_a_qualification_is_digest_bound_reverifies_and_never_carries_production_permission() -> None:
    q = qualification()
    verification = verify_governed_paper_ctr_source_qualification(q)
    assert (verification.intact, verification.recomputed_digest) == (True, q.qualification_digest)
    assert q.production_use_authorized is False
    forged = replace(q, venue="other-venue")  # a changed field without its digest never verifies
    assert verify_governed_paper_ctr_source_qualification(forged).intact is False
    assert verify_governed_paper_ctr_source_qualification(object()).intact is False


@pytest.mark.parametrize(
    "changes",
    [
        {"source_class": "L2_BOOK_DIFFERENCES"},  # counts inferred from L2 changes never qualify (T-CTR-03)
        {"source_class": "MODELED_CANCELLATIONS"},
        {"licence_digest": "x"},
        {"permitted_uses": ("b", "a")},
        {"permitted_uses": [GOVERNED_PAPER_CTR_REQUIRED_USE]},
        {"processing_by_this_system_permitted": 1},
        {"coverage_method": GovernedPaperCtrCoverageMethod.VENUE_HEARTBEATS},
        {"heartbeat_max_interval_ns": 5 * SECOND},
        {"approval_kind": "HUMAN_GOVERNANCE"},
        {"approval_time_ns": -1},
        {"venue": ""},
    ],
)
def test_a_malformed_qualification_is_refused(changes: dict[str, object]) -> None:
    with pytest.raises(GovernedPaperCtrError):
        qualification(**changes)


def test_the_production_table_admits_no_qualification_and_the_test_only_table_only_synthetic_ones() -> None:
    synthetic, human = qualification(), qualification(approval_kind=HUMAN)
    production = GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE
    assert ctr._APPROVAL_TABLE is production and production.admitted_qualification_digests == ()  # noqa: SLF001
    assert (
        governed_paper_ctr_admission(production, synthetic) == "synthetic_qualification_refused_on_the_production_table"
    )
    assert governed_paper_ctr_admission(production, human) == "qualification_not_authorized_for_production_use"
    assert governed_paper_ctr_admission(TEST_ONLY_TABLE, synthetic) == ""
    assert governed_paper_ctr_admission(TEST_ONLY_TABLE, human) == (
        "only_test_only_synthetic_qualifications_on_the_test_only_table"
    )
    for malformed in (
        GovernedPaperCtrApprovalTable("test_only", SYNTHETIC, ("1" * 64,)),
        GovernedPaperCtrApprovalTable("production", SYNTHETIC, ()),
        GovernedPaperCtrApprovalTable("other", HUMAN, ()),
    ):
        with pytest.raises(GovernedPaperCtrError, match="approval_table_malformed$"):
            governed_paper_ctr_admission(malformed, synthetic)


def test_in_production_no_reading_is_available_and_the_depth_cap_never_passes() -> None:
    source = context(window_events(2, 4))
    reading = read(source)
    assert (reading.available, reading.reason) == (False, "synthetic_qualification_refused_on_the_production_table")
    assert read(None).reason == "no_ctr_source_supplied"
    depth = GovernedPaperVisibleDepth(BUY, "2" * 64, "1000", True, "")
    assert evaluate_governed_paper_ctr_depth(quantity=Fraction(1), depth=depth, ctr=reading).status is D_BLOCKED
    assert governed_paper_ctr_depth_cap(depth, reading) is None  # T-CTR-01


# --- B. the reading (§1.2 A.4 and §5) ----------------------------------------------------------------------------------------


def test_a_qualified_covered_window_reads_the_exact_ctr_and_alpha(test_only: None) -> None:
    for cancels, trades, ctr_value, alpha in (
        (10, 4, Fraction(5, 2), Fraction(1)),
        (20, 4, Fraction(5), Fraction(1)),  # at 5.0 exactly: alpha 1 (T-CTR-08)
        (24, 4, Fraction(6), Fraction(5, 6)),  # 1 / (1 + 0.2 x 1)
        (40, 4, Fraction(10), Fraction(1, 2)),  # 1 / (1 + 0.2 x 5)
        (21, 4, Fraction(21, 4), Fraction(20, 21)),  # one quarter above 5.0
    ):
        reading = read(context(window_events(cancels, trades)))
        assert (reading.available, reading.cancel_count, reading.trade_count) == (True, cancels, trades)
        assert (Fraction(reading.ctr), Fraction(reading.alpha)) == (ctr_value, alpha)  # type: ignore[arg-type]
        assert Fraction(reading.alpha) == 1 / (1 + Fraction(1, 5) * (ctr_value - 5)) or ctr_value <= 5  # type: ignore[arg-type]


def test_the_cancel_definition_decides_what_counts(test_only: None) -> None:
    rows = [
        record(0, K.ORDER_ADD, T - WINDOW - SECOND),
        record(1, K.ORDER_CANCEL_FULL, T - 50 * SECOND),
        record(2, K.ORDER_CANCEL_PARTIAL, T - 40 * SECOND),
        record(3, K.ORDER_AMEND, T - 30 * SECOND),
        record(4, K.TRADE, T - 20 * SECOND),
    ]
    counts = {
        definition: read(context(rows, cancel_definition=definition)).cancel_count
        for definition in GovernedPaperCtrCancelDefinition
    }
    assert counts == {
        GovernedPaperCtrCancelDefinition.FULL_CANCEL_ONLY: 1,
        GovernedPaperCtrCancelDefinition.FULL_CANCEL_AND_PARTIAL_REDUCTION: 2,
        GovernedPaperCtrCancelDefinition.FULL_CANCEL_PARTIAL_REDUCTION_AND_AMEND: 3,
    }


def test_zero_trades_and_uncovered_or_broken_windows_are_blocked(test_only: None) -> None:
    assert read(context(window_events(3, 0))).reason == "zero_trades_in_the_window_ctr_undefined"  # T-CTR-06
    no_anchor = window_events(2, 2, anchor=T - WINDOW + SECOND // 2)  # nothing published at or before T - 60 s
    assert read(context(no_anchor)).reason == "window_start_not_observed"  # T-CTR-05
    rows = window_events(2, 3)
    gap = [item if item.sequence_id < 3 else replace(item, sequence_id=item.sequence_id + 1) for item in rows]
    assert read(context(gap)).reason == "sequence_gap_in_the_window"  # T-CTR-04
    duplicate = [*rows, replace(rows[2], receipt_time_ns=rows[2].receipt_time_ns + 1)]
    assert read(context(duplicate)).reason == "sequence_duplicate_in_the_window"
    swapped = [
        *rows[:2],
        replace(rows[2], publication_time_ns=rows[1].publication_time_ns - 1, receipt_time_ns=rows[2].receipt_time_ns),
        *rows[3:],
    ]
    assert read(context(swapped)).reason == "sequence_reordered_in_the_window"
    assert read(context(rows, through=T - 1)).reason == "capture_not_complete_at_the_reading_instant"


def test_a_record_received_or_published_after_the_reading_instant_is_excluded(test_only: None) -> None:
    rows = window_events(10, 4)
    late_receipt = [*rows, record(15, K.ORDER_CANCEL_FULL, T - SECOND, T + SECOND)]  # T-CTR-10
    later = [*rows, record(15, K.ORDER_CANCEL_FULL, T + SECOND)]
    for extra in (late_receipt, later):
        reading = read(context(extra, through=T + SECOND))
        assert (reading.available, reading.cancel_count, reading.trade_count) == (True, 10, 4)
    # read one second later, the late-received cancel counts, and the first cancel (at T - 59 s) left the window
    after = read(context(late_receipt, through=T + SECOND), T + SECOND)
    assert (after.cancel_count, after.trade_count) == (10, 4)


def received(*rows: GovernedPaperCtrSourceRecord, through: int = T, **changes: object) -> GovernedPaperCtrSourceContext:
    """A context whose capture holds ``rows`` in exactly this receipt order. The capture builder never sorts, and the
    capture is intact whatever order the sequence ids arrive in: its digest integrity is never the reading's coverage."""

    q = qualification(**changes)
    capture = build_governed_paper_ctr_source_capture(
        capture_id="synthetic-capture-1", qualification=q, complete_through_receipt_ns=through, records=rows
    )
    assert verify_governed_paper_ctr_source_capture(capture, q).intact
    return GovernedPaperCtrSourceContext(qualification=q, revocations=(), capture=capture)


def test_sequence_progression_is_judged_in_receipt_order_and_never_by_a_sort(test_only: None) -> None:
    anchor = record(0, K.ORDER_ADD, T - 100 * SECOND)
    cancel = record(1, K.ORDER_CANCEL_FULL, T - 40 * SECOND)
    trade = record(2, K.TRADE, T - 30 * SECOND)
    in_order = read(received(anchor, cancel, trade))
    assert (in_order.available, in_order.cancel_count, in_order.trade_count) == (True, 1, 1)
    # Sol B2: received [0, 2, 1] while published [0, 1, 2]; a sort by sequence id read it as covered (1/1, alpha 1)
    late_cancel = replace(cancel, receipt_time_ns=T - 20 * SECOND)
    reordered = received(anchor, trade, late_cancel)
    reading = read(reordered)
    assert (reading.available, reading.reason, reading.alpha) == (False, "sequence_reordered_in_the_window", None)
    # between the two receipts the cancel is missing (a gap), and its late receipt never rewrites that earlier reading
    between = T - 25 * SECOND
    assert read(reordered, between) == read(received(anchor, trade, through=between), between)
    assert read(reordered, between).reason == "sequence_gap_in_the_window"
    # an authentic depth never turns the reorder into a PASS: without a CTR reading there is no cap
    depth = GovernedPaperDepthIndex(rst.book_dataset([tight(T - SECOND, T - SECOND)]), instrument=INS).at(T, BUY)
    order = Fraction(50)  # below 2% of the depth 4100 (82)
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=depth, ctr=in_order).status is D_PASS
    blocked = evaluate_governed_paper_ctr_depth(quantity=order, depth=depth, ctr=reading)
    assert (blocked.status, blocked.reason) == (D_BLOCKED, "ctr_unavailable:sequence_reordered_in_the_window")
    assert governed_paper_ctr_depth_cap(depth, reading) is None


def test_a_reorder_across_the_window_start_after_the_anchor_or_inside_a_receipt_tie_is_blocked(test_only: None) -> None:
    head = record(0, K.ORDER_ADD, T - 90 * SECOND)
    cases = {
        # the record anchoring the window start (published at T - 61 s) received after a record published inside it
        "anchor_received_after_a_window_record": (
            head,
            record(2, K.TRADE, T - 30 * SECOND),
            record(1, K.ORDER_ADD, T - 61 * SECOND, T - 25 * SECOND),
        ),
        # an older record (published before the window) received after the anchor and a window record
        "older_record_received_after_the_anchor": (
            head,
            record(2, K.ORDER_ADD, T - 70 * SECOND),
            record(3, K.TRADE, T - 30 * SECOND),
            record(1, K.ORDER_ADD, T - 80 * SECOND, T - 20 * SECOND),
        ),
        # two records sharing a receipt instant in an order other than the sequence's: the tie is never sorted
        "receipt_tie_out_of_sequence_order": (
            head,
            record(2, K.TRADE, T - 30 * SECOND, T - 20 * SECOND),
            record(1, K.ORDER_CANCEL_FULL, T - 40 * SECOND, T - 20 * SECOND),
        ),
    }
    for name, rows in cases.items():
        assert read(received(*rows)).reason == "sequence_reordered_in_the_window", name
    tie = (
        head,
        record(1, K.ORDER_CANCEL_FULL, T - 40 * SECOND, T - 20 * SECOND),
        record(2, K.TRADE, T - 30 * SECOND, T - 20 * SECOND),
    )
    assert read(received(*tie)).available is True  # the same tie in the sequence's order
    duplicate = (*tie, record(1, K.ORDER_CANCEL_FULL, T - 40 * SECOND, T - 10 * SECOND))  # a late repeat
    assert read(received(*duplicate)).reason == "sequence_duplicate_in_the_window"
    # a reorder received wholly before the anchor lies outside the window and never blocks a later reading
    before = (
        head,
        record(2, K.ORDER_ADD, T - 88 * SECOND),
        record(1, K.ORDER_ADD, T - 89 * SECOND, T - 87 * SECOND),
        record(3, K.ORDER_ADD, T - 70 * SECOND),
        record(4, K.TRADE, T - 30 * SECOND),
    )
    assert read(received(*before)).available is True
    # under heartbeat coverage the sequence is still judged in receipt order before any heartbeat interval
    interval = 10 * SECOND
    beats = [record(index, K.HEARTBEAT, T - WINDOW - SECOND + index * interval) for index in range(6)]
    heartbeats = {
        "coverage_method": GovernedPaperCtrCoverageMethod.VENUE_HEARTBEATS,
        "heartbeat_max_interval_ns": interval,
    }
    swapped = (
        *beats[:4],
        beats[5],
        replace(beats[4], receipt_time_ns=T - 8 * SECOND),
        record(6, K.TRADE, T - 5 * SECOND),
    )
    assert read(received(*beats, record(6, K.TRADE, T - 5 * SECOND), **heartbeats)).available is True
    assert read(received(*swapped, **heartbeats)).reason == "sequence_reordered_in_the_window"


def test_a_reorder_received_after_the_decision_blocks_the_fill_reading_and_never_rewrites_the_decision(
    test_only: None,
) -> None:
    rows = window_events(10, 4)  # contiguous ids 0..14, covered at T
    after = (
        record(16, K.TRADE, T + SECOND // 4),
        record(15, K.ORDER_CANCEL_FULL, T + SECOND // 8, T + SECOND // 2),  # published before 16, received after it
    )
    decision = read(context(rows))
    fill_source = context([*rows, *after], through=T + SECOND)
    assert decision.available and read(fill_source) == decision  # T-CTR-10: receipts after T are invisible at T
    fill = read(fill_source, T + SECOND)
    assert (fill.available, fill.reason) == (False, "sequence_reordered_in_the_window")
    d1000, order = depth_of(1_000), Fraction(15)
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=d1000, ctr=decision).status is D_PASS
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=d1000, ctr=fill).status is D_BLOCKED
    assert governed_paper_ctr_depth_cap(d1000, fill) is None  # no fill-time cap: the engine refuses the fill (T-CTR-09)


def test_the_qualification_applies_only_from_its_approval_and_until_a_revocation_or_supersession(
    test_only: None,
) -> None:
    rows = window_events(10, 4)
    assert read(context(rows, approval_time_ns=T + 1)).reason == "qualification_not_yet_approved_at_the_reading_instant"
    base = qualification()
    for kind in GovernedPaperCtrRevocationKind:
        revocation = build_governed_paper_ctr_qualification_revocation(
            revocation_id=f"synthetic-{kind.value.lower()}",
            qualification_digest=base.qualification_digest,
            kind=kind,
            effective_from_ns=T,
            approval_kind=SYNTHETIC,
            approver_reference="synthetic-test-fixture",
        )
        assert verify_governed_paper_ctr_qualification_revocation(revocation).intact
        source = context(rows, revocations=(revocation,))
        assert read(source, T - 1).available is True
        assert read(source).reason == f"qualification_{kind.value.lower()}_at_the_reading_instant"  # T-CTR-07


def test_source_rights_must_permit_this_use_and_its_processing(test_only: None) -> None:
    rows = window_events(10, 4)
    for changes in ({"processing_by_this_system_permitted": False}, {"permitted_uses": ("another_use",)}):
        assert read(context(rows, **changes)).reason == "source_rights_do_not_permit_this_use"


def test_heartbeat_coverage_needs_no_publication_gap_above_its_interval(test_only: None) -> None:
    interval = 10 * SECOND
    beats = [record(index, K.HEARTBEAT, T - WINDOW - SECOND + index * interval) for index in range(6)]  # to T - 11 s
    covered = context(
        [*beats, record(6, K.TRADE, T - 5 * SECOND)],
        coverage_method=GovernedPaperCtrCoverageMethod.VENUE_HEARTBEATS,
        heartbeat_max_interval_ns=interval,
    )
    assert read(covered).available is True
    stalled = context(
        [*beats[:4], record(4, K.TRADE, T - 5 * SECOND)],
        coverage_method=GovernedPaperCtrCoverageMethod.VENUE_HEARTBEATS,
        heartbeat_max_interval_ns=interval,
    )
    assert read(stalled).reason == "heartbeat_coverage_gap_in_the_window"


def test_published_counts_count_only_when_they_tile_the_window_exactly(test_only: None) -> None:
    counts = {"source_class": GovernedPaperCtrSourceClass.VENUE_PUBLISHED_COUNTS}

    def published(sequence: int, start: int, end: int, cancels: int, trades: int):  # noqa: ANN202
        return record(
            sequence,
            K.PUBLISHED_COUNTS,
            end,
            interval_start_ns=start,
            interval_end_ns=end,
            cancel_count=cancels,
            trade_count=trades,
        )

    anchor = record(0, K.HEARTBEAT, T - WINDOW - SECOND)
    tiled = [anchor, published(1, T - WINDOW, T - 30 * SECOND, 6, 2), published(2, T - 30 * SECOND, T, 9, 1)]
    reading = read(context(tiled, **counts))
    assert (reading.cancel_count, reading.trade_count, Fraction(reading.ctr)) == (15, 3, Fraction(5))  # type: ignore[arg-type]
    misaligned = [
        anchor,
        published(1, T - WINDOW + SECOND, T - 30 * SECOND, 6, 2),
        published(2, T - 30 * SECOND, T, 9, 1),
    ]
    assert read(context(misaligned, **counts)).reason == "published_counts_do_not_tile_the_window"
    with pytest.raises(GovernedPaperCtrError, match="record_kind_not_of_the_source_class$"):
        context([anchor, record(1, K.TRADE, T - SECOND)], **counts)


# --- C. the capture and the context ------------------------------------------------------------------------------------------


def test_a_capture_is_bound_to_its_qualification_source_and_refuses_a_foreign_one() -> None:
    source = context(window_events(2, 2))
    capture = source.capture
    assert verify_governed_paper_ctr_source_capture(capture, source.qualification).intact
    other = qualification(venue="another-venue")  # wrong venue: another source (T: wrong venue)
    assert verify_governed_paper_ctr_source_capture(capture, other).intact is False
    with pytest.raises(GovernedPaperCtrError, match="ctr_capture_not_authentic$"):
        governed_paper_ctr_canonical_context(replace(source, qualification=other), instrument=INS)
    with pytest.raises(GovernedPaperCtrError, match="ctr_qualification_of_another_instrument$"):
        governed_paper_ctr_canonical_context(source, instrument="ETH-USDT-PERP")
    stranger = build_governed_paper_ctr_qualification_revocation(
        revocation_id="synthetic-foreign",
        qualification_digest=other.qualification_digest,
        kind=GovernedPaperCtrRevocationKind.REVOKED,
        effective_from_ns=T,
        approval_kind=SYNTHETIC,
        approver_reference="synthetic-test-fixture",
    )
    with pytest.raises(GovernedPaperCtrError, match="ctr_revocation_foreign$"):
        governed_paper_ctr_canonical_context(replace(source, revocations=(stranger,)), instrument=INS)
    tampered = replace(capture, records=capture.records[:-1])
    assert verify_governed_paper_ctr_source_capture(tampered, source.qualification).intact is False


@pytest.mark.parametrize(
    ("rows", "through", "reason"),
    [
        ([record(0, K.TRADE, T, T - 1)], T, "record_received_before_its_publication"),
        ([record(0, K.TRADE, T)], T - 1, "record_received_after_the_completeness_instant"),
        (
            [record(0, K.TRADE, T, interval_start_ns=0, interval_end_ns=1, cancel_count=1, trade_count=1)],
            T,
            "counts_on_a_record_that_is_not_published_counts",
        ),
    ],
)
def test_a_malformed_capture_is_refused(rows: list, through: int, reason: str) -> None:
    with pytest.raises(GovernedPaperCtrError, match=f"{reason}$"):
        build_governed_paper_ctr_source_capture(
            capture_id="synthetic-capture-1",
            qualification=qualification(),
            complete_through_receipt_ns=through,
            records=tuple(rows),
        )


def test_the_reading_reads_only_the_qualified_source_never_an_order_book() -> None:
    parameters = list(inspect.signature(governed_paper_ctr_reading).parameters)
    assert parameters == ["context", "instrument", "time_ns"]  # no dataset: no count can come from L2 changes
    source = inspect.getsource(ctr)
    tree = ast.parse(source)
    modules = {
        alias.name.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    modules |= {
        node.module.split(".")[0] for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module
    }
    assert modules <= {"__future__", "bisect", "collections", "dataclasses", "enum", "fractions", "crypto_core"}
    for forbidden in ("float(", "Decimal", "import random", "import time", "open(", "import os", "socket"):
        assert forbidden not in source


# --- D. the visible depth and the depth cap (§1.12 Mechanism 2, §7.2, §5) -------------------------------------------------------


def tight(event: int, visible: int, levels: int = 50):  # noqa: ANN201
    """A SYNTHETIC tip at mid 100 with a 0.001 tick: 41 levels per side lie inside the 5 bps band (100 +- 0.05)."""

    return rst.book_record(
        event, visible, Fraction("99.99"), Fraction("100.01"), Fraction(100), Fraction(1, 1000), levels
    )


def test_the_visible_depth_is_the_band_quantity_of_the_side_the_order_consumes() -> None:
    record_ = tight(T - SECOND, T - SECOND)
    index = GovernedPaperDepthIndex(rst.book_dataset([record_]), instrument=INS)
    for side in (BUY, SELL):
        depth = index.at(T, side)
        # oracle: asks 100.010..100.050 (and bids 99.990..99.950) every 0.001, each 100: 41 levels, the edge included
        assert (Fraction(depth.depth), depth.exact, depth.book_record_digest) == (  # type: ignore[arg-type]
            Fraction(4_100),
            True,
            record_.record_digest,
        )
    assert index.of_record(record_.record_digest, BUY) == index.at(T, BUY)
    wide = rst.book_record(
        T - SECOND, T - SECOND, Fraction("99.995"), Fraction("100.005"), Fraction(100), Fraction(1, 10_000)
    )
    lower = GovernedPaperDepthIndex(rst.book_dataset([wide]), instrument=INS).at(T, BUY)
    # 50 levels of 0.0001 end at 100.0099, inside the band: only a lower bound of the depth
    assert (Fraction(lower.depth), lower.exact) == (Fraction(5_000), False)  # type: ignore[arg-type]
    assert lower.reason == "depth_50_tip_does_not_cover_the_5bps_band_lower_bound_only"


def test_a_stale_absent_or_foreign_tip_gives_no_depth() -> None:
    record_ = tight(T - 11 * SECOND, T - 11 * SECOND)
    index = GovernedPaperDepthIndex(rst.book_dataset([record_]), instrument=INS)
    assert index.at(T, BUY).reason == "order_book_tip_older_than_10s"
    assert index.at(T - 12 * SECOND, BUY).reason == "no_order_book_tip_visible_at_the_instant"
    assert index.of_record("3" * 64, BUY).reason == "book_record_not_in_the_series"
    late = GovernedPaperDepthIndex(rst.book_dataset([tight(T - SECOND, T + SECOND)]), instrument=INS)
    assert late.at(T, BUY).reason == "no_order_book_tip_visible_at_the_instant"  # received after the decision


def forged_quantities(record_: object, factor: int):  # noqa: ANN201
    """``record_`` with every quantity multiplied by ``factor`` and its carried record digest KEPT: a forgery."""

    def scaled(text: str) -> str:
        whole, fraction = text.split(".")
        units = (int(whole) * 10**18 + int(fraction)) * factor
        return f"{units // 10**18}.{units % 10**18:018d}"

    values = tuple(
        HistoricalPitValue(item.name, scaled(item.value)) if item.name.endswith("_quantity") else item
        for item in record_.values  # type: ignore[attr-defined]
    )
    return replace(record_, values=values)  # type: ignore[type-var]


def restricted_dataset(records: list):  # noqa: ANN201
    """``rst.book_dataset`` with restricted rights: READY, intact, and NOT advancing (verdict FAIL)."""

    manifest, _, registry = rst.ingt.world_chain()
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=rst.data_requirement_registry_digest(registry),
        dataset_id="synthetic-books",
        correlation_id="corr-1",
        source_reference="archive:synthetic-books",
        rights_status="restricted",
        rights_reference="license-1",
        records=tuple(records),
    )


def test_the_depth_index_re_proves_the_whole_dataset_so_a_forged_quantity_never_turns_fail_into_pass(
    test_only: None,
) -> None:
    original = tight(T - SECOND, T - SECOND)
    dataset = rst.book_dataset([original])
    qualified = read(context(window_events(10, 4)))  # alpha 1
    order = Fraction(100)
    index = GovernedPaperDepthIndex(dataset, instrument=INS)
    depth = index.at(T, BUY)
    assert (index.dataset_digest, Fraction(depth.depth), governed_paper_ctr_depth_cap(depth, qualified)) == (  # type: ignore[arg-type]
        dataset.dataset_digest,
        Fraction(4_100),
        Fraction(82),
    )
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=depth, ctr=qualified).status is D_FAIL
    # Sol B1: every quantity x100 under the carried record digest, record digests and dataset digest. Read through the
    # manifest alone it was depth 410000, cap 8200 and a PASS of the same order.
    altered = forged_quantities(dataset.records[0], 100)
    forged = replace(dataset, records=(altered,))
    assert (altered.record_digest, forged.record_digests, forged.dataset_digest) == (
        original.record_digest,
        dataset.record_digests,
        dataset.dataset_digest,
    )
    assert historical_pit_record_digest(altered) != altered.record_digest
    assert historical_pit_dataset_digest(forged) != forged.dataset_digest
    assert governed_paper_order_book_series(forged, INS) == ("", "book")  # its manifest alone still re-proves
    assert verify_historical_pit_dataset(forged).intact is False
    with pytest.raises(GovernedPaperCtrError, match="depth_dataset_not_authentic$"):
        GovernedPaperDepthIndex(forged, instrument=INS)  # no index: no at(), of_record() or records_visible_between()
    assert GovernedPaperDepthIndex(dataset, instrument=INS).at(T, BUY) == depth  # the authentic reading is unchanged


def test_a_dataset_that_does_not_re_prove_whole_yields_no_index_and_a_rebuilt_one_is_another_artifact() -> None:
    first, second = tight(T - 2 * SECOND, T - 2 * SECOND), tight(T - SECOND, T - SECOND)
    dataset = rst.book_dataset([first, second])
    altered = forged_quantities(dataset.records[1], 100)
    redigested = replace(altered, record_digest=historical_pit_record_digest(altered))
    stale = rst.book_dataset([first, altered])  # assembled over the stale record digest: intact, yet REJECTED
    restricted = restricted_dataset([first, second])
    assert (verify_historical_pit_dataset(stale).intact, stale.status, stale.advances) == (
        True,
        EdgeEvidenceStatus.REJECTED,
        False,
    )
    assert (verify_historical_pit_dataset(restricted).intact, restricted.status, restricted.advances) == (
        True,
        EdgeEvidenceStatus.READY,
        False,
    )
    candidates = {
        "quantity_under_the_carried_digests": replace(dataset, records=(first, altered)),
        "record_redigested_under_the_carried_record_set": replace(dataset, records=(first, redigested)),
        "record_set_redigested_under_the_carried_dataset_digest": replace(
            dataset, records=(first, redigested), record_digests=(first.record_digest, redigested.record_digest)
        ),
        "record_removed_under_the_carried_record_set": replace(dataset, records=(first,)),
        "carried_dataset_digest_replaced": replace(dataset, dataset_digest="5" * 64),
        "assembled_over_the_stale_record_digest": stale,
        "restricted_rights_not_advancing": restricted,
    }
    accepted = []
    for name, candidate in candidates.items():
        try:
            GovernedPaperDepthIndex(candidate, instrument=INS)
        except GovernedPaperCtrError as exc:
            assert str(exc).endswith("depth_dataset_not_authentic"), name
        else:
            accepted.append(name)
    assert accepted == []
    with pytest.raises(GovernedPaperCtrError, match="depth_inputs_malformed$"):
        GovernedPaperDepthIndex(object(), instrument=INS)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="depth_index_is_final$"):  # no subclass can skip the verification
        type("UnverifiedDepthIndex", (GovernedPaperDepthIndex,), {})
    # a rebuild over the altered quantities is a NEW artifact with its own digests, never the original record's identity
    index, renewed = (
        GovernedPaperDepthIndex(dataset, instrument=INS),
        GovernedPaperDepthIndex(rst.book_dataset([first, redigested]), instrument=INS),
    )
    assert renewed.dataset_digest != index.dataset_digest == dataset.dataset_digest
    assert (Fraction(index.at(T, BUY).depth), Fraction(renewed.at(T, BUY).depth)) == (  # type: ignore[arg-type]
        Fraction(4_100),
        Fraction(410_000),
    )
    assert renewed.at(T, BUY).book_record_digest == redigested.record_digest != second.record_digest
    assert renewed.of_record(second.record_digest, BUY).reason == "book_record_not_in_the_series"
    assert index.of_record(redigested.record_digest, BUY).reason == "book_record_not_in_the_series"


def depth_of(value: object, exact: bool = True) -> GovernedPaperVisibleDepth:  # noqa: FBT001, FBT002
    return GovernedPaperVisibleDepth(BUY, "4" * 64, str(Fraction(value)), exact, "" if exact else "lower_bound")  # type: ignore[arg-type]


def test_the_depth_cap_is_strict_at_2pct_and_needs_a_qualified_reading_to_pass(test_only: None) -> None:
    qualified = read(context(window_events(10, 4)))  # alpha 1
    reduced = read(context(window_events(40, 4)))  # alpha 1/2
    unavailable = read(None)
    d1000 = depth_of(1_000)

    def status(quantity: object, depth: GovernedPaperVisibleDepth, reading: object) -> tuple:
        result = evaluate_governed_paper_ctr_depth(quantity=Fraction(quantity), depth=depth, ctr=reading)  # type: ignore[arg-type]
        return result.status, result.reason

    assert status(20, d1000, unavailable) == (
        D_FAIL,
        "order_at_or_above_2pct_of_the_unadjusted_visible_depth",
    )  # T-CTR-02
    assert status(20, d1000, qualified)[0] is D_FAIL  # strict: equality fails, whatever the CTR
    assert status(Fraction(20) - Fraction(1, 10**18), d1000, qualified) == (
        D_PASS,
        "order_below_2pct_of_the_ctr_adjusted_visible_depth",
    )
    assert status(10, d1000, reduced)[0] is D_BLOCKED  # at 2% x alpha (1/2) x D: not below the adjusted cap
    assert status(Fraction(10) - Fraction(1, 10**18), d1000, reduced)[0] is D_PASS
    assert status(15, d1000, reduced) == (D_BLOCKED, "order_not_below_2pct_of_the_ctr_adjusted_visible_depth")
    assert status(5, d1000, unavailable)[1] == "ctr_unavailable:no_ctr_source_supplied"
    # a lower bound of the depth never proves a FAIL, and still proves a PASS below its own cap
    assert status(25, depth_of(1_000, exact=False), qualified)[0] is D_BLOCKED
    assert status(19, depth_of(1_000, exact=False), qualified)[0] is D_PASS
    blocked = evaluate_governed_paper_ctr_depth(
        quantity=Fraction(1),
        depth=GovernedPaperVisibleDepth(BUY, None, None, False, "order_book_tip_older_than_10s"),
        ctr=qualified,
    )
    assert (blocked.status, blocked.reason) == (D_BLOCKED, "visible_depth_unavailable:order_book_tip_older_than_10s")
    assert (
        evaluate_governed_paper_ctr_depth(quantity=None, depth=d1000, ctr=qualified).reason
        == "order_quantity_unavailable"
    )
    assert governed_paper_ctr_depth_cap(d1000, qualified) == Fraction(20)
    assert governed_paper_ctr_depth_cap(d1000, reduced) == Fraction(10)


def test_the_decision_and_fill_readings_are_separate_instants(test_only: None) -> None:
    # PASS at the decision (alpha 1), refused at the fill a second later once a burst of cancels lifts the CTR (T-CTR-09)
    rows = window_events(10, 4)
    burst = [record(15 + index, K.ORDER_CANCEL_FULL, T + SECOND // 2) for index in range(30)]
    source = context([*rows, *burst], through=T + SECOND)
    decision, fill = read(source), read(source, T + SECOND)
    assert (decision.cancel_count, decision.trade_count, Fraction(decision.alpha)) == (10, 4, Fraction(1))  # type: ignore[arg-type]
    # at the fill: 9 + 30 cancels over 4 trades, CTR 39/4, alpha 1 / (1 + 0.2 x (39/4 - 5)) = 20/39
    assert (fill.cancel_count, fill.trade_count, Fraction(fill.alpha)) == (39, 4, Fraction(20, 39))  # type: ignore[arg-type]
    d1000 = depth_of(1_000)
    order = Fraction(15)
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=d1000, ctr=decision).status is D_PASS
    assert evaluate_governed_paper_ctr_depth(quantity=order, depth=d1000, ctr=fill).status is D_BLOCKED
    assert order >= governed_paper_ctr_depth_cap(d1000, fill)  # type: ignore[operator]  # the engine refuses the fill
