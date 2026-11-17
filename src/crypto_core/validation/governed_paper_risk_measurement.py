"""Governed paper native risk measurement (S1_NATIVE_RISK_MEASUREMENT_CONSTRUCTION_V1): RECORD B, constructed.

Design authority: ``docs/crypto_core/s1_native_risk_measurement_doctrine_adoption_v1.md`` (the adopted RECORD B,
``S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3``, with HZB-1 in PRDV4 §1.27, the selections MC-8a, MC-10 and LS-A, the
approved deltas D-B1, D-B2 (its exactness rule only) and D-B3, and the approved values V1-V4), read with PRDV4 §1.17,
§1.18, §1.19, §1.21, §1.27, §1.29, §7.2 and §8.2. Paper-only, deterministic, point-in-time and fail-closed. It creates
no order, sizes nothing, executes no de-risk action and authorizes no entry; every value in its tests is synthetic.

Authority. A digest-bound risk policy fixes every RECORD B constant and the values V1-V4; its builder takes only an id,
the instrument and the bound MARK bar source (its declaration digest and its bar interval, a whole divisor of the UTC
day), so no other number can enter it. An approval binds one policy digest over exactly the approved construction
scope, and only an approval the active table admits is used: the PRODUCTION table admits none, so in production every
reading here is BLOCKED (C-21, BV); tests alone install a TEST-ONLY table for TEST_ONLY_SYNTHETIC approvals. A
HUMAN_GOVERNANCE approval would still need an M1-qualified archive, which no archive here is, so it is refused too.
Every input is re-proven (policy, approval, archive, dataset intact + READY + advancing, the dataset's own EF-3
manifest), none is trusted for its own digest, and every reading is derived, never accepted.

FCD-01 (NT_R03_OPEN_RISK_AT_STOP_V1, R-1..R-8). ``risk = |q| x sgn(q) x (m - x) + |q| x x x c`` with ``x`` the armed stop
while the fresh mark ``m`` is on its safe side, else ``m``, and ``c = (taker_fee_bps + slippage_floor_bps) / 10,000`` of
the bound economics policy; flat is 0 and gap risk is excluded (a non-claim). ``rho = risk / E``, a fraction of equity at
stop risk (R-8), never a notional. At a decision, an entry from flat reads R-4 (basis ``m(t)``, distance
``min(1.5 x ATR_4h(t), 1.5% x m(t))``, over the candidate NAV), and any other decision reports the open position (R-6)
over the exact publication-visible NAV, its armed stop re-derived exactly from the engine's own protection record (the
policy v2 milestone-0 stop; a DEC-9 tightening never loosens it). NT-R03 FAILs iff ``rho > 0.04`` (0.04 passes) and is
BLOCKED on an order in flight, no fresh mark, no armed stop, no ATR, no positive NAV or an unrepresentable value (R-7).
A refusal reaches entries only. The fill-time R-5 bound is the engine's schedule v7 (``historical_execution_economics``).

FCD-02 (CVAR99_WEIGHTED_HS_DAILY_V2, C-1..C-21, with CVAR99_MC_V1, MC-1..MC-12). The policy-bound MARK archive's daily
close is the close of the bar of the policy interval ending at a UTC midnight. At ``t`` the series is the 253 consecutive
daily closes ending with the latest one visible at ``t``, each visible at ``t``; that latest close must have closed at or
after ``t - V1``, else BLOCKED (``cvar_history_stale``; a missing or not-yet-visible close is
``cvar_history_insufficient``). ``r_a = c_d / c_{d-1} - 1`` over 252 days (``a = 0`` newest); a unit LONG holding loses
``-r_a`` and a unit SHORT ``+r_a`` (C-3 at ``|q| x m / E = 1``; every reading scales the unit value exactly by
``|q| x m / E``). ``w_a = lambda^a (1 - lambda) / (1 - lambda^252)``, ``lambda = 47/50``. ES and VaR follow C-5 exactly
(descending loss, ties by ascending age, ``tau = 1/100``); ``n_tail = k*``. When ``n_tail < 50`` (C-6) the Monte Carlo of
MC-1..MC-6 runs: 10,000 paths, ``u_i`` the first 8 bytes of ``SHA-256(seed || i)`` (8-byte big-endian ``i``), the age the
smallest ``a`` with ``u_i < ceil(C_a x 2^64)``, the top 100 path losses (ties by path index) giving VaR_MC (the 100th) and
CVaR_MC (their exact mean); then ``CVaR99* = max(ES, CVaR_MC)`` (MC-8a, the human's choice; MC-8b is never read), else
``CVaR99* = ES`` (C-8). The seed (MC-3 with D-B3) is the SHA-256 of the canonical JSON of the method id
``CVAR99_MC_V1``, the risk-policy digest, the source declaration digest, the interval, the series end (the UTC midnight
of its latest close) and the 253 daily-close bar digests oldest first; the whole-archive digest is never read, and the
seed is independent of holdings, decision and side. MC-10: the counter-based sequence derives from verified inputs only.

* NT-R05 (C-9), at a decision on the decision's holdings over its denominator (an entry: the candidate over the candidate
  NAV; any other decision: the current position over the NAV): FAIL iff ``CVaR99* >= 0.05``, PASS below with every input
  proven, else BLOCKED. The fill-time C-10 bound is the engine's schedule v7, from the bounds ``governed_paper_risk_fill_
  bounds`` derives: one window per span of constant readability, with the exact unit CVaR99* of each side.
* S3 (C-11) on the current holdings over the NAV: ``min(1, max(0, CVaR99* / 0.05))``; unmeasured without a reading or a
  positive NAV (C-20). HZ-CVAR (C-12 under HZB-1): the INTRADAY horizon limit is 40% of the 5%-of-NAV daily budget, 2% of
  NAV; FAIL iff ``CVaR99* >= 0.02`` on the decision's holdings, PASS strictly below. EDGE-CVAR (C-13) and MARGINAL-CVAR
  (C-14) stay BLOCKED: FCD-17 (K_max, external ADV) and H^(e) are pending. STRESS-HV (C-15): ``1.5 x CVaR99*``, FAIL at or
  above 0.08. STRESS-CORR (C-16): PROVEN_NOT_APPLICABLE on one instrument. STRESS-LIQ (C-17 with LS-A): the fresh
  depth-50 tip at the decision with every quantity x 1/5 truncated on the quantity grid (the LOW_LIQUIDITY transform),
  the whole holding as one close-only order under the bound fill model; ``CVaR99* + exit cost / E`` FAILs at or above 0.08
  and when that order cannot fill the whole holding. The §1.18 de-risk duties (C-18) are recorded as
  BLOCKED_UNREPRESENTABLE obligations, never executed; hourly monitoring between decisions is unmeasured (C-19).

FCD-03 (LIQ_COMPOSITE_OBS_V3, L-1..L-10, with D-B1 and the D-B2 exactness rule). Observations sit at the UTC-aligned
multiples of V3 = 300 s. The observation at ``s`` reads the latest depth-50 tip by native event time among the tips
visible at or before ``s`` whose event time is at least ``s - 10 s`` (a tip visible after ``s`` never enters it), with
ask above bid and ``mid = (bid + ask) / 2``. ``depth_raw`` is the lesser of the quote notional of the bid levels at or
above ``mid x (1 - 0.0005)`` and of the ask levels at or below ``mid x (1 + 0.0005)``; a side's sum is exact only when its
50th level lies strictly beyond the band edge, and ``depth_raw`` is defined only when the minimum is attained on an exact
side (both exact, or one exact and the other's lower bound at least it); otherwise the observation is UNKNOWN. No
alternative depth definition exists here (it is PENDING_HUMAN_DECISION). ``spread_raw = (ask - bid) / mid``.
``arrival_raw`` counts the distinct native trade ids with event time in ``[s - 300 s, s)``, proven complete by one
contiguous run of the DECLARED contiguous-id profile from a visible trade strictly before ``s - 300 s`` to one at or after
``s`` (NT-D05's proof); its knowledge instant ``kappa`` is the visibility of that bounding trade, read as the latest
visibility of the proving chain so that no count is ever known before every trade it counts. LIQ(s_i) needs exactly the
8,640 consecutive members ``s_i - k x 300 s`` (``k = 1..8,640``), each valid: no instant is skipped, substituted,
interpolated, backfilled or carried forward. The depth and arrival scores are ``(#{y < x} + #{y = x} / 2) / 8,640``, the
spread score ``(#{y > x} + #{y = x} / 2) / 8,640``, ``LIQ = 0.4 depth + 0.3 spread + 0.3 arrival``, exact; CRISIS iff
``LIQ < 0.15``, NON-CRISIS iff ``LIQ >= 0.15``, else UNKNOWN; the knowledge instant ``K_i = max(kappa_i, ..., kappa_{i-
8640})``. A late observation counts only from its knowledge instant, and nothing is ever revised (L-9).

* NT-M01 (L-6) at ``t``, over the observations known at ``t``: PASS iff a valid NON-CRISIS observation ``s_nc`` has ``t -
  s_nc <= 1,800 s``; FAIL iff the latest known observation ``s_l`` is valid CRISIS, ``t - s_l <= V2`` and it closes a run
  of known valid CRISIS observations spanning strictly more than 1,800 s; BLOCKED otherwise (never both).
* T8 (L-7, a standard §1.19 trigger, lower bound only): from ``max(K_a, ..., K_b)`` of a run spanning strictly more than
  1,800 s, extended by each later member known valid CRISIS, ending at the earlier of ``K_{k+1}`` (the next member known
  valid NON-CRISIS) and ``s_{k+1} + V4`` (the next member not known valid by then); a late member restarts it at its
  knowledge instant; a lapse is never backfilled and records that the proof ended, never that CRISIS ended.
* S6 (L-8): ``1 - LIQ(s_l)`` only when ``s_l`` is valid and ``t - s_l <= V2``; otherwise unmeasured.

FCD-10 (NT_X03_AND_OB_SPREAD_V3, X-1..X-7 with D-B1). ``s(t)`` is the relative spread of the latest depth-50 tip visible at
``t`` with event time in ``[t - 10 s, t]`` and ask above bid. The baseline is exactly the 8,640 grid instants ``g_1`` (the
latest UTC-aligned 300 s instant strictly before ``t``) to ``g_8640``, each with a valid tip as of its own instant
(visibility at or before ``g_k``); ``M = (x_(4320) + x_(4321)) / 2`` exactly. NT-X03 (§1.21) FAILs iff ``s > 3M``;
OB-SPREAD (§7.2) FAILs iff ``s >= 3M``; both are BLOCKED without a fresh tip, on a crossed or locked tip and on any
missing, invalid or not-yet-visible baseline member. The Tier II alignment of X-7 is not read.

FCD-08 (HZ_TURNOVER_INTRADAY_V1, T-1..T-6). A trade is one excursion of the governed re-run, counted once at its first
entry fill: partial opening fills are one trade, and exits, reductions, protective attempts and children never count.
``N(t)`` counts the trades whose first entry fill falls in ``[UTC day start(t), t)``; an order in flight at ``t`` may be
one more (none is an exposure-increasing intent on the governed path, which is never assumed), so T-4 FAILs iff
``N(t) + 1 > 20``, PASSes iff ``N(t) + 1 <= 20`` even counting the order in flight, and is otherwise BLOCKED; without the
governed trade ledger it is BLOCKED. HZ-LIMITS PASSes only when both 8% shares hold and T-4 PASSes (T-5).

Exact arithmetic (``int`` and ``Fraction``; no float, no ``decimal`` context), and no IO, clock, randomness, network or
environment; the memo is exact over re-proven digests.
"""

from __future__ import annotations

import bisect
import hashlib
from collections import Counter, OrderedDict
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.validation.authenticated_pit_ingress import (
    TRADE_PRICE_VALUE_NAME,
    TRADE_QUANTITY_VALUE_NAME,
    TRADE_RUN_FIRST_ID_VALUE_NAME,
)
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourceSeriesRecord,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.governed_paper_regime_state import (
    GovernedPaperRegimeError,
    governed_paper_order_book_levels,
    governed_paper_order_book_series,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_CVAR_BUDGET,
    HISTORICAL_EXECUTION_OPEN_RISK_CAP,
    HistoricalExecutionCvarBound,
    HistoricalExecutionDecisionExactValues,
    HistoricalExecutionDecisionPortfolioSnapshot,
    HistoricalExecutionExcursionProtection,
    HistoricalExecutionGovernedPaperOutcome,
    historical_execution_close_only_exit_quote,
    historical_execution_risk_rational_text,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionEconomicsPolicy,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    historical_ohlc_wilder_atr,
    verify_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    verify_historical_pit_dataset,
)
from crypto_core.validation.historical_position_management_policy import (
    INITIAL_STOP_FRACTION,
    STOP_ATR_MULTIPLE,
    HistoricalPositionManagementPolicy,
    historical_position_management_initial_stop_fraction,
)

GOVERNED_PAPER_RISK_CONTRACT_ID = "S1_NATIVE_RISK_MEASUREMENT_CONSTRUCTION_V1"
GOVERNED_PAPER_RISK_DECISION_ID = "S1_NATIVE_RISK_MEASUREMENT_METHOD_DECISION_V3"
GOVERNED_PAPER_RISK_POLICY_SCHEMA = "governed-paper-risk-policy.v1"
GOVERNED_PAPER_RISK_APPROVAL_SCHEMA = "governed-paper-risk-approval.v1"
GOVERNED_PAPER_RISK_EVIDENCE_SCHEMA = "governed-paper-risk-evidence.v1"
# The human-approved RECORD B construction scope (adoption document section 1.2 and 1.1.2).
GOVERNED_PAPER_RISK_APPROVED_ITEMS: tuple[str, ...] = (
    "B1",
    "B2",
    "B2-H:HZB-1",
    "B2-L:LS-A",
    "B3",
    "B4",
    "B5",
    "BV:V1",
    "BV:V2",
    "BV:V3",
    "BV:V4",
    "MC-8a",
    "MC-10",
    "D-B1",
    "D-B2:exactness_rule",
    "D-B3",
)
# Never read, defaulted or selected here (adoption document section 13).
GOVERNED_PAPER_RISK_PENDING_ITEMS: tuple[str, ...] = (
    "D-A1",
    "D-B2:alternative_depth_definition",
    "D-B4",
    "D-B5",
    "FCD-17:K_max_and_external_ADV",
    "H(e)",
    "MONITORING_CADENCE",
    "FCD-05",
    "FCD-13",
    "FCD-14",
    "HD-07",
    "M1",
    "D1",
    "C1-C9",
    "DEC-1",
    "RISK_POLICY_PRODUCTION_APPROVAL",
)
# The risk checks of one decision, in the order the entry gate appends or reads them.
GOVERNED_PAPER_RISK_CHECK_IDS: tuple[str, ...] = (
    "NT-R03",
    "NT-R05",
    "NT-M01",
    "NT-X03",
    "HZ-TURNOVER",
    "HZ-CVAR",
    "EDGE-CVAR",
    "MARGINAL-CVAR",
    "STRESS-HV",
    "STRESS-CORR",
    "STRESS-LIQ",
    "OB-SPREAD",
)

