"""Governed paper approved sizing chain tests (S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1): schedule v5, rule set v8,
seal v9 and evidence v9.

SYNTHETIC TEST VALUES ONLY. Every world, policy, approval, qualification, capture, bound, price and instant here is a
synthetic fixture that exercises structure. None is a calibrated threshold, an approved EHS or Sharpe method, a venue
fact, a qualified source or a real human decision. The TEST-ONLY regime approval table is installed exactly as the
regime closure's tests install it, the TEST-ONLY CTR qualification table only where a test says so, and the permissive
entry table only inside the one test that exercises the engine's fill-time refusal; the PRODUCTION gate and tables stay
in force everywhere else.

It proves:

* A. the engine's schedule v5: its bounds are exact rationals, refused on any other schedule and never in a legacy
  payload; an exposure-increasing fill outside every envelope, above its fraction, against a book and side without a cap
  or at or above its cap is refused whole, never resized; equality admits the envelope and refuses the cap; a reduction
  or protective close never reads them; within proven bounds the fills are exactly schedule v4's;
* B. rule set v8 in the gate: every v1-v7 identity unchanged; ENVELOPE-FIT and CTR-DEPTH read the decision's own sizing
  reading; SCALE-1 under A9' keeps every rule set v7 FAIL with its reason, fails on ENVELOPE_FIT FAIL, names its complete
  multiplier inventory and never passes; the first refusal never moves; malformed facts refused;
* C. the decision reading: the usage, the exact publication-visible NAV and the reservation price, never the initial
  equity;
* D. world G's sizing chain lineage (seal v9, evidence v9): it changes only its version, schedule, rule set and bound
  sizing evidence; every entry is still refused; the public gate replays every sealed reading; lineage switches,
  relabelled versions and forged digests never verify; a CTR source is fixed for the lineage, its revocations
  append-only and inside their day, its capture complete through the seal and never rewritten or backfilled; under the
  TEST-ONLY qualification table its reading is available yet the depth cap stays BLOCKED;
* E. the fill-time refusal on the integrated path: with the decision-time gate forced open (permissive, test-only), the
  engine refuses every entry fill of a sizing lineage as unproven;
* F. legacy byte identity: world G's integrated lineage (seal v8, evidence v8) equals its accepted-main pins.
"""

from __future__ import annotations

import functools
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_ctr_qualification as ctr
import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_regime_state as regime
import crypto_core.validation.governed_paper_sizing_chain as sizing_module
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionError,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_allocation_envelope import (
    GovernedPaperAllocationEligibility,
    GovernedPaperEnvelopeFitStatus,
    derive_governed_paper_allocation_timeline,
)
from crypto_core.validation.governed_paper_ctr_qualification import (
    GovernedPaperCtrApprovalTable,
    GovernedPaperCtrDepthStatus,
    GovernedPaperCtrReading,
    GovernedPaperCtrRecordKind,
    GovernedPaperCtrRevocationKind,
    GovernedPaperCtrSourceContext,
    GovernedPaperDepthIndex,
    GovernedPaperVisibleDepth,
    build_governed_paper_ctr_qualification_revocation,
    build_governed_paper_ctr_source_capture,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetySizing,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_a9_multipliers,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_evidence_to_dict,
    governed_paper_entry_safety_rule_set,
)
from crypto_core.validation.governed_paper_execution_authority import build_governed_paper_cycle_authority
from crypto_core.validation.governed_paper_sizing_chain import (
    GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID,
    GOVERNED_PAPER_SIZING_RULE_DIGEST,
    GovernedPaperSizingContext,
    GovernedPaperSizingReading,
    governed_paper_sizing_evidence_digest,
    governed_paper_sizing_reading_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_SIZING_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionWindow,
    HistoricalExecutionDecisionExactValues,
    HistoricalExecutionDecisionPortfolioSnapshot,
    HistoricalExecutionDepthCap,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionExposureEnvelope,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionSide,
    historical_execution_admission_schedule_digest,
    historical_execution_admission_schedule_to_dict,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_ctr_qualification as ctrt
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_lineage as lineage
    import test_governed_paper_regime_state as rst
    import test_governed_paper_system_safety as sst
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_ctr_qualification as ctrt
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_system_safety as sst
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

SECOND = 1_000_000_000
UNIT = Fraction(1, 10**18)
S = GovernedPaperEntrySafetyStatus
BLOCKED = S.BLOCKED_ON_MISSING_INPUT
V5 = HISTORICAL_EXECUTION_SIZING_ADMISSION_SCHEDULE_SCHEMA_VERSION
V8, V9 = "governed-paper-day-seal.v8", "governed-paper-day-seal.v9"
EF = GovernedPaperEnvelopeFitStatus
DS = GovernedPaperCtrDepthStatus
FILLED, REJECTED = HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.REJECTED
BUY, SELL = HistoricalExecutionSide.BUY, HistoricalExecutionSide.SELL
NO_SOURCE = GovernedPaperSizingContext(ctr_source=None)
PRODUCTION_CHECKS = entry_safety._CHECKS  # noqa: SLF001 - captured at import, before any fixture could patch it
V8_TAIL = ("HZ-STOP", "HZ-LIMITS", "ENVELOPE-FIT", "SCALE-1", "CTR-DEPTH")

# The accepted-main identities of rule set v7 and of world G's integrated lineage (seal v8, evidence v8) under the
# TEST-ONLY regime table, pinned on main 5f88effa before this contract.
ACCEPTED_MAIN_RULE_SET_V7_DIGEST = "f6212320b466ac6eea27c387e0e267546f793c243f9e7be99f5492b92b8be4ec"
ACCEPTED_MAIN_V8_SEALS = (
    "24e325431858275ed26c49e23041a022b2c871ee5a3836b22ce7938f2f1c220b",
    "20a2f1042382d1476448bb12418bccaa88d10afdbd83170ecc03fabaa356e6d4",
    "6b8b3e9d8552e89ce7676e2fd2d1c199a3b41bec4c03c6b14e9afea5d1395d98",
    "e9ac97ff87fc7b20ce62044ac02569ff9ddfa73918240fbf8996224700e46a2e",
)
ACCEPTED_MAIN_V8_ENTRY_EVIDENCE = (
    "70ff629c17e6b05df28497865cd9231fb8e5118aeed226e80daf9306f560b395",
    "552235bdcfa0bb296c9925b87c39998229c0e5f46fbf2d5bce46716c5095b552",
    "344703a1cde1980c2b1d845b6678a68473a31acdb5512913fa6da3f756f5e184",
    "ddfadb313a15d799aa5cb695194af20439fb880b84a855004711a067507697f6",
)
ACCEPTED_MAIN_V8_LINEAGE_EVIDENCE = "27a61fdd5610a9387259930a0e7b4fe5a10273182e629d623ff2b958682ef9ed"


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
        assert regime._APPROVAL_TABLE is rst.PRODUCTION_TABLE  # noqa: SLF001
        assert ctr._APPROVAL_TABLE is ctr.GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE  # noqa: SLF001
        yield


# --- A. the engine's schedule v5 ----------------------------------------------------------------------------------------------

ONE_DAY_PATH = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6)  # SYNTHETIC: a SHORT entry and its deadline close


