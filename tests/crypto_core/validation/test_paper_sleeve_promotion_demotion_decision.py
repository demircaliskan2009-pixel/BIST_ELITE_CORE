"""RG-6 paper sleeve promotion and demotion decision (RG6_PAPER_SLEEVE_PROMOTION_DEMOTION_DECISION_V1) tests.

SYNTHETIC TEST VALUES ONLY: every ladder threshold, tier entry, identifier and approval below is a test value chosen to
exercise one rule, never a production number. Evidence is genuine (built by the accepted RG-2..RG-5 builders from the
shared authentic sleeve worlds) unless a test says it uses TEST-ONLY evidence stubs, which exist only to exercise the
lineage proof alone at depth.

Lineage depth is proven portably (RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1): long lineages verify
under the interpreter's default recursion limit from deep caller stacks, replays rebuild each node once, a static proof
shows no recursive call path, and no test asserts an exact interpreter frame boundary.
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
import crypto_core.validation.paper_sleeve_promotion_demotion_decision as rg6
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
)
from crypto_core.validation.paper_portfolio_risk_envelope import PaperPortfolioRiskEnvelope, PaperSleeveLadderTier
from crypto_core.validation.paper_position_state import paper_position_state_digest
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
from crypto_core.validation.paper_sleeve_funding_evidence import PaperSleeveFundingEvent
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

try:  # the module objects pytest collects (basename import), so authentic worlds and their caches are built once
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

PREFIX = "paper_sleeve_promotion_demotion_decision"
PROBATION = PaperSleeveLadderTier.PROBATION
STANDARD = PaperSleeveLadderTier.STANDARD
EXPANDED = PaperSleeveLadderTier.EXPANDED
HOLD = PaperSleeveLadderTransition.HOLD
PROMOTE = PaperSleeveLadderTransition.PROMOTE
DEMOTE = PaperSleeveLadderTransition.DEMOTE
READY = PaperSleeveLadderDecisionStatus.READY
NOT_COMPUTABLE = PaperSleeveLadderDecisionStatus.NOT_COMPUTABLE
NEEDS_GOVERNANCE = PaperSleeveLadderDecisionStatus.NEEDS_GOVERNANCE_APPROVAL
HUMAN = PaperSleeveLadderSeedApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperSleeveLadderSeedApprovalKind.TEST_ONLY_SYNTHETIC
ALPHA, BETA = rg4t.ALPHA, rg4t.BETA
W0, DAY, END = world.WINDOW_START, world.DAY_NS, world.WINDOW_END
INT64_MAX = 9223372036854775807
ULP = Fraction(1, 10**18)
TIER_RANK = {PROBATION: 0, STANDARD: 1, EXPANDED: 2}
DESIGN = Path(__file__).resolve().parents[3] / "docs" / "crypto_core" / "multi_sleeve_risk_governance_design.md"

# SYNTHETIC ladders as (lower-boundary overrides, upper-boundary overrides) of the RG-2 fixture ladder.
# WALK: over the WALK_WINDOWS ends it yields PROMOTE, PROMOTE, HOLD, DEMOTE, HOLD.
WALK = (
    (("probation", 25), ("promotion_sharpe", "1.2"), ("promotion_drawdown", "0.04")),
    (
        ("probation", 5),
        ("promotion_sharpe", "1.7"),
        ("promotion_drawdown", "0.04"),
        ("demotion_sharpe", "1.3"),
        ("demotion_drawdown", "0.12"),
    ),
)
WALK_LOWER_DEMOTION = (("demotion_sharpe", "0.3"), ("demotion_drawdown", "0.12"))
WALK_WINDOWS = ((-5, 25), (0, 30), (5, 35), (10, 40), (15, 45))
# DRAWDOWN: ceilings strictly between the current (~0.0002) and the maximum (~0.0388) peak distance of (15, 45).
DRAWDOWN = (
    (("promotion_drawdown", "0.025"), ("demotion_sharpe", "0"), ("demotion_drawdown", "0.035")),
    (("promotion_sharpe", "1.6"), ("promotion_drawdown", "0.02")),
)


class _Text(str):
    """A ``str`` subclass, never an exact text."""


def code(name: str) -> str:
    return f"{PREFIX}:{name}"


def codes(*names: str) -> tuple[str, ...]:
    return tuple(sorted(code(name) for name in names))


def raises(name: str):
    return pytest.raises(PaperSleeveLadderError, match=f"^{re.escape(code(name))}$")


def scale18(value: Fraction) -> str:
    units = value * 10**18
    assert units.denominator == 1
    magnitude = abs(units.numerator)
    text = f"{magnitude // 10**18}.{magnitude % 10**18:018d}"
    return f"-{text}" if units < 0 else text


# --- seeds ----------------------------------------------------------------------------------------------------------


def seed_args(**overrides: object) -> dict[str, object]:
    """SYNTHETIC TEST VALUES for every seed input; the module itself has no default."""

    args: dict[str, object] = {
        "seed_id": "rg6-test-seed",
        "seed_version": "synthetic-v1",
        "portfolio_risk_envelope": rg3t.world_envelope(),
        "sleeve_id": ALPHA,
        "tier_entered_at_ns": W0,
        "approval": None,
    }
    args.update(overrides)
    return args


def make_seed(**overrides: object) -> PaperSleeveLadderSeed:
    return build_paper_sleeve_ladder_seed(**seed_args(**overrides))  # type: ignore[arg-type]


def approval_for(
    seed: PaperSleeveLadderSeed, *, kind: object = HUMAN, **overrides: object
) -> PaperSleeveLadderSeedApproval:
    values: dict[str, object] = {
        "approval_reference": "synthetic-test-approval-record",
        "approval_digest": "c" * 64,
        "approval_kind": kind,
        "approved_seed_id": seed.seed_id,
        "approved_seed_version": seed.seed_version,
        "approved_seed_policy_digest": seed.seed_policy_digest,
        "approved_rule_set_digest": seed.rule_set_digest,
    }
    values.update(overrides)
    return PaperSleeveLadderSeedApproval(**values)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def human_seed(
    env: PaperPortfolioRiskEnvelope | None = None, entered: int = W0, sleeve_id: str = ALPHA
) -> PaperSleeveLadderSeed:
    """A seed under an exact synthetic HUMAN_GOVERNANCE test approval."""

    overrides = {
        "portfolio_risk_envelope": rg3t.world_envelope() if env is None else env,
        "tier_entered_at_ns": entered,
        "sleeve_id": sleeve_id,
    }
    return make_seed(approval=approval_for(make_seed(**overrides)), **overrides)


def reseal_seed(seed: PaperSleeveLadderSeed, **changes: object) -> PaperSleeveLadderSeed:
    changed = replace(seed, **changes)
    return replace(changed, ladder_seed_digest=paper_sleeve_ladder_seed_digest(changed))


# --- envelopes and genuine evidence ---------------------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def solo_envelope(
    lower: tuple[tuple[str, object], ...] = (), upper: tuple[tuple[str, object], ...] = ()
) -> PaperPortfolioRiskEnvelope:
    """A governed SYNTHETIC RG-2 envelope declaring alpha alone, the fixture ladder overridden."""

    return rg2.governed(
        sleeve_caps=[rg2.sleeve(ALPHA, "400")],
        ladder_boundaries=[rg2.lower_boundary(**dict(lower)), rg2.upper_boundary(**dict(upper))],
    )


@functools.lru_cache(maxsize=None)
def path_policy(env: PaperPortfolioRiskEnvelope):  # noqa: ANN201
    if [cap.sleeve_id for cap in env.sleeve_caps] == [ALPHA]:
        return rg4p.governed(portfolio_risk_envelope=env, performance_weights=[rg4p.weight(ALPHA, "1")])
    return rg4t.policy_for(env)


@dataclasses.dataclass(frozen=True)
class Evidence:
    """A target sleeve world and the RG-4 and RG-5 evidence that bind it."""

    target: rg4t.SleeveWorld
    drawdown_inputs: PaperSleeveDrawdownInputs
    drawdown: PaperSleeveDrawdownEvidence
    correlation_inputs: PaperSleeveCorrelationInputs
    correlation: PaperSleeveCorrelationEvidence


@functools.lru_cache(maxsize=None)
def shared_evidence() -> Evidence:
    """The shared authentic fixture: alpha's RG-3, with RG-4 and RG-5 over alpha and beta."""

    return Evidence(
        rg4t.sleeve_world(ALPHA),
        rg4t.drawdown_inputs(),
        rg4t.world_drawdown(),
        rg5t.correlation_inputs(),
        rg5t.world_correlation(),
    )


def lone_evidence(env: PaperPortfolioRiskEnvelope, target: rg4t.SleeveWorld) -> Evidence:
    """RG-4 and RG-5 over ``target`` alone, on its window and at its window end."""

    start, end = target.evidence.window_start_ns, target.evidence.window_end_ns
    label = f"{target.evidence.sleeve_id}-{(start - W0) // DAY}-{(end - W0) // DAY}"
    drawdown_inputs = PaperSleeveDrawdownInputs(
        drawdown_evidence_id=f"rg4-{label}",
        correlation_id="corr-rg6-test",
        portfolio_risk_envelope=env,
        performance_path_policy=path_policy(env),
        window_start_ns=start,
        window_end_ns=end,
        sleeves=(target.drawdown_inputs(),),
    )
    correlation_inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id=f"rg5-{label}",
        correlation_id="corr-rg6-test",
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
def window_evidence(
    env: PaperPortfolioRiskEnvelope, window: tuple[int, int] | None = None, sleeve_id: str = ALPHA
) -> Evidence:
    """``sleeve_id`` alone on ``env`` over ``window`` (the shared fixture window when None)."""

    target = rg4t.sleeve_world(sleeve_id, env) if window is None else rg5t.windowed_sleeve(sleeve_id, *window, env)
    return lone_evidence(env, target)


def with_beta(target: rg4t.SleeveWorld) -> Evidence:
    drawdown_inputs = rg4t.drawdown_inputs(
        sleeves=(target.drawdown_inputs(), rg4t.sleeve_world(BETA).drawdown_inputs())
    )
    correlation_inputs = rg5t.correlation_inputs(sleeves=(rg5t.item(target), rg5t.item(rg5t.sleeve(BETA))))
    return Evidence(
        target, drawdown_inputs, rg4t.build(drawdown_inputs), correlation_inputs, rg5t.build(correlation_inputs)
    )


def blocked_alpha(**valuation_overrides: object) -> rg4t.SleeveWorld:
    inputs = rg3t.performance_inputs(**rg3t.blocked_valuation_inputs(**valuation_overrides))
    return rg4t.SleeveWorld(inputs, rg3t.build(inputs))


def record_of(evidence: Evidence, sleeve_id: str = ALPHA):  # noqa: ANN201
    return next(record for record in evidence.drawdown.sleeves if record.sleeve_id == sleeve_id)


# --- decisions ------------------------------------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Built:
    inputs: PaperSleevePromotionDemotionInputs
    decision: PaperSleevePromotionDemotionDecision

    def node(self) -> PaperSleeveLadderPriorDecision:
        return PaperSleeveLadderPriorDecision(decision_inputs=self.inputs, decision=self.decision)


