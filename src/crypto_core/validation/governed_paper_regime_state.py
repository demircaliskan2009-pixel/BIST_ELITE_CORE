"""Governed paper regime state (``S1_FAMILY_B_REGIME_TREND_ACTIVATION_GATE_CLOSURE_V1``): the frozen PRDV4 §1.5 / §1.9
Family B regime, trend and activation evidence that the S1 entry gate reads under rule set v6.

Methodology authority: ``S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1`` revision r2 (2026-11-02). The human approved its
items CL1-1..CL1-13 and CL2-1..CL2-11 for CONSTRUCTION; CL1-14, CL2-12 and CL2-13 are excluded. This module implements
CL1-1..CL1-13 and CL2-1..CL2-7. A design approval is not production permission: every NEW value here is an uncalibrated
governance choice, and the price-CRISIS rule guarantees no crisis coverage. Paper-only, deterministic, point-in-time and
fail-closed. Arithmetic is exact (integers and ``Fraction``; no float, no ``decimal`` context), and there is no IO,
clock, randomness, network or environment.

Authority chain (derived, never accepted):

* ``GovernedPaperRegimePolicy`` v1 carries every NEW constant of the approved methodology. This module fixes them. Only
  the policy id, the instrument and the bound MARK bar source are chosen, so a policy with any other value never
  verifies.
* ``GovernedPaperRegimeApproval`` binds the policy digest and the approved items. The approval table decides whether the
  approval may be used:
  - the PRODUCTION table admits only a HUMAN_GOVERNANCE approval of a policy digest that a separate human authorization
    lists. It lists none, so production verification refuses every approval and every regime check stays BLOCKED;
  - a TEST-ONLY table, installed by tests alone, admits only TEST_ONLY_SYNTHETIC approvals, and every evidence derived
    under it says so (``synthetic_regime_approval_used``).
* The bars are those of the authenticated ``HistoricalOhlcBarArchive`` of the bound source: MARK_PRICE bars of the
  300 s interval of the instrument. An hourly bar is the exact aggregation of the twelve 5-minute bars of a UTC hour (max
  high, min low, last close); a declared 3600 s interval is ignored.
* The books are the ORDER_BOOK depth-50 tips of the dataset. They are re-proven on the dataset's own EF-3 manifest,
  with the registry semantics of their only producer (``authenticated_pit_ingress``).

Frozen knowledge instants (CL1-3, A3/I4 r2).
* Evaluation ``m`` classifies the window ending at the 5-minute bar that closes at ``g_m = m x 300 s``.
* It is computed once, at its knowledge instant ``kappa(m) = g_m + 300 s``, from the bars visible then
  (``max(available_at, finalized_at) <= kappa(m)``), and it is never revised. A bar visible later enters only the
  evaluations whose knowledge instant follows its visibility, and a bar missing at ``kappa(m)`` leaves evaluation ``m``
  UNKNOWN for good.
* A book sample at instant ``s`` reads only the records visible at ``s``: the latest tip by native event time, and only
  when it is fresh within 10 s (the NT-D02 reading at ``s``).
* A decision at ``t`` reads evaluation ``n(t) = max{m : kappa(m) <= t}``, so its information is 300-600 s old.
* ``kappa`` lies on the 10-second grid, so the 10-second state record is exactly the step function of the evaluations
  (``governed_paper_regime_state_at``). Nothing inside a bar, or after ``g_n``, is claimed.

One evaluation ``m``. Thresholds are strict as PRDV4 states them, and an equality goes to the higher bucket.
* D-PC2 PRICE_CRISIS_V1 (CL1-2; kind COMPLETE; NEW and uncalibrated): a witness is a pair of MARK closes ``C_i, C_j``
  with ``m - 288 <= i < j <= m``, ``j - i <= 12`` and ``20 C_j > 23 C_i`` or ``20 C_j < 17 C_i``, so the move is strictly
  beyond ±15% within an hour of the trailing 24 h. It borrows only the 15% number from PRDV4 §1.19 T10 (a BTC 5-minute
  kill-switch trigger), which stays separate and unmeasured here.
* D-PC1 (CL1-1): PROVEN_CRISIS needs one witness whose two closes are visible at ``kappa(m)``. PROVEN_NON_CRISIS needs
  all 289 closes visible and no witness. Anything else is UNKNOWN; not observing a crisis never proves its absence.
* A4 (CL1-5): ``sigma_r`` uses the 24 simple returns of the closes ``C_{m-24..m}``, with ``s^2 = sum((r - mean)^2) / 23``.
  The buckets are LOW ``s^2 < 1/40000``, MED ``< 9/40000``, HIGH ``< 49/40000``, and EXTREME otherwise.
* A7 (CL1-6): TS reads the 192 hourly bars ending at the latest UTC hour that closes at or before ``g_m``.
  - ``EMA_N`` is the normalized EMA over ``4N`` closes, with ``alpha = 2 / (N + 1)`` and ``N`` in {12, 48}.
  - ``ATR24`` is the mean of the last 24 hourly true ranges.
  - TS is strong iff ``2 |EMA12 - EMA48| > 3 ATR24``. ``ATR24 = 0`` leaves TS unavailable.
* A1 (CL1-4): the base set is {TRENDING} when TS is strong. Otherwise it is {HIGH_VOL} for a HIGH or EXTREME bucket and
  {RANGE} below that, with every completion kept while an input is unknown. The possible classes are {CRISIS} (proven),
  the base set (proven non-crisis), or both (UNKNOWN). The label is the single possible class, else UNKNOWN.
* A5 (CL1-10): the depth ``D(s)`` is the quote notional of the bid levels at or above ``mid x 999/1000`` and of the ask
  levels at or below ``mid x 1001/1000``. It is known only when the book is fresh and not crossed, and when its 50th
  levels lie strictly beyond that band on both sides. ``L = D(g_m) / mean(D(g_{m-0..287}))``, read against DRY < 3/10,
  THIN < 7/10, NORMAL <= 3/2 and DEEP.
* A6 (CL1-11): the spread is the CV of the six relative spreads ``(ask - bid) / mid`` at ``g_{m-0..5}``, read against
  STABLE < 1/2, WIDENING < 3/2 and BLOWN.
* A8 (CL1-7): the confirmed state ``S(m)`` is the label of the latest run of three equal labels whose last element lies in
  ``[m - 287, m]`` (UNKNOWN when there is none). A transition is pending while the label differs from it. A transition
  is ``S(e) != S(e - 1)``. Four transitions within 288 evaluations force FORCED_DEFENSIVE on the next 72 evaluations
  (I5: per dimension; this is never a price-CRISIS proof).

The log covers every evaluation from ``n(G) - 648`` to the last one whose knowledge instant precedes the horizon. Its
labels are derived from 648 evaluations further back. It depends on the genesis start, the bars, the books and the
policy alone, never on a decision or an admission, so the prefix a day seal binds (``governed_paper_regime_prefix_digest``)
is the same in every later seal of the lineage (X1).

A decision at ``t``, on ``n = n(t)``, receives the readings of the seven rule set v6 checks:
* FB-TREND (A10, CL1-9): a SHORT entry FAILs on a strong upward TS and a LONG entry on a strong downward TS. "Funding is
  extreme" is the Family B entry signal itself, so the check never waits on a separate extremity rule.
* FB-REGIME (CL1-1, CL1-4, CL1-7; I1): it FAILs on the overlay, on a confirmed or current CRISIS or TRENDING, or when no
  possible class is RANGE or HIGH_VOL. It PASSes only when both the confirmed and the current label are RANGE or HIGH_VOL
  and all 649 labels in ``[n - 648, n]`` are definite. Otherwise it is BLOCKED.
* FB-REGIME-COOLDOWN (A9, CL1-8): it FAILs on TRENDING as the label or the confirmed state in ``[n - 95, n]``, and PASSes
  only when all 385 labels in ``[n - 384, n]`` are definite and none is.
* NT-M03 (I7): it FAILs while a price transition is pending. It is otherwise BLOCKED, because the funding, leverage and
  liquidity dimensions are not produced; it never PASSes.
* FB-ACTIVATION (A2, CL1-12; I2): a proven forbidden column FAILs (vol LOW or EXTREME, liquidity DRY, spread BLOWN,
  governed latency >= 300 ms), and an unproven one is BLOCKED. No paper fill-rate or exchange-health proof exists, so
  the execution column is never allowed and the check never PASSes.
* FB-REGIME-CELL (R17, CL2-6; I6): Family B's 90 declared cells are {RANGE, HIGH_VOL} x five funding states x {LOW,
  NORMAL, HIGH leverage} x {DEEP, NORMAL, THIN liquidity}. It FAILs on a proven price state outside them; otherwise it is
  BLOCKED, because leverage and liquidity are not produced. It never PASSes.
* SYSTEM-STATE (R29, CL2-7): Family B is T1 (§1.16), so an entry needs a proven §1.29 SS-0. No system-state engine
  exists, so it is always BLOCKED.

Without an admitted approval, every reading is BLOCKED and the log is empty: an unadmitted policy's methods are never
applied. Non-claims: no venue or source fact, no qualified source, no real market observation, no T10 measurement, no
calibration, no admission, readiness, Stage-4 completion, edge or profitability.
"""

from __future__ import annotations

import bisect
from collections import OrderedDict
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.data.requirements import DataRequirementKey
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
from crypto_core.validation.historical_execution_economics_policy import (
    BEST_ASK_PRICE_NAME,
    BEST_ASK_QUANTITY_NAME,
    BEST_BID_PRICE_NAME,
    BEST_BID_QUANTITY_NAME,
    historical_execution_decimal_is_canonical,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    verify_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    verify_historical_pit_dataset,
)

