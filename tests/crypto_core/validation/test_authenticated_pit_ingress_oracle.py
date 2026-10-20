"""Independent seeded oracle for the authenticated PIT ingress (SYNTHETIC_TEST_ONLY).

The oracle never reuses the ingress update logic.

* It generates a random native truth market (insertions, removals and re-quotes on both sides, native update spans
  with id gaps).
* It renders consistent captures from that truth: buffered starts, native sequence gaps with resync snapshots, narrow
  and broad snapshots at boundaries and strictly inside delta spans, late snapshots and identical replays.
* From the truth it recomputes every record the ingress must emit: native id, PIT availability and the exact top-50
  state.
* A brute-force per-price step timeline, written independently of the ingress, decides whether a mutated capture is
  still consistent, and the ingress must reject exactly the inconsistent ones.
"""

from __future__ import annotations

import random
from collections.abc import Iterator
from dataclasses import dataclass, replace
from fractions import Fraction

import pytest

from crypto_core.validation.authenticated_pit_ingress import CapturedBookDelta, CapturedBookSnapshot, CapturedLevel
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus

try:
    import test_authenticated_pit_ingress as fx
except ImportError:  # pragma: no cover - package-style collection
    from tests.crypto_core.validation import test_authenticated_pit_ingress as fx

BASE = fx.BASE
DEPTH = fx.DEPTH
Book = tuple[dict[int, int], dict[int, int]]


def seeded(seed: int) -> random.Random:
    """The one deterministic generator of the SYNTHETIC oracle (reproducible fixtures, never cryptography)."""

    return random.Random(seed)  # noqa: S311 - seeded test fixture generator, not a security primitive


@dataclass(frozen=True)
class Event:
    first: int
    final: int
    previous: int
    event_ns: int
    levels: Book


@dataclass(frozen=True)
class Market:
    start: int
    events: tuple[Event, ...]
    states: tuple[Book, ...]


def market(rng: random.Random) -> Market:
    """A SYNTHETIC truth market in integer ticks of 0.01; ``states[i + 1]`` is the book after ``events[i]``."""

    bids = {10_000 - 5 - i: rng.randint(1, 9) for i in range(80)}
    asks = {10_000 + 5 + i: rng.randint(1, 9) for i in range(80)}
    states = [(dict(bids), dict(asks))]
    events: list[Event] = []
    previous = start = 1_000 + rng.randint(0, 5)
    event_ns = BASE + rng.randint(0, 50)
    for _ in range(rng.randint(40, 70)):
        first = previous + 1 + rng.randint(0, 2)
        final = first + rng.randint(0, 2)
        event_ns += rng.randint(0, 3) * 100
        updates: Book = ({}, {})
        for _change in range(rng.randint(0, 4)):
            side = rng.randint(0, 1)
            book, other = (bids, asks) if side == 0 else (asks, bids)
            ranked = sorted(book, reverse=side == 0)
            kind = rng.choice(("quantity", "insert", "remove") * 3 + ("deep",))
            if kind == "quantity":
                price, quantity = rng.choice(ranked[:20]), rng.randint(1, 9)
            elif kind == "deep":
                # Far from the best: mostly beyond any snapshot coverage, so it stays point knowledge.
                price = ranked[0] + (-1 if side == 0 else 1) * rng.randint(60, 200)
                if price <= 0 or price in book:
                    continue
                quantity = rng.randint(1, 9)
            elif kind == "insert":
                edge = min(other) if side == 0 else max(other)
                span = range(ranked[0] - 40, ranked[0] + 4) if side == 0 else range(ranked[0] - 3, ranked[0] + 41)
                candidates = [p for p in span if p not in book and (p < edge if side == 0 else p > edge)]
                if not candidates:
                    continue
                price, quantity = rng.choice(candidates), rng.randint(1, 9)
            else:
                if len(book) <= 62:
                    continue
                price, quantity = rng.choice(ranked[:30]), 0
            if quantity:
                book[price] = quantity
            else:
                book.pop(price, None)
            updates[side][price] = quantity
        events.append(Event(first, final, previous, event_ns, updates))
        states.append((dict(bids), dict(asks)))
        previous = final
    return Market(start, tuple(events), tuple(states))


