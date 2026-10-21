"""Governed admitted-variant paper execution tests (GOVERNED_PAPER_TYPED_PROVENANCE_V2).

SYNTHETIC TEST VALUES ONLY. Every price, mark, funding rate, depth, band, horizon, instant and approval here is a
synthetic test value that exercises structure. None is a production threshold, none is venue truth, and no
``HUMAN_GOVERNANCE`` record built here is a real human decision: they are synthetic PASS-branch fixtures.

World G is one integrated paper period after world P's admission horizon, built only through accepted public
builders: the governed EF-7 v2 admission of world P (``carry-sleeve-1``), its EF-8 genesis receipt, a synthetic PIT
paper archive (daily marks near 40, two-day final funding, a 10 bps book of depth 1000) that grows causally, and every
day the derived reservation, RG-4/RG-5/RG-7 and, once episodes exist, RG-3/RG-6/RG-8, the human cycle approval, the
closing attestation and the day seal. Day 0 opens at G = S0 + 635 days, the bootstrap horizon is 30 days and the
passive carry profile enters SHORT on days 3, 9, 15, 21, 27 and exits on days 7, 13, 19, 25, 31: B0 on days 0-3, B1
on days 4-29 and ORDINARY on days 30-31. RG-3 carries the genesis's derived metrics context (the section-7 chain over
the sealed history under the synthetic C7 policy of the accepted time-window fixture): no series on days 4-7, before
the first computed realized event, and the sample-eligible summary of the whole sealed history from day 8.

Cost: the world is built once per session and every pure upstream re-proof is memoized, exactly (frozen inputs, the
same objects) or by the accepted exact keys. A ``slow`` test re-proves the whole lineage memo-free.
"""

from __future__ import annotations

import functools
import json
import re
from dataclasses import dataclass, replace
from fractions import Fraction

import pytest

import crypto_core.validation.edge_kill_quarantine_decision as ef8_module
import crypto_core.validation.edge_paper_admission_decision as ef7_module
import crypto_core.validation.governed_admitted_variant_paper_execution as execution
import crypto_core.validation.governed_paper_execution_authority as authority
import crypto_core.validation.paper_portfolio_allocation_decision as rg7_module
import crypto_core.validation.paper_portfolio_governance_decision as rg8_module
from crypto_core.audit.evidence_journal import EvidenceJournal
from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.strategy.spec import strategy_spec_digest
from crypto_core.validation.deterministic_paper_replay_harness import verify_deterministic_paper_replay
from crypto_core.validation.edge_artifact_core import edge_canonical_json
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeVariantMetricsInput,
    build_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS,
    GovernedPaperDaySeal,
    GovernedPaperDaySealInputs,
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionDay,
    GovernedPaperExecutionError,
    GovernedPaperExecutionEvidence,
    GovernedPaperExecutionInputs,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_digest,
    governed_paper_execution_evidence_digest,
    governed_paper_execution_evidence_to_dict,
    verify_governed_paper_day_seal,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperApprovalKind,
    GovernedPaperCycleApproval,
    GovernedPaperCycleAuthority,
    GovernedPaperCycleInputs,
    GovernedPaperCycleStatus,
    GovernedPaperExecutionAuthorityError,
    GovernedPaperGenesis,
    GovernedPaperGenesisApproval,
    GovernedPaperGenesisInputs,
    build_governed_paper_cycle_authority,
    build_governed_paper_genesis,
    governed_paper_genesis_authority,
    governed_paper_metrics_context,
    governed_paper_reservation_plan,
    verify_governed_paper_cycle_authority,
)
from crypto_core.validation.historical_execution_economics import (
    build_historical_execution_economics,
    simulate_historical_execution_governed_paper,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionCitationKind,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from crypto_core.validation.paper_admission_ledger_bridge import append_paper_admission_record_to_evidence_journal
from crypto_core.validation.paper_capacity_gate import build_paper_capacity_gate_policy, evaluate_paper_capacity_gate
from crypto_core.validation.paper_deterministic_time_window_adapter import (
    build_paper_deterministic_time_window_evidence,
)
from crypto_core.validation.paper_end_to_end_episode import build_paper_end_to_end_episode
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_evidence_admission_record import build_paper_evidence_admission_record
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    simulate_paper_fill,
)
from crypto_core.validation.paper_governor_decision import build_paper_governor_policy, decide_paper_governor
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot
from crypto_core.validation.paper_portfolio_allocation_decision import (
    PaperPortfolioAllocationInputs,
    PaperPortfolioAllocationSleeveInputs,
    build_paper_lifecycle_head_authority,
    build_paper_portfolio_allocation_decision,
)
from crypto_core.validation.paper_portfolio_governance_decision import (
    PaperPortfolioGovernanceInputs,
    PaperPortfolioGovernanceSleeveInputs,
    build_paper_portfolio_governance_decision,
)
from crypto_core.validation.paper_position_state import (
    PaperPositionStateSide,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    build_paper_position_state,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_realized_pnl_rollup import PaperRealizedPnlRollupInput
from crypto_core.validation.paper_session_metrics_summary import summarize_paper_session_metrics
from crypto_core.validation.paper_session_realized_pnl_aggregate import (
    PaperSessionRealizedPnlAggregateInput,
    build_paper_session_realized_pnl_aggregate,
)
from crypto_core.validation.paper_session_realized_pnl_bridge import (
    PaperSessionSequenceProvenance,
    build_paper_session_realized_pnl_bridge,
)
from crypto_core.validation.paper_session_realized_pnl_evidence_manifest import (
    build_paper_session_realized_pnl_evidence_manifest,
)
from crypto_core.validation.paper_session_sequence import build_paper_session_sequence
from crypto_core.validation.paper_sharpe_evidence import build_paper_sharpe_evidence
from crypto_core.validation.paper_sleeve_correlation_evidence import (
    PaperSleeveCorrelationInputs,
    PaperSleeveCorrelationSleeveInputs,
    build_paper_sleeve_correlation_evidence,
)
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PaperSleeveValuationInputs,
    build_paper_sleeve_daily_valuation_evidence,
)
from crypto_core.validation.paper_sleeve_drawdown_evidence import (
    PaperSleeveDrawdownInputs,
    PaperSleeveDrawdownSleeveInputs,
    build_paper_sleeve_drawdown_evidence,
)
from crypto_core.validation.paper_sleeve_funding_evidence import build_paper_sleeve_funding_evidence
from crypto_core.validation.paper_sleeve_performance_evidence import (
    PaperSleevePerformanceInputs,
    PaperSleevePerformanceStatus,
    build_paper_sleeve_performance_evidence,
)
from crypto_core.validation.paper_sleeve_promotion_demotion_decision import (
    build_paper_sleeve_promotion_demotion_decision,
)
from crypto_core.validation.paper_stage4_readiness_decision import decide_paper_stage4_readiness
from crypto_core.validation.strategy_executable_profiles import (
    canonical_profile_parameter_assignment,
    get_strategy_executable_profile,
)
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent

try:  # the module objects pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_kill_quarantine_decision as ef8t
    import test_edge_paper_admission_decision as ef7t
    import test_edge_pre_paper_validation_evidence as pret
    import test_edge_walk_forward_oos_evidence as ef6t
    import test_historical_execution_economics_policy as polt
    import test_paper_portfolio_allocation_decision as rg7t
    import test_paper_portfolio_governance_decision as rg8t
    import test_paper_portfolio_risk_envelope as rg2
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
    from tests.crypto_core.validation import test_paper_sleeve_drawdown_evidence as rg4t
    from tests.crypto_core.validation import test_paper_sleeve_performance_evidence as rg3t
    from tests.crypto_core.validation import test_paper_sleeve_promotion_demotion_decision as rg6t
    from tests.crypto_core.validation import test_strategy_executable_binding as bindt

SLOW = pytest.mark.slow  # a memo-free re-proof of the whole lineage; see the module docstring
DAY, S0, INS = pret.DAY, pret.S0, pret.INS
FUNDING = pret.FUNDING
CARRY = ef7t.SLEEVE
G_DAY = 635
G = S0 + G_DAY * DAY
DAYS = 32
HORIZON_DAYS = 30
BAND = "0.100000000000000000"
HUMAN = GovernedPaperApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC
d = pret.d


def instant(day: int) -> int:
    """E_day = G + day days."""

    return G + day * DAY


# --- exact memos of pure re-proofs (frozen inputs, the very same objects) ------------------------------------------------


CONTRACT_MEMO_ENABLED = [True]


class SameObjects:
    """Memo of one pure function keyed by the IDENTITY of its frozen arguments; the arguments are kept alive."""

    def __init__(self, real) -> None:
        self.real = real
        self.cache: dict[tuple[object, ...], tuple[tuple[object, ...], object]] = {}

    def __call__(self, *args: object, **kwargs: object) -> object:
        if not CONTRACT_MEMO_ENABLED[0] or not ef6t._MEMO_ENABLED[0]:
            return self.real(*args, **kwargs)
        values = (*args, *(kwargs[name] for name in sorted(kwargs)))
        key = (len(args), tuple(sorted(kwargs)), tuple(id(item) for item in values))
        hit = self.cache.get(key)
        if hit is not None and all(left is right for left, right in zip(hit[0], values, strict=True)):
            return hit[1]
        result = self.real(*args, **kwargs)  # a raising call is never cached
        self.cache[key] = (values, result)
        return result


_SAME = {
    (module, name): SameObjects(getattr(module, name))
    for module, names in (
        (
            authority,
            (
                "build_governed_paper_genesis",
                "governed_paper_genesis_authority",
                "verify_paper_portfolio_allocation_decision",
                "verify_paper_sleeve_drawdown_evidence",
                "verify_paper_portfolio_governance_decision",
            ),
        ),
        (
            execution,
            (
                "governed_paper_genesis_authority",
                "verify_governed_paper_cycle_authority",
                "governed_paper_cycle_reservation",
                "verify_governed_paper_day_seal",
                "verify_paper_lifecycle_head_authority",
            ),
        ),
    )
    for name in names
}
_EXACT = {
    (authority, "verify_edge_paper_admission_decision"): ef8t._EF8_MEMOS["verify_edge_paper_admission_decision"],
    (authority, "verify_edge_kill_quarantine_decision"): ef8t._EF8_MEMOS["verify_edge_kill_quarantine_decision"],
    (execution, "verify_edge_kill_quarantine_decision"): ef8t._EF8_MEMOS["verify_edge_kill_quarantine_decision"],
    (authority, "verify_historical_pit_dataset"): pret._PRE_MEMOS[(pret.ev_module, "verify_historical_pit_dataset")],
    (execution, "verify_historical_pit_dataset"): pret._PRE_MEMOS[(pret.ev_module, "verify_historical_pit_dataset")],
    (execution, "build_historical_decision_run"): pret._CallMemo(execution.build_historical_decision_run),
    (execution, "build_historical_execution_economics"): pret._CallMemo(execution.build_historical_execution_economics),
}


