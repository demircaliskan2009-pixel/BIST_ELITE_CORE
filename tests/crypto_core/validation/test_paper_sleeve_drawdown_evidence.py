"""RG-4 paper sleeve and portfolio drawdown evidence tests (RG4_PAPER_SLEEVE_DRAWDOWN_EVIDENCE_V1).

SYNTHETIC TEST VALUES ONLY. The sleeve worlds, the RG-2 envelopes, the performance-path policies, their performance
weights and every approval are synthetic fixtures; none is a production value, none is a recommended weighting and
none is production-approved. Every sleeve world is built ONLY through the accepted public builders, exactly as the RG-3
tests build theirs, and every expected path is recomputed here by an independent exact oracle.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import json
import re
from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_drawdown_evidence as drawdown_module
from crypto_core.validation.edge_artifact_core import EdgeEvidenceVerification, edge_canonical_json, edge_sha256_text
from crypto_core.validation.paper_order_intent_admission import PaperOrderSide
from crypto_core.validation.paper_portfolio_performance_path_policy import (
    PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
    PaperPortfolioPerformancePathPolicy,
)
from crypto_core.validation.paper_portfolio_risk_envelope import PaperPortfolioRiskEnvelope
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveDailyValuationEvidence,
    PaperSleeveValuationInputs,
    build_paper_sleeve_daily_valuation_evidence,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST,
    PaperPeakDistanceMeasurement,
    PaperPortfolioDrawdownRecord,
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownEvidenceError,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownRecord,
    PaperSleeveDrawdownSleeveInputs,
    PaperSleeveDrawdownStatus,
    build_paper_sleeve_drawdown_evidence,
    measure_paper_peak_distance,
    paper_sleeve_drawdown_evidence_digest,
    paper_sleeve_drawdown_evidence_to_dict,
    paper_sleeve_drawdown_rule_set,
    verify_paper_sleeve_drawdown_evidence,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    paper_sleeve_performance_evidence_digest,
    paper_sleeve_performance_evidence_to_dict,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so the authentic worlds and their caches are built once
    import test_paper_portfolio_performance_path_policy as rg4p
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_performance_evidence as rg3t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_portfolio_performance_path_policy as rg4p
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t

_PREFIX = "paper_sleeve_drawdown_evidence"
_READY = PaperSleeveDrawdownStatus.READY
_NOT_COMPUTABLE = PaperSleeveDrawdownStatus.NOT_COMPUTABLE
_NEEDS_GOVERNANCE = PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL
_RG3_READY = PaperSleevePerformanceStatus.READY
INT64_MAX = 9223372036854775807
ALPHA, BETA, GAMMA = "sleeve-alpha", "sleeve-beta", "sleeve-gamma"
W0, DAY, HOUR = world.WINDOW_START, world.DAY_NS, world.HOUR_NS
WINDOW_END = world.WINDOW_END
REBALANCING_CONVENTION = "NO_REBALANCE_WITHIN_EVIDENCE_WINDOW_V1"
# SYNTHETIC TEST weights only; deliberately unequal and never derived from any cap, budget or reference notional.
WORLD_WEIGHTS = ((ALPHA, "0.6"), (BETA, "0.4"))
THREE_WEIGHTS = ((ALPHA, "0.5"), (BETA, "0.3"), (GAMMA, "0.2"))
SLEEVE_PLANS: dict[str, tuple[world.EpisodePlan, ...]] = {
    BETA: (
        world.EpisodePlan("b1", PaperOrderSide.SELL, "3", "100", W0 + 5 * HOUR),
        world.EpisodePlan("b2", PaperOrderSide.BUY, "3", "97", W0 + 6 * DAY + 6 * HOUR),
        world.EpisodePlan("b3", PaperOrderSide.BUY, "5", "99", W0 + 12 * DAY + 7 * HOUR),
        world.EpisodePlan("b4", PaperOrderSide.SELL, "5", "103", W0 + 25 * DAY + 9 * HOUR),
    ),
    GAMMA: (
        world.EpisodePlan("g1", PaperOrderSide.BUY, "2", "101", W0 + 2 * DAY + 3 * HOUR),
        world.EpisodePlan("g2", PaperOrderSide.SELL, "2", "104", W0 + 9 * DAY + 4 * HOUR),
        world.EpisodePlan("g3", PaperOrderSide.SELL, "4", "102", W0 + 15 * DAY + 5 * HOUR),
        world.EpisodePlan("g4", PaperOrderSide.BUY, "4", "98", W0 + 27 * DAY + 8 * HOUR),
    ),
}


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


class _List(list):
    """A ``list`` subclass, refused wherever an exact caller sequence is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleeveDrawdownEvidenceError, match=f"^{re.escape(_code(code))}$")


# --- genuine sleeve worlds ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SleeveWorld:
    """One genuine sleeve: its RG-3 inputs and the RG-3 evidence built from them."""

    inputs: PaperSleevePerformanceInputs
    evidence: PaperSleevePerformanceEvidence

    def drawdown_inputs(self) -> PaperSleeveDrawdownSleeveInputs:
        return PaperSleeveDrawdownSleeveInputs(performance_inputs=self.inputs, performance_evidence=self.evidence)


@functools.lru_cache(maxsize=None)
def _valuation_world(
    sleeve_id: str, reference_notional: str
) -> tuple[PaperSleeveValuationInputs, PaperSleeveDailyValuationEvidence, rg3t.SeriesWorld]:
    """A genuine sleeve valuation and its generic series world over the shared evidence window."""

    policy_id = sleeve_id.replace("sleeve", "policy")
    episodes = world.build_chain(
        SLEEVE_PLANS[sleeve_id],
        draft=world.make_draft(sleeve_id, policy_id),
        capacity_policy=world.make_capacity_policy(sleeve_id, policy_id),
    )
    basis = world.basis_policy(sleeve_id=sleeve_id, reference_notional=reference_notional)
    valuation_inputs = world.valuation_inputs(
        valuation_id=f"sleeve-valuation-{sleeve_id}",
        episodes=episodes,
        day_closes=tuple(world.build_day_close(day, episodes) for day in range(world.WINDOW_DAYS)),
        equity_basis_policy=basis,
        funding_evidence=world.funding_evidence(sleeve_id=sleeve_id, events=world.funding_events(episodes)),
    )
    valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
    return valuation_inputs, valuation, rg3t.series_world(valuation, basis, W0, WINDOW_END)


@functools.lru_cache(maxsize=None)
def sleeve_world(
    sleeve_id: str, envelope: PaperPortfolioRiskEnvelope | None = None, reference_notional: str = "1000"
) -> SleeveWorld:
    """The genuine world of ``sleeve_id`` whose RG-3 evidence re-pins ``envelope`` (the RG-2 fixture by default)."""

    envelope = rg3t.world_envelope() if envelope is None else envelope
    if sleeve_id == ALPHA:
        inputs = rg3t.performance_inputs(portfolio_risk_envelope=envelope)
    else:
        valuation_inputs, valuation, series = _valuation_world(sleeve_id, reference_notional)
        inputs = rg3t.performance_inputs(
            performance_evidence_id=f"rg3-{sleeve_id}-1",
            portfolio_risk_envelope=envelope,
            valuation_inputs=valuation_inputs,
            valuation=valuation,
            **series.inputs(),
        )
    return SleeveWorld(inputs, rg3t.build(inputs))


