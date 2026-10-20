"""Contract tests for FREE_FIRST_AUTHENTICATED_PIT_INGRESS_V2 (``authenticated_pit_ingress``).

Every capture here is SYNTHETIC_TEST_ONLY. It proves deterministic construction, negative paths and consumer
integration. It is never a real market observation, real paper evidence or source qualification.

Also the shared capture fixtures for the independent oracle tests.
"""

from __future__ import annotations

import functools
import json
from dataclasses import fields, replace
from fractions import Fraction

import pytest

import crypto_core.validation.authenticated_pit_ingress as ingress_module
from crypto_core.data.requirements import (
    DataRequirementKey,
    DataRequirementRegistry,
    data_requirement_registry_digest,
    default_perp_data_requirement_registry,
)
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.validation.authenticated_pit_ingress import (
    AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS,
    AuthenticatedPitIngressError,
    AuthenticatedPitIngressEvidence,
    AuthenticatedPitIngressInputs,
    AuthenticatedPitIngressResult,
    CapturedBookDelta,
    CapturedBookSnapshot,
    CaptureDeclaration,
    CapturedFundingSettlement,
    CapturedLevel,
    CapturedMarkPrice,
    CaptureStreamDeclaration,
    NativeBookContinuityProfile,
    authenticated_pit_ingress_evidence_digest,
    authenticated_pit_ingress_evidence_from_payload,
    authenticated_pit_ingress_evidence_to_dict,
    build_authenticated_pit_ingress,
    verify_authenticated_pit_ingress,
)
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus, EdgeGateVerdict
from crypto_core.validation.edge_idea_intake_evidence import (
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    build_edge_source_packet_evidence,
    edge_source_packet_evidence_digest,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
    select_visible_pit_records,
    verify_historical_pit_dataset,
)

try:
    import test_historical_execution_economics as econ
    import test_historical_pit_dataset as pit
except ImportError:  # pragma: no cover - package-style collection
    from tests.crypto_core.validation import test_historical_execution_economics as econ
    from tests.crypto_core.validation import test_historical_pit_dataset as pit

_PREFIX = "authenticated_pit_ingress"
INS = econ.INS
ETH = "ETH-USDT-PERP"
BASE = econ.BASE
INTERVAL = econ.INTERVAL
TICK = Fraction(1, 100)
DEPTH = 50
PROFILE = NativeBookContinuityProfile.UPDATE_SPAN_CHAIN_ABSOLUTE_LEVELS_V1.value
d = econ.d
State = tuple[dict[Fraction, Fraction], dict[Fraction, Fraction]]


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


# --- SYNTHETIC truth books ----------------------------------------------------------------------------------------


def _resting_quantity(price: Fraction) -> Fraction:
    return Fraction(50 + int(price * 100) % 7)


@functools.cache
def moving_state(step: int, depth: int = 300) -> State:
    """SYNTHETIC truth after the delta at chain position ``step`` (-1 = before the first delta).

    The ladder moves up one tick per step, so every delta inserts a best bid, removes the deepest bid, removes the
    best ask, inserts a deepest ask and re-quotes the three best levels of each side.
    """

    mid = Fraction(100) + Fraction(step + 1, 100)
    bids: dict[Fraction, Fraction] = {}
    asks: dict[Fraction, Fraction] = {}
    for index in range(depth):
        bump = Fraction(1 + (step + index) % 3) if index < 3 else Fraction(0)
        bid = mid - Fraction(5, 100) - TICK * index
        ask = mid + Fraction(5, 100) + TICK * index
        bids[bid] = _resting_quantity(bid) + bump
        asks[ask] = _resting_quantity(ask) + bump
    return bids, asks


def fixed_state(depth: int = 300, quantity: object = 100) -> State:
    """SYNTHETIC fixed-price ladder: bids 99.95 - 0.01 i, asks 100.05 + 0.01 i, uniform quantity."""

    bids = {Fraction("99.95") - TICK * index: Fraction(quantity) for index in range(depth)}  # type: ignore[arg-type]
    asks = {Fraction("100.05") + TICK * index: Fraction(quantity) for index in range(depth)}  # type: ignore[arg-type]
    return bids, asks


FIXED = fixed_state()


def changed(state: State, *, bids: dict | None = None, asks: dict | None = None) -> State:
    """A copy of ``state`` with absolute level updates applied (quantity 0 removes a level)."""

    sides = [dict(state[0]), dict(state[1])]
    for side, update in ((0, bids or {}), (1, asks or {})):
        for price, quantity in update.items():
            if quantity == 0:
                sides[side].pop(Fraction(price), None)
            else:
                sides[side][Fraction(price)] = Fraction(quantity)
    return sides[0], sides[1]


def expected_book_values(state: State, depth: int = DEPTH) -> dict[str, str]:
    """Oracle record values of a truth state: the best ``depth`` levels per side plus the consumer top-of-book."""

    bids = sorted(state[0].items(), reverse=True)[:depth]
    asks = sorted(state[1].items())[:depth]
    values = {
        "best_bid_price": d(bids[0][0]),
        "best_bid_quantity": d(bids[0][1]),
        "best_ask_price": d(asks[0][0]),
        "best_ask_quantity": d(asks[0][1]),
    }
    for name, levels in (("bid", bids), ("ask", asks)):
        for index, (price, quantity) in enumerate(levels, start=1):
            values[f"{name}_{index:02d}_price"] = d(price)
            values[f"{name}_{index:02d}_quantity"] = d(quantity)
    return values


# --- SYNTHETIC captures ---------------------------------------------------------------------------------------------


def side_levels(side: dict, *, descending: bool, depth: int | None = None) -> tuple[CapturedLevel, ...]:
    ordered = sorted(side.items(), reverse=descending)
    return tuple(CapturedLevel(d(price), d(quantity)) for price, quantity in ordered[:depth])


def captured_levels(pairs: object) -> tuple[CapturedLevel, ...]:
    return tuple(CapturedLevel(d(price), d(quantity)) for price, quantity in pairs)  # type: ignore[attr-defined]


def snapshot(
    native_id: int,
    receipt: int,
    state: State,
    *,
    depth: int | None = None,
    bid_depth: int | None = None,
    ask_depth: int | None = None,
    stream: str = "book-btc",
) -> CapturedBookSnapshot:
    return CapturedBookSnapshot(
        stream,
        native_id,
        receipt,
        side_levels(state[0], descending=True, depth=depth if bid_depth is None else bid_depth),
        side_levels(state[1], descending=False, depth=depth if ask_depth is None else ask_depth),
    )


def delta(
    first: int,
    final: int,
    previous: int,
    event: int,
    *,
    receipt: int | None = None,
    bids: object = (),
    asks: object = (),
    stream: str = "book-btc",
) -> CapturedBookDelta:
    def captured(levels: object) -> tuple[CapturedLevel, ...]:
        return tuple(CapturedLevel(d(price), d(quantity)) for price, quantity in dict(levels).items())  # type: ignore[call-overload]

    return CapturedBookDelta(
        stream, first, final, previous, event, event + 1 if receipt is None else receipt, captured(bids), captured(asks)
    )


def transition(before: State, after: State) -> tuple[dict, dict]:
    """The absolute level updates turning ``before`` into ``after``."""

    return tuple(  # type: ignore[return-value]
        {
            price: after[side].get(price, Fraction(0))
            for price in sorted(set(before[side]) | set(after[side]))
            if before[side].get(price) != after[side].get(price)
        }
        for side in (0, 1)
    )


def final_id(step: int) -> int:
    """Native final id of the moving-ladder delta at chain position ``step`` (two updates per event)."""

    return 1001 + 2 * step


def event_ns(step: int) -> int:
    return BASE + 1_000 * step + 500


def moving_delta(step: int, *, receipt: int | None = None, stream: str = "book-btc") -> CapturedBookDelta:
    bids, asks = transition(moving_state(step - 1), moving_state(step))
    return delta(
        final_id(step) - 1,
        final_id(step),
        final_id(step) - 2,
        event_ns(step),
        receipt=receipt,
        bids=bids,
        asks=asks,
        stream=stream,
    )


def moving_book(steps: range = range(101)) -> list:
    """Snapshot at 1000 (inside the first delta's span, U=1000 <= 1000 < u=1001), then the delta chain."""

    return [snapshot(1_000, BASE + 400, moving_state(-1)), *(moving_delta(step) for step in steps)]


def marks(count: int = 101, *, stream: str = "mark-btc") -> list[CapturedMarkPrice]:
    return [CapturedMarkPrice(stream, BASE + 1_000 * j, BASE + 1_000 * j + 1, d(econ.price(j))) for j in range(count)]


def settlement_ns(k: int) -> int:
    return BASE + (k + 1) * INTERVAL


