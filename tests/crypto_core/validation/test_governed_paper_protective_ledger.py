"""Governed paper protective obligation ledger v2 tests (S1_PROTECTIVE_OBLIGATION_LEDGER_V2_ENGINE_CONSTRUCTION_V1):
schedule v6 and outcome v4, the v2 ledger, rule set v9, seal v10 and evidence v10.

SYNTHETIC TEST VALUES ONLY. Every world, policy, approval, anchor, proof, reading, price and instant here is a synthetic
fixture that exercises structure. None is a calibrated threshold, a qualified source, an approved integrity verifier or
anchor, an approved DEC-1 grant or a real human decision. The TEST-ONLY integrity approval table is installed only where
a test says so; the PRODUCTION table admits no anchor and stays in force everywhere else. No test computes, defaults or
asserts a TARGET path (HC-11c), an impact measure (HC-11f) or a participation method (HD-04): each stays undefined.

It proves:

* A. the engine's schedule v6: its halt and flatten windows exist only on schedule v6 and never in a legacy payload; a
  flatten child is the whole remaining position, close-only, through the one fill model (latency, next book, depth cap,
  fee, transition and trade ledgers), needs a DEC-1 protective window at its instant and at its fill, re-derives the
  remainder of a partial fill, retries at least 30 s after a book rejection, stays pending across a replay's end (the
  prefix excludes it by its instant) and never reverses a position; the halt refuses every later exposure increase,
  an in-flight entry at its fill included; a v1 STOP or MAX_HOLD obligation keeps precedence, at the same instant too;
* A2. the v1 handoff: a v1 obligation due while a child is in flight waits only for that child, and when the child
  resolves without closing the position (refused by its governed authority, rejected by its book or filled in part) it
  is attempted at that resolution instant under v1's own window and book rules, never at the child's resume instant or
  30 s retry, with one MAX_HOLD trigger, one order in flight and no further child; equal instants keep one deterministic
  order, the repaired path replays byte-identically from its proofs and refuses tampering, and v1 alone and the filled
  and partial children keep the audited head's identities;
* B. the ledger: IR-2 proofs are admitted only by an independent verifier against an admitted anchor (the production
  table admits none; a self-report, the pending operator channel, a foreign, late, forged or unordered proof never
  proves); KS3_CLOSE from the authentic kill-switch ladder and SS3_CLOSE from authentic system-state readings open
  nonurgent obligations that record CAP_UNPROVEN, keep their deadline and record UNFULFILLED (CAP_UNPROVEN or
  V1_PRECEDENCE), never send a child and discharge only on a verified zero position; a joining kind appends MERGED
  (D_eff never later, earlier events unchanged, no TARGET anywhere) and a repeat appends nothing; an integrity flatten
  records CHILD_SENT, CHILD_FILLED, BOOK_UNAVAILABLE, AUTHORITY_UNPROVEN, INTEGRITY_UNPROVEN and its unfulfilled
  deadline with the first failing link; the chain, the anchor and the prefix are content-stable and tamper-evident;
* C. rule set v9: only PROTECTIVE-LEDGER is added; it FAILs while an obligation is open or a halt is proven and PASSes
  otherwise; every v1-v8 identity is unchanged and malformed facts are refused;
* D. world G's protective ledger lineage (seal v10, evidence v10): without a proof every day changes only its version,
  its schedule version, its rule set and its ledger bindings, and the public gate replays the sealed ledger; a lineage
  holds a ledger from day 0 or never; a proof binds its halt and flatten window, stays append-only, is known inside its
  day and never verifies on the production table; and, under TEST-ONLY permissive entry and sizing tables only, a
  proven KS4 trigger flattens world G's open SHORT through one close-only child in flight across two seals, projected
  onto the generic chain, while the later entry is halted at the gate; when a later SS4 proof ends that child's flatten
  authority before its fill, the MAX_HOLD obligation due meanwhile is attempted at the child's refusal, pends across a
  seal and closes the SHORT, every seal re-verifies and every resealed day is refused.
"""

from __future__ import annotations

import contextlib
import functools
from collections.abc import Iterator
from dataclasses import replace
from fractions import Fraction

import pytest

import crypto_core.validation.governed_paper_ctr_qualification as ctr
import crypto_core.validation.governed_paper_entry_safety as entry_safety
import crypto_core.validation.governed_paper_protective_ledger as ledger_module
import crypto_core.validation.governed_paper_regime_state as regime
import crypto_core.validation.governed_paper_sizing_chain as sizing_module
from crypto_core.validation.edge_artifact_core import edge_payload_digest
from crypto_core.validation.governed_admitted_variant_paper_execution import (
    GovernedPaperDaySealStatus,
    GovernedPaperExecutionStatus,
    build_governed_paper_day_seal,
    build_governed_paper_execution_evidence,
    governed_paper_day_seal_to_dict,
    verify_governed_paper_execution_evidence,
)
from crypto_core.validation.governed_paper_entry_safety import (
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_DIGEST,
    GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_ID,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET,
    GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST,
    GovernedPaperEntrySafetyError,
    GovernedPaperEntrySafetyPortfolio,
    GovernedPaperEntrySafetyProtectiveLedger,
    GovernedPaperEntrySafetyStatus,
    build_governed_paper_entry_safety_evidence,
    evaluate_governed_paper_entry_safety,
    governed_paper_entry_safety_evidence_to_dict,
    governed_paper_entry_safety_rule_set,
    governed_paper_entry_safety_rule_set_digest,
)
from crypto_core.validation.governed_paper_execution_authority import (
    GovernedPaperApprovalKind,
    build_governed_paper_cycle_authority,
)
from crypto_core.validation.governed_paper_kill_switch import (
    derive_governed_paper_kill_switch_ladder,
    governed_paper_kill_switch_ladder_digest,
)
from crypto_core.validation.governed_paper_protective_ledger import (
    GOVERNED_PAPER_INTEGRITY_PRODUCTION_APPROVAL_TABLE,
    GOVERNED_PAPER_UNFULFILLED_PROTECTIVE_OBLIGATION_SCHEMA,
    GovernedPaperIntegrityApprovalTable,
    GovernedPaperIntegrityTriggerProof,
    GovernedPaperIntegrityVerifierKind,
    GovernedPaperProtectiveLedgerContext,
    GovernedPaperProtectiveLedgerError,
    GovernedPaperProtectiveLedgerEventKind,
    GovernedPaperProtectiveLedgerEvidence,
    GovernedPaperProtectiveObligationKind,
    GovernedPaperProtectiveScheduleStatus,
    GovernedPaperUnfulfilledReason,
    build_governed_paper_integrity_anchor,
    build_governed_paper_integrity_trigger_proof,
    derive_governed_paper_protective_ledger,
    governed_paper_integrity_proof_admission,
    governed_paper_protective_ledger_canonical_context,
    governed_paper_protective_ledger_event_chain_intact,
    governed_paper_protective_ledger_evidence_digest,
    governed_paper_protective_ledger_evidence_to_dict,
    governed_paper_protective_ledger_halted_at,
    governed_paper_protective_ledger_open_at,
    governed_paper_protective_ledger_prefix_digest,
    governed_paper_protective_ledger_schedule_bounds,
)
from crypto_core.validation.governed_paper_system_state import derive_governed_paper_system_state_reading
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION,
    HistoricalExecutionDepthCap,
    HistoricalExecutionEconomicsError,
    HistoricalExecutionExposureEnvelope,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionFlattenWindow,
    HistoricalExecutionProtectiveTriggerKind,
    HistoricalExecutionProtectiveWindow,
    HistoricalExecutionSide,
    HistoricalExecutionTransitionKind,
    historical_execution_admission_schedule_digest,
    historical_execution_admission_schedule_to_dict,
    historical_execution_governed_paper_outcome_digest,
    historical_execution_governed_paper_outcome_to_dict,
    historical_execution_governed_paper_prefix_digest,
)

try:  # the module objects pytest collects (basename import): the shared synthetic worlds and their exact memos
    import test_governed_admitted_variant_paper_execution as gpe
    import test_governed_paper_entry_safety as est
    import test_governed_paper_kill_switch as kst
    import test_governed_paper_protective_lineage as lineage
    import test_governed_paper_regime_state as rst
    import test_governed_paper_sizing_chain as sct
    import test_historical_execution_protective_lifecycle as lifet
except ImportError:  # imported outside a pytest session
    from tests.crypto_core.validation import test_governed_admitted_variant_paper_execution as gpe
    from tests.crypto_core.validation import test_governed_paper_entry_safety as est
    from tests.crypto_core.validation import test_governed_paper_kill_switch as kst
    from tests.crypto_core.validation import test_governed_paper_protective_lineage as lineage
    from tests.crypto_core.validation import test_governed_paper_regime_state as rst
    from tests.crypto_core.validation import test_governed_paper_sizing_chain as sct
    from tests.crypto_core.validation import test_historical_execution_protective_lifecycle as lifet

SECOND = 1_000_000_000
MINUTE = 60 * SECOND
HOUR = 60 * MINUTE
V6 = HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION
OUTCOME_V4 = HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION
FILLED, PARTIAL = HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED
REJECTED, UNFILLED = HistoricalExecutionFillOutcome.REJECTED, HistoricalExecutionFillOutcome.UNFILLED
E = GovernedPaperProtectiveLedgerEventKind
R = GovernedPaperUnfulfilledReason
K = GovernedPaperProtectiveObligationKind
S = GovernedPaperEntrySafetyStatus
GENESIS = "c" * 64  # SYNTHETIC lineage digest of the engine-level worlds (the seal tests use world G's genesis)
AUTHORITY = "b" * 64
SYNTHETIC = GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC
TEST_ONLY_TABLE = GovernedPaperIntegrityApprovalTable("test_only", SYNTHETIC, ())
PRODUCTION_LEDGER_TABLE = ledger_module._APPROVAL_TABLE  # noqa: SLF001 - captured at import, before any patch


@contextlib.contextmanager
def integrity_table(table: GovernedPaperIntegrityApprovalTable) -> Iterator[None]:
    """SYNTHETIC, TEST-ONLY: the integrity approval table for one block (the production table admits no anchor)."""

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(ledger_module, "_APPROVAL_TABLE", table)
        yield
    assert ledger_module._APPROVAL_TABLE is PRODUCTION_LEDGER_TABLE  # noqa: SLF001


# --- the engine-level worlds ---------------------------------------------------------------------------------------------


def world_of(path: lifet.Path, end: int = lifet.LONG_RUN):  # noqa: ANN201
    """A SYNTHETIC lifecycle world (a SHORT entered at D_0 and held), its economics and its schedule v4 reference."""

    w, result = lifet.funded(path, end)
    schedule = lifet.both_sides(end=end)
    return w, result, schedule, lifet.governed_under(result, schedule)


@functools.cache
def baseline():  # noqa: ANN201
    return world_of(sct.ONE_DAY_PATH)


def v6_of(schedule: object, reference: object, halt: int | None = None, windows: tuple = (), **changes: object):  # noqa: ANN201
    """The schedule v6 of ``schedule`` with SYNTHETIC sizing bounds that admit the reference entries, the declared halt
    and flatten windows (authority ``AUTHORITY``)."""

    return replace(
        schedule,  # type: ignore[type-var]
        schema_version=V6,
        exposure_envelopes=sct.whole_run(1),
        depth_caps=sct.caps_for(sct.entries_of(reference)),
        exposure_halt_from_ns=halt,
        flatten_windows=tuple(HistoricalExecutionFlattenWindow(start, end, AUTHORITY) for start, end in windows),
        **changes,
    )


def opened_at(reference: object) -> int:
    return sct.entries_of(reference)[0].execution_time_ns


def children_of(outcome: object) -> list:
    """Each flatten child with its one fill outcome."""

    by_intent = {item.intent_id: item for item in outcome.fills}  # type: ignore[attr-defined]
    return [(child, by_intent[child.child_id]) for child in outcome.protective_children]  # type: ignore[attr-defined]


def book_override(after: int, **values: object):  # noqa: ANN201
    """A SYNTHETIC book function: the default 10 bps book of depth 100, and ``values`` from mark slot ``after`` on."""

    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return lifet.book_at(mid, **values) if j >= after else lifet.book_at(mid)  # type: ignore[arg-type]

    return book


TAU = lifet.ANCHOR + 10 * HOUR + 31 * SECOND  # 2 h after the D_0 SHORT's opening fill: mark slot 40's book instant
THIN = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=book_override(41, depth=25))  # 0.5 per fill
WIDE = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=book_override(41, half_spread=Fraction(5)))


def wide_once(j: int, mid: Fraction) -> dict[str, str] | None:
    return lifet.book_at(mid, half_spread=Fraction(5)) if j == 41 else lifet.book_at(mid)  # one 1000 bps book only


WIDE_ONCE = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=wide_once)


# --- A. the engine's schedule v6 ------------------------------------------------------------------------------------------


def test_schedule_v6_bounds_exist_only_on_schedule_v6_and_never_in_a_legacy_payload() -> None:
    _, _, schedule, reference = baseline()
    v5 = sct.v5_of(schedule, sct.whole_run(1), sct.caps_for(sct.entries_of(reference)))
    assert "exposure_halt_from_ns" not in historical_execution_admission_schedule_to_dict(v5)
    assert "flatten_windows" not in historical_execution_admission_schedule_to_dict(v5)
    v6 = v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),))
    payload = historical_execution_admission_schedule_to_dict(v6)
    assert payload["exposure_halt_from_ns"] == TAU
    assert payload["flatten_windows"] == [
        {"window_start_ns": TAU, "window_end_ns": lifet.LONG_RUN, "authority_digest": AUTHORITY}
    ]
    assert historical_execution_admission_schedule_digest(v6) != historical_execution_admission_schedule_digest(
        replace(v6, exposure_halt_from_ns=None, flatten_windows=())
    )
    window = HistoricalExecutionFlattenWindow
    invalid = (
        replace(v5, exposure_halt_from_ns=TAU),  # a v5 schedule never carries a v6 bound
        replace(v5, flatten_windows=(window(TAU, lifet.LONG_RUN, AUTHORITY),)),
        v6_of(schedule, reference, None, ((TAU, lifet.LONG_RUN),)),  # a flatten window needs the halt
        v6_of(schedule, reference, TAU + 1, ((TAU, lifet.LONG_RUN),)),  # and lies at or after it
        v6_of(schedule, reference, TAU, ((TAU, TAU),)),  # empty
        v6_of(schedule, reference, TAU, ((TAU, TAU + HOUR), (TAU + HOUR - 1, TAU + 2 * HOUR))),  # overlapping
        replace(v6_of(schedule, reference, TAU), flatten_windows=(window(TAU, lifet.LONG_RUN, "x"),)),
        replace(v6_of(schedule, reference, TAU), exposure_halt_from_ns=-1),
        replace(v6_of(schedule, reference, TAU), flatten_windows=[window(TAU, lifet.LONG_RUN, AUTHORITY)]),
    )
    for item in invalid:
        with pytest.raises(HistoricalExecutionEconomicsError):
            historical_execution_admission_schedule_digest(item)  # type: ignore[arg-type]
    # a schedule v6 runs only over a position-managed baseline: its children need the protective lifecycle's engine
    assert lifet.governed_under(baseline()[1], v6).schema_version == OUTCOME_V4
    legacy = lifet.econ.default_result()
    with pytest.raises(HistoricalExecutionEconomicsError, match="admission_schedule_version_mismatch$"):
        lifet.governed_under(legacy, replace(v6, exposure_halt_from_ns=None, flatten_windows=()))


