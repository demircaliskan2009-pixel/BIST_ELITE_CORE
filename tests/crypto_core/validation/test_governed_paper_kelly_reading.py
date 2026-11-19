"""RECORD A Kelly reading tests (S1_KELLY_DEFINED_READING_CONSTRUCTION_V1): KD-1..KD-13 with the D-A1 fit, constructed.

SYNTHETIC TEST VALUES ONLY. Every trade, price, mark, rate, policy, approval and table here is a synthetic fixture that
exercises structure: no production threshold, venue truth, qualified source, real trade or human decision. RECORD A's own
constants (the windows 100 and 60, the EWMA weight 19/20, the quarter fraction below 100 trades, the 0.04 cap) and the
D-A1 fit ``rho_t * max(1, Lbar) <= f_cap`` are the human-approved methodology the code fixes, never values chosen here.

What is proven:
* the one exact arithmetic (``historical_execution_kelly_fit``): classes, zeros, the EWMA order, the 60/61 and 99/100
  window boundaries, f* <= 0, the undecided bootstrap, Lbar below, at and above 1, KD-9 equality and the smallest excess,
  the solvency domain on every known outcome from the first trade, a product of exactly 1, fewer than two trades, a huge
  exact product never rendered, unknown trades and an unproven rho or risk, with FAIL dominating BLOCKED;
* the engine (schedule v8): the fit at every exposure-increasing fill on the run's own closed trades, a whole refusal (no
  fee, no transition), LONG and SHORT, only exposure-increasing fills reach it, and a v7 derivation's exact trade inputs
  equal an independent R-5 oracle;
* the reading (``governed_paper_kelly_reading``): every trade re-proven against the sealed records (a tampered net, risk,
  knowledge, order, fill or dataset fails closed), the known/unknown split at a decision, unrepresentable values, digests
  and a run-independent X1 prefix;
* the gate (rule set v11): SCALE-1 reads the Kelly-fit term in place (PASS proves it, FAIL refuses as a proven reduction,
  BLOCKED leaves it unproven) and rule sets v1-v10 keep their identities;
* the lineage (seal v12, evidence v12) on world G: one from day 0 or never, only on a risk lineage, the X1 chain, the public
  gate replays it, the R-4 fraction is the exact value behind NT-R03, every entry stays refused, the PRODUCTION table blocks
  every reading, and the accepted-main seal v11, outcome v4 and rule set v10 identities are byte-identical.
"""

from __future__ import annotations

import functools
import math
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_ctr_qualification as ctr
import crypto_core.validation.governed_paper_regime_state as regime
import crypto_core.validation.governed_paper_risk_measurement as risk
import crypto_core.validation.historical_execution_economics as economics
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    governed_paper_day_seal_to_dict,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyKelly,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_a9_multipliers,
    governed_paper_entry_safety_evidence_to_dict,
    governed_paper_entry_safety_rule_set,
)
from crypto_core.validation.governed_paper_kelly_reading import (
    GOVERNED_PAPER_KELLY_COVERAGE,
    GOVERNED_PAPER_KELLY_DECISION_IDS,
    GOVERNED_PAPER_KELLY_PENDING_ITEMS,
    GOVERNED_PAPER_KELLY_RULE,
    GOVERNED_PAPER_KELLY_UNREPRESENTABLE,
    GovernedPaperKellyError,
    GovernedPaperKellyKnownTrade,
    GovernedPaperKellyStatus,
    build_governed_paper_kelly_reading,
    derive_governed_paper_kelly_evidence,
    governed_paper_kelly_evidence_digest,
    governed_paper_kelly_prefix_digest,
    governed_paper_kelly_reading_digest,
    governed_paper_kelly_trades,
)
from crypto_core.validation.governed_paper_risk_measurement import GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_KELLY_BLOCKS,
    HISTORICAL_EXECUTION_KELLY_FAILURES,
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionKellyStatus,
    HistoricalExecutionTradeStatus,
    canonical_historical_execution_admission_schedule,
    historical_execution_admission_schedule_to_dict,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_kelly_fit,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_derivation,
)
from crypto_core.validation.historical_execution_economics_policy import historical_execution_render_amount

try:  # the module objects pytest collects (basename import), so cached worlds are shared
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_ledger as plt
    import test_governed_paper_protective_lineage as lineage
    import test_governed_paper_regime_state as rst
    import test_governed_paper_risk_lineage as rlt
    import test_governed_paper_risk_measurement as rmt
    import test_governed_paper_sizing_chain as sct
    import test_governed_paper_system_safety as sst
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_ledger as plt
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_risk_lineage as rlt
    from tests.crypto_core.validation import test_governed_paper_risk_measurement as rmt
    from tests.crypto_core.validation import test_governed_paper_sizing_chain as sct
    from tests.crypto_core.validation import test_governed_paper_system_safety as sst
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

F = Fraction
PASS, FAIL, BLOCKED = (
    HistoricalExecutionKellyStatus.PASS,
    HistoricalExecutionKellyStatus.FAIL,
    HistoricalExecutionKellyStatus.BLOCKED,
)
S = GovernedPaperEntrySafetyStatus
V7 = HISTORICAL_EXECUTION_RISK_MEASUREMENT_ADMISSION_SCHEDULE_SCHEMA_VERSION
V8 = HISTORICAL_EXECUTION_KELLY_ADMISSION_SCHEDULE_SCHEMA_VERSION
V11_SEAL, V12_SEAL = "governed-paper-day-seal.v11", "governed-paper-day-seal.v12"
V12_EVIDENCE = "governed-paper-execution-evidence.v12"
V12_FIELDS = ("kelly_evidence_digest", "kelly_prefix_digest_open", "kelly_prefix_digest_close")
SEALED = GovernedPaperDaySealStatus.SEALED
PRODUCTION = GOVERNED_PAPER_RISK_PRODUCTION_APPROVAL_TABLE
NOT_ADMITTED = "risk_policy_not_admitted:synthetic_approval_refused_on_the_production_table"
# What a v12 day moves of the v11 day: the schedule v8 (the Kelly fit at the fill; with no trade possible the outcome is
# the v11 one exactly when no entry fill exists), the rule set v11 gate and its evidence, and the seal itself.
MOVED = (
    "schema_version",
    "prior_seal_digest",
    "schedule",
    "schedule_digest",
    "governed_outcome_digest",
    "entry_safety_rule_set_digest",
    "entry_safety_evidence_digest",
    "entry_safety_decisions",
    "seal_digest",
    "kill_switch_ladder_digest",
    "kill_switch_prefix_digest_open",
    "kill_switch_prefix_digest_close",
    "system_state_evidence_digest",
    "protective_ledger_evidence_digest",
    "risk_evidence_digest",
)
# The accepted-main identities this contract keeps, computed on main 6a04109e's source (the reference clone at 7ba50105,
# PR #442 being docs-only) before any change of this contract.
ACCEPTED_MAIN_RULE_SET_V10_DIGEST = "2f34e726fcf9672af18e7893466067ca0ca8f8825bf789104b07e20c0f349096"
ACCEPTED_MAIN_HOLD_V7_OUTCOME_DIGEST = "a0151d9edae070c783430062d40ecce28164afe3b616fcd464cae3e1c95531e7"
ACCEPTED_MAIN_RISK_SEAL_V11_DIGESTS = (
    "7b770ad617b9703ec84b846a5d348883940be02dbdc0c398d971c52099545eff",
    "a1f3ad3097909c956b9cd10558f82062984869bd768d21e512d3885083380f0c",
)
ACCEPTED_MAIN_RISK_SEAL_V11_RISK_EVIDENCE_DIGESTS = (
    "77662c25b5c4f92f1ebf00674fc02e3688fa5321c42e652f8d492c9dab000b30",
    "53b9bceb1908d2d84c6321605792c1528ecdb6619071bdae236c2ed4f555a1d8",
)
ACCEPTED_MAIN_RISK_EVIDENCE_V11_DIGEST = "6acc79c6a495d2e1dbba82f0c6f0ed99f9c8c4b107e92b4ffe7c50b24536e4e9"


