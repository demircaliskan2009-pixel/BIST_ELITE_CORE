"""Governed admitted-variant paper execution (GOVERNED_PAPER_TYPED_PROVENANCE_V2): day seals and lineage evidence.

Design authority: ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7. Paper-only, deterministic,
point-in-time and fail-closed. It creates no order, reserves no capital and proves no venue fill or readiness.

The ONE economics authority is ``historical_execution_economics``. Every day ``k`` (window ``[E_k, E_{k+1})``) is sealed
at ``E_{k+1}`` by an authenticated prefix replay from the immutable genesis G:

* the decision run over ``[G, E_{k+1})`` and its economics are BUILT here from the archive ``dataset_k`` and the
  genesis's canonical authorities (never supplied), then re-run under the neutral admission schedule of every
  AUTHORIZED cycle so far (``simulate_historical_execution_governed_paper``). The archive holds only records known at
  ``E_{k+1}``, and it must reproduce the cycle's opening quote ``m(E_k)``;
* entry safety (``S1_PAPER_ENTRY_SAFETY_CLOSURE_V1``, ``governed_paper_entry_safety``): every decision of the run whose
  resulting direction is LONG or SHORT is evaluated at its own decision instant against the PRDV4 §1.21 NO-TRADE
  conditions and the §1.9 Family B gates, over the archive and the genesis facts. The schedule lists every refused
  decision and the engine refuses its entry, never an exit. The seal carries the day's evaluations and the digest of
  the whole evaluation;
* the engine content of every event before ``E_k`` must equal the previous seal's (X1, the prefix digest); the intent
  the previous replay's end left pending is excluded from both prefixes and keeps its deciding-cycle lineage (B3);
* the closing head attestation at ``E_{k+1}`` validates or invalidates the day, never authorizes it (X3). A changed head
  needs the re-proven successor receipts, effective inside the day, and their earliest instant invalidates every later
  decision and fill inside the economics (X2). A successor inside an already sealed day is a contradiction;
* the day's executed fills are projected through the accepted generic paper chain (capacity gate over the deciding
  cycle's derived reservation, order request, signal bridge, admission, intent, pass-through fill, position, PnL report,
  episode run, realized PnL and end-to-end episode). Every primitive must equal the engine exactly (X4); a fill on a
  side its deciding cycle did not authorize blocks the day (B2, defence in depth: the engine already refuses it);
* funding (B4): a settlement whose rendered scale-18 amount is not EXACTLY ``-q * m * r`` over the engine's own factors
  blocks the day, and the cumulative funding of the sealed events must equal the engine's at the day boundary. Rounded
  values never re-enter accounting as exact truth;
* the day close is the engine's own visible mark at ``E_{k+1}`` and the chain position after the day's fills.

The governed outcome itself is re-provable by anyone through ``verify_governed_paper_outcome``: typed identity
against a re-run of the engine under the outcome's own schedule, so the engine never depends on this contract.

A seal is a LOCAL derivation that trusts its predecessor seal only after recomputing its self-digest and typed form.
Only ``GovernedPaperExecutionEvidence`` proves a lineage: it re-proves every cycle and every seal by typed identity
against its rebuild and binds them pairwise (history, closing attestation, prefix, archive growth, pending lineage,
invalidation). A forged or stale seal never inherits authentic status.

Protective lineage (``PROTECTIVE_POSITION_LIFECYCLE_V1``, seal v3 and evidence v3). Every seal of a protective lineage,
from day 0 on, carries ``GovernedPaperDayProtectionInputs``; a lineage never switches mid-way, in either direction:

* the protective authority (DEC-1, ``governed_paper_protective_authority``) is re-proven, of this genesis and the same
  on every day; an authentic authority that is not AUTHORIZED blocks the day. Its human revocations must be effective
  inside the day, and the earliest instant ever revoked persists. Its window, ended by its expiry or that revocation,
  is the schedule's protective window (schedule v3);
* the replay builds the economics under the authority's position-management policy and the day's authenticated OHLC
  archive (only bars known at ``E_{k+1}``, of the adopted source). The entry gate evaluates rule set v2 on the same
  protective context, so backtest and governed paper apply one protective semantics;
* X4 for a protective fill: it is projected through the reservation of the cycle that decided its excursion's opening
  intent, which is today's cycle, the pending cycle, or the excursion cycle the previous seal named. A protective fill
  must be close-only, never bound to the cycle's direction authority (DEC-1). An excursion still open at ``E_{k+1}``
  names its deciding cycle, and the next seal must be given exactly that cycle, re-proven;
* X1 for a protective attempt left pending by the replay's end: it is excluded from both prefixes by its attempt instant
  and fills, or not, in a later day's replay. The day's protective obligations, and those still outstanding, are
  counted.

Without protection inputs, every seal and evidence is exactly the accepted v2 artifact.

Native portfolio NO-TRADE lineage (``S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1``, seal v4 and evidence v4). A protective
lineage whose protection inputs set ``portfolio_no_trade`` does so on every day from day 0, and never switches. Its
entry gate evaluates rule set v3: NT-R02, NT-R03 and NT-R04 on the governed decision portfolio the one engine derives
under the schedule. The admissions are sequential (``governed_paper_entry_safety_sequential_refusals``): the replay
starts from every entry refused and re-evaluates under the previous round's refusals until the schedule refuses
exactly the entries its own evaluation refuses, the unique causal fixed point, so each entry is judged on the portfolio
its admitted predecessors produced. The engine then re-runs under that schedule. Every other rule is the v3 lineage's,
and without ``portfolio_no_trade`` every protective seal and evidence is exactly the accepted v3 artifact.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EdgeKillQuarantineDecision,
    EdgeLifecycleState,
    verify_edge_kill_quarantine_decision,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GovernedPaperEntrySafetyDecision,
    GovernedPaperEntrySafetyEvidence,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyProtection,
    build_governed_paper_entry_safety_evidence,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_sequential_refusals,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperApprovalKind,
    GovernedPaperCycleAuthority,
    GovernedPaperCycleInputs,
    GovernedPaperCycleReservation,
    GovernedPaperCycleStatus,
    GovernedPaperGenesis,
    GovernedPaperGenesisAuthority,
    GovernedPaperGenesisInputs,
    governed_paper_cycle_admission_window,
    governed_paper_cycle_authority_digest,
    governed_paper_cycle_reservation,
    governed_paper_genesis_authority,
    governed_paper_sealed_history_digest,
    verify_governed_paper_cycle_authority,
)
from crypto_core.validation.governed_paper_protective_authority import (
    GovernedPaperProtectiveAuthority,
    GovernedPaperProtectiveAuthorityError,
    GovernedPaperProtectiveAuthorityInputs,
    GovernedPaperProtectiveContext,
    GovernedPaperProtectiveRevocation,
    governed_paper_protective_authority_context,
    governed_paper_protective_window,
    verify_governed_paper_protective_revocation,
)
from crypto_core.validation.governed_paper_typed_identity import (
    GovernedPaperTypeDomain,
    governed_paper_typed_image,
    governed_paper_verify_rebuilt,
)
from crypto_core.validation.historical_decision_run import build_historical_decision_run
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionExcursionProtection,
    HistoricalExecutionFill,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionPositionManagementInputs,
    HistoricalExecutionProtectiveObligationStatus,
    HistoricalExecutionProtectiveWindow,
    HistoricalExecutionSide,
    HistoricalExecutionTransitionKind,
    build_historical_execution_economics,
    historical_execution_admission_schedule_digest,
    historical_execution_admission_schedule_to_dict,
    historical_execution_governed_paper_outcome_to_dict,
    historical_execution_governed_paper_prefix_digest,
    historical_execution_latest_visible_mark,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_wire_int_is_valid
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBar,
    HistoricalOhlcBarArchive,
    verify_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, verify_historical_pit_dataset
from crypto_core.validation.paper_capacity_gate import PaperCapacityGateStatus, evaluate_paper_capacity_gate
from crypto_core.validation.paper_end_to_end_episode import PaperEndToEndEpisodeStatus, build_paper_end_to_end_episode
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
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot, compute_paper_pnl_report
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperLifecycleHeadAuthority,
    PaperLifecycleHeadAuthorityApprovalKind,
    PaperLifecycleHeadAuthorityInputs,
    paper_lifecycle_head_authority_digest,
    verify_paper_lifecycle_head_authority,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    paper_position_state_digest,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDayCloseValuation,
    PaperSleeveEpisodeEvidence,
)
from crypto_core.validation.paper_sleeve_funding_evidence import PaperSleeveFundingEvent
from crypto_core.validation.strategy_signal_to_paper_intent import (
    StrategySignalToPaperIntentStatus,
    build_strategy_signal_to_paper_intent,
)

_PREFIX = "governed_admitted_variant_paper_execution"
_SEAL_SCHEMA_VERSION = "governed-paper-day-seal.v2"
_PROTECTIVE_SEAL_SCHEMA_VERSION = "governed-paper-day-seal.v3"
_PORTFOLIO_SEAL_SCHEMA_VERSION = "governed-paper-day-seal.v4"
_EVIDENCE_SCHEMA_VERSION = "governed-paper-execution-evidence.v2"
_PROTECTIVE_EVIDENCE_SCHEMA_VERSION = "governed-paper-execution-evidence.v3"
_PORTFOLIO_EVIDENCE_SCHEMA_VERSION = "governed-paper-execution-evidence.v4"
_PROTECTIVE_SEALS = (_PROTECTIVE_SEAL_SCHEMA_VERSION, _PORTFOLIO_SEAL_SCHEMA_VERSION)
_SEAL_DIGEST_FIELD = "seal_digest"
_EVIDENCE_DIGEST_FIELD = "evidence_digest"
_UTC_DAY_NS = 86_400_000_000_000
_BPS = Fraction(10_000)
_EXECUTED = (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)

GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("synthetic_paper_simulation", True),
    ("execution_authorized", False),
    ("venue_orders_created", False),
    ("venue_fill_truth_proven", False),
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
    ("archive_completeness_proven", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


class GovernedPaperExecutionError(EdgeArtifactError):
    """Malformed input or a provenance defect: an invalid seal or evidence is never represented."""


class GovernedPaperDaySealStatus(str, Enum):
    SEALED = "SEALED"
    BLOCKED = "BLOCKED"


class GovernedPaperExecutionStatus(str, Enum):
    READY = "READY"
    BLOCKED = "BLOCKED"


@dataclass(frozen=True)
class GovernedPaperDaySeal:
    """The retrospective seal of one UTC paper day: the replay's identities and the cumulative projected history."""

    schema_version: str
    status: GovernedPaperDaySealStatus
    sealed: bool
    seal_id: str
    correlation_id: str
    genesis_id: str
    genesis_digest: str
    sleeve_id: str
    instrument: str
    day_index: int
    window_start_ns: int
    window_end_ns: int
    cycle_id: str
    cycle_digest: str
    cycle_status: str
    cycle_phase: str
    prior_seal_digest: str
    schedule: HistoricalExecutionAdmissionSchedule
    schedule_digest: str
    authorized_day_indexes: tuple[int, ...]
    invalidated_from_ns: int | None
    closing_head_authority_digest: str
    closing_lifecycle_head_digest: str
    successor_receipt_digests: tuple[str, ...]
    dataset_digest: str
    dataset_record_count: int
    decision_run_digest: str
    economics_result_digest: str
    governed_outcome_digest: str
    prefix_digest_open: str
    prefix_digest_close: str
    pending_decision_sequence: int | None
    pending_deciding_day_index: int | None
    pending_deciding_cycle_digest: str | None
    governance_rejected_fill_count: int
    entry_safety_rule_set_digest: str
    entry_safety_evidence_digest: str
    entry_safety_decisions: tuple[GovernedPaperEntrySafetyDecision, ...]
    episodes: tuple[PaperSleeveEpisodeEvidence, ...]
    episode_deciding_cycle_digests: tuple[str, ...]
    day_closes: tuple[PaperSleeveDayCloseValuation, ...]
    funding_events: tuple[PaperSleeveFundingEvent, ...]
    day_episode_count: int
    day_funding_event_count: int
    sealed_history_digest: str
    close_position_quantity: str
    close_cumulative_funding: str
    reason_codes: tuple[str, ...]
    seal_digest: str
    paper_only: bool = True
    synthetic_paper_simulation: bool = True
    execution_authorized: bool = False
    venue_orders_created: bool = False
    venue_fill_truth_proven: bool = False
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
    archive_completeness_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    # Seal v3 only (a protective lineage, PROTECTIVE_POSITION_LIFECYCLE_V1): a v2 payload carries none of these.
    protective_authority_digest: str = ""
    protective_revocation_digests: tuple[str, ...] = ()
    protective_revoked_from_ns: int | None = None
    ohlc_archive_digest: str = ""
    ohlc_bar_count: int = 0
    open_excursion_deciding_day_index: int | None = None
    open_excursion_deciding_cycle_digest: str | None = None
    pending_protective_attempt_time_ns: int | None = None
    day_protective_obligation_count: int = 0
    outstanding_protective_obligation_count: int = 0


