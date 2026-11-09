"""Governed paper sizing chain (``S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1``): the decision-time ENVELOPE_FIT and CTR
depth-cap readings of every S1 entry and the fill-time bounds of schedule v5, derived and never accepted.

Design authority: the approved companion ``docs/crypto_core/s1_approved_doctrine_adoption_v1.md`` §4.1-§4.7 and §5
(ALLOCATION_ENVELOPE_V1, A9', CTR_SOURCE_QUALIFICATION_V1; items 2.1-2.3 and 3.1-3.2; FCD-07), adopted by PR #433, over
PRDV4 §1.7, §1.2 A.4, §1.12 Mechanism 2 and §7.2. Paper-only, deterministic, point-in-time and fail-closed. Exact
arithmetic, no IO, clock, randomness, network or environment.

The chain of one entry decision at ``t`` (resulting direction LONG or SHORT, so its order buys or sells):

* input source: the genesis authority (its RG-2 envelope sleeves and instrument), the authenticated decision run and
  archive, the schedule under evaluation and the ONE engine re-run whose decision snapshot and exact NAV the entry gate
  already reads, and the CTR source context the day seal verified (or none);
* allocation: ``governed_paper_allocation_envelope`` derives the allocation timeline of ``[G, run end)`` and reads the
  genesis sleeve's eligibility and weight at ``t``;
* usage: ``abs(q_pre) x mark(t) + u x L_k``, with ``q_pre`` the snapshot position, ``mark(t)`` its fresh visible mark,
  ``u`` the order quantity (the distance from ``q_pre`` to the snapshot's candidate) and ``L_k`` the reservation price of
  the schedule window that contains ``t`` (the bound the engine places on the filled notional). ``B`` is the snapshot's
  exact publication-visible NAV;
* ENVELOPE_FIT at ``t`` (§4.6) on those facts;
* the CTR reading at ``t`` and the visible depth within 5 bps of the latest fresh depth-50 tip on the order's side, and
  the depth-cap status of the order quantity (§5).

The fill-time bounds (schedule v5) are facts of the inputs alone, never of the admissions, so the sequential admission
keeps its unique fixed point:

* exposure envelopes: an envelope window wherever the genesis sleeve's eligibility is proven over the window (the weight
  for a MEMBER, 0 for a NON_MEMBER); with the allocation BLOCKED at every rebalance of the governed path, there is none,
  so the engine refuses every exposure-increasing fill as unproven;
* depth caps: for every book record of the authenticated ORDER_BOOK series visible in ``[t + latency, t +
  max_execution_delay]`` of an entry decision, on that entry's side, the exact cap ``0.02 alpha D`` from the CTR reading
  at the record's visibility and its own visible depth (absent when either is unproven); without a qualified source
  there is none, so the engine refuses every exposure-increasing fill as unproven.

The evidence binds the allocation timeline, the CTR source digests and admission, the fill-time bounds and every
entry's reading. Nothing here approves a value, qualifies a source, creates a capital quantity or admits an entry.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_allocation_envelope import (
    GOVERNED_PAPER_ALLOCATION_CAP,
    GOVERNED_PAPER_ALLOCATION_CONTRACT_ID,
    GOVERNED_PAPER_ALLOCATION_FLOOR,
    GOVERNED_PAPER_ALLOCATION_TIMELINE_SCHEMA,
    GovernedPaperAllocationEligibility,
    GovernedPaperAllocationStatus,
    GovernedPaperAllocationTimeline,
    GovernedPaperEnvelopeFitStatus,
    derive_governed_paper_allocation_timeline,
    evaluate_governed_paper_envelope_fit,
    governed_paper_allocation_reading_at,
)
from crypto_core.validation.governed_paper_ctr_qualification import (
    GOVERNED_PAPER_CTR_CONTRACT_ID,
    GOVERNED_PAPER_CTR_DEPTH_BAND,
    GOVERNED_PAPER_CTR_DEPTH_FRACTION,
    GOVERNED_PAPER_CTR_REQUIRED_USE,
    GOVERNED_PAPER_CTR_SLOPE,
    GOVERNED_PAPER_CTR_THRESHOLD,
    GovernedPaperCtrApprovalKind,
    GovernedPaperCtrDepthStatus,
    GovernedPaperCtrReading,
    GovernedPaperCtrSourceContext,
    GovernedPaperDepthIndex,
    GovernedPaperVisibleDepth,
    evaluate_governed_paper_ctr_depth,
    governed_paper_ctr_active_table,
    governed_paper_ctr_admission,
    governed_paper_ctr_canonical_context,
    governed_paper_ctr_depth_cap,
    governed_paper_ctr_reading,
)
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperGenesisAuthority
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_SIZING_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HistoricalExecutionAdmissionSchedule,
    HistoricalExecutionDecisionExactValues,
    HistoricalExecutionDecisionPortfolioSnapshot,
    HistoricalExecutionDepthCap,
    HistoricalExecutionExposureEnvelope,
    HistoricalExecutionSide,
)
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset

_PREFIX = "governed_paper_sizing_chain"
_DIGEST_FIELD = "evidence_digest"
_ENTRY_DIRECTIONS = {"LONG": HistoricalExecutionSide.BUY, "SHORT": HistoricalExecutionSide.SELL}

GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID = "S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1"
GOVERNED_PAPER_SIZING_EVIDENCE_SCHEMA = "governed-paper-sizing-evidence.v1"
GOVERNED_PAPER_SIZING_RULE_ID = "governed-paper-sizing-chain.v1"
GOVERNED_PAPER_SIZING_APPROVED_ITEMS = ("D9", "D15", "2.1", "2.2", "2.3", "3.1", "3.2", "FCD-07")
GOVERNED_PAPER_SIZING_PENDING_ITEMS = (
    "1.4",
    "1.5",
    "1.6",
    "1.7",
    "1.8",
    "5.1",
    "5.2",
    "HD-07",
    "FCD-13",
    "X-H1",
    "X-M1-C",
)
GOVERNED_PAPER_SIZING_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("real_source_qualified", False),
    ("capital_allocated", False),
    ("entry_authorized", False),
    ("production_use_authorized", False),
)


def governed_paper_sizing_rule() -> dict[str, object]:
    """The sizing chain's rule: its authorities, readings and approved and pending items."""

    def render(value: Fraction) -> str:
        return str(value)

    return {
        "rule_id": GOVERNED_PAPER_SIZING_RULE_ID,
        "contract_id": GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID,
        "authorities": [
            "PRDV4 §1.7 (D9)",
            "PRDV4 §1.2 A.4 (D15)",
            "PRDV4 §1.12 Mechanism 2",
            "PRDV4 §7.2",
            "s1_approved_doctrine_adoption_v1 §4.1-§4.7",
            "s1_approved_doctrine_adoption_v1 §5",
        ],
        "approved_items": list(GOVERNED_PAPER_SIZING_APPROVED_ITEMS),
        "pending_items": list(GOVERNED_PAPER_SIZING_PENDING_ITEMS),
        "allocation_contract_id": GOVERNED_PAPER_ALLOCATION_CONTRACT_ID,
        "allocation_timeline_schema": GOVERNED_PAPER_ALLOCATION_TIMELINE_SCHEMA,
        "allocation_floor": render(GOVERNED_PAPER_ALLOCATION_FLOOR),
        "allocation_cap": render(GOVERNED_PAPER_ALLOCATION_CAP),
        "allocation_reading": "the_genesis_sleeve_at_t_from_the_latest_rebalance_at_or_before_t_while_no_later_"
        "rebalance_can_lie_between_otherwise_unknown",
        "usage": "abs_q_pre_times_the_fresh_visible_mark_plus_the_order_quantity_times_the_reservation_price_of_the_"
        "window_containing_t",
        "envelope_base": "the_exact_publication_visible_nav_of_the_decision_snapshot",
        "envelope_fit": "pass_member_usage_le_weight_times_nav_fail_member_above_or_non_member_positive_or_above_0_40_"
        "nav_otherwise_blocked",
        "ctr_contract_id": GOVERNED_PAPER_CTR_CONTRACT_ID,
        "ctr_required_use": GOVERNED_PAPER_CTR_REQUIRED_USE,
        "ctr_threshold": render(GOVERNED_PAPER_CTR_THRESHOLD),
        "ctr_slope": render(GOVERNED_PAPER_CTR_SLOPE),
        "ctr_window_ns": 60_000_000_000,
        "depth_fraction": render(GOVERNED_PAPER_CTR_DEPTH_FRACTION),
        "depth_band": render(GOVERNED_PAPER_CTR_DEPTH_BAND),
        "depth_side": "the_side_the_order_consumes_asks_for_a_buy_bids_for_a_sell",
        "depth_decision_tip": "the_latest_depth_50_tip_visible_at_t_by_native_event_time_fresh_within_10s",
        "depth_fill_tip": "the_book_record_the_fill_executes_against",
        "depth_cap": "fail_q_ge_0_02_d_exact_pass_q_lt_0_02_alpha_d_with_a_qualified_covered_reading_otherwise_blocked",
        "fill_envelopes": "a_window_wherever_the_genesis_sleeve_eligibility_is_proven_over_it",
        "fill_depth_caps": "every_series_book_visible_in_t_plus_latency_to_t_plus_max_execution_delay_of_an_entry_"
        "on_its_side_with_a_proven_0_02_alpha_d",
        "incubation": "not_represented_item_1_7_pending_no_cold_start_excepted",
        "admission": "the_readings_are_facts_of_the_inputs_and_of_each_decisions_own_snapshot_the_sequential_fixed_"
        "point_is_unchanged",
    }


