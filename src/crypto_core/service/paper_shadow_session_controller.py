"""Paper/shadow session controller - Phase 15M.

Deterministic lifecycle surface for paper/shadow activation plans.

Design rules:
  - Session lifecycle only: prepare/start/tick/stop/finalize/reset/restore.
  - No execution wiring, order routing, alpha, ranking, or allocation logic.
  - Fail closed on missing readiness, malformed restore, or unsafe real-trading flags.
  - PAPER/SHADOW ONLY.
"""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from enum import Enum

from crypto_core.service.sleeve_admission_controller import (
    PaperShadowActivationPlan,
    PaperShadowActivationStatus,
    SleeveAdmissionCorruptError,
    paper_shadow_activation_plan_to_dict,
)


class PaperShadowSessionStatus(str, Enum):
    CREATED = "created"
    READY = "ready"
    RUNNING = "running"
    STOPPED = "stopped"
    FINALIZED = "finalized"
    BLOCKED = "blocked"
    FAILED = "failed"


class PaperShadowSessionCorruptError(RuntimeError):
    pass


class RuntimeMonitorStatus(str, Enum):
    NOT_READY = "not_ready"
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class GuardrailAction(str, Enum):
    NONE = "none"
    WARN = "warn"
    PAUSE_SESSION = "pause_session"
    STOP_SESSION = "stop_session"
    BLOCK_FINALIZE = "block_finalize"


class MarketEventType(str, Enum):
    TRADE = "trade"
    MARK_PRICE = "mark_price"
    INDEX_PRICE = "index_price"
    FUNDING = "funding"
    OPEN_INTEREST = "open_interest"
    BOOK_TICK = "book_tick"


class PaperDataSourceType(str, Enum):
    LOCAL_PAYLOAD = "local_payload"
    LOCAL_JSON = "local_json"
    IN_MEMORY = "in_memory"


class PaperIntentSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class PaperFillStatus(str, Enum):
    FILLED = "filled"
    REJECTED_NO_MARKET = "rejected_no_market"
    REJECTED_GUARDRAIL = "rejected_guardrail"
    REJECTED_INVALID_INTENT = "rejected_invalid_intent"
    SKIPPED = "skipped"


class PaperCostStatus(str, Enum):
    ACCEPTED = "accepted"
    REJECTED_EXCESSIVE_COST = "rejected_excessive_cost"
    REJECTED_INVALID_FILL = "rejected_invalid_fill"
    SKIPPED = "skipped"


class PaperPnLStatus(str, Enum):
    APPLIED = "applied"
    SKIPPED = "skipped"
    REJECTED_INVALID_POSITION = "rejected_invalid_position"


class PaperPortfolioRiskStatus(str, Enum):
    COMPLETE = "complete"
    INCOMPLETE = "incomplete"
    EMPTY = "empty"


class PaperRiskLimitDecisionStatus(str, Enum):
    PASS = "pass"  # noqa: S105 - risk decision outcome, not a credential.
    WARN = "warn"
    BLOCK_NEW_INTENTS = "block_new_intents"
    STOP_SESSION = "stop_session"


class PaperShadowRunEvidenceStatus(str, Enum):
    PASS = "pass"  # noqa: S105 - run evidence outcome, not a credential.
    WARN = "warn"
    BLOCKED = "blocked"
    INCONCLUSIVE = "inconclusive"
    EMPTY = "empty"


@dataclass(frozen=True)
class MarketEvent:
    symbol: str
    venue: str
    ts_ns: int
    event_type: MarketEventType
    price: float | None = None
    mark_price: float | None = None
    index_price: float | None = None
    funding_rate: float | None = None
    open_interest: float | None = None


@dataclass(frozen=True)
class MarketEventBatch:
    batch_id: str
    events: tuple[MarketEvent, ...]


@dataclass(frozen=True)
class FeedReplayPlan:
    replay_id: str
    batches: tuple[MarketEventBatch, ...]


@dataclass(frozen=True)
class FeedReplayResult:
    replay_id: str
    session_id: str
    session_status: PaperShadowSessionStatus
    batches_planned: int
    batches_replayed: int
    events_replayed: int
    batches_rejected: int
    first_event_ns: int | None = None
    last_event_ns: int | None = None
    guardrail_actions_seen: tuple[GuardrailAction, ...] = ()
    halted_by_guardrail: bool = False
    halt_reason: str | None = None
    rejected_batch_ids: tuple[str, ...] = ()
    operator_summary: str = "Feed replay has not run."


@dataclass(frozen=True)
class PaperDataSourceSnapshot:
    source_id: str
    source_type: PaperDataSourceType
    symbols: tuple[str, ...]
    venue: str
    as_of_ns: int
    batches_produced: int = 0
    events_produced: int = 0
    rejected_records: int = 0
    batch_ids: tuple[str, ...] = ()
    first_event_ns: int | None = None
    last_event_ns: int | None = None


@dataclass(frozen=True)
class PaperDataSourceBatchResult:
    source: PaperDataSourceSnapshot
    batch: MarketEventBatch
    rejected_record_ids: tuple[str, ...] = ()
    operator_summary: str = "Paper data source batch has not been built."


@dataclass(frozen=True)
class PaperIntent:
    sleeve_id: str
    symbol: str
    venue: str
    side: PaperIntentSide
    intent_ts_ns: int
    reason: str
    source: str
    qty: float | None = None
    notional: float | None = None


@dataclass(frozen=True)
class PaperIntentBatch:
    batch_id: str
    intents: tuple[PaperIntent, ...]


@dataclass(frozen=True)
class PaperIntentValidationResult:
    intent: PaperIntent
    accepted: bool
    rejection_reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaperIntentBatchResult:
    batch_id: str
    session_id: str
    as_of_ns: int
    results: tuple[PaperIntentValidationResult, ...]
    intents_seen: int
    accepted_count: int
    rejected_count: int
    sleeves_seen: tuple[str, ...] = ()
    symbols_seen: tuple[str, ...] = ()
    venues_seen: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper intent batch has not been validated."


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    intent_id: str
    sleeve_id: str
    symbol: str
    venue: str
    side: PaperIntentSide
    qty: float | None
    notional: float | None
    fill_price: float | None
    fill_ts_ns: int
    status: PaperFillStatus
    reason: str


@dataclass(frozen=True)
class PaperFillSimulationResult:
    simulation_id: str
    session_id: str
    as_of_ns: int
    intent_batch_id: str
    fills: tuple[PaperFill, ...]
    fill_attempts: int
    simulated_fills: int
    rejected_fills: int
    symbols_filled: tuple[str, ...] = ()
    sleeves_filled: tuple[str, ...] = ()
    rejection_reasons: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper fill simulation has not run."


@dataclass(frozen=True)
class PaperCostModel:
    fee_bps: float = 0.0
    slippage_bps: float = 0.0
    min_fee: float = 0.0
    reject_if_cost_exceeds_bps: float | None = None
    partial_fill_ratio: float = 1.0


@dataclass(frozen=True)
class PaperCostLine:
    fill_id: str
    intent_id: str
    sleeve_id: str
    symbol: str
    venue: str
    side: PaperIntentSide
    gross_notional: float
    fee: float
    slippage_cost: float
    net_notional: float
    effective_price: float | None
    cost_bps: float
    status: PaperCostStatus
    reasons: tuple[str, ...] = ()
    qty: float = 0.0
    fill_price: float | None = None
    fill_ts_ns: int = 0


@dataclass(frozen=True)
class PaperCostResult:
    cost_result_id: str
    session_id: str
    as_of_ns: int
    source_fill_simulation_id: str
    cost_model: PaperCostModel
    costs: tuple[PaperCostLine, ...]
    cost_evaluations: int
    accepted_costs: int
    rejected_costs: int
    skipped_costs: int
    gross_notional: float
    fee: float
    slippage_cost: float
    net_notional: float
    effective_price: float | None
    cost_bps: float
    status: PaperCostStatus
    reasons: tuple[str, ...] = ()
    total_fee: float = 0.0
    total_slippage_cost: float = 0.0
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper cost model has not run."


@dataclass(frozen=True)
class PaperPosition:
    position_id: str
    sleeve_id: str
    symbol: str
    venue: str
    qty: float
    avg_price: float | None
    gross_notional: float
    fees: float
    slippage_cost: float
    realized_pnl: float
    unrealized_pnl: float | None = None
    last_price: float | None = None
    is_open: bool = False


@dataclass(frozen=True)
class PaperPnLLine:
    line_id: str
    cost_result_id: str
    fill_id: str
    sleeve_id: str
    symbol: str
    venue: str
    side: PaperIntentSide
    qty: float
    price: float | None
    fee: float
    slippage_cost: float
    realized_pnl: float
    position_qty_after: float
    avg_price_after: float | None
    status: PaperPnLStatus
    reasons: tuple[str, ...] = ()


@dataclass(frozen=True)
class PaperPnLLedger:
    ledger_id: str
    session_id: str
    as_of_ns: int
    source_cost_result_id: str
    positions: tuple[PaperPosition, ...]
    pnl_lines: tuple[PaperPnLLine, ...]
    pnl_events: int
    open_positions: int
    closed_positions: int
    total_fees: float
    total_slippage: float
    realized_pnl: float
    unrealized_pnl: float | None = None
    status: PaperPnLStatus = PaperPnLStatus.SKIPPED
    reasons: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper PnL ledger has not run."


@dataclass(frozen=True)
class PaperPortfolioExposure:
    exposure_id: str
    dimension: str
    key: str
    gross_exposure: float
    net_exposure: float
    open_position_count: int


@dataclass(frozen=True)
class PaperPortfolioRiskSnapshot:
    snapshot_id: str
    session_id: str
    as_of_ns: int
    source_ledger_id: str
    equity_start: float | None
    equity_current: float | None
    realized_pnl: float
    unrealized_pnl: float | None
    total_fees: float
    total_slippage: float
    gross_exposure: float
    net_exposure: float
    open_position_count: int
    sleeve_exposures: tuple[PaperPortfolioExposure, ...]
    symbol_exposures: tuple[PaperPortfolioExposure, ...]
    missing_price_positions: tuple[str, ...] = ()
    drawdown_available: bool = False
    current_drawdown: float | None = None
    max_drawdown: float | None = None
    status: PaperPortfolioRiskStatus = PaperPortfolioRiskStatus.EMPTY
    reasons: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper portfolio risk has not been assessed."


@dataclass(frozen=True)
class PaperRiskLimitPolicy:
    policy_id: str = "default-paper-risk-limit-policy"
    max_gross_exposure: float | None = None
    max_net_exposure: float | None = None
    max_open_positions: int | None = None
    max_unrealized_loss: float | None = None
    max_total_loss: float | None = None
    require_complete_prices: bool = True


@dataclass(frozen=True)
class PaperRiskLimitDecision:
    decision_id: str
    session_id: str
    as_of_ns: int
    source_risk_snapshot_id: str
    policy: PaperRiskLimitPolicy
    status: PaperRiskLimitDecisionStatus
    passed: bool
    block_new_intents: bool
    stop_session: bool
    breached_limits: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper risk limits have not been assessed."


@dataclass(frozen=True)
class PaperShadowRunEvidenceReport:
    report_id: str
    as_of_ns: int
    source_summary: dict
    replay_summary: dict
    session_status: PaperShadowSessionStatus
    monitor_status: RuntimeMonitorStatus
    guardrail_status: GuardrailAction
    accepted_event_count: int = 0
    rejected_event_count: int = 0
    accepted_batch_count: int = 0
    rejected_batch_count: int = 0
    symbols: tuple[str, ...] = ()
    venues: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    evidence_status: PaperShadowRunEvidenceStatus = PaperShadowRunEvidenceStatus.EMPTY
    next_actions: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper/shadow run evidence has not been assessed."


@dataclass(frozen=True)
class MultiSourceRunEvidenceReport:
    aggregate_id: str
    as_of_ns: int
    report_ids: tuple[str, ...]
    report_count: int
    pass_count: int
    warn_count: int
    blocked_count: int
    inconclusive_count: int
    empty_count: int
    accepted_event_count: int = 0
    rejected_event_count: int = 0
    accepted_batch_count: int = 0
    rejected_batch_count: int = 0
    symbols: tuple[str, ...] = ()
    venues: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    guardrail_actions: tuple[GuardrailAction, ...] = ()
    evidence_status: PaperShadowRunEvidenceStatus = PaperShadowRunEvidenceStatus.EMPTY
    next_actions: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Multi-source paper/shadow run evidence has not been assessed."


@dataclass(frozen=True)
class PaperShadowEvidenceBundle:
    bundle_id: str
    as_of_ns: int
    aggregate_report: MultiSourceRunEvidenceReport
    run_reports: tuple[PaperShadowRunEvidenceReport, ...]
    report_ids: tuple[str, ...]
    evidence_status: PaperShadowRunEvidenceStatus
    missing_report_ids: tuple[str, ...] = ()
    blockers: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ()
    next_actions: tuple[str, ...] = ()
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    operator_summary: str = "Paper/shadow evidence bundle has not been assessed."


@dataclass(frozen=True)
class MarketEventCursor:
    symbol: str
    venue: str
    last_event_ns: int


@dataclass(frozen=True)
class MarketEventPrice:
    symbol: str
    venue: str
    last_event_ns: int
    price: float


@dataclass(frozen=True)
class RuntimeMonitorSnapshot:
    status: RuntimeMonitorStatus = RuntimeMonitorStatus.NOT_READY
    event_count: int = 0
    stale_feed_detected: bool = False
    symbol_coverage_ok: bool = False
    venue_coverage_ok: bool = False
    price_validity_ok: bool = False
    event_gap_count: int = 0
    last_event_ns: int | None = None
    monitored_symbols: tuple[str, ...] = ()
    monitored_venues: tuple[str, ...] = ()
    required_symbols: tuple[str, ...] = ()
    required_venues: tuple[str, ...] = ()
    reason_codes: tuple[str, ...] = ("no_market_events",)


@dataclass(frozen=True)
class GuardrailSnapshot:
    primary_action: GuardrailAction = GuardrailAction.BLOCK_FINALIZE
    actions: tuple[GuardrailAction, ...] = (GuardrailAction.BLOCK_FINALIZE, GuardrailAction.WARN)
    reason_codes: tuple[str, ...] = ("no_market_events",)
    monitor_status: RuntimeMonitorStatus = RuntimeMonitorStatus.NOT_READY
    block_finalize: bool = True
    should_pause_session: bool = False
    should_stop_session: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    paper_only: bool = True


@dataclass(frozen=True)
class PaperShadowSessionSnapshot:
    session_id: str
    status: PaperShadowSessionStatus
    as_of_ns: int
    plan_id: str = "unknown"
    plan_status: str = "unknown"
    source_manifest_status: str = "unknown"
    prepared_at_ns: int | None = None
    started_at_ns: int | None = None
    last_tick_at_ns: int | None = None
    stopped_at_ns: int | None = None
    finalized_at_ns: int | None = None
    tick_count: int = 0
    active_sleeves_seen: tuple[str, ...] = ()
    blockers_seen: tuple[str, ...] = ()
    event_count: int = 0
    symbols_seen: tuple[str, ...] = ()
    venues_seen: tuple[str, ...] = ()
    first_event_ns: int | None = None
    last_event_ns: int | None = None
    rejected_event_count: int = 0
    market_event_cursors: tuple[MarketEventCursor, ...] = ()
    market_event_prices: tuple[MarketEventPrice, ...] = ()
    runtime_monitor: RuntimeMonitorSnapshot = field(default_factory=RuntimeMonitorSnapshot)
    guardrail: GuardrailSnapshot = field(default_factory=GuardrailSnapshot)
    intents_seen: int = 0
    accepted_intent_count: int = 0
    rejected_intent_count: int = 0
    intent_sleeves_seen: tuple[str, ...] = ()
    intent_symbols_seen: tuple[str, ...] = ()
    intent_venues_seen: tuple[str, ...] = ()
    intent_rejection_reasons: tuple[str, ...] = ()
    fill_attempts: int = 0
    simulated_fills: int = 0
    rejected_fills: int = 0
    symbols_filled: tuple[str, ...] = ()
    sleeves_filled: tuple[str, ...] = ()
    cost_evaluations: int = 0
    accepted_costs: int = 0
    rejected_costs: int = 0
    total_fee: float = 0.0
    total_slippage_cost: float = 0.0
    pnl_events: int = 0
    open_positions: int = 0
    closed_positions: int = 0
    total_fees: float = 0.0
    total_slippage: float = 0.0
    realized_pnl: float = 0.0
    paper_only: bool = True
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    active_sleeves: tuple[str, ...] = ()
    inactive_sleeves: tuple[str, ...] = ()
    admitted_unallocated_sleeves: tuple[str, ...] = ()
    activation_blockers: tuple[str, ...] = ()
    evidence_blockers: tuple[str, ...] = ()
    governance_blockers: tuple[str, ...] = ()
    operator_summary: str = "Paper/shadow session has not been prepared."


class PaperShadowSessionController:
    """Manage deterministic paper/shadow session lifecycle evidence."""

    def __init__(
        self,
        *,
        session_id: str = "paper-shadow-session-unprepared",
        clock_ns: Callable[[], int] | None = None,
        required_market_symbols: tuple[str, ...] = (),
        required_market_venues: tuple[str, ...] = (),
        max_market_event_gap_ns: int | None = None,
        snapshot: PaperShadowSessionSnapshot | None = None,
    ) -> None:
        self._clock_ns = time.time_ns if clock_ns is None else clock_ns
        self._required_market_symbols = _sorted_unique(required_market_symbols)
        self._required_market_venues = _sorted_unique(required_market_venues)
        self._max_market_event_gap_ns = _optional_non_negative_int(
            max_market_event_gap_ns,
            "max_market_event_gap_ns",
        )
        self._snapshot = (
            paper_shadow_session_snapshot_from_dict(paper_shadow_session_snapshot_to_dict(snapshot))
            if snapshot is not None
            else PaperShadowSessionSnapshot(
                session_id=session_id,
                status=PaperShadowSessionStatus.CREATED,
                as_of_ns=0,
            )
        )
        _validate_session_snapshot(self._snapshot)

    @property
    def current_snapshot(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def snapshot(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def report(self) -> PaperShadowSessionSnapshot:
        return self._snapshot

    def guardrail_snapshot(self) -> GuardrailSnapshot:
        return self._snapshot.guardrail

    def prepare(self, plan: PaperShadowActivationPlan) -> PaperShadowSessionSnapshot:
        _validate_activation_plan_for_session(plan)
        now = self._now_ns()
        status = (
            PaperShadowSessionStatus.READY
            if plan.activation_status == PaperShadowActivationStatus.READY_FOR_PAPER_SHADOW
            else PaperShadowSessionStatus.BLOCKED
        )
        blockers = _sorted_unique(
            (
                *plan.activation_blockers,
                *plan.evidence_blockers,
                *plan.governance_blockers,
            )
        )
        monitor = build_runtime_monitor_snapshot(
            event_count=0,
            monitored_symbols=(),
            monitored_venues=(),
            required_symbols=self._required_market_symbols,
            required_venues=self._required_market_venues,
        )
        return self._apply_snapshot(
            PaperShadowSessionSnapshot(
                session_id=_session_id_for_plan(plan),
                status=status,
                as_of_ns=now,
                plan_id=plan.plan_id,
                plan_status=plan.activation_status.value,
                source_manifest_status=plan.source_manifest_status.value,
                prepared_at_ns=now,
                tick_count=0,
                active_sleeves_seen=(),
                blockers_seen=blockers,
                runtime_monitor=monitor,
                guardrail=build_guardrail_snapshot(
                    monitor,
                    session_status=status,
                    rejected_event_count=0,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                ),
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                active_sleeves=plan.active_sleeves,
                inactive_sleeves=plan.inactive_sleeves,
                admitted_unallocated_sleeves=plan.admitted_unallocated_sleeves,
                activation_blockers=plan.activation_blockers,
                evidence_blockers=plan.evidence_blockers,
                governance_blockers=plan.governance_blockers,
                operator_summary=_operator_summary(status, 0, plan.active_sleeves, blockers),
            )
        )

    def start(self) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.READY:
            raise PaperShadowSessionCorruptError("paper/shadow session can only start from READY state")
        now = self._now_ns()
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.RUNNING,
                as_of_ns=now,
                started_at_ns=now,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            ),
        )

    def record_tick(
        self,
        *,
        active_sleeves_seen: tuple[str, ...] = (),
        blockers_seen: tuple[str, ...] = (),
    ) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session cannot record ticks before start")
        now = self._now_ns()
        seen = _sorted_unique((*self._snapshot.active_sleeves_seen, *active_sleeves_seen))
        blockers = _sorted_unique((*self._snapshot.blockers_seen, *blockers_seen))
        return self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                last_tick_at_ns=now,
                tick_count=self._snapshot.tick_count + 1,
                active_sleeves_seen=seen,
                blockers_seen=blockers,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count + 1,
                    self._snapshot.active_sleeves,
                    blockers,
                ),
            ),
        )

    def record_market_event_batch(self, batch: MarketEventBatch | dict) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session cannot record market events before start")
        try:
            normalized = market_event_batch_from_dict(batch) if isinstance(batch, dict) else _normalize_batch(batch)
            _validate_batch_against_session(self._snapshot, normalized)
        except PaperShadowSessionCorruptError:
            self._record_rejected_events(_rejected_event_increment(batch))
            raise
        now = self._now_ns()
        events = normalized.events
        event_count = len(events)
        symbols = _sorted_unique((*self._snapshot.symbols_seen, *(event.symbol for event in events)))
        venues = _sorted_unique((*self._snapshot.venues_seen, *(event.venue for event in events)))
        first_event_ns = min(event.ts_ns for event in events)
        last_event_ns = max(event.ts_ns for event in events)
        event_gap_count = _market_event_gap_count(
            self._snapshot.market_event_cursors,
            events,
            self._max_market_event_gap_ns,
        )
        cursors = _merge_market_event_cursors(self._snapshot.market_event_cursors, events)
        prices = _merge_market_event_prices(self._snapshot.market_event_prices, events)
        total_event_count = self._snapshot.event_count + event_count
        total_event_gap_count = self._snapshot.runtime_monitor.event_gap_count + event_gap_count
        session_first_event_ns = (
            first_event_ns
            if self._snapshot.first_event_ns is None
            else min(self._snapshot.first_event_ns, first_event_ns)
        )
        session_last_event_ns = (
            last_event_ns if self._snapshot.last_event_ns is None else max(self._snapshot.last_event_ns, last_event_ns)
        )
        monitor = build_runtime_monitor_snapshot(
            event_count=total_event_count,
            monitored_symbols=symbols,
            monitored_venues=venues,
            required_symbols=self._required_market_symbols,
            required_venues=self._required_market_venues,
            price_validity_ok=True,
            event_gap_count=total_event_gap_count,
            last_event_ns=session_last_event_ns,
        )
        guardrail = build_guardrail_snapshot(
            monitor,
            session_status=self._snapshot.status,
            rejected_event_count=self._snapshot.rejected_event_count,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        return self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                last_tick_at_ns=now,
                tick_count=self._snapshot.tick_count + 1,
                event_count=total_event_count,
                symbols_seen=symbols,
                venues_seen=venues,
                first_event_ns=session_first_event_ns,
                last_event_ns=session_last_event_ns,
                market_event_cursors=cursors,
                market_event_prices=prices,
                runtime_monitor=monitor,
                guardrail=guardrail,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.RUNNING,
                    self._snapshot.tick_count + 1,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            )
        )

    def tick_from_market_events(self, batch: MarketEventBatch | dict) -> PaperShadowSessionSnapshot:
        return self.record_market_event_batch(batch)

    def record_paper_intent_batch(
        self,
        batch: PaperIntentBatch | dict | tuple[PaperIntent, ...],
    ) -> PaperIntentBatchResult:
        normalized = _coerce_paper_intent_batch(batch)
        now = self._now_ns()
        results = tuple(
            PaperIntentValidationResult(
                intent=intent,
                accepted=not (reasons := _paper_intent_rejection_reasons(self._snapshot, intent)),
                rejection_reasons=reasons,
            )
            for intent in normalized.intents
        )
        result = PaperIntentBatchResult(
            batch_id=normalized.batch_id,
            session_id=self._snapshot.session_id,
            as_of_ns=now,
            results=results,
            intents_seen=len(results),
            accepted_count=sum(1 for item in results if item.accepted),
            rejected_count=sum(1 for item in results if not item.accepted),
            sleeves_seen=_sorted_unique(tuple(item.intent.sleeve_id for item in results)),
            symbols_seen=_sorted_unique(tuple(item.intent.symbol for item in results)),
            venues_seen=_sorted_unique(tuple(item.intent.venue for item in results)),
            rejection_reasons=_sorted_unique(tuple(reason for item in results for reason in item.rejection_reasons)),
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
            operator_summary=_paper_intent_batch_summary(normalized.batch_id, results),
        )
        _validate_paper_intent_batch_result(result)
        snapshot = replace(
            self._snapshot,
            as_of_ns=now,
            intents_seen=self._snapshot.intents_seen + result.intents_seen,
            accepted_intent_count=self._snapshot.accepted_intent_count + result.accepted_count,
            rejected_intent_count=self._snapshot.rejected_intent_count + result.rejected_count,
            intent_sleeves_seen=_sorted_unique((*self._snapshot.intent_sleeves_seen, *result.sleeves_seen)),
            intent_symbols_seen=_sorted_unique((*self._snapshot.intent_symbols_seen, *result.symbols_seen)),
            intent_venues_seen=_sorted_unique((*self._snapshot.intent_venues_seen, *result.venues_seen)),
            intent_rejection_reasons=_sorted_unique(
                (*self._snapshot.intent_rejection_reasons, *result.rejection_reasons)
            ),
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        self._apply_snapshot(snapshot)
        return result

    def simulate_paper_fills(
        self,
        result: PaperIntentBatchResult | dict,
    ) -> PaperFillSimulationResult:
        """Simulate deterministic paper-only fills from accepted intent audit results."""
        normalized = paper_intent_batch_result_from_dict(result) if isinstance(result, dict) else result
        _validate_paper_intent_batch_result(normalized)
        now = self._now_ns()
        fills = tuple(
            _paper_fill_for_intent_result(
                self._snapshot,
                normalized,
                item,
                index=index,
                fill_ts_ns=now,
            )
            for index, item in enumerate(normalized.results)
        )
        fills = tuple(sorted(fills, key=_paper_fill_sort_key))
        fill_attempts = sum(1 for fill in fills if fill.status != PaperFillStatus.SKIPPED)
        simulated_fills = sum(1 for fill in fills if fill.status == PaperFillStatus.FILLED)
        rejected_fills = sum(
            1
            for fill in fills
            if fill.status
            in {
                PaperFillStatus.REJECTED_NO_MARKET,
                PaperFillStatus.REJECTED_GUARDRAIL,
                PaperFillStatus.REJECTED_INVALID_INTENT,
            }
        )
        simulation = PaperFillSimulationResult(
            simulation_id=_paper_fill_simulation_id(self._snapshot.session_id, normalized.batch_id, fills),
            session_id=self._snapshot.session_id,
            as_of_ns=now,
            intent_batch_id=normalized.batch_id,
            fills=fills,
            fill_attempts=fill_attempts,
            simulated_fills=simulated_fills,
            rejected_fills=rejected_fills,
            symbols_filled=_sorted_unique(
                tuple(fill.symbol for fill in fills if fill.status == PaperFillStatus.FILLED)
            ),
            sleeves_filled=_sorted_unique(
                tuple(fill.sleeve_id for fill in fills if fill.status == PaperFillStatus.FILLED)
            ),
            rejection_reasons=_sorted_unique(
                tuple(fill.reason for fill in fills if fill.status != PaperFillStatus.FILLED)
            ),
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
            operator_summary=_paper_fill_simulation_summary(
                self._snapshot.session_id,
                fill_attempts,
                simulated_fills,
                rejected_fills,
            ),
        )
        _validate_paper_fill_simulation_result(simulation)
        self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                fill_attempts=self._snapshot.fill_attempts + simulation.fill_attempts,
                simulated_fills=self._snapshot.simulated_fills + simulation.simulated_fills,
                rejected_fills=self._snapshot.rejected_fills + simulation.rejected_fills,
                symbols_filled=_sorted_unique((*self._snapshot.symbols_filled, *simulation.symbols_filled)),
                sleeves_filled=_sorted_unique((*self._snapshot.sleeves_filled, *simulation.sleeves_filled)),
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
            )
        )
        return simulation

    def evaluate_paper_costs(
        self,
        result: PaperFillSimulationResult | dict,
        *,
        cost_model: PaperCostModel | dict | None = None,
    ) -> PaperCostResult:
        """Evaluate deterministic paper-only fees/slippage for simulated paper fills."""
        normalized = paper_fill_simulation_result_from_dict(result) if isinstance(result, dict) else result
        _validate_paper_fill_simulation_result(normalized)
        if normalized.session_id != self._snapshot.session_id:
            raise PaperShadowSessionCorruptError("paper cost result source fill simulation session mismatch")
        model = paper_cost_model_from_dict(cost_model) if isinstance(cost_model, dict) else cost_model
        resolved_model = PaperCostModel() if model is None else model
        _validate_paper_cost_model(resolved_model)
        now = self._now_ns()
        costs = tuple(_paper_cost_line_for_fill(fill, resolved_model) for fill in normalized.fills)
        costs = tuple(sorted(costs, key=_paper_cost_line_sort_key))
        cost_evaluations = sum(1 for line in costs if line.status != PaperCostStatus.SKIPPED)
        accepted_costs = sum(1 for line in costs if line.status == PaperCostStatus.ACCEPTED)
        rejected_costs = sum(
            1
            for line in costs
            if line.status
            in {
                PaperCostStatus.REJECTED_EXCESSIVE_COST,
                PaperCostStatus.REJECTED_INVALID_FILL,
            }
        )
        gross_notional = sum(line.gross_notional for line in costs if line.status != PaperCostStatus.SKIPPED)
        fee = sum(line.fee for line in costs if line.status != PaperCostStatus.SKIPPED)
        slippage_cost = sum(line.slippage_cost for line in costs if line.status != PaperCostStatus.SKIPPED)
        net_notional = sum(line.net_notional for line in costs if line.status != PaperCostStatus.SKIPPED)
        effective_price = _aggregate_effective_price(costs)
        cost_bps = _cost_bps(fee + slippage_cost, gross_notional)
        status = _paper_cost_result_status(costs)
        reasons = _paper_cost_result_reasons(costs, status)
        cost_result = PaperCostResult(
            cost_result_id=_paper_cost_result_id(normalized.simulation_id, resolved_model, costs),
            session_id=self._snapshot.session_id,
            as_of_ns=now,
            source_fill_simulation_id=normalized.simulation_id,
            cost_model=resolved_model,
            costs=costs,
            cost_evaluations=cost_evaluations,
            accepted_costs=accepted_costs,
            rejected_costs=rejected_costs,
            skipped_costs=sum(1 for line in costs if line.status == PaperCostStatus.SKIPPED),
            gross_notional=gross_notional,
            fee=fee,
            slippage_cost=slippage_cost,
            net_notional=net_notional,
            effective_price=effective_price,
            cost_bps=cost_bps,
            status=status,
            reasons=reasons,
            total_fee=fee,
            total_slippage_cost=slippage_cost,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
            operator_summary=_paper_cost_summary(status, cost_evaluations, accepted_costs, rejected_costs),
        )
        _validate_paper_cost_result(cost_result)
        self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                cost_evaluations=self._snapshot.cost_evaluations + cost_result.cost_evaluations,
                accepted_costs=self._snapshot.accepted_costs + cost_result.accepted_costs,
                rejected_costs=self._snapshot.rejected_costs + cost_result.rejected_costs,
                total_fee=self._snapshot.total_fee + cost_result.total_fee,
                total_slippage_cost=self._snapshot.total_slippage_cost + cost_result.total_slippage_cost,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
            )
        )
        return cost_result

    def apply_paper_pnl_ledger(
        self,
        result: PaperCostResult | dict,
        *,
        prior_ledger: PaperPnLLedger | dict | None = None,
    ) -> PaperPnLLedger:
        """Apply accepted paper cost lines to a deterministic long-only position/PnL ledger."""
        normalized = paper_cost_result_from_dict(result) if isinstance(result, dict) else result
        _validate_paper_cost_result(normalized)
        if normalized.session_id != self._snapshot.session_id:
            raise PaperShadowSessionCorruptError("paper PnL ledger source cost result session mismatch")
        resolved_prior = paper_pnl_ledger_from_dict(prior_ledger) if isinstance(prior_ledger, dict) else prior_ledger
        if resolved_prior is not None:
            _validate_paper_pnl_ledger(resolved_prior)
            if resolved_prior.session_id != self._snapshot.session_id:
                raise PaperShadowSessionCorruptError("paper PnL prior ledger session mismatch")
        now = self._now_ns()
        ledger = build_paper_pnl_ledger(
            cost_result=normalized,
            latest_prices=self._snapshot.market_event_prices,
            prior_ledger=resolved_prior,
            as_of_ns=now,
        )
        _validate_paper_pnl_ledger(ledger)
        self._apply_snapshot(
            replace(
                self._snapshot,
                as_of_ns=now,
                pnl_events=ledger.pnl_events,
                open_positions=ledger.open_positions,
                closed_positions=ledger.closed_positions,
                total_fees=ledger.total_fees,
                total_slippage=ledger.total_slippage,
                realized_pnl=ledger.realized_pnl,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
            )
        )
        return ledger

    def paper_portfolio_risk_snapshot(
        self,
        ledger: PaperPnLLedger | dict,
        *,
        equity_start: float | None = None,
        equity_history: tuple[float, ...] = (),
        snapshot_id: str | None = None,
    ) -> PaperPortfolioRiskSnapshot:
        """Build a deterministic paper-only risk/equity snapshot from the PnL ledger."""
        normalized = paper_pnl_ledger_from_dict(ledger) if isinstance(ledger, dict) else ledger
        _validate_paper_pnl_ledger(normalized)
        if normalized.session_id != self._snapshot.session_id:
            raise PaperShadowSessionCorruptError("paper portfolio risk source ledger session mismatch")
        risk = build_paper_portfolio_risk_snapshot(
            ledger=normalized,
            latest_prices=self._snapshot.market_event_prices,
            equity_start=equity_start,
            equity_history=equity_history,
            snapshot_id=snapshot_id,
            as_of_ns=self._now_ns(),
        )
        _validate_paper_portfolio_risk_snapshot(risk)
        return risk

    def paper_risk_limit_decision(
        self,
        snapshot: PaperPortfolioRiskSnapshot | dict,
        *,
        policy: PaperRiskLimitPolicy | dict | None = None,
        decision_id: str | None = None,
    ) -> PaperRiskLimitDecision:
        """Evaluate deterministic paper risk-limit and kill-switch decisions."""
        normalized = paper_portfolio_risk_snapshot_from_dict(snapshot) if isinstance(snapshot, dict) else snapshot
        _validate_paper_portfolio_risk_snapshot(normalized)
        if normalized.session_id != self._snapshot.session_id:
            raise PaperShadowSessionCorruptError("paper risk limit source snapshot session mismatch")
        decision = build_paper_risk_limit_decision(
            risk_snapshot=normalized,
            policy=policy,
            decision_id=decision_id,
            as_of_ns=self._now_ns(),
        )
        _validate_paper_risk_limit_decision(decision)
        return decision

    def replay_feed(self, plan: FeedReplayPlan | dict | tuple[MarketEventBatch, ...]) -> FeedReplayResult:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow feed replay can only run while session is RUNNING")
        replay_plan = _coerce_feed_replay_plan(plan)
        batches_replayed = 0
        events_replayed = 0
        batches_rejected = 0
        first_event_ns: int | None = None
        last_event_ns: int | None = None
        rejected_batch_ids: list[str] = []
        actions_seen: list[GuardrailAction] = []
        halted = False
        halt_reason: str | None = None

        for batch in replay_plan.batches:
            if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
                halted = True
                halt_reason = self._snapshot.status.value
                break
            try:
                snapshot = self.record_market_event_batch(batch)
                normalized = _normalize_batch(batch)
            except PaperShadowSessionCorruptError:
                batches_rejected += 1
                rejected_batch_ids.append(_batch_id_or_unknown(batch))
                actions_seen.extend(self._snapshot.guardrail.actions)
                if self._snapshot.guardrail.should_stop_session or self._snapshot.guardrail.should_pause_session:
                    applied = self.apply_guardrails()
                    actions_seen.extend(applied.guardrail.actions)
                    halted = True
                    halt_reason = applied.guardrail.primary_action.value
                    break
                continue

            batches_replayed += 1
            events_replayed += len(normalized.events)
            batch_first_event_ns = min(event.ts_ns for event in normalized.events)
            batch_last_event_ns = max(event.ts_ns for event in normalized.events)
            first_event_ns = (
                batch_first_event_ns if first_event_ns is None else min(first_event_ns, batch_first_event_ns)
            )
            last_event_ns = batch_last_event_ns if last_event_ns is None else max(last_event_ns, batch_last_event_ns)
            actions_seen.extend(snapshot.guardrail.actions)
            if snapshot.guardrail.should_stop_session or snapshot.guardrail.should_pause_session:
                applied = self.apply_guardrails()
                actions_seen.extend(applied.guardrail.actions)
                halted = True
                halt_reason = applied.guardrail.primary_action.value
                break

        result = FeedReplayResult(
            replay_id=replay_plan.replay_id,
            session_id=self._snapshot.session_id,
            session_status=self._snapshot.status,
            batches_planned=len(replay_plan.batches),
            batches_replayed=batches_replayed,
            events_replayed=events_replayed,
            batches_rejected=batches_rejected,
            first_event_ns=first_event_ns,
            last_event_ns=last_event_ns,
            guardrail_actions_seen=_sorted_unique_actions(actions_seen),
            halted_by_guardrail=halted,
            halt_reason=halt_reason,
            rejected_batch_ids=_sorted_unique(rejected_batch_ids),
            operator_summary=_feed_replay_summary(
                replay_plan.replay_id,
                batches_replayed,
                events_replayed,
                batches_rejected,
                halted,
                halt_reason,
            ),
        )
        _validate_feed_replay_result(result)
        return result

    def apply_guardrails(self) -> PaperShadowSessionSnapshot:
        guardrail = self._snapshot.guardrail
        if guardrail.should_stop_session and self._snapshot.status == PaperShadowSessionStatus.RUNNING:
            now = self._now_ns()
            blockers = _sorted_unique((*self._snapshot.blockers_seen, *guardrail.reason_codes))
            return self._apply_snapshot(
                replace(
                    self._snapshot,
                    status=PaperShadowSessionStatus.STOPPED,
                    as_of_ns=now,
                    stopped_at_ns=now,
                    blockers_seen=blockers,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                    operator_summary=_operator_summary(
                        PaperShadowSessionStatus.STOPPED,
                        self._snapshot.tick_count,
                        self._snapshot.active_sleeves,
                        blockers,
                    ),
                )
            )
        if guardrail.should_pause_session and self._snapshot.status == PaperShadowSessionStatus.RUNNING:
            now = self._now_ns()
            blockers = _sorted_unique((*self._snapshot.blockers_seen, *guardrail.reason_codes))
            return self._apply_snapshot(
                replace(
                    self._snapshot,
                    status=PaperShadowSessionStatus.BLOCKED,
                    as_of_ns=now,
                    blockers_seen=blockers,
                    paper_only=True,
                    real_orders_enabled=False,
                    real_money_enabled=False,
                    operator_summary=_operator_summary(
                        PaperShadowSessionStatus.BLOCKED,
                        self._snapshot.tick_count,
                        self._snapshot.active_sleeves,
                        blockers,
                    ),
                )
            )
        return self._snapshot

    def stop(self, *, blockers_seen: tuple[str, ...] = ()) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.RUNNING:
            raise PaperShadowSessionCorruptError("paper/shadow session can only stop from RUNNING state")
        now = self._now_ns()
        blockers = _sorted_unique((*self._snapshot.blockers_seen, *blockers_seen))
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.STOPPED,
                as_of_ns=now,
                stopped_at_ns=now,
                blockers_seen=blockers,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.STOPPED,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    blockers,
                ),
            ),
        )

    def finalize(self) -> PaperShadowSessionSnapshot:
        if self._snapshot.status != PaperShadowSessionStatus.STOPPED:
            raise PaperShadowSessionCorruptError("paper/shadow session can only finalize from STOPPED state")
        if self._snapshot.guardrail.block_finalize:
            raise PaperShadowSessionCorruptError("paper/shadow session guardrails block finalize")
        now = self._now_ns()
        return self._apply_snapshot(
            replace(
                self._snapshot,
                status=PaperShadowSessionStatus.FINALIZED,
                as_of_ns=now,
                finalized_at_ns=now,
                paper_only=True,
                real_orders_enabled=False,
                real_money_enabled=False,
                operator_summary=_operator_summary(
                    PaperShadowSessionStatus.FINALIZED,
                    self._snapshot.tick_count,
                    self._snapshot.active_sleeves,
                    self._snapshot.blockers_seen,
                ),
            ),
        )

    def reset(self) -> PaperShadowSessionSnapshot:
        return self._apply_snapshot(
            PaperShadowSessionSnapshot(
                session_id="paper-shadow-session-unprepared",
                status=PaperShadowSessionStatus.CREATED,
                as_of_ns=0,
            )
        )

    def restore(self, snapshot: PaperShadowSessionSnapshot | dict) -> PaperShadowSessionSnapshot:
        restored = (
            snapshot
            if isinstance(snapshot, PaperShadowSessionSnapshot)
            else paper_shadow_session_snapshot_from_dict(snapshot)
        )
        _validate_session_snapshot(restored)
        self._snapshot = restored
        return self._snapshot

    def to_dict(self) -> dict:
        return paper_shadow_session_snapshot_to_dict(self._snapshot)

    def _now_ns(self) -> int:
        now = self._clock_ns()
        if not isinstance(now, int) or isinstance(now, bool) or now < 0:
            raise PaperShadowSessionCorruptError("clock_ns must return a non-negative int")
        return now

    def _apply_snapshot(self, snapshot: PaperShadowSessionSnapshot) -> PaperShadowSessionSnapshot:
        _validate_session_snapshot(snapshot)
        self._snapshot = snapshot
        return self._snapshot

    def _record_rejected_events(self, count: int) -> None:
        if count <= 0:
            count = 1
        rejected_count = self._snapshot.rejected_event_count + count
        guardrail = build_guardrail_snapshot(
            self._snapshot.runtime_monitor,
            session_status=self._snapshot.status,
            rejected_event_count=rejected_count,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        self._snapshot = replace(
            self._snapshot,
            rejected_event_count=rejected_count,
            guardrail=guardrail,
            paper_only=True,
            real_orders_enabled=False,
            real_money_enabled=False,
        )
        _validate_session_snapshot(self._snapshot)


def paper_shadow_session_snapshot_to_dict(snapshot: PaperShadowSessionSnapshot) -> dict:
    _validate_session_snapshot(snapshot)
    return {
        "session_id": snapshot.session_id,
        "status": snapshot.status.value,
        "as_of_ns": snapshot.as_of_ns,
        "plan_id": snapshot.plan_id,
        "plan_status": snapshot.plan_status,
        "source_manifest_status": snapshot.source_manifest_status,
        "prepared_at_ns": snapshot.prepared_at_ns,
        "started_at_ns": snapshot.started_at_ns,
        "last_tick_at_ns": snapshot.last_tick_at_ns,
        "stopped_at_ns": snapshot.stopped_at_ns,
        "finalized_at_ns": snapshot.finalized_at_ns,
        "tick_count": snapshot.tick_count,
        "active_sleeves_seen": list(snapshot.active_sleeves_seen),
        "blockers_seen": list(snapshot.blockers_seen),
        "event_count": snapshot.event_count,
        "symbols_seen": list(snapshot.symbols_seen),
        "venues_seen": list(snapshot.venues_seen),
        "first_event_ns": snapshot.first_event_ns,
        "last_event_ns": snapshot.last_event_ns,
        "rejected_event_count": snapshot.rejected_event_count,
        "market_event_cursors": [market_event_cursor_to_dict(cursor) for cursor in snapshot.market_event_cursors],
        "market_event_prices": [market_event_price_to_dict(price) for price in snapshot.market_event_prices],
        "runtime_monitor": runtime_monitor_snapshot_to_dict(snapshot.runtime_monitor),
        "guardrail": guardrail_snapshot_to_dict(snapshot.guardrail),
        "intents_seen": snapshot.intents_seen,
        "accepted_intent_count": snapshot.accepted_intent_count,
        "rejected_intent_count": snapshot.rejected_intent_count,
        "intent_sleeves_seen": list(snapshot.intent_sleeves_seen),
        "intent_symbols_seen": list(snapshot.intent_symbols_seen),
        "intent_venues_seen": list(snapshot.intent_venues_seen),
        "intent_rejection_reasons": list(snapshot.intent_rejection_reasons),
        "fill_attempts": snapshot.fill_attempts,
        "simulated_fills": snapshot.simulated_fills,
        "rejected_fills": snapshot.rejected_fills,
        "symbols_filled": list(snapshot.symbols_filled),
        "sleeves_filled": list(snapshot.sleeves_filled),
        "cost_evaluations": snapshot.cost_evaluations,
        "accepted_costs": snapshot.accepted_costs,
        "rejected_costs": snapshot.rejected_costs,
        "total_fee": snapshot.total_fee,
        "total_slippage_cost": snapshot.total_slippage_cost,
        "pnl_events": snapshot.pnl_events,
        "open_positions": snapshot.open_positions,
        "closed_positions": snapshot.closed_positions,
        "total_fees": snapshot.total_fees,
        "total_slippage": snapshot.total_slippage,
        "realized_pnl": snapshot.realized_pnl,
        "paper_only": snapshot.paper_only,
        "real_orders_enabled": snapshot.real_orders_enabled,
        "real_money_enabled": snapshot.real_money_enabled,
        "active_sleeves": list(snapshot.active_sleeves),
        "inactive_sleeves": list(snapshot.inactive_sleeves),
        "admitted_unallocated_sleeves": list(snapshot.admitted_unallocated_sleeves),
        "activation_blockers": list(snapshot.activation_blockers),
        "evidence_blockers": list(snapshot.evidence_blockers),
        "governance_blockers": list(snapshot.governance_blockers),
        "operator_summary": snapshot.operator_summary,
    }


def paper_shadow_session_snapshot_from_dict(data: dict) -> PaperShadowSessionSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow session snapshot must be a dict, got {type(data).__name__!r}"
        )
    status = _session_status_or_default(data.get("status"), PaperShadowSessionStatus.CREATED)
    event_count = _require_non_negative_int(data.get("event_count", 0), "event_count")
    symbols_seen = _sorted_unique(data.get("symbols_seen", ()))
    venues_seen = _sorted_unique(data.get("venues_seen", ()))
    last_event_ns = _optional_non_negative_int(data.get("last_event_ns"), "last_event_ns")
    monitor_value = data.get("runtime_monitor")
    runtime_monitor = (
        runtime_monitor_snapshot_from_dict(_dict_value(monitor_value, "runtime_monitor"))
        if monitor_value is not None
        else build_runtime_monitor_snapshot(
            event_count=event_count,
            monitored_symbols=symbols_seen,
            monitored_venues=venues_seen,
            last_event_ns=last_event_ns,
        )
    )
    rejected_event_count = _require_non_negative_int(data.get("rejected_event_count", 0), "rejected_event_count")
    paper_only = _bool_or_default(data, "paper_only", True)
    real_orders_enabled = _bool_or_default(data, "real_orders_enabled", False)
    real_money_enabled = _bool_or_default(data, "real_money_enabled", False)
    guardrail_value = data.get("guardrail")
    guardrail = (
        guardrail_snapshot_from_dict(_dict_value(guardrail_value, "guardrail"))
        if guardrail_value is not None
        else build_guardrail_snapshot(
            runtime_monitor,
            session_status=status,
            rejected_event_count=rejected_event_count,
            paper_only=paper_only,
            real_orders_enabled=real_orders_enabled,
            real_money_enabled=real_money_enabled,
        )
    )
    snapshot = PaperShadowSessionSnapshot(
        session_id=_string_or_default(data.get("session_id"), "paper-shadow-session-legacy"),
        status=status,
        as_of_ns=_require_non_negative_int(data.get("as_of_ns", 0), "as_of_ns"),
        plan_id=_string_or_default(data.get("plan_id"), "unknown"),
        plan_status=_string_or_default(data.get("plan_status"), "unknown"),
        source_manifest_status=_string_or_default(data.get("source_manifest_status"), "unknown"),
        prepared_at_ns=_optional_non_negative_int(data.get("prepared_at_ns"), "prepared_at_ns"),
        started_at_ns=_optional_non_negative_int(data.get("started_at_ns"), "started_at_ns"),
        last_tick_at_ns=_optional_non_negative_int(data.get("last_tick_at_ns"), "last_tick_at_ns"),
        stopped_at_ns=_optional_non_negative_int(data.get("stopped_at_ns"), "stopped_at_ns"),
        finalized_at_ns=_optional_non_negative_int(data.get("finalized_at_ns"), "finalized_at_ns"),
        tick_count=_require_non_negative_int(data.get("tick_count", 0), "tick_count"),
        active_sleeves_seen=_sorted_unique(data.get("active_sleeves_seen", ())),
        blockers_seen=_sorted_unique(data.get("blockers_seen", ())),
        event_count=event_count,
        symbols_seen=symbols_seen,
        venues_seen=venues_seen,
        first_event_ns=_optional_non_negative_int(data.get("first_event_ns"), "first_event_ns"),
        last_event_ns=last_event_ns,
        rejected_event_count=rejected_event_count,
        market_event_cursors=_market_event_cursors_from_data(data.get("market_event_cursors", ())),
        market_event_prices=_market_event_prices_from_data(data.get("market_event_prices", ())),
        runtime_monitor=runtime_monitor,
        guardrail=guardrail,
        intents_seen=_require_non_negative_int(data.get("intents_seen", 0), "intents_seen"),
        accepted_intent_count=_require_non_negative_int(
            data.get("accepted_intent_count", 0),
            "accepted_intent_count",
        ),
        rejected_intent_count=_require_non_negative_int(
            data.get("rejected_intent_count", 0),
            "rejected_intent_count",
        ),
        intent_sleeves_seen=_sorted_unique(data.get("intent_sleeves_seen", ())),
        intent_symbols_seen=_sorted_unique(data.get("intent_symbols_seen", ())),
        intent_venues_seen=_sorted_unique(data.get("intent_venues_seen", ())),
        intent_rejection_reasons=_sorted_unique(data.get("intent_rejection_reasons", ())),
        fill_attempts=_require_non_negative_int(data.get("fill_attempts", 0), "fill_attempts"),
        simulated_fills=_require_non_negative_int(data.get("simulated_fills", 0), "simulated_fills"),
        rejected_fills=_require_non_negative_int(data.get("rejected_fills", 0), "rejected_fills"),
        symbols_filled=_sorted_unique(data.get("symbols_filled", ())),
        sleeves_filled=_sorted_unique(data.get("sleeves_filled", ())),
        cost_evaluations=_require_non_negative_int(data.get("cost_evaluations", 0), "cost_evaluations"),
        accepted_costs=_require_non_negative_int(data.get("accepted_costs", 0), "accepted_costs"),
        rejected_costs=_require_non_negative_int(data.get("rejected_costs", 0), "rejected_costs"),
        total_fee=_require_non_negative_float(data.get("total_fee", 0.0), "total_fee"),
        total_slippage_cost=_require_non_negative_float(
            data.get("total_slippage_cost", 0.0),
            "total_slippage_cost",
        ),
        pnl_events=_require_non_negative_int(data.get("pnl_events", 0), "pnl_events"),
        open_positions=_require_non_negative_int(data.get("open_positions", 0), "open_positions"),
        closed_positions=_require_non_negative_int(data.get("closed_positions", 0), "closed_positions"),
        total_fees=_require_non_negative_float(data.get("total_fees", 0.0), "total_fees"),
        total_slippage=_require_non_negative_float(data.get("total_slippage", 0.0), "total_slippage"),
        realized_pnl=_require_float(data.get("realized_pnl", 0.0), "realized_pnl"),
        paper_only=paper_only,
        real_orders_enabled=real_orders_enabled,
        real_money_enabled=real_money_enabled,
        active_sleeves=_sorted_unique(data.get("active_sleeves", ())),
        inactive_sleeves=_sorted_unique(data.get("inactive_sleeves", ())),
        admitted_unallocated_sleeves=_sorted_unique(data.get("admitted_unallocated_sleeves", ())),
        activation_blockers=_sorted_unique(data.get("activation_blockers", ())),
        evidence_blockers=_sorted_unique(data.get("evidence_blockers", ())),
        governance_blockers=_sorted_unique(data.get("governance_blockers", ())),
        operator_summary=_string_or_default(
            data.get("operator_summary"),
            _operator_summary(status, _require_non_negative_int(data.get("tick_count", 0), "tick_count"), (), ()),
        ),
    )
    _validate_session_snapshot(snapshot)
    return snapshot


