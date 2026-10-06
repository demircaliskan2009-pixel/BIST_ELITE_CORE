"""RG-6 paper sleeve promotion and demotion decision (RG6_PAPER_SLEEVE_PROMOTION_DEMOTION_DECISION_V1) tests.

SYNTHETIC TEST VALUES ONLY. Every ladder threshold, tier entry, identifier and approval in this file is a synthetic test
value chosen to exercise one rule; none is a production ladder number, tier-entry fact or governance approval. The
evidence is genuine: every RG-3, RG-4 and RG-5 artifact is built through its accepted public builder from the shared
authentic sleeve worlds.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import inspect
import json
import re
from dataclasses import FrozenInstanceError, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_drawdown_evidence as drawdown_module
import crypto_core.validation.paper_sleeve_promotion_demotion_decision as decision_module
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
)
from crypto_core.validation.paper_portfolio_performance_path_policy import PaperPortfolioPerformancePathPolicy
from crypto_core.validation.paper_portfolio_risk_envelope import PaperPortfolioRiskEnvelope, PaperSleeveLadderTier
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationPairStatus,
    PaperSleeveCorrelationSleeveInputs,
    PaperSleeveCorrelationStatus,
    build_paper_sleeve_correlation_evidence,
    paper_sleeve_correlation_evidence_digest,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import build_paper_sleeve_daily_valuation_evidence
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownEvidence,
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownStatus,
    build_paper_sleeve_drawdown_evidence,
    paper_sleeve_drawdown_evidence_digest,
)
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceStatus,
    paper_sleeve_performance_evidence_digest,
)
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS,
    PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderError,
    PaperSleeveLadderPriorDecision,
    PaperSleeveLadderSeed,
    PaperSleeveLadderSeedApproval,
    PaperSleeveLadderSeedApprovalKind,
    PaperSleeveLadderTransition,
    PaperSleevePromotionDemotionDecision,
    PaperSleevePromotionDemotionInputs,
    build_paper_sleeve_ladder_seed,
    build_paper_sleeve_promotion_demotion_decision,
    paper_sleeve_ladder_seed_digest,
    paper_sleeve_ladder_seed_from_payload,
    paper_sleeve_ladder_seed_to_dict,
    paper_sleeve_promotion_demotion_decision_digest,
    paper_sleeve_promotion_demotion_decision_to_dict,
    paper_sleeve_promotion_demotion_rule_set,
    verify_paper_sleeve_ladder_seed,
    verify_paper_sleeve_promotion_demotion_decision,
)
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so the authentic worlds and their caches are built once
    import test_paper_portfolio_performance_path_policy as rg4p
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_correlation_evidence as rg5t
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_drawdown_evidence as rg4t
    import test_paper_sleeve_performance_evidence as rg3t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_paper_portfolio_performance_path_policy as rg4p
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_correlation_evidence as rg5t
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t

_PREFIX = "paper_sleeve_promotion_demotion_decision"
PROBATION, STANDARD, EXPANDED = (
    PaperSleeveLadderTier.PROBATION,
    PaperSleeveLadderTier.STANDARD,
    PaperSleeveLadderTier.EXPANDED,
)
HOLD, PROMOTE, DEMOTE = (
    PaperSleeveLadderTransition.HOLD,
    PaperSleeveLadderTransition.PROMOTE,
    PaperSleeveLadderTransition.DEMOTE,
)
READY = PaperSleeveLadderDecisionStatus.READY
NOT_COMPUTABLE = PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
NEEDS_GOVERNANCE = PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL
HUMAN = PaperSleeveLadderSeedApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperSleeveLadderSeedApprovalKind.TEST_ONLY_SYNTHETIC
ALPHA, BETA = rg4t.ALPHA, rg4t.BETA
W0, DAY, END = world.WINDOW_START, world.DAY_NS, world.WINDOW_END
INT64_MAX = 9223372036854775807
UNIT = Fraction(1, 10**18)
TIER_INDEX = {PROBATION: 0, STANDARD: 1, EXPANDED: 2}
DESIGN_DOC = Path(__file__).resolve().parents[3] / "docs" / "crypto_core" / "multi_sleeve_risk_governance_design.md"

# SYNTHETIC TEST ladders, as (lower boundary overrides, upper boundary overrides) of the RG-2 fixture ladder.
# Over the chain windows they yield PROMOTE, PROMOTE, HOLD, DEMOTE and HOLD.
CHAIN_LADDER = (
    (
        ("probation", 25),
        ("promotion_sharpe", "1"),
        ("promotion_drawdown", "0.05"),
        ("demotion_sharpe", "0.5"),
        ("demotion_drawdown", "0.1"),
    ),
    (
        ("probation", 5),
        ("promotion_sharpe", "1.6"),
        ("promotion_drawdown", "0.05"),
        ("demotion_sharpe", "1.2"),
        ("demotion_drawdown", "0.1"),
    ),
)
CHAIN_WINDOWS = ((-5, 25), (0, 30), (5, 35), (10, 40), (15, 45))
# Drawdown ceilings strictly between the current and the maximum peak distance of the (15, 45) window.
DRAWDOWN_LADDER = (
    (
        ("probation", 30),
        ("promotion_sharpe", "1"),
        ("promotion_drawdown", "0.02"),
        ("demotion_sharpe", "0"),
        ("demotion_drawdown", "0.03"),
    ),
    (
        ("probation", 60),
        ("promotion_sharpe", "1.5"),
        ("promotion_drawdown", "0.01"),
        ("demotion_sharpe", "0.5"),
        ("demotion_drawdown", "0.15"),
    ),
)


class _Text(str):
    """A ``str`` subclass: never an exact text."""


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def codes(*names: str) -> tuple[str, ...]:
    return tuple(sorted(_code(name) for name in names))


def _raises(code: str):
    return pytest.raises(PaperSleeveLadderError, match=f"^{re.escape(_code(code))}$")


def scale18(value: Fraction) -> str:
    """Canonical scale-18 text of a value with at most 18 fractional digits."""

    units = value * 10**18
    assert units.denominator == 1
    magnitude = abs(units.numerator)
    text = f"{magnitude // 10**18}.{magnitude % 10**18:018d}"
    return f"-{text}" if units < 0 else text


def unit_above(text: str) -> str:
    return scale18(Fraction(text) + UNIT)


# --- the governed genesis seed --------------------------------------------------------------------------------------


def seed_args(**overrides: object) -> dict[str, object]:
    """SYNTHETIC TEST VALUES for every seed input; no default exists in the module itself."""

    args: dict[str, object] = {
        "seed_id": "rg6-synthetic-seed",
        "seed_version": "synthetic-v1",
        "portfolio_risk_envelope": rg3t.world_envelope(),
        "sleeve_id": ALPHA,
        "tier_entered_at_ns": W0,
        "approval": None,
    }
    args.update(overrides)
    return args


def build_seed(**overrides: object) -> PaperSleeveLadderSeed:
    return build_paper_sleeve_ladder_seed(**seed_args(**overrides))  # type: ignore[arg-type]


def seed_approval(
    seed: PaperSleeveLadderSeed, *, kind: object = HUMAN, **overrides: object
) -> PaperSleeveLadderSeedApproval:
    """A synthetic test approval committing exactly to ``seed`` unless overridden."""

    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "a" * 64,
        "approval_kind": kind,
        "approved_seed_id": seed.seed_id,
        "approved_seed_version": seed.seed_version,
        "approved_seed_policy_digest": seed.seed_policy_digest,
        "approved_rule_set_digest": seed.rule_set_digest,
    }
    values.update(overrides)
    return PaperSleeveLadderSeedApproval(**values)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def governed_seed(
    env: PaperPortfolioRiskEnvelope | None = None, entered: int = W0, sleeve_id: str = ALPHA
) -> PaperSleeveLadderSeed:
    """A seed under an exact synthetic HUMAN_GOVERNANCE test approval (PASS-branch fixture only)."""

    overrides = {
        "portfolio_risk_envelope": rg3t.world_envelope() if env is None else env,
        "tier_entered_at_ns": entered,
        "sleeve_id": sleeve_id,
    }
    return build_seed(approval=seed_approval(build_seed(**overrides)), **overrides)


def _reseal_seed(seed: PaperSleeveLadderSeed, **changes: object) -> PaperSleeveLadderSeed:
    changed = replace(seed, **changes)
    return replace(changed, ladder_seed_digest=paper_sleeve_ladder_seed_digest(changed))


def _assert_seed_intact(seed: PaperSleeveLadderSeed) -> None:
    verification = verify_paper_sleeve_ladder_seed(seed)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == seed.ladder_seed_digest
    assert paper_sleeve_ladder_seed_from_payload(json.loads(verification.canonical_json)) == seed


# --- synthetic envelopes and genuine evidence -----------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def ladder_envelope(
    lower: tuple[tuple[str, object], ...] = (), upper: tuple[tuple[str, object], ...] = ()
) -> PaperPortfolioRiskEnvelope:
    """A governed SYNTHETIC one-sleeve RG-2 envelope over alpha with the RG-2 fixture ladder overridden."""

    return rg2.governed(
        sleeve_caps=[rg2.sleeve(ALPHA, "400")],
        ladder_boundaries=[rg2.lower_boundary(**dict(lower)), rg2.upper_boundary(**dict(upper))],
    )


@functools.lru_cache(maxsize=None)
def path_policy(env: PaperPortfolioRiskEnvelope) -> PaperPortfolioPerformancePathPolicy:
    if [cap.sleeve_id for cap in env.sleeve_caps] == [ALPHA]:
        return rg4p.governed(portfolio_risk_envelope=env, performance_weights=[rg4p.weight(ALPHA, "1")])
    return rg4t.policy_for(env)


@dataclasses.dataclass(frozen=True)
class Evidence:
    """One target sleeve's RG-3 world and the RG-4 and RG-5 evidence that bind it."""

    target: rg4t.SleeveWorld
    drawdown_inputs: PaperSleeveDrawdownInputs
    drawdown: PaperSleeveDrawdownEvidence
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation: PaperSleeveCorrelationEvidence


@functools.lru_cache(maxsize=None)
def world_evidence() -> Evidence:
    """The shared authentic world: alpha's RG-3, with RG-4 and RG-5 over alpha and beta on the RG-2 fixture."""

    return Evidence(
        rg4t.sleeve_world(ALPHA),
        rg4t.drawdown_inputs(),
        rg4t.world_drawdown(),
        rg5t.correlation_inputs(),
        rg5t.world_correlation(),
    )


def bound_evidence(env: PaperPortfolioRiskEnvelope, target: rg4t.SleeveWorld) -> Evidence:
    """RG-4 and RG-5 over ``target`` alone, on its own window and at its own window end."""

    start, end = target.evidence.window_start_ns, target.evidence.window_end_ns
    drawdown_inputs = PaperSleeveDrawdownInputs(
        drawdown_evidence_id=f"rg4-{target.evidence.sleeve_id}-{(start - W0) // DAY}-{(end - W0) // DAY}",
        correlation_id="corr-rg6",
        portfolio_risk_envelope=env,
        performance_path_policy=path_policy(env),
        window_start_ns=start,
        window_end_ns=end,
        sleeves=(target.drawdown_inputs(),),
    )
    correlation_inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id=f"rg5-{target.evidence.sleeve_id}-{(end - W0) // DAY}",
        correlation_id="corr-rg6",
        portfolio_risk_envelope=env,
        evaluation_end_ns=end,
        sleeves=(PaperSleeveCorrelationSleeveInputs(target.inputs, target.evidence),),
    )
    return Evidence(
        target,
        drawdown_inputs,
        build_paper_sleeve_drawdown_evidence(drawdown_inputs),
        correlation_inputs,
        build_paper_sleeve_correlation_evidence(correlation_inputs),
    )