@functools.lru_cache(maxsize=None)
def policy_for(
    envelope: PaperPortfolioRiskEnvelope | None = None,
    pairs: tuple[tuple[str, str], ...] = WORLD_WEIGHTS,
    approved: bool = True,
) -> PaperPortfolioPerformancePathPolicy:
    """The synthetic performance-path policy over ``envelope``; ``approved`` adds an exact synthetic test approval."""

    args: dict[str, object] = {
        "portfolio_risk_envelope": rg3t.world_envelope() if envelope is None else envelope,
        "performance_weights": [rg4p.weight(sleeve_id, value) for sleeve_id, value in pairs],
    }
    return rg4p.governed(**args) if approved else rg4p.build(**args)


def drawdown_inputs(**overrides: object) -> PaperSleeveDrawdownInputs:
    values: dict[str, object] = {
        "drawdown_evidence_id": "rg4-drawdown-1",
        "correlation_id": "corr-rg4",
        "portfolio_risk_envelope": rg3t.world_envelope(),
        "performance_path_policy": policy_for(),
        "window_start_ns": W0,
        "window_end_ns": WINDOW_END,
        "sleeves": (sleeve_world(ALPHA).drawdown_inputs(), sleeve_world(BETA).drawdown_inputs()),
    }
    values.update(overrides)
    return PaperSleeveDrawdownInputs(**values)  # type: ignore[arg-type]


def three_sleeve_inputs(**overrides: object) -> PaperSleeveDrawdownInputs:
    envelope = rg4p.three_sleeve_envelope()
    values: dict[str, object] = {
        "portfolio_risk_envelope": envelope,
        "performance_path_policy": policy_for(envelope, THREE_WEIGHTS),
        "sleeves": tuple(sleeve_world(sleeve_id, envelope).drawdown_inputs() for sleeve_id in (ALPHA, BETA, GAMMA)),
    }
    values.update(overrides)
    return drawdown_inputs(**values)


def build(inputs: object) -> PaperSleeveDrawdownEvidence:
    return build_paper_sleeve_drawdown_evidence(inputs)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def world_drawdown() -> PaperSleeveDrawdownEvidence:
    return build(drawdown_inputs())


def verify(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_drawdown_evidence(evidence, inputs)  # type: ignore[arg-type]


def _reseal(evidence: PaperSleeveDrawdownEvidence, **changes: object) -> PaperSleeveDrawdownEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, drawdown_evidence_digest=paper_sleeve_drawdown_evidence_digest(changed))


def _reseal_rg3(evidence: PaperSleevePerformanceEvidence, **changes: object) -> PaperSleevePerformanceEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, performance_evidence_digest=paper_sleeve_performance_evidence_digest(changed))


def _assert_intact(evidence: PaperSleeveDrawdownEvidence, inputs: PaperSleeveDrawdownInputs) -> None:
    verification = verify(evidence, inputs)
    assert verification.intact is True, verification.reason_codes
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == evidence.drawdown_evidence_digest
    assert json.loads(verification.canonical_json) == paper_sleeve_drawdown_evidence_to_dict(evidence)


# --- the independent exact oracle -----------------------------------------------------------------------------------


def oracle_index(evidence: PaperSleevePerformanceEvidence) -> list[Fraction]:
    """The accepted chain-linked index rule, recomputed independently from the RG-3 daily returns."""

    path = [Fraction(1)]
    for text in evidence.daily_returns:
        path.append(path[-1] * (1 + Fraction(text)))
    return path


def oracle_portfolio(pairs: Sequence[tuple[str, str]], paths: dict[str, list[Fraction]]) -> list[Fraction]:
    """``P_t = sum_i(w_i * I_i,t)`` with fixed weights, recomputed independently."""

    weights = {sleeve_id: Fraction(value) for sleeve_id, value in pairs}
    steps = len(next(iter(paths.values())))
    return [
        sum((weights[sleeve_id] * paths[sleeve_id][step] for sleeve_id in weights), Fraction(0))
        for step in range(steps)
    ]


def oracle_peak_distance(path: Sequence[Fraction]) -> tuple[list[Fraction], list[Fraction]]:
    """Running peak from the start one, and ``(peak - value) / peak`` at every observation."""

    peaks: list[Fraction] = []
    distances: list[Fraction] = []
    peak = Fraction(1)
    for value in path:
        peak = max(peak, value)
        peaks.append(peak)
        distances.append((peak - value) / peak)
    return peaks, distances


_DECIMAL_TEXT = re.compile(r"(0|[1-9][0-9]*)(\.[0-9]*[1-9])?")


def assert_measures(measurement: PaperPeakDistanceMeasurement | None, path: Sequence[Fraction]) -> None:
    """The measurement equals the oracle exactly and every value is canonical text."""

    assert measurement is not None
    peaks, distances = oracle_peak_distance(path)
    assert [Fraction(text) for text in measurement.index_path] == list(path)
    assert [Fraction(text) for text in measurement.running_peak_path] == peaks
    assert [Fraction(text) for text in measurement.peak_distance_path] == distances
    assert Fraction(measurement.current_peak_distance) == distances[-1]
    assert Fraction(measurement.max_peak_distance) == max(distances)
    assert all(_DECIMAL_TEXT.fullmatch(text) for text in (*measurement.index_path, *measurement.running_peak_path))
    for text in (*measurement.peak_distance_path, measurement.max_peak_distance):
        value = Fraction(text)
        assert text == f"{value.numerator}/{value.denominator}"
        assert 0 <= value < 1


# --- B. RG-3 re-proof -----------------------------------------------------------------------------------------------


def test_every_sleeve_world_is_genuine_ready_rg3_evidence() -> None:
    for sleeve_id in (ALPHA, BETA):
        evidence = sleeve_world(sleeve_id).evidence
        assert evidence.status is _RG3_READY, evidence.reason_codes
        assert evidence.sleeve_id == sleeve_id
        assert (evidence.window_start_ns, evidence.window_end_ns, evidence.day_count) == (
            W0,
            WINDOW_END,
            world.WINDOW_DAYS,
        )
        assert len(evidence.daily_returns) == world.WINDOW_DAYS


