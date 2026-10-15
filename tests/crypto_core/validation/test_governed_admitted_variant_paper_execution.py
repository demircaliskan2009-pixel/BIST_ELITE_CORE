"""Tests for the governed admitted-variant paper execution (GOVERNED_ADMITTED_VARIANT_PAPER_EXECUTION_V1).

World G (the one shared positive world). It is purpose-built TEST_ONLY_SYNTHETIC construction over REAL authenticated
upstream artifacts:

* the admission: world P's governed EF-7 v2 PASS of ``carry-sleeve-1`` (the base variant of the ±20% / 5% star grid,
  admission cap fraction 1/4) and its ACTIVE EF-8 genesis on day 635, both from the EF-7/EF-8 test modules' caches;
* the variant: world P's executable binding, the base ``unit_size`` 1 assignment and its exact parameter approval;
  the economics policy and HUMAN_GOVERNANCE approval world P was evaluated under;
* the paper period: a synthetic PIT archive of the same manifest from the paper genesis ``G`` (day 635): world P's
  funding cycle every two days (``0``, a signal, a 45..65 bps payoff), a daily mark around 40 and one book per
  funding cycle with a 10 bps spread and depth 1000. Price levels sit near 40 so that one BUY and one SELL reservation
  tick of one unit at ``L = m * (1 + beta)`` fit EF-7's synthetic per-intent budget cap (100) and RG-7's admission cap
  (1/4 of the 400 sleeve cap): ``2 * 44.x <= 100``;
* governance: the RG-2 solo envelope of the RG-7 tests, an equity basis whose reference notional is the economics
  initial equity (10 000), a unit performance-path weight, the RG-6 seed entered at ``G``, the time-window chain's
  accepted metrics summary, a 30-day bootstrap and beta 0.1. Every approval and attestation (paper adoption, bootstrap,
  beta, every cycle and every head attestation) is a SYNTHETIC TEST VALUE committed exactly to its subject; none is a
  production value, and real paper execution stays BLOCKED.

The strategy first trades on day 3, so cycles 0..3 are B0, cycles 4..29 are B1 and cycle 30 (RG-3 READY over 30 daily
returns with non-zero variance) is the first ORDINARY cycle; world G seals 32 days so that cycle 31 continues the READY
RG-6 lineage. Negative worlds are short variants of the same construction, or targeted defects of world G's own inputs.

Cost control: as in the RG-7 and RG-8 tests, the EF-6/EF-7/EF-8 memos are applied, and every pure upstream builder or
verifier these modules call (including each module's call sites of the other's public verifiers) is memoized under an
exact key of its whole input. A memo only returns the result of an identical earlier real call: a tampered input is a
miss and is computed for real. A slow test re-proves world G with every memo of this contract disabled; world P's own
memo-free re-proof belongs to its modules' slow tests.
"""

from __future__ import annotations

import ast
import functools
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.edge_kill_quarantine_decision as ef8_module
import crypto_core.validation.edge_paper_admission_decision as ef7_module
import crypto_core.validation.governed_admitted_variant_paper_execution as execution
import crypto_core.validation.governed_paper_execution_authority as authority_module
import crypto_core.validation.paper_portfolio_allocation_decision as rg7
import crypto_core.validation.paper_portfolio_governance_decision as rg8
from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.strategy.spec import strategy_spec_to_dict, validate_strategy_spec
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDay,
    GovernedPaperDaySealInputs,
    GovernedPaperExecutionInputs,
    build_governed_paper_day,
    build_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    GovernedPaperApproval,
    GovernedPaperApprovalKind,
    GovernedPaperBootstrapAuthority,
    GovernedPaperCycleAuthority,
    GovernedPaperCycleInputs,
    GovernedPaperCycleStatus,
    GovernedPaperGenesis,
    GovernedPaperGenesisInputs,
    GovernedPaperReservationBand,
    build_governed_paper_cycle_authority,
    build_governed_paper_genesis,
    governed_paper_cycle_chain,
)
from crypto_core.validation.historical_execution_economics import (
    historical_execution_governed_paper_prefix_digest,
    historical_execution_latest_visible_mark,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    historical_execution_render_amount,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from crypto_core.validation.paper_portfolio_allocation_decision import PaperLifecycleHeadAuthorityInputs
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    PaperSleeveLadderDecisionStatus,
    PaperSleeveLadderPriorDecision,
)

try:  # the module objects pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_kill_quarantine_decision as ef8t
    import test_edge_paper_admission_decision as ef7t
    import test_edge_pre_paper_validation_evidence as pret
    import test_edge_walk_forward_oos_evidence as ef6t
    import test_historical_execution_economics_policy as polt
    import test_paper_portfolio_allocation_decision as rg7t
    import test_paper_portfolio_governance_decision as rg8t
    import test_paper_portfolio_risk_envelope as rg2
    import test_paper_sleeve_daily_valuation_evidence as world
    import test_paper_sleeve_drawdown_evidence as rg4t
    import test_paper_sleeve_performance_evidence as rg3t
    import test_paper_sleeve_promotion_demotion_decision as rg6t
    import test_strategy_executable_binding as bindt
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_kill_quarantine_decision as ef8t
    from tests.crypto_core.validation import test_edge_paper_admission_decision as ef7t
    from tests.crypto_core.validation import test_edge_pre_paper_validation_evidence as pret
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t
    from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
    from tests.crypto_core.validation import test_paper_portfolio_allocation_decision as rg7t
    from tests.crypto_core.validation import test_paper_portfolio_governance_decision as rg8t
    from tests.crypto_core.validation import test_paper_portfolio_risk_envelope as rg2
    from tests.crypto_core.validation import test_paper_sleeve_daily_valuation_evidence as world
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t
    from tests.crypto_core.validation import test_paper_sleeve_promotion_demotion_decision as rg6t
    from tests.crypto_core.validation import test_strategy_executable_binding as bindt

SLOW = pytest.mark.slow  # a memo-free re-proof of world G; see the module docstring
HUMAN = GovernedPaperApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC
DAY, S0, INS, FUNDING = pret.DAY, pret.S0, pret.INS, pret.FUNDING
SLEEVE = ef7t.SLEEVE
G = S0 + 635 * DAY  # the paper genesis: world P's EF-8 genesis instant, a UTC day boundary
WORLD_DAYS = 32
CORR = "gp-corr"
d = pret.d
# SYNTHETIC TEST VALUES of the paper period.
BETA = "0.100000000000000000"
HORIZON_DAYS = 30
FIRST_FUNDING, LAST_FUNDING = 315, 337  # funding windows k: event S0 + (k - 1) * FUNDING, visible S0 + k * FUNDING + 10


# --- exact memos of pure upstream calls (see module docstring) ----------------------------------------------------------


# This contract's own call-site memos can be switched off alone (the world P memos stay on).
_GP_MEMO_ENABLED = [True]