@functools.lru_cache(maxsize=None)
def evidence_for(
    env: PaperPortfolioRiskEnvelope, window: tuple[int, int] | None = None, sleeve_id: str = ALPHA
) -> Evidence:
    """``sleeve_id`` alone over ``window`` (the shared world window by default) on ``env``."""

    target = rg4t.sleeve_world(sleeve_id, env) if window is None else rg5t.windowed_sleeve(sleeve_id, *window, env)
    return bound_evidence(env, target)


def with_beta(target: rg4t.SleeveWorld) -> Evidence:
    """RG-4 and RG-5 over ``target`` and the authentic beta world on the RG-2 fixture."""

    drawdown_inputs = rg4t.drawdown_inputs(
        sleeves=(target.drawdown_inputs(), rg4t.sleeve_world(BETA).drawdown_inputs())
    )
    correlation_inputs = rg5t.correlation_inputs(sleeves=(rg5t.item(target), rg5t.item(rg5t.sleeve(BETA))))
    return Evidence(
        target,
        drawdown_inputs,
        rg4t.build(drawdown_inputs),
        correlation_inputs,
        rg5t.build(correlation_inputs),
    )


def blocked_target(**valuation_overrides: object) -> rg4t.SleeveWorld:
    inputs = rg3t.performance_inputs(**rg3t.blocked_valuation_inputs(**valuation_overrides))
    return rg4t.SleeveWorld(inputs, rg3t.build(inputs))


@functools.lru_cache(maxsize=None)
def ungoverned_beta() -> rg4t.SleeveWorld:
    """Beta's genuine world under an ungoverned equity-basis policy: its RG-3 needs governance approval."""

    policy_id = BETA.replace("sleeve", "policy")
    episodes = world.build_chain(
        rg4t.SLEEVE_PLANS[BETA],
        draft=world.make_draft(BETA, policy_id),
        capacity_policy=world.make_capacity_policy(BETA, policy_id),
    )
    valuation_inputs = world.valuation_inputs(
        valuation_id="sleeve-valuation-sleeve-beta-ungoverned",
        episodes=episodes,
        day_closes=tuple(world.build_day_close(day, episodes) for day in range(world.WINDOW_DAYS)),
        equity_basis_policy=world.basis_policy(sleeve_id=BETA, governed=False),
        funding_evidence=world.funding_evidence(sleeve_id=BETA, events=world.funding_events(episodes)),
    )
    inputs = rg3t.performance_inputs(
        performance_evidence_id="rg3-sleeve-beta-ungoverned",
        valuation_inputs=valuation_inputs,
        valuation=build_paper_sleeve_daily_valuation_evidence(valuation_inputs),
        **rg3t.NO_SERIES,
    )
    return rg4t.SleeveWorld(inputs, rg3t.build(inputs))


# --- decisions ------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Decided:
    """One decision and the exact inputs it is rebuilt from."""

    inputs: PaperSleevePromotionDemotionInputs
    decision: PaperSleevePromotionDemotionDecision

    def prior(self) -> PaperSleeveLadderPriorDecision:
        return PaperSleeveLadderPriorDecision(decision_inputs=self.inputs, decision=self.decision)


def decision_inputs(state: object, evidence: Evidence, **overrides: object) -> PaperSleevePromotionDemotionInputs:
    values: dict[str, object] = {
        "decision_id": "rg6-decision-1",
        "correlation_id": "corr-rg6",
        "portfolio_risk_envelope": evidence.target.inputs.portfolio_risk_envelope,
        "ladder_state": state,
        "evaluation_end_ns": evidence.target.evidence.window_end_ns,
        "performance_inputs": evidence.target.inputs,
        "performance_evidence": evidence.target.evidence,
        "drawdown_inputs": evidence.drawdown_inputs,
        "drawdown_evidence": evidence.drawdown,
        "correlation_inputs": evidence.correlation_inputs,
        "correlation_evidence": evidence.correlation,
    }
    values.update(overrides)
    return PaperSleevePromotionDemotionInputs(**values)  # type: ignore[arg-type]


def decide(inputs: object) -> PaperSleevePromotionDemotionDecision:
    return build_paper_sleeve_promotion_demotion_decision(inputs)  # type: ignore[arg-type]


def decided(inputs: PaperSleevePromotionDemotionInputs) -> Decided:
    return Decided(inputs, decide(inputs))


def verify(decision: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_promotion_demotion_decision(decision, inputs)  # type: ignore[arg-type]


def _reseal(decision: PaperSleevePromotionDemotionDecision, **changes: object) -> PaperSleevePromotionDemotionDecision:
    changed = replace(decision, **changes)
    return replace(changed, decision_digest=paper_sleeve_promotion_demotion_decision_digest(changed))


def _assert_intact(built: Decided) -> None:
    verification = verify(built.decision, built.inputs)
    assert verification.intact is True, verification.reason_codes
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == built.decision.decision_digest
    assert json.loads(verification.canonical_json) == paper_sleeve_promotion_demotion_decision_to_dict(built.decision)


def _record(evidence: Evidence, sleeve_id: str = ALPHA):
    return next(record for record in evidence.drawdown.sleeves if record.sleeve_id == sleeve_id)


@functools.lru_cache(maxsize=None)
def world_genesis(entered: int = W0) -> Decided:
    return decided(decision_inputs(governed_seed(entered=entered), world_evidence()))


@functools.lru_cache(maxsize=None)
def chain_link(index: int) -> Decided:
    env = ladder_envelope(*CHAIN_LADDER)
    state = governed_seed(env) if index == 0 else chain_link(index - 1).prior()
    return decided(decision_inputs(state, evidence_for(env, CHAIN_WINDOWS[index]), decision_id=f"rg6-chain-{index}"))


@functools.lru_cache(maxsize=None)
def holding_link(index: int) -> Decided:
    """A lineage whose genesis holds one day short of the PROBATION tenure, then promotes."""

    env = ladder_envelope(*CHAIN_LADDER)
    state = governed_seed(env, W0 + DAY) if index == 0 else holding_link(0).prior()
    return decided(decision_inputs(state, evidence_for(env, CHAIN_WINDOWS[index]), decision_id=f"rg6-hold-{index}"))


@functools.lru_cache(maxsize=None)
def drawdown_hold() -> Decided:
    env = ladder_envelope(*DRAWDOWN_LADDER)
    return decided(decision_inputs(governed_seed(env, W0 + 15 * DAY), evidence_for(env, (15, 45))))


@functools.lru_cache(maxsize=None)
def drawdown_link(index: int) -> Decided:
    env = ladder_envelope(*DRAWDOWN_LADDER)
    state = governed_seed(env, W0 + 5 * DAY) if index == 0 else drawdown_link(0).prior()
    window = ((5, 35), (15, 45))[index]
    return decided(decision_inputs(state, evidence_for(env, window), decision_id=f"rg6-drawdown-{index}"))


def world_sharpe() -> str:
    return rg4t.sleeve_world(ALPHA).evidence.paper_sharpe_annualized


def chain_sharpe(window: tuple[int, int]) -> str:
    return evidence_for(ladder_envelope(*CHAIN_LADDER), window).target.evidence.paper_sharpe_annualized


@functools.lru_cache(maxsize=None)
def promotion_floor_genesis(floor: str) -> Decided:
    env = ladder_envelope((("promotion_sharpe", floor),))
    return decided(decision_inputs(governed_seed(env), evidence_for(env)))


@functools.lru_cache(maxsize=None)
def demotion_floor_link(floor: str, index: int) -> Decided:
    env = ladder_envelope(
        (
            ("promotion_sharpe", "1.2"),
            ("promotion_drawdown", "0.05"),
            ("demotion_sharpe", floor),
            ("demotion_drawdown", "0.1"),
        )
    )
    state = governed_seed(env, W0 + 5 * DAY) if index == 0 else demotion_floor_link(floor, 0).prior()
    window = ((5, 35), (10, 40))[index]
    return decided(decision_inputs(state, evidence_for(env, window), decision_id=f"rg6-floor-{index}"))


@functools.lru_cache(maxsize=None)
def ungoverned_genesis() -> Decided:
    return decided(decision_inputs(build_seed(), world_evidence()))


@functools.lru_cache(maxsize=None)
def blocked_genesis() -> Decided:
    return decided(decision_inputs(governed_seed(), with_beta(blocked_target(funding_evidence=None))))


@functools.lru_cache(maxsize=None)
def beta_genesis() -> Decided:
    evidence = Evidence(
        rg4t.sleeve_world(BETA),
        rg4t.drawdown_inputs(),
        rg4t.world_drawdown(),
        rg5t.correlation_inputs(),
        rg5t.world_correlation(),
    )
    return decided(decision_inputs(governed_seed(sleeve_id=BETA), evidence))


def later_world_evidence() -> Evidence:
    """Alpha alone over ``[W0 + 5 days, W0 + 35 days)`` on the RG-2 fixture."""

    return evidence_for(rg3t.world_envelope(), (5, 35))


# --- the fixtures are genuine ---------------------------------------------------------------------------------------


def test_the_shared_world_is_genuine_ready_evidence() -> None:
    evidence = world_evidence()
    assert evidence.target.evidence.status is PaperSleevePerformanceStatus.READY
    assert evidence.target.evidence.window_end_ns == END
    assert evidence.drawdown.status is PaperSleeveDrawdownStatus.READY
    assert evidence.correlation.status is PaperSleeveCorrelationStatus.READY
    assert evidence.correlation.all_pairs_observed is True
    assert rg5t.envelope() == rg3t.world_envelope()


# --- B. the governed genesis seed -----------------------------------------------------------------------------------


def test_a_human_governed_seed_advances_at_probation() -> None:
    seed = governed_seed()
    env = rg3t.world_envelope()
    assert (seed.gate_verdict, seed.advances, seed.verdict_reason_codes) == (EdgeGateVerdict.PASS, True, ())
    assert (seed.initial_tier, seed.tier_entered_at_ns, seed.sleeve_id) == (PROBATION, W0, ALPHA)
    assert (seed.envelope_id, seed.envelope_version, seed.envelope_digest) == (
        env.envelope_id,
        env.envelope_version,
        env.envelope_digest,
    )
    assert (seed.rule_set_id, seed.rule_set_digest) == (
        "paper_sleeve_promotion_demotion_decision_rules.v1",
        PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
    )
    assert seed.synthetic_test_approval_used is False
    assert seed.approval == seed_approval(build_seed())
    assert seed.ladder_seed_digest == paper_sleeve_ladder_seed_digest(seed)
    assert {name: getattr(seed, name) for name, _ in PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS} == dict(
        PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS
    )
    _assert_seed_intact(seed)


def test_the_seed_policy_digest_commits_the_state_fact_and_excludes_only_governance() -> None:
    draft = build_seed()
    governed = governed_seed()
    assert draft.seed_policy_digest == governed.seed_policy_digest
    assert draft.ladder_seed_digest != governed.ladder_seed_digest
    for overrides in (
        {"tier_entered_at_ns": W0 + DAY},
        {"sleeve_id": BETA},
        {"seed_id": "rg6-synthetic-seed-2"},
        {"seed_version": "synthetic-v2"},
        {"portfolio_risk_envelope": ladder_envelope()},
    ):
        assert build_seed(**overrides).seed_policy_digest != draft.seed_policy_digest


@pytest.mark.parametrize(
    ("make_approval", "expected"),
    [
        (lambda draft: None, ("seed_governance_approval_missing",)),
        (lambda draft: seed_approval(draft, kind=SYNTHETIC), ("seed_governance_approval_test_only_synthetic",)),
        (
            lambda draft: seed_approval(build_seed(tier_entered_at_ns=W0 + DAY)),
            ("seed_governance_approval_seed_policy_digest_mismatch",),
        ),
        (
            lambda draft: seed_approval(draft, approved_rule_set_digest="b" * 64),
            ("seed_governance_approval_rule_set_digest_mismatch",),
        ),
        (
            lambda draft: seed_approval(draft, approved_seed_id="rg6-other-seed"),
            ("seed_governance_approval_seed_id_mismatch",),
        ),
        (
            lambda draft: seed_approval(draft, approved_seed_version="synthetic-v2"),
            ("seed_governance_approval_seed_version_mismatch",),
        ),
        (
            lambda draft: seed_approval(
                draft, kind=SYNTHETIC, approved_seed_policy_digest="c" * 64, approved_rule_set_digest="b" * 64
            ),
            (
                "seed_governance_approval_rule_set_digest_mismatch",
                "seed_governance_approval_seed_policy_digest_mismatch",
                "seed_governance_approval_test_only_synthetic",
            ),
        ),
    ],
)
def test_a_seed_advances_only_under_an_exact_human_approval(make_approval, expected: tuple[str, ...]) -> None:
    seed = build_seed(approval=make_approval(build_seed()))
    assert (seed.gate_verdict, seed.advances) == (EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL, False)
    assert seed.verdict_reason_codes == codes(*expected)
    assert seed.synthetic_test_approval_used is ("seed_governance_approval_test_only_synthetic" in expected)
    assert seed.initial_tier is PROBATION
    _assert_seed_intact(seed)


def test_an_ungoverned_seed_needs_governance_approval_and_decides_nothing() -> None:
    built = ungoverned_genesis()
    decision = built.decision
    assert (decision.status, decision.ready, decision.advances) == (NEEDS_GOVERNANCE, False, False)
    assert decision.reason_codes == codes("ladder_seed_not_governed")
    assert (decision.ladder_seed_digest, decision.ladder_seed_advances) == (build_seed().ladder_seed_digest, False)
    assert (decision.current_tier, decision.current_tier_entered_at_ns, decision.tier_elapsed_days) == (
        PROBATION,
        W0,
        30,
    )
    assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (None, None, None)
    assert (decision.paper_sharpe_annualized, decision.max_peak_distance) == ("", "")
    assert (decision.promotion_boundary, decision.demotion_boundary, decision.decision_reason_codes) == (None, None, ())
    _assert_intact(built)


def test_the_initial_tier_is_never_a_caller_choice() -> None:
    assert "initial_tier" not in inspect.signature(build_paper_sleeve_ladder_seed).parameters
    with pytest.raises(TypeError):
        build_paper_sleeve_ladder_seed(**seed_args(), initial_tier=STANDARD)  # type: ignore[call-arg]
    seed = governed_seed()
    for forged in (replace(seed, initial_tier=STANDARD), _reseal_seed(seed, initial_tier=EXPANDED)):
        verification = verify_paper_sleeve_ladder_seed(forged)
        assert verification.intact is False
        assert _code("field_mismatch:initial_tier") in verification.reason_codes
        with _raises("ladder_seed_not_intact"):
            decide(decision_inputs(forged, world_evidence()))


def test_a_resealed_seed_cannot_forge_its_governance() -> None:
    draft = build_seed()
    forged = _reseal_seed(draft, gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    verification = verify_paper_sleeve_ladder_seed(forged)
    assert verification.reason_codes == codes(
        "field_mismatch:advances",
        "field_mismatch:gate_verdict",
        "field_mismatch:ladder_seed_digest",
        "field_mismatch:verdict_reason_codes",
    )
    tampered = replace(governed_seed(), ladder_seed_digest="0" * 64)
    assert verify_paper_sleeve_ladder_seed(tampered).reason_codes == codes(
        "field_mismatch:ladder_seed_digest", "self_digest_mismatch"
    )
    for state in (forged, tampered):
        with _raises("ladder_seed_not_intact"):
            decide(decision_inputs(state, world_evidence()))


def test_the_seed_binds_an_intact_envelope_and_a_declared_sleeve() -> None:
    env = rg3t.world_envelope()
    with _raises("portfolio_risk_envelope_not_intact"):
        build_seed(portfolio_risk_envelope=replace(env, envelope_digest="0" * 64))
    with _raises("portfolio_risk_envelope_malformed"):
        build_seed(portfolio_risk_envelope=rg2.to_dict(env))
    with _raises("seed_sleeve_not_declared_by_envelope"):
        build_seed(sleeve_id="sleeve-gamma")
    with _raises("seed_sleeve_not_declared_by_envelope"):
        build_seed(sleeve_id=BETA, portfolio_risk_envelope=ladder_envelope())


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (_Text(ALPHA), "seed_sleeve_id_invalid"),
        ("", "seed_sleeve_id_invalid"),
        (" sleeve-alpha", "seed_sleeve_id_invalid"),
        ("sleeve alpha", "seed_sleeve_id_invalid"),
        (7, "seed_sleeve_id_invalid"),
        ("live", "forbidden_scope_token:seed_sleeve_id"),
    ],
)
def test_the_seed_sleeve_is_an_exact_identifier(value: object, code: str) -> None:
    with _raises(code):
        build_seed(sleeve_id=value)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        (True, "tier_entered_at_ns_invalid"),
        (-DAY, "tier_entered_at_ns_invalid"),
        (INT64_MAX + 1, "tier_entered_at_ns_invalid"),
        (float(W0), "tier_entered_at_ns_invalid"),
        (str(W0), "tier_entered_at_ns_invalid"),
        (None, "tier_entered_at_ns_invalid"),
        (W0 + 1, "tier_entered_at_ns_not_utc_day_aligned"),
        (W0 + DAY // 2, "tier_entered_at_ns_not_utc_day_aligned"),
    ],
)
def test_the_tier_entry_is_an_exact_utc_day_coordinate(value: object, code: str) -> None:
    with _raises(code):
        build_seed(tier_entered_at_ns=value)