def test_world_drawdown_is_ready_and_binds_every_reproven_digest() -> None:
    evidence = world_drawdown()
    envelope = rg3t.world_envelope()
    policy = policy_for()
    assert evidence.status is _READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert (evidence.drawdown_evidence_id, evidence.correlation_id) == ("rg4-drawdown-1", "corr-rg4")
    assert (evidence.envelope_digest, evidence.envelope_policy_digest, evidence.envelope_advances) == (
        envelope.envelope_digest,
        envelope.policy_digest,
        True,
    )
    assert (
        evidence.performance_path_policy_digest,
        evidence.performance_path_governed_digest,
        evidence.performance_path_policy_advances,
        evidence.performance_path_rule_set_digest,
    ) == (
        policy.performance_path_policy_digest,
        policy.policy_digest,
        True,
        PAPER_PORTFOLIO_PERFORMANCE_PATH_RULE_SET_DIGEST,
    )
    assert evidence.rebalancing_convention == REBALANCING_CONVENTION
    assert (evidence.window_start_ns, evidence.window_end_ns, evidence.day_count) == (W0, WINDOW_END, world.WINDOW_DAYS)
    assert evidence.rule_set_digest == PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST
    assert evidence.missing_sleeve_ids == ()
    assert [record.sleeve_id for record in evidence.sleeves] == [ALPHA, BETA]
    for record in evidence.sleeves:
        rg3 = sleeve_world(record.sleeve_id).evidence
        assert (record.market_symbol, record.performance_evidence_digest, record.performance_status) == (
            rg3.market_symbol,
            rg3.performance_evidence_digest,
            "READY",
        )
        assert (record.computed, record.reason_codes) == (True, ())
    assert evidence.portfolio.computed is True
    assert evidence.portfolio.performance_weights == policy.performance_weights
    assert evidence.portfolio.reason_codes == ()
    _assert_intact(evidence, drawdown_inputs())


RG3_FORGERIES: dict[str, Callable[[PaperSleevePerformanceEvidence], PaperSleevePerformanceEvidence]] = {
    "resealed_return": lambda e: _reseal_rg3(e, daily_returns=(*e.daily_returns[:3], "0.5", *e.daily_returns[4:])),
    "resealed_sharpe": lambda e: _reseal_rg3(e, paper_sharpe_annualized="9.9"),
    "resealed_window": lambda e: _reseal_rg3(e, day_count=e.day_count - 1),
    "stale_digest": lambda e: replace(e, performance_evidence_digest="0" * 64),
    "beta_evidence": lambda e: sleeve_world(BETA).evidence,
}


@pytest.mark.parametrize("name", sorted(RG3_FORGERIES))
def test_rg3_evidence_that_is_not_the_reconstruction_is_refused(name: str) -> None:
    alpha = sleeve_world(ALPHA)
    forged = RG3_FORGERIES[name](alpha.evidence)
    sleeves = (PaperSleeveDrawdownSleeveInputs(alpha.inputs, forged), sleeve_world(BETA).drawdown_inputs())
    with _raises("sleeve_performance_not_reconstructed"):
        build(drawdown_inputs(sleeves=sleeves))


def test_rg3_evidence_over_another_envelope_is_refused() -> None:
    foreign = sleeve_world(ALPHA, rg2.governed(total_paper_risk_budget=rg2.d("1200")))
    assert foreign.evidence.status is _RG3_READY
    with _raises("sleeve_performance_envelope_mismatch"):
        build(drawdown_inputs(sleeves=(foreign.drawdown_inputs(), sleeve_world(BETA).drawdown_inputs())))


SLEEVE_ITEMS: dict[str, tuple[Callable[[SleeveWorld], object], str]] = {
    "plain_tuple": (lambda s: (s.inputs, s.evidence), "sleeve_malformed"),
    "inputs_missing": (lambda s: PaperSleeveDrawdownSleeveInputs(None, s.evidence), "performance_inputs_malformed"),
    "evidence_missing": (lambda s: PaperSleeveDrawdownSleeveInputs(s.inputs, None), "performance_evidence_malformed"),
    "evidence_payload": (
        lambda s: PaperSleeveDrawdownSleeveInputs(s.inputs, paper_sleeve_performance_evidence_to_dict(s.evidence)),
        "performance_evidence_malformed",
    ),
    "inputs_unbuildable": (
        lambda s: PaperSleeveDrawdownSleeveInputs(replace(s.inputs, valuation_inputs="valuation"), s.evidence),
        "sleeve_performance_reconstruction_failed",
    ),
}


@pytest.mark.parametrize("name", sorted(SLEEVE_ITEMS))
def test_every_sleeve_item_is_an_exact_record_rebuilt_through_rg3(name: str) -> None:
    make, code = SLEEVE_ITEMS[name]
    with _raises(code):
        build(drawdown_inputs(sleeves=(make(sleeve_world(ALPHA)), sleeve_world(BETA).drawdown_inputs())))


def test_a_sleeve_supplied_twice_is_refused() -> None:
    alpha = sleeve_world(ALPHA).drawdown_inputs()
    with _raises("sleeve_duplicate"):
        build(drawdown_inputs(sleeves=(alpha, sleeve_world(BETA).drawdown_inputs(), alpha)))


@pytest.mark.parametrize(
    "sleeves", [None, "sleeves", {}, _List(), frozenset()], ids=["none", "text", "dict", "list_subclass", "set"]
)
def test_the_sleeves_are_an_exact_sequence(sleeves: object) -> None:
    with _raises("sleeves_malformed"):
        build(drawdown_inputs(sleeves=sleeves))


def test_sleeve_order_and_sequence_type_do_not_change_the_evidence() -> None:
    alpha, beta = (sleeve_world(sleeve_id).drawdown_inputs() for sleeve_id in (ALPHA, BETA))
    assert build(drawdown_inputs(sleeves=(beta, alpha))) == world_drawdown()
    assert build(drawdown_inputs(sleeves=[alpha, beta])) == world_drawdown()


FORGED_RECONSTRUCTIONS: dict[str, tuple[Callable[[PaperSleevePerformanceEvidence], dict[str, object]], str]] = {
    "returns_off_the_window": (
        lambda e: {"daily_returns": e.daily_returns[:-1]},
        "sleeve_daily_returns_not_the_evidence_window",
    ),
    "total_loss": (lambda e: {"daily_returns": ("-1", *e.daily_returns[1:])}, "sleeve_index_not_positive"),
    "noncanonical_return": (lambda e: {"daily_returns": ("0.10", *e.daily_returns[1:])}, "sleeve_daily_return_invalid"),
    "uncovered_sleeve": (lambda e: {"sleeve_id": "sleeve-delta"}, "sleeve_not_covered_by_performance_path_policy"),
}


