"""Governed paper execution authority (GOVERNED_PAPER_TYPED_PROVENANCE_V2): genesis and per-cycle authority.

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7. Paper-only, deterministic,
point-in-time and fail-closed. Nothing here routes an order, reserves capital or proves venue truth.

Trust rule (``DERIVE_NOT_ACCEPT + CANONICAL_TYPED_IDENTITY + RECOMPUTED_DIGEST + PUBLIC_VERIFIER_REPROOF``):

* every consumed upstream artifact is re-proven by its own public verifier, its self-digest is recomputed and must equal
  its upstream anchor, and only its strict canonical reconstruction is used afterwards;
* an authority that an authenticated upstream already binds is DERIVED from that binding, never accepted again. The
  risk-budget policy is rebuilt from the EF-7 ``risk_budget_policy_binding`` (exact snapshot shape, public builder,
  canonical JSON equal to the bound snapshot, recomputed digest equal to the snapshot, the binding anchor and the EF-7
  digest). The reservation chain of every cycle (ticks, journal, sleeve state, risk-budget decision, promotion
  candidate, readiness and allocator draft) is derived by the public builders, never supplied;
* inline governance records (approvals, the parameter assignment) must be typed-identical (``TCI_V1``,
  ``governed_paper_typed_identity``) to their canonical reconstruction. Python equality is never a trust decision;
* every artifact this module owns is verified by typed identity against its single assembly path plus a recomputed
  self-digest (``governed_paper_verify_rebuilt``). A forged ``False``/``0`` or ``True``/``1`` substitution never
  verifies, even resealed.

Genesis (``GovernedPaperGenesis``, one per sleeve, single-sleeve, one-use). It binds the EF-7 v2 admission (READY, PASS,
admitted), its EF-8 INITIAL_ACTIVATION receipt, the executable binding, one admitted variant and its exact parameter
assignment, the parameter approval, the EF-6 economics policy (its recomputed digest must equal the EF-6
``economics_policy_digest``) and its approval, the RG-2 envelope, the equity-basis policy (reference notional ==
``initial_equity``), the RG-6 ladder seed, the RG-4 performance-path policy, the C7 governor policy of the RG-3
metrics context (an exact canonical record of its public builder), the genesis instant G (a UTC day), the bootstrap
horizon H (``>= 30`` UTC days) and the reservation band beta. The capacity authority is the EF-7 assumption of the one
supported measure (``max_open_position_notional`` / ``quote_currency_notional`` / ``per_instrument_open_position``);
any other measure for the instrument blocks the genesis. A HUMAN_GOVERNANCE approval of the exact genesis policy
(adoption C1, bootstrap C2 and the C7 governor thresholds) is required for ``AUTHORIZED``.
``genesis_inputs_identity_digest`` is the typed identity of the complete inputs, with every verified upstream artifact
as a typed reference to its recomputed self-digest.

Cycle (``GovernedPaperCycleAuthority``, UTC day ``k``, window ``[E_k, E_k + 1 day)``, ``E_k = G + k days``). Opening uses
only facts that exist at ``E_k``: the history sealed before ``E_k`` (its typed digest is carried), the mark ``m(E_k)``
under the economics engine's own rule, RG-7 and RG-4 at ``E_k`` and, once episodes exist, RG-8 at ``E_k``.

* Reservation: ``L_k = m(E_k) * (1 + beta)`` on the price grid (ROUND_HALF_EVEN); one MARKETABLE_LIMIT tick per
  direction (BUY ``u`` and SELL ``u`` at limit ``L_k``) journaled and evaluated under the derived policy. ``u * L_k``
  must not exceed the capacity assumption.
* Per-direction authority (B2): a direction is authorized only by its OWN record: ELIGIBLE, requested == reserved ==
  ``u * L_k``, and its RG-7 record ELIGIBLE with ``final_allocated_budget == u * L_k`` on a READY allocation with an
  attested ACTIVE head and no kill override. Otherwise its ceiling is zero. There is no aggregate-to-symmetric shortcut,
  and at least one direction must be authorized.
* RG-3 metrics context (``M2_RG3_METRICS_CONTEXT_V1``), derived, never supplied: the accepted section-7 chain (session,
  realized-PnL bridge, aggregate, evidence manifest, admission record, journal ledger bridge, governor under the
  genesis C7 policy, its deterministic replay, Stage-4 readiness and metrics summary) over exactly the whole sealed
  history, anchored on the first sealed episode (the run that opened the period, so the summary's run and
  correlation identity, which RG-3's window, series and Sharpe must share, never moves). Its status is
  ``NO_COMPUTED_REALIZED_EVENT`` (the manifest has no computed realized event), ``BELOW_GOVERNOR_MINIMUM`` (the governor
  blocks only for fewer computed events than the C7 minimum), ``SAMPLE_ELIGIBLE`` (ALLOW_PAPER: a ready candidate
  summary), ``GOVERNOR_REVIEW_REQUIRED`` or ``GOVERNOR_BLOCKED``. RG-3 is valued under the genesis equity-basis policy
  (C5) only, and must carry exactly the derived summary when it is sample-eligible over a computed valuation, and no
  series otherwise; any other basis or metrics summary is refused. A governor review or block is a STOP.
* Phases (GAP-5): ``BOOTSTRAP_B0`` (no sealed episode; RG-8 cannot be constructed; RG-4 NOT_COMPUTABLE for exactly the
  missing sleeve, and absent on day 0, whose window ``[G, G)`` is empty); ``BOOTSTRAP_B1`` (episodes exist; RG-8, RG-4,
  RG-6, seeded from the genesis seed, and RG-3 NOT_COMPUTABLE with exactly the pinned reason sets of the bootstrap
  sleeve's insufficient sample: no series while the metrics context is ``NO_COMPUTED_REALIZED_EVENT`` or
  ``BELOW_GOVERNOR_MINIMUM``, an uncomputable Sharpe while it is ``SAMPLE_ELIGIBLE``; the bootstrap stop is not
  triggered); ``ORDINARY`` (RG-3 and RG-8 READY, the terminal allocation equal to RG-7's). Bootstrap phases need
  ``E_k < G + H`` and no other sleeve with a post-kill reservation. A STOP, a rejected allocation, a governance gap or
  a kill is never excepted.
* Approval (C3): only an exact HUMAN_GOVERNANCE approval of the cycle policy authorizes the cycle.

A cycle is prospective authority for its window only. It never proves the history it was opened on: the lineage
evidence (``governed_admitted_variant_paper_execution``) binds every cycle to the seal that closed the day before.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.deterministic_paper_replay_harness import (
    DeterministicPaperReplayHarnessStatus,
    verify_deterministic_paper_replay,
)
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeAuthorityBinding,
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
    edge_kill_quarantine_decision_from_payload,
    edge_kill_quarantine_decision_to_dict,
    verify_edge_kill_quarantine_decision,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EdgeCapacityAssumption,
    EdgePaperAdmissionDecision,
    edge_paper_admission_decision_from_payload,
    edge_paper_admission_decision_to_dict,
    verify_edge_paper_admission_decision,
)
from crypto_core.validation.edge_strategy_spec_admission import edge_strategy_spec_admission_from_payload
from crypto_core.validation.edge_walk_forward_oos_evidence import edge_walk_forward_oos_evidence_from_payload
from crypto_core.validation.governed_paper_typed_identity import (
    GovernedPaperTypeDomain,
    governed_paper_typed_identical,
    governed_paper_typed_identity_digest,
    governed_paper_verify_rebuilt,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionAdmissionWindow,
    historical_execution_latest_visible_mark,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionEconomicsApproval,
    HistoricalExecutionEconomicsPolicy,
    canonical_historical_execution_economics_approval,
    historical_execution_decimal_is_canonical,
    historical_execution_economics_approval_mismatches,
    historical_execution_economics_policy_from_payload,
    historical_execution_economics_policy_to_dict,
    historical_execution_quantize_price,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
    verify_historical_execution_economics_policy,
)
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, verify_historical_pit_dataset
from crypto_core.validation.paper_admission_ledger_bridge import (
    PaperAdmissionLedgerBridgeStatus,
    append_paper_admission_record_to_evidence_journal,
)
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    build_paper_allocator_intent_draft,
)
from crypto_core.validation.paper_capacity_gate import PaperCapacityGatePolicy, build_paper_capacity_gate_policy
from crypto_core.validation.paper_evidence_admission_record import (
    PaperEvidenceAdmissionStatus,
    build_paper_evidence_admission_record,
)
from crypto_core.validation.paper_governor_decision import (
    PaperGovernorDecision,
    PaperGovernorDecisionStatus,
    PaperGovernorPolicy,
    PaperGovernorVerdict,
    build_paper_governor_policy,
    decide_paper_governor,
)
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperGovernedLifecycleState,
    PaperPortfolioAllocationDecision,
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationStatus,
    paper_lifecycle_head_authority_digest,
    verify_paper_portfolio_allocation_decision,
)
from crypto_core.validation.paper_portfolio_governance_decision import (
    PaperPortfolioGovernanceDecision,
    PaperPortfolioGovernanceInputs,
    PaperPortfolioGovernanceStatus,
    verify_paper_portfolio_governance_decision,
)
from crypto_core.validation.paper_portfolio_performance_path_policy import (
    PaperPortfolioPerformancePathPolicy,
    paper_portfolio_performance_path_policy_from_payload,
    paper_portfolio_performance_path_policy_to_dict,
    verify_paper_portfolio_performance_path_policy,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    paper_portfolio_risk_envelope_from_payload,
    paper_portfolio_risk_envelope_to_dict,
    verify_paper_portfolio_risk_envelope,
)
from crypto_core.validation.paper_realized_pnl_rollup import PaperRealizedPnlRollupInput
from crypto_core.validation.paper_session_metrics_summary import (
    PaperSessionMetricsSummary,
    PaperSessionMetricsSummaryStatus,
    summarize_paper_session_metrics,
)
from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregateInput,
    build_paper_session_realized_pnl_aggregate,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
)
from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    PaperSessionRealizedPnlEvidenceManifestStatus,
    build_paper_session_realized_pnl_evidence_manifest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDayCloseValuation,
    PaperSleeveEpisodeEvidence,
    PaperSleeveValuationStatus,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownStatus,
    measure_paper_peak_distance,
    verify_paper_sleeve_drawdown_evidence,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PaperSleeveEquityBasisPolicy,
    PaperSleeveFundingTreatment,
    paper_sleeve_equity_basis_policy_from_payload,
    paper_sleeve_equity_basis_policy_to_dict,
    verify_paper_sleeve_equity_basis_policy,
)
from crypto_core.validation.paper_sleeve_funding_evidence import PaperSleeveFundingEvent
from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveState,
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
    paper_sleeve_state_digest,
)
from crypto_core.validation.paper_sleeve_performance_evidence import PaperSleevePerformanceStatus
from crypto_core.validation.paper_sleeve_promotion_candidate import (
    build_paper_sleeve_promotion_candidate,
    paper_sleeve_promotion_candidate_to_dict,
)
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderSeed,
    paper_sleeve_ladder_seed_digest,
    paper_sleeve_ladder_seed_from_payload,
    paper_sleeve_ladder_seed_to_dict,
    verify_paper_sleeve_ladder_seed,
)
from crypto_core.validation.paper_sleeve_promotion_readiness import (
    build_paper_sleeve_promotion_readiness,
    paper_sleeve_promotion_readiness_to_dict,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetPolicy,
    PaperSleeveRiskBudgetRecordStatus,
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
    paper_sleeve_risk_budget_decision_to_dict,
    paper_sleeve_risk_budget_policy_digest,
    paper_sleeve_risk_budget_policy_to_dict,
)
from crypto_core.validation.paper_stage4_readiness_decision import (
    PaperStage4ReadinessStatus,
    PaperStage4ReadinessVerdict,
    decide_paper_stage4_readiness,
)
from crypto_core.validation.paper_trade_tick import PaperTradeTick, build_paper_trade_tick, paper_trade_tick_to_dict
from crypto_core.validation.strategy_executable_binding import (
    StrategyExecutableBinding,
    StrategyExecutableParameterApproval,
    canonical_strategy_executable_parameter_approval,
    strategy_executable_binding_from_payload,
    strategy_executable_binding_to_dict,
    verify_strategy_executable_binding,
)
from crypto_core.validation.strategy_executable_profiles import (
    ProfileParameterAssignment,
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
    profile_parameter_assignment_digest,
)

_PREFIX = "governed_paper_execution_authority"
_GENESIS_SCHEMA_VERSION = "governed-paper-genesis.v2"
_CYCLE_SCHEMA_VERSION = "governed-paper-cycle-authority.v2"
_GENESIS_DIGEST_FIELD = "genesis_digest"
_CYCLE_DIGEST_FIELD = "cycle_digest"
_ADMISSION_SCHEMA_VERSION = "edge-paper-admission-decision.v2"
_UTC_DAY_NS = 86_400_000_000_000
_SUPPORTED_CAPACITY_MEASURE = (
    "max_open_position_notional",
    "quote_currency_notional",
    "per_instrument_open_position",
)
_LONG, _SHORT = "BUY", "SELL"

# The exact upstream reasons a bootstrap phase may carry, pinned so that any upstream change fails closed. ``{sleeve}``
# is the genesis sleeve; no other reason, no other sleeve and no other status is ever excepted.
_B0_DRAWDOWN_REASONS = (
    "paper_sleeve_drawdown_evidence:portfolio_requires_every_covered_sleeve_measured",
    "paper_sleeve_drawdown_evidence:sleeve_evidence_missing:{sleeve}",
)
_B1_PERFORMANCE_REASONS = (
    "paper_sharpe_evidence:insufficient_bucket_count",
    "paper_sharpe_evidence:insufficient_daily_return_count",
    "paper_sleeve_performance_evidence:sharpe_not_computed",
)
# RG-3 of a bootstrap sleeve whose derived metrics context cannot yet support a series: it carries none.
_B1_UNMEASURED_PERFORMANCE_REASONS = ("paper_sleeve_performance_evidence:daily_return_series_not_supplied",)
# The exact governor reasons of a sample below the C7 minimum (an insufficient sample, never a threshold breach).
_BELOW_GOVERNOR_MINIMUM_REASONS = ("paper_governor_decision:insufficient_computed_events",)
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

GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET: dict[str, object] = {
    "rule_set_id": "governed-paper-execution-authority.v2",
    "contract_id": "GOVERNED_PAPER_TYPED_PROVENANCE_V2",
    "trust_rule": "DERIVE_NOT_ACCEPT+CANONICAL_TYPED_IDENTITY+RECOMPUTED_DIGEST+PUBLIC_VERIFIER_REPROOF",
    "typed_identity_schema": "governed-paper-typed-image.v1",
    "genesis_schema_version": _GENESIS_SCHEMA_VERSION,
    "cycle_schema_version": _CYCLE_SCHEMA_VERSION,
    "admission_schema_version": _ADMISSION_SCHEMA_VERSION,
    "cycle_length_ns": _UTC_DAY_NS,
    "minimum_bootstrap_horizon_days": 30,
    "supported_capacity_measure": list(_SUPPORTED_CAPACITY_MEASURE),
    "reservation_price_rule": "latest_visible_mark_at_cycle_open_times_one_plus_band_price_grid_half_even",
    "reservation_tick_intent_type": "MARKETABLE_LIMIT",
    "direction_authority_rule": "own_eligible_record_reserved_equals_unit_times_reservation_and_rg7_final_equal",
    "bootstrap_b0_drawdown_reasons": list(_B0_DRAWDOWN_REASONS),
    "bootstrap_b1_performance_reasons": list(_B1_PERFORMANCE_REASONS),
    "bootstrap_b1_unmeasured_performance_reasons": list(_B1_UNMEASURED_PERFORMANCE_REASONS),
    "rg3_metrics_context_rule": "section7_chain_over_the_whole_sealed_history_under_the_genesis_c7_governor.v1",
    "rg3_metrics_context_anchor": "first_sealed_episode",
    "rg3_metrics_context_series_rule": "exact_derived_summary_when_sample_eligible_else_no_series",
    "rg3_metrics_context_below_minimum_reasons": list(_BELOW_GOVERNOR_MINIMUM_REASONS),
    "rg3_metrics_context_stop_rule": "governor_review_required_or_blocked_is_a_stop",
    "bootstrap_b1_drawdown_reasons": list(_B1_DRAWDOWN_REASONS),
    "bootstrap_b1_ladder_reasons": list(_B1_LADDER_REASONS),
    "bootstrap_b1_governance_reasons": list(_B1_GOVERNANCE_REASONS),
    "bootstrap_stop_rule": "max_peak_distance_strictly_above_any_rg2_portfolio_stop_level",
    "approval_rule": "exact_human_governance_commitments",
}
GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST = edge_sha256_text(
    edge_canonical_json(GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET)
)
_RULE_SET_ID = str(GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET["rule_set_id"])

GOVERNED_PAPER_AUTHORITY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("execution_authorized", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("real_capital_reserved", False),
    ("capital_allocated", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("venue_facts_proven", False),
    ("timestamp_origin_proven", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


class GovernedPaperExecutionAuthorityError(EdgeArtifactError):
    """Malformed input or a provenance defect: an invalid genesis or cycle is never represented."""


class GovernedPaperApprovalKind(str, Enum):
    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperGenesisStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class GovernedPaperCycleStatus(str, Enum):
    AUTHORIZED = "AUTHORIZED"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class GovernedPaperCyclePhase(str, Enum):
    BOOTSTRAP_B0 = "BOOTSTRAP_B0"
    BOOTSTRAP_B1 = "BOOTSTRAP_B1"
    ORDINARY = "ORDINARY"
    NOT_ESTABLISHED = "NOT_ESTABLISHED"


class GovernedPaperMetricsContextStatus(str, Enum):
    """What the derived RG-3 metrics context of one sealed history supports (see the module docstring)."""

    NO_COMPUTED_REALIZED_EVENT = "NO_COMPUTED_REALIZED_EVENT"
    BELOW_GOVERNOR_MINIMUM = "BELOW_GOVERNOR_MINIMUM"
    SAMPLE_ELIGIBLE = "SAMPLE_ELIGIBLE"
    GOVERNOR_REVIEW_REQUIRED = "GOVERNOR_REVIEW_REQUIRED"
    GOVERNOR_BLOCKED = "GOVERNOR_BLOCKED"


@dataclass(frozen=True)
class GovernedPaperGenesisApproval:
    """Human governance of one exact genesis policy (adoption C1, bootstrap C2 and the C7 governor thresholds)."""

    approval_reference: str
    approval_digest: str
    approval_kind: GovernedPaperApprovalKind
    approved_genesis_id: str
    approved_genesis_version: str
    approved_genesis_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class GovernedPaperCycleApproval:
    """Human governance of one exact cycle policy (C3)."""

    approval_reference: str
    approval_digest: str
    approval_kind: GovernedPaperApprovalKind
    approved_cycle_id: str
    approved_cycle_policy_digest: str
    approved_rule_set_digest: str


@dataclass(frozen=True)
class GovernedPaperGenesisInputs:
    """Everything a genesis consumes. There is no risk-budget policy input: it is derived from the EF-7 binding."""

    genesis_id: str
    genesis_version: str
    correlation_id: str
    paper_admission: EdgePaperAdmissionDecision
    expected_paper_admission_digest: str
    lifecycle_genesis: EdgeKillQuarantineDecision
    expected_lifecycle_genesis_digest: str
    executable_binding: StrategyExecutableBinding
    admitted_variant_id: str
    parameter_assignment: tuple[ProfileParameterAssignment, ...]
    parameter_approval: StrategyExecutableParameterApproval | None
    economics_policy: HistoricalExecutionEconomicsPolicy
    economics_approval: HistoricalExecutionEconomicsApproval | None
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    equity_basis_policy: PaperSleeveEquityBasisPolicy
    ladder_seed: PaperSleeveLadderSeed
    performance_path_policy: PaperPortfolioPerformancePathPolicy
    metrics_governor_policy: PaperGovernorPolicy
    genesis_start_ns: int
    bootstrap_horizon_days: int
    reservation_band: str
    approval: GovernedPaperGenesisApproval | None


@dataclass(frozen=True)
class GovernedPaperGenesis:
    """One sleeve's governed paper genesis: the derived, typed-identity-bound authorities of the whole paper period."""

    schema_version: str
    status: GovernedPaperGenesisStatus
    authorized: bool
    genesis_id: str
    genesis_version: str
    correlation_id: str
    sleeve_id: str
    instrument: str
    market_type: str
    paper_admission_digest: str
    walk_forward_evidence_digest: str
    lifecycle_genesis_digest: str
    lifecycle_subject_digest: str
    lifecycle_effective_at_ns: int
    source_manifest_digest: str
    data_requirement_registry_digest: str
    executable_binding_digest: str
    strategy_spec_digest: str
    strategy_id: str
    profile_semantics_digest: str
    admitted_variant_id: str
    parameter_assignment_digest: str
    unit_size: str
    parameter_approval_identity_digest: str
    economics_policy_digest: str
    economics_approval_identity_digest: str
    risk_budget_policy_id: str
    risk_budget_policy_digest: str
    risk_budget_policy_identity_digest: str
    admission_cap_fraction: str
    capacity_assumption_id: str
    capacity_max_value: str
    portfolio_risk_envelope_digest: str
    equity_basis_policy_digest: str
    ladder_seed_digest: str
    performance_path_policy_digest: str
    metrics_governor_policy_digest: str
    metrics_governor_policy_identity_digest: str
    genesis_start_ns: int
    bootstrap_horizon_days: int
    bootstrap_end_ns: int
    reservation_band: str
    genesis_inputs_identity_digest: str
    genesis_policy_digest: str
    rule_set_id: str
    rule_set_digest: str
    approval: GovernedPaperGenesisApproval | None
    synthetic_test_approval_used: bool
    reason_codes: tuple[str, ...]
    genesis_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    capital_allocated: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    venue_facts_proven: bool = False
    timestamp_origin_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