_PREFIX = "governed_paper_risk_measurement"
_NS = 1_000_000_000
_DAY_NS = 86_400 * _NS
_TWO_64 = 1 << 64
_INFINITY = 1 << 80  # an instant no reading reaches

# PRDV4 doctrine values and the RECORD B methodology constants: published or human-approved, never governed parameters.
_OPEN_RISK_METHOD = "NT_R03_OPEN_RISK_AT_STOP_V1"
_CVAR_METHOD = "CVAR99_WEIGHTED_HS_DAILY_V2"
_MC_METHOD = "CVAR99_MC_V1"
_MC_SELECTION = "MC-8a:max_of_es_and_cvar_mc"
_HORIZON_READING = "HZB-1"
_STRESS_LIQ_METHOD = "LS-A"
_LIQUIDITY_METHOD = "LIQ_COMPOSITE_OBS_V3"
_SPREAD_METHOD = "NT_X03_AND_OB_SPREAD_V3"
_TURNOVER_METHOD = "HZ_TURNOVER_INTRADAY_V1"
_RHO_CAP = HISTORICAL_EXECUTION_OPEN_RISK_CAP  # R-7: rho strictly above 0.04 fails (§1.21 NT-R03, §8.2)
_CVAR_BUDGET = HISTORICAL_EXECUTION_CVAR_BUDGET  # C-9: CVaR99* at or above 0.05 fails (§1.21 NT-R05, §1.18)
# HZB-1: each horizon's §1.18 CVaR99 limit is its §1.27 Risk Budget share of the 5%-of-NAV daily budget (arithmetic on
# doctrine, not a parameter): MICRO 1%, INTRADAY 2%, SWING 2% of NAV. S1 is an INTRADAY edge (CL2-9).
GOVERNED_PAPER_RISK_HORIZON_SHARES: tuple[tuple[str, Fraction], ...] = (
    ("MICRO", Fraction(20, 100)),
    ("INTRADAY", Fraction(40, 100)),
    ("SWING", Fraction(40, 100)),
)
_HORIZON_SHARE = dict(GOVERNED_PAPER_RISK_HORIZON_SHARES)["INTRADAY"]
_HZ_CVAR_LIMIT = _HORIZON_SHARE * _CVAR_BUDGET  # HZB-1: 2% of NAV per day for INTRADAY
_STRESS_LIMIT = Fraction(8, 100)  # C-15, LS-A: a stress CVaR99 at or above 8% of NAV fails (§1.18)
_STRESS_HV_MULTIPLE = Fraction(3, 2)  # C-15: returns scaled by 1.5 (§1.18)
_STRESS_DEPTH = Fraction(1, 5)  # LS-A: depth x 0.2 (§1.18)
_DECAY = Fraction(47, 50)  # C-4: lambda (§1.18 RiskMetrics decay)
_CLOSES = 253  # C-1
_SCENARIOS = 252  # C-2
_TAIL = Fraction(1, 100)  # C-5: tau
_MIN_TAIL = 50  # C-6: the analytical estimate is unreliable below 50 tail observations (§1.18)
_PATHS = 10_000  # MC-2
_TOP = 100  # MC-6
_V1 = 172_800 * _NS  # MAX_DAILY_BAR_AGE
_V2 = 600 * _NS  # delta_stale
_V3 = 300 * _NS  # delta_obs, the observation grid
_V4 = 300 * _NS  # Lambda, the T8 lapse
_BASELINE = 8_640  # L-3, X-2: 30 days of 300 s instants
_MEDIAN = (4_320, 4_321)  # X-3: the 1-based ranks of the exact median of 8,640 values
_TIP_FRESHNESS = 10 * _NS  # L-2, X-1: CL1-10 / NT-D02
_BAND = Fraction(5, 10_000)  # L-2: +-5 bps of the mid
# 1 / 0.0005: a price p is inside the band iff 2 x 2,000 x p lies within (2,000 -+ 1) x (bid + ask), in integers.
_BAND_EDGE = _BAND.denominator // _BAND.numerator
_ARRIVAL = 300 * _NS  # L-2: [s - 300 s, s)
_SUSTAIN = 1_800 * _NS  # L-6, L-7: strictly more than 30 minutes
_RUN = _SUSTAIN // _V3 + 2  # 8 consecutive members span 2,100 s > 1,800 s; 7 span exactly 1,800 s
_LIQ_WEIGHTS = (Fraction(2, 5), Fraction(3, 10), Fraction(3, 10))  # L-4: depth, spread, arrival (§1.17)
_LIQ_CRISIS = Fraction(15, 100)  # L-4: CRISIS iff LIQ < 0.15 (§1.17)
_SPREAD_MULTIPLE = 3  # X-4, X-5: 3 x the 30-day median (§1.21, §7.2)
_TURNOVER_CAP = 20  # T-4: INTRADAY max turnover per day (§1.27)
_CLASS_MARGIN = 24  # grid steps before the start whose class can still bind a reading inside the evaluation
_MEMO_SIZE = 8

_CRISIS = "CRISIS"
_NON_CRISIS = "NON_CRISIS"
_UNKNOWN = "UNKNOWN"


class GovernedPaperRiskError(EdgeArtifactError):
    """Malformed, foreign or non-authentic input: no risk reading is ever represented over it."""


class GovernedPaperRiskApprovalKind(str, Enum):
    """HUMAN_GOVERNANCE still needs a separate production authorization; TEST_ONLY_SYNTHETIC exists for tests only."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperRiskStatus(str, Enum):
    """The status of one risk check reading (the gate maps BLOCKED to its BLOCKED_ON_MISSING_INPUT)."""

    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"


@dataclass(frozen=True)
class GovernedPaperRiskPolicy:
    """The governed risk policy v1: every RECORD B constant and the values V1-V4, bound to one MARK bar source."""

    schema_version: str
    policy_id: str
    instrument: str
    mark_source_digest: str
    mark_interval_ns: int
    mark_price_semantics: str
    decision_id: str
    approved_items: tuple[str, ...]
    pending_items: tuple[str, ...]
    open_risk_method_id: str
    open_risk_cap: str
    stop_atr_multiple: str
    initial_stop_fraction: str
    cvar_method_id: str
    cvar_mc_method_id: str
    cvar_mc_selection: str
    cvar_budget: str
    cvar_closes: int
    cvar_scenarios: int
    cvar_decay: str
    cvar_tail_probability: str
    cvar_min_tail_count: int
    cvar_mc_paths: int
    cvar_mc_top: int
    max_daily_bar_age_ns: int
    horizon_reading_id: str
    horizon_id: str
    horizon_budget_share: str
    horizon_cvar_limit: str
    stress_limit: str
    stress_hv_multiple: str
    stress_liq_method_id: str
    stress_liq_depth_factor: str
    liquidity_method_id: str
    observation_grid_ns: int
    liquidity_baseline_members: int
    liquidity_band: str
    tip_freshness_ns: int
    arrival_window_ns: int
    liquidity_weights: tuple[str, ...]
    liquidity_crisis_bound: str
    liquidity_sustain_ns: int
    liquidity_proof_age_ns: int
    t8_lapse_ns: int
    spread_method_id: str
    spread_multiple: int
    turnover_method_id: str
    turnover_cap: int
    policy_digest: str
    paper_only: bool = True
    calibrated: bool = False
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperRiskApproval:
    """One approval of a risk policy digest; its approved items are exactly the human construction scope."""

    schema_version: str
    approval_id: str
    approval_kind: GovernedPaperRiskApprovalKind
    policy_digest: str
    approved_items: tuple[str, ...]
    approver_reference: str
    approval_digest: str
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperRiskApprovalTable:
    """Which approvals may be used.

    ``production`` admits a HUMAN_GOVERNANCE approval of a listed policy digest only. ``test_only`` admits only
    TEST_ONLY_SYNTHETIC approvals and lists no digest.
    """

    table_id: str
    admitted_kind: GovernedPaperRiskApprovalKind
    admitted_policy_digests: tuple[str, ...]


# No separate human authorization lists any risk-policy digest for production use, so this table refuses every approval.
GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE = GovernedPaperRiskApprovalTable(
    table_id="production",
    admitted_kind=GovernedPaperRiskApprovalKind.HUMAN_GOVERNANCE,
    admitted_policy_digests=(),
)
_APPROVAL_TABLE = GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperRiskContext:
    """The risk context of one governed evaluation, supplied by the day seal from verified lineage inputs: the policy,
    its approval and the policy's MARK bar archive known at the seal. Every reading is derived from it, never accepted."""

    policy: GovernedPaperRiskPolicy
    approval: GovernedPaperRiskApproval
    archive: HistoricalOhlcBarArchive


@dataclass(frozen=True)
class GovernedPaperRiskCvarEstimate:
    """One exact CVaR99* estimate of a 252-scenario loss vector (in memory: never serialized)."""

    expected_shortfall: Fraction
    value_at_risk: Fraction
    tail_count: int
    monte_carlo_used: bool
    monte_carlo_var: Fraction | None
    monte_carlo_cvar: Fraction | None
    cvar: Fraction


@dataclass(frozen=True)
class GovernedPaperRiskCvarDay:
    """The unit CVaR99* of the series ending at one daily close (``series_end_ns``, a UTC midnight), per side.

    ``long_cvar`` and ``short_cvar`` are exact canonical rational texts, None with ``reason`` when unrepresentable.
    ``closes_digest`` digests the 253 daily-close bar digests oldest first and ``seed`` is the MC-3 seed (hex).
    """

    series_end_ns: int
    reason: str
    closes_digest: str
    seed: str
    long_cvar: str | None
    long_tail_count: int
    long_monte_carlo_used: bool
    short_cvar: str | None
    short_tail_count: int
    short_monte_carlo_used: bool


@dataclass(frozen=True)
class GovernedPaperRiskCvarSegment:
    """One span ``[start_ns, end_ns)`` of constant C-1 readability: the series end it reads, or why none is readable."""

    start_ns: int
    end_ns: int
    series_end_ns: int | None
    reason: str


@dataclass(frozen=True)
class GovernedPaperRiskObservation:
    """One L-2 observation at grid index ``index`` (``s = index x 300 s``): valid exactly when ``reason`` is empty.

    ``depth`` is the exact quote notional in units of 10^-36, ``spread`` the exact relative spread and ``arrival`` the
    trade count; ``knowledge_ns`` is ``kappa``. ``spread`` is also kept for an invalid observation whose tip has ask above
    bid: it is the X-2 baseline value of its grid instant.
    """

    index: int
    reason: str
    depth: int | None
    spread: Fraction | None
    arrival: int | None
    knowledge_ns: int | None


@dataclass(frozen=True)
class GovernedPaperRiskLiquidityEntry:
    """The LIQ reading of one grid instant: defined (with its exact value, regime and knowledge instant) or UNKNOWN."""

    index: int
    instant_ns: int
    reason: str
    liquidity: str | None
    regime: str
    knowledge_ns: int | None


@dataclass(frozen=True)
class GovernedPaperRiskT8Interval:
    """One proven T8 interval ``[start_ns, end_ns)`` (None while proven at the horizon) of the run through
    ``last_member_ns`` (L-7); a lower bound of the §1.19 trigger only."""

    start_ns: int
    end_ns: int | None
    last_member_ns: int
    evidence_digest: str


@dataclass(frozen=True)
class GovernedPaperRiskCheckReading:
    """One risk check of one decision."""

    check_id: str
    status: GovernedPaperRiskStatus
    observed: str
    reason: str
    evidence: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperRiskReading:
    """Every risk reading of one entry decision; ``reading_digest`` covers every other field.

    ``cvar_severity`` (S3) and ``liquidity_severity`` (S6) are exact rational texts, None with their reason when
    unmeasured. ``obligations`` are the §1.18 de-risk duties this decision proves, each BLOCKED_UNREPRESENTABLE.
    """

    decision_sequence: int
    decision_time_ns: int
    target_direction: str
    checks: tuple[GovernedPaperRiskCheckReading, ...]
    cvar_severity: str | None
    cvar_severity_reason: str
    liquidity_severity: str | None
    liquidity_severity_reason: str
    obligations: tuple[str, ...]
    reading_digest: str

    def check(self, check_id: str) -> GovernedPaperRiskCheckReading:
        for item in self.checks:
            if item.check_id == check_id:
                return item
        raise GovernedPaperRiskError(f"{_PREFIX}:reading_check_missing:{check_id}")


@dataclass(frozen=True)
class GovernedPaperRiskEvidence:
    """The derived risk evidence of one governed evaluation horizon: the CVaR days and spans, the LIQ log, the T8
    intervals and every entry decision's readings."""

    schema_version: str
    contract_id: str
    decision_id: str
    policy_digest: str
    approval_digest: str
    approval_kind: GovernedPaperRiskApprovalKind
    approval_table_id: str
    approval_admitted: bool
    approval_reason: str
    archive_digest: str
    mark_source_digest: str
    dataset_digest: str
    economics_policy_digest: str
    position_management_policy_digest: str
    instrument: str
    start_ns: int
    horizon_ns: int
    book_series_id: str
    book_series_reason: str
    trade_series_id: str
    trade_series_reason: str
    cvar_days: tuple[GovernedPaperRiskCvarDay, ...]
    cvar_segments: tuple[GovernedPaperRiskCvarSegment, ...]
    liquidity: tuple[GovernedPaperRiskLiquidityEntry, ...]
    t8_intervals: tuple[GovernedPaperRiskT8Interval, ...]
    readings: tuple[GovernedPaperRiskReading, ...]
    evidence_digest: str
    paper_only: bool = True
    synthetic_risk_approval_used: bool = False
    production_use_authorized: bool = False
    real_market_source_qualified: bool = False
    venue_facts_proven: bool = False
    monitoring_between_decisions_measured: bool = False
    edge_cvar_measured: bool = False
    marginal_cvar_measured: bool = False
    alternative_depth_definition_applied: bool = False
    de_risk_actions_executed: bool = False
    gap_risk_measured: bool = False
    live_ready: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