def truth_at(world: Market, native_id: int) -> Book:
    """Truth at a native id; strictly inside a delta span the pre-delta book (its listed levels are unconstrained)."""

    if native_id == world.start:
        return world.states[0]
    for index, event in enumerate(world.events):
        if event.previous < native_id <= event.final:
            return world.states[index + 1] if native_id == event.final else world.states[index]
    raise AssertionError(native_id)


def levels_of(side: dict[int, int], *, descending: bool, depth: int | None = None) -> tuple[CapturedLevel, ...]:
    ordered = sorted(side.items(), reverse=descending)[:depth]
    return tuple(CapturedLevel(fx.d(Fraction(price, 100)), fx.d(quantity)) for price, quantity in ordered)


def delta_of(event: Event, receipt: int) -> CapturedBookDelta:
    return CapturedBookDelta(
        "book-btc",
        event.first,
        event.final,
        event.previous,
        event.event_ns,
        receipt,
        levels_of(event.levels[0], descending=False),
        levels_of(event.levels[1], descending=False),
    )


def snapshot_of(world: Market, native_id: int, receipt: int, depth: int) -> CapturedBookSnapshot:
    bids, asks = truth_at(world, native_id)
    return CapturedBookSnapshot(
        "book-btc",
        native_id,
        receipt,
        levels_of(bids, descending=True, depth=depth),
        levels_of(asks, descending=False, depth=depth),
    )


def capture(rng: random.Random, world: Market) -> list:
    """A consistent capture of ``world`` in receipt order."""

    count = len(world.events)
    skipped: set[int] = set()
    for _ in range(rng.randint(0, 2)):
        begin = rng.randint(6, count - 12)
        skipped.update(range(begin, begin + rng.randint(1, 3)))
    delivered = [index for index in range(count) if index not in skipped]
    timeline: list[tuple[int, int, object]] = []
    receipts: dict[int, int] = {}
    receipt = 0
    for index in delivered:
        receipt = max(receipt, world.events[index].event_ns + 1 + rng.randint(0, 20))
        receipts[index] = receipt
        timeline.append((receipt, len(timeline), delta_of(world.events[index], receipt)))
    first, last = receipts[delivered[0]], receipt
    heads = [index for position, index in enumerate(delivered) if position == 0 or delivered[position - 1] != index - 1]
    snapshots: list[tuple[int, CapturedBookSnapshot]] = []
    for head in heads:
        run = []
        for index in range(head, count):
            if index in skipped:
                break
            run.append(index)
        anchor = world.events[rng.choice(run[:4])]
        native_id = rng.randint(anchor.previous, anchor.final)
        depth = rng.randint(50, 80) if rng.random() < 0.7 else rng.randint(20, 49)
        low, high = receipts[run[0]] - 300, receipts[run[min(5, len(run) - 1)]] + 300
        snapshots.append((rng.randint(low, high), snapshot_of(world, native_id, 0, depth)))
    for _ in range(rng.randint(0, 3)):
        native_id = rng.randint(world.start, world.events[-1].final)
        snapshots.append((rng.randint(first, last + 500), snapshot_of(world, native_id, 0, rng.randint(10, 80))))
    if snapshots and rng.random() < 0.3:
        moment, chosen = rng.choice(snapshots)
        again = snapshot_of(world, chosen.last_update_id, 0, rng.randint(10, 80))
        snapshots.append((moment + rng.randint(1, 900), again))
    for moment, snap in snapshots:
        timeline.append((moment, len(timeline), replace(snap, receipt_ns=moment)))
    for _ in range(rng.randint(0, 4)):
        index = rng.choice(delivered)
        moment = receipts[index] + rng.randint(1, 3_000)
        timeline.append((moment, len(timeline), delta_of(world.events[index], moment)))
    return [item for _, _, item in sorted(timeline, key=lambda entry: (entry[0], entry[1]))]


