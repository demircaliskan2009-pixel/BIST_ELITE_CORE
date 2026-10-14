"""Edge pre-paper validation evidence (EDGE_PRE_PAPER_VALIDATION_EVIDENCE_V1): the mandatory precondition of EF-7 v2.

PRDV4 §1.13 Stage 3 and §1.20 require, before any paper admission, CSCV/PBO, a deflated Sharpe over all variants ever
tested, a Monte Carlo significance test, parameter sensitivity and synthetic stress. This artifact computes exactly
that, over ONE authenticated EF-6 walk-forward/OOS result and its sealed EF-5 preregistration, for the LIMITED S1
paper-only V1 route. It selects nothing: every gate is preregistered, deterministic and applied to the complete
registered set or to every EF-6 survivor. PASS means ONLY that the governed pre-paper process admitted a non-empty set
of survivors with an allocation cap fraction. It never means an edge, profitability, regime-conditional robustness,
venue-faithful stress, Stage-4 completion or any live authority.

Authority (shared kernel ``edge_artifact_core``):

* EF-6 is consumed by DIGEST, never embedded (EF-7 v2 embeds it once). Every builder call and every verification takes
  the EF-6 object as context and re-proves it through ``verify_edge_walk_forward_oos_evidence`` against the carried
  ``walk_forward_oos_evidence_digest``; it must share this correlation and root and be READY. A non-advancing EF-6
  propagates its verdict and nothing is computed. EF-5 is read from EF-6's authenticated snapshot.
* The governed ``EdgePrePaperValidationPolicy``, the ``EdgeTrialCountChain`` and the full-frame PIT dataset are
  required bindings re-proven through their public verifiers against their anchors.
* Frame dataset (``FRAME_DATASET_EQUALS_UNION_OF_EF6_SEGMENT_DATASETS_V1``): its record digests must equal the union of
  the record digests of every EF-6 IS/OOS segment dataset, under the same manifest and registry and this correlation,
  so the full-period runs see exactly the observations EF-6 evaluated and nothing else.

Frame and runs (``CSCV_FULL_FRAME_RUNS_V1``). The EF-6 span is ``[first IS start, last OOS end)`` of the authenticated
window frames; the frame is its trailing ``16 x floor(days / 16)`` UTC days, fixed by the authenticated geometry before
any performance is read and identical for every variant. Each registered variant gets ONE full-frame run built by the
accepted ``build_historical_decision_run`` and ``build_historical_execution_economics`` with EF-6's executable binding,
economics policy, economics approval and the variant's own parameter approval; every run must be READY + PASS.

Numerical methods (exact integer/rational arithmetic, no float, no decimal context, rendered once at scale 18):

* Daily returns are the accepted walk-forward methodology (``historical_walk_forward_*``): the daily endpoint rule,
  ``r_t = E_t / E_(t-1) - 1`` over one common denominator, never rounded before aggregation. The CSCV, DSR and
  sensitivity Sharpe use the authenticated EF-6 metric policy, whose risk-free return must be zero.
* CSCV/PBO (``CSCV_PBO_S16_LEXICOGRAPHIC_EXACT_V1``): 16 contiguous equal blocks; the 12 870 IS halves are the 8-subsets
  of the blocks in lexicographic order, each OOS half its complement. Variants are ranked by the exact Sharpe key
  ``sign(A) * A^2 / (n B - A^2)`` of each half (``A``, ``B`` the exact sums of returns and squared returns, ``n`` the
  day count), decided exactly: certified fixed-point intervals only accelerate, an exact tie (identical block returns)
  is decided structurally and any other overlap by exact integer cross-multiplication. ``theta*`` is EVERY IS-maximal
  variant; ``rank_OOS(theta) = 1 + #{v != theta: OOS_v >= OOS_theta}`` (ties against theta); a split is overfit iff some
  ``theta`` in ``theta*`` has ``2 x rank > N``; ``PBO = overfit / 12 870`` exactly. A half with zero variance and a
  nonzero mean makes the PBO undefined (FAIL). Bands: ``PBO < a`` normal (cap 1), ``a <= PBO < c`` capped (governed
  fraction), ``c <= PBO <= e`` FAIL (additional OOS required), ``PBO > e`` FAIL (overfit). Fewer than two registered
  variants is FAIL. A PBO failure stops every later gate. The full split matrix is committed.
* DSR (``DSR_PRDV4_STANDARDIZED_Z_EXACT_DECISION_V1``, human-authorized interpretation): PRDV4's ``SR_max`` is read as
  the maximal daily-return t-statistic ``z`` over the CSCV frame of the complete registered set (never an annualized
  Sharpe), and ``N`` as the attested cumulative trial count of the trial chain. ``DSR >= 0 <=> e^(z^2/2) >= 2N``; PASS iff
  ``z > 0`` and ``z^2 >= 2 ln(2N)``, decided by certified rational bounds of ``ln(2N)`` (it is irrational, so the bounds
  always separate). The DSR value itself is never rendered. The chain must contain this EF-5, its genesis must be the
  policy's pinned genesis, and one exact HUMAN_GOVERNANCE currentness attestation must bind it to this evaluation.
* Monte Carlo (``MC_SIGN_FLIP_SHA256_CTR_V1``, human-authorized; NOT a literal trade-order shuffle, under which the
  Sharpe is invariant): H0 = the closed-trade net returns ``X_i = realized_net_pnl / entry notional`` are independent
  and symmetric about zero. Sample ``s`` flips signs by the bits ``[s n, s n + n)`` of the SHA-256 counter stream of
  ``SHA-256(domain || EF-5 digest || assignment digest)`` (bit 1 keeps ``+|X_i|``); exactly 10 000 samples; ``p =
  #{sum_s >= sum_obs} / 10 000`` (ties count against the candidate); PASS iff ``p <= p_max``. With ``sum X_i^2`` fixed by
  the sign flips the trade Sharpe is strictly increasing in the sum, so the sum comparison is exact. Fewer closed
  trades than the governed floor, a zero-notional trade or zero observed variance is NOT_COMPUTABLE.
* Sensitivity (``SENSITIVITY_STAR_GRID_X20_V1``): for every SEARCHED parameter the probes ``v x (20 + k) / 20``,
  ``k = ±1..±4``, must each be an exact, schema-valid, registered EF-5 assignment differing only in that parameter (an
  unrepresentable, invalid or unregistered probe, or a zero base value, makes the survivor NOT_COMPUTABLE); the base
  Sharpe must be positive and every probe within ±10% must keep at least the governed retention ratio of it. The
  heatmap of every probe is committed.
* Stress (``STRESS_PIT_TRANSFORM_V1``): the accepted economics engine re-runs the survivor's full-frame result under the
  three governed scenarios; each passes iff its exact frame expectancy (sum of daily returns) is non-negative, every
  endpoint equity is positive and no maintenance-zone breach occurred. The PRDV4 regime-gate exception is not
  available: no input accepts a regime gate.
* Survivors are evaluated in that order (sensitivity, Monte Carlo, stress) after the candidate-level PBO and DSR pass;
  the admitted set is every survivor passing all of them, else FAIL.
* Cap (``ADMISSION_CAP_FRACTION_V1``): ``min(PBO band cap, LIMITED_S1_PAPER_V1 regime cap)``. The regime-conditional
  PBO is UNPROVEN; no BULL/BEAR/NEUTRAL label is consumed and no full PRDV4 compliance is claimed.

``status`` is integrity only; ``gate_verdict`` the outcome (FAIL > NEEDS_EXTERNAL_FACTS > NEEDS_GOVERNANCE_APPROVAL >
PASS); REJECTED implies NOT_EVALUATED; only READY + PASS advances and sets ``pre_paper_validation_passed``. One assembly
path serves the builder and verifier reassembly; ``verify_edge_pre_paper_validation_evidence`` is total. Paper-only,
deterministic, no IO, clock, network, float or decimal.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from enum import Enum
from fractions import Fraction
from itertools import combinations

from crypto_core.validation.edge_artifact_core import (
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
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeLeakageBiasEvidence,
    EdgeParameterSearchTreatment,
    edge_leakage_bias_evidence_from_payload,
)
from crypto_core.validation.edge_pre_paper_validation_policy import (
    EDGE_PRE_PAPER_ADMISSION_SCOPE,
    EDGE_PRE_PAPER_CSCV_BLOCK_COUNT,
    EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT,
    EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN,
    EdgePrePaperValidationPolicy,
    edge_pre_paper_stress_scenarios,
    edge_pre_paper_validation_policy_from_payload,
    edge_pre_paper_validation_policy_payload_is_well_formed,
    edge_pre_paper_validation_policy_to_dict,
    verify_edge_pre_paper_validation_policy,
)
from crypto_core.validation.edge_trial_count_chain import (
    EdgeTrialCountChain,
    EdgeTrialCountCurrentnessAttestation,
    canonical_edge_trial_count_currentness_attestation,
    edge_trial_count_chain_from_payload,
    edge_trial_count_chain_payload_is_well_formed,
    edge_trial_count_chain_to_dict,
    edge_trial_count_currentness_attestation_digest,
    edge_trial_count_currentness_attestation_from_payload,
    edge_trial_count_currentness_attestation_to_dict,
    edge_trial_count_currentness_reasons,
    verify_edge_trial_count_chain,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeWalkForwardOosEvidence,
    verify_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.historical_decision_run import build_historical_decision_run
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionStressScenario,
    HistoricalExecutionTradeStatus,
    build_historical_execution_economics,
    historical_execution_stress_outcome_digest,
    simulate_historical_execution_stress,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionEconomicsApproval,
    historical_execution_economics_policy_from_payload,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    historical_pit_dataset_from_payload,
    historical_pit_dataset_payload_is_well_formed,
    historical_pit_dataset_to_dict,
    verify_historical_pit_dataset,
)
from crypto_core.validation.historical_walk_forward_metric_policy import (
    HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1,
    HistoricalWalkForwardMetricPolicy,
    historical_walk_forward_metric_policy_from_payload,
)
from crypto_core.validation.historical_walk_forward_metrics import (
    historical_walk_forward_annualized_sharpe,
    historical_walk_forward_daily_endpoints,
    historical_walk_forward_equity_units,
    historical_walk_forward_render_ratio,
    historical_walk_forward_render_signed_sqrt,
    historical_walk_forward_risk_free,
    historical_walk_forward_scaled_daily_returns,
)
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableParameterApproval,
    strategy_executable_binding_from_payload,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileParameterAssignment,
    ProfileParameterKind,
    StrategyExecutableProfileError,
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)

_SCHEMA_VERSION = "edge-pre-paper-validation-evidence.v1"
_GATE_ID = "EF-PRE-PAPER"
_PREDECESSOR_GATE_ID = "EF-6"
_REASON_PREFIX = "edge_pre_paper_validation_evidence"
_SELF_DIGEST_FIELD = "pre_paper_validation_evidence_digest"
_INT64_MAX = 9223372036854775807
_MAX_TEXT_LENGTH = 256
_DAY_NS = 86_400_000_000_000
_CSCV_PRECISION_BITS = 192
_CSCV_KEY_BITS = 128
_MC_DOMAIN = b"crypto_core:ef_pre_paper:mc_sign_flip:v1"
_SENSITIVITY_STEPS = (-4, -3, -2, -1, 1, 2, 3, 4)
_FRAGILITY_STEPS = frozenset({-2, -1, 1, 2})
_DSR_INITIAL_TERMS = 32
_DSR_MAX_TERMS = 4096

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "edge_pre_paper_validation_evidence_rules.v1",
    "admission_scope": EDGE_PRE_PAPER_ADMISSION_SCOPE,
    "regime_conditional_pbo_status": EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN,
    "predecessor_rule_id": "ef6_consumed_by_digest_reproven_as_context_ready_same_root_and_correlation.v1",
    "frame_dataset_rule_id": "FRAME_DATASET_EQUALS_UNION_OF_EF6_SEGMENT_DATASETS_V1",
    "frame_rule_id": "trailing_16_floor_span_days_over_16_utc_days_of_the_authenticated_ef6_span.v1",
    "run_rule_id": "CSCV_FULL_FRAME_RUNS_V1_one_accepted_decision_run_and_economics_per_registered_variant.v1",
    "return_methodology_id": "historical_walk_forward_daily_endpoints_exact_common_denominator_returns.v1",
    "cscv_method_id": "CSCV_PBO_S16_LEXICOGRAPHIC_EXACT_V1",
    "cscv_rank_rule_id": "theta_star_every_is_maximal_variant_rank_counts_ties_against_overfit_iff_twice_rank_gt_n.v1",
    "pbo_band_rule_id": "normal_below_a_capped_below_c_additional_oos_through_e_rejected_above_e.v1",
    "pbo_stops_later_gates_rule_id": "prdv4_pbo_rejection_never_proceeds_to_stress_or_any_later_gate.v1",
    "dsr_method_id": "DSR_PRDV4_STANDARDIZED_Z_EXACT_DECISION_V1",
    "dsr_interpretation_id": "sr_max_is_the_max_daily_return_t_statistic_over_the_cscv_frame_not_annualized.v1",
    "dsr_decision_rule_id": "pass_iff_z_positive_and_z_squared_at_least_2_ln_2n_certified_rational_bounds.v1",
    "trial_count_authority_id": "EDGE_TRIAL_COUNT_CHAIN_V1",
    "monte_carlo_method_id": "MC_SIGN_FLIP_SHA256_CTR_V1",
    "monte_carlo_null_id": "closed_trade_net_returns_independent_and_symmetric_about_zero.v1",
    "monte_carlo_statistic_id": "signed_sum_of_trade_returns_equivalent_to_trade_sharpe_under_fixed_sum_of_squares.v1",
    "monte_carlo_sample_count": EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT,
    "monte_carlo_not_literal_shuffle_id": "sign_flip_is_not_the_prdv4_trade_order_or_label_shuffle.v1",
    "sensitivity_method_id": "SENSITIVITY_STAR_GRID_X20_V1",
    "sensitivity_steps": list(_SENSITIVITY_STEPS),
    "sensitivity_fragility_steps": sorted(_FRAGILITY_STEPS),
    "stress_method_id": "STRESS_PIT_TRANSFORM_V1",
    "stress_pass_rule_id": "non_negative_exact_frame_expectancy_positive_equity_and_no_maintenance_zone_breach.v1",
    "regime_gate_exception_id": "prdv4_documented_regime_gate_exception_unavailable_no_enforcing_consumer.v1",
    "survivor_order_id": "sensitivity_then_monte_carlo_then_stress_after_candidate_pbo_and_dsr.v1",
    "cap_rule_id": "ADMISSION_CAP_FRACTION_V1_min_of_pbo_band_cap_and_limited_s1_regime_cap.v1",
    "numeric_rule_id": "exact_integer_rational_arithmetic_render_once_scale18_no_float_no_decimal_context.v1",
    "cscv_precision_bits": _CSCV_PRECISION_BITS,
}
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])
EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))

_COMPUTED_FLAGS = frozenset({"preregistration_sealed", "performance_data_consumed", "oos_evidence_consumed"})
EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *(flag for flag in EDGE_STRUCTURAL_NON_CLAIM_FLAGS if flag[0] not in _COMPUTED_FLAGS),
    ("pbo_passed", False),
    ("stress_passed", False),
    ("regime_conditional_pbo_proven", False),
    ("full_prdv4_compliance_claimed", False),
    ("venue_liquidation_facts_proven", False),
    ("dsr_value_rendered", False),
    ("prdv4_stage4_complete", False),
)
_FLAG_NAMES = frozenset(name for name, _ in EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS)


def edge_pre_paper_validation_rule_set() -> dict[str, object]:
    """A fresh copy of the rule set committed by ``EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST``."""

    return {key: list(value) if isinstance(value, list) else value for key, value in _RULE_SET_V1.items()}


class EdgePrePaperValidationEvidenceError(EdgeArtifactError):
    """Raised on malformed caller input, a non-serializable upstream object, or a forbidden scope token."""


class EdgePrePaperCheckStatus(str, Enum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    NOT_COMPUTABLE = "NOT_COMPUTABLE"
    NOT_EVALUATED = "NOT_EVALUATED"


class EdgePboBand(str, Enum):
    NORMAL = "NORMAL"
    CAPPED = "CAPPED"
    ADDITIONAL_OOS_REQUIRED = "ADDITIONAL_OOS_REQUIRED"
    REJECTED = "REJECTED"
    NOT_COMPUTED = "NOT_COMPUTED"


@dataclass(frozen=True)
class EdgePrePaperFrameRun:
    """One registered variant's authenticated full-frame run and its exact frame statistics."""

    variant_id: str
    parameter_assignment_digest: str
    decision_run_digest: str
    economics_result_digest: str
    closed_trade_count: int
    daily_return_count: int
    daily_endpoint_digest: str
    annualized_sharpe: str | None
    daily_return_t_statistic: str | None


