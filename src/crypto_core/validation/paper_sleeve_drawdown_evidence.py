"""RG-4 paper sleeve and portfolio drawdown evidence (RG4_PAPER_SLEEVE_DRAWDOWN_EVIDENCE_V1).

``docs/crypto_core/multi_sleeve_risk_governance_design.md`` §1 (RG-4). This artifact measures the rolling peak distance
of every envelope-declared sleeve's normalized paper-performance index, and of the ONE portfolio performance path that
the governed ``PaperPortfolioPerformancePathPolicy`` defines. It is MEASUREMENT EVIDENCE ONLY. It decides no promotion,
demotion, portfolio stop or allocation: RG-6 owns the ladder decisions that consume sleeve drawdown, and RG-8 owns the
portfolio-stop decisions that consume portfolio drawdown. It is never capital, equity or execution permission.

Binding, every element re-proven:

* RG-2: the ``PaperPortfolioRiskEnvelope`` is re-pinned through its total verifier;
* policy: the ``PaperPortfolioPerformancePathPolicy`` is re-proven through its total verifier. It must bind this
  envelope's digest and weight exactly the envelope's declared sleeves;
* RG-3: every supplied sleeve's ``PaperSleevePerformanceEvidence`` is REBUILT from its exact inputs and must equal the
  supplied evidence; only the reconstruction is used, and the sleeve identity is copied from it. It must re-pin the
  same envelope, be covered by the policy, and lie on the exact evidence-window UTC-day grid.

Measurement (code-defined rule set ``PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST``). Every path starts with the start
observation ``1`` and continues with one observation per UTC-day endpoint of the evidence window:

* sleeve index: ``I_0 = 1`` (the accepted methodology start) and ``I_d = I_(d-1) * (1 + r_d)`` over the re-proven RG-3
  daily returns, the accepted chain-linked index rule;
* portfolio index: ``P_t = sum_i(w_i * I_i,t)`` with the policy's fixed weights and no rebalancing, so ``P_0 = 1``;
* running peak: ``M_0 = 1``, so the start participates, then ``M_t = max(M_(t-1), X_t)``;
* peak distance: ``(M_t - X_t) / M_t``, an exact reduced fraction in ``[0, 1)``;
* current peak distance: the end-of-window observation. Maximum peak distance: over every observation, start included.

Indices and running peaks are canonical exact decimal text; a peak distance is canonical reduced fraction text
``"p/q"`` (``"0/1"`` for zero). Nothing is rounded.

Status precedence:

* ``NEEDS_GOVERNANCE_APPROVAL`` when the envelope, the policy or a sleeve's RG-3 evidence is not governed;
* otherwise ``NOT_COMPUTABLE`` when a covered sleeve is not supplied or has no computable RG-3 evidence, or a
  representation bound is exceeded;
* otherwise ``READY``.

A sleeve's measurement is carried when that sleeve's RG-3 evidence is ``READY``. The portfolio measurement is carried
only when every covered sleeve is measured and both the envelope and the policy advance. A sleeve or a day is never
dropped, interpolated or carried forward.

Any provenance or binding defect raises ``PaperSleeveDrawdownEvidenceError``. ``verify_paper_sleeve_drawdown_evidence``
re-proves an evidence by rebuilding it from its inputs and is total. ``measure_paper_peak_distance`` exposes the exact
measurement of one index path.

Non-overclaim: no promotion, demotion, stop, allocation or threshold verdict, and no profitability, edge or readiness
claim. Mark, instant and funding origins and episode-set completeness stay unproven. Exact ``Fraction`` arithmetic, no
float, no ``decimal`` context, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_performance_path_policy import (
    PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
    PaperPortfolioPerformancePathPolicy,
    PaperPortfolioPerformanceWeight,
    verify_paper_portfolio_performance_path_policy,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
    paper_sleeve_performance_evidence_to_dict,
)

_SCHEMA_VERSION = "paper-sleeve-drawdown-evidence.v1"
_REASON_PREFIX = "paper_sleeve_drawdown_evidence"
_SELF_DIGEST_FIELD = "drawdown_evidence_digest"
_T = TypeVar("_T")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "paper_sleeve_drawdown_evidence_rules.v1",
    "scope_rule_id": "measurement_evidence_only_never_promotion_demotion_stop_allocation_or_execution.v1",
    "decision_ownership_rule_id": "rg6_owns_ladder_decisions_rg8_owns_portfolio_stop_decisions_rg4_decides_nothing.v1",
    "sleeve_index_rule_id": "methodology_start_one_then_rg3_daily_returns_chain_linked.v1",
    "portfolio_index_rule_id": "governed_performance_path_policy_fixed_weight_convex_combination.v1",
    "initial_index": "1",
    "initial_peak_rule_id": "the_start_observation_one_is_the_first_running_peak_observation.v1",
    "running_peak_rule_id": "running_peak_is_the_maximum_observation_so_far_never_decreasing.v1",
    "peak_distance_rule_id": "running_peak_minus_index_over_running_peak_exact_reduced_fraction_in_zero_one.v1",
    "current_rule_id": "current_peak_distance_is_the_end_of_window_observation.v1",
    "maximum_rule_id": "maximum_peak_distance_over_every_observation_start_included.v1",
    "evidence_window_rule_id": "every_sleeve_on_the_exact_evidence_window_utc_day_grid.v1",
    "completeness_rule_id": "missing_or_uncomputable_covered_sleeve_makes_the_portfolio_not_computable.v1",
    "status_rule_id": "needs_governance_approval_over_not_computable_over_ready.v1",
    "numeric_rule_id": "exact_fraction_arithmetic_canonical_decimal_and_reduced_fraction_text_no_rounding.v1",
    "index_max_text_length": 4096,
    "fraction_max_part_digits": 4096,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_INITIAL_INDEX_TEXT = str(_RULE_SET_V1["initial_index"])
_INITIAL_INDEX = Fraction(_INITIAL_INDEX_TEXT)
_MAX_INDEX_TEXT: int = _RULE_SET_V1["index_max_text_length"]  # type: ignore[assignment]
_MAX_FRACTION_DIGITS: int = _RULE_SET_V1["fraction_max_part_digits"]  # type: ignore[assignment]
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]


def paper_sleeve_drawdown_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class PaperSleeveDrawdownEvidenceError(EdgeArtifactError):
    """Raised on malformed input or any provenance or binding defect: an invalid evidence is never represented."""


class PaperSleeveDrawdownStatus(str, Enum):
    """READY only when governed and every measurement is computed; the other states are represented, never values."""

    READY = "READY"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


@dataclass(frozen=True)
class PaperPeakDistanceMeasurement:
    """The exact rolling peak distance of one strictly positive paper index path, start observation included."""

    index_path: tuple[str, ...]
    running_peak_path: tuple[str, ...]
    peak_distance_path: tuple[str, ...]
    current_peak_distance: str
    max_peak_distance: str


@dataclass(frozen=True)
class PaperSleeveDrawdownSleeveInputs:
    """One sleeve's RG-3 evidence and the exact inputs it is rebuilt from."""

    performance_inputs: PaperSleevePerformanceInputs
    performance_evidence: PaperSleevePerformanceEvidence