GOVERNED_PAPER_RISK_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("production_use_authorized", False),
    ("real_market_source_qualified", False),
    ("venue_facts_proven", False),
    ("monitoring_between_decisions_measured", False),
    ("edge_cvar_measured", False),
    ("marginal_cvar_measured", False),
    ("alternative_depth_definition_applied", False),
    ("de_risk_actions_executed", False),
    ("gap_risk_measured", False),
    ("live_ready", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperRiskError:
    return GovernedPaperRiskError(_reason(code))


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


def _require_text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _exact(value: Fraction) -> str | None:
    """The canonical exact text of a non-negative value, None when it is too large to write (an unrepresentable value)."""

    return historical_execution_risk_rational_text(value)


def _render(value: Fraction) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:  # pragma: no cover - every doctrine constant is representable
        raise _fail("constant_unrepresentable")
    return rendered


def _identical(left: object, right: object) -> bool:
    """Exact typed identity: equal values of the same types throughout (a str enum or an int never passes for another)."""

    if type(left) is not type(right):
        return False
    if is_dataclass(left) and not isinstance(left, type):
        return all(_identical(getattr(left, item.name), getattr(right, item.name)) for item in fields(left))
    if type(left) is tuple:
        return len(left) == len(right) and all(_identical(a, b) for a, b in zip(left, right, strict=True))  # type: ignore[arg-type]
    return left == right


def _verification(digest: str, intact: bool, reasons: tuple[str, ...], payload: object) -> EdgeEvidenceVerification:
    return EdgeEvidenceVerification(
        intact=intact,
        reason_codes=reasons,
        recomputed_digest=digest,
        canonical_json=edge_canonical_json(payload),
    )


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


# --- the policy and its approval ---------------------------------------------------------------------------------------


def _policy_seed(policy_id: str, instrument: str, source_digest: str, interval_ns: int) -> GovernedPaperRiskPolicy:
    return GovernedPaperRiskPolicy(
        schema_version=GOVERNED_PAPER_RISK_POLICY_SCHEMA,
        policy_id=policy_id,
        instrument=instrument,
        mark_source_digest=source_digest,
        mark_interval_ns=interval_ns,
        mark_price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE.value,
        decision_id=GOVERNED_PAPER_RISK_DECISION_ID,
        approved_items=GOVERNED_PAPER_RISK_APPROVED_ITEMS,
        pending_items=GOVERNED_PAPER_RISK_PENDING_ITEMS,
        open_risk_method_id=_OPEN_RISK_METHOD,
        open_risk_cap=str(_RHO_CAP),
        stop_atr_multiple=str(STOP_ATR_MULTIPLE),
        initial_stop_fraction=str(INITIAL_STOP_FRACTION),
        cvar_method_id=_CVAR_METHOD,
        cvar_mc_method_id=_MC_METHOD,
        cvar_mc_selection=_MC_SELECTION,
        cvar_budget=str(_CVAR_BUDGET),
        cvar_closes=_CLOSES,
        cvar_scenarios=_SCENARIOS,
        cvar_decay=str(_DECAY),
        cvar_tail_probability=str(_TAIL),
        cvar_min_tail_count=_MIN_TAIL,
        cvar_mc_paths=_PATHS,
        cvar_mc_top=_TOP,
        max_daily_bar_age_ns=_V1,
        horizon_reading_id=_HORIZON_READING,
        horizon_id="INTRADAY",
        horizon_budget_share=str(_HORIZON_SHARE),
        horizon_cvar_limit=str(_HZ_CVAR_LIMIT),
        stress_limit=str(_STRESS_LIMIT),
        stress_hv_multiple=str(_STRESS_HV_MULTIPLE),
        stress_liq_method_id=_STRESS_LIQ_METHOD,
        stress_liq_depth_factor=str(_STRESS_DEPTH),
        liquidity_method_id=_LIQUIDITY_METHOD,
        observation_grid_ns=_V3,
        liquidity_baseline_members=_BASELINE,
        liquidity_band=str(_BAND),
        tip_freshness_ns=_TIP_FRESHNESS,
        arrival_window_ns=_ARRIVAL,
        liquidity_weights=tuple(str(item) for item in _LIQ_WEIGHTS),
        liquidity_crisis_bound=str(_LIQ_CRISIS),
        liquidity_sustain_ns=_SUSTAIN,
        liquidity_proof_age_ns=_V2,
        t8_lapse_ns=_V4,
        spread_method_id=_SPREAD_METHOD,
        spread_multiple=_SPREAD_MULTIPLE,
        turnover_method_id=_TURNOVER_METHOD,
        turnover_cap=_TURNOVER_CAP,
        policy_digest="",
    )


def governed_paper_risk_policy_digest(policy: GovernedPaperRiskPolicy) -> str:
    """The canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), "policy_digest")


def build_governed_paper_risk_policy(
    *, policy_id: str, instrument: str, mark_source_digest: str, mark_interval_ns: int
) -> GovernedPaperRiskPolicy:
    """The RECORD B policy for one instrument and one MARK bar source of a UTC-day-dividing interval (C-1); every other
    value is fixed here."""

    policy_id = _require_text(policy_id, "policy_id")
    instrument = _require_text(instrument, "instrument")
    if not edge_is_hex64(mark_source_digest):
        raise _fail("mark_source_digest_invalid")
    if not historical_execution_wire_int_is_valid(mark_interval_ns, minimum=1) or _DAY_NS % mark_interval_ns:
        raise _fail("mark_interval_not_a_utc_day_divisor")
    seed = _policy_seed(policy_id, instrument, mark_source_digest, mark_interval_ns)
    return replace(seed, policy_digest=governed_paper_risk_policy_digest(seed))


def verify_governed_paper_risk_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-derive the policy from its id, instrument and source: any other value or a wrong digest is not intact. Total."""

    if type(policy) is not GovernedPaperRiskPolicy:
        return _verification("", False, (_reason("policy_malformed"),), {})
    try:
        rebuilt = build_governed_paper_risk_policy(
            policy_id=policy.policy_id,
            instrument=policy.instrument,
            mark_source_digest=policy.mark_source_digest,
            mark_interval_ns=policy.mark_interval_ns,
        )
    except GovernedPaperRiskError as exc:
        return _verification("", False, (str(exc),), {})
    intact = _identical(policy, rebuilt)
    reasons = () if intact else (_reason("policy_not_the_approved_methodology"),)
    return _verification(rebuilt.policy_digest, intact, reasons, _to_payload(rebuilt))


def governed_paper_risk_approval_digest(approval: GovernedPaperRiskApproval) -> str:
    """The canonical approval digest, excluding only ``approval_digest``."""

    return edge_payload_digest(_to_payload(approval), "approval_digest")


def build_governed_paper_risk_approval(
    *,
    approval_id: str,
    approval_kind: GovernedPaperRiskApprovalKind,
    policy_digest: str,
    approver_reference: str,
) -> GovernedPaperRiskApproval:
    """One approval of ``policy_digest`` over exactly the human construction scope (never production permission)."""

    if type(approval_kind) is not GovernedPaperRiskApprovalKind:
        raise _fail("approval_kind_invalid")
    if not edge_is_hex64(policy_digest):
        raise _fail("approval_policy_digest_invalid")
    seed = GovernedPaperRiskApproval(
        schema_version=GOVERNED_PAPER_RISK_APPROVAL_SCHEMA,
        approval_id=_require_text(approval_id, "approval_id"),
        approval_kind=approval_kind,
        policy_digest=policy_digest,
        approved_items=GOVERNED_PAPER_RISK_APPROVED_ITEMS,
        approver_reference=_require_text(approver_reference, "approver_reference"),
        approval_digest="",
    )
    return replace(seed, approval_digest=governed_paper_risk_approval_digest(seed))


def verify_governed_paper_risk_approval(approval: object) -> EdgeEvidenceVerification:
    """Re-derive the approval: its items must be exactly the approved scope and its digest exact. Total."""

    if type(approval) is not GovernedPaperRiskApproval:
        return _verification("", False, (_reason("approval_malformed"),), {})
    try:
        rebuilt = build_governed_paper_risk_approval(
            approval_id=approval.approval_id,
            approval_kind=approval.approval_kind,
            policy_digest=approval.policy_digest,
            approver_reference=approval.approver_reference,
        )
    except GovernedPaperRiskError as exc:
        return _verification("", False, (str(exc),), {})
    intact = _identical(approval, rebuilt)
    reasons = () if intact else (_reason("approval_not_the_approved_scope"),)
    return _verification(rebuilt.approval_digest, intact, reasons, _to_payload(rebuilt))


def _canonical_table(table: object) -> GovernedPaperRiskApprovalTable:
    if type(table) is not GovernedPaperRiskApprovalTable:
        raise _fail("approval_table_malformed")
    digests = table.admitted_policy_digests
    if type(digests) is not tuple or any(not edge_is_hex64(item) for item in digests):
        raise _fail("approval_table_malformed")
    if table.table_id == "production" and table.admitted_kind is GovernedPaperRiskApprovalKind.HUMAN_GOVERNANCE:
        return table
    if (
        table.table_id == "test_only"
        and table.admitted_kind is GovernedPaperRiskApprovalKind.TEST_ONLY_SYNTHETIC
        and not digests
    ):
        return table
    raise _fail("approval_table_malformed")


def _admission(
    table: GovernedPaperRiskApprovalTable, approval: GovernedPaperRiskApproval, archive: HistoricalOhlcBarArchive
) -> str:
    """Why the approval may not be used under ``table`` (empty when it may)."""

    kind = approval.approval_kind
    if table.table_id == "production":
        if kind is GovernedPaperRiskApprovalKind.TEST_ONLY_SYNTHETIC:
            return "synthetic_approval_refused_on_the_production_table"
        if approval.policy_digest not in table.admitted_policy_digests:
            return "risk_policy_not_authorized_for_production_use"
        if archive.source_qualified is not True:  # C-21: production also needs an M1-qualified archive
            return "mark_archive_not_m1_qualified"
        return ""  # pragma: no cover - no archive is ever qualified
    if kind is not GovernedPaperRiskApprovalKind.TEST_ONLY_SYNTHETIC:
        return "only_test_only_synthetic_approvals_on_the_test_only_table"
    return ""


def governed_paper_risk_rule() -> dict[str, object]:
    """The code-defined rule of this module: every method, value and reading, for the entry gate's rule set."""

    return {
        "contract_id": GOVERNED_PAPER_RISK_CONTRACT_ID,
        "decision_id": GOVERNED_PAPER_RISK_DECISION_ID,
        "policy_schema": GOVERNED_PAPER_RISK_POLICY_SCHEMA,
        "evidence_schema": GOVERNED_PAPER_RISK_EVIDENCE_SCHEMA,
        "approved_items": list(GOVERNED_PAPER_RISK_APPROVED_ITEMS),
        "pending_items": list(GOVERNED_PAPER_RISK_PENDING_ITEMS),
        "approval": "only_an_approval_the_active_table_admits_the_production_table_admits_none",
        "check_ids": list(GOVERNED_PAPER_RISK_CHECK_IDS),
        "NT-R03": "fcd01_r4_entry_from_flat_over_the_candidate_nav_r6_open_position_over_the_nav_fail_iff_rho_gt_"
        "0_04_blocked_on_an_order_in_flight_no_mark_no_armed_stop_no_atr_no_positive_nav_or_unrepresentable",
        "NT-R05": "c9_cvar99_star_of_the_decision_holdings_fail_iff_ge_0_05",
        "cvar": "c1_253_consecutive_visible_daily_closes_latest_within_v1_c5_weighted_es_mc_8a_max_es_cvar_mc_when_"
        "n_tail_lt_50_d_b3_seed",
        "NT-M01": "l6_pass_a_known_valid_non_crisis_within_1800s_fail_latest_known_crisis_within_v2_closing_a_run_gt_"
        "1800s_otherwise_blocked",
        "NT-X03": "x4_fail_iff_spread_gt_3_times_the_exact_median_of_the_8640_as_of_grid_spreads",
        "OB-SPREAD": "x5_fail_iff_spread_ge_3_times_that_median",
        "HZ-TURNOVER": "t4_fail_iff_n_plus_1_gt_20_pass_iff_le_20_counting_an_order_in_flight",
        "HZ-CVAR": "hzb1_fail_iff_cvar99_star_ge_2pct_of_nav",
        "EDGE-CVAR": "blocked_fcd17_kmax_and_h_e_pending",
        "MARGINAL-CVAR": "blocked_the_edge_budget_is_undefined",
        "STRESS-HV": "c15_fail_iff_1_5_times_cvar99_star_ge_0_08",
        "STRESS-CORR": "c16_proven_not_applicable_on_one_instrument",
        "STRESS-LIQ": "ls_a_fail_iff_cvar99_star_plus_the_stressed_exit_cost_over_e_ge_0_08_or_the_whole_holding_"
        "cannot_fill",
        "S3": "c11_min_1_max_0_cvar99_star_over_0_05_on_the_current_holdings",
        "S6": "l8_1_minus_liq_of_the_latest_known_valid_observation_within_v2",
        "T8": "l7_from_the_knowledge_of_a_run_gt_1800s_until_the_next_member_is_known_non_crisis_or_v4_after_it",
        "de_risk": "c18_section_1_18_duties_blocked_unrepresentable_never_executed",
        "values": {
            "V1_max_daily_bar_age_ns": _V1,
            "V2_delta_stale_ns": _V2,
            "V3_delta_obs_ns": _V3,
            "V4_t8_lapse_ns": _V4,
            "open_risk_cap": _render(_RHO_CAP),
            "cvar_budget": _render(_CVAR_BUDGET),
            "horizon_cvar_limit": _render(_HZ_CVAR_LIMIT),
            "stress_limit": _render(_STRESS_LIMIT),
            "liquidity_crisis_bound": _render(_LIQ_CRISIS),
            "turnover_cap": _TURNOVER_CAP,
        },
    }


def governed_paper_risk_horizon_cvar_limit(horizon_id: str) -> Fraction:
    """HZB-1: the §1.18 CVaR99 limit of one §1.27 horizon, as a fraction of NAV per day (its Risk Budget share of 5%)."""

    shares = dict(GOVERNED_PAPER_RISK_HORIZON_SHARES)
    if type(horizon_id) is not str or horizon_id not in shares:
        raise _fail("horizon_unknown")
    return shares[horizon_id] * _CVAR_BUDGET


GOVERNED_PAPER_RISK_RULE = governed_paper_risk_rule()
GOVERNED_PAPER_RISK_RULE_DIGEST = _digest_of(GOVERNED_PAPER_RISK_RULE)


# --- CVaR99* (C-1..C-8, MC-1..MC-11) ---------------------------------------------------------------------------------


def _scenario_weights() -> tuple[Fraction, ...]:
    scale = (1 - _DECAY) / (1 - _DECAY**_SCENARIOS)
    return tuple(_DECAY**age * scale for age in range(_SCENARIOS))


_WEIGHTS = _scenario_weights()


def _thresholds() -> tuple[int, ...]:
    """``ceil(C_a x 2^64)`` of the cumulative weights in ascending age (MC-5); ``C_251 = 1`` exactly."""

    cumulative, total = [], Fraction(0)
    for weight in _WEIGHTS:
        total += weight
        cumulative.append(-(-total.numerator * _TWO_64 // total.denominator))
    return tuple(cumulative)


_THRESHOLDS = _thresholds()


def governed_paper_risk_weighted_es(losses: Sequence[Fraction]) -> tuple[Fraction, Fraction, int]:
    """C-5: the exact lambda-weighted ES, VaR and ``n_tail`` of 252 scenario losses (``losses[a]``, ``a = 0`` newest).

    Losses are ordered descending, ties by ascending age; ``ES = (1/tau) x sum L_(k) x min(w_(k), max(0, tau -
    W_{k-1}))``, ``VaR = L_(k*)`` and ``n_tail = k*`` with ``k*`` the first rank whose cumulative weight reaches tau.
    """

    if len(losses) != _SCENARIOS or any(type(item) is not Fraction for item in losses):
        raise _fail("losses_malformed")
    covered, total = Fraction(0), Fraction(0)
    for rank, age in enumerate(sorted(range(_SCENARIOS), key=lambda item: (-losses[item], item)), start=1):
        weight = _WEIGHTS[age]
        total += losses[age] * min(weight, _TAIL - covered)
        covered += weight
        if covered >= _TAIL:
            return total / _TAIL, losses[age], rank
    raise _fail("weights_do_not_reach_tau")  # pragma: no cover - the weights sum to exactly 1


def governed_paper_risk_mc_seed(
    *, policy_digest: str, source_digest: str, interval_ns: int, series_end_ns: int, close_digests: Sequence[str]
) -> bytes:
    """MC-3 with D-B3: SHA-256 of the canonical JSON of the method id, the risk-policy digest, the source declaration
    digest, the interval, the series end and the 253 daily-close bar digests oldest first (no whole-archive digest)."""

    if not (edge_is_hex64(policy_digest) and edge_is_hex64(source_digest)) or len(close_digests) != _CLOSES:
        raise _fail("mc_seed_inputs_malformed")
    payload = {
        "method_id": _MC_METHOD,
        "risk_policy_digest": policy_digest,
        "source_declaration_digest": source_digest,
        "interval_ns": interval_ns,
        "series_end_ns": series_end_ns,
        "daily_close_bar_digests": list(close_digests),
    }
    return hashlib.sha256(edge_canonical_json(payload).encode("utf-8")).digest()


def governed_paper_risk_mc_ages(seed: bytes) -> tuple[int, ...]:
    """MC-4, MC-5: the age drawn by each of the 10,000 paths of ``seed`` (a 32-byte digest)."""

    if type(seed) is not bytes or len(seed) != 32:  # noqa: PLR2004 - a SHA-256 digest
        raise _fail("mc_seed_malformed")
    return tuple(
        bisect.bisect_right(
            _THRESHOLDS, int.from_bytes(hashlib.sha256(seed + index.to_bytes(8, "big")).digest()[:8], "big")
        )
        for index in range(_PATHS)
    )


def governed_paper_risk_cvar_star(losses: Sequence[Fraction], seed: bytes) -> GovernedPaperRiskCvarEstimate:
    """C-5..C-8 with MC-8a: ES when ``n_tail >= 50``, else ``max(ES, CVaR_MC)`` over the 10,000 paths of ``seed``."""

    return _estimate(losses, lambda: Counter(governed_paper_risk_mc_ages(seed)))


def _estimate(losses: Sequence[Fraction], counts: Callable[[], Counter[int]]) -> GovernedPaperRiskCvarEstimate:
    es, var, tail = governed_paper_risk_weighted_es(losses)
    if tail >= _MIN_TAIL:
        return GovernedPaperRiskCvarEstimate(es, var, tail, False, None, None, es)
    var_mc, cvar_mc = _monte_carlo(counts(), losses)
    return GovernedPaperRiskCvarEstimate(es, var, tail, True, var_mc, cvar_mc, max(es, cvar_mc))


def _monte_carlo(counts: Counter[int], losses: Sequence[Fraction]) -> tuple[Fraction, Fraction]:
    """MC-6: the top 100 path losses (descending; the order of equal losses changes no value) give VaR_MC, the 100th,
    and CVaR_MC, their exact mean."""

    remaining, total = _TOP, Fraction(0)
    for age in sorted(counts, key=lambda item: (-losses[item], item)):
        taken = min(counts[age], remaining)
        total += losses[age] * taken
        remaining -= taken
        if remaining == 0:
            return losses[age], total / _TOP
    raise _fail("fewer_than_100_paths")  # pragma: no cover - 10,000 paths are always drawn


@dataclass(frozen=True)
class _Close:
    close_ns: int
    price: Fraction
    visible_ns: int
    digest: str


def _daily_closes(archive: HistoricalOhlcBarArchive, interval_ns: int) -> dict[int, _Close]:
    """Every daily close of the archive: the close of the bar of ``interval_ns`` ending at a UTC midnight (C-1)."""

    return {
        bar.close_time_ns: _Close(
            bar.close_time_ns, Fraction(bar.close_price), max(bar.available_at_ns, bar.finalized_at_ns), bar.bar_digest
        )
        for bar in archive.bars
        if bar.interval_ns == interval_ns and bar.close_time_ns % _DAY_NS == 0
    }


def _series_at(closes: dict[int, _Close], ordered: Sequence[int], time_ns: int) -> tuple[str, int | None]:
    """C-1 at ``time_ns``: ``("", series end)`` of the 253 consecutive closes ending with the latest visible one, or the
    reason (with the latest visible close, when one exists)."""

    visible = [close for close in ordered if closes[close].visible_ns <= time_ns]
    if not visible:
        return "cvar_history_insufficient", None
    latest = visible[-1]
    if latest < time_ns - _V1:
        return "cvar_history_stale", latest
    for back in range(_CLOSES):
        item = closes.get(latest - back * _DAY_NS)
        if item is None or item.visible_ns > time_ns:
            return "cvar_history_insufficient", latest
    return "", latest


@dataclass(frozen=True)
class _Day:
    record: GovernedPaperRiskCvarDay
    long: Fraction | None
    short: Fraction | None


def _day(
    policy: GovernedPaperRiskPolicy, archive: HistoricalOhlcBarArchive, closes: dict[int, _Close], end: int
) -> _Day:
    series = [closes[end - (_CLOSES - 1 - position) * _DAY_NS] for position in range(_CLOSES)]  # oldest first
    returns = [series[_CLOSES - 1 - age].price / series[_CLOSES - 2 - age].price - 1 for age in range(_SCENARIOS)]
    digests = [item.digest for item in series]
    seed = governed_paper_risk_mc_seed(
        policy_digest=policy.policy_digest,
        source_digest=archive.source_digest,
        interval_ns=policy.mark_interval_ns,
        series_end_ns=end,
        close_digests=digests,
    )
    drawn: list[Counter[int]] = []  # the 10,000 draws are independent of the side: drawn once, read by both

    def counts() -> Counter[int]:
        if not drawn:
            drawn.append(Counter(governed_paper_risk_mc_ages(seed)))
        return drawn[0]

    long = _estimate([-item for item in returns], counts)
    short = _estimate(returns, counts)
    long_text, short_text = _exact(long.cvar), _exact(short.cvar)
    unrepresentable = long_text is None or short_text is None
    record = GovernedPaperRiskCvarDay(
        series_end_ns=end,
        reason="cvar_value_unrepresentable" if unrepresentable else "",
        closes_digest=_digest_of(digests),
        seed=seed.hex(),
        long_cvar=None if unrepresentable else long_text,
        long_tail_count=long.tail_count,
        long_monte_carlo_used=long.monte_carlo_used,
        short_cvar=None if unrepresentable else short_text,
        short_tail_count=short.tail_count,
        short_monte_carlo_used=short.monte_carlo_used,
    )
    return _Day(record, None if unrepresentable else long.cvar, None if unrepresentable else short.cvar)


# --- the books and the trades of the authenticated dataset ---------------------------------------------------------------

# The registry 1.0 semantics of the LAST_TRADE series, exactly as its only producer (authenticated_pit_ingress) enforces
# them on the bound EF-3 series record (the entry gate re-proves the same set for NT-D01..NT-D05).
_TRADE_SEMANTICS: tuple[tuple[str, object], ...] = (
    ("registry_requirement_bound", True),
    ("finality", "finalized_only"),
    ("revision_policy", "immutable_after_finalization"),
    ("historical_source", "trade_history_v1"),
    ("event_time_policy", "trade_event_ns"),
    ("available_at_policy", "trade_available_ns"),
    ("finalized_at_policy", "trade_finalized_ns"),
    ("price_semantics", "last_trade"),
    ("sequence_policy", None),
    ("finality_policy", "trade_tick_final"),
)
_TRADE_NAMES = (
    frozenset({TRADE_PRICE_VALUE_NAME, TRADE_QUANTITY_VALUE_NAME}),
    frozenset({TRADE_PRICE_VALUE_NAME, TRADE_QUANTITY_VALUE_NAME, TRADE_RUN_FIRST_ID_VALUE_NAME}),
)


def _authenticated_series(dataset: HistoricalPitDataset) -> tuple[EdgeSourceSeriesRecord, ...]:
    snapshot = edge_authority_binding_snapshot(dataset.source_manifest_binding)
    if not edge_source_packet_evidence_payload_is_well_formed(snapshot):
        raise _fail("dataset_manifest_not_authentic")
    manifest = edge_source_packet_evidence_from_payload(snapshot)
    verification = verify_edge_source_packet_evidence(manifest)
    if (
        not verification.intact
        or verification.recomputed_digest != dataset.source_manifest_digest
        or manifest.status is not EdgeEvidenceStatus.READY
    ):
        raise _fail("dataset_manifest_not_authentic")
    return manifest.series


def _trade_series(authenticated: Sequence[EdgeSourceSeriesRecord], instrument: str) -> tuple[str, str]:
    candidates = [
        record
        for record in authenticated
        if record.data_requirement_key == DataRequirementKey.LAST_TRADE.value
        and instrument in record.instrument_coverage
    ]
    if not candidates:
        return "last_trade_series_not_in_the_selected_data_contract", ""
    if len(candidates) > 1:
        return "last_trade_series_ambiguous", ""
    record = candidates[0]
    if record.finalized_only is not True or record.revision_policy != "immutable_after_finalization":
        return "last_trade_series_not_final_and_immutable", ""
    if not all(
        type(getattr(record, name)) is type(value) and getattr(record, name) == value
        for name, value in _TRADE_SEMANTICS
    ):
        return "last_trade_series_semantics_unsupported", ""
    return "", record.series_id


@dataclass(frozen=True)
class _Trade:
    trade_id: int
    event_ns: int
    visible_ns: int
    run_first: int | None


def _number(text: str) -> Fraction | None:
    try:
        return Fraction(text)
    except (ValueError, ZeroDivisionError):
        return None


def _trade_of(record: HistoricalPitRecord, visible: int) -> _Trade | None:
    """One well-formed trade record (positive price and quantity; a declared run that starts at or before it), else None:
    the parse the entry gate's NT-D readings use."""

    values = {value.name: value.value for value in record.values}
    if len(values) != len(record.values) or frozenset(values) not in _TRADE_NAMES:
        return None
    price, quantity = _number(values[TRADE_PRICE_VALUE_NAME]), _number(values[TRADE_QUANTITY_VALUE_NAME])
    run = values.get(TRADE_RUN_FIRST_ID_VALUE_NAME)
    first: int | None = None
    if run is not None:
        whole = _number(run)
        if whole is None or whole.denominator != 1 or whole < 0 or whole > record.sequence_id:
            return None
        first = whole.numerator
    if price is None or quantity is None or price <= 0 or quantity <= 0:
        return None
    return _Trade(record.sequence_id, record.event_time_ns, visible, first)


class _RangeMax:
    """Exact range maximum over a fixed integer list (a sparse table)."""

    def __init__(self, values: Sequence[int]) -> None:
        self._levels = [list(values)]
        width = 1
        while 2 * width <= len(values):
            previous = self._levels[-1]
            self._levels.append(
                [max(previous[index], previous[index + width]) for index in range(len(values) - 2 * width + 1)]
            )
            width *= 2

    def query(self, low: int, high: int) -> int:
        """The maximum over ``[low, high]`` (inclusive, ``low <= high``)."""

        level = (high - low + 1).bit_length() - 1
        row = self._levels[level]
        return max(row[low], row[high - (1 << level) + 1])


class _Trades:
    """The dataset's LAST_TRADE series of one instrument, in native id order, for the L-2 arrival proof."""

    def __init__(self, dataset: HistoricalPitDataset, instrument: str) -> None:
        self.reason, self.series = _trade_series(_authenticated_series(dataset), instrument)
        self.malformed_from: int | None = None
        trades: list[_Trade] = []
        if not self.reason:
            for record in dataset.records:
                if record.series_id != self.series or record.instrument != instrument or record.finalized_at_ns is None:
                    continue
                visible = max(record.available_at_ns, record.finalized_at_ns)
                trade = _trade_of(record, visible)
                if trade is None:
                    self.malformed_from = visible if self.malformed_from is None else min(self.malformed_from, visible)
                else:
                    trades.append(trade)
        trades.sort(key=lambda item: item.trade_id)
        if any(later.event_ns < earlier.event_ns for earlier, later in zip(trades, trades[1:], strict=False)):
            # the declared profile forbids an event-time regression; the series proves no window at all
            self.reason, trades = "trade_event_time_regressed_in_native_id_order", []
        self._trades = trades
        self._events = [item.event_ns for item in trades]
        self._visible = _RangeMax([item.visible_ns for item in trades]) if trades else None
        breaks, undeclared = [0], [0]
        for position, trade in enumerate(trades):
            previous = trades[position - 1] if position else None
            continued = previous is not None and (
                trade.run_first is not None
                and trade.run_first == previous.run_first
                and trade.trade_id == previous.trade_id + 1
            )
            breaks.append(breaks[-1] + (0 if position == 0 or continued else 1))
            undeclared.append(undeclared[-1] + (trade.run_first is None))
        self._breaks, self._undeclared = breaks, undeclared

    def arrival(self, instant: int) -> tuple[str, int | None, int | None]:
        """L-2 at ``instant``: ``("", count, kappa)`` of the trades with event time in ``[instant - 300 s, instant)``, or
        the reason no contiguous declared run proves the window."""

        if self.reason:
            return self.reason, None, None
        before = bisect.bisect_left(self._events, instant - _ARRIVAL) - 1
        after = bisect.bisect_left(self._events, instant)
        if before < 0:
            return "no_trade_strictly_before_the_arrival_window", None, None
        if after >= len(self._trades):
            return "no_trade_at_or_after_the_observation_instant", None, None
        if self._undeclared[after + 1] - self._undeclared[before]:
            return "trade_continuity_profile_not_declared", None, None
        if self._breaks[after + 1] - self._breaks[before + 1]:
            return "trade_continuity_broken_across_the_arrival_window", None, None
        kappa = self._visible.query(before, after)  # type: ignore[union-attr]
        if self.malformed_from is not None and self.malformed_from <= kappa:
            return "last_trade_record_malformed", None, None
        return "", after - before - 1, kappa


@dataclass(frozen=True)
class _Tip:
    visible_ns: int
    event_ns: int
    sequence_id: int
    record: HistoricalPitRecord


class _Tips:
    """The dataset's ORDER_BOOK depth-50 series of one instrument (the registry semantics every book reading uses)."""

    def __init__(self, dataset: HistoricalPitDataset, instrument: str) -> None:
        try:
            self.reason, self.series = governed_paper_order_book_series(dataset, instrument)
        except GovernedPaperRegimeError as exc:
            raise _fail("dataset_manifest_not_authentic") from exc
        tips: list[_Tip] = []
        if not self.reason:
            for record in dataset.records:
                if record.series_id != self.series or record.instrument != instrument or record.finalized_at_ns is None:
                    continue
                tips.append(
                    _Tip(
                        max(record.available_at_ns, record.finalized_at_ns),
                        record.event_time_ns,
                        record.sequence_id,
                        record,
                    )
                )
        tips.sort(key=lambda item: (item.visible_ns, item.event_ns, item.sequence_id))
        self._tips = tips
        self._visible = [item.visible_ns for item in tips]
        self._parsed: dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]] | None] = {}

    def levels(
        self, record: HistoricalPitRecord
    ) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]] | None:
        digest = record.record_digest
        if digest not in self._parsed:
            self._parsed[digest] = governed_paper_order_book_levels(record)
        return self._parsed[digest]

    def walk(self, instants: Sequence[int]) -> list[_Tip | None]:
        """D-B1 at each of the ascending ``instants``: the latest tip by native event time (then sequence) among those
        visible at or before it, when its event time is at least the instant minus 10 s; a later-visible tip never
        enters an earlier instant."""

        chosen: list[_Tip | None] = []
        known: list[tuple[int, int, int]] = []
        cursor = 0
        for instant in instants:
            while cursor < len(self._tips) and self._tips[cursor].visible_ns <= instant:
                tip = self._tips[cursor]
                bisect.insort(known, (tip.event_ns, tip.sequence_id, cursor))
                cursor += 1
            position = bisect.bisect_right(known, (instant, _INFINITY, _INFINITY))
            if position and instant - known[position - 1][0] <= _TIP_FRESHNESS:
                chosen.append(self._tips[known[position - 1][2]])
            else:
                chosen.append(None)
        return chosen

    def at(self, instant: int) -> _Tip | None:
        count = bisect.bisect_right(self._visible, instant)
        if count == 0:
            return None
        latest = max(self._tips[:count], key=lambda item: (item.event_ns, item.sequence_id))
        return latest if instant - latest.event_ns <= _TIP_FRESHNESS else None