class _CallMemo:
    """Exact memo of one pure function of positional and keyword arguments (RG-8's exact key); else a direct call."""

    def __init__(self, real: Callable[..., object]) -> None:
        self.real = real
        self.cache: dict[object, object] = {}

    def __call__(self, *args: object, **kwargs: object) -> object:
        if not (ef6t._MEMO_ENABLED[0] and _GP_MEMO_ENABLED[0]):
            return self.real(*args, **kwargs)
        try:
            key = (
                tuple(rg8t.exact_key(item) for item in args),
                tuple((name, rg8t.exact_key(value)) for name, value in sorted(kwargs.items())),
            )
        except Exception:  # noqa: BLE001 - no exact key: evaluate directly
            return self.real(*args, **kwargs)
        if key not in self.cache:
            self.cache[key] = self.real(*args, **kwargs)  # a raising call is never cached
        return self.cache[key]


_AUTHORITY_TARGETS = (
    "edge_authority_binding_snapshot",
    "verify_strategy_executable_binding",
    "verify_historical_execution_economics_policy",
    "verify_historical_pit_dataset",
    "verify_paper_portfolio_risk_envelope",
    "verify_paper_sleeve_equity_basis_policy",
    "verify_paper_portfolio_performance_path_policy",
    "verify_paper_sleeve_ladder_seed",
    "build_paper_sleeve_daily_valuation_evidence",
    "build_paper_sleeve_performance_evidence",
    "build_paper_sleeve_drawdown_evidence",
    "build_paper_sleeve_correlation_evidence",
    "build_paper_sleeve_promotion_demotion_decision",
    "build_paper_lifecycle_head_authority",
    "build_paper_portfolio_allocation_decision",
    "build_paper_portfolio_governance_decision",
)
_EXECUTION_TARGETS = (
    "verify_governed_paper_genesis",
    "verify_governed_paper_cycle_authority",
    "governed_paper_cycle_chain",
    "governed_paper_cycle_capacity",
    "governed_paper_strategy_spec",
    "verify_historical_pit_dataset",
    "build_historical_decision_run",
    "build_historical_execution_economics",
    "simulate_historical_execution_governed_paper",
    "build_paper_lifecycle_head_authority",
    "verify_paper_sleeve_performance_evidence",
)
_GP_MEMOS: dict[tuple[object, str], _CallMemo] = {
    **{(authority_module, name): _CallMemo(getattr(authority_module, name)) for name in _AUTHORITY_TARGETS},
    **{(execution, name): _CallMemo(getattr(execution, name)) for name in _EXECUTION_TARGETS},
    (authority_module, "verify_governed_paper_genesis"): _CallMemo(authority_module.verify_governed_paper_genesis),
}


def apply_memos(patch: pytest.MonkeyPatch) -> None:
    """The RG-8 tests' memos plus this contract's own call-site memos (shared with the authority tests)."""

    pret.apply_memos(patch)
    for name, memo in ef7t._EF7_MEMOS.items():
        patch.setattr(ef7_module, name, memo)
    for name, memo in ef8t._EF8_MEMOS.items():
        patch.setattr(ef8_module, name, memo)
    for name in ("verify_edge_kill_quarantine_decision", "verify_edge_paper_admission_decision"):
        patch.setattr(rg7, name, ef8t._EF8_MEMOS[name])
        patch.setattr(authority_module, name, ef8t._EF8_MEMOS[name])
    for name, memo in rg8t._RG8_MEMOS.items():
        patch.setattr(rg8, name, memo)
    for (module, name), memo in _GP_MEMOS.items():
        patch.setattr(module, name, memo)


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        apply_memos(patch)
        yield


# --- the synthetic paper archive ------------------------------------------------------------------------------------


def mark_price(day: int) -> Fraction:
    """SYNTHETIC daily mark of absolute day ``day`` (around 40, five deterministic levels, so returns vary)."""

    return Fraction(40) * (1 + Fraction(5 * (((day * 7) % 5) - 2), 10_000))


def _pit(series: str, key: str, sequence: int, event: int, values: dict[str, str]) -> HistoricalPitRecord:
    return build_historical_pit_record(
        series_id=series,
        data_requirement_key=key,
        instrument=INS,
        sequence_id=sequence,
        event_time_ns=event,
        available_at_ns=event + 1,
        finalized_at_ns=event + 2,
        revision_vintage_id=None,
        values=tuple(HistoricalPitValue(name, value) for name, value in sorted(values.items())),
    )


def funding_record(k: int, *, visible_at: int | None = None, rate: str | None = None) -> HistoricalPitRecord:
    """World P's funding window ``k``; ``visible_at`` publishes it later (a SYNTHETIC delayed publication)."""

    visible = S0 + k * FUNDING + 10 if visible_at is None else visible_at
    return build_historical_pit_record(
        series_id="funding-final",
        data_requirement_key="funding_rate",
        instrument=INS,
        sequence_id=k,
        event_time_ns=S0 + (k - 1) * FUNDING,
        available_at_ns=visible,
        finalized_at_ns=visible,
        revision_vintage_id=None,
        values=(HistoricalPitValue("funding_rate", pret._rate(k) if rate is None else rate),),
    )


def mark_record(day: int, *, price: Fraction | None = None) -> HistoricalPitRecord:
    """The SYNTHETIC mark of absolute day ``day``, visible just before that day's UTC boundary."""

    value = mark_price(day) if price is None else price
    return _pit("mark", "mark_price", day, S0 + day * DAY - 1_000, {"mark_price": d(value)})


def book_record(
    k: int, *, event: int | None = None, depth: int = 1000, sequence: int | None = None
) -> HistoricalPitRecord:
    """The SYNTHETIC book of funding cycle ``k``: mid at the day's mark, 10 bps spread, ``depth`` units each side."""

    time = S0 + k * FUNDING + 500 if event is None else event
    mid = mark_price((time - S0) // DAY)
    values = {
        "best_bid_price": d(mid * (1 - Fraction(5, 10_000))),
        "best_ask_price": d(mid * (1 + Fraction(5, 10_000))),
        "best_bid_quantity": d(depth),
        "best_ask_quantity": d(depth),
    }
    return _pit("book", "order_book", k if sequence is None else sequence, time, values)


@functools.cache
def world_records() -> tuple[HistoricalPitRecord, ...]:
    """World G's whole synthetic archive (records are revealed day by day through their visibility)."""

    return (
        *(funding_record(k) for k in range(FIRST_FUNDING, LAST_FUNDING)),
        *(mark_record(day) for day in range(620, 672)),
        *(book_record(k) for k in range(FIRST_FUNDING, LAST_FUNDING)),
    )


def visibility(record: HistoricalPitRecord) -> int:
    return (
        record.available_at_ns
        if record.finalized_at_ns is None
        else max(record.available_at_ns, record.finalized_at_ns)
    )


@functools.cache
def archive(as_of: int, records: tuple[HistoricalPitRecord, ...] | None = None) -> HistoricalPitDataset:
    """The authenticated archive as of ``as_of``: every record visible at or before it, under world P's manifest."""

    _, manifest, _, registry, _ = ef6t.world()
    items = tuple(item for item in (world_records() if records is None else records) if visibility(item) <= as_of)
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id=f"paper-archive-{(as_of - G) // DAY}",
        correlation_id=pret.CORR,  # the archive shares its source manifest's correlation
        source_reference="archive:paper",
        rights_status="own_research",
        rights_reference="license-1",
        records=items,
    )


# --- the governed paper genesis (SYNTHETIC TEST VALUES) -------------------------------------------------------------