def test_a_flatten_child_closes_the_whole_position_close_only_through_the_one_fill_model() -> None:
    _, result, schedule, reference = baseline()
    outcome = lifet.governed_under(result, v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),)))
    assert outcome.schema_version == OUTCOME_V4
    assert outcome.outcome_digest == historical_execution_governed_paper_outcome_digest(outcome)
    ((child, fill),) = children_of(outcome)
    assert (child.attempt_time_ns, child.flatten_authority_digest, child.child_sequence) == (TAU, AUTHORITY, 0)
    assert (child.position_quantity, child.requested_quantity, child.side) == (
        lifet.d(-1),
        lifet.d(1),
        HistoricalExecutionSide.BUY,
    )  # the whole remaining SHORT, bought back
    assert child.earliest_execution_time_ns == TAU + 100_000_000  # the governed latency
    # the next book strictly after the child instant (mark slot 41) prices it, with the fee, transition and trade ledgers
    assert (fill.outcome, fill.execution_time_ns, fill.decision_digest) == (FILLED, lifet.book_visible(41), AUTHORITY)
    transition = next(item for item in outcome.position_transitions if item.fill_digest == fill.fill_digest)
    assert transition.transition_kind is HistoricalExecutionTransitionKind.CLOSE
    assert any(item.fill_digest == fill.fill_digest for item in outcome.fee_cashflows)
    assert outcome.terminal_state.position_quantity == lifet.d(0)  # type: ignore[union-attr]
    assert outcome.protective_obligations == ()  # no v1 trigger reached before the close
    # the halt refuses every later entry (D_1 .. D_3), never a fill before it: the opening fill is the reference's own
    halted = [item.reason for item in outcome.fills if item.outcome is REJECTED]
    assert halted == ["governed_paper_exposure_halted"] * 3
    assert sct.entries_of(outcome)[0].fill_digest == sct.entries_of(reference)[0].fill_digest
    assert historical_execution_governed_paper_prefix_digest(
        outcome, before_ns=TAU
    ) != historical_execution_governed_paper_prefix_digest(reference, before_ns=TAU)  # outcome v4 adds its children
    payload = historical_execution_governed_paper_outcome_to_dict(outcome)
    assert payload["child_ledger_digest"] and payload["pending_protective_child_time_ns"] is None


def test_an_entry_in_flight_at_the_halt_is_refused_at_its_fill_and_no_position_or_child_follows() -> None:
    _, result, schedule, reference = baseline()
    fill_at = opened_at(reference)
    outcome = lifet.governed_under(result, v6_of(schedule, reference, fill_at - 1))  # decided before, filled after
    reasons = [item.reason for item in outcome.fills if item.outcome is REJECTED]
    assert reasons == ["governed_paper_exposure_halted_at_fill", *["governed_paper_exposure_halted"] * 3]
    assert outcome.position_transitions == () and outcome.fee_cashflows == () and outcome.protective_children == ()


def test_a_child_needs_a_dec1_window_at_its_instant_and_resumes_at_the_next_window() -> None:
    _, result, schedule, reference = baseline()
    later = TAU + HOUR
    windows = (
        HistoricalExecutionProtectiveWindow(lifet.ANCHOR, TAU - HOUR, "a" * 64),
        HistoricalExecutionProtectiveWindow(later, lifet.LONG_RUN, "a" * 64),
    )
    outcome = lifet.governed_under(
        result, v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),), protective_windows=windows)
    )
    (refused, resumed) = children_of(outcome)
    assert (refused[0].attempt_time_ns, refused[1].outcome, refused[1].reason, refused[1].execution_time_ns) == (
        TAU,
        REJECTED,
        "governed_paper_protective_authority_missing",
        None,
    )
    assert (resumed[0].attempt_time_ns, resumed[1].outcome) == (later, FILLED)
    assert refused[1].fill_digest in outcome.governance_rejected_fill_digests
    # without any later window the refused child never recurs and the position stays open, no fill invented
    none = lifet.governed_under(
        result, v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),), protective_windows=windows[:1])
    )
    assert len(none.protective_children) == 1 and none.terminal_state.position_quantity == lifet.d(-1)  # type: ignore[union-attr]


def test_a_partial_child_re_derives_the_remainder_at_its_own_instant_and_never_crosses_zero() -> None:
    _, result, schedule, reference = world_of(THIN)
    outcome = lifet.governed_under(result, v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),)))
    ((first, first_fill), (second, second_fill)) = children_of(outcome)
    assert (first.requested_quantity, first_fill.outcome, first_fill.filled_quantity) == (
        lifet.d(1),
        PARTIAL,
        lifet.d("0.5"),
    )
    assert first_fill.reason == "visible_depth_cap_partial_remainder_cancelled"
    # the remainder is a new child at the partial fill's own instant, of the remaining 0.5 only
    assert (second.attempt_time_ns, second.position_quantity, second.requested_quantity) == (
        first_fill.execution_time_ns,
        lifet.d("-0.5"),
        lifet.d("0.5"),
    )
    assert (second_fill.outcome, second_fill.execution_time_ns) == (FILLED, lifet.book_visible(42))
    kinds = [item.transition_kind for item in outcome.position_transitions]
    assert kinds == [
        HistoricalExecutionTransitionKind.OPEN,
        HistoricalExecutionTransitionKind.REDUCE,
        HistoricalExecutionTransitionKind.CLOSE,
    ]
    assert outcome.terminal_state.position_quantity == lifet.d(0)  # type: ignore[union-attr]


def test_a_book_rejection_retries_the_child_at_least_30_seconds_later() -> None:
    _, result, schedule, reference = world_of(WIDE_ONCE)
    outcome = lifet.governed_under(result, v6_of(schedule, reference, TAU, ((TAU, lifet.LONG_RUN),)))
    ((first, first_fill), (second, second_fill)) = children_of(outcome)
    assert (first_fill.outcome, first_fill.reason, first_fill.execution_time_ns) == (
        REJECTED,
        "spread_exceeds_max",
        lifet.book_visible(41),
    )
    assert second.attempt_time_ns == lifet.book_visible(41) + 30 * SECOND  # §1.19 item 4: at least 30 s later
    assert (second_fill.outcome, second_fill.execution_time_ns) == (FILLED, lifet.book_visible(42))
    assert first_fill.fill_digest not in outcome.governance_rejected_fill_digests  # a market rejection, not governance


@pytest.mark.parametrize("delay", [0, 1])
def test_a_v1_max_hold_obligation_keeps_precedence_over_a_flatten_child(delay: int) -> None:
    _, result, schedule, reference = baseline()
    deadline = opened_at(reference) + 24 * HOUR
    tau = deadline + delay  # the same instant (v1 rules come first) or while the v1 obligation is outstanding
    outcome = lifet.governed_under(result, v6_of(schedule, reference, tau, ((tau, lifet.LONG_RUN),)))
    assert outcome.protective_children == ()
    (obligation,) = outcome.protective_obligations
    assert (obligation.created_at_ns, obligation.status.value) == (deadline, "DISCHARGED")
    assert outcome.fills == reference.fills and outcome.position_transitions == reference.position_transitions


def test_a_child_in_flight_at_the_replay_end_is_pending_and_the_prefix_excludes_it_by_its_instant() -> None:
    short_end = TAU + MINUTE  # the child's book (mark slot 41) is visible only after this end
    w, result = lifet.funded(lifet.path_to(short_end, (lifet.POSITIVE,) * 6), short_end)
    schedule = lifet.both_sides(end=short_end)
    reference = lifet.governed_under(result, schedule)
    short = lifet.governed_under(result, v6_of(schedule, reference, TAU, ((TAU, short_end),)))
    ((child, fill),) = children_of(short)
    assert (fill.outcome, fill.reason) == (UNFILLED, "execution_window_closed")
    assert (short.pending_protective_child_time_ns, short.pending_protective_child_digest) == (
        TAU,
        child.child_digest,
    )
    _, long_result, long_schedule, long_reference = baseline()
    long = lifet.governed_under(long_result, v6_of(long_schedule, long_reference, TAU, ((TAU, lifet.LONG_RUN),)))
    assert long.pending_protective_child_time_ns is None and children_of(long)[0][1].outcome is FILLED
    excluded = {"excluded_protective_child_times": (TAU,)}
    assert historical_execution_governed_paper_prefix_digest(
        long, before_ns=short_end, **excluded
    ) == historical_execution_governed_paper_prefix_digest(short, before_ns=short_end, **excluded)
    assert historical_execution_governed_paper_prefix_digest(
        long, before_ns=short_end
    ) != historical_execution_governed_paper_prefix_digest(short, before_ns=short_end)


# --- A2. the v1 handoff when a child resolves without closing the position -------------------------------------------------

MAX_HOLD_AT = lifet.book_visible(128)  # the D_0 SHORT's 24 h deadline: its opening fill (mark slot 32's book) + 24 h
IN_FLIGHT = MAX_HOLD_AT - SECOND  # a child sent here skips slot 128's book (not after it) and waits for slot 129's
AT_DEADLINE = MAX_HOLD_AT - 2 * SECOND  # a child sent here is priced by slot 128's book, visible AT the deadline
MAX_HOLD = HistoricalExecutionProtectiveTriggerKind.MAX_HOLD


def wide_at(*slots: int):  # noqa: ANN201
    """A SYNTHETIC book function: a 1000 bps book (spread_exceeds_max) at mark slots ``slots``, the default elsewhere."""

    def book(j: int, mid: Fraction) -> dict[str, str] | None:
        return lifet.book_at(mid, half_spread=Fraction(5)) if j in slots else lifet.book_at(mid)

    return book


REJECTED_129 = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=wide_at(129))  # the in-flight child's book
REJECTED_129_130 = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=wide_at(129, 130))  # and v1's first one
REJECTED_128 = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=wide_at(128))  # the book AT the deadline
THIN_129 = lifet.path_to(lifet.LONG_RUN, (lifet.POSITIVE,) * 6, book=book_override(129, depth=25))  # 0.5 per fill
# Identities computed at the audited head 1ab87cdf, before the handoff repair: the legacy schedule v4 outcomes of the
# handoff worlds (v1 alone) and the R3 outcomes and ledgers (a filled and a partial child, no rejection branch).
HANDOFF_REFERENCE_PINS = (
    "6e67f35cc040a042c4f151135d4679d02059872cda132834dd5a5f87f1069e53",
    "53c877ee082448f273e099776eaf5c19e63f31684b552b702037e230d9783418",
    "9a13f08db4a8ea1b22d0d6a4b0a5b622fb28e19c7c7c8a386f66f555f9badd40",
    "979aa69ca0947f0a00e3de09ef0f27e9a4eaa6e878a2c5b218fa87cb143a5899",
    "f846c0aa60a9033010ffa01f5fd172d4c32bc22cc4e3b569977b46d1c8074281",
)
R3_PINS = (
    "8501e00d9aa27a2be20b437bec6e80fc94d9dfa3043d9395559807ead1578e7a",
    "30025ff4e3c94bb197e12fb10e76f93c5b7fda69b762480c56a45b0edd0693dd",
    "e4cac56e0b5ddc69c0a8c7eb4deebf3c537a6cb1f9fe541f0f08a6384b2e60fc",
    "31e0c41e3851652cf79be8047fcc22a5952d1c6966f5548192f256ec1538d9f1",
)


@functools.cache
def handoff_world(path: lifet.Path) -> tuple:
    return baseline() if path is sct.ONE_DAY_PATH else world_of(path)


def handoff_outcome(path: lifet.Path, sent: int, flatten_end: int, **changes: object):  # noqa: ANN201
    """The schedule v6 re-run of ``path`` with the halt and one flatten window ``[sent, flatten_end)`` (authority
    ``AUTHORITY``): its child is sent at ``sent``, before the deadline, and resolves at or after it."""

    _, result, schedule, reference = handoff_world(path)
    outcome = lifet.governed_under(result, v6_of(schedule, reference, sent, ((sent, flatten_end),), **changes))
    assert outcome.outcome_digest == historical_execution_governed_paper_outcome_digest(outcome)
    return outcome


def v1_timeline(outcome: object) -> tuple:
    """Every v1 attempt instant, and each v1 attempt fill as (outcome, execution instant, reason)."""

    fills = [(item.outcome, item.execution_time_ns, item.reason) for item in lifet.protective_fills(outcome)]  # type: ignore[arg-type]
    return [item.attempt_time_ns for item in outcome.protective_attempts], fills  # type: ignore[attr-defined]


def the_max_hold_obligation(outcome: object):  # noqa: ANN201
    """The one v1 obligation: the 24 h MAX_HOLD trigger exactly once, due at the deadline."""

    (obligation,) = outcome.protective_obligations  # type: ignore[attr-defined]
    assert [item.trigger_kind for item in obligation.triggers] == [MAX_HOLD]
    assert (obligation.triggers[0].trigger_time_ns, obligation.created_at_ns) == (MAX_HOLD_AT, MAX_HOLD_AT)
    assert obligation.attempt_ids == tuple(item.attempt_id for item in outcome.protective_attempts)  # type: ignore[attr-defined]
    return obligation


def closed_by(outcome: object, at: int) -> None:
    """The position closes once, at ``at``, through close-only fills that never cross zero: no fill is invented."""

    kinds = [item.transition_kind for item in outcome.position_transitions]  # type: ignore[attr-defined]
    assert kinds[0] is HistoricalExecutionTransitionKind.OPEN and kinds[-1] is HistoricalExecutionTransitionKind.CLOSE
    assert set(kinds[1:-1]) <= {HistoricalExecutionTransitionKind.REDUCE}
    quantities = [Fraction(item.post_quantity) for item in outcome.position_transitions]  # type: ignore[attr-defined]
    assert all(quantity * quantities[0] >= 0 for quantity in quantities)  # never crosses zero
    sizes = [abs(item) for item in quantities]
    assert sizes == sorted(sizes, reverse=True)  # the position only shrinks
    assert outcome.position_transitions[-1].time_ns == at  # type: ignore[attr-defined]
    assert outcome.terminal_state.position_quantity == lifet.d(0)  # type: ignore[attr-defined]
    assert (outcome.pending_protective_child_time_ns, outcome.pending_protective_attempt_time_ns) == (None, None)  # type: ignore[attr-defined]


