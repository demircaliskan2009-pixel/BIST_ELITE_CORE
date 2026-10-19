"""Tests for the free-first observed PIT ingress core (FREE_FIRST_OBSERVED_PIT_INGRESS_CORE_V1).

Every observation below is a SYNTHETIC_TEST_ONLY construction fixture. Passing tests prove code semantics only, never
source authenticity, genuine market depth, real elapsed time, profitability or paper operation.
"""

from __future__ import annotations

import functools
import inspect
import json
from dataclasses import fields, replace
from fractions import Fraction

import pytest

import crypto_core.validation.observed_pit_ingress as ingress_module
from crypto_core.data.requirements import (
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import SourcePacketRightsStatus, build_source_packet
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus, EdgeGateVerdict
from crypto_core.validation.edge_idea_intake_evidence import (
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_source_packet_evidence import EdgeInputSeries, build_edge_source_packet_evidence
from crypto_core.validation.historical_execution_economics import verify_historical_execution_economics
from crypto_core.validation.historical_pit_dataset import select_visible_pit_records, verify_historical_pit_dataset
from crypto_core.validation.observed_pit_ingress import (
    OBSERVED_PIT_BOOK_DEPTH,
    OBSERVED_PIT_CONTINUITY_PROFILE_ID,
    OBSERVED_PIT_INGRESS_CONTRACT_ID,
    OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS,
    ObservedBookDelta,
    ObservedBookLevel,
    ObservedBookSnapshot,
    ObservedBookStream,
    ObservedDisconnect,
    ObservedFundingSettlement,
    ObservedFundingStream,
    ObservedMarkObservation,
    ObservedMarkStream,
    ObservedPitIngressError,
    ObservedPitIngressEvidence,
    ObservedPitIngressInputs,
    ObservedPitIngressResult,
    ObservedSourceDeclaration,
    ObservedSourceObject,
    build_observed_pit_ingress,
    observed_pit_continuity_profile,
    observed_pit_continuity_profile_digest,
    observed_pit_implemented_series_semantics,
    observed_pit_ingress_digest,
    observed_pit_ingress_to_dict,
    verify_observed_pit_ingress,
)

try:  # the module objects pytest collects (basename import), so cached authentic fixtures are shared
    import test_historical_execution_economics as econ
    import test_historical_pit_dataset as pit
except ImportError:  # outside a pytest session / importlib mode
    from tests.crypto_core.validation import test_historical_execution_economics as econ
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "observed_pit_ingress"
INS = econ.INS
BASE = econ.BASE
INTERVAL = econ.INTERVAL
d = econ.d
TICK = Fraction(1, 100)
LEVELS = 300
ANCHOR = 1_000
SNAPSHOT_RECEIPT = BASE - 5
STEPS = 101
BOOK, MARK, FUNDING, PUBLICATION = (
    "synthetic-book-capture",
    "synthetic-mark-capture",
    "synthetic-funding-history",
    "synthetic-funding-publication-capture",
)


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


# --- SYNTHETIC_TEST_ONLY native observations -----------------------------------------------------------------------------


def lvl(price: Fraction, quantity: object = 100) -> ObservedBookLevel:
    return ObservedBookLevel(d(price), d(quantity))


def snapshot(
    *,
    levels: int = LEVELS,
    last_update_id: int = ANCHOR,
    receipt: int = SNAPSHOT_RECEIPT,
    shift: int = 0,
    bids: tuple[ObservedBookLevel, ...] | None = None,
    asks: tuple[ObservedBookLevel, ...] | None = None,
) -> ObservedBookSnapshot:
    """A full-depth book; ``shift`` ticks reproduce the state the moving chain reaches after that many steps."""

    best_bid, best_ask = Fraction("99.95") + TICK * shift, Fraction("100.05") + TICK * shift
    bid_levels = tuple(lvl(best_bid - TICK * i) for i in range(levels)) if bids is None else bids
    ask_levels = tuple(lvl(best_ask + TICK * i) for i in range(levels)) if asks is None else asks
    return ObservedBookSnapshot(BOOK, receipt, receipt - 5, last_update_id, bid_levels, ask_levels)


def step(
    j: int,
    *,
    first: int,
    final: int,
    previous: int,
    event: int | None = None,
    receipt: int | None = None,
    bids: tuple[ObservedBookLevel, ...] | None = None,
    asks: tuple[ObservedBookLevel, ...] | None = None,
) -> ObservedBookDelta:
    """Delta 0 restates the best bid quantity; delta j >= 1 moves the whole book up one tick."""

    event = BASE + j * 1_000 + 500 if event is None else event
    receipt = event + 1 if receipt is None else receipt
    if bids is None and asks is None:
        if j == 0:
            bids, asks = (lvl(Fraction("99.95"), 101),), ()
        else:
            bids = (lvl(Fraction("99.95") + TICK * j),)
            asks = (lvl(Fraction("100.05") + TICK * (j - 1), 0),)
    return ObservedBookDelta(BOOK, receipt, event, first, final, previous, bids or (), asks or ())


def chain_steps(count: int = STEPS, *, start: int = 0, anchor: int = ANCHOR, offset: int = 0) -> tuple:
    """A native chain: its first delta straddles ``anchor``; every later one names its predecessor's final id."""

    deltas = []
    previous = anchor - 2
    for j in range(start, start + count):
        first, final = (anchor - 1, anchor + 1) if j == start else (previous + 1, previous + 2)
        deltas.append(step(j, first=first, final=final, previous=previous, event=BASE + j * 1_000 + 500 + offset))
        previous = final
    return tuple(deltas)


def book_stream(**overrides: object) -> ObservedBookStream:
    values: dict[str, object] = {
        "series_id": "book",
        "source_reference": "archive:book",
        "continuity_profile_id": OBSERVED_PIT_CONTINUITY_PROFILE_ID,
        "events": (snapshot(), *chain_steps()),
    }
    values.update(overrides)
    return ObservedBookStream(**values)  # type: ignore[arg-type]


def mark_stream(**overrides: object) -> ObservedMarkStream:
    values: dict[str, object] = {
        "series_id": "mark",
        "source_reference": "archive:mark",
        "observations": tuple(
            ObservedMarkObservation(MARK, BASE + j * 1_000 + 1, BASE + j * 1_000, d(econ.price(j)))
            for j in range(STEPS)
        ),
    }
    values.update(overrides)
    return ObservedMarkStream(**values)  # type: ignore[arg-type]


def settlements(*, publish_delay: int = 10, interval: int = INTERVAL) -> tuple[ObservedFundingSettlement, ...]:
    return tuple(
        ObservedFundingSettlement(
            FUNDING,
            f"synthetic-settlement-{k}",
            BASE + (k + 1) * interval,
            rate,
            PUBLICATION,
            BASE + (k + 1) * interval + publish_delay,
        )
        for k, rate in enumerate(econ.RATES)
    )


def funding_stream(**overrides: object) -> ObservedFundingStream:
    values: dict[str, object] = {
        "series_id": "funding-final",
        "source_reference": "archive:funding-final",
        "governed_interval_ns": INTERVAL,
        "interval_reference": "SYNTHETIC_TEST_ONLY interval of the synthetic economics policy fixture",
        "coverage_start_ns": BASE + INTERVAL,
        "coverage_end_ns": BASE + (len(econ.RATES) + 1) * INTERVAL,
        "settlements": settlements(),
    }
    values.update(overrides)
    return ObservedFundingStream(**values)  # type: ignore[arg-type]


def declaration(**overrides: object) -> ObservedSourceDeclaration:
    values: dict[str, object] = {
        "source_id": "synthetic-test-only-capture",
        "source_contract_reference": "SYNTHETIC_TEST_ONLY construction fixture, never a genuine source",
        "rights_status": SourcePacketRightsStatus.OWN_RESEARCH,
        "rights_reference": "note-1",
        "objects": tuple(
            ObservedSourceObject(object_id, digit * 64, 4_096)
            for object_id, digit in ((BOOK, "1"), (MARK, "2"), (FUNDING, "3"), (PUBLICATION, "4"))
        ),
    }
    values.update(overrides)
    return ObservedSourceDeclaration(**values)  # type: ignore[arg-type]


@functools.cache
def upstream():  # noqa: ANN201 - the accepted economics world's authentic EF-2/EF-3/EF-4 chain
    return econ.chain()


def inputs(**overrides: object) -> ObservedPitIngressInputs:
    manifest, _, registry = upstream()
    values: dict[str, object] = {
        "ingress_id": "ingress-1",
        "correlation_id": "corr-1",
        "dataset_id": "dataset-observed-1",
        "instrument": INS,
        "declaration": declaration(),
        "source_manifest": manifest,
        "expected_source_manifest_digest": manifest.source_packet_evidence_digest,
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry),
        "book": book_stream(),
        "mark": mark_stream(),
        "funding": funding_stream(),
    }
    values.update(overrides)
    return ObservedPitIngressInputs(**values)  # type: ignore[arg-type]


@functools.cache
def default_result() -> ObservedPitIngressResult:
    return build_observed_pit_ingress(inputs())


def with_book(*events: object, **overrides: object) -> ObservedPitIngressResult:
    return build_observed_pit_ingress(inputs(book=book_stream(events=events), **overrides))


def assert_rejected(result: ObservedPitIngressResult, *codes: str) -> None:
    evidence = result.evidence
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.REJECTED,
        EdgeGateVerdict.NOT_EVALUATED,
        False,
    )
    assert result.dataset is None
    assert evidence.dataset_digest == ""
    assert evidence.verdict_reason_codes == ()
    assert {_code(code) for code in codes} <= set(evidence.integrity_reason_codes), evidence.integrity_reason_codes


