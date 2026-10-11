"""Tests for the RF-7 regime-conditioned paper performance evidence (``regime_conditioned_performance_evidence``).

Fixtures: ONE authentic joint world.

* EF/RF: the RF-6 test module's EF-2 -> EF-5 V2 chain and governed up/down filter over ``mark-final``. Its RF-3
  records here lie on the RG-3 window's UTC days: closes from day ``START``, one close (``SKIP``) missing. The earlier
  RF-4 evidence labels days 20454..20473, and the later one 20454..20478. RF-5 proves the 20-day overlap stable and
  RF-6 admits the filter;
* RG-3: the RG-3 test module's 30-day sleeve world (days 20454..20483), whose episodes are re-bridged through the
  accepted public builders over the EXACT spec the EF-5 preregistration admitted. The economics, and so the returns,
  are unchanged.

Every close, threshold, approval and identifier is a SYNTHETIC TEST VALUE. Expected labels come from the move string,
expected days from the window geometry. Means, Sharpe ratios and peak distances come from independent oracles: exact
``Fraction`` arithmetic, 150-digit ``decimal`` square roots and a direct running-peak scan. The paper Sharpe of the
full window is cross-checked against RG-3's accepted ``paper_sharpe_evidence`` output.
"""

from __future__ import annotations

import ast
import dataclasses
import decimal
import functools
import inspect
import json
import re
from collections.abc import Sequence
from dataclasses import fields, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.regime_conditioned_performance_evidence as rf7_module
from crypto_core.strategy.spec import StrategySpec, strategy_spec_digest, validate_strategy_spec
from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_leakage_bias_evidence import EdgeSurvivorshipClaimScope
from crypto_core.validation.paper_end_to_end_episode import build_paper_end_to_end_episode
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDailyValuationEvidence,
    PaperSleeveEpisodeEvidence,
    PaperSleeveValuationInputs,
    build_paper_sleeve_daily_valuation_evidence,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    build_paper_sleeve_performance_evidence,
    paper_sleeve_performance_evidence_digest,
)
from crypto_core.validation.regime_conditioned_performance_evidence import (
    REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS,
    REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
    RegimeConditionedDay,
    RegimeConditionedDayClass,
    RegimeConditionedPerformanceApproval,
    RegimeConditionedPerformanceError,
    RegimeConditionedPerformanceEvidence,
    RegimeConditionedPerformanceInputs,
    RegimeConditionedPerformancePolicy,
    RegimeConditionedPerformanceStatus,
    RegimeStratumMetricStatus,
    RegimeStratumPerformance,
    build_regime_conditioned_performance_evidence,
    build_regime_conditioned_performance_policy,
    measure_regime_stratum_returns,
    regime_conditioned_performance_evidence_digest,
    regime_conditioned_performance_evidence_from_payload,
    regime_conditioned_performance_evidence_payload_is_well_formed,
    regime_conditioned_performance_evidence_to_dict,
    regime_conditioned_performance_policy_digest,
    regime_conditioned_performance_policy_from_payload,
    regime_conditioned_performance_policy_to_dict,
    regime_conditioned_performance_rule_set,
    verify_regime_conditioned_performance_evidence,
    verify_regime_conditioned_performance_policy,
)
from crypto_core.validation.regime_feature_policy import REGIME_NON_CLAIM_FLAGS, RegimeFeaturePolicyApprovalKind
from crypto_core.validation.regime_feature_series_evidence import build_regime_feature_series_evidence
from crypto_core.validation.regime_filter_admission_decision import (
    RegimeFilterAdmissionDecision,
    RegimeFilterAdmissionInputs,
    build_regime_filter_admission_decision,
)
from crypto_core.validation.regime_label_evidence import (
    RegimeLabelInputs,
    build_regime_label_evidence,
    regime_label_evidence_digest,
)
from crypto_core.validation.regime_stability_evidence import (
    RegimeStabilityInputs,
    RegimeStabilityStatus,
    build_regime_stability_evidence,
    regime_stability_evidence_digest,
)
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so their cached worlds are built once
    import test_paper_sleeve_daily_valuation_evidence as valt
    import test_paper_sleeve_performance_evidence as rg3t
    import test_regime_feature_series_evidence as rf3t
    import test_regime_filter_admission_decision as rf6t
    import test_regime_label_evidence as rf4t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as valt
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t
    from tests.crypto_core.validation import test_regime_feature_series_evidence as rf3t
    from tests.crypto_core.validation import test_regime_filter_admission_decision as rf6t
    from tests.crypto_core.validation import test_regime_label_evidence as rf4t

_PREFIX = "regime_conditioned_performance_evidence"
SOURCE = Path(rf7_module.__file__).read_text(encoding="utf-8")
DAY_NS = 86_400_000_000_000
START, SKIP = 20_452, 20_460  # SYNTHETIC: first close day; one missing close
LATER = "UUDDUDUUUDDUDUUDDDUUDUUDU"  # SYNTHETIC moves: labels for days 20454..20478
EARLIER = LATER[:20]  # labels for days 20454..20473
WINDOW_FIRST, WINDOW_DAYS = 20_454, 30
READY = RegimeConditionedPerformanceStatus.READY
TRUSTED, UNLABELED = RegimeConditionedDayClass.TRUSTED, RegimeConditionedDayClass.UNLABELED
UNPROVEN, NOT_COVERED = RegimeConditionedDayClass.STABILITY_UNPROVEN, RegimeConditionedDayClass.LABEL_NOT_COVERED
COMPUTED = RegimeStratumMetricStatus.COMPUTED
INSUFFICIENT = RegimeStratumMetricStatus.INSUFFICIENT_SAMPLE
HUMAN = RegimeFeaturePolicyApprovalKind.HUMAN_GOVERNANCE
NOT_COMPUTABLE = RegimeConditionedPerformanceStatus.NOT_COMPUTABLE
NEEDS_GOVERNANCE = RegimeConditionedPerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
NOT_ADMITTED = RegimeConditionedPerformanceStatus.FILTER_NOT_ADMITTED


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    return pytest.raises(RegimeConditionedPerformanceError, match=f"^{re.escape(code(text))}$")


# --- the joint world ------------------------------------------------------------------------------------------------


@functools.cache
def admitted_spec() -> StrategySpec:
    """The exact StrategySpec the RF-6 world's EF-4 admitted (its digest is the EF-5 ``strategy_spec_digest``)."""

    spec = validate_strategy_spec({**pit.SPEC, "data_requirements": {"funding_rate": "8h", "mark_price": "8h"}}).spec
    assert strategy_spec_digest(spec) == rf6t.sealed().strategy_spec_digest
    return spec


def respec(episode: PaperSleeveEpisodeEvidence, spec: StrategySpec) -> PaperSleeveEpisodeEvidence:
    """The same economic episode, its signal bridge and end-to-end episode rebuilt over ``spec``."""

    old, request = episode.signal_bridge, episode.order_intent_request
    bridge = build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=strategy_spec_digest(spec),
        signal_id=old.signal_id,
        run_id=old.run_id,
        correlation_id=old.correlation_id,
        market_symbol=request.market_symbol,
        side=request.side,
        intent_type=request.intent_type,
        requested_units=request.requested_units,
        requested_notional=request.requested_notional,
        capacity_decision_digest=request.capacity_decision_digest,
        limit_price=request.limit_price,
    )
    e2e = episode.end_to_end_episode
    rebuilt = build_paper_end_to_end_episode(
        bridge,
        episode.order_intent,
        episode.episode_run,
        episode.realized_pnl_event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=episode.order_intent.intent_digest,
        expected_episode_run_digest=episode.episode_run.episode_run_digest,
        expected_realized_pnl_event_digest=episode.realized_pnl_event.realized_pnl_event_digest,
        episode_id=e2e.episode_id,
        run_id=e2e.run_id,
        correlation_id=e2e.correlation_id,
    )
    return replace(episode, strategy_spec=spec, signal_bridge=bridge, end_to_end_episode=rebuilt)


