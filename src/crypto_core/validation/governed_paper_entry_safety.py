"""Governed paper entry safety (S1_PAPER_ENTRY_SAFETY_CLOSURE_V1): the PRDV4 §1.21 NO-TRADE and §1.9 Family B gate.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.21 (explicit NO-TRADE conditions) and §1.9 (funding edge
safety), applied to the governed paper path of ``docs/crypto_core/multi_sleeve_risk_governance_design.md`` section 7.
Paper-only, deterministic, point-in-time and fail-closed. It creates no order and proves no venue fact.

Entry. A decision of the authenticated decision run whose resulting direction is LONG or SHORT can produce an intent
that increases the magnitude of the position; every such decision is evaluated here at its own decision instant ``t``.
A decision whose resulting direction is FLAT can only exit or hold, so it is never an entry. The day seal lists the
decision sequences this gate refuses in the engine's admission schedule, and the engine refuses their entries only: an
exit or a reduction of an open position is never refused by this gate.

Evaluation. The 26 NO-TRADE ids that PRDV4 §1.21 enumerates (its heading declares 23; every enumerated id is evaluated
and none is dropped), in the published order Data → Risk → Regime → Edge → Execution → Temporal, then the seven §1.9
Family B gates. Every check is exactly one of:

* ``PASS`` or ``FAIL``: the published rule evaluated on inputs derived here at ``t``, with the observed value and the
  threshold recorded;
* ``BLOCKED_ON_MISSING_INPUT``: a required measurement the selected path does not produce, never read as a pass;
* ``BLOCKED_PROTECTION_UNREPRESENTABLE``: a mandatory §1.9 position-management protection the selected path cannot
  represent, so no entry may rely on it;
* ``PROVEN_NOT_APPLICABLE``: the rule cannot apply on the selected path, for the exact reason recorded.

The first check, in that order, that is neither ``PASS`` nor ``PROVEN_NOT_APPLICABLE`` refuses the entry with its id,
reason, observed value, threshold, instrument and PIT instant. There is no override.

Derived inputs (none is supplied by a caller): the latest order-book update visible at ``t`` and the marks visible at
``t`` and at ``t − 4h`` under the economics engine's own rules (``historical_execution_visible_observations``), the
genesis instant G, the governed simulation latency and its tier, the RG-2 envelope's declared sleeves and markets, the
EF-8 invalidation instant and the registered profile of the run. The rules evaluated on them:

* NT-D02: the age ``t − event_time`` of the latest visible book update FAILs when strictly above 10 s;
* NT-E02: an EF-8 DISABLED or QUARANTINE successor effective at or before ``t`` FAILs. Otherwise the check is BLOCKED:
  the PRDV4 edge state machine (§1.6, §1.22) is driven by the edge health score, which is not produced, and an ACTIVE
  EF-8 receipt is not that state machine;
* NT-M04: PROVEN_NOT_APPLICABLE when the paper portfolio (the RG-2 envelope) declares exactly one sleeve, the genesis
  sleeve, whose admitted universe the genesis proves to be the one genesis instrument: a single instrument has no
  pairwise correlation. Market caps are budget bounds, never positions. Otherwise BLOCKED;
* NT-X01: the governed simulated latency ``latency_ns``, the only latency of the paper path, FAILs when strictly above
  five times the §1.16 tier budget (tier T1, Funding (B): 100 ms);
* NT-T01: FAILs while ``t`` lies in the first five minutes after the paper engine start G;
* FB-ANTITREND: ``r_4h = m(t) / m(t − 4h) − 1`` over the engine's visible marks; a SHORT entry FAILs when
  ``r_4h > +2%`` and a LONG entry when ``r_4h < −2%``. The §1.9 override needs the composite microstructure signal
  (§1.2) and the cascade state (§1.3); neither is produced, so an anti-trend block is never overridden.

Every other check is BLOCKED with the missing measurement or protection named. Family B applies to the registered
``passive_funding_carry.v1``: it enters SHORT on a positive and LONG on a negative trailing mean of final funding
rates, the §1.1 Family B funding mean-reversion entry. Any other profile leaves every Family B check BLOCKED.

Protective position management (``PROTECTIVE_POSITION_LIFECYCLE_V1``, rule set v2). Rule set v1 above holds for every
evaluation without a protective context. When the day seal supplies one, the three §1.9 position-management gates are
evaluated against it, and the 26 NO-TRADE ids and the other four gates are unchanged. The context holds the verified
position-management policy the economics applies, its authenticated OHLC archive and the DEC-1 protective window:

* FB-MAX-HOLD PASSes when the protective window covers ``[t, t + 24 h + 2 x max_execution_delay_ns]``, the nominal
  horizon of the first protective attempt. The engine then enforces the close-only obligation itself; an unfilled
  obligation stays an auditable breach and never a successful protection. Otherwise the gate is
  BLOCKED_PROTECTION_UNREPRESENTABLE;
* FB-STOP PASSes when, in addition, the DEC-7 ATR_4h reading at ``t`` is available. The engine reads the same ATR for
  the entry it admits. An unavailable reading is BLOCKED_ON_MISSING_INPUT with its reason, among them a positive ATR
  below half a scale-18 unit (``atr_rounds_to_zero``): an available reading always renders positive, and that
  rendering is the observed value;
* FB-STOP-TIGHTENING stays BLOCKED_PROTECTION_UNREPRESENTABLE: its exact reading (DEC-9) needs a human approval no one
  has given, whether or not the policy executes the proposed reading.

Native portfolio measurement (``S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1``, rule set v3). Rule sets v1 and v2 hold for
every evaluation without a governed portfolio. When the day seal also supplies the replayed economics and the schedule
under evaluation, the one engine DERIVES the decision portfolio of that schedule
(``simulate_historical_execution_governed_paper_decision_portfolio``, information-time schedule v4 only): the paper
portfolio as known at each decision instant, before its admission. Under that schedule every admission, at a decision
and at a fill alike, reads the publication-visible equity: a funding settlement whose final rate is not yet visible
reaches no admission, position or snapshot before its publication. The NAV is the engine's own equity over the
economics policy's ``initial_equity``; no C5 or other C1-C9 approval is claimed or implied. Each snapshot also carries
the decision's candidate: the position its intent targets if admitted and filled in full. Three NO-TRADE ids are
evaluated on it, and only while the paper portfolio is exactly the genesis sleeve (otherwise BLOCKED):

* NT-R02 (daily loss limit): ``(NAV(t) − NAV(d)) / NAV(d)`` with ``d`` the UTC midnight that starts the decision's day
  and ``NAV(d)`` the engine's valuation at ``d`` (the initial one when the run starts exactly then). It FAILs when
  strictly below −2%; equality passes. The day-start NAV is never substituted: a partial first day, a decision exactly
  at the boundary or a non-positive day-start NAV is BLOCKED, and so is an unavailable NAV (an open position without
  a fresh visible mark, or an amount outside the numeric policy's representation domain);
* NT-R03 (open risk cap): PRDV4 defines no position-risk measure. The CURRENT open risk is measured only while there is
  no position and no order in flight, where it is exactly zero; an open position or an order in flight is BLOCKED. A
  candidate that increases the magnitude of the position is a PROSPECTIVE entry whose position risk has no approved
  measure, so it is BLOCKED (``prospective_entry_position_risk_measure_undefined``), with the current zero recorded as
  observed: a zero present risk never approves a new position's risk;
* NT-R04 (position concentration): on an available positive NAV, the current share ``|q| x mark(t) / NAV(t)`` FAILs when
  strictly above 25%. A candidate that increases the magnitude of the position FAILs when its own share at the decision
  instant, ``|candidate| x mark(t) / (NAV(t) − its taker fee at mark(t))``, is strictly above 25% (equality passes), and
  is BLOCKED without that projection. The projection is the decision-time reading only: the later fill executes at an
  unknown book, and the engine refuses there every exposure-increasing fill whose exact post-fill share of the
  publication-visible equity is strictly above 25% (``governed_paper_position_concentration_exceeded_at_fill``), so no
  admitted entry ever holds more than 25% of NAV at its fill.

The admissions are sequential: an entry is evaluated on the portfolio that the admitted entries before it produced. The
day seal finds the one schedule whose refusals are its own (``governed_paper_entry_safety_sequential_refusals``):
starting from every entry refused, each round re-derives the decision portfolio under the previous refusals. Because a
decision's portfolio depends only on the admissions before it, round k is exact for the first k entries, so the
fixed point exists, is unique and is reached in at most one round more than there are entries. Every other check is
unchanged, and a refusal never reaches an exit.

Native market-data integrity (``S1_MARKET_DATA_INTEGRITY_NATIVE_MEASUREMENT_CLOSURE_V1``, rule set v4). Rule sets v1-v3
hold for every evaluation without market data. When the day seal opts in, on top of the governed portfolio of rule set
v3, NT-D01, NT-D03, NT-D04 and NT-D05 are measured on the archive at ``t``
(``governed_paper_entry_safety_market_data``). The series are the registered LAST_TRADE and INDEX_PRICE series of
the genesis data contract, each the one final, immutable series of its key covering the instrument, read under PIT
visibility (available and final at or before ``t``, by native event time then native id). A public dataset can bypass
their only producer (``authenticated_pit_ingress``). So each series is selected (key and instrument coverage) and
judged on the dataset's own EF-3 manifest, reconstructed from its source-manifest binding and re-verified by the public
EF-3 verifier with its digest recomputed. Every registry 1.0 field that producer implements (source, event,
availability and finality times, price semantics, no sequence policy, finality policy, final-only, immutable) must hold
with its exact type, or the series is BLOCKED as unsupported. A dataset label never stands in for those semantics.

The kline feed is the protective context's OHLC archive only when its source DECLARES the ``exchange_kline`` origin,
last-trade bars and the 1-minute interval: trade-derived bars, an undeclared origin or any other source is never an
exchange kline feed. A
series the data contract does not declare is BLOCKED with that reason and never substituted (no mark, mid or book stands
in for a trade or an index). The thresholds are PRDV4 §1.21's, and equality passes:

* NT-D01 (feed gap), over the span from the open ``w`` of the latest completed UTC 5-minute window to ``t``: the
  largest observed gap of the trade stream, between consecutive visible trades from the latest one at or before ``w``
  and from the newest one to ``t`` (by native event time), FAILs strictly above 60 s; the largest gap of the 1-minute
  exchange klines, between consecutive visible bars from the latest one closing at or before ``w`` and from the newest
  close to ``t``, FAILs strictly above 5 minutes. A PASS needs both feeds observed back to ``w`` and the trade stream
  proven continuous there: one contiguous run of its DECLARED ``contiguous_trade_id.v1`` profile. Without the profile no
  continuity is claimed (BLOCKED), a native gap inside the span is BLOCKED, and a recent trade never repairs an
  unobserved span start;
* NT-D03 (trade/book timestamp divergence): ``|e_trade - e_book|`` between the latest visible trade and the latest
  visible L2 update (NT-D02's), both by native event time, FAILs strictly above 5 s. Receipt times only decide
  visibility and are never compared;
* NT-D04 (price vs index): the price is the latest visible trade's price (the versioned reading of "price"; never the
  mark or the mid) and ``|price - index| / index`` against the latest visible index FAILs strictly above 2%. Both must be
  current: the trade within NT-D01's 60 s trade-stream bound, the index inside the UTC second of its DECLARED
  ``index_one_per_utc_second.v1`` profile, where no later value can exist yet. No index freshness bound is invented: an
  index without that profile, or whose second has elapsed, is BLOCKED. The profile is re-proven on the index records
  visible at ``t``, as its producer enforces it. A stream that mixes declared and undeclared records is BLOCKED, and so
  are two distinct publications (native event time and value) in one declared second, whatever their values or order:
  no preferred value is ever chosen. An identical replay is one publication;
* NT-D05 (volume anomaly): the base-asset traded quantity of the latest completed UTC 5-minute window against the mean
  of the 8640 completed windows before it (30 days), the target excluded. Every window must be proven covered: one
  contiguous run of the declared trade profile from a visible trade strictly before the first window to one at or
  after the target window's end, so no unseen trade can lie inside and no unknown interval is read as zero volume. The
  mean must be strictly positive; the target FAILs strictly below 5% of it.

These facts read the archive alone and never the admission schedule, so the sequential admission is unchanged. A
declared capture profile is documented, never qualified (M1): a PASS proves software construction on the supplied
archive, never real market continuity, source rights or venue facts.

Proven kill-switch escalation (``S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1``, rule set v5). Rule sets v1-v4 hold for
every evaluation without it. When the day seal opts in, on top of rule set v4, the evaluation derives the proven
lower-bound PRDV4 §1.19 ladder of its own governed re-run (``governed_paper_kill_switch``): the decision portfolio and
the governed outcome of ONE engine re-run under the schedule under evaluation, the archive's final funding series, the
governed latency and the genesis envelope. A reading there is a trigger proven TRUE; every other trigger is unproven,
never FALSE:

* NT-R01 (kill-switch active) FAILs exactly when the proven lower bound of the level at ``t`` is at least KS-2: two
  standard triggers proven at ``t`` itself, or a KS-3 proven at or before ``t`` (absorbing without a governed recovery
  approval), with the triggers that prove it. Otherwise it is BLOCKED with that lower bound and every trigger neither
  proven TRUE at ``t`` nor proven not applicable. It never passes: an unmeasured trigger (no CVaR, liquidity,
  venue-health, BTC-identity, critical-feed, system-integrity or margin reading exists) may be active, so neither KS-0
  nor KS-1 is ever proven, and a KS-1 entry would also need the §1.19 KS-1 actions, which nothing represents;
* NT-T02 (post-kill-switch cool-down) stays BLOCKED: a cool-down state is exact only over a complete trigger history,
  and this one is not, so no absence of a cool-down is ever claimed.

The ladder at ``t`` reads only the portfolio the admissions before ``t`` produced, so the sequential admission of rule
set v3 stays the unique causal fixed point, and a refusal still reaches an entry only, never an exit or a protective
close-only action. The evidence binds the ladder; every v1-v4 payload is unchanged.

The evidence is digest-bound and paper-only. It proves no venue fact, edge, profitability, readiness or Stage-4
completion. Exact arithmetic, no float, no ``decimal`` context, and no IO, clock, randomness, network or environment.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.validation.authenticated_pit_ingress import (
    INDEX_PRICE_VALUE_NAME,
    INDEX_UTC_SECOND_SLOT_VALUE_NAME,
    TRADE_PRICE_VALUE_NAME,
    TRADE_QUANTITY_VALUE_NAME,
    TRADE_RUN_FIRST_ID_VALUE_NAME,
    NativeIndexPublicationProfile,
    NativeTradeContinuityProfile,
)
from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeGateVerdict,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourceSeriesRecord,
    edge_source_packet_evidence_from_payload,
    edge_source_packet_evidence_payload_is_well_formed,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperGenesisAuthority
from crypto_core.validation.governed_paper_kill_switch import (
    GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
    GOVERNED_PAPER_KILL_SWITCH_RULE_ID,
    GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS,
    GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS,
    GovernedPaperKillSwitchError,
    GovernedPaperKillSwitchLadder,
    build_governed_paper_kill_switch_ladder,
    governed_paper_kill_switch_level_at,
    governed_paper_kill_switch_proven_at,
    governed_paper_kill_switch_unmeasured,
    governed_paper_kill_switch_unproven_at,
)
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionDecisionPortfolioSnapshot,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionGovernedPaperDecisionPortfolio,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionProtectiveWindow,
    historical_execution_visible_observations,
    simulate_historical_execution_governed_paper_decision_portfolio_and_outcome,
)
from crypto_core.validation.historical_execution_economics_policy import (
    historical_execution_decimal_is_canonical,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcBarOrigin,
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
    MAX_HOLD_NS,
    TIGHTENING_DEC9_READING_V1,
    HistoricalPositionManagementPolicy,
    verify_historical_position_management_policy,
)
from crypto_core.validation.strategy_executable_profiles import (
    PASSIVE_FUNDING_CARRY_V1,
    get_strategy_executable_profile,
)

_SCHEMA_VERSION = "governed-paper-entry-safety-evidence.v1"
_PREFIX = "governed_paper_entry_safety"
_DIGEST_FIELD = "evidence_digest"
_NS_PER_SECOND = 1_000_000_000

# PRDV4 doctrine values: published thresholds, never governed parameters.
_BOOK_STALE_AFTER_NS = 10 * _NS_PER_SECOND  # NT-D02 (§1.21, §4.2)
_TIER_LATENCY_BUDGET_NS = GOVERNED_PAPER_KILL_SWITCH_TIER_LATENCY_BUDGET_NS  # §1.16 T1 Critical, < 100 ms: Funding (B)
_LATENCY_BREACH_MULTIPLE = 5  # NT-X01
_STARTUP_WARMUP_NS = 5 * 60 * _NS_PER_SECOND  # NT-T01
_RETURN_LOOKBACK_NS = 4 * 3600 * _NS_PER_SECOND  # §1.9 r_4h
_DAILY_LOSS_LIMIT = Fraction(-2, 100)  # NT-R02 (§1.21, §8.2): intraday PnL / NAV strictly below -2%
# NT-R04 (§1.21, §8.2): a single position strictly above 25% of NAV; the one constant the engine's fill-time bound reads
_CONCENTRATION_CAP = HISTORICAL_EXECUTION_POSITION_CONCENTRATION_CAP
_UTC_DAY_NS = 86_400 * _NS_PER_SECOND
_DAY_START_REASONS = ("partial_first_utc_day", "day_start_valued_after_the_decision", "day_start_nav_unrepresentable")
_NAV_REASONS = ("no_fresh_visible_mark", "nav_unrepresentable")
_CANDIDATE_REASONS = ("no_fresh_visible_mark", "nav_unavailable", "candidate_nav_unrepresentable")
_ZERO_RENDERING = "0.000000000000000000"  # the zero open risk of an empty portfolio, at the numeric policy's scale 18
_ANTI_TREND_BOUND = Fraction(2, 100)  # §1.9 anti-trend protection, ±2%
_ENTRY_DIRECTIONS = ("LONG", "SHORT")
# Rule set v4 (§1.21 Data): PRDV4's published thresholds and the windows of their versioned readings.
_TRADE_GAP_NS = 60 * _NS_PER_SECOND  # NT-D01: a trade stream gap strictly above 60 s
_KLINE_GAP_NS = 5 * 60 * _NS_PER_SECOND  # NT-D01: a kline feed gap strictly above 5 minutes
_KLINE_INTERVAL_NS = 60 * _NS_PER_SECOND  # the 1-minute exchange kline (§4.1) the NT-D01 kline reading consumes
_DIVERGENCE_NS = 5 * _NS_PER_SECOND  # NT-D03: |trade - book event time| strictly above 5 s
_INDEX_DEVIATION = Fraction(2, 100)  # NT-D04: |price - index| / index strictly above 2%
_WINDOW_NS = 5 * 60 * _NS_PER_SECOND  # NT-D05: UTC 5-minute windows (the NT-D01 span opens on one)
_BASELINE_WINDOWS = 30 * 24 * 12  # NT-D05: the 8640 completed windows of the 30 days before the target window
_VOLUME_FLOOR = Fraction(5, 100)  # NT-D05: target volume strictly below 5% of the 30-day mean
_INDEX_SLOT_NS = _NS_PER_SECOND  # index_one_per_utc_second.v1: at most one index value per UTC second
_IMMUTABLE = "immutable_after_finalization"
# The registry 1.0 semantics of the two market series, exactly as their only producer (authenticated_pit_ingress)
# implements and enforces them on the bound EF-3 series record, field by field and by exact type. A public dataset can
# bypass that producer, so the gate re-proves the same set on the dataset's own authenticated manifest.
_MARKET_SERIES_SEMANTICS: dict[DataRequirementKey, tuple[tuple[str, object], ...]] = {
    DataRequirementKey.LAST_TRADE: (
        ("registry_requirement_bound", True),
        ("finality", "finalized_only"),
        ("revision_policy", _IMMUTABLE),
        ("historical_source", "trade_history_v1"),
        ("event_time_policy", "trade_event_ns"),
        ("available_at_policy", "trade_available_ns"),
        ("finalized_at_policy", "trade_finalized_ns"),
        ("price_semantics", "last_trade"),
        ("sequence_policy", None),  # no native continuity is ever inferred: it is only a declared capture profile
        ("finality_policy", "trade_tick_final"),
    ),
    DataRequirementKey.INDEX_PRICE: (
        ("registry_requirement_bound", True),
        ("finality", "finalized_only"),
        ("revision_policy", _IMMUTABLE),
        ("historical_source", "index_price_history_v1"),
        ("event_time_policy", "index_event_ns"),
        ("available_at_policy", "index_available_ns"),
        ("finalized_at_policy", "index_finalized_ns"),
        ("price_semantics", "index_price"),
        ("sequence_policy", None),
        ("finality_policy", "index_snapshot_final"),
    ),
}

GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID = "governed-paper-entry-safety.v1"
GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID = "governed-paper-entry-safety.v2"
GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID = "governed-paper-entry-safety.v3"
GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_ID = "governed-paper-entry-safety.v4"
GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID = "governed-paper-entry-safety.v5"

GOVERNED_PAPER_ENTRY_SAFETY_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("execution_authorized", False),
    ("venue_orders_created", False),
    ("real_market_source_qualified", False),
    ("venue_facts_proven", False),
    ("timestamp_origin_proven", False),
    ("live_ready", False),
    ("shadow_ready", False),
    ("operational_readiness", False),
    ("stage4_complete", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


class GovernedPaperEntrySafetyError(EdgeArtifactError):
    """Malformed input or a binding defect: an entry-safety evaluation is never represented over it."""


class GovernedPaperEntrySafetyStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED_ON_MISSING_INPUT = "BLOCKED_ON_MISSING_INPUT"
    BLOCKED_PROTECTION_UNREPRESENTABLE = "BLOCKED_PROTECTION_UNREPRESENTABLE"
    PROVEN_NOT_APPLICABLE = "PROVEN_NOT_APPLICABLE"


class GovernedPaperEntrySafetyFamily(str, Enum):
    """The PRDV4 §1.21 evaluation families in their published order, then the §1.9 Family B gates."""

    DATA = "DATA"
    RISK = "RISK"
    REGIME = "REGIME"
    EDGE = "EDGE"
    EXECUTION = "EXECUTION"
    TEMPORAL = "TEMPORAL"
    FAMILY_B = "FAMILY_B"


_ADMITTING = (GovernedPaperEntrySafetyStatus.PASS, GovernedPaperEntrySafetyStatus.PROVEN_NOT_APPLICABLE)

# Rule set v4: why a market-data reading is unavailable (each a fixed vocabulary, never caller text).
_TRADE_SERIES_REASONS = (
    "last_trade_series_not_in_the_selected_data_contract",
    "last_trade_series_ambiguous",
    "last_trade_series_not_final_and_immutable",
    "last_trade_series_semantics_unsupported",
    "last_trade_record_malformed",
)
_TRADE_REASONS = (*_TRADE_SERIES_REASONS, "no_trade_visible_at_the_decision_instant")
_CONTINUITY_REASONS = ("trade_continuity_profile_not_declared", "trade_continuity_declaration_inconsistent")
_TRADE_GAP_REASONS = (
    *_TRADE_REASONS,
    *_CONTINUITY_REASONS,
    "trade_stream_not_observed_back_to_the_span_start",
    "trade_stream_continuity_broken_in_the_span",
)
_KLINE_GAP_REASONS = (
    "exchange_kline_feed_not_in_the_selected_data_contract",
    "kline_origin_undeclared",
    "kline_bars_trade_derived_not_an_exchange_kline_feed",
    "exchange_kline_bars_not_last_trade",
    "exchange_kline_1m_interval_not_declared",
    "exchange_kline_feed_of_another_instrument",
    "no_exchange_kline_bar_visible_at_the_decision_instant",
    "exchange_kline_feed_not_observed_back_to_the_span_start",
)
_INDEX_REASONS = (
    "index_price_series_not_in_the_selected_data_contract",
    "index_price_series_ambiguous",
    "index_price_series_not_final_and_immutable",
    "index_price_series_semantics_unsupported",
    "index_price_record_malformed",
    "index_publication_declaration_inconsistent",
    "index_publication_slot_conflict",
    "no_index_price_visible_at_the_decision_instant",
    "index_price_not_positive",
)
_VOLUME_REASONS = (
    *_TRADE_SERIES_REASONS,
    *_CONTINUITY_REASONS,
    "no_visible_trade_before_the_30d_baseline",
    "no_visible_trade_at_or_after_the_target_window_end",
    "trade_continuity_broken_inside_the_30d_baseline_and_target_windows",
    "volume_unrepresentable",
)


@dataclass(frozen=True)
class GovernedPaperEntrySafetyMarketData:
    """The native market-data facts of one decision at ``t`` (rule set v4), derived from the archive, never accepted.

    ``trade_reason`` is empty exactly when the LAST_TRADE series is usable and a trade is visible: the latest one (by
    native event time, then native id) gives the digest, event time and price. Each NT-D01 feed carries its largest
    observed gap over the span (None when nothing is observed), why the span is not proven continuous (empty when it
    is) and the digest of the records it read. ``index_*`` is the latest visible index likewise, ``index_slot_ns`` its
    declared publication second (None without the profile). NT-D05 carries the exact base-asset volumes of the target
    window and of the 8640 windows before it, present exactly when every window is proven covered.
    """

    trade_reason: str
    trade_record_digest: str | None
    trade_event_time_ns: int | None
    trade_price: str | None
    trade_gap_ns: int | None
    trade_gap_reason: str
    trade_gap_evidence: tuple[str, ...]
    kline_gap_ns: int | None
    kline_gap_reason: str
    kline_gap_evidence: tuple[str, ...]
    index_reason: str
    index_record_digest: str | None
    index_event_time_ns: int | None
    index_price: str | None
    index_slot_ns: int | None
    volume_target: str | None
    volume_baseline: str | None
    volume_reason: str
    volume_evidence: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperEntrySafetyKillSwitch:
    """The kill-switch facts of one decision at ``t`` (rule set v5), derived from the evaluation's ladder, never accepted.

    ``level`` is the PROVEN LOWER BOUND of the PRDV4 §1.19 level at ``t``, never a proven level; ``transition_digest`` is
    the ladder transition that set it and ``proving_trigger_ids`` the triggers that prove it: those proven at ``t``, or
    for an absorbed KS-3 those proven when it was reached (both absent at 0). ``unproven_trigger_ids`` are the triggers
    neither proven TRUE at ``t`` nor proven not applicable, and ``unmeasured_trigger_ids`` those never read TRUE.
    """

    level: int
    proving_trigger_ids: tuple[str, ...]
    unproven_trigger_ids: tuple[str, ...]
    unmeasured_trigger_ids: tuple[str, ...]
    ladder_digest: str
    transition_digest: str | None


@dataclass(frozen=True)
class GovernedPaperEntrySafetyObservation:
    """The point-in-time facts one decision is evaluated on (derived by this module, never caller authority)."""

    decision_sequence: int
    decision_time_ns: int
    decision_digest: str
    instrument: str
    target_direction: str
    family_b_applicable: bool
    genesis_start_ns: int
    latency_tier_id: str
    latency_ns: int
    single_instrument_portfolio: bool
    lifecycle_invalidated: bool
    book_update_record_digest: str | None
    book_update_event_time_ns: int | None
    mark_record_digest: str | None
    mark_price: str | None
    lookback_mark_record_digest: str | None
    lookback_mark_price: str | None
    protection_present: bool = False
    protective_window_covers: bool = False
    protective_authority_digest: str | None = None
    atr_available: bool = False
    atr_value: str | None = None
    atr_reason: str = ""
    atr_window_digest: str | None = None
    stop_tightening_method_id: str | None = None
    # Rule set v3 only: the governed decision portfolio of the decision (absent without one, as in rule sets v1/v2).
    portfolio_present: bool = False
    portfolio_snapshot_digest: str | None = None
    position_quantity: str | None = None
    order_in_flight: bool = False
    portfolio_mark_record_digest: str | None = None  # the snapshot's fresh visible mark, open position or not
    portfolio_mark_price: str | None = None
    portfolio_nav: str | None = None
    portfolio_nav_reason: str = ""
    day_start_ns: int | None = None
    day_start_nav: str | None = None
    day_start_reason: str = ""
    candidate_position_quantity: str | None = None
    candidate_nav: str | None = None
    candidate_nav_reason: str = ""
    # Rule set v4 only: the native market-data facts of the decision (absent without them, as in rule sets v1-v3).
    market_data: GovernedPaperEntrySafetyMarketData | None = None
    # Rule set v5 only: the proven kill-switch facts of the decision (absent without them, as in rule sets v1-v4).
    kill_switch: GovernedPaperEntrySafetyKillSwitch | None = None


@dataclass(frozen=True)
class GovernedPaperEntrySafetyPortfolio:
    """The governed portfolio of one evaluation (rule set v3): the replayed economics and the schedule under evaluation.

    Supplied by the day seal. The decision portfolio itself is derived here by the one engine, never accepted; the
    schedule's entry refusals are the admissions the evaluation is conditioned on, and the seal proves they are the
    evaluation's own (``governed_paper_entry_safety_sequential_refusals``).
    """

    economics: HistoricalExecutionEconomicsResult
    schedule: HistoricalExecutionAdmissionSchedule


@dataclass(frozen=True)
class GovernedPaperEntrySafetyProtection:
    """The protective context of one evaluation (rule set v2): what the economics applies to an admitted entry.

    Supplied by the day seal from verified authorities: the position-management policy the replayed economics binds,
    its authenticated OHLC archive (known at the seal) and the DEC-1 protective window, or None when no protective
    authority covers the lineage.
    """

    position_management_policy: HistoricalPositionManagementPolicy
    ohlc_archive: HistoricalOhlcBarArchive
    protective_window: HistoricalExecutionProtectiveWindow | None


@dataclass(frozen=True)
class GovernedPaperEntrySafetyCheck:
    """One evaluated check: its status, the observed value (empty when unavailable), the published threshold."""

    check_id: str
    family: GovernedPaperEntrySafetyFamily
    status: GovernedPaperEntrySafetyStatus
    observed: str
    threshold: str
    reason: str
    evidence_record_digests: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperEntrySafetyDecision:
    """Every check of one entry decision, in evaluation order, and the first one that refuses the entry."""

    decision_sequence: int
    decision_time_ns: int
    decision_digest: str
    instrument: str
    target_direction: str
    checks: tuple[GovernedPaperEntrySafetyCheck, ...]
    entry_permitted: bool
    first_failure_check_id: str
    first_failure_reason: str


@dataclass(frozen=True)
class GovernedPaperEntrySafetyEvidence:
    """The entry-safety evaluation of every entry decision of one decision run; ``evidence_digest`` covers the rest."""

    schema_version: str
    rule_set_id: str
    rule_set_digest: str
    genesis_id: str
    genesis_digest: str
    run_digest: str
    dataset_digest: str
    economics_policy_digest: str
    instrument: str
    profile_id: str
    family_b_applicable: bool
    invalidated_from_ns: int | None
    decisions: tuple[GovernedPaperEntrySafetyDecision, ...]
    refused_decision_sequences: tuple[int, ...]
    evidence_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    venue_orders_created: bool = False
    real_market_source_qualified: bool = False
    venue_facts_proven: bool = False
    timestamp_origin_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    stage4_complete: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    # Rule set v5 only: the proven lower-bound §1.19 ladder the evaluation read (never in a v1-v4 payload).
    kill_switch_ladder: GovernedPaperKillSwitchLadder | None = None


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperEntrySafetyError:
    return GovernedPaperEntrySafetyError(_reason(code))


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


def _evidence_payload(evidence: GovernedPaperEntrySafetyEvidence) -> dict[str, object]:
    """The wire payload of one evaluation; a v1-v4 payload is exactly its accepted one and carries no ladder.

    A v1-v4 evidence holding a ladder is never serialized (``ValueError``): a forged ladder never hides behind it.
    """

    payload = _to_payload(evidence)
    if evidence.rule_set_id != GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID:
        if evidence.kill_switch_ladder is not None:
            raise ValueError(f"{_PREFIX}:legacy_rule_set_carries_a_kill_switch_ladder")
        del payload["kill_switch_ladder"]
    return payload


# --- the checks --------------------------------------------------------------------------------------------------------

_Status = GovernedPaperEntrySafetyStatus
_Family = GovernedPaperEntrySafetyFamily
_Observation = GovernedPaperEntrySafetyObservation


@dataclass(frozen=True)
class _Outcome:
    status: GovernedPaperEntrySafetyStatus
    observed: str
    reason: str
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Check:
    check_id: str
    family: GovernedPaperEntrySafetyFamily
    clause: str
    threshold: str
    evaluate: Callable[[GovernedPaperEntrySafetyObservation], _Outcome]


def _missing(reason: str) -> Callable[[_Observation], _Outcome]:
    def evaluate(observation: _Observation) -> _Outcome:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason)

    return evaluate


def _family_b(evaluate: Callable[[_Observation], _Outcome]) -> Callable[[_Observation], _Outcome]:
    def gated(observation: _Observation) -> _Outcome:
        if not observation.family_b_applicable:
            return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "family_b_applicability_undetermined")
        return evaluate(observation)

    return gated


def _book_staleness(observation: _Observation) -> _Outcome:
    if observation.book_update_event_time_ns is None or observation.book_update_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "no_order_book_update_visible_at_the_decision_instant")
    evidence = (observation.book_update_record_digest,)
    age = observation.decision_time_ns - observation.book_update_event_time_ns
    if age < 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, str(age), "order_book_update_after_the_decision", evidence)
    if age > _BOOK_STALE_AFTER_NS:
        return _Outcome(_Status.FAIL, str(age), "last_l2_update_older_than_10s", evidence)
    return _Outcome(_Status.PASS, str(age), "last_l2_update_within_10s", evidence)


def _edge_state(observation: _Observation) -> _Outcome:
    if observation.lifecycle_invalidated:
        return _Outcome(_Status.FAIL, "EF8_DISABLED_OR_QUARANTINE", "edge_lifecycle_disabled_at_or_before_the_decision")
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "prdv4_edge_state_machine_not_produced")


def _correlation(observation: _Observation) -> _Outcome:
    if observation.single_instrument_portfolio:
        return _Outcome(
            _Status.PROVEN_NOT_APPLICABLE, "", "single_instrument_paper_portfolio_has_no_pairwise_correlation"
        )
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "cross_asset_correlation_not_measured")


def _latency(observation: _Observation) -> _Outcome:
    budget = _TIER_LATENCY_BUDGET_NS.get(observation.latency_tier_id)
    if budget is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "latency_tier_budget_unknown")
    observed = str(observation.latency_ns)
    if observation.latency_ns > _LATENCY_BREACH_MULTIPLE * budget:
        return _Outcome(_Status.FAIL, observed, "simulated_latency_above_five_times_the_tier_budget")
    return _Outcome(_Status.PASS, observed, "simulated_latency_within_five_times_the_tier_budget")


def _startup(observation: _Observation) -> _Outcome:
    elapsed = observation.decision_time_ns - observation.genesis_start_ns
    if elapsed < 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, str(elapsed), "decision_before_the_paper_engine_start")
    if elapsed < _STARTUP_WARMUP_NS:
        return _Outcome(_Status.FAIL, str(elapsed), "inside_the_first_5_minutes_after_the_paper_engine_start")
    return _Outcome(_Status.PASS, str(elapsed), "after_the_startup_warmup")


def _anti_trend(observation: _Observation) -> _Outcome:
    if observation.mark_price is None or observation.mark_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "mark_unavailable_at_the_decision_instant")
    if observation.lookback_mark_price is None or observation.lookback_mark_record_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "mark_unavailable_4h_before_the_decision_instant")
    evidence = (observation.lookback_mark_record_digest, observation.mark_record_digest)
    move = Fraction(observation.mark_price) / Fraction(observation.lookback_mark_price) - 1
    observed = historical_execution_render_amount(move)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "r_4h_unrepresentable", evidence)
    if observation.target_direction == "SHORT":
        triggered = move > _ANTI_TREND_BOUND
    else:
        triggered = move < -_ANTI_TREND_BOUND
    if triggered:
        return _Outcome(_Status.FAIL, observed, "anti_trend_entry_blocked_and_override_unprovable", evidence)
    return _Outcome(_Status.PASS, observed, "anti_trend_bound_not_crossed", evidence)


_HORIZON_NOT_COVERED = "protective_authority_does_not_cover_the_holding_horizon"


def _max_hold(observation: _Observation) -> _Outcome:
    if not observation.protection_present:
        return _Outcome(
            _Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", "holding_period_exit_not_representable_on_the_selected_path"
        )
    if not observation.protective_window_covers or observation.protective_authority_digest is None:
        return _Outcome(_Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", _HORIZON_NOT_COVERED)
    evidence = (observation.protective_authority_digest,)
    return _Outcome(_Status.PASS, "", "max_hold_close_only_obligation_enforced_by_the_engine", evidence)


def _stop(observation: _Observation) -> _Outcome:
    if not observation.protection_present:
        return _Outcome(
            _Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", "atr_4h_stop_exit_not_representable_on_the_selected_path"
        )
    if not observation.protective_window_covers or observation.protective_authority_digest is None:
        return _Outcome(_Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", _HORIZON_NOT_COVERED)
    if not observation.atr_available or observation.atr_value is None or observation.atr_window_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", f"atr_4h_unavailable:{observation.atr_reason}")
    evidence = (observation.protective_authority_digest, observation.atr_window_digest)
    return _Outcome(_Status.PASS, observation.atr_value, "atr_4h_stop_enforced_by_the_engine", evidence)


def _tightening(observation: _Observation) -> _Outcome:
    if not observation.protection_present:
        return _Outcome(
            _Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", "stop_tightening_not_representable_on_the_selected_path"
        )
    if observation.stop_tightening_method_id == TIGHTENING_DEC9_READING_V1:
        return _Outcome(
            _Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", "dec9_tightening_reading_requires_human_approval"
        )
    return _Outcome(_Status.BLOCKED_PROTECTION_UNREPRESENTABLE, "", "stop_tightening_not_applied_pending_dec9")


@dataclass(frozen=True)
class _Portfolio:
    """A measured governed portfolio: its snapshot evidence, its exact position and the decision's exact candidate."""

    evidence: tuple[str, ...]
    quantity: Fraction
    candidate: Fraction

    @property
    def entry(self) -> bool:
        """Whether the candidate increases the magnitude of the position: a prospective entry."""

        return abs(self.candidate) > abs(self.quantity)


