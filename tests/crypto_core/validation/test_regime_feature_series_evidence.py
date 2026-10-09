"""Tests for the RF-3 regime feature series evidence (``regime_feature_series_evidence``).

Fixtures:
* the authentic EF-2 -> EF-3 manifest of the EF-3 test module, whose eligible ``mark-majors`` mark-price series covers
  ``BTC-PERPETUAL``;
* an authentic ``HistoricalPitDataset`` built by the accepted public builders over that exact manifest, one record per
  UTC day carrying a synthetic ``close`` value;
* the RF-2 test module's governed synthetic policy (F1 over 3 closes, F2 over 2 closes).

Every close, coordinate, threshold and approval is a SYNTHETIC TEST VALUE. Expected feature values come from an
independent exact oracle (integer square roots and plain ``Fraction`` arithmetic), expected provenance from the
dataset records themselves, and every retained-digest attack is refused by the ACCEPTED record-digest recomputation
(``historical_pit_record_digest`` and ``verify_historical_pit_dataset``), never by RF-3 producing both sides.
"""

from __future__ import annotations

import ast
import dataclasses
import decimal
import functools
import json
import math
import re
from collections.abc import Sequence
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.regime_feature_series_evidence as series_module
from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_source_packet_evidence import EdgeSourcePacketEvidence
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
    historical_pit_dataset_digest,
    historical_pit_record_digest,
    verify_historical_pit_dataset,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_F1_FORMULA_POLICY_ID,
    REGIME_F2_FORMULA_POLICY_ID,
    REGIME_NON_CLAIM_FLAGS,
    REGIME_NUMERIC_POLICY_ID,
    RegimeFeatureClass,
    RegimeFeaturePolicy,
)
from crypto_core.validation.regime_feature_series_evidence import (
    REGIME_FEATURE_SERIES_RULE_SET_DIGEST,
    RegimeDailyCloseObservation,
    RegimeFeatureClaim,
    RegimeFeatureSeriesError,
    RegimeFeatureSeriesEvidence,
    RegimeFeatureSeriesInputs,
    build_regime_feature_series_evidence,
    measure_regime_feature_value,
    regime_feature_series_evidence_digest,
    regime_feature_series_evidence_to_dict,
    regime_feature_series_rule_set,
    verify_regime_feature_series_evidence,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so cached fixtures are shared with their own tests
    import test_edge_source_packet_evidence as ef3t
    import test_regime_feature_policy as rf2t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_source_packet_evidence as ef3t
    from tests.crypto_core.validation import test_regime_feature_policy as rf2t

_PREFIX = "regime_feature_series_evidence"
SOURCE = Path(series_module.__file__).read_text(encoding="utf-8")
DAY = 86_400_000_000_000
D0 = 20_000  # SYNTHETIC first source day
F1, F2 = RegimeFeatureClass.F1_REALIZED_VOL, RegimeFeatureClass.F2_DRAWDOWN_STATE
SERIES, INSTRUMENT, VOL, DD, VALUE = rf2t.SERIES, rf2t.INSTRUMENT, rf2t.VOL, rf2t.DD, rf2t.VALUE
# SYNTHETIC closes of days D0 .. D0+9: rises, falls, a rebound and new lows.
CLOSES = ("100", "110", "99", "108.9", "100", "101", "95", "96", "97", "90")
LOOKBACK = {VOL: 3, DD: 2}


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RF-3 construction error."""

    return pytest.raises(RegimeFeatureSeriesError, match=f"^{re.escape(code(text))}$")


def price(value: str) -> str:
    return rf2t.d(value)


@functools.cache
def manifest() -> EdgeSourcePacketEvidence:
    return ef3t._manifest()


def pit_record(
    day: int,
    close: str | None = None,
    *,
    sequence: int | None = None,
    series: str = SERIES,
    instrument: str = INSTRUMENT,
    event: int | None = None,
    available: int | None = None,
    finalized: int | None = None,
    vintage: str | None = None,
    values: tuple[HistoricalPitValue, ...] | None = None,
) -> HistoricalPitRecord:
    """An authentic record of source day ``day`` (digest computed by the accepted builder); its close instant,
    availability and finality default to the end of the day, and sequence ids leave room for extra records."""

    end = (day + 1) * DAY
    return build_historical_pit_record(
        series_id=series,
        data_requirement_key="mark_price",
        instrument=instrument,
        sequence_id=(day - D0) * 10 if sequence is None else sequence,
        event_time_ns=end if event is None else event,
        available_at_ns=end if available is None else available,
        finalized_at_ns=end if finalized is None else finalized,
        revision_vintage_id=vintage,
        values=(HistoricalPitValue(VALUE, close),) if values is None else values,  # type: ignore[arg-type]
    )


def pit_records(
    closes: Sequence[str] = CLOSES, *, start: int = D0, skip: Sequence[int] = ()
) -> tuple[HistoricalPitRecord, ...]:
    return tuple(
        pit_record(start + index, price(close)) for index, close in enumerate(closes) if start + index not in skip
    )


def dataset(
    records: Sequence[HistoricalPitRecord] | None = None,
    *,
    source_manifest: EdgeSourcePacketEvidence | None = None,
    **overrides: object,
) -> HistoricalPitDataset:
    """A ``HistoricalPitDataset`` built by the accepted public builder over ``source_manifest`` (the default world)."""

    source = manifest() if source_manifest is None else source_manifest
    values: dict[str, object] = {
        "expected_source_manifest_digest": source.source_packet_evidence_digest,
        "expected_data_requirement_registry_digest": source.data_requirement_registry_digest,
        "dataset_id": "rf3-pit-dataset-1",
        "correlation_id": source.correlation_id,
        "source_reference": "archive:synthetic-mark-closes",
        "rights_status": "own_research",
        "rights_reference": "research-license-1",
        "records": pit_records() if records is None else tuple(records),
    }
    values.update(overrides)
    return build_historical_pit_dataset(source, **values)  # type: ignore[arg-type]


@functools.cache
def default_dataset() -> HistoricalPitDataset:
    return dataset()


@functools.cache
def default_policy() -> RegimeFeaturePolicy:
    return rf2t.governed()


def series_inputs(
    *,
    policy: RegimeFeaturePolicy | None = None,
    records: Sequence[HistoricalPitRecord] | None = None,
    pit_dataset: HistoricalPitDataset | None = None,
    source_manifest: EdgeSourcePacketEvidence | None = None,
    last: int = D0 + len(CLOSES),
    as_of_day: int | None = None,
    **overrides: object,
) -> RegimeFeatureSeriesInputs:
    """The default world: features for days D0+3 .. D0+10, as of the start of the last feature day."""

    source = manifest() if source_manifest is None else source_manifest
    if pit_dataset is None:
        pit_dataset = (
            default_dataset()
            if records is None and source_manifest is None
            else dataset(records, source_manifest=source)
        )
    values: dict[str, object] = {
        "feature_series_id": "rf3-synthetic-1",
        "correlation_id": source.correlation_id,
        "policy": default_policy() if policy is None else policy,
        "source_manifest": source,
        "source_manifest_digest": source.source_packet_evidence_digest,
        "pit_dataset": pit_dataset,
        "pit_dataset_digest": pit_dataset.dataset_digest,
        "as_of_ns": (last if as_of_day is None else as_of_day) * DAY,
        "first_feature_day": D0 + 3,
        "last_feature_day": last,
        "claims": (),
    }
    values.update(overrides)
    return RegimeFeatureSeriesInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> RegimeFeatureSeriesEvidence:
    return build_regime_feature_series_evidence(inputs)  # type: ignore[arg-type]


def decide(inputs: RegimeFeatureSeriesInputs) -> RegimeFeatureSeriesEvidence:
    """Build, then re-prove by reconstruction: every evidence a test reads is intact."""

    evidence = build(inputs)
    verification = verify_regime_feature_series_evidence(evidence, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == evidence.feature_series_digest
    assert json.loads(verification.canonical_json) == regime_feature_series_evidence_to_dict(evidence)
    assert {name: getattr(evidence, name) for name, _ in REGIME_NON_CLAIM_FLAGS} == dict(REGIME_NON_CLAIM_FLAGS)
    return evidence


@functools.cache
def default_evidence() -> RegimeFeatureSeriesEvidence:
    return decide(series_inputs())


def record(evidence: RegimeFeatureSeriesEvidence, feature_id: str, day: int):  # noqa: ANN201
    (match,) = [item for item in evidence.records if item.feature_id == feature_id and item.target_day_index == day]
    return match


def reseal(evidence: RegimeFeatureSeriesEvidence, **changes: object) -> RegimeFeatureSeriesEvidence:
    changed = replace(evidence, **changes)  # type: ignore[arg-type]
    return replace(changed, feature_series_digest=regime_feature_series_evidence_digest(changed))


def reseal_dataset(source: HistoricalPitDataset, **changes: object) -> HistoricalPitDataset:
    changed = replace(source, **changes)  # type: ignore[arg-type]
    return replace(changed, dataset_digest=historical_pit_dataset_digest(changed))


# --- independent oracles --------------------------------------------------------------------------------------------


def oracle_square_root(variance: Fraction) -> str:
    """Half-even scale-18 ``sqrt``: an integer square root of the floor, then the half unit decided exactly."""

    scaled = variance * 10**36
    floor = math.isqrt(scaled.numerator // scaled.denominator)
    upper = (2 * floor + 1) ** 2
    units = floor + 1 if 4 * scaled > upper or (4 * scaled == upper and floor % 2) else floor
    return f"{units // 10**18}.{units % 10**18:018d}"


def oracle_f1(closes: Sequence[str]) -> str:
    values = [Fraction(close) for close in closes]
    returns = [current / previous - 1 for previous, current in zip(values, values[1:])]
    mean = sum(returns, Fraction(0)) / len(returns)
    return oracle_square_root(sum(((item - mean) ** 2 for item in returns), Fraction(0)) / (len(returns) - 1))


def oracle_f2(closes: Sequence[str]) -> str:
    values = [Fraction(close) for close in closes]
    return rf2t.oracle_half_even(1 - values[-1] / max(values))


ORACLES = {VOL: oracle_f1, DD: oracle_f2}


def window_closes(day: int, feature_id: str, closes: Sequence[str] = CLOSES) -> list[str]:
    start = day - LOOKBACK[feature_id] - D0
    return [price(close) for close in closes[start : day - D0]]


def oracle_source(source: HistoricalPitRecord, day: int) -> dict[str, object]:
    """The derived provenance of one consumed close, read straight from the authenticated record."""

    (value,) = [item.value for item in source.values if item.name == VALUE]
    return {
        "series_id": source.series_id,
        "instrument_id": source.instrument,
        "day_index": day,
        "value_name": VALUE,
        "close": value,
        "event_time_ns": source.event_time_ns,
        "available_at_ns": source.available_at_ns,
        "finalized_at_ns": source.finalized_at_ns,
        "source_record_digest": source.record_digest,
    }


def oracle_window_digest(dataset_digest: str, window: Sequence[tuple[HistoricalPitRecord, int]]) -> str:
    return edge_sha256_text(
        edge_canonical_json(
            {"pit_dataset_digest": dataset_digest, "sources": [oracle_source(r, day) for r, day in window]}
        )
    )


# --- the READY world ------------------------------------------------------------------------------------------------


def test_a_ready_world_binds_every_authority_and_derives_every_close() -> None:
    inputs, evidence = series_inputs(), default_evidence()
    source, policy, pit_dataset = manifest(), default_policy(), default_dataset()
    assert (pit_dataset.status, pit_dataset.gate_verdict, pit_dataset.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (evidence.gate_verdict, evidence.advances, evidence.policy_governed) == (EdgeGateVerdict.PASS, True, True)
    assert (evidence.policy_id, evidence.policy_version, evidence.regime_feature_policy_digest) == (
        policy.policy_id,
        policy.policy_version,
        policy.regime_feature_policy_digest,
    )
    assert (evidence.source_manifest_id, evidence.source_manifest_digest, evidence.source_manifest_gate_verdict) == (
        source.manifest_id,
        source.source_packet_evidence_digest,
        "PASS",
    )
    assert (evidence.pit_dataset_id, evidence.pit_dataset_digest) == (
        pit_dataset.dataset_id,
        pit_dataset.dataset_digest,
    )
    assert evidence.correlation_id == source.correlation_id == pit_dataset.correlation_id
    assert (evidence.as_of_ns, evidence.first_feature_day_index, evidence.last_feature_day_index) == (
        (D0 + 10) * DAY,
        D0 + 3,
        D0 + 10,
    )
    assert (evidence.feature_ids, evidence.claimed_value_count) == ((DD, VOL), 0)
    assert (len(evidence.records), evidence.available_record_count, evidence.unavailable_record_count) == (16, 16, 0)
    by_day = {source_record.event_time_ns // DAY - 1: source_record for source_record in pit_dataset.records}
    # Every consumed close is exactly the authenticated record of its source day; its digest is the accepted one.
    assert [dataclasses.asdict(item) for item in evidence.consumed_sources] == [
        oracle_source(by_day[day], day) for day in range(D0, D0 + 10)
    ]
    for item in evidence.consumed_sources:
        assert item.source_record_digest == historical_pit_record_digest(
            replace(by_day[item.day_index], record_digest="")
        )
    for item in evidence.records:
        first = item.target_day_index - LOOKBACK[item.feature_id]
        window = [(by_day[day], day) for day in range(first, item.target_day_index)]
        assert (item.window_first_day_index, item.window_last_day_index) == (first, item.target_day_index - 1)
        assert item.cutoff_ns == item.target_day_index * DAY
        assert item.feature_class is (F1 if item.feature_id == VOL else F2)
        assert (item.source_series_id, item.instrument_id, item.value_name) == (SERIES, INSTRUMENT, VALUE)
        assert item.formula_policy_id == (
            REGIME_F1_FORMULA_POLICY_ID if item.feature_id == VOL else REGIME_F2_FORMULA_POLICY_ID
        )
        assert (item.numeric_policy_id, item.available, item.unavailable_reason_codes) == (
            REGIME_NUMERIC_POLICY_ID,
            True,
            (),
        )
        assert item.source_record_digests == tuple(source_record.record_digest for source_record, _ in window)
        assert item.inputs_window_digest == oracle_window_digest(pit_dataset.dataset_digest, window)
    assert (evidence.rule_set_digest, evidence.verdict_reason_codes) == (REGIME_FEATURE_SERIES_RULE_SET_DIGEST, ())
    assert inputs.pit_dataset_digest == pit_dataset.dataset_digest


def test_every_feature_value_equals_the_independent_oracle() -> None:
    evidence = default_evidence()
    for item in evidence.records:
        window = window_closes(item.target_day_index, item.feature_id)
        expected = ORACLES[item.feature_id](window)
        assert item.value == expected, (item.feature_id, item.target_day_index)
        assert measure_regime_feature_value(item.feature_class, window) == expected
    assert record(evidence, DD, D0 + 3).value == "0.100000000000000000"  # closes 110 -> 99


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (("100", "110", "99"), "0.141421356237309505"),  # returns +0.1 and -0.1: sample variance 0.02, sqrt(2)/10
        (("100", "100", "100", "100"), "0.000000000000000000"),
        (("100", "110", "121"), "0.000000000000000000"),  # two equal returns
        (("100", "50", "100"), None),
        (("1", "1000000000000000000000000000000000000000", "0.000000000000000001"), None),
        (("97.123456789012345678", "101.5", "99.000000000000000001", "100.25", "98"), None),
    ],
)
def test_f1_is_the_exact_sample_standard_deviation_of_simple_returns(
    closes: tuple[str, ...], expected: str | None
) -> None:
    window = [price(close) for close in closes]
    value = measure_regime_feature_value(F1, window)
    assert value == oracle_f1(window)
    if expected is not None:
        assert value == expected
    if closes == ("100", "110", "99"):
        assert value != "0.100000000000000000"  # the population denominator n would give exactly 0.1


@pytest.mark.parametrize(
    ("closes", "expected"),
    [
        (("100", "101", "102"), "0.000000000000000000"),  # monotone up
        (("100", "120", "90"), "0.250000000000000000"),  # 1 - 90/120
        (("100", "80", "100"), "0.000000000000000000"),  # recovered to the peak
        (("100", "90"), "0.100000000000000000"),  # an exact threshold-sized distance
        (("3", "2"), "0.333333333333333333"),
        (("3", "1"), "0.666666666666666667"),
        (("10000000000000000000", "9999999999999999995"), "0.000000000000000000"),  # exact half unit, even below
        (("10000000000000000000", "9999999999999999985"), "0.000000000000000002"),  # exact half unit, odd below
    ],
)
def test_f2_is_the_exact_peak_distance_rendered_half_even(closes: tuple[str, ...], expected: str) -> None:
    window = [price(close) for close in closes]
    assert measure_regime_feature_value(F2, window) == expected == oracle_f2(window)


def test_a_value_beyond_the_representation_bound_is_unavailable_never_truncated() -> None:
    huge = [
        price("0.000000000000000001"),
        price("10000000000000000000000000000000000000000"),
        price("0.000000000000000001"),
    ]
    assert measure_regime_feature_value(F1, huge) is None


@pytest.mark.parametrize(
    ("feature_class", "closes", "reason"),
    [
        (F1, ["100.000000000000000000", "101.000000000000000000"], "measure_window_too_short"),
        (F2, ["100.000000000000000000"], "measure_window_too_short"),
        (F2, ["100.000000000000000000", "0.000000000000000000"], "measure_close_invalid"),
        (F2, ["100", "90"], "measure_close_invalid"),
        (F2, "100", "measure_closes_malformed"),
        ("F2_DRAWDOWN_STATE", ["100.000000000000000000", "90.000000000000000000"], "measure_feature_class_invalid"),
    ],
)
def test_the_public_measure_refuses_malformed_windows(feature_class: object, closes: object, reason: str) -> None:
    with refused(reason):
        measure_regime_feature_value(feature_class, closes)  # type: ignore[arg-type]


def test_features_never_read_or_set_the_ambient_decimal_context() -> None:
    baseline = default_evidence()
    saved_default = (decimal.DefaultContext.prec, decimal.DefaultContext.rounding)
    with decimal.localcontext() as poisoned:
        poisoned.clear_flags()
        poisoned.prec = 2
        poisoned.rounding = decimal.ROUND_DOWN
        poisoned.Emax = 3
        poisoned.Emin = -3
        for signal in (decimal.Inexact, decimal.Rounded, decimal.Clamped, decimal.Subnormal, decimal.Underflow):
            poisoned.traps[signal] = True
        decimal.DefaultContext.prec, decimal.DefaultContext.rounding = 1, decimal.ROUND_UP
        try:
            assert build(series_inputs()) == baseline
            assert decimal.getcontext().prec == 2
            assert not any(decimal.getcontext().flags.values())
        finally:
            decimal.DefaultContext.prec, decimal.DefaultContext.rounding = saved_default


# --- C/D. the HistoricalPitDataset authority ------------------------------------------------------------------------


def test_the_pit_dataset_is_reproven_anchored_and_advancing() -> None:
    source = default_dataset()
    with refused("pit_dataset_malformed"):
        build(replace(series_inputs(), pit_dataset=None))
    with refused("pit_dataset_digest_invalid"):
        build(series_inputs(pit_dataset_digest="A" * 64))
    other = dataset(dataset_id="rf3-pit-dataset-2")
    assert verify_historical_pit_dataset(other).intact is True
    with refused("pit_dataset_digest_mismatch"):
        build(series_inputs(pit_dataset_digest=other.dataset_digest))
    with refused("pit_dataset_not_intact"):
        build(series_inputs(pit_dataset=replace(source, dataset_id="rf3-pit-dataset-x")))
    forged = reseal_dataset(source, records=source.records[:-1])
    with refused("pit_dataset_not_intact"):
        build(series_inputs(pit_dataset=forged))
    restricted = dataset(rights_status="restricted")
    assert (restricted.status, restricted.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(pit_dataset=restricted))
    foreign_correlation = dataset(correlation_id="corr-2")
    assert foreign_correlation.status is EdgeEvidenceStatus.REJECTED  # the dataset binds its manifest correlation
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(pit_dataset=foreign_correlation))


def test_the_dataset_must_belong_to_the_exact_supplied_ef3_world() -> None:
    other_manifest = ef3t._manifest(manifest_id="manifest-2")
    foreign = dataset(source_manifest=other_manifest)
    assert foreign.advances is True and foreign.source_manifest_digest != manifest().source_packet_evidence_digest
    with refused("pit_dataset_source_manifest_mismatch"):
        build(series_inputs(pit_dataset=foreign))
    with refused("source_manifest_correlation_mismatch"):
        build(series_inputs(correlation_id="corr-rf3-other"))
    # A manifest that fails its own gate cannot back an advancing dataset, so it never feeds RF-3.
    failing = ef3t._manifest(series=(ef3t._series("mark-majors"), ef3t._series(rights_status="restricted")))
    assert failing.gate_verdict is EdgeGateVerdict.FAIL
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(source_manifest=failing))


def test_rf3_binds_the_world_and_correlation_even_if_the_dataset_verifier_were_fooled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defence in depth: RF-3's own status, EF-3 world and correlation checks hold for a dataset a broken verifier
    would pass, so the binding never rests on the dataset's internal invariants alone."""

    def fooled(value: HistoricalPitDataset) -> EdgeEvidenceVerification:
        return EdgeEvidenceVerification(True, (), value.dataset_digest, "")

    monkeypatch.setattr(series_module, "verify_historical_pit_dataset", fooled)
    source = default_dataset()
    foreign_snapshot = replace(source.source_manifest_binding, snapshot_json="{}")
    for changes, reason in (
        ({"correlation_id": "corr-2"}, "pit_dataset_correlation_mismatch"),
        ({"source_manifest_digest": "e" * 64}, "pit_dataset_source_manifest_mismatch"),
        ({"source_manifest_binding": foreign_snapshot}, "pit_dataset_source_manifest_mismatch"),
        ({"status": EdgeEvidenceStatus.REJECTED}, "pit_dataset_not_advancing"),
        ({"gate_verdict": EdgeGateVerdict.FAIL}, "pit_dataset_not_advancing"),
        ({"advances": False}, "pit_dataset_not_advancing"),
    ):
        with refused(reason):
            build(series_inputs(pit_dataset=replace(source, **changes)))  # type: ignore[arg-type]


# --- E/F/G/L. authenticated closes and the retained-digest attacks --------------------------------------------------


def test_rf3_consumes_exactly_the_authenticated_record_value() -> None:
    evidence = default_evidence()
    consumed = {item.day_index: item for item in evidence.consumed_sources}
    for source_record in default_dataset().records:
        day = source_record.event_time_ns // DAY - 1
        (value,) = [item.value for item in source_record.values if item.name == VALUE]
        assert (consumed[day].close, consumed[day].source_record_digest) == (value, source_record.record_digest)
    assert record(evidence, DD, D0 + 3).source_record_digests == tuple(
        source_record.record_digest for source_record in default_dataset().records[1:3]
    )


ATTACKS = {
    "close": {"values": (HistoricalPitValue(VALUE, price("80")),)},
    "event_time": {"event_time_ns": (D0 + 2) * DAY - 1},
    "available_at": {"available_at_ns": (D0 + 2) * DAY + 1},
    "finalized_at": {"finalized_at_ns": (D0 + 2) * DAY + 1},
    "series": {"series_id": "funding-btc-eth"},
    "instrument": {"instrument": "ETH-PERPETUAL"},
}


@pytest.mark.parametrize("field", list(ATTACKS))
def test_a_retained_record_digest_never_authenticates_a_changed_field(field: str) -> None:
    authentic = pit_records()
    tampered = replace(authentic[1], **ATTACKS[field])  # type: ignore[arg-type]
    # The accepted recomputation is the oracle: the retained digest no longer authenticates the record.
    assert historical_pit_record_digest(replace(tampered, record_digest="")) != tampered.record_digest
    rebuilt = dataset((authentic[0], tampered, *authentic[2:]))
    assert rebuilt.status is EdgeEvidenceStatus.REJECTED and rebuilt.advances is False
    assert any(
        item.startswith("historical_pit_dataset:record_digest_mismatch") for item in rebuilt.integrity_reason_codes
    )
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(pit_dataset=rebuilt))
    substituted = reseal_dataset(
        default_dataset(), records=(default_dataset().records[0], tampered, *default_dataset().records[2:])
    )
    assert verify_historical_pit_dataset(substituted).intact is False
    with refused("pit_dataset_not_intact"):
        build(series_inputs(pit_dataset=substituted))