_SEAL_V3_FIELDS = (
    "protective_authority_digest",
    "protective_revocation_digests",
    "protective_revoked_from_ns",
    "ohlc_archive_digest",
    "ohlc_bar_count",
    "open_excursion_deciding_day_index",
    "open_excursion_deciding_cycle_digest",
    "pending_protective_attempt_time_ns",
    "day_protective_obligation_count",
    "outstanding_protective_obligation_count",
)


@dataclass(frozen=True)
class GovernedPaperDayProtectionInputs:
    """The protective inputs of one day of a protective lineage (PROTECTIVE_POSITION_LIFECYCLE_V1).

    ``revocations`` are the human revocations effective inside this day. ``ohlc_archive`` holds the adopted source's bars
    known at ``E_{k+1}``. The excursion cycle is the cycle that decided the opening intent of an excursion the previous
    seal left open; it is None exactly when no excursion was open then. ``portfolio_no_trade`` selects the native
    portfolio NO-TRADE lineage (seal v4, entry rule set v3) for the whole lineage.
    """

    authority_inputs: GovernedPaperProtectiveAuthorityInputs
    authority: GovernedPaperProtectiveAuthority
    revocations: tuple[GovernedPaperProtectiveRevocation, ...]
    ohlc_archive: HistoricalOhlcBarArchive
    excursion_cycle_inputs: GovernedPaperCycleInputs | None
    excursion_cycle: GovernedPaperCycleAuthority | None
    portfolio_no_trade: bool = False


@dataclass(frozen=True)
class GovernedPaperDaySealInputs:
    """Everything one day seal consumes; the pending cycle is the deciding cycle of the previous seal's pending intent."""

    seal_id: str
    correlation_id: str
    day_index: int
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    cycle_inputs: GovernedPaperCycleInputs
    cycle: GovernedPaperCycleAuthority
    prior_seal: GovernedPaperDaySeal | None
    pending_cycle_inputs: GovernedPaperCycleInputs | None
    pending_cycle: GovernedPaperCycleAuthority | None
    dataset: HistoricalPitDataset
    closing_head_authority_inputs: PaperLifecycleHeadAuthorityInputs
    closing_head_authority: PaperLifecycleHeadAuthority
    successor_receipts: tuple[EdgeKillQuarantineDecision, ...]
    protection: GovernedPaperDayProtectionInputs | None = None


@dataclass(frozen=True)
class GovernedPaperExecutionDay:
    """One day of the lineage: its cycle and its seal, each with the exact inputs it is rebuilt from."""

    cycle_inputs: GovernedPaperCycleInputs
    cycle: GovernedPaperCycleAuthority
    seal_inputs: GovernedPaperDaySealInputs
    seal: GovernedPaperDaySeal


@dataclass(frozen=True)
class GovernedPaperExecutionInputs:
    evidence_id: str
    correlation_id: str
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    days: tuple[GovernedPaperExecutionDay, ...]


@dataclass(frozen=True)
class GovernedPaperExecutionDayRecord:
    day_index: int
    cycle_digest: str
    cycle_status: str
    cycle_phase: str
    long_authorized: bool
    short_authorized: bool
    seal_digest: str
    seal_status: str
    day_episode_count: int
    day_funding_event_count: int
    governance_rejected_fill_count: int
    pending_decision_sequence: int | None
    sealed_history_digest: str


@dataclass(frozen=True)
class GovernedPaperExecutionEvidence:
    """Terminal public evidence of one governed paper lineage: every cycle and seal re-proven and bound pairwise."""

    schema_version: str
    status: GovernedPaperExecutionStatus
    ready: bool
    evidence_id: str
    correlation_id: str
    genesis_id: str
    genesis_digest: str
    genesis_inputs_identity_digest: str
    sleeve_id: str
    instrument: str
    genesis_start_ns: int
    day_count: int
    sealed_day_count: int
    days: tuple[GovernedPaperExecutionDayRecord, ...]
    bootstrap_b0_day_count: int
    bootstrap_b1_day_count: int
    ordinary_day_count: int
    first_ordinary_day_index: int | None
    terminal_seal_digest: str
    terminal_sealed_history_digest: str
    terminal_episode_count: int
    terminal_day_close_count: int
    terminal_funding_event_count: int
    terminal_invalidated_from_ns: int | None
    lineage_digest: str
    reason_codes: tuple[str, ...]
    evidence_digest: str
    paper_only: bool = True
    synthetic_paper_simulation: bool = True
    execution_authorized: bool = False
    venue_orders_created: bool = False
    venue_fill_truth_proven: bool = False
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
    archive_completeness_proven: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    # Evidence v3 only (a protective lineage): a v2 payload carries none of these.
    protective_authority_digest: str = ""
    terminal_protective_revoked_from_ns: int | None = None
    terminal_outstanding_protective_obligation_count: int = 0