@pytest.fixture(autouse=True, scope="module")
def _production_tables_with_exact_memos():
    """The risk lineage tests' exact upstream memos and identity memos of pure re-proofs; every PRODUCTION rule and
    approval table stays (a TEST-ONLY table is installed only where a test says so)."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        archives = gpe.SameObjects(regime.verify_historical_ohlc_bar_archive)
        for module in (regime, gpe.execution, risk):
            patch.setattr(module, "verify_historical_ohlc_bar_archive", archives)
        exact = gpe._EXACT[(gpe.execution, "verify_historical_pit_dataset")]  # noqa: SLF001
        for module in (regime, ctr, risk):
            patch.setattr(module, "verify_historical_pit_dataset", exact)
        assert risk._APPROVAL_TABLE is PRODUCTION  # noqa: SLF001
        yield
    assert risk._APPROVAL_TABLE is PRODUCTION  # noqa: SLF001


# --- the one exact arithmetic (KD-1..KD-12 with the D-A1 fit) ---------------------------------------------------------------


def fit(trades: list, rho: object = F(1, 100), unknown: int = 0):  # noqa: ANN201
    """``historical_execution_kelly_fit`` on ``(net, risk)`` pairs, oldest first (a None risk is unproven)."""

    known = tuple((F(net), None if value is None else F(value)) for net, value in trades)
    return historical_execution_kelly_fit(known, unknown_count=unknown, rho=None if rho is None else F(rho))  # type: ignore[arg-type]


def oracle(window: list) -> tuple:
    """An independent KD-4..KD-6 oracle: Fraction weights (19/20)^j, j = 0 the newest, and plain means."""

    outcomes = [F(net) / F(value) for net, value in window]
    weights = [F(19, 20) ** j for j in range(len(window))]
    newest = list(reversed(window))
    p = sum((w for w, (net, _) in zip(weights, newest, strict=True) if F(net) > 0), F(0)) / sum(weights)
    wins = [r for (net, _), r in zip(window, outcomes, strict=True) if F(net) > 0]
    losses = [-r for (net, _), r in zip(window, outcomes, strict=True) if F(net) < 0]
    mean_win, mean_loss = sum(wins, F(0)) / len(wins), sum(losses, F(0)) / len(losses)
    b = mean_win / mean_loss
    return p, mean_win, mean_loss, b, (p * b - (1 - p)) / b


def test_a_window_without_a_win_or_a_loss_is_ratio_undefined_and_never_passes() -> None:  # KD-2, KD-3
    for trades, zeros in (([], 0), ([(-1, 1)], 0), ([(2, 1), (3, 1)], 0), ([(0, 1), (2, 1)], 1), ([(0, 1)], 1)):
        read = fit(trades)
        assert (read.status, read.reason, read.zeros) == (BLOCKED, "KELLY_RATIO_UNDEFINED", zeros), trades
        assert read.f_star is None and read.fit_value is None
    assert fit([(2, 1)]).blocks == ("KELLY_RATIO_UNDEFINED",)  # "wins only gives f* = 1" is never read


def test_zero_trades_count_in_p_and_never_in_b_or_lbar() -> None:  # KD-2, KD-4, KD-5
    base, zeroed = fit([(-1, 1), (2, 1)]), fit([(-1, 1), (0, 1), (2, 1)])
    assert (base.p, zeroed.p) == (F(20, 39), F(400, 1141))  # the zero holds weight 19/20 in the denominator
    assert (base.b, base.mean_loss) == (zeroed.b, zeroed.mean_loss) == (F(2), F(1))
    assert (zeroed.wins, zeroed.losses, zeroed.zeros) == (1, 1, 1)


def test_the_ewma_weights_the_newest_trade_first_exactly() -> None:  # KD-4 (HC-16b)
    assert fit([(-1, 1), (2, 1)]).p == F(20, 39)  # the newest (a win) weighs 1, the older loss 19/20
    assert fit([(2, 1), (-1, 1)]).p == F(19, 39)
    window = [(3, 2), (-1, 1), (0, 1), (5, 3), (-2, 1), (1, 1), (-7, 4)]
    read = fit(window, rho=F(1, 1000))
    assert (read.p, read.mean_win, read.mean_loss, read.b, read.f_star) == oracle(window)


def alternating(count: int, oldest: tuple = (-1, 1)) -> list:
    """``count`` trades, oldest first: ``oldest`` then alternating wins of 2R and losses of 1R (the newest a win)."""

    rest = [(2, 1) if (count - 1 - index) % 2 == 0 else (-1, 1) for index in range(1, count)]
    return [oldest, *rest]


def test_the_g_window_holds_the_latest_60_and_the_kd1_window_the_latest_100() -> None:  # KD-1, KD-7, KD-10
    rho = F(1, 1000)
    sixty, sixty_one = fit(alternating(60, (-50, 1)), rho), fit(alternating(61, (-50, 1)), rho)
    assert (sixty.g_count, len(sixty.terms), sixty.terms[0]) == (60, 60, 1 + rho * -50)
    assert (sixty_one.g_count, len(sixty_one.terms)) == (60, 60) and 1 + rho * -50 not in sixty_one.terms
    assert sixty_one.mean_loss == oracle(alternating(61, (-50, 1)))[2]  # still inside the KD-1 window
    ninety_nine = fit(alternating(99), rho)
    assert (ninety_nine.window_count, ninety_nine.status) == (99, PASS)
    assert ninety_nine.f == ninety_nine.f_star / 4 and ninety_nine.f_cap == min(ninety_nine.f, F(4, 100))  # type: ignore[operator]
    hundred = fit(alternating(100), rho)
    assert (hundred.window_count, hundred.status, hundred.reason) == (100, BLOCKED, "KELLY_BOOTSTRAP_UNDECIDED")
    assert hundred.f is None and hundred.f_cap is None and hundred.fit_value is None  # never an invented bootstrap
    hundred_one = fit(alternating(101, (-50, 1)), rho)
    assert hundred_one.window_count == 100 and hundred_one.mean_loss == F(1)  # the oldest left the KD-1 window
    # the solvency domain reads every known outcome, inside a window or not (PRDV4 §1.21, A1.3)
    ruined = fit(alternating(101, (-2000, 1)), rho)
    assert (ruined.status, ruined.reason) == (FAIL, "KELLY_LOG_DOMAIN_RUIN")


def test_f_star_not_positive_fails_and_dominates_the_undecided_bootstrap() -> None:  # KD-6, KD-12
    read = fit([(-3, 1), (1, 1)])
    assert read.f_star == F(20, 39) - F(19, 39) * 3 < 0
    # 0.97 x 1.01 < 1 is proven as well: every proven failure is recorded, the first in order is the reason
    assert (read.status, read.reason, read.failures) == (
        FAIL,
        "KELLY_NON_POSITIVE",
        ("KELLY_NON_POSITIVE", "KELLY_LOG_UTILITY_NON_POSITIVE"),
    )
    assert (read.f, read.f_cap, read.fit_value) == (None, None, None)  # f*/4 of a non-positive f* is never read
    alone = fit([(-3, 1), (1, 1)], None)  # no rho: no product, f* <= 0 alone
    assert (alone.status, alone.failures, alone.blocks) == (
        FAIL,
        ("KELLY_NON_POSITIVE",),
        ("KELLY_RISK_FRACTION_UNPROVEN",),
    )
    losing = [(-3, 1) if index % 2 == 0 else (1, 1) for index in range(100)]
    hundred = fit(losing, F(1, 100_000))
    assert (hundred.window_count, hundred.status, hundred.reason) == (100, FAIL, "KELLY_NON_POSITIVE")
    assert "KELLY_BOOTSTRAP_UNDECIDED" not in hundred.blocks  # the proven f* <= 0 needs no bootstrap


def test_the_d_a1_fit_scales_rho_by_max_1_lbar() -> None:  # KD-9, D-A1 Alternative 1
    rho = F(1, 100)
    assert fit([(-1, 2), (2, 1)], rho).fit_value == rho  # Lbar = 1/2: never loosened below RECORD A's wording
    assert fit([(-1, 1), (2, 1)], rho).fit_value == rho  # Lbar = 1
    assert fit([(-3, 2), (4, 1)], rho).fit_value == rho * F(3, 2)  # Lbar = 3/2


def test_kd9_holds_at_equality_and_fails_one_part_in_10_30_above() -> None:  # KD-9, KD-12
    at_cap = fit([(-1, 1), (2, 1)], F(1, 25))  # f* = 7/26, f = 7/104 > 0.04: f_cap = 1/25 and Lbar = 1
    assert (at_cap.f_star, at_cap.f, at_cap.f_cap) == (F(7, 26), F(7, 104), F(1, 25))
    assert (at_cap.status, at_cap.product_exceeds_one) == (PASS, True)
    over = fit([(-1, 1), (2, 1)], F(1, 25) + F(1, 10**30))
    assert (over.status, over.reason) == (FAIL, "KELLY_FIT_EXCEEDED")
    history = [(-3, 2), (4, 1)]  # Lbar = 3/2: the bound is f_cap / Lbar = (1/25) / (3/2) = 2/75
    assert fit(history, F(2, 75)).status is PASS
    assert fit(history, F(2, 75) + F(1, 10**30)).reason == "KELLY_FIT_EXCEEDED"
    record_a_wording = fit(history, F(1, 30))  # 1/30 <= f_cap = 1/25 would have passed RECORD A's rho <= f_cap
    assert (record_a_wording.status, record_a_wording.reason) == (FAIL, "KELLY_FIT_EXCEEDED")


def test_the_decision_passes_at_r4_and_the_fill_fails_at_r5_on_the_same_history() -> None:  # KD-9 at R-4 and R-5
    history = [(-3, 2), (4, 1)]
    decision, filled = fit(history, F(2, 75)), fit(history, F(2, 75) + F(1, 10**9))
    assert (decision.status, filled.status, filled.reason) == (PASS, FAIL, "KELLY_FIT_EXCEEDED")
    assert economics._KELLY_FILL_REFUSALS[filled.reason] == "governed_paper_kelly_fit_exceeded_at_fill"  # noqa: SLF001
    assert set(economics._KELLY_FILL_REFUSALS) == set(HISTORICAL_EXECUTION_KELLY_FAILURES)  # noqa: SLF001


def test_the_solvency_domain_fails_at_zero_and_below_from_the_first_known_trade() -> None:  # A1.3, KD-10b
    for rho in (F(1, 100), F(1, 50)):  # 1 + rho x (-100) is 0, then -1
        read = fit([(-100, 1)], rho)
        assert (read.status, read.reason) == (FAIL, "KELLY_LOG_DOMAIN_RUIN")
        assert read.blocks == ("KELLY_RATIO_UNDEFINED",)  # the proven failure dominates the undefined window
    assert fit([(-100, 1)], F(1, 200)).reason == "KELLY_RATIO_UNDEFINED"


def test_a_product_of_exactly_one_fails_and_two_losses_fail_without_a_class() -> None:  # KD-10c, T-KCW-08
    exact = fit([(-200, 201), (1, 1)], F(1, 200))  # the terms 200/201 and 201/200, oldest first
    assert exact.terms == (F(200, 201), F(201, 200)) and exact.product_exceeds_one is False
    assert exact.fit_value <= exact.f_cap  # type: ignore[operator]  # KD-9 alone passes: the product decides
    assert (exact.status, exact.reason, exact.failures) == (
        FAIL,
        "KELLY_LOG_UTILITY_NON_POSITIVE",
        ("KELLY_LOG_UTILITY_NON_POSITIVE",),
    )
    both = fit([(1, 1), (-10, 11)], F(1, 10))  # 11/10 x 10/11 = 1 with KD-9 exceeded: every failure, in order
    assert both.failures == ("KELLY_FIT_EXCEEDED", "KELLY_LOG_UTILITY_NON_POSITIVE")
    assert both.reason == "KELLY_FIT_EXCEEDED"
    losses = fit([(-1, 1), (-1, 1)])
    assert (losses.status, losses.reason, losses.blocks) == (
        FAIL,
        "KELLY_LOG_UTILITY_NON_POSITIVE",
        ("KELLY_RATIO_UNDEFINED",),
    )


def test_fewer_than_two_known_trades_have_no_product() -> None:  # KD-10c needs n_g >= 2
    read = fit([(2, 1)])
    assert (read.g_count, read.terms, read.product_exceeds_one, read.diagnostic) == (1, (F(102, 100),), None, None)


def test_a_huge_exact_product_is_compared_and_never_rendered() -> None:  # KD-10e
    big = 10**300
    trades = [
        (F(2 * big + k, big), F(big + 3 * k, big)) if k % 2 else (F(-(big + k), big), F(big + k + 1, big))
        for k in range(60)
    ]
    read = historical_execution_kelly_fit(tuple(trades), unknown_count=0, rho=F(1, 100))
    numerators = math.prod(term.numerator for term in read.terms)
    assert numerators.bit_length() > 40_000  # about 12,000 digits: far beyond CPython's 4,300-digit int-to-text limit
    assert type(read.product_exceeds_one) is bool and len(read.terms) == 60
    product = math.prod(read.terms, start=F(1))
    assert read.product_exceeds_one is (product.numerator > product.denominator)  # the exact comparison, oracle
    reading = build_governed_paper_kelly_reading(
        decision_sequence=1,
        decision_time_ns=100,  # every trade closed and known at 0..59
        target_direction="SHORT",
        trades=tuple(GovernedPaperKellyKnownTrade(f"t{k}", k, k, net, value) for k, (net, value) in enumerate(trades)),
        rho=F(1, 100),
        rho_reason="",
    )
    assert (reading.g_count, reading.product_exceeds_one) == (60, read.product_exceeds_one)
    assert len(reading.terms) == 60 and all(len(item) < 60 for item in reading.terms)  # each a scale-18 rendering


def test_an_unproven_risk_an_unknown_trade_or_an_unproven_rho_blocks_unless_a_failure_is_proven() -> None:
    for value in (None, 0, -1):  # KD-10a: R_j needs a proven positive risk
        read = fit([(-1, value), (2, 1)])
        assert (read.status, read.reason) == (BLOCKED, "KELLY_OUTCOME_UNPROVEN"), value
    ruin = fit([(-200, 1), (-1, None), (2, 1)])
    assert (ruin.status, ruin.reason, ruin.blocks) == (FAIL, "KELLY_LOG_DOMAIN_RUIN", ("KELLY_OUTCOME_UNPROVEN",))
    unknown = fit([(-1, 1), (2, 1)], unknown=1)  # A1.3: a closed trade not yet known keeps the windows undefined
    assert (unknown.status, unknown.reason, unknown.f_star) == (BLOCKED, "KELLY_TRADE_COUNT_UNPROVEN", None)
    assert fit([(-200, 1), (2, 1)], unknown=1).reason == "KELLY_LOG_DOMAIN_RUIN"  # a known ruin is proven anyway
    no_rho = fit([(-1, 1), (2, 1)], None)  # KD-0 C-2: no FCD-01 fraction of the candidate
    assert (no_rho.status, no_rho.reason, no_rho.fit_value, no_rho.terms) == (
        BLOCKED,
        "KELLY_RISK_FRACTION_UNPROVEN",
        None,
        (),
    )
    assert fit([(-3, 1), (1, 1)], None).reason == "KELLY_NON_POSITIVE"  # f* needs no rho
    assert set(HISTORICAL_EXECUTION_KELLY_BLOCKS) >= set(no_rho.blocks)
    for kwargs, pattern in (
        ({"unknown_count": -1, "rho": F(1)}, "kelly_unknown_count_invalid"),
        ({"unknown_count": 0, "rho": 0.01}, "kelly_rho_malformed"),
    ):
        with pytest.raises(HistoricalExecutionEconomicsError, match=pattern):
            historical_execution_kelly_fit((), **kwargs)  # type: ignore[arg-type]
    with pytest.raises(HistoricalExecutionEconomicsError, match="kelly_known_trade_malformed"):
        historical_execution_kelly_fit(((1.0, F(1)),), unknown_count=0, rho=F(1))  # type: ignore[arg-type]


# --- the reading -----------------------------------------------------------------------------------------------------------


def known(trade_id: str, closed: int, knowledge: int, net: object, value: object) -> GovernedPaperKellyKnownTrade:
    return GovernedPaperKellyKnownTrade(trade_id, closed, knowledge, F(net), None if value is None else F(value))  # type: ignore[arg-type]


TRADES = (known("t1", 10, 15, -1, 1), known("t2", 20, 25, 2, 1))


def read_at(instant: int, rho: object = F(1, 25), reason: str = "", trades: tuple = TRADES):  # noqa: ANN201
    return build_governed_paper_kelly_reading(
        decision_sequence=3,
        decision_time_ns=instant,
        target_direction="LONG",
        trades=trades,
        rho=rho,
        rho_reason=reason,
    )


def test_the_reading_reads_the_trades_known_at_its_instant_and_is_digest_bound() -> None:  # A1.3, KD-12, KD-13
    reading = read_at(30)
    assert (reading.status, reading.reason, reading.known_trade_ids) == (
        GovernedPaperKellyStatus.PASS,
        "KELLY_FIT_PROVEN",
        ("t1", "t2"),
    )
    assert reading.coverage == GOVERNED_PAPER_KELLY_COVERAGE  # no ACTIVE incubation record: never covered
    assert reading.reading_digest == governed_paper_kelly_reading_digest(reading)
    assert governed_paper_kelly_reading_digest(replace(reading, fit_value="0")) != reading.reading_digest
    late = read_at(22)  # t2 closed at 20 but its last final rate is visible only at 25
    assert (late.status, late.reason, late.unknown_trade_ids) == (
        GovernedPaperKellyStatus.BLOCKED,
        "KELLY_TRADE_COUNT_UNPROVEN",
        ("t2",),
    )
    assert read_at(12).unknown_trade_ids == ("t1",) and read_at(5).reason == "KELLY_RATIO_UNDEFINED"
    no_rho = read_at(30, None, "no_fresh_visible_mark")
    assert (no_rho.rho, no_rho.rho_reason, no_rho.reason) == (
        None,
        "no_fresh_visible_mark",
        "KELLY_RISK_FRACTION_UNPROVEN",
    )
    for rho, reason in ((None, ""), (F(1, 25), "why")):
        with pytest.raises(GovernedPaperKellyError, match="rho_reason_malformed"):
            read_at(30, rho, reason)
    with pytest.raises(GovernedPaperKellyError, match="target_direction_invalid"):
        build_governed_paper_kelly_reading(
            decision_sequence=3, decision_time_ns=30, target_direction="FLAT", trades=TRADES, rho=F(1), rho_reason=""
        )


def test_an_unrepresentable_value_is_never_recorded_and_a_pass_becomes_blocked() -> None:  # KD-10e
    huge_b = read_at(30, F(1, 100), "", (known("t1", 10, 10, -1, 10**80), known("t2", 20, 20, 1, 1)))
    assert (huge_b.status, huge_b.reason, huge_b.b) == (
        GovernedPaperKellyStatus.BLOCKED,
        GOVERNED_PAPER_KELLY_UNREPRESENTABLE,
        None,
    )
    assert GOVERNED_PAPER_KELLY_UNREPRESENTABLE in huge_b.blocks and huge_b.terms == ()
    failing = read_at(30, F(10**60), "", (known("t1", 10, 10, -1, 10**100), known("t2", 20, 20, 1, 1)))
    assert failing.status is GovernedPaperKellyStatus.FAIL and GOVERNED_PAPER_KELLY_UNREPRESENTABLE in failing.blocks


# --- the engine: schedule v8 --------------------------------------------------------------------------------------------


def hold_schedule(world: object, direction: str, schema_version: str = V8, bounds: tuple | None = None):  # noqa: ANN201
    """``rmt.v7_schedule`` at ``schema_version`` whose HOLD window authorizes one unit of ``direction`` only, with the
    whole-HOLD CVaR bound of unit 0 unless ``bounds`` is given (SYNTHETIC)."""

    long_unit, short_unit = (rmt.d(1), rmt.d(0)) if direction == "LONG" else (rmt.d(0), rmt.d(1))
    window = economics.HistoricalExecutionAdmissionWindow(
        lifet.ANCHOR, lifet.HOLD_END, long_unit, short_unit, rmt.d(10_000)
    )
    return rmt.v7_schedule(
        world,
        rmt.whole_hold(0, 0) if bounds is None else bounds,
        schema_version=schema_version,
        windows=(window,),
    )


def governed(result: object, schedule: object):  # noqa: ANN201
    outcome = simulate_historical_execution_governed_paper(
        result,  # type: ignore[arg-type]
        expected_result_digest=result.result_digest,  # type: ignore[attr-defined]
        schedule=schedule,  # type: ignore[arg-type]
    )
    assert outcome.simulated is True, outcome.reason_codes
    return outcome


@functools.cache
def long_v2():  # noqa: ANN201
    path = lifet.Path(rates=(lifet.NEGATIVE,) * 12)
    return sst.run_under(path, lifet.HOLD_END, "v2"), lifet.world(path, end=lifet.HOLD_END)


def test_schedule_v8_refuses_the_first_entry_fill_whole_where_schedule_v7_fills_it() -> None:
    for (result, world), direction in ((rmt.hold_v2(), "SHORT"), (long_v2(), "LONG")):
        admitted = governed(result, hold_schedule(world, direction, V7))
        assert rmt.entry_fill(admitted).outcome is HistoricalExecutionFillOutcome.FILLED, direction
        assert admitted.trades[0].direction == direction
        refused = governed(result, hold_schedule(world, direction))
        fill = rmt.entry_fill(refused)
        # no incubation record: the first trade's window holds no known trade, so the fit is never defined
        assert (fill.outcome, fill.reason) == (
            HistoricalExecutionFillOutcome.REJECTED,
            "governed_paper_kelly_unproven_at_fill",
        )
        assert refused.position_transitions == () and refused.fee_cashflows == () and refused.trades == ()
        assert fill.fill_digest in refused.governance_rejected_fill_digests
        assert refused.schema_version == HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION
        # the earlier rules still come first: without a CVaR bound C-10 refuses before the fit is read
        unbounded = governed(result, hold_schedule(world, direction, bounds=()))
        assert rmt.entry_fill(unbounded).reason == "governed_paper_cvar_unproven_at_fill"
    _, world = rmt.hold_v2()
    v7, v8 = hold_schedule(world, "SHORT", V7), hold_schedule(world, "SHORT")
    assert set(historical_execution_admission_schedule_to_dict(v8)) == set(
        historical_execution_admission_schedule_to_dict(v7)
    )
    assert canonical_historical_execution_admission_schedule(v8) == v8


def seeded(history: tuple):  # noqa: ANN201
    """The schedule v8 run of the SHORT HOLD world whose simulation starts with ``history`` already closed: ``(net PnL,
    opening risk, knowledge instant)`` per trade, oldest first. A WHITE-BOX stand-in for a lineage's earlier trades,
    which no evaluation can hold while no incubation record is ACTIVE (KD-13)."""

    original = economics._GovernedPaperSimulation.__init__  # noqa: SLF001

    def init(self: object, *args: object, **kwargs: object) -> None:
        original(self, *args, **kwargs)  # type: ignore[arg-type]
        self.trade_exact_values.extend(  # type: ignore[attr-defined]
            economics.HistoricalExecutionTradeExactValues(
                f"seed-{k}", F(net), None if value is None else F(value), instant
            )
            for k, (net, value, instant) in enumerate(history)
        )

    result, world = rmt.hold_v2()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(economics._GovernedPaperSimulation, "__init__", init)  # noqa: SLF001
        return governed(result, hold_schedule(world, "SHORT"))


def test_a_known_history_admits_a_fitting_fill_and_refuses_a_failing_or_undefined_one_whole() -> None:  # R-5
    result, world = rmt.hold_v2()
    v7 = governed(result, hold_schedule(world, "SHORT", V7))
    entry = rmt.entry_fill(v7)
    basis = F(entry.fill_price)
    stop = basis + min(F(3), F(15, 1000) * basis)
    rho = ((stop - 100) + stop * F(10, 10_000)) / rmt.candidate_equity(entry)  # the fill's own R-5 fraction (oracle)
    assert historical_execution_kelly_fit(((F(-1), F(1)), (F(3), F(1))), unknown_count=0, rho=rho).status is PASS
    passing = seeded(((-1, 1, 0), (3, 1, 0)))  # b = 3, f_cap = 0.04 >= rho: KD-9 and KD-10 hold at every entry
    assert rmt.entry_fill(passing).outcome is HistoricalExecutionFillOutcome.FILLED
    # a passing fit changes nothing the v7 run executes: every fill, transition and trade (exits never reach it)
    assert (passing.fills, passing.position_transitions, passing.trades) == (
        v7.fills,
        v7.position_transitions,
        v7.trades,
    )
    seed_100 = tuple((2, 1, 0) if k % 2 else (-1, 1, 0) for k in range(100))
    for history, reason in (
        (((-1000, 1, 0), (3000, 1, 0)), "governed_paper_kelly_fit_exceeded_at_fill"),  # rho x Lbar 1,000 > 0.04
        (((-3, 1, 0), (1, 1, 0)), "governed_paper_kelly_non_positive_at_fill"),
        ((*[(-1, 1, 0)] * 11, (10, 1, 0)), "governed_paper_kelly_log_utility_non_positive_at_fill"),
        (((-1, 1, 0), (3, 1, 0), (3, 1, lifet.HOLD_END)), "governed_paper_kelly_unproven_at_fill"),  # not yet known
        (seed_100, "governed_paper_kelly_unproven_at_fill"),  # n_w = 100: the undecided bootstrap
        (((-1, None, 0), (3, 1, 0)), "governed_paper_kelly_unproven_at_fill"),  # an unproven risk
    ):
        refused = seeded(history)  # type: ignore[arg-type]
        fill = rmt.entry_fill(refused)
        assert (fill.outcome, fill.reason) == (HistoricalExecutionFillOutcome.REJECTED, reason), reason
        assert refused.position_transitions == () and refused.fee_cashflows == ()  # whole: never a resize


def test_only_an_exposure_increasing_fill_reaches_the_kelly_hook() -> None:
    calls: list[object] = []
    original = economics._GovernedPaperSimulation._kelly_fill_admission  # noqa: SLF001

    def recording(self: object, order: object, equity: object) -> object:
        calls.append(order)
        return original(self, order, equity)  # type: ignore[arg-type]

    result, world = rmt.hold_v2()
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(economics._GovernedPaperSimulation, "_kelly_fill_admission", recording)  # noqa: SLF001
        outcome = governed(result, rmt.v7_schedule(world, rmt.whole_hold(0, 0)))
    kinds = [item.transition_kind.value for item in outcome.position_transitions]
    increasing = [kind for kind in kinds if kind in ("OPEN", "INCREASE")]
    assert "OPEN" in kinds and "CLOSE" in kinds and len(calls) == len(increasing)  # every exit bypasses the fit
    assert all(type(item).__name__ == "HistoricalExecutionIntent" for item in calls)


@functools.cache
def hold_derivation():  # noqa: ANN201
    result, world = rmt.hold_v2()
    derivation = simulate_historical_execution_governed_paper_derivation(
        result, expected_result_digest=result.result_digest, schedule=rmt.v7_schedule(world, rmt.whole_hold(0, 0))
    )
    return result, world, derivation


def visibility(record: object) -> int:
    return max(record.available_at_ns, record.finalized_at_ns)  # type: ignore[attr-defined]


def test_a_v7_derivation_carries_every_closed_trades_exact_kelly_inputs() -> None:
    _, world, derivation = hold_derivation()
    outcome = derivation.outcome
    closed = [item for item in outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED]
    assert closed and [item.trade_id for item in derivation.trade_exact_values] == [item.trade_id for item in closed]
    fills = {item.fill_digest: item for item in outcome.fills}
    cashflows = {item.cashflow_digest: item for item in outcome.funding_cashflows}
    records = {item.record_digest: item for item in world.dataset.records}  # type: ignore[attr-defined]
    for record, values in zip(closed, derivation.trade_exact_values, strict=True):
        assert historical_execution_render_amount(values.realized_net_pnl) == record.realized_net_pnl
        # the independent R-5 oracle: SHORT 1 at the flat mark 100, the nearer of 1.5 x ATR 2 and 1.5% of the basis,
        # the mark below the stop so x is the stop, and the policy's 5 bps taker fee plus 5 bps slippage floor
        basis = F(fills[record.entry_fill_digests[0]].fill_price)
        stop = basis + min(F(3), F(15, 1000) * basis)
        assert values.opening_risk == (stop - 100) + stop * F(10, 10_000)
        carried = [
            visibility(records[cashflows[digest].funding_record_digest]) for digest in record.funding_cashflow_digests
        ]
        assert values.knowledge_ns == max([record.end_time_ns, *carried])  # type: ignore[type-var]
    assert any(item.funding_cashflow_digests for item in closed)  # a trade carries settlements: its knowledge waits


def kelly_trades(derivation: object, world: object, **changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "outcome": derivation.outcome,  # type: ignore[attr-defined]
        "trade_exact_values": derivation.trade_exact_values,  # type: ignore[attr-defined]
        "dataset": world.dataset,  # type: ignore[attr-defined]
        "economics_policy": lifet.economics_policy(),
        "position_management_policy": sst.pm_v2(),
        "position_management_archive": lifet.ohlc_archive(),
    }
    values.update(changes)
    return governed_paper_kelly_trades(**values)  # type: ignore[arg-type]


def test_every_trade_is_re_proven_against_the_sealed_records_and_a_tamper_fails_closed() -> None:  # KD-0, KD-10a
    result, world, derivation = hold_derivation()
    assert result.position_management_policy_digest == sst.pm_v2().policy_digest
    trades, facts = kelly_trades(derivation, world)
    for trade, fact, values in zip(trades, facts, derivation.trade_exact_values, strict=True):
        assert trade.risk_reason == "" and fact.opening_risk == values.opening_risk
        assert trade.opening_risk == historical_execution_render_amount(values.opening_risk)  # type: ignore[arg-type]
        assert trade.outcome_r == historical_execution_render_amount(values.realized_net_pnl / values.opening_risk)  # type: ignore[operator]
        assert trade.trade_class == (
            "WIN" if values.realized_net_pnl > 0 else "LOSS" if values.realized_net_pnl < 0 else "ZERO"
        )
        assert (trade.knowledge_ns, trade.direction) == (values.knowledge_ns, "SHORT")
    first = derivation.trade_exact_values[0]
    for tampered, reason in (
        (replace(first, realized_net_pnl=first.realized_net_pnl + 1), "trade_net_pnl_not_of_the_record"),
        (replace(first, opening_risk=first.opening_risk + F(1, 10**18)), "trade_opening_risk_not_of_the_records"),  # type: ignore[operator]
        (replace(first, knowledge_ns=first.knowledge_ns + 1), "trade_knowledge_not_of_the_records"),
        (replace(first, trade_id="f" * 64), "trade_exact_values_not_of_the_outcome"),
    ):
        with pytest.raises(GovernedPaperKellyError, match=reason):
            kelly_trades(derivation, world, trade_exact_values=(tampered, *derivation.trade_exact_values[1:]))
    for reordered in (derivation.trade_exact_values[::-1], (*derivation.trade_exact_values, first)):
        if reordered != derivation.trade_exact_values:
            with pytest.raises(GovernedPaperKellyError, match="trade_exact_values_not_of_the_outcome"):
                kelly_trades(derivation, world, trade_exact_values=reordered)
    unmeasured = (replace(first, opening_risk=None), *derivation.trade_exact_values[1:])
    assert kelly_trades(derivation, world, trade_exact_values=unmeasured)[0][0].risk_reason == (
        "opening_risk_not_measured_by_the_re_run"
    )
    # a forged opening fill price: the bound outcome digest no longer recomputes, so it is never read
    opening = derivation.outcome.trades[0].entry_fill_digests[0]
    forged = tuple(
        replace(item, fill_price=lifet.d(F(item.fill_price) + 1)) if item.fill_digest == opening else item
        for item in derivation.outcome.fills
    )
    outcome = replace(derivation.outcome, fills=forged)
    with pytest.raises(GovernedPaperKellyError, match="governed_outcome_digest_mismatch$"):
        kelly_trades(derivation, world, outcome=outcome)
    # even re-digested, it no longer matches its protection's basis: its risk is unproven, never accepted
    resealed = replace(outcome, outcome_digest=historical_execution_governed_paper_outcome_digest(outcome))
    (trade, *_), (fact, *_) = kelly_trades(derivation, world, outcome=resealed)
    assert (trade.risk_reason, fact.opening_risk) == ("protection_not_of_the_opening_fill", None)
    other, other_world = long_v2()
    assert other.result_digest != result.result_digest
    for changes, reason in (  # provenance: one dataset, one economics policy, a governed simulated outcome
        ({"dataset": other_world.dataset}, "dataset_not_of_the_outcome"),  # type: ignore[attr-defined]
        ({"outcome": replace(derivation.outcome, simulated=False)}, "governed_outcome_malformed"),
        ({"outcome": replace(derivation.outcome, outcome_digest="0" * 64)}, "governed_outcome_digest_mismatch"),
        (
            {"economics_policy": replace(lifet.economics_policy(), policy_digest="0" * 64)},
            "economics_policy_not_of_the_outcome",
        ),
        ({"position_management_archive": object()}, "position_management_inputs_malformed"),
    ):
        with pytest.raises(GovernedPaperKellyError, match=f"{reason}$"):
            kelly_trades(derivation, world, **changes)
    # a policy v1 arms no R-1 stop: the risk of every opening fill is unproven, never estimated (KD-10a)
    (trade, *_), (fact, *_) = kelly_trades(derivation, world, position_management_policy=lifet.pm_policy())
    assert (trade.risk_reason, fact.opening_risk) == (
        "opening_stop_unproven:armed_stop_needs_the_policy_v2_r1_stop",
        None,
    )


def test_the_evidence_and_its_prefix_are_deterministic_and_run_independent() -> None:
    result, world, derivation = hold_derivation()
    entries = tuple(
        (item.decision_sequence, item.decision_time_ns, item.resulting_direction)
        for item in world.run.decisions  # type: ignore[attr-defined]
        if item.resulting_direction in ("LONG", "SHORT")
    )
    fractions = {sequence: (F(1, 100), "") for sequence, _, _ in entries}

    def derive():  # noqa: ANN202
        return derive_governed_paper_kelly_evidence(
            decisions=entries,
            outcome=derivation.outcome,
            trade_exact_values=derivation.trade_exact_values,
            dataset=world.dataset,  # type: ignore[attr-defined]
            economics_policy=lifet.economics_policy(),
            position_management_policy=sst.pm_v2(),
            position_management_archive=lifet.ohlc_archive(),
            fractions=fractions,
            risk_evidence_digest="e" * 64,
            instrument=lifet.INS,
            start_ns=lifet.ANCHOR,
            horizon_ns=lifet.HOLD_END,
        )

    evidence = derive()
    assert evidence == derive() and evidence.evidence_digest == governed_paper_kelly_evidence_digest(evidence)
    assert (evidence.paper_only, evidence.execution_authorized, evidence.edge_proven, evidence.stage4_complete) == (
        True,
        False,
        False,
        False,
    )
    assert (
        evidence.decision_ids == GOVERNED_PAPER_KELLY_DECISION_IDS
        and evidence.pending_items == GOVERNED_PAPER_KELLY_PENDING_ITEMS
    )
    later = [item for item in evidence.readings if item.known_trade_ids]
    assert later, "a decision after a trade's knowledge reads it"
    cut = later[0].decision_time_ns
    before = governed_paper_kelly_prefix_digest(evidence, before_ns=cut)
    assert before != governed_paper_kelly_prefix_digest(evidence, before_ns=cut + 1)  # the reading at cut joins it
    renamed = replace(
        evidence, trades=tuple(replace(item, trade_id="0" * 64, trade_digest="0" * 64) for item in evidence.trades)
    )
    assert governed_paper_kelly_prefix_digest(renamed, before_ns=lifet.HOLD_END) == governed_paper_kelly_prefix_digest(
        evidence, before_ns=lifet.HOLD_END
    )  # run-derived identifiers are not X1 content
    assert governed_paper_kelly_evidence_digest(renamed) != evidence.evidence_digest
    with pytest.raises(GovernedPaperKellyError, match="entry_fractions_malformed"):
        derive_governed_paper_kelly_evidence(
            decisions=entries,
            outcome=derivation.outcome,
            trade_exact_values=derivation.trade_exact_values,
            dataset=world.dataset,  # type: ignore[attr-defined]
            economics_policy=lifet.economics_policy(),
            position_management_policy=sst.pm_v2(),
            position_management_archive=lifet.ohlc_archive(),
            fractions={},
            risk_evidence_digest="e" * 64,
            instrument=lifet.INS,
            start_ns=lifet.ANCHOR,
            horizon_ns=lifet.HOLD_END,
        )


# --- the gate: rule set v11 and SCALE-1 ---------------------------------------------------------------------------------


def test_rule_set_v11_is_rule_set_v10_with_the_kelly_rule_and_v10_keeps_its_identity() -> None:
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET["checks"]
        == GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET["checks"]
    )
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET["rule_set_id"]
        == GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_ID
        == ("governed-paper-entry-safety.v11")
    )
    assert "kelly_rule" in GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET
    assert "kelly_rule" not in GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET
    assert GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V10_DIGEST
    assert GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST not in (
        ACCEPTED_MAIN_RULE_SET_V10_DIGEST,
        *rmt.ACCEPTED_MAIN_RULE_SET_DIGESTS,
    )
    with pytest.raises(GovernedPaperEntrySafetyError, match="kelly_rule_set_needs_the_risk_measurement_rule_set"):
        governed_paper_entry_safety_rule_set(kelly=True)
    assert GOVERNED_PAPER_KELLY_RULE["kd13"] == GOVERNED_PAPER_KELLY_COVERAGE
    assert "KD-7:the_100_trade_bootstrap" in GOVERNED_PAPER_KELLY_PENDING_ITEMS


def kelly_facts(status: str) -> GovernedPaperEntrySafetyKelly:
    """A SYNTHETIC rule set v11 reading of decision 7 at ``est.T`` (SHORT) with the given status."""

    trades = {
        "PASS": TRADES,
        "FAIL": (known("t1", 10, 15, -3, 2), known("t2", 20, 25, 4, 1)),  # Lbar = 3/2 at rho 1/30: KD-9 fails
        "BLOCKED": (),
    }[status]
    reading = build_governed_paper_kelly_reading(
        decision_sequence=7,
        decision_time_ns=est.T,
        target_direction="SHORT",
        trades=trades,
        rho=F(1, 25) if status == "PASS" else F(1, 30),
        rho_reason="",
    )
    assert reading.status.value == status
    return GovernedPaperEntrySafetyKelly(reading, "d" * 64)


def v11(status: str, **observation: object):  # noqa: ANN201
    return replace(rmt.v10(**observation), kelly=kelly_facts(status))


def scale(decision: object) -> tuple:
    check = est.check_of(decision, "SCALE-1")
    return check.status, check.observed, check.reason, check.evidence_record_digests


def test_scale_1_reads_the_kelly_fit_term_in_place_and_keeps_every_other_term_binding() -> None:  # V6
    legacy = governed_paper_entry_safety_a9_multipliers(rmt.v10())
    assert legacy[-1] == ("kelly_fit_1_28", "UNPROVEN", "kelly_fit_pending_items_5_1_and_5_2")  # rule set v10 exactly
    base = scale(evaluate_governed_paper_entry_safety(rmt.v10()))
    assert base[0] is S.BLOCKED_ON_MISSING_INPUT and "kelly_fit_1_28" in base[2]
    proven = v11("PASS")
    terms = governed_paper_entry_safety_a9_multipliers(proven)
    assert terms[-1] == ("kelly_fit_1_28", "PROVEN_ONE", "kelly_fit_proven_at_the_r4_fraction")
    assert terms[:-1] == legacy[:-1]  # every other term is untouched
    status, observed, reason, digests = scale(evaluate_governed_paper_entry_safety(proven))
    assert status is S.BLOCKED_ON_MISSING_INPUT and "kelly_fit_1_28" not in reason  # other terms still unproven
    assert (proven.kelly.reading.reading_digest, "d" * 64) == digests[-2:]  # type: ignore[union-attr]
    status, observed, reason, _ = scale(evaluate_governed_paper_entry_safety(v11("FAIL")))
    assert (status, observed) == (S.FAIL, "kelly_fit_1_28")
    assert reason.endswith("kelly_fit_exceeded_reduces_the_allocation")  # KD-0 C-2: refused, never resized
    blocked = governed_paper_entry_safety_a9_multipliers(v11("BLOCKED"))
    assert blocked[-1] == ("kelly_fit_1_28", "UNPROVEN", "kelly_ratio_undefined")
    decision = evaluate_governed_paper_entry_safety(v11("PASS"))
    assert decision.entry_permitted is False  # SCALE-1 never passes: ENVELOPE_FIT and the other terms stay binding


def test_the_kelly_facts_are_canonical_and_only_on_top_of_the_risk_facts() -> None:
    facts = kelly_facts("PASS")
    for observation, reason in (
        (replace(rmt.v10(), kelly=facts, risk=None), "observation_malformed:kelly_without_the_risk_facts"),
        (
            replace(rmt.v10(), kelly=replace(facts, evidence_digest="nope")),
            "observation_malformed:kelly_evidence_digest",
        ),
        (
            replace(rmt.v10(), kelly=replace(facts, reading=replace(facts.reading, decision_sequence=8))),
            "observation_malformed:kelly_reading",
        ),
        (
            replace(rmt.v10(), kelly=replace(facts, reading=replace(facts.reading, fit_value="0"))),
            "observation_malformed:kelly_reading_digest",
        ),
        (replace(rmt.v10(), kelly=object()), "observation_malformed:kelly"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            evaluate_governed_paper_entry_safety(observation)  # type: ignore[arg-type]


# --- the lineage on world G (seal v12) -------------------------------------------------------------------------------------


def kelly_day(days: tuple, context: object, table: object = rmt.TEST_ONLY_TABLE):  # noqa: ANN201
    cycle_inputs, cycle, seal_inputs = rlt.risk_inputs(days, context)
    seal_inputs = replace(seal_inputs, protection=replace(seal_inputs.protection, kelly=True))
    with rlt.tables(table):  # type: ignore[arg-type]
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def kelly_days(count: int, production: bool = False) -> tuple:
    if count == 0:
        return ()
    days = kelly_days(count - 1, production)
    return (*days, kelly_day(days, rlt.risk_context(len(days)), PRODUCTION if production else rmt.TEST_ONLY_TABLE))


def kelly_gate(  # noqa: ANN201, PLR0913
    item: object,
    day: int,
    context: object,
    schedule: object | None = None,
    kelly: bool = True,  # noqa: FBT001, FBT002
    table: object = rmt.TEST_ONLY_TABLE,
):
    """Day ``day``'s rule set v11 evaluation of ``item`` under the risk ``table``, rebuilt independently through the
    public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics_result = lineage.protected_replay(item)[0]
    with rlt.tables(table):  # type: ignore[arg-type]
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(
                economics_result,
                item.seal.schedule if schedule is None else schedule,  # type: ignore[attr-defined]
            ),
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
            sizing=sct.NO_SOURCE,
            protective_ledger=plt.NO_PROOFS,
            risk=context,  # type: ignore[arg-type]
            kelly=kelly,
        )


