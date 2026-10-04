"""Paper sleeve daily valuation evidence tests (PAPER_SLEEVE_PERFORMANCE_PROVENANCE_CONSTRUCTION_V1).

SYNTHETIC TEST VALUES ONLY. Every price, unit, fee rate, mark, funding amount, reference notional, instant and approval
in this file is a synthetic test value that exercises structure. None is a production threshold, none is venue truth,
and none is production-approved. The ``HUMAN_GOVERNANCE`` approvals built here are synthetic test fixtures for the
PASS branch only.

The fixture world is built ONLY through the accepted public builders: one sleeve, one market, four genuine episodes
over a 30-day UTC window, an exact bucket-end close per day, and explicit funding evidence. Other sleeve test modules
import this module as the shared authentic world.
"""

from __future__ import annotations

import ast
import functools
import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import FrozenInstanceError, dataclass, fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.paper_sleeve_daily_valuation_evidence as valuation_module
from crypto_core.strategy.spec import strategy_spec_digest
from crypto_core.validation.edge_artifact_core import edge_canonical_json
from crypto_core.validation.paper_allocator_intent_draft import (
    PaperAllocatorIntentDraft,
    PaperAllocatorIntentDraftStatus,
    paper_allocator_intent_draft_digest,
)
from crypto_core.validation.paper_capacity_gate import (
    PaperCapacityGateStatus,
    build_paper_capacity_gate_policy,
    evaluate_paper_capacity_gate,
    paper_capacity_gate_decision_digest,
)
from crypto_core.validation.paper_daily_return_series_evidence import PaperDailyReturnBucket
from crypto_core.validation.paper_end_to_end_episode import build_paper_end_to_end_episode
from crypto_core.validation.paper_episode_runner import run_paper_episode
from crypto_core.validation.paper_fill_simulator import (
    build_paper_fill_market_snapshot,
    build_paper_fill_policy,
    paper_fill_simulation_result_digest,
    simulate_paper_fill,
)
from crypto_core.validation.paper_order_intent import build_paper_order_intent
from crypto_core.validation.paper_order_intent_admission import (
    PaperOrderIntentType,
    PaperOrderSide,
    build_paper_order_intent_request,
    evaluate_paper_order_intent_admission,
)
from crypto_core.validation.paper_pnl_report import build_paper_mark_snapshot, compute_paper_pnl_report
from crypto_core.validation.paper_position_state import (
    PaperPositionState,
    apply_paper_fill_to_position,
    build_flat_paper_position_state,
    paper_position_state_digest,
)
from crypto_core.validation.paper_realized_pnl import compute_paper_realized_pnl_event
from crypto_core.validation.paper_sleeve_daily_valuation_evidence import (
    PAPER_SLEEVE_DAILY_VALUATION_NON_CLAIM_FLAGS,
    PaperSleeveDailyValuationError,
    PaperSleeveDailyValuationEvidence,
    PaperSleeveDayCloseValuation,
    PaperSleeveDayValuation,
    PaperSleeveEpisodeEvidence,
    PaperSleeveValuationInputs,
    PaperSleeveValuationStatus,
    build_paper_sleeve_daily_valuation_evidence,
    paper_sleeve_daily_return_buckets,
    paper_sleeve_daily_valuation_evidence_digest,
    paper_sleeve_daily_valuation_evidence_to_dict,
    verify_paper_sleeve_daily_valuation_evidence,
)
from crypto_core.validation.paper_sleeve_equity_basis_policy import (
    PaperSleeveEquityBasisApproval,
    PaperSleeveEquityBasisApprovalKind,
    PaperSleeveEquityBasisPolicy,
    PaperSleeveFundingTreatment,
    build_paper_sleeve_equity_basis_policy,
    paper_sleeve_equity_basis_rule_set,
)
from crypto_core.validation.paper_sleeve_funding_evidence import (
    PaperSleeveFundingEvent,
    PaperSleeveFundingEvidence,
    build_paper_sleeve_funding_evidence,
)
from crypto_core.validation.strategy_signal_to_paper_intent import build_strategy_signal_to_paper_intent
from tests.crypto_core.validation import test_historical_pit_dataset as pit
from tests.crypto_core.validation import test_paper_deterministic_time_window_adapter as window_support

DAY_NS = 86_400_000_000_000
HOUR_NS = 3_600_000_000_000
WINDOW_DAYS = 30
WINDOW_START = 20_454 * DAY_NS
WINDOW_END = WINDOW_START + WINDOW_DAYS * DAY_NS
MARKET = "BTC-PERPETUAL"
SLEEVE = "sleeve-alpha"
VALUATION_CORRELATION = "corr-ep"
FEE_RATE_BPS = "10"


def d(text: str) -> str:
    """A SYNTHETIC TEST VALUE rendered as canonical scale-18 decimal text."""

    negative = text.startswith("-")
    integer, _, fraction = text.lstrip("-").partition(".")
    rendered = f"{integer}.{fraction.ljust(18, '0')}"
    return f"-{rendered}" if negative else rendered


def plain(value: Fraction) -> str:
    """Plain canonical decimal text of a terminating synthetic value (test-side rendering)."""

    numerator, denominator = value.numerator, value.denominator
    scale = 0
    while denominator != 1:
        if denominator % 2 == 0:
            denominator //= 2
            numerator *= 5
        elif denominator % 5 == 0:
            denominator //= 5
            numerator *= 2
        else:
            raise AssertionError("non-terminating synthetic value")
        scale += 1
    digits = str(abs(numerator)).rjust(scale + 1, "0")
    text = f"{digits[:-scale]}.{digits[-scale:]}".rstrip("0").rstrip(".") if scale else digits
    return f"-{text}" if numerator < 0 and text != "0" else text


@dataclass(frozen=True)
class EpisodePlan:
    """One synthetic episode: a MARKET order filled at the reference price (zero slippage) at ``at_ns``."""

    key: str
    side: PaperOrderSide
    units: str
    price: str
    at_ns: int


EPISODE_PLANS: tuple[EpisodePlan, ...] = (
    EpisodePlan("e1", PaperOrderSide.BUY, "4", "100", WINDOW_START + 1 * HOUR_NS),
    EpisodePlan("e2", PaperOrderSide.SELL, "2", "110", WINDOW_START + 3 * DAY_NS + 2 * HOUR_NS),
    EpisodePlan("e3", PaperOrderSide.BUY, "2", "95", WINDOW_START + 10 * DAY_NS + 3 * HOUR_NS),
    EpisodePlan("e4", PaperOrderSide.SELL, "4", "104", WINDOW_START + 20 * DAY_NS + 4 * HOUR_NS),
)


def close_mark_price(day_index: int) -> str:
    """Synthetic day-close mark: deterministic and varying, so daily returns have variance."""

    return str(95 + (day_index * 7) % 11)


def make_draft(sleeve_id: str = SLEEVE, policy_id: str = "policy-alpha") -> PaperAllocatorIntentDraft:
    fields_payload: dict[str, object] = {
        "schema_version": "paper-allocator-intent-draft.v1",
        "status": PaperAllocatorIntentDraftStatus.DRAFT_READY,
        "sleeve_id": sleeve_id,
        "policy_id": policy_id,
        "readiness_digest": "a" * 64,
        "promotion_readiness_journal_entry_digest": "a" * 64,
        "promotion_readiness_payload_digest": "a" * 64,
        "promotion_candidate_journal_entry_digest": "a" * 64,
        "decision_journal_entry_digest": "a" * 64,
        "decision_journal_payload_digest": "a" * 64,
        "eligible_count": 2,
        "blocked_count": 0,
        "insufficient_count": 0,
        "blockers": (),
        "correlation_id": f"corr-draft-{sleeve_id}",
        "metadata": (),
    }
    draft = PaperAllocatorIntentDraft(**fields_payload, draft_digest="")  # type: ignore[arg-type]
    return replace(draft, draft_digest=paper_allocator_intent_draft_digest(draft))


def make_capacity_policy(sleeve_id: str = SLEEVE, policy_id: str = "policy-alpha"):  # noqa: ANN201
    return build_paper_capacity_gate_policy(
        policy_id=policy_id, sleeve_id=sleeve_id, max_notional="100000000", max_units="100000", max_open_intents=5
    )


def genesis_state(position_state_id: str = "pos-genesis") -> PaperPositionState:
    return build_flat_paper_position_state(
        position_state_id=position_state_id, market_symbol=MARKET, correlation_id="corr-pos-genesis"
    )


