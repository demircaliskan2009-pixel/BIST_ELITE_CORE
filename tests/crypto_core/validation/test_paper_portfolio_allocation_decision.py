"""Tests for the RG-7 paper portfolio allocation decision (RG7_PAPER_PORTFOLIO_ALLOCATION_DECISION_V1).

Fixtures are REAL authenticated upstream artifacts:

* EF-7/EF-8: the EF-8 test module's cached lifecycle of ``carry-sleeve-1`` (ACTIVE genesis on day 635, DISABLED on day
  636, QUARANTINE 31 days later and re-admitted to a NEW cycle 14 days after that). For portfolios, governed EF-7 PASS
  admissions of the same authentic EF-6 chain into the RG-3 world sleeves ``sleeve-alpha`` and ``sleeve-beta`` (the
  paper sleeve is an EF-7 caller input), each with its own EF-8 genesis, plus a disable of ``sleeve-beta``;
* RG-5: either the genuine OBSERVED (alpha, beta) pair of the RG-5 worlds, rebuilt on each envelope, or the complete
  WORST_CASE_UNKNOWN matrix of an evidence that supplies no sleeve;
* risk budgets: real paper trade ticks recorded into real sleeve states and evaluated by the accepted intra-sleeve
  layer under each admission's own budget policy.

Every approval, cap, budget and coordinate below is a SYNTHETIC TEST VALUE: RG-7 holds no production number.

The EF-6, EF-7, EF-8 and RG test modules are imported under the module names pytest collects them with (basename
import), so their cached worlds and memos are one object shared with their own tests.

Cost control: as in the EF-7 and EF-8 tests, the pure public upstream verifiers are memoized at their call sites with
the EF-6 module's exact memo, and so are RG-7's own references to the EF-7 and EF-8 verifiers. A memo only returns the
result of an identical earlier real call: a tampered or forged object is always a miss and is verified for real. A
slow test rebuilds and re-verifies a READY portfolio with every memo disabled.
"""

from __future__ import annotations

import ast
import dataclasses
import functools
import json
import re
from collections.abc import Callable
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.edge_kill_quarantine_decision as ef8_module
import crypto_core.validation.edge_paper_admission_decision as ef7_module
import crypto_core.validation.paper_portfolio_allocation_decision as rg7
from crypto_core.audit.evidence_journal import EvidenceArtifactType, EvidenceJournal
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_REGIME_LABEL_BINDING_PENDING,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_kill_quarantine_decision import (
    EdgeKillQuarantineDecision,
    EdgeLifecycleState,
    edge_kill_quarantine_decision_digest,
)
from crypto_core.validation.edge_paper_admission_decision import (
    EdgePaperAdmissionDecision,
    edge_paper_admission_decision_digest,
)
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS,
    PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS,
    PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST,
    PaperAllocationMarketBinding,
    PaperAllocationPairExposure,
    PaperGovernedLifecycleState,
    PaperLifecycleHeadAuthority,
    PaperLifecycleHeadAuthorityApproval,
    PaperLifecycleHeadAuthorityApprovalKind,
    PaperLifecycleHeadAuthorityInputs,
    PaperPortfolioAllocationDecision,
    PaperPortfolioAllocationError,
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationSleeveInputs,
    PaperPortfolioAllocationStatus,
    build_paper_lifecycle_head_authority,
    build_paper_portfolio_allocation_decision,
    paper_lifecycle_head_authority_digest,
    paper_lifecycle_head_authority_to_dict,
    paper_portfolio_allocation_decision_digest,
    paper_portfolio_allocation_decision_to_dict,
    paper_portfolio_allocation_rule_set,
    verify_paper_lifecycle_head_authority,
    verify_paper_portfolio_allocation_decision,
)
from crypto_core.validation.paper_portfolio_risk_envelope import PaperPortfolioRiskEnvelope
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationEvidence,
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationSleeveInputs,
    build_paper_sleeve_correlation_evidence,
    paper_sleeve_correlation_evidence_digest,
)
from crypto_core.validation.paper_sleeve_intent_ledger import (
    PaperSleeveState,
    apply_paper_trade_tick_to_sleeve_state,
    build_initial_paper_sleeve_state,
)
from crypto_core.validation.paper_sleeve_risk_budget_decision import (
    PaperSleeveRiskBudgetDecision,
    PaperSleeveRiskBudgetPolicy,
    build_paper_sleeve_risk_budget_policy,
    evaluate_paper_sleeve_risk_budget,
    paper_sleeve_risk_budget_decision_digest,
)
from crypto_core.validation.paper_trade_tick import build_paper_trade_tick, paper_trade_tick_to_dict
from tests.crypto_core.validation import test_historical_pit_dataset as pit

try:  # the module objects pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_kill_quarantine_decision as ef8t
    import test_edge_paper_admission_decision as ef7t
    import test_edge_walk_forward_oos_evidence as ef6t
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_drawdown_evidence as rg4t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_kill_quarantine_decision as ef8t
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t

_PREFIX = "paper_portfolio_allocation_decision"
_AUTHORITY_PREFIX = "paper_lifecycle_head_authority"
_UNSET = object()
SLOW = pytest.mark.slow  # a memo-free re-proof of a whole READY portfolio; see the module docstring
DESIGN = Path(__file__).resolve().parents[3] / "docs" / "crypto_core" / "multi_sleeve_risk_governance_design.md"
SOURCE = Path(rg7.__file__).read_text(encoding="utf-8")
HUMAN = PaperLifecycleHeadAuthorityApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = PaperLifecycleHeadAuthorityApprovalKind.TEST_ONLY_SYNTHETIC
READY = PaperPortfolioAllocationStatus.READY
REJECTED = PaperPortfolioAllocationStatus.ALLOCATION_REJECTED
NEEDS_GOVERNANCE = PaperPortfolioAllocationStatus.NEEDS_GOVERNANCE_APPROVAL
ACTIVE = PaperGovernedLifecycleState.ACTIVE
DISABLED = PaperGovernedLifecycleState.DISABLED
QUARANTINE = PaperGovernedLifecycleState.QUARANTINE
UNPROVEN = PaperGovernedLifecycleState.UNPROVEN
BOUND = PaperAllocationMarketBinding.BOUND
UNBOUND = PaperAllocationMarketBinding.UNBOUND
NOT_EXPOSED = PaperAllocationMarketBinding.NOT_EXPOSED
NOT_EVALUATED = PaperAllocationMarketBinding.NOT_EVALUATED
WITHIN = PaperAllocationPairExposure.WITHIN_CAP
BREACH = PaperAllocationPairExposure.BREACH
PAIR_NOT_EXPOSED = PaperAllocationPairExposure.NOT_EXPOSED
CARRY, ALPHA, BETA = ef7t.SLEEVE, rg4t.ALPHA, rg4t.BETA
INS = ef7t.INS  # the authentic EF-7 pinned universe is exactly (INS,)
PERP_BTC, PERP_ETH = "BTC-PERPETUAL", "ETH-PERPETUAL"  # RG-3 world markets: declared, outside the EF-7 universe
UNLISTED = "SOL-USDT-PERP"
END, DAY = world.WINDOW_END, world.DAY_NS
UNKNOWN = "1.000000000000000000"
INT64_MAX = 9223372036854775807
# SYNTHETIC TEST VALUES: (instrument, quantity, limit price) of each recorded paper intent.
ROWS: dict[str, tuple[tuple[str, str, str], ...]] = {
    CARRY: ((INS, "2", "30"), (INS, "1", "15.5")),
    ALPHA: ((INS, "2", "30"), (INS, "1", "15.5")),
    BETA: ((INS, "1", "40"),),
}
# A reservation that would breach every cap of the kill-override test if it were ever counted.
WHALE = tuple((INS, "1", "99.77") for _ in range(9)) + ((UNLISTED, "1", "77.77"),)
MARKETS = ((INS, "600"), (PERP_BTC, "600"), (PERP_ETH, "500"))

# --- memoized re-proof of upstream artifacts (see module docstring) ---------------------------------------------------


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
        yield


# --- codes and reseals ------------------------------------------------------------------------------------------------


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def authority_code(text: str) -> str:
    return f"{_AUTHORITY_PREFIX}:{text}"


def refused(text: str):
    """``pytest.raises`` for one exact RG-7 decision construction error."""

    return pytest.raises(PaperPortfolioAllocationError, match=f"^{re.escape(code(text))}$")


def refused_authority(text: str):
    """``pytest.raises`` for one exact current-head authority construction error."""

    return pytest.raises(PaperPortfolioAllocationError, match=f"^{re.escape(authority_code(text))}$")


def _resealed(
    artifact: object, digest_field: str, digest: Callable[[object], str], changes: dict[str, object]
) -> object:
    changed = replace(artifact, **changes)  # type: ignore[type-var]
    return replace(changed, **{digest_field: digest(changed)})


def reseal_head(head: EdgeKillQuarantineDecision, **changes: object) -> EdgeKillQuarantineDecision:
    return _resealed(head, "kill_quarantine_decision_digest", edge_kill_quarantine_decision_digest, changes)  # type: ignore[return-value,arg-type]


def reseal_admission(admission: EdgePaperAdmissionDecision, **changes: object) -> EdgePaperAdmissionDecision:
    return _resealed(admission, "paper_admission_decision_digest", edge_paper_admission_decision_digest, changes)  # type: ignore[return-value,arg-type]


def reseal_budget(decision: PaperSleeveRiskBudgetDecision, **changes: object) -> PaperSleeveRiskBudgetDecision:
    return _resealed(decision, "decision_digest", paper_sleeve_risk_budget_decision_digest, changes)  # type: ignore[return-value,arg-type]


def reseal_correlation(evidence: PaperSleeveCorrelationEvidence, **changes: object) -> PaperSleeveCorrelationEvidence:
    return _resealed(evidence, "correlation_evidence_digest", paper_sleeve_correlation_evidence_digest, changes)  # type: ignore[return-value,arg-type]


