"""Governed paper regime state tests (S1_FAMILY_B_REGIME_TREND_ACTIVATION_GATE_CLOSURE_V1).

SYNTHETIC TEST VALUES ONLY. Every bar, book, price path, instant, latency, policy and approval here is a synthetic fixture
that exercises structure. None is a calibrated threshold, a venue fact, a qualified source, a real market observation or
a real human decision. Methodology S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1 r2 implements CL1-1..CL1-13 and
CL2-1..CL2-7 and excludes CL1-14, CL2-12 and CL2-13; its design approval is not production permission.

APPROVAL TABLE SUBSTITUTION (SYNTHETIC, TEST-ONLY). The PRODUCTION regime approval table admits no approval, so every
production regime reading is BLOCKED. The tests that exercise the methods install the TEST-ONLY table, which admits only
TEST_ONLY_SYNTHETIC approvals and marks every evidence derived under it. No test builds or grants a production
HUMAN_GOVERNANCE regime approval, and the PRODUCTION entry gate stays in force throughout (no rule table is replaced).

It proves:

* A. the policy fixes every r2 constant (a strict typed identity: an int never passes for a bool); the approval is
  exactly the human construction scope; the production table admits no approval and the test-only table only synthetic
  ones;
* B. D-PC2 and D-PC1:
  - exactly ±15% is no witness and one scale-18 unit beyond is; a 12-bar span counts and a 13-bar one never does;
  - the 289-close window edges hold;
  - one missing close of 289 leaves UNKNOWN, a visible witness proves CRISIS on partial data, and a close published
    after kappa(m) is unknown at m;
* C. sigma_r buckets at their exact boundaries (an equality goes to the higher bucket); TS against an independent EMA
  oracle, strict at one scale-18 unit, UNAVAILABLE on ATR24 = 0 or an hourly gap, and blind to a supplied hourly bar;
  the A1 possibility sets against an exhaustive completion oracle;
* D. the books:
  - the band depth and the relative spread are exact; a crossed book or an uncovered band gives no sample;
  - a stale or late tip is never read, and a malformed tip blocks every later sample;
  - the A/B oracle: a tip published after s never changes the sample at s;
  - the liquidity and spread-CV thresholds hold at their exact boundaries;
* E. A8 equals an unbounded oracle over every small history; K - 1 vs K; the 288 memory; the 4-in-288 overlay held 72;
* F. every rule set v6 reading (FB-REGIME 649, FB-REGIME-COOLDOWN 96 / 385, NT-M03, FB-TREND, FB-ACTIVATION,
  FB-REGIME-CELL, SYSTEM-STATE); UNKNOWN never PASSes and four checks never PASS;
* G. the derivation over a synthetic world:
  - every input is re-proven, never trusted for its digest;
  - the frozen knowledge instants hold: the kappa boundary, no relabelling (a bar arriving after the horizon included),
    the 10 s state record, horizon-independent prefixes and the late-book A/B oracle;
  - the disclosed cost of immutability: one late bar blocks FB-REGIME for exactly 649 evaluations (54 h);
  - the production table refuses every approval;
* H. rule set v6 in the gate: v1-v5 identities unchanged, the reading mapping, the accepted outcomes without regime
  facts, no admission change, no wallet, margin-utilization or DTL reading, and malformed facts refused;
* I. world G's regime lineage (seal v7, evidence v7) under the test-only table:
  - it changes only its version, its rule set and the bound regime evidence, and an audit replay with the original
    cutoffs reproduces every sealed entry;
  - X1 for the regime: a rewritten prefix or bar is refused, the evidence refuses a rewritten or backfilled archive, and
    a bar published after a seal arrives the next day with X1 intact;
  - forged facts, switched lineages and a foreign or late context are refused;
  - under the production table every reading is BLOCKED and a test-only seal never verifies;
* J. legacy byte identity: world G's kill-switch lineage (seal v6, evidence v6) equals its accepted-main pins.
"""

from __future__ import annotations