def test_the_former_close_substitution_attack_can_never_move_a_feature() -> None:
    """The audited attack: day D0+1's authenticated close 101 replaced by 80 under its retained record digest."""

    closes = ("100", "101", "99", "103")
    authentic = pit_records(closes)
    honest = decide(series_inputs(records=authentic, last=D0 + 4))
    # 1 - 99/101 over the authenticated closes; the forged 80 would erase the drawdown (1 - 99/99 = 0).
    assert record(honest, DD, D0 + 3).value == "0.019801980198019802" == oracle_f2([price("101"), price("99")])
    forged = replace(authentic[1], values=(HistoricalPitValue(VALUE, price("80")),))
    attacked = dataset((authentic[0], forged, *authentic[2:]))
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(pit_dataset=attacked, last=D0 + 4))
    # A record whose digest is honestly recomputed is a DIFFERENT authenticated dataset: never the anchored one.
    redigested = pit_record(D0 + 1, price("80"))
    honest_other = dataset((authentic[0], redigested, *authentic[2:]))
    with refused("pit_dataset_digest_mismatch"):
        build(series_inputs(pit_dataset=honest_other, pit_dataset_digest=honest.pit_dataset_digest, last=D0 + 4))


def test_no_public_input_route_accepts_a_caller_close_or_source_digest() -> None:
    assert [item.name for item in fields(RegimeFeatureSeriesInputs)] == [
        "feature_series_id",
        "correlation_id",
        "policy",
        "source_manifest",
        "source_manifest_digest",
        "pit_dataset",
        "pit_dataset_digest",
        "as_of_ns",
        "first_feature_day",
        "last_feature_day",
        "claims",
    ]
    unbacked = replace(pit_record(D0 + 1, price("101")), record_digest="ab" * 32)  # an invented digest
    forged = dataset((pit_records()[0], unbacked, *pit_records()[2:]))
    assert forged.status is EdgeEvidenceStatus.REJECTED
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(pit_dataset=forged))
    # A derived close is constructed in exactly one place, from one authenticated record.
    tree = ast.parse(SOURCE)
    builders = {
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RegimeDailyCloseObservation"
    }
    assert builders == {"_daily_close"}
    (daily_close,) = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_daily_close"
    ]
    assert ast.unparse(daily_close.args.args[0].annotation) == "HistoricalPitRecord"  # type: ignore[arg-type]