def reseal_authority(authority: PaperLifecycleHeadAuthority, **changes: object) -> PaperLifecycleHeadAuthority:
    return _resealed(authority, "authority_digest", paper_lifecycle_head_authority_digest, changes)  # type: ignore[return-value,arg-type]


def reseal_decision(decision: PaperPortfolioAllocationDecision, **changes: object) -> PaperPortfolioAllocationDecision:
    return _resealed(decision, "allocation_decision_digest", paper_portfolio_allocation_decision_digest, changes)  # type: ignore[return-value,arg-type]


def shifted(text: str, units: int) -> str:
    """A scale-18 decimal text moved by ``units`` units in its last place."""

    value = (Fraction(text) + Fraction(units, 10**18)) * 10**18
    assert value.denominator == 1
    sign, units_total = ("-" if value < 0 else ""), abs(value.numerator)
    return f"{sign}{units_total // 10**18}.{units_total % 10**18:018d}"


# --- authentic upstream worlds ----------------------------------------------------------------------------------------


@functools.cache
def admission_for(sleeve_id: str) -> EdgePaperAdmissionDecision:
    """A governed EF-7 PASS admitting the authentic EF-6 chain into ``sleeve_id`` under that sleeve's budget policy."""

    if sleeve_id == CARRY:
        return ef7t.admitted()
    policy = ef7t.budget_policy(sleeve_id)
    arguments = {
        "paper_sleeve_id": sleeve_id,
        "risk_budget_policy": policy,
        "expected_risk_budget_policy_digest": policy.policy_digest,
        "decision_id": f"ef7-{sleeve_id}",
    }
    draft = ef7t.decide(ef6t.passed(), **arguments)
    return ef7t.decide(ef6t.passed(), **arguments, governance=ef7t.approval_for(draft))


@functools.cache
def head_of(sleeve_id: str, lifecycle: str = "genesis") -> EdgeKillQuarantineDecision:
    """An authentic advancing EF-8 receipt: CARRY's whole lifecycle, or an alpha/beta genesis and a beta disable."""

    if sleeve_id == CARRY:
        return getattr(ef8t, lifecycle)()
    if lifecycle == "genesis":
        return ef8t.activate(admission_for(sleeve_id), decision_id=f"ef8-activate-{sleeve_id}")
    assert lifecycle == "disabled"
    return ef8t.disable(head_of(sleeve_id), decision_id=f"ef8-disable-{sleeve_id}")


def admission_of(sleeve_id: str, lifecycle: str = "genesis") -> EdgePaperAdmissionDecision:
    """The EF-7 that opened the head's current cycle."""

    if sleeve_id == CARRY and lifecycle == "readmitted":
        return ef8t.revalidation()
    return admission_for(sleeve_id)


@functools.cache
def budget_of(
    sleeve_id: str, rows: tuple[tuple[str, str, str], ...]
) -> tuple[PaperSleeveState, PaperSleeveRiskBudgetPolicy, PaperSleeveRiskBudgetDecision]:
    """A real sleeve state of journal-bound paper intents and its accepted risk-budget decision."""

    policy = ef7t.budget_policy(sleeve_id)
    state = build_initial_paper_sleeve_state(sleeve_id=sleeve_id, correlation_id="corr:rg7-sleeve")
    for index, (instrument, quantity, price) in enumerate(rows):
        tick = build_paper_trade_tick(
            tick_id=f"{sleeve_id}-tick-{index}",
            action="BUY",
            intent_type="LIMIT",
            instrument_id=instrument,
            quantity=quantity,
            strategy_id="rg7-strategy",
            run_plan_id="rg7-run",
            upstream_report_digest="f" * 64,
            correlation_id="corr:rg7-tick",
            limit_price=price,
        )
        entry = EvidenceJournal().append(
            EvidenceArtifactType.PAPER_TRADE_TICK, paper_trade_tick_to_dict(tick), correlation_id="corr:rg7-journal"
        )
        state = apply_paper_trade_tick_to_sleeve_state(
            state, tick, correlation_id=f"corr:rg7-apply-{index}", journal_entry=entry
        ).to_state
    decision = evaluate_paper_sleeve_risk_budget(
        state, policy, correlation_id=f"rg7-budget-{sleeve_id}", metadata={"review": "synthetic-test-value"}
    )
    return state, policy, decision


def approval_for(
    inputs: PaperLifecycleHeadAuthorityInputs, *, kind: object = HUMAN, **overrides: object
) -> PaperLifecycleHeadAuthorityApproval:
    """SYNTHETIC TEST VALUES: the exact commitments a human reviews before attesting one paper current head."""

    draft = build_paper_lifecycle_head_authority(replace(inputs, approval=None))
    values: dict[str, object] = {
        "approval_reference": "synthetic-head-attestation-1",
        "approval_digest": "c" * 64,
        "approval_kind": kind,
        "approved_authority_id": draft.authority_id,
        "approved_authority_version": draft.authority_version,
        "approved_authority_policy_digest": draft.authority_policy_digest,
        "approved_rule_set_digest": draft.rule_set_digest,
    }
    values.update(overrides)
    return PaperLifecycleHeadAuthorityApproval(**values)  # type: ignore[arg-type]


def head_inputs(
    head: EdgeKillQuarantineDecision, *, approval: object = _UNSET, **overrides: object
) -> PaperLifecycleHeadAuthorityInputs:
    """Authority inputs declaring the receipt's own anchors; an exact human approval unless ``approval`` is given."""

    values: dict[str, object] = {
        "authority_id": f"rg7-head-{head.paper_sleeve_id}",
        "authority_version": "synthetic-v1",
        "sleeve_id": head.paper_sleeve_id,
        "lifecycle_head_digest": head.kill_quarantine_decision_digest,
        "lifecycle_subject_digest": head.lifecycle_subject_digest,
        "current_cycle_admission_decision_digest": head.cycle_admission_decision_digest,
        "evaluation_end_ns": END,
        "lifecycle_head": head,
        "approval": None,
    }
    values.update(overrides)
    inputs = PaperLifecycleHeadAuthorityInputs(**values)  # type: ignore[arg-type]
    return replace(inputs, approval=approval_for(inputs) if approval is _UNSET else approval)


def subject(
    sleeve_id: str,
    lifecycle: str = "genesis",
    *,
    rows: tuple[tuple[str, str, str], ...] | None = None,
    approval: object = _UNSET,
    **overrides: object,
) -> PaperPortfolioAllocationSleeveInputs:
    """One sleeve's single allocation subject over authentic EF-7, EF-8 and risk-budget artifacts."""

    authority_inputs = head_inputs(head_of(sleeve_id, lifecycle), approval=approval)
    state, policy, decision = budget_of(sleeve_id, ROWS[sleeve_id] if rows is None else rows)
    values: dict[str, object] = {
        "sleeve_id": sleeve_id,
        "paper_admission": admission_of(sleeve_id, lifecycle),
        "lifecycle_head_authority_inputs": authority_inputs,
        "lifecycle_head_authority": build_paper_lifecycle_head_authority(authority_inputs),
        "risk_budget_state": state,
        "risk_budget_policy": policy,
        "risk_budget_decision": decision,
    }
    values.update(overrides)
    return PaperPortfolioAllocationSleeveInputs(**values)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def envelope(
    sleeves: tuple[tuple[str, str], ...] = ((ALPHA, "400"), (BETA, "300")),
    *,
    total: str = "1000",
    markets: tuple[tuple[str, str], ...] = MARKETS,
    max_count: int | None = None,
    cap: str = "0.6",
    governed: bool = True,
    ladder: tuple[object, ...] | None = None,
) -> PaperPortfolioRiskEnvelope:
    """A SYNTHETIC RG-2 envelope; it declares the RG-3 world markets so genuine RG-5 evidence can bind it."""

    overrides: dict[str, object] = {
        "total_paper_risk_budget": rg2.d(total),
        "sleeve_caps": [rg2.sleeve(sleeve_id, sleeve_cap) for sleeve_id, sleeve_cap in sleeves],
        "market_caps": [rg2.market(market, market_cap) for market, market_cap in markets],
        "max_sleeve_count": len(sleeves) if max_count is None else max_count,
        "correlation_cap": rg2.correlation(cap, 30, 20),
    }
    if ladder is not None:
        overrides["ladder_boundaries"] = list(ladder)
    if governed:
        return rg2.governed(**overrides)
    return rg2.build(approval=rg2.approval_for(rg2.build(**overrides), kind=rg2.SYNTHETIC), **overrides)


def solo_envelope(cap: str = "400", **options: object) -> PaperPortfolioRiskEnvelope:
    return envelope(((CARRY, cap),), **options)  # type: ignore[arg-type]


def caps_envelope(
    *,
    total: str = "1000",
    alpha: str = "400",
    beta: str = "300",
    ins: str = "600",
    count: int | None = None,
    cap: str = "0.6",
    ladder: tuple[object, ...] | None = None,
) -> PaperPortfolioRiskEnvelope:
    return envelope(
        ((ALPHA, alpha), (BETA, beta)),
        total=total,
        markets=((INS, ins), (PERP_BTC, "50"), (PERP_ETH, "50")),
        max_count=count,
        cap=cap,
        ladder=ladder,
    )


@functools.lru_cache(maxsize=None)
def correlation_of(
    env: PaperPortfolioRiskEnvelope, observed: bool
) -> tuple[PaperSleeveCorrelationInputs, PaperSleeveCorrelationEvidence]:
    """Genuine RG-5 on ``env``: the observed (alpha, beta) worlds, or no sleeve evidence (every pair worst case)."""

    sleeves: tuple[PaperSleeveCorrelationSleeveInputs, ...] = ()
    if observed:
        sleeves = tuple(
            PaperSleeveCorrelationSleeveInputs(item.inputs, item.evidence)
            for item in (rg4t.sleeve_world(sleeve_id, env) for sleeve_id in (ALPHA, BETA))
        )
    inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id="rg5-for-rg7",
        correlation_id="corr-rg5",
        portfolio_risk_envelope=env,
        evaluation_end_ns=END,
        sleeves=sleeves,
    )
    return inputs, build_paper_sleeve_correlation_evidence(inputs)