def build_episode(
    plan: EpisodePlan,
    prior: PaperPositionState,
    *,
    draft: PaperAllocatorIntentDraft | None = None,
    capacity_policy: object | None = None,
) -> PaperSleeveEpisodeEvidence:
    """One genuine sleeve episode built only through the accepted public builders."""

    draft = draft if draft is not None else make_draft()
    capacity_policy = capacity_policy if capacity_policy is not None else make_capacity_policy()
    notional = plain(Fraction(plan.units) * Fraction(plan.price))
    decision = evaluate_paper_capacity_gate(
        draft,
        capacity_policy,  # type: ignore[arg-type]
        requested_notional=notional,
        requested_units=plan.units,
        correlation_id=f"corr-capacity-{plan.key}",
    )
    request = build_paper_order_intent_request(
        request_id=f"req-{plan.key}",
        capacity_decision_digest=decision.decision_digest,
        market_symbol=MARKET,
        side=plan.side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_notional=notional,
        requested_units=plan.units,
        limit_price=None,
        correlation_id=f"corr-req-{plan.key}",
    )
    spec = window_support._spec()  # noqa: SLF001 - the accepted StrategySpec fixture of the time-window chain
    bridge = build_strategy_signal_to_paper_intent(
        spec,
        expected_spec_digest=strategy_spec_digest(spec),
        signal_id=f"req-{plan.key}",
        run_id=f"run-{plan.key}",
        correlation_id=f"corr-req-{plan.key}",
        market_symbol=MARKET,
        side=plan.side,
        intent_type=PaperOrderIntentType.MARKET,
        requested_units=plan.units,
        requested_notional=notional,
        capacity_decision_digest=decision.decision_digest,
        limit_price=None,
    )
    admission = evaluate_paper_order_intent_admission(decision, request, correlation_id=f"corr-admit-{plan.key}")
    intent = build_paper_order_intent(
        admission, intent_id=f"intent-{plan.key}", correlation_id=f"corr-intent-{plan.key}"
    )
    snapshot = build_paper_fill_market_snapshot(
        snapshot_id=f"snap-{plan.key}", market_symbol=MARKET, reference_price=plan.price, observed_at_ns=plan.at_ns
    )
    fill_policy = build_paper_fill_policy(
        policy_id="fill-policy-sleeve", slippage_bps="0", fee_rate_bps=FEE_RATE_BPS, allow_partial_fill=False
    )
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"mark-{plan.key}",
        market_symbol=MARKET,
        mark_price=plan.price,
        observed_at_ns=plan.at_ns,
        correlation_id=f"corr-mark-{plan.key}",
    )
    run_correlation = f"corr-run-{plan.key}"
    ids = {
        "fill_simulation_id": f"fill-{plan.key}",
        "position_transition_id": f"trans-{plan.key}",
        "new_position_state_id": f"pos-{plan.key}",
        "pnl_report_id": f"pnl-{plan.key}",
    }
    run = run_paper_episode(
        intent,
        prior,
        snapshot,
        fill_policy,
        mark,
        **ids,
        episode_run_id=f"run-result-{plan.key}",
        correlation_id=run_correlation,
    )
    fill = simulate_paper_fill(
        intent, snapshot, fill_policy, fill_simulation_id=ids["fill_simulation_id"], correlation_id=run_correlation
    )
    transition, new_state = apply_paper_fill_to_position(
        prior,
        fill,
        transition_id=ids["position_transition_id"],
        new_position_state_id=ids["new_position_state_id"],
        correlation_id=run_correlation,
    )
    assert new_state is not None
    report = compute_paper_pnl_report(
        new_state, mark, pnl_report_id=ids["pnl_report_id"], correlation_id=run_correlation
    )
    event = compute_paper_realized_pnl_event(
        prior, fill, transition, new_state, realized_pnl_event_id=f"rpnl-{plan.key}", correlation_id=run_correlation
    )
    episode = build_paper_end_to_end_episode(
        bridge,
        intent,
        run,
        event,
        expected_bridge_digest=bridge.bridge_digest,
        expected_order_intent_digest=intent.intent_digest,
        expected_episode_run_digest=run.episode_run_digest,
        expected_realized_pnl_event_digest=event.realized_pnl_event_digest,
        episode_id=f"episode-{plan.key}",
        run_id=f"run-{plan.key}",
        correlation_id=run_correlation,
    )
    return PaperSleeveEpisodeEvidence(
        capacity_policy=capacity_policy,  # type: ignore[arg-type]
        allocator_draft=draft,
        capacity_decision=decision,
        order_intent_request=request,
        admission_decision=admission,
        order_intent=intent,
        signal_bridge=bridge,
        prior_position_state=prior,
        fill_market_snapshot=snapshot,
        fill_policy=fill_policy,
        episode_mark_snapshot=mark,
        fill_result=fill,
        position_transition=transition,
        new_position_state=new_state,
        episode_pnl_report=report,
        episode_run=run,
        realized_pnl_event=event,
        end_to_end_episode=episode,
    )


def build_chain(
    plans: tuple[EpisodePlan, ...],
    *,
    draft: PaperAllocatorIntentDraft | None = None,
    capacity_policy: object | None = None,
) -> tuple[PaperSleeveEpisodeEvidence, ...]:
    """Genuine episodes chained from a FLAT genesis, each prior state being the previous new state."""

    episodes: list[PaperSleeveEpisodeEvidence] = []
    prior = genesis_state()
    for plan in plans:
        episode = build_episode(plan, prior, draft=draft, capacity_policy=capacity_policy)
        episodes.append(episode)
        prior = episode.new_position_state
    return tuple(episodes)


@functools.lru_cache(maxsize=None)
def world_episodes() -> tuple[PaperSleeveEpisodeEvidence, ...]:
    """The four genuine sleeve episodes, chained from a FLAT genesis."""

    return build_chain(EPISODE_PLANS)


def position_before(instant: int, episodes: tuple[PaperSleeveEpisodeEvidence, ...]) -> PaperPositionState:
    state = episodes[0].prior_position_state
    for episode in episodes:
        if episode.fill_market_snapshot.observed_at_ns < instant:  # type: ignore[operator]
            state = episode.new_position_state
    return state


def build_day_close(
    day_index: int, episodes: tuple[PaperSleeveEpisodeEvidence, ...], *, mark_price: str | None = None
) -> PaperSleeveDayCloseValuation:
    instant = WINDOW_START + (day_index + 1) * DAY_NS
    mark = build_paper_mark_snapshot(
        mark_snapshot_id=f"close-mark-{day_index}",
        market_symbol=MARKET,
        mark_price=mark_price if mark_price is not None else close_mark_price(day_index),
        observed_at_ns=instant,
        correlation_id="corr-close",
    )
    report = compute_paper_pnl_report(
        position_before(instant, episodes), mark, pnl_report_id=f"close-pnl-{day_index}", correlation_id="corr-close"
    )
    return PaperSleeveDayCloseValuation(close_mark_snapshot=mark, close_pnl_report=report)


@functools.lru_cache(maxsize=None)
def world_day_closes() -> tuple[PaperSleeveDayCloseValuation, ...]:
    episodes = world_episodes()
    return tuple(build_day_close(day, episodes) for day in range(WINDOW_DAYS))


FUNDING_SETTLEMENT_OFFSET_NS = 8 * HOUR_NS


def funding_events(episodes: tuple[PaperSleeveEpisodeEvidence, ...]) -> tuple[PaperSleeveFundingEvent, ...]:
    """Synthetic funding: one settlement at 08:00 UTC on every day the bound position is open."""

    events: list[PaperSleeveFundingEvent] = []
    for day in range(WINDOW_DAYS):
        instant = WINDOW_START + day * DAY_NS + FUNDING_SETTLEMENT_OFFSET_NS
        state = position_before(instant, episodes)
        if state.side.value == "FLAT":
            continue
        events.append(
            PaperSleeveFundingEvent(
                event_id=f"funding-{day}",
                settlement_at_ns=instant,
                position_state_digest=paper_position_state_digest(state),
                funding_amount=d("-0.01"),
            )
        )
    return tuple(events)


