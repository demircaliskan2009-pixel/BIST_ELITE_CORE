"""Tests for Edge Factory EF-6 governed walk-forward / OOS evidence (EF6_EDGE_WALK_FORWARD_OOS_EVIDENCE_V1).

Fixtures are REAL authenticated chains: EF-2 → EF-3 → EF-4 → executable binding → sealed EF-5, one PIT dataset, real
decision runs, real historical execution economics (Deep-Research-cited venue facts and a human-governance economics
approval as test fixtures, per the economics test convention) and real P3 walk-forward metrics. Every governance value
below is a SYNTHETIC TEST VALUE; EF-6 holds no production threshold. World A trades densely (a two-day funding cycle
whose rate repeats ``0, H, H`` under a lookback-1 carry) so every 365-day in-sample segment carries more than the PRDV4
§1.13 Stage 1 floor of 50 CLOSED trades; a sparse constant-rate dataset reproduces a backtest with none.

CI budget: the required ``tests`` CI job runs the suite twice (plain and coverage) under a 20-minute timeout, so the
default suite keeps the real end-to-end world A and every test that needs only EF-5 or A; attack worlds that need extra
authenticated economics, and end-to-end repeats of the default boundary grid, are ``@pytest.mark.slow`` (run with
``--runslow`` and by the scheduled CI job).

Cost control: pure public UPSTREAM functions are memoized for this module, each at the call site that resolves it:
the EF-5/EF-4/EF-3/EF-2 and P3 metrics verifiers and the P3 strict parser and shape predicate (as EF-6 calls them), the
economics verifier, strict parser and shape predicate (as P3 calls them), the decision-run verifier (as economics calls
it) and the PIT dataset verifier (as the decision run calls it). EF-6's own code is never memoized. Keys are exact: a
record's exact type and every field value (a str-enum alias, ``True`` versus ``1`` and a tuple versus a list never
collide), or a JSON payload's canonical text. Semantically transparent: the same input always yields the same immutable
result, and a raising call is never cached. Tests that change global registries disable every memo.
"""

from __future__ import annotations