@pytest.mark.parametrize("name", sorted(FORGED_RECONSTRUCTIONS))
def test_defense_in_depth_guards_fail_closed_on_a_forged_reconstruction(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    change, code = FORGED_RECONSTRUCTIONS[name]
    alpha = sleeve_world(ALPHA)
    forged = replace(alpha.evidence, **change(alpha.evidence))
    monkeypatch.setattr(drawdown_module, "build_paper_sleeve_performance_evidence", lambda _inputs: forged)
    with _raises(code):
        build(drawdown_inputs(sleeves=(PaperSleeveDrawdownSleeveInputs(alpha.inputs, forged),)))


def test_a_methodology_that_does_not_start_at_one_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    alpha = sleeve_world(ALPHA)
    assert alpha.inputs.methodology is not None
    shifted = replace(alpha.inputs, methodology=replace(alpha.inputs.methodology, normalized_index_start="2"))
    monkeypatch.setattr(drawdown_module, "build_paper_sleeve_performance_evidence", lambda _inputs: alpha.evidence)
    with _raises("sleeve_index_start_not_one"):
        build(drawdown_inputs(sleeves=(PaperSleeveDrawdownSleeveInputs(shifted, alpha.evidence),)))


# --- C. initial peak and the exact peak-distance math -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "peaks", "distances", "current", "maximum"),
    [
        pytest.param(("1",), ("1",), ("0/1",), "0/1", "0/1", id="start_only"),
        pytest.param(("1", "1", "1"), ("1", "1", "1"), ("0/1", "0/1", "0/1"), "0/1", "0/1", id="flat"),
        pytest.param(("1", "0.9"), ("1", "1"), ("0/1", "1/10"), "1/10", "1/10", id="first_day_loss_against_the_start"),
        pytest.param(
            ("1", "1.2", "0.9"), ("1", "1.2", "1.2"), ("0/1", "0/1", "1/4"), "1/4", "1/4", id="rise_then_fall"
        ),
        pytest.param(
            ("1", "1.1", "0.99", "1.05"),
            ("1", "1.1", "1.1", "1.1"),
            ("0/1", "0/1", "1/10", "1/22"),
            "1/22",
            "1/10",
            id="partial_recovery_current_below_maximum",
        ),
        pytest.param(
            ("1", "0.8", "1"), ("1", "1", "1"), ("0/1", "1/5", "0/1"), "0/1", "1/5", id="recovery_to_the_peak"
        ),
        pytest.param(
            ("1", "0.8", "1.25", "1"),
            ("1", "1", "1.25", "1.25"),
            ("0/1", "1/5", "0/1", "1/5"),
            "1/5",
            "1/5",
            id="new_high_then_fall",
        ),
        pytest.param(
            ("1", "1.5", "1.5", "1.2"),
            ("1", "1.5", "1.5", "1.5"),
            ("0/1", "0/1", "0/1", "1/5"),
            "1/5",
            "1/5",
            id="repeated_peak",
        ),
        pytest.param(
            ("1", "0.5", "0.75", "0.6"),
            ("1", "1", "1", "1"),
            ("0/1", "1/2", "1/4", "2/5"),
            "2/5",
            "1/2",
            id="never_regains_the_start",
        ),
    ],
)
def test_peak_distance_is_exact_with_the_start_as_the_first_peak(
    path: tuple[str, ...], peaks: tuple[str, ...], distances: tuple[str, ...], current: str, maximum: str
) -> None:
    measurement = measure_paper_peak_distance(list(path))
    assert measurement == PaperPeakDistanceMeasurement(path, peaks, distances, current, maximum)
    assert_measures(measurement, [Fraction(text) for text in path])


def test_the_start_observation_participates_in_the_running_peak() -> None:
    measurement = measure_paper_peak_distance(["1", "0.9", "0.95"])
    assert measurement.running_peak_path == ("1", "1", "1")
    assert measurement.peak_distance_path == ("0/1", "1/10", "1/20")
    # A path whose running peak started at its first post-start observation would report the 0.9 low as no drawdown.
    rule_set = paper_sleeve_drawdown_rule_set()
    assert rule_set["initial_index"] == "1"
    assert "the_start_observation_one_is_the_first_running_peak_observation" in str(rule_set["initial_peak_rule_id"])


def test_peak_distance_stays_strictly_below_one_near_zero() -> None:
    measurement = measure_paper_peak_distance(["1", "0.000000000000000001"])
    assert measurement.max_peak_distance == "999999999999999999/1000000000000000000"


def test_a_distance_at_a_decimal_threshold_is_exact_never_rounded() -> None:
    threshold = Fraction("0.05")
    at = measure_paper_peak_distance(["1", "0.95"])
    inside = measure_paper_peak_distance(["1", "0.950000000000000001"])
    beyond = measure_paper_peak_distance(["1", "0.949999999999999999"])
    assert at.max_peak_distance == "1/20"
    assert Fraction(at.max_peak_distance) == threshold
    assert Fraction(inside.max_peak_distance) < threshold < Fraction(beyond.max_peak_distance)


def test_every_prefix_measures_exactly_its_own_past() -> None:
    path = world_drawdown().portfolio.measurement.index_path  # type: ignore[union-attr]
    full = measure_paper_peak_distance(list(path))
    for end in range(1, len(path) + 1):
        prefix = measure_paper_peak_distance(list(path[:end]))
        assert prefix.running_peak_path == full.running_peak_path[:end]
        assert prefix.peak_distance_path == full.peak_distance_path[:end]
        assert prefix.current_peak_distance == full.peak_distance_path[end - 1]
        assert Fraction(prefix.max_peak_distance) == max(Fraction(text) for text in full.peak_distance_path[:end])


@pytest.mark.parametrize(
    ("path", "code"),
    [
        pytest.param(None, "index_path_malformed", id="none"),
        pytest.param("1", "index_path_malformed", id="text"),
        pytest.param(_List(["1"]), "index_path_malformed", id="list_subclass"),
        pytest.param((text for text in ["1"]), "index_path_malformed", id="generator"),
        pytest.param([], "index_path_empty", id="empty"),
        pytest.param(["1.1", "1"], "index_path_start_not_one", id="start_above_one"),
        pytest.param(["0.5"], "index_path_start_not_one", id="start_below_one"),
        pytest.param(["1", "0"], "index_path_observation_not_positive", id="zero"),
        pytest.param(["1", "-0.5"], "index_path_observation_not_positive", id="negative"),
        pytest.param(["1.0"], "index_path_observation_invalid", id="trailing_zero"),
        pytest.param(["1", "1e0"], "index_path_observation_invalid", id="exponent"),
        pytest.param(["1", "+1"], "index_path_observation_invalid", id="plus_sign"),
        pytest.param(["1", "01"], "index_path_observation_invalid", id="leading_zero"),
        pytest.param(["1", "-0"], "index_path_observation_invalid", id="negative_zero"),
        pytest.param(["1", " 1"], "index_path_observation_invalid", id="padded"),
        pytest.param(["1", ""], "index_path_observation_invalid", id="empty_text"),
        pytest.param(["1", "1."], "index_path_observation_invalid", id="bare_point"),
        pytest.param(["1", ".5"], "index_path_observation_invalid", id="bare_fraction"),
        pytest.param(["1", "1/2"], "index_path_observation_invalid", id="fraction_text"),
        pytest.param(["1", 1], "index_path_observation_invalid", id="int"),
        pytest.param(["1", 1.0], "index_path_observation_invalid", id="float"),
        pytest.param(["1", Fraction(1)], "index_path_observation_invalid", id="fraction"),
        pytest.param(["1", _Text("1")], "index_path_observation_invalid", id="text_subclass"),
        pytest.param(["1", "1." + "1" * 4095], "index_path_observation_invalid", id="over_the_text_bound"),
    ],
)
def test_an_invalid_index_path_is_refused(path: object, code: str) -> None:
    with _raises(code):
        measure_paper_peak_distance(path)  # type: ignore[arg-type]