def approval(kind_label: str, subject_id: str, subject_digest: str, *, kind: object = HUMAN, **overrides: object):
    """SYNTHETIC TEST VALUES: one exact human commitment to one subject digest."""

    values: dict[str, object] = {
        "approval_reference": f"test-fixture:{kind_label}:{subject_id}",
        "approval_digest": "d" * 64,
        "approval_kind": kind,
        "approved_subject_kind": kind_label,
        "approved_subject_id": subject_id,
        "approved_subject_digest": subject_digest,
        "approved_rule_set_digest": GOVERNED_PAPER_EXECUTION_AUTHORITY_RULE_SET_DIGEST,
    }
    values.update(overrides)
    return GovernedPaperApproval(**values)  # type: ignore[arg-type]


def subject_digest(record: object) -> str:
    return authority_module._subject_digest(record)


def bootstrap_authority(
    *, horizon: int = HORIZON_DAYS, sleeve: str = SLEEVE, genesis_ns: int = G, kind: object = HUMAN
):
    unapproved = GovernedPaperBootstrapAuthority("gp-bootstrap-1", "synthetic-v1", sleeve, genesis_ns, horizon, None)
    return replace(
        unapproved,
        approval=approval("bootstrap", unapproved.bootstrap_id, subject_digest(unapproved), kind=kind),
    )


def reservation_band(*, beta: str = BETA, kind: object = HUMAN) -> GovernedPaperReservationBand:
    unapproved = GovernedPaperReservationBand("gp-band-1", "synthetic-v1", INS, beta, None)
    return replace(
        unapproved, approval=approval("reservation_band", unapproved.band_id, subject_digest(unapproved), kind=kind)
    )


@functools.cache
def solo_envelope():
    return rg7t.solo_envelope()


@functools.cache
def basis_policy():
    return world.basis_policy(sleeve_id=SLEEVE, market_symbol=INS, reference_notional="10000")


@functools.cache
def path_policy():
    return rg4t.policy_for(solo_envelope(), ((SLEEVE, "1"),))


@functools.cache
def ladder_seed():
    return rg6t.human_seed(solo_envelope(), G, SLEEVE)


@functools.cache
def metrics_summary():
    """The time-window producer source: the accepted time-window test recipe re-targeted to the paper instrument.

    RG-3 binds the daily-return series market to the summary's market, so the summary must be of ``INS``. Its paper
    session, governor policy thresholds (C7) and readiness are SYNTHETIC TEST VALUES of that recipe; RG-3 claims the
    session context is not sleeve-scoped, and nothing here promotes them to governance.
    """

    support = world.window_support
    payload = strategy_spec_to_dict(support._spec())
    payload["instrument_universe"] = [INS]
    result = validate_strategy_spec(payload)
    assert result.accepted and result.spec is not None
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(support, "_SYMBOL", INS)
        patch.setattr(support, "_spec", lambda: result.spec)
        summary = support._summary()
    assert summary.market_symbol == INS
    return summary


@functools.cache
def economics_approval():
    _, _, _, registry, binding = ef6t.world()
    return polt.approval_for(
        pret.economics_policy_p(),
        strategy_spec_digest=binding.strategy_spec_digest,
        data_requirement_registry_digest=data_requirement_registry_digest(registry),
        approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
    )


def genesis_inputs(**overrides: object) -> GovernedPaperGenesisInputs:
    """World G's genesis inputs; the adoption approval commits exactly to the assembled genesis unless overridden."""

    _, _, _, _, binding = ef6t.world()
    params = pret.params_p()
    values: dict[str, object] = {
        "genesis_id": "gp-carry-1",
        "genesis_version": "synthetic-v1",
        "correlation_id": CORR,
        "sleeve_id": SLEEVE,
        "instrument": INS,
        "genesis_ns": G,
        "paper_admission": ef7t.admitted(),
        "lifecycle_genesis": ef8t.genesis(),
        "admitted_variant_id": pret.BASE_VARIANT,
        "executable_binding": binding,
        "parameter_assignment": params,
        "parameter_approval": bindt.parameter_approval_for(binding, params),
        "economics_policy": pret.economics_policy_p(),
        "economics_approval": economics_approval(),
        "risk_budget_policy": ef7t.budget_policy(SLEEVE),
        "portfolio_risk_envelope": solo_envelope(),
        "equity_basis_policy": basis_policy(),
        "performance_path_policy": path_policy(),
        "ladder_seed": ladder_seed(),
        "metrics_summary": metrics_summary(),
        "methodology_id": "gp-method-1",
        "risk_free_policy_id": rg3t.RISK_FREE_POLICY_ID,
        "bootstrap": bootstrap_authority(),
        "reservation_band": reservation_band(),
        "adoption_approval": None,
    }
    adopt = overrides.pop("adopt", True)
    values.update(overrides)
    inputs = GovernedPaperGenesisInputs(**values)  # type: ignore[arg-type]
    if adopt is True and "adoption_approval" not in overrides:
        draft = build_governed_paper_genesis(inputs)
        inputs = replace(
            inputs, adoption_approval=approval("paper_adoption", draft.genesis_id, draft.genesis_policy_digest)
        )
    return inputs


@functools.cache
def world_genesis() -> tuple[GovernedPaperGenesisInputs, GovernedPaperGenesis]:
    inputs = genesis_inputs()
    return inputs, build_governed_paper_genesis(inputs)


# --- the daily construction -----------------------------------------------------------------------------------------


def head_at(instant: int, head=None, *, approval_kind: object = rg7t._UNSET) -> PaperLifecycleHeadAuthorityInputs:
    """A SYNTHETIC human attestation at ``instant`` that ``head`` (the paper genesis receipt by default) is current."""

    receipt = ef8t.genesis() if head is None else head
    return rg7t.head_inputs(
        receipt, approval=approval_kind, authority_id=f"gp-head-{(instant - G) // DAY}", evaluation_end_ns=instant
    )


def approve_cycle(
    inputs: GovernedPaperCycleInputs, *, kind: object = HUMAN
) -> tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority]:
    """Build the cycle's draft, then (when only its human approval is missing) approve exactly that draft."""

    draft = build_governed_paper_cycle_authority(inputs)
    if draft.status is not GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL or draft.blocked_reason_codes:
        return inputs, draft
    approved = replace(inputs, approval=approval("cycle", draft.cycle_id, draft.cycle_policy_digest, kind=kind))
    return approved, build_governed_paper_cycle_authority(approved)


@dataclass(frozen=True)
class World:
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    cycles: tuple[tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority], ...]
    seals: tuple[GovernedPaperDaySealInputs, ...]
    days: tuple[GovernedPaperDay, ...]

    def execution_inputs(self, **overrides: object) -> GovernedPaperExecutionInputs:
        values: dict[str, object] = {
            "evidence_id": "gp-evidence-1",
            "correlation_id": CORR,
            "genesis_inputs": self.genesis_inputs,
            "genesis": self.genesis,
            "days": self.seals,
            "seals": tuple(day.seal for day in self.days),
        }
        values.update(overrides)
        return GovernedPaperExecutionInputs(**values)  # type: ignore[arg-type]