import ast
import functools
import importlib
import inspect
import json
from dataclasses import MISSING, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.edge_walk_forward_oos_evidence as ef6_module
import crypto_core.validation.historical_decision_run as run_module
import crypto_core.validation.historical_execution_economics as economics_module
import crypto_core.validation.historical_walk_forward_metrics as metrics_module
import crypto_core.validation.strategy_executable_profiles as profiles_module
from crypto_core.data.requirements import data_requirement_registry_digest, default_perp_data_requirement_registry
from crypto_core.strategy.source_packet import build_source_packet
from crypto_core.strategy.spec import strategy_spec_digest, validate_strategy_spec
from crypto_core.validation import WalkForwardWindow, validate_walk_forward
from crypto_core.validation.edge_artifact_core import (
    EDGE_REGIME_EVIDENCE_UNAVAILABLE,
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeAuthorityBinding,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.edge_idea_intake_evidence import (
    build_edge_idea_intake_evidence,
    build_edge_kill_criteria_policy,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeInputVariant,
    EdgeLeakageBiasEvidence,
    EdgeParameterSearchBound,
    build_edge_leakage_bias_evidence,
    edge_leakage_bias_evidence_digest,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeInputSeries,
    build_edge_source_packet_evidence,
)
from crypto_core.validation.edge_strategy_spec_admission import (
    build_edge_strategy_spec_admission,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS,
    EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST,
    EdgeVariantEvaluationStatus,
    EdgeVariantMetricsInput,
    EdgeWalkForwardOosEvidence,
    EdgeWalkForwardOosEvidenceError,
    EdgeWalkForwardOosGovernance,
    build_edge_walk_forward_oos_evidence,
    edge_walk_forward_oos_evidence_digest,
    edge_walk_forward_oos_evidence_from_payload,
    edge_walk_forward_oos_evidence_payload_is_well_formed,
    edge_walk_forward_oos_evidence_to_dict,
    edge_walk_forward_oos_rule_set,
    verify_edge_walk_forward_oos_evidence,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionTradeStatus,
    build_historical_execution_economics,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionApprovalKind,
    HistoricalExecutionCitationKind,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
)
from crypto_core.validation.historical_walk_forward_metrics import (
    HistoricalWalkForwardMetricsResult,
    HistoricalWalkForwardSegmentKind,
    HistoricalWalkForwardSegmentMetrics,
    HistoricalWalkForwardWindowMetrics,
    historical_walk_forward_metrics_digest,
    verify_historical_walk_forward_metrics,
)
from tests.crypto_core.validation import test_edge_leakage_bias_evidence as ef5t
from tests.crypto_core.validation import test_historical_decision_run as runt
from tests.crypto_core.validation import test_historical_execution_economics as econ
from tests.crypto_core.validation import test_historical_execution_economics_policy as polt
from tests.crypto_core.validation import test_historical_walk_forward_metrics as mt
from tests.crypto_core.validation import test_strategy_executable_binding as bind
from tests.crypto_core.validation import test_strategy_executable_profiles as prof

_PREFIX = "edge_walk_forward_oos_evidence"
_UNSET = object()
SLOW = pytest.mark.slow  # an extra authenticated economics world; see the module docstring
DAY = mt.DAY
S0 = mt.S0
FUNDING = 2 * DAY  # a short governed funding cycle: one closed trade every three cycles, 60 per in-sample segment
HORIZON_DAYS = 640  # three governed windows end at day 635
MARK_STEP = 10 * DAY
RATE = "0.003000000000000000"  # synthetic: one settlement of RATE dominates the entry and exit costs of a trade
ZERO_RATE = "0.000000000000000000"
SPARSE_DATASET = "dataset-sparse"  # a constant RATE: the carry opens once and never closes a trade
LOSING_RATE = "0.001000000000000000"  # synthetic: one settlement no longer covers a trade's costs
LOSING_DATASET = "dataset-losing"  # the dense pattern at LOSING_RATE: negative in-sample and out-of-sample Sharpe
INS = econ.INS
d = polt.d
STARTS = (0, 90, 180)  # three governed windows: IS [s, s+365), OOS [s+365, s+455)

PA = prof.params(n="1")  # variant-a: a lookback-1 carry
PB = prof.params(n="1", unit="2.000000000000000000")  # variant-b
PN = prof.params(n="1", entry="0.010000000000000000")  # variant-n: never enters, so P3 cannot compute a profit factor
S = HistoricalWalkForwardSegmentKind

# --- memoized pure upstream functions (see module docstring) -----------------------------------------------------------

_MEMO_ENABLED = [True]


def _exact_key(value: object) -> object:
    """An exact hashable identity: the exact type is part of every key and records recurse over every field."""

    kind = type(value)
    if kind in (str, int, bool, type(None)) or isinstance(value, Enum):
        return kind, value
    if kind in (tuple, list):
        return kind, tuple(_exact_key(item) for item in value)  # type: ignore[union-attr]
    if is_dataclass(value) and not isinstance(value, type):
        return kind, tuple((field.name, _exact_key(getattr(value, field.name))) for field in fields(value))
    raise TypeError(f"no exact memo key for {kind.__name__}")


class _Memoized:
    """Exact memo of one pure upstream function; an input without an exact key is evaluated directly."""

    def __init__(self, real, key) -> None:
        self.real, self.key = real, key
        self.cache: dict[object, object] = {}

    def __call__(self, value: object) -> object:
        if not _MEMO_ENABLED[0]:
            return self.real(value)
        try:
            key = self.key(value)
        except Exception:  # noqa: BLE001 - no exact key: evaluate directly
            return self.real(value)
        if key not in self.cache:
            self.cache[key] = self.real(value)  # a raising call is never cached
        return self.cache[key]


# (calling module, name it resolves at call time, key). Payload functions only ever receive ``json.loads`` output here.
_MEMO_TARGETS = (
    (ef6_module, "verify_edge_leakage_bias_evidence", _exact_key),
    (ef6_module, "verify_edge_strategy_spec_admission", _exact_key),
    (ef6_module, "verify_edge_source_packet_evidence", _exact_key),
    (ef6_module, "verify_edge_idea_intake_evidence", _exact_key),
    (ef6_module, "verify_historical_walk_forward_metrics", _exact_key),
    (ef6_module, "historical_walk_forward_metrics_from_payload", edge_canonical_json),
    (ef6_module, "historical_walk_forward_metrics_payload_is_well_formed", edge_canonical_json),
    (metrics_module, "verify_historical_execution_economics", _exact_key),
    (metrics_module, "historical_execution_economics_from_payload", edge_canonical_json),
    (metrics_module, "historical_execution_economics_payload_is_well_formed", edge_canonical_json),
    (economics_module, "verify_historical_decision_run", _exact_key),
    (run_module, "verify_historical_pit_dataset", _exact_key),
)
_MEMOS = {(module, name): _Memoized(getattr(module, name), key) for module, name, key in _MEMO_TARGETS}


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        for (module, name), memo in _MEMOS.items():
            patch.setattr(module, name, memo)
        yield


# --- authentic worlds ---------------------------------------------------------------------------------------------------


def _pit(series: str, key: str, sequence: int, event: int, values: dict[str, str]):
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


def _rate(series: str, k: int) -> str:
    if series == "sparse":
        return RATE
    return (LOSING_RATE if series == "losing" else RATE) if k % 3 else ZERO_RATE


@functools.cache
def records(series: str, start_day: int, days: int) -> tuple:
    """The PIT slice one segment ``[start, start + days)`` consumes, cut from one fixed series.

    Constant marks every 10 days; a final funding settlement (final after its cycle) and a book every cycle. Dense: the
    rate repeats ``0, H, H``. A lookback-1 carry opens a short on the first ``H``, earns the second ``H`` at its
    settlement and closes on the ``0``: one CLOSED trade every three cycles. Losing: the same pattern at a rate that
    does not cover a trade's costs. Sparse: a constant ``H``. The slice keeps
    every settlement and book from before the start to after the end and a mark within the staleness bound of the start,
    so each segment's run and economics see exactly the records they need and payloads stay small.
    """

    low, high = S0 + start_day * DAY, S0 + (start_day + days) * DAY
    count = HORIZON_DAYS * DAY // FUNDING + 2
    funding = [
        build_historical_pit_record(
            series_id="funding-final",
            data_requirement_key="funding_rate",
            instrument=INS,
            sequence_id=k,
            event_time_ns=S0 + (k - 1) * FUNDING,
            available_at_ns=S0 + k * FUNDING + 10,
            finalized_at_ns=S0 + k * FUNDING + 10,
            revision_vintage_id=None,
            values=(HistoricalPitValue("funding_rate", _rate(series, k)),),
        )
        for k in range(count)
        if low - 2 * FUNDING <= S0 + (k - 1) * FUNDING <= high + FUNDING
    ]
    marks = [
        _pit("mark", "mark_price", j, S0 + j * MARK_STEP - 1_000, {"mark_price": d(100)})
        for j in range(HORIZON_DAYS // 10 + 2)
        if low - 12 * DAY <= S0 + j * MARK_STEP <= high + MARK_STEP
    ]
    books = [
        _pit("book", "order_book", k, S0 + k * FUNDING + 500, mt._book())
        for k in range(count)
        if low - FUNDING <= S0 + k * FUNDING <= high + FUNDING
    ]
    return tuple(funding + marks + books)


def _chain(universe: tuple[str, ...] = (INS,), spec_changes: dict[str, object] | None = None):
    """Authentic EF-2 → EF-3 → EF-4 over funding/mark/book series covering ``universe``."""

    packet = build_source_packet(
        packet_id="pkt-1",
        source_type="academic_paper",
        source_reference="doi:10.0/carry",
        source_title="Perpetual funding carry",
        rights_status="own_research",
        edge_hypothesis="Funding pays passive carry.",
        content_digest="c" * 64,
        market_scope_tags=("crypto_perpetuals",),
    )
    kill_policy = build_edge_kill_criteria_policy(
        policy_id="kp-1",
        correlation_id="corr-1",
        kill_criteria=ef5t.support.CRITERIA,
        thresholds_approved=True,
        approval_reference="gov-1",
        approval_digest="d" * 64,
    )
    intake = build_edge_idea_intake_evidence(
        packet,
        expected_source_packet_digest=packet.packet_digest,
        intake_id="intake-1",
        correlation_id="corr-1",
        candidate_strategy_id="passive-funding-carry",
        edge_family="funding_basis_carry",
        economic_rationale="Funding pays carry.",
        data_requirement_keys=econ.KEYS,
        declared_regime_dependence="positive_funding_regime",
        kill_criteria_draft=ef5t.support.CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    registry = default_perp_data_requirement_registry()
    manifest = build_edge_source_packet_evidence(
        intake,
        expected_root_intake_digest=intake.intake_digest,
        data_requirement_registry=registry,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        manifest_id="manifest-1",
        correlation_id="corr-1",
        input_series=tuple(
            EdgeInputSeries(
                econ.SERIES_IDS[key],
                key,
                f"archive:{econ.SERIES_IDS[key]}",
                "own_research",
                "note-1",
                "finalized_only",
                "immutable_after_finalization",
                universe,
            )
            for key in econ.KEYS
        ),
    )
    spec = validate_strategy_spec(
        {
            **ef5t.support.SPEC,
            "market_type": "usdt_perp",
            "instrument_universe": list(universe),
            **(spec_changes or {}),
        }
    ).spec
    admission = build_edge_strategy_spec_admission(
        manifest,
        expected_predecessor_digest=manifest.source_packet_evidence_digest,
        expected_root_intake_digest=intake.intake_digest,
        strategy_spec=spec,
        expected_strategy_spec_digest=strategy_spec_digest(spec),
        admission_id="admission-1",
        correlation_id="corr-1",
        admitted_kill_criteria=ef5t.support.CRITERIA,
        kill_criteria_policy=kill_policy,
        expected_kill_criteria_policy_digest=kill_policy.policy_digest,
    )
    return intake, manifest, admission, registry


@functools.cache
def world(name: str = "main"):
    """``(intake, manifest, admission, registry, binding)`` of a named world."""

    if name == "multi":
        intake, manifest, admission, registry = _chain(universe=(INS, "ETH-USDT-PERP"))
    elif name == "spec":
        intake, manifest, admission, registry = _chain(spec_changes={"strategy_version": "1.0.1"})
    else:
        intake, manifest, admission, registry = _chain()
    return intake, manifest, admission, registry, bind.executable_binding(admission, binding_id="binding-1")


@functools.cache
def dataset(world_name: str, dataset_id: str, start_day: int, days: int):
    """The PIT dataset of one segment; its id names the series and the segment."""

    _, manifest, _, registry, _ = world(world_name)
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id=f"{dataset_id}-{start_day}-{days}",
        correlation_id="corr-1",
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=records({SPARSE_DATASET: "sparse", LOSING_DATASET: "losing"}.get(dataset_id, "dense"), start_day, days),
    )


@functools.cache
def economics_policy(fee: str = d(5), synthetic: bool = False):
    kind = (
        HistoricalExecutionCitationKind.TEST_ONLY_SYNTHETIC
        if synthetic
        else HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED
    )
    return polt.cited_policy(kind=kind, funding_interval_ns=FUNDING, max_mark_staleness_ns=11 * DAY, taker_fee_bps=fee)


@functools.cache
def economics(
    start_day: int,
    days: int,
    params,
    *,
    world_name: str = "main",
    dataset_id: str = "dataset-1",
    fee: str = d(5),
    synthetic: bool = False,
):
    _, _, _, registry, binding = world(world_name)
    run_id = f"run-{world_name}-{dataset_id}-{start_day}-{days}-{edge_sha256_text(str(params))[:8]}"
    run = runt.decision_run(
        dataset(world_name, dataset_id, start_day, days),
        binding,
        instrument=INS,
        evaluation_start_ns=S0 + start_day * DAY,
        evaluation_end_ns=S0 + (start_day + days) * DAY,
        parameter_assignment=params,
        run_id=run_id,
    )
    policy = economics_policy(fee, synthetic)
    approval = polt.approval_for(
        policy,
        strategy_spec_digest=run.strategy_spec_digest,
        data_requirement_registry_digest=data_requirement_registry_digest(registry),
        approval_kind=HistoricalExecutionApprovalKind.TEST_ONLY_SYNTHETIC
        if synthetic
        else HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
    )
    return build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=approval,
        result_id=f"{run_id}-economics",
        correlation_id="corr-1",
    )


def _window(index: int, start: int, params, **kwargs: object):
    return mt.window(
        f"wf-{index + 1}", economics(start, 365, params, **kwargs), economics(start + 365, 90, params, **kwargs)
    )


_LOSING = {"dataset_id": LOSING_DATASET}
_FEE6 = {"fee": d(6)}
# Bundles whose segments differ: per window (start, params, in-sample kwargs, out-of-sample kwargs).
_SEGMENTED: dict[str, tuple] = {
    "B1ds": ((0, PB, {"dataset_id": "dataset-2"}, {}),),  # the in-sample segment on another dataset, same records
    "Aneg1": ((0, PA, _LOSING, _LOSING),),  # negative IS and OOS Sharpe
    "Aneg3": ((0, PA, _LOSING, _LOSING), (90, PA, {}, {}), (180, PA, {}, {})),  # one losing window of three
    "A1mixoos": ((0, PA, {}, _FEE6),),  # the out-of-sample source under another economics policy
    "Bmix3": ((0, PB, {}, {}), (90, PB, _FEE6, {}), (180, PB, {}, {})),  # a later in-sample source under another
}


# Named variant bundles. Only the happy/partial-survival bundles need the three governed windows; every isolation case
# compares two bundles of the SAME reduced geometry, so the one property under test is the only difference.
@functools.cache
def metrics(name: str) -> HistoricalWalkForwardMetricsResult:
    table: dict[str, tuple] = {
        "A": ((PA,) * 3, STARTS, {}),
        "Adup": ((PA,) * 3, STARTS, {}),  # the same registered assignment evaluated a second time
        "N": ((PN,) * 3, STARTS, {}),
        "A1": ((PA,), (0,), {}),
        "B1": ((PB,), (0,), {}),
        "A1dup": ((PA,), (0,), {}),
        "B1fee": ((PB,), (0,), {"fee": d(6)}),
        "A2w": ((PA,) * 2, (0, 90), {}),
        "B2": ((PB,) * 2, (0, 90), {}),
        "B2rev": ((PB,) * 2, (90, 0), {}),
        "AB2": ((PA, PB), (0, 90), {}),
        "Aspec1": ((PA,), (0,), {"world_name": "spec"}),
        "Asyn1": ((PA,), (0,), {"synthetic": True}),
        "Amulti1": ((PA,), (0,), {"world_name": "multi"}),
        "Asparse": ((PA,) * 3, STARTS, {"dataset_id": SPARSE_DATASET}),
    }
    if name in _SEGMENTED:
        return mt.build(
            tuple(
                mt.window(
                    f"wf-{index + 1}",
                    economics(start, 365, param, **in_kw),
                    economics(start + 365, 90, param, **out_kw),
                )
                for index, (start, param, in_kw, out_kw) in enumerate(_SEGMENTED[name])
            ),
            result_id=f"wf-{name}",
        )
    params, starts, kwargs = table[name]
    windows = tuple(_window(index, start, param, **kwargs) for index, (start, param) in enumerate(zip(starts, params)))
    return mt.build(windows, result_id=f"wf-{name}")


# --- EF-5 preregistrations ----------------------------------------------------------------------------------------------

_LEDGERS = {
    "A": (
        (
            EdgeParameterSearchBound("entry_threshold", "fixed", (PA[0].value,)),
            EdgeParameterSearchBound("exit_threshold", "fixed", (PA[1].value,)),
            EdgeParameterSearchBound("final_funding_lookback_count", "fixed", (PA[2].value,)),
            EdgeParameterSearchBound("unit_size", "fixed", (PA[3].value,)),
        ),
        (EdgeInputVariant("variant-a", PA),),
    ),
    "AB": (
        (
            EdgeParameterSearchBound("entry_threshold", "fixed", (PA[0].value,)),
            EdgeParameterSearchBound("exit_threshold", "fixed", (PA[1].value,)),
            EdgeParameterSearchBound("final_funding_lookback_count", "fixed", (PA[2].value,)),
            EdgeParameterSearchBound("unit_size", "searched", (PA[3].value, PB[3].value)),
        ),
        (EdgeInputVariant("variant-a", PA), EdgeInputVariant("variant-b", PB)),
    ),
    "AN": (
        (
            EdgeParameterSearchBound("entry_threshold", "searched", (PA[0].value, PN[0].value)),
            EdgeParameterSearchBound("exit_threshold", "fixed", (PA[1].value,)),
            EdgeParameterSearchBound("final_funding_lookback_count", "fixed", (PA[2].value,)),
            EdgeParameterSearchBound("unit_size", "fixed", (PA[3].value,)),
        ),
        (EdgeInputVariant("variant-a", PA), EdgeInputVariant("variant-n", PN)),
    ),
}
_LEDGERS["B"] = (
    (
        EdgeParameterSearchBound("entry_threshold", "fixed", (PB[0].value,)),
        EdgeParameterSearchBound("exit_threshold", "fixed", (PB[1].value,)),
        EdgeParameterSearchBound("final_funding_lookback_count", "fixed", (PB[2].value,)),
        EdgeParameterSearchBound("unit_size", "fixed", (PB[3].value,)),
    ),
    (EdgeInputVariant("variant-b", PB),),
)
_DEFAULT_BUNDLES = {"A": ("A",), "AB": ("A1", "B1"), "AN": ("A", "N")}


@functools.cache
def ef5(ledger: str = "A", world_name: str = "main", approve: bool = True) -> EdgeLeakageBiasEvidence:
    intake, _, admission, _, binding = world(world_name)
    bounds, variants = _LEDGERS[ledger]
    arguments = {
        "expected_predecessor_digest": admission.admission_digest,
        "expected_root_intake_digest": intake.intake_digest,
        "executable_binding": binding,
        "expected_executable_binding_digest": binding.binding_digest,
        "preregistration_id": f"prereg-{ledger}",
        "correlation_id": "corr-1",
        "feature_ids": ("final_funding_mean",),
        "parameter_bounds": bounds,
        "variants": variants,
        "survivorship_claim_scope": "pinned_instrument_universe",
    }
    draft = build_edge_leakage_bias_evidence(admission, **arguments)
    if approve:
        arguments["approval"] = ef5t.approval_for(draft)
    return build_edge_leakage_bias_evidence(admission, **arguments)


# --- EF-6 builders ------------------------------------------------------------------------------------------------------

AUTO = object()
# SYNTHETIC TEST VALUES: exactly the PRDV4 floors where PRDV4 names one, plus test-only drawdown/profit-factor values.
GOVERNED_VALUES = {
    "min_oos_window_count": 3,
    "min_in_sample_closed_trade_count": 50,
    "min_sharpe_retention_ratio": "0.500000000000000000",
    "min_hit_rate_delta_percentage_points": "-10.000000000000000000",
    "positive_expectancy_fraction_numerator": 2,
    "positive_expectancy_fraction_denominator": 3,
    "max_drawdown_ratio_exclusive": "2.000000000000000000",
    "min_profit_factor_exclusive": "1.000000000000000000",
    "profit_factor_fraction_numerator": 2,
    "profit_factor_fraction_denominator": 3,
}


def governance_for(evidence: EdgeWalkForwardOosEvidence, **overrides: object) -> EdgeWalkForwardOosGovernance:
    arguments: dict[str, object] = {
        "approval_reference": "governance-ef6-1",
        "approval_digest": "c" * 64,
        "approved_predecessor_digest": evidence.predecessor_digest,
        "approved_variant_ledger_digest": evidence.variant_ledger_digest or "0" * 64,
        "approved_multiple_testing_count": max(evidence.multiple_testing_count, 1),
        "approved_rule_set_digest": evidence.rule_set_digest,
        "approved_evaluation_frame_digest": evidence.evaluation_frame_digest,
        **GOVERNED_VALUES,
    }
    arguments.update(overrides)
    return EdgeWalkForwardOosGovernance(**arguments)  # type: ignore[arg-type]


def arguments_for(predecessor: EdgeLeakageBiasEvidence, bundles: tuple[str, ...], world_name: str = "main") -> dict:
    return {
        "expected_predecessor_digest": predecessor.leakage_bias_evidence_digest,
        "expected_root_intake_digest": world(world_name)[0].intake_digest,
        "variant_metrics": tuple(
            EdgeVariantMetricsInput(metrics(name), metrics(name).result_digest) for name in bundles
        ),
        "evidence_id": "ef6-1",
        "correlation_id": "corr-1",
    }


@functools.cache
def _draft(ledger: str, bundles: tuple[str, ...], world_name: str) -> EdgeWalkForwardOosEvidence:
    predecessor = ef5(ledger, world_name)
    return build_edge_walk_forward_oos_evidence(predecessor, **arguments_for(predecessor, bundles, world_name))


def ef6(
    ledger: str = "A",
    bundles: tuple[str, ...] | None = None,
    *,
    governance: object = AUTO,
    world_name: str = "main",
    predecessor: EdgeLeakageBiasEvidence | None = None,
    **overrides: object,
) -> EdgeWalkForwardOosEvidence:
    bundles = _DEFAULT_BUNDLES[ledger] if bundles is None else bundles
    predecessor = ef5(ledger, world_name) if predecessor is None else predecessor
    arguments = arguments_for(predecessor, bundles, world_name)
    if governance is AUTO:
        arguments["governance"] = governance_for(_draft(ledger, bundles, world_name))
    elif governance is not None:
        arguments["governance"] = governance
    arguments.update(overrides)
    return build_edge_walk_forward_oos_evidence(predecessor, **arguments)  # type: ignore[arg-type]


@functools.cache
def passed() -> EdgeWalkForwardOosEvidence:
    return ef6("A")


@functools.cache
def passed_an() -> EdgeWalkForwardOosEvidence:
    return ef6("AN")


@functools.cache
def cheap() -> EdgeWalkForwardOosEvidence:
    """A governed EF-6 over sealed EF-5 'A' with no bundle: the whole chain re-proves, nothing is consumed (FAIL)."""

    return ef6("A", (), governance=governance_for(_draft("A", (), "main")))


@functools.cache
def failed1() -> EdgeWalkForwardOosEvidence:
    """Governed EF-6 over world A's one-window bundle: authentic, cheap, and FAIL (1 OOS window < approved 3)."""

    return ef6("A", ("A1",))


@functools.cache
def _failed1_payload_text() -> str:
    return edge_canonical_json(edge_walk_forward_oos_evidence_to_dict(failed1()))


def _failed1_payload() -> dict:
    return json.loads(_failed1_payload_text())


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(evidence: EdgeWalkForwardOosEvidence, **changes: object) -> EdgeWalkForwardOosEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, walk_forward_oos_evidence_digest=edge_walk_forward_oos_evidence_digest(changed))