@dataclass(frozen=True)
class GovernedPaperCycleInputs:
    """Everything one cycle consumes; the sealed history is the cumulative history sealed before ``E_k``."""

    cycle_id: str
    correlation_id: str
    day_index: int
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    sealed_episodes: tuple[PaperSleeveEpisodeEvidence, ...]
    sealed_day_closes: tuple[PaperSleeveDayCloseValuation, ...]
    sealed_funding_events: tuple[PaperSleeveFundingEvent, ...]
    reservation_dataset: HistoricalPitDataset
    allocation_inputs: PaperPortfolioAllocationInputs
    allocation_decision: PaperPortfolioAllocationDecision
    drawdown_inputs: PaperSleeveDrawdownInputs | None
    drawdown_evidence: PaperSleeveDrawdownEvidence | None
    governance_inputs: PaperPortfolioGovernanceInputs | None
    governance_decision: PaperPortfolioGovernanceDecision | None
    approval: GovernedPaperCycleApproval | None


@dataclass(frozen=True)
class GovernedPaperCycleAuthority:
    """Prospective paper authority for one UTC day; per-direction ceilings, never an execution permission."""

    schema_version: str
    status: GovernedPaperCycleStatus
    authorized: bool
    phase: GovernedPaperCyclePhase
    cycle_id: str
    correlation_id: str
    genesis_id: str
    genesis_digest: str
    sleeve_id: str
    instrument: str
    day_index: int
    window_start_ns: int
    window_end_ns: int
    sealed_history_digest: str
    sealed_episode_count: int
    sealed_day_count: int
    sealed_funding_event_count: int
    reservation_dataset_digest: str
    reservation_mark_record_digest: str
    reservation_mark_price: str
    reservation_price: str
    unit_size: str
    reservation_notional: str
    capacity_max_value: str
    reservation_state_digest: str
    reservation_decision_digest: str
    reservation_draft_digest: str
    long_record_status: str
    long_reserved_budget: str
    long_final_allocated_budget: str
    long_authorized: bool
    short_record_status: str
    short_reserved_budget: str
    short_final_allocated_budget: str
    short_authorized: bool
    max_long_quantity: str
    max_short_quantity: str
    eligible_direction_count: int
    lifecycle_head_digest: str
    lifecycle_head_authority_digest: str
    allocation_decision_digest: str
    allocation_status: str
    drawdown_evidence_digest: str
    drawdown_status: str
    governance_decision_digest: str
    governance_status: str
    performance_evidence_digest: str
    performance_status: str
    metrics_context_status: str
    metrics_summary_digest: str
    metrics_governor_decision_digest: str
    bootstrap_max_peak_distance: str
    cycle_policy_digest: str
    rule_set_id: str
    rule_set_digest: str
    approval: GovernedPaperCycleApproval | None
    synthetic_test_approval_used: bool
    reason_codes: tuple[str, ...]
    cycle_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    capital_allocated: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    venue_facts_proven: bool = False
    timestamp_origin_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


