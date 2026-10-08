"""Tests for the RF-3 regime feature series evidence (``regime_feature_series_evidence``).

Fixtures: the authentic EF-2 -> EF-3 manifest of the EF-3 test module (an eligible ``mark-majors`` mark-price series
covering ``BTC-PERPETUAL``) and the RF-2 test module's governed synthetic policy (F1 over 3 closes, F2 over 2 closes).
Every close, coordinate, threshold and approval is a SYNTHETIC TEST VALUE. Every expected feature value is recomputed
here by an independent exact oracle: integer square roots and plain ``Fraction`` arithmetic, never the module.
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
from crypto_core.data.requirements import DataAvailabilityMode
from crypto_core.validation.edge_artifact_core import EdgeGateVerdict, edge_canonical_json, edge_sha256_text
from crypto_core.validation.edge_source_packet_evidence import EdgeSourcePacketEvidence
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
    regime_daily_close_observation_digest,
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
D0 = 20_000  # SYNTHETIC first observation day
F1, F2 = RegimeFeatureClass.F1_REALIZED_VOL, RegimeFeatureClass.F2_DRAWDOWN_STATE
SERIES, INSTRUMENT, VOL, DD = rf2t.SERIES, rf2t.INSTRUMENT, rf2t.VOL, rf2t.DD
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


def observation(
    day: int,
    close: str,
    *,
    series: str = SERIES,
    instrument: str = INSTRUMENT,
    event: int | None = None,
    available: int | None = None,
    finalized: int | None = None,
    source: str = "a" * 64,
) -> RegimeDailyCloseObservation:
    """A close of ``day`` whose instant, availability and finality default to the end of its day."""

    end = (day + 1) * DAY
    return RegimeDailyCloseObservation(
        series_id=series,
        instrument_id=instrument,
        day_index=day,
        close=close,
        event_time_ns=end if event is None else event,
        available_at_ns=end if available is None else available,
        finalized_at_ns=end if finalized is None else finalized,
        source_digest=source,
    )


def world(closes: Sequence[str] = CLOSES, start: int = D0) -> tuple[RegimeDailyCloseObservation, ...]:
    return tuple(observation(start + index, price(close)) for index, close in enumerate(closes))


@functools.cache
def manifest() -> EdgeSourcePacketEvidence:
    return ef3t._manifest()


@functools.cache
def default_policy() -> RegimeFeaturePolicy:
    return rf2t.governed()


def series_inputs(
    *,
    policy: RegimeFeaturePolicy | None = None,
    observations: Sequence[RegimeDailyCloseObservation] | None = None,
    source_manifest: EdgeSourcePacketEvidence | None = None,
    last: int = D0 + len(CLOSES),
    as_of_day: int | None = None,
    **overrides: object,
) -> RegimeFeatureSeriesInputs:
    """The default world: features for days D0+3 .. D0+10, as of the start of the last feature day."""

    source = manifest() if source_manifest is None else source_manifest
    values: dict[str, object] = {
        "feature_series_id": "rf3-synthetic-1",
        "correlation_id": "corr-rf3",
        "policy": default_policy() if policy is None else policy,
        "source_manifest": source,
        "source_manifest_digest": source.source_packet_evidence_digest,
        "as_of_ns": (last if as_of_day is None else as_of_day) * DAY,
        "first_feature_day": D0 + 3,
        "last_feature_day": last,
        "observations": world() if observations is None else tuple(observations),
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


# --- the READY world ------------------------------------------------------------------------------------------------


def test_a_ready_world_binds_every_input_and_computes_every_feature_day() -> None:
    inputs, evidence = series_inputs(), default_evidence()
    source, policy = manifest(), default_policy()
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
    assert (evidence.as_of_ns, evidence.first_feature_day_index, evidence.last_feature_day_index) == (
        (D0 + 10) * DAY,
        D0 + 3,
        D0 + 10,
    )
    assert (evidence.feature_ids, evidence.observation_count, evidence.claimed_value_count) == ((DD, VOL), 10, 0)
    assert (len(evidence.records), evidence.available_record_count, evidence.unavailable_record_count) == (16, 16, 0)
    assert [(item.feature_id, item.target_day_index) for item in evidence.records] == [
        (feature_id, day) for feature_id in (DD, VOL) for day in range(D0 + 3, D0 + 11)
    ]
    observation_digests = [regime_daily_close_observation_digest(item) for item in inputs.observations]
    assert evidence.observations_digest == edge_sha256_text(edge_canonical_json(observation_digests))
    for item in evidence.records:
        first = item.target_day_index - LOOKBACK[item.feature_id]
        assert (item.window_first_day_index, item.window_last_day_index) == (first, item.target_day_index - 1)
        assert item.cutoff_ns == item.target_day_index * DAY
        assert item.feature_class is (F1 if item.feature_id == VOL else F2)
        assert (item.source_series_id, item.instrument_id) == (SERIES, INSTRUMENT)
        assert item.formula_policy_id == (
            REGIME_F1_FORMULA_POLICY_ID if item.feature_id == VOL else REGIME_F2_FORMULA_POLICY_ID
        )
        assert (item.numeric_policy_id, item.available, item.unavailable_reason_codes) == (
            REGIME_NUMERIC_POLICY_ID,
            True,
            (),
        )
        window = observation_digests[first - D0 : item.target_day_index - D0]
        assert item.inputs_window_digest == edge_sha256_text(edge_canonical_json(window))
    assert (evidence.rule_set_digest, evidence.verdict_reason_codes) == (REGIME_FEATURE_SERIES_RULE_SET_DIGEST, ())


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


# --- E. the prior-day cutoff (P1) -----------------------------------------------------------------------------------


def extended(**changes: object) -> RegimeFeatureSeriesInputs:
    """Eleven closes (D0 .. D0+10), features through D0+11, one day changed by ``changes`` (keyed by day offset)."""

    observations = list(world((*CLOSES, "92")))
    for offset, replacement in changes.items():
        observations[int(offset.removeprefix("day"))] = replacement  # type: ignore[assignment]
    return series_inputs(observations=observations, last=D0 + 11)


def test_a_close_final_exactly_at_the_start_of_the_feature_day_counts() -> None:
    boundary = (D0 + 10) * DAY
    evidence = decide(extended(day9=observation(D0 + 9, price("90"), available=boundary, finalized=boundary)))
    assert record(evidence, VOL, D0 + 10).available is True
    assert record(evidence, DD, D0 + 10).value == oracle_f2([price("97"), price("90")])


@pytest.mark.parametrize("late", ["available", "finalized"])
def test_one_nanosecond_after_the_cutoff_feeds_only_later_feature_days(late: str) -> None:
    boundary = (D0 + 10) * DAY
    times = {"available": boundary, "finalized": boundary, late: boundary + 1}
    evidence = decide(extended(day9=observation(D0 + 9, price("90"), **times)))  # type: ignore[arg-type]
    for feature_id in (VOL, DD):
        missing = record(evidence, feature_id, D0 + 10)
        assert (missing.available, missing.value, missing.inputs_window_digest) == (False, None, None)
        assert missing.unavailable_reason_codes == (code(f"window_day_not_final_by_cutoff:{D0 + 9}"),)
        later = record(evidence, feature_id, D0 + 11)
        assert later.available is True
        assert later.value == ORACLES[feature_id](window_closes(D0 + 11, feature_id, (*CLOSES, "92")))


def test_the_feature_day_and_later_closes_are_never_read() -> None:
    base = decide(extended())
    changed = decide(extended(day10=observation(D0 + 10, price("500"))))
    for feature_id in (VOL, DD):
        assert record(changed, feature_id, D0 + 10) == record(base, feature_id, D0 + 10)
        assert record(changed, feature_id, D0 + 11) != record(base, feature_id, D0 + 11)
    # Day D0+11 has no close at all: its absence never touches D0+11 itself.
    assert record(base, VOL, D0 + 11).available is True


def test_a_missing_day_is_never_filled() -> None:
    observations = [item for item in world() if item.day_index != D0 + 5]
    evidence = decide(series_inputs(observations=observations))
    unavailable = {(item.feature_id, item.target_day_index) for item in evidence.records if not item.available}
    expected = {
        (feature_id, day)
        for feature_id in (VOL, DD)
        for day in range(D0 + 3, D0 + 11)
        if day - LOOKBACK[feature_id] <= D0 + 5 <= day - 1
    }
    assert unavailable == expected == {(VOL, D0 + 6), (VOL, D0 + 7), (VOL, D0 + 8), (DD, D0 + 6), (DD, D0 + 7)}
    for feature_id, day in unavailable:
        assert record(evidence, feature_id, day).unavailable_reason_codes == (code(f"window_day_missing:{D0 + 5}"),)
    assert (evidence.available_record_count, evidence.unavailable_record_count) == (11, 5)
    assert evidence.gate_verdict is EdgeGateVerdict.PASS  # unavailable days are recorded, never a failure


# --- observations ---------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("replacement", "reason"),
    [
        (observation(D0 + 4, price("0")), "observation_close_not_positive"),
        (observation(D0 + 4, price("-1")), "observation_close_not_positive"),
        (observation(D0 + 4, "100"), "observation_close_invalid"),
        (observation(D0 + 4, price("100"), event=(D0 + 4) * DAY), "observation_close_instant_outside_its_day"),
        (observation(D0 + 4, price("100"), event=(D0 + 5) * DAY + 1), "observation_close_instant_outside_its_day"),
        (
            observation(D0 + 4, price("100"), event=(D0 + 5) * DAY - 9, available=(D0 + 5) * DAY - 10),
            "observation_available_before_its_close",
        ),
        (
            observation(D0 + 4, price("100"), event=(D0 + 5) * DAY - 9, finalized=(D0 + 5) * DAY - 10),
            "observation_finalized_before_its_close",
        ),
        (observation(D0 + 4, price("100"), finalized=(D0 + 10) * DAY + 1), "observation_after_as_of"),
        (observation(D0 + 4, price("100"), available=(D0 + 10) * DAY + 1), "observation_after_as_of"),
        (observation(D0 + 4, price("100"), instrument="ETH-PERPETUAL"), "observation_not_bound_to_a_policy_feature"),
        (observation(D0 + 4, price("100"), series="index-btc"), "observation_not_bound_to_a_policy_feature"),
        (observation(D0 + 3, price("100")), "observation_duplicate_day"),
        (observation(D0 + 4, price("100"), source="A" * 64), "observation_source_digest_invalid"),
        (observation(-1, price("100")), "observation_day_index_invalid"),
        (observation(D0 + 4, price("100"), event=True), "observation_event_time_ns_invalid"),  # type: ignore[arg-type]
        ("close", "observation_malformed"),
    ],
)
def test_every_observation_is_validated_once(replacement: object, reason: str) -> None:
    observations = list(world())
    observations[4] = replacement  # type: ignore[call-overload]
    with refused(reason):
        build(series_inputs(observations=observations))


def test_an_early_close_instant_inside_its_day_is_accepted_and_still_cut_by_finality() -> None:
    early = observation(
        D0 + 9, price("90"), event=(D0 + 9) * DAY + 1, available=(D0 + 9) * DAY + 1, finalized=(D0 + 9) * DAY + 1
    )
    evidence = decide(series_inputs(observations=[*world()[:9], early]))
    assert record(evidence, DD, D0 + 10).value == oracle_f2([price("97"), price("90")])


# --- B. EF-3 source binding -----------------------------------------------------------------------------------------


def test_a_manifest_that_fails_its_candidate_gate_still_serves_its_eligible_series() -> None:
    failing = ef3t._manifest(series=(ef3t._series("mark-majors"), ef3t._series(rights_status="restricted")))
    assert failing.gate_verdict is EdgeGateVerdict.FAIL
    evidence = decide(series_inputs(source_manifest=failing))
    assert (evidence.source_manifest_gate_verdict, evidence.advances) == ("FAIL", True)


@pytest.mark.parametrize(
    ("series_changes", "registry_changes", "reason"),
    [
        ({"finality": "includes_unfinalized"}, None, "source_series_not_finalized_only:mark-majors"),
        ({"finality": "unknown"}, None, "source_series_not_finalized_only:mark-majors"),
        (
            {"revision_policy": "revised_without_vintages"},
            None,
            "source_series_not_point_in_time_revision_safe:mark-majors",
        ),
        ({"revision_policy": "unknown"}, None, "source_series_not_point_in_time_revision_safe:mark-majors"),
        ({"rights_status": "restricted"}, None, "source_series_rights_not_usable:mark-majors"),
        (
            {},
            {"availability_mode": DataAvailabilityMode.HISTORICAL_ONLY},
            "source_series_not_feature_input_eligible:mark-majors",
        ),
        ({}, {"finality_policy": None}, "source_series_not_finalized_only:mark-majors"),
    ],
)
def test_only_finalized_pit_safe_usable_eligible_series_serve(
    series_changes: dict[str, object], registry_changes: dict[str, object] | None, reason: str
) -> None:
    registry = ef3t._registry({"mark_price": registry_changes} if registry_changes else None)
    source = ef3t._manifest(registry=registry, series=(ef3t._series("mark-majors", **series_changes), ef3t._series()))
    record_ = next(item for item in source.series if item.series_id == SERIES)
    assert record_.feature_input_eligible is False and SERIES not in source.feature_input_series_ids
    with refused(reason):
        build(series_inputs(source_manifest=source))


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


def test_the_manifest_is_reproven_anchored_and_ready() -> None:
    source = manifest()
    other = ef3t._manifest(manifest_id="manifest-2")
    with refused("source_manifest_digest_mismatch"):
        build(series_inputs(source_manifest_digest=other.source_packet_evidence_digest))
    with refused("source_manifest_not_intact"):
        build(series_inputs(source_manifest=replace(source, manifest_id="manifest-x")))
    forged = ef3t._redigest(replace(source, feature_input_series_ids=(SERIES,)))
    with refused("source_manifest_not_intact"):
        build(series_inputs(source_manifest=forged, source_manifest_digest=forged.source_packet_evidence_digest))
    rejected = ef3t._manifest(correlation_id="corr-2")
    with refused("source_manifest_rejected"):
        build(series_inputs(source_manifest=rejected))
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
    missing = decide(series_inputs(observations=world()[:9], claims=(RegimeFeatureClaim(DD, D0 + 10, None),)))
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
        ({"as_of_ns": (D0 + 10) * DAY + 1}, "as_of_ns_not_utc_day_aligned"),
        ({"as_of_ns": True}, "as_of_ns_invalid"),
        ({"first_feature_day": D0 + 11}, "feature_window_empty"),
        ({"last_feature_day": D0 + 11}, "feature_window_after_as_of"),
        ({"first_feature_day": 2, "observations": ()}, "feature_window_reaches_before_day_zero"),
        ({"first_feature_day": -1}, "first_feature_day_invalid"),
        ({"observations": None}, "observations_malformed"),
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
        "crypto_core.validation.regime_feature_policy",
    }
    assert decimal_names == {"Context", "Decimal", "DivisionByZero", "InvalidOperation", "Overflow"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"getcontext", "setcontext", "localcontext", "DefaultContext", "BasicContext", "ExtendedContext"}
    assert not [token for token in pit.FORBIDDEN_IDENTIFIERS if token in SOURCE.lower()]
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE


def test_the_cutoff_reads_only_days_before_the_feature_day_on_the_inclusive_boundary() -> None:
    tree = ast.parse(SOURCE)
    (function,) = [
        node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "_feature_record"
    ]
    source = ast.unparse(function)
    assert "first, last = (day - feature.lookback_days, day - 1)" in source
    assert "cutoff = day * _DAY_NS" in source
    assert "observation.available_at_ns > cutoff or observation.finalized_at_ns > cutoff" in source


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
        "regime_daily_close_observation_digest",
        "regime_feature_series_evidence_digest",
        "regime_feature_series_evidence_to_dict",
        "regime_feature_series_rule_set",
        "verify_regime_feature_series_evidence",
    }