def _payload(evidence: EdgeWalkForwardOosEvidence) -> dict:
    return json.loads(edge_canonical_json(edge_walk_forward_oos_evidence_to_dict(evidence)))


def _resealed_payload(payload: dict) -> EdgeWalkForwardOosEvidence:
    payload["walk_forward_oos_evidence_digest"] = edge_payload_digest(payload, "walk_forward_oos_evidence_digest")
    return edge_walk_forward_oos_evidence_from_payload(payload)


def _assert_not_intact(evidence: object, *codes: str) -> EdgeEvidenceVerification:
    verification = verify_edge_walk_forward_oos_evidence(evidence)
    assert type(verification) is EdgeEvidenceVerification
    assert verification.intact is False
    assert verification.reason_codes
    assert {_code(code) for code in codes} <= set(verification.reason_codes), verification.reason_codes
    return verification


def _assert_shape(evidence: EdgeWalkForwardOosEvidence) -> None:
    """Invariants every builder state satisfies (no re-proof)."""

    assert evidence.walk_forward_oos_evidence_digest == edge_walk_forward_oos_evidence_digest(evidence)
    assert evidence.advances is (
        evidence.status is EdgeEvidenceStatus.READY and evidence.gate_verdict is EdgeGateVerdict.PASS
    )
    assert {name: getattr(evidence, name) for name, _ in EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS} == dict(
        EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS
    )
    assert evidence.surviving_variant_count == len(evidence.surviving_assignment_digests)
    assert evidence.surviving_assignment_digests == tuple(sorted(evidence.surviving_assignment_digests))
    assert evidence.regime_split_report == EDGE_REGIME_EVIDENCE_UNAVAILABLE
    assert evidence.regime_evidence_available is False
    assert evidence.rule_set_digest == EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST
    if evidence.status is EdgeEvidenceStatus.REJECTED:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes and evidence.verdict_reason_codes == ()
        assert evidence.variant_evaluations == () and evidence.surviving_assignment_digests == ()
        assert (evidence.preregistration_sealed, evidence.performance_data_consumed) == (False, False)
        assert (evidence.oos_evidence_consumed, evidence.walk_forward_evaluated) == (False, False)
    else:
        assert evidence.integrity_reason_codes == ()
        assert evidence.preregistration_sealed is True
    if evidence.gate_verdict is not EdgeGateVerdict.PASS:
        assert evidence.advances is False
    if evidence.surviving_assignment_digests:
        assert evidence.walk_forward_evaluated is True


def _assert_receipt_invariants(evidence: EdgeWalkForwardOosEvidence) -> None:
    _assert_shape(evidence)
    verification = verify_edge_walk_forward_oos_evidence(evidence)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.walk_forward_oos_evidence_digest
    assert edge_walk_forward_oos_evidence_payload_is_well_formed(json.loads(verification.canonical_json)) is True


def _units(text: str) -> Fraction:
    return Fraction(int(text.replace(".", "")), 10**18)


def _text(value: Fraction) -> str:
    """Canonical scale-18 text of a value already on the scale-18 grid."""

    return d(value)


