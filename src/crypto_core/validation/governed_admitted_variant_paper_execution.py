"""Governed admitted-variant paper execution (GOVERNED_ADMITTED_VARIANT_PAPER_EXECUTION_V1).

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7, under the controller-adjudicated
architecture ``GPC_V1R``. This module owns the EXECUTION half of the contract: the causal paper-period decisions of one
EF-7 admitted variant, their governed historical execution economics, the sealed paper days and the evidence that binds
them to the prospective cycle authorities of ``governed_paper_execution_authority``. Paper-only, deterministic,
digest-bound and fail-closed; ``IMPLEMENTATION_SCOPE=SYNTHETIC_CONSTRUCTION_ONLY`` and real paper execution stays
BLOCKED.

The one economics source is ``historical_execution_economics``. Every day ``k`` is an authenticated PREFIX REPLAY from
the one immutable paper genesis ``G``: the archive as of ``E_(k+1)`` (``dataset_k``), the admitted variant's
``HistoricalDecisionRun`` over ``[G, E_(k+1))`` under its exact binding, assignment and parameter approval, the
``HistoricalExecutionEconomicsResult`` under the admission's own economics policy and approval, and
``simulate_historical_execution_governed_paper`` under the schedule ``S_k`` of every cycle window granted so far. No
state is injected and the engine is unchanged.

Sealing day ``k`` at ``E_(k+1)`` (``GovernedPaperDaySeal``):

* dataset causality: ``dataset_k`` has the genesis manifest, registry, source and rights, contains every record of the
  previous archive, adds only records visible in ``(E_k, E_(k+1)]`` and holds nothing visible after ``E_(k+1)``;
* the cycle authority ``A_k`` and its inputs are re-proven, and its opening archive is the previous archive. The
  previous seal must bind this genesis, day ``k - 1``, ``A_k``'s opening archive and ``A_k``'s sealed history;
* the closing human attestation ``H_(k+1)`` (an RG-7 ``PaperLifecycleHeadAuthority`` at ``E_(k+1)``) either names the
  paper genesis receipt again, or names its direct KILL_DISABLE successor taking effect inside ``[E_k, E_(k+1)]``. That
  successor invalidates the schedule from its effective instant. A successor taking effect before ``E_k`` contradicts the
  attestation that opened the cycle and RAISES: sealed history is never rewritten. Once invalidated, no later attestation
  may name the paper genesis receipt again. Closing evidence only VALIDATES or INVALIDATES; it never creates ex-ante
  authority, and the cycle ``k`` must open on exactly the attestation that closed day ``k - 1`` (one ``H_k``);
* the replay must reproduce the sealed prefix exactly: the content digest of every event strictly before ``E_k``
  (run-derived identifiers removed, the previous replay's pending intent excluded) must equal the previous seal's
  closing prefix digest, or it RAISES. An intent of the last decision that only the prefix end left open is PENDING and
  is resolved by a later replay (``GPC_PENDING_LINEAGE_V1``). The seal carries its deciding day, the digest of the cycle
  authority that decided it, and whether every cycle since that decision was AUTHORIZED. A pending fill executed in a
  later cycle needs a window in the executing cycle and is bounded by the reservation of the cycle that decided it. The
  next seal re-proves that deciding authority against the carried digest, using the previous cycle or, when it lies
  further back, the supplied deciding cycle. A missing intervening authority BLOCKS the day of the fill. The policy's
  ``max_execution_delay_ns`` bounds every pending interval, and a kill still invalidates the fill inside the economics;
* projection (``GPC_EXACT_GENERIC_PROJECTION_V1``): every governed fill executed in ``W_k`` becomes one generic paper
  episode built only through the accepted public builders: capacity (the deciding cycle's journaled draft and unit-
  notional capacity policy, one distinct decision per episode), a MARKET request for the filled side with
  ``requested_notional = |delta| * L`` of the deciding cycle (known when the intent was decided, never a fill price), the
  StrategySpec signal bridge, admission, intent, a pass-through fill (reference price = the engine's executed price,
  slippage ``0``, fee = the policy taker fee, available units = the engine's filled quantity, observed at the fill
  instant), position, PnL report, realized event and the end-to-end episode. The generic hard guards all stay active and
  the projection REQUIRES exact equality: price, quantity, status, gross notional, fee (``price * filled * bps / 10 000``,
  exact), the signed post-fill position and the realized gross PnL. The filled side must be a direction that its
  deciding cycle authorized (``GPC_PER_DIRECTION_AUTHORITY_V1``). Funding events carry the engine's settlement amount at
  the liability instant, bound to the projected position before it. Each amount must be exactly the engine's exact
  settlement ``-position * mark * rate`` (``GPC_EXACT_FUNDING_V1``), so RG-3 never accounts a rounded amount and its
  funding total is always the engine's own. The day close carries the engine's own mark at ``E_(k+1)``. Any other
  discrepancy RAISES; a same-side add never reaches the projection because the engine refuses it at decision time.

A day is BLOCKED when its economics cannot be computed (an unrepresentable value, a stale mark, incomplete funding, no
mark for the close). It is also BLOCKED when a funding settlement is not exactly representable at scale 18, when a fill
is on a direction its deciding cycle did not authorize, or when a pending fill lacks continuous cycle authority. A day
without a human closing attestation NEEDS_GOVERNANCE_APPROVAL. Neither is sealed, and nothing after it can open.

``GovernedPaperExecutionEvidence`` is the public reproof of one whole governed paper execution: it rebuilds every
supplied seal from its inputs in order and proves the lineage — day ``k``'s seal binds seal ``k - 1``, cycle ``k`` opens
on archive ``k - 1``, on exactly the generic history the seals ``0 .. k - 1`` projected, on the closing attestation of
day ``k - 1`` and on the RG-6 decision of cycle ``k - 1`` once that decision is READY. It then rebuilds the RG-3
performance of the whole sealed window through its public builder and records the bootstrap-to-ordinary transition.
A cycle or seal alone is never current authority; only this evidence proves a lineage.

Non-overclaim: synthetic paper construction only. No venue fill, machine time, current venue fact, edge, profitability,
readiness, execution permission, order or capital is proven or created. Exact ``Fraction`` arithmetic, no float, no
``decimal`` context, and no IO, clock, randomness, network or environment access.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction
from typing import cast

from crypto_core.strategy.spec import strategy_spec_digest
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EdgeKillQuarantineDecision,
    EdgeLifecycleTransition,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperCycleAuthority,
    GovernedPaperCycleInputs,
    GovernedPaperCyclePhase,
    GovernedPaperGenesis,
    GovernedPaperGenesisInputs,
    GovernedPaperGenesisStatus,
    governed_paper_cycle_admission_window,
    governed_paper_cycle_capacity,
    governed_paper_cycle_chain,
    governed_paper_sealed_history_digest,
    governed_paper_strategy_spec,
    verify_governed_paper_cycle_authority,
    verify_governed_paper_genesis,
)
from crypto_core.validation.historical_decision_run import build_historical_decision_run
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionFill,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionIntent,
    HistoricalExecutionSide,
    HistoricalExecutionValuationKind,
    build_historical_execution_economics,
    historical_execution_admission_schedule_digest,
    historical_execution_governed_paper_prefix_digest,
    historical_execution_latest_visible_mark,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, verify_historical_pit_dataset
from crypto_core.validation.paper_capacity_gate import PaperCapacityGateStatus, evaluate_paper_capacity_gate
from crypto_core.validation.paper_end_to_end_episode import (
    PaperEndToEndEpisodeStatus,
    build_paper_end_to_end_episode,
)
from crypto_core.validation.paper_episode_runner import PaperEpisodeRunStatus, run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    PaperFillSimulationStatus,
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentAdmissionStatus,
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import (
    PaperPnlReportStatus,
    build_paper_mark_snapshot,
    compute_paper_pnl_report,
    paper_mark_snapshot_digest,
    paper_pnl_report_digest,
)
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperLifecycleHeadAuthorityInputs,
    build_paper_lifecycle_head_authority,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    paper_position_state_digest,
)
from crypto_core.validation.paper_realized_pnl import PaperRealizedPnlStatus, compute_paper_realized_pnl_event
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDayCloseValuation,
    PaperSleeveEpisodeEvidence,
)
from crypto_core.validation.paper_sleeve_funding_evidence import PaperSleeveFundingEvent
from crypto_core.validation.paper_sleeve_performance_evidence import verify_paper_sleeve_performance_evidence
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderPriorDecision,
)
from crypto_core.validation.strategy_signal_to_paper_intent import (
    StrategySignalToPaperIntentStatus,
    build_strategy_signal_to_paper_intent,
)

_PREFIX = "governed_admitted_variant_paper_execution"
_SEAL_SCHEMA = "governed-paper-day-seal.v1"
_EVIDENCE_SCHEMA = "governed-paper-execution-evidence.v1"
_SCHEDULE_SCHEMA = "historical-execution-admission-schedule.v1"
_SEAL_DIGEST_FIELD = "seal_digest"
_EVIDENCE_DIGEST_FIELD = "evidence_digest"
_DAY_NS = 86_400_000_000_000
_MAX_WIRE_INT = 9_223_372_036_854_775_807
_MAX_IDENTIFIER = 64
_BPS = Fraction(10_000)

_RULE_SET_V1: dict[str, object] = {
    "rule_set_id": "governed_admitted_variant_paper_execution_rules.v1",
    "contract_id": "GOVERNED_ADMITTED_VARIANT_PAPER_EXECUTION_V1",
    "architecture_id": "GPC_V1R",
    "economics_source_rule_id": "historical_execution_economics_is_the_only_economics_source.v1",
    "replay_rule_id": "day_k_replays_genesis_to_closing_under_every_cycle_window_granted_so_far.v1",
    "dataset_rule_id": "archive_k_extends_archive_k_minus_1_with_records_visible_after_opening_through_closing.v1",
    "prefix_rule_id": "content_digest_before_opening_equals_the_previous_closing_prefix_or_raise.v1",
    "pending_rule_id": "last_decision_left_open_by_the_prefix_end_is_pending_never_final.v1",
    "cross_cycle_fill_rule_id": "a_pending_fill_keeps_its_reproven_deciding_cycle_through_authorized_cycles_only.v1",
    "direction_rule_id": "a_projected_fill_needs_its_side_authorized_by_its_deciding_cycle_else_blocked.v1",
    "closing_rule_id": "closing_attestation_names_the_genesis_or_its_direct_disable_inside_the_cycle.v1",
    "late_successor_rule_id": "a_successor_effective_before_the_opening_contradicts_sealed_history_and_raises.v1",
    "projection_rule_id": "GPC_EXACT_GENERIC_PROJECTION_V1_public_builders_hard_guards_active_exact_equality.v1",
    "requested_notional_rule_id": "requested_notional_is_delta_times_the_deciding_cycle_reservation_price.v1",
    "fill_policy_rule_id": "pass_through_reference_is_the_engine_price_slippage_zero_fee_taker_partial_allowed.v1",
    "fee_rule_id": "generic_fee_equals_price_times_filled_times_taker_bps_exactly_counted_once.v1",
    "funding_rule_id": "exactly_representable_engine_settlement_at_liability_bound_to_the_prior_position.v1",
    "close_rule_id": "engine_mark_at_the_bucket_end_position_strictly_before_it.v1",
    "lineage_rule_id": "every_seal_rebuilt_in_order_and_bound_to_its_predecessor_cycle_archive_and_history.v1",
    "ladder_lineage_rule_id": "the_next_cycle_continues_a_ready_rg6_decision_else_starts_from_the_seed.v1",
    "status_rule_id": "provenance_raises_then_blocked_then_needs_governance_approval_then_sealed.v1",
    "utc_day_ns": _DAY_NS,
}
GOVERNED_PAPER_EXECUTION_RULE_SET_DIGEST = edge_sha256_text(edge_canonical_json(_RULE_SET_V1))
_RULE_SET_ID = str(_RULE_SET_V1["rule_set_id"])


def governed_paper_execution_rule_set() -> dict[str, object]:
    """A fresh copy of the V1 rule set that ``GOVERNED_PAPER_EXECUTION_RULE_SET_DIGEST`` commits."""

    return json.loads(edge_canonical_json(_RULE_SET_V1))


class GovernedPaperExecutionError(EdgeArtifactError):
    """Malformed input or a provenance, causality or projection defect: an invalid seal is never represented."""


class GovernedPaperDaySealStatus(str, Enum):
    """SEALED only when the day's governed economics are computed, prefix-preserving, attested and exactly projected."""

    SEALED = "SEALED"
    BLOCKED = "BLOCKED"
    NEEDS_GOVERNANCE_APPROVAL = "NEEDS_GOVERNANCE_APPROVAL"