def test_an_exceeded_representation_bound_is_refused_never_rounded() -> None:
    peak = "9" * 2000 + ".5"
    later = "1." + "1" * 4000
    assert measure_paper_peak_distance(["1", peak]).max_peak_distance == "0/1"
    with _raises("measurement_representation_bound_exceeded"):
        measure_paper_peak_distance(["1", peak, later])


# --- D. sleeve and portfolio index paths ------------------------------------------------------------------------------


def test_sleeve_index_paths_are_the_accepted_chain_linked_rg3_index() -> None:
    evidence = world_drawdown()
    for record in evidence.sleeves:
        sleeve = sleeve_world(record.sleeve_id)
        measurement = record.measurement
        assert measurement is not None
        assert len(measurement.index_path) == evidence.day_count + 1
        assert (measurement.index_path[0], measurement.running_peak_path[0], measurement.peak_distance_path[0]) == (
            "1",
            "1",
            "0/1",
        )
        # The accepted valuation's own normalized index chain, carried day by day, is exactly the measured path.
        assert measurement.index_path == ("1", *(day.normalized_index_end for day in sleeve.inputs.valuation.days))
        assert_measures(measurement, oracle_index(sleeve.evidence))


def test_the_portfolio_index_is_the_fixed_weight_convex_combination() -> None:
    evidence = world_drawdown()
    measurement = evidence.portfolio.measurement
    assert measurement is not None
    assert len(measurement.index_path) == evidence.day_count + 1
    assert (measurement.index_path[0], measurement.running_peak_path[0], measurement.peak_distance_path[0]) == (
        "1",
        "1",
        "0/1",
    )
    paths = {sleeve_id: oracle_index(sleeve_world(sleeve_id).evidence) for sleeve_id in (ALPHA, BETA)}
    assert_measures(measurement, oracle_portfolio(WORLD_WEIGHTS, paths))


# --- E. portfolio composition and the exact UTC-day grid ------------------------------------------------------------


def test_three_sleeves_combine_with_their_governed_weights() -> None:
    inputs = three_sleeve_inputs()
    evidence = build(inputs)
    assert evidence.status is _READY, evidence.reason_codes
    envelope = rg4p.three_sleeve_envelope()
    paths = {sleeve_id: oracle_index(sleeve_world(sleeve_id, envelope).evidence) for sleeve_id in (ALPHA, BETA, GAMMA)}
    assert_measures(evidence.portfolio.measurement, oracle_portfolio(THREE_WEIGHTS, paths))
    reordered = three_sleeve_inputs(sleeves=tuple(reversed(inputs.sleeves)))
    assert build(reordered) == evidence
    _assert_intact(evidence, inputs)


def test_the_portfolio_never_rebalances_within_the_window() -> None:
    weights = {sleeve_id: Fraction(value) for sleeve_id, value in WORLD_WEIGHTS}
    returns = {
        sleeve_id: [Fraction(text) for text in sleeve_world(sleeve_id).evidence.daily_returns] for sleeve_id in weights
    }
    rebalanced = [Fraction(1)]
    for day in range(world.WINDOW_DAYS):
        rebalanced.append(
            rebalanced[-1] * (1 + sum(weights[sleeve_id] * returns[sleeve_id][day] for sleeve_id in weights))
        )
    evidence = world_drawdown()
    carried = [Fraction(text) for text in evidence.portfolio.measurement.index_path]  # type: ignore[union-attr]
    assert carried[:2] == rebalanced[:2]  # identical until the sleeve weights first drift
    assert carried != rebalanced
    assert evidence.rebalancing_convention == REBALANCING_CONVENTION
    assert evidence.rebalancing_applied is False


def test_envelope_caps_and_budget_never_change_the_measured_paths() -> None:
    envelope = rg2.governed(sleeve_caps=[rg2.sleeve(ALPHA, "100"), rg2.sleeve(BETA, "900")])
    inputs = drawdown_inputs(
        portfolio_risk_envelope=envelope,
        performance_path_policy=policy_for(envelope),
        sleeves=tuple(sleeve_world(sleeve_id, envelope).drawdown_inputs() for sleeve_id in (ALPHA, BETA)),
    )
    evidence = build(inputs)
    assert evidence.status is _READY
    assert evidence.envelope_digest != world_drawdown().envelope_digest
    assert evidence.portfolio.measurement == world_drawdown().portfolio.measurement
    assert [record.measurement for record in evidence.sleeves] == [
        record.measurement for record in world_drawdown().sleeves
    ]


def test_reference_notionals_never_weight_the_portfolio() -> None:
    beta = sleeve_world(BETA, reference_notional="3000")
    evidence = build(drawdown_inputs(sleeves=(sleeve_world(ALPHA).drawdown_inputs(), beta.drawdown_inputs())))
    assert evidence.status is _READY
    paths = {ALPHA: oracle_index(sleeve_world(ALPHA).evidence), BETA: oracle_index(beta.evidence)}
    governed = oracle_portfolio(WORLD_WEIGHTS, paths)
    notional_weighted = oracle_portfolio(((ALPHA, "0.25"), (BETA, "0.75")), paths)  # 1000 : 3000
    assert_measures(evidence.portfolio.measurement, governed)
    assert governed != notional_weighted


def test_a_missing_covered_sleeve_makes_the_portfolio_not_computable() -> None:
    inputs = drawdown_inputs(sleeves=(sleeve_world(ALPHA).drawdown_inputs(),))
    evidence = build(inputs)
    assert evidence.status is _NOT_COMPUTABLE
    assert evidence.ready is False
    assert evidence.missing_sleeve_ids == (BETA,)
    assert evidence.reason_codes == (
        _code("portfolio_requires_every_covered_sleeve_measured"),
        _code(f"sleeve_evidence_missing:{BETA}"),
    )
    assert evidence.sleeves == world_drawdown().sleeves[:1]  # the supplied sleeve is still measured, unchanged
    assert evidence.portfolio == PaperPortfolioDrawdownRecord(
        computed=False,
        performance_weights=policy_for().performance_weights,
        measurement=None,
        reason_codes=(_code("portfolio_requires_every_covered_sleeve_measured"),),
    )
    _assert_intact(evidence, inputs)


def test_no_supplied_sleeve_measures_nothing() -> None:
    evidence = build(drawdown_inputs(sleeves=()))
    assert evidence.status is _NOT_COMPUTABLE
    assert evidence.sleeves == ()
    assert evidence.missing_sleeve_ids == (ALPHA, BETA)
    assert evidence.portfolio.measurement is None