def fundings(rates: tuple[str, ...] = econ.RATES, *, stream: str = "funding-btc") -> list[CapturedFundingSettlement]:
    return [
        CapturedFundingSettlement(stream, settlement_ns(k), settlement_ns(k) + 10, rate) for k, rate in enumerate(rates)
    ]


def merged(*groups: object) -> tuple:
    """One capture in receipt order (stable for equal receipts)."""

    observations = [item for group in groups for item in group]  # type: ignore[attr-defined]
    return tuple(sorted(observations, key=lambda item: item.receipt_ns))


def world_capture(book: object = None) -> tuple:
    return merged(moving_book() if book is None else book, marks(), fundings())


def fixed_tail(
    previous: int, count: int, *, step0: int = 1, stream: str = "book-btc", quantity: int = 100
) -> list[CapturedBookDelta]:
    """Fixed-price deltas re-quoting only the best ask quantity (``quantity`` / ``quantity + 1``) from ``previous``."""

    deltas = []
    for index in range(count):
        step = step0 + index
        deltas.append(
            delta(
                previous + 1,
                previous + 2,
                previous,
                BASE + 1_000 * step + 500,
                asks={Fraction("100.05"): quantity + step % 2},
                stream=stream,
            )
        )
        previous += 2
    return deltas


# --- declaration, authority and assembly ---------------------------------------------------------------------------


def stream(
    stream_id: str,
    key: str,
    *,
    instrument: str = INS,
    series: str | None = None,
    reference: str | None = None,
    epoch: str = "epoch-1",
    profile: object = "default",
    interval: object = "default",
) -> CaptureStreamDeclaration:
    series_id = econ.SERIES_IDS[key] if series is None else series
    return CaptureStreamDeclaration(
        stream_id=stream_id,
        data_requirement_key=key,
        instrument=instrument,
        series_id=series_id,
        source_reference=f"archive:{series_id}" if reference is None else reference,
        native_epoch_id=epoch,
        continuity_profile=(PROFILE if key == "order_book" else None) if profile == "default" else profile,  # type: ignore[arg-type]
        funding_interval_ns=(INTERVAL if key == "funding_rate" else None) if interval == "default" else interval,  # type: ignore[arg-type]
    )


DEFAULT_STREAMS = (
    stream("book-btc", "order_book"),
    stream("mark-btc", "mark_price"),
    stream("funding-btc", "funding_rate"),
)


def declaration(**changes: object) -> CaptureDeclaration:
    base = CaptureDeclaration(
        capture_id="capture-1",
        source_id="synthetic-fixture",
        source_reference="capture:synthetic-fixture",
        source_object_id="synthetic-capture-1.jsonl",
        source_object_digest="a" * 64,
        rights_status="own_research",
        rights_reference="note-1",
        streams=DEFAULT_STREAMS,
    )
    return replace(base, **changes)  # type: ignore[arg-type]


@functools.cache
def world_chain():
    """The accepted econ EF-3 / EF-4 chain: ``(manifest, admission, registry)``."""

    return econ.chain()


@functools.cache
def _intake():
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
    return build_edge_idea_intake_evidence(
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


def variant_manifest(
    *,
    registry: DataRequirementRegistry | None = None,
    instruments: tuple[str, ...] = (INS,),
    rights: tuple[str, str] = ("own_research", "note-1"),
):
    """An EF-3 manifest over the econ intake with chosen registry, coverage and rights: ``(manifest, registry)``."""

    registry = default_perp_data_requirement_registry() if registry is None else registry
    intake = _intake()
    series = tuple(
        EdgeInputSeries(
            econ.SERIES_IDS[key],
            key,
            f"archive:{econ.SERIES_IDS[key]}",
            rights[0],
            rights[1],
            "finalized_only",
            "immutable_after_finalization",
            instruments,
        )
        for key in econ.KEYS
    )
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=series,
    )
    return manifest, registry


def inputs(
    observations: object,
    *,
    manifest: object = None,
    registry: DataRequirementRegistry | None = None,
    **changes: object,
) -> AuthenticatedPitIngressInputs:
    if manifest is None:
        manifest, _, registry = world_chain()
    elif registry is None:
        registry = default_perp_data_requirement_registry()
    arguments: dict[str, object] = {
        "ingress_id": "ingress-1",
        "correlation_id": "corr-1",
        "dataset_id": "dataset-1",
        "source_manifest": manifest,
        "expected_source_manifest_digest": manifest.source_packet_evidence_digest,  # type: ignore[attr-defined]
        "expected_data_requirement_registry_digest": data_requirement_registry_digest(registry),
        "declaration": declaration(),
        "observations": tuple(observations),  # type: ignore[arg-type]
    }
    arguments.update(changes)
    return AuthenticatedPitIngressInputs(**arguments)  # type: ignore[arg-type]


def ingest(observations: object, **changes: object) -> AuthenticatedPitIngressResult:
    return build_authenticated_pit_ingress(inputs(observations, **changes))


@functools.cache
def world_result() -> AuthenticatedPitIngressResult:
    return ingest(world_capture())


def economics_of(dataset: HistoricalPitDataset):
    """The accepted decision run and economics consumers over an ingress dataset."""

    _, admission, registry = world_chain()
    run = econ.runt.decision_run(
        dataset,
        econ.bind.executable_binding(admission),
        instrument=INS,
        evaluation_start_ns=econ.START,
        evaluation_end_ns=econ.END,
        parameter_assignment=econ.prof.params(),
    )
    return econ.economics(econ.World(run, dataset, registry))


@functools.cache
def world_economics():
    return economics_of(world_result().dataset)


# --- assertions ------------------------------------------------------------------------------------------------------


def assert_ready(result: AuthenticatedPitIngressResult) -> HistoricalPitDataset:
    evidence = result.evidence
    assert evidence.status is EdgeEvidenceStatus.READY, evidence.integrity_reason_codes
    assert evidence.integrity_reason_codes == ()
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert evidence.advances is False
    assert result.dataset is not None
    assert result.dataset.status is EdgeEvidenceStatus.READY
    assert evidence.dataset_digest == result.dataset.dataset_digest
    assert evidence.record_count == len(result.dataset.records)
    return result.dataset


def assert_rejected(result: AuthenticatedPitIngressResult, *codes: str) -> None:
    evidence = result.evidence
    assert result.dataset is None
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
    assert evidence.advances is False
    assert evidence.verdict_reason_codes == ()
    assert evidence.dataset_digest == ""
    assert evidence.record_count == 0
    for expected in codes:
        assert code(expected) in evidence.integrity_reason_codes, evidence.integrity_reason_codes


def book_records(result: AuthenticatedPitIngressResult, instrument: str = INS) -> list[HistoricalPitRecord]:
    assert result.dataset is not None
    return [
        record for record in result.dataset.records if record.series_id == "book" and record.instrument == instrument
    ]


def values_of(record: HistoricalPitRecord) -> dict[str, str]:
    return {value.name: value.value for value in record.values}


def summary(result: AuthenticatedPitIngressResult, stream_id: str = "book-btc"):
    return next(item for item in result.evidence.streams if item.stream_id == stream_id)


# --- A/F: source-to-consumer integration ---------------------------------------------------------------------------


def test_clean_capture_is_ready_never_advances_and_carries_the_open_source_gate() -> None:
    result = world_result()
    dataset = assert_ready(result)
    evidence = result.evidence
    assert evidence.verdict_reason_codes == tuple(
        sorted(
            code(reason)
            for reason in (
                "funding_finality_source_unproven",
                "historical_coverage_unknown",
                "native_continuity_profile_unqualified",
                "source_rights_unverified",
            )
        )
    )
    assert dataset.gate_verdict is EdgeGateVerdict.PASS
    assert verify_historical_pit_dataset(dataset).intact is True
    assert evidence.continuity_profile_qualification == "documented_not_qualified"
    assert evidence.book_record_depth == DEPTH
    assert [(item.stream_id, item.record_count) for item in evidence.streams] == [
        ("book-btc", 101),
        ("funding-btc", 10),
        ("mark-btc", 101),
    ]
    book = summary(result)
    assert (book.native_chain_count, book.attached_snapshot_count, book.unattached_snapshot_count) == (1, 1, 0)
    assert (book.first_record_sequence_id, book.last_record_sequence_id) == (final_id(0), final_id(100))


def test_book_records_carry_the_exact_l2_depth_50_truth_with_native_identity_and_pit_times() -> None:
    records = book_records(world_result())
    assert [record.sequence_id for record in records] == [final_id(step) for step in range(101)]
    for step, record in enumerate(records):
        assert values_of(record) == expected_book_values(moving_state(step))
        assert len(record.values) == 4 + 4 * DEPTH
        assert record.data_requirement_key == "order_book"
        assert record.event_time_ns == event_ns(step)
        # Known at the receipt of the delta that completed the state; book finality is that authentication instant.
        assert record.available_at_ns == record.finalized_at_ns == event_ns(step) + 1


