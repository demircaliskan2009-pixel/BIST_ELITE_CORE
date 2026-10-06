"""RG-5 paper sleeve correlation evidence tests (RG5_PAPER_SLEEVE_CORRELATION_EVIDENCE_V1).

SYNTHETIC TEST VALUES ONLY. The sleeve worlds, the RG-2 envelopes, their correlation caps, lookbacks and minimum
overlaps, and every approval are synthetic fixtures; none is a production value and none is production-approved.
Every sleeve world is built ONLY through the accepted public builders, exactly as the RG-3 and RG-4 tests build theirs,
and every expected correlation is recomputed here by an independent exact oracle (integer square root, half-even).
"""

from __future__ import annotations

import ast
import dataclasses
import decimal
import functools
import json
import math
import re
from collections.abc import Callable, Sequence
from dataclasses import FrozenInstanceError, fields, replace
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_correlation_evidence as correlation_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST,
    PaperPortfolioRiskEnvelope,
    paper_portfolio_risk_envelope_rule_set,
)
from crypto_core.validation.paper_position_state import paper_position_state_digest
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST,
    PaperPearsonCorrelationMeasurement,
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationEvidenceError,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationPair,
    PaperSleeveCorrelationPairStatus,
    PaperSleeveCorrelationSleeveInputs,
    PaperSleeveCorrelationSleeveRecord,
    PaperSleeveCorrelationStatus,
    build_paper_sleeve_correlation_evidence,
    measure_paper_pearson_correlation,
    paper_sleeve_correlation_evidence_digest,
    paper_sleeve_correlation_evidence_to_dict,
    paper_sleeve_correlation_rule_set,
    verify_paper_sleeve_correlation_evidence,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import build_paper_sleeve_daily_valuation_evidence
from crypto_core.validation.paper_sleeve_funding_evidence import PaperSleeveFundingEvent
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceEvidence,
    PaperSleevePerformanceStatus,
    paper_sleeve_performance_evidence_digest,
    paper_sleeve_performance_evidence_to_dict,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so the authentic worlds and their caches are built once
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_drawdown_evidence as rg4t
    import test_paper_sleeve_performance_evidence as rg3t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t

_PREFIX = "paper_sleeve_correlation_evidence"
_READY = PaperSleeveCorrelationStatus.READY
_NEEDS_GOVERNANCE = PaperSleeveCorrelationStatus.NEEDS_GOVERNANCE_APPROVAL
_OBSERVED = PaperSleeveCorrelationPairStatus.OBSERVED
_UNKNOWN = PaperSleeveCorrelationPairStatus.WORST_CASE_UNKNOWN
_RG3_READY = PaperSleevePerformanceStatus.READY
INT64_MAX = 9223372036854775807
ALPHA, BETA, GAMMA, DELTA = rg4t.ALPHA, rg4t.BETA, rg4t.GAMMA, "sleeve-delta"
W0, DAY, END = world.WINDOW_START, world.DAY_NS, world.WINDOW_END
UNKNOWN_EFFECTIVE = "1.000000000000000000"
METHOD_ID = "RG5_PEARSON_CORRELATION_METHODOLOGY_V1"
DECIMAL_POLICY_ID = "decimal_quantized_scale_18_round_half_even_internal_precision_80.v1"
PUBLIC_CORRELATION = re.compile(r"-?[01]\.[0-9]{18}")
# Synthetic RG-2 sleeve caps per declared sleeve id: structure only, never read by RG-5.
_SLEEVE_CAPS = {ALPHA: "400", BETA: "250", GAMMA: "100", DELTA: "50"}


class _Text(str):
    """A ``str`` subclass, refused wherever exact text is required."""


