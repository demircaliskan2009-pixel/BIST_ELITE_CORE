"""Governed paper Kelly reading (S1_KELLY_DEFINED_READING_CONSTRUCTION_V1): RECORD A's KD-1..KD-13 with D-A1, constructed.

Design authority: ``docs/crypto_core/s1_kelly_class_completion_amendment_v1.md`` (RECORD A: A1.3, the doctrine reading
KD-0 with the clarification C-1 and C-2, and the approved methodology KD-1..KD-13) and
``docs/crypto_core/s1_kelly_da1_doctrine_adoption_v1.md`` (the KD-9 of the human decision ``S1_KELLY_DA1_DECISION_V1``),
read with PRDV4 §0.3, §1.21 and §1.28 and the FCD-01 of ``docs/crypto_core/s1_native_risk_measurement_doctrine_adoption_v1.md``.
Paper-only, deterministic, point-in-time and fail-closed. It creates no order, sizes nothing and authorizes no entry.

Authority (S1_KELLY_PUBLIC_PROVENANCE_REPAIR_V1). Every reading is derived, never accepted, from the replay authority
of its evaluation: the engine result and the caller's anchor (``result``, ``expected_result_digest``), the same authority
``verify_governed_paper_outcome`` re-proves an outcome against. Both public producers re-run the ONE governed engine
derivation under the supplied outcome's own schedule (``simulate_historical_execution_governed_paper_derivation``: the
engine re-proves the result by recomputation from its own bindings against the anchor, then re-runs it). The supplied
outcome must be that replay's outcome, field for field, and every supplied exact trade fact
(``HistoricalExecutionTradeExactValues``) must equal the replay's own exact value: exact rationals, never a rendering, and
never joined by a label. Only the replay's own facts are read after that. The dataset, the economics and
position-management policies and the OHLC archive are re-proven by their public verifiers and must recompute to the
digests the authenticated result binds. The decisions are the authenticated run's own (the run the result binds), and
each entry's FCD-01 R-4 stop-risk fraction is derived here, from the evaluation's re-proven risk context over the same
replay (``governed_paper_risk_entry_fraction``, the computation NT-R03 renders). A self-digest, a matching rendering or
a matching identifier authenticates nothing: a supplied fact that is not the replay's is ``GovernedPaperKellyError``.

Trades (A1.3, KD-0, KD-10a). Every CLOSED excursion of the re-run, in engine close order, is a trade. Its exact realized net
PnL must render to the trade record's own, and its class is the sign of that PnL (win, loss or zero). Its knowledge instant
is the later of its closing fill and the visibility of the final rate of every settlement it carries, read from the
dataset's funding records, and must equal the re-run's. Its risk ``Risk_j`` is recomputed here from the sealed opening fill:
the executed price and filled quantity of its first entry fill, the milestone-0 stop that fill armed (the protection record
re-derived exactly: the basis on the price grid and the ATR re-computed at its own decision instant), the fill-instant mark
(the mark record of the fill's own valuation, visible at the fill) and the policy's taker fee plus slippage floor, by the
FCD-01 R-1 formula; it must equal the replay's own R-5 measurement exactly. ``R_j = net_j / Risk_j`` exists only for a proven
positive risk; a missing, unmeasured, unreproducible, publication-invisible or non-positive one leaves ``R_j`` unproven. A
replay fact that does not agree with the sealed records is not an input: ``GovernedPaperKellyError``.

Reading. At an entry decision at ``t`` the known trades are those known at or before ``t``; a trade closed by ``t`` but not
yet known keeps the windows undefined. The candidate's ``rho_t`` is its FCD-01 R-4 fraction. The one exact arithmetic is the
engine's ``historical_execution_kelly_fit`` (KD-1..KD-12 with the D-A1 Alternative 1 fit ``rho_t * max(1, Lbar) <= f_cap``),
the same the engine's schedule v8 applies at the R-5 fill. Coverage (KD-13) needs an ACTIVE PAPER_INCUBATION_V1 record,
and none can exist (companion items 1.4-1.7 are pending): no reading is ever covered, so a class-incomplete window is
``KELLY_RATIO_UNDEFINED`` (BLOCKED), never COLD_START_EXCEPTED. An incubation lineage (``cold_start=True``) also records each reading's KD-13 at its R-4 fraction
(``historical_execution_kelly_cold_start``); every other lineage's readings and evidence keep their bytes. The undecided
100-trade bootstrap (KD-7) and HC-16a, HC-16c
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
    edge_authority_binding_snapshot,
    edge_canonical_json,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_risk_measurement import (
    GovernedPaperRiskContext,
    GovernedPaperRiskError,
    derive_governed_paper_risk_market,
    governed_paper_risk_entry_fraction,
    governed_paper_risk_protection_stop,
    governed_paper_risk_stop_risk,
)
from crypto_core.validation.historical_decision_run import HistoricalDecisionRun, historical_decision_run_from_payload
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_KELLY_BLOCKS,
    HISTORICAL_EXECUTION_KELLY_CAP,
    HISTORICAL_EXECUTION_KELLY_DECAY,
    HISTORICAL_EXECUTION_KELLY_FAILURES,
    HISTORICAL_EXECUTION_KELLY_FRACTION,
    HISTORICAL_EXECUTION_KELLY_G_WINDOW,
    HISTORICAL_EXECUTION_KELLY_WINDOW,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionEconomicsResult,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionGovernedPaperDerivation,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionKellyFit,
    HistoricalExecutionKellyStatus,
    HistoricalExecutionTrade,
    HistoricalExecutionTradeExactValues,
    HistoricalExecutionTradeStatus,
    HistoricalExecutionValuationKind,
    historical_execution_kelly_cold_start,
    historical_execution_kelly_fit,
    simulate_historical_execution_governed_paper_derivation,
)
from crypto_core.validation.historical_execution_economics_policy import (
    HistoricalExecutionEconomicsPolicy,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
    verify_historical_execution_economics_policy,
)
from crypto_core.validation.historical_ohlc_bar_archive import (
    HistoricalOhlcBarArchive,
    verify_historical_ohlc_bar_archive,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    verify_historical_pit_dataset,
)
from crypto_core.validation.historical_position_management_policy import (
    HistoricalPositionManagementPolicy,
    verify_historical_position_management_policy,
)

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
    # Incubation lineages only (S1_PAPER_INCUBATION_RECORD_V1_CONSTRUCTION): RECORD A's KD-13 at the decision's R-4
    # fraction, as if the reading were covered; whether it is covered is the incubation evidence's decision. Empty, and
    # absent from the payload, on every other lineage, so every v12 reading keeps its bytes.
    cold_start_status: str = ""
    cold_start_reason: str = ""


@dataclass(frozen=True)
class GovernedPaperKellyEvidence:
    """The derived Kelly evidence of one governed evaluation: its trades and every entry decision's reading.

    Every digest names an authenticated authority: the replay's outcome and the result it re-proved against the caller's
    anchor, the re-proven dataset, policies and archive the result binds, and the re-proven risk context the R-4
    fractions read (its policy, approval, MARK archive and the approval table that admitted it or not).
    """

    schema_version: str
    contract_id: str
    decision_ids: tuple[str, ...]
    method_id: str
    rule_digest: str
    outcome_digest: str
    baseline_result_digest: str
    dataset_digest: str
    economics_policy_digest: str
    position_management_policy_digest: str
    ohlc_archive_digest: str
    risk_policy_digest: str
    risk_approval_digest: str
    risk_archive_digest: str
    risk_approval_table_id: str
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


_COLD_START_FIELDS = ("cold_start_status", "cold_start_reason")


def _to_payload(artifact: object) -> dict[str, object]:
    payload = {item.name: _serialize(getattr(artifact, item.name)) for item in fields(artifact)}  # type: ignore[arg-type]
    if isinstance(artifact, GovernedPaperKellyReading) and not artifact.cold_start_status:
        for name in _COLD_START_FIELDS:
            del payload[name]
    return payload


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
        "provenance": "the_replay_authority_result_and_anchor_re_proven_by_the_engine_the_supplied_outcome_equal_to_the_"
        "replay_field_for_field_every_supplied_exact_trade_fact_equal_to_the_replay_exactly_inputs_re_proven_to_the_"
        "result_bindings_decisions_from_the_authenticated_run_r4_fractions_derived_from_the_re_proven_risk_context",
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


@dataclass(frozen=True)
class _Replay:
    """The authenticated replay of one evaluation (in memory only): the ONE engine derivation re-run from the replay
    authority, the result the engine re-proved against the anchor, and the decision run that result binds."""

    derivation: HistoricalExecutionGovernedPaperDerivation
    result: HistoricalExecutionEconomicsResult
    run: HistoricalDecisionRun


def _authenticated_replay(  # noqa: PLR0913 - the replay authority and every input bound to it
    *,
    result: object,
    expected_result_digest: object,
    outcome: object,
    trade_exact_values: object,
    dataset: object,
    economics_policy: object,
    position_management_policy: object,
    position_management_archive: object,
) -> _Replay:
    """Authenticate a supplied governed outcome and its exact trade facts against their replay authority.

    The engine re-proves ``result`` against the caller's anchor (recomputed from its own run, policy and dataset
    bindings) and re-runs it under the supplied outcome's own schedule: ONE derivation gives the outcome and the exact
    Kelly inputs of every closed trade. The supplied outcome must be that outcome field for field, and the supplied exact
    facts must equal its exact values exactly, in order. The dataset, policies and archive must recompute, through their
    public verifiers, to the digests the authenticated result binds. Anything else raises ``GovernedPaperKellyError``
    before any evidence exists; nothing supplied is read afterwards.
    """

    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome or outcome.simulated is not True:
        raise _fail("governed_outcome_malformed")
    try:
        exact = tuple(trade_exact_values)  # type: ignore[arg-type]
    except TypeError as exc:
        raise _fail("trade_exact_values_malformed") from exc
    if any(type(item) is not HistoricalExecutionTradeExactValues for item in exact):
        raise _fail("trade_exact_values_malformed")
    try:  # the engine re-proves the result against the anchor, then re-runs it: never a supplied fact
        derivation = simulate_historical_execution_governed_paper_derivation(
            result,  # type: ignore[arg-type]
            expected_result_digest=expected_result_digest,  # type: ignore[arg-type]
            schedule=outcome.schedule,
        )
    except HistoricalExecutionEconomicsError as exc:
        raise _fail("replay_authority_rejected") from exc
    if derivation.outcome.simulated is not True or derivation.outcome != outcome:
        raise _fail("governed_outcome_not_the_authenticated_replay")
    if exact != derivation.trade_exact_values:  # exact rationals, in close order: never a rendering or a label
        raise _fail("trade_exact_values_not_of_the_authenticated_replay")
    authentic: HistoricalExecutionEconomicsResult = result  # type: ignore[assignment] - re-proven by the engine above
    for verify, value, expected, code in (
        (verify_historical_pit_dataset, dataset, authentic.dataset_digest, "dataset_not_of_the_replay"),
        (
            verify_historical_execution_economics_policy,
            economics_policy,
            authentic.economics_policy_digest,
            "economics_policy_not_of_the_replay",
        ),
        (
            verify_historical_position_management_policy,
            position_management_policy,
            authentic.position_management_policy_digest,
            "position_management_policy_not_of_the_replay",
        ),
        (
            verify_historical_ohlc_bar_archive,
            position_management_archive,
            authentic.ohlc_archive_digest,
            "ohlc_archive_not_of_the_replay",
        ),
    ):
        verification = verify(value)  # total: a malformed or forged input is never intact or never the bound digest
        if not verification.intact or verification.recomputed_digest != expected:
            raise _fail(code)
    try:  # the run the authenticated result binds (the engine re-proved it against the binding's anchor)
        run = historical_decision_run_from_payload(edge_authority_binding_snapshot(authentic.run_binding))
    except Exception as exc:  # noqa: BLE001 - an underivable run is never read
        raise _fail("replay_run_not_derivable") from exc
    if run.run_digest != authentic.run_digest:  # pragma: no cover - the engine re-proved this binding
        raise _fail("replay_run_not_derivable")
    return _Replay(derivation, authentic, run)


def governed_paper_kelly_trades(  # noqa: PLR0913 - the replay authority and every input bound to it
    *,
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    trade_exact_values: Sequence[HistoricalExecutionTradeExactValues],
    dataset: HistoricalPitDataset,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
) -> tuple[tuple[GovernedPaperKellyTrade, ...], tuple[GovernedPaperKellyKnownTrade, ...]]:
    """Every CLOSED trade of one authenticated governed replay, re-proven against the sealed records (see the module
    docstring): the evidence records and their exact facts, in engine close order.

    ``result`` and ``expected_result_digest`` are the replay authority; ``outcome`` and ``trade_exact_values`` are claims
    that must be that replay's own (``_authenticated_replay``), and only the replay's own facts are read. A non-authentic
    authority, a supplied fact that is not the replay's, an input that is not the one the result binds, or a replay fact
    that disagrees with the sealed records raises ``GovernedPaperKellyError``. Pure.
    """

    replay = _authenticated_replay(
        result=result,
        expected_result_digest=expected_result_digest,
        outcome=outcome,
        trade_exact_values=trade_exact_values,
        dataset=dataset,
        economics_policy=economics_policy,
        position_management_policy=position_management_policy,
        position_management_archive=position_management_archive,
    )
    return _reproven_trades(
        replay.derivation,
        dataset=dataset,
        economics_policy=economics_policy,
        position_management_policy=position_management_policy,
        position_management_archive=position_management_archive,
    )


def _reproven_trades(  # noqa: C901 - one linear re-proof of every closed trade
    derivation: HistoricalExecutionGovernedPaperDerivation,
    *,
    dataset: HistoricalPitDataset,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
) -> tuple[tuple[GovernedPaperKellyTrade, ...], tuple[GovernedPaperKellyKnownTrade, ...]]:
    """The re-proof of an AUTHENTICATED replay's closed trades against its sealed records (every input already bound)."""

    outcome = derivation.outcome
    exact = derivation.trade_exact_values
    closed = [item for item in outcome.trades if item.status is HistoricalExecutionTradeStatus.CLOSED]
    if [item.trade_id for item in closed] != [item.trade_id for item in exact] or len(
        {item.trade_id for item in closed}
    ) != len(closed):  # pragma: no cover - one replay gives both, in close order
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
    cold_start: bool = False,
) -> GovernedPaperKellyReading:
    """The Kelly reading of one entry decision at ``decision_time_ns`` on the re-proven trades of its evaluation (in
    engine close order): the trades known by then, the closed but not yet known ones, the candidate's exact FCD-01 R-4
    ``rho`` (None with ``rho_reason``) and the engine's one exact arithmetic (module docstring). Pure.

    This is the KD arithmetic over the facts it is given, and it carries no provenance of its own: a reading is evidence
    only inside ``derive_governed_paper_kelly_evidence``, which derives its trades and fraction from the authenticated
    replay, and the entry gate reads only that derived evidence.
    """

    for value, name in ((decision_sequence, "decision_sequence"), (decision_time_ns, "decision_time_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if target_direction not in ("LONG", "SHORT"):
        raise _fail("target_direction_invalid")
    if rho is not None and type(rho) is not Fraction:
        raise _fail("rho_malformed")
    if type(rho_reason) is not str or (rho is None) is (rho_reason == ""):
        raise _fail("rho_reason_malformed")
    if type(cold_start) is not bool:
        raise _fail("cold_start_flag_malformed")
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
    cold_status, cold_reason = historical_execution_kelly_cold_start(fit, rho) if cold_start else ("", "")
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
        cold_start_status=cold_status,
        cold_start_reason=cold_reason,
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


def derive_governed_paper_kelly_evidence(  # noqa: PLR0913 - the replay authority, its bound inputs and the span
    *,
    result: HistoricalExecutionEconomicsResult,
    expected_result_digest: str,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    trade_exact_values: Sequence[HistoricalExecutionTradeExactValues],
    dataset: HistoricalPitDataset,
    economics_policy: HistoricalExecutionEconomicsPolicy,
    position_management_policy: HistoricalPositionManagementPolicy,
    position_management_archive: HistoricalOhlcBarArchive,
    risk: GovernedPaperRiskContext,
    instrument: str,
    start_ns: int,
    horizon_ns: int,
    cold_start: bool = False,
) -> GovernedPaperKellyEvidence:
    """The Kelly evidence of one governed evaluation, derived from its authenticated replay (module docstring).

    ``cold_start=True`` (an incubation lineage only) also records each reading's RECORD A KD-13 at its R-4 fraction
    (``historical_execution_kelly_cold_start``); otherwise every reading and the evidence keep their v12 bytes.

    The supplied outcome and exact trade facts must be the replay's own (``_authenticated_replay``). The trades are the
    replay's closed trades re-proven against the sealed records. The entry decisions are every LONG/SHORT decision of
    the run the authenticated result binds, each inside ``[start_ns, horizon_ns)``, and each is read at the exact FCD-01
    R-4 fraction derived here from the re-proven ``risk`` context over the same replay
    (``governed_paper_risk_entry_fraction``; an approval the active table does not admit gives no fraction). Nothing
    else supplied is read. A non-authentic or foreign input raises ``GovernedPaperKellyError``. Pure.
    """

    for value, name in ((start_ns, "start_ns"), (horizon_ns, "horizon_ns")):
        if not historical_execution_wire_int_is_valid(value, minimum=0):
            raise _fail(f"{name}_invalid")
    if horizon_ns <= start_ns:
        raise _fail("evaluation_horizon_invalid")
    replay = _authenticated_replay(
        result=result,
        expected_result_digest=expected_result_digest,
        outcome=outcome,
        trade_exact_values=trade_exact_values,
        dataset=dataset,
        economics_policy=economics_policy,
        position_management_policy=position_management_policy,
        position_management_archive=position_management_archive,
    )
    derived = replay.derivation.outcome
    if type(instrument) is not str or instrument != derived.instrument:
        raise _fail("instrument_not_of_the_replay")
    entries = _canonical_decisions(
        tuple(
            (item.decision_sequence, item.decision_time_ns, item.resulting_direction)
            for item in replay.run.decisions
            if item.resulting_direction in ("LONG", "SHORT")
        ),
        start_ns,
        horizon_ns,
    )
    snapshots = {item.decision_sequence: item for item in replay.derivation.portfolio.snapshots}
    exact_values = {item.decision_sequence: item for item in replay.derivation.exact_values}
    try:  # the evaluation's risk context, re-proven by the market derivation; the fractions read the same replay
        market = derive_governed_paper_risk_market(
            risk, dataset=dataset, instrument=instrument, start_ns=start_ns, horizon_ns=horizon_ns
        )
        fractions = {
            sequence: governed_paper_risk_entry_fraction(
                market,
                instant,
                snapshot=snapshots.get(sequence),
                exact=exact_values.get(sequence),
                outcome=derived,
                economics_policy=economics_policy,
                position_management_policy=position_management_policy,
                position_management_archive=position_management_archive,
            )
            for sequence, instant, _ in entries
        }
    except GovernedPaperRiskError as exc:
        raise _fail("risk_market_not_derivable") from exc
    if market.dataset_digest != replay.result.dataset_digest:  # pragma: no cover - the same re-proven dataset
        raise _fail("risk_market_not_of_the_replay")
    trades, known = _reproven_trades(
        replay.derivation,
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
            cold_start=cold_start is True,
        )
        for sequence, instant, direction in entries
    )
    seed = GovernedPaperKellyEvidence(
        schema_version=GOVERNED_PAPER_KELLY_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_KELLY_CONTRACT_ID,
        decision_ids=GOVERNED_PAPER_KELLY_DECISION_IDS,
        method_id=GOVERNED_PAPER_KELLY_METHOD_ID,
        rule_digest=GOVERNED_PAPER_KELLY_RULE_DIGEST,
        outcome_digest=derived.outcome_digest,
        baseline_result_digest=derived.baseline_result_digest,
        dataset_digest=derived.dataset_digest,
        economics_policy_digest=derived.economics_policy_digest,
        position_management_policy_digest=replay.result.position_management_policy_digest,  # type: ignore[arg-type]
        ohlc_archive_digest=replay.result.ohlc_archive_digest,  # type: ignore[arg-type]
        risk_policy_digest=market.policy_digest,
        risk_approval_digest=market.approval_digest,
        risk_archive_digest=market.archive_digest,
        risk_approval_table_id=market.approval_table_id,
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