def apply_memos(patch: pytest.MonkeyPatch) -> None:
    """Install every accepted upstream memo and this contract's exact memos (shared with the authority tests)."""

    pret.apply_memos(patch)
    for name, memo in ef7t._EF7_MEMOS.items():
        patch.setattr(ef7_module, name, memo)
    for name, memo in ef8t._EF8_MEMOS.items():
        patch.setattr(ef8_module, name, memo)
    for name in ("verify_edge_kill_quarantine_decision", "verify_edge_paper_admission_decision"):
        patch.setattr(rg7_module, name, ef8t._EF8_MEMOS[name])
    for name, memo in rg8t._RG8_MEMOS.items():
        patch.setattr(rg8_module, name, memo)
    for (module, name), memo in {**_EXACT, **_SAME}.items():
        patch.setattr(module, name, memo)


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        apply_memos(patch)
        yield


# --- the synthetic paper archive -----------------------------------------------------------------------------------------


def paper_mark(day: int) -> Fraction:
    """SYNTHETIC daily mark of absolute day ``day`` (near 40, deterministic and varying)."""

    return 40 * (1 + Fraction(5 * (((day * 7) % 5) - 2), 10_000))


def _record(series: str, key: str, sequence: int, event: int, visible: int, values: dict[str, str]):
    return build_historical_pit_record(
        series_id=series,
        data_requirement_key=key,
        instrument=INS,
        sequence_id=sequence,
        event_time_ns=event,
        available_at_ns=visible - 1,
        finalized_at_ns=visible,
        revision_vintage_id=None,
        values=tuple(HistoricalPitValue(name, value) for name, value in sorted(values.items())),
    )


def book_values(time_ns: int) -> dict[str, str]:
    mid = paper_mark((time_ns - S0) // DAY)
    return {
        "best_bid_price": d(mid * (1 - Fraction(5, 10_000))),
        "best_ask_price": d(mid * (1 + Fraction(5, 10_000))),
        "best_bid_quantity": d(1000),
        "best_ask_quantity": d(1000),
    }


def funding_record(k: int, rate: str | None = None):
    """Final funding record ``k``: event S0 + (k - 1) * FUNDING, final at its liability + 10 ns."""

    return build_historical_pit_record(
        series_id="funding-final",
        data_requirement_key="funding_rate",
        instrument=INS,
        sequence_id=k,
        event_time_ns=S0 + (k - 1) * FUNDING,
        available_at_ns=S0 + k * FUNDING + 10,
        finalized_at_ns=S0 + k * FUNDING + 10,
        revision_vintage_id=None,
        values=(HistoricalPitValue("funding_rate", pret._rate(k) if rate is None else rate),),
    )


def mark_record(day: int, price: Fraction | None = None):
    event = S0 + day * DAY - 1_000
    return _record(
        "mark", "mark_price", day, event, event + 2, {"mark_price": d(paper_mark(day) if price is None else price)}
    )


def book_record(k: int, event: int | None = None):
    event = S0 + k * FUNDING + 500 if event is None else event
    return _record("book", "order_book", k, event, event + 2, book_values(event))


@functools.cache
def paper_records() -> tuple:
    funding = tuple(funding_record(k) for k in range(316, 340))
    marks = tuple(mark_record(day) for day in range(G_DAY - 12, G_DAY + DAYS + 4))
    books = tuple(book_record(k) for k in range(316, 340))
    return (*funding, *marks, *books)


def visibility(record: object) -> int:
    return max(record.available_at_ns, record.finalized_at_ns)  # type: ignore[attr-defined]


def archive_of(dataset_id: str, records: tuple) -> HistoricalPitDataset:
    _, manifest, _, registry, _ = ef6t.world()
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id=dataset_id,
        correlation_id=pret.CORR,
        source_reference="archive:paper-period",
        rights_status="own_research",
        rights_reference="license-1",
        records=records,
    )


@functools.cache
def archive(day: int, name: str = "G") -> HistoricalPitDataset:
    """The archive of scenario ``name`` sealed at E_(day + 1): exactly the records known then (day -1: at G)."""

    end = instant(day + 1)
    return archive_of(
        f"paper-archive-{name}-{day}", tuple(item for item in scenario(name).records if visibility(item) <= end)
    )


@functools.cache
def negated_records() -> tuple:
    """World G's archive with every funding rate negated: the carry profile enters LONG instead of SHORT."""

    funding = tuple(
        funding_record(k, d(-Fraction(pret._rate(k))) if Fraction(pret._rate(k)) else None) for k in range(316, 340)
    )
    return (*funding, *(item for item in paper_records() if item.series_id != "funding-final"))


INEXACT_MARK = Fraction("40.0000000000000001")  # SYNTHETIC: q * m * r at rate 0.0045 needs 20 decimal places


@functools.cache
def inexact_records() -> tuple:
    """B4: world G with the settlement of k = 320 (day 5) on an inexact mark and rate, so -q*m*r is not scale-18."""

    replaced = {("funding-final", 320): funding_record(320, d("0.0045")), ("mark", 640): mark_record(640, INEXACT_MARK)}
    return tuple(replaced.get((item.series_id, item.sequence_id), item) for item in paper_records())


@functools.cache
def cancelling_records() -> tuple:
    """B4: two inexact settlements (days 5 and 7, k = 320 and 321) whose rounding remainders cancel exactly."""

    replaced = {
        ("funding-final", 320): funding_record(320, d("0.0045")),
        ("mark", 640): mark_record(640, INEXACT_MARK),
        ("funding-final", 321): funding_record(321, d("-0.0045")),
        ("mark", 642): mark_record(642, INEXACT_MARK),
    }
    return tuple(replaced.get((item.series_id, item.sequence_id), item) for item in paper_records())


@functools.cache
def delayed_records() -> tuple:
    """B3: world G with the book after the day-3 decision delayed to day 5 (decided k, pending k + 1, filled k + 2)."""

    delayed = book_record(319, event=instant(5) + 5)
    return tuple(delayed if (item.series_id, item.sequence_id) == ("book", 319) else item for item in paper_records())


# --- the genesis -----------------------------------------------------------------------------------------------------------


@functools.cache
def environment():  # noqa: ANN201 - the shared synthetic governance environment of the carry sleeve
    env = rg7t.solo_envelope()
    basis = rg3t.world.basis_policy(sleeve_id=CARRY, market_symbol=INS, reference_notional="10000")
    seed = rg6t.human_seed(env, G, CARRY)
    path = rg4t.policy_for(env, ((CARRY, "1"),))
    return env, basis, seed, path


def assignment():  # noqa: ANN201
    _, _, _, _, binding = ef6t.world()
    profile = get_strategy_executable_profile(binding.profile_id)
    return tuple(canonical_profile_parameter_assignment(profile, pret.params_p()))


@functools.cache
def governor_policy(**overrides: object):  # noqa: ANN201
    """SYNTHETIC C7: the accepted time-window fixture's governor thresholds, never governed values.

    ``overrides`` builds a SYNTHETIC variant that exercises one metrics-context branch; no variant is a threshold.
    """

    accepted = rg3t.world.window_support._gov_policy()  # noqa: SLF001 - the accepted fixture's synthetic C7
    values: dict[str, object] = {
        "policy_id": accepted.policy_id,
        "min_computed_event_count": accepted.min_computed_event_count,
        "max_abs_realized_pnl": accepted.max_abs_realized_pnl,
        "review_abs_realized_pnl": accepted.review_abs_realized_pnl,
        "max_closed_units": accepted.max_closed_units,
    }
    if not overrides:
        return accepted
    values.update(overrides)
    return build_paper_governor_policy(**values)  # type: ignore[arg-type]


def genesis_arguments(**overrides: object) -> dict[str, object]:
    intake, _, _, registry, binding = ef6t.world()
    admission = ef7t.admitted()
    lifecycle = ef8t.genesis()
    policy = pret.economics_policy_p()
    env, basis, seed, path = environment()
    params = assignment()
    values: dict[str, object] = {
        "genesis_id": "gpe-genesis-1",
        "genesis_version": "synthetic-v1",
        "correlation_id": "corr-gpe-genesis",
        "paper_admission": admission,
        "expected_paper_admission_digest": admission.paper_admission_decision_digest,
        "lifecycle_genesis": lifecycle,
        "expected_lifecycle_genesis_digest": lifecycle.kill_quarantine_decision_digest,
        "executable_binding": binding,
        "admitted_variant_id": pret.BASE_VARIANT,
        "parameter_assignment": params,
        "parameter_approval": bindt.parameter_approval_for(binding, params),
        "economics_policy": policy,
        "economics_approval": polt.approval_for(
            policy,
            strategy_spec_digest=binding.strategy_spec_digest,
            data_requirement_registry_digest=data_requirement_registry_digest(registry),
            approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
        ),
        "portfolio_risk_envelope": env,
        "equity_basis_policy": basis,
        "ladder_seed": seed,
        "performance_path_policy": path,
        "metrics_governor_policy": governor_policy(),
        "genesis_start_ns": G,
        "bootstrap_horizon_days": HORIZON_DAYS,
        "reservation_band": BAND,
        "approval": None,
    }
    values.update(overrides)
    return values


def genesis_approval_for(
    inputs: GovernedPaperGenesisInputs, *, kind: object = HUMAN, **overrides: object
) -> GovernedPaperGenesisApproval:
    """SYNTHETIC: the exact commitments a human reviews before adopting one paper genesis (C1, C2)."""

    draft = build_governed_paper_genesis(replace(inputs, approval=None))
    values: dict[str, object] = {
        "approval_reference": "synthetic-genesis-adoption-1",
        "approval_digest": "d" * 64,
        "approval_kind": kind,
        "approved_genesis_id": draft.genesis_id,
        "approved_genesis_version": draft.genesis_version,
        "approved_genesis_policy_digest": draft.genesis_policy_digest,
        "approved_rule_set_digest": draft.rule_set_digest,
    }
    values.update(overrides)
    return GovernedPaperGenesisApproval(**values)  # type: ignore[arg-type]


def governed_genesis_inputs(**overrides: object) -> GovernedPaperGenesisInputs:
    inputs = GovernedPaperGenesisInputs(**genesis_arguments(**overrides))  # type: ignore[arg-type]
    return replace(inputs, approval=genesis_approval_for(inputs))


@functools.cache
def world_genesis() -> tuple[GovernedPaperGenesisInputs, GovernedPaperGenesis]:
    inputs = governed_genesis_inputs()
    return inputs, build_governed_paper_genesis(inputs)


