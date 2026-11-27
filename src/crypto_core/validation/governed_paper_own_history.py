"""Governed paper own-history authority (``S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1``): C-1 to C-6 and the readings C-7
consumes, derived from the ONE engine re-run and never accepted.

Design authority: ``docs/crypto_core/s1_own_history_measurement_doctrine_adoption_v1.md`` (decision
``S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1``, D1-D7) and ``docs/crypto_core/s1_own_history_residual_doctrine_adoption_v1.md``
(decision ``S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1``, P-1 to P-6, the readings RD-1 to RD-15, the shared numerical and
authority contract and FA-1 to FA-19), read with PRDV4 §0.3, §1.5, §1.6, §1.7 and §1.21, the approved companion §§3-4
and the incubation records r1 and HD-INC-AUTH-1 r2. Paper-only, deterministic, point-in-time and fail-closed. It creates
no order, approves nothing, qualifies no source and admits no entry.

The one authority. ``derive_governed_paper_own_history_evidence`` takes the replay authority of the governed outcome (the
authenticated economics result, its anchor and the outcome, whose schedule must be the engine's schedule v10), re-runs
the ONE engine under that schedule (``simulate_historical_execution_governed_paper_derivation``), requires the re-run's
outcome to equal the supplied one and reads only the re-run's own in-memory facts: the logical simulated submissions,
the own-edge valuation path and the trade close order (``historical_execution_economics`` schedule v10), the closed
trades' exact values, and the decision run's own evaluations over the authenticated archive. No count, score, flag,
state, peak, coverage or digest is ever supplied by a caller.

Knowledge time (P-2). Every fact sits at one coordinate ``(t, phase, native_sequence)`` over the engine's unchanged
equal-instant phases FUNDING, PROTECTIVE, DECISION, FILL, UTC_DAY_BOUNDARY, EVALUATION_END; a source publication, a mark
visibility and a time-defined instant (a window expiry, a deadline, a time-defined resolution) take the phase ``-1``
before every phase of its instant. A reading at ``(t, DECISION)`` sees the FUNDING and PROTECTIVE events of ``t``, the
publications visible at ``t`` and its own evaluation, and no FILL-phase event of ``t`` (RD-2, RD-11). Each coordinate is
evaluated once; a later publication acts from its own coordinate and never rewrites an earlier reading, transition,
coverage end or prefix (X1).

Completeness (P-2, E-1). Own history is proven complete through ``t`` only when the funding, mark and order-book series
the economics reads are each covered over ``[G, t]`` by coverage claims known at ``t`` and admitted by the active table
(``GovernedPaperOwnHistoryCoverage``): "no events observed does not prove no events occurred". The production table
admits no claim, and a HUMAN_GOVERNANCE claim would still need an M1-qualified source, which none is, so in production
every reading that needs completeness is UNPROVEN; tests alone install a test-only table for TEST_ONLY_SYNTHETIC claims.
A claim published at ``P`` is knowledge from ``P`` only.

The readings, each in one of D6's categories (DEFINED, INSUFFICIENT: proven insufficient history, UNDEFINED: complete
but mathematically undefined, UNPROVEN: missing or unproven):

* U1/U2, Sharpe_30d and Sharpe_90d (D1, C-2): the edge's own daily returns ``r = NAV_end / NAV_start - 1`` over the
  engine's UTC day-boundary valuations (a partial genesis day is never a completed day; a day is completed at its
  boundary valuation and known once every settlement it books is published), the latest 30 or 90 consecutive completed
  days, arithmetic mean, sample variance (n - 1), ``sqrt(365)``, no risk-free term; zero variance and a non-positive NAV
  are UNDEFINED; DECAY_ALERT is ``Sharpe_30d < 0.5 x Sharpe_90d``. NAV readings need exclusive one-edge attribution (a
  one-sleeve portfolio, P-5);
* U3/U4, FR_10 and FR_20 (D4, D5, P-4, C-5): over the logical simulated submissions in submission order (coordinate, then
  native sequence), the latest N: a fill ``filled / requested`` exact, a rejection at the book 0, a decision intent's own
  window close (RD-12) a conclusive 0 only on book coverage of its window known at the reading, anything else UNKNOWN; an
  unresolved member blocks the reading and is never skipped. Fewer than N submissions, all resolved, on complete history:
  INSUFFICIENT;
* S_hitrate and HIT_RATE_ALERT (P-6): one closed excursion per trade, membership by its closing coordinate in
  ``(t - 30d, t]``, admissible only once known (closing fill and every settlement's final rate); positive net is a win,
  zero and negative are non-wins; fewer than 10 known trades (zero included) on complete history give the neutral 0.5;
  HIT_RATE_ALERT needs two complete windows wholly after G with both rates defined and the strict comparison;
* S_drawdown (P-5): ``DD = 1 - NAV(t) / peak(t)`` over the own-edge valuation path from G, the peak never reset, each
  point usable only once known; a stale mark, an unknown point or incomplete coverage leaves only RD-9's lower bound over
  the known sampled points, which can prove the inclusive 5% Family B breach and never PASS;
* S_stability (D2, P-1, C-3): the exact signed mean of the latest N visible final funding rates of every scheduled H2
  evaluation of ``passive_funding_carry.v1`` (NO_ACTION, HOLD, EXIT and refused entries included), reconstructed from the
  decision's own input records over the archive, over ``(t - 30d, t]`` from G (an inception-truncated window only on
  complete history); an undefined evaluation inside the window, fewer than two values or a non-positive mean are
  UNDEFINED; a constant positive window has CV 0;
* EHS (D3): ``0.30 S_sharpe + 0.25 S_hitrate + 0.25 S_drawdown + 0.20 S_stability``, compared EXACTLY: S_sharpe and
  S_stability are of the form ``a + b sqrt(x)``, so every threshold comparison is the sign of ``r + c1 sqrt(x) + c2
  sqrt(y)``, decided by squaring with signs (``_sign_surd``); no float, epsilon or rendered decimal decides anything.

The state machine (D3, P-3, C-4) is replayed at every input change, decision, window expiry and deadline: the four PRDV4
states with STATE_NOT_ESTABLISHED as an evidence status, no default state, the first fully defined EHS (or a proven drawdown
breach) as the start, exact 0.70/0.30 thresholds, no direct DISABLED to ACTIVE step, recovery to WARNING only after a
proven continuous 48 hours of EHS >= 0.40 without a breach (any gap restarts the proof), ACTIVE only at a later
coordinate, the second distinct disable episode inside ``(t - 30d, t]`` entering QUARANTINE. QUARANTINE is never left
here: its release needs a fresh independent revalidation known before the release and a separate attributable release
authority (R-2, R-3), neither of which exists, so every release is BLOCKED; an EF-8 receipt is never an EHS state or
release, and nothing here clears or adds an EF-8 restriction (RD-7). When the disable condition becomes unknown while a
hidden DISABLED transition is possible (NOT_ESTABLISHED, ACTIVE or WARNING), the lifecycle is unproven from then on
(LIFECYCLE_UNPROVEN); a proven current disable condition still proves NT-E02's FAIL.

Coverage ends (C-6). A reading's coverage ends, irreversibly, at the first coordinate at which its window holds enough own
observations: 30 or 90 completed known days on complete history (U1, U2), 10 or 20 conclusively resolved submissions
(U3, U4); the cut instant is that instant, or the next nanosecond when it lies in the FILL phase or later, so no decision
of the same instant reads it early.

The checks C-7 reads (``GovernedPaperOwnHistoryCheck``): PASS, FAIL, COVERED (the only non-PASS input is a covered
reading proven insufficient, never failing under every completion; it becomes COLD_START_EXCEPTED only under an ACTIVE
record selecting those readings) or BLOCKED. A proven FAIL dominates every exception. The allocation eligibility of the
genesis sleeve is read at the latest rebalance (every UTC midnight and every state transition) through
``derive_governed_paper_allocation_decided``; activation is never PASS (the latency and API legs are X-H1), so no member
and no incubation member is reachable.

Non-claims: no production coverage, signal qualification, venue health, approved release, readiness, profitability or
edge. Exact integers and fractions; no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

import bisect
import heapq
from collections.abc import Sequence
from dataclasses import dataclass, field, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

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
from crypto_core.validation.governed_paper_allocation_envelope import (
    GovernedPaperAllocationActivation,
    GovernedPaperAllocationDecidedCandidate,
    GovernedPaperAllocationEligibility,
    derive_governed_paper_allocation_decided,
)
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperGenesisAuthority
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES,
    HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionTradeStatus,
    simulate_historical_execution_governed_paper_derivation,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_wire_int_is_valid
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, select_visible_pit_records
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    get_strategy_executable_profile,
)

GOVERNED_PAPER_OWN_HISTORY_CONTRACT_ID = "S1_OWN_HISTORY_UNIFIED_CONSTRUCTION_V1"
GOVERNED_PAPER_OWN_HISTORY_DECISION_IDS: tuple[str, ...] = (
    "S1_OWN_HISTORY_MEASUREMENT_METHOD_DECISION_V1",
    "S1_OWN_HISTORY_RESIDUAL_METHOD_DECISION_V1",
)
GOVERNED_PAPER_OWN_HISTORY_EVIDENCE_SCHEMA = "governed-paper-own-history-evidence.v1"
GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA = "governed-paper-own-history-coverage.v1"
GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL = "HUMAN_GOVERNANCE"
GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL = "TEST_ONLY_SYNTHETIC"
GOVERNED_PAPER_OWN_HISTORY_READING_IDS: tuple[str, ...] = ("U1", "U2", "U3", "U4")
GOVERNED_PAPER_OWN_HISTORY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("production_coverage_qualified", False),
    ("signal_provenance_qualified", False),
    ("venue_health_proven", False),
    ("quarantine_release_authorized", False),
    ("entry_authorized", False),
    ("stage4_credit", False),
    ("live_ready", False),
    ("edge_proven", False),
)

_PREFIX = "governed_paper_own_history"
_DIGEST_FIELD = "evidence_digest"
_SECOND_NS = 1_000_000_000
_HOUR_NS = 3_600 * _SECOND_NS
_DAY_NS = 24 * _HOUR_NS
_WINDOW_30D_NS = 30 * _DAY_NS
_WINDOW_90D_NS = 90 * _DAY_NS
_RECOVERY_NS = 48 * _HOUR_NS  # P-3: at least 48 hours, met at exactly 48 hours (RD-4)
_SHARPE_30D_DAYS, _SHARPE_90D_DAYS = 30, 90
_FR_10, _FR_20 = 10, 20
_PRE = -1  # the phase of a publication, a mark or a time-defined instant: before every engine phase of its instant
_FUNDING, _PROTECTIVE, _DECISION, _FILL, _DAY_BOUNDARY, _END = range(6)
_PHASES = {name: index for index, name in enumerate(HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES)}
# PRDV4 §1.6 and §1.7, exact.
_W_SHARPE, _W_HIT, _W_DRAWDOWN, _W_STABILITY = Fraction(3, 10), Fraction(1, 4), Fraction(1, 4), Fraction(1, 5)
_EHS_ACTIVE, _EHS_DISABLE, _EHS_RECOVERY, _EHS_ASSET, _EHS_BOOST = (
    Fraction(7, 10),
    Fraction(3, 10),
    Fraction(2, 5),
    Fraction(1, 2),
    Fraction(4, 5),
)
_ANNUALIZATION = Fraction(365)
_HIT_MINIMUM, _HIT_NEUTRAL, _HIT_FLOOR, _HIT_SPAN, _HIT_ALERT_GAP = (
    10,
    Fraction(1, 2),
    Fraction(7, 20),
    Fraction(3, 10),
    Fraction(1, 10),
)
_DRAWDOWN_MAX_FAMILY_B = Fraction(1, 20)  # PRDV4 §1.6: 5%, inclusive (P-5)
_NT_X02_FLOOR = Fraction(1, 2)  # PRDV4 §1.21: FR_10 < 50% fails, 0.50 does not
_EXECUTION_FORBIDDEN_AT_MOST = Fraction(7, 10)  # §1.5: FR_20 <= 0.70 is IMPAIRED or HALTED (the restrictive class)
_DECAY_RATIO = Fraction(1, 2)
_BOOST_SHARPE = Fraction(3, 2)

_Coordinate = tuple[int, int, int]


class GovernedPaperOwnHistoryError(EdgeArtifactError):
    """Malformed or foreign input: no own-history authority is ever represented over it."""


class GovernedPaperOwnHistoryStatus(str, Enum):
    """D6's categories of one reading."""

    DEFINED = "DEFINED"
    INSUFFICIENT = "INSUFFICIENT"  # proven insufficient own history
    UNDEFINED = "UNDEFINED"  # complete but mathematically undefined (or invalid)
    UNPROVEN = "UNPROVEN"  # missing or unproven


