"""RF-2 governed, preregistered regime feature and label policy (RF2_REGIME_FEATURE_POLICY_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-2), under the controller
structural authority ``RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1`` (closure
``RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1``).

A ``RegimeFeaturePolicy`` is the preregistration core of the regime filter, and POLICY EVIDENCE ONLY. It pins, before
any feature or label exists:
* the regime features;
* the ordered label rules;
* the closed label set;
* the UNLABELED cap;
* the RF-5 stability parameters.

It consumes no market data and labels nothing. A regime label is never an edge, a direction, an allocation, a
portfolio stop, a promotion or demotion, a kill or quarantine decision, an order, capital or readiness.

Governed structure. Every number is a caller-supplied GOVERNANCE input: nothing is defaulted, and this module holds no
production value.

* ``features``. Each one binds an id, a feature class, an EF-3 source series id, an instrument, ``lookback_days`` and
  its formula policy id. V1 supports exactly two classes:
  - ``F1_REALIZED_VOL`` with ``RF_F1_SIMPLE_RETURN_SAMPLE_STDDEV_V1``. It needs at least 3 closes, so that 2 returns
    give a sample variance.
  - ``F2_DRAWDOWN_STATE`` with ``RF_F2_ROLLING_PEAK_DISTANCE_V1``. It needs at least 2 closes, because one close is
    its own peak and measures zero by construction.

  The deferred classes ``F3_TREND_RANGE_PERSISTENCE``, ``F4_FUNDING_REGIME``, ``F5_LIQUIDITY_SPREAD`` and
  ``F6_LIQUIDATION_EVENT`` are refused explicitly; none is stubbed. Feature ids are unique (also case-insensitively),
  and so are the bindings (class, series, instrument, lookback).
* ``label_set``. The closed, human-governed label vocabulary. It is exactly the set of rule outputs and never contains
  the reserved system label ``UNLABELED``. Growing it is a new policy version and a new digest.
* ``label_rules``. Priorities are contiguous from 1 and evaluated ascending, and the first matching rule wins.
  - A rule binds its output label and one or more conjunctive predicates.
  - A predicate binds a policy feature, an operator (``LT``, ``LTE``, ``GT`` or ``GTE``) and a canonical scale-18
    threshold.
  - Every predicate reads a policy feature, and every feature is read by some predicate.
  - No two rules carry the same predicate set: the later one could never match.
  - A day that no rule matches is ``UNLABELED``.
* ``max_unlabeled_fraction`` and ``distribution_drift_cap``: canonical scale-18 in ``[0, 1]``, both bounds inclusive.
* ``stability_min_overlap_days`` and ``stability_min_asof_gap_days``: integers of at least 1.

Governance. ``policy_digest`` commits every governed value and the code-defined rule set
(``REGIME_FEATURE_POLICY_RULE_SET_DIGEST``). A ``RegimeFeaturePolicyApproval`` must commit the exact policy id,
version, ``policy_digest`` and rule-set digest. Changing any governed value changes ``policy_digest`` and makes every
earlier approval stale.

Outcomes:
* a missing, stale or non-matching approval leaves the policy ``NEEDS_GOVERNANCE_APPROVAL``;
* a ``TEST_ONLY_SYNTHETIC`` approval is surfaced through ``synthetic_test_approval_used`` and never advances;
* only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``;
* malformed, missing, out-of-domain, duplicate, deferred or inconsistent input raises ``RegimeFeaturePolicyError``, so
  an invalid policy is never represented.

``regime_feature_policy_digest`` is the self-digest over everything, approval included: the exact anchor RF-3, RF-4
and RF-5 pin. One assembly path serves the builder and the verifier reassembly, and ``verify_regime_feature_policy`` is
total.

Numeric policy ``RF_FIXED_SCALE18_DECIMAL_HALF_EVEN_P80_V1`` is methodology, not a governance value:
* canonical fixed scale-18 ASCII decimal text of at most 60 characters;
* exact ``Fraction`` comparison;
* exact half-even rendering of rationals (``regime_decimal_text``);
* for an irrational square root, a precision-80 ``ROUND_HALF_EVEN`` candidate from one explicit local context,
  adjudicated exactly (RF-3).

There is no float, and no IO, clock, randomness, network or environment access. The runtime ``crypto_core.regime``
package is never imported.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)

_SCHEMA_VERSION = "regime-feature-policy.v1"
_REASON_PREFIX = "regime_feature_policy"
_SELF_DIGEST_FIELD = "regime_feature_policy_digest"
_IDENTIFIER_EXTRA_CHARS = frozenset("-_./:")
_SERIES_EXTRA_CHARS = frozenset("_.:-")

REGIME_UNLABELED = "UNLABELED"
REGIME_NUMERIC_POLICY_ID = "RF_FIXED_SCALE18_DECIMAL_HALF_EVEN_P80_V1"
REGIME_F1_FORMULA_POLICY_ID = "RF_F1_SIMPLE_RETURN_SAMPLE_STDDEV_V1"
REGIME_F2_FORMULA_POLICY_ID = "RF_F2_ROLLING_PEAK_DISTANCE_V1"


class RegimeFeaturePolicyError(EdgeArtifactError):
    """Raised on malformed, missing, out-of-domain, duplicate, deferred or inconsistent policy input."""


class RegimeFeatureClass(str, Enum):
    """The V1 feature classes. The deferred classes F3 to F6 are refused, never represented."""

    F1_REALIZED_VOL = "F1_REALIZED_VOL"
    F2_DRAWDOWN_STATE = "F2_DRAWDOWN_STATE"


class RegimePredicateOperator(str, Enum):
    """``feature_value <operator> threshold``, decided by exact rational comparison."""

    LT = "LT"
    LTE = "LTE"
    GT = "GT"
    GTE = "GTE"


class RegimeFeaturePolicyApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` approvals exist for tests only: they are surfaced and never advance a policy."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_feature_policy_rules.v1",
    "contract_id": "RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1",
    "structural_authority_id": "RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1",
    "scope_rule_id": "preregistered_paper_regime_methodology_never_edge_direction_allocation_stop_or_execution.v1",
    # (feature class, its code-defined formula policy id, its structural minimum lookback in UTC days)
    "supported_feature_classes": (
        ("F1_REALIZED_VOL", REGIME_F1_FORMULA_POLICY_ID, 3),
        ("F2_DRAWDOWN_STATE", REGIME_F2_FORMULA_POLICY_ID, 2),
    ),
    "deferred_feature_classes": (
        "F3_TREND_RANGE_PERSISTENCE",
        "F4_FUNDING_REGIME",
        "F5_LIQUIDITY_SPREAD",
        "F6_LIQUIDATION_EVENT",
    ),
    "numeric_policy_id": REGIME_NUMERIC_POLICY_ID,
    "feature_rule_id": "unique_feature_ids_and_bindings_every_feature_read_by_some_predicate.v1",
    "lookback_rule_id": "f1_needs_three_closes_for_two_returns_and_a_sample_variance_f2_needs_two_closes.v1",
    "predicate_operators": tuple(operator.value for operator in RegimePredicateOperator),
    "predicate_rule_id": "conjunctive_predicates_on_policy_features_against_canonical_scale_18_thresholds.v1",
    "label_rule_id": "contiguous_priorities_from_one_ascending_first_matching_rule_wins_no_match_is_unlabeled.v1",
    "label_set_rule_id": "label_set_is_exactly_the_rule_outputs_unlabeled_reserved_growth_is_a_new_policy_digest.v1",
    "unlabeled_label_id": REGIME_UNLABELED,
    "fraction_rule_id": "max_unlabeled_fraction_and_drift_cap_canonical_scale_18_in_zero_one_both_inclusive.v1",
    "stability_rule_id": "stability_min_overlap_days_and_min_as_of_gap_days_at_least_one.v1",
    "governance_rule_id": "approval_commits_policy_id_version_policy_digest_and_rule_set_digest.v1",
    "gate_rule_id": "pass_iff_exact_matching_human_governance_approval_test_only_synthetic_never_advances.v1",
    "numeric_rule_id": "canonical_fixed_scale_decimal_text_exact_fraction_comparison_exact_half_even_no_float.v1",
    "decimal_scale": 18,
    "decimal_max_text_length": 60,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
    "max_identifier_length": 128,
    "max_instrument_length": 64,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
REGIME_FEATURE_POLICY_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_UNITS = 10**_SCALE
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]
_MAX_IDENTIFIER: int = _RULE_SET_V1["max_identifier_length"]  # type: ignore[assignment]
_MAX_INSTRUMENT: int = _RULE_SET_V1["max_instrument_length"]  # type: ignore[assignment]
_FORMULA_POLICY: dict[RegimeFeatureClass, str] = {
    RegimeFeatureClass(name): str(formula)
    for name, formula, _minimum in _RULE_SET_V1["supported_feature_classes"]  # type: ignore[attr-defined]
}
_MIN_LOOKBACK: dict[RegimeFeatureClass, int] = {
    RegimeFeatureClass(name): int(minimum)
    for name, _formula, minimum in _RULE_SET_V1["supported_feature_classes"]  # type: ignore[attr-defined]
}
_DEFERRED_CLASSES = frozenset(_RULE_SET_V1["deferred_feature_classes"])  # type: ignore[arg-type]


def regime_feature_policy_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-2 V1 rule set that ``REGIME_FEATURE_POLICY_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


# Structural non-claims shared by every RF-2 to RF-5 artifact: dataclass defaults no builder parameter can set,
# serialized into the digest and re-proven by reassembly.
REGIME_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("direction_signal_emitted", False),
    ("allocation_decided", False),
    ("portfolio_stop_authority", False),
    ("promotion_demotion_decided", False),
    ("kill_quarantine_decided", False),
    ("execution_authorized", False),
    ("order_created", False),
    ("real_orders_enabled", False),
    ("capital_allocated", False),
    ("real_capital_reserved", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("current_venue_facts_consumed", False),
    ("external_market_truth_proven", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("regime_filter_admitted", False),
    ("regime_conditioned_performance_proven", False),
)
_FLAG_NAMES = frozenset(name for name, _ in REGIME_NON_CLAIM_FLAGS)


@dataclass(frozen=True)
class RegimeFeatureDefinition:
    """One governed regime feature over the finalized daily closes of one EF-3 series and instrument."""

    feature_id: str
    feature_class: RegimeFeatureClass
    source_series_id: str
    instrument_id: str
    lookback_days: int
    formula_policy_id: str


@dataclass(frozen=True)
class RegimeLabelPredicate:
    """``feature_value <operator> threshold`` over one policy feature; the threshold is a governance value."""

    feature_id: str
    operator: RegimePredicateOperator
    threshold: str


@dataclass(frozen=True)
class RegimeLabelRule:
    """One governed label rule: its output label holds iff every predicate holds (conjunction)."""

    priority: int
    label_id: str
    predicates: tuple[RegimeLabelPredicate, ...]


@dataclass(frozen=True)
class RegimeFeaturePolicyApproval:
    """Governance approval of one exact policy: every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: RegimeFeaturePolicyApprovalKind
    approved_policy_id: str
    approved_policy_version: str
    approved_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class RegimeFeaturePolicy:
    """Immutable, digest-bound RF-2 regime feature and label policy. POLICY EVIDENCE ONLY."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    rule_set_id: str
    rule_set_digest: str
    numeric_policy_id: str
    unlabeled_label_id: str
    features: tuple[RegimeFeatureDefinition, ...]
    label_set: tuple[str, ...]
    label_rules: tuple[RegimeLabelRule, ...]
    max_unlabeled_fraction: str
    stability_min_overlap_days: int
    stability_min_asof_gap_days: int
    distribution_drift_cap: str
    policy_digest: str
    approval: RegimeFeaturePolicyApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    regime_feature_policy_digest: str
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


# Everything outside the governed methodology: the approval, the verdict it yields, and the two digests themselves.
_NON_POLICY_FIELDS = frozenset(
    {
        "gate_verdict",
        "advances",
        "policy_digest",
        "approval",
        "synthetic_test_approval_used",
        "verdict_reason_codes",
        "regime_feature_policy_digest",
    }
)
_RECORD_TYPES = frozenset({RegimeFeatureDefinition, RegimeLabelPredicate, RegimeLabelRule, RegimeFeaturePolicyApproval})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    RegimeFeatureDefinition: {"feature_class": RegimeFeatureClass},
    RegimeLabelPredicate: {"operator": RegimePredicateOperator},
    RegimeFeaturePolicyApproval: {"approval_kind": RegimeFeaturePolicyApprovalKind},
    RegimeFeaturePolicy: {"gate_verdict": EdgeGateVerdict},
}


# --- exact numbers --------------------------------------------------------------------------------------------------


def _ascii_digits(text: str) -> bool:
    return text != "" and all("0" <= char <= "9" for char in text)


def _decimal_is_canonical(value: object) -> bool:
    """Canonical ASCII fixed scale-18 decimal text within the 60-character representation bound."""

    if type(value) is not str or len(value) > _MAX_DECIMAL_TEXT or not value.isascii():
        return False
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if dot != "." or len(fraction) != _SCALE:
        return False
    if not _ascii_digits(integer) or not _ascii_digits(fraction):
        return False
    if integer != "0" and integer.startswith("0"):
        return False
    if negative and integer == "0" and fraction.strip("0") == "":
        return False
    return True


def regime_decimal_value(value: object) -> Fraction | None:
    """The exact value of canonical fixed scale-18 decimal text (at most 60 characters); None for anything else."""

    return Fraction(value) if _decimal_is_canonical(value) else None  # type: ignore[arg-type]


def regime_decimal_text(value: Fraction) -> str | None:
    """The exact half-even rounding of a rational to canonical scale-18 text; None beyond the 60-character bound.

    The rounding is decided by integer arithmetic on the exact value, so no digit is lost and nothing is rounded twice.
    """

    if type(value) is not Fraction:
        return None
    scaled = value * _UNITS
    units, remainder = divmod(scaled.numerator, scaled.denominator)
    if 2 * remainder > scaled.denominator or (2 * remainder == scaled.denominator and units % 2 == 1):
        units += 1
    negative = units < 0
    magnitude = -units if negative else units
    # The length bound is checked on the integer before any text exists, so no oversized integer is ever rendered.
    if magnitude >= 10 ** (_MAX_DECIMAL_TEXT - 1 - int(negative)):
        return None
    whole, fraction = divmod(magnitude, _UNITS)
    return f"{'-' if negative and magnitude else ''}{whole}.{fraction:0{_SCALE}d}"


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> RegimeFeaturePolicyError:
    return RegimeFeaturePolicyError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


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


def _require_identifier(value: object, field_name: str) -> str:
    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail(f"{field_name}_invalid")
    if not value[0].isalnum() or any(not (char.isalnum() or char in _IDENTIFIER_EXTRA_CHARS) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_series_id(value: object) -> str:
    """An EF-3 series id: the exact token grammar EF-3 accepts, so no policy names a series EF-3 could never hold."""

    if type(value) is not str or value == "" or len(value) > _MAX_IDENTIFIER or not value.isascii():
        raise _fail("feature_source_series_id_invalid")
    if not value[0].isalnum() or any(
        not (char.islower() or char.isdigit() or char in _SERIES_EXTRA_CHARS) for char in value
    ):
        raise _fail("feature_source_series_id_invalid")
    return _require_text(value, "feature_source_series_id")


def _require_instrument(value: object) -> str:
    """An instrument id in the EF-3 instrument grammar."""

    if type(value) is not str or value == "" or len(value) > _MAX_INSTRUMENT or not value.isascii():
        raise _fail("feature_instrument_id_invalid")
    if not value[0].isalnum() or any(not (char.isalnum() or char in _IDENTIFIER_EXTRA_CHARS) for char in value):
        raise _fail("feature_instrument_id_invalid")
    return _require_text(value, "feature_instrument_id")


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str and value in {member.value for member in enum_cls}:
        return enum_cls(value)
    raise _fail(f"{field_name}_invalid")


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    if value < minimum:
        raise _fail(f"{field_name}_below_minimum")
    return value


def _require_threshold(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("label_predicate_threshold_invalid")
    return value  # type: ignore[return-value]


def _require_unit_fraction(value: object, field_name: str) -> str:
    number = regime_decimal_value(value)
    if number is None:
        raise _fail(f"{field_name}_invalid")
    if number < 0 or number > 1:
        raise _fail(f"{field_name}_out_of_domain")
    return value  # type: ignore[return-value]


def _snapshot(values: object, field_name: str) -> tuple[object, ...]:
    """Read a caller sequence exactly once into an immutable tuple; only an exact tuple or list is accepted."""

    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    return tuple(values)  # type: ignore[arg-type]


# --- governed structure ---------------------------------------------------------------------------------------------


def _require_feature_class(value: object) -> RegimeFeatureClass:
    if type(value) is RegimeFeatureClass:
        return value
    if type(value) is str:
        if value in _DEFERRED_CLASSES:
            raise _fail("feature_class_deferred_not_supported_in_v1")
        if value in {member.value for member in RegimeFeatureClass}:
            return RegimeFeatureClass(value)
    raise _fail("feature_class_invalid")


def _canonical_features(values: object) -> tuple[RegimeFeatureDefinition, ...]:
    items = _snapshot(values, "features")
    if not items:
        raise _fail("features_missing")
    by_id: dict[str, RegimeFeatureDefinition] = {}
    folded: set[str] = set()
    bindings: set[tuple[RegimeFeatureClass, str, str, int]] = set()
    for item in items:
        if type(item) is not RegimeFeatureDefinition:
            raise _fail("feature_malformed")
        feature_id = _require_identifier(item.feature_id, "feature_id")
        feature_class = _require_feature_class(item.feature_class)
        series_id = _require_series_id(item.source_series_id)
        instrument_id = _require_instrument(item.instrument_id)
        lookback = _require_int(item.lookback_days, "feature_lookback_days", minimum=_MIN_LOOKBACK[feature_class])
        formula = _require_text(item.formula_policy_id, "feature_formula_policy_id")
        if formula != _FORMULA_POLICY[feature_class]:
            raise _fail("feature_formula_policy_mismatch")
        if feature_id.lower() in folded:
            raise _fail("feature_id_duplicate")
        binding = (feature_class, series_id, instrument_id, lookback)
        if binding in bindings:
            raise _fail("feature_binding_duplicate")
        folded.add(feature_id.lower())
        bindings.add(binding)
        by_id[feature_id] = RegimeFeatureDefinition(
            feature_id=feature_id,
            feature_class=feature_class,
            source_series_id=series_id,
            instrument_id=instrument_id,
            lookback_days=lookback,
            formula_policy_id=formula,
        )
    return tuple(by_id[feature_id] for feature_id in sorted(by_id))


def _canonical_label_set(values: object) -> tuple[str, ...]:
    items = _snapshot(values, "label_set")
    if not items:
        raise _fail("label_set_missing")
    labels: dict[str, str] = {}
    for item in items:
        label = _require_identifier(item, "label_set_member")
        if label.upper() == REGIME_UNLABELED:
            raise _fail("label_set_reserved_unlabeled")
        if label.lower() in labels:
            raise _fail("label_set_duplicate")
        labels[label.lower()] = label
    return tuple(sorted(labels.values()))


def _canonical_predicates(values: object, feature_ids: frozenset[str]) -> tuple[RegimeLabelPredicate, ...]:
    items = _snapshot(values, "label_predicates")
    if not items:
        raise _fail("label_predicates_missing")
    predicates: dict[tuple[str, str, Fraction], RegimeLabelPredicate] = {}
    for item in items:
        if type(item) is not RegimeLabelPredicate:
            raise _fail("label_predicate_malformed")
        feature_id = _require_identifier(item.feature_id, "label_predicate_feature_id")
        if feature_id not in feature_ids:
            raise _fail("label_predicate_feature_unknown")
        operator = _require_member(item.operator, RegimePredicateOperator, "label_predicate_operator")
        threshold = _require_threshold(item.threshold)
        key = (feature_id, operator.value, Fraction(threshold))
        if key in predicates:
            raise _fail("label_predicate_duplicate")
        predicates[key] = RegimeLabelPredicate(
            feature_id=feature_id,
            operator=operator,  # type: ignore[arg-type]
            threshold=threshold,
        )
    return tuple(predicates[key] for key in sorted(predicates))


def _canonical_rules(
    values: object, features: Sequence[RegimeFeatureDefinition], label_set: Sequence[str]
) -> tuple[RegimeLabelRule, ...]:
    items = _snapshot(values, "label_rules")
    if not items:
        raise _fail("label_rules_missing")
    feature_ids = frozenset(feature.feature_id for feature in features)
    by_priority: dict[int, RegimeLabelRule] = {}
    for item in items:
        if type(item) is not RegimeLabelRule:
            raise _fail("label_rule_malformed")
        priority = _require_int(item.priority, "label_rule_priority", minimum=1)
        label = _require_identifier(item.label_id, "label_rule_label_id")
        if label.upper() == REGIME_UNLABELED:
            raise _fail("label_rule_label_reserved_unlabeled")
        if label not in label_set:
            raise _fail("label_rule_label_not_in_label_set")
        predicates = _canonical_predicates(item.predicates, feature_ids)
        if priority in by_priority:
            raise _fail("label_rule_priority_duplicate")
        by_priority[priority] = RegimeLabelRule(priority=priority, label_id=label, predicates=predicates)
    ordered = tuple(by_priority[priority] for priority in sorted(by_priority))
    if [rule.priority for rule in ordered] != list(range(1, len(ordered) + 1)):
        raise _fail("label_rule_priorities_not_contiguous_from_one")
    predicate_sets = [rule.predicates for rule in ordered]
    if len(set(predicate_sets)) != len(predicate_sets):
        raise _fail("label_rule_predicates_duplicate")
    if {rule.label_id for rule in ordered} != set(label_set):
        raise _fail("label_set_member_without_rule")
    if {predicate.feature_id for rule in ordered for predicate in rule.predicates} != feature_ids:
        raise _fail("feature_not_read_by_any_rule")
    return ordered


# --- governance approval --------------------------------------------------------------------------------------------


def _canonical_approval(approval: object) -> RegimeFeaturePolicyApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not RegimeFeaturePolicyApproval:
        raise _fail("governance_approval_malformed")
    return RegimeFeaturePolicyApproval(
        approval_reference=_require_text(approval.approval_reference, "governance_approval_reference"),
        approval_digest=_require_hex64(approval.approval_digest, "governance_approval_digest"),
        approval_kind=_require_member(  # type: ignore[arg-type]
            approval.approval_kind, RegimeFeaturePolicyApprovalKind, "governance_approval_kind"
        ),
        approved_policy_id=_require_text(approval.approved_policy_id, "governance_approved_policy_id"),
        approved_policy_version=_require_text(approval.approved_policy_version, "governance_approved_policy_version"),
        approved_policy_digest=_require_hex64(approval.approved_policy_digest, "governance_approved_policy_digest"),
        approved_rule_set_digest=_require_hex64(
            approval.approved_rule_set_digest, "governance_approved_rule_set_digest"
        ),
    )


def _governance_reasons(approval: RegimeFeaturePolicyApproval | None, committed: Mapping[str, str]) -> list[str]:
    if approval is None:
        return [_reason("governance_approval_missing")]
    reasons = [
        _reason(f"governance_approval_{name}_mismatch")
        for name, value in committed.items()
        if getattr(approval, f"approved_{name}") != value
    ]
    if approval.approval_kind is RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC:
        reasons.append(_reason("governance_approval_test_only_synthetic"))
    return reasons


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


def _policy_digest(payload: Mapping[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({name: value for name, value in payload.items() if name not in _NON_POLICY_FIELDS})
    )


# --- policy assembly ------------------------------------------------------------------------------------------------


def _assemble_policy(
    *,
    policy_id: object,
    policy_version: object,
    features: object,
    label_set: object,
    label_rules: object,
    max_unlabeled_fraction: object,
    stability_min_overlap_days: object,
    stability_min_asof_gap_days: object,
    distribution_drift_cap: object,
    approval: object,
) -> RegimeFeaturePolicy:
    """The one policy assembly path, shared by the builder and verifier reassembly."""

    policy_id = _require_text(policy_id, "policy_id")
    policy_version = _require_text(policy_version, "policy_version")
    canonical_features = _canonical_features(features)
    canonical_labels = _canonical_label_set(label_set)
    rules = _canonical_rules(label_rules, canonical_features, canonical_labels)
    unlabeled_cap = _require_unit_fraction(max_unlabeled_fraction, "max_unlabeled_fraction")
    drift_cap = _require_unit_fraction(distribution_drift_cap, "distribution_drift_cap")
    min_overlap = _require_int(stability_min_overlap_days, "stability_min_overlap_days", minimum=1)
    min_gap = _require_int(stability_min_asof_gap_days, "stability_min_asof_gap_days", minimum=1)
    approval_record = _canonical_approval(approval)

    seed = RegimeFeaturePolicy(
        schema_version=_SCHEMA_VERSION,
        gate_verdict=EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        advances=False,
        policy_id=policy_id,
        policy_version=policy_version,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_FEATURE_POLICY_RULE_SET_DIGEST,
        numeric_policy_id=REGIME_NUMERIC_POLICY_ID,
        unlabeled_label_id=REGIME_UNLABELED,
        features=canonical_features,
        label_set=canonical_labels,
        label_rules=rules,
        max_unlabeled_fraction=unlabeled_cap,
        stability_min_overlap_days=min_overlap,
        stability_min_asof_gap_days=min_gap,
        distribution_drift_cap=drift_cap,
        policy_digest="",
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=(),
        regime_feature_policy_digest="",
    )
    policy_digest = _policy_digest(_to_payload(seed))
    committed = {
        "policy_id": policy_id,
        "policy_version": policy_version,
        "policy_digest": policy_digest,
        "rule_set_digest": REGIME_FEATURE_POLICY_RULE_SET_DIGEST,
    }
    needs_governance = _governance_reasons(approval_record, committed)
    verdict = resolve_edge_gate_verdict([], [], needs_governance)
    governed = replace(
        seed,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        policy_digest=policy_digest,
        verdict_reason_codes=_sorted_unique(needs_governance),
    )
    return replace(
        governed, regime_feature_policy_digest=edge_payload_digest(_to_payload(governed), _SELF_DIGEST_FIELD)
    )


def build_regime_feature_policy(
    *,
    policy_id: str,
    policy_version: str,
    features: Sequence[RegimeFeatureDefinition],
    label_set: Sequence[str],
    label_rules: Sequence[RegimeLabelRule],
    max_unlabeled_fraction: str,
    stability_min_overlap_days: int,
    stability_min_asof_gap_days: int,
    distribution_drift_cap: str,
    approval: RegimeFeaturePolicyApproval | None,
) -> RegimeFeaturePolicy:
    """Build the governed policy; every governed value is explicit (there are no defaults).

    Malformed, missing, out-of-domain, duplicate, deferred or inconsistent input, or a malformed approval, raises
    ``RegimeFeaturePolicyError``. A missing, non-matching or ``TEST_ONLY_SYNTHETIC`` approval yields
    ``NEEDS_GOVERNANCE_APPROVAL``; only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS`` and ``advances``.
    Inputs are read once and never mutated.
    """

    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        features=features,
        label_set=label_set,
        label_rules=label_rules,
        max_unlabeled_fraction=max_unlabeled_fraction,
        stability_min_overlap_days=stability_min_overlap_days,
        stability_min_asof_gap_days=stability_min_asof_gap_days,
        distribution_drift_cap=distribution_drift_cap,
        approval=approval,
    )


def regime_feature_policy_to_dict(policy: RegimeFeaturePolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a policy, including its self-digest."""

    return _to_payload(policy)