def book_records(result: ObservedPitIngressResult) -> list:
    assert result.dataset is not None
    return [record for record in result.dataset.records if record.series_id == "book"]


def values_of(record: object) -> dict[str, str]:
    return {item.name: item.value for item in record.values}  # type: ignore[attr-defined]


# --- the accepted path ---------------------------------------------------------------------------------------------------


def test_default_ingress_assembles_an_advancing_dataset_but_never_advances_itself() -> None:
    result = default_result()
    evidence = result.evidence
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.NEEDS_EXTERNAL_FACTS,
        False,
    )
    assert evidence.verdict_reason_codes == (
        _code(f"continuity_profile_not_qualified:{OBSERVED_PIT_CONTINUITY_PROFILE_ID}"),
    )
    assert evidence.integrity_reason_codes == ()
    dataset = result.dataset
    assert dataset is not None
    assert (dataset.status, dataset.gate_verdict, dataset.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert verify_historical_pit_dataset(dataset).intact is True
    assert evidence.dataset_digest == dataset.dataset_digest
    assert dataset.source_reference == f"observed-pit-ingress-declaration:{evidence.declaration_digest}"
    assert (dataset.rights_status, dataset.rights_reference) == ("own_research", "note-1")
    assert (evidence.book_record_count, evidence.mark_record_count, evidence.funding_record_count) == (101, 101, 10)
    assert len(dataset.records) == 212
    (segment,) = evidence.book_segments
    assert (segment.anchor_last_update_id, segment.applied_delta_count, segment.emitted_record_count) == (
        1_000,
        101,
        101,
    )
    assert (segment.stale_delta_count, segment.depth_ineligible_count, segment.horizon_ineligible_count) == (0, 0, 0)
    assert segment.end_reason == "end_of_input"
    assert (evidence.book_disconnect_count, evidence.book_gap_count, evidence.book_unanchored_delta_count) == (0, 0, 0)
    assert evidence.contract_id == OBSERVED_PIT_INGRESS_CONTRACT_ID
    assert verify_observed_pit_ingress(evidence, inputs()).intact is True


def test_book_records_are_native_identity_l2_fifty_level_ladders_available_at_receipt() -> None:
    records = book_records(default_result())
    finals = [1_001 + 2 * j for j in range(STEPS)]
    assert [record.sequence_id for record in records] == finals
    for j, record in enumerate(records):
        event = BASE + j * 1_000 + 500
        assert (record.event_time_ns, record.available_at_ns, record.finalized_at_ns) == (event, event + 1, event + 1)
        assert (record.data_requirement_key, record.instrument, record.revision_vintage_id) == ("order_book", INS, None)
        values = values_of(record)
        assert len(values) == 4 + 4 * OBSERVED_PIT_BOOK_DEPTH
        bids = [Fraction(values[f"bid_price_{level:02d}"]) for level in range(1, 51)]
        asks = [Fraction(values[f"ask_price_{level:02d}"]) for level in range(1, 51)]
        assert bids == sorted(bids, reverse=True) and len(set(bids)) == 50
        assert asks == sorted(asks) and len(set(asks)) == 50
        assert values["best_bid_price"] == values["bid_price_01"] == d(Fraction("99.95") + TICK * j)
        assert values["best_ask_price"] == values["ask_price_01"] == d(Fraction("100.05") + TICK * j)
        assert values["best_bid_quantity"] == values["bid_quantity_01"]
        assert values["best_ask_quantity"] == values["ask_quantity_01"]
    assert values_of(records[0])["best_bid_quantity"] == d(101)


def test_mark_and_funding_keep_event_receipt_and_finality_separate() -> None:
    dataset = default_result().dataset
    assert dataset is not None
    marks = [record for record in dataset.records if record.series_id == "mark"]
    for j, record in enumerate(marks):
        event = BASE + j * 1_000
        assert (record.sequence_id, record.event_time_ns, record.available_at_ns, record.finalized_at_ns) == (
            event,
            event,
            event + 1,
            event + 1,
        )
        assert values_of(record) == {"mark_price": d(econ.price(j))}
    funding = [record for record in dataset.records if record.series_id == "funding-final"]
    assert [record.sequence_id for record in funding] == list(range(len(econ.RATES)))
    for k, record in enumerate(funding):
        settlement = BASE + (k + 1) * INTERVAL
        assert (record.event_time_ns, record.available_at_ns, record.finalized_at_ns) == (
            settlement - INTERVAL,
            settlement + 10,
            settlement,
        )
        assert values_of(record) == {"funding_rate": econ.RATES[k]}
    evidence = default_result().evidence
    assert (evidence.book_sequence_identity, evidence.mark_sequence_identity, evidence.funding_sequence_identity) == (
        "native_final_update_id",
        "source_event_time_ns_not_a_native_sequence",
        "governed_settlement_grid_index_not_a_native_sequence",
    )


def test_ex_post_final_funding_is_invisible_before_its_observed_publication() -> None:
    result = build_observed_pit_ingress(inputs(funding=funding_stream(settlements=settlements(publish_delay=4_000))))
    dataset = result.dataset
    assert dataset is not None
    settlement = BASE + INTERVAL

    def visible(t: int) -> list[int]:
        view = select_visible_pit_records(dataset, series_id="funding-final", instrument=INS, decision_time_ns=t)
        return [record.sequence_id for record in view.records]

    assert visible(settlement) == []
    assert visible(settlement + 3_999) == []
    assert visible(settlement + 4_000) == [0]


def test_same_inputs_replay_to_identical_evidence_and_dataset() -> None:
    first, second = build_observed_pit_ingress(inputs()), build_observed_pit_ingress(inputs())
    assert first.evidence.ingress_digest == second.evidence.ingress_digest == default_result().evidence.ingress_digest
    assert observed_pit_ingress_to_dict(first.evidence) == observed_pit_ingress_to_dict(second.evidence)
    assert first.dataset is not None and second.dataset is not None
    assert first.dataset.dataset_digest == second.dataset.dataset_digest
    assert observed_pit_ingress_digest(first.evidence) == first.evidence.ingress_digest


def test_the_evidence_binds_the_exact_capture_not_only_its_emitted_records() -> None:
    tail = chain_steps(3, start=STEPS)
    altered = (replace(tail[0], bids=(lvl(Fraction("99.95"), 7),)), *tail[1:])
    events = (snapshot(), *chain_steps(), ObservedDisconnect(BOOK))
    first, second = with_book(*events, *tail), with_book(*events, *altered)
    assert first.dataset is not None and second.dataset is not None
    assert first.dataset.dataset_digest == second.dataset.dataset_digest
    assert first.evidence.book_unanchored_delta_count == second.evidence.book_unanchored_delta_count == 3
    assert first.evidence.observation_digest != second.evidence.observation_digest
    mismatch = verify_observed_pit_ingress(first.evidence, inputs(book=book_stream(events=(*events, *altered))))
    assert _code("field_mismatch:observation_digest") in mismatch.reason_codes


# --- native continuity -----------------------------------------------------------------------------------------------------


def test_buffered_deltas_are_available_only_at_their_anchoring_snapshot_receipt() -> None:
    early = (
        step(0, first=999, final=1_001, previous=998, event=SNAPSHOT_RECEIPT - 30, receipt=SNAPSHOT_RECEIPT - 20),
        step(1, first=1_002, final=1_003, previous=1_001, event=SNAPSHOT_RECEIPT - 15, receipt=SNAPSHOT_RECEIPT - 10),
    )
    later = tuple(
        step(j, first=1_002 + 2 * (j - 1), final=1_003 + 2 * (j - 1), previous=1_001 + 2 * (j - 1)) for j in range(2, 5)
    )
    records = book_records(with_book(*early, snapshot(), *later))
    assert [record.sequence_id for record in records] == [1_001, 1_003, 1_005, 1_007, 1_009]
    assert [record.available_at_ns for record in records[:2]] == [SNAPSHOT_RECEIPT, SNAPSHOT_RECEIPT]
    assert [record.event_time_ns for record in records[:2]] == [SNAPSHOT_RECEIPT - 30, SNAPSHOT_RECEIPT - 15]
    assert all(record.available_at_ns == record.event_time_ns + 1 for record in records[2:])


def test_stale_deltas_below_the_anchor_are_dropped_before_the_straddling_delta() -> None:
    stale = step(0, first=991, final=995, previous=990, event=SNAPSHOT_RECEIPT - 40, receipt=SNAPSHOT_RECEIPT - 30)
    result = with_book(stale, snapshot(), *chain_steps())
    (segment,) = result.evidence.book_segments
    assert (segment.stale_delta_count, segment.applied_delta_count, segment.emitted_record_count) == (1, 101, 101)
    assert [record.sequence_id for record in book_records(result)][0] == 1_001


def test_the_first_applied_delta_must_straddle_the_snapshot_anchor() -> None:
    assert_rejected(
        with_book(snapshot(), step(0, first=1_002, final=1_003, previous=1_001)), "book_snapshot_alignment_failed:1"
    )


def test_a_predecessor_gap_without_a_disconnect_rejects() -> None:
    deltas = list(chain_steps(10))
    deltas[5] = replace(deltas[5], previous_final_update_id=deltas[5].previous_final_update_id - 1)
    assert_rejected(with_book(snapshot(), *deltas), "book_sequence_gap_without_disconnect:end")
    assert_rejected(
        with_book(snapshot(), *deltas, snapshot(last_update_id=5_000, receipt=BASE + 50_000)),
        "book_sequence_gap_without_disconnect:11",
    )


def test_a_gap_then_disconnect_then_snapshot_resynchronizes_into_two_segments() -> None:
    first = list(chain_steps(10))
    first[5] = replace(first[5], previous_final_update_id=first[5].previous_final_update_id - 1)
    resync_receipt = BASE + 20_000
    second = chain_steps(5, start=20, anchor=2_000)
    resync = snapshot(last_update_id=2_000, receipt=resync_receipt, shift=19)
    result = with_book(snapshot(), *first, ObservedDisconnect(BOOK), resync, *second)
    evidence = result.evidence
    assert evidence.status is EdgeEvidenceStatus.READY
    assert [segment.end_reason for segment in evidence.book_segments] == ["gap_then_disconnect", "end_of_input"]
    assert [segment.emitted_record_count for segment in evidence.book_segments] == [5, 5]
    assert (evidence.book_gap_count, evidence.book_invalidated_delta_count, evidence.book_disconnect_count) == (1, 5, 1)
    sequence = [record.sequence_id for record in book_records(result)]
    assert sequence == sorted(sequence) and len(set(sequence)) == 10
    assert sequence[:5] == [1_001, 1_003, 1_005, 1_007, 1_009] and sequence[5] == 2_001
    assert all(record.available_at_ns >= resync_receipt for record in book_records(result)[5:])


def test_a_disconnect_requires_a_new_snapshot_before_any_further_admission() -> None:
    deltas = chain_steps(10)
    result = with_book(snapshot(), *deltas[:5], ObservedDisconnect(BOOK), *deltas[5:])
    assert result.evidence.status is EdgeEvidenceStatus.READY
    assert [record.sequence_id for record in book_records(result)] == [1_001, 1_003, 1_005, 1_007, 1_009]
    assert (result.evidence.book_unanchored_delta_count, result.evidence.book_disconnect_count) == (5, 1)
    assert [segment.end_reason for segment in result.evidence.book_segments] == ["disconnect"]


def test_a_snapshot_without_a_disconnect_is_an_unjustified_resync() -> None:
    deltas = chain_steps(4)
    assert_rejected(
        with_book(snapshot(), *deltas, snapshot(last_update_id=5_000, receipt=BASE + 50_000)),
        "book_unjustified_resync:5",
    )


def test_native_regression_replay_reorder_and_malformed_ids_reject() -> None:
    deltas = list(chain_steps(6))
    assert_rejected(with_book(snapshot(), *deltas[:4], deltas[3], *deltas[4:]), "book_sequence_regression:5")
    reordered = [*deltas[:2], deltas[3], deltas[2], *deltas[4:]]
    assert_rejected(with_book(snapshot(), *reordered), "book_receipt_time_regression:4")
    times = ("receipt_ns", "event_time_ns")
    swapped = [
        *deltas[:2],
        replace(deltas[3], **{name: getattr(deltas[2], name) for name in times}),
        replace(deltas[2], **{name: getattr(deltas[3], name) for name in times}),
        *deltas[4:],
    ]
    assert_rejected(with_book(snapshot(), *swapped), "book_sequence_gap_without_disconnect:end")
    overlapping = replace(deltas[1], previous_final_update_id=deltas[1].first_update_id)
    assert_rejected(with_book(snapshot(), deltas[0], overlapping), "book_delta_sequence_malformed:2")
    inverted = replace(deltas[1], first_update_id=deltas[1].final_update_id + 1)
    assert_rejected(with_book(snapshot(), deltas[0], inverted), "book_delta_sequence_malformed:2")
    stale_snapshot = snapshot(last_update_id=1_004, receipt=BASE + 50_000)
    assert_rejected(
        with_book(snapshot(), *deltas, ObservedDisconnect(BOOK), stale_snapshot), "book_snapshot_regression:8"
    )


@pytest.mark.parametrize("value", [None, True, "1001", -1, 1.0, 2**63])
def test_a_missing_or_malformed_native_sequence_field_raises(value: object) -> None:
    broken = replace(chain_steps(1)[0], final_update_id=value)
    with pytest.raises(ObservedPitIngressError, match="delta_final_update_id_invalid"):
        with_book(snapshot(), broken)


@pytest.mark.parametrize("value", [None, True, "1", 0, 1.0, 2**63])
def test_a_missing_or_malformed_receipt_time_raises(value: object) -> None:
    with pytest.raises(ObservedPitIngressError, match="book_receipt_ns_invalid"):
        with_book(replace(snapshot(), receipt_ns=value), *chain_steps(1))
    marks = mark_stream().observations
    with pytest.raises(ObservedPitIngressError, match="mark_receipt_ns_invalid"):
        build_observed_pit_ingress(inputs(mark=mark_stream(observations=(replace(marks[0], receipt_ns=value),))))


def test_receipt_regression_and_event_after_receipt_reject() -> None:
    deltas = list(chain_steps(4))
    deltas[2] = replace(deltas[2], receipt_ns=deltas[1].receipt_ns - 1, event_time_ns=deltas[1].receipt_ns - 2)
    assert_rejected(with_book(snapshot(), *deltas), "book_receipt_time_regression:3")
    ahead = replace(chain_steps(1)[0], event_time_ns=chain_steps(1)[0].receipt_ns + 1)
    assert_rejected(with_book(snapshot(), ahead), "book_event_after_receipt:1")
    marks = list(mark_stream().observations)
    marks[3] = replace(marks[3], event_time_ns=marks[3].receipt_ns + 1)
    assert_rejected(
        build_observed_pit_ingress(inputs(mark=mark_stream(observations=tuple(marks)))), "mark_event_after_receipt:3"
    )
    marks = list(mark_stream().observations)
    marks[3] = replace(marks[3], receipt_ns=marks[2].receipt_ns - 1, event_time_ns=marks[2].receipt_ns - 2)
    assert_rejected(
        build_observed_pit_ingress(inputs(mark=mark_stream(observations=tuple(marks)))),
        "mark_receipt_time_regression:3",
    )


# --- genuine depth ---------------------------------------------------------------------------------------------------------


def test_fewer_than_fifty_levels_on_either_side_is_never_admitted() -> None:
    thin_bids = snapshot(bids=tuple(lvl(Fraction("99.95") - TICK * i) for i in range(OBSERVED_PIT_BOOK_DEPTH - 1)))
    result = with_book(thin_bids, step(0, first=999, final=1_001, previous=998))
    assert_rejected(result, "book_no_eligible_observation")
    (segment,) = result.evidence.book_segments
    assert (segment.applied_delta_count, segment.depth_ineligible_count, segment.emitted_record_count) == (1, 1, 0)
    thin_asks = snapshot(asks=tuple(lvl(Fraction("100.05") + TICK * i) for i in range(OBSERVED_PIT_BOOK_DEPTH - 1)))
    assert_rejected(with_book(thin_asks, step(0, first=999, final=1_001, previous=998)), "book_no_eligible_observation")


def test_a_fiftieth_level_beyond_the_snapshot_horizon_is_never_admitted() -> None:
    horizon = snapshot(levels=OBSERVED_PIT_BOOK_DEPTH)
    moved = step(
        1,
        first=1_002,
        final=1_003,
        previous=1_001,
        bids=(),
        asks=(lvl(Fraction("100.05"), 0), lvl(Fraction("100.05") + TICK * OBSERVED_PIT_BOOK_DEPTH)),
    )
    result = with_book(horizon, step(0, first=999, final=1_001, previous=998), moved)
    (segment,) = result.evidence.book_segments
    assert (segment.emitted_record_count, segment.horizon_ineligible_count) == (1, 1)
    assert [record.sequence_id for record in book_records(result)] == [1_001]


def test_crossed_books_and_invalid_levels_reject() -> None:
    crossed = snapshot(bids=(lvl(Fraction("100.10")),), asks=(lvl(Fraction("100.05")),))
    assert_rejected(with_book(crossed, *chain_steps(1)), "book_snapshot_invalid:0:crossed")
    zero = snapshot(bids=(lvl(Fraction("99.95"), 0), *snapshot().bids[1:]))
    assert_rejected(with_book(zero, *chain_steps(1)), "book_snapshot_invalid:0:level_nonpositive")
    duplicate = snapshot(bids=(snapshot().bids[0], *snapshot().bids))
    assert_rejected(with_book(duplicate, *chain_steps(1)), "book_snapshot_invalid:0:price_duplicate")
    crossing = step(0, first=999, final=1_001, previous=998, bids=(lvl(Fraction("100.10")),), asks=())
    assert_rejected(with_book(snapshot(), crossing), "book_crossed:1")
    repeated = step(0, first=999, final=1_001, previous=998, bids=(lvl(Fraction("99.95")), lvl(Fraction("99.95"), 5)))
    assert_rejected(with_book(snapshot(), repeated), "book_delta_price_duplicate:1")
    nonpositive = step(0, first=999, final=1_001, previous=998, bids=(lvl(Fraction(0)),), asks=())
    assert_rejected(with_book(snapshot(), nonpositive), "book_delta_level_invalid:1")
    negative = step(0, first=999, final=1_001, previous=998, bids=(lvl(Fraction("99.95"), -1),), asks=())
    assert_rejected(with_book(snapshot(), negative), "book_delta_level_invalid:1")


@pytest.mark.parametrize("text", ["100.05", "1e2", "100.050000000000000000 ", "-0.000000000000000000", 100])
def test_a_noncanonical_level_or_rate_raises(text: object) -> None:
    with pytest.raises(ObservedPitIngressError, match="noncanonical"):
        with_book(snapshot(asks=(ObservedBookLevel(text, d(1)), *snapshot().asks[1:])), *chain_steps(1))  # type: ignore[arg-type]
    broken = replace(settlements()[0], funding_rate=text)
    with pytest.raises(ObservedPitIngressError, match="funding_rate_noncanonical"):
        build_observed_pit_ingress(inputs(funding=funding_stream(settlements=(broken, *settlements()[1:]))))


# --- funding ---------------------------------------------------------------------------------------------------------------


def funding_result(items: tuple[ObservedFundingSettlement, ...], **overrides: object) -> ObservedPitIngressResult:
    return build_observed_pit_ingress(inputs(funding=funding_stream(settlements=items, **overrides)))


def test_a_final_rate_observed_before_its_settlement_is_refused_as_an_estimate() -> None:
    items = list(settlements())
    items[2] = replace(items[2], published_observed_at_ns=items[2].settlement_time_ns - 1)
    assert_rejected(funding_result(tuple(items)), "funding_final_observed_before_settlement:2")


@pytest.mark.parametrize("value", [None, True, "1", 0, 1.0])
def test_a_missing_or_malformed_finality_observation_raises(value: object) -> None:
    items = settlements()
    with pytest.raises(ObservedPitIngressError, match="funding_published_observed_at_ns_invalid"):
        funding_result((replace(items[0], published_observed_at_ns=value), *items[1:]))


def test_conflicting_revised_off_grid_and_uncovered_settlements_are_refused() -> None:
    items = settlements()
    assert_rejected(
        funding_result((*items[:3], replace(items[3], settlement_id=items[2].settlement_id), *items[4:])),
        "funding_settlement_conflict:3",
    )
    assert_rejected(
        funding_result((*items[:3], replace(items[2], funding_rate=d("0.0005")), *items[3:])),
        "funding_settlement_conflict:3",
    )
    assert_rejected(funding_result((items[1], items[0], *items[2:])), "funding_settlement_conflict:1")
    off_grid = replace(
        items[4],
        settlement_time_ns=items[4].settlement_time_ns + 1,
        published_observed_at_ns=items[4].published_observed_at_ns + 1,
    )
    assert_rejected(funding_result((*items[:4], off_grid, *items[5:])), "funding_settlement_off_grid:4")
    late = replace(
        items[-1], settlement_time_ns=BASE + 50 * INTERVAL, published_observed_at_ns=BASE + 50 * INTERVAL + 10
    )
    assert_rejected(funding_result((*items[:-1], late)), "funding_settlement_outside_coverage:9")


def test_an_incomplete_settlement_grid_is_refused_never_estimated() -> None:
    items = settlements()
    assert_rejected(funding_result((*items[:4], *items[5:])), "funding_coverage_incomplete:4")
    assert_rejected(funding_result(items[:-1]), "funding_coverage_incomplete:9")
    assert_rejected(funding_result(items[1:]), "funding_coverage_incomplete:0")


def test_the_interval_is_governed_never_a_fixed_eight_hours() -> None:
    wide = 2 * INTERVAL
    result = funding_result(
        settlements(interval=wide),
        governed_interval_ns=wide,
        coverage_start_ns=BASE + wide,
        coverage_end_ns=BASE + (len(econ.RATES) + 1) * wide,
    )
    assert result.evidence.status is EdgeEvidenceStatus.READY
    assert result.evidence.funding_interval_ns == wide
    assert result.dataset is not None
    funding = [record for record in result.dataset.records if record.series_id == "funding-final"]
    assert [record.event_time_ns for record in funding] == [BASE + k * wide for k in range(len(econ.RATES))]
    assert_rejected(funding_result(settlements(), governed_interval_ns=wide), "funding_settlement_off_grid:1")
    assert_rejected(funding_result(settlements(), coverage_start_ns=INTERVAL), "funding_window_open_invalid")


# --- authority, provenance and the implemented contract ---------------------------------------------------------------------


def manifest_over(registry: DataRequirementRegistry):  # noqa: ANN201 - an EF-3 manifest of the same series over `registry`
    packet = build_source_packet(
        packet_id="pkt-1",
        source_type="academic_paper",
        source_reference="doi:10.0/carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Funding pays passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    kill_policy = build_edge_kill_criteria_policy(
        policy_id="kp-1",
        correlation_id="corr-1",
        kill_criteria=pit.CRITERIA,
        thresholds_approved=True,
        approval_reference="gov-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id="intake-1",
        correlation_id="corr-1",
        candidate_strategy_id="passive-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Funding pays carry.",
        data_requirement_keys=econ.KEYS,
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=pit.CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    series = tuple(
        EdgeInputSeries(
            econ.SERIES_IDS[key],
            key,
            f"archive:{econ.SERIES_IDS[key]}",
            "own_research",
            "note-1",
            "finalized_only",
            "immutable_after_finalization",
            (INS,),
        )
        for key in econ.KEYS
    )
    return build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=series,
    )


def registry_with_book(**changes: object) -> DataRequirementRegistry:
    registry = default_perp_data_requirement_registry()
    requirements = dict(registry.requirements)
    requirements[DataRequirementKey.ORDER_BOOK] = replace(requirements[DataRequirementKey.ORDER_BOOK], **changes)
    return DataRequirementRegistry(schema_version=registry.schema_version, requirements=requirements)


def over(registry: DataRequirementRegistry) -> ObservedPitIngressResult:
    manifest = manifest_over(registry)
    return build_observed_pit_ingress(
        inputs(
            source_manifest=manifest,
            expected_source_manifest_digest=manifest.source_packet_evidence_digest,
            expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        )
    )


def test_the_implemented_semantics_are_exactly_the_accepted_registry() -> None:
    registry = default_perp_data_requirement_registry()
    implemented = observed_pit_implemented_series_semantics()
    assert set(implemented) == {"order_book", "mark_price", "funding_rate"}
    for key, expected in implemented.items():
        requirement = registry.requirements[DataRequirementKey(key)]
        actual = {name: getattr(requirement, name) for name in expected}
        assert actual == expected
        assert all(type(actual[name]) is type(value) for name, value in expected.items())
    implemented["order_book"]["order_book_level"] = "l1"
    assert observed_pit_implemented_series_semantics()["order_book"]["order_book_level"] == "l2"
    assert over(default_perp_data_requirement_registry()).evidence.status is EdgeEvidenceStatus.READY


def test_an_l1_or_shallower_book_declaration_is_never_substituted_for_l2_fifty() -> None:
    assert_rejected(
        over(registry_with_book(order_book_level="l1", order_book_depth=1)),
        "manifest_series_semantics_mismatch:book:order_book_level",
        "manifest_series_semantics_mismatch:book:order_book_depth",
    )
    assert_rejected(
        over(registry_with_book(order_book_depth=25)), "manifest_series_semantics_mismatch:book:order_book_depth"
    )
    assert_rejected(
        over(registry_with_book(sequence_policy="best_effort", finality_policy="gap_tolerant")),
        "manifest_series_semantics_mismatch:book:sequence_policy",
        "manifest_series_semantics_mismatch:book:finality_policy",
    )


def test_cross_instrument_and_cross_series_leakage_is_refused() -> None:
    assert_rejected(
        build_observed_pit_ingress(inputs(instrument="ETH-USDT-PERP")),
        "manifest_series_instrument_uncovered:book",
        "manifest_series_instrument_uncovered:mark",
        "manifest_series_instrument_uncovered:funding-final",
    )
    assert_rejected(
        build_observed_pit_ingress(inputs(book=book_stream(series_id="mark-shadow"))),
        "manifest_series_missing:mark-shadow",
    )
    swapped = build_observed_pit_ingress(
        inputs(
            book=book_stream(series_id="funding-final", source_reference="archive:funding-final"),
            funding=funding_stream(series_id="book", source_reference="archive:book"),
        )
    )
    assert_rejected(
        swapped,
        "manifest_series_semantics_mismatch:funding-final:data_requirement_key",
        "manifest_series_semantics_mismatch:book:data_requirement_key",
    )
    with pytest.raises(ObservedPitIngressError, match="series_ids_not_distinct"):
        build_observed_pit_ingress(inputs(mark=mark_stream(series_id="book")))


def test_source_identity_rights_and_object_provenance_are_bound() -> None:
    assert_rejected(
        build_observed_pit_ingress(inputs(book=book_stream(source_reference="archive:other"))),
        "manifest_series_source_reference_mismatch:book",
    )
    assert_rejected(
        build_observed_pit_ingress(inputs(declaration=declaration(rights_reference="note-2"))),
        "manifest_series_rights_mismatch:book",
        "manifest_series_rights_mismatch:mark",
        "manifest_series_rights_mismatch:funding-final",
    )
    assert_rejected(
        build_observed_pit_ingress(
            inputs(declaration=declaration(rights_status=SourcePacketRightsStatus.PERMISSIVE_LICENSE))
        ),
        "manifest_series_rights_mismatch:book",
    )
    foreign = replace(chain_steps(1)[0], object_id="synthetic-unknown-capture")
    assert_rejected(with_book(snapshot(), foreign), "source_object_undeclared:book:1")
    extra = (*declaration().objects, ObservedSourceObject("synthetic-unused-capture", "5" * 64, 1))
    assert_rejected(
        build_observed_pit_ingress(inputs(declaration=declaration(objects=extra))),
        "source_object_unused:synthetic-unused-capture",
    )


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        ({"rights_status": "own_research"}, "declaration_rights_status_invalid"),
        ({"rights_reference": ""}, "rights_reference_invalid"),
        ({"source_id": "Synthetic"}, "source_id_invalid"),
        ({"source_contract_reference": "a live_order feed"}, "forbidden_scope_token:source_contract_reference"),
        ({"objects": ()}, "declaration_objects_invalid"),
        ({"objects": [ObservedSourceObject(BOOK, "1" * 64, 1)]}, "declaration_objects_invalid"),
        ({"objects": (ObservedSourceObject(BOOK, "A" * 64, 1),)}, "source_object_sha256_invalid"),
        ({"objects": (ObservedSourceObject(BOOK, "1" * 64, 0),)}, "source_object_byte_length_invalid"),
        (
            {"objects": (ObservedSourceObject(BOOK, "1" * 64, 1), ObservedSourceObject(BOOK, "2" * 64, 1))},
            "source_object_id_duplicate",
        ),
    ],
)
def test_a_malformed_declaration_raises(changes: dict[str, object], match: str) -> None:
    with pytest.raises(ObservedPitIngressError, match=match):
        build_observed_pit_ingress(inputs(declaration=declaration(**changes)))