def build_world(
    days: int,
    *,
    genesis: tuple[GovernedPaperGenesisInputs, GovernedPaperGenesis] | None = None,
    records: tuple[HistoricalPitRecord, ...] | None = None,
    heads: Callable[[int], object] | None = None,
    approve: Callable[[int, GovernedPaperCycleInputs], tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority]]
    | None = None,
) -> World:
    """Construct ``days`` governed paper days causally: cycle ``k`` opens at ``E_k``, day ``k`` is sealed at ``E_(k+1)``."""

    gi, gen = world_genesis() if genesis is None else genesis
    opening = archive(G, records)
    episodes: tuple = ()
    closes: tuple = ()
    funding: tuple = ()
    prior_ladder: PaperSleeveLadderPriorDecision | None = None
    prior_cycle: tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority] | None = None
    prior_seal = None
    cycles, seals, built = [], [], []
    for k in range(days):
        open_ns, close_ns = G + k * DAY, G + (k + 1) * DAY
        head_open = head_at(open_ns) if heads is None else heads(open_ns)
        inputs = GovernedPaperCycleInputs(
            cycle_id=f"gp-c{k}",
            correlation_id=CORR,
            genesis_inputs=gi,
            genesis=gen,
            day_index=k,
            opening_dataset=opening,
            sealed_episodes=episodes,
            sealed_day_closes=closes,
            sealed_funding_events=funding,
            prior_ladder=prior_ladder,
            head_authority_inputs=head_open,  # type: ignore[arg-type]
            approval=None,
        )
        inputs, cycle = approve_cycle(inputs) if approve is None else approve(k, inputs)
        dataset = archive(close_ns, records)
        seal_inputs = GovernedPaperDaySealInputs(
            seal_id=f"gp-s{k}",
            correlation_id=CORR,
            cycle_inputs=inputs,
            cycle_authority=cycle,
            prior_cycle_inputs=None if prior_cycle is None else prior_cycle[0],
            prior_cycle_authority=None if prior_cycle is None else prior_cycle[1],
            prior_seal=prior_seal,
            dataset=dataset,
            closing_head_authority_inputs=head_at(close_ns) if heads is None else heads(close_ns),  # type: ignore[arg-type]
        )
        day = build_governed_paper_day(seal_inputs)
        cycles.append((inputs, cycle))
        seals.append(seal_inputs)
        built.append(day)
        if day.projection is None:
            break
        episodes = (*episodes, *day.projection.episodes)
        closes = (*closes, day.projection.day_close)
        funding = (*funding, *day.projection.funding_events)
        chain = governed_paper_cycle_chain(inputs)
        ladder = None if chain is None else chain.ladder
        prior_ladder = (
            PaperSleeveLadderPriorDecision(chain.ladder_inputs, ladder)  # type: ignore[union-attr,arg-type]
            if ladder is not None and ladder.status is PaperSleeveLadderDecisionStatus.READY
            else None
        )
        prior_cycle, prior_seal, opening = (inputs, cycle), day.seal, dataset
    return World(gi, gen, tuple(cycles), tuple(seals), tuple(built))


@functools.cache
def world_g() -> World:
    return build_world(WORLD_DAYS)


# --- world variants (SYNTHETIC TEST VALUES) -------------------------------------------------------------------------


def E(k: int) -> int:  # noqa: N802 - the design's cycle-opening name
    return G + k * DAY


@functools.cache
def envelope_with(cap: str = "400", stops: tuple[str, ...] | None = None) -> object:
    """A governed solo RG-2 envelope; with the defaults it equals the RG-7 tests' solo envelope."""

    overrides: dict[str, object] = {
        "total_paper_risk_budget": rg2.d("1000"),
        "sleeve_caps": [rg2.sleeve(SLEEVE, cap)],
        "market_caps": [rg2.market(market, value) for market, value in rg7t.MARKETS],
        "max_sleeve_count": 1,
        "correlation_cap": rg2.correlation("0.6", 30, 20),
    }
    if stops is not None:
        overrides["portfolio_stop_levels"] = [rg2.stop(level, text) for level, text in enumerate(stops, 1)]
    return rg2.governed(**overrides)


@functools.cache
def variant_genesis(
    *, cap: str = "400", stops: tuple[str, ...] | None = None, beta: str = BETA, horizon: int = HORIZON_DAYS
) -> tuple[GovernedPaperGenesisInputs, GovernedPaperGenesis]:
    env = envelope_with(cap, stops)
    inputs = genesis_inputs(
        genesis_id=f"gp-variant-{cap}-{len(stops or ())}-{horizon}",
        portfolio_risk_envelope=env,
        performance_path_policy=rg4t.policy_for(env, ((SLEEVE, "1"),)),
        ladder_seed=rg6t.human_seed(env, G, SLEEVE),
        reservation_band=reservation_band(beta=beta),
        bootstrap=bootstrap_authority(horizon=horizon),
    )
    return inputs, build_governed_paper_genesis(inputs)


def renumbered_books(*extra: tuple[int, int]) -> tuple[HistoricalPitRecord, ...]:
    """World G's books numbered ``2k``, plus ``(event, sequence)`` extras that keep sequence order with event time."""

    books = [book_record(k, sequence=2 * k) for k in range(FIRST_FUNDING, LAST_FUNDING)]
    books += [book_record(0, event=event, sequence=sequence) for event, sequence in extra]
    return tuple(books)


def records_with(
    *,
    funding: dict[int, HistoricalPitRecord] | None = None,
    books: tuple[HistoricalPitRecord, ...] | None = None,
    marks: tuple[HistoricalPitRecord, ...] | None = None,
) -> tuple[HistoricalPitRecord, ...]:
    return (
        *((funding or {}).get(k, funding_record(k)) for k in range(FIRST_FUNDING, LAST_FUNDING)),
        *((mark_record(day) for day in range(620, 672)) if marks is None else marks),
        *((book_record(k) for k in range(FIRST_FUNDING, LAST_FUNDING)) if books is None else books),
    )


@functools.cache
def cross_day_records() -> tuple[HistoricalPitRecord, ...]:
    """Funding window 319 published at ``E_4 - 1000`` (a late decision of cycle 3) and a book at ``E_4 + 500``."""

    return records_with(
        funding={319: funding_record(319, visible_at=E(4) - 1_000)},
        books=renumbered_books((E(4) + 500, 2 * 319 + 1)),
    )


def unapproved_at(day: int) -> Callable[[int, GovernedPaperCycleInputs], tuple[object, object]]:
    def approve(k: int, inputs: GovernedPaperCycleInputs):
        if k == day:
            return inputs, build_governed_paper_cycle_authority(inputs)
        return approve_cycle(inputs)

    return approve


@functools.cache
def disable_at(instant: int):
    """An authentic EF-8 KILL_DISABLE of the paper genesis receipt taking effect at ``instant``."""

    return ef8t.disable(ef8t.genesis(), effective_at_ns=instant, decision_id=f"ef8-disable-gp-{instant - G}")


def heads_with(at: int, receipt) -> Callable[[int], PaperLifecycleHeadAuthorityInputs]:
    """Attest the paper genesis receipt everywhere except at ``at``, where ``receipt`` is the attested head."""

    def heads(instant: int) -> PaperLifecycleHeadAuthorityInputs:
        return head_at(instant, receipt if instant >= at else None)

    return heads