def regime_feature_policy_digest(policy: RegimeFeaturePolicy) -> str:
    """Recompute the canonical policy self-digest, excluding only ``regime_feature_policy_digest``."""

    return edge_payload_digest(_to_payload(policy), _SELF_DIGEST_FIELD)


# --- strict parsing -------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail("payload_field_malformed")
    return value


def _as_decimal(value: object) -> str:
    if not _decimal_is_canonical(value):
        raise _fail("payload_field_malformed")
    return value  # type: ignore[return-value]


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_optional(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return None if value is None else _parse_exact(cls, value, converters)

    return convert


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


_FEATURE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "feature_class": _as_enum(RegimeFeatureClass),
    "lookback_days": _as_int,
}
_PREDICATE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "operator": _as_enum(RegimePredicateOperator),
    "threshold": _as_decimal,
}
_RULE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "priority": _as_int,
    "predicates": _as_records(RegimeLabelPredicate, _PREDICATE_CONVERTERS),
}
_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(RegimeFeaturePolicyApprovalKind),
}
_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "features": _as_records(RegimeFeatureDefinition, _FEATURE_CONVERTERS),
    "label_set": _as_str_tuple,
    "label_rules": _as_records(RegimeLabelRule, _RULE_CONVERTERS),
    "max_unlabeled_fraction": _as_decimal,
    "stability_min_overlap_days": _as_int,
    "stability_min_asof_gap_days": _as_int,
    "distribution_drift_cap": _as_decimal,
    "approval": _as_optional(RegimeFeaturePolicyApproval, _APPROVAL_CONVERTERS),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def regime_feature_policy_from_payload(payload: object) -> RegimeFeaturePolicy:
    """Strictly reconstruct a policy from its serialized payload (exact fields, types and domains; no proof)."""

    return _parse_exact(RegimeFeaturePolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def regime_feature_policy_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a policy snapshot."""

    try:
        regime_feature_policy_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_policy(policy: object) -> RegimeFeaturePolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        features=policy.features,  # type: ignore[attr-defined]
        label_set=policy.label_set,  # type: ignore[attr-defined]
        label_rules=policy.label_rules,  # type: ignore[attr-defined]
        max_unlabeled_fraction=policy.max_unlabeled_fraction,  # type: ignore[attr-defined]
        stability_min_overlap_days=policy.stability_min_overlap_days,  # type: ignore[attr-defined]
        stability_min_asof_gap_days=policy.stability_min_asof_gap_days,  # type: ignore[attr-defined]
        distribution_drift_cap=policy.distribution_drift_cap,  # type: ignore[attr-defined]
        approval=policy.approval,  # type: ignore[attr-defined]
    )


def verify_regime_feature_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a policy by strict parse, self-digest recomputation and full reassembly. Total: never raises."""

    return verify_edge_artifact_total(
        policy,
        cls=RegimeFeaturePolicy,
        to_payload=_to_payload,
        parse_payload=regime_feature_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "REGIME_F1_FORMULA_POLICY_ID",
    "REGIME_F2_FORMULA_POLICY_ID",
    "REGIME_FEATURE_POLICY_RULE_SET_DIGEST",
    "REGIME_NON_CLAIM_FLAGS",
    "REGIME_NUMERIC_POLICY_ID",
    "REGIME_UNLABELED",
    "RegimeFeatureClass",
    "RegimeFeatureDefinition",
    "RegimeFeaturePolicy",
    "RegimeFeaturePolicyApproval",
    "RegimeFeaturePolicyApprovalKind",
    "RegimeFeaturePolicyError",
    "RegimeLabelPredicate",
    "RegimeLabelRule",
    "RegimePredicateOperator",
    "build_regime_feature_policy",
    "regime_decimal_text",
    "regime_decimal_value",
    "regime_feature_policy_digest",
    "regime_feature_policy_from_payload",
    "regime_feature_policy_payload_is_well_formed",
    "regime_feature_policy_rule_set",
    "regime_feature_policy_to_dict",
    "verify_regime_feature_policy",
]