def test_stale_or_foreign_upstream_authority_rejects() -> None:
    assert_rejected(
        build_observed_pit_ingress(inputs(expected_source_manifest_digest="0" * 64)), "source_manifest_digest_mismatch"
    )
    assert_rejected(
        build_observed_pit_ingress(inputs(expected_data_requirement_registry_digest="0" * 64)),
        "data_requirement_registry_mismatch",
    )
    assert_rejected(build_observed_pit_ingress(inputs(correlation_id="corr-2")), "source_manifest_correlation_mismatch")
    with pytest.raises(ObservedPitIngressError, match="expected_source_manifest_digest_invalid"):
        build_observed_pit_ingress(inputs(expected_source_manifest_digest="0" * 63))
    with pytest.raises(ObservedPitIngressError, match="source_manifest_malformed"):
        build_observed_pit_ingress(inputs(source_manifest=object()))
    with pytest.raises(ObservedPitIngressError, match="book_continuity_profile_unknown"):
        build_observed_pit_ingress(inputs(book=book_stream(continuity_profile_id="sequence_gap_tolerant.v1")))


# --- verification, non-claims and purity -------------------------------------------------------------------------------------


def resealed(evidence: ObservedPitIngressEvidence, **changes: object) -> ObservedPitIngressEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, ingress_digest=observed_pit_ingress_digest(changed))