@functools.cache
def baseline():  # noqa: ANN201
    """The SYNTHETIC lifecycle world, its economics and its schedule v4 outcome (the reference fills)."""

    w, result = lifet.funded(ONE_DAY_PATH, lifet.LONG_RUN)
    schedule = lifet.both_sides(end=lifet.LONG_RUN)
    return w, result, schedule, lifet.governed_under(result, schedule)


def entries_of(outcome: object) -> list:
    """The executed fills that increase the magnitude of the position (OPEN or INCREASE transitions)."""

    increasing = {
        item.fill_digest
        for item in outcome.position_transitions  # type: ignore[attr-defined]
        if abs(Fraction(item.post_quantity)) > abs(Fraction(item.prior_quantity))
    }
    return [item for item in outcome.fills if item.fill_digest in increasing]  # type: ignore[attr-defined]


def v5_of(schedule: object, envelopes: tuple = (), caps: tuple = ()):  # noqa: ANN201
    return replace(schedule, schema_version=V5, exposure_envelopes=envelopes, depth_caps=caps)  # type: ignore[type-var]


def whole_run(fraction: object) -> tuple:
    return (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.LONG_RUN, str(Fraction(fraction))),)  # type: ignore[arg-type]


def caps_for(fills: list, side: HistoricalExecutionSide = SELL, extra: object = UNIT) -> tuple:
    return tuple(
        sorted(
            (
                HistoricalExecutionDepthCap(
                    item.book_record_digest, side, str(Fraction(item.requested_quantity) + extra)
                )  # type: ignore[arg-type]
                for item in fills
            ),
            key=lambda cap: (cap.book_record_digest, cap.side.value),
        )
    )


def test_schedule_v5_bounds_are_exact_rationals_only_on_schedule_v5_and_never_in_a_legacy_payload() -> None:
    _, _, schedule, _ = baseline()
    assert set(historical_execution_admission_schedule_to_dict(schedule)) == {
        "schema_version",
        "schedule_id",
        "windows",
        "invalidated_from_ns",
        "entry_refused_decision_sequences",
        "protective_windows",
    }  # a schedule v4 payload is exactly its accepted one
    v5 = v5_of(schedule, whole_run("1/4"), caps_for(entries_of(baseline()[3])))
    payload = historical_execution_admission_schedule_to_dict(v5)
    assert payload["exposure_envelopes"][0]["max_exposure_fraction"] == "1/4"  # type: ignore[index]
    assert historical_execution_admission_schedule_digest(v5) != historical_execution_admission_schedule_digest(
        schedule
    )
    invalid = (
        replace(schedule, exposure_envelopes=whole_run("1/4")),  # a v4 schedule never carries a bound
        v5_of(schedule, (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.LONG_RUN, "2/4"),)),  # not canonical
        v5_of(schedule, (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.LONG_RUN, "0.25"),)),  # a decimal
        v5_of(schedule, (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.LONG_RUN, "3/2"),)),  # above 1
        v5_of(schedule, (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, lifet.LONG_RUN, "-1/4"),)),
        v5_of(schedule, (*whole_run("1/4"), *whole_run("1/4"))),  # overlapping
        v5_of(schedule, (), (HistoricalExecutionDepthCap("x", SELL, "1"),)),
        v5_of(schedule, (), (HistoricalExecutionDepthCap("a" * 64, SELL, "1"),) * 2),  # not unique
        v5_of(
            schedule,
            (),
            (HistoricalExecutionDepthCap("b" * 64, SELL, "1"), HistoricalExecutionDepthCap("a" * 64, SELL, "1")),
        ),
        v5_of(schedule, (), (HistoricalExecutionDepthCap("a" * 64, "SELL", "1"),)),
    )
    for item in invalid:
        with pytest.raises(HistoricalExecutionEconomicsError):
            historical_execution_admission_schedule_digest(item)  # type: ignore[arg-type]


def test_without_proven_bounds_every_entry_fill_is_refused_whole_and_a_close_never_reads_them() -> None:
    _, result, schedule, reference = baseline()
    entries = entries_of(reference)
    assert entries and all(item.outcome is FILLED for item in entries)
    refused = lifet.governed_under(result, v5_of(schedule))
    assert not entries_of(refused)
    rejected = [item for item in refused.fills if item.outcome is REJECTED]
    assert rejected and {item.reason for item in rejected} == {"governed_paper_exposure_envelope_unproven_at_fill"}
    assert not refused.position_transitions and not refused.fee_cashflows  # no state change at all
    # an envelope alone: the missing depth cap refuses; a cap of the other side or book is no cap
    for caps in ((), caps_for(entries, BUY), (HistoricalExecutionDepthCap("c" * 64, SELL, "100"),)):
        outcome = lifet.governed_under(result, v5_of(schedule, whole_run(1), caps))
        assert {item.reason for item in outcome.fills if item.outcome is REJECTED} == {
            "governed_paper_depth_cap_unproven_at_fill"
        }
    # proven bounds that admit every entry reproduce schedule v4's fills exactly, closes included
    admitted = lifet.governed_under(result, v5_of(schedule, whole_run(1), caps_for(entries)))
    for name in (
        "intent_ledger_digest",
        "fill_ledger_digest",
        "position_transition_ledger_digest",
        "fee_ledger_digest",
        "funding_ledger_digest",
        "valuation_ledger_digest",
        "trade_ledger_digest",
        "obligation_ledger_digest",
        "attempt_ledger_digest",
    ):
        assert getattr(admitted, name) == getattr(reference, name), name
    assert admitted.outcome_digest != reference.outcome_digest  # it binds its own schedule