@dataclass(frozen=True)
class GovernedPaperGenesisAuthority:
    """The canonical reconstructions a verified AUTHORIZED genesis lets downstream use (never caller originals)."""

    genesis: GovernedPaperGenesis
    paper_admission: EdgePaperAdmissionDecision
    lifecycle_genesis: EdgeKillQuarantineDecision
    executable_binding: StrategyExecutableBinding
    strategy_spec: StrategySpec
    parameter_assignment: tuple[ProfileParameterAssignment, ...]
    parameter_approval: StrategyExecutableParameterApproval
    economics_policy: HistoricalExecutionEconomicsPolicy
    economics_approval: HistoricalExecutionEconomicsApproval
    risk_budget_policy: PaperSleeveRiskBudgetPolicy
    portfolio_risk_envelope: PaperPortfolioRiskEnvelope
    equity_basis_policy: PaperSleeveEquityBasisPolicy
    ladder_seed: PaperSleeveLadderSeed
    performance_path_policy: PaperPortfolioPerformancePathPolicy
    metrics_governor_policy: PaperGovernorPolicy


@dataclass(frozen=True)
class GovernedPaperMetricsContext:
    """The derived RG-3 metrics context of one cumulative sealed history (never supplied, never a value).

    ``summary`` is the section-7 metrics summary of the whole sealed history (None without any computed realized
    event); ``governor_decision`` is its governor decision under the genesis C7 policy (None likewise).
    """

    status: GovernedPaperMetricsContextStatus
    governor_policy_digest: str
    manifest_digest: str
    governor_decision: PaperGovernorDecision | None
    summary: PaperSessionMetricsSummary | None

    @property
    def series_summary(self) -> PaperSessionMetricsSummary | None:
        """The summary RG-3 carries: the derived one when sample-eligible, otherwise None (RG-3 carries no series)."""

        return self.summary if self.status is GovernedPaperMetricsContextStatus.SAMPLE_ELIGIBLE else None


@dataclass(frozen=True)
class GovernedPaperReservationPlan:
    """The derived reservation of one cycle opening: the quote, the journaled ticks and their public decisions.

    Callers build RG-7 over exactly this plan; the cycle re-derives it and refuses any other reservation.
    """

    reservation_mark_record_digest: str
    reservation_mark_price: str
    reservation_price: str
    ticks: tuple[PaperTradeTick, ...]
    state: PaperSleeveState
    risk_budget_policy: PaperSleeveRiskBudgetPolicy
    risk_budget_decision: PaperSleeveRiskBudgetDecision
    allocator_draft: PaperAllocatorIntentDraft


@dataclass(frozen=True)
class GovernedPaperCycleReservation:
    """The derived reservation of one verified AUTHORIZED cycle (what a projected episode is built from)."""

    cycle: GovernedPaperCycleAuthority
    plan: GovernedPaperReservationPlan
    capacity_policy: PaperCapacityGatePolicy

    @property
    def allocator_draft(self) -> PaperAllocatorIntentDraft:
        return self.plan.allocator_draft


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperExecutionAuthorityError:
    return GovernedPaperExecutionAuthorityError(_reason(code))


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


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _plain(value: Fraction) -> str:
    """Exact plain decimal text of a terminating value (the generic paper grammar); raises when it does not terminate."""

    numerator, denominator = value.numerator, value.denominator
    scale = 0
    while denominator != 1:
        if denominator % 10 == 0:
            denominator //= 10
        elif denominator % 2 == 0:
            denominator //= 2
            numerator *= 5
        elif denominator % 5 == 0:
            denominator //= 5
            numerator *= 2
        else:
            raise _fail("decimal_not_terminating")
        scale += 1
    digits = str(abs(numerator)).rjust(scale + 1, "0")
    text = f"{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".") if scale else digits
    return f"-{text}" if numerator < 0 else text


def _scale18(value: Fraction, field_name: str) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None or Fraction(rendered) != value:
        raise _fail(f"value_not_exactly_representable:{field_name}")
    return rendered


def _verified_digest(value: object, verify: Callable[[object], EdgeEvidenceVerification], code: str) -> str:
    verification = verify(value)
    if not verification.intact or not edge_is_hex64(verification.recomputed_digest):
        raise _fail(f"{code}_not_authentic")
    return verification.recomputed_digest


def _reconstruct(value: object, to_dict: Callable[[object], dict], from_payload: Callable[[object], object]) -> object:
    """The strict canonical reconstruction of an already re-proven upstream artifact (only it is used afterwards)."""

    return from_payload(json.loads(edge_canonical_json(to_dict(value))))


def _approval_reasons(approval: object, *, kind: object, expected: Mapping[str, object], prefix: str) -> list[str]:
    if approval is None:
        return [_reason(f"{prefix}_approval_missing")]
    if approval.approval_kind is not kind.HUMAN_GOVERNANCE:  # type: ignore[attr-defined]
        return [_reason(f"{prefix}_approval_not_human_governance")]
    return [
        _reason(f"{prefix}_approval_mismatch:{name}")
        for name, value in expected.items()
        if type(getattr(approval, name)) is not type(value) or getattr(approval, name) != value
    ]


def _canonical_approval(approval: object, cls: type, code: str) -> object:
    if approval is None:
        return None
    if type(approval) is not cls:
        raise _fail(f"{code}_malformed")
    canonical = cls(
        approval_reference=_require_text(approval.approval_reference, f"{code}_reference"),  # type: ignore[attr-defined]
        approval_digest=_require_hex64(approval.approval_digest, f"{code}_digest"),  # type: ignore[attr-defined]
        **{
            item.name: getattr(approval, item.name)
            for item in fields(cls)
            if item.name not in ("approval_reference", "approval_digest")
        },
    )
    if type(canonical.approval_kind) is not GovernedPaperApprovalKind:
        raise _fail(f"{code}_kind_malformed")
    for item in fields(cls):
        if item.name.startswith("approved_"):
            value = getattr(canonical, item.name)
            if item.name.endswith("_digest"):
                _require_hex64(value, f"{code}_{item.name}")
            else:
                _require_text(value, f"{code}_{item.name}")
    return canonical


# --- typed identity domains ----------------------------------------------------------------------------------------------

_UPSTREAM_REFERENCES = (
    EdgePaperAdmissionDecision,
    EdgeKillQuarantineDecision,
    StrategyExecutableBinding,
    HistoricalExecutionEconomicsPolicy,
    PaperPortfolioRiskEnvelope,
    PaperSleeveEquityBasisPolicy,
    PaperSleeveLadderSeed,
    PaperPortfolioPerformancePathPolicy,
)
_GENESIS_INPUTS_DOMAIN = GovernedPaperTypeDomain(
    "governed-paper-genesis-inputs.v2", roots=(GovernedPaperGenesisInputs,), references=_UPSTREAM_REFERENCES
)
_GENESIS_DOMAIN = GovernedPaperTypeDomain(_GENESIS_SCHEMA_VERSION, roots=(GovernedPaperGenesis,))
_CYCLE_DOMAIN = GovernedPaperTypeDomain(_CYCLE_SCHEMA_VERSION, roots=(GovernedPaperCycleAuthority,))
_RECORD_DOMAIN = GovernedPaperTypeDomain(
    "governed-paper-governance-records.v2",
    roots=(
        ProfileParameterAssignment,
        StrategyExecutableParameterApproval,
        HistoricalExecutionEconomicsApproval,
        PaperSleeveRiskBudgetPolicy,
        PaperGovernorPolicy,
    ),
)
# The RG-3 metrics context: a supplied summary must be typed-identical to the derived one.
_METRICS_DOMAIN = GovernedPaperTypeDomain("governed-paper-rg3-metrics-summary.v1", roots=(PaperSessionMetricsSummary,))
# The sealed history: the closure of the RG-3 episode, day-close and funding-event schemas. The StrategySpec carries
# open ``dict[str, Any]`` fields, so it is a reference re-proven through its public digest, never imaged.
_HISTORY_DOMAIN = GovernedPaperTypeDomain(
    "governed-paper-sealed-history.v1",
    roots=(PaperSleeveEpisodeEvidence, PaperSleeveDayCloseValuation, PaperSleeveFundingEvent),
    references=(StrategySpec,),
)


def _history_resolver(strategy_spec_digest_anchor: str) -> Mapping[type, Callable[[object], str]]:
    def resolve(spec: object) -> str:
        digest = strategy_spec_digest(spec)  # type: ignore[arg-type]
        if digest != strategy_spec_digest_anchor:
            raise _fail("sealed_history_strategy_spec_foreign")
        return digest

    return {StrategySpec: resolve}


def governed_paper_sealed_history_digest(
    episodes: tuple[PaperSleeveEpisodeEvidence, ...],
    day_closes: tuple[PaperSleeveDayCloseValuation, ...],
    funding_events: tuple[PaperSleeveFundingEvent, ...],
    *,
    strategy_spec_digest_anchor: str,
) -> str:
    """The typed identity of one cumulative sealed history (TCI_V1; the StrategySpec as a re-proven reference)."""

    if type(episodes) is not tuple or type(day_closes) is not tuple or type(funding_events) is not tuple:
        raise _fail("sealed_history_malformed")
    return governed_paper_typed_identity_digest(
        (episodes, day_closes, funding_events),
        _HISTORY_DOMAIN,
        resolve=_history_resolver(strategy_spec_digest_anchor),
    )


# --- genesis -------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _GenesisProof:
    authority: GovernedPaperGenesisAuthority | None
    facts: dict[str, object]
    blocked: list[str]
    governance: list[str]


def _derive_risk_budget_policy(admission: EdgePaperAdmissionDecision) -> PaperSleeveRiskBudgetPolicy:
    """Rebuild the EF-7-bound policy; the stored digest is never trusted (DERIVE_NOT_ACCEPT, B1)."""

    binding = admission.risk_budget_policy_binding
    if type(binding) is not EdgeAuthorityBinding:
        raise _fail("risk_budget_policy_binding_malformed")
    snapshot = edge_authority_binding_snapshot(binding)
    texts = ("schema_version", "policy_id", "sleeve_id", "total_budget", "per_intent_budget_cap", "policy_digest")
    flags = ("require_journal_bound", "paper_only", "real_orders_enabled", "real_money_enabled")
    if (
        type(snapshot) is not dict
        or set(snapshot) != {*texts, *flags, "per_instrument_budget_cap", "metadata"}
        or any(type(snapshot[name]) is not str for name in texts)
        or any(type(snapshot[name]) is not bool for name in flags)
        or not (snapshot["per_instrument_budget_cap"] is None or type(snapshot["per_instrument_budget_cap"]) is str)
        or type(snapshot["metadata"]) is not list
        or any(
            type(pair) is not list or len(pair) != 2 or any(type(text) is not str for text in pair)
            for pair in snapshot["metadata"]
        )
    ):
        raise _fail("risk_budget_policy_snapshot_malformed")
    try:
        rebuilt = build_paper_sleeve_risk_budget_policy(
            policy_id=snapshot["policy_id"],
            sleeve_id=snapshot["sleeve_id"],
            total_budget=snapshot["total_budget"],
            per_intent_budget_cap=snapshot["per_intent_budget_cap"],
            per_instrument_budget_cap=snapshot["per_instrument_budget_cap"],
            require_journal_bound=snapshot["require_journal_bound"],
            metadata=dict(snapshot["metadata"]),
        )
    except Exception as exc:  # noqa: BLE001 - the public builder refusing the bound fields is a provenance defect
        raise _fail("risk_budget_policy_rebuild_failed") from exc
    if edge_canonical_json(paper_sleeve_risk_budget_policy_to_dict(rebuilt)) != binding.snapshot_json:
        raise _fail("risk_budget_policy_noncanonical")
    recomputed = paper_sleeve_risk_budget_policy_digest(rebuilt)
    if (
        recomputed != snapshot["policy_digest"]
        or recomputed != binding.expected_digest
        or recomputed != admission.risk_budget_policy_digest
    ):
        raise _fail("risk_budget_policy_digest_mismatch")
    return rebuilt


def _strategy_spec_of(binding: StrategyExecutableBinding) -> StrategySpec:
    try:
        admission = edge_strategy_spec_admission_from_payload(
            edge_authority_binding_snapshot(binding.admission_binding)
        )
        result = validate_strategy_spec(edge_authority_binding_snapshot(admission.strategy_spec_binding))
    except Exception as exc:  # noqa: BLE001 - an underivable spec is a provenance defect
        raise _fail("strategy_spec_unavailable") from exc
    if result.accepted is not True or type(result.spec) is not StrategySpec:
        raise _fail("strategy_spec_unavailable")
    return result.spec


def _capacity(
    admission: EdgePaperAdmissionDecision, instrument: str, blocked: list[str]
) -> EdgeCapacityAssumption | None:
    supported: list[EdgeCapacityAssumption] = []
    for item in admission.capacity_assumptions:
        if item.instrument != instrument:
            continue
        if (item.capacity_measure_id, item.unit_id, item.scope_id) == _SUPPORTED_CAPACITY_MEASURE:
            supported.append(item)
        else:
            blocked.append(_reason(f"capacity_measure_unsupported:{item.assumption_id}"))
    if len(supported) != 1:
        blocked.append(_reason("capacity_assumption_not_unique" if supported else "capacity_assumption_missing"))
        return None
    return supported[0]