def governed_paper_risk_tip_reading(
    levels: tuple[Sequence[tuple[int, int]], Sequence[tuple[int, int]]],
) -> tuple[str, int | None, Fraction | None]:
    """L-2 and D-B2 on one parsed depth-50 tip (levels in integer units of 10^-18, best first): ``(reason, depth_raw,
    spread_raw)``.

    A crossed or locked tip gives nothing. ``spread_raw = (ask - bid) / mid``. A side's band sum (quote notional, units
    of 10^-36) is exact only when its 50th level lies strictly beyond the band edge; ``depth_raw`` is defined only when the
    minimum is attained on an exact side, otherwise the reason names it and the spread is still returned.
    """

    bids, asks = levels
    bid, ask = bids[0][0], asks[0][0]
    if bid >= ask:
        return "order_book_tip_crossed_or_locked", None, None
    total = bid + ask  # twice the mid
    spread = Fraction(2 * (ask - bid), total)
    low, high = (_BAND_EDGE - 1) * total, (_BAND_EDGE + 1) * total  # 2 x 2,000 x the band edges
    bid_sum = sum(price * quantity for price, quantity in bids if 2 * _BAND_EDGE * price >= low)
    ask_sum = sum(price * quantity for price, quantity in asks if 2 * _BAND_EDGE * price <= high)
    bid_exact = 2 * _BAND_EDGE * bids[-1][0] < low
    ask_exact = 2 * _BAND_EDGE * asks[-1][0] > high
    if bid_exact and ask_exact:
        return "", min(bid_sum, ask_sum), spread
    if bid_exact and ask_sum >= bid_sum:
        return "", bid_sum, spread
    if ask_exact and bid_sum >= ask_sum:
        return "", ask_sum, spread
    return "depth_minimum_not_attained_on_an_exact_side", None, spread