# --- H/I. daily cardinality and the governed value ------------------------------------------------------------------


def test_exactly_one_visible_record_per_source_day_is_consumed() -> None:
    extra = pit_record(D0 + 5, price("102"), sequence=49, event=(D0 + 5) * DAY + 1)  # a second record inside day D0+5
    evidence = decide(series_inputs(records=(*pit_records(), extra)))
    ambiguous = {(item.feature_id, item.target_day_index) for item in evidence.records if not item.available}
    expected = {
        (feature_id, day)
        for feature_id in (VOL, DD)
        for day in range(D0 + 3, D0 + 11)
        if day - LOOKBACK[feature_id] <= D0 + 5 <= day - 1
    }
    assert ambiguous == expected
    for feature_id, day in ambiguous:
        assert record(evidence, feature_id, day).unavailable_reason_codes == (code(f"window_day_ambiguous:{D0 + 5}"),)
        assert record(evidence, feature_id, day).source_record_digests == ()
    missing = decide(series_inputs(records=pit_records(skip=(D0 + 5,))))
    unavailable = {(item.feature_id, item.target_day_index) for item in missing.records if not item.available}
    assert unavailable == expected == {(VOL, D0 + 6), (VOL, D0 + 7), (VOL, D0 + 8), (DD, D0 + 6), (DD, D0 + 7)}
    for feature_id, day in unavailable:
        assert record(missing, feature_id, day).unavailable_reason_codes == (
            code(f"window_day_not_visible_at_cutoff:{D0 + 5}"),
        )
    assert missing.gate_verdict is EdgeGateVerdict.PASS  # unavailable days are recorded, never a failure