def test_the_envelope_admits_its_exact_fraction_and_the_cap_refuses_its_exact_quantity() -> None:
    w, result, schedule, reference = baseline()
    first = entries_of(reference)[0]
    notional, equity, _ = lifet.candidate_equities(w, reference, first, 10_000)
    fraction = notional / equity  # the publication-visible candidate equity the NT-R04 fill bound reads
    caps = caps_for(entries_of(reference))
    at = lifet.governed_under(result, v5_of(schedule, whole_run(fraction), caps))
    assert [item.fill_digest for item in entries_of(at)][:1] == [first.fill_digest]  # equality admits
    below = lifet.governed_under(result, v5_of(schedule, whole_run(fraction - Fraction(1, 10**30)), caps))
    first_reason = next(item.reason for item in below.fills if item.intent_id == first.intent_id)
    assert first_reason == "governed_paper_exposure_envelope_exceeded_at_fill"
    exact_cap = tuple(
        replace(cap, max_order_quantity=str(Fraction(first.requested_quantity)))
        if cap.book_record_digest == first.book_record_digest
        else cap
        for cap in caps
    )
    capped = lifet.governed_under(result, v5_of(schedule, whole_run(1), exact_cap))
    assert next(item.reason for item in capped.fills if item.intent_id == first.intent_id) == (
        "governed_paper_depth_cap_exceeded_at_fill"
    )  # an order must stay strictly below its cap
    outside = (HistoricalExecutionExposureEnvelope(lifet.ANCHOR, first.execution_time_ns, "1"),)
    late = lifet.governed_under(result, v5_of(schedule, outside, caps))
    assert next(item.reason for item in late.fills if item.intent_id == first.intent_id) == (
        "governed_paper_exposure_envelope_unproven_at_fill"
    )  # the window ends at the fill instant: the fill lies outside it


def test_schedule_v5_is_an_information_time_schedule_with_a_decision_portfolio() -> None:
    _, result, schedule, _ = baseline()
    v4_portfolio = lifet.portfolio_of(result, schedule)
    v5_portfolio = lifet.portfolio_of(result, v5_of(schedule))
    first = v5_portfolio.snapshots[0]
    assert (first.position_quantity, first.nav) == (
        v4_portfolio.snapshots[0].position_quantity,
        v4_portfolio.snapshots[0].nav,
    )


# --- B. rule set v8 in the gate -----------------------------------------------------------------------------------------------


def reading(**changes: object) -> GovernedPaperSizingReading:
    """A SYNTHETIC sizing reading of ``est``'s decision 7 (SHORT at ``est.T``), digest-bound."""

    values: dict[str, object] = {
        "decision_sequence": 7,
        "decision_time_ns": est.T,
        "target_direction": "SHORT",
        "order_side": SELL,
        "order_quantity": "20",
        "reservation_price": "40",
        "position_quantity": "0",
        "mark_price": "40",
        "usage": "800",
        "usage_exact": True,
        "nav": "10000",
        "allocation_rebalance_ns": None,
        "eligibility": GovernedPaperAllocationEligibility.UNKNOWN,
        "weight": None,
        "allocation_reason": "no_rebalance_at_or_before_the_instant",
        "envelope_status": EF.BLOCKED,
        "envelope_observed": "0.080000000000000000",
        "envelope_reason": "eligibility_unknown_and_usage_within_0_40_of_nav",
        "ctr": GovernedPaperCtrReading(est.T, False, "no_ctr_source_supplied", None, None, None, None),
        "depth": GovernedPaperVisibleDepth(SELL, None, None, False, "order_book_tip_older_than_10s"),
        "depth_status": DS.BLOCKED,
        "depth_observed": "",
        "depth_reason": "visible_depth_unavailable:order_book_tip_older_than_10s",
        "reading_digest": "",
    }
    values.update(changes)
    seed = GovernedPaperSizingReading(**values)  # type: ignore[arg-type]
    return replace(seed, reading_digest=governed_paper_sizing_reading_digest(seed))


SIZING_EVIDENCE = "9" * 64  # SYNTHETIC sizing evidence digest of the gate observations


def v8(sized: GovernedPaperSizingReading | None = None, **observation: object):  # noqa: ANN201
    return sst.v7(
        sizing=GovernedPaperEntrySafetySizing(reading() if sized is None else sized, SIZING_EVIDENCE), **observation
    )


def outcome(decision: object, name: str) -> tuple:
    check = est.check_of(decision, name)
    return check.status, check.observed, check.reason


A9_UNPROVEN = (
    "a9_prime_unproven_envelope_fit_edge_health_alpha_1_6_de_weight_1_7_combined_drawdown_reduction_1_7_kill_switch_9_2_"
    "system_state_1_29_crowding_1_11_capacity_tier_1_15_regime_dimensions_and_leverage_1_17_0_2_calibration_1_24_"
    "margin_and_dtl_1_26_kelly_fit_1_28"
)


def test_rule_set_v8_adds_only_its_rule_and_checks_and_v1_to_v7_keep_their_identities() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_MARKET_DATA_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_KILL_SWITCH_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET_DIGEST,
        GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST,
    ) == (
        est.ACCEPTED_MAIN_RULE_SET_V1_DIGEST,
        est.ACCEPTED_MAIN_RULE_SET_V2_DIGEST,
        est.RULE_SET_V3_DIGEST,
        est.RULE_SET_V4_DIGEST,
        rst.ACCEPTED_MAIN_RULE_SET_V5_DIGEST,
        sst.ACCEPTED_MAIN_RULE_SET_V6_DIGEST,
        ACCEPTED_MAIN_RULE_SET_V7_DIGEST,
    )
    v8_rules, v6_rules = GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_REGIME_RULE_SET
    v7_rules = GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET
    added = ("rule_set_id", "contract_id", "checks", "sizing_chain_rule")
    assert {key: value for key, value in v8_rules.items() if key not in added} == {
        key: value for key, value in v7_rules.items() if key not in added
    }
    assert v8_rules["checks"][: len(v6_rules["checks"])] == v6_rules["checks"]  # type: ignore[index, arg-type]
    tail = v8_rules["checks"][len(v6_rules["checks"]) :]  # type: ignore[index]
    assert [item["check_id"] for item in tail] == list(V8_TAIL)  # type: ignore[index]
    assert tail[:2] == v7_rules["checks"][len(v6_rules["checks"]) : len(v6_rules["checks"]) + 2]  # type: ignore[index]
    assert (v8_rules["rule_set_id"], v8_rules["contract_id"]) == (
        GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_ID,
        GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID,
    )
    rule = v8_rules["sizing_chain_rule"]
    assert rule["sizing_rule_digest"] == GOVERNED_PAPER_SIZING_RULE_DIGEST  # type: ignore[index]
    assert rule["approved_items"] == ["D9", "D15", "2.1", "2.2", "2.3", "3.1", "3.2", "FCD-07"]  # type: ignore[index]
    with pytest.raises(GovernedPaperEntrySafetyError, match="sizing_chain_rule_set_needs_the_system_safety_rule_set$"):
        governed_paper_entry_safety_rule_set(
            protective=True, portfolio=True, market_data=True, kill_switch=True, regime=True, sizing_chain=True
        )
    assert GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST not in (
        ACCEPTED_MAIN_RULE_SET_V7_DIGEST,
        sst.ACCEPTED_MAIN_RULE_SET_V6_DIGEST,
    )


