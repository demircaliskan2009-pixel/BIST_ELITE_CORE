"""Governed paper execution authority (GOVERNED_PAPER_EXECUTION_AUTHORITY_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7 (governed admitted-variant paper
execution), under the controller-adjudicated architecture ``GPC_V1R`` of ``GOVERNED_ADMITTED_VARIANT_PAPER_EXECUTION_V1``.
This module owns the GOVERNANCE half of that contract. ``governed_admitted_variant_paper_execution`` owns the economics
replay, the sealed paper days and the evidence that binds both halves. Paper-only, deterministic, digest-bound and
fail-closed; ``IMPLEMENTATION_SCOPE=SYNTHETIC_CONSTRUCTION_ONLY`` and real paper execution stays BLOCKED.

``GovernedPaperGenesis`` is the one paper genesis of one EF-7 admitted variant. Every element is re-proven:

* EF-7: the ``EdgePaperAdmissionDecision`` v2, through ``verify_edge_paper_admission_decision``. It must be READY,
  PASS, advancing, admitted to paper and pre-paper validated, for the genesis sleeve, with the genesis instrument as its
  whole pinned universe. The named variant must be one of its admitted variants. Its admission cap fraction stays
  RG-7's to enforce;
* EF-8: the ``EdgeKillQuarantineDecision`` INITIAL_ACTIVATION of that admission (ACTIVE, advancing, same sleeve,
  effective at or before the genesis instant). It is the paper genesis lifecycle head; any other head ends the authority;
* the executable binding, re-proven through its verifier, carries the EF-7 binding, spec, profile-semantics and manifest
  digests. The parameter assignment must canonicalize to the admitted variant's digest, and the
  ``StrategyExecutableParameterApproval`` must match the binding, spec, profile semantics and assignment exactly;
* the economics: the ``HistoricalExecutionEconomicsPolicy`` must be the policy the admission was evaluated under (the
  digest the authenticated EF-6 snapshot inside EF-7 carries), re-proven and advancing, for the genesis instrument. The
  ``HistoricalExecutionEconomicsApproval`` must match it with no mismatch and be ``HUMAN_GOVERNANCE``;
* the risk-budget policy is rebuilt through its public builder and must equal the supplied policy exactly (its content,
  paper-safety flags, schema and canonical digest), and that digest must be the one EF-7 binds. The RG-2 envelope, the
  RG-3 equity basis policy, the RG-4 performance-path policy and the RG-6 ladder seed are re-proven through their
  verifiers and must advance, and the time-window producer source (``PaperSessionMetricsSummary``) must re-prove its
  public digest;
* capacity: EF-7's single capacity assumption for the instrument must use the one supported measure
  ``max_open_position_notional`` / ``quote_currency_notional`` / ``per_instrument_open_position``. Any other measure is
  never equated with it and BLOCKS (C6 stays a human decision);
* scope: the envelope declares exactly the one bootstrap sleeve (``GPC_SINGLE_BOOTSTRAP_SLEEVE_V1``; a multi-sleeve
  portfolio needs its own authorization), and the basis policy's reference notional equals the economics
  ``initial_equity`` (C5: structural equality, otherwise BLOCKED).

Three human commitments are recorded, each as a ``GovernedPaperApproval`` that must commit exactly to the digest of its
subject: the paper ADOPTION of the economics and parameter approvals (C1, over ``genesis_policy_digest``), the
one-use, time-bounded ``GovernedPaperBootstrapAuthority`` (C2: sleeve, genesis instant and a horizon of at least 30 UTC
days, the accepted Sharpe minimum sample), and the ``GovernedPaperReservationBand`` beta (C8). Only an exact
``HUMAN_GOVERNANCE`` approval establishes anything; ``TEST_ONLY_SYNTHETIC`` never does. No value is defaulted.

``GovernedPaperCycleAuthority`` is the PROSPECTIVE authority of one UTC-day cycle ``W_k = [E_k, E_(k+1))`` with
``E_k = genesis + k days``. It is derived ONLY from what exists at ``E_k``:

* the opening dataset: an authenticated paper PIT dataset of the genesis manifest and registry in which no record is
  visible after ``E_k``. Its latest mark visible at ``E_k`` under the engine's own rule is the opening mark ``m``;
* the reservation price ``L = m * (1 + beta)``, ROUND_HALF_EVEN on the scale-18 price grid, and the capacity check
  ``unit_size * L <= max_value``;
* the sealed governed paper history as of ``E_k`` (the generic RG-3 episodes, day closes and funding events of the
  sealed days), from which RG-3 (valuation and performance over ``[genesis, E_k)``), RG-4, RG-5, RG-6 (genesis from the
  seed, or the prior READY decision), RG-7 and RG-8 are DERIVED through their public builders;
* the human head attestation ``H_k`` (RG-7 ``PaperLifecycleHeadAuthority`` at ``E_k``), which must name the paper
  genesis receipt;
* RG-7's reservation: exactly one BUY and one SELL LIMIT tick of ``unit_size`` at ``L`` (reservation ceilings, never
  execution limits), journaled with the risk-budget decision, promotion candidate and readiness into one evidence
  journal, from which the cycle's ``PaperAllocatorIntentDraft`` and the per-cycle capacity policy derive.

Phases (``GPC_BOOTSTRAP_TO_ORDINARY_V1``), first match wins:

* ORDINARY: RG-3, RG-4, RG-6 and RG-8 READY, and RG-8 carries RG-7's positive final allocation;
* otherwise a bootstrap phase, only within ``[genesis, genesis + horizon)``:
  - B0: no sealed episode exists, so RG-3, RG-6 and RG-8 cannot be constructed; RG-4 (once the window is non-empty) is
    NOT_COMPUTABLE for exactly the missing bootstrap sleeve, and RG-5 is READY;
  - B1: RG-3 is NOT_COMPUTABLE for exactly the insufficient-sample reasons, and RG-4, RG-6 and RG-8 are NOT_COMPUTABLE
    for exactly the reasons that sleeve propagates, with the portfolio stop not evaluated. The RG-2 stop levels are
    applied by ``measure_paper_peak_distance`` to the RG-3 valuation index: a maximum peak distance strictly above any
    level blocks the bootstrap;
* otherwise BLOCKED. An RG-8 STOP, ALLOCATION_REJECTED or NEEDS_GOVERNANCE_APPROVAL is never excepted, and neither is a
  zero-variance, stale or otherwise not computable RG-3. The bootstrap is one-use by construction: B0 needs zero sealed
  episodes and B1 needs fewer than 30 daily buckets, so neither can recur once left.

Every phase also needs RG-7 READY with a positive final allocation and the paper genesis head attested. Each direction is
authorized on its own (``GPC_PER_DIRECTION_AUTHORITY_V1``): the long (BUY) ceiling is ``unit_size`` only when the BUY
reservation record is ELIGIBLE, reserved in full at ``unit_size * L`` and allocated in full by RG-7's own record of it (so
no kill override and no cap reduced it), and it is zero otherwise; the short (SELL) ceiling follows the SELL record in the
same way. The aggregate allocation never stands in for a direction, and nothing is clipped. At least one direction must
be authorized. An AUTHORIZED cycle grants one admission window ``W_k`` with those ceilings and the reservation price
``L``; it also needs the per-cycle human approval (C3) committing to ``cycle_policy_digest``, which covers both directions.
A missing, synthetic or mismatching approval is NEEDS_GOVERNANCE_APPROVAL with no window. A zero ceiling refuses every
entry in its direction inside the economics; the execution half refuses any other fill on an unauthorized side. The
window is a bound on a deterministic paper simulation: never an execution permission, a capital reservation, an order or
readiness.

Provenance or binding defects raise ``GovernedPaperExecutionAuthorityError``. Both verifiers rebuild from the exact
inputs and are total. Exact ``Fraction`` arithmetic, no float and no ``decimal`` context, and no IO, clock,
randomness, network or environment access.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction
from typing import cast

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.audit.paper_sleeve_promotion_candidate_journal_adapter import (
    append_paper_sleeve_promotion_candidate_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_promotion_readiness_journal_adapter import (
    append_paper_sleeve_promotion_readiness_to_evidence_journal,
)
from crypto_core.audit.paper_sleeve_risk_budget_decision_journal_adapter import (
    append_paper_sleeve_risk_budget_decision_to_evidence_journal,
)
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EdgeKillQuarantineDecision,
    EdgeLifecycleState,
    EdgeLifecycleTransition,
    verify_edge_kill_quarantine_decision,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EdgePaperAdmissionDecision,
    verify_edge_paper_admission_decision,
)
from crypto_core.validation.edge_strategy_spec_admission import edge_strategy_spec_admission_from_payload
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionAdmissionWindow,
    historical_execution_latest_visible_mark,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionEconomicsApproval,
    HistoricalExecutionEconomicsPolicy,
    HistoricalExecutionEconomicsPolicyError,
    canonical_historical_execution_economics_approval,
    historical_execution_decimal_is_canonical,
    historical_execution_economics_approval_mismatches,
    historical_execution_quantize_price,
    historical_execution_render_amount,
    verify_historical_execution_economics_policy,
)
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, verify_historical_pit_dataset
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    build_paper_allocator_intent_draft,
)
from crypto_core.validation.paper_capacity_gate import PaperCapacityGatePolicy, build_paper_capacity_gate_policy
from crypto_core.validation.paper_daily_return_series_evidence import build_paper_daily_return_series_evidence
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    build_paper_deterministic_time_window_evidence,
)
from crypto_core.validation.paper_end_to_end_episode import paper_end_to_end_episode_digest
from crypto_core.validation.paper_pnl_report import paper_mark_snapshot_digest, paper_pnl_report_digest
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperGovernedLifecycleState,
    PaperLifecycleHeadAuthority,
    PaperLifecycleHeadAuthorityInputs,
    PaperPortfolioAllocationDecision,
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationSleeveInputs,
    PaperPortfolioAllocationStatus,
    build_paper_lifecycle_head_authority,
    build_paper_portfolio_allocation_decision,
)
from crypto_core.validation.paper_portfolio_governance_decision import (
    PaperPortfolioGovernanceDecision,
    PaperPortfolioGovernanceInputs,
    PaperPortfolioGovernanceSleeveInputs,
    PaperPortfolioGovernanceStatus,
    build_paper_portfolio_governance_decision,
)
from crypto_core.validation.paper_portfolio_performance_path_policy import (
    PaperPortfolioPerformancePathPolicy,
    verify_paper_portfolio_performance_path_policy,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_return_series_methodology import build_paper_return_series_methodology
from crypto_core.validation.paper_session_metrics_summary import (
    PaperSessionMetricsSummary,
    paper_session_metrics_summary_digest,
)
from crypto_core.validation.paper_sharpe_evidence import build_paper_sharpe_evidence
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationSleeveInputs,
    PaperSleeveCorrelationStatus,
    build_paper_sleeve_correlation_evidence,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDailyValuationEvidence,
    PaperSleeveDayCloseValuation,
    PaperSleeveEpisodeEvidence,
    PaperSleeveValuationInputs,
    PaperSleeveValuationStatus,
    build_paper_sleeve_daily_valuation_evidence,
    paper_sleeve_daily_return_buckets,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownSleeveInputs,
    PaperSleeveDrawdownStatus,
    build_paper_sleeve_drawdown_evidence,
    measure_paper_peak_distance,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PaperSleeveEquityBasisPolicy,
    PaperSleeveFundingTreatment,
    paper_sleeve_equity_basis_methodology_policy_ids,
    verify_paper_sleeve_equity_basis_policy,
)
from crypto_core.validation.paper_sleeve_funding_evidence import (
    PaperSleeveFundingEvent,
    build_paper_sleeve_funding_evidence,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveState,
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
)
from crypto_core.validation.paper_sleeve_promotion_candidate import build_paper_sleeve_promotion_candidate
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderPriorDecision,
    PaperSleeveLadderSeed,
    PaperSleevePromotionDemotionDecision,
    PaperSleevePromotionDemotionInputs,
    build_paper_sleeve_promotion_demotion_decision,
    verify_paper_sleeve_ladder_seed,
)
from crypto_core.validation.paper_sleeve_promotion_readiness import build_paper_sleeve_promotion_readiness
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetPolicy,
    PaperSleeveRiskBudgetRecordStatus,
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableBinding,
    StrategyExecutableParameterApproval,
    canonical_strategy_executable_parameter_approval,
    verify_strategy_executable_binding,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileParameterAssignment,
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)

_PREFIX = "governed_paper_execution_authority"
_GENESIS_SCHEMA = "governed-paper-genesis.v1"
_CYCLE_SCHEMA = "governed-paper-cycle-authority.v1"
_GENESIS_DIGEST_FIELD = "genesis_digest"
_CYCLE_DIGEST_FIELD = "authority_digest"
_DAY_NS = 86_400_000_000_000
_MAX_WIRE_INT = 9_223_372_036_854_775_807
_MAX_IDENTIFIER = 64
_SUPPORTED_CAPACITY = ("max_open_position_notional", "quote_currency_notional", "per_instrument_open_position")
# The accepted paper Sharpe needs 30 consecutive daily buckets; a shorter bootstrap horizon could never reach ORDINARY.
_MIN_BOOTSTRAP_HORIZON_DAYS = 30
_BOOTSTRAP_RG3_REASONS = (
    "paper_sharpe_evidence:insufficient_bucket_count",
    "paper_sharpe_evidence:insufficient_daily_return_count",
    "paper_sleeve_performance_evidence:sharpe_not_computed",
)
# The exact NOT_COMPUTABLE reasons the bootstrap sleeve propagates; ``{sleeve}`` is the bootstrap sleeve. In B0 the
# sleeve has no RG-3 at all, in B1 an insufficient-sample one; any other reason is never a bootstrap reason.
_B0_DRAWDOWN_REASONS = (
    "paper_sleeve_drawdown_evidence:portfolio_requires_every_covered_sleeve_measured",
    "paper_sleeve_drawdown_evidence:sleeve_evidence_missing:{sleeve}",
)
_B1_DRAWDOWN_REASONS = (
    "paper_sleeve_drawdown_evidence:portfolio_requires_every_covered_sleeve_measured",
    "paper_sleeve_drawdown_evidence:sleeve_not_measured:{sleeve}",
)
_B1_LADDER_REASONS = ("paper_sleeve_promotion_demotion_decision:performance_evidence_not_computable",)
_B1_GOVERNANCE_REASONS = (
    "paper_portfolio_governance_decision:drawdown_evidence_not_computable",
    "paper_portfolio_governance_decision:ladder_decision_not_computable:{sleeve}",
    "paper_portfolio_governance_decision:portfolio_drawdown_not_computed",
)
_ELIGIBLE_RESERVATION_TICKS = 2
_NOT_DERIVED = "NOT_DERIVED"
# The economics admission ceiling of a reservation direction that is not authorized: no entry in that direction.
_ZERO_QUANTITY = "0.000000000000000000"

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "governed_paper_execution_authority_rules.v1",
    "contract_id": "GOVERNED_ADMITTED_VARIANT_PAPER_EXECUTION_V1",
    "architecture_id": "GPC_V1R",
    "scope_rule_id": "synthetic_construction_only_real_paper_execution_blocked_never_capital_order_or_live.v1",
    "genesis_rule_id": "one_reproven_ef7_v2_admitted_variant_one_ef8_genesis_head_one_sleeve_one_instrument.v1",
    "parameter_rule_id": "assignment_digest_is_the_admitted_variant_digest_under_an_exact_parameter_approval.v1",
    "economics_identity_rule_id": "paper_economics_policy_is_the_admission_evaluation_policy_under_exact_approval.v1",
    "risk_budget_policy_rule_id": "risk_budget_policy_rebuilt_exactly_by_its_public_builder_and_bound_to_ef7.v1",
    "capacity_measure_rule_id": "only_the_supported_open_position_notional_measure_is_consumed_any_other_blocks.v1",
    "capacity_measure": list(_SUPPORTED_CAPACITY),
    "capacity_check_rule_id": "unit_size_times_reservation_price_at_most_the_assumed_max_value_at_cycle_opening.v1",
    "basis_rule_id": "equity_basis_reference_notional_equals_economics_initial_equity.v1",
    "single_sleeve_rule_id": "GPC_SINGLE_BOOTSTRAP_SLEEVE_V1_envelope_declares_exactly_the_bootstrap_sleeve.v1",
    "approval_rule_id": "only_an_exact_human_governance_approval_establishes_test_only_synthetic_never_does.v1",
    "cycle_rule_id": "cycle_k_opens_at_genesis_plus_k_utc_days_and_closes_one_day_later.v1",
    "opening_rule_id": "derived_only_from_the_opening_dataset_sealed_history_and_head_attestation_at_opening.v1",
    "opening_dataset_rule_id": "authenticated_genesis_manifest_dataset_with_no_record_visible_after_opening.v1",
    "opening_mark_rule_id": "latest_mark_visible_at_opening_within_policy_staleness_the_engine_rule.v1",
    "reservation_rule_id": "reservation_price_is_opening_mark_times_one_plus_beta_half_even_on_the_price_grid.v1",
    "reservation_tick_rule_id": "one_buy_and_one_sell_limit_tick_of_unit_size_at_the_reservation_price.v1",
    "capacity_lineage_rule_id": "ticks_budget_candidate_readiness_journaled_draft_and_unit_notional_capacity_policy.v1",
    "phase_rule_id": "ordinary_needs_rg3_rg4_rg6_rg8_ready_else_bootstrap_b0_or_b1_within_horizon_else_blocked.v1",
    "bootstrap_b0_rule_id": "zero_sealed_episodes_rg4_not_computable_sleeve_missing_rg5_ready.v1",
    "bootstrap_b1_rule_id": "rg3_insufficient_sample_only_rg4_rg6_rg8_not_computable_stop_not_evaluated.v1",
    "bootstrap_rg3_reasons": list(_BOOTSTRAP_RG3_REASONS),
    "bootstrap_b0_rg4_reasons": list(_B0_DRAWDOWN_REASONS),
    "bootstrap_b1_rg4_reasons": list(_B1_DRAWDOWN_REASONS),
    "bootstrap_b1_rg6_reasons": list(_B1_LADDER_REASONS),
    "bootstrap_b1_rg8_reasons": list(_B1_GOVERNANCE_REASONS),
    "bootstrap_horizon_rule_id": "genesis_at_or_before_opening_strictly_before_genesis_plus_horizon_days.v1",
    "bootstrap_minimum_horizon_days": _MIN_BOOTSTRAP_HORIZON_DAYS,
    "bootstrap_stop_rule_id": "rg3_valuation_index_max_peak_distance_strictly_above_any_rg2_stop_level_blocks.v1",
    "never_excepted_rule_id": "rg8_stop_rejection_or_missing_governance_and_any_other_rg3_block_are_never_excepted.v1",
    "ladder_rule_id": "rg6_genesis_from_the_seed_until_a_ready_decision_then_its_lineage.v1",
    "head_rule_id": "the_attested_rg7_head_is_the_paper_genesis_receipt_any_successor_ends_the_authority.v1",
    "window_rule_id": "authorized_cycle_window_with_per_direction_ceilings_and_the_reservation_price.v1",
    "direction_rule_id": "a_direction_needs_its_own_eligible_fully_reserved_fully_allocated_record_else_zero.v1",
    "status_rule_id": "provenance_raises_then_blocked_then_needs_governance_approval_then_authorized.v1",
    "utc_day_ns": _DAY_NS,
}
GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])


def governed_paper_execution_authority_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST`` commits."""

    return json.loads(edge_canonical_json(_RULE_SET_V1))