class GovernedPaperExecutionStatus(str, Enum):
    """READY: every supplied day is sealed and its lineage re-proven; BLOCKED: the lineage stops at an unsealed day."""

    READY = "READY"
    BLOCKED = "BLOCKED"


GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("synthetic_construction_only", True),
    ("real_paper_execution_authorized", False),
    ("execution_authorized", False),
    ("capital_allocated", False),
    ("real_capital_reserved", False),
    ("real_orders_enabled", False),
    ("real_money_enabled", False),
    ("venue_orders_created", False),
    ("venue_fill_truth_proven", False),
    ("machine_time_proven", False),
    ("venue_facts_current_proven", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("deribit_ready", False),
    ("live_api_called", False),
    ("connector_invoked", False),
    ("scheduler_enabled", False),
    ("auto_loop_enabled", False),
    ("global_current_lifecycle_head_proven", False),
    ("edge_proven", False),
    ("profitability_proven", False),
    ("prdv4_stage4_complete", False),
)


@dataclass(frozen=True)
class GovernedPaperDaySeal:
    """The digest-bound retrospective seal of one governed paper day. History only; never current authority."""

    schema_version: str
    status: GovernedPaperDaySealStatus
    sealed: bool
    seal_id: str
    correlation_id: str
    genesis_digest: str
    day_index: int
    opening_ns: int
    closing_ns: int
    cycle_authority_digest: str
    cycle_status: str
    cycle_phase: str
    prior_seal_digest: str
    prior_cycle_authority_digest: str
    opening_dataset_digest: str
    dataset_digest: str
    dataset_record_count: int
    new_record_count: int
    run_digest: str
    economics_result_digest: str
    economics_gate_verdict: str
    schedule_windows: tuple[HistoricalExecutionAdmissionWindow, ...]
    invalidated_from_ns: int | None
    schedule_digest: str
    governed_outcome_digest: str
    governed_outcome_simulated: bool
    opening_prefix_digest: str
    closing_prefix_digest: str
    pending_decision_sequence: int | None
    pending_deciding_day_index: int | None
    pending_deciding_cycle_authority_digest: str
    pending_cycle_authority_continuous: bool
    closing_head_authority_digest: str
    closing_lifecycle_head_digest: str
    successor_effective_at_ns: int | None
    governance_rejected_fill_count: int
    episode_digests: tuple[str, ...]
    day_close_mark_digest: str
    day_close_report_digest: str
    funding_event_count: int
    projection_digest: str
    cumulative_history_digest: str
    cumulative_episode_count: int
    closing_position_state_digest: str
    reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    seal_digest: str
    paper_only: bool = True
    synthetic_construction_only: bool = True
    real_paper_execution_authorized: bool = False
    execution_authorized: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    venue_orders_created: bool = False
    venue_fill_truth_proven: bool = False
    machine_time_proven: bool = False
    venue_facts_current_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    global_current_lifecycle_head_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    prdv4_stage4_complete: bool = False