def _measured_portfolio(observation: _Observation, legacy_reason: str) -> _Outcome | _Portfolio:
    """The BLOCKED outcome without a measured governed portfolio, else the measured portfolio.

    Without a governed portfolio (rule sets v1 and v2) the outcome is exactly the earlier missing-input outcome.
    """

    if not observation.portfolio_present:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", legacy_reason)
    if not observation.single_instrument_portfolio:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "paper_portfolio_holds_more_than_the_genesis_sleeve")
    digest, quantity = observation.portfolio_snapshot_digest, observation.position_quantity
    candidate = observation.candidate_position_quantity
    if digest is None or quantity is None or candidate is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "governed_portfolio_not_computed")
    return _Portfolio((digest,), Fraction(quantity), Fraction(candidate))


def _nav_unavailable(observation: _Observation) -> str:
    return f"nav_unavailable:{observation.portfolio_nav_reason}"


def _daily_loss(observation: _Observation) -> _Outcome:
    measured = _measured_portfolio(observation, "intraday_portfolio_pnl_and_nav_not_measured_at_the_decision_instant")
    if isinstance(measured, _Outcome):
        return measured
    evidence = measured.evidence
    start_text, nav_text = observation.day_start_nav, observation.portfolio_nav
    if start_text is None:
        reason = f"utc_day_start_nav_unavailable:{observation.day_start_reason}"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, evidence)
    if nav_text is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", _nav_unavailable(observation), evidence)
    start = Fraction(start_text)
    if start <= 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "utc_day_start_nav_not_positive", evidence)
    change = (Fraction(nav_text) - start) / start
    observed = historical_execution_render_amount(change)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "intraday_pnl_ratio_unrepresentable", evidence)
    if change < _DAILY_LOSS_LIMIT:
        return _Outcome(_Status.FAIL, observed, "intraday_loss_beyond_2pct_of_the_day_start_nav", evidence)
    return _Outcome(_Status.PASS, observed, "intraday_loss_within_2pct_of_the_day_start_nav", evidence)