def _floor18(value: Fraction) -> Fraction:
    return Fraction((value.numerator * 10**18) // value.denominator, 10**18)


ULP = Fraction(1, 10**18)


# --- happy path and the authority chain ---------------------------------------------------------------------------------


def test_sealed_chain_real_metrics_and_governance_pass_with_truthful_consumption() -> None:
    evidence = passed()
    _assert_receipt_invariants(evidence)
    intake, manifest, admission, registry, binding = world()
    predecessor = ef5("A")
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (evidence.gate_id, evidence.predecessor_gate_id) == ("EF-6", "EF-5")
    assert evidence.root_intake_digest == intake.intake_digest
    assert evidence.predecessor_digest == predecessor.leakage_bias_evidence_digest
    assert evidence.admission_digest == admission.admission_digest
    assert evidence.source_manifest_digest == manifest.source_packet_evidence_digest
    assert evidence.data_requirement_registry_digest == data_requirement_registry_digest(registry)
    assert evidence.executable_binding_digest == binding.binding_digest
    assert evidence.strategy_spec_digest == predecessor.strategy_spec_digest
    assert evidence.profile_semantics_digest == predecessor.profile_semantics_digest
    assert (evidence.market_type, evidence.pinned_instrument_universe, evidence.evaluated_instrument) == (
        "usdt_perp",
        (INS,),
        INS,
    )
    assert evidence.variant_ledger_digest == predecessor.variant_ledger_digest
    assert evidence.registered_parameter_assignment_digests == predecessor.registered_parameter_assignment_digests
    assert (evidence.multiple_testing_count, evidence.registered_variant_count, evidence.evaluated_variant_count) == (
        1,
        1,
        1,
    )
    assert evidence.surviving_assignment_digests == predecessor.registered_parameter_assignment_digests
    (variant,) = evidence.variant_evaluations
    assert (variant.variant_id, variant.evaluation_status, variant.metrics_computed) == (
        "variant-a",
        EdgeVariantEvaluationStatus.SURVIVED,
        True,
    )
    assert variant.metrics_result_digest == metrics("A").result_digest
    assert variant.window_digests == metrics("A").window_digests
    assert (variant.positive_expectancy_window_count, variant.required_positive_expectancy_window_count) == (3, 2)
    assert (variant.profit_factor_window_count, variant.required_profit_factor_window_count) == (3, 2)
    assert (evidence.performance_data_consumed, evidence.oos_evidence_consumed, evidence.walk_forward_evaluated) == (
        True,
        True,
        True,
    )
    assert evidence.metric_policy_digest == metrics("A").metric_policy_digest
    assert evidence.economics_policy_digest == metrics("A").economics_policy_digest
    assert evidence.governance_digest == edge_sha256_text(
        edge_canonical_json(ef6_module._to_payload(evidence.governance))
    )


@SLOW
def test_two_variant_ledger_evaluates_every_registered_variant_once_and_reports_no_winner() -> None:
    evidence = passed_an()
    _assert_receipt_invariants(evidence)
    predecessor = ef5("AN")
    assert evidence.multiple_testing_count == predecessor.multiple_testing_count == 2
    evaluated = {item.parameter_assignment_digest for item in evidence.variant_evaluations}
    assert evaluated == set(predecessor.registered_parameter_assignment_digests)
    assert (evidence.registered_variant_count, evidence.evaluated_variant_count) == (2, 2)
    assert [item.variant_id for item in evidence.variant_evaluations] == ["variant-a", "variant-n"]
    names = {field.name for field in fields(EdgeWalkForwardOosEvidence)} | {
        field.name for field in fields(type(evidence.variant_evaluations[0]))
    }
    assert not [name for name in names if any(token in name for token in ("best", "winner", "rank", "select"))]


@SLOW
def test_every_variant_uses_the_identical_governed_window_frame() -> None:
    evidence = passed_an()
    frames = [(frame.in_sample_start_ns - S0, frame.out_of_sample_start_ns - S0) for frame in evidence.window_frames]
    assert frames == [(start * DAY, (start + 365) * DAY) for start in STARTS]
    for frame in evidence.window_frames:
        assert frame.in_sample_end_ns - frame.in_sample_start_ns == 365 * DAY
        assert frame.out_of_sample_end_ns - frame.out_of_sample_start_ns == 90 * DAY
        start = (frame.in_sample_start_ns - S0) // DAY
        assert frame.in_sample_dataset_digest == dataset("main", "dataset-1", start, 365).dataset_digest
        assert frame.out_of_sample_dataset_digest == dataset("main", "dataset-1", start + 365, 90).dataset_digest


@SLOW
def test_partial_survival_reports_only_surviving_registered_digests() -> None:
    evidence = passed_an()
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    statuses = {item.variant_id: item.evaluation_status for item in evidence.variant_evaluations}
    assert statuses == {
        "variant-a": EdgeVariantEvaluationStatus.SURVIVED,
        "variant-n": EdgeVariantEvaluationStatus.FAILED,
    }
    (failed,) = [item for item in evidence.variant_evaluations if item.variant_id == "variant-n"]
    assert (failed.metrics_computed, failed.failure_codes, failed.window_outcomes) == (
        False,
        ("metrics_not_computed",),
        (),
    )
    assert evidence.surviving_variant_count == 1
    assert evidence.surviving_assignment_digests == (
        next(
            item.parameter_assignment_digest for item in evidence.variant_evaluations if item.variant_id == "variant-a"
        ),
    )


def test_unsealed_ef5_is_rejected() -> None:
    unsealed = ef5("A", approve=False)
    assert (unsealed.status, unsealed.preregistration_sealed) == (EdgeEvidenceStatus.READY, False)
    evidence = ef6("A", (), predecessor=unsealed, governance=None)
    _assert_shape(evidence)
    assert evidence.integrity_reason_codes == (_code("predecessor_not_sealed:NEEDS_GOVERNANCE_APPROVAL"),)


def test_root_anchor_transplant_is_rejected() -> None:
    evidence = ef6("A", (), governance=None, expected_root_intake_digest="e" * 64)
    _assert_shape(evidence)
    assert evidence.integrity_reason_codes == (_code("chain_splice_root_intake_mismatch"),)


def test_predecessor_anchor_transplant_is_rejected() -> None:
    evidence = ef6("A", (), governance=None, expected_predecessor_digest=ef5("AB").leakage_bias_evidence_digest)
    _assert_shape(evidence)
    assert evidence.integrity_reason_codes == (_code("predecessor_digest_mismatch"),)


def test_correlation_splice_is_rejected() -> None:
    evidence = ef6("A", ("A1",), governance=None, correlation_id="corr-2")
    _assert_shape(evidence)
    assert set(evidence.integrity_reason_codes) == {
        _code("predecessor_correlation_mismatch"),
        _code("variant_metrics_0:correlation_mismatch"),
    }


def test_forged_resealed_ef5_is_rejected() -> None:
    genuine = ef5("A")
    forged = replace(genuine, multiple_testing_count=2)
    forged = replace(forged, leakage_bias_evidence_digest=edge_leakage_bias_evidence_digest(forged))
    evidence = ef6("A", (), predecessor=forged, governance=None)
    _assert_shape(evidence)
    assert any(code.startswith(_code("predecessor_integrity_failure:")) for code in evidence.integrity_reason_codes)


@SLOW
def test_metrics_from_another_strategy_spec_and_binding_are_rejected() -> None:
    evidence = ef6("A", ("Aspec1",), governance=None)
    _assert_shape(evidence)
    codes = set(evidence.integrity_reason_codes)
    assert _code("variant_metrics_0:strategy_spec_digest_mismatch") in codes
    assert _code("variant_metrics_0:window_0:in_sample:executable_binding_digest_mismatch") in codes


def test_broken_metrics_authority_is_rejected() -> None:
    genuine = metrics("A1")
    window = genuine.windows[0]
    forged_window = replace(
        window, out_of_sample=replace(window.out_of_sample, annualized_sharpe="99.000000000000000000")
    )
    forged = replace(genuine, windows=(forged_window, *genuine.windows[1:]))
    forged = replace(forged, result_digest=historical_walk_forward_metrics_digest(forged))
    predecessor = ef5("A")
    arguments = arguments_for(predecessor, ("A1",))
    arguments["variant_metrics"] = (EdgeVariantMetricsInput(forged, forged.result_digest),)
    evidence = build_edge_walk_forward_oos_evidence(predecessor, **arguments)
    _assert_shape(evidence)
    assert any(
        code.startswith(_code("variant_metrics_0:integrity_failure:")) for code in evidence.integrity_reason_codes
    )
    assert evidence.performance_data_consumed is False


def test_metrics_anchor_mismatch_is_rejected() -> None:
    predecessor = ef5("A")
    arguments = arguments_for(predecessor, ("A1",))
    arguments["variant_metrics"] = (EdgeVariantMetricsInput(metrics("A1"), "f" * 64),)
    evidence = build_edge_walk_forward_oos_evidence(predecessor, **arguments)
    assert evidence.integrity_reason_codes == (_code("variant_metrics_0:digest_mismatch"),)


@SLOW
def test_profile_semantics_drift_rejects_the_whole_chain(monkeypatch: pytest.MonkeyPatch) -> None:
    genuine = passed()
    drifted = bind.drifted_registry_profile(max_decimal_text_length=59)
    _MEMO_ENABLED[0] = False
    try:
        monkeypatch.setitem(profiles_module._REGISTRY, bind.PASSIVE_FUNDING_CARRY_V1, drifted)
        _assert_not_intact(genuine, "field_mismatch:status")
    finally:
        _MEMO_ENABLED[0] = True


# --- registered-variant coverage and assignment provenance ------------------------------------------------------------


def test_unregistered_excellent_assignment_is_rejected_regardless_of_performance() -> None:
    assert passed().variant_evaluations[0].evaluation_status is EdgeVariantEvaluationStatus.SURVIVED
    evidence = ef6("B", ("A1",), governance=None)
    _assert_shape(evidence)
    assert any(code.endswith(":parameter_assignment_unregistered") for code in evidence.integrity_reason_codes)
    assert evidence.surviving_assignment_digests == ()


def test_duplicate_evaluation_of_one_assignment_is_rejected() -> None:
    evidence = ef6("A", ("A1", "A1dup"), governance=None)
    _assert_shape(evidence)
    duplicated = ef5("A").registered_parameter_assignment_digests[0]
    assert evidence.integrity_reason_codes == (_code(f"parameter_assignment_evaluated_more_than_once:{duplicated}"),)


def test_identical_duplicate_input_is_a_construction_error() -> None:
    predecessor = ef5("A")
    arguments = arguments_for(predecessor, ("A", "A"))
    with pytest.raises(EdgeWalkForwardOosEvidenceError) as excinfo:
        build_edge_walk_forward_oos_evidence(predecessor, **arguments)
    assert str(excinfo.value) == _code("variant_metrics_duplicate")


def test_missing_registered_variant_is_incomplete_coverage_fail() -> None:
    evidence = ef6("AB", ("A1",))
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.verdict_reason_codes == (_code("registered_variant_not_evaluated:variant-b"),)
    assert evidence.surviving_assignment_digests == ()
    assert [item.evaluation_status for item in evidence.variant_evaluations] == [
        EdgeVariantEvaluationStatus.NOT_EVALUATED
    ]
    assert (evidence.registered_variant_count, evidence.evaluated_variant_count) == (2, 1)


def test_no_variant_evaluated_is_fail_and_consumes_nothing() -> None:
    evidence = ef6("A", (), governance=None)
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("registered_variant_not_evaluated:variant-a") in evidence.verdict_reason_codes
    assert (evidence.performance_data_consumed, evidence.walk_forward_evaluated) == (False, False)


@SLOW
def test_per_window_assignment_switching_is_rejected() -> None:
    switching = metrics("AB2")
    assert switching.computation_verdict is EdgeGateVerdict.PASS  # P3 permits it; EF-6 must not
    evidence = ef6("AB", ("AB2", "B1"), governance=None)
    _assert_shape(evidence)
    switching = [code for code in evidence.integrity_reason_codes if code.endswith(":parameter_assignment_switching")]
    assert len(switching) == 1


# --- window fairness ----------------------------------------------------------------------------------------------------


@SLOW
@pytest.mark.parametrize(
    ("reference", "candidate", "computed"),
    [
        ("A", "B2", True),  # one window missing (equivalently: the reference has an extra window)
        ("A2w", "B2rev", False),  # the same two windows in another order (P3 cannot compute it; EF-6 still refuses it)
        ("A1", "B1fee", True),  # the same window under another cost model (fee), everything else identical
        ("A1", "B1ds", True),  # the same window on another PIT dataset artifact with identical records
    ],
)
def test_result_aware_frame_differences_are_unfair_and_fail(reference: str, candidate: str, computed: bool) -> None:
    assert (metrics(candidate).computation_verdict is EdgeGateVerdict.PASS) is computed
    evidence = ef6("AB", (reference, candidate), governance=None)
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("evaluation_frame_mismatch:variant-b") in evidence.verdict_reason_codes
    assert evidence.surviving_assignment_digests == ()
    assert evidence.walk_forward_evaluated is False


# --- governance ---------------------------------------------------------------------------------------------------------


def test_missing_governance_needs_approval_and_evaluates_no_variant() -> None:
    evidence = _draft("A", ("A1",), "main")
    _assert_receipt_invariants(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == (_code("oos_governance_missing"),)
    assert evidence.variant_evaluations[0].evaluation_status is EdgeVariantEvaluationStatus.NOT_EVALUATED
    assert (evidence.performance_data_consumed, evidence.walk_forward_evaluated) == (True, False)
    assert evidence.governance is None and evidence.governance_digest == ""


def test_copied_governance_with_every_commitment_changed_needs_approval() -> None:
    approval = governance_for(
        passed(),
        approved_predecessor_digest="0" * 64,
        approved_variant_ledger_digest="1" * 64,
        approved_multiple_testing_count=2,
        approved_rule_set_digest="2" * 64,
        approved_evaluation_frame_digest="3" * 64,
    )
    evidence = ef6("A", ("A1",), governance=approval)
    _assert_shape(evidence)
    assert evidence.verdict_reason_codes == tuple(
        sorted(
            _code(f"oos_governance_{name}_mismatch")
            for name in (
                "predecessor_digest",
                "variant_ledger_digest",
                "multiple_testing_count",
                "rule_set_digest",
                "evaluation_frame_digest",
            )
        )
    )
    assert evidence.surviving_assignment_digests == ()


def test_governance_approved_for_another_ledger_cannot_be_reused() -> None:
    evidence = ef6("AB", ("A1",), governance=governance_for(passed()))
    assert evidence.advances is False
    assert {
        _code("oos_governance_predecessor_digest_mismatch"),
        _code("oos_governance_variant_ledger_digest_mismatch"),
        _code("oos_governance_multiple_testing_count_mismatch"),
    } <= set(evidence.verdict_reason_codes)


def test_governance_looser_than_prdv4_floors_needs_approval() -> None:
    approval = governance_for(
        _draft("A", ("A1",), "main"),
        min_oos_window_count=2,
        min_in_sample_closed_trade_count=49,
        min_sharpe_retention_ratio="0.499999999999999999",
        min_hit_rate_delta_percentage_points="-10.000000000000000001",
        positive_expectancy_fraction_numerator=1,
        positive_expectancy_fraction_denominator=2,
    )
    evidence = ef6("A", ("A1",), governance=approval)
    assert evidence.verdict_reason_codes == tuple(
        sorted(
            _code(f"oos_governance_below_prdv4_floor:{name}")
            for name in (
                "min_oos_window_count",
                "min_in_sample_closed_trade_count",
                "min_sharpe_retention_ratio",
                "min_hit_rate_delta_percentage_points",
                "positive_expectancy_fraction",
            )
        )
    )


def test_no_production_default_exists_for_any_governed_value() -> None:
    assert inspect.signature(build_edge_walk_forward_oos_evidence).parameters["governance"].default is None
    assert all(field.default is MISSING for field in fields(EdgeWalkForwardOosGovernance))
    rules = edge_walk_forward_oos_rule_set()
    assert not [key for key in rules if key.startswith(("min_", "max_")) and not key.startswith("prdv4")]


def test_stricter_approved_minimum_window_count_is_enforced() -> None:
    evidence = ef6("A", governance=governance_for(passed(), min_oos_window_count=4))
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert evidence.verdict_reason_codes == (_code("no_registered_variant_survived"),)
    assert evidence.variant_evaluations[0].failure_codes == ("oos_window_count_below_minimum",)


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"approval_reference": ""}, "governance_approval_reference_invalid"),
        ({"approval_reference": "bist-committee"}, "bist_scope_leakage:governance_approval_reference"),
        ({"approval_digest": "A" * 64}, "governance_approval_digest_invalid"),
        ({"approved_multiple_testing_count": 0}, "governance_approved_multiple_testing_count_invalid"),
        ({"approved_multiple_testing_count": True}, "governance_approved_multiple_testing_count_invalid"),
        ({"min_oos_window_count": 2**63}, "governance_min_oos_window_count_invalid"),
        ({"min_sharpe_retention_ratio": 0.5}, "governance_min_sharpe_retention_ratio_invalid"),
        ({"min_sharpe_retention_ratio": "0.5"}, "governance_min_sharpe_retention_ratio_invalid"),
        ({"min_hit_rate_delta_percentage_points": "-10"}, "governance_min_hit_rate_delta_percentage_points_invalid"),
        ({"positive_expectancy_fraction_numerator": 4}, "governance_positive_expectancy_fraction_invalid"),
        ({"positive_expectancy_fraction_denominator": 0}, "governance_positive_expectancy_fraction_invalid"),
        ({"max_drawdown_ratio_exclusive": "0.000000000000000000"}, "governance_max_drawdown_ratio_exclusive_invalid"),
        ({"min_profit_factor_exclusive": "-1.000000000000000000"}, "governance_min_profit_factor_exclusive_invalid"),
        (
            {"profit_factor_fraction_numerator": 3, "profit_factor_fraction_denominator": 2},
            "governance_profit_factor_fraction_invalid",
        ),
    ],
)
def test_malformed_governance_is_a_construction_error(change: dict[str, object], code: str) -> None:
    with pytest.raises(EdgeWalkForwardOosEvidenceError) as excinfo:
        ef6("A", (), governance=governance_for(passed(), **change))
    assert str(excinfo.value) == _code(code)