def build_market_event_batch(
    events: tuple[MarketEvent, ...],
    *,
    batch_id: str | None = None,
) -> MarketEventBatch:
    original = MarketEventBatch(
        batch_id=batch_id or _market_event_batch_id(events),
        events=tuple(events),
    )
    return _normalize_batch(original)


def market_event_to_dict(event: MarketEvent) -> dict:
    _validate_market_event(event)
    return {
        "symbol": event.symbol,
        "venue": event.venue,
        "ts_ns": event.ts_ns,
        "event_type": event.event_type.value,
        "price": event.price,
        "mark_price": event.mark_price,
        "index_price": event.index_price,
        "funding_rate": event.funding_rate,
        "open_interest": event.open_interest,
    }


def market_event_from_dict(data: dict) -> MarketEvent:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event must be a dict, got {type(data).__name__!r}")
    event = MarketEvent(
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        ts_ns=_require_non_negative_int(data.get("ts_ns"), "ts_ns"),
        event_type=_market_event_type_from_value(data.get("event_type")),
        price=_optional_non_negative_float(data.get("price"), "price"),
        mark_price=_optional_non_negative_float(data.get("mark_price"), "mark_price"),
        index_price=_optional_non_negative_float(data.get("index_price"), "index_price"),
        funding_rate=_optional_float(data.get("funding_rate"), "funding_rate"),
        open_interest=_optional_non_negative_float(data.get("open_interest"), "open_interest"),
    )
    _validate_market_event(event)
    return event


def market_event_batch_to_dict(batch: MarketEventBatch) -> dict:
    normalized = _normalize_batch(batch)
    return {
        "batch_id": normalized.batch_id,
        "events": [market_event_to_dict(event) for event in normalized.events],
    }