def test_the_epoch_is_a_valid_tier_entry() -> None:
    assert build_seed(tier_entered_at_ns=0).tier_entered_at_ns == 0


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"seed_id": _Text("rg6-seed")}, "seed_id_invalid"),
        ({"seed_id": ""}, "seed_id_invalid"),
        ({"seed_id": "rg6\nseed"}, "seed_id_invalid"),
        ({"seed_version": " synthetic-v1"}, "seed_version_invalid"),
        ({"seed_version": 1}, "seed_version_invalid"),
        ({"seed_id": "live-seed"}, "forbidden_scope_token:seed_id"),
        ({"seed_id": "bist-seed"}, "bist_scope_leakage:seed_id"),
    ],
)
def test_seed_texts_are_exact(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        build_seed(**overrides)


@pytest.mark.parametrize(
    ("approval", "code"),
    [
        ({"approval_kind": "HUMAN_GOVERNANCE"}, "seed_governance_approval_malformed"),
        (lambda draft: seed_approval(draft, kind="ROOT"), "seed_governance_approval_kind_invalid"),
        (lambda draft: seed_approval(draft, approval_digest="A" * 64), "seed_governance_approval_digest_invalid"),
        (
            lambda draft: seed_approval(draft, approved_seed_policy_digest="0" * 63),
            "seed_governance_approved_seed_policy_digest_invalid",
        ),
        (
            lambda draft: seed_approval(draft, approval_reference="approved-by-live-desk"),
            "forbidden_scope_token:seed_governance_approval_reference",
        ),
    ],
)
def test_the_seed_approval_is_an_exact_record(approval: object, code: str) -> None:
    value = approval(build_seed()) if callable(approval) else approval
    with _raises(code):
        build_seed(approval=value)


def test_an_exact_kind_text_is_normalized_to_its_member() -> None:
    draft = build_seed()
    seed = build_seed(approval=seed_approval(draft, kind="HUMAN_GOVERNANCE"))
    assert seed.approval is not None and seed.approval.approval_kind is HUMAN
    assert seed == governed_seed()


def test_the_seed_verifier_is_total() -> None:
    seed = governed_seed()
    for value in (None, {}, "seed", paper_sleeve_ladder_seed_to_dict(seed), world_genesis().decision):
        assert verify_paper_sleeve_ladder_seed(value).reason_codes == codes("evidence_type_invalid")
    cases = {
        "evidence_serialization_failed": (
            replace(seed, initial_tier="PROBATION"),
            replace(seed, tier_entered_at_ns=-1),
            replace(seed, verdict_reason_codes=["x"]),
        ),
        "evidence_parse_failed": (replace(seed, advances=1), replace(seed, seed_id=7)),
        "evidence_reassembly_failed": (replace(seed, seed_id=""), replace(seed, tier_entered_at_ns=W0 + 1)),
    }
    for stage, forged in cases.items():
        for value in forged:
            verification = verify_paper_sleeve_ladder_seed(value)
            assert (verification.intact, verification.reason_codes) == (False, codes(stage))
            assert (verification.recomputed_digest, verification.canonical_json) == ("", "")


def test_the_seed_payload_parses_strictly() -> None:
    seed = governed_seed()
    payload = paper_sleeve_ladder_seed_to_dict(seed)
    assert paper_sleeve_ladder_seed_from_payload(json.loads(json.dumps(payload))) == seed
    payload["approval"]["approval_kind"] = "ROOT"  # type: ignore[index]
    malformed: list[object] = [
        {**paper_sleeve_ladder_seed_to_dict(seed), "extra": 1},
        {name: value for name, value in paper_sleeve_ladder_seed_to_dict(seed).items() if name != "advances"},
        {**paper_sleeve_ladder_seed_to_dict(seed), "tier_entered_at_ns": True},
        {**paper_sleeve_ladder_seed_to_dict(seed), "initial_tier": "TOP"},
        {**paper_sleeve_ladder_seed_to_dict(seed), "verdict_reason_codes": "x"},
        payload,
        [],
    ]
    for value in malformed:
        with pytest.raises(PaperSleeveLadderError):
            paper_sleeve_ladder_seed_from_payload(value)


# --- genesis decisions ----------------------------------------------------------------------------------------------


def test_a_genesis_at_exactly_the_minimum_tenure_promotes_once() -> None:
    built = world_genesis()
    decision = built.decision
    evidence = world_evidence()
    env = rg3t.world_envelope()
    lower, _ = env.ladder_boundaries
    record = _record(evidence)
    assert (decision.status, decision.ready, decision.advances) == (READY, True, True)
    assert (decision.decision_id, decision.correlation_id) == ("rg6-decision-1", "corr-rg6")
    assert (decision.envelope_id, decision.envelope_version, decision.envelope_digest) == (
        env.envelope_id,
        env.envelope_version,
        env.envelope_digest,
    )
    assert (decision.envelope_policy_digest, decision.envelope_advances) == (env.policy_digest, True)
    assert (decision.sleeve_id, decision.market_symbol) == (ALPHA, evidence.target.evidence.market_symbol)
    assert (decision.ladder_seed_digest, decision.ladder_seed_advances) == (governed_seed().ladder_seed_digest, True)
    assert (decision.prior_decision_digest, decision.lineage_sequence, decision.evaluation_end_ns) == ("", 0, END)
    assert (decision.current_tier, decision.current_tier_entered_at_ns, decision.tier_elapsed_days) == (
        PROBATION,
        W0,
        30,
    )
    assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (
        PROMOTE,
        STANDARD,
        END,
    )
    assert (decision.performance_evidence_digest, decision.performance_status) == (
        evidence.target.evidence.performance_evidence_digest,
        "READY",
    )
    assert (decision.drawdown_evidence_digest, decision.drawdown_status) == (
        evidence.drawdown.drawdown_evidence_digest,
        "READY",
    )
    assert (decision.correlation_evidence_digest, decision.correlation_status) == (
        evidence.correlation.correlation_evidence_digest,
        "READY",
    )
    assert decision.paper_sharpe_annualized == evidence.target.evidence.paper_sharpe_annualized
    assert decision.max_peak_distance == record.measurement.max_peak_distance
    assert decision.drawdown_consumption == "MAX_PEAK_DISTANCE"
    assert (decision.promotion_boundary, decision.demotion_boundary) == (lower, None)
    assert decision.decision_reason_codes == codes(
        "no_demotion_below_probation",
        "promotion_max_drawdown_ceiling_met",
        "promotion_sharpe_floor_met",
        "promotion_tenure_met",
    )
    assert decision.reason_codes == ()
    assert decision.regime_concentration_demotion_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert (decision.rule_set_id, decision.rule_set_digest) == (
        "paper_sleeve_promotion_demotion_decision_rules.v1",
        PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
    )
    assert decision.decision_digest == paper_sleeve_promotion_demotion_decision_digest(decision)
    _assert_intact(built)


def test_a_genesis_one_day_short_of_the_tenure_holds_and_keeps_its_entry() -> None:
    built = world_genesis(W0 + DAY)
    decision = built.decision
    assert (decision.status, decision.current_tier, decision.tier_elapsed_days) == (READY, PROBATION, 29)
    assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (
        HOLD,
        PROBATION,
        W0 + DAY,
    )
    assert decision.decision_reason_codes == codes(
        "no_demotion_below_probation",
        "promotion_max_drawdown_ceiling_met",
        "promotion_sharpe_floor_met",
        "promotion_tenure_insufficient",
    )
    assert decision.paper_sharpe_annualized == world_genesis().decision.paper_sharpe_annualized
    _assert_intact(built)


def test_a_tier_entered_at_the_evaluation_end_has_zero_tenure() -> None:
    decision = world_genesis(END).decision
    assert (decision.tier_elapsed_days, decision.transition, decision.resulting_tier_entered_at_ns) == (0, HOLD, END)
    with _raises("evaluation_end_precedes_the_tier_entry"):
        decide(decision_inputs(governed_seed(entered=END + DAY), world_evidence()))


def test_promotion_crosses_one_boundary_however_far_the_snapshot_clears_the_ladder() -> None:
    built = world_genesis(W0 - 100 * DAY)
    decision = built.decision
    lower, upper = rg3t.world_envelope().ladder_boundaries
    sharpe, drawdown = Fraction(decision.paper_sharpe_annualized), Fraction(decision.max_peak_distance)
    # The snapshot also clears every upper-boundary promotion threshold, which PROBATION never consults.
    assert decision.tier_elapsed_days == 130 >= upper.min_probation_days
    assert sharpe >= Fraction(upper.promotion_min_paper_sharpe)
    assert drawdown <= Fraction(upper.promotion_max_drawdown_fraction)
    assert (decision.transition, decision.resulting_tier) == (PROMOTE, STANDARD)
    assert (decision.promotion_boundary, decision.demotion_boundary) == (lower, None)
    _assert_intact(built)


# --- C. the prior-chain lineage and L. tier entry -------------------------------------------------------------------


def test_the_lineage_promotes_promotes_holds_demotes_and_holds() -> None:
    lower, upper = ladder_envelope(*CHAIN_LADDER).ladder_boundaries
    held = ("demotion_max_drawdown_ceiling_held", "demotion_sharpe_floor_held")
    expected = (
        (
            PROBATION,
            0,
            25,
            PROMOTE,
            STANDARD,
            25,
            (lower, None),
            ("promotion_tenure_met", "promotion_sharpe_floor_met"),
        ),
        (STANDARD, 25, 5, PROMOTE, EXPANDED, 30, (upper, lower), (*held, "promotion_sharpe_floor_met")),
        (EXPANDED, 30, 5, HOLD, EXPANDED, 30, (None, upper), held),
        (
            EXPANDED,
            30,
            10,
            DEMOTE,
            STANDARD,
            40,
            (None, upper),
            ("demotion_max_drawdown_ceiling_held", "demotion_sharpe_strictly_below_floor"),
        ),
        (STANDARD, 40, 5, HOLD, STANDARD, 40, (upper, lower), (*held, "promotion_sharpe_below_floor")),
    )
    tier_reasons = {
        PROBATION: ("no_demotion_below_probation", "promotion_max_drawdown_ceiling_met"),
        STANDARD: ("demotion_evaluated_before_promotion", "promotion_tenure_met", "promotion_max_drawdown_ceiling_met"),
        EXPANDED: ("no_promotion_above_expanded",),
    }
    seed = governed_seed(ladder_envelope(*CHAIN_LADDER))
    for index, (current, entered, tenure, transition, resulting, resulting_entered, bounds, reasons) in enumerate(
        expected
    ):
        decision = chain_link(index).decision
        assert decision.status is READY
        assert (decision.evaluation_end_ns, decision.lineage_sequence) == (W0 + CHAIN_WINDOWS[index][1] * DAY, index)
        assert decision.ladder_seed_digest == seed.ladder_seed_digest
        prior = "" if index == 0 else chain_link(index - 1).decision.decision_digest
        assert decision.prior_decision_digest == prior
        assert (decision.current_tier, decision.current_tier_entered_at_ns, decision.tier_elapsed_days) == (
            current,
            W0 + entered * DAY,
            tenure,
        )
        assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (
            transition,
            resulting,
            W0 + resulting_entered * DAY,
        )
        assert (decision.promotion_boundary, decision.demotion_boundary) == bounds
        assert decision.decision_reason_codes == codes(*reasons, *tier_reasons[current])
        assert decision.current_ladder_head_proven is False
    _assert_intact(chain_link(4))


def test_every_later_state_is_the_prior_resulting_state() -> None:
    for index in range(1, len(CHAIN_WINDOWS)):
        prior, decision = chain_link(index - 1).decision, chain_link(index).decision
        assert decision.current_tier is prior.resulting_tier
        assert decision.current_tier_entered_at_ns == prior.resulting_tier_entered_at_ns
        assert decision.evaluation_end_ns > prior.evaluation_end_ns
    # HOLD at link 2 carries the link 1 entry forward, so link 3 counts its tenure from there.
    assert chain_link(3).decision.tier_elapsed_days == 10


def test_a_holding_genesis_carries_its_seed_entry_into_the_next_decision() -> None:
    genesis, after = holding_link(0).decision, holding_link(1).decision
    assert (genesis.tier_elapsed_days, genesis.transition, genesis.resulting_tier_entered_at_ns) == (24, HOLD, W0 + DAY)
    assert (after.current_tier, after.current_tier_entered_at_ns, after.tier_elapsed_days) == (PROBATION, W0 + DAY, 29)
    assert (after.transition, after.resulting_tier, after.resulting_tier_entered_at_ns) == (
        PROMOTE,
        STANDARD,
        W0 + 30 * DAY,
    )
    _assert_intact(holding_link(1))


def test_the_caller_never_supplies_a_current_tier_or_tier_entry() -> None:
    assert [item.name for item in fields(PaperSleevePromotionDemotionInputs)] == [
        "decision_id",
        "correlation_id",
        "portfolio_risk_envelope",
        "ladder_state",
        "evaluation_end_ns",
        "performance_inputs",
        "performance_evidence",
        "drawdown_inputs",
        "drawdown_evidence",
        "correlation_inputs",
        "correlation_evidence",
    ]
    assert [item.name for item in fields(PaperSleeveLadderPriorDecision)] == ["decision_inputs", "decision"]
    with pytest.raises(TypeError):
        decision_inputs(governed_seed(), world_evidence(), current_tier=STANDARD)


@pytest.mark.parametrize(
    "forge",
    [
        lambda link: PaperSleeveLadderPriorDecision(link.inputs, replace(link.decision, decision_digest="0" * 64)),
        lambda link: PaperSleeveLadderPriorDecision(link.inputs, _reseal(link.decision, resulting_tier=STANDARD)),
        lambda link: PaperSleeveLadderPriorDecision(
            link.inputs, _reseal(link.decision, resulting_tier_entered_at_ns=W0)
        ),
        lambda link: PaperSleeveLadderPriorDecision(link.inputs, replace(link.decision, resulting_tier=PROBATION)),
        lambda link: PaperSleeveLadderPriorDecision(chain_link(0).inputs, link.decision),
    ],
    ids=["digest_tamper", "resealed_tier", "resealed_entry", "forged_tier", "swapped_inputs"],
)
def test_only_a_reproven_prior_carries_the_ladder_state(forge) -> None:
    inputs = decision_inputs(forge(chain_link(1)), evidence_for(ladder_envelope(*CHAIN_LADDER), CHAIN_WINDOWS[2]))
    with _raises("prior_decision_not_reproven"):
        decide(inputs)


@pytest.mark.parametrize(
    ("state", "code"),
    [
        (None, "ladder_state_malformed"),
        (lambda: world_genesis().decision, "ladder_state_malformed"),
        (lambda: PaperSleeveLadderPriorDecision(None, world_genesis().decision), "prior_decision_inputs_malformed"),
        (lambda: PaperSleeveLadderPriorDecision(world_genesis().inputs, None), "prior_decision_malformed"),
    ],
)
def test_the_ladder_state_is_an_exact_seed_or_prior(state: object, code: str) -> None:
    value = state() if callable(state) else state
    with _raises(code):
        decide(decision_inputs(value, later_world_evidence()))


def test_a_prior_must_bind_the_same_envelope() -> None:
    inputs = decision_inputs(chain_link(0).prior(), evidence_for(ladder_envelope(*DRAWDOWN_LADDER), (5, 35)))
    with _raises("prior_decision_envelope_mismatch"):
        decide(inputs)


def test_a_prior_must_bind_the_same_sleeve() -> None:
    assert beta_genesis().decision.sleeve_id == BETA
    with _raises("performance_sleeve_not_the_lineage_sleeve"):
        decide(decision_inputs(beta_genesis().prior(), later_world_evidence()))


@pytest.mark.parametrize("days", [25, 24])
def test_the_evaluation_end_strictly_advances_past_the_prior(days: int) -> None:
    inputs = replace(chain_link(1).inputs, evaluation_end_ns=W0 + days * DAY)
    with _raises("evaluation_end_not_after_the_prior_decision"):
        decide(inputs)


@pytest.mark.parametrize(
    ("make_prior", "status"),
    [(ungoverned_genesis, NEEDS_GOVERNANCE), (blocked_genesis, NOT_COMPUTABLE)],
    ids=["needs_governance_prior", "not_computable_prior"],
)
def test_a_non_advancing_prior_propagates_its_status(make_prior, status: PaperSleeveLadderDecisionStatus) -> None:
    prior = make_prior()
    assert (prior.decision.status, prior.decision.advances) == (status, False)
    built = decided(decision_inputs(prior.prior(), later_world_evidence()))
    decision = built.decision
    assert (decision.status, decision.advances) == (status, False)
    assert decision.reason_codes == codes("prior_decision_not_advancing")
    assert (decision.prior_decision_digest, decision.lineage_sequence) == (prior.decision.decision_digest, 1)
    assert decision.ladder_seed_advances is prior.decision.ladder_seed_advances
    assert (decision.current_tier, decision.current_tier_entered_at_ns, decision.tier_elapsed_days) == (
        None,
        None,
        None,
    )
    assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (None, None, None)
    assert (decision.paper_sharpe_annualized, decision.max_peak_distance, decision.decision_reason_codes) == (
        "",
        "",
        (),
    )
    _assert_intact(built)


def test_an_older_prior_is_another_history_never_a_current_head() -> None:
    env = ladder_envelope(*CHAIN_LADDER)
    fork = decided(decision_inputs(chain_link(0).prior(), evidence_for(env, CHAIN_WINDOWS[2]), decision_id="rg6-fork"))
    main = chain_link(2).decision
    assert fork.decision.evaluation_end_ns == main.evaluation_end_ns
    assert (fork.decision.current_tier, fork.decision.tier_elapsed_days, fork.decision.transition) == (
        STANDARD,
        10,
        HOLD,
    )
    assert (main.current_tier, main.transition) == (EXPANDED, HOLD)
    # Two authentic decisions at one coordinate: neither proves itself the current ladder state.
    assert fork.decision.current_ladder_head_proven is False and main.current_ladder_head_proven is False
    _assert_intact(fork)


# --- D. the RG-2 envelope -------------------------------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def ungoverned_envelope_genesis(kind: str) -> Decided:
    base = {"sleeve_caps": [rg2.sleeve(ALPHA, "400")]}
    approval = None if kind == "missing" else rg2.approval_for(rg2.build(**base), kind=rg2.SYNTHETIC)
    env = rg2.build(approval=approval, **base)
    assert env.advances is False
    return decided(decision_inputs(governed_seed(env), evidence_for(env)))


@pytest.mark.parametrize("kind", ["missing", "synthetic"])
def test_an_ungoverned_envelope_needs_governance_approval(kind: str) -> None:
    built = ungoverned_envelope_genesis(kind)
    decision = built.decision
    assert (decision.status, decision.envelope_advances, decision.transition) == (NEEDS_GOVERNANCE, False, None)
    assert decision.reason_codes == codes(
        "correlation_evidence_needs_governance_approval",
        "drawdown_evidence_needs_governance_approval",
        "performance_evidence_needs_governance_approval",
        "portfolio_risk_envelope_not_governed",
    )
    _assert_intact(built)


def test_the_envelope_is_an_intact_exact_record() -> None:
    env = rg3t.world_envelope()
    with _raises("portfolio_risk_envelope_not_intact"):
        decide(
            decision_inputs(governed_seed(), world_evidence(), portfolio_risk_envelope=replace(env, max_sleeve_count=9))
        )
    with _raises("portfolio_risk_envelope_malformed"):
        decide(decision_inputs(governed_seed(), world_evidence(), portfolio_risk_envelope=None))


def test_an_unsupported_envelope_rule_set_or_regime_status_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = decision_inputs(governed_seed(), world_evidence())
    with monkeypatch.context() as patch:
        patch.setattr(decision_module, "PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST", "0" * 64)
        with _raises("portfolio_risk_envelope_rule_set_unsupported"):
            decide(inputs)
    with monkeypatch.context() as patch:
        patch.setattr(decision_module, "EDGE_REGIME_LABEL_BINDING_PENDING", "RF_LABEL_ENUM_BOUND")
        with _raises("regime_concentration_demotion_status_unsupported"):
            decide(inputs)


@pytest.mark.parametrize(
    ("ladder", "code"),
    [
        # Within one boundary: the promotion floor below its demotion floor, or its ceiling above its demotion ceiling.
        (lambda: (rg2.lower_boundary(promotion_sharpe="0", demotion_sharpe="1"), rg2.upper_boundary()), "consistency"),
        (lambda: (rg2.lower_boundary(promotion_drawdown="0.3"), rg2.upper_boundary()), "consistency"),
        (
            lambda: (rg2.lower_boundary(), rg2.upper_boundary(promotion_drawdown="0.2", demotion_drawdown="0.1")),
            "consistency",
        ),
        # Across the middle tier: upper promotion looser than lower demotion.
        (lambda: (rg2.lower_boundary(promotion_sharpe="2", demotion_sharpe="2"), rg2.upper_boundary()), "consistency"),
        (
            lambda: (rg2.lower_boundary(promotion_drawdown="0.05", demotion_drawdown="0.05"), rg2.upper_boundary()),
            "consistency",
        ),
        (lambda: (rg2.upper_boundary(), rg2.lower_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(), rg2.upper_boundary(), rg2.upper_boundary()), "shape"),
        (lambda: [rg2.lower_boundary(), rg2.upper_boundary()], "shape"),
        (lambda: (rg2.lower_boundary(probation=0), rg2.upper_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(probation=True), rg2.upper_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(), rg2.to_dict(rg3t.world_envelope())), "shape"),
        (
            lambda: (replace(rg2.lower_boundary(), promotion_min_paper_sharpe="1"), rg2.upper_boundary()),
            "threshold",
        ),
    ],
)
def test_a_ladder_contradicting_the_rg2_invariant_fails_closed(
    monkeypatch: pytest.MonkeyPatch, ladder, code: str
) -> None:
    expected = {
        "consistency": "ladder_consistency_invariant_violated",
        "shape": "ladder_boundaries_not_the_accepted_ladder",
        "threshold": "ladder_threshold_invalid",
    }[code]
    with _raises(expected):
        decision_module._require_consistent_ladder(ladder())
    # The builder re-pins the ladder of a (forged) envelope its verifier accepted before any evidence is read.
    monkeypatch.setattr(
        decision_module,
        "verify_paper_portfolio_risk_envelope",
        lambda envelope: EdgeEvidenceVerification(True, (), "", ""),
    )
    forged = replace(rg3t.world_envelope(), ladder_boundaries=ladder())
    with _raises(expected):
        decide(decision_inputs(governed_seed(), world_evidence(), portfolio_risk_envelope=forged))


def test_the_accepted_ladders_are_consistent() -> None:
    for env in (rg3t.world_envelope(), ladder_envelope(*CHAIN_LADDER), ladder_envelope(*DRAWDOWN_LADDER)):
        assert decision_module._require_consistent_ladder(env.ladder_boundaries) == env.ladder_boundaries


# --- E. RG-3 --------------------------------------------------------------------------------------------------------


def test_an_uncomputable_target_is_not_computable() -> None:
    built = blocked_genesis()
    decision = built.decision
    assert (decision.status, decision.advances) == (NOT_COMPUTABLE, False)
    assert decision.reason_codes == codes("performance_evidence_not_computable")
    assert (decision.performance_status, decision.drawdown_status) == ("NOT_COMPUTABLE", "NOT_COMPUTABLE")
    assert (decision.current_tier, decision.tier_elapsed_days, decision.transition) == (PROBATION, 30, None)
    assert (decision.paper_sharpe_annualized, decision.max_peak_distance) == ("", "")
    _assert_intact(built)


def test_an_ungoverned_target_needs_governance_approval() -> None:
    target = blocked_target(equity_basis_policy=world.basis_policy(governed=False))
    assert target.evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    built = decided(decision_inputs(governed_seed(), with_beta(target)))
    assert built.decision.status is NEEDS_GOVERNANCE
    assert built.decision.reason_codes == codes(
        "correlation_evidence_needs_governance_approval",
        "drawdown_evidence_needs_governance_approval",
        "performance_evidence_needs_governance_approval",
    )
    _assert_intact(built)


def _reseal_rg3(evidence, **changes):
    changed = replace(evidence, **changes)
    return replace(changed, performance_evidence_digest=paper_sleeve_performance_evidence_digest(changed))


@pytest.mark.parametrize(
    "forge",
    [
        lambda evidence: replace(evidence, paper_sharpe_annualized="9.000000000000000000"),
        lambda evidence: _reseal_rg3(evidence, paper_sharpe_annualized="9.000000000000000000"),
        lambda evidence: rg4t.sleeve_world(BETA).evidence,
    ],
    ids=["sharpe_tamper", "resealed_sharpe", "another_sleeve_evidence"],
)
def test_rg3_evidence_that_is_not_the_reconstruction_is_refused(forge) -> None:
    evidence = world_evidence()
    inputs = decision_inputs(governed_seed(), evidence, performance_evidence=forge(evidence.target.evidence))
    with _raises("performance_evidence_not_reconstructed"):
        decide(inputs)


def test_rg3_over_another_envelope_is_refused() -> None:
    foreign = evidence_for(ladder_envelope(*CHAIN_LADDER), (0, 30)).target
    inputs = decision_inputs(
        governed_seed(), world_evidence(), performance_inputs=foreign.inputs, performance_evidence=foreign.evidence
    )
    with _raises("performance_evidence_envelope_mismatch"):
        decide(inputs)


def test_rg3_of_another_sleeve_is_refused() -> None:
    beta = rg4t.sleeve_world(BETA)
    inputs = decision_inputs(
        governed_seed(), world_evidence(), performance_inputs=beta.inputs, performance_evidence=beta.evidence
    )
    with _raises("performance_sleeve_not_the_lineage_sleeve"):
        decide(inputs)


@pytest.mark.parametrize("end", [END + DAY, END - DAY])
def test_rg3_must_end_exactly_at_the_evaluation_end(end: int) -> None:
    with _raises("performance_evidence_not_at_the_evaluation_end"):
        decide(decision_inputs(governed_seed(), world_evidence(), evaluation_end_ns=end))


@pytest.mark.parametrize(
    "name",
    [
        "performance_inputs",
        "performance_evidence",
        "drawdown_inputs",
        "drawdown_evidence",
        "correlation_inputs",
        "correlation_evidence",
    ],
)
def test_every_evidence_input_is_an_exact_record(name: str) -> None:
    with _raises(f"{name}_malformed"):
        decide(decision_inputs(governed_seed(), world_evidence(), **{name: None}))


def test_inputs_are_an_exact_record() -> None:
    with _raises("inputs_malformed"):
        decide(None)
    with _raises("inputs_malformed"):
        decide({"decision_id": "rg6-decision-1", "ladder_state": governed_seed()})


@pytest.mark.parametrize(
    ("name", "builder_inputs"),
    [
        (
            "performance",
            lambda evidence: {"performance_inputs": replace(evidence.target.inputs, performance_evidence_id="")},
        ),
        ("drawdown", lambda evidence: {"drawdown_inputs": replace(evidence.drawdown_inputs, drawdown_evidence_id="")}),
        (
            "correlation",
            lambda evidence: {"correlation_inputs": replace(evidence.correlation_inputs, correlation_evidence_id="")},
        ),
    ],
)
def test_an_evidence_the_accepted_builder_refuses_fails_closed(name: str, builder_inputs) -> None:
    evidence = world_evidence()
    with _raises(f"{name}_reconstruction_failed"):
        decide(decision_inputs(governed_seed(), evidence, **builder_inputs(evidence)))


# --- F. RG-4 and M. the drawdown consumption ------------------------------------------------------------------------


def test_the_rg4_target_must_be_present() -> None:
    drawdown_inputs = rg4t.drawdown_inputs(sleeves=(rg4t.sleeve_world(BETA).drawdown_inputs(),))
    drawdown = rg4t.build(drawdown_inputs)
    assert ALPHA in drawdown.missing_sleeve_ids
    inputs = decision_inputs(
        governed_seed(), world_evidence(), drawdown_inputs=drawdown_inputs, drawdown_evidence=drawdown
    )
    with _raises("drawdown_evidence_missing_the_target_sleeve"):
        decide(inputs)


def test_an_unmeasured_target_is_not_computable(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, seed = world_evidence(), governed_seed()  # cached authentic fixtures, built before the patch
    monkeypatch.setattr(drawdown_module, "_measure", lambda values: None)
    drawdown = build_paper_sleeve_drawdown_evidence(evidence.drawdown_inputs)
    assert _record(replace(evidence, drawdown=drawdown)).computed is False
    built = decided(decision_inputs(seed, evidence, drawdown_evidence=drawdown))
    decision = built.decision
    assert (decision.status, decision.performance_status, decision.drawdown_status) == (
        NOT_COMPUTABLE,
        "READY",
        "NOT_COMPUTABLE",
    )
    assert decision.reason_codes == codes("drawdown_target_measurement_not_computed")
    assert (decision.transition, decision.max_peak_distance) == (None, "")
    _assert_intact(built)


def test_rg4_and_rg5_status_elsewhere_never_blocks_the_measured_target() -> None:
    env = rg3t.world_envelope()
    evidence = bound_evidence(env, rg4t.sleeve_world(ALPHA))
    assert evidence.drawdown.status is PaperSleeveDrawdownStatus.NOT_COMPUTABLE
    assert evidence.drawdown.missing_sleeve_ids == (BETA,)
    (pair,) = evidence.correlation.pairs
    assert pair.pair_status is PaperSleeveCorrelationPairStatus.WORST_CASE_UNKNOWN
    built = decided(decision_inputs(governed_seed(), evidence))
    decision, reference = built.decision, world_genesis().decision
    assert (decision.status, decision.drawdown_status, decision.correlation_status) == (
        READY,
        "NOT_COMPUTABLE",
        "READY",
    )
    for name in (
        "current_tier",
        "tier_elapsed_days",
        "transition",
        "resulting_tier",
        "resulting_tier_entered_at_ns",
        "paper_sharpe_annualized",
        "max_peak_distance",
        "decision_reason_codes",
    ):
        assert getattr(decision, name) == getattr(reference, name), name
    assert decision.drawdown_evidence_digest != reference.drawdown_evidence_digest
    _assert_intact(built)


def test_an_ungoverned_rg4_policy_needs_governance_approval() -> None:
    drawdown_inputs = rg4t.drawdown_inputs(performance_path_policy=rg4t.policy_for(approved=False))
    drawdown = rg4t.build(drawdown_inputs)
    assert drawdown.status is PaperSleeveDrawdownStatus.NEEDS_GOVERNANCE_APPROVAL
    built = decided(
        decision_inputs(governed_seed(), world_evidence(), drawdown_inputs=drawdown_inputs, drawdown_evidence=drawdown)
    )
    assert (built.decision.status, built.decision.transition) == (NEEDS_GOVERNANCE, None)
    assert built.decision.reason_codes == codes("drawdown_evidence_needs_governance_approval")
    _assert_intact(built)


def _reseal_rg4(evidence, **changes):
    changed = replace(evidence, **changes)
    return replace(changed, drawdown_evidence_digest=paper_sleeve_drawdown_evidence_digest(changed))


@pytest.mark.parametrize(
    "forge",
    [
        lambda evidence: replace(evidence, drawdown_evidence_digest="0" * 64),
        lambda evidence: _reseal_rg4(
            evidence,
            sleeves=tuple(
                replace(record, measurement=replace(record.measurement, max_peak_distance="0/1"))
                for record in evidence.sleeves
            ),
        ),
        lambda evidence: _reseal_rg4(evidence, sleeves=evidence.sleeves[1:]),
    ],
    ids=["digest_tamper", "resealed_max", "resealed_dropped_target"],
)
def test_rg4_evidence_that_is_not_the_reconstruction_is_refused(forge) -> None:
    evidence = world_evidence()
    with _raises("drawdown_evidence_not_reconstructed"):
        decide(decision_inputs(governed_seed(), evidence, drawdown_evidence=forge(evidence.drawdown)))


def test_rg4_over_another_envelope_is_refused() -> None:
    foreign = evidence_for(ladder_envelope(*CHAIN_LADDER), (0, 30))
    inputs = decision_inputs(
        governed_seed(), world_evidence(), drawdown_inputs=foreign.drawdown_inputs, drawdown_evidence=foreign.drawdown
    )
    with _raises("drawdown_evidence_envelope_mismatch"):
        decide(inputs)


def test_rg4_must_bind_the_exact_target_rg3() -> None:
    other = evidence_for(rg3t.world_envelope(), (0, 30))
    assert (
        other.target.evidence.performance_evidence_digest
        != world_evidence().target.evidence.performance_evidence_digest
    )
    inputs = decision_inputs(
        governed_seed(), world_evidence(), drawdown_inputs=other.drawdown_inputs, drawdown_evidence=other.drawdown
    )
    with _raises("drawdown_target_performance_mismatch"):
        decide(inputs)


def test_rg4_must_end_at_the_evaluation_end() -> None:
    later = later_world_evidence()
    inputs = decision_inputs(
        governed_seed(), world_evidence(), drawdown_inputs=later.drawdown_inputs, drawdown_evidence=later.drawdown
    )
    with _raises("drawdown_evidence_not_at_the_evaluation_end"):
        decide(inputs)


def test_promotion_consumes_the_maximum_never_the_current_peak_distance() -> None:
    built = drawdown_hold()
    decision = built.decision
    measurement = _record(evidence_for(ladder_envelope(*DRAWDOWN_LADDER), (15, 45))).measurement
    ceiling = Fraction(decision.promotion_boundary.promotion_max_drawdown_fraction)
    # Negative control: the current peak distance clears the ceiling, the maximum does not.
    assert Fraction(measurement.current_peak_distance) <= ceiling < Fraction(measurement.max_peak_distance)
    assert decision.max_peak_distance == measurement.max_peak_distance
    assert (decision.current_tier, decision.tier_elapsed_days, decision.transition) == (PROBATION, 30, HOLD)
    assert decision.decision_reason_codes == codes(
        "no_demotion_below_probation",
        "promotion_max_drawdown_above_ceiling",
        "promotion_sharpe_floor_met",
        "promotion_tenure_met",
    )
    _assert_intact(built)


def test_demotion_consumes_the_maximum_never_the_current_peak_distance() -> None:
    promoted, built = drawdown_link(0).decision, drawdown_link(1)
    decision = built.decision
    measurement = _record(evidence_for(ladder_envelope(*DRAWDOWN_LADDER), (15, 45))).measurement
    ceiling = Fraction(decision.demotion_boundary.demotion_max_drawdown_fraction)
    assert (promoted.transition, promoted.resulting_tier) == (PROMOTE, STANDARD)
    # Negative control: the current peak distance stays within the ceiling, the maximum breaches it.
    assert Fraction(measurement.current_peak_distance) <= ceiling < Fraction(measurement.max_peak_distance)
    assert decision.max_peak_distance == measurement.max_peak_distance
    assert (decision.current_tier, decision.transition, decision.resulting_tier) == (STANDARD, DEMOTE, PROBATION)
    assert decision.resulting_tier_entered_at_ns == decision.evaluation_end_ns == W0 + 45 * DAY
    assert (decision.promotion_boundary, decision.demotion_boundary) == (None, promoted.promotion_boundary)
    assert decision.decision_reason_codes == codes(
        "demotion_evaluated_before_promotion",
        "demotion_max_drawdown_strictly_above_ceiling",
        "demotion_sharpe_floor_held",
        "promotion_not_evaluated_after_demotion",
    )
    _assert_intact(built)


def test_the_drawdown_measure_is_fixed_and_never_chosen() -> None:
    assert paper_sleeve_promotion_demotion_rule_set()["drawdown_consumption"] == "MAX_PEAK_DISTANCE"
    for decision in (world_genesis().decision, chain_link(3).decision, drawdown_link(1).decision):
        assert decision.drawdown_consumption == "MAX_PEAK_DISTANCE"
    source = Path(decision_module.__file__).read_text(encoding="utf-8")
    assert "current_peak_distance" not in source
    assert "portfolio" not in {node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)}


# --- G. RG-5 --------------------------------------------------------------------------------------------------------


def test_rg5_is_provenance_only_and_its_cap_is_never_evaluated() -> None:
    reference = world_genesis().decision
    worst = bound_evidence(rg3t.world_envelope(), rg4t.sleeve_world(ALPHA)).correlation
    (pair,) = worst.pairs
    # The worst-case pair's effective correlation exceeds the cap, and the transition is still unchanged.
    assert Fraction(pair.effective_correlation) > Fraction(worst.max_pairwise_correlation)
    assert reference.transition is PROMOTE
    assert reference.correlation_cap_breach_evaluated is False
    assert reference.diversification_credit_granted is False


def test_a_one_sleeve_envelope_has_no_pair_and_still_decides() -> None:
    link = chain_link(0)
    assert (link.inputs.correlation_evidence.pair_count, link.decision.status) == (0, READY)


def test_an_ungoverned_rg5_needs_governance_approval() -> None:
    alpha = rg4t.sleeve_world(ALPHA)
    assert ungoverned_beta().evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    drawdown_inputs = rg4t.drawdown_inputs(sleeves=(alpha.drawdown_inputs(),))
    correlation_inputs = rg5t.correlation_inputs(sleeves=(rg5t.item(alpha), rg5t.item(ungoverned_beta())))
    correlation = rg5t.build(correlation_inputs)
    assert correlation.status is PaperSleeveCorrelationStatus.NEEDS_GOVERNANCE_APPROVAL
    evidence = Evidence(alpha, drawdown_inputs, rg4t.build(drawdown_inputs), correlation_inputs, correlation)
    built = decided(decision_inputs(governed_seed(), evidence))
    assert (built.decision.status, built.decision.transition) == (NEEDS_GOVERNANCE, None)
    assert built.decision.reason_codes == codes("correlation_evidence_needs_governance_approval")
    _assert_intact(built)


def _reseal_rg5(evidence, **changes):
    changed = replace(evidence, **changes)
    return replace(changed, correlation_evidence_digest=paper_sleeve_correlation_evidence_digest(changed))


@pytest.mark.parametrize(
    "forge",
    [
        lambda evidence: replace(evidence, correlation_evidence_digest="0" * 64),
        lambda evidence: _reseal_rg5(evidence, max_pairwise_correlation="0.990000000000000000"),
    ],
    ids=["digest_tamper", "resealed_cap"],
)
def test_rg5_evidence_that_is_not_the_reconstruction_is_refused(forge) -> None:
    evidence = world_evidence()
    with _raises("correlation_evidence_not_reconstructed"):
        decide(decision_inputs(governed_seed(), evidence, correlation_evidence=forge(evidence.correlation)))


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda: evidence_for(ladder_envelope(*CHAIN_LADDER), (0, 30)), "correlation_evidence_envelope_mismatch"),
        (lambda: evidence_for(rg3t.world_envelope(), (0, 30)), "correlation_target_performance_mismatch"),
        (lambda: evidence_for(rg3t.world_envelope(), sleeve_id=BETA), "correlation_evidence_missing_the_target_sleeve"),
    ],
)
def test_rg5_must_bind_the_envelope_and_the_exact_target(make, code: str) -> None:
    other = make()
    inputs = decision_inputs(
        governed_seed(),
        world_evidence(),
        correlation_inputs=other.correlation_inputs,
        correlation_evidence=other.correlation,
    )
    with _raises(code):
        decide(inputs)