# --- exact governed rules on real P3 metrics ----------------------------------------------------------------------------


def _windows_a():
    return metrics("A").windows


def _sharpe_boundary() -> Fraction:
    return min(_units(w.out_of_sample.annualized_sharpe) / _units(w.in_sample.annualized_sharpe) for w in _windows_a())


def _hit_boundary_pp() -> Fraction:
    return min(100 * (_units(w.out_of_sample.hit_rate) - _units(w.in_sample.hit_rate)) for w in _windows_a())


def _closed_trades(start_day: int, **kwargs: object) -> int:
    """CLOSED excursions of a real in-sample economics result, counted from the typed ledger (independently of EF-6)."""

    trades = economics(start_day, 365, PA, **kwargs).trades
    return sum(1 for trade in trades if trade.status is HistoricalExecutionTradeStatus.CLOSED)


def _trade_boundary() -> int:
    return min(_closed_trades(start) for start in STARTS)


_BOUNDARY_CASES = [
    (lambda: {"min_sharpe_retention_ratio": _text(_floor18(_sharpe_boundary()))}, True),
    (lambda: {"min_sharpe_retention_ratio": _text(_floor18(_sharpe_boundary()) + ULP)}, False),
    (lambda: {"min_hit_rate_delta_percentage_points": _text(_hit_boundary_pp())}, True),
    (lambda: {"min_hit_rate_delta_percentage_points": _text(_hit_boundary_pp() + ULP)}, False),
    (lambda: {"max_drawdown_ratio_exclusive": "1.000000000000000000"}, False),
    (lambda: {"max_drawdown_ratio_exclusive": "1.000000000000000001"}, True),
    (lambda: {"min_profit_factor_exclusive": _windows_a()[0].out_of_sample.profit_factor}, False),
    (lambda: {"min_profit_factor_exclusive": _text(_units(_windows_a()[0].out_of_sample.profit_factor) - ULP)}, True),
    (lambda: {"positive_expectancy_fraction_numerator": 1, "positive_expectancy_fraction_denominator": 1}, True),
    (lambda: {"min_in_sample_closed_trade_count": _trade_boundary()}, True),
    (lambda: {"min_in_sample_closed_trade_count": _trade_boundary() + 1}, False),
]


@pytest.mark.parametrize(("override", "survives"), _BOUNDARY_CASES)
def test_exact_rule_boundaries_on_authenticated_metrics(override, survives: bool) -> None:
    """The governed rules applied to world A's REAL authenticated P3 window texts at each exact boundary."""

    record = governance_for(passed(), **override())
    _, thresholds = ef6_module._governance_reasons(
        record,
        {
            "predecessor_digest": record.approved_predecessor_digest,
            "variant_ledger_digest": record.approved_variant_ledger_digest,
            "multiple_testing_count": record.approved_multiple_testing_count,
            "rule_set_digest": record.approved_rule_set_digest,
            "evaluation_frame_digest": record.approved_evaluation_frame_digest,
        },
    )
    assert thresholds is not None
    bundle = ef6_module._Bundle(
        metrics=metrics("A"),
        binding=EdgeAuthorityBinding(snapshot_json="{}", expected_digest=metrics("A").result_digest),
        assignment_digest=ef5("A").registered_parameter_assignment_digests[0],
        frames=(),
        in_sample_closed_trade_counts=tuple(_closed_trades(start) for start in STARTS),
    )
    evaluation = ef6_module._evaluate_bundle("variant-a", bundle, thresholds)
    expected = EdgeVariantEvaluationStatus.SURVIVED if survives else EdgeVariantEvaluationStatus.FAILED
    assert evaluation.evaluation_status is expected


@SLOW
@pytest.mark.parametrize(("override", "survives"), [_BOUNDARY_CASES[0], _BOUNDARY_CASES[1]])
def test_exact_boundary_through_the_public_builder(override, survives: bool) -> None:
    evidence = ef6("A", governance=governance_for(passed(), **override()))
    _assert_shape(evidence)
    assert evidence.gate_verdict is (EdgeGateVerdict.PASS if survives else EdgeGateVerdict.FAIL)


def test_in_sample_closed_trade_count_is_read_from_the_authenticated_trade_ledger() -> None:
    """PRDV4 §1.13 Stage 1: each window's count equals the real IS ledger's CLOSED excursions; OPEN is not a trade."""

    outcomes = passed().variant_evaluations[0].window_outcomes
    assert [outcome.in_sample_closed_trade_count for outcome in outcomes] == [_closed_trades(s) for s in STARTS]
    assert all(outcome.in_sample_trade_count_holds for outcome in outcomes)
    ledger = economics(0, 365, PA).trades
    assert (_closed_trades(0), len(ledger), ledger[-1].status) == (60, 61, HistoricalExecutionTradeStatus.OPEN)