GOVERNED_PAPER_SIZING_RULE = governed_paper_sizing_rule()
GOVERNED_PAPER_SIZING_RULE_DIGEST = edge_sha256_text(edge_canonical_json(GOVERNED_PAPER_SIZING_RULE))


class GovernedPaperSizingError(EdgeArtifactError):
    """Malformed input or a binding defect: no sizing evidence is represented over it."""


@dataclass(frozen=True)
class GovernedPaperSizingContext:
    """The sizing chain context of one evaluation (rule set v8), supplied by the day seal from verified lineage inputs:
    the CTR source (qualification, revocations, capture) or None, for no source at all."""

    ctr_source: GovernedPaperCtrSourceContext | None


@dataclass(frozen=True)
class GovernedPaperSizingReading:
    """The sizing facts and readings of one entry decision; amounts are exact rational texts (``str(Fraction)``)."""

    decision_sequence: int
    decision_time_ns: int
    target_direction: str
    order_side: HistoricalExecutionSide
    order_quantity: str | None
    reservation_price: str | None
    position_quantity: str | None
    mark_price: str | None
    usage: str | None
    usage_exact: bool
    nav: str | None
    allocation_rebalance_ns: int | None
    eligibility: GovernedPaperAllocationEligibility
    weight: str | None
    allocation_reason: str
    envelope_status: GovernedPaperEnvelopeFitStatus
    envelope_observed: str
    envelope_reason: str
    ctr: GovernedPaperCtrReading
    depth: GovernedPaperVisibleDepth
    depth_status: GovernedPaperCtrDepthStatus
    depth_observed: str
    depth_reason: str
    reading_digest: str


