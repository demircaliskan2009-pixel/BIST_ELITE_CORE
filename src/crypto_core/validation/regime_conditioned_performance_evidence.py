"""RF-7 regime-conditioned paper performance evidence (RF7_REGIME_CONDITIONED_PERFORMANCE_EVIDENCE_V1).

Design authority: ``docs/crypto_core/regime_volatility_filter_design.md`` section 1 (RF-7) and section 9.

RF-7 is a deterministic, point-in-time, descriptive REPORT: the paper performance of ONE sleeve stratified by the
labels of ONE admitted regime filter. It measures; it never decides, ranks, selects, allocates, promotes, kills or
trades, and it proves no significance, edge or profitability.

Authority, every element re-proven before anything is measured (a defect raises
``RegimeConditionedPerformanceError``):

* RF-6: the ``RegimeFilterAdmissionDecision`` is re-proven through ``verify_regime_filter_admission_decision`` from its
  exact inputs, and its recomputed digest must equal the caller's anchor. That rebuild re-proves the exact RF-2
  policy, the EF-5 preregistration, both RF-4 label evidences, both RF-3 feature series and the RF-5 stability world,
  so every label, policy and coverage fact RF-7 reads comes from that proven world, never from a caller string;
* RG-3: the ``PaperSleevePerformanceEvidence`` is re-proven through ``verify_paper_sleeve_performance_evidence`` from
  its exact producer inputs, which rebuilds the valuation and the daily-return series, and its recomputed digest must
  equal the caller's anchor. Only its rebuilt ``READY`` daily returns are ever measured;
* EF-5: the preregistration RF-6 consumed is read back from its canonical snapshot, and its recomputed digest must
  equal the digest RF-6 bound;
* the measurement policy (``RegimeConditionedPerformancePolicy``): re-proven through its total verifier.

Identity, resolved only from supported provenance:

* correlation: the report's correlation must equal the RF-6 world's (RF-6 already binds one correlation across EF-5,
  RF-5, both RF-4 and both RF-3). The RG-3 correlation is a separate sleeve-world identifier: it is recorded and never
  used as attribution;
* strategy: every episode of the re-proven RG-3 valuation carries the exact ``StrategySpec`` its signal bridge was
  rebuilt from. Each spec's recomputed public digest must equal the EF-5 ``strategy_spec_digest``; one other spec is a
  cross-world contradiction and raises. With no episode the attribution is unproven (False), never assumed;
* market: the RG-3 market must lie in the EF-5 pinned instrument universe, or the build raises;
* candidate paper admission (EF-7) and the trading variant are NOT consumed: ``candidate_paper_admission_proven`` and
  ``variant_attribution_proven`` stay structurally False.

Status, first match wins (a modelled outcome, never an error):

1. ``FILTER_NOT_ADMITTED`` when RF-6 is neither a ``PASS`` that admits the filter nor pending governance (``FAIL``,
   ``NEEDS_EXTERNAL_FACTS`` or any other verdict): authorization is positive, never the absence of a known refusal;
2. ``NEEDS_GOVERNANCE_APPROVAL`` when RF-6 or RG-3 is pending governance, or the measurement policy lacks an exact
   ``HUMAN_GOVERNANCE`` approval (a missing, stale or ``TEST_ONLY_SYNTHETIC`` approval never advances);
3. ``NOT_COMPUTABLE`` when RG-3 is otherwise not ``READY``, or no trusted regime day exists;
4. ``READY``. Only ``READY`` carries the day join and the strata; every other state carries identities, statuses and
   reasons, never a measurement.

Join (``RF7_EXACT_UTC_DAY_JOIN_V1``). The RG-3 window must lie on the UTC-day grid: its start is UTC-day aligned, it
spans exactly ``day_count`` days and carries one return per day. Return ``i`` belongs to UTC day
``window_start_ns // 86_400_000_000_000 + i``, and RF-4 indexes its labels by the same absolute UTC day. A label of
day D is known at the start of D (prior-day close) and the return of D is realized during D, so no label is ever later
than the return it conditions. Nothing is shifted, interpolated, carried forward or inferred from a timezone.

Coverage. Every window day is classified, and the four classes sum to the window:

* ``TRUSTED``: inside the RF-5 proven overlap with a governed label: the only days any stratum measures;
* ``UNLABELED``: inside the overlap but ``UNLABELED``: counted, never a stratum;
* ``STABILITY_UNPROVEN``: labeled by only one RF-4 evidence (outside the overlap): no no-repaint proof, so excluded;
* ``LABEL_NOT_COVERED``: no label at all: excluded.

Label days outside the RG-3 window are counted separately.

Strata. One stratum per governed label, an empty one included, so no stratum disappears. A stratum with fewer
trusted days than the governed ``min_observations_per_stratum`` is ``insufficient_sample``: its counts are published,
its metrics never are. Otherwise:

* mean: the exact ``Fraction`` mean of its daily returns, rendered half-even at scale 18;
* paper Sharpe (the accepted ``paper_sharpe_evidence`` methodology): risk-free zero, sample standard deviation with
  ``n - 1``, annualized by ``sqrt(365)``, and exact zero variance fail-closed. Both ratios are a signed square root of
  an exact rational (``mean^2 / variance`` and ``365 * mean^2 / variance``), adjudicated half-even at scale 18 by
  integer arithmetic: no float, no ``decimal`` context, nothing rounded twice;
* drawdown (``RF7_EPISODE_PEAK_DISTANCE_V1``): an episode is a maximal run of consecutive trusted days with that label.
  Each episode is its own chain-linked index ``1, (1 + r_1), (1 + r_1)(1 + r_2), ...``, measured by the accepted RG-4
  ``measure_paper_peak_distance``. The stratum publishes the maximum episode peak distance (exact reduced ``p/q``),
  the episode count and the longest episode. Days of different episodes are never concatenated into one path, so a
  decline spanning a regime switch or a gap is split, and a decline that began before an episode is not measured. An
  episode index beyond the committed 4096-character bound (the RG-4 index grammar) makes the drawdown
  ``NOT_REPRESENTABLE``; it is decided on integers before any text is rendered.

Multiple testing. The EF-5 variant ledger cardinality and digest, the registered regime filter count and set digest,
their product (the preregistered variant-filter pairs) and the reported stratum count are published with provenance.
No correction, threshold or significance is computed.

Non-claims: no chronological ordering of registration versus returns, no profitability, edge, statistical
significance, strategy causation, candidate paper admission, variant attribution or episode-set completeness, and no
direction, allocation, stop, promotion, kill, quarantine, execution, order, capital, readiness or live authority.
``verify_regime_conditioned_performance_evidence`` rebuilds a report from its exact inputs and is total. No float, no
``decimal`` context, and no IO, clock, randomness, network or environment access. The runtime ``crypto_core.regime``
package is never imported, and no EF-6 or RG-5 schema is touched.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from typing import cast

from crypto_core.strategy.spec import strategy_spec_digest
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    edge_leakage_bias_evidence_digest,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidenceError,
    measure_paper_peak_distance,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    verify_paper_sleeve_performance_evidence,
)
from crypto_core.validation.regime_feature_policy import (
    REGIME_NON_CLAIM_FLAGS,
    REGIME_UNLABELED,
    RegimeFeaturePolicyApprovalKind,
    regime_decimal_text,
)
from crypto_core.validation.regime_filter_admission_decision import (
    RegimeFilterAdmissionDecision,
    RegimeFilterAdmissionInputs,
    verify_regime_filter_admission_decision,
)

_PREFIX = "regime_conditioned_performance_evidence"
_SCHEMA = "regime-conditioned-performance-evidence.v1"
_POLICY_SCHEMA = "regime-conditioned-performance-policy.v1"
_DIGEST_FIELD = "regime_conditioned_performance_digest"
_POLICY_DIGEST_FIELD = "regime_conditioned_performance_policy_digest"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "regime_conditioned_performance_evidence_rules.v1",
    "contract_id": "RF7_REGIME_CONDITIONED_PERFORMANCE_EVIDENCE_V1",
    "scope_rule_id": "descriptive_paper_regime_stratified_performance_report_never_a_decision_or_significance.v1",
    "admission_rule_id": "rf6_reproven_by_its_verifier_and_exact_anchor_only_pass_authorizes_measurement.v1",
    "performance_rule_id": "rg3_reproven_by_its_verifier_and_exact_anchor_only_ready_daily_returns_measured.v1",
    "preregistration_rule_id": "ef5_read_back_from_its_canonical_snapshot_digest_equal_to_the_rf6_binding.v1",
    "attribution_rule_id": "every_rg3_episode_strategy_spec_digest_equals_the_ef5_spec_digest_else_contradiction.v1",
    "market_rule_id": "rg3_market_in_the_ef5_pinned_instrument_universe.v1",
    "correlation_rule_id": "report_correlation_equals_the_rf6_world_rg3_correlation_recorded_never_attribution.v1",
    "join_rule_id": "RF7_EXACT_UTC_DAY_JOIN_V1",
    "coverage_rule_id": "trusted_days_are_rf5_overlap_days_with_a_governed_label_every_window_day_classified.v1",
    "status_rule_id": "filter_not_admitted_then_needs_governance_approval_then_not_computable_then_ready.v1",
    "sample_rule_id": "governed_min_observations_per_stratum_below_is_insufficient_sample_metrics_withheld.v1",
    "mean_rule_id": "exact_fraction_mean_rendered_half_even_scale_18.v1",
    "sharpe_rule_id": "paper_sharpe_risk_free_zero_sample_n_minus_1_sqrt_365_exact_zero_variance_fail_closed.v1",
    "sharpe_rounding_rule_id": "signed_square_root_of_an_exact_rational_adjudicated_half_even_scale_18_by_integers.v1",
    "drawdown_rule_id": "RF7_EPISODE_PEAK_DISTANCE_V1",
    "multiple_testing_rule_id": "ef5_variant_and_regime_filter_counts_published_no_correction_no_threshold.v1",
    "risk_free_policy_id": "constant_zero_daily_review_only.v1",
    "stddev_policy_id": "sample_stddev_n_minus_1.v1",
    "annualization_factor": 365,
    "minimum_observations_floor": 2,
    "decimal_scale": 18,
    "decimal_rounding": "ROUND_HALF_EVEN",
    "decimal_max_text_length": 60,
    "return_max_text_length": 4096,
    "episode_index_max_text_length": 4096,
    "utc_day_ns": 86_400_000_000_000,
    "max_wire_integer": 9223372036854775807,
    "max_text_length": 256,
}
REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
_ANNUALIZATION: int = _RULE_SET_V1["annualization_factor"]  # type: ignore[assignment]
_MIN_FLOOR: int = _RULE_SET_V1["minimum_observations_floor"]  # type: ignore[assignment]
_SCALE: int = _RULE_SET_V1["decimal_scale"]  # type: ignore[assignment]
_UNITS = 10**_SCALE
_MAX_DECIMAL_TEXT: int = _RULE_SET_V1["decimal_max_text_length"]  # type: ignore[assignment]
_MAX_RETURN_TEXT: int = _RULE_SET_V1["return_max_text_length"]  # type: ignore[assignment]
_MAX_INDEX_TEXT: int = _RULE_SET_V1["episode_index_max_text_length"]  # type: ignore[assignment]
_MAX_INDEX_UNITS = 10**_MAX_INDEX_TEXT
_DAY_NS: int = _RULE_SET_V1["utc_day_ns"]  # type: ignore[assignment]
_MAX_WIRE_INT: int = _RULE_SET_V1["max_wire_integer"]  # type: ignore[assignment]
_MAX_TEXT: int = _RULE_SET_V1["max_text_length"]  # type: ignore[assignment]


def regime_conditioned_performance_rule_set() -> dict[str, object]:
    """A fresh copy of the RF-7 V1 rule set that ``REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST`` commits."""

    return dict(_RULE_SET_V1)


class RegimeConditionedPerformanceError(EdgeArtifactError):
    """Raised on malformed input, a failed upstream re-proof, or an identity, attribution or geometry defect."""


class RegimeConditionedPerformanceStatus(str, Enum):
    READY = "READY"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"
    FILTER_NOT_ADMITTED = "FILTER_NOT_ADMITTED"


class RegimeConditionedDayClass(str, Enum):
    TRUSTED = "TRUSTED"
    UNLABELED = "UNLABELED"
    STABILITY_UNPROVEN = "STABILITY_UNPROVEN"
    LABEL_NOT_COVERED = "LABEL_NOT_COVERED"


class RegimeStratumMetricStatus(str, Enum):
    COMPUTED = "COMPUTED"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    ZERO_VARIANCE = "ZERO_VARIANCE"
    NOT_REPRESENTABLE = "NOT_REPRESENTABLE"


# --- the governed measurement policy --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeConditionedPerformanceApproval:
    """Governance approval of one exact measurement policy: every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: RegimeFeaturePolicyApprovalKind
    approved_policy_id: str
    approved_policy_version: str
    approved_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class RegimeConditionedPerformancePolicy:
    """The governed RF-7 sample floor. Governance evidence only; it holds no default and measures nothing."""

    schema_version: str
    gate_verdict: EdgeGateVerdict
    advances: bool
    policy_id: str
    policy_version: str
    rule_set_id: str
    rule_set_digest: str
    min_observations_per_stratum: int
    policy_digest: str
    approval: RegimeConditionedPerformanceApproval | None
    synthetic_test_approval_used: bool
    verdict_reason_codes: tuple[str, ...]
    regime_conditioned_performance_policy_digest: str
    paper_only: bool = True