class _List(list):
    """A ``list`` subclass, refused wherever an exact caller sequence is required."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleeveCorrelationEvidenceError, match=f"^{re.escape(_code(code))}$")


# --- synthetic envelopes and genuine sleeve worlds ------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def envelope(
    lookback: int = 60, overlap: int = 30, cap: str = "0.6", sleeves: tuple[str, ...] = (ALPHA, BETA)
) -> PaperPortfolioRiskEnvelope:
    """A governed SYNTHETIC RG-2 envelope; the defaults are exactly the RG-2 test fixture (``rg2.governed()``)."""

    return rg2.governed(
        sleeve_caps=[rg2.sleeve(sleeve_id, _SLEEVE_CAPS[sleeve_id]) for sleeve_id in sleeves],
        max_sleeve_count=max(3, len(sleeves)),
        correlation_cap=rg2.correlation(cap, lookback, overlap),
    )


def sleeve(sleeve_id: str, env: PaperPortfolioRiskEnvelope | None = None) -> rg4t.SleeveWorld:
    return rg4t.sleeve_world(sleeve_id, envelope() if env is None else env)


def item(world_sleeve: rg4t.SleeveWorld) -> PaperSleeveCorrelationSleeveInputs:
    return PaperSleeveCorrelationSleeveInputs(world_sleeve.inputs, world_sleeve.evidence)


def items(env: PaperPortfolioRiskEnvelope, *sleeve_ids: str) -> tuple[PaperSleeveCorrelationSleeveInputs, ...]:
    return tuple(item(sleeve(sleeve_id, env)) for sleeve_id in sleeve_ids)


@functools.lru_cache(maxsize=None)
def windowed_sleeve(sleeve_id: str, start_day: int, end_day: int, env: PaperPortfolioRiskEnvelope) -> rg4t.SleeveWorld:
    """The genuine world of ``sleeve_id`` over its own UTC-day window ``[W0 + start_day days, W0 + end_day days)``.

    The sleeve keeps those of its standard SYNTHETIC episode plans that fall inside the window.
    """

    start, end = W0 + start_day * DAY, W0 + end_day * DAY
    plans = world.EPISODE_PLANS if sleeve_id == ALPHA else rg4t.SLEEVE_PLANS[sleeve_id]
    policy_id = sleeve_id.replace("sleeve", "policy")
    episodes = world.build_chain(
        tuple(plan for plan in plans if start <= plan.at_ns < end),
        draft=world.make_draft(sleeve_id, policy_id),
        capacity_policy=world.make_capacity_policy(sleeve_id, policy_id),
    )
    days = end_day - start_day
    events = []
    for day in range(days):
        instant = start + day * DAY + world.FUNDING_SETTLEMENT_OFFSET_NS
        state = world.position_before(instant, episodes)
        if state.side.value != "FLAT":
            events.append(
                PaperSleeveFundingEvent(
                    event_id=f"funding-{day}",
                    settlement_at_ns=instant,
                    position_state_digest=paper_position_state_digest(state),
                    funding_amount=world.d("-0.01"),
                )
            )
    basis = world.basis_policy(sleeve_id=sleeve_id)
    valuation_inputs = world.valuation_inputs(
        valuation_id=f"sleeve-valuation-{sleeve_id}-{start_day}-{end_day}",
        window_start_ns=start,
        window_end_ns=end,
        episodes=episodes,
        day_closes=tuple(world.build_day_close(start_day + day, episodes) for day in range(days)),
        equity_basis_policy=basis,
        funding_evidence=world.funding_evidence(
            sleeve_id=sleeve_id, window_start_ns=start, window_end_ns=end, events=tuple(events)
        ),
    )
    valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
    series = rg3t.series_world(valuation, basis, start, end)
    inputs = rg3t.performance_inputs(
        performance_evidence_id=f"rg3-{sleeve_id}-{start_day}-{end_day}",
        portfolio_risk_envelope=env,
        valuation_inputs=valuation_inputs,
        valuation=valuation,
        **series.inputs(),
    )
    return rg4t.SleeveWorld(inputs, rg3t.build(inputs))


def correlation_inputs(**overrides: object) -> PaperSleeveCorrelationInputs:
    env = overrides.get("portfolio_risk_envelope", envelope())
    values: dict[str, object] = {
        "correlation_evidence_id": "rg5-correlation-1",
        "correlation_id": "corr-rg5",
        "portfolio_risk_envelope": env,
        "evaluation_end_ns": END,
    }
    if "sleeves" not in overrides:
        values["sleeves"] = items(env, ALPHA, BETA)  # type: ignore[arg-type]
    values.update(overrides)
    return PaperSleeveCorrelationInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> PaperSleeveCorrelationEvidence:
    return build_paper_sleeve_correlation_evidence(inputs)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def world_correlation() -> PaperSleeveCorrelationEvidence:
    return build(correlation_inputs())


def verify(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_correlation_evidence(evidence, inputs)  # type: ignore[arg-type]


def _reseal(evidence: PaperSleeveCorrelationEvidence, **changes: object) -> PaperSleeveCorrelationEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, correlation_evidence_digest=paper_sleeve_correlation_evidence_digest(changed))


def _reseal_rg3(evidence: PaperSleevePerformanceEvidence, **changes: object) -> PaperSleevePerformanceEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, performance_evidence_digest=paper_sleeve_performance_evidence_digest(changed))


def _assert_intact(evidence: PaperSleeveCorrelationEvidence, inputs: PaperSleeveCorrelationInputs) -> None:
    verification = verify(evidence, inputs)
    assert verification.intact is True, verification.reason_codes
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == evidence.correlation_evidence_digest
    assert json.loads(verification.canonical_json) == paper_sleeve_correlation_evidence_to_dict(evidence)


# --- the independent exact oracle -----------------------------------------------------------------------------------


def returns_of(world_sleeve: rg4t.SleeveWorld) -> list[Fraction]:
    return [Fraction(text) for text in world_sleeve.evidence.daily_returns]


def oracle_correlation(xs: Sequence[Fraction], ys: Sequence[Fraction]) -> str | None:
    """``Sxy / sqrt(Sxx*Syy)`` rounded half-even to 18 places by exact integer arithmetic; ``None`` when undefined."""

    count = len(xs)
    mean_x, mean_y = sum(xs, Fraction(0)) / count, sum(ys, Fraction(0)) / count
    sxx = sum(((x - mean_x) ** 2 for x in xs), Fraction(0))
    syy = sum(((y - mean_y) ** 2 for y in ys), Fraction(0))
    sxy = sum(((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)), Fraction(0))
    if sxx == 0 or syy == 0:
        return None
    squared = sxy * sxy / (sxx * syy) * 10**36  # (10**18 * |rho|) ** 2
    units = math.isqrt(squared.numerator // squared.denominator)
    half = Fraction(2 * units + 1, 2) ** 2
    if squared > half or (squared == half and units % 2 == 1):
        units += 1
    sign = "-" if sxy < 0 and units else ""
    return f"{sign}{units // 10**18}.{units % 10**18:018d}"


def as_text(value: Fraction) -> str:
    """Canonical plain decimal text of a terminating SYNTHETIC test value."""

    with decimal.localcontext() as context:
        context.prec = 200
        rendered = format((Decimal(value.numerator) / Decimal(value.denominator)).normalize(), "f")
    return "0" if rendered in {"-0", "0"} else rendered


def texts(values: Sequence[Fraction]) -> list[str]:
    return [as_text(value) for value in values]


def measured(x: Sequence[str], y: Sequence[str]) -> str:
    return measure_paper_pearson_correlation(list(x), list(y)).correlation


# --- RG-2 re-pin -----------------------------------------------------------------------------------------------------


def test_the_default_envelope_is_the_rg2_fixture_and_both_worlds_are_ready() -> None:
    assert envelope() == rg2.governed() == rg3t.world_envelope()
    for sleeve_id in (ALPHA, BETA):
        evidence = sleeve(sleeve_id).evidence
        assert evidence.status is _RG3_READY, evidence.reason_codes
        assert (evidence.window_start_ns, evidence.window_end_ns, evidence.day_count) == (W0, END, world.WINDOW_DAYS)


def test_world_correlation_is_ready_and_binds_every_reproven_digest() -> None:
    evidence = world_correlation()
    env = envelope()
    assert evidence.status is _READY
    assert evidence.ready is True
    assert evidence.reason_codes == ()
    assert (evidence.correlation_evidence_id, evidence.correlation_id) == ("rg5-correlation-1", "corr-rg5")
    assert (evidence.envelope_digest, evidence.envelope_policy_digest, evidence.envelope_advances) == (
        env.envelope_digest,
        env.policy_digest,
        True,
    )
    assert evidence.envelope_rule_set_digest == PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST
    assert (evidence.max_pairwise_correlation, evidence.lookback_window_days, evidence.min_overlap_days) == (
        env.correlation_cap.max_pairwise_correlation,
        60,
        30,
    )
    assert (evidence.evaluation_end_ns, evidence.lookback_start_ns) == (END, END - 60 * DAY)
    assert evidence.declared_sleeve_ids == (ALPHA, BETA)
    assert evidence.missing_sleeve_ids == ()
    assert (evidence.correlation_method_id, evidence.decimal_policy_id) == (METHOD_ID, DECIMAL_POLICY_ID)
    assert evidence.unknown_effective_correlation == UNKNOWN_EFFECTIVE
    assert evidence.rule_set_digest == PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST
    for record in evidence.sleeves:
        rg3 = sleeve(record.sleeve_id).evidence
        assert record == PaperSleeveCorrelationSleeveRecord(
            sleeve_id=rg3.sleeve_id,
            market_symbol=rg3.market_symbol,
            performance_evidence_digest=rg3.performance_evidence_digest,
            performance_status="READY",
            window_start_ns=W0,
            window_end_ns=END,
            day_count=world.WINDOW_DAYS,
            current_for_evaluation=True,
            lookback_day_count=world.WINDOW_DAYS,
            reason_codes=(),
        )
    (pair,) = evidence.pairs
    expected = oracle_correlation(returns_of(sleeve(ALPHA)), returns_of(sleeve(BETA)))
    assert expected == "0.305474502762819688"
    assert pair == PaperSleeveCorrelationPair(
        sleeve_a_id=ALPHA,
        sleeve_b_id=BETA,
        pair_status=_OBSERVED,
        overlap_start_ns=W0,
        overlap_end_ns=END,
        overlap_day_count=30,
        observed_correlation=expected,
        effective_correlation=expected,
        reason_codes=(),
    )
    assert (evidence.pair_count, evidence.observed_pair_count, evidence.worst_case_pair_count) == (1, 1, 0)
    assert evidence.all_pairs_observed is True
    _assert_intact(evidence, correlation_inputs())


ENVELOPE_DEFECTS: dict[str, tuple[Callable[[], object], str]] = {
    "missing": (lambda: None, "portfolio_risk_envelope_malformed"),
    "payload": (lambda: rg2.to_dict(envelope()), "portfolio_risk_envelope_malformed"),
    "stale_digest": (lambda: replace(envelope(), envelope_digest="0" * 64), "portfolio_risk_envelope_not_intact"),
    "unsealed_change": (
        lambda: replace(envelope(), total_paper_risk_budget=rg2.d("5000")),
        "portfolio_risk_envelope_not_intact",
    ),
    "resealed_lookback": (
        lambda: rg2._reseal(envelope(), correlation_cap=rg2.correlation("0.6", 20, 10)),  # noqa: SLF001
        "portfolio_risk_envelope_not_intact",
    ),
}


@pytest.mark.parametrize("name", sorted(ENVELOPE_DEFECTS))
def test_a_malformed_stale_or_resealed_envelope_is_refused(name: str) -> None:
    make, code = ENVELOPE_DEFECTS[name]
    with _raises(code):
        build(correlation_inputs(portfolio_risk_envelope=make(), sleeves=items(envelope(), ALPHA, BETA)))


def test_a_non_advanced_envelope_needs_governance_approval_and_every_pair_stays_worst_case() -> None:
    unapproved = rg2.build()
    assert unapproved.advances is False
    inputs = correlation_inputs(portfolio_risk_envelope=unapproved, sleeves=items(unapproved, ALPHA, BETA))
    evidence = build(inputs)
    assert evidence.status is _NEEDS_GOVERNANCE
    assert evidence.ready is False
    assert evidence.envelope_advances is False
    assert evidence.reason_codes == (
        _code("portfolio_risk_envelope_not_governed"),
        _code(f"sleeve_performance_needs_governance_approval:{ALPHA}"),
        _code(f"sleeve_performance_needs_governance_approval:{BETA}"),
    )
    (pair,) = evidence.pairs
    assert (pair.pair_status, pair.observed_correlation, pair.effective_correlation) == (
        _UNKNOWN,
        "",
        UNKNOWN_EFFECTIVE,
    )
    assert pair.reason_codes == (
        _code(f"pair_sleeve_performance_not_ready:{ALPHA}"),
        _code(f"pair_sleeve_performance_not_ready:{BETA}"),
    )
    _assert_intact(evidence, inputs)


def test_cap_lookback_and_min_overlap_are_repinned_and_the_cap_never_changes_a_pair() -> None:
    for cap in ("-0.5", "0.999999999999999999"):
        env = envelope(cap=cap)
        evidence = build(correlation_inputs(portfolio_risk_envelope=env))
        assert evidence.max_pairwise_correlation == rg2.d(cap) == env.correlation_cap.max_pairwise_correlation
        assert evidence.pairs[0].observed_correlation == world_correlation().pairs[0].observed_correlation
        assert evidence.envelope_digest != world_correlation().envelope_digest
    governed = build(correlation_inputs(portfolio_risk_envelope=envelope(lookback=45, overlap=12)))
    assert (governed.lookback_window_days, governed.min_overlap_days) == (45, 12)
    assert governed.lookback_start_ns == END - 45 * DAY


# --- RG-3 re-proof ---------------------------------------------------------------------------------------------------


RG3_FORGERIES: dict[str, Callable[[PaperSleevePerformanceEvidence], PaperSleevePerformanceEvidence]] = {
    "resealed_daily_return": lambda e: _reseal_rg3(
        e, daily_returns=(*e.daily_returns[:3], "0.5", *e.daily_returns[4:])
    ),
    "resealed_day_reorder": lambda e: _reseal_rg3(e, daily_returns=tuple(reversed(e.daily_returns))),
    "resealed_day_duplicate": lambda e: _reseal_rg3(e, daily_returns=(e.daily_returns[0], *e.daily_returns[:-1])),
    "resealed_market_swap": lambda e: _reseal_rg3(e, market_symbol="ETH-PERPETUAL"),
    "resealed_window_shift": lambda e: _reseal_rg3(e, window_start_ns=e.window_start_ns + DAY),
    "resealed_sharpe": lambda e: _reseal_rg3(e, paper_sharpe_annualized="9.9"),
    "stale_digest": lambda e: replace(e, performance_evidence_digest="0" * 64),
    "sleeve_swap": lambda e: sleeve(BETA).evidence,
}


@pytest.mark.parametrize("name", sorted(RG3_FORGERIES))
def test_rg3_evidence_that_is_not_the_reconstruction_is_refused_never_an_unknown_pair(name: str) -> None:
    alpha = sleeve(ALPHA)
    forged = PaperSleeveCorrelationSleeveInputs(alpha.inputs, RG3_FORGERIES[name](alpha.evidence))
    with _raises("sleeve_performance_not_reconstructed"):
        build(correlation_inputs(sleeves=(forged, item(sleeve(BETA)))))


def test_rg3_evidence_over_a_foreign_envelope_is_refused() -> None:
    foreign = sleeve(ALPHA, envelope(lookback=45, overlap=12))
    assert foreign.evidence.status is _RG3_READY
    with _raises("sleeve_performance_envelope_mismatch"):
        build(correlation_inputs(sleeves=(item(foreign), item(sleeve(BETA)))))


SLEEVE_ITEMS: dict[str, tuple[Callable[[rg4t.SleeveWorld], object], str]] = {
    "plain_tuple": (lambda s: (s.inputs, s.evidence), "sleeve_malformed"),
    "inputs_missing": (lambda s: PaperSleeveCorrelationSleeveInputs(None, s.evidence), "performance_inputs_malformed"),
    "evidence_missing": (
        lambda s: PaperSleeveCorrelationSleeveInputs(s.inputs, None),
        "performance_evidence_malformed",
    ),
    "evidence_payload": (
        lambda s: PaperSleeveCorrelationSleeveInputs(s.inputs, paper_sleeve_performance_evidence_to_dict(s.evidence)),
        "performance_evidence_malformed",
    ),
    "inputs_unbuildable": (
        lambda s: PaperSleeveCorrelationSleeveInputs(replace(s.inputs, valuation_inputs="valuation"), s.evidence),
        "sleeve_performance_reconstruction_failed",
    ),
}


@pytest.mark.parametrize("name", sorted(SLEEVE_ITEMS))
def test_every_sleeve_item_is_an_exact_record_rebuilt_through_rg3(name: str) -> None:
    make, code = SLEEVE_ITEMS[name]
    with _raises(code):
        build(correlation_inputs(sleeves=(make(sleeve(ALPHA)), item(sleeve(BETA)))))


def test_a_sleeve_supplied_twice_is_refused() -> None:
    alpha = item(sleeve(ALPHA))
    with _raises("sleeve_duplicate"):
        build(correlation_inputs(sleeves=(alpha, item(sleeve(BETA)), alpha)))


@pytest.mark.parametrize(
    "sleeves", [None, "sleeves", {}, _List(), frozenset()], ids=["none", "text", "dict", "subclass", "set"]
)
def test_the_sleeves_are_an_exact_sequence(sleeves: object) -> None:
    with _raises("sleeves_malformed"):
        build(correlation_inputs(sleeves=sleeves))


def test_an_uncomputable_rg3_sleeve_is_a_worst_case_pair_with_its_provenance() -> None:
    blocked = rg3t.performance_inputs(**rg3t.blocked_valuation_inputs(funding_evidence=None))
    rg3 = rg3t.build(blocked)
    assert rg3.status is PaperSleevePerformanceStatus.NOT_COMPUTABLE
    inputs = correlation_inputs(sleeves=(PaperSleeveCorrelationSleeveInputs(blocked, rg3), item(sleeve(BETA))))
    evidence = build(inputs)
    assert evidence.status is _READY
    assert evidence.reason_codes == ()
    alpha_record = evidence.sleeves[0]
    assert (alpha_record.performance_status, alpha_record.current_for_evaluation, alpha_record.lookback_day_count) == (
        "NOT_COMPUTABLE",
        False,
        0,
    )
    assert alpha_record.performance_evidence_digest == rg3.performance_evidence_digest
    assert alpha_record.reason_codes == tuple(sorted({_code("sleeve_performance_not_ready"), *rg3.reason_codes}))
    assert evidence.sleeves[1] == world_correlation().sleeves[1]
    (pair,) = evidence.pairs
    assert (pair.pair_status, pair.observed_correlation, pair.effective_correlation) == (
        _UNKNOWN,
        "",
        UNKNOWN_EFFECTIVE,
    )
    assert (pair.overlap_start_ns, pair.overlap_end_ns, pair.overlap_day_count) == (END, END, 0)
    assert pair.reason_codes == (_code(f"pair_sleeve_performance_not_ready:{ALPHA}"),)
    assert (evidence.observed_pair_count, evidence.worst_case_pair_count, evidence.all_pairs_observed) == (0, 1, False)
    _assert_intact(evidence, inputs)


def test_an_ungoverned_rg3_sleeve_needs_governance_approval_and_stays_worst_case() -> None:
    blocked = rg3t.performance_inputs(
        **rg3t.blocked_valuation_inputs(equity_basis_policy=world.basis_policy(governed=False))
    )
    rg3 = rg3t.build(blocked)
    assert rg3.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    inputs = correlation_inputs(sleeves=(PaperSleeveCorrelationSleeveInputs(blocked, rg3), item(sleeve(BETA))))
    evidence = build(inputs)
    assert evidence.status is _NEEDS_GOVERNANCE
    assert evidence.reason_codes == (_code(f"sleeve_performance_needs_governance_approval:{ALPHA}"),)
    assert evidence.pairs[0].effective_correlation == UNKNOWN_EFFECTIVE
    assert evidence.pairs[0].reason_codes == (_code(f"pair_sleeve_performance_not_ready:{ALPHA}"),)
    _assert_intact(evidence, inputs)


FORGED_RECONSTRUCTIONS: dict[str, tuple[Callable[[PaperSleevePerformanceEvidence], dict[str, object]], str]] = {
    "undeclared_sleeve": (lambda e: {"sleeve_id": DELTA}, "sleeve_not_declared_by_envelope"),
    "returns_off_the_window": (
        lambda e: {"daily_returns": e.daily_returns[:-1]},
        "sleeve_daily_returns_not_the_window",
    ),
    "window_not_utc_aligned": (
        lambda e: {"window_start_ns": e.window_start_ns + 1},
        "sleeve_daily_returns_not_the_window",
    ),
    "noncanonical_return": (lambda e: {"daily_returns": ("0.10", *e.daily_returns[1:])}, "sleeve_daily_return_invalid"),
}


@pytest.mark.parametrize("name", sorted(FORGED_RECONSTRUCTIONS))
def test_defense_in_depth_guards_fail_closed_on_a_forged_reconstruction(
    name: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    change, code = FORGED_RECONSTRUCTIONS[name]
    alpha = sleeve(ALPHA)
    forged = replace(alpha.evidence, **change(alpha.evidence))
    monkeypatch.setattr(correlation_module, "build_paper_sleeve_performance_evidence", lambda _inputs: forged)
    with _raises(code):
        build(correlation_inputs(sleeves=(PaperSleeveCorrelationSleeveInputs(alpha.inputs, forged),)))


# --- the complete canonical pair universe ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("declared", "supplied", "expected_pairs"),
    [
        pytest.param((ALPHA,), (ALPHA,), (), id="one_sleeve_no_pair"),
        pytest.param((ALPHA, BETA), (ALPHA, BETA), ((ALPHA, BETA),), id="two_sleeves_one_pair"),
        pytest.param(
            (ALPHA, BETA, GAMMA),
            (GAMMA, ALPHA, BETA),
            ((ALPHA, BETA), (ALPHA, GAMMA), (BETA, GAMMA)),
            id="three_sleeves_three_pairs",
        ),
        pytest.param(
            (ALPHA, BETA, GAMMA, DELTA),
            (BETA, GAMMA, ALPHA),
            ((ALPHA, BETA), (ALPHA, DELTA), (ALPHA, GAMMA), (BETA, DELTA), (BETA, GAMMA), (DELTA, GAMMA)),
            id="four_sleeves_six_pairs_one_missing",
        ),
    ],
)
def test_every_unordered_declared_pair_appears_exactly_once_in_canonical_order(
    declared: tuple[str, ...], supplied: tuple[str, ...], expected_pairs: tuple[tuple[str, str], ...]
) -> None:
    env = envelope(sleeves=declared)
    inputs = correlation_inputs(portfolio_risk_envelope=env, sleeves=items(env, *supplied))
    evidence = build(inputs)
    assert evidence.status is _READY
    assert evidence.declared_sleeve_ids == tuple(sorted(declared))
    assert tuple((pair.sleeve_a_id, pair.sleeve_b_id) for pair in evidence.pairs) == expected_pairs
    assert evidence.pair_count == len(declared) * (len(declared) - 1) // 2 == len(evidence.pairs)
    assert evidence.missing_sleeve_ids == tuple(sorted(set(declared) - set(supplied)))
    for pair in evidence.pairs:
        assert pair.sleeve_a_id < pair.sleeve_b_id
        if DELTA in (pair.sleeve_a_id, pair.sleeve_b_id):
            assert (pair.pair_status, pair.effective_correlation) == (_UNKNOWN, UNKNOWN_EFFECTIVE)
            assert pair.reason_codes == (_code(f"pair_sleeve_evidence_missing:{DELTA}"),)
        else:
            assert pair.pair_status is _OBSERVED
            xs = returns_of(sleeve(pair.sleeve_a_id, env))
            ys = returns_of(sleeve(pair.sleeve_b_id, env))
            assert pair.observed_correlation == pair.effective_correlation == oracle_correlation(xs, ys)
    assert evidence.observed_pair_count + evidence.worst_case_pair_count == evidence.pair_count
    assert evidence.all_pairs_observed is (evidence.worst_case_pair_count == 0)
    reordered = correlation_inputs(portfolio_risk_envelope=env, sleeves=tuple(reversed(inputs.sleeves)))
    assert build(reordered) == evidence
    _assert_intact(evidence, inputs)


def test_a_missing_sleeve_still_materializes_its_worst_case_pairs() -> None:
    inputs = correlation_inputs(sleeves=items(envelope(), ALPHA))
    evidence = build(inputs)
    assert evidence.status is _READY
    assert evidence.missing_sleeve_ids == (BETA,)
    assert [record.sleeve_id for record in evidence.sleeves] == [ALPHA]
    (pair,) = evidence.pairs
    assert pair == PaperSleeveCorrelationPair(
        sleeve_a_id=ALPHA,
        sleeve_b_id=BETA,
        pair_status=_UNKNOWN,
        overlap_start_ns=END,
        overlap_end_ns=END,
        overlap_day_count=0,
        observed_correlation="",
        effective_correlation=UNKNOWN_EFFECTIVE,
        reason_codes=(_code(f"pair_sleeve_evidence_missing:{BETA}"),),
    )
    empty = build(correlation_inputs(sleeves=()))
    assert empty.missing_sleeve_ids == (ALPHA, BETA)
    assert empty.pairs[0].effective_correlation == UNKNOWN_EFFECTIVE
    _assert_intact(evidence, inputs)


def test_symmetry_the_canonical_pair_correlation_equals_the_swapped_vector_correlation() -> None:
    alpha, beta = sleeve(ALPHA).evidence.daily_returns, sleeve(BETA).evidence.daily_returns
    assert measured(alpha, beta) == measured(beta, alpha) == world_correlation().pairs[0].observed_correlation


# --- the Pearson estimator (independent oracle) ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("x", "y", "expected"),
    [
        pytest.param(["0.1", "0.2", "0.3"], ["0.2", "0.4", "0.6"], "1.000000000000000000", id="perfect_plus_one"),
        pytest.param(["0.1", "0.2", "0.3"], ["0.3", "0.2", "0.1"], "-1.000000000000000000", id="perfect_minus_one"),
        pytest.param(["1", "2", "3"], ["1", "0", "1"], "0.000000000000000000", id="exact_zero"),
        pytest.param(["1", "2", "3", "4"], ["1", "3", "2", "4"], "0.800000000000000000", id="rational_positive"),
        pytest.param(["1", "2", "3", "4"], ["4", "2", "3", "1"], "-0.800000000000000000", id="rational_negative"),
    ],
)
def test_pearson_values_with_an_exact_algebraic_answer(x: list[str], y: list[str], expected: str) -> None:
    measurement = measure_paper_pearson_correlation(x, y)
    assert measurement == PaperPearsonCorrelationMeasurement(
        observation_count=len(x), x_variance_zero=False, y_variance_zero=False, defined=True, correlation=expected
    )


@pytest.mark.parametrize(
    ("x", "y"),
    [
        pytest.param(["1", "2", "3"], ["1", "2", "4"], id="irrational_positive"),
        pytest.param(["1", "2", "3"], ["4", "2", "1"], id="irrational_negative"),
        pytest.param(["0.001", "0.0013", "0.0009", "0.0021"], ["1000", "1003.5", "998.25", "1010"], id="unequal_means"),
        pytest.param(
            ["0.000000000000000001", "0.000000000000000003", "0.000000000000000002"],
            ["123456789.123456789", "-987654321.987654321", "0.5"],
            id="small_and_high_scale",
        ),
    ],
)
def test_pearson_values_equal_the_exact_oracle(x: list[str], y: list[str]) -> None:
    expected = oracle_correlation([Fraction(v) for v in x], [Fraction(v) for v in y])
    assert expected is not None
    assert measured(x, y) == expected
    assert measured(y, x) == expected


def test_the_irrational_value_is_the_correctly_rounded_square_root() -> None:
    # x = (1, 2, 3), y = (1, 2, 4): Sxy = 3, Sxx = 2, Syy = 14/3, so rho = sqrt(27/28).
    rho = measured(["1", "2", "3"], ["1", "2", "4"])
    units = int(rho.replace(".", ""))
    target = Fraction(27, 28) * 10**36
    assert Fraction(2 * units - 1, 2) ** 2 < target < Fraction(2 * units + 1, 2) ** 2


def test_positive_affine_maps_preserve_and_negative_ones_flip_the_correlation() -> None:
    xs = [Fraction(v) for v in ("0.012", "-0.003", "0.007", "0.0105", "-0.0021")]
    ys = [Fraction(v) for v in ("0.4", "0.1", "-0.25", "0.33", "0.05")]
    base = measured(texts(xs), texts(ys))
    assert measured(texts([3 * y + 7 for y in ys]), texts(xs)) == base
    assert measured(texts([Fraction(1, 8) * x - 2 for x in xs]), texts([5 * y for y in ys])) == base
    flipped = measured(texts(xs), texts([-2 * y + 1 for y in ys]))
    assert Fraction(flipped) == -Fraction(base)


def _lcg(seed: int) -> Callable[[], int]:
    state = [seed]

    def step() -> int:
        state[0] = (state[0] * 6364136223846793005 + 1442695040888963407) % 2**64
        return state[0]

    return step


def test_pearson_equals_the_exact_oracle_over_generated_vectors_and_stays_in_bounds() -> None:
    step = _lcg(20261006)
    for _ in range(300):
        count = 2 + step() % 12
        xs = [Fraction(int(step() % 2000001) - 1000000, 10 ** (step() % 19)) for _ in range(count)]
        ys = [Fraction(int(step() % 2000001) - 1000000, 10 ** (step() % 19)) for _ in range(count)]
        measurement = measure_paper_pearson_correlation(texts(xs), texts(ys))
        expected = oracle_correlation(xs, ys)
        assert measurement.correlation == ("" if expected is None else expected)
        if measurement.defined:
            assert PUBLIC_CORRELATION.fullmatch(measurement.correlation)
            assert -1 <= Fraction(measurement.correlation) <= 1


@pytest.mark.parametrize(
    ("x", "y", "exact", "half_even", "half_up", "half_down"),
    [
        pytest.param(
            ["-83", "-51", "95", "522", "-483"],
            ["-83", "-51", "95", "-483", "522"],
            Fraction(-485737, 2**19),
            "-0.926469802856445312",
            "-0.926469802856445313",
            "-0.926469802856445312",
            id="tie_with_even_floor",
        ),
        pytest.param(
            ["-317", "223", "-337", "505", "-74"],
            ["-74", "223", "-337", "505", "-317"],
            Fraction(465239, 2**19),
            "0.887372970581054688",
            "0.887372970581054688",
            "0.887372970581054687",
            id="tie_with_odd_floor",
        ),
    ],
)
def test_exact_ties_round_half_even(
    x: list[str], y: list[str], exact: Fraction, half_even: str, half_up: str, half_down: str
) -> None:
    xs, ys = [Fraction(v) for v in x], [Fraction(v) for v in y]
    mean = sum(xs, Fraction(0)) / len(xs)
    sxx = sum(((v - mean) ** 2 for v in xs), Fraction(0))
    assert sxx == sum(((v - mean) ** 2 for v in ys), Fraction(0))  # y permutes x: Syy == Sxx
    assert sum(((a - mean) * (b - mean) for a, b in zip(xs, ys, strict=True)), Fraction(0)) / sxx == exact
    assert (exact * 2 * 10**18).denominator == 1  # an exact tie at the 18th fractional digit
    assert (exact * 2 * 10**18).numerator % 2 == 1
    assert oracle_correlation([Fraction(v) for v in x], [Fraction(v) for v in y]) == half_even
    assert measured(x, y) == half_even
    assert half_even in {half_up, half_down}
    assert half_up != half_down


def test_signed_zero_is_normalized_to_positive_zero() -> None:
    # Sxy = -3.5e-20 against sqrt(Sxx*Syy) near sqrt(12): rho near -1.01e-20 rounds to a negative zero.
    rho = measured(["-1", "0", "1"], ["1", "-2", "0.999999999999999999965"])
    assert rho == "0.000000000000000000"
    assert not rho.startswith("-")


@pytest.mark.parametrize(
    ("x", "y", "x_zero", "y_zero"),
    [
        pytest.param(["0.1", "0.1", "0.1"], ["1", "2", "4"], True, False, id="x_constant"),
        pytest.param(["1", "2", "4"], ["-0.2", "-0.2", "-0.2"], False, True, id="y_constant"),
        pytest.param(["0", "0"], ["5", "5"], True, True, id="both_constant"),
        pytest.param(["0.7"], ["0.3"], True, True, id="single_observation"),
    ],
)
def test_zero_variance_leaves_the_estimate_undefined(x: list[str], y: list[str], x_zero: bool, y_zero: bool) -> None:
    assert measure_paper_pearson_correlation(x, y) == PaperPearsonCorrelationMeasurement(
        observation_count=len(x), x_variance_zero=x_zero, y_variance_zero=y_zero, defined=False, correlation=""
    )


@pytest.mark.parametrize(
    ("x", "y", "code"),
    [
        pytest.param(None, ["1"], "x_returns_malformed", id="x_none"),
        pytest.param("1", ["1"], "x_returns_malformed", id="x_text"),
        pytest.param(_List(["1"]), ["1"], "x_returns_malformed", id="x_list_subclass"),
        pytest.param((text for text in ["1"]), ["1"], "x_returns_malformed", id="x_generator"),
        pytest.param([], [], "x_returns_empty", id="x_empty"),
        pytest.param(["1.0"], ["1"], "x_returns_observation_invalid", id="trailing_zero"),
        pytest.param(["1e1"], ["1"], "x_returns_observation_invalid", id="exponent"),
        pytest.param(["-0"], ["1"], "x_returns_observation_invalid", id="negative_zero"),
        pytest.param(["+1"], ["1"], "x_returns_observation_invalid", id="plus_sign"),
        pytest.param([1], ["1"], "x_returns_observation_invalid", id="int"),
        pytest.param([0.5], ["1"], "x_returns_observation_invalid", id="float"),
        pytest.param([Fraction(1, 2)], ["1"], "x_returns_observation_invalid", id="fraction"),
        pytest.param([_Text("1")], ["1"], "x_returns_observation_invalid", id="text_subclass"),
        pytest.param(["1." + "1" * 4095], ["1"], "x_returns_observation_invalid", id="over_the_text_bound"),
        pytest.param(["1"], None, "y_returns_malformed", id="y_none"),
        pytest.param(["1"], ["one"], "y_returns_observation_invalid", id="y_word"),
        pytest.param(["1", "2"], ["1"], "returns_length_mismatch", id="length_mismatch"),
    ],
)
def test_invalid_estimator_input_is_refused(x: object, y: object, code: str) -> None:
    with _raises(code):
        measure_paper_pearson_correlation(x, y)  # type: ignore[arg-type]


# --- zero variance, lookback, currency and overlap over genuine worlds -----------------------------------------------


def _pair(env: PaperPortfolioRiskEnvelope, evaluation_end: int, *sleeves: PaperSleeveCorrelationSleeveInputs):
    inputs = correlation_inputs(
        portfolio_risk_envelope=env, evaluation_end_ns=evaluation_end, sleeves=sleeves or items(env, ALPHA, BETA)
    )
    evidence = build(inputs)
    _assert_intact(evidence, inputs)
    return evidence, evidence.pairs[0]


@pytest.mark.parametrize(
    ("lookback", "window", "zero"),
    [
        pytest.param(6, None, (ALPHA,), id="first_sleeve_constant"),
        pytest.param(5, (-18, 12), (BETA,), id="second_sleeve_constant"),
        pytest.param(4, None, (ALPHA, BETA), id="both_constant"),
    ],
)
def test_zero_variance_in_an_aligned_vector_is_a_worst_case_unknown(
    lookback: int, window: tuple[int, int] | None, zero: tuple[str, ...]
) -> None:
    env = envelope(lookback=lookback, overlap=2)
    if window is None:
        worlds = {sleeve_id: sleeve(sleeve_id, env) for sleeve_id in (ALPHA, BETA)}
        evaluation_end = END
    else:
        worlds = {sleeve_id: windowed_sleeve(sleeve_id, *window, env) for sleeve_id in (ALPHA, BETA)}
        evaluation_end = W0 + window[1] * DAY
    evidence, pair = _pair(env, evaluation_end, item(worlds[ALPHA]), item(worlds[BETA]))
    assert evidence.status is _READY
    assert (pair.pair_status, pair.observed_correlation, pair.effective_correlation) == (
        _UNKNOWN,
        "",
        UNKNOWN_EFFECTIVE,
    )
    assert pair.overlap_day_count == lookback
    assert pair.reason_codes == tuple(_code(f"pair_variance_zero:{sleeve_id}") for sleeve_id in zero)
    for sleeve_id in (ALPHA, BETA):
        assert (set(worlds[sleeve_id].evidence.daily_returns[-lookback:]) == {"0"}) is (sleeve_id in zero)


def test_a_lookback_shorter_than_the_evidence_excludes_every_earlier_day() -> None:
    env = envelope(lookback=20, overlap=10)
    evidence, pair = _pair(env, END)
    assert (pair.pair_status, pair.overlap_start_ns, pair.overlap_day_count) == (_OBSERVED, END - 20 * DAY, 20)
    expected = oracle_correlation(returns_of(sleeve(ALPHA, env))[10:], returns_of(sleeve(BETA, env))[10:])
    assert pair.observed_correlation == expected
    assert pair.observed_correlation != world_correlation().pairs[0].observed_correlation
    assert [record.lookback_day_count for record in evidence.sleeves] == [20, 20]


def test_a_lookback_equal_to_or_longer_than_the_evidence_measures_the_whole_window() -> None:
    exact, exact_pair = _pair(envelope(lookback=30, overlap=30), END)
    assert (exact_pair.pair_status, exact_pair.overlap_day_count) == (_OBSERVED, 30)
    assert exact_pair.observed_correlation == world_correlation().pairs[0].observed_correlation
    assert exact.lookback_start_ns == W0
    assert world_correlation().lookback_start_ns == END - 60 * DAY < W0
    assert world_correlation().pairs[0].overlap_start_ns == W0


def test_a_governed_lookback_change_changes_the_measured_pair_exactly_when_it_changes_the_days() -> None:
    longer = _pair(envelope(lookback=60, overlap=10), END)[1]
    window = _pair(envelope(lookback=30, overlap=10), END)[1]
    shorter = _pair(envelope(lookback=12, overlap=10), END)[1]
    assert longer.observed_correlation == window.observed_correlation
    assert shorter.observed_correlation != window.observed_correlation
    assert shorter.overlap_day_count == 12


def test_evidence_that_runs_past_the_evaluation_end_never_takes_part() -> None:
    evaluation_end = W0 + 25 * DAY
    evidence, pair = _pair(envelope(), evaluation_end)  # the standard worlds end five days after it
    assert [record.current_for_evaluation for record in evidence.sleeves] == [False, False]
    assert [record.reason_codes for record in evidence.sleeves] == [
        (_code("sleeve_evidence_extends_past_the_evaluation_end"),)
    ] * 2
    assert (pair.pair_status, pair.overlap_day_count, pair.effective_correlation) == (_UNKNOWN, 0, UNKNOWN_EFFECTIVE)
    assert pair.reason_codes == (
        _code(f"pair_sleeve_evidence_not_current:{ALPHA}"),
        _code(f"pair_sleeve_evidence_not_current:{BETA}"),
    )
    as_of = {sleeve_id: windowed_sleeve(sleeve_id, -5, 25, envelope()) for sleeve_id in (ALPHA, BETA)}
    current, current_pair = _pair(envelope(), evaluation_end, item(as_of[ALPHA]), item(as_of[BETA]))
    assert [record.window_end_ns for record in current.sleeves] == [evaluation_end, evaluation_end]
    assert (current_pair.pair_status, current_pair.overlap_start_ns, current_pair.overlap_day_count) == (
        _OBSERVED,
        W0 - 5 * DAY,
        30,
    )
    assert current_pair.observed_correlation == oracle_correlation(returns_of(as_of[ALPHA]), returns_of(as_of[BETA]))


def test_evidence_that_stops_before_the_evaluation_end_is_stale() -> None:
    evidence, pair = _pair(envelope(), END + 5 * DAY)
    assert [record.current_for_evaluation for record in evidence.sleeves] == [False, False]
    assert [record.reason_codes for record in evidence.sleeves] == [
        (_code("sleeve_evidence_ends_before_the_evaluation_end"),)
    ] * 2
    assert (pair.pair_status, pair.overlap_day_count, pair.effective_correlation) == (_UNKNOWN, 0, UNKNOWN_EFFECTIVE)
    assert pair.reason_codes == (
        _code(f"pair_sleeve_evidence_not_current:{ALPHA}"),
        _code(f"pair_sleeve_evidence_not_current:{BETA}"),
    )


def test_an_overlap_exactly_at_the_governed_minimum_is_observed_and_one_less_is_worst_case() -> None:
    assert world_correlation().pairs[0].overlap_day_count == world_correlation().min_overlap_days == 30
    assert world_correlation().pairs[0].pair_status is _OBSERVED
    evidence, pair = _pair(envelope(overlap=31), END)
    assert evidence.status is _READY
    assert (pair.pair_status, pair.effective_correlation) == (_UNKNOWN, UNKNOWN_EFFECTIVE)
    assert (pair.overlap_start_ns, pair.overlap_end_ns, pair.overlap_day_count) == (W0, END, 30)
    assert pair.reason_codes == (_code("pair_overlap_below_governed_minimum"),)


# --- exact UTC-day alignment ------------------------------------------------------------------------------------------


def test_pairs_align_by_exact_utc_day_identity_never_by_position() -> None:
    env = envelope()
    longer = windowed_sleeve(BETA, -5, 30, env)
    assert longer.evidence.status is _RG3_READY
    assert (longer.evidence.window_start_ns, longer.evidence.window_end_ns) == (W0 - 5 * DAY, END)
    assert longer.evidence.daily_returns[5:] == sleeve(BETA, env).evidence.daily_returns
    evidence, pair = _pair(env, END, item(sleeve(ALPHA, env)), item(longer))
    assert (pair.pair_status, pair.overlap_start_ns, pair.overlap_end_ns, pair.overlap_day_count) == (
        _OBSERVED,
        W0,
        END,
        30,
    )
    alpha, beta = returns_of(sleeve(ALPHA, env)), returns_of(longer)
    aligned = oracle_correlation(alpha, beta[5:])
    positional = oracle_correlation(alpha, beta[:30])
    assert pair.observed_correlation == aligned == world_correlation().pairs[0].observed_correlation
    assert positional != aligned
    assert evidence.positional_alignment_used is False
    assert [record.lookback_day_count for record in evidence.sleeves] == [30, 35]


def test_overlap_counts_only_the_common_days_of_the_pair() -> None:
    env = envelope(overlap=31)
    evidence, pair = _pair(env, END, item(sleeve(ALPHA, env)), item(windowed_sleeve(BETA, -5, 30, env)))
    assert [record.lookback_day_count for record in evidence.sleeves] == [30, 35]
    assert (pair.pair_status, pair.overlap_day_count) == (_UNKNOWN, 30)
    assert pair.reason_codes == (_code("pair_overlap_below_governed_minimum"),)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"evaluation_end_ns": END + 1}, "evaluation_end_ns_not_utc_day_aligned"),
        ({"evaluation_end_ns": END - DAY // 2}, "evaluation_end_ns_not_utc_day_aligned"),
        ({"evaluation_end_ns": 10 * DAY}, "evaluation_end_ns_precedes_the_lookback_window"),
        ({"evaluation_end_ns": True}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": float(END)}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": -DAY}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": INT64_MAX + 1}, "evaluation_end_ns_invalid"),
        ({"correlation_evidence_id": ""}, "correlation_evidence_id_invalid"),
        ({"correlation_evidence_id": "live-correlation"}, "forbidden_scope_token:correlation_evidence_id"),
        ({"correlation_id": _Text("corr-rg5")}, "correlation_id_invalid"),
        ({"correlation_id": "bist-corr"}, "bist_scope_leakage:correlation_id"),
    ],
    ids=lambda value: str(value)[:40],
)
def test_identity_and_the_injected_evaluation_end_are_validated(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build(correlation_inputs(**overrides))


@pytest.mark.parametrize("candidate", [None, "inputs", {}, 1])
def test_inputs_must_be_the_exact_record(candidate: object) -> None:
    with _raises("inputs_malformed"):
        build(candidate)


# --- numeric determinism ---------------------------------------------------------------------------------------------


_AMBIENT_CASES = (
    (["1", "2", "4"], ["1", "3", "2"]),
    (["-83", "-51", "95", "522", "-483"], ["-83", "-51", "95", "-483", "522"]),
    (["0.012", "-0.003", "0.007"], ["0.4", "0.1", "-0.25"]),
)


def test_the_estimator_never_reads_or_sets_the_ambient_decimal_context() -> None:
    baseline = [measured(x, y) for x, y in _AMBIENT_CASES]
    saved_default = (decimal.DefaultContext.prec, decimal.DefaultContext.rounding)
    with decimal.localcontext() as poisoned:
        poisoned.clear_flags()
        poisoned.prec = 2
        poisoned.rounding = decimal.ROUND_DOWN
        poisoned.Emax = 3
        poisoned.Emin = -3
        for signal in (decimal.Inexact, decimal.Rounded, decimal.Clamped, decimal.Subnormal, decimal.Underflow):
            poisoned.traps[signal] = True
        decimal.DefaultContext.prec, decimal.DefaultContext.rounding = 1, decimal.ROUND_UP
        try:
            assert [measured(x, y) for x, y in _AMBIENT_CASES] == baseline
            assert decimal.getcontext().prec == 2
            assert not any(decimal.getcontext().flags.values())
        finally:
            decimal.DefaultContext.prec, decimal.DefaultContext.rounding = saved_default


def test_world_evidence_is_immune_to_the_ambient_precision_rounding_and_default_context() -> None:
    # Only precision, rounding and the default context are poisoned here: the accepted RG-3 Sharpe substrate opens a
    # local context that inherits the caller's traps, so trap poisoning would fail its re-proof closed upstream.
    saved_default = decimal.DefaultContext.prec
    with decimal.localcontext() as poisoned:
        poisoned.prec = 2
        poisoned.rounding = decimal.ROUND_DOWN
        decimal.DefaultContext.prec = 1
        try:
            rebuilt = build(correlation_inputs())
        finally:
            decimal.DefaultContext.prec = saved_default
    assert rebuilt == world_correlation()


def test_every_public_correlation_has_exactly_eighteen_fractional_digits() -> None:
    evidence = build(
        correlation_inputs(
            portfolio_risk_envelope=envelope(sleeves=(ALPHA, BETA, GAMMA)),
            sleeves=items(envelope(sleeves=(ALPHA, BETA, GAMMA)), ALPHA, BETA, GAMMA),
        )
    )
    values = [pair.effective_correlation for pair in evidence.pairs] + [evidence.unknown_effective_correlation]
    assert all(PUBLIC_CORRELATION.fullmatch(value) for value in values)
    assert all(-1 <= Fraction(value) <= 1 for value in values)


def test_the_unknown_effective_correlation_is_the_rg2_worst_case_one_that_breaches_every_legal_cap() -> None:
    rg2_rules = paper_portfolio_risk_envelope_rule_set()
    worst = Fraction(UNKNOWN_EFFECTIVE)
    assert worst == Fraction(rg2_rules["correlation_cap_upper_bound_exclusive"]) == 1  # type: ignore[arg-type]
    assert paper_sleeve_correlation_rule_set()["unknown_effective_correlation"] == UNKNOWN_EFFECTIVE
    assert "worst_case_one" in str(rg2_rules["unknown_correlation_rule_id"])


# --- regime: pending, never fabricated -------------------------------------------------------------------------------


def test_regime_stratified_correlation_stays_pending_and_regime_evidence_unavailable() -> None:
    evidence = world_correlation()
    assert evidence.regime_stratified_correlation_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert evidence.regime_stratified_correlation_status == "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
    assert evidence.regime_stratified_correlation_status == envelope().regime_stratified_correlation_status
    assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert evidence.regime_evidence_available is False
    names = {item.name for item in fields(PaperSleeveCorrelationEvidence)} | {
        item.name
        for record in (PaperSleeveCorrelationPair, PaperSleeveCorrelationSleeveRecord)
        for item in fields(record)
    }
    assert {name for name in names if "regime" in name} == {
        "regime_stratified_correlation_status",
        "regime_evidence_status",
        "regime_evidence_available",
    }


def test_an_envelope_regime_status_other_than_pending_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(correlation_module, "EDGE_REGIME_LABEL_BINDING_PENDING", "SOME_RF_LABEL_SET")
    with _raises("portfolio_risk_envelope_regime_status_unsupported"):
        build(correlation_inputs())


# --- measurement only: no decision ------------------------------------------------------------------------------------


def test_the_evidence_decides_nothing() -> None:
    flags = dict(PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS)
    assert flags["paper_only"] is True
    assert not [name for name, value in flags.items() if value and name != "paper_only"]
    assert {
        "correlation_cap_breach_evaluated",
        "diversification_credit_granted",
        "portfolio_allocation_approved",
        "capital_allocated",
        "promotion_demotion_decided",
        "portfolio_stop_evaluated",
        "execution_authorized",
        "positional_alignment_used",
        "interpolation_used",
        "carry_forward_used",
        "backfill_used",
        "future_observation_used",
        "statistical_significance_proven",
        "live_ready",
    } <= set(flags)
    evidence = world_correlation()
    assert {name: getattr(evidence, name) for name in flags} == flags
    assert {item.name: item.default for item in fields(PaperSleeveCorrelationEvidence) if item.name in flags} == flags
    record_types = (PaperSleeveCorrelationEvidence, PaperSleeveCorrelationPair, PaperSleeveCorrelationSleeveRecord)
    names = {item.name for record_type in record_types for item in fields(record_type)} - set(flags)
    decision_words = re.compile(r"eligib|trigger|breach|verdict|tier|allocat|approv|decision|decided|diversif|within")
    assert not [name for name in names if decision_words.search(name)]


def test_the_cap_is_read_only_as_carried_provenance_and_no_threshold_is_ever_read() -> None:
    tree = ast.parse(Path(correlation_module.__file__).read_text(encoding="utf-8"))
    reads = [
        node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "max_pairwise_correlation"
    ]
    assert len(reads) == 1
    keywords = [
        keyword
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "max_pairwise_correlation"
    ]
    assert len(keywords) == 1
    assert keywords[0].value is reads[0]
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            compared = {sub.attr for sub in ast.walk(node) if isinstance(sub, ast.Attribute)}
            assert "max_pairwise_correlation" not in compared
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not attributes & {
        "ladder_boundaries",
        "portfolio_stop_levels",
        "total_paper_risk_budget",
        "max_paper_risk_budget",
        "market_caps",
        "paper_performance_reference_notional",
        "paper_sharpe_annualized",
    }


@pytest.mark.parametrize(
    "flag",
    [
        "correlation_cap_breach_evaluated",
        "diversification_credit_granted",
        "portfolio_allocation_approved",
        "future_observation_used",
        "regime_evidence_available",
        "live_ready",
    ],
)
def test_forged_decision_or_readiness_flags_fail_verification(flag: str) -> None:
    verification = verify(_reseal(world_correlation(), **{flag: True}), correlation_inputs())
    assert verification.intact is False
    assert _code(f"field_mismatch:{flag}") in verification.reason_codes


# --- tamper and totality ---------------------------------------------------------------------------------------------


def test_serialization_is_canonical_and_deterministic() -> None:
    evidence = world_correlation()
    payload = paper_sleeve_correlation_evidence_to_dict(evidence)
    assert json.loads(json.dumps(payload)) == payload
    assert paper_sleeve_correlation_evidence_digest(evidence) == evidence.correlation_evidence_digest
    again = build(correlation_inputs())
    assert again == evidence
    assert edge_canonical_json(paper_sleeve_correlation_evidence_to_dict(again)) == edge_canonical_json(payload)


def test_stale_self_digest_is_rejected() -> None:
    verification = verify(replace(world_correlation(), correlation_evidence_digest="0" * 64), correlation_inputs())
    assert verification.intact is False
    assert _code("self_digest_mismatch") in verification.reason_codes


def _pair_change(**changes: object) -> Callable[[PaperSleeveCorrelationEvidence], dict[str, object]]:
    return lambda e: {"pairs": (replace(e.pairs[0], **changes),)}


RESEALED_TAMPERS: dict[str, tuple[Callable[[PaperSleeveCorrelationEvidence], dict[str, object]], str]] = {
    "observed_correlation": (_pair_change(observed_correlation="0.900000000000000000"), "pairs"),
    "effective_correlation": (_pair_change(effective_correlation="0.000000000000000000"), "pairs"),
    "worst_case_to_zero": (
        _pair_change(pair_status=_UNKNOWN, observed_correlation="", effective_correlation="0.000000000000000000"),
        "pairs",
    ),
    "overlap": (_pair_change(overlap_day_count=29), "pairs"),
    "pair_reason": (_pair_change(reason_codes=(_code("pair_overlap_below_governed_minimum"),)), "pairs"),
    "pair_dropped": (lambda e: {"pairs": (), "pair_count": 0, "observed_pair_count": 0}, "pairs"),
    "pair_added": (lambda e: {"pairs": (*e.pairs, replace(e.pairs[0], sleeve_a_id=BETA, sleeve_b_id=ALPHA))}, "pairs"),
    "pair_reordered": (lambda e: {"pairs": (replace(e.pairs[0], sleeve_a_id=BETA, sleeve_b_id=ALPHA),)}, "pairs"),
    "counts": (lambda e: {"worst_case_pair_count": 1, "all_pairs_observed": False}, "worst_case_pair_count"),
    "status": (lambda e: {"status": _NEEDS_GOVERNANCE, "ready": False}, "status"),
    "reason_codes": (lambda e: {"reason_codes": (_code("portfolio_risk_envelope_not_governed"),)}, "reason_codes"),
    "pending_marker": (
        lambda e: {"regime_stratified_correlation_status": "REGIME_HIGH_VOL"},
        "regime_stratified_correlation_status",
    ),
    "lookback": (lambda e: {"lookback_window_days": 30}, "lookback_window_days"),
    "cap": (lambda e: {"max_pairwise_correlation": "0.100000000000000000"}, "max_pairwise_correlation"),
}


@pytest.mark.parametrize("name", sorted(RESEALED_TAMPERS))
def test_resealed_tamper_is_rejected_by_reconstruction(name: str) -> None:
    change, field_name = RESEALED_TAMPERS[name]
    evidence = world_correlation()
    verification = verify(_reseal(evidence, **change(evidence)), correlation_inputs())
    assert verification.intact is False
    assert _code(f"field_mismatch:{field_name}") in verification.reason_codes


def test_the_evidence_binds_its_exact_envelope_and_sleeves() -> None:
    evidence = world_correlation()
    other = envelope(lookback=45, overlap=12)
    swapped = verify(evidence, correlation_inputs(portfolio_risk_envelope=other, sleeves=items(other, ALPHA, BETA)))
    assert {_code("field_mismatch:envelope_digest"), _code("field_mismatch:lookback_window_days")} <= set(
        swapped.reason_codes
    )
    missing = verify(evidence, correlation_inputs(sleeves=items(envelope(), ALPHA)))
    assert {_code("field_mismatch:missing_sleeve_ids"), _code("field_mismatch:pairs")} <= set(missing.reason_codes)
    foreign = verify(
        evidence, correlation_inputs(portfolio_risk_envelope=other, sleeves=items(envelope(), ALPHA, BETA))
    )
    assert foreign.reason_codes == (_code("evidence_reconstruction_failed"),)


CORRUPTIONS: dict[str, Callable[[PaperSleeveCorrelationEvidence], dict[str, object]]] = {
    "status_alias": lambda e: {"status": "READY"},
    "pair_status_alias": lambda e: {"pairs": (replace(e.pairs[0], pair_status="OBSERVED"),)},
    "pairs_list": lambda e: {"pairs": list(e.pairs)},
    "float_window": lambda e: {"evaluation_end_ns": float(e.evaluation_end_ns)},
    "negative_count": lambda e: {"pair_count": -1},
    "float_correlation": lambda e: {"pairs": (replace(e.pairs[0], observed_correlation=0.3),)},
    "record_payload": lambda e: {"sleeves": ({"sleeve_id": ALPHA},)},
    "text_subclass": lambda e: {"correlation_id": _Text("corr-rg5")},
}


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_public_verifier_is_total_for_corrupted_evidence(name: str) -> None:
    evidence = replace(world_correlation())
    for field_name, value in CORRUPTIONS[name](evidence).items():
        object.__setattr__(evidence, field_name, value)
    verification = verify(evidence, correlation_inputs())
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_serialization_failed"),)


@pytest.mark.parametrize(
    "artifact",
    [None, "evidence", {}, object.__new__(PaperSleeveCorrelationEvidence)],
    ids=["none", "text", "dict", "uninitialized"],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    verification = verify(artifact, correlation_inputs())
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes


@pytest.mark.parametrize("inputs", [None, "inputs", {}], ids=["none", "text", "dict"])
def test_verification_against_malformed_inputs_fails_closed(inputs: object) -> None:
    verification = verify(world_correlation(), inputs)
    assert verification.intact is False
    assert verification.reason_codes == (_code("evidence_reconstruction_failed"),)


def test_evidence_is_frozen() -> None:
    evidence = world_correlation()
    with pytest.raises(FrozenInstanceError):
        evidence.ready = False  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        evidence.pairs[0].effective_correlation = "0.000000000000000000"  # type: ignore[misc]


# --- static discipline -----------------------------------------------------------------------------------------------


def test_module_is_pure_and_confines_decimal_to_one_explicit_context() -> None:
    source = Path(correlation_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    forbidden_modules = tuple(module for module in pit.FORBIDDEN_MODULES if module != "decimal")
    crypto_imports: set[str] = set()
    decimal_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
                assert not alias.name.startswith("crypto_core")
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in forbidden_modules)
            if node.module.startswith("crypto_core"):
                crypto_imports.add(node.module)
                assert not {alias.name for alias in node.names if alias.name.startswith("_")}
            if node.module == "decimal":
                decimal_names |= {alias.name for alias in node.names}
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
            assert not (isinstance(node.func, ast.Name) and name in pit.FORBIDDEN_BUILTINS), name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "__globals__", "__code__"}
    assert crypto_imports == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.paper_portfolio_risk_envelope",
        "crypto_core.validation.paper_sleeve_performance_evidence",
    }
    assert decimal_names == {"Context", "Decimal", "DivisionByZero", "InvalidOperation", "Overflow"}
    names = {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
    names |= {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not names & {"getcontext", "setcontext", "localcontext", "DefaultContext", "BasicContext", "ExtendedContext"}
    assert not [token for token in pit.FORBIDDEN_IDENTIFIERS if token in source.lower()]


def test_single_construction_site_serves_builder_and_verifier() -> None:
    world.assert_single_construction_site(
        correlation_module,
        "PaperSleeveCorrelationEvidence",
        "build_paper_sleeve_correlation_evidence",
        "verify_paper_sleeve_correlation_evidence",
    )


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(correlation_module)
    # Character, wire and Decimal representation bounds, the public scale, the pair size, the decimal base and the day.
    assert integers <= {0, 1, 2, 10, 18, 32, 80, 127, 256, 4096, 999999, world.DAY_NS, INT64_MAX}
    assert decimals <= {"0", "9", UNKNOWN_EFFECTIVE}
    flags = dict(PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS)
    for record_type in (
        PaperSleeveCorrelationInputs,
        PaperSleeveCorrelationSleeveInputs,
        PaperSleeveCorrelationPair,
        PaperSleeveCorrelationSleeveRecord,
        PaperPearsonCorrelationMeasurement,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record_type))
    assert all(
        item.default is dataclasses.MISSING for item in fields(PaperSleeveCorrelationEvidence) if item.name not in flags
    )


def test_rule_set_digest_commits_the_methodology() -> None:
    rule_set = paper_sleeve_correlation_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST
    assert world_correlation().rule_set_digest == PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST
    assert rule_set["methodology_id"] == METHOD_ID
    assert rule_set["decimal_policy_id"] == DECIMAL_POLICY_ID
    assert (rule_set["decimal_scale"], rule_set["decimal_internal_precision"]) == (18, 80)
    assert rule_set["decimal_rounding"] == decimal.ROUND_HALF_EVEN
    rg2_rules = paper_portfolio_risk_envelope_rule_set()
    assert rule_set["envelope_correlation_measure_id"] == rg2_rules["correlation_measure_id"]
    assert rule_set["envelope_unknown_correlation_rule_id"] == rg2_rules["unknown_correlation_rule_id"]
    for name, phrase in (
        ("estimator_rule_id", "rho_equals_sxy_over_sqrt_sxx_times_syy"),
        ("moment_rule_id", "denominator_convention_cancels"),
        ("decimal_context_rule_id", "ambient_never_used"),
        ("pair_universe_rule_id", "min_max_lexicographic"),
        ("day_identity_rule_id", "window_start_plus_i_days"),
        ("lookback_rule_id", "injected_utc_aligned_evaluation_end"),
        ("currency_rule_id", "window_ends_exactly_at_the_evaluation_end"),
        ("overlap_rule_id", "below_governed_min_overlap_is_worst_case_unknown"),
        ("zero_variance_rule_id", "worst_case_unknown"),
        ("unknown_rule_id", "never_zero_never_dropped_never_the_cap"),
        ("observation_rule_id", "no_positional_zip"),
        ("decision_ownership_rule_id", "rg5_decides_nothing"),
        ("regime_rule_id", "pending_until_an_accepted_rf_chain"),
    ):
        assert phrase in str(rule_set[name]), name
    rule_set["decimal_scale"] = 2
    assert paper_sleeve_correlation_rule_set()["decimal_scale"] == 18


def test_public_api_is_exact() -> None:
    assert set(correlation_module.__all__) == {
        "PAPER_SLEEVE_CORRELATION_NON_CLAIM_FLAGS",
        "PAPER_SLEEVE_CORRELATION_RULE_SET_DIGEST",
        "PaperPearsonCorrelationMeasurement",
        "PaperSleeveCorrelationEvidence",
        "PaperSleeveCorrelationEvidenceError",
        "PaperSleeveCorrelationInputs",
        "PaperSleeveCorrelationPair",
        "PaperSleeveCorrelationPairStatus",
        "PaperSleeveCorrelationSleeveInputs",
        "PaperSleeveCorrelationSleeveRecord",
        "PaperSleeveCorrelationStatus",
        "build_paper_sleeve_correlation_evidence",
        "measure_paper_pearson_correlation",
        "paper_sleeve_correlation_evidence_digest",
        "paper_sleeve_correlation_evidence_to_dict",
        "paper_sleeve_correlation_rule_set",
        "verify_paper_sleeve_correlation_evidence",
    }


# --- document authority ----------------------------------------------------------------------------------------------


def test_design_doc_records_the_rg5_methodology() -> None:
    docs = Path(__file__).resolve().parents[3] / "docs" / "crypto_core"
    text = " ".join((docs / "multi_sleeve_risk_governance_design.md").read_text(encoding="utf-8").split())
    rg5 = text[text.index("4. **RG-5") : text.index("5. **RG-6")]
    for phrase in (
        "measurement evidence only (`RG5_PEARSON_CORRELATION_METHODOLOGY_V1`)",
        "WORST-CASE 1.0 for budget math (never 0, never skipped)",
        "every unordered pair of envelope-declared sleeves exactly once as `(min, max)`, lexicographically sorted",
        "a one-sleeve envelope has none",
        "pairs align by day identity, never by position, interpolation, carry-forward or backfill",
        "`[evaluation_end - lookback_window_days, evaluation_end)`",
        "both only from the re-pinned RG-2 envelope",
        "a sleeve counts only when its evidence window ends exactly at the evaluation end, so no later observation,"
        " and no readiness that depends on one, takes part",
        "`rho = Sxy / sqrt(Sxx * Syy)` over exact `Fraction` moments",
        "sample-versus-population denominator cancels",
        "zero variance in either aligned vector makes the pair unknown",
        "`decimal_quantized_scale_18_round_half_even_internal_precision_80.v1`",
        "exactly 18 fractional digits, ROUND_HALF_EVEN, an explicit precision-80 context, signed zero normalized",
        "an unknown pair's effective correlation is exactly `1.000000000000000000`",
        "READY means the complete conservative matrix, never that every pair was observed",
        "RG-5 decides no cap breach, diversification credit or allocation",
        "Regime-stratified correlation is a pending field until the RF chain merges",
    ):
        assert phrase in rg5, phrase