@pytest.mark.parametrize(
    ("values", "reason"),
    [
        ((HistoricalPitValue("open", price("101")),), "window_day_value_missing"),
        ((HistoricalPitValue(VALUE, price("0")),), "window_day_close_not_positive"),
        ((HistoricalPitValue(VALUE, price("-5")),), "window_day_close_not_positive"),
    ],
)
def test_only_a_positive_governed_value_is_ever_the_close(values: tuple[HistoricalPitValue, ...], reason: str) -> None:
    records = list(pit_records())
    records[5] = pit_record(D0 + 5, values=values)
    evidence = decide(series_inputs(records=records))
    assert record(evidence, DD, D0 + 6).unavailable_reason_codes == (code(f"{reason}:{D0 + 5}"),)
    assert record(evidence, DD, D0 + 5).available is True  # its window ends on day D0+4


def test_other_values_of_the_same_record_never_substitute_for_the_governed_one() -> None:
    records = list(pit_records())
    for day, opening in ((D0 + 4, "2"), (D0 + 5, "1")):  # only days D0+4 and D0+5 also carry an "open" value
        records[day - D0] = pit_record(
            day, values=(HistoricalPitValue(VALUE, price(CLOSES[day - D0])), HistoricalPitValue("open", price(opening)))
        )
    evidence = decide(series_inputs(records=records))
    assert [item.value for item in evidence.records] == [item.value for item in default_evidence().records]
    open_policy = rf2t.governed(features=[rf2t.feature(VOL, F1), rf2t.feature(DD, F2, lookback=2, value_name="open")])
    reads_open = decide(series_inputs(policy=open_policy, records=records))
    assert record(reads_open, DD, D0 + 6).value == oracle_f2([price("2"), price("1")]) == "0.500000000000000000"
    assert record(reads_open, DD, D0 + 5).unavailable_reason_codes == (code(f"window_day_value_missing:{D0 + 3}"),)
    assert record(reads_open, DD, D0 + 7).unavailable_reason_codes == (code(f"window_day_value_missing:{D0 + 6}"),)
    assert [item for item in reads_open.records if item.feature_id == VOL] == [
        item for item in evidence.records if item.feature_id == VOL
    ]  # the feature that governs "close" still reads only "close"