def funding_evidence(**overrides: object) -> PaperSleeveFundingEvidence:
    values: dict[str, object] = {
        "evidence_id": "funding-evidence-1",
        "sleeve_id": SLEEVE,
        "market_symbol": MARKET,
        "window_start_ns": WINDOW_START,
        "window_end_ns": WINDOW_END,
    }
    values.update(overrides)
    if "events" not in values:
        values["events"] = funding_events(world_episodes())
    return build_paper_sleeve_funding_evidence(**values)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def world_funding() -> PaperSleeveFundingEvidence:
    return funding_evidence()


def basis_policy(
    *,
    governed: bool = True,
    kind: PaperSleeveEquityBasisApprovalKind = PaperSleeveEquityBasisApprovalKind.HUMAN_GOVERNANCE,
    reference_notional: str = "1000",
    funding_treatment: PaperSleeveFundingTreatment = PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED,
    sleeve_id: str = SLEEVE,
    market_symbol: str = MARKET,
) -> PaperSleeveEquityBasisPolicy:
    """The equity-basis policy over SYNTHETIC values; ``governed`` adds an exact synthetic test approval."""

    args: dict[str, object] = {
        "policy_id": "sleeve-basis-policy",
        "policy_version": "synthetic-v1",
        "sleeve_id": sleeve_id,
        "market_symbol": market_symbol,
        "paper_performance_reference_notional": d(reference_notional),
        "funding_treatment": funding_treatment,
    }
    unapproved = build_paper_sleeve_equity_basis_policy(**args, approval=None)  # type: ignore[arg-type]
    if not governed:
        return unapproved
    approval = PaperSleeveEquityBasisApproval(
        approval_reference="synthetic-test-approval-record",
        approval_digest="b" * 64,
        approval_kind=kind,
        approved_policy_id=unapproved.policy_id,
        approved_policy_version=unapproved.policy_version,
        approved_policy_digest=unapproved.policy_digest,
        approved_rule_set_digest=unapproved.rule_set_digest,
    )
    return build_paper_sleeve_equity_basis_policy(**args, approval=approval)  # type: ignore[arg-type]


def valuation_inputs(**overrides: object) -> PaperSleeveValuationInputs:
    values: dict[str, object] = {
        "valuation_id": "sleeve-valuation-1",
        "correlation_id": VALUATION_CORRELATION,
        "equity_basis_policy": basis_policy(),
        "window_start_ns": WINDOW_START,
        "window_end_ns": WINDOW_END,
        "episodes": world_episodes(),
        "day_closes": world_day_closes(),
        "funding_evidence": world_funding(),
    }
    values.update(overrides)
    return PaperSleeveValuationInputs(**values)  # type: ignore[arg-type]


@functools.lru_cache(maxsize=None)
def world_valuation() -> PaperSleeveDailyValuationEvidence:
    return build_paper_sleeve_daily_valuation_evidence(valuation_inputs())


# --- shared assertion helpers ---------------------------------------------------------------------------------------

_PREFIX = "paper_sleeve_daily_valuation_evidence"
_COMPUTED = PaperSleeveValuationStatus.COMPUTED
_NOT_COMPUTABLE = PaperSleeveValuationStatus.NOT_COMPUTABLE
_NOT_APPLICABLE = PaperSleeveFundingTreatment.GOVERNED_NOT_APPLICABLE
_CANONICAL_DECIMAL = re.compile(r"^-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?$")
# The accepted paper-execution artifacts this consumer must name to re-prove them. ``pit.assert_module_is_pure``
# forbids these identifiers for modules that must never touch paper execution; every other purity rule still applies.
_PAPER_EXECUTION_ARTIFACT_TOKENS = frozenset({"paperorderintent", "fill_price", "realized_pnl"})


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _raises(code: str):
    """``pytest.raises`` for one exact prefixed construction-error code."""

    return pytest.raises(PaperSleeveDailyValuationError, match=f"^{re.escape(_code(code))}$")


def build(inputs: object) -> PaperSleeveDailyValuationEvidence:
    return build_paper_sleeve_daily_valuation_evidence(inputs)  # type: ignore[arg-type]


def _reseal(evidence: PaperSleeveDailyValuationEvidence, **changes: object) -> PaperSleeveDailyValuationEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, valuation_digest=paper_sleeve_daily_valuation_evidence_digest(changed))


def _with_first_episode(**changes: object) -> tuple[PaperSleeveEpisodeEvidence, ...]:
    episodes = world_episodes()
    return (replace(episodes[0], **changes),) + episodes[1:]


def _with_close(day_index: int, close: PaperSleeveDayCloseValuation) -> tuple[PaperSleeveDayCloseValuation, ...]:
    closes = world_day_closes()
    return closes[:day_index] + (close,) + closes[day_index + 1 :]


def oracle_bucket_digest(day: PaperSleeveDayValuation) -> str:
    """The accepted daily-return bucket digest contract, recomputed independently of the module under test."""

    payload = {
        "bucket_id": day.bucket_id,
        "bucket_start_ns": day.bucket_start_ns,
        "bucket_end_ns": day.bucket_end_ns,
        "normalized_index_start": day.normalized_index_start,
        "normalized_index_end": day.normalized_index_end,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def assert_paper_consumer_is_pure(module: object, allowed_crypto_modules: set[str]) -> None:
    """``pit.assert_module_is_pure`` for a module that re-proves the accepted paper-execution artifacts.

    Every pit rule is applied unchanged (forbidden modules, calls and builtins, no float literal, no environment or
    code introspection, an exact crypto import set, no private crypto import, no BIST token), except that the
    paper-execution artifact identifiers the module must name to re-prove those artifacts are allowed.
    """

    source = Path(module.__file__).read_text(encoding="utf-8")  # type: ignore[attr-defined]
    crypto_imports: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
                assert not alias.name.startswith("crypto_core")
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in pit.FORBIDDEN_MODULES)
            if node.module.startswith("crypto_core"):
                crypto_imports.add(node.module)
                assert not {alias.name for alias in node.names if alias.name.startswith("_")}
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in pit.FORBIDDEN_CALLS, name
            assert not (isinstance(node.func, ast.Name) and name in pit.FORBIDDEN_BUILTINS), name
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "__globals__", "__code__"}
    assert crypto_imports == allowed_crypto_modules
    lowered = source.lower()
    forbidden = [token for token in pit.FORBIDDEN_IDENTIFIERS if token not in _PAPER_EXECUTION_ARTIFACT_TOKENS]
    assert not [token for token in forbidden if token in lowered]
    assert {"bist", "borsa"} <= set(forbidden)


def assert_single_construction_site(module: object, cls_name: str, builder: str, verifier: str) -> None:
    """The artifact is constructed at exactly one site, the builder, and the verifier re-proves through it."""

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    sites: list[str] = []
    calls: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls[function.name] = set(names)
        sites.extend(function.name for name in names if name == cls_name)
    assert sites == [builder]
    assert builder in calls[verifier]


def module_literals(module: object) -> tuple[set[int], set[str]]:
    """Every integer literal, and every string literal that reads as a decimal number, in the module source."""

    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))  # type: ignore[attr-defined]
    constants = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant)]
    integers = {value for value in constants if type(value) is int}
    decimals = {value for value in constants if type(value) is str and re.fullmatch(r"-?[0-9]+(\.[0-9]+)?", value)}
    return integers, decimals


# --- the authentic world --------------------------------------------------------------------------------------------


def test_world_valuation_is_computed() -> None:
    valuation = world_valuation()
    assert valuation.status is _COMPUTED, valuation.reason_codes
    assert valuation.computed is True
    assert valuation.reason_codes == ()
    assert (valuation.day_count, valuation.day_close_count, len(valuation.days)) == (WINDOW_DAYS,) * 3
    assert (valuation.episode_count, valuation.funding_event_count) == (4, 20)
    assert (valuation.window_start_ns, valuation.window_end_ns) == (WINDOW_START, WINDOW_END)


EXPECTED_DAYS: dict[int, dict[str, str]] = {
    0: {
        "cumulative_realized": "0",
        "cumulative_fees": "0.4",
        "cumulative_funding": "-0.01",
        "close_unrealized": "-20",
        "equity_basis": "979.59",
        "daily_return": "-0.02041",
        "normalized_index_start": "1",
        "normalized_index_end": "0.97959",
    },
    1: {"close_unrealized": "8", "equity_basis": "1007.58", "daily_return": "0.028573178574709828"},
    2: {"close_unrealized": "-8", "equity_basis": "991.57"},
    3: {
        "cumulative_realized": "20",
        "cumulative_fees": "0.62",
        "cumulative_funding": "-0.04",
        "close_unrealized": "10",
        "equity_basis": "1029.34",
    },
    10: {"cumulative_fees": "0.81", "cumulative_funding": "-0.11"},
    20: {
        "cumulative_realized": "46",
        "cumulative_fees": "1.226",
        "cumulative_funding": "-0.2",
        "close_unrealized": "0",
        "equity_basis": "1044.574",
    },
    21: {"equity_basis": "1044.574", "daily_return": "0"},
    29: {"equity_basis": "1044.574", "daily_return": "0"},
}


