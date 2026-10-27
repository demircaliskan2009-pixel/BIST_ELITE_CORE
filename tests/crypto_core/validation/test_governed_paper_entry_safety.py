"""Governed paper entry safety tests (S1_PAPER_ENTRY_SAFETY_CLOSURE_V1: PRDV4 §1.21 NO-TRADE and §1.9 Family B).

SYNTHETIC TEST VALUES ONLY. Every price, instant, latency, envelope and approval here is a synthetic value that
exercises structure; none is a production threshold, venue truth or a real human decision.

Every governed world in this module runs the PRODUCTION entry gate. Unlike the downstream-mechanics lineage tests,
this module never installs the test-only permissive rule table. It proves:

* the rule set evaluates all 26 NO-TRADE ids PRDV4 §1.21 enumerates (its heading declares 23), in the published
  order, then the seven §1.9 Family B gates, with no override;
* each check enforces its published rule on the inputs the selected path derives, and fails closed otherwise;
* on the selected data contract every S1 entry of world G and of the accepted scenarios is refused (NT-D01 is the
  first non-admitting check), only entries are refused, and the seal and lineage bind exactly that evaluation;
* the test-only permissive table cannot masquerade as the production gate;
* rule set v2 (``PROTECTIVE_POSITION_LIFECYCLE_V1``): with a verified protective context FB-MAX-HOLD and FB-STOP pass
  exactly when the engine enforces them, FB-STOP-TIGHTENING stays blocked (DEC-9), every NO-TRADE id is unchanged and
  rule set v1 keeps its accepted identity;
* a positive ATR that rounds to zero at scale 18 is an explicit BLOCKED FB-STOP, on the public evidence builder and
  across a four-day protective lineage, never an uncaught malformed observation (P2-POSITIVE-ATR-RENDER-ZERO);
* rule set v3 (``S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1``): NT-R02, NT-R03 and NT-R04 are evaluated on the governed
  decision portfolio the one engine derives, at their exact published boundaries and BLOCKED wherever the snapshot
  cannot support a reading; rule sets v1 and v2 keep their accepted identities; a four-day seal v4 lineage of world G
  stays READY with every entry still refused by NT-D01; and in the protective lifecycle world, under a TEST-ONLY
  reading of those three checks alone (no rule table is replaced), a same-day loss beyond 2% refuses the re-entry
  through the sequential admission, which an evaluation on the neutral replay would get wrong.
"""

from __future__ import annotations