def test_an_uncomputable_rg3_sleeve_makes_the_portfolio_not_computable_with_its_provenance() -> None:
    blocked = rg3t.performance_inputs(**rg3t.blocked_valuation_inputs(funding_evidence=None))
    rg3 = rg3t.build(blocked)
    assert rg3.status is PaperSleevePerformanceStatus.NOT_COMPUTABLE
    inputs = drawdown_inputs(
        sleeves=(PaperSleeveDrawdownSleeveInputs(blocked, rg3), sleeve_world(BETA).drawdown_inputs())
    )
    evidence = build(inputs)
    assert evidence.status is _NOT_COMPUTABLE
    alpha, beta = evidence.sleeves
    assert (alpha.computed, alpha.measurement, alpha.performance_status) == (False, None, "NOT_COMPUTABLE")
    assert alpha.performance_evidence_digest == rg3.performance_evidence_digest
    assert alpha.reason_codes == tuple(sorted({_code("sleeve_performance_not_ready"), *rg3.reason_codes}))
    assert beta == world_drawdown().sleeves[1]
    assert evidence.missing_sleeve_ids == ()
    assert evidence.reason_codes == (
        _code("portfolio_requires_every_covered_sleeve_measured"),
        _code(f"sleeve_not_measured:{ALPHA}"),
    )
    assert evidence.portfolio.measurement is None
    _assert_intact(evidence, inputs)


def test_an_ungoverned_rg3_sleeve_needs_governance_approval() -> None:
    blocked = rg3t.performance_inputs(
        **rg3t.blocked_valuation_inputs(equity_basis_policy=world.basis_policy(governed=False))
    )
    rg3 = rg3t.build(blocked)
    assert rg3.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    inputs = drawdown_inputs(
        sleeves=(PaperSleeveDrawdownSleeveInputs(blocked, rg3), sleeve_world(BETA).drawdown_inputs())
    )
    evidence = build(inputs)
    assert evidence.status is _NEEDS_GOVERNANCE
    assert evidence.reason_codes == (
        _code("portfolio_governance_not_advanced"),
        _code("portfolio_requires_every_covered_sleeve_measured"),
        _code(f"sleeve_performance_needs_governance_approval:{ALPHA}"),
    )
    assert [record.computed for record in evidence.sleeves] == [False, True]
    _assert_intact(evidence, inputs)


def test_an_ungoverned_policy_measures_the_sleeves_but_never_the_portfolio() -> None:
    synthetic = rg4p.build(approval=rg4p.approval_for(rg4p.build(), kind=rg4p.SYNTHETIC))
    for policy in (policy_for(approved=False), synthetic):
        inputs = drawdown_inputs(performance_path_policy=policy)
        evidence = build(inputs)
        assert evidence.status is _NEEDS_GOVERNANCE
        assert evidence.performance_path_policy_advances is False
        assert evidence.reason_codes == (
            _code("performance_path_policy_not_governed"),
            _code("portfolio_governance_not_advanced"),
        )
        assert evidence.sleeves == world_drawdown().sleeves
        assert evidence.portfolio.measurement is None
        _assert_intact(evidence, inputs)


def test_an_ungoverned_envelope_needs_governance_approval() -> None:
    envelope = rg2.build()
    inputs = drawdown_inputs(
        portfolio_risk_envelope=envelope,
        performance_path_policy=policy_for(envelope),
        sleeves=tuple(sleeve_world(sleeve_id, envelope).drawdown_inputs() for sleeve_id in (ALPHA, BETA)),
    )
    evidence = build(inputs)
    assert evidence.status is _NEEDS_GOVERNANCE
    assert evidence.envelope_advances is False
    assert {
        _code("portfolio_risk_envelope_not_governed"),
        _code("portfolio_governance_not_advanced"),
        _code(f"sleeve_performance_needs_governance_approval:{ALPHA}"),
        _code(f"sleeve_performance_needs_governance_approval:{BETA}"),
    } <= set(evidence.reason_codes)
    assert evidence.portfolio.measurement is None
    _assert_intact(evidence, inputs)


@pytest.mark.parametrize(
    ("start", "end"),
    [
        pytest.param(W0 + DAY, WINDOW_END + DAY, id="shifted"),
        pytest.param(W0, WINDOW_END - DAY, id="truncated"),
        pytest.param(W0 + DAY, WINDOW_END, id="intersected"),
        pytest.param(W0 - DAY, WINDOW_END, id="extended"),
    ],
)
def test_every_sleeve_must_lie_on_the_exact_evidence_window_grid(start: int, end: int) -> None:
    with _raises("sleeve_window_not_the_evidence_window"):
        build(drawdown_inputs(window_start_ns=start, window_end_ns=end))