@dataclass(frozen=True)
class PaperSleeveDrawdownInputs:
    """Everything RG-4 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    drawdown_evidence_id: str
    correlation_id: str
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    performance_path_policy: PaperPortfolioPerformancePathPolicy
    window_start_ns: int
    window_end_ns: int
    sleeves: tuple[PaperSleeveDrawdownSleeveInputs, ...]


@dataclass(frozen=True)
class PaperSleeveDrawdownRecord:
    """One sleeve's re-proven RG-3 binding and, when its evidence is READY, its exact drawdown measurement."""

    sleeve_id: str
    market_symbol: str
    performance_evidence_digest: str
    performance_status: str
    computed: bool
    measurement: PaperPeakDistanceMeasurement | None
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class PaperPortfolioDrawdownRecord:
    """The portfolio performance path's weights and, when every covered sleeve is measured, its drawdown measurement."""

    computed: bool
    performance_weights: tuple[PaperPortfolioPerformanceWeight, ...]
    measurement: PaperPeakDistanceMeasurement | None
    reason_codes: tuple[str, ...]


PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("promotion_demotion_decided", False),
    ("ladder_threshold_evaluated", False),
    ("portfolio_stop_evaluated", False),
    ("portfolio_allocation_approved", False),
    ("capital_allocated", False),
    ("execution_authorized", False),
    ("account_equity_represented", False),
    ("capital_represented", False),
    ("risk_budget_used_as_weight", False),
    ("reference_notional_used_as_weight", False),
    ("rebalancing_applied", False),
    ("interpolation_used", False),
    ("carry_forward_used", False),
    ("profitability_proven", False),
    ("edge_proven", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("prdv4_stage4_complete", False),
    ("mark_price_origin_proven", False),
    ("timestamp_origin_proven", False),
    ("episode_set_completeness_proven", False),
)