import functools
import inspect
import itertools
import math
import statistics
from collections import OrderedDict
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import fields, replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_regime_state as regime
from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyRegime,
    GovernedPaperEntrySafetyRegimeContext,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_evidence_digest,
    governed_paper_entry_safety_rule_set,
    governed_paper_entry_safety_rule_set_digest,
)
from crypto_core.validation.governed_paper_execution_authority import build_governed_paper_cycle_authority
from crypto_core.validation.governed_paper_kill_switch import GovernedPaperKillSwitchMeasurement
from crypto_core.validation.governed_paper_regime_state import (
    GOVERNED_PAPER_REGIME_APPROVED_ITEMS,
    GOVERNED_PAPER_REGIME_CHECK_IDS,
    GOVERNED_PAPER_REGIME_CONTRACT_ID,
    GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS,
    GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS,
    GOVERNED_PAPER_REGIME_PRODUCTION_APPROVAL_TABLE,
    GovernedPaperPriceCrisis,
    GovernedPaperRegimeApproval,
    GovernedPaperRegimeApprovalKind,
    GovernedPaperRegimeApprovalTable,
    GovernedPaperRegimeCheckReading,
    GovernedPaperRegimeError,
    GovernedPaperRegimeEvaluation,
    GovernedPaperRegimeEvidence,
    GovernedPaperRegimePolicy,
    GovernedPaperRegimeReading,
    GovernedPaperRegimeStatus,
    build_governed_paper_regime_approval,
    build_governed_paper_regime_policy,
    decision_evaluation_index,
    derive_governed_paper_regime_evidence,
    governed_paper_regime_approval_digest,
    governed_paper_regime_evidence_digest,
    governed_paper_regime_evidence_to_dict,
    governed_paper_regime_policy_digest,
    governed_paper_regime_prefix_digest,
    governed_paper_regime_state_at,
    verify_governed_paper_regime_approval,
    verify_governed_paper_regime_policy,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    HistoricalOhlcSourceDeclaration,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
    historical_ohlc_source_declaration_digest,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_authenticated_pit_ingress as ingt
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_lineage as lineage
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_authenticated_pit_ingress as ingt
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage

SECOND = 1_000_000_000
HOUR = 3_600 * SECOND
DAY = 86_400 * SECOND
BAR = 300 * SECOND  # the 5-minute MARK bar and the evaluation grid
KAPPA = 300 * SECOND  # kappa(m) = g_m + 300 s
UNIT = Fraction(1, 10**18)  # one scale-18 unit
INS = gpe.INS
d = gpe.d
P, F, B = GovernedPaperRegimeStatus.PASS, GovernedPaperRegimeStatus.FAIL, GovernedPaperRegimeStatus.BLOCKED
S = GovernedPaperEntrySafetyStatus
BLOCKED = S.BLOCKED_ON_MISSING_INPUT
HUMAN = GovernedPaperRegimeApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = GovernedPaperRegimeApprovalKind.TEST_ONLY_SYNTHETIC
NON = GovernedPaperPriceCrisis.PROVEN_NON_CRISIS.value
CRISIS = GovernedPaperPriceCrisis.PROVEN_CRISIS.value
UNKNOWN = GovernedPaperPriceCrisis.UNKNOWN.value
PRODUCTION_TABLE = GOVERNED_PAPER_REGIME_PRODUCTION_APPROVAL_TABLE
TEST_ONLY_TABLE = GovernedPaperRegimeApprovalTable("test_only", SYNTHETIC, ())
TABLES = {"test_only": TEST_ONLY_TABLE, "production": PRODUCTION_TABLE}
PRODUCTION_CHECKS = entry_safety._CHECKS  # noqa: SLF001 - captured at import, before any fixture could patch it
NOTHING: frozenset[int] = frozenset()
V6, V7 = "governed-paper-day-seal.v6", "governed-paper-day-seal.v7"
V7_FIELDS = (
    "regime_policy_digest",
    "regime_approval_digest",
    "regime_archive_digest",
    "regime_evidence_digest",
    "regime_prefix_digest_open",
    "regime_prefix_digest_close",
)

# The accepted-main identities of world G's kill-switch lineage (seal v6, evidence v6), pinned on main 0ca6e5cb before
# this contract: without a regime context every kill-switch seal and evidence stays byte-identical.
ACCEPTED_MAIN_RULE_SET_V5_DIGEST = "568862158ce8da4c40ba68089e8ad469dbae1956090837f6bf7292839a4a23ee"
ACCEPTED_MAIN_V6_SEALS = (
    "ec785d0c7c23518d693b6c50d25c1cb9e87d2a99ec360d150a37ac1a337afb4c",
    "b58fcd036994da62380f354d3171aba56d16b96f1f5888eda0b612c79e0d1392",
    "4a411083b705a8b97ae9b2746b92b2c88b1d6bc1f36580efcbb19b5f4b6549ea",
    "5b4d2fd4a4dc4ff971f7453758e055ef0ccc537281f835c51d51a45ca268b164",
)
ACCEPTED_MAIN_V6_ENTRY_EVIDENCE = (
    "6f34f08c5436277c9aa1c563cefa9af9bf8be42b886da3206276a8c540e1a243",
    "33e22d6ef578d7a2ecda936c5eafa1ae898b8300b4fe43ae2f460957e9585c3a",
    "ce375ce08a95178c537fb9c1bebcd2852d695c50a4196240f781aa9499b1f080",
    "814a6d15339b70621cf172349ec6b94bafe07d94cd5dc6a1e10c0840e11a10f2",
)
ACCEPTED_MAIN_V6_LADDERS = (
    "3048c7ce9576efe02d29435634afca09fd9f72167cd4274a9e91c30154b1ce79",
    "f2742b686fd08dba47991ec90052c1e821e5c590901a09e3cdf2e7fef3596b19",
    "b5eb66cf8ae79a304fc40962d2218e26869a5f54a8a6fb7a76277b43264c3575",
    "99da9572060250b62a3ea3e634bd2a6d801e12808807a096c80fbf908a0e29be",
)
ACCEPTED_MAIN_V6_LADDER_PREFIX = "01090b096489203d54727b9803dd842d1aa5f0f3fd96f156286655d624a4f0cd"
ACCEPTED_MAIN_V6_EVIDENCE = "16d592f0f4ce84379370d3497059dc47d45957cc94402ec6575165b359584c32"


@pytest.fixture(autouse=True, scope="module")
def _production_tables_with_exact_memos():
    """The exact upstream memos and identity memos of pure re-proofs; the PRODUCTION rule and approval tables stay."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        archives = gpe.SameObjects(regime.verify_historical_ohlc_bar_archive)
        patch.setattr(regime, "verify_historical_ohlc_bar_archive", archives)
        patch.setattr(gpe.execution, "verify_historical_ohlc_bar_archive", archives)
        patch.setattr(
            regime, "verify_historical_pit_dataset", gpe._EXACT[(gpe.execution, "verify_historical_pit_dataset")]
        )  # noqa: SLF001
        assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
        assert regime._APPROVAL_TABLE is PRODUCTION_TABLE  # noqa: SLF001
        yield


@contextmanager
def approval_table(table: GovernedPaperRegimeApprovalTable) -> Iterator[None]:
    """SYNTHETIC, TEST-ONLY: install ``table`` as the active regime approval table for the block."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(regime, "_APPROVAL_TABLE", table)
        yield


@pytest.fixture
def test_only_table() -> Iterator[None]:
    with approval_table(TEST_ONLY_TABLE):
        yield


def code(text: str) -> str:
    return f"governed_paper_regime_state:{text}"


# --- the policy, the approval and the MARK bars -------------------------------------------------------------------------


def mark_source(**changes: object) -> HistoricalOhlcSourceDeclaration:
    base = HistoricalOhlcSourceDeclaration(
        source_id="synthetic-regime-mark",
        source_reference="archive:synthetic-regime-mark",
        rights_status=SourcePacketRightsStatus.OWN_RESEARCH,
        rights_reference="license-1",
        instrument=INS,
        price_semantics=HistoricalOhlcPriceSemantics.MARK_PRICE,
        bar_intervals_ns=(BAR,),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


SOURCE_DIGEST = historical_ohlc_source_declaration_digest(mark_source())


@functools.cache
def regime_policy(policy_id: str = "synthetic-regime-policy-1", source_digest: str = SOURCE_DIGEST):  # noqa: ANN201
    return build_governed_paper_regime_policy(policy_id=policy_id, instrument=INS, bar_source_digest=source_digest)


@functools.cache
def regime_approval(kind: GovernedPaperRegimeApprovalKind = SYNTHETIC, policy_id: str = "synthetic-regime-policy-1"):  # noqa: ANN201
    return build_governed_paper_regime_approval(
        approval_id=f"synthetic-regime-approval-{kind.value.lower()}",
        approval_kind=kind,
        policy_digest=regime_policy(policy_id).policy_digest,
        approver_reference="synthetic-approver-1",
    )


def approval_of(policy: GovernedPaperRegimePolicy, kind: GovernedPaperRegimeApprovalKind = SYNTHETIC):  # noqa: ANN201
    return build_governed_paper_regime_approval(
        approval_id=f"synthetic-regime-approval-{policy.policy_id}",
        approval_kind=kind,
        policy_digest=policy.policy_digest,
        approver_reference="synthetic-approver-1",
    )


def resealed_policy(policy: GovernedPaperRegimePolicy, **changes: object) -> GovernedPaperRegimePolicy:
    changed = replace(policy, **changes)  # type: ignore[arg-type]
    return replace(changed, policy_digest=governed_paper_regime_policy_digest(changed))


def resealed_approval(approval: GovernedPaperRegimeApproval, **changes: object) -> GovernedPaperRegimeApproval:
    changed = replace(approval, **changes)  # type: ignore[arg-type]
    return replace(changed, approval_digest=governed_paper_regime_approval_digest(changed))


@functools.cache
def mark_bar(  # noqa: ANN201
    k: int,
    previous: Fraction,
    close: Fraction,
    visible: int,
    high: Fraction | None = None,
    low: Fraction | None = None,
    interval: int = BAR,
):
    """SYNTHETIC MARK bar closing at ``k`` intervals, opening at the previous close."""

    return build_historical_ohlc_bar(
        interval_ns=interval,
        open_time_ns=(k - 1) * interval,
        open_price=d(previous),
        high_price=d(max(previous, close) if high is None else high),
        low_price=d(min(previous, close) if low is None else low),
        close_price=d(close),
        available_at_ns=visible,
        finalized_at_ns=visible,
    )


def published(k: int) -> int:
    """The default visibility of 5-minute bar ``k``: one second after its close."""

    return k * BAR + SECOND


def mark_archive(  # noqa: PLR0913
    price,  # noqa: ANN001
    first: int,
    last: int,
    *,
    missing: frozenset[int] = NOTHING,
    visible=published,  # noqa: ANN001
    archive_id: str = "synthetic-regime-mark",
    source: HistoricalOhlcSourceDeclaration | None = None,
    extra: tuple = (),
) -> HistoricalOhlcBarArchive:
    """The 5-minute bars ``first..last`` of the path ``price`` (bar ``k`` closes at ``price(k)``), minus ``missing``."""

    bars = tuple(mark_bar(k, price(k - 1), price(k), visible(k)) for k in range(first, last + 1) if k not in missing)
    return build_historical_ohlc_bar_archive(
        archive_id=archive_id, source=mark_source() if source is None else source, bars=(*bars, *extra)
    )


# --- A. the policy, the approval and the approval tables -----------------------------------------------------------------


def other_value(value: object) -> object:
    """A different value of ``value``'s field; an int for a bool (equal, but never the same type)."""

    if type(value) is bool:
        return int(value)
    if type(value) is int:
        return value + 1
    if type(value) is str:
        return f"{value}-x"
    if type(value) is tuple:
        return value[:-1]
    raise AssertionError(type(value))


def test_the_policy_fixes_every_r2_constant_and_only_its_id_instrument_and_source_vary() -> None:
    policy = regime_policy()
    verification = verify_governed_paper_regime_policy(policy)
    assert (verification.intact, verification.reason_codes, verification.recomputed_digest) == (
        True,
        (),
        policy.policy_digest,
    )
    assert (policy.methodology_id, policy.methodology_revision) == ("S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1", "r2")
    expected = {
        "bar_price_semantics": "mark_price",
        "bar_interval_ns": 300 * SECOND,
        "knowledge_deadline_ns": 300 * SECOND,
        "price_crisis_kind": "COMPLETE",
        "price_crisis_up_ratio": "23/20",
        "price_crisis_down_ratio": "17/20",
        "price_crisis_max_span_bars": 12,
        "price_crisis_window_closes": 289,
        "volatility_window_closes": 25,
        "trend_ema_fast_hours": 12,
        "trend_ema_slow_hours": 48,
        "trend_ema_truncation_multiple": 4,
        "trend_atr_hours": 24,
        "trend_strength_bound": "3/2",
        "hysteresis_confirmations": 3,
        "hysteresis_memory_evaluations": 288,
        "overlay_transitions": 4,
        "overlay_window_evaluations": 288,
        "overlay_hold_evaluations": 72,
        "regime_pass_label_window": 649,
        "cooldown_window_evaluations": 96,
        "cooldown_pass_label_window": 385,
        "book_freshness_ns": 10 * SECOND,
        "liquidity_band_ratio": "1/1000",
        "liquidity_samples": 288,
        "spread_samples": 6,
        "execution_fail_latency_ns": 300_000_000,
        "system_state_edge_tier": "T1",
        "system_state_required": "SS-0",
        "paper_only": True,
        "calibrated": False,
        "crisis_coverage_guaranteed": False,
        "production_use_authorized": False,
    }
    assert {name: getattr(policy, name) for name in expected} == expected
    axes = (
        policy.regime_cell_price_states,
        policy.regime_cell_funding_states,
        policy.regime_cell_leverage_states,
        policy.regime_cell_liquidity_states,
    )
    assert [len(axis) for axis in axes] == [2, 5, 3, 3] and len(list(itertools.product(*axes))) == 90
    assert policy.regime_cell_price_states == ("RANGE", "HIGH_VOL")
    assert policy.implemented_items == GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS
    # any other value of any methodology field, resealed, is not the approved methodology
    for item in fields(policy):
        if item.name in ("policy_id", "instrument", "bar_source_digest", "policy_digest"):
            continue
        forged = resealed_policy(policy, **{item.name: other_value(getattr(policy, item.name))})
        verification = verify_governed_paper_regime_policy(forged)
        assert (verification.intact, verification.reason_codes) == (
            False,
            (code("policy_not_the_approved_methodology"),),
        ), item.name
    # a stale digest, a malformed source digest and a non-policy are never intact
    assert verify_governed_paper_regime_policy(replace(policy, policy_digest="0" * 64)).intact is False
    for forged, reason in (
        (resealed_policy(policy, bar_source_digest="x"), "bar_source_digest_invalid"),
        (resealed_policy(policy, instrument=""), "instrument_invalid"),
        (object(), "policy_malformed"),
    ):
        verification = verify_governed_paper_regime_policy(forged)
        assert (verification.intact, verification.reason_codes) == (False, (code(reason),))
    # only the policy id, the instrument and the bound MARK source vary
    other = regime_policy("synthetic-regime-policy-2")
    assert verify_governed_paper_regime_policy(other).intact and other.policy_digest != policy.policy_digest


def test_the_approval_is_exactly_the_human_construction_scope_and_never_production_permission() -> None:
    assert GOVERNED_PAPER_REGIME_APPROVED_ITEMS == (
        *(f"CL1-{k}" for k in range(1, 14)),
        *(f"CL2-{k}" for k in range(1, 12)),
    )
    assert GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS == ("CL1-14", "CL2-12", "CL2-13")
    assert not set(GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS) & set(GOVERNED_PAPER_REGIME_APPROVED_ITEMS)
    assert GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS == (
        *(f"CL1-{k}" for k in range(1, 14)),
        *(f"CL2-{k}" for k in range(1, 8)),
    )
    approval = regime_approval()
    verification = verify_governed_paper_regime_approval(approval)
    assert (verification.intact, verification.recomputed_digest) == (True, approval.approval_digest)
    assert approval.approved_items == GOVERNED_PAPER_REGIME_APPROVED_ITEMS
    assert approval.production_use_authorized is False
    for changes in (
        {"approved_items": (*GOVERNED_PAPER_REGIME_APPROVED_ITEMS, "CL1-14")},  # an excluded item is never approved
        {"approved_items": GOVERNED_PAPER_REGIME_APPROVED_ITEMS[:-1]},
        {"production_use_authorized": True},
        {"schema_version": "governed-paper-regime-approval.v2"},
    ):
        verification = verify_governed_paper_regime_approval(resealed_approval(approval, **changes))
        assert (verification.intact, verification.reason_codes) == (False, (code("approval_not_the_approved_scope"),))
    for forged, reason in (
        (
            resealed_approval(approval, approval_kind="TEST_ONLY_SYNTHETIC"),
            "approval_kind_invalid",
        ),  # a str, not the kind
        (resealed_approval(approval, policy_digest="x"), "approval_policy_digest_invalid"),
        (object(), "approval_malformed"),
    ):
        verification = verify_governed_paper_regime_approval(forged)
        assert (verification.intact, verification.reason_codes) == (False, (code(reason),))
    with pytest.raises(GovernedPaperRegimeError, match=f"^{code('approver_reference_invalid')}$"):
        build_governed_paper_regime_approval(
            approval_id="a-1", approval_kind=SYNTHETIC, policy_digest="0" * 64, approver_reference=""
        )


def test_the_production_table_admits_no_approval_and_the_test_only_table_only_synthetic_ones() -> None:
    assert regime._APPROVAL_TABLE is PRODUCTION_TABLE  # noqa: SLF001
    assert (PRODUCTION_TABLE.table_id, PRODUCTION_TABLE.admitted_kind, PRODUCTION_TABLE.admitted_policy_digests) == (
        "production",
        HUMAN,
        (),
    )
    synthetic, human = regime_approval(), regime_approval(HUMAN)
    admission = regime._admission  # noqa: SLF001
    assert admission(PRODUCTION_TABLE, synthetic) == "synthetic_approval_refused_on_the_production_table"
    assert admission(PRODUCTION_TABLE, human) == "policy_not_authorized_for_production_use"
    assert admission(TEST_ONLY_TABLE, human) == "only_test_only_synthetic_approvals_on_the_test_only_table"
    assert admission(TEST_ONLY_TABLE, synthetic) == ""
    for table in (
        object(),
        replace(PRODUCTION_TABLE, admitted_kind=SYNTHETIC),
        replace(PRODUCTION_TABLE, table_id="staging"),
        replace(PRODUCTION_TABLE, admitted_policy_digests=["0" * 64]),
        replace(PRODUCTION_TABLE, admitted_policy_digests=("x",)),
        replace(TEST_ONLY_TABLE, admitted_kind=HUMAN),
        replace(TEST_ONLY_TABLE, admitted_policy_digests=(regime_policy().policy_digest,)),
    ):
        with pytest.raises(GovernedPaperRegimeError, match=f"^{code('approval_table_malformed')}$"):
            regime._canonical_table(table)  # noqa: SLF001


# --- B. D-PC2 / D-PC1 on 289-close windows --------------------------------------------------------------------------------

M = 20_000  # SYNTHETIC evaluation index of the pure price-crisis checks


def flat(k: int) -> Fraction:
    return Fraction(100)


def step(at: int, level: Fraction):  # noqa: ANN201
    """100 before bar ``at``, ``level`` from it on."""

    def price(k: int) -> Fraction:
        return Fraction(100) if k < at else level

    return price


def ramp(start: int, rise: Fraction, count: int, last: Fraction = UNIT * 0):  # noqa: ANN201
    """100 up to bar ``start``, then ``rise`` per bar for ``count`` bars (``last`` added on arrival), then flat."""

    def price(k: int) -> Fraction:
        steps = min(max(k - start, 0), count)
        return 100 + rise * steps + (last if k >= start + count else 0)

    return price


def late_at(late: int, at: int):  # noqa: ANN201
    """Every bar published one second after its close, but bar ``late`` at ``at``."""

    def visible(k: int) -> int:
        return at if k == late else published(k)

    return visible


def crisis_at(price, m: int = M, **options: object) -> str:  # noqa: ANN001
    """The D-PC1 state of evaluation ``m`` over the bars ``m - 300..m + 1`` of ``price``."""

    archive = mark_archive(price, m - 300, m + 1, **options)  # type: ignore[arg-type]
    bars = regime._Bars(archive, m - 300, m + 1)  # noqa: SLF001
    witnesses = regime._crisis_witnesses(bars, m - 300, m + 1)  # noqa: SLF001
    return regime._price_crisis(bars, witnesses, [item[0] for item in witnesses], m, m * BAR + KAPPA)  # noqa: SLF001


def test_dpc2_is_strictly_beyond_15pct_within_12_bars_of_the_289_close_window() -> None:
    # exactly +-15% is no witness; one scale-18 unit beyond is
    assert crisis_at(step(M - 6, Fraction(115))) == NON
    assert crisis_at(step(M - 6, 115 + UNIT)) == CRISIS
    assert crisis_at(step(M - 6, Fraction(85))) == NON
    assert crisis_at(step(M - 6, 85 - UNIT)) == CRISIS
    # a 12-bar span counts, a 13-bar one never does: 15.6% over 13 bars is at most 14.4% over any 12
    assert crisis_at(ramp(M - 20, Fraction("1.2"), 13)) == NON
    assert crisis_at(ramp(M - 20, Fraction("1.25"), 12)) == NON  # exactly 15% over 12 bars
    assert crisis_at(ramp(M - 20, Fraction("1.25"), 12, UNIT)) == CRISIS
    # the window is [m - 288, m]: a move into it counts, one completed before it never does
    assert crisis_at(step(M - 287, Fraction(116))) == CRISIS  # 100 at m - 288, 116 at m - 287
    assert crisis_at(step(M - 288, Fraction(116))) == NON  # the last 100 is m - 289
    assert crisis_at(step(M, Fraction(116))) == CRISIS
    assert crisis_at(step(M, Fraction(116)), M - 1) == NON


def test_dpc1_a_witness_proves_crisis_on_partial_data_and_only_a_complete_window_proves_its_absence() -> None:
    assert crisis_at(flat) == NON
    for missing in (M - 288, M - 100, M):  # one missing close of 289, at either edge or inside
        assert crisis_at(flat, missing=frozenset({missing})) == UNKNOWN
    assert crisis_at(flat, missing=frozenset({M - 289})) == NON  # outside the window
    assert crisis_at(step(M - 6, Fraction(116)), missing=frozenset({M - 100})) == CRISIS  # a visible witness suffices
    # a close published after kappa(m) is unknown at m: never assumed calm, never a witness yet
    assert crisis_at(flat, visible=late_at(M, M * BAR + KAPPA)) == NON  # exactly at kappa(m)
    assert crisis_at(flat, visible=late_at(M, M * BAR + KAPPA + 1)) == UNKNOWN
    assert crisis_at(step(M, Fraction(116)), visible=late_at(M, M * BAR + KAPPA + 1)) == UNKNOWN
    assert crisis_at(step(M, Fraction(116)), M + 1, visible=late_at(M, M * BAR + KAPPA + 1)) == CRISIS


# --- C. sigma_r, TS and the A1 possibility sets ---------------------------------------------------------------------------

# Integer quadruples whose squares sum to 45, 46 and 47: returns +-a/400 (12 or fewer, the rest 0) have mean 0 and
# sample variance (2 x sum / 400^2) / 23, which is exactly 1/40000 for 46.
SQUARES = {45: (6, 3), 46: (6, 3, 1), 47: (6, 3, 1, 1)}


def sigma_returns(squares: tuple[int, ...], scale: int) -> list[Fraction]:
    returns = [sign * scale * Fraction(item, 400) for item in squares for sign in (1, -1)]
    return returns + [Fraction(0)] * (24 - len(returns))


def sigma_bucket(squares: tuple[int, ...], scale: int, m: int = M) -> str:
    closes = [Fraction(400**8)]  # every close an integer
    for item in sigma_returns(squares, scale):
        closes.append(closes[-1] * (1 + item))

    def price(k: int) -> Fraction:
        return closes[max(k - (m - 24), 0)]

    archive = mark_archive(price, m - 24, m)
    return regime._sigma_bucket(regime._Bars(archive, m - 24, m), m)  # noqa: SLF001


@pytest.mark.parametrize(("scale", "below", "at"), [(1, "LOW", "MED"), (3, "MED", "HIGH"), (7, "HIGH", "EXTREME")])
def test_sigma_r_buckets_are_strict_and_an_equality_goes_to_the_higher_bucket(scale: int, below: str, at: str) -> None:
    assert statistics.variance(sigma_returns(SQUARES[46], scale)) == Fraction(scale * scale, 40_000)
    assert statistics.variance(sigma_returns(SQUARES[45], scale)) < Fraction(scale * scale, 40_000)
    assert sigma_bucket(SQUARES[45], scale) == below
    assert sigma_bucket(SQUARES[46], scale) == at
    assert sigma_bucket(SQUARES[47], scale) == at


TS_HOUR = 2_000  # SYNTHETIC hour of the pure TS checks; its 192-hour window starts at hour 1_809
TS_FIRST, TS_LAST = 12 * (TS_HOUR - 191) + 1, 12 * TS_HOUR + 12


def ema_lead(span: int) -> Fraction:
    """Independent oracle: the normalized weight of the latest close of a truncated EMA over 4 x span closes."""

    alpha = Fraction(2, span + 1)
    return alpha / sum(alpha * (1 - alpha) ** i for i in range(4 * span))


def trend_state(half_range: Fraction, move: Fraction, *, missing: frozenset[int] = NOTHING, hourly: bool = False):  # noqa: ANN201
    """The TS of hour ``TS_HOUR``: flat hours of close 100 and range 2 x ``half_range``, then a last close 100 + move."""

    bars = []
    for k in range(TS_FIRST, TS_LAST + 1):
        if k in missing:
            continue
        close = Fraction(100) + (move if k == TS_LAST else 0)
        high = max(Fraction(100) + half_range, close)
        low = min(Fraction(100) - half_range, close)
        bars.append(mark_bar(k, Fraction(100), close, published(k), high, low))
    source = mark_source()
    if hourly:  # a supplied hourly bar of a wild close: the hourly bar is the exact aggregation, never the declared one
        source = mark_source(bar_intervals_ns=(BAR, HOUR))
        bars.extend(
            mark_bar(hour + 1, Fraction(1_000), Fraction(1_000), (hour + 1) * HOUR + SECOND, interval=HOUR)
            for hour in range(TS_HOUR - 191, TS_HOUR + 1)
        )
    archive = build_historical_ohlc_bar_archive(archive_id="synthetic-regime-ts", source=source, bars=tuple(bars))
    return regime._Trend(regime._Bars(archive, TS_FIRST, TS_LAST)).state(TS_HOUR)  # noqa: SLF001


def test_ts_is_strict_at_one_unit_against_an_independent_ema_oracle() -> None:
    fast, slow = regime._FAST_WEIGHTS, regime._SLOW_WEIGHTS  # noqa: SLF001
    assert (Fraction(fast[0][0], fast[1]), Fraction(slow[0][0], slow[1])) == (ema_lead(12), ema_lead(48))
    # flat hours of range 2h and a last close 100 + 10: |EMA12 - EMA48| = 10 (lead12 - lead48), ATR24 = (47h + 10)/24
    move = Fraction(10)
    threshold = (16 * move * (ema_lead(12) - ema_lead(48)) - move) / 47
    below = Fraction(math.floor(threshold / UNIT)) * UNIT
    assert below < threshold < below + UNIT  # the threshold is not a scale-18 value: one unit decides
    visible = published(TS_LAST)
    assert trend_state(below, move) == ("STRONG_UP", visible)
    assert trend_state(below + UNIT, move) == ("NOT_STRONG", visible)
    assert trend_state(below, -move) == ("STRONG_DOWN", visible)
    assert trend_state(below + UNIT, -move) == ("NOT_STRONG", visible)
    # ATR24 = 0 leaves TS unavailable at its visibility; a missing 5-minute bar leaves its hour, and TS, unavailable
    assert trend_state(Fraction(0), Fraction(0)) == ("UNAVAILABLE", visible)
    assert trend_state(below, move, missing=frozenset({12 * (TS_HOUR - 100) + 5})) == ("UNAVAILABLE", regime._INFINITY)  # noqa: SLF001
    assert trend_state(below, move, hourly=True) == ("STRONG_UP", visible)


CRISES = (CRISIS, NON, UNKNOWN)
TRENDS = ("STRONG_UP", "STRONG_DOWN", "NOT_STRONG", "UNAVAILABLE")
VOLATILITIES = ("LOW", "MED", "HIGH", "EXTREME", "UNKNOWN")


def a1(crisis: bool, strong: bool, volatility: str) -> str:
    if crisis:
        return "CRISIS"
    if strong:
        return "TRENDING"
    return "HIGH_VOL" if volatility in ("HIGH", "EXTREME") else "RANGE"


def test_the_label_is_the_single_class_every_completion_of_the_unknown_inputs_allows() -> None:
    for crisis, trend, volatility in itertools.product(CRISES, TRENDS, VOLATILITIES):
        crises = (True, False) if crisis == UNKNOWN else (crisis == CRISIS,)
        strongs = (True, False) if trend == "UNAVAILABLE" else (trend in ("STRONG_UP", "STRONG_DOWN"),)
        volatilities = ("LOW", "MED", "HIGH", "EXTREME") if volatility == "UNKNOWN" else (volatility,)
        expected = {a1(*item) for item in itertools.product(crises, strongs, volatilities)}
        possible = regime._possible(crisis, trend, volatility)  # noqa: SLF001
        assert set(possible) == expected, (crisis, trend, volatility)
        assert list(possible) == [item for item in ("CRISIS", "TRENDING", "HIGH_VOL", "RANGE") if item in expected]
        if crisis == CRISIS:
            assert possible == ("CRISIS",)  # a proven price crisis decides, whatever else is unknown
        if crisis == UNKNOWN:
            assert "CRISIS" in possible  # an unobserved crisis is never assumed absent


# --- D. the books ---------------------------------------------------------------------------------------------------------

BEST_BID, BEST_ASK, TICK = Fraction("99.95"), Fraction("100.05"), Fraction(1, 100)
LOT = Fraction(100)


def ladder(best_bid: Fraction, best_ask: Fraction, quantity: Fraction, tick: Fraction, levels: int) -> tuple:
    return (
        {best_bid - tick * i: quantity for i in range(levels)},
        {best_ask + tick * i: quantity for i in range(levels)},
    )


@functools.cache
def book_record(  # noqa: ANN201, PLR0913
    event: int,
    visible: int,
    best_bid: Fraction = BEST_BID,
    best_ask: Fraction = BEST_ASK,
    quantity: Fraction = LOT,
    tick: Fraction = TICK,
    levels: int = 50,
):
    """A SYNTHETIC depth-50 ORDER_BOOK tip (the producer's value names), sequenced by its event instant."""

    values = ingt.expected_book_values(ladder(best_bid, best_ask, quantity, tick, levels))
    return build_historical_pit_record(
        series_id="book",
        data_requirement_key="order_book",
        instrument=INS,
        sequence_id=event,
        event_time_ns=event,
        available_at_ns=visible,
        finalized_at_ns=visible,
        revision_vintage_id=None,
        values=tuple(HistoricalPitValue(name, value) for name, value in sorted(values.items())),
    )


def tip(index: int, before: int = SECOND, *, after: int = 1, **book: object):  # noqa: ANN201
    """The tip whose event is ``before`` ns before g_index and which is visible ``after`` ns after its event."""

    event = index * BAR - before
    return book_record(event, event + after, **book)  # type: ignore[arg-type]


def book_dataset(records: tuple | list, *, chain: tuple | None = None, dataset_id: str = "synthetic-books"):  # noqa: ANN201
    manifest, _, registry = ingt.world_chain() if chain is None else chain
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id=dataset_id,
        correlation_id="corr-1",
        source_reference="archive:synthetic-books",
        rights_status="own_research",
        rights_reference="license-1",
        records=tuple(records),
    )


Q = 30_000  # SYNTHETIC grid index of the pure sample checks


def samples(records: tuple | list, first: int = Q, last: int = Q + 2):  # noqa: ANN201
    return regime._Samples(book_dataset(records), INS, first, last)  # noqa: SLF001


def test_a_book_sample_is_the_exact_band_depth_and_relative_spread_or_nothing() -> None:
    def reading(best_bid: str, best_ask: str, tick: str = "0.01"):  # noqa: ANN202
        record = book_record(SECOND, SECOND, Fraction(best_bid), Fraction(best_ask), LOT, Fraction(tick), 50)
        return regime._reading_of(regime._parse_book(record))  # noqa: SLF001

    base = reading("99.95", "100.05")
    # oracle: the quote notional of the levels inside the band [99.9, 100.1] around the mid 100, its edges included
    inside = sum(BEST_BID - TICK * i for i in range(6)) + sum(BEST_ASK + TICK * i for i in range(6))
    assert (Fraction(base.depth, 10**36), base.spread, base.unusable) == (LOT * inside, Fraction(1, 1_000), "")
    assert reading("100.05", "100.05").unusable == "book_crossed"
    assert reading("100.06", "100.05").unusable == "book_crossed"
    # the 50th levels must lie strictly beyond the band: at its edges (99.9 and 100.1) the band is not covered
    assert reading("99.949", "100.051", "0.001").unusable == "book_depth_does_not_cover_the_10bps_band"
    assert reading("99.948", "100.052", "0.001").unusable == ""


def test_a_malformed_tip_is_never_parsed() -> None:
    good = book_record(SECOND, SECOND)
    values = {item.name: item.value for item in good.values}
    assert regime._parse_book(good) is not None  # noqa: SLF001

    def parsed(**changes: str | None) -> object:
        changed = {**values, **changes}
        record = build_historical_pit_record(
            series_id="book",
            data_requirement_key="order_book",
            instrument=INS,
            sequence_id=1,
            event_time_ns=SECOND,
            available_at_ns=SECOND,
            finalized_at_ns=SECOND,
            revision_vintage_id=None,
            values=tuple(HistoricalPitValue(n, v) for n, v in sorted(changed.items()) if v is not None),
        )
        return regime._parse_book(record)  # noqa: SLF001

    assert parsed(bid_50_price=None, bid_50_quantity=None) is None  # 49 levels: not the producer's depth 50
    assert parsed(bid_51_price=d(1), bid_51_quantity=d(1)) is None  # an unknown name
    assert parsed(bid_01_price=values["bid_02_price"], bid_02_price=values["bid_01_price"]) is None  # unordered
    assert parsed(best_bid_price=values["bid_02_price"]) is None  # the best is not level 1
    assert parsed(ask_10_quantity=d(0)) is None


def test_a_sample_reads_only_a_fresh_tip_visible_at_s_and_a_late_tip_never_changes_it() -> None:
    def depth(records: tuple) -> list:  # noqa: ANN202
        return samples(records).depth

    assert depth((tip(Q, 10 * SECOND),))[0] is not None  # exactly 10 s old: fresh
    assert depth((tip(Q, 10 * SECOND + 1),))[0] is None  # one nanosecond older: stale
    assert depth((tip(Q, SECOND, after=SECOND + 1),)) == [None, None, None]  # visible after s, stale by the next s
    # B3 / A/B oracle: B adds a tip with the LATEST event before g_Q (half a second) that is published 5.5 s after it.
    # An as-of-later reading would relabel the sample at g_Q with it; the frozen sample never changes.
    a = (tip(Q, SECOND),)
    b = (*a, tip(Q, SECOND // 2, after=6 * SECOND, quantity=Fraction(10)))
    assert samples(a).depth[0] is not None
    assert samples(a).depth == samples(b).depth and samples(a).spread == samples(b).spread
    # a crossed tip gives no sample but blocks nothing; a malformed tip blocks every later sample
    crossed = (tip(Q, SECOND), tip(Q + 1, SECOND, best_bid=Fraction("100.06")), tip(Q + 2, SECOND))
    assert [item is None for item in depth(crossed)] == [False, True, False]
    malformed = (tip(Q, SECOND), tip(Q + 1, SECOND, levels=49), tip(Q + 2, SECOND))
    assert [item is None for item in depth(malformed)] == [False, True, True]


def liquidity(now: int, others: int, *, gap: int | None = None) -> str:
    records = [tip(Q + i, quantity=Fraction(others)) for i in range(287) if i != gap]
    records.append(tip(Q + 287, quantity=Fraction(now)))
    return samples(records, Q, Q + 287).liquidity(Q + 287)


@pytest.mark.parametrize(
    ("now", "others", "boundary", "below", "at"),
    [
        (41, 137, Fraction(3, 10), "DRY", "THIN"),
        (2_009, 2_873, Fraction(7, 10), "THIN", "NORMAL"),
    ],
)
def test_liquidity_thresholds_are_strict_below_and_an_equality_goes_up(
    now: int, others: int, boundary: Fraction, below: str, at: str
) -> None:
    assert Fraction(288 * now, now + 287 * others) == boundary  # depth is linear in the uniform quantity
    assert liquidity(now, others) == at
    assert liquidity(now - 1, others) == below


def test_liquidity_normal_includes_3_2_and_an_incomplete_window_is_unknown() -> None:
    assert Fraction(288 * 287, 287 + 287 * 191) == Fraction(3, 2)
    assert liquidity(287, 191) == "NORMAL"
    assert liquidity(288, 191) == "DEEP"
    assert liquidity(100, 100, gap=100) == "UNKNOWN"  # one of the 288 samples missing


def spread_state(units: tuple[int, ...]) -> str:
    records = [
        tip(Q + i, best_bid=100 - Fraction(unit, 200), best_ask=100 + Fraction(unit, 200))
        for i, unit in enumerate(units)
    ]
    return samples(records, Q, Q + 5).spread_state(Q + 5)


def spread_cv_squared(units: tuple[int, ...]) -> Fraction:
    spreads = [Fraction(unit, 10_000) for unit in units]
    return statistics.variance(spreads) / statistics.mean(spreads) ** 2


def test_spread_cv_thresholds_are_exact_and_an_equality_goes_up() -> None:
    for units, cv_squared, state in (
        ((2, 3, 3, 5, 6, 6), None, "STABLE"),
        ((1, 3, 3, 5, 6, 6), Fraction(1, 4), "WIDENING"),  # CV exactly 1/2
        ((1, 1, 1, 1, 4, 15), None, "WIDENING"),
        ((1, 1, 1, 1, 4, 16), Fraction(9, 4), "BLOWN"),  # CV exactly 3/2
        ((10, 10, 10, 10, 10, 10), Fraction(0), "STABLE"),
    ):
        if cv_squared is not None:
            assert spread_cv_squared(units) == cv_squared
        assert spread_state(units) == state, units
    assert spread_cv_squared((2, 3, 3, 5, 6, 6)) < Fraction(1, 4)
    assert spread_cv_squared((1, 1, 1, 1, 4, 15)) < Fraction(9, 4)


def test_the_book_series_is_judged_on_its_own_manifest_with_the_producer_semantics() -> None:
    records = (tip(Q),)
    assert regime._book_series(book_dataset(records), INS) == ("", "book")  # noqa: SLF001
    assert regime._book_series(book_dataset(records), ingt.ETH) == (  # noqa: SLF001
        "order_book_series_not_in_the_selected_data_contract",
        "",
    )
    substituted = est.substituted_chain("order_book", "historical_source", "mark_price_history_v1")
    assert regime._book_series(book_dataset(records, chain=substituted), INS) == (  # noqa: SLF001
        "order_book_series_semantics_unsupported",
        "",
    )


# --- E. A8 hysteresis ------------------------------------------------------------------------------------------------------


def hysteresis_oracle(labels: list[str], first: int, last: int, **parameters: int) -> tuple[dict, dict]:
    """Independent, unbounded A8: rescan every run, every transition and every count from scratch."""

    confirmations, memory = parameters["confirmations"], parameters["memory"]
    window, threshold, hold = parameters["window"], parameters["threshold"], parameters["hold"]

    def confirmed(m: int) -> str:
        for end in range(m, m - memory, -1):
            start = end - confirmations + 1
            if start < 0:
                break
            if len(set(labels[start : end + 1])) == 1:
                return labels[end]
        return "UNKNOWN"

    def count(k: int) -> int:
        return sum(confirmed(e) != confirmed(e - 1) for e in range(k - window + 1, k + 1))

    return (
        {m: confirmed(m) for m in range(first, last + 1)},
        {m: any(count(k) >= threshold for k in range(m - hold + 1, m + 1)) for m in range(first, last + 1)},
    )


@pytest.mark.parametrize(
    ("parameters", "symbols", "length"),
    [
        (
            {"confirmations": 2, "memory": 3, "window": 3, "threshold": 2, "hold": 2},
            ("RANGE", "HIGH_VOL", "UNKNOWN"),
            9,
        ),
        ({"confirmations": 3, "memory": 4, "window": 4, "threshold": 2, "hold": 3}, ("RANGE", "TRENDING"), 13),
    ],
)
def test_a8_equals_the_unbounded_oracle_over_every_small_history(
    parameters: dict[str, int], symbols: tuple[str, ...], length: int
) -> None:
    # the earliest evaluation whose overlay reads only confirmed states derived from whole label windows
    first = parameters["memory"] + parameters["confirmations"] - 2 + parameters["hold"] + parameters["window"] - 1
    for labels in itertools.product(symbols, repeat=length):
        sequence = list(labels)
        assert regime._confirmations(sequence, 0, first, length - 1, **parameters) == hysteresis_oracle(  # noqa: SLF001
            sequence, first, length - 1, **parameters
        ), labels
    with pytest.raises(GovernedPaperRegimeError, match=f"^{code('confirmation_window_outside_the_labels')}$"):
        regime._confirmations(list(symbols) * length, 0, first - 1, len(symbols) * length - 1, **parameters)  # noqa: SLF001


def run_labels(*runs: tuple[str, int]) -> list[str]:
    return [label for label, count in runs for _ in range(count)]


def test_a8_confirms_on_k_equal_labels_remembers_288_and_holds_the_overlay_72() -> None:
    confirm = regime._confirmations  # noqa: SLF001
    # K - 1 vs K: two HIGH_VOL never confirm, three do
    two = run_labels(("RANGE", 700), ("HIGH_VOL", 2), ("RANGE", 50))
    three = run_labels(("RANGE", 700), ("HIGH_VOL", 3), ("RANGE", 50))
    assert set(confirm(two, 0, 648, len(two) - 1)[0].values()) == {"RANGE"}
    confirmed = confirm(three, 0, 648, len(three) - 1)[0]
    assert (confirmed[701], confirmed[702], confirmed[705]) == ("RANGE", "HIGH_VOL", "RANGE")
    # the memory: the RANGE run ending at 699 confirms up to 699 + 287, never at 699 + 288 (no run follows it)
    fading = run_labels(("RANGE", 700), *((("HIGH_VOL", 2), ("UNKNOWN", 2)) * 80))
    confirmed = confirm(fading, 0, 648, len(fading) - 1)[0]
    assert (confirmed[699 + 287], confirmed[699 + 288]) == ("RANGE", "UNKNOWN")
    # the overlay: four transitions within 288 evaluations force it, and it holds 72 after the count falls below four
    four = run_labels(("RANGE", 700), ("HIGH_VOL", 3), ("RANGE", 3), ("HIGH_VOL", 3), ("RANGE", 500))
    _, overlays = confirm(four, 0, 648, len(four) - 1)
    t1, t4 = 702, 711  # the four transitions are at 702, 705, 708 and 711
    assert (overlays[t4 - 1], overlays[t4]) == (False, True)
    assert (overlays[t1 + 287 + 71], overlays[t1 + 287 + 72]) == (True, False)
    assert sum(overlays.values()) == (t1 + 287 + 71) - t4 + 1
    three_transitions = run_labels(("RANGE", 700), ("HIGH_VOL", 3), ("RANGE", 3), ("HIGH_VOL", 503))
    assert not any(confirm(three_transitions, 0, 648, len(three_transitions) - 1)[1].values())


# --- F. the rule set v6 readings on synthetic frozen logs -----------------------------------------------------------------


def synthetic_log(labels: list[str], columns: dict[int, dict[str, str]] | None = None):  # noqa: ANN201
    """A SYNTHETIC frozen log over ``labels`` (labels from 0, evaluations from 648) with per-index column overrides."""

    first, last = 648, len(labels) - 1
    confirmed, overlays = regime._confirmations(labels, 0, first, last)  # noqa: SLF001
    possible = [(label,) if label != "UNKNOWN" else ("HIGH_VOL", "RANGE") for label in labels]
    evaluations = []
    for m in range(first, last + 1):
        values = {
            "price_crisis": CRISIS if labels[m] == "CRISIS" else UNKNOWN if labels[m] == "UNKNOWN" else NON,
            "trend": "STRONG_UP" if labels[m] == "TRENDING" else "NOT_STRONG",
            "volatility": "HIGH" if labels[m] == "HIGH_VOL" else "MED",
            "liquidity": "NORMAL",
            "spread": "STABLE",
            **(columns or {}).get(m, {}),
        }
        evaluations.append(
            GovernedPaperRegimeEvaluation(
                index=m,
                close_time_ns=m * BAR,
                knowledge_time_ns=m * BAR + KAPPA,
                label=labels[m],
                possible=possible[m],
                confirmed=confirmed[m],
                pending=labels[m] != confirmed[m],
                overlay=overlays[m],
                **values,
            )
        )
    return regime._Log(0, first, last, labels, possible, evaluations)  # noqa: SLF001


def readings(log: object, n: int, direction: str = "SHORT", latency: int = 50_000_000) -> dict[str, tuple]:
    reading = regime._readings(log, (1, (n + 1) * BAR, direction), latency)  # noqa: SLF001
    assert reading.evaluation_index == n
    return {item.check_id: (item.status, item.observed, item.reason) for item in reading.checks}


N = 1_500  # the evaluation the synthetic decisions read


def test_fb_regime_passes_only_on_a_definite_649_label_window_with_a_confirmed_range_or_high_vol() -> None:
    calm = ["RANGE"] * 1_600
    assert readings(synthetic_log(calm), N)["FB-REGIME"] == (
        P,
        "RANGE/RANGE",
        "range_or_high_vol_confirmed_and_proven_non_crisis",
    )
    for back, status in ((648, B), (649, P)):  # an UNKNOWN label inside [n - 648, n] blocks; one before it does not
        labels = list(calm)
        labels[N - back] = "UNKNOWN"
        expected = (
            "price_regime_proof_window_not_definite"
            if status is B
            else "range_or_high_vol_confirmed_and_proven_non_crisis"
        )
        assert readings(synthetic_log(labels), N)["FB-REGIME"] == (status, "RANGE/RANGE", expected)
    high = ["HIGH_VOL"] * 1_600
    assert readings(synthetic_log(high), N)["FB-REGIME"][0] is P
    cases = {
        "CRISIS": (F, "price_regime_crisis"),
        "TRENDING": (F, "price_regime_trending"),
    }
    for label, (status, reason) in cases.items():
        labels = [*calm[:N], label]
        assert readings(synthetic_log(labels), N)["FB-REGIME"][::2] == (status, reason)
    unknown = [*calm[:N], "UNKNOWN"]
    assert readings(synthetic_log(unknown), N)["FB-REGIME"] == (
        B,
        "UNKNOWN/RANGE",
        "price_regime_unknown_never_admits_family_b",
    )
    # no possible class admits Family B: whichever completion holds, FB-REGIME fails
    log = synthetic_log(unknown)
    log.possible[N] = ("CRISIS", "TRENDING")
    log.evaluations[N - 648] = replace(log.evaluations[N - 648], possible=("CRISIS", "TRENDING"))
    assert readings(log, N)["FB-REGIME"][::2] == (F, "no_possible_price_regime_admits_family_b")
    # a confirmed TRENDING fails even when the current label is RANGE; the overlay fails whatever the label
    trending = [*calm[:1_400], *["TRENDING"] * 3, *["RANGE", "HIGH_VOL"] * 50]
    assert readings(synthetic_log(trending), N)["FB-REGIME"] == (F, "HIGH_VOL/TRENDING", "price_regime_trending")
    flapping = [*calm[:1_480], *(["HIGH_VOL"] * 3 + ["RANGE"] * 3) * 2, *calm[:9]]
    log = synthetic_log(flapping)
    assert log.entry(N).overlay is True
    assert readings(log, N)["FB-REGIME"][::2] == (F, "price_regime_oscillation_overlay_forces_the_defensive_state")
    # no confirmed state (the latest run is an UNKNOWN one): BLOCKED, never PASS
    unconfirmed = [*calm[:1_300], *["UNKNOWN"] * 3, *["RANGE", "HIGH_VOL"] * 100]
    assert readings(synthetic_log(unconfirmed), N)["FB-REGIME"] == (B, "HIGH_VOL/UNKNOWN", "price_regime_not_confirmed")


def test_fb_regime_cooldown_fails_on_trending_in_96_and_passes_only_on_385_definite_labels() -> None:
    calm = ["RANGE"] * 1_600
    pass_reason = (P, "", "no_trending_within_the_8h_union_window")
    assert readings(synthetic_log(calm), N)["FB-REGIME-COOLDOWN"] == pass_reason
    for back, expected in ((95, (F, "95", "trending_within_the_8h_union_window")), (96, pass_reason)):
        labels = list(calm)
        labels[N - back] = "TRENDING"
        assert readings(synthetic_log(labels), N)["FB-REGIME-COOLDOWN"] == expected
    for back, status in ((384, B), (385, P)):
        labels = list(calm)
        labels[N - back] = "UNKNOWN"
        assert readings(synthetic_log(labels), N)["FB-REGIME-COOLDOWN"][0] is status
    # a TRENDING confirmed state inside the window fails though no label in it is TRENDING
    confirmed = [*calm[: N - 200], *["TRENDING"] * 3, *["RANGE", "HIGH_VOL"] * 120]
    log = synthetic_log(confirmed)
    assert {log.label(m) for m in range(N - 95, N + 1)} == {"RANGE", "HIGH_VOL"}
    assert readings(log, N)["FB-REGIME-COOLDOWN"][::2] == (F, "trending_within_the_8h_union_window")


def test_nt_m03_fails_on_a_pending_price_transition_and_never_passes() -> None:
    calm = ["RANGE"] * 1_600
    assert readings(synthetic_log(calm), N)["NT-M03"] == (
        B,
        "RANGE/RANGE",
        "funding_leverage_and_liquidity_hysteresis_not_produced",
    )
    for tail in (["HIGH_VOL"], ["HIGH_VOL"] * 2, ["UNKNOWN"]):  # a label not (yet) confirmed: K - 1 equal labels
        labels = [*calm[: N + 1 - len(tail)], *tail]
        assert readings(synthetic_log(labels), N)["NT-M03"][::2] == (
            F,
            "price_regime_transition_in_its_hysteresis_window",
        )
    confirmed = [*calm[: N - 2], *["HIGH_VOL"] * 3]
    assert readings(synthetic_log(confirmed), N)["NT-M03"][0] is B


def test_fb_trend_fails_only_a_strong_ts_aligned_with_the_faded_direction() -> None:
    calm = ["RANGE"] * 1_600
    for trend, short, long in (
        ("STRONG_UP", F, P),
        ("STRONG_DOWN", P, F),
        ("NOT_STRONG", P, P),
        ("UNAVAILABLE", B, B),
    ):
        log = synthetic_log(calm, {N: {"trend": trend}})
        assert (readings(log, N, "SHORT")["FB-TREND"][0], readings(log, N, "LONG")["FB-TREND"][0]) == (short, long)


def test_fb_activation_fails_a_proven_forbidden_column_and_otherwise_never_passes() -> None:
    calm = ["RANGE"] * 1_600
    cases = (
        ({"volatility": "LOW"}, 50_000_000, F, "volatility_low_forbidden_for_family_b"),  # RANGE + LOW
        ({"volatility": "EXTREME"}, 50_000_000, F, "volatility_extreme_forbidden_for_family_b"),
        ({"liquidity": "DRY"}, 50_000_000, F, "liquidity_dry_forbidden_for_family_b"),
        ({"spread": "BLOWN"}, 50_000_000, F, "spread_blown_forbidden_for_family_b"),
        ({}, 300_000_000, F, "execution_at_least_impaired_latency_at_or_above_300ms"),
        ({}, 299_999_999, B, "execution_fill_rate_and_exchange_health_unproven_on_the_paper_path"),
        ({"volatility": "UNKNOWN"}, 50_000_000, B, "volatility_unproven"),
        ({"liquidity": "UNKNOWN"}, 50_000_000, B, "liquidity_unproven"),
        ({"spread": "UNKNOWN"}, 50_000_000, B, "spread_unproven"),
        (
            {"liquidity": "DEEP", "spread": "WIDENING"},
            50_000_000,
            B,
            "execution_fill_rate_and_exchange_health_unproven_on_the_paper_path",
        ),
    )
    for columns, latency, status, reason in cases:
        log = synthetic_log(calm, {N: columns})
        assert readings(log, N, latency=latency)["FB-ACTIVATION"][::2] == (status, reason), columns
    high = ["HIGH_VOL"] * 1_600
    log = synthetic_log(high, {N: {"volatility": "EXTREME"}})  # HIGH_VOL + EXTREME
    assert readings(log, N)["FB-ACTIVATION"][::2] == (F, "volatility_extreme_forbidden_for_family_b")
    assert readings(log, N)["FB-REGIME"][0] is P


def test_the_cell_and_system_state_checks_never_pass_and_unknown_never_passes_any_check() -> None:
    calm = ["RANGE"] * 1_600
    calm_reading = readings(synthetic_log(calm), N)
    assert calm_reading["FB-REGIME-CELL"] == (B, "RANGE/RANGE", "leverage_and_liquidity_regime_dimensions_not_produced")
    assert calm_reading["SYSTEM-STATE"] == (
        B,
        "",
        "system_state_engine_not_produced_family_b_is_t1_and_needs_a_proven_ss0",
    )
    for label in ("CRISIS", "TRENDING"):
        assert readings(synthetic_log([*calm[:N], label]), N)["FB-REGIME-CELL"][0] is F
    # over every label history of a small alphabet around n: UNKNOWN never passes, four checks never pass
    never = ("NT-M03", "FB-ACTIVATION", "FB-REGIME-CELL", "SYSTEM-STATE")
    for tail in itertools.product(("RANGE", "HIGH_VOL", "TRENDING", "UNKNOWN"), repeat=4):
        log = synthetic_log([*calm[: N - 3], *tail])
        reading = readings(log, N)
        assert all(reading[name][0] is not P for name in never), tail
        if reading["FB-REGIME"][0] is P:
            entry = log.entry(N)
            assert entry.label in ("RANGE", "HIGH_VOL") and entry.confirmed in ("RANGE", "HIGH_VOL")
            assert log.definite(N - 648, N) and entry.price_crisis == NON
        if reading["FB-REGIME-COOLDOWN"][0] is P:
            assert log.definite(N - 384, N)


# --- G. the derivation over the synthetic world R --------------------------------------------------------------------------

GR = 19_001 * DAY  # SYNTHETIC genesis of world R (a UTC midnight)
NR = GR // BAR - 1  # n(GR)
HR = GR + 2 * HOUR
R_FIRST_BAR = NR - 3_700
R_DECISIONS = ((1, GR + 10 * SECOND, "SHORT"), (2, GR + HOUR, "LONG"))
LATE_BAR = NR + 5  # not the last bar of an hour: only its own windows read it


def calm(k: int) -> Fraction:
    """World R's calm path: 100 and 101 alternating (1% moves, flat hourly closes): MED, NOT_STRONG, RANGE."""

    return Fraction(100) if k % 2 == 0 else Fraction(101)


def quiet(k: int) -> Fraction:
    return Fraction(100) if k % 2 == 0 else Fraction("100.1")  # 0.1% moves: LOW, RANGE


def wild(k: int) -> Fraction:
    return Fraction(100) if k % 2 == 0 else Fraction(104)  # 4% moves: EXTREME, HIGH_VOL


def jump(k: int) -> Fraction:
    return calm(k) * (Fraction(117, 100) if k >= NR - 10 else 1)  # +17% within the trailing hour: CRISIS


def rising(k: int) -> Fraction:
    return 100 + Fraction(1, 100) * (k - R_FIRST_BAR)  # a steady rise: STRONG_UP, TRENDING


PATHS = {"calm": calm, "quiet": quiet, "wild": wild, "jump": jump, "rising": rising}


@functools.cache
def world_r_archive(path: str = "calm", horizon: int = HR, late: int | None = None) -> HistoricalOhlcBarArchive:
    visible = published if late is None else late_at(LATE_BAR, late)
    return mark_archive(
        PATHS[path], R_FIRST_BAR, horizon // BAR + 1, visible=visible, archive_id=f"synthetic-regime-r-{path}"
    )


@functools.cache
def world_r_books(variant: str = "normal", horizon: int = HR) -> HistoricalPitDataset:
    """One fresh depth-50 tip per grid instant from 300 evaluations before GR (variants change the books at NR)."""

    records = []
    for index in range(NR - 300, decision_evaluation_index(horizon - 1) + 1):
        book: dict[str, object] = {}
        if variant == "dry" and index == NR:
            book = {"quantity": Fraction(10)}
        if variant == "blown" and NR - 5 <= index <= NR:
            unit = (1, 1, 1, 1, 4, 16)[index - (NR - 5)]
            book = {"best_bid": 100 - Fraction(unit, 200), "best_ask": 100 + Fraction(unit, 200)}
        records.append(tip(index, **book))  # type: ignore[arg-type]
    if variant == "late":  # B adds a DRY tip with the latest event before g_NR, published after g_NR
        records.append(tip(NR, SECOND // 2, after=6 * SECOND, quantity=Fraction(10)))
    return book_dataset(records, dataset_id=f"synthetic-regime-r-books-{variant}-{horizon}")


def derive_r(**changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "policy": regime_policy(),
        "approval": regime_approval(),
        "archive": world_r_archive(),
        "dataset": world_r_books(),
        "instrument": INS,
        "genesis_start_ns": GR,
        "horizon_ns": HR,
        "decisions": R_DECISIONS,
        "latency_ns": 50_000_000,
    }
    values.update(changes)
    return derive_governed_paper_regime_evidence(**values)  # type: ignore[arg-type]


def statuses(reading: GovernedPaperRegimeReading) -> dict[str, tuple]:
    return {item.check_id: (item.status, item.reason) for item in reading.checks}


NON_CLAIMS = (
    ("paper_only", True),
    ("production_use_authorized", False),
    ("intrabar_state_claimed", False),
    ("real_market_source_qualified", False),
    ("venue_facts_proven", False),
    ("calibrated", False),
    ("crisis_coverage_guaranteed", False),
    ("t10_measured", False),
    ("live_ready", False),
    ("edge_proven", False),
    ("profitability_proven", False),
)


def test_the_derivation_reads_every_check_of_a_calm_world_and_never_passes_four_of_them(test_only_table: None) -> None:
    evidence = derive_r()
    first, last = NR - 648, decision_evaluation_index(HR - 1)
    assert (evidence.log_first_index, evidence.log_last_index, len(evidence.evaluations)) == (
        first,
        last,
        last - first + 1,
    )
    assert (evidence.approval_table_id, evidence.approval_admitted, evidence.approval_reason) == ("test_only", True, "")
    assert (evidence.book_series_id, evidence.book_series_reason) == ("book", "")
    assert evidence.synthetic_regime_approval_used is True
    payload = governed_paper_regime_evidence_to_dict(evidence)
    assert [(name, payload[name]) for name, _ in NON_CLAIMS] == list(NON_CLAIMS)
    assert evidence.evidence_digest == governed_paper_regime_evidence_digest(evidence)
    assert evidence.contract_id == GOVERNED_PAPER_REGIME_CONTRACT_ID
    entry = evidence.evaluations[NR - first]
    assert (entry.label, entry.price_crisis, entry.trend, entry.volatility, entry.liquidity, entry.spread) == (
        "RANGE",
        NON,
        "NOT_STRONG",
        "MED",
        "NORMAL",
        "STABLE",
    )
    short, long = evidence.readings
    assert (short.evaluation_index, long.evaluation_index) == (NR, NR + 12)
    assert statuses(short) == {
        "FB-TREND": (P, "no_strong_trend_aligned_with_the_faded_funding_direction"),
        "FB-REGIME": (P, "range_or_high_vol_confirmed_and_proven_non_crisis"),
        "FB-REGIME-COOLDOWN": (P, "no_trending_within_the_8h_union_window"),
        "NT-M03": (B, "funding_leverage_and_liquidity_hysteresis_not_produced"),
        "FB-ACTIVATION": (B, "execution_fill_rate_and_exchange_health_unproven_on_the_paper_path"),
        "FB-REGIME-CELL": (B, "leverage_and_liquidity_regime_dimensions_not_produced"),
        "SYSTEM-STATE": (B, "system_state_engine_not_produced_family_b_is_t1_and_needs_a_proven_ss0"),
    }
    assert short.check("FB-ACTIVATION").observed == "MED/NORMAL/STABLE/50000000"
    assert statuses(long) == statuses(short)
    # a pure derivation: the memo returns the very evidence, and a memo-free re-derivation is identical
    assert derive_r() is evidence
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(regime, "_MEMO", OrderedDict())
        assert derive_r() == evidence


@pytest.mark.parametrize(
    ("path", "books", "latency", "expected"),
    [
        ("calm", "dry", 50_000_000, {"FB-ACTIVATION": (F, "liquidity_dry_forbidden_for_family_b")}),
        ("calm", "blown", 50_000_000, {"FB-ACTIVATION": (F, "spread_blown_forbidden_for_family_b")}),
        (
            "calm",
            "normal",
            300_000_000,
            {"FB-ACTIVATION": (F, "execution_at_least_impaired_latency_at_or_above_300ms")},
        ),
        (
            "quiet",
            "normal",
            50_000_000,
            {
                "FB-REGIME": (P, "range_or_high_vol_confirmed_and_proven_non_crisis"),
                "FB-ACTIVATION": (F, "volatility_low_forbidden_for_family_b"),
            },
        ),
        (
            "wild",
            "normal",
            50_000_000,
            {
                "FB-REGIME": (P, "range_or_high_vol_confirmed_and_proven_non_crisis"),
                "FB-ACTIVATION": (F, "volatility_extreme_forbidden_for_family_b"),
            },
        ),
        (
            "jump",
            "normal",
            50_000_000,
            {
                "FB-REGIME": (F, "price_regime_crisis"),
                "FB-REGIME-CELL": (F, "price_regime_outside_the_declared_family_b_cells"),
            },
        ),
        (
            "rising",
            "normal",
            50_000_000,
            {
                "FB-TREND": (F, "strong_trend_aligned_with_the_faded_funding_direction"),
                "FB-REGIME": (F, "price_regime_trending"),
                "FB-REGIME-COOLDOWN": (F, "trending_within_the_8h_union_window"),
                "FB-REGIME-CELL": (F, "price_regime_outside_the_declared_family_b_cells"),
            },
        ),
    ],
)
def test_the_derivation_measures_each_family_b_refusal_on_its_own_synthetic_path(
    test_only_table: None, path: str, books: str, latency: int, expected: dict[str, tuple]
) -> None:
    evidence = derive_r(archive=world_r_archive(path), dataset=world_r_books(books), latency_ns=latency)
    short = statuses(evidence.readings[0])
    assert {name: short[name] for name in expected} == expected
    assert short["NT-M03"][0] is not P and short["SYSTEM-STATE"][0] is B
    assert evidence.readings[1].check("FB-TREND").status is (P if path == "rising" else short["FB-TREND"][0])


def test_the_production_table_refuses_every_approval_and_applies_no_method() -> None:
    for approval, reason in (
        (regime_approval(), "synthetic_approval_refused_on_the_production_table"),
        (regime_approval(HUMAN), "policy_not_authorized_for_production_use"),
    ):
        evidence = derive_r(approval=approval)
        assert (evidence.approval_table_id, evidence.approval_admitted, evidence.approval_reason) == (
            "production",
            False,
            reason,
        )
        assert (evidence.evaluations, evidence.log_first_index, evidence.book_series_id) == ((), None, "")
        assert evidence.synthetic_regime_approval_used is False
        for reading in evidence.readings:
            assert reading.evaluation_index is None
            assert [(item.check_id, item.status, item.reason) for item in reading.checks] == [
                (name, B, f"regime_policy_not_admitted:{reason}") for name in GOVERNED_PAPER_REGIME_CHECK_IDS
            ]
        assert governed_paper_regime_state_at(evidence, HR - 1) is None
    with approval_table(TEST_ONLY_TABLE):
        evidence = derive_r(approval=regime_approval(HUMAN))
        assert evidence.approval_reason == "only_test_only_synthetic_approvals_on_the_test_only_table"


def test_every_input_is_re_proven_and_a_malformed_or_foreign_one_is_refused(test_only_table: None) -> None:
    policy, archive, dataset = regime_policy(), world_r_archive(), world_r_books()
    last_trade = mark_source(price_semantics=HistoricalOhlcPriceSemantics.LAST_TRADE)
    foreign = regime_policy(source_digest=historical_ohlc_source_declaration_digest(last_trade))
    hourly = mark_source(bar_intervals_ns=(HOUR,))
    cases = (
        ({"policy": replace(policy, policy_digest="0" * 64)}, "policy_not_authentic"),
        ({"policy": resealed_policy(policy, trend_atr_hours=14)}, "policy_not_authentic"),
        ({"approval": regime_approval(policy_id="synthetic-regime-policy-2")}, "approval_not_of_the_policy"),
        ({"approval": replace(regime_approval(), approval_digest="0" * 64)}, "approval_not_of_the_policy"),
        ({"instrument": ingt.ETH}, "instrument_not_of_the_policy"),
        ({"archive": object()}, "archive_malformed"),
        ({"archive": replace(archive, archive_digest="0" * 64)}, "archive_not_authentic"),
        (
            {"archive": mark_archive(calm, NR - 3, NR, source=mark_source(source_id="other"))},
            "archive_not_of_the_policy_source",
        ),
        (
            {
                "policy": foreign,
                "approval": approval_of(foreign),
                "archive": mark_archive(calm, NR - 3, NR, source=last_trade),
            },
            "archive_not_of_the_policy_source",
        ),
        ({"dataset": object()}, "dataset_malformed"),
        ({"dataset": replace(dataset, dataset_digest="0" * 64)}, "dataset_not_authentic"),
        ({"genesis_start_ns": 3_000 * BAR}, "evaluation_horizon_invalid"),
        ({"horizon_ns": GR}, "evaluation_horizon_invalid"),
        ({"latency_ns": -1}, "latency_ns_invalid"),
        ({"horizon_ns": True}, "horizon_ns_invalid"),
        ({"decisions": [(1, GR, "SHORT")]}, "decisions_malformed"),
        ({"decisions": ((1, GR, "FLAT"),)}, "decisions_malformed"),
        ({"decisions": ((True, GR, "SHORT"),)}, "decisions_malformed"),
        ({"decisions": ((1, GR - 1, "SHORT"),)}, "decision_outside_the_evaluation_horizon"),
        ({"decisions": ((1, HR, "SHORT"),)}, "decision_outside_the_evaluation_horizon"),
        ({"decisions": ((2, GR, "SHORT"), (1, GR + 1, "SHORT"))}, "decisions_not_ordered"),
        ({"decisions": ((1, GR + 1, "SHORT"), (2, GR, "SHORT"))}, "decisions_not_ordered"),
    )
    for changes, reason in cases:
        with pytest.raises(GovernedPaperRegimeError, match=f"^{code(reason)}$"):
            derive_r(**changes)
    assert hourly.bar_intervals_ns == (HOUR,)  # a policy of an hourly-only source never reads 5-minute bars
    hourly_policy = regime_policy("synthetic-regime-policy-h", historical_ohlc_source_declaration_digest(hourly))
    with pytest.raises(GovernedPaperRegimeError, match=f"^{code('archive_not_of_the_policy_source')}$"):
        derive_r(
            policy=hourly_policy,
            approval=approval_of(hourly_policy),
            archive=build_historical_ohlc_bar_archive(
                archive_id="hourly",
                source=hourly,
                bars=(mark_bar(NR // 12, Fraction(100), Fraction(100), NR * BAR, interval=HOUR),),
            ),
        )


def test_a_bar_published_after_kappa_m_is_unknown_at_m_and_never_relabels_it(test_only_table: None) -> None:
    kappa = LATE_BAR * BAR + KAPPA
    decisions = ((1, kappa - 1, "SHORT"), (2, kappa, "SHORT"))
    on_time = derive_r(archive=world_r_archive(late=kappa), decisions=decisions)
    late = derive_r(archive=world_r_archive(late=kappa + 1), decisions=decisions)
    first = NR - 648
    assert on_time.evaluations[LATE_BAR - first].label == "RANGE"
    entry = late.evaluations[LATE_BAR - first]
    assert (entry.label, entry.possible, entry.price_crisis, entry.volatility, entry.trend) == (
        "UNKNOWN",
        ("CRISIS", "HIGH_VOL", "RANGE"),
        UNKNOWN,
        "UNKNOWN",
        "NOT_STRONG",
    )
    assert late.evaluations[LATE_BAR + 1 - first].label == "RANGE"  # known one evaluation later
    # the kappa boundary: a decision one nanosecond before kappa(m) reads m - 1, at kappa(m) it reads m
    before, at = late.readings
    assert (before.evaluation_index, at.evaluation_index) == (LATE_BAR - 1, LATE_BAR)
    assert before.check("FB-REGIME").status is P
    assert statuses(at)["FB-REGIME"] == (B, "price_regime_unknown_never_admits_family_b")
    assert statuses(at)["NT-M03"] == (F, "price_regime_transition_in_its_hysteresis_window")
    assert statuses(at)["FB-REGIME-COOLDOWN"] == (B, "cooldown_proof_window_not_definite")
    # every evaluation but the late bar's windows is the same; none is ever revised
    changed = {item.index for item, other in zip(on_time.evaluations, late.evaluations, strict=True) if item != other}
    assert min(changed) == LATE_BAR and LATE_BAR + 1 not in changed
    # arriving only after the horizon, the bar never relabels a sealed evaluation: the later log keeps m UNKNOWN
    after = HR + 10 * SECOND
    sealed = derive_r(archive=world_r_archive(late=after), decisions=decisions)
    later = derive_r(
        archive=world_r_archive(horizon=HR + HOUR, late=after),
        dataset=world_r_books(horizon=HR + HOUR),
        horizon_ns=HR + HOUR,
        decisions=decisions,
    )
    assert later.evaluations[: len(sealed.evaluations)] == sealed.evaluations
    assert governed_paper_regime_prefix_digest(later, before_ns=HR) == (
        governed_paper_regime_prefix_digest(sealed, before_ns=HR)
    )
    assert later.evaluations[LATE_BAR - first].label == "UNKNOWN"
    assert later.evaluations[decision_evaluation_index(after) + 1 - first].label == "RANGE"
    # the cost of immutability (disclosed P2): one late bar blocks FB-REGIME for the 649 evaluations (54 h) reading it
    blocked, passed = (LATE_BAR + 649) * BAR, (LATE_BAR + 650) * BAR  # kappa(LATE_BAR + 648), kappa(LATE_BAR + 649)
    long = derive_r(
        archive=world_r_archive(horizon=passed + BAR, late=kappa + 1),
        horizon_ns=passed + BAR,
        decisions=((1, blocked, "SHORT"), (2, passed, "SHORT")),
    )
    assert [statuses(reading)["FB-REGIME"] for reading in long.readings] == [
        (B, "price_regime_proof_window_not_definite"),
        (P, "range_or_high_vol_confirmed_and_proven_non_crisis"),
    ]


def test_the_10s_state_record_and_the_prefix_never_depend_on_the_horizon(test_only_table: None) -> None:
    longer = HR + HOUR
    short = derive_r()
    long = derive_r(
        archive=world_r_archive(horizon=longer),
        dataset=world_r_books(horizon=longer),
        horizon_ns=longer,
        decisions=((1, GR + 10 * SECOND, "SHORT"),),
    )
    count = len(short.evaluations)
    assert long.evaluations[:count] == short.evaluations
    for before in (GR, GR + HOUR, HR):
        assert governed_paper_regime_prefix_digest(short, before_ns=before) == governed_paper_regime_prefix_digest(
            long, before_ns=before
        )
    assert governed_paper_regime_prefix_digest(long, before_ns=HR) != governed_paper_regime_prefix_digest(
        long, before_ns=HR + BAR
    )
    # the 10 s record is the step function of the frozen evaluations, changing only at a knowledge instant
    previous = None
    for at in range(GR, HR, 10 * SECOND):
        state = governed_paper_regime_state_at(short, at)
        assert state is short.evaluations[decision_evaluation_index(at) - (NR - 648)]
        assert state == governed_paper_regime_state_at(long, at)
        if previous is not None and state is not previous:
            assert at % BAR == 0 and at == state.knowledge_time_ns
        previous = state
    first = short.evaluations[0]
    assert governed_paper_regime_state_at(short, first.knowledge_time_ns - 1) is None
    assert governed_paper_regime_state_at(short, first.knowledge_time_ns) is first
    with pytest.raises(GovernedPaperRegimeError, match=f"^{code('state_instant_beyond_the_evaluation_horizon')}$"):
        governed_paper_regime_state_at(short, HR)
    for bad, reason in ((object(), "evidence_malformed"), (-1, "state_instant_invalid")):
        with pytest.raises(GovernedPaperRegimeError, match=f"^{code(reason)}$"):
            governed_paper_regime_state_at(*((bad, GR) if reason == "evidence_malformed" else (short, bad)))  # type: ignore[arg-type]


def test_a_late_book_never_relabels_a_frozen_sample_of_the_log(test_only_table: None) -> None:
    a, b = derive_r(), derive_r(dataset=world_r_books("late"))
    assert a.evaluations == b.evaluations and a.readings == b.readings
    assert a.dataset_digest != b.dataset_digest  # the evidence still names the archive it read
    assert derive_r(dataset=world_r_books("dry")).evaluations[648].liquidity == "DRY"  # the same tip, on time


# --- H. rule set v6 in the gate --------------------------------------------------------------------------------------------

REGIME_EVIDENCE = "7" * 64  # SYNTHETIC regime evidence digest of the gate observations
V6_ADDED = ("FB-ACTIVATION", "FB-REGIME-CELL", "SYSTEM-STATE")
READ_IN_PLACE = ("NT-M03", "FB-TREND", "FB-REGIME", "FB-REGIME-COOLDOWN")


def regime_facts(states: dict[str, GovernedPaperRegimeStatus] | None = None, **changes: object):  # noqa: ANN201
    """SYNTHETIC rule set v6 facts of the base observation (decision 7, SHORT at ``est.T``)."""

    checks = tuple(
        GovernedPaperRegimeCheckReading(
            name, (states or {}).get(name, B), f"seen-{name.lower()}", f"why_{name.lower()}"
        )
        for name in GOVERNED_PAPER_REGIME_CHECK_IDS
    )
    reading = GovernedPaperRegimeReading(7, est.T, "SHORT", decision_evaluation_index(est.T), checks)
    values: dict[str, object] = {"reading": replace(reading, **changes), "evidence_digest": REGIME_EVIDENCE}
    return GovernedPaperEntrySafetyRegime(**values)  # type: ignore[arg-type]


def v6_decision(states: dict[str, GovernedPaperRegimeStatus] | None = None, **observation: object):  # noqa: ANN201
    return evaluate_governed_paper_entry_safety(
        est.measured(kill_switch=kst.ks(), regime=regime_facts(states), **observation)
    )


def test_rule_set_v6_adds_only_its_regime_rule_and_three_checks_and_v1_to_v5_keep_their_identities() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    ) == (
        est.ACCEPTED_MAIN_RULE_SET_V1_DIGEST,
        est.ACCEPTED_MAIN_RULE_SET_V2_DIGEST,
        est.RULE_SET_V3_DIGEST,
        est.RULE_SET_V4_DIGEST,
        ACCEPTED_MAIN_RULE_SET_V5_DIGEST,
    )
    v6, v5 = GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET
    added = ("rule_set_id", "contract_id", "checks", "regime_rule")
    assert {key: value for key, value in v6.items() if key not in added} == {
        key: value for key, value in v5.items() if key not in added
    }
    assert v6["checks"][: len(v5["checks"])] == v5["checks"]  # type: ignore[index, arg-type]
    assert [item["check_id"] for item in v6["checks"][len(v5["checks"]) :]] == list(V6_ADDED)  # type: ignore[index, arg-type]
    assert (v6["rule_set_id"], v6["contract_id"]) == (
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_ID,
        GOVERNED_PAPER_REGIME_CONTRACT_ID,
    )
    rule = v6["regime_rule"]
    assert rule["methodology"] == "S1_COMPLETE_ENTRY_METHODOLOGY_DECISION_V1:r2"  # type: ignore[index]
    assert rule["excluded_items"] == list(GOVERNED_PAPER_REGIME_EXCLUDED_ITEMS)  # type: ignore[index]
    assert rule["implemented_items"] == list(GOVERNED_PAPER_REGIME_IMPLEMENTED_ITEMS)  # type: ignore[index]
    assert rule["regime_check_ids"] == list(GOVERNED_PAPER_REGIME_CHECK_IDS)  # type: ignore[index]
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST
        == entry_safety.edge_sha256_text(entry_safety.edge_canonical_json(v6))
        == governed_paper_entry_safety_rule_set_digest(
            protective=True, portfolio=True, market_data=True, kill_switch=True, regime=True
        )
    )
    with pytest.raises(GovernedPaperEntrySafetyError, match="regime_rule_set_needs_the_kill_switch_rule_set$"):
        governed_paper_entry_safety_rule_set(protective=True, portfolio=True, market_data=True, regime=True)


def test_each_regime_reading_maps_onto_its_gate_check_with_its_evidence() -> None:
    mapping = {P: S.PASS, F: S.FAIL, B: BLOCKED}
    for status in (P, F, B):
        decision = v6_decision(dict.fromkeys(GOVERNED_PAPER_REGIME_CHECK_IDS, status))
        assert [item.check_id for item in decision.checks][-3:] == list(V6_ADDED) and len(decision.checks) == 36
        for name in GOVERNED_PAPER_REGIME_CHECK_IDS:
            check = est.check_of(decision, name)
            assert (check.status, check.observed, check.reason, check.evidence_record_digests) == (
                mapping[status],
                f"seen-{name.lower()}",
                est.code(f"{name}:why_{name.lower()}"),
                (REGIME_EVIDENCE,),
            )
        # no admission change: after the measured Data PASS the first refusal is still NT-R01
        assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-R01")
    # every other check is exactly its rule set v5 outcome
    legacy = evaluate_governed_paper_entry_safety(est.measured(kill_switch=kst.ks()))
    current = v6_decision()
    assert [item for item in current.checks if item.check_id not in (*READ_IN_PLACE, *V6_ADDED)] == [
        item for item in legacy.checks if item.check_id not in READ_IN_PLACE
    ]
    # a decision that is not Family B never reads the Family B checks
    other = v6_decision(dict.fromkeys(GOVERNED_PAPER_REGIME_CHECK_IDS, P), family_b_applicable=False)
    for name in (*READ_IN_PLACE[1:], *V6_ADDED):
        assert (est.check_of(other, name).status, est.check_of(other, name).reason) == (
            BLOCKED,
            est.code(f"{name}:family_b_applicability_undetermined"),
        )
    assert est.check_of(other, "NT-M03").status is S.PASS


def test_without_regime_facts_every_check_keeps_its_accepted_outcome() -> None:
    decision = evaluate_governed_paper_entry_safety(est.measured(kill_switch=kst.ks()))
    assert len(decision.checks) == 33
    for name, reason in (
        ("NT-M03", "regime_hysteresis_state_not_produced"),
        ("FB-TREND", "trend_strength_ema_atr_construction_not_defined_or_produced"),
        ("FB-REGIME", "regime_state_not_produced"),
        ("FB-REGIME-COOLDOWN", "trending_regime_history_not_produced"),
    ):
        check = est.check_of(decision, name)
        assert (check.status, check.observed, check.reason, check.evidence_record_digests) == (
            BLOCKED,
            "",
            est.code(f"{name}:{reason}"),
            (),
        )


def test_no_wallet_margin_utilization_or_dtl_reading_exists_in_the_regime_closure() -> None:
    tokens = ("wallet", "margin", "dtl", "utilization")
    assert not any(token in inspect.getsource(regime).lower() for token in tokens)
    rule = GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET["regime_rule"]
    names = [
        item.name
        for artifact in (GovernedPaperRegimePolicy, GovernedPaperRegimeEvidence, GovernedPaperRegimeEvaluation)
        for item in fields(artifact)
    ]
    for name in (*names, *rule, *(str(value) for value in rule.values())):  # type: ignore[union-attr]
        assert not any(token in name.lower() for token in tokens), name


@pytest.mark.parametrize(
    ("build", "name"),
    [
        (lambda: est.measured(kill_switch=kst.ks(), regime=object()), "regime"),
        (lambda: est.measured(regime=regime_facts()), "regime_without_the_kill_switch_facts"),
        (
            lambda: est.measured(kill_switch=kst.ks(), regime=replace(regime_facts(), evidence_digest="x")),
            "regime_evidence_digest",
        ),
        (lambda: est.measured(kill_switch=kst.ks(), regime=regime_facts(decision_sequence=8)), "regime_reading"),
        (lambda: est.measured(kill_switch=kst.ks(), regime=regime_facts(decision_time_ns=est.T + 1)), "regime_reading"),
        (lambda: est.measured(kill_switch=kst.ks(), regime=regime_facts(target_direction="LONG")), "regime_reading"),
        (
            lambda: est.measured(kill_switch=kst.ks(), regime=regime_facts(checks=regime_facts().reading.checks[::-1])),
            "regime_reading",
        ),
        (
            lambda: est.measured(kill_switch=kst.ks(), regime=regime_facts(checks=list(regime_facts().reading.checks))),
            "regime_reading",
        ),
        (
            lambda: est.measured(kill_switch=kst.ks(), regime=replace(regime_facts(), reading=object())),
            "regime_reading",
        ),
        (
            lambda: est.measured(
                kill_switch=kst.ks(),
                regime=regime_facts(
                    checks=(
                        replace(regime_facts().reading.checks[0], status="PASS"),
                        *regime_facts().reading.checks[1:],
                    )
                ),
            ),
            "regime_reading",
        ),
        (
            lambda: est.measured(
                kill_switch=kst.ks(),
                regime=regime_facts(
                    checks=(replace(regime_facts().reading.checks[0], reason=""), *regime_facts().reading.checks[1:])
                ),
            ),
            "regime_reading",
        ),
    ],
)
def test_malformed_regime_facts_are_refused(build: object, name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{est.code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(build())  # type: ignore[operator]


# --- I. world G's regime lineage (seal v7, evidence v7) -------------------------------------------------------------------

G_FIRST_BAR = gpe.G // BAR - 3_700


def calm_g(k: int) -> Fraction:
    """World G's SYNTHETIC regime MARK path: 40 and 40.4 alternating (MED, NOT_STRONG, RANGE)."""

    return Fraction(40) if k % 2 == 0 else Fraction("40.4")


@functools.cache
def regime_archive_g(
    day: int, drop: int | None = None, retime: tuple[int, int] | None = None
) -> HistoricalOhlcBarArchive:
    """World G's regime MARK archive sealed at E_(day + 1): exactly the bars visible then (``drop`` omits one bar and
    ``retime`` republishes one)."""

    end = gpe.instant(day + 1)

    def visible(k: int) -> int:
        return retime[1] if retime is not None and k == retime[0] else published(k)

    bars = tuple(
        mark_bar(k, calm_g(k - 1), calm_g(k), visible(k))
        for k in range(G_FIRST_BAR, end // BAR + 1)
        if k != drop and visible(k) <= end
    )
    return build_historical_ohlc_bar_archive(archive_id=f"synthetic-regime-g-{day}", source=mark_source(), bars=bars)


def regime_context(day: int, **archive: object) -> GovernedPaperEntrySafetyRegimeContext:
    return GovernedPaperEntrySafetyRegimeContext(regime_policy(), regime_approval(), regime_archive_g(day, **archive))  # type: ignore[arg-type]


def regime_day(days: tuple, context: object, table: GovernedPaperRegimeApprovalTable = TEST_ONLY_TABLE):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of world G on the kill-switch lineage with the regime ``context``."""

    world = gpe.scenario("G")
    day = len(days)
    prior = days[-1].seal if days else None
    cycle_inputs = gpe.cycle_inputs_for(day, prior, world=world)
    cycle = build_governed_paper_cycle_authority(cycle_inputs)
    protection = replace(
        lineage.protection_for(
            day, days, portfolio_no_trade=True, market_data_integrity=True, kill_switch_escalation=True
        ),
        regime=context,
    )
    seal_inputs = gpe.seal_inputs_for(
        day, cycle_inputs, cycle, prior, gpe.pending_of(days), world=world, protection=protection
    )
    with approval_table(table):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def regime_days(count: int, table: str = "test_only") -> tuple:
    """World G's first ``count`` days of the regime lineage (seal v7) under the named approval table."""

    if count == 0:
        return ()
    days = regime_days(count - 1, table)
    return (*days, regime_day(days, regime_context(len(days)), TABLES[table]))


def verify(seal: object, inputs: object, table: GovernedPaperRegimeApprovalTable = TEST_ONLY_TABLE):  # noqa: ANN201
    """The public seal verifier through the module attribute (the identity memo the lineage evidence shares)."""

    with approval_table(table):
        return gpe.execution.verify_governed_paper_day_seal(seal, inputs)


def verify_unmemoized(seal: object, inputs: object, table: GovernedPaperRegimeApprovalTable):  # noqa: ANN201
    """The public seal verifier without the identity memo: a seal re-proven under another approval table."""

    with approval_table(table):
        return gpe._SAME[(gpe.execution, "verify_governed_paper_day_seal")].real(seal, inputs)  # noqa: SLF001


def regime_lineage_evidence(days: tuple):  # noqa: ANN201
    with approval_table(TEST_ONLY_TABLE):
        return lineage.evidence_of(days)


@functools.cache
def regime_day_3_gate():  # noqa: ANN201
    """World G's sealed day-3 rule set v6 evaluation, rebuilt once through the public builders."""

    return public_gate(regime_days(4)[3], regime_context(3))


def public_gate(item: object, context: object, table: GovernedPaperRegimeApprovalTable = TEST_ONLY_TABLE):  # noqa: ANN201
    """The day's rule set v6 evaluation rebuilt independently through the public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    with approval_table(table):
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),  # type: ignore[attr-defined]
            market_data=True,
            kill_switch=True,
            regime=context,  # type: ignore[arg-type]
        )


def test_world_g_regime_lineage_changes_only_its_version_rule_set_and_bound_regime_evidence() -> None:
    days, legacy = regime_days(4), kst.kill_switch_days(4)
    for index, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V7, GovernedPaperDaySealStatus.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST
        for name in (
            "schedule",
            "governed_outcome_digest",
            "episodes",
            "funding_events",
            "sealed_history_digest",
            "kill_switch_ladder_digest",
            "kill_switch_prefix_digest_open",
            "kill_switch_prefix_digest_close",
        ):
            assert getattr(seal, name) == getattr(old.seal, name), name
        assert (seal.regime_policy_digest, seal.regime_approval_digest) == (
            regime_policy().policy_digest,
            regime_approval().approval_digest,
        )
        assert seal.regime_archive_digest == regime_archive_g(index).archive_digest
        if index:
            assert seal.regime_prefix_digest_open == days[index - 1].seal.regime_prefix_digest_close
        verification = verify(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    item = days[3]
    (entry,) = item.seal.entry_safety_decisions
    (old_entry,) = legacy[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # unchanged: no new admission
    assert [check for check in entry.checks if check.check_id not in (*READ_IN_PLACE, *V6_ADDED)] == [
        check for check in old_entry.checks if check.check_id not in READ_IN_PLACE
    ]
    measured = {check.check_id: (check.status, check.reason) for check in entry.checks}
    assert {name: measured[name] for name in (*READ_IN_PLACE, *V6_ADDED)} == {
        "NT-M03": (BLOCKED, est.code("NT-M03:funding_leverage_and_liquidity_hysteresis_not_produced")),
        "FB-TREND": (S.PASS, est.code("FB-TREND:no_strong_trend_aligned_with_the_faded_funding_direction")),
        "FB-REGIME": (S.PASS, est.code("FB-REGIME:range_or_high_vol_confirmed_and_proven_non_crisis")),
        "FB-REGIME-COOLDOWN": (S.PASS, est.code("FB-REGIME-COOLDOWN:no_trending_within_the_8h_union_window")),
        # world G's books carry the top of the book only: no depth-50 sample, so liquidity stays unproven
        "FB-ACTIVATION": (BLOCKED, est.code("FB-ACTIVATION:liquidity_unproven")),
        "FB-REGIME-CELL": (BLOCKED, est.code("FB-REGIME-CELL:leverage_and_liquidity_regime_dimensions_not_produced")),
        "SYSTEM-STATE": (
            BLOCKED,
            est.code("SYSTEM-STATE:system_state_engine_not_produced_family_b_is_t1_and_needs_a_proven_ss0"),
        ),
    }
    # the public builder re-derives exactly the sealed rule set v6 evaluation and its regime evidence
    evidence = regime_day_3_gate()
    regime_evidence = evidence.regime_evidence
    assert (evidence.rule_set_id, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    assert regime_evidence.evidence_digest == item.seal.regime_evidence_digest
    assert governed_paper_regime_prefix_digest(regime_evidence, before_ns=item.seal.window_start_ns) == (
        item.seal.regime_prefix_digest_open
    )
    assert governed_paper_regime_prefix_digest(regime_evidence, before_ns=item.seal.window_end_ns) == (
        item.seal.regime_prefix_digest_close
    )
    assert (regime_evidence.book_series_id, regime_evidence.synthetic_regime_approval_used) == ("book", True)
    assert {reading.decision_sequence for reading in regime_evidence.readings} == set(
        governed_paper_entry_safety_entry_sequences(est.run_and_evidence(item)[1])
    )  # entries only: an exit or a protective close-only action is never read
    states = {state.trigger_id: state.measurement for state in evidence.kill_switch_ladder.triggers}
    assert states["T10"] is GovernedPaperKillSwitchMeasurement.UNMEASURED  # T10 is never inferred from PRICE_CRISIS_V1
    lineage_evidence = regime_lineage_evidence(days)
    assert (lineage_evidence.schema_version, lineage_evidence.status) == (
        "governed-paper-execution-evidence.v7",
        GovernedPaperExecutionStatus.READY,
    )
    with approval_table(TEST_ONLY_TABLE):
        verification = verify_governed_paper_execution_evidence(lineage_evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert set(V7_FIELDS) <= set(governed_paper_day_seal_to_dict(item.seal))


def test_a_regime_lineage_is_one_from_day_0_or_never_and_only_on_a_kill_switch_lineage() -> None:
    days, legacy = regime_days(2), kst.kill_switch_days(2)
    for item, changes, reason in (
        (days[1], {"regime": None}, "regime_gate_lineage_switched"),
        (legacy[1], {"regime": regime_context(1)}, "regime_gate_lineage_switched"),
        (days[0], {"kill_switch_escalation": False}, "regime_gate_needs_the_kill_switch_lineage"),
        (days[1], {"regime": object()}, "protection_inputs_malformed:regime"),
    ):
        with approval_table(TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    # a relabelled version never verifies: a v7 seal cannot hide behind a v6 payload, a v6 seal labelled v7 never rebuilds
    assert verify(replace(days[1].seal, schema_version=V6), days[1].seal_inputs).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:regime_policy_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V6)
    for forged in (replace(legacy[1].seal, schema_version=V7), gpe.reseal_seal(legacy[1].seal, schema_version=V7)):
        assert kst.verify(forged, legacy[1].seal_inputs).intact is False


def test_the_regime_context_is_authentic_of_the_policy_and_known_at_the_seal() -> None:
    item = regime_days(2)[1]
    other = regime_policy("synthetic-regime-policy-2")
    eth = build_governed_paper_regime_policy(policy_id="eth", instrument=ingt.ETH, bar_source_digest=SOURCE_DIGEST)
    last_trade = mark_source(price_semantics=HistoricalOhlcPriceSemantics.LAST_TRADE)
    foreign = regime_policy("synthetic-regime-policy-lt", historical_ohlc_source_declaration_digest(last_trade))
    archive = regime_archive_g(1)
    late = mark_archive(
        calm_g, G_FIRST_BAR, gpe.instant(2) // BAR, archive_id="late"
    )  # its last bar is published E_2 + 1 s
    context = regime_context(1)
    for changed, reason in (
        (replace(context, policy=replace(regime_policy(), policy_digest="0" * 64)), "regime_policy_not_authentic"),
        (replace(context, approval=regime_approval(policy_id=other.policy_id)), "regime_approval_not_of_the_policy"),
        (replace(context, policy=eth, approval=approval_of(eth)), "regime_policy_not_of_the_genesis_instrument"),
        (replace(context, archive=object()), "regime_archive_malformed"),
        (replace(context, archive=replace(archive, archive_digest="0" * 64)), "regime_archive_not_authentic"),
        (
            replace(
                context,
                archive=mark_archive(calm_g, G_FIRST_BAR, G_FIRST_BAR + 3, source=mark_source(source_id="other")),
            ),
            "regime_archive_not_of_the_policy_source",
        ),
        (
            replace(
                context,
                policy=foreign,
                approval=approval_of(foreign),
                archive=mark_archive(calm_g, G_FIRST_BAR, G_FIRST_BAR + 3, source=last_trade),
            ),
            "regime_archive_not_of_the_policy_source",
        ),
        (replace(context, archive=late), "regime_archive_holds_a_bar_unknown_at_the_seal"),
        (
            replace(context, policy=other, approval=regime_approval(policy_id=other.policy_id)),
            "regime_policy_changed_inside_the_lineage",
        ),
    ):
        with approval_table(TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, regime=changed))


def test_a_forged_regime_fact_never_verifies_and_a_rewritten_prefix_or_bar_is_refused() -> None:
    days = regime_days(4)
    item = days[3]
    seal = item.seal
    (entry,) = seal.entry_safety_decisions
    forged_entry = replace(
        entry,
        checks=tuple(
            replace(check, status=S.FAIL) if check.check_id == "FB-REGIME" else check for check in entry.checks
        ),
    )
    for changed in (
        *({name: "0" * 64} for name in V7_FIELDS),
        {"entry_safety_decisions": (forged_entry,)},
        {"entry_safety_rule_set_digest": GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST},
    ):
        for forged in (replace(seal, **changed), gpe.reseal_seal(seal, **changed)):
            assert verify(forged, item.seal_inputs).intact is False
    # X1: a predecessor whose sealed regime prefix was rewritten (and resealed) is refused
    rewritten = gpe.reseal_seal(days[0].seal, regime_prefix_digest_close="0" * 64)
    with approval_table(TEST_ONLY_TABLE), gpe.refused("regime_prefix_rewritten"):
        build_governed_paper_day_seal(replace(days[1].seal_inputs, prior_seal=rewritten))
    # X1: a replay whose archive republishes a bar an earlier sealed evaluation read rewrites the sealed prefix
    bar = gpe.G // BAR + 5
    republished = regime_context(1, retime=(bar, gpe.instant(1) - SECOND))
    with approval_table(TEST_ONLY_TABLE), gpe.refused("regime_prefix_rewritten"):
        build_governed_paper_day_seal(kst.switched(days[1], regime=republished))
    # a v6 seal never carries a v7 fact, not even one that would verify elsewhere
    legacy = kst.kill_switch_days(1)[0].seal
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:regime_policy_digest$"):
        governed_paper_day_seal_to_dict(replace(legacy, regime_policy_digest=seal.regime_policy_digest))


def test_the_lineage_evidence_refuses_a_rewritten_or_backfilled_regime_archive_and_keeps_x1_on_a_late_one() -> None:
    days = regime_days(2)
    last = gpe.instant(1) // BAR - 1  # day 0's last bar: published 299 s before E_1, read by no evaluation before E_1
    # a later archive missing a bar of an earlier one rewrites it, though no sealed evaluation read that bar
    rewritten = regime_day(days[:1], regime_context(1, drop=last))
    assert rewritten.seal.status is GovernedPaperDaySealStatus.SEALED
    with pytest.raises(gpe.execution.GovernedPaperExecutionError, match=f"^{gpe.code('regime_archive_rewritten:1')}$"):
        regime_lineage_evidence((days[0], rewritten))
    # a bar first delivered on day 1 but published before E_1 is a backfill
    day0 = regime_day((), regime_context(0, drop=last))
    day1 = regime_day((day0,), regime_context(1))
    assert day0.seal.regime_prefix_digest_close == days[0].seal.regime_prefix_digest_close
    with pytest.raises(
        gpe.execution.GovernedPaperExecutionError, match=f"^{gpe.code('regime_archive_backfilled_before_the_day:1')}$"
    ):
        regime_lineage_evidence((day0, day1))
    # the same bar PUBLISHED after E_1 arrives on day 1 without a backfill: X1 holds, the lineage is READY, and the bar
    # enters only the evaluations whose knowledge instant follows its publication (its own stays UNKNOWN)
    arrived = regime_day((day0,), regime_context(1, retime=(last, gpe.instant(1) + 5 * SECOND)))
    assert arrived.seal.regime_prefix_digest_open == day0.seal.regime_prefix_digest_close
    assert regime_lineage_evidence((day0, arrived)).status is GovernedPaperExecutionStatus.READY
    with approval_table(TEST_ONLY_TABLE):
        log = derive_governed_paper_regime_evidence(
            policy=regime_policy(),
            approval=regime_approval(),
            archive=arrived.seal_inputs.protection.regime.archive,
            dataset=arrived.seal_inputs.dataset,
            instrument=INS,
            genesis_start_ns=gpe.G,
            horizon_ns=gpe.instant(2),
            decisions=(),
            latency_ns=0,
        )
    first = log.log_first_index
    assert (log.evaluations[last - first].label, log.evaluations[last - first].price_crisis) == ("UNKNOWN", UNKNOWN)
    assert log.evaluations[last + 1 - first].label == "RANGE"


def test_under_the_production_table_every_regime_reading_is_blocked_and_a_test_only_seal_never_verifies() -> None:
    (production,) = regime_days(1, "production")
    seal = production.seal
    assert (seal.schema_version, seal.status) == (V7, GovernedPaperDaySealStatus.SEALED)
    assert seal.regime_prefix_digest_open == seal.regime_prefix_digest_close  # no admitted approval: an empty log
    assert verify(seal, production.seal_inputs, PRODUCTION_TABLE).intact is True
    (test_only,) = regime_days(1)
    assert seal.regime_evidence_digest != test_only.seal.regime_evidence_digest
    assert verify_unmemoized(test_only.seal, test_only.seal_inputs, PRODUCTION_TABLE).intact is False
    # world G's day-3 entry under the production table: every regime check BLOCKED by the refused synthetic approval
    item = kst.kill_switch_days(4)[3]
    for approval, reason in (
        (regime_approval(), "synthetic_approval_refused_on_the_production_table"),
        (regime_approval(HUMAN), "policy_not_authorized_for_production_use"),
    ):
        context = replace(regime_context(3), approval=approval)
        evidence = public_gate(item, context, PRODUCTION_TABLE)
        (entry,) = evidence.decisions
        assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
        for name in GOVERNED_PAPER_REGIME_CHECK_IDS:
            check = est.check_of(entry, name)
            assert (check.status, check.reason) == (
                BLOCKED,
                est.code(f"{name}:regime_policy_not_admitted:{reason}"),
            ), name
        assert evidence.regime_evidence.evaluations == ()
    # the gate refuses a malformed context, a context without the kill-switch rule set and an underivable one
    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    base = {
        "authority": authority,
        "run": run,
        "dataset": item.seal_inputs.dataset,
        "invalidated_from_ns": None,
        "protection": est.seal_protection(item),
        "portfolio": GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),
        "market_data": True,
        "kill_switch": True,
    }
    for changes, reason in (
        ({"regime": object()}, "regime_context_malformed"),
        ({"regime": regime_context(3), "kill_switch": False}, "regime_without_the_kill_switch_rule_set"),
        (
            {"regime": replace(regime_context(3), approval=regime_approval(policy_id="synthetic-regime-policy-2"))},
            "regime_evidence_not_derivable",
        ),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{est.code(reason)}$"):
            build_governed_paper_entry_safety_evidence(**{**base, **changes})  # type: ignore[arg-type]


# --- J. legacy byte identity --------------------------------------------------------------------------------------------------


def test_world_g_kill_switch_lineage_is_byte_identical_to_accepted_main() -> None:
    days = kst.kill_switch_days(4)
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_V6_SEALS
    assert tuple(item.seal.entry_safety_evidence_digest for item in days) == ACCEPTED_MAIN_V6_ENTRY_EVIDENCE
    assert tuple(item.seal.kill_switch_ladder_digest for item in days) == ACCEPTED_MAIN_V6_LADDERS
    assert {item.seal.kill_switch_prefix_digest_close for item in days} == {ACCEPTED_MAIN_V6_LADDER_PREFIX}
    assert lineage.evidence_of(days).evidence_digest == ACCEPTED_MAIN_V6_EVIDENCE
    for item in days:
        assert item.seal.schema_version == V6
        assert not set(V7_FIELDS) & set(governed_paper_day_seal_to_dict(item.seal))
    # a v1-v5 entry evaluation never carries a regime evidence, not even a valid one
    evidence = regime_day_3_gate()
    legacy = replace(evidence, rule_set_id=GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_ID)
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_regime_evidence$"):
        governed_paper_entry_safety_evidence_digest(legacy)