@dataclass(frozen=True)
class GovernedPaperSizingEvidence:
    """The derived sizing evidence of one evaluation: the allocation timeline, the CTR source binding, the fill-time
    bounds and every entry's reading."""

    schema_version: str
    contract_id: str
    rule_id: str
    rule_digest: str
    instrument: str
    genesis_digest: str
    # §4.5: the equity origin E0 and the C5 reference notional R, re-proven equal; the envelope base is the
    # publication-visible NAV B of each decision, never E0, R or the RG-2 budget K (which is not read).
    equity_origin_e0: str
    reference_notional_r: str
    allocation_timeline: GovernedPaperAllocationTimeline
    ctr_qualification_digest: str
    ctr_revocation_digests: tuple[str, ...]
    ctr_capture_digest: str
    ctr_approval_table_id: str
    ctr_admission_reason: str
    exposure_envelopes: tuple[HistoricalExecutionExposureEnvelope, ...]
    depth_caps: tuple[HistoricalExecutionDepthCap, ...]
    readings: tuple[GovernedPaperSizingReading, ...]
    evidence_digest: str
    paper_only: bool = True
    synthetic_ctr_qualification_used: bool = False
    real_source_qualified: bool = False
    capital_allocated: bool = False
    entry_authorized: bool = False
    production_use_authorized: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperSizingError:
    return GovernedPaperSizingError(_reason(code))


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]