@dataclass(frozen=True)
class EdgeSensitivityProbe:
    """One heatmap cell: a registered probe of one searched parameter and its exact frame Sharpe."""

    parameter_id: str
    step_percent: int
    probe_value: str
    probe_variant_id: str
    probe_assignment_digest: str
    annualized_sharpe: str | None
    within_fragility_band: bool
    retention_holds: bool


@dataclass(frozen=True)
class EdgeStressScenarioResult:
    """One governed Stage-3 scenario of one survivor, re-simulated by the accepted economics engine."""

    scenario_kind: str
    scenario_digest: str
    outcome_digest: str
    simulated: bool
    shock_time_ns: int | None
    maintenance_breached: bool
    expectancy_non_negative: bool
    status: EdgePrePaperCheckStatus
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EdgePrePaperSurvivorValidation:
    """The per-survivor gates of one EF-6 survivor, in their fixed order. Eligible only if every gate PASSED."""

    variant_id: str
    parameter_assignment_digest: str
    sensitivity_status: EdgePrePaperCheckStatus
    sensitivity_base_annualized_sharpe: str | None
    sensitivity_probes: tuple[EdgeSensitivityProbe, ...]
    monte_carlo_status: EdgePrePaperCheckStatus
    monte_carlo_closed_trade_count: int
    monte_carlo_exceedance_count: int
    monte_carlo_p_value: str | None
    monte_carlo_seed: str
    stress_status: EdgePrePaperCheckStatus
    stress_results: tuple[EdgeStressScenarioResult, ...]
    eligible: bool
    reason_codes: tuple[str, ...]


@dataclass(frozen=True)
class EdgePrePaperValidationEvidence:
    """Immutable, digest-bound pre-paper validation evidence. PAPER ONLY; LIMITED_S1_PAPER_V1; never an edge."""

    schema_version: str
    gate_id: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    evidence_id: str
    correlation_id: str
    root_intake_digest: str
    predecessor_gate_id: str
    walk_forward_oos_evidence_digest: str
    walk_forward_gate_verdict: str
    preregistration_digest: str
    variant_ledger_digest: str
    registered_variant_ids: tuple[str, ...]
    registered_parameter_assignment_digests: tuple[str, ...]
    registered_variant_count: int
    multiple_testing_count: int
    surviving_assignment_digests: tuple[str, ...]
    policy_binding: EdgeAuthorityBinding
    policy_digest: str
    trial_chain_binding: EdgeAuthorityBinding
    trial_chain_digest: str
    currentness_attestation: EdgeTrialCountCurrentnessAttestation | None
    currentness_attestation_digest: str
    frame_dataset_binding: EdgeAuthorityBinding
    frame_dataset_digest: str
    metric_policy_digest: str
    economics_policy_digest: str
    frame_start_ns: int
    frame_end_ns: int
    frame_day_count: int
    cscv_block_count: int
    cscv_block_days: int
    frame_runs: tuple[EdgePrePaperFrameRun, ...]
    cscv_split_count: int
    cscv_overfit_split_count: int
    pbo: str | None
    pbo_band: EdgePboBand
    split_is_best_masks: str
    split_worst_oos_ranks: str
    split_overfit_bits: str
    split_matrix_digest: str
    dsr_status: EdgePrePaperCheckStatus
    dsr_cumulative_trial_count: int
    dsr_max_t_statistic: str | None
    dsr_max_variant_ids: tuple[str, ...]
    dsr_z_squared_threshold_lower: str | None
    dsr_z_squared_threshold_upper: str | None
    survivors: tuple[EdgePrePaperSurvivorValidation, ...]
    admitted_assignment_digests: tuple[str, ...]
    admitted_variant_count: int
    pbo_cap_fraction: str | None
    regime_cap_fraction: str | None
    admission_cap_fraction: str | None
    admission_scope: str
    regime_conditional_pbo_status: str
    rule_set_id: str
    rule_set_digest: str
    synthetic_test_approval_used: bool
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    preregistration_sealed: bool
    performance_data_consumed: bool
    oos_evidence_consumed: bool
    pre_paper_validation_passed: bool
    pre_paper_validation_evidence_digest: str
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
    regime_conditional_pbo_proven: bool = False
    full_prdv4_compliance_claimed: bool = False
    venue_liquidation_facts_proven: bool = False
    dsr_value_rendered: bool = False
    prdv4_stage4_complete: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> EdgePrePaperValidationEvidenceError:
    return EdgePrePaperValidationEvidenceError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_TEXT_LENGTH
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


def _serialize(value: object) -> object:
    if type(value) is EdgeAuthorityBinding:
        return edge_authority_binding_to_payload(value)
    if type(value) is EdgeTrialCountCurrentnessAttestation:
        return edge_trial_count_currentness_attestation_to_dict(value)
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
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


_RECORD_TYPES = frozenset(
    {EdgePrePaperFrameRun, EdgeSensitivityProbe, EdgeStressScenarioResult, EdgePrePaperSurvivorValidation}
)
_ENUM_FIELDS: dict[type, tuple[tuple[str, type[Enum]], ...]] = {
    EdgePrePaperValidationEvidence: (
        ("status", EdgeEvidenceStatus),
        ("gate_verdict", EdgeGateVerdict),
        ("pbo_band", EdgePboBand),
        ("dsr_status", EdgePrePaperCheckStatus),
    ),
    EdgeStressScenarioResult: (("status", EdgePrePaperCheckStatus),),
    EdgePrePaperSurvivorValidation: (
        ("sensitivity_status", EdgePrePaperCheckStatus),
        ("monte_carlo_status", EdgePrePaperCheckStatus),
        ("stress_status", EdgePrePaperCheckStatus),
    ),
}