def _canonical_governor_policy(policy: object) -> PaperGovernorPolicy:
    """C7 rebuilt by its public builder (every threshold invariant re-checked); the record must be typed-identical."""

    if type(policy) is not PaperGovernorPolicy:
        raise _fail("metrics_governor_policy_malformed")
    try:
        canonical = build_paper_governor_policy(
            policy_id=policy.policy_id,
            min_computed_event_count=policy.min_computed_event_count,
            max_abs_realized_pnl=policy.max_abs_realized_pnl,
            review_abs_realized_pnl=policy.review_abs_realized_pnl,
            max_closed_units=policy.max_closed_units,
            metadata=dict(policy.metadata),
        )
        identical = governed_paper_typed_identical(canonical, policy, _RECORD_DOMAIN)
    except Exception as exc:  # noqa: BLE001 - a policy its builder or the record schema refuses is never C7
        raise _fail("metrics_governor_policy_invalid") from exc
    if not identical:
        raise _fail("metrics_governor_policy_not_canonical")
    return canonical


def _genesis_proof(inputs: GovernedPaperGenesisInputs) -> _GenesisProof:  # noqa: C901 - one linear re-proof
    if type(inputs) is not GovernedPaperGenesisInputs:
        raise _fail("genesis_inputs_malformed")
    genesis_id = _require_text(inputs.genesis_id, "genesis_id")
    _require_text(inputs.genesis_version, "genesis_version")
    _require_text(inputs.correlation_id, "correlation_id")
    blocked: list[str] = []
    governance: list[str] = []

    # EF-7: public verifier, recomputed digest == caller anchor, strict reconstruction used afterwards.
    if type(inputs.paper_admission) is not EdgePaperAdmissionDecision:
        raise _fail("paper_admission_malformed")
    admission_digest = _verified_digest(inputs.paper_admission, verify_edge_paper_admission_decision, "paper_admission")
    if admission_digest != _require_hex64(inputs.expected_paper_admission_digest, "expected_paper_admission_digest"):
        raise _fail("paper_admission_digest_mismatch")
    admission: EdgePaperAdmissionDecision = _reconstruct(  # type: ignore[assignment]
        inputs.paper_admission, edge_paper_admission_decision_to_dict, edge_paper_admission_decision_from_payload
    )
    if admission.schema_version != _ADMISSION_SCHEMA_VERSION:
        raise _fail("paper_admission_schema_unsupported")
    if (
        admission.status is not EdgeEvidenceStatus.READY
        or admission.gate_verdict is not EdgeGateVerdict.PASS
        or admission.advances is not True
        or admission.candidate_admitted_to_paper is not True
    ):
        blocked.append(_reason("paper_admission_not_admitted"))
    sleeve_id = admission.paper_sleeve_id
    walk_forward = edge_walk_forward_oos_evidence_from_payload(
        edge_authority_binding_snapshot(admission.predecessor_binding)
    )
    if walk_forward.walk_forward_oos_evidence_digest != admission.predecessor_digest:
        raise _fail("walk_forward_evidence_digest_mismatch")
    if len(admission.pinned_instrument_universe) != 1:
        blocked.append(_reason("instrument_universe_not_single"))
    instrument = admission.pinned_instrument_universe[0] if admission.pinned_instrument_universe else ""
    if walk_forward.evaluated_instrument != instrument:
        raise _fail("walk_forward_instrument_mismatch")

    # EF-8 INITIAL_ACTIVATION of exactly this admission and sleeve.
    if type(inputs.lifecycle_genesis) is not EdgeKillQuarantineDecision:
        raise _fail("lifecycle_genesis_malformed")
    lifecycle_digest = _verified_digest(
        inputs.lifecycle_genesis, verify_edge_kill_quarantine_decision, "lifecycle_genesis"
    )
    if lifecycle_digest != _require_hex64(
        inputs.expected_lifecycle_genesis_digest, "expected_lifecycle_genesis_digest"
    ):
        raise _fail("lifecycle_genesis_digest_mismatch")
    lifecycle: EdgeKillQuarantineDecision = _reconstruct(  # type: ignore[assignment]
        inputs.lifecycle_genesis, edge_kill_quarantine_decision_to_dict, edge_kill_quarantine_decision_from_payload
    )
    if (
        lifecycle.transition is not EdgeLifecycleTransition.INITIAL_ACTIVATION
        or lifecycle.admission_decision_digest != admission_digest
        or lifecycle.cycle_admission_decision_digest != admission_digest
        or lifecycle.paper_sleeve_id != sleeve_id
    ):
        raise _fail("lifecycle_genesis_mismatch")
    if (
        lifecycle.status is not EdgeEvidenceStatus.READY
        or lifecycle.advances is not True
        or lifecycle.resulting_lifecycle_state is not EdgeLifecycleState.ACTIVE
    ):
        blocked.append(_reason("lifecycle_genesis_not_active"))

    # Executable binding, StrategySpec, admitted variant, exact parameter assignment and its approval.
    if type(inputs.executable_binding) is not StrategyExecutableBinding:
        raise _fail("executable_binding_malformed")
    binding_digest = _verified_digest(
        inputs.executable_binding, verify_strategy_executable_binding, "executable_binding"
    )
    if binding_digest != admission.executable_binding_digest:
        raise _fail("executable_binding_digest_mismatch")
    binding: StrategyExecutableBinding = _reconstruct(  # type: ignore[assignment]
        inputs.executable_binding, strategy_executable_binding_to_dict, strategy_executable_binding_from_payload
    )
    spec = _strategy_spec_of(binding)
    spec_digest = strategy_spec_digest(spec)
    if spec_digest != admission.strategy_spec_digest:
        raise _fail("strategy_spec_digest_mismatch")
    variant_id = _require_text(inputs.admitted_variant_id, "admitted_variant_id")
    variants = [item for item in admission.admitted_variants if item.variant_id == variant_id]
    if len(variants) != 1:
        raise _fail("admitted_variant_unknown")
    try:
        assignment = canonical_profile_parameter_assignment(
            get_strategy_executable_profile(binding.profile_id), inputs.parameter_assignment
        )
    except Exception as exc:  # noqa: BLE001 - an assignment the profile refuses is never paper authority
        raise _fail("parameter_assignment_invalid") from exc
    if type(inputs.parameter_assignment) is not tuple or not governed_paper_typed_identical(
        tuple(assignment), inputs.parameter_assignment, _RECORD_DOMAIN
    ):
        raise _fail("parameter_assignment_not_canonical")
    assignment_digest = profile_parameter_assignment_digest(assignment)
    if assignment_digest != variants[0].parameter_assignment_digest:
        raise _fail("parameter_assignment_not_the_admitted_variant")
    units = [item.value for item in assignment if item.parameter_id == "unit_size"]
    if len(units) != 1 or not historical_execution_decimal_is_canonical(units[0]) or Fraction(units[0]) <= 0:
        raise _fail("unit_size_unavailable")
    unit_size = units[0]
    try:
        parameter_approval = canonical_strategy_executable_parameter_approval(inputs.parameter_approval)
    except Exception as exc:  # noqa: BLE001
        raise _fail("parameter_approval_malformed") from exc
    if parameter_approval is not None and not governed_paper_typed_identical(
        parameter_approval, inputs.parameter_approval, _RECORD_DOMAIN
    ):
        raise _fail("parameter_approval_not_canonical")
    if parameter_approval is None:
        governance.append(_reason("parameter_approval_missing"))
    else:
        governance.extend(
            _reason(f"parameter_approval_mismatch:{name}")
            for name, value in (
                ("approved_executable_binding_digest", binding_digest),
                ("approved_strategy_spec_digest", spec_digest),
                ("approved_profile_semantics_digest", admission.profile_semantics_digest),
                ("approved_parameter_assignment_digest", assignment_digest),
            )
            if getattr(parameter_approval, name) != value
        )

    # Economics policy (EF-6 anchor) and its approval.
    if type(inputs.economics_policy) is not HistoricalExecutionEconomicsPolicy:
        raise _fail("economics_policy_malformed")
    policy_digest = _verified_digest(
        inputs.economics_policy, verify_historical_execution_economics_policy, "economics_policy"
    )
    if policy_digest != walk_forward.economics_policy_digest:
        raise _fail("economics_policy_not_the_walk_forward_policy")
    policy: HistoricalExecutionEconomicsPolicy = _reconstruct(  # type: ignore[assignment]
        inputs.economics_policy,
        historical_execution_economics_policy_to_dict,
        historical_execution_economics_policy_from_payload,
    )
    if policy.status is not EdgeEvidenceStatus.READY or policy.advances is not True:
        blocked.append(_reason("economics_policy_not_ready"))
    if policy.instrument != instrument:
        raise _fail("economics_policy_instrument_mismatch")
    try:
        economics_approval = canonical_historical_execution_economics_approval(inputs.economics_approval)
    except Exception as exc:  # noqa: BLE001
        raise _fail("economics_approval_malformed") from exc
    if economics_approval is not None and not governed_paper_typed_identical(
        economics_approval, inputs.economics_approval, _RECORD_DOMAIN
    ):
        raise _fail("economics_approval_not_canonical")
    if economics_approval is None:
        governance.append(_reason("economics_approval_missing"))
    elif economics_approval.approval_kind is not HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE:
        governance.append(_reason("economics_approval_not_human_governance"))
    else:
        governance.extend(
            _reason(f"economics_approval_mismatch:{name}")
            for name in historical_execution_economics_approval_mismatches(
                economics_approval,
                policy=policy,
                strategy_spec_digest=spec_digest,
                instrument=instrument,
                market_type=admission.market_type,
                data_requirement_registry_digest=walk_forward.data_requirement_registry_digest,
            )
        )

    # RG-2 envelope, equity basis, RG-6 seed and RG-4 performance-path policy.
    upstream: dict[str, object] = {}
    for name, cls, verify, to_dict, from_payload in (
        (
            "portfolio_risk_envelope",
            PaperPortfolioRiskEnvelope,
            verify_paper_portfolio_risk_envelope,
            paper_portfolio_risk_envelope_to_dict,
            paper_portfolio_risk_envelope_from_payload,
        ),
        (
            "equity_basis_policy",
            PaperSleeveEquityBasisPolicy,
            verify_paper_sleeve_equity_basis_policy,
            paper_sleeve_equity_basis_policy_to_dict,
            paper_sleeve_equity_basis_policy_from_payload,
        ),
        (
            "ladder_seed",
            PaperSleeveLadderSeed,
            verify_paper_sleeve_ladder_seed,
            paper_sleeve_ladder_seed_to_dict,
            paper_sleeve_ladder_seed_from_payload,
        ),
        (
            "performance_path_policy",
            PaperPortfolioPerformancePathPolicy,
            verify_paper_portfolio_performance_path_policy,
            paper_portfolio_performance_path_policy_to_dict,
            paper_portfolio_performance_path_policy_from_payload,
        ),
    ):
        value = getattr(inputs, name)
        if type(value) is not cls:
            raise _fail(f"{name}_malformed")
        upstream[f"{name}_digest"] = _verified_digest(value, verify, name)
        upstream[name] = _reconstruct(value, to_dict, from_payload)
        if upstream[name].advances is not True:  # type: ignore[attr-defined]
            governance.append(_reason(f"{name}_not_governed"))
    envelope: PaperPortfolioRiskEnvelope = upstream["portfolio_risk_envelope"]  # type: ignore[assignment]
    basis: PaperSleeveEquityBasisPolicy = upstream["equity_basis_policy"]  # type: ignore[assignment]
    seed: PaperSleeveLadderSeed = upstream["ladder_seed"]  # type: ignore[assignment]
    path: PaperPortfolioPerformancePathPolicy = upstream["performance_path_policy"]  # type: ignore[assignment]
    envelope_digest = str(upstream["portfolio_risk_envelope_digest"])
    if sleeve_id not in [item.sleeve_id for item in envelope.sleeve_caps]:
        blocked.append(_reason("envelope_sleeve_undeclared"))
    if basis.sleeve_id != sleeve_id or basis.market_symbol != instrument:
        blocked.append(_reason("equity_basis_policy_subject_mismatch"))
    if Fraction(basis.paper_performance_reference_notional) != Fraction(policy.initial_equity):
        blocked.append(_reason("equity_basis_reference_not_initial_equity"))
    if basis.funding_treatment is not PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED:
        blocked.append(_reason("equity_basis_funding_not_evidence_required"))
    if seed.sleeve_id != sleeve_id or seed.envelope_digest != envelope_digest:
        blocked.append(_reason("ladder_seed_subject_mismatch"))
    if path.envelope_digest != envelope_digest:
        blocked.append(_reason("performance_path_policy_envelope_mismatch"))

    # C7: the governor policy of the RG-3 metrics context, adopted only through the exact genesis approval.
    governor_policy = _canonical_governor_policy(inputs.metrics_governor_policy)

    # The derived risk-budget policy (B1) and the one supported capacity assumption (GAP-3).
    risk_budget_policy = _derive_risk_budget_policy(admission)
    if risk_budget_policy.sleeve_id != sleeve_id:
        raise _fail("risk_budget_policy_sleeve_mismatch")
    if risk_budget_policy.require_journal_bound is not True:
        blocked.append(_reason("risk_budget_policy_not_journal_bound"))
    capacity = _capacity(admission, instrument, blocked)

    # The paper period: a UTC-day genesis after the activation, a horizon of at least 30 days and a band.
    start = inputs.genesis_start_ns
    if not historical_execution_wire_int_is_valid(start, minimum=0) or start % _UTC_DAY_NS != 0:
        raise _fail("genesis_start_ns_invalid")
    if start < lifecycle.effective_at_ns:
        blocked.append(_reason("genesis_before_lifecycle_activation"))
    horizon = inputs.bootstrap_horizon_days
    if type(horizon) is not int or horizon < 1:
        raise _fail("bootstrap_horizon_days_invalid")
    if horizon < int(GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET["minimum_bootstrap_horizon_days"]):  # type: ignore[call-overload]
        blocked.append(_reason("bootstrap_horizon_below_minimum"))
    bootstrap_end = start + horizon * _UTC_DAY_NS
    if not historical_execution_wire_int_is_valid(bootstrap_end, minimum=0):
        raise _fail("bootstrap_horizon_days_invalid")
    band = inputs.reservation_band
    if not historical_execution_decimal_is_canonical(band) or Fraction(band) < 0:
        raise _fail("reservation_band_invalid")

    # The typed identity of the complete inputs (the approval excluded: it commits to this identity).
    known: dict[int, tuple[object, str]] = {
        id(inputs.paper_admission): (inputs.paper_admission, admission_digest),
        id(inputs.lifecycle_genesis): (inputs.lifecycle_genesis, lifecycle_digest),
        id(inputs.executable_binding): (inputs.executable_binding, binding_digest),
        id(inputs.economics_policy): (inputs.economics_policy, policy_digest),
        **{
            id(getattr(inputs, name)): (getattr(inputs, name), str(upstream[f"{name}_digest"]))
            for name in ("portfolio_risk_envelope", "equity_basis_policy", "ladder_seed", "performance_path_policy")
        },
    }

    def resolve(value: object) -> str:
        entry = known.get(id(value))
        if entry is None or entry[0] is not value:
            raise _fail("genesis_reference_unverified")
        return entry[1]

    identity = governed_paper_typed_identity_digest(
        replace(inputs, approval=None),
        _GENESIS_INPUTS_DOMAIN,
        resolve=dict.fromkeys(_UPSTREAM_REFERENCES, resolve),
    )
    facts: dict[str, object] = {
        "genesis_id": genesis_id,
        "genesis_version": inputs.genesis_version,
        "correlation_id": inputs.correlation_id,
        "sleeve_id": sleeve_id,
        "instrument": instrument,
        "market_type": admission.market_type,
        "paper_admission_digest": admission_digest,
        "walk_forward_evidence_digest": admission.predecessor_digest,
        "lifecycle_genesis_digest": lifecycle_digest,
        "lifecycle_subject_digest": lifecycle.lifecycle_subject_digest,
        "lifecycle_effective_at_ns": lifecycle.effective_at_ns,
        "source_manifest_digest": admission.source_manifest_digest,
        "data_requirement_registry_digest": walk_forward.data_requirement_registry_digest,
        "executable_binding_digest": binding_digest,
        "strategy_spec_digest": spec_digest,
        "strategy_id": admission.strategy_id,
        "profile_semantics_digest": admission.profile_semantics_digest,
        "admitted_variant_id": variant_id,
        "parameter_assignment_digest": assignment_digest,
        "unit_size": unit_size,
        "parameter_approval_identity_digest": ""
        if parameter_approval is None
        else governed_paper_typed_identity_digest(parameter_approval, _RECORD_DOMAIN),
        "economics_policy_digest": policy_digest,
        "economics_approval_identity_digest": ""
        if economics_approval is None
        else governed_paper_typed_identity_digest(economics_approval, _RECORD_DOMAIN),
        "risk_budget_policy_id": risk_budget_policy.policy_id,
        "risk_budget_policy_digest": paper_sleeve_risk_budget_policy_digest(risk_budget_policy),
        "risk_budget_policy_identity_digest": governed_paper_typed_identity_digest(risk_budget_policy, _RECORD_DOMAIN),
        "admission_cap_fraction": admission.admission_cap_fraction,
        "capacity_assumption_id": "" if capacity is None else capacity.assumption_id,
        "capacity_max_value": "" if capacity is None else capacity.max_value,
        "portfolio_risk_envelope_digest": envelope_digest,
        "equity_basis_policy_digest": str(upstream["equity_basis_policy_digest"]),
        "ladder_seed_digest": str(upstream["ladder_seed_digest"]),
        "performance_path_policy_digest": str(upstream["performance_path_policy_digest"]),
        "metrics_governor_policy_digest": governor_policy.policy_digest,
        "metrics_governor_policy_identity_digest": governed_paper_typed_identity_digest(
            governor_policy, _RECORD_DOMAIN
        ),
        "genesis_start_ns": start,
        "bootstrap_horizon_days": horizon,
        "bootstrap_end_ns": bootstrap_end,
        "reservation_band": band,
        "genesis_inputs_identity_digest": identity,
    }
    authority = None
    if parameter_approval is not None and economics_approval is not None:
        authority = GovernedPaperGenesisAuthority(
            genesis=None,  # type: ignore[arg-type] - completed by the assembly
            paper_admission=admission,
            lifecycle_genesis=lifecycle,
            executable_binding=binding,
            strategy_spec=spec,
            parameter_assignment=tuple(assignment),
            parameter_approval=parameter_approval,
            economics_policy=policy,
            economics_approval=economics_approval,
            risk_budget_policy=risk_budget_policy,
            portfolio_risk_envelope=envelope,
            equity_basis_policy=basis,
            ladder_seed=seed,
            performance_path_policy=path,
            metrics_governor_policy=governor_policy,
        )
    return _GenesisProof(authority, facts, blocked, governance)