@functools.cache
def authentic_handoff() -> tuple:
    """The auditor's public-ledger context on the baseline world: a KS4 proof at IN_FLIGHT (its child waits for slot
    129's book) and an SS4 proof at the MAX_HOLD deadline that threatens the lineage's own book, so the flatten
    authority ends at the deadline while the DEC-1 protective window stays in force."""

    book = baseline()[0].dataset.source_manifest_digest
    proofs = (proof(IN_FLIGHT), proof(MAX_HOLD_AT, K.SS4_FLATTEN, scope=(book,)))
    with integrity_table(TEST_ONLY_TABLE):
        outcome, evidence = ledger_for(baseline(), proofs=proofs)
    return proofs, outcome, evidence


def test_r1_a_child_refused_at_its_fill_hands_the_max_hold_obligation_to_v1_at_its_own_resolution() -> None:
    proofs, outcome, evidence = authentic_handoff()
    resolved, closed = lifet.book_visible(129), lifet.book_visible(130)
    assert opened_at(baseline()[3]) + 24 * HOUR == MAX_HOLD_AT  # the deadline passes while the child is in flight
    # the child: the whole SHORT at IN_FLIGHT, refused at its fill because its flatten authority ended at the deadline
    ((child, fill),) = children_of(outcome)  # no child preempts v1, before or after its resolution
    assert (child.attempt_time_ns, child.flatten_authority_digest, child.requested_quantity) == (
        IN_FLIGHT,
        proofs[0].proof_digest,
        lifet.d(1),
    )
    assert (fill.outcome, fill.reason, fill.execution_time_ns) == (
        REJECTED,
        "governed_paper_flatten_authority_missing_at_fill",
        resolved,
    )
    assert fill.fill_digest in outcome.governance_rejected_fill_digests
    window = HistoricalExecutionFlattenWindow(IN_FLIGHT, MAX_HOLD_AT, proofs[0].proof_digest)
    assert outcome.schedule.flatten_windows == (window,)  # the SS4 proof ends the flatten authority at the deadline
    assert outcome.schedule.protective_windows[0].window_end_ns > closed  # v1's close-only authority stays valid
    # v1: the obligation due in flight is attempted at the child's resolution, never at a later child resume instant
    obligation = the_max_hold_obligation(outcome)
    (attempt,) = outcome.protective_attempts
    assert (attempt.attempt_time_ns, attempt.position_quantity, attempt.requested_quantity, attempt.side) == (
        resolved,
        lifet.d(-1),
        lifet.d(1),
        HistoricalExecutionSide.BUY,
    )
    assert attempt.earliest_execution_time_ns == resolved + 100_000_000  # the governed latency
    # the next authenticated book strictly after the resolution (mark slot 130) closes the whole SHORT through v1
    (v1_fill,) = lifet.protective_fills(outcome)
    assert (v1_fill.outcome, v1_fill.execution_time_ns, v1_fill.filled_quantity) == (FILLED, closed, lifet.d(1))
    assert v1_fill.book_event_time_ns == lifet.slot(130) + lifet.BOOK_OFFSET
    assert (obligation.status.value, obligation.discharged_at_ns, obligation.discharging_fill_digest) == (
        "DISCHARGED",
        closed,
        v1_fill.fill_digest,
    )
    assert obligation.breach_duration_ns == closed - MAX_HOLD_AT
    closed_by(outcome, closed)
    assert outcome.position_transitions[-1].fill_digest == v1_fill.fill_digest
    # the ledger agrees: the refused child is recorded at its instant, and the v1 fill discharges the schedule
    (schedule,) = evidence.schedules
    events = [(item.kind, item.time_ns, item.reason) for item in schedule.events]
    assert (E.CHILD_SENT, IN_FLIGHT, "") in events
    assert (E.INTEGRITY_UNPROVEN, resolved, "governed_paper_flatten_authority_missing_at_fill") in events
    assert events[-1] == (E.DISCHARGED, closed, "verified_position_zero")
    assert [(item.source.value, item.time_ns, item.quantity) for item in schedule.attributed_fills] == [
        ("V1_ATTEMPT", closed, lifet.d(1))
    ]
    assert (schedule.status, schedule.discharged_at_ns, evidence.open_obligation_count) == (
        GovernedPaperProtectiveScheduleStatus.DISCHARGED,
        closed,
        0,
    )
    assert evidence.governed_outcome_digest == outcome.outcome_digest


def test_r2_a_child_book_rejection_never_lends_its_30_second_retry_to_v1() -> None:
    resolved = lifet.book_visible(129)
    outcome = handoff_outcome(REJECTED_129, IN_FLIGHT, lifet.LONG_RUN)  # the auditor's rejected child book
    ((child, fill),) = children_of(outcome)
    assert (child.attempt_time_ns, fill.outcome, fill.reason, fill.execution_time_ns) == (
        IN_FLIGHT,
        REJECTED,
        "spread_exceeds_max",
        resolved,
    )
    assert fill.fill_digest not in outcome.governance_rejected_fill_digests
    # v1 is attempted at the rejection instant itself, not at the child's retry 30 s later
    assert v1_timeline(outcome) == ([resolved], [(FILLED, lifet.book_visible(130), "filled")])
    assert the_max_hold_obligation(outcome).discharged_at_ns == lifet.book_visible(130)
    closed_by(outcome, lifet.book_visible(130))
    # v1 keeps its own book rule: a rejected v1 attempt re-attempts at its own rejection instant, never 30 s later, and
    # the child's retry wake event (while v1 is in flight) issues nothing: one child, one attempt in flight at a time
    twice = handoff_outcome(REJECTED_129_130, IN_FLIGHT, lifet.LONG_RUN)
    assert len(twice.protective_children) == 1
    assert v1_timeline(twice) == (
        [resolved, lifet.book_visible(130)],
        [
            (REJECTED, lifet.book_visible(130), "spread_exceeds_max"),
            (FILLED, lifet.book_visible(131), "filled"),
        ],
    )
    assert the_max_hold_obligation(twice).discharged_at_ns == lifet.book_visible(131)
    closed_by(twice, lifet.book_visible(131))
    for item in (outcome, twice):
        assert all(child.attempt_time_ns < resolved for child in item.protective_children)


def test_r3_a_filled_or_partial_child_keeps_its_exact_fill_attribution_and_v1_takes_only_the_remainder() -> None:
    with integrity_table(TEST_ONLY_TABLE):
        whole, whole_ledger = ledger_for(baseline(), proofs=(proof(IN_FLIGHT),))
        part, part_ledger = ledger_for(handoff_world(THIN_129), proofs=(proof(IN_FLIGHT),))
    resolved = lifet.book_visible(129)
    # FILLED: the child closes the whole SHORT and discharges the v1 obligation due in flight; v1 never attempts
    ((_, fill),) = children_of(whole)
    assert (fill.outcome, fill.execution_time_ns, fill.filled_quantity) == (FILLED, resolved, lifet.d(1))
    obligation = the_max_hold_obligation(whole)
    assert (obligation.status.value, obligation.discharging_fill_digest, whole.protective_attempts) == (
        "DISCHARGED",
        fill.fill_digest,
        (),
    )
    closed_by(whole, resolved)
    assert [(item.source.value, item.quantity) for item in whole_ledger.schedules[0].attributed_fills] == [
        ("CHILD", lifet.d(1))
    ]
    # PARTIALLY_FILLED: the child closes 0.5 at its book; v1 then holds precedence and closes only the remaining 0.5
    ((_, partial),) = children_of(part)  # no second child while the v1 obligation is outstanding
    assert (partial.outcome, partial.execution_time_ns, partial.filled_quantity) == (PARTIAL, resolved, lifet.d("0.5"))
    (attempt,) = part.protective_attempts
    assert (attempt.attempt_time_ns, attempt.position_quantity, attempt.requested_quantity) == (
        resolved,
        lifet.d("-0.5"),
        lifet.d("0.5"),
    )
    (v1_fill,) = lifet.protective_fills(part)
    assert (v1_fill.outcome, v1_fill.execution_time_ns, v1_fill.filled_quantity) == (
        FILLED,
        lifet.book_visible(130),
        lifet.d("0.5"),
    )
    assert the_max_hold_obligation(part).discharging_fill_digest == v1_fill.fill_digest
    closed_by(part, lifet.book_visible(130))
    assert [
        (item.transition_kind, item.fill_digest, item.closed_quantity) for item in part.position_transitions[1:]
    ] == [
        (HistoricalExecutionTransitionKind.REDUCE, partial.fill_digest, lifet.d("0.5")),
        (HistoricalExecutionTransitionKind.CLOSE, v1_fill.fill_digest, lifet.d("0.5")),
    ]
    assert [(item.source.value, item.quantity) for item in part_ledger.schedules[0].attributed_fills] == [
        ("CHILD", lifet.d("0.5")),
        ("V1_ATTEMPT", lifet.d("0.5")),
    ]  # each fill attributed once, to its own order
    # both paths are byte-identical to the audited head's (neither reaches a rejection branch)
    assert (whole.outcome_digest, whole_ledger.evidence_digest, part.outcome_digest, part_ledger.evidence_digest) == (
        R3_PINS
    )


AUTHORITY_GAP = (
    HistoricalExecutionProtectiveWindow(lifet.ANCHOR, MAX_HOLD_AT + 10 * MINUTE, "a" * 64),
    HistoricalExecutionProtectiveWindow(MAX_HOLD_AT + HOUR, lifet.LONG_RUN + 24 * HOUR, "a" * 64),
)  # SYNTHETIC: no DEC-1 window from 10 min after the deadline until 1 h after it


@pytest.mark.parametrize(
    ("path", "sent", "flatten_end", "changes", "rejection", "attempts", "v1_fills"),
    [
        pytest.param(  # MAX_HOLD, the child's outcome and v1's evaluation at ONE instant: v1 loses nothing to the child
            sct.ONE_DAY_PATH,
            AT_DEADLINE,
            MAX_HOLD_AT,
            {},
            ("governed_paper_flatten_authority_missing_at_fill", MAX_HOLD_AT),
            [MAX_HOLD_AT],
            [(FILLED, lifet.book_visible(129), "filled")],
            id="governed-refusal-at-the-deadline",
        ),
        pytest.param(
            REJECTED_128,
            AT_DEADLINE,
            lifet.LONG_RUN,
            {},
            ("spread_exceeds_max", MAX_HOLD_AT),
            [MAX_HOLD_AT],
            [(FILLED, lifet.book_visible(129), "filled")],
            id="book-rejection-at-the-deadline",
        ),
        pytest.param(  # the auditor's FLATTEN_EXPIRES timestamps: the deadline passes 1 s after the child is sent
            sct.ONE_DAY_PATH,
            IN_FLIGHT,
            MAX_HOLD_AT,
            {},
            ("governed_paper_flatten_authority_missing_at_fill", lifet.book_visible(129)),
            [lifet.book_visible(129)],
            [(FILLED, lifet.book_visible(130), "filled")],
            id="governed-refusal-after-the-deadline",
        ),
        pytest.param(  # v1's own DEC-1 rule at the handoff, then the child's resume wake and v1's resume coincide
            sct.ONE_DAY_PATH,
            IN_FLIGHT,
            lifet.LONG_RUN,
            {"protective_windows": AUTHORITY_GAP},
            ("governed_paper_protective_authority_missing_at_fill", lifet.book_visible(129)),
            [lifet.book_visible(129), MAX_HOLD_AT + HOUR],
            [
                (REJECTED, None, "governed_paper_protective_authority_missing"),
                (FILLED, lifet.book_visible(133), "filled"),
            ],
            id="dec1-refusal-and-coinciding-resume-wakes",
        ),
    ],
)
def test_r4_equal_and_near_instants_keep_one_deterministic_order_and_never_duplicate_a_protective_order(  # noqa: PLR0913
    path: lifet.Path,
    sent: int,
    flatten_end: int,
    changes: dict,
    rejection: tuple[str, int],
    attempts: list[int],
    v1_fills: list[tuple],
) -> None:
    outcome = handoff_outcome(path, sent, flatten_end, **changes)
    ((child, fill),) = children_of(outcome)  # never a second child: v1's obligation holds the slot after the outcome
    assert (child.attempt_time_ns, fill.outcome, (fill.reason, fill.execution_time_ns)) == (sent, REJECTED, rejection)
    # the first v1 attempt is the child's own resolution instant; each later one is v1's own rule, never a child retry
    assert v1_timeline(outcome) == (attempts, v1_fills)
    obligation = the_max_hold_obligation(outcome)  # one MAX_HOLD trigger, though the deadline met other events
    assert (obligation.status.value, obligation.discharged_at_ns) == ("DISCHARGED", v1_fills[-1][1])
    closed_by(outcome, v1_fills[-1][1])
    if rejection[1] == MAX_HOLD_AT:  # resolved AT the deadline: v1 attempts and closes exactly as without the child
        reference = handoff_world(path)[3]
        assert v1_timeline(outcome) == v1_timeline(reference)
        assert outcome.position_transitions[-1].time_ns == reference.position_transitions[-1].time_ns
    # the equal-instant priority is deterministic: an independent re-run is byte-identical
    assert historical_execution_governed_paper_outcome_to_dict(
        handoff_outcome(path, sent, flatten_end, **changes)
    ) == historical_execution_governed_paper_outcome_to_dict(outcome)


def ledger_arguments(world: tuple, outcome: object, ladder: object, context: object) -> dict[str, object]:
    """The public ledger builder's arguments for one re-run of ``world`` (as ``ledger_for`` passes them)."""

    w, result = world[0], world[1]
    return {
        "genesis_digest": GENESIS,
        "instrument": result.instrument,
        "start_ns": result.evaluation_start_ns,
        "outcome": outcome,
        "ladder": ladder,
        "system_states": (),
        "decision_instants": tuple(item.decision_time_ns for item in w.run.decisions),
        "context": context,
        "book_source_digest": w.dataset.source_manifest_digest,
        "depth_cap_fraction": policy_of(result).visible_depth_cap_fraction,
    }