# --- the report -----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class RegimeStratumReturnMeasurement:
    """Mean and paper Sharpe of one exact sample of daily returns (``measure_regime_stratum_returns``)."""

    observation_count: int
    mean_daily_return: str | None
    sharpe_status: RegimeStratumMetricStatus
    paper_sharpe_daily: str | None
    paper_sharpe_annualized: str | None


@dataclass(frozen=True)
class RegimeConditionedDay:
    """One RG-3 window day: its absolute UTC day, its coverage class, its label (``""`` when none) and its return."""

    day_index: int
    day_class: RegimeConditionedDayClass
    label_id: str
    daily_return: str


@dataclass(frozen=True)
class RegimeStratumPerformance:
    """One governed label's trusted days; metrics are published only when the sample is sufficient."""

    label_id: str
    observation_count: int
    insufficient_sample: bool
    mean_daily_return: str | None
    sharpe_status: RegimeStratumMetricStatus
    paper_sharpe_daily: str | None
    paper_sharpe_annualized: str | None
    episode_count: int
    longest_episode_day_count: int
    drawdown_status: RegimeStratumMetricStatus
    max_episode_peak_distance: str | None


@dataclass(frozen=True)
class RegimeConditionedPerformanceInputs:
    """Everything RF-7 consumes; consumers re-prove a report by rebuilding it from exactly these."""

    report_id: str
    correlation_id: str
    measurement_policy: RegimeConditionedPerformancePolicy
    admission_inputs: RegimeFilterAdmissionInputs
    admission: RegimeFilterAdmissionDecision
    expected_admission_digest: str
    performance_inputs: PaperSleevePerformanceInputs
    performance: PaperSleevePerformanceEvidence
    expected_performance_digest: str


REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in REGIME_NON_CLAIM_FLAGS if flag[0] != "regime_filter_admitted"),
    ("statistical_significance_proven", False),
    ("multiple_testing_correction_applied", False),
    ("strategy_causation_proven", False),
    ("chronological_ordering_proven", False),
    ("candidate_paper_admission_proven", False),
    ("variant_attribution_proven", False),
    ("episode_set_completeness_proven", False),
)


@dataclass(frozen=True)
class RegimeConditionedPerformanceEvidence:
    """Immutable, digest-bound RF-7 report. Descriptive paper measurement only."""

    schema_version: str
    status: RegimeConditionedPerformanceStatus
    ready: bool
    report_id: str
    correlation_id: str
    filter_admission_id: str
    filter_admission_digest: str
    filter_admission_verdict: str
    filter_admitted: bool
    regime_feature_policy_id: str
    regime_feature_policy_version: str
    regime_feature_policy_digest: str
    label_set: tuple[str, ...]
    stability_evidence_digest: str
    stability_status: str
    earlier_as_of_ns: int
    later_as_of_ns: int
    stability_overlap_first_day_index: int | None
    stability_overlap_last_day_index: int | None
    earlier_label_evidence_digest: str
    later_label_evidence_digest: str
    preregistration_digest: str
    candidate_strategy_id: str
    strategy_spec_digest: str
    pinned_instrument_universe: tuple[str, ...]
    variant_ledger_digest: str
    ledger_variant_count: int
    regime_filter_set_digest: str
    ledger_regime_filter_count: int
    preregistered_variant_filter_pair_count: int
    reported_stratum_count: int
    sleeve_performance_digest: str
    sleeve_performance_status: str
    sleeve_id: str
    market_symbol: str
    sleeve_correlation_id: str
    window_start_ns: int
    window_end_ns: int
    window_day_count: int
    sleeve_episode_count: int
    sleeve_episode_strategy_spec_digests: tuple[str, ...]
    strategy_spec_attribution_proven: bool
    measurement_policy_id: str
    measurement_policy_version: str
    measurement_policy_digest: str
    measurement_policy_governed: bool
    min_observations_per_stratum: int
    days: tuple[RegimeConditionedDay, ...]
    trusted_day_count: int
    unlabeled_day_count: int
    stability_unproven_day_count: int
    label_not_covered_day_count: int
    label_days_outside_window_count: int
    strata: tuple[RegimeStratumPerformance, ...]
    reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    regime_conditioned_performance_digest: str
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
    regime_conditioned_performance_proven: bool = False
    statistical_significance_proven: bool = False
    multiple_testing_correction_applied: bool = False
    strategy_causation_proven: bool = False
    chronological_ordering_proven: bool = False
    candidate_paper_admission_proven: bool = False
    variant_attribution_proven: bool = False
    episode_set_completeness_proven: bool = False


_FLAG_NAMES = frozenset(name for name, _ in REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS)
_RECORD_TYPES = frozenset(
    {
        RegimeConditionedPerformanceApproval,
        RegimeConditionedDay,
        RegimeStratumPerformance,
        RegimeStratumReturnMeasurement,
    }
)
_ENUM_FIELDS: dict[type, dict[str, type[Enum]]] = {
    RegimeConditionedPerformanceApproval: {"approval_kind": RegimeFeaturePolicyApprovalKind},
    RegimeConditionedPerformancePolicy: {"gate_verdict": EdgeGateVerdict},
    RegimeConditionedDay: {"day_class": RegimeConditionedDayClass},
    RegimeStratumPerformance: {
        "sharpe_status": RegimeStratumMetricStatus,
        "drawdown_status": RegimeStratumMetricStatus,
    },
    RegimeStratumReturnMeasurement: {"sharpe_status": RegimeStratumMetricStatus},
    RegimeConditionedPerformanceEvidence: {"status": RegimeConditionedPerformanceStatus},
}


