"""Governed paper Kelly reading (S1_KELLY_DEFINED_READING_CONSTRUCTION_V1): RECORD A's KD-1..KD-13 with D-A1, constructed.

Design authority: ``docs/crypto_core/s1_kelly_class_completion_amendment_v1.md`` (RECORD A: A1.3, the doctrine reading
KD-0 with the clarification C-1 and C-2, and the approved methodology KD-1..KD-13) and
``docs/crypto_core/s1_kelly_da1_doctrine_adoption_v1.md`` (the KD-9 of the human decision ``S1_KELLY_DA1_DECISION_V1``),
read with PRDV4 §0.3, §1.21 and §1.28 and the FCD-01 of ``docs/crypto_core/s1_native_risk_measurement_doctrine_adoption_v1.md``.
Paper-only, deterministic, point-in-time and fail-closed. It creates no order, sizes nothing and authorizes no entry.

Authority. Every reading is derived, never accepted, from the evaluation's own ONE governed engine re-run (its governed
outcome and, in memory only, the exact Kelly inputs of every closed trade: ``HistoricalExecutionTradeExactValues``), the
re-proven dataset, the economics and position-management policies and OHLC archive the economics binds, and the exact
FCD-01 R-4 stop-risk fraction of each entry decision (``governed_paper_risk_entry_fraction``, the same computation NT-R03
renders). The caller re-proves every one of them; this module re-proves their mutual consistency.

Trades (A1.3, KD-0, KD-10a). Every CLOSED excursion of the re-run, in engine close order, is a trade. Its exact realized net
PnL must render to the trade record's own, and its class is the sign of that PnL (win, loss or zero). Its knowledge instant
is the later of its closing fill and the visibility of the final rate of every settlement it carries, read from the
dataset's funding records, and must equal the re-run's. Its risk ``Risk_j`` is recomputed here from the sealed opening fill:
the executed price and filled quantity of its first entry fill, the milestone-0 stop that fill armed (the protection record
re-derived exactly: the basis on the price grid and the ATR re-computed at its own decision instant), the fill-instant mark
(the mark record of the fill's own valuation, visible at the fill) and the policy's taker fee plus slippage floor, by the
FCD-01 R-1 formula; it must equal the re-run's own R-5 measurement exactly. ``R_j = net_j / Risk_j`` exists only for a proven
positive risk; a missing, unmeasured, unreproducible, publication-invisible or non-positive one leaves ``R_j`` unproven. A
re-run fact that does not agree with the sealed records is not an input: ``GovernedPaperKellyError``.

Reading. At an entry decision at ``t`` the known trades are those known at or before ``t``; a trade closed by ``t`` but not
yet known keeps the windows undefined. The candidate's ``rho_t`` is its FCD-01 R-4 fraction. The one exact arithmetic is the
engine's ``historical_execution_kelly_fit`` (KD-1..KD-12 with the D-A1 Alternative 1 fit ``rho_t * max(1, Lbar) <= f_cap``),
the same the engine's schedule v8 applies at the R-5 fill. Coverage (KD-13) needs an ACTIVE PAPER_INCUBATION_V1 record,
and none can exist (companion items 1.4-1.7 are pending): no reading is ever covered, so a class-incomplete window is
``KELLY_RATIO_UNDEFINED`` (BLOCKED), never COLD_START_EXCEPTED. The undecided 100-trade bootstrap (KD-7) and HC-16a, HC-16c
and HC-16d are never read. Every recorded value is a scale-18 ROUND_HALF_EVEN rendering of the exact one (KD-10e); a value
outside the representation domain leaves the reading BLOCKED (``KELLY_VALUE_UNREPRESENTABLE``), and KD-10c's product is
decided by one exact comparison and never formed or rendered.

Evidence. ``GovernedPaperKellyEvidence`` binds the trades and every entry decision's reading; ``evidence_digest`` covers
the rest. ``governed_paper_kelly_prefix_digest`` is its run-independent X1 content before an instant (no identifier the
re-run derives), so a later seal of the lineage proves it never rewrote a reading or a trade known before.

Non-claims. A Kelly PASS proves only the fit of its own inputs: not an edge, profitability, survival, class completion,
ordinary admission, Stage-4 eligibility or readiness. The fit is a conservative constraint, not the growth-optimal or the
quarter-Kelly fraction of an arbitrary outcome distribution.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_risk_measurement import (
    governed_paper_risk_protection_stop,
    governed_paper_risk_stop_risk,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_KELLY_BLOCKS,
    HISTORICAL_EXECUTION_KELLY_CAP,
    HISTORICAL_EXECUTION_KELLY_DECAY,
    HISTORICAL_EXECUTION_KELLY_FAILURES,
    HISTORICAL_EXECUTION_KELLY_FRACTION,
    HISTORICAL_EXECUTION_KELLY_G_WINDOW,
    HISTORICAL_EXECUTION_KELLY_WINDOW,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionKellyFit,
    HistoricalExecutionKellyStatus,
    HistoricalExecutionTrade,
    HistoricalExecutionTradeExactValues,
    HistoricalExecutionTradeStatus,
    HistoricalExecutionValuationKind,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_kelly_fit,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionEconomicsPolicy,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_ohlc_bar_archive import HistoricalOhlcBarArchive
from crypto_core.validation.historical_pit_dataset import HistoricalPitDataset, HistoricalPitRecord
from crypto_core.validation.historical_position_management_policy import HistoricalPositionManagementPolicy

GOVERNED_PAPER_KELLY_CONTRACT_ID = "S1_KELLY_DEFINED_READING_CONSTRUCTION_V1"
# RECORD A (the human-approved class-completion decision) and the human decision resolving its delta D-A1.
GOVERNED_PAPER_KELLY_DECISION_IDS: tuple[str, ...] = (
    "S1_KELLY_CLASS_COMPLETION_DECISION_V3",
    "S1_KELLY_DA1_DECISION_V1",
)
GOVERNED_PAPER_KELLY_METHOD_ID = "KELLY_DEFINED_READING_V3:KD-9_D-A1_ALTERNATIVE_1"
GOVERNED_PAPER_KELLY_EVIDENCE_SCHEMA = "governed-paper-kelly-evidence.v1"
# No ACTIVE PAPER_INCUBATION_V1 record can exist (companion items 1.4-1.7): KD-13 never covers a reading.
GOVERNED_PAPER_KELLY_COVERAGE = "NOT_COVERED_NO_ACTIVE_PAPER_INCUBATION_RECORD"
# Never read, defaulted or selected here.
GOVERNED_PAPER_KELLY_PENDING_ITEMS: tuple[str, ...] = (
    "KD-7:the_100_trade_bootstrap",
    "HC-16a",
    "HC-16c",
    "HC-16d",
    "items_1.4-1.8:the_paper_incubation_record_and_its_parameters",
)
GOVERNED_PAPER_KELLY_UNREPRESENTABLE = "KELLY_VALUE_UNREPRESENTABLE"
_PREFIX = "governed_paper_kelly_reading"
_WIN, _LOSS, _ZERO = "WIN", "LOSS", "ZERO"


class GovernedPaperKellyError(EdgeArtifactError):
    """Malformed, foreign or non-authentic input: no Kelly reading is ever represented over it."""


class GovernedPaperKellyStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - reading status label, not a credential.
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


_STATUS = {
    HistoricalExecutionKellyStatus.PASS: GovernedPaperKellyStatus.PASS,
    HistoricalExecutionKellyStatus.FAIL: GovernedPaperKellyStatus.FAIL,
    HistoricalExecutionKellyStatus.BLOCKED: GovernedPaperKellyStatus.BLOCKED,
}


@dataclass(frozen=True)
class GovernedPaperKellyTrade:
    """One closed trade as the Kelly reading knows it (A1.3, KD-0, KD-10a): its class, its knowledge instant and its
    opening-fill risk, each re-proven from the sealed records. Amounts are scale-18 renderings of exact values;
    ``risk_reason`` says why ``opening_risk`` and ``outcome_r`` are absent ("" when proven)."""

    trade_id: str
    trade_digest: str
    direction: str
    opened_at_ns: int
    closed_at_ns: int
    knowledge_ns: int
    trade_class: str
    realized_net_pnl: str
    opening_fill_digest: str
    opening_mark_record_digest: str
    protection_digest: str
    stop_price: str | None
    opening_risk: str | None
    outcome_r: str | None
    risk_reason: str
    funding_record_digests: tuple[str, ...]


@dataclass(frozen=True)
class GovernedPaperKellyReading:
    """The Kelly reading of one entry decision (KD-1..KD-13 with D-A1); ``reading_digest`` covers every other field.

    ``status``/``reason``/``failures``/``blocks`` are the engine arithmetic's, plus ``KELLY_VALUE_UNREPRESENTABLE`` when a
    value cannot be recorded. ``rho`` is the candidate's FCD-01 R-4 fraction (None with ``rho_reason``). Values are
    scale-18 renderings, None where undefined; ``terms`` are the G window's ``1 + rho * R_j``, oldest first.
    """

    decision_sequence: int
    decision_time_ns: int
    target_direction: str
    status: GovernedPaperKellyStatus
    reason: str
    failures: tuple[str, ...]
    blocks: tuple[str, ...]
    coverage: str
    rho: str | None
    rho_reason: str
    known_trade_ids: tuple[str, ...]
    unknown_trade_ids: tuple[str, ...]
    window_count: int
    g_count: int
    wins: int
    losses: int
    zeros: int
    p: str | None
    mean_win: str | None
    mean_loss: str | None
    b: str | None
    f_star: str | None
    f: str | None
    f_cap: str | None
    fit_value: str | None
    terms: tuple[str, ...]
    product_exceeds_one: bool | None
    diagnostic: str | None
    reading_digest: str


@dataclass(frozen=True)
class GovernedPaperKellyEvidence:
    """The derived Kelly evidence of one governed evaluation: its trades and every entry decision's reading."""

    schema_version: str
    contract_id: str
    decision_ids: tuple[str, ...]
    method_id: str
    rule_digest: str
    outcome_digest: str
    dataset_digest: str
    economics_policy_digest: str
    position_management_policy_digest: str
    ohlc_archive_digest: str
    risk_evidence_digest: str
    instrument: str
    start_ns: int
    horizon_ns: int
    coverage: str
    pending_items: tuple[str, ...]
    trades: tuple[GovernedPaperKellyTrade, ...]
    readings: tuple[GovernedPaperKellyReading, ...]
    evidence_digest: str
    paper_only: bool = True
    execution_authorized: bool = False
    edge_proven: bool = False
    profitability_proven: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    operational_readiness: bool = False
    stage4_complete: bool = False