def test_r5_the_handoff_replays_from_its_proofs_byte_identically_and_every_tamper_is_refused() -> None:
    proofs, outcome, evidence = authentic_handoff()
    world = baseline()
    w, result, schedule, reference = world
    context = GovernedPaperProtectiveLedgerContext(proofs)
    resolved = lifet.book_visible(129)
    with integrity_table(TEST_ONLY_TABLE):
        # the schedule rebuilt from the proofs alone, an independent re-run, and the ledger rebuilt from that re-run
        halt, flatten = governed_paper_protective_ledger_schedule_bounds(
            context, book_source_digest=w.dataset.source_manifest_digest, horizon_ns=result.evaluation_end_ns
        )
        rebuilt = replace(v6_of(schedule, reference), exposure_halt_from_ns=halt, flatten_windows=flatten)
        replayed = derivation(world, rebuilt)
        replayed_ledger = derive_governed_paper_protective_ledger(
            **ledger_arguments(world, replayed.outcome, replayed.ladder, context)  # type: ignore[arg-type]
        )
        # tampering: the v1 attempt restated at the child's 30 s retry, or no v1 attempt at all (the unrepaired shape)
        (attempt,) = outcome.protective_attempts
        late = replace(
            outcome, protective_attempts=(replace(attempt, attempt_time_ns=attempt.attempt_time_ns + 30 * SECOND),)
        )
        dropped = replace(outcome, protective_attempts=())
        for forged in (late, dropped):
            assert historical_execution_governed_paper_outcome_digest(forged) != outcome.outcome_digest
            resealed = replace(forged, outcome_digest=historical_execution_governed_paper_outcome_digest(forged))
            for item, reason in ((forged, "outcome_digest_mismatch"), (resealed, "ladder_not_of_this_re_run")):
                with pytest.raises(GovernedPaperProtectiveLedgerError, match=f"{reason}$"):
                    derive_governed_paper_protective_ledger(
                        **ledger_arguments(world, item, replayed.ladder, context)  # type: ignore[arg-type]
                    )
    assert historical_execution_admission_schedule_digest(rebuilt) == historical_execution_admission_schedule_digest(
        outcome.schedule
    )
    assert historical_execution_governed_paper_outcome_to_dict(
        replayed.outcome
    ) == historical_execution_governed_paper_outcome_to_dict(outcome)
    assert replayed.ladder.governed_outcome_digest == outcome.outcome_digest
    assert governed_paper_protective_ledger_evidence_to_dict(
        replayed_ledger
    ) == governed_paper_protective_ledger_evidence_to_dict(evidence)
    # the ledger: moving the refused child's event off its resolution instant breaks the chain and the evidence digest
    (ledger_schedule,) = evidence.schedules
    events = list(ledger_schedule.events)
    index = next(
        position
        for position, item in enumerate(events)
        if (item.kind, item.time_ns) == (E.INTEGRITY_UNPROVEN, resolved)
    )
    events[index] = replace(events[index], time_ns=resolved + 30 * SECOND)
    broken = replace(ledger_schedule, events=tuple(events))
    assert governed_paper_protective_ledger_event_chain_intact(ledger_schedule)
    assert not governed_paper_protective_ledger_event_chain_intact(broken)
    assert governed_paper_protective_ledger_evidence_digest(replace(evidence, schedules=(broken,))) != (
        evidence.evidence_digest
    )


HANDOFF_V1_ALONE = (  # each handoff world under v1 alone: its attempt instants and its attempt fills
    (sct.ONE_DAY_PATH, [MAX_HOLD_AT], [(FILLED, lifet.book_visible(129), "filled")]),
    (
        REJECTED_129,
        [MAX_HOLD_AT, lifet.book_visible(129)],
        [(REJECTED, lifet.book_visible(129), "spread_exceeds_max"), (FILLED, lifet.book_visible(130), "filled")],
    ),
    (
        REJECTED_129_130,
        [MAX_HOLD_AT, lifet.book_visible(129), lifet.book_visible(130)],
        [
            (REJECTED, lifet.book_visible(129), "spread_exceeds_max"),
            (REJECTED, lifet.book_visible(130), "spread_exceeds_max"),
            (FILLED, lifet.book_visible(131), "filled"),
        ],
    ),
    (REJECTED_128, [MAX_HOLD_AT], [(FILLED, lifet.book_visible(129), "filled")]),
    (
        THIN_129,
        [MAX_HOLD_AT, lifet.book_visible(129)],
        [
            (PARTIAL, lifet.book_visible(129), "visible_depth_cap_partial_remainder_cancelled"),
            (FILLED, lifet.book_visible(130), "filled"),
        ],
    ),
)


V1_REPLAYED_FIELDS = (
    "fills",
    "protective_attempts",
    "protective_obligations",
    "position_transitions",
    "terminal_state",
)


def test_r6_v1_alone_keeps_its_exact_rules_and_legacy_identities_on_every_handoff_world() -> None:
    digests = []
    for path, attempts, fills in HANDOFF_V1_ALONE:
        _, result, schedule, reference = handoff_world(path)
        # the legacy schedule v4 (no child): the deadline attempt at exactly MAX_HOLD_AT, then v1's own book rules
        assert reference.schema_version != OUTCOME_V4 and reference.protective_children == ()
        assert v1_timeline(reference) == (attempts, fills)
        the_max_hold_obligation(reference)
        closed_by(reference, fills[-1][1])
        # a schedule v6 without a halt or a flatten window replays v1 exactly: the v2 extension stays inert
        bare = lifet.governed_under(result, v6_of(schedule, reference))
        assert (bare.schema_version, bare.protective_children) == (OUTCOME_V4, ())
        for name in V1_REPLAYED_FIELDS:
            assert getattr(bare, name) == getattr(reference, name), name
        digests.append(reference.outcome_digest)
    assert tuple(digests) == HANDOFF_REFERENCE_PINS  # byte-identical to the audited head's legacy outcomes


def anchor(**changes: object):  # noqa: ANN201
    values: dict[str, object] = {
        "anchor_id": "synthetic-anchor-1",
        "anchor_reference": "synthetic:outside-lineage-anchor",
        "approval_kind": SYNTHETIC,
        "approver_reference": "synthetic-approver",
        "approved_at_ns": lifet.ANCHOR,
    }
    values.update(changes)
    return build_governed_paper_integrity_anchor(**values)  # type: ignore[arg-type]


def proof(  # noqa: PLR0913
    at: int = TAU,
    kind: GovernedPaperProtectiveObligationKind = K.KS4_FLATTEN,
    *,
    scope: tuple[str, ...] = ("e" * 64,),
    complete: bool = True,
    genesis: str = GENESIS,
    verifier: GovernedPaperIntegrityVerifierKind = GovernedPaperIntegrityVerifierKind.INDEPENDENT_VERIFIER,
    **anchor_changes: object,
) -> GovernedPaperIntegrityTriggerProof:
    """A SYNTHETIC IR-2 proof: an independent verifier's re-derivation from raw sealed inputs against an anchor."""

    return build_governed_paper_integrity_trigger_proof(
        proof_id=f"synthetic-proof-{kind.value}-{at}",
        genesis_digest=genesis,
        trigger_kind=kind,
        trigger_time_ns=at,
        verifier_kind=verifier,
        verifier_id="synthetic-independent-verifier",
        anchor=anchor(**anchor_changes),
        sealed_input_digests=("d" * 64,),
        threat_scope_digests=scope,
        threat_scope_complete=complete,
    )


def crisis(decision: object):  # noqa: ANN201
    """An AUTHENTIC §1.29 reading at ``decision`` of five proven NT-D failures (S4 = 1, CRISIS by the critical override)."""

    return derive_governed_paper_system_state_reading(
        decision_sequence=decision.decision_sequence,  # type: ignore[attr-defined]
        decision_time_ns=decision.decision_time_ns,  # type: ignore[attr-defined]
        kill_switch_level=0,
        drawdown_beyond_10pct_proven=False,
        drawdown_beyond_15pct_proven=False,
        data_statuses=tuple((f"NT-D0{index}", "FAIL") for index in range(1, 6)),
        execution_statuses=tuple((f"NT-X0{index}", "PASS") for index in range(1, 5)),
        latency_ns=100_000_000,
        latency_budget_ns=100_000_000,
        single_instrument_portfolio=True,
    )


def policy_of(result: object):  # noqa: ANN201
    """The SYNTHETIC economics policy the world's economics bound (the lifecycle or the information-time variant)."""

    for policy in (lifet.economics_policy(), lifet.equity_policy(lifet.d(10_000))):
        if policy.policy_digest == result.economics_policy_digest:  # type: ignore[attr-defined]
            return policy
    raise AssertionError("unknown synthetic economics policy")


def derivation(world: tuple, schedule: object):  # noqa: ANN201
    """The kill-switch ladder, decision portfolio and governed outcome of ONE schedule v6 re-run of ``world``."""

    w, result = world[0], world[1]
    return derive_governed_paper_kill_switch_ladder(
        policy=policy_of(result),
        dataset=w.dataset,
        economics=result,
        schedule=schedule,
        single_instrument_portfolio=True,
    )


def ledger_for(  # noqa: PLR0913
    world: tuple,
    *,
    proofs: tuple[GovernedPaperIntegrityTriggerProof, ...] = (),
    readings: tuple = (),
    windows: tuple | None = None,
    protective: tuple | None = None,
) -> tuple[object, GovernedPaperProtectiveLedgerEvidence]:
    """The schedule v6 re-run of ``world`` under the bounds ``proofs`` imply, and its ledger."""

    w, result, schedule, reference = world
    context = GovernedPaperProtectiveLedgerContext(proofs)
    halt, flatten = governed_paper_protective_ledger_schedule_bounds(
        context, book_source_digest=w.dataset.source_manifest_digest, horizon_ns=result.evaluation_end_ns
    )
    changes = {} if protective is None else {"protective_windows": protective}
    v6 = replace(
        v6_of(schedule, reference, **changes),
        exposure_halt_from_ns=halt,
        flatten_windows=flatten if windows is None else windows,
    )
    derived = derivation(world, v6)
    policy = policy_of(result)
    evidence = derive_governed_paper_protective_ledger(
        genesis_digest=GENESIS,
        instrument=result.instrument,
        start_ns=result.evaluation_start_ns,
        outcome=derived.outcome,
        ladder=derived.ladder,
        system_states=readings,
        decision_instants=tuple(item.decision_time_ns for item in w.run.decisions),
        context=context,
        book_source_digest=w.dataset.source_manifest_digest,
        depth_cap_fraction=policy.visible_depth_cap_fraction,
    )
    assert evidence.evidence_digest == governed_paper_protective_ledger_evidence_digest(evidence)
    assert all(governed_paper_protective_ledger_event_chain_intact(item) for item in evidence.schedules)
    return derived.outcome, evidence


def events_of(evidence: GovernedPaperProtectiveLedgerEvidence) -> list[tuple]:
    (schedule,) = evidence.schedules
    return [
        (
            item.kind,
            item.time_ns,
            item.quantity,
            item.closed_quantity,
            item.remaining_quantity,
            None if item.unfulfilled is None else (item.unfulfilled.reason, item.unfulfilled.remaining_exposure),
        )
        for item in schedule.events
    ]


PENDING_METHOD_FLAGS = ("target_path_defined", "impact_measure_defined", "participation_method_defined")


def no_target_anywhere(value: object) -> bool:
    """Whether no field of a payload carries a target path (HC-11c), an impact pause (HC-11f) or a participation
    allowance (HD-04); the only keys naming them are the non-claim flags, each False."""

    if isinstance(value, dict):
        for key, item in value.items():
            if key in PENDING_METHOD_FLAGS:
                if item is not False:
                    return False
                continue
            if "target" in key or "impact_pause" in key or "allowance" in key or not no_target_anywhere(item):
                return False
        return True
    if isinstance(value, list):
        return all(no_target_anywhere(item) for item in value)
    return True


def test_an_ir2_proof_is_admitted_only_by_an_independent_verifier_against_an_admitted_anchor() -> None:
    valid = proof()
    assert governed_paper_integrity_proof_admission(valid, genesis_digest=GENESIS) == (
        "synthetic_anchor_refused_on_the_production_table"
    )
    human = proof(approval_kind=GovernedPaperApprovalKind.HUMAN_GOVERNANCE)
    assert governed_paper_integrity_proof_admission(human, genesis_digest=GENESIS) == (
        "anchor_not_authorized_for_production_use"
    )
    with integrity_table(TEST_ONLY_TABLE):
        assert governed_paper_integrity_proof_admission(valid, genesis_digest=GENESIS) == ""
        for item, reason in (
            (human, "only_test_only_synthetic_anchors_on_the_test_only_table"),
            (
                proof(verifier=GovernedPaperIntegrityVerifierKind.EXECUTOR_SELF_REPORT),
                "executor_self_report_never_proves_a_trigger",
            ),
            (
                proof(verifier=GovernedPaperIntegrityVerifierKind.OPERATOR_RAISE_CHANNEL),
                "operator_raise_channel_scope_pending_hc_05d",
            ),
            (proof(genesis="f" * 64), "integrity_proof_of_another_lineage"),
            (proof(approved_at_ns=TAU + 1), "anchor_approved_after_the_trigger"),
        ):
            assert governed_paper_integrity_proof_admission(item, genesis_digest=GENESIS) == reason
        # a forged anchor or proof never re-proves its digest, and a malformed one never builds
        forged_anchor = replace(valid, anchor=replace(valid.anchor, anchor_reference="forged"))
        forged = replace(valid, trigger_time_ns=TAU - 1)
        for item in (forged_anchor, forged, replace(valid, sealed_input_digests=())):
            with pytest.raises(GovernedPaperProtectiveLedgerError):
                governed_paper_integrity_proof_admission(item, genesis_digest=GENESIS)
        with pytest.raises(GovernedPaperProtectiveLedgerError, match="integrity_proof_malformed:trigger_kind$"):
            proof(kind=K.KS3_CLOSE)  # KS-3 and SS-3 are never an integrity proof
        # a context is re-proven whole: a refused, late, duplicated or unordered proof fails it, never skipped
        later = proof(TAU + HOUR, K.SS4_FLATTEN)
        governed_paper_protective_ledger_canonical_context(
            GovernedPaperProtectiveLedgerContext((valid, later)), genesis_digest=GENESIS, horizon_ns=lifet.LONG_RUN
        )
        for proofs, reason in (
            (
                (proof(verifier=GovernedPaperIntegrityVerifierKind.EXECUTOR_SELF_REPORT),),
                "integrity_proof_not_admitted",
            ),
            ((valid,), "integrity_proof_unknown_at_the_horizon"),
            ((later, valid), "integrity_proofs_not_ordered_unique"),
            ((valid, valid), "integrity_proofs_not_ordered_unique"),
        ):
            horizon = TAU if reason == "integrity_proof_unknown_at_the_horizon" else lifet.LONG_RUN
            with pytest.raises(GovernedPaperProtectiveLedgerError, match=reason):
                governed_paper_protective_ledger_canonical_context(
                    GovernedPaperProtectiveLedgerContext(proofs), genesis_digest=GENESIS, horizon_ns=horizon
                )
    with pytest.raises(GovernedPaperProtectiveLedgerError, match="integrity_proof_not_admitted:synthetic_anchor"):
        governed_paper_protective_ledger_canonical_context(
            GovernedPaperProtectiveLedgerContext((valid,)), genesis_digest=GENESIS, horizon_ns=lifet.LONG_RUN
        )


