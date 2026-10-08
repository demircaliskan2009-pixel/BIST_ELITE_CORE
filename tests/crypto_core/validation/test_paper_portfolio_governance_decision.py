"""Tests for the RG-8 paper portfolio governance decision (RG8_PAPER_PORTFOLIO_GOVERNANCE_DECISION_V1).

Fixtures are REAL authenticated upstream artifacts, assembled into small terminal worlds on SYNTHETIC RG-2 envelopes over
the RG-3 world sleeves ``sleeve-alpha`` and ``sleeve-beta``:

* RG-4: the genuine drawdown evidence of both sleeves under the synthetic 0.6/0.4 performance-path policy. Its
  portfolio path does not depend on the envelope, so every world measures the same portfolio maximum M;
* RG-6: one genesis decision per sleeve over that RG-4 and over the RG-5 that RG-7 re-proves;
* RG-7: the RG-7 test module's authentic subjects (governed EF-7 admissions, attested EF-8 heads, real risk budgets)
  with the genuine RG-5 of the same envelope.

The levels of the decisive stop world sit around M: 0.01 lies between the current and the maximum peak distance, and
the other two levels are M truncated to 18 places and one unit above that. M is no 18-place decimal, so the exact
threshold-equality boundary drives the public builder through a FORGED RG-4 reconstruction instead (see that test).
Every expected stop outcome is recomputed with plain ``Fraction`` comparisons, never by the module.

Every approval, cap, stop level, budget and coordinate below is a SYNTHETIC TEST VALUE: RG-8 holds no production number.

Cost control: the EF-6, EF-7 and EF-8 memos and the RG-7 verifier memos are applied as in the RG-7 tests, and RG-8's
own three upstream builder references are memoized with the same exact memo, under a key that also covers the plain
dicts and floats of RG-3 strategy specs. A memo only returns the result of an identical earlier real call and its key
is the whole input: a tampered input is a miss and is built for real, and a tampered artifact is compared with the real
reconstruction. One default test re-proves the READY world without the RG-8 memos, and a slow test re-proves the
decisive stop world with every memo disabled.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import json
import re
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.edge_kill_quarantine_decision as ef8_module
import crypto_core.validation.edge_paper_admission_decision as ef7_module
import crypto_core.validation.paper_portfolio_allocation_decision as rg7
import crypto_core.validation.paper_portfolio_governance_decision as rg8
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeEvidenceVerification,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperPortfolioAllocationDecision,
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationStatus,
)
from crypto_core.validation.paper_portfolio_governance_decision import (
    PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS,
    PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST,
    PaperPortfolioGovernanceDecision,
    PaperPortfolioGovernanceError,
    PaperPortfolioGovernanceInputs,
    PaperPortfolioGovernanceSleeveInputs,
    PaperPortfolioGovernanceSleeveRecord,
    PaperPortfolioGovernanceStatus,
    PaperPortfolioStopLevelCheck,
    build_paper_portfolio_governance_decision,
    paper_portfolio_governance_decision_digest,
    paper_portfolio_governance_decision_to_dict,
    paper_portfolio_governance_rule_set,
    verify_paper_portfolio_governance_decision,
)
from crypto_core.validation.paper_portfolio_risk_envelope import (
    PaperPortfolioRiskEnvelope,
    PaperSleeveLadderTier,
    paper_portfolio_risk_envelope_digest,
)
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationSleeveInputs,
    build_paper_sleeve_correlation_evidence,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownStatus,
)
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderTransition,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_kill_quarantine_decision as ef8t
    import test_edge_paper_admission_decision as ef7t
    import test_edge_walk_forward_oos_evidence as ef6t
    import test_paper_portfolio_allocation_decision as rg7t
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_drawdown_evidence as rg4t
    import test_paper_sleeve_performance_evidence as rg3t
    import test_paper_sleeve_promotion_demotion_decision as rg6t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_kill_quarantine_decision as ef8t
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t
    from tests.crypto_core.validation import test_paper_portfolio_allocation_decision as rg7t
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t
    from tests.crypto_core.validation import test_paper_sleeve_promotion_demotion_decision as rg6t

_PREFIX = "paper_portfolio_governance_decision"
SLOW = pytest.mark.slow  # a memo-free re-proof of the decisive stop world; see the module docstring
DESIGN = Path(__file__).resolve().parents[3] / "docs" / "crypto_core" / "multi_sleeve_risk_governance_design.md"
SOURCE = Path(rg8.__file__).read_text(encoding="utf-8")
READY = PaperPortfolioGovernanceStatus.READY
STOP = PaperPortfolioGovernanceStatus.PORTFOLIO_STOP_TRIGGERED
REJECTED = PaperPortfolioGovernanceStatus.ALLOCATION_REJECTED
NOT_COMPUTABLE = PaperPortfolioGovernanceStatus.NOT_COMPUTABLE
NEEDS_GOVERNANCE = PaperPortfolioGovernanceStatus.NEEDS_GOVERNANCE_APPROVAL
ALPHA, BETA = rg4t.ALPHA, rg4t.BETA
INS, UNLISTED, PERP_BTC, PERP_ETH = rg7t.INS, rg7t.UNLISTED, rg7t.PERP_BTC, rg7t.PERP_ETH
W0, END, DAY = world.WINDOW_START, world.WINDOW_END, world.DAY_NS
UNIT = Fraction(1, 10**18)
INT64_MAX = 9223372036854775807
CONSUMPTION = "RG8_PORTFOLIO_STOP_MAX_PEAK_DISTANCE_V1"
OBSERVED_CORRELATION = ("0.6", 30, 20)
# SYNTHETIC TEST VALUES: more overlap days than the 30-day RG-3 world has, so the (alpha, beta) pair is worst case.
WORST_CASE_CORRELATION = ("0.6", 60, 45)
# SYNTHETIC TEST VALUES: beta's paper intents in the RG-7 variants (an unlisted market; a larger reservation).
UNLISTED_ROWS = ((UNLISTED, "1", "10"),)
LARGER_ROWS = ((INS, "2", "40"),)


# --- memoized re-proof of upstream artifacts (see module docstring) ---------------------------------------------------


def exact_key(value: object) -> object:
    """``ef6t._exact_key`` extended to the plain dicts and floats an RG-3 strategy spec carries; still exact and typed."""

    kind = type(value)
    if kind in (str, int, bool, type(None)) or isinstance(value, Enum):
        return kind, value
    if kind is float and value == value:  # a NaN has no exact key
        return kind, value.hex()  # type: ignore[attr-defined]
    if kind in (tuple, list):
        return kind, tuple(exact_key(item) for item in value)  # type: ignore[attr-defined]
    if kind is dict:
        items = ((exact_key(key), exact_key(item)) for key, item in value.items())  # type: ignore[attr-defined]
        return kind, tuple(sorted(items, key=repr))
    if is_dataclass(value) and not isinstance(value, type):
        return kind, tuple((item.name, exact_key(getattr(value, item.name))) for item in fields(value))
    raise TypeError(f"no exact memo key for {kind.__name__}")


_RG8_MEMOS = {
    name: ef6t._Memoized(getattr(rg8, name), exact_key)
    for name in (
        "build_paper_sleeve_drawdown_evidence",
        "build_paper_portfolio_allocation_decision",
        "build_paper_sleeve_promotion_demotion_decision",
    )
}


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        for (module, name), memo in ef6t._MEMOS.items():
            patch.setattr(module, name, memo)
        for name, memo in ef7t._EF7_MEMOS.items():
            patch.setattr(ef7_module, name, memo)
        for name, memo in ef8t._EF8_MEMOS.items():
            patch.setattr(ef8_module, name, memo)
        for name in ("verify_edge_kill_quarantine_decision", "verify_edge_paper_admission_decision"):
            patch.setattr(rg7, name, ef8t._EF8_MEMOS[name])
        for name, memo in _RG8_MEMOS.items():
            patch.setattr(rg8, name, memo)
        yield


# --- codes, oracles and reseals ---------------------------------------------------------------------------------------


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RG-8 construction error."""

    return pytest.raises(PaperPortfolioGovernanceError, match=f"^{re.escape(code(text))}$")