def phases(w: World) -> list[str]:
    return [cycle.phase.value for _, cycle in w.cycles]


def all_fills(w: World, day: int) -> list[tuple[int, str, str]]:
    outcome = w.days[day].outcome
    decided = {item.intent_id: item for item in outcome.intents}  # type: ignore[union-attr]
    return [
        (decided[item.intent_id].decision_sequence, item.outcome.value, item.reason)
        for item in outcome.fills  # type: ignore[union-attr]
    ]


def code(text: str) -> str:
    return f"governed_admitted_variant_paper_execution:{text}"


def refused(text: str):
    return pytest.raises(execution.GovernedPaperExecutionError, match=f"^{re.escape(code(text))}$")


def reseal_seal(seal, **changes: object):
    changed = replace(seal, **changes)
    return replace(changed, seal_digest=execution.governed_paper_day_seal_digest(changed))


# --- A/B. the positive world ------------------------------------------------------------------------------------------


def test_world_g_moves_from_b0_through_b1_to_ordinary_and_seals_every_day() -> None:
    w = world_g()
    assert len(w.days) == WORLD_DAYS
    assert phases(w) == ["BOOTSTRAP_B0"] * 4 + ["BOOTSTRAP_B1"] * 26 + ["ORDINARY"] * 2
    assert all(cycle.authorized and cycle.window_start_ns == E(k) for k, (_, cycle) in enumerate(w.cycles))
    assert all(day.seal.sealed for day in w.days)
    counts = [len(day.seal.episode_digests) for day in w.days]
    assert counts[:3] == [0, 0, 0] and counts[3] == 1 and sum(counts) == 10
    statuses = [(c.performance_status, c.drawdown_status, c.ladder_status, c.governance_status) for _, c in w.cycles]
    assert statuses[0] == ("NOT_DERIVED",) * 4
    assert statuses[1:4] == [("NOT_DERIVED", "NOT_COMPUTABLE", "NOT_DERIVED", "NOT_DERIVED")] * 3
    assert statuses[4:30] == [("NOT_COMPUTABLE",) * 4] * 26
    assert statuses[30:] == [("READY",) * 4] * 2
    assert all(c.allocation_status == "READY" and c.correlation_status == "READY" for _, c in w.cycles)
    assert [c.bootstrap_status for _, c in w.cycles] == ["WITHIN_HORIZON"] * 30 + ["NOT_REQUIRED"] * 2


