"""Edge Factory EF-6: governed walk-forward / out-of-sample performance evidence over a sealed EF-5 preregistration.

EF-6 is the FIRST Edge Factory gate that consumes performance. It interprets authenticated historical walk-forward
metrics (``HistoricalWalkForwardMetricsResult``) ONLY for parameter assignments preregistered in a sealed EF-5 ledger,
and it evaluates EVERY registered variant independently over one identical governed window frame. It selects nothing:
there is no best variant, winner, ranking or selected assignment. Its only derived output about variants is the
canonical set of surviving assignment digests; go/no-go and any choice among survivors belong to later governance.

PASS means ONLY that one or more preregistered variants survived the governed EF-6 historical walk-forward/OOS process.
It never means an edge, profitability, paper admission, PBO, stress, readiness or any live authority.

Authority (shared kernel ``edge_artifact_core``):

* Back-chain. The EF-5 predecessor is a required ``EdgeAuthorityBinding`` re-proven through
  ``verify_edge_leakage_bias_evidence`` against the caller's predecessor anchor; it must be READY + PASS + advancing
  and ``preregistration_sealed``. EF-4, EF-3 and EF-2 are re-proven through their public verifiers from the nested
  bindings; the EF-2 digest must equal the explicit root anchor and every carried root field. Every link shares this
  artifact's correlation. An unsealed or broken chain is REJECTED.
* Performance. Each variant bundle is one ``HistoricalWalkForwardMetricsResult`` binding re-proven through
  ``verify_historical_walk_forward_metrics`` (which re-proves its metric policy and every IS/OOS historical execution
  economics source against their anchors). It must be READY with this correlation and cross-bind to EF-5 on the
  StrategySpec digest, profile semantics digest, DataRequirementRegistry digest, market type and pinned instrument;
  every IS/OOS source must carry EF-5's exact executable binding and EF-3 manifest digests and ONE parameter assignment
  digest across every window (no per-window switching), which must be registered in EF-5. A transplant, a switching
  bundle, an unregistered assignment or an assignment evaluated twice is REJECTED. Nothing is recomputed: no decision,
  execution, fee, funding, slippage or metric; EF-6 compares the authenticated metric texts exactly.
* Costs. The metrics descend from authenticated economics equity already net of taker fees, funding, spread, impact
  slippage and mark-to-market (``cost_accounting_basis_id``); EF-6 adds no cost and adjusts no value.
* Coverage (``ALL_REGISTERED_VARIANTS_EVALUATED_EXACTLY_ONCE``). The evaluated assignment set must equal the sealed
  EF-5 set; a missing registered variant is FAIL.
* Fairness. Every variant must share one evaluation frame — metric policy, economics policy, instrument, market type
  and the ordered IS/OOS intervals with their PIT dataset digests; any difference is FAIL. The frame digest is
  approved by governance, so the horizon, data and cost model cannot be changed after the fact.
* Governance. ``EdgeWalkForwardOosGovernance`` carries every governance-owned EF-6 value (minimum OOS window count,
  Sharpe retention ratio, hit-rate delta in percentage points, positive-expectancy window fraction, drawdown ratio,
  profit-factor minimum and window fraction) and commits to the EF-5 digest, the variant ledger digest, the
  multiple-testing count, the EF-6 rule set digest and the evaluation frame digest. Missing, non-matching or looser
  than the PRDV4 §1.13 Stage 2 / §12.3 floors (>= 3 OOS windows, retention >= 0.5, hit-rate delta >= -10pp, positive
  expectancy in >= 2/3 of windows) is NEEDS_GOVERNANCE_APPROVAL. No value is defaulted; legacy defaults are never
  treated as approval. ``governance_digest`` commits the exact approved record for any later consumer.
* Rules (``EDGE_WALK_FORWARD_OOS_RULE_SET_V1``, committed by ``rule_set_digest``), exact integer arithmetic over
  canonical scale-18 texts, no float, no epsilon, no ``decimal`` context. P3 hit rate is a RATIO; the approved delta
  is in percentage points and converts as ``ratio = pp / 100`` (0.55 ratio is 55 percentage points). A variant
  survives iff its metrics were computed and: OOS window count >= the approved minimum; in EVERY window OOS Sharpe >=
  IS Sharpe x ratio, OOS hit rate >= IS hit rate + pp/100 and IS max drawdown > 0 with OOS max drawdown strictly below
  ratio x IS max drawdown; OOS expectancy strictly positive in >= ceil(n x fraction) windows; OOS profit factor
  strictly above the minimum in >= ceil(n x fraction) windows. The rules are applied ONLY to an admissible evaluation
  set (complete, fair, single-instrument, non-synthetic, under valid governance); otherwise no computed variant is
  evaluated and no survivor is reported.
* Synthetic facts. Metrics whose economics used TEST_ONLY synthetic venue facts are NEEDS_EXTERNAL_FACTS; a TEST_ONLY
  synthetic economics approval is NEEDS_GOVERNANCE_APPROVAL. Synthetic evidence never advances a real gate.
* Multi-instrument. No accepted historical multi-instrument aggregation authority exists, so a pinned universe of more
  than one instrument is FAIL (``multi_instrument_universe_unsupported_v1``); one-instrument metrics never stand for a
  multi-instrument candidate.
* Regime. The regime split is explicit and digest-bound: ``regime_evidence_unavailable`` until an accepted RF chain
  exists; ``regime_evidence_available`` is structurally False.
* ``status`` is integrity only; ``gate_verdict`` the outcome (FAIL > NEEDS_EXTERNAL_FACTS > NEEDS_GOVERNANCE_APPROVAL >
  PASS); REJECTED implies NOT_EVALUATED. ``performance_data_consumed``/``oos_evidence_consumed`` are True exactly when
  authenticated computed metrics were consumed, ``walk_forward_evaluated`` exactly when the governed rules were
  evaluated; never on a REJECTED path. One assembly path serves the builder and verifier reassembly;
  ``verify_edge_walk_forward_oos_evidence`` is total. Paper-only, deterministic, no IO/clock/network/float.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum

from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    build_edge_authority_binding,
    edge_authority_binding_snapshot,
    edge_authority_binding_to_payload,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    parse_edge_authority_binding,
    require_edge_authority_binding,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    edge_idea_intake_evidence_from_payload,
    verify_edge_idea_intake_evidence,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    edge_leakage_bias_evidence_from_payload,
    edge_leakage_bias_evidence_payload_is_well_formed,
    edge_leakage_bias_evidence_to_dict,
    verify_edge_leakage_bias_evidence,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    edge_source_packet_evidence_from_payload,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    EdgeStrategySpecAdmissionEvidence,
    edge_strategy_spec_admission_from_payload,
    verify_edge_strategy_spec_admission,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_decimal_is_canonical
from crypto_core.validation.historical_walk_forward_metrics import (
    HistoricalWalkForwardMetricsResult,
    HistoricalWalkForwardWindowMetrics,
    historical_walk_forward_metrics_from_payload,
    historical_walk_forward_metrics_payload_is_well_formed,
    historical_walk_forward_metrics_to_dict,
    verify_historical_walk_forward_metrics,
)

_SCHEMA_VERSION = "edge-walk-forward-oos-evidence.v1"
_GATE_ID = "EF-6"
_PREDECESSOR_GATE_ID = "EF-5"
_REASON_PREFIX = "edge_walk_forward_oos_evidence"
_SELF_DIGEST_FIELD = "walk_forward_oos_evidence_digest"
_SCALE_UNITS = 10**18
_PERCENTAGE_POINTS_PER_RATIO = 100
_INT64_MAX = 9223372036854775807
_DAY_NS = 86_400_000_000_000

# PRDV4 §1.13 Stage 2 / §12.3 floors (governance may be stricter, never looser) and the accepted P3 V1 geometry reading
# of "each >= 3 months" as 90 UTC days, plus the §1.13 Stage 1 "12 months in-sample" read as 365 UTC days.
_PRDV4_MIN_OOS_WINDOW_COUNT = 3
_PRDV4_MIN_SHARPE_RETENTION_RATIO = "0.500000000000000000"
_PRDV4_MIN_HIT_RATE_DELTA_PERCENTAGE_POINTS = "-10.000000000000000000"
_PRDV4_MIN_POSITIVE_EXPECTANCY_FRACTION = (2, 3)
_PRDV4_MIN_IN_SAMPLE_DURATION_DAYS = 365
_PRDV4_MIN_OOS_DURATION_DAYS = 90
_COST_ACCOUNTING_BASIS_ID = (
    "historical_execution_economics_equity_net_of_taker_fees_funding_spread_impact_slippage_and_mark_to_market.v1"
)
_MULTI_INSTRUMENT_UNSUPPORTED = "multi_instrument_universe_unsupported_v1"
# Identity fields every IS/OOS economics source must carry, read from its authenticated snapshot.
_SOURCE_TEXT_FIELDS = (
    "strategy_spec_digest",
    "profile_semantics_digest",
    "data_requirement_registry_digest",
    "market_type",
    "instrument",
    "executable_binding_digest",
    "source_manifest_digest",
    "parameter_assignment_digest",
    "dataset_digest",
)
_SOURCE_TIME_FIELDS = ("evaluation_start_ns", "evaluation_end_ns")

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_walk_forward_oos_rules.v1",
    "evaluation_coverage_rule_id": "all_registered_variants_evaluated_exactly_once.v1",
    "selection_provenance_rule_id": "no_selection_every_registered_variant_evaluated_independently.v1",
    "assignment_rule_id": "one_registered_parameter_assignment_across_every_window_and_segment.v1",
    "window_fairness_rule_id": "identical_evaluation_frame_across_variants.v1",
    "evaluation_frame_fields_id": "metric_policy_economics_policy_instrument_market_type_ordered_is_oos_intervals_and_pit_datasets.v1",
    "sharpe_retention_rule_id": "every_window_oos_sharpe_at_least_is_sharpe_times_min_ratio.v1",
    "hit_rate_retention_rule_id": "every_window_oos_hit_rate_at_least_is_hit_rate_plus_delta.v1",
    "hit_rate_unit_conversion_id": "p3_hit_rate_is_a_ratio_delta_percentage_points_divided_by_100.v1",
    "drawdown_rule_id": "every_window_positive_is_max_drawdown_and_oos_strictly_below_ratio_times_is.v1",
    "positive_expectancy_rule_id": "oos_expectancy_strictly_positive_in_at_least_ceil_n_times_fraction_windows.v1",
    "profit_factor_rule_id": "oos_profit_factor_strictly_above_minimum_in_at_least_ceil_n_times_fraction_windows.v1",
    "window_count_rule_id": "oos_window_count_at_least_approved_minimum.v1",
    "survival_rule_id": "variant_survives_iff_metrics_computed_and_every_rule_holds.v1",
    "gate_rule_id": "pass_iff_complete_fair_coverage_and_at_least_one_registered_variant_survives.v1",
    "numeric_rule_id": "exact_integer_comparison_of_canonical_scale18_texts_no_float_no_decimal_context.v1",
    "multi_instrument_rule_id": "single_pinned_instrument_only_multi_instrument_fails_closed.v1",
    "synthetic_fact_rule_id": "synthetic_facts_need_external_facts_synthetic_approval_needs_governance.v1",
    "regime_rule_id": "regime_split_explicit_unavailable_until_accepted_rf_chain.v1",
    "cost_accounting_basis_id": _COST_ACCOUNTING_BASIS_ID,
    "prdv4_floor_rule_id": "governance_values_never_looser_than_prdv4_1_13_stage_2_and_12_3.v1",
    "prdv4_min_oos_window_count": _PRDV4_MIN_OOS_WINDOW_COUNT,
    "prdv4_min_sharpe_retention_ratio": _PRDV4_MIN_SHARPE_RETENTION_RATIO,
    "prdv4_min_hit_rate_delta_percentage_points": _PRDV4_MIN_HIT_RATE_DELTA_PERCENTAGE_POINTS,
    "prdv4_min_positive_expectancy_fraction": list(_PRDV4_MIN_POSITIVE_EXPECTANCY_FRACTION),
    "prdv4_min_in_sample_duration_days": _PRDV4_MIN_IN_SAMPLE_DURATION_DAYS,
    "prdv4_min_oos_duration_days": _PRDV4_MIN_OOS_DURATION_DAYS,
    "prdv4_duration_interpretation_id": "twelve_months_as_365_and_three_months_as_90_utc_days_p3_v1_geometry.v1",
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))


def edge_walk_forward_oos_rule_set() -> dict[str, object]:
    """A fresh copy of the code-defined EF-6 V1 rule set committed by ``EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST``."""

    return {key: list(value) if isinstance(value, list) else value for key, value in _RULE_SET_V1.items()}


# EF-6 genuinely consumes performance: the three consumption flags are computed, never structural defaults.
_COMPUTED_FLAGS = frozenset({"preregistration_sealed", "performance_data_consumed", "oos_evidence_consumed"})
EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if flag[0] not in _COMPUTED_FLAGS),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS)


class EdgeWalkForwardOosEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgeVariantEvaluationStatus(str, Enum):
    """Per-variant outcome.

    A variant whose metrics were not computed is FAILED. A computed variant is NOT_EVALUATED exactly when the governed
    rules were not applied: the evaluation set is incomplete, unfair, multi-instrument or synthetic, or governance is
    missing, non-matching or looser than the PRDV4 floors. Only then is no survivor ever reported.
    """

    SURVIVED = "SURVIVED"
    FAILED = "FAILED"
    NOT_EVALUATED = "NOT_EVALUATED"


@dataclass(frozen=True)
class EdgeVariantMetricsInput:
    """Caller input: one registered variant's walk-forward metrics result and the caller's anchor for it."""

    metrics_result: HistoricalWalkForwardMetricsResult
    expected_metrics_result_digest: str


@dataclass(frozen=True)
class EdgeWalkForwardOosGovernance:
    """Human governance approval of every governance-owned EF-6 value, bound to one exact preregistration and frame.

    Decimal values are canonical scale-18 texts; fractions are ``numerator / denominator`` with ``0 < n <= d``.
    """

    approval_reference: str
    approval_digest: str
    approved_predecessor_digest: str
    approved_variant_ledger_digest: str
    approved_multiple_testing_count: int
    approved_rule_set_digest: str
    approved_evaluation_frame_digest: str
    min_oos_window_count: int
    min_sharpe_retention_ratio: str
    min_hit_rate_delta_percentage_points: str
    positive_expectancy_fraction_numerator: int
    positive_expectancy_fraction_denominator: int
    max_drawdown_ratio_exclusive: str
    min_profit_factor_exclusive: str
    profit_factor_fraction_numerator: int
    profit_factor_fraction_denominator: int


@dataclass(frozen=True)
class EdgeWalkForwardWindowFrame:
    """One governed window: IS and OOS half-open intervals and the PIT dataset digest each segment consumed."""

    window_index: int
    in_sample_start_ns: int
    in_sample_end_ns: int
    in_sample_dataset_digest: str
    out_of_sample_start_ns: int
    out_of_sample_end_ns: int
    out_of_sample_dataset_digest: str


@dataclass(frozen=True)
class EdgeWalkForwardWindowOutcome:
    """Exact rule outcomes of one window of one variant under the approved governance values."""

    window_index: int
    window_digest: str
    sharpe_retention_holds: bool
    hit_rate_retention_holds: bool
    drawdown_holds: bool
    positive_expectancy: bool
    profit_factor_above_minimum: bool


@dataclass(frozen=True)
class EdgeVariantWalkForwardEvaluation:
    """The independent EF-6 evaluation of one registered variant; never a ranking and never a selection."""

    variant_id: str
    parameter_assignment_digest: str
    metrics_result_id: str
    metrics_result_digest: str
    metrics_computed: bool
    window_count: int
    window_digests: tuple[str, ...]
    evaluation_status: EdgeVariantEvaluationStatus
    window_outcomes: tuple[EdgeWalkForwardWindowOutcome, ...]
    positive_expectancy_window_count: int
    required_positive_expectancy_window_count: int
    profit_factor_window_count: int
    required_profit_factor_window_count: int
    failure_codes: tuple[str, ...]


@dataclass(frozen=True)
class EdgeWalkForwardOosEvidence:
    """Immutable, digest-bound EF-6 evidence. PAPER ONLY; proves governed historical survival, never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    evidence_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_binding: EdgeAuthorityBinding
    predecessor_gate_id: str
    predecessor_digest: str
    admission_digest: str
    source_manifest_digest: str
    data_requirement_registry_digest: str
    strategy_spec_digest: str
    executable_binding_digest: str
    profile_semantics_digest: str
    market_type: str
    pinned_instrument_universe: tuple[str, ...]
    variant_ledger_digest: str
    registered_parameter_assignment_digests: tuple[str, ...]
    multiple_testing_count: int
    registered_variant_count: int
    variant_metrics_bindings: tuple[EdgeAuthorityBinding, ...]
    evaluated_variant_count: int
    rule_set_id: str
    rule_set_digest: str
    metric_policy_digest: str
    economics_policy_digest: str
    evaluated_instrument: str
    window_frames: tuple[EdgeWalkForwardWindowFrame, ...]
    evaluation_frame_digest: str
    cost_accounting_basis_id: str
    synthetic_test_facts_used: bool
    synthetic_test_approval_used: bool
    governance: EdgeWalkForwardOosGovernance | None
    governance_digest: str
    variant_evaluations: tuple[EdgeVariantWalkForwardEvaluation, ...]
    surviving_assignment_digests: tuple[str, ...]
    surviving_variant_count: int
    regime_label_binding_status: str
    regime_evidence_status: str
    regime_split_report: str
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    preregistration_sealed: bool
    performance_data_consumed: bool
    oos_evidence_consumed: bool
    walk_forward_evaluated: bool
    walk_forward_oos_evidence_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    kill_criteria_sealed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    pbo_passed: bool = False
    stress_passed: bool = False
    performance_metrics_computed: bool = False