def test_the_v8_checks_read_the_decisions_own_sizing_reading_and_the_first_refusal_never_moves() -> None:
    legacy, current = sst.decided(), evaluate_governed_paper_entry_safety(v8())
    assert (len(legacy.checks), len(current.checks)) == (39, 41)
    assert [item.check_id for item in current.checks][-5:] == list(V8_TAIL)
    assert [item for item in current.checks if item.check_id not in ("ENVELOPE-FIT", "SCALE-1", "CTR-DEPTH")] == [
        item for item in legacy.checks if item.check_id != "SCALE-1"
    ]
    digest = reading().reading_digest
    assert outcome(current, "ENVELOPE-FIT") == (
        BLOCKED,
        "0.080000000000000000",
        est.code("ENVELOPE-FIT:eligibility_unknown_and_usage_within_0_40_of_nav"),
    )
    assert outcome(current, "CTR-DEPTH") == (
        BLOCKED,
        "",
        est.code("CTR-DEPTH:visible_depth_unavailable:order_book_tip_older_than_10s"),
    )
    assert est.check_of(current, "ENVELOPE-FIT").evidence_record_digests == (digest,)
    assert est.check_of(current, "CTR-DEPTH").evidence_record_digests == (digest,)
    for status, mapped in ((EF.PASS, S.PASS), (EF.FAIL, S.FAIL), (EF.BLOCKED, BLOCKED)):
        decided = evaluate_governed_paper_entry_safety(v8(reading(envelope_status=status)))
        assert est.check_of(decided, "ENVELOPE-FIT").status is mapped
    for status, mapped in ((DS.PASS, S.PASS), (DS.FAIL, S.FAIL), (DS.BLOCKED, BLOCKED)):
        decided = evaluate_governed_paper_entry_safety(v8(reading(depth_status=status)))
        assert est.check_of(decided, "CTR-DEPTH").status is mapped
    # no admission change: the first refusal is still NT-R01, and no v8 check ever passes the whole gate
    cases = (
        v8(),
        v8(reading(envelope_status=EF.PASS, depth_status=DS.PASS)),
        v8(kill_switch=kst.ks(1)),
        v8(latency_ns=500 * sst.MS),
    )
    for observation in cases:
        new = evaluate_governed_paper_entry_safety(observation)
        old = evaluate_governed_paper_entry_safety(replace(observation, sizing=None))
        assert (new.entry_permitted, new.first_failure_check_id, new.first_failure_reason) == (
            old.entry_permitted,
            old.first_failure_check_id,
            old.first_failure_reason,
        )
        assert new.entry_permitted is False
    other = evaluate_governed_paper_entry_safety(v8(family_b_applicable=False))
    assert outcome(other, "ENVELOPE-FIT")[2] == est.code("ENVELOPE-FIT:family_b_applicability_undetermined")


def test_scale_1_under_a9_keeps_every_v7_fail_names_its_inventory_and_never_passes() -> None:
    base = evaluate_governed_paper_entry_safety(v8())
    assert outcome(base, "SCALE-1") == (BLOCKED, "ENVELOPE_FIT=BLOCKED", est.code(f"SCALE-1:{A9_UNPROVEN}"))
    # every rule set v7 FAIL dominates with its accepted reason and observed value
    for changes in ({"kill_switch": kst.ks(1)}, {"latency_ns": 200 * sst.MS + 1}):
        assert outcome(evaluate_governed_paper_entry_safety(v8(**changes)), "SCALE-1") == outcome(
            sst.decided(**changes), "SCALE-1"
        )
    lost = sst.lost_data(sizing=GovernedPaperEntrySafetySizing(reading(), SIZING_EVIDENCE))
    assert outcome(evaluate_governed_paper_entry_safety(lost), "SCALE-1") == (
        S.FAIL,
        "SS-3",
        est.code("SCALE-1:system_state_at_least_ss-3_reduces_the_allocation"),
    )
    failed = evaluate_governed_paper_entry_safety(
        v8(reading(envelope_status=EF.FAIL, envelope_reason="usage_above_0_40_of_nav_for_any_eligibility"))
    )
    assert outcome(failed, "SCALE-1") == (
        S.FAIL,
        "ENVELOPE_FIT=FAIL",
        est.code("SCALE-1:envelope_fit_fail_under_a9_prime:usage_above_0_40_of_nav_for_any_eligibility"),
    )
    # an ENVELOPE_FIT PASS never passes SCALE-1: the other multipliers and the Kelly fit stay unproven
    passed = evaluate_governed_paper_entry_safety(v8(reading(envelope_status=EF.PASS)))
    assert outcome(passed, "SCALE-1") == (
        BLOCKED,
        "ENVELOPE_FIT=PASS",
        est.code(f"SCALE-1:{A9_UNPROVEN.replace('envelope_fit_', '', 1)}"),
    )
    terms = governed_paper_entry_safety_a9_multipliers(v8())
    assert [name for name, _, _ in terms] == list(
        GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET["sizing_chain_rule"]["SCALE-1_terms"]
    )  # type: ignore[index]
    statuses = {name: status for name, status, _ in terms}
    assert {name for name, status in statuses.items() if status == "PROVEN_ONE"} == {
        "correlation_halving_1_7",
        "latency_1_16",
    }  # the single-sleeve portfolio and a latency within twice the budget: nothing else is ever proven 1
    assert statuses["kelly_fit_1_28"] == statuses["calibration_1_24"] == "UNPROVEN"
    multi = dict(
        (name, status)
        for name, status, _ in governed_paper_entry_safety_a9_multipliers(v8(single_instrument_portfolio=False))
    )
    assert multi["correlation_halving_1_7"] == "UNPROVEN"