def test_the_bootstrap_rg8_exception_is_exactly_the_insufficient_sample() -> None:
    w = world_g()
    chain = governed_paper_cycle_chain(w.cycles[4][0])
    assert chain is not None and chain.governance is not None and chain.performance is not None
    assert chain.performance.reason_codes == authority_module._BOOTSTRAP_RG3_REASONS
    assert chain.governance.status.value == "NOT_COMPUTABLE" and chain.governance.portfolio_stop_evaluated is False

    def pinned(reasons: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(item.format(sleeve=SLEEVE) for item in reasons)

    assert chain.drawdown.reason_codes == pinned(authority_module._B1_DRAWDOWN_REASONS)  # type: ignore[union-attr]
    assert chain.ladder.reason_codes == pinned(authority_module._B1_LADDER_REASONS)  # type: ignore[union-attr]
    assert chain.governance.reason_codes == pinned(authority_module._B1_GOVERNANCE_REASONS)
    assert chain.drawdown.status.value == "NOT_COMPUTABLE"  # type: ignore[union-attr]
    assert chain.ladder.status.value == "NOT_COMPUTABLE"  # type: ignore[union-attr]
    b0 = governed_paper_cycle_chain(w.cycles[3][0])
    assert b0 is not None and (b0.performance, b0.ladder, b0.governance) == (None, None, None)
    assert b0.drawdown is not None and b0.drawdown.missing_sleeve_ids == (SLEEVE,)
    assert b0.drawdown.reason_codes == pinned(authority_module._B0_DRAWDOWN_REASONS)
    ordinary = governed_paper_cycle_chain(w.cycles[30][0])
    assert ordinary is not None and ordinary.governance.status.value == "READY"  # type: ignore[union-attr]
    assert ordinary.governance.sleeves[0].terminal_final_allocated_budget == w.cycles[30][1].allocation_final_budget  # type: ignore[union-attr]


def test_the_evidence_reproves_the_lineage_and_the_terminal_rg3_over_every_sealed_day() -> None:
    w = world_g()
    inputs = w.execution_inputs()
    evidence = build_governed_paper_execution_evidence(inputs)
    verification = execution.verify_governed_paper_execution_evidence(evidence, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert (evidence.status.value, evidence.sealed_day_count, evidence.episode_count) == ("READY", WORLD_DAYS, 10)
    assert (evidence.first_b1_day_index, evidence.first_ordinary_day_index) == (4, 30)
    assert (evidence.bootstrap_b0_cycle_count, evidence.bootstrap_b1_cycle_count, evidence.ordinary_cycle_count) == (
        4,
        26,
        2,
    )
    assert evidence.performance_status == "READY" and evidence.performance_daily_return_count == WORLD_DAYS
    assert Fraction(evidence.paper_sharpe_annualized) != 0  # a computed Sharpe: the daily returns have variance
    assert evidence.invalidated_from_ns is None and evidence.reason_codes == ()
    flags = dict(execution.GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS)
    for artifact in (evidence, *(day.seal for day in w.days)):
        assert {name: getattr(artifact, name) for name in flags} == flags


def test_every_projected_episode_is_exactly_the_engine_fill_and_its_deciding_reservation() -> None:
    w = world_g()
    seen: set[str] = set()
    for k, day in enumerate(w.days):
        outcome, projection = day.outcome, day.projection
        assert outcome is not None and projection is not None
        executed = [
            item
            for item in outcome.fills
            if item.outcome.value in ("FILLED", "PARTIALLY_FILLED") and E(k) <= item.execution_time_ns < E(k + 1)  # type: ignore[operator]
        ]
        assert len(executed) == len(projection.episodes)
        fees = {item.fill_digest: item for item in outcome.fee_cashflows}
        decided = {item.intent_id: item for item in outcome.intents}
        for fill, episode in zip(executed, projection.episodes, strict=True):
            intent = decided[fill.intent_id]
            cycle = w.cycles[(intent.decision_time_ns - G) // DAY][1]
            generic = episode.fill_result
            assert Fraction(generic.fill_price) == Fraction(fill.fill_price)  # type: ignore[arg-type]
            assert Fraction(generic.filled_units) == Fraction(fill.filled_quantity)
            assert historical_execution_render_amount(Fraction(generic.fee_amount)) == fees[fill.fill_digest].fee_amount
            assert (
                episode.fill_policy.slippage_bps == "0"
                and episode.fill_market_snapshot.observed_at_ns == fill.execution_time_ns
            )
            requested = Fraction(intent.requested_quantity) * Fraction(cycle.reservation_price)
            assert Fraction(episode.order_intent_request.requested_notional) == requested
            assert Fraction(generic.gross_notional) <= requested  # the generic overfill guard holds by construction
            assert episode.capacity_decision.decision_digest not in seen
            seen.add(episode.capacity_decision.decision_digest)
            assert getattr(episode.order_intent.intent_type, "value", episode.order_intent.intent_type) == "MARKET"
    assert len(seen) == 10


def test_funding_and_day_closes_carry_the_engine_settlements_marks_and_positions() -> None:
    w = world_g()
    gi = w.genesis_inputs
    for k, day in enumerate(w.days):
        outcome, projection = day.outcome, day.projection
        settled = [item for item in outcome.funding_cashflows if E(k) <= item.liability_time_ns < E(k + 1)]  # type: ignore[union-attr]
        assert [(e.settlement_at_ns, e.funding_amount) for e in projection.funding_events] == [  # type: ignore[union-attr]
            (item.liability_time_ns, item.cashflow_amount) for item in settled
        ]
        close = projection.day_close  # type: ignore[union-attr]
        mark = historical_execution_latest_visible_mark(
            w.seals[k].dataset, policy=gi.economics_policy, instrument=INS, at_ns=E(k + 1)
        )
        assert close.close_mark_snapshot.observed_at_ns == E(k + 1) and mark is not None
        assert Fraction(close.close_mark_snapshot.mark_price) == Fraction(mark[1])


def test_each_replay_preserves_every_sealed_prefix_exactly() -> None:
    w = world_g()
    final = w.days[-1].outcome
    for k in range(1, WORLD_DAYS):
        prior = w.days[k - 1].seal
        assert w.days[k].seal.opening_prefix_digest == prior.closing_prefix_digest
        excluded = () if prior.pending_decision_sequence is None else (prior.pending_decision_sequence,)
        assert (
            historical_execution_governed_paper_prefix_digest(
                final, before_ns=E(k), excluded_decision_sequences=excluded
            )  # type: ignore[arg-type]
            == prior.closing_prefix_digest
        )
    assert len({day.seal.run_digest for day in w.days}) == WORLD_DAYS  # every replay is its own authenticated run


def test_the_rg6_lineage_starts_at_the_seed_and_continues_the_first_ready_decision() -> None:
    w = world_g()
    assert all(inputs.prior_ladder is None for inputs, _ in w.cycles[:31])
    continued = w.cycles[31][0].prior_ladder
    first_ready = governed_paper_cycle_chain(w.cycles[30][0])
    assert continued is not None and first_ready is not None and first_ready.ladder is not None
    assert continued.decision.decision_digest == first_ready.ladder.decision_digest
    assert (
        governed_paper_cycle_chain(w.cycles[31][0]).ladder.prior_decision_digest == first_ready.ladder.decision_digest
    )  # type: ignore[union-attr]


def test_the_reservation_fits_the_admission_cap_and_the_supported_capacity_measure() -> None:
    w = world_g()
    _, genesis = world_genesis()
    admission_cap = Fraction(genesis.admission_cap_fraction) * Fraction(400)
    for _, cycle in w.cycles:
        reservation = Fraction(cycle.reservation_price)
        assert reservation == Fraction(cycle.opening_mark_price) * (1 + Fraction(BETA))
        assert Fraction(cycle.allocation_final_budget) == 2 * reservation <= admission_cap
        assert cycle.capacity_within_assumption and Fraction(cycle.reservation_notional) <= Fraction(
            genesis.capacity_max_value
        )


def test_the_day_seal_is_digest_bound_and_reproven_totally() -> None:
    w = world_g()
    seal, inputs = w.days[3].seal, w.seals[3]
    verification = execution.verify_governed_paper_day_seal(seal, inputs)
    assert (verification.intact, verification.reason_codes) == (True, ())
    for forged, reason in (
        (replace(seal, sealed=False), "day_seal_self_digest_mismatch"),
        (reseal_seal(seal, episode_digests=()), "day_seal_field_mismatch:episode_digests"),
        (
            reseal_seal(seal, real_paper_execution_authorized=True),
            "day_seal_field_mismatch:real_paper_execution_authorized",
        ),
    ):
        result = execution.verify_governed_paper_day_seal(forged, inputs)
        assert result.intact is False and code(reason) in result.reason_codes
    for garbage in (None, object(), w.days[3]):
        assert execution.verify_governed_paper_day_seal(garbage, inputs).intact is False
    assert execution.verify_governed_paper_day_seal(seal, object()).intact is False


# --- C. negative worlds -----------------------------------------------------------------------------------------------


def test_a_pending_cross_day_fill_needs_both_cycle_windows_and_keeps_its_deciding_reservation() -> None:
    authorized = build_world(6, records=cross_day_records())
    assert authorized.days[3].seal.pending_decision_sequence is not None
    assert all_fills(authorized, 3)[-1][1:] == ("UNFILLED", "no_eligible_book_observation")
    pending = authorized.days[3].seal.pending_decision_sequence
    assert [item for item in all_fills(authorized, 4) if item[0] == pending] == [(pending, "FILLED", "filled")]
    episode = authorized.days[4].projection.episodes[0]  # type: ignore[union-attr]
    deciding = authorized.cycles[3][1]
    assert Fraction(episode.order_intent_request.requested_notional) == Fraction(deciding.reservation_price)
    assert episode.capacity_policy.max_notional == execution._plain(Fraction(deciding.reservation_notional))
    refused_world = build_world(6, records=cross_day_records(), approve=unapproved_at(4))
    assert refused_world.cycles[4][1].status is GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL
    assert [item for item in all_fills(refused_world, 4) if item[0] == pending] == [
        (pending, "REJECTED", "governed_paper_no_cycle_authority_at_fill")
    ]
    assert refused_world.days[4].projection.episodes == ()  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("offset", "expected"),
    [
        (300, (None, "REJECTED", "governed_paper_lifecycle_invalidated_before_fill")),
        (502, (None, "REJECTED", "governed_paper_lifecycle_invalidated_before_fill")),
        (10, (None, "REJECTED", "governed_paper_lifecycle_invalidated")),
        (503, (None, "FILLED", "filled")),
    ],
)
def test_a_kill_between_decision_and_fill_never_advances_the_position(offset: int, expected) -> None:
    w = build_world(4, heads=heads_with(E(4), disable_at(E(3) + offset)))
    seal = w.days[3].seal
    assert (seal.invalidated_from_ns, seal.successor_effective_at_ns) == (E(3) + offset, E(3) + offset)
    assert all_fills(w, 3)[-1][1:] == expected[1:]
    episodes = w.days[3].projection.episodes  # type: ignore[union-attr]
    assert len(episodes) == (1 if expected[1] == "FILLED" else 0)
    if expected[1] == "REJECTED":
        terminal = w.days[3].outcome.terminal_state  # type: ignore[union-attr]
        assert terminal.position_quantity == d(0) and terminal.cumulative_fees == d(0)


def test_a_later_discovered_successor_inside_a_sealed_day_is_a_contradiction() -> None:
    with refused("late_successor_contradicts_sealed_history"):
        build_world(4, heads=heads_with(E(4), disable_at(E(2) + 100)))


def test_after_a_kill_no_later_cycle_opens_and_the_position_is_never_forced() -> None:
    w = build_world(6, heads=heads_with(E(4), disable_at(E(3) + 503)))
    assert [cycle.status.value for _, cycle in w.cycles] == ["AUTHORIZED"] * 4 + ["BLOCKED"] * 2
    assert (
        "governed_paper_execution_authority:lifecycle_head_not_the_paper_genesis" in w.cycles[4][1].blocked_reason_codes
    )
    assert all(day.seal.sealed and day.seal.invalidated_from_ns == E(3) + 503 for day in w.days[3:])
    assert w.days[-1].outcome.terminal_state.position_quantity == d(-1)  # type: ignore[union-attr]


def test_an_invalidation_is_never_undone_and_each_cycle_opens_on_the_closing_attestation() -> None:
    w = build_world(5, heads=heads_with(E(4), disable_at(E(3) + 503)))
    seal_inputs = w.seals[4]
    with refused("closing_head_contradicts_the_invalidation"):
        build_governed_paper_day(replace(seal_inputs, closing_head_authority_inputs=head_at(E(5))))
    g = world_g()
    other = rg7t.head_inputs(ef8t.genesis(), authority_id="gp-head-other", evaluation_end_ns=E(5))
    cycle_inputs, cycle = approve_cycle(replace(g.cycles[5][0], head_authority_inputs=other))
    assert cycle.authorized and cycle.head_authority_digest != g.days[4].seal.closing_head_authority_digest
    with refused("cycle_not_opened_on_the_closing_attestation"):
        build_governed_paper_day(replace(g.seals[5], cycle_inputs=cycle_inputs, cycle_authority=cycle))


def test_a_delayed_book_is_final_unfilled_never_pending() -> None:
    delayed = tuple(
        book_record(k, event=E(3) + 6_000 if k == 319 else None) for k in range(FIRST_FUNDING, LAST_FUNDING)
    )
    w = build_world(5, records=records_with(books=delayed))
    assert all_fills(w, 3)[-1][1:] == ("UNFILLED", "execution_delay_expired")
    assert w.days[3].seal.pending_decision_sequence is None and w.days[3].projection.episodes == ()  # type: ignore[union-attr]


def test_a_stale_close_mark_blocks_the_seal_and_nothing_after_it_opens() -> None:
    marks = tuple(mark_record(day) for day in (*range(615, 625), *range(637, 672)))
    w = build_world(2, records=records_with(marks=marks))
    assert w.cycles[0][1].status is GovernedPaperCycleStatus.BLOCKED
    assert w.cycles[0][1].blocked_reason_codes == ("governed_paper_execution_authority:opening_mark_unavailable",)
    seal = w.days[0].seal
    assert (seal.status.value, seal.reason_codes) == ("BLOCKED", (code("day_close_mark_unavailable"),))
    assert len(w.days) == 1 and w.days[0].projection is None
    evidence = build_governed_paper_execution_evidence(w.execution_inputs())
    assert (evidence.status.value, evidence.sealed_day_count) == ("BLOCKED", 0)


def test_late_funding_during_an_open_position_makes_the_economics_uncomputable() -> None:
    late = records_with(funding={320: funding_record(320, visible_at=E(9))})
    w = build_world(6, records=late)
    seal = w.days[5].seal
    assert seal.status.value == "BLOCKED"
    assert seal.reason_codes == (
        code("economics_not_computed"),
        "historical_execution_economics:funding_coverage_incomplete",
    )


def test_the_archive_must_grow_causally() -> None:
    base = world_g().seals[3]
    for records, reason in (
        ((*base.dataset.records, mark_record(700)), "dataset_record_visible_after_closing"),
        (base.dataset.records[1:], "dataset_drops_a_sealed_record"),
    ):
        with refused(reason):
            build_governed_paper_day(replace(base, dataset=_raw_archive(records)))
    other = _raw_archive(base.dataset.records, source_reference="archive:other")
    with refused("dataset_not_of_the_archive"):
        build_governed_paper_day(replace(base, dataset=other))
    renumbered = build_world(4, records=records_with(books=renumbered_books()))
    late = book_record(0, event=E(3) - 50, sequence=2 * 319 - 1)  # visible before E_3, discovered only after it
    backfilled = _raw_archive((*renumbered.seals[3].dataset.records, late))
    with refused("dataset_record_backfilled_before_opening"):
        build_governed_paper_day(replace(renumbered.seals[3], dataset=backfilled))


def foreign_manifest_archive(as_of: int) -> HistoricalPitDataset:
    """World G's archive as of ``as_of`` under ANOTHER authenticated EF-3 manifest (world P's two-instrument chain)."""

    _, manifest, _, registry, _ = ef6t.world("multi")
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="paper-archive-foreign",
        correlation_id="corr-1",
        source_reference="archive:paper",
        rights_status="own_research",
        rights_reference="license-1",
        records=tuple(item for item in world_records() if visibility(item) <= as_of),
    )


def _raw_archive(records, *, source_reference: str = "archive:paper") -> HistoricalPitDataset:
    _, manifest, _, registry, _ = ef6t.world()
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id="paper-archive-raw",
        correlation_id=pret.CORR,
        source_reference=source_reference,
        rights_status="own_research",
        rights_reference="license-1",
        records=tuple(records),
    )