def test_governed_trade_minimum_above_the_real_count_fails_every_window() -> None:
    evidence = ef6("A", governance=governance_for(passed(), min_in_sample_closed_trade_count=_trade_boundary() + 1))
    _assert_shape(evidence)
    assert (evidence.status, evidence.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    evaluation = evidence.variant_evaluations[0]
    assert evaluation.failure_codes == tuple(f"window_{i}:in_sample_closed_trade_count_below_minimum" for i in range(3))
    assert not any(outcome.in_sample_trade_count_holds for outcome in evaluation.window_outcomes)
    assert evidence.surviving_assignment_digests == ()


@SLOW
def test_a_backtest_without_fifty_closed_trades_cannot_survive() -> None:
    """The reviewed gap: every performance rule holds, but no in-sample segment carries the 50 PRDV4 closed trades."""

    assert [_closed_trades(start, dataset_id=SPARSE_DATASET) for start in STARTS] == [0, 0, 0]
    evidence = ef6("A", ("Asparse",))
    _assert_shape(evidence)
    assert (evidence.status, evidence.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.FAIL)
    evaluation = evidence.variant_evaluations[0]
    assert evaluation.failure_codes == tuple(f"window_{i}:in_sample_closed_trade_count_below_minimum" for i in range(3))
    assert [outcome.in_sample_closed_trade_count for outcome in evaluation.window_outcomes] == [0, 0, 0]
    assert evidence.surviving_assignment_digests == ()


@pytest.mark.parametrize(
    ("snapshot", "expected"),
    [
        ({"trades": []}, 0),
        ({"trades": [{"status": "CLOSED"}, {"status": "OPEN"}, {"status": "CLOSED"}]}, 2),
        ({}, None),
        ({"trades": [{"status": "CLOSED"}, "CLOSED"]}, None),
        ({"trades": [{"status": "closed"}]}, None),
        ({"trades": [{}]}, None),
        ({"trades": {"status": "CLOSED"}}, None),
    ],
)
def test_closed_trade_count_reads_only_an_exact_trade_ledger_shape(snapshot: dict, expected: int | None) -> None:
    assert ef6_module._closed_trade_count(snapshot) == expected


def test_hit_rate_boundary_is_a_ratio_delta_in_percentage_points() -> None:
    boundary = _hit_boundary_pp()
    assert -1 < boundary < 0  # under one percentage point, i.e. well under 0.01 in ratio units
    wrong_unit = _text(boundary / 100)  # treating the ratio delta as percentage points would be 100x too lenient
    evidence = ef6("A", governance=governance_for(passed(), min_hit_rate_delta_percentage_points=wrong_unit))
    assert evidence.variant_evaluations[0].evaluation_status is EdgeVariantEvaluationStatus.FAILED
    assert "window_1:hit_rate_retention_below_minimum" in evidence.variant_evaluations[0].failure_codes


def _segment(sharpe: str, hit: str, drawdown: str, expectancy: str, profit_factor: str):
    return HistoricalWalkForwardSegmentMetrics(
        segment_kind=S.IN_SAMPLE,
        source_result_id="r",
        source_result_digest="0" * 64,
        source_valuation_ledger_digest="0" * 64,
        evaluation_start_ns=1,
        evaluation_end_ns=2,
        daily_endpoint_count=2,
        daily_endpoint_digest="0" * 64,
        daily_return_count=1,
        positive_daily_return_count=1,
        negative_daily_return_count=0,
        zero_daily_return_count=0,
        start_equity=d(1),
        end_equity=d(1),
        annualized_sharpe=sharpe,
        hit_rate=hit,
        expectancy=expectancy,
        max_drawdown=drawdown,
        profit_factor=profit_factor,
        segment_digest="0" * 64,
    )


def _window_metrics(
    index: int,
    *,
    is_sharpe="1",
    oos_sharpe="1",
    is_hit="0.5",
    oos_hit="0.5",
    is_dd="0.1",
    oos_dd="0.1",
    oos_e="0.1",
    oos_pf="2",
):
    return HistoricalWalkForwardWindowMetrics(
        window_index=index,
        window_id=f"w{index}",
        parameter_assignment_digest="0" * 64,
        in_sample=_segment(d(Fraction(is_sharpe)), d(Fraction(is_hit)), d(Fraction(is_dd)), d(0), d(2)),
        out_of_sample=_segment(
            d(Fraction(oos_sharpe)), d(Fraction(oos_hit)), d(Fraction(oos_dd)), d(Fraction(oos_e)), d(Fraction(oos_pf))
        ),
        window_digest=f"{index}" * 64,
    )


def _thresholds(**changes: object):
    values = {
        "min_windows": 3,
        "min_in_sample_closed_trades": 50,
        "sharpe_ratio": 5 * 10**17,
        "hit_delta_pp": -10 * 10**18,
        "expectancy_fraction": (2, 3),
        "drawdown_ratio": 2 * 10**18,
        "profit_factor_min": 10**18,
        "profit_factor_fraction": (2, 3),
    }
    values.update(changes)
    return ef6_module._Thresholds(**values)  # type: ignore[arg-type]


def _evaluate(windows, closed_trades: int = 50, **changes: object):
    bundle = ef6_module._Bundle(
        metrics=replace(metrics("A"), windows=tuple(windows), window_count=len(windows)),
        binding=EdgeAuthorityBinding(snapshot_json="{}", expected_digest="a" * 64),
        assignment_digest="b" * 64,
        frames=(),
        in_sample_closed_trade_counts=(closed_trades,) * len(windows),
    )
    return ef6_module._evaluate_bundle("variant-x", bundle, _thresholds(**changes))


def test_float_rounding_cannot_flip_an_exact_decision() -> None:
    assert 0.1 * 3.0 > 0.3  # the float product overshoots the exact boundary
    windows = [_window_metrics(i, is_sharpe="0.1", oos_sharpe="0.3") for i in range(3)]
    assert _evaluate(windows, sharpe_ratio=3 * 10**18).evaluation_status is EdgeVariantEvaluationStatus.SURVIVED
    one_over = [_window_metrics(i, is_sharpe="0.1", oos_sharpe="0.299999999999999999") for i in range(3)]
    assert _evaluate(one_over, sharpe_ratio=3 * 10**18).evaluation_status is EdgeVariantEvaluationStatus.FAILED


@pytest.mark.parametrize(
    ("expectancies", "fraction", "survives"),
    [
        (("0.1", "0.1", "-0.1"), (2, 3), True),
        (("0.1", "0", "-0.1"), (2, 3), False),  # zero expectancy is not positive
        (("0.1", "0.1", "0"), (1, 1), False),
        (("0.1", "0.1", "0.1"), (1, 1), True),
        (("0.1", "0.1", "-0.1"), (3, 4), False),  # ceil(3 x 3/4) = 3
    ],
)
def test_positive_expectancy_count_boundary(
    expectancies: tuple[str, ...], fraction: tuple[int, int], survives: bool
) -> None:
    windows = [_window_metrics(i, oos_e=value) for i, value in enumerate(expectancies)]
    evaluation = _evaluate(windows, expectancy_fraction=fraction)
    assert (evaluation.evaluation_status is EdgeVariantEvaluationStatus.SURVIVED) is survives


def test_hit_rate_ratio_versus_percentage_points_identity() -> None:
    # 0.55 ratio is 55 percentage points: a -10pp delta from 0.55 is 0.45, never 0.55 - 10.
    at = [_window_metrics(i, is_hit="0.55", oos_hit="0.45") for i in range(3)]
    below = [_window_metrics(i, is_hit="0.55", oos_hit="0.449999999999999999") for i in range(3)]
    assert _evaluate(at).evaluation_status is EdgeVariantEvaluationStatus.SURVIVED
    assert _evaluate(below).evaluation_status is EdgeVariantEvaluationStatus.FAILED


def test_zero_in_sample_drawdown_can_never_satisfy_the_drawdown_rule() -> None:
    windows = [_window_metrics(i, is_dd="0", oos_dd="0") for i in range(3)]
    evaluation = _evaluate(windows)
    assert evaluation.evaluation_status is EdgeVariantEvaluationStatus.FAILED
    assert "window_0:in_sample_max_drawdown_not_positive" in evaluation.failure_codes


@pytest.mark.parametrize(
    "shape",
    [
        {},
        {"oos_sharpe": "0.4"},
        {"oos_hit": "0.39"},
        {"oos_dd": "0.25"},
        {"oos_e": "-0.1"},
        {"oos_pf": "0.9"},
    ],
)
def test_legacy_walk_forward_semantic_parity_away_from_boundaries(shape: dict[str, str]) -> None:
    windows = [_window_metrics(0, **shape), _window_metrics(1), _window_metrics(2, **shape)]
    exact = _evaluate(windows)
    legacy = validate_walk_forward(
        tuple(
            WalkForwardWindow(
                window_id=w.window_id,
                in_sample_sharpe=float(_units(w.in_sample.annualized_sharpe)),
                out_of_sample_sharpe=float(_units(w.out_of_sample.annualized_sharpe)),
                oos_expectancy=float(_units(w.out_of_sample.expectancy)),
                in_sample_hit_rate=float(100 * _units(w.in_sample.hit_rate)),
                out_of_sample_hit_rate=float(100 * _units(w.out_of_sample.hit_rate)),
                trade_count=1,
                evidence_count=1,
                in_sample_max_drawdown=float(_units(w.in_sample.max_drawdown)),
                oos_max_drawdown=float(_units(w.out_of_sample.max_drawdown)),
                oos_profit_factor=float(_units(w.out_of_sample.profit_factor)),
            )
            for w in windows
        )
    )
    assert (exact.evaluation_status is EdgeVariantEvaluationStatus.SURVIVED) is legacy.supportive


# --- costs, synthetic facts, multi-instrument and regime ---------------------------------------------------------------


def test_costs_are_proven_upstream_and_never_added_again() -> None:
    evidence = passed()
    assert evidence.cost_accounting_basis_id.startswith(
        "historical_execution_economics_equity_net_of_taker_fees_funding"
    )
    source = economics(0, 365, PA)
    assert source.fee_cashflows and source.funding_cashflows and source.fills
    # The profit-factor boundary sits EXACTLY on the P3 text: EF-6 adjusts no metric by any cost.
    pf = _windows_a()[0].out_of_sample.profit_factor
    at = ef6("A", governance=governance_for(passed(), min_profit_factor_exclusive=pf))
    assert at.variant_evaluations[0].profit_factor_window_count == 0


@SLOW
def test_synthetic_facts_and_approval_can_never_advance_a_real_gate() -> None:
    assert metrics("Asyn1").synthetic_test_facts_used is True
    assert metrics("Asyn1").synthetic_test_approval_used is True
    evidence = ef6("A", ("Asyn1",), governance=AUTO)
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS
    assert {
        _code("synthetic_test_facts_used:variant-a"),
        _code("synthetic_test_approval_used:variant-a"),
    } <= set(evidence.verdict_reason_codes)
    assert evidence.surviving_assignment_digests == ()
    assert evidence.variant_evaluations[0].evaluation_status is EdgeVariantEvaluationStatus.NOT_EVALUATED


@SLOW
def test_multi_instrument_universe_fails_closed_without_overclaiming() -> None:
    evidence = ef6("A", ("Amulti1",), world_name="multi", governance=None)
    _assert_shape(evidence)
    assert evidence.pinned_instrument_universe == (INS, "ETH-USDT-PERP")
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("multi_instrument_universe_unsupported_v1") in evidence.verdict_reason_codes
    assert evidence.surviving_assignment_digests == ()
    assert evidence.variant_evaluations[0].evaluation_status is EdgeVariantEvaluationStatus.NOT_EVALUATED


def test_regime_state_is_always_present_and_explicitly_unavailable() -> None:
    for evidence in (passed(), _draft("A", ("A1",), "main")):
        assert evidence.regime_split_report == EDGE_REGIME_EVIDENCE_UNAVAILABLE
        assert evidence.regime_evidence_status == EDGE_REGIME_EVIDENCE_UNAVAILABLE
        assert evidence.regime_evidence_available is False


# --- protected audit repairs: the signed PRDV4 Sharpe floor and one economics-policy frame ----------------------------

_RATIOS = ("0.500000000000000000", "1.000000000000000000", "2.000000000000000000")


def _ratio_units(ratio: str) -> int:
    return int(Fraction(ratio) * 10**18)


@pytest.mark.parametrize("ratio", _RATIOS)
def test_negative_in_sample_sharpe_is_never_loosened_by_a_larger_approved_ratio(ratio: str) -> None:
    """A signed product ``OOS >= IS x ratio`` alone lets a larger ratio LOWER the bar when IS Sharpe is negative."""

    window = metrics("Aneg1").windows[0]
    is_sharpe, oos_sharpe = _units(window.in_sample.annualized_sharpe), _units(window.out_of_sample.annualized_sharpe)
    assert is_sharpe < oos_sharpe < 0 and oos_sharpe < is_sharpe / 2  # the audited shape, on REAL P3 texts
    bundle = ef6_module._Bundle(
        metrics=metrics("Aneg1"),
        binding=EdgeAuthorityBinding(snapshot_json="{}", expected_digest=metrics("Aneg1").result_digest),
        assignment_digest=ef5("A").registered_parameter_assignment_digests[0],
        frames=(),
        in_sample_closed_trade_counts=(_closed_trades(0, dataset_id=LOSING_DATASET),),
    )
    assert bundle.in_sample_closed_trade_counts == (60,)
    evaluation = ef6_module._evaluate_bundle("variant-a", bundle, _thresholds(sharpe_ratio=_ratio_units(ratio)))
    outcome = evaluation.window_outcomes[0]
    assert outcome.sharpe_retention_holds is False
    assert (outcome.hit_rate_retention_holds, outcome.drawdown_holds, outcome.in_sample_trade_count_holds) == (
        True,
        True,
        True,
    )
    assert "window_0:sharpe_retention_below_minimum" in evaluation.failure_codes


@SLOW
@pytest.mark.parametrize("ratio", _RATIOS)
def test_the_audited_negative_sharpe_bundle_never_passes_at_any_approved_ratio(ratio: str) -> None:
    """Two profitable windows and one losing window: before the repair, ratio 1.0 made it SURVIVE and advance."""

    record = governance_for(_draft("A", ("Aneg3",), "main"), min_sharpe_retention_ratio=ratio)
    evidence = ef6("A", ("Aneg3",), governance=record)
    _assert_shape(evidence)
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.FAIL,
        False,
    )
    assert evidence.surviving_assignment_digests == ()
    evaluation = evidence.variant_evaluations[0]
    assert "window_0:sharpe_retention_below_minimum" in evaluation.failure_codes
    if ratio == _RATIOS[0]:
        assert evaluation.failure_codes == ("window_0:sharpe_retention_below_minimum",)