# --- exact input discipline -----------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> RegimeConditionedPerformanceError:
    return RegimeConditionedPerformanceError(_reason(code))


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


def _require_hex64(value: object, name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{name}_invalid")
    return cast(str, value)


def _require_member(value: object, enum_cls: type[Enum], name: str) -> Enum:
    if type(value) is enum_cls:
        return cast(Enum, value)
    if type(value) is str:
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise _fail(f"{name}_invalid") from exc
    raise _fail(f"{name}_invalid")


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


def _as_optional(convert: Callable[[object], object]) -> Callable[[object], object]:
    return lambda value: None if value is None else convert(value)


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


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


# --- the measurement policy -----------------------------------------------------------------------------------------


def _canonical_approval(approval: object) -> RegimeConditionedPerformanceApproval | None:
    """Structural validation only: whether the commitments MATCH is decided at assembly."""

    if approval is None:
        return None
    if type(approval) is not RegimeConditionedPerformanceApproval:
        raise _fail("governance_approval_malformed")
    return RegimeConditionedPerformanceApproval(
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


def _assemble_policy(
    *, policy_id: object, policy_version: object, min_observations_per_stratum: object, approval: object
) -> RegimeConditionedPerformancePolicy:
    """The one policy assembly path, shared by the builder and the verifier reassembly."""

    policy_id = _require_text(policy_id, "policy_id")
    policy_version = _require_text(policy_version, "policy_version")
    minimum = min_observations_per_stratum
    if type(minimum) is not int or minimum < _MIN_FLOOR or minimum > _MAX_WIRE_INT:
        raise _fail("min_observations_per_stratum_invalid")
    approval_record = _canonical_approval(approval)
    content = {
        "schema_version": _POLICY_SCHEMA,
        "policy_id": policy_id,
        "policy_version": policy_version,
        "rule_set_id": _RULE_SET_ID,
        "rule_set_digest": REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
        "min_observations_per_stratum": minimum,
    }
    policy_digest = edge_sha256_text(edge_canonical_json(content))
    reasons: list[str] = []
    if approval_record is None:
        reasons.append(_reason("governance_approval_missing"))
    else:
        committed = {
            "policy_id": policy_id,
            "policy_version": policy_version,
            "policy_digest": policy_digest,
            "rule_set_digest": REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
        }
        reasons.extend(
            _reason(f"governance_approval_{name}_mismatch")
            for name, value in committed.items()
            if getattr(approval_record, f"approved_{name}") != value
        )
        if approval_record.approval_kind is RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC:
            reasons.append(_reason("governance_approval_test_only_synthetic"))
    verdict = resolve_edge_gate_verdict([], [], reasons)
    seed = RegimeConditionedPerformancePolicy(
        schema_version=_POLICY_SCHEMA,
        gate_verdict=verdict,
        advances=verdict is EdgeGateVerdict.PASS,
        policy_id=policy_id,
        policy_version=policy_version,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
        min_observations_per_stratum=minimum,
        policy_digest=policy_digest,
        approval=approval_record,
        synthetic_test_approval_used=approval_record is not None
        and approval_record.approval_kind is RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC,
        verdict_reason_codes=_sorted_unique(reasons),
        regime_conditioned_performance_policy_digest="",
    )
    return replace(
        seed, regime_conditioned_performance_policy_digest=edge_payload_digest(_payload(seed), _POLICY_DIGEST_FIELD)
    )


def build_regime_conditioned_performance_policy(
    *,
    policy_id: str,
    policy_version: str,
    min_observations_per_stratum: int,
    approval: RegimeConditionedPerformanceApproval | None,
) -> RegimeConditionedPerformancePolicy:
    """Build the governed RF-7 sample floor; nothing is defaulted.

    ``min_observations_per_stratum`` is a governance value of at least 2 (a sample variance needs two observations).
    Malformed input raises ``RegimeConditionedPerformanceError``. A missing, non-matching or ``TEST_ONLY_SYNTHETIC``
    approval yields ``NEEDS_GOVERNANCE_APPROVAL``; only an exact ``HUMAN_GOVERNANCE`` approval yields ``PASS``.
    """

    return _assemble_policy(
        policy_id=policy_id,
        policy_version=policy_version,
        min_observations_per_stratum=min_observations_per_stratum,
        approval=approval,
    )


def regime_conditioned_performance_policy_to_dict(policy: RegimeConditionedPerformancePolicy) -> dict[str, object]:
    """Canonical JSON-ready mapping of a measurement policy, including its self-digest."""

    return _payload(policy)


def regime_conditioned_performance_policy_digest(policy: RegimeConditionedPerformancePolicy) -> str:
    """Recompute the canonical policy self-digest, excluding only its self-digest field."""

    return edge_payload_digest(_payload(policy), _POLICY_DIGEST_FIELD)


_APPROVAL_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approval_kind": _as_enum(RegimeFeaturePolicyApprovalKind),
}
_POLICY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "min_observations_per_stratum": _as_int,
    "approval": _as_optional(
        lambda value: _parse_exact(RegimeConditionedPerformanceApproval, value, _APPROVAL_CONVERTERS)
    ),
    "synthetic_test_approval_used": _as_bool,
    "verdict_reason_codes": _as_str_tuple,
    "paper_only": _as_bool,
}


def regime_conditioned_performance_policy_from_payload(payload: object) -> RegimeConditionedPerformancePolicy:
    """Strictly reconstruct a measurement policy from its serialized payload (exact fields and types; no proof)."""

    return _parse_exact(RegimeConditionedPerformancePolicy, payload, _POLICY_CONVERTERS)  # type: ignore[return-value]


def _reassemble_policy(policy: object) -> RegimeConditionedPerformancePolicy:
    return _assemble_policy(
        policy_id=policy.policy_id,  # type: ignore[attr-defined]
        policy_version=policy.policy_version,  # type: ignore[attr-defined]
        min_observations_per_stratum=policy.min_observations_per_stratum,  # type: ignore[attr-defined]
        approval=policy.approval,  # type: ignore[attr-defined]
    )