def scale18(value: Fraction) -> str:
    units = value * 10**18
    assert units.denominator == 1 and units >= 0
    return f"{units.numerator // 10**18}.{units.numerator % 10**18:018d}"


def ratio(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def oracle_distances(path: tuple[str, ...]) -> tuple[Fraction, Fraction]:
    """(current, maximum) peak distance of an index path with plain Fractions; the first observation is the first peak."""

    peak, distances = Fraction(0), []
    for value in map(Fraction, path):
        peak = max(peak, value)
        distances.append((peak - value) / peak)
    return distances[-1], max(distances)


def oracle_breaches(env: PaperPortfolioRiskEnvelope, maximum: Fraction) -> tuple[int, ...]:
    """The levels a maximum STRICTLY exceeds, from plain Fraction comparisons of the governed texts."""

    return tuple(
        level.stop_level
        for level in env.portfolio_stop_levels
        if maximum > Fraction(level.max_portfolio_drawdown_fraction)
    )


def reseal_envelope(env: PaperPortfolioRiskEnvelope, **changes: object) -> PaperPortfolioRiskEnvelope:
    changed = replace(env, **changes)  # type: ignore[arg-type]
    return replace(changed, envelope_digest=paper_portfolio_risk_envelope_digest(changed))


# --- authentic terminal worlds ----------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def envelope(
    stops: tuple[str, ...] | None = None,
    *,
    correlation: tuple[str, int, int] = OBSERVED_CORRELATION,
    approval: str = "human",
) -> PaperPortfolioRiskEnvelope:
    """A SYNTHETIC RG-2 envelope over the RG-3 world sleeves; ``stops`` replaces the RG-2 fixture's 0.05/0.1/0.15 levels.

    With the defaults it equals the RG-7 tests' ``caps_envelope()``, so their cached worlds are shared.
    """

    overrides: dict[str, object] = {
        "total_paper_risk_budget": rg2.d("1000"),
        "sleeve_caps": [rg2.sleeve(ALPHA, "400"), rg2.sleeve(BETA, "300")],
        "market_caps": [rg2.market(INS, "600"), rg2.market(PERP_BTC, "50"), rg2.market(PERP_ETH, "50")],
        "max_sleeve_count": 2,
        "correlation_cap": rg2.correlation(*correlation),
    }
    if stops is not None:
        overrides["portfolio_stop_levels"] = [rg2.stop(level, text) for level, text in enumerate(stops, 1)]
    if approval == "human":
        return rg2.governed(**overrides)
    if approval == "synthetic":
        return rg2.build(approval=rg2.approval_for(rg2.build(**overrides), kind=rg2.SYNTHETIC), **overrides)
    assert approval == "missing"
    return rg2.build(**overrides)


@functools.lru_cache(maxsize=None)
def targets(env: PaperPortfolioRiskEnvelope, blocked: bool = False) -> tuple[rg4t.SleeveWorld, rg4t.SleeveWorld]:
    """Alpha's and beta's RG-3 on ``env``; a blocked alpha has no funding evidence and is NOT_COMPUTABLE."""

    alpha = rg4t.sleeve_world(ALPHA, env)
    if blocked:
        inputs = rg3t.performance_inputs(
            portfolio_risk_envelope=env, **rg3t.blocked_valuation_inputs(funding_evidence=None)
        )
        alpha = rg4t.SleeveWorld(inputs, rg3t.build(inputs))
    return alpha, rg4t.sleeve_world(BETA, env)


@functools.lru_cache(maxsize=None)
def drawdown_of(
    env: PaperPortfolioRiskEnvelope, blocked: bool = False, approved_policy: bool = True
) -> tuple[PaperSleeveDrawdownInputs, PaperSleeveDrawdownEvidence]:
    inputs = rg4t.drawdown_inputs(
        portfolio_risk_envelope=env,
        performance_path_policy=rg4t.policy_for(env, approved=approved_policy),
        sleeves=tuple(target.drawdown_inputs() for target in targets(env, blocked)),
    )
    return inputs, _RG8_MEMOS["build_paper_sleeve_drawdown_evidence"](inputs)  # type: ignore[return-value]


@functools.lru_cache(maxsize=None)
def correlation_of(
    env: PaperPortfolioRiskEnvelope, blocked: bool = False
) -> tuple[PaperSleeveCorrelationInputs, PaperSleeveCorrelationEvidence]:
    """RG-5 over both sleeves at the evaluation end: the RG-7 tests' genuine one, or one over the blocked alpha."""

    if not blocked:
        return rg7t.correlation_of(env, True)
    inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id="rg5-for-rg8-blocked",
        correlation_id="corr-rg5",
        portfolio_risk_envelope=env,
        evaluation_end_ns=END,
        sleeves=tuple(PaperSleeveCorrelationSleeveInputs(item.inputs, item.evidence) for item in targets(env, True)),
    )
    return inputs, build_paper_sleeve_correlation_evidence(inputs)


@functools.lru_cache(maxsize=None)
def ladder_of(
    env: PaperPortfolioRiskEnvelope,
    sleeve_id: str,
    *,
    blocked: bool = False,
    approved_policy: bool = True,
    entered: int = W0,
    governed_seed: bool = True,
) -> PaperPortfolioGovernanceSleeveInputs:
    """One sleeve's historical RG-6 genesis decision at the evaluation end, over the world's RG-4 and RG-5."""

    if governed_seed:
        seed = rg6t.human_seed(env, entered, sleeve_id)
    else:
        seed = rg6t.make_seed(portfolio_risk_envelope=env, tier_entered_at_ns=entered, sleeve_id=sleeve_id)
    evidence = rg6t.Evidence(
        targets(env, blocked)[(ALPHA, BETA).index(sleeve_id)],
        *drawdown_of(env, blocked, approved_policy),
        *correlation_of(env, blocked),
    )
    inputs = rg6t.inputs_for(seed, evidence, decision_id=f"rg6-for-rg8-{sleeve_id}")
    decision = _RG8_MEMOS["build_paper_sleeve_promotion_demotion_decision"](inputs)
    return PaperPortfolioGovernanceSleeveInputs(sleeve_id, inputs, decision)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def allocation_of(
    env: PaperPortfolioRiskEnvelope,
    *,
    blocked: bool = False,
    beta_rows: tuple[tuple[str, str, str], ...] | None = None,
    attested: bool = True,
    observed: bool = True,
) -> tuple[PaperPortfolioAllocationInputs, PaperPortfolioAllocationDecision]:
    """RG-7 over alpha (75.5) and beta (40 unless ``beta_rows``); unattested: alpha's head has no approval.

    ``observed=False`` binds the RG-5 that supplies no sleeve (every pair worst case) instead of the world's RG-5.
    """

    correlation = correlation_of(env, blocked) if observed else rg7t.correlation_of(env, False)
    inputs = rg7t.allocation(
        env,
        rg7t.subject(ALPHA) if attested else rg7t.subject(ALPHA, approval=None),
        rg7t.subject(BETA, rows=beta_rows),
        correlation_inputs=correlation[0],
        correlation_evidence=correlation[1],
    )
    return inputs, _RG8_MEMOS["build_paper_portfolio_allocation_decision"](inputs)  # type: ignore[return-value]


@functools.lru_cache(maxsize=None)
def terminal(
    stops: tuple[str, ...] | None = None,
    *,
    correlation: tuple[str, int, int] = OBSERVED_CORRELATION,
    approval: str = "human",
    approved_policy: bool = True,
    blocked: bool = False,
    entered: int = W0,
    governed_seed: bool = True,
    beta_rows: tuple[tuple[str, str, str], ...] | None = None,
    attested: bool = True,
) -> PaperPortfolioGovernanceInputs:
    """One authentic terminal world; ``entered`` and ``governed_seed`` vary alpha's RG-6 seed only."""

    env = envelope(stops, correlation=correlation, approval=approval)
    drawdown_inputs, drawdown = drawdown_of(env, blocked, approved_policy)
    allocation_inputs, allocation = allocation_of(env, blocked=blocked, beta_rows=beta_rows, attested=attested)
    alpha = ladder_of(
        env, ALPHA, blocked=blocked, approved_policy=approved_policy, entered=entered, governed_seed=governed_seed
    )
    return PaperPortfolioGovernanceInputs(
        governance_decision_id="rg8-terminal-1",
        correlation_id="corr-rg8",
        portfolio_risk_envelope=env,
        evaluation_end_ns=END,
        drawdown_inputs=drawdown_inputs,
        drawdown_evidence=drawdown,
        sleeves=(alpha, ladder_of(env, BETA, blocked=blocked, approved_policy=approved_policy)),
        allocation_inputs=allocation_inputs,
        allocation_decision=allocation,
    )