def market_event_batch_from_dict(data: dict) -> MarketEventBatch:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event batch must be a dict, got {type(data).__name__!r}")
    events_value = data.get("events")
    if not isinstance(events_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("Market event batch field 'events' must be a list/tuple")
    events = tuple(market_event_from_dict(_dict_value(item, "events")) for item in events_value)
    return build_market_event_batch(
        events,
        batch_id=_string_or_default(data.get("batch_id"), _market_event_batch_id(events)),
    )


def build_feed_replay_plan(
    batches: tuple[MarketEventBatch | dict, ...],
    *,
    replay_id: str | None = None,
) -> FeedReplayPlan:
    if not isinstance(batches, tuple):
        raise PaperShadowSessionCorruptError("feed replay batches must be a tuple")
    normalized_batches = tuple(
        market_event_batch_from_dict(batch) if isinstance(batch, dict) else _normalize_batch(batch) for batch in batches
    )
    plan = FeedReplayPlan(
        replay_id=_string_or_default(replay_id, _feed_replay_plan_id(normalized_batches)),
        batches=normalized_batches,
    )
    _validate_feed_replay_plan(plan)
    return plan


def feed_replay_plan_to_dict(plan: FeedReplayPlan) -> dict:
    _validate_feed_replay_plan(plan)
    return {
        "replay_id": plan.replay_id,
        "batches": [market_event_batch_to_dict(batch) for batch in plan.batches],
    }


def feed_replay_plan_from_dict(data: dict) -> FeedReplayPlan:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Feed replay plan must be a dict, got {type(data).__name__!r}")
    batches_value = data.get("batches")
    if not isinstance(batches_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("feed replay plan batches must be a list/tuple")
    return build_feed_replay_plan(
        tuple(_dict_value(batch, "batches") for batch in batches_value),
        replay_id=_require_non_empty_str(data.get("replay_id"), "replay_id"),
    )


def feed_replay_result_to_dict(result: FeedReplayResult) -> dict:
    _validate_feed_replay_result(result)
    return {
        "replay_id": result.replay_id,
        "session_id": result.session_id,
        "session_status": result.session_status.value,
        "batches_planned": result.batches_planned,
        "batches_replayed": result.batches_replayed,
        "events_replayed": result.events_replayed,
        "batches_rejected": result.batches_rejected,
        "first_event_ns": result.first_event_ns,
        "last_event_ns": result.last_event_ns,
        "guardrail_actions_seen": [action.value for action in result.guardrail_actions_seen],
        "halted_by_guardrail": result.halted_by_guardrail,
        "halt_reason": result.halt_reason,
        "rejected_batch_ids": list(result.rejected_batch_ids),
        "operator_summary": result.operator_summary,
    }


def feed_replay_result_from_dict(data: dict) -> FeedReplayResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Feed replay result must be a dict, got {type(data).__name__!r}")
    result = FeedReplayResult(
        replay_id=_require_non_empty_str(data.get("replay_id"), "replay_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        session_status=_session_status_or_default(data.get("session_status"), PaperShadowSessionStatus.FAILED),
        batches_planned=_require_non_negative_int(data.get("batches_planned"), "batches_planned"),
        batches_replayed=_require_non_negative_int(data.get("batches_replayed"), "batches_replayed"),
        events_replayed=_require_non_negative_int(data.get("events_replayed"), "events_replayed"),
        batches_rejected=_require_non_negative_int(data.get("batches_rejected"), "batches_rejected"),
        first_event_ns=_optional_non_negative_int(data.get("first_event_ns"), "first_event_ns"),
        last_event_ns=_optional_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
        guardrail_actions_seen=_guardrail_actions_from_data(data.get("guardrail_actions_seen", ())),
        halted_by_guardrail=_bool_or_default(data, "halted_by_guardrail", False),
        halt_reason=_optional_str(data.get("halt_reason"), "halt_reason"),
        rejected_batch_ids=_sorted_unique(data.get("rejected_batch_ids", ())),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_feed_replay_result(result)
    return result


def build_paper_data_source_batch_result(
    payload: dict,
    *,
    allowed_source_ids: tuple[str, ...] = (),
    allow_unknown_source: bool = False,
    batch_id: str | None = None,
) -> PaperDataSourceBatchResult:
    if not isinstance(payload, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper data source payload must be a dict, got {type(payload).__name__!r}"
        )
    _reject_forbidden_data_source_keys(payload)
    source_id = _require_non_empty_str(payload.get("source_id"), "source_id")
    allowed = _sorted_unique(allowed_source_ids)
    if not allow_unknown_source and source_id not in allowed:
        raise PaperShadowSessionCorruptError("paper data source source_id is not explicitly allowed")
    source_type = _paper_data_source_type_from_value(payload.get("source_type"))
    venue = _require_non_empty_str(payload.get("venue"), "venue")
    as_of_ns = _require_non_negative_int(payload.get("as_of_ns"), "as_of_ns")
    records_value = payload.get("records", payload.get("events"))
    if not isinstance(records_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper data source records must be a list/tuple")
    if not records_value:
        raise PaperShadowSessionCorruptError("paper data source records cannot be empty")
    symbols = _sorted_unique(payload.get("symbols", ()))
    events = tuple(
        _paper_data_source_record_to_event(_dict_value(record, "records"), venue=venue, as_of_ns=as_of_ns)
        for record in records_value
    )
    event_symbols = _sorted_unique(tuple(event.symbol for event in events))
    if symbols and symbols != event_symbols:
        raise PaperShadowSessionCorruptError("paper data source declared symbols must match record symbols")
    resolved_symbols = event_symbols
    batch = build_market_event_batch(
        events,
        batch_id=batch_id or _paper_data_source_batch_id(source_id, venue, events),
    )
    snapshot = PaperDataSourceSnapshot(
        source_id=source_id,
        source_type=source_type,
        symbols=resolved_symbols,
        venue=venue,
        as_of_ns=as_of_ns,
        batches_produced=1,
        events_produced=len(batch.events),
        rejected_records=0,
        batch_ids=(batch.batch_id,),
        first_event_ns=min(event.ts_ns for event in batch.events),
        last_event_ns=max(event.ts_ns for event in batch.events),
    )
    result = PaperDataSourceBatchResult(
        source=snapshot,
        batch=batch,
        rejected_record_ids=(),
        operator_summary=_paper_data_source_summary(snapshot),
    )
    _validate_paper_data_source_batch_result(result)
    return result


def paper_data_source_payload_to_market_event_batch(
    payload: dict,
    *,
    allowed_source_ids: tuple[str, ...] = (),
    allow_unknown_source: bool = False,
    batch_id: str | None = None,
) -> MarketEventBatch:
    return build_paper_data_source_batch_result(
        payload,
        allowed_source_ids=allowed_source_ids,
        allow_unknown_source=allow_unknown_source,
        batch_id=batch_id,
    ).batch


def paper_data_source_snapshot_to_dict(snapshot: PaperDataSourceSnapshot) -> dict:
    _validate_paper_data_source_snapshot(snapshot)
    return {
        "source_id": snapshot.source_id,
        "source_type": snapshot.source_type.value,
        "symbols": list(snapshot.symbols),
        "venue": snapshot.venue,
        "as_of_ns": snapshot.as_of_ns,
        "batches_produced": snapshot.batches_produced,
        "events_produced": snapshot.events_produced,
        "rejected_records": snapshot.rejected_records,
        "batch_ids": list(snapshot.batch_ids),
        "first_event_ns": snapshot.first_event_ns,
        "last_event_ns": snapshot.last_event_ns,
    }


def paper_data_source_snapshot_from_dict(data: dict) -> PaperDataSourceSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper data source snapshot must be a dict, got {type(data).__name__!r}")
    snapshot = PaperDataSourceSnapshot(
        source_id=_require_non_empty_str(data.get("source_id"), "source_id"),
        source_type=_paper_data_source_type_from_value(data.get("source_type")),
        symbols=_sorted_unique(data.get("symbols", ())),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        batches_produced=_require_non_negative_int(data.get("batches_produced", 0), "batches_produced"),
        events_produced=_require_non_negative_int(data.get("events_produced", 0), "events_produced"),
        rejected_records=_require_non_negative_int(data.get("rejected_records", 0), "rejected_records"),
        batch_ids=_sorted_unique(data.get("batch_ids", ())),
        first_event_ns=_optional_non_negative_int(data.get("first_event_ns"), "first_event_ns"),
        last_event_ns=_optional_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
    )
    _validate_paper_data_source_snapshot(snapshot)
    return snapshot


def paper_data_source_batch_result_to_dict(result: PaperDataSourceBatchResult) -> dict:
    _validate_paper_data_source_batch_result(result)
    return {
        "source": paper_data_source_snapshot_to_dict(result.source),
        "batch": market_event_batch_to_dict(result.batch),
        "rejected_record_ids": list(result.rejected_record_ids),
        "operator_summary": result.operator_summary,
    }


def paper_data_source_batch_result_from_dict(data: dict) -> PaperDataSourceBatchResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper data source batch result must be a dict, got {type(data).__name__!r}"
        )
    result = PaperDataSourceBatchResult(
        source=paper_data_source_snapshot_from_dict(_dict_value(data.get("source"), "source")),
        batch=market_event_batch_from_dict(_dict_value(data.get("batch"), "batch")),
        rejected_record_ids=_sorted_unique(data.get("rejected_record_ids", ())),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_data_source_batch_result(result)
    return result


def build_paper_intent_batch(
    intents: tuple[PaperIntent | dict, ...],
    *,
    batch_id: str | None = None,
) -> PaperIntentBatch:
    if not isinstance(intents, tuple):
        raise PaperShadowSessionCorruptError("paper intent batch intents must be a tuple")
    resolved = tuple(paper_intent_from_dict(item) if isinstance(item, dict) else item for item in intents)
    batch = PaperIntentBatch(
        batch_id=_string_or_default(batch_id, _paper_intent_batch_id(resolved)),
        intents=tuple(sorted(resolved, key=_paper_intent_sort_key)),
    )
    _validate_paper_intent_batch(batch)
    return batch


def paper_intent_to_dict(intent: PaperIntent) -> dict:
    _validate_paper_intent_shape(intent)
    return {
        "sleeve_id": intent.sleeve_id,
        "symbol": intent.symbol,
        "venue": intent.venue,
        "side": intent.side.value,
        "qty": intent.qty,
        "notional": intent.notional,
        "intent_ts_ns": intent.intent_ts_ns,
        "reason": intent.reason,
        "source": intent.source,
    }


def paper_intent_from_dict(data: dict) -> PaperIntent:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper intent must be a dict, got {type(data).__name__!r}")
    intent = PaperIntent(
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        side=_paper_intent_side_from_value(data.get("side")),
        qty=_optional_float(data.get("qty"), "qty"),
        notional=_optional_float(data.get("notional"), "notional"),
        intent_ts_ns=_require_non_negative_int(data.get("intent_ts_ns"), "intent_ts_ns"),
        reason=_require_non_empty_str(data.get("reason"), "reason"),
        source=_require_non_empty_str(data.get("source"), "source"),
    )
    _validate_paper_intent_shape(intent)
    return intent


def paper_intent_batch_to_dict(batch: PaperIntentBatch) -> dict:
    normalized = build_paper_intent_batch(batch.intents, batch_id=batch.batch_id)
    return {
        "batch_id": normalized.batch_id,
        "intents": [paper_intent_to_dict(intent) for intent in normalized.intents],
    }


def paper_intent_batch_from_dict(data: dict) -> PaperIntentBatch:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper intent batch must be a dict, got {type(data).__name__!r}")
    intents_value = data.get("intents")
    if not isinstance(intents_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper intent batch field 'intents' must be a list/tuple")
    batch_id_value = data.get("batch_id")
    return build_paper_intent_batch(
        tuple(_dict_value(item, "intents") for item in intents_value),
        batch_id=None if batch_id_value is None else _require_non_empty_str(batch_id_value, "batch_id"),
    )


def paper_intent_validation_result_to_dict(result: PaperIntentValidationResult) -> dict:
    _validate_paper_intent_validation_result(result)
    return {
        "intent": paper_intent_to_dict(result.intent),
        "accepted": result.accepted,
        "rejection_reasons": list(result.rejection_reasons),
    }


def paper_intent_validation_result_from_dict(data: dict) -> PaperIntentValidationResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper intent validation result must be a dict, got {type(data).__name__!r}"
        )
    result = PaperIntentValidationResult(
        intent=paper_intent_from_dict(_dict_value(data.get("intent"), "intent")),
        accepted=_bool_or_default(data, "accepted", False),
        rejection_reasons=_sorted_unique(data.get("rejection_reasons", ())),
    )
    _validate_paper_intent_validation_result(result)
    return result


def paper_intent_batch_result_to_dict(result: PaperIntentBatchResult) -> dict:
    _validate_paper_intent_batch_result(result)
    return {
        "batch_id": result.batch_id,
        "session_id": result.session_id,
        "as_of_ns": result.as_of_ns,
        "results": [paper_intent_validation_result_to_dict(item) for item in result.results],
        "intents_seen": result.intents_seen,
        "accepted_count": result.accepted_count,
        "rejected_count": result.rejected_count,
        "sleeves_seen": list(result.sleeves_seen),
        "symbols_seen": list(result.symbols_seen),
        "venues_seen": list(result.venues_seen),
        "rejection_reasons": list(result.rejection_reasons),
        "paper_only": result.paper_only,
        "real_orders_enabled": result.real_orders_enabled,
        "real_money_enabled": result.real_money_enabled,
        "operator_summary": result.operator_summary,
    }


def paper_intent_batch_result_from_dict(data: dict) -> PaperIntentBatchResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper intent batch result must be a dict, got {type(data).__name__!r}")
    results_value = data.get("results")
    if not isinstance(results_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper intent batch result field 'results' must be a list/tuple")
    result = PaperIntentBatchResult(
        batch_id=_require_non_empty_str(data.get("batch_id"), "batch_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        results=tuple(paper_intent_validation_result_from_dict(_dict_value(item, "results")) for item in results_value),
        intents_seen=_require_non_negative_int(data.get("intents_seen"), "intents_seen"),
        accepted_count=_require_non_negative_int(data.get("accepted_count"), "accepted_count"),
        rejected_count=_require_non_negative_int(data.get("rejected_count"), "rejected_count"),
        sleeves_seen=_sorted_unique(data.get("sleeves_seen", ())),
        symbols_seen=_sorted_unique(data.get("symbols_seen", ())),
        venues_seen=_sorted_unique(data.get("venues_seen", ())),
        rejection_reasons=_sorted_unique(data.get("rejection_reasons", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_intent_batch_result(result)
    return result


def paper_fill_to_dict(fill: PaperFill) -> dict:
    _validate_paper_fill(fill)
    return {
        "fill_id": fill.fill_id,
        "intent_id": fill.intent_id,
        "sleeve_id": fill.sleeve_id,
        "symbol": fill.symbol,
        "venue": fill.venue,
        "side": fill.side.value,
        "qty": fill.qty,
        "notional": fill.notional,
        "fill_price": fill.fill_price,
        "fill_ts_ns": fill.fill_ts_ns,
        "status": fill.status.value,
        "reason": fill.reason,
    }


def paper_fill_from_dict(data: dict) -> PaperFill:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper fill must be a dict, got {type(data).__name__!r}")
    fill = PaperFill(
        fill_id=_require_non_empty_str(data.get("fill_id"), "fill_id"),
        intent_id=_require_non_empty_str(data.get("intent_id"), "intent_id"),
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        side=_paper_intent_side_from_value(data.get("side")),
        qty=_optional_float(data.get("qty"), "qty"),
        notional=_optional_float(data.get("notional"), "notional"),
        fill_price=_optional_non_negative_float(data.get("fill_price"), "fill_price"),
        fill_ts_ns=_require_non_negative_int(data.get("fill_ts_ns"), "fill_ts_ns"),
        status=_paper_fill_status_from_value(data.get("status")),
        reason=_require_non_empty_str(data.get("reason"), "reason"),
    )
    _validate_paper_fill(fill)
    return fill


def paper_fill_simulation_result_to_dict(result: PaperFillSimulationResult) -> dict:
    _validate_paper_fill_simulation_result(result)
    return {
        "simulation_id": result.simulation_id,
        "session_id": result.session_id,
        "as_of_ns": result.as_of_ns,
        "intent_batch_id": result.intent_batch_id,
        "fills": [paper_fill_to_dict(fill) for fill in result.fills],
        "fill_attempts": result.fill_attempts,
        "simulated_fills": result.simulated_fills,
        "rejected_fills": result.rejected_fills,
        "symbols_filled": list(result.symbols_filled),
        "sleeves_filled": list(result.sleeves_filled),
        "rejection_reasons": list(result.rejection_reasons),
        "paper_only": result.paper_only,
        "real_orders_enabled": result.real_orders_enabled,
        "real_money_enabled": result.real_money_enabled,
        "operator_summary": result.operator_summary,
    }


def paper_fill_simulation_result_from_dict(data: dict) -> PaperFillSimulationResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper fill simulation result must be a dict, got {type(data).__name__!r}"
        )
    fills_value = data.get("fills")
    if not isinstance(fills_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper fill simulation result field 'fills' must be a list/tuple")
    result = PaperFillSimulationResult(
        simulation_id=_require_non_empty_str(data.get("simulation_id"), "simulation_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        intent_batch_id=_require_non_empty_str(data.get("intent_batch_id"), "intent_batch_id"),
        fills=tuple(paper_fill_from_dict(_dict_value(item, "fills")) for item in fills_value),
        fill_attempts=_require_non_negative_int(data.get("fill_attempts"), "fill_attempts"),
        simulated_fills=_require_non_negative_int(data.get("simulated_fills"), "simulated_fills"),
        rejected_fills=_require_non_negative_int(data.get("rejected_fills"), "rejected_fills"),
        symbols_filled=_sorted_unique(data.get("symbols_filled", ())),
        sleeves_filled=_sorted_unique(data.get("sleeves_filled", ())),
        rejection_reasons=_sorted_unique(data.get("rejection_reasons", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_fill_simulation_result(result)
    return result


def paper_cost_model_to_dict(model: PaperCostModel) -> dict:
    _validate_paper_cost_model(model)
    return {
        "fee_bps": model.fee_bps,
        "slippage_bps": model.slippage_bps,
        "min_fee": model.min_fee,
        "reject_if_cost_exceeds_bps": model.reject_if_cost_exceeds_bps,
        "partial_fill_ratio": model.partial_fill_ratio,
    }


def paper_cost_model_from_dict(data: dict | None) -> PaperCostModel:
    if data is None:
        return PaperCostModel()
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper cost model must be a dict, got {type(data).__name__!r}")
    model = PaperCostModel(
        fee_bps=_require_non_negative_float(data.get("fee_bps", 0.0), "fee_bps"),
        slippage_bps=_require_non_negative_float(data.get("slippage_bps", 0.0), "slippage_bps"),
        min_fee=_require_non_negative_float(data.get("min_fee", 0.0), "min_fee"),
        reject_if_cost_exceeds_bps=_optional_non_negative_float(
            data.get("reject_if_cost_exceeds_bps"),
            "reject_if_cost_exceeds_bps",
        ),
        partial_fill_ratio=_require_non_negative_float(data.get("partial_fill_ratio", 1.0), "partial_fill_ratio"),
    )
    _validate_paper_cost_model(model)
    return model


def paper_cost_line_to_dict(line: PaperCostLine) -> dict:
    _validate_paper_cost_line(line)
    return {
        "fill_id": line.fill_id,
        "intent_id": line.intent_id,
        "sleeve_id": line.sleeve_id,
        "symbol": line.symbol,
        "venue": line.venue,
        "side": line.side.value,
        "gross_notional": line.gross_notional,
        "fee": line.fee,
        "slippage_cost": line.slippage_cost,
        "net_notional": line.net_notional,
        "effective_price": line.effective_price,
        "cost_bps": line.cost_bps,
        "status": line.status.value,
        "reasons": list(line.reasons),
        "qty": line.qty,
        "fill_price": line.fill_price,
        "fill_ts_ns": line.fill_ts_ns,
    }


def paper_cost_line_from_dict(data: dict) -> PaperCostLine:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper cost line must be a dict, got {type(data).__name__!r}")
    line = PaperCostLine(
        fill_id=_require_non_empty_str(data.get("fill_id"), "fill_id"),
        intent_id=_require_non_empty_str(data.get("intent_id"), "intent_id"),
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        side=_paper_intent_side_from_value(data.get("side")),
        gross_notional=_require_non_negative_float(data.get("gross_notional"), "gross_notional"),
        fee=_require_non_negative_float(data.get("fee"), "fee"),
        slippage_cost=_require_non_negative_float(data.get("slippage_cost"), "slippage_cost"),
        net_notional=_require_non_negative_float(data.get("net_notional"), "net_notional"),
        effective_price=_optional_non_negative_float(data.get("effective_price"), "effective_price"),
        cost_bps=_require_non_negative_float(data.get("cost_bps"), "cost_bps"),
        status=_paper_cost_status_from_value(data.get("status")),
        reasons=_sorted_unique(data.get("reasons", ())),
        qty=_require_non_negative_float(data.get("qty", 0.0), "qty"),
        fill_price=_optional_non_negative_float(data.get("fill_price"), "fill_price"),
        fill_ts_ns=_require_non_negative_int(data.get("fill_ts_ns", 0), "fill_ts_ns"),
    )
    _validate_paper_cost_line(line)
    return line


def paper_cost_result_to_dict(result: PaperCostResult) -> dict:
    _validate_paper_cost_result(result)
    return {
        "cost_result_id": result.cost_result_id,
        "session_id": result.session_id,
        "as_of_ns": result.as_of_ns,
        "source_fill_simulation_id": result.source_fill_simulation_id,
        "cost_model": paper_cost_model_to_dict(result.cost_model),
        "costs": [paper_cost_line_to_dict(line) for line in result.costs],
        "cost_evaluations": result.cost_evaluations,
        "accepted_costs": result.accepted_costs,
        "rejected_costs": result.rejected_costs,
        "skipped_costs": result.skipped_costs,
        "gross_notional": result.gross_notional,
        "fee": result.fee,
        "slippage_cost": result.slippage_cost,
        "net_notional": result.net_notional,
        "effective_price": result.effective_price,
        "cost_bps": result.cost_bps,
        "status": result.status.value,
        "reasons": list(result.reasons),
        "total_fee": result.total_fee,
        "total_slippage_cost": result.total_slippage_cost,
        "paper_only": result.paper_only,
        "real_orders_enabled": result.real_orders_enabled,
        "real_money_enabled": result.real_money_enabled,
        "operator_summary": result.operator_summary,
    }


def paper_cost_result_from_dict(data: dict) -> PaperCostResult:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper cost result must be a dict, got {type(data).__name__!r}")
    costs_value = data.get("costs")
    if not isinstance(costs_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper cost result field 'costs' must be a list/tuple")
    result = PaperCostResult(
        cost_result_id=_require_non_empty_str(data.get("cost_result_id"), "cost_result_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        source_fill_simulation_id=_require_non_empty_str(
            data.get("source_fill_simulation_id"),
            "source_fill_simulation_id",
        ),
        cost_model=paper_cost_model_from_dict(_dict_value(data.get("cost_model"), "cost_model")),
        costs=tuple(paper_cost_line_from_dict(_dict_value(item, "costs")) for item in costs_value),
        cost_evaluations=_require_non_negative_int(data.get("cost_evaluations"), "cost_evaluations"),
        accepted_costs=_require_non_negative_int(data.get("accepted_costs"), "accepted_costs"),
        rejected_costs=_require_non_negative_int(data.get("rejected_costs"), "rejected_costs"),
        skipped_costs=_require_non_negative_int(data.get("skipped_costs"), "skipped_costs"),
        gross_notional=_require_non_negative_float(data.get("gross_notional"), "gross_notional"),
        fee=_require_non_negative_float(data.get("fee"), "fee"),
        slippage_cost=_require_non_negative_float(data.get("slippage_cost"), "slippage_cost"),
        net_notional=_require_non_negative_float(data.get("net_notional"), "net_notional"),
        effective_price=_optional_non_negative_float(data.get("effective_price"), "effective_price"),
        cost_bps=_require_non_negative_float(data.get("cost_bps"), "cost_bps"),
        status=_paper_cost_status_from_value(data.get("status")),
        reasons=_sorted_unique(data.get("reasons", ())),
        total_fee=_require_non_negative_float(data.get("total_fee", data.get("fee")), "total_fee"),
        total_slippage_cost=_require_non_negative_float(
            data.get("total_slippage_cost", data.get("slippage_cost")),
            "total_slippage_cost",
        ),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_cost_result(result)
    return result


def paper_position_to_dict(position: PaperPosition) -> dict:
    _validate_paper_position(position)
    return {
        "position_id": position.position_id,
        "sleeve_id": position.sleeve_id,
        "symbol": position.symbol,
        "venue": position.venue,
        "qty": position.qty,
        "avg_price": position.avg_price,
        "gross_notional": position.gross_notional,
        "fees": position.fees,
        "slippage_cost": position.slippage_cost,
        "realized_pnl": position.realized_pnl,
        "unrealized_pnl": position.unrealized_pnl,
        "last_price": position.last_price,
        "is_open": position.is_open,
    }


def paper_position_from_dict(data: dict) -> PaperPosition:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper position must be a dict, got {type(data).__name__!r}")
    position = PaperPosition(
        position_id=_require_non_empty_str(data.get("position_id"), "position_id"),
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        qty=_require_non_negative_float(data.get("qty"), "qty"),
        avg_price=_optional_non_negative_float(data.get("avg_price"), "avg_price"),
        gross_notional=_require_non_negative_float(data.get("gross_notional"), "gross_notional"),
        fees=_require_non_negative_float(data.get("fees"), "fees"),
        slippage_cost=_require_non_negative_float(data.get("slippage_cost"), "slippage_cost"),
        realized_pnl=_require_float(data.get("realized_pnl"), "realized_pnl"),
        unrealized_pnl=_optional_float(data.get("unrealized_pnl"), "unrealized_pnl"),
        last_price=_optional_non_negative_float(data.get("last_price"), "last_price"),
        is_open=_bool_or_default(data, "is_open", False),
    )
    _validate_paper_position(position)
    return position


def paper_pnl_line_to_dict(line: PaperPnLLine) -> dict:
    _validate_paper_pnl_line(line)
    return {
        "line_id": line.line_id,
        "cost_result_id": line.cost_result_id,
        "fill_id": line.fill_id,
        "sleeve_id": line.sleeve_id,
        "symbol": line.symbol,
        "venue": line.venue,
        "side": line.side.value,
        "qty": line.qty,
        "price": line.price,
        "fee": line.fee,
        "slippage_cost": line.slippage_cost,
        "realized_pnl": line.realized_pnl,
        "position_qty_after": line.position_qty_after,
        "avg_price_after": line.avg_price_after,
        "status": line.status.value,
        "reasons": list(line.reasons),
    }


def paper_pnl_line_from_dict(data: dict) -> PaperPnLLine:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper PnL line must be a dict, got {type(data).__name__!r}")
    line = PaperPnLLine(
        line_id=_require_non_empty_str(data.get("line_id"), "line_id"),
        cost_result_id=_require_non_empty_str(data.get("cost_result_id"), "cost_result_id"),
        fill_id=_require_non_empty_str(data.get("fill_id"), "fill_id"),
        sleeve_id=_require_non_empty_str(data.get("sleeve_id"), "sleeve_id"),
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        side=_paper_intent_side_from_value(data.get("side")),
        qty=_require_non_negative_float(data.get("qty"), "qty"),
        price=_optional_non_negative_float(data.get("price"), "price"),
        fee=_require_non_negative_float(data.get("fee"), "fee"),
        slippage_cost=_require_non_negative_float(data.get("slippage_cost"), "slippage_cost"),
        realized_pnl=_require_float(data.get("realized_pnl"), "realized_pnl"),
        position_qty_after=_require_non_negative_float(data.get("position_qty_after"), "position_qty_after"),
        avg_price_after=_optional_non_negative_float(data.get("avg_price_after"), "avg_price_after"),
        status=_paper_pnl_status_from_value(data.get("status")),
        reasons=_sorted_unique(data.get("reasons", ())),
    )
    _validate_paper_pnl_line(line)
    return line


def paper_pnl_ledger_to_dict(ledger: PaperPnLLedger) -> dict:
    _validate_paper_pnl_ledger(ledger)
    return {
        "ledger_id": ledger.ledger_id,
        "session_id": ledger.session_id,
        "as_of_ns": ledger.as_of_ns,
        "source_cost_result_id": ledger.source_cost_result_id,
        "positions": [paper_position_to_dict(position) for position in ledger.positions],
        "pnl_lines": [paper_pnl_line_to_dict(line) for line in ledger.pnl_lines],
        "pnl_events": ledger.pnl_events,
        "open_positions": ledger.open_positions,
        "closed_positions": ledger.closed_positions,
        "total_fees": ledger.total_fees,
        "total_slippage": ledger.total_slippage,
        "realized_pnl": ledger.realized_pnl,
        "unrealized_pnl": ledger.unrealized_pnl,
        "status": ledger.status.value,
        "reasons": list(ledger.reasons),
        "paper_only": ledger.paper_only,
        "real_orders_enabled": ledger.real_orders_enabled,
        "real_money_enabled": ledger.real_money_enabled,
        "operator_summary": ledger.operator_summary,
    }


def paper_pnl_ledger_from_dict(data: dict) -> PaperPnLLedger:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper PnL ledger must be a dict, got {type(data).__name__!r}")
    positions_value = data.get("positions")
    pnl_lines_value = data.get("pnl_lines")
    if not isinstance(positions_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper PnL ledger field 'positions' must be a list/tuple")
    if not isinstance(pnl_lines_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper PnL ledger field 'pnl_lines' must be a list/tuple")
    ledger = PaperPnLLedger(
        ledger_id=_require_non_empty_str(data.get("ledger_id"), "ledger_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        source_cost_result_id=_require_non_empty_str(data.get("source_cost_result_id"), "source_cost_result_id"),
        positions=tuple(paper_position_from_dict(_dict_value(item, "positions")) for item in positions_value),
        pnl_lines=tuple(paper_pnl_line_from_dict(_dict_value(item, "pnl_lines")) for item in pnl_lines_value),
        pnl_events=_require_non_negative_int(data.get("pnl_events"), "pnl_events"),
        open_positions=_require_non_negative_int(data.get("open_positions"), "open_positions"),
        closed_positions=_require_non_negative_int(data.get("closed_positions"), "closed_positions"),
        total_fees=_require_non_negative_float(data.get("total_fees"), "total_fees"),
        total_slippage=_require_non_negative_float(data.get("total_slippage"), "total_slippage"),
        realized_pnl=_require_float(data.get("realized_pnl"), "realized_pnl"),
        unrealized_pnl=_optional_float(data.get("unrealized_pnl"), "unrealized_pnl"),
        status=_paper_pnl_status_from_value(data.get("status")),
        reasons=_sorted_unique(data.get("reasons", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_pnl_ledger(ledger)
    return ledger


def paper_portfolio_exposure_to_dict(exposure: PaperPortfolioExposure) -> dict:
    _validate_paper_portfolio_exposure(exposure)
    return {
        "exposure_id": exposure.exposure_id,
        "dimension": exposure.dimension,
        "key": exposure.key,
        "gross_exposure": exposure.gross_exposure,
        "net_exposure": exposure.net_exposure,
        "open_position_count": exposure.open_position_count,
    }


def paper_portfolio_exposure_from_dict(data: dict) -> PaperPortfolioExposure:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper portfolio exposure must be a dict, got {type(data).__name__!r}")
    exposure = PaperPortfolioExposure(
        exposure_id=_require_non_empty_str(data.get("exposure_id"), "exposure_id"),
        dimension=_require_non_empty_str(data.get("dimension"), "dimension"),
        key=_require_non_empty_str(data.get("key"), "key"),
        gross_exposure=_require_non_negative_float(data.get("gross_exposure"), "gross_exposure"),
        net_exposure=_require_non_negative_float(data.get("net_exposure"), "net_exposure"),
        open_position_count=_require_non_negative_int(data.get("open_position_count"), "open_position_count"),
    )
    _validate_paper_portfolio_exposure(exposure)
    return exposure


def paper_portfolio_risk_snapshot_to_dict(snapshot: PaperPortfolioRiskSnapshot) -> dict:
    _validate_paper_portfolio_risk_snapshot(snapshot)
    return {
        "snapshot_id": snapshot.snapshot_id,
        "session_id": snapshot.session_id,
        "as_of_ns": snapshot.as_of_ns,
        "source_ledger_id": snapshot.source_ledger_id,
        "equity_start": snapshot.equity_start,
        "equity_current": snapshot.equity_current,
        "realized_pnl": snapshot.realized_pnl,
        "unrealized_pnl": snapshot.unrealized_pnl,
        "total_fees": snapshot.total_fees,
        "total_slippage": snapshot.total_slippage,
        "gross_exposure": snapshot.gross_exposure,
        "net_exposure": snapshot.net_exposure,
        "open_position_count": snapshot.open_position_count,
        "sleeve_exposures": [paper_portfolio_exposure_to_dict(item) for item in snapshot.sleeve_exposures],
        "symbol_exposures": [paper_portfolio_exposure_to_dict(item) for item in snapshot.symbol_exposures],
        "missing_price_positions": list(snapshot.missing_price_positions),
        "drawdown_available": snapshot.drawdown_available,
        "current_drawdown": snapshot.current_drawdown,
        "max_drawdown": snapshot.max_drawdown,
        "status": snapshot.status.value,
        "reasons": list(snapshot.reasons),
        "paper_only": snapshot.paper_only,
        "real_orders_enabled": snapshot.real_orders_enabled,
        "real_money_enabled": snapshot.real_money_enabled,
        "operator_summary": snapshot.operator_summary,
    }


def paper_portfolio_risk_snapshot_from_dict(data: dict) -> PaperPortfolioRiskSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper portfolio risk snapshot must be a dict, got {type(data).__name__!r}"
        )
    sleeve_exposures_value = data.get("sleeve_exposures")
    symbol_exposures_value = data.get("symbol_exposures")
    if not isinstance(sleeve_exposures_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper portfolio risk sleeve_exposures must be a list/tuple")
    if not isinstance(symbol_exposures_value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper portfolio risk symbol_exposures must be a list/tuple")
    snapshot = PaperPortfolioRiskSnapshot(
        snapshot_id=_require_non_empty_str(data.get("snapshot_id"), "snapshot_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        source_ledger_id=_require_non_empty_str(data.get("source_ledger_id"), "source_ledger_id"),
        equity_start=_optional_non_negative_float(data.get("equity_start"), "equity_start"),
        equity_current=_optional_non_negative_float(data.get("equity_current"), "equity_current"),
        realized_pnl=_require_float(data.get("realized_pnl"), "realized_pnl"),
        unrealized_pnl=_optional_float(data.get("unrealized_pnl"), "unrealized_pnl"),
        total_fees=_require_non_negative_float(data.get("total_fees"), "total_fees"),
        total_slippage=_require_non_negative_float(data.get("total_slippage"), "total_slippage"),
        gross_exposure=_require_non_negative_float(data.get("gross_exposure"), "gross_exposure"),
        net_exposure=_require_non_negative_float(data.get("net_exposure"), "net_exposure"),
        open_position_count=_require_non_negative_int(data.get("open_position_count"), "open_position_count"),
        sleeve_exposures=tuple(
            paper_portfolio_exposure_from_dict(_dict_value(item, "sleeve_exposures")) for item in sleeve_exposures_value
        ),
        symbol_exposures=tuple(
            paper_portfolio_exposure_from_dict(_dict_value(item, "symbol_exposures")) for item in symbol_exposures_value
        ),
        missing_price_positions=_sorted_unique(data.get("missing_price_positions", ())),
        drawdown_available=_bool_or_default(data, "drawdown_available", False),
        current_drawdown=_optional_non_negative_float(data.get("current_drawdown"), "current_drawdown"),
        max_drawdown=_optional_non_negative_float(data.get("max_drawdown"), "max_drawdown"),
        status=_paper_portfolio_risk_status_from_value(data.get("status")),
        reasons=_sorted_unique(data.get("reasons", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_portfolio_risk_snapshot(snapshot)
    return snapshot


def paper_risk_limit_policy_to_dict(policy: PaperRiskLimitPolicy) -> dict:
    _validate_paper_risk_limit_policy(policy)
    return {
        "policy_id": policy.policy_id,
        "max_gross_exposure": policy.max_gross_exposure,
        "max_net_exposure": policy.max_net_exposure,
        "max_open_positions": policy.max_open_positions,
        "max_unrealized_loss": policy.max_unrealized_loss,
        "max_total_loss": policy.max_total_loss,
        "require_complete_prices": policy.require_complete_prices,
    }


def paper_risk_limit_policy_from_dict(data: dict) -> PaperRiskLimitPolicy:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper risk limit policy must be a dict, got {type(data).__name__!r}")
    policy = PaperRiskLimitPolicy(
        policy_id=_require_non_empty_str(data.get("policy_id", "default-paper-risk-limit-policy"), "policy_id"),
        max_gross_exposure=_optional_non_negative_float(data.get("max_gross_exposure"), "max_gross_exposure"),
        max_net_exposure=_optional_non_negative_float(data.get("max_net_exposure"), "max_net_exposure"),
        max_open_positions=_optional_non_negative_int(data.get("max_open_positions"), "max_open_positions"),
        max_unrealized_loss=_optional_non_negative_float(data.get("max_unrealized_loss"), "max_unrealized_loss"),
        max_total_loss=_optional_non_negative_float(data.get("max_total_loss"), "max_total_loss"),
        require_complete_prices=_bool_or_default(data, "require_complete_prices", True),
    )
    _validate_paper_risk_limit_policy(policy)
    return policy


def paper_risk_limit_decision_to_dict(decision: PaperRiskLimitDecision) -> dict:
    _validate_paper_risk_limit_decision(decision)
    return {
        "decision_id": decision.decision_id,
        "session_id": decision.session_id,
        "as_of_ns": decision.as_of_ns,
        "source_risk_snapshot_id": decision.source_risk_snapshot_id,
        "policy": paper_risk_limit_policy_to_dict(decision.policy),
        "status": decision.status.value,
        "passed": decision.passed,
        "block_new_intents": decision.block_new_intents,
        "stop_session": decision.stop_session,
        "breached_limits": list(decision.breached_limits),
        "reasons": list(decision.reasons),
        "paper_only": decision.paper_only,
        "real_orders_enabled": decision.real_orders_enabled,
        "real_money_enabled": decision.real_money_enabled,
        "operator_summary": decision.operator_summary,
    }


def paper_risk_limit_decision_from_dict(data: dict) -> PaperRiskLimitDecision:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Paper risk limit decision must be a dict, got {type(data).__name__!r}")
    decision = PaperRiskLimitDecision(
        decision_id=_require_non_empty_str(data.get("decision_id"), "decision_id"),
        session_id=_require_non_empty_str(data.get("session_id"), "session_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        source_risk_snapshot_id=_require_non_empty_str(
            data.get("source_risk_snapshot_id"),
            "source_risk_snapshot_id",
        ),
        policy=paper_risk_limit_policy_from_dict(_dict_value(data.get("policy"), "policy")),
        status=_paper_risk_limit_decision_status_from_value(data.get("status")),
        passed=_bool_or_default(data, "passed", False),
        block_new_intents=_bool_or_default(data, "block_new_intents", True),
        stop_session=_bool_or_default(data, "stop_session", False),
        breached_limits=_sorted_unique(data.get("breached_limits", ())),
        reasons=_sorted_unique(data.get("reasons", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_risk_limit_decision(decision)
    return decision


def build_paper_pnl_ledger(
    *,
    cost_result: PaperCostResult | dict,
    latest_prices: tuple[MarketEventPrice, ...] = (),
    prior_ledger: PaperPnLLedger | dict | None = None,
    ledger_id: str | None = None,
    as_of_ns: int | None = None,
) -> PaperPnLLedger:
    """Build a deterministic long-only paper position/PnL ledger from paper costs."""
    resolved_cost = paper_cost_result_from_dict(cost_result) if isinstance(cost_result, dict) else cost_result
    _validate_paper_cost_result(resolved_cost)
    resolved_prior = paper_pnl_ledger_from_dict(prior_ledger) if isinstance(prior_ledger, dict) else prior_ledger
    if resolved_prior is not None:
        _validate_paper_pnl_ledger(resolved_prior)
        if resolved_prior.session_id != resolved_cost.session_id:
            raise PaperShadowSessionCorruptError("paper PnL prior ledger session must match cost result")
    prices = _market_event_prices_from_data(tuple(market_event_price_to_dict(price) for price in latest_prices))
    positions_by_key = {
        _paper_position_key(position.sleeve_id, position.symbol, position.venue): position
        for position in (resolved_prior.positions if resolved_prior is not None else ())
    }
    pnl_lines: list[PaperPnLLine] = list(resolved_prior.pnl_lines if resolved_prior is not None else ())
    for line in resolved_cost.costs:
        pnl_line, updated_position = _paper_pnl_line_for_cost(resolved_cost, line, positions_by_key)
        pnl_lines.append(pnl_line)
        if updated_position is not None:
            positions_by_key[_paper_position_key(line.sleeve_id, line.symbol, line.venue)] = updated_position
    priced_positions = tuple(
        _paper_position_with_unrealized(position, prices)
        for position in sorted(positions_by_key.values(), key=_paper_position_sort_key)
    )
    resolved_lines = tuple(sorted(pnl_lines, key=_paper_pnl_line_sort_key))
    pnl_events = sum(1 for line in resolved_lines if line.status == PaperPnLStatus.APPLIED)
    open_positions = sum(1 for position in priced_positions if position.is_open)
    closed_positions = sum(1 for position in priced_positions if not position.is_open)
    total_fees = sum(position.fees for position in priced_positions)
    total_slippage = sum(position.slippage_cost for position in priced_positions)
    realized_pnl = sum(position.realized_pnl for position in priced_positions)
    unrealized_values = tuple(
        position.unrealized_pnl for position in priced_positions if position.unrealized_pnl is not None
    )
    unrealized_pnl = sum(unrealized_values) if unrealized_values else None
    status = _paper_pnl_ledger_status(resolved_lines)
    reasons = _paper_pnl_ledger_reasons(resolved_lines, status)
    ledger = PaperPnLLedger(
        ledger_id=_string_or_default(ledger_id, _paper_pnl_ledger_id(resolved_cost.cost_result_id, resolved_lines)),
        session_id=resolved_cost.session_id,
        as_of_ns=_optional_non_negative_int(as_of_ns, "as_of_ns") if as_of_ns is not None else resolved_cost.as_of_ns,
        source_cost_result_id=resolved_cost.cost_result_id,
        positions=priced_positions,
        pnl_lines=resolved_lines,
        pnl_events=pnl_events,
        open_positions=open_positions,
        closed_positions=closed_positions,
        total_fees=total_fees,
        total_slippage=total_slippage,
        realized_pnl=realized_pnl,
        unrealized_pnl=unrealized_pnl,
        status=status,
        reasons=reasons,
        paper_only=resolved_cost.paper_only,
        real_orders_enabled=resolved_cost.real_orders_enabled,
        real_money_enabled=resolved_cost.real_money_enabled,
        operator_summary=_paper_pnl_summary(status, pnl_events, open_positions, closed_positions, realized_pnl),
    )
    _validate_paper_pnl_ledger(ledger)
    return ledger


def build_paper_portfolio_risk_snapshot(
    *,
    ledger: PaperPnLLedger | dict,
    latest_prices: tuple[MarketEventPrice, ...] = (),
    equity_start: float | None = None,
    equity_history: tuple[float, ...] = (),
    snapshot_id: str | None = None,
    as_of_ns: int | None = None,
) -> PaperPortfolioRiskSnapshot:
    """Build a deterministic paper portfolio risk/equity snapshot from the PnL ledger."""
    resolved_ledger = paper_pnl_ledger_from_dict(ledger) if isinstance(ledger, dict) else ledger
    _validate_paper_pnl_ledger(resolved_ledger)
    prices = _market_event_prices_from_data(tuple(market_event_price_to_dict(price) for price in latest_prices))
    resolved_equity_start = _optional_non_negative_float(equity_start, "equity_start")
    resolved_equity_history = _equity_history_from_data(equity_history)
    open_positions = tuple(position for position in resolved_ledger.positions if position.is_open)
    priced_values: list[tuple[PaperPosition, MarketEventPrice, float, float]] = []
    missing_price_positions: list[str] = []
    unrealized_parts: list[float] = []
    for position in open_positions:
        latest = _latest_market_price_from_prices(prices, position.symbol, position.venue)
        if latest is None:
            missing_price_positions.append(position.position_id)
            continue
        exposure = position.qty * latest.price
        unrealized = 0.0 if position.avg_price is None else (latest.price - position.avg_price) * position.qty
        priced_values.append((position, latest, exposure, unrealized))
        unrealized_parts.append(unrealized)
    missing_positions = _sorted_unique(tuple(missing_price_positions))
    gross_exposure = sum(exposure for _, _, exposure, _ in priced_values)
    net_exposure = gross_exposure
    unrealized_pnl = None if missing_positions else sum(unrealized_parts)
    equity_current = (
        None
        if resolved_equity_start is None or unrealized_pnl is None
        else resolved_equity_start + resolved_ledger.realized_pnl + unrealized_pnl
    )
    drawdown_available, current_drawdown, max_drawdown = _paper_drawdown_from_equity_history(
        resolved_equity_history,
        equity_current,
    )
    sleeve_exposures = _paper_portfolio_exposures("sleeve", priced_values)
    symbol_exposures = _paper_portfolio_exposures("symbol", priced_values)
    status = _paper_portfolio_risk_status(resolved_ledger, missing_positions)
    reasons = _paper_portfolio_risk_reasons(resolved_ledger, missing_positions, resolved_equity_history)
    snapshot = PaperPortfolioRiskSnapshot(
        snapshot_id=_string_or_default(snapshot_id, _paper_portfolio_risk_snapshot_id(resolved_ledger.ledger_id)),
        session_id=resolved_ledger.session_id,
        as_of_ns=_optional_non_negative_int(as_of_ns, "as_of_ns") if as_of_ns is not None else resolved_ledger.as_of_ns,
        source_ledger_id=resolved_ledger.ledger_id,
        equity_start=resolved_equity_start,
        equity_current=equity_current,
        realized_pnl=resolved_ledger.realized_pnl,
        unrealized_pnl=unrealized_pnl,
        total_fees=resolved_ledger.total_fees,
        total_slippage=resolved_ledger.total_slippage,
        gross_exposure=gross_exposure,
        net_exposure=net_exposure,
        open_position_count=len(open_positions),
        sleeve_exposures=sleeve_exposures,
        symbol_exposures=symbol_exposures,
        missing_price_positions=missing_positions,
        drawdown_available=drawdown_available,
        current_drawdown=current_drawdown,
        max_drawdown=max_drawdown,
        status=status,
        reasons=reasons,
        paper_only=resolved_ledger.paper_only,
        real_orders_enabled=resolved_ledger.real_orders_enabled,
        real_money_enabled=resolved_ledger.real_money_enabled,
        operator_summary=_paper_portfolio_risk_summary(
            status,
            len(open_positions),
            gross_exposure,
            resolved_ledger.realized_pnl,
            unrealized_pnl,
        ),
    )
    _validate_paper_portfolio_risk_snapshot(snapshot)
    return snapshot


def build_paper_risk_limit_decision(
    *,
    risk_snapshot: PaperPortfolioRiskSnapshot | dict,
    policy: PaperRiskLimitPolicy | dict | None = None,
    decision_id: str | None = None,
    as_of_ns: int | None = None,
) -> PaperRiskLimitDecision:
    """Build deterministic paper risk-limit and kill-switch decision from a risk snapshot."""
    resolved_risk = (
        paper_portfolio_risk_snapshot_from_dict(risk_snapshot) if isinstance(risk_snapshot, dict) else risk_snapshot
    )
    _validate_paper_portfolio_risk_snapshot(resolved_risk)
    resolved_policy = _paper_risk_limit_policy_from_value(policy)
    breaches = _paper_risk_limit_breaches(resolved_risk, resolved_policy)
    reasons = _paper_risk_limit_reasons(resolved_risk, breaches)
    status = _paper_risk_limit_decision_status(breaches, reasons)
    decision = PaperRiskLimitDecision(
        decision_id=_string_or_default(
            decision_id,
            _paper_risk_limit_decision_id(resolved_risk.snapshot_id, resolved_policy.policy_id),
        ),
        session_id=resolved_risk.session_id,
        as_of_ns=_optional_non_negative_int(as_of_ns, "as_of_ns") if as_of_ns is not None else resolved_risk.as_of_ns,
        source_risk_snapshot_id=resolved_risk.snapshot_id,
        policy=resolved_policy,
        status=status,
        passed=status == PaperRiskLimitDecisionStatus.PASS,
        block_new_intents=status
        in {
            PaperRiskLimitDecisionStatus.BLOCK_NEW_INTENTS,
            PaperRiskLimitDecisionStatus.STOP_SESSION,
        },
        stop_session=status == PaperRiskLimitDecisionStatus.STOP_SESSION,
        breached_limits=breaches,
        reasons=reasons,
        paper_only=resolved_risk.paper_only,
        real_orders_enabled=resolved_risk.real_orders_enabled,
        real_money_enabled=resolved_risk.real_money_enabled,
        operator_summary=_paper_risk_limit_decision_summary(status, breaches, reasons),
    )
    _validate_paper_risk_limit_decision(decision)
    return decision


def build_paper_shadow_run_evidence_report(
    *,
    session_snapshot: PaperShadowSessionSnapshot | dict | None,
    source_result: PaperDataSourceBatchResult | dict | None = None,
    replay_result: FeedReplayResult | dict | None = None,
    report_id: str | None = None,
    as_of_ns: int | None = None,
) -> PaperShadowRunEvidenceReport:
    """Build one deterministic run-level evidence report from existing surfaces."""
    resolved_source = (
        paper_data_source_batch_result_from_dict(source_result) if isinstance(source_result, dict) else source_result
    )
    resolved_replay = feed_replay_result_from_dict(replay_result) if isinstance(replay_result, dict) else replay_result
    if resolved_source is not None:
        _validate_paper_data_source_batch_result(resolved_source)
    if resolved_replay is not None:
        _validate_feed_replay_result(resolved_replay)

    if session_snapshot is None:
        resolved_as_of_ns = _optional_non_negative_int(as_of_ns, "as_of_ns") or 0
        report = PaperShadowRunEvidenceReport(
            report_id=_string_or_default(report_id, _run_evidence_report_id(None, resolved_source, resolved_replay)),
            as_of_ns=resolved_as_of_ns,
            source_summary=_paper_data_source_run_summary(resolved_source),
            replay_summary=_feed_replay_run_summary(resolved_replay),
            session_status=PaperShadowSessionStatus.FAILED,
            monitor_status=RuntimeMonitorStatus.NOT_READY,
            guardrail_status=GuardrailAction.BLOCK_FINALIZE,
            blockers=("missing_session_snapshot",),
            reason_codes=("missing_session_snapshot",),
            evidence_status=PaperShadowRunEvidenceStatus.INCONCLUSIVE,
            next_actions=("restore_session_snapshot",),
            operator_summary=_run_evidence_summary(
                PaperShadowRunEvidenceStatus.INCONCLUSIVE,
                accepted_event_count=0,
                rejected_event_count=0,
                blockers=("missing_session_snapshot",),
            ),
        )
        _validate_paper_shadow_run_evidence_report(report)
        return report

    resolved_session = (
        paper_shadow_session_snapshot_from_dict(session_snapshot)
        if isinstance(session_snapshot, dict)
        else session_snapshot
    )
    _validate_session_snapshot(resolved_session)
    accepted_event_count = (
        resolved_replay.events_replayed if resolved_replay is not None else resolved_session.event_count
    )
    accepted_batch_count = (
        resolved_replay.batches_replayed
        if resolved_replay is not None
        else resolved_source.source.batches_produced
        if resolved_source is not None
        else 0
    )
    rejected_batch_count = resolved_replay.batches_rejected if resolved_replay is not None else 0
    rejected_event_count = resolved_session.rejected_event_count + (
        resolved_source.source.rejected_records if resolved_source is not None else 0
    )
    source_summary = _paper_data_source_run_summary(resolved_source)
    replay_summary = _feed_replay_run_summary(resolved_replay)
    reason_codes = _run_evidence_reason_codes(
        resolved_session,
        source_available=resolved_source is not None,
        replay_available=resolved_replay is not None,
        accepted_event_count=accepted_event_count,
        rejected_event_count=rejected_event_count,
        rejected_batch_count=rejected_batch_count,
        source_rejected_record_ids=resolved_source.rejected_record_ids if resolved_source is not None else (),
        replay_rejected_batch_ids=resolved_replay.rejected_batch_ids if resolved_replay is not None else (),
    )
    blockers = _run_evidence_blockers(
        reason_codes,
        resolved_session,
        rejected_batch_count=rejected_batch_count,
        rejected_event_count=rejected_event_count,
    )
    evidence_status = _run_evidence_status(
        resolved_session,
        source_available=resolved_source is not None,
        replay_available=resolved_replay is not None,
        accepted_event_count=accepted_event_count,
        rejected_event_count=rejected_event_count,
        rejected_batch_count=rejected_batch_count,
    )
    next_actions = _run_evidence_next_actions(evidence_status, reason_codes)
    resolved_as_of_ns = (
        _optional_non_negative_int(as_of_ns, "as_of_ns") if as_of_ns is not None else resolved_session.as_of_ns
    )
    report = PaperShadowRunEvidenceReport(
        report_id=_string_or_default(
            report_id,
            _run_evidence_report_id(resolved_session, resolved_source, resolved_replay),
        ),
        as_of_ns=resolved_as_of_ns,
        source_summary=source_summary,
        replay_summary=replay_summary,
        session_status=resolved_session.status,
        monitor_status=resolved_session.runtime_monitor.status,
        guardrail_status=resolved_session.guardrail.primary_action,
        accepted_event_count=accepted_event_count,
        rejected_event_count=rejected_event_count,
        accepted_batch_count=accepted_batch_count,
        rejected_batch_count=rejected_batch_count,
        symbols=resolved_session.symbols_seen,
        venues=resolved_session.venues_seen,
        blockers=blockers,
        reason_codes=reason_codes,
        evidence_status=evidence_status,
        next_actions=next_actions,
        paper_only=resolved_session.paper_only,
        real_orders_enabled=resolved_session.real_orders_enabled,
        real_money_enabled=resolved_session.real_money_enabled,
        operator_summary=_run_evidence_summary(
            evidence_status,
            accepted_event_count=accepted_event_count,
            rejected_event_count=rejected_event_count,
            blockers=blockers,
        ),
    )
    _validate_paper_shadow_run_evidence_report(report)
    return report


def paper_shadow_run_evidence_report_to_dict(report: PaperShadowRunEvidenceReport) -> dict:
    _validate_paper_shadow_run_evidence_report(report)
    return {
        "report_id": report.report_id,
        "as_of_ns": report.as_of_ns,
        "source_summary": dict(report.source_summary),
        "replay_summary": dict(report.replay_summary),
        "session_status": report.session_status.value,
        "monitor_status": report.monitor_status.value,
        "guardrail_status": report.guardrail_status.value,
        "accepted_event_count": report.accepted_event_count,
        "rejected_event_count": report.rejected_event_count,
        "accepted_batch_count": report.accepted_batch_count,
        "rejected_batch_count": report.rejected_batch_count,
        "symbols": list(report.symbols),
        "venues": list(report.venues),
        "blockers": list(report.blockers),
        "reason_codes": list(report.reason_codes),
        "evidence_status": report.evidence_status.value,
        "next_actions": list(report.next_actions),
        "paper_only": report.paper_only,
        "real_orders_enabled": report.real_orders_enabled,
        "real_money_enabled": report.real_money_enabled,
        "operator_summary": report.operator_summary,
    }


def paper_shadow_run_evidence_report_from_dict(data: dict) -> PaperShadowRunEvidenceReport:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow run evidence report must be a dict, got {type(data).__name__!r}"
        )
    report = PaperShadowRunEvidenceReport(
        report_id=_require_non_empty_str(data.get("report_id"), "report_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        source_summary=_report_summary_from_data(data.get("source_summary"), "source_summary"),
        replay_summary=_report_summary_from_data(data.get("replay_summary"), "replay_summary"),
        session_status=_session_status_or_default(data.get("session_status"), PaperShadowSessionStatus.FAILED),
        monitor_status=_runtime_monitor_status_from_value(data.get("monitor_status")),
        guardrail_status=_guardrail_action_from_value(data.get("guardrail_status")),
        accepted_event_count=_require_non_negative_int(data.get("accepted_event_count"), "accepted_event_count"),
        rejected_event_count=_require_non_negative_int(data.get("rejected_event_count"), "rejected_event_count"),
        accepted_batch_count=_require_non_negative_int(data.get("accepted_batch_count"), "accepted_batch_count"),
        rejected_batch_count=_require_non_negative_int(data.get("rejected_batch_count"), "rejected_batch_count"),
        symbols=_sorted_unique(data.get("symbols", ())),
        venues=_sorted_unique(data.get("venues", ())),
        blockers=_sorted_unique(data.get("blockers", ())),
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
        evidence_status=_run_evidence_status_from_value(data.get("evidence_status")),
        next_actions=_sorted_unique(data.get("next_actions", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_shadow_run_evidence_report(report)
    return report


def build_multi_source_run_evidence_report(
    reports: tuple[PaperShadowRunEvidenceReport | dict, ...],
    *,
    aggregate_id: str | None = None,
    as_of_ns: int | None = None,
) -> MultiSourceRunEvidenceReport:
    """Aggregate multiple run-level evidence reports into one deterministic summary."""
    if not isinstance(reports, tuple):
        raise PaperShadowSessionCorruptError("multi-source run evidence reports must be a tuple")
    resolved_reports = tuple(
        paper_shadow_run_evidence_report_from_dict(report) if isinstance(report, dict) else report for report in reports
    )
    for report in resolved_reports:
        _validate_paper_shadow_run_evidence_report(report)
    _validate_unique_report_ids(resolved_reports)
    ordered_reports = tuple(sorted(resolved_reports, key=lambda report: report.report_id))
    report_ids = tuple(report.report_id for report in ordered_reports)
    status = _multi_source_run_evidence_status(ordered_reports)
    reason_codes = _multi_source_reason_codes(ordered_reports)
    blockers = _multi_source_blockers(ordered_reports, reason_codes)
    next_actions = _multi_source_next_actions(status, ordered_reports, reason_codes)
    guardrail_actions = _sorted_unique_actions(tuple(report.guardrail_status for report in ordered_reports))
    resolved_as_of_ns = (
        _optional_non_negative_int(as_of_ns, "as_of_ns")
        if as_of_ns is not None
        else max((report.as_of_ns for report in ordered_reports), default=0)
    )
    aggregate = MultiSourceRunEvidenceReport(
        aggregate_id=_string_or_default(aggregate_id, _multi_source_run_evidence_id(report_ids)),
        as_of_ns=resolved_as_of_ns,
        report_ids=report_ids,
        report_count=len(ordered_reports),
        pass_count=sum(1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.PASS),
        warn_count=sum(1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.WARN),
        blocked_count=sum(
            1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
        ),
        inconclusive_count=sum(
            1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.INCONCLUSIVE
        ),
        empty_count=sum(
            1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY
        ),
        accepted_event_count=sum(report.accepted_event_count for report in ordered_reports),
        rejected_event_count=sum(report.rejected_event_count for report in ordered_reports),
        accepted_batch_count=sum(report.accepted_batch_count for report in ordered_reports),
        rejected_batch_count=sum(report.rejected_batch_count for report in ordered_reports),
        symbols=_sorted_unique(tuple(symbol for report in ordered_reports for symbol in report.symbols)),
        venues=_sorted_unique(tuple(venue for report in ordered_reports for venue in report.venues)),
        blockers=blockers,
        reason_codes=reason_codes,
        guardrail_actions=guardrail_actions,
        evidence_status=status,
        next_actions=next_actions,
        paper_only=all(report.paper_only for report in ordered_reports) if ordered_reports else True,
        real_orders_enabled=any(report.real_orders_enabled for report in ordered_reports),
        real_money_enabled=any(report.real_money_enabled for report in ordered_reports),
        operator_summary=_multi_source_run_evidence_summary(
            status,
            report_count=len(ordered_reports),
            pass_count=sum(
                1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.PASS
            ),
            warn_count=sum(
                1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.WARN
            ),
            blocked_count=sum(
                1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED
            ),
            inconclusive_count=sum(
                1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.INCONCLUSIVE
            ),
            empty_count=sum(
                1 for report in ordered_reports if report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY
            ),
        ),
    )
    _validate_multi_source_run_evidence_report(aggregate)
    return aggregate


def multi_source_run_evidence_report_to_dict(report: MultiSourceRunEvidenceReport) -> dict:
    _validate_multi_source_run_evidence_report(report)
    return {
        "aggregate_id": report.aggregate_id,
        "as_of_ns": report.as_of_ns,
        "report_ids": list(report.report_ids),
        "report_count": report.report_count,
        "pass_count": report.pass_count,
        "warn_count": report.warn_count,
        "blocked_count": report.blocked_count,
        "inconclusive_count": report.inconclusive_count,
        "empty_count": report.empty_count,
        "accepted_event_count": report.accepted_event_count,
        "rejected_event_count": report.rejected_event_count,
        "accepted_batch_count": report.accepted_batch_count,
        "rejected_batch_count": report.rejected_batch_count,
        "symbols": list(report.symbols),
        "venues": list(report.venues),
        "blockers": list(report.blockers),
        "reason_codes": list(report.reason_codes),
        "guardrail_actions": [action.value for action in report.guardrail_actions],
        "evidence_status": report.evidence_status.value,
        "next_actions": list(report.next_actions),
        "paper_only": report.paper_only,
        "real_orders_enabled": report.real_orders_enabled,
        "real_money_enabled": report.real_money_enabled,
        "operator_summary": report.operator_summary,
    }


def multi_source_run_evidence_report_from_dict(data: dict) -> MultiSourceRunEvidenceReport:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Multi-source run evidence report must be a dict, got {type(data).__name__!r}"
        )
    report = MultiSourceRunEvidenceReport(
        aggregate_id=_require_non_empty_str(data.get("aggregate_id"), "aggregate_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        report_ids=_report_ids_from_data(data.get("report_ids", ())),
        report_count=_require_non_negative_int(data.get("report_count"), "report_count"),
        pass_count=_require_non_negative_int(data.get("pass_count"), "pass_count"),
        warn_count=_require_non_negative_int(data.get("warn_count"), "warn_count"),
        blocked_count=_require_non_negative_int(data.get("blocked_count"), "blocked_count"),
        inconclusive_count=_require_non_negative_int(data.get("inconclusive_count"), "inconclusive_count"),
        empty_count=_require_non_negative_int(data.get("empty_count"), "empty_count"),
        accepted_event_count=_require_non_negative_int(data.get("accepted_event_count"), "accepted_event_count"),
        rejected_event_count=_require_non_negative_int(data.get("rejected_event_count"), "rejected_event_count"),
        accepted_batch_count=_require_non_negative_int(data.get("accepted_batch_count"), "accepted_batch_count"),
        rejected_batch_count=_require_non_negative_int(data.get("rejected_batch_count"), "rejected_batch_count"),
        symbols=_sorted_unique(data.get("symbols", ())),
        venues=_sorted_unique(data.get("venues", ())),
        blockers=_sorted_unique(data.get("blockers", ())),
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
        guardrail_actions=_guardrail_actions_from_data(data.get("guardrail_actions", ())),
        evidence_status=_run_evidence_status_from_value(data.get("evidence_status")),
        next_actions=_sorted_unique(data.get("next_actions", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_multi_source_run_evidence_report(report)
    return report


def build_paper_shadow_evidence_bundle(
    *,
    aggregate_report: MultiSourceRunEvidenceReport | dict,
    run_reports: tuple[PaperShadowRunEvidenceReport | dict, ...],
    bundle_id: str | None = None,
    as_of_ns: int | None = None,
) -> PaperShadowEvidenceBundle:
    """Bundle a multi-source aggregate with its exact run-report drilldowns."""
    resolved_aggregate = (
        multi_source_run_evidence_report_from_dict(aggregate_report)
        if isinstance(aggregate_report, dict)
        else aggregate_report
    )
    _validate_multi_source_run_evidence_report(resolved_aggregate)
    if not isinstance(run_reports, tuple):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle run_reports must be a tuple")
    resolved_reports = tuple(
        paper_shadow_run_evidence_report_from_dict(report) if isinstance(report, dict) else report
        for report in run_reports
    )
    for report in resolved_reports:
        _validate_paper_shadow_run_evidence_report(report)
    ordered_reports = tuple(sorted(resolved_reports, key=lambda report: report.report_id))
    _validate_unique_report_ids(ordered_reports)
    nested_report_ids = tuple(report.report_id for report in ordered_reports)
    missing_report_ids = _evidence_bundle_missing_report_ids(resolved_aggregate, nested_report_ids)
    _ensure_no_unexpected_evidence_bundle_reports(resolved_aggregate, nested_report_ids)
    if not missing_report_ids:
        _assert_evidence_bundle_aggregate_matches_reports(resolved_aggregate, ordered_reports)

    status = _evidence_bundle_status(resolved_aggregate, missing_report_ids)
    reason_codes = _evidence_bundle_reason_codes(resolved_aggregate, missing_report_ids)
    blockers = _evidence_bundle_blockers(resolved_aggregate, missing_report_ids, reason_codes)
    next_actions = _evidence_bundle_next_actions(status, resolved_aggregate, missing_report_ids)
    bundle = PaperShadowEvidenceBundle(
        bundle_id=_string_or_default(bundle_id, _paper_shadow_evidence_bundle_id(resolved_aggregate)),
        as_of_ns=(
            _optional_non_negative_int(as_of_ns, "as_of_ns") if as_of_ns is not None else resolved_aggregate.as_of_ns
        ),
        aggregate_report=resolved_aggregate,
        run_reports=ordered_reports,
        report_ids=resolved_aggregate.report_ids,
        evidence_status=status,
        missing_report_ids=missing_report_ids,
        blockers=blockers,
        reason_codes=reason_codes,
        next_actions=next_actions,
        paper_only=resolved_aggregate.paper_only and all(report.paper_only for report in ordered_reports),
        real_orders_enabled=resolved_aggregate.real_orders_enabled
        or any(report.real_orders_enabled for report in ordered_reports),
        real_money_enabled=resolved_aggregate.real_money_enabled
        or any(report.real_money_enabled for report in ordered_reports),
        operator_summary=_paper_shadow_evidence_bundle_summary(
            status,
            aggregate_id=resolved_aggregate.aggregate_id,
            report_count=resolved_aggregate.report_count,
            missing_report_count=len(missing_report_ids),
            blocker_count=len(blockers),
        ),
    )
    _validate_paper_shadow_evidence_bundle(bundle)
    return bundle


def paper_shadow_evidence_bundle_to_dict(bundle: PaperShadowEvidenceBundle) -> dict:
    _validate_paper_shadow_evidence_bundle(bundle)
    return {
        "bundle_id": bundle.bundle_id,
        "as_of_ns": bundle.as_of_ns,
        "aggregate_report": multi_source_run_evidence_report_to_dict(bundle.aggregate_report),
        "run_reports": [paper_shadow_run_evidence_report_to_dict(report) for report in bundle.run_reports],
        "report_ids": list(bundle.report_ids),
        "evidence_status": bundle.evidence_status.value,
        "missing_report_ids": list(bundle.missing_report_ids),
        "blockers": list(bundle.blockers),
        "reason_codes": list(bundle.reason_codes),
        "next_actions": list(bundle.next_actions),
        "paper_only": bundle.paper_only,
        "real_orders_enabled": bundle.real_orders_enabled,
        "real_money_enabled": bundle.real_money_enabled,
        "operator_summary": bundle.operator_summary,
    }


def paper_shadow_evidence_bundle_from_dict(data: dict) -> PaperShadowEvidenceBundle:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(
            f"Paper/shadow evidence bundle must be a dict, got {type(data).__name__!r}"
        )
    raw_reports = data.get("run_reports")
    if not isinstance(raw_reports, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle run_reports must be a list/tuple")
    bundle = PaperShadowEvidenceBundle(
        bundle_id=_require_non_empty_str(data.get("bundle_id"), "bundle_id"),
        as_of_ns=_require_non_negative_int(data.get("as_of_ns"), "as_of_ns"),
        aggregate_report=multi_source_run_evidence_report_from_dict(
            _dict_value(data.get("aggregate_report"), "aggregate_report")
        ),
        run_reports=tuple(
            paper_shadow_run_evidence_report_from_dict(_dict_value(report, "run_reports")) for report in raw_reports
        ),
        report_ids=_report_ids_from_data(data.get("report_ids", ())),
        evidence_status=_run_evidence_status_from_value(data.get("evidence_status")),
        missing_report_ids=_report_ids_from_data(data.get("missing_report_ids", ())),
        blockers=_sorted_unique(data.get("blockers", ())),
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
        next_actions=_sorted_unique(data.get("next_actions", ())),
        paper_only=_bool_or_default(data, "paper_only", True),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        operator_summary=_require_non_empty_str(data.get("operator_summary"), "operator_summary"),
    )
    _validate_paper_shadow_evidence_bundle(bundle)
    return bundle


def market_event_cursor_to_dict(cursor: MarketEventCursor) -> dict:
    _validate_market_event_cursor(cursor)
    return {
        "symbol": cursor.symbol,
        "venue": cursor.venue,
        "last_event_ns": cursor.last_event_ns,
    }


def market_event_cursor_from_dict(data: dict) -> MarketEventCursor:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event cursor must be a dict, got {type(data).__name__!r}")
    cursor = MarketEventCursor(
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        last_event_ns=_require_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
    )
    _validate_market_event_cursor(cursor)
    return cursor


def market_event_price_to_dict(price: MarketEventPrice) -> dict:
    _validate_market_event_price(price)
    return {
        "symbol": price.symbol,
        "venue": price.venue,
        "last_event_ns": price.last_event_ns,
        "price": price.price,
    }


def market_event_price_from_dict(data: dict) -> MarketEventPrice:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Market event price must be a dict, got {type(data).__name__!r}")
    price = MarketEventPrice(
        symbol=_require_non_empty_str(data.get("symbol"), "symbol"),
        venue=_require_non_empty_str(data.get("venue"), "venue"),
        last_event_ns=_require_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
        price=_require_non_negative_float(data.get("price"), "price"),
    )
    _validate_market_event_price(price)
    return price


def build_runtime_monitor_snapshot(
    *,
    event_count: int,
    monitored_symbols: tuple[str, ...],
    monitored_venues: tuple[str, ...],
    required_symbols: tuple[str, ...] = (),
    required_venues: tuple[str, ...] = (),
    price_validity_ok: bool | None = None,
    event_gap_count: int = 0,
    last_event_ns: int | None = None,
) -> RuntimeMonitorSnapshot:
    event_count = _require_non_negative_int(event_count, "event_count")
    monitored_symbols = _sorted_unique(monitored_symbols)
    monitored_venues = _sorted_unique(monitored_venues)
    required_symbols = _sorted_unique(required_symbols)
    required_venues = _sorted_unique(required_venues)
    event_gap_count = _require_non_negative_int(event_gap_count, "event_gap_count")
    last_event_ns = _optional_non_negative_int(last_event_ns, "last_event_ns")
    has_events = event_count > 0
    resolved_price_validity_ok = (
        has_events
        if price_validity_ok is None
        else _require_bool(
            price_validity_ok,
            "price_validity_ok",
        )
    )
    symbol_coverage_ok = has_events and (
        bool(monitored_symbols) if not required_symbols else set(required_symbols).issubset(set(monitored_symbols))
    )
    venue_coverage_ok = has_events and (
        bool(monitored_venues) if not required_venues else set(required_venues).issubset(set(monitored_venues))
    )
    stale_feed_detected = event_gap_count > 0
    reason_codes = _runtime_monitor_reason_codes(
        has_events=has_events,
        stale_feed_detected=stale_feed_detected,
        symbol_coverage_ok=symbol_coverage_ok,
        venue_coverage_ok=venue_coverage_ok,
        price_validity_ok=resolved_price_validity_ok,
    )
    if not has_events:
        status = RuntimeMonitorStatus.NOT_READY
    elif reason_codes:
        status = RuntimeMonitorStatus.DEGRADED
    else:
        status = RuntimeMonitorStatus.HEALTHY
    monitor = RuntimeMonitorSnapshot(
        status=status,
        event_count=event_count,
        stale_feed_detected=stale_feed_detected,
        symbol_coverage_ok=symbol_coverage_ok,
        venue_coverage_ok=venue_coverage_ok,
        price_validity_ok=resolved_price_validity_ok,
        event_gap_count=event_gap_count,
        last_event_ns=last_event_ns,
        monitored_symbols=monitored_symbols,
        monitored_venues=monitored_venues,
        required_symbols=required_symbols,
        required_venues=required_venues,
        reason_codes=reason_codes,
    )
    _validate_runtime_monitor_snapshot(monitor)
    return monitor


def runtime_monitor_snapshot_to_dict(monitor: RuntimeMonitorSnapshot) -> dict:
    _validate_runtime_monitor_snapshot(monitor)
    return {
        "status": monitor.status.value,
        "event_count": monitor.event_count,
        "stale_feed_detected": monitor.stale_feed_detected,
        "symbol_coverage_ok": monitor.symbol_coverage_ok,
        "venue_coverage_ok": monitor.venue_coverage_ok,
        "price_validity_ok": monitor.price_validity_ok,
        "event_gap_count": monitor.event_gap_count,
        "last_event_ns": monitor.last_event_ns,
        "monitored_symbols": list(monitor.monitored_symbols),
        "monitored_venues": list(monitor.monitored_venues),
        "required_symbols": list(monitor.required_symbols),
        "required_venues": list(monitor.required_venues),
        "reason_codes": list(monitor.reason_codes),
    }


def runtime_monitor_snapshot_from_dict(data: dict) -> RuntimeMonitorSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Runtime monitor must be a dict, got {type(data).__name__!r}")
    monitor = RuntimeMonitorSnapshot(
        status=_runtime_monitor_status_from_value(data.get("status")),
        event_count=_require_non_negative_int(data.get("event_count", 0), "event_count"),
        stale_feed_detected=_bool_or_default(data, "stale_feed_detected", False),
        symbol_coverage_ok=_bool_or_default(data, "symbol_coverage_ok", False),
        venue_coverage_ok=_bool_or_default(data, "venue_coverage_ok", False),
        price_validity_ok=_bool_or_default(data, "price_validity_ok", False),
        event_gap_count=_require_non_negative_int(data.get("event_gap_count", 0), "event_gap_count"),
        last_event_ns=_optional_non_negative_int(data.get("last_event_ns"), "last_event_ns"),
        monitored_symbols=_sorted_unique(data.get("monitored_symbols", ())),
        monitored_venues=_sorted_unique(data.get("monitored_venues", ())),
        required_symbols=_sorted_unique(data.get("required_symbols", ())),
        required_venues=_sorted_unique(data.get("required_venues", ())),
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
    )
    _validate_runtime_monitor_snapshot(monitor)
    return monitor


def build_guardrail_snapshot(
    monitor: RuntimeMonitorSnapshot,
    *,
    session_status: PaperShadowSessionStatus,
    rejected_event_count: int = 0,
    paper_only: bool = True,
    real_orders_enabled: bool = False,
    real_money_enabled: bool = False,
) -> GuardrailSnapshot:
    _validate_runtime_monitor_snapshot(monitor)
    if not isinstance(session_status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("guardrail session_status must be a PaperShadowSessionStatus")
    rejected_event_count = _require_non_negative_int(rejected_event_count, "rejected_event_count")
    paper_only = _require_bool(paper_only, "paper_only")
    real_orders_enabled = _require_bool(real_orders_enabled, "real_orders_enabled")
    real_money_enabled = _require_bool(real_money_enabled, "real_money_enabled")
    reasons: list[str] = []
    actions: list[GuardrailAction] = []
    if not paper_only or real_orders_enabled or real_money_enabled:
        reasons.append("unsafe_real_trading_flags")
        actions.extend((GuardrailAction.STOP_SESSION, GuardrailAction.BLOCK_FINALIZE))
    has_events = monitor.event_count > 0
    if not has_events:
        reasons.append("no_market_events")
        actions.extend((GuardrailAction.WARN, GuardrailAction.BLOCK_FINALIZE))
    if has_events and monitor.stale_feed_detected:
        reasons.append("stale_feed_detected")
        actions.extend((GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.symbol_coverage_ok:
        reasons.append("missing_symbol_coverage")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.venue_coverage_ok:
        reasons.append("missing_venue_coverage")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if has_events and not monitor.price_validity_ok:
        reasons.append("price_validity_failed")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if rejected_event_count > 0:
        reasons.append("rejected_market_events")
        actions.extend((GuardrailAction.WARN, GuardrailAction.PAUSE_SESSION, GuardrailAction.BLOCK_FINALIZE))
    if not actions:
        actions.append(GuardrailAction.NONE)
    resolved_actions = _sorted_unique_actions(actions)
    primary_action = _primary_guardrail_action(resolved_actions)
    guardrail = GuardrailSnapshot(
        primary_action=primary_action,
        actions=resolved_actions,
        reason_codes=_sorted_unique(reasons),
        monitor_status=monitor.status,
        block_finalize=GuardrailAction.BLOCK_FINALIZE in resolved_actions,
        should_pause_session=GuardrailAction.PAUSE_SESSION in resolved_actions,
        should_stop_session=GuardrailAction.STOP_SESSION in resolved_actions,
        real_orders_enabled=real_orders_enabled,
        real_money_enabled=real_money_enabled,
        paper_only=paper_only,
    )
    _validate_guardrail_snapshot(guardrail)
    return guardrail


def guardrail_snapshot_to_dict(guardrail: GuardrailSnapshot) -> dict:
    _validate_guardrail_snapshot(guardrail)
    return {
        "primary_action": guardrail.primary_action.value,
        "actions": [action.value for action in guardrail.actions],
        "reason_codes": list(guardrail.reason_codes),
        "monitor_status": guardrail.monitor_status.value,
        "block_finalize": guardrail.block_finalize,
        "should_pause_session": guardrail.should_pause_session,
        "should_stop_session": guardrail.should_stop_session,
        "real_orders_enabled": guardrail.real_orders_enabled,
        "real_money_enabled": guardrail.real_money_enabled,
        "paper_only": guardrail.paper_only,
    }


def guardrail_snapshot_from_dict(data: dict) -> GuardrailSnapshot:
    if not isinstance(data, dict):
        raise PaperShadowSessionCorruptError(f"Guardrail snapshot must be a dict, got {type(data).__name__!r}")
    actions = _guardrail_actions_from_data(data.get("actions", ()))
    primary_action = _guardrail_action_from_value(data.get("primary_action", _primary_guardrail_action(actions).value))
    guardrail = GuardrailSnapshot(
        primary_action=primary_action,
        actions=actions,
        reason_codes=_sorted_unique(data.get("reason_codes", ())),
        monitor_status=_runtime_monitor_status_from_value(data.get("monitor_status")),
        block_finalize=_bool_or_default(data, "block_finalize", GuardrailAction.BLOCK_FINALIZE in actions),
        should_pause_session=_bool_or_default(data, "should_pause_session", GuardrailAction.PAUSE_SESSION in actions),
        should_stop_session=_bool_or_default(data, "should_stop_session", GuardrailAction.STOP_SESSION in actions),
        real_orders_enabled=_bool_or_default(data, "real_orders_enabled", False),
        real_money_enabled=_bool_or_default(data, "real_money_enabled", False),
        paper_only=_bool_or_default(data, "paper_only", True),
    )
    _validate_guardrail_snapshot(guardrail)
    return guardrail


def _validate_activation_plan_for_session(plan: PaperShadowActivationPlan) -> None:
    try:
        paper_shadow_activation_plan_to_dict(plan)
    except SleeveAdmissionCorruptError as exc:
        raise PaperShadowSessionCorruptError(str(exc)) from exc
    if not plan.paper_only or plan.real_orders_enabled or plan.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session plan contains unsafe real-trading flags")


def _coerce_paper_intent_batch(batch: PaperIntentBatch | dict | tuple[PaperIntent, ...]) -> PaperIntentBatch:
    if isinstance(batch, PaperIntentBatch):
        _validate_paper_intent_batch(batch)
        return build_paper_intent_batch(batch.intents, batch_id=batch.batch_id)
    if isinstance(batch, dict):
        return paper_intent_batch_from_dict(batch)
    if isinstance(batch, tuple):
        return build_paper_intent_batch(batch)
    raise PaperShadowSessionCorruptError("paper intent batch must be a PaperIntentBatch, dict, or tuple of intents")


def _paper_intent_rejection_reasons(
    snapshot: PaperShadowSessionSnapshot,
    intent: PaperIntent,
) -> tuple[str, ...]:
    _validate_paper_intent_shape(intent)
    reasons: list[str] = []
    if snapshot.status != PaperShadowSessionStatus.RUNNING:
        reasons.append("session_not_running")
    if snapshot.guardrail.should_stop_session:
        reasons.append("guardrail_stop_session")
    if snapshot.guardrail.block_finalize:
        reasons.append("guardrail_block_finalize")
    if intent.sleeve_id not in snapshot.active_sleeves:
        reasons.append("inactive_sleeve")
    if not _paper_intent_has_valid_size(intent):
        reasons.append("invalid_intent_size")
    if snapshot.symbols_seen and intent.symbol not in snapshot.symbols_seen:
        reasons.append("unknown_symbol")
    if snapshot.venues_seen and intent.venue not in snapshot.venues_seen:
        reasons.append("unknown_venue")
    return _sorted_unique(tuple(reasons))


def _coerce_feed_replay_plan(plan: FeedReplayPlan | dict | tuple[MarketEventBatch, ...]) -> FeedReplayPlan:
    if isinstance(plan, FeedReplayPlan):
        _validate_feed_replay_plan_shape(plan)
        return plan
    if isinstance(plan, dict):
        return feed_replay_plan_from_dict(plan)
    if isinstance(plan, tuple):
        coerced = FeedReplayPlan(
            replay_id=_feed_replay_plan_id(plan),
            batches=plan,
        )
        _validate_feed_replay_plan_shape(coerced)
        return coerced
    raise PaperShadowSessionCorruptError("feed replay plan must be a FeedReplayPlan, dict, or tuple of batches")


def _validate_feed_replay_plan_shape(plan: FeedReplayPlan) -> None:
    if not isinstance(plan, FeedReplayPlan):
        raise PaperShadowSessionCorruptError("feed replay plan must be a FeedReplayPlan")
    _require_non_empty_str(plan.replay_id, "replay_id")
    if not isinstance(plan.batches, tuple):
        raise PaperShadowSessionCorruptError("feed replay batches must be a tuple")
    if not plan.batches:
        raise PaperShadowSessionCorruptError("feed replay plan must contain at least one batch")
    if any(not isinstance(batch, MarketEventBatch) for batch in plan.batches):
        raise PaperShadowSessionCorruptError("feed replay batches must contain MarketEventBatch values")


def _validate_paper_intent_shape(intent: PaperIntent) -> None:
    if not isinstance(intent, PaperIntent):
        raise PaperShadowSessionCorruptError("paper intent must be a PaperIntent")
    _require_non_empty_str(intent.sleeve_id, "sleeve_id")
    _require_non_empty_str(intent.symbol, "symbol")
    _require_non_empty_str(intent.venue, "venue")
    if not isinstance(intent.side, PaperIntentSide):
        raise PaperShadowSessionCorruptError("paper intent side must be a PaperIntentSide")
    _optional_float(intent.qty, "qty")
    _optional_float(intent.notional, "notional")
    _require_non_negative_int(intent.intent_ts_ns, "intent_ts_ns")
    _require_non_empty_str(intent.reason, "reason")
    _require_non_empty_str(intent.source, "source")


def _validate_paper_intent_batch(batch: PaperIntentBatch) -> None:
    if not isinstance(batch, PaperIntentBatch):
        raise PaperShadowSessionCorruptError("paper intent batch must be a PaperIntentBatch")
    _require_non_empty_str(batch.batch_id, "batch_id")
    if not isinstance(batch.intents, tuple):
        raise PaperShadowSessionCorruptError("paper intent batch intents must be a tuple")
    if not batch.intents:
        raise PaperShadowSessionCorruptError("paper intent batch must contain at least one intent")
    for intent in batch.intents:
        _validate_paper_intent_shape(intent)
    if batch.intents != tuple(sorted(batch.intents, key=_paper_intent_sort_key)):
        raise PaperShadowSessionCorruptError("paper intent batch intents must be sorted")


def _validate_paper_intent_validation_result(result: PaperIntentValidationResult) -> None:
    if not isinstance(result, PaperIntentValidationResult):
        raise PaperShadowSessionCorruptError("paper intent validation result must be a PaperIntentValidationResult")
    _validate_paper_intent_shape(result.intent)
    _require_bool(result.accepted, "accepted")
    if result.rejection_reasons != _sorted_unique(result.rejection_reasons):
        raise PaperShadowSessionCorruptError("paper intent rejection reasons must be sorted unique")
    if result.accepted and result.rejection_reasons:
        raise PaperShadowSessionCorruptError("accepted paper intent cannot carry rejection reasons")
    if not result.accepted and not result.rejection_reasons:
        raise PaperShadowSessionCorruptError("rejected paper intent requires rejection reasons")


def _validate_paper_intent_batch_result(result: PaperIntentBatchResult) -> None:
    if not isinstance(result, PaperIntentBatchResult):
        raise PaperShadowSessionCorruptError("paper intent batch result must be a PaperIntentBatchResult")
    _require_non_empty_str(result.batch_id, "batch_id")
    _require_non_empty_str(result.session_id, "session_id")
    _require_non_negative_int(result.as_of_ns, "as_of_ns")
    if not isinstance(result.results, tuple):
        raise PaperShadowSessionCorruptError("paper intent batch result results must be a tuple")
    for item in result.results:
        _validate_paper_intent_validation_result(item)
    _require_non_negative_int(result.intents_seen, "intents_seen")
    _require_non_negative_int(result.accepted_count, "accepted_count")
    _require_non_negative_int(result.rejected_count, "rejected_count")
    if result.intents_seen != len(result.results):
        raise PaperShadowSessionCorruptError("paper intent intents_seen must match result count")
    if result.accepted_count != sum(1 for item in result.results if item.accepted):
        raise PaperShadowSessionCorruptError("paper intent accepted_count does not match results")
    if result.rejected_count != sum(1 for item in result.results if not item.accepted):
        raise PaperShadowSessionCorruptError("paper intent rejected_count does not match results")
    if result.accepted_count + result.rejected_count != result.intents_seen:
        raise PaperShadowSessionCorruptError("paper intent result counts must sum to intents_seen")
    expected_sleeves = _sorted_unique(tuple(item.intent.sleeve_id for item in result.results))
    expected_symbols = _sorted_unique(tuple(item.intent.symbol for item in result.results))
    expected_venues = _sorted_unique(tuple(item.intent.venue for item in result.results))
    expected_reasons = _sorted_unique(tuple(reason for item in result.results for reason in item.rejection_reasons))
    if result.sleeves_seen != expected_sleeves:
        raise PaperShadowSessionCorruptError("paper intent sleeves_seen do not match results")
    if result.symbols_seen != expected_symbols:
        raise PaperShadowSessionCorruptError("paper intent symbols_seen do not match results")
    if result.venues_seen != expected_venues:
        raise PaperShadowSessionCorruptError("paper intent venues_seen do not match results")
    if result.rejection_reasons != expected_reasons:
        raise PaperShadowSessionCorruptError("paper intent rejection reasons do not match results")
    _require_bool(result.paper_only, "paper_only")
    _require_bool(result.real_orders_enabled, "real_orders_enabled")
    _require_bool(result.real_money_enabled, "real_money_enabled")
    if not result.paper_only or result.real_orders_enabled or result.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper intent result cannot carry unsafe real-trading flags")
    _require_non_empty_str(result.operator_summary, "operator_summary")


def _validate_paper_fill(fill: PaperFill) -> None:
    if not isinstance(fill, PaperFill):
        raise PaperShadowSessionCorruptError("paper fill must be a PaperFill")
    _require_non_empty_str(fill.fill_id, "fill_id")
    _require_non_empty_str(fill.intent_id, "intent_id")
    _require_non_empty_str(fill.sleeve_id, "sleeve_id")
    _require_non_empty_str(fill.symbol, "symbol")
    _require_non_empty_str(fill.venue, "venue")
    if not isinstance(fill.side, PaperIntentSide):
        raise PaperShadowSessionCorruptError("paper fill side must be a PaperIntentSide")
    _optional_float(fill.qty, "qty")
    _optional_float(fill.notional, "notional")
    _optional_non_negative_float(fill.fill_price, "fill_price")
    _require_non_negative_int(fill.fill_ts_ns, "fill_ts_ns")
    if not isinstance(fill.status, PaperFillStatus):
        raise PaperShadowSessionCorruptError("paper fill status must be a PaperFillStatus")
    _require_non_empty_str(fill.reason, "reason")
    if fill.status == PaperFillStatus.FILLED:
        if fill.fill_price is None:
            raise PaperShadowSessionCorruptError("FILLED paper fill requires fill_price")
        if not _paper_fill_has_valid_size(fill):
            raise PaperShadowSessionCorruptError("FILLED paper fill requires positive qty or notional")
        if fill.reason != "filled_from_latest_market_event":
            raise PaperShadowSessionCorruptError("FILLED paper fill requires deterministic fill reason")
    else:
        if fill.fill_price is not None:
            raise PaperShadowSessionCorruptError("non-filled paper fill cannot carry fill_price")
        expected_reason = {
            PaperFillStatus.REJECTED_NO_MARKET: "missing_latest_market_price",
            PaperFillStatus.REJECTED_GUARDRAIL: "guardrail_blocks_paper_fill",
            PaperFillStatus.REJECTED_INVALID_INTENT: ("invalid_intent_size", "intent_session_mismatch"),
            PaperFillStatus.SKIPPED: "intent_rejected",
        }[fill.status]
        if isinstance(expected_reason, tuple):
            if fill.reason not in expected_reason:
                raise PaperShadowSessionCorruptError("paper fill reason does not match rejected status")
        elif fill.reason != expected_reason:
            raise PaperShadowSessionCorruptError("paper fill reason does not match rejected status")


def _validate_paper_fill_simulation_result(result: PaperFillSimulationResult) -> None:
    if not isinstance(result, PaperFillSimulationResult):
        raise PaperShadowSessionCorruptError("paper fill simulation result must be a PaperFillSimulationResult")
    _require_non_empty_str(result.simulation_id, "simulation_id")
    _require_non_empty_str(result.session_id, "session_id")
    _require_non_negative_int(result.as_of_ns, "as_of_ns")
    _require_non_empty_str(result.intent_batch_id, "intent_batch_id")
    if not isinstance(result.fills, tuple):
        raise PaperShadowSessionCorruptError("paper fill simulation fills must be a tuple")
    for fill in result.fills:
        _validate_paper_fill(fill)
    if result.fills != tuple(sorted(result.fills, key=_paper_fill_sort_key)):
        raise PaperShadowSessionCorruptError("paper fill simulation fills must be sorted")
    _require_non_negative_int(result.fill_attempts, "fill_attempts")
    _require_non_negative_int(result.simulated_fills, "simulated_fills")
    _require_non_negative_int(result.rejected_fills, "rejected_fills")
    expected_attempts = sum(1 for fill in result.fills if fill.status != PaperFillStatus.SKIPPED)
    expected_simulated = sum(1 for fill in result.fills if fill.status == PaperFillStatus.FILLED)
    expected_rejected = sum(
        1
        for fill in result.fills
        if fill.status
        in {
            PaperFillStatus.REJECTED_NO_MARKET,
            PaperFillStatus.REJECTED_GUARDRAIL,
            PaperFillStatus.REJECTED_INVALID_INTENT,
        }
    )
    if result.fill_attempts != expected_attempts:
        raise PaperShadowSessionCorruptError("paper fill attempts do not match fills")
    if result.simulated_fills != expected_simulated:
        raise PaperShadowSessionCorruptError("paper simulated fill count does not match fills")
    if result.rejected_fills != expected_rejected:
        raise PaperShadowSessionCorruptError("paper rejected fill count does not match fills")
    if result.simulated_fills + result.rejected_fills != result.fill_attempts:
        raise PaperShadowSessionCorruptError("paper fill attempts must equal simulated plus rejected fills")
    expected_symbols = _sorted_unique(
        tuple(fill.symbol for fill in result.fills if fill.status == PaperFillStatus.FILLED)
    )
    expected_sleeves = _sorted_unique(
        tuple(fill.sleeve_id for fill in result.fills if fill.status == PaperFillStatus.FILLED)
    )
    expected_reasons = _sorted_unique(
        tuple(fill.reason for fill in result.fills if fill.status != PaperFillStatus.FILLED)
    )
    if result.symbols_filled != expected_symbols:
        raise PaperShadowSessionCorruptError("paper fill symbols_filled do not match FILLED fills")
    if result.sleeves_filled != expected_sleeves:
        raise PaperShadowSessionCorruptError("paper fill sleeves_filled do not match FILLED fills")
    if result.rejection_reasons != expected_reasons:
        raise PaperShadowSessionCorruptError("paper fill rejection reasons do not match non-filled fills")
    _require_bool(result.paper_only, "paper_only")
    _require_bool(result.real_orders_enabled, "real_orders_enabled")
    _require_bool(result.real_money_enabled, "real_money_enabled")
    if not result.paper_only or result.real_orders_enabled or result.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper fill simulation cannot carry unsafe real-trading flags")
    _require_non_empty_str(result.operator_summary, "operator_summary")


def _validate_paper_cost_model(model: PaperCostModel) -> None:
    if not isinstance(model, PaperCostModel):
        raise PaperShadowSessionCorruptError("paper cost model must be a PaperCostModel")
    _require_non_negative_float(model.fee_bps, "fee_bps")
    _require_non_negative_float(model.slippage_bps, "slippage_bps")
    _require_non_negative_float(model.min_fee, "min_fee")
    _optional_non_negative_float(model.reject_if_cost_exceeds_bps, "reject_if_cost_exceeds_bps")
    partial_fill_ratio = _require_non_negative_float(model.partial_fill_ratio, "partial_fill_ratio")
    if partial_fill_ratio <= 0.0 or partial_fill_ratio > 1.0:
        raise PaperShadowSessionCorruptError("paper cost partial_fill_ratio must be in (0, 1]")


def _validate_paper_cost_line(line: PaperCostLine) -> None:
    if not isinstance(line, PaperCostLine):
        raise PaperShadowSessionCorruptError("paper cost line must be a PaperCostLine")
    _require_non_empty_str(line.fill_id, "fill_id")
    _require_non_empty_str(line.intent_id, "intent_id")
    _require_non_empty_str(line.sleeve_id, "sleeve_id")
    _require_non_empty_str(line.symbol, "symbol")
    _require_non_empty_str(line.venue, "venue")
    if not isinstance(line.side, PaperIntentSide):
        raise PaperShadowSessionCorruptError("paper cost line side must be a PaperIntentSide")
    _require_non_negative_float(line.gross_notional, "gross_notional")
    _require_non_negative_float(line.fee, "fee")
    _require_non_negative_float(line.slippage_cost, "slippage_cost")
    _require_non_negative_float(line.net_notional, "net_notional")
    _optional_non_negative_float(line.effective_price, "effective_price")
    _require_non_negative_float(line.cost_bps, "cost_bps")
    if not isinstance(line.status, PaperCostStatus):
        raise PaperShadowSessionCorruptError("paper cost line status must be a PaperCostStatus")
    if line.reasons != _sorted_unique(line.reasons):
        raise PaperShadowSessionCorruptError("paper cost line reasons must be sorted unique")
    _require_non_negative_float(line.qty, "qty")
    _optional_non_negative_float(line.fill_price, "fill_price")
    _require_non_negative_int(line.fill_ts_ns, "fill_ts_ns")
    if line.status == PaperCostStatus.ACCEPTED:
        if line.reasons:
            raise PaperShadowSessionCorruptError("accepted paper cost cannot carry reasons")
        if line.gross_notional <= 0.0 or line.effective_price is None:
            raise PaperShadowSessionCorruptError("accepted paper cost requires positive notional and effective price")
    else:
        if not line.reasons:
            raise PaperShadowSessionCorruptError("non-accepted paper cost requires reasons")
    if line.status == PaperCostStatus.SKIPPED:
        if any(value != 0.0 for value in (line.gross_notional, line.fee, line.slippage_cost, line.net_notional)):
            raise PaperShadowSessionCorruptError("skipped paper cost cannot carry cost amounts")
        if line.effective_price is not None or line.cost_bps != 0.0:
            raise PaperShadowSessionCorruptError("skipped paper cost cannot carry effective price or cost bps")
    if line.status == PaperCostStatus.REJECTED_INVALID_FILL and "invalid_paper_fill" not in line.reasons:
        raise PaperShadowSessionCorruptError("invalid fill paper cost requires invalid_paper_fill reason")
    if line.status == PaperCostStatus.REJECTED_EXCESSIVE_COST and "cost_exceeds_threshold" not in line.reasons:
        raise PaperShadowSessionCorruptError("excessive paper cost requires cost_exceeds_threshold reason")


def _validate_paper_cost_result(result: PaperCostResult) -> None:
    if not isinstance(result, PaperCostResult):
        raise PaperShadowSessionCorruptError("paper cost result must be a PaperCostResult")
    _require_non_empty_str(result.cost_result_id, "cost_result_id")
    _require_non_empty_str(result.session_id, "session_id")
    _require_non_negative_int(result.as_of_ns, "as_of_ns")
    _require_non_empty_str(result.source_fill_simulation_id, "source_fill_simulation_id")
    _validate_paper_cost_model(result.cost_model)
    if not isinstance(result.costs, tuple):
        raise PaperShadowSessionCorruptError("paper cost result costs must be a tuple")
    for line in result.costs:
        _validate_paper_cost_line(line)
    if result.costs != tuple(sorted(result.costs, key=_paper_cost_line_sort_key)):
        raise PaperShadowSessionCorruptError("paper cost lines must be sorted")
    _require_non_negative_int(result.cost_evaluations, "cost_evaluations")
    _require_non_negative_int(result.accepted_costs, "accepted_costs")
    _require_non_negative_int(result.rejected_costs, "rejected_costs")
    _require_non_negative_int(result.skipped_costs, "skipped_costs")
    expected_evaluations = sum(1 for line in result.costs if line.status != PaperCostStatus.SKIPPED)
    expected_accepted = sum(1 for line in result.costs if line.status == PaperCostStatus.ACCEPTED)
    expected_rejected = sum(
        1
        for line in result.costs
        if line.status
        in {
            PaperCostStatus.REJECTED_EXCESSIVE_COST,
            PaperCostStatus.REJECTED_INVALID_FILL,
        }
    )
    expected_skipped = sum(1 for line in result.costs if line.status == PaperCostStatus.SKIPPED)
    if result.cost_evaluations != expected_evaluations:
        raise PaperShadowSessionCorruptError("paper cost evaluations do not match cost lines")
    if result.accepted_costs != expected_accepted:
        raise PaperShadowSessionCorruptError("paper accepted cost count does not match cost lines")
    if result.rejected_costs != expected_rejected:
        raise PaperShadowSessionCorruptError("paper rejected cost count does not match cost lines")
    if result.skipped_costs != expected_skipped:
        raise PaperShadowSessionCorruptError("paper skipped cost count does not match cost lines")
    if result.cost_evaluations + result.skipped_costs != len(result.costs):
        raise PaperShadowSessionCorruptError("paper cost counts must cover every cost line")
    expected_gross = sum(line.gross_notional for line in result.costs if line.status != PaperCostStatus.SKIPPED)
    expected_fee = sum(line.fee for line in result.costs if line.status != PaperCostStatus.SKIPPED)
    expected_slippage = sum(line.slippage_cost for line in result.costs if line.status != PaperCostStatus.SKIPPED)
    expected_net = sum(line.net_notional for line in result.costs if line.status != PaperCostStatus.SKIPPED)
    if result.gross_notional != expected_gross:
        raise PaperShadowSessionCorruptError("paper cost gross_notional does not match cost lines")
    if result.fee != expected_fee or result.total_fee != expected_fee:
        raise PaperShadowSessionCorruptError("paper cost fee totals do not match cost lines")
    if result.slippage_cost != expected_slippage or result.total_slippage_cost != expected_slippage:
        raise PaperShadowSessionCorruptError("paper cost slippage totals do not match cost lines")
    if result.net_notional != expected_net:
        raise PaperShadowSessionCorruptError("paper cost net_notional does not match cost lines")
    expected_cost_bps = _cost_bps(expected_fee + expected_slippage, expected_gross)
    if result.cost_bps != expected_cost_bps:
        raise PaperShadowSessionCorruptError("paper cost_bps does not match cost totals")
    if result.effective_price != _aggregate_effective_price(result.costs):
        raise PaperShadowSessionCorruptError("paper cost effective_price does not match cost lines")
    if result.status != _paper_cost_result_status(result.costs):
        raise PaperShadowSessionCorruptError("paper cost result status does not match cost lines")
    if result.reasons != _paper_cost_result_reasons(result.costs, result.status):
        raise PaperShadowSessionCorruptError("paper cost result reasons do not match cost lines")
    _require_bool(result.paper_only, "paper_only")
    _require_bool(result.real_orders_enabled, "real_orders_enabled")
    _require_bool(result.real_money_enabled, "real_money_enabled")
    if not result.paper_only or result.real_orders_enabled or result.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper cost result cannot carry unsafe real-trading flags")
    _require_non_empty_str(result.operator_summary, "operator_summary")


def _validate_paper_position(position: PaperPosition) -> None:
    if not isinstance(position, PaperPosition):
        raise PaperShadowSessionCorruptError("paper position must be a PaperPosition")
    if position.position_id != _paper_position_id(position.sleeve_id, position.symbol, position.venue):
        raise PaperShadowSessionCorruptError("paper position_id does not match sleeve/symbol/venue")
    _require_non_empty_str(position.sleeve_id, "sleeve_id")
    _require_non_empty_str(position.symbol, "symbol")
    _require_non_empty_str(position.venue, "venue")
    _require_non_negative_float(position.qty, "qty")
    _optional_non_negative_float(position.avg_price, "avg_price")
    _require_non_negative_float(position.gross_notional, "gross_notional")
    _require_non_negative_float(position.fees, "fees")
    _require_non_negative_float(position.slippage_cost, "slippage_cost")
    _require_float(position.realized_pnl, "realized_pnl")
    _optional_float(position.unrealized_pnl, "unrealized_pnl")
    _optional_non_negative_float(position.last_price, "last_price")
    _require_bool(position.is_open, "is_open")
    if position.is_open != (position.qty > 0.0):
        raise PaperShadowSessionCorruptError("paper position is_open must match positive qty")
    if position.qty == 0.0 and position.avg_price is not None:
        raise PaperShadowSessionCorruptError("closed paper position cannot carry avg_price")
    if position.qty > 0.0 and position.avg_price is None:
        raise PaperShadowSessionCorruptError("open paper position requires avg_price")
    if position.unrealized_pnl is not None and position.last_price is None:
        raise PaperShadowSessionCorruptError("paper position cannot carry unrealized PnL without latest price")


def _validate_paper_pnl_line(line: PaperPnLLine) -> None:
    if not isinstance(line, PaperPnLLine):
        raise PaperShadowSessionCorruptError("paper PnL line must be a PaperPnLLine")
    _require_non_empty_str(line.line_id, "line_id")
    _require_non_empty_str(line.cost_result_id, "cost_result_id")
    _require_non_empty_str(line.fill_id, "fill_id")
    _require_non_empty_str(line.sleeve_id, "sleeve_id")
    _require_non_empty_str(line.symbol, "symbol")
    _require_non_empty_str(line.venue, "venue")
    if not isinstance(line.side, PaperIntentSide):
        raise PaperShadowSessionCorruptError("paper PnL line side must be a PaperIntentSide")
    _require_non_negative_float(line.qty, "qty")
    _optional_non_negative_float(line.price, "price")
    _require_non_negative_float(line.fee, "fee")
    _require_non_negative_float(line.slippage_cost, "slippage_cost")
    _require_float(line.realized_pnl, "realized_pnl")
    _require_non_negative_float(line.position_qty_after, "position_qty_after")
    _optional_non_negative_float(line.avg_price_after, "avg_price_after")
    if not isinstance(line.status, PaperPnLStatus):
        raise PaperShadowSessionCorruptError("paper PnL line status must be a PaperPnLStatus")
    if line.reasons != _sorted_unique(line.reasons):
        raise PaperShadowSessionCorruptError("paper PnL line reasons must be sorted unique")
    if line.status == PaperPnLStatus.APPLIED:
        if line.reasons:
            raise PaperShadowSessionCorruptError("applied paper PnL line cannot carry reasons")
        if line.qty <= 0.0 or line.price is None:
            raise PaperShadowSessionCorruptError("applied paper PnL line requires positive qty and price")
    else:
        if not line.reasons:
            raise PaperShadowSessionCorruptError("non-applied paper PnL line requires reasons")
    if line.position_qty_after == 0.0 and line.avg_price_after is not None:
        raise PaperShadowSessionCorruptError("closed paper PnL line cannot carry avg_price_after")


def _validate_paper_pnl_ledger(ledger: PaperPnLLedger) -> None:
    if not isinstance(ledger, PaperPnLLedger):
        raise PaperShadowSessionCorruptError("paper PnL ledger must be a PaperPnLLedger")
    _require_non_empty_str(ledger.ledger_id, "ledger_id")
    _require_non_empty_str(ledger.session_id, "session_id")
    _require_non_negative_int(ledger.as_of_ns, "as_of_ns")
    _require_non_empty_str(ledger.source_cost_result_id, "source_cost_result_id")
    if not isinstance(ledger.positions, tuple):
        raise PaperShadowSessionCorruptError("paper PnL ledger positions must be a tuple")
    if not isinstance(ledger.pnl_lines, tuple):
        raise PaperShadowSessionCorruptError("paper PnL ledger lines must be a tuple")
    for position in ledger.positions:
        _validate_paper_position(position)
    for line in ledger.pnl_lines:
        _validate_paper_pnl_line(line)
    if ledger.positions != tuple(sorted(ledger.positions, key=_paper_position_sort_key)):
        raise PaperShadowSessionCorruptError("paper PnL ledger positions must be sorted")
    if ledger.pnl_lines != tuple(sorted(ledger.pnl_lines, key=_paper_pnl_line_sort_key)):
        raise PaperShadowSessionCorruptError("paper PnL ledger lines must be sorted")
    line_ids = tuple(line.line_id for line in ledger.pnl_lines)
    if len(line_ids) != len(set(line_ids)):
        raise PaperShadowSessionCorruptError("paper PnL ledger lines must be unique")
    position_keys = tuple(
        _paper_position_key(position.sleeve_id, position.symbol, position.venue) for position in ledger.positions
    )
    if len(position_keys) != len(set(position_keys)):
        raise PaperShadowSessionCorruptError("paper PnL ledger positions must be unique")
    _require_non_negative_int(ledger.pnl_events, "pnl_events")
    _require_non_negative_int(ledger.open_positions, "open_positions")
    _require_non_negative_int(ledger.closed_positions, "closed_positions")
    _require_non_negative_float(ledger.total_fees, "total_fees")
    _require_non_negative_float(ledger.total_slippage, "total_slippage")
    _require_float(ledger.realized_pnl, "realized_pnl")
    _optional_float(ledger.unrealized_pnl, "unrealized_pnl")
    if not isinstance(ledger.status, PaperPnLStatus):
        raise PaperShadowSessionCorruptError("paper PnL ledger status must be a PaperPnLStatus")
    if ledger.reasons != _sorted_unique(ledger.reasons):
        raise PaperShadowSessionCorruptError("paper PnL ledger reasons must be sorted unique")
    if ledger.pnl_events != sum(1 for line in ledger.pnl_lines if line.status == PaperPnLStatus.APPLIED):
        raise PaperShadowSessionCorruptError("paper PnL ledger pnl_events do not match applied lines")
    if ledger.open_positions != sum(1 for position in ledger.positions if position.is_open):
        raise PaperShadowSessionCorruptError("paper PnL ledger open position count does not match positions")
    if ledger.closed_positions != sum(1 for position in ledger.positions if not position.is_open):
        raise PaperShadowSessionCorruptError("paper PnL ledger closed position count does not match positions")
    if ledger.total_fees != sum(position.fees for position in ledger.positions):
        raise PaperShadowSessionCorruptError("paper PnL ledger total_fees do not match positions")
    if ledger.total_slippage != sum(position.slippage_cost for position in ledger.positions):
        raise PaperShadowSessionCorruptError("paper PnL ledger total_slippage does not match positions")
    if ledger.realized_pnl != sum(position.realized_pnl for position in ledger.positions):
        raise PaperShadowSessionCorruptError("paper PnL ledger realized_pnl does not match positions")
    unrealized_values = tuple(
        position.unrealized_pnl for position in ledger.positions if position.unrealized_pnl is not None
    )
    expected_unrealized = sum(unrealized_values) if unrealized_values else None
    if ledger.unrealized_pnl != expected_unrealized:
        raise PaperShadowSessionCorruptError("paper PnL ledger unrealized_pnl does not match positions")
    if ledger.status != _paper_pnl_ledger_status(ledger.pnl_lines):
        raise PaperShadowSessionCorruptError("paper PnL ledger status does not match lines")
    if ledger.reasons != _paper_pnl_ledger_reasons(ledger.pnl_lines, ledger.status):
        raise PaperShadowSessionCorruptError("paper PnL ledger reasons do not match lines")
    _require_bool(ledger.paper_only, "paper_only")
    _require_bool(ledger.real_orders_enabled, "real_orders_enabled")
    _require_bool(ledger.real_money_enabled, "real_money_enabled")
    if not ledger.paper_only or ledger.real_orders_enabled or ledger.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper PnL ledger cannot carry unsafe real-trading flags")
    _require_non_empty_str(ledger.operator_summary, "operator_summary")


def _validate_paper_portfolio_exposure(exposure: PaperPortfolioExposure) -> None:
    if not isinstance(exposure, PaperPortfolioExposure):
        raise PaperShadowSessionCorruptError("paper portfolio exposure must be a PaperPortfolioExposure")
    _require_non_empty_str(exposure.exposure_id, "exposure_id")
    if exposure.dimension not in {"sleeve", "symbol"}:
        raise PaperShadowSessionCorruptError("paper portfolio exposure dimension must be sleeve or symbol")
    _require_non_empty_str(exposure.key, "key")
    if exposure.exposure_id != _paper_portfolio_exposure_id(exposure.dimension, exposure.key):
        raise PaperShadowSessionCorruptError("paper portfolio exposure_id does not match dimension/key")
    _require_non_negative_float(exposure.gross_exposure, "gross_exposure")
    _require_non_negative_float(exposure.net_exposure, "net_exposure")
    _require_non_negative_int(exposure.open_position_count, "open_position_count")


def _validate_paper_portfolio_risk_snapshot(snapshot: PaperPortfolioRiskSnapshot) -> None:
    if not isinstance(snapshot, PaperPortfolioRiskSnapshot):
        raise PaperShadowSessionCorruptError("paper portfolio risk snapshot must be a PaperPortfolioRiskSnapshot")
    _require_non_empty_str(snapshot.snapshot_id, "snapshot_id")
    _require_non_empty_str(snapshot.session_id, "session_id")
    _require_non_negative_int(snapshot.as_of_ns, "as_of_ns")
    _require_non_empty_str(snapshot.source_ledger_id, "source_ledger_id")
    _optional_non_negative_float(snapshot.equity_start, "equity_start")
    _optional_non_negative_float(snapshot.equity_current, "equity_current")
    _require_float(snapshot.realized_pnl, "realized_pnl")
    _optional_float(snapshot.unrealized_pnl, "unrealized_pnl")
    _require_non_negative_float(snapshot.total_fees, "total_fees")
    _require_non_negative_float(snapshot.total_slippage, "total_slippage")
    _require_non_negative_float(snapshot.gross_exposure, "gross_exposure")
    _require_non_negative_float(snapshot.net_exposure, "net_exposure")
    _require_non_negative_int(snapshot.open_position_count, "open_position_count")
    if not isinstance(snapshot.sleeve_exposures, tuple):
        raise PaperShadowSessionCorruptError("paper portfolio sleeve exposures must be a tuple")
    if not isinstance(snapshot.symbol_exposures, tuple):
        raise PaperShadowSessionCorruptError("paper portfolio symbol exposures must be a tuple")
    for exposure in snapshot.sleeve_exposures:
        _validate_paper_portfolio_exposure(exposure)
        if exposure.dimension != "sleeve":
            raise PaperShadowSessionCorruptError("paper portfolio sleeve exposure has wrong dimension")
    for exposure in snapshot.symbol_exposures:
        _validate_paper_portfolio_exposure(exposure)
        if exposure.dimension != "symbol":
            raise PaperShadowSessionCorruptError("paper portfolio symbol exposure has wrong dimension")
    if snapshot.sleeve_exposures != tuple(sorted(snapshot.sleeve_exposures, key=_paper_portfolio_exposure_sort_key)):
        raise PaperShadowSessionCorruptError("paper portfolio sleeve exposures must be sorted")
    if snapshot.symbol_exposures != tuple(sorted(snapshot.symbol_exposures, key=_paper_portfolio_exposure_sort_key)):
        raise PaperShadowSessionCorruptError("paper portfolio symbol exposures must be sorted")
    exposure_keys = tuple((item.dimension, item.key) for item in snapshot.sleeve_exposures + snapshot.symbol_exposures)
    if len(exposure_keys) != len(set(exposure_keys)):
        raise PaperShadowSessionCorruptError("paper portfolio exposures must be unique")
    if snapshot.missing_price_positions != _sorted_unique(snapshot.missing_price_positions):
        raise PaperShadowSessionCorruptError("paper portfolio missing price positions must be sorted unique")
    _require_bool(snapshot.drawdown_available, "drawdown_available")
    _optional_non_negative_float(snapshot.current_drawdown, "current_drawdown")
    _optional_non_negative_float(snapshot.max_drawdown, "max_drawdown")
    if snapshot.drawdown_available:
        if snapshot.current_drawdown is None or snapshot.max_drawdown is None:
            raise PaperShadowSessionCorruptError("available paper drawdown requires current and max drawdown")
    elif snapshot.current_drawdown is not None or snapshot.max_drawdown is not None:
        raise PaperShadowSessionCorruptError("unavailable paper drawdown cannot carry drawdown values")
    if snapshot.equity_current is not None and snapshot.equity_start is None:
        raise PaperShadowSessionCorruptError("paper portfolio risk equity_current requires equity_start")
    if snapshot.unrealized_pnl is None and snapshot.equity_current is not None:
        raise PaperShadowSessionCorruptError("paper portfolio risk cannot carry equity_current without unrealized PnL")
    if not isinstance(snapshot.status, PaperPortfolioRiskStatus):
        raise PaperShadowSessionCorruptError("paper portfolio risk status must be a PaperPortfolioRiskStatus")
    if snapshot.reasons != _sorted_unique(snapshot.reasons):
        raise PaperShadowSessionCorruptError("paper portfolio risk reasons must be sorted unique")
    if snapshot.status == PaperPortfolioRiskStatus.COMPLETE and snapshot.reasons:
        raise PaperShadowSessionCorruptError("complete paper portfolio risk cannot carry reasons")
    if snapshot.status != PaperPortfolioRiskStatus.COMPLETE and not snapshot.reasons:
        raise PaperShadowSessionCorruptError("non-complete paper portfolio risk requires reasons")
    if snapshot.status == PaperPortfolioRiskStatus.INCOMPLETE and not snapshot.missing_price_positions:
        raise PaperShadowSessionCorruptError("incomplete paper portfolio risk requires missing prices")
    if snapshot.missing_price_positions and (
        snapshot.status != PaperPortfolioRiskStatus.INCOMPLETE
        or snapshot.unrealized_pnl is not None
        or snapshot.equity_current is not None
    ):
        raise PaperShadowSessionCorruptError("missing prices must force incomplete paper portfolio risk")
    sleeve_exposure_count = sum(item.open_position_count for item in snapshot.sleeve_exposures)
    symbol_exposure_count = sum(item.open_position_count for item in snapshot.symbol_exposures)
    if snapshot.missing_price_positions:
        if sleeve_exposure_count > snapshot.open_position_count or symbol_exposure_count > snapshot.open_position_count:
            raise PaperShadowSessionCorruptError("paper portfolio exposure count cannot exceed open positions")
    elif snapshot.open_position_count != sleeve_exposure_count or snapshot.open_position_count != symbol_exposure_count:
        raise PaperShadowSessionCorruptError("paper portfolio exposure count does not match open positions")
    if snapshot.gross_exposure != sum(item.gross_exposure for item in snapshot.sleeve_exposures):
        raise PaperShadowSessionCorruptError("paper portfolio gross exposure does not match sleeve exposures")
    if snapshot.net_exposure != sum(item.net_exposure for item in snapshot.sleeve_exposures):
        raise PaperShadowSessionCorruptError("paper portfolio net exposure does not match sleeve exposures")
    _require_bool(snapshot.paper_only, "paper_only")
    _require_bool(snapshot.real_orders_enabled, "real_orders_enabled")
    _require_bool(snapshot.real_money_enabled, "real_money_enabled")
    if not snapshot.paper_only or snapshot.real_orders_enabled or snapshot.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper portfolio risk cannot carry unsafe real-trading flags")
    _require_non_empty_str(snapshot.operator_summary, "operator_summary")


def _validate_paper_risk_limit_policy(policy: PaperRiskLimitPolicy) -> None:
    if not isinstance(policy, PaperRiskLimitPolicy):
        raise PaperShadowSessionCorruptError("paper risk limit policy must be a PaperRiskLimitPolicy")
    _require_non_empty_str(policy.policy_id, "policy_id")
    _optional_non_negative_float(policy.max_gross_exposure, "max_gross_exposure")
    _optional_non_negative_float(policy.max_net_exposure, "max_net_exposure")
    _optional_non_negative_int(policy.max_open_positions, "max_open_positions")
    _optional_non_negative_float(policy.max_unrealized_loss, "max_unrealized_loss")
    _optional_non_negative_float(policy.max_total_loss, "max_total_loss")
    _require_bool(policy.require_complete_prices, "require_complete_prices")


def _validate_paper_risk_limit_decision(decision: PaperRiskLimitDecision) -> None:
    if not isinstance(decision, PaperRiskLimitDecision):
        raise PaperShadowSessionCorruptError("paper risk limit decision must be a PaperRiskLimitDecision")
    _require_non_empty_str(decision.decision_id, "decision_id")
    _require_non_empty_str(decision.session_id, "session_id")
    _require_non_negative_int(decision.as_of_ns, "as_of_ns")
    _require_non_empty_str(decision.source_risk_snapshot_id, "source_risk_snapshot_id")
    _validate_paper_risk_limit_policy(decision.policy)
    if not isinstance(decision.status, PaperRiskLimitDecisionStatus):
        raise PaperShadowSessionCorruptError("paper risk limit decision status must be a PaperRiskLimitDecisionStatus")
    _require_bool(decision.passed, "passed")
    _require_bool(decision.block_new_intents, "block_new_intents")
    _require_bool(decision.stop_session, "stop_session")
    if decision.breached_limits != _sorted_unique(decision.breached_limits):
        raise PaperShadowSessionCorruptError("paper risk limit decision breached limits must be sorted unique")
    if decision.reasons != _sorted_unique(decision.reasons):
        raise PaperShadowSessionCorruptError("paper risk limit decision reasons must be sorted unique")
    if decision.status == PaperRiskLimitDecisionStatus.PASS:
        if (
            not decision.passed
            or decision.block_new_intents
            or decision.stop_session
            or decision.breached_limits
            or decision.reasons
        ):
            raise PaperShadowSessionCorruptError("passing paper risk decision cannot carry blockers")
    else:
        if decision.passed:
            raise PaperShadowSessionCorruptError("non-passing paper risk decision cannot be passed")
        if not decision.reasons:
            raise PaperShadowSessionCorruptError("non-passing paper risk decision requires reasons")
    if decision.status == PaperRiskLimitDecisionStatus.STOP_SESSION and (
        not decision.stop_session or not decision.block_new_intents
    ):
        raise PaperShadowSessionCorruptError("STOP_SESSION paper risk decision must stop and block")
    if decision.status == PaperRiskLimitDecisionStatus.BLOCK_NEW_INTENTS and (
        not decision.block_new_intents or decision.stop_session
    ):
        raise PaperShadowSessionCorruptError("BLOCK_NEW_INTENTS paper risk decision must only block new intents")
    if decision.status == PaperRiskLimitDecisionStatus.WARN and (decision.block_new_intents or decision.stop_session):
        raise PaperShadowSessionCorruptError("WARN paper risk decision cannot block or stop")
    _require_bool(decision.paper_only, "paper_only")
    _require_bool(decision.real_orders_enabled, "real_orders_enabled")
    _require_bool(decision.real_money_enabled, "real_money_enabled")
    if not decision.paper_only or decision.real_orders_enabled or decision.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper risk limit decision cannot carry unsafe real-trading flags")
    _require_non_empty_str(decision.operator_summary, "operator_summary")


def _validate_feed_replay_plan(plan: FeedReplayPlan) -> None:
    _validate_feed_replay_plan_shape(plan)
    for batch in plan.batches:
        _validate_market_event_batch(batch)


def _validate_feed_replay_result(result: FeedReplayResult) -> None:
    if not isinstance(result, FeedReplayResult):
        raise PaperShadowSessionCorruptError("feed replay result must be a FeedReplayResult")
    _require_non_empty_str(result.replay_id, "replay_id")
    _require_non_empty_str(result.session_id, "session_id")
    if not isinstance(result.session_status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("feed replay session_status must be a PaperShadowSessionStatus")
    _require_non_negative_int(result.batches_planned, "batches_planned")
    _require_non_negative_int(result.batches_replayed, "batches_replayed")
    _require_non_negative_int(result.events_replayed, "events_replayed")
    _require_non_negative_int(result.batches_rejected, "batches_rejected")
    if result.batches_planned <= 0:
        raise PaperShadowSessionCorruptError("feed replay result must have at least one planned batch")
    if result.batches_replayed + result.batches_rejected > result.batches_planned:
        raise PaperShadowSessionCorruptError("feed replay result counts exceed planned batches")
    _optional_non_negative_int(result.first_event_ns, "first_event_ns")
    _optional_non_negative_int(result.last_event_ns, "last_event_ns")
    if result.events_replayed == 0 and (result.first_event_ns is not None or result.last_event_ns is not None):
        raise PaperShadowSessionCorruptError("feed replay without events cannot carry event timestamps")
    if result.events_replayed > 0:
        if result.first_event_ns is None or result.last_event_ns is None:
            raise PaperShadowSessionCorruptError("feed replay with events requires first/last timestamps")
        if result.last_event_ns < result.first_event_ns:
            raise PaperShadowSessionCorruptError("feed replay last_event_ns cannot predate first_event_ns")
    if result.guardrail_actions_seen != _sorted_unique_actions(result.guardrail_actions_seen):
        raise PaperShadowSessionCorruptError("feed replay guardrail actions must be sorted unique")
    _require_bool(result.halted_by_guardrail, "halted_by_guardrail")
    if result.halted_by_guardrail and not result.halt_reason:
        raise PaperShadowSessionCorruptError("halted feed replay requires halt_reason")
    if not result.halted_by_guardrail and result.halt_reason is not None:
        raise PaperShadowSessionCorruptError("non-halted feed replay cannot carry halt_reason")
    _optional_str(result.halt_reason, "halt_reason")
    if result.rejected_batch_ids != _sorted_unique(result.rejected_batch_ids):
        raise PaperShadowSessionCorruptError("feed replay rejected batch ids must be sorted unique")
    if len(result.rejected_batch_ids) > result.batches_rejected:
        raise PaperShadowSessionCorruptError("feed replay rejected batch ids exceed rejected count")
    _require_non_empty_str(result.operator_summary, "operator_summary")


def _validate_paper_data_source_snapshot(snapshot: PaperDataSourceSnapshot) -> None:
    if not isinstance(snapshot, PaperDataSourceSnapshot):
        raise PaperShadowSessionCorruptError("paper data source snapshot must be a PaperDataSourceSnapshot")
    _require_non_empty_str(snapshot.source_id, "source_id")
    if not isinstance(snapshot.source_type, PaperDataSourceType):
        raise PaperShadowSessionCorruptError("paper data source source_type must be a PaperDataSourceType")
    if snapshot.symbols != _sorted_unique(snapshot.symbols):
        raise PaperShadowSessionCorruptError("paper data source symbols must be sorted unique")
    _require_non_empty_str(snapshot.venue, "venue")
    _require_non_negative_int(snapshot.as_of_ns, "as_of_ns")
    _require_non_negative_int(snapshot.batches_produced, "batches_produced")
    _require_non_negative_int(snapshot.events_produced, "events_produced")
    _require_non_negative_int(snapshot.rejected_records, "rejected_records")
    if snapshot.batch_ids != _sorted_unique(snapshot.batch_ids):
        raise PaperShadowSessionCorruptError("paper data source batch ids must be sorted unique")
    _optional_non_negative_int(snapshot.first_event_ns, "first_event_ns")
    _optional_non_negative_int(snapshot.last_event_ns, "last_event_ns")
    if snapshot.events_produced == 0 and (snapshot.first_event_ns is not None or snapshot.last_event_ns is not None):
        raise PaperShadowSessionCorruptError("paper data source without events cannot carry event timestamps")
    if snapshot.events_produced > 0:
        if snapshot.first_event_ns is None or snapshot.last_event_ns is None:
            raise PaperShadowSessionCorruptError("paper data source events require first/last timestamps")
        if snapshot.last_event_ns < snapshot.first_event_ns:
            raise PaperShadowSessionCorruptError("paper data source last_event_ns cannot predate first_event_ns")
        if snapshot.last_event_ns > snapshot.as_of_ns:
            raise PaperShadowSessionCorruptError("paper data source events cannot be newer than as_of_ns")
    if snapshot.batches_produced != len(snapshot.batch_ids):
        raise PaperShadowSessionCorruptError("paper data source batch count must match batch ids")


def _validate_paper_data_source_batch_result(result: PaperDataSourceBatchResult) -> None:
    if not isinstance(result, PaperDataSourceBatchResult):
        raise PaperShadowSessionCorruptError("paper data source batch result must be a PaperDataSourceBatchResult")
    _validate_paper_data_source_snapshot(result.source)
    _validate_market_event_batch(result.batch)
    if result.rejected_record_ids != _sorted_unique(result.rejected_record_ids):
        raise PaperShadowSessionCorruptError("paper data source rejected record ids must be sorted unique")
    if len(result.rejected_record_ids) > result.source.rejected_records:
        raise PaperShadowSessionCorruptError("paper data source rejected record ids exceed rejected count")
    if result.source.batches_produced != 1:
        raise PaperShadowSessionCorruptError("paper data source batch result must produce exactly one batch")
    if result.source.events_produced != len(result.batch.events):
        raise PaperShadowSessionCorruptError("paper data source event count must match batch events")
    if result.source.batch_ids != (result.batch.batch_id,):
        raise PaperShadowSessionCorruptError("paper data source batch ids must match result batch")
    event_symbols = _sorted_unique(tuple(event.symbol for event in result.batch.events))
    if event_symbols != result.source.symbols:
        raise PaperShadowSessionCorruptError("paper data source symbols must match result batch")
    event_venues = _sorted_unique(tuple(event.venue for event in result.batch.events))
    if event_venues != (result.source.venue,):
        raise PaperShadowSessionCorruptError("paper data source batch must contain one source venue")
    if result.source.first_event_ns != min(event.ts_ns for event in result.batch.events):
        raise PaperShadowSessionCorruptError("paper data source first_event_ns must match result batch")
    if result.source.last_event_ns != max(event.ts_ns for event in result.batch.events):
        raise PaperShadowSessionCorruptError("paper data source last_event_ns must match result batch")
    _require_non_empty_str(result.operator_summary, "operator_summary")


def _validate_paper_shadow_run_evidence_report(report: PaperShadowRunEvidenceReport) -> None:
    if not isinstance(report, PaperShadowRunEvidenceReport):
        raise PaperShadowSessionCorruptError("paper/shadow run evidence report must be a PaperShadowRunEvidenceReport")
    _require_non_empty_str(report.report_id, "report_id")
    _require_non_negative_int(report.as_of_ns, "as_of_ns")
    _validate_report_summary(report.source_summary, "source_summary")
    _validate_report_summary(report.replay_summary, "replay_summary")
    if not isinstance(report.session_status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("paper/shadow run evidence session_status must be a session status")
    if not isinstance(report.monitor_status, RuntimeMonitorStatus):
        raise PaperShadowSessionCorruptError("paper/shadow run evidence monitor_status must be a monitor status")
    if not isinstance(report.guardrail_status, GuardrailAction):
        raise PaperShadowSessionCorruptError("paper/shadow run evidence guardrail_status must be a guardrail action")
    if not isinstance(report.evidence_status, PaperShadowRunEvidenceStatus):
        raise PaperShadowSessionCorruptError("paper/shadow run evidence status must be a run evidence status")
    _require_non_negative_int(report.accepted_event_count, "accepted_event_count")
    _require_non_negative_int(report.rejected_event_count, "rejected_event_count")
    _require_non_negative_int(report.accepted_batch_count, "accepted_batch_count")
    _require_non_negative_int(report.rejected_batch_count, "rejected_batch_count")
    for field_name in ("symbols", "venues", "blockers", "reason_codes", "next_actions"):
        value = getattr(report, field_name)
        if value != _sorted_unique(value):
            raise PaperShadowSessionCorruptError(f"paper/shadow run evidence {field_name} must be sorted unique")
    _require_bool(report.paper_only, "paper_only")
    _require_bool(report.real_orders_enabled, "real_orders_enabled")
    _require_bool(report.real_money_enabled, "real_money_enabled")
    _require_non_empty_str(report.operator_summary, "operator_summary")
    if not report.paper_only or report.real_orders_enabled or report.real_money_enabled:
        if report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED:
            raise PaperShadowSessionCorruptError("unsafe run evidence flags must force BLOCKED status")
    if report.evidence_status == PaperShadowRunEvidenceStatus.PASS:
        if report.accepted_event_count <= 0:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS with zero events")
        if report.accepted_batch_count <= 0:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS with zero accepted batches")
        if report.rejected_event_count > 0 or report.rejected_batch_count > 0:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS with rejected evidence")
        if report.monitor_status != RuntimeMonitorStatus.HEALTHY:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS without a healthy monitor")
        if report.guardrail_status != GuardrailAction.NONE:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS with guardrail actions")
        if not _report_summary_available(report.source_summary):
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS without source evidence")
        if not _report_summary_available(report.replay_summary):
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS without replay evidence")
        if report.blockers or report.reason_codes:
            raise PaperShadowSessionCorruptError("paper/shadow run evidence cannot PASS with blockers or reasons")
    if report.rejected_event_count > 0 and report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED:
        raise PaperShadowSessionCorruptError("rejected events must force BLOCKED run evidence status")
    if report.rejected_batch_count > 0 and report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED:
        raise PaperShadowSessionCorruptError("rejected batches must force BLOCKED run evidence status")
    if report.guardrail_status in {GuardrailAction.STOP_SESSION, GuardrailAction.PAUSE_SESSION}:
        if report.evidence_status == PaperShadowRunEvidenceStatus.PASS:
            raise PaperShadowSessionCorruptError("stop/pause guardrails cannot produce PASS run evidence")
    if report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY and report.accepted_event_count > 0:
        raise PaperShadowSessionCorruptError("EMPTY run evidence cannot carry accepted events")


def _validate_multi_source_run_evidence_report(report: MultiSourceRunEvidenceReport) -> None:
    if not isinstance(report, MultiSourceRunEvidenceReport):
        raise PaperShadowSessionCorruptError("multi-source run evidence report must be a MultiSourceRunEvidenceReport")
    _require_non_empty_str(report.aggregate_id, "aggregate_id")
    _require_non_negative_int(report.as_of_ns, "as_of_ns")
    for field_name in ("report_ids", "symbols", "venues", "blockers", "reason_codes", "next_actions"):
        value = getattr(report, field_name)
        if value != _sorted_unique(value):
            raise PaperShadowSessionCorruptError(f"multi-source run evidence {field_name} must be sorted unique")
    _require_non_negative_int(report.report_count, "report_count")
    _require_non_negative_int(report.pass_count, "pass_count")
    _require_non_negative_int(report.warn_count, "warn_count")
    _require_non_negative_int(report.blocked_count, "blocked_count")
    _require_non_negative_int(report.inconclusive_count, "inconclusive_count")
    _require_non_negative_int(report.empty_count, "empty_count")
    _require_non_negative_int(report.accepted_event_count, "accepted_event_count")
    _require_non_negative_int(report.rejected_event_count, "rejected_event_count")
    _require_non_negative_int(report.accepted_batch_count, "accepted_batch_count")
    _require_non_negative_int(report.rejected_batch_count, "rejected_batch_count")
    if report.report_count != len(report.report_ids):
        raise PaperShadowSessionCorruptError("multi-source report_count must match report_ids")
    status_count = (
        report.pass_count + report.warn_count + report.blocked_count + report.inconclusive_count + report.empty_count
    )
    if status_count != report.report_count:
        raise PaperShadowSessionCorruptError("multi-source evidence status counts must sum to report_count")
    if report.guardrail_actions != _sorted_unique_actions(report.guardrail_actions):
        raise PaperShadowSessionCorruptError("multi-source guardrail actions must be sorted unique")
    if not report.guardrail_actions and report.report_count > 0:
        raise PaperShadowSessionCorruptError("multi-source run evidence requires guardrail actions when reports exist")
    if report.guardrail_actions and report.report_count == 0:
        raise PaperShadowSessionCorruptError("empty multi-source run evidence cannot carry guardrail actions")
    if not isinstance(report.evidence_status, PaperShadowRunEvidenceStatus):
        raise PaperShadowSessionCorruptError("multi-source evidence_status must be a run evidence status")
    _require_bool(report.paper_only, "paper_only")
    _require_bool(report.real_orders_enabled, "real_orders_enabled")
    _require_bool(report.real_money_enabled, "real_money_enabled")
    _require_non_empty_str(report.operator_summary, "operator_summary")
    if report.report_count == 0 and report.evidence_status == PaperShadowRunEvidenceStatus.PASS:
        raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS with zero reports")
    if report.evidence_status == PaperShadowRunEvidenceStatus.PASS:
        if report.pass_count != report.report_count:
            raise PaperShadowSessionCorruptError("multi-source PASS requires every report to PASS")
        if report.accepted_event_count <= 0 or report.accepted_batch_count <= 0:
            raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS without accepted evidence")
        if report.rejected_event_count > 0 or report.rejected_batch_count > 0:
            raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS with rejected evidence")
        if report.guardrail_actions != (GuardrailAction.NONE,):
            raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS with guardrail actions")
        if report.blockers or report.reason_codes:
            raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS with blockers or reasons")
        if not report.paper_only or report.real_orders_enabled or report.real_money_enabled:
            raise PaperShadowSessionCorruptError("multi-source run evidence cannot PASS with unsafe flags")
    if report.blocked_count > 0 and report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED:
        raise PaperShadowSessionCorruptError("any blocked run evidence report must force BLOCKED aggregate status")
    if (report.rejected_event_count > 0 or report.rejected_batch_count > 0) and (
        report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED
    ):
        raise PaperShadowSessionCorruptError("rejected multi-source evidence must force BLOCKED status")
    if (not report.paper_only or report.real_orders_enabled or report.real_money_enabled) and (
        report.evidence_status != PaperShadowRunEvidenceStatus.BLOCKED
    ):
        raise PaperShadowSessionCorruptError("unsafe multi-source evidence flags must force BLOCKED status")
    if report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY and report.report_count > 0:
        raise PaperShadowSessionCorruptError("EMPTY multi-source run evidence is reserved for zero reports")


def _validate_paper_shadow_evidence_bundle(bundle: PaperShadowEvidenceBundle) -> None:
    if not isinstance(bundle, PaperShadowEvidenceBundle):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle must be a PaperShadowEvidenceBundle")
    _require_non_empty_str(bundle.bundle_id, "bundle_id")
    _require_non_negative_int(bundle.as_of_ns, "as_of_ns")
    _validate_multi_source_run_evidence_report(bundle.aggregate_report)
    if not isinstance(bundle.run_reports, tuple):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle run_reports must be a tuple")
    for report in bundle.run_reports:
        _validate_paper_shadow_run_evidence_report(report)
    if bundle.run_reports != tuple(sorted(bundle.run_reports, key=lambda report: report.report_id)):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle run_reports must be sorted by report_id")
    _validate_unique_report_ids(bundle.run_reports)
    for field_name in ("report_ids", "missing_report_ids", "blockers", "reason_codes", "next_actions"):
        value = getattr(bundle, field_name)
        if value != _sorted_unique(value):
            raise PaperShadowSessionCorruptError(f"paper/shadow evidence bundle {field_name} must be sorted unique")
    if not isinstance(bundle.evidence_status, PaperShadowRunEvidenceStatus):
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle evidence_status must be a run status")
    _require_bool(bundle.paper_only, "paper_only")
    _require_bool(bundle.real_orders_enabled, "real_orders_enabled")
    _require_bool(bundle.real_money_enabled, "real_money_enabled")
    _require_non_empty_str(bundle.operator_summary, "operator_summary")
    if bundle.report_ids != bundle.aggregate_report.report_ids:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle report_ids must match aggregate report_ids")
    nested_report_ids = tuple(report.report_id for report in bundle.run_reports)
    missing_report_ids = _evidence_bundle_missing_report_ids(bundle.aggregate_report, nested_report_ids)
    if bundle.missing_report_ids != missing_report_ids:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle missing_report_ids are stale")
    _ensure_no_unexpected_evidence_bundle_reports(bundle.aggregate_report, nested_report_ids)
    if not missing_report_ids:
        _assert_evidence_bundle_aggregate_matches_reports(bundle.aggregate_report, bundle.run_reports)
    expected_status = _evidence_bundle_status(bundle.aggregate_report, missing_report_ids)
    if bundle.evidence_status != expected_status:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle status does not match aggregate/drilldowns")
    expected_reason_codes = _evidence_bundle_reason_codes(bundle.aggregate_report, missing_report_ids)
    if bundle.reason_codes != expected_reason_codes:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle reason_codes do not match truth")
    expected_blockers = _evidence_bundle_blockers(bundle.aggregate_report, missing_report_ids, expected_reason_codes)
    if bundle.blockers != expected_blockers:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle blockers do not match truth")
    expected_next_actions = _evidence_bundle_next_actions(expected_status, bundle.aggregate_report, missing_report_ids)
    if bundle.next_actions != expected_next_actions:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle next_actions do not match truth")
    expected_paper_only = bundle.aggregate_report.paper_only and all(report.paper_only for report in bundle.run_reports)
    expected_real_orders_enabled = bundle.aggregate_report.real_orders_enabled or any(
        report.real_orders_enabled for report in bundle.run_reports
    )
    expected_real_money_enabled = bundle.aggregate_report.real_money_enabled or any(
        report.real_money_enabled for report in bundle.run_reports
    )
    if bundle.paper_only != expected_paper_only:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle paper_only flag does not match reports")
    if bundle.real_orders_enabled != expected_real_orders_enabled:
        raise PaperShadowSessionCorruptError(
            "paper/shadow evidence bundle real_orders_enabled flag does not match reports"
        )
    if bundle.real_money_enabled != expected_real_money_enabled:
        raise PaperShadowSessionCorruptError(
            "paper/shadow evidence bundle real_money_enabled flag does not match reports"
        )
    if missing_report_ids and bundle.evidence_status == PaperShadowRunEvidenceStatus.PASS:
        raise PaperShadowSessionCorruptError("paper/shadow evidence bundle cannot PASS with missing drilldowns")
    if bundle.evidence_status == PaperShadowRunEvidenceStatus.PASS:
        if bundle.aggregate_report.evidence_status != PaperShadowRunEvidenceStatus.PASS:
            raise PaperShadowSessionCorruptError("paper/shadow evidence bundle PASS requires PASS aggregate")
        if not bundle.run_reports:
            raise PaperShadowSessionCorruptError("paper/shadow evidence bundle cannot PASS without run drilldowns")
        if bundle.blockers or bundle.reason_codes:
            raise PaperShadowSessionCorruptError("paper/shadow evidence bundle cannot PASS with blockers or reasons")
        if not bundle.paper_only or bundle.real_orders_enabled or bundle.real_money_enabled:
            raise PaperShadowSessionCorruptError("paper/shadow evidence bundle cannot PASS with unsafe flags")


def _validate_session_snapshot(snapshot: PaperShadowSessionSnapshot) -> None:
    if not isinstance(snapshot, PaperShadowSessionSnapshot):
        raise PaperShadowSessionCorruptError("paper/shadow session snapshot must be a PaperShadowSessionSnapshot")
    if not isinstance(snapshot.session_id, str) or not snapshot.session_id:
        raise PaperShadowSessionCorruptError("paper/shadow session_id must be a non-empty string")
    if not isinstance(snapshot.status, PaperShadowSessionStatus):
        raise PaperShadowSessionCorruptError("paper/shadow session status must be a PaperShadowSessionStatus")
    if not isinstance(snapshot.as_of_ns, int) or isinstance(snapshot.as_of_ns, bool) or snapshot.as_of_ns < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session as_of_ns must be a non-negative int")
    if snapshot.prepared_at_ns is not None and snapshot.as_of_ns < snapshot.prepared_at_ns:
        raise PaperShadowSessionCorruptError("paper/shadow session as_of_ns cannot predate prepare")
    for field_name in (
        "active_sleeves_seen",
        "blockers_seen",
        "symbols_seen",
        "venues_seen",
        "active_sleeves",
        "inactive_sleeves",
        "admitted_unallocated_sleeves",
        "activation_blockers",
        "evidence_blockers",
        "governance_blockers",
        "intent_sleeves_seen",
        "intent_symbols_seen",
        "intent_venues_seen",
        "intent_rejection_reasons",
        "symbols_filled",
        "sleeves_filled",
    ):
        value = getattr(snapshot, field_name)
        if value != _sorted_unique(value):
            raise PaperShadowSessionCorruptError(f"paper/shadow session {field_name} must be sorted unique strings")
    if not snapshot.paper_only:
        raise PaperShadowSessionCorruptError("paper/shadow session must remain paper_only")
    if snapshot.real_orders_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session cannot enable real orders")
    if snapshot.real_money_enabled:
        raise PaperShadowSessionCorruptError("paper/shadow session cannot enable real money")
    if snapshot.tick_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session tick_count cannot be negative")
    if snapshot.tick_count > 0 and snapshot.last_tick_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow session ticks require last_tick_at_ns")
    if snapshot.event_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session event_count cannot be negative")
    if snapshot.rejected_event_count < 0:
        raise PaperShadowSessionCorruptError("paper/shadow session rejected_event_count cannot be negative")
    _require_non_negative_int(snapshot.intents_seen, "intents_seen")
    _require_non_negative_int(snapshot.accepted_intent_count, "accepted_intent_count")
    _require_non_negative_int(snapshot.rejected_intent_count, "rejected_intent_count")
    if snapshot.accepted_intent_count + snapshot.rejected_intent_count != snapshot.intents_seen:
        raise PaperShadowSessionCorruptError("paper/shadow intent counts must sum to intents_seen")
    if snapshot.intents_seen == 0 and (
        snapshot.intent_sleeves_seen
        or snapshot.intent_symbols_seen
        or snapshot.intent_venues_seen
        or snapshot.intent_rejection_reasons
    ):
        raise PaperShadowSessionCorruptError("paper/shadow session without intents cannot carry intent counters")
    if snapshot.rejected_intent_count == 0 and snapshot.intent_rejection_reasons:
        raise PaperShadowSessionCorruptError("paper/shadow session without rejected intents cannot carry reasons")
    _require_non_negative_int(snapshot.fill_attempts, "fill_attempts")
    _require_non_negative_int(snapshot.simulated_fills, "simulated_fills")
    _require_non_negative_int(snapshot.rejected_fills, "rejected_fills")
    if snapshot.simulated_fills + snapshot.rejected_fills != snapshot.fill_attempts:
        raise PaperShadowSessionCorruptError("paper/shadow fill attempts must equal simulated plus rejected fills")
    if snapshot.fill_attempts == 0 and (
        snapshot.simulated_fills or snapshot.rejected_fills or snapshot.symbols_filled or snapshot.sleeves_filled
    ):
        raise PaperShadowSessionCorruptError("paper/shadow session without fill attempts cannot carry fill counters")
    if snapshot.simulated_fills == 0 and (snapshot.symbols_filled or snapshot.sleeves_filled):
        raise PaperShadowSessionCorruptError("paper/shadow session without simulated fills cannot carry filled sets")
    _require_non_negative_int(snapshot.cost_evaluations, "cost_evaluations")
    _require_non_negative_int(snapshot.accepted_costs, "accepted_costs")
    _require_non_negative_int(snapshot.rejected_costs, "rejected_costs")
    _require_non_negative_float(snapshot.total_fee, "total_fee")
    _require_non_negative_float(snapshot.total_slippage_cost, "total_slippage_cost")
    if snapshot.accepted_costs + snapshot.rejected_costs != snapshot.cost_evaluations:
        raise PaperShadowSessionCorruptError("paper/shadow cost evaluations must equal accepted plus rejected costs")
    if snapshot.cost_evaluations == 0 and (
        snapshot.accepted_costs
        or snapshot.rejected_costs
        or snapshot.total_fee != 0.0
        or snapshot.total_slippage_cost != 0.0
    ):
        raise PaperShadowSessionCorruptError("paper/shadow session without cost evaluations cannot carry cost counters")
    _require_non_negative_int(snapshot.pnl_events, "pnl_events")
    _require_non_negative_int(snapshot.open_positions, "open_positions")
    _require_non_negative_int(snapshot.closed_positions, "closed_positions")
    _require_non_negative_float(snapshot.total_fees, "total_fees")
    _require_non_negative_float(snapshot.total_slippage, "total_slippage")
    _require_float(snapshot.realized_pnl, "realized_pnl")
    if snapshot.pnl_events == 0 and (
        snapshot.open_positions
        or snapshot.closed_positions
        or snapshot.total_fees != 0.0
        or snapshot.total_slippage != 0.0
        or snapshot.realized_pnl != 0.0
    ):
        raise PaperShadowSessionCorruptError("paper/shadow session without PnL events cannot carry PnL counters")
    if snapshot.event_count > 0:
        if snapshot.first_event_ns is None or snapshot.last_event_ns is None:
            raise PaperShadowSessionCorruptError("paper/shadow session events require first/last event timestamps")
        if snapshot.first_event_ns > snapshot.last_event_ns:
            raise PaperShadowSessionCorruptError(
                "paper/shadow first event timestamp cannot exceed last event timestamp"
            )
        if not snapshot.symbols_seen or not snapshot.venues_seen:
            raise PaperShadowSessionCorruptError("paper/shadow session events require symbol and venue counters")
    if snapshot.event_count == 0 and (snapshot.first_event_ns is not None or snapshot.last_event_ns is not None):
        raise PaperShadowSessionCorruptError("paper/shadow session without events cannot carry event timestamps")
    for cursor in snapshot.market_event_cursors:
        _validate_market_event_cursor(cursor)
    cursor_pairs = tuple((cursor.symbol, cursor.venue) for cursor in snapshot.market_event_cursors)
    if cursor_pairs != tuple(sorted(cursor_pairs)) or len(cursor_pairs) != len(set(cursor_pairs)):
        raise PaperShadowSessionCorruptError("paper/shadow session market event cursors must be sorted unique")
    for price in snapshot.market_event_prices:
        _validate_market_event_price(price)
    price_pairs = tuple((price.symbol, price.venue) for price in snapshot.market_event_prices)
    if price_pairs != tuple(sorted(price_pairs)) or len(price_pairs) != len(set(price_pairs)):
        raise PaperShadowSessionCorruptError("paper/shadow session market event prices must be sorted unique")
    if snapshot.event_count == 0 and snapshot.market_event_prices:
        raise PaperShadowSessionCorruptError("paper/shadow session without events cannot carry market prices")
    for price in snapshot.market_event_prices:
        if price.symbol not in snapshot.symbols_seen or price.venue not in snapshot.venues_seen:
            raise PaperShadowSessionCorruptError("paper/shadow market prices must match seen symbols and venues")
        if snapshot.last_event_ns is not None and price.last_event_ns > snapshot.last_event_ns:
            raise PaperShadowSessionCorruptError("paper/shadow market price timestamp cannot exceed last event")
    _validate_runtime_monitor_snapshot(snapshot.runtime_monitor)
    if snapshot.runtime_monitor.event_count != snapshot.event_count:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor event_count must match session")
    if snapshot.runtime_monitor.monitored_symbols != snapshot.symbols_seen:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor symbols must match session")
    if snapshot.runtime_monitor.monitored_venues != snapshot.venues_seen:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor venues must match session")
    if snapshot.runtime_monitor.last_event_ns != snapshot.last_event_ns:
        raise PaperShadowSessionCorruptError("paper/shadow runtime monitor last_event_ns must match session")
    _validate_guardrail_snapshot(snapshot.guardrail)
    expected_guardrail = build_guardrail_snapshot(
        snapshot.runtime_monitor,
        session_status=snapshot.status,
        rejected_event_count=snapshot.rejected_event_count,
        paper_only=snapshot.paper_only,
        real_orders_enabled=snapshot.real_orders_enabled,
        real_money_enabled=snapshot.real_money_enabled,
    )
    if snapshot.guardrail != expected_guardrail:
        raise PaperShadowSessionCorruptError("paper/shadow guardrail snapshot does not match session truth")
    if set(snapshot.active_sleeves) & set(snapshot.inactive_sleeves):
        raise PaperShadowSessionCorruptError("paper/shadow session active and inactive sleeves overlap")
    if not set(snapshot.active_sleeves_seen).issubset(set(snapshot.active_sleeves)):
        raise PaperShadowSessionCorruptError("paper/shadow session saw sleeves outside the active manifest set")
    if snapshot.status == PaperShadowSessionStatus.READY and snapshot.prepared_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow READY session requires prepared_at_ns")
    if snapshot.status == PaperShadowSessionStatus.RUNNING and snapshot.started_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow RUNNING session requires started_at_ns")
    if snapshot.status == PaperShadowSessionStatus.STOPPED and snapshot.stopped_at_ns is None:
        raise PaperShadowSessionCorruptError("paper/shadow STOPPED session requires stopped_at_ns")
    if snapshot.status == PaperShadowSessionStatus.FINALIZED:
        if snapshot.stopped_at_ns is None or snapshot.finalized_at_ns is None:
            raise PaperShadowSessionCorruptError("paper/shadow FINALIZED session requires stop and finalize timestamps")
    if snapshot.status == PaperShadowSessionStatus.BLOCKED and not snapshot.blockers_seen:
        raise PaperShadowSessionCorruptError("paper/shadow BLOCKED session requires blockers")
    if (
        snapshot.status
        in {
            PaperShadowSessionStatus.RUNNING,
            PaperShadowSessionStatus.STOPPED,
            PaperShadowSessionStatus.FINALIZED,
        }
        and snapshot.prepared_at_ns is None
    ):
        raise PaperShadowSessionCorruptError("paper/shadow active lifecycle states require prepared_at_ns")
    if (
        snapshot.status
        in {
            PaperShadowSessionStatus.RUNNING,
            PaperShadowSessionStatus.STOPPED,
            PaperShadowSessionStatus.FINALIZED,
        }
        and snapshot.started_at_ns is None
    ):
        raise PaperShadowSessionCorruptError("paper/shadow active lifecycle states require started_at_ns")
    if snapshot.prepared_at_ns is not None and snapshot.started_at_ns is not None:
        if snapshot.started_at_ns < snapshot.prepared_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session start cannot predate prepare")
    if snapshot.started_at_ns is not None and snapshot.last_tick_at_ns is not None:
        if snapshot.last_tick_at_ns < snapshot.started_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session tick cannot predate start")
    if snapshot.started_at_ns is not None and snapshot.stopped_at_ns is not None:
        if snapshot.stopped_at_ns < snapshot.started_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session stop cannot predate start")
    if snapshot.last_tick_at_ns is not None and snapshot.stopped_at_ns is not None:
        if snapshot.stopped_at_ns < snapshot.last_tick_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session stop cannot predate latest tick")
    if snapshot.stopped_at_ns is not None and snapshot.finalized_at_ns is not None:
        if snapshot.finalized_at_ns < snapshot.stopped_at_ns:
            raise PaperShadowSessionCorruptError("paper/shadow session finalize cannot predate stop")


def _operator_summary(
    status: PaperShadowSessionStatus,
    tick_count: int,
    active_sleeves: tuple[str, ...],
    blockers: tuple[str, ...],
) -> str:
    return f"session_status={status.value}; ticks={tick_count}; active={len(active_sleeves)}; blockers={len(blockers)}"


def _feed_replay_summary(
    replay_id: str,
    batches_replayed: int,
    events_replayed: int,
    batches_rejected: int,
    halted: bool,
    halt_reason: str | None,
) -> str:
    reason = halt_reason or "none"
    return (
        f"feed_replay={replay_id}; batches={batches_replayed}; events={events_replayed}; "
        f"rejected={batches_rejected}; halted={halted}; halt_reason={reason}"
    )


def _paper_data_source_summary(snapshot: PaperDataSourceSnapshot) -> str:
    return (
        f"source={snapshot.source_id}; type={snapshot.source_type.value}; venue={snapshot.venue}; "
        f"symbols={len(snapshot.symbols)}; events={snapshot.events_produced}; rejected={snapshot.rejected_records}"
    )


def _paper_data_source_run_summary(result: PaperDataSourceBatchResult | None) -> dict:
    if result is None:
        return {"available": False}
    _validate_paper_data_source_batch_result(result)
    return {
        "available": True,
        "source_id": result.source.source_id,
        "source_type": result.source.source_type.value,
        "venue": result.source.venue,
        "symbols": list(result.source.symbols),
        "as_of_ns": result.source.as_of_ns,
        "batches_produced": result.source.batches_produced,
        "events_produced": result.source.events_produced,
        "rejected_records": result.source.rejected_records,
        "batch_ids": list(result.source.batch_ids),
        "first_event_ns": result.source.first_event_ns,
        "last_event_ns": result.source.last_event_ns,
        "rejected_record_ids": list(result.rejected_record_ids),
    }


def _feed_replay_run_summary(result: FeedReplayResult | None) -> dict:
    if result is None:
        return {"available": False}
    _validate_feed_replay_result(result)
    return {
        "available": True,
        "replay_id": result.replay_id,
        "session_id": result.session_id,
        "session_status": result.session_status.value,
        "batches_planned": result.batches_planned,
        "batches_replayed": result.batches_replayed,
        "events_replayed": result.events_replayed,
        "batches_rejected": result.batches_rejected,
        "first_event_ns": result.first_event_ns,
        "last_event_ns": result.last_event_ns,
        "guardrail_actions_seen": [action.value for action in result.guardrail_actions_seen],
        "halted_by_guardrail": result.halted_by_guardrail,
        "halt_reason": result.halt_reason,
        "rejected_batch_ids": list(result.rejected_batch_ids),
    }


def _run_evidence_report_id(
    session: PaperShadowSessionSnapshot | None,
    source: PaperDataSourceBatchResult | None,
    replay: FeedReplayResult | None,
) -> str:
    session_id = session.session_id if session is not None else "missing-session"
    as_of_ns = session.as_of_ns if session is not None else 0
    source_id = source.source.source_id if source is not None else "missing-source"
    replay_id = replay.replay_id if replay is not None else "missing-replay"
    return f"paper-shadow-run-evidence-{session_id}-{source_id}-{replay_id}-{as_of_ns}"


def _run_evidence_reason_codes(
    session: PaperShadowSessionSnapshot,
    *,
    source_available: bool,
    replay_available: bool,
    accepted_event_count: int,
    rejected_event_count: int,
    rejected_batch_count: int,
    source_rejected_record_ids: tuple[str, ...],
    replay_rejected_batch_ids: tuple[str, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not source_available:
        reasons.append("missing_data_source_evidence")
    if not replay_available:
        reasons.append("missing_replay_evidence")
    if accepted_event_count == 0:
        reasons.append("no_market_events")
    if rejected_event_count > 0:
        reasons.append("rejected_market_events")
    if rejected_batch_count > 0:
        reasons.append("rejected_replay_batches")
    if not session.paper_only or session.real_orders_enabled or session.real_money_enabled:
        reasons.append("unsafe_real_trading_flags")
    reasons.extend(session.runtime_monitor.reason_codes)
    reasons.extend(session.guardrail.reason_codes)
    reasons.extend(f"rejected_record:{record_id}" for record_id in source_rejected_record_ids)
    reasons.extend(f"rejected_batch:{batch_id}" for batch_id in replay_rejected_batch_ids)
    return _sorted_unique(reasons)


def _run_evidence_blockers(
    reason_codes: tuple[str, ...],
    session: PaperShadowSessionSnapshot,
    *,
    rejected_batch_count: int,
    rejected_event_count: int,
) -> tuple[str, ...]:
    blockers: list[str] = []
    if rejected_batch_count > 0 or rejected_event_count > 0:
        blockers.append("rejected_run_evidence")
    if session.guardrail.primary_action != GuardrailAction.NONE or session.guardrail.block_finalize:
        blockers.append("guardrail_action_required")
    if not session.paper_only or session.real_orders_enabled or session.real_money_enabled:
        blockers.append("unsafe_real_trading_flags")
    if session.runtime_monitor.status != RuntimeMonitorStatus.HEALTHY and session.event_count > 0:
        blockers.append("runtime_monitor_not_healthy")
    blockers.extend(session.blockers_seen)
    blockers.extend(
        reason
        for reason in reason_codes
        if reason
        in {
            "rejected_market_events",
            "rejected_replay_batches",
            "stale_feed_detected",
            "missing_symbol_coverage",
            "missing_venue_coverage",
            "price_validity_failed",
            "unsafe_real_trading_flags",
        }
    )
    return _sorted_unique(blockers)


def _run_evidence_status(
    session: PaperShadowSessionSnapshot,
    *,
    source_available: bool,
    replay_available: bool,
    accepted_event_count: int,
    rejected_event_count: int,
    rejected_batch_count: int,
) -> PaperShadowRunEvidenceStatus:
    if not session.paper_only or session.real_orders_enabled or session.real_money_enabled:
        return PaperShadowRunEvidenceStatus.BLOCKED
    if rejected_event_count > 0 or rejected_batch_count > 0:
        return PaperShadowRunEvidenceStatus.BLOCKED
    if accepted_event_count == 0:
        return PaperShadowRunEvidenceStatus.EMPTY
    if (
        session.guardrail.should_stop_session
        or session.guardrail.should_pause_session
        or session.guardrail.block_finalize
    ):
        return PaperShadowRunEvidenceStatus.BLOCKED
    if session.guardrail.primary_action != GuardrailAction.NONE:
        return PaperShadowRunEvidenceStatus.BLOCKED
    if session.runtime_monitor.status != RuntimeMonitorStatus.HEALTHY:
        return PaperShadowRunEvidenceStatus.WARN
    if not source_available or not replay_available:
        return PaperShadowRunEvidenceStatus.WARN
    return PaperShadowRunEvidenceStatus.PASS


def _run_evidence_next_actions(
    status: PaperShadowRunEvidenceStatus,
    reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    if status == PaperShadowRunEvidenceStatus.PASS:
        return ("continue_paper_shadow_observation",)
    if status == PaperShadowRunEvidenceStatus.EMPTY:
        return ("provide_market_events",)
    if status == PaperShadowRunEvidenceStatus.INCONCLUSIVE:
        return ("restore_session_snapshot",)
    actions: list[str] = []
    if "missing_data_source_evidence" in reason_codes:
        actions.append("attach_data_source_evidence")
    if "missing_replay_evidence" in reason_codes:
        actions.append("attach_feed_replay_evidence")
    if "no_market_events" in reason_codes:
        actions.append("provide_market_events")
    if any(reason.startswith("rejected_") for reason in reason_codes):
        actions.append("replay_with_valid_paper_data")
    if status == PaperShadowRunEvidenceStatus.BLOCKED:
        actions.append("resolve_run_evidence_blockers")
    if status == PaperShadowRunEvidenceStatus.WARN:
        actions.append("review_run_evidence_warnings")
    return _sorted_unique(tuple(actions))


def _run_evidence_summary(
    status: PaperShadowRunEvidenceStatus,
    *,
    accepted_event_count: int,
    rejected_event_count: int,
    blockers: tuple[str, ...],
) -> str:
    return (
        f"run_evidence={status.value}; accepted_events={accepted_event_count}; "
        f"rejected_events={rejected_event_count}; blockers={len(blockers)}"
    )


def _validate_unique_report_ids(reports: tuple[PaperShadowRunEvidenceReport, ...]) -> None:
    report_ids = tuple(report.report_id for report in reports)
    if len(report_ids) != len(set(report_ids)):
        raise PaperShadowSessionCorruptError("multi-source run evidence report_ids must be unique")


def _report_ids_from_data(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("multi-source report_ids must be a list/tuple")
    report_ids = tuple(_require_non_empty_str(item, "report_id") for item in value)
    if len(report_ids) != len(set(report_ids)):
        raise PaperShadowSessionCorruptError("multi-source run evidence report_ids must be unique")
    ordered = tuple(sorted(report_ids))
    if report_ids != ordered:
        raise PaperShadowSessionCorruptError("multi-source report_ids must be sorted")
    return report_ids


def _multi_source_run_evidence_status(
    reports: tuple[PaperShadowRunEvidenceReport, ...],
) -> PaperShadowRunEvidenceStatus:
    if not reports:
        return PaperShadowRunEvidenceStatus.EMPTY
    if any(not report.paper_only or report.real_orders_enabled or report.real_money_enabled for report in reports):
        return PaperShadowRunEvidenceStatus.BLOCKED
    if any(report.rejected_event_count > 0 or report.rejected_batch_count > 0 for report in reports):
        return PaperShadowRunEvidenceStatus.BLOCKED
    statuses = tuple(report.evidence_status for report in reports)
    if PaperShadowRunEvidenceStatus.BLOCKED in statuses:
        return PaperShadowRunEvidenceStatus.BLOCKED
    if PaperShadowRunEvidenceStatus.INCONCLUSIVE in statuses:
        return PaperShadowRunEvidenceStatus.INCONCLUSIVE
    if PaperShadowRunEvidenceStatus.EMPTY in statuses:
        return PaperShadowRunEvidenceStatus.INCONCLUSIVE
    if all(status == PaperShadowRunEvidenceStatus.PASS for status in statuses):
        return PaperShadowRunEvidenceStatus.PASS
    return PaperShadowRunEvidenceStatus.WARN


def _multi_source_reason_codes(reports: tuple[PaperShadowRunEvidenceReport, ...]) -> tuple[str, ...]:
    if not reports:
        return ("no_run_evidence_reports",)
    reasons: list[str] = []
    for report in reports:
        reasons.extend(report.reason_codes)
        if report.evidence_status == PaperShadowRunEvidenceStatus.WARN:
            reasons.append("warn_run_evidence_report")
        if report.evidence_status == PaperShadowRunEvidenceStatus.INCONCLUSIVE:
            reasons.append("inconclusive_run_evidence_report")
        if report.evidence_status == PaperShadowRunEvidenceStatus.EMPTY:
            reasons.append("empty_run_evidence_report")
        if report.evidence_status == PaperShadowRunEvidenceStatus.BLOCKED:
            reasons.append("blocked_run_evidence_report")
        if report.rejected_event_count > 0:
            reasons.append("rejected_market_events")
        if report.rejected_batch_count > 0:
            reasons.append("rejected_replay_batches")
        if not report.paper_only or report.real_orders_enabled or report.real_money_enabled:
            reasons.append("unsafe_real_trading_flags")
        if report.guardrail_status != GuardrailAction.NONE:
            reasons.append("guardrail_action_required")
    return _sorted_unique(tuple(reasons))


def _multi_source_blockers(
    reports: tuple[PaperShadowRunEvidenceReport, ...],
    reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    blockers: list[str] = []
    if not reports:
        blockers.append("no_run_evidence_reports")
    for report in reports:
        blockers.extend(report.blockers)
    blockers.extend(
        reason
        for reason in reason_codes
        if reason
        in {
            "blocked_run_evidence_report",
            "empty_run_evidence_report",
            "guardrail_action_required",
            "inconclusive_run_evidence_report",
            "no_run_evidence_reports",
            "rejected_market_events",
            "rejected_replay_batches",
            "unsafe_real_trading_flags",
        }
    )
    return _sorted_unique(tuple(blockers))


def _multi_source_next_actions(
    status: PaperShadowRunEvidenceStatus,
    reports: tuple[PaperShadowRunEvidenceReport, ...],
    reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    if status == PaperShadowRunEvidenceStatus.PASS:
        return ("continue_paper_shadow_observation",)
    if not reports:
        return ("provide_run_evidence_reports",)
    actions: list[str] = []
    for report in reports:
        actions.extend(report.next_actions)
    if "blocked_run_evidence_report" in reason_codes:
        actions.append("resolve_blocked_run_evidence")
    if "inconclusive_run_evidence_report" in reason_codes:
        actions.append("restore_missing_run_evidence")
    if "empty_run_evidence_report" in reason_codes or "no_run_evidence_reports" in reason_codes:
        actions.append("provide_run_evidence_reports")
    if status == PaperShadowRunEvidenceStatus.WARN:
        actions.append("review_multi_source_run_warnings")
    if status == PaperShadowRunEvidenceStatus.BLOCKED:
        actions.append("resolve_multi_source_run_blockers")
    return _sorted_unique(tuple(actions))


def _multi_source_run_evidence_id(report_ids: tuple[str, ...]) -> str:
    if not report_ids:
        return "multi-source-run-evidence-empty"
    return f"multi-source-run-evidence-{len(report_ids)}-{report_ids[0]}-{report_ids[-1]}"


def _multi_source_run_evidence_summary(
    status: PaperShadowRunEvidenceStatus,
    *,
    report_count: int,
    pass_count: int,
    warn_count: int,
    blocked_count: int,
    inconclusive_count: int,
    empty_count: int,
) -> str:
    return (
        f"multi_source_run_evidence={status.value}; reports={report_count}; pass={pass_count}; "
        f"warn={warn_count}; blocked={blocked_count}; inconclusive={inconclusive_count}; empty={empty_count}"
    )


def _paper_shadow_evidence_bundle_id(aggregate: MultiSourceRunEvidenceReport) -> str:
    return f"paper-shadow-evidence-bundle-{aggregate.aggregate_id}"


def _evidence_bundle_missing_report_ids(
    aggregate: MultiSourceRunEvidenceReport,
    nested_report_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(report_id for report_id in aggregate.report_ids if report_id not in set(nested_report_ids))


def _ensure_no_unexpected_evidence_bundle_reports(
    aggregate: MultiSourceRunEvidenceReport,
    nested_report_ids: tuple[str, ...],
) -> None:
    unexpected = tuple(report_id for report_id in nested_report_ids if report_id not in set(aggregate.report_ids))
    if unexpected:
        raise PaperShadowSessionCorruptError(
            f"paper/shadow evidence bundle has unexpected run report drilldowns: {unexpected!r}"
        )


def _assert_evidence_bundle_aggregate_matches_reports(
    aggregate: MultiSourceRunEvidenceReport,
    run_reports: tuple[PaperShadowRunEvidenceReport, ...],
) -> None:
    recomputed = build_multi_source_run_evidence_report(
        run_reports,
        aggregate_id=aggregate.aggregate_id,
        as_of_ns=aggregate.as_of_ns,
    )
    expected = multi_source_run_evidence_report_to_dict(recomputed)
    observed = multi_source_run_evidence_report_to_dict(aggregate)
    checked_fields = (
        "aggregate_id",
        "as_of_ns",
        "report_ids",
        "report_count",
        "pass_count",
        "warn_count",
        "blocked_count",
        "inconclusive_count",
        "empty_count",
        "accepted_event_count",
        "rejected_event_count",
        "accepted_batch_count",
        "rejected_batch_count",
        "symbols",
        "venues",
        "blockers",
        "reason_codes",
        "guardrail_actions",
        "evidence_status",
        "next_actions",
        "paper_only",
        "real_orders_enabled",
        "real_money_enabled",
    )
    for field_name in checked_fields:
        if observed[field_name] != expected[field_name]:
            raise PaperShadowSessionCorruptError(
                f"paper/shadow evidence bundle aggregate drift detected for {field_name!r}"
            )


def _evidence_bundle_status(
    aggregate: MultiSourceRunEvidenceReport,
    missing_report_ids: tuple[str, ...],
) -> PaperShadowRunEvidenceStatus:
    if missing_report_ids:
        return PaperShadowRunEvidenceStatus.BLOCKED
    if not aggregate.paper_only or aggregate.real_orders_enabled or aggregate.real_money_enabled:
        return PaperShadowRunEvidenceStatus.BLOCKED
    return aggregate.evidence_status


def _evidence_bundle_reason_codes(
    aggregate: MultiSourceRunEvidenceReport,
    missing_report_ids: tuple[str, ...],
) -> tuple[str, ...]:
    reasons = list(aggregate.reason_codes)
    if missing_report_ids:
        reasons.append("missing_run_report_drilldown")
    if not aggregate.paper_only or aggregate.real_orders_enabled or aggregate.real_money_enabled:
        reasons.append("unsafe_real_trading_flags")
    return _sorted_unique(tuple(reasons))


def _evidence_bundle_blockers(
    aggregate: MultiSourceRunEvidenceReport,
    missing_report_ids: tuple[str, ...],
    reason_codes: tuple[str, ...],
) -> tuple[str, ...]:
    blockers = list(aggregate.blockers)
    if missing_report_ids:
        blockers.append("missing_run_report_drilldown")
    blockers.extend(
        reason for reason in reason_codes if reason in {"missing_run_report_drilldown", "unsafe_real_trading_flags"}
    )
    return _sorted_unique(tuple(blockers))


def _evidence_bundle_next_actions(
    status: PaperShadowRunEvidenceStatus,
    aggregate: MultiSourceRunEvidenceReport,
    missing_report_ids: tuple[str, ...],
) -> tuple[str, ...]:
    if missing_report_ids:
        return ("attach_missing_run_reports",)
    if status == PaperShadowRunEvidenceStatus.PASS:
        return aggregate.next_actions
    actions = list(aggregate.next_actions)
    if status == PaperShadowRunEvidenceStatus.BLOCKED:
        actions.append("resolve_evidence_bundle_blockers")
    if status == PaperShadowRunEvidenceStatus.INCONCLUSIVE:
        actions.append("restore_missing_run_evidence")
    if status == PaperShadowRunEvidenceStatus.EMPTY:
        actions.append("provide_run_evidence_reports")
    return _sorted_unique(tuple(actions))


def _paper_shadow_evidence_bundle_summary(
    status: PaperShadowRunEvidenceStatus,
    *,
    aggregate_id: str,
    report_count: int,
    missing_report_count: int,
    blocker_count: int,
) -> str:
    return (
        f"paper_shadow_evidence_bundle={status.value}; aggregate={aggregate_id}; reports={report_count}; "
        f"missing_drilldowns={missing_report_count}; blockers={blocker_count}"
    )


def _session_id_for_plan(plan: PaperShadowActivationPlan) -> str:
    return f"paper-shadow-session-{plan.plan_id}"


def _paper_data_source_batch_id(source_id: str, venue: str, events: tuple[MarketEvent, ...]) -> str:
    if not events:
        return f"paper-data-source-{source_id}-{venue}-empty"
    ordered = tuple(sorted(events, key=_market_event_sort_key))
    return f"paper-data-source-{source_id}-{venue}-{ordered[0].ts_ns}-{ordered[-1].ts_ns}-{len(ordered)}"


def _paper_intent_batch_id(intents: tuple[PaperIntent, ...]) -> str:
    if not intents:
        return "paper-intent-batch-empty"
    ordered = tuple(sorted(intents, key=_paper_intent_sort_key))
    return f"paper-intent-batch-{ordered[0].intent_ts_ns}-{ordered[-1].intent_ts_ns}-{len(ordered)}"


def _paper_intent_batch_summary(batch_id: str, results: tuple[PaperIntentValidationResult, ...]) -> str:
    accepted = sum(1 for item in results if item.accepted)
    rejected = len(results) - accepted
    return f"paper_intent_batch={batch_id}; intents={len(results)}; accepted={accepted}; rejected={rejected}"


def _paper_fill_simulation_summary(
    session_id: str,
    fill_attempts: int,
    simulated_fills: int,
    rejected_fills: int,
) -> str:
    return (
        f"paper_fill_simulation={session_id}; attempts={fill_attempts}; "
        f"filled={simulated_fills}; rejected={rejected_fills}"
    )


def _paper_intent_id(intent: PaperIntent) -> str:
    return f"paper-intent-{intent.intent_ts_ns}-{intent.sleeve_id}-{intent.symbol}-{intent.venue}-{intent.side.value}"


def _paper_fill_id(session_id: str, batch_id: str, index: int, intent: PaperIntent) -> str:
    return f"paper-fill-{session_id}-{batch_id}-{index}-{_paper_intent_id(intent)}"


def _paper_fill_simulation_id(
    session_id: str,
    batch_id: str,
    fills: tuple[PaperFill, ...],
) -> str:
    return f"paper-fill-simulation-{session_id}-{batch_id}-{len(fills)}"


def _paper_cost_summary(
    status: PaperCostStatus,
    cost_evaluations: int,
    accepted_costs: int,
    rejected_costs: int,
) -> str:
    return (
        f"paper_cost={status.value}; evaluations={cost_evaluations}; "
        f"accepted={accepted_costs}; rejected={rejected_costs}"
    )


def _paper_cost_result_id(
    simulation_id: str,
    model: PaperCostModel,
    costs: tuple[PaperCostLine, ...],
) -> str:
    return (
        f"paper-cost-{simulation_id}-fee-{model.fee_bps}-slip-{model.slippage_bps}-"
        f"partial-{model.partial_fill_ratio}-{len(costs)}"
    )


def _paper_cost_line_for_fill(fill: PaperFill, model: PaperCostModel) -> PaperCostLine:
    try:
        _validate_paper_fill(fill)
    except PaperShadowSessionCorruptError:
        return PaperCostLine(
            fill_id=_string_or_default(getattr(fill, "fill_id", None), "invalid-fill"),
            intent_id=_string_or_default(getattr(fill, "intent_id", None), "invalid-intent"),
            sleeve_id=_string_or_default(getattr(fill, "sleeve_id", None), "invalid-sleeve"),
            symbol=_string_or_default(getattr(fill, "symbol", None), "invalid-symbol"),
            venue=_string_or_default(getattr(fill, "venue", None), "invalid-venue"),
            side=getattr(fill, "side", PaperIntentSide.BUY)
            if isinstance(getattr(fill, "side", PaperIntentSide.BUY), PaperIntentSide)
            else PaperIntentSide.BUY,
            gross_notional=0.0,
            fee=0.0,
            slippage_cost=0.0,
            net_notional=0.0,
            effective_price=None,
            cost_bps=0.0,
            status=PaperCostStatus.REJECTED_INVALID_FILL,
            reasons=("invalid_paper_fill",),
            qty=0.0,
            fill_price=None,
            fill_ts_ns=0,
        )
    if fill.status != PaperFillStatus.FILLED:
        line = PaperCostLine(
            fill_id=fill.fill_id,
            intent_id=fill.intent_id,
            sleeve_id=fill.sleeve_id,
            symbol=fill.symbol,
            venue=fill.venue,
            side=fill.side,
            gross_notional=0.0,
            fee=0.0,
            slippage_cost=0.0,
            net_notional=0.0,
            effective_price=None,
            cost_bps=0.0,
            status=PaperCostStatus.SKIPPED,
            reasons=("fill_not_filled",),
            qty=0.0,
            fill_price=None,
            fill_ts_ns=fill.fill_ts_ns,
        )
        _validate_paper_cost_line(line)
        return line
    if fill.fill_price is None or not _paper_fill_has_valid_size(fill):
        line = PaperCostLine(
            fill_id=fill.fill_id,
            intent_id=fill.intent_id,
            sleeve_id=fill.sleeve_id,
            symbol=fill.symbol,
            venue=fill.venue,
            side=fill.side,
            gross_notional=0.0,
            fee=0.0,
            slippage_cost=0.0,
            net_notional=0.0,
            effective_price=None,
            cost_bps=0.0,
            status=PaperCostStatus.REJECTED_INVALID_FILL,
            reasons=("invalid_paper_fill",),
            qty=0.0,
            fill_price=None,
            fill_ts_ns=fill.fill_ts_ns,
        )
        _validate_paper_cost_line(line)
        return line
    base_notional = _paper_fill_base_notional(fill)
    gross_notional = base_notional * model.partial_fill_ratio
    fee = max(gross_notional * model.fee_bps / 10_000.0, model.min_fee if gross_notional > 0.0 else 0.0)
    slippage_cost = gross_notional * model.slippage_bps / 10_000.0
    net_notional = gross_notional + fee + slippage_cost
    effective_price = _paper_cost_effective_price(fill, model)
    cost_bps = _cost_bps(fee + slippage_cost, gross_notional)
    status = PaperCostStatus.ACCEPTED
    reasons: tuple[str, ...] = ()
    if model.reject_if_cost_exceeds_bps is not None and cost_bps > model.reject_if_cost_exceeds_bps:
        status = PaperCostStatus.REJECTED_EXCESSIVE_COST
        reasons = ("cost_exceeds_threshold",)
    base_qty = fill.qty if fill.qty is not None and fill.qty > 0.0 else base_notional / (fill.fill_price or 1.0)
    line = PaperCostLine(
        fill_id=fill.fill_id,
        intent_id=fill.intent_id,
        sleeve_id=fill.sleeve_id,
        symbol=fill.symbol,
        venue=fill.venue,
        side=fill.side,
        gross_notional=gross_notional,
        fee=fee,
        slippage_cost=slippage_cost,
        net_notional=net_notional,
        effective_price=effective_price,
        cost_bps=cost_bps,
        status=status,
        reasons=reasons,
        qty=base_qty * model.partial_fill_ratio,
        fill_price=fill.fill_price,
        fill_ts_ns=fill.fill_ts_ns,
    )
    _validate_paper_cost_line(line)
    return line


def _paper_fill_base_notional(fill: PaperFill) -> float:
    if fill.notional is not None and fill.notional > 0.0:
        return _require_non_negative_float(fill.notional, "notional")
    if fill.qty is None or fill.fill_price is None:
        raise PaperShadowSessionCorruptError("paper fill requires qty or notional for cost evaluation")
    return _require_non_negative_float(fill.qty, "qty") * _require_non_negative_float(fill.fill_price, "fill_price")


def _paper_cost_effective_price(fill: PaperFill, model: PaperCostModel) -> float | None:
    if fill.fill_price is None:
        return None
    fill_price = _require_non_negative_float(fill.fill_price, "fill_price")
    adjustment = fill_price * model.slippage_bps / 10_000.0
    if fill.side == PaperIntentSide.SELL:
        return max(0.0, fill_price - adjustment)
    return fill_price + adjustment


def _cost_bps(cost: float, gross_notional: float) -> float:
    cost = _require_non_negative_float(cost, "cost")
    gross_notional = _require_non_negative_float(gross_notional, "gross_notional")
    if gross_notional == 0.0:
        return 0.0
    return cost / gross_notional * 10_000.0


def _aggregate_effective_price(costs: tuple[PaperCostLine, ...]) -> float | None:
    accepted = tuple(line for line in costs if line.status == PaperCostStatus.ACCEPTED)
    if not accepted:
        return None
    denominator = sum(line.gross_notional for line in accepted)
    if denominator == 0.0:
        return None
    return sum((line.effective_price or 0.0) * line.gross_notional for line in accepted) / denominator


def _paper_cost_result_status(costs: tuple[PaperCostLine, ...]) -> PaperCostStatus:
    if any(line.status == PaperCostStatus.REJECTED_INVALID_FILL for line in costs):
        return PaperCostStatus.REJECTED_INVALID_FILL
    if any(line.status == PaperCostStatus.REJECTED_EXCESSIVE_COST for line in costs):
        return PaperCostStatus.REJECTED_EXCESSIVE_COST
    if any(line.status == PaperCostStatus.ACCEPTED for line in costs):
        return PaperCostStatus.ACCEPTED
    return PaperCostStatus.SKIPPED


def _paper_cost_result_reasons(
    costs: tuple[PaperCostLine, ...],
    status: PaperCostStatus,
) -> tuple[str, ...]:
    if status == PaperCostStatus.ACCEPTED:
        return ()
    reasons = tuple(reason for line in costs for reason in line.reasons)
    if not reasons:
        reasons = ("no_filled_paper_fills",)
    return _sorted_unique(reasons)


def _paper_pnl_summary(
    status: PaperPnLStatus,
    pnl_events: int,
    open_positions: int,
    closed_positions: int,
    realized_pnl: float,
) -> str:
    return (
        f"paper_pnl={status.value}; events={pnl_events}; open={open_positions}; "
        f"closed={closed_positions}; realized={realized_pnl}"
    )


def _paper_pnl_ledger_id(cost_result_id: str, lines: tuple[PaperPnLLine, ...]) -> str:
    return f"paper-pnl-ledger-{cost_result_id}-{len(lines)}"


def _paper_position_key(sleeve_id: str, symbol: str, venue: str) -> tuple[str, str, str]:
    return (
        _require_non_empty_str(sleeve_id, "sleeve_id"),
        _require_non_empty_str(symbol, "symbol"),
        _require_non_empty_str(venue, "venue"),
    )


def _paper_position_id(sleeve_id: str, symbol: str, venue: str) -> str:
    return f"paper-position-{sleeve_id}-{symbol}-{venue}"


def _paper_pnl_line_id(cost_result_id: str, fill_id: str) -> str:
    return f"paper-pnl-line-{cost_result_id}-{fill_id}"


def _paper_pnl_line_for_cost(
    cost_result: PaperCostResult,
    line: PaperCostLine,
    positions: dict[tuple[str, str, str], PaperPosition],
) -> tuple[PaperPnLLine, PaperPosition | None]:
    _validate_paper_cost_line(line)
    if line.status != PaperCostStatus.ACCEPTED:
        key = _paper_position_key(line.sleeve_id, line.symbol, line.venue)
        current = positions.get(key, _empty_position(line))
        return (
            _paper_pnl_line(
                cost_result.cost_result_id,
                line,
                status=PaperPnLStatus.SKIPPED,
                reasons=("cost_not_accepted",),
                realized_pnl=0.0,
                position_qty_after=current.qty,
                avg_price_after=current.avg_price,
            ),
            None,
        )
    if line.qty <= 0.0 or line.effective_price is None or line.fill_price is None:
        return (
            _paper_pnl_line(
                cost_result.cost_result_id,
                line,
                status=PaperPnLStatus.REJECTED_INVALID_POSITION,
                reasons=("invalid_cost_line_for_position",),
                realized_pnl=0.0,
                position_qty_after=0.0,
                avg_price_after=None,
            ),
            None,
        )
    key = _paper_position_key(line.sleeve_id, line.symbol, line.venue)
    current = positions.get(key, _empty_position(line))
    if line.side == PaperIntentSide.BUY:
        updated = _apply_buy_to_position(current, line)
        return (
            _paper_pnl_line(
                cost_result.cost_result_id,
                line,
                status=PaperPnLStatus.APPLIED,
                reasons=(),
                realized_pnl=0.0,
                position_qty_after=updated.qty,
                avg_price_after=updated.avg_price,
            ),
            updated,
        )
    if current.qty <= 0.0 or line.qty > current.qty:
        return (
            _paper_pnl_line(
                cost_result.cost_result_id,
                line,
                status=PaperPnLStatus.REJECTED_INVALID_POSITION,
                reasons=("short_or_crossing_sell_rejected",),
                realized_pnl=0.0,
                position_qty_after=current.qty,
                avg_price_after=current.avg_price,
            ),
            None,
        )
    updated, realized = _apply_sell_to_position(current, line)
    return (
        _paper_pnl_line(
            cost_result.cost_result_id,
            line,
            status=PaperPnLStatus.APPLIED,
            reasons=(),
            realized_pnl=realized,
            position_qty_after=updated.qty,
            avg_price_after=updated.avg_price,
        ),
        updated,
    )


def _paper_pnl_line(
    cost_result_id: str,
    line: PaperCostLine,
    *,
    status: PaperPnLStatus,
    reasons: tuple[str, ...],
    realized_pnl: float,
    position_qty_after: float,
    avg_price_after: float | None,
) -> PaperPnLLine:
    pnl_line = PaperPnLLine(
        line_id=_paper_pnl_line_id(cost_result_id, line.fill_id),
        cost_result_id=cost_result_id,
        fill_id=line.fill_id,
        sleeve_id=line.sleeve_id,
        symbol=line.symbol,
        venue=line.venue,
        side=line.side,
        qty=line.qty if status == PaperPnLStatus.APPLIED else 0.0,
        price=line.effective_price if status == PaperPnLStatus.APPLIED else None,
        fee=line.fee if status == PaperPnLStatus.APPLIED else 0.0,
        slippage_cost=line.slippage_cost if status == PaperPnLStatus.APPLIED else 0.0,
        realized_pnl=realized_pnl,
        position_qty_after=position_qty_after,
        avg_price_after=avg_price_after,
        status=status,
        reasons=_sorted_unique(reasons),
    )
    _validate_paper_pnl_line(pnl_line)
    return pnl_line


def _empty_position(line: PaperCostLine) -> PaperPosition:
    return PaperPosition(
        position_id=_paper_position_id(line.sleeve_id, line.symbol, line.venue),
        sleeve_id=line.sleeve_id,
        symbol=line.symbol,
        venue=line.venue,
        qty=0.0,
        avg_price=None,
        gross_notional=0.0,
        fees=0.0,
        slippage_cost=0.0,
        realized_pnl=0.0,
        is_open=False,
    )


def _apply_buy_to_position(position: PaperPosition, line: PaperCostLine) -> PaperPosition:
    _validate_paper_position(position)
    new_qty = position.qty + line.qty
    weighted_cost = (position.avg_price or 0.0) * position.qty + (line.effective_price or 0.0) * line.qty
    avg_price = weighted_cost / new_qty if new_qty > 0.0 else None
    updated = PaperPosition(
        position_id=position.position_id,
        sleeve_id=position.sleeve_id,
        symbol=position.symbol,
        venue=position.venue,
        qty=new_qty,
        avg_price=avg_price,
        gross_notional=position.gross_notional + line.gross_notional,
        fees=position.fees + line.fee,
        slippage_cost=position.slippage_cost + line.slippage_cost,
        realized_pnl=position.realized_pnl,
        is_open=new_qty > 0.0,
    )
    _validate_paper_position(updated)
    return updated


def _apply_sell_to_position(position: PaperPosition, line: PaperCostLine) -> tuple[PaperPosition, float]:
    _validate_paper_position(position)
    if position.avg_price is None or line.effective_price is None:
        raise PaperShadowSessionCorruptError("paper PnL sell requires position avg price and cost effective price")
    close_ratio = line.qty / position.qty
    allocated_open_fee = position.fees * close_ratio
    realized = (line.effective_price - position.avg_price) * line.qty - allocated_open_fee - line.fee
    remaining_qty = position.qty - line.qty
    updated = PaperPosition(
        position_id=position.position_id,
        sleeve_id=position.sleeve_id,
        symbol=position.symbol,
        venue=position.venue,
        qty=remaining_qty,
        avg_price=position.avg_price if remaining_qty > 0.0 else None,
        gross_notional=position.gross_notional + line.gross_notional,
        fees=position.fees + line.fee,
        slippage_cost=position.slippage_cost + line.slippage_cost,
        realized_pnl=position.realized_pnl + realized,
        is_open=remaining_qty > 0.0,
    )
    _validate_paper_position(updated)
    return updated, realized


def _paper_position_with_unrealized(
    position: PaperPosition,
    prices: tuple[MarketEventPrice, ...],
) -> PaperPosition:
    _validate_paper_position(position)
    latest = _latest_market_price_from_prices(prices, position.symbol, position.venue)
    if latest is None or not position.is_open or position.avg_price is None:
        return replace(position, unrealized_pnl=None, last_price=None)
    marked = replace(
        position,
        last_price=latest.price,
        unrealized_pnl=(latest.price - position.avg_price) * position.qty,
    )
    _validate_paper_position(marked)
    return marked


def _latest_market_price_from_prices(
    prices: tuple[MarketEventPrice, ...],
    symbol: str,
    venue: str,
) -> MarketEventPrice | None:
    for price in prices:
        if price.symbol == symbol and price.venue == venue:
            return price
    return None


def _paper_pnl_ledger_status(lines: tuple[PaperPnLLine, ...]) -> PaperPnLStatus:
    if any(line.status == PaperPnLStatus.REJECTED_INVALID_POSITION for line in lines):
        return PaperPnLStatus.REJECTED_INVALID_POSITION
    if any(line.status == PaperPnLStatus.APPLIED for line in lines):
        return PaperPnLStatus.APPLIED
    return PaperPnLStatus.SKIPPED


def _paper_pnl_ledger_reasons(
    lines: tuple[PaperPnLLine, ...],
    status: PaperPnLStatus,
) -> tuple[str, ...]:
    if status == PaperPnLStatus.APPLIED:
        return ()
    reasons = tuple(reason for line in lines for reason in line.reasons)
    if not reasons:
        reasons = ("no_accepted_cost_lines",)
    return _sorted_unique(reasons)


def _paper_portfolio_risk_snapshot_id(ledger_id: str) -> str:
    return f"paper-portfolio-risk-{ledger_id}"


def _paper_portfolio_exposure_id(dimension: str, key: str) -> str:
    return f"paper-risk-exposure-{dimension}-{key}"


def _paper_portfolio_exposures(
    dimension: str,
    priced_values: list[tuple[PaperPosition, MarketEventPrice, float, float]],
) -> tuple[PaperPortfolioExposure, ...]:
    grouped: dict[str, tuple[float, float, int]] = {}
    for position, _, exposure, _ in priced_values:
        key = position.sleeve_id if dimension == "sleeve" else position.symbol
        gross, net, count = grouped.get(key, (0.0, 0.0, 0))
        grouped[key] = (gross + exposure, net + exposure, count + 1)
    exposures = tuple(
        PaperPortfolioExposure(
            exposure_id=_paper_portfolio_exposure_id(dimension, key),
            dimension=dimension,
            key=key,
            gross_exposure=gross,
            net_exposure=net,
            open_position_count=count,
        )
        for key, (gross, net, count) in sorted(grouped.items())
    )
    for exposure in exposures:
        _validate_paper_portfolio_exposure(exposure)
    return exposures


def _paper_portfolio_risk_status(
    ledger: PaperPnLLedger,
    missing_price_positions: tuple[str, ...],
) -> PaperPortfolioRiskStatus:
    if missing_price_positions:
        return PaperPortfolioRiskStatus.INCOMPLETE
    if not ledger.positions and ledger.pnl_events == 0:
        return PaperPortfolioRiskStatus.EMPTY
    return PaperPortfolioRiskStatus.COMPLETE


def _paper_portfolio_risk_reasons(
    ledger: PaperPnLLedger,
    missing_price_positions: tuple[str, ...],
    equity_history: tuple[float, ...],
) -> tuple[str, ...]:
    reasons: list[str] = []
    if missing_price_positions:
        reasons.append("missing_latest_market_price")
    if not ledger.positions and ledger.pnl_events == 0:
        reasons.append("empty_paper_pnl_ledger")
    if not equity_history:
        reasons.append("drawdown_history_unavailable")
    status = _paper_portfolio_risk_status(ledger, missing_price_positions)
    if status == PaperPortfolioRiskStatus.COMPLETE:
        return ()
    return _sorted_unique(tuple(reasons))


def _paper_portfolio_risk_summary(
    status: PaperPortfolioRiskStatus,
    open_position_count: int,
    gross_exposure: float,
    realized_pnl: float,
    unrealized_pnl: float | None,
) -> str:
    return (
        f"paper_portfolio_risk={status.value}; open={open_position_count}; gross={gross_exposure}; "
        f"realized={realized_pnl}; unrealized={unrealized_pnl}"
    )


def _paper_risk_limit_decision_id(snapshot_id: str, policy_id: str) -> str:
    return f"paper-risk-limit-{snapshot_id}-{policy_id}"


def _paper_risk_limit_policy_from_value(policy: PaperRiskLimitPolicy | dict | None) -> PaperRiskLimitPolicy:
    if policy is None:
        resolved = PaperRiskLimitPolicy()
    elif isinstance(policy, dict):
        resolved = paper_risk_limit_policy_from_dict(policy)
    else:
        resolved = policy
    _validate_paper_risk_limit_policy(resolved)
    return resolved


def _paper_risk_limit_breaches(
    risk: PaperPortfolioRiskSnapshot,
    policy: PaperRiskLimitPolicy,
) -> tuple[str, ...]:
    breaches: list[str] = []
    if risk.status == PaperPortfolioRiskStatus.INCOMPLETE:
        breaches.append("risk_snapshot_incomplete")
        if policy.require_complete_prices:
            breaches.append("complete_prices_required")
    if risk.status == PaperPortfolioRiskStatus.EMPTY:
        breaches.append("risk_snapshot_empty")
    if policy.max_gross_exposure is not None and risk.gross_exposure > policy.max_gross_exposure:
        breaches.append("max_gross_exposure")
    if policy.max_net_exposure is not None and risk.net_exposure > policy.max_net_exposure:
        breaches.append("max_net_exposure")
    if policy.max_open_positions is not None and risk.open_position_count > policy.max_open_positions:
        breaches.append("max_open_positions")
    if policy.max_unrealized_loss is not None and risk.unrealized_pnl is not None:
        unrealized_loss = max(0.0, -risk.unrealized_pnl)
        if unrealized_loss > policy.max_unrealized_loss:
            breaches.append("max_unrealized_loss")
    if policy.max_total_loss is not None and risk.unrealized_pnl is not None:
        total_loss = max(0.0, -(risk.realized_pnl + risk.unrealized_pnl))
        if total_loss > policy.max_total_loss:
            breaches.append("max_total_loss")
    return _sorted_unique(tuple(breaches))


def _paper_risk_limit_reasons(
    risk: PaperPortfolioRiskSnapshot,
    breaches: tuple[str, ...],
) -> tuple[str, ...]:
    if not breaches:
        return ()
    reasons = list(breaches)
    if risk.missing_price_positions:
        reasons.append("missing_latest_market_price")
    return _sorted_unique(tuple(reasons))


def _paper_risk_limit_decision_status(
    breaches: tuple[str, ...],
    reasons: tuple[str, ...],
) -> PaperRiskLimitDecisionStatus:
    if not breaches and not reasons:
        return PaperRiskLimitDecisionStatus.PASS
    if any(item in breaches for item in ("max_unrealized_loss", "max_total_loss")):
        return PaperRiskLimitDecisionStatus.STOP_SESSION
    if any(
        item in breaches
        for item in (
            "complete_prices_required",
            "max_gross_exposure",
            "max_net_exposure",
            "max_open_positions",
            "risk_snapshot_incomplete",
        )
    ):
        return PaperRiskLimitDecisionStatus.BLOCK_NEW_INTENTS
    return PaperRiskLimitDecisionStatus.WARN


def _paper_risk_limit_decision_summary(
    status: PaperRiskLimitDecisionStatus,
    breaches: tuple[str, ...],
    reasons: tuple[str, ...],
) -> str:
    return f"paper_risk_limit={status.value}; breaches={len(breaches)}; reasons={','.join(reasons)}"


def _equity_history_from_data(value: object) -> tuple[float, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper equity_history must be a list/tuple")
    return tuple(_require_non_negative_float(item, "equity_history") for item in value)


def _paper_drawdown_from_equity_history(
    equity_history: tuple[float, ...],
    equity_current: float | None,
) -> tuple[bool, float | None, float | None]:
    if not equity_history or equity_current is None:
        return False, None, None
    values = equity_history + (equity_current,)
    peak = max(values)
    if peak <= 0.0:
        return False, None, None
    drawdowns = tuple(
        max(0.0, (max(values[: index + 1]) - value) / max(values[: index + 1])) for index, value in enumerate(values)
    )
    return True, drawdowns[-1], max(drawdowns)


def _paper_fill_for_intent_result(
    snapshot: PaperShadowSessionSnapshot,
    batch_result: PaperIntentBatchResult,
    result: PaperIntentValidationResult,
    *,
    index: int,
    fill_ts_ns: int,
) -> PaperFill:
    intent = result.intent
    intent_id = _paper_intent_id(intent)
    fill_id = _paper_fill_id(snapshot.session_id, batch_result.batch_id, index, intent)
    status = PaperFillStatus.FILLED
    reason = "filled_from_latest_market_event"
    fill_price: float | None = None
    if not result.accepted:
        status = PaperFillStatus.SKIPPED
        reason = "intent_rejected"
    elif batch_result.session_id != snapshot.session_id:
        status = PaperFillStatus.REJECTED_INVALID_INTENT
        reason = "intent_session_mismatch"
    elif not _paper_intent_has_valid_size(intent):
        status = PaperFillStatus.REJECTED_INVALID_INTENT
        reason = "invalid_intent_size"
    elif (
        snapshot.status != PaperShadowSessionStatus.RUNNING
        or snapshot.guardrail.should_stop_session
        or snapshot.guardrail.should_pause_session
        or snapshot.guardrail.block_finalize
    ):
        status = PaperFillStatus.REJECTED_GUARDRAIL
        reason = "guardrail_blocks_paper_fill"
    else:
        latest_price = _latest_market_event_price(snapshot, intent.symbol, intent.venue)
        if latest_price is None:
            status = PaperFillStatus.REJECTED_NO_MARKET
            reason = "missing_latest_market_price"
        else:
            fill_price = latest_price.price
    fill = PaperFill(
        fill_id=fill_id,
        intent_id=intent_id,
        sleeve_id=intent.sleeve_id,
        symbol=intent.symbol,
        venue=intent.venue,
        side=intent.side,
        qty=intent.qty,
        notional=intent.notional,
        fill_price=fill_price,
        fill_ts_ns=fill_ts_ns,
        status=status,
        reason=reason,
    )
    _validate_paper_fill(fill)
    return fill


def _latest_market_event_price(
    snapshot: PaperShadowSessionSnapshot,
    symbol: str,
    venue: str,
) -> MarketEventPrice | None:
    _require_non_empty_str(symbol, "symbol")
    _require_non_empty_str(venue, "venue")
    for price in snapshot.market_event_prices:
        if price.symbol == symbol and price.venue == venue:
            return price
    return None


def _feed_replay_plan_id(batches: tuple[MarketEventBatch, ...]) -> str:
    if not batches:
        return "feed-replay-empty"
    return f"feed-replay-{len(batches)}-{_batch_id_or_unknown(batches[0])}-{_batch_id_or_unknown(batches[-1])}"


def _batch_id_or_unknown(batch: object) -> str:
    if isinstance(batch, MarketEventBatch) and isinstance(batch.batch_id, str) and batch.batch_id:
        return batch.batch_id
    if isinstance(batch, dict):
        batch_id = batch.get("batch_id")
        if isinstance(batch_id, str) and batch_id:
            return batch_id
    return "unknown_batch"


def _normalize_batch(batch: MarketEventBatch) -> MarketEventBatch:
    _validate_market_event_batch(batch)
    return MarketEventBatch(
        batch_id=batch.batch_id,
        events=tuple(sorted(batch.events, key=_market_event_sort_key)),
    )


def _validate_market_event_batch(batch: MarketEventBatch) -> None:
    if not isinstance(batch, MarketEventBatch):
        raise PaperShadowSessionCorruptError("market event batch must be a MarketEventBatch")
    if not isinstance(batch.batch_id, str) or not batch.batch_id:
        raise PaperShadowSessionCorruptError("market event batch_id must be a non-empty string")
    if not isinstance(batch.events, tuple):
        raise PaperShadowSessionCorruptError("market event batch events must be a tuple")
    if not batch.events:
        raise PaperShadowSessionCorruptError("market event batch must contain at least one event")
    last_by_pair: dict[tuple[str, str], int] = {}
    for event in batch.events:
        _validate_market_event(event)
        pair = (event.symbol, event.venue)
        previous = last_by_pair.get(pair)
        if previous is not None and event.ts_ns < previous:
            raise PaperShadowSessionCorruptError("market event batch timestamps must be monotonic per symbol/venue")
        last_by_pair[pair] = event.ts_ns


def _validate_market_event(event: MarketEvent) -> None:
    if not isinstance(event, MarketEvent):
        raise PaperShadowSessionCorruptError("market event must be a MarketEvent")
    _require_non_empty_str(event.symbol, "symbol")
    _require_non_empty_str(event.venue, "venue")
    _require_non_negative_int(event.ts_ns, "ts_ns")
    if not isinstance(event.event_type, MarketEventType):
        raise PaperShadowSessionCorruptError("market event_type must be a MarketEventType")
    _optional_non_negative_float(event.price, "price")
    _optional_non_negative_float(event.mark_price, "mark_price")
    _optional_non_negative_float(event.index_price, "index_price")
    _optional_float(event.funding_rate, "funding_rate")
    _optional_non_negative_float(event.open_interest, "open_interest")
    if all(
        value is None
        for value in (
            event.price,
            event.mark_price,
            event.index_price,
            event.funding_rate,
            event.open_interest,
        )
    ):
        raise PaperShadowSessionCorruptError("market event must carry at least one market field")


def _validate_batch_against_session(snapshot: PaperShadowSessionSnapshot, batch: MarketEventBatch) -> None:
    cursor_lookup = {(cursor.symbol, cursor.venue): cursor.last_event_ns for cursor in snapshot.market_event_cursors}
    for event in batch.events:
        previous = cursor_lookup.get((event.symbol, event.venue))
        if previous is not None and event.ts_ns < previous:
            raise PaperShadowSessionCorruptError("market event timestamp regressed from session cursor")


def _merge_market_event_cursors(
    cursors: tuple[MarketEventCursor, ...],
    events: tuple[MarketEvent, ...],
) -> tuple[MarketEventCursor, ...]:
    latest = {(cursor.symbol, cursor.venue): cursor.last_event_ns for cursor in cursors}
    for event in events:
        pair = (event.symbol, event.venue)
        latest[pair] = max(latest.get(pair, event.ts_ns), event.ts_ns)
    return tuple(
        MarketEventCursor(symbol=symbol, venue=venue, last_event_ns=ts_ns)
        for (symbol, venue), ts_ns in sorted(latest.items())
    )


def _merge_market_event_prices(
    prices: tuple[MarketEventPrice, ...],
    events: tuple[MarketEvent, ...],
) -> tuple[MarketEventPrice, ...]:
    latest = {(price.symbol, price.venue): price for price in prices}
    for event in sorted(events, key=_market_event_sort_key):
        fill_price = _market_event_fill_price(event)
        if fill_price is None:
            continue
        pair = (event.symbol, event.venue)
        previous = latest.get(pair)
        if previous is None or event.ts_ns >= previous.last_event_ns:
            latest[pair] = MarketEventPrice(
                symbol=event.symbol,
                venue=event.venue,
                last_event_ns=event.ts_ns,
                price=fill_price,
            )
    resolved = tuple(latest[pair] for pair in sorted(latest))
    for price in resolved:
        _validate_market_event_price(price)
    return resolved


def _market_event_gap_count(
    cursors: tuple[MarketEventCursor, ...],
    events: tuple[MarketEvent, ...],
    max_gap_ns: int | None,
) -> int:
    if max_gap_ns is None:
        return 0
    max_gap_ns = _require_non_negative_int(max_gap_ns, "max_market_event_gap_ns")
    grouped: dict[tuple[str, str], list[int]] = {}
    for cursor in cursors:
        grouped.setdefault((cursor.symbol, cursor.venue), []).append(cursor.last_event_ns)
    for event in events:
        grouped.setdefault((event.symbol, event.venue), []).append(event.ts_ns)
    gap_count = 0
    for timestamps in grouped.values():
        ordered = sorted(timestamps)
        for previous, current in zip(ordered, ordered[1:]):
            if current - previous > max_gap_ns:
                gap_count += 1
    return gap_count


def _market_event_cursors_from_data(value: object) -> tuple[MarketEventCursor, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("market event cursors must be a list/tuple")
    cursors = tuple(market_event_cursor_from_dict(_dict_value(item, "market_event_cursors")) for item in value)
    for cursor in cursors:
        _validate_market_event_cursor(cursor)
    pairs = tuple((cursor.symbol, cursor.venue) for cursor in cursors)
    if pairs != tuple(sorted(pairs)) or len(pairs) != len(set(pairs)):
        raise PaperShadowSessionCorruptError("market event cursors must be sorted unique")
    return cursors


def _market_event_prices_from_data(value: object) -> tuple[MarketEventPrice, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("market event prices must be a list/tuple")
    prices = tuple(market_event_price_from_dict(_dict_value(item, "market_event_prices")) for item in value)
    for price in prices:
        _validate_market_event_price(price)
    pairs = tuple((price.symbol, price.venue) for price in prices)
    if pairs != tuple(sorted(pairs)) or len(pairs) != len(set(pairs)):
        raise PaperShadowSessionCorruptError("market event prices must be sorted unique")
    return prices


def _validate_market_event_cursor(cursor: MarketEventCursor) -> None:
    if not isinstance(cursor, MarketEventCursor):
        raise PaperShadowSessionCorruptError("market event cursor must be a MarketEventCursor")
    _require_non_empty_str(cursor.symbol, "symbol")
    _require_non_empty_str(cursor.venue, "venue")
    _require_non_negative_int(cursor.last_event_ns, "last_event_ns")


def _validate_market_event_price(price: MarketEventPrice) -> None:
    if not isinstance(price, MarketEventPrice):
        raise PaperShadowSessionCorruptError("market event price must be a MarketEventPrice")
    _require_non_empty_str(price.symbol, "symbol")
    _require_non_empty_str(price.venue, "venue")
    _require_non_negative_int(price.last_event_ns, "last_event_ns")
    _require_non_negative_float(price.price, "price")


def _validate_runtime_monitor_snapshot(monitor: RuntimeMonitorSnapshot) -> None:
    if not isinstance(monitor, RuntimeMonitorSnapshot):
        raise PaperShadowSessionCorruptError("runtime monitor must be a RuntimeMonitorSnapshot")
    if not isinstance(monitor.status, RuntimeMonitorStatus):
        raise PaperShadowSessionCorruptError("runtime monitor status must be a RuntimeMonitorStatus")
    _require_non_negative_int(monitor.event_count, "event_count")
    _require_bool(monitor.stale_feed_detected, "stale_feed_detected")
    _require_bool(monitor.symbol_coverage_ok, "symbol_coverage_ok")
    _require_bool(monitor.venue_coverage_ok, "venue_coverage_ok")
    _require_bool(monitor.price_validity_ok, "price_validity_ok")
    _require_non_negative_int(monitor.event_gap_count, "event_gap_count")
    _optional_non_negative_int(monitor.last_event_ns, "last_event_ns")
    if monitor.monitored_symbols != _sorted_unique(monitor.monitored_symbols):
        raise PaperShadowSessionCorruptError("runtime monitor symbols must be sorted unique")
    if monitor.monitored_venues != _sorted_unique(monitor.monitored_venues):
        raise PaperShadowSessionCorruptError("runtime monitor venues must be sorted unique")
    if monitor.required_symbols != _sorted_unique(monitor.required_symbols):
        raise PaperShadowSessionCorruptError("runtime monitor required symbols must be sorted unique")
    if monitor.required_venues != _sorted_unique(monitor.required_venues):
        raise PaperShadowSessionCorruptError("runtime monitor required venues must be sorted unique")
    if monitor.reason_codes != _sorted_unique(monitor.reason_codes):
        raise PaperShadowSessionCorruptError("runtime monitor reason codes must be sorted unique")
    if monitor.event_count == 0:
        if monitor.status == RuntimeMonitorStatus.HEALTHY:
            raise PaperShadowSessionCorruptError("runtime monitor cannot be healthy without events")
        if monitor.last_event_ns is not None:
            raise PaperShadowSessionCorruptError("runtime monitor without events cannot carry last_event_ns")
        if monitor.symbol_coverage_ok or monitor.venue_coverage_ok or monitor.price_validity_ok:
            raise PaperShadowSessionCorruptError("runtime monitor without events cannot report healthy checks")
    if monitor.event_count > 0 and monitor.last_event_ns is None:
        raise PaperShadowSessionCorruptError("runtime monitor with events requires last_event_ns")
    if monitor.stale_feed_detected != (monitor.event_gap_count > 0):
        raise PaperShadowSessionCorruptError("runtime monitor stale flag must match event gaps")
    if monitor.status == RuntimeMonitorStatus.HEALTHY and monitor.reason_codes:
        raise PaperShadowSessionCorruptError("runtime monitor healthy state cannot carry reason codes")
    if monitor.status == RuntimeMonitorStatus.HEALTHY and (
        monitor.stale_feed_detected
        or not monitor.symbol_coverage_ok
        or not monitor.venue_coverage_ok
        or not monitor.price_validity_ok
    ):
        raise PaperShadowSessionCorruptError("runtime monitor healthy state requires all checks ok")
    expected_status = (
        RuntimeMonitorStatus.NOT_READY
        if monitor.event_count == 0
        else RuntimeMonitorStatus.DEGRADED
        if monitor.reason_codes
        else RuntimeMonitorStatus.HEALTHY
    )
    if monitor.status != expected_status:
        raise PaperShadowSessionCorruptError("runtime monitor status does not match checks")


def _validate_guardrail_snapshot(guardrail: GuardrailSnapshot) -> None:
    if not isinstance(guardrail, GuardrailSnapshot):
        raise PaperShadowSessionCorruptError("guardrail snapshot must be a GuardrailSnapshot")
    if not isinstance(guardrail.primary_action, GuardrailAction):
        raise PaperShadowSessionCorruptError("guardrail primary_action must be a GuardrailAction")
    if not guardrail.actions:
        raise PaperShadowSessionCorruptError("guardrail actions cannot be empty")
    if guardrail.actions != _sorted_unique_actions(guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail actions must be sorted unique")
    if guardrail.primary_action != _primary_guardrail_action(guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail primary_action does not match actions")
    if guardrail.reason_codes != _sorted_unique(guardrail.reason_codes):
        raise PaperShadowSessionCorruptError("guardrail reason codes must be sorted unique")
    if not isinstance(guardrail.monitor_status, RuntimeMonitorStatus):
        raise PaperShadowSessionCorruptError("guardrail monitor_status must be a RuntimeMonitorStatus")
    if guardrail.block_finalize != (GuardrailAction.BLOCK_FINALIZE in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail block_finalize flag does not match actions")
    if guardrail.should_pause_session != (GuardrailAction.PAUSE_SESSION in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail pause flag does not match actions")
    if guardrail.should_stop_session != (GuardrailAction.STOP_SESSION in guardrail.actions):
        raise PaperShadowSessionCorruptError("guardrail stop flag does not match actions")
    _require_bool(guardrail.paper_only, "paper_only")
    _require_bool(guardrail.real_orders_enabled, "real_orders_enabled")
    _require_bool(guardrail.real_money_enabled, "real_money_enabled")
    if GuardrailAction.NONE in guardrail.actions and guardrail.actions != (GuardrailAction.NONE,):
        raise PaperShadowSessionCorruptError("guardrail NONE action cannot be combined with other actions")
    if guardrail.actions == (GuardrailAction.NONE,) and guardrail.reason_codes:
        raise PaperShadowSessionCorruptError("guardrail NONE action cannot carry reason codes")
    if (not guardrail.paper_only or guardrail.real_orders_enabled or guardrail.real_money_enabled) and (
        GuardrailAction.STOP_SESSION not in guardrail.actions or GuardrailAction.BLOCK_FINALIZE not in guardrail.actions
    ):
        raise PaperShadowSessionCorruptError("guardrail unsafe real-trading flags require stop and block actions")
    if guardrail.monitor_status != RuntimeMonitorStatus.HEALTHY and GuardrailAction.NONE in guardrail.actions:
        raise PaperShadowSessionCorruptError("guardrail cannot be NONE with unhealthy monitor")


def _runtime_monitor_reason_codes(
    *,
    has_events: bool,
    stale_feed_detected: bool,
    symbol_coverage_ok: bool,
    venue_coverage_ok: bool,
    price_validity_ok: bool,
) -> tuple[str, ...]:
    reasons: list[str] = []
    if not has_events:
        reasons.append("no_market_events")
    if stale_feed_detected:
        reasons.append("stale_feed_detected")
    if not symbol_coverage_ok:
        reasons.append("missing_symbol_coverage")
    if not venue_coverage_ok:
        reasons.append("missing_venue_coverage")
    if not price_validity_ok:
        reasons.append("price_validity_failed")
    return _sorted_unique(reasons)


def _runtime_monitor_status_from_value(value: object) -> RuntimeMonitorStatus:
    if isinstance(value, RuntimeMonitorStatus):
        return value
    if value is None:
        return RuntimeMonitorStatus.NOT_READY
    try:
        return RuntimeMonitorStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid runtime monitor status: {value!r}") from exc


def _run_evidence_status_from_value(value: object) -> PaperShadowRunEvidenceStatus:
    if isinstance(value, PaperShadowRunEvidenceStatus):
        return value
    try:
        return PaperShadowRunEvidenceStatus(_require_non_empty_str(value, "evidence_status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper/shadow run evidence status: {value!r}") from exc


def _guardrail_action_from_value(value: object) -> GuardrailAction:
    if isinstance(value, GuardrailAction):
        return value
    try:
        return GuardrailAction(_require_non_empty_str(value, "guardrail_action"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid guardrail action: {value!r}") from exc


def _guardrail_actions_from_data(value: object) -> tuple[GuardrailAction, ...]:
    if not isinstance(value, (list, tuple)):
        raise PaperShadowSessionCorruptError("guardrail actions must be a list/tuple")
    return _sorted_unique_actions(tuple(_guardrail_action_from_value(item) for item in value))


def _sorted_unique_actions(actions: tuple[GuardrailAction, ...] | list[GuardrailAction]) -> tuple[GuardrailAction, ...]:
    if not isinstance(actions, (list, tuple)):
        raise PaperShadowSessionCorruptError("guardrail actions must be a list/tuple")
    seen: list[GuardrailAction] = []
    for action in actions:
        if not isinstance(action, GuardrailAction):
            raise PaperShadowSessionCorruptError("guardrail actions must be GuardrailAction values")
        if action not in seen:
            seen.append(action)
    order = {
        GuardrailAction.STOP_SESSION: 0,
        GuardrailAction.PAUSE_SESSION: 1,
        GuardrailAction.BLOCK_FINALIZE: 2,
        GuardrailAction.WARN: 3,
        GuardrailAction.NONE: 4,
    }
    return tuple(sorted(seen, key=lambda item: order[item]))


def _primary_guardrail_action(actions: tuple[GuardrailAction, ...]) -> GuardrailAction:
    ordered = _sorted_unique_actions(actions)
    if not ordered:
        raise PaperShadowSessionCorruptError("guardrail actions cannot be empty")
    return ordered[0]


def _market_event_batch_id(events: tuple[MarketEvent, ...]) -> str:
    if not events:
        return "market-event-batch-empty"
    ordered = tuple(sorted(events, key=_market_event_sort_key))
    first_ts = ordered[0].ts_ns
    last_ts = ordered[-1].ts_ns
    return f"market-event-batch-{first_ts}-{last_ts}-{len(ordered)}"


def _market_event_sort_key(event: MarketEvent) -> tuple[int, str, str, str]:
    return (event.ts_ns, event.symbol, event.venue, event.event_type.value)


def _market_event_fill_price(event: MarketEvent) -> float | None:
    for value in (event.price, event.mark_price, event.index_price):
        if value is not None:
            return _require_non_negative_float(value, "price")
    return None


def _paper_intent_sort_key(intent: PaperIntent) -> tuple[int, str, str, str, str]:
    return (intent.intent_ts_ns, intent.sleeve_id, intent.symbol, intent.venue, intent.side.value)


def _paper_fill_sort_key(fill: PaperFill) -> tuple[int, str, str, str, str, str]:
    return (fill.fill_ts_ns, fill.sleeve_id, fill.symbol, fill.venue, fill.side.value, fill.fill_id)


def _paper_cost_line_sort_key(line: PaperCostLine) -> tuple[str, str, str, str, str, str]:
    return (line.sleeve_id, line.symbol, line.venue, line.side.value, line.fill_id, line.status.value)


def _paper_position_sort_key(position: PaperPosition) -> tuple[str, str, str]:
    return (position.sleeve_id, position.symbol, position.venue)


def _paper_pnl_line_sort_key(line: PaperPnLLine) -> tuple[str, str, str]:
    return (line.cost_result_id, line.fill_id, line.status.value)


def _paper_portfolio_exposure_sort_key(exposure: PaperPortfolioExposure) -> tuple[str, str]:
    return (exposure.dimension, exposure.key)


def _market_event_type_from_value(value: object) -> MarketEventType:
    if isinstance(value, MarketEventType):
        return value
    try:
        return MarketEventType(_require_non_empty_str(value, "event_type"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid market event_type: {value!r}") from exc


def _paper_data_source_type_from_value(value: object) -> PaperDataSourceType:
    if isinstance(value, PaperDataSourceType):
        return value
    try:
        return PaperDataSourceType(_require_non_empty_str(value, "source_type"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper data source_type: {value!r}") from exc


def _paper_intent_side_from_value(value: object) -> PaperIntentSide:
    if isinstance(value, PaperIntentSide):
        return value
    try:
        return PaperIntentSide(_require_non_empty_str(value, "side"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper intent side: {value!r}") from exc


def _paper_fill_status_from_value(value: object) -> PaperFillStatus:
    if isinstance(value, PaperFillStatus):
        return value
    try:
        return PaperFillStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper fill status: {value!r}") from exc


def _paper_cost_status_from_value(value: object) -> PaperCostStatus:
    if isinstance(value, PaperCostStatus):
        return value
    try:
        return PaperCostStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper cost status: {value!r}") from exc


def _paper_pnl_status_from_value(value: object) -> PaperPnLStatus:
    if isinstance(value, PaperPnLStatus):
        return value
    try:
        return PaperPnLStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper PnL status: {value!r}") from exc


def _paper_portfolio_risk_status_from_value(value: object) -> PaperPortfolioRiskStatus:
    if isinstance(value, PaperPortfolioRiskStatus):
        return value
    try:
        return PaperPortfolioRiskStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper portfolio risk status: {value!r}") from exc


def _paper_risk_limit_decision_status_from_value(value: object) -> PaperRiskLimitDecisionStatus:
    if isinstance(value, PaperRiskLimitDecisionStatus):
        return value
    try:
        return PaperRiskLimitDecisionStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper risk limit decision status: {value!r}") from exc


def _paper_intent_has_valid_size(intent: PaperIntent) -> bool:
    sizes = tuple(value for value in (intent.qty, intent.notional) if value is not None)
    return bool(sizes) and all(value >= 0.0 for value in sizes) and any(value > 0.0 for value in sizes)


def _paper_fill_has_valid_size(fill: PaperFill) -> bool:
    sizes = tuple(value for value in (fill.qty, fill.notional) if value is not None)
    return bool(sizes) and all(value >= 0.0 for value in sizes) and any(value > 0.0 for value in sizes)


def _paper_data_source_record_to_event(record: dict, *, venue: str, as_of_ns: int) -> MarketEvent:
    _reject_forbidden_data_source_keys(record)
    record_venue = _string_or_default(record.get("venue"), venue)
    if record_venue != venue:
        raise PaperShadowSessionCorruptError("paper data source record venue must match source venue")
    ts_ns = _require_non_negative_int(record.get("ts_ns"), "ts_ns")
    if ts_ns > as_of_ns:
        raise PaperShadowSessionCorruptError("paper data source record timestamp cannot be newer than as_of_ns")
    event = MarketEvent(
        symbol=_require_non_empty_str(record.get("symbol"), "symbol"),
        venue=record_venue,
        ts_ns=ts_ns,
        event_type=_market_event_type_from_value(record.get("event_type")),
        price=_optional_non_negative_float(record.get("price"), "price"),
        mark_price=_optional_non_negative_float(record.get("mark_price"), "mark_price"),
        index_price=_optional_non_negative_float(record.get("index_price"), "index_price"),
        funding_rate=_optional_float(record.get("funding_rate"), "funding_rate"),
        open_interest=_optional_non_negative_float(record.get("open_interest"), "open_interest"),
    )
    _validate_market_event(event)
    return event


def _reject_forbidden_data_source_keys(value: object) -> None:
    forbidden = {
        "api_key",
        "client",
        "credentials",
        "network_client",
        "password",
        "private_key",
        "secret",
        "token",
    }
    if isinstance(value, dict):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in forbidden:
                raise PaperShadowSessionCorruptError("paper data source payload cannot carry client or credential keys")
            _reject_forbidden_data_source_keys(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _reject_forbidden_data_source_keys(item)


def _rejected_event_increment(batch: object) -> int:
    if isinstance(batch, MarketEventBatch):
        return max(1, len(batch.events))
    if isinstance(batch, dict):
        events = batch.get("events")
        if isinstance(events, (list, tuple)):
            return max(1, len(events))
    return 1


def _require_non_negative_float(value: object, field_name: str) -> float:
    parsed = _optional_non_negative_float(value, field_name)
    if parsed is None:
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} must be numeric")
    return parsed


def _require_float(value: object, field_name: str) -> float:
    parsed = _optional_float(value, field_name)
    if parsed is None:
        raise PaperShadowSessionCorruptError(f"field {field_name!r} must be numeric")
    return parsed


def _optional_non_negative_float(value: object, field_name: str) -> float | None:
    parsed = _optional_float(value, field_name)
    if parsed is not None and parsed < 0.0:
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} cannot be negative")
    return parsed


def _optional_float(value: object, field_name: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} must be numeric or None")
    parsed = float(value)
    if not math.isfinite(parsed):
        raise PaperShadowSessionCorruptError(f"market event field {field_name!r} must be finite")
    return parsed


def _session_status_or_default(value: object, default: PaperShadowSessionStatus) -> PaperShadowSessionStatus:
    if value is None:
        return default
    if isinstance(value, PaperShadowSessionStatus):
        return value
    try:
        return PaperShadowSessionStatus(_require_non_empty_str(value, "status"))
    except ValueError as exc:
        raise PaperShadowSessionCorruptError(f"Invalid paper/shadow session status: {value!r}") from exc


def _require_non_empty_str(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value:
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be a non-empty string")
    return value


def _string_or_default(value: object, default: str) -> str:
    if value is None:
        return default
    if not isinstance(value, str):
        raise PaperShadowSessionCorruptError("paper/shadow session string fields must be strings")
    return value or default


def _optional_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    return _require_non_empty_str(value, field_name)


def _require_non_negative_int(value: object, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be a non-negative int")
    return value


def _optional_non_negative_int(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    return _require_non_negative_int(value, field_name)


def _bool_or_default(data: dict, field_name: str, default: bool) -> bool:
    value = data.get(field_name, default)
    return _require_bool(value, field_name)


def _require_bool(value: object, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise PaperShadowSessionCorruptError(f"paper/shadow session field {field_name!r} must be bool")
    return value


def _dict_value(value: object, field_name: str) -> dict:
    if not isinstance(value, dict):
        raise PaperShadowSessionCorruptError(f"{field_name} must contain dict entries")
    return dict(value)


def _report_summary_from_data(value: object, field_name: str) -> dict:
    summary = _dict_value(value, field_name)
    _validate_report_summary(summary, field_name)
    return summary


def _validate_report_summary(value: object, field_name: str) -> None:
    if not isinstance(value, dict):
        raise PaperShadowSessionCorruptError(f"paper/shadow run evidence {field_name} must be a dict")
    if "available" in value:
        _require_bool(value["available"], f"{field_name}.available")
    _validate_jsonish(value, field_name)


def _report_summary_available(value: dict) -> bool:
    return value.get("available") is True


def _validate_jsonish(value: object, field_name: str) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise PaperShadowSessionCorruptError(f"paper/shadow run evidence {field_name} must be finite")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_jsonish(item, f"{field_name}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key:
                raise PaperShadowSessionCorruptError(
                    f"paper/shadow run evidence {field_name} requires non-empty string keys"
                )
            _validate_jsonish(item, f"{field_name}.{key}")
        return
    raise PaperShadowSessionCorruptError(
        f"paper/shadow run evidence {field_name} contains non-serializable {type(value).__name__!r}"
    )


def _sorted_unique(values: object) -> tuple[str, ...]:
    if values is None:
        return ()
    if not isinstance(values, (list, tuple)):
        raise PaperShadowSessionCorruptError("paper/shadow session string collections must be list/tuple")
    result: list[str] = []
    for value in values:
        if not isinstance(value, str) or not value:
            raise PaperShadowSessionCorruptError("paper/shadow session string collections require non-empty strings")
        if value not in result:
            result.append(value)
    return tuple(sorted(result))
