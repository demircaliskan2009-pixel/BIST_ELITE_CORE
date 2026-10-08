"""RF-3 deterministic point-in-time regime feature series evidence (RF3_REGIME_FEATURE_SERIES_EVIDENCE_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-3), under the controller
structural authority ``RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1`` (closure
``RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1``).

For one exact RF-2 policy, RF-3 computes every policy feature for every UTC day of a declared feature window. It does
so from supplied, digest-bound daily close observations, as of one UTC-day-aligned coordinate. It proves a
deterministic transformation of authenticated inputs, never external market truth.

Source authority. The exact EF-3 ``EdgeSourcePacketEvidence`` is re-proven through
``verify_edge_source_packet_evidence``. It must be intact, ``READY`` and equal to the caller's digest anchor; a
manifest that fails its own candidate-level gate still serves, because RF-3 reads only per-series eligibility. Every
feature's source series must, in the authenticated manifest:
* exist;
* be ``finalized_only`` and ``point_in_time_revision_safe``;
* be ``rights_usable``;
* be ``feature_input_eligible`` and listed in ``feature_input_series_ids``;
* be a price series (``price_semantics`` present);
* cover the feature's instrument.

Any failure raises.

Observations. Exactly one per (series, instrument, UTC day). Each binds:
* the series, instrument and ``day_index``;
* a canonical strictly positive close;
* the close instant ``event_time_ns`` inside ``(start(day), start(day + 1)]``;
* ``available_at_ns`` and ``finalized_at_ns``, never before the close instant and never after ``as_of_ns``;
* its source record digest.

Every supplied observation must belong to a policy feature's series and instrument.

Cutoff (the prior-day-close rule). Feature day ``D`` reads ONLY the closes of days ``D - w`` to ``D - 1``. Each must be
available and finalized at or before ``start(D) = D * 86_400_000_000_000`` ns. The boundary is inclusive, the accepted
point-in-time convention (``historical_pit_dataset``: visible at ``t`` iff ``available_at_ns <= t`` and
``finalized_at_ns <= t``). So:
* a close finalized exactly at ``start(D)`` counts;
* one nanosecond later it does not;
* day ``D`` and later days are never read.

A missing or late window day makes that feature-day UNAVAILABLE with its reasons. There is no interpolation, carry
forward or backfill, and a late close feeds only later feature days.

Formulas (``RF_FIXED_SCALE18_DECIMAL_HALF_EVEN_P80_V1``):
* ``RF_F1_SIMPLE_RETURN_SAMPLE_STDDEV_V1``: ``w`` closes give ``w - 1`` exact simple returns ``c_t / c_(t-1) - 1``, then
  the exact rational mean and the sample variance with denominator ``n - 1``. The square root is published as its
  half-even scale-18 rounding. A precision-80 ``ROUND_HALF_EVEN`` ``Decimal`` value from one fresh, fully specified
  local context only proposes the unit, and exact squared half-unit comparisons decide it (the RG-5 method).
* ``RF_F2_ROLLING_PEAK_DISTANCE_V1``: ``1 - last_close / max(window)``, exact, published half-even at scale 18.

A value beyond the 60-character representation bound is unavailable, never truncated.

Every record binds:
* the feature, its class, source series and instrument;
* the target day and its exact window day range;
* the cutoff and the published value;
* the ``inputs_window_digest`` of the window's observation digests;
* the formula and numeric policy ids.

Every caller claim is recomputed: a different value raises ``feature_recompute_mismatch``. Status: ``PASS`` with a
governed policy, otherwise ``NEEDS_GOVERNANCE_APPROVAL``; unavailable days are recorded and never fail the evidence.
Malformed input and every provenance defect raise ``RegimeFeatureSeriesError``.
``verify_regime_feature_series_evidence`` rebuilds from the exact inputs and is total.

No float, no ambient ``Decimal`` context, no IO, clock, randomness, network or environment access. The runtime
``crypto_core.regime`` package is never imported. Paper evidence only.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, replace
from decimal import Context, Decimal, DivisionByZero, InvalidOperation, Overflow
from enum import Enum
from fractions import Fraction
from itertools import pairwise
from typing import cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_F1_FORMULA_POLICY_ID,
    REGIME_F2_FORMULA_POLICY_ID,
    REGIME_NON_CLAIM_FLAGS,
    REGIME_NUMERIC_POLICY_ID,
    RegimeFeatureClass,
    RegimeFeatureDefinition,
    RegimeFeaturePolicy,
    regime_decimal_text,
    regime_decimal_value,
    regime_feature_policy_rule_set,
    verify_regime_feature_policy,
)

_PREFIX = "regime_feature_series_evidence"
_SCHEMA = "regime-feature-series-evidence.v1"
_DIGEST_FIELD = "feature_series_digest"
_IDENTIFIER_PUNCTUATION = frozenset("-_./:")
_SERIES_PUNCTUATION = frozenset("_.:-")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_feature_series_evidence_rules.v1",
    "contract_id": "RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1",
    "structural_authority_id": "RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1",
    "scope_rule_id": "deterministic_transformation_of_digest_bound_observations_never_external_market_truth.v1",
    "policy_rule_id": "exact_rf2_policy_reproven_governance_incomplete_policy_never_advances.v1",
    "source_rule_id": (
        "ef3_reproven_intact_ready_anchor_equal_every_feature_series_finalized_point_in_time_safe_rights_usable_"
        "feature_input_eligible_price_series_covering_its_instrument.v1"
    ),
    "observation_rule_id": "one_digest_bound_positive_daily_close_per_series_instrument_utc_day_bound_to_a_feature.v1",
    "close_instant_rule_id": "close_instant_after_start_of_its_day_and_at_or_before_start_of_the_next.v1",
    "time_order_rule_id": "available_and_finalized_never_before_the_close_instant.v1",
    "as_of_rule_id": "utc_day_aligned_as_of_every_observation_known_by_it_every_feature_day_starts_by_it.v1",
    "cutoff_rule_id": "feature_day_d_reads_only_days_d_minus_w_to_d_minus_1_available_and_finalized_by_start_of_d.v1",
    "cutoff_boundary": "INCLUSIVE_AT_START_OF_FEATURE_DAY",
    "visibility_convention_id": "accepted_pit_visibility_available_at_and_finalized_at_at_or_before_t.v1",
    "no_fill_rule_id": "missing_or_late_window_day_makes_the_feature_unavailable_no_interpolation_carry_or_backfill.v1",
    "f1_formula_policy_id": REGIME_F1_FORMULA_POLICY_ID,
    "f1_method_id": "w_closes_w_minus_1_exact_simple_returns_exact_mean_sample_variance_n_minus_1_square_root.v1",
    "f2_formula_policy_id": REGIME_F2_FORMULA_POLICY_ID,
    "f2_method_id": "one_minus_last_close_over_window_peak_exact.v1",
    "numeric_policy_id": REGIME_NUMERIC_POLICY_ID,
    "rendering_rule_id": "exact_half_even_scale_18_square_root_precision_80_candidate_adjudicated_exactly.v1",
    "representation_rule_id": "value_beyond_sixty_characters_is_unavailable_never_truncated.v1",
    "recompute_rule_id": "every_claimed_value_must_equal_the_recomputation_else_feature_recompute_mismatch.v1",
    "decimal_internal_precision": 80,
    "decimal_rounding": "ROUND_HALF_EVEN",
    "decimal_exponent_limit": 999999,
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
    "max_instrument_length": 64,
}
REGIME_FEATURE_SERIES_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_PRECISION: int = _RULE_SET_V1["decimal_internal_precision"]  # type: ignore[assignment]
_ROUNDING = str(_RULE_SET_V1["decimal_rounding"])
_EXPONENT_LIMIT: int = _RULE_SET_V1["decimal_exponent_limit"]  # type: ignore[assignment]
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_UNITS = 10**_SCALE
_MAX_TEXT_DECIMAL: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_DAY_INDEX = _MAX_WIRE_INT // _DAY_NS - 1  # so that the start of the next day is still an int64 coordinate
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]
_MAX_INSTRUMENT: int = _RULE_SET_V1["max_instrument_length"]  # type: ignore[assignment]
_UNITS_BOUND = 10 ** (_MAX_TEXT_DECIMAL - 1)  # the first unit count whose rendering exceeds the 60-character bound
_MIN_CLOSES: dict[RegimeFeatureClass, int] = {
    RegimeFeatureClass(name): int(minimum)
    for name, _formula, minimum in regime_feature_policy_rule_set()["supported_feature_classes"]  # type: ignore[attr-defined]
}


def regime_feature_series_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-3 V1 rule set that ``REGIME_FEATURE_SERIES_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class RegimeFeatureSeriesError(EdgeArtifactError):
    """A malformed input or any provenance or source-binding defect: an invalid feature series is never represented."""


@dataclass(frozen=True)
class RegimeDailyCloseObservation:
    """One finalized daily close of one series and instrument, as its digest-bound source record supplies it."""

    series_id: str
    instrument_id: str
    day_index: int
    close: str
    event_time_ns: int
    available_at_ns: int
    finalized_at_ns: int
    source_digest: str


@dataclass(frozen=True)
class RegimeFeatureClaim:
    """A caller's claim of one feature value, ``None`` claiming unavailability; recomputed, never trusted."""

    feature_id: str
    day_index: int
    value: str | None