def test_mark_and_final_funding_records_keep_event_receipt_and_finality_separate() -> None:
    dataset = world_result().dataset
    mark_records = [record for record in dataset.records if record.series_id == "mark"]
    assert [(r.sequence_id, r.event_time_ns, r.available_at_ns, r.finalized_at_ns) for r in mark_records] == [
        (BASE + 1_000 * j, BASE + 1_000 * j, BASE + 1_000 * j + 1, BASE + 1_000 * j) for j in range(101)
    ]
    funding = [record for record in dataset.records if record.series_id == "funding-final"]
    assert [(r.sequence_id, r.event_time_ns, r.available_at_ns, r.finalized_at_ns) for r in funding] == [
        (settlement_ns(k) // INTERVAL, settlement_ns(k) - INTERVAL, settlement_ns(k) + 10, settlement_ns(k))
        for k in range(10)
    ]
    assert [values_of(record) for record in funding] == [{"funding_rate": rate} for rate in econ.RATES]


def test_ingress_dataset_drives_the_accepted_decision_and_economics_consumers() -> None:
    result = world_economics()
    assert result.status is EdgeEvidenceStatus.READY and result.gate_verdict is EdgeGateVerdict.PASS
    executed = [fill for fill in result.fills if fill.outcome.value == "FILLED"]
    assert executed
    books = {record.record_digest: record for record in book_records(world_result())}
    assert all(fill.book_record_digest in books for fill in executed)


def oracle_dataset() -> HistoricalPitDataset:
    """The same capture mapped by hand from the SYNTHETIC truth (independent of the ingress update logic)."""

    manifest, _, registry = world_chain()
    records = [
        build_historical_pit_record(
            series_id="book",
            data_requirement_key="order_book",
            instrument=INS,
            sequence_id=final_id(step),
            event_time_ns=event_ns(step),
            available_at_ns=event_ns(step) + 1,
            finalized_at_ns=event_ns(step) + 1,
            revision_vintage_id=None,
            values=tuple(HistoricalPitValue(n, v) for n, v in expected_book_values(moving_state(step)).items()),
        )
        for step in range(101)
    ]
    records += [
        build_historical_pit_record(
            series_id="mark",
            data_requirement_key="mark_price",
            instrument=INS,
            sequence_id=BASE + 1_000 * j,
            event_time_ns=BASE + 1_000 * j,
            available_at_ns=BASE + 1_000 * j + 1,
            finalized_at_ns=BASE + 1_000 * j,
            revision_vintage_id=None,
            values=(HistoricalPitValue("mark_price", d(econ.price(j))),),
        )
        for j in range(101)
    ]
    records += [
        build_historical_pit_record(
            series_id="funding-final",
            data_requirement_key="funding_rate",
            instrument=INS,
            sequence_id=settlement_ns(k) // INTERVAL,
            event_time_ns=settlement_ns(k) - INTERVAL,
            available_at_ns=settlement_ns(k) + 10,
            finalized_at_ns=settlement_ns(k),
            revision_vintage_id=None,
            values=(HistoricalPitValue("funding_rate", rate),),
        )
        for k, rate in enumerate(econ.RATES)
    ]
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="dataset-1",
        correlation_id="corr-1",
        source_reference="capture:synthetic-fixture",
        rights_status="own_research",
        rights_reference="note-1",
        records=records,
    )


def test_exact_engine_regression_parity_with_the_independently_mapped_truth() -> None:
    oracle = oracle_dataset()
    assert world_result().dataset == oracle
    assert world_result().evidence.dataset_digest == oracle.dataset_digest
    assert economics_of(oracle).result_digest == world_economics().result_digest


def test_decisions_never_see_final_funding_before_its_publication_and_settlement() -> None:
    _, admission, _ = world_chain()
    run = econ.runt.decision_run(
        world_result().dataset,
        econ.bind.executable_binding(admission),
        instrument=INS,
        evaluation_start_ns=econ.START,
        evaluation_end_ns=econ.END,
        parameter_assignment=econ.prof.params(),
    )
    assert run.decision_count > 0
    funding = {r.record_digest: r for r in world_result().dataset.records if r.series_id == "funding-final"}
    for decision in run.decisions:
        for digest in decision.input_record_digests:
            used = funding[digest]
            assert used.finalized_at_ns <= decision.decision_time_ns
            assert used.available_at_ns <= decision.decision_time_ns
            assert used.event_time_ns + INTERVAL <= decision.decision_time_ns
    view = select_visible_pit_records(
        world_result().dataset, series_id="funding-final", instrument=INS, decision_time_ns=settlement_ns(0) + 9
    )
    assert view.records == ()


# --- C: B1 regression family (B1_NATIVE_REPLAY_STATE_CONFLICT) -----------------------------------------------------


@pytest.mark.parametrize(
    "mutation",
    [
        pytest.param({"asks": "quantity"}, id="conflicting-quantity"),
        pytest.param({"event_time_ns": 7}, id="conflicting-event-time"),
        pytest.param({"first_update_id": 1}, id="conflicting-first-update-id"),
        pytest.param({"previous_final_update_id": -1}, id="conflicting-predecessor"),
    ],
)
def test_c1_an_applied_native_id_redelivered_with_other_content_rejects_the_capture(mutation: dict) -> None:
    original = moving_delta(40)
    if "asks" in mutation:
        first = original.asks[0]
        redelivery = replace(original, asks=(replace(first, quantity=d(777)), *original.asks[1:]))
    else:
        name, offset = next(iter(mutation.items()))
        redelivery = replace(original, **{name: getattr(original, name) + offset})
    redelivery = replace(redelivery, receipt_ns=event_ns(50) + 2)
    result = ingest(world_capture([*moving_book(), redelivery]))
    assert_rejected(result, f"book_native_identity_conflict:book-btc:{final_id(40)}")
    identical = ingest(world_capture([*moving_book(), replace(original, receipt_ns=event_ns(50) + 2)]))
    assert identical.dataset == world_result().dataset
    assert summary(identical).replay_count == 1


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_c2_c3_a_narrower_same_id_snapshot_never_replaces_broader_authenticated_knowledge(side: str) -> None:
    truth = changed(FIXED, asks={Fraction("100.05"): 101})
    deep_price = Fraction("99.95") - TICK * 200 if side == "bid" else Fraction("100.05") + TICK * 200
    conflicting = changed(truth, **{f"{side}s": {deep_price: 5}})
    chain = [
        snapshot(1_001, BASE + 100, truth),
        delta(1_000, 1_001, 999, BASE + 500, asks={Fraction("100.05"): 101}),
        *fixed_tail(1_001, 2, step0=1),
    ]
    narrow = snapshot(1_001, BASE + 5_000, truth, depth=60)
    poisoned = ingest([*chain, narrow, snapshot(1_001, BASE + 6_000, conflicting)])
    assert_rejected(poisoned, "book_snapshot_conflict:book-btc:1001")
    clean = ingest([*chain, narrow, snapshot(1_001, BASE + 6_000, truth)])
    assert_ready(clean)
    assert [r.sequence_id for r in book_records(clean)] == [1_001, 1_003, 1_005]


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_c2_same_id_knowledge_is_a_union_even_where_no_chain_ever_covers_the_identity(side: str) -> None:
    # 1007 falls in the native gap between the chain ending at 1004 and the chain starting at 1010, so no chain step
    # ever re-checks it: only the retained union of the same-id snapshots can reject the later contradiction.
    deep_price = Fraction("99.95") - TICK * 200 if side == "bid" else Fraction("100.05") + TICK * 200
    before_gap = [snapshot(1_000, BASE + 100, FIXED), *fixed_tail(998, 3, step0=0)]
    after_gap = [snapshot(1_012, BASE + 9_400, FIXED), delta(1_011, 1_012, 1_010, BASE + 9_500)]
    same_id = [
        snapshot(1_007, BASE + 10_000, FIXED),
        snapshot(1_007, BASE + 10_100, FIXED, depth=60),
    ]
    conflicting = snapshot(1_007, BASE + 10_200, changed(FIXED, **{f"{side}s": {deep_price: 5}}))
    poisoned = ingest([*before_gap, *after_gap, *same_id, conflicting])
    assert_rejected(poisoned, "book_snapshot_conflict:book-btc:1007")
    clean = ingest([*before_gap, *after_gap, *same_id, snapshot(1_007, BASE + 10_200, FIXED)])
    assert_ready(clean)
    assert (summary(clean).native_chain_count, summary(clean).unattached_snapshot_count) == (2, 3)