@functools.lru_cache(maxsize=None)
def stop_levels() -> tuple[str, str, str]:
    """SYNTHETIC levels around the authentic portfolio maximum M, from an independent recomputation of the RG-4 path.

    0.01 lies strictly between the current and the maximum peak distance; M truncated to 18 places lies less than one
    unit below M, and one unit above that lies above M (M is no 18-place decimal).
    """

    current, maximum = oracle_distances(drawdown_of(envelope())[1].portfolio.measurement.index_path)  # type: ignore[union-attr]
    floor = Fraction(maximum.numerator * 10**18 // maximum.denominator, 10**18)
    assert current < Fraction("0.01") < floor < maximum < floor + UNIT
    return "0.01", scale18(floor), scale18(floor + UNIT)


def build(inputs: object) -> PaperPortfolioGovernanceDecision:
    return build_paper_portfolio_governance_decision(inputs)  # type: ignore[arg-type]


def verify(decision: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_paper_portfolio_governance_decision(decision, inputs)  # type: ignore[arg-type]


def assert_non_claims(decision: PaperPortfolioGovernanceDecision) -> None:
    flags = dict(PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS)
    assert {name: getattr(decision, name) for name in flags} == flags
    assert (decision.regime_advisory_status, decision.regime_evidence_status) == (
        EDGE_REGIME_LABEL_BINDING_PENDING,
        EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    )


@functools.lru_cache(maxsize=None)
def decided(stops: tuple[str, ...] | None = None, **scenario: object) -> PaperPortfolioGovernanceDecision:
    """Build a world's decision, then re-prove it by reconstruction: every decision a test reads is intact."""

    inputs = terminal(stops, **scenario)  # type: ignore[arg-type]
    decision = build(inputs)
    verification = verify(decision, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == decision.governance_decision_digest
    assert json.loads(verification.canonical_json) == paper_portfolio_governance_decision_to_dict(decision)
    assert_non_claims(decision)
    return decision


def stop_view(decision: PaperPortfolioGovernanceDecision) -> tuple[object, ...]:
    """Every field the portfolio stop decides."""

    return (
        decision.portfolio_stop_evaluated,
        decision.portfolio_stop_triggered,
        decision.portfolio_current_peak_distance,
        decision.portfolio_max_peak_distance,
        decision.drawdown_consumption,
        decision.stop_level_checks,
        decision.breached_stop_levels,
        decision.highest_breached_stop_level,
        decision.stop_reason_codes,
    )


def assert_not_evaluated(decision: PaperPortfolioGovernanceDecision, *blockers: str) -> None:
    """No stop decision exists: nothing measured is consumed and no zero drawdown is fabricated."""

    reasons = tuple(sorted(code(blocker) for blocker in blockers))
    assert stop_view(decision) == (False, False, "", "", CONSUMPTION, (), (), None, reasons)


def assert_terminal_allocation(
    decision: PaperPortfolioGovernanceDecision, allocation: PaperPortfolioAllocationDecision
) -> None:
    """READY carries every RG-7 final exactly; every other status governs zero and keeps RG-7's own finals."""

    finals = {sleeve.sleeve_id: sleeve.final_allocated_budget for sleeve in allocation.sleeves}
    accepted = decision.status is READY
    assert decision.ready is decision.paper_allocation_governance_accepted is accepted
    assert decision.allocation_status == allocation.status.value
    assert decision.allocation_total_final_allocated_budget == allocation.total_final_allocated_budget
    assert decision.terminal_total_final_allocated_budget == (
        allocation.total_final_allocated_budget if accepted else "0"
    )
    for record in decision.sleeves:
        assert record.allocation_final_allocated_budget == finals[record.sleeve_id]
        assert record.terminal_final_allocated_budget == (finals[record.sleeve_id] if accepted else "0")


# --- A. the READY world and the stop's consumption of the maximum -----------------------------------------------------


def test_a_ready_world_carries_the_exact_rg7_allocation_and_binds_every_input() -> None:
    inputs, decision = terminal(), decided()
    env, drawdown, allocation = inputs.portfolio_risk_envelope, inputs.drawdown_evidence, inputs.allocation_decision
    measurement = drawdown.portfolio.measurement
    assert measurement is not None
    assert (decision.status, decision.schema_version) == (READY, "paper-portfolio-governance-decision.v1")
    assert (decision.governance_decision_id, decision.correlation_id, decision.evaluation_end_ns) == (
        "rg8-terminal-1",
        "corr-rg8",
        END,
    )
    assert (
        decision.envelope_id,
        decision.envelope_version,
        decision.envelope_digest,
        decision.envelope_policy_digest,
        decision.envelope_advances,
    ) == (env.envelope_id, env.envelope_version, env.envelope_digest, env.policy_digest, True)
    assert (decision.drawdown_evidence_digest, decision.drawdown_status, decision.performance_path_policy_digest) == (
        drawdown.drawdown_evidence_digest,
        "READY",
        drawdown.performance_path_policy_digest,
    )
    # F4: the RG-2 fixture's levels are 0.05/0.1/0.15 and the maximum lies below the first: evaluated, no stop.
    current, maximum = oracle_distances(measurement.index_path)
    assert (Fraction(measurement.current_peak_distance), Fraction(measurement.max_peak_distance)) == (current, maximum)
    assert oracle_breaches(env, maximum) == ()
    checks = tuple(
        PaperPortfolioStopLevelCheck(level.stop_level, level.max_portfolio_drawdown_fraction, False)
        for level in env.portfolio_stop_levels
    )
    assert [check.max_portfolio_drawdown_fraction for check in checks] == [
        "0.050000000000000000",
        "0.100000000000000000",
        "0.150000000000000000",
    ]
    assert stop_view(decision) == (
        True,
        False,
        measurement.current_peak_distance,
        measurement.max_peak_distance,
        CONSUMPTION,
        checks,
        (),
        None,
        (),
    )
    assert (decision.correlation_evidence_digest, decision.allocation_decision_digest) == (
        allocation.correlation_evidence_digest,
        allocation.allocation_decision_digest,
    )
    assert_terminal_allocation(decision, allocation)
    assert decision.terminal_total_final_allocated_budget == "115.5"
    assert decision.declared_sleeve_ids == (ALPHA, BETA)
    performance = {record.sleeve_id: record.performance_evidence_digest for record in drawdown.sleeves}
    for record, sleeve, final in zip(decision.sleeves, inputs.sleeves, ("75.5", "40"), strict=True):
        assert record == PaperPortfolioGovernanceSleeveRecord(
            sleeve_id=sleeve.sleeve_id,
            performance_evidence_digest=performance[sleeve.sleeve_id],
            ladder_decision_digest=sleeve.ladder_decision.decision_digest,
            ladder_decision_status="READY",
            ladder_transition=PaperSleeveLadderTransition.PROMOTE.value,
            ladder_resulting_tier=PaperSleeveLadderTier.STANDARD.value,
            allocation_final_allocated_budget=final,
            terminal_final_allocated_budget=final,
        )
    assert (decision.governance_reason_codes, decision.reason_codes) == ((), ())
    assert (decision.rule_set_id, decision.rule_set_digest) == (
        "paper_portfolio_governance_decision_rules.v1",
        PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST,
    )


def test_the_stop_consumes_the_maximum_never_the_current_peak_distance() -> None:
    """F1, F5 and the finest authentic boundaries: current < 0.01 < M, and floor18(M) < M < floor18(M) + 1 unit."""

    levels = stop_levels()
    inputs, decision = terminal(levels), decided(levels)
    current, maximum = oracle_distances(inputs.drawdown_evidence.portfolio.measurement.index_path)  # type: ignore[union-attr]
    # The decisive negative control: the CURRENT peak distance lies below level 1 and only the maximum exceeds it.
    assert current < Fraction(levels[0]) < maximum
    assert (Fraction(decision.portfolio_current_peak_distance), Fraction(decision.portfolio_max_peak_distance)) == (
        current,
        maximum,
    )
    # Level 2 lies less than one unit below the maximum and still breaches; level 3 lies above it and does not.
    assert oracle_breaches(inputs.portfolio_risk_envelope, maximum) == (1, 2)
    assert [(check.stop_level, check.breached) for check in decision.stop_level_checks] == [
        (1, True),
        (2, True),
        (3, False),
    ]
    assert (decision.status, decision.portfolio_stop_evaluated, decision.portfolio_stop_triggered) == (STOP, True, True)
    assert (decision.breached_stop_levels, decision.highest_breached_stop_level) == ((1, 2), 2)
    breached = (code("portfolio_stop_level_breached:1"), code("portfolio_stop_level_breached:2"))
    assert decision.stop_reason_codes == decision.reason_codes == breached
    assert decision.governance_reason_codes == ()
    # H: a valid stop dominates a READY RG-7. Every terminal allocation is zero; RG-7's own finals stay evidence.
    assert inputs.allocation_decision.status is PaperPortfolioAllocationStatus.READY
    assert_terminal_allocation(decision, inputs.allocation_decision)
    assert [record.allocation_final_allocated_budget for record in decision.sleeves] == ["75.5", "40"]
    # The measured path does not depend on the envelope: this world measures exactly the READY world's maximum.
    assert decision.portfolio_max_peak_distance == decided().portfolio_max_peak_distance


@pytest.mark.parametrize(
    ("current", "maximum"),
    [
        pytest.param(Fraction(0), Fraction(0), id="flat"),
        pytest.param(Fraction(1, 100), Fraction(1, 20), id="max_equals_level_1"),
        pytest.param(Fraction(1, 100), Fraction(1, 20) + UNIT, id="max_one_unit_above_level_1"),
        pytest.param(Fraction(0), Fraction(1, 10), id="max_equals_level_2"),
        pytest.param(Fraction(0), Fraction(1, 10) + UNIT, id="max_one_unit_above_level_2"),
        pytest.param(Fraction(0), Fraction(3, 20), id="max_equals_level_3"),
        pytest.param(Fraction(0), Fraction(3, 20) + UNIT, id="every_level_breached"),
        pytest.param(Fraction(99, 100), Fraction(1, 20), id="a_current_above_every_level_never_triggers"),
        pytest.param(Fraction(0), Fraction(99, 100), id="a_zero_current_never_suppresses"),
    ],
)
def test_threshold_equality_never_breaches_and_one_unit_above_does(
    monkeypatch: pytest.MonkeyPatch, current: Fraction, maximum: Fraction
) -> None:
    """F2/F3 through the public builder over the RG-2 fixture levels 0.05/0.1/0.15.

    No authentic RG-4 path has an 18-place maximum, so the RG-4 builder is replaced by one returning the READY world's
    evidence with a forged portfolio measurement, which the inputs also carry (every digest binding still holds). The
    expectation is the independent Fraction oracle.
    """

    inputs = terminal()
    evidence = inputs.drawdown_evidence
    measurement = replace(
        evidence.portfolio.measurement,  # type: ignore[type-var]
        current_peak_distance=ratio(current),
        max_peak_distance=ratio(maximum),
    )
    forged = replace(evidence, portfolio=replace(evidence.portfolio, measurement=measurement))
    monkeypatch.setattr(rg8, "build_paper_sleeve_drawdown_evidence", lambda _inputs: forged)
    decision = build(replace(inputs, drawdown_evidence=forged))
    expected = oracle_breaches(inputs.portfolio_risk_envelope, maximum)
    assert [check.stop_level for check in decision.stop_level_checks if check.breached] == list(expected)
    assert (decision.breached_stop_levels, decision.highest_breached_stop_level) == (
        expected,
        max(expected, default=None),
    )
    assert (decision.portfolio_stop_triggered, decision.status) == (bool(expected), STOP if expected else READY)
    assert (decision.portfolio_current_peak_distance, decision.portfolio_max_peak_distance) == (
        ratio(current),
        ratio(maximum),
    )


# --- G/H. stop independence and precedence ----------------------------------------------------------------------------


def test_the_stop_depends_only_on_the_governed_levels_and_the_rg4_maximum() -> None:
    """G and H: RG-5, the RG-6 tier, the RG-7 amount and downstream governance never change or erase a valid stop."""

    levels = stop_levels()
    reference = decided(levels)
    variants = {
        "rg5_worst_case_and_rg7_rejected": {"correlation": WORST_CASE_CORRELATION},
        "rg6_alpha_holds_on_probation": {"entered": W0 + DAY},
        "rg7_larger_beta_reservation": {"beta_rows": LARGER_ROWS},
        "rg6_and_rg7_without_governance": {"governed_seed": False, "attested": False},
    }
    decisions = {name: decided(levels, **scenario) for name, scenario in variants.items()}
    for name, decision in decisions.items():
        assert stop_view(decision) == stop_view(reference), name
        assert decision.status is STOP, name
        assert_terminal_allocation(decision, terminal(levels, **variants[name]).allocation_decision)  # type: ignore[arg-type]
    # Each variant really changed what it names.
    worst = decisions["rg5_worst_case_and_rg7_rejected"]
    assert worst.correlation_evidence_digest != reference.correlation_evidence_digest
    assert worst.allocation_status == "ALLOCATION_REJECTED"
    assert code("allocation_decision_rejected") in worst.reason_codes
    hold = decisions["rg6_alpha_holds_on_probation"].sleeves[0]
    assert (hold.ladder_transition, hold.ladder_resulting_tier) == ("HOLD", "PROBATION")
    assert reference.sleeves[0].ladder_transition == "PROMOTE"
    assert decisions["rg7_larger_beta_reservation"].allocation_total_final_allocated_budget == "155.5"
    assert decisions["rg6_and_rg7_without_governance"].governance_reason_codes == (
        code("allocation_decision_needs_governance_approval"),
        code(f"ladder_decision_needs_governance_approval:{ALPHA}"),
    )


@pytest.mark.parametrize(
    ("scenario", "status", "reasons"),
    [
        pytest.param({"beta_rows": UNLISTED_ROWS}, REJECTED, ("allocation_decision_rejected",), id="rg7_rejected"),
        pytest.param(
            {"attested": False},
            NEEDS_GOVERNANCE,
            ("allocation_decision_needs_governance_approval",),
            id="rg7_unattested_head",
        ),
        pytest.param(
            {"governed_seed": False},
            NEEDS_GOVERNANCE,
            (f"ladder_decision_needs_governance_approval:{ALPHA}",),
            id="rg6_ungoverned_seed",
        ),
        pytest.param({"entered": W0 + DAY}, READY, (), id="rg6_other_historical_decision"),
    ],
)
def test_without_a_stop_the_downstream_outcomes_decide_the_status(
    scenario: dict[str, object], status: PaperPortfolioGovernanceStatus, reasons: tuple[str, ...]
) -> None:
    """D/E: downstream governance and rejection propagate; another historical RG-6 decision is just as valid."""

    inputs, decision = terminal(**scenario), decided(**scenario)  # type: ignore[arg-type]
    assert decision.status is status
    assert decision.reason_codes == tuple(sorted(code(reason) for reason in reasons))
    assert stop_view(decision) == stop_view(decided())
    assert_terminal_allocation(decision, inputs.allocation_decision)
    if status is READY:
        # A fork of alpha's ladder history: both records bind their own decision, neither is a current ladder head.
        assert decision.sleeves[0].ladder_decision_digest != decided().sleeves[0].ladder_decision_digest
        assert decision.sleeves[0].ladder_transition == "HOLD"
        assert decision.terminal_total_final_allocated_budget == decided().terminal_total_final_allocated_budget


def test_stop_authority_without_governance_evaluates_no_stop() -> None:
    """B/C/H: an ungoverned RG-2 or an ungoverned RG-4 never yields a stop decision, though its levels would breach."""

    levels = stop_levels()
    synthetic = decided(levels, approval="synthetic")
    assert (synthetic.status, synthetic.envelope_advances, synthetic.drawdown_status) == (
        NEEDS_GOVERNANCE,
        False,
        "NEEDS_GOVERNANCE_APPROVAL",
    )
    assert_not_evaluated(
        synthetic, "drawdown_evidence_needs_governance_approval", "portfolio_risk_envelope_not_governed"
    )
    assert_terminal_allocation(synthetic, terminal(levels, approval="synthetic").allocation_decision)
    unapproved = decided(levels, approved_policy=False)
    assert (unapproved.status, unapproved.envelope_advances, unapproved.drawdown_status) == (
        NEEDS_GOVERNANCE,
        True,
        "NEEDS_GOVERNANCE_APPROVAL",
    )
    assert_not_evaluated(unapproved, "drawdown_evidence_needs_governance_approval")
    assert unapproved.terminal_total_final_allocated_budget == "0"
    # A missing approval is no stop authority either (the stop stage itself, on the decisive levels).
    stage = rg8._portfolio_stop(envelope(levels, approval="missing"), terminal(levels).drawdown_evidence)
    assert (stage.evaluated, stage.governance_blockers, stage.breached, stage.max_peak_distance) == (
        False,
        (code("portfolio_risk_envelope_not_governed"),),
        (),
        "",
    )


def test_an_uncomputable_portfolio_drawdown_evaluates_no_stop() -> None:
    """C/F: alpha's RG-3 is NOT_COMPUTABLE, so RG-4 measures no portfolio and no zero drawdown is fabricated."""

    levels = stop_levels()
    inputs, decision = terminal(levels, blocked=True), decided(levels, blocked=True)
    assert inputs.drawdown_evidence.status is PaperSleeveDrawdownStatus.NOT_COMPUTABLE
    assert inputs.drawdown_evidence.portfolio.measurement is None
    assert decision.status is NOT_COMPUTABLE
    assert_not_evaluated(decision, "drawdown_evidence_not_computable", "portfolio_drawdown_not_computed")
    assert decision.sleeves[0].ladder_decision_status == "NOT_COMPUTABLE"
    assert code(f"ladder_decision_not_computable:{ALPHA}") in decision.reason_codes
    assert_terminal_allocation(decision, inputs.allocation_decision)


@pytest.mark.parametrize(
    ("stopped", "scenario", "status", "extra"),
    [
        pytest.param(False, {}, NOT_COMPUTABLE, (), id="alone"),
        pytest.param(
            False, {"beta_rows": UNLISTED_ROWS}, NOT_COMPUTABLE, ("allocation_decision_rejected",), id="over_rejection"
        ),
        pytest.param(
            False,
            {"attested": False},
            NEEDS_GOVERNANCE,
            ("allocation_decision_needs_governance_approval",),
            id="under_governance",
        ),
        pytest.param(
            True, {}, STOP, ("portfolio_stop_level_breached:1", "portfolio_stop_level_breached:2"), id="under_stop"
        ),
    ],
)
def test_a_not_computable_rg6_is_ordered_between_governance_and_rejection(
    monkeypatch: pytest.MonkeyPatch,
    stopped: bool,
    scenario: dict[str, object],
    status: PaperPortfolioGovernanceStatus,
    extra: tuple[str, ...],
) -> None:
    """D: with a READY RG-4 an RG-6 is NOT_COMPUTABLE only through a lineage whose earlier decision was, so alpha's
    rebuild is forged to that status (the inputs carry the same forged decision)."""

    inputs = terminal(stop_levels() if stopped else None, **scenario)  # type: ignore[arg-type]
    alpha = inputs.sleeves[0]
    forged = rg6t.reseal(alpha.ladder_decision, status=PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE)
    real = rg8.build_paper_sleeve_promotion_demotion_decision
    monkeypatch.setattr(
        rg8,
        "build_paper_sleeve_promotion_demotion_decision",
        lambda value: forged if value is alpha.ladder_decision_inputs else real(value),
    )
    decision = build(replace(inputs, sleeves=(replace(alpha, ladder_decision=forged), inputs.sleeves[1])))
    assert decision.status is status
    assert set(decision.reason_codes) == {code(f"ladder_decision_not_computable:{ALPHA}"), *map(code, extra)}
    assert decision.terminal_total_final_allocated_budget == "0"


@pytest.mark.parametrize(
    ("stage", "downstream", "not_computable", "rejected", "expected"),
    [
        ({}, (), (), False, READY),
        ({}, (), (), True, REJECTED),
        ({}, (), ("nc",), True, NOT_COMPUTABLE),
        ({}, ("gov",), ("nc",), True, NEEDS_GOVERNANCE),
        ({"breached": (1,)}, ("gov",), ("nc",), True, STOP),
        ({"computability": ("c",)}, ("gov",), ("nc",), True, NOT_COMPUTABLE),
        ({"governance": ("g",), "computability": ("c",)}, (), (), False, NEEDS_GOVERNANCE),
    ],
)
def test_the_terminal_status_order_is_exact(
    stage: dict[str, tuple[object, ...]],
    downstream: tuple[str, ...],
    not_computable: tuple[str, ...],
    rejected: bool,
    expected: PaperPortfolioGovernanceStatus,
) -> None:
    breached = stage.get("breached", ())
    stop = rg8._Stop(
        stage.get("governance", ()),  # type: ignore[arg-type]
        stage.get("computability", ()),  # type: ignore[arg-type]
        "",
        "",
        (),
        breached,  # type: ignore[arg-type]
        max(breached, default=None),  # type: ignore[arg-type]
    )
    status = rg8._terminal_status(
        stop=stop, downstream_governance=downstream, ladder_not_computable=not_computable, allocation_rejected=rejected
    )
    assert status is expected


# --- B/C/D/E/J. re-proof and cross-contract coherence -----------------------------------------------------------------


def swap(inputs: PaperPortfolioGovernanceInputs, **changes: object) -> PaperPortfolioGovernanceInputs:
    return replace(inputs, **changes)  # type: ignore[arg-type]


def with_alpha(inputs: PaperPortfolioGovernanceInputs, item: object) -> PaperPortfolioGovernanceInputs:
    return swap(inputs, sleeves=(item, inputs.sleeves[1]))


def other_rg7(inputs: PaperPortfolioGovernanceInputs, **options: object) -> PaperPortfolioGovernanceInputs:
    allocation_inputs, allocation = allocation_of(inputs.portfolio_risk_envelope, **options)  # type: ignore[arg-type]
    return swap(inputs, allocation_inputs=allocation_inputs, allocation_decision=allocation)


def tampered_measurement(inputs: PaperPortfolioGovernanceInputs) -> PaperPortfolioGovernanceInputs:
    evidence = inputs.drawdown_evidence
    measurement = replace(evidence.portfolio.measurement, max_peak_distance="1/2")  # type: ignore[type-var]
    return swap(
        inputs, drawdown_evidence=rg4t._reseal(evidence, portfolio=replace(evidence.portfolio, measurement=measurement))
    )


MISMATCHES = {
    "rg4_at_another_end": (
        lambda i: swap(i, evaluation_end_ns=END + DAY),
        "drawdown_evidence_not_at_the_evaluation_end",
    ),
    "rg4_of_another_envelope": (
        lambda i: swap(i, drawdown_inputs=terminal().drawdown_inputs, drawdown_evidence=terminal().drawdown_evidence),
        "drawdown_evidence_envelope_mismatch",
    ),
    "rg4_tampered_portfolio_measurement": (tampered_measurement, "drawdown_evidence_not_reconstructed"),
    "rg4_policy_of_another_envelope": (
        lambda i: swap(
            i, drawdown_inputs=replace(i.drawdown_inputs, performance_path_policy=rg4t.policy_for(envelope()))
        ),
        "drawdown_evidence_reconstruction_failed",
    ),
    "rg7_of_another_envelope": (
        lambda i: swap(
            i, allocation_inputs=terminal().allocation_inputs, allocation_decision=terminal().allocation_decision
        ),
        "allocation_decision_envelope_mismatch",
    ),
    "rg7_resealed": (
        lambda i: swap(
            i, allocation_decision=rg7t.reseal_decision(i.allocation_decision, total_final_allocated_budget="1")
        ),
        "allocation_decision_not_reconstructed",
    ),
    "rg7_unbuildable": (
        lambda i: swap(i, allocation_inputs=replace(i.allocation_inputs, allocation_id="")),
        "allocation_decision_reconstruction_failed",
    ),
    "rg7_over_another_rg5": (lambda i: other_rg7(i, observed=False), "ladder_decision_correlation_evidence_mismatch"),
    "rg6_of_another_envelope": (lambda i: with_alpha(i, terminal().sleeves[0]), "ladder_decision_envelope_mismatch"),
    "rg6_over_another_rg4": (
        lambda i: with_alpha(i, terminal(stop_levels(), approved_policy=False).sleeves[0]),
        "ladder_decision_drawdown_evidence_mismatch",
    ),
    "rg6_of_another_sleeve": (
        lambda i: with_alpha(i, replace(i.sleeves[1], sleeve_id=ALPHA)),
        "ladder_decision_sleeve_mismatch",
    ),
    "rg6_not_the_reconstruction": (
        lambda i: with_alpha(i, replace(i.sleeves[0], ladder_decision=i.sleeves[1].ladder_decision)),
        "ladder_decision_not_reconstructed",
    ),
    "rg6_unbuildable": (
        lambda i: with_alpha(
            i,
            replace(i.sleeves[0], ladder_decision_inputs=replace(i.sleeves[0].ladder_decision_inputs, decision_id="")),
        ),
        "ladder_decision_reconstruction_failed",
    ),
    "rg6_duplicate": (lambda i: swap(i, sleeves=(i.sleeves[0], i.sleeves[0])), "sleeve_ladder_decision_duplicate"),
    "rg6_missing": (lambda i: swap(i, sleeves=i.sleeves[:1]), "sleeve_ladder_decisions_incomplete"),
    "rg6_extra": (
        lambda i: swap(i, sleeves=(*i.sleeves, replace(i.sleeves[1], sleeve_id="sleeve-gamma"))),
        "sleeve_not_declared_by_envelope",
    ),
    "rg6_sleeve_id_invalid": (lambda i: with_alpha(i, replace(i.sleeves[0], sleeve_id="")), "sleeve_id_invalid"),
    "rg6_item_not_a_record": (lambda i: with_alpha(i, i.sleeves[0].ladder_decision), "sleeve_malformed"),
    "rg6_inputs_not_a_record": (
        lambda i: with_alpha(i, replace(i.sleeves[0], ladder_decision_inputs=None)),
        "ladder_decision_inputs_malformed",
    ),
    "rg6_decision_not_a_record": (
        lambda i: with_alpha(i, replace(i.sleeves[0], ladder_decision=None)),
        "ladder_decision_malformed",
    ),
    "sleeves_not_a_sequence": (lambda i: swap(i, sleeves=iter(i.sleeves)), "sleeves_malformed"),
}


@pytest.mark.parametrize("name", list(MISMATCHES))
def test_every_input_is_reproven_and_bound_to_one_evaluation_world(name: str) -> None:
    mutate, reason = MISMATCHES[name]
    with refused(reason):
        build(mutate(terminal(stop_levels())))


@pytest.mark.parametrize(
    ("builder", "changes", "reason"),
    [
        (
            "build_paper_portfolio_allocation_decision",
            {"evaluation_end_ns": END - DAY},
            "allocation_decision_not_at_the_evaluation_end",
        ),
        (
            "build_paper_sleeve_promotion_demotion_decision",
            {"evaluation_end_ns": END - DAY},
            "ladder_decision_not_at_the_evaluation_end",
        ),
        (
            "build_paper_sleeve_promotion_demotion_decision",
            {"performance_evidence_digest": "e" * 64},
            "ladder_decision_performance_evidence_mismatch",
        ),
    ],
)
def test_defence_in_depth_guards_fail_closed_on_a_forged_reconstruction(
    monkeypatch: pytest.MonkeyPatch, builder: str, changes: dict[str, object], reason: str
) -> None:
    """No accepted builder produces these: RG-7 binds RG-5 at its own end, and RG-6 binds its RG-3 to its RG-4. The
    builder is replaced by one returning a forged artifact that the inputs also carry."""

    inputs = terminal(stop_levels())
    if builder == "build_paper_portfolio_allocation_decision":
        forged: object = replace(inputs.allocation_decision, **changes)  # type: ignore[arg-type]
        target: object = inputs.allocation_inputs
        forged_inputs = swap(inputs, allocation_decision=forged)
    else:
        alpha = inputs.sleeves[0]
        forged = replace(alpha.ladder_decision, **changes)  # type: ignore[arg-type]
        target = alpha.ladder_decision_inputs
        forged_inputs = with_alpha(inputs, replace(alpha, ladder_decision=forged))
    real = getattr(rg8, builder)
    monkeypatch.setattr(rg8, builder, lambda value: forged if value is target else real(value))
    with refused(reason):
        build(forged_inputs)


def test_the_envelope_is_reproven_through_its_total_verifier() -> None:
    inputs = terminal()
    env = inputs.portfolio_risk_envelope
    with refused("portfolio_risk_envelope_not_intact"):
        build(swap(inputs, portfolio_risk_envelope=replace(env, total_paper_risk_budget=rg2.d("999"))))
    with refused("portfolio_risk_envelope_malformed"):
        build(swap(inputs, portfolio_risk_envelope=paper_portfolio_governance_rule_set()))


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"regime_stratified_correlation_status": "REGIME_BOUND_V1"}, "regime_status_unsupported"),
        ({"regime_concentration_demotion_status": "REGIME_BOUND_V1"}, "regime_status_unsupported"),
        ({"rule_set_digest": "e" * 64}, "portfolio_risk_envelope_rule_set_unsupported"),
    ],
)
def test_the_envelope_rule_set_and_pending_regime_markers_are_pinned(
    monkeypatch: pytest.MonkeyPatch, changes: dict[str, object], reason: str
) -> None:
    """K: no regime authority exists in V1. RG-2's own verifier refuses these resealed forgeries; behind it RG-8 pins
    the rule set and the pending markers itself (an intact forgery is simulated by replacing the RG-2 verifier)."""

    inputs = terminal()
    forged = swap(inputs, portfolio_risk_envelope=reseal_envelope(inputs.portfolio_risk_envelope, **changes))
    with refused("portfolio_risk_envelope_not_intact"):
        build(forged)
    monkeypatch.setattr(
        rg8, "verify_paper_portfolio_risk_envelope", lambda _env: EdgeEvidenceVerification(True, (), "", "")
    )
    with refused(reason):
        build(forged)