@pytest.mark.parametrize(
    ("build", "name"),
    [
        (
            lambda: est.measured(
                kill_switch=kst.ks(),
                regime=rst.regime_facts(),
                sizing=GovernedPaperEntrySafetySizing(reading(), SIZING_EVIDENCE),
            ),
            "sizing_without_the_system_safety_facts",
        ),
        (lambda: v8(reading(decision_sequence=8)), "sizing_reading"),
        (lambda: v8(replace(reading(), envelope_reason="")), "sizing_reading"),
        (lambda: v8(replace(reading(), usage="900")), "sizing_reading_digest"),
        (lambda: sst.v7(sizing=GovernedPaperEntrySafetySizing(reading(), "x")), "sizing_evidence_digest"),
        (lambda: sst.v7(sizing=(reading(), SIZING_EVIDENCE)), "sizing"),
    ],
)
def test_malformed_sizing_facts_are_refused(build: object, name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{est.code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(build())  # type: ignore[operator]


# --- C. the decision reading ----------------------------------------------------------------------------------------------------


def snapshot(position: str, candidate: str, mark: str | None, nav: str | None):  # noqa: ANN201
    return HistoricalExecutionDecisionPortfolioSnapshot(
        decision_sequence=1,
        decision_time_ns=ctrt.T,
        decision_digest="5" * 64,
        position_quantity=position,
        order_in_flight=False,
        mark_record_digest=None if mark is None else "6" * 64,
        mark_price=mark,
        nav=nav,
        nav_reason="" if nav is not None else "no_fresh_visible_mark",
        day_start_ns=ctrt.T - ctrt.T % (86_400 * SECOND),
        day_start_nav=None,
        day_start_reason="partial_first_utc_day",
        unpublished_settlement_count=0,
        candidate_position_quantity=candidate,
        candidate_nav=None,
        candidate_nav_reason="",
        snapshot_digest="7" * 64,
    )


def derived_reading(snap: object, exact_nav: Fraction | None, *, windowed: bool = True):  # noqa: ANN201
    schedule = v5_of(lifet.both_sides(end=lifet.LONG_RUN))
    if windowed:
        schedule = replace(
            schedule,
            windows=(HistoricalExecutionAdmissionWindow(ctrt.T - SECOND, ctrt.T + SECOND, "100", "100", "41.5"),),
        )
    timeline = derive_governed_paper_allocation_timeline(
        genesis_digest="a" * 64, candidate_edge_ids=("s1",), start_ns=ctrt.T - 10 * SECOND, horizon_ns=ctrt.T + SECOND
    )
    depth = GovernedPaperDepthIndex(
        rst.book_dataset([ctrt.tight(ctrt.T - SECOND, ctrt.T - SECOND)]), instrument=ctrt.INS
    )
    return sizing_module._reading(  # noqa: SLF001
        sequence=1,
        instant=ctrt.T,
        direction="SHORT",
        snapshot=snap,
        exact=None if snap is None else HistoricalExecutionDecisionExactValues(1, exact_nav, None),
        schedule=schedule,
        timeline=timeline,
        sleeve="s1",
        depth=depth,
        context=NO_SOURCE,
        instrument=ctrt.INS,
    )


def test_the_usage_reads_the_order_quantity_and_reservation_price_and_b_is_the_exact_nav() -> None:
    exact_nav = Fraction(99_999) + Fraction(1, 3)  # an exact NAV no scale-18 rendering equals
    flat = derived_reading(
        snapshot("0.000000000000000000", "-2.000000000000000000", "40.000000000000000000", "99999.333333333333333333"),
        exact_nav,
    )
    assert (flat.order_quantity, flat.reservation_price, flat.usage, flat.usage_exact) == ("2", "83/2", "83", True)
    assert flat.nav == str(exact_nav) != "99999.333333333333333333"  # the exact value, never the rendering
    assert (flat.eligibility, flat.allocation_reason) == (
        GovernedPaperAllocationEligibility.UNKNOWN,
        "no_rebalance_at_or_before_the_instant",
    )
    assert (flat.envelope_status, flat.envelope_reason) == (
        EF.BLOCKED,
        "eligibility_unknown_and_usage_within_0_40_of_nav",
    )
    assert flat.order_side is SELL and flat.depth.depth == "4100" and flat.depth_status is DS.BLOCKED
    assert flat.depth_reason == "ctr_unavailable:no_ctr_source_supplied"  # 2 is below 2% of 4100 (82): no FAIL
    held = derived_reading(
        snapshot("-1.000000000000000000", "-3.000000000000000000", "40.000000000000000000", "1.000000000000000000"),
        Fraction(1),
    )
    assert (held.usage, held.usage_exact) == (str(2 * Fraction(83, 2) + 40), True)  # |q_pre| x mark + u x L_k
    assert held.envelope_status is EF.FAIL  # 123 is above 40% of a NAV of 1, whatever the eligibility
    unmarked = derived_reading(snapshot("-1.000000000000000000", "-3.000000000000000000", None, None), None)
    assert (unmarked.usage, unmarked.usage_exact, unmarked.nav) == ("83", False, None)  # a lower bound, never exact
    assert unmarked.envelope_reason == "publication_visible_nav_unavailable"
    nowindow = derived_reading(
        snapshot("0.000000000000000000", "-2.000000000000000000", "40.000000000000000000", "10.000000000000000000"),
        Fraction(10),
        windowed=False,
    )
    assert (nowindow.reservation_price, nowindow.usage, nowindow.envelope_reason) == (None, None, "usage_unavailable")
    missing = derived_reading(None, None)
    assert (missing.order_quantity, missing.usage, missing.depth_reason) == (None, None, "order_quantity_unavailable")


def test_e0_and_r_are_re_proven_equal_and_never_the_envelope_base() -> None:
    authority = est.run_and_evidence(sizing_days(1)[0])[0]
    origin, reference = sizing_module._capital_quantities(authority)  # noqa: SLF001
    assert origin == reference == Fraction(authority.economics_policy.initial_equity)
    basis = authority.equity_basis_policy
    forged = replace(
        authority, equity_basis_policy=replace(basis, paper_performance_reference_notional=gpe.d(origin + 1))
    )
    with pytest.raises(
        sizing_module.GovernedPaperSizingError, match="reference_notional_r_is_not_the_equity_origin_e0$"
    ):
        sizing_module._capital_quantities(forged)  # noqa: SLF001


# --- D. world G's sizing chain lineage (seal v9, evidence v9) ---------------------------------------------------------------------


def sizing_inputs(days: tuple, context: object, sizing: object = NO_SOURCE):  # noqa: ANN201
    """The cycle and seal inputs of the day after ``days`` of world G on the sizing chain lineage."""

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
        system_safety=True,
        sizing=sizing,
    )
    seal_inputs = gpe.seal_inputs_for(
        day, cycle_inputs, cycle, prior, gpe.pending_of(days), world=world, protection=protection
    )
    return cycle_inputs, cycle, seal_inputs


def sizing_day(days: tuple, context: object, sizing: object = NO_SOURCE):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of world G on the sizing chain lineage with the regime ``context``."""

    cycle_inputs, cycle, seal_inputs = sizing_inputs(days, context, sizing)
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def sizing_days(count: int) -> tuple:
    """World G's first ``count`` days of the sizing chain lineage (seal v9) without a CTR source."""

    if count == 0:
        return ()
    days = sizing_days(count - 1)
    return (*days, sizing_day(days, rst.regime_context(len(days))))


def public_gate(item: object, day: int, sizing: GovernedPaperSizingContext):  # noqa: ANN201
    """Day ``day``'s decision run and rule set v8 evaluation of ``item``, rebuilt independently through the public
    builders with the sizing context ``sizing``."""

    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        evidence = build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),  # type: ignore[attr-defined]
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
            sizing=sizing,
        )
    return run, evidence