@dataclass(frozen=True)
class _Chain:
    ef5: EdgeLeakageBiasEvidence
    admission: EdgeStrategySpecAdmissionEvidence
    manifest: EdgeSourcePacketEvidence


@dataclass(frozen=True)
class _Bundle:
    """One authenticated, cross-bound variant bundle."""

    metrics: HistoricalWalkForwardMetricsResult
    binding: EdgeAuthorityBinding
    assignment_digest: str
    frames: tuple[EdgeWalkForwardWindowFrame, ...]


@dataclass(frozen=True)
class _Thresholds:
    """Approved governance values as exact scale units; built only from a validated governance record."""

    min_windows: int
    sharpe_ratio: int
    hit_delta_pp: int
    expectancy_fraction: tuple[int, int]
    drawdown_ratio: int
    profit_factor_min: int
    profit_factor_fraction: tuple[int, int]


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgeWalkForwardOosEvidenceError:
    return EdgeWalkForwardOosEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or not minimum <= value <= _INT64_MAX:
        raise _fail(f"{field_name}_invalid")
    return value


def _units(value: object) -> int | None:
    """Exact scale-18 units of a canonical decimal text (bounded to 60 characters by the canonical grammar)."""

    if not historical_execution_decimal_is_canonical(value):
        return None
    return int(value.replace(".", ""))  # type: ignore[union-attr]