_EVIDENCE_V3_FIELDS = (
    "protective_authority_digest",
    "terminal_protective_revoked_from_ns",
    "terminal_outstanding_protective_obligation_count",
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperExecutionError:
    return GovernedPaperExecutionError(_reason(code))


class _Blocked(Exception):
    """Internal: a represented BLOCKED day (never escapes the module)."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


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


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        if type(value) is StrategySpec:
            return {"strategy_spec_digest": strategy_spec_digest(value)}
        if type(value) is HistoricalExecutionAdmissionSchedule:  # the engine's own (versioned) wire payload
            return historical_execution_admission_schedule_to_dict(value)
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _is_neutral(value: object) -> bool:
    return (
        value is None
        or (type(value) is tuple and value == ())
        or (type(value) is str and value == "")
        or (type(value) is int and value == 0)
    )


def _to_payload(artifact: object) -> dict[str, object]:
    """The wire payload of one artifact; a v2 seal or evidence carries exactly its v2 fields.

    A v2 artifact holding a non-neutral v3 field is never serialized (``ValueError``): a forged protective fact never
    hides behind the legacy payload.
    """

    payload = {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]
    legacy = _LEGACY_PAYLOADS.get(type(artifact))
    if legacy is not None and getattr(artifact, "schema_version", None) == legacy[0]:
        for name in legacy[1]:
            if not _is_neutral(getattr(artifact, name)):
                raise ValueError(f"{_PREFIX}:legacy_schema_carries_an_extension_field:{name}")
            del payload[name]
    return payload


_LEGACY_PAYLOADS: dict[type, tuple[str, tuple[str, ...]]] = {
    GovernedPaperDaySeal: (_SEAL_SCHEMA_VERSION, _SEAL_V3_FIELDS),
    GovernedPaperExecutionEvidence: (_EVIDENCE_SCHEMA_VERSION, _EVIDENCE_V3_FIELDS),
}


def _plain(value: Fraction) -> str:
    """Exact plain decimal text of a terminating value (the generic paper grammar)."""

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
            raise _Blocked("projection_value_not_terminating")
        scale += 1
    digits = str(abs(numerator)).rjust(scale + 1, "0")
    text = f"{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".") if scale else digits
    return f"-{text}" if numerator < 0 else text


def _visibility(record: object) -> int:
    finalized = record.finalized_at_ns  # type: ignore[attr-defined]
    return record.available_at_ns if finalized is None else max(record.available_at_ns, finalized)  # type: ignore[attr-defined]


def _spec_resolver() -> Mapping[type, Callable[[object], str]]:
    return {StrategySpec: lambda spec: strategy_spec_digest(spec)}  # type: ignore[arg-type]


_SEAL_DOMAIN = GovernedPaperTypeDomain(_SEAL_SCHEMA_VERSION, roots=(GovernedPaperDaySeal,), references=(StrategySpec,))
# The typed identity domain of the engine's governed outcome: the closure of its declared schema (TCI_V1).
_OUTCOME_DOMAIN = GovernedPaperTypeDomain(
    HISTORICAL_EXECUTION_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION, roots=(HistoricalExecutionGovernedPaperOutcome,)
)
_EVIDENCE_DOMAIN = GovernedPaperTypeDomain(_EVIDENCE_SCHEMA_VERSION, roots=(GovernedPaperExecutionEvidence,))


def verify_governed_paper_outcome(
    outcome: object, *, result: object, expected_result_digest: object
) -> EdgeEvidenceVerification:
    """Re-prove one governed engine outcome by typed identity against a re-run under its own schedule. Total.

    Exact type, typed image, the carried ``outcome_digest`` recomputed over the engine's wire payload, then typed
    identity field by field against ``simulate_historical_execution_governed_paper`` over the authenticated ``result``.
    """

    def rebuild() -> object:
        return simulate_historical_execution_governed_paper(
            result,  # type: ignore[arg-type]
            expected_result_digest=expected_result_digest,  # type: ignore[arg-type]
            schedule=outcome.schedule,  # type: ignore[attr-defined]
        )

    return governed_paper_verify_rebuilt(
        outcome,
        cls=HistoricalExecutionGovernedPaperOutcome,
        domain=_OUTCOME_DOMAIN,
        to_payload=historical_execution_governed_paper_outcome_to_dict,  # type: ignore[arg-type]
        digest_field="outcome_digest",
        rebuild=rebuild,
        code="governed_paper_outcome",
        reason=_reason,
    )


def governed_paper_day_seal_to_dict(seal: GovernedPaperDaySeal) -> dict[str, object]:
    """Canonical JSON-ready mapping of a seal; a StrategySpec appears as its public digest."""

    return _to_payload(seal)


def governed_paper_day_seal_digest(seal: GovernedPaperDaySeal) -> str:
    return edge_payload_digest(_to_payload(seal), _SEAL_DIGEST_FIELD)


def _prior_seal(seal: object, *, day: int, genesis_digest: str) -> GovernedPaperDaySeal:
    """The previous seal, trusted locally only after its self-digest and typed form are recomputed."""

    if type(seal) is not GovernedPaperDaySeal:
        raise _fail("prior_seal_malformed")
    try:
        governed_paper_typed_image(seal, _SEAL_DOMAIN, resolve=_spec_resolver())
        recomputed = governed_paper_day_seal_digest(seal)
    except Exception as exc:  # noqa: BLE001 - an uncanonical seal is never a predecessor
        raise _fail("prior_seal_not_canonically_typed") from exc
    if recomputed != seal.seal_digest:
        raise _fail("prior_seal_digest_mismatch")
    if seal.day_index != day - 1 or seal.genesis_digest != genesis_digest:
        raise _fail("prior_seal_not_the_previous_day")
    if seal.status is not GovernedPaperDaySealStatus.SEALED or seal.sealed is not True:
        raise _fail("prior_seal_not_sealed")
    return seal


# --- the projection (X4): the accepted generic chain over each executed engine fill --------------------------------------


@dataclass
class _Chain:
    state: PaperPositionState
    episodes: list[PaperSleeveEpisodeEvidence]
    deciding: list[str]


def _exact(text: object, expected: Fraction, field_name: str) -> None:
    if type(text) is not str or Fraction(text) != expected:
        raise _Blocked(f"projection_not_exact:{field_name}")


def _episode(
    authority: GovernedPaperGenesisAuthority,
    reservation: GovernedPaperCycleReservation,
    fill: HistoricalExecutionFill,
    prior: PaperPositionState,
    *,
    base: str,
    side: HistoricalExecutionSide,
    requested_quantity: str,
    mark_price: str,
    transition: object,
) -> PaperSleeveEpisodeEvidence:
    """One executed engine fill projected onto the generic paper chain; ``base`` names the decision or attempt."""

    genesis = authority.genesis
    correlation = f"corr-{base}"
    order_side = PaperOrderSide.BUY if side is HistoricalExecutionSide.BUY else PaperOrderSide.SELL
    requested = Fraction(requested_quantity)
    units = _plain(requested)
    notional = _plain(requested * Fraction(reservation.cycle.reservation_price))
    decision = evaluate_paper_capacity_gate(
        reservation.allocator_draft,
        reservation.capacity_policy,
        requested_notional=notional,
        requested_units=units,
        correlation_id=correlation,
    )
    if decision.status is not PaperCapacityGateStatus.ADMITTED:
        raise _Blocked("projection_capacity_not_admitted")
    request = build_paper_order_intent_request(
        request_id=f"req-{base}",
        capacity_decision_digest=decision.decision_digest,
        market_symbol=genesis.instrument,
        side=order_side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=notional,
        requested_units=units,
        limit_price=None,
        correlation_id=correlation,
    )
    spec = authority.strategy_spec
    bridge = build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=genesis.strategy_spec_digest,
        signal_id=f"req-{base}",
        run_id=f"run-{base}",
        correlation_id=correlation,
        market_symbol=genesis.instrument,
        side=order_side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units=units,
        requested_notional=notional,
        capacity_decision_digest=decision.decision_digest,
        limit_price=None,
    )
    admission = evaluate_paper_order_intent_admission(decision, request, correlation_id=correlation)
    if (
        bridge.status is not StrategySignalToPaperIntentStatus.READY
        or admission.status is not PaperOrderIntentAdmissionStatus.ADMITTED
    ):
        raise _Blocked("projection_intent_not_admitted")
    order_intent = build_paper_order_intent(admission, intent_id=f"intent-{base}", correlation_id=correlation)
    executed_at = fill.execution_time_ns
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"snap-{base}",
        market_symbol=genesis.instrument,
        reference_price=_plain(Fraction(fill.fill_price)),  # type: ignore[arg-type]
        available_units=_plain(Fraction(fill.filled_quantity)),
        observed_at_ns=executed_at,
    )
    fill_policy = build_paper_fill_policy(
        policy_id=f"{genesis.genesis_id}-pass-through",
        slippage_bps="0",
        fee_rate_bps=_plain(Fraction(authority.economics_policy.taker_fee_bps)),
        allow_partial_fill=True,
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"mark-{base}",
        market_symbol=genesis.instrument,
        mark_price=_plain(Fraction(mark_price)),
        observed_at_ns=executed_at,
        correlation_id=correlation,
    )
    ids = {
        "fill_simulation_id": f"fill-{base}",
        "position_transition_id": f"trans-{base}",
        "new_position_state_id": f"pos-{base}",
        "pnl_report_id": f"pnl-{base}",
    }
    run = run_paper_episode(
        order_intent,
        prior,
        snapshot,
        fill_policy,
        mark,
        **ids,
        episode_run_id=f"run-result-{base}",
        correlation_id=correlation,
    )
    result = simulate_paper_fill(
        order_intent, snapshot, fill_policy, fill_simulation_id=ids["fill_simulation_id"], correlation_id=correlation
    )
    position_transition, new_state = apply_paper_fill_to_position(
        prior,
        result,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=correlation,
    )
    if run.status is not PaperEpisodeRunStatus.COMPUTED or new_state is None:
        raise _Blocked("projection_episode_not_computed")
    report = compute_paper_pnl_report(new_state, mark, pnl_report_id=ids["pnl_report_id"], correlation_id=correlation)
    event = compute_paper_realized_pnl_event(
        prior, result, position_transition, new_state, realized_pnl_event_id=f"rpnl-{base}", correlation_id=correlation
    )
    episode = build_paper_end_to_end_episode(
        bridge,
        order_intent,
        run,
        event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=order_intent.intent_digest,
        expected_episode_run_digest=run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=f"episode-{base}",
        run_id=f"run-{base}",
        correlation_id=correlation,
    )
    if episode.status is not PaperEndToEndEpisodeStatus.READY:
        raise _Blocked("projection_episode_not_ready")
    # X4: every primitive is the engine's, exactly; nothing is recomputed into a second economics.
    expected_status = (
        PaperFillSimulationStatus.FILLED
        if fill.outcome is HistoricalExecutionFillOutcome.FILLED
        else PaperFillSimulationStatus.PARTIALLY_FILLED
    )
    if result.status is not expected_status:
        raise _Blocked("projection_not_exact:fill_status")
    _exact(result.fill_price, Fraction(fill.fill_price), "fill_price")  # type: ignore[arg-type]
    _exact(result.filled_units, Fraction(fill.filled_quantity), "filled_units")
    _exact(
        result.fee_amount,
        Fraction(fill.fill_price)
        * Fraction(fill.filled_quantity)
        * Fraction(authority.economics_policy.taker_fee_bps)
        / _BPS,  # type: ignore[arg-type]
        "fee_amount",
    )
    _exact(new_state.signed_units, Fraction(transition.post_quantity), "post_position")  # type: ignore[attr-defined]
    _exact(event.realized_pnl, Fraction(transition.realized_gross_pnl), "realized_pnl")  # type: ignore[attr-defined]
    return PaperSleeveEpisodeEvidence(
        capacity_policy=reservation.capacity_policy,
        allocator_draft=reservation.allocator_draft,
        capacity_decision=decision,
        order_intent_request=request,
        admission_decision=admission,
        order_intent=order_intent,
        strategy_spec=spec,
        signal_bridge=bridge,
        prior_position_state=prior,
        fill_market_snapshot=snapshot,
        fill_policy=fill_policy,
        episode_mark_snapshot=mark,
        fill_result=result,
        position_transition=position_transition,
        new_position_state=new_state,
        episode_pnl_report=report,
        episode_run=run,
        realized_pnl_event=event,
        end_to_end_episode=episode,
    )


# --- the day seal --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _SealProof:
    facts: dict[str, object]
    blocked: tuple[str, ...]
    protective: bool = False
    portfolio: bool = False


def _closing(inputs: GovernedPaperDaySealInputs, cycle: GovernedPaperCycleAuthority, sleeve_id: str, end: int):  # noqa: ANN202
    head, head_inputs = inputs.closing_head_authority, inputs.closing_head_authority_inputs
    if type(head) is not PaperLifecycleHeadAuthority or type(head_inputs) is not PaperLifecycleHeadAuthorityInputs:
        raise _fail("closing_head_authority_malformed")
    verification = verify_paper_lifecycle_head_authority(head, head_inputs)
    if not verification.intact or verification.recomputed_digest != head.authority_digest:
        raise _fail("closing_head_authority_not_authentic")
    if head.sleeve_id != sleeve_id or head.evaluation_end_ns != end:
        raise _fail("closing_head_authority_not_at_the_seal")
    attested = (
        head.paper_current_head_attested is True
        and head.synthetic_test_approval_used is False
        and head.approval is not None
        and head.approval.approval_kind is PaperLifecycleHeadAuthorityApprovalKind.HUMAN_GOVERNANCE
    )
    receipts = inputs.successor_receipts
    if type(receipts) is not tuple or any(type(item) is not EdgeKillQuarantineDecision for item in receipts):
        raise _fail("successor_receipts_malformed")
    digests: list[str] = []
    previous = cycle.lifecycle_head_digest
    effective: int | None = None
    for receipt in receipts:
        verification = verify_edge_kill_quarantine_decision(receipt)
        if not verification.intact or not edge_is_hex64(verification.recomputed_digest):
            raise _fail("successor_receipt_not_authentic")
        if receipt.prior_digest != previous or receipt.paper_sleeve_id != sleeve_id:
            raise _fail("successor_receipt_not_a_direct_successor")
        if not cycle.window_start_ns < receipt.effective_at_ns <= end:
            raise _fail("successor_receipt_outside_the_sealed_day")
        if receipt.resulting_lifecycle_state is EdgeLifecycleState.ACTIVE:
            raise _fail("successor_receipt_reactivates_inside_the_day")
        effective = receipt.effective_at_ns if effective is None else effective
        previous = verification.recomputed_digest
        digests.append(previous)
    if head.lifecycle_head_digest != previous:
        raise _fail("closing_head_not_reached_by_the_successors")
    return paper_lifecycle_head_authority_digest(head), head.lifecycle_head_digest, tuple(digests), effective, attested


@dataclass(frozen=True)
class _DayProtection:
    """The verified protective inputs of one day of a protective lineage (``context`` is None unless AUTHORIZED)."""

    authority: GovernedPaperProtectiveAuthority
    context: GovernedPaperProtectiveContext | None
    revocation_digests: tuple[str, ...]
    revoked_from_ns: int | None
    window: HistoricalExecutionProtectiveWindow | None
    archive: HistoricalOhlcBarArchive
    archive_digest: str
    excursion: GovernedPaperCycleReservation | None
    portfolio_no_trade: bool


def _day_protection(  # noqa: C901 - one linear proof of the protective inputs
    inputs: GovernedPaperDaySealInputs,
    prior: GovernedPaperDaySeal | None,
    *,
    genesis: GovernedPaperGenesis,
    start: int,
    end: int,
) -> _DayProtection | None:
    """Re-prove the protective inputs of one day; a lineage is protective from day 0 on, or never."""

    protection = inputs.protection
    if protection is not None and type(protection) is not GovernedPaperDayProtectionInputs:
        raise _fail("protection_inputs_malformed")
    if prior is not None and (prior.schema_version in _PROTECTIVE_SEALS) is not (protection is not None):
        raise _fail("protective_lineage_switched")
    if protection is None:
        return None
    if type(protection.portfolio_no_trade) is not bool:
        raise _fail("protection_inputs_malformed:portfolio_no_trade")
    if (
        prior is not None
        and (prior.schema_version == _PORTFOLIO_SEAL_SCHEMA_VERSION) is not protection.portfolio_no_trade
    ):
        raise _fail("portfolio_no_trade_lineage_switched")
    authority, authority_inputs = protection.authority, protection.authority_inputs
    if type(authority) is not GovernedPaperProtectiveAuthority:
        raise _fail("protective_authority_malformed")
    try:  # one re-proof: the canonical context of an AUTHORIZED authority, None for an authentic unauthorized one
        context = governed_paper_protective_authority_context(authority, authority_inputs)
    except GovernedPaperProtectiveAuthorityError as exc:
        raise _fail("protective_authority_not_authentic") from exc
    if authority.genesis_digest != genesis.genesis_digest:
        raise _fail("protective_authority_foreign")
    if prior is not None and authority.authority_digest != prior.protective_authority_digest:
        raise _fail("protective_authority_changed_inside_the_lineage")

    # Human revocations effective inside this day; the earliest instant ever revoked persists.
    revocations = protection.revocations
    if type(revocations) is not tuple or any(
        type(item) is not GovernedPaperProtectiveRevocation for item in revocations
    ):
        raise _fail("protective_revocations_malformed")
    digests: list[str] = []
    previous_at: int | None = None
    for revocation in revocations:
        verification = verify_governed_paper_protective_revocation(revocation)
        if not verification.intact:
            raise _fail("protective_revocation_not_authentic")
        if revocation.authority_digest != authority.authority_digest:
            raise _fail("protective_revocation_foreign")
        if revocation.approval_kind is not GovernedPaperApprovalKind.HUMAN_GOVERNANCE:
            raise _fail("protective_revocation_not_human_governance")
        if not start < revocation.effective_at_ns <= end:
            raise _fail("protective_revocation_outside_the_sealed_day")
        if previous_at is not None and revocation.effective_at_ns <= previous_at:
            raise _fail("protective_revocations_not_ordered")
        previous_at = revocation.effective_at_ns
        digests.append(verification.recomputed_digest)
    revoked_from = None if prior is None else prior.protective_revoked_from_ns
    if revoked_from is None and revocations:
        revoked_from = revocations[0].effective_at_ns

    # The adopted source's bars known at E_{k+1}.
    archive = protection.ohlc_archive
    if type(archive) is not HistoricalOhlcBarArchive:
        raise _fail("ohlc_archive_malformed")
    archive_verification = verify_historical_ohlc_bar_archive(archive)
    if not archive_verification.intact:
        raise _fail("ohlc_archive_not_authentic")
    if archive.source_digest != authority.ohlc_source_digest:
        raise _fail("ohlc_archive_not_of_the_adopted_source")
    if any(max(bar.available_at_ns, bar.finalized_at_ns) > end for bar in archive.bars):
        raise _fail("ohlc_archive_holds_a_bar_unknown_at_the_seal")

    # The deciding cycle of the excursion the previous seal left open, re-proven against what that seal named.
    open_digest = None if prior is None else prior.open_excursion_deciding_cycle_digest
    excursion: GovernedPaperCycleReservation | None = None
    if open_digest is None:
        if protection.excursion_cycle is not None or protection.excursion_cycle_inputs is not None:
            raise _fail("excursion_cycle_without_an_open_excursion")
    else:
        cycle = protection.excursion_cycle
        if (
            cycle is None
            or not verify_governed_paper_cycle_authority(cycle, protection.excursion_cycle_inputs).intact
            or governed_paper_cycle_authority_digest(cycle) != open_digest
            or cycle.day_index != prior.open_excursion_deciding_day_index  # type: ignore[union-attr]
            or cycle.genesis_digest != genesis.genesis_digest
        ):
            raise _fail("excursion_deciding_cycle_not_authentic")
        excursion = governed_paper_cycle_reservation(cycle, protection.excursion_cycle_inputs)
    return _DayProtection(
        authority=authority,
        context=context,
        revocation_digests=tuple(digests),
        revoked_from_ns=revoked_from,
        window=governed_paper_protective_window(authority, revoked_from_ns=revoked_from),
        archive=archive,
        archive_digest=archive_verification.recomputed_digest,
        excursion=excursion,
        portfolio_no_trade=protection.portfolio_no_trade,
    )


def _seal_proof(inputs: GovernedPaperDaySealInputs) -> _SealProof:  # noqa: C901 - one linear derivation
    if type(inputs) is not GovernedPaperDaySealInputs:
        raise _fail("seal_inputs_malformed")
    seal_id = _require_text(inputs.seal_id, "seal_id")
    correlation_id = _require_text(inputs.correlation_id, "seal_correlation_id")
    day = inputs.day_index
    if type(day) is not int or day < 0:
        raise _fail("day_index_invalid")
    authority = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
    genesis = authority.genesis
    start = genesis.genesis_start_ns + day * _UTC_DAY_NS
    end = start + _UTC_DAY_NS
    if not historical_execution_wire_int_is_valid(end, minimum=0):
        raise _fail("day_index_invalid")

    # The day's cycle (re-proven) and the previous seal (locally consistent; the evidence proves the lineage).
    cycle = inputs.cycle
    verification = verify_governed_paper_cycle_authority(cycle, inputs.cycle_inputs)
    if not verification.intact:
        raise _fail("cycle_not_authentic")
    if cycle.day_index != day or cycle.genesis_digest != genesis.genesis_digest:
        raise _fail("cycle_not_this_day")
    if day == 0:
        if inputs.prior_seal is not None:
            raise _fail("prior_seal_before_the_first_day")
        prior = None
        empty = governed_paper_sealed_history_digest(
            (), (), (), strategy_spec_digest_anchor=genesis.strategy_spec_digest
        )
        if cycle.sealed_history_digest != empty:
            raise _fail("cycle_not_opened_on_the_sealed_history")
    else:
        prior = _prior_seal(inputs.prior_seal, day=day, genesis_digest=genesis.genesis_digest)
        if cycle.sealed_history_digest != prior.sealed_history_digest:
            raise _fail("cycle_not_opened_on_the_sealed_history")
        if cycle.lifecycle_head_authority_digest != prior.closing_head_authority_digest:
            raise _fail("cycle_not_opened_on_the_closing_attestation")
    reservation = (
        governed_paper_cycle_reservation(cycle, inputs.cycle_inputs)
        if cycle.status is GovernedPaperCycleStatus.AUTHORIZED
        else None
    )
    pending_sequence = None if prior is None else prior.pending_decision_sequence
    pending_reservation: GovernedPaperCycleReservation | None = None
    if pending_sequence is None:
        if inputs.pending_cycle is not None or inputs.pending_cycle_inputs is not None:
            raise _fail("pending_cycle_without_a_pending_intent")
    else:
        pending = inputs.pending_cycle
        if (
            pending is None
            or not verify_governed_paper_cycle_authority(pending, inputs.pending_cycle_inputs).intact
            or governed_paper_cycle_authority_digest(pending) != prior.pending_deciding_cycle_digest  # type: ignore[union-attr]
            or pending.day_index != prior.pending_deciding_day_index  # type: ignore[union-attr]
            or pending.genesis_digest != genesis.genesis_digest
        ):
            raise _fail("pending_deciding_cycle_not_authentic")
        pending_reservation = governed_paper_cycle_reservation(pending, inputs.pending_cycle_inputs)

    # The archive at E_{k+1}: authentic, of the genesis manifest, holding only records known at the sealing instant.
    dataset = inputs.dataset
    if type(dataset) is not HistoricalPitDataset:
        raise _fail("dataset_malformed")
    dataset_verification = verify_historical_pit_dataset(dataset)
    if not dataset_verification.intact:
        raise _fail("dataset_not_authentic")
    if dataset.status is not EdgeEvidenceStatus.READY or dataset.advances is not True:
        raise _fail("dataset_not_ready")
    if (
        dataset.source_manifest_digest != genesis.source_manifest_digest
        or dataset.data_requirement_registry_digest != genesis.data_requirement_registry_digest
    ):
        raise _fail("dataset_foreign")
    if any(_visibility(record) > end for record in dataset.records):
        raise _fail("dataset_holds_a_record_unknown_at_the_seal")
    if cycle.reservation_mark_record_digest:
        mark = historical_execution_latest_visible_mark(
            dataset, policy=authority.economics_policy, instrument=genesis.instrument, at_ns=start
        )
        if mark != (cycle.reservation_mark_record_digest, cycle.reservation_mark_price):
            raise _fail("reservation_mark_not_reproduced_by_the_archive")
    head_digest, closing_head, successors, effective, attested = _closing(inputs, cycle, genesis.sleeve_id, end)
    protection = _day_protection(inputs, prior, genesis=genesis, start=start, end=end)
    invalidated = (
        prior.invalidated_from_ns if prior is not None and prior.invalidated_from_ns is not None else effective
    )
    window = governed_paper_cycle_admission_window(cycle)
    windows: tuple[HistoricalExecutionAdmissionWindow, ...] = (*(() if prior is None else prior.schedule.windows),)
    days = (*(() if prior is None else prior.authorized_day_indexes),)
    if window is not None:
        windows, days = (*windows, window), (*days, day)
    schedule = HistoricalExecutionAdmissionSchedule(
        schema_version=HISTORICAL_EXECUTION_ADMISSION_SCHEDULE_SCHEMA_VERSION
        if protection is None
        else HISTORICAL_EXECUTION_PROTECTIVE_ADMISSION_SCHEDULE_SCHEMA_VERSION,
        schedule_id=f"{genesis.genesis_id}-schedule",
        windows=windows,
        invalidated_from_ns=invalidated,
        protective_windows=() if protection is None or protection.window is None else (protection.window,),
    )
    facts: dict[str, object] = {
        "seal_id": seal_id,
        "correlation_id": correlation_id,
        "genesis_id": genesis.genesis_id,
        "genesis_digest": genesis.genesis_digest,
        "sleeve_id": genesis.sleeve_id,
        "instrument": genesis.instrument,
        "day_index": day,
        "window_start_ns": start,
        "window_end_ns": end,
        "cycle_id": cycle.cycle_id,
        "cycle_digest": cycle.cycle_digest,
        "cycle_status": cycle.status.value,
        "cycle_phase": cycle.phase.value,
        "prior_seal_digest": "" if prior is None else prior.seal_digest,
        "schedule": schedule,
        "schedule_digest": historical_execution_admission_schedule_digest(schedule),
        "authorized_day_indexes": days,
        "invalidated_from_ns": invalidated,
        "closing_head_authority_digest": head_digest,
        "closing_lifecycle_head_digest": closing_head,
        "successor_receipt_digests": successors,
        "dataset_digest": dataset_verification.recomputed_digest,
        "dataset_record_count": len(dataset.records),
    }
    empty: dict[str, object] = {
        "decision_run_digest": "",
        "economics_result_digest": "",
        "governed_outcome_digest": "",
        "prefix_digest_open": "",
        "prefix_digest_close": "",
        "pending_decision_sequence": None,
        "pending_deciding_day_index": None,
        "pending_deciding_cycle_digest": None,
        "governance_rejected_fill_count": 0,
        "entry_safety_rule_set_digest": "",
        "entry_safety_evidence_digest": "",
        "entry_safety_decisions": (),
        "episodes": (),
        "episode_deciding_cycle_digests": (),
        "day_closes": (),
        "funding_events": (),
        "day_episode_count": 0,
        "day_funding_event_count": 0,
        "sealed_history_digest": "",
        "close_position_quantity": "",
        "close_cumulative_funding": "",
    }
    if protection is not None:
        facts.update(
            protective_authority_digest=protection.authority.authority_digest,
            protective_revocation_digests=protection.revocation_digests,
            protective_revoked_from_ns=protection.revoked_from_ns,
            ohlc_archive_digest=protection.archive_digest,
            ohlc_bar_count=len(protection.archive.bars),
        )
        empty.update(
            open_excursion_deciding_day_index=None,
            open_excursion_deciding_cycle_digest=None,
            pending_protective_attempt_time_ns=None,
            day_protective_obligation_count=0,
            outstanding_protective_obligation_count=0,
        )
    protective = protection is not None
    portfolio = protection is not None and protection.portfolio_no_trade
    try:
        if not attested:
            raise _Blocked("closing_head_not_attested")
        if protection is not None and protection.context is None:
            raise _Blocked("protective_authority_not_authorized")
        replay = _replay(inputs, authority, schedule, start, end, protection)
        facts.update(
            _derive_day(
                authority, cycle, prior, reservation, pending_reservation, protection, replay, dataset, start, end
            )
        )
        # The engine ran under the schedule the entry-safety refusals completed; a blocked day keeps the opening one.
        facts["schedule"] = replay.schedule
        facts["schedule_digest"] = historical_execution_admission_schedule_digest(replay.schedule)
        return _SealProof(facts, (), protective, portfolio)
    except _Blocked as blocked:
        facts.update(empty)
        return _SealProof(facts, (_reason(blocked.code),), protective, portfolio)


@dataclass(frozen=True)
class _Replay:
    run_digest: str
    economics_digest: str
    outcome: HistoricalExecutionGovernedPaperOutcome
    entry_safety: GovernedPaperEntrySafetyEvidence
    schedule: HistoricalExecutionAdmissionSchedule


def _replay(
    inputs: GovernedPaperDaySealInputs,
    authority: GovernedPaperGenesisAuthority,
    schedule: HistoricalExecutionAdmissionSchedule,
    start: int,
    end: int,
    protection: _DayProtection | None,
) -> _Replay:
    """The authenticated prefix replay over ``[G, E_{k+1})``: run, economics, entry safety and governed outcome.

    Every artifact is built here. The economics validates the archive's economic series first, so an archive it cannot
    compute keeps its BLOCKED day; only then do the entry-safety refusals complete the schedule the engine re-runs under.
    A protective lineage builds the economics under the authority's position-management policy and the day's OHLC
    archive, and the entry gate evaluates rule set v2 on the same protective context.
    """

    genesis = authority.genesis
    position_management: HistoricalExecutionPositionManagementInputs | None = None
    gate_protection: GovernedPaperEntrySafetyProtection | None = None
    if protection is not None:
        context = protection.context
        if context is None:
            raise _Blocked("protective_authority_not_authorized")
        position_management = HistoricalExecutionPositionManagementInputs(
            policy=context.position_management_policy,
            expected_policy_digest=context.authority.position_management_policy_digest,
            approval=context.position_management_approval,
            ohlc_archive=protection.archive,
            expected_ohlc_archive_digest=protection.archive_digest,
        )
        gate_protection = GovernedPaperEntrySafetyProtection(
            position_management_policy=context.position_management_policy,
            ohlc_archive=protection.archive,
            protective_window=protection.window,
        )
    run = build_historical_decision_run(
        inputs.dataset,
        authority.executable_binding,
        expected_dataset_digest=inputs.dataset.dataset_digest,
        expected_executable_binding_digest=genesis.executable_binding_digest,
        run_id=f"{inputs.seal_id}-run",
        correlation_id=inputs.correlation_id,
        parameter_assignment=authority.parameter_assignment,
        instrument=genesis.instrument,
        evaluation_start_ns=genesis.genesis_start_ns,
        evaluation_end_ns=end,
        parameter_approval=authority.parameter_approval,
    )
    if run.status is not EdgeEvidenceStatus.READY or run.gate_verdict is not EdgeGateVerdict.PASS:
        raise _Blocked(f"decision_run_not_ready:{run.gate_verdict.value}")
    economics = build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=authority.economics_policy,
        expected_economics_policy_digest=genesis.economics_policy_digest,
        economics_approval=authority.economics_approval,
        result_id=f"{inputs.seal_id}-economics",
        correlation_id=inputs.correlation_id,
        position_management=position_management,
    )
    if (
        economics.status is not EdgeEvidenceStatus.READY
        or economics.gate_verdict is not EdgeGateVerdict.PASS
        or economics.simulated_economics_computed is not True
    ):
        raise _Blocked(f"economics_not_computed:{economics.gate_verdict.value}")

    def evaluated(refused: tuple[int, ...]) -> GovernedPaperEntrySafetyEvidence:
        """The gate under the schedule refusing ``refused``; with a governed portfolio (rule set v3) only."""

        trial = replace(schedule, entry_refused_decision_sequences=refused)
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=inputs.dataset,
            invalidated_from_ns=schedule.invalidated_from_ns,
            protection=gate_protection,
            portfolio=GovernedPaperEntrySafetyPortfolio(economics, trial),
        )

    if protection is not None and protection.portfolio_no_trade:
        refused = governed_paper_entry_safety_sequential_refusals(
            governed_paper_entry_safety_entry_sequences(run),
            lambda current: evaluated(current).refused_decision_sequences,
        )
        entry_safety = evaluated(refused)
    else:
        entry_safety = build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=inputs.dataset,
            invalidated_from_ns=schedule.invalidated_from_ns,
            protection=gate_protection,
        )
    schedule = replace(schedule, entry_refused_decision_sequences=entry_safety.refused_decision_sequences)
    outcome = simulate_historical_execution_governed_paper(
        economics, expected_result_digest=economics.result_digest, schedule=schedule
    )
    if outcome.simulated is not True:
        raise _Blocked("governed_economics_not_computed")
    return _Replay(run.run_digest, economics.result_digest, outcome, entry_safety, schedule)


def _derive_day(  # noqa: C901, PLR0912, PLR0915 - one linear derivation of the day
    authority: GovernedPaperGenesisAuthority,
    cycle: GovernedPaperCycleAuthority,
    prior: GovernedPaperDaySeal | None,
    reservation: GovernedPaperCycleReservation | None,
    pending_reservation: GovernedPaperCycleReservation | None,
    protection: _DayProtection | None,
    replay: _Replay,
    dataset: HistoricalPitDataset,
    start: int,
    end: int,
) -> dict[str, object]:
    genesis = authority.genesis
    outcome = replay.outcome
    decided = {item.intent_id: item for item in outcome.intents}

    # Pending lineage (B3) and the prefix preservation of every earlier event (X1).
    pending_sequence = outcome.pending_decision_sequence
    pending_day: int | None = None
    pending_digest: str | None = None
    prior_pending = None if prior is None else prior.pending_decision_sequence
    if pending_sequence is not None:
        if prior is not None and pending_sequence == prior_pending:
            pending_day, pending_digest = prior.pending_deciding_day_index, prior.pending_deciding_cycle_digest
        else:
            intent = [item for item in outcome.intents if item.decision_sequence == pending_sequence][0]
            if not start <= intent.decision_time_ns < end:
                raise _fail("pending_intent_without_its_deciding_cycle")
            pending_day, pending_digest = cycle.day_index, cycle.cycle_digest
    # A protective attempt the replay's end left in flight (outcome v3): made today, or the previous seal's own.
    pending_attempt = outcome.pending_protective_attempt_time_ns
    prior_attempt = None if prior is None else prior.pending_protective_attempt_time_ns
    if pending_attempt is not None and pending_attempt != prior_attempt and not start <= pending_attempt < end:
        raise _fail("pending_protective_attempt_without_its_day")
    excluded_open = () if prior_pending is None else (prior_pending,)
    prefix_open = historical_execution_governed_paper_prefix_digest(
        outcome,
        before_ns=start,
        excluded_decision_sequences=excluded_open,
        excluded_protective_attempt_times=() if prior_attempt is None else (prior_attempt,),
    )
    if prior is not None and prefix_open != prior.prefix_digest_close:
        raise _fail("sealed_prefix_rewritten")
    prefix_close = historical_execution_governed_paper_prefix_digest(
        outcome,
        before_ns=end,
        excluded_decision_sequences=() if pending_sequence is None else (pending_sequence,),
        excluded_protective_attempt_times=() if pending_attempt is None else (pending_attempt,),
    )

    # The deciding cycle of an excursion (DEC-1 lineage): the cycle that decided its opening intent, which is today's,
    # the pending cycle, or the excursion cycle the previous seal named for the excursion open at E_k.
    def opening_cycle(record: HistoricalExecutionExcursionProtection) -> tuple[int, str, GovernedPaperCycleReservation]:
        opening = decided[record.opening_intent_id]
        deciding_day = (opening.decision_time_ns - genesis.genesis_start_ns) // _UTC_DAY_NS
        if deciding_day == cycle.day_index and reservation is not None:
            return cycle.day_index, cycle.cycle_digest, reservation
        if prior is not None and opening.decision_sequence == prior_pending and pending_reservation is not None:
            return prior.pending_deciding_day_index, prior.pending_deciding_cycle_digest, pending_reservation  # type: ignore[return-value]
        excursion = None if protection is None else protection.excursion
        if record.opened_at_ns < start and excursion is not None and deciding_day == excursion.cycle.day_index:
            return excursion.cycle.day_index, excursion.cycle.cycle_digest, excursion
        raise _fail("excursion_without_its_deciding_cycle")

    # B4: every settlement of the day must be exactly representable over the engine's own factors.
    day_funding = [item for item in outcome.funding_cashflows if start <= item.liability_time_ns < end]
    for item in day_funding:
        exact = -Fraction(item.position_quantity) * Fraction(item.mark_price) * Fraction(item.funding_rate)
        if Fraction(item.cashflow_amount) != exact:
            raise _Blocked(f"funding_settlement_not_exactly_representable:{item.funding_sequence_id}")

    # X4: project the day's executed fills, in engine order, onto the generic position chain.
    if prior is None:
        state = build_flat_paper_position_state(
            position_state_id=f"pos-{genesis.genesis_id}-genesis",
            market_symbol=genesis.instrument,
            correlation_id=f"corr-{genesis.genesis_id}-genesis",
        )
        chain = _Chain(state, [], [])
    else:
        last = prior.episodes[-1].new_position_state if prior.episodes else None
        state = (
            last
            if last is not None
            else build_flat_paper_position_state(
                position_state_id=f"pos-{genesis.genesis_id}-genesis",
                market_symbol=genesis.instrument,
                correlation_id=f"corr-{genesis.genesis_id}-genesis",
            )
        )
        chain = _Chain(state, list(prior.episodes), list(prior.episode_deciding_cycle_digests))
    transitions = {item.fill_digest: item for item in outcome.position_transitions}
    marks = {item.trigger_digest: item for item in outcome.valuations if item.trigger_digest is not None}
    attempted = {item.attempt_id: item for item in outcome.protective_attempts}
    obligations = {item.obligation_id: item for item in outcome.protective_obligations}
    protections = {item.protection_id: item for item in outcome.excursion_protections}
    states_at: list[tuple[int, PaperPositionState]] = []
    day_fills = [
        item
        for item in outcome.fills
        if item.outcome in _EXECUTED and item.execution_time_ns is not None and start <= item.execution_time_ns < end
    ]
    for fill in day_fills:
        attempt = attempted.get(fill.intent_id)
        if attempt is None:
            intent = decided[fill.intent_id]
            deciding_day = (intent.decision_time_ns - genesis.genesis_start_ns) // _UTC_DAY_NS
            if deciding_day == cycle.day_index and reservation is not None:
                deciding = reservation
            elif (
                prior_pending is not None
                and intent.decision_sequence == prior_pending
                and pending_reservation is not None
            ):
                deciding = pending_reservation
            else:
                raise _fail("fill_without_its_deciding_cycle")
            authorized = (
                deciding.cycle.long_authorized
                if fill.side is HistoricalExecutionSide.BUY
                else deciding.cycle.short_authorized
            )
            if authorized is not True:
                raise _Blocked("fill_side_not_authorized_by_its_deciding_cycle")
            base, side, requested = (
                f"{genesis.genesis_id}-d{intent.decision_sequence}",
                intent.side,
                intent.requested_quantity,
            )
        else:
            # DEC-1: a protective fill is close-only and never bound to a cycle's direction authority; it is projected
            # through the reservation of the cycle that decided its excursion.
            deciding = opening_cycle(protections[obligations[attempt.obligation_id].protection_id])[2]
            if transitions[fill.fill_digest].transition_kind not in (
                HistoricalExecutionTransitionKind.REDUCE,
                HistoricalExecutionTransitionKind.CLOSE,
            ):
                raise _Blocked("protective_fill_not_close_only")
            base, side, requested = (
                f"{genesis.genesis_id}-p{attempt.attempt_time_ns}",
                attempt.side,
                attempt.requested_quantity,
            )
        valuation = marks.get(fill.fill_digest)
        mark_price = None if valuation is None else valuation.mark_price
        if mark_price is None:
            visible = historical_execution_latest_visible_mark(
                dataset,
                policy=authority.economics_policy,
                instrument=genesis.instrument,
                at_ns=fill.execution_time_ns,  # type: ignore[arg-type]
            )
            if visible is None:
                raise _Blocked("projection_mark_unavailable")
            mark_price = visible[1]
        episode = _episode(
            authority,
            deciding,
            fill,
            chain.state,
            base=base,
            side=side,
            requested_quantity=requested,
            mark_price=mark_price,
            transition=transitions[fill.fill_digest],
        )
        chain.episodes.append(episode)
        chain.deciding.append(deciding.cycle.cycle_digest)
        chain.state = episode.new_position_state
        states_at.append((fill.execution_time_ns, chain.state))  # type: ignore[arg-type]

    # Funding events, each bound to the chain position liable at its instant (before any fill at that instant).
    events = list(() if prior is None else prior.funding_events)
    opening_state = state
    for item in day_funding:
        liable = opening_state
        for instant, after in states_at:
            if instant < item.liability_time_ns:
                liable = after
        _exact(liable.signed_units, Fraction(item.position_quantity), "funding_position")
        events.append(
            PaperSleeveFundingEvent(
                event_id=f"{genesis.genesis_id}-funding-{item.funding_sequence_id}",
                settlement_at_ns=item.liability_time_ns,
                position_state_digest=paper_position_state_digest(liable),
                funding_amount=item.cashflow_amount,
            )
        )

    # The day close at E_{k+1}: the engine's own visible mark and the chain position after the day's fills.
    closing = outcome.valuations[-1]
    if closing.time_ns != end:
        raise _fail("replay_did_not_end_at_the_seal")
    _exact(chain.state.signed_units, Fraction(closing.position_quantity), "close_position")
    visible = historical_execution_latest_visible_mark(
        dataset, policy=authority.economics_policy, instrument=genesis.instrument, at_ns=end
    )
    if visible is None:
        raise _Blocked("day_close_mark_unavailable")
    if closing.mark_price is not None and Fraction(closing.mark_price) != Fraction(visible[1]):
        raise _Blocked("projection_not_exact:close_mark")
    close_mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"close-mark-{genesis.genesis_id}-{cycle.day_index}",
        market_symbol=genesis.instrument,
        mark_price=_plain(Fraction(visible[1])),
        observed_at_ns=end,
        correlation_id=f"corr-{genesis.genesis_id}-close",
    )
    close_report = compute_paper_pnl_report(
        chain.state,
        close_mark,
        pnl_report_id=f"close-pnl-{genesis.genesis_id}-{cycle.day_index}",
        correlation_id=f"corr-{genesis.genesis_id}-close",
    )
    closes = (*(() if prior is None else prior.day_closes), PaperSleeveDayCloseValuation(close_mark, close_report))
    # B4 reconciliation: the sealed funding events sum EXACTLY to the engine's cumulative funding at the boundary.
    if sum((Fraction(item.funding_amount) for item in events), Fraction(0)) != Fraction(closing.cumulative_funding):
        raise _Blocked("funding_reconciliation_failed")
    episodes = tuple(chain.episodes)
    funding = tuple(events)
    derived: dict[str, object] = {}
    if protection is not None:
        # The excursion still open at E_{k+1} names its deciding cycle; the next seal must be given exactly that cycle.
        still_open = [item for item in outcome.excursion_protections if item.closed_at_ns is None]
        open_day, open_digest = (None, None) if not still_open else opening_cycle(still_open[-1])[:2]
        derived = {
            "open_excursion_deciding_day_index": open_day,
            "open_excursion_deciding_cycle_digest": open_digest,
            "pending_protective_attempt_time_ns": pending_attempt,
            "day_protective_obligation_count": sum(
                1 for item in outcome.protective_obligations if start <= item.created_at_ns < end
            ),
            "outstanding_protective_obligation_count": sum(
                1
                for item in outcome.protective_obligations
                if item.status is HistoricalExecutionProtectiveObligationStatus.OUTSTANDING
            ),
        }
    return {
        **derived,
        "decision_run_digest": replay.run_digest,
        "economics_result_digest": replay.economics_digest,
        "governed_outcome_digest": outcome.outcome_digest,
        "prefix_digest_open": prefix_open,
        "prefix_digest_close": prefix_close,
        "pending_decision_sequence": pending_sequence,
        "pending_deciding_day_index": pending_day,
        "pending_deciding_cycle_digest": pending_digest,
        "governance_rejected_fill_count": len(outcome.governance_rejected_fill_digests),
        "entry_safety_rule_set_digest": replay.entry_safety.rule_set_digest,
        "entry_safety_evidence_digest": replay.entry_safety.evidence_digest,
        "entry_safety_decisions": tuple(
            item for item in replay.entry_safety.decisions if start <= item.decision_time_ns < end
        ),
        "episodes": episodes,
        "episode_deciding_cycle_digests": tuple(chain.deciding),
        "day_closes": closes,
        "funding_events": funding,
        "day_episode_count": len(day_fills),
        "day_funding_event_count": len(day_funding),
        "sealed_history_digest": governed_paper_sealed_history_digest(
            episodes, closes, funding, strategy_spec_digest_anchor=genesis.strategy_spec_digest
        ),
        "close_position_quantity": closing.position_quantity,
        "close_cumulative_funding": closing.cumulative_funding,
    }


def _assemble_seal(proof: _SealProof) -> GovernedPaperDaySeal:
    status = GovernedPaperDaySealStatus.BLOCKED if proof.blocked else GovernedPaperDaySealStatus.SEALED
    seed = GovernedPaperDaySeal(
        schema_version=_PORTFOLIO_SEAL_SCHEMA_VERSION
        if proof.portfolio
        else _PROTECTIVE_SEAL_SCHEMA_VERSION
        if proof.protective
        else _SEAL_SCHEMA_VERSION,
        status=status,
        sealed=status is GovernedPaperDaySealStatus.SEALED,
        **proof.facts,  # type: ignore[arg-type]
        reason_codes=tuple(sorted(proof.blocked)),
        seal_digest="",
    )
    return replace(seed, seal_digest=governed_paper_day_seal_digest(seed))


def build_governed_paper_day_seal(inputs: GovernedPaperDaySealInputs) -> GovernedPaperDaySeal:
    """Seal one governed paper day at ``E_{k+1}`` (see the module docstring).

    Malformed input or any provenance defect raises ``GovernedPaperExecutionError``. A day that cannot be sealed
    truthfully (an unattested closing head, an unready run or economics, an inexact settlement or projection) is
    ``BLOCKED`` with its reason and carries no history. Pure.
    """

    return _assemble_seal(_seal_proof(inputs))


def verify_governed_paper_day_seal(seal: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a seal by typed identity against its rebuild from ``inputs``. Total: never raises."""

    return governed_paper_verify_rebuilt(
        seal,
        cls=GovernedPaperDaySeal,
        domain=_SEAL_DOMAIN,
        to_payload=_to_payload,
        digest_field=_SEAL_DIGEST_FIELD,
        rebuild=lambda: build_governed_paper_day_seal(inputs),  # type: ignore[arg-type]
        code="day_seal",
        reason=_reason,
        resolve=_spec_resolver(),
    )


# --- the lineage evidence ------------------------------------------------------------------------------------------------


def _record_digests(dataset: HistoricalPitDataset) -> dict[str, object]:
    return {record.record_digest: record for record in dataset.records}


def _bar_digests(archive: HistoricalOhlcBarArchive) -> dict[str, HistoricalOhlcBar]:
    return {bar.bar_digest: bar for bar in archive.bars}


def build_governed_paper_execution_evidence(inputs: GovernedPaperExecutionInputs) -> GovernedPaperExecutionEvidence:  # noqa: C901
    """Re-prove one whole governed paper lineage and bind every day pairwise (see the module docstring).

    Malformed input or any lineage defect raises ``GovernedPaperExecutionError``. A lineage whose last seal is BLOCKED
    is ``BLOCKED``; no day may follow a blocked seal. Pure.
    """

    if type(inputs) is not GovernedPaperExecutionInputs:
        raise _fail("evidence_inputs_malformed")
    evidence_id = _require_text(inputs.evidence_id, "evidence_id")
    correlation_id = _require_text(inputs.correlation_id, "evidence_correlation_id")
    genesis = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs).genesis
    if type(inputs.days) is not tuple or not inputs.days:
        raise _fail("evidence_days_missing")
    records: list[GovernedPaperExecutionDayRecord] = []
    cycles: list[GovernedPaperCycleAuthority] = []
    seals: list[GovernedPaperDaySeal] = []
    lineage: list[list[str]] = []
    reasons: list[str] = []
    for day, item in enumerate(inputs.days):
        if type(item) is not GovernedPaperExecutionDay:
            raise _fail("evidence_day_malformed")
        if seals and seals[-1].status is not GovernedPaperDaySealStatus.SEALED:
            raise _fail("a_day_follows_a_blocked_seal")
        cycle, seal = item.cycle, item.seal
        if not verify_governed_paper_cycle_authority(cycle, item.cycle_inputs).intact:
            raise _fail(f"cycle_not_authentic:{day}")
        if not verify_governed_paper_day_seal(seal, item.seal_inputs).intact:
            raise _fail(f"seal_not_authentic:{day}")
        if (
            cycle.day_index != day
            or seal.day_index != day
            or cycle.genesis_digest != genesis.genesis_digest
            or seal.genesis_digest != genesis.genesis_digest
            or seal.cycle_digest != cycle.cycle_digest
            or governed_paper_cycle_authority_digest(item.seal_inputs.cycle) != cycle.cycle_digest
        ):
            raise _fail(f"day_not_bound_to_its_cycle:{day}")
        if day == 0:
            empty = governed_paper_sealed_history_digest(
                (), (), (), strategy_spec_digest_anchor=genesis.strategy_spec_digest
            )
            if seal.prior_seal_digest != "" or cycle.sealed_history_digest != empty:
                raise _fail("first_day_not_opened_on_the_genesis")
            if cycle.lifecycle_head_digest != genesis.lifecycle_genesis_digest:
                raise _fail("first_day_not_opened_on_the_genesis_head")
        else:
            previous = seals[-1]
            if seal.prior_seal_digest != previous.seal_digest or item.seal_inputs.prior_seal is None:
                raise _fail(f"seal_not_chained:{day}")
            if governed_paper_day_seal_digest(item.seal_inputs.prior_seal) != previous.seal_digest:
                raise _fail(f"seal_not_chained:{day}")
            if cycle.sealed_history_digest != previous.sealed_history_digest:
                raise _fail(f"cycle_not_opened_on_the_sealed_history:{day}")
            if cycle.lifecycle_head_authority_digest != previous.closing_head_authority_digest:
                raise _fail(f"cycle_not_opened_on_the_closing_attestation:{day}")
            if previous.invalidated_from_ns is not None and seal.invalidated_from_ns != previous.invalidated_from_ns:
                raise _fail(f"invalidation_undone:{day}")
            earlier = _record_digests(inputs.days[day - 1].seal_inputs.dataset)
            current = _record_digests(item.seal_inputs.dataset)
            if not set(earlier) <= set(current):
                raise _fail(f"archive_rewritten:{day}")
            if any(_visibility(current[name]) <= cycle.window_start_ns for name in set(current) - set(earlier)):
                raise _fail(f"archive_backfilled_before_the_day:{day}")
            protection = item.seal_inputs.protection
            if protection is not None:  # the seal proved the lineage is protective on both days
                earlier_bars = _bar_digests(inputs.days[day - 1].seal_inputs.protection.ohlc_archive)  # type: ignore[union-attr]
                current_bars = _bar_digests(protection.ohlc_archive)
                if not set(earlier_bars) <= set(current_bars):
                    raise _fail(f"ohlc_archive_rewritten:{day}")
                if any(
                    max(current_bars[name].available_at_ns, current_bars[name].finalized_at_ns) <= cycle.window_start_ns
                    for name in set(current_bars) - set(earlier_bars)
                ):
                    raise _fail(f"ohlc_archive_backfilled_before_the_day:{day}")
        pending = item.seal_inputs.pending_cycle
        if pending is not None:
            index = pending.day_index
            if not 0 <= index < day or governed_paper_cycle_authority_digest(pending) != cycles[index].cycle_digest:
                raise _fail(f"pending_cycle_not_the_lineage_cycle:{day}")
        excursion = None if item.seal_inputs.protection is None else item.seal_inputs.protection.excursion_cycle
        if excursion is not None:
            index = excursion.day_index
            if not 0 <= index < day or governed_paper_cycle_authority_digest(excursion) != cycles[index].cycle_digest:
                raise _fail(f"excursion_cycle_not_the_lineage_cycle:{day}")
        cycles.append(cycle)
        seals.append(seal)
        lineage.append([cycle.cycle_digest, seal.seal_digest])
        records.append(
            GovernedPaperExecutionDayRecord(
                day_index=day,
                cycle_digest=cycle.cycle_digest,
                cycle_status=cycle.status.value,
                cycle_phase=cycle.phase.value,
                long_authorized=cycle.long_authorized,
                short_authorized=cycle.short_authorized,
                seal_digest=seal.seal_digest,
                seal_status=seal.status.value,
                day_episode_count=seal.day_episode_count,
                day_funding_event_count=seal.day_funding_event_count,
                governance_rejected_fill_count=seal.governance_rejected_fill_count,
                pending_decision_sequence=seal.pending_decision_sequence,
                sealed_history_digest=seal.sealed_history_digest,
            )
        )
        reasons.extend(seal.reason_codes)
    terminal = seals[-1]
    status = (
        GovernedPaperExecutionStatus.READY
        if all(item.status is GovernedPaperDaySealStatus.SEALED for item in seals)
        else GovernedPaperExecutionStatus.BLOCKED
    )
    phases = [item.phase.value for item in cycles]
    ordinary = [index for index, value in enumerate(phases) if value == "ORDINARY"]
    protective = terminal.schema_version in _PROTECTIVE_SEALS
    extension: dict[str, object] = {}
    if protective:
        extension = {
            "protective_authority_digest": terminal.protective_authority_digest,
            "terminal_protective_revoked_from_ns": terminal.protective_revoked_from_ns,
            "terminal_outstanding_protective_obligation_count": terminal.outstanding_protective_obligation_count,
        }
    seed = GovernedPaperExecutionEvidence(
        schema_version=_PORTFOLIO_EVIDENCE_SCHEMA_VERSION
        if terminal.schema_version == _PORTFOLIO_SEAL_SCHEMA_VERSION
        else _PROTECTIVE_EVIDENCE_SCHEMA_VERSION
        if protective
        else _EVIDENCE_SCHEMA_VERSION,
        status=status,
        ready=status is GovernedPaperExecutionStatus.READY,
        evidence_id=evidence_id,
        correlation_id=correlation_id,
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        genesis_inputs_identity_digest=genesis.genesis_inputs_identity_digest,
        sleeve_id=genesis.sleeve_id,
        instrument=genesis.instrument,
        genesis_start_ns=genesis.genesis_start_ns,
        day_count=len(seals),
        sealed_day_count=sum(1 for item in seals if item.status is GovernedPaperDaySealStatus.SEALED),
        days=tuple(records),
        bootstrap_b0_day_count=phases.count("BOOTSTRAP_B0"),
        bootstrap_b1_day_count=phases.count("BOOTSTRAP_B1"),
        ordinary_day_count=len(ordinary),
        first_ordinary_day_index=ordinary[0] if ordinary else None,
        terminal_seal_digest=terminal.seal_digest,
        terminal_sealed_history_digest=terminal.sealed_history_digest,
        terminal_episode_count=len(terminal.episodes),
        terminal_day_close_count=len(terminal.day_closes),
        terminal_funding_event_count=len(terminal.funding_events),
        terminal_invalidated_from_ns=terminal.invalidated_from_ns,
        lineage_digest=edge_sha256_text(edge_canonical_json(lineage)),
        reason_codes=tuple(sorted(set(reasons))),
        evidence_digest="",
        **extension,  # type: ignore[arg-type]
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), _EVIDENCE_DIGEST_FIELD))