@functools.cache
def sleeve_valuation() -> tuple[PaperSleeveValuationInputs, PaperSleeveDailyValuationEvidence]:
    episodes = tuple(respec(item, admitted_spec()) for item in valt.world_episodes())
    valuation_inputs = valt.valuation_inputs(episodes=episodes)
    return valuation_inputs, build_paper_sleeve_daily_valuation_evidence(valuation_inputs)


@functools.cache
def sleeve_series() -> dict[str, object]:
    valuation = sleeve_valuation()[1]
    return rg3t.series_world(valuation, valt.basis_policy(), valt.WINDOW_START, valt.WINDOW_END).inputs()


def sleeve_world(**overrides: object) -> tuple[PaperSleevePerformanceInputs, PaperSleevePerformanceEvidence]:
    valuation_inputs, valuation = sleeve_valuation()
    values: dict[str, object] = {"valuation_inputs": valuation_inputs, "valuation": valuation, **sleeve_series()}
    values.update(overrides)
    inputs = rg3t.performance_inputs(**values)
    return inputs, build_paper_sleeve_performance_evidence(inputs)


@functools.cache
def default_sleeve() -> tuple[PaperSleevePerformanceInputs, PaperSleevePerformanceEvidence]:
    return sleeve_world()


def label_world(moves: str, label_id: str, start: int = START) -> tuple[RegimeLabelInputs, object]:
    """RF-3 over authenticated closes from day ``start`` (the close of ``SKIP`` missing), then RF-4 from ``start + 2``."""

    closes = rf4t.moves_closes(moves)
    records = tuple(
        rf3t.pit_record(start + index, rf3t.price(close), series=rf6t.MARK)
        for index, close in enumerate(closes)
        if start + index != SKIP
    )
    series_inputs = rf3t.series_inputs(
        policy=rf6t.policy(),
        records=records,
        source_manifest=rf6t.ef_world()[3],
        last=start + len(closes),
        first_feature_day=start + 2,
    )
    inputs = RegimeLabelInputs(
        label_id, "corr-1", rf6t.policy(), series_inputs, build_regime_feature_series_evidence(series_inputs)
    )
    return inputs, build_regime_label_evidence(inputs)


@functools.cache
def admission_world(
    earlier: str = EARLIER, later: str = LATER, start: int = START
) -> tuple[RegimeFilterAdmissionInputs, RegimeFilterAdmissionDecision]:
    stability_inputs = RegimeStabilityInputs(
        "rf5-joint",
        "corr-1",
        rf6t.policy(),
        *label_world(earlier, "rf4-earlier", start),
        *label_world(later, "rf4-later", start),
    )
    stability = build_regime_stability_evidence(stability_inputs)
    inputs = rf6t.admission_inputs(stability=(stability_inputs, stability))
    return inputs, build_regime_filter_admission_decision(inputs)


def measurement_policy(
    min_observations: object = 4, approval: dict[str, object] | None = None, *, governed: bool = True
) -> RegimeConditionedPerformancePolicy:
    """A SYNTHETIC sample floor; ``approval`` overrides fields of an exact HUMAN_GOVERNANCE test approval."""

    draft = build_regime_conditioned_performance_policy(
        policy_id="rf7-policy-1",
        policy_version="synthetic-v1",
        min_observations_per_stratum=min_observations,
        approval=None,  # type: ignore[arg-type]
    )
    if not governed:
        return draft
    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "c" * 64,
        "approval_kind": HUMAN,
        "approved_policy_id": draft.policy_id,
        "approved_policy_version": draft.policy_version,
        "approved_policy_digest": draft.policy_digest,
        "approved_rule_set_digest": draft.rule_set_digest,
    }
    values.update(approval or {})
    return build_regime_conditioned_performance_policy(
        policy_id="rf7-policy-1",
        policy_version="synthetic-v1",
        min_observations_per_stratum=min_observations,  # type: ignore[arg-type]
        approval=RegimeConditionedPerformanceApproval(**values),  # type: ignore[arg-type]
    )


@functools.cache
def default_policy() -> RegimeConditionedPerformancePolicy:
    return measurement_policy()


def report_inputs(
    *,
    admission: tuple[RegimeFilterAdmissionInputs, RegimeFilterAdmissionDecision] | None = None,
    sleeve: tuple[PaperSleevePerformanceInputs, PaperSleevePerformanceEvidence] | None = None,
    **overrides: object,
) -> RegimeConditionedPerformanceInputs:
    admission_inputs, decision = admission_world() if admission is None else admission
    performance_inputs, performance = default_sleeve() if sleeve is None else sleeve
    values: dict[str, object] = {
        "report_id": "rf7-1",
        "correlation_id": "corr-1",
        "measurement_policy": default_policy(),
        "admission_inputs": admission_inputs,
        "admission": decision,
        "expected_admission_digest": decision.regime_filter_admission_digest,
        "performance_inputs": performance_inputs,
        "performance": performance,
        "expected_performance_digest": performance.performance_evidence_digest,
    }
    values.update(overrides)
    return RegimeConditionedPerformanceInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> RegimeConditionedPerformanceEvidence:
    return build_regime_conditioned_performance_evidence(inputs)  # type: ignore[arg-type]