@pytest.mark.parametrize("side", ["bid", "ask"])
def test_c4_deeper_levels_stay_known_through_narrower_captures_and_the_chain(side: str) -> None:
    best = (
        [Fraction("99.95") - TICK * i for i in range(30)]
        if side == "bid"
        else [Fraction("100.05") + TICK * i for i in range(30)]
    )
    removal = dict.fromkeys(best, 0)
    thinner = changed(FIXED, **{f"{side}s": removal})
    broad = snapshot(1_000, BASE + 100, FIXED)
    narrow_at_l = snapshot(1_000, BASE + 2_000, FIXED, depth=60)
    narrow_at_tip = snapshot(1_002, BASE + 2_100, FIXED, depth=60)
    chain = [
        delta(999, 1_000, 998, BASE + 500),
        delta(1_001, 1_002, 1_000, BASE + 1_500),
        narrow_at_l,
        narrow_at_tip,
        delta(1_003, 1_004, 1_002, BASE + 3_500, **{f"{side}s": removal}),
    ]
    retained = ingest([broad, *chain])
    records = book_records(retained)
    assert [record.sequence_id for record in records] == [1_000, 1_002, 1_004]
    # The 50th best level now lies 80 levels deep: exact only because the broad snapshot's knowledge was retained.
    assert values_of(records[-1]) == expected_book_values(thinner)
    narrow_only = ingest(chain)
    assert [record.sequence_id for record in book_records(narrow_only)] == [1_002]
    deep = Fraction("99.95") - TICK * 250 if side == "bid" else Fraction("100.05") + TICK * 250
    contradiction = snapshot(1_004, BASE + 9_000, changed(thinner, **{f"{side}s": {deep: 7}}))
    assert_rejected(ingest([broad, *chain, contradiction]), "book_knowledge_conflict:book-btc:1004")


def test_c5_equivalent_narrow_and_broad_resync_observations_preserve_book_and_economics() -> None:
    resync = [
        snapshot(final_id(40), event_ns(40) + 50, moving_state(40), depth=60),
        snapshot(final_id(40), event_ns(40) + 60, moving_state(40)),
        snapshot(final_id(40) - 1, event_ns(40) + 70, moving_state(39), depth=55),
        *(replace(moving_delta(step), receipt_ns=event_ns(40) + 80 + step) for step in range(36, 41)),
        snapshot(final_id(75), event_ns(90) + 5, moving_state(75), depth=120),
        snapshot(1_000, event_ns(95) + 5, moving_state(-1), depth=70),
    ]
    result = ingest(world_capture([*moving_book(), *resync]))
    assert result.dataset == world_result().dataset
    assert summary(result).replay_count == 5
    assert economics_of(result.dataset).result_digest == world_economics().result_digest