def inputs_for(state: object, evidence: Evidence, **overrides: object) -> PaperSleevePromotionDemotionInputs:
    values: dict[str, object] = {
        "decision_id": "rg6-test-decision",
        "correlation_id": "corr-rg6-test",
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


def built(inputs: PaperSleevePromotionDemotionInputs) -> Built:
    return Built(inputs, decide(inputs))


def verify(decision: object, inputs: object) -> EdgeEvidenceVerification:
    return verify_paper_sleeve_promotion_demotion_decision(decision, inputs)  # type: ignore[arg-type]


def reseal(decision: PaperSleevePromotionDemotionDecision, **changes: object) -> PaperSleevePromotionDemotionDecision:
    changed = replace(decision, **changes)
    return replace(changed, decision_digest=paper_sleeve_promotion_demotion_decision_digest(changed))


def assert_reproven(item: Built) -> None:
    verification = verify(item.decision, item.inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == item.decision.decision_digest
    assert json.loads(verification.canonical_json) == paper_sleeve_promotion_demotion_decision_to_dict(item.decision)


@functools.lru_cache(maxsize=None)
def genesis(entered: int = W0) -> Built:
    return built(inputs_for(human_seed(entered=entered), shared_evidence()))


def walk_envelope() -> PaperPortfolioRiskEnvelope:
    lower, upper = WALK
    return solo_envelope(lower + WALK_LOWER_DEMOTION, upper)


@functools.lru_cache(maxsize=None)
def walk(index: int) -> Built:
    """The WALK lineage: seed at W0, then one decision per WALK_WINDOWS end."""

    env = walk_envelope()
    state = human_seed(env) if index == 0 else walk(index - 1).node()
    return built(inputs_for(state, window_evidence(env, WALK_WINDOWS[index]), decision_id=f"rg6-walk-{index}"))


@functools.lru_cache(maxsize=None)
def late_walk(index: int) -> Built:
    """A WALK lineage whose seed enters one day late, so its genesis holds and its second decision promotes."""

    env = walk_envelope()
    state = human_seed(env, W0 + DAY) if index == 0 else late_walk(index - 1).node()
    return built(inputs_for(state, window_evidence(env, WALK_WINDOWS[index]), decision_id=f"rg6-late-{index}"))


def drawdown_envelope() -> PaperPortfolioRiskEnvelope:
    return solo_envelope(*DRAWDOWN)


@functools.lru_cache(maxsize=None)
def drawdown_genesis() -> Built:
    env = drawdown_envelope()
    return built(inputs_for(human_seed(env, W0 + 15 * DAY), window_evidence(env, (15, 45))))


@functools.lru_cache(maxsize=None)
def drawdown_walk(index: int) -> Built:
    env = drawdown_envelope()
    state = human_seed(env, W0 + 5 * DAY) if index == 0 else drawdown_walk(0).node()
    window = ((5, 35), (15, 45))[index]
    return built(inputs_for(state, window_evidence(env, window), decision_id=f"rg6-drawdown-{index}"))


@functools.lru_cache(maxsize=None)
def ungoverned_genesis() -> Built:
    return built(inputs_for(make_seed(), shared_evidence()))


@functools.lru_cache(maxsize=None)
def blocked_genesis() -> Built:
    return built(inputs_for(human_seed(), with_beta(blocked_alpha(funding_evidence=None))))


@functools.lru_cache(maxsize=None)
def beta_genesis() -> Built:
    evidence = replace(shared_evidence(), target=rg4t.sleeve_world(BETA))
    return built(inputs_for(human_seed(sleeve_id=BETA), evidence))


def later_shared_evidence(window: tuple[int, int] = (5, 35)) -> Evidence:
    return window_evidence(rg3t.world_envelope(), window)


def alpha_sharpe(evidence: Evidence) -> str:
    return evidence.target.evidence.paper_sharpe_annualized


# --- the fixtures are genuine ---------------------------------------------------------------------------------------


def test_the_shared_fixture_is_genuine_ready_evidence() -> None:
    evidence = shared_evidence()
    assert evidence.target.evidence.status is PaperSleevePerformanceStatus.READY
    assert evidence.target.evidence.window_end_ns == END
    assert (evidence.drawdown.status, evidence.correlation.status) == (
        PaperSleeveDrawdownStatus.READY,
        PaperSleeveCorrelationStatus.READY,
    )
    assert evidence.correlation.all_pairs_observed is True
    assert rg5t.envelope() == rg3t.world_envelope()


# --- B. the governed genesis seed -----------------------------------------------------------------------------------


def test_a_human_governed_seed_advances_at_probation() -> None:
    seed, env = human_seed(), rg3t.world_envelope()
    assert (seed.gate_verdict, seed.advances, seed.verdict_reason_codes) == (EdgeGateVerdict.PASS, True, ())
    assert (seed.initial_tier, seed.tier_entered_at_ns, seed.sleeve_id) == (PROBATION, W0, ALPHA)
    assert (seed.envelope_id, seed.envelope_version, seed.envelope_digest) == (
        env.envelope_id,
        env.envelope_version,
        env.envelope_digest,
    )
    assert seed.rule_set_digest == PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST
    assert seed.synthetic_test_approval_used is False
    assert seed.ladder_seed_digest == paper_sleeve_ladder_seed_digest(seed)
    assert {name: getattr(seed, name) for name, _ in PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS} == dict(
        PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS
    )
    verification = verify_paper_sleeve_ladder_seed(seed)
    assert (verification.intact, verification.recomputed_digest) == (True, seed.ladder_seed_digest)
    assert paper_sleeve_ladder_seed_from_payload(json.loads(verification.canonical_json)) == seed


def test_the_seed_policy_binds_the_state_and_excludes_only_governance() -> None:
    draft, governed = make_seed(), human_seed()
    assert draft.seed_policy_digest == governed.seed_policy_digest
    assert draft.ladder_seed_digest != governed.ladder_seed_digest
    for overrides in (
        {"tier_entered_at_ns": W0 + DAY},
        {"sleeve_id": BETA},
        {"seed_id": "rg6-test-seed-2"},
        {"seed_version": "synthetic-v2"},
        {"portfolio_risk_envelope": solo_envelope()},
    ):
        assert make_seed(**overrides).seed_policy_digest != draft.seed_policy_digest


@pytest.mark.parametrize(
    ("approval", "expected"),
    [
        (lambda draft: None, ("seed_governance_approval_missing",)),
        (lambda draft: approval_for(draft, kind=SYNTHETIC), ("seed_governance_approval_test_only_synthetic",)),
        (
            lambda draft: approval_for(make_seed(tier_entered_at_ns=W0 + DAY)),
            ("seed_governance_approval_seed_policy_digest_mismatch",),
        ),
        (
            lambda draft: approval_for(draft, approved_rule_set_digest="d" * 64),
            ("seed_governance_approval_rule_set_digest_mismatch",),
        ),
        (
            lambda draft: approval_for(draft, approved_seed_id="rg6-other-seed"),
            ("seed_governance_approval_seed_id_mismatch",),
        ),
        (
            lambda draft: approval_for(draft, approved_seed_version="synthetic-v9"),
            ("seed_governance_approval_seed_version_mismatch",),
        ),
        (
            lambda draft: approval_for(draft, kind=SYNTHETIC, approved_seed_policy_digest="e" * 64),
            ("seed_governance_approval_seed_policy_digest_mismatch", "seed_governance_approval_test_only_synthetic"),
        ),
    ],
    ids=["missing", "synthetic", "stale_policy", "stale_rule_set", "other_id", "other_version", "several"],
)
def test_only_an_exact_human_approval_advances_a_seed(approval, expected: tuple[str, ...]) -> None:
    seed = make_seed(approval=approval(make_seed()))
    assert (seed.gate_verdict, seed.advances, seed.initial_tier) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        PROBATION,
    )
    assert seed.verdict_reason_codes == codes(*expected)
    assert seed.synthetic_test_approval_used is ("seed_governance_approval_test_only_synthetic" in expected)
    assert verify_paper_sleeve_ladder_seed(seed).intact is True


def test_a_seed_without_governance_decides_nothing() -> None:
    item = ungoverned_genesis()
    decision = item.decision
    assert (decision.status, decision.advances, decision.reason_codes) == (
        NEEDS_GOVERNANCE,
        False,
        codes("ladder_seed_not_governed"),
    )
    assert (decision.ladder_seed_digest, decision.ladder_seed_advances) == (make_seed().ladder_seed_digest, False)
    assert (decision.current_tier, decision.tier_elapsed_days) == (PROBATION, 30)
    assert (decision.transition, decision.resulting_tier, decision.resulting_tier_entered_at_ns) == (None, None, None)
    assert (decision.paper_sharpe_annualized, decision.max_peak_distance, decision.decision_reason_codes) == (
        "",
        "",
        (),
    )


def test_the_genesis_tier_is_never_a_caller_choice() -> None:
    assert "initial_tier" not in inspect.signature(build_paper_sleeve_ladder_seed).parameters
    with pytest.raises(TypeError):
        build_paper_sleeve_ladder_seed(**seed_args(), initial_tier=STANDARD)  # type: ignore[call-arg]
    for forged in (replace(human_seed(), initial_tier=STANDARD), reseal_seed(human_seed(), initial_tier=EXPANDED)):
        assert code("field_mismatch:initial_tier") in verify_paper_sleeve_ladder_seed(forged).reason_codes
        with raises("ladder_seed_not_intact"):
            decide(inputs_for(forged, shared_evidence()))


def test_resealed_or_tampered_seed_governance_is_detected() -> None:
    forged = reseal_seed(make_seed(), gate_verdict=EdgeGateVerdict.PASS, advances=True, verdict_reason_codes=())
    assert verify_paper_sleeve_ladder_seed(forged).reason_codes == codes(
        "field_mismatch:advances",
        "field_mismatch:gate_verdict",
        "field_mismatch:ladder_seed_digest",
        "field_mismatch:verdict_reason_codes",
    )
    tampered = replace(human_seed(), ladder_seed_digest="0" * 64)
    assert verify_paper_sleeve_ladder_seed(tampered).reason_codes == codes(
        "field_mismatch:ladder_seed_digest", "self_digest_mismatch"
    )
    for state in (forged, tampered):
        with raises("ladder_seed_not_intact"):
            decide(inputs_for(state, shared_evidence()))


def test_a_seed_needs_an_intact_envelope_that_declares_its_sleeve() -> None:
    env = rg3t.world_envelope()
    with raises("portfolio_risk_envelope_not_intact"):
        make_seed(portfolio_risk_envelope=replace(env, envelope_digest="0" * 64))
    with raises("portfolio_risk_envelope_malformed"):
        make_seed(portfolio_risk_envelope=rg2.to_dict(env))
    with raises("seed_sleeve_not_declared_by_envelope"):
        make_seed(sleeve_id="sleeve-gamma")
    with raises("seed_sleeve_not_declared_by_envelope"):
        make_seed(sleeve_id=BETA, portfolio_risk_envelope=solo_envelope())


@pytest.mark.parametrize(
    ("value", "name"),
    [
        (True, "tier_entered_at_ns_invalid"),
        (-DAY, "tier_entered_at_ns_invalid"),
        (INT64_MAX + 1, "tier_entered_at_ns_invalid"),
        (float(W0), "tier_entered_at_ns_invalid"),
        (str(W0), "tier_entered_at_ns_invalid"),
        (None, "tier_entered_at_ns_invalid"),
        (W0 + 1, "tier_entered_at_ns_not_utc_day_aligned"),
        (W0 - DAY // 3, "tier_entered_at_ns_not_utc_day_aligned"),
    ],
)
def test_the_tier_entry_is_an_exact_utc_day_coordinate(value: object, name: str) -> None:
    with raises(name):
        make_seed(tier_entered_at_ns=value)
    assert make_seed(tier_entered_at_ns=0).tier_entered_at_ns == 0


@pytest.mark.parametrize(
    ("overrides", "name"),
    [
        ({"sleeve_id": _Text(ALPHA)}, "seed_sleeve_id_invalid"),
        ({"sleeve_id": " sleeve-alpha"}, "seed_sleeve_id_invalid"),
        ({"sleeve_id": "sleeve alpha"}, "seed_sleeve_id_invalid"),
        ({"sleeve_id": 3}, "seed_sleeve_id_invalid"),
        ({"sleeve_id": "live"}, "forbidden_scope_token:seed_sleeve_id"),
        ({"seed_id": ""}, "seed_id_invalid"),
        ({"seed_id": "rg6\tseed"}, "seed_id_invalid"),
        ({"seed_id": _Text("rg6-seed")}, "seed_id_invalid"),
        ({"seed_version": 1}, "seed_version_invalid"),
        ({"seed_id": "live-seed"}, "forbidden_scope_token:seed_id"),
        ({"seed_version": "bist-v1"}, "bist_scope_leakage:seed_version"),
    ],
)
def test_seed_texts_and_identifiers_are_exact(overrides: dict[str, object], name: str) -> None:
    with raises(name):
        make_seed(**overrides)


@pytest.mark.parametrize(
    ("approval", "name"),
    [
        (lambda draft: {"approval_kind": "HUMAN_GOVERNANCE"}, "seed_governance_approval_malformed"),
        (lambda draft: approval_for(draft, kind="OWNER"), "seed_governance_approval_kind_invalid"),
        (lambda draft: approval_for(draft, approval_digest="C" * 64), "seed_governance_approval_digest_invalid"),
        (
            lambda draft: approval_for(draft, approved_rule_set_digest="0" * 65),
            "seed_governance_approved_rule_set_digest_invalid",
        ),
        (
            lambda draft: approval_for(draft, approval_reference="signed by live desk"),
            "forbidden_scope_token:seed_governance_approval_reference",
        ),
    ],
)
def test_the_seed_approval_is_an_exact_record(approval, name: str) -> None:
    with raises(name):
        make_seed(approval=approval(make_seed()))


def test_an_exact_kind_text_normalizes_to_its_member() -> None:
    seed = make_seed(approval=approval_for(make_seed(), kind="HUMAN_GOVERNANCE"))
    assert seed == human_seed()
    assert seed.approval is not None and seed.approval.approval_kind is HUMAN


def test_the_seed_verifier_is_total() -> None:
    seed = human_seed()
    for value in (None, {}, "seed", paper_sleeve_ladder_seed_to_dict(seed), genesis().decision):
        assert verify_paper_sleeve_ladder_seed(value).reason_codes == codes("evidence_type_invalid")
    stages = {
        "evidence_serialization_failed": (
            replace(seed, initial_tier="PROBATION"),
            replace(seed, tier_entered_at_ns=-1),
            replace(seed, verdict_reason_codes=["x"]),
        ),
        "evidence_parse_failed": (replace(seed, advances=1), replace(seed, seed_version=2)),
        "evidence_reassembly_failed": (replace(seed, seed_id=""), replace(seed, tier_entered_at_ns=W0 + 7)),
    }
    for stage, forged in stages.items():
        for value in forged:
            verification = verify_paper_sleeve_ladder_seed(value)
            assert (verification.intact, verification.reason_codes) == (False, codes(stage))
            assert (verification.recomputed_digest, verification.canonical_json) == ("", "")


def test_the_seed_wire_form_parses_strictly() -> None:
    payload = paper_sleeve_ladder_seed_to_dict(human_seed())
    assert paper_sleeve_ladder_seed_from_payload(json.loads(json.dumps(payload))) == human_seed()
    bad_kind = json.loads(json.dumps(payload))
    bad_kind["approval"]["approval_kind"] = "OWNER"
    for value in (
        {**payload, "unexpected": 1},
        {name: item for name, item in payload.items() if name != "advances"},
        {**payload, "tier_entered_at_ns": True},
        {**payload, "initial_tier": "TOP"},
        {**payload, "verdict_reason_codes": "x"},
        bad_kind,
        [],
    ):
        with pytest.raises(PaperSleeveLadderError):
            paper_sleeve_ladder_seed_from_payload(value)


# --- I. genesis decisions and short-history semantics ---------------------------------------------------------------


def test_a_genesis_at_exactly_the_minimum_tenure_promotes_one_step() -> None:
    item, evidence = genesis(), shared_evidence()
    decision, env = item.decision, rg3t.world_envelope()
    lower = env.ladder_boundaries[0]
    assert (decision.status, decision.ready, decision.advances) == (READY, True, True)
    assert (decision.decision_id, decision.correlation_id) == ("rg6-test-decision", "corr-rg6-test")
    assert (decision.envelope_id, decision.envelope_version, decision.envelope_digest) == (
        env.envelope_id,
        env.envelope_version,
        env.envelope_digest,
    )
    assert (decision.envelope_policy_digest, decision.envelope_advances) == (env.policy_digest, True)
    assert (decision.sleeve_id, decision.market_symbol) == (ALPHA, evidence.target.evidence.market_symbol)
    assert (decision.ladder_seed_digest, decision.ladder_seed_advances) == (human_seed().ladder_seed_digest, True)
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
    assert (
        decision.performance_evidence_digest,
        decision.drawdown_evidence_digest,
        decision.correlation_evidence_digest,
    ) == (
        evidence.target.evidence.performance_evidence_digest,
        evidence.drawdown.drawdown_evidence_digest,
        evidence.correlation.correlation_evidence_digest,
    )
    assert (decision.performance_status, decision.drawdown_status, decision.correlation_status) == ("READY",) * 3
    assert decision.paper_sharpe_annualized == alpha_sharpe(evidence)
    assert decision.max_peak_distance == record_of(evidence).measurement.max_peak_distance
    assert (decision.drawdown_consumption, decision.promotion_boundary, decision.demotion_boundary) == (
        "MAX_PEAK_DISTANCE",
        lower,
        None,
    )
    assert decision.decision_reason_codes == codes(
        "probation_cannot_demote",
        "promotion_max_drawdown_within_ceiling",
        "promotion_sharpe_at_or_above_floor",
        "promotion_tenure_met",
    )
    assert decision.reason_codes == ()
    assert decision.regime_concentration_demotion_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert (decision.rule_set_digest, decision.decision_digest) == (
        PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST,
        paper_sleeve_promotion_demotion_decision_digest(decision),
    )
    assert_reproven(item)


def test_a_genesis_one_day_short_holds_and_keeps_its_entry() -> None:
    decision = genesis(W0 + DAY).decision
    assert (decision.tier_elapsed_days, decision.transition, decision.resulting_tier) == (29, HOLD, PROBATION)
    assert decision.resulting_tier_entered_at_ns == W0 + DAY
    assert code("promotion_tenure_short") in decision.decision_reason_codes


def test_zero_tenure_holds_and_an_entry_after_the_evaluation_end_is_refused() -> None:
    decision = genesis(END).decision
    assert (decision.tier_elapsed_days, decision.transition, decision.resulting_tier_entered_at_ns) == (0, HOLD, END)
    with raises("evaluation_end_precedes_the_tier_entry"):
        decide(inputs_for(human_seed(entered=END + DAY), shared_evidence()))


def test_a_promotion_crosses_one_boundary_however_far_the_snapshot_clears_the_ladder() -> None:
    decision = genesis(W0 - 200 * DAY).decision
    upper = rg3t.world_envelope().ladder_boundaries[1]
    assert decision.tier_elapsed_days == 230 >= upper.min_probation_days
    assert Fraction(decision.paper_sharpe_annualized) >= Fraction(upper.promotion_min_paper_sharpe)
    assert Fraction(decision.max_peak_distance) <= Fraction(upper.promotion_max_drawdown_fraction)
    assert (decision.transition, decision.resulting_tier, decision.demotion_boundary) == (PROMOTE, STANDARD, None)


def test_the_walk_lineage_promotes_promotes_holds_demotes_and_holds() -> None:
    lower, upper = walk_envelope().ladder_boundaries
    held = ("demotion_max_drawdown_not_above_ceiling", "demotion_sharpe_not_below_floor")
    standard = ("standard_demotion_evaluated_first", "promotion_tenure_met", "promotion_max_drawdown_within_ceiling")
    expected = (
        (PROBATION, 0, 25, PROMOTE, STANDARD, 25, (lower, None)),
        (STANDARD, 25, 5, PROMOTE, EXPANDED, 30, (upper, lower)),
        (EXPANDED, 30, 5, HOLD, EXPANDED, 30, (None, upper)),
        (EXPANDED, 30, 10, DEMOTE, STANDARD, 40, (None, upper)),
        (STANDARD, 40, 5, HOLD, STANDARD, 40, (upper, lower)),
    )
    reasons = (
        (
            "promotion_tenure_met",
            "promotion_sharpe_at_or_above_floor",
            "promotion_max_drawdown_within_ceiling",
            "probation_cannot_demote",
        ),
        (*held, *standard, "promotion_sharpe_at_or_above_floor"),
        (*held, "expanded_cannot_promote"),
        ("demotion_max_drawdown_not_above_ceiling", "demotion_sharpe_below_floor", "expanded_cannot_promote"),
        (*held, *standard, "promotion_sharpe_below_floor"),
    )
    for index, (row, why) in enumerate(zip(expected, reasons)):
        current, entered, tenure, transition, resulting, resulting_entered, bounds = row
        decision = walk(index).decision
        assert decision.status is READY
        assert (decision.lineage_sequence, decision.evaluation_end_ns) == (index, W0 + WALK_WINDOWS[index][1] * DAY)
        assert decision.prior_decision_digest == ("" if index == 0 else walk(index - 1).decision.decision_digest)
        assert decision.ladder_seed_digest == human_seed(walk_envelope()).ladder_seed_digest
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
        assert decision.decision_reason_codes == codes(*why)
    assert_reproven(walk(4))


def test_a_later_state_is_exactly_the_rebuilt_prior_result() -> None:
    for index in range(1, len(WALK_WINDOWS)):
        prior, decision = walk(index - 1).decision, walk(index).decision
        assert (decision.current_tier, decision.current_tier_entered_at_ns) == (
            prior.resulting_tier,
            prior.resulting_tier_entered_at_ns,
        )
        assert decision.evaluation_end_ns > prior.evaluation_end_ns
    # The HOLD at walk 2 keeps the walk 1 entry, so walk 3 counts ten days in EXPANDED.
    assert walk(3).decision.tier_elapsed_days == 10


def test_a_holding_genesis_carries_its_seed_entry_forward() -> None:
    first, second = late_walk(0).decision, late_walk(1).decision
    assert (first.tier_elapsed_days, first.transition, first.resulting_tier_entered_at_ns) == (24, HOLD, W0 + DAY)
    assert (second.current_tier_entered_at_ns, second.tier_elapsed_days, second.transition) == (W0 + DAY, 29, PROMOTE)
    assert second.resulting_tier_entered_at_ns == W0 + 30 * DAY


def test_inputs_carry_no_tier_entry_or_previous_result() -> None:
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
        inputs_for(human_seed(), shared_evidence(), current_tier=STANDARD)


def test_an_older_prior_yields_another_history_never_a_current_head() -> None:
    env = walk_envelope()
    fork = built(inputs_for(walk(0).node(), window_evidence(env, WALK_WINDOWS[2]), decision_id="rg6-fork"))
    assert fork.decision.evaluation_end_ns == walk(2).decision.evaluation_end_ns
    assert (fork.decision.current_tier, fork.decision.tier_elapsed_days, fork.decision.transition) == (
        STANDARD,
        10,
        HOLD,
    )
    assert walk(2).decision.current_tier is EXPANDED
    assert fork.decision.current_ladder_head_proven is False and walk(2).decision.current_ladder_head_proven is False


@pytest.mark.parametrize("prior", [ungoverned_genesis, blocked_genesis], ids=["needs_governance", "not_computable"])
def test_a_non_advancing_prior_propagates_its_status_through_the_lineage(prior) -> None:
    first = prior()
    second = built(inputs_for(first.node(), later_shared_evidence(), decision_id="rg6-propagated-1"))
    third = built(inputs_for(second.node(), later_shared_evidence((10, 40)), decision_id="rg6-propagated-2"))
    for item, sequence in ((second, 1), (third, 2)):
        decision = item.decision
        assert (decision.status, decision.advances, decision.lineage_sequence) == (
            first.decision.status,
            False,
            sequence,
        )
        assert decision.reason_codes == codes("prior_decision_not_advancing")
        assert (decision.current_tier, decision.tier_elapsed_days, decision.transition) == (None, None, None)
        assert decision.ladder_seed_advances is first.decision.ladder_seed_advances
    assert third.decision.prior_decision_digest == second.decision.decision_digest


def test_a_prior_must_bind_the_same_envelope_sleeve_and_an_earlier_end() -> None:
    with raises("prior_decision_envelope_mismatch"):
        decide(inputs_for(walk(0).node(), window_evidence(drawdown_envelope(), (5, 35))))
    with raises("performance_sleeve_not_the_lineage_sleeve"):
        decide(inputs_for(beta_genesis().node(), later_shared_evidence()))
    for days in (25, 20):
        with raises("evaluation_end_not_after_the_prior_decision"):
            decide(replace(walk(1).inputs, evaluation_end_ns=W0 + days * DAY))


@pytest.mark.parametrize(
    ("state", "name"),
    [
        (lambda: None, "ladder_state_malformed"),
        (lambda: genesis().decision, "ladder_state_malformed"),
        (lambda: PaperSleeveLadderPriorDecision(None, genesis().decision), "prior_decision_inputs_malformed"),
        (lambda: PaperSleeveLadderPriorDecision(genesis().inputs, None), "prior_decision_malformed"),
    ],
)
def test_the_ladder_state_is_an_exact_seed_or_prior_node(state, name: str) -> None:
    with raises(name):
        decide(inputs_for(state(), later_shared_evidence()))


# --- C/D/E/F/G/H. the non-recursive lineage proof -------------------------------------------------------------------


def through(wrappers: int, call):  # noqa: ANN001, ANN201
    """Call ``call`` behind ``wrappers`` extra caller frames (TEST-ONLY caller-depth variation)."""

    return call() if wrappers == 0 else through(wrappers - 1, call)


def stack_depth() -> int:
    frame, depth = inspect.currentframe(), 0
    while frame is not None:
        depth += 1
        frame = frame.f_back
    return depth


def count_assemblies(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, int]]:
    """Record every decision assembly (decision id, assembly stack depth) without changing its result."""

    real, seen = rg6._assemble_decision, []

    def counted(
        inputs: PaperSleevePromotionDemotionInputs, predecessor: object
    ) -> PaperSleevePromotionDemotionDecision:
        seen.append((inputs.decision_id, stack_depth()))
        return real(inputs, predecessor)  # type: ignore[arg-type]

    monkeypatch.setattr(rg6, "_assemble_decision", counted)
    return seen


def test_one_replay_rebuilds_each_historical_node_once_oldest_first(monkeypatch: pytest.MonkeyPatch) -> None:
    item = walk(4)
    seen = count_assemblies(monkeypatch)
    assert verify(item.decision, item.inputs).intact is True
    assert [name for name, _ in seen] == [f"rg6-walk-{index}" for index in range(len(WALK_WINDOWS))]
    # Every ancestor is rebuilt at one stack depth, the current decision one frame higher: the depth never grows.
    assert {depth for _, depth in seen[:-1]} == {seen[-1][1] + 1}


def serve_shared_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    """TEST-ONLY evidence stubs: every node gets the shared genuine evidence without a rebuild, so only the lineage
    proof runs; the same stubs serve construction and verification alike."""

    evidence = shared_evidence()
    target = record_of(evidence)
    monkeypatch.setattr(rg6, "_prove_performance", lambda inputs, envelope, end: evidence.target.evidence)
    monkeypatch.setattr(rg6, "_prove_drawdown", lambda inputs, envelope, end, performance: (evidence.drawdown, target))
    monkeypatch.setattr(rg6, "_prove_correlation", lambda inputs, envelope, end, performance: evidence.correlation)


def stubbed_lineage(length: int) -> list[Built]:
    """``length`` daily decisions after the shared seed, each assembled once from its predecessor."""

    evidence, predecessor = shared_evidence(), human_seed()
    state: object = predecessor
    lineage: list[Built] = []
    for index in range(length):
        inputs = inputs_for(state, evidence, evaluation_end_ns=END + index * DAY, decision_id=f"rg6-deep-{index}")
        lineage.append(Built(inputs, rg6._assemble_decision(inputs, predecessor)))
        predecessor, state = lineage[-1].decision, lineage[-1].node()
    return lineage


def test_a_300_link_lineage_verifies_alike_from_shallow_and_deep_callers(monkeypatch: pytest.MonkeyPatch) -> None:
    shared_evidence(), human_seed()  # authentic fixtures first, before any stub
    serve_shared_evidence(monkeypatch)
    lineage = stubbed_lineage(300)
    top = lineage[-1]
    assert (top.decision.status, top.decision.lineage_sequence, top.decision.current_tier) == (READY, 299, EXPANDED)
    assert [item.decision.transition for item in lineage].count(PROMOTE) == 2
    seen = count_assemblies(monkeypatch)
    # Under the default recursion limit a recursive re-proof needs several frames per link, far beyond what 300 links
    # allow; this proof verifies identically however deep its caller sits, rebuilding each node once per replay.
    results = []
    for wrappers in (0, 1, 500):
        seen.clear()
        results.append(through(wrappers, lambda: verify(top.decision, top.inputs)))
        assert [name for name, _ in seen] == [f"rg6-deep-{index}" for index in range(300)]
    assert results[0].intact is True and results[0].recomputed_digest == top.decision.decision_digest
    assert results == [results[0]] * 3


def test_a_5000_node_lineage_is_walked_without_recursion() -> None:
    base, carried = genesis().inputs, genesis().decision
    node = PaperSleeveLadderPriorDecision(base, carried)
    for _ in range(4999):
        node = PaperSleeveLadderPriorDecision(replace(base, ladder_state=node), carried)
    top = replace(base, ladder_state=node)
    # The walk reaches the seed through all 5000 nodes, the oldest rebuilds exactly, and the second fails on order.
    with raises("prior_decision_not_reproven") as failure:
        decide(top)
    assert str(failure.value.__cause__) == code("evaluation_end_not_after_the_prior_decision")
    assert verify(carried, top).reason_codes == codes("evidence_reconstruction_failed")
    # Generic equality, hashing and repr stay flat: a node compares by identity, and inputs leave the lineage out.
    assert (
        top == top
        and node == node
        and hash(node) == hash(node)
        and node != PaperSleeveLadderPriorDecision(base, carried)
    )
    assert "ladder_state" not in repr(top)


def test_a_cyclic_lineage_object_graph_fails_closed() -> None:
    later = window_evidence(walk_envelope(), WALK_WINDOWS[2])
    looped = replace(walk(1).inputs)
    single = PaperSleeveLadderPriorDecision(looped, walk(1).decision)
    object.__setattr__(looped, "ladder_state", single)  # hostile graph: the inputs lead back to their own node
    first_inputs, second_inputs = replace(walk(0).inputs), replace(walk(1).inputs)
    first = PaperSleeveLadderPriorDecision(first_inputs, walk(0).decision)
    second = PaperSleeveLadderPriorDecision(second_inputs, walk(1).decision)
    object.__setattr__(first_inputs, "ladder_state", second)
    object.__setattr__(second_inputs, "ladder_state", first)
    for state in (single, second):
        inputs = inputs_for(state, later)
        with raises("ladder_state_cycle"):
            decide(inputs)
        assert verify(walk(2).decision, inputs).reason_codes == codes("evidence_reconstruction_failed")


def rechain(*pairs: tuple[PaperSleevePromotionDemotionInputs, PaperSleevePromotionDemotionDecision]) -> object:
    """Nest ``(inputs, decision)`` pairs, oldest first, on the WALK seed, re-pointing each inputs at its predecessor."""

    state: object = human_seed(walk_envelope())
    for inputs, decision in pairs:
        state = PaperSleeveLadderPriorDecision(replace(inputs, ladder_state=state), decision)
    return state


def pair(index: int) -> tuple[PaperSleevePromotionDemotionInputs, PaperSleevePromotionDemotionDecision]:
    return walk(index).inputs, walk(index).decision


def resealed(
    index: int, **changes: object
) -> tuple[PaperSleevePromotionDemotionInputs, PaperSleevePromotionDemotionDecision]:
    return walk(index).inputs, reseal(walk(index).decision, **changes)


def test_an_authentic_rechained_lineage_rebuilds_the_same_decision() -> None:
    top = replace(walk(4).inputs, ladder_state=rechain(*(pair(index) for index in range(4))))
    assert decide(top) == walk(4).decision


@pytest.mark.parametrize(
    "history",
    [
        lambda: (pair(0), pair(2), pair(3)),
        lambda: (pair(1), pair(0), pair(2), pair(3)),
        lambda: (pair(0), pair(0), pair(1), pair(2), pair(3)),
        lambda: ((pair(0)[0], pair(1)[1]), pair(1), pair(2), pair(3)),
        lambda: (pair(0), (drawdown_walk(0).inputs, drawdown_walk(0).decision), pair(2), pair(3)),
        lambda: (pair(0), resealed(1, prior_decision_digest="0" * 64), pair(2), pair(3)),
        lambda: (pair(0), resealed(1, lineage_sequence=4), pair(2), pair(3)),
        lambda: (pair(0), resealed(1, evaluation_end_ns=W0 + 31 * DAY), pair(2), pair(3)),
        lambda: (pair(0), resealed(1, resulting_tier=STANDARD), pair(2), pair(3)),
        lambda: (pair(0), resealed(1, current_tier=PROBATION), pair(2), pair(3)),
        lambda: (pair(0), (pair(1)[0], replace(pair(1)[1], decision_digest="0" * 64)), pair(2), pair(3)),
        lambda: (pair(0), (replace(pair(1)[0], evaluation_end_ns=W0 + 31 * DAY), pair(1)[1]), pair(2), pair(3)),
    ],
    ids=[
        "skipped",
        "reordered",
        "duplicated",
        "foreign_inputs",
        "foreign_envelope",
        "forged_prior_digest",
        "forged_sequence",
        "forged_coordinate",
        "forged_resulting_tier",
        "forged_current_tier",
        "tampered_self_digest",
        "inputs_off_their_evidence_end",
    ],
)
def test_a_spliced_or_forged_ancestor_fails_closed(history) -> None:
    with raises("prior_decision_not_reproven"):
        decide(replace(walk(4).inputs, ladder_state=rechain(*history())))


def test_the_module_has_no_recursive_call_path_and_no_recursion_limit() -> None:
    source = Path(rg6.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    graph = {
        function.name: {
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        for function in tree.body
        if isinstance(function, ast.FunctionDef)
    }
    edges = {name: sorted(called & graph.keys()) for name, called in graph.items()}
    finished: set[str] = set()
    for start in edges:
        path, pending = [start], [iter(edges[start])]
        while pending:
            following = next(pending[-1], None)
            if following is None:
                finished.add(path.pop())
                pending.pop()
            elif following not in finished:
                assert following not in path, path + [following]
                path.append(following)
                pending.append(iter(edges[following]))
    assert "setrecursionlimit" not in source and "getrecursionlimit" not in source
    assert "verify_paper_sleeve_promotion_demotion_decision" not in {
        called
        for name, calls in graph.items()
        if name != "verify_paper_sleeve_promotion_demotion_decision"
        for called in calls
    }


@pytest.mark.slow
def test_a_genuine_300_link_lineage_verifies_and_extends() -> None:
    """Genuine RG-2..RG-5 evidence at every node (``--runslow``; the weekly CI slow-tests job runs it on its Python)."""

    env = solo_envelope((("probation", 1000),))

    def evidence_ending(offset: int) -> Evidence:
        start, end = W0 + offset * DAY, W0 + (offset + 30) * DAY
        plans = tuple(
            replace(plan, key=f"{plan.key}-at-{offset}", at_ns=plan.at_ns + offset * DAY)
            for plan in world.EPISODE_PLANS
        )
        episodes = world.build_chain(
            plans,
            draft=world.make_draft(ALPHA, "policy-alpha"),
            capacity_policy=world.make_capacity_policy(ALPHA, "policy-alpha"),
        )
        events = []
        for day in range(30):
            instant = start + day * DAY + world.FUNDING_SETTLEMENT_OFFSET_NS
            state = world.position_before(instant, episodes)
            if state.side.value != "FLAT":
                events.append(
                    PaperSleeveFundingEvent(
                        event_id=f"funding-{offset}-{day}",
                        settlement_at_ns=instant,
                        position_state_digest=paper_position_state_digest(state),
                        funding_amount=world.d("-0.01"),
                    )
                )
        basis = world.basis_policy(sleeve_id=ALPHA)
        valuation_inputs = world.valuation_inputs(
            valuation_id=f"rg6-deep-valuation-{offset}",
            window_start_ns=start,
            window_end_ns=end,
            episodes=episodes,
            day_closes=tuple(world.build_day_close(offset + day, episodes) for day in range(30)),
            equity_basis_policy=basis,
            funding_evidence=world.funding_evidence(
                sleeve_id=ALPHA, window_start_ns=start, window_end_ns=end, events=tuple(events)
            ),
        )
        valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
        inputs = rg3t.performance_inputs(
            performance_evidence_id=f"rg6-deep-rg3-{offset}",
            portfolio_risk_envelope=env,
            valuation_inputs=valuation_inputs,
            valuation=valuation,
            **rg3t.series_world(valuation, basis, start, end).inputs(),
        )
        target = rg4t.SleeveWorld(inputs, rg3t.build(inputs))
        assert target.evidence.status is PaperSleevePerformanceStatus.READY
        return lone_evidence(env, target)

    predecessor: object = human_seed(env)
    state, lineage = predecessor, []
    for offset in range(300):
        inputs = inputs_for(state, evidence_ending(offset), decision_id=f"rg6-genuine-{offset}")
        # Built once per node on the shared assembly path; every claim below is made by the PUBLIC verifier and builder.
        lineage.append(Built(inputs, rg6._assemble_decision(inputs, predecessor)))
        predecessor, state = lineage[-1].decision, lineage[-1].node()
    assert all(item.decision.status is READY and item.decision.transition is HOLD for item in lineage)
    for depth in (50, 256, 300):
        assert verify(lineage[depth - 1].decision, lineage[depth - 1].inputs).intact is True
    deep_caller = through(500, lambda: verify(lineage[-1].decision, lineage[-1].inputs))
    assert deep_caller.intact is True
    extension = decide(inputs_for(state, evidence_ending(300), decision_id="rg6-genuine-300"))
    assert (extension.status, extension.lineage_sequence, extension.current_ladder_head_proven) == (READY, 300, False)
    assert extension.prior_decision_digest == lineage[-1].decision.decision_digest


# --- D (RG-2). the envelope and its ladder --------------------------------------------------------------------------


@functools.lru_cache(maxsize=None)
def ungoverned_envelope_genesis(kind: str) -> Built:
    base = {"sleeve_caps": [rg2.sleeve(ALPHA, "400")]}
    approval = None if kind == "missing" else rg2.approval_for(rg2.build(**base), kind=rg2.SYNTHETIC)
    env = rg2.build(approval=approval, **base)
    assert env.advances is False
    return built(inputs_for(human_seed(env), window_evidence(env)))


@pytest.mark.parametrize("kind", ["missing", "synthetic"])
def test_an_ungoverned_envelope_needs_governance_approval(kind: str) -> None:
    decision = ungoverned_envelope_genesis(kind).decision
    assert (decision.status, decision.envelope_advances, decision.transition) == (NEEDS_GOVERNANCE, False, None)
    assert decision.reason_codes == codes(
        "correlation_evidence_needs_governance_approval",
        "drawdown_evidence_needs_governance_approval",
        "performance_evidence_needs_governance_approval",
        "portfolio_risk_envelope_not_governed",
    )


def test_the_envelope_is_an_intact_exact_record() -> None:
    with raises("portfolio_risk_envelope_not_intact"):
        decide(
            inputs_for(
                human_seed(),
                shared_evidence(),
                portfolio_risk_envelope=replace(rg3t.world_envelope(), max_sleeve_count=7),
            )
        )
    with raises("portfolio_risk_envelope_malformed"):
        decide(inputs_for(human_seed(), shared_evidence(), portfolio_risk_envelope="envelope"))


def test_the_envelope_rule_set_and_pending_regime_marker_are_pinned(monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = inputs_for(human_seed(), shared_evidence())
    with monkeypatch.context() as patch:
        patch.setattr(rg6, "PAPER_PORTFOLIO_RISK_ENVELOPE_RULE_SET_DIGEST", "f" * 64)
        with raises("portfolio_risk_envelope_rule_set_unsupported"):
            decide(inputs)
    with monkeypatch.context() as patch:
        patch.setattr(rg6, "EDGE_REGIME_LABEL_BINDING_PENDING", "RF_LABEL_ENUM_BOUND")
        with raises("regime_concentration_demotion_status_unsupported"):
            decide(inputs)


@pytest.mark.parametrize(
    ("ladder", "name"),
    [
        (
            lambda: (rg2.lower_boundary(promotion_sharpe="0", demotion_sharpe="0.5"), rg2.upper_boundary()),
            "consistency",
        ),
        (lambda: (rg2.lower_boundary(promotion_drawdown="0.25"), rg2.upper_boundary()), "consistency"),
        (
            lambda: (rg2.lower_boundary(), rg2.upper_boundary(promotion_drawdown="0.2", demotion_drawdown="0.1")),
            "consistency",
        ),
        (lambda: (rg2.lower_boundary(promotion_sharpe="2", demotion_sharpe="2"), rg2.upper_boundary()), "consistency"),
        (
            lambda: (rg2.lower_boundary(promotion_drawdown="0.05", demotion_drawdown="0.05"), rg2.upper_boundary()),
            "consistency",
        ),
        (lambda: (rg2.upper_boundary(), rg2.lower_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(),), "shape"),
        (lambda: [rg2.lower_boundary(), rg2.upper_boundary()], "shape"),
        (lambda: (rg2.lower_boundary(probation=0), rg2.upper_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(probation=False), rg2.upper_boundary()), "shape"),
        (lambda: (rg2.lower_boundary(), "upper"), "shape"),
        (lambda: (replace(rg2.lower_boundary(), promotion_min_paper_sharpe="1.0"), rg2.upper_boundary()), "threshold"),
    ],
)
def test_a_ladder_contradicting_rg2_fails_closed(monkeypatch: pytest.MonkeyPatch, ladder, name: str) -> None:
    expected = {
        "consistency": "ladder_consistency_invariant_violated",
        "shape": "ladder_boundaries_not_the_accepted_ladder",
        "threshold": "ladder_threshold_invalid",
    }[name]
    # Only a verifier-accepted envelope reaches the ladder check, so a TEST-ONLY verifier stub admits the forgery.
    seed, evidence = human_seed(), shared_evidence()
    monkeypatch.setattr(
        rg6, "verify_paper_portfolio_risk_envelope", lambda envelope: EdgeEvidenceVerification(True, (), "", "")
    )
    forged = replace(rg3t.world_envelope(), ladder_boundaries=ladder())
    with raises(expected):
        decide(inputs_for(seed, evidence, portfolio_risk_envelope=forged))


def test_every_accepted_fixture_ladder_is_consistent() -> None:
    for env in (rg3t.world_envelope(), walk_envelope(), drawdown_envelope()):
        assert rg6._require_ladder(env) == env.ladder_boundaries


# --- J/K. RG-3, RG-4 and RG-5 re-proof and temporal coherence -------------------------------------------------------


def test_an_uncomputable_target_is_not_computable() -> None:
    decision = blocked_genesis().decision
    assert (decision.status, decision.reason_codes) == (NOT_COMPUTABLE, codes("performance_evidence_not_computable"))
    assert (decision.performance_status, decision.drawdown_status, decision.correlation_status) == (
        "NOT_COMPUTABLE",
        "NOT_COMPUTABLE",
        "READY",
    )
    assert (decision.current_tier, decision.tier_elapsed_days, decision.transition, decision.max_peak_distance) == (
        PROBATION,
        30,
        None,
        "",
    )
    assert_reproven(blocked_genesis())


def test_an_ungoverned_target_needs_governance_approval() -> None:
    target = blocked_alpha(equity_basis_policy=world.basis_policy(governed=False))
    assert target.evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    decision = decide(inputs_for(human_seed(), with_beta(target)))
    assert (decision.status, decision.reason_codes) == (
        NEEDS_GOVERNANCE,
        codes(
            "correlation_evidence_needs_governance_approval",
            "drawdown_evidence_needs_governance_approval",
            "performance_evidence_needs_governance_approval",
        ),
    )


def reseal_rg3(evidence, **changes):  # noqa: ANN001, ANN201
    changed = replace(evidence, **changes)
    return replace(changed, performance_evidence_digest=paper_sleeve_performance_evidence_digest(changed))


@pytest.mark.parametrize(
    "forge",
    [
        lambda evidence: replace(evidence, paper_sharpe_annualized="7.000000000000000000"),
        lambda evidence: reseal_rg3(evidence, paper_sharpe_annualized="7.000000000000000000"),
        lambda evidence: rg4t.sleeve_world(BETA).evidence,
    ],
    ids=["tampered_sharpe", "resealed_sharpe", "another_sleeve"],
)
def test_rg3_that_is_not_the_reconstruction_is_refused(forge) -> None:
    evidence = shared_evidence()
    with raises("performance_evidence_not_reconstructed"):
        decide(inputs_for(human_seed(), evidence, performance_evidence=forge(evidence.target.evidence)))


def test_rg3_of_a_foreign_envelope_or_another_sleeve_is_refused() -> None:
    foreign = window_evidence(walk_envelope(), (0, 30)).target
    with raises("performance_evidence_envelope_mismatch"):
        decide(
            inputs_for(
                human_seed(),
                shared_evidence(),
                performance_inputs=foreign.inputs,
                performance_evidence=foreign.evidence,
            )
        )
    beta = rg4t.sleeve_world(BETA)
    with raises("performance_sleeve_not_the_lineage_sleeve"):
        decide(
            inputs_for(
                human_seed(), shared_evidence(), performance_inputs=beta.inputs, performance_evidence=beta.evidence
            )
        )


@pytest.mark.parametrize("end", [END - DAY, END + DAY])
def test_rg3_must_end_exactly_at_the_evaluation_end(end: int) -> None:
    with raises("performance_evidence_not_at_the_evaluation_end"):
        decide(inputs_for(human_seed(), shared_evidence(), evaluation_end_ns=end))


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
    with raises(f"{name}_malformed"):
        decide(inputs_for(human_seed(), shared_evidence(), **{name: None}))


@pytest.mark.parametrize(
    ("stage", "changes"),
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
def test_evidence_the_accepted_builder_refuses_fails_closed(stage: str, changes) -> None:
    evidence = shared_evidence()
    with raises(f"{stage}_reconstruction_failed"):
        decide(inputs_for(human_seed(), evidence, **changes(evidence)))


def test_the_rg4_target_must_be_present_and_bind_the_exact_rg3() -> None:
    beta_only = rg4t.drawdown_inputs(sleeves=(rg4t.sleeve_world(BETA).drawdown_inputs(),))
    with raises("drawdown_evidence_missing_the_target_sleeve"):
        decide(
            inputs_for(
                human_seed(), shared_evidence(), drawdown_inputs=beta_only, drawdown_evidence=rg4t.build(beta_only)
            )
        )
    other = later_shared_evidence((0, 30))
    assert (
        other.target.evidence.performance_evidence_digest
        != shared_evidence().target.evidence.performance_evidence_digest
    )
    with raises("drawdown_target_performance_mismatch"):
        decide(
            inputs_for(
                human_seed(), shared_evidence(), drawdown_inputs=other.drawdown_inputs, drawdown_evidence=other.drawdown
            )
        )


def test_rg4_of_a_foreign_envelope_or_another_end_is_refused() -> None:
    foreign = window_evidence(walk_envelope(), (0, 30))
    with raises("drawdown_evidence_envelope_mismatch"):
        decide(
            inputs_for(
                human_seed(),
                shared_evidence(),
                drawdown_inputs=foreign.drawdown_inputs,
                drawdown_evidence=foreign.drawdown,
            )
        )
    later = later_shared_evidence()
    with raises("drawdown_evidence_not_at_the_evaluation_end"):
        decide(
            inputs_for(
                human_seed(), shared_evidence(), drawdown_inputs=later.drawdown_inputs, drawdown_evidence=later.drawdown
            )
        )


def reseal_rg4(evidence, **changes):  # noqa: ANN001, ANN201
    changed = replace(evidence, **changes)
    return replace(changed, drawdown_evidence_digest=paper_sleeve_drawdown_evidence_digest(changed))


@pytest.mark.parametrize(
    "forge",
    [
        lambda evidence: replace(evidence, drawdown_evidence_digest="0" * 64),
        lambda evidence: reseal_rg4(
            evidence,
            sleeves=tuple(
                replace(item, measurement=replace(item.measurement, max_peak_distance="0/1"))
                for item in evidence.sleeves
            ),
        ),
        lambda evidence: reseal_rg4(evidence, sleeves=evidence.sleeves[1:]),
    ],
    ids=["tampered_digest", "resealed_max", "resealed_without_target"],
)
def test_rg4_that_is_not_the_reconstruction_is_refused(forge) -> None:
    evidence = shared_evidence()
    with raises("drawdown_evidence_not_reconstructed"):
        decide(inputs_for(human_seed(), evidence, drawdown_evidence=forge(evidence.drawdown)))


def test_an_unmeasured_target_is_not_computable(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, seed = shared_evidence(), human_seed()  # authentic cached fixtures first, before the patch
    monkeypatch.setattr(drawdown_module, "_measure", lambda values: None)
    drawdown = build_paper_sleeve_drawdown_evidence(evidence.drawdown_inputs)
    assert record_of(replace(evidence, drawdown=drawdown)).computed is False
    decision = decide(inputs_for(seed, evidence, drawdown_evidence=drawdown))
    assert (decision.status, decision.reason_codes) == (
        NOT_COMPUTABLE,
        codes("drawdown_target_measurement_not_computed"),
    )
    assert (decision.performance_status, decision.drawdown_status, decision.transition) == (
        "READY",
        "NOT_COMPUTABLE",
        None,
    )


def test_rg4_and_rg5_states_of_other_sleeves_never_block_the_measured_target() -> None:
    evidence = lone_evidence(rg3t.world_envelope(), rg4t.sleeve_world(ALPHA))
    assert evidence.drawdown.status is PaperSleeveDrawdownStatus.NOT_COMPUTABLE
    (pair_record,) = evidence.correlation.pairs
    assert pair_record.pair_status is PaperSleeveCorrelationPairStatus.WORST_CASE_UNKNOWN
    decision, reference = decide(inputs_for(human_seed(), evidence)), genesis().decision
    assert (decision.status, decision.drawdown_status) == (READY, "NOT_COMPUTABLE")
    for name in ("tier_elapsed_days", "transition", "resulting_tier", "paper_sharpe_annualized", "max_peak_distance"):
        assert getattr(decision, name) == getattr(reference, name), name


def test_an_ungoverned_rg4_policy_needs_governance_approval() -> None:
    drawdown_inputs = rg4t.drawdown_inputs(performance_path_policy=rg4t.policy_for(approved=False))
    decision = decide(
        inputs_for(
            human_seed(),
            shared_evidence(),
            drawdown_inputs=drawdown_inputs,
            drawdown_evidence=rg4t.build(drawdown_inputs),
        )
    )
    assert (decision.status, decision.reason_codes) == (
        NEEDS_GOVERNANCE,
        codes("drawdown_evidence_needs_governance_approval"),
    )


def test_rg5_is_provenance_only_and_its_cap_is_never_evaluated() -> None:
    worst = lone_evidence(rg3t.world_envelope(), rg4t.sleeve_world(ALPHA)).correlation
    (pair_record,) = worst.pairs
    assert Fraction(pair_record.effective_correlation) > Fraction(worst.max_pairwise_correlation)
    decision = genesis().decision
    assert decision.transition is PROMOTE
    assert (decision.correlation_cap_breach_evaluated, decision.diversification_credit_granted) == (False, False)
    assert walk(0).inputs.correlation_evidence.pair_count == 0 and walk(0).decision.status is READY


@functools.lru_cache(maxsize=None)
def ungoverned_beta() -> rg4t.SleeveWorld:
    policy_id = BETA.replace("sleeve", "policy")
    episodes = world.build_chain(
        rg4t.SLEEVE_PLANS[BETA],
        draft=world.make_draft(BETA, policy_id),
        capacity_policy=world.make_capacity_policy(BETA, policy_id),
    )
    valuation_inputs = world.valuation_inputs(
        valuation_id="rg6-beta-ungoverned",
        episodes=episodes,
        day_closes=tuple(world.build_day_close(day, episodes) for day in range(world.WINDOW_DAYS)),
        equity_basis_policy=world.basis_policy(sleeve_id=BETA, governed=False),
        funding_evidence=world.funding_evidence(sleeve_id=BETA, events=world.funding_events(episodes)),
    )
    inputs = rg3t.performance_inputs(
        performance_evidence_id="rg6-beta-ungoverned-rg3",
        valuation_inputs=valuation_inputs,
        valuation=build_paper_sleeve_daily_valuation_evidence(valuation_inputs),
        **rg3t.NO_SERIES,
    )
    return rg4t.SleeveWorld(inputs, rg3t.build(inputs))


def test_an_ungoverned_rg5_needs_governance_approval() -> None:
    alpha = rg4t.sleeve_world(ALPHA)
    assert ungoverned_beta().evidence.status is PaperSleevePerformanceStatus.NEEDS_GOVERNANCE_APPROVAL
    drawdown_inputs = rg4t.drawdown_inputs(sleeves=(alpha.drawdown_inputs(),))
    correlation_inputs = rg5t.correlation_inputs(sleeves=(rg5t.item(alpha), rg5t.item(ungoverned_beta())))
    evidence = Evidence(
        alpha, drawdown_inputs, rg4t.build(drawdown_inputs), correlation_inputs, rg5t.build(correlation_inputs)
    )
    decision = decide(inputs_for(human_seed(), evidence))
    assert (decision.status, decision.reason_codes) == (
        NEEDS_GOVERNANCE,
        codes("correlation_evidence_needs_governance_approval"),
    )


def reseal_rg5(evidence, **changes):  # noqa: ANN001, ANN201
    changed = replace(evidence, **changes)
    return replace(changed, correlation_evidence_digest=paper_sleeve_correlation_evidence_digest(changed))


@pytest.mark.parametrize(
    ("make", "name"),
    [
        (
            lambda: replace(
                shared_evidence(),
                correlation=replace(shared_evidence().correlation, correlation_evidence_digest="0" * 64),
            ),
            "correlation_evidence_not_reconstructed",
        ),
        (
            lambda: replace(
                shared_evidence(),
                correlation=reseal_rg5(shared_evidence().correlation, max_pairwise_correlation="0.900000000000000000"),
            ),
            "correlation_evidence_not_reconstructed",
        ),
        (lambda: window_evidence(walk_envelope(), (0, 30)), "correlation_evidence_envelope_mismatch"),
        (lambda: later_shared_evidence((0, 30)), "correlation_target_performance_mismatch"),
        (
            lambda: window_evidence(rg3t.world_envelope(), sleeve_id=BETA),
            "correlation_evidence_missing_the_target_sleeve",
        ),
    ],
    ids=["tampered_digest", "resealed_cap", "foreign_envelope", "other_rg3_binding", "target_missing"],
)
def test_rg5_must_be_the_reconstruction_on_the_envelope_binding_the_exact_target(make, name: str) -> None:
    other = make()
    with raises(name):
        decide(
            inputs_for(
                human_seed(),
                shared_evidence(),
                correlation_inputs=other.correlation_inputs,
                correlation_evidence=other.correlation,
            )
        )


def test_rg5_must_be_at_the_evaluation_end() -> None:
    correlation_inputs = rg5t.correlation_inputs(evaluation_end_ns=END + 3 * DAY)
    with raises("correlation_evidence_not_at_the_evaluation_end"):
        decide(
            inputs_for(
                human_seed(),
                shared_evidence(),
                correlation_inputs=correlation_inputs,
                correlation_evidence=rg5t.build(correlation_inputs),
            )
        )


# --- L. MAX_PEAK_DISTANCE negative controls -------------------------------------------------------------------------


def test_promotion_reads_the_maximum_never_the_current_peak_distance() -> None:
    decision = drawdown_genesis().decision
    measurement = record_of(window_evidence(drawdown_envelope(), (15, 45))).measurement
    ceiling = Fraction(decision.promotion_boundary.promotion_max_drawdown_fraction)
    assert Fraction(measurement.current_peak_distance) <= ceiling < Fraction(measurement.max_peak_distance)
    assert decision.max_peak_distance == measurement.max_peak_distance
    assert (decision.current_tier, decision.tier_elapsed_days, decision.transition) == (PROBATION, 30, HOLD)
    assert decision.decision_reason_codes == codes(
        "probation_cannot_demote",
        "promotion_max_drawdown_above_ceiling",
        "promotion_sharpe_at_or_above_floor",
        "promotion_tenure_met",
    )


def test_demotion_reads_the_maximum_never_the_current_peak_distance() -> None:
    promoted, decision = drawdown_walk(0).decision, drawdown_walk(1).decision
    measurement = record_of(window_evidence(drawdown_envelope(), (15, 45))).measurement
    ceiling = Fraction(decision.demotion_boundary.demotion_max_drawdown_fraction)
    assert (promoted.transition, promoted.resulting_tier) == (PROMOTE, STANDARD)
    assert Fraction(measurement.current_peak_distance) <= ceiling < Fraction(measurement.max_peak_distance)
    assert (decision.current_tier, decision.transition, decision.resulting_tier) == (STANDARD, DEMOTE, PROBATION)
    assert decision.resulting_tier_entered_at_ns == decision.evaluation_end_ns == W0 + 45 * DAY
    assert decision.decision_reason_codes == codes(
        "demotion_max_drawdown_above_ceiling",
        "demotion_sharpe_not_below_floor",
        "promotion_skipped_after_demotion",
        "standard_demotion_evaluated_first",
    )
    assert_reproven(drawdown_walk(1))


def test_the_drawdown_measure_is_fixed_by_the_rule_set() -> None:
    assert paper_sleeve_promotion_demotion_rule_set()["drawdown_consumption"] == "MAX_PEAK_DISTANCE"
    assert {genesis().decision.drawdown_consumption, walk(3).decision.drawdown_consumption} == {"MAX_PEAK_DISTANCE"}
    source = Path(rg6.__file__).read_text(encoding="utf-8")
    assert "current_peak_distance" not in source
    assert "portfolio" not in {node.attr for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Attribute)}


# --- M/N. exact transition matrices and STANDARD precedence ---------------------------------------------------------


def move(tier, tenure, sharpe, drawdown, ladder=None):  # noqa: ANN001, ANN201
    lower, upper = ladder or (rg2.lower_boundary(), rg2.upper_boundary())
    return rg6._move(tier, tenure, sharpe, drawdown, lower, upper)


def around(text: str) -> tuple[Fraction, ...]:
    center = Fraction(text)
    return (center - ULP, center - Fraction(1, 10**90), center, center + Fraction(1, 10**90), center + ULP)


def test_probation_promotes_iff_tenure_sharpe_and_maximum_drawdown_all_hold() -> None:
    for tenure in (29, 30, 31):
        for sharpe in around("1"):
            for drawdown in around("0.1"):
                outcome = move(PROBATION, tenure, sharpe, drawdown)
                eligible = tenure >= 30 and sharpe >= 1 and drawdown <= Fraction(1, 10)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (PROMOTE, STANDARD) if eligible else (HOLD, PROBATION)
                )
                assert (outcome.promotion_boundary, outcome.demotion_boundary) == (rg2.lower_boundary(), None)


def test_standard_demotes_strictly_first_over_its_lower_boundary() -> None:
    for sharpe in around("0"):
        for drawdown in around("0.2"):
            outcome = move(STANDARD, 10**6, sharpe, drawdown)
            breach = sharpe < 0 or drawdown > Fraction(1, 5)
            assert (outcome.transition, outcome.resulting_tier) == ((DEMOTE, PROBATION) if breach else (HOLD, STANDARD))
            assert (code("promotion_skipped_after_demotion") in outcome.reasons) is breach
            assert outcome.promotion_boundary == (None if breach else rg2.upper_boundary())


def test_standard_promotes_iff_every_upper_promotion_condition_holds() -> None:
    for tenure in (59, 60, 61):
        for sharpe in around("1.5"):
            for drawdown in around("0.08"):
                outcome = move(STANDARD, tenure, sharpe, drawdown)
                eligible = tenure >= 60 and sharpe >= Fraction(3, 2) and drawdown <= Fraction(2, 25)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (PROMOTE, EXPANDED) if eligible else (HOLD, STANDARD)
                )


def test_expanded_demotes_strictly_and_never_promotes() -> None:
    for tenure in (0, 10**6):
        for sharpe in (*around("0.5"), Fraction(10**6)):
            for drawdown in (*around("0.15"), Fraction(0)):
                outcome = move(EXPANDED, tenure, sharpe, drawdown)
                breach = sharpe < Fraction(1, 2) or drawdown > Fraction(3, 20)
                assert (outcome.transition, outcome.resulting_tier) == (
                    (DEMOTE, STANDARD) if breach else (HOLD, EXPANDED)
                )
                assert code("expanded_cannot_promote") in outcome.reasons


def test_demotion_wins_where_only_a_contradictory_ladder_could_also_promote() -> None:
    contradictory = (rg2.lower_boundary(promotion_sharpe="2", demotion_sharpe="2"), rg2.upper_boundary())
    outcome = move(STANDARD, 10**6, Fraction(9, 5), Fraction(1, 100), contradictory)
    assert (outcome.transition, outcome.resulting_tier, outcome.promotion_boundary) == (DEMOTE, PROBATION, None)
    assert set(outcome.reasons) == set(
        codes(
            "demotion_sharpe_below_floor",
            "demotion_max_drawdown_not_above_ceiling",
            "standard_demotion_evaluated_first",
            "promotion_skipped_after_demotion",
        )
    )


def test_every_movement_is_at_most_one_adjacent_step() -> None:
    for tier in (PROBATION, STANDARD, EXPANDED):
        for tenure in (0, 10**6):
            for sharpe in (Fraction(-(10**6)), Fraction(0), Fraction(10**6)):
                for drawdown in (Fraction(0), Fraction(1, 2), 1 - ULP):
                    outcome = move(tier, tenure, sharpe, drawdown)
                    step = TIER_RANK[outcome.resulting_tier] - TIER_RANK[tier]
                    assert step == {HOLD: 0, PROMOTE: 1, DEMOTE: -1}[outcome.transition]
    with raises("current_tier_invalid"):
        move(None, 0, Fraction(0), Fraction(0))


@functools.lru_cache(maxsize=None)
def promotion_floor_genesis(floor: str) -> Built:
    env = solo_envelope((("promotion_sharpe", floor),))
    return built(inputs_for(human_seed(env), window_evidence(env)))


@functools.lru_cache(maxsize=None)
def demotion_floor_walk(floor: str, index: int) -> Built:
    env = solo_envelope((("promotion_sharpe", "1.25"), ("promotion_drawdown", "0.05"), ("demotion_sharpe", floor)))
    state = human_seed(env, W0 + 5 * DAY) if index == 0 else demotion_floor_walk(floor, 0).node()
    return built(inputs_for(state, window_evidence(env, ((5, 35), (10, 40))[index]), decision_id=f"rg6-floor-{index}"))


def test_an_exact_promotion_floor_is_inclusive_end_to_end() -> None:
    sharpe = alpha_sharpe(shared_evidence())
    at_floor, above = (
        promotion_floor_genesis(sharpe).decision,
        promotion_floor_genesis(scale18(Fraction(sharpe) + ULP)).decision,
    )
    assert (at_floor.paper_sharpe_annualized, at_floor.transition) == (sharpe, PROMOTE)
    assert (above.transition, code("promotion_sharpe_below_floor") in above.decision_reason_codes) == (HOLD, True)


def test_an_exact_demotion_floor_is_strict_end_to_end() -> None:
    sharpe = alpha_sharpe(window_evidence(walk_envelope(), (10, 40)))
    for floor, transition, reason in (
        (sharpe, HOLD, "demotion_sharpe_not_below_floor"),
        (scale18(Fraction(sharpe) + ULP), DEMOTE, "demotion_sharpe_below_floor"),
    ):
        assert demotion_floor_walk(floor, 0).decision.transition is PROMOTE
        decision = demotion_floor_walk(floor, 1).decision
        assert (decision.current_tier, decision.paper_sharpe_annualized, decision.transition) == (
            STANDARD,
            sharpe,
            transition,
        )
        assert code(reason) in decision.decision_reason_codes


# --- O. regime and non-decisions ------------------------------------------------------------------------------------


def test_regime_concentration_demotion_stays_pending() -> None:
    decision = genesis().decision
    assert (decision.regime_concentration_demotion_status, decision.regime_demotion_evaluated) == (
        "PENDING_RF_LABEL_ENUM_UNAVAILABLE",
        False,
    )
    tree = ast.parse(Path(rg6.__file__).read_text(encoding="utf-8"))
    imported = {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}
    assert not [name for name in imported if name and name.startswith(("crypto_core.regime", "crypto_core.edge"))]
    assert "crypto_core.validation.edge_kill_quarantine_decision" not in imported


def test_a_decision_claims_nothing_beyond_one_ladder_movement() -> None:
    flags = dict(PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS)
    assert [name for name, value in flags.items() if value] == ["paper_only"]
    for item in (genesis(), walk(3), blocked_genesis(), ungoverned_genesis()):
        assert {name: getattr(item.decision, name) for name in flags} == flags
    names = [item.name for item in fields(PaperSleevePromotionDemotionDecision)]
    assert names[-len(flags) :] == list(flags)
    assert not [
        name for name in names if name not in flags and re.search("alloc|weight|budget|capital|order|stop", name)
    ]


# --- P. tamper and totality -----------------------------------------------------------------------------------------


TAMPERS: dict[str, object] = {
    "status": NOT_COMPUTABLE,
    "ready": False,
    "advances": False,
    "decision_id": "rg6-forged-decision",
    "envelope_digest": "0" * 64,
    "envelope_advances": False,
    "sleeve_id": BETA,
    "ladder_seed_digest": "0" * 64,
    "ladder_seed_advances": False,
    "prior_decision_digest": "0" * 64,
    "lineage_sequence": 9,
    "evaluation_end_ns": W0 + 26 * DAY,
    "current_tier": STANDARD,
    "current_tier_entered_at_ns": W0 + DAY,
    "tier_elapsed_days": 20,
    "transition": HOLD,
    "resulting_tier": EXPANDED,
    "resulting_tier_entered_at_ns": W0,
    "performance_evidence_digest": "0" * 64,
    "drawdown_evidence_digest": "0" * 64,
    "correlation_evidence_digest": "0" * 64,
    "paper_sharpe_annualized": "8.000000000000000000",
    "max_peak_distance": "0/1",
    "drawdown_consumption": "CURRENT_PEAK_DISTANCE",
    "promotion_boundary": None,
    "demotion_boundary": rg2.lower_boundary(),
    "decision_reason_codes": (),
    "reason_codes": (code("forged"),),
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
def served_rebuild(monkeypatch: pytest.MonkeyPatch) -> Built:
    """walk(0), with the verifier's rebuild served from its authentic cached decision (TEST-ONLY speed-up)."""

    item, real = walk(0), rg6.build_paper_sleeve_promotion_demotion_decision
    monkeypatch.setattr(
        rg6,
        "build_paper_sleeve_promotion_demotion_decision",
        lambda inputs: item.decision if inputs is item.inputs else real(inputs),
    )
    return item


@pytest.mark.parametrize("name", sorted(TAMPERS))
def test_every_tampered_field_is_detected(served_rebuild: Built, name: str) -> None:
    decision = served_rebuild.decision
    assert getattr(decision, name) != TAMPERS[name]
    plain = verify(replace(decision, **{name: TAMPERS[name]}), served_rebuild.inputs)
    assert set(plain.reason_codes) == {code(f"field_mismatch:{name}"), code("self_digest_mismatch")}
    sealed = verify(reseal(decision, **{name: TAMPERS[name]}), served_rebuild.inputs)
    assert sealed.reason_codes == codes(f"field_mismatch:{name}", "field_mismatch:decision_digest")


@pytest.mark.parametrize("name", ["current_tier", "transition", "max_peak_distance", "current_ladder_head_proven"])
def test_a_resealed_tamper_is_caught_by_genuine_reconstruction(name: str) -> None:
    item = walk(0)
    assert verify(reseal(item.decision, **{name: TAMPERS[name]}), item.inputs).reason_codes == codes(
        f"field_mismatch:{name}", "field_mismatch:decision_digest"
    )


def test_the_decision_verifier_is_total() -> None:
    item = walk(0)
    for value in (None, {}, "decision", item.inputs, human_seed()):
        assert verify(value, item.inputs).reason_codes == codes("evidence_type_invalid")
    for forged in (
        replace(item.decision, status="READY"),
        replace(item.decision, lineage_sequence=-1),
        replace(item.decision, reason_codes=["x"]),
        replace(item.decision, promotion_boundary={"lower_tier": "PROBATION"}),
        replace(item.decision, promotion_boundary=replace(rg2.lower_boundary(), lower_tier="PROBATION")),
    ):
        assert verify(forged, item.inputs).reason_codes == codes("evidence_serialization_failed")
    for inputs in (None, replace(item.inputs, decision_id="")):
        verification = verify(item.decision, inputs)
        assert (verification.reason_codes, verification.recomputed_digest) == (
            codes("evidence_reconstruction_failed"),
            "",
        )


def test_a_decision_is_immutable_deterministic_and_its_mapping_fresh() -> None:
    item = walk(0)
    with pytest.raises(FrozenInstanceError):
        item.decision.transition = HOLD  # type: ignore[misc]
    mapping = paper_sleeve_promotion_demotion_decision_to_dict(item.decision)
    mapping["transition"] = "HOLD"
    assert paper_sleeve_promotion_demotion_decision_to_dict(item.decision)["transition"] == "PROMOTE"
    assert decide(item.inputs) == item.decision


@pytest.mark.parametrize(
    ("overrides", "name"),
    [
        ({"decision_id": _Text("rg6-test-decision")}, "decision_id_invalid"),
        ({"decision_id": ""}, "decision_id_invalid"),
        ({"decision_id": "live-decision"}, "forbidden_scope_token:decision_id"),
        ({"correlation_id": "bist-corr"}, "bist_scope_leakage:correlation_id"),
        ({"correlation_id": 5}, "correlation_id_invalid"),
        ({"evaluation_end_ns": True}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": -DAY}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": INT64_MAX + 1}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": float(END)}, "evaluation_end_ns_invalid"),
        ({"evaluation_end_ns": END + 1}, "evaluation_end_ns_not_utc_day_aligned"),
    ],
)
def test_decision_scalars_are_exact(overrides: dict[str, object], name: str) -> None:
    with raises(name):
        decide(inputs_for(human_seed(), shared_evidence(), **overrides))


def test_inputs_are_an_exact_record() -> None:
    for value in (None, {"decision_id": "rg6-test-decision", "ladder_state": human_seed()}):
        with raises("inputs_malformed"):
            decide(value)


@pytest.mark.parametrize(
    ("reader", "value", "name"),
    [
        ("decimal", "1.80931453070937285", "x"),
        ("decimal", "01.809314530709372854", "x"),
        ("decimal", "-0.000000000000000000", "x"),
        ("decimal", "+1.000000000000000000", "x"),
        ("decimal", "1e+00", "x"),
        ("decimal", "１.000000000000000000", "x"),
        ("decimal", "9" * 90 + ".000000000000000000", "x"),
        ("decimal", Fraction(1), "x"),
        ("distance", "2/4", "drawdown_peak_distance_invalid"),
        ("distance", "1/1", "drawdown_peak_distance_invalid"),
        ("distance", "0/3", "drawdown_peak_distance_invalid"),
        ("distance", "01/3", "drawdown_peak_distance_invalid"),
        ("distance", "1/03", "drawdown_peak_distance_invalid"),
        ("distance", "1/0", "drawdown_peak_distance_invalid"),
        ("distance", "-1/3", "drawdown_peak_distance_invalid"),
        ("distance", "1", "drawdown_peak_distance_invalid"),
        ("distance", "1/" + "7" * 4097, "drawdown_peak_distance_invalid"),
        ("distance", Fraction(1, 3), "drawdown_peak_distance_invalid"),
    ],
)
def test_consumed_metric_texts_are_exact(reader: str, value: object, name: str) -> None:
    with raises(name):
        rg6._decimal_fraction(value, name) if reader == "decimal" else rg6._peak_distance_fraction(value)


def test_consumed_metric_texts_read_exactly() -> None:
    assert rg6._decimal_fraction("-3.000000000000000007", "x") == Fraction(-3_000_000_000_000_000_007, 10**18)
    assert rg6._decimal_fraction("0.000000000000000000", "x") == 0
    assert rg6._decimal_fraction("9" * 81 + ".000000000000000000", "x") == 10**81 - 1
    assert (rg6._peak_distance_fraction("0/1"), rg6._peak_distance_fraction("2/7")) == (0, Fraction(2, 7))
    big = "9" * 4095 + "8"
    assert rg6._peak_distance_fraction(f"1/{big}") == Fraction(1, int(big))


@pytest.mark.parametrize(
    ("guard", "forge", "name"),
    [
        ("seed", lambda seed: replace(seed, initial_tier=STANDARD), "ladder_seed_initial_tier_not_probation"),
        ("seed", lambda seed: replace(seed, rule_set_digest="0" * 64), "ladder_seed_rule_set_unsupported"),
        ("seed", lambda seed: replace(seed, sleeve_id="sleeve-gamma"), "ladder_seed_sleeve_not_declared_by_envelope"),
        ("seed", lambda seed: replace(seed, tier_entered_at_ns=W0 + 3), "tier_tenure_not_whole_utc_days"),
        ("prior", lambda decision: replace(decision, rule_set_digest="0" * 64), "prior_decision_rule_set_unsupported"),
        ("prior", lambda decision: replace(decision, resulting_tier=None), "prior_decision_resulting_state_invalid"),
    ],
)
def test_defense_in_depth_guards_fail_closed_on_forged_state(
    monkeypatch: pytest.MonkeyPatch, guard: str, forge, name: str
) -> None:
    if guard == "seed":
        seed, evidence = human_seed(), shared_evidence()
        monkeypatch.setattr(
            rg6, "verify_paper_sleeve_ladder_seed", lambda value: EdgeEvidenceVerification(True, (), "", "")
        )
        inputs = inputs_for(forge(seed), evidence)
    else:
        item, later = genesis(), later_shared_evidence()
        forged = forge(item.decision)
        # A forged lineage proof hands the assembly a predecessor that no reconstruction could produce.
        monkeypatch.setattr(rg6, "_proven_predecessor", lambda state: forged)
        inputs = inputs_for(item.node(), later)
    with raises(name):
        decide(inputs)


def test_a_rebuilt_rg3_sleeve_the_envelope_does_not_declare_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    evidence, seed = shared_evidence(), human_seed()
    forged = replace(evidence.target.evidence, sleeve_id="sleeve-gamma")
    monkeypatch.setattr(rg6, "build_paper_sleeve_performance_evidence", lambda inputs: forged)
    with raises("performance_sleeve_not_declared_by_envelope"):
        decide(inputs_for(seed, evidence, performance_evidence=forged))


def test_a_seed_of_another_envelope_is_refused() -> None:
    with raises("ladder_seed_envelope_mismatch"):
        decide(inputs_for(human_seed(walk_envelope()), shared_evidence()))


# --- Q. design authority and static discipline ----------------------------------------------------------------------


def test_the_design_records_the_rg6_contract() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("5. **RG-6 `paper_sleeve_promotion_demotion_decision.py`**")
    item = " ".join(text[start : text.index("6. **RG-7", start)].split())
    for phrase in (
        "RG6_LADDER_STATE_LINEAGE_AND_DRAWDOWN_CONSUMPTION_POLICY_V1",
        "RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1",
        "governed ladder seed whose tier is always PROBATION",
        "exact HUMAN_GOVERNANCE approval",
        "walked back to the seed iteratively",
        "each ancestor is rebuilt once, oldest first, on the same assembly path as the current decision",
        "there is no depth cap, checkpoint or trusted prefix",
        "`current_ladder_head_proven` is structurally False",
        "exact number of UTC days",
        "RG-3 `paper_sharpe_annualized`",
        "RG-6 owns how ladder thresholds consume RG-4 sleeve drawdown evidence",
        "RG-4 `max_peak_distance` for promotion and demotion alike (`MAX_PEAK_DISTANCE`)",
        "its cap is never evaluated",
        "STANDARD evaluates demotion first and evaluates promotion only when no demotion breach applies",
        "at most one adjacent transition per record",
        "pending and unevaluated until the RF chain merges",
        "decides no allocation, cap breach, diversification credit, kill or quarantine, portfolio stop or execution",
        "chooses no production number",
    ):
        assert phrase in item, phrase


def test_the_module_is_pure_and_consumes_only_its_reproven_inputs() -> None:
    pit.assert_module_is_pure(
        rg6,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_sleeve_correlation_evidence",
            "crypto_core.validation.paper_sleeve_drawdown_evidence",
            "crypto_core.validation.paper_sleeve_performance_evidence",
        },
    )


def test_one_construction_site_and_one_assembly_path() -> None:
    pit.assert_single_assembly_path(
        rg6, "PaperSleeveLadderSeed", "_assemble_seed", "build_paper_sleeve_ladder_seed", "_reassemble_seed"
    )
    tree = ast.parse(Path(rg6.__file__).read_text(encoding="utf-8"))
    calls = {
        function.name: [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        for function in tree.body
        if isinstance(function, ast.FunctionDef)
    }

    def callers(name: str) -> list[str]:
        return sorted(caller for caller, called in calls.items() for _ in range(called.count(name)))

    assert callers("PaperSleevePromotionDemotionDecision") == ["_assemble_decision"]
    assert callers("_move") == ["_assemble_decision"]
    assert callers("_assemble_decision") == ["_proven_predecessor", "build_paper_sleeve_promotion_demotion_decision"]
    assert callers("build_paper_sleeve_promotion_demotion_decision") == [
        "verify_paper_sleeve_promotion_demotion_decision"
    ]


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(rg6)
    # Text, identifier and wire bounds, the ladder size, the decimal base and scale, the RG-4 digit bound and the day.
    assert integers <= {0, 1, 2, 10, 18, 32, 100, 127, 128, 256, 4096, world.DAY_NS, INT64_MAX}
    assert decimals <= {"0", "9"}
    for record in (PaperSleeveLadderSeedApproval, PaperSleevePromotionDemotionInputs, PaperSleeveLadderPriorDecision):
        assert all(item.default is dataclasses.MISSING for item in fields(record))
    for record, flags in (
        (PaperSleeveLadderSeed, dict(PAPER_SLEEVE_LADDER_SEED_NON_CLAIM_FLAGS)),
        (PaperSleevePromotionDemotionDecision, dict(PAPER_SLEEVE_PROMOTION_DEMOTION_NON_CLAIM_FLAGS)),
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record) if item.name not in flags)


def test_the_rule_set_is_committed_and_handed_out_fresh() -> None:
    rule_set = paper_sleeve_promotion_demotion_rule_set()
    assert rg6.edge_sha256_text(rg6.edge_canonical_json(rule_set)) == PAPER_SLEEVE_PROMOTION_DEMOTION_RULE_SET_DIGEST
    assert (rule_set["genesis_tier"], rule_set["drawdown_consumption"], rule_set["lineage_architecture_id"]) == (
        "PROBATION",
        "MAX_PEAK_DISTANCE",
        "RG6_ROOT_CAUSE_ESCAPE_ITERATIVE_LINEAGE_PORTABLE_VALIDATION_V1",
    )
    rule_set["genesis_tier"] = "EXPANDED"
    assert paper_sleeve_promotion_demotion_rule_set()["genesis_tier"] == "PROBATION"


def test_the_public_api_is_exact_and_offers_no_head_lookup() -> None:
    assert set(rg6.__all__) == {
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
    assert all(hasattr(rg6, name) for name in rg6.__all__)
    assert not [name for name in rg6.__all__ if re.search("head|latest|registry|current", name, re.IGNORECASE)]