def test_verification_detects_tampering_revision_and_typed_substitution() -> None:
    evidence = default_result().evidence
    assert verify_observed_pit_ingress(evidence, inputs()).intact is True
    revised_objects = tuple(
        replace(item, content_sha256="9" * 64) if item.object_id == BOOK else item for item in declaration().objects
    )
    revision = verify_observed_pit_ingress(evidence, inputs(declaration=declaration(objects=revised_objects)))
    assert revision.intact is False
    assert _code("field_mismatch:declaration_digest") in revision.reason_codes
    assert _code("field_mismatch:dataset_digest") in revision.reason_codes
    tampered = verify_observed_pit_ingress(resealed(evidence, book_record_count=100), inputs())
    assert tampered.intact is False
    assert {_code("field_mismatch:book_record_count"), _code("typed_identity_mismatch")} <= set(tampered.reason_codes)
    unsealed = verify_observed_pit_ingress(replace(evidence, book_gap_count=1), inputs())
    assert _code("self_digest_mismatch") in unsealed.reason_codes
    for name, value in (
        ("funding_coverage_end_ns", evidence.funding_coverage_end_ns + INTERVAL),
        ("rights_reference", "note-2"),
        ("observation_digest", "0" * 64),
        ("source_objects", evidence.source_objects[1:]),
    ):
        forged = verify_observed_pit_ingress(resealed(evidence, **{name: value}), inputs())
        assert _code(f"field_mismatch:{name}") in forged.reason_codes, name
    for name, value in (("status", "READY"), ("gate_verdict", "NEEDS_EXTERNAL_FACTS"), ("advances", 0)):
        substituted = verify_observed_pit_ingress(resealed(evidence, **{name: value}), inputs())
        assert substituted.intact is False, name
        assert _code("typed_identity_mismatch") in substituted.reason_codes
    assert verify_observed_pit_ingress(object(), inputs()).reason_codes == (_code("evidence_type_invalid"),)
    assert verify_observed_pit_ingress(evidence, object()).reason_codes == (_code("evidence_reassembly_failed"),)