def _open_risk(observation: _Observation) -> _Outcome:
    measured = _measured_portfolio(observation, "portfolio_position_risk_not_measured_at_the_decision_instant")
    if isinstance(measured, _Outcome):
        return measured
    evidence = measured.evidence
    if measured.quantity != 0:
        reason = "position_risk_measure_undefined_for_an_open_position"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, evidence)
    if observation.order_in_flight:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "an_order_in_flight_may_open_exposure", evidence)
    nav_text = observation.portfolio_nav
    if nav_text is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", _nav_unavailable(observation), evidence)
    if Fraction(nav_text) <= 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "portfolio_equity_not_positive", evidence)
    # CURRENT_POSITION_MEASUREMENT: no position and no order in flight carry exactly zero open risk (the observed value).
    # PROSPECTIVE_ENTRY_ELIGIBILITY: the position an entry would open has no approved risk measure, so zero present risk
    # never approves it.
    if measured.entry:
        reason = "prospective_entry_position_risk_measure_undefined"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, _ZERO_RENDERING, reason, evidence)
    return _Outcome(_Status.PASS, _ZERO_RENDERING, "no_position_and_no_order_in_flight_carry_risk", evidence)


def _concentration(observation: _Observation) -> _Outcome:
    measured = _measured_portfolio(observation, "portfolio_position_concentration_not_measured_at_the_decision_instant")
    if isinstance(measured, _Outcome):
        return measured
    evidence = measured.evidence
    nav_text, mark_text = observation.portfolio_nav, observation.portfolio_mark_price
    if nav_text is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", _nav_unavailable(observation), evidence)
    nav = Fraction(nav_text)
    if nav <= 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "nav_not_positive", evidence)
    # an available NAV values an open position at its fresh visible mark; a flat portfolio holds no exposure
    share = Fraction(0) if mark_text is None else abs(measured.quantity) * Fraction(mark_text) / nav
    observed = historical_execution_render_amount(share)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "position_share_unrepresentable", evidence)
    if share > _CONCENTRATION_CAP:
        return _Outcome(_Status.FAIL, observed, "single_position_above_25pct_of_nav", evidence)
    if not measured.entry:
        return _Outcome(_Status.PASS, observed, "single_position_within_25pct_of_nav", evidence)
    # The prospective entry, at the decision mark net of its own taker fee; its fill is bounded exactly by the engine.
    candidate_text = observation.candidate_nav
    if candidate_text is None or mark_text is None:  # the canonical facts bind a candidate NAV to a fresh mark
        reason = f"candidate_nav_unavailable:{observation.candidate_nav_reason}"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, evidence)
    candidate_nav = Fraction(candidate_text)
    if candidate_nav <= 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "candidate_nav_not_positive", evidence)
    share = abs(measured.candidate) * Fraction(mark_text) / candidate_nav
    observed = historical_execution_render_amount(share)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "candidate_share_unrepresentable", evidence)
    if share > _CONCENTRATION_CAP:
        return _Outcome(_Status.FAIL, observed, "candidate_position_above_25pct_of_nav", evidence)
    return _Outcome(_Status.PASS, observed, "candidate_position_within_25pct_of_nav_and_bounded_at_its_fill", evidence)


def _gap_text(gap: int | None) -> str:
    return "unobserved" if gap is None else str(gap)


def _feed_gap(observation: _Observation) -> _Outcome:
    """NT-D01 (rule set v4): an observed gap above its bound FAILs; a PASS needs both feeds proven over the span."""

    data = observation.market_data
    if data is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "trade_and_kline_feeds_not_in_the_selected_data_contract")
    observed = f"trade_gap_ns={_gap_text(data.trade_gap_ns)};kline_gap_ns={_gap_text(data.kline_gap_ns)}"
    evidence = (*data.trade_gap_evidence, *data.kline_gap_evidence)
    if data.trade_gap_ns is not None and data.trade_gap_ns > _TRADE_GAP_NS:
        return _Outcome(_Status.FAIL, observed, "trade_stream_gap_above_60s", evidence)
    if data.kline_gap_ns is not None and data.kline_gap_ns > _KLINE_GAP_NS:
        return _Outcome(_Status.FAIL, observed, "kline_feed_gap_above_5min", evidence)
    for reason in (data.trade_gap_reason, data.kline_gap_reason):
        if reason:
            return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, observed, reason, evidence)
    return _Outcome(_Status.PASS, observed, "trade_and_kline_feeds_continuous_within_their_gap_bounds", evidence)