# --- E/J. the prior-day cutoff and revision vintages ----------------------------------------------------------------


def extended(*changes: HistoricalPitRecord) -> RegimeFeatureSeriesInputs:
    """Eleven closes (D0 .. D0+10), features through D0+11; ``changes`` replace the record of their day."""

    records = {source_record.event_time_ns // DAY - 1: source_record for source_record in pit_records((*CLOSES, "92"))}
    for change in changes:
        records[change.event_time_ns // DAY - 1] = change
    return series_inputs(records=tuple(records.values()), last=D0 + 11)


def test_a_close_final_exactly_at_the_start_of_the_feature_day_counts() -> None:
    evidence = decide(extended())  # every default record is available and finalized exactly at the next day's start
    assert record(evidence, VOL, D0 + 10).available is True
    assert record(evidence, DD, D0 + 10).value == oracle_f2([price("97"), price("90")])


@pytest.mark.parametrize("late", ["available", "finalized"])
def test_one_nanosecond_after_the_cutoff_feeds_only_later_feature_days(late: str) -> None:
    boundary = (D0 + 10) * DAY
    times = {"available": boundary, "finalized": boundary, late: boundary + 1}
    evidence = decide(extended(pit_record(D0 + 9, price("90"), **times)))  # type: ignore[arg-type]
    for feature_id in (VOL, DD):
        missing = record(evidence, feature_id, D0 + 10)
        assert (missing.available, missing.value, missing.inputs_window_digest) == (False, None, None)
        assert missing.unavailable_reason_codes == (code(f"window_day_not_visible_at_cutoff:{D0 + 9}"),)
        later = record(evidence, feature_id, D0 + 11)
        assert later.available is True
        assert later.value == ORACLES[feature_id](window_closes(D0 + 11, feature_id, (*CLOSES, "92")))


def test_the_feature_day_and_later_closes_are_never_read() -> None:
    base_inputs, changed_inputs = extended(), extended(pit_record(D0 + 10, price("500")))
    base, changed = decide(base_inputs), decide(changed_inputs)
    by_day = {
        source_record.event_time_ns // DAY - 1: source_record for source_record in changed_inputs.pit_dataset.records
    }
    for feature_id in (VOL, DD):
        before, after = record(base, feature_id, D0 + 10), record(changed, feature_id, D0 + 10)
        # The value and every consumed record are unchanged; only the dataset identity the window digest binds moved.
        assert replace(after, inputs_window_digest=None) == replace(before, inputs_window_digest=None)
        window = [(by_day[day], day) for day in range(D0 + 10 - LOOKBACK[feature_id], D0 + 10)]
        assert after.inputs_window_digest == oracle_window_digest(changed_inputs.pit_dataset_digest, window)
        assert record(changed, feature_id, D0 + 11).source_record_digests[-1] == by_day[D0 + 10].record_digest
        assert record(base, feature_id, D0 + 11).source_record_digests[-1] != by_day[D0 + 10].record_digest


@functools.cache
def vintage_manifest() -> EdgeSourcePacketEvidence:
    return ef3t._manifest(
        series=(ef3t._series("mark-majors", revision_policy="revised_with_point_in_time_vintages"), ef3t._series())
    )


def test_a_later_revision_vintage_never_alters_an_earlier_feature_day() -> None:
    source = vintage_manifest()
    assert source.advances is True
    first = pit_record(D0 + 8, price("97"), vintage="v1")
    revised = pit_record(
        D0 + 8, price("80"), vintage="v2", available=(D0 + 9) * DAY + 6, finalized=(D0 + 9) * DAY + 6
    )  # published six nanoseconds after day D0+8 closed
    records = [*pit_records()[:8], first, revised, pit_records()[9]]
    evidence = decide(series_inputs(source_manifest=source, records=records, policy=default_policy()))
    assert record(evidence, DD, D0 + 9).value == oracle_f2([price("96"), price("97")])  # v1 is the visible vintage
    assert record(evidence, DD, D0 + 10).value == oracle_f2([price("80"), price("90")])  # v2 is visible by then
    assert record(evidence, DD, D0 + 9).source_record_digests[-1] == first.record_digest
    assert record(evidence, DD, D0 + 10).source_record_digests[0] == revised.record_digest


# --- B. EF-3 source binding -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("features", "reason"),
    [
        (
            [rf2t.feature(rf2t.VOL, F1, series="index-btc"), rf2t.feature(rf2t.DD, F2, lookback=2)],
            "source_series_not_in_manifest:index-btc",
        ),
        (
            [rf2t.feature(rf2t.VOL, F1, series="funding-btc-eth"), rf2t.feature(rf2t.DD, F2, lookback=2)],
            "source_series_not_a_price_series:funding-btc-eth",
        ),
        (
            [rf2t.feature(rf2t.VOL, F1, instrument="XRP-PERPETUAL"), rf2t.feature(rf2t.DD, F2, lookback=2)],
            "source_series_instrument_not_covered:mark-majors:XRP-PERPETUAL",
        ),
    ],
)
def test_every_feature_names_a_covered_price_series_of_the_manifest(features: list[object], reason: str) -> None:
    with refused(reason):
        build(series_inputs(policy=rf2t.governed(features=features)))


@pytest.mark.parametrize(
    "series_changes",
    [
        {"finality": "includes_unfinalized"},
        {"revision_policy": "revised_without_vintages"},
        {"rights_status": "restricted"},
    ],
)
def test_an_ineligible_source_series_can_never_feed_an_advancing_dataset(series_changes: dict[str, object]) -> None:
    source = ef3t._manifest(series=(ef3t._series("mark-majors", **series_changes), ef3t._series()))
    assert SERIES not in source.feature_input_series_ids and source.advances is False
    with refused("pit_dataset_not_advancing"):
        build(series_inputs(source_manifest=source))


def test_the_manifest_is_reproven_anchored_and_ready() -> None:
    source = manifest()
    other = ef3t._manifest(manifest_id="manifest-2")
    with refused("source_manifest_digest_mismatch"):
        build(series_inputs(source_manifest_digest=other.source_packet_evidence_digest))
    with refused("source_manifest_not_intact"):
        build(series_inputs(source_manifest=replace(source, manifest_id="manifest-x"), pit_dataset=default_dataset()))
    rejected = ef3t._manifest(correlation_id="corr-2")
    with refused("source_manifest_rejected"):
        build(series_inputs(source_manifest=rejected, pit_dataset=default_dataset()))
    with refused("source_manifest_digest_invalid"):
        build(series_inputs(source_manifest_digest="A" * 64))


# --- claims, inputs and governance ----------------------------------------------------------------------------------


def test_matching_claims_are_recomputed_and_counted() -> None:
    evidence = default_evidence()
    claims = (
        RegimeFeatureClaim(DD, D0 + 3, "0.100000000000000000"),
        RegimeFeatureClaim(VOL, D0 + 10, record(evidence, VOL, D0 + 10).value),
    )
    claimed = decide(series_inputs(claims=claims))
    assert claimed.claimed_value_count == 2
    assert claimed.records == evidence.records
    missing = decide(
        series_inputs(records=pit_records(skip=(D0 + 9,)), claims=(RegimeFeatureClaim(DD, D0 + 10, None),))
    )
    assert record(missing, DD, D0 + 10).available is False


@pytest.mark.parametrize(
    ("claim", "reason"),
    [
        (RegimeFeatureClaim(DD, D0 + 3, "0.100000000000000001"), f"feature_recompute_mismatch:{rf2t.DD}:{D0 + 3}"),
        (RegimeFeatureClaim(DD, D0 + 3, None), f"feature_recompute_mismatch:{rf2t.DD}:{D0 + 3}"),
        (RegimeFeatureClaim(DD, D0 + 11, "0.100000000000000000"), "claim_outside_the_evidence"),
        (RegimeFeatureClaim("vol-other", D0 + 3, "0.100000000000000000"), "claim_outside_the_evidence"),
        (RegimeFeatureClaim(DD, D0 + 3, "0.1"), "claim_value_invalid"),
        (RegimeFeatureClaim(DD, "day", "0.100000000000000000"), "claim_day_index_invalid"),  # type: ignore[arg-type]
        ("claim", "claim_malformed"),
    ],
)
def test_a_claim_that_is_not_the_recomputation_fails_closed(claim: object, reason: str) -> None:
    with refused(reason):
        build(series_inputs(claims=(claim,)))
    with refused("claim_duplicate"):
        build(series_inputs(claims=(RegimeFeatureClaim(DD, D0 + 3, "0.100000000000000000"),) * 2))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"feature_series_id": ""}, "feature_series_id_invalid"),
        ({"correlation_id": "corr live"}, "forbidden_scope_token:correlation_id"),
        ({"policy": None}, "policy_malformed"),
        ({"source_manifest": None}, "source_manifest_malformed"),
        ({"pit_dataset_digest": None}, "pit_dataset_digest_invalid"),
        ({"as_of_ns": (D0 + 10) * DAY + 1}, "as_of_ns_not_utc_day_aligned"),
        ({"as_of_ns": True}, "as_of_ns_invalid"),
        ({"first_feature_day": D0 + 11}, "feature_window_empty"),
        ({"last_feature_day": D0 + 11}, "feature_window_after_as_of"),
        ({"first_feature_day": 2}, "feature_window_reaches_before_day_zero"),
        ({"first_feature_day": -1}, "first_feature_day_invalid"),
        ({"claims": None}, "claims_malformed"),
    ],
)
def test_malformed_inputs_are_refused(overrides: dict[str, object], reason: str) -> None:
    with refused(reason):
        build(replace(series_inputs(), **overrides))
    with refused("inputs_malformed"):
        build(None)