@dataclass(frozen=True)
class PaperSleeveDrawdownEvidence:
    """Immutable, digest-bound RG-4 drawdown measurement evidence. Paper only; decides nothing."""

    schema_version: str
    status: PaperSleeveDrawdownStatus
    ready: bool
    drawdown_evidence_id: str
    correlation_id: str
    envelope_digest: str
    envelope_policy_digest: str
    envelope_advances: bool
    performance_path_policy_digest: str
    performance_path_governed_digest: str
    performance_path_policy_advances: bool
    performance_path_rule_set_digest: str
    rebalancing_convention: str
    window_start_ns: int
    window_end_ns: int
    day_count: int
    sleeves: tuple[PaperSleeveDrawdownRecord, ...]
    missing_sleeve_ids: tuple[str, ...]
    portfolio: PaperPortfolioDrawdownRecord
    rule_set_id: str
    rule_set_digest: str
    reason_codes: tuple[str, ...]
    drawdown_evidence_digest: str
    paper_only: bool = True
    promotion_demotion_decided: bool = False
    ladder_threshold_evaluated: bool = False
    portfolio_stop_evaluated: bool = False
    portfolio_allocation_approved: bool = False
    capital_allocated: bool = False
    execution_authorized: bool = False
    account_equity_represented: bool = False
    capital_represented: bool = False
    risk_budget_used_as_weight: bool = False
    reference_notional_used_as_weight: bool = False
    rebalancing_applied: bool = False
    interpolation_used: bool = False
    carry_forward_used: bool = False
    profitability_proven: bool = False
    edge_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    prdv4_stage4_complete: bool = False
    mark_price_origin_proven: bool = False
    timestamp_origin_proven: bool = False
    episode_set_completeness_proven: bool = False


_RECORD_TYPES = frozenset(
    {
        PaperPeakDistanceMeasurement,
        PaperSleeveDrawdownRecord,
        PaperPortfolioDrawdownRecord,
        PaperPortfolioPerformanceWeight,
    }
)
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    PaperSleeveDrawdownEvidence: {"status": PaperSleeveDrawdownStatus},
}


# --- helpers --------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> PaperSleeveDrawdownEvidenceError:
    return PaperSleeveDrawdownEvidenceError(_reason(code))


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_exact(value: object, cls: type, code: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{code}_malformed")


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object, **kwargs: object) -> _T:
    """Call one accepted public builder; any failure is a provenance defect of this evidence."""

    try:
        return builder(*args, **kwargs)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed at this boundary
        raise _fail(f"{code}_reconstruction_failed") from exc


def _parse_decimal(value: object, max_length: int) -> Fraction | None:
    """Exact value of canonical plain decimal text (no exponent, trailing zero or negative zero), else ``None``."""

    if type(value) is not str or value == "" or len(value) > max_length or not value.isascii():
        return None
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if not _ascii_digits(integer) or (integer != "0" and integer.startswith("0")):
        return None
    if dot == "." and (not _ascii_digits(fraction) or fraction.endswith("0")):
        return None
    if negative and integer == "0" and dot == "":
        return None
    return Fraction(value)