class GovernedPaperExecutionAuthorityError(EdgeArtifactError):
    """Malformed input or a provenance or binding defect: an invalid authority is never represented."""


class GovernedPaperApprovalKind(str, Enum):
    """``TEST_ONLY_SYNTHETIC`` exists for tests only: it is recorded and never establishes anything."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperGenesisStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class GovernedPaperCycleStatus(str, Enum):
    """AUTHORIZED grants exactly one bounded admission window; every other status grants none."""

    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class GovernedPaperCyclePhase(str, Enum):
    ORDINARY = "ORDINARY"
    BOOTSTRAP_B0 = "BOOTSTRAP_B0"
    BOOTSTRAP_B1 = "BOOTSTRAP_B1"
    NONE = "NONE"


@dataclass(frozen=True)
class GovernedPaperApproval:
    """One human commitment to one exact subject digest; every commitment must equal the assembled value."""

    approval_reference: str
    approval_digest: str
    approval_kind: GovernedPaperApprovalKind
    approved_subject_kind: str
    approved_subject_id: str
    approved_subject_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class GovernedPaperBootstrapAuthority:
    """C2: the one-use, scoped, time-bounded bootstrap of one zero-history sleeve from one genesis instant."""

    bootstrap_id: str
    bootstrap_version: str
    sleeve_id: str
    genesis_ns: int
    horizon_days: int
    approval: GovernedPaperApproval | None


@dataclass(frozen=True)
class GovernedPaperReservationBand:
    """C8: the governed band beta above the opening mark that bounds every reservation of one instrument."""

    band_id: str
    band_version: str
    instrument: str
    beta: str
    approval: GovernedPaperApproval | None


@dataclass(frozen=True)
class GovernedPaperGenesisInputs:
    """Everything the paper genesis consumes; consumers re-prove a genesis by rebuilding it from exactly these."""

    genesis_id: str
    genesis_version: str
    correlation_id: str
    sleeve_id: str
    instrument: str
    genesis_ns: int
    paper_admission: EdgePaperAdmissionDecision
    lifecycle_genesis: EdgeKillQuarantineDecision
    admitted_variant_id: str
    executable_binding: StrategyExecutableBinding
    parameter_assignment: tuple[ProfileParameterAssignment, ...]
    parameter_approval: StrategyExecutableParameterApproval
    economics_policy: HistoricalExecutionEconomicsPolicy
    economics_approval: HistoricalExecutionEconomicsApproval
    risk_budget_policy: PaperSleeveRiskBudgetPolicy
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    equity_basis_policy: PaperSleeveEquityBasisPolicy
    performance_path_policy: PaperPortfolioPerformancePathPolicy
    ladder_seed: PaperSleeveLadderSeed
    metrics_summary: PaperSessionMetricsSummary
    methodology_id: str
    risk_free_policy_id: str
    bootstrap: GovernedPaperBootstrapAuthority
    reservation_band: GovernedPaperReservationBand
    adoption_approval: GovernedPaperApproval | None


GOVERNED_PAPER_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("real_paper_execution_authorized", False),
    ("execution_authorized", False),
    ("capital_allocated", False),
    ("real_capital_reserved", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("venue_orders_created", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("global_current_lifecycle_head_proven", False),
    ("machine_time_proven", False),
    ("venue_facts_current_proven", False),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("prdv4_stage4_complete", False),
)


@dataclass(frozen=True)
class GovernedPaperGenesis:
    """The digest-bound paper genesis of one EF-7 admitted variant. Paper governance only; never a permission."""

    schema_version: str
    status: GovernedPaperGenesisStatus
    ready: bool
    genesis_id: str
    genesis_version: str
    correlation_id: str
    sleeve_id: str
    instrument: str
    market_type: str
    genesis_ns: int
    bootstrap_horizon_days: int
    bootstrap_end_ns: int
    paper_admission_decision_digest: str
    admission_cap_fraction: str
    lifecycle_genesis_digest: str
    lifecycle_subject_digest: str
    admitted_variant_id: str
    parameter_assignment_digest: str
    unit_size: str
    executable_binding_digest: str
    strategy_spec_digest: str
    strategy_id: str
    profile_semantics_digest: str
    source_manifest_digest: str
    data_requirement_registry_digest: str
    parameter_approval_digest: str
    economics_policy_digest: str
    economics_approval_digest: str
    initial_equity: str
    risk_budget_policy_digest: str
    capacity_assumption_id: str
    capacity_max_value: str
    envelope_digest: str
    equity_basis_policy_digest: str
    performance_path_policy_digest: str
    ladder_seed_digest: str
    metrics_summary_digest: str
    methodology_id: str
    risk_free_policy_id: str
    reservation_band_digest: str
    reservation_beta: str
    bootstrap_authority_digest: str
    synthetic_test_facts_used: bool
    synthetic_test_approval_used: bool
    genesis_policy_digest: str
    adoption_approval: GovernedPaperApproval | None
    blocked_reason_codes: tuple[str, ...]
    governance_reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    genesis_digest: str
    paper_only: bool = True
    real_paper_execution_authorized: bool = False
    execution_authorized: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    venue_orders_created: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    global_current_lifecycle_head_proven: bool = False
    machine_time_proven: bool = False
    venue_facts_current_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    prdv4_stage4_complete: bool = False


@dataclass(frozen=True)
class GovernedPaperCycleInputs:
    """Everything one cycle authority consumes: only facts that exist at the cycle opening ``E_k``."""

    cycle_id: str
    correlation_id: str
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    day_index: int
    opening_dataset: HistoricalPitDataset
    sealed_episodes: tuple[PaperSleeveEpisodeEvidence, ...]
    sealed_day_closes: tuple[PaperSleeveDayCloseValuation, ...]
    sealed_funding_events: tuple[PaperSleeveFundingEvent, ...]
    prior_ladder: PaperSleeveLadderPriorDecision | None
    head_authority_inputs: PaperLifecycleHeadAuthorityInputs
    approval: GovernedPaperApproval | None


@dataclass(frozen=True)
class GovernedPaperCycleChain:
    """The RG-3 to RG-8 artifacts and the reservation lineage DERIVED for one cycle; ``None`` where not constructible."""

    valuation_inputs: PaperSleeveValuationInputs | None
    valuation: PaperSleeveDailyValuationEvidence | None
    performance_inputs: PaperSleevePerformanceInputs | None
    performance: PaperSleevePerformanceEvidence | None
    drawdown_inputs: PaperSleeveDrawdownInputs | None
    drawdown: PaperSleeveDrawdownEvidence | None
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation: PaperSleeveCorrelationEvidence
    ladder_inputs: PaperSleevePromotionDemotionInputs | None
    ladder: PaperSleevePromotionDemotionDecision | None
    head_authority: PaperLifecycleHeadAuthority
    risk_budget_state: PaperSleeveState
    risk_budget_decision: PaperSleeveRiskBudgetDecision
    allocator_draft: PaperAllocatorIntentDraft
    capacity_policy: PaperCapacityGatePolicy
    allocation_inputs: PaperPortfolioAllocationInputs
    allocation: PaperPortfolioAllocationDecision
    governance_inputs: PaperPortfolioGovernanceInputs | None
    governance: PaperPortfolioGovernanceDecision | None


@dataclass(frozen=True)
class GovernedPaperCycleAuthority:
    """The digest-bound PROSPECTIVE authority of one UTC-day cycle. A bound on a simulation, never a permission."""

    schema_version: str
    status: GovernedPaperCycleStatus
    authorized: bool
    phase: GovernedPaperCyclePhase
    cycle_id: str
    correlation_id: str
    genesis_digest: str
    day_index: int
    opening_ns: int
    closing_ns: int
    opening_dataset_digest: str
    sealed_history_digest: str
    sealed_episode_count: int
    head_authority_digest: str
    lifecycle_head_digest: str
    lifecycle_head_is_paper_genesis: bool
    head_attested: bool
    opening_mark_record_digest: str
    opening_mark_price: str
    reservation_price: str
    max_long_quantity: str
    max_short_quantity: str
    long_direction_authorized: bool
    short_direction_authorized: bool
    long_reservation_record_digest: str
    short_reservation_record_digest: str
    long_allocated_budget: str
    short_allocated_budget: str
    reservation_notional: str
    capacity_max_value: str
    capacity_within_assumption: bool
    performance_evidence_digest: str
    performance_status: str
    drawdown_evidence_digest: str
    drawdown_status: str
    correlation_evidence_digest: str
    correlation_status: str
    ladder_decision_digest: str
    ladder_status: str
    allocation_decision_digest: str
    allocation_status: str
    allocation_final_budget: str
    governance_decision_digest: str
    governance_status: str
    bootstrap_status: str
    bootstrap_max_peak_distance: str
    window_start_ns: int | None
    window_end_ns: int | None
    blocked_reason_codes: tuple[str, ...]
    governance_reason_codes: tuple[str, ...]
    cycle_policy_digest: str
    approval: GovernedPaperApproval | None
    rule_set_id: str
    rule_set_digest: str
    authority_digest: str
    paper_only: bool = True
    real_paper_execution_authorized: bool = False
    execution_authorized: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    venue_orders_created: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    global_current_lifecycle_head_proven: bool = False
    machine_time_proven: bool = False
    venue_facts_current_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    prdv4_stage4_complete: bool = False


# --- helpers ----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperExecutionAuthorityError:
    return GovernedPaperExecutionAuthorityError(_reason(code))


def _require_text(value: object, field_name: str, *, max_length: int = 256) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > max_length
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_identifier(value: object, field_name: str) -> str:
    text = _require_text(value, field_name, max_length=_MAX_IDENTIFIER)
    if not all(char.isascii() and (char.isalnum() or char in "-_.:") for char in text):
        raise _fail(f"{field_name}_invalid")
    return text


def _require_int(value: object, field_name: str, *, minimum: int) -> int:
    if type(value) is not int or value < minimum or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_exact(value: object, cls: type, field_name: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{field_name}_malformed")


def _require_tuple_of(value: object, cls: type, field_name: str) -> tuple:
    if type(value) is not tuple or any(type(item) is not cls for item in value):
        raise _fail(f"{field_name}_malformed")
    return value


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return {item.name: _serialize(getattr(value, item.name)) for item in fields(value)}
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    if value is None or type(value) in (str, int, bool):
        return value
    raise _fail("payload_value_not_canonical")


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _sorted_unique(codes: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(codes)))


def _plain(value: Fraction) -> str:
    """Exact plain decimal text of a terminating value (an amount on a scale-36 grid at most); never rounded."""

    numerator, denominator, scale = value.numerator, value.denominator, 0
    while denominator != 1:
        for prime, other in ((2, 5), (5, 2)):
            if denominator % prime == 0:
                denominator //= prime
                numerator *= other
                break
        else:
            raise _fail("amount_not_terminating")
        scale += 1
    digits = str(abs(numerator)).rjust(scale + 1, "0")
    text = f"{digits[:-scale]}.{digits[-scale:]}" if scale else digits
    return f"-{text}" if numerator < 0 else text


def _scale18(value: Fraction, code: str) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None or Fraction(rendered) != value:
        raise _fail(code)
    return rendered


def _canonical_approval(value: object, field_name: str) -> GovernedPaperApproval | None:
    if value is None:
        return None
    if type(value) is not GovernedPaperApproval:
        raise _fail(f"{field_name}_malformed")
    _require_text(value.approval_reference, f"{field_name}_reference")
    if not edge_is_hex64(value.approval_digest):
        raise _fail(f"{field_name}_digest_invalid")
    if type(value.approval_kind) is not GovernedPaperApprovalKind:
        raise _fail(f"{field_name}_kind_invalid")
    _require_text(value.approved_subject_kind, f"{field_name}_subject_kind")
    _require_text(value.approved_subject_id, f"{field_name}_subject_id")
    for name in ("approved_subject_digest", "approved_rule_set_digest"):
        if not edge_is_hex64(getattr(value, name)):
            raise _fail(f"{field_name}_{name}_invalid")
    return value


def _approval_codes(
    approval: GovernedPaperApproval | None, *, kind: str, subject_id: str, subject_digest: str
) -> list[str]:
    """Governance reasons for one approval: missing, synthetic, or any commitment that differs from the assembly."""

    if approval is None:
        return [_reason(f"{kind}_approval_missing")]
    codes: list[str] = []
    if approval.approval_kind is not GovernedPaperApprovalKind.HUMAN_GOVERNANCE:
        codes.append(_reason(f"{kind}_approval_not_human_governance"))
    expected = {
        "approved_subject_kind": kind,
        "approved_subject_id": subject_id,
        "approved_subject_digest": subject_digest,
        "approved_rule_set_digest": GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    }
    codes.extend(
        _reason(f"{kind}_approval_{name}_mismatch")
        for name, value in expected.items()
        if getattr(approval, name) != value
    )
    return codes


def _subject_digest(record: object) -> str:
    """The digest a human approves: the record's whole payload except its own approval."""

    payload = _to_payload(record)
    payload.pop("approval", None)
    return _digest_of(payload)