# --- scenarios ------------------------------------------------------------------------------------------------------------


@functools.cache
def budget50_admission():  # noqa: ANN201
    """B2: world P's EF-7 v2 under an EF-7-bound total budget of 50, which reserves BUY but blocks SELL."""

    policy = ef7t.budget_policy(CARRY, total_budget="50")
    arguments = {
        "risk_budget_policy": policy,
        "expected_risk_budget_policy_digest": policy.policy_digest,
        "decision_id": "ef7-gpe-b50",
    }
    draft = ef7t.decide(ef7t.passing_chain(), **arguments)
    return ef7t.decide(ef7t.passing_chain(), **arguments, governance=ef7t.approval_for(draft))


@functools.cache
def delay_policy():  # noqa: ANN201
    """B3: world P's economics policy with a SYNTHETIC 3-day maximum execution delay (a pending intent may span days)."""

    return polt.cited_policy(
        kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED,
        funding_interval_ns=FUNDING,
        max_mark_staleness_ns=11 * DAY,
        taker_fee_bps=d(5),
        impact_coefficient_bps_per_participation_pct=d(2),
        max_execution_delay_ns=3 * DAY,
    )


def economics_approval(policy: object):  # noqa: ANN201
    _, _, _, registry, binding = ef6t.world()
    return polt.approval_for(
        policy,
        strategy_spec_digest=binding.strategy_spec_digest,
        data_requirement_registry_digest=data_requirement_registry_digest(registry),
        approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
    )


@functools.cache
def delay_economics(start_day: int, days: int, unit: str):  # noqa: ANN201
    """World P's segment economics under the delay policy (the decision runs are world P's own)."""

    _, _, _, _, binding = ef6t.world()
    run = pret.runt.decision_run(
        pret.dataset_p(start_day, days),
        binding,
        instrument=INS,
        evaluation_start_ns=S0 + start_day * DAY,
        evaluation_end_ns=S0 + (start_day + days) * DAY,
        parameter_assignment=pret.params_p(unit),
        run_id=f"run-p-{start_day}-{days}-{unit}",
    )
    policy = delay_policy()
    return build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=economics_approval(policy),
        result_id=f"run-delay-{start_day}-{days}-{unit}-economics",
        correlation_id=pret.CORR,
    )


@functools.cache
def delay_admission():  # noqa: ANN201
    """B3: the whole EF-6 -> pre-paper -> EF-7 v2 chain of world P re-run under the delay policy."""

    windows = {
        unit: pret.mt.build(
            tuple(
                pret.mt.window(
                    f"wf-{index + 1}", delay_economics(start, 365, unit), delay_economics(start + 365, 90, unit)
                )
                for index, start in enumerate(pret.STARTS)
            ),
            result_id=f"wf-delay-{unit}",
        )
        for unit in pret.UNITS
    }
    predecessor = pret.ef5_p()
    arguments = {
        "expected_predecessor_digest": predecessor.leakage_bias_evidence_digest,
        "expected_root_intake_digest": ef6t.world()[0].intake_digest,
        "variant_metrics": tuple(
            EdgeVariantMetricsInput(windows[unit], windows[unit].result_digest) for unit in pret.UNITS
        ),
        "evidence_id": "ef6-gpe-delay",
        "correlation_id": pret.CORR,
    }
    draft = build_edge_walk_forward_oos_evidence(predecessor, **arguments)  # type: ignore[arg-type]
    ef6 = build_edge_walk_forward_oos_evidence(predecessor, **arguments, governance=ef6t.governance_for(draft))  # type: ignore[arg-type]
    decision = ef7t.decide(ef6, decision_id="ef7-gpe-delay")
    return ef7t.decide(ef6, decision_id="ef7-gpe-delay", governance=ef7t.approval_for(decision))


@dataclass(frozen=True)
class Scenario:
    """One synthetic paper world: a governed genesis, its archive records and its EF-8 lifecycle receipts."""

    name: str
    genesis_inputs: GovernedPaperGenesisInputs
    genesis: GovernedPaperGenesis
    records: tuple
    receipts: tuple

    def head_at(self, at_ns: int):  # noqa: ANN201
        return [item for item in self.receipts if item.effective_at_ns <= at_ns][-1]

    def successors(self, day: int) -> tuple:
        return tuple(item for item in self.receipts[1:] if instant(day) < item.effective_at_ns <= instant(day + 1))


def scenario_genesis(name: str, admission: object, receipt: object, policy: object):  # noqa: ANN201
    inputs = governed_genesis_inputs(
        genesis_id=f"gpe-genesis-{name}",
        paper_admission=admission,
        expected_paper_admission_digest=admission.paper_admission_decision_digest,  # type: ignore[attr-defined]
        lifecycle_genesis=receipt,
        expected_lifecycle_genesis_digest=receipt.kill_quarantine_decision_digest,  # type: ignore[attr-defined]
        economics_policy=policy,
        economics_approval=economics_approval(policy),
    )
    return inputs, build_governed_paper_genesis(inputs)


@functools.cache
def carry_envelope(cap: str = "400", stops: tuple[str, ...] | None = None):  # noqa: ANN201
    """A SYNTHETIC governed RG-2 envelope declaring the carry sleeve alone (the defaults equal RG-7's solo one)."""

    overrides: dict[str, object] = {
        "total_paper_risk_budget": rg2.d("1000"),
        "sleeve_caps": [rg2.sleeve(CARRY, cap)],
        "market_caps": [rg2.market(market, value) for market, value in rg7t.MARKETS],
        "max_sleeve_count": 1,
        "correlation_cap": rg2.correlation("0.6", 30, 20),
    }
    if stops is not None:
        overrides["portfolio_stop_levels"] = [rg2.stop(level, text) for level, text in enumerate(stops, 1)]
    return rg2.governed(**overrides)


@functools.cache
def envelope_genesis(name: str, env: object):  # noqa: ANN201
    """World G's genesis on another envelope (its seed and path policy re-bound to that envelope)."""

    inputs = governed_genesis_inputs(
        genesis_id=f"gpe-genesis-{name}",
        portfolio_risk_envelope=env,
        ladder_seed=rg6t.human_seed(env, G, CARRY),
        performance_path_policy=rg4t.policy_for(env, ((CARRY, "1"),)),
    )
    return inputs, build_governed_paper_genesis(inputs)


@functools.cache
def flip_records() -> tuple:
    """World G with a negative final rate at k = 320 (day 5): the SHORT pays, then exits on the sign flip."""

    flipped = funding_record(320, d("-0.002"))
    return tuple(
        flipped if (item.series_id, item.sequence_id) == ("funding-final", 320) else item for item in paper_records()
    )


@functools.cache
def kill_receipt(offset_ns: int):  # noqa: ANN201
    """X2: an authentic EF-8 kill of the genesis head effective ``offset_ns`` after the day-3 cycle opens."""

    return ef8t.disable(
        ef8t.genesis(), effective_at_ns=instant(3) + offset_ns, decision_id=f"ef8-disable-gpe-{offset_ns}"
    )


@functools.cache
def scenario(name: str) -> Scenario:
    """The named synthetic worlds; every one but ``G`` differs from world G in exactly the stated input."""

    inputs, record = world_genesis()
    genesis_receipt = ef8t.genesis()
    if name == "G":
        return Scenario(name, inputs, record, paper_records(), (genesis_receipt,))
    if name == "long":
        return Scenario(name, inputs, record, negated_records(), (genesis_receipt,))
    if name == "inexact":
        return Scenario(name, inputs, record, inexact_records(), (genesis_receipt,))
    if name == "cancel":
        return Scenario(name, inputs, record, cancelling_records(), (genesis_receipt,))
    if name.startswith("kill-"):
        return Scenario(name, inputs, record, paper_records(), (genesis_receipt, kill_receipt(int(name[5:]))))
    if name in ("b50-short", "b50-long"):
        admission = budget50_admission()
        receipt = ef8t.activate(admission, decision_id="ef8-activate-gpe-b50")
        b50 = scenario_genesis("b50", admission, receipt, pret.economics_policy_p())
        return Scenario(name, *b50, paper_records() if name == "b50-short" else negated_records(), (receipt,))
    if name == "flip":
        return Scenario(name, inputs, record, flip_records(), (genesis_receipt,))
    if name == "stop":
        stopped = envelope_genesis(name, carry_envelope(stops=("0.000001", "0.1", "0.15")))
        return Scenario(name, *stopped, paper_records(), (genesis_receipt,))
    if name == "rejected":
        return Scenario(name, *envelope_genesis(name, carry_envelope(cap="300")), paper_records(), (genesis_receipt,))
    if name == "delay":
        admission = delay_admission()
        receipt = ef8t.activate(admission, decision_id="ef8-activate-gpe-delay")
        return Scenario(
            name, *scenario_genesis("delay", admission, receipt, delay_policy()), delayed_records(), (receipt,)
        )
    raise AssertionError(f"unknown scenario {name}")


# --- one day: the cycle at E_k and the seal at E_(k+1) ----------------------------------------------------------------------


def head_inputs(evaluation_end_ns: int, head: object | None = None):  # noqa: ANN201
    receipt = ef8t.genesis() if head is None else head
    return rg7t.head_inputs(receipt, evaluation_end_ns=evaluation_end_ns, authority_id=f"gpe-head-{evaluation_end_ns}")


@dataclass(frozen=True)
class Governance:
    """Every upstream governance artifact a cycle at E_k consumes."""

    allocation_inputs: PaperPortfolioAllocationInputs
    allocation: object
    drawdown_inputs: PaperSleeveDrawdownInputs | None
    drawdown: object | None
    governance_inputs: PaperPortfolioGovernanceInputs | None
    governance: object | None


