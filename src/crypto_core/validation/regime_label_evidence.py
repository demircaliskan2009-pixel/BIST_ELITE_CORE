"""RF-4 prior-day-close regime label evidence (RF4_REGIME_LABEL_EVIDENCE_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-4), under the controller
structural authority ``RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1`` (closure
``RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1``).

RF-4 labels every UTC day of an RF-3 feature window with the exact governed RF-2 label rules. It re-proves both inputs
independently:
* the RF-2 policy, through its total verifier;
* the RF-3 evidence, rebuilt from its exact inputs and canonically equal.

Both must bind the same exact policy (self-digest).

Prior-day-close discipline. ``label(D)`` reads only the RF-3 records of day ``D``. RF-3 already guarantees that those
read only closes of days before ``D``, available and finalized by ``start(D)``. RF-4 never reads an observation, a later
feature day or a neighbouring day: there is no interpolation, forward fill or next-available substitution.

Rules. If ANY policy feature is unavailable on ``D``, ``D`` is ``UNLABELED`` with every missing feature named.
Otherwise the rules are evaluated in ascending priority, and the first rule whose conjunctive predicates all hold
gives the label. A predicate compares the PUBLISHED scale-18 RF-3 value with its scale-18 threshold by exact
``Fraction`` comparison (``LT``, ``LTE``, ``GT``, ``GTE``). When no rule matches, ``D`` is ``UNLABELED`` (reason
``no_rule_matched``).

UNLABELED cap. Every day of the window is labelled exactly once, and no day is ever dropped from the denominator. The
exact ``unlabeled_fraction`` is ``unlabeled_days / label_days``. It passes when ``fraction <= max_unlabeled_fraction``
(equality passes); above the cap, the evidence ``FAIL``s and never advances.

Counts are published over the closed vocabulary: the sorted policy label set, then ``UNLABELED``, every member
included, zero or not.

Status: ``FAIL`` on a cap breach, over ``NEEDS_GOVERNANCE_APPROVAL`` for a policy without exact human governance, over
``PASS``. Only ``PASS`` advances. Malformed input and every provenance defect raise ``RegimeLabelEvidenceError``.
``verify_regime_label_evidence`` rebuilds from the exact inputs and is total.

Paper evidence only: a label is never an edge, a direction, an allocation, a stop, a promotion or demotion, a kill, an
order, capital or readiness. No float, and no IO, clock, randomness, network or environment access. The runtime
``crypto_core.regime`` package is never imported.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import TypeVar, cast

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    REGIME_UNLABELED,
    RegimeFeaturePolicy,
    RegimeLabelRule,
    RegimePredicateOperator,
    regime_decimal_value,
    verify_regime_feature_policy,
)
from crypto_core.validation.regime_feature_series_evidence import (
    RegimeFeatureRecord,
    RegimeFeatureSeriesEvidence,
    RegimeFeatureSeriesInputs,
    build_regime_feature_series_evidence,
    regime_feature_series_evidence_to_dict,
)

_T = TypeVar("_T")
_PREFIX = "regime_label_evidence"
_SCHEMA = "regime-label-evidence.v1"
_DIGEST_FIELD = "label_evidence_digest"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_label_evidence_rules.v1",
    "contract_id": "RF2_RF5_CORE_PIT_REGIME_EVIDENCE_SPINE_V1",
    "structural_authority_id": "RF_CORE_FORMULA_LABEL_AND_STABILITY_POLICY_V1",
    "scope_rule_id": "paper_regime_labels_never_edge_direction_allocation_stop_promotion_kill_or_execution.v1",
    "input_rule_id": "exact_rf2_policy_reproven_rf3_rebuilt_from_its_inputs_canonically_equal_same_policy.v1",
    "label_window_rule_id": "every_rf3_feature_day_labelled_exactly_once_no_day_dropped.v1",
    "prior_day_close_rule_id": "label_d_reads_only_the_rf3_records_of_d_whose_windows_end_d_minus_1_final_by_start_of_d.v1",
    "missing_feature_rule_id": "any_unavailable_policy_feature_makes_the_day_unlabeled_never_filled_or_carried.v1",
    "rule_evaluation_id": "ascending_priority_first_rule_whose_conjunctive_predicates_all_hold_wins.v1",
    "no_match_rule_id": "no_matching_rule_is_unlabeled.v1",
    "comparison_rule_id": "published_scale_18_feature_value_against_scale_18_threshold_exact_fraction.v1",
    "unlabeled_cap_rule_id": "exact_unlabeled_days_over_every_label_day_at_most_cap_passes_equality_passes.v1",
    "vocabulary_rule_id": "sorted_policy_label_set_then_unlabeled_every_member_counted_zero_included.v1",
    "status_rule_id": "fail_on_cap_breach_over_needs_governance_approval_over_pass.v1",
    "unlabeled_label_id": REGIME_UNLABELED,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
REGIME_LABEL_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]


def regime_label_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-4 V1 rule set that ``REGIME_LABEL_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class RegimeLabelEvidenceError(EdgeArtifactError):
    """A malformed input or any provenance defect: an invalid label evidence is never represented."""


@dataclass(frozen=True)
class RegimeLabelInputs:
    """Everything RF-4 consumes; consumers re-prove an evidence by rebuilding it from exactly these."""

    label_evidence_id: str
    correlation_id: str
    policy: RegimeFeaturePolicy
    feature_series_inputs: RegimeFeatureSeriesInputs
    feature_series: RegimeFeatureSeriesEvidence


@dataclass(frozen=True)
class RegimeDayLabel:
    """The label of one UTC day: a governed label with its rule, or ``UNLABELED`` with every reason."""

    day_index: int
    label_id: str
    matched_rule_priority: int | None
    unlabeled_reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class RegimeLabelCount:
    """How many days of the window carry one vocabulary member."""

    label_id: str
    day_count: int


@dataclass(frozen=True)
class RegimeLabelEvidence:
    """Immutable, digest-bound RF-4 regime label evidence. Paper evidence only."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    label_evidence_id: str
    correlation_id: str
    policy_id: str
    policy_version: str
    regime_feature_policy_digest: str
    policy_governed: bool
    feature_series_digest: str
    as_of_ns: int
    first_label_day_index: int
    last_label_day_index: int
    label_day_count: int
    unlabeled_day_count: int
    unlabeled_fraction: str
    max_unlabeled_fraction: str
    unlabeled_within_cap: bool
    labels: tuple[RegimeDayLabel, ...]
    label_counts: tuple[RegimeLabelCount, ...]
    verdict_reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    label_evidence_digest: str
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