def test_rg5_must_be_at_the_evaluation_end() -> None:
    correlation_inputs = rg5t.correlation_inputs(evaluation_end_ns=END + 5 * DAY)
    inputs = decision_inputs(
        governed_seed(),
        world_evidence(),
        correlation_inputs=correlation_inputs,
        correlation_evidence=rg5t.build(correlation_inputs),
    )
    with _raises("correlation_evidence_not_at_the_evaluation_end"):
        decide(inputs)


# --- H/I/J. exact transition matrices -------------------------------------------------------------------------------


def _outcome(tier: PaperSleeveLadderTier, tenure: int, sharpe: Fraction, drawdown: Fraction, ladder=None):
    lower, upper = ladder or (rg2.lower_boundary(), rg2.upper_boundary())
    return decision_module._evaluate_transition(tier, tenure, sharpe, drawdown, lower, upper)


def _around(value: str) -> tuple[Fraction, ...]:
    center = Fraction(value)
    return (center - UNIT, center - Fraction(1, 10**100), center, center + Fraction(1, 10**100), center + UNIT)


def test_probation_promotes_iff_tenure_sharpe_and_max_drawdown_all_hold() -> None:
    lower = rg2.lower_boundary()
    for tenure in (29, 30, 31):
        for sharpe in _around("1"):
            for drawdown in _around("0.1"):
                outcome = _outcome(PROBATION, tenure, sharpe, drawdown)
                eligible = tenure >= 30 and sharpe >= 1 and drawdown <= Fraction(1, 10)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (PROMOTE, STANDARD) if eligible else (HOLD, PROBATION)
                )
                assert (outcome.promotion_boundary, outcome.demotion_boundary) == (lower, None)
                assert set(outcome.reasons) == {
                    _code("promotion_tenure_met" if tenure >= 30 else "promotion_tenure_insufficient"),
                    _code("promotion_sharpe_floor_met" if sharpe >= 1 else "promotion_sharpe_below_floor"),
                    _code(
                        "promotion_max_drawdown_ceiling_met"
                        if drawdown <= Fraction(1, 10)
                        else "promotion_max_drawdown_above_ceiling"
                    ),
                    _code("no_demotion_below_probation"),
                }