@functools.cache
def foreign_summary():  # noqa: ANN201 - a self-consistent metrics summary that is not the sleeve's own
    """A FOREIGN metrics summary: one genuine deterministic paper chain re-targeted to the carry market.

    It mirrors the accepted time-window fixture chain (aggregate, manifest, ledger bridge, governor, replay, Stage-4
    readiness, summary) on ``INS`` under the same synthetic C7 policy. It is READY and digest-valid, but none of its
    episodes was sealed by the genesis, so no governed cycle may accept it as the sleeve's metrics context.
    """

    support = rg3t.world.window_support
    spec = governed_paper_genesis_authority(*reversed(world_genesis())).strategy_spec
    capacity = evaluate_paper_capacity_gate(
        support._make_draft(),  # noqa: SLF001 - the accepted fixture draft of the time-window chain
        build_paper_capacity_gate_policy(
            policy_id="policy-alpha",
            sleeve_id="sleeve-alpha",
            max_notional="100000000",
            max_units="100000",
            max_open_intents=5,
        ),
        requested_notional="200",
        requested_units="4",
        correlation_id="corr-capacity",
    )

    def order_intent(intent_id: str):  # noqa: ANN202
        request = build_paper_order_intent_request(
            request_id="req-1",
            capacity_decision_digest=capacity.decision_digest,
            market_symbol=INS,
            side=PaperOrderSide.SELL,
            intent_type=PaperOrderIntentType.MARKET,
            requested_notional=capacity.requested_notional,
            requested_units=capacity.requested_units,
            limit_price=None,
            correlation_id="corr-req",
        )
        admission = evaluate_paper_order_intent_admission(capacity, request, correlation_id="corr-admit")
        return build_paper_order_intent(admission, intent_id=intent_id, correlation_id="corr-intent")

    run_id, corr = support._RUN, support._CORR  # noqa: SLF001
    bridge = build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=strategy_spec_digest(spec),
        signal_id="req-1",
        run_id=run_id,
        correlation_id="corr-req",
        market_symbol=INS,
        side=PaperOrderSide.SELL,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units=capacity.requested_units,
        requested_notional=capacity.requested_notional,
        capacity_decision_digest=capacity.decision_digest,
        limit_price=None,
    )
    intent = order_intent("intent-1")
    prior = build_paper_position_state(
        position_state_id="pos-1",
        market_symbol=INS,
        side=PaperPositionStateSide.LONG,
        signed_units="10",
        abs_units="10",
        average_entry_price="100",
        transition_count=0,
        correlation_id="corr-pos",
    )
    snapshot = build_paper_fill_market_snapshot(snapshot_id="snap-1", market_symbol=INS, reference_price="50")
    fill_policy = build_paper_fill_policy(
        policy_id="fill-policy-1", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id="mark-1", market_symbol=INS, mark_price="60", correlation_id="corr-mark"
    )
    ids = support._CHAIN_IDS  # noqa: SLF001
    episode_run = run_paper_episode(intent, prior, snapshot, fill_policy, mark, **ids)  # type: ignore[arg-type]
    fill = simulate_paper_fill(
        intent, snapshot, fill_policy, fill_simulation_id=ids["fill_simulation_id"], correlation_id=corr
    )
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=corr,
    )
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id="rpnl-1", correlation_id=corr
    )
    episode = build_paper_end_to_end_episode(
        bridge,
        intent,
        episode_run,
        event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=intent.intent_digest,
        expected_episode_run_digest=episode_run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=support._EPISODE_ID,  # noqa: SLF001
        run_id=run_id,
        correlation_id=corr,
    )
    flat = build_flat_paper_position_state(position_state_id="pos-m", market_symbol=INS, correlation_id="corr-pos")
    session_episode = run_paper_episode(
        order_intent("intent-m"),
        flat,
        build_paper_fill_market_snapshot(snapshot_id="snap-m", market_symbol=INS, reference_price="50"),
        build_paper_fill_policy(
            policy_id="fill-policy-m", slippage_bps="0", fee_rate_bps="0", allow_partial_fill=False
        ),
        build_paper_mark_snapshot(
            mark_snapshot_id="mark-m", market_symbol=INS, mark_price="60", correlation_id="corr-mark"
        ),
        fill_simulation_id="fillsim-m",
        position_transition_id="trans-m",
        new_position_state_id="newpos-m",
        pnl_report_id="pnl-m",
        episode_run_id="ep-m",
        correlation_id="corr-ep",
    )
    session = build_paper_session_sequence([session_episode], paper_session_id="sess-1", correlation_id="corr-sess-1")
    provenance = PaperSessionSequenceProvenance(session_sequence=session, episodes=(session_episode,))
    rollup = PaperRealizedPnlRollupInput(
        event=event, prior_state=prior, fill_result=fill, transition=transition, new_position_state=new_state
    )
    session_bridge = build_paper_session_realized_pnl_bridge(
        provenance, (rollup,), bridge_id="bridge-1", correlation_id="corr-bridge"
    )
    aggregate = build_paper_session_realized_pnl_aggregate(
        [
            PaperSessionRealizedPnlAggregateInput(
                bridge=session_bridge, session_input=provenance, rollup_entries=(rollup,)
            )
        ],
        aggregate_id=support._AGG_ID,  # noqa: SLF001
        correlation_id="corr-agg",
    )
    manifest = build_paper_session_realized_pnl_evidence_manifest(
        aggregate, expected_aggregate_digest=aggregate.aggregate_digest, correlation_id="corr-manifest"
    )
    record = build_paper_evidence_admission_record(
        manifest, expected_manifest_digest=manifest.manifest_digest, correlation_id=corr
    )
    journal = EvidenceJournal()
    ledger = append_paper_admission_record_to_evidence_journal(
        journal,
        record,
        episode,
        manifest,
        expected_admission_digest=record.admission_digest,
        expected_episode_digest=episode.episode_digest,
        expected_prior_journal_head_digest=journal.head_digest,
        episode_id=support._EPISODE_ID,  # noqa: SLF001
        run_id=run_id,
        correlation_id=corr,
    )
    governor = decide_paper_governor(
        ledger,
        governor_policy(),  # the same SYNTHETIC C7 governor thresholds as the genesis
        expected_ledger_bridge_digest=ledger.ledger_digest,
        episode_id=support._EPISODE_ID,  # noqa: SLF001
        run_id=run_id,
        correlation_id=corr,
    )
    replay = verify_deterministic_paper_replay(
        governor,
        governor,
        expected_original_digest=governor.decision_digest,
        expected_replay_digest=governor.decision_digest,
        run_id=run_id,
        episode_id=support._EPISODE_ID,  # noqa: SLF001
        correlation_id=corr,
    )
    readiness = decide_paper_stage4_readiness(
        replay,
        governor,
        expected_replay_result_digest=replay.replay_result_digest,
        expected_governor_decision_digest=governor.decision_digest,
        run_id=run_id,
        episode_id=support._EPISODE_ID,  # noqa: SLF001
        correlation_id=corr,
    )
    return summarize_paper_session_metrics(
        aggregate,
        manifest,
        readiness,
        expected_session_aggregate_digest=aggregate.aggregate_digest,
        expected_evidence_manifest_digest=manifest.manifest_digest,
        expected_readiness_decision_digest=readiness.readiness_decision_digest,
        run_id=run_id,
        aggregate_id=aggregate.aggregate_id,
        correlation_id=corr,
    )


def series_world_for(valuation: object, basis: object, start: int, end: int, summary: object):  # noqa: ANN201
    """RG-3's generic series inputs over ``valuation`` and ``summary``, all under the summary's run and correlation.

    The accepted chain pins one correlation: the summary's equals the window's, the methodology's, the series' and the
    Sharpe's, and RG-3 requires the series' to equal the valuation's.
    """

    correlation = summary.correlation_id  # type: ignore[attr-defined]
    methodology = rg3t.methodology_for(basis, correlation_id=correlation)  # type: ignore[arg-type]
    window = build_paper_deterministic_time_window_evidence(
        summary,  # type: ignore[arg-type]
        expected_metrics_summary_digest=summary.summary_digest,  # type: ignore[attr-defined]
        started_at_ns=start,
        stopped_at_ns=end,
        window_id="window-sleeve",
        methodology_id=methodology.methodology_id,
        run_id=summary.run_id,  # type: ignore[attr-defined]
        aggregate_id=summary.aggregate_id,  # type: ignore[attr-defined]
        correlation_id=correlation,
        sample_observation_count=(end - start) // DAY,
    )
    series = rg3t.series_for(valuation, methodology, window, correlation_id=correlation)  # type: ignore[arg-type]
    sharpe = build_paper_sharpe_evidence(
        series,
        expected_daily_return_series_digest=series.series_digest,
        risk_free_policy_id=rg3t.RISK_FREE_POLICY_ID,
        sharpe_evidence_id="sleeve-sharpe-1",
        paper_id="sleeve-paper-1",
        correlation_id=correlation,
    )
    return rg3t.SeriesWorld(methodology, summary, window, series, sharpe)  # type: ignore[arg-type]


DERIVED = object()  # the metrics context a world's RG-3 carries by default: the genesis's own derivation


def metrics_context_of(seal: GovernedPaperDaySeal, *, world: Scenario | None = None):  # noqa: ANN201
    """The RG-3 metrics context the genesis derives over the history ``seal`` closed (the cycle's own derivation)."""

    world = scenario("G") if world is None else world
    return governed_paper_metrics_context(world.genesis, world.genesis_inputs, sealed_episodes=seal.episodes)


def performance_world(  # noqa: ANN201
    day: int, seal: GovernedPaperDaySeal, *, world: Scenario | None = None, metrics_summary: object = DERIVED
):
    """RG-3 over the history sealed before E_day (window [G, E_day)) on the genesis's envelope and basis policy.

    By default RG-3 carries the derived metrics context: its sample-eligible summary, or no series at all. A test may
    supply another ``metrics_summary`` (None: no series) to prove the cycle refuses it. RG-3 is identified by the
    carried summary's correlation, else by the first sealed episode's (the derivation's anchor).
    """

    world = scenario("G") if world is None else world
    if metrics_summary is DERIVED:
        metrics_summary = metrics_context_of(seal, world=world).series_summary
    correlation = (
        seal.episodes[0].end_to_end_episode.correlation_id
        if metrics_summary is None
        else metrics_summary.correlation_id  # type: ignore[attr-defined]
    )
    genesis_inputs = world.genesis_inputs
    env, basis = genesis_inputs.portfolio_risk_envelope, genesis_inputs.equity_basis_policy
    end = instant(day)
    funding = build_paper_sleeve_funding_evidence(
        evidence_id=f"gpe-funding-{day}",
        sleeve_id=CARRY,
        market_symbol=INS,
        window_start_ns=G,
        window_end_ns=end,
        events=seal.funding_events,
    )
    valuation_inputs = PaperSleeveValuationInputs(
        valuation_id=f"gpe-valuation-{day}",
        correlation_id=correlation,
        equity_basis_policy=basis,
        window_start_ns=G,
        window_end_ns=end,
        episodes=seal.episodes,
        day_closes=seal.day_closes,
        funding_evidence=funding,
    )
    valuation = build_paper_sleeve_daily_valuation_evidence(valuation_inputs)
    series = (
        dict.fromkeys(("methodology", "metrics_summary", "time_window", "daily_return_series", "sharpe_evidence"))
        if metrics_summary is None
        else series_world_for(valuation, basis, G, end, metrics_summary).inputs()
    )
    inputs = PaperSleevePerformanceInputs(
        performance_evidence_id=f"gpe-rg3-{day}",
        correlation_id=correlation,
        portfolio_risk_envelope=env,
        valuation_inputs=valuation_inputs,
        valuation=valuation,
        **series,  # type: ignore[arg-type]
    )
    return inputs, build_paper_sleeve_performance_evidence(inputs)