def test_the_bounds_halt_from_the_earliest_proof_and_flatten_only_on_an_independent_book() -> None:
    book = baseline()[0].dataset.source_manifest_digest
    with integrity_table(TEST_ONLY_TABLE):
        for proofs, expected in (
            ((), (None, ())),
            ((proof(),), (TAU, (HistoricalExecutionFlattenWindow(TAU, lifet.LONG_RUN, proof().proof_digest),))),
            ((proof(scope=(book,)),), (TAU, ())),  # the lineage's own book is the threatened component
            ((proof(complete=False),), (TAU, ())),  # an unknown threat scope
            (
                (proof(), proof(TAU + HOUR, K.SS4_FLATTEN, complete=False)),
                (TAU, (HistoricalExecutionFlattenWindow(TAU, TAU + HOUR, proof().proof_digest),)),
            ),  # a later unknown scope ends the window: the book is never trusted again
        ):
            context = governed_paper_protective_ledger_canonical_context(
                GovernedPaperProtectiveLedgerContext(proofs), genesis_digest=GENESIS, horizon_ns=lifet.LONG_RUN
            )
            assert (
                governed_paper_protective_ledger_schedule_bounds(
                    context, book_source_digest=book, horizon_ns=lifet.LONG_RUN
                )
                == expected
            )


def test_an_integrity_flatten_records_its_child_its_unfulfilled_instant_deadline_and_the_discharge() -> None:
    with integrity_table(TEST_ONLY_TABLE):
        outcome, evidence = ledger_for(baseline(), proofs=(proof(),))
    (schedule,) = evidence.schedules
    (obligation,) = schedule.obligations
    assert (obligation.trigger_kind, obligation.integrity_class, obligation.opened_ns, obligation.deadline_ns) == (
        K.KS4_FLATTEN,
        True,
        TAU,
        TAU,
    )
    assert (obligation.caps.participation_method, obligation.caps.impact_measure) == ("EXEMPT_IR5", "EXEMPT_IR5")
    one, zero = lifet.d(1), lifet.d(0)
    filled_at = lifet.book_visible(41)
    assert events_of(evidence) == [
        (E.OPENED, TAU, one, zero, one, None),
        (E.CHILD_SENT, TAU, one, zero, one, None),
        (E.DEADLINE_MISSED, TAU, "", zero, one, (R.ENGINE_UNREPRESENTABLE, one)),  # no fill at its own instant
        (E.CHILD_FILLED, filled_at, one, one, zero, None),
        (E.DISCHARGED, filled_at, "", one, zero, None),
    ]
    missed = schedule.events[2].unfulfilled
    assert missed.schema_version == GOVERNED_PAPER_UNFULFILLED_PROTECTIVE_OBLIGATION_SCHEMA  # type: ignore[union-attr]
    assert (schedule.status, schedule.discharged_at_ns, schedule.anchor_q0) == (
        GovernedPaperProtectiveScheduleStatus.DISCHARGED,
        filled_at,
        one,
    )
    ((child, fill),) = children_of(outcome)
    (record,) = schedule.children
    assert (record.outcome, record.filled_quantity, record.vwap) == ("FILLED", one, fill.fill_price)
    assert [item.source.value for item in schedule.attributed_fills] == ["CHILD"]
    # every later entry is refused by the halt; the obligation is open from its instant until the discharge
    assert governed_paper_protective_ledger_halted_at(evidence, TAU) and not governed_paper_protective_ledger_halted_at(
        evidence, TAU - 1
    )
    assert governed_paper_protective_ledger_open_at(evidence, TAU) == (obligation.obligation_id,)
    assert governed_paper_protective_ledger_open_at(evidence, filled_at) == ()
    assert (evidence.open_obligation_count, evidence.nonurgent_child_sent, evidence.target_path_defined) == (
        0,
        False,
        False,
    )
    assert no_target_anywhere(governed_paper_protective_ledger_evidence_to_dict(evidence))


def test_a_partial_and_a_rejected_child_are_recorded_and_counted_once() -> None:
    with integrity_table(TEST_ONLY_TABLE):
        _, thin = ledger_for(world_of(THIN), proofs=(proof(),))
        _, wide = ledger_for(world_of(WIDE_ONCE), proofs=(proof(),))
    half, one, zero = lifet.d("0.5"), lifet.d(1), lifet.d(0)
    assert [entry[:5] for entry in events_of(thin)] == [
        (E.OPENED, TAU, one, zero, one),
        (E.CHILD_SENT, TAU, one, zero, one),
        (E.DEADLINE_MISSED, TAU, "", zero, one),
        (E.CHILD_FILLED, lifet.book_visible(41), half, half, half),
        (E.CHILD_SENT, lifet.book_visible(41), half, half, half),
        (E.CHILD_FILLED, lifet.book_visible(42), half, one, zero),
        (E.DISCHARGED, lifet.book_visible(42), "", one, zero),
    ]
    (schedule,) = thin.schedules
    assert [item.quantity for item in schedule.attributed_fills] == [half, half]
    assert len({item.fill_id for item in schedule.attributed_fills}) == 2  # each fill once
    assert [entry[:2] for entry in events_of(wide)] == [
        (E.OPENED, TAU),
        (E.CHILD_SENT, TAU),
        (E.DEADLINE_MISSED, TAU),
        (E.BOOK_UNAVAILABLE, lifet.book_visible(41)),
        (E.CHILD_SENT, lifet.book_visible(41) + 30 * SECOND),
        (E.CHILD_FILLED, lifet.book_visible(42)),
        (E.DISCHARGED, lifet.book_visible(42)),
    ]
    assert wide.schedules[0].events[3].reason == "spread_exceeds_max"


def test_an_integrity_obligation_without_dec1_or_an_independent_book_sends_no_child_and_records_why() -> None:
    later = TAU + HOUR
    windows = (
        HistoricalExecutionProtectiveWindow(lifet.ANCHOR, TAU - HOUR, "a" * 64),
        HistoricalExecutionProtectiveWindow(later, lifet.LONG_RUN, "a" * 64),
    )
    book = baseline()[0].dataset.source_manifest_digest
    with integrity_table(TEST_ONLY_TABLE):
        _, authority = ledger_for(baseline(), proofs=(proof(),), protective=windows)
        _, threatened = ledger_for(baseline(), proofs=(proof(scope=(book,)),))
    one = lifet.d(1)
    assert [(entry[0], entry[1], entry[5]) for entry in events_of(authority)][:4] == [
        (E.OPENED, TAU, None),
        (E.AUTHORITY_UNPROVEN, TAU, None),  # the engine's refused child: no CHILD_SENT
        (E.DEADLINE_MISSED, TAU, (R.AUTHORITY_UNPROVEN, one)),
        (E.CHILD_SENT, later, None),  # the next DEC-1 window resumes it
    ]
    assert events_of(authority)[-1][0] is E.DISCHARGED
    deadline = opened_at(baseline()[3]) + 24 * HOUR
    assert [(entry[0], entry[1], entry[5]) for entry in events_of(threatened)] == [
        (E.OPENED, TAU, None),
        (E.INTEGRITY_UNPROVEN, TAU, None),
        (E.DEADLINE_MISSED, TAU, (R.INTEGRITY_UNPROVEN, one)),
        (E.DISCHARGED, deadline + 15 * MINUTE, None),  # the v1 MAX_HOLD close, counted in C, never a child
    ]
    (schedule,) = threatened.schedules
    assert schedule.children == () and [item.source.value for item in schedule.attributed_fills] == ["V1_ATTEMPT"]


def test_a_proven_halt_without_a_position_opens_no_obligation() -> None:
    _, _, _, reference = baseline()
    before = opened_at(reference) - 1
    with integrity_table(TEST_ONLY_TABLE):
        outcome, evidence = ledger_for(baseline(), proofs=(proof(before),))
    assert outcome.position_transitions == () and evidence.schedules == ()
    assert (evidence.integrity_halt_from_ns, len(evidence.integrity_triggers)) == (before, 1)
    assert governed_paper_protective_ledger_open_at(evidence, lifet.LONG_RUN - 1) == ()
    assert governed_paper_protective_ledger_halted_at(evidence, before)


def test_ss3_opens_a_nonurgent_obligation_that_records_cap_unproven_misses_its_deadline_and_sends_no_child() -> None:
    world = baseline()
    decisions = world[0].run.decisions
    first = crisis(decisions[1])
    assert first.state_lower_bound == 3  # CRISIS: the bound never exceeds it on the governed path
    _, evidence = ledger_for(world, readings=(first, crisis(decisions[2])))  # the repeat at D_2 appends nothing
    (schedule,) = evidence.schedules
    (obligation,) = schedule.obligations
    at = decisions[1].decision_time_ns
    assert (obligation.trigger_kind, obligation.integrity_class, obligation.deadline_ns - at, obligation.horizon) == (
        K.SS3_CLOSE,
        False,
        15 * MINUTE,
        "INTRADAY",
    )
    assert obligation.trigger_proof_digest == first.reading_digest
    assert (obligation.caps.participation_method, obligation.caps.impact_measure) == ("CAP_UNPROVEN", "CAP_UNPROVEN")
    one, zero = lifet.d(1), lifet.d(0)
    deadline = opened_at(world[3]) + 24 * HOUR
    assert events_of(evidence) == [
        (E.OPENED, at, one, zero, one, None),
        (E.CAP_UNPROVEN, at, "", zero, one, None),
        # the first injected instant at or after the deadline: the 24 h funding settlement
        (E.DEADLINE_MISSED, lifet.ANCHOR + 24 * HOUR, "", zero, one, (R.CAP_UNPROVEN, one)),
        (E.DISCHARGED, deadline + 15 * MINUTE, "", one, zero, None),  # the v1 MAX_HOLD close
    ]
    assert schedule.children == () and evidence.nonurgent_child_sent is False
    assert governed_paper_protective_ledger_open_at(evidence, at) == (obligation.obligation_id,)
    assert governed_paper_protective_ledger_open_at(evidence, at - 1) == ()


@functools.cache
def crash_world() -> tuple:
    """The kill-switch tests' SYNTHETIC crash: the D_0 SHORT valued ~16% of NAV down at D_1 proves T1, T2 and T11
    (KS-3, absorbing) while it is open; every later entry is refused, as the gate's NT-R01 would refuse it."""

    w, result, derived = kst.derived(kst.CRASH)
    at = kst.decided(1)
    later = tuple(item.decision_sequence for item in w.run.decisions if item.decision_time_ns > at)
    return w, result, lifet.both_sides(end=kst.END_2D, refused=later), derived.outcome


def test_ks3_from_the_authentic_ladder_opens_on_the_open_position_and_v1_precedence_names_the_missed_deadline() -> None:
    at = kst.decided(1)
    _, evidence = ledger_for(crash_world())
    (schedule,) = evidence.schedules
    (obligation,) = schedule.obligations
    assert (obligation.trigger_kind, obligation.opened_ns, obligation.deadline_ns) == (
        K.KS3_CLOSE,
        at,
        at + 30 * MINUTE,
    )
    kinds = [entry[0] for entry in events_of(evidence)]
    assert kinds == [E.OPENED, E.CAP_UNPROVEN, E.DISCHARGED]  # the v1 STOP's close-only fill discharges it
    # without a DEC-1 window after the crash the v1 stop is refused, the position stays open and the KS-3 deadline
    # passes while the v1 obligation holds the slot
    windows = (HistoricalExecutionProtectiveWindow(lifet.ANCHOR, at - HOUR, "a" * 64),)
    _, stuck = ledger_for(crash_world(), protective=windows)
    (schedule,) = stuck.schedules
    missed = [item for item in schedule.events if item.kind is E.DEADLINE_MISSED]
    assert [(item.unfulfilled.reason, item.unfulfilled.remaining_exposure) for item in missed] == [  # type: ignore[union-attr]
        (R.V1_PRECEDENCE, lifet.d(1))
    ]
    assert missed[0].time_ns >= at + 30 * MINUTE and schedule.status is GovernedPaperProtectiveScheduleStatus.OPEN
    assert stuck.open_obligation_count == 1
    # without a DEC-1 window at its instant the nonurgent obligation records AUTHORITY_UNPROVEN beside CAP_UNPROVEN,
    # and the deadline names its first failing link: the v1 obligation holding the slot
    assert [(item.kind, item.reason) for item in schedule.events[:3]] == [
        (E.OPENED, ""),
        (E.CAP_UNPROVEN, "nonurgent_demand_undefined_target_hc_11c_impact_hc_11f_participation_hd_04"),
        (E.AUTHORITY_UNPROVEN, "dec1_protective_window_absent"),
    ]


def test_a_joining_kind_appends_merged_without_rewriting_earlier_events_and_d_eff_never_moves_later() -> None:
    world = crash_world()
    decision = world[0].run.decisions[1]
    at = decision.decision_time_ns
    _, alone = ledger_for(world)
    _, merged = ledger_for(world, readings=(crisis(decision),))
    first, joined = alone.schedules[0], merged.schedules[0]
    assert joined.anchor_digest == first.anchor_digest and joined.events[:2] == first.events[:2]
    merge = joined.events[2]
    assert (merge.kind, merge.time_ns) == (E.MERGED, at)
    record = merge.merge
    assert record is not None and record.anchor_digest == first.anchor_digest
    assert (record.effective_deadline_before_ns, record.effective_deadline_after_ns) == (
        at + 30 * MINUTE,
        at + 15 * MINUTE,
    )  # the SS-3 INTRADAY deadline is earlier, so D_eff advances; it never moves later
    assert (record.in_flight_reference, record.closed_quantity) == ("v1_attempt", lifet.d(0))
    assert record.caps.participation_method == "CAP_UNPROVEN" and no_target_anywhere(
        governed_paper_protective_ledger_evidence_to_dict(merged)
    )
    assert [item.trigger_kind for item in joined.obligations] == [K.KS3_CLOSE, K.SS3_CLOSE]