@pytest.mark.parametrize("day_index", sorted(EXPECTED_DAYS))
def test_world_daily_economics_are_exact(day_index: int) -> None:
    day = world_valuation().days[day_index]
    assert {name: getattr(day, name) for name in EXPECTED_DAYS[day_index]} == EXPECTED_DAYS[day_index]


def test_equity_basis_is_reference_plus_realized_minus_fees_plus_unrealized_plus_funding() -> None:
    valuation = world_valuation()
    reference = Fraction(valuation.paper_performance_reference_notional)
    assert reference == 1000
    for day in valuation.days:
        assert Fraction(day.equity_basis) == (
            reference
            + Fraction(day.cumulative_realized)
            - Fraction(day.cumulative_fees)
            + Fraction(day.close_unrealized)
            + Fraction(day.cumulative_funding)
        )


def test_daily_returns_are_exact_ratios_rendered_once_half_even() -> None:
    valuation = world_valuation()
    previous = Fraction(valuation.paper_performance_reference_notional)
    for day in valuation.days:
        equity = Fraction(day.equity_basis)
        assert Fraction(day.daily_return) == round(equity / previous - 1, 18)  # Fraction rounds half to even
        previous = equity


def test_the_normalized_index_is_chain_linked_exactly() -> None:
    days = world_valuation().days
    bound = paper_sleeve_equity_basis_rule_set()["normalized_index_max_text_length"]
    assert days[0].normalized_index_start == "1"
    for previous, current in zip(days, days[1:]):
        assert current.normalized_index_start == previous.normalized_index_end
    product = Fraction(1)
    for day in days:
        growth = 1 + Fraction(day.daily_return)
        assert Fraction(day.normalized_index_end) == Fraction(day.normalized_index_start) * growth
        assert len(day.normalized_index_end) <= bound  # type: ignore[operator]
        product *= growth
    assert Fraction(days[-1].normalized_index_end) == product


def test_every_decimal_text_is_canonical() -> None:
    valuation = world_valuation()
    texts: list[str] = []
    for day in valuation.days:
        texts.extend(
            (
                day.cumulative_realized,
                day.cumulative_fees,
                day.cumulative_funding,
                day.close_unrealized,
                day.equity_basis,
                day.daily_return,
                day.normalized_index_start,
                day.normalized_index_end,
            )
        )
    for episode in valuation.episodes:
        texts.extend((episode.realized_amount, episode.fee_amount))
    assert all(_CANONICAL_DECIMAL.match(text) and text != "-0" for text in texts)
    assert all(len(day.daily_return.partition(".")[2]) <= 18 for day in valuation.days)


def test_buckets_partition_the_window_into_accepted_utc_days() -> None:
    valuation = world_valuation()
    for index, day in enumerate(valuation.days):
        assert day.day_index == index
        assert day.bucket_start_ns == WINDOW_START + index * DAY_NS
        assert day.bucket_end_ns == day.bucket_start_ns + DAY_NS
        assert day.bucket_id == f"sleeve-day-{index}-{valuation.lineage_digest}"
        assert day.bucket_digest == oracle_bucket_digest(day)
    assert len({day.bucket_digest for day in valuation.days}) == WINDOW_DAYS


def test_each_day_binds_its_exact_close_artifacts() -> None:
    valuation = world_valuation()
    episodes = world_episodes()
    for day, close in zip(valuation.days, world_day_closes()):
        assert day.close_mark_snapshot_digest == close.close_mark_snapshot.mark_snapshot_digest
        assert day.close_pnl_report_digest == close.close_pnl_report.pnl_report_digest
        expected_position = position_before(day.bucket_end_ns, episodes)
        assert day.close_position_state_digest == paper_position_state_digest(expected_position)


def test_episode_records_carry_the_reconstructed_lineage() -> None:
    valuation = world_valuation()
    episodes = world_episodes()
    assert len(valuation.episodes) == len(episodes)
    for record, episode, plan in zip(valuation.episodes, episodes, EPISODE_PLANS):
        assert record.episode_digest == episode.end_to_end_episode.episode_digest
        assert record.capacity_decision_digest == episode.capacity_decision.decision_digest
        assert record.order_intent_digest == episode.order_intent.intent_digest
        assert record.episode_run_digest == episode.episode_run.episode_run_digest
        assert record.fill_simulation_result_digest == episode.fill_result.result_digest
        assert record.realized_pnl_event_digest == episode.realized_pnl_event.realized_pnl_event_digest
        assert record.prior_position_state_digest == episode.prior_position_state.position_state_digest
        assert record.new_position_state_digest == episode.new_position_state.position_state_digest
        assert record.fill_observed_at_ns == plan.at_ns
    assert [record.day_index for record in valuation.episodes] == [0, 3, 10, 20]
    assert [record.realized_amount for record in valuation.episodes] == ["0", "20", "0", "26"]
    assert valuation.capacity_decision_digests == tuple(
        sorted({episode.capacity_decision.decision_digest for episode in episodes})
    )


def test_fees_are_the_reproven_fill_fees_and_are_never_zeroed() -> None:
    valuation = world_valuation()
    fees = [Fraction(episode.fill_result.fee_amount) for episode in world_episodes()]
    assert [record.fee_amount for record in valuation.episodes] == ["0.4", "0.22", "0.19", "0.416"]
    assert [Fraction(record.fee_amount) for record in valuation.episodes] == fees
    assert all(fee > 0 for fee in fees)
    assert Fraction(valuation.days[-1].cumulative_fees) == sum(fees)


def test_policy_and_funding_bindings_are_carried() -> None:
    valuation = world_valuation()
    policy = basis_policy()
    assert valuation.equity_basis_policy_id == policy.policy_id
    assert valuation.equity_basis_policy_version == policy.policy_version
    assert valuation.equity_basis_policy_digest == policy.policy_digest
    assert valuation.equity_basis_digest == policy.equity_basis_digest
    assert valuation.equity_basis_rule_set_digest == policy.rule_set_digest
    assert valuation.equity_basis_policy_advances is True
    assert valuation.paper_performance_reference_notional == policy.paper_performance_reference_notional
    assert valuation.funding_treatment is PaperSleeveFundingTreatment.FUNDING_EVIDENCE_REQUIRED
    assert valuation.funding_evidence_digest == world_funding().funding_evidence_digest
    assert (valuation.valuation_id, valuation.correlation_id) == ("sleeve-valuation-1", VALUATION_CORRELATION)


def test_the_build_is_deterministic_and_reads_lists_like_tuples() -> None:
    valuation = world_valuation()
    assert build(valuation_inputs()) == valuation
    assert build(valuation_inputs(episodes=list(world_episodes()), day_closes=list(world_day_closes()))) == valuation


def test_day_close_order_does_not_change_the_valuation() -> None:
    assert build(valuation_inputs(day_closes=tuple(reversed(world_day_closes())))) == world_valuation()


# --- sleeve authority -----------------------------------------------------------------------------------------------


def test_sleeve_and_market_are_copied_from_the_reconstructed_capacity_decisions() -> None:
    valuation = world_valuation()
    assert {episode.capacity_decision.sleeve_id for episode in world_episodes()} == {SLEEVE}
    assert (valuation.sleeve_id, valuation.market_symbol) == (SLEEVE, MARKET)
    assert "sleeve_id" not in {field.name for field in fields(PaperSleeveValuationInputs)}


def test_a_sleeve_beta_chain_is_valued_as_sleeve_beta() -> None:
    episodes = build_chain(
        EPISODE_PLANS,
        draft=make_draft("sleeve-beta", "policy-beta"),
        capacity_policy=make_capacity_policy("sleeve-beta", "policy-beta"),
    )
    valued = build(
        valuation_inputs(
            episodes=episodes,
            day_closes=tuple(build_day_close(day, episodes) for day in range(WINDOW_DAYS)),
            equity_basis_policy=basis_policy(sleeve_id="sleeve-beta"),
            funding_evidence=funding_evidence(sleeve_id="sleeve-beta", events=funding_events(episodes)),
        )
    )
    assert valued.status is _COMPUTED
    assert valued.sleeve_id == "sleeve-beta"
    assert [day.equity_basis for day in valued.days] == [day.equity_basis for day in world_valuation().days]
    assert valued.lineage_digest != world_valuation().lineage_digest