def test_the_closing_attestation_must_be_human_at_the_closing_instant_and_a_direct_successor() -> None:
    base = world_g().seals[3]
    unattested = replace(base, closing_head_authority_inputs=head_at(E(4), approval_kind=None))
    day = build_governed_paper_day(unattested)
    assert (day.seal.status.value, day.seal.reason_codes) == (
        "NEEDS_GOVERNANCE_APPROVAL",
        (code("closing_head_not_attested"),),
    )
    assert (day.projection, day.outcome, day.seal.sealed) == (None, None, False)
    with refused("closing_head_not_at_the_closing_instant"):
        build_governed_paper_day(replace(base, closing_head_authority_inputs=head_at(E(3))))
    with refused("closing_head_not_a_direct_successor_of_the_paper_genesis"):
        build_governed_paper_day(replace(base, closing_head_authority_inputs=head_at(E(4), ef8t.second_genesis())))


def test_a_rewritten_sealed_prefix_is_refused() -> None:
    base = world_g().seals[4]
    forged = reseal_seal(base.prior_seal, closing_prefix_digest="0" * 64)  # type: ignore[arg-type]
    with refused("prefix_replay_breaks_sealed_history"):
        build_governed_paper_day(replace(base, prior_seal=forged))
    windows = base.prior_seal.schedule_windows  # type: ignore[union-attr]
    dropped = reseal_seal(base.prior_seal, schedule_windows=(*windows[:3], *windows[4:]))  # type: ignore[arg-type]
    with refused("prefix_replay_breaks_sealed_history"):
        build_governed_paper_day(replace(base, prior_seal=dropped))


def test_a_same_side_add_after_a_partial_fill_is_refused_and_never_projected() -> None:
    thin = records_with(books=tuple(book_record(k, depth=30) for k in range(FIRST_FUNDING, LAST_FUNDING)))
    w = build_world(8, records=thin)
    assert all_fills(w, 3)[-1][1] == "PARTIALLY_FILLED"
    assert all_fills(w, 5)[-1][1:] == ("REJECTED", "governed_paper_same_side_add_unsupported")
    assert all_fills(w, 7)[-1][1] == "FILLED"
    assert [len(day.projection.episodes) for day in w.days] == [0, 0, 0, 1, 0, 0, 0, 1]  # type: ignore[union-attr]