def test_the_ledger_chain_anchor_and_prefix_are_content_stable_and_tamper_evident() -> None:
    world = baseline()
    decisions = world[0].run.decisions
    _, evidence = ledger_for(world, readings=(crisis(decisions[1]),))
    (schedule,) = evidence.schedules
    tampered = replace(schedule.events[1], reason="forged")
    broken = replace(schedule, events=(schedule.events[0], tampered, *schedule.events[2:]))
    assert not governed_paper_protective_ledger_event_chain_intact(broken)
    resealed = replace(tampered, event_digest=edge_payload_digest(ledger_module._to_payload(tampered), "event_digest"))  # noqa: SLF001
    assert not governed_paper_protective_ledger_event_chain_intact(
        replace(schedule, events=(schedule.events[0], resealed, *schedule.events[2:]))
    )  # a re-digested event breaks its successor's link
    assert governed_paper_protective_ledger_evidence_digest(replace(evidence, open_obligation_count=9)) != (
        evidence.evidence_digest
    )
    # a causal replay over a shorter horizon yields the same prefix
    short_end = lifet.ANCHOR + 30 * HOUR
    short_world = world_of(lifet.path_to(short_end, (lifet.POSITIVE,) * 6), short_end)
    _, shorter = ledger_for(short_world, readings=(crisis(short_world[0].run.decisions[1]),))
    for cut in (decisions[1].decision_time_ns, lifet.ANCHOR + 25 * HOUR, short_end):
        assert governed_paper_protective_ledger_prefix_digest(
            shorter, before_ns=cut
        ) == governed_paper_protective_ledger_prefix_digest(evidence, before_ns=cut)
    assert governed_paper_protective_ledger_prefix_digest(evidence, before_ns=lifet.LONG_RUN) != (
        governed_paper_protective_ledger_prefix_digest(shorter, before_ns=short_end)
    )  # the discharge after the shorter horizon is part of the longer prefix only


def test_the_ledger_never_accepts_a_foreign_or_mismatched_input() -> None:
    world = baseline()
    w, result, schedule, reference = world
    derived = derivation(world, v6_of(schedule, reference))
    policy = lifet.equity_policy(lifet.d(10_000))
    good = {
        "genesis_digest": GENESIS,
        "instrument": result.instrument,
        "start_ns": result.evaluation_start_ns,
        "outcome": derived.outcome,
        "ladder": derived.ladder,
        "system_states": (),
        "decision_instants": tuple(item.decision_time_ns for item in w.run.decisions),
        "context": GovernedPaperProtectiveLedgerContext(),
        "book_source_digest": w.dataset.source_manifest_digest,
        "depth_cap_fraction": policy.visible_depth_cap_fraction,
    }
    derive_governed_paper_protective_ledger(**good)  # type: ignore[arg-type]
    v4 = lifet.governed_under(result, schedule)
    other = derivation(world, v6_of(schedule, reference, TAU))
    for changes, reason in (
        ({"outcome": v4}, "outcome_needs_the_schedule_v6_re_run"),
        ({"outcome": replace(derived.outcome, terminal_state=None)}, "outcome_digest_mismatch"),
        ({"ladder": other.ladder}, "ladder_not_of_this_re_run"),
        ({"ladder": replace(derived.ladder, start_ns=1)}, "ladder_digest_mismatch"),
        (
            {"system_states": (replace(crisis(w.run.decisions[1]), state_lower_bound=4),)},
            "system_state_digest_mismatch",
        ),
        ({"outcome": other.outcome, "ladder": other.ladder}, "schedule_protective_ledger_bounds_not_derived"),
        ({"instrument": "OTHER-PERP"}, "outcome_not_of_this_instrument"),
        ({"depth_cap_fraction": "0.5000"}, "depth_cap_fraction_malformed"),
    ):
        with pytest.raises(GovernedPaperProtectiveLedgerError, match=reason):
            derive_governed_paper_protective_ledger(**{**good, **changes})  # type: ignore[arg-type]


def test_a_history_the_ledger_cannot_reconcile_records_position_unproven_and_never_re_anchors() -> None:
    world = baseline()
    w, result, schedule, reference = world
    decisions = w.run.decisions
    reading = crisis(decisions[1])
    derived = derivation(world, v6_of(schedule, reference))
    _, honest = ledger_for(world, readings=(reading,))
    # SYNTHETIC defect fixture (no supported engine run can produce it): the v1 close is re-reported as an increase to
    # -2, re-digested with the ladder bound to it, so only the ledger's own reconciliation can catch it
    close = derived.outcome.position_transitions[-1]
    forged_close = replace(close, transition_kind=HistoricalExecutionTransitionKind.INCREASE, post_quantity=lifet.d(-2))
    forged = replace(derived.outcome, position_transitions=(*derived.outcome.position_transitions[:-1], forged_close))
    forged = replace(forged, outcome_digest=historical_execution_governed_paper_outcome_digest(forged))
    ladder = replace(derived.ladder, governed_outcome_digest=forged.outcome_digest)
    ladder = replace(ladder, ladder_digest=governed_paper_kill_switch_ladder_digest(ladder))
    evidence = derive_governed_paper_protective_ledger(
        genesis_digest=GENESIS,
        instrument=result.instrument,
        start_ns=result.evaluation_start_ns,
        outcome=forged,
        ladder=ladder,
        system_states=(reading,),
        decision_instants=tuple(item.decision_time_ns for item in decisions),
        context=GovernedPaperProtectiveLedgerContext(),
        book_source_digest=w.dataset.source_manifest_digest,
        depth_cap_fraction=policy_of(result).visible_depth_cap_fraction,
    )
    (schedule_,) = evidence.schedules
    (original,) = honest.schedules
    assert schedule_.anchor_digest == original.anchor_digest and schedule_.events[:3] == original.events[:3]
    unproven = schedule_.events[3]
    assert (unproven.kind, unproven.time_ns, unproven.reason) == (
        E.POSITION_UNPROVEN,
        close.time_ns,
        "exposure_increased_after_the_anchor",
    )
    assert E.DISCHARGED not in [item.kind for item in schedule_.events]  # never a discharge on an unproven history
    assert (schedule_.status, schedule_.anchor_q0) == (GovernedPaperProtectiveScheduleStatus.OPEN, lifet.d(1))


# --- C. rule set v9 -------------------------------------------------------------------------------------------------------


def ledger_facts(open_ids: tuple[str, ...] = (), *, halted: bool = False) -> GovernedPaperEntrySafetyProtectiveLedger:
    return GovernedPaperEntrySafetyProtectiveLedger(open_ids, halted, "f" * 64)


def v9(facts: GovernedPaperEntrySafetyProtectiveLedger | None, **observation: object):  # noqa: ANN201
    return replace(sct.v8(**observation), protective_ledger=facts)


def test_rule_set_v9_adds_only_protective_ledger_and_v1_to_v8_keep_their_identities() -> None:
    v8, v9_set = (
        GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET,
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET,
    )
    assert v9_set["rule_set_id"] == GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_ID
    assert [item["check_id"] for item in v9_set["checks"]] == [
        *(item["check_id"] for item in v8["checks"]),
        "PROTECTIVE-LEDGER",
    ]  # type: ignore[index,union-attr]
    assert (
        governed_paper_entry_safety_rule_set_digest(
            protective=True,
            portfolio=True,
            market_data=True,
            kill_switch=True,
            regime=True,
            system_safety=True,
            sizing_chain=True,
        )
        == GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST
    )
    assert GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_DIGEST not in (
        GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST,
    )
    assert sct.ACCEPTED_MAIN_RULE_SET_V7_DIGEST == governed_paper_entry_safety_rule_set_digest(
        protective=True, portfolio=True, market_data=True, kill_switch=True, regime=True, system_safety=True
    )
    with pytest.raises(GovernedPaperEntrySafetyError, match="protective_ledger_rule_set_needs_the_sizing_chain"):
        governed_paper_entry_safety_rule_set(protective_ledger=True)
    rule = v9_set["protective_ledger_rule"]
    assert rule["pending_never_read"] == ["HC-11c", "HC-11f", "HD-04", "HC-05d"]  # type: ignore[index]


def test_protective_ledger_fails_while_open_or_halted_passes_otherwise_and_the_first_refusal_never_moves() -> None:
    baseline_v8 = evaluate_governed_paper_entry_safety(sct.v8())
    for facts, status, reason in (
        (ledger_facts(), S.PASS, "no_v2_obligation_open_and_no_integrity_halt"),
        (ledger_facts(("a" * 64,)), S.FAIL, "v2_protective_obligation_open_entries_refused"),
        (ledger_facts(halted=True), S.FAIL, "proven_integrity_trigger_halts_every_exposure_increase"),
        (ledger_facts(("a" * 64,), halted=True), S.FAIL, "proven_integrity_trigger_halts_every_exposure_increase"),
    ):
        decided = evaluate_governed_paper_entry_safety(v9(facts))
        check = decided.checks[-1]
        assert (check.check_id, check.status, check.reason) == (
            "PROTECTIVE-LEDGER",
            status,
            est.code(f"PROTECTIVE-LEDGER:{reason}"),
        )
        assert check.evidence_record_digests[0] == "f" * 64  # the ledger evidence it read
        assert [item.check_id for item in decided.checks[:-1]] == [item.check_id for item in baseline_v8.checks]
        assert decided.first_failure_check_id == baseline_v8.first_failure_check_id  # every S1 entry: same refusal
        assert decided.entry_permitted is False


@pytest.mark.parametrize(
    "facts",
    [
        GovernedPaperEntrySafetyProtectiveLedger(("x",), False, "f" * 64),
        GovernedPaperEntrySafetyProtectiveLedger(("a" * 64, "a" * 64), False, "f" * 64),
        GovernedPaperEntrySafetyProtectiveLedger((), 0, "f" * 64),  # type: ignore[arg-type]
        GovernedPaperEntrySafetyProtectiveLedger((), False, "nope"),
        GovernedPaperEntrySafetyProtectiveLedger([], False, "f" * 64),  # type: ignore[arg-type]
    ],
)
def test_malformed_ledger_facts_are_refused(facts: GovernedPaperEntrySafetyProtectiveLedger) -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match="observation_malformed:protective_ledger"):
        evaluate_governed_paper_entry_safety(v9(facts))


def test_ledger_facts_need_the_rule_set_v8_facts() -> None:
    with pytest.raises(GovernedPaperEntrySafetyError, match="protective_ledger_without_the_sizing_facts"):
        evaluate_governed_paper_entry_safety(replace(sct.v8(), sizing=None, protective_ledger=ledger_facts()))


# --- D. world G's protective ledger lineage (seal v10, evidence v10) --------------------------------------------------------

V9_SEAL, V10_SEAL = "governed-paper-day-seal.v9", "governed-paper-day-seal.v10"
V10_EVIDENCE = "governed-paper-execution-evidence.v10"
SEALED = GovernedPaperDaySealStatus.SEALED
NO_PROOFS = GovernedPaperProtectiveLedgerContext()
V10_FIELDS = (
    "protective_ledger_evidence_digest",
    "protective_ledger_prefix_digest_open",
    "protective_ledger_prefix_digest_close",
    "integrity_proof_digests",
    "pending_protective_child_time_ns",
    "open_protective_ledger_obligation_count",
)
# What a v10 day keeps of the v9 day exactly. Outcome v4 adds the child ledger and schedule v6 its bounds, so the governed
# outcome and its prefix digests, the ladder and every evidence that binds them move.
LEDGER_UNCHANGED = (
    *(name for name in sct.UNCHANGED if not name.startswith("prefix_digest")),
    "sizing_evidence_digest",
    "ctr_qualification_digest",
    "ctr_revocation_digests",
    "ctr_capture_digest",
    "dataset_digest",
)
# The accepted-main identities of rule set v8 and of world G's sizing chain lineage (seal v9, evidence v9) under the
# TEST-ONLY regime table, pinned on main 2992ae3f before this contract.
ACCEPTED_MAIN_RULE_SET_V8_DIGEST = "99f516414bfc1d43256f9b7d074bb2cc55f4a8927876859acf45ef57ba1d867d"
ACCEPTED_MAIN_V9_SEALS = (
    "3bfe792798a87dce43f6d67c82ec89a1ec0ffe5486eaf4d6b5fd65a57f8aa989",
    "1b92c33aba1e7bbcbb5c02dbefb5f05ae6867db35e4b240034e3bf9be87b74c1",
    "023b6b7f1381466f2d4c155bd0a307f2544602a422e34ebd2419a605ed35504b",
    "7183a2d10465da1199159e2588bb2928f8670a1d2eaf0f37092ca42fed835509",
)
ACCEPTED_MAIN_V9_ENTRY_EVIDENCE = (
    "89c345629f99247e9eeaa54366d3a699069a3a151d218b8298141610b36a224b",
    "2fcb86afe5dfa7b491271eed77cabd95f0b26a72ef95fe001235e7a1d93ad802",
    "b8949d1edd35ba2eb8ffc1b8eefb5d613f19e8c88295b670a5bae4045eb91864",
    "1e1f5d00260fd6e89a7aeae6835b199f1b1318dafe4e820770f5a02b28ff629e",
)
ACCEPTED_MAIN_V9_LINEAGE_EVIDENCE = "3b1de90e98bbf97836aa9b0afd1af64aba083c2e6111314e5273df51563a8936"


@pytest.fixture(autouse=True, scope="module")
def _production_tables_with_exact_memos():
    """The sizing chain tests' exact upstream memos and identity memos of pure re-proofs; every PRODUCTION rule and
    approval table stays (a TEST-ONLY table is installed only where a test says so)."""

    with pytest.MonkeyPatch.context() as patch:
        gpe.apply_memos(patch)
        archives = gpe.SameObjects(regime.verify_historical_ohlc_bar_archive)
        patch.setattr(regime, "verify_historical_ohlc_bar_archive", archives)
        patch.setattr(gpe.execution, "verify_historical_ohlc_bar_archive", archives)
        exact = gpe._EXACT[(gpe.execution, "verify_historical_pit_dataset")]  # noqa: SLF001
        patch.setattr(regime, "verify_historical_pit_dataset", exact)
        patch.setattr(ctr, "verify_historical_pit_dataset", exact)
        assert entry_safety._CHECKS is sct.PRODUCTION_CHECKS  # noqa: SLF001
        assert ledger_module._APPROVAL_TABLE is PRODUCTION_LEDGER_TABLE  # noqa: SLF001
        yield


def ledger_inputs(days: tuple, context: object):  # noqa: ANN201
    """The cycle and seal inputs of the day after ``days`` of world G on the protective ledger lineage."""

    world = gpe.scenario("G")
    day = len(days)
    prior = days[-1].seal if days else None
    cycle_inputs = gpe.cycle_inputs_for(day, prior, world=world)
    cycle = build_governed_paper_cycle_authority(cycle_inputs)
    protection = replace(
        lineage.protection_for(
            day, days, portfolio_no_trade=True, market_data_integrity=True, kill_switch_escalation=True
        ),
        regime=rst.regime_context(day),
        system_safety=True,
        sizing=sct.NO_SOURCE,
        protective_ledger=context,
    )
    seal_inputs = gpe.seal_inputs_for(
        day, cycle_inputs, cycle, prior, gpe.pending_of(days), world=world, protection=protection
    )
    return cycle_inputs, cycle, seal_inputs