def _rational(value: Fraction | None) -> str | None:
    return None if value is None else str(value)


def _canonical_context(context: object, *, instrument: str) -> GovernedPaperSizingContext:
    if type(context) is not GovernedPaperSizingContext:
        raise _fail("sizing_context_malformed")
    if context.ctr_source is not None:
        governed_paper_ctr_canonical_context(context.ctr_source, instrument=instrument)
    return context


def _candidate_sleeves(authority: GovernedPaperGenesisAuthority) -> tuple[str, ...]:
    return tuple(item.sleeve_id for item in authority.portfolio_risk_envelope.sleeve_caps)


def _capital_quantities(authority: GovernedPaperGenesisAuthority) -> tuple[Fraction, Fraction]:
    """``(E0, R)`` re-proven equal at genesis (§4.5); a difference is a structural block, never a reading."""

    origin = Fraction(authority.economics_policy.initial_equity)
    reference = Fraction(authority.equity_basis_policy.paper_performance_reference_notional)
    if origin != reference:
        raise _fail("reference_notional_r_is_not_the_equity_origin_e0")
    return origin, reference


# --- the fill-time bounds ----------------------------------------------------------------------------------------------


def governed_paper_sizing_exposure_envelopes(
    timeline: GovernedPaperAllocationTimeline, *, edge_id: str
) -> tuple[HistoricalExecutionExposureEnvelope, ...]:
    """The exposure envelopes of ``edge_id``: one window per rebalance whose allocation is proven, its weight for a MEMBER
    and 0 for a NON_MEMBER, over the window in which that rebalance is proven the latest (to the next rebalance or the
    horizon with a proven edge-state record, its own instant otherwise). Pure."""

    if type(timeline) is not GovernedPaperAllocationTimeline or edge_id not in timeline.candidate_edge_ids:
        raise _fail("timeline_or_edge_malformed")
    envelopes: list[HistoricalExecutionExposureEnvelope] = []
    rebalances = timeline.rebalances
    for index, rebalance in enumerate(rebalances):
        if rebalance.result.status is GovernedPaperAllocationStatus.BLOCKED:
            continue
        entry = next(item for item in rebalance.result.weights if item.edge_id == edge_id)
        if entry.eligibility is GovernedPaperAllocationEligibility.MEMBER and entry.weight is not None:
            fraction = entry.weight
        elif entry.eligibility is GovernedPaperAllocationEligibility.NON_MEMBER:
            fraction = "0"
        else:  # pragma: no cover - a proven allocation proves every candidate's eligibility
            continue
        if timeline.edge_state_transitions_proven:
            end = rebalances[index + 1].instant_ns if index + 1 < len(rebalances) else timeline.horizon_ns
        else:
            end = rebalance.instant_ns + 1
        envelopes.append(HistoricalExecutionExposureEnvelope(rebalance.instant_ns, end, fraction))
    return tuple(envelopes)


def _entries(run: HistoricalDecisionRun) -> tuple[tuple[int, int, str], ...]:
    return tuple(
        (item.decision_sequence, item.decision_time_ns, item.resulting_direction)
        for item in run.decisions
        if item.resulting_direction in _ENTRY_DIRECTIONS
    )