def test_a_self_sealed_capacity_decision_never_names_another_sleeve() -> None:
    decision = replace(world_episodes()[0].capacity_decision, sleeve_id="sleeve-beta")
    decision = replace(decision, decision_digest=paper_capacity_gate_decision_digest(decision))
    with _raises("capacity_decision_not_reconstructed"):
        build(valuation_inputs(episodes=_with_first_episode(capacity_decision=decision)))


def test_a_capacity_policy_of_another_sleeve_never_reconstructs_the_decision() -> None:
    policy = make_capacity_policy("sleeve-beta", "policy-beta")
    with _raises("capacity_decision_not_reconstructed"):
        build(valuation_inputs(episodes=_with_first_episode(capacity_policy=policy)))


def test_a_rejected_capacity_decision_is_never_sleeve_authority() -> None:
    rejected = evaluate_paper_capacity_gate(
        make_draft(),
        make_capacity_policy(),
        requested_notional="1000000000",
        requested_units="4",
        correlation_id="corr-capacity-e1",
    )
    assert rejected.status is PaperCapacityGateStatus.REJECTED
    with _raises("capacity_decision_not_admitted"):
        build(valuation_inputs(episodes=_with_first_episode(capacity_decision=rejected)))


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"sleeve_id": "sleeve-beta"}, "equity_basis_policy_sleeve_mismatch"),
        ({"market_symbol": "ETH-PERPETUAL"}, "equity_basis_policy_market_mismatch"),
    ],
)
def test_the_policy_must_name_the_reconstructed_sleeve_and_market(changes: dict[str, str], code: str) -> None:
    with _raises(code):
        build(valuation_inputs(equity_basis_policy=basis_policy(**changes)))  # type: ignore[arg-type]


def test_an_episode_of_another_sleeve_is_never_aggregated() -> None:
    first = world_episodes()[0]
    other = build_episode(
        EPISODE_PLANS[1],
        first.new_position_state,
        draft=make_draft("sleeve-beta", "policy-beta"),
        capacity_policy=make_capacity_policy("sleeve-beta", "policy-beta"),
    )
    with _raises("cross_sleeve_episode"):
        build(valuation_inputs(episodes=(first, other)))


def test_a_capacity_decision_never_authorizes_two_episodes() -> None:
    first = world_episodes()[0]
    reuse = build_episode(
        EpisodePlan("e1", PaperOrderSide.SELL, "4", "100", WINDOW_START + DAY_NS), first.new_position_state
    )
    assert reuse.capacity_decision == first.capacity_decision
    with _raises("economic_action_reused"):
        build(valuation_inputs(episodes=(first, reuse)))


# --- episode reconstruction -----------------------------------------------------------------------------------------

SUBSTITUTED_PART_CODES: tuple[tuple[str, str], ...] = (
    ("capacity_decision", "request_capacity_lineage_mismatch"),
    ("order_intent_request", "request_capacity_lineage_mismatch"),
    ("admission_decision", "admission_decision_not_reconstructed"),
    ("order_intent", "order_intent_not_reconstructed"),
    ("signal_bridge", "end_to_end_episode_not_reconstructed"),
    ("prior_position_state", "position_transition_not_reconstructed"),
    ("fill_market_snapshot", "fill_result_not_reconstructed"),
    ("episode_mark_snapshot", "episode_pnl_report_not_reconstructed"),
    ("fill_result", "fill_result_not_reconstructed"),
    ("position_transition", "position_transition_not_reconstructed"),
    ("new_position_state", "position_transition_not_reconstructed"),
    ("episode_pnl_report", "episode_pnl_report_not_reconstructed"),
    ("episode_run", "fill_result_not_reconstructed"),
    ("realized_pnl_event", "realized_pnl_event_not_reconstructed"),
    ("end_to_end_episode", "end_to_end_episode_not_reconstructed"),
)


@pytest.mark.parametrize(("part", "code"), SUBSTITUTED_PART_CODES)
def test_a_genuine_artifact_of_another_episode_is_never_accepted(part: str, code: str) -> None:
    donor = world_episodes()[1]
    with _raises(code):
        build(valuation_inputs(episodes=_with_first_episode(**{part: getattr(donor, part)})))


def test_a_self_sealed_zero_fee_fill_never_replaces_the_reproven_fee() -> None:
    fill = replace(world_episodes()[0].fill_result, fee_amount="0")
    fill = replace(fill, result_digest=paper_fill_simulation_result_digest(fill))
    with _raises("fill_result_not_reconstructed"):
        build(valuation_inputs(episodes=_with_first_episode(fill_result=fill)))


def test_a_fill_policy_with_another_fee_rate_never_reproduces_the_fill() -> None:
    policy = build_paper_fill_policy(
        policy_id="fill-policy-sleeve", slippage_bps="0", fee_rate_bps="20", allow_partial_fill=False
    )
    with _raises("fill_result_not_reconstructed"):
        build(valuation_inputs(episodes=_with_first_episode(fill_policy=policy)))


def test_the_chain_must_start_from_a_flat_genesis() -> None:
    with _raises("genesis_position_not_flat"):
        build(valuation_inputs(episodes=tuple(reversed(world_episodes()))))


@pytest.mark.parametrize("indexes", [(0, 0, 1, 2, 3), (0, 2, 3), (0, 1, 3)], ids=["duplicate", "skip-e2", "skip-e3"])
def test_a_duplicated_or_skipped_episode_breaks_the_position_chain(indexes: tuple[int, ...]) -> None:
    episodes = world_episodes()
    with _raises("position_chain_discontinuous"):
        build(valuation_inputs(episodes=tuple(episodes[index] for index in indexes)))


@pytest.mark.parametrize("at_ns", [WINDOW_START + HOUR_NS // 2, WINDOW_START + HOUR_NS], ids=["earlier", "same"])
def test_fill_instants_must_strictly_increase(at_ns: int) -> None:
    first = world_episodes()[0]
    second = build_episode(EpisodePlan("e2", PaperOrderSide.SELL, "2", "110", at_ns), first.new_position_state)
    with _raises("fill_instants_not_strictly_increasing"):
        build(valuation_inputs(episodes=(first, second)))


@pytest.mark.parametrize(
    "window",
    [(WINDOW_START + DAY_NS, WINDOW_END), (WINDOW_START, WINDOW_START + 20 * DAY_NS)],
    ids=["fill-before-start", "fill-at-or-after-end"],
)
def test_a_fill_outside_the_window_is_rejected(window: tuple[int, int]) -> None:
    with _raises("fill_instant_outside_window"):
        build(valuation_inputs(window_start_ns=window[0], window_end_ns=window[1]))


# --- funding --------------------------------------------------------------------------------------------------------


def test_missing_funding_evidence_is_not_computable_and_never_an_implicit_zero() -> None:
    valued = build(valuation_inputs(funding_evidence=None))
    assert valued.status is _NOT_COMPUTABLE
    assert valued.computed is False
    assert valued.reason_codes == (_code("funding_evidence_missing"),)
    assert valued.days == ()
    assert (valued.funding_evidence_digest, valued.funding_event_count, valued.episode_count) == ("", 0, 4)


def test_governed_not_applicable_funding_is_an_exact_governed_zero() -> None:
    valued = build(
        valuation_inputs(equity_basis_policy=basis_policy(funding_treatment=_NOT_APPLICABLE), funding_evidence=None)
    )
    assert valued.status is _COMPUTED
    assert valued.funding_treatment is _NOT_APPLICABLE
    assert {day.cumulative_funding for day in valued.days} == {"0"}
    assert valued.days[20].equity_basis == "1044.774"
    assert (valued.funding_evidence_digest, valued.funding_event_count) == ("", 0)


def test_funding_evidence_under_governed_not_applicable_is_rejected() -> None:
    with _raises("funding_evidence_supplied_under_governed_not_applicable"):
        build(valuation_inputs(equity_basis_policy=basis_policy(funding_treatment=_NOT_APPLICABLE)))


def test_an_explicit_empty_funding_statement_is_evidence_not_an_absence() -> None:
    statement = funding_evidence(events=())
    valued = build(valuation_inputs(funding_evidence=statement))
    assert valued.status is _COMPUTED
    assert (valued.funding_evidence_digest, valued.funding_event_count) == (statement.funding_evidence_digest, 0)
    assert valued.days[20].equity_basis == "1044.774"


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"sleeve_id": "sleeve-beta"}, "funding_evidence_sleeve_mismatch"),
        ({"market_symbol": "ETH-PERPETUAL"}, "funding_evidence_market_mismatch"),
        ({"window_end_ns": WINDOW_END + DAY_NS}, "funding_evidence_window_mismatch"),
        ({"window_start_ns": WINDOW_START - DAY_NS}, "funding_evidence_window_mismatch"),
    ],
)
def test_funding_evidence_must_match_the_sleeve_market_and_window(changes: dict[str, object], code: str) -> None:
    with _raises(code):
        build(valuation_inputs(funding_evidence=funding_evidence(**changes)))