@dataclass(frozen=True)
class GovernedPaperDaySealInputs:
    """Everything one seal consumes: the day's cycle, the previous cycle and seal, the archive and the closing head.

    The pending cycle is supplied exactly when the previous seal carries a pending intent decided before the previous
    cycle: it is that intent's deciding cycle, re-proven against the digest the previous seal carries.
    """

    seal_id: str
    correlation_id: str
    cycle_inputs: GovernedPaperCycleInputs
    cycle_authority: GovernedPaperCycleAuthority
    prior_cycle_inputs: GovernedPaperCycleInputs | None
    prior_cycle_authority: GovernedPaperCycleAuthority | None
    prior_seal: GovernedPaperDaySeal | None
    dataset: HistoricalPitDataset
    closing_head_authority_inputs: PaperLifecycleHeadAuthorityInputs
    pending_cycle_inputs: GovernedPaperCycleInputs | None = None
    pending_cycle_authority: GovernedPaperCycleAuthority | None = None


@dataclass(frozen=True)
class GovernedPaperDayProjection:
    """The generic RG-3 records one sealed day projects: its episodes, its day close and its funding events."""

    episodes: tuple[PaperSleeveEpisodeEvidence, ...]
    day_close: PaperSleeveDayCloseValuation
    funding_events: tuple[PaperSleeveFundingEvent, ...]


@dataclass(frozen=True)
class GovernedPaperDay:
    """One day's seal with the projection and governed outcome it was derived with (``None`` unless sealed)."""

    seal: GovernedPaperDaySeal
    projection: GovernedPaperDayProjection | None
    outcome: HistoricalExecutionGovernedPaperOutcome | None


@dataclass(frozen=True)
class GovernedPaperExecutionInputs:
    """One whole governed paper execution: the genesis and every day's seal inputs and seal, in order."""

    evidence_id: str
    correlation_id: str
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    days: tuple[GovernedPaperDaySealInputs, ...]
    seals: tuple[GovernedPaperDaySeal, ...]


@dataclass(frozen=True)
class GovernedPaperExecutionEvidence:
    """The digest-bound public reproof of one governed paper execution lineage. Synthetic paper evidence only."""

    schema_version: str
    status: GovernedPaperExecutionStatus
    ready: bool
    evidence_id: str
    correlation_id: str
    genesis_digest: str
    sleeve_id: str
    instrument: str
    genesis_ns: int
    day_count: int
    sealed_day_count: int
    seal_digests: tuple[str, ...]
    cycle_authority_digests: tuple[str, ...]
    cycle_phases: tuple[str, ...]
    authorized_cycle_count: int
    bootstrap_b0_cycle_count: int
    bootstrap_b1_cycle_count: int
    ordinary_cycle_count: int
    first_b1_day_index: int | None
    first_ordinary_day_index: int | None
    invalidated_from_ns: int | None
    episode_count: int
    cumulative_history_digest: str
    performance_window_end_ns: int
    performance_evidence_digest: str
    performance_status: str
    performance_daily_return_count: int
    paper_sharpe_annualized: str
    reason_codes: tuple[str, ...]
    rule_set_id: str
    rule_set_digest: str
    evidence_digest: str
    paper_only: bool = True
    synthetic_construction_only: bool = True
    real_paper_execution_authorized: bool = False
    execution_authorized: bool = False
    capital_allocated: bool = False
    real_capital_reserved: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    venue_orders_created: bool = False
    venue_fill_truth_proven: bool = False
    machine_time_proven: bool = False
    venue_facts_current_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    deribit_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    global_current_lifecycle_head_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    prdv4_stage4_complete: bool = False


# --- helpers ----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperExecutionError:
    return GovernedPaperExecutionError(_reason(code))