def _ticks(level: CapturedLevel) -> tuple[Fraction, Fraction]:
    return Fraction(level.price), Fraction(level.quantity)


def _sides(item: object) -> tuple[dict[Fraction, Fraction], dict[Fraction, Fraction]]:
    return dict(map(_ticks, item.bids)), dict(map(_ticks, item.asks))  # type: ignore[attr-defined]


def _covers(sides: tuple[dict, dict], side: int, price: Fraction) -> bool:
    return price >= min(sides[0]) if side == 0 else price <= max(sides[1])


def _book_values(book: Book) -> dict[str, str]:
    as_fractions = tuple({Fraction(p, 100): Fraction(q) for p, q in side.items()} for side in book)
    return fx.expected_book_values(as_fractions)  # type: ignore[arg-type]


def expected_records(world: Market, observations: list) -> list[tuple[int, int, dict[str, str]]]:
    """Emission recomputed from the truth: the tip of the newest chain, once, when its top 50 is inside coverage."""

    by_final = {event.final: index for index, event in enumerate(world.events)}
    seen: set[int] = set()
    chains: list[dict] = []
    pending: list[CapturedBookSnapshot] = []
    emitted: list[tuple[int, int, dict[str, str]]] = []
    last: int | None = None

    def attach(chain: dict, snap: CapturedBookSnapshot) -> None:
        bids, asks = _sides(snap)
        low, high = min(bids), max(asks)
        chain["bid"] = low if chain["bid"] is None else min(chain["bid"], low)
        chain["ask"] = high if chain["ask"] is None else max(chain["ask"], high)

    for item in observations:
        if type(item) is CapturedBookDelta:
            if item.final_update_id in seen:
                continue
            seen.add(item.final_update_id)
            if not chains or item.previous_final_update_id > chains[-1]["tip"]:
                chains.append({"start": item.previous_final_update_id, "tip": None, "bid": None, "ask": None})
                pending = [snap for snap in pending if snap.last_update_id >= item.previous_final_update_id]
            chain = chains[-1]
            chain["tip"], chain["index"] = item.final_update_id, by_final[item.final_update_id]
            for snap in [snap for snap in pending if snap.last_update_id <= chain["tip"]]:
                attach(chain, snap)
            pending = [snap for snap in pending if snap.last_update_id > chain["tip"]]
        else:
            target = next((c for c in chains if c["start"] <= item.last_update_id <= c["tip"]), None)
            if target is not None:
                attach(target, item)
            elif not chains or item.last_update_id > chains[-1]["tip"]:
                pending.append(item)
        if not chains or chains[-1]["bid"] is None:
            continue
        chain = chains[-1]
        if last is not None and chain["tip"] <= last:
            continue
        bids, asks = world.states[chain["index"] + 1]
        known_bids = sum(1 for price in bids if Fraction(price, 100) >= chain["bid"])
        known_asks = sum(1 for price in asks if Fraction(price, 100) <= chain["ask"])
        if known_bids >= DEPTH and known_asks >= DEPTH:
            emitted.append((chain["tip"], item.receipt_ns, _book_values(world.states[chain["index"] + 1])))
            last = chain["tip"]
    return emitted


def _native(item: CapturedBookDelta) -> tuple:
    return (item.first_update_id, item.previous_final_update_id, item.event_time_ns, _sides(item))