def _timestamp_divergence(observation: _Observation) -> _Outcome:
    """NT-D03 (rule set v4): native event times of the latest visible trade and L2 update, never receipt times."""

    data = observation.market_data
    if data is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "trade_stream_not_in_the_selected_data_contract")
    if data.trade_reason:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", data.trade_reason)
    book_event, book_digest = observation.book_update_event_time_ns, observation.book_update_record_digest
    if book_event is None or book_digest is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "no_order_book_update_visible_at_the_decision_instant")
    evidence = (data.trade_record_digest, book_digest)  # type: ignore[assignment]
    if book_event > observation.decision_time_ns:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "order_book_update_after_the_decision", evidence)  # type: ignore[arg-type]
    divergence = abs(data.trade_event_time_ns - book_event)  # type: ignore[operator]
    if divergence > _DIVERGENCE_NS:
        return _Outcome(_Status.FAIL, str(divergence), "trade_book_event_time_divergence_above_5s", evidence)  # type: ignore[arg-type]
    return _Outcome(_Status.PASS, str(divergence), "trade_book_event_time_divergence_within_5s", evidence)  # type: ignore[arg-type]


def _index_deviation(observation: _Observation) -> _Outcome:
    """NT-D04 (rule set v4): the latest trade price against the latest index, both proven current at ``t``."""

    data = observation.market_data
    if data is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "index_price_series_not_in_the_selected_data_contract")
    if data.trade_reason:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", data.trade_reason)
    instant = observation.decision_time_ns
    if instant - data.trade_event_time_ns > _TRADE_GAP_NS:  # type: ignore[operator]
        reason = "last_trade_not_current_beyond_the_nt_d01_60s_trade_bound"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, (data.trade_record_digest,))  # type: ignore[arg-type]
    if data.index_reason:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", data.index_reason)
    evidence = (data.trade_record_digest, data.index_record_digest)
    slot = data.index_slot_ns
    if slot is None:
        reason = "index_currency_unprovable_without_a_declared_publication_profile"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, evidence)  # type: ignore[arg-type]
    if instant >= (data.index_event_time_ns // slot + 1) * slot:  # type: ignore[operator]
        reason = "index_publication_second_elapsed_at_the_decision_instant"
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, evidence)  # type: ignore[arg-type]
    index = Fraction(data.index_price)  # type: ignore[arg-type]
    deviation = abs(Fraction(data.trade_price) - index) / index  # type: ignore[arg-type]
    observed = historical_execution_render_amount(deviation)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "price_index_deviation_unrepresentable", evidence)  # type: ignore[arg-type]
    if deviation > _INDEX_DEVIATION:
        return _Outcome(_Status.FAIL, observed, "last_trade_deviates_from_the_index_beyond_2pct", evidence)  # type: ignore[arg-type]
    return _Outcome(_Status.PASS, observed, "last_trade_within_2pct_of_the_index", evidence)  # type: ignore[arg-type]


def _volume_anomaly(observation: _Observation) -> _Outcome:
    """NT-D05 (rule set v4): the latest completed 5-minute volume against the 30-day mean of proven-covered windows."""

    data = observation.market_data
    if data is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "volume_series_not_in_the_selected_data_contract")
    if data.volume_reason:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", data.volume_reason)
    evidence = data.volume_evidence
    baseline = Fraction(data.volume_baseline)  # type: ignore[arg-type]
    if baseline <= 0:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "thirty_day_mean_5min_volume_not_positive", evidence)
    mean = baseline / _BASELINE_WINDOWS
    share = Fraction(data.volume_target) / mean  # type: ignore[arg-type]
    observed = historical_execution_render_amount(share)
    if observed is None:
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "volume_share_unrepresentable", evidence)
    if share < _VOLUME_FLOOR:
        return _Outcome(_Status.FAIL, observed, "volume_5min_below_5pct_of_the_30d_mean", evidence)
    return _Outcome(_Status.PASS, observed, "volume_5min_at_or_above_5pct_of_the_30d_mean", evidence)


def _trigger_text(ids: tuple[str, ...]) -> str:
    return "_".join(ids).lower() if ids else "none"


def _kill_switch_level(observation: _Observation) -> _Outcome:
    """NT-R01: FAIL only on a proven lower bound of KS-2 or more (rule set v5), BLOCKED otherwise, never PASS."""

    facts = observation.kill_switch
    if facts is None:  # rule sets v1-v4: exactly the earlier missing-input outcome
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "kill_switch_ladder_level_not_produced")
    evidence = (
        (facts.ladder_digest,) if facts.transition_digest is None else (facts.ladder_digest, facts.transition_digest)
    )
    if facts.level >= 2:
        reason = f"kill_switch_level_ge_2_proven_by_{_trigger_text(facts.proving_trigger_ids)}"
        return _Outcome(_Status.FAIL, str(facts.level), reason, evidence)
    reason = f"kill_switch_lower_bound_{facts.level}_unproven_{_trigger_text(facts.unproven_trigger_ids)}"
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, str(facts.level), reason, evidence)


def _kill_switch_cooldown(observation: _Observation) -> _Outcome:
    """NT-T02: BLOCKED under rule set v5 too; no absence of a cool-down is ever claimed."""

    facts = observation.kill_switch
    if facts is None:  # rule sets v1-v4: exactly the earlier missing-input outcome
        return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", "kill_switch_cooldown_state_not_produced")
    reason = f"kill_switch_cooldown_history_unprovable_unmeasured_{_trigger_text(facts.unmeasured_trigger_ids)}"
    return _Outcome(_Status.BLOCKED_ON_MISSING_INPUT, "", reason, (facts.ladder_digest,))


_D, _R, _M, _E, _X, _T, _B = (
    _Family.DATA,
    _Family.RISK,
    _Family.REGIME,
    _Family.EDGE,
    _Family.EXECUTION,
    _Family.TEMPORAL,
    _Family.FAMILY_B,
)
_CHECKS: tuple[_Check, ...] = (
    _Check(
        "NT-D01",
        _D,
        "PRDV4 §1.21 NT-D01 OHLCV feed gap",
        "trade_stream_gap_gt_60s_or_kline_gap_gt_5min",
        _feed_gap,
    ),
    _Check("NT-D02", _D, "PRDV4 §1.21 NT-D02 order book stale", "last_l2_update_age_gt_10s", _book_staleness),
    _Check(
        "NT-D03",
        _D,
        "PRDV4 §1.21 NT-D03 trade/book timestamp divergence",
        "abs_trade_book_timestamp_divergence_gt_5s",
        _timestamp_divergence,
    ),
    _Check(
        "NT-D04",
        _D,
        "PRDV4 §1.21 NT-D04 price vs index deviation",
        "abs_price_minus_index_over_index_gt_2pct",
        _index_deviation,
    ),
    _Check(
        "NT-D05",
        _D,
        "PRDV4 §1.21 NT-D05 volume anomaly",
        "volume_5min_lt_5pct_of_the_30d_mean_5min_volume",
        _volume_anomaly,
    ),
    _Check(
        "NT-R01",
        _R,
        "PRDV4 §1.21 NT-R01 kill-switch active (§1.19)",
        "kill_switch_level_ge_2",
        _kill_switch_level,
    ),
    _Check(
        "NT-R02",
        _R,
        "PRDV4 §1.21 NT-R02 daily loss limit",
        "intraday_pnl_over_nav_lt_minus_2pct",
        _daily_loss,
    ),
    _Check(
        "NT-R03",
        _R,
        "PRDV4 §1.21 NT-R03 open risk cap",
        "sum_position_risk_over_equity_gt_4pct",
        _open_risk,
    ),
    _Check(
        "NT-R04",
        _R,
        "PRDV4 §1.21 NT-R04 position concentration",
        "any_position_gt_25pct_of_nav",
        _concentration,
    ),
    _Check(
        "NT-R05",
        _R,
        "PRDV4 §1.21 NT-R05 CVaR budget exhausted (§1.18)",
        "portfolio_cvar99_ge_5pct_of_nav",
        _missing("portfolio_cvar99_not_produced"),
    ),
    _Check(
        "NT-R06",
        _R,
        "PRDV4 §1.21 NT-R06 margin utilization",
        "used_margin_gt_80pct_of_available",
        _missing("margin_utilization_not_modeled"),
    ),
    _Check(
        "NT-M01",
        _M,
        "PRDV4 §1.21 NT-M01 liquidity regime CRISIS (§1.17)",
        "liq_lt_0.15_sustained_gt_30min",
        _missing("liquidity_regime_not_produced"),
    ),
    _Check(
        "NT-M02",
        _M,
        "PRDV4 §1.21 NT-M02 leverage regime EXTREME (§1.17)",
        "open_interest_over_market_cap_gt_0.10",
        _missing("open_interest_and_market_cap_not_in_the_selected_data_contract"),
    ),
    _Check(
        "NT-M03",
        _M,
        "PRDV4 §1.21 NT-M03 regime transition in progress",
        "any_regime_dimension_in_its_hysteresis_window",
        _missing("regime_hysteresis_state_not_produced"),
    ),
    _Check(
        "NT-M04",
        _M,
        "PRDV4 §1.21 NT-M04 correlation breakdown",
        "mean_pairwise_correlation_gt_0.85",
        _correlation,
    ),
    _Check(
        "NT-E01",
        _E,
        "PRDV4 §1.21 NT-E01 edge health score (§1.6)",
        "edge_health_score_lt_0.30",
        _missing("edge_health_score_not_produced"),
    ),
    _Check("NT-E02", _E, "PRDV4 §1.21 NT-E02 edge in DISABLED state", "edge_state_machine_disabled", _edge_state),
    _Check(
        "NT-E03",
        _E,
        "PRDV4 §1.21 NT-E03 edge capacity RED (§1.15)",
        "utilization_ge_80pct_of_kmax",
        _missing("edge_capacity_kmax_and_utilization_not_produced"),
    ),
    _Check(
        "NT-E04",
        _E,
        "PRDV4 §1.21 NT-E04 no valid edge for asset",
        "zero_edges_with_edge_health_score_gt_0.50",
        _missing("edge_health_score_not_produced"),
    ),
    _Check(
        "NT-X01",
        _X,
        "PRDV4 §1.21 NT-X01 latency breach (§1.16)",
        "latency_gt_5x_the_tier_budget_t1_100ms",
        _latency,
    ),
    _Check(
        "NT-X02",
        _X,
        "PRDV4 §1.21 NT-X02 fill rate degradation",
        "last_10_orders_fill_rate_lt_50pct",
        _missing("exchange_order_fill_rate_not_observable_on_the_paper_path"),
    ),
    _Check(
        "NT-X03",
        _X,
        "PRDV4 §1.21 NT-X03 spread anomaly",
        "spread_gt_3x_the_30d_median",
        _missing("thirty_day_median_spread_needs_proven_complete_book_coverage"),
    ),
    _Check(
        "NT-X04",
        _X,
        "PRDV4 §1.21 NT-X04 exchange maintenance",
        "scheduled_or_detected_maintenance_window",
        _missing("exchange_maintenance_schedule_not_produced"),
    ),
    _Check("NT-T01", _T, "PRDV4 §1.21 NT-T01 system startup", "first_5min_after_the_engine_start", _startup),
    _Check(
        "NT-T02",
        _T,
        "PRDV4 §1.21 NT-T02 post-kill-switch cool-down (§1.19)",
        "inside_the_kill_switch_cooldown",
        _kill_switch_cooldown,
    ),
    _Check(
        "NT-T03",
        _T,
        "PRDV4 §1.21 NT-T03 high-impact event window",
        "within_15min_of_a_known_macro_event",
        _missing("macro_event_calendar_not_produced"),
    ),
    _Check(
        "FB-TREND",
        _B,
        "PRDV4 §1.9 trend filter",
        "funding_extreme_and_trend_strength_aligned_ts_gt_1.5",
        _family_b(_missing("trend_strength_ema_atr_construction_not_defined_or_produced")),
    ),
    _Check(
        "FB-REGIME",
        _B,
        "PRDV4 §1.9 regime filter",
        "regime_not_range_or_high_vol_or_crisis",
        _family_b(_missing("regime_state_not_produced")),
    ),
    _Check(
        "FB-REGIME-COOLDOWN",
        _B,
        "PRDV4 §1.9 regime filter transition cooldown",
        "trending_within_the_last_4h_suppresses_4h",
        _family_b(_missing("trending_regime_history_not_produced")),
    ),
    _Check(
        "FB-ANTITREND",
        _B,
        "PRDV4 §1.9 anti-trend protection",
        "short_with_r4h_gt_plus_2pct_or_long_with_r4h_lt_minus_2pct",
        _family_b(_anti_trend),
    ),
    _Check(
        "FB-MAX-HOLD",
        _B,
        "PRDV4 §1.9 position management maximum holding period",
        "maximum_holding_period_24h",
        _family_b(_max_hold),
    ),
    _Check(
        "FB-STOP",
        _B,
        "PRDV4 §1.9 position management mandatory stop",
        "stop_at_1.5x_atr4h_from_entry",
        _family_b(_stop),
    ),
    _Check(
        "FB-STOP-TIGHTENING",
        _B,
        "PRDV4 §1.9 position management time-decay stop",
        "stop_tightened_by_20pct_every_8h",
        _family_b(_tightening),
    ),
)