import decimal
import functools
import json
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_entry_safety as entry_safety
from crypto_core.validation.edge_artifact_core import EdgeEvidenceStatus, edge_canonical_json, edge_sha256_text
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_digest,
    verify_governed_paper_day_seal,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_NON_CLAIM_FLAGS,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyObservation,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyProtection,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_entry_sequences,
    governed_paper_entry_safety_evidence_digest,
    governed_paper_entry_safety_evidence_to_dict,
    governed_paper_entry_safety_portfolio_facts,
    governed_paper_entry_safety_rule_set_digest,
    governed_paper_entry_safety_sequential_refusals,
)
from crypto_core.validation.governed_paper_execution_authority import governed_paper_genesis_authority
from crypto_core.validation.governed_paper_protective_authority import governed_paper_protective_context
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionFillOutcome,
    HistoricalExecutionProtectiveWindow,
    historical_execution_latest_visible_mark,
    simulate_historical_execution_governed_paper,
    simulate_historical_execution_governed_paper_decision_portfolio,
)
from crypto_core.validation.historical_execution_economics_policy import LATENCY_TIER_PRDV4_T1
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    HistoricalOhlcPriceSemantics,
    build_historical_ohlc_bar,
    build_historical_ohlc_bar_archive,
    historical_ohlc_wilder_atr,
)
from crypto_core.validation.historical_position_management_policy import (
    MAX_HOLD_NS,
    TIGHTENING_DEC9_READING_V1,
    TIGHTENING_NOT_APPLIED_PENDING_DEC9,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_protective_authority as prot
    import test_governed_paper_protective_lineage as lineage
    import test_historical_execution_protective_lifecycle as lifet
    import test_historical_ohlc_bar_archive as ohlct
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_protective_authority as prot
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet
    from tests.crypto_core.validation import test_historical_ohlc_bar_archive as ohlct

_PREFIX = "governed_paper_entry_safety"
S = GovernedPaperEntrySafetyStatus
PRODUCTION_CHECKS = entry_safety._CHECKS  # noqa: SLF001 - captured at import, before any fixture could patch it
NT_IDS = (
    *(f"NT-D0{index}" for index in range(1, 6)),
    *(f"NT-R0{index}" for index in range(1, 7)),
    *(f"NT-M0{index}" for index in range(1, 5)),
    *(f"NT-E0{index}" for index in range(1, 5)),
    *(f"NT-X0{index}" for index in range(1, 5)),
    *(f"NT-T0{index}" for index in range(1, 4)),
)
FB_IDS = (
    "FB-TREND",
    "FB-REGIME",
    "FB-REGIME-COOLDOWN",
    "FB-ANTITREND",
    "FB-MAX-HOLD",
    "FB-STOP",
    "FB-STOP-TIGHTENING",
)
SECOND = 1_000_000_000
G0 = 1_800_000_000 * SECOND  # SYNTHETIC paper engine start for the pure evaluations
T = G0 + 86_400 * SECOND
BLOCKED = S.BLOCKED_ON_MISSING_INPUT
UNREPRESENTABLE = S.BLOCKED_PROTECTION_UNREPRESENTABLE


@pytest.fixture(autouse=True, scope="module")
def _production_gate_with_exact_memos():
    """Only the exact upstream memos (pure re-proofs): the PRODUCTION rule table stays in force throughout."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
        yield


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def d(value: object) -> str:
    return gpe.d(Fraction(value))  # type: ignore[arg-type]


# --- A. the rule set ---------------------------------------------------------------------------------------------------


def test_the_rule_set_evaluates_all_26_enumerated_no_trade_ids_in_order_then_family_b() -> None:
    checks = GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["checks"]
    assert [item["check_id"] for item in checks] == [*NT_IDS, *FB_IDS]  # type: ignore[index, union-attr]
    assert len(NT_IDS) == 26 and len(set(NT_IDS)) == 26 and len(FB_IDS) == 7
    assert [item["family"] for item in checks] == (  # type: ignore[index, union-attr]
        ["DATA"] * 5 + ["RISK"] * 6 + ["REGIME"] * 4 + ["EDGE"] * 4 + ["EXECUTION"] * 4 + ["TEMPORAL"] * 3
    ) + ["FAMILY_B"] * 7
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["prdv4_no_trade_count"] == (
        "heading_declares_23_tables_enumerate_26_ids_every_enumerated_id_is_evaluated"
    )
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["override_rule"] == "none"
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["rule_set_id"] == GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["family_b_profiles"] == ["passive_funding_carry.v1"]
    thresholds = {item["check_id"]: item["threshold"] for item in checks}  # type: ignore[index, union-attr]
    assert thresholds["NT-D02"] == "last_l2_update_age_gt_10s"
    assert thresholds["NT-X01"] == "latency_gt_5x_the_tier_budget_t1_100ms"
    assert thresholds["NT-T01"] == "first_5min_after_the_engine_start"
    assert thresholds["FB-ANTITREND"] == "short_with_r4h_gt_plus_2pct_or_long_with_r4h_lt_minus_2pct"
    assert thresholds["FB-STOP"] == "stop_at_1.5x_atr4h_from_entry"
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST
        == edge_sha256_text(edge_canonical_json(GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET))
        == governed_paper_entry_safety_rule_set_digest()
    )


# --- B. one decision: every check, its published rule and its fail-closed boundary ----------------------------------------


def observation(**changes: object) -> GovernedPaperEntrySafetyObservation:
    """A SYNTHETIC entry observation whose derivable checks all pass (the base of every boundary test)."""

    base = GovernedPaperEntrySafetyObservation(
        decision_sequence=7,
        decision_time_ns=T,
        decision_digest="a" * 64,
        instrument="BTC-USDT-PERP",
        target_direction="SHORT",
        family_b_applicable=True,
        genesis_start_ns=G0,
        latency_tier_id=LATENCY_TIER_PRDV4_T1,
        latency_ns=50_000_000,
        single_instrument_portfolio=True,
        lifecycle_invalidated=False,
        book_update_record_digest="b" * 64,
        book_update_event_time_ns=T - SECOND,
        mark_record_digest="c" * 64,
        mark_price=d(40),
        lookback_mark_record_digest="e" * 64,
        lookback_mark_price=d(40),
    )
    return replace(base, **changes)


def check_of(decision: object, check_id: str):  # noqa: ANN201
    return next(item for item in decision.checks if item.check_id == check_id)  # type: ignore[attr-defined]


EXPECTED_BASE = {
    **dict.fromkeys(NT_IDS, BLOCKED),
    "NT-D02": S.PASS,
    "NT-M04": S.PROVEN_NOT_APPLICABLE,
    "NT-X01": S.PASS,
    "NT-T01": S.PASS,
    "FB-TREND": BLOCKED,
    "FB-REGIME": BLOCKED,
    "FB-REGIME-COOLDOWN": BLOCKED,
    "FB-ANTITREND": S.PASS,
    "FB-MAX-HOLD": UNREPRESENTABLE,
    "FB-STOP": UNREPRESENTABLE,
    "FB-STOP-TIGHTENING": UNREPRESENTABLE,
}


def test_every_check_is_evaluated_in_order_and_the_first_non_admitting_one_refuses_the_entry() -> None:
    decision = evaluate_governed_paper_entry_safety(observation())
    assert [item.check_id for item in decision.checks] == [*NT_IDS, *FB_IDS]
    assert {item.check_id: item.status for item in decision.checks} == EXPECTED_BASE
    published = {item["check_id"]: item["threshold"] for item in GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET["checks"]}  # type: ignore[index, union-attr]
    assert all(item.threshold == published[item.check_id] for item in decision.checks)
    admitting = (S.PASS, S.PROVEN_NOT_APPLICABLE)
    first = next(item for item in decision.checks if item.status not in admitting)
    assert (decision.entry_permitted, decision.first_failure_check_id, decision.first_failure_reason) == (
        False,
        "NT-D01",
        code("NT-D01:trade_and_kline_feeds_not_in_the_selected_data_contract"),
    )
    assert first.check_id == decision.first_failure_check_id and first.reason == decision.first_failure_reason
    assert (decision.decision_sequence, decision.decision_time_ns, decision.instrument, decision.target_direction) == (
        7,
        T,
        "BTC-USDT-PERP",
        "SHORT",
    )
    # a PASS of every derivable check never admits an entry: only absent measurements remain, and none is a pass
    assert all(item.observed == "" for item in decision.checks if item.status in (BLOCKED, UNREPRESENTABLE))


@pytest.mark.parametrize(
    ("check_id", "reason"),
    [
        ("NT-D01", "trade_and_kline_feeds_not_in_the_selected_data_contract"),
        ("NT-D03", "trade_stream_not_in_the_selected_data_contract"),
        ("NT-D04", "index_price_series_not_in_the_selected_data_contract"),
        ("NT-D05", "volume_series_not_in_the_selected_data_contract"),
        ("NT-R01", "kill_switch_ladder_level_not_produced"),
        ("NT-R02", "intraday_portfolio_pnl_and_nav_not_measured_at_the_decision_instant"),
        ("NT-R03", "portfolio_position_risk_not_measured_at_the_decision_instant"),
        ("NT-R04", "portfolio_position_concentration_not_measured_at_the_decision_instant"),
        ("NT-R05", "portfolio_cvar99_not_produced"),
        ("NT-R06", "margin_utilization_not_modeled"),
        ("NT-M01", "liquidity_regime_not_produced"),
        ("NT-M02", "open_interest_and_market_cap_not_in_the_selected_data_contract"),
        ("NT-M03", "regime_hysteresis_state_not_produced"),
        ("NT-E01", "edge_health_score_not_produced"),
        ("NT-E03", "edge_capacity_kmax_and_utilization_not_produced"),
        ("NT-E04", "edge_health_score_not_produced"),
        ("NT-X02", "exchange_order_fill_rate_not_observable_on_the_paper_path"),
        ("NT-X03", "thirty_day_median_spread_needs_proven_complete_book_coverage"),
        ("NT-X04", "exchange_maintenance_schedule_not_produced"),
        ("NT-T02", "kill_switch_cooldown_state_not_produced"),
        ("NT-T03", "macro_event_calendar_not_produced"),
        ("FB-TREND", "trend_strength_ema_atr_construction_not_defined_or_produced"),
        ("FB-REGIME", "regime_state_not_produced"),
        ("FB-REGIME-COOLDOWN", "trending_regime_history_not_produced"),
    ],
)
def test_an_unproduced_measurement_is_blocked_never_read_as_a_pass(check_id: str, reason: str) -> None:
    for direction in ("SHORT", "LONG"):
        check = check_of(evaluate_governed_paper_entry_safety(observation(target_direction=direction)), check_id)
        assert (check.status, check.observed, check.reason, check.evidence_record_digests) == (
            BLOCKED,
            "",
            code(f"{check_id}:{reason}"),
            (),
        )


@pytest.mark.parametrize(
    ("check_id", "reason"),
    [
        ("FB-MAX-HOLD", "holding_period_exit_not_representable_on_the_selected_path"),
        ("FB-STOP", "atr_4h_stop_exit_not_representable_on_the_selected_path"),
        ("FB-STOP-TIGHTENING", "stop_tightening_not_representable_on_the_selected_path"),
    ],
)
def test_a_mandatory_family_b_exit_the_path_cannot_represent_blocks_every_entry(check_id: str, reason: str) -> None:
    for direction in ("SHORT", "LONG"):
        check = check_of(evaluate_governed_paper_entry_safety(observation(target_direction=direction)), check_id)
        assert (check.status, check.reason) == (UNREPRESENTABLE, code(f"{check_id}:{reason}"))


@pytest.mark.parametrize(
    ("event", "status", "reason"),
    [
        (T, S.PASS, "last_l2_update_within_10s"),
        (T - 10 * SECOND, S.PASS, "last_l2_update_within_10s"),
        (T - 10 * SECOND - 1, S.FAIL, "last_l2_update_older_than_10s"),
        (T + 1, BLOCKED, "order_book_update_after_the_decision"),
    ],
)
def test_nt_d02_fails_strictly_above_10_seconds(
    event: int, status: GovernedPaperEntrySafetyStatus, reason: str
) -> None:
    check = check_of(evaluate_governed_paper_entry_safety(observation(book_update_event_time_ns=event)), "NT-D02")
    assert (check.status, check.observed, check.reason) == (status, str(T - event), code(f"NT-D02:{reason}"))
    assert check.evidence_record_digests == ("b" * 64,)
    missing = observation(book_update_event_time_ns=None, book_update_record_digest=None)
    absent = check_of(evaluate_governed_paper_entry_safety(missing), "NT-D02")
    assert (absent.status, absent.observed, absent.reason) == (
        BLOCKED,
        "",
        code("NT-D02:no_order_book_update_visible_at_the_decision_instant"),
    )


@pytest.mark.parametrize(
    ("latency", "status"),
    [(1, S.PASS), (500_000_000, S.PASS), (500_000_001, S.FAIL)],
)
def test_nt_x01_fails_strictly_above_five_times_the_t1_budget(
    latency: int, status: GovernedPaperEntrySafetyStatus
) -> None:
    check = check_of(evaluate_governed_paper_entry_safety(observation(latency_ns=latency)), "NT-X01")
    assert (check.status, check.observed) == (status, str(latency))
    unknown = check_of(evaluate_governed_paper_entry_safety(observation(latency_tier_id="prdv4_t2_standard")), "NT-X01")
    assert (unknown.status, unknown.reason) == (BLOCKED, code("NT-X01:latency_tier_budget_unknown"))


@pytest.mark.parametrize(
    ("elapsed", "status"),
    [(0, S.FAIL), (300 * SECOND - 1, S.FAIL), (300 * SECOND, S.PASS), (86_400 * SECOND, S.PASS)],
)
def test_nt_t01_refuses_the_first_five_minutes_after_the_paper_engine_start(
    elapsed: int, status: GovernedPaperEntrySafetyStatus
) -> None:
    check = check_of(evaluate_governed_paper_entry_safety(observation(decision_time_ns=G0 + elapsed)), "NT-T01")
    assert (check.status, check.observed) == (status, str(elapsed))
    early = check_of(evaluate_governed_paper_entry_safety(observation(genesis_start_ns=T + 1)), "NT-T01")
    assert (early.status, early.reason) == (BLOCKED, code("NT-T01:decision_before_the_paper_engine_start"))


@pytest.mark.parametrize(
    ("direction", "mark", "status"),
    [
        ("SHORT", "40.800000000000000000", S.PASS),  # r_4h = +2% exactly: not strictly above
        ("SHORT", "40.800000000000000001", S.FAIL),
        ("SHORT", "20.000000000000000000", S.PASS),  # a SHORT into a falling price is not anti-trend
        ("LONG", "39.200000000000000000", S.PASS),  # r_4h = -2% exactly: not strictly below
        ("LONG", "39.199999999999999999", S.FAIL),
        ("LONG", "60.000000000000000000", S.PASS),  # a LONG into a rising price is not anti-trend
    ],
)
def test_fb_antitrend_blocks_an_entry_against_a_2pct_4h_move_and_is_never_overridden(
    direction: str, mark: str, status: GovernedPaperEntrySafetyStatus
) -> None:
    decision = evaluate_governed_paper_entry_safety(observation(target_direction=direction, mark_price=mark))
    check = check_of(decision, "FB-ANTITREND")
    move = Fraction(mark) / 40 - 1
    assert (check.status, check.observed) == (status, gpe.d(move))
    assert check.evidence_record_digests == ("e" * 64, "c" * 64)
    expected = (
        "anti_trend_entry_blocked_and_override_unprovable" if status is S.FAIL else "anti_trend_bound_not_crossed"
    )
    assert check.reason == code(f"FB-ANTITREND:{expected}")


def test_fb_antitrend_needs_both_marks_and_family_b_needs_an_established_applicability() -> None:
    for changes, reason in (
        ({"mark_price": None, "mark_record_digest": None}, "mark_unavailable_at_the_decision_instant"),
        (
            {"lookback_mark_price": None, "lookback_mark_record_digest": None},
            "mark_unavailable_4h_before_the_decision_instant",
        ),
    ):
        check = check_of(evaluate_governed_paper_entry_safety(observation(**changes)), "FB-ANTITREND")
        assert (check.status, check.reason) == (BLOCKED, code(f"FB-ANTITREND:{reason}"))
    undetermined = evaluate_governed_paper_entry_safety(observation(family_b_applicable=False))
    for check_id in FB_IDS:
        assert (check_of(undetermined, check_id).status, check_of(undetermined, check_id).reason) == (
            BLOCKED,
            code(f"{check_id}:family_b_applicability_undetermined"),
        )


def test_nt_e02_and_nt_m04_report_only_what_the_path_proves() -> None:
    disabled = check_of(evaluate_governed_paper_entry_safety(observation(lifecycle_invalidated=True)), "NT-E02")
    assert (disabled.status, disabled.observed, disabled.reason) == (
        S.FAIL,
        "EF8_DISABLED_OR_QUARANTINE",
        code("NT-E02:edge_lifecycle_disabled_at_or_before_the_decision"),
    )
    active = check_of(evaluate_governed_paper_entry_safety(observation()), "NT-E02")
    assert (active.status, active.reason) == (BLOCKED, code("NT-E02:prdv4_edge_state_machine_not_produced"))
    single = check_of(evaluate_governed_paper_entry_safety(observation()), "NT-M04")
    assert (single.status, single.reason) == (
        S.PROVEN_NOT_APPLICABLE,
        code("NT-M04:single_instrument_paper_portfolio_has_no_pairwise_correlation"),
    )
    several = check_of(evaluate_governed_paper_entry_safety(observation(single_instrument_portfolio=False)), "NT-M04")
    assert (several.status, several.reason) == (BLOCKED, code("NT-M04:cross_asset_correlation_not_measured"))


@pytest.mark.parametrize(
    ("changes", "name"),
    [
        ({"decision_sequence": True}, "decision_sequence"),
        ({"decision_time_ns": -1}, "decision_time_ns"),
        ({"latency_ns": 1.0}, "latency_ns"),
        ({"decision_digest": "A" * 64}, "decision_digest"),
        ({"instrument": ""}, "instrument"),
        ({"target_direction": "FLAT"}, "target_direction"),
        ({"family_b_applicable": 1}, "family_b_applicable"),
        ({"lifecycle_invalidated": None}, "lifecycle_invalidated"),
        ({"book_update_event_time_ns": False}, "book_update_event_time_ns"),
        ({"mark_record_digest": "x"}, "mark_record_digest"),
        ({"mark_price": "40"}, "mark_price"),
        ({"lookback_mark_price": d(0)}, "lookback_mark_price"),
    ],
)
def test_a_malformed_observation_is_refused_never_evaluated(changes: dict[str, object], name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(observation(**changes))
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code('observation_malformed')}$"):
        evaluate_governed_paper_entry_safety(object())  # type: ignore[arg-type]


def test_an_evaluation_is_deterministic_and_independent_of_the_ambient_decimal_context() -> None:
    base = observation(mark_price="40.812345678901234567", target_direction="SHORT")
    reference = evaluate_governed_paper_entry_safety(base)
    for precision in (1, 2, 6, 28):
        for rounding in (decimal.ROUND_HALF_EVEN, decimal.ROUND_DOWN, decimal.ROUND_UP, decimal.ROUND_FLOOR):
            with decimal.localcontext() as context:
                context.prec, context.rounding = precision, rounding
                assert evaluate_governed_paper_entry_safety(base) == reference
    assert check_of(reference, "FB-ANTITREND").observed == gpe.d(Fraction("40.812345678901234567") / 40 - 1)


# --- C. the production gate on the accepted synthetic worlds ---------------------------------------------------------------

_GATED: dict[tuple[str, int], tuple] = {}


def gated_days(name: str, count: int) -> tuple:
    """The first ``count`` days of scenario ``name`` under the PRODUCTION gate (never the shared permissive cache)."""

    key = (name, count)
    if key not in _GATED:
        if count == 0:
            _GATED[key] = ()
        else:
            days = gated_days(name, count - 1)
            _GATED[key] = (*days, gpe.next_day(days, gpe.scenario(name)))
    return _GATED[key]


def run_and_evidence(item: object):  # noqa: ANN201
    """The day's decision run and its entry-safety evidence, rebuilt independently through the public builders."""

    inputs = item.seal_inputs  # type: ignore[attr-defined]
    # through the module attribute: the exact identity memo of ``gpe.apply_memos`` (a pure re-proof of the same objects)
    authority = gpe.authority.governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
    genesis = authority.genesis
    run = gpe.execution.build_historical_decision_run(
        inputs.dataset,
        authority.executable_binding,
        expected_dataset_digest=inputs.dataset.dataset_digest,
        expected_executable_binding_digest=genesis.executable_binding_digest,
        run_id=f"{inputs.seal_id}-run",
        correlation_id=inputs.correlation_id,
        parameter_assignment=authority.parameter_assignment,
        instrument=genesis.instrument,
        evaluation_start_ns=genesis.genesis_start_ns,
        evaluation_end_ns=item.seal.window_end_ns,  # type: ignore[attr-defined]
        parameter_approval=authority.parameter_approval,
    )
    evidence = build_governed_paper_entry_safety_evidence(
        authority=authority,
        run=run,
        dataset=inputs.dataset,
        invalidated_from_ns=item.seal.invalidated_from_ns,  # type: ignore[attr-defined]
    )
    return authority, run, evidence


def entry_outcomes(item: object) -> list[tuple[int, str, str]]:
    """``(decision sequence, outcome, reason)`` of every fill record of an intent that would open from flat."""

    outcome = gpe.replay_of(item)[1]  # type: ignore[arg-type]
    opening = {
        entry.intent_id: entry.decision_sequence for entry in outcome.intents if Fraction(entry.actual_quantity) == 0
    }
    return [
        (opening[fill.intent_id], fill.outcome.value, fill.reason)
        for fill in outcome.fills
        if fill.intent_id in opening
    ]


def test_the_production_gate_refuses_every_entry_of_world_g_and_the_lineage_stays_ready() -> None:
    days = gated_days("G", 6)
    evaluated = [decision for item in days for decision in item.seal.entry_safety_decisions]
    assert [decision.target_direction for decision in evaluated] == ["SHORT", "SHORT"]  # day 3 entry, day 5 re-entry
    for decision in evaluated:
        assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-D01")
    for item in days:
        seal = item.seal
        assert (seal.status, seal.episodes, seal.funding_events) == (GovernedPaperDaySealStatus.SEALED, (), ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST
        assert seal.schedule.entry_refused_decision_sequences == tuple(
            decision.decision_sequence for decision in evaluated if decision.decision_time_ns < seal.window_end_ns
        )
        verification = verify_governed_paper_day_seal(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    outcomes = entry_outcomes(days[-1])
    assert outcomes and all(item[1:] == ("REJECTED", "governed_paper_entry_safety_refused") for item in outcomes)
    assert sorted({item[0] for item in outcomes}) == [decision.decision_sequence for decision in evaluated]
    assert days[-1].seal.governance_rejected_fill_count == len(outcomes)
    assert days[-1].seal.pending_decision_sequence is None
    evidence = build_governed_paper_execution_evidence(gpe.evidence_inputs(days))
    assert (evidence.status, evidence.terminal_episode_count, evidence.terminal_funding_event_count) == (
        GovernedPaperExecutionStatus.READY,
        0,
        0,
    )
    assert all(item.cycle_phase == "BOOTSTRAP_B0" for item in evidence.days)
    verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_world_g_entries_are_evaluated_on_the_derived_point_in_time_inputs() -> None:
    days = gated_days("G", 6)
    world = gpe.scenario("G")
    authority = governed_paper_genesis_authority(world.genesis, world.genesis_inputs)
    policy = authority.economics_policy
    for item in days:
        dataset = item.seal_inputs.dataset
        for decision in item.seal.entry_safety_decisions:
            instant = decision.decision_time_ns
            statuses = {check.check_id: check.status for check in decision.checks}
            assert {
                key: value for key, value in statuses.items() if key not in ("NT-D02", "NT-X01", "FB-ANTITREND")
            } == {key: value for key, value in EXPECTED_BASE.items() if key not in ("NT-D02", "NT-X01", "FB-ANTITREND")}
            # NT-D02: the latest book visible at the decision is the previous funding cycle's, two days old
            book = check_of(decision, "NT-D02")
            assert (book.status, book.observed) == (S.FAIL, str(gpe.FUNDING - 490))
            latency = check_of(decision, "NT-X01")
            assert latency.observed == str(policy.latency_ns)
            assert latency.status is (S.FAIL if policy.latency_ns > 500_000_000 else S.PASS)
            # FB-ANTITREND: exactly the engine's own visible marks at t and t - 4h
            now = historical_execution_latest_visible_mark(dataset, policy=policy, instrument=gpe.INS, at_ns=instant)
            then = historical_execution_latest_visible_mark(
                dataset, policy=policy, instrument=gpe.INS, at_ns=instant - 4 * 3600 * SECOND
            )
            anti = check_of(decision, "FB-ANTITREND")
            if now is None or then is None:
                assert anti.status is BLOCKED
            else:
                move = Fraction(now[1]) / Fraction(then[1]) - 1
                assert anti.observed == gpe.d(move) and anti.evidence_record_digests == (then[0], now[0])
                assert anti.status is (S.FAIL if move > Fraction(2, 100) else S.PASS)


def test_the_seal_carries_exactly_its_derived_entry_safety_evaluation() -> None:
    days = gated_days("G", 6)
    item = days[3]
    _, run, evidence = run_and_evidence(item)
    seal = item.seal
    assert seal.entry_safety_evidence_digest == evidence.evidence_digest
    assert governed_paper_entry_safety_evidence_digest(evidence) == evidence.evidence_digest
    assert seal.entry_safety_decisions == tuple(
        decision
        for decision in evidence.decisions
        if seal.window_start_ns <= decision.decision_time_ns < seal.window_end_ns
    )
    assert seal.schedule.entry_refused_decision_sequences == evidence.refused_decision_sequences
    assert evidence.refused_decision_sequences == tuple(
        decision.decision_sequence for decision in run.decisions if decision.resulting_direction != "FLAT"
    )
    assert (evidence.rule_set_id, evidence.rule_set_digest, evidence.profile_id, evidence.family_b_applicable) == (
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_ID,
        GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST,
        "passive_funding_carry.v1",
        True,
    )
    payload = governed_paper_entry_safety_evidence_to_dict(evidence)
    assert (
        json.loads(edge_canonical_json(payload)) == payload and payload["evidence_digest"] == evidence.evidence_digest
    )
    flags = dict(GOVERNED_PAPER_ENTRY_SAFETY_NON_CLAIM_FLAGS)
    assert {name: getattr(evidence, name) for name in flags} == flags
    # the earlier seals carry exactly the earlier decisions: the evaluation of a sealed decision never changes
    assert days[5].seal.entry_safety_decisions and days[4].seal.entry_safety_decisions == ()
    assert run_and_evidence(days[5])[2].decisions[: len(evidence.decisions)] == evidence.decisions


GATE = "governed_paper_entry_safety_refused"


@pytest.mark.parametrize(
    ("name", "reasons"),
    [
        ("long", {GATE}),
        ("b50-long", {GATE}),
        ("delay", {GATE}),
        ("flip", {GATE}),
        ("stop", {GATE}),
        # an earlier governance refusal decides the engine reason; the gate still evaluates and refuses the entry
        ("b50-short", {"governed_paper_direction_not_authorized"}),
        ("rejected", {"governed_paper_no_cycle_authority"}),
        ("kill-10", {"governed_paper_lifecycle_invalidated", "governed_paper_no_cycle_authority"}),
    ],
)
def test_no_accepted_synthetic_world_opens_an_entry_under_the_production_gate(name: str, reasons: set[str]) -> None:
    days = gated_days(name, 5)  # through day 4: every scenario's first entry decision is on day 3
    evaluated = [decision for item in days for decision in item.seal.entry_safety_decisions]
    assert evaluated and all(
        not decision.entry_permitted and decision.first_failure_check_id == "NT-D01" for decision in evaluated
    )
    assert all(item.seal.status is GovernedPaperDaySealStatus.SEALED for item in days)
    assert all(item.seal.episodes == () and item.seal.funding_events == () for item in days)
    outcomes = entry_outcomes(days[-1])
    assert outcomes and all(item[1] == "REJECTED" for item in outcomes)
    assert {item[2] for item in outcomes} <= reasons and outcomes[0][2] in reasons
    if name == "kill-10":  # the kill takes effect at the day-3 decision instant: NT-E02 FAILs on the evidence too
        assert check_of(evaluated[0], "NT-E02").status is S.FAIL
    direction = "LONG" if name in ("long", "b50-long") else "SHORT"
    assert {decision.target_direction for decision in evaluated} == {direction}


def test_a_forged_entry_safety_fact_never_verifies_even_resealed() -> None:
    item = gated_days("G", 4)[3]
    seal, inputs = item.seal, item.seal_inputs
    decision = seal.entry_safety_decisions[0]
    permitted = replace(decision, entry_permitted=True, first_failure_check_id="", first_failure_reason="")
    for changes in (
        {"entry_safety_decisions": ()},
        {"entry_safety_decisions": (permitted,)},
        {"entry_safety_evidence_digest": "0" * 64},
        {"entry_safety_rule_set_digest": "0" * 64},
        {"schedule": replace(seal.schedule, entry_refused_decision_sequences=())},
    ):
        for forged in (replace(seal, **changes), gpe.reseal_seal(seal, **changes)):
            assert verify_governed_paper_day_seal(forged, inputs).intact is False
    assert governed_paper_day_seal_digest(seal) == seal.seal_digest


def test_a_blocked_day_carries_no_entry_safety_fact_and_keeps_its_opening_schedule() -> None:
    item = gated_days("G", 4)[3]
    synthetic = gpe.rg7t.head_inputs(
        gpe.ef8t.genesis(), evaluation_end_ns=gpe.instant(4), authority_id="gpe-head-synthetic", approval=None
    )
    synthetic = replace(synthetic, approval=gpe.rg7t.approval_for(synthetic, kind=gpe.rg7t.SYNTHETIC))
    seal = gpe.rebuilt_seal(
        item,
        closing_head_authority_inputs=synthetic,
        closing_head_authority=gpe.build_paper_lifecycle_head_authority(synthetic),
    )
    assert seal.status is GovernedPaperDaySealStatus.BLOCKED
    assert (seal.entry_safety_rule_set_digest, seal.entry_safety_evidence_digest, seal.entry_safety_decisions) == (
        "",
        "",
        (),
    )
    assert seal.schedule.entry_refused_decision_sequences == ()
    assert (seal.schedule.windows, seal.schedule.invalidated_from_ns) == (
        item.seal.schedule.windows,
        item.seal.schedule.invalidated_from_ns,
    )
    assert item.seal.schedule.entry_refused_decision_sequences  # the sealed day ran under the completed schedule


def test_an_archive_the_economics_cannot_compute_keeps_its_blocked_day_and_the_gate_never_raises_first() -> None:
    """A mark visible at the day-3 decision (not at the cycle opening) that lacks its ``mark_price`` value.

    The archive stays authentic and READY and the funding decision run still passes, but the economics cannot compute
    over it, so the day is BLOCKED exactly as before the gate existed: the gate runs only after the economics, so its
    visible-mark rule never raises over an archive whose blocked day the seal must represent.
    """

    item = gated_days("G", 4)[3]
    decision_ns = item.seal.entry_safety_decisions[0].decision_time_ns
    day = (item.seal.window_start_ns - gpe.S0) // gpe.DAY
    stray = gpe._record(  # noqa: SLF001 - the shared SYNTHETIC record helper
        "mark",
        "mark_price",
        100_000 + day,
        decision_ns - 5,
        decision_ns - 3,
        {"index_price": gpe.d(gpe.paper_mark(day))},
    )
    assert stray.event_time_ns > item.seal.window_start_ns  # invisible at E_3: the opening quote is unchanged
    # a later mark would precede the stray's sequence (marks are sequenced by day); the archive need not be complete
    kept = [
        record
        for record in item.seal_inputs.dataset.records
        if not (record.series_id == "mark" and record.event_time_ns > stray.event_time_ns)
    ]
    malformed = gpe.archive_of("paper-archive-G-3-stray-mark", (*kept, stray))
    assert (malformed.status, malformed.advances) == (EdgeEvidenceStatus.READY, True)
    seal = gpe.rebuilt_seal(item, dataset=malformed)
    assert seal.status is GovernedPaperDaySealStatus.BLOCKED
    assert len(seal.reason_codes) == 1 and seal.reason_codes[0].startswith(gpe.code("economics_not_computed:"))
    assert (seal.entry_safety_decisions, seal.schedule.entry_refused_decision_sequences) == ((), ())
    assert verify_governed_paper_day_seal(seal, replace(item.seal_inputs, dataset=malformed)).intact is True


def test_the_evidence_builder_refuses_a_foreign_unready_or_malformed_input() -> None:
    item = gated_days("G", 4)[3]
    authority, run, _ = run_and_evidence(item)
    dataset = item.seal_inputs.dataset
    for arguments, reason in (
        ({"authority": object()}, "genesis_authority_malformed"),
        ({"run": object()}, "decision_run_or_archive_malformed"),
        ({"dataset": object()}, "decision_run_or_archive_malformed"),
        ({"invalidated_from_ns": True}, "invalidated_from_ns_invalid"),
        ({"run": replace(run, status=EdgeEvidenceStatus.REJECTED)}, "decision_run_not_ready"),
        ({"dataset": gpe.archive(2)}, "decision_run_or_archive_not_of_the_genesis"),
        ({"run": replace(run, instrument="ETH-USDT-PERP")}, "decision_run_or_archive_not_of_the_genesis"),
    ):
        values = {"authority": authority, "run": run, "dataset": dataset, "invalidated_from_ns": None, **arguments}
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code(reason)}$"):
            build_governed_paper_entry_safety_evidence(**values)  # type: ignore[arg-type]


def test_an_exit_is_never_refused_on_the_governed_engine_even_when_its_decision_is_listed() -> None:
    """Listing the decision of an exit never refuses it: the engine refuses only a magnitude-increasing intent."""

    item = gated_days("G", 8)[7]
    economics, _ = gpe.replay_of(item)  # the historical run: SHORT entry on day 3, exit on day 7
    entries = tuple(
        sorted(entry.decision_sequence for entry in economics.intents if Fraction(entry.actual_quantity) == 0)
    )
    exits = tuple(
        sorted(entry.decision_sequence for entry in economics.intents if Fraction(entry.actual_quantity) != 0)
    )
    assert entries and exits
    listed = simulate_historical_execution_governed_paper(
        economics,
        expected_result_digest=economics.result_digest,
        schedule=replace(item.seal.schedule, entry_refused_decision_sequences=exits),
    )
    exit_fills = [
        fill
        for fill in listed.fills
        if next(entry for entry in listed.intents if entry.intent_id == fill.intent_id).decision_sequence in exits
    ]
    assert exit_fills and all(fill.outcome.value in ("FILLED", "PARTIALLY_FILLED") for fill in exit_fills)
    assert GATE not in {fill.reason for fill in listed.fills}
    # the seal's own schedule lists every evaluated decision: nothing ever opens, so there is nothing to exit
    sealed = gpe.replay_of(item)[1]
    assert sealed.position_transitions == () and {fill.reason for fill in sealed.fills} == {GATE}


def test_the_test_only_permissive_table_cannot_masquerade_as_the_production_gate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(entry_safety, "_CHECKS", gpe.TEST_ONLY_PERMISSIVE_ENTRY_CHECKS)
    days: tuple = ()
    for _ in range(4):
        days = (*days, gpe.next_day(days, gpe.scenario("G")))
    substituted = days[3].seal
    assert substituted.episodes and substituted.schedule.entry_refused_decision_sequences == ()
    assert substituted.entry_safety_rule_set_digest != GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST
    monkeypatch.undo()
    assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
    gpe.CONTRACT_MEMO_ENABLED[0] = False
    try:
        assert verify_governed_paper_day_seal(substituted, days[3].seal_inputs).intact is False
    finally:
        gpe.CONTRACT_MEMO_ENABLED[0] = True
    assert gated_days("G", 4)[3].seal.episodes == ()


# --- D. rule set v2: the protective context (PROTECTIVE_POSITION_LIFECYCLE_V1) ---------------------------------------------

# The accepted-main identity of rule set v1 (main 8a5b7560): this contract never changes it.
ACCEPTED_MAIN_RULE_SET_V1_DIGEST = "c6c1647f434f6b7e3f52b69f142aedc0d79b7a90128bc9f4e5f4a3a84366d023"
AUTHORITY = "f" * 64
ATR_WINDOW = "9" * 64


def protected(**changes: object) -> GovernedPaperEntrySafetyObservation:
    """A SYNTHETIC entry observation under a protective context whose window covers the horizon and whose ATR exists."""

    values: dict[str, object] = {
        "protection_present": True,
        "protective_window_covers": True,
        "protective_authority_digest": AUTHORITY,
        "atr_available": True,
        "atr_value": d("0.4"),
        "atr_reason": "",
        "atr_window_digest": ATR_WINDOW,
        "stop_tightening_method_id": TIGHTENING_NOT_APPLIED_PENDING_DEC9,
    }
    values.update(changes)
    return observation(**values)


def test_rule_set_v1_keeps_its_accepted_identity_and_v2_adds_only_its_protective_rule() -> None:
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V1_DIGEST
    assert governed_paper_entry_safety_rule_set_digest() == ACCEPTED_MAIN_RULE_SET_V1_DIGEST
    v1, v2 = GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET
    assert (v2["rule_set_id"], GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID) == (
        "governed-paper-entry-safety.v2",
    ) * 2
    assert v2["checks"] == v1["checks"] and v2["authorities"] == v1["authorities"]
    assert set(v2) - set(v1) == {"protective_rule"}
    assert v2["protective_rule"]["max_hold_ns"] == MAX_HOLD_NS  # type: ignore[index]
    assert GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST == edge_sha256_text(edge_canonical_json(v2))
    assert GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST != ACCEPTED_MAIN_RULE_SET_V1_DIGEST


def test_a_protective_context_passes_max_hold_and_stop_only_and_every_no_trade_id_is_unchanged() -> None:
    for direction in ("SHORT", "LONG"):
        decision = evaluate_governed_paper_entry_safety(protected(target_direction=direction))
        statuses = {item.check_id: item.status for item in decision.checks}
        assert statuses == {**EXPECTED_BASE, "FB-MAX-HOLD": S.PASS, "FB-STOP": S.PASS}
        hold, stop, tighten = (check_of(decision, name) for name in ("FB-MAX-HOLD", "FB-STOP", "FB-STOP-TIGHTENING"))
        assert (hold.reason, hold.evidence_record_digests) == (
            code("FB-MAX-HOLD:max_hold_close_only_obligation_enforced_by_the_engine"),
            (AUTHORITY,),
        )
        assert (stop.observed, stop.reason, stop.evidence_record_digests) == (
            d("0.4"),
            code("FB-STOP:atr_4h_stop_enforced_by_the_engine"),
            (AUTHORITY, ATR_WINDOW),
        )
        assert (tighten.status, tighten.reason) == (
            UNREPRESENTABLE,
            code("FB-STOP-TIGHTENING:stop_tightening_not_applied_pending_dec9"),
        )
        # the entry stays refused: NT-D01 is still the first non-admitting check
        assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-D01")


def test_an_uncovered_horizon_an_unavailable_atr_or_the_dec9_reading_never_passes() -> None:
    uncovered = evaluate_governed_paper_entry_safety(
        protected(protective_window_covers=False, protective_authority_digest=None)
    )
    for name in ("FB-MAX-HOLD", "FB-STOP"):
        check = check_of(uncovered, name)
        assert (check.status, check.reason) == (
            UNREPRESENTABLE,
            code(f"{name}:protective_authority_does_not_cover_the_holding_horizon"),
        )
    stale = evaluate_governed_paper_entry_safety(
        protected(atr_available=False, atr_value=None, atr_window_digest=None, atr_reason="atr_bar_stale")
    )
    assert check_of(stale, "FB-MAX-HOLD").status is S.PASS
    stop = check_of(stale, "FB-STOP")
    assert (stop.status, stop.observed, stop.reason) == (BLOCKED, "", code("FB-STOP:atr_4h_unavailable:atr_bar_stale"))
    dec9 = check_of(
        evaluate_governed_paper_entry_safety(protected(stop_tightening_method_id=TIGHTENING_DEC9_READING_V1)),
        "FB-STOP-TIGHTENING",
    )
    assert (dec9.status, dec9.reason) == (
        UNREPRESENTABLE,
        code("FB-STOP-TIGHTENING:dec9_tightening_reading_requires_human_approval"),
    )


@pytest.mark.parametrize(
    ("changes", "name"),
    [
        ({"protection_present": False}, "protective_facts_without_a_protective_context"),
        ({"atr_reason": "atr_bar_stale"}, "atr_reading_inconsistent"),
        ({"atr_value": None}, "atr_reading_inconsistent"),
        ({"protective_authority_digest": None}, "protective_window_without_authority"),
        ({"stop_tightening_method_id": None}, "stop_tightening_method_id"),
        ({"atr_value": "0.000000000000000000"}, "atr_value"),
        ({"protection_present": 1}, "protection_present"),
    ],
)
def test_malformed_protective_facts_are_refused(changes: dict[str, object], name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(protected(**changes))


def world_protection(window_end_ns: int, **changes: object) -> GovernedPaperEntrySafetyProtection:
    values: dict[str, object] = {
        "position_management_policy": prot.pm_policy(),
        "ohlc_archive": prot.world_ohlc(3),
        "protective_window": HistoricalExecutionProtectiveWindow(gpe.G, window_end_ns, AUTHORITY),
    }
    values.update(changes)
    return GovernedPaperEntrySafetyProtection(**values)  # type: ignore[arg-type]


def test_world_g_entries_are_evaluated_against_the_engine_horizon_and_atr() -> None:
    item = gated_days("G", 4)[3]
    authority, run, _ = run_and_evidence(item)
    instant = gpe.instant(3) + 10  # the day-3 entry decision
    horizon = instant + MAX_HOLD_NS + 2 * authority.economics_policy.max_execution_delay_ns

    def evaluated(protection: GovernedPaperEntrySafetyProtection):  # noqa: ANN202
        evidence = build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,
            invalidated_from_ns=None,
            protection=protection,
        )
        (entry,) = [decision for decision in evidence.decisions if decision.decision_time_ns == instant]
        return evidence, entry

    evidence, entry = evaluated(world_protection(horizon + 1))
    assert (evidence.rule_set_id, evidence.rule_set_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_ID,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST,
    )
    stop = check_of(entry, "FB-STOP")
    assert (check_of(entry, "FB-MAX-HOLD").status, stop.status, stop.observed) == (S.PASS, S.PASS, d("0.4"))
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    # the horizon must lie strictly inside the window: ending exactly at it never covers the obligation
    _, boundary = evaluated(world_protection(horizon))
    assert check_of(boundary, "FB-MAX-HOLD").status is UNREPRESENTABLE
    _, absent = evaluated(world_protection(horizon + 1, protective_window=None))
    assert check_of(absent, "FB-STOP").reason == code("FB-STOP:protective_authority_does_not_cover_the_holding_horizon")
    last_trade = prot.world_ohlc(3, source=prot.ohlc_source(price_semantics=HistoricalOhlcPriceSemantics.LAST_TRADE))
    with pytest.raises(GovernedPaperEntrySafetyError, match=code("protection_archive_not_of_the_policy")):
        evaluated(world_protection(horizon + 1, ohlc_archive=last_trade))


# --- E. a positive ATR that rounds to zero at scale 18 (P2-POSITIVE-ATR-RENDER-ZERO) -----------------------------------------

ROUNDS_TO_ZERO = code("FB-STOP:atr_4h_unavailable:atr_rounds_to_zero")


@functools.cache
def tiny_world_bar(k: int):  # noqa: ANN201
    """SYNTHETIC 4 h bar ``k`` of world G: open == high == close == 40; bar FIRST_BAR + 1 alone dips one scale-18 unit."""

    opened = gpe.G + k * prot.H4
    low = Fraction(40) - Fraction(1, 10**18) if k == prot.FIRST_BAR + 1 else Fraction(40)
    return build_historical_ohlc_bar(
        interval_ns=prot.H4,
        open_time_ns=opened,
        open_price=d(40),
        high_price=d(40),
        low_price=d(low),
        close_price=d(40),
        available_at_ns=opened + prot.H4 + prot.SECOND,
        finalized_at_ns=opened + prot.H4 + prot.SECOND,
    )


@functools.cache
def tiny_world_ohlc(day: int) -> HistoricalOhlcBarArchive:
    """World G's archive sealed at E_(day + 1), with ONE true range of one unit: a positive ATR rendering as zero."""

    end = gpe.instant(day + 1)
    bars = tuple(
        tiny_world_bar(k)
        for k in range(prot.FIRST_BAR, 6 * (day + 1))
        if max(tiny_world_bar(k).available_at_ns, tiny_world_bar(k).finalized_at_ns) <= end
    )
    return build_historical_ohlc_bar_archive(archive_id=f"ohlc-g-tiny-{day}", source=prot.ohlc_source(), bars=bars)


def test_a_positive_atr_rounding_to_zero_blocks_fb_stop_on_the_public_evidence_builder() -> None:
    assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001 - the production table, never the permissive one
    item = gated_days("G", 4)[3]
    authority, run, _ = run_and_evidence(item)
    instant = gpe.instant(3) + 10  # the day-3 entry decision
    archive = tiny_world_ohlc(3)
    policy = prot.pm_policy()
    reading = historical_ohlc_wilder_atr(
        archive, interval_ns=policy.atr_interval_ns, at_ns=instant, max_bar_age_ns=policy.atr_max_bar_age_ns
    )
    visible = tuple(bar for bar in archive.bars if max(bar.available_at_ns, bar.finalized_at_ns) <= instant)
    exact = ohlct.wilder_oracle(visible)  # the independent oracle: strictly positive, rendered zero
    assert exact > 0 and d(exact) == d(0)
    assert (reading.available, reading.reason, reading.value, reading.rendered_value, reading.window_digest) == (
        False,
        "atr_rounds_to_zero",
        None,
        None,
        None,
    )
    assert reading.run_bar_count == len(visible)
    horizon = instant + MAX_HOLD_NS + 2 * authority.economics_policy.max_execution_delay_ns
    evidence = build_governed_paper_entry_safety_evidence(
        authority=authority,
        run=run,
        dataset=item.seal_inputs.dataset,
        invalidated_from_ns=None,
        protection=world_protection(horizon + 1, ohlc_archive=archive),
    )
    (entry,) = [decision for decision in evidence.decisions if decision.decision_time_ns == instant]
    stop = check_of(entry, "FB-STOP")
    assert (stop.status, stop.observed, stop.reason, stop.evidence_record_digests) == (BLOCKED, "", ROUNDS_TO_ZERO, ())
    assert check_of(entry, "FB-MAX-HOLD").status is S.PASS
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")


def test_a_four_day_protective_lineage_with_a_rounding_to_zero_atr_seals_every_day_on_the_production_table() -> None:
    assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001 - the production table, never the permissive one
    days: tuple = ()
    for day in range(4):  # days 0, 1 and 2 hold no entry; day 3 evaluates world G's SHORT entry
        days = (*days, lineage.protective_day(days, archive=tiny_world_ohlc(day)))
    for item in days:
        seal = item.seal
        assert (seal.status, seal.reason_codes, seal.episodes) == (GovernedPaperDaySealStatus.SEALED, (), ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST
        assert seal.ohlc_archive_digest == tiny_world_ohlc(seal.day_index).archive_digest
        verification = verify_governed_paper_day_seal(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    (entry,) = days[3].seal.entry_safety_decisions
    stop = check_of(entry, "FB-STOP")
    assert (stop.status, stop.reason) == (BLOCKED, ROUNDS_TO_ZERO)
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")
    assert days[3].seal.close_position_quantity == gpe.d(0) and days[3].seal.day_protective_obligation_count == 0
    evidence = lineage.evidence_of(days)
    assert (evidence.status, evidence.terminal_episode_count) == (GovernedPaperExecutionStatus.READY, 0)
    verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days, gpe.scenario("G")))
    assert (verification.intact, verification.reason_codes) == (True, ())


# --- F. rule set v3: the native governed portfolio (S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1) -------------------------------

# The accepted-main identity of rule set v2 (main 99518b37) and the identity of the rule set v3 this contract adds.
ACCEPTED_MAIN_RULE_SET_V2_DIGEST = "5988c063ede8d42648b608c2649f92ca51c66719eccf81f499490088534c3ac2"
RULE_SET_V3_DIGEST = "b04336551becd1e6c7b5e070545d015473081280230a09b65510b2c97f67c552"
PORTFOLIO_IDS = ("NT-R02", "NT-R03", "NT-R04")
SNAPSHOT = "8" * 64
POSITION_MARK = "7" * 64
DAY_NS = 86_400 * SECOND
DAY_START = T // DAY_NS * DAY_NS  # the UTC midnight that starts the day of T
FLAT_PASS = {
    "NT-R02": (S.PASS, "intraday_loss_within_2pct_of_the_day_start_nav"),
    "NT-R03": (S.PASS, "no_position_and_no_order_in_flight_carry_risk"),
    "NT-R04": (S.PASS, "single_position_within_25pct_of_nav"),
}
OPEN_RISK = (BLOCKED, "position_risk_measure_undefined_for_an_open_position")
UNMEASURED = ("paper_portfolio_holds_more_than_the_genesis_sleeve", "governed_portfolio_not_computed")


def portfolio(**changes: object) -> GovernedPaperEntrySafetyObservation:
    """A SYNTHETIC rule set v3 entry observation: flat, NAV 10000 and day-start NAV 10000 on one governed snapshot."""

    values: dict[str, object] = {
        "portfolio_present": True,
        "portfolio_snapshot_digest": SNAPSHOT,
        "position_quantity": d(0),
        "order_in_flight": False,
        "position_mark_record_digest": None,
        "position_mark_price": None,
        "portfolio_nav": d(10_000),
        "day_start_ns": DAY_START,
        "day_start_nav": d(10_000),
        "day_start_reason": "",
    }
    values.update(changes)
    return protected(**values)


def held(quantity: object = -1, mark: object = 40, **changes: object) -> GovernedPaperEntrySafetyObservation:
    """``portfolio`` holding ``quantity`` units valued at the fresh visible ``mark``."""

    position = {"position_mark_record_digest": POSITION_MARK, "position_mark_price": d(mark)}
    return portfolio(position_quantity=d(quantity), **{**position, **changes})


def test_rule_sets_v1_and_v2_keep_their_accepted_identity_and_v3_adds_only_its_portfolio_rule() -> None:
    assert GOVERNED_PAPER_ENTRY_SAFETY_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V1_DIGEST
    assert GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V2_DIGEST
    v2, v3 = GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_RULE_SET, GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET
    assert (v3["rule_set_id"], v3["contract_id"], GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID) == (
        "governed-paper-entry-safety.v3",
        "S1_NO_TRADE_NATIVE_MEASUREMENT_CLOSURE_V1",
        "governed-paper-entry-safety.v3",
    )
    assert v3["checks"] == v2["checks"] and v3["protective_rule"] == v2["protective_rule"]
    assert set(v3) - set(v2) == {"portfolio_rule"}
    rule = v3["portfolio_rule"]
    assert (rule["daily_loss_limit"], rule["concentration_cap"]) == (d("-0.02"), d("0.25"))  # type: ignore[index]
    assert (
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_DIGEST
        == edge_sha256_text(edge_canonical_json(v3))
        == governed_paper_entry_safety_rule_set_digest(protective=True, portfolio=True)
        == RULE_SET_V3_DIGEST
    )
    needs_v2 = code("portfolio_rule_set_needs_the_protective_rule_set")
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{needs_v2}$"):
        entry_safety.governed_paper_entry_safety_rule_set(portfolio=True)


def test_a_flat_governed_portfolio_passes_r02_r03_and_r04_on_its_snapshot_and_changes_nothing_else() -> None:
    for direction in ("SHORT", "LONG"):
        decision = evaluate_governed_paper_entry_safety(portfolio(target_direction=direction))
        statuses = {item.check_id: item.status for item in decision.checks}
        assert statuses == {
            **EXPECTED_BASE,
            "FB-MAX-HOLD": S.PASS,
            "FB-STOP": S.PASS,
            **dict.fromkeys(PORTFOLIO_IDS, S.PASS),
        }
        for name in PORTFOLIO_IDS:
            check = check_of(decision, name)
            assert (check.observed, check.reason, check.evidence_record_digests) == (
                d(0),
                code(f"{name}:{FLAT_PASS[name][1]}"),
                (SNAPSHOT,),
            )
        assert (decision.entry_permitted, decision.first_failure_check_id) == (False, "NT-D01")
    # without a governed portfolio (rule sets v1 and v2) each keeps exactly its earlier missing-input outcome
    legacy = evaluate_governed_paper_entry_safety(protected())
    assert [(check_of(legacy, name).status, check_of(legacy, name).reason) for name in PORTFOLIO_IDS] == [
        (BLOCKED, code("NT-R02:intraday_portfolio_pnl_and_nav_not_measured_at_the_decision_instant")),
        (BLOCKED, code("NT-R03:portfolio_position_risk_not_measured_at_the_decision_instant")),
        (BLOCKED, code("NT-R04:portfolio_position_concentration_not_measured_at_the_decision_instant")),
    ]


@pytest.mark.parametrize(
    ("nav", "status"),
    [
        ("9800", S.PASS),  # exactly -2% of the day-start NAV: equality never triggers
        ("9799.999999999999999999", S.FAIL),  # one unit below: the rendered ratio rounds to -2%, the exact one is below
        ("9800.000000000000000001", S.PASS),
        ("9000", S.FAIL),
        ("10200", S.PASS),
    ],
)
def test_nt_r02_fails_strictly_below_minus_2pct_of_the_utc_day_start_nav(nav: str, status: S) -> None:
    reason = "beyond" if status is S.FAIL else "within"
    for item in (portfolio(portfolio_nav=d(nav)), held(portfolio_nav=d(nav))):
        check = check_of(evaluate_governed_paper_entry_safety(item), "NT-R02")
        assert (check.status, check.observed, check.reason, check.evidence_record_digests) == (
            status,
            d((Fraction(nav) - 10_000) / 10_000),
            code(f"NT-R02:intraday_loss_{reason}_2pct_of_the_day_start_nav"),
            (SNAPSHOT,),
        )


@pytest.mark.parametrize(
    ("quantity", "mark", "status"),
    [
        ("-1", "2500", S.PASS),  # exactly 25% of NAV: equality never triggers
        ("-1", "2500.000000000000000001", S.FAIL),
        ("1", "2499.999999999999999999", S.PASS),
        ("0.5", "6000", S.FAIL),
        ("-1", "40", S.PASS),
    ],
)
def test_nt_r04_fails_strictly_above_25pct_of_nav_at_the_fresh_visible_mark(
    quantity: str, mark: str, status: S
) -> None:
    decision = evaluate_governed_paper_entry_safety(held(quantity, mark))
    check = check_of(decision, "NT-R04")
    reason = "above" if status is S.FAIL else "within"
    assert (check.status, check.observed, check.reason, check.evidence_record_digests) == (
        status,
        d(abs(Fraction(quantity)) * Fraction(mark) / 10_000),
        code(f"NT-R04:single_position_{reason}_25pct_of_nav"),
        (SNAPSHOT,),
    )
    # an open position never reads as zero open risk
    risk = check_of(decision, "NT-R03")
    assert (risk.status, risk.reason) == (OPEN_RISK[0], code(f"NT-R03:{OPEN_RISK[1]}"))


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        (
            portfolio(day_start_nav=None, day_start_reason="partial_first_utc_day"),
            {**FLAT_PASS, "NT-R02": (BLOCKED, "utc_day_start_nav_unavailable:partial_first_utc_day")},
        ),
        (
            portfolio(day_start_nav=None, day_start_reason="day_start_valued_after_the_decision"),
            {**FLAT_PASS, "NT-R02": (BLOCKED, "utc_day_start_nav_unavailable:day_start_valued_after_the_decision")},
        ),
        (
            portfolio(day_start_nav=None, day_start_reason="day_start_nav_unrepresentable"),
            {**FLAT_PASS, "NT-R02": (BLOCKED, "utc_day_start_nav_unavailable:day_start_nav_unrepresentable")},
        ),
        (portfolio(day_start_nav=d(0)), {**FLAT_PASS, "NT-R02": (BLOCKED, "utc_day_start_nav_not_positive")}),
        (portfolio(day_start_nav=d(-5)), {**FLAT_PASS, "NT-R02": (BLOCKED, "utc_day_start_nav_not_positive")}),
        (
            portfolio(day_start_nav=d("0.000000000000000001"), portfolio_nav=d(10**30)),
            {**FLAT_PASS, "NT-R02": (BLOCKED, "intraday_pnl_ratio_unrepresentable")},
        ),
        (portfolio(order_in_flight=True), {**FLAT_PASS, "NT-R03": (BLOCKED, "an_order_in_flight_may_open_exposure")}),
        (
            portfolio(portfolio_nav=d(0)),
            {
                "NT-R02": (S.FAIL, "intraday_loss_beyond_2pct_of_the_day_start_nav"),
                "NT-R03": (BLOCKED, "portfolio_equity_not_positive"),
                "NT-R04": (BLOCKED, "nav_not_positive"),
            },
        ),
        (
            portfolio(position_quantity=d(-1), portfolio_nav=None, portfolio_nav_reason="no_fresh_visible_mark"),
            {
                "NT-R02": (BLOCKED, "nav_unavailable:no_fresh_visible_mark"),
                "NT-R03": OPEN_RISK,
                "NT-R04": (BLOCKED, "nav_unavailable:no_fresh_visible_mark"),
            },
        ),
        (
            held(portfolio_nav=None, portfolio_nav_reason="nav_unrepresentable"),
            {
                "NT-R02": (BLOCKED, "nav_unavailable:nav_unrepresentable"),
                "NT-R03": OPEN_RISK,
                "NT-R04": (BLOCKED, "nav_unavailable:nav_unrepresentable"),
            },
        ),
        (
            portfolio(portfolio_nav=None, portfolio_nav_reason="nav_unrepresentable"),
            dict.fromkeys(PORTFOLIO_IDS, (BLOCKED, "nav_unavailable:nav_unrepresentable")),
        ),
        (
            held(portfolio_nav=d(-1)),
            {
                "NT-R02": (S.FAIL, "intraday_loss_beyond_2pct_of_the_day_start_nav"),
                "NT-R03": OPEN_RISK,
                "NT-R04": (BLOCKED, "nav_not_positive"),
            },
        ),
        (
            held(mark=10**30, portfolio_nav=d("0.000000000000000001")),
            {
                "NT-R02": (S.FAIL, "intraday_loss_beyond_2pct_of_the_day_start_nav"),
                "NT-R03": OPEN_RISK,
                "NT-R04": (BLOCKED, "position_share_unrepresentable"),
            },
        ),
        (portfolio(single_instrument_portfolio=False), dict.fromkeys(PORTFOLIO_IDS, (BLOCKED, UNMEASURED[0]))),
        (
            portfolio(
                portfolio_snapshot_digest=None,
                position_quantity=None,
                portfolio_nav=None,
                day_start_ns=None,
                day_start_nav=None,
            ),
            dict.fromkeys(PORTFOLIO_IDS, (BLOCKED, UNMEASURED[1])),
        ),
    ],
)
def test_the_portfolio_checks_never_read_an_unsupported_snapshot_as_a_pass(
    item: GovernedPaperEntrySafetyObservation, expected: dict[str, tuple[S, str]]
) -> None:
    decision = evaluate_governed_paper_entry_safety(item)
    for name, (status, reason) in expected.items():
        check = check_of(decision, name)
        assert (check.status, check.reason) == (status, code(f"{name}:{reason}"))
        assert check.evidence_record_digests == (() if reason in UNMEASURED else (SNAPSHOT,))
        if status is BLOCKED:
            assert check.observed == ""
    assert decision.entry_permitted is False