def governance_at(
    day: int,
    plan: object,
    prior: GovernedPaperDaySeal | None,
    *,
    world: Scenario | None = None,
    metrics_summary: object = DERIVED,
) -> Governance:
    """RG-4/RG-5/RG-7 at E_day and, once an episode is sealed, RG-3/RG-6/RG-8 (B0 supplies no sleeve evidence).

    Every RG artifact is built on the genesis's own envelope, seed, path policy and basis policy; RG-3 carries
    ``metrics_summary`` (by default the derived metrics context, see ``performance_world``).
    """

    world = scenario("G") if world is None else world
    genesis_inputs = world.genesis_inputs
    env, seed, path = (
        genesis_inputs.portfolio_risk_envelope,
        genesis_inputs.ladder_seed,
        genesis_inputs.performance_path_policy,
    )
    end = instant(day)
    performance = (
        None
        if prior is None or not prior.episodes
        else performance_world(day, prior, world=world, metrics_summary=metrics_summary)
    )
    sleeves = () if performance is None else (performance,)
    correlation_inputs = PaperSleeveCorrelationInputs(
        correlation_evidence_id=f"gpe-rg5-{day}",
        correlation_id="corr-gpe-rg5",
        portfolio_risk_envelope=env,
        evaluation_end_ns=end,
        sleeves=tuple(PaperSleeveCorrelationSleeveInputs(*item) for item in sleeves),
    )
    correlation = build_paper_sleeve_correlation_evidence(correlation_inputs)
    drawdown_inputs = None
    if day > 0:  # RG-4 needs a non-empty window [G, E_day)
        drawdown_inputs = PaperSleeveDrawdownInputs(
            drawdown_evidence_id=f"gpe-rg4-{day}",
            correlation_id="corr-gpe-rg4",
            portfolio_risk_envelope=env,
            performance_path_policy=path,
            window_start_ns=G,
            window_end_ns=end,
            sleeves=tuple(PaperSleeveDrawdownSleeveInputs(*item) for item in sleeves),
        )
    drawdown = None if drawdown_inputs is None else build_paper_sleeve_drawdown_evidence(drawdown_inputs)
    authority_inputs = head_inputs(end, world.head_at(end))
    subject = PaperPortfolioAllocationSleeveInputs(
        sleeve_id=CARRY,
        paper_admission=world.genesis_inputs.paper_admission,
        lifecycle_head_authority_inputs=authority_inputs,
        lifecycle_head_authority=build_paper_lifecycle_head_authority(authority_inputs),
        risk_budget_state=plan.state,  # type: ignore[attr-defined]
        risk_budget_policy=plan.risk_budget_policy,  # type: ignore[attr-defined]
        risk_budget_decision=plan.risk_budget_decision,  # type: ignore[attr-defined]
    )
    allocation_inputs = PaperPortfolioAllocationInputs(
        allocation_id=f"gpe-rg7-{day}",
        correlation_id="corr-gpe-rg7",
        portfolio_risk_envelope=env,
        evaluation_end_ns=end,
        sleeves=(subject,),
        correlation_inputs=correlation_inputs,
        correlation_evidence=correlation,
    )
    allocation = build_paper_portfolio_allocation_decision(allocation_inputs)
    if performance is None:
        return Governance(allocation_inputs, allocation, drawdown_inputs, drawdown, None, None)
    ladder_inputs = rg6t.inputs_for(
        seed,
        rg6t.Evidence(rg4t.SleeveWorld(*performance), drawdown_inputs, drawdown, correlation_inputs, correlation),
        decision_id=f"gpe-rg6-{day}",
        correlation_id="corr-gpe-rg6",
        evaluation_end_ns=end,
    )
    ladder = build_paper_sleeve_promotion_demotion_decision(ladder_inputs)
    governance_inputs = PaperPortfolioGovernanceInputs(
        governance_decision_id=f"gpe-rg8-{day}",
        correlation_id="corr-gpe-rg8",
        portfolio_risk_envelope=env,
        evaluation_end_ns=end,
        drawdown_inputs=drawdown_inputs,
        drawdown_evidence=drawdown,
        sleeves=(PaperPortfolioGovernanceSleeveInputs(CARRY, ladder_inputs, ladder),),
        allocation_inputs=allocation_inputs,
        allocation_decision=allocation,
    )
    return Governance(
        allocation_inputs,
        allocation,
        drawdown_inputs,
        drawdown,
        governance_inputs,
        build_paper_portfolio_governance_decision(governance_inputs),
    )


def cycle_approval_for(
    inputs: GovernedPaperCycleInputs, *, kind: object = HUMAN, **overrides: object
) -> GovernedPaperCycleApproval:
    """SYNTHETIC: the exact commitments a human reviews before opening one paper cycle (C3)."""

    draft = build_governed_paper_cycle_authority(replace(inputs, approval=None))
    values: dict[str, object] = {
        "approval_reference": f"synthetic-cycle-approval-{inputs.day_index}",
        "approval_digest": "e" * 64,
        "approval_kind": kind,
        "approved_cycle_id": draft.cycle_id,
        "approved_cycle_policy_digest": draft.cycle_policy_digest,
        "approved_rule_set_digest": draft.rule_set_digest,
    }
    values.update(overrides)
    return GovernedPaperCycleApproval(**values)  # type: ignore[arg-type]


def reservation_plan(day: int, world: Scenario, dataset: HistoricalPitDataset | None = None):  # noqa: ANN201
    return governed_paper_reservation_plan(
        world.genesis,
        world.genesis_inputs,
        cycle_id=f"gpe-cycle-{day}",
        correlation_id="corr-gpe-cycle",
        day_index=day,
        reservation_dataset=archive(day - 1, world.name) if dataset is None else dataset,
    )


def cycle_inputs_for(
    day: int,
    prior: GovernedPaperDaySeal | None,
    *,
    world: Scenario | None = None,
    reservation_dataset: HistoricalPitDataset | None = None,
    governance: Governance | None = None,
    approved: bool = True,
) -> GovernedPaperCycleInputs:
    world = scenario("G") if world is None else world
    dataset = archive(day - 1, world.name) if reservation_dataset is None else reservation_dataset
    if governance is None:
        governance = governance_at(day, reservation_plan(day, world, dataset), prior, world=world)
    history = ((), (), ()) if prior is None else (prior.episodes, prior.day_closes, prior.funding_events)
    inputs = GovernedPaperCycleInputs(
        cycle_id=f"gpe-cycle-{day}",
        correlation_id="corr-gpe-cycle",
        day_index=day,
        genesis_inputs=world.genesis_inputs,
        genesis=world.genesis,
        sealed_episodes=history[0],
        sealed_day_closes=history[1],
        sealed_funding_events=history[2],
        reservation_dataset=dataset,
        allocation_inputs=governance.allocation_inputs,
        allocation_decision=governance.allocation,  # type: ignore[arg-type]
        drawdown_inputs=governance.drawdown_inputs,
        drawdown_evidence=governance.drawdown,  # type: ignore[arg-type]
        governance_inputs=governance.governance_inputs,
        governance_decision=governance.governance,  # type: ignore[arg-type]
        approval=None,
    )
    return replace(inputs, approval=cycle_approval_for(inputs)) if approved else inputs


def seal_inputs_for(
    day: int,
    cycle_inputs: GovernedPaperCycleInputs,
    cycle: GovernedPaperCycleAuthority,
    prior: GovernedPaperDaySeal | None,
    pending: tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority] | None,
    *,
    world: Scenario | None = None,
    **overrides: object,
) -> GovernedPaperDaySealInputs:
    world = scenario("G") if world is None else world
    closing = head_inputs(instant(day + 1), world.head_at(instant(day + 1)))
    values: dict[str, object] = {
        "seal_id": f"gpe-seal-{day}",
        "correlation_id": pret.CORR,
        "day_index": day,
        "genesis_inputs": cycle_inputs.genesis_inputs,
        "genesis": cycle_inputs.genesis,
        "cycle_inputs": cycle_inputs,
        "cycle": cycle,
        "prior_seal": prior,
        "pending_cycle_inputs": None if pending is None else pending[0],
        "pending_cycle": None if pending is None else pending[1],
        "dataset": archive(day, world.name),
        "closing_head_authority_inputs": closing,
        "closing_head_authority": build_paper_lifecycle_head_authority(closing),
        "successor_receipts": world.successors(day),
    }
    values.update(overrides)
    return GovernedPaperDaySealInputs(**values)  # type: ignore[arg-type]


@dataclass(frozen=True)
class Day:
    cycle_inputs: GovernedPaperCycleInputs
    cycle: GovernedPaperCycleAuthority
    seal_inputs: GovernedPaperDaySealInputs
    seal: GovernedPaperDaySeal

    def lineage(self) -> GovernedPaperExecutionDay:
        return GovernedPaperExecutionDay(self.cycle_inputs, self.cycle, self.seal_inputs, self.seal)


def pending_of(days: tuple[Day, ...]) -> tuple[GovernedPaperCycleInputs, GovernedPaperCycleAuthority] | None:
    """The lineage's own deciding cycle of the previous seal's pending intent (B3), or None."""

    prior = days[-1].seal if days else None
    if prior is None or prior.pending_deciding_day_index is None:
        return None
    source = days[prior.pending_deciding_day_index]
    return source.cycle_inputs, source.cycle


def next_day(days: tuple[Day, ...], world: Scenario | None = None, **cycle_options: object) -> Day:
    """Open, run and seal the day after ``days`` in ``world``."""

    world = scenario("G") if world is None else world
    day = len(days)
    prior = days[-1].seal if days else None
    cycle_inputs = cycle_inputs_for(day, prior, world=world, **cycle_options)  # type: ignore[arg-type]
    cycle = build_governed_paper_cycle_authority(cycle_inputs)
    seal_inputs = seal_inputs_for(day, cycle_inputs, cycle, prior, pending_of(days), world=world)
    return Day(cycle_inputs, cycle, seal_inputs, build_governed_paper_day_seal(seal_inputs))


@functools.cache
def days_of(name: str, count: int) -> tuple[Day, ...]:
    """The first ``count`` days of scenario ``name``, each built on the previous one (shared prefixes)."""

    if count == 0:
        return ()
    days = days_of(name, count - 1)
    return (*days, next_day(days, scenario(name)))


def world_days(count: int = DAYS) -> tuple[Day, ...]:
    return days_of("G", count)


def evidence_inputs(
    days: tuple[Day, ...], world: Scenario | None = None, **overrides: object
) -> GovernedPaperExecutionInputs:
    world = scenario("G") if world is None else world
    values: dict[str, object] = {
        "evidence_id": "gpe-evidence-1",
        "correlation_id": "corr-gpe-evidence",
        "genesis_inputs": world.genesis_inputs,
        "genesis": world.genesis,
        "days": tuple(item.lineage() for item in days),
    }
    values.update(overrides)
    return GovernedPaperExecutionInputs(**values)  # type: ignore[arg-type]