GOVERNED_PAPER_REGIME_CONTRACT_ID = "S1_FAMILY_B_REGIME_TREND_ACTIVATION_GATE_CLOSURE_V1"
GOVERNED_PAPER_REGIME_METHODOLOGY_ID = "S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1"
GOVERNED_PAPER_REGIME_METHODOLOGY_REVISION = "r2"
# The exact human approval scope (construction only), the items implemented here and the excluded items.
GOVERNED_PAPER_REGIME_APPROVED_ITEMS: tuple[str, ...] = (
    *(f"CL1-{index}" for index in range(1, 14)),
    *(f"CL2-{index}" for index in range(1, 12)),
)
GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS: tuple[str, ...] = (
    *(f"CL1-{index}" for index in range(1, 14)),
    *(f"CL2-{index}" for index in range(1, 8)),
)
GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS: tuple[str, ...] = ("CL1-14", "CL2-12", "CL2-13")
GOVERNED_PAPER_REGIME_POLICY_SCHEMA = "governed-paper-regime-policy.v1"
GOVERNED_PAPER_REGIME_APPROVAL_SCHEMA = "governed-paper-regime-approval.v1"
GOVERNED_PAPER_REGIME_EVIDENCE_SCHEMA = "governed-paper-regime-evidence.v1"
# The rule set v6 checks this module reads, in the gate's evaluation order.
GOVERNED_PAPER_REGIME_CHECK_IDS: tuple[str, ...] = (
    "FB-TREND",
    "FB-REGIME",
    "FB-REGIME-COOLDOWN",
    "NT-M03",
    "FB-ACTIVATION",
    "FB-REGIME-CELL",
    "SYSTEM-STATE",
)

_PREFIX = "governed_paper_regime_state"
_NS = 1_000_000_000
_BAR_NS = 300 * _NS  # the 5-minute MARK bar and the evaluation grid
_HOUR_NS = 3_600 * _NS
_BARS_PER_HOUR = _HOUR_NS // _BAR_NS
_UNIT = 10**18  # one whole unit at the canonical scale 18

# Every NEW constant of the approved methodology (r2); the policy carries them and a verifier re-derives them.
_KNOWLEDGE_DEADLINE_NS = 300 * _NS  # CL1-3: kappa(m) = g_m + 300 s
_CRISIS_UP = Fraction(23, 20)  # CL1-2: strictly above +15%
_CRISIS_DOWN = Fraction(17, 20)  # CL1-2: strictly below -15%
_CRISIS_SPAN = 12  # CL1-2: two closes at most 12 bars (one hour) apart
_CRISIS_WINDOW = 289  # CL1-2: the trailing 289 closes (24 h)
_SIGMA_WINDOW = 25  # CL1-5: 25 closes, 24 simple returns, n - 1 = 23
_EMA_FAST, _EMA_SLOW, _EMA_TRUNCATION, _ATR_HOURS = 12, 48, 4, 24  # CL1-6
_TREND_BOUND = Fraction(3, 2)  # CL1-6: |TS| strictly above 3/2 (PRDV4 §1.9)
_CONFIRMATIONS = 3  # CL1-7: K = 3
_MEMORY = 288  # CL1-7: the run must end within the trailing 288 evaluations
_OVERLAY_TRANSITIONS, _OVERLAY_WINDOW, _OVERLAY_HOLD = 4, 288, 72  # CL1-7: >= 4 in 288 evaluations -> 72 evaluations
_REGIME_PASS_WINDOW = 649  # CL1-7: labels [n - 648, n] definite for FB-REGIME PASS
_COOLDOWN_WINDOW = 96  # CL1-8: (g_n - 8 h, g_n]
_COOLDOWN_PASS_WINDOW = 385  # CL1-8: labels [n - 384, n] definite for FB-REGIME-COOLDOWN PASS
_BOOK_FRESHNESS_NS = 10 * _NS  # CL1-10: the NT-D02 freshness of a book sample
_BAND = Fraction(1, 1_000)  # CL1-10: ±10 bps around the mid
_LIQUIDITY_SAMPLES = 288  # CL1-10
_SPREAD_SAMPLES = 6  # CL1-11
_EXECUTION_FAIL_LATENCY_NS = 300_000_000  # CL1-12: 300 ms proves at least IMPAIRED (§1.5)
# PRDV4 doctrine values (published thresholds, never governed parameters).
_SIGMA_BOUNDS = (Fraction(1, 40_000), Fraction(9, 40_000), Fraction(49, 40_000))  # §1.5 0.005 / 0.015 / 0.035 squared
_LIQUIDITY_BOUNDS = (Fraction(3, 10), Fraction(7, 10), Fraction(3, 2))  # §1.5 DRY / THIN / NORMAL
_SPREAD_BOUNDS = (Fraction(1, 2), Fraction(3, 2))  # §1.5 STABLE / WIDENING
_BOOK_DEPTH = 50  # the producer's ORDER_BOOK depth (registry 1.0)
_DERIVED_BACK = _REGIME_PASS_WINDOW - 1  # 648: the log's first evaluation precedes the first decision by this much
_BAR_HISTORY = 2_316  # bars before a label that its TS can read: 12 x (192 + 1) hourly bars

_PRICE_CRISIS_METHOD = "PRICE_CRISIS_15PCT_WITHIN_1H_OVER_24H_MARK_5M_CLOSES_V1"
_TEMPORAL_METHOD = "I4_A3_R2_FROZEN_KNOWLEDGE_INSTANT_CLOSE_PLUS_300S_10S_STEP_RECORD_V1"
_VOLATILITY_METHOD = "A4_SIGMA_R_SIMPLE_RETURNS_N_MINUS_1_OVER_25_MARK_5M_CLOSES_V1"
_TREND_METHOD = "A7_TS_HOURLY_AGGREGATE_NORMALIZED_EMA_OVER_4N_CLOSES_OVER_MEAN_24_TRUE_RANGES_V1"
_CLASSIFIER_METHOD = "A1_CRISIS_TRENDING_HIGH_VOL_RANGE_POSSIBILITY_LABEL_V1"
_HYSTERESIS_METHOD = "A8_BOUNDED_3_RUN_WITHIN_288_OVERLAY_4_IN_288_HOLD_72_V1"
_COOLDOWN_METHOD = "A9_8H_UNION_96_EVALUATIONS_V1"
_TREND_FILTER_METHOD = "A10_SIGN_ALIGNED_ABS_TS_GT_3_2_ENTRY_SIGNAL_IS_THE_FUNDING_EXTREMITY_V1"
_LIQUIDITY_METHOD = "A5_DEPTH_10BPS_QUOTE_NOTIONAL_288_SAMPLES_AS_KNOWN_AT_S_V1"
_SPREAD_METHOD = "A6_RELATIVE_SPREAD_CV_6_SAMPLES_AS_KNOWN_AT_S_V1"
_EXECUTION_METHOD = "A2_GOVERNED_LATENCY_GE_300MS_FAILS_ELSE_UNPROVEN_V1"
_REGIME_CELLS = (
    ("RANGE", "HIGH_VOL"),
    ("NEGATIVE_EXTREME", "NEGATIVE", "NEUTRAL", "POSITIVE", "POSITIVE_EXTREME"),
    ("LOW_LEVERAGE", "NORMAL", "HIGH_LEVERAGE"),
    ("DEEP", "NORMAL", "THIN"),
)
_INTERPRETATION_RECORDS = (
    "D-PC1:tri_state_price_crisis_proof_complete_or_sufficient_only",
    "I1:unknown_never_admits_a_family_b_entry",
    "I2:a_blown_spread_fails_row_b_no_50pct_allocation",
    "I4:frozen_knowledge_instant_close_plus_300s_10s_step_record_no_intrabar_claim",
    "I5:the_oscillation_overlay_is_per_dimension",
    "I6:the_r17_price_axis_is_the_prdv4_1_5_regime_state",
    "I7:nt_m03_dimensions_are_price_funding_leverage_liquidity",
    "A10:the_funding_extremity_of_fb_trend_is_the_family_b_entry_signal",
)
# The registry 1.0 ORDER_BOOK semantics, exactly as their only producer (``authenticated_pit_ingress``) implements them.
_BOOK_SEMANTICS: tuple[tuple[str, object], ...] = (
    ("registry_requirement_bound", True),
    ("finality", "finalized_only"),
    ("revision_policy", "immutable_after_finalization"),
    ("historical_source", "order_book_snapshot_delta_v1"),
    ("event_time_policy", "book_event_ns"),
    ("available_at_policy", "book_available_ns"),
    ("finalized_at_policy", "book_sequence_finalized_ns"),
    ("order_book_level", "l2"),
    ("order_book_depth", _BOOK_DEPTH),
    ("sequence_policy", "strict_monotonic"),
    ("resync_policy", "snapshot_then_delta"),
    ("finality_policy", "sequence_gap_reject"),
)
_LEVEL_WIDTH = len(str(_BOOK_DEPTH))
_BOOK_NAMES = frozenset(
    {
        BEST_BID_PRICE_NAME,
        BEST_BID_QUANTITY_NAME,
        BEST_ASK_PRICE_NAME,
        BEST_ASK_QUANTITY_NAME,
        *(
            f"{side}_{index:0{_LEVEL_WIDTH}d}_{part}"
            for side in ("bid", "ask")
            for index in range(1, _BOOK_DEPTH + 1)
            for part in ("price", "quantity")
        ),
    }
)
_INFINITY = 1 << 80  # a visibility no instant reaches: the bar is missing
_MEMO_SIZE = 8