# --- the LIQ log (L-3, L-4) ------------------------------------------------------------------------------------------------


def governed_paper_risk_liquidity_entries(
    observations: Sequence[GovernedPaperRiskObservation], *, first: int, last: int
) -> tuple[GovernedPaperRiskLiquidityEntry, ...]:
    """L-3 and L-4 over the grid indexes ``[first, last]``: ``observations`` hold exactly the indexes
    ``[first - 8,640, last]`` in order. Each reading needs its own observation and its 8,640 members valid; its knowledge
    instant is the latest ``kappa`` of all 8,641. Pure and exact."""

    low = first - _BASELINE
    if (
        last < first
        or len(observations) != last - low + 1
        or any(item.index != low + offset for offset, item in enumerate(observations))
    ):
        raise _fail("liquidity_observations_malformed")
    kappas = _RangeMax([-1 if item.reason else item.knowledge_ns for item in observations])  # type: ignore[misc]
    depth: list[int] = []
    spread: list[Fraction] = []
    arrival: list[int] = []
    invalid = 0
    for item in observations[:_BASELINE]:
        if item.reason:
            invalid += 1
        else:
            bisect.insort(depth, item.depth)  # type: ignore[arg-type]
            bisect.insort(spread, item.spread)  # type: ignore[arg-type]
            bisect.insort(arrival, item.arrival)  # type: ignore[arg-type]
    entries: list[GovernedPaperRiskLiquidityEntry] = []
    width = 2 * _BASELINE
    for offset in range(_BASELINE, len(observations)):
        item = observations[offset]
        index = item.index
        instant = index * _V3
        if item.reason:
            entries.append(GovernedPaperRiskLiquidityEntry(index, instant, item.reason, None, _UNKNOWN, None))
        elif invalid:
            entries.append(
                GovernedPaperRiskLiquidityEntry(index, instant, "baseline_member_invalid", None, _UNKNOWN, None)
            )
        else:
            d = bisect.bisect_left(depth, item.depth) + bisect.bisect_right(depth, item.depth)  # type: ignore[arg-type]
            a = bisect.bisect_left(arrival, item.arrival) + bisect.bisect_right(arrival, item.arrival)  # type: ignore[arg-type]
            s = width - bisect.bisect_left(spread, item.spread) - bisect.bisect_right(spread, item.spread)  # type: ignore[arg-type]
            value = (_LIQ_WEIGHTS[0] * d + _LIQ_WEIGHTS[1] * s + _LIQ_WEIGHTS[2] * a) / width
            knowledge = kappas.query(offset - _BASELINE, offset)
            entries.append(
                GovernedPaperRiskLiquidityEntry(
                    index, instant, "", str(value), _CRISIS if value < _LIQ_CRISIS else _NON_CRISIS, knowledge
                )
            )
        leaving = observations[offset - _BASELINE]
        if leaving.reason:
            invalid -= 1
        else:
            del depth[bisect.bisect_left(depth, leaving.depth)]  # type: ignore[arg-type]
            del spread[bisect.bisect_left(spread, leaving.spread)]  # type: ignore[arg-type]
            del arrival[bisect.bisect_left(arrival, leaving.arrival)]  # type: ignore[arg-type]
        if item.reason:
            invalid += 1
        else:
            bisect.insort(depth, item.depth)  # type: ignore[arg-type]
            bisect.insort(spread, item.spread)  # type: ignore[arg-type]
            bisect.insort(arrival, item.arrival)  # type: ignore[arg-type]
    return tuple(entries)


def _known(entry: GovernedPaperRiskLiquidityEntry, at: int) -> bool:
    return entry.knowledge_ns is not None and entry.knowledge_ns <= at


def governed_paper_risk_nt_m01(
    entries: Sequence[GovernedPaperRiskLiquidityEntry], time_ns: int
) -> tuple[GovernedPaperRiskStatus, str, str, tuple[str, ...]]:
    """L-6 at ``time_ns`` over ``entries`` (consecutive grid indexes): ``(status, observed, reason, evidence)``."""

    by_index = {item.index: item for item in entries}
    known = [item for item in entries if _known(item, time_ns)]
    passing = [item for item in known if item.regime == _NON_CRISIS and time_ns - item.instant_ns <= _SUSTAIN]
    latest = max(known, key=lambda item: item.index) if known else None
    failing = False
    if latest is not None and latest.regime == _CRISIS and time_ns - latest.instant_ns <= _V2:
        run = [by_index.get(latest.index - back) for back in range(_RUN)]
        failing = all(item is not None and item.regime == _CRISIS and _known(item, time_ns) for item in run)
    if passing and failing:  # pragma: no cover - a run beyond 30 minutes ending at the latest known instant excludes it
        raise _fail("nt_m01_pass_and_fail_together")
    if passing:
        proof = max(passing, key=lambda item: item.index)
        return (
            GovernedPaperRiskStatus.PASS,
            f"non_crisis_at={proof.instant_ns};liq={proof.liquidity}",
            ("valid_non_crisis_observation_known_within_30min_no_crisis_run_beyond_30min_ends_at_t"),
            (_digest_of(_to_payload(proof)),),
        )
    if failing:
        return (
            GovernedPaperRiskStatus.FAIL,
            f"crisis_through={latest.instant_ns};liq={latest.liquidity}",
            (  # type: ignore[union-attr]
                "latest_known_observation_closes_a_crisis_run_beyond_30min_within_v2"
            ),
            (_digest_of([_to_payload(item) for item in run]),),
        )  # type: ignore[union-attr]
    if latest is None:
        return GovernedPaperRiskStatus.BLOCKED, "", "no_liquidity_observation_known_at_t", ()
    return (
        GovernedPaperRiskStatus.BLOCKED,
        f"latest_known={latest.instant_ns};regime={latest.regime}",
        ("neither_a_non_crisis_proof_within_30min_nor_a_proven_crisis_run_beyond_30min"),
        (_digest_of(_to_payload(latest)),),
    )


def governed_paper_risk_liquidity_severity(
    entries: Sequence[GovernedPaperRiskLiquidityEntry], time_ns: int
) -> tuple[Fraction | None, str]:
    """L-8: ``1 - LIQ(s_l)`` of the latest observation known at ``time_ns`` when it is valid and within V2."""

    known = [item for item in entries if _known(item, time_ns)]
    if not known:
        return None, "no_liquidity_observation_known_at_t"
    latest = max(known, key=lambda item: item.index)
    if time_ns - latest.instant_ns > _V2:
        return None, "latest_known_liquidity_observation_older_than_v2"
    return 1 - Fraction(latest.liquidity), ""  # type: ignore[arg-type]


def governed_paper_risk_t8_intervals(
    entries: Sequence[GovernedPaperRiskLiquidityEntry], *, start_ns: int, horizon_ns: int
) -> tuple[GovernedPaperRiskT8Interval, ...]:
    """L-7 over ``[start_ns, horizon_ns)``: the proven T8 intervals, one per last known member of a qualifying run,
    adjacent intervals of consecutive members merged under the first one. Pure."""

    by_index = {item.index: item for item in entries}
    spans: list[tuple[int, int | None, int, str]] = []
    for item in entries:
        run = [by_index.get(item.index - back) for back in range(_RUN)]
        if not all(member is not None and member.regime == _CRISIS for member in run):
            continue
        begin = max(member.knowledge_ns for member in run)  # type: ignore[type-var,union-attr]
        following = by_index.get(item.index + 1)
        lapse = (item.index + 1) * _V3 + _V4
        if following is not None and following.knowledge_ns is not None:  # the next member is known valid by then
            lapse = min(lapse, following.knowledge_ns)
        begin, lapse = max(begin, start_ns), min(lapse, horizon_ns)  # type: ignore[assignment]
        if begin >= lapse:
            continue
        evidence = _digest_of([_to_payload(member) for member in run])  # type: ignore[arg-type]
        spans.append((begin, None if lapse >= horizon_ns else lapse, item.instant_ns, evidence))
    merged: list[GovernedPaperRiskT8Interval] = []
    for begin, end, member, evidence in sorted(spans):
        previous = merged[-1] if merged else None
        if previous is not None and previous.end_ns is not None and previous.end_ns >= begin:
            if end is None or end > previous.end_ns:
                merged[-1] = replace(previous, end_ns=end)
            continue
        if previous is not None and previous.end_ns is None:
            continue
        merged.append(GovernedPaperRiskT8Interval(begin, end, member, evidence))
    return tuple(merged)


# --- NT-X03 / OB-SPREAD (X-1..X-7) and turnover (T-1..T-6) ----------------------------------------------------------------


def governed_paper_risk_spread_checks(
    current: Fraction | None, current_reason: str, baseline: Sequence[Fraction | None]
) -> tuple[tuple[GovernedPaperRiskStatus, str, str], tuple[GovernedPaperRiskStatus, str, str]]:
    """X-3..X-6: ``((NT-X03 status, observed, reason), (OB-SPREAD status, observed, reason))`` of the current spread and
    the 8,640 baseline spreads (None for a missing, invalid or not-yet-visible member)."""

    if len(baseline) != _BASELINE:
        raise _fail("spread_baseline_malformed")
    if current is None:
        blocked = (GovernedPaperRiskStatus.BLOCKED, "", current_reason)
        return blocked, blocked
    missing = sum(1 for item in baseline if item is None)
    if missing:
        blocked = (GovernedPaperRiskStatus.BLOCKED, "", f"thirty_day_spread_baseline_incomplete_{missing}_members")
        return blocked, blocked
    ordered = sorted(baseline)  # type: ignore[type-var]
    median = (ordered[_MEDIAN[0] - 1] + ordered[_MEDIAN[1] - 1]) / 2  # type: ignore[operator]
    observed = f"spread={current};median={median}"
    limit = _SPREAD_MULTIPLE * median
    x03 = (
        (GovernedPaperRiskStatus.FAIL, observed, "spread_strictly_above_3x_the_30d_median")
        if current > limit
        else (GovernedPaperRiskStatus.PASS, observed, "spread_at_or_below_3x_the_30d_median")
    )
    ob = (
        (GovernedPaperRiskStatus.FAIL, observed, "spread_at_or_above_3x_the_30d_median")
        if current >= limit
        else (GovernedPaperRiskStatus.PASS, observed, "spread_strictly_below_3x_the_30d_median")
    )
    return x03, ob