@functools.cache
def world_evidence() -> GovernedPaperExecutionEvidence:
    return build_governed_paper_execution_evidence(evidence_inputs(world_days()))


def canonical(value: object) -> str:
    return edge_canonical_json(value)


# --- shared assertion helpers ---------------------------------------------------------------------------------------------

_PREFIX = "governed_admitted_variant_paper_execution"
_AUTH = "governed_paper_execution_authority"
SEALED = GovernedPaperDaySealStatus.SEALED
BLOCKED_SEAL = GovernedPaperDaySealStatus.BLOCKED


def code(text: str) -> str:
    return f"{_PREFIX}:{text}"


def refused(text: str):  # noqa: ANN201
    return pytest.raises(GovernedPaperExecutionError, match=f"^{re.escape(code(text))}$")


def reseal_seal(seal: GovernedPaperDaySeal, **changes: object) -> GovernedPaperDaySeal:
    changed = replace(seal, **changes)
    return replace(changed, seal_digest=governed_paper_day_seal_digest(changed))


def reseal_evidence(evidence: GovernedPaperExecutionEvidence, **changes: object) -> GovernedPaperExecutionEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, evidence_digest=governed_paper_execution_evidence_digest(changed))


def replay_of(item: Day):  # noqa: ANN201
    """The day's replay rebuilt independently through the public engine functions (economics, governed outcome)."""

    inputs = item.seal_inputs
    authority_view = governed_paper_genesis_authority(inputs.genesis, inputs.genesis_inputs)
    genesis = authority_view.genesis
    run = execution.build_historical_decision_run(
        inputs.dataset,
        authority_view.executable_binding,
        expected_dataset_digest=inputs.dataset.dataset_digest,
        expected_executable_binding_digest=genesis.executable_binding_digest,
        run_id=f"{inputs.seal_id}-run",
        correlation_id=inputs.correlation_id,
        parameter_assignment=authority_view.parameter_assignment,
        instrument=genesis.instrument,
        evaluation_start_ns=genesis.genesis_start_ns,
        evaluation_end_ns=item.seal.window_end_ns,
        parameter_approval=authority_view.parameter_approval,
    )
    economics = execution.build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=authority_view.economics_policy,
        expected_economics_policy_digest=genesis.economics_policy_digest,
        economics_approval=authority_view.economics_approval,
        result_id=f"{inputs.seal_id}-economics",
        correlation_id=inputs.correlation_id,
    )
    return economics, simulate_historical_execution_governed_paper(
        economics, expected_result_digest=economics.result_digest, schedule=item.seal.schedule
    )


def governed_reasons(item: Day) -> list[str]:
    return [fill.reason for fill in replay_of(item)[1].fills if fill.reason.startswith("governed_paper_")]


def outcome_of_decision(item: Day, sequence: int) -> tuple[str, str]:
    """The final fill outcome and reason the day's replay records for decision ``sequence``."""

    outcome = replay_of(item)[1]
    intent = next(entry for entry in outcome.intents if entry.decision_sequence == sequence)
    fill = [entry for entry in outcome.fills if entry.intent_id == intent.intent_id][-1]
    return fill.outcome.value, fill.reason


def rebuilt_seal(item: Day, **overrides: object) -> GovernedPaperDaySeal:
    return build_governed_paper_day_seal(replace(item.seal_inputs, **overrides))


def assert_flags(artifact: object) -> None:
    flags = dict(GOVERNED_PAPER_EXECUTION_NON_CLAIM_FLAGS)
    assert {name: getattr(artifact, name) for name in flags} == flags
    assert all(type(getattr(artifact, name)) is bool for name in flags)


# --- A. the integrated world: B0 -> B1 -> ORDINARY ---------------------------------------------------------------------------


def test_world_g_lineage_is_ready_across_b0_b1_and_ordinary() -> None:
    evidence = world_evidence()
    assert (evidence.status, evidence.ready, evidence.day_count, evidence.sealed_day_count) == (
        GovernedPaperExecutionStatus.READY,
        True,
        DAYS,
        DAYS,
    )
    assert (evidence.bootstrap_b0_day_count, evidence.bootstrap_b1_day_count, evidence.ordinary_day_count) == (4, 26, 2)
    assert evidence.first_ordinary_day_index == 30
    assert [item.cycle_phase for item in evidence.days] == ["BOOTSTRAP_B0"] * 4 + ["BOOTSTRAP_B1"] * 26 + [
        "ORDINARY"
    ] * 2
    assert all(item.cycle_status == "AUTHORIZED" and item.seal_status == "SEALED" for item in evidence.days)
    assert (
        evidence.terminal_episode_count,
        evidence.terminal_day_close_count,
        evidence.terminal_funding_event_count,
    ) == (
        10,
        DAYS,
        10,
    )
    assert [index for index, item in enumerate(evidence.days) if item.day_episode_count] == [
        3,
        7,
        9,
        13,
        15,
        19,
        21,
        25,
        27,
        31,
    ]
    assert all(item.governance_rejected_fill_count == 0 for item in evidence.days)
    assert evidence.reason_codes == () and evidence.terminal_invalidated_from_ns is None
    assert evidence.genesis_digest == world_genesis()[1].genesis_digest
    assert_flags(evidence)


def test_every_cycle_and_seal_is_its_typed_rebuild_and_the_lineage_reverifies() -> None:
    days = world_days()
    for item in days:
        assert verify_governed_paper_cycle_authority(item.cycle, item.cycle_inputs).intact
        verification = verify_governed_paper_day_seal(item.seal, item.seal_inputs)
        assert verification.intact and verification.recomputed_digest == item.seal.seal_digest
        assert_flags(item.seal)
    verification = verify_governed_paper_execution_evidence(world_evidence(), evidence_inputs(days))
    assert (verification.intact, verification.reason_codes) == (True, ())
    assert verification.recomputed_digest == world_evidence().evidence_digest
    assert json.loads(verification.canonical_json) == governed_paper_execution_evidence_to_dict(world_evidence())


def test_the_terminal_history_is_an_rg3_ready_paper_record_over_32_daily_returns() -> None:
    inputs, performance = performance_world(DAYS, world_days()[-1].seal)
    assert performance.status is PaperSleevePerformanceStatus.READY
    assert len(inputs.valuation.days) == DAYS and Fraction(performance.paper_sharpe_annualized) != 0
    assert len(set(performance.daily_returns)) > 1  # nonzero variance


def test_every_projected_episode_is_exactly_the_engine_fill_and_its_deciding_reservation() -> None:
    days = world_days()
    _, outcome = replay_of(days[-1])
    executed = [fill for fill in outcome.fills if fill.outcome.value in ("FILLED", "PARTIALLY_FILLED")]
    seal = days[-1].seal
    assert len(executed) == len(seal.episodes) == 10
    intents = {intent.intent_id: intent for intent in outcome.intents}
    for fill, episode, deciding in zip(executed, seal.episodes, seal.episode_deciding_cycle_digests, strict=True):
        intent = intents[fill.intent_id]
        day = (intent.decision_time_ns - G) // DAY
        cycle = days[day].cycle
        assert deciding == cycle.cycle_digest and cycle.authorized is True
        price, units = Fraction(fill.fill_price), Fraction(fill.filled_quantity)
        assert Fraction(episode.fill_result.fill_price) == price and Fraction(episode.fill_result.filled_units) == units
        assert (
            Fraction(episode.fill_result.fee_amount)
            == price * units * Fraction(pret.economics_policy_p().taker_fee_bps) / 10_000
        )
        assert episode.fill_market_snapshot.observed_at_ns == fill.execution_time_ns
        assert Fraction(episode.capacity_decision.requested_notional) == units * Fraction(cycle.reservation_price)
        assert Fraction(episode.capacity_policy.max_notional) == Fraction(cycle.reservation_notional)
        assert episode.allocator_draft.draft_digest == cycle.reservation_draft_digest
        assert episode.fill_policy.slippage_bps == "0" and episode.end_to_end_episode.ready is True
        assert episode.order_intent.side == intent.side.value
    for left, right in zip(seal.episodes, seal.episodes[1:], strict=False):
        assert right.prior_position_state == left.new_position_state


def test_funding_events_and_day_closes_are_the_engine_settlements_and_marks() -> None:
    days = world_days()
    _, outcome = replay_of(days[-1])
    seal = days[-1].seal
    assert len(outcome.funding_cashflows) == len(seal.funding_events) == 10
    for cashflow, event in zip(outcome.funding_cashflows, seal.funding_events, strict=True):
        exact = -Fraction(cashflow.position_quantity) * Fraction(cashflow.mark_price) * Fraction(cashflow.funding_rate)
        assert Fraction(event.funding_amount) == exact == Fraction(cashflow.cashflow_amount)
        assert event.settlement_at_ns == cashflow.liability_time_ns
    for item in days:
        total = sum((Fraction(event.funding_amount) for event in item.seal.funding_events), Fraction(0))
        assert total == Fraction(item.seal.close_cumulative_funding)
        close = item.seal.day_closes[-1]
        assert close.close_mark_snapshot.observed_at_ns == item.seal.window_end_ns
        assert Fraction(close.close_mark_snapshot.mark_price) == paper_mark(G_DAY + item.seal.day_index + 1)
        assert Fraction(close.close_pnl_report.signed_units) == Fraction(item.seal.close_position_quantity)


# --- X1: causal daily construction ---------------------------------------------------------------------------------------------


def test_each_replay_preserves_every_sealed_prefix() -> None:
    days = world_days()
    for previous, current in zip(days, days[1:], strict=False):
        assert current.seal.prior_seal_digest == previous.seal.seal_digest
        assert current.seal.prefix_digest_open == previous.seal.prefix_digest_close
        assert current.seal.episodes[: len(previous.seal.episodes)] == previous.seal.episodes
        assert current.seal.day_closes[:-1] == previous.seal.day_closes
        assert current.cycle.sealed_history_digest == previous.seal.sealed_history_digest
        assert current.seal.schedule.windows[:-1] == previous.seal.schedule.windows


def relineage(days: tuple[Day, ...], datasets: dict[int, HistoricalPitDataset]) -> tuple[Day, ...]:
    """Re-seal ``days`` in order, each on the previous re-sealed day and on its replacement archive if given."""

    rebuilt: list[Day] = []
    for item in days:
        inputs = replace(
            item.seal_inputs,
            dataset=datasets.get(item.seal.day_index, item.seal_inputs.dataset),
            prior_seal=rebuilt[-1].seal if rebuilt else None,
        )
        rebuilt.append(replace(item, seal_inputs=inputs, seal=build_governed_paper_day_seal(inputs)))
    return tuple(rebuilt)