class GovernedPaperRegimeError(EdgeArtifactError):
    """Malformed, foreign or non-authentic input: no regime evidence is ever represented over it."""


class GovernedPaperRegimeApprovalKind(str, Enum):
    """HUMAN_GOVERNANCE still needs a separate production authorization; TEST_ONLY_SYNTHETIC exists for tests only."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperRegimeStatus(str, Enum):
    """The status of one check reading (the gate maps BLOCKED to its BLOCKED_ON_MISSING_INPUT)."""

    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


class GovernedPaperRegimeClass(str, Enum):
    """The PRDV4 §1.5 regime state R of one evaluation (UNKNOWN when more than one class is possible)."""

    CRISIS = "CRISIS"
    TRENDING = "TRENDING"
    HIGH_VOL = "HIGH_VOL"
    RANGE = "RANGE"
    UNKNOWN = "UNKNOWN"


class GovernedPaperPriceCrisis(str, Enum):
    """The D-PC1 tri-state price-CRISIS proof of one evaluation."""

    PROVEN_CRISIS = "PROVEN_CRISIS"
    PROVEN_NON_CRISIS = "PROVEN_NON_CRISIS"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class GovernedPaperRegimePolicy:
    """The governed regime policy v1: the approved methodology's every NEW constant, bound to one MARK bar source."""

    schema_version: str
    policy_id: str
    instrument: str
    bar_source_digest: str
    methodology_id: str
    methodology_revision: str
    implemented_items: tuple[str, ...]
    bar_price_semantics: str
    bar_interval_ns: int
    knowledge_deadline_ns: int
    temporal_method_id: str
    price_crisis_method_id: str
    price_crisis_kind: str
    price_crisis_up_ratio: str
    price_crisis_down_ratio: str
    price_crisis_max_span_bars: int
    price_crisis_window_closes: int
    volatility_method_id: str
    volatility_window_closes: int
    trend_method_id: str
    trend_ema_fast_hours: int
    trend_ema_slow_hours: int
    trend_ema_truncation_multiple: int
    trend_atr_hours: int
    trend_strength_bound: str
    classifier_method_id: str
    hysteresis_method_id: str
    hysteresis_confirmations: int
    hysteresis_memory_evaluations: int
    overlay_transitions: int
    overlay_window_evaluations: int
    overlay_hold_evaluations: int
    regime_pass_label_window: int
    cooldown_method_id: str
    cooldown_window_evaluations: int
    cooldown_pass_label_window: int
    trend_filter_method_id: str
    liquidity_method_id: str
    book_freshness_ns: int
    liquidity_band_ratio: str
    liquidity_samples: int
    spread_method_id: str
    spread_samples: int
    execution_method_id: str
    execution_fail_latency_ns: int
    regime_cell_price_states: tuple[str, ...]
    regime_cell_funding_states: tuple[str, ...]
    regime_cell_leverage_states: tuple[str, ...]
    regime_cell_liquidity_states: tuple[str, ...]
    system_state_edge_tier: str
    system_state_required: str
    interpretation_records: tuple[str, ...]
    policy_digest: str
    paper_only: bool = True
    calibrated: bool = False
    crisis_coverage_guaranteed: bool = False
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperRegimeApproval:
    """One approval of a regime policy digest; its approved items are exactly the human construction scope."""

    schema_version: str
    approval_id: str
    approval_kind: GovernedPaperRegimeApprovalKind
    policy_digest: str
    approved_items: tuple[str, ...]
    approver_reference: str
    approval_digest: str
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperRegimeApprovalTable:
    """Which approvals may be used.

    ``production`` admits a HUMAN_GOVERNANCE approval of a listed policy digest only. ``test_only`` admits only
    TEST_ONLY_SYNTHETIC approvals and lists no digest.
    """

    table_id: str
    admitted_kind: GovernedPaperRegimeApprovalKind
    admitted_policy_digests: tuple[str, ...]


# No separate human authorization lists any policy digest for production use, so this table refuses every approval.
GOVERNED_PAPER_REGIME_PRODUCTION_APPROVAL_TABLE = GovernedPaperRegimeApprovalTable(
    table_id="production",
    admitted_kind=GovernedPaperRegimeApprovalKind.HUMAN_GOVERNANCE,
    admitted_policy_digests=(),
)
_APPROVAL_TABLE = GOVERNED_PAPER_REGIME_PRODUCTION_APPROVAL_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperRegimeEvaluation:
    """One frozen evaluation: what was known at ``knowledge_time_ns`` about the window ending at ``close_time_ns``.

    ``label`` is the §1.5 state (UNKNOWN unless exactly one class is possible), ``possible`` the classes still possible,
    ``confirmed`` the A8 confirmed state, ``pending`` whether the label differs from it, ``overlay`` the FORCED_DEFENSIVE
    overlay. ``trend`` is STRONG_UP, STRONG_DOWN, NOT_STRONG or UNAVAILABLE; the activation columns are UNKNOWN when
    unproven.
    """

    index: int
    close_time_ns: int
    knowledge_time_ns: int
    label: str
    possible: tuple[str, ...]
    price_crisis: str
    trend: str
    volatility: str
    liquidity: str
    spread: str
    confirmed: str
    pending: bool
    overlay: bool


@dataclass(frozen=True)
class GovernedPaperRegimeCheckReading:
    """One rule set v6 check's reading for one decision."""

    check_id: str
    status: GovernedPaperRegimeStatus
    observed: str
    reason: str


@dataclass(frozen=True)
class GovernedPaperRegimeReading:
    """The readings of one entry decision, on the evaluation it reads (None without an admitted approval)."""

    decision_sequence: int
    decision_time_ns: int
    target_direction: str
    evaluation_index: int | None
    checks: tuple[GovernedPaperRegimeCheckReading, ...]

    def check(self, check_id: str) -> GovernedPaperRegimeCheckReading:
        for item in self.checks:
            if item.check_id == check_id:
                return item
        raise GovernedPaperRegimeError(f"{_PREFIX}:reading_check_missing:{check_id}")


@dataclass(frozen=True)
class GovernedPaperRegimeEvidence:
    """The derived regime evidence of one evaluation horizon: the frozen log and every entry decision's readings."""

    schema_version: str
    contract_id: str
    policy_digest: str
    approval_digest: str
    approval_kind: GovernedPaperRegimeApprovalKind
    approval_table_id: str
    approval_admitted: bool
    approval_reason: str
    archive_digest: str
    bar_source_digest: str
    dataset_digest: str
    book_series_id: str
    book_series_reason: str
    instrument: str
    genesis_start_ns: int
    horizon_ns: int
    latency_ns: int
    log_first_index: int | None
    log_last_index: int | None
    evaluations: tuple[GovernedPaperRegimeEvaluation, ...]
    readings: tuple[GovernedPaperRegimeReading, ...]
    evidence_digest: str
    paper_only: bool = True
    synthetic_regime_approval_used: bool = False
    production_use_authorized: bool = False
    intrabar_state_claimed: bool = False
    real_market_source_qualified: bool = False
    venue_facts_proven: bool = False
    calibrated: bool = False
    crisis_coverage_guaranteed: bool = False
    t10_measured: bool = False
    live_ready: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperRegimeError:
    return GovernedPaperRegimeError(_reason(code))


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