def allocation(
    env: PaperPortfolioRiskEnvelope,
    *subjects: PaperPortfolioAllocationSleeveInputs,
    observed: bool = False,
    **overrides: object,
) -> PaperPortfolioAllocationInputs:
    correlation_inputs, correlation_evidence = correlation_of(env, observed)
    values: dict[str, object] = {
        "allocation_id": "rg7-allocation-1",
        "correlation_id": "corr-rg7",
        "portfolio_risk_envelope": env,
        "evaluation_end_ns": END,
        "sleeves": subjects,
        "correlation_inputs": correlation_inputs,
        "correlation_evidence": correlation_evidence,
    }
    values.update(overrides)
    return PaperPortfolioAllocationInputs(**values)  # type: ignore[arg-type]


def build(inputs: object) -> PaperPortfolioAllocationDecision:
    return build_paper_portfolio_allocation_decision(inputs)  # type: ignore[arg-type]


def decide(inputs: PaperPortfolioAllocationInputs) -> PaperPortfolioAllocationDecision:
    """Build, then re-prove by reconstruction: every decision a test reads is intact."""

    decision = build(inputs)
    verification = verify_paper_portfolio_allocation_decision(decision, inputs)
    assert verification.intact, verification.reason_codes
    assert verification.recomputed_digest == decision.allocation_decision_digest
    return decision


def solo(lifecycle: str = "genesis", **subject_options: object) -> PaperPortfolioAllocationInputs:
    return allocation(solo_envelope(), subject(CARRY, lifecycle, **subject_options))  # type: ignore[arg-type]


def portfolio_decision(env: PaperPortfolioRiskEnvelope) -> PaperPortfolioAllocationDecision:
    """ALPHA (75.5) and BETA (40) ACTIVE on ``env`` with their genuine OBSERVED correlation."""

    return decide(allocation(env, subject(ALPHA), subject(BETA), observed=True))


@functools.cache
def ready_portfolio() -> tuple[PaperPortfolioAllocationInputs, PaperPortfolioAllocationDecision]:
    inputs = allocation(caps_envelope(), subject(ALPHA), subject(BETA), observed=True)
    return inputs, decide(inputs)


def amounts(sleeve: object) -> tuple[str, str, str]:
    return sleeve.pre_kill_requested_budget, sleeve.post_kill_requested_budget, sleeve.final_allocated_budget  # type: ignore[attr-defined]


# --- A. the governed paper current-head authority ---------------------------------------------------------------------


def test_a_human_attestation_establishes_the_paper_current_head_and_binds_every_fact() -> None:
    head = head_of(CARRY)
    inputs = head_inputs(head)
    authority = build_paper_lifecycle_head_authority(inputs)
    assert (authority.gate_verdict, authority.advances, authority.paper_current_head_attested) == (
        EdgeGateVerdict.PASS,
        True,
        True,
    )
    assert (authority.verdict_reason_codes, authority.synthetic_test_approval_used) == ((), False)
    assert (authority.authority_id, authority.authority_version) == (f"rg7-head-{CARRY}", "synthetic-v1")
    assert (authority.sleeve_id, authority.evaluation_end_ns) == (CARRY, END)
    assert authority.lifecycle_head_digest == edge_kill_quarantine_decision_digest(head)
    assert authority.lifecycle_subject_digest == head.lifecycle_subject_digest
    assert authority.current_cycle_admission_decision_digest == ef7t.admitted().paper_admission_decision_digest
    assert authority.resulting_lifecycle_state is EdgeLifecycleState.ACTIVE
    assert authority.lifecycle_head_effective_at_ns == head.effective_at_ns < END
    assert authority.rule_set_digest == PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST
    assert authority.approval == inputs.approval
    for name, value in PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS:
        assert getattr(authority, name) is value, name
    # EF-8 is untouched: the receipt itself still claims no current head and no paper admission.
    assert (head.current_lifecycle_head_proven, head.candidate_admitted_to_paper) == (False, False)
    verification = verify_paper_lifecycle_head_authority(authority, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert (
        verification.recomputed_digest == authority.authority_digest == paper_lifecycle_head_authority_digest(authority)
    )
    assert json.loads(verification.canonical_json) == paper_lifecycle_head_authority_to_dict(authority)


def test_the_authority_policy_commits_every_fact_but_its_governance() -> None:
    inputs = head_inputs(head_of(CARRY), approval=None)
    draft = build_paper_lifecycle_head_authority(inputs)
    attested = build_paper_lifecycle_head_authority(replace(inputs, approval=approval_for(inputs)))
    assert draft.authority_policy_digest == attested.authority_policy_digest
    assert draft.authority_digest != attested.authority_digest
    later = build_paper_lifecycle_head_authority(replace(inputs, evaluation_end_ns=END + DAY))
    assert later.authority_policy_digest != draft.authority_policy_digest
    assert build_paper_lifecycle_head_authority(inputs) == draft


def test_a_missing_approval_needs_governance_and_never_attests() -> None:
    authority = build_paper_lifecycle_head_authority(head_inputs(head_of(CARRY), approval=None))
    assert (authority.gate_verdict, authority.advances, authority.paper_current_head_attested) == (
        EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL,
        False,
        False,
    )
    assert authority.verdict_reason_codes == (authority_code("governance_approval_missing"),)


def test_a_test_only_synthetic_approval_never_attests() -> None:
    inputs = head_inputs(head_of(CARRY), approval=None)
    authority = build_paper_lifecycle_head_authority(replace(inputs, approval=approval_for(inputs, kind=SYNTHETIC)))
    assert (authority.paper_current_head_attested, authority.synthetic_test_approval_used) == (False, True)
    assert authority.verdict_reason_codes == (authority_code("governance_approval_test_only_synthetic"),)


@pytest.mark.parametrize("name", ["authority_id", "authority_version", "authority_policy_digest", "rule_set_digest"])
def test_each_approval_commitment_must_match_exactly(name: str) -> None:
    inputs = head_inputs(head_of(CARRY), approval=None)
    wrong = "0" * 64 if name.endswith("digest") else "rg7-other"
    authority = build_paper_lifecycle_head_authority(
        replace(inputs, approval=approval_for(inputs, **{f"approved_{name}": wrong}))
    )
    assert authority.paper_current_head_attested is False
    assert authority.verdict_reason_codes == (authority_code(f"governance_approval_{name}_mismatch"),)


def test_an_attestation_of_another_head_or_evaluation_end_is_stale() -> None:
    genesis = head_inputs(head_of(CARRY))
    stale_head = build_paper_lifecycle_head_authority(
        head_inputs(head_of(CARRY, "disabled"), approval=genesis.approval)
    )
    earlier = head_inputs(head_of(CARRY), evaluation_end_ns=END - DAY)
    stale_end = build_paper_lifecycle_head_authority(replace(earlier, evaluation_end_ns=END))
    for authority in (stale_head, stale_end):
        assert authority.paper_current_head_attested is False
        assert authority.verdict_reason_codes == (
            authority_code("governance_approval_authority_policy_digest_mismatch"),
        )


@pytest.mark.parametrize(
    "lifecycle, state",
    [
        ("disabled", EdgeLifecycleState.DISABLED),
        ("quarantined", EdgeLifecycleState.QUARANTINE),
        ("readmitted", EdgeLifecycleState.ACTIVE),
    ],
)
def test_every_advancing_lifecycle_state_can_be_attested_as_a_paper_snapshot(
    lifecycle: str, state: EdgeLifecycleState
) -> None:
    head = head_of(CARRY, lifecycle)
    authority = build_paper_lifecycle_head_authority(head_inputs(head))
    assert (authority.paper_current_head_attested, authority.resulting_lifecycle_state) == (True, state)
    assert authority.lifecycle_head_effective_at_ns == head.effective_at_ns
    assert (
        authority.current_cycle_admission_decision_digest
        == admission_of(CARRY, lifecycle).paper_admission_decision_digest
    )
    assert (authority.global_current_lifecycle_head_proven, authority.live_current_lifecycle_head_proven) == (
        False,
        False,
    )
    assert head.current_lifecycle_head_proven is False


def test_a_forged_receipt_is_never_a_head() -> None:
    forged = reseal_head(head_of(CARRY, "disabled"), resulting_lifecycle_state=EdgeLifecycleState.ACTIVE)
    with refused_authority("lifecycle_head_not_intact"):
        build_paper_lifecycle_head_authority(head_inputs(forged, approval=None))


@pytest.mark.parametrize("receipt", [ef8t.cheap_genesis, ef8t.readmission_draft], ids=["fail", "needs_governance"])
def test_a_non_advancing_receipt_is_never_a_head(receipt: Callable[[], EdgeKillQuarantineDecision]) -> None:
    with refused_authority("lifecycle_head_not_advancing"):
        build_paper_lifecycle_head_authority(
            head_inputs(receipt(), approval=None, current_cycle_admission_decision_digest="0" * 64)
        )


@pytest.mark.parametrize(
    "anchor, reason",
    [
        ("lifecycle_head_digest", "lifecycle_head_digest_mismatch"),
        ("lifecycle_subject_digest", "lifecycle_head_subject_mismatch"),
        ("current_cycle_admission_decision_digest", "lifecycle_head_current_cycle_admission_mismatch"),
    ],
)
def test_every_declared_anchor_must_equal_the_reproven_receipt(anchor: str, reason: str) -> None:
    other = {
        "lifecycle_head_digest": head_of(CARRY, "quarantined").kill_quarantine_decision_digest,
        "lifecycle_subject_digest": head_of(ALPHA).lifecycle_subject_digest,
        "current_cycle_admission_decision_digest": ef7t.admitted().paper_admission_decision_digest,
    }
    with refused_authority(reason):
        build_paper_lifecycle_head_authority(
            head_inputs(head_of(CARRY, "readmitted"), approval=None, **{anchor: other[anchor]})
        )


def test_a_receipt_of_another_sleeve_is_refused() -> None:
    with refused_authority("lifecycle_head_sleeve_mismatch"):
        build_paper_lifecycle_head_authority(head_inputs(head_of(CARRY), approval=None, sleeve_id=ALPHA))


def test_the_head_must_take_effect_by_the_evaluation_end_inclusively() -> None:
    head = head_of(CARRY)
    at_end = build_paper_lifecycle_head_authority(head_inputs(head, evaluation_end_ns=head.effective_at_ns))
    assert at_end.paper_current_head_attested is True
    with refused_authority("lifecycle_head_after_the_evaluation_end"):
        build_paper_lifecycle_head_authority(
            head_inputs(head, approval=None, evaluation_end_ns=head.effective_at_ns - DAY)
        )


@pytest.mark.parametrize(
    "name, value, reason",
    [
        ("authority_id", "", "authority_id_invalid"),
        ("authority_version", " v1", "authority_version_invalid"),
        ("authority_id", "live-head", "forbidden_scope_token:authority_id"),
        ("sleeve_id", "carry sleeve", "sleeve_id_invalid"),
        ("lifecycle_head_digest", "A" * 64, "lifecycle_head_digest_invalid"),
        ("lifecycle_subject_digest", None, "lifecycle_subject_digest_invalid"),
        ("current_cycle_admission_decision_digest", "0" * 63, "current_cycle_admission_decision_digest_invalid"),
        ("evaluation_end_ns", True, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", -DAY, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", END + 1, "evaluation_end_ns_not_utc_day_aligned"),
        ("lifecycle_head", "not-a-receipt", "lifecycle_head_malformed"),
    ],
)
def test_malformed_authority_inputs_are_refused(name: str, value: object, reason: str) -> None:
    with refused_authority(reason):
        build_paper_lifecycle_head_authority(head_inputs(head_of(CARRY), approval=None, **{name: value}))


def test_authority_inputs_must_be_the_exact_record() -> None:
    with refused_authority("inputs_malformed"):
        build_paper_lifecycle_head_authority("inputs")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name, value, reason",
    [
        ("approval_kind", "MAYBE", "governance_approval_kind_invalid"),
        ("approval_digest", "x", "governance_approval_digest_invalid"),
        ("approval_reference", "", "governance_approval_reference_invalid"),
        ("approved_authority_policy_digest", "0", "governance_approved_authority_policy_digest_invalid"),
    ],
)
def test_a_malformed_approval_is_refused_never_downgraded(name: str, value: object, reason: str) -> None:
    inputs = head_inputs(head_of(CARRY), approval=None)
    with refused_authority(reason):
        build_paper_lifecycle_head_authority(replace(inputs, approval=approval_for(inputs, **{name: value})))