def consistent(observations: list) -> bool:
    """Brute force: one content per final id, chain order, same-id agreement and one value per price step."""

    deltas: dict[int, tuple] = {}
    chains: list[list[CapturedBookDelta]] = []
    snapshots: list[CapturedBookSnapshot] = []
    for item in observations:
        if type(item) is not CapturedBookDelta:
            snapshots.append(item)
            continue
        if item.final_update_id in deltas:
            if deltas[item.final_update_id] != _native(item):
                return False
            continue
        deltas[item.final_update_id] = _native(item)
        if not chains or item.previous_final_update_id > chains[-1][-1].final_update_id:
            chains.append([item])
        elif item.previous_final_update_id == chains[-1][-1].final_update_id:
            chains[-1].append(item)
        else:
            return False
    for index, one in enumerate(snapshots):
        for other in snapshots[index + 1 :]:
            if one.last_update_id != other.last_update_id:
                continue
            for side in (0, 1):
                for a, b in ((_sides(one), _sides(other)), (_sides(other), _sides(one))):
                    for price, quantity in a[side].items():
                        if _covers(b, side, price) and b[side].get(price, 0) != quantity:
                            return False
    for snap in snapshots:
        native = deltas.get(snap.last_update_id)
        if native is None:
            continue
        known = _sides(snap)
        for side in (0, 1):
            for price, quantity in native[3][side].items():
                if _covers(known, side, price) and known[side].get(price, 0) != quantity:
                    return False
    universe: tuple[set, set] = (set(), set())
    for item in observations:
        for side, levels in enumerate(_sides(item)):
            universe[side].update(levels)
    for chain in chains:
        start, tip = chain[0].previous_final_update_id, chain[-1].final_update_id
        attached = [(snap.last_update_id, _sides(snap)) for snap in snapshots if start <= snap.last_update_id <= tip]
        for side in (0, 1):
            for price in universe[side]:
                mentions = [
                    (pos, _sides(item)[side][price]) for pos, item in enumerate(chain) if price in _sides(item)[side]
                ]
                base: Fraction | None = None
                for native_id, known in attached:
                    if not _covers(known, side, price):
                        continue
                    value = known[side].get(price, Fraction(0))
                    if native_id == start:
                        step = 0
                    else:
                        position = next(pos for pos, item in enumerate(chain) if item.final_update_id >= native_id)
                        boundary = chain[position].final_update_id == native_id
                        if not boundary and any(pos == position for pos, _ in mentions):
                            continue
                        step = sum(1 for pos, _ in mentions if pos < position or (boundary and pos == position))
                    if step:
                        if mentions[step - 1][1] != value:
                            return False
                    elif base is None:
                        base = value
                    elif base != value:
                        return False
    return True


def _future_level(world: Market, snap: CapturedBookSnapshot, side: str) -> CapturedLevel | None:
    """A level some later delta inserts that the truth at the snapshot id lacks, inside its coverage, kept at least
    30 ticks behind the snapshot's best so that listing it early can never cross the book."""

    index = 0 if side == "bids" else 1
    listed = [Fraction(level.price) * 100 for level in getattr(snap, side)]
    best, horizon = (max(listed), min(listed)) if index == 0 else (min(listed), max(listed))
    present_at_snapshot = truth_at(world, snap.last_update_id)[index]
    for event in world.events:
        if event.final <= snap.last_update_id:
            continue
        for price, quantity in sorted(event.levels[index].items()):
            behind = best - price if index == 0 else price - best
            inside = price >= horizon if index == 0 else price <= horizon
            if quantity and price not in present_at_snapshot and inside and behind >= 30:
                return CapturedLevel(fx.d(Fraction(price, 100)), fx.d(quantity))
    return None