def ledger_day(days: tuple, context: object):  # noqa: ANN201
    """Open, run and seal the day after ``days`` of world G with the ledger ``context`` (TEST-ONLY regime and integrity
    tables)."""

    cycle_inputs, cycle, seal_inputs = ledger_inputs(days, context)
    with rst.approval_table(rst.TEST_ONLY_TABLE), integrity_table(TEST_ONLY_TABLE):
        seal = build_governed_paper_day_seal(seal_inputs)
    return gpe.Day(cycle_inputs, cycle, seal_inputs, seal)


@functools.cache
def ledger_days(count: int) -> tuple:
    """World G's first ``count`` days of the protective ledger lineage (seal v10) without an integrity proof."""

    if count == 0:
        return ()
    days = ledger_days(count - 1)
    return (*days, ledger_day(days, NO_PROOFS))


@functools.cache
def world_g_proof(
    at: int, kind: GovernedPaperProtectiveObligationKind = K.KS4_FLATTEN
) -> GovernedPaperIntegrityTriggerProof:
    """A SYNTHETIC IR-2 proof of world G's lineage triggered at ``at``, its anchor approved at G."""

    return proof(at, kind, genesis=ledger_days(1)[0].seal.genesis_digest, approved_at_ns=gpe.instant(0))


def verified(item: object):  # noqa: ANN201
    with integrity_table(TEST_ONLY_TABLE):
        return rst.verify(item.seal, item.seal_inputs)  # type: ignore[attr-defined]


def lineage_evidence(days: tuple) -> tuple:
    with rst.approval_table(rst.TEST_ONLY_TABLE), integrity_table(TEST_ONLY_TABLE):
        evidence = build_governed_paper_execution_evidence(gpe.evidence_inputs(days))
        verification = verify_governed_paper_execution_evidence(evidence, gpe.evidence_inputs(days))
    return evidence, verification


def ledger_gate(item: object, day: int, context: object, schedule: object | None = None):  # noqa: ANN201
    """Day ``day``'s rule set v9 evaluation of ``item``, rebuilt independently through the public builders."""

    authority, run, _ = est.run_and_evidence(item)
    economics = lineage.protected_replay(item)[0]
    with rst.approval_table(rst.TEST_ONLY_TABLE), integrity_table(TEST_ONLY_TABLE):
        return build_governed_paper_entry_safety_evidence(
            authority=authority,
            run=run,
            dataset=item.seal_inputs.dataset,  # type: ignore[attr-defined]
            invalidated_from_ns=None,
            protection=est.seal_protection(item),
            portfolio=GovernedPaperEntrySafetyPortfolio(
                economics,
                item.seal.schedule if schedule is None else schedule,  # type: ignore[attr-defined]
            ),
            market_data=True,
            kill_switch=True,
            regime=rst.regime_context(day),
            system_safety=True,
            sizing=sct.NO_SOURCE,
            protective_ledger=context,
        )


def checks_of(decision: object) -> list[tuple]:
    return [
        (item.check_id, item.status, item.observed, item.threshold, item.reason)
        for item in decision.checks  # type: ignore[attr-defined]
    ]


def test_world_g_ledger_lineage_changes_only_its_version_schedule_rule_set_and_ledger_bindings() -> None:
    days, legacy = ledger_days(4), sct.sizing_days(4)
    for day, (item, old) in enumerate(zip(days, legacy, strict=True)):
        seal = item.seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V10_SEAL, SEALED, ())
        assert seal.entry_safety_rule_set_digest == GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_DIGEST
        for name in LEDGER_UNCHANGED:
            assert getattr(seal, name) == getattr(old.seal, name), name
        assert seal.schedule == replace(old.seal.schedule, schema_version=V6)  # no proof: no halt, no flatten window
        assert (
            seal.integrity_proof_digests,
            seal.pending_protective_child_time_ns,
            seal.open_protective_ledger_obligation_count,
        ) == ((), None, 0)
        if day:
            assert seal.protective_ledger_prefix_digest_open == days[day - 1].seal.protective_ledger_prefix_digest_close
        verification = verified(item)
        assert (verification.intact, verification.reason_codes) == (True, ())
    (entry,) = days[3].seal.entry_safety_decisions
    (old_entry,) = legacy[3].seal.entry_safety_decisions
    assert checks_of(entry)[:-1] == checks_of(old_entry)  # every rule set v8 outcome is unchanged
    assert (entry.entry_permitted, entry.first_failure_check_id) == (False, "NT-D01")  # no new admission
    last = entry.checks[-1]
    assert (last.check_id, last.status, last.observed, last.reason, last.evidence_record_digests) == (
        "PROTECTIVE-LEDGER",
        S.PASS,
        "0",
        est.code("PROTECTIVE-LEDGER:no_v2_obligation_open_and_no_integrity_halt"),
        (days[3].seal.protective_ledger_evidence_digest,),
    )
    evidence, verification = lineage_evidence(days)
    assert (evidence.schema_version, evidence.status) == (V10_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())
    payload = governed_paper_day_seal_to_dict(days[3].seal)
    legacy_payload = governed_paper_day_seal_to_dict(legacy[3].seal)
    assert set(payload) - set(V10_FIELDS) == set(legacy_payload)  # seal v10 adds exactly its six fields


def test_the_public_gate_replays_the_sealed_ledger_and_a_legacy_gate_never_carries_one() -> None:
    item = ledger_days(4)[3]
    evidence = ledger_gate(item, 3, NO_PROOFS)
    assert (evidence.rule_set_id, evidence.evidence_digest) == (
        GOVERNED_PAPER_ENTRY_SAFETY_PROTECTIVE_LEDGER_RULE_SET_ID,
        item.seal.entry_safety_evidence_digest,
    )
    ledger = evidence.protective_ledger_evidence
    assert ledger is not None and ledger.evidence_digest == item.seal.protective_ledger_evidence_digest
    assert ledger.evidence_digest == governed_paper_protective_ledger_evidence_digest(ledger)
    assert (ledger.genesis_digest, ledger.book_source_digest, ledger.governed_outcome_digest) == (
        item.seal.genesis_digest,
        item.seal_inputs.dataset.source_manifest_digest,
        item.seal.governed_outcome_digest,
    )
    assert (
        ledger.integrity_triggers,
        ledger.integrity_halt_from_ns,
        ledger.schedules,
        ledger.open_obligation_count,
    ) == (
        (),
        None,
        (),
        0,
    )  # world G's integrated lineage never holds a position: no KS3, no SS3, no proof
    for before, sealed in (
        (gpe.instant(3), item.seal.protective_ledger_prefix_digest_open),
        (gpe.instant(4), item.seal.protective_ledger_prefix_digest_close),
    ):
        assert governed_paper_protective_ledger_prefix_digest(ledger, before_ns=before) == sealed
    assert no_target_anywhere(governed_paper_protective_ledger_evidence_to_dict(ledger))
    legacy = sct.sizing_gate(3)[1]  # rule set v8, rebuilt through the public builders
    assert "protective_ledger_evidence" not in governed_paper_entry_safety_evidence_to_dict(legacy)
    with pytest.raises(ValueError, match="legacy_rule_set_carries_a_protective_ledger_evidence$"):
        governed_paper_entry_safety_evidence_to_dict(replace(legacy, protective_ledger_evidence=ledger))
    for schedule, context, reason in (
        (item.seal.schedule, None, "protective_ledger_schedule_and_rule_set_mismatch"),
        (sct.sizing_days(4)[3].seal.schedule, NO_PROOFS, "protective_ledger_schedule_and_rule_set_mismatch"),
        (item.seal.schedule, object(), "protective_ledger_context_malformed"),
        (
            replace(item.seal.schedule, exposure_halt_from_ns=gpe.instant(3)),
            NO_PROOFS,
            "protective_ledger_not_derivable",
        ),
    ):
        with pytest.raises(GovernedPaperEntrySafetyError, match=f"{reason}$"):
            ledger_gate(item, 3, context, schedule)


def test_a_ledger_lineage_is_one_from_day_0_or_never_and_only_on_a_sizing_chain_lineage() -> None:
    days, legacy = ledger_days(2), sct.sizing_days(2)
    for item, changes, reason in (
        (days[1], {"protective_ledger": None}, "protective_ledger_lineage_switched"),
        (legacy[1], {"protective_ledger": NO_PROOFS}, "protective_ledger_lineage_switched"),
        (days[0], {"sizing": None}, "protective_ledger_needs_the_sizing_chain_lineage"),
        (days[1], {"protective_ledger": object()}, "protection_inputs_malformed:protective_ledger"),
    ):
        with rst.approval_table(rst.TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(kst.switched(item, **changes))
    assert rst.verify(replace(days[1].seal, schema_version=V9_SEAL), days[1].seal_inputs).intact is False
    with pytest.raises(ValueError, match="legacy_schema_carries_an_extension_field:protective_ledger_evidence_digest$"):
        gpe.reseal_seal(days[1].seal, schema_version=V9_SEAL)
    for forged in (
        replace(legacy[1].seal, schema_version=V10_SEAL),
        gpe.reseal_seal(legacy[1].seal, schema_version=V10_SEAL),
    ):
        assert rst.verify(forged, legacy[1].seal_inputs).intact is False
    for changes in (
        {"protective_ledger_evidence_digest": "0" * 64},
        {"protective_ledger_prefix_digest_close": "0" * 64},
        {"integrity_proof_digests": ("0" * 64,)},
        {"open_protective_ledger_obligation_count": 1},
        {"pending_protective_child_time_ns": gpe.instant(1)},
    ):
        assert rst.verify(gpe.reseal_seal(days[1].seal, **changes), days[1].seal_inputs).intact is False


@functools.cache
def proven_days() -> tuple:
    """World G's day 0 and a day 1 that adds one SYNTHETIC KS4 proof triggered 1 h after E_1 (world G is flat)."""

    days = ledger_days(1)
    return (*days, ledger_day(days, GovernedPaperProtectiveLedgerContext((world_g_proof(gpe.instant(1) + HOUR),))))


def test_a_proof_binds_its_halt_stays_append_only_inside_its_day_and_never_verifies_on_production() -> None:
    days = proven_days()
    trigger = world_g_proof(gpe.instant(1) + HOUR)
    seal = days[1].seal
    assert (seal.schema_version, seal.status, seal.reason_codes) == (V10_SEAL, SEALED, ())
    assert seal.integrity_proof_digests == (trigger.proof_digest,)
    assert (seal.schedule.exposure_halt_from_ns, seal.schedule.flatten_windows) == (
        trigger.trigger_time_ns,
        (HistoricalExecutionFlattenWindow(trigger.trigger_time_ns, gpe.instant(2), trigger.proof_digest),),
    )  # the halt from the proof's instant on; one flatten window to the horizon on an independent book
    assert (seal.open_protective_ledger_obligation_count, seal.pending_protective_child_time_ns) == (0, None)  # flat
    unproven = ledger_days(2)[1].seal
    for name in ("prefix_digest_open", "protective_ledger_prefix_digest_open", "economics_result_digest", "episodes"):
        assert getattr(seal, name) == getattr(unproven, name), name  # a trigger rewrites nothing before it
    assert seal.protective_ledger_prefix_digest_close != unproven.protective_ledger_prefix_digest_close
    verification = verified(days[1])
    assert (verification.intact, verification.reason_codes) == (True, ())
    # the PRODUCTION integrity table admits no anchor: the seal never re-verifies and no day seals on the proof
    assert ledger_module._APPROVAL_TABLE is GOVERNED_PAPER_INTEGRITY_PRODUCTION_APPROVAL_TABLE  # noqa: SLF001
    assert rst.verify_unmemoized(seal, days[1].seal_inputs, rst.TEST_ONLY_TABLE).intact is False
    _, _, production = ledger_inputs(days[:1], GovernedPaperProtectiveLedgerContext((trigger,)))
    with rst.approval_table(rst.TEST_ONLY_TABLE), gpe.refused("integrity_proofs_not_authentic"):
        build_governed_paper_day_seal(production)
    # append-only, and each new proof is known inside the day that adds it
    for context, reason in (
        (NO_PROOFS, "integrity_proofs_rewritten"),
        (
            GovernedPaperProtectiveLedgerContext((world_g_proof(gpe.instant(2) + HOUR, K.SS4_FLATTEN),)),
            "integrity_proofs_rewritten",
        ),
        (
            GovernedPaperProtectiveLedgerContext((trigger, world_g_proof(gpe.instant(2) - 1, K.SS4_FLATTEN))),
            "integrity_proof_outside_the_sealed_day",
        ),
        (
            GovernedPaperProtectiveLedgerContext((trigger, world_g_proof(gpe.instant(3), K.SS4_FLATTEN))),
            "integrity_proofs_not_authentic",
        ),  # triggered at E_3: unknown at the day's horizon
    ):
        _, _, inputs = ledger_inputs(days, context)
        with rst.approval_table(rst.TEST_ONLY_TABLE), integrity_table(TEST_ONLY_TABLE), gpe.refused(reason):
            build_governed_paper_day_seal(inputs)


# --- the end-to-end flatten under TEST-ONLY permissive entry and sizing tables ----------------------------------------------


def whole_horizon_envelope(timeline: object, *, edge_id: str) -> tuple:
    """SYNTHETIC, TEST-ONLY: one envelope of fraction 1 over the whole horizon (production proves no allocation)."""

    return (HistoricalExecutionExposureEnvelope(timeline.start_ns, timeline.horizon_ns, "1"),)  # type: ignore[attr-defined]


def unbounded_caps(**values: object) -> tuple:
    """SYNTHETIC, TEST-ONLY: a 10^6 cap on every book an entry may execute against (production qualifies no CTR)."""

    run, depth = values["run"], values["depth"]
    latency, delay = values["latency_ns"], values["max_execution_delay_ns"]
    caps: dict[tuple[str, str], HistoricalExecutionDepthCap] = {}
    for _, instant, direction in sizing_module._entries(run):  # noqa: SLF001
        side = sizing_module._ENTRY_DIRECTIONS[direction]  # noqa: SLF001
        for record in depth.records_visible_between(instant + latency, instant + delay):  # type: ignore[attr-defined,operator]
            caps[(record.record_digest, side.value)] = HistoricalExecutionDepthCap(
                record.record_digest, side, "1000000"
            )
    return tuple(caps[key] for key in sorted(caps))


@contextlib.contextmanager
def permissive_entries() -> Iterator[None]:
    """SYNTHETIC, TEST-ONLY: every rule set v1-v8 check passes and the sizing bounds admit every entry fill, so world G
    opens a position; PROTECTIVE-LEDGER, the ledger, the engine and the seal stay the production code."""

    ledger_check = entry_safety._PROTECTIVE_LEDGER_CHECKS[-1]  # noqa: SLF001
    assert ledger_check.check_id == "PROTECTIVE-LEDGER"
    with pytest.MonkeyPatch.context() as patch:
        permissive = tuple(replace(item, evaluate=gpe._test_only_permissive_check) for item in sct.PRODUCTION_CHECKS)  # noqa: SLF001
        patch.setattr(entry_safety, "_CHECKS", permissive)
        patch.setattr(entry_safety, "_REGIME_CHECKS", ())
        patch.setattr(entry_safety, "_PROTECTIVE_LEDGER_CHECKS", (ledger_check,))
        patch.setattr(sizing_module, "governed_paper_sizing_exposure_envelopes", whole_horizon_envelope)
        patch.setattr(sizing_module, "governed_paper_sizing_depth_caps", unbounded_caps)
        yield
    assert entry_safety._CHECKS is sct.PRODUCTION_CHECKS  # noqa: SLF001


def test_end_to_end_a_proven_trigger_flattens_world_gs_open_short_through_one_close_only_child() -> None:
    prefix = ledger_days(3)  # no entry is decided before day 3: the lineage opens on the production lineage's own days
    tau = gpe.instant(3) + 2 * HOUR  # 2 h after the day 3 SHORT is decided and filled
    trigger = world_g_proof(tau)
    context = GovernedPaperProtectiveLedgerContext((trigger,))
    with permissive_entries():
        days = prefix
        for _ in range(3):
            days = (*days, ledger_day(days, context))
        outcome = lineage.protected_replay(days[5])[1]
        gate = ledger_gate(days[5], 5, context)
        evidence, verification = lineage_evidence(days)
    # the engine: the SHORT opens before tau; one whole close-only child at tau waits for a book and closes it on day 5
    assert outcome.schema_version == OUTCOME_V4
    opened, closed = outcome.position_transitions
    assert (opened.transition_kind, opened.post_quantity) == (HistoricalExecutionTransitionKind.OPEN, lifet.d(-1))
    assert gpe.instant(3) < opened.time_ns < tau
    ((child, fill),) = children_of(outcome)
    assert (child.attempt_time_ns, child.side, child.requested_quantity, child.position_quantity) == (
        tau,
        HistoricalExecutionSide.BUY,
        lifet.d(1),
        lifet.d(-1),
    )
    assert child.flatten_authority_digest == trigger.proof_digest
    assert (fill.outcome, fill.filled_quantity) == (FILLED, lifet.d(1))
    assert fill.execution_time_ns > gpe.instant(5)  # no eligible book before day 5: in flight across two seals
    assert (closed.transition_kind, closed.time_ns, closed.post_quantity) == (
        HistoricalExecutionTransitionKind.CLOSE,
        fill.execution_time_ns,
        lifet.d(0),
    )
    # the v1 MAX_HOLD obligation opened while the child was in flight waits for it (one in flight) and is discharged
    (obligation,) = outcome.protective_obligations
    assert (obligation.status.value, outcome.protective_attempts) == ("DISCHARGED", ())
    # the seals: the halt and the flatten window to each horizon, the pending child by its instant, X1 on both prefixes
    for day in (3, 4, 5):
        seal, prior = days[day].seal, days[day - 1].seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V10_SEAL, SEALED, ())
        assert seal.integrity_proof_digests == (trigger.proof_digest,)
        assert (seal.schedule.exposure_halt_from_ns, seal.schedule.flatten_windows) == (
            tau,
            (HistoricalExecutionFlattenWindow(tau, gpe.instant(day + 1), trigger.proof_digest),),
        )
        assert seal.prefix_digest_open == prior.prefix_digest_close
        assert seal.protective_ledger_prefix_digest_open == prior.protective_ledger_prefix_digest_close
    assert [days[day].seal.pending_protective_child_time_ns for day in (3, 4, 5)] == [tau, tau, None]
    assert [days[day].seal.open_protective_ledger_obligation_count for day in (3, 4, 5)] == [1, 1, 0]
    # the gate: the entry decided before tau is admitted; the next entry is halted (PROTECTIVE-LEDGER refuses first)
    (entry,) = days[3].seal.entry_safety_decisions
    (halted,) = days[5].seal.entry_safety_decisions
    assert (entry.entry_permitted, entry.first_failure_check_id) == (True, "")
    assert (halted.entry_permitted, halted.first_failure_check_id) == (False, "PROTECTIVE-LEDGER")
    assert (halted.checks[-1].status, halted.checks[-1].observed, halted.checks[-1].reason) == (
        S.FAIL,
        "HALTED",
        est.code("PROTECTIVE-LEDGER:proven_integrity_trigger_halts_every_exposure_increase"),
    )
    assert days[5].seal.schedule.entry_refused_decision_sequences == (halted.decision_sequence,)
    # X4: the child's fill is projected onto the generic chain, named by its instant, and leaves the chain flat
    episode = days[5].seal.episodes[-1]
    assert episode.order_intent_request.request_id == f"req-{gpe.scenario('G').genesis.genesis_id}-c{tau}"
    assert Fraction(episode.new_position_state.signed_units) == 0
    # the ledger the seal bound, rebuilt through the public gate
    assert gate.evidence_digest == days[5].seal.entry_safety_evidence_digest
    ledger = gate.protective_ledger_evidence
    assert ledger is not None and ledger.evidence_digest == days[5].seal.protective_ledger_evidence_digest
    (schedule,) = ledger.schedules
    assert [
        (item.kind, item.time_ns, None if item.unfulfilled is None else item.unfulfilled.reason)
        for item in schedule.events
    ] == [
        (E.OPENED, tau, None),
        (E.CHILD_SENT, tau, None),
        (E.DEADLINE_MISSED, tau, R.ENGINE_UNREPRESENTABLE),  # D = tau: no child can fill at its own instant
        (E.CHILD_FILLED, fill.execution_time_ns, None),
        (E.DISCHARGED, fill.execution_time_ns, None),
    ]
    assert governed_paper_protective_ledger_open_at(ledger, halted.decision_time_ns) == (
        schedule.obligations[0].obligation_id,
    )
    assert governed_paper_protective_ledger_prefix_digest(ledger, before_ns=gpe.instant(5)) == (
        days[5].seal.protective_ledger_prefix_digest_open
    )
    assert no_target_anywhere(governed_paper_protective_ledger_evidence_to_dict(ledger))
    assert (evidence.schema_version, evidence.status) == (V10_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())