def _require_identifier(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > _MAX_IDENTIFIER
        or not all(char.isascii() and (char.isalnum() or char in "-_.:") for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_exact(value: object, cls: type, field_name: str) -> None:
    if type(value) is not cls:
        raise _fail(f"{field_name}_malformed")


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
    """Exact plain decimal text of a terminating value; never rounded."""

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


def _visibility(record: object) -> int:
    finalized = record.finalized_at_ns  # type: ignore[attr-defined]
    available = record.available_at_ns  # type: ignore[attr-defined]
    return available if finalized is None else max(available, finalized)


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


def governed_paper_day_seal_digest(seal: GovernedPaperDaySeal) -> str:
    """Recompute the canonical seal digest, excluding only ``seal_digest``."""

    return edge_payload_digest(_to_payload(seal), _SEAL_DIGEST_FIELD)


def governed_paper_day_seal_to_dict(seal: GovernedPaperDaySeal) -> dict[str, object]:
    """Canonical JSON-ready mapping of a seal, including its self-digest."""

    return _to_payload(seal)


# --- the day ------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Context:
    """The re-proven facts one seal works from."""

    inputs: GovernedPaperDaySealInputs
    gi: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    authority: GovernedPaperCycleAuthority
    seal_id: str
    correlation_id: str
    day_index: int
    opening_ns: int
    closing_ns: int
    prior_windows: tuple[HistoricalExecutionAdmissionWindow, ...]
    prior_invalidated_from_ns: int | None
    pending_authority: GovernedPaperCycleAuthority | None


def _require_cycle(
    inputs: object, authority: object, code: str
) -> tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority]:
    _require_exact(inputs, GovernedPaperCycleInputs, f"{code}_inputs")
    _require_exact(authority, GovernedPaperCycleAuthority, f"{code}_authority")
    if not verify_governed_paper_cycle_authority(authority, inputs).intact:
        raise _fail(f"{code}_authority_not_authentic")
    return cast(GovernedPaperCycleInputs, inputs), cast(GovernedPaperCycleAuthority, authority)


def _context(inputs: object) -> _Context:
    _require_exact(inputs, GovernedPaperDaySealInputs, "seal_inputs")
    si = cast(GovernedPaperDaySealInputs, inputs)
    seal_id = _require_identifier(si.seal_id, "seal_id")
    correlation_id = _require_identifier(si.correlation_id, "correlation_id")
    cycle_inputs, authority = _require_cycle(si.cycle_inputs, si.cycle_authority, "cycle")
    gi, genesis = cycle_inputs.genesis_inputs, cycle_inputs.genesis
    if not verify_governed_paper_genesis(genesis, gi).intact:
        raise _fail("genesis_not_authentic")
    if genesis.status is not GovernedPaperGenesisStatus.READY:
        raise _fail("genesis_not_ready")
    day_index = authority.day_index
    _require_exact(si.dataset, HistoricalPitDataset, "dataset")
    _require_exact(si.closing_head_authority_inputs, PaperLifecycleHeadAuthorityInputs, "closing_head_authority_inputs")
    prior_windows: tuple[HistoricalExecutionAdmissionWindow, ...] = ()
    prior_invalidated: int | None = None
    pending_authority: GovernedPaperCycleAuthority | None = None
    pending_required = False
    if day_index == 0:
        if si.prior_seal is not None or si.prior_cycle_inputs is not None or si.prior_cycle_authority is not None:
            raise _fail("genesis_day_has_no_predecessor")
        if cycle_inputs.sealed_episodes or cycle_inputs.sealed_day_closes or cycle_inputs.sealed_funding_events:
            raise _fail("genesis_day_has_no_sealed_history")
    else:
        prior_inputs, prior_authority = _require_cycle(si.prior_cycle_inputs, si.prior_cycle_authority, "prior_cycle")
        prior = si.prior_seal
        _require_exact(prior, GovernedPaperDaySeal, "prior_seal")
        prior = cast(GovernedPaperDaySeal, prior)
        if governed_paper_day_seal_digest(prior) != prior.seal_digest or prior.sealed is not True:
            raise _fail("prior_seal_not_intact")
        if (
            prior.genesis_digest != genesis.genesis_digest
            or prior.day_index != day_index - 1
            or prior_authority.day_index != day_index - 1
            or prior_authority.genesis_digest != genesis.genesis_digest
            or prior.cycle_authority_digest != prior_authority.authority_digest
        ):
            raise _fail("prior_seal_not_the_previous_day")
        if prior.dataset_digest != authority.opening_dataset_digest:
            raise _fail("cycle_not_opened_on_the_previous_archive")
        if prior.cumulative_history_digest != authority.sealed_history_digest:
            raise _fail("cycle_not_opened_on_the_sealed_history")
        if prior.closing_head_authority_digest != authority.head_authority_digest:
            raise _fail("cycle_not_opened_on_the_closing_attestation")
        if prior_inputs.genesis.genesis_digest != genesis.genesis_digest:
            raise _fail("prior_cycle_of_another_genesis")
        prior_windows, prior_invalidated = prior.schedule_windows, prior.invalidated_from_ns
        deciding_day = prior.pending_deciding_day_index
        pending_required = deciding_day is not None and deciding_day < day_index - 1
        if pending_required:
            pending_inputs, pending_authority = _require_cycle(
                si.pending_cycle_inputs, si.pending_cycle_authority, "pending_cycle"
            )
            if (
                pending_authority.authority_digest != prior.pending_deciding_cycle_authority_digest
                or pending_authority.day_index != deciding_day
                or pending_authority.genesis_digest != genesis.genesis_digest
                or pending_inputs.genesis.genesis_digest != genesis.genesis_digest
            ):
                raise _fail("pending_cycle_not_the_deciding_cycle_of_the_pending_intent")
    if not pending_required and (si.pending_cycle_inputs is not None or si.pending_cycle_authority is not None):
        raise _fail("pending_cycle_not_required")
    opening = genesis.genesis_ns + day_index * _DAY_NS
    return _Context(
        inputs=si,
        gi=gi,
        genesis=genesis,
        authority=authority,
        seal_id=seal_id,
        correlation_id=correlation_id,
        day_index=day_index,
        opening_ns=opening,
        closing_ns=opening + _DAY_NS,
        prior_windows=prior_windows,
        prior_invalidated_from_ns=prior_invalidated,
        pending_authority=pending_authority,
    )


def _check_dataset(ctx: _Context) -> tuple[HistoricalPitDataset, int]:
    """Archive causality: authenticated, the genesis identity, a superset of the opening archive, nothing late or early."""

    dataset, opening = ctx.inputs.dataset, ctx.inputs.cycle_inputs.opening_dataset
    if not verify_historical_pit_dataset(dataset).intact or dataset.advances is not True:
        raise _fail("dataset_not_authentic")
    if (
        dataset.source_manifest_digest != opening.source_manifest_digest
        or dataset.data_requirement_registry_digest != opening.data_requirement_registry_digest
        or (dataset.source_reference, dataset.rights_status, dataset.rights_reference)
        != (opening.source_reference, opening.rights_status, opening.rights_reference)
    ):
        raise _fail("dataset_not_of_the_archive")
    previous = set(opening.record_digests)
    current = set(dataset.record_digests)
    if not previous <= current:
        raise _fail("dataset_drops_a_sealed_record")
    new_count = 0
    for record in dataset.records:
        visible = _visibility(record)
        if visible > ctx.closing_ns:
            raise _fail("dataset_record_visible_after_closing")
        if record.record_digest not in previous:
            new_count += 1
            if visible <= ctx.opening_ns:
                raise _fail("dataset_record_backfilled_before_opening")
    return dataset, new_count


def _closing_head(ctx: _Context) -> tuple[str, str, int | None, int | None, list[str]]:
    """``(authority digest, head digest, successor instant, invalidated from, governance reasons)`` of ``H_(k+1)``."""

    head_inputs = ctx.inputs.closing_head_authority_inputs
    authority = build_paper_lifecycle_head_authority(head_inputs)
    if authority.evaluation_end_ns != ctx.closing_ns or authority.sleeve_id != ctx.genesis.sleeve_id:
        raise _fail("closing_head_not_at_the_closing_instant")
    governance: list[str] = []
    if authority.paper_current_head_attested is not True:
        governance.append(_reason("closing_head_not_attested"))
    head: EdgeKillQuarantineDecision = head_inputs.lifecycle_head
    invalidated = ctx.prior_invalidated_from_ns
    successor: int | None = None
    if invalidated is not None and head.kill_quarantine_decision_digest == ctx.genesis.lifecycle_genesis_digest:
        raise _fail("closing_head_contradicts_the_invalidation")
    if invalidated is None and head.kill_quarantine_decision_digest != ctx.genesis.lifecycle_genesis_digest:
        if (
            head.transition is not EdgeLifecycleTransition.KILL_DISABLE
            or head.prior_digest != ctx.genesis.lifecycle_genesis_digest
        ):
            raise _fail("closing_head_not_a_direct_successor_of_the_paper_genesis")
        if head.effective_at_ns < ctx.opening_ns:
            raise _fail("late_successor_contradicts_sealed_history")
        if head.effective_at_ns > ctx.closing_ns:
            raise _fail("closing_head_effective_after_closing")
        successor = invalidated = head.effective_at_ns
    return authority.authority_digest, head.kill_quarantine_decision_digest, successor, invalidated, governance


def _schedule(ctx: _Context, invalidated: int | None) -> HistoricalExecutionAdmissionSchedule:
    window = governed_paper_cycle_admission_window(ctx.authority)
    windows = ctx.prior_windows if window is None else (*ctx.prior_windows, window)
    return HistoricalExecutionAdmissionSchedule(
        schema_version=_SCHEDULE_SCHEMA,
        schedule_id=f"{ctx.seal_id}:schedule",
        windows=windows,
        invalidated_from_ns=invalidated,
    )


def _economics(ctx: _Context, dataset: HistoricalPitDataset) -> HistoricalExecutionEconomicsResult:
    gi = ctx.gi
    run = build_historical_decision_run(
        dataset,
        gi.executable_binding,
        expected_dataset_digest=dataset.dataset_digest,
        expected_executable_binding_digest=gi.executable_binding.binding_digest,
        run_id=f"{ctx.seal_id}:run",
        correlation_id=gi.executable_binding.correlation_id,
        parameter_assignment=gi.parameter_assignment,
        instrument=ctx.genesis.instrument,
        evaluation_start_ns=ctx.genesis.genesis_ns,
        evaluation_end_ns=ctx.closing_ns,
        parameter_approval=gi.parameter_approval,
    )
    if run.status is not EdgeEvidenceStatus.READY or run.gate_verdict is not EdgeGateVerdict.PASS:
        raise _fail("paper_decision_run_not_ready")
    return build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=gi.economics_policy,
        expected_economics_policy_digest=gi.economics_policy.policy_digest,
        economics_approval=gi.economics_approval,
        result_id=f"{ctx.seal_id}:economics",
        correlation_id=gi.executable_binding.correlation_id,
    )


# --- the exact generic projection -----------------------------------------------------------------------------------


class _Unsealable(Exception):
    """Internal: a data-driven reason the day cannot be sealed; never escapes the module."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class _Lineage:
    """One deciding cycle's reservation price, journaled draft, capacity policy and authorized directions."""

    reservation_price: Fraction
    allocator_draft: object
    capacity_policy: object
    buy_authorized: bool
    sell_authorized: bool


def _genesis_position(genesis: GovernedPaperGenesis) -> PaperPositionState:
    return build_flat_paper_position_state(
        position_state_id=f"{genesis.genesis_id}-pos-genesis",
        market_symbol=genesis.instrument,
        correlation_id=f"{genesis.genesis_id}-corr-pos-genesis",
    )