def governed_paper_sizing_depth_caps(
    *,
    run: HistoricalDecisionRun,
    depth: GovernedPaperDepthIndex,
    context: GovernedPaperSizingContext,
    instrument: str,
    latency_ns: int,
    max_execution_delay_ns: int,
) -> tuple[HistoricalExecutionDepthCap, ...]:
    """Every proven depth cap a fill of an entry decision of ``run`` may execute against (see the module docstring)."""

    caps: dict[tuple[str, str], HistoricalExecutionDepthCap] = {}
    readings: dict[int, GovernedPaperCtrReading] = {}
    for _, instant, direction in _entries(run):
        side = _ENTRY_DIRECTIONS[direction]
        for record in depth.records_visible_between(instant + latency_ns, instant + max_execution_delay_ns):
            key = (record.record_digest, side.value)
            if key in caps:
                continue
            visible = max(record.available_at_ns, record.finalized_at_ns)  # type: ignore[type-var]
            if visible not in readings:
                readings[visible] = governed_paper_ctr_reading(
                    context.ctr_source, instrument=instrument, time_ns=visible
                )
            if not readings[visible].available:  # no cap is provable without a qualified, covered reading
                continue
            cap = governed_paper_ctr_depth_cap(depth.of_record(record.record_digest, side), readings[visible])
            if cap is not None:
                caps[key] = HistoricalExecutionDepthCap(record.record_digest, side, str(cap))
    return tuple(caps[key] for key in sorted(caps))


def governed_paper_sizing_fill_bounds(
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    context: GovernedPaperSizingContext,
) -> tuple[tuple[HistoricalExecutionExposureEnvelope, ...], tuple[HistoricalExecutionDepthCap, ...]]:
    """The schedule v5 fill-time bounds of one evaluation: exposure envelopes and depth caps. Pure."""

    if type(authority) is not GovernedPaperGenesisAuthority or type(run) is not HistoricalDecisionRun:
        raise _fail("sizing_inputs_malformed")
    genesis, policy = authority.genesis, authority.economics_policy
    _capital_quantities(authority)
    context = _canonical_context(context, instrument=genesis.instrument)
    timeline = derive_governed_paper_allocation_timeline(
        genesis_digest=genesis.genesis_digest,
        candidate_edge_ids=_candidate_sleeves(authority),
        start_ns=genesis.genesis_start_ns,
        horizon_ns=run.evaluation_end_ns,
    )
    envelopes = governed_paper_sizing_exposure_envelopes(timeline, edge_id=genesis.sleeve_id)
    caps = governed_paper_sizing_depth_caps(
        run=run,
        depth=GovernedPaperDepthIndex(dataset, instrument=genesis.instrument),
        context=context,
        instrument=genesis.instrument,
        latency_ns=policy.latency_ns,
        max_execution_delay_ns=policy.max_execution_delay_ns,
    )
    return envelopes, caps


# --- the decision readings ---------------------------------------------------------------------------------------------


def _reservation_price(schedule: HistoricalExecutionAdmissionSchedule, instant: int) -> Fraction | None:
    for window in schedule.windows:
        if window.window_start_ns <= instant < window.window_end_ns:
            return Fraction(window.reservation_price)
    return None