def _verified(verification: EdgeEvidenceVerification, code: str) -> None:
    if not verification.intact:
        raise _fail(code)


def _visibility(record: object) -> int:
    finalized = record.finalized_at_ns  # type: ignore[attr-defined]
    available = record.available_at_ns  # type: ignore[attr-defined]
    return available if finalized is None else max(available, finalized)


# --- the genesis --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Admission:
    """The admission facts the genesis reads from the authenticated EF-7 (and the EF-6 snapshot it carries)."""

    spec: StrategySpec
    unit_size: Fraction
    economics_policy_digest: str
    data_requirement_registry_digest: str


def _admission_evaluation(ef7: EdgePaperAdmissionDecision) -> tuple[str, str]:
    """The economics policy and registry digests of the EF-6 evaluation the authenticated EF-7 admitted."""

    snapshot = edge_authority_binding_snapshot(ef7.predecessor_binding)
    policy_digest = snapshot.get("economics_policy_digest") if type(snapshot) is dict else None
    registry_digest = snapshot.get("data_requirement_registry_digest") if type(snapshot) is dict else None
    if not edge_is_hex64(policy_digest) or not edge_is_hex64(registry_digest):
        raise _fail("admission_evaluation_unavailable")
    return policy_digest, registry_digest  # type: ignore[return-value]


def _binding_spec(binding: StrategyExecutableBinding) -> StrategySpec:
    """The StrategySpec of a verified binding, re-derived exactly as the economics engine derives it."""

    try:
        admission = edge_strategy_spec_admission_from_payload(
            edge_authority_binding_snapshot(binding.admission_binding)
        )
        result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    except Exception as exc:  # noqa: BLE001 - an underivable spec is a provenance defect, never a receipt
        raise _fail("strategy_spec_unavailable") from exc
    if result.accepted is not True or type(result.spec) is not StrategySpec:
        raise _fail("strategy_spec_unavailable")
    return result.spec