def _scale18(value: Fraction) -> str | None:
    """Exact ROUND_HALF_EVEN scale-18 text of one exact non-integer-domain value (the walk-forward render)."""

    return historical_walk_forward_render_ratio(
        value.numerator, value.denominator, HISTORICAL_WALK_FORWARD_NUMERIC_POLICY_V1
    )


def _fraction_text(text: str | None) -> Fraction | None:
    return None if text is None else Fraction(text)


# --- the exact CSCV/PBO kernel (CSCV_PBO_S16_LEXICOGRAPHIC_EXACT_V1) --------------------------------------------------


@dataclass(frozen=True)
class EdgeCscvComputation:
    """The exact split matrix of one CSCV run: per split the IS-maximal variant mask, the worst OOS rank and overfit."""

    variant_count: int
    block_count: int
    block_days: int
    split_count: int
    overfit_split_count: int
    is_best_masks: tuple[int, ...]
    worst_oos_ranks: tuple[int, ...]
    overfit: tuple[bool, ...]
    undefined_variant_indexes: tuple[int, ...]


@dataclass(frozen=True)
class _CscvVariant:
    product: int
    sums: tuple[int, ...]
    squares: tuple[int, ...]
    constants: tuple[int | None, ...]
    signatures: tuple[tuple[int, ...], ...]
    alpha: tuple[int, ...]
    beta: tuple[int, ...]