def test_an_approval_that_is_not_the_exact_record_is_refused() -> None:
    with refused_authority("governance_approval_malformed"):
        build_paper_lifecycle_head_authority(head_inputs(head_of(CARRY), approval="HUMAN_GOVERNANCE"))


def test_the_authority_verifier_is_exact_and_total() -> None:
    inputs = head_inputs(head_of(CARRY, "disabled"))
    authority = build_paper_lifecycle_head_authority(inputs)
    forged = reseal_authority(authority, resulting_lifecycle_state=EdgeLifecycleState.ACTIVE)
    assert verify_paper_lifecycle_head_authority(forged, inputs).reason_codes == (
        authority_code("field_mismatch:authority_digest"),
        authority_code("field_mismatch:resulting_lifecycle_state"),
    )
    tampered = verify_paper_lifecycle_head_authority(replace(authority, authority_digest="0" * 64), inputs)
    assert authority_code("self_digest_mismatch") in tampered.reason_codes
    for value in (None, {}, "authority", inputs, replace(authority, gate_verdict="PASS")):
        verification = verify_paper_lifecycle_head_authority(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in (
            (authority_code("evidence_type_invalid"),),
            (authority_code("evidence_serialization_failed"),),
        )
    broken = verify_paper_lifecycle_head_authority(authority, None)  # type: ignore[arg-type]
    assert broken.reason_codes == (authority_code("evidence_reconstruction_failed"),)


# --- B. provenance of the proposal ------------------------------------------------------------------------------------


def test_a_ready_single_sleeve_allocation_passes_the_exact_reservation_through() -> None:
    inputs = solo()
    decision = decide(inputs)
    env = inputs.portfolio_risk_envelope
    state, policy, budget = budget_of(CARRY, ROWS[CARRY])
    assert (decision.status, decision.ready, decision.paper_allocation_evidence_accepted) == (READY, True, True)
    assert (decision.governance_reason_codes, decision.breach_reason_codes) == ((), ())
    (sleeve,) = decision.sleeves
    assert (sleeve.governed_lifecycle_state, sleeve.current_head_attested, sleeve.kill_override_applied) == (
        ACTIVE,
        True,
        False,
    )
    assert amounts(sleeve) == (budget.total_reserved_budget,) * 3 == ("75.5",) * 3
    assert [
        (
            record.sequence,
            record.instrument_id,
            record.risk_budget_record_status,
            *amounts(record),
            record.market_binding,
        )
        for record in sleeve.records
    ] == [(0, INS, "ELIGIBLE", "60", "60", "60", BOUND), (1, INS, "ELIGIBLE", "15.5", "15.5", "15.5", BOUND)]
    assert [record.record_decision_digest for record in sleeve.records] == [
        record.record_decision_digest for record in budget.record_decisions
    ]
    assert (decision.exposure_evaluated, decision.positive_exposure_sleeve_count) == (True, 1)
    assert decision.total_post_kill_requested_budget == decision.total_final_allocated_budget == "75.5"
    assert decision.correlation_pair_checks == ()  # a one-sleeve envelope has no pair
    assert [(m.market_symbol, m.post_kill_requested_budget, m.within_cap) for m in decision.market_exposures] == [
        (PERP_BTC, "0", True),
        (INS, "75.5", True),
        (PERP_ETH, "0", True),
    ]
    assert (decision.envelope_id, decision.envelope_version, decision.envelope_digest) == (
        env.envelope_id,
        env.envelope_version,
        env.envelope_digest,
    )
    assert (decision.envelope_policy_digest, decision.envelope_advances) == (env.policy_digest, True)
    assert decision.correlation_evidence_digest == inputs.correlation_evidence.correlation_evidence_digest
    assert decision.correlation_evidence_status == "READY"
    assert (decision.total_paper_risk_budget, decision.max_sleeve_count, decision.max_pairwise_correlation) == (
        env.total_paper_risk_budget,
        1,
        env.correlation_cap.max_pairwise_correlation,
    )
    assert decision.declared_sleeve_ids == (CARRY,)
    assert sleeve.sleeve_cap == env.sleeve_caps[0].max_paper_risk_budget
    assert sleeve.paper_admission_decision_digest == ef7t.admitted().paper_admission_decision_digest
    assert sleeve.lifecycle_head_digest == head_of(CARRY).kill_quarantine_decision_digest
    assert sleeve.lifecycle_subject_digest == head_of(CARRY).lifecycle_subject_digest
    assert sleeve.lifecycle_head_authority_digest == inputs.sleeves[0].lifecycle_head_authority.authority_digest
    assert (
        sleeve.risk_budget_policy_id,
        sleeve.risk_budget_policy_digest,
        sleeve.risk_budget_state_digest,
        sleeve.risk_budget_decision_digest,
    ) == (policy.policy_id, policy.policy_digest, state.state_digest, budget.decision_digest)
    assert decision.regime_conditioned_caps_status == EDGE_REGIME_LABEL_BINDING_PENDING
    assert decision.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert decision.rule_set_digest == PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST
    for name, value in PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS:
        assert getattr(decision, name) is value, name


def test_every_declared_sleeve_needs_exactly_one_subject() -> None:
    env, alpha, beta = envelope(), subject(ALPHA), subject(BETA)
    with refused("sleeve_subjects_incomplete"):
        build(allocation(env, alpha))
    with refused("sleeve_subject_duplicate"):
        build(allocation(env, alpha, beta, alpha))
    with refused("sleeve_not_declared_by_envelope"):
        build(allocation(env, alpha, beta, subject(CARRY)))
    with refused("sleeves_malformed"):
        build(allocation(env, sleeves=iter((alpha, beta))))
    with refused("sleeve_malformed"):
        build(allocation(env, alpha, "not-a-subject"))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "name",
    ["paper_admission", "lifecycle_head_authority", "risk_budget_state", "risk_budget_policy", "risk_budget_decision"],
)
def test_every_subject_element_must_be_its_exact_record(name: str) -> None:
    with refused(f"{name}_malformed"):
        build(allocation(solo_envelope(), subject(CARRY, **{name: "not-a-record"})))


def test_the_admission_is_reproven_through_its_public_verifier() -> None:
    forged = reseal_admission(ef7t.admitted(), pinned_instrument_universe=(INS, "ETH-USDT-PERP"))
    with refused("paper_admission_not_intact"):
        build(solo(paper_admission=forged))
    with refused("paper_admission_not_admitted"):
        build(solo(paper_admission=ef7t.draft()))
    with refused("paper_admission_sleeve_mismatch"):
        build(solo(paper_admission=admission_for(ALPHA)))


def test_only_the_admission_that_opened_the_current_cycle_backs_the_head() -> None:
    # The re-admitted head's cycle was opened by the revalidation EF-7: the killed cycle's admission is history.
    with refused("paper_admission_not_the_current_cycle_admission"):
        build(solo("readmitted", paper_admission=ef7t.admitted()))
    with refused("paper_admission_not_the_current_cycle_admission"):
        build(solo("genesis", paper_admission=ef8t.revalidation()))


def test_the_proposal_must_use_the_admission_budget_policy() -> None:
    state, _, _ = budget_of(CARRY, ROWS[CARRY])
    other = build_paper_sleeve_risk_budget_policy(
        policy_id="paper-budget-1",
        sleeve_id=CARRY,
        total_budget="2000",
        per_intent_budget_cap="100",
        metadata={"review": "synthetic-test-value"},
    )
    decision = evaluate_paper_sleeve_risk_budget(
        state, other, correlation_id=f"rg7-budget-{CARRY}", metadata={"review": "synthetic-test-value"}
    )
    with refused("risk_budget_policy_not_the_admission_policy"):
        build(solo(risk_budget_policy=other, risk_budget_decision=decision))