REGIME_LABEL_NON_CLAIM_FLAGS = REGIME_NON_CLAIM_FLAGS
_RECORD_TYPES = frozenset({RegimeDayLabel, RegimeLabelCount})
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {RegimeLabelEvidence: {"gate_verdict": EdgeGateVerdict}}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> RegimeLabelEvidenceError:
    return RegimeLabelEvidenceError(_reason(code))


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


def _canonically_equal(supplied: object, rebuilt: object, to_dict: Callable[..., dict]) -> bool:
    if type(supplied) is not type(rebuilt):
        return False
    try:
        return edge_canonical_json(to_dict(supplied)) == edge_canonical_json(to_dict(rebuilt))
    except Exception:  # noqa: BLE001 - an artifact that cannot serialize canonically is not the reconstruction
        return False


def _rebuild(code: str, builder: Callable[..., _T], *args: object) -> _T:
    """One accepted public builder call; any failure is a provenance defect of this evidence."""

    try:
        return builder(*args)
    except Exception as exc:  # noqa: BLE001 - every reconstruction failure fails closed here
        raise _fail(f"{code}_reconstruction_failed") from exc


# --- the labels -----------------------------------------------------------------------------------------------------


def _holds(value: Fraction, operator: RegimePredicateOperator, threshold: Fraction) -> bool:
    if operator is RegimePredicateOperator.LT:
        return value < threshold
    if operator is RegimePredicateOperator.LTE:
        return value <= threshold
    if operator is RegimePredicateOperator.GT:
        return value > threshold
    return value >= threshold


def _first_match(rules: Sequence[RegimeLabelRule], values: Mapping[str, Fraction]) -> RegimeLabelRule | None:
    """Ascending priority; the first rule whose conjunctive predicates all hold wins."""

    for rule in rules:
        if all(
            _holds(values[predicate.feature_id], predicate.operator, Fraction(predicate.threshold))
            for predicate in rule.predicates
        ):
            return rule
    return None


def _day_label(
    day: int, policy: RegimeFeaturePolicy, records: Mapping[tuple[str, int], RegimeFeatureRecord]
) -> RegimeDayLabel:
    """``label(D)`` from the RF-3 records of ``D`` alone; any unavailable policy feature makes ``D`` UNLABELED."""

    values: dict[str, Fraction] = {}
    missing: list[str] = []
    for feature in policy.features:
        record = records.get((feature.feature_id, day))
        if record is None:
            raise _fail("feature_record_missing")
        value = regime_decimal_value(record.value) if record.available else None
        if value is None:
            missing.append(_reason(f"required_feature_unavailable:{feature.feature_id}"))
        else:
            values[feature.feature_id] = value
    if missing:
        return RegimeDayLabel(day, REGIME_UNLABELED, None, _sorted_unique(missing))
    rule = _first_match(policy.label_rules, values)
    if rule is None:
        return RegimeDayLabel(day, REGIME_UNLABELED, None, (_reason("no_rule_matched"),))
    return RegimeDayLabel(day, rule.label_id, rule.priority, ())


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