@pytest.mark.parametrize(
    ("is_sharpe", "oos_sharpe", "ratio", "holds"),
    [
        ("-1", "-0.5", "0.5", True),  # exactly the PRDV4 floor
        ("-1", "-0.5", "2", True),  # a larger approved ratio never lowers the bar below the floor ...
        ("-1", "-0.500000000000000001", "0.5", False),
        ("-1", "-0.500000000000000001", "2", False),  # ... nor raises the pass set above it
        ("-1", "-1", "1", False),  # the signed product alone would accept this
        ("-12.316407671228772967", "-11.994822050568919996", "1", False),  # the audit reproduction values
        ("-12.316407671228772967", "-11.994822050568919996", "2", False),
        ("-1", "-0.4", "2", True),  # no positive-Sharpe requirement is invented
        ("0", "0", "2", True),
        ("0", "-0.000000000000000001", "0.5", False),
        ("1", "0.5", "0.5", True),
        ("1", "0.5", "1", False),  # for a positive IS Sharpe a larger approved ratio is genuinely stricter
        ("1", "1", "1", True),
        ("1", "1.999999999999999999", "2", False),
        ("1", "2", "2", True),
    ],
)
def test_sharpe_threshold_is_the_stricter_of_the_prdv4_floor_and_the_approved_ratio(
    is_sharpe: str, oos_sharpe: str, ratio: str, holds: bool
) -> None:
    windows = [_window_metrics(i, is_sharpe=is_sharpe, oos_sharpe=oos_sharpe) for i in range(3)]
    expected = EdgeVariantEvaluationStatus.SURVIVED if holds else EdgeVariantEvaluationStatus.FAILED
    assert _evaluate(windows, sharpe_ratio=_ratio_units(ratio)).evaluation_status is expected


def test_sharpe_rule_is_monotone_in_the_approved_ratio_for_every_signed_sharpe() -> None:
    values = ("-3", "-1.5", "-1", "-0.5", "-0.05", "0", "0.05", "0.5", "1", "1.5", "3")
    ratios = ("0.5", "0.75", "1", "2", "5")
    for is_sharpe in values:
        for oos_sharpe in values:
            window = _window_metrics(0, is_sharpe=is_sharpe, oos_sharpe=oos_sharpe)
            holds = [
                ef6_module._window_outcome(window, 50, _thresholds(sharpe_ratio=_ratio_units(r)))[
                    0
                ].sharpe_retention_holds
                for r in ratios
            ]
            assert holds == sorted(holds, reverse=True), (is_sharpe, oos_sharpe)  # a larger ratio is never easier
            assert holds[0] is (Fraction(oos_sharpe) >= Fraction(is_sharpe) / 2)  # the PRDV4 floor, exactly


def test_forged_sharpe_outcome_with_reseal_never_verifies() -> None:
    payload = _payload(ef6("A", ("Aneg1",)))
    assert payload["variant_evaluations"][0]["window_outcomes"][0]["sharpe_retention_holds"] is False
    payload["variant_evaluations"][0]["window_outcomes"][0]["sharpe_retention_holds"] = True
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:variant_evaluations")


def test_an_out_of_sample_source_under_another_economics_policy_makes_the_set_inadmissible() -> None:
    upstream = metrics("A1mixoos")
    assert verify_historical_walk_forward_metrics(upstream).intact is True  # P3 itself stays intact ...
    assert upstream.verdict_reason_codes == (
        "historical_walk_forward_metrics:source_inconsistent:economics_policy_digest",
    )  # ... and only reports a computation FAIL
    evidence = ef6("A", ("A1mixoos",))
    _assert_shape(evidence)
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.FAIL,
        False,
    )
    assert evidence.surviving_assignment_digests == ()
    assert (
        _code("economics_policy_outside_evaluation_frame:variant-a:window_0:out_of_sample")
        in evidence.verdict_reason_codes
    )
    frame = evidence.window_frames[0]
    assert frame.in_sample_economics_policy_digest == economics_policy().policy_digest
    assert frame.out_of_sample_economics_policy_digest == economics_policy(d(6)).policy_digest
    forged = _payload(evidence)
    forged.update(gate_verdict="PASS", advances=True, verdict_reason_codes=[])
    _assert_not_intact(_resealed_payload(forged), "field_mismatch:gate_verdict")


def test_a_consistent_economics_policy_frame_keeps_the_happy_path() -> None:
    evidence = passed()
    assert evidence.gate_verdict is EdgeGateVerdict.PASS
    policies = {
        policy
        for frame in evidence.window_frames
        for policy in (frame.in_sample_economics_policy_digest, frame.out_of_sample_economics_policy_digest)
    }
    assert policies == {evidence.economics_policy_digest} == {economics_policy().policy_digest}


@SLOW
def test_a_later_in_sample_source_of_another_variant_under_another_policy_blocks_every_survivor() -> None:
    """The audit reproduction: variant A would survive; B's window-1 IS source uses another economics policy."""

    assert verify_historical_walk_forward_metrics(metrics("Bmix3")).intact is True
    evidence = ef6("AB", ("A", "Bmix3"))
    _assert_shape(evidence)
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.FAIL,
        False,
    )
    assert evidence.surviving_assignment_digests == ()
    assert {
        _code("economics_policy_outside_evaluation_frame:variant-b:window_1:in_sample"),
        _code("evaluation_frame_mismatch:variant-b"),
    } <= set(evidence.verdict_reason_codes)
    statuses = {item.variant_id: item.evaluation_status for item in evidence.variant_evaluations}
    assert statuses == {
        "variant-a": EdgeVariantEvaluationStatus.NOT_EVALUATED,
        "variant-b": EdgeVariantEvaluationStatus.FAILED,
    }


@pytest.mark.parametrize(("closed", "survives"), [(49, False), (50, True)])
def test_the_prdv4_trade_floor_counts_closed_trades_and_never_the_open_one(closed: int, survives: bool) -> None:
    ledger = {"trades": [{"status": "CLOSED"}] * closed + [{"status": "OPEN"}]}
    counted = ef6_module._closed_trade_count(ledger)
    assert counted == closed
    evaluation = _evaluate([_window_metrics(i) for i in range(3)], closed_trades=counted)
    assert (evaluation.evaluation_status is EdgeVariantEvaluationStatus.SURVIVED) is survives
    if not survives:
        assert evaluation.failure_codes == tuple(
            f"window_{i}:in_sample_closed_trade_count_below_minimum" for i in range(3)
        )


# --- tamper, reseal and totality ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("artifact", "changes", "field"),
    [
        ("passed", {"surviving_assignment_digests": ()}, "surviving_assignment_digests"),
        ("failed1", {"surviving_variant_count": 1}, "surviving_variant_count"),
        ("failed1", {"window_frames": ()}, "window_frames"),
        ("cheap", {"surviving_assignment_digests": ("a" * 64,)}, "surviving_assignment_digests"),
        ("cheap", {"multiple_testing_count": 5}, "multiple_testing_count"),
        ("cheap", {"registered_variant_count": 2}, "registered_variant_count"),
        ("cheap", {"regime_evidence_available": True}, "regime_evidence_available"),
        ("cheap", {"regime_split_report": "bull:0.9"}, "regime_split_report"),
        ("cheap", {"rule_set_digest": "0" * 64}, "rule_set_digest"),
        ("cheap", {"governance_digest": "0" * 64}, "governance_digest"),
        ("cheap", {"evaluation_frame_digest": "0" * 64}, "evaluation_frame_digest"),
        ("cheap", {"cost_accounting_basis_id": "costs_included"}, "cost_accounting_basis_id"),
        ("cheap", {"performance_data_consumed": True}, "performance_data_consumed"),
        ("cheap", {"oos_evidence_consumed": True}, "oos_evidence_consumed"),
        ("cheap", {"walk_forward_evaluated": True}, "walk_forward_evaluated"),
        ("cheap", {"performance_metrics_computed": True}, "performance_metrics_computed"),
        ("cheap", {"pbo_passed": True}, "pbo_passed"),
        ("cheap", {"stress_passed": True}, "stress_passed"),
        ("cheap", {"candidate_admitted_to_paper": True}, "candidate_admitted_to_paper"),
        ("cheap", {"edge_proven": True}, "edge_proven"),
        ("cheap", {"profitability_proven": True}, "profitability_proven"),
        ("cheap", {"kill_criteria_sealed": True}, "kill_criteria_sealed"),
        ("cheap", {"live_ready": True}, "live_ready"),
        ("cheap", {"real_capital_reserved": True}, "real_capital_reserved"),
    ],
)
def test_derived_field_tamper_with_reseal_never_verifies(artifact: str, changes: dict[str, object], field: str) -> None:
    base = {"passed": passed, "failed1": failed1, "cheap": cheap}[artifact]()
    _assert_not_intact(_reseal(base, **changes), f"field_mismatch:{field}")


def test_tampered_variant_verdict_and_forced_pass_never_verify() -> None:
    draft = _draft("A", ("A1",), "main")
    variant = replace(draft.variant_evaluations[0], evaluation_status=EdgeVariantEvaluationStatus.SURVIVED)
    forced = _reseal(
        draft,
        variant_evaluations=(variant,),
        surviving_assignment_digests=(variant.parameter_assignment_digest,),
        surviving_variant_count=1,
        gate_verdict=EdgeGateVerdict.PASS,
        advances=True,
        verdict_reason_codes=(),
    )
    _assert_not_intact(forced, "field_mismatch:variant_evaluations", "field_mismatch:gate_verdict")


def test_changed_approval_values_change_the_evidence_deterministically() -> None:
    stricter = ef6("A", ("A1",), governance=governance_for(_draft("A", ("A1",), "main"), min_oos_window_count=4))
    assert stricter.governance_digest != failed1().governance_digest
    payload = _failed1_payload()
    payload["governance"]["min_oos_window_count"] = 4
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:governance_digest")


def test_forged_in_sample_trade_count_with_reseal_never_verifies() -> None:
    payload = _failed1_payload()
    payload["variant_evaluations"][0]["window_outcomes"][0]["in_sample_closed_trade_count"] = 999
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:variant_evaluations")


def test_nested_metrics_forgery_with_every_digest_recomputed_never_verifies() -> None:
    payload = _failed1_payload()
    snapshot = payload["variant_metrics_bindings"][0]["snapshot"]
    snapshot["windows"][0]["out_of_sample"]["annualized_sharpe"] = "99.000000000000000000"
    snapshot["result_digest"] = edge_payload_digest(snapshot, "result_digest")
    payload["variant_metrics_bindings"][0]["expected_digest"] = snapshot["result_digest"]
    _assert_not_intact(_resealed_payload(payload), "field_mismatch:status")


def test_deterministic_rebuild_is_byte_identical() -> None:
    again = ef6("A", ("A1",), governance=failed1().governance)
    assert again == failed1()
    assert edge_canonical_json(edge_walk_forward_oos_evidence_to_dict(again)) == _failed1_payload_text()


@SLOW
def test_rebuild_is_input_order_insensitive() -> None:
    first = passed_an()
    again = ef6("AN", ("N", "A"), governance=first.governance)
    assert edge_walk_forward_oos_evidence_to_dict(again) == edge_walk_forward_oos_evidence_to_dict(first)


def _corrupted(**changes: object) -> EdgeWalkForwardOosEvidence:
    copy = replace(cheap())
    for name, value in changes.items():
        object.__setattr__(copy, name, value)
    return copy


def _cyclic() -> list:
    loop: list = []
    loop.append(loop)
    return loop