def test_the_risk_budget_decision_is_rebuilt_exactly() -> None:
    _, policy, budget = budget_of(CARRY, ROWS[CARRY])
    with refused("risk_budget_decision_not_reconstructed"):
        build(solo(risk_budget_decision=reseal_budget(budget, total_reserved_budget="100")))
    other_state, _, _ = budget_of(CARRY, ((INS, "1", "10"),))
    with refused("risk_budget_decision_not_reconstructed"):
        build(solo(risk_budget_state=other_state))
    with refused("risk_budget_decision_malformed"):
        build(solo(risk_budget_decision=replace(budget, metadata=[("review", "synthetic-test-value")])))
    with refused("risk_budget_decision_reconstruction_failed"):
        build(solo(risk_budget_policy=replace(policy, total_budget="999")))


def test_the_authority_must_be_the_rebuild_of_its_inputs() -> None:
    item = subject(CARRY, "disabled")
    forged = reseal_authority(item.lifecycle_head_authority, resulting_lifecycle_state=EdgeLifecycleState.ACTIVE)
    with refused("lifecycle_head_authority_not_reconstructed"):
        build(allocation(solo_envelope(), replace(item, lifecycle_head_authority=forged)))
    with refused("lifecycle_head_authority_reconstruction_failed") as failure:
        build(allocation(solo_envelope(), replace(item, lifecycle_head_authority_inputs="inputs")))
    assert str(failure.value.__cause__) == authority_code("inputs_malformed")
    for authority_inputs, reason in (
        (head_inputs(head_of(CARRY), evaluation_end_ns=END - DAY), "lifecycle_head_authority_evaluation_end_mismatch"),
        (head_inputs(head_of(ALPHA)), "lifecycle_head_authority_sleeve_mismatch"),
    ):
        with refused(reason):
            build(
                solo(
                    lifecycle_head_authority_inputs=authority_inputs,
                    lifecycle_head_authority=build_paper_lifecycle_head_authority(authority_inputs),
                )
            )


def test_the_correlation_evidence_is_rebuilt_on_the_same_envelope_and_evaluation_end() -> None:
    env, item = solo_envelope(), subject(CARRY)
    correlation_inputs, evidence = correlation_of(env, False)
    with refused("correlation_evidence_not_reconstructed"):
        build(allocation(env, item, correlation_evidence=reseal_correlation(evidence, correlation_id="corr-forged")))
    foreign_inputs, foreign = correlation_of(solo_envelope(cap="350"), False)
    with refused("correlation_evidence_envelope_mismatch"):
        build(allocation(env, item, correlation_inputs=foreign_inputs, correlation_evidence=foreign))
    earlier = replace(correlation_inputs, evaluation_end_ns=END - DAY)
    with refused("correlation_evidence_evaluation_end_mismatch"):
        build(
            allocation(
                env,
                item,
                correlation_inputs=earlier,
                correlation_evidence=build_paper_sleeve_correlation_evidence(earlier),
            )
        )
    with refused("correlation_inputs_malformed"):
        build(allocation(env, item, correlation_inputs=None))
    with refused("correlation_evidence_malformed"):
        build(allocation(env, item, correlation_evidence=None))


def test_the_envelope_is_reproven() -> None:
    env = solo_envelope()
    with refused("portfolio_risk_envelope_not_intact"):
        build(
            allocation(env, subject(CARRY), portfolio_risk_envelope=replace(env, total_paper_risk_budget=rg2.d("5000")))
        )
    with refused("portfolio_risk_envelope_malformed"):
        build(allocation(env, subject(CARRY), portfolio_risk_envelope=None))


@pytest.mark.parametrize(
    "name, value, reason",
    [
        ("allocation_id", "", "allocation_id_invalid"),
        ("correlation_id", "scheduler-run", "forbidden_scope_token:correlation_id"),
        ("evaluation_end_ns", "2026", "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", True, "evaluation_end_ns_invalid"),
        ("evaluation_end_ns", END + 1, "evaluation_end_ns_not_utc_day_aligned"),
        ("evaluation_end_ns", END - DAY, "correlation_evidence_evaluation_end_mismatch"),
        ("sleeves", None, "sleeves_malformed"),
    ],
)
def test_malformed_top_level_inputs_are_refused(name: str, value: object, reason: str) -> None:
    with refused(reason):
        build(replace(solo(), **{name: value}))
    with refused("inputs_malformed"):
        build("inputs")


# --- C. governance ----------------------------------------------------------------------------------------------------


def test_an_unattested_head_is_never_active_and_no_exposure_is_evaluated() -> None:
    tight = solo_envelope(cap="10", total="10", markets=((INS, "10"), (PERP_BTC, "10"), (PERP_ETH, "10")))
    decision = decide(allocation(tight, subject(CARRY, approval=None)))
    assert (decision.status, decision.ready) == (NEEDS_GOVERNANCE, False)
    assert decision.governance_reason_codes == (code(f"lifecycle_head_authority_not_governed:{CARRY}"),)
    (sleeve,) = decision.sleeves
    assert (sleeve.governed_lifecycle_state, sleeve.current_head_attested, sleeve.kill_override_applied) == (
        UNPROVEN,
        False,
        False,
    )
    assert amounts(sleeve) == ("75.5", "0", "0")
    assert {(record.market_binding, record.final_allocated_budget) for record in sleeve.records} == {
        (NOT_EVALUATED, "0")
    }
    # 75.5 would breach every cap of 10, yet nothing is evaluated without a governed current head.
    assert decision.exposure_evaluated is False
    assert (decision.breach_reason_codes, decision.market_exposures, decision.correlation_pair_checks) == ((), (), ())
    assert (
        decision.total_post_kill_requested_budget,
        decision.total_final_allocated_budget,
        decision.positive_exposure_sleeve_count,
    ) == ("", "0", 0)


def test_a_test_only_synthetic_attestation_needs_governance() -> None:
    inputs = head_inputs(head_of(CARRY), approval=None)
    synthetic = replace(inputs, approval=approval_for(inputs, kind=SYNTHETIC))
    decision = decide(
        solo(
            lifecycle_head_authority_inputs=synthetic,
            lifecycle_head_authority=build_paper_lifecycle_head_authority(synthetic),
        )
    )
    assert (decision.status, decision.sleeves[0].governed_lifecycle_state) == (NEEDS_GOVERNANCE, UNPROVEN)
    assert decision.total_final_allocated_budget == "0"


def test_an_ungoverned_envelope_needs_governance() -> None:
    decision = decide(allocation(solo_envelope(governed=False), subject(CARRY)))
    assert decision.status is NEEDS_GOVERNANCE
    assert decision.governance_reason_codes == (
        code("correlation_evidence_needs_governance_approval"),
        code("portfolio_risk_envelope_not_governed"),
    )
    assert (decision.envelope_advances, decision.correlation_evidence_status, decision.exposure_evaluated) == (
        False,
        "NEEDS_GOVERNANCE_APPROVAL",
        False,
    )
    # The attested head still classifies the sleeve; only the arithmetic waits for governance, and nothing is allocated.
    (sleeve,) = decision.sleeves
    assert (sleeve.governed_lifecycle_state, *amounts(sleeve)) == (ACTIVE, "75.5", "75.5", "0")


# --- D. the kill/quarantine override ----------------------------------------------------------------------------------


@pytest.mark.parametrize("lifecycle, state", [("disabled", DISABLED), ("quarantined", QUARANTINE)])
def test_a_killed_head_zeroes_the_sleeve_and_every_record(lifecycle: str, state: PaperGovernedLifecycleState) -> None:
    decision = decide(solo(lifecycle))
    assert decision.status is READY
    (sleeve,) = decision.sleeves
    assert (sleeve.governed_lifecycle_state, sleeve.kill_override_applied, sleeve.current_head_attested) == (
        state,
        True,
        True,
    )
    assert amounts(sleeve) == ("75.5", "0", "0")
    assert [(*amounts(record), record.market_binding) for record in sleeve.records] == [
        ("60", "0", "0", NOT_EXPOSED),
        ("15.5", "0", "0", NOT_EXPOSED),
    ]
    assert (
        decision.total_post_kill_requested_budget,
        decision.total_final_allocated_budget,
        decision.positive_exposure_sleeve_count,
    ) == ("0", "0", 0)
    assert {market.post_kill_requested_budget for market in decision.market_exposures} == {"0"}


def test_a_readmitted_head_is_active_on_its_new_cycle() -> None:
    decision = decide(solo("readmitted"))
    (sleeve,) = decision.sleeves
    assert (decision.status, sleeve.governed_lifecycle_state, sleeve.kill_override_applied) == (READY, ACTIVE, False)
    assert sleeve.paper_admission_decision_digest == ef8t.revalidation().paper_admission_decision_digest
    assert sleeve.lifecycle_head_digest == head_of(CARRY, "readmitted").kill_quarantine_decision_digest
    assert decision.total_final_allocated_budget == "75.5"