@pytest.mark.parametrize(
    ("build", "name"),
    [
        (lambda: portfolio(portfolio_present=1), "portfolio_present"),
        (lambda: portfolio(order_in_flight=None), "order_in_flight"),
        (lambda: portfolio(day_start_reason="genesis_substituted"), "day_start_reason"),
        (lambda: portfolio(day_start_reason=None), "day_start_reason"),
        (lambda: portfolio(portfolio_snapshot_digest="x" * 64), "portfolio_snapshot_digest"),
        (lambda: portfolio(position_quantity=None), "position_quantity"),
        (lambda: portfolio(position_quantity="0"), "position_quantity"),
        (lambda: portfolio(portfolio_nav="10000"), "portfolio_nav"),
        (lambda: portfolio(day_start_nav="10000"), "day_start_nav"),
        (lambda: portfolio(position_mark_price=d(40)), "position_mark"),
        (lambda: portfolio(position_mark_record_digest=POSITION_MARK), "position_mark"),
        (lambda: held(position_mark_record_digest="A" * 64), "position_mark"),
        (lambda: held(mark=0), "position_mark_price"),
        (lambda: held(quantity=0), "flat_portfolio_inconsistent"),
        (lambda: portfolio(portfolio_nav_reason=None), "portfolio_nav_reason"),
        (lambda: portfolio(portfolio_nav_reason="stale_mark"), "portfolio_nav_reason"),
        (lambda: portfolio(portfolio_nav_reason="nav_unrepresentable"), "portfolio_nav_reason"),
        (lambda: portfolio(portfolio_nav=None), "portfolio_nav_reason"),
        (lambda: held(portfolio_nav=None), "portfolio_nav_reason"),
        (
            lambda: portfolio(portfolio_nav=None, portfolio_nav_reason="no_fresh_visible_mark"),
            "flat_portfolio_inconsistent",
        ),
        (
            lambda: held(portfolio_nav=None, portfolio_nav_reason="no_fresh_visible_mark"),
            "open_position_nav_inconsistent",
        ),
        (lambda: portfolio(position_quantity=d(-1)), "open_position_nav_inconsistent"),
        (
            lambda: portfolio(position_quantity=d(-1), portfolio_nav=None, portfolio_nav_reason="nav_unrepresentable"),
            "open_position_nav_inconsistent",
        ),
        (lambda: portfolio(day_start_ns=DAY_START + 1), "day_start_ns"),
        (lambda: portfolio(day_start_ns=DAY_START - DAY_NS), "day_start_ns"),
        (lambda: portfolio(day_start_ns=None), "day_start_ns"),
        (lambda: portfolio(day_start_ns=True), "day_start_ns"),
        (lambda: portfolio(day_start_reason="partial_first_utc_day"), "day_start_reason"),
        (lambda: portfolio(day_start_nav=None), "day_start_reason"),
        (lambda: portfolio(portfolio_snapshot_digest=None), "portfolio_facts_without_a_snapshot"),
        (lambda: protected(position_quantity=d(0)), "portfolio_facts_without_a_snapshot"),
        (lambda: protected(order_in_flight=True), "portfolio_facts_without_a_snapshot"),
        (lambda: protected(day_start_reason="partial_first_utc_day"), "portfolio_facts_without_a_snapshot"),
        (lambda: protected(portfolio_nav_reason="nav_unrepresentable"), "portfolio_facts_without_a_snapshot"),
        (lambda: observation(portfolio_present=True), "portfolio_without_a_protective_context"),
        (
            lambda: observation(portfolio_present=True, portfolio_snapshot_digest=SNAPSHOT, position_quantity=d(0)),
            "portfolio_without_a_protective_context",
        ),
    ],
)
def test_malformed_portfolio_facts_are_refused(build: object, name: str) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code(f'observation_malformed:{name}')}$"):
        evaluate_governed_paper_entry_safety(build())  # type: ignore[operator]