def mutate(rng: random.Random, world: Market, observations: list) -> list:
    """One seeded change that may or may not contradict other facts (never crossing, never an invalid level)."""

    items = list(observations)
    deltas = [i for i, item in enumerate(items) if type(item) is CapturedBookDelta and (item.bids or item.asks)]
    snapshots = [i for i, item in enumerate(items) if type(item) is CapturedBookSnapshot]
    kind = rng.choice(
        ("replay", "delta_quantity", "snapshot_quantity", "snapshot_drop", "snapshot_insert", "snapshot_future", "twin")
    )
    if kind == "twin" and snapshots:
        index = rng.choice(snapshots)
        original = items[index]
        side = rng.choice(("bids", "asks"))
        levels = list(getattr(original, side))
        k = rng.randrange(len(levels))
        levels[k] = replace(levels[k], quantity=fx.d(Fraction(levels[k].quantity) + 1))
        position = rng.randint(index + 1, len(items))
        items.insert(position, replace(original, receipt_ns=items[position - 1].receipt_ns, **{side: tuple(levels)}))
        return items
    if kind in ("replay", "delta_quantity") and deltas:
        index = rng.choice(deltas)
        original = items[index]
        side = "bids" if original.bids else "asks"
        levels = list(getattr(original, side))
        positive = [k for k, level in enumerate(levels) if Fraction(level.quantity) > 0]
        if kind == "replay":
            k = rng.randrange(len(levels))
            levels[k] = replace(levels[k], quantity=fx.d(Fraction(levels[k].quantity) + 1))
            position = rng.randint(index + 1, len(items))
            copy = replace(original, receipt_ns=items[position - 1].receipt_ns, **{side: tuple(levels)})
            items.insert(position, copy)
        elif positive:
            k = rng.choice(positive)
            levels[k] = replace(levels[k], quantity=fx.d(Fraction(levels[k].quantity) + rng.randint(1, 3)))
            items[index] = replace(original, **{side: tuple(levels)})
        return items
    if snapshots:
        index = rng.choice(snapshots)
        snap = items[index]
        side = rng.choice(("bids", "asks"))
        levels = list(getattr(snap, side))
        future = _future_level(world, snap, side) if kind == "snapshot_future" else None
        if future is not None:
            levels.append(future)
        elif kind == "snapshot_drop" and len(levels) > 1:
            del levels[rng.randrange(len(levels))]
        elif kind == "snapshot_insert" and len(levels) > 46:
            anchor = Fraction(levels[rng.randrange(45, len(levels) - 1)].price)
            half_tick = Fraction(-1, 200) if side == "bids" else Fraction(1, 200)
            levels.append(CapturedLevel(fx.d(anchor + half_tick), fx.d(rng.randint(1, 9))))
        else:
            k = rng.randrange(len(levels))
            levels[k] = replace(levels[k], quantity=fx.d(Fraction(levels[k].quantity) + rng.randint(1, 3)))
        items[index] = replace(snap, **{side: tuple(levels)})
    return items


def _outcome(observations: list):
    return fx.ingest(observations)


def _emitted(result) -> list[tuple[int, int, dict[str, str]]]:
    return [(r.sequence_id, r.available_at_ns, fx.values_of(r)) for r in fx.book_records(result)]


SEEDS = range(120)


@pytest.mark.parametrize("seed", SEEDS)
def test_clean_seeded_captures_emit_exactly_the_oracle_records(seed: int) -> None:
    rng = seeded(seed)
    world = market(rng)
    observations = capture(rng, world)
    assert consistent(observations)
    expected = expected_records(world, observations)
    result = _outcome(observations)
    if not expected:
        assert result.evidence.integrity_reason_codes == (fx.code("capture_without_records"),)
        return
    fx.assert_ready(result)
    assert _emitted(result) == expected


@pytest.mark.parametrize("seed", SEEDS)
def test_mutated_captures_are_rejected_exactly_when_the_independent_timeline_finds_a_contradiction(seed: int) -> None:
    rng = seeded(10_000 + seed)
    world = market(rng)
    observations = mutate(rng, world, capture(rng, world))
    result = _outcome(observations)
    if consistent(observations):
        assert result.evidence.status is EdgeEvidenceStatus.READY or result.evidence.integrity_reason_codes == (
            fx.code("capture_without_records"),
        ), result.evidence.integrity_reason_codes
    else:
        assert result.dataset is None and result.evidence.status is EdgeEvidenceStatus.REJECTED
        assert any(code.startswith(fx.code("book_")) for code in result.evidence.integrity_reason_codes)