def test_a_rewritten_or_backfilled_archive_breaks_the_lineage() -> None:
    days = world_days(8)
    old = mark_record(G_DAY - 12)  # visible long before G and irrelevant to every replay

    def without(item: Day) -> HistoricalPitDataset:
        records = tuple(record for record in item.seal_inputs.dataset.records if record != old)
        return archive_of(f"paper-archive-without-{item.seal.day_index}", records)

    rewritten = relineage(days, {7: without(days[7])})
    assert rewritten[7].seal.status is SEALED  # each seal is a local derivation over its own archive
    with refused("archive_rewritten:7"):
        build_governed_paper_execution_evidence(evidence_inputs(rewritten))
    backfilled = relineage(days, {day: without(days[day]) for day in range(7)})
    assert all(item.seal.status is SEALED for item in backfilled)
    with refused("archive_backfilled_before_the_day:7"):
        build_governed_paper_execution_evidence(evidence_inputs(backfilled))
    assert build_governed_paper_execution_evidence(evidence_inputs(relineage(days, {}))).ready is True


def test_a_rejected_archive_is_never_a_sealing_or_opening_basis() -> None:
    item = world_days(8)[7]
    rejected = archive_of(
        "paper-archive-rejected", (*item.seal_inputs.dataset.records, book_record(400, event=instant(7) - 2_000))
    )
    assert rejected.status.value == "REJECTED"
    with refused("dataset_not_ready"):
        rebuilt_seal(item, dataset=rejected)
    with pytest.raises(GovernedPaperExecutionAuthorityError, match="reservation_dataset_not_ready$"):
        reservation_plan(8, scenario("G"), rejected)


def test_an_archive_holds_only_records_known_at_the_seal_and_reproduces_the_opening_quote() -> None:
    item = world_days(8)[7]
    future = archive_of("paper-archive-future", (*item.seal_inputs.dataset.records, book_record(401, event=instant(9))))
    with refused("dataset_holds_a_record_unknown_at_the_seal"):
        rebuilt_seal(item, dataset=future)
    quote = mark_record(G_DAY + 7, paper_mark(G_DAY + 7) + 1)
    requoted = archive_of(
        "paper-archive-requoted",
        tuple(
            quote if (record.series_id, record.sequence_id) == ("mark", G_DAY + 7) else record
            for record in item.seal_inputs.dataset.records
        ),
    )
    with refused("reservation_mark_not_reproduced_by_the_archive"):
        rebuilt_seal(item, dataset=requoted)


def test_a_day_opens_only_on_its_previous_seal_and_closing_attestation() -> None:
    days = world_days(6)
    item = days[5]
    with refused("cycle_not_opened_on_the_sealed_history"):
        rebuilt_seal(item, prior_seal=reseal_seal(days[4].seal, sealed_history_digest="0" * 64))
    other = reseal_seal(days[4].seal, closing_head_authority_digest="0" * 64)
    with refused("cycle_not_opened_on_the_closing_attestation"):
        rebuilt_seal(item, prior_seal=other)
    with refused("prior_seal_not_the_previous_day"):
        rebuilt_seal(item, prior_seal=days[3].seal)
    with refused("prior_seal_before_the_first_day"):
        rebuilt_seal(world_days(1)[0], prior_seal=days[3].seal)


def test_a_blocked_or_forged_predecessor_is_never_a_seal_to_build_on() -> None:
    days = world_days(6)
    item = days[5]
    blocked = reseal_seal(days[4].seal, status=BLOCKED_SEAL, sealed=False)
    with refused("prior_seal_not_sealed"):
        rebuilt_seal(item, prior_seal=blocked)
    with refused("prior_seal_digest_mismatch"):
        rebuilt_seal(item, prior_seal=replace(days[4].seal, close_cumulative_funding="9.000000000000000000"))
    with refused("prior_seal_not_sealed"):
        rebuilt_seal(item, prior_seal=reseal_seal(days[4].seal, sealed=1))
    with refused("prior_seal_not_canonically_typed"):
        rebuilt_seal(item, prior_seal=replace(days[4].seal, close_cumulative_funding=Fraction(1)))
    forged = reseal_seal(days[4].seal, close_cumulative_funding="9.000000000000000000")
    local = rebuilt_seal(item, prior_seal=forged)  # locally consistent with a predecessor that is not the lineage's
    lineage = (*days[:5], replace(item, seal_inputs=replace(item.seal_inputs, prior_seal=forged), seal=local))
    with refused("seal_not_chained:5"):
        build_governed_paper_execution_evidence(evidence_inputs(lineage))


# --- X2: a kill between decision and fill ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("offset", "reason", "episodes"),
    [
        (10, "governed_paper_lifecycle_invalidated", 0),
        (300, "governed_paper_lifecycle_invalidated_before_fill", 0),
        (502, "governed_paper_lifecycle_invalidated_before_fill", 0),
        (503, None, 1),
    ],
)
def test_a_kill_between_decision_and_fill_never_advances_the_position(
    offset: int, reason: str | None, episodes: int
) -> None:
    days = days_of(f"kill-{offset}", 4)
    seal = days[3].seal
    assert seal.status is SEALED and seal.invalidated_from_ns == instant(3) + offset
    assert seal.successor_receipt_digests == (kill_receipt(offset).kill_quarantine_decision_digest,)
    assert (len(seal.episodes), seal.governance_rejected_fill_count) == (episodes, 0 if reason is None else 1)
    assert governed_reasons(days[3]) == ([] if reason is None else [reason])
    assert seal.close_position_quantity == d(0 if reason else -1)


def test_an_invalidation_persists_and_every_later_cycle_is_blocked() -> None:
    days = days_of("kill-300", 6)
    for item in days[4:]:
        assert item.cycle.status is GovernedPaperCycleStatus.BLOCKED
        assert item.cycle.reason_codes == (f"{_AUTH}:lifecycle_head_not_active",)
        assert item.seal.invalidated_from_ns == instant(3) + 300 and item.seal.status is SEALED
    evidence = build_governed_paper_execution_evidence(evidence_inputs(days, scenario("kill-300")))
    assert evidence.ready is True and evidence.terminal_invalidated_from_ns == instant(3) + 300


# --- X3: retrospective closure never creates authority -------------------------------------------------------------------------


def test_the_closing_attestation_validates_and_never_authorizes() -> None:
    item = world_days(4)[3]
    synthetic = rg7t.head_inputs(
        ef8t.genesis(), evaluation_end_ns=instant(4), authority_id="gpe-head-synthetic", approval=None
    )
    synthetic = replace(synthetic, approval=rg7t.approval_for(synthetic, kind=rg7t.SYNTHETIC))
    seal = rebuilt_seal(
        item,
        closing_head_authority_inputs=synthetic,
        closing_head_authority=build_paper_lifecycle_head_authority(synthetic),
    )
    assert seal.status is BLOCKED_SEAL and seal.reason_codes == (code("closing_head_not_attested"),)
    assert (seal.episodes, seal.day_closes, seal.funding_events, seal.sealed_history_digest) == ((), (), (), "")
    stale = head_inputs(instant(5))
    with refused("closing_head_authority_not_at_the_seal"):
        rebuilt_seal(
            item,
            closing_head_authority_inputs=stale,
            closing_head_authority=build_paper_lifecycle_head_authority(stale),
        )
    killed = head_inputs(instant(4), kill_receipt(300))
    with refused("closing_head_not_reached_by_the_successors"):
        rebuilt_seal(
            item,
            closing_head_authority_inputs=killed,
            closing_head_authority=build_paper_lifecycle_head_authority(killed),
        )


def test_a_successor_inside_an_already_sealed_day_is_a_contradiction() -> None:
    item = world_days(6)[5]
    late = head_inputs(instant(6), kill_receipt(300))
    with refused("successor_receipt_outside_the_sealed_day"):
        rebuilt_seal(
            item,
            closing_head_authority_inputs=late,
            closing_head_authority=build_paper_lifecycle_head_authority(late),
            successor_receipts=(kill_receipt(300),),
        )


# --- B2: per-direction authority -------------------------------------------------------------------------------------------


def test_both_sides_are_authorized_independently_when_both_are_eligible() -> None:
    cycle = world_days(4)[3].cycle
    assert (cycle.long_record_status, cycle.short_record_status) == ("ELIGIBLE", "ELIGIBLE")
    assert cycle.long_reserved_budget == cycle.short_reserved_budget
    assert (
        Fraction(cycle.long_final_allocated_budget)
        == Fraction(cycle.short_final_allocated_budget)
        == Fraction(cycle.reservation_notional)
    )
    assert (cycle.max_long_quantity, cycle.max_short_quantity, cycle.eligible_direction_count) == (d(1), d(1), 2)


def test_a_budget_that_reserves_only_buy_never_fills_a_sell() -> None:
    days = days_of("b50-short", 5)
    for item in days:
        cycle = item.cycle
        assert (cycle.long_authorized, cycle.short_authorized) == (True, False)
        assert (cycle.long_record_status, cycle.short_record_status) == ("ELIGIBLE", "BLOCKED")
        assert (
            Fraction(cycle.long_reserved_budget) == Fraction(cycle.reservation_notional)
            and Fraction(cycle.short_reserved_budget) == 0
        )
        assert (cycle.max_long_quantity, cycle.max_short_quantity) == (d(1), d(0))
    assert governed_reasons(days[3]) == ["governed_paper_direction_not_authorized"]
    assert days[4].seal.episodes == () and days[4].seal.close_position_quantity == d(0)


def test_a_blocked_side_never_exits_a_position_it_never_reserved() -> None:
    days = days_of("b50-long", 9)
    assert [len(item.seal.episodes) for item in days] == [0, 0, 0, 1, 1, 1, 1, 1, 1]
    assert days[3].seal.episodes[0].order_intent.side == "BUY"
    assert governed_reasons(days[7]) == ["governed_paper_direction_not_authorized"]
    assert all(item.seal.close_position_quantity == d(1) for item in days[3:])  # held and valued, never force-closed
    assert days[8].seal.funding_events  # the open position keeps settling funding exactly


# --- B3: a pending intent keeps its deciding-cycle lineage -------------------------------------------------------------------