@dataclass(frozen=True)
class RegimeFeatureSeriesInputs:
    """Everything RF-3 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    feature_series_id: str
    correlation_id: str
    policy: RegimeFeaturePolicy
    source_manifest: EdgeSourcePacketEvidence
    source_manifest_digest: str
    as_of_ns: int
    first_feature_day: int
    last_feature_day: int
    observations: tuple[RegimeDailyCloseObservation, ...]
    claims: tuple[RegimeFeatureClaim, ...]


@dataclass(frozen=True)
class RegimeFeatureRecord:
    """One feature on one target day: its exact window, its cutoff and its published value or unavailability."""

    feature_id: str
    feature_class: RegimeFeatureClass
    source_series_id: str
    instrument_id: str
    target_day_index: int
    window_first_day_index: int
    window_last_day_index: int
    cutoff_ns: int
    available: bool
    value: str | None
    inputs_window_digest: str | None
    unavailable_reason_codes: tuple[str, ...]
    formula_policy_id: str
    numeric_policy_id: str


@dataclass(frozen=True)
class RegimeFeatureSeriesEvidence:
    """Immutable, digest-bound RF-3 regime feature series evidence. Paper evidence only."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    feature_series_id: str
    correlation_id: str
    policy_id: str
    policy_version: str
    regime_feature_policy_digest: str
    policy_governed: bool
    source_manifest_id: str
    source_manifest_digest: str
    source_manifest_gate_verdict: str
    as_of_ns: int
    first_feature_day_index: int
    last_feature_day_index: int
    feature_ids: tuple[str, ...]
    observation_count: int
    observations_digest: str
    claimed_value_count: int
    records: tuple[RegimeFeatureRecord, ...]
    available_record_count: int
    unavailable_record_count: int
    verdict_reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    feature_series_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    direction_signal_emitted: bool = False
    allocation_decided: bool = False
    portfolio_stop_authority: bool = False
    promotion_demotion_decided: bool = False
    kill_quarantine_decided: bool = False
    execution_authorized: bool = False
    order_created: bool = False
    real_orders_enabled: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    current_venue_facts_consumed: bool = False
    external_market_truth_proven: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    regime_filter_admitted: bool = False
    regime_conditioned_performance_proven: bool = False