def _reading(  # noqa: PLR0913 - the facts of one decision
    *,
    sequence: int,
    instant: int,
    direction: str,
    snapshot: HistoricalExecutionDecisionPortfolioSnapshot | None,
    exact: HistoricalExecutionDecisionExactValues | None,
    schedule: HistoricalExecutionAdmissionSchedule,
    timeline: GovernedPaperAllocationTimeline,
    sleeve: str,
    depth: GovernedPaperDepthIndex,
    context: GovernedPaperSizingContext,
    instrument: str,
) -> GovernedPaperSizingReading:
    side = _ENTRY_DIRECTIONS[direction]
    position = mark = quantity = nav = None
    if snapshot is not None:
        position = Fraction(snapshot.position_quantity)
        mark = None if snapshot.mark_price is None else Fraction(snapshot.mark_price)
        distance = abs(Fraction(snapshot.candidate_position_quantity) - position)
        quantity = distance if distance > 0 else None
        nav = None if exact is None else exact.nav
    reservation = _reservation_price(schedule, instant)
    usage: Fraction | None = None
    usage_exact = False
    if quantity is not None and reservation is not None:
        usage = quantity * reservation
        if position == 0:
            usage_exact = True
        elif mark is not None:
            usage, usage_exact = usage + abs(position) * mark, True  # type: ignore[operator]
    allocation = governed_paper_allocation_reading_at(timeline, edge_id=sleeve, time_ns=instant)
    weight = None if allocation.weight is None else Fraction(allocation.weight)
    envelope = evaluate_governed_paper_envelope_fit(
        eligibility=allocation.eligibility, weight=weight, nav=nav, usage_lower=usage, usage_exact=usage_exact
    )
    ctr = governed_paper_ctr_reading(context.ctr_source, instrument=instrument, time_ns=instant)
    visible = depth.at(instant, side)
    cap = evaluate_governed_paper_ctr_depth(quantity=quantity, depth=visible, ctr=ctr)
    seed = GovernedPaperSizingReading(
        decision_sequence=sequence,
        decision_time_ns=instant,
        target_direction=direction,
        order_side=side,
        order_quantity=_rational(quantity),
        reservation_price=_rational(reservation),
        position_quantity=_rational(position),
        mark_price=_rational(mark),
        usage=_rational(usage),
        usage_exact=usage_exact,
        nav=_rational(nav),
        allocation_rebalance_ns=allocation.rebalance_ns,
        eligibility=allocation.eligibility,
        weight=allocation.weight,
        allocation_reason=allocation.reason,
        envelope_status=envelope.status,
        envelope_observed=envelope.observed,
        envelope_reason=envelope.reason,
        ctr=ctr,
        depth=visible,
        depth_status=cap.status,
        depth_observed=cap.observed,
        depth_reason=cap.reason,
        reading_digest="",
    )
    return replace(seed, reading_digest=edge_payload_digest(_to_payload(seed), "reading_digest"))