def _deciding_cycle(ctx: _Context, intent: HistoricalExecutionIntent, cache: dict[int, _Lineage]) -> _Lineage:
    """The cycle that decided a projected fill: this cycle, or the re-proven cycle of the carried pending intent."""

    day = (intent.decision_time_ns - ctx.genesis.genesis_ns) // _DAY_NS
    if day not in cache:
        if day == ctx.day_index:
            authority: GovernedPaperCycleAuthority | None = ctx.authority
        else:
            prior = ctx.inputs.prior_seal
            if (
                prior is None
                or day > ctx.day_index
                or prior.pending_decision_sequence != intent.decision_sequence
                or prior.pending_deciding_day_index != day
            ):
                raise _fail("projected_fill_not_the_carried_pending_intent")
            if prior.pending_cycle_authority_continuous is not True:
                raise _Unsealable("pending_fill_without_continuous_cycle_authority")
            authority = ctx.inputs.prior_cycle_authority if day == ctx.day_index - 1 else ctx.pending_authority
            if authority is None or authority.authority_digest != prior.pending_deciding_cycle_authority_digest:
                raise _fail("projected_fill_not_the_carried_pending_intent")
        if authority.authorized is not True:
            raise _fail("projected_fill_without_its_deciding_cycle_window")
        draft, policy = governed_paper_cycle_capacity(ctx.gi, ctx.genesis, authority)
        cache[day] = _Lineage(
            Fraction(authority.reservation_price),
            draft,
            policy,
            authority.long_direction_authorized,
            authority.short_direction_authorized,
        )
    return cache[day]


def _pending_lineage(ctx: _Context, outcome: HistoricalExecutionGovernedPaperOutcome) -> tuple[int | None, str, bool]:
    """``(deciding day, deciding cycle authority digest, every later cycle AUTHORIZED)`` of the replay's pending intent."""

    if outcome.pending_decision_sequence is None:
        return None, "", False
    intents = [item for item in outcome.intents if item.intent_digest == outcome.pending_intent_digest]
    if len(intents) != 1:
        raise _fail("pending_intent_not_in_the_replay")
    day = (intents[0].decision_time_ns - ctx.genesis.genesis_ns) // _DAY_NS
    if day == ctx.day_index:
        return day, ctx.authority.authority_digest, True
    prior = ctx.inputs.prior_seal
    if prior is None or (prior.pending_decision_sequence, prior.pending_deciding_day_index) != (
        outcome.pending_decision_sequence,
        day,
    ):
        raise _fail("pending_intent_not_carried_from_the_prior_seal")
    continuous = prior.pending_cycle_authority_continuous is True and ctx.authority.authorized is True
    return day, prior.pending_deciding_cycle_authority_digest, continuous


def _renders_as(exact: Fraction, rendered: str) -> bool:
    return historical_execution_render_amount(exact) == rendered


def _episode(
    ctx: _Context,
    spec: object,
    dataset: HistoricalPitDataset,
    intent: HistoricalExecutionIntent,
    fill: HistoricalExecutionFill,
    transition: object,
    fee: object,
    prior: PaperPositionState,
    lineage: _Lineage,
) -> PaperSleeveEpisodeEvidence:
    """One governed fill as one generic paper episode; every value must equal the engine's exactly."""

    genesis, gi = ctx.genesis, ctx.gi
    gid, seq, market = genesis.genesis_id, intent.decision_sequence, genesis.instrument
    requested_notional = _plain(Fraction(intent.requested_quantity) * lineage.reservation_price)
    decision = evaluate_paper_capacity_gate(
        lineage.allocator_draft,  # type: ignore[arg-type]
        lineage.capacity_policy,  # type: ignore[arg-type]
        requested_notional=requested_notional,
        requested_units=intent.requested_quantity,
        correlation_id=f"{gid}-capacity-{seq}",
    )
    if decision.status is not PaperCapacityGateStatus.ADMITTED:
        raise _fail("projection_capacity_not_admitted")
    side = PaperOrderSide.BUY if intent.side is HistoricalExecutionSide.BUY else PaperOrderSide.SELL
    request_id, request_correlation = f"{gid}-req-{seq}", f"{gid}-corr-req-{seq}"
    request = build_paper_order_intent_request(
        request_id=request_id,
        capacity_decision_digest=decision.decision_digest,
        market_symbol=market,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=requested_notional,
        requested_units=intent.requested_quantity,
        limit_price=None,
        correlation_id=request_correlation,
    )
    bridge = build_strategy_signal_to_paper_intent(
        spec,  # type: ignore[arg-type]
        expected_spec_digest=strategy_spec_digest(spec),  # type: ignore[arg-type]
        signal_id=request_id,
        run_id=f"{gid}-run-{seq}",
        correlation_id=request_correlation,
        market_symbol=market,
        side=side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units=intent.requested_quantity,
        requested_notional=requested_notional,
        capacity_decision_digest=decision.decision_digest,
        limit_price=None,
    )
    if bridge.status is not StrategySignalToPaperIntentStatus.READY:
        raise _fail("projection_signal_bridge_not_ready")
    admission = evaluate_paper_order_intent_admission(decision, request, correlation_id=f"{gid}-corr-admit-{seq}")
    if admission.status is not PaperOrderIntentAdmissionStatus.ADMITTED:
        raise _fail("projection_admission_not_admitted")
    order_intent = build_paper_order_intent(
        admission, intent_id=f"{gid}-intent-{seq}", correlation_id=f"{gid}-corr-intent-{seq}"
    )
    instant = cast(int, fill.execution_time_ns)
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"{gid}-snap-{seq}",
        market_symbol=market,
        reference_price=cast(str, fill.fill_price),
        available_units=fill.filled_quantity,
        observed_at_ns=instant,
    )
    fill_policy = build_paper_fill_policy(
        policy_id=f"{gid}-fill-policy",
        slippage_bps="0",
        fee_rate_bps=gi.economics_policy.taker_fee_bps,
        allow_partial_fill=True,
    )
    mark_view = historical_execution_latest_visible_mark(
        dataset, policy=gi.economics_policy, instrument=market, at_ns=instant
    )
    if mark_view is None:
        raise _Unsealable("projection_fill_mark_unavailable")
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"{gid}-mark-{seq}",
        market_symbol=market,
        mark_price=mark_view[1],
        observed_at_ns=instant,
        correlation_id=f"{gid}-corr-mark-{seq}",
    )
    run_correlation = f"{gid}-corr-run-{seq}"
    ids = {
        "fill_simulation_id": f"{gid}-fill-{seq}",
        "position_transition_id": f"{gid}-trans-{seq}",
        "new_position_state_id": f"{gid}-pos-{seq}",
        "pnl_report_id": f"{gid}-pnl-{seq}",
    }
    run = run_paper_episode(
        order_intent,
        prior,
        snapshot,
        fill_policy,
        mark,
        **ids,
        episode_run_id=f"{gid}-episode-run-{seq}",
        correlation_id=run_correlation,
    )
    generic_fill = simulate_paper_fill(
        order_intent,
        snapshot,
        fill_policy,
        fill_simulation_id=ids["fill_simulation_id"],
        correlation_id=run_correlation,
    )
    generic_transition, new_state = apply_paper_fill_to_position(
        prior,
        generic_fill,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=run_correlation,
    )
    if run.status is not PaperEpisodeRunStatus.COMPUTED or new_state is None:
        raise _fail("projection_episode_not_computed")
    report = compute_paper_pnl_report(
        new_state, mark, pnl_report_id=ids["pnl_report_id"], correlation_id=run_correlation
    )
    event = compute_paper_realized_pnl_event(
        prior,
        generic_fill,
        generic_transition,
        new_state,
        realized_pnl_event_id=f"{gid}-rpnl-{seq}",
        correlation_id=run_correlation,
    )
    if event.status not in (PaperRealizedPnlStatus.COMPUTED, PaperRealizedPnlStatus.NO_REALIZED_PNL):
        raise _fail("projection_realized_event_not_computed")
    episode = build_paper_end_to_end_episode(
        bridge,
        order_intent,
        run,
        event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=order_intent.intent_digest,
        expected_episode_run_digest=run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=f"{gid}-episode-{seq}",
        run_id=f"{gid}-run-{seq}",
        correlation_id=run_correlation,
    )
    if episode.status is not PaperEndToEndEpisodeStatus.READY:
        raise _fail("projection_end_to_end_episode_not_ready")
    price, filled = Fraction(cast(str, fill.fill_price)), Fraction(fill.filled_quantity)
    expected_status = (
        PaperFillSimulationStatus.FILLED
        if fill.outcome is HistoricalExecutionFillOutcome.FILLED
        else PaperFillSimulationStatus.PARTIALLY_FILLED
    )
    generic_fee = Fraction(generic_fill.fee_amount)
    exact = (
        generic_fill.status is expected_status
        and Fraction(generic_fill.fill_price) == price
        and Fraction(generic_fill.filled_units) == filled
        and Fraction(generic_fill.gross_notional) == price * filled
        and generic_fee == price * filled * Fraction(gi.economics_policy.taker_fee_bps) / _BPS
        and _renders_as(generic_fee, fee.fee_amount)  # type: ignore[attr-defined]
        and Fraction(new_state.signed_units) == Fraction(transition.post_quantity)  # type: ignore[attr-defined]
        and _renders_as(Fraction(event.realized_pnl), transition.realized_gross_pnl)  # type: ignore[attr-defined]
        and report.status is PaperPnlReportStatus.COMPUTED
    )
    if not exact:
        raise _fail("projection_not_exactly_the_engine_economics")
    return PaperSleeveEpisodeEvidence(
        capacity_policy=lineage.capacity_policy,  # type: ignore[arg-type]
        allocator_draft=lineage.allocator_draft,  # type: ignore[arg-type]
        capacity_decision=decision,
        order_intent_request=request,
        admission_decision=admission,
        order_intent=order_intent,
        strategy_spec=spec,  # type: ignore[arg-type]
        signal_bridge=bridge,
        prior_position_state=prior,
        fill_market_snapshot=snapshot,
        fill_policy=fill_policy,
        episode_mark_snapshot=mark,
        fill_result=generic_fill,
        position_transition=generic_transition,
        new_position_state=new_state,
        episode_pnl_report=report,
        episode_run=run,
        realized_pnl_event=event,
        end_to_end_episode=episode,
    )