def test_standard_demotes_strictly_over_its_lower_boundary_first() -> None:
    lower = rg2.lower_boundary()
    for sharpe in _around("0"):
        for drawdown in _around("0.2"):
            outcome = _outcome(STANDARD, 10**6, sharpe, drawdown)
            breach = sharpe < 0 or drawdown > Fraction(2, 10)
            if breach:
                assert (outcome.transition, outcome.resulting_tier) == (DEMOTE, PROBATION)
                assert (outcome.promotion_boundary, outcome.demotion_boundary) == (None, lower)
                assert _code("promotion_not_evaluated_after_demotion") in outcome.reasons
            else:
                # Sharpe below the upper promotion floor: the sleeve holds.
                assert (outcome.transition, outcome.resulting_tier) == (HOLD, STANDARD)
            assert (_code("demotion_sharpe_strictly_below_floor") in outcome.reasons) is (sharpe < 0)
            assert (_code("demotion_max_drawdown_strictly_above_ceiling") in outcome.reasons) is (
                drawdown > Fraction(2, 10)
            )


def test_standard_promotes_iff_every_upper_promotion_condition_holds() -> None:
    lower, upper = rg2.lower_boundary(), rg2.upper_boundary()
    for tenure in (59, 60, 61):
        for sharpe in _around("1.5"):
            for drawdown in _around("0.08"):
                outcome = _outcome(STANDARD, tenure, sharpe, drawdown)
                eligible = tenure >= 60 and sharpe >= Fraction(3, 2) and drawdown <= Fraction(8, 100)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (PROMOTE, EXPANDED) if eligible else (HOLD, STANDARD)
                )
                assert (outcome.promotion_boundary, outcome.demotion_boundary) == (upper, lower)
                assert {_code("demotion_sharpe_floor_held"), _code("demotion_evaluated_before_promotion")} <= set(
                    outcome.reasons
                )