def test_a_policy_without_human_governance_never_advances() -> None:
    draft = rf2t.build()
    evidence = decide(series_inputs(policy=draft))
    assert (evidence.gate_verdict, evidence.advances, evidence.policy_governed) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        False,
    )
    assert evidence.verdict_reason_codes == (code("policy_needs_governance_approval"),)
    assert evidence.records == default_evidence().records  # governance gates advancement, never the arithmetic
    with refused("policy_not_intact"):
        build(series_inputs(policy=replace(default_policy(), distribution_drift_cap=rf2t.d("0.9"))))


# --- the verifier ---------------------------------------------------------------------------------------------------


def test_every_field_is_digest_bound_and_reproven() -> None:
    inputs, evidence = series_inputs(), default_evidence()
    changed_record = replace(evidence.records[0], value="0.200000000000000000")
    forged = reseal(evidence, records=(changed_record, *evidence.records[1:]))
    assert verify_regime_feature_series_evidence(forged, inputs).reason_codes == (
        code("field_mismatch:feature_series_digest"),
        code("field_mismatch:records"),
    )
    for changes in (
        {"pit_dataset_digest": "e" * 64},
        {
            "consumed_sources": (
                replace(evidence.consumed_sources[0], close=price("80")),
                *evidence.consumed_sources[1:],
            )
        },
        {
            "consumed_sources": (
                replace(evidence.consumed_sources[0], source_record_digest="e" * 64),
                *evidence.consumed_sources[1:],
            )
        },
        {"records": (replace(evidence.records[0], source_record_digests=("e" * 64, "f" * 64)), *evidence.records[1:])},
        {"records": (replace(evidence.records[0], inputs_window_digest="e" * 64), *evidence.records[1:])},
    ):
        name = next(iter(changes))
        assert set(verify_regime_feature_series_evidence(reseal(evidence, **changes), inputs).reason_codes) == {
            code(f"field_mismatch:{name}"),
            code("field_mismatch:feature_series_digest"),
        }
    stale = verify_regime_feature_series_evidence(replace(evidence, advances=False), inputs)
    assert stale.reason_codes == (code("field_mismatch:advances"), code("self_digest_mismatch"))
    for name, _ in REGIME_NON_CLAIM_FLAGS:
        flipped = reseal(evidence, **{name: not getattr(evidence, name)})
        assert set(verify_regime_feature_series_evidence(flipped, inputs).reason_codes) == {
            code(f"field_mismatch:{name}"),
            code("field_mismatch:feature_series_digest"),
        }