def _cscv_variant(
    path: Sequence[int], block_count: int, block_days: int, returns: tuple[int, tuple[int, ...]] | None = None
) -> _CscvVariant:
    """Exact per-block sums of one path's common-denominator returns (computed once) and their fixed-point bounds."""

    product, scaled = historical_walk_forward_scaled_daily_returns(path) if returns is None else returns
    sums: list[int] = []
    squares: list[int] = []
    constants: list[int | None] = []
    signatures: list[tuple[int, ...]] = []
    for block in range(block_count):
        part = scaled[block * block_days : (block + 1) * block_days]
        sums.append(sum(part))
        squares.append(sum([item * item for item in part]))
        constants.append(part[0] if part.count(part[0]) == len(part) else None)
        signatures.append(tuple(path[block * block_days : (block + 1) * block_days + 1]))
    precision = _CSCV_PRECISION_BITS
    return _CscvVariant(
        product=product,
        sums=tuple(sums),
        squares=tuple(squares),
        constants=tuple(constants),
        signatures=tuple(signatures),
        alpha=tuple((item << precision) // product for item in sums),
        beta=tuple((item << (2 * precision)) // (product * product) for item in squares),
    )


def _variant_intervals(
    variant: _CscvVariant, subsets: Sequence[tuple[int, ...]], days: int
) -> list[tuple[int | None, int | None] | None]:
    """The certified key interval of one variant for every half (one pass, local bindings)."""

    alpha, beta, constants = variant.alpha.__getitem__, variant.beta.__getitem__, variant.constants
    constant_blocks = any(item is not None for item in constants)
    return [
        _key_interval(sum(map(alpha, subset)), sum(map(beta, subset)), subset, constants, constant_blocks, days)
        for subset in subsets
    ]


def _key_interval(
    alpha: int,
    beta: int,
    blocks: Sequence[int],
    constants: Sequence[int | None],
    constant_blocks: bool,
    days: int,
) -> tuple[int | None, int | None] | None:
    """Certified bounds of ``sign(A) * A^2 / (n B - A^2) * 2^Q`` for one half, or ``None`` when undefined.

    Each floored fixed-point block term errs by less than one unit, so the half sums lie in ``[alpha, alpha + m)`` and
    ``[beta, beta + m)`` for ``m`` blocks. The key is increasing in ``|A|`` and decreasing in ``B``. ``None`` as the upper
    bound means unbounded in that direction (the exact fallback decides). A zero-variance half is exact: key 0 for a
    zero constant return, undefined otherwise.
    """

    if constant_blocks:
        values = {constants[block] for block in blocks}
        if len(values) == 1 and None not in values:
            return (0, 0) if values == {0} else None
    error = len(blocks)
    if alpha >= 0:
        sign, low_magnitude, high_magnitude = 1, alpha, alpha + error
    elif alpha + error <= 0:
        sign, low_magnitude, high_magnitude = -1, -(alpha + error), -alpha
    else:
        sign, low_magnitude, high_magnitude = 0, 0, max(-alpha, alpha + error)
    scale = 1 << _CSCV_KEY_BITS
    low_denominator = days * (beta + error) - low_magnitude * low_magnitude
    low_key = (low_magnitude * low_magnitude * scale) // low_denominator if low_denominator > 0 else 0
    high_denominator = days * beta - high_magnitude * high_magnitude
    high_key = -((-high_magnitude * high_magnitude * scale) // high_denominator) if high_denominator > 0 else None
    if sign > 0:
        return low_key, high_key
    if sign < 0:
        return (None if high_key is None else -high_key), -low_key
    return (None, None) if high_key is None else (-high_key, high_key)


def _exact_compare(left: _CscvVariant, right: _CscvVariant, blocks: Sequence[int], days: int) -> int:
    """Exact comparison of two variants' half keys by integer cross-multiplication (-1, 0 or 1)."""

    left_sum = sum(left.sums[block] for block in blocks)
    right_sum = sum(right.sums[block] for block in blocks)
    left_dispersion = days * sum(left.squares[block] for block in blocks) - left_sum * left_sum
    right_dispersion = days * sum(right.squares[block] for block in blocks) - right_sum * right_sum
    left_sign = (left_sum > 0) - (left_sum < 0)
    right_sign = (right_sum > 0) - (right_sum < 0)
    if left_sign != right_sign:
        return 1 if left_sign > right_sign else -1
    if left_sign == 0:
        return 0
    left_cross = left_sum * left_sum * right_dispersion
    right_cross = right_sum * right_sum * left_dispersion
    order = (left_cross > right_cross) - (left_cross < right_cross)
    return order if left_sign > 0 else -order


def _cscv_matrix(variants: Sequence[_CscvVariant], block_count: int, block_days: int) -> EdgeCscvComputation:
    """The split matrix of already decomposed variants (the single kernel behind the public function)."""

    count = len(variants)
    half_days = (block_count // 2) * block_days
    subsets = list(combinations(range(block_count), block_count // 2))
    masks = [sum(1 << block for block in subset) for subset in subsets]
    full = (1 << block_count) - 1
    index_of = {mask: index for index, mask in enumerate(masks)}
    columns = [_variant_intervals(variant, subsets, half_days) for variant in variants]
    intervals: list[list[tuple[int | None, int | None] | None]] = [list(row) for row in zip(*columns, strict=True)]
    undefined = {position for position, column in enumerate(columns) if any(item is None for item in column)}
    if undefined:
        return EdgeCscvComputation(
            count, block_count, block_days, len(subsets), 0, (), (), (), tuple(sorted(undefined))
        )
    equal_blocks = [
        [
            sum(1 << block for block in range(block_count) if a.signatures[block] == b.signatures[block])
            for b in variants
        ]
        for a in variants
    ]

    def compare(left: int, right: int, subset_index: int) -> int:
        mask = masks[subset_index]
        if equal_blocks[left][right] & mask == mask:
            return 0
        low_left, high_left = intervals[subset_index][left]  # type: ignore[misc]
        low_right, high_right = intervals[subset_index][right]  # type: ignore[misc]
        if low_left is not None and high_right is not None and low_left > high_right:
            return 1
        if high_left is not None and low_right is not None and high_left < low_right:
            return -1
        return _exact_compare(variants[left], variants[right], subsets[subset_index], half_days)

    best_masks: list[int] = []
    worst_ranks: list[int] = []
    overfit: list[bool] = []
    for subset_index, mask in enumerate(masks):
        complement = index_of[full ^ mask]
        best = [0]
        for candidate in range(1, count):
            order = compare(candidate, best[0], subset_index)
            if order > 0:
                best = [candidate]
            elif order == 0:
                best.append(candidate)
        worst = 0
        for theta in best:
            rank = 1 + sum(1 for other in range(count) if other != theta and compare(other, theta, complement) >= 0)
            worst = max(worst, rank)
        best_masks.append(sum(1 << theta for theta in best))
        worst_ranks.append(worst)
        overfit.append(2 * worst > count)
    return EdgeCscvComputation(
        variant_count=count,
        block_count=block_count,
        block_days=block_days,
        split_count=len(subsets),
        overfit_split_count=sum(overfit),
        is_best_masks=tuple(best_masks),
        worst_oos_ranks=tuple(worst_ranks),
        overfit=tuple(overfit),
        undefined_variant_indexes=(),
    )


def edge_cscv_pbo_split_matrix(
    equity_paths: Sequence[Sequence[int]], *, block_count: int = EDGE_PRE_PAPER_CSCV_BLOCK_COUNT
) -> EdgeCscvComputation:
    """The exact CSCV split matrix over daily endpoint equity paths (exact scale units, one path per variant).

    Every path has ``block_count x b + 1`` strictly positive endpoints. Raises ``EdgePrePaperValidationEvidenceError``
    on malformed input. ``undefined_variant_indexes`` lists the variants with a zero-variance, nonzero-mean half, in
    which case no split is evaluated.
    """

    if type(block_count) is not int or block_count < 2 or block_count % 2:
        raise _fail("cscv_block_count_invalid")
    paths = [tuple(path) for path in equity_paths]
    if len(paths) < 2:
        raise _fail("cscv_variant_count_insufficient")
    length = len(paths[0])
    if length < block_count + 1 or (length - 1) % block_count or any(len(path) != length for path in paths):
        raise _fail("cscv_paths_not_one_equal_block_frame")
    if any(type(units) is not int or units <= 0 for path in paths for units in path):
        raise _fail("cscv_equity_nonpositive")
    block_days = (length - 1) // block_count
    return _cscv_matrix([_cscv_variant(path, block_count, block_days) for path in paths], block_count, block_days)


# --- DSR (DSR_PRDV4_STANDARDIZED_Z_EXACT_DECISION_V1) ----------------------------------------------------------------


def _atanh_bounds(value: Fraction, terms: int) -> tuple[Fraction, Fraction]:
    """Rational bounds of ``atanh(value)`` for ``0 <= value < 1`` from ``terms`` series terms and the tail bound."""

    total = Fraction(0)
    power = value
    square = value * value
    for index in range(terms):
        total += power / (2 * index + 1)
        power *= square
    return total, total + power / ((2 * terms + 1) * (1 - square))


def edge_ln_bounds(value: int, terms: int) -> tuple[Fraction, Fraction]:
    """Certified rational bounds ``lo <= ln(value) <= hi`` of an integer ``value >= 1`` (exact series, no float).

    ``ln(value) = k ln 2 + ln(y)`` with ``y = value / 2^k`` in ``[1, 2)``; ``ln 2 = 2 atanh(1/3)`` and
    ``ln(y) = 2 atanh((y - 1) / (y + 1))``, each bounded by its partial sum and geometric tail.
    """

    if type(value) is not int or value < 1 or type(terms) is not int or terms < 1:
        raise _fail("ln_bounds_input_invalid")
    power = value.bit_length() - 1
    ratio = Fraction(value, 1 << power)
    low_two, high_two = _atanh_bounds(Fraction(1, 3), terms)
    low_y, high_y = _atanh_bounds((ratio - 1) / (ratio + 1), terms)
    return 2 * power * low_two + 2 * low_y, 2 * power * high_two + 2 * high_y


def edge_dsr_decision(z_squared: Fraction, trial_count: int) -> tuple[bool | None, Fraction, Fraction]:
    """``(passes, threshold_lo, threshold_hi)`` for ``z^2 >= 2 ln(2N)``; ``passes`` is None only if never separated."""

    terms = _DSR_INITIAL_TERMS
    while True:
        low, high = edge_ln_bounds(2 * trial_count, terms)
        threshold_low, threshold_high = 2 * low, 2 * high
        if z_squared > threshold_high:
            return True, threshold_low, threshold_high
        if z_squared < threshold_low:
            return False, threshold_low, threshold_high
        if terms >= _DSR_MAX_TERMS:
            return None, threshold_low, threshold_high
        terms *= 2


# --- Monte Carlo sign-flip (MC_SIGN_FLIP_SHA256_CTR_V1) ----------------------------------------------------------------


def edge_monte_carlo_seed(preregistration_digest: str, parameter_assignment_digest: str) -> bytes:
    """The deterministic seed: SHA-256 of the domain, the sealed EF-5 digest and the variant assignment digest."""

    return hashlib.sha256(
        _MC_DOMAIN + bytes.fromhex(preregistration_digest) + bytes.fromhex(parameter_assignment_digest)
    ).digest()


def edge_monte_carlo_sign_flip_exceedances(
    returns: Sequence[Fraction], seed: bytes, *, sample_count: int = EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT
) -> int:
    """``#{s: sum_i eps_si |X_i| >= sum_i X_i}`` over ``sample_count`` SHA-256 counter-stream sign samples (exact).

    The stream is ``SHA-256(seed || u64be(j))`` for ``j = 0, 1, ...``; sample ``s`` reads its ``n`` bits from offset
    ``s x n``, most significant first, and bit 1 keeps ``+|X_i|``. With ``m_i = |X_i| x L`` over one common denominator,
    ``sum_s >= sum_obs`` iff the flipped magnitudes sum to at most the negative observed magnitudes.
    """

    values = [Fraction(item) for item in returns]
    count = len(values)
    if count == 0 or type(sample_count) is not int or sample_count <= 0:
        raise _fail("monte_carlo_input_invalid")
    common = math.lcm(*(item.denominator for item in values))
    integers = [item.numerator * (common // item.denominator) for item in values]
    magnitudes = [abs(item) for item in integers]
    negative_mass = sum(-item for item in integers if item < 0)
    total_bits = sample_count * count
    blocks = (total_bits + 255) // 256
    stream = b"".join(hashlib.sha256(seed + index.to_bytes(8, "big")).digest() for index in range(blocks))
    chunks: list[tuple[int, list[int]]] = []
    for start in range(0, count, 8):
        width = min(8, count - start)
        table = [0] * (1 << width)
        for pattern in range(1 << width):
            table[pattern] = sum(
                magnitudes[start + position] for position in range(width) if not (pattern >> (width - 1 - position)) & 1
            )
        chunks.append((width, table))
    exceedances = 0
    for sample in range(sample_count):
        first = sample * count
        first_byte, last_byte = first // 8, (first + count + 7) // 8
        window = int.from_bytes(stream[first_byte:last_byte], "big") >> (last_byte * 8 - first - count)
        window &= (1 << count) - 1
        flipped = 0
        remaining = count
        for width, table in chunks:
            remaining -= width
            flipped += table[(window >> remaining) & ((1 << width) - 1)]
        if flipped <= negative_mass:
            exceedances += 1
    return exceedances


# --- authorities -------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    ef6: EdgeWalkForwardOosEvidence
    ef5: EdgeLeakageBiasEvidence
    metric_policy: HistoricalWalkForwardMetricPolicy | None


def _walk_forward_authority(
    ef6: object, *, anchor: str, root_intake_digest: str, correlation_id: str
) -> tuple[list[str], _Context | None]:
    """Re-prove the EF-6 context object against the carried anchor and read EF-5 and the metric policy from it."""

    if type(ef6) is not EdgeWalkForwardOosEvidence:
        return [_reason("walk_forward_oos_evidence_malformed")], None
    verification = verify_edge_walk_forward_oos_evidence(ef6)
    if not verification.intact:
        return [_reason(f"walk_forward_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != anchor:
        return [_reason("walk_forward_digest_mismatch")], None
    if ef6.correlation_id != correlation_id:
        return [_reason("walk_forward_correlation_mismatch")], None
    if ef6.root_intake_digest != root_intake_digest:
        return [_reason("walk_forward_root_intake_mismatch")], None
    if ef6.status is not EdgeEvidenceStatus.READY:
        return [_reason("walk_forward_rejected")], None
    # EF-6's READY verification re-proved EF-5 and every metrics bundle with its metric policy against their anchors.
    ef5 = edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(ef6.predecessor_binding))
    metric_policy: HistoricalWalkForwardMetricPolicy | None = None
    if ef6.variant_metrics_bindings:
        metrics = edge_authority_binding_snapshot(ef6.variant_metrics_bindings[0])
        metric_policy = historical_walk_forward_metric_policy_from_payload(metrics["policy_binding"]["snapshot"])
    return [], _Context(ef6=ef6, ef5=ef5, metric_policy=metric_policy)


def _bound_authority(
    binding: EdgeAuthorityBinding,
    *,
    label: str,
    parse: Callable[[dict], object],
    verify: Callable[[object], EdgeEvidenceVerification],
) -> tuple[list[str], object | None]:
    artifact = parse(edge_authority_binding_snapshot(binding))
    verification = verify(artifact)
    if not verification.intact:
        return [_reason(f"{label}_integrity_failure:{code}") for code in verification.reason_codes], None
    if verification.recomputed_digest != binding.expected_digest:
        return [_reason(f"{label}_digest_mismatch")], None
    if getattr(artifact, "status", None) is not EdgeEvidenceStatus.READY:
        return [_reason(f"{label}_rejected")], None
    return [], artifact


def _dataset_authority(
    binding: EdgeAuthorityBinding, correlation_id: str
) -> tuple[list[str], HistoricalPitDataset | None]:
    codes, dataset = _bound_authority(
        binding, label="frame_dataset", parse=historical_pit_dataset_from_payload, verify=verify_historical_pit_dataset
    )
    if dataset is None:
        return codes, None
    if dataset.correlation_id != correlation_id:  # type: ignore[attr-defined]
        return [_reason("frame_dataset_correlation_mismatch")], None
    return [], dataset  # type: ignore[return-value]


@dataclass(frozen=True)
class _Sources:
    """The EF-6-authenticated inputs of the full-frame runs, read from the variants' own economics snapshots."""

    segment_record_digests: frozenset[str]
    segment_dataset_digests: frozenset[str]
    executable_binding: object
    executable_binding_digest: str
    economics_policy: object
    economics_policy_digest: str
    economics_approval: object
    parameter_approvals: Mapping[str, object]


def _exact_record(cls: type, value: object) -> object:
    """One authenticated snapshot record as its exact dataclass (exact text fields), or None if absent."""

    names = [item.name for item in fields(cls)]
    if value is None:
        return None
    if type(value) is not dict or set(value) != set(names) or not all(type(value[name]) is str for name in names):
        raise _fail("walk_forward_source_record_malformed")
    return cls(**value)


def _economics_approval(value: object) -> HistoricalExecutionEconomicsApproval | None:
    """The authenticated economics approval of an EF-6 source snapshot, as its exact record."""

    if value is None:
        return None
    if type(value) is not dict or type(value.get("approval_kind")) is not str:
        raise _fail("walk_forward_source_record_malformed")
    try:
        kind = HistoricalExecutionApprovalKind(value["approval_kind"])
    except ValueError as exc:
        raise _fail("walk_forward_source_record_malformed") from exc
    record = _exact_record(HistoricalExecutionEconomicsApproval, {**value, "approval_kind": ""})
    return replace(record, approval_kind=kind)  # type: ignore[type-var]


def _sources(context: _Context) -> tuple[list[str], _Sources | None]:
    """Read the segment datasets and the run authorities from EF-6 authenticated metrics snapshots.

    The READY verification of EF-6 re-proved every metrics bundle and every IS/OOS economics source in them, so their
    canonical snapshots are read as data here and never re-parsed into a second authority; every object built from
    them is re-validated by the accepted builders that consume it.
    """

    ef6 = context.ef6
    segment_records: set[str] = set()
    segment_datasets: set[str] = set()
    approvals: dict[str, object] = {}
    binding = policy = policy_digest = approval = binding_digest = None
    for position, metrics_binding in enumerate(ef6.variant_metrics_bindings):
        windows = edge_authority_binding_snapshot(metrics_binding)["window_bindings"]
        for index, window in enumerate(windows):
            for side in ("in_sample_binding", "out_of_sample_binding"):
                snapshot = window[side]["snapshot"]
                run = snapshot["run_binding"]["snapshot"]
                if position == 0:
                    segment_datasets.add(run["dataset_binding"]["expected_digest"])
                    segment_records.update(run["dataset_binding"]["snapshot"]["record_digests"])
                if index or side != "in_sample_binding":
                    continue
                approvals[snapshot["parameter_assignment_digest"]] = _exact_record(
                    StrategyExecutableParameterApproval, snapshot["parameter_approval"]
                )
                if binding is None:
                    binding = strategy_executable_binding_from_payload(run["executable_binding"]["snapshot"])
                    binding_digest = run["executable_binding"]["expected_digest"]
                    policy = historical_execution_economics_policy_from_payload(snapshot["policy_binding"]["snapshot"])
                    policy_digest = snapshot["policy_binding"]["expected_digest"]
                    approval = _economics_approval(snapshot["economics_approval"])
    frame_digests = {
        digest
        for frame in ef6.window_frames
        for digest in (frame.in_sample_dataset_digest, frame.out_of_sample_dataset_digest)
    }
    if binding is None or segment_datasets != frame_digests:
        return [_reason("walk_forward_segment_sources_inconsistent")], None
    return [], _Sources(
        segment_record_digests=frozenset(segment_records),
        segment_dataset_digests=frozenset(segment_datasets),
        executable_binding=binding,
        executable_binding_digest=binding_digest,  # type: ignore[arg-type]
        economics_policy=policy,
        economics_policy_digest=policy_digest,  # type: ignore[arg-type]
        economics_approval=approval,
        parameter_approvals=approvals,
    )


# --- frame, runs and statistics ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Frame:
    start_ns: int
    end_ns: int
    day_count: int
    block_days: int


def _frame(ef6: EdgeWalkForwardOosEvidence) -> _Frame | None:
    if not ef6.window_frames:
        return None
    start = min(frame.in_sample_start_ns for frame in ef6.window_frames)
    end = max(frame.out_of_sample_end_ns for frame in ef6.window_frames)
    if (end - start) % _DAY_NS or end <= start:
        return None
    days = (end - start) // _DAY_NS
    frame_days = EDGE_PRE_PAPER_CSCV_BLOCK_COUNT * (days // EDGE_PRE_PAPER_CSCV_BLOCK_COUNT)
    if frame_days == 0:
        return None
    return _Frame(end - frame_days * _DAY_NS, end, frame_days, frame_days // EDGE_PRE_PAPER_CSCV_BLOCK_COUNT)


@dataclass(frozen=True)
class _Series:
    variant_id: str
    assignment_digest: str
    assignment: tuple[ProfileParameterAssignment, ...]
    economics: HistoricalExecutionEconomicsResult
    run_digest: str
    units: tuple[int, ...]
    product: int
    total: int
    squares: int
    blocks: _CscvVariant


def _frame_series(
    context: _Context,
    sources: _Sources,
    dataset: HistoricalPitDataset,
    frame_dataset_digest: str,
    frame: _Frame,
    *,
    correlation_id: str,
) -> tuple[list[str], list[_Series]]:
    """One accepted full-frame decision run and economics result per registered variant (complete set, in order)."""

    codes: list[str] = []
    series: list[_Series] = []
    for variant in context.ef5.registered_variants:
        run = build_historical_decision_run(
            dataset,
            sources.executable_binding,  # type: ignore[arg-type]
            expected_dataset_digest=frame_dataset_digest,
            expected_executable_binding_digest=sources.executable_binding_digest,
            run_id=f"pre-paper-frame-run:{frame.start_ns}:{frame.end_ns}:{variant.variant_id}",
            correlation_id=correlation_id,
            parameter_assignment=variant.parameter_assignment,
            instrument=context.ef6.evaluated_instrument,
            evaluation_start_ns=frame.start_ns,
            evaluation_end_ns=frame.end_ns,
            parameter_approval=sources.parameter_approvals.get(variant.parameter_assignment_digest),  # type: ignore[arg-type]
        )
        economics = build_historical_execution_economics(
            run,
            expected_run_digest=run.run_digest,
            economics_policy=sources.economics_policy,  # type: ignore[arg-type]
            expected_economics_policy_digest=sources.economics_policy_digest,
            economics_approval=sources.economics_approval,  # type: ignore[arg-type]
            result_id=f"pre-paper-frame-economics:{frame.start_ns}:{frame.end_ns}:{variant.variant_id}",
            correlation_id=correlation_id,
        )
        label = f"frame_run_not_computed:{variant.variant_id}"
        if not (
            economics.status is EdgeEvidenceStatus.READY
            and economics.gate_verdict is EdgeGateVerdict.PASS
            and economics.simulated_economics_computed is True
        ):
            codes.append(_reason(f"{label}:{economics.status.value}:{economics.gate_verdict.value}"))
            continue
        endpoints, endpoint_code = historical_walk_forward_daily_endpoints(economics, day_ns=_DAY_NS)
        units = None if endpoints is None else [historical_walk_forward_equity_units(item.equity) for item in endpoints]
        if endpoints is None or units is None or len(units) != frame.day_count + 1:
            codes.append(_reason(f"{label}:{endpoint_code or 'daily_endpoint_count_mismatch'}"))
            continue
        if any(item is None or item <= 0 for item in units):
            codes.append(_reason(f"{label}:equity_nonpositive"))
            continue
        returns = historical_walk_forward_scaled_daily_returns(units)  # type: ignore[arg-type]
        blocks = _cscv_variant(units, EDGE_PRE_PAPER_CSCV_BLOCK_COUNT, frame.block_days, returns)  # type: ignore[arg-type]
        series.append(
            _Series(
                variant_id=variant.variant_id,
                assignment_digest=variant.parameter_assignment_digest,
                assignment=variant.parameter_assignment,
                economics=economics,
                run_digest=run.run_digest,
                units=tuple(units),  # type: ignore[arg-type]
                product=returns[0],
                total=sum(blocks.sums),
                squares=sum(blocks.squares),
                blocks=blocks,
            )
        )
    return codes, series


def _sharpe_text(item: _Series, metric_policy: HistoricalWalkForwardMetricPolicy) -> str | None:
    risk_free = historical_walk_forward_risk_free(metric_policy.numeric_policy, metric_policy.risk_free_daily_return)
    if risk_free is None:
        return None
    text, _ = historical_walk_forward_annualized_sharpe(
        total=item.total,
        squares=item.squares,
        count=len(item.units) - 1,
        product=item.product,
        risk_free=risk_free,
        factor=metric_policy.sharpe_annualization_factor,
        numeric=metric_policy.numeric_policy,
    )
    return text


def _t_statistic(item: _Series) -> tuple[int, int, int] | None:
    """``(sign, numerator, denominator)`` of ``z^2 = A^2 (T - 1) / (T B - A^2)`` over the frame; None if undefined."""

    count = len(item.units) - 1
    dispersion = count * item.squares - item.total * item.total
    if dispersion == 0:
        return (0, 0, 1) if item.total == 0 else None
    sign = (item.total > 0) - (item.total < 0)
    return sign, item.total * item.total * (count - 1), dispersion


def _compare_signed(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    if left[0] != right[0]:
        return 1 if left[0] > right[0] else -1
    if left[0] == 0:
        return 0
    order = (left[1] * right[2] > right[1] * left[2]) - (left[1] * right[2] < right[1] * left[2])
    return order if left[0] > 0 else -order


def _closed_trade_returns(economics: HistoricalExecutionEconomicsResult) -> list[Fraction] | None:
    """``X_i = realized_net_pnl / entry notional`` of every CLOSED trade (exact); None for a zero-notional trade."""

    fills = {item.fill_digest: item for item in economics.fills}
    values: list[Fraction] = []
    for trade in economics.trades:
        if trade.status is not HistoricalExecutionTradeStatus.CLOSED:
            continue
        notional = Fraction(0)
        for digest in trade.entry_fill_digests:
            fill = fills[digest]
            notional += Fraction(fill.fill_price) * Fraction(fill.filled_quantity)  # type: ignore[arg-type]
        if notional <= 0:
            return None
        values.append(Fraction(trade.realized_net_pnl) / notional)
    return values


def _probe_value(text: str, kind: ProfileParameterKind, step: int, scale: int) -> str | None:
    """The exact probe ``value x (20 + step) / 20`` in the parameter's own grammar, or None if not exactly representable."""

    value = Fraction(text) * (20 + step) / 20
    if kind is ProfileParameterKind.POSITIVE_INTEGER:
        return str(value.numerator) if value.denominator == 1 else None
    units = value * 10**scale
    if units.denominator != 1 or units < 0:
        return None
    digits = str(units.numerator).rjust(scale + 1, "0")
    return f"{digits[:-scale]}.{digits[-scale:]}"


def _key(item: _Series) -> tuple[int, int, int] | None:
    """The exact Sharpe ordering key of a full frame: ``(sign, A^2, n B - A^2)``; None if undefined."""

    count = len(item.units) - 1
    dispersion = count * item.squares - item.total * item.total
    if dispersion == 0:
        return (0, 0, 1) if item.total == 0 else None
    return (item.total > 0) - (item.total < 0), item.total * item.total, dispersion


def _sensitivity(
    survivor: _Series,
    context: _Context,
    series_by_digest: Mapping[str, _Series],
    retention: Fraction,
) -> tuple[EdgePrePaperCheckStatus, str | None, tuple[EdgeSensitivityProbe, ...], list[str]]:
    profile = get_strategy_executable_profile(context.ef5.profile_id)
    kinds = {item.parameter_id: item.kind for item in profile.parameter_schema}
    scale = profile.numeric_policy.decimal_scale
    base_values = {item.parameter_id: item.value for item in survivor.assignment}
    base_key = _key(survivor)
    base_text = _sharpe_text(survivor, context.metric_policy)
    names = {item.parameter_assignment_digest: item.variant_id for item in context.ef5.registered_variants}
    searched = [
        bound.parameter_id
        for bound in context.ef5.parameter_bounds
        if EdgeParameterSearchTreatment(bound.treatment) is EdgeParameterSearchTreatment.SEARCHED
    ]
    if not searched:
        return EdgePrePaperCheckStatus.NOT_COMPUTABLE, base_text, (), [_reason("sensitivity_no_searched_parameter")]
    probes: list[EdgeSensitivityProbe] = []
    codes: list[str] = []
    fragile = False
    for parameter_id in searched:
        base = base_values[parameter_id]
        if Fraction(base) == 0:
            codes.append(_reason(f"sensitivity_base_value_zero:{parameter_id}"))
            continue
        for step in _SENSITIVITY_STEPS:
            value = _probe_value(base, kinds[parameter_id], step, scale)
            if value is None:
                codes.append(_reason(f"sensitivity_probe_unrepresentable:{parameter_id}:{5 * step}"))
                continue
            assignment = tuple(
                ProfileParameterAssignment(
                    item.parameter_id, value if item.parameter_id == parameter_id else item.value
                )
                for item in survivor.assignment
            )
            try:
                canonical = canonical_profile_parameter_assignment(profile, assignment)
            except StrategyExecutableProfileError:
                codes.append(_reason(f"sensitivity_probe_invalid:{parameter_id}:{5 * step}"))
                continue
            digest = profile_parameter_assignment_digest(canonical)
            probe = series_by_digest.get(digest)
            if probe is None:
                codes.append(_reason(f"sensitivity_probe_unregistered:{parameter_id}:{5 * step}"))
                continue
            probe_key = _key(probe)
            holds = False
            if base_key is not None and probe_key is not None and base_key[0] > 0:
                # S_k >= d S_0 with d > 0 and S_0 > 0: a non-positive probe fails; otherwise compare the squares.
                holds = probe_key[0] > 0 and probe_key[1] * base_key[2] * retention.denominator**2 >= (
                    retention.numerator**2 * base_key[1] * probe_key[2]
                )
            within = step in _FRAGILITY_STEPS
            if within and not holds:
                fragile = True
                codes.append(_reason(f"sensitivity_fragile:{parameter_id}:{5 * step}"))
            probes.append(
                EdgeSensitivityProbe(
                    parameter_id=parameter_id,
                    step_percent=5 * step,
                    probe_value=value,
                    probe_variant_id=names[digest],
                    probe_assignment_digest=digest,
                    annualized_sharpe=_sharpe_text(probe, context.metric_policy),
                    within_fragility_band=within,
                    retention_holds=holds,
                )
            )
    if codes and not fragile:
        return EdgePrePaperCheckStatus.NOT_COMPUTABLE, base_text, tuple(probes), codes
    if base_key is None or base_key[0] <= 0:
        return (
            EdgePrePaperCheckStatus.FAILED,
            base_text,
            tuple(probes),
            [
                *codes,
                _reason("sensitivity_base_sharpe_not_positive"),
            ],
        )
    if fragile:
        return EdgePrePaperCheckStatus.FAILED, base_text, tuple(probes), codes
    return EdgePrePaperCheckStatus.PASSED, base_text, tuple(probes), []


def _monte_carlo(
    survivor: _Series, context: _Context, policy: EdgePrePaperValidationPolicy
) -> tuple[EdgePrePaperCheckStatus, int, int, str | None, str, list[str]]:
    seed = edge_monte_carlo_seed(context.ef6.predecessor_digest, survivor.assignment_digest)
    returns = _closed_trade_returns(survivor.economics)
    if returns is None:
        return EdgePrePaperCheckStatus.NOT_COMPUTABLE, 0, 0, None, seed.hex(), [_reason("monte_carlo_zero_notional")]
    count = len(returns)
    if count < policy.monte_carlo_min_closed_trade_count:
        return (
            EdgePrePaperCheckStatus.NOT_COMPUTABLE,
            count,
            0,
            None,
            seed.hex(),
            [_reason("monte_carlo_closed_trade_count_insufficient")],
        )
    if len(set(returns)) == 1:
        return (
            EdgePrePaperCheckStatus.NOT_COMPUTABLE,
            count,
            0,
            None,
            seed.hex(),
            [_reason("monte_carlo_observed_variance_zero")],
        )
    exceedances = edge_monte_carlo_sign_flip_exceedances(returns, seed)
    p_value = Fraction(exceedances, EDGE_PRE_PAPER_MONTE_CARLO_SAMPLE_COUNT)
    passed = p_value <= Fraction(policy.monte_carlo_p_value_max)
    status = EdgePrePaperCheckStatus.PASSED if passed else EdgePrePaperCheckStatus.FAILED
    codes = [] if passed else [_reason("monte_carlo_p_value_above_maximum")]
    return status, count, exceedances, _scale18(p_value), seed.hex(), codes


def _stress(
    survivor: _Series, scenarios: Sequence[HistoricalExecutionStressScenario], frame: _Frame
) -> tuple[EdgePrePaperCheckStatus, tuple[EdgeStressScenarioResult, ...], list[str]]:
    results: list[EdgeStressScenarioResult] = []
    codes: list[str] = []
    for scenario in scenarios:
        outcome = simulate_historical_execution_stress(
            survivor.economics, expected_result_digest=survivor.economics.result_digest, scenario=scenario
        )
        reasons: list[str] = []
        expectancy_ok = False
        if not outcome.simulated:
            status = EdgePrePaperCheckStatus.NOT_COMPUTABLE
            reasons.extend(outcome.reason_codes)
        else:
            units = [historical_walk_forward_equity_units(item) for item in outcome.daily_endpoint_equities]
            if len(units) != frame.day_count + 1 or any(item is None or item <= 0 for item in units):
                reasons.append(_reason("stress_equity_nonpositive_or_endpoints_incomplete"))
            else:
                _, scaled = historical_walk_forward_scaled_daily_returns(units)  # type: ignore[arg-type]
                expectancy_ok = sum(scaled) >= 0
                if not expectancy_ok:
                    reasons.append(_reason("stress_expectancy_negative"))
            if outcome.maintenance_breached:
                reasons.append(_reason("stress_maintenance_zone_breached"))
            status = EdgePrePaperCheckStatus.FAILED if reasons else EdgePrePaperCheckStatus.PASSED
        kind = scenario.scenario_kind.value
        codes.extend(f"{code}:{kind}" for code in reasons)
        results.append(
            EdgeStressScenarioResult(
                scenario_kind=kind,
                scenario_digest=outcome.scenario_digest,
                outcome_digest=historical_execution_stress_outcome_digest(outcome),
                simulated=outcome.simulated,
                shock_time_ns=outcome.shock_time_ns,
                maintenance_breached=outcome.maintenance_breached,
                expectancy_non_negative=expectancy_ok,
                status=status,
                reason_codes=_sorted_unique(reasons),
            )
        )
    statuses = {item.status for item in results}
    if EdgePrePaperCheckStatus.FAILED in statuses:
        return EdgePrePaperCheckStatus.FAILED, tuple(results), codes
    if EdgePrePaperCheckStatus.NOT_COMPUTABLE in statuses:
        return EdgePrePaperCheckStatus.NOT_COMPUTABLE, tuple(results), codes
    return EdgePrePaperCheckStatus.PASSED, tuple(results), []


def _survivor_record(
    survivor: _Series,
    context: _Context,
    policy: EdgePrePaperValidationPolicy,
    series_by_digest: Mapping[str, _Series],
    frame: _Frame,
) -> EdgePrePaperSurvivorValidation:
    not_evaluated = EdgePrePaperCheckStatus.NOT_EVALUATED
    sensitivity, base_text, probes, codes = _sensitivity(
        survivor, context, series_by_digest, Fraction(policy.sensitivity_min_retention_ratio)
    )
    mc_status, mc_count, mc_exceedances, mc_p_value = not_evaluated, 0, 0, None
    mc_seed = edge_monte_carlo_seed(context.ef6.predecessor_digest, survivor.assignment_digest).hex()
    stress_status, stress_results = not_evaluated, ()
    if sensitivity is EdgePrePaperCheckStatus.PASSED:
        mc_status, mc_count, mc_exceedances, mc_p_value, mc_seed, mc_codes = _monte_carlo(survivor, context, policy)
        codes.extend(mc_codes)
        if mc_status is EdgePrePaperCheckStatus.PASSED:
            stress_status, stress_results, stress_codes = _stress(
                survivor, edge_pre_paper_stress_scenarios(policy), frame
            )
            codes.extend(stress_codes)
    eligible = (sensitivity, mc_status, stress_status) == (EdgePrePaperCheckStatus.PASSED,) * 3
    return EdgePrePaperSurvivorValidation(
        variant_id=survivor.variant_id,
        parameter_assignment_digest=survivor.assignment_digest,
        sensitivity_status=sensitivity,
        sensitivity_base_annualized_sharpe=base_text,
        sensitivity_probes=probes,
        monte_carlo_status=mc_status,
        monte_carlo_closed_trade_count=mc_count,
        monte_carlo_exceedance_count=mc_exceedances,
        monte_carlo_p_value=mc_p_value,
        monte_carlo_seed=mc_seed,
        stress_status=stress_status,
        stress_results=stress_results,  # type: ignore[arg-type]
        eligible=eligible,
        reason_codes=_sorted_unique(codes),
    )


def _propagate(prefix: str, verdict: EdgeGateVerdict, buckets: tuple[list[str], list[str], list[str]]) -> None:
    fail, needs_external, needs_governance = buckets
    code = _reason(f"{prefix}_not_advanced:{verdict.value}")
    if verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
        needs_external.append(code)
    elif verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
        needs_governance.append(code)
    else:
        fail.append(code)


# --- the evidence ------------------------------------------------------------------------------------------------------


@dataclass
class _Computed:
    frame: _Frame | None = None
    runs: tuple[EdgePrePaperFrameRun, ...] = ()
    cscv: EdgeCscvComputation | None = None
    pbo: Fraction | None = None
    band: EdgePboBand = EdgePboBand.NOT_COMPUTED
    dsr_status: EdgePrePaperCheckStatus = EdgePrePaperCheckStatus.NOT_EVALUATED
    dsr_count: int = 0
    dsr_max: str | None = None
    dsr_ids: tuple[str, ...] = ()
    dsr_low: str | None = None
    dsr_high: str | None = None
    survivors: tuple[EdgePrePaperSurvivorValidation, ...] = ()
    admitted: tuple[str, ...] = ()
    pbo_cap: Fraction | None = None


def _compute(
    context: _Context,
    sources: _Sources,
    dataset: HistoricalPitDataset,
    dataset_digest: str,
    policy: EdgePrePaperValidationPolicy,
    chain: EdgeTrialCountChain,
    *,
    evidence_id: str,
    correlation_id: str,
    fail: list[str],
) -> _Computed:
    """Every computation of an admissible evidence, in the declared order; failure reasons go to ``fail``."""

    computed = _Computed()
    frame = _frame(context.ef6)
    if frame is None:
        fail.append(_reason("frame_geometry_invalid"))
        return computed
    computed.frame = frame
    if len(context.ef5.registered_variants) < 2:
        fail.append(_reason("cscv_requires_at_least_two_registered_variants"))
        return computed
    run_codes, series = _frame_series(context, sources, dataset, dataset_digest, frame, correlation_id=correlation_id)
    if run_codes:
        fail.extend(run_codes)
        return computed
    computed.runs = tuple(
        EdgePrePaperFrameRun(
            variant_id=item.variant_id,
            parameter_assignment_digest=item.assignment_digest,
            decision_run_digest=item.run_digest,
            economics_result_digest=item.economics.result_digest,
            closed_trade_count=sum(
                1 for trade in item.economics.trades if trade.status is HistoricalExecutionTradeStatus.CLOSED
            ),
            daily_return_count=len(item.units) - 1,
            daily_endpoint_digest=_digest_of([str(units) for units in item.units]),
            annualized_sharpe=_sharpe_text(item, context.metric_policy),
            daily_return_t_statistic=None
            if (statistic := _t_statistic(item)) is None
            else historical_walk_forward_render_signed_sqrt(
                statistic[0] < 0, statistic[1], statistic[2], context.metric_policy.numeric_policy
            ),
        )
        for item in series
    )
    cscv = _cscv_matrix([item.blocks for item in series], EDGE_PRE_PAPER_CSCV_BLOCK_COUNT, frame.block_days)
    computed.cscv = cscv
    if cscv.undefined_variant_indexes:
        fail.extend(
            _reason(f"cscv_sharpe_undefined_zero_variance_nonzero_mean:{series[index].variant_id}")
            for index in cscv.undefined_variant_indexes
        )
        return computed
    pbo = Fraction(cscv.overfit_split_count, cscv.split_count)
    computed.pbo = pbo
    if pbo < Fraction(policy.pbo_normal_max_exclusive):
        computed.band, computed.pbo_cap = EdgePboBand.NORMAL, Fraction(1)
    elif pbo < Fraction(policy.pbo_capped_max_exclusive):
        computed.band, computed.pbo_cap = EdgePboBand.CAPPED, Fraction(policy.pbo_capped_allocation_fraction)
    elif pbo <= Fraction(policy.pbo_additional_oos_max_inclusive):
        computed.band = EdgePboBand.ADDITIONAL_OOS_REQUIRED
        fail.append(_reason("pbo_requires_additional_out_of_sample_period"))
        return computed
    else:
        computed.band = EdgePboBand.REJECTED
        fail.append(_reason("pbo_overfit_rejected"))
        return computed

    # DSR over the complete registered set and the attested cumulative trial count.
    statistics = [_t_statistic(item) for item in series]
    if any(item is None for item in statistics):
        computed.dsr_status = EdgePrePaperCheckStatus.NOT_COMPUTABLE
        fail.append(_reason("dsr_t_statistic_undefined"))
        return computed
    best = statistics[0]
    for item in statistics[1:]:
        if _compare_signed(item, best) > 0:  # type: ignore[arg-type]
            best = item
    computed.dsr_ids = tuple(
        item.variant_id
        for item, value in zip(series, statistics, strict=True)
        if _compare_signed(value, best) == 0  # type: ignore[arg-type]
    )
    computed.dsr_max = historical_walk_forward_render_signed_sqrt(
        best[0] < 0,  # type: ignore[index]
        best[1],  # type: ignore[index]
        best[2],  # type: ignore[index]
        context.metric_policy.numeric_policy,
    )
    if chain.advances is not True:
        return computed
    computed.dsr_count = chain.head_cumulative_trial_count
    if best[0] <= 0:  # type: ignore[index]
        computed.dsr_status = EdgePrePaperCheckStatus.FAILED
        fail.append(_reason("dsr_max_t_statistic_not_positive"))
        return computed
    passes, low, high = edge_dsr_decision(Fraction(best[1], best[2]), computed.dsr_count)  # type: ignore[index]
    computed.dsr_low, computed.dsr_high = _scale18(low), _scale18(high)
    if passes is None:
        computed.dsr_status = EdgePrePaperCheckStatus.NOT_COMPUTABLE
        fail.append(_reason("dsr_decision_not_separable"))
        return computed
    if not passes:
        computed.dsr_status = EdgePrePaperCheckStatus.FAILED
        fail.append(_reason("dsr_negative_after_all_trials"))
        return computed
    computed.dsr_status = EdgePrePaperCheckStatus.PASSED

    # Per-survivor gates, in the declared order, for every EF-6 survivor.
    by_digest = {item.assignment_digest: item for item in series}
    survivors = tuple(
        _survivor_record(by_digest[digest], context, policy, by_digest, frame)
        for digest in context.ef6.surviving_assignment_digests
    )
    computed.survivors = survivors
    computed.admitted = tuple(item.parameter_assignment_digest for item in survivors if item.eligible)
    if not computed.admitted:
        fail.append(_reason("no_survivor_passes_every_pre_paper_gate"))
    return computed


def _assemble_evidence(
    *,
    walk_forward_oos_evidence: object,
    walk_forward_anchor: object,
    root_intake_digest: object,
    frame_dataset_binding: object,
    policy_binding: object,
    trial_chain_binding: object,
    currentness_attestation: object,
    evidence_id: object,
    correlation_id: object,
) -> EdgePrePaperValidationEvidence:
    """The one evidence assembly path, shared by the builder and verifier reassembly."""

    anchor = _require_hex64(walk_forward_anchor, "walk_forward_oos_evidence_digest")
    root_anchor = _require_hex64(root_intake_digest, "root_intake_digest")
    dataset_ref = require_edge_authority_binding(
        frame_dataset_binding,
        shape=historical_pit_dataset_payload_is_well_formed,
        error=EdgePrePaperValidationEvidenceError,
        code=_reason("frame_dataset"),
        optional=False,
    )
    policy_ref = require_edge_authority_binding(
        policy_binding,
        shape=edge_pre_paper_validation_policy_payload_is_well_formed,
        error=EdgePrePaperValidationEvidenceError,
        code=_reason("policy"),
        optional=False,
    )
    chain_ref = require_edge_authority_binding(
        trial_chain_binding,
        shape=edge_trial_count_chain_payload_is_well_formed,
        error=EdgePrePaperValidationEvidenceError,
        code=_reason("trial_chain"),
        optional=False,
    )
    try:
        attestation = canonical_edge_trial_count_currentness_attestation(currentness_attestation)
    except EdgeArtifactError as exc:
        raise _fail("currentness_attestation_malformed") from exc
    evidence_id = _require_text(evidence_id, "evidence_id")
    correlation_id = _require_text(correlation_id, "correlation_id")

    codes, context = _walk_forward_authority(
        walk_forward_oos_evidence, anchor=anchor, root_intake_digest=root_anchor, correlation_id=correlation_id
    )
    policy_codes, policy = _bound_authority(
        policy_ref,  # type: ignore[arg-type]
        label="policy",
        parse=edge_pre_paper_validation_policy_from_payload,
        verify=verify_edge_pre_paper_validation_policy,
    )
    chain_codes, chain = _bound_authority(
        chain_ref,  # type: ignore[arg-type]
        label="trial_chain",
        parse=edge_trial_count_chain_from_payload,
        verify=verify_edge_trial_count_chain,
    )
    dataset_codes, dataset = _dataset_authority(dataset_ref, correlation_id)  # type: ignore[arg-type]
    codes.extend([*policy_codes, *chain_codes, *dataset_codes])
    sources: _Sources | None = None
    if context is not None and context.ef6.variant_metrics_bindings:
        source_codes, sources = _sources(context)
        codes.extend(source_codes)
    if context is not None and dataset is not None and sources is not None:
        if frozenset(dataset.record_digests) != sources.segment_record_digests:
            codes.append(_reason("frame_dataset_not_the_union_of_ef6_segment_datasets"))
        if (
            dataset.source_manifest_digest != context.ef6.source_manifest_digest
            or dataset.data_requirement_registry_digest != context.ef6.data_requirement_registry_digest
        ):
            codes.append(_reason("frame_dataset_source_identity_mismatch"))
    integrity = _sorted_unique(codes)
    rejected = bool(integrity) or context is None or policy is None or chain is None or dataset is None

    computed = _Computed()
    if rejected:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
    else:
        buckets: tuple[list[str], list[str], list[str]] = ([], [], [])
        fail, needs_external, needs_governance = buckets
        ef6 = context.ef6  # type: ignore[union-attr]
        if policy.advances is not True:  # type: ignore[union-attr]
            _propagate("policy", policy.gate_verdict, buckets)  # type: ignore[union-attr]
        if chain.advances is not True:  # type: ignore[union-attr]
            _propagate("trial_chain", chain.gate_verdict, buckets)  # type: ignore[union-attr]
        if chain.genesis.genesis_digest != policy.approved_trial_chain_genesis_digest:  # type: ignore[union-attr]
            fail.append(_reason("trial_chain_genesis_not_the_governed_genesis"))
        if ef6.predecessor_digest not in {item.preregistration_digest for item in chain.links}:  # type: ignore[union-attr]
            fail.append(_reason("trial_chain_missing_this_preregistration"))
        if chain.advances is True:  # type: ignore[union-attr]
            needs_governance.extend(
                edge_trial_count_currentness_reasons(
                    attestation,
                    chain=chain,  # type: ignore[arg-type]
                    evaluation_id=evidence_id,
                    correlation_id=correlation_id,
                    preregistration_digest=ef6.predecessor_digest,
                )
            )
        if ef6.advances is not True:
            _propagate("walk_forward", ef6.gate_verdict, buckets)
        elif context.metric_policy is None:  # type: ignore[union-attr]
            fail.append(_reason("walk_forward_metric_policy_unavailable"))
        elif Fraction(context.metric_policy.risk_free_daily_return) != 0:  # type: ignore[union-attr]
            fail.append(_reason("metric_policy_risk_free_nonzero_unsupported_v1"))
        elif sources is None:
            fail.append(_reason("walk_forward_segment_sources_unavailable"))
        else:
            computed = _compute(
                context,  # type: ignore[arg-type]
                sources,
                dataset,  # type: ignore[arg-type]
                dataset_ref.expected_digest,  # type: ignore[union-attr]
                policy,  # type: ignore[arg-type]
                chain,  # type: ignore[arg-type]
                evidence_id=evidence_id,
                correlation_id=correlation_id,
                fail=fail,
            )
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    ready = status is EdgeEvidenceStatus.READY
    advances = ready and verdict is EdgeGateVerdict.PASS
    ef6 = None if context is None else context.ef6
    ef5 = None if context is None else context.ef5
    cscv = computed.cscv
    split_payload = (
        ("", "", "")
        if cscv is None or cscv.undefined_variant_indexes
        else (
            ",".join(format(mask, "x") for mask in cscv.is_best_masks),
            ",".join(str(rank) for rank in cscv.worst_oos_ranks),
            "".join("1" if item else "0" for item in cscv.overfit),
        )
    )
    regime_cap = None if policy is None or computed.pbo_cap is None else Fraction(policy.regime_allocation_fraction)  # type: ignore[union-attr]
    admission_cap = None if regime_cap is None or not advances else min(computed.pbo_cap, regime_cap)  # type: ignore[type-var]
    synthetic = (
        (policy is not None and policy.synthetic_test_approval_used is True)  # type: ignore[union-attr]
        or (chain is not None and chain.synthetic_test_approval_used is True)  # type: ignore[union-attr]
        or (attestation is not None and attestation.approval_kind.value == "TEST_ONLY_SYNTHETIC")
    )
    frame = computed.frame
    seed = EdgePrePaperValidationEvidence(
        schema_version=_SCHEMA_VERSION,
        gate_id=_GATE_ID,
        status=status,
        gate_verdict=verdict,
        advances=advances,
        evidence_id=evidence_id,
        correlation_id=correlation_id,
        root_intake_digest=root_anchor,
        predecessor_gate_id=_PREDECESSOR_GATE_ID,
        walk_forward_oos_evidence_digest=anchor,
        walk_forward_gate_verdict="" if ef6 is None else ef6.gate_verdict.value,
        preregistration_digest="" if ef6 is None else ef6.predecessor_digest,
        variant_ledger_digest="" if ef5 is None else ef5.variant_ledger_digest,
        registered_variant_ids=() if ef5 is None else tuple(item.variant_id for item in ef5.registered_variants),
        registered_parameter_assignment_digests=() if ef5 is None else ef5.registered_parameter_assignment_digests,
        registered_variant_count=0 if ef5 is None else len(ef5.registered_variants),
        multiple_testing_count=0 if ef5 is None else ef5.multiple_testing_count,
        surviving_assignment_digests=() if ef6 is None else ef6.surviving_assignment_digests,
        policy_binding=policy_ref,  # type: ignore[arg-type]
        policy_digest=policy_ref.expected_digest,  # type: ignore[union-attr]
        trial_chain_binding=chain_ref,  # type: ignore[arg-type]
        trial_chain_digest=chain_ref.expected_digest,  # type: ignore[union-attr]
        currentness_attestation=attestation,
        currentness_attestation_digest=""
        if attestation is None
        else edge_trial_count_currentness_attestation_digest(attestation),
        frame_dataset_binding=dataset_ref,  # type: ignore[arg-type]
        frame_dataset_digest=dataset_ref.expected_digest,  # type: ignore[union-attr]
        metric_policy_digest="" if ef6 is None else ef6.metric_policy_digest,
        economics_policy_digest="" if ef6 is None else ef6.economics_policy_digest,
        frame_start_ns=0 if frame is None else frame.start_ns,
        frame_end_ns=0 if frame is None else frame.end_ns,
        frame_day_count=0 if frame is None else frame.day_count,
        cscv_block_count=EDGE_PRE_PAPER_CSCV_BLOCK_COUNT,
        cscv_block_days=0 if frame is None else frame.block_days,
        frame_runs=computed.runs,
        cscv_split_count=0 if cscv is None else cscv.split_count,
        cscv_overfit_split_count=0 if cscv is None else cscv.overfit_split_count,
        pbo=None if computed.pbo is None else _scale18(computed.pbo),
        pbo_band=computed.band,
        split_is_best_masks=split_payload[0],
        split_worst_oos_ranks=split_payload[1],
        split_overfit_bits=split_payload[2],
        split_matrix_digest=_digest_of(list(split_payload)),
        dsr_status=computed.dsr_status,
        dsr_cumulative_trial_count=computed.dsr_count,
        dsr_max_t_statistic=computed.dsr_max,
        dsr_max_variant_ids=computed.dsr_ids,
        dsr_z_squared_threshold_lower=computed.dsr_low,
        dsr_z_squared_threshold_upper=computed.dsr_high,
        survivors=computed.survivors,
        admitted_assignment_digests=computed.admitted if advances else (),
        admitted_variant_count=len(computed.admitted) if advances else 0,
        pbo_cap_fraction=None if computed.pbo_cap is None else _scale18(computed.pbo_cap),
        regime_cap_fraction=None if regime_cap is None else _scale18(regime_cap),
        admission_cap_fraction=None if admission_cap is None else _scale18(admission_cap),
        admission_scope=EDGE_PRE_PAPER_ADMISSION_SCOPE,
        regime_conditional_pbo_status=EDGE_REGIME_CONDITIONAL_PBO_UNPROVEN,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST,
        synthetic_test_approval_used=synthetic,
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        preregistration_sealed=ready,
        performance_data_consumed=bool(computed.runs),
        oos_evidence_consumed=cscv is not None and not cscv.undefined_variant_indexes,
        pre_paper_validation_passed=advances,
        pre_paper_validation_evidence_digest="",
    )
    return replace(
        seed, pre_paper_validation_evidence_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD)
    )


def _binding_of(
    value: object, cls: type, to_dict: Callable[[object], dict], shape: Callable, digest: object, label: str
):
    if type(value) is not cls:
        raise _fail(f"{label}_malformed")
    try:
        payload = to_dict(value)
    except Exception as exc:  # noqa: BLE001 - a hollow upstream object is a construction error, never a receipt
        raise _fail(f"{label}_not_serializable") from exc
    return build_edge_authority_binding(
        snapshot_payload=payload,
        expected_digest=digest,
        shape=shape,
        error=EdgePrePaperValidationEvidenceError,
        code=_reason(label),
    )


def build_edge_pre_paper_validation_evidence(
    walk_forward_oos_evidence: EdgeWalkForwardOosEvidence,
    *,
    expected_walk_forward_oos_evidence_digest: str,
    expected_root_intake_digest: str,
    frame_dataset: HistoricalPitDataset,
    expected_frame_dataset_digest: str,
    policy: EdgePrePaperValidationPolicy,
    expected_policy_digest: str,
    trial_chain: EdgeTrialCountChain,
    expected_trial_chain_digest: str,
    currentness_attestation: EdgeTrialCountCurrentnessAttestation | None,
    evidence_id: str,
    correlation_id: str,
) -> EdgePrePaperValidationEvidence:
    """Build the deterministic pre-paper validation evidence of one EF-6 result.

    There is deliberately no input for a statistic, a variant choice, a ranking, a seed, a regime label or a flag:
    everything is derived from authenticated authority. Malformed caller input or a non-serializable upstream object
    raises ``EdgePrePaperValidationEvidenceError``; a failing re-proof yields ``REJECTED``/``NOT_EVALUATED``.
    """

    if type(walk_forward_oos_evidence) is not EdgeWalkForwardOosEvidence:
        raise _fail("walk_forward_oos_evidence_malformed")
    return _assemble_evidence(
        walk_forward_oos_evidence=walk_forward_oos_evidence,
        walk_forward_anchor=expected_walk_forward_oos_evidence_digest,
        root_intake_digest=expected_root_intake_digest,
        frame_dataset_binding=_binding_of(
            frame_dataset,
            HistoricalPitDataset,
            historical_pit_dataset_to_dict,  # type: ignore[arg-type]
            historical_pit_dataset_payload_is_well_formed,
            expected_frame_dataset_digest,
            "frame_dataset",
        ),
        policy_binding=_binding_of(
            policy,
            EdgePrePaperValidationPolicy,
            edge_pre_paper_validation_policy_to_dict,  # type: ignore[arg-type]
            edge_pre_paper_validation_policy_payload_is_well_formed,
            expected_policy_digest,
            "policy",
        ),
        trial_chain_binding=_binding_of(
            trial_chain,
            EdgeTrialCountChain,
            edge_trial_count_chain_to_dict,  # type: ignore[arg-type]
            edge_trial_count_chain_payload_is_well_formed,
            expected_trial_chain_digest,
            "trial_chain",
        ),
        currentness_attestation=currentness_attestation,
        evidence_id=evidence_id,
        correlation_id=correlation_id,
    )


def edge_pre_paper_validation_evidence_to_dict(evidence: EdgePrePaperValidationEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an evidence, including its self-digest."""

    return _to_payload(evidence)


def edge_pre_paper_validation_evidence_digest(evidence: EdgePrePaperValidationEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only the self-digest field."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or not 0 <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


def _as_signed_int(value: object) -> int:
    if type(value) is not int or not -_INT64_MAX <= value <= _INT64_MAX:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


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
    names = [item.name for item in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


def _as_records(cls: type, converters: Mapping[str, Callable[[object], object]]) -> Callable[[object], object]:
    def convert(value: object) -> tuple[object, ...]:
        if type(value) is not list:
            raise _fail("payload_field_malformed")
        return tuple(_parse_exact(cls, entry, converters) for entry in value)

    return convert


def _binding_parser(shape: Callable[[dict], bool], label: str) -> Callable[[object], object]:
    def convert(value: object) -> object:
        return parse_edge_authority_binding(
            value, shape=shape, error=EdgePrePaperValidationEvidenceError, code=_reason(label), optional=False
        )

    return convert


def _as_attestation(value: object) -> object:
    if value is None:
        return None
    try:
        return edge_trial_count_currentness_attestation_from_payload(value)
    except EdgeArtifactError as exc:
        raise _fail("payload_field_malformed") from exc


_STATUS = _as_enum(EdgePrePaperCheckStatus)
_FRAME_RUN_CONVERTERS: dict[str, Callable[[object], object]] = {
    "closed_trade_count": _as_int,
    "daily_return_count": _as_int,
    "annualized_sharpe": _as_optional_str,
    "daily_return_t_statistic": _as_optional_str,
}
_PROBE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "step_percent": _as_signed_int,
    "annualized_sharpe": _as_optional_str,
    "within_fragility_band": _as_bool,
    "retention_holds": _as_bool,
}
_STRESS_CONVERTERS: dict[str, Callable[[object], object]] = {
    "simulated": _as_bool,
    "shock_time_ns": _as_optional_int,
    "maintenance_breached": _as_bool,
    "expectancy_non_negative": _as_bool,
    "status": _STATUS,
    "reason_codes": _as_str_tuple,
}
_SURVIVOR_CONVERTERS: dict[str, Callable[[object], object]] = {
    "sensitivity_status": _STATUS,
    "sensitivity_base_annualized_sharpe": _as_optional_str,
    "sensitivity_probes": _as_records(EdgeSensitivityProbe, _PROBE_CONVERTERS),
    "monte_carlo_status": _STATUS,
    "monte_carlo_closed_trade_count": _as_int,
    "monte_carlo_exceedance_count": _as_int,
    "monte_carlo_p_value": _as_optional_str,
    "stress_status": _STATUS,
    "stress_results": _as_records(EdgeStressScenarioResult, _STRESS_CONVERTERS),
    "eligible": _as_bool,
    "reason_codes": _as_str_tuple,
}
_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "registered_variant_ids": _as_str_tuple,
    "registered_parameter_assignment_digests": _as_str_tuple,
    "registered_variant_count": _as_int,
    "multiple_testing_count": _as_int,
    "surviving_assignment_digests": _as_str_tuple,
    "policy_binding": _binding_parser(edge_pre_paper_validation_policy_payload_is_well_formed, "policy"),
    "trial_chain_binding": _binding_parser(edge_trial_count_chain_payload_is_well_formed, "trial_chain"),
    "currentness_attestation": _as_attestation,
    "frame_dataset_binding": _binding_parser(historical_pit_dataset_payload_is_well_formed, "frame_dataset"),
    "frame_start_ns": _as_int,
    "frame_end_ns": _as_int,
    "frame_day_count": _as_int,
    "cscv_block_count": _as_int,
    "cscv_block_days": _as_int,
    "frame_runs": _as_records(EdgePrePaperFrameRun, _FRAME_RUN_CONVERTERS),
    "cscv_split_count": _as_int,
    "cscv_overfit_split_count": _as_int,
    "pbo": _as_optional_str,
    "pbo_band": _as_enum(EdgePboBand),
    "dsr_status": _STATUS,
    "dsr_cumulative_trial_count": _as_int,
    "dsr_max_t_statistic": _as_optional_str,
    "dsr_max_variant_ids": _as_str_tuple,
    "dsr_z_squared_threshold_lower": _as_optional_str,
    "dsr_z_squared_threshold_upper": _as_optional_str,
    "survivors": _as_records(EdgePrePaperSurvivorValidation, _SURVIVOR_CONVERTERS),
    "admitted_assignment_digests": _as_str_tuple,
    "admitted_variant_count": _as_int,
    "pbo_cap_fraction": _as_optional_str,
    "regime_cap_fraction": _as_optional_str,
    "admission_cap_fraction": _as_optional_str,
    "synthetic_test_approval_used": _as_bool,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    "pre_paper_validation_passed": _as_bool,
    **dict.fromkeys(_COMPUTED_FLAGS, _as_bool),
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def edge_pre_paper_validation_evidence_from_payload(payload: object) -> EdgePrePaperValidationEvidence:
    """Strictly reconstruct an evidence from its serialized payload (exact fields, types and bindings; no proof)."""

    return _parse_exact(EdgePrePaperValidationEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def edge_pre_paper_validation_evidence_payload_is_well_formed(payload: object) -> bool:
    """Binding shape predicate for an evidence snapshot consumed by EF-7 v2."""

    try:
        edge_pre_paper_validation_evidence_from_payload(payload)
    except Exception:  # noqa: BLE001 - well-formedness is exactly "the strict parser accepts it"
        return False
    return True


def verify_edge_pre_paper_validation_evidence(
    evidence: object, *, walk_forward_oos_evidence: object
) -> EdgeEvidenceVerification:
    """Re-prove an evidence by strict parse and reassembly against its EF-6 context object. Total: never raises.

    The EF-6 is consumed by digest, so the caller supplies the EF-6 object; the reassembly re-proves it against the
    carried ``walk_forward_oos_evidence_digest`` and re-derives every run, statistic, gate and digest.
    """

    def reassemble(parsed: object) -> EdgePrePaperValidationEvidence:
        return _assemble_evidence(
            walk_forward_oos_evidence=walk_forward_oos_evidence,
            walk_forward_anchor=parsed.walk_forward_oos_evidence_digest,  # type: ignore[attr-defined]
            root_intake_digest=parsed.root_intake_digest,  # type: ignore[attr-defined]
            frame_dataset_binding=parsed.frame_dataset_binding,  # type: ignore[attr-defined]
            policy_binding=parsed.policy_binding,  # type: ignore[attr-defined]
            trial_chain_binding=parsed.trial_chain_binding,  # type: ignore[attr-defined]
            currentness_attestation=parsed.currentness_attestation,  # type: ignore[attr-defined]
            evidence_id=parsed.evidence_id,  # type: ignore[attr-defined]
            correlation_id=parsed.correlation_id,  # type: ignore[attr-defined]
        )

    return verify_edge_artifact_total(
        evidence,
        cls=EdgePrePaperValidationEvidence,
        to_payload=_to_payload,
        parse_payload=edge_pre_paper_validation_evidence_from_payload,
        reassemble=reassemble,
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS",
    "EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST",
    "EdgeCscvComputation",
    "EdgePboBand",
    "EdgePrePaperCheckStatus",
    "EdgePrePaperFrameRun",
    "EdgePrePaperSurvivorValidation",
    "EdgePrePaperValidationEvidence",
    "EdgePrePaperValidationEvidenceError",
    "EdgeSensitivityProbe",
    "EdgeStressScenarioResult",
    "build_edge_pre_paper_validation_evidence",
    "edge_cscv_pbo_split_matrix",
    "edge_dsr_decision",
    "edge_ln_bounds",
    "edge_monte_carlo_seed",
    "edge_monte_carlo_sign_flip_exceedances",
    "edge_pre_paper_validation_evidence_digest",
    "edge_pre_paper_validation_evidence_from_payload",
    "edge_pre_paper_validation_evidence_payload_is_well_formed",
    "edge_pre_paper_validation_evidence_to_dict",
    "edge_pre_paper_validation_rule_set",
    "verify_edge_pre_paper_validation_evidence",
]