def _prove_admission(
    inputs: GovernedPaperGenesisInputs, sleeve_id: str, instrument: str, genesis_ns: int
) -> _Admission:
    ef7 = inputs.paper_admission
    _verified(verify_edge_paper_admission_decision(ef7), "paper_admission_not_authentic")
    if not (
        ef7.status is EdgeEvidenceStatus.READY
        and ef7.gate_verdict is EdgeGateVerdict.PASS
        and ef7.advances is True
        and ef7.candidate_admitted_to_paper is True
        and ef7.pre_paper_validation_passed is True
    ):
        raise _fail("paper_admission_not_admitted")
    if ef7.paper_sleeve_id != sleeve_id:
        raise _fail("paper_admission_sleeve_mismatch")
    if ef7.pinned_instrument_universe != (instrument,):
        raise _fail("paper_admission_universe_not_the_instrument")
    variants = [item for item in ef7.admitted_variants if item.variant_id == inputs.admitted_variant_id]
    if len(variants) != 1:
        raise _fail("admitted_variant_not_admitted")

    ef8 = inputs.lifecycle_genesis
    _verified(verify_edge_kill_quarantine_decision(ef8), "lifecycle_genesis_not_authentic")
    if not (
        ef8.advances is True
        and ef8.transition is EdgeLifecycleTransition.INITIAL_ACTIVATION
        and ef8.resulting_lifecycle_state is EdgeLifecycleState.ACTIVE
    ):
        raise _fail("lifecycle_genesis_not_an_active_initial_activation")
    if ef8.paper_sleeve_id != sleeve_id or ef8.cycle_admission_decision_digest != ef7.paper_admission_decision_digest:
        raise _fail("lifecycle_genesis_not_of_the_admission")
    if ef8.effective_at_ns > genesis_ns:
        raise _fail("lifecycle_genesis_after_paper_genesis")

    binding = inputs.executable_binding
    _verified(verify_strategy_executable_binding(binding), "executable_binding_not_authentic")
    if binding.advances is not True:
        raise _fail("executable_binding_not_advancing")
    if (
        binding.binding_digest != ef7.executable_binding_digest
        or binding.strategy_spec_digest != ef7.strategy_spec_digest
        or binding.registered_profile_semantics_digest != ef7.profile_semantics_digest
        or binding.source_manifest_digest != ef7.source_manifest_digest
    ):
        raise _fail("executable_binding_not_the_admitted_binding")
    try:
        profile = get_strategy_executable_profile(binding.profile_id)
        assignment = canonical_profile_parameter_assignment(profile, inputs.parameter_assignment)
    except Exception as exc:  # noqa: BLE001 - an invalid assignment is a provenance defect, never a receipt
        raise _fail("parameter_assignment_invalid") from exc
    if assignment != inputs.parameter_assignment:
        raise _fail("parameter_assignment_not_canonical")
    assignment_digest = profile_parameter_assignment_digest(assignment)
    if assignment_digest != variants[0].parameter_assignment_digest:
        raise _fail("parameter_assignment_not_the_admitted_variant")
    try:
        approval = canonical_strategy_executable_parameter_approval(inputs.parameter_approval)
    except Exception as exc:  # noqa: BLE001 - a malformed approval is a provenance defect, never a receipt
        raise _fail("parameter_approval_malformed") from exc
    if approval is None or (
        approval.approved_executable_binding_digest,
        approval.approved_strategy_spec_digest,
        approval.approved_profile_semantics_digest,
        approval.approved_parameter_assignment_digest,
    ) != (binding.binding_digest, binding.strategy_spec_digest, profile.profile_semantics_digest, assignment_digest):
        raise _fail("parameter_approval_not_the_admitted_variant")
    units = [item.value for item in assignment if item.parameter_id == "unit_size"]
    if len(units) != 1 or not historical_execution_decimal_is_canonical(units[0]) or Fraction(units[0]) <= 0:
        raise _fail("unit_size_unavailable")
    spec = _binding_spec(binding)
    if strategy_spec_digest(spec) != ef7.strategy_spec_digest:
        raise _fail("strategy_spec_digest_mismatch")
    policy_digest, registry_digest = _admission_evaluation(ef7)
    return _Admission(spec, Fraction(units[0]), policy_digest, registry_digest)


def _authentic_risk_budget_policy(policy: PaperSleeveRiskBudgetPolicy) -> PaperSleeveRiskBudgetPolicy:
    """The policy only when its public builder rebuilds it exactly: content, paper-safety flags, schema and digest."""

    try:
        rebuilt = build_paper_sleeve_risk_budget_policy(
            policy_id=policy.policy_id,
            sleeve_id=policy.sleeve_id,
            total_budget=policy.total_budget,
            per_intent_budget_cap=policy.per_intent_budget_cap,
            per_instrument_budget_cap=policy.per_instrument_budget_cap,
            require_journal_bound=policy.require_journal_bound,
            metadata=dict(policy.metadata),
        )
    except Exception as exc:  # noqa: BLE001 - an unbuildable policy is a provenance defect, never a receipt
        raise _fail("risk_budget_policy_not_authentic") from exc
    if rebuilt != policy:
        raise _fail("risk_budget_policy_not_authentic")
    return policy


def _capacity(ef7: EdgePaperAdmissionDecision, instrument: str) -> tuple[str, str, list[str]]:
    """``(assumption id, max value, blocked reasons)``: only the supported measure is ever consumed."""

    assumptions = [item for item in ef7.capacity_assumptions if item.instrument == instrument]
    if len(assumptions) != 1:
        return "", "", [_reason("capacity_assumption_not_unique")]
    item = assumptions[0]
    if (item.capacity_measure_id, item.unit_id, item.scope_id) != _SUPPORTED_CAPACITY:
        return item.assumption_id, item.max_value, [_reason("capacity_measure_unsupported")]
    return item.assumption_id, item.max_value, []