def _require_decimal(value: object, field_name: str) -> str:
    if _units(value) is None:
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _required_count(window_count: int, fraction: tuple[int, int]) -> int:
    """``ceil(window_count * numerator / denominator)`` in exact integer arithmetic."""

    numerator, denominator = fraction
    return -(-window_count * numerator // denominator)


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) in _RECORD_TYPES:
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    """Serialize a record; an enum-typed field must hold the exact enum member, never an equal plain string."""

    for name, enum_cls in _ENUM_FIELDS.get(type(artifact), ()):
        if type(getattr(artifact, name)) is not enum_cls:
            raise _fail("payload_enum_field_not_exact_member")
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset(
    {
        EdgeWalkForwardOosGovernance,
        EdgeWalkForwardWindowFrame,
        EdgeWalkForwardWindowOutcome,
        EdgeVariantWalkForwardEvaluation,
    }
)
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgeWalkForwardOosEvidence: (("status", EdgeEvidenceStatus), ("gate_verdict", EdgeGateVerdict)),
    EdgeVariantWalkForwardEvaluation: (("evaluation_status", EdgeVariantEvaluationStatus),),
}


# --- caller declarations -----------------------------------------------------------------------------------------------


def _canonical_governance(governance: object) -> EdgeWalkForwardOosGovernance | None:
    """Structural validation only: whether the values MATCH and respect the PRDV4 floors is decided at assembly."""

    if governance is None:
        return None
    if type(governance) is not EdgeWalkForwardOosGovernance:
        raise _fail("governance_malformed")

    def attribute(name: str) -> object:
        return getattr(governance, name, None)

    record = EdgeWalkForwardOosGovernance(
        approval_reference=_require_text(attribute("approval_reference"), "governance_approval_reference"),
        approval_digest=_require_hex64(attribute("approval_digest"), "governance_approval_digest"),
        approved_predecessor_digest=_require_hex64(
            attribute("approved_predecessor_digest"), "governance_approved_predecessor_digest"
        ),
        approved_variant_ledger_digest=_require_hex64(
            attribute("approved_variant_ledger_digest"), "governance_approved_variant_ledger_digest"
        ),
        approved_multiple_testing_count=_require_int(
            attribute("approved_multiple_testing_count"), "governance_approved_multiple_testing_count", minimum=1
        ),
        approved_rule_set_digest=_require_hex64(
            attribute("approved_rule_set_digest"), "governance_approved_rule_set_digest"
        ),
        approved_evaluation_frame_digest=_require_hex64(
            attribute("approved_evaluation_frame_digest"), "governance_approved_evaluation_frame_digest"
        ),
        min_oos_window_count=_require_int(
            attribute("min_oos_window_count"), "governance_min_oos_window_count", minimum=1
        ),
        min_sharpe_retention_ratio=_require_decimal(
            attribute("min_sharpe_retention_ratio"), "governance_min_sharpe_retention_ratio"
        ),
        min_hit_rate_delta_percentage_points=_require_decimal(
            attribute("min_hit_rate_delta_percentage_points"), "governance_min_hit_rate_delta_percentage_points"
        ),
        positive_expectancy_fraction_numerator=_require_int(
            attribute("positive_expectancy_fraction_numerator"), "governance_positive_expectancy_fraction", minimum=1
        ),
        positive_expectancy_fraction_denominator=_require_int(
            attribute("positive_expectancy_fraction_denominator"), "governance_positive_expectancy_fraction", minimum=1
        ),
        max_drawdown_ratio_exclusive=_require_decimal(
            attribute("max_drawdown_ratio_exclusive"), "governance_max_drawdown_ratio_exclusive"
        ),
        min_profit_factor_exclusive=_require_decimal(
            attribute("min_profit_factor_exclusive"), "governance_min_profit_factor_exclusive"
        ),
        profit_factor_fraction_numerator=_require_int(
            attribute("profit_factor_fraction_numerator"), "governance_profit_factor_fraction", minimum=1
        ),
        profit_factor_fraction_denominator=_require_int(
            attribute("profit_factor_fraction_denominator"), "governance_profit_factor_fraction", minimum=1
        ),
    )
    if record.positive_expectancy_fraction_numerator > record.positive_expectancy_fraction_denominator:
        raise _fail("governance_positive_expectancy_fraction_invalid")
    if record.profit_factor_fraction_numerator > record.profit_factor_fraction_denominator:
        raise _fail("governance_profit_factor_fraction_invalid")
    if _units(record.max_drawdown_ratio_exclusive) <= 0:  # type: ignore[operator]
        raise _fail("governance_max_drawdown_ratio_exclusive_invalid")
    if _units(record.min_profit_factor_exclusive) < 0:  # type: ignore[operator]
        raise _fail("governance_min_profit_factor_exclusive_invalid")
    return record