def test_c6_a_later_higher_id_snapshot_reflects_market_evolution_not_a_same_id_conflict() -> None:
    evolved = snapshot(final_id(60), event_ns(60) + 30, moving_state(60))
    assert ingest(world_capture([*moving_book(), evolved])).dataset == world_result().dataset
    gapped = [
        item
        for item in moving_book()
        if not (type(item) is CapturedBookDelta and 30 <= (item.final_update_id - 1_001) // 2 <= 34)
    ]
    resync = snapshot(final_id(40), event_ns(39) + 400, moving_state(40))
    result = ingest(world_capture([*gapped, resync]))
    assert_ready(result)
    assert [r.sequence_id for r in book_records(result)] == [final_id(s) for s in (*range(30), *range(40, 101))]
    assert values_of(book_records(result)[30]) == expected_book_values(moving_state(40))
    assert summary(result).native_chain_count == 2
    wrong = changed(moving_state(60), bids={sorted(moving_state(60)[0])[-10]: 999})
    assert_rejected(
        ingest(world_capture([*moving_book(), snapshot(final_id(60), event_ns(60) + 30, wrong)])),
        f"book_knowledge_conflict:book-btc:{final_id(60)}",
    )


def test_b1_conflicting_reconnect_replay_never_reaches_the_decision_or_economics_consumer() -> None:
    original = moving_delta(20)
    poisoned_bid = replace(original.bids[0], quantity=d(Fraction(original.bids[0].quantity) + 500))
    replay = replace(original, bids=(poisoned_bid, *original.bids[1:]), receipt_ns=event_ns(21) + 100)
    result = ingest(world_capture([*moving_book(), replay]))
    assert_rejected(result, f"book_native_identity_conflict:book-btc:{final_id(20)}")
    assert world_economics().gate_verdict is EdgeGateVerdict.PASS


# --- D: B2 regression family (B2_NATIVE_SNAPSHOT_DELTA_STATE_CONFLICT) ---------------------------------------------


def test_d1_a_first_delta_ending_at_the_snapshot_id_cannot_rewrite_the_known_book() -> None:
    conflicting = delta(999, 1_000, 998, BASE + 500, bids={Fraction("99.95"): 777})
    tail = fixed_tail(1_000, 20)
    poisoned = ingest([snapshot(1_000, BASE + 100, FIXED), conflicting, *tail])
    assert_rejected(poisoned, "book_snapshot_delta_conflict:book-btc:1000")
    clean = ingest(
        [snapshot(1_000, BASE + 100, FIXED), replace(conflicting, bids=(CapturedLevel(d("99.95"), d(100)),)), *tail]
    )
    assert_ready(clean)
    first = book_records(clean)[0]
    assert first.sequence_id == 1_000
    assert values_of(first) == expected_book_values(FIXED)


def test_d2_the_same_contradiction_is_rejected_through_pre_snapshot_buffered_alignment() -> None:
    conflicting = delta(999, 1_000, 998, BASE + 500, bids={Fraction("99.95"): 777})
    buffered = [conflicting, *fixed_tail(1_000, 5)]
    late = snapshot(1_000, BASE + 9_000, FIXED)
    assert_rejected(ingest([*buffered, late]), "book_snapshot_delta_conflict:book-btc:1000")
    clean = [replace(conflicting, bids=(CapturedLevel(d("99.95"), d(100)),)), *fixed_tail(1_000, 5)]
    result = ingest([*clean, late])
    # Only the tip is emitted, at the receipt that completed its knowledge; buffered states are never backfilled.
    assert [(r.sequence_id, r.available_at_ns) for r in book_records(result)] == [(1_010, BASE + 9_000)]


D3_PRICES = {
    ("bid", "quantity"): (Fraction("99.90"), 37),
    ("bid", "insertion"): (Fraction("99.905"), 9),
    ("bid", "removal"): (Fraction("99.50"), 0),
    ("ask", "quantity"): (Fraction("100.10"), 37),
    ("ask", "insertion"): (Fraction("100.095"), 9),
    ("ask", "removal"): (Fraction("100.50"), 0),
}


@pytest.mark.parametrize("variant", sorted(D3_PRICES))
@pytest.mark.parametrize(
    ("order", "event_offset"),
    [
        pytest.param("delta_first", -300, id="delta-first-event-well-before"),
        pytest.param("delta_first", -2, id="delta-first-event-just-before"),
        pytest.param("snapshot_first", -300, id="snapshot-first-event-before"),
        pytest.param("snapshot_first", 0, id="snapshot-first-event-at-receipt"),
        pytest.param("snapshot_first", 1, id="snapshot-first-event-after-receipt"),
    ],
)
def test_d3_every_same_id_disagreement_is_rejected_on_both_sides_in_any_order(
    variant: tuple[str, str], order: str, event_offset: int
) -> None:
    side, _ = variant
    price, quantity = D3_PRICES[variant]
    truth = FIXED[0 if side == "bid" else 1]
    snapshot_receipt = BASE + 1_000
    delta_receipt = snapshot_receipt - 1 if order == "delta_first" else snapshot_receipt + 1
    conflicting = delta(
        999, 1_000, 998, snapshot_receipt + event_offset, receipt=delta_receipt, **{f"{side}s": {price: quantity}}
    )
    snap = snapshot(1_000, snapshot_receipt, FIXED)

    def arrival(first_delta: CapturedBookDelta) -> list:
        pair = [first_delta, snap] if order == "delta_first" else [snap, first_delta]
        return [*pair, *fixed_tail(1_000, 3, step0=3)]

    assert_rejected(ingest(arrival(conflicting)), "book_snapshot_delta_conflict:book-btc:1000")
    twin = replace(conflicting, **{f"{side}s": captured_levels([(price, truth.get(price, 0))])})
    assert_ready(ingest(arrival(twin)))


def test_d3_a_same_id_level_outside_snapshot_coverage_is_unknown_not_a_contradiction() -> None:
    outside_bid = Fraction("99.95") - TICK * 400
    outside_ask = Fraction("100.05") + TICK * 400
    beyond = delta(999, 1_000, 998, BASE + 500, bids={outside_bid: 3}, asks={outside_ask: 4})
    result = ingest([snapshot(1_000, BASE + 100, FIXED), beyond, *fixed_tail(1_000, 2)])
    assert_ready(result)
    assert values_of(book_records(result)[0]) == expected_book_values(FIXED)


def test_d4_a_content_equivalent_same_id_overlap_mutates_nothing_and_emits_one_record() -> None:
    equivalent = delta(999, 1_000, 998, BASE + 500, bids={Fraction("99.95"): 100}, asks={Fraction("100.05"): 100})
    result = ingest(
        [
            snapshot(1_000, BASE + 100, FIXED),
            equivalent,
            replace(equivalent, receipt_ns=BASE + 700),
            *fixed_tail(1_000, 2),
        ]
    )
    records = book_records(result)
    assert [record.sequence_id for record in records] == [1_000, 1_002, 1_004]
    assert values_of(records[0]) == expected_book_values(FIXED)
    assert summary(result).replay_count == 1
    main = ingest(world_capture([snapshot(final_id(0), BASE + 400, moving_state(0)), *moving_book()[1:]]))
    assert main.dataset == world_result().dataset


def test_d5_a_delta_spanning_the_snapshot_id_advances_only_under_the_declared_profile() -> None:
    advancing = delta(
        999, 1_002, 998, BASE + 500, bids={Fraction("99.96"): 11, Fraction("99.95"): 120}, asks={Fraction("100.05"): 0}
    )
    result = ingest([snapshot(1_000, BASE + 100, FIXED), advancing, *fixed_tail(1_002, 1)])
    expected = changed(FIXED, bids={Fraction("99.96"): 11, Fraction("99.95"): 120}, asks={Fraction("100.05"): 0})
    assert values_of(book_records(result)[0]) == expected_book_values(expected)
    for profile in ("update_id_predecessor_chain_snapshot_aligned.v1", "unknown", None):
        streams = (stream("book-btc", "order_book", profile=profile), *DEFAULT_STREAMS[1:])
        with pytest.raises(AuthenticatedPitIngressError, match="stream_continuity_profile"):
            ingest([snapshot(1_000, BASE + 100, FIXED), advancing], declaration=declaration(streams=streams))


def test_d5_a_snapshot_before_the_first_update_of_the_spanning_delta_is_continued_exactly() -> None:
    advancing = delta(1_001, 1_002, 998, BASE + 500, bids={Fraction("99.95"): 120})
    result = ingest([snapshot(1_000, BASE + 100, FIXED), advancing])
    assert values_of(book_records(result)[0]) == expected_book_values(changed(FIXED, bids={Fraction("99.95"): 120}))


def test_b2_contradiction_never_reaches_the_decision_or_economics_consumer() -> None:
    first = moving_delta(0)
    aligned = [snapshot(final_id(0), BASE + 400, moving_state(0)), *moving_book()[1:]]
    assert ingest(world_capture(aligned)).dataset == world_result().dataset
    best = max(range(len(first.bids)), key=lambda index: Fraction(first.bids[index].price))
    poisoned_bids = tuple(
        replace(level, quantity=d(777)) if index == best else level for index, level in enumerate(first.bids)
    )
    poisoned_delta = replace(first, bids=poisoned_bids)
    poisoned = [aligned[0], poisoned_delta, *aligned[2:]]
    assert_rejected(ingest(world_capture(poisoned)), f"book_snapshot_delta_conflict:book-btc:{final_id(0)}")


# --- B: step knowledge projections across native identities ----------------------------------------------------------

P_NEW = Fraction("99.905")
T1003 = changed(FIXED, bids={P_NEW: 5})
T1005 = changed(T1003, bids={Fraction("99.90"): 0})
KNOWLEDGE_CHAIN = [
    delta(999, 1_000, 998, BASE + 500),
    delta(1_001, 1_001, 1_000, BASE + 1_500),
    delta(1_002, 1_003, 1_001, BASE + 2_500, bids={P_NEW: 5}),
    delta(1_004, 1_005, 1_003, BASE + 3_500, bids={Fraction("99.90"): 0}),
]


def anchored(*late: CapturedBookSnapshot) -> list:
    return [snapshot(1_000, BASE + 100, FIXED), *KNOWLEDGE_CHAIN, *late]


@pytest.mark.parametrize(
    ("late", "native_id"),
    [
        # 1004 lies strictly inside the last delta's span; that delta lists only 99.90.
        pytest.param(snapshot(1_004, BASE + 9_000, changed(T1003, bids={P_NEW: 6})), 1_004, id="mention-quantity"),
        pytest.param(snapshot(1_004, BASE + 9_000, changed(T1003, bids={P_NEW: 0})), 1_004, id="mention-omitted"),
        pytest.param(
            snapshot(1_001, BASE + 9_000, changed(FIXED, bids={Fraction("99.90"): 0})),
            1_001,
            id="base-omitted-before-first-mention",
        ),
        pytest.param(
            snapshot(1_005, BASE + 9_000, changed(T1005, bids={Fraction("98.50"): 0})), 1_005, id="base-omitted"
        ),
        pytest.param(
            snapshot(1_003, BASE + 9_000, changed(T1003, bids={Fraction("98.505"): 3})), 1_003, id="known-absent-listed"
        ),
        pytest.param(
            snapshot(1_001, BASE + 9_000, changed(FIXED, bids={P_NEW: 5})), 1_001, id="listed-before-its-insertion"
        ),
    ],
)
def test_every_snapshot_is_projected_onto_the_chain_steps_and_any_contradiction_rejects(
    late: CapturedBookSnapshot, native_id: int
) -> None:
    assert_rejected(ingest(anchored(late)), f"book_knowledge_conflict:book-btc:{native_id}")


def test_consistent_snapshots_at_every_identity_are_accepted_and_change_no_record() -> None:
    late = [
        snapshot(1_001, BASE + 9_000, FIXED),
        snapshot(1_003, BASE + 9_100, T1003, depth=80),
        snapshot(1_004, BASE + 9_150, T1003, depth=120),
        snapshot(1_005, BASE + 9_200, T1005),
        snapshot(998, BASE + 9_300, FIXED, depth=55),
    ]
    base = ingest(anchored())
    assert [r.sequence_id for r in book_records(base)] == [1_000, 1_001, 1_003, 1_005]
    result = ingest(anchored(*late))
    assert result.dataset == base.dataset
    assert summary(result).attached_snapshot_count == 6


def test_knowledge_projects_backward_from_a_later_snapshot_onto_earlier_identities() -> None:
    later_first = [*KNOWLEDGE_CHAIN, snapshot(1_005, BASE + 5_000, T1005)]
    accepted = ingest([*later_first, snapshot(1_000, BASE + 6_000, FIXED)])
    assert [(r.sequence_id, r.available_at_ns) for r in book_records(accepted)] == [(1_005, BASE + 5_000)]
    contradiction = snapshot(1_000, BASE + 6_000, changed(FIXED, bids={Fraction("98.00"): 7}))
    assert_rejected(ingest([*later_first, contradiction]), "book_knowledge_conflict:book-btc:1000")


def test_inside_a_delta_span_only_the_levels_that_delta_lists_are_unconstrained() -> None:
    spanning = [
        snapshot(1_000, BASE + 100, FIXED),
        delta(999, 1_000, 998, BASE + 500),
        delta(1_001, 1_004, 1_000, BASE + 1_500, bids={Fraction("99.90"): 37}),
    ]
    inside = snapshot(1_002, BASE + 9_000, changed(FIXED, bids={Fraction("99.90"): 999}))
    assert_ready(ingest([*spanning, inside]))
    unmentioned = snapshot(1_002, BASE + 9_000, changed(FIXED, bids={Fraction("99.80"): 1}))
    assert_rejected(ingest([*spanning, unmentioned]), "book_knowledge_conflict:book-btc:1002")


# --- E: whole native continuity contract ---------------------------------------------------------------------------


def test_e_a_native_gap_opens_a_new_chain_that_emits_nothing_until_a_snapshot_proves_it() -> None:
    gapped = [
        item for item in moving_book() if not (type(item) is CapturedBookDelta and item.final_update_id == final_id(50))
    ]
    result = ingest(world_capture(gapped))
    assert [r.sequence_id for r in book_records(result)] == [final_id(s) for s in range(50)]
    book = summary(result)
    assert (book.native_chain_count, book.last_record_sequence_id) == (2, final_id(49))
    stranded = snapshot(final_id(50) - 1, event_ns(50) + 200, moving_state(49))
    resumed = ingest(world_capture([*gapped, stranded, snapshot(final_id(60), event_ns(60) + 10, moving_state(60))]))
    assert [r.sequence_id for r in book_records(resumed)] == [final_id(s) for s in (*range(50), *range(60, 101))]
    assert summary(resumed).unattached_snapshot_count == 1
    assert book_records(resumed)[50].available_at_ns == event_ns(60) + 10


def test_e_a_reconnect_that_loses_no_update_continues_and_replays_change_nothing() -> None:
    reconnect = [
        *(replace(moving_delta(step), receipt_ns=event_ns(40) + 10 + step) for step in range(30, 41)),
    ]
    result = ingest(world_capture([*moving_book(), *reconnect]))
    assert result.dataset == world_result().dataset
    assert summary(result).replay_count == 11
    assert summary(result).native_chain_count == 1


def test_e_a_stale_or_overlapping_non_replay_delta_is_a_sequence_regression() -> None:
    stale = delta(
        final_id(10) - 1, final_id(10), final_id(10) - 2, event_ns(10), receipt=event_ns(20) + 3, bids={Fraction(1): 1}
    )
    assert_rejected(
        ingest(
            world_capture(
                [*moving_book(), replace(stale, final_update_id=final_id(10) + 1, first_update_id=final_id(10) + 1)]
            )
        ),
        f"book_native_sequence_regression:book-btc:{final_id(10) + 1}",
    )
    overlapping = delta(final_id(20), final_id(20) + 1, final_id(19) + 1, event_ns(20) + 1, receipt=event_ns(20) + 2)
    assert_rejected(
        ingest(world_capture([*moving_book(), overlapping])),
        f"book_native_sequence_regression:book-btc:{final_id(20) + 1}",
    )
    assert_rejected(
        ingest(world_capture([*moving_book(), stale])), f"book_native_identity_conflict:book-btc:{final_id(10)}"
    )


def test_e_cross_chain_native_replay_protection_survives_a_gap() -> None:
    gapped = [
        item for item in moving_book() if not (type(item) is CapturedBookDelta and item.final_update_id == final_id(50))
    ]
    old = moving_delta(10)
    altered = replace(old, asks=(replace(old.asks[0], quantity=d(Fraction(old.asks[0].quantity) + 1)), *old.asks[1:]))
    late = replace(altered, receipt_ns=event_ns(80) + 7)
    assert_rejected(ingest(world_capture([*gapped, late])), f"book_native_identity_conflict:book-btc:{final_id(10)}")
    same = ingest(world_capture([*gapped, replace(old, receipt_ns=event_ns(80) + 7)]))
    assert summary(same).replay_count == 1
    assert_ready(same)


def test_e_native_identities_are_scoped_by_stream_and_never_leak_across_instruments() -> None:
    manifest, registry = variant_manifest(instruments=(ETH, INS))
    streams = (*DEFAULT_STREAMS, stream("book-eth", "order_book", instrument=ETH, epoch="epoch-eth"))
    eth_state = fixed_state(quantity=3)
    # Identical native ids in both scopes, with different books: never compared, never mixed.
    eth = [
        snapshot(1_000, BASE + 300, eth_state, stream="book-eth"),
        *fixed_tail(998, 12, step0=0, stream="book-eth", quantity=3),
    ]
    btc = [snapshot(1_000, BASE + 350, FIXED), *fixed_tail(998, 12, step0=0)]
    result = ingest(merged(btc, eth), manifest=manifest, registry=registry, declaration=declaration(streams=streams))
    assert_ready(result)
    btc_records, eth_records = book_records(result, INS), book_records(result, ETH)
    assert [r.sequence_id for r in btc_records] == [r.sequence_id for r in eth_records]
    assert all(values_of(r)["best_bid_quantity"] == d(100) for r in btc_records)
    assert all(values_of(r)["best_bid_quantity"] == d(3) for r in eth_records)
    conflicting_eth = snapshot(1_000, BASE + 30_000, fixed_state(quantity=4), stream="book-eth")
    assert_rejected(
        ingest(
            merged(btc, eth, [conflicting_eth]),
            manifest=manifest,
            registry=registry,
            declaration=declaration(streams=streams),
        ),
        "book_snapshot_conflict:book-eth:1000",
    )
    assert [s.native_epoch_id for s in result.evidence.streams] == ["epoch-1", "epoch-eth", "epoch-1", "epoch-1"]


def test_e_exact_depth_requires_fifty_known_levels_on_both_sides() -> None:
    def run(bid_depth: int, ask_depth: int) -> list[HistoricalPitRecord]:
        observations = [
            snapshot(1_000, BASE + 100, FIXED, bid_depth=bid_depth, ask_depth=ask_depth),
            *fixed_tail(998, 2, step0=0),
        ]
        result = ingest(observations)
        return [] if result.dataset is None else book_records(result)

    assert run(49, 300) == [] and run(300, 49) == []
    records = run(50, 50)
    assert [r.sequence_id for r in records] == [1_000, 1_002]
    names = set(values_of(records[0]))
    assert {f"bid_{i:02d}_price" for i in range(1, 51)} <= names and "bid_51_price" not in names
    assert values_of(records[0])["best_ask_price"] == values_of(records[0])["ask_01_price"]


def test_e_unknown_depth_beyond_the_horizon_is_never_treated_as_empty() -> None:
    far = {Fraction("90.00") - TICK * i: 1 for i in range(60)}
    removal = {Fraction("99.95") - TICK * i: 0 for i in range(20)}
    observations = [
        snapshot(1_000, BASE + 100, FIXED, depth=60),
        delta(999, 1_000, 998, BASE + 500),
        delta(1_001, 1_002, 1_000, BASE + 1_500, bids=far),
        delta(1_003, 1_004, 1_002, BASE + 2_500, bids=removal),
    ]
    result = ingest(observations)
    # 60 far bids are point-known, but the 40 levels left above the horizon cannot prove an exact top 50.
    assert [r.sequence_id for r in book_records(result)] == [1_000, 1_002]
    deeper = ingest([snapshot(1_000, BASE + 100, FIXED), *observations[1:]])
    assert [r.sequence_id for r in book_records(deeper)] == [1_000, 1_002, 1_004]


@pytest.mark.parametrize(
    ("bids", "asks", "reason"),
    [
        pytest.param(((Fraction("99.95"), 0),), None, "book_snapshot_level_invalid", id="zero-quantity"),
        pytest.param(((Fraction("99.95"), -1),), None, "book_snapshot_level_invalid", id="negative-quantity"),
        pytest.param(((Fraction(-1), 1),), None, "book_snapshot_level_invalid", id="negative-price"),
        pytest.param(((Fraction(0), 1),), None, "book_snapshot_level_invalid", id="zero-price"),
        pytest.param(
            ((Fraction("99.95"), 1), (Fraction("99.95"), 2)), None, "book_snapshot_level_invalid", id="duplicate"
        ),
        pytest.param((), None, "book_snapshot_side_empty", id="empty-bids"),
        pytest.param(None, (), "book_snapshot_side_empty", id="empty-asks"),
        pytest.param(((Fraction("100.05"), 1),), None, "book_snapshot_crossed", id="crossed"),
    ],
)
def test_e_invalid_snapshots_reject_the_capture(bids: object, asks: object, reason: str) -> None:
    base = snapshot(1_000, BASE + 100, FIXED)
    sides = {name: captured_levels(pairs) for name, pairs in (("bids", bids), ("asks", asks)) if pairs is not None}
    bad = replace(base, **sides)
    assert_rejected(ingest([bad, *fixed_tail(998, 2, step0=0)]), f"{reason}:book-btc:1000")


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        pytest.param({"bids": ((Fraction("99.95"), -1),)}, "book_delta_level_invalid", id="negative-quantity"),
        pytest.param({"bids": ((Fraction(0), 1),)}, "book_delta_level_invalid", id="zero-price"),
        pytest.param(
            {"asks": ((Fraction("100.05"), 1), (Fraction("100.05"), 2))}, "book_delta_level_invalid", id="duplicate"
        ),
        pytest.param({"first_update_id": 1_001}, "book_delta_span_invalid", id="first-after-final"),
        pytest.param({"first_update_id": 998}, "book_delta_span_invalid", id="first-at-predecessor"),
        pytest.param({"receipt_ns": BASE + 499}, "book_receipt_before_event", id="receipt-before-event"),
    ],
)
def test_e_invalid_deltas_reject_the_capture(changes: dict, reason: str) -> None:
    base = delta(999, 1_000, 998, BASE + 500)
    levels = {name: captured_levels(value) for name, value in changes.items() if name in ("bids", "asks")}
    bad = replace(base, **{**changes, **levels})
    observations = sorted([snapshot(1_000, BASE + 100, FIXED), bad], key=lambda item: item.receipt_ns)
    assert_rejected(ingest(observations), f"{reason}:book-btc:1000")