def test_a_sleeve_on_another_grid_is_never_truncated_or_intersected() -> None:
    short_inputs = rg3t.performance_inputs(**rg3t.short_window_inputs())
    short = PaperSleeveDrawdownSleeveInputs(short_inputs, rg3t.build(short_inputs))
    short_end = W0 + rg3t.SHORT_WINDOW_DAYS * DAY
    beta = sleeve_world(BETA).drawdown_inputs()
    with _raises("sleeve_window_not_the_evidence_window"):
        build(drawdown_inputs(sleeves=(short, beta)))
    with _raises("sleeve_window_not_the_evidence_window"):
        build(drawdown_inputs(window_end_ns=short_end, sleeves=(short, beta)))
    evidence = build(drawdown_inputs(window_end_ns=short_end, sleeves=(short,)))
    assert evidence.status is _NOT_COMPUTABLE
    assert evidence.day_count == rg3t.SHORT_WINDOW_DAYS
    assert evidence.sleeves[0].reason_codes == tuple(
        sorted({_code("sleeve_performance_not_ready"), *short.performance_evidence.reason_codes})
    )
    assert evidence.missing_sleeve_ids == (BETA,)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"window_start_ns": W0 + 1}, "window_not_utc_day_aligned"),
        ({"window_end_ns": WINDOW_END - 1}, "window_not_utc_day_aligned"),
        ({"window_end_ns": W0}, "window_end_not_after_start"),
        ({"window_start_ns": WINDOW_END, "window_end_ns": W0}, "window_end_not_after_start"),
        ({"window_start_ns": -DAY}, "window_start_ns_invalid"),
        ({"window_start_ns": True}, "window_start_ns_invalid"),
        ({"window_end_ns": float(WINDOW_END)}, "window_end_ns_invalid"),
        ({"window_end_ns": INT64_MAX + 1}, "window_end_ns_invalid"),
        ({"drawdown_evidence_id": ""}, "drawdown_evidence_id_invalid"),
        ({"drawdown_evidence_id": "live-drawdown"}, "forbidden_scope_token:drawdown_evidence_id"),
        ({"correlation_id": _Text("corr-rg4")}, "correlation_id_invalid"),
        ({"correlation_id": "bist-corr"}, "bist_scope_leakage:correlation_id"),
    ],
    ids=lambda value: str(value)[:40],
)
def test_identity_and_window_are_validated(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(drawdown_inputs(**overrides))


BINDING_DEFECTS: dict[str, tuple[Callable[[], dict[str, object]], str]] = {
    "envelope_missing": (lambda: {"portfolio_risk_envelope": None}, "portfolio_risk_envelope_malformed"),
    "envelope_tampered": (
        lambda: {"portfolio_risk_envelope": replace(rg3t.world_envelope(), total_paper_risk_budget=rg2.d("5000"))},
        "portfolio_risk_envelope_not_intact",
    ),
    "policy_missing": (lambda: {"performance_path_policy": None}, "performance_path_policy_malformed"),
    "policy_tampered": (
        lambda: {
            "performance_path_policy": replace(
                policy_for(), performance_weights=(rg4p.weight(ALPHA, "0.7"), rg4p.weight(BETA, "0.3"))
            )
        },
        "performance_path_policy_not_intact",
    ),
    "policy_of_another_envelope": (
        lambda: {"performance_path_policy": policy_for(rg2.governed(total_paper_risk_budget=rg2.d("1200")))},
        "performance_path_policy_envelope_mismatch",
    ),
    "policy_of_the_three_sleeve_envelope": (
        lambda: {"performance_path_policy": policy_for(rg4p.three_sleeve_envelope(), THREE_WEIGHTS)},
        "performance_path_policy_envelope_mismatch",
    ),
}


@pytest.mark.parametrize("name", sorted(BINDING_DEFECTS))
def test_the_envelope_and_the_policy_are_reproven(name: str) -> None:
    overrides, code = BINDING_DEFECTS[name]
    with _raises(code):
        build(drawdown_inputs(**overrides()))


@pytest.mark.parametrize("candidate", [None, "inputs", {}, 1])
def test_inputs_must_be_the_exact_record(candidate: object) -> None:
    with _raises("inputs_malformed"):
        build(candidate)


# --- F. portfolio drawdown --------------------------------------------------------------------------------------------


def test_every_measurement_carries_both_its_current_and_its_maximum() -> None:
    evidence = world_drawdown()
    measurements = [record.measurement for record in evidence.sleeves] + [evidence.portfolio.measurement]
    for measurement in measurements:
        assert measurement is not None
        assert measurement.current_peak_distance == measurement.peak_distance_path[-1]
        assert Fraction(measurement.max_peak_distance) == max(Fraction(text) for text in measurement.peak_distance_path)
        assert Fraction(measurement.current_peak_distance) <= Fraction(measurement.max_peak_distance)
    assert [m.current_peak_distance != m.max_peak_distance for m in measurements if m is not None] == [True] * 3


def test_the_fixed_weight_portfolio_never_draws_down_more_than_its_worst_sleeve() -> None:
    for evidence in (world_drawdown(), build(three_sleeve_inputs())):
        worst = max(Fraction(record.measurement.max_peak_distance) for record in evidence.sleeves)
        assert Fraction(evidence.portfolio.measurement.max_peak_distance) <= worst  # type: ignore[union-attr]


def test_running_peaks_never_decrease_and_indices_stay_positive() -> None:
    evidence = world_drawdown()
    for measurement in [record.measurement for record in evidence.sleeves] + [evidence.portfolio.measurement]:
        assert measurement is not None
        peaks = [Fraction(text) for text in measurement.running_peak_path]
        assert peaks == sorted(peaks)
        assert all(Fraction(text) > 0 for text in measurement.index_path)


# --- G. measurement only: no decision ---------------------------------------------------------------------------------


def test_the_evidence_decides_nothing() -> None:
    flags = dict(PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS)
    assert flags["paper_only"] is True
    assert not [name for name, value in flags.items() if value and name != "paper_only"]
    assert {
        "promotion_demotion_decided",
        "ladder_threshold_evaluated",
        "portfolio_stop_evaluated",
        "portfolio_allocation_approved",
        "capital_allocated",
        "execution_authorized",
        "risk_budget_used_as_weight",
        "reference_notional_used_as_weight",
        "rebalancing_applied",
        "interpolation_used",
        "carry_forward_used",
    } <= set(flags)
    evidence = world_drawdown()
    assert {name: getattr(evidence, name) for name in flags} == flags
    assert {item.name: item.default for item in fields(PaperSleeveDrawdownEvidence) if item.name in flags} == flags
    record_types = (
        PaperSleeveDrawdownEvidence,
        PaperSleeveDrawdownRecord,
        PaperPortfolioDrawdownRecord,
        PaperPeakDistanceMeasurement,
    )
    names = {item.name for record_type in record_types for item in fields(record_type)} - set(flags)
    decision_words = re.compile(r"eligib|trigger|breach|verdict|threshold|tier|allocat|approv|decision|decided")
    assert not [name for name in names if decision_words.search(name)]


def test_rg4_never_reads_thresholds_budgets_caps_or_reference_notionals() -> None:
    tree = ast.parse(Path(drawdown_module.__file__).read_text(encoding="utf-8"))
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {
        "ladder_boundaries",
        "portfolio_stop_levels",
        "promotion_max_drawdown_fraction",
        "demotion_max_drawdown_fraction",
        "max_portfolio_drawdown_fraction",
        "promotion_min_paper_sharpe",
        "demotion_min_paper_sharpe",
        "total_paper_risk_budget",
        "max_paper_risk_budget",
        "market_caps",
        "correlation_cap",
        "paper_performance_reference_notional",
    }


@pytest.mark.parametrize(
    "flag",
    [
        "promotion_demotion_decided",
        "ladder_threshold_evaluated",
        "portfolio_stop_evaluated",
        "portfolio_allocation_approved",
        "rebalancing_applied",
        "live_ready",
    ],
)
def test_forged_decision_or_readiness_flags_fail_verification(flag: str) -> None:
    verification = verify(_reseal(world_drawdown(), **{flag: True}), drawdown_inputs())
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


def test_rule_set_digest_commits_the_measurement_rules() -> None:
    rule_set = paper_sleeve_drawdown_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST
    assert world_drawdown().rule_set_digest == PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST
    assert rule_set["initial_index"] == "1"
    for name, phrase in (
        ("scope_rule_id", "measurement_evidence_only_never_promotion_demotion_stop_allocation_or_execution"),
        (
            "decision_ownership_rule_id",
            "rg6_owns_ladder_decisions_rg8_owns_portfolio_stop_decisions_rg4_decides_nothing",
        ),
        ("portfolio_index_rule_id", "fixed_weight_convex_combination"),
        ("initial_peak_rule_id", "the_start_observation_one_is_the_first_running_peak_observation"),
        ("running_peak_rule_id", "never_decreasing"),
        ("peak_distance_rule_id", "exact_reduced_fraction_in_zero_one"),
        ("current_rule_id", "end_of_window_observation"),
        ("maximum_rule_id", "every_observation_start_included"),
        ("evidence_window_rule_id", "exact_evidence_window_utc_day_grid"),
        ("completeness_rule_id", "makes_the_portfolio_not_computable"),
    ):
        assert phrase in str(rule_set[name]), name
    rule_set["initial_index"] = "0"
    assert paper_sleeve_drawdown_rule_set()["initial_index"] == "1"


# --- H. tamper and totality -----------------------------------------------------------------------------------------


def test_serialization_is_canonical_and_deterministic() -> None:
    evidence = world_drawdown()
    payload = paper_sleeve_drawdown_evidence_to_dict(evidence)
    assert json.loads(json.dumps(payload)) == payload
    assert paper_sleeve_drawdown_evidence_digest(evidence) == evidence.drawdown_evidence_digest
    again = build(drawdown_inputs())
    assert again == evidence
    assert edge_canonical_json(paper_sleeve_drawdown_evidence_to_dict(again)) == edge_canonical_json(payload)


def test_stale_self_digest_is_rejected() -> None:
    verification = verify(replace(world_drawdown(), drawdown_evidence_digest="0" * 64), drawdown_inputs())
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


RESEALED_TAMPERS: dict[str, tuple[Callable[[PaperSleeveDrawdownEvidence], dict[str, object]], str]] = {
    "portfolio_maximum": (
        lambda e: {
            "portfolio": replace(e.portfolio, measurement=replace(e.portfolio.measurement, max_peak_distance="0/1"))
        },
        "portfolio",
    ),
    "sleeve_current": (
        lambda e: {
            "sleeves": (
                replace(e.sleeves[0], measurement=replace(e.sleeves[0].measurement, current_peak_distance="0/1")),
                *e.sleeves[1:],
            )
        },
        "sleeves",
    ),
    "status": (lambda e: {"status": _NOT_COMPUTABLE, "ready": False}, "status"),
    "sleeve_dropped": (lambda e: {"sleeves": e.sleeves[:1]}, "sleeves"),
    "day_count": (lambda e: {"day_count": e.day_count - 1}, "day_count"),
    "weights": (
        lambda e: {
            "portfolio": replace(e.portfolio, performance_weights=tuple(reversed(e.portfolio.performance_weights)))
        },
        "portfolio",
    ),
}


@pytest.mark.parametrize("name", sorted(RESEALED_TAMPERS))
def test_resealed_tamper_is_rejected_by_reconstruction(name: str) -> None:
    change, field_name = RESEALED_TAMPERS[name]
    evidence = world_drawdown()
    verification = verify(_reseal(evidence, **change(evidence)), drawdown_inputs())
    assert verification.intact is False
    assert _code(f"field_mismatch:{field_name}") in verification.reason_codes


def test_the_evidence_binds_its_exact_policy_sleeves_and_envelope() -> None:
    evidence = world_drawdown()
    reweighted = verify(
        evidence, drawdown_inputs(performance_path_policy=policy_for(pairs=((ALPHA, "0.7"), (BETA, "0.3"))))
    )
    assert {
        _code("field_mismatch:performance_path_policy_digest"),
        _code("field_mismatch:performance_path_governed_digest"),
        _code("field_mismatch:portfolio"),
    } <= set(reweighted.reason_codes)
    missing = verify(evidence, drawdown_inputs(sleeves=(sleeve_world(ALPHA).drawdown_inputs(),)))
    assert {_code("field_mismatch:missing_sleeve_ids"), _code("field_mismatch:status")} <= set(missing.reason_codes)
    foreign = verify(evidence, drawdown_inputs(portfolio_risk_envelope=rg2.build()))
    assert foreign.reason_codes == (_code("evidence_reconstruction_failed"),)


CORRUPTIONS: dict[str, Callable[[PaperSleeveDrawdownEvidence], dict[str, object]]] = {
    "status_alias": lambda e: {"status": "READY"},
    "sleeves_list": lambda e: {"sleeves": list(e.sleeves)},
    "float_window": lambda e: {"window_start_ns": float(e.window_start_ns)},
    "negative_day_count": lambda e: {"day_count": -1},
    "float_measurement": lambda e: {
        "portfolio": replace(e.portfolio, measurement=replace(e.portfolio.measurement, max_peak_distance=0.0))
    },
    "record_payload": lambda e: {"portfolio": {"computed": True}},
    "text_subclass": lambda e: {"correlation_id": _Text("corr-rg4")},
}


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_public_verifier_is_total_for_corrupted_evidence(name: str) -> None:
    evidence = replace(world_drawdown())
    for field_name, value in CORRUPTIONS[name](evidence).items():
        object.__setattr__(evidence, field_name, value)
    verification = verify(evidence, drawdown_inputs())
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


@pytest.mark.parametrize(
    "artifact",
    [None, "evidence", {}, object.__new__(PaperSleeveDrawdownEvidence)],
    ids=["none", "text", "dict", "uninitialized"],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify(artifact, drawdown_inputs())
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize("inputs", [None, "inputs", {}], ids=["none", "text", "dict"])
def test_verification_against_malformed_inputs_fails_closed(inputs: object) -> None:
    verification = verify(world_drawdown(), inputs)
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_reconstruction_failed"),)


def test_evidence_is_frozen() -> None:
    evidence = world_drawdown()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evidence.portfolio.computed = False  # type: ignore[misc]


# --- static discipline ----------------------------------------------------------------------------------------------


def test_module_is_pure_and_consumes_only_its_reproven_inputs() -> None:
    pit.assert_module_is_pure(
        drawdown_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_portfolio_performance_path_policy",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_sleeve_performance_evidence",
        },
    )


def test_single_construction_site_serves_builder_and_verifier() -> None:
    world.assert_single_construction_site(
        drawdown_module,
        "PaperSleeveDrawdownEvidence",
        "build_paper_sleeve_drawdown_evidence",
        "verify_paper_sleeve_drawdown_evidence",
    )


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(drawdown_module)
    # Character and representation bounds, the decimal base and its prime factors, the start one and the UTC day.
    assert integers <= {0, 1, 2, 5, 10, 32, 127, 256, 4096, world.DAY_NS, INT64_MAX}
    assert decimals <= {"0", "1", "9"}
    flags = dict(PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS)
    for record_type in (
        PaperSleeveDrawdownInputs,
        PaperSleeveDrawdownSleeveInputs,
        PaperSleeveDrawdownRecord,
        PaperPortfolioDrawdownRecord,
        PaperPeakDistanceMeasurement,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record_type))
    assert all(
        item.default is dataclasses.MISSING for item in fields(PaperSleeveDrawdownEvidence) if item.name not in flags
    )


def test_public_api_is_exact() -> None:
    assert set(drawdown_module.__all__) == {
        "PAPER_SLEEVE_DRAWDOWN_NON_CLAIM_FLAGS",
        "PAPER_SLEEVE_DRAWDOWN_RULE_SET_DIGEST",
        "PaperPeakDistanceMeasurement",
        "PaperPortfolioDrawdownRecord",
        "PaperSleeveDrawdownEvidence",
        "PaperSleeveDrawdownEvidenceError",
        "PaperSleeveDrawdownInputs",
        "PaperSleeveDrawdownRecord",
        "PaperSleeveDrawdownSleeveInputs",
        "PaperSleeveDrawdownStatus",
        "build_paper_sleeve_drawdown_evidence",
        "measure_paper_peak_distance",
        "paper_sleeve_drawdown_evidence_digest",
        "paper_sleeve_drawdown_evidence_to_dict",
        "paper_sleeve_drawdown_rule_set",
        "verify_paper_sleeve_drawdown_evidence",
    }