def verify_regime_conditioned_performance_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-prove a measurement policy by strict parse, self-digest recomputation and reassembly. Total."""

    return verify_edge_artifact_total(
        policy,
        cls=RegimeConditionedPerformancePolicy,
        to_payload=_payload,
        parse_payload=regime_conditioned_performance_policy_from_payload,
        reassemble=_reassemble_policy,
        self_digest_field=_POLICY_DIGEST_FIELD,
        reason=_reason,
    )


# --- exact numbers --------------------------------------------------------------------------------------------------


def _parse_return(value: object) -> Fraction:
    """A canonical plain decimal return (no exponent, sign of zero, leading or trailing zero), else a defect.

    The 4096-character bound covers every return the accepted valuation renders (at most 4000 characters) and is the
    bound the accepted RG-4 consumer parses the same returns under, so an authentic return is never refused.
    """

    if type(value) is not str or value == "" or len(value) > _MAX_RETURN_TEXT or not value.isascii():
        raise _fail("daily_return_malformed")
    negative = value.startswith("-")
    integer, dot, fraction = (value[1:] if negative else value).partition(".")
    if not integer.isdigit() or (integer != "0" and integer.startswith("0")):
        raise _fail("daily_return_malformed")
    if dot and (not fraction.isdigit() or fraction.endswith("0")):
        raise _fail("daily_return_malformed")
    if negative and integer == "0" and not dot:
        raise _fail("daily_return_malformed")
    return Fraction(value)


def _integer_square_root(value: int) -> int:
    """``floor(sqrt(value))`` for a non-negative integer, by Newton's method on integers."""

    if value < 2:
        return value
    root = 1 << ((value.bit_length() + 1) // 2)
    while True:
        smaller = (root + value // root) // 2
        if smaller >= root:
            return root
        root = smaller


def _signed_root_text(sign_source: Fraction, square: Fraction) -> str | None:
    """``sign(sign_source) * sqrt(square)`` rendered half-even at scale 18, decided by exact integer arithmetic."""

    scaled = square * _UNITS * _UNITS
    units = _integer_square_root(scaled.numerator // scaled.denominator)
    boundary = (2 * units + 1) ** 2
    if 4 * scaled > boundary or (4 * scaled == boundary and units % 2 == 1):
        units += 1
    negative = sign_source < 0 and units > 0
    if units >= 10 ** (_MAX_DECIMAL_TEXT - 1 - int(negative)):
        return None
    whole, fraction = divmod(units, _UNITS)
    return f"{'-' if negative else ''}{whole}.{fraction:0{_SCALE}d}"


def _plain_decimal_text(value: Fraction) -> str | None:
    """The canonical plain decimal text of a positive terminating rational (the accepted RG-4 index grammar).

    None beyond the committed episode index bound. Scale and magnitude are decided on integers before any text exists,
    so no integer wider than the bound is ever rendered (the runtime refuses to render integers above 4300 digits).
    """

    denominator = value.denominator
    twos = (denominator & -denominator).bit_length() - 1
    rest, fives, chunk = denominator >> twos, 0, 5**64
    while rest % chunk == 0 and fives < _MAX_INDEX_TEXT:
        rest //= chunk
        fives += 64
    while rest % 5 == 0 and fives < _MAX_INDEX_TEXT:
        rest //= 5
        fives += 1
    scale = max(twos, fives)
    if scale >= _MAX_INDEX_TEXT:
        return None
    if rest != 1:
        raise _fail("index_not_terminating")
    units = value.numerator * 10**scale // value.denominator
    if units >= _MAX_INDEX_UNITS:
        return None
    whole, fraction = divmod(units, 10**scale)
    digits = f"{fraction:0{scale}d}".rstrip("0") if scale else ""
    return f"{whole}.{digits}" if digits else str(whole)


def measure_regime_stratum_returns(daily_returns: Sequence[str]) -> RegimeStratumReturnMeasurement:
    """Exact mean and paper Sharpe of one sample of canonical daily returns, without any sample floor.

    ``INSUFFICIENT_SAMPLE`` below two observations, ``ZERO_VARIANCE`` when every return is equal, and
    ``NOT_REPRESENTABLE`` when a published mean or ratio would exceed the 60-character bound. Malformed input raises.
    """

    if type(daily_returns) not in (tuple, list):
        raise _fail("daily_returns_malformed")
    values = [_parse_return(item) for item in cast(Sequence[object], daily_returns)]
    count = len(values)
    if count == 0:
        return RegimeStratumReturnMeasurement(0, None, RegimeStratumMetricStatus.INSUFFICIENT_SAMPLE, None, None)
    mean = sum(values, Fraction(0)) / count
    mean_text = regime_decimal_text(mean)
    if mean_text is None:
        return RegimeStratumReturnMeasurement(count, None, RegimeStratumMetricStatus.NOT_REPRESENTABLE, None, None)
    if count < _MIN_FLOOR:
        return RegimeStratumReturnMeasurement(
            count, mean_text, RegimeStratumMetricStatus.INSUFFICIENT_SAMPLE, None, None
        )
    variance = sum(((value - mean) ** 2 for value in values), Fraction(0)) / (count - 1)
    if variance == 0:
        return RegimeStratumReturnMeasurement(count, mean_text, RegimeStratumMetricStatus.ZERO_VARIANCE, None, None)
    daily = _signed_root_text(mean, mean * mean / variance)
    annualized = _signed_root_text(mean, _ANNUALIZATION * mean * mean / variance)
    if daily is None or annualized is None:
        return RegimeStratumReturnMeasurement(count, mean_text, RegimeStratumMetricStatus.NOT_REPRESENTABLE, None, None)
    return RegimeStratumReturnMeasurement(count, mean_text, RegimeStratumMetricStatus.COMPUTED, daily, annualized)


def _episode_peak_distance(returns: Sequence[Fraction]) -> Fraction | None:
    """The accepted RG-4 maximum peak distance of one episode's chain-linked index, re-based to 1; None when the
    index exceeds the committed representation bound (here, before rendering, or in the RG-4 measure)."""

    index, path = Fraction(1), ["1"]
    for value in returns:
        index *= 1 + value
        text = _plain_decimal_text(index)
        if text is None:
            return None
        path.append(text)
    try:
        measurement = measure_paper_peak_distance(path)
    except PaperSleeveDrawdownEvidenceError:
        return None
    return Fraction(measurement.max_peak_distance)


def _fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


# --- upstream authority ---------------------------------------------------------------------------------------------


def _require_policy(value: object) -> RegimeConditionedPerformancePolicy:
    _require_exact(value, RegimeConditionedPerformancePolicy, "measurement_policy")
    if not verify_regime_conditioned_performance_policy(value).intact:
        raise _fail("measurement_policy_not_intact")
    return cast(RegimeConditionedPerformancePolicy, value)


def _prove_admission(inputs: object, decision: object, anchor: object) -> RegimeFilterAdmissionDecision:
    _require_exact(inputs, RegimeFilterAdmissionInputs, "admission_inputs")
    _require_exact(decision, RegimeFilterAdmissionDecision, "admission")
    expected = _require_hex64(anchor, "expected_admission_digest")
    verification = verify_regime_filter_admission_decision(decision, cast(RegimeFilterAdmissionInputs, inputs))
    if not verification.intact:
        raise _fail("filter_admission_not_intact")
    if verification.recomputed_digest != expected:
        raise _fail("filter_admission_digest_mismatch")
    return cast(RegimeFilterAdmissionDecision, decision)


def _prove_performance(inputs: object, evidence: object, anchor: object) -> PaperSleevePerformanceEvidence:
    _require_exact(inputs, PaperSleevePerformanceInputs, "performance_inputs")
    _require_exact(evidence, PaperSleevePerformanceEvidence, "performance")
    expected = _require_hex64(anchor, "expected_performance_digest")
    verification = verify_paper_sleeve_performance_evidence(evidence, cast(PaperSleevePerformanceInputs, inputs))
    if not verification.intact:
        raise _fail("sleeve_performance_not_intact")
    if verification.recomputed_digest != expected:
        raise _fail("sleeve_performance_digest_mismatch")
    return cast(PaperSleevePerformanceEvidence, evidence)


def _read_preregistration(value: object, digest: str) -> EdgeLeakageBiasEvidence:
    """The EF-5 artifact RF-6 re-proved, read back from its canonical snapshot and bound to RF-6's digest."""

    try:
        snapshot_payload = edge_leakage_bias_evidence_to_dict(cast(EdgeLeakageBiasEvidence, value))
    except Exception as exc:  # noqa: BLE001 - an EF-5 object that cannot serialize is never authority
        raise _fail("preregistration_not_serializable") from exc
    binding = build_edge_authority_binding(
        snapshot_payload=snapshot_payload,
        expected_digest=digest,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=RegimeConditionedPerformanceError,
        code=_reason("preregistration"),
    )
    preregistration = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(binding))
    if edge_leakage_bias_evidence_digest(preregistration) != digest:
        raise _fail("preregistration_digest_mismatch")
    return preregistration


def _episode_spec_digests(inputs: PaperSleevePerformanceInputs) -> tuple[str, ...]:
    """The recomputed digest of every episode's source spec, in episode order (re-proven by the RG-3 rebuild)."""

    try:
        return tuple(strategy_spec_digest(item.strategy_spec) for item in inputs.valuation_inputs.episodes)
    except Exception as exc:  # noqa: BLE001 - an episode spec that cannot be digested is never attribution
        raise _fail("sleeve_episode_spec_unreadable") from exc


# --- the day join and the strata ------------------------------------------------------------------------------------


def _labels_by_day(labels: Sequence[object]) -> dict[int, str]:
    by_day: dict[int, str] = {}
    for label in labels:
        day, label_id = label.day_index, label.label_id  # type: ignore[attr-defined]
        if day in by_day:
            raise _fail("label_day_duplicate")
        by_day[day] = label_id
    return by_day


def _join_days(
    performance: PaperSleevePerformanceEvidence,
    earlier: Mapping[int, str],
    later: Mapping[int, str],
    overlap: range,
) -> tuple[tuple[RegimeConditionedDay, ...], int]:
    """Every window day, classified by exact UTC day identity, and the count of label days outside the window."""

    start, end, count = performance.window_start_ns, performance.window_end_ns, performance.day_count
    if start % _DAY_NS or end - start != count * _DAY_NS or len(performance.daily_returns) != count:
        raise _fail("sleeve_window_not_on_the_utc_day_grid")
    first_day = start // _DAY_NS
    window = range(first_day, first_day + count)
    days: list[RegimeConditionedDay] = []
    for offset, daily_return in enumerate(performance.daily_returns):
        day = first_day + offset
        if day in overlap:
            if day not in later:
                raise _fail("stability_overlap_day_without_a_label")
            label = later[day]
            day_class = (
                RegimeConditionedDayClass.UNLABELED
                if label == REGIME_UNLABELED
                else (RegimeConditionedDayClass.TRUSTED)
            )
        elif day in later or day in earlier:
            label = later.get(day, earlier.get(day, ""))
            day_class = RegimeConditionedDayClass.STABILITY_UNPROVEN
        else:
            label, day_class = "", RegimeConditionedDayClass.LABEL_NOT_COVERED
        days.append(RegimeConditionedDay(day, day_class, label, daily_return))
    outside = len({day for day in (*earlier, *later) if day not in window})
    return tuple(days), outside


def _stratum(label_id: str, days: Sequence[RegimeConditionedDay], minimum: int) -> RegimeStratumPerformance:
    """One governed label's trusted days: its episodes, and its metrics when the sample is sufficient."""

    members = [day for day in days if day.day_class is RegimeConditionedDayClass.TRUSTED and day.label_id == label_id]
    episodes: list[list[Fraction]] = []
    previous: int | None = None
    for day in members:
        value = _parse_return(day.daily_return)
        if previous is not None and day.day_index == previous + 1:
            episodes[-1].append(value)
        else:
            episodes.append([value])
        previous = day.day_index
    count, longest = len(members), max((len(episode) for episode in episodes), default=0)
    if count < minimum:
        insufficient = RegimeStratumMetricStatus.INSUFFICIENT_SAMPLE
        return RegimeStratumPerformance(
            label_id, count, True, None, insufficient, None, None, len(episodes), longest, insufficient, None
        )
    measurement = measure_regime_stratum_returns(tuple(day.daily_return for day in members))
    distances = [_episode_peak_distance(episode) for episode in episodes]
    if any(distance is None for distance in distances):
        drawdown_status, drawdown = RegimeStratumMetricStatus.NOT_REPRESENTABLE, None
    else:
        drawdown_status = RegimeStratumMetricStatus.COMPUTED
        drawdown = _fraction_text(max(cast(list[Fraction], distances)))
    return RegimeStratumPerformance(
        label_id=label_id,
        observation_count=count,
        insufficient_sample=False,
        mean_daily_return=measurement.mean_daily_return,
        sharpe_status=measurement.sharpe_status,
        paper_sharpe_daily=measurement.paper_sharpe_daily,
        paper_sharpe_annualized=measurement.paper_sharpe_annualized,
        episode_count=len(episodes),
        longest_episode_day_count=longest,
        drawdown_status=drawdown_status,
        max_episode_peak_distance=drawdown,
    )


# --- the report -----------------------------------------------------------------------------------------------------


def build_regime_conditioned_performance_evidence(
    inputs: RegimeConditionedPerformanceInputs,
) -> RegimeConditionedPerformanceEvidence:
    """Measure one sleeve's paper performance stratified by one admitted regime filter's trusted labels.

    Malformed input, a failed upstream re-proof, an anchor mismatch and every identity, attribution or geometry defect
    raise ``RegimeConditionedPerformanceError``. A filter that is not admitted, missing governance and an incomputable
    sleeve are modelled outcomes, never errors. Inputs are never mutated.
    """

    _require_exact(inputs, RegimeConditionedPerformanceInputs, "inputs")
    report_id = _require_text(inputs.report_id, "report_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    policy = _require_policy(inputs.measurement_policy)
    admission = _prove_admission(inputs.admission_inputs, inputs.admission, inputs.expected_admission_digest)
    performance = _prove_performance(inputs.performance_inputs, inputs.performance, inputs.expected_performance_digest)
    if admission.correlation_id != correlation_id:
        raise _fail("filter_admission_correlation_mismatch")
    world = inputs.admission_inputs
    preregistration = _read_preregistration(world.preregistration, admission.preregistration_digest)
    spec_digests = _episode_spec_digests(inputs.performance_inputs)
    if any(digest != preregistration.strategy_spec_digest for digest in spec_digests):
        raise _fail("sleeve_strategy_spec_contradicts_the_preregistration")
    if performance.market_symbol not in preregistration.pinned_instrument_universe:
        raise _fail("sleeve_market_outside_the_preregistered_universe")
    stability, rf2 = world.stability, world.policy

    not_admitted: list[str] = []
    pending: list[str] = []
    not_computable: list[str] = []
    # Authorization is positive: only an RF-6 PASS that admits the filter measures; every other verdict never does.
    if admission.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        pending.append(_reason("filter_admission_needs_governance_approval"))
    elif admission.gate_verdict is not EdgeGateVerdict.PASS or admission.regime_filter_admitted is not True:
        not_admitted.append(_reason(f"filter_not_admitted:{admission.gate_verdict.value}"))
    if performance.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL:
        pending.append(_reason("sleeve_performance_needs_governance_approval"))
    elif performance.status is not PaperSleevePerformanceStatus.READY or performance.ready is not True:
        not_computable.append(_reason("sleeve_performance_not_computable"))
    if not policy.advances:
        pending.append(_reason("measurement_policy_needs_governance_approval"))

    days: tuple[RegimeConditionedDay, ...] = ()
    outside = 0
    strata: tuple[RegimeStratumPerformance, ...] = ()
    if not not_admitted and not pending and not not_computable:
        first, last = stability.overlap_first_day_index, stability.overlap_last_day_index
        overlap = range(first, last + 1) if first is not None and last is not None else range(0)
        days, outside = _join_days(
            performance,
            _labels_by_day(world.stability_inputs.earlier_labels.labels),
            _labels_by_day(world.stability_inputs.later_labels.labels),
            overlap,
        )
        if not any(day.day_class is RegimeConditionedDayClass.TRUSTED for day in days):
            not_computable.append(_reason("no_trusted_regime_day"))
            days, outside = (), 0
        else:
            minimum = policy.min_observations_per_stratum
            strata = tuple(_stratum(label_id, days, minimum) for label_id in rf2.label_set)

    if not_admitted:
        status = RegimeConditionedPerformanceStatus.FILTER_NOT_ADMITTED
    elif pending:
        status = RegimeConditionedPerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    elif not_computable:
        status = RegimeConditionedPerformanceStatus.NOT_COMPUTABLE
    else:
        status = RegimeConditionedPerformanceStatus.READY
    count = dict.fromkeys(RegimeConditionedDayClass, 0)
    for day in days:
        count[day.day_class] += 1
    variants = preregistration.multiple_testing_count
    filters = len(preregistration.registered_regime_policy_digests)

    seed = RegimeConditionedPerformanceEvidence(
        schema_version=_SCHEMA,
        status=status,
        ready=status is RegimeConditionedPerformanceStatus.READY,
        report_id=report_id,
        correlation_id=correlation_id,
        filter_admission_id=admission.admission_id,
        filter_admission_digest=admission.regime_filter_admission_digest,
        filter_admission_verdict=admission.gate_verdict.value,
        filter_admitted=admission.regime_filter_admitted,
        regime_feature_policy_id=rf2.policy_id,
        regime_feature_policy_version=rf2.policy_version,
        regime_feature_policy_digest=rf2.regime_feature_policy_digest,
        label_set=rf2.label_set,
        stability_evidence_digest=stability.stability_evidence_digest,
        stability_status=stability.status.value,
        earlier_as_of_ns=stability.earlier_as_of_ns,
        later_as_of_ns=stability.later_as_of_ns,
        stability_overlap_first_day_index=stability.overlap_first_day_index,
        stability_overlap_last_day_index=stability.overlap_last_day_index,
        earlier_label_evidence_digest=stability.earlier_label_evidence_digest,
        later_label_evidence_digest=stability.later_label_evidence_digest,
        preregistration_digest=admission.preregistration_digest,
        candidate_strategy_id=preregistration.candidate_strategy_id,
        strategy_spec_digest=preregistration.strategy_spec_digest,
        pinned_instrument_universe=preregistration.pinned_instrument_universe,
        variant_ledger_digest=preregistration.variant_ledger_digest,
        ledger_variant_count=variants,
        regime_filter_set_digest=preregistration.regime_filter_set_digest,
        ledger_regime_filter_count=filters,
        preregistered_variant_filter_pair_count=variants * filters,
        reported_stratum_count=len(rf2.label_set),
        sleeve_performance_digest=performance.performance_evidence_digest,
        sleeve_performance_status=performance.status.value,
        sleeve_id=performance.sleeve_id,
        market_symbol=performance.market_symbol,
        sleeve_correlation_id=performance.correlation_id,
        window_start_ns=performance.window_start_ns,
        window_end_ns=performance.window_end_ns,
        window_day_count=performance.day_count,
        sleeve_episode_count=len(spec_digests),
        sleeve_episode_strategy_spec_digests=tuple(sorted(set(spec_digests))),
        strategy_spec_attribution_proven=bool(spec_digests),
        measurement_policy_id=policy.policy_id,
        measurement_policy_version=policy.policy_version,
        measurement_policy_digest=policy.regime_conditioned_performance_policy_digest,
        measurement_policy_governed=policy.advances,
        min_observations_per_stratum=policy.min_observations_per_stratum,
        days=days,
        trusted_day_count=count[RegimeConditionedDayClass.TRUSTED],
        unlabeled_day_count=count[RegimeConditionedDayClass.UNLABELED],
        stability_unproven_day_count=count[RegimeConditionedDayClass.STABILITY_UNPROVEN],
        label_not_covered_day_count=count[RegimeConditionedDayClass.LABEL_NOT_COVERED],
        label_days_outside_window_count=outside,
        strata=strata,
        reason_codes=_sorted_unique([*not_admitted, *pending, *not_computable]),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
        regime_conditioned_performance_digest="",
    )
    return replace(seed, regime_conditioned_performance_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def regime_conditioned_performance_evidence_to_dict(
    evidence: RegimeConditionedPerformanceEvidence,
) -> dict[str, object]:
    """Canonical JSON-ready mapping of a report, its self-digest included."""

    return _payload(evidence)


def regime_conditioned_performance_evidence_digest(evidence: RegimeConditionedPerformanceEvidence) -> str:
    """Recompute the canonical report digest, excluding only ``regime_conditioned_performance_digest``."""

    return edge_payload_digest(_payload(evidence), _DIGEST_FIELD)


_DAY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "day_index": _as_int,
    "day_class": _as_enum(RegimeConditionedDayClass),
}
_STRATUM_CONVERTERS: dict[str, Callable[[object], object]] = {
    "observation_count": _as_int,
    "insufficient_sample": _as_bool,
    "mean_daily_return": _as_optional(_as_str),
    "sharpe_status": _as_enum(RegimeStratumMetricStatus),
    "paper_sharpe_daily": _as_optional(_as_str),
    "paper_sharpe_annualized": _as_optional(_as_str),
    "episode_count": _as_int,
    "longest_episode_day_count": _as_int,
    "drawdown_status": _as_enum(RegimeStratumMetricStatus),
    "max_episode_peak_distance": _as_optional(_as_str),
}
_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(RegimeConditionedPerformanceStatus),
    "ready": _as_bool,
    "filter_admitted": _as_bool,
    "label_set": _as_str_tuple,
    "earlier_as_of_ns": _as_int,
    "later_as_of_ns": _as_int,
    "stability_overlap_first_day_index": _as_optional(_as_int),
    "stability_overlap_last_day_index": _as_optional(_as_int),
    "pinned_instrument_universe": _as_str_tuple,
    "ledger_variant_count": _as_int,
    "ledger_regime_filter_count": _as_int,
    "preregistered_variant_filter_pair_count": _as_int,
    "reported_stratum_count": _as_int,
    "window_start_ns": _as_int,
    "window_end_ns": _as_int,
    "window_day_count": _as_int,
    "sleeve_episode_count": _as_int,
    "sleeve_episode_strategy_spec_digests": _as_str_tuple,
    "strategy_spec_attribution_proven": _as_bool,
    "measurement_policy_governed": _as_bool,
    "min_observations_per_stratum": _as_int,
    "days": _as_records(RegimeConditionedDay, _DAY_CONVERTERS),
    "trusted_day_count": _as_int,
    "unlabeled_day_count": _as_int,
    "stability_unproven_day_count": _as_int,
    "label_not_covered_day_count": _as_int,
    "label_days_outside_window_count": _as_int,
    "strata": _as_records(RegimeStratumPerformance, _STRATUM_CONVERTERS),
    "reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def regime_conditioned_performance_evidence_from_payload(payload: object) -> RegimeConditionedPerformanceEvidence:
    """Strictly reconstruct a report from its serialized payload (exact fields and types; no proof).

    Reconstruction is not verification: consumers re-prove a report with
    ``verify_regime_conditioned_performance_evidence`` and its exact inputs.
    """

    return _parse_exact(RegimeConditionedPerformanceEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def regime_conditioned_performance_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for a report snapshot a later consumer binds."""

    try:
        regime_conditioned_performance_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def verify_regime_conditioned_performance_evidence(
    evidence: object, inputs: RegimeConditionedPerformanceInputs
) -> EdgeEvidenceVerification:
    """Re-prove a report by rebuilding it, every upstream re-proof included, from its exact inputs. Total."""

    stage = "evidence_type_invalid"
    try:
        if type(evidence) is not RegimeConditionedPerformanceEvidence:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = "evidence_serialization_failed"
        carried = _payload(evidence)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, _DIGEST_FIELD)
        stage = "evidence_reconstruction_failed"
        expected = _payload(build_regime_conditioned_performance_evidence(inputs))
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
    "REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS",
    "REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST",
    "RegimeConditionedDay",
    "RegimeConditionedDayClass",
    "RegimeConditionedPerformanceApproval",
    "RegimeConditionedPerformanceError",
    "RegimeConditionedPerformanceEvidence",
    "RegimeConditionedPerformanceInputs",
    "RegimeConditionedPerformancePolicy",
    "RegimeConditionedPerformanceStatus",
    "RegimeStratumMetricStatus",
    "RegimeStratumPerformance",
    "RegimeStratumReturnMeasurement",
    "build_regime_conditioned_performance_evidence",
    "build_regime_conditioned_performance_policy",
    "measure_regime_stratum_returns",
    "regime_conditioned_performance_evidence_digest",
    "regime_conditioned_performance_evidence_from_payload",
    "regime_conditioned_performance_evidence_payload_is_well_formed",
    "regime_conditioned_performance_evidence_to_dict",
    "regime_conditioned_performance_policy_digest",
    "regime_conditioned_performance_policy_from_payload",
    "regime_conditioned_performance_policy_to_dict",
    "regime_conditioned_performance_rule_set",
    "verify_regime_conditioned_performance_evidence",
    "verify_regime_conditioned_performance_policy",
]