def test_tampered_funding_evidence_is_rejected() -> None:
    with _raises("funding_evidence_not_intact"):
        build(valuation_inputs(funding_evidence=replace(world_funding(), funding_total=d("0"))))


def _funding_with(event_id: str, instant: int, state: PaperPositionState, amount: str) -> PaperSleeveFundingEvidence:
    extra = PaperSleeveFundingEvent(
        event_id=event_id,
        settlement_at_ns=instant,
        position_state_digest=paper_position_state_digest(state),
        funding_amount=d(amount),
    )
    return funding_evidence(events=funding_events(world_episodes()) + (extra,))


def test_a_funding_event_bound_to_a_stale_position_is_rejected() -> None:
    stale = world_episodes()[0].prior_position_state
    evidence = _funding_with("funding-stale", WINDOW_START + 5 * DAY_NS + 9 * HOUR_NS, stale, "-0.01")
    with _raises("funding_event_position_mismatch"):
        build(valuation_inputs(funding_evidence=evidence))


def test_a_funding_event_on_a_flat_position_is_rejected() -> None:
    flat = world_episodes()[-1].new_position_state
    assert flat.side.value == "FLAT"
    evidence = _funding_with("funding-flat", WINDOW_START + 25 * DAY_NS + 8 * HOUR_NS, flat, "-0.01")
    with _raises("funding_event_position_flat"):
        build(valuation_inputs(funding_evidence=evidence))


def test_funding_at_a_fill_instant_applies_to_the_position_before_that_fill() -> None:
    episodes = world_episodes()
    instant = EPISODE_PLANS[1].at_ns
    valued = build(
        valuation_inputs(
            funding_evidence=_funding_with("funding-at-fill", instant, episodes[0].new_position_state, "-0.5")
        )
    )
    assert valued.status is _COMPUTED
    assert valued.days[3].cumulative_funding == "-0.54"
    assert valued.funding_event_count == 21
    with _raises("funding_event_position_mismatch"):
        build(
            valuation_inputs(
                funding_evidence=_funding_with("funding-at-fill", instant, episodes[1].new_position_state, "-0.5")
            )
        )


# --- day closes, marks and time -------------------------------------------------------------------------------------


def test_a_missing_day_close_is_not_computable() -> None:
    closes = world_day_closes()
    valued = build(valuation_inputs(day_closes=closes[:5] + closes[6:]))
    assert valued.status is _NOT_COMPUTABLE
    assert valued.reason_codes == (_code("day_close_missing:5"),)
    assert (valued.days, valued.day_close_count) == ((), WINDOW_DAYS - 1)


def test_without_any_day_close_every_day_is_reported_missing() -> None:
    valued = build(valuation_inputs(day_closes=()))
    assert set(valued.reason_codes) == {_code(f"day_close_missing:{day}") for day in range(WINDOW_DAYS)}
    assert valued.reason_codes == tuple(sorted(valued.reason_codes))


def test_a_duplicate_day_close_is_rejected() -> None:
    closes = world_day_closes()
    with _raises("day_close_duplicate"):
        build(valuation_inputs(day_closes=closes + (closes[3],)))


@pytest.mark.parametrize(
    "instant",
    [
        WINDOW_START + DAY_NS + 1,
        WINDOW_START + DAY_NS - 1,
        WINDOW_START,
        WINDOW_START - DAY_NS,
        WINDOW_END + DAY_NS,
    ],
    ids=["late", "early", "window-start", "before-window", "after-window"],
)
def test_a_close_mark_off_a_bucket_end_is_rejected(instant: int) -> None:
    mark = build_paper_mark_snapshot(
        mark_snapshot_id="close-mark-off",
        market_symbol=MARKET,
        mark_price="100",
        observed_at_ns=instant,
        correlation_id="c",
    )
    with _raises("close_mark_not_at_a_bucket_end"):
        build(valuation_inputs(day_closes=_with_close(0, replace(world_day_closes()[0], close_mark_snapshot=mark))))


def test_a_close_mark_of_another_market_is_rejected() -> None:
    mark = build_paper_mark_snapshot(
        mark_snapshot_id="close-mark-eth",
        market_symbol="ETH-PERPETUAL",
        mark_price="100",
        observed_at_ns=WINDOW_START + DAY_NS,
        correlation_id="corr-close",
    )
    with _raises("close_mark_market_mismatch"):
        build(valuation_inputs(day_closes=_with_close(0, replace(world_day_closes()[0], close_mark_snapshot=mark))))


def test_a_close_report_over_a_stale_position_is_rejected() -> None:
    close = world_day_closes()[2]
    stale = compute_paper_pnl_report(
        genesis_state(), close.close_mark_snapshot, pnl_report_id="close-pnl-2", correlation_id="corr-close"
    )
    with _raises("close_pnl_report_not_reconstructed"):
        build(valuation_inputs(day_closes=_with_close(2, replace(close, close_pnl_report=stale))))


def test_an_unsealed_close_mark_is_rejected() -> None:
    close = world_day_closes()[4]
    forged = replace(close, close_mark_snapshot=replace(close.close_mark_snapshot, mark_price="200"))
    with _raises("close_pnl_report_reconstruction_failed"):
        build(valuation_inputs(day_closes=_with_close(4, forged)))


def test_each_day_is_valued_at_its_own_close_mark_only() -> None:
    changed = build(valuation_inputs(day_closes=_with_close(7, build_day_close(7, world_episodes(), mark_price="120"))))
    base = world_valuation()
    assert changed.status is _COMPUTED
    for index in range(WINDOW_DAYS):
        same = changed.days[index].equity_basis == base.days[index].equity_basis
        assert same is (index != 7)
    assert changed.days[7].close_unrealized == "40"
    assert changed.days[8].daily_return != base.days[8].daily_return
    assert changed.carry_forward_used is False
    assert changed.interpolation_used is False


# --- governance and represented blocking ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "policy_kwargs",
    [{"governed": False}, {"kind": PaperSleeveEquityBasisApprovalKind.TEST_ONLY_SYNTHETIC}],
    ids=["unapproved", "test-only-synthetic"],
)
def test_a_policy_that_does_not_advance_is_not_computable(policy_kwargs: dict[str, object]) -> None:
    policy = basis_policy(**policy_kwargs)  # type: ignore[arg-type]
    assert policy.advances is False
    valued = build(valuation_inputs(equity_basis_policy=policy))
    assert valued.status is _NOT_COMPUTABLE
    assert valued.reason_codes == (_code("equity_basis_policy_not_governed"),)
    assert (valued.days, valued.equity_basis_policy_advances) == ((), False)


def test_every_blocking_reason_is_reported_sorted() -> None:
    closes = world_day_closes()
    valued = build(
        valuation_inputs(
            equity_basis_policy=basis_policy(governed=False), funding_evidence=None, day_closes=closes[:5] + closes[6:]
        )
    )
    expected = {"day_close_missing:5", "equity_basis_policy_not_governed", "funding_evidence_missing"}
    assert valued.reason_codes == tuple(sorted(_code(code) for code in expected))


def test_a_tampered_policy_is_rejected() -> None:
    forged = replace(basis_policy(), paper_performance_reference_notional=d("2000"))
    with _raises("equity_basis_policy_not_intact"):
        build(valuation_inputs(equity_basis_policy=forged))