# --- helpers -----------------------------------------------------------------------------------------------------------


def _fail(code: str) -> GovernedPaperKellyError:
    return GovernedPaperKellyError(f"{_PREFIX}:{code}")


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


def _digest_of(payload: object) -> str:
    return edge_sha256_text(edge_canonical_json(payload))


def _visibility(record: HistoricalPitRecord) -> int | None:
    if record.finalized_at_ns is None:
        return None
    return max(record.available_at_ns, record.finalized_at_ns)


class _Unrepresentable(Exception):
    pass


def _render(value: Fraction | None) -> str | None:
    """The scale-18 rendering of a defined exact value (None stays None); outside the domain it is unrepresentable."""

    if value is None:
        return None
    rendered = historical_execution_render_amount(value)
    if rendered is None:
        raise _Unrepresentable
    return rendered


def governed_paper_kelly_rule() -> dict[str, object]:
    """The constructed methodology this module and the engine's schedule v8 apply, as canonical content."""

    return {
        "contract_id": GOVERNED_PAPER_KELLY_CONTRACT_ID,
        "decision_ids": list(GOVERNED_PAPER_KELLY_DECISION_IDS),
        "method_id": GOVERNED_PAPER_KELLY_METHOD_ID,
        "doctrine": "s1_kelly_class_completion_amendment_v1 sections 2, 4.1 and 5.1 (A1.3, KD-0 with C-1 and C-2, "
        "KD-1..KD-13) with the KD-9 of s1_kelly_da1_doctrine_adoption_v1 section 2.1; PRDV4 §0.3, §1.21, §1.28",
        "kd0": "risk_units_r_j_is_net_pnl_over_the_fcd01_r5_opening_fill_risk_rho_t_is_fcd01_r4_at_the_decision_and_r5_at_"
        "the_exposure_increasing_fill",
        "kd1_window": HISTORICAL_EXECUTION_KELLY_WINDOW,
        "kd4_decay": str(HISTORICAL_EXECUTION_KELLY_DECAY),
        "kd7_fraction_below_the_window": str(HISTORICAL_EXECUTION_KELLY_FRACTION),
        "kd7_at_the_window": "bootstrap_undecided_blocked",
        "kd8_cap": str(HISTORICAL_EXECUTION_KELLY_CAP),
        "kd9": "rho_t * max(1, Lbar) <= f_cap at the decision (R-4) and at the exposure-increasing fill (R-5), Lbar the "
        "unweighted mean of abs(R_j) over the losses of the KD-1 window; otherwise FAIL with no resize; missing or "
        "invalid evidence BLOCKED",
        "kd10_g_window": HISTORICAL_EXECUTION_KELLY_G_WINDOW,
        "kd10_domain": "every_known_outcome_1_plus_rho_r_j_gt_0_from_the_first_known_trade",
        "kd10_product": "exact_product_of_the_g_window_terms_gt_1_never_formed_or_rendered",
        "kd13": GOVERNED_PAPER_KELLY_COVERAGE,
        "failures": list(HISTORICAL_EXECUTION_KELLY_FAILURES),
        "blocks": [*HISTORICAL_EXECUTION_KELLY_BLOCKS, GOVERNED_PAPER_KELLY_UNREPRESENTABLE],
        "pending_never_read": list(GOVERNED_PAPER_KELLY_PENDING_ITEMS),
        "fill": "the_engine_schedule_v8_refuses_an_exposure_increasing_fill_whose_r5_kelly_reading_is_not_pass_whole_"
        "and_never_resized",
    }