def _assemble_genesis(inputs: object) -> GovernedPaperGenesis:
    _require_exact(inputs, GovernedPaperGenesisInputs, "genesis_inputs")
    gi = cast(GovernedPaperGenesisInputs, inputs)
    for name, cls in (
        ("paper_admission", EdgePaperAdmissionDecision),
        ("lifecycle_genesis", EdgeKillQuarantineDecision),
        ("executable_binding", StrategyExecutableBinding),
        ("parameter_approval", StrategyExecutableParameterApproval),
        ("economics_policy", HistoricalExecutionEconomicsPolicy),
        ("economics_approval", HistoricalExecutionEconomicsApproval),
        ("risk_budget_policy", PaperSleeveRiskBudgetPolicy),
        ("portfolio_risk_envelope", PaperPortfolioRiskEnvelope),
        ("equity_basis_policy", PaperSleeveEquityBasisPolicy),
        ("performance_path_policy", PaperPortfolioPerformancePathPolicy),
        ("ladder_seed", PaperSleeveLadderSeed),
        ("metrics_summary", PaperSessionMetricsSummary),
        ("bootstrap", GovernedPaperBootstrapAuthority),
        ("reservation_band", GovernedPaperReservationBand),
    ):
        _require_exact(getattr(gi, name), cls, name)
    _require_tuple_of(gi.parameter_assignment, ProfileParameterAssignment, "parameter_assignment")
    genesis_id = _require_identifier(gi.genesis_id, "genesis_id")
    genesis_version = _require_identifier(gi.genesis_version, "genesis_version")
    correlation_id = _require_identifier(gi.correlation_id, "correlation_id")
    sleeve_id = _require_identifier(gi.sleeve_id, "sleeve_id")
    instrument = _require_identifier(gi.instrument, "instrument")
    _require_identifier(gi.admitted_variant_id, "admitted_variant_id")
    methodology_id = _require_identifier(gi.methodology_id, "methodology_id")
    risk_free_policy_id = _require_identifier(gi.risk_free_policy_id, "risk_free_policy_id")
    genesis_ns = _require_int(gi.genesis_ns, "genesis_ns", minimum=_DAY_NS)
    if genesis_ns % _DAY_NS != 0:
        raise _fail("genesis_not_utc_day_aligned")
    admission = _prove_admission(gi, sleeve_id, instrument, genesis_ns)
    ef7, ef8 = gi.paper_admission, gi.lifecycle_genesis
    blocked: list[str] = []
    governance: list[str] = []

    policy = gi.economics_policy
    _verified(verify_historical_execution_economics_policy(policy), "economics_policy_not_authentic")
    if policy.policy_digest != admission.economics_policy_digest:
        raise _fail("economics_policy_not_the_admission_evaluation_policy")
    if policy.advances is not True or policy.instrument != instrument or policy.market_type != ef7.market_type:
        raise _fail("economics_policy_not_applicable")
    try:
        economics_approval = canonical_historical_execution_economics_approval(gi.economics_approval)
    except HistoricalExecutionEconomicsPolicyError as exc:
        raise _fail("economics_approval_malformed") from exc
    if economics_approval is None or historical_execution_economics_approval_mismatches(
        economics_approval,
        policy=policy,
        strategy_spec_digest=ef7.strategy_spec_digest,
        instrument=instrument,
        market_type=ef7.market_type,
        data_requirement_registry_digest=admission.data_requirement_registry_digest,
    ):
        raise _fail("economics_approval_not_the_policy_approval")
    if economics_approval.approval_kind is not HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE:
        governance.append(_reason("economics_approval_not_human_governance"))

    budget = _authentic_risk_budget_policy(gi.risk_budget_policy)
    if budget.policy_digest != ef7.risk_budget_policy_digest or budget.sleeve_id != sleeve_id:
        raise _fail("risk_budget_policy_not_the_admission_policy")
    capacity_id, capacity_max, capacity_codes = _capacity(ef7, instrument)
    blocked.extend(capacity_codes)

    envelope = gi.portfolio_risk_envelope
    _verified(verify_paper_portfolio_risk_envelope(envelope), "portfolio_risk_envelope_not_authentic")
    if tuple(item.sleeve_id for item in envelope.sleeve_caps) != (sleeve_id,):
        raise _fail("single_sleeve_envelope_required")
    if instrument not in tuple(item.market_symbol for item in envelope.market_caps):
        raise _fail("portfolio_risk_envelope_market_missing")
    if envelope.advances is not True:
        governance.append(_reason("portfolio_risk_envelope_not_governed"))
    basis = gi.equity_basis_policy
    _verified(verify_paper_sleeve_equity_basis_policy(basis), "equity_basis_policy_not_authentic")
    if basis.sleeve_id != sleeve_id or basis.market_symbol != instrument:
        raise _fail("equity_basis_policy_not_of_the_sleeve")
    if basis.funding_treatment is not PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED:
        raise _fail("equity_basis_policy_funding_treatment_unsupported")
    if Fraction(basis.paper_performance_reference_notional) != Fraction(policy.initial_equity):
        blocked.append(_reason("equity_basis_reference_notional_not_initial_equity"))
    if basis.advances is not True:
        governance.append(_reason("equity_basis_policy_not_governed"))
    path = gi.performance_path_policy
    _verified(verify_paper_portfolio_performance_path_policy(path), "performance_path_policy_not_authentic")
    if path.envelope_digest != envelope.envelope_digest or tuple(
        item.sleeve_id for item in path.performance_weights
    ) != (sleeve_id,):
        raise _fail("performance_path_policy_not_of_the_envelope")
    if path.advances is not True:
        governance.append(_reason("performance_path_policy_not_governed"))
    seed = gi.ladder_seed
    _verified(verify_paper_sleeve_ladder_seed(seed), "ladder_seed_not_authentic")
    if seed.envelope_digest != envelope.envelope_digest or seed.sleeve_id != sleeve_id:
        raise _fail("ladder_seed_not_of_the_sleeve")
    if seed.tier_entered_at_ns != genesis_ns:
        raise _fail("ladder_seed_not_entered_at_genesis")
    if seed.advances is not True:
        governance.append(_reason("ladder_seed_not_governed"))
    summary = gi.metrics_summary
    if paper_session_metrics_summary_digest(summary) != summary.summary_digest:
        raise _fail("metrics_summary_not_authentic")
    if summary.market_symbol != instrument:
        raise _fail("metrics_summary_not_of_the_instrument")

    bootstrap = gi.bootstrap
    _require_identifier(bootstrap.bootstrap_id, "bootstrap_id")
    _require_identifier(bootstrap.bootstrap_version, "bootstrap_version")
    horizon = _require_int(bootstrap.horizon_days, "bootstrap_horizon_days", minimum=1)
    if bootstrap.sleeve_id != sleeve_id or bootstrap.genesis_ns != genesis_ns:
        raise _fail("bootstrap_not_of_the_genesis")
    if horizon < _MIN_BOOTSTRAP_HORIZON_DAYS:
        blocked.append(_reason("bootstrap_horizon_below_the_minimum_sample"))
    bootstrap_end = _require_int(genesis_ns + horizon * _DAY_NS, "bootstrap_end_ns", minimum=0)
    bootstrap_approval = _canonical_approval(bootstrap.approval, "bootstrap_approval")
    bootstrap_digest = _subject_digest(bootstrap)
    governance.extend(
        _approval_codes(
            bootstrap_approval, kind="bootstrap", subject_id=bootstrap.bootstrap_id, subject_digest=bootstrap_digest
        )
    )
    band = gi.reservation_band
    _require_identifier(band.band_id, "band_id")
    _require_identifier(band.band_version, "band_version")
    if band.instrument != instrument:
        raise _fail("reservation_band_not_of_the_instrument")
    if not historical_execution_decimal_is_canonical(band.beta) or Fraction(band.beta) <= 0:
        raise _fail("reservation_band_beta_invalid")
    band_approval = _canonical_approval(band.approval, "reservation_band_approval")
    band_digest = _subject_digest(band)
    governance.extend(
        _approval_codes(band_approval, kind="reservation_band", subject_id=band.band_id, subject_digest=band_digest)
    )
    adoption = _canonical_approval(gi.adoption_approval, "adoption_approval")
    synthetic_approval = any(
        item is not None and item.approval_kind is not GovernedPaperApprovalKind.HUMAN_GOVERNANCE
        for item in (adoption, bootstrap_approval, band_approval)
    ) or (economics_approval.approval_kind is not HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE)

    seed_record = GovernedPaperGenesis(
        schema_version=_GENESIS_SCHEMA,
        status=GovernedPaperGenesisStatus.READY,
        ready=False,
        genesis_id=genesis_id,
        genesis_version=genesis_version,
        correlation_id=correlation_id,
        sleeve_id=sleeve_id,
        instrument=instrument,
        market_type=ef7.market_type,
        genesis_ns=genesis_ns,
        bootstrap_horizon_days=horizon,
        bootstrap_end_ns=bootstrap_end,
        paper_admission_decision_digest=ef7.paper_admission_decision_digest,
        admission_cap_fraction=ef7.admission_cap_fraction,
        lifecycle_genesis_digest=ef8.kill_quarantine_decision_digest,
        lifecycle_subject_digest=ef8.lifecycle_subject_digest,
        admitted_variant_id=gi.admitted_variant_id,
        parameter_assignment_digest=profile_parameter_assignment_digest(gi.parameter_assignment),
        unit_size=_scale18(admission.unit_size, "unit_size_not_representable"),
        executable_binding_digest=gi.executable_binding.binding_digest,
        strategy_spec_digest=ef7.strategy_spec_digest,
        strategy_id=admission.spec.strategy_id,
        profile_semantics_digest=ef7.profile_semantics_digest,
        source_manifest_digest=ef7.source_manifest_digest,
        data_requirement_registry_digest=admission.data_requirement_registry_digest,
        parameter_approval_digest=_digest_of(_to_payload(gi.parameter_approval)),
        economics_policy_digest=policy.policy_digest,
        economics_approval_digest=_digest_of(_to_payload(economics_approval)),
        initial_equity=policy.initial_equity,
        risk_budget_policy_digest=budget.policy_digest,
        capacity_assumption_id=capacity_id,
        capacity_max_value=capacity_max,
        envelope_digest=envelope.envelope_digest,
        equity_basis_policy_digest=basis.policy_digest,
        performance_path_policy_digest=path.policy_digest,
        ladder_seed_digest=seed.ladder_seed_digest,
        metrics_summary_digest=summary.summary_digest,
        methodology_id=methodology_id,
        risk_free_policy_id=risk_free_policy_id,
        reservation_band_digest=band_digest,
        reservation_beta=band.beta,
        bootstrap_authority_digest=bootstrap_digest,
        synthetic_test_facts_used=policy.synthetic_test_facts_used,
        synthetic_test_approval_used=synthetic_approval,
        genesis_policy_digest="",
        adoption_approval=adoption,
        blocked_reason_codes=(),
        governance_reason_codes=(),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
        genesis_digest="",
    )
    policy_payload = _to_payload(seed_record)
    for name in ("status", "ready", "adoption_approval", "genesis_policy_digest", "genesis_digest"):
        policy_payload.pop(name)
    genesis_policy_digest = _digest_of(policy_payload)
    governance.extend(
        _approval_codes(adoption, kind="paper_adoption", subject_id=genesis_id, subject_digest=genesis_policy_digest)
    )
    blocked_codes, governance_codes = _sorted_unique(blocked), _sorted_unique(governance)
    status = (
        GovernedPaperGenesisStatus.BLOCKED
        if blocked_codes
        else GovernedPaperGenesisStatus.NEEDS_GOVERNANCE_APPROVAL
        if governance_codes
        else GovernedPaperGenesisStatus.READY
    )
    sealed = replace(
        seed_record,
        status=status,
        ready=status is GovernedPaperGenesisStatus.READY,
        genesis_policy_digest=genesis_policy_digest,
        blocked_reason_codes=blocked_codes,
        governance_reason_codes=governance_codes,
    )
    return replace(sealed, genesis_digest=edge_payload_digest(_to_payload(sealed), _GENESIS_DIGEST_FIELD))


def build_governed_paper_genesis(inputs: GovernedPaperGenesisInputs) -> GovernedPaperGenesis:
    """Build the paper genesis of one EF-7 admitted variant; provenance defects raise. See the module docstring."""

    return _assemble_genesis(inputs)


def governed_paper_genesis_to_dict(genesis: GovernedPaperGenesis) -> dict[str, object]:
    """Canonical JSON-ready mapping of a genesis, including its self-digest."""

    return _to_payload(genesis)


def governed_paper_genesis_digest(genesis: GovernedPaperGenesis) -> str:
    """Recompute the canonical genesis digest, excluding only ``genesis_digest``."""

    return edge_payload_digest(_to_payload(genesis), _GENESIS_DIGEST_FIELD)


def _verify_rebuilt(
    artifact: object, cls: type, rebuild: object, digest_field: str, code: str
) -> EdgeEvidenceVerification:
    stage = f"{code}_type_invalid"
    try:
        if type(artifact) is not cls:
            return EdgeEvidenceVerification(False, (_reason(stage),), "", "")
        stage = f"{code}_serialization_failed"
        carried = _to_payload(artifact)
        canonical = edge_canonical_json(carried)
        recomputed = edge_payload_digest(carried, digest_field)
        stage = f"{code}_rebuild_failed"
        expected = _to_payload(rebuild())  # type: ignore[operator]
        codes: set[str] = set()
        if carried[digest_field] != recomputed:
            codes.add(_reason(f"{code}_self_digest_mismatch"))
        for name in expected:
            if edge_canonical_json(expected[name]) != edge_canonical_json(carried[name]):
                codes.add(_reason(f"{code}_field_mismatch:{name}"))
        reason_codes = tuple(sorted(codes))
        return EdgeEvidenceVerification(
            intact=not reason_codes, reason_codes=reason_codes, recomputed_digest=recomputed, canonical_json=canonical
        )
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return EdgeEvidenceVerification(False, (_reason(stage),), "", "")