def _factor_out(value: int, prime: int) -> tuple[int, int]:
    """``(rest, count)`` with ``value == rest * prime**count`` and ``rest`` not divisible by ``prime``."""

    count = 0
    while value % prime == 0:
        power, exponent = prime, 1
        while value % (power * power) == 0:
            power *= power
            exponent *= 2
        value //= power
        count += exponent
    return value, count


def _render_decimal(value: Fraction) -> str | None:
    """Canonical plain decimal text of a terminating value within the committed bound, else ``None``."""

    rest, twos = _factor_out(value.denominator, 2)
    rest, fives = _factor_out(rest, 5)
    if rest != 1:
        return None
    scale = max(twos, fives)
    if scale >= _MAX_INDEX_TEXT:
        return None
    units = abs(value.numerator) * (2 ** (scale - twos)) * (5 ** (scale - fives))
    if units >= 10**_MAX_INDEX_TEXT:
        return None
    digits = str(units).rjust(scale + 1, "0")
    rendered = f"{digits[:-scale]}.{digits[-scale:]}" if scale else digits
    if scale:
        rendered = rendered.rstrip("0").rstrip(".")
    if value < 0 and rendered != "0":
        rendered = f"-{rendered}"
    return rendered if len(rendered) <= _MAX_INDEX_TEXT else None


def _render_fraction(value: Fraction) -> str | None:
    """Canonical reduced fraction text ``"p/q"`` (``"0/1"`` for zero) within the committed bound, else ``None``."""

    bound = 10**_MAX_FRACTION_DIGITS
    if value.numerator < 0 or value.numerator >= bound or value.denominator >= bound:
        return None
    return f"{value.numerator}/{value.denominator}"


# --- measurement ----------------------------------------------------------------------------------------------------


def _measure(values: tuple[Fraction, ...]) -> PaperPeakDistanceMeasurement | None:
    """The exact rolling peak distance of a strictly positive path whose first observation is the start one.

    ``None`` when a value exceeds its committed representation bound.
    """

    peak = values[0]
    maximum = Fraction(0)
    index_path: list[str] = []
    peak_path: list[str] = []
    distance_path: list[str] = []
    for value in values:
        if value > peak:
            peak = value
        distance = (peak - value) / peak
        if distance > maximum:
            maximum = distance
        texts = (_render_decimal(value), _render_decimal(peak), _render_fraction(distance))
        if any(text is None for text in texts):
            return None
        index_text, peak_text, distance_text = cast(tuple[str, str, str], texts)
        index_path.append(index_text)
        peak_path.append(peak_text)
        distance_path.append(distance_text)
    maximum_text = _render_fraction(maximum)
    if maximum_text is None:
        return None
    return PaperPeakDistanceMeasurement(
        index_path=tuple(index_path),
        running_peak_path=tuple(peak_path),
        peak_distance_path=tuple(distance_path),
        current_peak_distance=distance_path[-1],
        max_peak_distance=maximum_text,
    )


def measure_paper_peak_distance(index_path: Sequence[str]) -> PaperPeakDistanceMeasurement:
    """Exact rolling peak distance of one strictly positive paper index path whose first observation is ``"1"``.

    Every observation must be canonical plain decimal text within the committed bound. Malformed input, a first
    observation other than the start one, a non-positive observation or an exceeded representation bound raises
    ``PaperSleeveDrawdownEvidenceError``.
    """

    items = _snapshot(index_path, "index_path")
    if not items:
        raise _fail("index_path_empty")
    values: list[Fraction] = []
    for item in items:
        value = _parse_decimal(item, _MAX_INDEX_TEXT)
        if value is None:
            raise _fail("index_path_observation_invalid")
        if value <= 0:
            raise _fail("index_path_observation_not_positive")
        values.append(value)
    if values[0] != _INITIAL_INDEX:
        raise _fail("index_path_start_not_one")
    measurement = _measure(tuple(values))
    if measurement is None:
        raise _fail("measurement_representation_bound_exceeded")
    return measurement


# --- sleeve re-proof ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _ProvenSleeve:
    sleeve_id: str
    evidence: PaperSleevePerformanceEvidence
    index: tuple[Fraction, ...] | None