@pytest.mark.parametrize(
    ("name", "value", "reason"),
    [
        ("governance_decision_id", "", "governance_decision_id_invalid"),
        ("governance_decision_id", " rg8", "governance_decision_id_invalid"),
        ("governance_decision_id", "x" * 257, "governance_decision_id_invalid"),
        ("correlation_id", 7, "correlation_id_invalid"),
        ("correlation_id", "corr live", "forbidden_scope_token:correlation_id"),
        ("evaluation_end_ns", True, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", -DAY, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", INT64_MAX + 1, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", END + 1, "evaluation_end_ns_not_utc_day_aligned"),
        ("drawdown_inputs", None, "drawdown_inputs_malformed"),
        ("drawdown_evidence", None, "drawdown_evidence_malformed"),
        ("allocation_inputs", None, "allocation_inputs_malformed"),
        ("allocation_decision", None, "allocation_decision_malformed"),
        ("sleeves", None, "sleeves_malformed"),
    ],
)
def test_malformed_inputs_are_refused(name: str, value: object, reason: str) -> None:
    with refused(reason):
        build(swap(terminal(), **{name: value}))


def test_the_inputs_must_be_the_exact_record() -> None:
    for value in (None, {}, terminal().sleeves[0]):
        with refused("inputs_malformed"):
            build(value)


def test_sleeve_order_and_sequence_type_never_change_the_decision() -> None:
    inputs = terminal()
    assert build(swap(inputs, sleeves=list(reversed(inputs.sleeves)))) == decided()


# --- L/M. the verifier ------------------------------------------------------------------------------------------------


def altered(value: object) -> object:
    """A different value of the same wire kind."""

    if type(value) is bool:
        return not value
    if type(value) is int:
        return value + 1
    if value is None:
        return 1
    if isinstance(value, Enum):
        return next(member for member in type(value) if member is not value)
    if type(value) is str:
        return f"{value}-x" if value else "x"
    assert type(value) is tuple
    return value[:-1] if value else ("x",)


def test_every_field_is_digest_bound_and_reproven() -> None:
    levels = stop_levels()
    inputs, decision = terminal(levels), decided(levels)
    names = [item.name for item in fields(decision)]
    for name in (name for name in names if name != "governance_decision_digest"):
        changed = replace(decision, **{name: altered(getattr(decision, name))})
        assert paper_portfolio_governance_decision_digest(changed) != decision.governance_decision_digest, name
    for attribute in ("stop_level_checks", "sleeves"):
        records = getattr(decision, attribute)
        for item in fields(records[0]):
            record = replace(records[0], **{item.name: altered(getattr(records[0], item.name))})
            changed = replace(decision, **{attribute: (record, *records[1:])})
            assert paper_portfolio_governance_decision_digest(changed) != decision.governance_decision_digest, item.name
    # A resealed forgery of every field is named field by field; a stale self-digest is named too.
    forged = replace(decision, **{name: altered(getattr(decision, name)) for name in names})
    resealed = replace(forged, governance_decision_digest=paper_portfolio_governance_decision_digest(forged))
    assert set(verify(resealed, inputs).reason_codes) == {code(f"field_mismatch:{name}") for name in names}
    stale = verify(replace(decision, portfolio_stop_triggered=False), inputs)
    assert stale.reason_codes == (code("field_mismatch:portfolio_stop_triggered"), code("self_digest_mismatch"))


def test_the_verifier_is_total() -> None:
    inputs, decision = terminal(), decided()
    for value in (
        None,
        {},
        "decision",
        decision.sleeves[0],
        replace(decision, status="READY"),
        replace(decision, evaluation_end_ns=-1),
        replace(decision, sleeves=list(decision.sleeves)),
        replace(decision, portfolio_max_peak_distance=0.5),
    ):
        verification = verify(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in ((code("evidence_type_invalid"),), (code("evidence_serialization_failed"),))
    for broken in (None, swap(inputs, evaluation_end_ns=END + DAY), swap(inputs, sleeves=inputs.sleeves[:1])):
        assert verify(decision, broken).reason_codes == (code("evidence_reconstruction_failed"),)


def test_the_wire_form_is_canonical_json() -> None:
    payload = paper_portfolio_governance_decision_to_dict(decided(stop_levels()))
    assert json.loads(edge_canonical_json(payload)) == payload
    assert (payload["status"], payload["highest_breached_stop_level"]) == ("PORTFOLIO_STOP_TRIGGERED", 2)
    assert payload["stop_level_checks"][0] == {
        "stop_level": 1,
        "max_portfolio_drawdown_fraction": "0.010000000000000000",
        "breached": True,
    }


# --- N. design authority and static discipline ------------------------------------------------------------------------


def functions() -> dict[str, ast.FunctionDef]:
    return {node.name: node for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.FunctionDef)}


def test_the_module_is_pure_and_imports_only_its_terminal_inputs() -> None:
    # No RG-3, RG-5, EF, risk-budget or regime module: those are reached only through the RG-4, RG-6 and RG-7 re-proofs.
    pit.assert_module_is_pure(
        rg8,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_portfolio_allocation_decision",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_sleeve_drawdown_evidence",
            "crypto_core.validation.paper_sleeve_promotion_demotion_decision",
        },
    )
    assert "crypto_core.regime" not in SOURCE