class GovernedPaperOwnHistoryEhsStatus(str, Enum):
    DEFINED = "DEFINED"
    U1_INSUFFICIENT_ONLY = "U1_INSUFFICIENT_ONLY"  # every component defined but S_sharpe, proven insufficient (U1)
    UNDEFINED = "UNDEFINED"
    UNPROVEN = "UNPROVEN"


class GovernedPaperOwnHistoryTruth(str, Enum):
    TRUE = "TRUE"
    FALSE = "FALSE"
    UNKNOWN = "UNKNOWN"


class GovernedPaperOwnHistoryState(str, Enum):
    """The four PRDV4 states, ``STATE_NOT_ESTABLISHED`` (an evidence status, P-3) and ``LIFECYCLE_UNPROVEN``."""

    STATE_NOT_ESTABLISHED = "STATE_NOT_ESTABLISHED"
    ACTIVE = "ACTIVE"
    WARNING = "WARNING"
    DISABLED = "DISABLED"
    QUARANTINE = "QUARANTINE"
    LIFECYCLE_UNPROVEN = "LIFECYCLE_UNPROVEN"


class GovernedPaperOwnHistoryOutcome(str, Enum):
    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    COVERED = "COVERED"  # COLD_START_EXCEPTED only under an ACTIVE record selecting ``covered``
    BLOCKED = "BLOCKED"


_St, _Ehs, _T, _State, _Out = (
    GovernedPaperOwnHistoryStatus,
    GovernedPaperOwnHistoryEhsStatus,
    GovernedPaperOwnHistoryTruth,
    GovernedPaperOwnHistoryState,
    GovernedPaperOwnHistoryOutcome,
)


# --- inputs ------------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperOwnHistoryCoverage:
    """One coverage claim: every publication of ``series_id`` for ``instrument`` from the archive ``source_manifest_digest``
    visible in ``[start_ns, end_ns)`` is in the archive (or proven absent). Knowledge only from ``published_at_ns``;
    positive authority only where the active table admits it. ``coverage_digest`` covers every other field."""

    schema: str
    source_manifest_digest: str
    instrument: str
    series_id: str
    start_ns: int
    end_ns: int
    channel: str
    published_at_ns: int
    coverage_digest: str


@dataclass(frozen=True)
class GovernedPaperOwnHistoryContext:
    """The own-history context of one evaluation, known at its horizon: the coverage claims, append-only in publication
    order. Never authority on its own."""

    coverages: tuple[GovernedPaperOwnHistoryCoverage, ...]


@dataclass(frozen=True)
class GovernedPaperOwnHistoryTable:
    """Which coverage claims may confer completeness. ``production`` admits only listed HUMAN_GOVERNANCE digests of an
    M1-qualified source (none exists); ``test_only`` admits only TEST_ONLY_SYNTHETIC claims and lists nothing."""

    table_id: str
    admitted_channel: str
    admitted_coverage_digests: tuple[str, ...]


# No separate human authorization lists any own-history coverage claim, and no archive source is M1-qualified.
GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE = GovernedPaperOwnHistoryTable(
    table_id="production", admitted_channel=GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL, admitted_coverage_digests=()
)
_TABLE = GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE  # tests alone install a test-only table
_M1_QUALIFIED_SOURCE_DIGESTS: frozenset[str] = frozenset()  # E-1: no source qualification exists


# --- derived artifacts -------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperOwnHistorySubmission:
    """One logical simulated submission of the re-run (P-4), its run-independent identity digest and its resolution as
    the engine reached it. Quantities are exact rational texts."""

    order_kind: str
    identity_digest: str
    native_sequence: int
    submitted_ns: int
    submitted_phase: str
    side: str
    exposure_increasing: bool
    requested_quantity: str
    reached_book: bool
    filled_quantity: str | None
    resolved_ns: int | None
    resolved_phase: str | None
    resolved_sequence: int | None
    window_open_ns: int | None
    window_close_ns: int | None
    window_close_in_horizon: bool
    reason: str


@dataclass(frozen=True)
class GovernedPaperOwnHistoryBoundary:
    """One day boundary of the own-edge NAV series: the genesis anchor when G is a UTC midnight, then every UTC day
    boundary the engine valued; ``known_ns`` is when every input of that NAV is visible."""

    boundary_ns: int
    nav: str
    known_ns: int


@dataclass(frozen=True)
class GovernedPaperOwnHistoryTrade:
    """One closed excursion (P-6): its closing coordinate, exact realized net PnL and knowledge instant."""

    close_ns: int
    close_phase: str
    close_sequence: int
    realized_net_pnl: str
    knowledge_ns: int
    win: bool


@dataclass(frozen=True)
class GovernedPaperOwnHistorySignal:
    """One scheduled H2 evaluation (P-1): its exact scalar, or none with the reason it is undefined."""

    decision_sequence: int
    evaluation_ns: int
    scalar: str | None
    reason: str


@dataclass(frozen=True)
class GovernedPaperOwnHistoryTransition:
    """One state transition at its coordinate; ``episode`` marks a new disable episode (a transition into DISABLED, or
    the second episode entering QUARANTINE)."""

    time_ns: int
    phase: int
    sequence: int
    state_from: GovernedPaperOwnHistoryState
    state_to: GovernedPaperOwnHistoryState
    episode: bool
    reason: str


@dataclass(frozen=True)
class GovernedPaperOwnHistoryCoverageEnd:
    """When one covered reading's window first holds enough own observations (None when it never does by the horizon);
    ``cut_ns`` is the instant from which a decision and a fill read the coverage as ended."""

    reading_id: str
    time_ns: int | None
    phase: int | None
    sequence: int | None
    cut_ns: int | None


@dataclass(frozen=True)
class GovernedPaperOwnHistoryCheck:
    """One check outcome the entry gate reads. ``covered`` names the U readings a COVERED outcome owes to."""

    outcome: GovernedPaperOwnHistoryOutcome
    observed: str
    reason: str
    covered: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperOwnHistoryReading:
    """The own-history readings of one entry decision at ``(t, DECISION)``; ``reading_digest`` covers the rest.

    Exact rationals are texts (``str(Fraction)``); an irrational quantity is reported only through its exact decided
    comparisons. ``coverage_ended`` names the U readings whose coverage has ended by this coordinate.
    """

    decision_sequence: int
    decision_time_ns: int
    complete: bool
    sharpe_30d_status: GovernedPaperOwnHistoryStatus
    completed_days: int
    sharpe_90d_status: GovernedPaperOwnHistoryStatus
    decay_alert: GovernedPaperOwnHistoryTruth
    fr_10_status: GovernedPaperOwnHistoryStatus
    fr_10: str | None
    fr_20_status: GovernedPaperOwnHistoryStatus
    fr_20: str | None
    resolved_observations: int
    unresolved_submissions: int
    hit_rate_status: GovernedPaperOwnHistoryStatus
    s_hitrate: str | None
    trade_count: int | None
    hit_rate_alert: GovernedPaperOwnHistoryTruth
    drawdown_status: GovernedPaperOwnHistoryStatus
    drawdown: str | None
    drawdown_lower_bound: str | None
    s_drawdown: str | None
    drawdown_breach: GovernedPaperOwnHistoryTruth
    stability_status: GovernedPaperOwnHistoryStatus
    signal_count: int
    ehs_status: GovernedPaperOwnHistoryEhsStatus
    ehs_at_least_0_30: GovernedPaperOwnHistoryTruth
    ehs_above_0_50: GovernedPaperOwnHistoryTruth
    ehs_at_least_0_70: GovernedPaperOwnHistoryTruth
    ehs_above_0_80: GovernedPaperOwnHistoryTruth
    state: GovernedPaperOwnHistoryState
    state_reason: str
    disable_condition: GovernedPaperOwnHistoryTruth
    coverage_ended: tuple[str, ...]
    execution_forbidden: GovernedPaperOwnHistoryTruth
    nt_e01: GovernedPaperOwnHistoryCheck
    nt_e02: GovernedPaperOwnHistoryCheck
    nt_e04: GovernedPaperOwnHistoryCheck
    nt_x02: GovernedPaperOwnHistoryCheck
    fill_leg: GovernedPaperOwnHistoryCheck
    alpha_edge: GovernedPaperOwnHistoryCheck
    de_weight: GovernedPaperOwnHistoryCheck
    allocation_rebalance_ns: int | None
    allocation_eligibility: GovernedPaperAllocationEligibility
    allocation_weight: str | None
    allocation_reason: str
    reading_digest: str