def _policy_digest(facts: Mapping[str, object]) -> str:
    return edge_sha256_text(
        edge_canonical_json({**facts, "rule_set_digest": GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST})
    )


def _assemble_genesis(inputs: GovernedPaperGenesisInputs, proof: _GenesisProof) -> GovernedPaperGenesis:
    policy_digest = _policy_digest(proof.facts)
    approval = _canonical_approval(inputs.approval, GovernedPaperGenesisApproval, "genesis_approval")
    governance = list(proof.governance)
    governance.extend(
        _approval_reasons(
            approval,
            kind=GovernedPaperApprovalKind,
            expected={
                "approved_genesis_id": proof.facts["genesis_id"],
                "approved_genesis_version": proof.facts["genesis_version"],
                "approved_genesis_policy_digest": policy_digest,
                "approved_rule_set_digest": GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
            },
            prefix="genesis",
        )
    )
    if proof.blocked:
        status = GovernedPaperGenesisStatus.BLOCKED
    elif governance:
        status = GovernedPaperGenesisStatus.NEEDS_GOVERNANCE_APPROVAL
    else:
        status = GovernedPaperGenesisStatus.AUTHORIZED
    seed = GovernedPaperGenesis(
        schema_version=_GENESIS_SCHEMA_VERSION,
        status=status,
        authorized=status is GovernedPaperGenesisStatus.AUTHORIZED,
        **proof.facts,  # type: ignore[arg-type]
        genesis_policy_digest=policy_digest,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
        approval=approval,  # type: ignore[arg-type]
        synthetic_test_approval_used=approval is not None
        and approval.approval_kind is GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC,  # type: ignore[attr-defined]
        reason_codes=tuple(sorted(set(proof.blocked) | set(governance))),
        genesis_digest="",
    )
    return replace(seed, genesis_digest=edge_payload_digest(_to_payload(seed), _GENESIS_DIGEST_FIELD))


def build_governed_paper_genesis(inputs: GovernedPaperGenesisInputs) -> GovernedPaperGenesis:
    """Build one governed paper genesis from fully re-proven inputs (see the module docstring).

    Malformed input or any provenance defect raises ``GovernedPaperExecutionAuthorityError``. A structural shortfall
    is ``BLOCKED``; a missing, synthetic or non-matching approval is ``NEEDS_GOVERNANCE_APPROVAL``. Pure.
    """

    return _assemble_genesis(inputs, _genesis_proof(inputs))


def governed_paper_genesis_to_dict(genesis: GovernedPaperGenesis) -> dict[str, object]:
    return _to_payload(genesis)


def governed_paper_genesis_digest(genesis: GovernedPaperGenesis) -> str:
    return edge_payload_digest(_to_payload(genesis), _GENESIS_DIGEST_FIELD)