def decide(inputs: RegimeConditionedPerformanceInputs) -> RegimeConditionedPerformanceEvidence:
    """Build, then re-prove by reconstruction: every report a test reads is intact."""

    report = build(inputs)
    verification = verify_regime_conditioned_performance_evidence(report, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == report.regime_conditioned_performance_digest
    assert json.loads(verification.canonical_json) == regime_conditioned_performance_evidence_to_dict(report)
    assert {name: getattr(report, name) for name, _ in REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS} == dict(
        REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS
    )
    assert report.ready is (report.status is READY)
    if not report.ready:
        assert (report.days, report.strata, report.trusted_day_count) == ((), (), 0)
    return report


@functools.cache
def default_report() -> RegimeConditionedPerformanceEvidence:
    return decide(report_inputs())


def reseal(report: RegimeConditionedPerformanceEvidence, **changes: object) -> RegimeConditionedPerformanceEvidence:
    changed = replace(report, **changes)  # type: ignore[arg-type]
    return replace(
        changed, regime_conditioned_performance_digest=regime_conditioned_performance_evidence_digest(changed)
    )


# --- independent oracles --------------------------------------------------------------------------------------------


def oracle_label(day: int, moves: str = LATER, start: int = START) -> str | None:
    """label(D) is STRESSED iff day D-1 closed below D-2; a window holding the missing close is UNLABELED."""

    index = day - start - 2
    if not 0 <= index < len(moves):
        return None
    if day in (SKIP + 1, SKIP + 2):
        return "UNLABELED"
    return "STRESSED" if moves[index] == "D" else "CALM"


def oracle_class(day: int, earlier: str = EARLIER, later: str = LATER, start: int = START) -> RegimeConditionedDayClass:
    """TRUSTED only inside the overlap of both label evidences (the earlier is a prefix of the later)."""

    if oracle_label(day, earlier, start) is not None:
        return UNLABELED if oracle_label(day, later, start) == "UNLABELED" else TRUSTED
    if oracle_label(day, later, start) is not None:
        return UNPROVEN
    return NOT_COVERED


def oracle_text(value: Decimal) -> str:
    return format(value.quantize(Decimal(1).scaleb(-18), rounding=decimal.ROUND_HALF_EVEN), "f")


def oracle_measure(returns: Sequence[str]) -> tuple[str, str, str]:
    """Mean, daily and annualized Sharpe by 150-digit decimal arithmetic, rounded half-even once at scale 18."""

    values = [Fraction(item) for item in returns]
    mean = sum(values, Fraction(0)) / len(values)
    variance = sum(((value - mean) ** 2 for value in values), Fraction(0)) / (len(values) - 1)
    with decimal.localcontext(decimal.Context(prec=150, rounding=decimal.ROUND_HALF_EVEN)):
        exact_mean = Decimal(mean.numerator) / Decimal(mean.denominator)
        daily = exact_mean / (Decimal(variance.numerator) / Decimal(variance.denominator)).sqrt()
        return oracle_text(exact_mean), oracle_text(daily), oracle_text(daily * Decimal(365).sqrt())


def oracle_peak_distance(returns: Sequence[str]) -> Fraction:
    """A direct running-peak scan of one chain-linked index from 1."""

    index = peak = Fraction(1)
    worst = Fraction(0)
    for item in returns:
        index *= 1 + Fraction(item)
        peak = max(peak, index)
        worst = max(worst, (peak - index) / peak)
    return worst


def oracle_episodes(days: Sequence[int]) -> list[list[int]]:
    runs: list[list[int]] = []
    for day in days:
        if runs and runs[-1][-1] == day - 1:
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs


def returns_by_day() -> dict[int, str]:
    performance = default_sleeve()[1]
    return {WINDOW_FIRST + offset: value for offset, value in enumerate(performance.daily_returns)}


def trusted_days(report: RegimeConditionedPerformanceEvidence, label_id: str) -> list[int]:
    return [day.day_index for day in report.days if day.day_class is TRUSTED and day.label_id == label_id]


def verify(report: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_regime_conditioned_performance_evidence(report, inputs)  # type: ignore[arg-type]


# --- the READY report: authority, identity and replay ---------------------------------------------------------------


def test_a_ready_report_binds_every_reproven_authority_and_replays_exactly() -> None:
    report = default_report()
    admission_inputs, decision = admission_world()
    stability, rf2, ef5 = admission_inputs.stability, rf6t.policy(), rf6t.sealed()
    performance, policy = default_sleeve()[1], default_policy()
    assert (report.status, report.ready, report.reason_codes) == (READY, True, ())
    assert (decision.gate_verdict, decision.regime_filter_admitted, stability.status) == (
        EdgeGateVerdict.PASS,
        True,
        RegimeStabilityStatus.STABILITY_PROVEN,
    )
    assert (report.filter_admission_id, report.filter_admission_digest, report.filter_admission_verdict) == (
        decision.admission_id,
        decision.regime_filter_admission_digest,
        "PASS",
    )
    assert report.filter_admitted is True
    assert (report.regime_feature_policy_id, report.regime_feature_policy_version) == (
        rf2.policy_id,
        rf2.policy_version,
    )
    assert (report.regime_feature_policy_digest, report.label_set) == (rf2.regime_feature_policy_digest, rf2.label_set)
    assert (report.stability_evidence_digest, report.stability_status) == (
        stability.stability_evidence_digest,
        "STABILITY_PROVEN",
    )
    assert (report.earlier_as_of_ns, report.later_as_of_ns) == (stability.earlier_as_of_ns, stability.later_as_of_ns)
    assert (report.stability_overlap_first_day_index, report.stability_overlap_last_day_index) == (20_454, 20_473)
    assert (report.earlier_label_evidence_digest, report.later_label_evidence_digest) == (
        stability.earlier_label_evidence_digest,
        stability.later_label_evidence_digest,
    )
    assert (report.preregistration_digest, report.candidate_strategy_id) == (
        ef5.leakage_bias_evidence_digest,
        ef5.candidate_strategy_id,
    )
    assert (report.strategy_spec_digest, report.pinned_instrument_universe) == (
        ef5.strategy_spec_digest,
        ef5.pinned_instrument_universe,
    )
    assert (report.sleeve_performance_digest, report.sleeve_performance_status) == (
        performance.performance_evidence_digest,
        "READY",
    )
    assert (report.sleeve_id, report.market_symbol) == (valt.SLEEVE, valt.MARKET)
    assert (report.window_start_ns, report.window_end_ns, report.window_day_count) == (
        valt.WINDOW_START,
        valt.WINDOW_END,
        WINDOW_DAYS,
    )
    # The RF-6 world binds one correlation; the sleeve world's own correlation is recorded, never attribution.
    assert report.correlation_id == decision.correlation_id == "corr-1"
    assert report.sleeve_correlation_id == performance.correlation_id == valt.VALUATION_CORRELATION
    assert (report.measurement_policy_id, report.measurement_policy_version, report.measurement_policy_digest) == (
        policy.policy_id,
        policy.policy_version,
        policy.regime_conditioned_performance_policy_digest,
    )
    assert (report.measurement_policy_governed, report.min_observations_per_stratum) == (True, 4)
    assert (report.rule_set_id, report.rule_set_digest) == (
        "regime_conditioned_performance_evidence_rules.v1",
        REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST,
    )
    assert build(report_inputs()) == report  # deterministic replay


def test_the_sleeve_trades_the_preregistered_spec_and_nothing_more_is_attributed() -> None:
    report, ef5 = default_report(), rf6t.sealed()
    episodes = sleeve_valuation()[0].episodes
    assert report.sleeve_episode_count == len(episodes) == 4
    assert {strategy_spec_digest(item.strategy_spec) for item in episodes} == {ef5.strategy_spec_digest}
    assert report.sleeve_episode_strategy_spec_digests == (ef5.strategy_spec_digest,)
    assert report.strategy_spec_attribution_proven is True
    assert (report.candidate_paper_admission_proven, report.variant_attribution_proven) == (False, False)
    # The RG-3 module's own world has the same economics over another StrategySpec: a cross-world contradiction.
    other_inputs, other = rg3t.performance_inputs(), rg3t.world_performance()
    other_specs = {strategy_spec_digest(item.strategy_spec) for item in other_inputs.valuation_inputs.episodes}
    assert ef5.strategy_spec_digest not in other_specs
    assert other.daily_returns == default_sleeve()[1].daily_returns
    with refused("sleeve_strategy_spec_contradicts_the_preregistration"):
        build(report_inputs(sleeve=(other_inputs, other)))


# --- the exact UTC-day join and its denominators --------------------------------------------------------------------

JOIN_WORLDS: dict[str, tuple[tuple[str, str, int], tuple[int, int, int, int], int]] = {
    # (earlier moves, later moves, first close day), (trusted, UNLABELED, stability-unproven, not covered), outside
    "aligned": ((EARLIER, LATER, START), (18, 2, 5, 5), 0),
    "labels_one_day_earlier": ((EARLIER, LATER, START - 1), (17, 2, 5, 6), 1),
    "labels_beyond_the_window": ((EARLIER, LATER + "UDUDUDUDUD", START), (18, 2, 10, 0), 5),
}


@pytest.mark.parametrize("name", sorted(JOIN_WORLDS))
def test_every_window_day_is_joined_by_its_exact_utc_day_and_counted_once(name: str) -> None:
    (earlier, later, start), counts, outside = JOIN_WORLDS[name]
    world = admission_world(earlier, later, start)
    report = default_report() if name == "aligned" else build(report_inputs(admission=world))
    returns = returns_by_day()
    labels = {item.day_index: item.label_id for item in world[0].stability_inputs.later_labels.labels}
    assert [day.day_index for day in report.days] == list(range(WINDOW_FIRST, WINDOW_FIRST + WINDOW_DAYS))
    for day in report.days:
        assert day.daily_return == returns[day.day_index]
        assert day.label_id == labels.get(day.day_index, "") == (oracle_label(day.day_index, later, start) or "")
        assert day.day_class is oracle_class(day.day_index, earlier, later, start), day.day_index
    assert [sum(day.day_class is cls for day in report.days) for cls in RegimeConditionedDayClass] == list(counts)
    assert counts == (
        report.trusted_day_count,
        report.unlabeled_day_count,
        report.stability_unproven_day_count,
        report.label_not_covered_day_count,
    )
    assert sum(counts) == report.window_day_count == WINDOW_DAYS
    window = range(WINDOW_FIRST, WINDOW_FIRST + WINDOW_DAYS)
    assert report.label_days_outside_window_count == outside == sum(day not in window for day in labels)
    assert sum(stratum.observation_count for stratum in report.strata) == report.trusted_day_count
    assert [stratum.label_id for stratum in report.strata] == list(report.label_set)


def test_each_stratum_equals_the_independent_oracle() -> None:
    report, returns = default_report(), returns_by_day()
    for stratum in report.strata:
        days = [
            day
            for day in range(WINDOW_FIRST, WINDOW_FIRST + WINDOW_DAYS)
            if oracle_class(day) is TRUSTED and oracle_label(day) == stratum.label_id
        ]
        assert trusted_days(report, stratum.label_id) == days
        episodes = oracle_episodes(days)
        assert (stratum.observation_count, stratum.insufficient_sample) == (len(days), False)
        assert (stratum.mean_daily_return, stratum.paper_sharpe_daily, stratum.paper_sharpe_annualized) == (
            oracle_measure([returns[day] for day in days])
        )
        assert (stratum.sharpe_status, stratum.drawdown_status) == (COMPUTED, COMPUTED)
        assert (stratum.episode_count, stratum.longest_episode_day_count) == (
            len(episodes),
            max(len(episode) for episode in episodes),
        )
        worst = max(oracle_peak_distance([returns[day] for day in episode]) for episode in episodes)
        assert stratum.max_episode_peak_distance == f"{worst.numerator}/{worst.denominator}"
    summary = [
        (item.label_id, item.observation_count, item.episode_count, item.longest_episode_day_count)
        for item in report.strata
    ]
    assert summary == [("CALM", 9, 6, 2), ("STRESSED", 9, 5, 3)]


def test_noncontiguous_regime_days_are_never_one_equity_path() -> None:
    report, returns = default_report(), returns_by_day()
    overstated = []
    for stratum in report.strata:
        assert stratum.episode_count > 1  # regime switches and the UNLABELED gap split every stratum
        concatenated = oracle_peak_distance([returns[day] for day in trusted_days(report, stratum.label_id)])
        per_episode = Fraction(stratum.max_episode_peak_distance)  # type: ignore[arg-type]
        assert per_episode <= concatenated
        overstated.append(per_episode < concatenated)
    assert any(overstated)  # one fake continuous path would report a decline no single episode suffered


# --- the exact measure ----------------------------------------------------------------------------------------------


def test_the_full_window_measure_reproduces_the_accepted_paper_sharpe() -> None:
    performance = default_sleeve()[1]
    measurement = measure_regime_stratum_returns(performance.daily_returns)
    assert (measurement.observation_count, measurement.sharpe_status) == (WINDOW_DAYS, COMPUTED)
    assert (measurement.paper_sharpe_daily, measurement.paper_sharpe_annualized) == (
        performance.paper_sharpe_daily,
        performance.paper_sharpe_annualized,
    )
    assert performance.paper_sharpe_annualized == "1.809314530709372854"
    assert (measurement.mean_daily_return, measurement.paper_sharpe_daily, measurement.paper_sharpe_annualized) == (
        oracle_measure(performance.daily_returns)
    )


def test_the_measure_is_exact_signed_and_fails_closed() -> None:
    pair = measure_regime_stratum_returns(("0.01", "0.03"))  # mean 0.02, sample variance 0.0002: daily sqrt(2)
    assert (pair.observation_count, pair.sharpe_status) == (2, COMPUTED)
    assert (pair.mean_daily_return, pair.paper_sharpe_daily) == ("0.020000000000000000", "1.414213562373095049")
    assert (pair.mean_daily_return, pair.paper_sharpe_daily, pair.paper_sharpe_annualized) == (
        oracle_measure(("0.01", "0.03"))
    )
    negative = measure_regime_stratum_returns(["-0.01", "-0.03"])
    assert (negative.mean_daily_return, negative.paper_sharpe_daily) == (
        "-0.020000000000000000",
        "-1.414213562373095049",
    )
    centred = measure_regime_stratum_returns(("-0.01", "0.01"))
    assert (centred.mean_daily_return, centred.paper_sharpe_daily, centred.paper_sharpe_annualized) == (
        "0.000000000000000000",
        "0.000000000000000000",
        "0.000000000000000000",
    )
    flat = measure_regime_stratum_returns(("0.01", "0.01", "0.01"))
    assert (flat.sharpe_status, flat.mean_daily_return, flat.paper_sharpe_daily, flat.paper_sharpe_annualized) == (
        RegimeStratumMetricStatus.ZERO_VARIANCE,
        "0.010000000000000000",
        None,
        None,
    )
    single = measure_regime_stratum_returns(("0.05",))
    assert (single.observation_count, single.sharpe_status, single.mean_daily_return, single.paper_sharpe_daily) == (
        1,
        INSUFFICIENT,
        "0.050000000000000000",
        None,
    )
    empty = measure_regime_stratum_returns(())
    assert (empty.observation_count, empty.sharpe_status, empty.mean_daily_return) == (0, INSUFFICIENT, None)
    huge = measure_regime_stratum_returns(("9" * 50, "1"))  # a mean beyond the 60-character bound
    assert (huge.sharpe_status, huge.mean_daily_return, huge.paper_sharpe_daily) == (
        RegimeStratumMetricStatus.NOT_REPRESENTABLE,
        None,
        None,
    )
    steep = measure_regime_stratum_returns(("1", "1." + "0" * 56 + "1"))  # a ratio beyond the bound
    assert (steep.sharpe_status, steep.mean_daily_return, steep.paper_sharpe_daily) == (
        RegimeStratumMetricStatus.NOT_REPRESENTABLE,
        "1.000000000000000000",
        None,
    )
    # A 71-character return lies inside the accepted valuation's return grammar: measured, never refused.
    wide = measure_regime_stratum_returns(("1" + "0" * 70, "1"))
    assert (wide.sharpe_status, wide.mean_daily_return) == (RegimeStratumMetricStatus.NOT_REPRESENTABLE, None)


def test_an_episode_index_beyond_the_rg4_bound_is_not_representable_never_a_crash() -> None:
    render = rf7_module._plain_decimal_text
    assert render(1 + Fraction(1, 10**4095)) == "1." + "0" * 4094 + "1"  # scale 4095: within the 4096 bound
    assert render(Fraction(10**4096 - 1)) == "9" * 4096
    assert render(1 + Fraction(1, 10**4096)) is None  # scale beyond the bound
    assert render(Fraction(10**4096)) is None  # magnitude beyond the bound
    assert render(Fraction(21, 2 * 5**70)) == "0." + str(21 * 2**69).rjust(70, "0")  # scale max(1, 70)
    small = "0." + "0" * 59 + "1"  # each day adds 60 decimals to the exact chain-linked index
    assert rf7_module._episode_peak_distance([Fraction(small)] * 69) is None  # 4140 decimals
    # 80 days need 4800 decimals: past the runtime's 4300-digit rendering limit, so the bound is decided first.
    days = tuple(RegimeConditionedDay(20_000 + offset, TRUSTED, "CALM", small) for offset in range(80))
    stratum = rf7_module._stratum("CALM", days, 2)
    assert (stratum.observation_count, stratum.episode_count, stratum.longest_episode_day_count) == (80, 1, 80)
    assert (stratum.sharpe_status, stratum.drawdown_status, stratum.max_episode_peak_distance) == (
        RegimeStratumMetricStatus.ZERO_VARIANCE,
        RegimeStratumMetricStatus.NOT_REPRESENTABLE,
        None,
    )


@pytest.mark.parametrize(
    ("mean", "rounded"),
    [
        ("0.0000000000000000005", "0.000000000000000000"),
        ("0.0000000000000000015", "0.000000000000000002"),
        ("0.0000000000000000025", "0.000000000000000002"),
        ("-0.0000000000000000025", "-0.000000000000000002"),
        ("-0.0000000000000000005", "0.000000000000000000"),
    ],
)
def test_an_exact_half_unit_ratio_rounds_half_even_once(mean: str, rounded: str) -> None:
    # m - 1, m + 1, m - 1, m + 1, m: the sample variance is exactly 1, so the daily ratio is exactly the mean.
    with decimal.localcontext(decimal.Context(prec=50)):
        returns = [format(Decimal(mean) + offset, "f") for offset in (-1, 1, -1, 1, 0)]
    measurement = measure_regime_stratum_returns(returns)
    assert (measurement.sharpe_status, measurement.mean_daily_return, measurement.paper_sharpe_daily) == (
        COMPUTED,
        rounded,
        rounded,
    )


@pytest.mark.parametrize(
    "bad", ["0.10", "1e-3", "+0.1", "-0", "-0.0", "00.1", ".1", "0.", "", " 0.1", "0.1\u0660", "1" * 4097, 0.1, None, 1]
)
def test_a_non_canonical_daily_return_is_a_defect(bad: object) -> None:
    with refused("daily_return_malformed"):
        measure_regime_stratum_returns(("0.01", bad))  # type: ignore[arg-type]


@pytest.mark.parametrize("bad", ["0.01", None, {"0.01"}])
def test_the_sample_is_an_exact_sequence(bad: object) -> None:
    with refused("daily_returns_malformed"):
        measure_regime_stratum_returns(bad)  # type: ignore[arg-type]


# --- the governed sample floor --------------------------------------------------------------------------------------


def test_strata_below_the_governed_floor_publish_counts_but_never_a_metric() -> None:
    reference = default_report()
    report = build(report_inputs(measurement_policy=measurement_policy(10)))
    assert (report.status, report.min_observations_per_stratum, report.days) == (READY, 10, reference.days)
    assert len(report.strata) == len(reference.strata) == 2
    for stratum, full in zip(report.strata, reference.strata):
        assert (stratum.label_id, stratum.observation_count, stratum.insufficient_sample) == (full.label_id, 9, True)
        assert (stratum.episode_count, stratum.longest_episode_day_count) == (
            full.episode_count,
            full.longest_episode_day_count,
        )
        assert (stratum.sharpe_status, stratum.drawdown_status) == (INSUFFICIENT, INSUFFICIENT)
        assert (
            stratum.mean_daily_return,
            stratum.paper_sharpe_daily,
            stratum.paper_sharpe_annualized,
            stratum.max_episode_peak_distance,
        ) == (None, None, None, None)
    # The floor is inclusive: nine observations meet a floor of nine.
    assert build(report_inputs(measurement_policy=measurement_policy(9))).strata == reference.strata


@pytest.mark.parametrize(
    ("approval", "reason"),
    [
        (None, "governance_approval_missing"),
        (
            {"approval_kind": RegimeFeaturePolicyApprovalKind.TEST_ONLY_SYNTHETIC},
            "governance_approval_test_only_synthetic",
        ),
        ({"approved_policy_digest": "e" * 64}, "governance_approval_policy_digest_mismatch"),
        ({"approved_policy_version": "synthetic-v0"}, "governance_approval_policy_version_mismatch"),
        ({"approved_rule_set_digest": "e" * 64}, "governance_approval_rule_set_digest_mismatch"),
    ],
)
def test_only_an_exact_human_approval_governs_the_measurement_policy(
    approval: dict[str, object] | None, reason: str
) -> None:
    policy = measurement_policy(governed=False) if approval is None else measurement_policy(approval=approval)
    assert (policy.gate_verdict, policy.advances, policy.verdict_reason_codes) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        (code(reason),),
    )
    assert policy.synthetic_test_approval_used is (reason == "governance_approval_test_only_synthetic")
    assert verify_regime_conditioned_performance_policy(policy).intact is True
    governed = default_policy()
    assert (governed.gate_verdict, governed.advances, governed.verdict_reason_codes) == (EdgeGateVerdict.PASS, True, ())


def test_an_ungoverned_measurement_policy_never_measures() -> None:
    report = build(report_inputs(measurement_policy=measurement_policy(governed=False)))
    assert (report.status, report.measurement_policy_governed, report.days, report.strata) == (
        NEEDS_GOVERNANCE,
        False,
        (),
        (),
    )
    assert report.reason_codes == (code("measurement_policy_needs_governance_approval"),)


@pytest.mark.parametrize("value", [1, 0, -3, True, "4", 4.0, None, 2**63])
def test_the_sample_floor_is_an_explicit_integer_of_at_least_two(value: object) -> None:
    with refused("min_observations_per_stratum_invalid"):
        measurement_policy(value)


def test_the_measurement_policy_is_digest_bound_and_reproven() -> None:
    policy = default_policy()
    verification = verify_regime_conditioned_performance_policy(policy)
    assert (verification.intact, verification.recomputed_digest) == (
        True,
        policy.regime_conditioned_performance_policy_digest,
    )
    assert json.loads(verification.canonical_json) == regime_conditioned_performance_policy_to_dict(policy)
    forged = replace(policy, min_observations_per_stratum=2)
    forged = replace(
        forged, regime_conditioned_performance_policy_digest=regime_conditioned_performance_policy_digest(forged)
    )
    for value in (forged, None, "policy", replace(policy, gate_verdict="PASS")):
        assert verify_regime_conditioned_performance_policy(value).intact is False
    with refused("measurement_policy_not_intact"):
        build(report_inputs(measurement_policy=forged))
    with refused("governance_approval_malformed"):
        build_regime_conditioned_performance_policy(
            policy_id="rf7-policy-1",
            policy_version="synthetic-v1",
            min_observations_per_stratum=4,
            approval="approved",  # type: ignore[arg-type]
        )


# --- RF-6 authorization and RG-3 status -----------------------------------------------------------------------------


def rf6_world(case: str) -> RegimeFilterAdmissionInputs:
    """Authentic RF-6 worlds that never admit; their RF-5 days (from 20000) never reach the sleeve window anyway."""

    if case == "v1_preregistration":
        return rf6t.admission_inputs(prereg=rf6t.preregistration())
    if case == "policy_not_registered":
        return rf6t.admission_inputs(prereg=rf6t.preregistration(rf6t.filter_policy(threshold="0.005")))
    if case == "stability_repainted":
        return rf6t.admission_inputs(stability=rf6t.stability_world("UDDU", "UUDUUDU"))
    if case == "external_facts_needed":
        scope = EdgeSurvivorshipClaimScope.EDGE_FAMILY_CROSS_SECTION
        return rf6t.admission_inputs(prereg=rf6t.preregistration(rf6t.policy(), survivorship_claim_scope=scope))
    draft = rf6t.filter_policy(governed=False)
    return rf6t.admission_inputs(
        prereg=rf6t.preregistration(draft), policy_=draft, stability=rf6t.stability_world(policy_=draft)
    )


@pytest.mark.parametrize(
    ("case", "status", "reason"),
    [
        ("v1_preregistration", NOT_ADMITTED, "filter_not_admitted:FAIL"),
        ("policy_not_registered", NOT_ADMITTED, "filter_not_admitted:FAIL"),
        ("stability_repainted", NOT_ADMITTED, "filter_not_admitted:FAIL"),
        ("external_facts_needed", NOT_ADMITTED, "filter_not_admitted:NEEDS_EXTERNAL_FACTS"),
        ("policy_ungoverned", NEEDS_GOVERNANCE, "filter_admission_needs_governance_approval"),
    ],
)
def test_only_an_authentic_pass_admission_is_ever_measured(
    case: str, status: RegimeConditionedPerformanceStatus, reason: str
) -> None:
    inputs = rf6_world(case)
    decision = build_regime_filter_admission_decision(inputs)
    assert decision.regime_filter_admitted is False
    report = build(report_inputs(admission=(inputs, decision)))
    assert (report.status, report.ready, report.filter_admitted, report.reason_codes) == (
        status,
        False,
        False,
        (code(reason),),
    )
    assert report.filter_admission_verdict == decision.gate_verdict.value
    assert (report.days, report.strata, report.trusted_day_count, report.label_days_outside_window_count) == (
        (),
        (),
        0,
        0,
    )


def test_a_filter_whose_proven_labels_miss_the_sleeve_window_is_not_computable() -> None:
    stability = rf6t.default_stability()[1]
    assert stability.overlap_last_day_index is not None and stability.overlap_last_day_index < WINDOW_FIRST
    report = build(report_inputs(admission=(rf6t.admission_inputs(), rf6t.default_decision())))
    assert (report.status, report.filter_admitted, report.reason_codes) == (
        NOT_COMPUTABLE,
        True,
        (code("no_trusted_regime_day"),),
    )


def test_an_incomputable_or_ungoverned_sleeve_is_never_measured() -> None:
    blocked = build(report_inputs(sleeve=sleeve_world(**rg3t.NO_SERIES)))
    assert (blocked.status, blocked.sleeve_performance_status, blocked.reason_codes) == (
        NOT_COMPUTABLE,
        "NOT_COMPUTABLE",
        (code("sleeve_performance_not_computable"),),
    )
    ungoverned = build(report_inputs(sleeve=sleeve_world(portfolio_risk_envelope=rg3t.rg2.build())))
    assert (ungoverned.status, ungoverned.sleeve_performance_status, ungoverned.reason_codes) == (
        NEEDS_GOVERNANCE,
        "NEEDS_GOVERNANCE_APPROVAL",
        (code("sleeve_performance_needs_governance_approval"),),
    )
    for report in (blocked, ungoverned):
        assert (report.days, report.strata, report.trusted_day_count) == ((), (), 0)


def test_status_precedence_keeps_every_reason() -> None:
    inputs = rf6t.admission_inputs(prereg=rf6t.preregistration())
    blocked_sleeve, ungoverned = sleeve_world(**rg3t.NO_SERIES), measurement_policy(governed=False)
    report = decide(
        report_inputs(
            admission=(inputs, build_regime_filter_admission_decision(inputs)),
            sleeve=blocked_sleeve,
            measurement_policy=ungoverned,
        )
    )
    assert report.status is NOT_ADMITTED
    assert report.reason_codes == (
        code("filter_not_admitted:FAIL"),
        code("measurement_policy_needs_governance_approval"),
        code("sleeve_performance_not_computable"),
    )
    pending = build(report_inputs(sleeve=blocked_sleeve, measurement_policy=ungoverned))
    assert pending.status is NEEDS_GOVERNANCE
    assert pending.reason_codes == (
        code("measurement_policy_needs_governance_approval"),
        code("sleeve_performance_not_computable"),
    )


def test_preregistered_hypotheses_are_counted_with_provenance_and_never_corrected() -> None:
    report, ef5 = default_report(), rf6t.sealed()
    assert (report.variant_ledger_digest, report.ledger_variant_count) == (
        ef5.variant_ledger_digest,
        ef5.multiple_testing_count,
    )
    assert (report.regime_filter_set_digest, report.ledger_regime_filter_count) == (
        ef5.regime_filter_set_digest,
        len(ef5.registered_regime_policy_digests),
    )
    assert (
        report.ledger_variant_count,
        report.ledger_regime_filter_count,
        report.preregistered_variant_filter_pair_count,
        report.reported_stratum_count,
    ) == (4, 1, 4, 2)
    assert (report.multiple_testing_correction_applied, report.statistical_significance_proven) == (False, False)
    rf2t = rf6t.rf2t  # a second governed filter needs its own version: EF-5 refuses an ambiguous id and version
    other = rf4t.updown_policy(
        features=[rf2t.feature(rf2t.DD, rf6t.F2, lookback=2, series=rf6t.MARK)], policy_version="synthetic-v2"
    )
    ledger = rf6t.preregistration(rf6t.policy(), other)
    assert (ledger.preregistration_sealed, len(ledger.registered_regime_policy_digests)) == (True, 2)
    world = replace(
        admission_world()[0],
        preregistration=ledger,
        expected_preregistration_digest=ledger.leakage_bias_evidence_digest,
    )
    counted = build(report_inputs(admission=(world, build_regime_filter_admission_decision(world))))
    assert (counted.status, counted.ledger_regime_filter_count, counted.preregistered_variant_filter_pair_count) == (
        READY,
        2,
        8,
    )
    assert counted.regime_filter_set_digest == ledger.regime_filter_set_digest != report.regime_filter_set_digest
    assert counted.strata == report.strata  # counting more hypotheses never changes a measurement


# --- provenance refusals --------------------------------------------------------------------------------------------


def test_every_upstream_is_reproven_against_its_exact_anchor() -> None:
    admission_inputs, decision = admission_world()
    performance_inputs, performance = default_sleeve()
    with refused("filter_admission_digest_mismatch"):
        build(report_inputs(expected_admission_digest=rf6t.default_decision().regime_filter_admission_digest))
    with refused("filter_admission_not_intact"):  # another world's inputs never re-prove this decision
        build(report_inputs(admission=(rf6t.admission_inputs(), decision)))
    with refused("filter_admission_not_intact"):
        build(report_inputs(admission=(admission_inputs, rf6t.reseal(decision, regime_filter_admitted=False))))
    with refused("filter_admission_correlation_mismatch"):
        build(report_inputs(correlation_id="corr-2"))
    with refused("sleeve_performance_digest_mismatch"):
        build(report_inputs(expected_performance_digest=rg3t.world_performance().performance_evidence_digest))
    returns = list(performance.daily_returns)
    returns[3] = "0.5"
    for changes in (
        {"daily_returns": tuple(returns)},
        {"sleeve_id": "sleeve-beta", "market_symbol": "ETH-PERPETUAL"},
        {"window_start_ns": performance.window_start_ns + DAY_NS},
    ):
        forged = replace(performance, **changes)  # type: ignore[arg-type]
        forged = replace(forged, performance_evidence_digest=paper_sleeve_performance_evidence_digest(forged))
        with refused("sleeve_performance_not_intact"):
            build(report_inputs(sleeve=(performance_inputs, forged)))
    with refused("sleeve_performance_not_intact"):  # the RG-3 module's own inputs never re-prove this sleeve
        build(report_inputs(sleeve=(rg3t.performance_inputs(), performance)))


def test_a_forged_label_stability_policy_or_correlation_never_reaches_measurement() -> None:
    admission_inputs, decision = admission_world()
    stability_inputs, stability = admission_inputs.stability_inputs, admission_inputs.stability
    later = stability_inputs.later_labels
    first = later.labels[0]
    flipped = replace(first, label_id="STRESSED" if first.label_id == "CALM" else "CALM")
    labels = replace(later, labels=(flipped, *later.labels[1:]))
    labels = replace(labels, label_evidence_digest=regime_label_evidence_digest(labels))
    repainted = replace(stability, overlap_day_count=99)
    repainted = replace(repainted, stability_evidence_digest=regime_stability_evidence_digest(repainted))
    twin = rf6t.filter_policy(approval={"approval_reference": "governance-record-2"})
    for world in (
        replace(admission_inputs, stability_inputs=replace(stability_inputs, later_labels=labels)),
        replace(admission_inputs, stability=repainted),
        replace(admission_inputs, policy=twin),
        replace(admission_inputs, correlation_id="corr-2"),
    ):
        with refused("filter_admission_not_intact"):
            build(report_inputs(admission=(world, decision)))


@pytest.mark.parametrize(
    ("overrides", "reason"),
    [
        ({"report_id": ""}, "report_id_invalid"),
        ({"report_id": "rf7 live"}, "forbidden_scope_token:report_id"),
        ({"correlation_id": None}, "correlation_id_invalid"),
        ({"measurement_policy": None}, "measurement_policy_malformed"),
        ({"admission_inputs": None}, "admission_inputs_malformed"),
        ({"admission": None}, "admission_malformed"),
        ({"expected_admission_digest": "A" * 64}, "expected_admission_digest_invalid"),
        ({"performance_inputs": None}, "performance_inputs_malformed"),
        ({"performance": None}, "performance_malformed"),
        ({"expected_performance_digest": None}, "expected_performance_digest_invalid"),
    ],
)
def test_malformed_inputs_are_refused(overrides: dict[str, object], reason: str) -> None:
    with refused(reason):
        build(replace(report_inputs(), **overrides))  # type: ignore[arg-type]


def test_inputs_of_another_type_are_refused() -> None:
    with refused("inputs_malformed"):
        build(None)


def test_the_join_refuses_any_geometry_it_cannot_prove() -> None:
    performance = default_sleeve()[1]
    labels = admission_world()[0].stability_inputs.later_labels.labels
    later = rf7_module._labels_by_day(labels)
    overlap = range(20_454, 20_474)
    assert rf7_module._join_days(performance, later, later, overlap) == (default_report().days, 0)
    for changes in (
        {"window_start_ns": performance.window_start_ns + 1, "window_end_ns": performance.window_end_ns + 1},
        {"day_count": WINDOW_DAYS - 1},
        {"daily_returns": performance.daily_returns[:-1]},
    ):
        with refused("sleeve_window_not_on_the_utc_day_grid"):
            rf7_module._join_days(replace(performance, **changes), later, later, overlap)  # type: ignore[arg-type]
    gap = {day: label for day, label in later.items() if day != 20_465}
    with refused("stability_overlap_day_without_a_label"):
        rf7_module._join_days(performance, later, gap, overlap)
    with refused("label_day_duplicate"):
        rf7_module._labels_by_day((labels[0], *labels))


# --- the verifier and the parsers -----------------------------------------------------------------------------------


def test_every_field_is_digest_bound_and_reproven() -> None:
    inputs, report = report_inputs(), default_report()
    stratum, first = report.strata[0], report.days[0]
    changes: dict[str, object] = {
        "status": NOT_COMPUTABLE,
        "trusted_day_count": 19,
        "label_days_outside_window_count": 1,
        "ledger_variant_count": 1,
        "preregistered_variant_filter_pair_count": 1,
        "strategy_spec_attribution_proven": False,
        "sleeve_correlation_id": "corr-1",
        "min_observations_per_stratum": 2,
        "days": (replace(first, label_id="STRESSED" if first.label_id == "CALM" else "CALM"), *report.days[1:]),
        "strata": (replace(stratum, paper_sharpe_daily="9.000000000000000000"), *report.strata[1:]),
        **{name: not default for name, default in REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS},
    }
    assert set(verify(reseal(report, **changes), inputs).reason_codes) == {
        *(code(f"field_mismatch:{name}") for name in changes),
        code("field_mismatch:regime_conditioned_performance_digest"),
    }
    stale = verify(replace(report, report_id="rf7-2"), inputs)
    assert (stale.intact, stale.reason_codes) == (
        False,
        (code("field_mismatch:report_id"), code("self_digest_mismatch")),
    )


def test_the_verifier_is_total() -> None:
    inputs, report = report_inputs(), default_report()
    for value in (None, {}, "report", default_policy(), regime_conditioned_performance_evidence_to_dict(report)):
        assert verify(value, inputs) == EdgeEvidenceVerification(False, (code("evidence_type_invalid"),), "", "")
    for value in (
        replace(report, status="READY"),
        replace(report, window_day_count=-1),
        replace(report, days=list(report.days)),
        replace(report, strata=(replace(report.strata[0], sharpe_status="COMPUTED"), *report.strata[1:])),
    ):
        verification = verify(value, inputs)
        assert (verification.intact, verification.reason_codes) == (False, (code("evidence_serialization_failed"),))
    for broken in (None, replace(inputs, expected_performance_digest="e" * 64)):
        verification = verify(report, broken)
        assert (verification.intact, verification.reason_codes) == (False, (code("evidence_reconstruction_failed"),))


def test_the_report_and_policy_round_trip_through_their_strict_parsers() -> None:
    report, policy = default_report(), default_policy()
    payload = json.loads(edge_canonical_json(regime_conditioned_performance_evidence_to_dict(report)))
    assert regime_conditioned_performance_evidence_from_payload(payload) == report
    assert regime_conditioned_performance_evidence_payload_is_well_formed(payload) is True
    for broken in (
        {**payload, "extra": 1},
        {name: value for name, value in payload.items() if name != "strata"},
        {**payload, "status": "DONE"},
        {**payload, "window_day_count": -1},
        {**payload, "stability_overlap_first_day_index": "20454"},
        {**payload, "days": "days"},
        {**payload, "ready": "true"},
        {**payload, "days": [{**payload["days"][0], "day_class": "TRUSTED_MAYBE"}]},
        {**payload, "strata": [{**payload["strata"][0], "sharpe_status": "GOOD"}]},
        {**payload, "edge_proven": 0},
        [],
        None,
    ):
        assert regime_conditioned_performance_evidence_payload_is_well_formed(broken) is False
    with refused("payload_fields_malformed"):
        regime_conditioned_performance_evidence_from_payload({**payload, "extra": 1})
    policy_payload = json.loads(edge_canonical_json(regime_conditioned_performance_policy_to_dict(policy)))
    assert regime_conditioned_performance_policy_from_payload(policy_payload) == policy
    with refused("payload_field_malformed"):
        regime_conditioned_performance_policy_from_payload({**policy_payload, "min_observations_per_stratum": "4"})
    with refused("payload_fields_malformed"):
        regime_conditioned_performance_policy_from_payload({**policy_payload, "approval": {}})


# --- static discipline, isolation, rule set and API -----------------------------------------------------------------


def test_the_module_is_pure_with_one_assembly_path_per_artifact() -> None:
    pit.assert_module_is_pure(
        rf7_module,
        {
            "crypto_core.strategy.spec",
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_leakage_bias_evidence",
            "crypto_core.validation.paper_sleeve_drawdown_evidence",
            "crypto_core.validation.paper_sleeve_performance_evidence",
            "crypto_core.validation.regime_feature_policy",
            "crypto_core.validation.regime_filter_admission_decision",
        },
    )
    assert "crypto_core.regime." not in SOURCE and "from crypto_core.regime" not in SOURCE
    pit.assert_single_assembly_path(
        rf7_module,
        "RegimeConditionedPerformancePolicy",
        "_assemble_policy",
        "build_regime_conditioned_performance_policy",
        "_reassemble_policy",
    )
    constructors = [
        function.name
        for function in ast.walk(ast.parse(SOURCE))
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "RegimeConditionedPerformanceEvidence"
    ]
    assert constructors == ["build_regime_conditioned_performance_evidence"]


def test_no_accepted_module_consumes_rf7_and_the_ef6_rg5_regime_interfaces_stay_pending() -> None:
    validation = Path(rf7_module.__file__).parent
    readers = sorted(
        path.name
        for path in validation.parent.rglob("*.py")
        if path.name != "regime_conditioned_performance_evidence.py"
        and "regime_conditioned_performance_evidence" in path.read_text(encoding="utf-8")
    )
    assert readers == []
    walk_forward = (validation / "edge_walk_forward_oos_evidence.py").read_text(encoding="utf-8")
    correlation = (validation / "paper_sleeve_correlation_evidence.py").read_text(encoding="utf-8")
    assert "regime_split_explicit_unavailable_until_accepted_rf_chain.v1" in walk_forward
    assert "regime_stratified_correlation_pending_until_an_accepted_rf_chain.v1" in correlation
    assert default_sleeve()[1].regime_evidence_available is False


def test_the_report_names_only_structural_false_claims_and_no_builder_can_set_them() -> None:
    flags = dict(REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS)
    assert set(flags) == ({name for name, _ in REGIME_NON_CLAIM_FLAGS} - {"regime_filter_admitted"}) | {
        "statistical_significance_proven",
        "multiple_testing_correction_applied",
        "strategy_causation_proven",
        "chronological_ordering_proven",
        "candidate_paper_admission_proven",
        "variant_attribution_proven",
        "episode_set_completeness_proven",
    }
    assert flags["regime_conditioned_performance_proven"] is False  # a measurement, never a proven conditional effect
    assert {item.name: item.default for item in fields(RegimeConditionedPerformanceEvidence) if item.name in flags} == (
        flags
    )
    assert all(
        item.default is dataclasses.MISSING
        for item in fields(RegimeConditionedPerformanceEvidence)
        if item.name not in flags
    )
    for cls in (
        RegimeConditionedPerformanceInputs,
        RegimeConditionedDay,
        RegimeStratumPerformance,
        RegimeConditionedPerformanceApproval,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(cls))
    assert set(inspect.signature(build_regime_conditioned_performance_evidence).parameters) == {"inputs"}
    assert all(
        parameter.default is inspect.Parameter.empty
        for parameter in inspect.signature(build_regime_conditioned_performance_policy).parameters.values()
    )
    tree = ast.parse(SOURCE)
    keywords = {keyword.arg for node in ast.walk(tree) if isinstance(node, ast.Call) for keyword in node.keywords}
    assert not keywords & set(flags)
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    risky = {
        name
        for name in names
        if re.search(r"(^|_)(live|orders?|capital|scheduler|connector|shadow|execution)(_|$)", name)
    }
    assert risky <= set(flags)


def test_the_rule_set_commits_the_methodology_and_is_handed_out_fresh() -> None:
    rule_set = regime_conditioned_performance_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST
    assert (rule_set["contract_id"], rule_set["join_rule_id"], rule_set["drawdown_rule_id"]) == (
        "RF7_REGIME_CONDITIONED_PERFORMANCE_EVIDENCE_V1",
        "RF7_EXACT_UTC_DAY_JOIN_V1",
        "RF7_EPISODE_PEAK_DISTANCE_V1",
    )
    assert (rule_set["risk_free_policy_id"], rule_set["stddev_policy_id"]) == (
        "constant_zero_daily_review_only.v1",
        "sample_stddev_n_minus_1.v1",
    )
    assert (rule_set["annualization_factor"], rule_set["minimum_observations_floor"]) == (365, 2)
    assert "no_correction" in str(rule_set["multiple_testing_rule_id"])
    rule_set["contract_id"] = "OTHER"
    assert regime_conditioned_performance_rule_set()["contract_id"] == "RF7_REGIME_CONDITIONED_PERFORMANCE_EVIDENCE_V1"


def test_the_public_api_is_exact() -> None:
    assert set(rf7_module.__all__) == {
        "REGIME_CONDITIONED_PERFORMANCE_NON_CLAIM_FLAGS",
        "REGIME_CONDITIONED_PERFORMANCE_RULE_SET_DIGEST",
        "RegimeConditionedDay",
        "RegimeConditionedDayClass",
        "RegimeConditionedPerformanceApproval",
        "RegimeConditionedPerformanceError",
        "RegimeConditionedPerformanceEvidence",
        "RegimeConditionedPerformanceInputs",
        "RegimeConditionedPerformancePolicy",
        "RegimeConditionedPerformanceStatus",
        "RegimeStratumMetricStatus",
        "RegimeStratumPerformance",
        "RegimeStratumReturnMeasurement",
        "build_regime_conditioned_performance_evidence",
        "build_regime_conditioned_performance_policy",
        "measure_regime_stratum_returns",
        "regime_conditioned_performance_evidence_digest",
        "regime_conditioned_performance_evidence_from_payload",
        "regime_conditioned_performance_evidence_payload_is_well_formed",
        "regime_conditioned_performance_evidence_to_dict",
        "regime_conditioned_performance_policy_digest",
        "regime_conditioned_performance_policy_from_payload",
        "regime_conditioned_performance_policy_to_dict",
        "regime_conditioned_performance_rule_set",
        "verify_regime_conditioned_performance_evidence",
        "verify_regime_conditioned_performance_policy",
    }