def verify_governed_paper_genesis(genesis: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a genesis by rebuilding it from its exact inputs. Total: never raises."""

    return _verify_rebuilt(
        genesis, GovernedPaperGenesis, lambda: _assemble_genesis(inputs), _GENESIS_DIGEST_FIELD, "genesis"
    )


# --- the cycle authority ----------------------------------------------------------------------------------------------


def _opening_dataset(dataset: object, genesis: GovernedPaperGenesis, opening_ns: int) -> HistoricalPitDataset:
    """The authenticated archive as of the opening: genesis manifest and registry, nothing visible after it."""

    _require_exact(dataset, HistoricalPitDataset, "opening_dataset")
    value = cast(HistoricalPitDataset, dataset)
    _verified(verify_historical_pit_dataset(value), "opening_dataset_not_authentic")
    if value.advances is not True:
        raise _fail("opening_dataset_not_advancing")
    if (
        value.source_manifest_digest != genesis.source_manifest_digest
        or value.data_requirement_registry_digest != genesis.data_requirement_registry_digest
    ):
        raise _fail("opening_dataset_not_of_the_genesis_manifest")
    if any(_visibility(record) > opening_ns for record in value.records):
        raise _fail("opening_dataset_record_visible_after_opening")
    return value


def governed_paper_sealed_history_digest(
    episodes: tuple[PaperSleeveEpisodeEvidence, ...],
    closes: tuple[PaperSleeveDayCloseValuation, ...],
    events: tuple[PaperSleeveFundingEvent, ...],
) -> str:
    """The digest a cycle binds for the generic RG-3 history sealed before it (episodes, day closes, funding)."""

    return _digest_of(
        {
            "episodes": [paper_end_to_end_episode_digest(item.end_to_end_episode) for item in episodes],
            "day_closes": [
                [paper_mark_snapshot_digest(item.close_mark_snapshot), paper_pnl_report_digest(item.close_pnl_report)]
                for item in closes
            ],
            "funding_events": [_to_payload(item) for item in events],
        }
    )


def _reservation(
    gi: GovernedPaperGenesisInputs,
    genesis: GovernedPaperGenesis,
    *,
    cycle_id: str,
    correlation_id: str,
    opening_dataset_digest: str,
    reservation_price: str,
) -> tuple[PaperSleeveState, PaperSleeveRiskBudgetDecision, PaperAllocatorIntentDraft]:
    """The two reservation ticks, journaled with the budget decision, candidate and readiness, and the cycle draft."""

    journal = EvidenceJournal()
    state = build_initial_paper_sleeve_state(sleeve_id=genesis.sleeve_id, correlation_id=correlation_id)
    for action in ("BUY", "SELL"):
        tick = build_paper_trade_tick(
            tick_id=f"{cycle_id}:reserve-{action.lower()}",
            action=action,
            intent_type="LIMIT",
            instrument_id=genesis.instrument,
            quantity=genesis.unit_size,
            strategy_id=genesis.strategy_id,
            run_plan_id=cycle_id,
            upstream_report_digest=opening_dataset_digest,
            correlation_id=correlation_id,
            limit_price=reservation_price,
        )
        entry = journal.append(
            EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id=correlation_id
        )
        state = apply_paper_trade_tick_to_sleeve_state(
            state, tick, correlation_id=f"{cycle_id}:reserve-{action.lower()}", journal_entry=entry
        ).to_state
    decision = evaluate_paper_sleeve_risk_budget(state, gi.risk_budget_policy, correlation_id=f"{cycle_id}:budget")
    decision_entry = append_paper_sleeve_risk_budget_decision_to_evidence_journal(
        journal, decision, state=state, policy=gi.risk_budget_policy, correlation_id=f"{cycle_id}:budget"
    )
    candidate = build_paper_sleeve_promotion_candidate(decision_entry, decision, correlation_id=f"{cycle_id}:budget")
    candidate_entry = append_paper_sleeve_promotion_candidate_to_evidence_journal(
        journal,
        candidate,
        decision_journal_entry=decision_entry,
        decision=decision,
        correlation_id=f"{cycle_id}:candidate",
    )
    readiness = build_paper_sleeve_promotion_readiness(
        journal, candidate_entry, candidate, correlation_id=f"{cycle_id}:readiness"
    )
    readiness_entry = append_paper_sleeve_promotion_readiness_to_evidence_journal(
        journal,
        readiness,
        promotion_candidate_journal_entry=candidate_entry,
        candidate=candidate,
        correlation_id=f"{cycle_id}:readiness",
    )
    draft = build_paper_allocator_intent_draft(journal, readiness_entry, readiness, correlation_id=f"{cycle_id}:draft")
    return state, decision, draft


def _capacity_policy(
    gi: GovernedPaperGenesisInputs, genesis: GovernedPaperGenesis, reservation_price: Fraction
) -> PaperCapacityGatePolicy:
    """The per-cycle capacity policy: the reservation's unit notional, one unit and the two eligible reservation ticks."""

    return build_paper_capacity_gate_policy(
        policy_id=gi.risk_budget_policy.policy_id,
        sleeve_id=genesis.sleeve_id,
        max_notional=_plain(Fraction(genesis.unit_size) * reservation_price),
        max_units=genesis.unit_size,
        max_open_intents=_ELIGIBLE_RESERVATION_TICKS,
    )


@dataclass(frozen=True)
class _Direction:
    """One reservation direction: the budget record that reserves it and that record's exact RG-7 final allocation."""

    authorized: bool
    record_decision_digest: str
    allocated_budget: str


_NO_DIRECTION = _Direction(False, "", "")


def _direction(chain: GovernedPaperCycleChain, action: str, notional: Fraction) -> _Direction:
    """Authorized only by its own ELIGIBLE record, reserved and finally allocated by RG-7 at its full ``notional``."""

    records = [
        item
        for item in chain.risk_budget_decision.record_decisions
        if getattr(item.action, "value", item.action) == action
    ]
    if len(records) != 1:
        raise _fail("reservation_direction_record_not_unique")
    record = records[0]
    sleeves = chain.allocation.sleeves
    allocated = [
        item
        for item in (sleeves[0].records if len(sleeves) == 1 else ())
        if (item.sequence, item.record_decision_digest) == (record.sequence, record.record_decision_digest)
    ]
    if len(allocated) != 1:
        return _Direction(False, record.record_decision_digest, "")
    final = allocated[0].final_allocated_budget
    authorized = (
        record.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE
        and allocated[0].risk_budget_record_status == PaperSleeveRiskBudgetRecordStatus.ELIGIBLE.value
        and Fraction(record.requested_budget) == notional
        and Fraction(record.reserved_budget) == notional
        and Fraction(final) == notional
    )
    return _Direction(authorized, record.record_decision_digest, final)


def _derive_chain(
    inputs: GovernedPaperCycleInputs,
    genesis: GovernedPaperGenesis,
    *,
    cycle_id: str,
    correlation_id: str,
    opening_ns: int,
    opening_dataset_digest: str,
    reservation_price: Fraction,
) -> GovernedPaperCycleChain:
    gi = inputs.genesis_inputs
    envelope = gi.portfolio_risk_envelope
    sleeve, genesis_ns = genesis.sleeve_id, genesis.genesis_ns
    day_count = (opening_ns - genesis_ns) // _DAY_NS
    # RG-3 chains one correlation from the time-window producer's source summary through every artifact it rebuilds.
    rg3_correlation = gi.metrics_summary.correlation_id
    valuation_inputs = valuation = performance_inputs = performance = None
    if inputs.sealed_episodes:
        funding = build_paper_sleeve_funding_evidence(
            evidence_id=f"{cycle_id}:funding",
            sleeve_id=sleeve,
            market_symbol=genesis.instrument,
            window_start_ns=genesis_ns,
            window_end_ns=opening_ns,
            events=inputs.sealed_funding_events,
        )
        valuation_inputs = PaperSleeveValuationInputs(
            valuation_id=f"{cycle_id}:valuation",
            correlation_id=rg3_correlation,
            equity_basis_policy=gi.equity_basis_policy,
            window_start_ns=genesis_ns,
            window_end_ns=opening_ns,
            episodes=inputs.sealed_episodes,
            day_closes=inputs.sealed_day_closes,
            funding_evidence=funding,
        )
        valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
        series: dict[str, object] = dict.fromkeys(
            ("methodology", "metrics_summary", "time_window", "daily_return_series", "sharpe_evidence")
        )
        if valuation.status is PaperSleeveValuationStatus.COMPUTED:
            methodology = build_paper_return_series_methodology(
                methodology_id=genesis.methodology_id,
                correlation_id=rg3_correlation,
                risk_free_policy_id=genesis.risk_free_policy_id,
                **paper_sleeve_equity_basis_methodology_policy_ids(gi.equity_basis_policy),
            )
            summary = gi.metrics_summary
            window = build_paper_deterministic_time_window_evidence(
                summary,
                expected_metrics_summary_digest=summary.summary_digest,
                started_at_ns=genesis_ns,
                stopped_at_ns=opening_ns,
                window_id=f"{cycle_id}:window",
                methodology_id=genesis.methodology_id,
                run_id=summary.run_id,
                aggregate_id=summary.aggregate_id,
                correlation_id=rg3_correlation,
                sample_observation_count=day_count,
            )
            returns = build_paper_daily_return_series_evidence(
                methodology,
                window,
                expected_methodology_digest=methodology.methodology_digest,
                expected_time_window_digest=window.time_window_digest,
                series_id=f"{cycle_id}:series",
                correlation_id=rg3_correlation,
                daily_buckets=paper_sleeve_daily_return_buckets(valuation),
            )
            sharpe = build_paper_sharpe_evidence(
                returns,
                expected_daily_return_series_digest=returns.series_digest,
                risk_free_policy_id=genesis.risk_free_policy_id,
                sharpe_evidence_id=f"{cycle_id}:sharpe",
                paper_id=genesis.genesis_id,
                correlation_id=rg3_correlation,
            )
            series = {
                "methodology": methodology,
                "metrics_summary": summary,
                "time_window": window,
                "daily_return_series": returns,
                "sharpe_evidence": sharpe,
            }
        performance_inputs = PaperSleevePerformanceInputs(
            performance_evidence_id=f"{cycle_id}:rg3",
            correlation_id=rg3_correlation,
            portfolio_risk_envelope=envelope,
            valuation_inputs=valuation_inputs,
            valuation=valuation,
            **series,  # type: ignore[arg-type]
        )
        performance = build_paper_sleeve_performance_evidence(performance_inputs)
    drawdown_inputs = drawdown = None
    if day_count > 0:
        drawdown_inputs = PaperSleeveDrawdownInputs(
            drawdown_evidence_id=f"{cycle_id}:rg4",
            correlation_id=correlation_id,
            portfolio_risk_envelope=envelope,
            performance_path_policy=gi.performance_path_policy,
            window_start_ns=genesis_ns,
            window_end_ns=opening_ns,
            sleeves=() if performance is None else (PaperSleeveDrawdownSleeveInputs(performance_inputs, performance),),  # type: ignore[arg-type]
        )
        drawdown = build_paper_sleeve_drawdown_evidence(drawdown_inputs)
    correlation_inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id=f"{cycle_id}:rg5",
        correlation_id=correlation_id,
        portfolio_risk_envelope=envelope,
        evaluation_end_ns=opening_ns,
        sleeves=() if performance is None else (PaperSleeveCorrelationSleeveInputs(performance_inputs, performance),),  # type: ignore[arg-type]
    )
    correlation = build_paper_sleeve_correlation_evidence(correlation_inputs)
    ladder_inputs = ladder = None
    if performance is not None and drawdown is not None:
        ladder_inputs = PaperSleevePromotionDemotionInputs(
            decision_id=f"{cycle_id}:rg6",
            correlation_id=correlation_id,
            portfolio_risk_envelope=envelope,
            ladder_state=gi.ladder_seed if inputs.prior_ladder is None else inputs.prior_ladder,
            evaluation_end_ns=opening_ns,
            performance_inputs=performance_inputs,  # type: ignore[arg-type]
            performance_evidence=performance,
            drawdown_inputs=drawdown_inputs,  # type: ignore[arg-type]
            drawdown_evidence=drawdown,
            correlation_inputs=correlation_inputs,
            correlation_evidence=correlation,
        )
        ladder = build_paper_sleeve_promotion_demotion_decision(ladder_inputs)
    reservation_text = _scale18(reservation_price, "reservation_price_not_representable")
    state, budget, draft = _reservation(
        gi,
        genesis,
        cycle_id=cycle_id,
        correlation_id=correlation_id,
        opening_dataset_digest=opening_dataset_digest,
        reservation_price=reservation_text,
    )
    capacity_policy = _capacity_policy(gi, genesis, reservation_price)
    head_authority = build_paper_lifecycle_head_authority(inputs.head_authority_inputs)
    allocation_inputs = PaperPortfolioAllocationInputs(
        allocation_id=f"{cycle_id}:rg7",
        correlation_id=correlation_id,
        portfolio_risk_envelope=envelope,
        evaluation_end_ns=opening_ns,
        sleeves=(
            PaperPortfolioAllocationSleeveInputs(
                sleeve_id=sleeve,
                paper_admission=gi.paper_admission,
                lifecycle_head_authority_inputs=inputs.head_authority_inputs,
                lifecycle_head_authority=head_authority,
                risk_budget_state=state,
                risk_budget_policy=gi.risk_budget_policy,
                risk_budget_decision=budget,
            ),
        ),
        correlation_inputs=correlation_inputs,
        correlation_evidence=correlation,
    )
    allocation = build_paper_portfolio_allocation_decision(allocation_inputs)
    governance_inputs = governance = None
    if ladder is not None and ladder_inputs is not None:
        governance_inputs = PaperPortfolioGovernanceInputs(
            governance_decision_id=f"{cycle_id}:rg8",
            correlation_id=correlation_id,
            portfolio_risk_envelope=envelope,
            evaluation_end_ns=opening_ns,
            drawdown_inputs=drawdown_inputs,  # type: ignore[arg-type]
            drawdown_evidence=drawdown,  # type: ignore[arg-type]
            sleeves=(PaperPortfolioGovernanceSleeveInputs(sleeve, ladder_inputs, ladder),),
            allocation_inputs=allocation_inputs,
            allocation_decision=allocation,
        )
        governance = build_paper_portfolio_governance_decision(governance_inputs)
    return GovernedPaperCycleChain(
        valuation_inputs=valuation_inputs,
        valuation=valuation,
        performance_inputs=performance_inputs,
        performance=performance,
        drawdown_inputs=drawdown_inputs,
        drawdown=drawdown,
        correlation_inputs=correlation_inputs,
        correlation=correlation,
        ladder_inputs=ladder_inputs,
        ladder=ladder,
        head_authority=head_authority,
        risk_budget_state=state,
        risk_budget_decision=budget,
        allocator_draft=draft,
        capacity_policy=capacity_policy,
        allocation_inputs=allocation_inputs,
        allocation=allocation,
        governance_inputs=governance_inputs,
        governance=governance,
    )