GOVERNED_PAPER_KELLY_RULE = governed_paper_kelly_rule()
GOVERNED_PAPER_KELLY_RULE_DIGEST = _digest_of(GOVERNED_PAPER_KELLY_RULE)


# --- the trades ----------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperKellyKnownTrade:
    """The exact facts of one re-proven trade one reading consumes (in memory only, never serialized)."""

    trade_id: str
    closed_at_ns: int
    knowledge_ns: int
    realized_net_pnl: Fraction
    opening_risk: Fraction | None


def _trade_class(net: Fraction) -> str:
    return _WIN if net > 0 else _LOSS if net < 0 else _ZERO


def _opening_risk(  # noqa: PLR0911 - one linear re-derivation, every refusal named
    record: HistoricalExecutionTrade,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    records: Mapping[str, HistoricalPitRecord],
    *,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    pm_policy: HistoricalPositionManagementPolicy,
    pm_archive: HistoricalOhlcBarArchive,
) -> tuple[Fraction | None, str, dict[str, object]]:
    """KD-10a: the FCD-01 R-1 risk of the trade's opening fill, re-derived from the sealed records, or why it is not."""

    facts: dict[str, object] = {
        "opening_fill_digest": "",
        "opening_mark_record_digest": "",
        "protection_digest": "",
        "stop_price": None,
    }
    if not record.entry_fill_digests:
        return None, "opening_fill_missing", facts
    opening = record.entry_fill_digests[0]
    facts["opening_fill_digest"] = opening
    fills = [item for item in outcome.fills if item.fill_digest == opening]
    if len(fills) != 1 or fills[0].outcome not in (
        HistoricalExecutionFillOutcome.FILLED,
        HistoricalExecutionFillOutcome.PARTIALLY_FILLED,
    ):
        return None, "opening_fill_not_executed", facts
    fill = fills[0]
    if fill.fill_price is None or fill.execution_time_ns is None:
        return None, "opening_fill_not_executed", facts
    sign = 1 if record.direction == "LONG" else -1
    quantity = sign * Fraction(fill.filled_quantity)  # the grid quantity: its text is the exact value
    price = Fraction(fill.fill_price)  # the grid price: its text is the exact value
    protections = [
        item
        for item in outcome.excursion_protections
        if item.trade_id == record.trade_id and item.opening_fill_digest == opening
    ]
    if len(protections) != 1:
        return None, "protection_of_the_opening_fill_missing", facts
    protection = protections[0]
    facts["protection_digest"] = protection.protection_digest
    if Fraction(protection.basis_price) != price or protection.opened_at_ns != fill.execution_time_ns:
        return None, "protection_not_of_the_opening_fill", facts
    stop, why, _ = governed_paper_risk_protection_stop(
        protection, position_management_policy=pm_policy, position_management_archive=pm_archive
    )
    if stop is None:
        return None, f"opening_stop_unproven:{why}", facts
    facts["stop_price"] = historical_execution_render_amount(stop)
    valuations = [
        item
        for item in outcome.valuations
        if item.valuation_kind is HistoricalExecutionValuationKind.FILL and item.trigger_digest == opening
    ]
    if len(valuations) != 1 or valuations[0].mark_record_digest is None or valuations[0].mark_price is None:
        return None, "opening_fill_mark_missing", facts
    valuation = valuations[0]
    facts["opening_mark_record_digest"] = valuation.mark_record_digest
    mark_record = records.get(valuation.mark_record_digest)
    if mark_record is None:
        return None, "opening_fill_mark_not_in_the_dataset", facts
    visible = _visibility(mark_record)
    if visible is None or visible > fill.execution_time_ns:
        return None, "opening_fill_mark_not_visible_at_the_fill", facts
    values = [item.value for item in mark_record.values if item.name == economics_policy.mark_value_name]
    if len(values) != 1:
        return None, "opening_fill_mark_value_missing", facts
    mark = Fraction(values[0])
    if historical_execution_render_amount(mark) != valuation.mark_price:
        return None, "opening_fill_mark_not_the_valued_one", facts
    cost = (Fraction(economics_policy.taker_fee_bps) + Fraction(economics_policy.slippage_floor_bps)) / 10_000
    risk = governed_paper_risk_stop_risk(quantity, mark, stop, cost)
    if risk <= 0:
        return None, "opening_risk_not_positive", facts
    return risk, "", facts