def _prove_sleeve(
    item: object,
    *,
    envelope: PaperPortfolioRiskEnvelope,
    covered: frozenset[str],
    window_start_ns: int,
    window_end_ns: int,
    day_count: int,
) -> _ProvenSleeve:
    _require_exact(item, PaperSleeveDrawdownSleeveInputs, "sleeve")
    sleeve = cast(PaperSleeveDrawdownSleeveInputs, item)
    _require_exact(getattr(sleeve, "performance_inputs", None), PaperSleevePerformanceInputs, "performance_inputs")
    _require_exact(
        getattr(sleeve, "performance_evidence", None), PaperSleevePerformanceEvidence, "performance_evidence"
    )
    rebuilt = _rebuild("sleeve_performance", build_paper_sleeve_performance_evidence, sleeve.performance_inputs)
    if not _canonically_equal(sleeve.performance_evidence, rebuilt, paper_sleeve_performance_evidence_to_dict):
        raise _fail("sleeve_performance_not_reconstructed")
    if rebuilt.envelope_digest != envelope.envelope_digest:
        raise _fail("sleeve_performance_envelope_mismatch")
    if rebuilt.sleeve_id not in covered:
        raise _fail("sleeve_not_covered_by_performance_path_policy")
    if (
        rebuilt.window_start_ns != window_start_ns
        or rebuilt.window_end_ns != window_end_ns
        or rebuilt.day_count != day_count
    ):
        raise _fail("sleeve_window_not_the_evidence_window")
    if rebuilt.status is not PaperSleevePerformanceStatus.READY:
        return _ProvenSleeve(sleeve_id=rebuilt.sleeve_id, evidence=rebuilt, index=None)

    methodology = sleeve.performance_inputs.methodology
    if methodology is None or methodology.normalized_index_start != _INITIAL_INDEX_TEXT:
        raise _fail("sleeve_index_start_not_one")
    if len(rebuilt.daily_returns) != day_count:
        raise _fail("sleeve_daily_returns_not_the_evidence_window")
    index = [_INITIAL_INDEX]
    for text in rebuilt.daily_returns:
        daily_return = _parse_decimal(text, _MAX_INDEX_TEXT)
        if daily_return is None:
            raise _fail("sleeve_daily_return_invalid")
        growth = 1 + daily_return
        if growth <= 0:
            raise _fail("sleeve_index_not_positive")
        index.append(index[-1] * growth)
    return _ProvenSleeve(sleeve_id=rebuilt.sleeve_id, evidence=rebuilt, index=tuple(index))


# --- serialization --------------------------------------------------------------------------------------------------