def governed_paper_entry_safety_rule_set(
    *, protective: bool = False, portfolio: bool = False, market_data: bool = False, kill_switch: bool = False
) -> dict[str, object]:
    """The rule set this module evaluates: every check, in order, with its PRDV4 clause and published threshold.

    ``protective=True`` is rule set v2: the same checks, with the §1.9 position-management gates evaluated against the
    protective context of ``PROTECTIVE_POSITION_LIFECYCLE_V1`` (see the module docstring). ``portfolio=True`` (only
    with ``protective=True``) is rule set v3: rule set v2 with NT-R02, NT-R03 and NT-R04 evaluated on the governed
    decision portfolio of ``S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1``. ``market_data=True`` (only with
    ``portfolio=True``) is rule set v4: rule set v3 with NT-D01, NT-D03, NT-D04 and NT-D05 measured on the archive's
    market data (``S1_MARKET_DATA_INTEGRITY_NATIVE_MEASUREMENT_CLOSURE_V1``). ``kill_switch=True`` (only with
    ``market_data=True``) is rule set v5: rule set v4 with NT-R01 and NT-T02 read on the proven lower-bound §1.19 ladder
    (``S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1``).
    """

    if portfolio and not protective:
        raise _fail("portfolio_rule_set_needs_the_protective_rule_set")
    if market_data and not portfolio:
        raise _fail("market_data_rule_set_needs_the_portfolio_rule_set")
    if kill_switch and not market_data:
        raise _fail("kill_switch_rule_set_needs_the_market_data_rule_set")

    rule_set: dict[str, object] = {
        "rule_set_id": GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
        "contract_id": "S1_PAPER_ENTRY_SAFETY_CLOSURE_V1",
        "authorities": ["PRDV4 §1.21", "PRDV4 §1.9", "PRDV4 §1.16", "PRDV4 §1.1 Family B"],
        "entry_rule": "decisions_with_a_LONG_or_SHORT_resulting_direction_are_evaluated_and_only_a_magnitude_increasing_intent_is_refused",
        "first_failure_rule": "the_first_check_in_order_that_is_neither_PASS_nor_PROVEN_NOT_APPLICABLE_refuses_the_entry",
        "override_rule": "none",
        "prdv4_no_trade_count": "heading_declares_23_tables_enumerate_26_ids_every_enumerated_id_is_evaluated",
        "family_b_profiles": [PASSIVE_FUNDING_CARRY_V1],
        "visible_observation_rule": "historical_execution_visible_observations",
        "checks": [
            {"check_id": item.check_id, "family": item.family.value, "clause": item.clause, "threshold": item.threshold}
            for item in _CHECKS
        ],
    }
    if protective:
        rule_set.update(
            rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID,
            contract_id="PROTECTIVE_POSITION_LIFECYCLE_V1",
            protective_rule={
                "FB-MAX-HOLD": "pass_when_the_dec1_protective_window_covers_t_to_t_plus_24h_plus_two_max_execution_delays",
                "FB-STOP": "pass_when_the_horizon_is_covered_and_the_dec7_atr_4h_reading_at_t_is_available",
                "FB-STOP-TIGHTENING": "blocked_dec9_tightening_reading_requires_human_approval",
                "max_hold_ns": MAX_HOLD_NS,
            },
        )
    if portfolio:
        rule_set.update(
            rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID,
            contract_id="S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1",
            portfolio_rule={
                "source": "historical_execution_governed_paper_decision_portfolio_v1_derived_by_the_one_engine",
                "schedule": "information_time_admission_schedule_v4_of_a_position_managed_baseline",
                "instant": "the_decision_instant_before_its_admission_after_same_instant_funding_and_protective_rules",
                "scope": "the_paper_portfolio_is_exactly_the_genesis_sleeve_otherwise_blocked",
                "nav": "initial_equity_plus_realized_minus_fees_plus_funding_plus_unrealized_at_the_fresh_visible_mark",
                "unavailable": "a_nav_without_a_fresh_visible_mark_or_an_amount_outside_the_numeric_domain_is_blocked",
                "funding_currency": "a_settlement_whose_final_rate_is_not_visible_reaches_no_decision_or_fill_admission",
                "candidate": "the_position_the_decision_intent_targets_if_admitted_and_filled_in_full",
                "NT-R02": "nav_minus_utc_day_start_nav_over_utc_day_start_nav_strictly_below_minus_2pct",
                "NT-R02_day_start": "the_engine_valuation_at_the_utc_midnight_otherwise_blocked_never_substituted",
                "NT-R03": "zero_current_open_risk_only_flat_without_an_order_in_flight_a_prospective_entry_is_blocked",
                "NT-R04": "the_current_share_and_an_entry_candidates_share_net_of_its_fee_at_the_mark_strictly_above_25pct",
                "NT-R04_fill": "the_engine_refuses_an_entry_fill_whose_exact_post_fill_share_is_strictly_above_25pct",
                "admission": "each_entry_on_the_portfolio_its_admitted_predecessors_produced_the_unique_fixed_point",
                "daily_loss_limit": _render_threshold(_DAILY_LOSS_LIMIT),
                "concentration_cap": _render_threshold(_CONCENTRATION_CAP),
            },
        )
    if market_data:
        rule_set.update(
            rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_ID,
            contract_id="S1_MARKET_DATA_INTEGRITY_NATIVE_MEASUREMENT_CLOSURE_V1",
            market_data_rule={
                "series": "the_one_final_immutable_last_trade_and_index_price_series_of_the_genesis_data_contract_"
                "covering_the_instrument_with_their_registry_1_0_semantics",
                "visibility": "a_record_is_read_once_available_and_final_at_or_before_t_latest_by_event_time_then_id",
                "substitution": "none_an_undeclared_series_is_blocked_and_no_mark_mid_or_book_stands_in_for_it",
                "kline_feed": "the_protective_ohlc_archive_only_when_its_source_declares_the_exchange_kline_origin_"
                "last_trade_bars_and_the_1m_interval",
                "NT-D01_span": "from_the_open_of_the_latest_completed_utc_5min_window_to_t",
                "NT-D01_trade": "largest_gap_of_consecutive_visible_trades_from_the_latest_at_or_before_the_span_start_"
                "and_from_the_newest_to_t_by_native_event_time_strictly_above_60s",
                "NT-D01_kline": "largest_gap_of_consecutive_visible_1m_exchange_klines_from_the_latest_closing_at_or_"
                "before_the_span_start_and_from_the_newest_close_to_t_strictly_above_5min",
                "NT-D01_pass": "both_feeds_observed_back_to_the_span_start_and_the_trades_one_contiguous_run_of_the_"
                "declared_trade_continuity_profile",
                "NT-D03": "abs_native_event_time_of_the_latest_visible_trade_minus_the_latest_visible_l2_update_"
                "strictly_above_5s",
                "NT-D04": "abs_latest_visible_trade_price_minus_the_latest_visible_index_over_the_index_strictly_"
                "above_2pct",
                "NT-D04_currency": "the_trade_within_the_nt_d01_60s_trade_bound_and_the_index_inside_the_utc_second_"
                "of_its_declared_publication_profile",
                "NT-D05": "base_asset_volume_of_the_latest_completed_utc_5min_window_strictly_below_5pct_of_the_mean_"
                "of_the_8640_completed_windows_before_it",
                "NT-D05_coverage": "one_contiguous_run_of_the_declared_trade_continuity_profile_from_a_visible_trade_"
                "strictly_before_the_first_window_to_one_at_or_after_the_target_window_end",
                "trade_continuity_profile": NativeTradeContinuityProfile.CONTIGUOUS_TRADE_ID_V1.value,
                "index_publication_profile": NativeIndexPublicationProfile.ONE_PER_UTC_SECOND_V1.value,
                "trade_gap_ns": _TRADE_GAP_NS,
                "kline_gap_ns": _KLINE_GAP_NS,
                "kline_interval_ns": _KLINE_INTERVAL_NS,
                "divergence_ns": _DIVERGENCE_NS,
                "index_deviation": _render_threshold(_INDEX_DEVIATION),
                "volume_window_ns": _WINDOW_NS,
                "baseline_windows": _BASELINE_WINDOWS,
                "volume_floor": _render_threshold(_VOLUME_FLOOR),
            },
        )
    if kill_switch:
        rule_set.update(
            rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID,
            contract_id="S1_KILL_SWITCH_PROVEN_ESCALATION_CLOSURE_V1",
            kill_switch_rule={
                "ladder_rule_id": GOVERNED_PAPER_KILL_SWITCH_RULE_ID,
                "ladder_rule_digest": GOVERNED_PAPER_KILL_SWITCH_RULE_DIGEST,
                "source": "the_proven_lower_bound_ladder_of_the_decision_portfolio_and_governed_outcome_of_one_engine_"
                "re_run_under_the_schedule_under_evaluation",
                "NT-R01": "fail_exactly_when_the_proven_lower_bound_at_t_is_at_least_ks_2_otherwise_blocked_never_pass",
                "NT-R01_observed": "the_proven_lower_bound_of_the_kill_switch_level_never_a_proven_level",
                "NT-R01_blocked": "names_every_trigger_neither_proven_true_at_t_nor_proven_not_applicable",
                "NT-T02": "blocked_no_cooldown_state_is_exact_over_an_incomplete_trigger_history",
                "admission": "the_ladder_at_t_reads_only_the_admissions_before_t_the_sequential_fixed_point_is_unchanged",
            },
        )
    return rule_set


def _render_threshold(value: Fraction) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:  # pragma: no cover - the PRDV4 thresholds are representable
        raise _fail("threshold_unrepresentable")
    return rendered


def governed_paper_entry_safety_rule_set_digest(
    *, protective: bool = False, portfolio: bool = False, market_data: bool = False, kill_switch: bool = False
) -> str:
    return edge_sha256_text(
        edge_canonical_json(
            governed_paper_entry_safety_rule_set(
                protective=protective, portfolio=portfolio, market_data=market_data, kill_switch=kill_switch
            )
        )
    )


GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET = governed_paper_entry_safety_rule_set()
GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest()
GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET = governed_paper_entry_safety_rule_set(protective=True)
GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest(protective=True)
GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET = governed_paper_entry_safety_rule_set(protective=True, portfolio=True)
GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest(
    protective=True, portfolio=True
)
GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET = governed_paper_entry_safety_rule_set(
    protective=True, portfolio=True, market_data=True
)
GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest(
    protective=True, portfolio=True, market_data=True
)
GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET = governed_paper_entry_safety_rule_set(
    protective=True, portfolio=True, market_data=True, kill_switch=True
)
GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST = governed_paper_entry_safety_rule_set_digest(
    protective=True, portfolio=True, market_data=True, kill_switch=True
)


# --- one decision ------------------------------------------------------------------------------------------------------


def _optional_text(value: object, name: str) -> None:
    if value is not None and (type(value) is not str or value == ""):
        raise _fail(f"observation_malformed:{name}")


def _canonical_observation(observation: object) -> GovernedPaperEntrySafetyObservation:
    if type(observation) is not GovernedPaperEntrySafetyObservation:
        raise _fail("observation_malformed")
    for name in ("decision_sequence", "decision_time_ns", "genesis_start_ns", "latency_ns"):
        if not historical_execution_wire_int_is_valid(getattr(observation, name), minimum=0):
            raise _fail(f"observation_malformed:{name}")
    if not edge_is_hex64(observation.decision_digest):
        raise _fail("observation_malformed:decision_digest")
    for name in ("instrument", "latency_tier_id"):
        value = getattr(observation, name)
        if type(value) is not str or value == "":
            raise _fail(f"observation_malformed:{name}")
    if type(observation.target_direction) is not str or observation.target_direction not in _ENTRY_DIRECTIONS:
        raise _fail("observation_malformed:target_direction")
    for name in ("family_b_applicable", "single_instrument_portfolio", "lifecycle_invalidated"):
        if type(getattr(observation, name)) is not bool:
            raise _fail(f"observation_malformed:{name}")
    event = observation.book_update_event_time_ns
    if event is not None and not historical_execution_wire_int_is_valid(event, minimum=0):
        raise _fail("observation_malformed:book_update_event_time_ns")
    for name in ("book_update_record_digest", "mark_record_digest", "lookback_mark_record_digest"):
        value = getattr(observation, name)
        if value is not None and not edge_is_hex64(value):
            raise _fail(f"observation_malformed:{name}")
    for name in ("mark_price", "lookback_mark_price"):
        value = getattr(observation, name)
        _optional_text(value, name)
        if value is not None and (not historical_execution_decimal_is_canonical(value) or Fraction(value) <= 0):
            raise _fail(f"observation_malformed:{name}")
    _canonical_protection_facts(observation)
    _canonical_portfolio_facts(observation)
    _canonical_market_data(observation)
    _canonical_kill_switch(observation)
    return observation


_PORTFOLIO_FACTS = (
    "portfolio_snapshot_digest",
    "position_quantity",
    "portfolio_mark_record_digest",
    "portfolio_mark_price",
    "portfolio_nav",
    "day_start_ns",
    "day_start_nav",
    "candidate_position_quantity",
    "candidate_nav",
)


def _canonical_portfolio_facts(observation: GovernedPaperEntrySafetyObservation) -> None:  # noqa: C901, PLR0912
    """The portfolio facts are exact types and one consistent snapshot, and absent without a governed portfolio."""

    if type(observation.portfolio_present) is not bool:
        raise _fail("observation_malformed:portfolio_present")
    if type(observation.order_in_flight) is not bool:
        raise _fail("observation_malformed:order_in_flight")
    reason = observation.day_start_reason
    if type(reason) is not str or (reason != "" and reason not in _DAY_START_REASONS):
        raise _fail("observation_malformed:day_start_reason")
    nav_reason = observation.portfolio_nav_reason
    if type(nav_reason) is not str or (nav_reason != "" and nav_reason not in _NAV_REASONS):
        raise _fail("observation_malformed:portfolio_nav_reason")
    candidate_reason = observation.candidate_nav_reason
    if type(candidate_reason) is not str or (candidate_reason != "" and candidate_reason not in _CANDIDATE_REASONS):
        raise _fail("observation_malformed:candidate_nav_reason")
    snapshot = observation.portfolio_snapshot_digest
    if not observation.portfolio_present or snapshot is None:
        if any(getattr(observation, name) is not None for name in _PORTFOLIO_FACTS) or observation.order_in_flight:
            raise _fail("observation_malformed:portfolio_facts_without_a_snapshot")
        if reason or nav_reason or candidate_reason:
            raise _fail("observation_malformed:portfolio_facts_without_a_snapshot")
        if observation.portfolio_present and not observation.protection_present:
            raise _fail("observation_malformed:portfolio_without_a_protective_context")
        return
    if not observation.protection_present:
        raise _fail("observation_malformed:portfolio_without_a_protective_context")
    if not edge_is_hex64(snapshot):
        raise _fail("observation_malformed:portfolio_snapshot_digest")
    for name in (
        "position_quantity",
        "portfolio_mark_price",
        "portfolio_nav",
        "day_start_nav",
        "candidate_position_quantity",
        "candidate_nav",
    ):
        value = getattr(observation, name)
        if value is not None and not historical_execution_decimal_is_canonical(value):
            raise _fail(f"observation_malformed:{name}")
    if observation.position_quantity is None:
        raise _fail("observation_malformed:position_quantity")
    if observation.candidate_position_quantity is None:
        raise _fail("observation_malformed:candidate_position_quantity")
    mark_digest, mark_price = observation.portfolio_mark_record_digest, observation.portfolio_mark_price
    if (mark_digest is None) is not (mark_price is None) or (
        mark_digest is not None and not edge_is_hex64(mark_digest)
    ):
        raise _fail("observation_malformed:portfolio_mark")
    if mark_price is not None and Fraction(mark_price) <= 0:
        raise _fail("observation_malformed:portfolio_mark_price")
    if (observation.portfolio_nav is None) is not (nav_reason != ""):
        raise _fail("observation_malformed:portfolio_nav_reason")
    quantity = Fraction(observation.position_quantity)
    # a flat portfolio is valued without a mark; an open position exactly when the fresh mark exists
    if (nav_reason == "no_fresh_visible_mark") is not (quantity != 0 and mark_price is None):
        raise _fail("observation_malformed:portfolio_nav_inconsistent")
    _canonical_candidate_facts(observation, quantity, candidate_reason)
    day = observation.day_start_ns
    if (
        not historical_execution_wire_int_is_valid(day, minimum=0)
        or day % _UTC_DAY_NS != 0  # type: ignore[operator]
        or not day <= observation.decision_time_ns < day + _UTC_DAY_NS  # type: ignore[operator]
    ):
        raise _fail("observation_malformed:day_start_ns")
    if (observation.day_start_nav is None) is not (reason != ""):
        raise _fail("observation_malformed:day_start_reason")