def governed_paper_kelly_trades(  # noqa: C901, PLR0913 - one linear re-proof of every closed trade
    *,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    trade_exact_values: Sequence[HistoricalExecutionTradeExactValues],
    dataset: HistoricalPitDataset,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
) -> tuple[tuple[GovernedPaperKellyTrade, ...], tuple[GovernedPaperKellyKnownTrade, ...]]:
    """Every CLOSED trade of one governed re-run, re-proven against the sealed records (see the module docstring): the
    evidence records and their exact facts, in engine close order. The outcome's own digest is recomputed through the
    public serializer first (the evidence binds it). A re-run fact that disagrees with the sealed records, a reordered,
    missing or duplicate trade, or a malformed input raises ``GovernedPaperKellyError``. Pure."""

    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome or outcome.simulated is not True:
        raise _fail("governed_outcome_malformed")
    if historical_execution_governed_paper_outcome_digest(outcome) != outcome.outcome_digest:
        raise _fail("governed_outcome_digest_mismatch")
    if type(dataset) is not HistoricalPitDataset or outcome.dataset_digest != dataset.dataset_digest:
        raise _fail("dataset_not_of_the_outcome")
    if (
        type(economics_policy) is not HistoricalExecutionEconomicsPolicy
        or economics_policy.policy_digest != outcome.economics_policy_digest
    ):
        raise _fail("economics_policy_not_of_the_outcome")
    if type(position_management_policy) is not HistoricalPositionManagementPolicy or (
        type(position_management_archive) is not HistoricalOhlcBarArchive
    ):
        raise _fail("position_management_inputs_malformed")
    exact = tuple(trade_exact_values)
    if any(type(item) is not HistoricalExecutionTradeExactValues for item in exact):
        raise _fail("trade_exact_values_malformed")
    closed = [item for item in outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED]
    if [item.trade_id for item in closed] != [item.trade_id for item in exact] or len(
        {item.trade_id for item in closed}
    ) != len(closed):
        raise _fail("trade_exact_values_not_of_the_outcome")
    records = {item.record_digest: item for item in dataset.records}
    cashflows = {item.cashflow_digest: item for item in outcome.funding_cashflows}
    evidence: list[GovernedPaperKellyTrade] = []
    known: list[GovernedPaperKellyKnownTrade] = []
    previous_close = -1
    for record, values in zip(closed, exact, strict=True):
        if record.end_time_ns is None or record.end_time_ns < previous_close:
            raise _fail("trades_not_in_close_order")
        previous_close = record.end_time_ns
        if type(values.realized_net_pnl) is not Fraction or historical_execution_render_amount(
            values.realized_net_pnl
        ) != (record.realized_net_pnl):
            raise _fail("trade_net_pnl_not_of_the_record")
        funding_records: list[str] = []
        knowledge = record.end_time_ns
        for digest in record.funding_cashflow_digests:
            cashflow = cashflows.get(digest)
            source = None if cashflow is None else records.get(cashflow.funding_record_digest)
            visible = None if source is None else _visibility(source)
            if visible is None:
                raise _fail("trade_settlement_not_in_the_dataset")
            funding_records.append(source.record_digest)  # type: ignore[union-attr]
            knowledge = max(knowledge, visible)
        if values.knowledge_ns != knowledge:
            raise _fail("trade_knowledge_not_of_the_records")
        risk, reason, facts = _opening_risk(
            record,
            outcome,
            records,
            economics_policy=economics_policy,
            pm_policy=position_management_policy,
            pm_archive=position_management_archive,
        )
        if risk is not None and values.opening_risk is not None and risk != values.opening_risk:
            raise _fail("trade_opening_risk_not_of_the_records")
        if risk is not None and values.opening_risk is None:
            risk, reason = None, "opening_risk_not_measured_by_the_re_run"
        outcome_r = None if risk is None else values.realized_net_pnl / risk
        rendered_risk = None if risk is None else historical_execution_render_amount(risk)
        rendered_r = None if outcome_r is None else historical_execution_render_amount(outcome_r)
        if risk is not None and (rendered_risk is None or rendered_r is None):
            risk, reason, rendered_risk, rendered_r = None, "opening_risk_unrepresentable", None, None
        evidence.append(
            GovernedPaperKellyTrade(
                trade_id=record.trade_id,
                trade_digest=record.trade_digest,
                direction=record.direction,
                opened_at_ns=record.start_time_ns,
                closed_at_ns=record.end_time_ns,
                knowledge_ns=knowledge,
                trade_class=_trade_class(values.realized_net_pnl),
                realized_net_pnl=record.realized_net_pnl,
                opening_fill_digest=facts["opening_fill_digest"],  # type: ignore[arg-type]
                opening_mark_record_digest=facts["opening_mark_record_digest"],  # type: ignore[arg-type]
                protection_digest=facts["protection_digest"],  # type: ignore[arg-type]
                stop_price=facts["stop_price"],  # type: ignore[arg-type]
                opening_risk=rendered_risk,
                outcome_r=rendered_r,
                risk_reason=reason,
                funding_record_digests=tuple(funding_records),
            )
        )
        known.append(
            GovernedPaperKellyKnownTrade(record.trade_id, record.end_time_ns, knowledge, values.realized_net_pnl, risk)
        )
    return tuple(evidence), tuple(known)