@dataclass(frozen=True)
class GovernedPaperOwnHistoryEvidence:
    """The own-history evidence of one governed evaluation; ``evidence_digest`` covers the rest."""

    schema_version: str
    contract_id: str
    decision_ids: tuple[str, ...]
    genesis_id: str
    genesis_digest: str
    instrument: str
    run_digest: str
    dataset_digest: str
    economics_result_digest: str
    outcome_digest: str
    schedule_digest: str
    start_ns: int
    horizon_ns: int
    table_id: str
    coverage_digests: tuple[str, ...]
    coverage_refusals: tuple[str, ...]
    required_series: tuple[str, ...]
    exclusive_attribution: bool
    signal_profile_registered: bool
    submissions: tuple[GovernedPaperOwnHistorySubmission, ...]
    boundaries: tuple[GovernedPaperOwnHistoryBoundary, ...]
    trades: tuple[GovernedPaperOwnHistoryTrade, ...]
    signals: tuple[GovernedPaperOwnHistorySignal, ...]
    transitions: tuple[GovernedPaperOwnHistoryTransition, ...]
    lifecycle_unproven_from_ns: int | None
    lifecycle_reason: str
    coverage_ends: tuple[GovernedPaperOwnHistoryCoverageEnd, ...]
    readings: tuple[GovernedPaperOwnHistoryReading, ...]
    evidence_digest: str
    paper_only: bool = True
    production_coverage_qualified: bool = False
    signal_provenance_qualified: bool = False
    venue_health_proven: bool = False
    quarantine_release_authorized: bool = False
    entry_authorized: bool = False
    stage4_credit: bool = False
    live_ready: bool = False
    edge_proven: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _fail(code: str) -> GovernedPaperOwnHistoryError:
    return GovernedPaperOwnHistoryError(f"{_PREFIX}:{code}")


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _text(value: object) -> bool:
    return (
        type(value) is str
        and 0 < len(value) <= 256
        and value == value.strip()
        and not any(ord(char) < 32 or ord(char) == 127 for char in value)
        and edge_scope_violation(value) is None
    )