def _project(
    ctx: _Context, dataset: HistoricalPitDataset, outcome: HistoricalExecutionGovernedPaperOutcome
) -> GovernedPaperDayProjection:
    """The generic RG-3 records of every governed economic event inside ``W_k``, in the engine's event order."""

    genesis = ctx.genesis
    gid, market, opening, closing = genesis.genesis_id, genesis.instrument, ctx.opening_ns, ctx.closing_ns
    sealed = ctx.inputs.cycle_inputs.sealed_episodes
    state = sealed[-1].new_position_state if sealed else _genesis_position(genesis)
    intents = {item.intent_id: item for item in outcome.intents}
    transitions = {item.fill_digest: item for item in outcome.position_transitions}
    fees = {item.fill_digest: item for item in outcome.fee_cashflows}
    executed = [
        item
        for item in outcome.fills
        if item.outcome in (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)
        and item.execution_time_ns is not None
        and opening <= item.execution_time_ns < closing
    ]
    settlements = [item for item in outcome.funding_cashflows if opening <= item.liability_time_ns < closing]
    events = sorted(
        [(item.liability_time_ns, 0, index) for index, item in enumerate(settlements)]
        + [(cast(int, item.execution_time_ns), 1, index) for index, item in enumerate(executed)]
    )
    spec = governed_paper_strategy_spec(ctx.gi)
    cache: dict[int, _Lineage] = {}
    episodes: list[PaperSleeveEpisodeEvidence] = []
    funding: list[PaperSleeveFundingEvent] = []
    for _, kind, index in events:
        if kind == 0:
            cashflow = settlements[index]
            if Fraction(state.signed_units) != Fraction(cashflow.position_quantity):
                raise _fail("projection_funding_position_mismatch")
            # The rendered amount is artifact output; it enters RG-3 accounting only when it IS the engine's exact one.
            exact = (
                -Fraction(cashflow.position_quantity) * Fraction(cashflow.mark_price) * Fraction(cashflow.funding_rate)
            )
            if Fraction(cashflow.cashflow_amount) != exact:
                raise _Unsealable("funding_settlement_not_exactly_representable")
            funding.append(
                PaperSleeveFundingEvent(
                    event_id=f"{gid}-funding-{cashflow.funding_sequence_id}",
                    settlement_at_ns=cashflow.liability_time_ns,
                    position_state_digest=paper_position_state_digest(state),
                    funding_amount=cashflow.cashflow_amount,
                )
            )
            continue
        fill = executed[index]
        intent = intents[fill.intent_id]
        lineage = _deciding_cycle(ctx, intent, cache)
        if not (lineage.buy_authorized if intent.side is HistoricalExecutionSide.BUY else lineage.sell_authorized):
            raise _Unsealable("projected_fill_direction_not_authorized")
        episode = _episode(
            ctx, spec, dataset, intent, fill, transitions[fill.fill_digest], fees[fill.fill_digest], state, lineage
        )
        episodes.append(episode)
        state = episode.new_position_state
    end = [
        item
        for item in outcome.valuations
        if item.valuation_kind is HistoricalExecutionValuationKind.EVALUATION_END and item.time_ns == closing
    ]
    if len(end) != 1 or Fraction(end[0].position_quantity) != Fraction(state.signed_units):
        raise _fail("projection_close_position_mismatch")
    mark_view = historical_execution_latest_visible_mark(
        dataset, policy=ctx.gi.economics_policy, instrument=market, at_ns=closing
    )
    if mark_view is None:
        raise _Unsealable("day_close_mark_unavailable")
    if end[0].mark_record_digest is not None and end[0].mark_record_digest != mark_view[0]:
        raise _fail("projection_close_mark_mismatch")
    close_mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"{gid}-close-mark-{ctx.day_index}",
        market_symbol=market,
        mark_price=mark_view[1],
        observed_at_ns=closing,
        correlation_id=f"{gid}-corr-close",
    )
    close_report = compute_paper_pnl_report(
        state, close_mark, pnl_report_id=f"{gid}-close-pnl-{ctx.day_index}", correlation_id=f"{gid}-corr-close"
    )
    if close_report.status is not PaperPnlReportStatus.COMPUTED:
        raise _fail("projection_close_report_not_computed")
    return GovernedPaperDayProjection(
        episodes=tuple(episodes),
        day_close=PaperSleeveDayCloseValuation(close_mark_snapshot=close_mark, close_pnl_report=close_report),
        funding_events=tuple(funding),
    )


# --- the seal ---------------------------------------------------------------------------------------------------------