def test_world_g_kelly_lineage_seals_v12_binds_the_kelly_evidence_and_refuses_every_entry() -> None:
    days, legacy = kelly_days(4), rlt.risk_days(4)
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V12_SEAL, SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_DIGEST
        assert seal.schedule == replace(old.seal.schedule, schema_version=V8)
        for name in governed_paper_day_seal_to_dict(old.seal):
            if name not in MOVED:
                assert getattr(seal, name) == getattr(old.seal, name), name
        if day:
            assert seal.kelly_prefix_digest_open == days[day - 1].seal.kelly_prefix_digest_close
        verification = rlt.verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
        assert all(not entry.entry_permitted for entry in seal.entry_safety_decisions)
    (entry,) = days[3].seal.entry_safety_decisions  # world G's one entry decision
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    scale_1 = est.check_of(entry, "SCALE-1")
    assert scale_1.evidence_record_digests[-1] == days[3].seal.kelly_evidence_digest  # SCALE-1 binds the evidence
    payload = governed_paper_day_seal_to_dict(days[1].seal)
    assert set(payload) - set(V12_FIELDS) == set(governed_paper_day_seal_to_dict(legacy[1].seal))
    evidence, verification = rlt.lineage_evidence(days)
    assert (evidence.schema_version, evidence.status) == (V12_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_the_public_gate_replays_the_sealed_kelly_evidence_at_the_exact_r4_fraction_behind_nt_r03() -> None:
    item = kelly_days(4)[3]
    evidence = kelly_gate(item, 3, rlt.risk_context(3))
    assert (evidence.rule_set_id, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_KELLY_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    found = evidence.kelly_evidence
    assert found is not None and found.evidence_digest == item.seal.kelly_evidence_digest
    assert found.risk_evidence_digest == evidence.risk_evidence.evidence_digest  # type: ignore[union-attr]
    for before, sealed in (
        (gpe.instant(3), item.seal.kelly_prefix_digest_open),
        (gpe.instant(4), item.seal.kelly_prefix_digest_close),
    ):
        assert governed_paper_kelly_prefix_digest(found, before_ns=before) == sealed
    risk_readings = {reading.decision_sequence: reading.check("NT-R03") for reading in evidence.risk_evidence.readings}  # type: ignore[union-attr]
    assert found.readings and found.trades == ()  # every entry is refused, so no trade ever opens
    assert set(risk_readings) == {reading.decision_sequence for reading in found.readings}
    for reading in found.readings:
        nt_r03 = risk_readings[reading.decision_sequence]
        if nt_r03.status.value == "BLOCKED":
            assert (reading.rho, reading.rho_reason) == (None, nt_r03.reason)
            assert reading.reason == "KELLY_RISK_FRACTION_UNPROVEN"
        else:
            assert reading.rho == nt_r03.observed  # the exact R-4 fraction NT-R03 renders, never re-parsed
            assert reading.reason == "KELLY_RATIO_UNDEFINED"
        assert reading.status is GovernedPaperKellyStatus.BLOCKED
    legacy = rlt.risk_gate(rlt.risk_days(4)[3], 3, rlt.risk_context(3))  # rule set v10, through the public builders
    assert "kelly_evidence" not in governed_paper_entry_safety_evidence_to_dict(legacy)
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_kelly_evidence$"):
        governed_paper_entry_safety_evidence_to_dict(replace(legacy, kelly_evidence=found))
    v7 = replace(item.seal.schedule, schema_version=V7)
    for schedule, context, kelly, reason in (
        (v7, rlt.risk_context(3), True, "kelly_schedule_and_rule_set_mismatch"),
        (item.seal.schedule, rlt.risk_context(3), False, "kelly_schedule_and_rule_set_mismatch"),
        (item.seal.schedule, None, True, "kelly_without_the_risk_measurement_rule_set"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            kelly_gate(item, 3, context, schedule, kelly)


def test_a_kelly_lineage_is_one_from_day_0_or_never_and_only_on_a_risk_lineage() -> None:
    days, legacy = kelly_days(2), rlt.risk_days(2)
    for item, changes, reason in (
        (days[1], {"kelly": False}, "kelly_reading_lineage_switched"),
        (legacy[1], {"kelly": True}, "kelly_reading_lineage_switched"),
        (days[0], {"risk": None}, "kelly_reading_needs_the_risk_measurement_lineage"),
        (days[1], {"kelly": 1}, "protection_inputs_malformed:kelly"),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), rmt.risk_table(rmt.TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:kelly_evidence_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V11_SEAL)
    for changes in (
        {"kelly_evidence_digest": "0" * 64},
        {"kelly_prefix_digest_open": "0" * 64},
        {"kelly_prefix_digest_close": "0" * 64},
        {"schedule": replace(days[1].seal.schedule, schema_version=V7)},
    ):
        assert rlt.verified(replace(days[1], seal=gpe.reseal_seal(days[1].seal, **changes))).intact is False


def test_on_the_production_table_every_kelly_reading_is_blocked_by_an_unadmitted_risk_policy() -> None:
    days = kelly_days(4, production=True)
    for item in days:
        assert (item.seal.schema_version, item.seal.status) == (V12_SEAL, SEALED)
        assert (item.seal.schedule.schema_version, item.seal.schedule.cvar_bounds) == (V8, ())  # C-10 refuses first
        assert rlt.verified(item, PRODUCTION).intact is True
        assert all(not entry.entry_permitted for entry in item.seal.entry_safety_decisions)
    assert rlt.verified(days[1]).intact is False  # never verified under the TEST-ONLY table
    evidence, verification = rlt.lineage_evidence(days, PRODUCTION)
    assert (evidence.schema_version, evidence.status, verification.intact) == (
        V12_EVIDENCE,
        GovernedPaperExecutionStatus.READY,
        True,
    )
    production = kelly_gate(days[3], 3, rlt.risk_context(3), table=PRODUCTION)
    assert production.evidence_digest == days[3].seal.entry_safety_evidence_digest
    assert production.kelly_evidence.readings  # type: ignore[union-attr]
    for reading in production.kelly_evidence.readings:  # type: ignore[union-attr]
        assert (reading.status, reading.reason, reading.rho, reading.rho_reason) == (
            GovernedPaperKellyStatus.BLOCKED,
            "KELLY_RISK_FRACTION_UNPROVEN",
            None,
            NOT_ADMITTED,
        )


# --- the accepted identities --------------------------------------------------------------------------------------------


def test_the_accepted_v11_seals_v10_rule_set_and_v4_outcome_are_byte_identical() -> None:
    result, world = rmt.hold_v2()
    assert rmt.governed_v7(result, world, rmt.whole_hold(0, 0)).outcome_digest == ACCEPTED_MAIN_HOLD_V7_OUTCOME_DIGEST
    days = rlt.risk_days(2)
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_RISK_SEAL_V11_DIGESTS
    assert tuple(item.seal.risk_evidence_digest for item in days) == ACCEPTED_MAIN_RISK_SEAL_V11_RISK_EVIDENCE_DIGESTS
    assert all(set(V12_FIELDS).isdisjoint(governed_paper_day_seal_to_dict(item.seal)) for item in days)
    evidence, verification = rlt.lineage_evidence(days)
    assert (evidence.evidence_digest, verification.intact) == (ACCEPTED_MAIN_RISK_EVIDENCE_V11_DIGEST, True)
    assert GOVERNED_PAPER_ENTRY_SAFETY_RISK_MEASUREMENT_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V10_DIGEST