def _canonical_candidate_facts(
    observation: GovernedPaperEntrySafetyObservation, quantity: Fraction, reason: str
) -> None:
    """The candidate never reverses the position, and its projected NAV exists exactly for an entry it can value."""

    candidate = Fraction(observation.candidate_position_quantity)  # type: ignore[arg-type]
    if quantity != 0 and candidate != 0 and (candidate > 0) is not (quantity > 0):
        raise _fail("observation_malformed:candidate_reverses_the_position")
    if abs(candidate) <= abs(quantity):  # no entry: nothing is projected
        if observation.candidate_nav is not None or reason:
            raise _fail("observation_malformed:candidate_nav_without_an_entry")
        return
    if (observation.candidate_nav is None) is not (reason != ""):
        raise _fail("observation_malformed:candidate_nav_reason")
    if observation.portfolio_mark_price is None:
        consistent = reason == "no_fresh_visible_mark"
    elif observation.portfolio_nav is None:
        consistent = reason == "nav_unavailable"
    else:
        consistent = reason in ("", "candidate_nav_unrepresentable")
    if not consistent:
        raise _fail("observation_malformed:candidate_nav_inconsistent")


def _canonical_protection_facts(observation: GovernedPaperEntrySafetyObservation) -> None:
    """The protective facts are exact types, consistent, and absent (their defaults) without a protective context."""

    for name in ("protection_present", "protective_window_covers", "atr_available"):
        if type(getattr(observation, name)) is not bool:
            raise _fail(f"observation_malformed:{name}")
    for name in ("protective_authority_digest", "atr_window_digest"):
        value = getattr(observation, name)
        if value is not None and not edge_is_hex64(value):
            raise _fail(f"observation_malformed:{name}")
    value = observation.atr_value
    if value is not None and (not historical_execution_decimal_is_canonical(value) or Fraction(value) <= 0):
        raise _fail("observation_malformed:atr_value")
    if type(observation.atr_reason) is not str:
        raise _fail("observation_malformed:atr_reason")
    method = observation.stop_tightening_method_id
    if method is not None and (type(method) is not str or method == ""):
        raise _fail("observation_malformed:stop_tightening_method_id")
    available = observation.atr_value is not None and observation.atr_window_digest is not None
    if observation.atr_available is not available or (observation.atr_reason == "") is not (
        available or not observation.protection_present
    ):
        raise _fail("observation_malformed:atr_reading_inconsistent")
    if observation.protective_window_covers and observation.protective_authority_digest is None:
        raise _fail("observation_malformed:protective_window_without_authority")
    if not observation.protection_present and (
        observation.protective_window_covers
        or observation.protective_authority_digest is not None
        or observation.atr_available
        or method is not None
    ):
        raise _fail("observation_malformed:protective_facts_without_a_protective_context")
    if observation.protection_present and method is None:
        raise _fail("observation_malformed:stop_tightening_method_id")


def _canonical_reason(value: object, vocabulary: tuple[str, ...], name: str) -> str:
    if type(value) is not str or (value != "" and value not in vocabulary):
        raise _fail(f"observation_malformed:{name}")
    return value


def _canonical_latest(
    reason: str, digest: object, event: object, price: object, *, instant: int, positive: bool, name: str
) -> None:
    """A latest visible record: absent exactly with a reason, else a digest, an event at or before ``t`` and a price."""

    if reason:
        if digest is not None or event is not None or price is not None:
            raise _fail(f"observation_malformed:{name}_without_a_visible_record")
        return
    if not edge_is_hex64(digest) or not historical_execution_wire_int_is_valid(event, minimum=0) or event > instant:  # type: ignore[operator]
        raise _fail(f"observation_malformed:{name}_record")
    if not historical_execution_decimal_is_canonical(price) or (positive and Fraction(price) <= 0):  # type: ignore[arg-type]
        raise _fail(f"observation_malformed:{name}_price")


def _canonical_feed(gap: object, reason: str, evidence: object, *, name: str) -> None:
    """One NT-D01 feed: an observed gap binds the digest of what it read; an unobserved feed carries its reason."""

    if gap is not None and not historical_execution_wire_int_is_valid(gap, minimum=0):
        raise _fail(f"observation_malformed:{name}_gap_ns")
    if type(evidence) is not tuple or any(not edge_is_hex64(item) for item in evidence):
        raise _fail(f"observation_malformed:{name}_gap_evidence")
    if (gap is None) is not (evidence == ()) or (gap is None and not reason):
        raise _fail(f"observation_malformed:{name}_gap_inconsistent")


def _canonical_market_data(observation: GovernedPaperEntrySafetyObservation) -> None:  # noqa: C901
    """The rule set v4 facts are exact types and one consistent reading, and exist only with a governed portfolio."""

    data = observation.market_data
    if data is None:
        return
    if type(data) is not GovernedPaperEntrySafetyMarketData:
        raise _fail("observation_malformed:market_data")
    if not observation.portfolio_present:
        raise _fail("observation_malformed:market_data_without_a_governed_portfolio")
    instant = observation.decision_time_ns
    trade_reason = _canonical_reason(data.trade_reason, _TRADE_REASONS, "trade_reason")
    _canonical_latest(
        trade_reason,
        data.trade_record_digest,
        data.trade_event_time_ns,
        data.trade_price,
        instant=instant,
        positive=True,
        name="trade",
    )
    trade_gap_reason = _canonical_reason(data.trade_gap_reason, _TRADE_GAP_REASONS, "trade_gap_reason")
    _canonical_feed(data.trade_gap_ns, trade_gap_reason, data.trade_gap_evidence, name="trade")
    if trade_reason and (data.trade_gap_ns is not None or trade_gap_reason != trade_reason):
        raise _fail("observation_malformed:trade_gap_without_a_visible_trade")
    if not trade_reason and (data.trade_gap_ns is None or trade_gap_reason in _TRADE_REASONS):
        raise _fail("observation_malformed:trade_gap_of_a_visible_trade")
    kline_gap_reason = _canonical_reason(data.kline_gap_reason, _KLINE_GAP_REASONS, "kline_gap_reason")
    _canonical_feed(data.kline_gap_ns, kline_gap_reason, data.kline_gap_evidence, name="kline")
    # an observed kline feed can only lack the proof that it reaches back to the span start
    if data.kline_gap_ns is not None and kline_gap_reason not in (
        "",
        "exchange_kline_feed_not_observed_back_to_the_span_start",
    ):
        raise _fail("observation_malformed:kline_gap_inconsistent")
    index_reason = _canonical_reason(data.index_reason, _INDEX_REASONS, "index_reason")
    _canonical_latest(
        index_reason,
        data.index_record_digest,
        data.index_event_time_ns,
        data.index_price,
        instant=instant,
        positive=True,
        name="index",
    )
    if data.index_slot_ns is not None and (data.index_slot_ns != _INDEX_SLOT_NS or index_reason):
        raise _fail("observation_malformed:index_slot_ns")
    volume_reason = _canonical_reason(data.volume_reason, _VOLUME_REASONS, "volume_reason")
    volumes = (data.volume_target, data.volume_baseline)
    evidence = data.volume_evidence
    if type(evidence) is not tuple or any(not edge_is_hex64(item) for item in evidence):
        raise _fail("observation_malformed:volume_evidence")
    if volume_reason:
        if volumes != (None, None) or evidence != ():
            raise _fail("observation_malformed:volume_without_its_coverage")
        return
    if len(evidence) != 3 or any(
        not historical_execution_decimal_is_canonical(value) or Fraction(value) < 0  # type: ignore[arg-type]
        for value in volumes
    ):
        raise _fail("observation_malformed:volume")


def _canonical_trigger_ids(value: object, name: str) -> tuple[str, ...]:
    """Distinct §1.19 trigger ids in PRDV4 order, exact str."""

    if type(value) is not tuple or any(type(item) is not str for item in value):
        raise _fail(f"observation_malformed:{name}")
    if list(value) != [item for item in GOVERNED_PAPER_KILL_SWITCH_TRIGGER_IDS if item in value] or len(
        set(value)
    ) != len(value):
        raise _fail(f"observation_malformed:{name}")
    return value  # type: ignore[return-value]


def _canonical_kill_switch(observation: GovernedPaperEntrySafetyObservation) -> None:
    """The rule set v5 facts are exact types and one consistent ladder reading, and exist only on top of rule set v4."""

    facts = observation.kill_switch
    if facts is None:
        return
    if type(facts) is not GovernedPaperEntrySafetyKillSwitch:
        raise _fail("observation_malformed:kill_switch")
    if observation.market_data is None:
        raise _fail("observation_malformed:kill_switch_without_the_market_data_facts")
    level = facts.level
    if type(level) is not int or not 0 <= level <= 3:
        raise _fail("observation_malformed:kill_switch_level")
    proving = _canonical_trigger_ids(facts.proving_trigger_ids, "kill_switch_proving_trigger_ids")
    unproven = _canonical_trigger_ids(facts.unproven_trigger_ids, "kill_switch_unproven_trigger_ids")
    unmeasured = _canonical_trigger_ids(facts.unmeasured_trigger_ids, "kill_switch_unmeasured_trigger_ids")
    if not edge_is_hex64(facts.ladder_digest):
        raise _fail("observation_malformed:kill_switch_ladder_digest")
    transition = facts.transition_digest
    if (transition is None) is not (level == 0) or (transition is not None and not edge_is_hex64(transition)):
        raise _fail("observation_malformed:kill_switch_transition")
    # a positive bound always rests on proven triggers, and a zero bound on none
    if (level == 0) is not (not proving):
        raise _fail("observation_malformed:kill_switch_proving_trigger_ids")
    if not set(unmeasured) <= set(unproven):
        raise _fail("observation_malformed:kill_switch_unmeasured_trigger_ids")


def evaluate_governed_paper_entry_safety(
    observation: GovernedPaperEntrySafetyObservation,
) -> GovernedPaperEntrySafetyDecision:
    """Evaluate every check of one entry decision in order (pure); the first non-admitting check refuses the entry."""

    observation = _canonical_observation(observation)
    checks: list[GovernedPaperEntrySafetyCheck] = []
    first: GovernedPaperEntrySafetyCheck | None = None
    for item in _CHECKS:
        outcome = item.evaluate(observation)
        check = GovernedPaperEntrySafetyCheck(
            check_id=item.check_id,
            family=item.family,
            status=outcome.status,
            observed=outcome.observed,
            threshold=item.threshold,
            reason=_reason(f"{item.check_id}:{outcome.reason}"),
            evidence_record_digests=outcome.evidence,
        )
        checks.append(check)
        if first is None and outcome.status not in _ADMITTING:
            first = check
    return GovernedPaperEntrySafetyDecision(
        decision_sequence=observation.decision_sequence,
        decision_time_ns=observation.decision_time_ns,
        decision_digest=observation.decision_digest,
        instrument=observation.instrument,
        target_direction=observation.target_direction,
        checks=tuple(checks),
        entry_permitted=first is None,
        first_failure_check_id="" if first is None else first.check_id,
        first_failure_reason="" if first is None else first.reason,
    )


# --- the evidence of one decision run ----------------------------------------------------------------------------------


def _single_instrument_portfolio(authority: GovernedPaperGenesisAuthority) -> bool:
    """The paper portfolio is exactly the genesis sleeve (its universe is the one genesis instrument)."""

    genesis, envelope = authority.genesis, authority.portfolio_risk_envelope
    return len(envelope.sleeve_caps) == 1 and envelope.sleeve_caps[0].sleeve_id == genesis.sleeve_id


def _canonical_protection(protection: object, *, instrument: str) -> GovernedPaperEntrySafetyProtection | None:
    if protection is None:
        return None
    if type(protection) is not GovernedPaperEntrySafetyProtection:
        raise _fail("protection_malformed")
    policy, archive, window = (
        protection.position_management_policy,
        protection.ohlc_archive,
        protection.protective_window,
    )
    if (
        type(policy) is not HistoricalPositionManagementPolicy
        or not verify_historical_position_management_policy(policy).intact
        or type(archive) is not HistoricalOhlcBarArchive
        or not verify_historical_ohlc_bar_archive(archive).intact
    ):
        raise _fail("protection_not_authentic")
    if policy.instrument != instrument or archive.source.instrument != instrument:
        raise _fail("protection_not_of_the_genesis_instrument")
    if (
        policy.atr_interval_ns not in archive.source.bar_intervals_ns
        or archive.source.price_semantics is not policy.atr_bar_price_semantics
    ):
        raise _fail("protection_archive_not_of_the_policy")
    if window is not None and (
        type(window) is not HistoricalExecutionProtectiveWindow
        or not edge_is_hex64(window.authority_digest)
        or not historical_execution_wire_int_is_valid(window.window_start_ns, minimum=0)
        or not historical_execution_wire_int_is_valid(window.window_end_ns, minimum=0)
        or window.window_end_ns <= window.window_start_ns
    ):
        raise _fail("protective_window_malformed")
    return protection


def _protection_facts(
    protection: GovernedPaperEntrySafetyProtection | None, *, instant: int, max_execution_delay_ns: int
) -> dict[str, object]:
    """The protective facts of one entry at ``instant`` (rule set v2), derived exactly as the engine will apply them."""

    if protection is None:
        return {}
    policy, window = protection.position_management_policy, protection.protective_window
    horizon = instant + MAX_HOLD_NS + 2 * max_execution_delay_ns
    reading = historical_ohlc_wilder_atr(
        protection.ohlc_archive,
        interval_ns=policy.atr_interval_ns,
        at_ns=instant,
        max_bar_age_ns=policy.atr_max_bar_age_ns,
    )
    return {
        "protection_present": True,
        "protective_window_covers": window is not None
        and window.window_start_ns <= instant
        and horizon < window.window_end_ns,
        "protective_authority_digest": None if window is None else window.authority_digest,
        "atr_available": reading.available,
        "atr_value": reading.rendered_value,
        "atr_reason": reading.reason,
        "atr_window_digest": reading.window_digest,
        "stop_tightening_method_id": policy.stop_tightening_method_id,
    }


@dataclass(frozen=True)
class _Trade:
    trade_id: int
    event_ns: int
    visible_ns: int
    price: str
    quantity: Fraction
    run_first: int | None
    digest: str


@dataclass(frozen=True)
class _Index:
    event_ns: int
    sequence_id: int
    visible_ns: int
    price: str
    slot: int | None
    digest: str


@dataclass(frozen=True)
class _Bar:
    open_ns: int
    close_ns: int
    visible_ns: int
    digest: str


def _record_values(record: HistoricalPitRecord, names: tuple[frozenset[str], ...]) -> dict[str, str] | None:
    """The record's values when their name set is one of ``names``, else None (a malformed record)."""

    values = {value.name: value.value for value in record.values}
    return values if frozenset(values) in names else None


def _continuity_reason(trades: Sequence[_Trade]) -> str:
    """Whether the visible trades DECLARE the contiguous-id profile: every one names its run (none visible declares
    nothing either way, so the coverage itself is what is missing)."""

    declared = {item.run_first is not None for item in trades}
    if declared in (set(), {True}):
        return ""
    if declared == {True, False}:
        return "trade_continuity_declaration_inconsistent"
    return "trade_continuity_profile_not_declared"


def _whole_number(text: str) -> int | None:
    value = Fraction(text)
    return value.numerator if value.denominator == 1 and value >= 0 else None