def test_a_tight_band_refuses_the_exit_and_never_forces_the_position() -> None:
    w = build_world(8, genesis=variant_genesis(beta="0.000000000000000001"))
    assert all_fills(w, 3)[-1][1] == "FILLED"
    assert all_fills(w, 7)[-1][1:] == ("REJECTED", "governed_paper_price_ceiling_exceeded")
    assert w.days[7].outcome.terminal_state.position_quantity == d(-1)  # type: ignore[union-attr]


@pytest.mark.parametrize(
    "patched",
    ["fill_policy_double_fee", "reference_price", "available_units", "position", "funding_position"],
)
def test_defence_in_depth_projection_guards_fail_closed(patched: str, monkeypatch: pytest.MonkeyPatch) -> None:
    inputs = world_g().seals[5 if patched == "funding_position" else 3]
    if patched == "fill_policy_double_fee":
        real = execution.build_paper_fill_policy
        monkeypatch.setattr(execution, "build_paper_fill_policy", lambda **kw: real(**{**kw, "fee_rate_bps": "10"}))
    elif patched == "reference_price":
        real_snapshot = execution.build_paper_fill_market_snapshot
        monkeypatch.setattr(
            execution,
            "build_paper_fill_market_snapshot",
            lambda **kw: real_snapshot(**{**kw, "reference_price": d(Fraction(kw["reference_price"]) - 1)}),
        )
    elif patched == "available_units":
        real_snapshot = execution.build_paper_fill_market_snapshot
        monkeypatch.setattr(
            execution,
            "build_paper_fill_market_snapshot",
            lambda **kw: real_snapshot(**{**kw, "available_units": "0.5"}),
        )
    else:
        real_sim = execution.simulate_historical_execution_governed_paper

        def shifted(result, **kw):
            outcome = real_sim(result, **kw)
            if patched == "position":
                moved = tuple(replace(item, post_quantity=d(-2)) for item in outcome.position_transitions)
                return replace(outcome, position_transitions=moved)
            moved = tuple(replace(item, position_quantity=d(1)) for item in outcome.funding_cashflows)
            return replace(outcome, funding_cashflows=moved)

        monkeypatch.setattr(execution, "simulate_historical_execution_governed_paper", shifted)
    expected = (
        "projection_funding_position_mismatch"
        if patched == "funding_position"
        else "projection_not_exactly_the_engine_economics"
    )
    with refused(expected):
        build_governed_paper_day(inputs)


@functools.cache
def short_world() -> World:
    return build_world(6)


def test_the_evidence_refuses_any_lineage_that_is_not_the_sealed_history() -> None:
    w = short_world()
    inputs = w.execution_inputs()
    seals = inputs.seals
    with refused("seal_not_the_reconstruction"):
        build_governed_paper_execution_evidence(
            replace(inputs, seals=(*seals[:2], reseal_seal(seals[2], reason_codes=("x",)), *seals[3:]))
        )
    forged_history = replace(
        w.seals[5],
        cycle_inputs=replace(w.seals[5].cycle_inputs, sealed_episodes=w.seals[5].cycle_inputs.sealed_episodes[:-1]),
    )
    with pytest.raises((execution.GovernedPaperExecutionError, authority_module.GovernedPaperExecutionAuthorityError)):
        build_governed_paper_execution_evidence(replace(inputs, days=(*inputs.days[:5], forged_history)))
    with refused("days_malformed"):
        build_governed_paper_execution_evidence(replace(inputs, seals=seals[:-1]))
    swapped = replace(inputs, days=(inputs.days[1], *inputs.days[1:]))
    with pytest.raises((execution.GovernedPaperExecutionError, authority_module.GovernedPaperExecutionAuthorityError)):
        build_governed_paper_execution_evidence(swapped)


def test_an_unsealed_day_ends_the_lineage() -> None:
    w = short_world()
    unsealed = replace(w.seals[2], closing_head_authority_inputs=head_at(E(3), approval_kind=None))
    day = build_governed_paper_day(unsealed)
    inputs = w.execution_inputs(days=(*w.seals[:2], unsealed), seals=(*(d.seal for d in w.days[:2]), day.seal))
    evidence = build_governed_paper_execution_evidence(inputs)
    assert (evidence.status.value, evidence.sealed_day_count) == ("BLOCKED", 2)
    with refused("day_after_an_unsealed_day"):
        build_governed_paper_execution_evidence(
            w.execution_inputs(
                days=(*w.seals[:2], unsealed, w.seals[3]),
                seals=(*(d.seal for d in w.days[:2]), day.seal, w.days[3].seal),
            )
        )


def test_a_cycle_cannot_consume_a_provisional_day() -> None:
    w = world_g()
    cycle_inputs = w.cycles[7][0]
    provisional = (*cycle_inputs.sealed_episodes, *w.days[7].projection.episodes)  # type: ignore[union-attr]
    assert len(provisional) == len(cycle_inputs.sealed_episodes) + 1
    with pytest.raises(authority_module.GovernedPaperExecutionAuthorityError, match="sealed_history_after_opening"):
        build_governed_paper_cycle_authority(replace(cycle_inputs, sealed_episodes=provisional))


# --- memos, purity --------------------------------------------------------------------------------------------------


def test_the_call_site_memos_agree_with_the_real_functions() -> None:
    w = world_g()
    inputs, cycle = w.cycles[3]
    assert execution.verify_governed_paper_cycle_authority.real(cycle, inputs).intact  # type: ignore[attr-defined]
    _GP_MEMO_ENABLED[0] = False
    try:
        assert build_governed_paper_day(w.seals[3]).seal == w.days[3].seal
        assert build_governed_paper_cycle_authority(inputs) == cycle
    finally:
        _GP_MEMO_ENABLED[0] = True


def test_the_execution_module_is_pure() -> None:
    source = Path(execution.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(
                not alias.name.startswith(("time", "datetime", "random", "os", "socket")) for alias in node.names
            )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not node.module.startswith(
                ("crypto_core.execution", "crypto_core.service", "crypto_core.data.ingest")
            )
            assert node.module.split(".")[0] in (
                "__future__",
                "collections",
                "dataclasses",
                "enum",
                "fractions",
                "json",
                "typing",
                "crypto_core",
            )
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
    lowered = source.lower()
    assert not [
        token
        for token in ("bist", "borsa", "place_order", "submit_order", "wall_clock", "time.time")
        if token in lowered
    ]


@SLOW
def test_memo_free_reproof_of_world_g() -> None:
    # Every memo of THIS contract is off; world P's EF-6/EF-7/EF-8 memos stay on (their own slow tests re-prove world P
    # memo-free, and repeating that once per sealed day would not fit the weekly job).
    _GP_MEMO_ENABLED[0] = False
    try:
        w = world_g()
        inputs = w.execution_inputs()
        evidence = build_governed_paper_execution_evidence(inputs)
        assert evidence.status.value == "READY" and evidence.ordinary_cycle_count == 2
        assert execution.verify_governed_paper_execution_evidence(evidence, inputs).intact
    finally:
        _GP_MEMO_ENABLED[0] = True