def test_a_killed_sleeve_never_reaches_any_exposure_arithmetic(monkeypatch: pytest.MonkeyPatch) -> None:
    """The design's proof: a killed sleeve whose reservation would breach every cap gets zero, unseen by arithmetic."""

    env = envelope(
        ((ALPHA, "80"), (BETA, "50")), total="100", markets=((INS, "90"), (PERP_BTC, "90"), (PERP_ETH, "90"))
    )
    seen_amounts: list[str] = []
    seen_sleeves: list[str] = []
    real_amount, real_exposure = rg7._amount_value, rg7._evaluate_exposure

    def amount_spy(text: str) -> Fraction:
        seen_amounts.append(text)
        return real_amount(text)

    def exposure_spy(active: tuple[object, ...], **options: object) -> object:
        seen_sleeves.extend(item.sleeve_id for item in active)  # type: ignore[attr-defined]
        return real_exposure(active, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(rg7, "_amount_value", amount_spy)
    monkeypatch.setattr(rg7, "_evaluate_exposure", exposure_spy)
    decision = decide(allocation(env, subject(ALPHA), subject(BETA, "disabled", rows=WHALE)))
    assert decision.status is READY, decision.breach_reason_codes
    beta = decision.sleeves[1]
    assert (beta.governed_lifecycle_state, beta.kill_override_applied, *amounts(beta)) == (
        DISABLED,
        True,
        "975.70",
        "0",
        "0",
    )
    whale = {beta.pre_kill_requested_budget, *(record.pre_kill_requested_budget for record in beta.records)}
    assert whale == {"975.70", "99.77", "77.77"}
    # Neither the exposure stage nor the one amount conversion ever saw the killed sleeve, in build or re-proof.
    assert set(seen_sleeves) == {ALPHA}
    assert set(seen_amounts) == {"75.5", "60", "15.5"}
    assert not whale & set(seen_amounts)
    assert [(c.pair_status, c.effective_correlation, c.exposure) for c in decision.correlation_pair_checks] == [
        ("WORST_CASE_UNKNOWN", UNKNOWN, PAIR_NOT_EXPOSED)
    ]
    assert (decision.total_final_allocated_budget, decision.positive_exposure_sleeve_count) == ("75.5", 1)
    # The same reservation ACTIVE breaches every limit: the zero above is the kill override, not slack.
    active = build(allocation(env, subject(ALPHA), subject(BETA, rows=WHALE)))
    assert active.status is REJECTED
    assert set(active.breach_reason_codes) == {
        code("total_paper_risk_budget_exceeded"),
        code(f"sleeve_cap_exceeded:{BETA}"),
        code(f"market_cap_exceeded:{INS}"),
        code(f"pairwise_correlation_cap_exceeded:{ALPHA}:{BETA}"),
        code(f"record_instrument_not_an_envelope_market:{BETA}:9"),
        code(f"record_instrument_outside_admitted_universe:{BETA}:9"),
    }


def test_currentness_is_exactly_the_human_attestation_never_inferred() -> None:
    # The lifecycle later disabled this sleeve, but the human attested the ACTIVE genesis for this coordinate: RG-7
    # applies the attestation and infers nothing from the existence of later receipts.
    assert head_of(CARRY, "disabled").lifecycle_sequence > head_of(CARRY).lifecycle_sequence
    decision = decide(solo("genesis"))
    assert (decision.status, decision.sleeves[0].governed_lifecycle_state) == (READY, ACTIVE)
    assert (decision.global_current_lifecycle_head_proven, decision.live_current_lifecycle_head_proven) == (
        False,
        False,
    )
    for token in ("lifecycle_sequence", "lifecycle_cycle", "prior_binding", "consumed_admission", "build_edge_kill"):
        assert token not in SOURCE, token


# --- E. caps, correlation and the whole-proposal rule -----------------------------------------------------------------


@pytest.mark.parametrize(
    "total, expected",
    [
        ("115.5", set()),
        ("116", set()),
        ("115.499999999999999999", {"total_paper_risk_budget_exceeded", f"market_cap_exceeded:{INS}"}),
    ],
    ids=["equal", "above", "below"],
)
def test_the_total_cap_is_inclusive(total: str, expected: set[str]) -> None:
    decision = portfolio_decision(caps_envelope(total=total, alpha="75.5", beta="40", ins=total))
    assert decision.status is (REJECTED if expected else READY)
    assert set(decision.breach_reason_codes) == {code(reason) for reason in expected}
    assert (decision.total_paper_risk_budget, decision.total_post_kill_requested_budget) == (rg2.d(total), "115.5")


@pytest.mark.parametrize(
    "cap, breached",
    [("75.5", False), ("75.6", False), ("75.499999999999999999", True)],
    ids=["equal", "above", "below"],
)
def test_a_sleeve_cap_is_inclusive(cap: str, breached: bool) -> None:
    decision = portfolio_decision(caps_envelope(alpha=cap))
    assert decision.sleeves[0].sleeve_cap == rg2.d(cap)
    assert decision.breach_reason_codes == ((code(f"sleeve_cap_exceeded:{ALPHA}"),) if breached else ())


@pytest.mark.parametrize(
    "cap, breached",
    [("115.5", False), ("200", False), ("115.499999999999999999", True)],
    ids=["equal", "above", "below"],
)
def test_a_market_cap_is_inclusive(cap: str, breached: bool) -> None:
    decision = portfolio_decision(caps_envelope(ins=cap))
    market = {item.market_symbol: item for item in decision.market_exposures}[INS]
    assert (market.market_cap, market.post_kill_requested_budget, market.within_cap) == (
        rg2.d(cap),
        "115.5",
        not breached,
    )
    assert decision.breach_reason_codes == ((code(f"market_cap_exceeded:{INS}"),) if breached else ())


def test_the_positive_sleeve_count_is_inclusive_and_counts_only_positive_sleeves() -> None:
    at_limit = portfolio_decision(caps_envelope(count=2))
    assert (at_limit.status, at_limit.positive_exposure_sleeve_count, at_limit.max_sleeve_count) == (READY, 2, 2)
    below = portfolio_decision(caps_envelope(count=3))
    assert (below.status, below.positive_exposure_sleeve_count, below.max_sleeve_count) == (READY, 2, 3)
    zero = decide(allocation(caps_envelope(count=2), subject(ALPHA), subject(BETA, rows=()), observed=True))
    assert (zero.positive_exposure_sleeve_count, zero.sleeves[1].final_allocated_budget) == (1, "0")
    # RG-2 never declares more sleeves than the count, so only the exposure stage itself can exceed it.
    sleeves = tuple(
        rg7._ExposureSleeve(sleeve_id, "10", rg2.d("400"), frozenset({INS}), (rg7._ExposureRecord(0, INS, "10"),))
        for sleeve_id in (ALPHA, BETA, "sleeve-gamma")
    )
    exposure = rg7._evaluate_exposure(sleeves, envelope=caps_envelope(count=2), pairs=())
    assert exposure.breaches == (code("max_sleeve_count_exceeded"),)


def observed_correlation() -> str:
    return correlation_of(caps_envelope(), True)[1].pairs[0].effective_correlation


@pytest.mark.parametrize(
    "units, exposure", [(0, WITHIN), (1, WITHIN), (-1, BREACH)], ids=["equal", "cap_above", "cap_below"]
)
def test_an_exposed_pair_meets_the_pairwise_cap_inclusively(units: int, exposure: PaperAllocationPairExposure) -> None:
    rho = observed_correlation()
    decision = portfolio_decision(caps_envelope(cap=shifted(rho, units)))
    (check,) = decision.correlation_pair_checks
    assert (check.sleeve_a_id, check.sleeve_b_id, check.pair_status, check.effective_correlation, check.exposure) == (
        ALPHA,
        BETA,
        "OBSERVED",
        rho,
        exposure,
    )
    assert decision.max_pairwise_correlation == shifted(rho, units)
    expected = (code(f"pairwise_correlation_cap_exceeded:{ALPHA}:{BETA}"),) if exposure is BREACH else ()
    assert decision.breach_reason_codes == expected


@pytest.mark.parametrize("cap", ["0.6", "0.999999999999999999", "-1"])
def test_two_positive_sleeves_without_observed_correlation_reject_the_whole_proposal(cap: str) -> None:
    decision = decide(allocation(caps_envelope(cap=cap), subject(ALPHA), subject(BETA), observed=False))
    assert decision.status is REJECTED
    (check,) = decision.correlation_pair_checks
    assert (check.pair_status, check.effective_correlation, check.exposure) == ("WORST_CASE_UNKNOWN", UNKNOWN, BREACH)
    assert decision.breach_reason_codes == (code(f"pairwise_correlation_cap_exceeded:{ALPHA}:{BETA}"),)
    # Rejected as a whole and kept as evidence: nothing allocated, nothing scaled, every request preserved.
    assert [amounts(sleeve) for sleeve in decision.sleeves] == [("75.5", "75.5", "0"), ("40", "40", "0")]
    assert {record.final_allocated_budget for sleeve in decision.sleeves for record in sleeve.records} == {"0"}
    assert (decision.total_post_kill_requested_budget, decision.total_final_allocated_budget) == ("115.5", "0")


@pytest.mark.parametrize("rows, lifecycle", [((), "genesis"), (None, "disabled")], ids=["zero_sleeve", "killed_sleeve"])
def test_an_unknown_pair_with_a_zero_or_killed_sleeve_is_not_exposed(
    rows: tuple[tuple[str, str, str], ...] | None, lifecycle: str
) -> None:
    decision = decide(allocation(caps_envelope(), subject(ALPHA), subject(BETA, lifecycle, rows=rows)))
    assert decision.status is READY
    (check,) = decision.correlation_pair_checks
    assert (check.pair_status, check.exposure) == ("WORST_CASE_UNKNOWN", PAIR_NOT_EXPOSED)
    assert decision.total_final_allocated_budget == "75.5"


def test_markets_are_summed_separately_across_sleeves() -> None:
    env = envelope(markets=((INS, "100"), (PERP_ETH, "60"), (PERP_BTC, "500")))
    universe = frozenset({INS, PERP_ETH})
    first = rg7._ExposureSleeve(
        ALPHA,
        "100",
        rg2.d("400"),
        universe,
        (rg7._ExposureRecord(0, INS, "60"), rg7._ExposureRecord(1, PERP_ETH, "40")),
    )
    second = rg7._ExposureSleeve(
        BETA, "50", rg2.d("300"), universe, (rg7._ExposureRecord(0, INS, "30"), rg7._ExposureRecord(1, PERP_ETH, "20"))
    )
    exposure = rg7._evaluate_exposure((first, second), envelope=env, pairs=())
    assert [(m.market_symbol, m.post_kill_requested_budget, m.within_cap) for m in exposure.market_exposures] == [
        (PERP_BTC, "0", True),
        (INS, "90", True),
        (PERP_ETH, "60", True),
    ]
    assert (exposure.breaches, exposure.total, exposure.positive) == ((), Fraction(150), frozenset({ALPHA, BETA}))
    heavier = replace(
        first,
        reserved_total="100.000000000000000001",
        records=(first.records[0], replace(first.records[1], reserved_budget="40.000000000000000001")),
    )
    assert rg7._evaluate_exposure((heavier, second), envelope=env, pairs=()).breaches == (
        code(f"market_cap_exceeded:{PERP_ETH}"),
    )


@pytest.mark.parametrize(
    "instrument, reasons",
    [
        (PERP_ETH, ("record_instrument_outside_admitted_universe",)),
        (UNLISTED, ("record_instrument_not_an_envelope_market", "record_instrument_outside_admitted_universe")),
    ],
)
def test_a_positive_record_must_bind_an_envelope_market_inside_the_admitted_universe(
    instrument: str, reasons: tuple[str, ...]
) -> None:
    decision = decide(solo(rows=ROWS[CARRY] + ((instrument, "1", "10"),)))
    assert decision.status is REJECTED
    record = decision.sleeves[0].records[2]
    assert (record.instrument_id, record.market_binding) == (instrument, UNBOUND)
    assert record.binding_reason_codes == tuple(code(reason) for reason in reasons)
    assert decision.breach_reason_codes == tuple(code(f"{reason}:{CARRY}:2") for reason in reasons)
    # The unbound reservation joins no market but stays in the sleeve and the total.
    assert {item.market_symbol: item.post_kill_requested_budget for item in decision.market_exposures}[INS] == "75.5"
    assert (decision.total_post_kill_requested_budget, decision.total_final_allocated_budget) == ("85.5", "0")


def test_a_zero_reservation_binds_no_market() -> None:
    decision = decide(solo(rows=ROWS[CARRY] + ((UNLISTED, "1", "200"),)))  # over the per-intent cap: BLOCKED at zero
    assert decision.status is READY
    record = decision.sleeves[0].records[2]
    assert (record.risk_budget_record_status, record.pre_kill_requested_budget, record.market_binding) == (
        "BLOCKED",
        "0",
        NOT_EXPOSED,
    )


def test_one_breach_rejects_the_whole_proposal_and_keeps_it_as_evidence() -> None:
    decision = portfolio_decision(caps_envelope(beta="39.999999999999999999"))
    assert (decision.status, decision.ready, decision.paper_allocation_evidence_accepted) == (REJECTED, False, False)
    assert decision.breach_reason_codes == (code(f"sleeve_cap_exceeded:{BETA}"),)
    # The sleeve within its own cap is not allocated either: no partial fit, no clipping.
    for sleeve in decision.sleeves:
        assert sleeve.final_allocated_budget == "0"
        assert sleeve.post_kill_requested_budget == sleeve.pre_kill_requested_budget != "0"
        for record in sleeve.records:
            assert (record.final_allocated_budget, record.post_kill_requested_budget) == (
                "0",
                record.pre_kill_requested_budget,
            )
    assert (decision.total_post_kill_requested_budget, decision.total_final_allocated_budget) == ("115.5", "0")


def test_without_a_breach_every_reservation_passes_through_exactly() -> None:
    _, decision = ready_portfolio()
    assert decision.status is READY
    for sleeve in decision.sleeves:
        budget = budget_of(sleeve.sleeve_id, ROWS[sleeve.sleeve_id])[2]
        assert amounts(sleeve) == (budget.total_reserved_budget,) * 3
        assert [record.final_allocated_budget for record in sleeve.records] == [
            record.reserved_budget for record in budget.record_decisions
        ]
    total = sum((Fraction(sleeve.final_allocated_budget) for sleeve in decision.sleeves), Fraction(0))
    assert Fraction(decision.total_final_allocated_budget) == total == Fraction("115.5")
    assert (decision.silent_scaling_applied, decision.partial_fit_applied, decision.covariance_used) == (False,) * 3


def test_breach_reasons_are_exact_sorted_and_deterministic() -> None:
    inputs = allocation(caps_envelope(total="100", alpha="70", beta="39", ins="100"), subject(ALPHA), subject(BETA))
    first, second = decide(inputs), decide(inputs)
    assert first == second
    assert paper_portfolio_allocation_decision_to_dict(first) == paper_portfolio_allocation_decision_to_dict(second)
    assert first.breach_reason_codes == tuple(
        sorted(
            {
                code("total_paper_risk_budget_exceeded"),
                code(f"sleeve_cap_exceeded:{ALPHA}"),
                code(f"sleeve_cap_exceeded:{BETA}"),
                code(f"market_cap_exceeded:{INS}"),
                code(f"pairwise_correlation_cap_exceeded:{ALPHA}:{BETA}"),
            }
        )
    )


# --- F. integrity -----------------------------------------------------------------------------------------------------


def test_the_self_digest_is_recomputed() -> None:
    inputs, decision = ready_portfolio()
    assert paper_portfolio_allocation_decision_digest(decision) == decision.allocation_decision_digest
    verification = verify_paper_portfolio_allocation_decision(
        replace(decision, allocation_decision_digest="0" * 64), inputs
    )
    assert verification.intact is False
    assert set(verification.reason_codes) == {
        code("self_digest_mismatch"),
        code("field_mismatch:allocation_decision_digest"),
    }


@pytest.mark.parametrize(
    "name, value",
    [
        ("status", REJECTED),
        ("ready", False),
        ("paper_allocation_evidence_accepted", False),
        ("allocation_id", "rg7-other"),
        ("evaluation_end_ns", END - DAY),
        ("envelope_digest", "0" * 64),
        ("envelope_advances", False),
        ("correlation_evidence_digest", "0" * 64),
        ("total_paper_risk_budget", "2000.000000000000000000"),
        ("max_pairwise_correlation", "0.900000000000000000"),
        ("declared_sleeve_ids", (ALPHA,)),
        ("exposure_evaluated", False),
        ("market_exposures", ()),
        ("correlation_pair_checks", ()),
        ("total_post_kill_requested_budget", "115"),
        ("total_final_allocated_budget", "116"),
        ("positive_exposure_sleeve_count", 1),
        ("governance_reason_codes", ("paper_portfolio_allocation_decision:portfolio_risk_envelope_not_governed",)),
        ("breach_reason_codes", ("paper_portfolio_allocation_decision:total_paper_risk_budget_exceeded",)),
        ("rule_set_digest", "0" * 64),
        ("capital_allocated", True),
        ("order_permitted", True),
        ("execution_authorized", True),
        ("live_ready", True),
        ("global_current_lifecycle_head_proven", True),
    ],
)
def test_every_decision_field_is_bound_by_reconstruction(name: str, value: object) -> None:
    inputs, decision = ready_portfolio()
    verification = verify_paper_portfolio_allocation_decision(reseal_decision(decision, **{name: value}), inputs)
    assert verification.intact is False
    assert code(f"field_mismatch:{name}") in verification.reason_codes


def test_every_sleeve_and_record_field_is_bound_by_reconstruction() -> None:
    inputs, decision = ready_portfolio()
    alpha = decision.sleeves[0]
    for sleeve in (
        replace(alpha, final_allocated_budget="0"),
        replace(alpha, governed_lifecycle_state=DISABLED),
        replace(alpha, kill_override_applied=True),
        replace(alpha, lifecycle_head_digest="0" * 64),
        replace(alpha, paper_admission_decision_digest="0" * 64),
        replace(alpha, records=(replace(alpha.records[0], final_allocated_budget="1"), alpha.records[1])),
        replace(alpha, records=(replace(alpha.records[0], market_binding=UNBOUND), alpha.records[1])),
    ):
        forged = reseal_decision(decision, sleeves=(sleeve, decision.sleeves[1]))
        assert verify_paper_portfolio_allocation_decision(forged, inputs).reason_codes == (
            code("field_mismatch:allocation_decision_digest"),
            code("field_mismatch:sleeves"),
        )


def test_the_decision_verifier_is_total() -> None:
    inputs, decision = ready_portfolio()
    for value in (
        None,
        {},
        "decision",
        decision.sleeves[0],
        replace(decision, status="READY"),
        replace(decision, max_sleeve_count=-1),
        replace(decision, sleeves=list(decision.sleeves)),
    ):
        verification = verify_paper_portfolio_allocation_decision(value, inputs)
        assert verification.intact is False
        assert verification.reason_codes in ((code("evidence_type_invalid"),), (code("evidence_serialization_failed"),))
    broken = verify_paper_portfolio_allocation_decision(decision, None)  # type: ignore[arg-type]
    assert broken.reason_codes == (code("evidence_reconstruction_failed"),)


def test_the_wire_form_is_canonical_json() -> None:
    _, decision = ready_portfolio()
    payload = paper_portfolio_allocation_decision_to_dict(decision)
    assert json.loads(edge_canonical_json(payload)) == payload
    assert (payload["status"], payload["sleeves"][0]["governed_lifecycle_state"]) == ("READY", "ACTIVE")
    assert payload["sleeves"][0]["records"][0]["market_binding"] == "BOUND"
    assert payload["correlation_pair_checks"][0]["exposure"] == "WITHIN_CAP"


# --- G. design authority and static discipline ------------------------------------------------------------------------


def test_the_module_is_pure_and_consumes_only_accepted_public_surfaces() -> None:
    pit.assert_module_is_pure(
        rg7,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.edge_kill_quarantine_decision",
            "crypto_core.validation.edge_paper_admission_decision",
            "crypto_core.validation.paper_portfolio_risk_envelope",
            "crypto_core.validation.paper_sleeve_correlation_evidence",
            "crypto_core.validation.paper_sleeve_intent_ledger",
            "crypto_core.validation.paper_sleeve_risk_budget_decision",
        },
    )
    assert "crypto_core.regime" not in SOURCE