def governed_paper_execution_evidence_to_dict(evidence: GovernedPaperExecutionEvidence) -> dict[str, object]:
    return _to_payload(evidence)


def governed_paper_execution_evidence_digest(evidence: GovernedPaperExecutionEvidence) -> str:
    return edge_payload_digest(_to_payload(evidence), _EVIDENCE_DIGEST_FIELD)


def verify_governed_paper_execution_evidence(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove a lineage evidence by typed identity against its rebuild from ``inputs``. Total: never raises."""

    return governed_paper_verify_rebuilt(
        evidence,
        cls=GovernedPaperExecutionEvidence,
        domain=_EVIDENCE_DOMAIN,
        to_payload=_to_payload,
        digest_field=_EVIDENCE_DIGEST_FIELD,
        rebuild=lambda: build_governed_paper_execution_evidence(inputs),  # type: ignore[arg-type]
        code="execution_evidence",
        reason=_reason,
    )


def governed_paper_cumulative_history(
    seal: GovernedPaperDaySeal,
) -> tuple[
    tuple[PaperSleeveEpisodeEvidence, ...],
    tuple[PaperSleeveDayCloseValuation, ...],
    tuple[PaperSleeveFundingEvent, ...],
]:
    """The cumulative history a SEALED seal carries (what the next cycle opens on); raises for any other seal."""

    if type(seal) is not GovernedPaperDaySeal or seal.status is not GovernedPaperDaySealStatus.SEALED:
        raise _fail("seal_not_sealed")
    return seal.episodes, seal.day_closes, seal.funding_events


__all__ = [
    "GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS",
    "GovernedPaperDayProtectionInputs",
    "GovernedPaperDaySeal",
    "GovernedPaperDaySealInputs",
    "GovernedPaperDaySealStatus",
    "GovernedPaperExecutionDay",
    "GovernedPaperExecutionDayRecord",
    "GovernedPaperExecutionError",
    "GovernedPaperExecutionEvidence",
    "GovernedPaperExecutionInputs",
    "GovernedPaperExecutionStatus",
    "build_governed_paper_day_seal",
    "build_governed_paper_execution_evidence",
    "governed_paper_cumulative_history",
    "governed_paper_day_seal_digest",
    "governed_paper_day_seal_to_dict",
    "governed_paper_execution_evidence_digest",
    "governed_paper_execution_evidence_to_dict",
    "verify_governed_paper_day_seal",
    "verify_governed_paper_outcome",
    "verify_governed_paper_execution_evidence",
]