@functools.cache
def sizing_gate(day: int):  # noqa: ANN201
    """Day ``day``'s rule set v8 evaluation of the source-free lineage, rebuilt through the public builders."""

    return public_gate(sizing_days(day + 1)[day], day, NO_SOURCE)


UNCHANGED = (
    "economics_result_digest",
    "episodes",
    "funding_events",
    "sealed_history_digest",
    "prefix_digest_open",
    "prefix_digest_close",
    "kill_switch_prefix_digest_open",
    "kill_switch_prefix_digest_close",
    "system_state_evidence_digest",
    *rst.V7_FIELDS,
)


def test_world_g_sizing_lineage_changes_only_its_version_schedule_rule_set_and_bound_sizing_evidence() -> None:
    days, legacy = sizing_days(4), sst.safety_days(4)
    for item, old in zip(days, legacy, strict=True):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V9, GovernedPaperDaySealStatus.SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST
        for name in UNCHANGED:
            assert getattr(seal, name) == getattr(old.seal, name), name
        schedule = seal.schedule
        assert (schedule.schema_version, schedule.exposure_envelopes, schedule.depth_caps) == (V5, (), ())
        assert schedule.entry_refused_decision_sequences == old.seal.schedule.entry_refused_decision_sequences
        assert (seal.ctr_qualification_digest, seal.ctr_revocation_digests, seal.ctr_capture_digest) == ("", (), "")
        assert len(seal.sizing_evidence_digest) == 64
        verification = rst.verify(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    (entry,) = days[3].seal.entry_safety_decisions
    (old_entry,) = legacy[3].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # no new admission

    def summary(decision: object, skip: tuple[str, ...]) -> list[tuple]:
        return [
            (item.check_id, item.status, item.observed, item.threshold, item.reason)
            for item in decision.checks  # type: ignore[attr-defined]
            if item.check_id not in skip
        ]

    assert summary(entry, ("ENVELOPE-FIT", "SCALE-1", "CTR-DEPTH")) == summary(old_entry, ("SCALE-1",))
    # only the ladder's own digest moves (it binds the schedule v5 under evaluation): NT-R01 and NT-T02 cite it
    moved = {
        item.check_id
        for item, old in zip(
            [c for c in entry.checks if c.check_id not in ("ENVELOPE-FIT", "CTR-DEPTH")], old_entry.checks, strict=True
        )
        if item.evidence_record_digests != old.evidence_record_digests
    }
    assert moved <= {"NT-R01", "NT-T02", "SCALE-1"}
    statuses = {check.check_id: (check.status, check.reason) for check in entry.checks}
    assert statuses["SCALE-1"] == (BLOCKED, est.code(f"SCALE-1:{A9_UNPROVEN}"))
    assert statuses["ENVELOPE-FIT"][0] is BLOCKED and statuses["CTR-DEPTH"][0] is BLOCKED
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        evidence = build_governed_paper_execution_evidence(gpe.evidence_inputs(days))
    assert (evidence.schema_version, evidence.status) == (
        "governed-paper-execution-evidence.v9",
        GovernedPaperExecutionStatus.READY,
    )
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())
    payload = governed_paper_day_seal_to_dict(days[3].seal)
    assert {"sizing_evidence_digest", "ctr_qualification_digest", "ctr_capture_record_count"} <= set(payload)


def test_the_public_gate_replays_every_sealed_sizing_reading_and_no_later_seal_revises_one() -> None:
    days = sizing_days(5)
    readings: list[dict[int, object]] = []
    for day in (3, 4):  # two UTC days of the lineage: day 4's evaluation re-derives day 3's entry
        item = days[day]
        run, evidence = sizing_gate(day)
        assert (evidence.rule_set_id, evidence.evidence_digest) == (
            GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_ID,
            item.seal.entry_safety_evidence_digest,
        )
        sized = evidence.sizing_evidence
        assert sized is not None and sized.evidence_digest == item.seal.sizing_evidence_digest
        assert sized.evidence_digest == governed_paper_sizing_evidence_digest(sized)
        assert {reading_.decision_sequence for reading_ in sized.readings} == set(
            governed_paper_entry_safety_entry_sequences(run)
        )  # entries only
        assert (sized.exposure_envelopes, sized.depth_caps, sized.ctr_admission_reason) == (
            (),
            (),
            "no_ctr_source_supplied",
        )
        assert (sized.synthetic_ctr_qualification_used, sized.capital_allocated, sized.production_use_authorized) == (
            False,
            False,
            False,
        )
        timeline = sized.allocation_timeline
        assert all(item_.result.status.value == "BLOCKED" for item_ in timeline.rebalances)
        for decision in evidence.decisions:
            derived = next(r for r in sized.readings if r.decision_sequence == decision.decision_sequence)
            assert est.check_of(decision, "ENVELOPE-FIT").evidence_record_digests == (derived.reading_digest,)
            assert derived.eligibility is GovernedPaperAllocationEligibility.UNKNOWN
            assert derived.ctr.reason == "no_ctr_source_supplied" and derived.depth_status is DS.BLOCKED
        readings.append({reading_.decision_sequence: reading_ for reading_ in sized.readings})
    earlier, later = readings
    assert earlier and all(later[sequence] == item for sequence, item in earlier.items())


def test_a_sizing_lineage_is_one_from_day_0_or_never_and_only_on_an_integrated_lineage() -> None:
    days, legacy = sizing_days(2), sst.safety_days(2)
    for item, changes, reason in (
        (days[1], {"sizing": None}, "sizing_chain_lineage_switched"),
        (legacy[1], {"sizing": NO_SOURCE}, "sizing_chain_lineage_switched"),
        (days[0], {"system_safety": False}, "sizing_chain_needs_the_system_safety_lineage"),
        (days[1], {"sizing": object()}, "protection_inputs_malformed:sizing"),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    assert rst.verify(replace(days[1].seal, schema_version=V8), days[1].seal_inputs).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:sizing_evidence_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V8)
    for forged in (replace(legacy[1].seal, schema_version=V9), gpe.reseal_seal(legacy[1].seal, schema_version=V9)):
        assert rst.verify(forged, legacy[1].seal_inputs).intact is False
    for changes in ({"sizing_evidence_digest": "0" * 64}, {"ctr_capture_record_count": 1}):
        assert rst.verify(gpe.reseal_seal(days[1].seal, **changes), days[1].seal_inputs).intact is False