def test_one_construction_site_per_artifact_and_amounts_become_numbers_only_after_the_kill_override() -> None:
    pit.assert_single_assembly_path(
        rg7,
        "PaperLifecycleHeadAuthority",
        "_assemble_authority",
        "build_paper_lifecycle_head_authority",
        "verify_paper_lifecycle_head_authority",
    )
    calls: dict[str, list[str]] = {}
    for function in (node for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.FunctionDef)):
        calls[function.name] = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]

    def callers(name: str) -> set[str]:
        return {caller for caller, called in calls.items() if name in called}

    assert callers("PaperPortfolioAllocationDecision") == {"build_paper_portfolio_allocation_decision"}
    assert callers("build_paper_portfolio_allocation_decision") == {"verify_paper_portfolio_allocation_decision"}
    # Stage 2 then stages 3-5: only ACTIVE sleeves become exposure inputs, and only the exposure stage takes a value.
    assert callers("_exposure_sleeve") == callers("_evaluate_exposure") == {"build_paper_portfolio_allocation_decision"}
    assert callers("_amount_value") == {"_evaluate_exposure"}
    assert callers("Fraction") == {"_amount_value", "_governed_value", "_evaluate_exposure"}


def test_live_order_capital_and_scheduler_names_are_only_structural_false_flags() -> None:
    flags = dict(PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS) | dict(PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS)
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
    for record, record_flags in (
        (PaperPortfolioAllocationDecision, dict(PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS)),
        (PaperLifecycleHeadAuthority, dict(PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS)),
    ):
        assert {item.name: item.default for item in fields(record) if item.name in record_flags} == record_flags
        assert all(item.default is dataclasses.MISSING for item in fields(record) if item.name not in record_flags)