# --- the reading -----------------------------------------------------------------------------------------------------------


def _reading_values(fit: HistoricalExecutionKellyFit) -> dict[str, object]:
    return {
        "p": _render(fit.p),
        "mean_win": _render(fit.mean_win),
        "mean_loss": _render(fit.mean_loss),
        "b": _render(fit.b),
        "f_star": _render(fit.f_star),
        "f": _render(fit.f),
        "f_cap": _render(fit.f_cap),
        "fit_value": _render(fit.fit_value),
        "terms": tuple(_render(item) for item in fit.terms),
        "diagnostic": _render(fit.diagnostic),
    }


def build_governed_paper_kelly_reading(  # noqa: PLR0913
    *,
    decision_sequence: int,
    decision_time_ns: int,
    target_direction: str,
    trades: Sequence[GovernedPaperKellyKnownTrade],
    rho: Fraction | None,
    rho_reason: str,
) -> GovernedPaperKellyReading:
    """The Kelly reading of one entry decision at ``decision_time_ns`` on the re-proven trades of its evaluation (in
    engine close order): the trades known by then, the closed but not yet known ones, the candidate's exact FCD-01 R-4
    ``rho`` (None with ``rho_reason``) and the engine's one exact arithmetic (module docstring). Pure."""

    for value, name in ((decision_sequence, "decision_sequence"), (decision_time_ns, "decision_time_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if target_direction not in ("LONG", "SHORT"):
        raise _fail("target_direction_invalid")
    if rho is not None and type(rho) is not Fraction:
        raise _fail("rho_malformed")
    if type(rho_reason) is not str or (rho is None) is (rho_reason == ""):
        raise _fail("rho_reason_malformed")
    items = tuple(trades)
    if any(type(item) is not GovernedPaperKellyKnownTrade for item in items):
        raise _fail("trades_malformed")
    closed = [item for item in items if item.closed_at_ns <= decision_time_ns]
    known = [item for item in closed if item.knowledge_ns <= decision_time_ns]
    unknown = [item for item in closed if item.knowledge_ns > decision_time_ns]
    fit = historical_execution_kelly_fit(
        tuple((item.realized_net_pnl, item.opening_risk) for item in known),
        unknown_count=len(unknown),
        rho=rho,
    )
    status, reason = _STATUS[fit.status], fit.reason
    failures, blocks = fit.failures, fit.blocks
    try:
        rendered_rho = _render(rho)
        values = _reading_values(fit)
    except _Unrepresentable:
        rendered_rho = historical_execution_render_amount(rho) if rho is not None else None
        values = dict.fromkeys(("p", "mean_win", "mean_loss", "b", "f_star", "f", "f_cap", "fit_value"))
        values.update(terms=(), diagnostic=None)
        blocks = (*blocks, GOVERNED_PAPER_KELLY_UNREPRESENTABLE)
        if status is GovernedPaperKellyStatus.PASS:
            status, reason = GovernedPaperKellyStatus.BLOCKED, GOVERNED_PAPER_KELLY_UNREPRESENTABLE
    seed = GovernedPaperKellyReading(
        decision_sequence=decision_sequence,
        decision_time_ns=decision_time_ns,
        target_direction=target_direction,
        status=status,
        reason=reason,
        failures=failures,
        blocks=blocks,
        coverage=GOVERNED_PAPER_KELLY_COVERAGE,
        rho=rendered_rho,
        rho_reason=rho_reason,
        known_trade_ids=tuple(item.trade_id for item in known),
        unknown_trade_ids=tuple(item.trade_id for item in unknown),
        window_count=fit.window_count,
        g_count=fit.g_count,
        wins=fit.wins,
        losses=fit.losses,
        zeros=fit.zeros,
        product_exceeds_one=fit.product_exceeds_one,
        reading_digest="",
        **values,  # type: ignore[arg-type]
    )
    return replace(seed, reading_digest=governed_paper_kelly_reading_digest(seed))


def governed_paper_kelly_reading_digest(reading: GovernedPaperKellyReading) -> str:
    """Recompute the canonical reading digest, excluding only ``reading_digest``."""

    return edge_payload_digest(_to_payload(reading), "reading_digest")


# --- the evidence ------------------------------------------------------------------------------------------------------


def _canonical_decisions(decisions: object, start_ns: int, horizon_ns: int) -> tuple[tuple[int, int, str], ...]:
    if type(decisions) is not tuple:
        raise _fail("decisions_malformed")
    previous: tuple[int, int] | None = None
    for item in decisions:
        if (
            type(item) is not tuple
            or len(item) != 3  # noqa: PLR2004 - (sequence, instant, direction)
            or not historical_execution_wire_int_is_valid(item[0], minimum=0)
            or not historical_execution_wire_int_is_valid(item[1], minimum=0)
            or item[2] not in ("LONG", "SHORT")
        ):
            raise _fail("decisions_malformed")
        if not start_ns <= item[1] < horizon_ns:
            raise _fail("decision_outside_the_evaluation_horizon")
        if previous is not None and (item[0] <= previous[0] or item[1] < previous[1]):
            raise _fail("decisions_not_ordered")
        previous = (item[0], item[1])
    return decisions  # type: ignore[return-value]


def derive_governed_paper_kelly_evidence(  # noqa: PLR0913
    *,
    decisions: tuple[tuple[int, int, str], ...],
    outcome: HistoricalExecutionGovernedPaperOutcome,
    trade_exact_values: Sequence[HistoricalExecutionTradeExactValues],
    dataset: HistoricalPitDataset,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
    fractions: Mapping[int, tuple[Fraction | None, str]],
    risk_evidence_digest: str,
    instrument: str,
    start_ns: int,
    horizon_ns: int,
) -> GovernedPaperKellyEvidence:
    """The Kelly evidence of one governed evaluation: the re-proven trades of its one engine re-run and the reading of
    every entry decision ``(sequence, instant, direction)`` at its exact FCD-01 R-4 fraction ``fractions[sequence]``
    (``governed_paper_risk_entry_fraction``, derived by the caller from the same re-run). Pure."""

    for value, name in ((start_ns, "start_ns"), (horizon_ns, "horizon_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if horizon_ns <= start_ns:
        raise _fail("evaluation_horizon_invalid")
    entries = _canonical_decisions(decisions, start_ns, horizon_ns)
    if type(instrument) is not str or instrument != outcome.instrument:  # type: ignore[union-attr]
        raise _fail("instrument_not_of_the_outcome")
    if type(risk_evidence_digest) is not str or len(risk_evidence_digest) != 64:  # noqa: PLR2004 - a SHA-256 hex digest
        raise _fail("risk_evidence_digest_malformed")
    if not isinstance(fractions, Mapping) or any(item[0] not in fractions for item in entries):
        raise _fail("entry_fractions_malformed")
    trades, known = governed_paper_kelly_trades(
        outcome=outcome,
        trade_exact_values=trade_exact_values,
        dataset=dataset,
        economics_policy=economics_policy,
        position_management_policy=position_management_policy,
        position_management_archive=position_management_archive,
    )
    readings = tuple(
        build_governed_paper_kelly_reading(
            decision_sequence=sequence,
            decision_time_ns=instant,
            target_direction=direction,
            trades=known,
            rho=fractions[sequence][0],
            rho_reason=fractions[sequence][1],
        )
        for sequence, instant, direction in entries
    )
    seed = GovernedPaperKellyEvidence(
        schema_version=GOVERNED_PAPER_KELLY_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_KELLY_CONTRACT_ID,
        decision_ids=GOVERNED_PAPER_KELLY_DECISION_IDS,
        method_id=GOVERNED_PAPER_KELLY_METHOD_ID,
        rule_digest=GOVERNED_PAPER_KELLY_RULE_DIGEST,
        outcome_digest=outcome.outcome_digest,
        dataset_digest=dataset.dataset_digest,
        economics_policy_digest=economics_policy.policy_digest,
        position_management_policy_digest=position_management_policy.policy_digest,
        ohlc_archive_digest=position_management_archive.archive_digest,
        risk_evidence_digest=risk_evidence_digest,
        instrument=instrument,
        start_ns=start_ns,
        horizon_ns=horizon_ns,
        coverage=GOVERNED_PAPER_KELLY_COVERAGE,
        pending_items=GOVERNED_PAPER_KELLY_PENDING_ITEMS,
        trades=trades,
        readings=readings,
        evidence_digest="",
    )
    return replace(seed, evidence_digest=governed_paper_kelly_evidence_digest(seed))


def governed_paper_kelly_evidence_to_dict(evidence: GovernedPaperKellyEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping of the evidence, including its self-digest."""

    return _to_payload(evidence)


def governed_paper_kelly_evidence_digest(evidence: GovernedPaperKellyEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), "evidence_digest")


_PREFIX_TRADE_FIELDS = ("direction", "opened_at_ns", "closed_at_ns", "knowledge_ns", "trade_class", "realized_net_pnl")
_PREFIX_TRADE_VALUES = ("stop_price", "opening_risk", "outcome_r", "risk_reason")
_PREFIX_READING_EXCLUDED = ("known_trade_ids", "unknown_trade_ids", "reading_digest")


def governed_paper_kelly_prefix_digest(evidence: GovernedPaperKellyEvidence, *, before_ns: int) -> str:
    """The run-independent X1 content before ``before_ns``: the method, every trade known before it and every reading of
    a decision before it, without the identifiers the re-run derives (trade, fill and record ids). A later seal of the
    lineage re-derives it unchanged: nothing known before ``before_ns`` ever changes. Pure."""

    if type(evidence) is not GovernedPaperKellyEvidence:
        raise _fail("evidence_malformed")
    if not historical_execution_wire_int_is_valid(before_ns, minimum=0):
        raise _fail("prefix_instant_invalid")
    trades = [
        {name: getattr(item, name) for name in (*_PREFIX_TRADE_FIELDS, *_PREFIX_TRADE_VALUES)}
        for item in evidence.trades
        if item.knowledge_ns < before_ns
    ]
    readings = [
        {key: value for key, value in _to_payload(item).items() if key not in _PREFIX_READING_EXCLUDED}
        | {"known_trade_count": len(item.known_trade_ids), "unknown_trade_count": len(item.unknown_trade_ids)}
        for item in evidence.readings
        if item.decision_time_ns < before_ns
    ]
    payload = {
        "schema_version": evidence.schema_version,
        "method_id": evidence.method_id,
        "rule_digest": evidence.rule_digest,
        "decision_ids": list(evidence.decision_ids),
        "coverage": evidence.coverage,
        "trades": trades,
        "readings": readings,
    }
    return _digest_of(payload)


def governed_paper_kelly_status_of(reading: GovernedPaperKellyReading) -> GovernedPaperKellyStatus:
    """The status of an authentic reading (its digest re-proven), for a consumer such as SCALE-1."""

    if type(reading) is not GovernedPaperKellyReading or governed_paper_kelly_reading_digest(reading) != (
        reading.reading_digest
    ):
        raise _fail("reading_not_authentic")
    return reading.status


__all__ = [
    "GOVERNED_PAPER_KELLY_CONTRACT_ID",
    "GOVERNED_PAPER_KELLY_COVERAGE",
    "GOVERNED_PAPER_KELLY_DECISION_IDS",
    "GOVERNED_PAPER_KELLY_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_KELLY_METHOD_ID",
    "GOVERNED_PAPER_KELLY_PENDING_ITEMS",
    "GOVERNED_PAPER_KELLY_RULE",
    "GOVERNED_PAPER_KELLY_RULE_DIGEST",
    "GOVERNED_PAPER_KELLY_UNREPRESENTABLE",
    "GovernedPaperKellyError",
    "GovernedPaperKellyEvidence",
    "GovernedPaperKellyKnownTrade",
    "GovernedPaperKellyReading",
    "GovernedPaperKellyStatus",
    "GovernedPaperKellyTrade",
    "build_governed_paper_kelly_reading",
    "derive_governed_paper_kelly_evidence",
    "governed_paper_kelly_evidence_digest",
    "governed_paper_kelly_evidence_to_dict",
    "governed_paper_kelly_prefix_digest",
    "governed_paper_kelly_reading_digest",
    "governed_paper_kelly_rule",
    "governed_paper_kelly_status_of",
    "governed_paper_kelly_trades",
]