def test_the_verifier_is_total() -> None:
    inputs, evidence = series_inputs(), default_evidence()
    for value in (
        None,
        {},
        "evidence",
        evidence.records[0],
        replace(evidence, gate_verdict="PASS"),
        replace(evidence, as_of_ns=-1),
        replace(evidence, records=list(evidence.records)),
        replace(evidence, consumed_sources=list(evidence.consumed_sources)),
    ):
        verification = verify_regime_feature_series_evidence(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in ((code("evidence_type_invalid"),), (code("evidence_serialization_failed"),))
    for broken in (None, replace(inputs, claims=(RegimeFeatureClaim(DD, D0 + 3, None),))):
        verification = verify_regime_feature_series_evidence(evidence, broken)  # type: ignore[arg-type]
        assert verification.reason_codes == (code("evidence_reconstruction_failed"),)


# --- static discipline, rule set and API ----------------------------------------------------------------------------


def test_the_module_is_pure_confines_decimal_to_one_explicit_context_and_never_imports_runtime_regime() -> None:
    tree = ast.parse(SOURCE)
    forbidden_modules = tuple(module for module in pit.FORBIDDEN_MODULES if module != "decimal")
    crypto_imports: set[str] = set()
    decimal_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
                assert not alias.name.startswith("crypto_core")
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in forbidden_modules)
            if node.module.startswith("crypto_core"):
                crypto_imports.add(node.module)
                assert not {alias.name for alias in node.names if alias.name.startswith("_")}
            if node.module == "decimal":
                decimal_names |= {alias.name for alias in node.names}
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
            assert not (isinstance(node.func, ast.Name) and name in pit.FORBIDDEN_BUILTINS), name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "__globals__", "__code__"}
    assert crypto_imports == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_source_packet_evidence",
        "crypto_core.validation.historical_pit_dataset",
        "crypto_core.validation.regime_feature_policy",
    }
    assert decimal_names == {"Context", "Decimal", "DivisionByZero", "InvalidOperation", "Overflow"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"getcontext", "setcontext", "localcontext", "DefaultContext", "BasicContext", "ExtendedContext"}
    assert not [token for token in pit.FORBIDDEN_IDENTIFIERS if token in SOURCE.lower()]
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE


def test_the_cutoff_reads_only_days_before_the_feature_day_through_the_accepted_view() -> None:
    tree = ast.parse(SOURCE)
    functions = {node.name: ast.unparse(node) for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)}
    assert "first, last = (day - feature.lookback_days, day - 1)" in functions["_feature_record"]
    assert "cutoff = day * _DAY_NS" in functions["_feature_record"]
    assert "start < record.event_time_ns <= end" in functions["_feature_record"]
    assert "decision_time_ns=cutoff" in functions["_visible_records"]
    assert "select_visible_pit_records(" in functions["_visible_records"]


def test_execution_capital_and_scheduler_names_are_only_structural_false_flags() -> None:
    flags = dict(REGIME_NON_CLAIM_FLAGS)
    names = {node.id for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Attribute)}
    risky = {
        name
        for name in names
        if re.search(r"(^|_)(live|orders?|capital|scheduler|connector|shadow|execution)(_|$)", name)
    }
    assert risky <= set(flags)
    assert {item.name: item.default for item in fields(RegimeFeatureSeriesEvidence) if item.name in flags} == flags
    assert all(
        item.default is dataclasses.MISSING for item in fields(RegimeFeatureSeriesEvidence) if item.name not in flags
    )
    assert flags["external_market_truth_proven"] is False  # record authentication is internal provenance only
    for record_type in (RegimeDailyCloseObservation, RegimeFeatureClaim, RegimeFeatureSeriesInputs):
        assert all(item.default is dataclasses.MISSING for item in fields(record_type))


def test_the_rule_set_commits_the_controller_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_feature_series_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_FEATURE_SERIES_RULE_SET_DIGEST
    assert (rule_set["cutoff_boundary"], rule_set["numeric_policy_id"]) == (
        "INCLUSIVE_AT_START_OF_FEATURE_DAY",
        REGIME_NUMERIC_POLICY_ID,
    )
    assert (rule_set["f1_formula_policy_id"], rule_set["f2_formula_policy_id"]) == (
        REGIME_F1_FORMULA_POLICY_ID,
        REGIME_F2_FORMULA_POLICY_ID,
    )
    assert (rule_set["decimal_internal_precision"], rule_set["decimal_rounding"], rule_set["utc_day_ns"]) == (
        80,
        "ROUND_HALF_EVEN",
        DAY,
    )
    assert "historical_pit_dataset" in str(rule_set["dataset_rule_id"])
    assert "exactly_one_visible_record" in str(rule_set["daily_close_rule_id"])
    rule_set["cutoff_boundary"] = "EXCLUSIVE"
    assert regime_feature_series_rule_set()["cutoff_boundary"] == "INCLUSIVE_AT_START_OF_FEATURE_DAY"


def test_the_public_api_is_exact() -> None:
    assert set(series_module.__all__) == {
        "REGIME_FEATURE_SERIES_NON_CLAIM_FLAGS",
        "REGIME_FEATURE_SERIES_RULE_SET_DIGEST",
        "RegimeDailyCloseObservation",
        "RegimeFeatureClaim",
        "RegimeFeatureRecord",
        "RegimeFeatureSeriesError",
        "RegimeFeatureSeriesEvidence",
        "RegimeFeatureSeriesInputs",
        "build_regime_feature_series_evidence",
        "measure_regime_feature_value",
        "regime_feature_series_evidence_digest",
        "regime_feature_series_evidence_to_dict",
        "regime_feature_series_rule_set",
        "verify_regime_feature_series_evidence",
    }