def test_world_g_seals_the_v1_handoff_at_a_refused_childs_resolution_replays_it_and_refuses_its_tampering() -> None:
    """R5 on world G (seal v10, evidence v10): the end-to-end child of the test above, but an SS4 proof 1 h into day 4
    threatens the lineage's own book, so the child in flight is refused at its day 5 fill; the MAX_HOLD obligation due on
    day 4 meanwhile is attempted at that very resolution, stays pending (world G's next book is on day 7) and closes the
    SHORT on day 7."""

    prefix = ledger_days(3)
    tau, threatened = gpe.instant(3) + 2 * HOUR, gpe.instant(4) + HOUR
    first = world_g_proof(tau)
    book = prefix[0].seal_inputs.dataset.source_manifest_digest
    second = proof(
        threatened, K.SS4_FLATTEN, scope=(book,), genesis=prefix[0].seal.genesis_digest, approved_at_ns=gpe.instant(0)
    )
    contexts = {day: GovernedPaperProtectiveLedgerContext((first,) if day == 3 else (first, second)) for day in (3, 4)}
    # the production prefix re-verifies under the production tables (the lineage evidence shares this identity memo)
    assert [(item.intact, item.reason_codes) for item in map(verified, prefix)] == [(True, ())] * 3
    with permissive_entries():
        days = prefix
        for day in range(3, 8):
            days = (*days, ledger_day(days, contexts[min(day, 4)]))
        outcome = lineage.protected_replay(days[7])[1]
        gate = ledger_gate(days[7], 7, contexts[4])
        evidence, verification = lineage_evidence(days)
        with integrity_table(TEST_ONLY_TABLE):
            sealed = [rst.verify(item.seal, item.seal_inputs) for item in days[3:]]
            forged = [
                rst.verify(gpe.reseal_seal(days[day].seal, **changes), days[day].seal_inputs)
                for day, changes in (
                    (5, {"pending_protective_attempt_time_ns": None}),  # the unrepaired day 5: no v1 attempt pending
                    (6, {"pending_protective_attempt_time_ns": None}),
                    (7, {"open_protective_ledger_obligation_count": 1}),
                    (7, {"protective_ledger_evidence_digest": "0" * 64}),
                )
            ]
    # the engine: the child in flight across day 4 is refused at its day 5 fill by its ended flatten authority
    opened, closed = outcome.position_transitions
    deadline = opened.time_ns + 24 * HOUR
    assert gpe.instant(3) < opened.time_ns < tau < gpe.instant(4) <= deadline < threatened < gpe.instant(5)
    ((child, fill),) = children_of(outcome)
    resolved = fill.execution_time_ns
    assert (child.attempt_time_ns, fill.outcome, fill.reason) == (
        tau,
        REJECTED,
        "governed_paper_flatten_authority_missing_at_fill",
    )
    assert gpe.instant(5) < resolved < gpe.instant(6)
    # v1: the MAX_HOLD obligation due on day 4 is attempted at the resolution itself and closes the SHORT on day 7
    (obligation,) = outcome.protective_obligations
    assert [item.trigger_kind for item in obligation.triggers] == [MAX_HOLD]
    (attempt,) = outcome.protective_attempts
    (v1_fill,) = lifet.protective_fills(outcome)
    assert (obligation.created_at_ns, attempt.attempt_time_ns, attempt.requested_quantity) == (
        deadline,
        resolved,
        lifet.d(1),
    )
    assert (v1_fill.outcome, v1_fill.filled_quantity) == (FILLED, lifet.d(1))
    assert gpe.instant(7) < v1_fill.execution_time_ns < gpe.instant(8)
    assert (closed.transition_kind, closed.fill_digest, closed.post_quantity) == (
        HistoricalExecutionTransitionKind.CLOSE,
        v1_fill.fill_digest,
        lifet.d(0),
    )
    assert (obligation.status.value, obligation.discharging_fill_digest) == ("DISCHARGED", v1_fill.fill_digest)
    # the seals: the flatten window ends at the SS4 proof from day 4 on; the child, then the v1 attempt, pend by instant
    for day in range(3, 8):
        seal, prior = days[day].seal, days[day - 1].seal
        assert (seal.schema_version, seal.status, seal.reason_codes) == (V10_SEAL, SEALED, ())
        assert seal.schedule.flatten_windows == (
            HistoricalExecutionFlattenWindow(tau, gpe.instant(4) if day == 3 else threatened, first.proof_digest),
        )
        assert seal.prefix_digest_open == prior.prefix_digest_close
        assert seal.protective_ledger_prefix_digest_open == prior.protective_ledger_prefix_digest_close
    assert [days[day].seal.integrity_proof_digests for day in range(3, 8)] == [(first.proof_digest,)] + [
        (first.proof_digest, second.proof_digest)
    ] * 4
    assert [days[day].seal.pending_protective_child_time_ns for day in range(3, 8)] == [tau, tau, None, None, None]
    assert [days[day].seal.pending_protective_attempt_time_ns for day in range(3, 8)] == [
        None,
        None,
        resolved,
        resolved,
        None,
    ]
    # KS4 alone on day 3; the SS4 proof joins the open schedule as a second obligation on day 4; both discharge on day 7
    assert [days[day].seal.open_protective_ledger_obligation_count for day in range(3, 8)] == [1, 2, 2, 2, 0]
    # replay: every seal re-verifies from its inputs, the public gate rebuilds the sealed ledger, the lineage verifies
    assert [(item.intact, item.reason_codes) for item in sealed] == [(True, ())] * 5
    assert gate.evidence_digest == days[7].seal.entry_safety_evidence_digest
    ledger = gate.protective_ledger_evidence
    assert ledger is not None and ledger.evidence_digest == days[7].seal.protective_ledger_evidence_digest
    assert ledger.governed_outcome_digest == days[7].seal.governed_outcome_digest == outcome.outcome_digest
    (schedule,) = ledger.schedules
    assert [item.trigger_kind for item in schedule.obligations] == [K.KS4_FLATTEN, K.SS4_FLATTEN]
    events = [(item.kind, item.time_ns) for item in schedule.events]
    assert (E.CHILD_SENT, tau) in events and (E.MERGED, threatened) in events
    assert (E.INTEGRITY_UNPROVEN, resolved) in events
    assert events[-1] == (E.DISCHARGED, v1_fill.execution_time_ns)
    assert [item.source.value for item in schedule.attributed_fills] == ["V1_ATTEMPT"]
    assert governed_paper_protective_ledger_prefix_digest(ledger, before_ns=gpe.instant(7)) == (
        days[7].seal.protective_ledger_prefix_digest_open
    )
    assert (evidence.schema_version, evidence.status) == (V10_EVIDENCE, GovernedPaperExecutionStatus.READY)
    assert (verification.intact, verification.reason_codes) == (True, ())
    # tampering: no resealed day verifies, the unrepaired "no pending v1 attempt" day 5 included
    assert [item.intact for item in forged] == [False] * 4


# --- legacy byte identity -----------------------------------------------------------------------------------------------------


def test_world_g_sizing_chain_lineage_is_byte_identical_to_accepted_main() -> None:
    days = sct.sizing_days(4)
    assert GOVERNED_PAPER_ENTRY_SAFETY_SIZING_CHAIN_RULE_SET_DIGEST == ACCEPTED_MAIN_RULE_SET_V8_DIGEST
    assert tuple(item.seal.schema_version for item in days) == (V9_SEAL,) * 4
    assert tuple(item.seal.seal_digest for item in days) == ACCEPTED_MAIN_V9_SEALS
    assert tuple(item.seal.entry_safety_evidence_digest for item in days) == ACCEPTED_MAIN_V9_ENTRY_EVIDENCE
    assert all(item.seal.schedule.schema_version == "historical-execution-admission-schedule.v5" for item in days)
    assert not set(V10_FIELDS) & set(governed_paper_day_seal_to_dict(days[3].seal))
    with rst.approval_table(rst.TEST_ONLY_TABLE):
        evidence = build_governed_paper_execution_evidence(gpe.evidence_inputs(days))
    assert (evidence.schema_version, evidence.evidence_digest) == (
        "governed-paper-execution-evidence.v9",
        ACCEPTED_MAIN_V9_LINEAGE_EVIDENCE,
    )