def test_e_a_known_crossed_tip_and_time_regressions_reject_the_capture() -> None:
    crossing = delta(1_001, 1_002, 1_000, BASE + 1_500, bids={Fraction("100.06"): 1})
    assert_rejected(
        ingest([snapshot(1_000, BASE + 100, FIXED), delta(999, 1_000, 998, BASE + 500), crossing]),
        "book_crossed:book-btc:1002",
    )
    earlier = delta(1_001, 1_002, 1_000, BASE + 400)
    assert_rejected(
        ingest(
            [
                snapshot(1_000, BASE + 100, FIXED),
                delta(999, 1_000, 998, BASE + 500),
                replace(earlier, receipt_ns=BASE + 600),
            ]
        ),
        "book_event_time_regression:book-btc:1002",
    )
    regressed = [*moving_book(range(3)), replace(moving_delta(3), receipt_ns=event_ns(2))]
    assert_rejected(ingest(regressed), "capture_receipt_regression:4")


def test_e_records_are_unique_strictly_increasing_and_available_in_capture_order() -> None:
    noisy = [*moving_book(), *(replace(moving_delta(s), receipt_ns=event_ns(s) + 300) for s in range(0, 101, 7))]
    result = ingest(world_capture(noisy))
    records = book_records(result)
    assert result.dataset == world_result().dataset
    identities = [(r.series_id, r.instrument, r.sequence_id) for r in result.dataset.records]
    assert len(identities) == len(set(identities))
    assert [r.sequence_id for r in records] == sorted({r.sequence_id for r in records})
    assert [r.available_at_ns for r in records] == sorted(r.available_at_ns for r in records)
    assert [r.event_time_ns for r in records] == sorted(r.event_time_ns for r in records)