def test_expanded_demotes_strictly_and_never_promotes() -> None:
    upper = rg2.upper_boundary()
    for tenure in (0, 10**6):
        for sharpe in (*_around("0.5"), Fraction(10**6)):
            for drawdown in (*_around("0.15"), Fraction(0)):
                outcome = _outcome(EXPANDED, tenure, sharpe, drawdown)
                breach = sharpe < Fraction(1, 2) or drawdown > Fraction(15, 100)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (DEMOTE, STANDARD) if breach else (HOLD, EXPANDED)
                )
                assert (outcome.promotion_boundary, outcome.demotion_boundary) == (None, upper)
                assert _code("no_promotion_above_expanded") in outcome.reasons


def test_demotion_precedes_a_promotion_only_a_contradictory_ladder_allows() -> None:
    contradictory = (rg2.lower_boundary(promotion_sharpe="2", demotion_sharpe="2"), rg2.upper_boundary())
    with _raises("ladder_consistency_invariant_violated"):
        decision_module._require_consistent_ladder(contradictory)
    # Eligible for demotion over the lower boundary and for promotion over the upper boundary at once.
    outcome = _outcome(STANDARD, 10**6, Fraction(18, 10), Fraction(1, 100), contradictory)
    assert (outcome.transition, outcome.resulting_tier) == (DEMOTE, PROBATION)
    assert (outcome.promotion_boundary, outcome.demotion_boundary) == (None, contradictory[0])
    assert set(outcome.reasons) == {
        _code("demotion_sharpe_strictly_below_floor"),
        _code("demotion_max_drawdown_ceiling_held"),
        _code("demotion_evaluated_before_promotion"),
        _code("promotion_not_evaluated_after_demotion"),
    }