def _ratio(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def _units(text: str) -> int:
    """A canonical scale-18 decimal in exact integer units."""

    value = Fraction(text) * _UNIT
    if value.denominator != 1:
        raise _fail("price_not_at_scale_18")
    return value.numerator


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


# --- the policy and its approval ---------------------------------------------------------------------------------------


def _policy_seed(policy_id: str, instrument: str, bar_source_digest: str) -> GovernedPaperRegimePolicy:
    return GovernedPaperRegimePolicy(
        schema_version=GOVERNED_PAPER_REGIME_POLICY_SCHEMA,
        policy_id=policy_id,
        instrument=instrument,
        bar_source_digest=bar_source_digest,
        methodology_id=GOVERNED_PAPER_REGIME_METHODOLOGY_ID,
        methodology_revision=GOVERNED_PAPER_REGIME_METHODOLOGY_REVISION,
        implemented_items=GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS,
        bar_price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE.value,
        bar_interval_ns=_BAR_NS,
        knowledge_deadline_ns=_KNOWLEDGE_DEADLINE_NS,
        temporal_method_id=_TEMPORAL_METHOD,
        price_crisis_method_id=_PRICE_CRISIS_METHOD,
        price_crisis_kind="COMPLETE",
        price_crisis_up_ratio=_ratio(_CRISIS_UP),
        price_crisis_down_ratio=_ratio(_CRISIS_DOWN),
        price_crisis_max_span_bars=_CRISIS_SPAN,
        price_crisis_window_closes=_CRISIS_WINDOW,
        volatility_method_id=_VOLATILITY_METHOD,
        volatility_window_closes=_SIGMA_WINDOW,
        trend_method_id=_TREND_METHOD,
        trend_ema_fast_hours=_EMA_FAST,
        trend_ema_slow_hours=_EMA_SLOW,
        trend_ema_truncation_multiple=_EMA_TRUNCATION,
        trend_atr_hours=_ATR_HOURS,
        trend_strength_bound=_ratio(_TREND_BOUND),
        classifier_method_id=_CLASSIFIER_METHOD,
        hysteresis_method_id=_HYSTERESIS_METHOD,
        hysteresis_confirmations=_CONFIRMATIONS,
        hysteresis_memory_evaluations=_MEMORY,
        overlay_transitions=_OVERLAY_TRANSITIONS,
        overlay_window_evaluations=_OVERLAY_WINDOW,
        overlay_hold_evaluations=_OVERLAY_HOLD,
        regime_pass_label_window=_REGIME_PASS_WINDOW,
        cooldown_method_id=_COOLDOWN_METHOD,
        cooldown_window_evaluations=_COOLDOWN_WINDOW,
        cooldown_pass_label_window=_COOLDOWN_PASS_WINDOW,
        trend_filter_method_id=_TREND_FILTER_METHOD,
        liquidity_method_id=_LIQUIDITY_METHOD,
        book_freshness_ns=_BOOK_FRESHNESS_NS,
        liquidity_band_ratio=_ratio(_BAND),
        liquidity_samples=_LIQUIDITY_SAMPLES,
        spread_method_id=_SPREAD_METHOD,
        spread_samples=_SPREAD_SAMPLES,
        execution_method_id=_EXECUTION_METHOD,
        execution_fail_latency_ns=_EXECUTION_FAIL_LATENCY_NS,
        regime_cell_price_states=_REGIME_CELLS[0],
        regime_cell_funding_states=_REGIME_CELLS[1],
        regime_cell_leverage_states=_REGIME_CELLS[2],
        regime_cell_liquidity_states=_REGIME_CELLS[3],
        system_state_edge_tier="T1",
        system_state_required="SS-0",
        interpretation_records=_INTERPRETATION_RECORDS,
        policy_digest="",
    )


def governed_paper_regime_policy_digest(policy: GovernedPaperRegimePolicy) -> str:
    """The canonical policy digest, excluding only ``policy_digest``."""

    return edge_payload_digest(_to_payload(policy), "policy_digest")


def build_governed_paper_regime_policy(
    *, policy_id: str, instrument: str, bar_source_digest: str
) -> GovernedPaperRegimePolicy:
    """The approved methodology's policy for one instrument and one MARK bar source (every other value is fixed)."""

    policy_id = _require_text(policy_id, "policy_id")
    instrument = _require_text(instrument, "instrument")
    if not edge_is_hex64(bar_source_digest):
        raise _fail("bar_source_digest_invalid")
    seed = _policy_seed(policy_id, instrument, bar_source_digest)
    return replace(seed, policy_digest=governed_paper_regime_policy_digest(seed))


def verify_governed_paper_regime_policy(policy: object) -> EdgeEvidenceVerification:
    """Re-derive the policy from its id, instrument and source: any other value or a wrong digest is not intact. Total."""

    if type(policy) is not GovernedPaperRegimePolicy:
        return _verification("", False, (_reason("policy_malformed"),), {})
    try:
        rebuilt = build_governed_paper_regime_policy(
            policy_id=policy.policy_id, instrument=policy.instrument, bar_source_digest=policy.bar_source_digest
        )
    except GovernedPaperRegimeError as exc:
        return _verification("", False, (str(exc),), {})
    intact = _identical(policy, rebuilt)
    reasons = () if intact else (_reason("policy_not_the_approved_methodology"),)
    return _verification(rebuilt.policy_digest, intact, reasons, _to_payload(rebuilt))


def governed_paper_regime_approval_digest(approval: GovernedPaperRegimeApproval) -> str:
    """The canonical approval digest, excluding only ``approval_digest``."""

    return edge_payload_digest(_to_payload(approval), "approval_digest")


def build_governed_paper_regime_approval(
    *,
    approval_id: str,
    approval_kind: GovernedPaperRegimeApprovalKind,
    policy_digest: str,
    approver_reference: str,
) -> GovernedPaperRegimeApproval:
    """One approval of ``policy_digest`` over exactly the human construction scope (never production permission)."""

    if type(approval_kind) is not GovernedPaperRegimeApprovalKind:
        raise _fail("approval_kind_invalid")
    if not edge_is_hex64(policy_digest):
        raise _fail("approval_policy_digest_invalid")
    seed = GovernedPaperRegimeApproval(
        schema_version=GOVERNED_PAPER_REGIME_APPROVAL_SCHEMA,
        approval_id=_require_text(approval_id, "approval_id"),
        approval_kind=approval_kind,
        policy_digest=policy_digest,
        approved_items=GOVERNED_PAPER_REGIME_APPROVED_ITEMS,
        approver_reference=_require_text(approver_reference, "approver_reference"),
        approval_digest="",
    )
    return replace(seed, approval_digest=governed_paper_regime_approval_digest(seed))


def verify_governed_paper_regime_approval(approval: object) -> EdgeEvidenceVerification:
    """Re-derive the approval: its items must be exactly the approved scope and its digest exact. Total."""

    if type(approval) is not GovernedPaperRegimeApproval:
        return _verification("", False, (_reason("approval_malformed"),), {})
    try:
        rebuilt = build_governed_paper_regime_approval(
            approval_id=approval.approval_id,
            approval_kind=approval.approval_kind,
            policy_digest=approval.policy_digest,
            approver_reference=approval.approver_reference,
        )
    except GovernedPaperRegimeError as exc:
        return _verification("", False, (str(exc),), {})
    intact = _identical(approval, rebuilt)
    reasons = () if intact else (_reason("approval_not_the_approved_scope"),)
    return _verification(rebuilt.approval_digest, intact, reasons, _to_payload(rebuilt))


def _canonical_table(table: object) -> GovernedPaperRegimeApprovalTable:
    if type(table) is not GovernedPaperRegimeApprovalTable:
        raise _fail("approval_table_malformed")
    digests = table.admitted_policy_digests
    if type(digests) is not tuple or any(not edge_is_hex64(item) for item in digests):
        raise _fail("approval_table_malformed")
    if table.table_id == "production" and table.admitted_kind is GovernedPaperRegimeApprovalKind.HUMAN_GOVERNANCE:
        return table
    if (
        table.table_id == "test_only"
        and table.admitted_kind is GovernedPaperRegimeApprovalKind.TEST_ONLY_SYNTHETIC
        and not digests
    ):
        return table
    raise _fail("approval_table_malformed")


def _admission(table: GovernedPaperRegimeApprovalTable, approval: GovernedPaperRegimeApproval) -> str:
    """Why the approval may not be used under ``table`` (empty when it may)."""

    kind = approval.approval_kind
    if table.table_id == "production":
        if kind is GovernedPaperRegimeApprovalKind.TEST_ONLY_SYNTHETIC:
            return "synthetic_approval_refused_on_the_production_table"
        if approval.policy_digest not in table.admitted_policy_digests:
            return "policy_not_authorized_for_production_use"
        return ""
    if kind is not GovernedPaperRegimeApprovalKind.TEST_ONLY_SYNTHETIC:
        return "only_test_only_synthetic_approvals_on_the_test_only_table"
    return ""


# --- the bars ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _BarFacts:
    close: int
    high: int
    low: int
    visible: int


class _RangeMax:
    """Exact range maximum (a sparse table) over the visibilities of the bars ``[first, first + len)``."""

    def __init__(self, first: int, values: list[int]) -> None:
        self.first = first
        self.table = [values]
        span = 1
        while 2 * span <= len(values):
            previous = self.table[-1]
            self.table.append([max(previous[i], previous[i + span]) for i in range(len(previous) - span)])
            span *= 2

    def query(self, low: int, high: int) -> int:
        """max over bars ``low..high`` (inclusive); a bar outside the table is missing."""

        size = len(self.table[0])
        if low > high or low < self.first or high >= self.first + size:
            return _INFINITY
        low, high = low - self.first, high - self.first
        level = (high - low + 1).bit_length() - 1
        row = self.table[level]
        return max(row[low], row[high - (1 << level) + 1])


class _Bars:
    """The bound source's 300 s MARK bars of ``[first, last]`` by close index (``close_time_ns // 300 s``)."""

    def __init__(self, archive: HistoricalOhlcBarArchive, first: int, last: int) -> None:
        self.first, self.last = first, last
        self.bars: dict[int, _BarFacts] = {}
        for bar in archive.bars:
            if bar.interval_ns != _BAR_NS:
                continue
            index = bar.close_time_ns // _BAR_NS
            if first <= index <= last:
                self.bars[index] = _BarFacts(
                    close=_units(bar.close_price),
                    high=_units(bar.high_price),
                    low=_units(bar.low_price),
                    visible=max(bar.available_at_ns, bar.finalized_at_ns),
                )
        self.visible = _RangeMax(
            first, [self.bars[k].visible if k in self.bars else _INFINITY for k in range(first, last + 1)]
        )

    def known(self, low: int, high: int, at: int) -> bool:
        """Whether every bar ``low..high`` exists and is visible at ``at``."""

        return self.visible.query(low, high) <= at


def _crisis_witnesses(bars: _Bars, first: int, last: int) -> list[tuple[int, int, int]]:
    """Every witness pair ``(j, i, visibility)`` with ``j`` in ``[first, last]``, ordered by ``j``."""

    witnesses: list[tuple[int, int, int]] = []
    for j in range(first, last + 1):
        later = bars.bars.get(j)
        if later is None:
            continue
        for i in range(j - _CRISIS_SPAN, j):
            earlier = bars.bars.get(i)
            if earlier is None:
                continue
            up = _CRISIS_UP.denominator * later.close > _CRISIS_UP.numerator * earlier.close
            down = _CRISIS_DOWN.denominator * later.close < _CRISIS_DOWN.numerator * earlier.close
            if up or down:
                witnesses.append((j, i, max(later.visible, earlier.visible)))
    return witnesses


def _price_crisis(bars: _Bars, witnesses: list[tuple[int, int, int]], ends: list[int], m: int, knowledge: int) -> str:
    """D-PC1 over the D-PC2 witnesses (``ends`` are their ``j``): a witness of ``[m - 288, m]`` visible at ``knowledge``
    proves CRISIS; all 289 closes visible without one prove NON_CRISIS; anything else is UNKNOWN."""

    low = bisect.bisect_left(ends, m - _CRISIS_WINDOW + 2)
    high = bisect.bisect_right(ends, m)
    if any(witnesses[k][1] >= m - _CRISIS_WINDOW + 1 and witnesses[k][2] <= knowledge for k in range(low, high)):
        return GovernedPaperPriceCrisis.PROVEN_CRISIS.value
    if bars.known(m - _CRISIS_WINDOW + 1, m, knowledge):
        return GovernedPaperPriceCrisis.PROVEN_NON_CRISIS.value
    return GovernedPaperPriceCrisis.UNKNOWN.value


def _sigma_bucket(bars: _Bars, m: int) -> str:
    """The A4 bucket of the 25 closes ending at ``m`` (they must exist; visibility is checked by the caller)."""

    closes = [bars.bars[k].close for k in range(m - _SIGMA_WINDOW + 1, m + 1)]
    returns = [Fraction(closes[k] - closes[k - 1], closes[k - 1]) for k in range(1, len(closes))]
    mean = sum(returns, Fraction(0)) / len(returns)
    variance = sum(((item - mean) ** 2 for item in returns), Fraction(0)) / (len(returns) - 1)
    if variance < _SIGMA_BOUNDS[0]:
        return "LOW"
    if variance < _SIGMA_BOUNDS[1]:
        return "MED"
    if variance < _SIGMA_BOUNDS[2]:
        return "HIGH"
    return "EXTREME"


def _ema_weights(span: int) -> tuple[tuple[int, ...], int]:
    """``w_i = (N - 1)^i (N + 1)^(4N - 1 - i)`` for ``i < 4N`` (``alpha (1 - alpha)^i`` scaled) and their sum."""

    count = _EMA_TRUNCATION * span
    weights = tuple((span - 1) ** i * (span + 1) ** (count - 1 - i) for i in range(count))
    return weights, sum(weights)


_FAST_WEIGHTS = _ema_weights(_EMA_FAST)
_SLOW_WEIGHTS = _ema_weights(_EMA_SLOW)
_TREND_HOURS = _EMA_TRUNCATION * _EMA_SLOW  # 192 hourly closes


class _Trend:
    """The A7 TS state of every hour, with the latest visibility of the 5-minute bars it reads."""

    def __init__(self, bars: _Bars) -> None:
        self.bars = bars
        self.hours: dict[int, tuple[int, int, int] | None] = {}  # hour -> (high, low, close) of a complete hour
        self.states: dict[int, tuple[str, int]] = {}

    def _hour(self, hour: int) -> tuple[int, int, int] | None:
        if hour not in self.hours:
            parts = [self.bars.bars.get(_BARS_PER_HOUR * hour + k) for k in range(1, _BARS_PER_HOUR + 1)]
            self.hours[hour] = (
                None
                if any(item is None for item in parts)
                else (
                    max(item.high for item in parts),  # type: ignore[union-attr]
                    min(item.low for item in parts),  # type: ignore[union-attr]
                    parts[-1].close,  # type: ignore[union-attr]
                )
            )
        return self.hours[hour]

    def state(self, hour: int) -> tuple[str, int]:
        """``(state, visibility)`` of the TS at the close of ``hour``; UNAVAILABLE (visibility infinite) when a bar is
        missing, UNAVAILABLE at its visibility when ATR24 is zero."""

        if hour in self.states:
            return self.states[hour]
        first = hour - _TREND_HOURS + 1
        hours = [self._hour(item) for item in range(first, hour + 1)]
        if any(item is None for item in hours):
            result = ("UNAVAILABLE", _INFINITY)
        else:
            visible = self.bars.visible.query(_BARS_PER_HOUR * first + 1, _BARS_PER_HOUR * hour + _BARS_PER_HOUR)
            closes = [item[2] for item in hours]  # type: ignore[index]
            fast_weights, fast_total = _FAST_WEIGHTS
            slow_weights, slow_total = _SLOW_WEIGHTS
            fast = sum(weight * closes[-1 - i] for i, weight in enumerate(fast_weights))
            slow = sum(weight * closes[-1 - i] for i, weight in enumerate(slow_weights))
            ranges = 0
            for k in range(len(hours) - _ATR_HOURS, len(hours)):
                high, low, _ = hours[k]  # type: ignore[misc]
                previous = hours[k - 1][2]  # type: ignore[index]
                ranges += max(high - low, abs(high - previous), abs(low - previous))
            if ranges <= 0:
                result = ("UNAVAILABLE", visible)
            else:
                gap = fast * slow_total - slow * fast_total  # (EMA12 - EMA48) x fast_total x slow_total
                # 2 |EMA12 - EMA48| > (3/2) x 2 x ATR24, with ATR24 = ranges / 24, cross-multiplied exactly
                strong = (
                    _TREND_BOUND.denominator * _ATR_HOURS * abs(gap)
                    > _TREND_BOUND.numerator * ranges * fast_total * slow_total
                )
                result = ("NOT_STRONG" if not strong else "STRONG_UP" if gap > 0 else "STRONG_DOWN", visible)
        self.states[hour] = result
        return result


# --- the books ---------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Book:
    event: int
    sequence: int
    visible: int
    record: HistoricalPitRecord


@dataclass(frozen=True)
class _BookReading:
    """One parsed tip: its band depth and relative spread, or why it gives no sample (crossed, band not covered)."""

    depth: int  # quote notional in units of 10^-36
    spread: Fraction
    unusable: str


def _book_series(dataset: HistoricalPitDataset, instrument: str) -> tuple[str, str]:
    """``(reason, series id)``: the dataset's one final, immutable ORDER_BOOK series of the instrument, judged on its own
    authenticated EF-3 manifest with the producer's registry semantics, or why there is none."""

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
    candidates: list[EdgeSourceSeriesRecord] = [
        record
        for record in manifest.series
        if record.data_requirement_key == DataRequirementKey.ORDER_BOOK.value
        and instrument in record.instrument_coverage
    ]
    if not candidates:
        return "order_book_series_not_in_the_selected_data_contract", ""
    if len(candidates) > 1:
        return "order_book_series_ambiguous", ""
    record = candidates[0]
    if record.finalized_only is not True:
        return "order_book_series_not_final_and_immutable", ""
    if not all(
        type(getattr(record, name)) is type(value) and getattr(record, name) == value for name, value in _BOOK_SEMANTICS
    ):
        return "order_book_series_semantics_unsupported", ""
    return "", record.series_id


def _parse_book(record: HistoricalPitRecord) -> tuple[list[tuple[int, int]], list[tuple[int, int]]] | None:
    """The 50 exact levels of each side, best first, or None for a malformed tip."""

    values = {value.name: value.value for value in record.values}
    if len(values) != len(record.values) or frozenset(values) != _BOOK_NAMES:
        return None
    if not all(historical_execution_decimal_is_canonical(text) for text in values.values()):
        return None
    sides: list[list[tuple[int, int]]] = []
    for side in ("bid", "ask"):
        levels = [
            (
                _units(values[f"{side}_{index:0{_LEVEL_WIDTH}d}_price"]),
                _units(values[f"{side}_{index:0{_LEVEL_WIDTH}d}_quantity"]),
            )
            for index in range(1, _BOOK_DEPTH + 1)
        ]
        if any(price <= 0 or quantity <= 0 for price, quantity in levels):
            return None
        ordered = (
            all(levels[k][0] > levels[k + 1][0] for k in range(len(levels) - 1))
            if side == "bid"
            else all(levels[k][0] < levels[k + 1][0] for k in range(len(levels) - 1))
        )
        if not ordered:
            return None
        sides.append(levels)
    best = (
        _units(values[BEST_BID_PRICE_NAME]),
        _units(values[BEST_BID_QUANTITY_NAME]),
        _units(values[BEST_ASK_PRICE_NAME]),
        _units(values[BEST_ASK_QUANTITY_NAME]),
    )
    if best != (*sides[0][0], *sides[1][0]):
        return None
    return sides[0], sides[1]


def governed_paper_order_book_series(dataset: HistoricalPitDataset, instrument: str) -> tuple[str, str]:
    """``(reason, series id)``: the dataset's one final, immutable ORDER_BOOK depth-50 series of ``instrument``, the
    series every book sample here reads, judged on the dataset's own authenticated EF-3 manifest with the producer's
    registry semantics; ``reason`` names why there is none. A non-authentic manifest raises ``GovernedPaperRegimeError``.
    """

    return _book_series(dataset, instrument)


def governed_paper_order_book_levels(
    record: HistoricalPitRecord,
) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]] | None:
    """The 50 exact ``(price, quantity)`` levels of each side of one ORDER_BOOK depth-50 tip, best first, in integer units
    of 10^-18, or None for a malformed tip (exactly the parse every book sample here uses)."""

    levels = _parse_book(record)
    return None if levels is None else (tuple(levels[0]), tuple(levels[1]))


