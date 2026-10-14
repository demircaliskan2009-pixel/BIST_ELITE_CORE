"""Tests for the pre-paper validation evidence (EDGE_PRE_PAPER_VALIDATION_EVIDENCE_V1) and its shared test world.

World P (the authentic positive world). The degenerate world A of the EF-6 module cannot pass: its dense ``0, H, H``
rates make every entry-threshold probe trade identically, the conservative CSCV ties then count every split as overfit
and PBO = 12 870 / 12 870 = 1 (proven below on its real full-frame runs). World P is purpose-built and preregistered
BEFORE any performance is observed: one lookback-1 carry whose ``unit_size`` is the only SEARCHED parameter, with a
complete ±20% / 5% star grid of nine registered variants (0.80 ... 1.20). Its funding cycle repeats ``0, signal,
payoff`` with a payoff that varies deterministically (45 ... 65 bps), marks step by ±0.05% every ten days and books
track the marks with a 10 bps spread, 1000 units of depth and a 2 bps-per-participation-percent impact. Larger units
therefore pay strictly more impact on every fill, so the variants are distinct and strictly ordered by size in every
CSCV block, every closed trade return differs, and every EF-6 window holds 60 closed trades. Nothing is selected after
the fact: EF-5 seals the nine variants, EF-6 evaluates all of them, and the pre-paper gates admit the one variant with a
complete grid (the base) because the probes have no grid of their own.

Every approval, governance value, trial count, attestation and stress parameter below is a SYNTHETIC TEST VALUE
recorded as an explicit test fixture (``test-fixture:`` references); none is a production value and none is promoted
into production governance. Synthetic economics remain synthetic: world P proves code behavior, never an edge.

This module hosts world P for the EF-7, EF-8, RG-7 and RG-8 test modules, which import it under the basename pytest
collects it with, so the world is built once per process.

Cost control: every pure upstream function the evidence calls (the EF-6, policy, chain and dataset verifiers, the
accepted decision-run and economics builders, the stress simulation and the strict parsers) is memoized at the
evidence module's call site by an exact key of its whole input (exact types, every field; payload parsers by canonical
JSON). A memo only returns the result of an identical earlier real call; a tampered, foreign or changed input is always
a miss and is computed for real. The evidence module's own code is never memoized, and one slow test re-proves the
positive world with every memo disabled.
"""

from __future__ import annotations

import ast
import functools
import itertools
import json
from dataclasses import fields, replace
from fractions import Fraction
from pathlib import Path

import pytest

import crypto_core.validation.edge_pre_paper_validation_evidence as ev_module
import crypto_core.validation.edge_trial_count_chain as chain_module
import crypto_core.validation.historical_execution_economics as economics_module
from crypto_core.data.requirements import data_requirement_registry_digest
from crypto_core.validation.edge_artifact_core import (
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_sha256_text,
)
from crypto_core.validation.edge_leakage_bias_evidence import (
    EdgeInputVariant,
    EdgeLeakageBiasEvidence,
    EdgeParameterSearchBound,
    build_edge_leakage_bias_evidence,
    edge_leakage_bias_evidence_from_payload,
)
from crypto_core.validation.edge_pre_paper_validation_evidence import (
    EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS,
    EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST,
    EdgePboBand,
    EdgePrePaperCheckStatus,
    EdgePrePaperValidationEvidence,
    EdgePrePaperValidationEvidenceError,
    build_edge_pre_paper_validation_evidence,
    edge_cscv_pbo_split_matrix,
    edge_dsr_decision,
    edge_ln_bounds,
    edge_monte_carlo_seed,
    edge_monte_carlo_sign_flip_exceedances,
    edge_pre_paper_validation_evidence_digest,
    edge_pre_paper_validation_evidence_from_payload,
    edge_pre_paper_validation_evidence_payload_is_well_formed,
    edge_pre_paper_validation_evidence_to_dict,
    edge_pre_paper_validation_rule_set,
    verify_edge_pre_paper_validation_evidence,
)
from crypto_core.validation.edge_pre_paper_validation_policy import (
    EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST,
    EdgePrePaperApprovalKind,
    EdgePrePaperValidationApproval,
    EdgePrePaperValidationPolicy,
    build_edge_pre_paper_validation_policy,
)
from crypto_core.validation.edge_source_packet_evidence import edge_source_packet_evidence_from_payload
from crypto_core.validation.edge_trial_count_chain import (
    EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST,
    EdgeTrialCountApprovalKind,
    EdgeTrialCountChain,
    EdgeTrialCountCurrentnessAttestation,
    EdgeTrialCountGenesis,
    EdgeTrialCountGenesisApproval,
    build_edge_trial_count_chain,
    build_edge_trial_count_genesis,
)
from crypto_core.validation.edge_walk_forward_oos_evidence import (
    EdgeVariantMetricsInput,
    EdgeWalkForwardOosEvidence,
    build_edge_walk_forward_oos_evidence,
    edge_walk_forward_oos_evidence_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionTradeStatus,
    build_historical_execution_economics,
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
    historical_pit_dataset_from_payload,
)
from crypto_core.validation.historical_walk_forward_metrics import (
    historical_walk_forward_daily_endpoints,
    historical_walk_forward_equity_units,
)

try:  # the module object pytest collects (basename import), so the authentic worlds and their memos are built once
    import test_edge_walk_forward_oos_evidence as ef6t
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_edge_walk_forward_oos_evidence as ef6t

_PREFIX = "edge_pre_paper_validation_evidence"
_UNSET = object()
SLOW = pytest.mark.slow  # a memo-free re-proof of the positive world; see the module docstring
DAY, S0, INS = ef6t.DAY, ef6t.S0, ef6t.INS
d = ef6t.d
mt, polt, runt, prof, ef5t = ef6t.mt, ef6t.polt, ef6t.runt, ef6t.prof, ef6t.ef5t
HUMAN = EdgeTrialCountApprovalKind.HUMAN_GOVERNANCE
SYNTHETIC = EdgeTrialCountApprovalKind.TEST_ONLY_SYNTHETIC
EVIDENCE_ID = "pre-paper-1"
CORR = "corr-1"

# --- world P (see module docstring) --------------------------------------------------------------------------------------

FUNDING = 2 * DAY
MARK_STEP = 10 * DAY
HORIZON_DAYS = 640
STARTS = (0, 90, 180)  # the admission frame: IS [s, s+365), OOS [s+365, s+455); span [0, 635), CSCV frame [11, 635)
REVALIDATION_STARTS = (2, 92, 182)  # one funding cycle later: span [2, 637), CSCV frame [13, 637)
STEPS = tuple(range(-4, 5))
UNITS = tuple(d(Fraction(20 + step, 20)) for step in STEPS)  # 0.80 ... 1.20, the ±20% / 5% star grid of 1.00
BASE_UNIT = UNITS[4]
VARIANT_IDS = tuple(f"variant-u{100 + 5 * step:03d}" for step in STEPS)
BASE_VARIANT = VARIANT_IDS[4]