def _bootstrap_peak_distance(valuation: PaperSleeveDailyValuationEvidence) -> Fraction:
    """The maximum peak distance of the RG-3 valuation index, its start ``1`` included."""

    path = ["1", *(day.normalized_index_end for day in valuation.days)]
    numerator, _, denominator = measure_paper_peak_distance(path).max_peak_distance.partition("/")
    return Fraction(int(numerator), int(denominator))


@dataclass(frozen=True)
class _Classification:
    phase: GovernedPaperCyclePhase
    bootstrap_status: str
    peak_distance: str
    blocked: tuple[str, ...]
    governance: tuple[str, ...]


def _classify(
    chain: GovernedPaperCycleChain, genesis: GovernedPaperGenesis, gi: GovernedPaperGenesisInputs, opening_ns: int
) -> _Classification:
    blocked: list[str] = []
    governance: list[str] = []
    allocation, head = chain.allocation, chain.head_authority
    record = allocation.sleeves[0] if allocation.sleeves else None
    if head.lifecycle_head_digest != genesis.lifecycle_genesis_digest:
        blocked.append(_reason("lifecycle_head_not_the_paper_genesis"))
    if allocation.status is PaperPortfolioAllocationStatus.NEEDS_GOVERNANCE_APPROVAL:
        governance.append(_reason("rg7_needs_governance_approval"))
    elif allocation.status is PaperPortfolioAllocationStatus.ALLOCATION_REJECTED:
        blocked.append(_reason("rg7_allocation_rejected"))
    elif record is None or record.governed_lifecycle_state is not PaperGovernedLifecycleState.ACTIVE:
        blocked.append(_reason("lifecycle_head_not_active"))
    elif Fraction(record.final_allocated_budget) <= 0:
        blocked.append(_reason("rg7_final_allocation_not_positive"))
    performance, governance_decision = chain.performance, chain.governance
    if (
        performance is not None
        and performance.status is PaperSleevePerformanceStatus.READY
        and governance_decision is not None
        and governance_decision.status is PaperPortfolioGovernanceStatus.READY
    ):
        terminal = governance_decision.sleeves[0].terminal_final_allocated_budget if governance_decision.sleeves else ""
        if record is None or terminal != record.final_allocated_budget:
            blocked.append(_reason("rg8_terminal_allocation_not_the_rg7_final"))
        return _Classification(
            GovernedPaperCyclePhase.ORDINARY, "NOT_REQUIRED", "", _sorted_unique(blocked), _sorted_unique(governance)
        )
    if governance_decision is not None and governance_decision.status in (
        PaperPortfolioGovernanceStatus.PORTFOLIO_STOP_TRIGGERED,
        PaperPortfolioGovernanceStatus.ALLOCATION_REJECTED,
        PaperPortfolioGovernanceStatus.NEEDS_GOVERNANCE_APPROVAL,
    ):
        blocked.append(_reason(f"rg8_{governance_decision.status.value.lower()}_never_excepted"))
        return _Classification(
            GovernedPaperCyclePhase.NONE, "NOT_ELIGIBLE", "", _sorted_unique(blocked), _sorted_unique(governance)
        )
    if not genesis.genesis_ns <= opening_ns < genesis.bootstrap_end_ns:
        blocked.append(_reason("bootstrap_expired"))
        return _Classification(
            GovernedPaperCyclePhase.NONE, "EXPIRED", "", _sorted_unique(blocked), _sorted_unique(governance)
        )
    sleeve = genesis.sleeve_id

    def exactly(artifact: object, status: Enum, reasons: tuple[str, ...]) -> bool:
        expected = tuple(item.format(sleeve=sleeve) for item in reasons)
        return artifact.status is status and artifact.reason_codes == expected  # type: ignore[attr-defined]

    correlation_ready = chain.correlation.status is PaperSleeveCorrelationStatus.READY
    drawdown = chain.drawdown
    if performance is None:
        drawdown_missing = drawdown is None or (
            exactly(drawdown, PaperSleeveDrawdownStatus.NOT_COMPUTABLE, _B0_DRAWDOWN_REASONS)
            and drawdown.missing_sleeve_ids == (sleeve,)
        )
        if correlation_ready and drawdown_missing and chain.ladder is None and governance_decision is None:
            return _Classification(
                GovernedPaperCyclePhase.BOOTSTRAP_B0,
                "WITHIN_HORIZON",
                "",
                _sorted_unique(blocked),
                _sorted_unique(governance),
            )
        blocked.append(_reason("bootstrap_b0_not_eligible"))
        return _Classification(
            GovernedPaperCyclePhase.NONE, "NOT_ELIGIBLE", "", _sorted_unique(blocked), _sorted_unique(governance)
        )
    eligible = (
        exactly(performance, PaperSleevePerformanceStatus.NOT_COMPUTABLE, _BOOTSTRAP_RG3_REASONS)
        and chain.valuation is not None
        and chain.valuation.status is PaperSleeveValuationStatus.COMPUTED
        and correlation_ready
        and drawdown is not None
        and exactly(drawdown, PaperSleeveDrawdownStatus.NOT_COMPUTABLE, _B1_DRAWDOWN_REASONS)
        and chain.ladder is not None
        and exactly(chain.ladder, PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE, _B1_LADDER_REASONS)
        and governance_decision is not None
        and exactly(governance_decision, PaperPortfolioGovernanceStatus.NOT_COMPUTABLE, _B1_GOVERNANCE_REASONS)
        and governance_decision.portfolio_stop_evaluated is False
    )
    if not eligible:
        blocked.append(_reason("bootstrap_b1_not_eligible"))
        return _Classification(
            GovernedPaperCyclePhase.NONE, "NOT_ELIGIBLE", "", _sorted_unique(blocked), _sorted_unique(governance)
        )
    peak = _bootstrap_peak_distance(chain.valuation)  # type: ignore[arg-type]
    peak_text = f"{peak.numerator}/{peak.denominator}"
    if any(
        peak > Fraction(level.max_portfolio_drawdown_fraction)
        for level in gi.portfolio_risk_envelope.portfolio_stop_levels
    ):
        blocked.append(_reason("bootstrap_stop_triggered"))
        return _Classification(
            GovernedPaperCyclePhase.NONE,
            "STOP_TRIGGERED",
            peak_text,
            _sorted_unique(blocked),
            _sorted_unique(governance),
        )
    return _Classification(
        GovernedPaperCyclePhase.BOOTSTRAP_B1,
        "WITHIN_HORIZON",
        peak_text,
        _sorted_unique(blocked),
        _sorted_unique(governance),
    )


def _status_text(artifact: object | None) -> str:
    return _NOT_DERIVED if artifact is None else artifact.status.value  # type: ignore[attr-defined]


def _cycle_parts(inputs: object) -> tuple[GovernedPaperCycleInputs, GovernedPaperGenesis, str, str, int, int]:
    _require_exact(inputs, GovernedPaperCycleInputs, "cycle_inputs")
    ci = cast(GovernedPaperCycleInputs, inputs)
    cycle_id = _require_identifier(ci.cycle_id, "cycle_id")
    correlation_id = _require_identifier(ci.correlation_id, "correlation_id")
    day_index = _require_int(ci.day_index, "day_index", minimum=0)
    _require_exact(ci.genesis_inputs, GovernedPaperGenesisInputs, "genesis_inputs")
    _require_exact(ci.genesis, GovernedPaperGenesis, "genesis")
    _require_exact(ci.head_authority_inputs, PaperLifecycleHeadAuthorityInputs, "head_authority_inputs")
    _require_tuple_of(ci.sealed_episodes, PaperSleeveEpisodeEvidence, "sealed_episodes")
    _require_tuple_of(ci.sealed_day_closes, PaperSleeveDayCloseValuation, "sealed_day_closes")
    _require_tuple_of(ci.sealed_funding_events, PaperSleeveFundingEvent, "sealed_funding_events")
    if ci.prior_ladder is not None:
        _require_exact(ci.prior_ladder, PaperSleeveLadderPriorDecision, "prior_ladder")
    _verified(verify_governed_paper_genesis(ci.genesis, ci.genesis_inputs), "genesis_not_authentic")
    genesis = ci.genesis
    opening = _require_int(genesis.genesis_ns + day_index * _DAY_NS, "opening_ns", minimum=0)
    closing = _require_int(opening + _DAY_NS, "closing_ns", minimum=0)
    if len(ci.sealed_day_closes) != day_index:
        raise _fail("sealed_day_closes_not_one_per_sealed_day")
    if any(item.close_mark_snapshot.observed_at_ns > opening for item in ci.sealed_day_closes):
        raise _fail("sealed_history_after_opening")
    if any(item.fill_market_snapshot.observed_at_ns >= opening for item in ci.sealed_episodes):  # type: ignore[operator]
        raise _fail("sealed_history_after_opening")
    if any(item.settlement_at_ns >= opening for item in ci.sealed_funding_events):
        raise _fail("sealed_history_after_opening")
    if ci.prior_ladder is not None and not ci.sealed_episodes:
        raise _fail("prior_ladder_without_sealed_history")
    return ci, genesis, cycle_id, correlation_id, opening, closing