def test_a_legacy_entry_safety_evidence_never_carries_a_sizing_evidence() -> None:
    legacy = sst.public_gate(3)[1]  # rule set v7, rebuilt through the public builders
    assert "sizing_evidence" not in governed_paper_entry_safety_evidence_to_dict(legacy)
    stray = sizing_gate(3)[1].sizing_evidence
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_sizing_evidence$"):
        governed_paper_entry_safety_evidence_to_dict(replace(legacy, sizing_evidence=stray))
    item = sizing_days(4)[3]
    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    for schedule, sized, reason in (
        (item.seal.schedule, None, "sizing_schedule_and_rule_set_mismatch"),
        (sst.safety_days(4)[3].seal.schedule, NO_SOURCE, "sizing_schedule_and_rule_set_mismatch"),
        (
            replace(item.seal.schedule, exposure_envelopes=(HistoricalExecutionExposureEnvelope(0, 1, "1"),)),
            NO_SOURCE,
            "sizing_evidence_not_derivable",
        ),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            build_governed_paper_entry_safety_evidence(
                authority=authority,
                run=run,
                dataset=item.seal_inputs.dataset,
                invalidated_from_ns=None,
                protection=est.seal_protection(item),
                portfolio=GovernedPaperEntrySafetyPortfolio(economics, schedule),
                market_data=True,
                kill_switch=True,
                regime=rst.regime_context(3),
                system_safety=True,
                sizing=sized,
            )


# --- the CTR source lineage under the TEST-ONLY qualification table ---------------------------------------------------------------

CTR_TABLE = GovernedPaperCtrApprovalTable("test_only", ctr.GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC, ())
DAY_NS = 86_400 * SECOND


def day_end(day: int) -> int:
    return gpe.G + (day + 1) * DAY_NS


@functools.cache
def entry_instants() -> tuple[int, ...]:
    _, run, _ = est.run_and_evidence(sizing_days(4)[3])
    return tuple(item.decision_time_ns for item in run.decisions if item.resulting_direction in ("LONG", "SHORT"))


@functools.cache
def source_records() -> tuple:
    """SYNTHETIC order-level records: one on each of days 0 and 1, then, for every entry decision of the first four days,
    an anchor 61 s before it, two cancels and a trade inside its 60-second window (contiguous sequence ids)."""

    rows: list = [
        ctrt.record(0, GovernedPaperCtrRecordKind.ORDER_ADD, gpe.G + 3_600 * SECOND),
        ctrt.record(1, GovernedPaperCtrRecordKind.ORDER_ADD, day_end(0) + 3_600 * SECOND),
    ]
    for instant in entry_instants():
        for offset, kind in (
            (61, GovernedPaperCtrRecordKind.ORDER_ADD),
            (30, GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL),
            (20, GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL),
            (10, GovernedPaperCtrRecordKind.TRADE),
        ):
            rows.append(ctrt.record(len(rows), kind, instant - offset * SECOND))
    return tuple(rows)


def source_for(  # noqa: PLR0913
    day: int, *, records: tuple | None = None, revocations: tuple = (), through: int | None = None, **changes: object
) -> GovernedPaperSizingContext:
    """The CTR source known at ``E_{day+1}``: the records received by then, complete through it."""

    end = day_end(day) if through is None else through
    q = ctrt.qualification(instrument=gpe.INS, **changes)
    rows = tuple(item for item in (source_records() if records is None else records) if item.receipt_time_ns <= end)
    capture = build_governed_paper_ctr_source_capture(
        capture_id="synthetic-capture-g", qualification=q, complete_through_receipt_ns=end, records=rows
    )
    return GovernedPaperSizingContext(GovernedPaperCtrSourceContext(q, revocations, capture))


@functools.cache
def source_days(count: int) -> tuple:
    """World G's first ``count`` days of the sizing chain lineage with the SYNTHETIC qualified source, built under the
    TEST-ONLY qualification table (and the TEST-ONLY regime table)."""

    if count == 0:
        return ()
    days = source_days(count - 1)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctr, "_APPROVAL_TABLE", CTR_TABLE)
        return (*days, sizing_day(days, rst.regime_context(len(days)), source_for(len(days))))


def lineage_evidence(days: tuple):  # noqa: ANN201
    """The lineage evidence of ``days`` under the TEST-ONLY qualification and regime tables they were sealed under."""

    with pytest.MonkeyPatch.context() as patch, rst.approval_table(rst.TEST_ONLY_TABLE):
        patch.setattr(ctr, "_APPROVAL_TABLE", CTR_TABLE)
        return build_governed_paper_execution_evidence(gpe.evidence_inputs(days))


def test_a_qualified_source_binds_its_lineage_reads_available_ctr_and_never_passes_the_depth_cap() -> None:
    days = source_days(2)
    q = ctrt.qualification(instrument=gpe.INS)
    for index, item in enumerate(days):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.ctr_qualification_digest, seal.ctr_revocation_digests) == (
            V9,
            GovernedPaperDaySealStatus.SEALED,
            q.qualification_digest,
            (),
        )
        assert seal.ctr_capture_record_count == sum(
            1 for row in source_records() if row.receipt_time_ns <= day_end(index)
        )
        assert seal.ctr_capture_digest == item.seal_inputs.protection.sizing.ctr_source.capture.capture_digest  # type: ignore[union-attr]
    assert lineage_evidence(days).status is GovernedPaperExecutionStatus.READY
    # at the day-3 entry of world G the qualified, covered TEST-ONLY reading is available, yet no depth is proven
    item = sizing_days(4)[3]
    (entry,) = item.seal.entry_safety_decisions
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctr, "_APPROVAL_TABLE", CTR_TABLE)
        _, gate = public_gate(item, 3, source_for(3))
    sized = gate.sizing_evidence
    assert sized is not None and (sized.ctr_admission_reason, sized.synthetic_ctr_qualification_used) == ("", True)
    assert (sized.real_source_qualified, sized.depth_caps, sized.exposure_envelopes) == (False, (), ())
    reading_ = {row.decision_sequence: row for row in sized.readings}[entry.decision_sequence]
    assert (reading_.ctr.available, reading_.ctr.cancel_count, reading_.ctr.trade_count, reading_.ctr.alpha) == (
        True,
        2,
        1,
        "1",
    )
    assert reading_.depth_status is DS.BLOCKED and reading_.depth_reason.startswith("visible_depth_unavailable:")
    decision = next(row for row in gate.decisions if row.decision_sequence == entry.decision_sequence)
    assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-D01")
    assert est.check_of(decision, "CTR-DEPTH").reason == est.code(f"CTR-DEPTH:{reading_.depth_reason}")
    # under the PRODUCTION qualification table the same source reads nothing: it is refused, never qualified
    _, production = public_gate(item, 3, source_for(3))
    refused = {row.decision_sequence: row for row in production.sizing_evidence.readings}  # type: ignore[union-attr]
    assert refused[entry.decision_sequence].ctr.reason == "synthetic_qualification_refused_on_the_production_table"