def verify_governed_paper_genesis(genesis: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a genesis by typed identity against its rebuild from ``inputs``. Total: never raises."""

    return governed_paper_verify_rebuilt(
        genesis,
        cls=GovernedPaperGenesis,
        domain=_GENESIS_DOMAIN,
        to_payload=_to_payload,
        digest_field=_GENESIS_DIGEST_FIELD,
        rebuild=lambda: build_governed_paper_genesis(inputs),  # type: ignore[arg-type]
        code="genesis",
        reason=_reason,
    )


def _verified_genesis(genesis: object, inputs: object) -> tuple[GovernedPaperGenesis, GovernedPaperGenesisAuthority]:
    proof = _genesis_proof(inputs)  # type: ignore[arg-type]
    rebuilt = _assemble_genesis(inputs, proof)  # type: ignore[arg-type]
    if (
        type(genesis) is not GovernedPaperGenesis
        or governed_paper_genesis_digest(genesis) != genesis.genesis_digest
        or not governed_paper_typed_identical(genesis, rebuilt, _GENESIS_DOMAIN)
    ):
        raise _fail("genesis_not_authentic")
    if rebuilt.status is not GovernedPaperGenesisStatus.AUTHORIZED or proof.authority is None:
        raise _fail("genesis_not_authorized")
    return rebuilt, replace(proof.authority, genesis=rebuilt)


def governed_paper_genesis_authority(genesis: object, inputs: object) -> GovernedPaperGenesisAuthority:
    """The canonical reconstructions of a verified AUTHORIZED genesis; raises otherwise."""

    return _verified_genesis(genesis, inputs)[1]


# --- the reservation chain (derived, never supplied) -----------------------------------------------------------------------


def _reservation_chain(
    authority: GovernedPaperGenesisAuthority, *, cycle_id: str, correlation_id: str, reservation_price: str
) -> tuple[tuple[PaperTradeTick, ...], PaperSleeveState, PaperSleeveRiskBudgetDecision, PaperAllocatorIntentDraft]:
    genesis = authority.genesis
    journal = EvidenceJournal()
    state = build_initial_paper_sleeve_state(sleeve_id=genesis.sleeve_id, correlation_id=correlation_id)
    ticks: list[PaperTradeTick] = []
    for action in (_LONG, _SHORT):
        tick = build_paper_trade_tick(
            tick_id=f"{cycle_id}-reserve-{action.lower()}",
            action=action,
            intent_type="MARKETABLE_LIMIT",
            instrument_id=genesis.instrument,
            quantity=genesis.unit_size,
            strategy_id=genesis.strategy_id,
            run_plan_id=cycle_id,
            upstream_report_digest=genesis.genesis_digest,
            correlation_id=correlation_id,
            limit_price=reservation_price,
        )
        entry = journal.append(
            EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id=correlation_id
        )
        state = apply_paper_trade_tick_to_sleeve_state(
            state, tick, correlation_id=correlation_id, journal_entry=entry
        ).to_state
        ticks.append(tick)
    decision = evaluate_paper_sleeve_risk_budget(state, authority.risk_budget_policy, correlation_id=correlation_id)
    decision_entry = journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_RISK_BUDGET_DECISION,
        paper_sleeve_risk_budget_decision_to_dict(decision),
        correlation_id=correlation_id,
    )
    candidate = build_paper_sleeve_promotion_candidate(decision_entry, decision, correlation_id=correlation_id)
    candidate_entry = journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_CANDIDATE,
        paper_sleeve_promotion_candidate_to_dict(candidate),
        correlation_id=correlation_id,
    )
    readiness = build_paper_sleeve_promotion_readiness(
        journal, candidate_entry, candidate, correlation_id=correlation_id
    )
    readiness_entry = journal.append(
        EvidenceArtifactType.PAPER_SLEEVE_PROMOTION_READINESS,
        paper_sleeve_promotion_readiness_to_dict(readiness),
        correlation_id=correlation_id,
    )
    draft = build_paper_allocator_intent_draft(journal, readiness_entry, readiness, correlation_id=correlation_id)
    return tuple(ticks), state, decision, draft


def _plan(
    authority: GovernedPaperGenesisAuthority, *, cycle_id: str, correlation_id: str, start: int, dataset: object
) -> tuple[str, GovernedPaperReservationPlan | None]:
    """The reservation of one cycle opening at ``start``: None when the engine's visible-mark rule has no quote."""

    genesis = authority.genesis
    if type(dataset) is not HistoricalPitDataset:
        raise _fail("reservation_dataset_malformed")
    dataset_digest = _verified_digest(dataset, verify_historical_pit_dataset, "reservation_dataset")
    if dataset.status is not EdgeEvidenceStatus.READY or dataset.advances is not True:
        raise _fail("reservation_dataset_not_ready")
    if (
        dataset.source_manifest_digest != genesis.source_manifest_digest
        or dataset.data_requirement_registry_digest != genesis.data_requirement_registry_digest
    ):
        raise _fail("reservation_dataset_foreign")
    mark = historical_execution_latest_visible_mark(
        dataset, policy=authority.economics_policy, instrument=genesis.instrument, at_ns=start
    )
    if mark is None:
        return dataset_digest, None
    quantized = historical_execution_quantize_price(Fraction(mark[1]) * (1 + Fraction(genesis.reservation_band)))
    if quantized is None:
        raise _fail("reservation_price_unrepresentable")
    ticks, state, decision, draft = _reservation_chain(
        authority, cycle_id=cycle_id, correlation_id=correlation_id, reservation_price=quantized[1]
    )
    return dataset_digest, GovernedPaperReservationPlan(
        reservation_mark_record_digest=mark[0],
        reservation_mark_price=mark[1],
        reservation_price=quantized[1],
        ticks=ticks,
        state=state,
        risk_budget_policy=authority.risk_budget_policy,
        risk_budget_decision=decision,
        allocator_draft=draft,
    )


def governed_paper_reservation_plan(
    genesis: object,
    genesis_inputs: object,
    *,
    cycle_id: str,
    correlation_id: str,
    day_index: int,
    reservation_dataset: object,
) -> GovernedPaperReservationPlan | None:
    """The reservation a cycle of a verified AUTHORIZED genesis derives at ``E_k`` (None without a visible quote).

    The same derivation the cycle performs; a caller builds RG-7 over exactly this plan. Raises on any defect.
    """

    authority = governed_paper_genesis_authority(genesis, genesis_inputs)
    _require_text(cycle_id, "cycle_id")
    _require_text(correlation_id, "cycle_correlation_id")
    if type(day_index) is not int or day_index < 0:
        raise _fail("day_index_invalid")
    start = authority.genesis.genesis_start_ns + day_index * _UTC_DAY_NS
    return _plan(authority, cycle_id=cycle_id, correlation_id=correlation_id, start=start, dataset=reservation_dataset)[
        1
    ]


# --- the RG-3 metrics context (derived, never supplied) ------------------------------------------------------------------


def _metrics_context(
    authority: GovernedPaperGenesisAuthority, episodes: tuple[PaperSleeveEpisodeEvidence, ...]
) -> GovernedPaperMetricsContext:
    """The section-7 chain over exactly ``episodes`` (a validated, non-empty sealed history) under the genesis C7.

    One session over every sealed episode in sealed order, anchored on the first one (the run that opened the period):
    its episode, run and correlation identity is the journal, governor, replay, readiness and summary identity, stable
    across the whole period. Every hop is an accepted public builder, so no metric is computed here, and a hop that
    does not reach its trusted state is a provenance defect.
    """

    policy = authority.metrics_governor_policy
    genesis_id = authority.genesis.genesis_id
    anchor = episodes[0].end_to_end_episode
    correlation = anchor.correlation_id
    ids = {"episode_id": anchor.episode_id, "run_id": anchor.run_id, "correlation_id": correlation}
    try:
        runs = tuple(item.episode_run for item in episodes)
        provenance = PaperSessionSequenceProvenance(
            session_sequence=build_paper_session_sequence(
                runs, paper_session_id=f"{genesis_id}-rg3-session", correlation_id=correlation
            ),
            episodes=runs,
        )
        rollups = tuple(
            PaperRealizedPnlRollupInput(
                event=item.realized_pnl_event,
                prior_state=item.prior_position_state,
                fill_result=item.fill_result,
                transition=item.position_transition,
                new_position_state=item.new_position_state,
            )
            for item in episodes
        )
        bridge = build_paper_session_realized_pnl_bridge(
            provenance, rollups, bridge_id=f"{genesis_id}-rg3-bridge", correlation_id=correlation
        )
        aggregate = build_paper_session_realized_pnl_aggregate(
            [PaperSessionRealizedPnlAggregateInput(bridge=bridge, session_input=provenance, rollup_entries=rollups)],
            aggregate_id=f"{genesis_id}-rg3-aggregate",
            correlation_id=correlation,
        )
        manifest = build_paper_session_realized_pnl_evidence_manifest(
            aggregate, expected_aggregate_digest=aggregate.aggregate_digest, correlation_id=correlation
        )
        if manifest.status is PaperSessionRealizedPnlEvidenceManifestStatus.INSUFFICIENT_EVIDENCE:
            return GovernedPaperMetricsContext(
                status=GovernedPaperMetricsContextStatus.NO_COMPUTED_REALIZED_EVENT,
                governor_policy_digest=policy.policy_digest,
                manifest_digest=manifest.manifest_digest,
                governor_decision=None,
                summary=None,
            )
        record = build_paper_evidence_admission_record(
            manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id=correlation
        )
        journal = EvidenceJournal()
        ledger = append_paper_admission_record_to_evidence_journal(
            journal,
            record,
            anchor,
            manifest,
            expected_admission_digest=record.admission_digest,
            expected_episode_digest=anchor.episode_digest,
            expected_prior_journal_head_digest=journal.head_digest,
            **ids,
        )
        # The decision and its deterministic replay: two independent derivations over the same ledger and policy.
        original = decide_paper_governor(ledger, policy, expected_ledger_bridge_digest=ledger.ledger_digest, **ids)
        replayed = decide_paper_governor(ledger, policy, expected_ledger_bridge_digest=ledger.ledger_digest, **ids)
        replay = verify_deterministic_paper_replay(
            original,
            replayed,
            expected_original_digest=original.decision_digest,
            expected_replay_digest=replayed.decision_digest,
            **ids,
        )
        readiness = decide_paper_stage4_readiness(
            replay,
            original,
            expected_replay_result_digest=replay.replay_result_digest,
            expected_governor_decision_digest=original.decision_digest,
            **ids,
        )
        summary = summarize_paper_session_metrics(
            aggregate,
            manifest,
            readiness,
            expected_session_aggregate_digest=aggregate.aggregate_digest,
            expected_evidence_manifest_digest=manifest.manifest_digest,
            expected_readiness_decision_digest=readiness.readiness_decision_digest,
            run_id=anchor.run_id,
            aggregate_id=aggregate.aggregate_id,
            correlation_id=correlation,
        )
    except Exception as exc:  # noqa: BLE001 - a sealed history the accepted chain refuses is a provenance defect
        raise _fail("metrics_context_not_derivable") from exc
    if (
        manifest.status is not PaperSessionRealizedPnlEvidenceManifestStatus.READY
        or record.status is not PaperEvidenceAdmissionStatus.ADMITTED
        or ledger.status is not PaperAdmissionLedgerBridgeStatus.READY
        or ledger.appended is not True
        or original.status is not PaperGovernorDecisionStatus.DECIDED
        or replay.status is not DeterministicPaperReplayHarnessStatus.MATCHED
        or readiness.status is not PaperStage4ReadinessStatus.DECIDED
        or summary.status is not PaperSessionMetricsSummaryStatus.READY
    ):
        raise _fail("metrics_context_not_derivable")
    candidate = PaperStage4ReadinessVerdict.PAPER_STAGE4_CANDIDATE.value
    if original.decision is PaperGovernorVerdict.ALLOW_PAPER:
        if summary.ready is not True or summary.readiness_verdict != candidate:
            raise _fail("metrics_context_not_derivable")
        status = GovernedPaperMetricsContextStatus.SAMPLE_ELIGIBLE
    elif original.decision is PaperGovernorVerdict.REVIEW_REQUIRED:
        status = GovernedPaperMetricsContextStatus.GOVERNOR_REVIEW_REQUIRED
    elif (
        original.decision is PaperGovernorVerdict.BLOCK_PAPER
        and tuple(original.reason_codes) == _BELOW_GOVERNOR_MINIMUM_REASONS
    ):
        status = GovernedPaperMetricsContextStatus.BELOW_GOVERNOR_MINIMUM
    else:
        status = GovernedPaperMetricsContextStatus.GOVERNOR_BLOCKED
    return GovernedPaperMetricsContext(
        status=status,
        governor_policy_digest=policy.policy_digest,
        manifest_digest=manifest.manifest_digest,
        governor_decision=original,
        summary=summary,
    )


def governed_paper_metrics_context(
    genesis: object, genesis_inputs: object, *, sealed_episodes: tuple[PaperSleeveEpisodeEvidence, ...]
) -> GovernedPaperMetricsContext:
    """The RG-3 metrics context a cycle of a verified AUTHORIZED genesis derives over ``sealed_episodes``.

    ``sealed_episodes`` is the whole, non-empty episode history sealed before the cycle opens. The same derivation the
    cycle performs: a caller builds RG-3 over exactly its ``series_summary``, or with no series when that is None.
    Raises on any defect.
    """

    authority = governed_paper_genesis_authority(genesis, genesis_inputs)
    if type(sealed_episodes) is not tuple or not sealed_episodes:
        raise _fail("metrics_context_needs_sealed_episodes")
    try:  # the exact typed episode schema the cycle's sealed-history digest images
        governed_paper_sealed_history_digest(
            sealed_episodes, (), (), strategy_spec_digest_anchor=authority.genesis.strategy_spec_digest
        )
    except Exception as exc:  # noqa: BLE001 - an episode outside the sealed-history schema is never history
        raise _fail("metrics_context_history_malformed") from exc
    return _metrics_context(authority, sealed_episodes)


def _is_the_derived_summary(supplied: object, expected: PaperSessionMetricsSummary | None) -> bool:
    if expected is None:
        return supplied is None
    try:
        return type(supplied) is PaperSessionMetricsSummary and governed_paper_typed_identical(
            supplied, expected, _METRICS_DOMAIN
        )
    except Exception:  # noqa: BLE001 - a value outside the summary schema is never the derived summary
        return False


# --- cycle ---------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _CycleProof:
    facts: dict[str, object]
    blocked: list[str]
    governance: list[str]
    reservation: GovernedPaperCycleReservation | None


_EMPTY_DIRECTION = {"status": "", "reserved": "", "final": "", "authorized": False}
# The RG-3 reasons a bootstrap phase pins for each derived metrics context; any other context never bootstraps.
_B1_PERFORMANCE_BY_CONTEXT = {
    GovernedPaperMetricsContextStatus.NO_COMPUTED_REALIZED_EVENT: _B1_UNMEASURED_PERFORMANCE_REASONS,
    GovernedPaperMetricsContextStatus.BELOW_GOVERNOR_MINIMUM: _B1_UNMEASURED_PERFORMANCE_REASONS,
    GovernedPaperMetricsContextStatus.SAMPLE_ELIGIBLE: _B1_PERFORMANCE_REASONS,
}
_METRICS_GOVERNOR_STOPS = (
    GovernedPaperMetricsContextStatus.GOVERNOR_REVIEW_REQUIRED,
    GovernedPaperMetricsContextStatus.GOVERNOR_BLOCKED,
)


def _direction(
    budget: PaperSleeveRiskBudgetDecision, records: tuple[object, ...], action: str, notional: Fraction
) -> dict[str, object]:
    """B2: one direction is authorized only by its own ELIGIBLE record and its own RG-7 final allocation."""

    own = [item for item in budget.record_decisions if item.action == action]
    if len(own) != 1:
        raise _fail(f"reservation_direction_record_missing:{action}")
    record = own[0]
    allocated = [
        item
        for item in records
        if item.sequence == record.sequence  # type: ignore[attr-defined]
        and item.record_decision_digest == record.record_decision_digest  # type: ignore[attr-defined]
    ]
    final = allocated[0].final_allocated_budget if len(allocated) == 1 else ""  # type: ignore[attr-defined]
    authorized = (
        record.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE
        and Fraction(record.requested_budget) == notional
        and Fraction(record.reserved_budget) == notional
        and len(allocated) == 1
        and allocated[0].risk_budget_record_status == PaperSleeveRiskBudgetRecordStatus.ELIGIBLE.value  # type: ignore[attr-defined]
        and type(allocated[0].risk_budget_record_status) is str  # type: ignore[attr-defined]
        and Fraction(final) == notional
    )
    return {"status": record.status.value, "reserved": record.reserved_budget, "final": final, "authorized": authorized}


def _expected_reasons(templates: tuple[str, ...], sleeve_id: str) -> tuple[str, ...]:
    return tuple(sorted(template.format(sleeve=sleeve_id) for template in templates))


def _sleeve_record(decision: PaperPortfolioAllocationDecision, sleeve_id: str) -> object | None:
    records = [item for item in decision.sleeves if item.sleeve_id == sleeve_id]
    return records[0] if len(records) == 1 else None


def _cycle_proof(inputs: GovernedPaperCycleInputs) -> _CycleProof:  # noqa: C901 - one linear re-proof
    if type(inputs) is not GovernedPaperCycleInputs:
        raise _fail("cycle_inputs_malformed")
    cycle_id = _require_text(inputs.cycle_id, "cycle_id")
    correlation_id = _require_text(inputs.correlation_id, "cycle_correlation_id")
    day = inputs.day_index
    if type(day) is not int or day < 0:
        raise _fail("day_index_invalid")
    authority = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
    genesis = authority.genesis
    start = genesis.genesis_start_ns + day * _UTC_DAY_NS
    end = start + _UTC_DAY_NS
    if not historical_execution_wire_int_is_valid(end, minimum=0):
        raise _fail("day_index_invalid")
    sleeve_id, instrument = genesis.sleeve_id, genesis.instrument
    blocked: list[str] = []
    governance: list[str] = []

    # The cumulative history sealed before E_k (its lineage is proven by the evidence, never here).
    episodes, closes, funding = inputs.sealed_episodes, inputs.sealed_day_closes, inputs.sealed_funding_events
    history_digest = governed_paper_sealed_history_digest(
        episodes, closes, funding, strategy_spec_digest_anchor=genesis.strategy_spec_digest
    )
    if len(closes) != day:
        raise _fail("sealed_history_not_through_previous_day")

    # The opening quote m(E_k) under the engine's own visible-mark rule, and the derived reservation.
    dataset_digest, plan = _plan(
        authority,
        cycle_id=cycle_id,
        correlation_id=correlation_id,
        start=start,
        dataset=inputs.reservation_dataset,
    )
    facts: dict[str, object] = {
        "cycle_id": cycle_id,
        "correlation_id": correlation_id,
        "genesis_id": genesis.genesis_id,
        "genesis_digest": genesis.genesis_digest,
        "sleeve_id": sleeve_id,
        "instrument": instrument,
        "day_index": day,
        "window_start_ns": start,
        "window_end_ns": end,
        "sealed_history_digest": history_digest,
        "sealed_episode_count": len(episodes),
        "sealed_day_count": len(closes),
        "sealed_funding_event_count": len(funding),
        "reservation_dataset_digest": dataset_digest,
        "reservation_mark_record_digest": "",
        "reservation_mark_price": "",
        "reservation_price": "",
        "unit_size": genesis.unit_size,
        "reservation_notional": "",
        "capacity_max_value": genesis.capacity_max_value,
        "reservation_state_digest": "",
        "reservation_decision_digest": "",
        "reservation_draft_digest": "",
    }
    unit = Fraction(genesis.unit_size)
    reservation: GovernedPaperCycleReservation | None = None
    budget: PaperSleeveRiskBudgetDecision | None = None
    notional = Fraction(0)
    if plan is None:
        blocked.append(_reason("reservation_mark_unavailable"))
    else:
        budget = plan.risk_budget_decision
        notional = unit * Fraction(plan.reservation_price)
        eligible = sum(
            1 for item in budget.record_decisions if item.status is PaperSleeveRiskBudgetRecordStatus.ELIGIBLE
        )
        capacity_policy = build_paper_capacity_gate_policy(
            policy_id=authority.risk_budget_policy.policy_id,
            sleeve_id=sleeve_id,
            max_notional=_plain(notional),
            max_units=_plain(unit),
            max_open_intents=max(eligible, 1),
        )
        facts.update(
            reservation_mark_record_digest=plan.reservation_mark_record_digest,
            reservation_mark_price=plan.reservation_mark_price,
            reservation_price=plan.reservation_price,
            reservation_notional=_scale18(notional, "reservation_notional"),
            reservation_state_digest=paper_sleeve_state_digest(plan.state),
            reservation_decision_digest=paper_sleeve_risk_budget_decision_digest(budget),
            reservation_draft_digest=plan.allocator_draft.draft_digest,
        )
        if plan.allocator_draft.status is not PaperAllocatorIntentDraftStatus.DRAFT_READY:
            blocked.append(_reason("reservation_draft_not_ready"))
        if genesis.capacity_max_value == "" or notional > Fraction(genesis.capacity_max_value):
            blocked.append(_reason("capacity_assumption_exceeded"))
        reservation = GovernedPaperCycleReservation(
            cycle=None,  # type: ignore[arg-type] - completed by the assembly
            plan=plan,
            capacity_policy=capacity_policy,
        )

    # RG-7 at E_k: re-proven by its public verifier; the subject must carry exactly the derived reservation.
    allocation, allocation_inputs = inputs.allocation_decision, inputs.allocation_inputs
    if (
        type(allocation) is not PaperPortfolioAllocationDecision
        or type(allocation_inputs) is not PaperPortfolioAllocationInputs
    ):
        raise _fail("allocation_malformed")
    verification = verify_paper_portfolio_allocation_decision(allocation, allocation_inputs)
    if not verification.intact or verification.recomputed_digest != allocation.allocation_decision_digest:
        raise _fail("allocation_not_authentic")
    if allocation.evaluation_end_ns != start or allocation_inputs.evaluation_end_ns != start:
        raise _fail("allocation_not_at_cycle_open")
    if allocation.envelope_digest != genesis.portfolio_risk_envelope_digest:
        raise _fail("allocation_not_on_the_genesis_envelope")
    subjects = [item for item in allocation_inputs.sleeves if item.sleeve_id == sleeve_id]
    record = _sleeve_record(allocation, sleeve_id)
    if len(subjects) != 1 or record is None:
        raise _fail("allocation_sleeve_missing")
    subject = subjects[0]
    if (
        record.paper_admission_decision_digest != genesis.paper_admission_digest  # type: ignore[attr-defined]
        or record.risk_budget_policy_digest != genesis.risk_budget_policy_digest  # type: ignore[attr-defined]
    ):
        raise _fail("allocation_subject_not_the_genesis")
    if budget is not None and (
        paper_sleeve_state_digest(subject.risk_budget_state) != facts["reservation_state_digest"]
        or paper_sleeve_risk_budget_decision_digest(subject.risk_budget_decision)
        != facts["reservation_decision_digest"]
        or record.risk_budget_state_digest != facts["reservation_state_digest"]  # type: ignore[attr-defined]
        or record.risk_budget_decision_digest != facts["reservation_decision_digest"]  # type: ignore[attr-defined]
    ):
        raise _fail("allocation_reservation_not_derived")
    head = subject.lifecycle_head_authority
    head_digest = paper_lifecycle_head_authority_digest(head)
    if head_digest != record.lifecycle_head_authority_digest:  # type: ignore[attr-defined]
        raise _fail("lifecycle_head_authority_mismatch")
    facts.update(
        lifecycle_head_digest=record.lifecycle_head_digest,  # type: ignore[attr-defined]
        lifecycle_head_authority_digest=head_digest,
        allocation_decision_digest=allocation.allocation_decision_digest,
        allocation_status=allocation.status.value,
    )
    if allocation.status is not PaperPortfolioAllocationStatus.READY:
        blocked.append(_reason(f"allocation_not_ready:{allocation.status.value}"))
    if (
        record.current_head_attested is not True  # type: ignore[attr-defined]
        or record.governed_lifecycle_state is not PaperGovernedLifecycleState.ACTIVE  # type: ignore[attr-defined]
        or record.kill_override_applied is not False  # type: ignore[attr-defined]
    ):
        blocked.append(_reason("lifecycle_head_not_active"))
    if (
        subject.lifecycle_head_authority_inputs.lifecycle_head.cycle_admission_decision_digest
        != genesis.paper_admission_digest
    ):
        blocked.append(_reason("lifecycle_head_cycle_not_the_genesis_admission"))

    # Per-direction authority (B2).
    directions = {"long": dict(_EMPTY_DIRECTION), "short": dict(_EMPTY_DIRECTION)}
    if budget is not None and len(budget.record_decisions) == 2:
        records = tuple(record.records)  # type: ignore[attr-defined]
        directions = {
            "long": _direction(budget, records, _LONG, notional),
            "short": _direction(budget, records, _SHORT, notional),
        }
        if blocked or allocation.status is not PaperPortfolioAllocationStatus.READY:
            for item in directions.values():
                item["authorized"] = False
    for name in ("long", "short"):
        item = directions[name]
        facts.update(
            {
                f"{name}_record_status": item["status"],
                f"{name}_reserved_budget": item["reserved"],
                f"{name}_final_allocated_budget": item["final"],
                f"{name}_authorized": item["authorized"],
            }
        )
    zero = _scale18(Fraction(0), "zero")
    unit_text = _scale18(unit, "unit_size")

    # RG-4 over [G, E_k) (none on day 0: that window is empty and RG-4 cannot be constructed), and RG-8 once episodes
    # exist: the bootstrap phase or the ordinary path (GAP-5).
    drawdown, drawdown_inputs = inputs.drawdown_evidence, inputs.drawdown_inputs
    if day == 0:
        if drawdown is not None or drawdown_inputs is not None:
            raise _fail("drawdown_supplied_for_an_empty_window")
    else:
        if type(drawdown) is not PaperSleeveDrawdownEvidence or type(drawdown_inputs) is not PaperSleeveDrawdownInputs:
            raise _fail("drawdown_malformed")
        verification = verify_paper_sleeve_drawdown_evidence(drawdown, drawdown_inputs)
        if not verification.intact or verification.recomputed_digest != drawdown.drawdown_evidence_digest:
            raise _fail("drawdown_not_authentic")
        if drawdown_inputs.window_start_ns != genesis.genesis_start_ns or drawdown_inputs.window_end_ns != start:
            raise _fail("drawdown_not_at_cycle_open")
        if (
            drawdown.envelope_digest != genesis.portfolio_risk_envelope_digest
            or drawdown.performance_path_policy_digest != genesis.performance_path_policy_digest
        ):
            raise _fail("drawdown_not_on_the_genesis_governance")
    facts.update(
        drawdown_evidence_digest="" if drawdown is None else drawdown.drawdown_evidence_digest,
        drawdown_status="" if drawdown is None else drawdown.status.value,
        governance_decision_digest="",
        governance_status="",
        performance_evidence_digest="",
        performance_status="",
        metrics_context_status="",
        metrics_summary_digest="",
        metrics_governor_decision_digest="",
        bootstrap_max_peak_distance="",
    )
    # The RG-3 metrics context of the sealed history (M2): derived under the genesis C7 policy, never supplied.
    context = _metrics_context(authority, episodes) if episodes else None
    if context is not None:
        decision = context.governor_decision
        facts.update(
            metrics_context_status=context.status.value,
            metrics_summary_digest="" if context.summary is None else context.summary.summary_digest,
            metrics_governor_decision_digest="" if decision is None else decision.decision_digest,
        )
        if context.status in _METRICS_GOVERNOR_STOPS:
            blocked.append(_reason(f"metrics_governor_stop:{context.status.value}"))
    phase = GovernedPaperCyclePhase.NOT_ESTABLISHED
    bootstrap = False
    governed, governed_inputs = inputs.governance_decision, inputs.governance_inputs
    if not episodes:
        if governed is not None or governed_inputs is not None:
            raise _fail("governance_supplied_before_any_episode")
        if drawdown is None or (
            drawdown.status is PaperSleeveDrawdownStatus.NOT_COMPUTABLE
            and tuple(sorted(drawdown.reason_codes)) == _expected_reasons(_B0_DRAWDOWN_REASONS, sleeve_id)
        ):
            phase, bootstrap = GovernedPaperCyclePhase.BOOTSTRAP_B0, True
        else:
            blocked.append(_reason("bootstrap_b0_conditions_unmet"))
    elif drawdown is None:
        raise _fail("episodes_sealed_before_the_first_day")
    elif (
        type(governed) is not PaperPortfolioGovernanceDecision
        or type(governed_inputs) is not PaperPortfolioGovernanceInputs
    ):
        blocked.append(_reason("portfolio_governance_missing"))
    else:
        verification = verify_paper_portfolio_governance_decision(governed, governed_inputs)
        if not verification.intact or verification.recomputed_digest != governed.governance_decision_digest:
            raise _fail("portfolio_governance_not_authentic")
        if (
            governed.evaluation_end_ns != start
            or governed.envelope_digest != genesis.portfolio_risk_envelope_digest
            or governed.allocation_decision_digest != allocation.allocation_decision_digest
            or governed.drawdown_evidence_digest != drawdown.drawdown_evidence_digest  # type: ignore[union-attr]
        ):
            raise _fail("portfolio_governance_not_this_cycle")
        sleeves = [
            item
            for item in governed_inputs.drawdown_inputs.sleeves
            if item.performance_inputs.valuation_inputs.equity_basis_policy.sleeve_id == sleeve_id
        ]
        ladders = [item for item in governed_inputs.sleeves if item.sleeve_id == sleeve_id]
        if len(sleeves) != 1 or len(ladders) != 1:
            raise _fail("portfolio_governance_sleeve_missing")
        performance = sleeves[0].performance_evidence
        valuation_inputs = sleeves[0].performance_inputs.valuation_inputs
        funding_evidence = valuation_inputs.funding_evidence
        if (
            valuation_inputs.window_start_ns != genesis.genesis_start_ns
            or valuation_inputs.window_end_ns != start
            or funding_evidence is None
            or governed_paper_sealed_history_digest(
                tuple(valuation_inputs.episodes),
                tuple(valuation_inputs.day_closes),
                tuple(funding_evidence.events),
                strategy_spec_digest_anchor=genesis.strategy_spec_digest,
            )
            != history_digest
        ):
            raise _fail("performance_history_not_the_sealed_history")
        # C5: RG-3 (hence every drawdown, ladder and bootstrap-stop index) is valued under exactly the genesis's basis
        # record: the genesis fact is that record's recomputed self-digest, which RG-3 carries as equity_basis_digest.
        if performance.equity_basis_digest != genesis.equity_basis_policy_digest:
            raise _fail("performance_not_on_the_genesis_basis")
        if context is None:
            raise _fail("performance_metrics_context_not_derived")
        # RG-3 carries a series only over a computed valuation, and there only the derived sample-eligible summary.
        valuation_computed = sleeves[0].performance_inputs.valuation.status is PaperSleeveValuationStatus.COMPUTED
        expected_summary = context.series_summary if valuation_computed else None
        if not _is_the_derived_summary(sleeves[0].performance_inputs.metrics_summary, expected_summary):
            raise _fail("performance_metrics_context_not_derived")
        pinned_performance = _B1_PERFORMANCE_BY_CONTEXT.get(context.status)
        ladder_state = ladders[0].ladder_decision_inputs.ladder_state
        facts.update(
            governance_decision_digest=governed.governance_decision_digest,
            governance_status=governed.status.value,
            performance_evidence_digest=performance.performance_evidence_digest,
            performance_status=performance.status.value,
        )
        if (
            type(ladder_state) is not PaperSleeveLadderSeed
            or paper_sleeve_ladder_seed_digest(ladder_state) != genesis.ladder_seed_digest
        ):
            blocked.append(_reason("ladder_state_not_the_genesis_seed"))
        terminal = [item for item in governed.sleeves if item.sleeve_id == sleeve_id]
        if (
            governed.status is PaperPortfolioGovernanceStatus.READY
            and performance.status is PaperSleevePerformanceStatus.READY
        ):
            if len(terminal) != 1 or Fraction(terminal[0].terminal_final_allocated_budget) != Fraction(
                record.final_allocated_budget  # type: ignore[attr-defined]
            ):
                blocked.append(_reason("terminal_allocation_not_the_allocation"))
            else:
                phase = GovernedPaperCyclePhase.ORDINARY
        elif (
            governed.status is PaperPortfolioGovernanceStatus.NOT_COMPUTABLE
            and governed.governance_reason_codes == ()
            and tuple(sorted(governed.reason_codes)) == _expected_reasons(_B1_GOVERNANCE_REASONS, sleeve_id)
            and drawdown.status is PaperSleeveDrawdownStatus.NOT_COMPUTABLE
            and tuple(sorted(drawdown.reason_codes)) == _expected_reasons(_B1_DRAWDOWN_REASONS, sleeve_id)
            and ladders[0].ladder_decision.status is PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
            and tuple(sorted(ladders[0].ladder_decision.reason_codes))
            == _expected_reasons(_B1_LADDER_REASONS, sleeve_id)
            and performance.status is PaperSleevePerformanceStatus.NOT_COMPUTABLE
            and pinned_performance is not None
            and tuple(sorted(performance.reason_codes)) == _expected_reasons(pinned_performance, sleeve_id)
        ):
            phase, bootstrap = GovernedPaperCyclePhase.BOOTSTRAP_B1, True
            days = sleeves[0].performance_inputs.valuation.days
            if not days:
                blocked.append(_reason("bootstrap_valuation_without_days"))
            else:
                path = (days[0].normalized_index_start, *(item.normalized_index_end for item in days))
                peak = measure_paper_peak_distance(path).max_peak_distance
                facts["bootstrap_max_peak_distance"] = peak
                breached = [
                    item.stop_level
                    for item in authority.portfolio_risk_envelope.portfolio_stop_levels
                    if Fraction(peak) > Fraction(item.max_portfolio_drawdown_fraction)
                ]
                if breached:
                    blocked.append(_reason(f"bootstrap_stop_triggered:{min(breached)}"))
        else:
            blocked.append(_reason(f"portfolio_governance_not_ready:{governed.status.value}"))
    if bootstrap:
        if start >= genesis.bootstrap_end_ns:
            blocked.append(_reason("bootstrap_expired"))
        for other in allocation.sleeves:
            if other.sleeve_id != sleeve_id and Fraction(other.post_kill_requested_budget) != 0:
                blocked.append(_reason(f"bootstrap_other_sleeve_reserved:{other.sleeve_id}"))
    authorized_count = sum(1 for item in directions.values() if item["authorized"] is True)
    if blocked:
        authorized_count = 0
        for name in ("long", "short"):
            facts[f"{name}_authorized"] = False
    facts.update(
        phase=phase,
        max_long_quantity=unit_text if facts["long_authorized"] is True else zero,
        max_short_quantity=unit_text if facts["short_authorized"] is True else zero,
        eligible_direction_count=authorized_count,
    )
    if not blocked and authorized_count == 0:
        blocked.append(_reason("no_direction_authorized"))
    return _CycleProof(facts, blocked, governance, reservation)


def _assemble_cycle(inputs: GovernedPaperCycleInputs, proof: _CycleProof) -> GovernedPaperCycleAuthority:
    committed = {name: (value.value if isinstance(value, Enum) else value) for name, value in proof.facts.items()}
    policy_digest = _policy_digest(committed)
    approval = _canonical_approval(inputs.approval, GovernedPaperCycleApproval, "cycle_approval")
    governance = list(proof.governance)
    governance.extend(
        _approval_reasons(
            approval,
            kind=GovernedPaperApprovalKind,
            expected={
                "approved_cycle_id": proof.facts["cycle_id"],
                "approved_cycle_policy_digest": policy_digest,
                "approved_rule_set_digest": GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
            },
            prefix="cycle",
        )
    )
    if proof.blocked:
        status = GovernedPaperCycleStatus.BLOCKED
    elif governance:
        status = GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL
    else:
        status = GovernedPaperCycleStatus.AUTHORIZED
    seed = GovernedPaperCycleAuthority(
        schema_version=_CYCLE_SCHEMA_VERSION,
        status=status,
        authorized=status is GovernedPaperCycleStatus.AUTHORIZED,
        **proof.facts,  # type: ignore[arg-type]
        cycle_policy_digest=policy_digest,
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
        approval=approval,  # type: ignore[arg-type]
        synthetic_test_approval_used=approval is not None
        and approval.approval_kind is GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC,  # type: ignore[attr-defined]
        reason_codes=tuple(sorted(set(proof.blocked) | set(governance))),
        cycle_digest="",
    )
    return replace(seed, cycle_digest=edge_payload_digest(_to_payload(seed), _CYCLE_DIGEST_FIELD))


def build_governed_paper_cycle_authority(inputs: GovernedPaperCycleInputs) -> GovernedPaperCycleAuthority:
    """Open one governed paper cycle from fully re-proven, ``E_k``-visible inputs (see the module docstring).

    Malformed input or any provenance defect raises ``GovernedPaperExecutionAuthorityError``. A governance or phase
    shortfall is ``BLOCKED``; a missing, synthetic or non-matching approval is ``NEEDS_GOVERNANCE_APPROVAL``. Pure.
    """

    return _assemble_cycle(inputs, _cycle_proof(inputs))


def governed_paper_cycle_authority_to_dict(cycle: GovernedPaperCycleAuthority) -> dict[str, object]:
    return _to_payload(cycle)


def governed_paper_cycle_authority_digest(cycle: GovernedPaperCycleAuthority) -> str:
    return edge_payload_digest(_to_payload(cycle), _CYCLE_DIGEST_FIELD)


def verify_governed_paper_cycle_authority(cycle: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a cycle by typed identity against its rebuild from ``inputs``. Total: never raises."""

    return governed_paper_verify_rebuilt(
        cycle,
        cls=GovernedPaperCycleAuthority,
        domain=_CYCLE_DOMAIN,
        to_payload=_to_payload,
        digest_field=_CYCLE_DIGEST_FIELD,
        rebuild=lambda: build_governed_paper_cycle_authority(inputs),  # type: ignore[arg-type]
        code="cycle",
        reason=_reason,
    )


def governed_paper_cycle_reservation(cycle: object, inputs: object) -> GovernedPaperCycleReservation:
    """The derived reservation chain of a verified AUTHORIZED cycle; raises unless ``cycle`` is its exact rebuild."""

    proof = _cycle_proof(inputs)  # type: ignore[arg-type]
    rebuilt = _assemble_cycle(inputs, proof)  # type: ignore[arg-type]
    if (
        type(cycle) is not GovernedPaperCycleAuthority
        or governed_paper_cycle_authority_digest(cycle) != cycle.cycle_digest
        or not governed_paper_typed_identical(cycle, rebuilt, _CYCLE_DOMAIN)
    ):
        raise _fail("cycle_not_authentic")
    if rebuilt.status is not GovernedPaperCycleStatus.AUTHORIZED or proof.reservation is None:
        raise _fail("cycle_not_authorized")
    return replace(proof.reservation, cycle=rebuilt)


def governed_paper_cycle_admission_window(
    cycle: GovernedPaperCycleAuthority,
) -> HistoricalExecutionAdmissionWindow | None:
    """The neutral engine window of an AUTHORIZED cycle (its per-direction ceilings and reservation price), else None."""

    if type(cycle) is not GovernedPaperCycleAuthority:
        raise _fail("cycle_malformed")
    if cycle.status is not GovernedPaperCycleStatus.AUTHORIZED:
        return None
    return HistoricalExecutionAdmissionWindow(
        window_start_ns=cycle.window_start_ns,
        window_end_ns=cycle.window_end_ns,
        max_long_quantity=cycle.max_long_quantity,
        max_short_quantity=cycle.max_short_quantity,
        reservation_price=cycle.reservation_price,
    )


__all__ = [
    "GOVERNED_PAPER_AUTHORITY_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET",
    "GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST",
    "GovernedPaperApprovalKind",
    "GovernedPaperCycleApproval",
    "GovernedPaperCycleAuthority",
    "GovernedPaperCycleInputs",
    "GovernedPaperCyclePhase",
    "GovernedPaperCycleReservation",
    "GovernedPaperCycleStatus",
    "GovernedPaperExecutionAuthorityError",
    "GovernedPaperGenesis",
    "GovernedPaperGenesisApproval",
    "GovernedPaperGenesisAuthority",
    "GovernedPaperGenesisInputs",
    "GovernedPaperGenesisStatus",
    "GovernedPaperMetricsContext",
    "GovernedPaperMetricsContextStatus",
    "GovernedPaperReservationPlan",
    "build_governed_paper_cycle_authority",
    "build_governed_paper_genesis",
    "governed_paper_cycle_admission_window",
    "governed_paper_cycle_authority_digest",
    "governed_paper_cycle_authority_to_dict",
    "governed_paper_cycle_reservation",
    "governed_paper_genesis_authority",
    "governed_paper_genesis_digest",
    "governed_paper_genesis_to_dict",
    "governed_paper_metrics_context",
    "governed_paper_reservation_plan",
    "governed_paper_sealed_history_digest",
    "verify_governed_paper_cycle_authority",
    "verify_governed_paper_genesis",
]