# --- F: provenance, lineage, funding and marks ----------------------------------------------------------------------


def test_evidence_binds_the_source_declaration_anchors_capture_and_output() -> None:
    evidence = world_result().evidence
    manifest, _, registry = world_chain()
    assert (evidence.capture_id, evidence.source_id, evidence.source_object_id) == (
        "capture-1",
        "synthetic-fixture",
        "synthetic-capture-1.jsonl",
    )
    assert evidence.source_object_digest == "a" * 64
    assert (evidence.rights_status, evidence.rights_reference) == ("own_research", "note-1")
    assert evidence.source_manifest_digest == manifest.source_packet_evidence_digest
    assert evidence.data_requirement_registry_digest == data_requirement_registry_digest(registry)
    assert evidence.observation_count == len(world_capture())
    assert len(evidence.capture_digest) == 64 and evidence.capture_digest != evidence.dataset_digest
    assert world_result().dataset.source_reference == "capture:synthetic-fixture"
    assert [(s.stream_id, s.series_id, s.source_reference) for s in evidence.streams] == [
        ("book-btc", "book", "archive:book"),
        ("funding-btc", "funding-final", "archive:funding-final"),
        ("mark-btc", "mark", "archive:mark"),
    ]


@pytest.mark.parametrize(
    ("streams", "reason"),
    [
        pytest.param((stream("book-btc", "order_book", series="nope"),), "series_missing:book-btc", id="missing"),
        pytest.param((stream("book-btc", "order_book", series="mark"),), "series_key_mismatch:book-btc", id="key"),
        pytest.param(
            (stream("book-btc", "order_book", instrument=ETH),), "series_instrument_foreign:book-btc", id="instrument"
        ),
        pytest.param(
            (stream("book-btc", "order_book", reference="archive:elsewhere"),),
            "series_lineage_mismatch:book-btc:source_reference",
            id="source",
        ),
    ],
)
def test_every_stream_must_bind_exactly_its_ef3_series(streams: tuple, reason: str) -> None:
    assert_rejected(ingest(moving_book(range(3)), declaration=declaration(streams=streams)), reason)


def test_capture_rights_must_equal_the_ef3_series_rights_and_restricted_rights_fail() -> None:
    assert_rejected(
        ingest(moving_book(range(3)), declaration=declaration(rights_reference="note-2")),
        "series_lineage_mismatch:book-btc:rights_reference",
    )
    assert_rejected(
        ingest(moving_book(range(3)), declaration=declaration(rights_status="public_domain")),
        "series_lineage_mismatch:book-btc:rights_status",
    )
    manifest, registry = variant_manifest(rights=("restricted", "note-1"))
    result = ingest(
        moving_book(range(3)), manifest=manifest, registry=registry, declaration=declaration(rights_status="restricted")
    )
    assert result.evidence.status is EdgeEvidenceStatus.READY
    assert result.evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert code("capture_rights_restricted") in result.evidence.verdict_reason_codes
    assert result.dataset is not None and result.dataset.gate_verdict is EdgeGateVerdict.FAIL


def _registry_with(**changes: object) -> DataRequirementRegistry:
    registry = default_perp_data_requirement_registry()
    requirements = dict(registry.requirements)
    book = requirements[DataRequirementKey.ORDER_BOOK]
    requirements[DataRequirementKey.ORDER_BOOK] = replace(book, **changes)
    return DataRequirementRegistry(schema_version=registry.schema_version, requirements=requirements)


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"order_book_depth": 20}, "order_book_depth"),
        ({"order_book_level": "l1"}, "order_book_level"),
        ({"sequence_policy": "best_effort"}, "sequence_policy"),
        ({"resync_policy": "delta_only"}, "resync_policy"),
        ({"finality_policy": "sequence_gap_tolerate"}, "finality_policy"),
    ],
)
def test_a_registry_that_differs_from_the_implemented_l2_50_semantics_is_refused_never_downgraded(
    changes: dict, field: str
) -> None:
    manifest, registry = variant_manifest(registry=_registry_with(**changes))
    result = ingest(moving_book(range(3)), manifest=manifest, registry=registry)
    assert_rejected(result, f"series_semantics_unsupported:book-btc:{field}")


def test_ef3_and_registry_anchors_and_correlation_fail_closed() -> None:
    manifest, _, registry = world_chain()
    observations = moving_book(range(3))
    assert_rejected(ingest(observations, expected_source_manifest_digest="0" * 64), "source_manifest_digest_mismatch")
    assert_rejected(
        ingest(observations, expected_data_requirement_registry_digest="0" * 64), "data_requirement_registry_mismatch"
    )
    assert_rejected(ingest(observations, correlation_id="corr-2"), "source_manifest_correlation_mismatch")
    forged = replace(manifest, edge_family="forged_family")
    forged = replace(forged, source_packet_evidence_digest=edge_source_packet_evidence_digest(forged))
    result = ingest(
        observations, source_manifest=forged, expected_source_manifest_digest=forged.source_packet_evidence_digest
    )
    assert result.dataset is None and result.evidence.status is EdgeEvidenceStatus.REJECTED
    assert any(c.startswith(code("source_manifest_integrity_failure")) for c in result.evidence.integrity_reason_codes)
    other_manifest, other_registry = variant_manifest(instruments=(ETH, INS))
    assert_rejected(
        ingest(observations, expected_source_manifest_digest=other_manifest.source_packet_evidence_digest),
        "source_manifest_digest_mismatch",
    )
    assert data_requirement_registry_digest(other_registry) == data_requirement_registry_digest(registry)


def test_final_funding_must_be_published_after_settlement_on_the_declared_governed_grid() -> None:
    book = moving_book(range(3))
    missing = [item for item in fundings() if item.funding_time_ns != settlement_ns(4)]
    assert_rejected(ingest(merged(book, missing)), f"funding_interval_inconsistent:funding-btc:{settlement_ns(5)}")
    early = [
        replace(item, receipt_ns=item.funding_time_ns - 1) if item.funding_time_ns == settlement_ns(2) else item
        for item in fundings()
    ]
    assert_rejected(ingest(merged(book, early)), f"funding_observed_before_settlement:funding-btc:{settlement_ns(2)}")
    conflicting = CapturedFundingSettlement(
        "funding-btc", settlement_ns(3), settlement_ns(3) + 99, "0.000900000000000000"
    )
    assert_rejected(
        ingest(merged(book, fundings(), [conflicting])), f"funding_identity_conflict:funding-btc:{settlement_ns(3)}"
    )
    replayed = ingest(merged(book, fundings(), [replace(fundings()[3], receipt_ns=settlement_ns(3) + 99)]))
    funding = [r for r in replayed.dataset.records if r.series_id == "funding-final"]
    assert len(funding) == 10 and funding[3].available_at_ns == settlement_ns(3) + 10
    first = CapturedFundingSettlement("funding-btc", INTERVAL, INTERVAL + 1, "0.000100000000000000")
    assert_rejected(ingest(merged(book, [first])), f"funding_window_open_invalid:funding-btc:{INTERVAL}")
    streams = (*DEFAULT_STREAMS[:2], stream("funding-btc", "funding_rate", interval=2 * INTERVAL))
    assert_rejected(
        ingest(merged(book, fundings()), declaration=declaration(streams=streams)),
        f"funding_interval_inconsistent:funding-btc:{settlement_ns(1)}",
    )


def test_mark_identity_receipt_and_value_fail_closed() -> None:
    book = moving_book(range(3))
    good = marks(5)
    assert_rejected(
        ingest(merged(book, good, [replace(good[2], mark_price=d(1), receipt_ns=BASE + 9_000)])),
        f"mark_identity_conflict:mark-btc:{BASE + 2_000}",
    )
    assert_rejected(
        ingest(merged(book, [replace(good[1], receipt_ns=BASE + 999)])),
        f"mark_receipt_before_event:mark-btc:{BASE + 1_000}",
    )
    assert_rejected(
        ingest(merged(book, [replace(good[1], mark_price=d(0))])), f"mark_price_invalid:mark-btc:{BASE + 1_000}"
    )
    replayed = ingest(merged(book, good, [replace(good[2], receipt_ns=BASE + 9_000)]))
    assert len([r for r in replayed.dataset.records if r.series_id == "mark"]) == 5
    assert summary(replayed, "mark-btc").replay_count == 1