def _assemble_day(inputs: object) -> GovernedPaperDay:
    ctx = _context(inputs)
    dataset, new_count = _check_dataset(ctx)
    head_authority_digest, head_digest, successor, invalidated, head_governance = _closing_head(ctx)
    schedule = _schedule(ctx, invalidated)
    reasons: list[str] = []
    blocked = False
    economics = _economics(ctx, dataset)
    outcome: HistoricalExecutionGovernedPaperOutcome | None = None
    projection: GovernedPaperDayProjection | None = None
    opening_prefix = closing_prefix = ""
    pending: int | None = None
    pending_day: int | None = None
    pending_digest = ""
    pending_continuous = False
    if (
        economics.status is not EdgeEvidenceStatus.READY
        or economics.gate_verdict is not EdgeGateVerdict.PASS
        or economics.simulated_economics_computed is not True
    ):
        blocked = True
        reasons.append(_reason("economics_not_computed"))
        reasons.extend(economics.verdict_reason_codes)
    else:
        outcome = simulate_historical_execution_governed_paper(
            economics, expected_result_digest=economics.result_digest, schedule=schedule
        )
        if outcome.simulated is not True:
            blocked = True
            reasons.append(_reason("governed_outcome_not_simulated"))
            reasons.extend(outcome.reason_codes)
    if outcome is not None and outcome.simulated is True:
        prior = ctx.inputs.prior_seal
        excluded = (
            () if prior is None or prior.pending_decision_sequence is None else (prior.pending_decision_sequence,)
        )
        opening_prefix = historical_execution_governed_paper_prefix_digest(
            outcome, before_ns=ctx.opening_ns, excluded_decision_sequences=excluded
        )
        if prior is not None and opening_prefix != prior.closing_prefix_digest:
            raise _fail("prefix_replay_breaks_sealed_history")
        pending = outcome.pending_decision_sequence
        pending_day, pending_digest, pending_continuous = _pending_lineage(ctx, outcome)
        closing_prefix = historical_execution_governed_paper_prefix_digest(
            outcome, before_ns=ctx.closing_ns, excluded_decision_sequences=() if pending is None else (pending,)
        )
        try:
            projection = _project(ctx, dataset, outcome)
        except _Unsealable as failure:
            blocked = True
            reasons.append(_reason(failure.code))
    status = GovernedPaperDaySealStatus.BLOCKED if blocked else GovernedPaperDaySealStatus.SEALED
    if not blocked and head_governance:
        status = GovernedPaperDaySealStatus.NEEDS_GOVERNANCE_APPROVAL
        reasons.extend(head_governance)
    sealed = status is GovernedPaperDaySealStatus.SEALED
    cycle_inputs = ctx.inputs.cycle_inputs
    episodes: tuple[PaperSleeveEpisodeEvidence, ...] = ()
    cumulative = projection_digest = close_mark_digest = close_report_digest = closing_state_digest = ""
    episode_digests: tuple[str, ...] = ()
    if projection is not None:
        episodes = (*cycle_inputs.sealed_episodes, *projection.episodes)
        closes = (*cycle_inputs.sealed_day_closes, projection.day_close)
        funding = (*cycle_inputs.sealed_funding_events, *projection.funding_events)
        cumulative = governed_paper_sealed_history_digest(episodes, closes, funding)
        closing_state = episodes[-1].new_position_state if episodes else _genesis_position(ctx.genesis)
        closing_state_digest = paper_position_state_digest(closing_state)
        episode_digests = tuple(item.end_to_end_episode.episode_digest for item in projection.episodes)
        close_mark_digest = paper_mark_snapshot_digest(projection.day_close.close_mark_snapshot)
        close_report_digest = paper_pnl_report_digest(projection.day_close.close_pnl_report)
        projection_digest = governed_paper_sealed_history_digest(
            projection.episodes, (projection.day_close,), projection.funding_events
        )
    prior_seal = ctx.inputs.prior_seal
    prior_authority = ctx.inputs.prior_cycle_authority
    seed = GovernedPaperDaySeal(
        schema_version=_SEAL_SCHEMA,
        status=status,
        sealed=sealed,
        seal_id=ctx.seal_id,
        correlation_id=ctx.correlation_id,
        genesis_digest=ctx.genesis.genesis_digest,
        day_index=ctx.day_index,
        opening_ns=ctx.opening_ns,
        closing_ns=ctx.closing_ns,
        cycle_authority_digest=ctx.authority.authority_digest,
        cycle_status=ctx.authority.status.value,
        cycle_phase=ctx.authority.phase.value,
        prior_seal_digest="" if prior_seal is None else prior_seal.seal_digest,
        prior_cycle_authority_digest="" if prior_authority is None else prior_authority.authority_digest,
        opening_dataset_digest=cycle_inputs.opening_dataset.dataset_digest,
        dataset_digest=dataset.dataset_digest,
        dataset_record_count=len(dataset.records),
        new_record_count=new_count,
        run_digest=economics.run_digest,
        economics_result_digest=economics.result_digest,
        economics_gate_verdict=economics.gate_verdict.value,
        schedule_windows=schedule.windows,
        invalidated_from_ns=invalidated,
        schedule_digest=historical_execution_admission_schedule_digest(schedule),
        governed_outcome_digest="" if outcome is None else outcome.outcome_digest,
        governed_outcome_simulated=outcome is not None and outcome.simulated is True,
        opening_prefix_digest=opening_prefix,
        closing_prefix_digest=closing_prefix,
        pending_decision_sequence=pending,
        pending_deciding_day_index=pending_day,
        pending_deciding_cycle_authority_digest=pending_digest,
        pending_cycle_authority_continuous=pending_continuous,
        closing_head_authority_digest=head_authority_digest,
        closing_lifecycle_head_digest=head_digest,
        successor_effective_at_ns=successor,
        governance_rejected_fill_count=0 if outcome is None else len(outcome.governance_rejected_fill_digests),
        episode_digests=episode_digests,
        day_close_mark_digest=close_mark_digest,
        day_close_report_digest=close_report_digest,
        funding_event_count=0 if projection is None else len(projection.funding_events),
        projection_digest=projection_digest,
        cumulative_history_digest=cumulative,
        cumulative_episode_count=len(episodes),
        closing_position_state_digest=closing_state_digest,
        reason_codes=_sorted_unique(reasons),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_RULE_SET_DIGEST,
        seal_digest="",
    )
    seal = replace(seed, seal_digest=edge_payload_digest(_to_payload(seed), _SEAL_DIGEST_FIELD))
    return GovernedPaperDay(seal, projection if sealed else None, outcome if sealed else None)


def build_governed_paper_day(inputs: GovernedPaperDaySealInputs) -> GovernedPaperDay:
    """Replay, seal and project one governed paper day; provenance and causality defects raise. See the docstring."""

    return _assemble_day(inputs)