def _rate(k: int) -> str:
    """Funding cycle ``k``: 0 (exit), then a signal above the entry threshold, then a payoff of 45 to 65 bps."""

    if k % 3 == 0:
        return d(0)
    if k % 3 == 1:
        return d("0.003")
    return d(Fraction(45 + 5 * ((k // 3) % 5), 10_000))


def _mark_price(index: int) -> Fraction:
    return Fraction(100) * (1 + Fraction(5 * (((index * 7) % 5) - 2), 10_000))


def _book_values(time_ns: int) -> dict[str, str]:
    mid = _mark_price(max(0, (time_ns - S0 + 1_000) // MARK_STEP))
    return {
        "best_bid_price": d(mid * (1 - Fraction(5, 10_000))),
        "best_ask_price": d(mid * (1 + Fraction(5, 10_000))),
        "best_bid_quantity": d(1000),
        "best_ask_quantity": d(1000),
    }


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


@functools.cache
def _all_records() -> tuple[tuple, tuple, tuple]:
    count = HORIZON_DAYS * DAY // FUNDING + 2
    funding = tuple(
        build_historical_pit_record(
            series_id="funding-final",
            data_requirement_key="funding_rate",
            instrument=INS,
            sequence_id=k,
            event_time_ns=S0 + (k - 1) * FUNDING,
            available_at_ns=S0 + k * FUNDING + 10,
            finalized_at_ns=S0 + k * FUNDING + 10,
            revision_vintage_id=None,
            values=(HistoricalPitValue("funding_rate", _rate(k)),),
        )
        for k in range(count)
    )
    marks = tuple(
        _pit("mark", "mark_price", j, S0 + j * MARK_STEP - 1_000, {"mark_price": d(_mark_price(j))})
        for j in range(HORIZON_DAYS // 10 + 2)
    )
    books = tuple(
        _pit("book", "order_book", k, S0 + k * FUNDING + 500, _book_values(S0 + k * FUNDING + 500))
        for k in range(count)
    )
    return funding, marks, books


@functools.cache
def records_p(start_day: int, days: int) -> tuple:
    """The PIT slice one segment consumes (the EF-6 module's slicing rule, so each payload stays small)."""

    low, high = S0 + start_day * DAY, S0 + (start_day + days) * DAY
    funding, marks, books = _all_records()
    return (
        *(item for item in funding if low - 2 * FUNDING <= item.event_time_ns <= high + FUNDING),
        *(item for item in marks if low - 12 * DAY <= item.event_time_ns + 1_000 <= high + MARK_STEP),
        *(item for item in books if low - FUNDING <= item.event_time_ns - 500 <= high + FUNDING),
    )


def _dataset(dataset_id: str, items: tuple) -> HistoricalPitDataset:
    _, manifest, _, registry, _ = ef6t.world()
    return build_historical_pit_dataset(
        manifest,
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,
        expected_data_requirement_registry_digest=data_requirement_registry_digest(registry),
        dataset_id=dataset_id,
        correlation_id=CORR,
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=items,
    )


@functools.cache
def dataset_p(start_day: int, days: int) -> HistoricalPitDataset:
    return _dataset(f"dataset-p-{start_day}-{days}", records_p(start_day, days))


def _segments(starts: tuple[int, ...]) -> tuple[tuple[int, int], ...]:
    return tuple(segment for start in starts for segment in ((start, 365), (start + 365, 90)))


@functools.cache
def economics_policy_p():
    return polt.cited_policy(
        kind=HistoricalExecutionCitationKind.DEEP_RESEARCH_CITED,
        funding_interval_ns=FUNDING,
        max_mark_staleness_ns=11 * DAY,
        taker_fee_bps=d(5),
        impact_coefficient_bps_per_participation_pct=d(2),
    )


def params_p(unit: str = BASE_UNIT):
    return prof.params(n="1", unit=unit)


@functools.cache
def economics_p(start_day: int, days: int, unit: str = BASE_UNIT) -> HistoricalExecutionEconomicsResult:
    _, _, _, registry, binding = ef6t.world()
    run_id = f"run-p-{start_day}-{days}-{unit}"
    run = runt.decision_run(
        dataset_p(start_day, days),
        binding,
        instrument=INS,
        evaluation_start_ns=S0 + start_day * DAY,
        evaluation_end_ns=S0 + (start_day + days) * DAY,
        parameter_assignment=params_p(unit),
        run_id=run_id,
    )
    policy = economics_policy_p()
    approval = polt.approval_for(
        policy,
        strategy_spec_digest=run.strategy_spec_digest,
        data_requirement_registry_digest=data_requirement_registry_digest(registry),
        approval_kind=HistoricalExecutionApprovalKind.HUMAN_GOVERNANCE,
    )
    return build_historical_execution_economics(
        run,
        expected_run_digest=run.run_digest,
        economics_policy=policy,
        expected_economics_policy_digest=policy.policy_digest,
        economics_approval=approval,
        result_id=f"{run_id}-economics",
        correlation_id=CORR,
    )


@functools.cache
def metrics_p(unit: str, starts: tuple[int, ...] = STARTS):
    windows = tuple(
        mt.window(f"wf-{index + 1}", economics_p(start, 365, unit), economics_p(start + 365, 90, unit))
        for index, start in enumerate(starts)
    )
    return mt.build(windows, result_id=f"wf-p-{unit}-{starts[0]}")


def _bounds() -> tuple[EdgeParameterSearchBound, ...]:
    base = params_p()
    return (
        EdgeParameterSearchBound("entry_threshold", "fixed", (base[0].value,)),
        EdgeParameterSearchBound("exit_threshold", "fixed", (base[1].value,)),
        EdgeParameterSearchBound("final_funding_lookback_count", "fixed", (base[2].value,)),
        EdgeParameterSearchBound("unit_size", "searched", UNITS),
    )


@functools.cache
def ef5_p() -> EdgeLeakageBiasEvidence:
    """The sealed EF-5 preregistration of the nine star-grid variants (sealed before any economics exists)."""

    intake, _, admission, _, binding = ef6t.world()
    arguments = {
        "expected_predecessor_digest": admission.admission_digest,
        "expected_root_intake_digest": intake.intake_digest,
        "executable_binding": binding,
        "expected_executable_binding_digest": binding.binding_digest,
        "preregistration_id": "prereg-p",
        "correlation_id": CORR,
        "feature_ids": ("final_funding_mean",),
        "parameter_bounds": _bounds(),
        "variants": tuple(
            EdgeInputVariant(name, params_p(unit)) for name, unit in zip(VARIANT_IDS, UNITS, strict=True)
        ),
        "survivorship_claim_scope": "pinned_instrument_universe",
    }
    draft = build_edge_leakage_bias_evidence(admission, **arguments)
    return build_edge_leakage_bias_evidence(admission, **arguments, approval=ef5t.approval_for(draft))


@functools.cache
def ef6_p(starts: tuple[int, ...] = STARTS, evidence_id: str = "ef6-p") -> EdgeWalkForwardOosEvidence:
    """The governed EF-6 PASS over every registered variant of ``ef5_p`` (complete coverage)."""

    predecessor = ef5_p()
    arguments = {
        "expected_predecessor_digest": predecessor.leakage_bias_evidence_digest,
        "expected_root_intake_digest": ef6t.world()[0].intake_digest,
        "variant_metrics": tuple(
            EdgeVariantMetricsInput(metrics_p(unit, starts), metrics_p(unit, starts).result_digest) for unit in UNITS
        ),
        "evidence_id": evidence_id,
        "correlation_id": CORR,
    }
    draft = build_edge_walk_forward_oos_evidence(predecessor, **arguments)  # type: ignore[arg-type]
    return build_edge_walk_forward_oos_evidence(predecessor, **arguments, governance=ef6t.governance_for(draft))  # type: ignore[arg-type]


# --- governed pre-paper authorities (SYNTHETIC TEST VALUES) --------------------------------------------------------------


@functools.cache
def genesis(pre_genesis_trial_count: int = 3) -> EdgeTrialCountGenesis:
    return build_edge_trial_count_genesis(
        genesis_id="trial-genesis-1",
        pre_genesis_trial_count=pre_genesis_trial_count,
        pre_genesis_evidence_reference="test-fixture:pre-genesis-trial-count-attestation",
    )


def genesis_approval(record: EdgeTrialCountGenesis | None = None, **overrides: object) -> EdgeTrialCountGenesisApproval:
    record = genesis() if record is None else record
    values: dict[str, object] = {
        "approval_reference": "test-fixture:trial-genesis-approval",
        "approval_digest": "1" * 64,
        "approval_kind": HUMAN,
        "approved_genesis_digest": record.genesis_digest,
        "approved_rule_set_digest": EDGE_TRIAL_COUNT_CHAIN_RULE_SET_DIGEST,
    }
    values.update(overrides)
    return EdgeTrialCountGenesisApproval(**values)  # type: ignore[arg-type]


@functools.cache
def chain_for(
    preregistrations: tuple[EdgeLeakageBiasEvidence, ...], record: EdgeTrialCountGenesis | None = None
) -> EdgeTrialCountChain:
    record = genesis() if record is None else record
    return build_edge_trial_count_chain(
        chain_id="trial-chain-1",
        genesis=record,
        genesis_approval=genesis_approval(record),
        preregistrations=preregistrations,
        expected_preregistration_digests=tuple(item.leakage_bias_evidence_digest for item in preregistrations),
    )


# Exactly the PRDV4 limits where PRDV4 names one; the flash-crash depth, slippage and maintenance values are test-only.
POLICY_VALUES: dict[str, object] = {
    "policy_id": "pre-paper-policy-1",
    "policy_version": "1",
    "pbo_normal_max_exclusive": "0.200000000000000000",
    "pbo_capped_max_exclusive": "0.400000000000000000",
    "pbo_additional_oos_max_inclusive": "0.600000000000000000",
    "pbo_capped_allocation_fraction": "0.500000000000000000",
    "regime_allocation_fraction": "0.250000000000000000",
    "monte_carlo_p_value_max": "0.050000000000000000",
    "monte_carlo_min_closed_trade_count": 50,
    "sensitivity_min_retention_ratio": "0.500000000000000000",
    "high_volatility_slippage_multiplier": "2.000000000000000000",
    "low_liquidity_depth_multiplier": "0.200000000000000000",
    "low_liquidity_slippage_multiplier": "3.000000000000000000",
    "flash_crash_gap_fraction": "0.100000000000000000",
    "flash_crash_recovery_ns": 300_000_000_000,
    "flash_crash_depth_multiplier": "0.200000000000000000",
    "flash_crash_slippage_multiplier": "3.000000000000000000",
    "flash_crash_maintenance_margin_fraction": "0.005000000000000000",
}


def policy_approval(
    draft: EdgePrePaperValidationPolicy, kind: EdgePrePaperApprovalKind = EdgePrePaperApprovalKind.HUMAN_GOVERNANCE
) -> EdgePrePaperValidationApproval:
    return EdgePrePaperValidationApproval(
        approval_reference="test-fixture:pre-paper-policy-approval",
        approval_digest="2" * 64,
        approval_kind=kind,
        approved_policy_values_digest=draft.policy_values_digest,
        approved_rule_set_digest=EDGE_PRE_PAPER_VALIDATION_POLICY_RULE_SET_DIGEST,
    )


@functools.cache
def _policy(items: tuple[tuple[str, object], ...], approved: bool) -> EdgePrePaperValidationPolicy:
    values = dict(items)
    draft = build_edge_pre_paper_validation_policy(**values)  # type: ignore[arg-type]
    if not approved:
        return draft
    return build_edge_pre_paper_validation_policy(**values, approval=policy_approval(draft))  # type: ignore[arg-type]


def policy(*, approved: bool = True, **overrides: object) -> EdgePrePaperValidationPolicy:
    values = {**POLICY_VALUES, "approved_trial_chain_genesis_digest": genesis().genesis_digest, **overrides}
    return _policy(tuple(sorted(values.items())), approved)


def attestation_for(
    chain: EdgeTrialCountChain,
    *,
    preregistration_digest: str,
    evidence_id: str = EVIDENCE_ID,
    **overrides: object,
) -> EdgeTrialCountCurrentnessAttestation:
    values: dict[str, object] = {
        "attestation_reference": "test-fixture:trial-count-currentness-attestation",
        "attestation_digest": "3" * 64,
        "approval_kind": HUMAN,
        "attested_chain_id": chain.chain_id,
        "attested_chain_digest": chain.chain_digest,
        "attested_head_digest": chain.head_digest,
        "attested_cumulative_trial_count": chain.head_cumulative_trial_count,
        "attested_evaluation_id": evidence_id,
        "attested_correlation_id": CORR,
        "attested_preregistration_digest": preregistration_digest,
        "attested_at_ns": S0 + 640 * DAY,
        "no_off_chain_trial_attested": True,
    }
    values.update(overrides)
    return EdgeTrialCountCurrentnessAttestation(**values)  # type: ignore[arg-type]


def _ef5_of(ef6: EdgeWalkForwardOosEvidence) -> EdgeLeakageBiasEvidence:
    return edge_leakage_bias_evidence_from_payload(edge_authority_binding_snapshot(ef6.predecessor_binding))


@functools.cache
def frame_dataset_for(ef6: EdgeWalkForwardOosEvidence) -> HistoricalPitDataset:
    """The union of an EF-6's segment datasets (read from its first bundle), or world A's first slice without bundles.

    The dataset id is derived from the union itself, so EF-6s over the same segments share one frame dataset (and the
    accepted full-frame runs over it).
    """

    if not ef6.variant_metrics_bindings:
        return ef6t.dataset("main", "dataset-1", 0, 365)
    union: dict[str, object] = {}
    manifest = registry_digest = None
    for window in edge_authority_binding_snapshot(ef6.variant_metrics_bindings[0])["window_bindings"]:
        for side in ("in_sample_binding", "out_of_sample_binding"):
            run = window[side]["snapshot"]["run_binding"]["snapshot"]
            segment = historical_pit_dataset_from_payload(run["dataset_binding"]["snapshot"])
            union.update((item.record_digest, item) for item in segment.records)
            manifest = edge_source_packet_evidence_from_payload(
                edge_authority_binding_snapshot(segment.source_manifest_binding)
            )
            registry_digest = segment.expected_data_requirement_registry_digest
    return build_historical_pit_dataset(
        manifest,  # type: ignore[arg-type]
        expected_source_manifest_digest=manifest.source_packet_evidence_digest,  # type: ignore[union-attr]
        expected_data_requirement_registry_digest=registry_digest,  # type: ignore[arg-type]
        dataset_id=f"dataset-frame-{edge_sha256_text(edge_canonical_json(sorted(union)))[:16]}",
        correlation_id=ef6.correlation_id,
        source_reference="archive:history",
        rights_status="own_research",
        rights_reference="license-1",
        records=tuple(union.values()),
    )


def evidence_arguments(
    ef6: EdgeWalkForwardOosEvidence,
    *,
    attestation: object = _UNSET,
    chain: EdgeTrialCountChain | None = None,
    **overrides: object,
) -> dict[str, object]:
    chain = chain_for((_ef5_of(ef6),)) if chain is None else chain
    selected_policy = overrides.pop("policy", None) or policy()
    dataset = overrides.pop("frame_dataset", None) or frame_dataset_for(ef6)
    evidence_id = overrides.get("evidence_id", EVIDENCE_ID)
    arguments: dict[str, object] = {
        "expected_walk_forward_oos_evidence_digest": ef6.walk_forward_oos_evidence_digest,
        "expected_root_intake_digest": ef6t.world()[0].intake_digest,
        "frame_dataset": dataset,
        "expected_frame_dataset_digest": dataset.dataset_digest,  # type: ignore[attr-defined]
        "policy": selected_policy,
        "expected_policy_digest": selected_policy.policy_digest,  # type: ignore[attr-defined]
        "trial_chain": chain,
        "expected_trial_chain_digest": chain.chain_digest,
        "currentness_attestation": attestation_for(
            chain,
            preregistration_digest=ef6.predecessor_digest,
            evidence_id=evidence_id,  # type: ignore[arg-type]
        )
        if attestation is _UNSET
        else attestation,
        "evidence_id": EVIDENCE_ID,
        "correlation_id": CORR,
    }
    arguments.update(overrides)
    return arguments


def build(ef6: EdgeWalkForwardOosEvidence, **overrides: object) -> EdgePrePaperValidationEvidence:
    return build_edge_pre_paper_validation_evidence(ef6, **evidence_arguments(ef6, **overrides))  # type: ignore[arg-type]


@functools.cache
def evidence_for(ef6: EdgeWalkForwardOosEvidence, evidence_id: str = EVIDENCE_ID) -> EdgePrePaperValidationEvidence:
    """The default governed evidence of any EF-6 (cached): its own chain, the default policy and an exact attestation."""

    return build(ef6, evidence_id=evidence_id)


@functools.cache
def passed() -> EdgePrePaperValidationEvidence:
    """The authentic pre-paper PASS of world P."""

    return evidence_for(ef6_p())


@functools.cache
def draft() -> EdgePrePaperValidationEvidence:
    """World P before the currentness attestation: every statistic computed, NEEDS_GOVERNANCE_APPROVAL."""

    return build(ef6_p(), attestation=None)


# --- memoized pure upstream functions (see module docstring) -------------------------------------------------------------


class _CallMemo:
    """Exact memo of one pure function of positional and keyword arguments; no exact key means a direct call."""

    def __init__(self, real) -> None:
        self.real = real
        self.cache: dict[object, object] = {}

    def __call__(self, *args: object, **kwargs: object) -> object:
        if not ef6t._MEMO_ENABLED[0]:
            return self.real(*args, **kwargs)
        try:
            key = (
                tuple(ef6t._exact_key(item) for item in args),
                tuple((name, ef6t._exact_key(value)) for name, value in sorted(kwargs.items())),
            )
        except Exception:  # noqa: BLE001 - no exact key: evaluate directly
            return self.real(*args, **kwargs)
        if key not in self.cache:
            self.cache[key] = self.real(*args, **kwargs)  # a raising call is never cached
        return self.cache[key]


_EXACT_TARGETS = (
    (ev_module, "verify_edge_walk_forward_oos_evidence"),
    (ev_module, "verify_edge_pre_paper_validation_policy"),
    (ev_module, "verify_edge_trial_count_chain"),
    (ev_module, "verify_historical_pit_dataset"),
    (economics_module, "verify_historical_execution_economics"),
    (chain_module, "verify_edge_leakage_bias_evidence"),
)
_CALL_TARGETS = (
    (ev_module, "build_historical_decision_run"),
    (ev_module, "build_historical_execution_economics"),
    (ev_module, "simulate_historical_execution_stress"),
)
_PAYLOAD_TARGETS = (
    (ev_module, "historical_pit_dataset_from_payload"),
    (ev_module, "edge_pre_paper_validation_policy_from_payload"),
    (ev_module, "edge_trial_count_chain_from_payload"),
    (ev_module, "edge_leakage_bias_evidence_from_payload"),
    (chain_module, "edge_leakage_bias_evidence_from_payload"),
)
_PRE_MEMOS: dict[tuple[object, str], object] = {
    **{(module, name): ef6t._Memoized(getattr(module, name), ef6t._exact_key) for module, name in _EXACT_TARGETS},
    **{(module, name): _CallMemo(getattr(module, name)) for module, name in _CALL_TARGETS},
    **{(module, name): ef6t._Memoized(getattr(module, name), edge_canonical_json) for module, name in _PAYLOAD_TARGETS},
}


def apply_memos(patch: pytest.MonkeyPatch) -> None:
    """Install the EF-6 module's memos and this module's memos (shared with the EF-7, EF-8, RG-7 and RG-8 tests)."""

    for (module, name), memo in ef6t._MEMOS.items():
        patch.setattr(module, name, memo)
    for (module, name), memo in _PRE_MEMOS.items():
        patch.setattr(module, name, memo)


@pytest.fixture(autouse=True, scope="module")
def _memoized_verification():
    with pytest.MonkeyPatch.context() as patch:
        apply_memos(patch)
        yield


# --- assertions ------------------------------------------------------------------------------------------------------------


def _code(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _reseal(evidence: EdgePrePaperValidationEvidence, **changes: object) -> EdgePrePaperValidationEvidence:
    changed = replace(evidence, **changes)
    return replace(changed, pre_paper_validation_evidence_digest=edge_pre_paper_validation_evidence_digest(changed))


def _verify(evidence: object, ef6: object | None = None) -> EdgeEvidenceVerification:
    return verify_edge_pre_paper_validation_evidence(
        evidence, walk_forward_oos_evidence=ef6_p() if ef6 is None else ef6
    )


def _assert_shape(evidence: EdgePrePaperValidationEvidence) -> None:
    assert evidence.pre_paper_validation_evidence_digest == edge_pre_paper_validation_evidence_digest(evidence)
    ready = evidence.status is EdgeEvidenceStatus.READY
    assert evidence.advances is (ready and evidence.gate_verdict is EdgeGateVerdict.PASS)
    assert evidence.pre_paper_validation_passed is evidence.advances
    assert {name: getattr(evidence, name) for name, _ in EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS} == dict(
        EDGE_PRE_PAPER_VALIDATION_NON_CLAIM_FLAGS
    )
    assert (evidence.admission_scope, evidence.regime_conditional_pbo_status) == ("LIMITED_S1_PAPER_V1", "UNPROVEN")
    assert evidence.rule_set_digest == EDGE_PRE_PAPER_VALIDATION_RULE_SET_DIGEST
    assert evidence.admitted_variant_count == len(evidence.admitted_assignment_digests)
    if evidence.advances:
        assert evidence.admitted_assignment_digests and evidence.admission_cap_fraction is not None
    else:
        assert evidence.admitted_assignment_digests == () and evidence.admission_cap_fraction is None
    if not ready:
        assert evidence.gate_verdict is EdgeGateVerdict.NOT_EVALUATED
        assert evidence.integrity_reason_codes and evidence.verdict_reason_codes == ()


def _assert_receipt(evidence: EdgePrePaperValidationEvidence, ef6: object | None = None) -> None:
    _assert_shape(evidence)
    verification = _verify(evidence, ef6)
    assert verification.intact is True, verification.reason_codes
    assert verification.recomputed_digest == evidence.pre_paper_validation_evidence_digest
    payload = json.loads(verification.canonical_json)
    assert edge_pre_paper_validation_evidence_payload_is_well_formed(payload) is True
    assert edge_pre_paper_validation_evidence_from_payload(payload) == evidence


def _frame_paths(starts: tuple[int, ...] = STARTS) -> list[list[int]]:
    """The exact daily endpoint equity units of every registered variant's full-frame run (independent of the module)."""

    frame_end = S0 + (starts[-1] + 455) * DAY
    frame_start = frame_end - 624 * DAY
    dataset = frame_dataset_for(ef6_p(starts))
    binding = ef6t.world()[4]
    paths = []
    for name in ef5_p().registered_variants:
        run = ev_module.build_historical_decision_run(
            dataset,
            binding,
            expected_dataset_digest=dataset.dataset_digest,
            expected_executable_binding_digest=binding.binding_digest,
            run_id=f"pre-paper-frame-run:{frame_start}:{frame_end}:{name.variant_id}",
            correlation_id=CORR,
            parameter_assignment=name.parameter_assignment,
            instrument=INS,
            evaluation_start_ns=frame_start,
            evaluation_end_ns=frame_end,
            parameter_approval=ef6t.bind.parameter_approval_for(binding, name.parameter_assignment),
        )
        result = ev_module.build_historical_execution_economics(
            run,
            expected_run_digest=run.run_digest,
            economics_policy=economics_policy_p(),
            expected_economics_policy_digest=economics_policy_p().policy_digest,
            economics_approval=economics_p(0, 365).economics_approval,
            result_id=f"pre-paper-frame-economics:{frame_start}:{frame_end}:{name.variant_id}",
            correlation_id=CORR,
        )
        endpoints, _ = historical_walk_forward_daily_endpoints(result, day_ns=DAY)
        paths.append([historical_walk_forward_equity_units(item.equity) for item in endpoints])  # type: ignore[union-attr]
    return paths


# --- A. the authentic positive world --------------------------------------------------------------------------------------


def test_world_p_is_preregistered_complete_and_passes_ef6_with_every_variant_surviving() -> None:
    ef5, ef6 = ef5_p(), ef6_p()
    assert (ef5.status, ef5.gate_verdict, ef5.preregistration_sealed) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert tuple(item.variant_id for item in ef5.registered_variants) == VARIANT_IDS
    assert ef5.multiple_testing_count == 9
    assert (ef6.status, ef6.gate_verdict, ef6.surviving_variant_count) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        9,
    )
    assert ef6.evaluated_variant_count == ef6.registered_variant_count == 9
    # Every in-sample window holds at least the PRDV4 floor of 50 closed trades for every variant.
    for unit in UNITS:
        for start in STARTS:
            trades = economics_p(start, 365, unit).trades
            assert sum(1 for item in trades if item.status is HistoricalExecutionTradeStatus.CLOSED) >= 50


def test_authentic_positive_world_passes_every_pre_paper_gate_and_admits_only_the_complete_grid_base() -> None:
    evidence = passed()
    _assert_receipt(evidence)
    assert (evidence.status, evidence.gate_verdict, evidence.advances) == (
        EdgeEvidenceStatus.READY,
        EdgeGateVerdict.PASS,
        True,
    )
    assert (evidence.integrity_reason_codes, evidence.verdict_reason_codes) == ((), ())
    assert evidence.walk_forward_oos_evidence_digest == ef6_p().walk_forward_oos_evidence_digest
    assert evidence.preregistration_digest == ef5_p().leakage_bias_evidence_digest
    assert evidence.registered_variant_ids == VARIANT_IDS and evidence.registered_variant_count == 9
    assert (evidence.frame_start_ns, evidence.frame_end_ns) == (S0 + 11 * DAY, S0 + 635 * DAY)
    assert (evidence.frame_day_count, evidence.cscv_block_count, evidence.cscv_block_days) == (624, 16, 39)
    assert tuple(run.variant_id for run in evidence.frame_runs) == VARIANT_IDS
    assert all(run.closed_trade_count >= 100 and run.daily_return_count == 624 for run in evidence.frame_runs)
    assert (evidence.cscv_split_count, evidence.cscv_overfit_split_count) == (12_870, 0)
    assert (evidence.pbo, evidence.pbo_band) == ("0.000000000000000000", EdgePboBand.NORMAL)
    assert evidence.dsr_status is EdgePrePaperCheckStatus.PASSED
    assert evidence.dsr_cumulative_trial_count == 3 + 9  # the attested pre-genesis count E1 plus this EF-5
    assert evidence.dsr_max_variant_ids == (VARIANT_IDS[0],)  # the smallest unit pays the least impact
    survivors = {item.variant_id: item for item in evidence.survivors}
    assert set(survivors) == set(VARIANT_IDS)
    base = survivors[BASE_VARIANT]
    assert (base.sensitivity_status, base.monte_carlo_status, base.stress_status, base.eligible) == (
        EdgePrePaperCheckStatus.PASSED,
        EdgePrePaperCheckStatus.PASSED,
        EdgePrePaperCheckStatus.PASSED,
        True,
    )
    assert evidence.admitted_assignment_digests == (base.parameter_assignment_digest,)
    for name in VARIANT_IDS:
        if name != BASE_VARIANT:
            assert survivors[name].eligible is False
            assert survivors[name].sensitivity_status is EdgePrePaperCheckStatus.NOT_COMPUTABLE
            assert any("sensitivity_probe_unregistered" in code for code in survivors[name].reason_codes)
    # The cap is the stricter of the normal PBO band cap (1) and the LIMITED_S1_PAPER_V1 regime cap (1/4).
    assert (evidence.pbo_cap_fraction, evidence.regime_cap_fraction, evidence.admission_cap_fraction) == (
        "1.000000000000000000",
        "0.250000000000000000",
        "0.250000000000000000",
    )
    assert evidence.synthetic_test_approval_used is False
    assert (evidence.pbo_passed, evidence.stress_passed, evidence.full_prdv4_compliance_claimed) == (False,) * 3


def test_evidence_is_deterministic_and_byte_identical_on_rebuild() -> None:
    rebuilt = build(ef6_p())
    assert edge_pre_paper_validation_evidence_to_dict(rebuilt) == edge_pre_paper_validation_evidence_to_dict(passed())


def test_missing_currentness_attestation_computes_everything_but_needs_governance() -> None:
    evidence = draft()
    _assert_receipt(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.verdict_reason_codes == ("edge_trial_count_chain:currentness_attestation_missing",)
    assert (evidence.pbo, evidence.dsr_status) == (passed().pbo, EdgePrePaperCheckStatus.PASSED)
    assert evidence.survivors == passed().survivors
    assert (evidence.admitted_assignment_digests, evidence.admission_cap_fraction) == ((), None)


# --- B. the exact CSCV/PBO kernel ------------------------------------------------------------------------------------------


def _path(returns: list[Fraction], start: int = 10**120) -> list[int]:
    """Equity units of a path with the given exact daily returns (each step representable at the unit scale)."""

    units = [start]
    for item in returns:
        value = Fraction(units[-1]) * (1 + item)
        assert value.denominator == 1
        units.append(value.numerator)
    return units


def _oracle_key(path: list[int], blocks: tuple[int, ...], block_days: int) -> tuple[int, Fraction]:
    """Independent exact Sharpe ordering key of a half: (sign of the sum, mean^2 / sample variance)."""

    returns = [
        Fraction(path[day + 1], path[day]) - 1
        for block in blocks
        for day in range(block * block_days, (block + 1) * block_days)
    ]
    count = len(returns)
    mean = sum(returns) / count
    variance = sum((item - mean) ** 2 for item in returns) / (count - 1)
    sign = (mean > 0) - (mean < 0)
    return sign, (mean * mean / variance) if variance else Fraction(0)


def _oracle_split(paths: list[list[int]], block_count: int, subset: tuple[int, ...]) -> tuple[int, int, bool]:
    block_days = (len(paths[0]) - 1) // block_count
    complement = tuple(block for block in range(block_count) if block not in subset)

    def order(key: tuple[int, Fraction]) -> tuple[int, Fraction]:
        return key[0], key[1] if key[0] >= 0 else -key[1]

    in_keys = [order(_oracle_key(path, subset, block_days)) for path in paths]
    out_keys = [order(_oracle_key(path, complement, block_days)) for path in paths]
    best = max(in_keys)
    stars = [index for index, key in enumerate(in_keys) if key == best]
    worst = max(
        1 + sum(1 for other in range(len(paths)) if other != theta and out_keys[other] >= out_keys[theta])
        for theta in stars
    )
    return sum(1 << theta for theta in stars), worst, 2 * worst > len(paths)


def test_the_split_set_is_every_lexicographic_half_and_its_complement() -> None:
    subsets = list(itertools.combinations(range(16), 8))
    assert len(subsets) == 12_870 and subsets[0] == tuple(range(8)) and subsets[-1] == tuple(range(8, 16))
    masks = {sum(1 << block for block in subset) for subset in subsets}
    assert {0xFFFF ^ mask for mask in masks} == masks


def test_hand_computed_pbo_on_a_constructed_four_block_matrix() -> None:
    # Variant 0 wins blocks 0-1 and loses 2-3; variant 1 the reverse; variant 2 is flat with noise in every block.
    up, down = Fraction(1, 100), Fraction(-1, 100)
    blocks = {
        0: [[up, down, up], [up, up, down], [down, down, up], [down, up, down]],
        1: [[down, down, up], [down, up, down], [up, down, up], [up, up, down]],
        2: [[up, down, down], [down, up, up], [up, down, down], [down, up, up]],
    }
    paths = [_path([item for block in blocks[variant] for item in block]) for variant in range(3)]
    result = edge_cscv_pbo_split_matrix(paths, block_count=4)
    subsets = list(itertools.combinations(range(4), 2))
    expected = [_oracle_split(paths, 4, subset) for subset in subsets]
    assert (result.split_count, result.block_days) == (6, 3)
    assert list(zip(result.is_best_masks, result.worst_oos_ranks, result.overfit, strict=True)) == expected
    assert result.overfit_split_count == sum(item[2] for item in expected)


def test_identical_variants_tie_in_sample_and_the_worst_oos_rank_counts_the_tie() -> None:
    noisy = [Fraction((-1) ** day * (day % 3 + 1), 1000) for day in range(32)]
    path = _path(noisy)
    result = edge_cscv_pbo_split_matrix([path, path], block_count=16)
    assert result.is_best_masks == (0b11,) * 12_870
    assert result.worst_oos_ranks == (2,) * 12_870
    assert result.overfit_split_count == 12_870  # 2 x 2 > 2: PBO = 1


def test_rank_threshold_is_twice_rank_greater_than_n_for_odd_and_even_n() -> None:
    noisy = [Fraction((-1) ** day * (day % 3 + 1), 1000) for day in range(32)]
    for count in (3, 4):
        result = edge_cscv_pbo_split_matrix([_path(noisy)] * count, block_count=16)
        assert set(result.worst_oos_ranks) == {count}
        assert result.overfit_split_count == 12_870
    better = _path([item + Fraction(1, 1000) for item in noisy])
    result = edge_cscv_pbo_split_matrix([better, _path(noisy), _path(noisy)], block_count=16)
    assert set(result.is_best_masks) == {0b001} and set(result.worst_oos_ranks) == {1}
    assert result.overfit_split_count == 0


def test_zero_variance_halves_are_exact_zero_or_undefined() -> None:
    flat = [10**22] * 33
    noisy = _path([Fraction((-1) ** day * (day % 3 + 1), 1000) for day in range(32)])
    zero = edge_cscv_pbo_split_matrix([flat, noisy], block_count=16)
    assert zero.undefined_variant_indexes == () and zero.split_count == 12_870
    constant = _path([Fraction(1, 1000)] * 32)
    undefined = edge_cscv_pbo_split_matrix([constant, noisy], block_count=16)
    assert undefined.undefined_variant_indexes == (0,) and undefined.overfit_split_count == 0


@pytest.mark.parametrize(
    ("paths", "block_count", "code"),
    [
        ([[1, 2, 3]], 2, "cscv_variant_count_insufficient"),
        ([[1, 2, 3], [1, 2]], 2, "cscv_paths_not_one_equal_block_frame"),
        ([[1, 2, 3, 4], [1, 2, 3, 4]], 2, "cscv_paths_not_one_equal_block_frame"),
        ([[1, 0, 3], [1, 2, 3]], 2, "cscv_equity_nonpositive"),
        ([[1, 2, 3], [1, 2, 3]], 3, "cscv_block_count_invalid"),
        ([[1, 2, 3], [1, 2, 3]], True, "cscv_block_count_invalid"),
    ],
)
def test_malformed_cscv_input_is_refused(paths, block_count, code: str) -> None:
    with pytest.raises(EdgePrePaperValidationEvidenceError, match=code):
        edge_cscv_pbo_split_matrix(paths, block_count=block_count)


def test_world_p_split_matrix_agrees_with_an_independent_exact_oracle() -> None:
    evidence = passed()
    paths = _frame_paths()
    masks = [int(item, 16) for item in evidence.split_is_best_masks.split(",")]
    ranks = [int(item) for item in evidence.split_worst_oos_ranks.split(",")]
    bits = evidence.split_overfit_bits
    assert len(masks) == len(ranks) == len(bits) == 12_870
    subsets = list(itertools.combinations(range(16), 8))
    for index in (0, 1, 6_435, 12_869):
        assert (masks[index], ranks[index], bits[index] == "1") == _oracle_split(paths, 16, subsets[index]), index
    assert set(masks) == {0b1} and set(ranks) == {1} and set(bits) == {"0"}


def test_old_degenerate_world_a_gives_pbo_one_on_its_real_full_frame_runs() -> None:
    """World A's nine entry-threshold probes trade identically: every split is a tie and every split is overfit."""

    frame_start, frame_end = S0 + 11 * DAY, S0 + 635 * DAY
    union = {
        item.record_digest: item for start, days in _segments(STARTS) for item in ef6t.records("dense", start, days)
    }
    dataset = _dataset("dataset-a-frame", tuple(union.values()))
    _, _, _, registry, binding = ef6t.world()
    paths = []
    for step in STEPS:
        params = prof.params(n="1", entry=d(Fraction(20 + step, 20) * Fraction(1, 10_000)))
        run = runt.decision_run(
            dataset,
            binding,
            instrument=INS,
            evaluation_start_ns=frame_start,
            evaluation_end_ns=frame_end,
            parameter_assignment=params,
            run_id=f"run-a-frame-{step}",
        )
        policy_a = ef6t.economics_policy()
        result = build_historical_execution_economics(
            run,
            expected_run_digest=run.run_digest,
            economics_policy=policy_a,
            expected_economics_policy_digest=policy_a.policy_digest,
            economics_approval=ef6t.economics(0, 365, ef6t.PA).economics_approval,
            result_id=f"run-a-frame-{step}-economics",
            correlation_id=CORR,
        )
        endpoints, _ = historical_walk_forward_daily_endpoints(result, day_ns=DAY)
        paths.append([historical_walk_forward_equity_units(item.equity) for item in endpoints])  # type: ignore[union-attr]
    assert all(path == paths[0] for path in paths)
    result = edge_cscv_pbo_split_matrix(paths)
    assert (result.overfit_split_count, result.split_count) == (12_870, 12_870)
    assert set(result.is_best_masks) == {(1 << 9) - 1} and set(result.worst_oos_ranks) == {9}


# --- C. DSR -----------------------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "digits"),
    [
        (2, "0.693147180559945309417232121458176568"),
        (3, "1.098612288668109691395245236922525704"),
        (10, "2.302585092994045684017991454684364207"),
        (24, "3.178053830347945619646941601297055408"),
    ],
)
def test_certified_ln_bounds_bracket_the_true_value(value: int, digits: str) -> None:
    low, high = edge_ln_bounds(value, 64)
    reference = Fraction(digits)
    assert low <= reference + Fraction(1, 10**36) and reference - Fraction(1, 10**36) <= high
    assert high - low < Fraction(1, 10**50)


def test_dsr_decision_is_exact_on_both_sides_of_the_threshold() -> None:
    low, high = edge_ln_bounds(24, 64)
    passes, threshold_low, threshold_high = edge_dsr_decision(2 * high + Fraction(1, 10**40), 12)
    assert passes is True and threshold_low <= threshold_high
    fails, _, _ = edge_dsr_decision(2 * low - Fraction(1, 10**40), 12)
    assert fails is False
    assert edge_dsr_decision(Fraction(0), 1)[0] is False  # 2 ln 2 > 0
    assert edge_ln_bounds(1, 8) == (Fraction(0), Fraction(0))
    with pytest.raises(EdgePrePaperValidationEvidenceError, match="ln_bounds_input_invalid"):
        edge_ln_bounds(0, 8)


def test_dsr_fails_when_the_attested_cumulative_trial_count_is_large_enough() -> None:
    record = genesis(10**15)
    chain = chain_for((ef5_p(),), record)
    evidence = build(ef6_p(), chain=chain, policy=policy(approved_trial_chain_genesis_digest=record.genesis_digest))
    _assert_receipt(evidence)
    assert evidence.dsr_status is EdgePrePaperCheckStatus.FAILED
    assert evidence.verdict_reason_codes == (_code("dsr_negative_after_all_trials"),)
    assert evidence.dsr_cumulative_trial_count == 10**15 + 9
    assert evidence.survivors == () and evidence.admitted_assignment_digests == ()
    assert Fraction(evidence.dsr_z_squared_threshold_lower) > Fraction(passed().dsr_max_t_statistic) ** 2  # type: ignore[arg-type]


# --- D. Monte Carlo sign flip -----------------------------------------------------------------------------------------------


def _oracle_exceedances(returns: list[Fraction], seed: bytes, samples: int) -> int:
    stream = b"".join(
        __import__("hashlib").sha256(seed + index.to_bytes(8, "big")).digest()
        for index in range((samples * len(returns) + 255) // 256)
    )
    bits = "".join(format(byte, "08b") for byte in stream)
    observed = sum(returns)
    count = 0
    for sample in range(samples):
        window = bits[sample * len(returns) : (sample + 1) * len(returns)]
        total = sum(abs(item) if bit == "1" else -abs(item) for item, bit in zip(returns, window, strict=True))
        count += total >= observed
    return count


def test_sign_flip_exceedances_match_an_independent_bitwise_oracle() -> None:
    seed = edge_monte_carlo_seed("a" * 64, "b" * 64)
    for returns in (
        [Fraction(1, 3), Fraction(-1, 7), Fraction(2, 9)],
        [Fraction(item - 5, 11) for item in range(13)],
        [Fraction(1, 10)] * 9 + [Fraction(-1, 10)],
    ):
        assert edge_monte_carlo_sign_flip_exceedances(returns, seed, sample_count=400) == _oracle_exceedances(
            returns, seed, 400
        )


def test_monte_carlo_seed_is_digest_derived_and_changes_only_with_its_inputs() -> None:
    seed = edge_monte_carlo_seed("a" * 64, "b" * 64)
    assert seed == edge_monte_carlo_seed("a" * 64, "b" * 64) and len(seed) == 32
    assert seed != edge_monte_carlo_seed("c" * 64, "b" * 64) != edge_monte_carlo_seed("a" * 64, "c" * 64)


def test_a_literal_trade_order_shuffle_never_changes_the_sharpe_so_it_cannot_be_the_null() -> None:
    returns = [Fraction(item - 5, 11) for item in range(13)]
    shuffled = returns[::-1]
    mean = sum(returns) / len(returns)
    assert sum(shuffled) / len(shuffled) == mean
    assert sum((item - mean) ** 2 for item in shuffled) == sum((item - mean) ** 2 for item in returns)


def test_world_p_monte_carlo_is_exactly_significant_and_ties_count_against_the_candidate() -> None:
    base = {item.variant_id: item for item in passed().survivors}[BASE_VARIANT]
    assert base.monte_carlo_closed_trade_count >= 100
    assert (base.monte_carlo_exceedance_count, base.monte_carlo_p_value) == (0, "0.000000000000000000")
    assert (
        base.monte_carlo_seed
        == edge_monte_carlo_seed(ef5_p().leakage_bias_evidence_digest, base.parameter_assignment_digest).hex()
    )
    # Every sign pattern that reproduces the observed sum counts: with one zero return both of its signs tie.
    assert edge_monte_carlo_sign_flip_exceedances([Fraction(0), Fraction(1)], b"\x00" * 32, sample_count=2_000) > 0


def test_monte_carlo_trade_floor_makes_the_survivor_not_computable_and_nothing_admitted() -> None:
    evidence = build(ef6_p(), policy=policy(monte_carlo_min_closed_trade_count=10_000))
    _assert_receipt(evidence)
    base = {item.variant_id: item for item in evidence.survivors}[BASE_VARIANT]
    assert base.monte_carlo_status is EdgePrePaperCheckStatus.NOT_COMPUTABLE
    assert base.stress_status is EdgePrePaperCheckStatus.NOT_EVALUATED and base.eligible is False
    assert evidence.verdict_reason_codes == (_code("no_survivor_passes_every_pre_paper_gate"),)


# --- E. parameter sensitivity -------------------------------------------------------------------------------------------------


def test_the_sensitivity_heatmap_is_the_complete_registered_star_grid_of_the_base() -> None:
    base = {item.variant_id: item for item in passed().survivors}[BASE_VARIANT]
    probes = base.sensitivity_probes
    assert [item.step_percent for item in probes] == [-20, -15, -10, -5, 5, 10, 15, 20]
    assert [item.probe_value for item in probes] == [unit for unit in UNITS if unit != BASE_UNIT]
    assert [item.probe_variant_id for item in probes] == [name for name in VARIANT_IDS if name != BASE_VARIANT]
    assert [item.within_fragility_band for item in probes] == [False, False, True, True, True, True, False, False]
    assert all(item.retention_holds for item in probes)
    sharpes = [Fraction(item.annualized_sharpe) for item in probes]  # type: ignore[arg-type]
    assert sharpes == sorted(sharpes, reverse=True)  # strictly decreasing in size: more impact per unit


def test_a_strict_retention_floor_makes_the_base_fragile_and_nothing_admitted() -> None:
    evidence = build(ef6_p(), policy=policy(sensitivity_min_retention_ratio="1.000000000000000000"))
    _assert_receipt(evidence)
    base = {item.variant_id: item for item in evidence.survivors}[BASE_VARIANT]
    assert base.sensitivity_status is EdgePrePaperCheckStatus.FAILED
    assert set(base.reason_codes) == {
        _code("sensitivity_fragile:unit_size:5"),
        _code("sensitivity_fragile:unit_size:10"),
    }
    assert base.monte_carlo_status is EdgePrePaperCheckStatus.NOT_EVALUATED
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL


@pytest.mark.parametrize(
    ("text", "kind", "step", "expected"),
    [
        ("20", "positive_integer", -1, "19"),
        ("20", "positive_integer", 4, "24"),
        ("19", "positive_integer", 1, None),
        ("1.000000000000000000", "positive_decimal", -4, "0.800000000000000000"),
        ("0.000000000000000001", "positive_decimal", 1, None),
        ("0.000100000000000000", "nonnegative_decimal", 3, "0.000115000000000000"),
    ],
)
def test_probe_values_are_exact_or_unrepresentable_never_rounded(text, kind, step, expected) -> None:
    from crypto_core.validation.strategy_executable_profiles import ProfileParameterKind

    assert ev_module._probe_value(text, ProfileParameterKind(kind), step, 18) == expected


# --- F. Stage-3 synthetic stress ---------------------------------------------------------------------------------------------


def test_world_p_base_passes_every_governed_stress_scenario_through_the_economics_engine() -> None:
    base = {item.variant_id: item for item in passed().survivors}[BASE_VARIANT]
    kinds = [item.scenario_kind for item in base.stress_results]
    assert kinds == ["HIGH_VOLATILITY", "LOW_LIQUIDITY", "FLASH_CRASH"]
    assert all(item.status is EdgePrePaperCheckStatus.PASSED and item.simulated for item in base.stress_results)
    assert all(item.expectancy_non_negative and not item.maintenance_breached for item in base.stress_results)
    flash = base.stress_results[2]
    assert flash.shock_time_ns is not None and flash.shock_time_ns % DAY == 0
    assert base.stress_results[0].shock_time_ns is None


def test_a_harsher_governed_low_liquidity_slippage_fails_stress_and_admits_nothing() -> None:
    evidence = build(ef6_p(), policy=policy(low_liquidity_slippage_multiplier="40.000000000000000000"))
    _assert_receipt(evidence)
    base = {item.variant_id: item for item in evidence.survivors}[BASE_VARIANT]
    assert base.stress_status is EdgePrePaperCheckStatus.FAILED
    assert _code("stress_expectancy_negative") + ":LOW_LIQUIDITY" in base.reason_codes
    assert evidence.verdict_reason_codes == (_code("no_survivor_passes_every_pre_paper_gate"),)


# --- G. trial chain, governance and currentness ------------------------------------------------------------------------------


def test_a_chain_without_this_preregistration_fails_and_a_foreign_genesis_fails() -> None:
    foreign = build(ef6_p(), chain=chain_for((ef6t.ef5("A"),)))
    _assert_receipt(foreign)
    assert _code("trial_chain_missing_this_preregistration") in foreign.verdict_reason_codes
    record = genesis(4)
    other = build(ef6_p(), chain=chain_for((ef5_p(),), record))
    assert _code("trial_chain_genesis_not_the_governed_genesis") in other.verdict_reason_codes
    assert other.gate_verdict is EdgeGateVerdict.FAIL


@pytest.mark.parametrize(
    "change",
    [
        {"approval_kind": SYNTHETIC},
        {"attested_cumulative_trial_count": 13},
        {"attested_evaluation_id": "pre-paper-2"},
        {"attested_head_digest": "f" * 64},
        {"attested_chain_digest": "f" * 64},
        {"attested_preregistration_digest": "f" * 64},
        {"attested_correlation_id": "corr-2"},
        {"no_off_chain_trial_attested": False},
    ],
)
def test_a_stale_foreign_or_synthetic_currentness_attestation_needs_governance(change: dict[str, object]) -> None:
    chain = chain_for((ef5_p(),))
    attestation = attestation_for(chain, preregistration_digest=ef5_p().leakage_bias_evidence_digest, **change)
    evidence = build(ef6_p(), attestation=attestation)
    _assert_shape(evidence)
    assert evidence.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL
    assert evidence.admitted_assignment_digests == ()
    assert evidence.synthetic_test_approval_used is (change.get("approval_kind") is SYNTHETIC)


def test_unapproved_or_synthetic_policy_and_genesis_need_governance() -> None:
    unapproved = build(ef6_p(), policy=policy(approved=False))
    assert _code("policy_not_advanced:NEEDS_GOVERNANCE_APPROVAL") in unapproved.verdict_reason_codes
    record = genesis()
    synthetic_chain = build_edge_trial_count_chain(
        chain_id="trial-chain-1",
        genesis=record,
        genesis_approval=genesis_approval(record, approval_kind=SYNTHETIC),
        preregistrations=(ef5_p(),),
        expected_preregistration_digests=(ef5_p().leakage_bias_evidence_digest,),
    )
    synthetic = build(ef6_p(), chain=synthetic_chain)
    assert _code("trial_chain_not_advanced:NEEDS_GOVERNANCE_APPROVAL") in synthetic.verdict_reason_codes
    assert synthetic.synthetic_test_approval_used is True
    assert synthetic.dsr_status is EdgePrePaperCheckStatus.NOT_EVALUATED


# --- H. provenance and integrity ---------------------------------------------------------------------------------------------


def test_a_frame_dataset_that_is_not_the_union_of_the_segments_is_rejected() -> None:
    items = frame_dataset_for(ef6_p()).records
    books = [item for item in items if item.series_id == "book"]
    missing = _dataset("dataset-p-frame-missing", tuple(item for item in items if item is not books[-1]))
    later = books[-1].event_time_ns + FUNDING
    extra_book = _pit("book", "order_book", books[-1].sequence_id + 1, later, _book_values(later))
    extra = _dataset("dataset-p-frame-extra", (*items, extra_book))
    for dataset in (missing, extra):
        assert (dataset.status, dataset.gate_verdict) == (EdgeEvidenceStatus.READY, EdgeGateVerdict.PASS)
        evidence = build(ef6_p(), frame_dataset=dataset)
        _assert_receipt(evidence)
        assert evidence.status is EdgeEvidenceStatus.REJECTED
        assert evidence.integrity_reason_codes == (_code("frame_dataset_not_the_union_of_ef6_segment_datasets"),)


def test_verification_needs_the_exact_ef6_context_and_rejects_a_forged_split_matrix() -> None:
    evidence = passed()
    assert _verify(evidence, ef6t.cheap()).intact is False
    assert _verify(evidence, None).intact is True
    for changes in (
        {"split_overfit_bits": "1" + evidence.split_overfit_bits[1:]},
        {"cscv_overfit_split_count": 1},
        {"pbo": "0.100000000000000000"},
        {"admission_cap_fraction": "0.500000000000000000"},
        {"admitted_assignment_digests": ef6_p().surviving_assignment_digests},
        {"dsr_cumulative_trial_count": 9},
        {"gate_verdict": EdgeGateVerdict.FAIL},
    ):
        verification = _verify(_reseal(evidence, **changes))
        assert verification.intact is False, changes
        assert any(code.startswith(_code("field_mismatch:")) for code in verification.reason_codes)
    assert _verify(replace(evidence, evidence_id="pre-paper-2")).intact is False


def test_a_tampered_ef6_policy_or_chain_is_rejected() -> None:
    forged_ef6 = replace(ef6t.cheap(), gate_verdict=EdgeGateVerdict.PASS, advances=True)
    forged_ef6 = replace(forged_ef6, walk_forward_oos_evidence_digest=edge_walk_forward_oos_evidence_digest(forged_ef6))
    evidence = build(forged_ef6, expected_walk_forward_oos_evidence_digest=forged_ef6.walk_forward_oos_evidence_digest)
    assert evidence.status is EdgeEvidenceStatus.REJECTED
    assert any(code.startswith(_code("walk_forward_integrity_failure:")) for code in evidence.integrity_reason_codes)
    wrong_anchor = build(ef6_p(), expected_policy_digest="0" * 64)
    assert wrong_anchor.integrity_reason_codes == (_code("policy_digest_mismatch"),)
    wrong_chain = build(ef6_p(), expected_trial_chain_digest="0" * 64)
    assert wrong_chain.integrity_reason_codes == (_code("trial_chain_digest_mismatch"),)


def test_a_non_advancing_ef6_propagates_and_computes_nothing() -> None:
    evidence = evidence_for(ef6t.cheap())
    _assert_receipt(evidence, ef6t.cheap())
    assert evidence.gate_verdict is EdgeGateVerdict.FAIL
    assert _code("walk_forward_not_advanced:FAIL") in evidence.verdict_reason_codes
    assert (evidence.frame_runs, evidence.cscv_split_count, evidence.survivors) == ((), 0, ())
    assert evidence.pbo_band is EdgePboBand.NOT_COMPUTED


def test_a_single_registered_variant_is_never_computable() -> None:
    evidence = evidence_for(ef6t.passed())
    _assert_receipt(evidence, ef6t.passed())
    assert evidence.verdict_reason_codes == (_code("cscv_requires_at_least_two_registered_variants"),)
    assert evidence.frame_runs == ()


@pytest.mark.parametrize(
    ("override", "code"),
    [
        ({"evidence_id": ""}, "evidence_id_invalid"),
        ({"correlation_id": "live run"}, "forbidden_scope_token"),
        ({"expected_root_intake_digest": "x"}, "root_intake_digest_invalid"),
        ({"currentness_attestation": object()}, "currentness_attestation_malformed"),
        ({"policy": object()}, "policy_malformed"),
        ({"trial_chain": object()}, "trial_chain_malformed"),
        ({"frame_dataset": object()}, "frame_dataset_malformed"),
    ],
)
def test_malformed_caller_input_is_a_construction_error(override: dict[str, object], code: str) -> None:
    arguments = evidence_arguments(ef6t.cheap())
    arguments.update(override)
    with pytest.raises(EdgePrePaperValidationEvidenceError, match=code):
        build_edge_pre_paper_validation_evidence(ef6t.cheap(), **arguments)  # type: ignore[arg-type]


def test_builder_accepts_no_statistic_seed_ranking_regime_or_flag_input() -> None:
    import inspect

    parameters = set(inspect.signature(build_edge_pre_paper_validation_evidence).parameters)
    assert parameters == {
        "walk_forward_oos_evidence",
        "expected_walk_forward_oos_evidence_digest",
        "expected_root_intake_digest",
        "frame_dataset",
        "expected_frame_dataset_digest",
        "policy",
        "expected_policy_digest",
        "trial_chain",
        "expected_trial_chain_digest",
        "currentness_attestation",
        "evidence_id",
        "correlation_id",
    }


def test_rule_set_commits_every_methodology_and_the_limited_regime_scope() -> None:
    rules = edge_pre_paper_validation_rule_set()
    assert rules["cscv_method_id"] == "CSCV_PBO_S16_LEXICOGRAPHIC_EXACT_V1"
    assert rules["dsr_method_id"] == "DSR_PRDV4_STANDARDIZED_Z_EXACT_DECISION_V1"
    assert rules["monte_carlo_method_id"] == "MC_SIGN_FLIP_SHA256_CTR_V1"
    assert rules["monte_carlo_sample_count"] == 10_000
    assert rules["sensitivity_method_id"] == "SENSITIVITY_STAR_GRID_X20_V1"
    assert rules["stress_method_id"] == "STRESS_PIT_TRANSFORM_V1"
    assert (rules["admission_scope"], rules["regime_conditional_pbo_status"]) == ("LIMITED_S1_PAPER_V1", "UNPROVEN")


def test_module_is_pure_and_imports_no_runtime_or_bist_authority() -> None:
    source = Path(ev_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            assert node.module.startswith(
                (
                    "crypto_core.validation.",
                    "collections",
                    "dataclasses",
                    "enum",
                    "fractions",
                    "itertools",
                    "__future__",
                )
            )
        if isinstance(node, ast.Import):
            assert {alias.name for alias in node.names} <= {"hashlib", "math"}
        if isinstance(node, ast.Constant):
            assert type(node.value) is not float
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            assert node.func.id not in {"float", "open", "eval", "exec"}
    lowered = source.lower()
    assert "bist" not in lowered and "decimal import" not in lowered and "random" not in lowered


@SLOW
def test_memo_free_reproof_of_the_positive_world() -> None:
    evidence = passed()
    ef6t._MEMO_ENABLED[0] = False
    try:
        verification = _verify(evidence)
    finally:
        ef6t._MEMO_ENABLED[0] = True
    assert verification.intact is True, verification.reason_codes


def test_memos_agree_with_the_real_functions() -> None:
    memo = _PRE_MEMOS[(ev_module, "verify_edge_trial_count_chain")]
    chain = chain_for((ef5_p(),))
    assert memo.real(chain) == memo(chain)  # type: ignore[attr-defined]
    assert ev_module.verify_edge_trial_count_chain is memo
    assert {field.name for field in fields(EdgePrePaperValidationEvidence)} >= {"split_matrix_digest", "pbo"}