def test_capture_without_any_emittable_record_is_rejected() -> None:
    assert_rejected(ingest(fixed_tail(998, 3, step0=0)), "capture_without_records")


# --- determinism, digest binding and the total verifier ---------------------------------------------------------------


def test_identical_input_yields_identical_evidence_and_dataset() -> None:
    again = ingest(world_capture())
    assert again == world_result()
    assert authenticated_pit_ingress_evidence_digest(again.evidence) == again.evidence.ingress_digest


def test_any_captured_input_change_changes_the_capture_binding() -> None:
    base = world_result().evidence
    replayed = ingest(world_capture([*moving_book(), replace(moving_delta(5), receipt_ns=event_ns(5) + 100)]))
    assert replayed.dataset == world_result().dataset
    assert replayed.evidence.capture_digest != base.capture_digest
    assert replayed.evidence.ingress_digest != base.ingress_digest
    for changes in (
        {"source_object_digest": "b" * 64},
        {"source_object_id": "synthetic-capture-2.jsonl"},
        {"capture_id": "capture-2"},
    ):
        changed_result = ingest(world_capture(), declaration=declaration(**changes))
        assert changed_result.evidence.capture_digest != base.capture_digest
        assert changed_result.dataset == world_result().dataset
    epoch = (stream("book-btc", "order_book", epoch="epoch-2"), *DEFAULT_STREAMS[1:])
    assert (
        ingest(world_capture(), declaration=declaration(streams=epoch)).evidence.capture_digest != base.capture_digest
    )


def test_the_verifier_re_proves_evidence_against_the_exact_capture_and_is_total() -> None:
    clean_inputs = inputs(world_capture())
    evidence = world_result().evidence
    assert verify_authenticated_pit_ingress(evidence, clean_inputs).intact is True
    rejected_inputs = inputs(fixed_tail(998, 3, step0=0))
    rejected = build_authenticated_pit_ingress(rejected_inputs).evidence
    assert verify_authenticated_pit_ingress(rejected, rejected_inputs).intact is True
    other = inputs(world_capture([*moving_book(), replace(moving_delta(5), receipt_ns=event_ns(5) + 100)]))
    assert verify_authenticated_pit_ingress(evidence, other).intact is False
    forged = replace(evidence, record_count=evidence.record_count + 1)
    forged = replace(forged, ingress_digest=authenticated_pit_ingress_evidence_digest(forged))
    verification = verify_authenticated_pit_ingress(forged, clean_inputs)
    assert verification.intact is False and code("field_mismatch:record_count") in verification.reason_codes
    for junk in (None, 1, "evidence", object(), world_result(), authenticated_pit_ingress_evidence_to_dict(evidence)):
        assert verify_authenticated_pit_ingress(junk, clean_inputs).intact is False
    assert verify_authenticated_pit_ingress(evidence, None).intact is False
    payload = json.loads(json.dumps(authenticated_pit_ingress_evidence_to_dict(evidence)))
    assert authenticated_pit_ingress_evidence_from_payload(payload) == evidence


def test_structural_non_claims_are_defaults_no_input_can_set_and_forgery_fails() -> None:
    evidence = world_result().evidence
    for name, value in AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS:
        assert getattr(evidence, name) is value
    defaults = {f.name: f.default for f in fields(AuthenticatedPitIngressEvidence)}
    assert all(defaults[name] is value for name, value in AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS)
    flags = {name for name, _ in AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS}
    assert not flags & {f.name for f in fields(AuthenticatedPitIngressInputs)}
    assert not flags & {f.name for f in fields(CaptureDeclaration)}
    for flag in ("real_paper_observed", "source_qualified", "stage4_evidence_available", "live_ready"):
        forged = replace(evidence, **{flag: True})
        forged = replace(forged, ingress_digest=authenticated_pit_ingress_evidence_digest(forged))
        assert verify_authenticated_pit_ingress(forged, inputs(world_capture())).intact is False


def test_module_is_pure_deterministic_and_consumes_only_public_substrate() -> None:
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


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    pit.assert_single_assembly_path(
        ingress_module,
        "AuthenticatedPitIngressEvidence",
        "_assemble",
        "build_authenticated_pit_ingress",
        "_reassemble_evidence",
    )


# --- malformed caller input is a construction error ------------------------------------------------------------------

_SNAP = snapshot(1_000, BASE + 100, FIXED)


@pytest.mark.parametrize(
    ("observations", "match"),
    [
        pytest.param((), "observations_malformed", id="empty"),
        pytest.param(("snapshot",), "observation_malformed", id="foreign-type"),
        pytest.param((replace(_SNAP, stream_id="book-eth"),), "observation_stream_unknown", id="unknown-stream"),
        pytest.param((replace(_SNAP, stream_id="mark-btc"),), "observation_stream_kind_mismatch", id="kind"),
        pytest.param((replace(_SNAP, last_update_id=True),), "snapshot_last_update_id_invalid", id="bool-id"),
        pytest.param((replace(_SNAP, last_update_id=-1),), "snapshot_last_update_id_invalid", id="negative-id"),
        pytest.param((replace(_SNAP, last_update_id=2**63),), "snapshot_last_update_id_invalid", id="int64"),
        pytest.param((replace(_SNAP, receipt_ns=0),), "snapshot_receipt_ns_invalid", id="zero-receipt"),
        pytest.param(
            (replace(_SNAP, bids=(CapturedLevel("99.95", d(1)),)),),
            "snapshot_bids_price_noncanonical",
            id="noncanonical",
        ),
        pytest.param((replace(_SNAP, asks=[("100", "1")]),), "snapshot_asks_level_malformed", id="tuple-level"),
        pytest.param((replace(_SNAP, asks="levels"),), "snapshot_asks_malformed", id="string-levels"),
    ],
)
def test_malformed_observations_raise(observations: tuple, match: str) -> None:
    with pytest.raises(AuthenticatedPitIngressError, match=match):
        ingest(observations)


@pytest.mark.parametrize(
    ("changes", "match"),
    [
        pytest.param({"streams": ()}, "declaration_streams_malformed", id="no-streams"),
        pytest.param({"streams": (DEFAULT_STREAMS[0], DEFAULT_STREAMS[0])}, "stream_id_duplicate", id="duplicate-id"),
        pytest.param(
            {"streams": (DEFAULT_STREAMS[0], stream("book-two", "order_book"))}, "stream_scope_duplicate", id="scope"
        ),
        pytest.param(
            {"streams": (stream("liq", "liquidation", series="liq", profile=None),)}, "unsupported", id="liquidation"
        ),
        pytest.param(
            {"streams": (stream("book-btc", "order_book", interval=5),)}, "funding_interval_unexpected", id="interval"
        ),
        pytest.param(
            {"streams": (stream("funding-btc", "funding_rate", interval=0),)},
            "funding_interval_ns_invalid",
            id="zero-interval",
        ),
        pytest.param(
            {"streams": (stream("mark-btc", "mark_price", profile=PROFILE),)},
            "continuity_profile_unexpected",
            id="profile",
        ),
        pytest.param({"rights_status": "licensed"}, "rights_status_invalid", id="rights"),
        pytest.param({"source_object_digest": "A" * 64}, "source_object_digest_invalid", id="digest"),
        pytest.param({"source_reference": "capture:live feed"}, "forbidden_scope_token", id="scope-token"),
        pytest.param({"capture_id": "Capture 1"}, "capture_id_invalid", id="token"),
        pytest.param({"streams": (stream("BOOK", "order_book"),)}, "stream_id_invalid", id="stream-token"),
    ],
)
def test_malformed_declarations_raise(changes: dict, match: str) -> None:
    with pytest.raises(AuthenticatedPitIngressError, match=match):
        ingest(moving_book(range(2)), declaration=declaration(**changes))


def test_malformed_inputs_and_authority_objects_raise() -> None:
    with pytest.raises(AuthenticatedPitIngressError, match="inputs_malformed"):
        build_authenticated_pit_ingress(object())  # type: ignore[arg-type]
    with pytest.raises(AuthenticatedPitIngressError, match="source_manifest_malformed"):
        ingest(moving_book(range(2)), source_manifest=object())
    with pytest.raises(AuthenticatedPitIngressError, match="expected_source_manifest_digest_invalid"):
        ingest(moving_book(range(2)), expected_source_manifest_digest="x")
    with pytest.raises(AuthenticatedPitIngressError, match="ingress_id_invalid"):
        ingest(moving_book(range(2)), ingress_id=" ingress")