def governed_paper_risk_turnover(
    trade_starts: Sequence[int] | None, time_ns: int, *, order_in_flight: bool
) -> tuple[GovernedPaperRiskStatus, str, str]:
    """T-3 and T-4 at ``time_ns`` from the first-entry-fill instants of the governed trades (None without the ledger)."""

    if trade_starts is None:
        return GovernedPaperRiskStatus.BLOCKED, "", "governed_trade_ledger_not_available"
    day = time_ns // _DAY_NS * _DAY_NS
    count = sum(1 for item in trade_starts if day <= item < time_ns)
    observed = f"trades_today={count};order_in_flight={str(order_in_flight).lower()}"
    if count + 1 > _TURNOVER_CAP:
        return GovernedPaperRiskStatus.FAIL, observed, "the_entry_would_be_trade_21_or_more_of_the_utc_day"
    if count + 1 + int(order_in_flight) <= _TURNOVER_CAP:
        return GovernedPaperRiskStatus.PASS, observed, "the_entry_is_at_most_trade_20_of_the_utc_day"
    return GovernedPaperRiskStatus.BLOCKED, observed, "an_order_in_flight_may_be_trade_20_of_the_utc_day"


def governed_paper_risk_stop_risk(quantity: Fraction, mark: Fraction, stop: Fraction, cost: Fraction) -> Fraction:
    """R-1: ``|q| x sgn(q) x (m - x) + |q| x x x c``, ``x`` the stop while ``sgn(q) x (m - stop) > 0``, else the mark."""

    if quantity == 0:
        return Fraction(0)
    sign = 1 if quantity > 0 else -1
    exit_price = stop if sign * (mark - stop) > 0 else mark
    return abs(quantity) * sign * (mark - exit_price) + abs(quantity) * exit_price * cost


# --- the market facts of one evaluation (schedule-independent, memoized) ---------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperRiskMarket:
    """The schedule-independent risk facts of one evaluation, derived once from re-proven inputs (in memory only)."""

    policy_digest: str
    approval_digest: str
    approval_kind: GovernedPaperRiskApprovalKind
    approval_table_id: str
    approval_admitted: bool
    approval_reason: str
    archive_digest: str
    mark_source_digest: str
    dataset_digest: str
    instrument: str
    start_ns: int
    horizon_ns: int
    book_series_id: str
    book_series_reason: str
    trade_series_id: str
    trade_series_reason: str
    cvar_days: tuple[GovernedPaperRiskCvarDay, ...]
    cvar_segments: tuple[GovernedPaperRiskCvarSegment, ...]
    cvar_units: tuple[tuple[int, Fraction, Fraction], ...]  # (series end, long unit, short unit), exact
    liquidity: tuple[GovernedPaperRiskLiquidityEntry, ...]
    spreads: tuple[tuple[int, Fraction | None], ...]  # (grid index, as-of spread or None), ascending
    t8_intervals: tuple[GovernedPaperRiskT8Interval, ...]
    tips: object  # the _Tips index of the dataset (the decision-time tip of X-1 and LS-A)


_MARKET_MEMO: OrderedDict[tuple[object, ...], GovernedPaperRiskMarket] = OrderedDict()


def _canonical_context(context: object) -> GovernedPaperRiskContext:
    if type(context) is not GovernedPaperRiskContext:
        raise _fail("context_malformed")
    return context


def _proven_inputs(context: GovernedPaperRiskContext, dataset: object, instrument: object) -> tuple[str, str, str, str]:
    """Re-prove the policy, its approval, the archive of the policy source and the dataset; their recomputed digests."""

    policy_check = verify_governed_paper_risk_policy(context.policy)
    if not policy_check.intact:
        raise _fail("policy_not_authentic")
    approval_check = verify_governed_paper_risk_approval(context.approval)
    if not approval_check.intact or context.approval.policy_digest != policy_check.recomputed_digest:
        raise _fail("approval_not_of_the_policy")
    if type(instrument) is not str or instrument != context.policy.instrument:
        raise _fail("instrument_not_of_the_policy")
    archive = context.archive
    if type(archive) is not HistoricalOhlcBarArchive:
        raise _fail("archive_malformed")
    archive_check = verify_historical_ohlc_bar_archive(archive)
    if not archive_check.intact:
        raise _fail("archive_not_authentic")
    source = archive.source
    if (
        archive.source_digest != context.policy.mark_source_digest
        or source.instrument != instrument
        or source.price_semantics is not HistoricalOhlcPriceSemantics.MARK_PRICE
        or context.policy.mark_interval_ns not in source.bar_intervals_ns
    ):
        raise _fail("archive_not_of_the_policy_source")
    if type(dataset) is not HistoricalPitDataset:
        raise _fail("dataset_malformed")
    dataset_check = verify_historical_pit_dataset(dataset)
    if not dataset_check.intact or dataset.status is not EdgeEvidenceStatus.READY or dataset.advances is not True:
        raise _fail("dataset_not_authentic")
    return (
        policy_check.recomputed_digest,
        approval_check.recomputed_digest,
        archive_check.recomputed_digest,
        dataset_check.recomputed_digest,
    )


def _cvar_facts(
    policy: GovernedPaperRiskPolicy, archive: HistoricalOhlcBarArchive, start_ns: int, horizon_ns: int
) -> tuple[
    tuple[GovernedPaperRiskCvarDay, ...],
    tuple[GovernedPaperRiskCvarSegment, ...],
    tuple[tuple[int, Fraction, Fraction], ...],
]:
    closes = _daily_closes(archive, policy.mark_interval_ns)
    ordered = sorted(closes)
    events = {start_ns}
    for close in ordered:
        for instant in (closes[close].visible_ns, close + _V1 + 1):
            if start_ns < instant < horizon_ns:
                events.add(instant)
    instants = sorted(events)
    segments: list[GovernedPaperRiskCvarSegment] = []
    days: dict[int, _Day] = {}
    for position, instant in enumerate(instants):
        end = instants[position + 1] if position + 1 < len(instants) else horizon_ns
        reason, latest = _series_at(closes, ordered, instant)
        if not reason:
            if latest not in days:
                days[latest] = _day(policy, archive, closes, latest)  # type: ignore[index,arg-type]
            reason = days[latest].record.reason  # type: ignore[index]
        series = latest if not reason else None
        previous = segments[-1] if segments else None
        if previous is not None and previous.series_end_ns == series and previous.reason == reason:
            segments[-1] = replace(previous, end_ns=end)
        else:
            segments.append(GovernedPaperRiskCvarSegment(instant, end, series, reason))
    units = tuple(
        (end, day.long, day.short)  # type: ignore[misc]
        for end, day in sorted(days.items())
        if day.long is not None and day.short is not None
    )
    return tuple(days[end].record for end in sorted(days)), tuple(segments), units  # type: ignore[return-value]


def _observations(
    tips: _Tips, trades: _Trades, low: int, high: int
) -> tuple[list[GovernedPaperRiskObservation], dict[int, Fraction | None]]:
    """L-2 at every grid index of ``[low, high]``, and each instant's X-2 baseline spread (None when invalid)."""

    indexes = list(range(low, high + 1))
    walked = tips.walk([max(index, 0) * _V3 for index in indexes]) if not tips.reason else [None] * len(indexes)
    observations: list[GovernedPaperRiskObservation] = []
    spreads: dict[int, Fraction | None] = {}
    for index, tip in zip(indexes, walked, strict=True):
        instant = index * _V3
        spreads[index] = None
        if index < 0:
            observations.append(GovernedPaperRiskObservation(index, "before_the_utc_epoch", None, None, None, None))
            continue
        if tips.reason or tip is None:
            reason = tips.reason or "no_fresh_depth_50_tip_visible_at_the_instant"
            observations.append(GovernedPaperRiskObservation(index, reason, None, None, None, None))
            continue
        levels = tips.levels(tip.record)
        if levels is None:
            observations.append(GovernedPaperRiskObservation(index, "order_book_tip_malformed", None, None, None, None))
            continue
        tip_reason, depth, spread = governed_paper_risk_tip_reading(levels)
        spreads[index] = spread
        arrival_reason, arrival, kappa = trades.arrival(instant)
        reason = tip_reason or arrival_reason
        if reason:
            observations.append(GovernedPaperRiskObservation(index, reason, None, spread, None, None))
            continue
        knowledge = max(tip.visible_ns, kappa)  # type: ignore[type-var]
        observations.append(GovernedPaperRiskObservation(index, "", depth, spread, arrival, knowledge))
    return observations, spreads