def test_structural_non_claims_hold_and_no_parameter_can_assert_them() -> None:
    evidence = default_result().evidence
    parameters = set(inspect.signature(build_observed_pit_ingress).parameters) | {
        item.name for item in fields(ObservedPitIngressInputs)
    }
    for name, value in OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is value, name
        assert name not in parameters
    flipped = resealed(evidence, **{name: not value for name, value in OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS})
    verification = verify_observed_pit_ingress(flipped, inputs())
    for name, _ in OBSERVED_PIT_INGRESS_NON_CLAIM_FLAGS:
        assert _code(f"field_mismatch:{name}") in verification.reason_codes, name
    payload = json.loads(json.dumps(observed_pit_ingress_to_dict(evidence)))
    assert payload["real_paper_data"] is False and payload["stage4_evidence"] is False


def test_the_continuity_profile_is_documented_not_qualified_and_digest_bound() -> None:
    profile = observed_pit_continuity_profile()
    assert profile["profile_id"] == OBSERVED_PIT_CONTINUITY_PROFILE_ID
    assert profile["qualification_status"] == "documented_not_qualified"
    assert default_result().evidence.continuity_profile_digest == observed_pit_continuity_profile_digest()
    profile["qualification_status"] = "qualified"
    assert observed_pit_continuity_profile()["qualification_status"] == "documented_not_qualified"
    assert default_result().evidence.continuity_profile_qualified is False