def _reading_of(levels: tuple[list[tuple[int, int]], list[tuple[int, int]]]) -> _BookReading:
    bids, asks = levels
    bid, ask = bids[0][0], asks[0][0]
    if bid >= ask:
        return _BookReading(0, Fraction(0), "book_crossed")
    total = bid + ask  # 2 x mid
    low = (1 - _BAND) * total  # 2 x the band's lower edge
    high = (1 + _BAND) * total  # 2 x the band's upper edge
    if not (2 * bids[-1][0] < low and 2 * asks[-1][0] > high):
        return _BookReading(0, Fraction(0), "book_depth_does_not_cover_the_10bps_band")
    depth = sum(price * quantity for price, quantity in bids if 2 * price >= low)
    depth += sum(price * quantity for price, quantity in asks if 2 * price <= high)
    return _BookReading(depth, Fraction(2 * (ask - bid), total), "")


class _Samples:
    """The as-known-at-``s`` book samples (CL1-10, CL1-11) at the grid instants of ``[first, last]``."""

    def __init__(self, dataset: HistoricalPitDataset, instrument: str, first: int, last: int) -> None:
        self.reason, series = _book_series(dataset, instrument)
        self.series = series
        self.first = first
        self.depth: list[int | None] = []
        self.spread: list[Fraction | None] = []
        if self.reason:
            self.depth = [None] * (last - first + 1)
            self.spread = [None] * (last - first + 1)
            return
        books: list[_Book] = []
        for record in dataset.records:
            if record.series_id != series or record.instrument != instrument or record.finalized_at_ns is None:
                continue
            books.append(
                _Book(
                    record.event_time_ns,
                    record.sequence_id,
                    max(record.available_at_ns, record.finalized_at_ns),
                    record,
                )
            )
        books.sort(key=lambda item: item.visible)
        parsed: dict[str, _BookReading | None] = {}
        malformed: int | None = None
        events: list[tuple[int, int, int]] = []  # (event, sequence, position) of the books visible so far
        cursor = 0
        for index in range(first, last + 1):
            instant = index * _BAR_NS
            while cursor < len(books) and books[cursor].visible <= instant:
                book = books[cursor]
                if book.record.record_digest not in parsed:
                    levels = _parse_book(book.record)
                    parsed[book.record.record_digest] = None if levels is None else _reading_of(levels)
                if parsed[book.record.record_digest] is None:
                    malformed = book.visible if malformed is None else min(malformed, book.visible)
                bisect.insort(events, (book.event, book.sequence, cursor))
                cursor += 1
            sample: _BookReading | None = None
            if malformed is None:
                position = bisect.bisect_right(events, (instant, _INFINITY, _INFINITY))
                if position:
                    event, _, chosen = events[position - 1]
                    if instant - event <= _BOOK_FRESHNESS_NS:
                        candidate = parsed[books[chosen].record.record_digest]
                        sample = None if candidate is None or candidate.unusable else candidate
            self.depth.append(None if sample is None else sample.depth)
            self.spread.append(None if sample is None else sample.spread)
        self._prefix_unknown = [0]
        self._prefix_depth = [0]
        for value in self.depth:
            self._prefix_unknown.append(self._prefix_unknown[-1] + (value is None))
            self._prefix_depth.append(self._prefix_depth[-1] + (value or 0))

    def liquidity(self, m: int) -> str:
        if self.reason:
            return "UNKNOWN"
        low, high = m - _LIQUIDITY_SAMPLES + 1 - self.first, m - self.first
        if low < 0 or self._prefix_unknown[high + 1] - self._prefix_unknown[low]:
            return "UNKNOWN"
        total = self._prefix_depth[high + 1] - self._prefix_depth[low]
        if total <= 0:
            return "UNKNOWN"
        score = Fraction(_LIQUIDITY_SAMPLES * self.depth[high], total)  # type: ignore[operator]
        if score < _LIQUIDITY_BOUNDS[0]:
            return "DRY"
        if score < _LIQUIDITY_BOUNDS[1]:
            return "THIN"
        if score <= _LIQUIDITY_BOUNDS[2]:
            return "NORMAL"
        return "DEEP"

    def spread_state(self, m: int) -> str:
        if self.reason:
            return "UNKNOWN"
        low, high = m - _SPREAD_SAMPLES + 1 - self.first, m - self.first
        if low < 0:
            return "UNKNOWN"
        values = self.spread[low : high + 1]
        if any(item is None for item in values):
            return "UNKNOWN"
        mean = sum(values, Fraction(0)) / len(values)  # type: ignore[arg-type]
        if mean <= 0:
            return "UNKNOWN"
        variance = sum(((item - mean) ** 2 for item in values), Fraction(0)) / (len(values) - 1)  # type: ignore[operator]
        if variance < _SPREAD_BOUNDS[0] ** 2 * mean**2:
            return "STABLE"
        if variance < _SPREAD_BOUNDS[1] ** 2 * mean**2:
            return "WIDENING"
        return "BLOWN"