def test_the_stop_reads_only_the_governed_levels_and_the_rg4_maximum() -> None:
    nodes = functions()
    called = {
        name: {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for name, function in nodes.items()
    }

    def callers(name: str) -> set[str]:
        return {caller for caller, names in called.items() if name in names}

    assert callers("PaperPortfolioGovernanceDecision") == {"build_paper_portfolio_governance_decision"}
    assert callers("build_paper_portfolio_governance_decision") == {"verify_paper_portfolio_governance_decision"}
    assert callers("_portfolio_stop") == {"build_paper_portfolio_governance_decision"}
    assert callers("_check_stop_levels") == callers("_peak_distance") == {"_portfolio_stop"}
    assert callers("_governed_threshold") == {"_check_stop_levels"}
    assert callers("Fraction") == {"_governed_threshold", "_peak_distance"}
    # The stage takes the envelope and the re-proven RG-4 only, and the comparator gets the MAXIMUM only.
    assert [argument.arg for argument in nodes["_portfolio_stop"].args.args] == ["envelope", "drawdown"]
    (call,) = [
        node
        for node in ast.walk(nodes["_portfolio_stop"])
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_check_stop_levels"
    ]
    assert [ast.unparse(argument) for argument in call.args] == [
        "_peak_distance(measurement.max_peak_distance)",
        "envelope.portfolio_stop_levels",
    ]
    (compare,) = [node for node in ast.walk(nodes["_check_stop_levels"]) if isinstance(node, ast.Compare)]
    assert [type(operator) for operator in compare.ops] == [ast.Gt]  # strict: equality never breaches
    # The current peak distance is carried as evidence only.
    tree = ast.parse(SOURCE)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    uses = [node for node in ast.walk(tree) if isinstance(node, ast.Attribute) and node.attr == "current_peak_distance"]
    assert len(uses) == 2
    for use in uses:
        parent = parents[use]
        assert (isinstance(parent, ast.keyword) and parent.arg == "portfolio_current_peak_distance") or (
            isinstance(parent, ast.Call) and getattr(parent.func, "id", None) == "_Stop"
        )
    # Nothing the stop stage reads names a tier, ladder, correlation, allocation, Sharpe, lifecycle or regime.
    read = {
        node.attr
        for name in ("_portfolio_stop", "_check_stop_levels")
        for node in ast.walk(nodes[name])
        if isinstance(node, ast.Attribute)
    }
    assert read and not [
        name
        for name in read
        if re.search(r"tier|transition|ladder|correlation|allocat|budget|sharpe|lifecycle|kill|regime", name)
    ]


def test_no_amount_is_ever_computed_and_only_ready_carries_the_rg7_finals() -> None:
    """No sizing, scaling, clipping or partial fit: the only arithmetic is the UTC-day check and the scale-18 base."""

    tree = ast.parse(SOURCE)
    annotations = [getattr(node, "annotation", None) for node in ast.walk(tree)]
    annotations += [node.returns for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
    typing = {id(inner) for node in annotations if node is not None for inner in ast.walk(node)}
    enclosing = {
        id(node): function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
    }
    operators = sorted(
        (enclosing.get(id(node), ""), type(node.op).__name__)
        for node in ast.walk(tree)
        if isinstance(node, (ast.BinOp, ast.AugAssign)) and id(node) not in typing
    )
    # Besides the day check and the scale-18 base, only the verifier's union of field-name sets.
    assert operators == [
        ("_governed_threshold", "Pow"),
        ("_require_utc_day", "Mod"),
        ("verify_paper_portfolio_governance_decision", "BitOr"),
    ]
    terminal_values = {
        ast.unparse(node.value)
        for node in ast.walk(functions()["build_paper_portfolio_governance_decision"])
        if isinstance(node, ast.keyword)
        and node.arg in {"terminal_final_allocated_budget", "terminal_total_final_allocated_budget"}
    }
    assert terminal_values == {
        "allocation_finals[sleeve_id] if accepted else _ZERO",
        "allocation.total_final_allocated_budget if accepted else _ZERO",
    }


def test_rg6_is_historical_provenance_only() -> None:
    """D: no ladder state, lineage, sequence, newest-object or current-head inference; tier and transition are carried."""

    attributes = {node.attr for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Attribute)}
    assert not [name for name in attributes if re.search(r"ladder_state|lineage|sequence|prior|newest|latest", name)]
    tree = ast.parse(SOURCE)
    parents = {child: node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in {"transition", "resulting_tier"}:
            record = parents[node]
            while not isinstance(record, ast.Call):  # the nearest enclosing call is the record that carries it
                record = parents[record]
            assert getattr(record.func, "id", None) == "PaperPortfolioGovernanceSleeveRecord"
    assert dict(PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS)["current_ladder_head_proven"] is False


def test_live_order_capital_and_scheduler_names_are_only_structural_false_flags() -> None:
    flags = dict(PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS)
    names: set[str] = set()
    for node in ast.walk(ast.parse(SOURCE)):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.arg):
            names.add(node.arg)
        elif isinstance(node, ast.keyword) and node.arg is not None:
            names.add(node.arg)
    risky = {
        name for name in names if re.search(r"live|order|capital|scheduler|connector|deribit|shadow|execution", name)
    }
    assert risky and risky <= set(flags)
    decision_fields = fields(PaperPortfolioGovernanceDecision)
    assert {item.name: item.default for item in decision_fields if item.name in flags} == flags
    assert all(item.default is dataclasses.MISSING for item in decision_fields if item.name not in flags)
    # The stop decision is RG-8's own: neither of its fields is a structural non-claim.
    assert not {"portfolio_stop_evaluated", "portfolio_stop_triggered"} & set(flags)
    assert (flags["regime_stop_triggered"], flags["regime_advisory_can_trigger_portfolio_stop"]) == (False, False)


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(rg8)
    # Text, identifier and wire bounds, the scale and its base, the UTC day, and indexes.
    assert integers <= {0, 1, 10, 18, 32, 60, 127, 128, 256, 4096, DAY, INT64_MAX}
    assert decimals <= {"0", "9"}
    for record in (PaperPortfolioGovernanceSleeveInputs, PaperPortfolioGovernanceInputs):
        assert all(item.default is dataclasses.MISSING for item in fields(record))


def test_the_rule_set_commits_the_controller_rules_and_is_handed_out_fresh() -> None:
    rule_set = paper_portfolio_governance_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST
    assert {
        key: rule_set[key]
        for key in (
            "contract_id",
            "structural_authority_id",
            "rg6_role_id",
            "rg7_role_id",
            "drawdown_consumption",
            "stop_breach_operator",
        )
    } == {
        "contract_id": "RG8_PAPER_PORTFOLIO_GOVERNANCE_DECISION_V1",
        "structural_authority_id": "RG8_TERMINAL_GOVERNANCE_AND_PORTFOLIO_STOP_POLICY_V1",
        "rg6_role_id": "BIND_EXACT_SAME_COORDINATE_RG6_DECISION_AS_HISTORICAL_PROVENANCE_ONLY",
        "rg7_role_id": "EXACT_REPROVEN_ALLOCATION_INPUT",
        "drawdown_consumption": CONSUMPTION,
        "stop_breach_operator": "STRICT_GREATER_THAN",
    }
    assert rule_set["status_order"] == (
        "provenance_contradiction_raises",
        "stop_authority_needs_governance_approval",
        "stop_input_not_computable",
        "portfolio_stop_triggered",
        "rg6_or_rg7_needs_governance_approval",
        "rg6_not_computable",
        "rg7_allocation_rejected",
        "ready",
    )
    rule_set["drawdown_consumption"] = "current_peak_distance"
    assert paper_portfolio_governance_rule_set()["drawdown_consumption"] == CONSUMPTION


def test_the_public_api_is_exact_and_offers_no_head_lookup() -> None:
    assert set(rg8.__all__) == {
        "PAPER_PORTFOLIO_GOVERNANCE_NON_CLAIM_FLAGS",
        "PAPER_PORTFOLIO_GOVERNANCE_RULE_SET_DIGEST",
        "PaperPortfolioGovernanceDecision",
        "PaperPortfolioGovernanceError",
        "PaperPortfolioGovernanceInputs",
        "PaperPortfolioGovernanceSleeveInputs",
        "PaperPortfolioGovernanceSleeveRecord",
        "PaperPortfolioGovernanceStatus",
        "PaperPortfolioStopLevelCheck",
        "build_paper_portfolio_governance_decision",
        "paper_portfolio_governance_decision_digest",
        "paper_portfolio_governance_decision_to_dict",
        "paper_portfolio_governance_rule_set",
        "verify_paper_portfolio_governance_decision",
    }
    assert not [name for name in rg8.__all__ if re.search(r"latest|registry|lookup|newest|head|current", name, re.I)]


def test_the_design_records_the_rg8_contract() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("7. **RG-8 `paper_portfolio_governance_decision.py`**")
    item = " ".join(text[start : text.index("## 2. Cross-cutting invariants", start)].split())
    for phrase in (
        "advisory regime-drift warnings never trigger stops by themselves",
        "RG-8 owns how portfolio-stop levels consume RG-4 portfolio drawdown evidence.",
        "`RG8_TERMINAL_GOVERNANCE_AND_PORTFOLIO_STOP_POLICY_V1`",
        "exactly one RG-6 decision per envelope-declared sleeve",
        "Any contradiction fails closed",
        "RG-6 is bound as historical provenance only",
        "`current_ladder_head_proven` stays False",
        "portfolio stop (`RG8_PORTFOLIO_STOP_MAX_PEAK_DISTANCE_V1`)",
        "only the RG-4 portfolio `max_peak_distance` is consumed",
        "The current peak distance is evidence only",
        "a level is breached iff the maximum is strictly greater than its threshold; equality does not breach",
        "never from a fabricated zero",
        "no correlation, tier, allocation amount, Sharpe, lifecycle state or regime marker creates or suppresses it",
        "PORTFOLIO_STOP_TRIGGERED for a valid stop, whatever RG-6 or RG-7 say",
        "READY carries every RG-7 final allocation exactly (`paper_allocation_governance_accepted`)",
        "Every other status governs zero for every sleeve while keeping the RG-7 proposal as evidence",
        "There is no sizing, scaling or partial fit",
        "never capital, an order, execution or readiness",
    ):
        assert phrase in item, phrase


# --- P. memo discipline and the memo-free re-proof --------------------------------------------------------------------


def test_the_rg8_memo_key_is_exact() -> None:
    assert exact_key({"a": 1, "b": 2.0}) == exact_key({"b": 2.0, "a": 1})
    assert exact_key({"a": 2.0}) != exact_key({"a": 2})
    assert exact_key(0.1 + 0.2) != exact_key(0.3)
    assert exact_key(0.5) != exact_key("0.5")
    assert exact_key(True) != exact_key(1)
    assert exact_key((1,)) != exact_key([1])
    for value in (float("nan"), Fraction(1, 2)):
        with pytest.raises(TypeError):
            exact_key(value)


def test_the_ready_world_re_proves_without_the_rg8_memos(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, memo in _RG8_MEMOS.items():
        monkeypatch.setattr(rg8, name, memo.real)
    verification = verify(decided(), terminal())
    assert (verification.intact, verification.reason_codes) == (True, ())


@SLOW
def test_the_decisive_stop_world_re_proves_with_every_memo_disabled() -> None:
    levels = stop_levels()
    inputs, decision = terminal(levels), decided(levels)
    ef6t._MEMO_ENABLED[0] = False
    try:
        verification = verify(decision, inputs)
    finally:
        ef6t._MEMO_ENABLED[0] = True
    assert (verification.intact, verification.reason_codes) == (True, ())