def test_an_exact_promotion_sharpe_floor_is_inclusive_end_to_end() -> None:
    at_floor = promotion_floor_genesis(world_sharpe())
    above = promotion_floor_genesis(unit_above(world_sharpe()))
    assert at_floor.decision.paper_sharpe_annualized == world_sharpe()
    assert at_floor.decision.promotion_boundary.promotion_min_paper_sharpe == world_sharpe()
    assert (at_floor.decision.transition, at_floor.decision.resulting_tier) == (PROMOTE, STANDARD)
    assert (above.decision.transition, above.decision.resulting_tier) == (HOLD, PROBATION)
    assert _code("promotion_sharpe_below_floor") in above.decision.decision_reason_codes
    _assert_intact(at_floor)


def test_an_exact_demotion_sharpe_floor_is_strict_end_to_end() -> None:
    sharpe = chain_sharpe((10, 40))
    for floor, transition, resulting, reason in (
        (sharpe, HOLD, STANDARD, "demotion_sharpe_floor_held"),
        (unit_above(sharpe), DEMOTE, PROBATION, "demotion_sharpe_strictly_below_floor"),
    ):
        promoted, decision = demotion_floor_link(floor, 0).decision, demotion_floor_link(floor, 1).decision
        assert (promoted.transition, promoted.resulting_tier) == (PROMOTE, STANDARD)
        assert (decision.current_tier, decision.paper_sharpe_annualized) == (STANDARD, sharpe)
        assert decision.demotion_boundary.demotion_min_paper_sharpe == floor
        assert (decision.transition, decision.resulting_tier) == (transition, resulting)
        assert _code(reason) in decision.decision_reason_codes
    _assert_intact(demotion_floor_link(unit_above(sharpe), 1))


# --- K. one adjacent step -------------------------------------------------------------------------------------------


def test_every_transition_moves_at_most_one_adjacent_tier() -> None:
    extremes = (Fraction(-(10**6)), Fraction(0), Fraction(10**6))
    for tier in (PROBATION, STANDARD, EXPANDED):
        for tenure in (0, 10**6):
            for sharpe in extremes:
                for drawdown in (Fraction(0), Fraction(1, 2), 1 - UNIT):
                    outcome = _outcome(tier, tenure, sharpe, drawdown)
                    step = TIER_INDEX[outcome.resulting_tier] - TIER_INDEX[tier]
                    assert step == {HOLD: 0, PROMOTE: 1, DEMOTE: -1}[outcome.transition]
    with _raises("current_tier_invalid"):
        _outcome(None, 0, Fraction(0), Fraction(0))  # type: ignore[arg-type]


# --- N. regime and O. non-decisions ---------------------------------------------------------------------------------


def test_regime_concentration_demotion_stays_pending_until_rf() -> None:
    decision = world_genesis().decision
    assert decision.regime_concentration_demotion_status == "PENDING_RF_LABEL_ENUM_UNAVAILABLE"
    assert rg3t.world_envelope().regime_concentration_demotion_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert decision.regime_demotion_evaluated is False
    tree = ast.parse(Path(decision_module.__file__).read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)} | {
        alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names
    }
    assert not [name for name in imported if name and name.startswith(("crypto_core.regime", "crypto_core.edge"))]
    assert "crypto_core.validation.edge_kill_quarantine_decision" not in imported


def test_a_decision_claims_nothing_beyond_one_ladder_transition() -> None:
    flags = dict(PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS)
    assert [name for name, value in flags.items() if value is True] == ["paper_only"]
    assert {
        "current_ladder_head_proven",
        "regime_demotion_evaluated",
        "correlation_cap_breach_evaluated",
        "diversification_credit_granted",
        "portfolio_allocation_approved",
        "capital_allocated",
        "portfolio_stop_evaluated",
        "kill_quarantine_decided",
        "execution_authorized",
        "live_ready",
        "shadow_ready",
        "operational_readiness",
        "real_orders_enabled",
        "real_capital_reserved",
    } <= set(flags)
    for built in (world_genesis(), chain_link(3), blocked_genesis(), ungoverned_genesis()):
        assert {name: getattr(built.decision, name) for name in flags} == flags
    names = [item.name for item in fields(PaperSleevePromotionDemotionDecision)]
    assert names[-len(flags) :] == list(flags)
    assert not [name for name in names if name not in flags and re.search("alloc|weight|budget|capital|order", name)]


# --- P. tamper and totality -----------------------------------------------------------------------------------------


TAMPERS: dict[str, object] = {
    "status": NOT_COMPUTABLE,
    "ready": False,
    "advances": False,
    "decision_id": "rg6-decision-forged",
    "correlation_id": "corr-forged",
    "envelope_digest": "0" * 64,
    "envelope_advances": False,
    "sleeve_id": BETA,
    "ladder_seed_digest": "0" * 64,
    "ladder_seed_advances": False,
    "prior_decision_digest": "0" * 64,
    "lineage_sequence": 1,
    "evaluation_end_ns": W0 + 26 * DAY,
    "current_tier": STANDARD,
    "current_tier_entered_at_ns": W0 + DAY,
    "tier_elapsed_days": 24,
    "transition": HOLD,
    "resulting_tier": EXPANDED,
    "resulting_tier_entered_at_ns": W0,
    "performance_evidence_digest": "0" * 64,
    "drawdown_evidence_digest": "0" * 64,
    "correlation_evidence_digest": "0" * 64,
    "paper_sharpe_annualized": "9.000000000000000000",
    "max_peak_distance": "0/1",
    "drawdown_consumption": "CURRENT_PEAK_DISTANCE",
    "promotion_boundary": None,
    "demotion_boundary": rg2.lower_boundary(),
    "decision_reason_codes": (),
    "reason_codes": (_code("forged"),),
    "regime_concentration_demotion_status": "RF_LABEL_ENUM_BOUND",
    "rule_set_digest": "0" * 64,
    "paper_only": False,
    "current_ladder_head_proven": True,
    "regime_demotion_evaluated": True,
    "correlation_cap_breach_evaluated": True,
    "portfolio_allocation_approved": True,
    "kill_quarantine_decided": True,
    "execution_authorized": True,
}


@pytest.fixture
def cached_rebuild(monkeypatch: pytest.MonkeyPatch) -> Decided:
    """chain_link(0) with its verifier's rebuild served from the cached authentic decision."""

    built = chain_link(0)
    real = decision_module.build_paper_sleeve_promotion_demotion_decision
    monkeypatch.setattr(
        decision_module,
        "build_paper_sleeve_promotion_demotion_decision",
        lambda inputs: built.decision if inputs is built.inputs else real(inputs),
    )
    return built


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_every_tampered_field_is_detected(cached_rebuild: Decided, name: str) -> None:
    decision = cached_rebuild.decision
    assert getattr(decision, name) != TAMPERS[name]
    plain = verify(replace(decision, **{name: TAMPERS[name]}), cached_rebuild.inputs)
    assert plain.intact is False
    assert set(plain.reason_codes) == {_code(f"field_mismatch:{name}"), _code("self_digest_mismatch")}
    resealed = verify(_reseal(decision, **{name: TAMPERS[name]}), cached_rebuild.inputs)
    assert resealed.reason_codes == codes(f"field_mismatch:{name}", "field_mismatch:decision_digest")


def test_a_tampered_digest_alone_is_detected(cached_rebuild: Decided) -> None:
    verification = verify(replace(cached_rebuild.decision, decision_digest="0" * 64), cached_rebuild.inputs)
    assert verification.reason_codes == codes("field_mismatch:decision_digest", "self_digest_mismatch")


@pytest.mark.parametrize("name", ["current_tier", "transition", "max_peak_distance", "current_ladder_head_proven"])
def test_a_resealed_tamper_is_detected_by_genuine_reconstruction(name: str) -> None:
    built = chain_link(0)
    verification = verify(_reseal(built.decision, **{name: TAMPERS[name]}), built.inputs)
    assert verification.reason_codes == codes(f"field_mismatch:{name}", "field_mismatch:decision_digest")


def test_the_decision_verifier_is_total() -> None:
    built = chain_link(0)
    for value in (None, {}, "decision", built.inputs, governed_seed()):
        verification = verify(value, built.inputs)
        assert (verification.intact, verification.reason_codes) == (False, codes("evidence_type_invalid"))
    for forged in (
        replace(built.decision, status="READY"),
        replace(built.decision, lineage_sequence=-1),
        replace(built.decision, reason_codes=["x"]),
        replace(built.decision, promotion_boundary={"lower_tier": "PROBATION"}),
    ):
        assert verify(forged, built.inputs).reason_codes == codes("evidence_serialization_failed")
    for inputs in (None, replace(built.inputs, decision_id="")):
        verification = verify(built.decision, inputs)
        assert (verification.intact, verification.reason_codes) == (False, codes("evidence_reconstruction_failed"))
        assert (verification.recomputed_digest, verification.canonical_json) == ("", "")