def test_no_production_values_or_defaults_exist() -> None:
    integers, decimals = world.module_literals(rg7)
    # Text, identifier and wire bounds, the scale, the base, the terminating-decimal primes and the day.
    assert integers <= {0, 1, 2, 5, 10, 18, 32, 60, 127, 128, 256, 4096, DAY, INT64_MAX}
    assert decimals <= {"0", "9", UNKNOWN}
    for record in (
        PaperLifecycleHeadAuthorityApproval,
        PaperLifecycleHeadAuthorityInputs,
        PaperPortfolioAllocationSleeveInputs,
        PaperPortfolioAllocationInputs,
    ):
        assert all(item.default is dataclasses.MISSING for item in fields(record))


def test_the_rg6_ladder_never_sizes_an_allocation() -> None:
    assert paper_portfolio_allocation_rule_set()["rg6_numeric_effect"] == "NONE"
    attributes = {node.attr for node in ast.walk(ast.parse(SOURCE)) if isinstance(node, ast.Attribute)}
    assert not attributes & {
        "ladder_boundaries",
        "lower_tier",
        "upper_tier",
        "min_probation_days",
        "promotion_min_paper_sharpe",
        "promotion_max_drawdown_fraction",
        "demotion_min_paper_sharpe",
        "demotion_max_drawdown_fraction",
        "portfolio_stop_levels",
    }
    for record in (
        PaperPortfolioAllocationInputs,
        PaperPortfolioAllocationSleeveInputs,
        PaperLifecycleHeadAuthorityInputs,
    ):
        assert not [item.name for item in fields(record) if "tier" in item.name or "sharpe" in item.name]
    # Envelopes differing only in their ladder levels allocate identically.
    steeper = (
        rg2.lower_boundary(promotion_sharpe="3", demotion_sharpe="2"),
        rg2.upper_boundary(promotion_sharpe="5", demotion_sharpe="4"),
    )
    base = portfolio_decision(caps_envelope())
    other = portfolio_decision(caps_envelope(ladder=steeper))
    assert other.envelope_digest != base.envelope_digest
    for decision in (base, other):
        assert decision.status is READY
    assert [amounts(sleeve) for sleeve in other.sleeves] == [amounts(sleeve) for sleeve in base.sleeves]
    assert other.total_final_allocated_budget == base.total_final_allocated_budget == "115.5"


def test_the_rule_set_commits_the_controller_rules_and_is_handed_out_fresh() -> None:
    rule_set = paper_portfolio_allocation_rule_set()
    assert edge_sha256_text(edge_canonical_json(rule_set)) == PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST
    assert {
        key: rule_set[key]
        for key in (
            "contract_id",
            "structural_authority_id",
            "current_head_authority_id",
            "subject_cardinality_rule_id",
            "proposal_rule_id",
            "correlation_rule_id",
            "unknown_effective_correlation",
        )
    } == {
        "contract_id": "RG7_PAPER_PORTFOLIO_ALLOCATION_DECISION_V1",
        "structural_authority_id": "RG7_ALLOCATION_AUTHORITY_AND_MATH_POLICY_V1",
        "current_head_authority_id": "RG7_HUMAN_GOVERNANCE_PAPER_CURRENT_HEAD_ATTESTATION_V1",
        "subject_cardinality_rule_id": "RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1",
        "proposal_rule_id": "REPROVEN_INTRA_SLEEVE_TOTAL_RESERVED_BUDGET_PASSTHROUGH_V1",
        "correlation_rule_id": "RG7_CORRELATION_ACTIVE_PAIR_CAP_RULE_V1",
        "unknown_effective_correlation": UNKNOWN,
    }
    assert rule_set["order_of_operations"][:2] == ("provenance_and_governance", "kill_quarantine_override")
    assert {"covariance", "risk_parity", "kelly", "sharpe_sizing", "tier_multiplier"} <= set(
        rule_set["excluded_method_ids"]  # type: ignore[arg-type]
    )
    rule_set["contract_id"] = "rg7-other"
    assert paper_portfolio_allocation_rule_set()["contract_id"] == "RG7_PAPER_PORTFOLIO_ALLOCATION_DECISION_V1"


def test_the_public_api_is_exact_and_offers_no_head_lookup() -> None:
    assert set(rg7.__all__) == {
        "PAPER_LIFECYCLE_HEAD_AUTHORITY_NON_CLAIM_FLAGS",
        "PAPER_PORTFOLIO_ALLOCATION_NON_CLAIM_FLAGS",
        "PAPER_PORTFOLIO_ALLOCATION_RULE_SET_DIGEST",
        "PaperAllocationMarketBinding",
        "PaperAllocationPairExposure",
        "PaperGovernedLifecycleState",
        "PaperLifecycleHeadAuthority",
        "PaperLifecycleHeadAuthorityApproval",
        "PaperLifecycleHeadAuthorityApprovalKind",
        "PaperLifecycleHeadAuthorityInputs",
        "PaperPortfolioAllocationDecision",
        "PaperPortfolioAllocationError",
        "PaperPortfolioAllocationInputs",
        "PaperPortfolioAllocationRecord",
        "PaperPortfolioAllocationSleeveInputs",
        "PaperPortfolioAllocationSleeveRecord",
        "PaperPortfolioAllocationStatus",
        "PaperPortfolioCorrelationPairCheck",
        "PaperPortfolioMarketExposure",
        "build_paper_lifecycle_head_authority",
        "build_paper_portfolio_allocation_decision",
        "paper_lifecycle_head_authority_digest",
        "paper_lifecycle_head_authority_to_dict",
        "paper_portfolio_allocation_decision_digest",
        "paper_portfolio_allocation_decision_to_dict",
        "paper_portfolio_allocation_rule_set",
        "verify_paper_lifecycle_head_authority",
        "verify_paper_portfolio_allocation_decision",
    }
    assert not [
        name for name in rg7.__all__ if re.search(r"latest|registry|lookup|newest|head_of", name, re.IGNORECASE)
    ]


def test_the_design_records_the_rg7_contract() -> None:
    text = DESIGN.read_text(encoding="utf-8")
    start = text.index("6. **RG-7 `paper_portfolio_allocation_decision.py`**")
    item = " ".join(text[start : text.index("7. **RG-8", start)].split())
    for phrase in (
        "ORDER OF OPERATIONS IS THE P1 INVARIANT",
        "(a) kill/quarantine override FIRST (killed sleeve → allocation 0 BEFORE any arithmetic)",
        "`ALLOCATION_REJECTED` for the whole proposal (NO silent scaling, no partial fits)",
        "Output is digest-bound allocation EVIDENCE",
        "RG7_ALLOCATION_AUTHORITY_AND_MATH_POLICY_V1",
        "RG7_HUMAN_GOVERNANCE_PAPER_CURRENT_HEAD_ATTESTATION_V1",
        "EF-8 stays historical only and is not changed",
        "never inferred from the lifecycle sequence, an effective time, the newest object, a state, a digest or caller "
        "ordering",
        "`TEST_ONLY_SYNTHETIC` never establishes it",
        "RG7_ONE_ALLOCATION_SUBJECT_PER_SLEEVE_V1",
        "no duplicate, missing or extra sleeve",
        "exactly its re-proven intra-sleeve `total_reserved_budget`",
        "RG-6 has no numeric effect, because RG-2 defines no tier-to-budget multiplier",
        "no numeric field of it enters the total, a sleeve or market sum, the positive-sleeve count or a correlation pair",
        "an unproven head is never ACTIVE",
        "RG7_CORRELATION_ACTIVE_PAIR_CAP_RULE_V1",
        "exactly 1 for WORST_CASE_UNKNOWN",
        "No covariance, square-root portfolio risk, correlation-weighted scaling, diversification credit, averaging or "
        "matrix inversion",
        "inside the EF-7 pinned universe",
        "READY sets every final allocation to its exact post-kill reservation",
        "never capital allocated, an order or execution permitted",
    ):
        assert phrase in item, phrase


# --- H. the memo-free end-to-end re-proof -----------------------------------------------------------------------------


@SLOW
def test_a_ready_portfolio_re_proves_with_every_memo_disabled() -> None:
    inputs, decision = ready_portfolio()
    ef6t._MEMO_ENABLED[0] = False
    try:
        rebuilt = build(inputs)
        verification = verify_paper_portfolio_allocation_decision(decision, inputs)
    finally:
        ef6t._MEMO_ENABLED[0] = True
    assert rebuilt == decision
    assert (verification.intact, verification.reason_codes) == (True, ())