@pytest.mark.parametrize("reference_notional", ["10", "20.41"], ids=["negative", "zero"])
def test_a_non_positive_equity_basis_is_not_computable(reference_notional: str) -> None:
    valued = build(valuation_inputs(equity_basis_policy=basis_policy(reference_notional=reference_notional)))
    assert valued.status is _NOT_COMPUTABLE
    assert valued.reason_codes == (_code("paper_performance_basis_not_positive:0"),)
    assert valued.days == ()


def _single_episode_inputs(
    day_closes: tuple[PaperSleeveDayCloseValuation, ...], **overrides: object
) -> PaperSleeveValuationInputs:
    values: dict[str, object] = {
        "episodes": world_episodes()[:1],
        "day_closes": day_closes,
        "window_end_ns": WINDOW_START + len(day_closes) * DAY_NS,
        "equity_basis_policy": basis_policy(funding_treatment=_NOT_APPLICABLE),
        "funding_evidence": None,
    }
    values.update(overrides)
    return valuation_inputs(**values)


def test_a_rendered_growth_factor_must_stay_positive() -> None:
    # E_0 = 376.000000000000000001 and E_1 = 0.000000000000000001: the exact return is above -1, but it renders to -1.
    episodes = world_episodes()[:1]
    closes = (build_day_close(0, episodes), build_day_close(1, episodes, mark_price="1"))
    policy = basis_policy(reference_notional="396.400000000000000001", funding_treatment=_NOT_APPLICABLE)
    valued = build(_single_episode_inputs(closes, equity_basis_policy=policy))
    assert valued.status is _NOT_COMPUTABLE
    assert valued.reason_codes == (_code("rendered_growth_not_positive:1"),)
    assert valued.days == ()


LONG_WINDOW_DAYS = 226


@functools.lru_cache(maxsize=None)
def long_window_closes() -> tuple[PaperSleeveDayCloseValuation, ...]:
    episodes = world_episodes()[:1]
    return tuple(build_day_close(day, episodes) for day in range(LONG_WINDOW_DAYS))


def test_the_normalized_index_stays_inside_its_committed_representation_bound() -> None:
    bound = paper_sleeve_equity_basis_rule_set()["normalized_index_max_text_length"]
    longest = build(_single_episode_inputs(long_window_closes()[: LONG_WINDOW_DAYS - 1]))
    assert longest.status is _COMPUTED
    assert max(len(day.normalized_index_end) for day in longest.days) <= bound  # type: ignore[operator]
    beyond = build(_single_episode_inputs(long_window_closes()))
    assert beyond.status is _NOT_COMPUTABLE
    assert beyond.reason_codes == (_code(f"normalized_index_representation_bound_exceeded:{LONG_WINDOW_DAYS - 1}"),)
    assert beyond.days == ()


# --- malformed input ------------------------------------------------------------------------------------------------

MALFORMED_INPUTS: tuple[tuple[dict[str, object], str], ...] = (
    ({"valuation_id": ""}, "valuation_id_invalid"),
    ({"valuation_id": " padded"}, "valuation_id_invalid"),
    ({"valuation_id": "line\nbreak"}, "valuation_id_invalid"),
    ({"valuation_id": "x" * 257}, "valuation_id_invalid"),
    ({"valuation_id": 7}, "valuation_id_invalid"),
    ({"valuation_id": "bist-valuation"}, "bist_scope_leakage:valuation_id"),
    ({"correlation_id": ""}, "correlation_id_invalid"),
    ({"correlation_id": "live"}, "forbidden_scope_token:correlation_id"),
    ({"window_start_ns": True}, "window_start_ns_invalid"),
    ({"window_start_ns": -DAY_NS}, "window_start_ns_invalid"),
    ({"window_end_ns": 2**63}, "window_end_ns_invalid"),
    ({"window_start_ns": WINDOW_START + 1}, "window_not_utc_day_aligned"),
    ({"window_end_ns": WINDOW_START}, "window_not_utc_day_aligned"),
    ({"window_end_ns": WINDOW_START - DAY_NS}, "window_not_utc_day_aligned"),
    ({"equity_basis_policy": None}, "equity_basis_policy_malformed"),
    ({"episodes": None}, "episodes_malformed"),
    ({"episodes": frozenset()}, "episodes_malformed"),
    ({"episodes": ()}, "episodes_missing"),
    ({"episodes": (None,)}, "episode_malformed"),
    ({"day_closes": None}, "day_closes_malformed"),
    ({"day_closes": (None,)}, "day_close_malformed"),
    ({"funding_evidence": "funding"}, "funding_evidence_malformed"),
)


@pytest.mark.parametrize(("changes", "code"), MALFORMED_INPUTS)
def test_malformed_inputs_raise(changes: dict[str, object], code: str) -> None:
    with _raises(code):
        build(valuation_inputs(**changes))


def test_inputs_of_another_type_raise() -> None:
    with _raises("inputs_malformed"):
        build(None)


@pytest.mark.parametrize("part", [field.name for field in fields(PaperSleeveEpisodeEvidence)])
def test_a_malformed_episode_part_raises(part: str) -> None:
    with _raises(f"{part}_malformed"):
        build(valuation_inputs(episodes=_with_first_episode(**{part: None})))


@pytest.mark.parametrize("part", ["close_mark_snapshot", "close_pnl_report"])
def test_a_malformed_day_close_part_raises(part: str) -> None:
    with _raises(f"{part}_malformed"):
        build(valuation_inputs(day_closes=_with_close(0, replace(world_day_closes()[0], **{part: None}))))


# --- serialization and verification ---------------------------------------------------------------------------------


def test_to_dict_and_digest_are_canonical() -> None:
    valuation = world_valuation()
    payload = paper_sleeve_daily_valuation_evidence_to_dict(valuation)
    assert list(payload) == [field.name for field in fields(PaperSleeveDailyValuationEvidence)]
    assert payload["status"] == "COMPUTED"
    assert payload["funding_treatment"] == "FUNDING_EVIDENCE_REQUIRED"
    assert paper_sleeve_daily_valuation_evidence_digest(valuation) == valuation.valuation_digest
    assert json.loads(edge_canonical_json(payload)) == payload


@pytest.mark.parametrize(
    ("changes", "code"),
    [
        ({"status": "COMPUTED"}, "payload_enum_field_not_exact_member"),
        ({"funding_treatment": "FUNDING_EVIDENCE_REQUIRED"}, "payload_enum_field_not_exact_member"),
        ({"day_count": -1}, "payload_integer_out_of_range"),
        ({"day_count": 2**63}, "payload_integer_out_of_range"),
        ({"reason_codes": []}, "payload_value_not_canonical"),
        ({"valuation_id": 3.5}, "payload_value_not_canonical"),
        ({"episodes": (None,)}, "payload_value_not_canonical"),
    ],
)
def test_the_serializer_accepts_only_exact_values(changes: dict[str, object], code: str) -> None:
    with _raises(code):
        paper_sleeve_daily_valuation_evidence_digest(replace(world_valuation(), **changes))


def test_the_verifier_accepts_the_genuine_valuation() -> None:
    valuation = world_valuation()
    verification = verify_paper_sleeve_daily_valuation_evidence(valuation, valuation_inputs())
    assert verification.intact is True
    assert verification.reason_codes == ()
    assert verification.recomputed_digest == valuation.valuation_digest
    assert verification.canonical_json == edge_canonical_json(paper_sleeve_daily_valuation_evidence_to_dict(valuation))


@pytest.mark.parametrize(
    "changes",
    [
        {"account_equity_represented": True},
        {"risk_budget_used_as_denominator": True},
        {"episode_set_completeness_proven": True},
        {"carry_forward_used": True},
        {"sharpe_computed": True},
        {"sleeve_id": "sleeve-beta"},
        {"paper_performance_reference_notional": d("2000")},
        {"funding_event_count": 0},
        {"reason_codes": ("forged",)},
    ],
    ids=lambda changes: next(iter(changes)),
)
def test_the_verifier_detects_a_resealed_forgery(changes: dict[str, object]) -> None:
    verification = verify_paper_sleeve_daily_valuation_evidence(
        _reseal(world_valuation(), **changes), valuation_inputs()
    )
    assert verification.intact is False
    assert set(verification.reason_codes) == {
        _code(f"field_mismatch:{next(iter(changes))}"),
        _code("field_mismatch:valuation_digest"),
    }