def test_the_decision_is_immutable_and_its_mapping_fresh() -> None:
    built = chain_link(0)
    with pytest.raises(FrozenInstanceError):
        built.decision.transition = HOLD  # type: ignore[misc]
    mapping = paper_sleeve_promotion_demotion_decision_to_dict(built.decision)
    mapping["transition"] = "HOLD"
    assert paper_sleeve_promotion_demotion_decision_to_dict(built.decision)["transition"] == "PROMOTE"
    assert decide(built.inputs) == built.decision
    assert mapping["promotion_boundary"]["lower_tier"] == "PROBATION"  # type: ignore[index]


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"decision_id": _Text("rg6-decision-1")}, "decision_id_invalid"),
        ({"decision_id": ""}, "decision_id_invalid"),
        ({"decision_id": "live-decision"}, "forbidden_scope_token:decision_id"),
        ({"correlation_id": "bist-corr"}, "bist_scope_leakage:correlation_id"),
        ({"correlation_id": 7}, "correlation_id_invalid"),
        ({"evaluation_end_ns": True}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": -DAY}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": INT64_MAX + 1}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": float(END)}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": END + 1}, "evaluation_end_ns_not_utc_day_aligned"),
    ],
)
def test_decision_scalars_are_exact(overrides: dict[str, object], code: str) -> None:
    with _raises(code):
        decide(decision_inputs(governed_seed(), world_evidence(), **overrides))


@pytest.mark.parametrize(
    ("scalar", "value", "code"),
    [
        ("sharpe", "1.80931453070937285", "performance_sharpe_invalid"),
        ("sharpe", "01.809314530709372854", "performance_sharpe_invalid"),
        ("sharpe", "-0.000000000000000000", "performance_sharpe_invalid"),
        ("sharpe", "+1.000000000000000000", "performance_sharpe_invalid"),
        ("sharpe", "1e0", "performance_sharpe_invalid"),
        ("sharpe", "１.000000000000000000", "performance_sharpe_invalid"),
        ("sharpe", Fraction(1), "performance_sharpe_invalid"),
        ("distance", "2/4", "drawdown_peak_distance_invalid"),
        ("distance", "1/1", "drawdown_peak_distance_invalid"),
        ("distance", "0/2", "drawdown_peak_distance_invalid"),
        ("distance", "01/3", "drawdown_peak_distance_invalid"),
        ("distance", "1/03", "drawdown_peak_distance_invalid"),
        ("distance", "1/0", "drawdown_peak_distance_invalid"),
        ("distance", "-1/3", "drawdown_peak_distance_invalid"),
        ("distance", "1", "drawdown_peak_distance_invalid"),
        ("distance", "1/" + "9" * 4097, "drawdown_peak_distance_invalid"),
        ("distance", Fraction(1, 3), "drawdown_peak_distance_invalid"),
    ],
)
def test_consumed_metric_texts_are_exact(scalar: str, value: object, code: str) -> None:
    with _raises(code):
        if scalar == "sharpe":
            decision_module._scale18_value(value, code)
        else:
            decision_module._peak_distance_value(value)


def test_an_integer_text_the_interpreter_refuses_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(text: str) -> int:
        raise ValueError("Exceeds the limit for integer string conversion")

    monkeypatch.setattr(decision_module, "int", refuse, raising=False)
    with _raises("performance_sharpe_invalid"):
        decision_module._scale18_value("1.000000000000000000", "performance_sharpe_invalid")


def test_consumed_metric_texts_read_exactly() -> None:
    assert decision_module._scale18_value("-12.000000000000000001", "x") == Fraction(
        -12_000_000_000_000_000_001, 10**18
    )
    assert decision_module._scale18_value("0.000000000000000000", "x") == 0
    assert decision_module._peak_distance_value("0/1") == 0
    assert decision_module._peak_distance_value("1/3") == Fraction(1, 3)
    big = "9" * 4095 + "8"
    assert decision_module._peak_distance_value(f"1/{big}") == Fraction(1, int(big))


@pytest.mark.parametrize(
    ("guard", "forge", "code"),
    [
        ("seed", lambda seed: replace(seed, initial_tier=STANDARD), "ladder_seed_initial_tier_not_probation"),
        ("seed", lambda seed: replace(seed, rule_set_digest="0" * 64), "ladder_seed_rule_set_unsupported"),
        ("seed", lambda seed: replace(seed, sleeve_id="sleeve-gamma"), "ladder_seed_sleeve_not_declared_by_envelope"),
        ("seed", lambda seed: replace(seed, tier_entered_at_ns=W0 + 1), "tier_tenure_not_whole_utc_days"),
        ("prior", lambda decision: replace(decision, rule_set_digest="0" * 64), "prior_decision_rule_set_unsupported"),
        ("prior", lambda decision: replace(decision, resulting_tier=None), "prior_decision_resulting_state_invalid"),
    ],
)
def test_defense_in_depth_guards_fail_closed_on_a_forged_state(
    monkeypatch: pytest.MonkeyPatch, guard: str, forge, code: str
) -> None:
    intact = EdgeEvidenceVerification(True, (), "", "")
    if guard == "seed":
        monkeypatch.setattr(decision_module, "verify_paper_sleeve_ladder_seed", lambda seed: intact)
        inputs = decision_inputs(forge(governed_seed()), world_evidence())
    else:
        monkeypatch.setattr(decision_module, "verify_paper_sleeve_promotion_demotion_decision", lambda *args: intact)
        link = world_genesis()
        inputs = decision_inputs(
            PaperSleeveLadderPriorDecision(link.inputs, forge(link.decision)), later_world_evidence()
        )
    with _raises(code):
        decide(inputs)


def test_a_reconstructed_sleeve_the_envelope_does_not_declare_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence = world_evidence()
    forged = replace(evidence.target.evidence, sleeve_id="sleeve-gamma")
    monkeypatch.setattr(decision_module, "build_paper_sleeve_performance_evidence", lambda inputs: forged)
    with _raises("performance_sleeve_not_declared_by_envelope"):
        decide(decision_inputs(governed_seed(), evidence, performance_evidence=forged))


def test_a_seed_on_another_envelope_is_refused() -> None:
    with _raises("ladder_seed_envelope_mismatch"):
        decide(decision_inputs(governed_seed(ladder_envelope(*CHAIN_LADDER)), world_evidence()))


# --- Q. the design authority ----------------------------------------------------------------------------------------


def test_the_design_records_the_rg6_authority() -> None:
    text = DESIGN_DOC.read_text(encoding="utf-8")
    start = text.index("5. **RG-6 `paper_sleeve_promotion_demotion_decision.py`**")
    item = " ".join(text[start : text.index("6. **RG-7", start)].split())
    for phrase in (
        "RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1",
        "governed ladder-state seed: its initial tier is always PROBATION",
        "HUMAN_GOVERNANCE approval",
        "exactly one re-proven prior RG-6 decision of the same sleeve and envelope",
        "`current_ladder_head_proven` is structurally False",
        "exact number of UTC days",
        "RG-3 `paper_sharpe_annualized`",
        "RG-6 owns how ladder thresholds consume RG-4 sleeve drawdown evidence",
        "RG-4 `max_peak_distance` for promotion and demotion alike (`MAX_PEAK_DISTANCE`)",
        "RG-5 at the same evaluation end is re-proven provenance only: its cap is never evaluated",
        "STANDARD evaluates demotion first",
        "at most one adjacent transition per record",
        "pending and unevaluated until the RF chain merges",
        "decides no allocation, cap breach, diversification credit, kill or quarantine, portfolio stop or execution",
        "chooses no production number",
    ):
        assert phrase in item, phrase


# --- static discipline ----------------------------------------------------------------------------------------------


def test_module_is_pure_and_consumes_only_its_reproven_inputs() -> None:
    pit.assert_module_is_pure(
        decision_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_sleeve_correlation_evidence",
            "crypto_core.validation.paper_sleeve_drawdown_evidence",
            "crypto_core.validation.paper_sleeve_performance_evidence",
        },
    )


def test_single_assembly_and_construction_sites() -> None:
    pit.assert_single_assembly_path(
        decision_module, "PaperSleeveLadderSeed", "_assemble_seed", "build_paper_sleeve_ladder_seed", "_reassemble_seed"
    )
    world.assert_single_construction_site(
        decision_module,
        "PaperSleevePromotionDemotionDecision",
        "build_paper_sleeve_promotion_demotion_decision",
        "verify_paper_sleeve_promotion_demotion_decision",
    )
    tree = ast.parse(Path(decision_module.__file__).read_text(encoding="utf-8"))
    callers = [
        function.name
        for function in ast.walk(tree)
        if isinstance(function, ast.FunctionDef)
        for node in ast.walk(function)
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "_evaluate_transition"
    ]
    assert callers == ["build_paper_sleeve_promotion_demotion_decision"]


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(decision_module)
    # Character, identifier and wire bounds, the ladder size, the decimal base and scale, the RG-4 digit bound and the day.
    assert integers <= {0, 1, 2, 10, 18, 32, 127, 128, 256, 4096, world.DAY_NS, INT64_MAX}
    assert decimals <= {"0", "9"}
    for record_type in (
        PaperSleeveLadderSeedApproval,
        PaperSleevePromotionDemotionInputs,
        PaperSleeveLadderPriorDecision,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record_type))
    seed_flags = dict(PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS)
    decision_flags = dict(PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS)
    assert all(
        item.default is dataclasses.MISSING for item in fields(PaperSleeveLadderSeed) if item.name not in seed_flags
    )
    assert all(
        item.default is dataclasses.MISSING
        for item in fields(PaperSleevePromotionDemotionDecision)
        if item.name not in decision_flags
    )


def test_the_rule_set_is_committed_and_fresh() -> None:
    rule_set = paper_sleeve_promotion_demotion_rule_set()
    assert decision_module.edge_sha256_text(decision_module.edge_canonical_json(rule_set)) == (
        PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST
    )
    assert (rule_set["genesis_tier"], rule_set["drawdown_consumption"]) == ("PROBATION", "MAX_PEAK_DISTANCE")
    assert rule_set["structural_authority_id"] == "RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1"
    rule_set["genesis_tier"] = "EXPANDED"
    assert paper_sleeve_promotion_demotion_rule_set()["genesis_tier"] == "PROBATION"


def test_public_api_is_exact_and_offers_no_head_lookup() -> None:
    assert set(decision_module.__all__) == {
        "PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS",
        "PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS",
        "PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST",
        "PaperSleeveLadderDecisionStatus",
        "PaperSleeveLadderError",
        "PaperSleeveLadderPriorDecision",
        "PaperSleeveLadderSeed",
        "PaperSleeveLadderSeedApproval",
        "PaperSleeveLadderSeedApprovalKind",
        "PaperSleeveLadderTransition",
        "PaperSleevePromotionDemotionDecision",
        "PaperSleevePromotionDemotionInputs",
        "build_paper_sleeve_ladder_seed",
        "build_paper_sleeve_promotion_demotion_decision",
        "paper_sleeve_ladder_seed_digest",
        "paper_sleeve_ladder_seed_from_payload",
        "paper_sleeve_ladder_seed_to_dict",
        "paper_sleeve_promotion_demotion_decision_digest",
        "paper_sleeve_promotion_demotion_decision_to_dict",
        "paper_sleeve_promotion_demotion_rule_set",
        "verify_paper_sleeve_ladder_seed",
        "verify_paper_sleeve_promotion_demotion_decision",
    }
    assert all(hasattr(decision_module, name) for name in decision_module.__all__)
    assert not [name for name in decision_module.__all__ if re.search("head|latest|registry|current", name, re.I)]
    assert {status.value for status in PaperSleeveLadderDecisionStatus} == {
        "READY",
        "NOT_COMPUTABLE",
        "NEEDS_GOVERNANCE_APPROVAL",
    }
    assert [transition.value for transition in PaperSleeveLadderTransition] == ["HOLD", "PROMOTE", "DEMOTE"]