def verify_governed_paper_day_seal(seal: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a day seal by rebuilding it from its exact inputs. Total: never raises."""

    return _verify_rebuilt(
        seal, GovernedPaperDaySeal, lambda: _assemble_day(inputs).seal, _SEAL_DIGEST_FIELD, "day_seal"
    )


# --- the evidence -----------------------------------------------------------------------------------------------------


def _assemble_evidence(inputs: object) -> GovernedPaperExecutionEvidence:
    _require_exact(inputs, GovernedPaperExecutionInputs, "execution_inputs")
    ei = cast(GovernedPaperExecutionInputs, inputs)
    evidence_id = _require_identifier(ei.evidence_id, "evidence_id")
    correlation_id = _require_identifier(ei.correlation_id, "correlation_id")
    _require_exact(ei.genesis, GovernedPaperGenesis, "genesis")
    if not verify_governed_paper_genesis(ei.genesis, ei.genesis_inputs).intact:
        raise _fail("genesis_not_authentic")
    genesis = ei.genesis
    if genesis.status is not GovernedPaperGenesisStatus.READY:
        raise _fail("genesis_not_ready")
    if type(ei.days) is not tuple or type(ei.seals) is not tuple or not ei.days or len(ei.days) != len(ei.seals):
        raise _fail("days_malformed")
    reasons: list[str] = []
    phases: list[str] = []
    authority_digests: list[str] = []
    episodes: tuple[PaperSleeveEpisodeEvidence, ...] = ()
    closes: tuple[PaperSleeveDayCloseValuation, ...] = ()
    funding: tuple[PaperSleeveFundingEvent, ...] = ()
    previous: tuple[GovernedPaperDaySealInputs, GovernedPaperDaySeal] | None = None
    last_ladder: PaperSleeveLadderPriorDecision | None = None
    sealed_count = 0
    for index, (day_inputs, seal) in enumerate(zip(ei.days, ei.seals, strict=True)):
        _require_exact(day_inputs, GovernedPaperDaySealInputs, "day_inputs")
        _require_exact(seal, GovernedPaperDaySeal, "seal")
        if previous is not None and previous[1].sealed is not True:
            raise _fail("day_after_an_unsealed_day")
        day = _assemble_day(day_inputs)
        if _to_payload(day.seal) != _to_payload(seal):
            raise _fail("seal_not_the_reconstruction")
        cycle_inputs, authority = day_inputs.cycle_inputs, day_inputs.cycle_authority
        if authority.day_index != index or seal.genesis_digest != genesis.genesis_digest:
            raise _fail("day_out_of_lineage")
        if previous is not None:
            prior_inputs, prior_seal = previous
            if (
                day_inputs.prior_seal is None
                or day_inputs.prior_seal.seal_digest != prior_seal.seal_digest
                or day_inputs.prior_cycle_authority is None
                or day_inputs.prior_cycle_authority.authority_digest != prior_inputs.cycle_authority.authority_digest
                or authority.head_authority_digest != prior_seal.closing_head_authority_digest
            ):
                raise _fail("day_not_bound_to_its_predecessor")
        if governed_paper_sealed_history_digest(episodes, closes, funding) != authority.sealed_history_digest:
            raise _fail("cycle_history_not_the_sealed_projection")
        if (
            cycle_inputs.sealed_episodes != episodes
            or cycle_inputs.sealed_day_closes != closes
            or cycle_inputs.sealed_funding_events != funding
        ):
            raise _fail("cycle_history_not_the_sealed_projection")
        prior_ladder = cycle_inputs.prior_ladder
        if (last_ladder is None) != (prior_ladder is None) or (
            last_ladder is not None
            and prior_ladder is not None
            and prior_ladder.decision.decision_digest != last_ladder.decision.decision_digest
        ):
            raise _fail("ladder_lineage_not_continued")
        phases.append(authority.phase.value)
        authority_digests.append(authority.authority_digest)
        chain = governed_paper_cycle_chain(cycle_inputs)
        ladder = None if chain is None else chain.ladder
        last_ladder = (
            PaperSleeveLadderPriorDecision(chain.ladder_inputs, ladder)  # type: ignore[union-attr,arg-type]
            if ladder is not None and ladder.status is PaperSleeveLadderDecisionStatus.READY
            else None
        )
        if day.projection is not None:
            episodes = (*episodes, *day.projection.episodes)
            closes = (*closes, day.projection.day_close)
            funding = (*funding, *day.projection.funding_events)
        if seal.sealed:
            sealed_count += 1
        else:
            reasons.extend(seal.reason_codes)
        previous = (day_inputs, seal)
    last_inputs, last_seal = cast(tuple[GovernedPaperDaySealInputs, GovernedPaperDaySeal], previous)
    performance_digest, performance_status, return_count, sharpe = "", "NOT_DERIVED", 0, ""
    window_end = genesis.genesis_ns + sealed_count * _DAY_NS
    if last_seal.sealed and episodes:
        terminal = replace(
            last_inputs.cycle_inputs,
            cycle_id=f"{evidence_id}:terminal",
            day_index=sealed_count,
            opening_dataset=last_inputs.dataset,
            sealed_episodes=episodes,
            sealed_day_closes=closes,
            sealed_funding_events=funding,
            prior_ladder=last_ladder,
            head_authority_inputs=last_inputs.closing_head_authority_inputs,
            approval=None,
        )
        chain = governed_paper_cycle_chain(terminal)
        if chain is None or chain.performance is None or chain.performance_inputs is None:
            raise _fail("terminal_performance_unavailable")
        if not verify_paper_sleeve_performance_evidence(chain.performance, chain.performance_inputs).intact:
            raise _fail("terminal_performance_not_reproven")
        performance = chain.performance
        performance_digest = performance.performance_evidence_digest
        performance_status = performance.status.value
        return_count = len(performance.daily_returns)
        sharpe = performance.paper_sharpe_annualized
    status = GovernedPaperExecutionStatus.READY if last_seal.sealed else GovernedPaperExecutionStatus.BLOCKED
    first_b1 = next((i for i, p in enumerate(phases) if p == GovernedPaperCyclePhase.BOOTSTRAP_B1.value), None)
    first_ordinary = next((i for i, p in enumerate(phases) if p == GovernedPaperCyclePhase.ORDINARY.value), None)
    authorized = sum(1 for item in ei.days if item.cycle_authority.authorized)
    seed = GovernedPaperExecutionEvidence(
        schema_version=_EVIDENCE_SCHEMA,
        status=status,
        ready=status is GovernedPaperExecutionStatus.READY,
        evidence_id=evidence_id,
        correlation_id=correlation_id,
        genesis_digest=genesis.genesis_digest,
        sleeve_id=genesis.sleeve_id,
        instrument=genesis.instrument,
        genesis_ns=genesis.genesis_ns,
        day_count=len(ei.days),
        sealed_day_count=sealed_count,
        seal_digests=tuple(item.seal_digest for item in ei.seals),
        cycle_authority_digests=tuple(authority_digests),
        cycle_phases=tuple(phases),
        authorized_cycle_count=authorized,
        bootstrap_b0_cycle_count=phases.count(GovernedPaperCyclePhase.BOOTSTRAP_B0.value),
        bootstrap_b1_cycle_count=phases.count(GovernedPaperCyclePhase.BOOTSTRAP_B1.value),
        ordinary_cycle_count=phases.count(GovernedPaperCyclePhase.ORDINARY.value),
        first_b1_day_index=first_b1,
        first_ordinary_day_index=first_ordinary,
        invalidated_from_ns=last_seal.invalidated_from_ns,
        episode_count=len(episodes),
        cumulative_history_digest=governed_paper_sealed_history_digest(episodes, closes, funding),
        performance_window_end_ns=window_end,
        performance_evidence_digest=performance_digest,
        performance_status=performance_status,
        performance_daily_return_count=return_count,
        paper_sharpe_annualized=sharpe,
        reason_codes=_sorted_unique(reasons),
        rule_set_id=_RULE_SET_ID,
        rule_set_digest=GOVERNED_PAPER_EXECUTION_RULE_SET_DIGEST,
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), _EVIDENCE_DIGEST_FIELD))


def build_governed_paper_execution_evidence(inputs: GovernedPaperExecutionInputs) -> GovernedPaperExecutionEvidence:
    """Re-prove one whole governed paper execution lineage and its terminal RG-3 performance. See the docstring."""

    return _assemble_evidence(inputs)


def governed_paper_execution_evidence_to_dict(evidence: GovernedPaperExecutionEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of an evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_execution_evidence_digest(evidence: GovernedPaperExecutionEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _EVIDENCE_DIGEST_FIELD)


def verify_governed_paper_execution_evidence(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove an evidence by rebuilding it from its exact inputs. Total: never raises."""

    return _verify_rebuilt(
        evidence, GovernedPaperExecutionEvidence, lambda: _assemble_evidence(inputs), _EVIDENCE_DIGEST_FIELD, "evidence"
    )


__all__ = [
    "GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_EXECUTION_RULE_SET_DIGEST",
    "GovernedPaperDay",
    "GovernedPaperDayProjection",
    "GovernedPaperDaySeal",
    "GovernedPaperDaySealInputs",
    "GovernedPaperDaySealStatus",
    "GovernedPaperExecutionError",
    "GovernedPaperExecutionEvidence",
    "GovernedPaperExecutionInputs",
    "GovernedPaperExecutionStatus",
    "build_governed_paper_day",
    "build_governed_paper_execution_evidence",
    "governed_paper_day_seal_digest",
    "governed_paper_day_seal_to_dict",
    "governed_paper_execution_evidence_digest",
    "governed_paper_execution_evidence_to_dict",
    "governed_paper_execution_rule_set",
    "verify_governed_paper_day_seal",
    "verify_governed_paper_execution_evidence",
]