def test_the_verifier_detects_a_resealed_day_forgery() -> None:
    valuation = world_valuation()
    days = (replace(valuation.days[0], equity_basis="1000"),) + valuation.days[1:]
    verification = verify_paper_sleeve_daily_valuation_evidence(_reseal(valuation, days=days), valuation_inputs())
    assert set(verification.reason_codes) == {_code("field_mismatch:days"), _code("field_mismatch:valuation_digest")}


def test_the_verifier_detects_an_unsealed_tamper() -> None:
    forged = replace(world_valuation(), market_symbol="ETH-PERPETUAL")
    verification = verify_paper_sleeve_daily_valuation_evidence(forged, valuation_inputs())
    assert verification.intact is False
    assert set(verification.reason_codes) == {_code("self_digest_mismatch"), _code("field_mismatch:market_symbol")}


def test_the_verifier_binds_the_exact_inputs() -> None:
    other = valuation_inputs(valuation_id="sleeve-valuation-2")
    verification = verify_paper_sleeve_daily_valuation_evidence(world_valuation(), other)
    assert set(verification.reason_codes) == {
        _code("field_mismatch:valuation_id"),
        _code("field_mismatch:valuation_digest"),
    }


@pytest.mark.parametrize("evidence", [None, 0, "valuation", object()], ids=["none", "int", "str", "object"])
def test_the_verifier_is_total_for_any_object(evidence: object) -> None:
    verification = verify_paper_sleeve_daily_valuation_evidence(evidence, valuation_inputs())
    assert (verification.intact, verification.reason_codes) == (False, (_code("evidence_type_invalid"),))


def test_the_verifier_is_total_for_non_canonical_evidence_and_malformed_inputs() -> None:
    valuation = world_valuation()
    non_canonical = replace(valuation, status="COMPUTED")
    serialization = verify_paper_sleeve_daily_valuation_evidence(non_canonical, valuation_inputs())
    assert serialization.reason_codes == (_code("evidence_serialization_failed"),)
    reconstruction = verify_paper_sleeve_daily_valuation_evidence(valuation, None)  # type: ignore[arg-type]
    assert reconstruction.reason_codes == (_code("evidence_reconstruction_failed"),)
    assert reconstruction.intact is False


def test_the_valuation_is_immutable() -> None:
    with pytest.raises(FrozenInstanceError):
        world_valuation().status = _NOT_COMPUTABLE  # type: ignore[misc]


# --- the accepted daily-return bucket adapter -----------------------------------------------------------------------


def test_the_adapter_emits_the_exact_accepted_buckets() -> None:
    valuation = world_valuation()
    buckets = paper_sleeve_daily_return_buckets(valuation)
    assert len(buckets) == WINDOW_DAYS
    for bucket, day in zip(buckets, valuation.days):
        assert type(bucket) is PaperDailyReturnBucket
        assert (
            bucket.bucket_id,
            bucket.bucket_start_ns,
            bucket.bucket_end_ns,
            bucket.normalized_index_start,
            bucket.normalized_index_end,
            bucket.bucket_digest,
        ) == (
            day.bucket_id,
            day.bucket_start_ns,
            day.bucket_end_ns,
            day.normalized_index_start,
            day.normalized_index_end,
            oracle_bucket_digest(day),
        )


def _resealed_with_shifted_index() -> PaperSleeveDailyValuationEvidence:
    valuation = world_valuation()
    days = (replace(valuation.days[0], normalized_index_end="0.9796"),) + valuation.days[1:]
    return _reseal(valuation, days=days)


@pytest.mark.parametrize(
    ("factory", "code"),
    [
        (lambda: None, "evidence_malformed"),
        (lambda: replace(world_valuation(), status="COMPUTED"), "evidence_not_canonical"),
        (lambda: replace(world_valuation(), sleeve_id="sleeve-beta"), "valuation_digest_mismatch"),
        (lambda: build(valuation_inputs(funding_evidence=None)), "valuation_not_computed"),
        (_resealed_with_shifted_index, "bucket_digest_mismatch"),
    ],
    ids=["not-evidence", "not-canonical", "unsealed", "not-computed", "bucket-digest"],
)
def test_the_adapter_emits_nothing_for_uncomputed_or_tampered_evidence(
    factory: Callable[[], object], code: str
) -> None:
    with _raises(code):
        paper_sleeve_daily_return_buckets(factory())


# --- safety ---------------------------------------------------------------------------------------------------------


def test_non_claim_flags_are_structural_and_never_inputs() -> None:
    flags = dict(PAPER_SLEEVE_DAILY_VALUATION_NON_CLAIM_FLAGS)
    assert [name for name, value in flags.items() if value] == ["paper_only", "synthetic_paper_performance_index"]
    assert {
        "account_equity_represented",
        "capital_represented",
        "margin_modeled",
        "balance_represented",
        "risk_budget_used_as_denominator",
        "historical_economics_consumed",
        "allocation_performed",
        "execution_authorized",
        "episode_set_completeness_proven",
        "fill_policy_values_governed",
        "funding_amount_origin_proven",
        "carry_forward_used",
        "interpolation_used",
        "sharpe_computed",
    } <= set(flags)
    defaults = {field.name: field.default for field in fields(PaperSleeveDailyValuationEvidence) if field.name in flags}
    assert defaults == flags
    valuation = world_valuation()
    assert {name: getattr(valuation, name) for name in flags} == flags
    assert not set(flags) & {field.name for field in fields(PaperSleeveValuationInputs)}


def test_inputs_carry_no_sleeve_identity_or_denominator_beyond_the_policy() -> None:
    assert [field.name for field in fields(PaperSleeveValuationInputs)] == [
        "valuation_id",
        "correlation_id",
        "equity_basis_policy",
        "window_start_ns",
        "window_end_ns",
        "episodes",
        "day_closes",
        "funding_evidence",
    ]


def test_the_module_is_pure_and_consumes_only_the_accepted_paper_substrate() -> None:
    assert_paper_consumer_is_pure(
        valuation_module,
        {
            "crypto_core.validation.edge_artifact_core",
            "crypto_core.validation.paper_allocator_intent_draft",
            "crypto_core.validation.paper_capacity_gate",
            "crypto_core.validation.paper_daily_return_series_evidence",
            "crypto_core.validation.paper_end_to_end_episode",
            "crypto_core.validation.paper_episode_runner",
            "crypto_core.validation.paper_fill_simulator",
            "crypto_core.validation.paper_order_intent",
            "crypto_core.validation.paper_order_intent_admission",
            "crypto_core.validation.paper_pnl_report",
            "crypto_core.validation.paper_position_state",
            "crypto_core.validation.paper_realized_pnl",
            "crypto_core.validation.paper_sleeve_equity_basis_policy",
            "crypto_core.validation.paper_sleeve_funding_evidence",
            "crypto_core.validation.strategy_signal_to_paper_intent",
        },
    )


def test_one_construction_site_serves_the_builder_and_the_verifier() -> None:
    assert_single_construction_site(
        valuation_module,
        "PaperSleeveDailyValuationEvidence",
        "build_paper_sleeve_daily_valuation_evidence",
        "verify_paper_sleeve_daily_valuation_evidence",
    )


def test_the_module_embeds_no_production_number() -> None:
    integers, decimals = module_literals(valuation_module)
    # 0 and 1 are identities, 2, 5 and 10 are decimal-radix factors, and 32 and 127 bound control characters. Every
    # numeric rule (scale, lengths, day length, wire bound) is read from the committed equity-basis rule set.
    assert integers <= {0, 1, 2, 5, 10, 32, 127}
    # "0" and "9" are digit-character bounds and the canonical zero; "1" is the accepted index start convention.
    assert decimals <= {"0", "1", "9"}


def test_the_public_api_is_exact() -> None:
    assert set(valuation_module.__all__) == {
        "PAPER_SLEEVE_DAILY_VALUATION_NON_CLAIM_FLAGS",
        "PaperSleeveDailyValuationError",
        "PaperSleeveDailyValuationEvidence",
        "PaperSleeveDayCloseValuation",
        "PaperSleeveDayValuation",
        "PaperSleeveEpisodeEvidence",
        "PaperSleeveEpisodeValuation",
        "PaperSleeveValuationInputs",
        "PaperSleeveValuationStatus",
        "build_paper_sleeve_daily_valuation_evidence",
        "paper_sleeve_daily_return_buckets",
        "paper_sleeve_daily_valuation_evidence_digest",
        "paper_sleeve_daily_valuation_evidence_to_dict",
        "verify_paper_sleeve_daily_valuation_evidence",
    }