# --- the evidence ---------------------------------------------------------------------------------------------------


def _require_policy(value: object) -> RegimeFeaturePolicy:
    _require_exact(value, RegimeFeaturePolicy, "policy")
    if not verify_regime_feature_policy(value).intact:
        raise _fail("policy_not_intact")
    return cast(RegimeFeaturePolicy, value)


def _prove_feature_series(inputs: object, evidence: object, policy: RegimeFeaturePolicy) -> RegimeFeatureSeriesEvidence:
    """RF-3 rebuilt from its exact inputs, canonically equal to the supplied evidence and bound to the same policy."""

    _require_exact(inputs, RegimeFeatureSeriesInputs, "feature_series_inputs")
    _require_exact(evidence, RegimeFeatureSeriesEvidence, "feature_series")
    rebuilt = _rebuild("feature_series", build_regime_feature_series_evidence, inputs)
    if not _canonically_equal(evidence, rebuilt, regime_feature_series_evidence_to_dict):
        raise _fail("feature_series_not_reconstructed")
    if rebuilt.regime_feature_policy_digest != policy.regime_feature_policy_digest:
        raise _fail("feature_series_policy_mismatch")
    return rebuilt


def build_regime_label_evidence(inputs: RegimeLabelInputs) -> RegimeLabelEvidence:
    """Label every day of the RF-3 window from the exact, re-proven policy and feature series.

    Malformed input and every provenance defect raise ``RegimeLabelEvidenceError``. Inputs are never mutated.
    """

    _require_exact(inputs, RegimeLabelInputs, "inputs")
    label_evidence_id = _require_text(inputs.label_evidence_id, "label_evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    policy = _require_policy(inputs.policy)
    series = _prove_feature_series(inputs.feature_series_inputs, inputs.feature_series, policy)

    records = {(record.feature_id, record.target_day_index): record for record in series.records}
    first, last = series.first_feature_day_index, series.last_feature_day_index
    labels = tuple(_day_label(day, policy, records) for day in range(first, last + 1))
    vocabulary = (*policy.label_set, REGIME_UNLABELED)
    counts = tuple(
        RegimeLabelCount(label_id, sum(1 for label in labels if label.label_id == label_id)) for label_id in vocabulary
    )
    unlabeled = sum(1 for label in labels if label.label_id == REGIME_UNLABELED)
    fraction = Fraction(unlabeled, len(labels))
    cap = regime_decimal_value(policy.max_unlabeled_fraction)
    if cap is None:
        raise _fail("policy_max_unlabeled_fraction_invalid")
    within = fraction <= cap
    fail = [] if within else [_reason("unlabeled_fraction_above_cap")]
    governance = [] if policy.advances else [_reason("policy_needs_governance_approval")]
    verdict = resolve_edge_gate_verdict(fail, [], governance)

    seed = RegimeLabelEvidence(
        schema_version=_SCHEMA,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        label_evidence_id=label_evidence_id,
        correlation_id=correlation_id,
        policy_id=policy.policy_id,
        policy_version=policy.policy_version,
        regime_feature_policy_digest=policy.regime_feature_policy_digest,
        policy_governed=policy.advances,
        feature_series_digest=series.feature_series_digest,
        as_of_ns=series.as_of_ns,
        first_label_day_index=first,
        last_label_day_index=last,
        label_day_count=len(labels),
        unlabeled_day_count=unlabeled,
        unlabeled_fraction=f"{fraction.numerator}/{fraction.denominator}",
        max_unlabeled_fraction=policy.max_unlabeled_fraction,
        unlabeled_within_cap=within,
        labels=labels,
        label_counts=counts,
        verdict_reason_codes=_sorted_unique(fail + governance),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_LABEL_RULE_SET_DIGEST,
        label_evidence_digest="",
    )
    return replace(seed, label_evidence_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def regime_label_evidence_to_dict(evidence: RegimeLabelEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an evidence, its self-digest included."""

    return _payload(evidence)


def regime_label_evidence_digest(evidence: RegimeLabelEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``label_evidence_digest``."""

    return edge_payload_digest(_payload(evidence), _DIGEST_FIELD)


def verify_regime_label_evidence(evidence: object, inputs: RegimeLabelInputs) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not RegimeLabelEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_regime_label_evidence(inputs))
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
    "REGIME_LABEL_NON_CLAIM_FLAGS",
    "REGIME_LABEL_RULE_SET_DIGEST",
    "RegimeDayLabel",
    "RegimeLabelCount",
    "RegimeLabelEvidence",
    "RegimeLabelEvidenceError",
    "RegimeLabelInputs",
    "build_regime_label_evidence",
    "regime_label_evidence_digest",
    "regime_label_evidence_to_dict",
    "regime_label_rule_set",
    "verify_regime_label_evidence",
]