def _canonical_metrics_bindings(values: object) -> tuple[EdgeAuthorityBinding, ...]:
    if type(values) not in (tuple, list):
        raise _fail("variant_metrics_bindings_malformed")
    accepted: dict[str, EdgeAuthorityBinding] = {}
    for item in values:  # type: ignore[union-attr]
        binding = require_edge_authority_binding(
            item,
            shape=historical_walk_forward_metrics_payload_is_well_formed,
            error=EdgeWalkForwardOosEvidenceError,
            code=_reason("variant_metrics"),
            optional=False,
        )
        digest = binding.expected_digest  # type: ignore[union-attr]
        if digest in accepted:
            raise _fail("variant_metrics_duplicate")
        accepted[digest] = binding  # type: ignore[assignment]
    return tuple(accepted[digest] for digest in sorted(accepted))


# --- upstream authorities ----------------------------------------------------------------------------------------------


def _chain_authority(
    binding: EdgeAuthorityBinding, *, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], _Chain | None]:
    """Re-prove EF-5 → EF-4 → EF-3 → EF-2 through the public verifiers against both anchors and the correlation."""

    ef5 = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_edge_leakage_bias_evidence(ef5)
    if not verification.intact:
        return [_reason(f"predecessor_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason("predecessor_digest_mismatch")], None
    if ef5.correlation_id != correlation_id:
        return [_reason("predecessor_correlation_mismatch")], None
    if ef5.status is not EdgeEvidenceStatus.READY:
        return [_reason("predecessor_rejected")], None
    if (
        ef5.gate_verdict is not EdgeGateVerdict.PASS
        or ef5.advances is not True
        or ef5.preregistration_sealed is not True
    ):
        return [_reason(f"predecessor_not_sealed:{ef5.gate_verdict.value}")], None
    admission = edge_strategy_spec_admission_from_payload(edge_authority_binding_snapshot(ef5.predecessor_binding))
    admission_verification = verify_edge_strategy_spec_admission(admission)
    if not admission_verification.intact:
        return [_reason(f"admission_integrity_failure:{code}") for code in admission_verification.reason_codes], None
    if (
        admission_verification.recomputed_digest != ef5.predecessor_digest
        or admission.correlation_id != correlation_id
        or admission.status is not EdgeEvidenceStatus.READY
    ):
        return [_reason("admission_chain_mismatch")], None
    manifest = edge_source_packet_evidence_from_payload(edge_authority_binding_snapshot(admission.predecessor_binding))
    manifest_verification = verify_edge_source_packet_evidence(manifest)
    if not manifest_verification.intact:
        codes = [_reason(f"source_manifest_integrity_failure:{code}") for code in manifest_verification.reason_codes]
        return codes, None
    if (
        manifest_verification.recomputed_digest != admission.predecessor_digest
        or manifest.correlation_id != correlation_id
        or manifest.status is not EdgeEvidenceStatus.READY
    ):
        return [_reason("source_manifest_chain_mismatch")], None
    root = edge_idea_intake_evidence_from_payload(edge_authority_binding_snapshot(manifest.root_intake_binding))
    root_verification = verify_edge_idea_intake_evidence(root)
    if not root_verification.intact:
        return [_reason(f"root_intake_integrity_failure:{code}") for code in root_verification.reason_codes], None
    carried_roots = (ef5.root_intake_digest, admission.root_intake_digest, manifest.root_intake_digest)
    if root_verification.recomputed_digest != root_intake_digest or any(
        carried != root_intake_digest for carried in carried_roots
    ):
        return [_reason("chain_splice_root_intake_mismatch")], None
    if root.correlation_id != correlation_id or root.status is not EdgeEvidenceStatus.READY:
        return [_reason("root_intake_chain_mismatch")], None
    return [], _Chain(ef5=ef5, admission=admission, manifest=manifest)


def _source_identities(
    metrics: HistoricalWalkForwardMetricsResult,
) -> tuple[list[tuple[dict[str, object], dict[str, object]]], list[EdgeWalkForwardWindowFrame]] | None:
    """The identity fields of every IS/OOS economics source, read from the window-binding snapshots.

    The snapshots are exactly the economics payloads the metrics verifier just re-proved against their anchors (and the
    metrics shape predicate strictly parsed), so their fields are authenticated; they are read, never re-derived. Any
    field of an unexpected type is refused (``None``) rather than coerced.
    """

    sources: list[tuple[dict[str, object], dict[str, object]]] = []
    for window in metrics.window_bindings:
        pair = []
        for binding in (window.in_sample_binding, window.out_of_sample_binding):
            snapshot = edge_authority_binding_snapshot(binding)
            identity = {name: snapshot.get(name) for name in _SOURCE_TEXT_FIELDS + _SOURCE_TIME_FIELDS}
            if any(type(identity[name]) is not str for name in _SOURCE_TEXT_FIELDS) or any(
                type(identity[name]) is not int for name in _SOURCE_TIME_FIELDS
            ):
                return None
            pair.append(identity)
        sources.append((pair[0], pair[1]))
    frames = [
        EdgeWalkForwardWindowFrame(
            window_index=index,
            in_sample_start_ns=in_sample["evaluation_start_ns"],  # type: ignore[arg-type]
            in_sample_end_ns=in_sample["evaluation_end_ns"],  # type: ignore[arg-type]
            in_sample_dataset_digest=in_sample["dataset_digest"],  # type: ignore[arg-type]
            out_of_sample_start_ns=out_of_sample["evaluation_start_ns"],  # type: ignore[arg-type]
            out_of_sample_end_ns=out_of_sample["evaluation_end_ns"],  # type: ignore[arg-type]
            out_of_sample_dataset_digest=out_of_sample["dataset_digest"],  # type: ignore[arg-type]
        )
        for index, (in_sample, out_of_sample) in enumerate(sources)
    ]
    return sources, frames


def _bundle_authority(
    binding: EdgeAuthorityBinding, *, label: str, correlation_id: str, chain: _Chain | None
) -> tuple[list[str], _Bundle | None]:
    """Re-prove one variant metrics bundle and cross-bind it to the authenticated EF-5 chain."""

    metrics = historical_walk_forward_metrics_from_payload(edge_authority_binding_snapshot(binding))
    verification = verify_historical_walk_forward_metrics(metrics)
    if not verification.intact:
        return [_reason(f"{label}:integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason(f"{label}:digest_mismatch")], None
    if metrics.correlation_id != correlation_id:
        return [_reason(f"{label}:correlation_mismatch")], None
    if metrics.status is not EdgeEvidenceStatus.READY:
        return [_reason(f"{label}:rejected")], None
    if chain is None:
        return [], None
    ef5, admission, manifest = chain.ef5, chain.admission, chain.manifest
    identities = _source_identities(metrics)
    if identities is None:
        return [_reason(f"{label}:source_snapshot_malformed")], None
    sources, frames = identities
    expected = {
        "strategy_spec_digest": ef5.strategy_spec_digest,
        "profile_semantics_digest": ef5.profile_semantics_digest,
        "data_requirement_registry_digest": manifest.data_requirement_registry_digest,
        "market_type": admission.market_type,
    }
    codes = [_reason(f"{label}:{name}_mismatch") for name, value in expected.items() if getattr(metrics, name) != value]
    if metrics.instrument not in ef5.pinned_instrument_universe:
        codes.append(_reason(f"{label}:instrument_outside_pinned_universe"))
    source_expected = {
        **expected,
        "instrument": metrics.instrument,
        "executable_binding_digest": ef5.executable_binding_digest,
        "source_manifest_digest": ef5.source_manifest_digest,
    }
    for index, pair in enumerate(sources):
        for segment, source in zip(("in_sample", "out_of_sample"), pair, strict=True):
            codes.extend(
                _reason(f"{label}:window_{index}:{segment}:{name}_mismatch")
                for name, value in source_expected.items()
                if source[name] != value
            )
    assignments = {source["parameter_assignment_digest"] for pair in sources for source in pair}
    if len(assignments) != 1:
        codes.append(_reason(f"{label}:parameter_assignment_switching"))
    elif next(iter(assignments)) not in ef5.registered_parameter_assignment_digests:
        codes.append(_reason(f"{label}:parameter_assignment_unregistered"))
    if codes:
        return codes, None
    return [], _Bundle(
        metrics=metrics,
        binding=binding,
        assignment_digest=next(iter(assignments)),  # type: ignore[arg-type]
        frames=tuple(frames),
    )


# --- governed rules ----------------------------------------------------------------------------------------------------


def _governance_reasons(
    governance: EdgeWalkForwardOosGovernance | None, committed: Mapping[str, object]
) -> tuple[list[str], _Thresholds | None]:
    """``(needs_governance_codes, thresholds)``; thresholds exist only for a present, matching, floor-respecting record."""

    if governance is None:
        return [_reason("oos_governance_missing")], None
    codes = [
        _reason(f"oos_governance_{name}_mismatch")
        for name, value in committed.items()
        if getattr(governance, f"approved_{name}") != value
    ]
    sharpe = _units(governance.min_sharpe_retention_ratio)
    hit = _units(governance.min_hit_rate_delta_percentage_points)
    expectancy = (
        governance.positive_expectancy_fraction_numerator,
        governance.positive_expectancy_fraction_denominator,
    )
    floor_num, floor_den = _PRDV4_MIN_POSITIVE_EXPECTANCY_FRACTION
    if governance.min_oos_window_count < _PRDV4_MIN_OOS_WINDOW_COUNT:
        codes.append(_reason("oos_governance_below_prdv4_floor:min_oos_window_count"))
    if sharpe < _units(_PRDV4_MIN_SHARPE_RETENTION_RATIO):  # type: ignore[operator]
        codes.append(_reason("oos_governance_below_prdv4_floor:min_sharpe_retention_ratio"))
    if hit < _units(_PRDV4_MIN_HIT_RATE_DELTA_PERCENTAGE_POINTS):  # type: ignore[operator]
        codes.append(_reason("oos_governance_below_prdv4_floor:min_hit_rate_delta_percentage_points"))
    if expectancy[0] * floor_den < floor_num * expectancy[1]:
        codes.append(_reason("oos_governance_below_prdv4_floor:positive_expectancy_fraction"))
    if codes:
        return codes, None
    return [], _Thresholds(
        min_windows=governance.min_oos_window_count,
        sharpe_ratio=sharpe,  # type: ignore[arg-type]
        hit_delta_pp=hit,  # type: ignore[arg-type]
        expectancy_fraction=expectancy,
        drawdown_ratio=_units(governance.max_drawdown_ratio_exclusive),  # type: ignore[arg-type]
        profit_factor_min=_units(governance.min_profit_factor_exclusive),  # type: ignore[arg-type]
        profit_factor_fraction=(
            governance.profit_factor_fraction_numerator,
            governance.profit_factor_fraction_denominator,
        ),
    )


def _window_outcome(
    window: HistoricalWalkForwardWindowMetrics, thresholds: _Thresholds
) -> tuple[EdgeWalkForwardWindowOutcome, list[str]]:
    """Exact rule outcomes of one window; every comparison is between integers at the common scale."""

    in_sample, out_of_sample = window.in_sample, window.out_of_sample
    values = [
        _units(text)
        for text in (
            in_sample.annualized_sharpe,
            out_of_sample.annualized_sharpe,
            in_sample.hit_rate,
            out_of_sample.hit_rate,
            in_sample.max_drawdown,
            out_of_sample.max_drawdown,
            out_of_sample.expectancy,
            out_of_sample.profit_factor,
        )
    ]
    prefix = f"window_{window.window_index}"
    if any(value is None for value in values):
        outcome = EdgeWalkForwardWindowOutcome(
            window.window_index, window.window_digest, False, False, False, False, False
        )
        return outcome, [f"{prefix}:metric_text_noncanonical"]
    is_sharpe, oos_sharpe, is_hit, oos_hit, is_drawdown, oos_drawdown, oos_expectancy, oos_profit_factor = values
    sharpe_holds = oos_sharpe * _SCALE_UNITS >= is_sharpe * thresholds.sharpe_ratio  # type: ignore[operator]
    hit_holds = (
        _PERCENTAGE_POINTS_PER_RATIO * oos_hit  # type: ignore[operator]
        >= _PERCENTAGE_POINTS_PER_RATIO * is_hit + thresholds.hit_delta_pp  # type: ignore[operator]
    )
    drawdown_holds = is_drawdown > 0 and oos_drawdown * _SCALE_UNITS < thresholds.drawdown_ratio * is_drawdown  # type: ignore[operator]
    outcome = EdgeWalkForwardWindowOutcome(
        window_index=window.window_index,
        window_digest=window.window_digest,
        sharpe_retention_holds=sharpe_holds,
        hit_rate_retention_holds=hit_holds,
        drawdown_holds=drawdown_holds,
        positive_expectancy=oos_expectancy > 0,  # type: ignore[operator]
        profit_factor_above_minimum=oos_profit_factor > thresholds.profit_factor_min,  # type: ignore[operator]
    )
    codes: list[str] = []
    if not sharpe_holds:
        codes.append(f"{prefix}:sharpe_retention_below_minimum")
    if not hit_holds:
        codes.append(f"{prefix}:hit_rate_retention_below_minimum")
    if is_drawdown <= 0:  # type: ignore[operator]
        codes.append(f"{prefix}:in_sample_max_drawdown_not_positive")
    elif not drawdown_holds:
        codes.append(f"{prefix}:drawdown_ratio_not_below_maximum")
    return outcome, codes


def _evaluate_bundle(
    variant_id: str, bundle: _Bundle, thresholds: _Thresholds | None
) -> EdgeVariantWalkForwardEvaluation:
    """Evaluate one registered variant independently; no information from any other variant is consulted."""

    metrics = bundle.metrics
    computed = metrics.computation_verdict is EdgeGateVerdict.PASS and metrics.performance_metrics_computed is True
    windows = metrics.windows if computed else ()
    base = {
        "variant_id": variant_id,
        "parameter_assignment_digest": bundle.assignment_digest,
        "metrics_result_id": metrics.result_id,
        "metrics_result_digest": bundle.binding.expected_digest,
        "metrics_computed": computed,
        "window_count": metrics.window_count,
        "window_digests": metrics.window_digests,
    }
    if not computed:
        return EdgeVariantWalkForwardEvaluation(
            **base,  # type: ignore[arg-type]
            evaluation_status=EdgeVariantEvaluationStatus.FAILED,
            window_outcomes=(),
            positive_expectancy_window_count=0,
            required_positive_expectancy_window_count=0,
            profit_factor_window_count=0,
            required_profit_factor_window_count=0,
            failure_codes=("metrics_not_computed",),
        )
    if thresholds is None:
        return EdgeVariantWalkForwardEvaluation(
            **base,  # type: ignore[arg-type]
            evaluation_status=EdgeVariantEvaluationStatus.NOT_EVALUATED,
            window_outcomes=(),
            positive_expectancy_window_count=0,
            required_positive_expectancy_window_count=0,
            profit_factor_window_count=0,
            required_profit_factor_window_count=0,
            failure_codes=(),
        )
    outcomes: list[EdgeWalkForwardWindowOutcome] = []
    codes: list[str] = []
    for window in windows:
        outcome, window_codes = _window_outcome(window, thresholds)
        outcomes.append(outcome)
        codes.extend(window_codes)
    count = len(windows)
    expectancy_count = sum(1 for outcome in outcomes if outcome.positive_expectancy)
    expectancy_required = _required_count(count, thresholds.expectancy_fraction)
    profit_factor_count = sum(1 for outcome in outcomes if outcome.profit_factor_above_minimum)
    profit_factor_required = _required_count(count, thresholds.profit_factor_fraction)
    if count < thresholds.min_windows:
        codes.append("oos_window_count_below_minimum")
    if expectancy_count < expectancy_required:
        codes.append("positive_expectancy_window_count_below_required")
    if profit_factor_count < profit_factor_required:
        codes.append("profit_factor_window_count_below_required")
    return EdgeVariantWalkForwardEvaluation(
        **base,  # type: ignore[arg-type]
        evaluation_status=EdgeVariantEvaluationStatus.FAILED if codes else EdgeVariantEvaluationStatus.SURVIVED,
        window_outcomes=tuple(outcomes),
        positive_expectancy_window_count=expectancy_count,
        required_positive_expectancy_window_count=expectancy_required,
        profit_factor_window_count=profit_factor_count,
        required_profit_factor_window_count=profit_factor_required,
        failure_codes=_sorted_unique(codes),
    )


def _frame_payload(
    metrics: HistoricalWalkForwardMetricsResult | None, frames: Sequence[EdgeWalkForwardWindowFrame]
) -> dict[str, object]:
    return {
        "metric_policy_digest": "" if metrics is None else metrics.metric_policy_digest,
        "economics_policy_digest": "" if metrics is None else metrics.economics_policy_digest,
        "instrument": "" if metrics is None else metrics.instrument,
        "market_type": "" if metrics is None else metrics.market_type,
        "windows": [_to_payload(frame) for frame in frames],
    }


def _frame_geometry_reasons(frames: Sequence[EdgeWalkForwardWindowFrame]) -> list[str]:
    reasons: list[str] = []
    for frame in frames:
        if frame.in_sample_end_ns - frame.in_sample_start_ns < _PRDV4_MIN_IN_SAMPLE_DURATION_DAYS * _DAY_NS:
            reasons.append(_reason(f"prdv4_in_sample_duration_below_floor:window_{frame.window_index}"))
        if frame.out_of_sample_end_ns - frame.out_of_sample_start_ns < _PRDV4_MIN_OOS_DURATION_DAYS * _DAY_NS:
            reasons.append(_reason(f"prdv4_oos_duration_below_floor:window_{frame.window_index}"))
    return reasons


# --- EF-6 evidence -----------------------------------------------------------------------------------------------------


def _assemble_evidence(
    *,
    predecessor_binding: object,
    root_intake_digest: object,
    variant_metrics_bindings: object,
    evidence_id: object,
    correlation_id: object,
    governance: object,
) -> EdgeWalkForwardOosEvidence:
    """The one EF-6 assembly path, shared by the builder and verifier reassembly."""

    chain_binding = require_edge_authority_binding(
        predecessor_binding,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOosEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )
    root_anchor = _require_hex64(root_intake_digest, "root_intake_digest")
    bindings = _canonical_metrics_bindings(variant_metrics_bindings)
    evidence_id = _require_text(evidence_id, "evidence_id")
    correlation_id = _require_text(correlation_id, "correlation_id")
    governance_record = _canonical_governance(governance)

    chain_codes, chain = _chain_authority(
        chain_binding,  # type: ignore[arg-type]
        root_intake_digest=root_anchor,
        correlation_id=correlation_id,
    )
    codes = list(chain_codes)
    bundles: list[_Bundle] = []
    for index, binding in enumerate(bindings):
        bundle_codes, bundle = _bundle_authority(
            binding, label=f"variant_metrics_{index}", correlation_id=correlation_id, chain=chain
        )
        codes.extend(bundle_codes)
        if bundle is not None:
            bundles.append(bundle)
    by_assignment: dict[str, _Bundle] = {}
    for bundle in bundles:
        if bundle.assignment_digest in by_assignment:
            codes.append(_reason(f"parameter_assignment_evaluated_more_than_once:{bundle.assignment_digest}"))
        by_assignment[bundle.assignment_digest] = bundle
    integrity = _sorted_unique(codes)
    rejected = bool(integrity) or chain is None or len(bundles) != len(bindings)

    ef5 = None if chain is None else chain.ef5
    variant_ids = (
        {} if ef5 is None else {item.parameter_assignment_digest: item.variant_id for item in ef5.registered_variants}
    )
    ordered = [] if rejected else sorted(bundles, key=lambda item: variant_ids[item.assignment_digest])
    reference = ordered[0] if ordered else None
    frames = () if reference is None else reference.frames
    frame_digest = _digest_of(_frame_payload(None if reference is None else reference.metrics, frames))
    committed: dict[str, object] = {
        "predecessor_digest": chain_binding.expected_digest,  # type: ignore[union-attr]
        "variant_ledger_digest": "" if ef5 is None else ef5.variant_ledger_digest,
        "multiple_testing_count": 0 if ef5 is None else ef5.multiple_testing_count,
        "rule_set_digest": EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST,
        "evaluation_frame_digest": frame_digest,
    }

    evaluations: tuple[EdgeVariantWalkForwardEvaluation, ...] = ()
    survivors: tuple[str, ...] = ()
    evaluated_rules = False
    if rejected:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        fail: list[str] = []
        needs_external: list[str] = []
        needs_governance: list[str] = []
        if len(ef5.pinned_instrument_universe) != 1:  # type: ignore[union-attr]
            fail.append(_reason(_MULTI_INSTRUMENT_UNSUPPORTED))
        fail.extend(
            _reason(f"registered_variant_not_evaluated:{item.variant_id}")
            for item in ef5.registered_variants  # type: ignore[union-attr]
            if item.parameter_assignment_digest not in by_assignment
        )
        for bundle in ordered:
            variant_id = variant_ids[bundle.assignment_digest]
            if _frame_payload(bundle.metrics, bundle.frames) != _frame_payload(reference.metrics, frames):  # type: ignore[union-attr]
                fail.append(_reason(f"evaluation_frame_mismatch:{variant_id}"))
            if bundle.metrics.synthetic_test_facts_used:
                needs_external.append(_reason(f"synthetic_test_facts_used:{variant_id}"))
            if bundle.metrics.synthetic_test_approval_used:
                needs_governance.append(_reason(f"synthetic_test_approval_used:{variant_id}"))
        fail.extend(_frame_geometry_reasons(frames))
        governance_codes, thresholds = _governance_reasons(governance_record, committed)
        needs_governance.extend(governance_codes)
        # The governed rules are applied only to an admissible evaluation set: complete, fair, single-instrument and
        # non-synthetic, under valid governance. Otherwise no variant is evaluated and no survivor is ever reported.
        if fail or needs_external or needs_governance:
            thresholds = None
        evaluations = tuple(
            _evaluate_bundle(variant_ids[bundle.assignment_digest], bundle, thresholds) for bundle in ordered
        )
        survivors = tuple(
            sorted(
                item.parameter_assignment_digest
                for item in evaluations
                if item.evaluation_status is EdgeVariantEvaluationStatus.SURVIVED
            )
        )
        evaluated_rules = thresholds is not None and any(item.metrics_computed for item in evaluations)
        if thresholds is not None and not survivors:
            fail.append(_reason("no_registered_variant_survived"))
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    consumed = status is EdgeEvidenceStatus.READY and any(item.metrics_computed for item in evaluations)
    advances = status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS
    seed = EdgeWalkForwardOosEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=advances,
        evidence_id=evidence_id,
        correlation_id=correlation_id,
        root_intake_digest=root_anchor,
        predecessor_binding=chain_binding,  # type: ignore[arg-type]
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        predecessor_digest=chain_binding.expected_digest,  # type: ignore[union-attr]
        admission_digest="" if chain is None else chain.ef5.predecessor_digest,
        source_manifest_digest="" if chain is None else chain.ef5.source_manifest_digest,
        data_requirement_registry_digest="" if chain is None else chain.manifest.data_requirement_registry_digest,
        strategy_spec_digest="" if chain is None else chain.ef5.strategy_spec_digest,
        executable_binding_digest="" if chain is None else chain.ef5.executable_binding_digest,
        profile_semantics_digest="" if chain is None else chain.ef5.profile_semantics_digest,
        market_type="" if chain is None else chain.admission.market_type,
        pinned_instrument_universe=() if chain is None else chain.ef5.pinned_instrument_universe,
        variant_ledger_digest=committed["variant_ledger_digest"],  # type: ignore[arg-type]
        registered_parameter_assignment_digests=()
        if chain is None
        else chain.ef5.registered_parameter_assignment_digests,
        multiple_testing_count=committed["multiple_testing_count"],  # type: ignore[arg-type]
        registered_variant_count=0 if chain is None else len(chain.ef5.registered_variants),
        variant_metrics_bindings=bindings,
        evaluated_variant_count=len(ordered),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST,
        metric_policy_digest="" if reference is None else reference.metrics.metric_policy_digest,
        economics_policy_digest="" if reference is None else reference.metrics.economics_policy_digest,
        evaluated_instrument="" if reference is None else reference.metrics.instrument,
        window_frames=frames,
        evaluation_frame_digest=frame_digest,
        cost_accounting_basis_id=_COST_ACCOUNTING_BASIS_ID,
        synthetic_test_facts_used=any(bundle.metrics.synthetic_test_facts_used for bundle in ordered),
        synthetic_test_approval_used=any(bundle.metrics.synthetic_test_approval_used for bundle in ordered),
        governance=governance_record,
        governance_digest="" if governance_record is None else _digest_of(_to_payload(governance_record)),
        variant_evaluations=evaluations,
        surviving_assignment_digests=survivors,
        surviving_variant_count=len(survivors),
        regime_label_binding_status=EDGE_REGIME_LABEL_BINDING_PENDING,
        regime_evidence_status=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        regime_split_report=EDGE_REGIME_EVIDENCE_UNAVAILABLE,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        preregistration_sealed=status is EdgeEvidenceStatus.READY,
        performance_data_consumed=consumed,
        oos_evidence_consumed=consumed,
        walk_forward_evaluated=status is EdgeEvidenceStatus.READY and evaluated_rules,
        walk_forward_oos_evidence_digest="",
    )
    return replace(seed, walk_forward_oos_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))


def build_edge_walk_forward_oos_evidence(
    predecessor: EdgeLeakageBiasEvidence,
    *,
    expected_predecessor_digest: str,
    expected_root_intake_digest: str,
    variant_metrics: Sequence[EdgeVariantMetricsInput],
    evidence_id: str,
    correlation_id: str,
    governance: EdgeWalkForwardOosGovernance | None = None,
) -> EdgeWalkForwardOosEvidence:
    """Build deterministic EF-6 walk-forward/OOS evidence over a sealed EF-5 preregistration.

    Malformed caller input or a non-serializable upstream object raises ``EdgeWalkForwardOosEvidenceError``. A broken,
    spliced or unsealed chain, a non-verifying or transplanted metrics bundle, a switching, unregistered or duplicated
    assignment yields ``REJECTED``/``NOT_EVALUATED``. Otherwise the evidence is ``READY`` with ``FAIL``,
    ``NEEDS_EXTERNAL_FACTS``, ``NEEDS_GOVERNANCE_APPROVAL`` or ``PASS``.
    """

    if type(predecessor) is not EdgeLeakageBiasEvidence:
        raise _fail("predecessor_malformed")
    try:
        predecessor_payload = edge_leakage_bias_evidence_to_dict(predecessor)
    except Exception as exc:  # noqa: BLE001 - a hollow predecessor object is a construction error, never a receipt
        raise _fail("predecessor_not_serializable") from exc
    chain_binding = build_edge_authority_binding(
        snapshot_payload=predecessor_payload,
        expected_digest=expected_predecessor_digest,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOosEvidenceError,
        code=_reason("predecessor"),
    )
    if type(variant_metrics) not in (tuple, list):
        raise _fail("variant_metrics_malformed")
    bindings: list[EdgeAuthorityBinding] = []
    for item in variant_metrics:
        if type(item) is not EdgeVariantMetricsInput:
            raise _fail("variant_metrics_entry_malformed")
        metrics = getattr(item, "metrics_result", None)
        if type(metrics) is not HistoricalWalkForwardMetricsResult:
            raise _fail("variant_metrics_result_malformed")
        try:
            payload = historical_walk_forward_metrics_to_dict(metrics)
        except Exception as exc:  # noqa: BLE001 - a hollow metrics object is a construction error, never a receipt
            raise _fail("variant_metrics_not_serializable") from exc
        bindings.append(
            build_edge_authority_binding(
                snapshot_payload=payload,
                expected_digest=getattr(item, "expected_metrics_result_digest", None),
                shape=historical_walk_forward_metrics_payload_is_well_formed,
                error=EdgeWalkForwardOosEvidenceError,
                code=_reason("variant_metrics"),
            )
        )
    return _assemble_evidence(
        predecessor_binding=chain_binding,
        root_intake_digest=expected_root_intake_digest,
        variant_metrics_bindings=tuple(bindings),
        evidence_id=evidence_id,
        correlation_id=correlation_id,
        governance=governance,
    )


def edge_walk_forward_oos_evidence_to_dict(evidence: EdgeWalkForwardOosEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for EF-6 evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_walk_forward_oos_evidence_digest(evidence: EdgeWalkForwardOosEvidence) -> str:
    """Recompute the canonical EF-6 digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


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


def _parse_predecessor_binding(value: object) -> EdgeAuthorityBinding | None:
    return parse_edge_authority_binding(
        value,
        shape=edge_leakage_bias_evidence_payload_is_well_formed,
        error=EdgeWalkForwardOosEvidenceError,
        code=_reason("predecessor"),
        optional=False,
    )


def _as_metrics_bindings(value: object) -> tuple[EdgeAuthorityBinding, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(
        parse_edge_authority_binding(  # type: ignore[misc]
            entry,
            shape=historical_walk_forward_metrics_payload_is_well_formed,
            error=EdgeWalkForwardOosEvidenceError,
            code=_reason("variant_metrics"),
            optional=False,
        )
        for entry in value
    )


_GOVERNANCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "approved_multiple_testing_count": _as_int,
    "min_oos_window_count": _as_int,
    "positive_expectancy_fraction_numerator": _as_int,
    "positive_expectancy_fraction_denominator": _as_int,
    "profit_factor_fraction_numerator": _as_int,
    "profit_factor_fraction_denominator": _as_int,
}
_FRAME_CONVERTERS: dict[str, Callable[[object], object]] = {
    "window_index": _as_int,
    "in_sample_start_ns": _as_int,
    "in_sample_end_ns": _as_int,
    "out_of_sample_start_ns": _as_int,
    "out_of_sample_end_ns": _as_int,
}
_OUTCOME_CONVERTERS: dict[str, Callable[[object], object]] = {
    "window_index": _as_int,
    "sharpe_retention_holds": _as_bool,
    "hit_rate_retention_holds": _as_bool,
    "drawdown_holds": _as_bool,
    "positive_expectancy": _as_bool,
    "profit_factor_above_minimum": _as_bool,
}
_EVALUATION_CONVERTERS: dict[str, Callable[[object], object]] = {
    "metrics_computed": _as_bool,
    "window_count": _as_int,
    "window_digests": _as_str_tuple,
    "evaluation_status": _as_enum(EdgeVariantEvaluationStatus),
    "window_outcomes": _as_records(EdgeWalkForwardWindowOutcome, _OUTCOME_CONVERTERS),
    "positive_expectancy_window_count": _as_int,
    "required_positive_expectancy_window_count": _as_int,
    "profit_factor_window_count": _as_int,
    "required_profit_factor_window_count": _as_int,
    "failure_codes": _as_str_tuple,
}


def _as_governance(value: object) -> object:
    return None if value is None else _parse_exact(EdgeWalkForwardOosGovernance, value, _GOVERNANCE_CONVERTERS)


_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "predecessor_binding": _parse_predecessor_binding,
    "pinned_instrument_universe": _as_str_tuple,
    "registered_parameter_assignment_digests": _as_str_tuple,
    "multiple_testing_count": _as_int,
    "registered_variant_count": _as_int,
    "variant_metrics_bindings": _as_metrics_bindings,
    "evaluated_variant_count": _as_int,
    "window_frames": _as_records(EdgeWalkForwardWindowFrame, _FRAME_CONVERTERS),
    "synthetic_test_facts_used": _as_bool,
    "synthetic_test_approval_used": _as_bool,
    "governance": _as_governance,
    "variant_evaluations": _as_records(EdgeVariantWalkForwardEvaluation, _EVALUATION_CONVERTERS),
    "surviving_assignment_digests": _as_str_tuple,
    "surviving_variant_count": _as_int,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    "preregistration_sealed": _as_bool,
    "performance_data_consumed": _as_bool,
    "oos_evidence_consumed": _as_bool,
    "walk_forward_evaluated": _as_bool,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_walk_forward_oos_evidence_from_payload(payload: object) -> EdgeWalkForwardOosEvidence:
    """Strictly reconstruct EF-6 evidence from its serialized payload (exact fields, types and bindings).

    Reconstruction is not verification: consumers call ``verify_edge_walk_forward_oos_evidence`` on the result.
    """

    return _parse_exact(EdgeWalkForwardOosEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def edge_walk_forward_oos_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an EF-6 snapshot consumed by a later gate."""

    try:
        edge_walk_forward_oos_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def _reassemble_evidence(evidence: object) -> EdgeWalkForwardOosEvidence:
    return _assemble_evidence(
        predecessor_binding=evidence.predecessor_binding,  # type: ignore[attr-defined]
        root_intake_digest=evidence.root_intake_digest,  # type: ignore[attr-defined]
        variant_metrics_bindings=evidence.variant_metrics_bindings,  # type: ignore[attr-defined]
        evidence_id=evidence.evidence_id,  # type: ignore[attr-defined]
        correlation_id=evidence.correlation_id,  # type: ignore[attr-defined]
        governance=evidence.governance,  # type: ignore[attr-defined]
    )


def verify_edge_walk_forward_oos_evidence(evidence: object) -> EdgeEvidenceVerification:
    """Re-prove EF-6 evidence by strict parse and reassembly from its carried bindings, anchors and governance.

    Every derived field — chain identities, frame, per-variant outcomes, survivors, counts, flags, verdict and digests —
    must equal the reassembled artifact. Total: never raises.
    """

    return verify_edge_artifact_total(
        evidence,
        cls=EdgeWalkForwardOosEvidence,
        to_payload=_to_payload,
        parse_payload=edge_walk_forward_oos_evidence_from_payload,
        reassemble=_reassemble_evidence,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS",
    "EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST",
    "EdgeVariantEvaluationStatus",
    "EdgeVariantMetricsInput",
    "EdgeVariantWalkForwardEvaluation",
    "EdgeWalkForwardOosEvidence",
    "EdgeWalkForwardOosEvidenceError",
    "EdgeWalkForwardOosGovernance",
    "EdgeWalkForwardWindowFrame",
    "EdgeWalkForwardWindowOutcome",
    "build_edge_walk_forward_oos_evidence",
    "edge_walk_forward_oos_evidence_digest",
    "edge_walk_forward_oos_evidence_from_payload",
    "edge_walk_forward_oos_evidence_payload_is_well_formed",
    "edge_walk_forward_oos_evidence_to_dict",
    "edge_walk_forward_oos_rule_set",
    "verify_edge_walk_forward_oos_evidence",
]