def _rational(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def _truth(value: bool | None) -> GovernedPaperOwnHistoryTruth:
    return _T.UNKNOWN if value is None else (_T.TRUE if value else _T.FALSE)


def _sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def governed_paper_own_history_coverage_digest(coverage: GovernedPaperOwnHistoryCoverage) -> str:
    """The canonical digest of one coverage claim, excluding only ``coverage_digest``."""

    return edge_payload_digest(_payload(coverage), "coverage_digest")


# --- exact comparisons of a + b sqrt(x) + c sqrt(y) (the shared numerical contract) -------------------------------------


def _sign_root(p: Fraction, q: Fraction, r: Fraction) -> int:
    """The exact sign of ``p + q sqrt(r)`` with ``r >= 0``."""

    if q == 0 or r == 0:
        return _sign(p)
    sq = _sign(q)
    if p == 0:
        return sq
    sp = _sign(p)
    if sp == sq:
        return sp
    difference = p * p - q * q * r  # |p| against |q| sqrt(r), compared by squares
    return sp if difference > 0 else (sq if difference < 0 else 0)


def _sign_surd(constant: Fraction, terms: tuple[tuple[Fraction, Fraction], ...]) -> int:
    """The exact sign of ``constant + sum(c_i sqrt(x_i))`` for at most two radical terms (``x_i >= 0``)."""

    live = tuple((coefficient, radicand) for coefficient, radicand in terms if coefficient != 0 and radicand != 0)
    if not live:
        return _sign(constant)
    if len(live) == 1:
        return _sign_root(constant, *live[0])
    if len(live) > 2:  # pragma: no cover - EHS has at most two radical components
        raise _fail("surd_with_more_than_two_radicals")
    (a, x), (b, y) = live
    first = _sign_root(constant, a, x)  # the sign of u = constant + a sqrt(x)
    second = _sign(b)
    if first == 0:
        return second
    if first == second:
        return first
    # u and b sqrt(y) have opposite signs: compare u^2 = constant^2 + a^2 x + 2 constant a sqrt(x) with b^2 y
    squares = _sign_root(constant * constant + a * a * x - b * b * y, 2 * constant * a, x)
    return first if squares > 0 else (second if squares < 0 else 0)


@dataclass(frozen=True)
class _Surd:
    """``constant + sum(c sqrt(x))``: an exact algebraic reading with at most two radical terms."""

    constant: Fraction
    terms: tuple[tuple[Fraction, Fraction], ...] = ()

    def compare(self, threshold: Fraction) -> int:
        return _sign_surd(self.constant - threshold, self.terms)


def _add(*parts: tuple[Fraction, _Surd]) -> _Surd:
    constant = sum((weight * part.constant for weight, part in parts), Fraction(0))
    terms = tuple((weight * c, x) for weight, part in parts for c, x in part.terms)
    return _Surd(constant, terms)


@dataclass(frozen=True)
class _Sharpe:
    """``Sharpe = mean x sqrt(365 / variance)`` with a positive sample variance."""

    mean: Fraction
    radicand: Fraction  # 365 / variance

    def score(self) -> _Surd:
        """S_sharpe = min(1, max(0, Sharpe / 2)), exact."""

        half = self.mean / 2
        if half <= 0:
            return _Surd(Fraction(0))
        if half * half * self.radicand >= 1:
            return _Surd(Fraction(1))
        return _Surd(Fraction(0), ((half, self.radicand),))


@dataclass(frozen=True)
class _Stability:
    """A defined signal window: positive mean, non-negative sample variance."""

    mean: Fraction
    variance: Fraction

    def score(self) -> _Surd:
        """S_stability = min(1, max(0, 1 - CV / 2)) with CV = sqrt(variance) / mean, exact."""

        if self.variance == 0:
            return _Surd(Fraction(1))
        factor = 1 / (2 * self.mean)
        if factor * factor * self.variance >= 1:
            return _Surd(Fraction(0))
        return _Surd(Fraction(1), ((-factor, self.variance),))


def _sharpe_of(navs: Sequence[Fraction]) -> _Sharpe | None:
    """The D1 Sharpe of consecutive positive day-boundary NAVs; None on zero variance (HC-13a: BLOCKED)."""

    returns = [later / earlier - 1 for earlier, later in zip(navs, navs[1:], strict=False)]
    count = len(returns)
    mean = sum(returns, Fraction(0)) / count
    variance = sum(((item - mean) ** 2 for item in returns), Fraction(0)) / (count - 1)
    if variance == 0:
        return None
    return _Sharpe(mean, _ANNUALIZATION / variance)


# --- the coverage authority --------------------------------------------------------------------------------------------


def canonical_governed_paper_own_history_context(context: object) -> GovernedPaperOwnHistoryContext:
    """Validate one own-history context exactly: typed claims, recomputed digests, publication order, no duplicate."""

    if type(context) is not GovernedPaperOwnHistoryContext or type(context.coverages) is not tuple:
        raise _fail("context_malformed")
    seen: set[str] = set()
    previous = -1
    for claim in context.coverages:
        if (
            type(claim) is not GovernedPaperOwnHistoryCoverage
            or claim.schema != GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA
        ):
            raise _fail("coverage_malformed")
        if not edge_is_hex64(claim.source_manifest_digest) or not _text(claim.instrument) or not _text(claim.series_id):
            raise _fail("coverage_malformed")
        for value in (claim.start_ns, claim.end_ns, claim.published_at_ns):
            if not historical_execution_wire_int_is_valid(value, minimum=0):
                raise _fail("coverage_malformed")
        if claim.end_ns <= claim.start_ns:
            raise _fail("coverage_interval_empty")
        if claim.channel not in (GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL, GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL):
            raise _fail("coverage_channel_unknown")
        if governed_paper_own_history_coverage_digest(claim) != claim.coverage_digest:
            raise _fail("coverage_digest_mismatch")
        if claim.coverage_digest in seen:
            raise _fail("coverage_duplicated")
        if claim.published_at_ns < previous:
            raise _fail("coverage_not_in_publication_order")
        seen.add(claim.coverage_digest)
        previous = claim.published_at_ns
    return context


def _canonical_table(table: object) -> GovernedPaperOwnHistoryTable:
    if type(table) is not GovernedPaperOwnHistoryTable or type(table.admitted_coverage_digests) is not tuple:
        raise _fail("table_malformed")
    if table.table_id == "production" and table.admitted_channel == GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL:
        return table
    if (
        table.table_id == "test_only"
        and table.admitted_channel == GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL
        and table.admitted_coverage_digests == ()
    ):
        return table
    raise _fail("table_malformed")


def governed_paper_own_history_active_table() -> GovernedPaperOwnHistoryTable:
    """The table the derivation reads (the production table unless a test installed a test-only one)."""

    return _canonical_table(_TABLE)


def _admission(
    table: GovernedPaperOwnHistoryTable,
    claim: GovernedPaperOwnHistoryCoverage,
    *,
    source_manifest_digest: str,
    instrument: str,
    required: tuple[str, ...],
) -> str:
    """'' when the active table admits the claim for this archive; otherwise the fixed refusal reason."""

    if claim.source_manifest_digest != source_manifest_digest or claim.instrument != instrument:
        return "coverage_of_another_archive_or_instrument"
    if claim.series_id not in required:
        return "coverage_of_a_series_the_economics_does_not_read"
    if claim.channel != table.admitted_channel:
        return "coverage_channel_not_admitted_by_the_active_table"
    if table.table_id == "production":
        if claim.coverage_digest not in table.admitted_coverage_digests:
            return "coverage_not_listed_by_the_production_table"
        if source_manifest_digest not in _M1_QUALIFIED_SOURCE_DIGESTS:  # E-1: no source is M1-qualified
            return "coverage_source_not_m1_qualified"
    return ""


class _Coverage:
    """The admitted claims per required series, each known from its own publication."""

    def __init__(self, admitted: Sequence[GovernedPaperOwnHistoryCoverage], required: tuple[str, ...]) -> None:
        self.required = required
        self.claims: dict[str, list[tuple[int, int, int]]] = {series: [] for series in required}
        for claim in admitted:
            self.claims[claim.series_id].append((claim.start_ns, claim.end_ns, claim.published_at_ns))
        for series in required:
            self.claims[series].sort()
        self.publications = sorted({item[2] for series in required for item in self.claims[series]})
        self.ends = sorted({item[1] for series in required for item in self.claims[series]})

    def covered(self, series: str, start_ns: int, through_ns: int, at_ns: int) -> bool:
        """``series`` is covered over ``[start_ns, through_ns]`` by claims published at or before ``at_ns``."""

        cursor = start_ns
        for low, high, published in self.claims[series]:  # ordered by start
            if published > at_ns:
                continue
            if low > cursor:
                break
            cursor = max(cursor, high)
            if cursor > through_ns:
                return True
        return cursor > through_ns

    def complete(self, start_ns: int, through_ns: int, at_ns: int) -> bool:
        return all(self.covered(series, start_ns, through_ns, at_ns) for series in self.required)

    def known_from(self, series: str, start_ns: int, through_ns: int) -> int | None:
        """The earliest instant at which ``series`` is known covered over ``[start_ns, through_ns]`` (None: never)."""

        for instant in self.publications:
            if self.covered(series, start_ns, through_ns, instant):
                return instant
        return None


# --- the derivation ----------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Sub:
    key: _Coordinate
    requested: Fraction
    filled: Fraction | None
    resolved_key: _Coordinate | None
    window_open: int | None
    window_close: int | None  # set only for a decision intent without a book whose close precedes the horizon
    record: GovernedPaperOwnHistorySubmission


@dataclass(frozen=True)
class _Inputs:
    """Everything the readings and the state machine read at one coordinate."""

    complete: bool
    sharpe_30: tuple[GovernedPaperOwnHistoryStatus, _Sharpe | None]
    completed_days: int
    sharpe_90: tuple[GovernedPaperOwnHistoryStatus, _Sharpe | None]
    hit: tuple[GovernedPaperOwnHistoryStatus, Fraction | None, int | None]
    drawdown: tuple[GovernedPaperOwnHistoryStatus, Fraction | None, Fraction | None, bool | None]
    stability: tuple[GovernedPaperOwnHistoryStatus, _Stability | None, int]
    ehs: tuple[GovernedPaperOwnHistoryEhsStatus, _Surd | None]

    @property
    def breach(self) -> bool | None:
        return self.drawdown[3]

    def disable_condition(self) -> bool | None:
        """True on a proven breach or a defined EHS below 0.30; False on a proven absence of both; None otherwise."""

        status, value = self.ehs
        if self.breach is True or (status is _Ehs.DEFINED and value.compare(_EHS_DISABLE) < 0):  # type: ignore[union-attr]
            return True
        if self.breach is False and status is not _Ehs.UNPROVEN:
            return False
        return None


@dataclass(frozen=True)
class _Lineage:
    """The lineage facts one derivation binds, derived from the verified genesis authority (``_lineage_of``)."""

    genesis_id: str
    genesis_digest: str
    instrument: str
    start_ns: int
    sleeve_id: str
    candidates: tuple[str, ...]
    executable_binding_digest: str
    source_manifest_digest: str
    economics_policy_digest: str

    @property
    def exclusive(self) -> bool:
        """P-5: the shared engine equity is the edge's own only for a one-sleeve paper portfolio of the genesis sleeve."""

        return self.candidates == (self.sleeve_id,)


def _lineage_of(authority: GovernedPaperGenesisAuthority) -> _Lineage:
    genesis = authority.genesis
    return _Lineage(
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        instrument=genesis.instrument,
        start_ns=genesis.genesis_start_ns,
        sleeve_id=genesis.sleeve_id,
        candidates=tuple(item.sleeve_id for item in authority.portfolio_risk_envelope.sleeve_caps),
        executable_binding_digest=genesis.executable_binding_digest,
        source_manifest_digest=genesis.source_manifest_digest,
        economics_policy_digest=genesis.economics_policy_digest,
    )


def _point_key(point: object) -> _Coordinate:
    """The coordinate of one valuation point; the genesis anchor precedes every other fact of its instant."""

    if point.kind == "INITIAL":  # type: ignore[attr-defined]
        return (point.time_ns, _PRE, -2)  # type: ignore[attr-defined]
    return (point.time_ns, point.phase, point.native_sequence)  # type: ignore[attr-defined]


class _Derivation:  # noqa: PLR0902 - the facts of one evaluation
    """The one derivation over one re-run's facts (see the module docstring)."""

    def __init__(  # noqa: PLR0913, PLR0915 - one linear construction over authenticated facts
        self,
        *,
        lineage: _Lineage,
        run: HistoricalDecisionRun,
        dataset: HistoricalPitDataset,
        result: HistoricalExecutionEconomicsResult,
        derivation: object,
        coverage: _Coverage,
    ) -> None:
        self.start = lineage.start_ns
        self.horizon = run.evaluation_end_ns
        self.coverage = coverage
        self.exclusive = lineage.exclusive
        self.sleeve = lineage.sleeve_id
        self.candidates = lineage.candidates
        self.book_series = result.order_book_series_id
        # the valuation path (C-1): keys, NAVs, knowledge, the first stale point, the running maximum of fresh NAVs
        path = derivation.valuation_path  # type: ignore[attr-defined]
        self.path_keys: list[_Coordinate] = [_point_key(item) for item in path]
        self.path_navs: list[Fraction | None] = [item.nav for item in path]
        self.path_known: list[int] = [item.known_ns for item in path]
        self.first_stale = next((index for index, item in enumerate(path) if item.nav is None), None)
        self.path_peak: list[Fraction | None] = []
        best: Fraction | None = None
        for item in path:
            if item.nav is not None and (best is None or item.nav > best):
                best = item.nav
            self.path_peak.append(best)
        # the day boundaries (D1): the genesis anchor at a UTC midnight, then every UTC day boundary
        boundaries = [
            item
            for item in path
            if item.kind == "UTC_DAY_BOUNDARY" or (item.kind == "INITIAL" and item.time_ns % _DAY_NS == 0)
        ]
        self.bound_keys = [_point_key(item) for item in boundaries]
        self.bound_navs: list[Fraction] = [item.nav for item in boundaries]  # type: ignore[misc]
        self.bound_known = [item.known_ns for item in boundaries]
        self.boundaries = tuple(
            GovernedPaperOwnHistoryBoundary(item.time_ns, str(item.nav), item.known_ns) for item in boundaries
        )
        self.sharpe_cache: dict[tuple[int, int], _Sharpe | None] = {}
        # the closed excursions (P-6)
        outcome = derivation.outcome  # type: ignore[attr-defined]
        closed = [item for item in outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED]
        phases = derivation.trade_close_phases  # type: ignore[attr-defined]
        sequences = derivation.trade_close_sequences  # type: ignore[attr-defined]
        exact = derivation.trade_exact_values  # type: ignore[attr-defined]
        if not len(closed) == len(phases) == len(sequences) == len(exact):  # pragma: no cover - one re-run's facts
            raise _fail("trade_facts_misaligned")
        trades = sorted(
            (
                (item.end_time_ns, _PHASES[phase], sequence, value.realized_net_pnl, value.knowledge_ns)
                for item, phase, sequence, value in zip(closed, phases, sequences, exact, strict=True)
            ),
            key=lambda row: row[:3],
        )
        self.trade_keys = [row[:3] for row in trades]
        self.trade_times = [row[0] for row in trades]
        self.trade_nets = [row[3] for row in trades]
        self.trade_known = [row[4] for row in trades]
        self.trades = tuple(
            GovernedPaperOwnHistoryTrade(
                row[0], HISTORICAL_EXECUTION_EQUAL_INSTANT_PHASES[row[1]], row[2], str(row[3]), row[4], row[3] > 0
            )
            for row in trades
        )
        # the logical simulated submissions (C-5), in submission order
        subs: list[_Sub] = []
        for item in derivation.submissions:  # type: ignore[attr-defined]
            identity = _digest_of([item.order_kind, *item.order_identity])
            record = GovernedPaperOwnHistorySubmission(
                order_kind=item.order_kind,
                identity_digest=identity,
                native_sequence=item.native_sequence,
                submitted_ns=item.submitted_ns,
                submitted_phase=item.submitted_phase,
                side=item.side,
                exposure_increasing=item.exposure_increasing,
                requested_quantity=str(item.requested_quantity),
                reached_book=item.reached_book,
                filled_quantity=_rational(item.filled_quantity),
                resolved_ns=item.resolved_ns,
                resolved_phase=item.resolved_phase,
                resolved_sequence=item.resolved_sequence,
                window_open_ns=item.window_open_ns,
                window_close_ns=item.window_close_ns,
                window_close_in_horizon=item.window_close_in_horizon,
                reason=item.reason,
            )
            resolved = (
                (item.resolved_ns, _PHASES[item.resolved_phase], item.resolved_sequence) if item.reached_book else None
            )
            close = item.window_close_ns if not item.reached_book and item.window_close_in_horizon else None
            subs.append(
                _Sub(
                    (item.submitted_ns, _PHASES[item.submitted_phase], item.native_sequence),
                    item.requested_quantity,
                    item.filled_quantity,
                    resolved,  # type: ignore[arg-type]
                    item.window_open_ns,
                    close,
                    record,
                )
            )
        if any(later.key <= earlier.key for earlier, later in zip(subs, subs[1:], strict=False)):
            raise _fail("submissions_not_in_processing_order")  # pragma: no cover - the engine records them in order
        if len({item.record.identity_digest for item in subs}) != len(subs):
            raise _fail("submission_identity_duplicated")  # pragma: no cover - one identity per engine order
        self.subs = subs
        self.sub_keys = [item.key for item in subs]
        # the scheduled H2 evaluations (P-1): every decision of the run, its exact scalar from its own input records
        registered = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
        self.profile_registered = (
            run.profile_id == registered.profile_id
            and run.profile_semantics_digest == registered.profile_semantics_digest
        )
        self.signals = tuple(self._signal(run, dataset, item, registered) for item in run.decisions)
        self.eval_keys: list[_Coordinate] = [(item.evaluation_ns, _DECISION, -2) for item in self.signals]
        self.eval_times = [item.evaluation_ns for item in self.signals]
        self.eval_values: list[Fraction | None] = [
            None if item.scalar is None else Fraction(item.scalar) for item in self.signals
        ]
        self.stability_cache: dict[tuple[int, int], tuple[GovernedPaperOwnHistoryStatus, _Stability | None]] = {}
        self.decisions = run.decisions

    def _signal(
        self, run: HistoricalDecisionRun, dataset: HistoricalPitDataset, decision: object, registered: object
    ) -> GovernedPaperOwnHistorySignal:
        sequence, instant = decision.decision_sequence, decision.decision_time_ns  # type: ignore[attr-defined]
        if not self.profile_registered:
            return GovernedPaperOwnHistorySignal(sequence, instant, None, "signal_semantics_of_an_unregistered_profile")
        lookback_text = next(
            (item.value for item in run.parameter_assignment if item.parameter_id == "final_funding_lookback_count"),
            None,
        )
        exact = Fraction(lookback_text) if lookback_text is not None else Fraction(0)
        lookback = exact.numerator if exact.denominator == 1 and exact > 0 else 0
        if lookback <= 0:  # pragma: no cover - the registered profile's schema requires a positive integer N
            return GovernedPaperOwnHistorySignal(sequence, instant, None, "lookback_parameter_unproven")
        if decision.used_observation_count < lookback or decision.feature_mean is None:  # type: ignore[attr-defined]
            return GovernedPaperOwnHistorySignal(sequence, instant, None, "fewer_than_n_visible_final_rates")
        view = select_visible_pit_records(
            dataset, series_id=run.funding_series_id, instrument=run.instrument, decision_time_ns=instant
        )
        used = view.records[len(view.records) - lookback :]
        if tuple(item.record_digest for item in used) != decision.input_record_digests:  # type: ignore[attr-defined]
            raise _fail("decision_inputs_not_the_latest_visible_final_rates")  # pragma: no cover - a verified run
        value_name = registered.required_value_names[0]  # type: ignore[attr-defined]
        rates = [Fraction(next(value.value for value in item.values if value.name == value_name)) for item in used]
        return GovernedPaperOwnHistorySignal(sequence, instant, str(sum(rates, Fraction(0)) / lookback), "")

    # -- the readings at one coordinate, as known at an instant (P-2: knowledge acts forward only) --

    def complete(self, through_ns: int, at_ns: int) -> bool:
        return self.coverage.complete(self.start, through_ns, at_ns)

    def sharpe(
        self, key: _Coordinate, days: int, complete: bool, at_ns: int
    ) -> tuple[tuple[GovernedPaperOwnHistoryStatus, _Sharpe | None], int]:
        count = bisect.bisect_left(self.bound_keys, key)  # boundaries strictly before the coordinate
        completed = max(0, count - 1)
        if not self.exclusive or not complete:
            return (_St.UNPROVEN, None), completed
        if completed and self.bound_known[count - 1] > at_ns:  # the latest completed day awaits a publication
            return (_St.UNPROVEN, None), completed
        if completed < days:
            if any(nav <= 0 for nav in self.bound_navs[:count]):
                return (_St.UNDEFINED, None), completed
            return (_St.INSUFFICIENT, None), completed
        navs = self.bound_navs[count - 1 - days : count]
        if any(nav <= 0 for nav in navs):
            return (_St.UNDEFINED, None), completed
        cache_key = (count, days)
        if cache_key not in self.sharpe_cache:
            self.sharpe_cache[cache_key] = _sharpe_of(navs)
        found = self.sharpe_cache[cache_key]
        return ((_St.UNDEFINED, None) if found is None else (_St.DEFINED, found)), completed

    def hit(
        self, key: _Coordinate, complete: bool, at_ns: int, window: int = _WINDOW_30D_NS
    ) -> tuple[GovernedPaperOwnHistoryStatus, Fraction | None, int | None, Fraction | None]:
        low = bisect.bisect_right(self.trade_times, key[0] - window)
        high = bisect.bisect_left(self.trade_keys, key)
        if not complete or any(self.trade_known[index] > at_ns for index in range(low, high)):
            return _St.UNPROVEN, None, None, None
        count = high - low
        wins = sum(1 for index in range(low, high) if self.trade_nets[index] > 0)
        rate = None if count == 0 else Fraction(wins, count)
        if count < _HIT_MINIMUM:
            return _St.DEFINED, _HIT_NEUTRAL, count, rate
        score = min(Fraction(1), max(Fraction(0), (rate - _HIT_FLOOR) / _HIT_SPAN))  # type: ignore[operator]
        return _St.DEFINED, score, count, rate

    def drawdown(
        self, key: _Coordinate, complete: bool, at_ns: int
    ) -> tuple[GovernedPaperOwnHistoryStatus, Fraction | None, Fraction | None, bool | None]:
        index = bisect.bisect_right(self.path_keys, key) - 1
        if index < 0 or not self.exclusive:
            return _St.UNPROVEN, None, None, None
        known = bisect.bisect_right(self.path_known, at_ns) - 1
        current = self.path_navs[index]
        if index > known or current is None:  # the NAV at the coordinate is not known (or no valuation exists there)
            return _St.UNPROVEN, None, None, None
        peak = self.path_peak[index]
        if peak is None or peak <= 0:  # pragma: no cover - the genesis anchor is a positive initial equity
            return _St.UNPROVEN, None, None, None
        value = 1 - current / peak
        if complete and (self.first_stale is None or self.first_stale > index):
            return _St.DEFINED, value, value, value >= _DRAWDOWN_MAX_FAMILY_B
        # RD-9: the sampled peak bounds the true one from below, so this is a lower bound: it proves FAIL only
        return _St.UNPROVEN, None, value, True if value >= _DRAWDOWN_MAX_FAMILY_B else None

    def stability(
        self, key: _Coordinate, complete: bool
    ) -> tuple[GovernedPaperOwnHistoryStatus, _Stability | None, int]:
        low = bisect.bisect_right(self.eval_times, key[0] - _WINDOW_30D_NS)
        high = bisect.bisect_left(self.eval_keys, key)
        count = max(0, high - low)
        if not self.profile_registered or not complete:
            return _St.UNPROVEN, None, count
        cache_key = (low, high)
        if cache_key not in self.stability_cache:
            values = self.eval_values[low:high]
            if count < 2 or any(value is None for value in values):  # noqa: PLR2004 - P-1: at least two defined values
                found: tuple[GovernedPaperOwnHistoryStatus, _Stability | None] = (_St.UNDEFINED, None)
            else:
                mean = sum(values, Fraction(0)) / count  # type: ignore[arg-type]
                if mean <= 0:  # D2: a non-positive mean is BLOCKED, never made eligible by a sign change
                    found = (_St.UNDEFINED, None)
                else:
                    variance = sum(((value - mean) ** 2 for value in values), Fraction(0)) / (count - 1)  # type: ignore[operator]
                    found = (_St.DEFINED, _Stability(mean, variance))
            self.stability_cache[cache_key] = found
        status, value = self.stability_cache[cache_key]
        return status, value, count

    def inputs(self, key: _Coordinate, at_ns: int | None = None) -> _Inputs:
        """Every reading at the coordinate ``key`` as known at ``at_ns`` (its own instant by default)."""

        at = key[0] if at_ns is None else at_ns
        complete = self.complete(key[0], at)
        sharpe_30, completed = self.sharpe(key, _SHARPE_30D_DAYS, complete, at)
        sharpe_90, _ = self.sharpe(key, _SHARPE_90D_DAYS, complete, at)
        hit = self.hit(key, complete, at)[:3]
        drawdown = self.drawdown(key, complete, at)
        stability = self.stability(key, complete)
        statuses = (hit[0], drawdown[0], stability[0])
        if sharpe_30[0] is _St.UNPROVEN or _St.UNPROVEN in statuses:
            ehs: tuple[GovernedPaperOwnHistoryEhsStatus, _Surd | None] = (_Ehs.UNPROVEN, None)
        elif _St.UNDEFINED in statuses or sharpe_30[0] is _St.UNDEFINED:
            ehs = (_Ehs.UNDEFINED, None)
        else:
            base = _add(
                (_W_HIT, _Surd(hit[1])),  # type: ignore[arg-type]
                (_W_DRAWDOWN, _Surd(max(Fraction(0), 1 - drawdown[1] / _DRAWDOWN_MAX_FAMILY_B))),  # type: ignore[operator]
                (_W_STABILITY, stability[1].score()),  # type: ignore[union-attr]
            )
            if sharpe_30[0] is _St.INSUFFICIENT:
                ehs = (_Ehs.U1_INSUFFICIENT_ONLY, base)
            else:
                ehs = (_Ehs.DEFINED, _add((Fraction(1), base), (_W_SHARPE, sharpe_30[1].score())))  # type: ignore[union-attr]
        return _Inputs(complete, sharpe_30, completed, sharpe_90, hit, drawdown, stability, ehs)

    def fill_rate(
        self, key: _Coordinate, size: int, complete: bool
    ) -> tuple[GovernedPaperOwnHistoryStatus, Fraction | None, Fraction, int, int]:
        """``(status, FR_N, the sum of the known fractions, the known count, the unresolved count)`` at ``key``."""

        high = bisect.bisect_left(self.sub_keys, key)
        members = self.subs[max(0, high - size) : high]
        fractions = [self.fraction(item, key) for item in members]
        known = [value for value in fractions if value is not None]
        unresolved = len(fractions) - len(known)
        total = sum(known, Fraction(0))
        if high < size:
            if unresolved == 0 and complete:
                return _St.INSUFFICIENT, None, total, len(known), 0
            return _St.UNPROVEN, None, total, len(known), unresolved
        if unresolved:
            return _St.UNPROVEN, None, total, len(known), unresolved
        return _St.DEFINED, total / size, total, size, 0

    def fraction(self, item: _Sub, key: _Coordinate) -> Fraction | None:
        """The submission's fill fraction as known at ``key``, or None while unresolved there (RD-12)."""

        if item.resolved_key is not None:
            return item.filled / item.requested if item.resolved_key < key else None  # type: ignore[operator]
        if item.window_close is not None and item.window_close <= key[0]:
            if self.coverage.covered(self.book_series, item.window_open, item.window_close, key[0]):  # type: ignore[arg-type]
                return Fraction(0)
        return None

    def resolved_count(self, key: _Coordinate) -> int:
        high = bisect.bisect_left(self.sub_keys, key)
        return sum(1 for item in self.subs[:high] if self.fraction(item, key) is not None)


# --- the state machine (P-3), replayed in knowledge time -----------------------------------------------------------------

_HIDDEN_TRANSITION_POSSIBLE = (_State.STATE_NOT_ESTABLISHED, _State.ACTIVE, _State.WARNING)


@dataclass
class _Machine:
    """The state machine over the coordinates in event order, each processed once its disable condition is known.

    A coordinate whose disable condition is not yet known (a settlement or a trade awaiting its final rate, a day awaiting
    its publication, coverage not yet known) waits, with every later one, in ``pending``; each new coordinate first
    re-reads the waiting ones with its own knowledge and processes, in order, every one now known. A transition is dated
    at the coordinate it becomes known at (never earlier), so later knowledge acts forward only and never rewrites an
    earlier reading or transition (X1). A coordinate that never becomes known keeps every later one waiting: from
    STATE_NOT_ESTABLISHED, ACTIVE or WARNING a hidden DISABLED transition is then possible, so no later state is proven;
    DISABLED and QUARANTINE admit no hidden transition and stay proven, and DISABLED never recovers across it.
    """

    state: GovernedPaperOwnHistoryState = _State.STATE_NOT_ESTABLISHED
    episodes: list[int] = field(default_factory=list)
    recovery_start: int | None = None
    transitions: list[GovernedPaperOwnHistoryTransition] = field(default_factory=list)
    pending: list[_Coordinate] = field(default_factory=list)

    @property
    def proven(self) -> bool:
        return not self.pending or self.state not in _HIDDEN_TRANSITION_POSSIBLE

    def _move(self, now: _Coordinate, target: GovernedPaperOwnHistoryState, episode: bool, reason: str) -> None:
        self.transitions.append(
            GovernedPaperOwnHistoryTransition(now[0], now[1], now[2], self.state, target, episode, reason)
        )
        self.state = target

    def advance(self, facts: _Derivation, now: _Coordinate, inputs: _Inputs) -> list[int]:
        """Process every waiting coordinate known at ``now`` and then ``now`` itself (or queue it); the recovery
        deadlines to schedule."""

        self.pending.append(now)
        deadlines: list[int] = []
        while self.pending and self.state is not _State.QUARANTINE:  # QUARANTINE is never released here (R-2, R-3)
            event = self.pending[0]
            known = inputs if event == now else facts.inputs(event, now[0])
            disable = known.disable_condition()
            if disable is None:
                return deadlines  # it waits for knowledge, and every later coordinate with it
            self.pending.pop(0)
            deadline = self._process(event, known, disable, now)
            if deadline is not None:
                if (deadline, _PRE, -1) <= now:  # the deadline has passed: it is read in order with the waiting ones
                    bisect.insort(self.pending, (deadline, _PRE, -1))
                else:
                    deadlines.append(deadline)
        if self.state is _State.QUARANTINE:
            self.pending.clear()
        return deadlines

    def _process(  # noqa: PLR0911 - one linear reading of P-3
        self, event: _Coordinate, inputs: _Inputs, disable: bool, now: _Coordinate
    ) -> int | None:
        status, value = inputs.ehs
        if self.state is _State.DISABLED:
            recovering = (
                disable is False and status is _Ehs.DEFINED and value.compare(_EHS_RECOVERY) >= 0  # type: ignore[union-attr]
            )
            if not recovering:
                self.recovery_start = None  # a breach or EHS below 0.40 restarts the continuous proof
                return None
            if self.recovery_start is None:
                self.recovery_start = event[0]
                return event[0] + _RECOVERY_NS
            if event[0] - self.recovery_start >= _RECOVERY_NS:  # at least 48 hours, met at exactly 48 (RD-4)
                self.recovery_start = None
                self._move(now, _State.WARNING, False, "recovery_ehs_at_least_0_40_for_48h")
            return None
        if disable is True:
            recent = [item for item in self.episodes if item > now[0] - _WINDOW_30D_NS]
            self.episodes.append(now[0])
            why = "drawdown_breach_family_b_5pct" if inputs.breach is True else "edge_health_score_below_0_30"
            if recent:  # the second distinct episode inside (t - 30 UTC days, t] enters QUARANTINE (RD-4, RD-5)
                self._move(now, _State.QUARANTINE, True, f"second_disable_episode_within_30d:{why}")
            else:
                self._move(now, _State.DISABLED, True, why)
            return None
        if status is not _Ehs.DEFINED:
            return None  # an undefined EHS makes no EHS transition
        target = _State.ACTIVE if value.compare(_EHS_ACTIVE) >= 0 else _State.WARNING  # type: ignore[union-attr]
        if self.state is _State.STATE_NOT_ESTABLISHED:
            self._move(now, target, False, "first_fully_defined_edge_health_score")
        elif target is not self.state:
            last = self.transitions[-1] if self.transitions else None
            if target is _State.ACTIVE and last is not None and (last.time_ns, last.phase, last.sequence) == now:
                return None  # RD-3: ACTIVE needs a later coordinate than the recovery to WARNING
            self._move(now, target, False, f"edge_health_score_{target.value.lower()}")
        return None


# --- the checks ----------------------------------------------------------------------------------------------------------


def _check(
    outcome: GovernedPaperOwnHistoryOutcome, observed: str, reason: str, covered: tuple[str, ...] = ()
) -> GovernedPaperOwnHistoryCheck:
    return GovernedPaperOwnHistoryCheck(outcome, observed, reason, covered)


def _ehs_checks(
    inputs: _Inputs, exclusive: bool
) -> tuple[GovernedPaperOwnHistoryCheck, GovernedPaperOwnHistoryCheck, GovernedPaperOwnHistoryCheck]:
    """NT-E01, NT-E04 and the SCALE-1 alpha_edge term from the EHS reading (completion bounds for a U1-only reading)."""

    status, value = inputs.ehs
    if status is _Ehs.DEFINED:
        below = value.compare(_EHS_DISABLE) < 0  # type: ignore[union-attr]
        e01 = _check(
            _Out.FAIL if below else _Out.PASS,
            "",
            "edge_health_score_below_0_30" if below else "edge_health_score_at_least_0_30",
        )
        if not exclusive:
            e04 = _check(_Out.BLOCKED, "", "asset_edge_universe_unproven")
        elif value.compare(_EHS_ASSET) > 0:  # type: ignore[union-attr]
            e04 = _check(_Out.PASS, "", "an_edge_with_edge_health_score_above_0_50")
        else:
            e04 = _check(_Out.FAIL, "", "no_edge_with_edge_health_score_above_0_50")
        if value.compare(_EHS_ACTIVE) >= 0:  # type: ignore[union-attr]
            alpha = _check(_Out.PASS, "", "alpha_edge_proven_1")
        else:
            alpha = _check(_Out.FAIL, "", "alpha_edge_proven_below_1")
        return e01, e04, alpha
    if status is _Ehs.U1_INSUFFICIENT_ONLY:
        best = _add((Fraction(1), value), (_W_SHARPE, _Surd(Fraction(1))))  # type: ignore[arg-type] - S_sharpe = 1
        # S_sharpe = 1 leaves EHS >= 0.30 (best >= 0.30 always), so no U1-insufficient reading is a proven NT-E01 FAIL
        e01 = _check(_Out.COVERED, "", "u1_insufficient_own_history_not_failing_under_every_completion", ("U1",))
        if not exclusive:
            e04 = _check(_Out.BLOCKED, "", "asset_edge_universe_unproven")
        elif best.compare(_EHS_ASSET) <= 0:
            e04 = _check(_Out.FAIL, "", "every_completion_leaves_edge_health_score_at_most_0_50")
        else:
            e04 = _check(_Out.COVERED, "", "u1_insufficient_own_history", ("U1",))
        if best.compare(_EHS_ACTIVE) < 0:
            alpha = _check(_Out.FAIL, "", "every_completion_leaves_alpha_edge_below_1")
        else:
            alpha = _check(_Out.COVERED, "", "u1_insufficient_own_history", ("U1",))
        return e01, e04, alpha
    why = "edge_health_score_undefined" if status is _Ehs.UNDEFINED else "edge_health_score_unproven"
    return _check(_Out.BLOCKED, "", why), _check(_Out.BLOCKED, "", why), _check(_Out.BLOCKED, "", why)


def _state_check(
    inputs: _Inputs, machine: _Machine
) -> tuple[GovernedPaperOwnHistoryState, str, GovernedPaperOwnHistoryCheck]:
    """NT-E02 from the state machine (FAIL first on a proven current disable condition)."""

    state = machine.state if machine.proven else _State.LIFECYCLE_UNPROVEN
    reason = (
        state.value.lower() if machine.proven else "disable_condition_not_yet_known_a_hidden_transition_is_possible"
    )
    disable = inputs.disable_condition()
    status, _ = inputs.ehs
    if disable is True:
        why = "drawdown_breach_family_b_5pct" if inputs.breach is True else "edge_health_score_below_0_30"
        return state, reason, _check(_Out.FAIL, state.value, f"disable_condition_proven:{why}")
    if state in (_State.QUARANTINE, _State.DISABLED):
        return state, reason, _check(_Out.FAIL, state.value, f"edge_state_{state.value.lower()}")
    if state in (_State.ACTIVE, _State.WARNING) and status is _Ehs.DEFINED:
        return state, reason, _check(_Out.PASS, state.value, f"edge_state_{state.value.lower()}")
    if state is _State.STATE_NOT_ESTABLISHED and status is _Ehs.U1_INSUFFICIENT_ONLY and inputs.breach is False:
        return state, reason, _check(_Out.COVERED, state.value, "state_not_established_u1_insufficient_only", ("U1",))
    return state, reason, _check(_Out.BLOCKED, state.value, f"edge_state_unproven:{reason}")


def _fill_checks(
    fr10: tuple[GovernedPaperOwnHistoryStatus, Fraction | None, Fraction, int, int],
    fr20: tuple[GovernedPaperOwnHistoryStatus, Fraction | None, Fraction, int, int],
) -> tuple[GovernedPaperOwnHistoryCheck, GovernedPaperOwnHistoryCheck, GovernedPaperOwnHistoryTruth]:
    """NT-X02 on FR_10 and the §1.5 fill leg on FR_20 (a completion bound proves FAIL only)."""

    status, value, total, known, _ = fr10
    if status is _St.DEFINED:
        failed = value < _NT_X02_FLOOR  # type: ignore[operator]
        x02 = _check(
            _Out.FAIL if failed else _Out.PASS,
            str(value),
            "last_10_fill_rate_below_0_50" if failed else "last_10_fill_rate_at_least_0_50",
        )
    elif status is _St.INSUFFICIENT and (total + _FR_10 - known) / _FR_10 < _NT_X02_FLOOR:
        x02 = _check(_Out.FAIL, "", "every_completion_leaves_the_last_10_fill_rate_below_0_50")
    elif status is _St.INSUFFICIENT:
        x02 = _check(_Out.COVERED, "", "u3_insufficient_own_history", ("U3",))
    else:
        x02 = _check(_Out.BLOCKED, "", "last_10_fill_rate_unproven")
    status, value, total, known, _ = fr20
    if status is _St.DEFINED and value <= _EXECUTION_FORBIDDEN_AT_MOST:  # type: ignore[operator]
        leg = _check(_Out.FAIL, str(value), "last_20_fill_rate_at_most_0_70_execution_impaired_or_halted")
        forbidden = _T.TRUE
    elif status is _St.INSUFFICIENT and (total + _FR_20 - known) / _FR_20 <= _EXECUTION_FORBIDDEN_AT_MOST:
        leg = _check(_Out.FAIL, "", "every_completion_leaves_the_last_20_fill_rate_at_most_0_70")
        forbidden = _T.TRUE
    else:
        # the latency and API-error legs are X-H1 (never covered), so the execution column is never proven allowed
        leg = _check(_Out.BLOCKED, "" if value is None else str(value), "execution_latency_and_api_legs_unproven_x_h1")
        forbidden = _T.UNKNOWN
    return x02, leg, forbidden


def _decay(inputs: _Inputs) -> tuple[GovernedPaperOwnHistoryTruth, GovernedPaperOwnHistoryCheck]:
    """DECAY_ALERT (Sharpe_30d < 0.5 x Sharpe_90d) and the SCALE-1 DE-WEIGHT term."""

    (status_30, sharpe_30), (status_90, sharpe_90) = inputs.sharpe_30, inputs.sharpe_90
    if status_30 is _St.DEFINED and status_90 is _St.DEFINED:
        # 0.5 Sharpe_90 - Sharpe_30 > 0, both of the form mean x sqrt(365 / variance)
        sign = _sign_surd(
            Fraction(0),
            ((_DECAY_RATIO * sharpe_90.mean, sharpe_90.radicand), (-sharpe_30.mean, sharpe_30.radicand)),  # type: ignore[union-attr]
        )
        if sign > 0:
            return _T.TRUE, _check(_Out.FAIL, "DECAY_ALERT", "decay_alert_de_weight_halves_the_allocation")
        return _T.FALSE, _check(_Out.PASS, "", "no_decay_alert")
    covered = tuple(reading for reading, status in (("U1", status_30), ("U2", status_90)) if status is _St.INSUFFICIENT)
    defined_or_covered = all(status in (_St.DEFINED, _St.INSUFFICIENT) for status in (status_30, status_90))
    if covered and defined_or_covered:
        return _T.UNKNOWN, _check(_Out.COVERED, "", "decay_alert_undefined_for_insufficient_own_history", covered)
    return _T.UNKNOWN, _check(_Out.BLOCKED, "", "decay_alert_unproven")


def _allocation(
    inputs: _Inputs, forbidden: GovernedPaperOwnHistoryTruth, sleeve: str, candidates: tuple[str, ...]
) -> tuple[GovernedPaperAllocationEligibility, str | None, str]:
    """The genesis sleeve's §4.1 eligibility and weight at one rebalance, on decided readings only."""

    status, value = inputs.ehs
    member = None if status is not _Ehs.DEFINED else value.compare(_EHS_DISABLE) >= 0  # type: ignore[union-attr]
    rows = []
    for edge_id in candidates:
        if edge_id == sleeve:
            rows.append(
                GovernedPaperAllocationDecidedCandidate(
                    edge_id=edge_id,
                    activation=GovernedPaperAllocationActivation.FAIL
                    if forbidden is _T.TRUE
                    else GovernedPaperAllocationActivation.UNKNOWN,
                    ehs_at_least_member=member,
                    sharpe_30d_defined=inputs.sharpe_30[0] is _St.DEFINED,
                    reading_reason="own_history_decided_readings",
                )
            )
        else:  # another declared sleeve: no own history of it exists here
            rows.append(
                GovernedPaperAllocationDecidedCandidate(
                    edge_id=edge_id,
                    activation=GovernedPaperAllocationActivation.UNKNOWN,
                    ehs_at_least_member=None,
                    sharpe_30d_defined=False,
                    reading_reason="no_own_history_of_this_sleeve",
                )
            )
    result = derive_governed_paper_allocation_decided(tuple(rows))
    entry = next(item for item in result.weights if item.edge_id == sleeve)
    reason = f"{result.status.value.lower()}:{entry.reason}"
    return entry.eligibility, entry.weight, reason


# --- the public derivation ----------------------------------------------------------------------------------------------


def _cut(key: _Coordinate) -> int:
    """The instant from which a decision or a fill reads an event at ``key``: its own instant before the DECISION phase,
    the next nanosecond from it on (a decision of the instant precedes the FILL-phase event)."""

    return key[0] if key[1] < _DECISION else key[0] + 1


def derive_governed_paper_own_history_evidence(  # noqa: C901, PLR0912, PLR0913, PLR0915 - one linear derivation
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    context: GovernedPaperOwnHistoryContext,
) -> GovernedPaperOwnHistoryEvidence:
    """The own-history evidence of one governed evaluation (see the module docstring). Pure.

    ``result`` and ``expected_result_digest`` are the replay authority of ``outcome``, whose schedule must be a schedule
    v10; the one engine is re-run under it and must reproduce ``outcome`` exactly. ``run`` and ``dataset`` must be the
    genesis's own READY + PASS run and its archive. Malformed or foreign input raises ``GovernedPaperOwnHistoryError``.
    """

    if type(authority) is not GovernedPaperGenesisAuthority:
        raise _fail("inputs_malformed")
    return _derive(
        lineage=_lineage_of(authority),
        run=run,
        dataset=dataset,
        result=result,
        expected_result_digest=expected_result_digest,
        outcome=outcome,
        context=context,
    )


def _derive(  # noqa: C901, PLR0912, PLR0913, PLR0915 - one linear derivation
    *,
    lineage: _Lineage,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    context: GovernedPaperOwnHistoryContext,
) -> GovernedPaperOwnHistoryEvidence:
    """The derivation over the lineage facts of a verified genesis authority (``_lineage_of``)."""

    if type(run) is not HistoricalDecisionRun:
        raise _fail("inputs_malformed")
    if type(dataset) is not HistoricalPitDataset or type(result) is not HistoricalExecutionEconomicsResult:
        raise _fail("inputs_malformed")
    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome or type(expected_result_digest) is not str:
        raise _fail("inputs_malformed")
    context = canonical_governed_paper_own_history_context(context)
    table = governed_paper_own_history_active_table()
    if run.status is not EdgeEvidenceStatus.READY or run.gate_verdict is not EdgeGateVerdict.PASS:
        raise _fail("decision_run_not_ready")
    if (
        run.dataset_digest != dataset.dataset_digest
        or run.executable_binding_digest != lineage.executable_binding_digest
        or run.instrument != lineage.instrument
        or run.evaluation_start_ns != lineage.start_ns
        or dataset.source_manifest_digest != lineage.source_manifest_digest
        or result.run_digest != run.run_digest
        or result.economics_policy_digest != lineage.economics_policy_digest
        or outcome.evaluation_end_ns != run.evaluation_end_ns
    ):
        raise _fail("inputs_not_of_the_genesis")
    if outcome.schedule.schema_version != HISTORICAL_EXECUTION_OWN_HISTORY_ADMISSION_SCHEDULE_SCHEMA_VERSION:
        raise _fail("own_history_needs_the_schedule_v10")
    try:  # the replay authority: the one engine, re-run under the outcome's own schedule
        derivation = simulate_historical_execution_governed_paper_derivation(
            result, expected_result_digest=expected_result_digest, schedule=outcome.schedule
        )
    except HistoricalExecutionEconomicsError as exc:
        raise _fail("replay_authority_not_authentic") from exc
    if derivation.outcome != outcome or outcome.simulated is not True:
        raise _fail("outcome_not_reproduced_by_the_replay_authority")
    required = (run.funding_series_id, result.mark_series_id, result.order_book_series_id)
    admitted, refusals = [], []
    for claim in context.coverages:
        why = _admission(
            table,
            claim,
            source_manifest_digest=dataset.source_manifest_digest,
            instrument=lineage.instrument,
            required=required,
        )
        if why:
            refusals.append(f"{claim.coverage_digest}:{why}")
        else:
            admitted.append(claim)
    facts = _Derivation(
        lineage=lineage,
        run=run,
        dataset=dataset,
        result=result,
        derivation=derivation,
        coverage=_Coverage(admitted, required),
    )
    start, horizon = facts.start, facts.horizon

    # every coordinate at which an input can change, a window can expire or a reading is taken
    coordinates: set[_Coordinate] = {(start, _PRE, -1)}
    for key, known in zip(facts.path_keys, facts.path_known, strict=True):
        coordinates.add(key)
        if known > key[0]:
            coordinates.add((known, _PRE, -1))
    for key in facts.eval_keys:
        coordinates.add(key)
        coordinates.add((key[0] + _WINDOW_30D_NS, _PRE, -1))
    for key, known in zip(facts.trade_keys, facts.trade_known, strict=True):
        coordinates.add(key)
        coordinates.update({(known, _PRE, -1), (key[0] + _WINDOW_30D_NS, _PRE, -1)})
    for item in facts.subs:
        coordinates.add(item.key)
        if item.resolved_key is not None:
            coordinates.add(item.resolved_key)
        elif item.window_close is not None:
            coordinates.add((item.window_close, _PRE, -1))
            learned = facts.coverage.known_from(facts.book_series, item.window_open, item.window_close)  # type: ignore[arg-type]
            if learned is not None:
                coordinates.add((max(learned, item.window_close), _PRE, -1))
    for instant in (*facts.coverage.publications, *facts.coverage.ends):
        coordinates.add((instant, _PRE, -1))
    midnights = set(range(-(-start // _DAY_NS) * _DAY_NS, horizon, _DAY_NS))
    coordinates.update((instant, _PRE, -1) for instant in midnights)
    entries = {
        item.decision_sequence: item for item in facts.decisions if item.resulting_direction in ("LONG", "SHORT")
    }
    decision_keys = {(item.decision_time_ns, _DECISION, -1): item for item in entries.values()}
    coordinates.update(decision_keys)
    heap = [key for key in coordinates if start <= key[0] < horizon]
    heapq.heapify(heap)

    machine = _Machine()
    rebalance: tuple[int, GovernedPaperAllocationEligibility, str | None, str] | None = None
    ends: dict[str, _Coordinate | None] = dict.fromkeys(GOVERNED_PAPER_OWN_HISTORY_READING_IDS)
    readings: list[GovernedPaperOwnHistoryReading] = []
    seen: set[_Coordinate] = set()
    while heap:
        key = heapq.heappop(heap)
        if key in seen:
            continue
        seen.add(key)
        inputs = facts.inputs(key)
        before = len(machine.transitions)
        for deadline in machine.advance(facts, key, inputs):
            if deadline < horizon:
                heapq.heappush(heap, (deadline, _PRE, -1))
        fr10 = facts.fill_rate(key, _FR_10, inputs.complete)
        fr20 = facts.fill_rate(key, _FR_20, inputs.complete)
        resolved = facts.resolved_count(key)
        # C-6: a covered reading's coverage ends at the first coordinate its window holds enough own observations
        for reading_id, filled in (
            ("U1", inputs.completed_days >= _SHARPE_30D_DAYS and inputs.sharpe_30[0] is not _St.UNPROVEN),
            ("U2", inputs.completed_days >= _SHARPE_90D_DAYS and inputs.sharpe_90[0] is not _St.UNPROVEN),
            ("U3", resolved >= _FR_10),
            ("U4", resolved >= _FR_20),
        ):
            if filled and ends[reading_id] is None:
                ends[reading_id] = key
        x02, leg, forbidden = _fill_checks(fr10, fr20)
        transitioned = len(machine.transitions) > before
        if (key[1] == _PRE and key[2] == -1 and key[0] in midnights) or (transitioned and machine.proven):
            rebalance = (key[0], *_allocation(inputs, forbidden, facts.sleeve, facts.candidates))
        decision = decision_keys.get(key)
        if decision is None:
            continue
        e01, e04, alpha = _ehs_checks(inputs, facts.exclusive)
        state, state_reason, e02 = _state_check(inputs, machine)
        decay, de_weight = _decay(inputs)
        hit_status, s_hit, trades, _ = facts.hit(key, inputs.complete, key[0])
        alert = _T.UNKNOWN
        if inputs.complete and key[0] - _WINDOW_90D_NS >= start:
            short = facts.hit(key, True, key[0], _WINDOW_30D_NS)
            long = facts.hit(key, True, key[0], _WINDOW_90D_NS)
            if short[0] is _St.DEFINED and long[0] is _St.DEFINED and short[3] is not None and long[3] is not None:
                alert = _truth(short[3] < long[3] - _HIT_ALERT_GAP)
        drawdown_status, drawdown, lower, breach = inputs.drawdown
        ehs_status, ehs_value = inputs.ehs
        if ehs_status is _Ehs.DEFINED:
            comparisons = (
                _truth(ehs_value.compare(_EHS_DISABLE) >= 0),  # type: ignore[union-attr]
                _truth(ehs_value.compare(_EHS_ASSET) > 0),  # type: ignore[union-attr]
                _truth(ehs_value.compare(_EHS_ACTIVE) >= 0),  # type: ignore[union-attr]
                _truth(ehs_value.compare(_EHS_BOOST) > 0),  # type: ignore[union-attr]
            )
        else:
            comparisons = (_T.UNKNOWN,) * 4
        if not machine.proven and rebalance is not None:
            eligibility, weight, allocation_reason = (
                GovernedPaperAllocationEligibility.UNKNOWN,
                None,
                "edge_state_transitions_since_the_rebalance_unproven",
            )
            rebalance_ns: int | None = rebalance[0]
        elif rebalance is None:
            eligibility, weight, allocation_reason, rebalance_ns = (
                GovernedPaperAllocationEligibility.UNKNOWN,
                None,
                "no_rebalance_at_or_before_the_instant",
                None,
            )
        else:
            rebalance_ns, eligibility, weight, allocation_reason = rebalance
        seed = GovernedPaperOwnHistoryReading(
            decision_sequence=decision.decision_sequence,
            decision_time_ns=decision.decision_time_ns,
            complete=inputs.complete,
            sharpe_30d_status=inputs.sharpe_30[0],
            completed_days=inputs.completed_days,
            sharpe_90d_status=inputs.sharpe_90[0],
            decay_alert=decay,
            fr_10_status=fr10[0],
            fr_10=_rational(fr10[1]),
            fr_20_status=fr20[0],
            fr_20=_rational(fr20[1]),
            resolved_observations=resolved,
            unresolved_submissions=fr20[4],
            hit_rate_status=hit_status,
            s_hitrate=_rational(s_hit),
            trade_count=trades,
            hit_rate_alert=alert,
            drawdown_status=drawdown_status,
            drawdown=_rational(drawdown),
            drawdown_lower_bound=_rational(lower),
            s_drawdown=None if drawdown is None else str(max(Fraction(0), 1 - drawdown / _DRAWDOWN_MAX_FAMILY_B)),
            drawdown_breach=_truth(breach),
            stability_status=inputs.stability[0],
            signal_count=inputs.stability[2],
            ehs_status=ehs_status,
            ehs_at_least_0_30=comparisons[0],
            ehs_above_0_50=comparisons[1],
            ehs_at_least_0_70=comparisons[2],
            ehs_above_0_80=comparisons[3],
            state=state,
            state_reason=state_reason,
            disable_condition=_truth(inputs.disable_condition()),
            coverage_ended=tuple(
                reading_id
                for reading_id in GOVERNED_PAPER_OWN_HISTORY_READING_IDS
                if ends[reading_id] is not None and ends[reading_id] <= key  # type: ignore[operator]
            ),
            execution_forbidden=forbidden,
            nt_e01=e01,
            nt_e02=e02,
            nt_e04=e04,
            nt_x02=x02,
            fill_leg=leg,
            alpha_edge=alpha,
            de_weight=de_weight,
            allocation_rebalance_ns=rebalance_ns,
            allocation_eligibility=eligibility,
            allocation_weight=weight,
            allocation_reason=allocation_reason,
            reading_digest="",
        )
        readings.append(replace(seed, reading_digest=edge_payload_digest(_payload(seed), "reading_digest")))
    coverage_ends = tuple(
        GovernedPaperOwnHistoryCoverageEnd(reading_id, None, None, None, None)
        if ends[reading_id] is None
        else GovernedPaperOwnHistoryCoverageEnd(
            reading_id,
            ends[reading_id][0],
            ends[reading_id][1],
            ends[reading_id][2],
            _cut(ends[reading_id]),  # type: ignore[index,arg-type]
        )
        for reading_id in GOVERNED_PAPER_OWN_HISTORY_READING_IDS
    )
    readings.sort(key=lambda item: item.decision_sequence)
    seed = GovernedPaperOwnHistoryEvidence(
        schema_version=GOVERNED_PAPER_OWN_HISTORY_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_OWN_HISTORY_CONTRACT_ID,
        decision_ids=GOVERNED_PAPER_OWN_HISTORY_DECISION_IDS,
        genesis_id=lineage.genesis_id,
        genesis_digest=lineage.genesis_digest,
        instrument=lineage.instrument,
        run_digest=run.run_digest,
        dataset_digest=dataset.dataset_digest,
        economics_result_digest=result.result_digest,
        outcome_digest=outcome.outcome_digest,
        schedule_digest=outcome.schedule_digest,
        start_ns=start,
        horizon_ns=horizon,
        table_id=table.table_id,
        coverage_digests=tuple(item.coverage_digest for item in admitted),
        coverage_refusals=tuple(refusals),
        required_series=required,
        exclusive_attribution=facts.exclusive,
        signal_profile_registered=facts.profile_registered,
        submissions=tuple(item.record for item in facts.subs),
        boundaries=facts.boundaries,
        trades=facts.trades,
        signals=facts.signals,
        transitions=tuple(machine.transitions),  # type: ignore[arg-type]
        lifecycle_unproven_from_ns=machine.pending[0][0] if machine.pending and not machine.proven else None,
        lifecycle_reason="disable_condition_not_known_by_the_horizon" if machine.pending and not machine.proven else "",
        coverage_ends=coverage_ends,
        readings=tuple(readings),
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_payload(seed), _DIGEST_FIELD))


def governed_paper_own_history_evidence_to_dict(evidence: GovernedPaperOwnHistoryEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _payload(evidence)


def governed_paper_own_history_evidence_digest(evidence: GovernedPaperOwnHistoryEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_payload(evidence), _DIGEST_FIELD)


def governed_paper_own_history_reading_digest(reading: GovernedPaperOwnHistoryReading) -> str:
    """Recompute one reading's digest, excluding only ``reading_digest``."""

    return edge_payload_digest(_payload(reading), "reading_digest")


def governed_paper_own_history_reading(
    evidence: GovernedPaperOwnHistoryEvidence, decision_sequence: int
) -> GovernedPaperOwnHistoryReading:
    """The reading of one entry decision of the evidence."""

    if type(evidence) is not GovernedPaperOwnHistoryEvidence:
        raise _fail("evidence_malformed")
    for item in evidence.readings:
        if item.decision_sequence == decision_sequence:
            return item
    raise _fail("no_reading_of_the_decision")


def governed_paper_own_history_coverage_cuts(evidence: GovernedPaperOwnHistoryEvidence) -> dict[str, int | None]:
    """The cut instant of every covered reading U1-U4 (None: its coverage never ends by the horizon)."""

    if type(evidence) is not GovernedPaperOwnHistoryEvidence:
        raise _fail("evidence_malformed")
    return {item.reading_id: item.cut_ns for item in evidence.coverage_ends}


def governed_paper_own_history_prefix_digest(evidence: GovernedPaperOwnHistoryEvidence, *, before_ns: int) -> str:
    """The knowledge-stable content of the evidence strictly before ``before_ns`` (X1).

    Submissions issued before the instant (their resolution only where it precedes the instant), and the day boundaries,
    trades, evaluations, transitions, coverage ends and readings before it. The horizon's still-pending lifecycle
    conditions (``lifecycle_unproven_from_ns``) are excluded: a longer horizon may resolve them, while every reading
    before the instant already carries the state known at its own decision. A longer replay of the same lineage
    reproduces exactly this content.
    """

    if type(evidence) is not GovernedPaperOwnHistoryEvidence:
        raise _fail("evidence_malformed")
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("prefix_instant_invalid")
    submissions = []
    for item in evidence.submissions:
        if item.submitted_ns >= before_ns:
            continue
        row = {
            "order_kind": item.order_kind,
            "identity_digest": item.identity_digest,
            "native_sequence": item.native_sequence,
            "submitted_ns": item.submitted_ns,
            "submitted_phase": item.submitted_phase,
            "side": item.side,
            "exposure_increasing": item.exposure_increasing,
            "requested_quantity": item.requested_quantity,
        }
        if item.reached_book and item.resolved_ns is not None and item.resolved_ns < before_ns:
            row.update(
                filled_quantity=item.filled_quantity,
                resolved_ns=item.resolved_ns,
                resolved_phase=item.resolved_phase,
                resolved_sequence=item.resolved_sequence,
                reason=item.reason,
            )
        elif not item.reached_book and item.window_close_ns is not None and item.window_close_ns < before_ns:
            row.update(window_open_ns=item.window_open_ns, window_close_ns=item.window_close_ns)
        submissions.append(row)
    prefix = {
        "start_ns": evidence.start_ns,
        "genesis_digest": evidence.genesis_digest,
        "submissions": submissions,
        "boundaries": [_payload(item) for item in evidence.boundaries if item.boundary_ns < before_ns],
        "trades": [_payload(item) for item in evidence.trades if item.close_ns < before_ns],
        "signals": [_payload(item) for item in evidence.signals if item.evaluation_ns < before_ns],
        "transitions": [_payload(item) for item in evidence.transitions if item.time_ns < before_ns],
        "coverage_ends": [
            _payload(item) for item in evidence.coverage_ends if item.time_ns is not None and item.time_ns < before_ns
        ],
        "readings": [_payload(item) for item in evidence.readings if item.decision_time_ns < before_ns],
    }
    return _digest_of(prefix)


def verify_governed_paper_own_history_evidence(  # noqa: PLR0913 - the evidence and its authoritative inputs
    evidence: object,
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    context: GovernedPaperOwnHistoryContext,
) -> EdgeEvidenceVerification:
    """Re-prove a supplied evidence: its self-digest, and typed identity with the derivation over the same inputs under
    the active table. A forged, resealed or foreign evidence is never intact."""

    if type(evidence) is not GovernedPaperOwnHistoryEvidence:
        return EdgeEvidenceVerification(False, (f"{_PREFIX}:evidence_malformed",), "", "")
    recomputed = governed_paper_own_history_evidence_digest(evidence)
    codes: list[str] = []
    if recomputed != evidence.evidence_digest:
        codes.append(f"{_PREFIX}:evidence_digest_mismatch")
    try:
        rebuilt = derive_governed_paper_own_history_evidence(
            authority=authority,
            run=run,
            dataset=dataset,
            result=result,
            expected_result_digest=expected_result_digest,
            outcome=outcome,
            context=context,
        )
    except GovernedPaperOwnHistoryError as exc:
        codes.append(str(exc))
        rebuilt = None
    if rebuilt is not None and rebuilt != evidence:
        codes.append(f"{_PREFIX}:evidence_not_the_derivation")
    canonical = "" if codes else edge_canonical_json(_payload(evidence))
    return EdgeEvidenceVerification(not codes, tuple(codes), recomputed, canonical)


__all__ = [
    "GOVERNED_PAPER_OWN_HISTORY_CONTRACT_ID",
    "GOVERNED_PAPER_OWN_HISTORY_COVERAGE_SCHEMA",
    "GOVERNED_PAPER_OWN_HISTORY_DECISION_IDS",
    "GOVERNED_PAPER_OWN_HISTORY_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_OWN_HISTORY_HUMAN_CHANNEL",
    "GOVERNED_PAPER_OWN_HISTORY_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_OWN_HISTORY_PRODUCTION_TABLE",
    "GOVERNED_PAPER_OWN_HISTORY_READING_IDS",
    "GOVERNED_PAPER_OWN_HISTORY_TEST_CHANNEL",
    "GovernedPaperOwnHistoryBoundary",
    "GovernedPaperOwnHistoryCheck",
    "GovernedPaperOwnHistoryContext",
    "GovernedPaperOwnHistoryCoverage",
    "GovernedPaperOwnHistoryCoverageEnd",
    "GovernedPaperOwnHistoryEhsStatus",
    "GovernedPaperOwnHistoryError",
    "GovernedPaperOwnHistoryEvidence",
    "GovernedPaperOwnHistoryOutcome",
    "GovernedPaperOwnHistoryReading",
    "GovernedPaperOwnHistorySignal",
    "GovernedPaperOwnHistoryState",
    "GovernedPaperOwnHistoryStatus",
    "GovernedPaperOwnHistorySubmission",
    "GovernedPaperOwnHistoryTable",
    "GovernedPaperOwnHistoryTrade",
    "GovernedPaperOwnHistoryTransition",
    "GovernedPaperOwnHistoryTruth",
    "canonical_governed_paper_own_history_context",
    "derive_governed_paper_own_history_evidence",
    "governed_paper_own_history_active_table",
    "governed_paper_own_history_coverage_cuts",
    "governed_paper_own_history_coverage_digest",
    "governed_paper_own_history_evidence_digest",
    "governed_paper_own_history_evidence_to_dict",
    "governed_paper_own_history_prefix_digest",
    "governed_paper_own_history_reading",
    "governed_paper_own_history_reading_digest",
    "verify_governed_paper_own_history_evidence",
]