@functools.cache
def portfolio_days(count: int) -> tuple:
    """World G's first ``count`` protective days with the native portfolio checks (seal v4), on the PRODUCTION table."""

    assert entry_safety._CHECKS is PRODUCTION_CHECKS  # noqa: SLF001
    if count == 0:
        return ()
    days = portfolio_days(count - 1)
    return (*days, lineage.protective_day(days, portfolio_no_trade=True))


def seal_protection(item: object) -> GovernedPaperEntrySafetyProtection:
    """The protective context the day seal derives: the authority's policy, the day's archive and its DEC-1 window."""

    inputs = item.seal_inputs  # type: ignore[attr-defined]
    context = governed_paper_protective_context(inputs.protection.authority, inputs.protection.authority_inputs)
    (window,) = item.seal.schedule.protective_windows  # type: ignore[attr-defined]
    return GovernedPaperEntrySafetyProtection(
        context.position_management_policy, inputs.protection.ohlc_archive, window
    )


def test_a_four_day_native_portfolio_lineage_measures_world_g_on_the_production_table() -> None:
    days = portfolio_days(4)
    for item in days:
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (
            "governed-paper-day-seal.v4",
            GovernedPaperDaySealStatus.SEALED,
            (),
        )
        assert seal.entry_safety_rule_set_digest == RULE_SET_V3_DIGEST
        verification = verify_governed_paper_day_seal(seal, item.seal_inputs)
        assert (verification.intact, verification.reason_codes) == (True, ())
    item = days[3]
    (entry,) = item.seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # the data contract still refuses
    economics, outcome = lineage.protected_replay(item)
    measured = simulate_historical_execution_governed_paper_decision_portfolio(
        economics, expected_result_digest=economics.result_digest, schedule=item.seal.schedule
    )
    assert measured.outcome_digest == outcome.outcome_digest
    (snapshot,) = [value for value in measured.snapshots if value.decision_sequence == entry.decision_sequence]
    assert (snapshot.position_quantity, snapshot.order_in_flight, snapshot.nav, snapshot.day_start_nav) == (
        d(0),
        False,
        d(10_000),
        d(10_000),
    )
    for name in PORTFOLIO_IDS:
        check = check_of(entry, name)
        assert (check.status, check.observed, check.evidence_record_digests) == (
            S.PASS,
            d(0),
            (snapshot.snapshot_digest,),
        )
    # the public builder re-derives exactly the sealed evaluation from the replayed economics and the sealed schedule
    authority, run, _ = run_and_evidence(item)
    evidence = build_governed_paper_entry_safety_evidence(
        authority=authority,
        run=run,
        dataset=item.seal_inputs.dataset,
        invalidated_from_ns=None,
        protection=seal_protection(item),
        portfolio=GovernedPaperEntrySafetyPortfolio(economics, item.seal.schedule),
    )
    assert (evidence.rule_set_id, evidence.rule_set_digest, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_PORTFOLIO_RULE_SET_ID,
        RULE_SET_V3_DIGEST,
        item.seal.entry_safety_evidence_digest,
    )
    # the production table refuses every entry before any measurement: the sequential admission refuses exactly them
    assert item.seal.schedule.entry_refused_decision_sequences == governed_paper_entry_safety_entry_sequences(run)
    assert item.seal.schedule.entry_refused_decision_sequences == (entry.decision_sequence,)
    lineage_evidence = lineage.evidence_of(days)
    assert (lineage_evidence.schema_version, lineage_evidence.status) == (
        "governed-paper-execution-evidence.v4",
        GovernedPaperExecutionStatus.READY,
    )
    verification = verify_governed_paper_execution_evidence(lineage_evidence, gpe.evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_the_portfolio_is_derived_by_the_one_engine_and_a_foreign_or_underivable_one_is_refused() -> None:
    item = portfolio_days(4)[3]
    authority, run, _ = run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    schedule = item.seal.schedule
    unprotected = gpe.execution.build_historical_execution_economics(  # the same run, without position management
        run,
        expected_run_digest=run.run_digest,
        economics_policy=authority.economics_policy,
        expected_economics_policy_digest=authority.genesis.economics_policy_digest,
        economics_approval=authority.economics_approval,
        result_id="unprotected-economics",
        correlation_id="corr-unprotected",
    )
    outside = replace(schedule, windows=(replace(schedule.windows[0], window_end_ns=economics.evaluation_end_ns + 1),))
    protection = seal_protection(item)
    forged = replace(economics, result_digest="0" * 64)
    for context, supplied, reason in (
        (protection, object(), "portfolio_malformed"),
        (None, GovernedPaperEntrySafetyPortfolio(economics, schedule), "portfolio_without_a_protective_context"),
        (protection, GovernedPaperEntrySafetyPortfolio(object(), schedule), "portfolio_economics_malformed"),  # type: ignore[arg-type]
        (
            protection,
            GovernedPaperEntrySafetyPortfolio(unprotected, schedule),
            "portfolio_economics_not_of_this_evaluation",
        ),
        (protection, GovernedPaperEntrySafetyPortfolio(economics, outside), "portfolio_not_derivable"),
        (protection, GovernedPaperEntrySafetyPortfolio(forged, schedule), "portfolio_not_derivable"),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"^{code(reason)}$"):
            build_governed_paper_entry_safety_evidence(
                authority=authority,
                run=run,
                dataset=item.seal_inputs.dataset,
                invalidated_from_ns=None,
                protection=context,
                portfolio=supplied,  # type: ignore[arg-type]
            )


def lifecycle_observation(snapshot: object) -> GovernedPaperEntrySafetyObservation:
    """The rule set v3 observation of one protective lifecycle-world decision: its governed snapshot (SYNTHETIC rest)."""

    return portfolio(
        decision_sequence=snapshot.decision_sequence,  # type: ignore[attr-defined]
        decision_time_ns=snapshot.decision_time_ns,  # type: ignore[attr-defined]
        decision_digest=snapshot.decision_digest,  # type: ignore[attr-defined]
        genesis_start_ns=lifet.ANCHOR,
        book_update_event_time_ns=snapshot.decision_time_ns - SECOND,  # type: ignore[attr-defined]
        **governed_paper_entry_safety_portfolio_facts(snapshot),  # type: ignore[arg-type]
    )


def portfolio_refusals(result: object, refused: tuple[int, ...]) -> tuple[int, ...]:
    """TEST-ONLY READING: the entries NT-R02, NT-R03 or NT-R04 refuse on the portfolio of the schedule refusing ``refused``.

    Every other fact of these observations is synthetic, so only the three native measurements decide here; no rule
    table is replaced.
    """

    refusing = []
    for snapshot in lifet.portfolio_of(result, lifet.both_sides(refused=refused)).snapshots:  # type: ignore[arg-type]
        decision = evaluate_governed_paper_entry_safety(lifecycle_observation(snapshot))
        if any(check_of(decision, name).status is not S.PASS for name in PORTFOLIO_IDS):
            refusing.append(snapshot.decision_sequence)
    return tuple(refusing)


def test_a_same_day_loss_beyond_2pct_refuses_the_re_entry_and_admission_is_sequential_never_a_neutral_replay() -> None:
    world = lifet.world(lifet.STOPPED_OUT, end=lifet.END_2D)
    result = lifet.computed(lifet.managed(world))
    entries = governed_paper_entry_safety_entry_sequences(world.run)
    d0, d1, d2, d3, d4 = entries
    rounds: list[tuple[int, ...]] = []

    def refusals_under(refused: tuple[int, ...]) -> tuple[int, ...]:
        rounds.append(refused)
        return portfolio_refusals(result, refused)

    fixed = governed_paper_entry_safety_sequential_refusals(entries, refusals_under)
    assert fixed == (d1, d3, d4) and portfolio_refusals(result, fixed) == fixed  # the schedule refuses its own refusals
    assert rounds[0] == entries and len(rounds) <= len(entries) + 1
    measured = lifet.portfolio_of(result, lifet.both_sides(refused=fixed))
    evaluated = {
        snapshot.decision_sequence: evaluate_governed_paper_entry_safety(lifecycle_observation(snapshot))
        for snapshot in measured.snapshots
    }
    assert [check_of(evaluated[d0], name).status for name in PORTFOLIO_IDS] == [S.PASS] * 3
    # D_1: the SHORT of D_0 stopped out ~2.1% of NAV down at 12 h 31 s, the same UTC day: NT-R02 refuses the re-entry
    loss = check_of(evaluated[d1], "NT-R02")
    assert (loss.status, loss.reason) == (S.FAIL, code("NT-R02:intraday_loss_beyond_2pct_of_the_day_start_nav"))
    assert Fraction(loss.observed) < Fraction(-2, 100)
    # D_2 opens the next UTC day on its midnight valuation: no intraday loss, flat, admitted
    assert [check_of(evaluated[d2], name).status for name in PORTFOLIO_IDS] == [S.PASS] * 3
    assert check_of(evaluated[d2], "NT-R02").observed == d(0)
    # D_3 and D_4 hold the D_2 SHORT: an open position never reads as zero open risk; refusing a hold changes nothing
    for sequence in (d3, d4):
        assert check_of(evaluated[sequence], "NT-R03").reason == code(f"NT-R03:{OPEN_RISK[1]}")
    # an evaluation on the neutral replay would refuse D_2: there the D_1 re-entry is still open at D_2
    assert portfolio_refusals(result, ()) == (d1, d2, d3, d4)
    sequential = lifet.governed_under(result, lifet.both_sides(refused=fixed))
    neutral = lifet.governed_under(result, lifet.both_sides())
    assert measured.outcome_digest == sequential.outcome_digest

    def entry_fill(outcome: object, sequence: int):  # noqa: ANN202
        (intent,) = [item for item in outcome.intents if item.decision_sequence == sequence]  # type: ignore[attr-defined]
        return [item for item in outcome.fills if item.intent_id == intent.intent_id][-1]  # type: ignore[attr-defined]

    assert (entry_fill(sequential, d1).outcome, entry_fill(sequential, d1).reason) == (
        HistoricalExecutionFillOutcome.REJECTED,
        GATE,
    )
    assert entry_fill(sequential, d2).outcome is HistoricalExecutionFillOutcome.FILLED  # the next day's entry
    assert entry_fill(neutral, d1).outcome is HistoricalExecutionFillOutcome.FILLED
    assert all(item.decision_sequence != d2 for item in neutral.intents)  # there D_2 holds the D_1 SHORT


def test_an_unrepresentable_engine_nav_blocks_the_portfolio_checks_and_never_raises() -> None:
    """The engine snapshot of a NAV outside the scale-18 domain is an explicit BLOCKED reading of every check needing it."""

    result = lifet.computed(lifet.managed(lifet.world(lifet.NAV_SPIKE, end=lifet.END_2D)))
    snapshot = lifet.snapshot_at(lifet.portfolio_of(result, lifet.both_sides()), lifet.decision_instant(1))
    assert (snapshot.nav, snapshot.nav_reason) == (None, "nav_unrepresentable")
    decision = evaluate_governed_paper_entry_safety(lifecycle_observation(snapshot))
    assert [(check_of(decision, name).status, check_of(decision, name).reason) for name in PORTFOLIO_IDS] == [
        (BLOCKED, code("NT-R02:nav_unavailable:nav_unrepresentable")),
        (BLOCKED, code(f"NT-R03:{OPEN_RISK[1]}")),
        (BLOCKED, code("NT-R04:nav_unavailable:nav_unrepresentable")),
    ]


def test_a_stale_engine_mark_blocks_the_portfolio_checks_of_an_open_position() -> None:
    world = lifet.variant_world(lifet.MARK_GAP, end=lifet.END_2D, published=lifet.STALE_D1)
    result = lifet.computed(lifet.managed(world))
    snapshot = lifet.snapshot_at(lifet.portfolio_of(result, lifet.both_sides()), lifet.ANCHOR + 18 * lifet.HOUR)
    decision = evaluate_governed_paper_entry_safety(lifecycle_observation(snapshot))
    assert [(check_of(decision, name).status, check_of(decision, name).reason) for name in PORTFOLIO_IDS] == [
        (BLOCKED, code("NT-R02:nav_unavailable:no_fresh_visible_mark")),
        (BLOCKED, code(f"NT-R03:{OPEN_RISK[1]}")),
        (BLOCKED, code("NT-R04:nav_unavailable:no_fresh_visible_mark")),
    ]