REGIME_FEATURE_SERIES_NON_CLAIM_FLAGS = REGIME_NON_CLAIM_FLAGS
_RECORD_TYPES = frozenset({RegimeFeatureRecord, RegimeDailyCloseObservation})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    RegimeFeatureRecord: {"feature_class": RegimeFeatureClass},
    RegimeFeatureSeriesEvidence: {"gate_verdict": EdgeGateVerdict},
}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> RegimeFeatureSeriesError:
    return RegimeFeatureSeriesError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _require_identifier(value: object, name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(char.isalnum() or char in _IDENTIFIER_PUNCTUATION for char in value):
        raise _fail(f"{name}_invalid")
    return _require_text(value, name)


def _require_series_id(value: object, name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(
        char.islower() or char.isdigit() or char in _SERIES_PUNCTUATION for char in value
    ):
        raise _fail(f"{name}_invalid")
    return _require_text(value, name)


def _require_instrument(value: object, name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_INSTRUMENT or not value.isascii():
        raise _fail(f"{name}_invalid")
    if not value[0].isalnum() or not all(char.isalnum() or char in _IDENTIFIER_PUNCTUATION for char in value):
        raise _fail(f"{name}_invalid")
    return _require_text(value, name)


def _require_hex64(value: object, name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{name}_invalid")
    return cast(str, value)


def _require_ns(value: object, name: str) -> int:
    """An exact non-negative int64 nanosecond coordinate; never a bool, never a clock."""

    if type(value) is not int or not 0 <= value <= _MAX_WIRE_INT:
        raise _fail(f"{name}_invalid")
    return value


def _require_day_index(value: object, name: str) -> int:
    if type(value) is not int or not 0 <= value <= _MAX_DAY_INDEX:
        raise _fail(f"{name}_invalid")
    return value


def _snapshot(values: object, name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{name}_malformed")
    return tuple(cast(Sequence[object], values))


# --- the formulas ---------------------------------------------------------------------------------------------------


def _decimal_context() -> Context:
    """A fresh, fully specified local context: nothing comes from the thread's ambient or the module default context."""

    return Context(
        prec=_PRECISION,
        rounding=_ROUNDING,
        Emin=-_EXPONENT_LIMIT,
        Emax=_EXPONENT_LIMIT,
        capitals=1,
        clamp=0,
        flags=[],
        traps=[InvalidOperation, DivisionByZero, Overflow],
    )


def _candidate_units(variance: Fraction) -> int | None:
    """A precision-80 ``Decimal`` value of ``sqrt(variance)`` in ``10**-18`` units: a candidate only.

    Every operation receives the one explicit context and the quantized value is read back through ``as_tuple``, so no
    step reads or sets the thread's ambient context. ``None`` when the value leaves the precision-80 representation.
    """

    context = _decimal_context()
    try:
        exact = context.divide(Decimal(variance.numerator, context), Decimal(variance.denominator, context))
        quantum = Decimal((0, (1,), -_SCALE), context)
        _, digits, exponent = context.quantize(context.sqrt(exact), quantum).as_tuple()
    except (ArithmeticError, TypeError, ValueError):
        return None
    if exponent != -_SCALE:
        return None
    units = 0
    for digit in digits:
        units = units * 10 + digit
    return units


def _rounds_half_even_to(units: int, doubled_square: Fraction) -> bool:
    """Whether ``units`` is the half-even rounding of ``t >= 0``, given exactly ``doubled_square == (2 * t) ** 2``.

    ``t`` must lie strictly inside ``(units - 1/2, units + 1/2)``, or on one of those boundaries with ``units`` even.
    Both sides of every boundary comparison are non-negative, so squaring keeps each comparison exact.
    """

    upper = (2 * units + 1) ** 2
    if doubled_square > upper or (doubled_square == upper and units % 2 == 1):
        return False
    if units == 0:
        return True
    lower = (2 * units - 1) ** 2
    return doubled_square > lower or (doubled_square == lower and units % 2 == 0)


def _square_root_text(variance: Fraction) -> str | None:
    """``sqrt(variance)`` published half-even at scale 18, decided by exact rational comparisons.

    The precision-80 candidate is within one unit of the exact rounding: its three ``Decimal`` steps are each correctly
    rounded to 80 significant digits, and a value inside the 60-character bound has at most 59 integer-and-scale
    digits, so the candidate before quantization lies within ``10**-19`` units of the exact value. Exactly one integer
    of the candidate's one-unit neighbourhood passes the exact half-even test and is published; should none pass, the
    evaluation fails closed.
    """

    if variance == 0:
        return regime_decimal_text(Fraction(0))
    candidate = _candidate_units(variance)
    if candidate is None or candidate >= _UNITS_BOUND:
        return None
    doubled_square = 4 * _UNITS * _UNITS * variance
    for units in (candidate, candidate - 1, candidate + 1):
        if units >= 0 and _rounds_half_even_to(units, doubled_square):
            return regime_decimal_text(Fraction(units, _UNITS))
    raise _fail("feature_rounding_not_adjudicated")


def _realized_volatility(closes: Sequence[Fraction]) -> str | None:
    """F1: the sample standard deviation (denominator ``n - 1``) of the ``w - 1`` exact simple returns."""

    returns = [current / previous - 1 for previous, current in pairwise(closes)]
    count = len(returns)
    mean = sum(returns, Fraction(0)) / count
    variance = sum(((value - mean) ** 2 for value in returns), Fraction(0)) / (count - 1)
    return _square_root_text(variance)


def _peak_distance(closes: Sequence[Fraction]) -> str | None:
    """F2: ``1 - last_close / max(window)``, exact before its half-even rendering."""

    return regime_decimal_text(1 - closes[-1] / max(closes))


def _measure(feature_class: RegimeFeatureClass, closes: Sequence[Fraction]) -> str | None:
    if feature_class is RegimeFeatureClass.F1_REALIZED_VOL:
        return _realized_volatility(closes)
    return _peak_distance(closes)


def measure_regime_feature_value(feature_class: RegimeFeatureClass, closes: Sequence[str]) -> str | None:
    """The published value of one V1 feature class over an exact window of canonical positive closes, oldest first.

    ``None`` when the value lies beyond the 60-character representation bound. Malformed input raises.
    """

    if type(feature_class) is not RegimeFeatureClass:
        raise _fail("measure_feature_class_invalid")
    window = _snapshot(closes, "measure_closes")
    values = [regime_decimal_value(close) for close in window]
    if any(value is None or value <= 0 for value in values):
        raise _fail("measure_close_invalid")
    if len(values) < _MIN_CLOSES[feature_class]:
        raise _fail("measure_window_too_short")
    return _measure(feature_class, cast(list[Fraction], values))


# --- canonical wire form --------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in cast(tuple, value)]
    if type(value) is int:
        if 0 <= cast(int, value) <= _MAX_WIRE_INT:
            return value
        raise _fail("payload_integer_out_of_range")
    if value is None or type(value) is str or type(value) is bool:
        return value
    raise _fail("payload_value_not_canonical")


def _payload(artifact: object) -> dict[str, object]:
    """The exact wire form: an enum field holds its exact member, everything else exact records and scalars."""

    enums = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for item in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, item.name)
        enum_cls = enums.get(item.name)
        if enum_cls is None:
            payload[item.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[item.name] = cast(Enum, value).value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


def regime_daily_close_observation_digest(observation: RegimeDailyCloseObservation) -> str:
    """The digest of one observation's exact canonical wire form."""

    if type(observation) is not RegimeDailyCloseObservation:
        raise _fail("observation_malformed")
    return edge_sha256_text(edge_canonical_json(_payload(observation)))


# --- provenance -----------------------------------------------------------------------------------------------------


def _require_policy(value: object) -> RegimeFeaturePolicy:
    """The exact RF-2 policy, re-proven through its total verifier; its governance is read, never assumed."""

    _require_exact(value, RegimeFeaturePolicy, "policy")
    if not verify_regime_feature_policy(value).intact:
        raise _fail("policy_not_intact")
    return cast(RegimeFeaturePolicy, value)


def _require_source_manifest(value: object, anchor: object) -> EdgeSourcePacketEvidence:
    """The exact EF-3 manifest, re-proven through its public verifier, equal to the anchor and READY."""

    _require_exact(value, EdgeSourcePacketEvidence, "source_manifest")
    expected = _require_hex64(anchor, "source_manifest_digest")
    verification = verify_edge_source_packet_evidence(value)
    if not verification.intact:
        raise _fail("source_manifest_not_intact")
    if verification.recomputed_digest != expected:
        raise _fail("source_manifest_digest_mismatch")
    manifest = cast(EdgeSourcePacketEvidence, value)
    if manifest.status is not EdgeEvidenceStatus.READY:
        raise _fail("source_manifest_rejected")
    return manifest


def _bind_feature_sources(policy: RegimeFeaturePolicy, manifest: EdgeSourcePacketEvidence) -> None:
    """Every feature's series must be an authenticated, PIT-eligible price series of the manifest covering its instrument."""

    records = {record.series_id: record for record in manifest.series}
    eligible = frozenset(manifest.feature_input_series_ids)
    for feature in policy.features:
        series_id = feature.source_series_id
        record = records.get(series_id)
        if record is None:
            raise _fail(f"source_series_not_in_manifest:{series_id}")
        if record.finalized_only is not True:
            raise _fail(f"source_series_not_finalized_only:{series_id}")
        if record.point_in_time_revision_safe is not True:
            raise _fail(f"source_series_not_point_in_time_revision_safe:{series_id}")
        if record.rights_usable is not True:
            raise _fail(f"source_series_rights_not_usable:{series_id}")
        if record.feature_input_eligible is not True or series_id not in eligible:
            raise _fail(f"source_series_not_feature_input_eligible:{series_id}")
        if record.price_semantics is None:
            raise _fail(f"source_series_not_a_price_series:{series_id}")
        if feature.instrument_id not in record.instrument_coverage:
            raise _fail(f"source_series_instrument_not_covered:{series_id}:{feature.instrument_id}")


def _canonical_observations(
    values: object, *, as_of_ns: int, bindings: frozenset[tuple[str, str]]
) -> dict[tuple[str, str], dict[int, RegimeDailyCloseObservation]]:
    """Every observation validated once, grouped by (series, instrument) and keyed by UTC day."""

    grouped: dict[tuple[str, str], dict[int, RegimeDailyCloseObservation]] = {binding: {} for binding in bindings}
    for item in _snapshot(values, "observations"):
        _require_exact(item, RegimeDailyCloseObservation, "observation")
        observation = cast(RegimeDailyCloseObservation, item)
        series_id = _require_series_id(observation.series_id, "observation_series_id")
        instrument_id = _require_instrument(observation.instrument_id, "observation_instrument_id")
        day = _require_day_index(observation.day_index, "observation_day_index")
        close = regime_decimal_value(observation.close)
        if close is None:
            raise _fail("observation_close_invalid")
        if close <= 0:
            raise _fail("observation_close_not_positive")
        event = _require_ns(observation.event_time_ns, "observation_event_time_ns")
        available = _require_ns(observation.available_at_ns, "observation_available_at_ns")
        finalized = _require_ns(observation.finalized_at_ns, "observation_finalized_at_ns")
        if not day * _DAY_NS < event <= (day + 1) * _DAY_NS:
            raise _fail("observation_close_instant_outside_its_day")
        if available < event:
            raise _fail("observation_available_before_its_close")
        if finalized < event:
            raise _fail("observation_finalized_before_its_close")
        if available > as_of_ns or finalized > as_of_ns:
            raise _fail("observation_after_as_of")
        source_digest = _require_hex64(observation.source_digest, "observation_source_digest")
        binding = (series_id, instrument_id)
        if binding not in grouped:
            raise _fail("observation_not_bound_to_a_policy_feature")
        if day in grouped[binding]:
            raise _fail("observation_duplicate_day")
        grouped[binding][day] = RegimeDailyCloseObservation(
            series_id=series_id,
            instrument_id=instrument_id,
            day_index=day,
            close=cast(str, observation.close),
            event_time_ns=event,
            available_at_ns=available,
            finalized_at_ns=finalized,
            source_digest=source_digest,
        )
    return grouped


# --- the feature records --------------------------------------------------------------------------------------------


def _window_digest(window: Sequence[RegimeDailyCloseObservation]) -> str:
    return edge_sha256_text(edge_canonical_json([regime_daily_close_observation_digest(item) for item in window]))


def _feature_record(
    feature: RegimeFeatureDefinition, day: int, closes: Mapping[int, RegimeDailyCloseObservation]
) -> RegimeFeatureRecord:
    """One feature on day ``day``: only days ``day - w`` to ``day - 1``, each final by ``start(day)``."""

    first, last = day - feature.lookback_days, day - 1
    cutoff = day * _DAY_NS
    reasons: list[str] = []
    window: list[RegimeDailyCloseObservation] = []
    for index in range(first, last + 1):
        observation = closes.get(index)
        if observation is None:
            reasons.append(_reason(f"window_day_missing:{index}"))
        elif observation.available_at_ns > cutoff or observation.finalized_at_ns > cutoff:
            reasons.append(_reason(f"window_day_not_final_by_cutoff:{index}"))
        else:
            window.append(observation)
    value: str | None = None
    if not reasons:
        value = _measure(feature.feature_class, [Fraction(item.close) for item in window])
        if value is None:
            reasons.append(_reason("value_beyond_representation"))
    return RegimeFeatureRecord(
        feature_id=feature.feature_id,
        feature_class=feature.feature_class,
        source_series_id=feature.source_series_id,
        instrument_id=feature.instrument_id,
        target_day_index=day,
        window_first_day_index=first,
        window_last_day_index=last,
        cutoff_ns=cutoff,
        available=value is not None,
        value=value,
        inputs_window_digest=None if value is None else _window_digest(window),
        unavailable_reason_codes=_sorted_unique(reasons),
        formula_policy_id=feature.formula_policy_id,
        numeric_policy_id=REGIME_NUMERIC_POLICY_ID,
    )


def _verify_claims(values: object, records: Sequence[RegimeFeatureRecord]) -> int:
    """Every claim names one record of this evidence and equals its recomputed value exactly."""

    by_key = {(record.feature_id, record.target_day_index): record for record in records}
    seen: set[tuple[str, int]] = set()
    items = _snapshot(values, "claims")
    for item in items:
        _require_exact(item, RegimeFeatureClaim, "claim")
        claim = cast(RegimeFeatureClaim, item)
        feature_id = _require_identifier(claim.feature_id, "claim_feature_id")
        day = _require_day_index(claim.day_index, "claim_day_index")
        if claim.value is not None and regime_decimal_value(claim.value) is None:
            raise _fail("claim_value_invalid")
        key = (feature_id, day)
        if key in seen:
            raise _fail("claim_duplicate")
        seen.add(key)
        record = by_key.get(key)
        if record is None:
            raise _fail("claim_outside_the_evidence")
        if record.value != claim.value:
            raise _fail(f"feature_recompute_mismatch:{feature_id}:{day}")
    return len(items)


# --- the evidence ---------------------------------------------------------------------------------------------------


def build_regime_feature_series_evidence(inputs: RegimeFeatureSeriesInputs) -> RegimeFeatureSeriesEvidence:
    """Compute every policy feature for every day of the window from the exact, re-proven inputs.

    Malformed input and every provenance or source-binding defect raise ``RegimeFeatureSeriesError``; a claim that is
    not the recomputation raises ``feature_recompute_mismatch``. Inputs are never mutated.
    """

    _require_exact(inputs, RegimeFeatureSeriesInputs, "inputs")
    feature_series_id = _require_text(inputs.feature_series_id, "feature_series_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    policy = _require_policy(inputs.policy)
    manifest = _require_source_manifest(inputs.source_manifest, inputs.source_manifest_digest)
    as_of_ns = _require_ns(inputs.as_of_ns, "as_of_ns")
    if as_of_ns % _DAY_NS:
        raise _fail("as_of_ns_not_utc_day_aligned")
    first = _require_day_index(inputs.first_feature_day, "first_feature_day")
    last = _require_day_index(inputs.last_feature_day, "last_feature_day")
    if first > last:
        raise _fail("feature_window_empty")
    if last * _DAY_NS > as_of_ns:
        raise _fail("feature_window_after_as_of")
    if first < max(feature.lookback_days for feature in policy.features):
        raise _fail("feature_window_reaches_before_day_zero")
    _bind_feature_sources(policy, manifest)
    bindings = frozenset((feature.source_series_id, feature.instrument_id) for feature in policy.features)
    observations = _canonical_observations(inputs.observations, as_of_ns=as_of_ns, bindings=bindings)

    records = tuple(
        _feature_record(feature, day, observations[(feature.source_series_id, feature.instrument_id)])
        for feature in policy.features
        for day in range(first, last + 1)
    )
    claimed = _verify_claims(inputs.claims, records)
    ordered = [observations[binding][day] for binding in sorted(observations) for day in sorted(observations[binding])]
    governance = [] if policy.advances else [_reason("policy_needs_governance_approval")]
    verdict = resolve_edge_gate_verdict([], [], governance)
    available = sum(1 for record in records if record.available)

    seed = RegimeFeatureSeriesEvidence(
        schema_version=_SCHEMA,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        feature_series_id=feature_series_id,
        correlation_id=correlation_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        regime_feature_policy_digest=policy.regime_feature_policy_digest,
        policy_governed=policy.advances,
        source_manifest_id=manifest.manifest_id,
        source_manifest_digest=manifest.source_packet_evidence_digest,
        source_manifest_gate_verdict=manifest.gate_verdict.value,
        as_of_ns=as_of_ns,
        first_feature_day_index=first,
        last_feature_day_index=last,
        feature_ids=tuple(feature.feature_id for feature in policy.features),
        observation_count=len(ordered),
        observations_digest=_window_digest(ordered),
        claimed_value_count=claimed,
        records=records,
        available_record_count=available,
        unavailable_record_count=len(records) - available,
        verdict_reason_codes=_sorted_unique(governance),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_FEATURE_SERIES_RULE_SET_DIGEST,
        feature_series_digest="",
    )
    return replace(seed, feature_series_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def regime_feature_series_evidence_to_dict(evidence: RegimeFeatureSeriesEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an evidence, its self-digest included."""

    return _payload(evidence)


def regime_feature_series_evidence_digest(evidence: RegimeFeatureSeriesEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``feature_series_digest``."""

    return edge_payload_digest(_payload(evidence), _DIGEST_FIELD)


def verify_regime_feature_series_evidence(
    evidence: object, inputs: RegimeFeatureSeriesInputs
) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not RegimeFeatureSeriesEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_regime_feature_series_evidence(inputs))
        codes = {_reason("self_digest_mismatch")} if carried[_DIGEST_FIELD] != recomputed else set()
        for name in set(expected) | set(carried):
            if name not in expected or name not in carried:
                codes.add(_reason(f"field_mismatch:{name}"))
            elif edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(not reason_codes, reason_codes, recomputed, canonical)
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


__all__ = [
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
]