def test_a_ctr_source_is_fixed_for_the_lineage_its_revocations_append_only_and_its_capture_complete() -> None:
    day0 = source_days(1)
    digest = ctrt.qualification(instrument=gpe.INS).qualification_digest

    def revocation(effective: int):  # noqa: ANN202
        return build_governed_paper_ctr_qualification_revocation(
            revocation_id="synthetic-revocation-1",
            qualification_digest=digest,
            kind=GovernedPaperCtrRevocationKind.REVOKED,
            effective_from_ns=effective,
            approval_kind=ctr.GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC,
            approver_reference="synthetic-test-fixture",
        )

    inside = revocation(day_end(0) + SECOND)
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ctr, "_APPROVAL_TABLE", CTR_TABLE)
        revoked = sizing_day(day0, rst.regime_context(1), source_for(1, revocations=(inside,)))
        for sizing, reason in (
            (NO_SOURCE, "ctr_source_changed_inside_the_lineage"),
            (source_for(1, venue="another-venue"), "ctr_source_changed_inside_the_lineage"),
            (source_for(1, revocations=(revocation(day_end(0)),)), "ctr_revocation_outside_the_sealed_day"),
            (source_for(1, revocations=(revocation(day_end(1) + 1),)), "ctr_revocation_outside_the_sealed_day"),
            (source_for(1, through=day_end(1) - 1), "ctr_capture_not_complete_through_the_seal"),
        ):
            _, _, inputs = sizing_inputs(day0, rst.regime_context(1), sizing)
            with rst.approval_table(rst.TEST_ONLY_TABLE), gpe.refused(reason):
                build_governed_paper_day_seal(inputs)
        records = source_records()
        rewritten = (replace(records[0], publication_time_ns=records[0].publication_time_ns - 1), *records[1:])
        backfilled = (*records, ctrt.record(len(records), GovernedPaperCtrRecordKind.TRADE, day_end(0) - SECOND))
        forged = [
            (
                sizing_day(
                    day0,
                    rst.regime_context(1),
                    source_for(1, records=tuple(sorted(variant, key=lambda row: row.receipt_time_ns))),
                ),
                reason,
            )
            for variant, reason in (
                (rewritten, "ctr_capture_rewritten:1"),
                (backfilled, "ctr_capture_backfilled_before_the_day:1"),
            )
        ]
    assert revoked.seal.status is GovernedPaperDaySealStatus.SEALED
    assert revoked.seal.ctr_revocation_digests == (inside.revocation_digest,)
    assert lineage_evidence((*day0, revoked)).status is GovernedPaperExecutionStatus.READY
    # one seal alone cannot see the earlier capture; the lineage evidence refuses a rewrite or a backfill
    for item, reason in forged:
        assert item.seal.status is GovernedPaperDaySealStatus.SEALED
        with gpe.refused(reason):
            lineage_evidence((*day0, item))


# --- E. the fill-time refusal on the integrated path (permissive decision gate, TEST-ONLY) -------------------------------------


def test_with_the_decision_gate_forced_open_the_engine_refuses_every_entry_fill_as_unproven() -> None:
    with pytest.MonkeyPatch.context() as patch:
        # SYNTHETIC, TEST-ONLY: every production check keeps its id (rule set v7 reads the NT-D and NT-X ids) and passes
        permissive = tuple(replace(item, evaluate=gpe._test_only_permissive_check) for item in PRODUCTION_CHECKS)  # noqa: SLF001
        patch.setattr(entry_safety, "_CHECKS", permissive)
        patch.setattr(entry_safety, "_REGIME_CHECKS", ())
        patch.setattr(entry_safety, "_SIZING_CHAIN_CHECKS", ())
        days: tuple = ()
        for index in range(4):
            days = (*days, sizing_day(days, rst.regime_context(index)))
    admitted = [item for item in days for decision in item.seal.entry_safety_decisions if decision.entry_permitted]
    assert admitted, "the permissive decision gate admits at least one entry"
    for item in days:
        seal = item.seal
        assert seal.status is GovernedPaperDaySealStatus.SEALED
        assert seal.schedule.entry_refused_decision_sequences == ()  # nothing is refused at the decision
        assert (seal.schedule.exposure_envelopes, seal.schedule.depth_caps) == ((), ())
        assert not seal.episodes  # no entry fill ever executed: no position, no episode
    assert sum(item.seal.governance_rejected_fill_count for item in days) >= len(admitted)


# --- F. legacy byte identity -------------------------------------------------------------------------------------------------------


def test_world_g_integrated_lineage_is_byte_identical_to_accepted_main() -> None:
    days = sst.safety_days(4)
    assert GOVERNED_PAPER_ENTRY_SAFETY_SYSTEM_SAFETY_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V7_DIGEST
    assert tuple(item.seal.schema_version for item in days) == (V8,) * 4
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_V8_SEALS
    assert tuple(item.seal.entry_safety_evidence_digest for item in days) == ACCEPTED_MAIN_V8_ENTRY_EVIDENCE
    assert all(item.seal.sizing_evidence_digest == "" for item in days)
    assert all(item.seal.schedule.schema_version == "historical-execution-admission-schedule.v4" for item in days)
    assert "sizing_evidence_digest" not in governed_paper_day_seal_to_dict(days[3].seal)
    assert rst.regime_lineage_evidence(days).evidence_digest == ACCEPTED_MAIN_V8_LINEAGE_EVIDENCE


def test_a_sizing_context_is_derived_never_accepted() -> None:
    with pytest.raises(GovernedPaperExecutionError):
        build_governed_paper_day_seal(
            kst.switched(sizing_days(1)[0], sizing=GovernedPaperSizingContext(ctr_source=object()))
        )  # type: ignore[arg-type]