# --- one evaluation and the frozen log ---------------------------------------------------------------------------------

_ALLOWED = frozenset({"RANGE", "HIGH_VOL"})
_DEFINITE = frozenset({"CRISIS", "TRENDING", "HIGH_VOL", "RANGE"})
_ORDER = ("CRISIS", "TRENDING", "HIGH_VOL", "RANGE")


def decision_evaluation_index(time_ns: int) -> int:
    """``n(t) = max{m : kappa(m) <= t}``: the evaluation a decision at ``time_ns`` reads."""

    return time_ns // _BAR_NS - 1


def _possible(crisis: str, trend: str, volatility: str) -> tuple[str, ...]:
    """The A1 classes still possible (D-PC1 possibility semantics), in precedence order."""

    if trend in ("STRONG_UP", "STRONG_DOWN"):
        base = {"TRENDING"}
    else:
        base = {"TRENDING"} if trend == "UNAVAILABLE" else set()
        if volatility in ("HIGH", "EXTREME"):
            base.add("HIGH_VOL")
        elif volatility in ("LOW", "MED"):
            base.add("RANGE")
        else:
            base |= {"HIGH_VOL", "RANGE"}
    if crisis == GovernedPaperPriceCrisis.PROVEN_CRISIS.value:
        classes = {"CRISIS"}
    elif crisis == GovernedPaperPriceCrisis.PROVEN_NON_CRISIS.value:
        classes = base
    else:
        classes = {"CRISIS", *base}
    return tuple(item for item in _ORDER if item in classes)


def _confirmations(  # noqa: PLR0913
    labels: list[str],
    label_first: int,
    first: int,
    last: int,
    *,
    confirmations: int = _CONFIRMATIONS,
    memory: int = _MEMORY,
    window: int = _OVERLAY_WINDOW,
    threshold: int = _OVERLAY_TRANSITIONS,
    hold: int = _OVERLAY_HOLD,
) -> tuple[dict[int, str], dict[int, bool]]:
    """A8 (CL1-7) over the labels ``labels[m - label_first]``: the confirmed state and the overlay of each ``m`` in
    ``[first, last]``.

    ``S(m)`` is the label of the latest run of ``confirmations`` equal labels (UNKNOWN included) whose last element lies
    in ``[m - memory + 1, m]``, UNKNOWN without one. A transition is ``S(e) != S(e - 1)``, and at least ``threshold`` of
    them in ``[k - window + 1, k]`` hold the overlay on ``[k, k + hold - 1]``. Every value read lies in the labels: the
    caller derives ``(hold - 1) + (window - 1) + 1 + (memory + confirmations - 2)`` labels before ``first``.
    """

    confirmed_first = label_first + memory + confirmations - 2  # the earliest run it reads starts at label_first
    if first - (hold - 1) - (window - 1) - 1 < confirmed_first or last - label_first + 1 != len(labels):
        raise _fail("confirmation_window_outside_the_labels")
    run_end: int | None = None
    confirmed: dict[int, str] = {}
    for m in range(label_first, last + 1):
        recent = (
            {labels[m - k - label_first] for k in range(confirmations)} if m - confirmations + 1 >= label_first else ()
        )
        if len(recent) == 1:
            run_end = m
        if m >= confirmed_first:
            confirmed[m] = (
                labels[run_end - label_first]
                if run_end is not None and run_end >= m - memory + 1
                else GovernedPaperRegimeClass.UNKNOWN.value
            )
    transitions = {m: int(confirmed[m] != confirmed[m - 1]) for m in range(confirmed_first + 1, last + 1)}
    counts: dict[int, int] = {}
    count_first = confirmed_first + window  # its whole window lies inside the transitions
    running = sum(transitions[m] for m in range(confirmed_first + 1, count_first))
    for m in range(count_first, last + 1):
        running += transitions[m]
        counts[m] = running
        running -= transitions[m - window + 1]
    overlays = {m: any(counts[k] >= threshold for k in range(m - hold + 1, m + 1)) for m in range(first, last + 1)}
    return {m: confirmed[m] for m in range(first, last + 1)}, overlays


@dataclass
class _Log:
    """The labels of ``[label_first, last]`` and the frozen evaluations of ``[first, last]``."""

    label_first: int
    first: int
    last: int
    labels: list[str]
    possible: list[tuple[str, ...]]
    evaluations: list[GovernedPaperRegimeEvaluation]

    def label(self, m: int) -> str:
        return self.labels[m - self.label_first]

    def entry(self, m: int) -> GovernedPaperRegimeEvaluation:
        return self.evaluations[m - self.first]

    def definite(self, low: int, high: int) -> bool:
        return all(self.labels[m - self.label_first] in _DEFINITE for m in range(low, high + 1))