@pytest.mark.parametrize(
    "artifact",
    [
        None,
        0,
        "ef6",
        object(),
        {},
        [],
        object.__new__(EdgeWalkForwardOosEvidence),
        ef5("A"),
        _corrupted(variant_metrics_bindings=None),
        _corrupted(variant_metrics_bindings=(object(),)),
        _corrupted(variant_metrics_bindings=(EdgeAuthorityBinding(snapshot_json="{", expected_digest="a" * 64),)),
        _corrupted(predecessor_binding=object.__new__(EdgeAuthorityBinding)),
        _corrupted(governance=object()),
        _corrupted(window_frames=_cyclic()),
        _corrupted(multiple_testing_count="1"),
        _corrupted(status="READY"),
        _corrupted(evidence_id="ef6 scheduler"),
    ],
)
def test_public_verifier_is_total_for_any_object(artifact: object) -> None:
    _assert_not_intact(artifact)


@pytest.mark.parametrize(
    ("base", "path", "value"),
    [
        ("cheap", ("status",), None),
        ("cheap", ("multiple_testing_count",), True),
        ("cheap", ("multiple_testing_count",), -1),
        ("cheap", ("surviving_variant_count",), 1.0),
        ("cheap", ("governance",), {}),
        ("cheap", ("governance", "min_oos_window_count"), "3"),
        ("passed", ("variant_evaluations", 0, "evaluation_status"), "WINNER"),
        ("passed", ("variant_evaluations", 0, "extra"), 1),
        ("passed", ("window_frames", 0, "in_sample_start_ns"), -1),
        ("passed", ("variant_metrics_bindings", 0, "snapshot"), {}),
        ("cheap", ("predecessor_binding", "snapshot"), {}),
        ("cheap", ("performance_data_consumed",), 1),
        ("cheap", ("walk_forward_evaluated",), _UNSET),
    ],
)
def test_parser_refuses_every_state_the_builder_cannot_produce(
    base: str, path: tuple[object, ...], value: object
) -> None:
    payload = _failed1_payload() if base == "passed" else _payload(cheap())
    node = payload
    for key in path[:-1]:
        node = node[key]
    if value is _UNSET:
        del node[path[-1]]
    else:
        node[path[-1]] = value
    assert edge_walk_forward_oos_evidence_payload_is_well_formed(payload) is False


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"evidence_id": ""}, "evidence_id_invalid"),
        ({"evidence_id": "live-ef6"}, "forbidden_scope_token:evidence_id"),
        ({"evidence_id": "bist-ef6"}, "bist_scope_leakage:evidence_id"),
        ({"correlation_id": " corr-1"}, "correlation_id_invalid"),
        ({"expected_root_intake_digest": "A" * 64}, "root_intake_digest_invalid"),
        ({"expected_predecessor_digest": None}, "predecessor_expected_digest_invalid"),
        ({"variant_metrics": None}, "variant_metrics_malformed"),
        ({"variant_metrics": ("metrics",)}, "variant_metrics_entry_malformed"),
        ({"governance": "approved"}, "governance_malformed"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(overrides: dict[str, object], code: str) -> None:
    arguments = dict(overrides)
    governance = arguments.pop("governance", None)
    with pytest.raises(EdgeWalkForwardOosEvidenceError) as excinfo:
        ef6("A", (), governance=governance, **arguments)
    assert str(excinfo.value) == _code(code)


def test_performance_artifacts_other_than_p3_metrics_cannot_enter() -> None:
    predecessor = ef5("A")
    arguments = arguments_for(predecessor, ("A",))
    arguments["variant_metrics"] = (EdgeVariantMetricsInput(economics(0, 365, PA), "a" * 64),)  # type: ignore[arg-type]
    with pytest.raises(EdgeWalkForwardOosEvidenceError) as excinfo:
        build_edge_walk_forward_oos_evidence(predecessor, **arguments)
    assert str(excinfo.value) == _code("variant_metrics_result_malformed")
    with pytest.raises(EdgeWalkForwardOosEvidenceError):
        build_edge_walk_forward_oos_evidence(metrics("A"), **arguments_for(predecessor, ("A",)))  # type: ignore[arg-type]


def test_structural_non_claims_are_defaults_no_builder_parameter_can_set() -> None:
    names = {name for name, _ in EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS}
    defaults = {field.name: field.default for field in fields(EdgeWalkForwardOosEvidence) if field.name in names}
    assert defaults == dict(EDGE_WALK_FORWARD_OOS_NON_CLAIM_FLAGS)
    assert names == (
        {name for name, _ in EDGE_STRUCTURAL_NON_CLAIM_FLAGS}
        - {"preregistration_sealed", "performance_data_consumed", "oos_evidence_consumed"}
    ) | {"pbo_passed", "stress_passed", "performance_metrics_computed"}
    parameters = set(inspect.signature(build_edge_walk_forward_oos_evidence).parameters)
    assert not parameters & (names | {"performance_data_consumed", "oos_evidence_consumed", "walk_forward_evaluated"})


def test_rule_set_commits_the_prdv4_floors_and_the_hit_rate_unit_identity() -> None:
    rules = edge_walk_forward_oos_rule_set()
    assert edge_sha256_text(edge_canonical_json(rules)) == EDGE_WALK_FORWARD_OOS_RULE_SET_DIGEST
    assert rules["prdv4_min_oos_window_count"] == 3
    assert rules["prdv4_min_in_sample_closed_trade_count"] == 50
    assert "prdv4_floor" in str(rules["sharpe_retention_rule_id"])
    assert "economics_polic" in str(rules["evaluation_frame_fields_id"])
    assert str(rules["economics_policy_frame_rule_id"]).startswith("every_is_oos_economics_source")
    assert rules["prdv4_min_sharpe_retention_ratio"] == "0.500000000000000000"
    assert rules["prdv4_min_hit_rate_delta_percentage_points"] == "-10.000000000000000000"
    assert rules["prdv4_min_positive_expectancy_fraction"] == [2, 3]
    assert rules["hit_rate_unit_conversion_id"] == "p3_hit_rate_is_a_ratio_delta_percentage_points_divided_by_100.v1"
    rules["prdv4_min_oos_window_count"] = 1
    assert edge_walk_forward_oos_rule_set()["prdv4_min_oos_window_count"] == 3


@pytest.mark.parametrize(
    "state",
    [
        pytest.param("pass_partial", marks=SLOW),
        "fail_no_survivor",
        "fail_coverage",
        "needs_governance",
        pytest.param("needs_external", marks=SLOW),
        "rejected",
    ],
)
def test_every_builder_state_round_trips_through_the_verifier(state: str) -> None:
    builders = {
        "pass": passed,
        "pass_partial": passed_an,
        "fail_no_survivor": failed1,
        "fail_coverage": cheap,
        "needs_governance": lambda: _draft("A", ("A1",), "main"),
        "needs_external": lambda: ef6("A", ("Asyn1",)),
        "rejected": lambda: ef6("A", (), governance=None, correlation_id="corr-2"),
    }
    _assert_receipt_invariants(builders[state]())


# --- static purity, performance firewall and single assembly path -----------------------------------------------------

_FORBIDDEN_MODULES = (
    "math",
    "decimal",
    "fractions",
    "time",
    "datetime",
    "random",
    "secrets",
    "uuid",
    "socket",
    "ssl",
    "urllib",
    "http",
    "requests",
    "httpx",
    "aiohttp",
    "threading",
    "asyncio",
    "multiprocessing",
    "subprocess",
    "os",
    "sys",
    "pathlib",
    "shutil",
    "tempfile",
    "sqlite3",
    "logging",
    "importlib",
    "pickle",
    "bist_core",
)
_FORBIDDEN_CALLS = frozenset(
    {"open", "Path", "float", "eval", "exec", "compile", "__import__", "now", "utcnow", "time_ns", "getenv", "print"}
)


def _module_tree() -> ast.Module:
    return ast.parse(Path(ef6_module.__file__).read_text(encoding="utf-8"))


def test_module_has_no_io_clock_randomness_float_or_dynamic_execution() -> None:
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not any(alias.name == mod or alias.name.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert not any(node.module == mod or node.module.startswith(f"{mod}.") for mod in _FORBIDDEN_MODULES)
        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", None)
            assert name not in _FORBIDDEN_CALLS
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Attribute):
            assert node.attr not in {"environ", "system", "popen"}


def test_module_consumes_only_public_authenticated_substrate() -> None:
    crypto_imports: dict[str, set[str]] = {}
    for node in ast.walk(_module_tree()):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core"):
            crypto_imports.setdefault(node.module, set()).update(alias.name for alias in node.names)
    assert set(crypto_imports) == {
        "crypto_core.validation.edge_artifact_core",
        "crypto_core.validation.edge_idea_intake_evidence",
        "crypto_core.validation.edge_leakage_bias_evidence",
        "crypto_core.validation.edge_source_packet_evidence",
        "crypto_core.validation.edge_strategy_spec_admission",
        "crypto_core.validation.historical_execution_economics_policy",
        "crypto_core.validation.historical_walk_forward_metrics",
    }
    for names in crypto_imports.values():
        assert not {name for name in names if name.startswith("_")}
    assert crypto_imports["crypto_core.validation.historical_execution_economics_policy"] == {
        "historical_execution_decimal_is_canonical"
    }


def test_no_pbo_stress_ef7_service_live_order_or_capital_surface() -> None:
    closure: set[str] = set()
    pending = {ef6_module.__name__}
    while pending:
        name = pending.pop()
        closure.add(name)
        source = Path(importlib.import_module(name).__file__).read_text(encoding="utf-8")  # type: ignore[arg-type]
        pending |= {
            node.module
            for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("crypto_core")
        } - closure
    offending = [
        name
        for name in closure
        if any(
            token in name for token in ("pbo", "stress", "paper_", "service", "venue", "execution.", "live", "order")
        )
    ]
    assert offending == []
    names = {field.name for field in fields(EdgeWalkForwardOosEvidence)}
    assert not [name for name in names if "ef7" in name or "admission_decision" in name]


def test_single_assembly_path_serves_builder_and_verifier() -> None:
    tree = _module_tree()
    constructor_calls = 0
    calls_by_function: dict[str, set[str]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)):
        names = [
            node.func.id
            for node in ast.walk(function)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        ]
        calls_by_function[function.name] = set(names)
        constructor_calls += names.count("EdgeWalkForwardOosEvidence")
    assert constructor_calls == 1
    assert "EdgeWalkForwardOosEvidence" in calls_by_function["_assemble_evidence"]
    assert "_assemble_evidence" in calls_by_function["build_edge_walk_forward_oos_evidence"]
    assert "_assemble_evidence" in calls_by_function["_reassemble_evidence"]


def test_real_p3_verifier_agrees_with_the_memo_for_the_happy_bundle() -> None:
    memo = _MEMOS[(ef6_module, "verify_historical_walk_forward_metrics")]
    assert memo.real(metrics("A1")) == memo(metrics("A1"))
    assert verify_historical_walk_forward_metrics is memo.real


def test_memo_keys_are_exact() -> None:
    assert _exact_key(EdgeEvidenceStatus.READY) != _exact_key("READY")
    assert _exact_key(True) != _exact_key(1)
    assert _exact_key((1,)) != _exact_key([1])
    assert _exact_key(replace(passed(), evidence_id="ef6-2")) != _exact_key(passed())
    assert _exact_key(replace(passed())) == _exact_key(passed())
    with pytest.raises(TypeError):
        _exact_key(0.5)