def _assemble_cycle(inputs: object) -> GovernedPaperCycleAuthority:
    ci, genesis, cycle_id, correlation_id, opening, closing = _cycle_parts(inputs)
    gi = ci.genesis_inputs
    dataset = _opening_dataset(ci.opening_dataset, genesis, opening)
    approval = _canonical_approval(ci.approval, "cycle_approval")
    history_digest = governed_paper_sealed_history_digest(
        ci.sealed_episodes, ci.sealed_day_closes, ci.sealed_funding_events
    )
    blocked: list[str] = []
    governance: list[str] = []
    chain: GovernedPaperCycleChain | None = None
    mark: tuple[str, str] | None = None
    reservation = notional = Fraction(0)
    capacity_within = False
    long_direction = short_direction = _NO_DIRECTION
    classification = _Classification(GovernedPaperCyclePhase.NONE, "NOT_ELIGIBLE", "", (), ())
    if genesis.status is not GovernedPaperGenesisStatus.READY:
        blocked.append(_reason("genesis_not_ready"))
    else:
        mark = historical_execution_latest_visible_mark(
            dataset, policy=gi.economics_policy, instrument=genesis.instrument, at_ns=opening
        )
        if mark is None:
            blocked.append(_reason("opening_mark_unavailable"))
        else:
            quantized = historical_execution_quantize_price(
                Fraction(mark[1]) * (1 + Fraction(genesis.reservation_beta))
            )
            if quantized is None or quantized[0] <= 0:
                raise _fail("reservation_price_not_representable")
            reservation = quantized[0]
            notional = Fraction(genesis.unit_size) * reservation
            capacity_within = notional <= Fraction(genesis.capacity_max_value)
            if not capacity_within:
                blocked.append(_reason("capacity_assumption_exceeded"))
            chain = _derive_chain(
                ci,
                genesis,
                cycle_id=cycle_id,
                correlation_id=correlation_id,
                opening_ns=opening,
                opening_dataset_digest=dataset.dataset_digest,
                reservation_price=reservation,
            )
            classification = _classify(chain, genesis, gi, opening)
            blocked.extend(classification.blocked)
            governance.extend(classification.governance)
            long_direction = _direction(chain, "BUY", notional)
            short_direction = _direction(chain, "SELL", notional)
            if not blocked and not governance and not (long_direction.authorized or short_direction.authorized):
                blocked.append(_reason("no_reservation_direction_authorized"))
    blocked_codes, governance_codes = _sorted_unique(blocked), _sorted_unique(governance)
    granted = not blocked_codes and not governance_codes
    head = None if chain is None else chain.head_authority
    allocation_record = None if chain is None or not chain.allocation.sleeves else chain.allocation.sleeves[0]
    seed = GovernedPaperCycleAuthority(
        schema_version=_CYCLE_SCHEMA,
        status=GovernedPaperCycleStatus.AUTHORIZED,
        authorized=False,
        phase=classification.phase,
        cycle_id=cycle_id,
        correlation_id=correlation_id,
        genesis_digest=genesis.genesis_digest,
        day_index=ci.day_index,
        opening_ns=opening,
        closing_ns=closing,
        opening_dataset_digest=dataset.dataset_digest,
        sealed_history_digest=history_digest,
        sealed_episode_count=len(ci.sealed_episodes),
        head_authority_digest="" if head is None else head.authority_digest,
        lifecycle_head_digest="" if head is None else head.lifecycle_head_digest,
        lifecycle_head_is_paper_genesis=head is not None
        and head.lifecycle_head_digest == genesis.lifecycle_genesis_digest,
        head_attested=head is not None and head.paper_current_head_attested is True,
        opening_mark_record_digest="" if mark is None else mark[0],
        opening_mark_price="" if mark is None else mark[1],
        reservation_price="" if chain is None else _scale18(reservation, "reservation_price_not_representable"),
        max_long_quantity="" if chain is None else (genesis.unit_size if long_direction.authorized else _ZERO_QUANTITY),
        max_short_quantity=""
        if chain is None
        else (genesis.unit_size if short_direction.authorized else _ZERO_QUANTITY),
        long_direction_authorized=long_direction.authorized,
        short_direction_authorized=short_direction.authorized,
        long_reservation_record_digest=long_direction.record_decision_digest,
        short_reservation_record_digest=short_direction.record_decision_digest,
        long_allocated_budget=long_direction.allocated_budget,
        short_allocated_budget=short_direction.allocated_budget,
        reservation_notional="" if chain is None else _plain(notional),
        capacity_max_value=genesis.capacity_max_value,
        capacity_within_assumption=capacity_within,
        performance_evidence_digest=""
        if chain is None or chain.performance is None
        else chain.performance.performance_evidence_digest,
        performance_status=_NOT_DERIVED if chain is None else _status_text(chain.performance),
        drawdown_evidence_digest=""
        if chain is None or chain.drawdown is None
        else chain.drawdown.drawdown_evidence_digest,
        drawdown_status=_NOT_DERIVED if chain is None else _status_text(chain.drawdown),
        correlation_evidence_digest="" if chain is None else chain.correlation.correlation_evidence_digest,
        correlation_status=_NOT_DERIVED if chain is None else chain.correlation.status.value,
        ladder_decision_digest="" if chain is None or chain.ladder is None else chain.ladder.decision_digest,
        ladder_status=_NOT_DERIVED if chain is None else _status_text(chain.ladder),
        allocation_decision_digest="" if chain is None else chain.allocation.allocation_decision_digest,
        allocation_status=_NOT_DERIVED if chain is None else chain.allocation.status.value,
        allocation_final_budget="" if allocation_record is None else allocation_record.final_allocated_budget,
        governance_decision_digest=""
        if chain is None or chain.governance is None
        else chain.governance.governance_decision_digest,
        governance_status=_NOT_DERIVED if chain is None else _status_text(chain.governance),
        bootstrap_status=classification.bootstrap_status,
        bootstrap_max_peak_distance=classification.peak_distance,
        window_start_ns=opening if granted else None,
        window_end_ns=closing if granted else None,
        blocked_reason_codes=blocked_codes,
        governance_reason_codes=governance_codes,
        cycle_policy_digest="",
        approval=approval,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
        authority_digest="",
    )
    policy_payload = _to_payload(seed)
    for name in ("status", "authorized", "approval", "cycle_policy_digest", "authority_digest"):
        policy_payload.pop(name)
    cycle_policy_digest = _digest_of(policy_payload)
    if granted:
        governance_codes = _sorted_unique(
            _approval_codes(approval, kind="cycle", subject_id=cycle_id, subject_digest=cycle_policy_digest)
        )
    status = (
        GovernedPaperCycleStatus.BLOCKED
        if blocked_codes
        else GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL
        if governance_codes
        else GovernedPaperCycleStatus.AUTHORIZED
    )
    authorized = status is GovernedPaperCycleStatus.AUTHORIZED
    sealed = replace(
        seed,
        status=status,
        authorized=authorized,
        window_start_ns=opening if authorized else None,
        window_end_ns=closing if authorized else None,
        governance_reason_codes=governance_codes,
        cycle_policy_digest=cycle_policy_digest,
    )
    return replace(sealed, authority_digest=edge_payload_digest(_to_payload(sealed), _CYCLE_DIGEST_FIELD))


def build_governed_paper_cycle_authority(inputs: GovernedPaperCycleInputs) -> GovernedPaperCycleAuthority:
    """Build the prospective authority of one cycle from facts that exist at its opening. See the module docstring.

    The window bounds are present exactly when AUTHORIZED; the draft of an unapproved cycle carries the
    ``cycle_policy_digest`` its human approval (C3) must commit to.
    """

    return _assemble_cycle(inputs)


def governed_paper_cycle_authority_to_dict(authority: GovernedPaperCycleAuthority) -> dict[str, object]:
    """Canonical JSON-ready mapping of a cycle authority, including its self-digest."""

    return _to_payload(authority)


def governed_paper_cycle_authority_digest(authority: GovernedPaperCycleAuthority) -> str:
    """Recompute the canonical cycle authority digest, excluding only ``authority_digest``."""

    return edge_payload_digest(_to_payload(authority), _CYCLE_DIGEST_FIELD)


def verify_governed_paper_cycle_authority(authority: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a cycle authority by rebuilding it from its exact inputs. Total: never raises."""

    return _verify_rebuilt(
        authority, GovernedPaperCycleAuthority, lambda: _assemble_cycle(inputs), _CYCLE_DIGEST_FIELD, "cycle_authority"
    )


def governed_paper_cycle_chain(inputs: GovernedPaperCycleInputs) -> GovernedPaperCycleChain | None:
    """The RG-3 to RG-8 artifacts and the reservation lineage one cycle derives, or None when it derives none.

    Deterministic and consistent with ``build_governed_paper_cycle_authority`` over the same inputs: a consumer that
    needs the derived artifacts (the cycle's allocator draft and capacity policy, the RG-6 decision a later cycle
    continues) rebuilds them here instead of trusting a copy.
    """

    ci, genesis, cycle_id, correlation_id, opening, _ = _cycle_parts(inputs)
    if genesis.status is not GovernedPaperGenesisStatus.READY:
        return None
    dataset = _opening_dataset(ci.opening_dataset, genesis, opening)
    mark = historical_execution_latest_visible_mark(
        dataset, policy=ci.genesis_inputs.economics_policy, instrument=genesis.instrument, at_ns=opening
    )
    if mark is None:
        return None
    quantized = historical_execution_quantize_price(Fraction(mark[1]) * (1 + Fraction(genesis.reservation_beta)))
    if quantized is None or quantized[0] <= 0:
        raise _fail("reservation_price_not_representable")
    return _derive_chain(
        ci,
        genesis,
        cycle_id=cycle_id,
        correlation_id=correlation_id,
        opening_ns=opening,
        opening_dataset_digest=dataset.dataset_digest,
        reservation_price=quantized[0],
    )


def governed_paper_cycle_capacity(
    genesis_inputs: GovernedPaperGenesisInputs, genesis: GovernedPaperGenesis, authority: GovernedPaperCycleAuthority
) -> tuple[PaperAllocatorIntentDraft, PaperCapacityGatePolicy]:
    """The capacity lineage of one AUTHORIZED cycle: its journaled reservation draft and its capacity policy.

    A pure derivation from an authority the caller has re-proven: exactly the reservation journal the cycle's RG-7
    consumed (the same ticks, budget decision, candidate and readiness), so every episode the cycle decided is admitted
    against the reservation that authorized it and never against a later one.
    """

    if type(authority) is not GovernedPaperCycleAuthority or authority.authorized is not True:
        raise _fail("cycle_authority_not_authorized")
    if authority.genesis_digest != genesis.genesis_digest:
        raise _fail("cycle_authority_of_another_genesis")
    reservation = Fraction(authority.reservation_price)
    _, _, draft = _reservation(
        genesis_inputs,
        genesis,
        cycle_id=authority.cycle_id,
        correlation_id=authority.correlation_id,
        opening_dataset_digest=authority.opening_dataset_digest,
        reservation_price=authority.reservation_price,
    )
    return draft, _capacity_policy(genesis_inputs, genesis, reservation)


def governed_paper_strategy_spec(genesis_inputs: GovernedPaperGenesisInputs) -> StrategySpec:
    """The admitted variant's StrategySpec, re-derived from its executable binding and checked against EF-7."""

    _require_exact(genesis_inputs, GovernedPaperGenesisInputs, "genesis_inputs")
    spec = _binding_spec(genesis_inputs.executable_binding)
    if strategy_spec_digest(spec) != genesis_inputs.paper_admission.strategy_spec_digest:
        raise _fail("strategy_spec_digest_mismatch")
    return spec


def governed_paper_cycle_admission_window(
    authority: GovernedPaperCycleAuthority,
) -> HistoricalExecutionAdmissionWindow | None:
    """The neutral economics admission window an AUTHORIZED cycle grants, or None for every other cycle."""

    if type(authority) is not GovernedPaperCycleAuthority:
        raise _fail("cycle_authority_malformed")
    if authority.authorized is not True or authority.window_start_ns is None or authority.window_end_ns is None:
        return None
    return HistoricalExecutionAdmissionWindow(
        window_start_ns=authority.window_start_ns,
        window_end_ns=authority.window_end_ns,
        max_long_quantity=authority.max_long_quantity,
        max_short_quantity=authority.max_short_quantity,
        reservation_price=authority.reservation_price,
    )


__all__ = [
    "GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST",
    "GOVERNED_PAPER_NON_CLAIM_FLAGS",
    "GovernedPaperApproval",
    "GovernedPaperApprovalKind",
    "GovernedPaperBootstrapAuthority",
    "GovernedPaperCycleAuthority",
    "GovernedPaperCycleChain",
    "GovernedPaperCycleInputs",
    "GovernedPaperCyclePhase",
    "GovernedPaperCycleStatus",
    "GovernedPaperExecutionAuthorityError",
    "GovernedPaperGenesis",
    "GovernedPaperGenesisInputs",
    "GovernedPaperGenesisStatus",
    "GovernedPaperReservationBand",
    "build_governed_paper_cycle_authority",
    "build_governed_paper_genesis",
    "governed_paper_cycle_admission_window",
    "governed_paper_cycle_authority_digest",
    "governed_paper_cycle_authority_to_dict",
    "governed_paper_cycle_capacity",
    "governed_paper_cycle_chain",
    "governed_paper_execution_authority_rule_set",
    "governed_paper_genesis_digest",
    "governed_paper_genesis_to_dict",
    "governed_paper_sealed_history_digest",
    "governed_paper_strategy_spec",
    "verify_governed_paper_cycle_authority",
    "verify_governed_paper_genesis",
]