def _derive_log(  # noqa: C901, PLR0912, PLR0915 - one linear derivation of the frozen log
    archive: HistoricalOhlcBarArchive,
    dataset: HistoricalPitDataset,
    instrument: str,
    genesis_start_ns: int,
    horizon_ns: int,
) -> tuple[_Log, str, str]:
    first = decision_evaluation_index(genesis_start_ns) - _DERIVED_BACK
    last = decision_evaluation_index(horizon_ns - 1)
    label_first = first - _DERIVED_BACK
    bars = _Bars(archive, label_first - _BAR_HISTORY, last)
    samples = _Samples(dataset, instrument, label_first - _LIQUIDITY_SAMPLES + 1, last)
    witnesses = _crisis_witnesses(bars, label_first - _CRISIS_WINDOW + 1, last)
    witness_ends = [item[0] for item in witnesses]
    trend = _Trend(bars)
    labels: list[str] = []
    possible_sets: list[tuple[str, ...]] = []
    details: list[tuple[str, str, str, str, str]] = []
    for m in range(label_first, last + 1):
        knowledge = m * _BAR_NS + _KNOWLEDGE_DEADLINE_NS
        crisis = _price_crisis(bars, witnesses, witness_ends, m, knowledge)
        volatility = _sigma_bucket(bars, m) if bars.known(m - _SIGMA_WINDOW + 1, m, knowledge) else "UNKNOWN"
        state, visible = trend.state(m // _BARS_PER_HOUR - 1)
        trend_state = state if visible <= knowledge else "UNAVAILABLE"
        possible = _possible(crisis, trend_state, volatility)
        labels.append(possible[0] if len(possible) == 1 else GovernedPaperRegimeClass.UNKNOWN.value)
        possible_sets.append(possible)
        details.append((crisis, trend_state, volatility, samples.liquidity(m), samples.spread_state(m)))

    confirmed, overlays = _confirmations(labels, label_first, first, last)
    evaluations: list[GovernedPaperRegimeEvaluation] = []
    for m in range(first, last + 1):
        crisis, trend_state, volatility, liquidity, spread = details[m - label_first]
        label = labels[m - label_first]
        evaluations.append(
            GovernedPaperRegimeEvaluation(
                index=m,
                close_time_ns=m * _BAR_NS,
                knowledge_time_ns=m * _BAR_NS + _KNOWLEDGE_DEADLINE_NS,
                label=label,
                possible=possible_sets[m - label_first],
                price_crisis=crisis,
                trend=trend_state,
                volatility=volatility,
                liquidity=liquidity,
                spread=spread,
                confirmed=confirmed[m],
                pending=label != confirmed[m],
                overlay=overlays[m],
            )
        )
    return _Log(label_first, first, last, labels, possible_sets, evaluations), samples.reason, samples.series


# --- the readings of one decision --------------------------------------------------------------------------------------

_P, _F, _B = GovernedPaperRegimeStatus.PASS, GovernedPaperRegimeStatus.FAIL, GovernedPaperRegimeStatus.BLOCKED


def _check(
    check_id: str, status: GovernedPaperRegimeStatus, observed: str, reason: str
) -> GovernedPaperRegimeCheckReading:
    return GovernedPaperRegimeCheckReading(check_id, status, observed, reason)


def _trend_reading(entry: GovernedPaperRegimeEvaluation, direction: str) -> GovernedPaperRegimeCheckReading:
    if entry.trend == "UNAVAILABLE":
        return _check("FB-TREND", _B, entry.trend, "trend_strength_unavailable_at_the_knowledge_instant")
    aligned = (direction == "SHORT" and entry.trend == "STRONG_UP") or (
        direction == "LONG" and entry.trend == "STRONG_DOWN"
    )
    if aligned:
        return _check("FB-TREND", _F, entry.trend, "strong_trend_aligned_with_the_faded_funding_direction")
    return _check("FB-TREND", _P, entry.trend, "no_strong_trend_aligned_with_the_faded_funding_direction")


def _regime_reading(log: _Log, n: int) -> GovernedPaperRegimeCheckReading:
    entry = log.entry(n)
    observed = f"{entry.label}/{entry.confirmed}{'/overlay' if entry.overlay else ''}"
    states = {entry.label, entry.confirmed}
    if entry.overlay:
        return _check("FB-REGIME", _F, observed, "price_regime_oscillation_overlay_forces_the_defensive_state")
    if "CRISIS" in states:
        return _check("FB-REGIME", _F, observed, "price_regime_crisis")
    if "TRENDING" in states:
        return _check("FB-REGIME", _F, observed, "price_regime_trending")
    if entry.label == "UNKNOWN" and not set(entry.possible) & _ALLOWED:
        return _check("FB-REGIME", _F, observed, "no_possible_price_regime_admits_family_b")
    if entry.label == "UNKNOWN":
        return _check("FB-REGIME", _B, observed, "price_regime_unknown_never_admits_family_b")
    if entry.confirmed == "UNKNOWN":
        return _check("FB-REGIME", _B, observed, "price_regime_not_confirmed")
    if not log.definite(n - _REGIME_PASS_WINDOW + 1, n):
        return _check("FB-REGIME", _B, observed, "price_regime_proof_window_not_definite")
    return _check("FB-REGIME", _P, observed, "range_or_high_vol_confirmed_and_proven_non_crisis")


def _cooldown_reading(log: _Log, n: int) -> GovernedPaperRegimeCheckReading:
    window = range(n - _COOLDOWN_WINDOW + 1, n + 1)
    trending = [m for m in window if "TRENDING" in (log.entry(m).label, log.entry(m).confirmed)]
    if trending:
        observed = str(n - trending[-1])
        return _check("FB-REGIME-COOLDOWN", _F, observed, "trending_within_the_8h_union_window")
    if not log.definite(n - _COOLDOWN_PASS_WINDOW + 1, n):
        return _check("FB-REGIME-COOLDOWN", _B, "", "cooldown_proof_window_not_definite")
    return _check("FB-REGIME-COOLDOWN", _P, "", "no_trending_within_the_8h_union_window")


def _transition_reading(entry: GovernedPaperRegimeEvaluation) -> GovernedPaperRegimeCheckReading:
    observed = f"{entry.label}/{entry.confirmed}"
    if entry.pending:
        return _check("NT-M03", _F, observed, "price_regime_transition_in_its_hysteresis_window")
    return _check("NT-M03", _B, observed, "funding_leverage_and_liquidity_hysteresis_not_produced")


_FORBIDDEN = {
    "volatility": {"LOW", "EXTREME"},
    "liquidity": {"DRY"},
    "spread": {"BLOWN"},
}


def _activation_reading(entry: GovernedPaperRegimeEvaluation, latency_ns: int) -> GovernedPaperRegimeCheckReading:
    columns = (("volatility", entry.volatility), ("liquidity", entry.liquidity), ("spread", entry.spread))
    observed = f"{entry.volatility}/{entry.liquidity}/{entry.spread}/{latency_ns}"
    for name, state in columns:
        if state in _FORBIDDEN[name]:
            return _check("FB-ACTIVATION", _F, observed, f"{name}_{state.lower()}_forbidden_for_family_b")
    if latency_ns >= _EXECUTION_FAIL_LATENCY_NS:
        return _check("FB-ACTIVATION", _F, observed, "execution_at_least_impaired_latency_at_or_above_300ms")
    for name, state in columns:
        if state == "UNKNOWN":
            return _check("FB-ACTIVATION", _B, observed, f"{name}_unproven")
    return _check("FB-ACTIVATION", _B, observed, "execution_fill_rate_and_exchange_health_unproven_on_the_paper_path")


def _cell_reading(entry: GovernedPaperRegimeEvaluation) -> GovernedPaperRegimeCheckReading:
    observed = f"{entry.label}/{entry.confirmed}{'/overlay' if entry.overlay else ''}"
    if entry.overlay or {entry.label, entry.confirmed} & {"CRISIS", "TRENDING"}:
        return _check("FB-REGIME-CELL", _F, observed, "price_regime_outside_the_declared_family_b_cells")
    return _check("FB-REGIME-CELL", _B, observed, "leverage_and_liquidity_regime_dimensions_not_produced")


_SYSTEM_STATE = _check("SYSTEM-STATE", _B, "", "system_state_engine_not_produced_family_b_is_t1_and_needs_a_proven_ss0")


def _readings(log: _Log, decision: tuple[int, int, str], latency_ns: int) -> GovernedPaperRegimeReading:
    sequence, time_ns, direction = decision
    n = decision_evaluation_index(time_ns)
    entry = log.entry(n)
    return GovernedPaperRegimeReading(
        decision_sequence=sequence,
        decision_time_ns=time_ns,
        target_direction=direction,
        evaluation_index=n,
        checks=(
            _trend_reading(entry, direction),
            _regime_reading(log, n),
            _cooldown_reading(log, n),
            _transition_reading(entry),
            _activation_reading(entry, latency_ns),
            _cell_reading(entry),
            _SYSTEM_STATE,
        ),
    )


def _not_admitted(decision: tuple[int, int, str], reason: str) -> GovernedPaperRegimeReading:
    sequence, time_ns, direction = decision
    return GovernedPaperRegimeReading(
        decision_sequence=sequence,
        decision_time_ns=time_ns,
        target_direction=direction,
        evaluation_index=None,
        checks=tuple(
            _check(item, _B, "", f"regime_policy_not_admitted:{reason}") for item in GOVERNED_PAPER_REGIME_CHECK_IDS
        ),
    )


# --- the public derivation ---------------------------------------------------------------------------------------------

_MEMO: OrderedDict[tuple[object, ...], GovernedPaperRegimeEvidence] = OrderedDict()


def _canonical_decisions(decisions: object, genesis_start_ns: int, horizon_ns: int) -> tuple[tuple[int, int, str], ...]:
    if type(decisions) is not tuple:
        raise _fail("decisions_malformed")
    previous: tuple[int, int] | None = None
    for item in decisions:
        if (
            type(item) is not tuple
            or len(item) != 3
            or not historical_execution_wire_int_is_valid(item[0], minimum=0)
            or not historical_execution_wire_int_is_valid(item[1], minimum=0)
            or type(item[2]) is not str
            or item[2] not in ("LONG", "SHORT")
        ):
            raise _fail("decisions_malformed")
        if not genesis_start_ns <= item[1] < horizon_ns:
            raise _fail("decision_outside_the_evaluation_horizon")
        if previous is not None and (item[0] <= previous[0] or item[1] < previous[1]):
            raise _fail("decisions_not_ordered")
        previous = (item[0], item[1])
    return decisions  # type: ignore[return-value]


def derive_governed_paper_regime_evidence(  # noqa: PLR0913
    *,
    policy: GovernedPaperRegimePolicy,
    approval: GovernedPaperRegimeApproval,
    archive: HistoricalOhlcBarArchive,
    dataset: HistoricalPitDataset,
    instrument: str,
    genesis_start_ns: int,
    horizon_ns: int,
    decisions: tuple[tuple[int, int, str], ...],
    latency_ns: int,
) -> GovernedPaperRegimeEvidence:
    """Derive the frozen regime log of ``[G, horizon)`` and the readings of every entry decision (see the docstring).

    ``decisions`` are ``(sequence, time_ns, direction)`` of the entry decisions in time order, each in ``[G, horizon)``.
    Every input is re-proven here and none is trusted for its own digest. A malformed, foreign or non-authentic input
    raises ``GovernedPaperRegimeError``; an approval the active table does not admit gives BLOCKED readings and an empty
    log. Pure (an exact memo of identical re-proven inputs).
    """

    policy_check = verify_governed_paper_regime_policy(policy)
    if not policy_check.intact:
        raise _fail("policy_not_authentic")
    approval_check = verify_governed_paper_regime_approval(approval)
    if not approval_check.intact or approval.policy_digest != policy_check.recomputed_digest:
        raise _fail("approval_not_of_the_policy")
    if type(instrument) is not str or instrument != policy.instrument:
        raise _fail("instrument_not_of_the_policy")
    if type(archive) is not HistoricalOhlcBarArchive:
        raise _fail("archive_malformed")
    archive_check = verify_historical_ohlc_bar_archive(archive)
    if not archive_check.intact:
        raise _fail("archive_not_authentic")
    source = archive.source
    if (
        archive.source_digest != policy.bar_source_digest
        or source.instrument != instrument
        or source.price_semantics is not HistoricalOhlcPriceSemantics.MARK_PRICE
        or _BAR_NS not in source.bar_intervals_ns
    ):
        raise _fail("archive_not_of_the_policy_source")
    if type(dataset) is not HistoricalPitDataset:
        raise _fail("dataset_malformed")
    dataset_check = verify_historical_pit_dataset(dataset)
    if not dataset_check.intact or dataset.status is not EdgeEvidenceStatus.READY or dataset.advances is not True:
        raise _fail("dataset_not_authentic")
    for value, name in ((genesis_start_ns, "genesis_start_ns"), (horizon_ns, "horizon_ns"), (latency_ns, "latency_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if horizon_ns <= genesis_start_ns or genesis_start_ns < (_DERIVED_BACK * 2 + _BAR_HISTORY + 2) * _BAR_NS:
        raise _fail("evaluation_horizon_invalid")
    entries = _canonical_decisions(decisions, genesis_start_ns, horizon_ns)
    table = _canonical_table(_APPROVAL_TABLE)
    key = (
        policy_check.recomputed_digest,
        approval_check.recomputed_digest,
        archive_check.recomputed_digest,
        dataset_check.recomputed_digest,
        instrument,
        genesis_start_ns,
        horizon_ns,
        entries,
        latency_ns,
        table.table_id,
        table.admitted_kind.value,
        table.admitted_policy_digests,
    )
    if key in _MEMO:
        _MEMO.move_to_end(key)
        return _MEMO[key]
    refusal = _admission(table, approval)
    if refusal:
        log: _Log | None = None
        book_reason, book_series = "", ""
        readings = tuple(_not_admitted(item, refusal) for item in entries)
    else:
        log, book_reason, book_series = _derive_log(archive, dataset, instrument, genesis_start_ns, horizon_ns)
        readings = tuple(_readings(log, item, latency_ns) for item in entries)
    seed = GovernedPaperRegimeEvidence(
        schema_version=GOVERNED_PAPER_REGIME_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_REGIME_CONTRACT_ID,
        policy_digest=policy_check.recomputed_digest,
        approval_digest=approval_check.recomputed_digest,
        approval_kind=approval.approval_kind,
        approval_table_id=table.table_id,
        approval_admitted=not refusal,
        approval_reason=refusal,
        archive_digest=archive_check.recomputed_digest,
        bar_source_digest=archive.source_digest,
        dataset_digest=dataset_check.recomputed_digest,
        book_series_id=book_series,
        book_series_reason=book_reason,
        instrument=instrument,
        genesis_start_ns=genesis_start_ns,
        horizon_ns=horizon_ns,
        latency_ns=latency_ns,
        log_first_index=None if log is None else log.first,
        log_last_index=None if log is None else log.last,
        evaluations=() if log is None else tuple(log.evaluations),
        readings=readings,
        evidence_digest="",
        synthetic_regime_approval_used=not refusal
        and approval.approval_kind is GovernedPaperRegimeApprovalKind.TEST_ONLY_SYNTHETIC,
    )
    evidence = replace(seed, evidence_digest=governed_paper_regime_evidence_digest(seed))
    _MEMO[key] = evidence
    while len(_MEMO) > _MEMO_SIZE:
        _MEMO.popitem(last=False)
    return evidence


def governed_paper_regime_evidence_to_dict(evidence: GovernedPaperRegimeEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_regime_evidence_digest(evidence: GovernedPaperRegimeEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), "evidence_digest")


def governed_paper_regime_prefix_digest(evidence: GovernedPaperRegimeEvidence, *, before_ns: int) -> str:
    """The run-independent X1 content before ``before_ns``: the policy, the approval and its admission, and every frozen
    evaluation whose knowledge instant precedes ``before_ns``. A later seal of the lineage re-derives it unchanged."""

    if type(evidence) is not GovernedPaperRegimeEvidence:
        raise _fail("evidence_malformed")
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("prefix_instant_invalid")
    payload = {
        "schema_version": evidence.schema_version,
        "policy_digest": evidence.policy_digest,
        "approval_digest": evidence.approval_digest,
        "approval_table_id": evidence.approval_table_id,
        "approval_admitted": evidence.approval_admitted,
        "log_first_index": evidence.log_first_index,
        "evaluations": [_to_payload(item) for item in evidence.evaluations if item.knowledge_time_ns < before_ns],
    }
    return edge_sha256_text(edge_canonical_json(payload))


def governed_paper_regime_state_at(
    evidence: GovernedPaperRegimeEvidence, at_ns: int
) -> GovernedPaperRegimeEvaluation | None:
    """The frozen evaluation in force at ``at_ns``: the latest whose knowledge instant is at or before it (None before the
    first one, or without an admitted approval). Its 10-second samples are exactly the persisted state record."""

    if type(evidence) is not GovernedPaperRegimeEvidence:
        raise _fail("evidence_malformed")
    if not historical_execution_wire_int_is_valid(at_ns, minimum=0):
        raise _fail("state_instant_invalid")
    if not evidence.evaluations:
        return None
    index = decision_evaluation_index(at_ns)
    first = evidence.evaluations[0].index
    if index < first:
        return None
    if index > evidence.evaluations[-1].index:
        raise _fail("state_instant_beyond_the_evaluation_horizon")
    return evidence.evaluations[index - first]


__all__ = [
    "GOVERNED_PAPER_REGIME_APPROVAL_SCHEMA",
    "GOVERNED_PAPER_REGIME_APPROVED_ITEMS",
    "GOVERNED_PAPER_REGIME_CHECK_IDS",
    "GOVERNED_PAPER_REGIME_CONTRACT_ID",
    "GOVERNED_PAPER_REGIME_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS",
    "GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS",
    "GOVERNED_PAPER_REGIME_METHODOLOGY_ID",
    "GOVERNED_PAPER_REGIME_METHODOLOGY_REVISION",
    "GOVERNED_PAPER_REGIME_POLICY_SCHEMA",
    "GOVERNED_PAPER_REGIME_PRODUCTION_APPROVAL_TABLE",
    "GovernedPaperPriceCrisis",
    "GovernedPaperRegimeApproval",
    "GovernedPaperRegimeApprovalKind",
    "GovernedPaperRegimeApprovalTable",
    "GovernedPaperRegimeCheckReading",
    "GovernedPaperRegimeClass",
    "GovernedPaperRegimeError",
    "GovernedPaperRegimeEvaluation",
    "GovernedPaperRegimeEvidence",
    "GovernedPaperRegimePolicy",
    "GovernedPaperRegimeReading",
    "GovernedPaperRegimeStatus",
    "build_governed_paper_regime_approval",
    "build_governed_paper_regime_policy",
    "decision_evaluation_index",
    "derive_governed_paper_regime_evidence",
    "governed_paper_order_book_levels",
    "governed_paper_order_book_series",
    "governed_paper_regime_approval_digest",
    "governed_paper_regime_evidence_digest",
    "governed_paper_regime_evidence_to_dict",
    "governed_paper_regime_policy_digest",
    "governed_paper_regime_prefix_digest",
    "governed_paper_regime_state_at",
    "verify_governed_paper_regime_approval",
    "verify_governed_paper_regime_policy",
]