def _serialize(value: object) -> object:
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if type(value) is tuple:
        return [_serialize(item) for item in value]
    if type(value) is int:
        if value < 0 or value > _MAX_WIRE_INT:
            raise _fail("payload_integer_out_of_range")
        return value
    if value is None or type(value) in (str, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize exactly: an enum field must hold the exact member and every other value an exact builtin or record."""

    enum_fields = _ENUM_FIELDS.get(type(artifact), {})
    payload: dict[str, object] = {}
    for field in fields(artifact):  # type: ignore[arg-type]
        value = getattr(artifact, field.name)
        enum_cls = enum_fields.get(field.name)
        if enum_cls is None:
            payload[field.name] = _serialize(value)
        elif type(value) is enum_cls:
            payload[field.name] = value.value
        else:
            raise _fail("payload_enum_field_not_exact_member")
    return payload


# --- evidence -------------------------------------------------------------------------------------------------------


def _require_policy(
    value: object, envelope: PaperPortfolioRiskEnvelope
) -> tuple[PaperPortfolioPerformancePathPolicy, dict[str, Fraction]]:
    _require_exact(value, PaperPortfolioPerformancePathPolicy, "performance_path_policy")
    if not verify_paper_portfolio_performance_path_policy(value).intact:
        raise _fail("performance_path_policy_not_intact")
    policy = cast(PaperPortfolioPerformancePathPolicy, value)
    if policy.rule_set_digest != PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST:
        raise _fail("performance_path_policy_rule_set_unsupported")
    if policy.envelope_digest != envelope.envelope_digest:
        raise _fail("performance_path_policy_envelope_mismatch")
    weights = {weight.sleeve_id: Fraction(weight.performance_weight) for weight in policy.performance_weights}
    if set(weights) != {cap.sleeve_id for cap in envelope.sleeve_caps}:
        raise _fail("performance_path_policy_coverage_mismatch")
    return policy, weights


def _sleeve_record(proven: _ProvenSleeve) -> PaperSleeveDrawdownRecord:
    """The sleeve's record; a sleeve without a measurement carries its exact RG-3 reason provenance."""

    evidence = proven.evidence
    measurement: PaperPeakDistanceMeasurement | None = None
    reasons: list[str] = []
    if proven.index is None:
        reasons.append(_reason("sleeve_performance_not_ready"))
        reasons.extend(evidence.reason_codes)
    else:
        measurement = _measure(proven.index)
        if measurement is None:
            reasons.append(_reason("sleeve_measurement_representation_bound_exceeded"))
    return PaperSleeveDrawdownRecord(
        sleeve_id=proven.sleeve_id,
        market_symbol=evidence.market_symbol,
        performance_evidence_digest=evidence.performance_evidence_digest,
        performance_status=evidence.status.value,
        computed=measurement is not None,
        measurement=measurement,
        reason_codes=tuple(sorted(set(reasons))),
    )


def build_paper_sleeve_drawdown_evidence(inputs: PaperSleeveDrawdownInputs) -> PaperSleeveDrawdownEvidence:
    """Measure every covered sleeve's and the portfolio's exact rolling peak distance from re-proven evidence.

    Malformed input and every provenance or binding defect raise ``PaperSleeveDrawdownEvidenceError``. Missing
    governance yields ``NEEDS_GOVERNANCE_APPROVAL``; missing or uncomputable sleeve evidence yields ``NOT_COMPUTABLE``.
    Inputs are read once and never mutated. The evidence decides nothing.
    """

    _require_exact(inputs, PaperSleeveDrawdownInputs, "inputs")
    evidence_id = _require_text(inputs.drawdown_evidence_id, "drawdown_evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    window_start = _require_int(inputs.window_start_ns, "window_start_ns", minimum=0)
    window_end = _require_int(inputs.window_end_ns, "window_end_ns", minimum=0)
    if window_start % _DAY_NS != 0 or window_end % _DAY_NS != 0:
        raise _fail("window_not_utc_day_aligned")
    if window_end <= window_start:
        raise _fail("window_end_not_after_start")
    day_count = (window_end - window_start) // _DAY_NS

    envelope = inputs.portfolio_risk_envelope
    _require_exact(envelope, PaperPortfolioRiskEnvelope, "portfolio_risk_envelope")
    if not verify_paper_portfolio_risk_envelope(envelope).intact:
        raise _fail("portfolio_risk_envelope_not_intact")
    policy, weights = _require_policy(inputs.performance_path_policy, envelope)

    proven: dict[str, _ProvenSleeve] = {}
    for item in _snapshot(inputs.sleeves, "sleeves"):
        sleeve = _prove_sleeve(
            item,
            envelope=envelope,
            covered=frozenset(weights),
            window_start_ns=window_start,
            window_end_ns=window_end,
            day_count=day_count,
        )
        if sleeve.sleeve_id in proven:
            raise _fail("sleeve_duplicate")
        proven[sleeve.sleeve_id] = sleeve

    governance: list[str] = []
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    if policy.advances is not True:
        governance.append(_reason("performance_path_policy_not_governed"))
    blocking: list[str] = []
    records: list[PaperSleeveDrawdownRecord] = []
    for sleeve_id in sorted(proven):
        record = _sleeve_record(proven[sleeve_id])
        records.append(record)
        if proven[sleeve_id].evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL:
            governance.append(_reason(f"sleeve_performance_needs_governance_approval:{sleeve_id}"))
        elif not record.computed:
            blocking.append(_reason(f"sleeve_not_measured:{sleeve_id}"))
    missing = tuple(sorted(set(weights) - set(proven)))
    blocking.extend(_reason(f"sleeve_evidence_missing:{sleeve_id}") for sleeve_id in missing)

    portfolio_reasons: list[str] = []
    if governance:
        portfolio_reasons.append(_reason("portfolio_governance_not_advanced"))
    if missing or not all(record.computed for record in records):
        portfolio_reasons.append(_reason("portfolio_requires_every_covered_sleeve_measured"))
    portfolio_measurement: PaperPeakDistanceMeasurement | None = None
    if not portfolio_reasons:
        paths = {sleeve_id: cast(tuple[Fraction, ...], proven[sleeve_id].index) for sleeve_id in weights}
        portfolio_index = tuple(
            sum((weights[sleeve_id] * paths[sleeve_id][step] for sleeve_id in sorted(weights)), Fraction(0))
            for step in range(day_count + 1)
        )
        if portfolio_index[0] != _INITIAL_INDEX:
            raise _fail("portfolio_index_start_not_one")
        portfolio_measurement = _measure(portfolio_index)
        if portfolio_measurement is None:
            portfolio_reasons.append(_reason("portfolio_measurement_representation_bound_exceeded"))
    blocking.extend(portfolio_reasons)
    portfolio = PaperPortfolioDrawdownRecord(
        computed=portfolio_measurement is not None,
        performance_weights=policy.performance_weights,
        measurement=portfolio_measurement,
        reason_codes=tuple(sorted(set(portfolio_reasons))),
    )

    if governance:
        status = PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL
    elif blocking:
        status = PaperSleeveDrawdownStatus.NOT_COMPUTABLE
    else:
        status = PaperSleeveDrawdownStatus.READY
    seed = PaperSleeveDrawdownEvidence(
        schema_version=_SCHEMA_VERSION,
        status=status,
        ready=status is PaperSleeveDrawdownStatus.READY,
        drawdown_evidence_id=evidence_id,
        correlation_id=correlation_id,
        envelope_digest=envelope.envelope_digest,
        envelope_policy_digest=envelope.policy_digest,
        envelope_advances=envelope.advances,
        performance_path_policy_digest=policy.performance_path_policy_digest,
        performance_path_governed_digest=policy.policy_digest,
        performance_path_policy_advances=policy.advances,
        performance_path_rule_set_digest=policy.rule_set_digest,
        rebalancing_convention=policy.rebalancing_convention,
        window_start_ns=window_start,
        window_end_ns=window_end,
        day_count=day_count,
        sleeves=tuple(records),
        missing_sleeve_ids=missing,
        portfolio=portfolio,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST,
        reason_codes=tuple(sorted(set(governance + blocking))),
        drawdown_evidence_digest="",
    )
    return replace(seed, drawdown_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def paper_sleeve_drawdown_evidence_to_dict(evidence: PaperSleeveDrawdownEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def paper_sleeve_drawdown_evidence_digest(evidence: PaperSleeveDrawdownEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``drawdown_evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


def verify_paper_sleeve_drawdown_evidence(
    evidence: object, inputs: PaperSleeveDrawdownInputs
) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it from its exact inputs. Total: never raises."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not PaperSleeveDrawdownEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _to_payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _SELF_DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _to_payload(build_paper_sleeve_drawdown_evidence(inputs))
        codes: set[str] = set()
        if carried[_SELF_DIGEST_FIELD] != recomputed:
            codes.add(_reason("self_digest_mismatch"))
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
    "PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS",
    "PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST",
    "PaperPeakDistanceMeasurement",
    "PaperPortfolioDrawdownRecord",
    "PaperSleeveDrawdownEvidence",
    "PaperSleeveDrawdownEvidenceError",
    "PaperSleeveDrawdownInputs",
    "PaperSleeveDrawdownRecord",
    "PaperSleeveDrawdownSleeveInputs",
    "PaperSleeveDrawdownStatus",
    "build_paper_sleeve_drawdown_evidence",
    "measure_paper_peak_distance",
    "paper_sleeve_drawdown_evidence_digest",
    "paper_sleeve_drawdown_evidence_to_dict",
    "paper_sleeve_drawdown_rule_set",
    "verify_paper_sleeve_drawdown_evidence",
]