def _authenticated_series(dataset: HistoricalPitDataset) -> tuple[EdgeSourceSeriesRecord, ...]:
    """The dataset's own EF-3 series records, reconstructed from its source-manifest binding and re-proven by the public
    EF-3 verifier with the digest recomputed. A series is selected and judged on them, never on a dataset label."""

    snapshot = edge_authority_binding_snapshot(dataset.source_manifest_binding)
    if not edge_source_packet_evidence_payload_is_well_formed(snapshot):
        raise _fail("market_data_archive_not_authentic")
    manifest = edge_source_packet_evidence_from_payload(snapshot)
    verification = verify_edge_source_packet_evidence(manifest)
    if (
        not verification.intact
        or verification.recomputed_digest != dataset.source_manifest_digest
        or manifest.status is not EdgeEvidenceStatus.READY
    ):
        raise _fail("market_data_archive_not_authentic")
    return manifest.series


def _registry_semantics_hold(record: EdgeSourceSeriesRecord, key: DataRequirementKey) -> bool:
    """Whether an authenticated EF-3 series record carries exactly the producer's registry 1.0 semantics of ``key``."""

    return all(
        type(getattr(record, name)) is type(value) and getattr(record, name) == value
        for name, value in _MARKET_SERIES_SEMANTICS[key]
    )


def _market_series(
    authenticated: Sequence[EdgeSourceSeriesRecord], key: DataRequirementKey, label: str, instrument: str
) -> tuple[str, str]:
    """``(reason, series id)``: among the ``authenticated`` EF-3 series, the one final, immutable series of ``key``
    covering the instrument, carrying the producer's registry 1.0 semantics, or why there is none."""

    candidates = [
        record
        for record in authenticated
        if record.data_requirement_key == key.value and instrument in record.instrument_coverage
    ]
    if not candidates:
        return f"{label}_series_not_in_the_selected_data_contract", ""
    if len(candidates) > 1:
        return f"{label}_series_ambiguous", ""
    record = candidates[0]
    if record.finalized_only is not True or record.revision_policy != _IMMUTABLE:
        return f"{label}_series_not_final_and_immutable", ""
    if not _registry_semantics_hold(record, key):
        return f"{label}_series_semantics_unsupported", ""
    return "", record.series_id


_TRADE_NAMES = (
    frozenset({TRADE_PRICE_VALUE_NAME, TRADE_QUANTITY_VALUE_NAME}),
    frozenset({TRADE_PRICE_VALUE_NAME, TRADE_QUANTITY_VALUE_NAME, TRADE_RUN_FIRST_ID_VALUE_NAME}),
)
_INDEX_NAMES = (
    frozenset({INDEX_PRICE_VALUE_NAME}),
    frozenset({INDEX_PRICE_VALUE_NAME, INDEX_UTC_SECOND_SLOT_VALUE_NAME}),
)


def _trade_of(record: HistoricalPitRecord, visible: int) -> _Trade | None:
    """One well-formed trade record (positive price and quantity; a run that starts at or before it), else None."""

    values = _record_values(record, _TRADE_NAMES)
    if values is None:
        return None
    price, quantity = Fraction(values[TRADE_PRICE_VALUE_NAME]), Fraction(values[TRADE_QUANTITY_VALUE_NAME])
    run = values.get(TRADE_RUN_FIRST_ID_VALUE_NAME)
    first = None if run is None else _whole_number(run)
    if price <= 0 or quantity <= 0 or (run is not None and (first is None or first > record.sequence_id)):
        return None
    return _Trade(
        record.sequence_id,
        record.event_time_ns,
        visible,
        values[TRADE_PRICE_VALUE_NAME],
        quantity,
        first,
        record.record_digest,
    )


def _index_of(record: HistoricalPitRecord, visible: int) -> _Index | None:
    """One well-formed index record (a declared second, when named, is its own UTC second), else None."""

    values = _record_values(record, _INDEX_NAMES)
    if values is None:
        return None
    text = values.get(INDEX_UTC_SECOND_SLOT_VALUE_NAME)
    slot = None if text is None else _whole_number(text)
    if text is not None and slot != record.event_time_ns // _INDEX_SLOT_NS:
        return None
    return _Index(
        record.event_time_ns,
        record.sequence_id,
        visible,
        values[INDEX_PRICE_VALUE_NAME],
        slot,
        record.record_digest,
    )


def _series_entries(
    dataset: HistoricalPitDataset, series: str, instrument: str, parse: Callable[[HistoricalPitRecord, int], object]
) -> tuple[int | None, list[object]]:
    """``(the first instant a malformed record is visible, the well-formed entries)`` of one series and instrument.

    A final-required series never shows a record before its finality; a malformed record only matters from the instant
    it is visible, so no reading at ``t`` depends on a record unknown at ``t``.
    """

    malformed: int | None = None
    entries: list[object] = []
    for record in dataset.records:
        if record.series_id != series or record.instrument != instrument or record.finalized_at_ns is None:
            continue
        visible = max(record.available_at_ns, record.finalized_at_ns)
        entry = parse(record, visible)
        if entry is None:
            malformed = visible if malformed is None else min(malformed, visible)
        else:
            entries.append(entry)
    return malformed, entries


def _kline_index(archive: HistoricalOhlcBarArchive | None, instrument: str) -> tuple[str, tuple[_Bar, ...]]:
    """``(reason, 1-minute bars by open time)``: the archive is a kline feed only by its DECLARED exchange origin."""

    if archive is None:
        return "exchange_kline_feed_not_in_the_selected_data_contract", ()
    source = archive.source
    if source.bar_origin is None:
        return "kline_origin_undeclared", ()
    if source.bar_origin is not HistoricalOhlcBarOrigin.EXCHANGE_KLINE:
        return "kline_bars_trade_derived_not_an_exchange_kline_feed", ()
    if source.price_semantics is not HistoricalOhlcPriceSemantics.LAST_TRADE:
        return "exchange_kline_bars_not_last_trade", ()
    if _KLINE_INTERVAL_NS not in source.bar_intervals_ns:
        return "exchange_kline_1m_interval_not_declared", ()
    if source.instrument != instrument:
        return "exchange_kline_feed_of_another_instrument", ()
    return "", tuple(
        _Bar(bar.open_time_ns, bar.close_time_ns, max(bar.available_at_ns, bar.finalized_at_ns), bar.bar_digest)
        for bar in archive.bars
        if bar.interval_ns == _KLINE_INTERVAL_NS
    )


def _span_digest(digests: Sequence[str]) -> str:
    return edge_sha256_text(edge_canonical_json(list(digests)))


def _publication_profile(indexes: Sequence[_Index]) -> tuple[int | None, int | None]:
    """When the index records first break ``index_one_per_utc_second.v1`` as its producer enforces it: ``(the first
    instant declared and undeclared records are both visible, the first instant two distinct publications of one
    declared UTC second are)``. A publication is a native event time and its value, so an identical replay is the same
    publication, known from its earliest visibility. Order-free, and nothing visible after ``t`` breaks it at ``t``."""

    declared = [item.visible_ns for item in indexes if item.slot is not None]
    undeclared = [item.visible_ns for item in indexes if item.slot is None]
    mixed = max(min(declared), min(undeclared)) if declared and undeclared else None
    seconds: dict[int, dict[tuple[int, Fraction], int]] = {}
    for item in indexes:
        if item.slot is not None:
            known = seconds.setdefault(item.slot, {})
            publication = (item.event_ns, Fraction(item.price))
            known[publication] = min(known.get(publication, item.visible_ns), item.visible_ns)
    conflicts = [sorted(known.values())[1] for known in seconds.values() if len(known) > 1]
    return mixed, min(conflicts, default=None)


def _contiguous(trades: Sequence[_Trade]) -> bool:
    """One contiguous run of the declared profile: one run, consecutive native ids, every one visible."""

    first = trades[0]
    return all(
        item.run_first is not None and item.run_first == first.run_first and item.trade_id == first.trade_id + offset
        for offset, item in enumerate(trades)
    )


def _trade_feed(
    trades: Sequence[_Trade], reason: str, continuity: str, instant: int, start: int
) -> tuple[int | None, str, tuple[str, ...]]:
    """NT-D01 trade reading over ``[start, t]``: the largest observed gap and why the span is not proven continuous."""

    if reason:
        return None, reason, ()
    events = [item.event_ns for item in trades]
    witness = bisect.bisect_right(events, start) - 1
    chosen = trades[max(witness, 0) :]
    gaps = [later.event_ns - earlier.event_ns for earlier, later in zip(chosen, chosen[1:], strict=False)]
    gap = max((*gaps, instant - chosen[-1].event_ns))
    if witness < 0:
        reason = "trade_stream_not_observed_back_to_the_span_start"
    elif continuity:
        reason = continuity
    elif not _contiguous(chosen):
        reason = "trade_stream_continuity_broken_in_the_span"
    return gap, reason, (_span_digest([item.digest for item in chosen]),)


def _kline_feed(bars: Sequence[_Bar], reason: str, instant: int, start: int) -> tuple[int | None, str, tuple[str, ...]]:
    """NT-D01 kline reading over ``[start, t]``: a missing 1-minute bar is a gap of the delivered kline feed."""

    if reason:
        return None, reason, ()
    visible = [bar for bar in bars if bar.visible_ns <= instant]
    if not visible:
        return None, "no_exchange_kline_bar_visible_at_the_decision_instant", ()
    witness = bisect.bisect_right([bar.close_ns for bar in visible], start) - 1
    chosen = visible[max(witness, 0) :]
    gaps = [later.open_ns - earlier.close_ns for earlier, later in zip(chosen, chosen[1:], strict=False)]
    gap = max((*gaps, instant - chosen[-1].close_ns))
    reason = "" if witness >= 0 else "exchange_kline_feed_not_observed_back_to_the_span_start"
    return gap, reason, (_span_digest([bar.digest for bar in chosen]),)


def _volume(
    trades: Sequence[_Trade], reason: str, continuity: str, start: int
) -> tuple[str | None, str | None, str, tuple[str, ...]]:
    """NT-D05 reading for the target window opening at ``start``: ``(target, baseline, reason, evidence)``."""

    if reason or continuity:
        return None, None, reason or continuity, ()
    first, end = start - _BASELINE_WINDOWS * _WINDOW_NS, start + _WINDOW_NS
    events = [item.event_ns for item in trades]
    before = bisect.bisect_left(events, first) - 1  # the latest visible trade strictly before the first window
    after = bisect.bisect_left(events, end)  # the earliest visible trade at or after the target window's end
    if before < 0:
        return None, None, "no_visible_trade_before_the_30d_baseline", ()
    if after >= len(trades):
        return None, None, "no_visible_trade_at_or_after_the_target_window_end", ()
    chosen = trades[before : after + 1]
    if not _contiguous(chosen):
        return None, None, "trade_continuity_broken_inside_the_30d_baseline_and_target_windows", ()
    baseline = sum((item.quantity for item in chosen if first <= item.event_ns < start), Fraction(0))
    target = sum((item.quantity for item in chosen if start <= item.event_ns < end), Fraction(0))
    rendered = historical_execution_render_amount(target), historical_execution_render_amount(baseline)
    if None in rendered:
        return None, None, "volume_unrepresentable", ()
    evidence = (chosen[0].digest, chosen[-1].digest, _span_digest([item.digest for item in chosen]))
    return rendered[0], rendered[1], "", evidence