def test_the_seeded_matrix_exercises_every_scenario_and_both_verdicts() -> None:
    features = dict.fromkeys(("native_gap", "replay", "inside_span", "late_snapshot", "records"), 0)
    verdicts = {True: 0, False: 0}
    for seed in SEEDS:
        rng = seeded(seed)
        world = market(rng)
        observations = capture(rng, world)
        finals = [item.final_update_id for item in observations if type(item) is CapturedBookDelta]
        boundaries = {world.start, *(event.final for event in world.events)}
        reached = 0
        late = False
        for item in observations:
            if type(item) is CapturedBookDelta:
                reached = max(reached, item.final_update_id)
            elif item.last_update_id <= reached:
                late = True
        features["native_gap"] += len(set(finals)) < len(world.events)
        features["replay"] += len(finals) != len(set(finals))
        features["inside_span"] += any(
            type(item) is CapturedBookSnapshot and item.last_update_id not in boundaries for item in observations
        )
        features["late_snapshot"] += late
        features["records"] += bool(expected_records(world, observations))
        mutated_rng = seeded(10_000 + seed)
        mutated_world = market(mutated_rng)
        verdicts[consistent(mutate(mutated_rng, mutated_world, capture(mutated_rng, mutated_world)))] += 1
    assert all(count >= 10 for count in features.values()) and features["records"] >= 60, features
    assert verdicts[True] >= 15 and verdicts[False] >= 30, verdicts


def test_seeded_captures_are_deterministic() -> None:
    rng_a, rng_b = seeded(7), seeded(7)
    first = capture(rng_a, market(rng_a))
    second = capture(rng_b, market(rng_b))
    assert first == second
    assert _outcome(first) == _outcome(second)


# --- H: bounded capture scale (local proof; resource numbers are reported, never asserted) ---------------------------


def _ladder(step: int, depth: int = 300) -> fx.State:
    mid = Fraction(100) + Fraction(step + 1, 100)
    bids, asks = {}, {}
    for index in range(depth):
        bump = Fraction(1 + (step + index) % 3) if index < 3 else Fraction(0)
        bid = mid - Fraction(5, 100) - fx.TICK * index
        ask = mid + Fraction(5, 100) + fx.TICK * index
        bids[bid] = Fraction(50 + int(bid * 100) % 7) + bump
        asks[ask] = Fraction(50 + int(ask * 100) % 7) + bump
    return bids, asks


def ladder_capture(steps: int, *, resync_every: int = 200) -> Iterator[object]:
    """The moving SYNTHETIC ladder as a streaming capture with a consistent broad snapshot every ``resync_every``."""

    yield fx.snapshot(1_000, BASE + 400, _ladder(-1))
    before = _ladder(-1)
    for step in range(steps):
        after = _ladder(step)
        bids, asks = fx.transition(before, after)
        yield fx.delta(
            fx.final_id(step) - 1, fx.final_id(step), fx.final_id(step) - 2, fx.event_ns(step), bids=bids, asks=asks
        )
        if step and step % resync_every == 0:
            yield fx.snapshot(fx.final_id(step), fx.event_ns(step) + 2, after)
        before = after


@pytest.mark.slow
def test_bounded_capture_scale_keeps_every_native_identity_and_emits_every_known_tip() -> None:
    steps = 3_000
    result = fx.ingest(list(ladder_capture(steps)))
    fx.assert_ready(result)
    book = fx.summary(result)
    assert (book.observation_count, book.native_chain_count, book.replay_count) == (steps + 1 + 14, 1, 0)
    records = fx.book_records(result)
    assert len(records) == steps
    assert fx.values_of(records[-1]) == fx.expected_book_values(_ladder(steps - 1))