def derive_governed_paper_sizing_evidence(  # noqa: PLR0913 - one evaluation's authoritative inputs
    *,
    authority: GovernedPaperGenesisAuthority,
    run: HistoricalDecisionRun,
    dataset: HistoricalPitDataset,
    schedule: HistoricalExecutionAdmissionSchedule,
    snapshots: Mapping[int, HistoricalExecutionDecisionPortfolioSnapshot],
    exact_values: Mapping[int, HistoricalExecutionDecisionExactValues],
    context: GovernedPaperSizingContext,
) -> GovernedPaperSizingEvidence:
    """The sizing evidence of one evaluation (see the module docstring). Pure.

    ``snapshots`` and ``exact_values`` are the entry gate's own decision snapshots and the exact values of the same
    engine re-run, keyed by decision sequence. ``schedule`` must be the schedule v5 under evaluation, carrying exactly the
    fill-time bounds derived here (``schedule_sizing_bounds_not_derived`` otherwise). Malformed input raises
    ``GovernedPaperSizingError``.
    """

    if type(authority) is not GovernedPaperGenesisAuthority or type(run) is not HistoricalDecisionRun:
        raise _fail("sizing_inputs_malformed")
    if type(dataset) is not HistoricalPitDataset or type(schedule) is not HistoricalExecutionAdmissionSchedule:
        raise _fail("sizing_inputs_malformed")
    if schedule.schema_version != HISTORICAL_EXECUTION_SIZING_ADMISSION_SCHEDULE_SCHEMA_VERSION:
        raise _fail("sizing_needs_the_schedule_v5")
    genesis, policy = authority.genesis, authority.economics_policy
    origin, reference = _capital_quantities(authority)
    context = _canonical_context(context, instrument=genesis.instrument)
    timeline = derive_governed_paper_allocation_timeline(
        genesis_digest=genesis.genesis_digest,
        candidate_edge_ids=_candidate_sleeves(authority),
        start_ns=genesis.genesis_start_ns,
        horizon_ns=run.evaluation_end_ns,
    )
    depth = GovernedPaperDepthIndex(dataset, instrument=genesis.instrument)
    envelopes = governed_paper_sizing_exposure_envelopes(timeline, edge_id=genesis.sleeve_id)
    caps = governed_paper_sizing_depth_caps(
        run=run,
        depth=depth,
        context=context,
        instrument=genesis.instrument,
        latency_ns=policy.latency_ns,
        max_execution_delay_ns=policy.max_execution_delay_ns,
    )
    if (schedule.exposure_envelopes, schedule.depth_caps) != (envelopes, caps):
        raise _fail("schedule_sizing_bounds_not_derived")
    readings = tuple(
        _reading(
            sequence=sequence,
            instant=instant,
            direction=direction,
            snapshot=snapshots.get(sequence),
            exact=exact_values.get(sequence),
            schedule=schedule,
            timeline=timeline,
            sleeve=genesis.sleeve_id,
            depth=depth,
            context=context,
            instrument=genesis.instrument,
        )
        for sequence, instant, direction in _entries(run)
    )
    source = context.ctr_source
    table = governed_paper_ctr_active_table()
    admission = (
        "no_ctr_source_supplied" if source is None else governed_paper_ctr_admission(table, source.qualification)
    )
    seed = GovernedPaperSizingEvidence(
        schema_version=GOVERNED_PAPER_SIZING_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID,
        rule_id=GOVERNED_PAPER_SIZING_RULE_ID,
        rule_digest=GOVERNED_PAPER_SIZING_RULE_DIGEST,
        instrument=genesis.instrument,
        genesis_digest=genesis.genesis_digest,
        equity_origin_e0=str(origin),
        reference_notional_r=str(reference),
        allocation_timeline=timeline,
        ctr_qualification_digest="" if source is None else source.qualification.qualification_digest,
        ctr_revocation_digests=() if source is None else tuple(item.revocation_digest for item in source.revocations),
        ctr_capture_digest="" if source is None else source.capture.capture_digest,
        ctr_approval_table_id=table.table_id,
        ctr_admission_reason=admission,
        exposure_envelopes=envelopes,
        depth_caps=caps,
        readings=readings,
        evidence_digest="",
        synthetic_ctr_qualification_used=source is not None
        and admission == ""
        and source.qualification.approval_kind is GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC,
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), _DIGEST_FIELD))


def governed_paper_sizing_evidence_to_dict(evidence: GovernedPaperSizingEvidence) -> dict[str, object]:
    return _to_payload(evidence)


def governed_paper_sizing_evidence_digest(evidence: GovernedPaperSizingEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), _DIGEST_FIELD)


def governed_paper_sizing_reading_digest(reading: GovernedPaperSizingReading) -> str:
    """Recompute one reading's digest, excluding only ``reading_digest``."""

    return edge_payload_digest(_to_payload(reading), "reading_digest")


__all__ = [
    "GOVERNED_PAPER_SIZING_APPROVED_ITEMS",
    "GOVERNED_PAPER_SIZING_CHAIN_CONTRACT_ID",
    "GOVERNED_PAPER_SIZING_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_SIZING_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_SIZING_PENDING_ITEMS",
    "GOVERNED_PAPER_SIZING_RULE",
    "GOVERNED_PAPER_SIZING_RULE_DIGEST",
    "GOVERNED_PAPER_SIZING_RULE_ID",
    "GovernedPaperSizingContext",
    "GovernedPaperSizingError",
    "GovernedPaperSizingEvidence",
    "GovernedPaperSizingReading",
    "derive_governed_paper_sizing_evidence",
    "governed_paper_sizing_depth_caps",
    "governed_paper_sizing_evidence_digest",
    "governed_paper_sizing_evidence_to_dict",
    "governed_paper_sizing_exposure_envelopes",
    "governed_paper_sizing_fill_bounds",
    "governed_paper_sizing_reading_digest",
    "governed_paper_sizing_rule",
]