def test_a_pending_intent_keeps_its_deciding_cycle_across_two_day_boundaries() -> None:
    days = days_of("delay", 6)
    deciding = days[3].cycle
    for item in days[3:5]:
        assert (item.seal.pending_decision_sequence, item.seal.pending_deciding_day_index) == (1, 3)
        assert item.seal.pending_deciding_cycle_digest == deciding.cycle_digest and item.seal.episodes == ()
    assert days[5].seal_inputs.pending_cycle is deciding
    seal = days[5].seal
    assert seal.pending_decision_sequence is None and len(seal.episodes) == 1
    episode = seal.episodes[0]
    assert seal.episode_deciding_cycle_digests == (deciding.cycle_digest,)
    assert Fraction(episode.capacity_decision.requested_notional) == Fraction(deciding.reservation_price)
    assert episode.allocator_draft.draft_digest == deciding.reservation_draft_digest
    assert instant(5) <= episode.fill_market_snapshot.observed_at_ns < instant(6)
    evidence = build_governed_paper_execution_evidence(evidence_inputs(days, scenario("delay")))
    assert evidence.ready is True and evidence.terminal_episode_count == 1


def test_a_pending_fill_without_its_exact_deciding_cycle_fails_closed() -> None:
    days = days_of("delay", 5)
    item = days[4]
    with refused("pending_deciding_cycle_not_authentic"):
        rebuilt_seal(item, pending_cycle=None, pending_cycle_inputs=None)
    with refused("pending_deciding_cycle_not_authentic"):
        rebuilt_seal(item, pending_cycle=days[2].cycle, pending_cycle_inputs=days[2].cycle_inputs)
    forged = replace(days[3].cycle, long_authorized=1)
    with refused("pending_deciding_cycle_not_authentic"):
        rebuilt_seal(item, pending_cycle=forged)
    with refused("pending_cycle_without_a_pending_intent"):
        rebuilt_seal(world_days(5)[4], pending_cycle=days[3].cycle, pending_cycle_inputs=days[3].cycle_inputs)


def test_an_intervening_day_without_authority_refuses_the_pending_fill() -> None:
    world = scenario("delay")
    days = days_of("delay", 4)
    gap = next_day(days, world, approved=False)
    assert gap.cycle.status is GovernedPaperCycleStatus.NEEDS_GOVERNANCE_APPROVAL
    assert (gap.seal.pending_decision_sequence, gap.seal.pending_deciding_day_index) == (1, 3)
    fifth = next_day((*days, gap), world)
    assert outcome_of_decision(fifth, 1) == ("REJECTED", "governed_paper_cycle_authority_discontinuous")
    # the day's own next decision is a new intent under cycle 5, never the refused pending one
    assert fifth.seal.episode_deciding_cycle_digests == (fifth.cycle.cycle_digest,)


@pytest.mark.parametrize(
    ("instant_ns", "reason"),
    [
        (instant(5) + 3, "governed_paper_lifecycle_invalidated_before_fill"),
        (instant(4) + 100, "governed_paper_no_cycle_authority_at_fill"),
    ],
)
def test_an_intervening_kill_refuses_the_pending_fill(instant_ns: int, reason: str) -> None:
    world = scenario("delay")
    kill = ef8t.disable(
        world.receipts[0], effective_at_ns=instant_ns, decision_id=f"ef8-disable-gpe-delay-{instant_ns}"
    )
    killed = replace(world, receipts=(world.receipts[0], kill))
    days: tuple[Day, ...] = days_of("delay", 4)
    for _ in range(2):
        days = (*days, next_day(days, killed))
    assert days[5].seal.invalidated_from_ns == instant_ns
    assert days[5].seal.episodes == () and days[5].seal.close_position_quantity == d(0)
    assert outcome_of_decision(days[5], 1) == ("REJECTED", reason)


# --- B4: exact funding ------------------------------------------------------------------------------------------------------


def test_an_inexact_settlement_blocks_its_day_and_ends_the_lineage() -> None:
    days = days_of("inexact", 6)
    seal = days[5].seal
    assert seal.status is BLOCKED_SEAL
    assert seal.reason_codes == (code("funding_settlement_not_exactly_representable:320"),)
    assert (seal.episodes, seal.funding_events, seal.sealed_history_digest) == ((), (), "")
    economics, _ = replay_of(days[5])
    cashflow = next(item for item in economics.funding_cashflows if item.funding_sequence_id == 320)
    exact = -Fraction(cashflow.position_quantity) * Fraction(cashflow.mark_price) * Fraction(cashflow.funding_rate)
    assert exact == Fraction("0.18000000000000000045") and Fraction(cashflow.cashflow_amount) != exact
    evidence = build_governed_paper_execution_evidence(evidence_inputs(days, scenario("inexact")))
    assert (evidence.status, evidence.sealed_day_count) == (GovernedPaperExecutionStatus.BLOCKED, 5)
    with pytest.raises(GovernedPaperExecutionAuthorityError):
        next_day(days, scenario("inexact"))


def historical_economics_of(name: str, day: int):  # noqa: ANN201
    """The plain historical economics of scenario ``name`` over [G, E_(day + 1)) (no admission schedule)."""

    world = scenario(name)
    authority_view = governed_paper_genesis_authority(world.genesis, world.genesis_inputs)
    genesis = authority_view.genesis
    dataset = archive(day, name)
    run = execution.build_historical_decision_run(
        dataset,
        authority_view.executable_binding,
        expected_dataset_digest=dataset.dataset_digest,
        expected_executable_binding_digest=genesis.executable_binding_digest,
        run_id=f"gpe-historical-{name}-{day}",
        correlation_id=pret.CORR,
        parameter_assignment=authority_view.parameter_assignment,
        instrument=genesis.instrument,
        evaluation_start_ns=G,
        evaluation_end_ns=instant(day + 1),
        parameter_approval=authority_view.parameter_approval,
    )
    return execution.build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=authority_view.economics_policy,
        expected_economics_policy_digest=genesis.economics_policy_digest,
        economics_approval=authority_view.economics_approval,
        result_id=f"gpe-historical-{name}-{day}-economics",
        correlation_id=pret.CORR,
    )


def test_cancelling_rounding_remainders_never_defer_an_inexact_settlement() -> None:
    economics = historical_economics_of("cancel", 7)
    cashflows = {item.funding_sequence_id: item for item in economics.funding_cashflows}
    exact = {
        sequence: -Fraction(item.position_quantity) * Fraction(item.mark_price) * Fraction(item.funding_rate)
        for sequence, item in cashflows.items()
    }
    assert exact[320] == Fraction("0.18000000000000000045") == -exact[321]
    assert all(Fraction(cashflows[sequence].cashflow_amount) != exact[sequence] for sequence in (320, 321))
    # the rounded events would even reconcile with the exact cumulative: only the per-settlement rule catches them
    assert sum(Fraction(cashflows[sequence].cashflow_amount) for sequence in (320, 321)) == exact[320] + exact[321] == 0
    days = days_of("cancel", 6)
    assert days[5].seal.status is BLOCKED_SEAL
    assert days[5].seal.reason_codes == (code("funding_settlement_not_exactly_representable:320"),)


def test_negative_cashflows_and_sign_reversal_reconcile_exactly() -> None:
    days = days_of("flip", 7)
    event = days[5].seal.funding_events[-1]
    assert Fraction(event.funding_amount) == -Fraction("0.08") * paper_mark(G_DAY + 5) / 40
    assert days[5].seal.close_position_quantity == d(0)  # the sign flip exits on the same day
    for item in days:
        total = sum((Fraction(entry.funding_amount) for entry in item.seal.funding_events), Fraction(0))
        assert total == Fraction(item.seal.close_cumulative_funding)


# --- typed identity at the seal and evidence boundaries -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("sealed", 1),
        ("paper_only", 1),
        ("real_orders_enabled", 0),
        ("real_money_enabled", 0),
        ("execution_authorized", 0),
        ("status", "SEALED"),
        ("day_index", True),
    ],
)
def test_a_typed_substitution_never_verifies_even_resealed(name: str, value: object) -> None:
    item = world_days(4)[3]
    retained = replace(item.seal, **{name: value})
    assert verify_governed_paper_day_seal(retained, item.seal_inputs).intact is False
    resealed = reseal_seal(item.seal, **{name: value})
    verification = verify_governed_paper_day_seal(resealed, item.seal_inputs)
    assert verification.intact is False
    assert code(f"day_seal_field_mismatch:{name}") in verification.reason_codes


def test_a_nested_substitution_inside_the_sealed_history_never_verifies() -> None:
    item = world_days(4)[3]
    episode = item.seal.episodes[0]
    state = replace(episode.new_position_state, paper_only=1)
    forged = reseal_seal(item.seal, episodes=(replace(episode, new_position_state=state),))
    verification = verify_governed_paper_day_seal(forged, item.seal_inputs)
    assert verification.intact is False and code("day_seal_field_mismatch:episodes") in verification.reason_codes


@pytest.mark.parametrize(
    ("name", "value"), [("ready", 1), ("paper_only", 1), ("real_orders_enabled", 0), ("day_count", True)]
)
def test_a_forged_lineage_evidence_never_verifies(name: str, value: object) -> None:
    inputs = evidence_inputs(world_days())
    assert (
        verify_governed_paper_execution_evidence(reseal_evidence(world_evidence(), **{name: value}), inputs).intact
        is False
    )
    assert verify_governed_paper_execution_evidence(replace(world_evidence(), **{name: value}), inputs).intact is False


def test_public_verifiers_are_total() -> None:
    item = world_days(4)[3]
    for artifact, inputs in ((None, None), (object(), item.seal_inputs), (item.seal, None), (item.seal, object())):
        verification = verify_governed_paper_day_seal(artifact, inputs)
        assert verification.intact is False and verification.reason_codes
    for artifact, inputs in (
        (None, None),
        (world_evidence(), None),
        (world_evidence(), evidence_inputs(world_days(3))),
    ):
        assert verify_governed_paper_execution_evidence(artifact, inputs).intact is False


def test_a_lineage_rejects_a_foreign_cycle_a_reordered_day_or_no_day() -> None:
    days = world_days(6)
    swapped = (*days[:4], replace(days[4], cycle=days[5].cycle), days[5])
    with refused("cycle_not_authentic:4"):
        build_governed_paper_execution_evidence(evidence_inputs(swapped))
    with refused("day_not_bound_to_its_cycle:4"):
        build_governed_paper_execution_evidence(evidence_inputs((*days[:4], days[5], days[4])))
    with refused("evidence_days_missing"):
        build_governed_paper_execution_evidence(evidence_inputs(()))


@SLOW
def test_memo_free_reproof_of_the_whole_lineage() -> None:
    """World G's whole lineage re-proven with this contract's memos disabled.

    The accepted upstream verifiers keep their own memos and their own memo-free tests. Local only.
    """

    CONTRACT_MEMO_ENABLED[0] = False
    try:
        verification = verify_governed_paper_execution_evidence(world_evidence(), evidence_inputs(world_days()))
    finally:
        CONTRACT_MEMO_ENABLED[0] = True
    assert (verification.intact, verification.reason_codes) == (True, ())