def derive_governed_paper_risk_market(
    context: GovernedPaperRiskContext,
    *,
    dataset: HistoricalPitDataset,
    instrument: str,
    start_ns: int,
    horizon_ns: int,
) -> GovernedPaperRiskMarket:
    """The schedule-independent risk facts of ``[start_ns, horizon_ns)``: the C-1 spans and their unit CVaR99*, the LIQ
    log, its T8 intervals and the X-2 grid spreads. Every input is re-proven; an approval the active table does not admit
    gives no reading at all (empty facts). Pure (an exact memo of identical re-proven inputs)."""

    context = _canonical_context(context)
    digests = _proven_inputs(context, dataset, instrument)
    for value, name in ((start_ns, "start_ns"), (horizon_ns, "horizon_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if horizon_ns <= start_ns:
        raise _fail("evaluation_horizon_invalid")
    table = _canonical_table(_APPROVAL_TABLE)
    key = (
        *digests,
        instrument,
        start_ns,
        horizon_ns,
        table.table_id,
        table.admitted_kind.value,
        table.admitted_policy_digests,
    )
    if key in _MARKET_MEMO:
        _MARKET_MEMO.move_to_end(key)
        return _MARKET_MEMO[key]
    refusal = _admission(table, context.approval, context.archive)
    tips = _Tips(dataset, instrument)
    trades = _Trades(dataset, instrument)
    days: tuple[GovernedPaperRiskCvarDay, ...] = ()
    segments: tuple[GovernedPaperRiskCvarSegment, ...] = ()
    units: tuple[tuple[int, Fraction, Fraction], ...] = ()
    liquidity: tuple[GovernedPaperRiskLiquidityEntry, ...] = ()
    spreads: tuple[tuple[int, Fraction | None], ...] = ()
    t8: tuple[GovernedPaperRiskT8Interval, ...] = ()
    if not refusal:
        days, segments, units = _cvar_facts(context.policy, context.archive, start_ns, horizon_ns)
        first, last = start_ns // _V3 - _CLASS_MARGIN, (horizon_ns - 1) // _V3
        observations, grid = _observations(tips, trades, first - _BASELINE, last)
        liquidity = governed_paper_risk_liquidity_entries(observations, first=first, last=last)
        spreads = tuple(sorted(grid.items()))
        t8 = governed_paper_risk_t8_intervals(liquidity, start_ns=start_ns, horizon_ns=horizon_ns)
    market = GovernedPaperRiskMarket(
        policy_digest=digests[0],
        approval_digest=digests[1],
        approval_kind=context.approval.approval_kind,
        approval_table_id=table.table_id,
        approval_admitted=not refusal,
        approval_reason=refusal,
        archive_digest=digests[2],
        mark_source_digest=context.archive.source_digest,
        dataset_digest=digests[3],
        instrument=instrument,
        start_ns=start_ns,
        horizon_ns=horizon_ns,
        book_series_id=tips.series,
        book_series_reason=tips.reason,
        trade_series_id=trades.series,
        trade_series_reason=trades.reason,
        cvar_days=days,
        cvar_segments=segments,
        cvar_units=units,
        liquidity=liquidity,
        spreads=spreads,
        t8_intervals=t8,
        tips=tips,
    )
    _MARKET_MEMO[key] = market
    while len(_MARKET_MEMO) > _MEMO_SIZE:
        _MARKET_MEMO.popitem(last=False)
    return market


def governed_paper_risk_fill_bounds(market: GovernedPaperRiskMarket) -> tuple[HistoricalExecutionCvarBound, ...]:
    """The schedule v7 CVaR bounds of an evaluation: one per readable span, with the exact unit CVaR99* of each side."""

    if type(market) is not GovernedPaperRiskMarket:
        raise _fail("market_malformed")
    units = {end: (long, short) for end, long, short in market.cvar_units}
    return tuple(
        HistoricalExecutionCvarBound(
            window_start_ns=item.start_ns,
            window_end_ns=item.end_ns,
            long_unit_cvar=str(units[item.series_end_ns][0]),  # type: ignore[index]
            short_unit_cvar=str(units[item.series_end_ns][1]),  # type: ignore[index]
        )
        for item in market.cvar_segments
        if not item.reason
    )


# --- the readings of one decision ------------------------------------------------------------------------------------------

_P, _F, _B, _N = (
    GovernedPaperRiskStatus.PASS,
    GovernedPaperRiskStatus.FAIL,
    GovernedPaperRiskStatus.BLOCKED,
    GovernedPaperRiskStatus.PROVEN_NOT_APPLICABLE,
)


def _check(
    check_id: str, status: GovernedPaperRiskStatus, observed: str, reason: str, evidence: tuple[str, ...] = ()
) -> GovernedPaperRiskCheckReading:
    return GovernedPaperRiskCheckReading(check_id, status, observed, reason, evidence)


@dataclass(frozen=True)
class _Facts:
    """The exact facts of one decision the readings share (derived from the decision's own snapshot and re-run)."""

    snapshot: HistoricalExecutionDecisionPortfolioSnapshot | None
    quantity: Fraction | None
    candidate: Fraction | None
    entry: bool
    mark: Fraction | None
    nav: Fraction | None
    nav_reason: str
    candidate_nav: Fraction | None
    candidate_nav_reason: str


def _facts(
    snapshot: HistoricalExecutionDecisionPortfolioSnapshot | None,
    exact: HistoricalExecutionDecisionExactValues | None,
    fee_bps: Fraction,
) -> _Facts:
    if snapshot is None:
        return _Facts(None, None, None, False, None, None, "governed_portfolio_not_computed", None, "")
    quantity, candidate = Fraction(snapshot.position_quantity), Fraction(snapshot.candidate_position_quantity)
    entry = abs(candidate) > abs(quantity)
    mark = None if snapshot.mark_price is None else Fraction(snapshot.mark_price)
    nav: Fraction | None = None
    nav_reason = f"nav_unavailable:{snapshot.nav_reason}"
    if snapshot.nav is not None:
        if exact is None or exact.nav is None or historical_execution_render_amount(exact.nav) != snapshot.nav:
            nav_reason = "exact_nav_not_of_the_snapshot"
        else:
            nav, nav_reason = exact.nav, ""
    candidate_nav: Fraction | None = None
    candidate_reason = f"candidate_nav_unavailable:{snapshot.candidate_nav_reason}"
    if entry and nav is not None and mark is not None and snapshot.candidate_nav is not None:
        projected = nav - abs(candidate - quantity) * mark * fee_bps / 10_000
        if historical_execution_render_amount(projected) != snapshot.candidate_nav:
            candidate_reason = "candidate_nav_not_reproducible"
        else:
            candidate_nav, candidate_reason = projected, ""
    return _Facts(snapshot, quantity, candidate, entry, mark, nav, nav_reason, candidate_nav, candidate_reason)


@dataclass(frozen=True)
class _Protection:
    stop: Fraction | None
    reason: str
    evidence: tuple[str, ...]


def _armed_stop(
    protections: Sequence[HistoricalExecutionExcursionProtection],
    *,
    time_ns: int,
    quantity: Fraction,
    pm_policy: HistoricalPositionManagementPolicy,
    pm_archive: HistoricalOhlcBarArchive,
) -> _Protection:
    """R-1 of the open position at a decision: the armed milestone-0 stop of its excursion, re-derived exactly (the basis
    on the price grid, the ATR re-computed at its own instant), or why none is proven."""

    open_ = [
        item
        for item in protections
        if item.opened_at_ns < time_ns and (item.closed_at_ns is None or item.closed_at_ns >= time_ns)
    ]
    if len(open_) != 1:
        return _Protection(None, "no_armed_stop_of_the_open_position", ())
    protection = open_[0]
    sign = 1 if quantity > 0 else -1
    if protection.direction != ("LONG" if sign > 0 else "SHORT"):
        return _Protection(None, "armed_stop_of_another_direction", ())
    reading = historical_ohlc_wilder_atr(
        pm_archive,
        interval_ns=pm_policy.atr_interval_ns,
        at_ns=protection.atr_at_ns,
        max_bar_age_ns=pm_policy.atr_max_bar_age_ns,
    )
    if (
        not reading.available
        or reading.rendered_value != protection.atr_value
        or reading.window_digest != protection.atr_window_digest
    ):
        return _Protection(None, "armed_stop_atr_not_reproducible", ())
    basis = Fraction(protection.basis_price)
    stop = basis - sign * min(STOP_ATR_MULTIPLE * reading.value, INITIAL_STOP_FRACTION * basis)  # type: ignore[operator]
    levels = [item for item in protection.stop_levels if item.milestone == 0]
    if len(levels) != 1 or historical_execution_render_amount(stop) != levels[0].stop_price:
        return _Protection(None, "armed_stop_not_reproducible", ())
    return _Protection(stop, "", (protection.protection_digest, reading.window_digest))  # type: ignore[arg-type]


def _open_risk(
    facts: _Facts,
    *,
    time_ns: int,
    cost: Fraction,
    pm_policy: HistoricalPositionManagementPolicy,
    pm_archive: HistoricalOhlcBarArchive,
    protections: Sequence[HistoricalExecutionExcursionProtection],
) -> GovernedPaperRiskCheckReading:
    """NT-R03 under FCD-01 (R-4, R-6, R-7)."""

    snapshot = facts.snapshot
    if snapshot is None:
        return _check("NT-R03", _B, "", "governed_portfolio_not_computed")
    evidence = (snapshot.snapshot_digest,)
    if snapshot.order_in_flight:
        return _check("NT-R03", _B, "", "an_order_in_flight", evidence)
    if facts.nav is None:
        return _check("NT-R03", _B, "", facts.nav_reason, evidence)
    if facts.nav <= 0:
        return _check("NT-R03", _B, "", "nav_not_positive", evidence)
    if historical_position_management_initial_stop_fraction(pm_policy) is None:
        return _check("NT-R03", _B, "", "armed_stop_needs_the_policy_v2_r1_stop", evidence)
    quantity, candidate, mark = facts.quantity, facts.candidate, facts.mark
    if facts.entry:
        if quantity != 0:
            return _check("NT-R03", _B, "", "prospective_entry_not_from_flat_has_no_r4_reading", evidence)
        if mark is None:
            return _check("NT-R03", _B, "", "no_fresh_visible_mark", evidence)
        atr = historical_ohlc_wilder_atr(
            pm_archive,
            interval_ns=pm_policy.atr_interval_ns,
            at_ns=time_ns,
            max_bar_age_ns=pm_policy.atr_max_bar_age_ns,
        )
        if not atr.available:
            return _check("NT-R03", _B, "", f"atr_4h_unavailable:{atr.reason}", evidence)
        if facts.candidate_nav is None:
            return _check("NT-R03", _B, "", facts.candidate_nav_reason, evidence)
        if facts.candidate_nav <= 0:
            return _check("NT-R03", _B, "", "candidate_nav_not_positive", evidence)
        sign = 1 if candidate > 0 else -1  # type: ignore[operator]
        stop = mark - sign * min(STOP_ATR_MULTIPLE * atr.value, INITIAL_STOP_FRACTION * mark)  # type: ignore[operator]
        rho = governed_paper_risk_stop_risk(candidate, mark, stop, cost) / facts.candidate_nav  # type: ignore[arg-type]
        evidence = (*evidence, atr.window_digest)  # type: ignore[assignment]
        why = "candidate_open_risk_at_the_r4_stop"
    elif quantity == 0:
        rho, why = Fraction(0), "no_position_and_no_order_in_flight_carry_risk"
    else:
        if mark is None:
            return _check("NT-R03", _B, "", "no_fresh_visible_mark", evidence)
        armed = _armed_stop(protections, time_ns=time_ns, quantity=quantity, pm_policy=pm_policy, pm_archive=pm_archive)  # type: ignore[arg-type]
        if armed.stop is None:
            return _check("NT-R03", _B, "", armed.reason, evidence)
        rho = governed_paper_risk_stop_risk(quantity, mark, armed.stop, cost) / facts.nav  # type: ignore[arg-type]
        evidence = (*evidence, *armed.evidence)  # type: ignore[assignment]
        why = "current_position_open_risk_at_its_armed_stop_reported_r6"
    observed = historical_execution_render_amount(rho)
    if observed is None:
        return _check("NT-R03", _B, "", "open_risk_unrepresentable", evidence)
    if rho > _RHO_CAP:
        return _check("NT-R03", _F, observed, f"{why}_strictly_above_4pct_of_equity", evidence)
    return _check("NT-R03", _P, observed, f"{why}_within_4pct_of_equity", evidence)


def _cvar_unit(
    market: GovernedPaperRiskMarket, time_ns: int
) -> tuple[str, int | None, Fraction | None, Fraction | None]:
    """C-1 at ``time_ns``: ``(reason, series end, long unit, short unit)`` from the span containing it."""

    units = {end: (long, short) for end, long, short in market.cvar_units}
    for item in market.cvar_segments:
        if item.start_ns <= time_ns < item.end_ns:
            if item.reason:
                return item.reason, None, None, None
            long, short = units[item.series_end_ns]  # type: ignore[index]
            return "", item.series_end_ns, long, short
    return "cvar_history_insufficient", None, None, None  # pragma: no cover - the spans tile the evaluation


def _scaled(unit: tuple[Fraction, Fraction], quantity: Fraction, mark: Fraction, equity: Fraction) -> Fraction:
    if quantity == 0:
        return Fraction(0)
    return (unit[0] if quantity > 0 else unit[1]) * abs(quantity) * mark / equity


def _cvar_checks(  # noqa: C901, PLR0912 - one linear reading of the §1.18 checks of one decision
    facts: _Facts,
    market: GovernedPaperRiskMarket,
    *,
    time_ns: int,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    single_instrument: bool,
) -> tuple[list[GovernedPaperRiskCheckReading], Fraction | None, str, tuple[str, ...]]:
    """NT-R05, HZ-CVAR, EDGE-CVAR, MARGINAL-CVAR, STRESS-HV, STRESS-CORR and STRESS-LIQ, S3 and the C-18 duties."""

    reason, series, long, short = _cvar_unit(market, time_ns)
    evidence: tuple[str, ...] = ()
    if series is not None:
        day = next(item for item in market.cvar_days if item.series_end_ns == series)
        evidence = (day.closes_digest, day.seed)
    edge = _check("EDGE-CVAR", _B, "", "edge_cvar_budget_needs_fcd_17_kmax_external_adv_and_h_e_pending")
    marginal = _check("MARGINAL-CVAR", _B, "", "marginal_cvar_rule_needs_a_defined_edge_budget")
    correlation = (
        _check("STRESS-CORR", _N, "", "single_instrument_paper_portfolio_has_no_correlation_to_stress")
        if single_instrument
        else _check("STRESS-CORR", _B, "", "cross_asset_correlation_stress_not_measured")
    )
    holdings = facts.candidate if facts.entry else facts.quantity
    equity = facts.candidate_nav if facts.entry else facts.nav
    equity_reason = facts.candidate_nav_reason if facts.entry else facts.nav_reason
    severity, severity_reason = _cvar_severity(facts, reason, (long, short))  # type: ignore[arg-type]
    blocked: str = ""
    if facts.snapshot is None:
        blocked = "governed_portfolio_not_computed"
    elif reason:
        blocked = reason
    elif equity is None:
        blocked = equity_reason
    elif equity <= 0:
        blocked = "nav_not_positive"
    elif holdings != 0 and facts.mark is None:
        blocked = "no_fresh_visible_mark"
    if blocked:
        checks = [
            _check("NT-R05", _B, "", blocked, evidence),
            _check("HZ-CVAR", _B, "", blocked, evidence),
            edge,
            marginal,
            _check("STRESS-HV", _B, "", blocked, evidence),
            correlation,
            _check("STRESS-LIQ", _B, "", blocked, evidence),
        ]
        return checks, severity, severity_reason, ()
    cvar = _scaled((long, short), holdings, facts.mark or Fraction(0), equity)  # type: ignore[arg-type]
    observed = historical_execution_render_amount(cvar)
    if observed is None:
        unrepresentable = "cvar_unrepresentable"
        return (
            [
                _check("NT-R05", _B, "", unrepresentable, evidence),
                _check("HZ-CVAR", _B, "", unrepresentable, evidence),
                edge,
                marginal,
                _check("STRESS-HV", _B, "", unrepresentable, evidence),
                correlation,
                _check("STRESS-LIQ", _B, "", unrepresentable, evidence),
            ],
            severity,
            severity_reason,
            (),
        )
    nt_r05 = (
        _check("NT-R05", _F, observed, "portfolio_cvar99_at_or_above_5pct_of_nav", evidence)
        if cvar >= _CVAR_BUDGET
        else _check("NT-R05", _P, observed, "portfolio_cvar99_below_5pct_of_nav", evidence)
    )
    horizon = (
        _check("HZ-CVAR", _F, observed, "intraday_horizon_cvar99_at_or_above_2pct_of_nav_hzb_1", evidence)
        if cvar >= _HZ_CVAR_LIMIT
        else _check("HZ-CVAR", _P, observed, "intraday_horizon_cvar99_below_2pct_of_nav_hzb_1", evidence)
    )
    stressed = _STRESS_HV_MULTIPLE * cvar
    hv_observed = historical_execution_render_amount(stressed) or ""
    hv = (
        _check("STRESS-HV", _F, hv_observed, "high_vol_stress_cvar99_at_or_above_8pct_of_nav", evidence)
        if stressed >= _STRESS_LIMIT
        else _check("STRESS-HV", _P, hv_observed, "high_vol_stress_cvar99_below_8pct_of_nav", evidence)
    )
    liq = _stress_liquidity(market, cvar, holdings, equity, time_ns, economics_policy, evidence)  # type: ignore[arg-type]
    # C-18: "if any stress CVaR99 exceeds 8% of NAV -> de-risk immediately" (§1.18) is an obligation nothing represents
    obligations = (_DE_RISK_DUTY,) if _F in (hv.status, liq.status) else ()
    return [nt_r05, horizon, edge, marginal, hv, correlation, liq], severity, severity_reason, obligations


_DE_RISK_DUTY = "section_1_18_stress_cvar99_at_or_above_8pct_de_risk_immediately:BLOCKED_UNREPRESENTABLE"


def _cvar_severity(
    facts: _Facts, reason: str, unit: tuple[Fraction | None, Fraction | None]
) -> tuple[Fraction | None, str]:
    """C-11, C-20: S3 = ``min(1, max(0, CVaR99* / 0.05))`` of the current holdings over the exact NAV, or why it is
    unmeasured."""

    if facts.snapshot is None:
        return None, "governed_portfolio_not_computed"
    if reason:
        return None, reason
    if facts.nav is None:
        return None, facts.nav_reason
    if facts.nav <= 0:
        return None, "nav_not_positive"
    if facts.quantity != 0 and facts.mark is None:  # pragma: no cover - a NAV of an open position needs its mark
        return None, "no_fresh_visible_mark"
    current = _scaled(unit, facts.quantity, facts.mark or Fraction(0), facts.nav)  # type: ignore[arg-type]
    return min(Fraction(1), max(Fraction(0), current / _CVAR_BUDGET)), ""


def _stress_liquidity(  # noqa: PLR0913
    market: GovernedPaperRiskMarket,
    cvar: Fraction,
    holdings: Fraction,
    equity: Fraction,
    time_ns: int,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    evidence: tuple[str, ...],
) -> GovernedPaperRiskCheckReading:
    """STRESS-LIQ with LS-A: the fresh depth-50 tip at ``t``, quantities x 1/5, the whole holding as one close-only
    order under the bound fill model; FAIL at or above 8% or when the order cannot fill the whole holding."""

    tips: _Tips = market.tips  # type: ignore[assignment]
    if market.book_series_reason:
        return _check("STRESS-LIQ", _B, "", market.book_series_reason, evidence)
    tip = tips.at(time_ns)
    if tip is None:
        return _check("STRESS-LIQ", _B, "", "no_fresh_depth_50_tip_at_the_decision", evidence)
    levels = tips.levels(tip.record)
    if levels is None:
        return _check("STRESS-LIQ", _B, "", "order_book_tip_malformed", evidence)
    bids, asks = levels
    unit = Fraction(1, 10**18)
    reason, cost = historical_execution_close_only_exit_quote(
        economics_policy,
        position_quantity=holdings,
        best_bid_price=bids[0][0] * unit,
        best_ask_price=asks[0][0] * unit,
        best_bid_quantity=bids[0][1] * unit,
        best_ask_quantity=asks[0][1] * unit,
        depth_multiplier=_STRESS_DEPTH,
    )
    evidence = (*evidence, tip.record.record_digest)
    if reason.startswith("economic_value_out_of_representation"):
        return _check("STRESS-LIQ", _B, "", f"stressed_exit_unrepresentable:{reason}", evidence)
    if reason:
        return _check("STRESS-LIQ", _F, "", f"stressed_book_cannot_fill_the_whole_holding:{reason}", evidence)
    stressed = cvar + cost / equity  # type: ignore[operator]
    observed = historical_execution_render_amount(stressed)
    if observed is None:
        return _check("STRESS-LIQ", _B, "", "stressed_liquidity_cvar_unrepresentable", evidence)
    if stressed >= _STRESS_LIMIT:
        return _check("STRESS-LIQ", _F, observed, "liquidity_stress_cvar99_at_or_above_8pct_of_nav", evidence)
    return _check("STRESS-LIQ", _P, observed, "liquidity_stress_cvar99_below_8pct_of_nav", evidence)


def _spread_checks(market: GovernedPaperRiskMarket, time_ns: int) -> tuple[GovernedPaperRiskCheckReading, ...]:
    """NT-X03 and OB-SPREAD at ``t`` (X-1..X-6)."""

    if market.book_series_reason:
        reason = market.book_series_reason
        return _check("NT-X03", _B, "", reason), _check("OB-SPREAD", _B, "", reason)
    tips: _Tips = market.tips  # type: ignore[assignment]
    tip = tips.at(time_ns)
    current: Fraction | None = None
    current_reason = "no_fresh_depth_50_tip_at_the_decision"
    evidence: tuple[str, ...] = ()
    if tip is not None:
        evidence = (tip.record.record_digest,)
        levels = tips.levels(tip.record)
        if levels is None:
            current_reason = "order_book_tip_malformed"
        elif levels[0][0][0] >= levels[1][0][0]:
            current_reason = "current_tip_crossed_or_locked"
        else:
            bid, ask = levels[0][0][0], levels[1][0][0]
            current, current_reason = Fraction(2 * (ask - bid), bid + ask), ""
    spreads = dict(market.spreads)
    newest = (time_ns - 1) // _V3  # g_1: the latest grid instant strictly before t
    baseline = [spreads.get(index) for index in range(newest - _BASELINE + 1, newest + 1)]
    x03, ob = governed_paper_risk_spread_checks(current, current_reason, baseline)
    return _check("NT-X03", *x03, evidence), _check("OB-SPREAD", *ob, evidence)


def _decision_reading(  # noqa: PLR0913
    market: GovernedPaperRiskMarket,
    decision: tuple[int, int, str],
    *,
    snapshot: HistoricalExecutionDecisionPortfolioSnapshot | None,
    exact: HistoricalExecutionDecisionExactValues | None,
    outcome: HistoricalExecutionGovernedPaperOutcome | None,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    pm_policy: HistoricalPositionManagementPolicy,
    pm_archive: HistoricalOhlcBarArchive,
    single_instrument: bool,
) -> GovernedPaperRiskReading:
    sequence, time_ns, direction = decision
    if not market.approval_admitted:
        refusal = f"risk_policy_not_admitted:{market.approval_reason}"
        seed = GovernedPaperRiskReading(
            sequence,
            time_ns,
            direction,
            tuple(_check(item, _B, "", refusal) for item in GOVERNED_PAPER_RISK_CHECK_IDS),
            None,
            refusal,
            None,
            refusal,
            (),
            "",
        )
        return replace(seed, reading_digest=edge_payload_digest(_to_payload(seed), "reading_digest"))
    fee_bps = Fraction(economics_policy.taker_fee_bps)
    cost = (fee_bps + Fraction(economics_policy.slippage_floor_bps)) / 10_000
    facts = _facts(snapshot, exact, fee_bps)
    simulated = outcome is not None and outcome.simulated is True
    protections = outcome.excursion_protections if simulated else ()  # type: ignore[union-attr]
    open_risk = _open_risk(
        facts, time_ns=time_ns, cost=cost, pm_policy=pm_policy, pm_archive=pm_archive, protections=protections
    )
    cvar_checks, severity, severity_reason, obligations = _cvar_checks(
        facts, market, time_ns=time_ns, economics_policy=economics_policy, single_instrument=single_instrument
    )
    status, observed, reason, evidence = governed_paper_risk_nt_m01(market.liquidity, time_ns)
    nt_m01 = _check("NT-M01", status, observed, reason, evidence)
    liquidity, liquidity_reason = governed_paper_risk_liquidity_severity(market.liquidity, time_ns)
    x03, ob = _spread_checks(market, time_ns)
    starts = (
        tuple(item.start_time_ns for item in outcome.trades)  # type: ignore[union-attr]
        if simulated
        else None
    )
    # without a snapshot an order in flight is not excluded, so it is counted as one possible trade more
    turnover = _check(
        "HZ-TURNOVER",
        *governed_paper_risk_turnover(starts, time_ns, order_in_flight=snapshot is None or snapshot.order_in_flight),
    )
    by_id = {item.check_id: item for item in (open_risk, nt_m01, x03, ob, turnover, *cvar_checks)}
    severity_text = None if severity is None else _exact(severity)
    liquidity_text = None if liquidity is None else _exact(liquidity)
    seed = GovernedPaperRiskReading(
        decision_sequence=sequence,
        decision_time_ns=time_ns,
        target_direction=direction,
        checks=tuple(by_id[item] for item in GOVERNED_PAPER_RISK_CHECK_IDS),
        cvar_severity=severity_text,
        cvar_severity_reason=severity_reason
        if severity is None
        else ("" if severity_text is not None else "cvar_severity_unrepresentable"),
        liquidity_severity=liquidity_text,
        liquidity_severity_reason=liquidity_reason
        if liquidity is None
        else ("" if liquidity_text is not None else "liquidity_severity_unrepresentable"),
        obligations=obligations,
        reading_digest="",
    )
    return replace(seed, reading_digest=edge_payload_digest(_to_payload(seed), "reading_digest"))


def _canonical_decisions(decisions: object, start_ns: int, horizon_ns: int) -> tuple[tuple[int, int, str], ...]:
    if type(decisions) is not tuple:
        raise _fail("decisions_malformed")
    previous: tuple[int, int] | None = None
    for item in decisions:
        if (
            type(item) is not tuple
            or len(item) != 3  # noqa: PLR2004 - (sequence, instant, direction)
            or not historical_execution_wire_int_is_valid(item[0], minimum=0)
            or not historical_execution_wire_int_is_valid(item[1], minimum=0)
            or type(item[2]) is not str
            or item[2] not in ("LONG", "SHORT")
        ):
            raise _fail("decisions_malformed")
        if not start_ns <= item[1] < horizon_ns:
            raise _fail("decision_outside_the_evaluation_horizon")
        if previous is not None and (item[0] <= previous[0] or item[1] < previous[1]):
            raise _fail("decisions_not_ordered")
        previous = (item[0], item[1])
    return decisions  # type: ignore[return-value]


def derive_governed_paper_risk_evidence(  # noqa: PLR0913
    context: GovernedPaperRiskContext,
    *,
    dataset: HistoricalPitDataset,
    instrument: str,
    start_ns: int,
    horizon_ns: int,
    decisions: tuple[tuple[int, int, str], ...],
    snapshots: dict[int, HistoricalExecutionDecisionPortfolioSnapshot],
    exact_values: dict[int, HistoricalExecutionDecisionExactValues],
    outcome: HistoricalExecutionGovernedPaperOutcome | None,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
    single_instrument_portfolio: bool,
) -> GovernedPaperRiskEvidence:
    """The risk evidence of one governed evaluation: the market facts of ``[start_ns, horizon_ns)`` and the readings of
    every entry decision ``(sequence, instant, direction)``, each on its own snapshot, the exact values behind it and the
    governed outcome of the same one engine re-run (the caller's own derivation, never a supplied artifact). The
    economics policy, the position-management policy and its archive are the economics' own, re-proven by the caller.
    A malformed, foreign or non-authentic input raises ``GovernedPaperRiskError``. Pure."""

    market = derive_governed_paper_risk_market(
        context, dataset=dataset, instrument=instrument, start_ns=start_ns, horizon_ns=horizon_ns
    )
    entries = _canonical_decisions(decisions, start_ns, horizon_ns)
    if type(snapshots) is not dict or type(exact_values) is not dict:
        raise _fail("governed_run_malformed")
    if outcome is not None and type(outcome) is not HistoricalExecutionGovernedPaperOutcome:
        raise _fail("governed_outcome_malformed")
    if (
        type(economics_policy) is not HistoricalExecutionEconomicsPolicy
        or type(position_management_policy) is not HistoricalPositionManagementPolicy
        or type(position_management_archive) is not HistoricalOhlcBarArchive
        or type(single_instrument_portfolio) is not bool
    ):
        raise _fail("economics_inputs_malformed")
    readings = tuple(
        _decision_reading(
            market,
            item,
            snapshot=snapshots.get(item[0]),
            exact=exact_values.get(item[0]),
            outcome=outcome,
            economics_policy=economics_policy,
            pm_policy=position_management_policy,
            pm_archive=position_management_archive,
            single_instrument=single_instrument_portfolio,
        )
        for item in entries
    )
    seed = GovernedPaperRiskEvidence(
        schema_version=GOVERNED_PAPER_RISK_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_RISK_CONTRACT_ID,
        decision_id=GOVERNED_PAPER_RISK_DECISION_ID,
        policy_digest=market.policy_digest,
        approval_digest=market.approval_digest,
        approval_kind=market.approval_kind,
        approval_table_id=market.approval_table_id,
        approval_admitted=market.approval_admitted,
        approval_reason=market.approval_reason,
        archive_digest=market.archive_digest,
        mark_source_digest=market.mark_source_digest,
        dataset_digest=market.dataset_digest,
        economics_policy_digest=economics_policy.policy_digest,
        position_management_policy_digest=position_management_policy.policy_digest,
        instrument=instrument,
        start_ns=start_ns,
        horizon_ns=horizon_ns,
        book_series_id=market.book_series_id,
        book_series_reason=market.book_series_reason,
        trade_series_id=market.trade_series_id,
        trade_series_reason=market.trade_series_reason,
        cvar_days=market.cvar_days,
        cvar_segments=market.cvar_segments,
        liquidity=market.liquidity,
        t8_intervals=market.t8_intervals,
        readings=readings,
        evidence_digest="",
        synthetic_risk_approval_used=market.approval_admitted
        and market.approval_kind is GovernedPaperRiskApprovalKind.TEST_ONLY_SYNTHETIC,
    )
    return replace(seed, evidence_digest=governed_paper_risk_evidence_digest(seed))


def governed_paper_risk_evidence_to_dict(evidence: GovernedPaperRiskEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_risk_evidence_digest(evidence: GovernedPaperRiskEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), "evidence_digest")


def governed_paper_risk_reading_digest(reading: GovernedPaperRiskReading) -> str:
    """Recompute the canonical reading digest, excluding only ``reading_digest``."""

    return edge_payload_digest(_to_payload(reading), "reading_digest")


def governed_paper_risk_prefix_digest(evidence: GovernedPaperRiskEvidence, *, before_ns: int) -> str:
    """The run-independent X1 content before ``before_ns``: the policy, approval and admission, every C-1 span opened
    before it (its end clipped there) with the days those spans read, and every LIQ reading known before it. A later seal
    of the lineage re-derives it unchanged: nothing known before ``before_ns`` ever changes (L-9)."""

    if type(evidence) is not GovernedPaperRiskEvidence:
        raise _fail("evidence_malformed")
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("prefix_instant_invalid")
    segments = [
        {**_to_payload(item), "end_ns": min(item.end_ns, before_ns)}
        for item in evidence.cvar_segments
        if item.start_ns < before_ns
    ]
    read = {item["series_end_ns"] for item in segments}
    payload = {
        "schema_version": evidence.schema_version,
        "policy_digest": evidence.policy_digest,
        "approval_digest": evidence.approval_digest,
        "approval_table_id": evidence.approval_table_id,
        "approval_admitted": evidence.approval_admitted,
        "cvar_segments": segments,
        "cvar_days": [_to_payload(item) for item in evidence.cvar_days if item.series_end_ns in read],
        "liquidity": [
            _to_payload(item)
            for item in evidence.liquidity
            if item.knowledge_ns is not None and item.knowledge_ns < before_ns
        ],
    }
    return _digest_of(payload)


__all__ = [
    "GOVERNED_PAPER_RISK_APPROVAL_SCHEMA",
    "GOVERNED_PAPER_RISK_APPROVED_ITEMS",
    "GOVERNED_PAPER_RISK_CHECK_IDS",
    "GOVERNED_PAPER_RISK_CONTRACT_ID",
    "GOVERNED_PAPER_RISK_DECISION_ID",
    "GOVERNED_PAPER_RISK_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_RISK_HORIZON_SHARES",
    "GOVERNED_PAPER_RISK_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_RISK_PENDING_ITEMS",
    "GOVERNED_PAPER_RISK_POLICY_SCHEMA",
    "GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE",
    "GOVERNED_PAPER_RISK_RULE",
    "GOVERNED_PAPER_RISK_RULE_DIGEST",
    "GovernedPaperRiskApproval",
    "GovernedPaperRiskApprovalKind",
    "GovernedPaperRiskApprovalTable",
    "GovernedPaperRiskCheckReading",
    "GovernedPaperRiskContext",
    "GovernedPaperRiskCvarDay",
    "GovernedPaperRiskCvarEstimate",
    "GovernedPaperRiskCvarSegment",
    "GovernedPaperRiskError",
    "GovernedPaperRiskEvidence",
    "GovernedPaperRiskLiquidityEntry",
    "GovernedPaperRiskMarket",
    "GovernedPaperRiskObservation",
    "GovernedPaperRiskPolicy",
    "GovernedPaperRiskReading",
    "GovernedPaperRiskStatus",
    "GovernedPaperRiskT8Interval",
    "build_governed_paper_risk_approval",
    "build_governed_paper_risk_policy",
    "derive_governed_paper_risk_evidence",
    "derive_governed_paper_risk_market",
    "governed_paper_risk_approval_digest",
    "governed_paper_risk_cvar_star",
    "governed_paper_risk_evidence_digest",
    "governed_paper_risk_evidence_to_dict",
    "governed_paper_risk_fill_bounds",
    "governed_paper_risk_horizon_cvar_limit",
    "governed_paper_risk_liquidity_entries",
    "governed_paper_risk_liquidity_severity",
    "governed_paper_risk_mc_ages",
    "governed_paper_risk_mc_seed",
    "governed_paper_risk_nt_m01",
    "governed_paper_risk_policy_digest",
    "governed_paper_risk_prefix_digest",
    "governed_paper_risk_reading_digest",
    "governed_paper_risk_rule",
    "governed_paper_risk_spread_checks",
    "governed_paper_risk_stop_risk",
    "governed_paper_risk_t8_intervals",
    "governed_paper_risk_tip_reading",
    "governed_paper_risk_turnover",
    "governed_paper_risk_weighted_es",
    "verify_governed_paper_risk_approval",
    "verify_governed_paper_risk_policy",
]