class _MarketData:
    """The rule set v4 facts of one verified archive, instrument and kline feed; every query reads only what is visible
    at its instant and never the admission schedule."""

    def __init__(
        self, dataset: HistoricalPitDataset, *, instrument: str, kline: HistoricalOhlcBarArchive | None
    ) -> None:
        authenticated = _authenticated_series(dataset)
        self._trade_reason, series = _market_series(
            authenticated, DataRequirementKey.LAST_TRADE, "last_trade", instrument
        )
        self._trade_malformed, trades = _series_entries(dataset, series, instrument, _trade_of)
        # The archive's own integrity: native ids never run backwards in event time, so id order is event-time order.
        self._trades: tuple[_Trade, ...] = tuple(sorted(trades, key=lambda item: item.trade_id))  # type: ignore[attr-defined]
        self._index_reason, series = _market_series(
            authenticated, DataRequirementKey.INDEX_PRICE, "index_price", instrument
        )
        self._index_malformed, indexes = _series_entries(dataset, series, instrument, _index_of)
        self._indexes: tuple[_Index, ...] = tuple(sorted(indexes, key=lambda item: (item.event_ns, item.sequence_id)))  # type: ignore[attr-defined]
        self._index_mixed, self._index_conflict = _publication_profile(self._indexes)
        self._kline_reason, self._bars = _kline_index(kline, instrument)

    def facts_at(self, instant: int) -> GovernedPaperEntrySafetyMarketData:  # noqa: C901
        if not historical_execution_wire_int_is_valid(instant, minimum=1):
            raise _fail("market_data_instant_invalid")
        start = (instant // _WINDOW_NS - 1) * _WINDOW_NS  # the open of the latest completed UTC 5-minute window
        series_reason = self._trade_reason
        if not series_reason and self._trade_malformed is not None and self._trade_malformed <= instant:
            series_reason = "last_trade_record_malformed"
        trades = [] if series_reason else [item for item in self._trades if item.visible_ns <= instant]
        trade_reason = series_reason or ("" if trades else "no_trade_visible_at_the_decision_instant")
        continuity = _continuity_reason(trades)
        latest = None if trade_reason else trades[-1]
        trade_gap = _trade_feed(trades, trade_reason, continuity, instant, start)
        kline_gap = _kline_feed(self._bars, self._kline_reason, instant, start)
        index_reason, index = self._index_reason, None
        for since, broken in (
            (self._index_malformed, "index_price_record_malformed"),
            (self._index_mixed, "index_publication_declaration_inconsistent"),
            (self._index_conflict, "index_publication_slot_conflict"),
        ):
            if not index_reason and since is not None and since <= instant:
                index_reason = broken
        if not index_reason:
            index = next((item for item in reversed(self._indexes) if item.visible_ns <= instant), None)
            if index is None:
                index_reason = "no_index_price_visible_at_the_decision_instant"
            elif Fraction(index.price) <= 0:
                index_reason, index = "index_price_not_positive", None
        target, baseline, volume_reason, volume_evidence = _volume(trades, series_reason, continuity, start)
        return GovernedPaperEntrySafetyMarketData(
            trade_reason=trade_reason,
            trade_record_digest=None if latest is None else latest.digest,
            trade_event_time_ns=None if latest is None else latest.event_ns,
            trade_price=None if latest is None else latest.price,
            trade_gap_ns=trade_gap[0],
            trade_gap_reason=trade_gap[1],
            trade_gap_evidence=trade_gap[2],
            kline_gap_ns=kline_gap[0],
            kline_gap_reason=kline_gap[1],
            kline_gap_evidence=kline_gap[2],
            index_reason=index_reason,
            index_record_digest=None if index is None else index.digest,
            index_event_time_ns=None if index is None else index.event_ns,
            index_price=None if index is None else index.price,
            index_slot_ns=None if index is None or index.slot is None else _INDEX_SLOT_NS,
            volume_target=target,
            volume_baseline=baseline,
            volume_reason=volume_reason,
            volume_evidence=volume_evidence,
        )


def governed_paper_entry_safety_market_data(
    dataset: HistoricalPitDataset,
    *,
    instrument: str,
    decision_time_ns: int,
    kline_archive: HistoricalOhlcBarArchive | None = None,
) -> GovernedPaperEntrySafetyMarketData:
    """The rule set v4 market-data facts of ``instrument`` at ``decision_time_ns``, exactly as the gate derives them.

    The archive must be authentic, READY and advancing, and the kline archive (the kline feed candidate, None for none)
    authentic; both are verified here. Malformed or non-authentic input raises ``GovernedPaperEntrySafetyError``. Pure.
    """

    if (
        type(dataset) is not HistoricalPitDataset
        or not verify_historical_pit_dataset(dataset).intact
        or dataset.status is not EdgeEvidenceStatus.READY
        or dataset.advances is not True
    ):
        raise _fail("market_data_archive_not_authentic")
    if kline_archive is not None and (
        type(kline_archive) is not HistoricalOhlcBarArchive
        or not verify_historical_ohlc_bar_archive(kline_archive).intact
    ):
        raise _fail("market_data_kline_archive_not_authentic")
    if type(instrument) is not str or instrument == "":
        raise _fail("market_data_instrument_invalid")
    return _MarketData(dataset, instrument=instrument, kline=kline_archive).facts_at(decision_time_ns)


def governed_paper_entry_safety_portfolio_facts(
    snapshot: HistoricalExecutionDecisionPortfolioSnapshot | None,
) -> dict[str, object]:
    """The rule set v3 observation facts of one decision: its governed decision snapshot, or none when not computed."""

    if snapshot is None:
        return {"portfolio_present": True}
    if type(snapshot) is not HistoricalExecutionDecisionPortfolioSnapshot:
        raise _fail("portfolio_snapshot_malformed")
    return {
        "portfolio_present": True,
        "portfolio_snapshot_digest": snapshot.snapshot_digest,
        "position_quantity": snapshot.position_quantity,
        "order_in_flight": snapshot.order_in_flight,
        "portfolio_mark_record_digest": snapshot.mark_record_digest,
        "portfolio_mark_price": snapshot.mark_price,
        "portfolio_nav": snapshot.nav,
        "portfolio_nav_reason": snapshot.nav_reason,
        "day_start_ns": snapshot.day_start_ns,
        "day_start_nav": snapshot.day_start_nav,
        "day_start_reason": snapshot.day_start_reason,
        "candidate_position_quantity": snapshot.candidate_position_quantity,
        "candidate_nav": snapshot.candidate_nav,
        "candidate_nav_reason": snapshot.candidate_nav_reason,
    }


def governed_paper_entry_safety_kill_switch_facts(
    ladder: GovernedPaperKillSwitchLadder, time_ns: int
) -> GovernedPaperEntrySafetyKillSwitch:
    """The rule set v5 observation facts of one decision at ``time_ns``, read from its evaluation's ladder."""

    level, setting = governed_paper_kill_switch_level_at(ladder, time_ns)
    bound = level > 0 and setting is not None
    # below KS-3 the bound is the level of the triggers proven at the instant; an absorbed KS-3 rests on its escalation
    proving = setting.proven_trigger_ids if level == 3 else governed_paper_kill_switch_proven_at(ladder, time_ns)  # type: ignore[union-attr]
    return GovernedPaperEntrySafetyKillSwitch(
        level=level,
        proving_trigger_ids=proving if bound else (),
        unproven_trigger_ids=governed_paper_kill_switch_unproven_at(ladder, time_ns),
        unmeasured_trigger_ids=governed_paper_kill_switch_unmeasured(ladder),
        ladder_digest=ladder.ladder_digest,
        transition_digest=setting.transition_digest if bound else None,  # type: ignore[union-attr]
    )


@dataclass(frozen=True)
class _GovernedRun:
    """The one engine re-run of an evaluation (rule set v3 on): its snapshots by decision, its portfolio and outcome."""

    snapshots: dict[int, HistoricalExecutionDecisionPortfolioSnapshot]
    portfolio: HistoricalExecutionGovernedPaperDecisionPortfolio
    outcome: HistoricalExecutionGovernedPaperOutcome
    economics: HistoricalExecutionEconomicsResult


def _governed_run(
    portfolio: object,
    *,
    run: HistoricalDecisionRun,
    economics_policy_digest: str,
    protection: GovernedPaperEntrySafetyProtection | None,
) -> _GovernedRun | None:
    """The decision snapshots the one engine derives for this evaluation (rule set v3), keyed by decision sequence,
    with the decision portfolio and the governed outcome of that same re-run (the rule set v5 ladder reads both).

    Only an information-time schedule v4 has a decision portfolio: any other schedule is ``portfolio_not_derivable``.
    """

    if portfolio is None:
        return None
    if type(portfolio) is not GovernedPaperEntrySafetyPortfolio:
        raise _fail("portfolio_malformed")
    if protection is None:
        raise _fail("portfolio_without_a_protective_context")
    economics = portfolio.economics
    if type(economics) is not HistoricalExecutionEconomicsResult:
        raise _fail("portfolio_economics_malformed")
    if (
        economics.run_digest != run.run_digest
        or economics.economics_policy_digest != economics_policy_digest
        or economics.position_management_policy_digest != protection.position_management_policy.policy_digest
        or economics.ohlc_archive_digest != protection.ohlc_archive.archive_digest
    ):
        raise _fail("portfolio_economics_not_of_this_evaluation")
    try:  # derived, never accepted: the engine re-proves the economics and re-runs it under the schedule
        derived, outcome = simulate_historical_execution_governed_paper_decision_portfolio_and_outcome(
            economics, expected_result_digest=economics.result_digest, schedule=portfolio.schedule
        )
    except HistoricalExecutionEconomicsError as exc:
        raise _fail("portfolio_not_derivable") from exc
    return _GovernedRun({item.decision_sequence: item for item in derived.snapshots}, derived, outcome, economics)


def governed_paper_entry_safety_entry_sequences(run: HistoricalDecisionRun) -> tuple[int, ...]:
    """The decisions this gate evaluates, in time order: every one whose resulting direction is LONG or SHORT."""

    if type(run) is not HistoricalDecisionRun:
        raise _fail("decision_run_or_archive_malformed")
    return tuple(item.decision_sequence for item in run.decisions if item.resulting_direction in _ENTRY_DIRECTIONS)


def governed_paper_entry_safety_sequential_refusals(
    entries: tuple[int, ...], refusals_under: Callable[[tuple[int, ...]], tuple[int, ...]]
) -> tuple[int, ...]:
    """The refusals of rule set v3's sequential admission: the unique schedule that refuses exactly its own refusals.

    ``entries`` are the entry decisions in time order; ``refusals_under(refused)`` evaluates every entry on the decision
    portfolio of the schedule refusing ``refused``. Starting from every entry refused, each round replaces the refusals
    by the evaluation under them. A decision's portfolio depends only on the admissions before it, so round k is exact
    for the first k entries and the rounds settle on the fixed point within ``len(entries) + 1`` evaluations. A
    non-converging evaluation (impossible for a causal one) raises ``GovernedPaperEntrySafetyError``.
    """

    refused = entries
    for _ in range(len(entries) + 1):
        following = refusals_under(refused)
        if following == refused:
            return refused
        refused = following
    raise _fail("sequential_admission_not_converged")


def build_governed_paper_entry_safety_evidence(
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    invalidated_from_ns: int | None,
    protection: GovernedPaperEntrySafetyProtection | None = None,
    portfolio: GovernedPaperEntrySafetyPortfolio | None = None,
    market_data: bool = False,
    kill_switch: bool = False,
) -> GovernedPaperEntrySafetyEvidence:
    """Evaluate every entry decision of ``run`` over the archive ``dataset`` it was built from (see the module docstring).

    The run must be the genesis's own READY + PASS run over this archive and the archive the genesis's; the visible
    observations re-verify the archive and the economics policy. ``protection`` (rule set v2) is the verified protective
    context the day seal derives; without it the evaluation is rule set v1, unchanged. ``portfolio`` (rule set v3, only
    with ``protection``) is the replayed protective economics of this run and the schedule under evaluation, from which
    the one engine derives the decision portfolio. ``market_data=True`` (rule set v4, only with ``portfolio``) measures
    NT-D01, NT-D03, NT-D04 and NT-D05 on the archive's own market-data series and the protective context's OHLC
    archive as the kline feed candidate. ``kill_switch=True`` (rule set v5, only with ``market_data``) reads NT-R01 and
    NT-T02 on the proven lower-bound §1.19 ladder of the same governed re-run. A malformed or foreign input raises
    ``GovernedPaperEntrySafetyError``. Pure.
    """

    if type(authority) is not GovernedPaperGenesisAuthority:
        raise _fail("genesis_authority_malformed")
    if type(run) is not HistoricalDecisionRun or type(dataset) is not HistoricalPitDataset:
        raise _fail("decision_run_or_archive_malformed")
    if invalidated_from_ns is not None and not historical_execution_wire_int_is_valid(invalidated_from_ns, minimum=0):
        raise _fail("invalidated_from_ns_invalid")
    if type(market_data) is not bool:
        raise _fail("market_data_flag_malformed")
    if type(kill_switch) is not bool:
        raise _fail("kill_switch_flag_malformed")
    if kill_switch and not market_data:
        raise _fail("kill_switch_without_the_market_data_rule_set")
    genesis = authority.genesis
    protection = _canonical_protection(protection, instrument=genesis.instrument)
    if run.status is not EdgeEvidenceStatus.READY or run.gate_verdict is not EdgeGateVerdict.PASS:
        raise _fail("decision_run_not_ready")
    if (
        run.dataset_digest != dataset.dataset_digest
        or run.executable_binding_digest != genesis.executable_binding_digest
        or run.instrument != genesis.instrument
        or run.evaluation_start_ns != genesis.genesis_start_ns
        or dataset.source_manifest_digest != genesis.source_manifest_digest
        or dataset.data_requirement_registry_digest != genesis.data_requirement_registry_digest
    ):
        raise _fail("decision_run_or_archive_not_of_the_genesis")
    policy = authority.economics_policy
    governed = _governed_run(
        portfolio, run=run, economics_policy_digest=genesis.economics_policy_digest, protection=protection
    )
    snapshots = None if governed is None else governed.snapshots
    if market_data and snapshots is None:
        raise _fail("market_data_without_a_governed_portfolio")
    observations = historical_execution_visible_observations(dataset, policy=policy, instrument=genesis.instrument)
    # the archive is verified just above and the kline feed candidate in ``_canonical_protection``
    market = (
        _MarketData(dataset, instrument=genesis.instrument, kline=protection.ohlc_archive)  # type: ignore[union-attr]
        if market_data
        else None
    )
    registered = get_strategy_executable_profile(PASSIVE_FUNDING_CARRY_V1)
    family_b = (
        run.profile_id == registered.profile_id and run.profile_semantics_digest == registered.profile_semantics_digest
    )
    single = _single_instrument_portfolio(authority)
    ladder: GovernedPaperKillSwitchLadder | None = None
    if kill_switch:
        try:  # derived, never accepted: the ladder re-proves every input by its public digest and their bindings
            ladder = build_governed_paper_kill_switch_ladder(
                policy=policy,
                dataset=dataset,
                economics=governed.economics,  # type: ignore[union-attr]
                portfolio=governed.portfolio,  # type: ignore[union-attr]
                outcome=governed.outcome,  # type: ignore[union-attr]
                single_instrument_portfolio=single,
            )
        except GovernedPaperKillSwitchError as exc:
            raise _fail("kill_switch_ladder_not_derivable") from exc
    decisions: list[GovernedPaperEntrySafetyDecision] = []
    for decision in run.decisions:
        if decision.resulting_direction not in _ENTRY_DIRECTIONS:
            continue
        instant = decision.decision_time_ns
        book = observations.latest_book_update(instant)
        mark = observations.latest_mark(instant)
        lookback = observations.latest_mark(instant - _RETURN_LOOKBACK_NS) if instant >= _RETURN_LOOKBACK_NS else None
        observation = GovernedPaperEntrySafetyObservation(
            decision_sequence=decision.decision_sequence,
            decision_time_ns=instant,
            decision_digest=decision.decision_digest,
            instrument=genesis.instrument,
            target_direction=decision.resulting_direction,
            family_b_applicable=family_b,
            genesis_start_ns=genesis.genesis_start_ns,
            latency_tier_id=policy.latency_tier_id,
            latency_ns=policy.latency_ns,
            single_instrument_portfolio=single,
            lifecycle_invalidated=invalidated_from_ns is not None and invalidated_from_ns <= instant,
            book_update_record_digest=None if book is None else book[0],
            book_update_event_time_ns=None if book is None else book[1],
            mark_record_digest=None if mark is None else mark[0],
            mark_price=None if mark is None else mark[1],
            lookback_mark_record_digest=None if lookback is None else lookback[0],
            lookback_mark_price=None if lookback is None else lookback[1],
            **_protection_facts(  # type: ignore[arg-type]
                protection, instant=instant, max_execution_delay_ns=policy.max_execution_delay_ns
            ),
            **(  # type: ignore[arg-type]
                {}
                if snapshots is None
                else governed_paper_entry_safety_portfolio_facts(snapshots.get(decision.decision_sequence))
            ),
            market_data=None if market is None else market.facts_at(instant),
            kill_switch=None if ladder is None else governed_paper_entry_safety_kill_switch_facts(ladder, instant),
        )
        decisions.append(evaluate_governed_paper_entry_safety(observation))
    protective, measured = protection is not None, snapshots is not None
    seed = GovernedPaperEntrySafetyEvidence(
        schema_version=_SCHEMA_VERSION,
        rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID
        if kill_switch
        else GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_ID
        if market_data
        else GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID
        if measured
        else GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID
        if protective
        else GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
        rule_set_digest=governed_paper_entry_safety_rule_set_digest(
            protective=protective, portfolio=measured, market_data=market_data, kill_switch=kill_switch
        ),
        genesis_id=genesis.genesis_id,
        genesis_digest=genesis.genesis_digest,
        run_digest=run.run_digest,
        dataset_digest=dataset.dataset_digest,
        economics_policy_digest=genesis.economics_policy_digest,
        instrument=genesis.instrument,
        profile_id=run.profile_id,
        family_b_applicable=family_b,
        invalidated_from_ns=invalidated_from_ns,
        decisions=tuple(decisions),
        refused_decision_sequences=tuple(
            sorted(item.decision_sequence for item in decisions if not item.entry_permitted)
        ),
        evidence_digest="",
        kill_switch_ladder=ladder,
    )
    return replace(seed, evidence_digest=edge_payload_digest(_evidence_payload(seed), _DIGEST_FIELD))


def governed_paper_entry_safety_evidence_to_dict(evidence: GovernedPaperEntrySafetyEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _evidence_payload(evidence)


def governed_paper_entry_safety_evidence_digest(evidence: GovernedPaperEntrySafetyEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_evidence_payload(evidence), _DIGEST_FIELD)