def test_reason_codes_are_sorted_unique_and_prefixed() -> None:
    result = build_observed_pit_ingress(inputs(instrument="ETH-USDT-PERP"))
    codes = result.evidence.integrity_reason_codes
    assert list(codes) == sorted(set(codes))
    assert all(code.startswith(f"{_PREFIX}:") for code in codes)


def test_module_is_pure_and_has_one_assembly_path() -> None:
    pit.assert_module_is_pure(
        ingress_module,
        {
            "crypto_core.data.requirements",
            "crypto_core.strategy.source_packet",
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_source_packet_evidence",
            "crypto_core.validation.historical_execution_economics_policy",
            "crypto_core.validation.historical_pit_dataset",
        },
    )
    pit.assert_single_assembly_path(
        ingress_module,
        "ObservedPitIngressEvidence",
        "_assemble",
        "build_observed_pit_ingress",
        "verify_observed_pit_ingress",
    )


# --- the existing decision and economics engine consumes the dataset unchanged -----------------------------------------------


def ingress_world(result: ObservedPitIngressResult):  # noqa: ANN201 - econ.World over the ingress dataset
    _, admission, registry = upstream()
    assert result.dataset is not None
    binding = econ.bind.executable_binding(admission)
    run = econ.runt.decision_run(
        result.dataset,
        binding,
        instrument=INS,
        evaluation_start_ns=econ.START,
        evaluation_end_ns=econ.END,
        parameter_assignment=econ.prof.params(),
    )
    return econ.World(run, result.dataset, registry)


def test_the_accepted_decision_run_and_economics_engine_consume_the_ingress_dataset() -> None:
    world = ingress_world(default_result())
    assert world.run.status is EdgeEvidenceStatus.READY
    result = econ.economics(world)
    assert verify_historical_execution_economics(result).intact is True
    assert (result.status, result.gate_verdict, result.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert result.order_book_series_id == "book"
    assert econ._executed(result)  # noqa: SLF001 - the accepted test's own fill selector


def test_an_economics_policy_on_another_funding_interval_fails_closed_on_the_ingress_dataset() -> None:
    world = ingress_world(default_result())
    policy = econ.polt.cited_policy(funding_interval_ns=2 * INTERVAL)
    result = econ.economics(world, policy=policy)
    assert result.advances is False
    assert any("funding_interval" in code for code in result.verdict_reason_codes + result.integrity_reason_codes)
