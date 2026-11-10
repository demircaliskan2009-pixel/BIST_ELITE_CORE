"""Governed paper protective obligation ledger v2 (S1_PROTECTIVE_OBLIGATION_LEDGER_V2_ENGINE_CONSTRUCTION_V1).

Design authority: the approved companion ``docs/crypto_core/s1_approved_doctrine_adoption_v1.md`` §0.4 and §6.1-§6.7
(PROTECTIVE_OBLIGATION_LEDGER_V2, item 4.2 read with §0.4; FCD-11), adopted by PR #433, over the approved PRDV4 text D10,
D11, D13 and D14 (§1.19 KS-4 action and Position Closure Protocol item 5; §1.29 CRISIS and HALT). Paper-only,
deterministic, point-in-time and fail-closed. Exact arithmetic, no float, no ``decimal`` context, and no IO, clock,
randomness, network or environment.

What it is. The ledger of one governed evaluation: derived from that evaluation's one engine re-run (the governed outcome
under schedule v6), the proven lower-bound kill-switch ladder of the same re-run, the §1.29 system-state lower bounds of
its entry decisions and the IR-2 integrity trigger proofs known at the horizon. It is never accepted from a caller.

Triggers (only proven ones open an obligation; a caller's self-reported trigger, level or digest is never authority):

* ``KS3_CLOSE``: the ladder's proven lower bound reaches KS-3 (absorbing, ``governed_paper_kill_switch``). It applies to a
  position open at that instant, or, KS-3 holding, from the instant a later position opens. Its proof is the
  run-independent content of the ladder transition that set the level;
* ``SS3_CLOSE``: the §1.29 proven lower bound of an entry decision is at least SS-3 (CRISIS); its proof is that
  reading's digest. The bound never exceeds CRISIS on the governed path (``governed_paper_system_state``), so it never
  proves SS-4;
* ``KS4_FLATTEN`` and ``SS4_FLATTEN`` (integrity class, IR-1): proven only by an independent verifier from raw sealed
  inputs against an anchor outside the lineage (IR-2). A ``GovernedPaperIntegrityTriggerProof`` names its verifier, its
  anchor and its threat scope; it counts only when its verifier kind is ``INDEPENDENT_VERIFIER`` and its anchor is
  admitted by the active approval table. The PRODUCTION table admits none, so no integrity obligation ever opens in
  production; tests alone install a TEST-ONLY table for TEST_ONLY_SYNTHETIC anchors. The operator raise channel
  (HC-05d) is pending and an executor's self-report never proves or clears a trigger: both are refused.

A proven integrity trigger also halts exposure (PRDV4 §1.19 KS-4 and §1.29 HALT: cancel all orders, disable all engines):
the governed schedule v6 refuses every exposure-increasing intent decided, and every exposure-increasing fill executing,
at or after the earliest proof, and the entry gate refuses every later entry. A flatten acts only on a book
authenticated independently of the threatened component (IR-4): the lineage's book is authenticated by the dataset's
source manifest, so it is independent exactly while every proof at or before the instant declares a complete threat
scope that excludes that manifest. Otherwise the obligation records ``INTEGRITY_UNPROVEN`` and no child is sent.

Position schedule (§6.2). Every v2 obligation on one open position belongs to one schedule whose anchor the first of them
fixes: ``ANCHOR_OPENED`` = its instant and ``ANCHOR_Q0`` = the verified position after every fill of that nanosecond
(the equal-instant order of §6.6: fill outcomes, v1 rules, new triggers, one child, entries). The anchor never moves: a
joining trigger, a later fill, a retry, a new UTC day, a replay or a restart neither re-anchors nor resizes it. ``C(t)``
sums the verified close-only fill quantities on the position since the anchor (each fill once, from every source: v2
children, v1 STOP or MAX_HOLD attempts and decision exits); ``Rem(t) = min(ANCHOR_Q0 - C(t), |q(t)|)``, and a difference
between the two terms is ``POSITION_UNPROVEN``, never a new anchor. A later independent position gets a new schedule.

Deadlines (§6.2, §6.4). KS-3: the trigger instant + 30 minutes; SS-3: the earlier of the INTRADAY per-horizon rule and
the state-table row, the trigger instant + 15 minutes (S1 is INTRADAY, CL2-9; MICRO is the trigger instant and SWING is
outside S1); KS-4 and SS-4: the trigger instant. A deadline is evaluated at the first injected instant at or after it,
after the instant's child derivation; with ``Rem > 0`` it appends ``UNFULFILLED_PROTECTIVE_OBLIGATION_V1`` with the exact
remaining exposure and one reason, and the obligation stays open. The reason is the first failing link: a history
inconsistency (``POSITION_UNPROVEN``), an outstanding v1 obligation (``V1_PRECEDENCE``), for a nonurgent obligation the
unproven demand (``CAP_UNPROVEN``), and for an integrity obligation the threatened book (``INTEGRITY_UNPROVEN``), a
missing DEC-1 window (``AUTHORITY_UNPROVEN``), a child rejected for want of an admissible book (``BOOK_UNAVAILABLE``),
else ``ENGINE_UNREPRESENTABLE``: the fill model executes a child only at a later book observation, so no fill at the
deadline instant is representable. ``CAP_BINDING`` and ``IMPACT_PAUSE`` are never produced: no cap or impact measure is
proven.

Pending methods (§0.4), each left undefined and never defaulted: the target path TARGET(t) (HC-11c), the impact measure
(HC-11f) and the participation method (HD-04). A nonurgent obligation's demand is therefore undefined: it opens, binds
its schedule, keeps its deadline, records ``CAP_UNPROVEN`` (and ``AUTHORITY_UNPROVEN`` without a DEC-1 window), blocks
every entry and records its unfulfilled deadline, but no nonurgent child is ever derived or sent. No TARGET value is
computed, recorded or bound anywhere, ``MERGED`` included, and a missing TARGET is not zero. An integrity-class
obligation's demand is ``Rem(t)`` (IR-5): the engine derives a close-only flatten child of the whole remaining position,
exempt from pacing, participation and the impact pause, but bounded by DEC-1, the authenticated book and the fill model.

Lifecycle (§6.3). Per schedule, append-only and digest-chained from the anchor digest: ``OPENED``, ``CHILD_SENT``,
``CHILD_FILLED``, ``CAP_UNPROVEN``, ``AUTHORITY_UNPROVEN``, ``BOOK_UNAVAILABLE``, ``POSITION_UNPROVEN``,
``INTEGRITY_UNPROVEN``, ``MERGED``, ``DEADLINE_MISSED`` and ``DISCHARGED``. ``PAUSED`` is never produced (HC-11f).
``DISCHARGED`` only when the verified position is zero: never on an elapsed deadline, a submitted child, a partial fill,
a cancelled attempt or a missing book. A child the evaluation end leaves in flight records ``CHILD_SENT`` and no outcome.
Every identifier is a content identity (position, fill, child, obligation, schedule), never an identifier one engine
re-run derives, so a causal replay over a later archive yields the same prefix
(``governed_paper_protective_ledger_prefix_digest``, X1 for the ledger).

The evidence proves no venue fill, order, closed position, readiness or production authority.
"""

from __future__ import annotations

import bisect
from collections.abc import Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_sha256_text,
)
from crypto_core.validation.governed_paper_execution_authority import GovernedPaperApprovalKind
from crypto_core.validation.governed_paper_kill_switch import (
    GovernedPaperKillSwitchLadder,
    governed_paper_kill_switch_ladder_digest,
)
from crypto_core.validation.governed_paper_system_state import (
    GovernedPaperSystemStateReading,
    governed_paper_system_state_reading_digest,
)
from crypto_core.validation.historical_execution_economics import (
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION,
    HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION,
    HistoricalExecutionFill,
    HistoricalExecutionFillOutcome,
    HistoricalExecutionFlattenWindow,
    HistoricalExecutionGovernedPaperOutcome,
    HistoricalExecutionPositionTransition,
    HistoricalExecutionProtectiveChild,
    HistoricalExecutionTransitionKind,
    HistoricalExecutionValuationKind,
    historical_execution_governed_paper_outcome_digest,
)
from crypto_core.validation.historical_execution_economics_policy import (
    historical_execution_decimal_is_canonical,
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)

GOVERNED_PAPER_PROTECTIVE_LEDGER_CONTRACT_ID = "S1_PROTECTIVE_OBLIGATION_LEDGER_V2_ENGINE_CONSTRUCTION_V1"
GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_ID = "governed-paper-protective-obligation-ledger.v2"
GOVERNED_PAPER_PROTECTIVE_LEDGER_EVIDENCE_SCHEMA = "governed-paper-protective-ledger-evidence.v1"
GOVERNED_PAPER_INTEGRITY_TRIGGER_PROOF_SCHEMA = "governed-paper-integrity-trigger-proof.v1"
GOVERNED_PAPER_UNFULFILLED_PROTECTIVE_OBLIGATION_SCHEMA = "UNFULFILLED_PROTECTIVE_OBLIGATION_V1"
# S1 is an INTRADAY strategy (CL2-9): the SS-3 per-horizon deadline it reads.
GOVERNED_PAPER_PROTECTIVE_LEDGER_HORIZON = "INTRADAY"

_PREFIX = "governed_paper_protective_ledger"
_MINUTE_NS = 60_000_000_000
# PRDV4 doctrine deadlines (§1.19 KS-3 30-minute closure; §1.29 SS-3 per horizon; KS-4 and SS-4 immediate).
_KS3_DEADLINE_NS = 30 * _MINUTE_NS
_SS3_DEADLINE_NS: dict[str, int] = {"MICRO": 0, "INTRADAY": 15 * _MINUTE_NS}
_KS3_LEVEL = 3
_SS3_STATE = 3
_EXECUTED = (HistoricalExecutionFillOutcome.FILLED, HistoricalExecutionFillOutcome.PARTIALLY_FILLED)
_CLOSE_ONLY = (HistoricalExecutionTransitionKind.REDUCE, HistoricalExecutionTransitionKind.CLOSE)
# The engine's reasons for a child the fill model rejects for want of an admissible book (§1.19 item 4).
_BOOK_REJECTIONS = frozenset(
    {"book_invalid", "book_crossed", "spread_exceeds_max", "insufficient_depth", "fill_price_non_positive"}
)
_AUTHORITY_REFUSALS = frozenset(
    {"governed_paper_protective_authority_missing", "governed_paper_protective_authority_missing_at_fill"}
)
_FLATTEN_REFUSAL = "governed_paper_flatten_authority_missing_at_fill"
_PENDING_REASONS = frozenset({"execution_window_closed", "no_eligible_book_observation"})
_CAP_UNPROVEN = "CAP_UNPROVEN"
_EXEMPT = "EXEMPT_IR5"


class GovernedPaperProtectiveLedgerError(EdgeArtifactError):
    """Malformed input or a binding defect: a ledger is never represented over it."""


class GovernedPaperProtectiveObligationKind(str, Enum):
    """The four v2 trigger kinds, in the §6.6 equal-instant order."""

    KS4_FLATTEN = "KS4_FLATTEN"
    SS4_FLATTEN = "SS4_FLATTEN"
    KS3_CLOSE = "KS3_CLOSE"
    SS3_CLOSE = "SS3_CLOSE"


_KIND_ORDER = {kind: index for index, kind in enumerate(GovernedPaperProtectiveObligationKind)}
_INTEGRITY_KINDS = (
    GovernedPaperProtectiveObligationKind.KS4_FLATTEN,
    GovernedPaperProtectiveObligationKind.SS4_FLATTEN,
)


class GovernedPaperIntegrityVerifierKind(str, Enum):
    INDEPENDENT_VERIFIER = "INDEPENDENT_VERIFIER"  # IR-2: raw sealed inputs against an anchor outside the lineage
    OPERATOR_RAISE_CHANNEL = "OPERATOR_RAISE_CHANNEL"  # IR-2's other channel: its scope (HC-05d) is pending, refused
    EXECUTOR_SELF_REPORT = "EXECUTOR_SELF_REPORT"  # never proves or clears a trigger, refused


class GovernedPaperProtectiveLedgerEventKind(str, Enum):
    OPENED = "OPENED"
    CHILD_SENT = "CHILD_SENT"
    CHILD_FILLED = "CHILD_FILLED"
    CAP_UNPROVEN = "CAP_UNPROVEN"
    AUTHORITY_UNPROVEN = "AUTHORITY_UNPROVEN"
    BOOK_UNAVAILABLE = "BOOK_UNAVAILABLE"
    POSITION_UNPROVEN = "POSITION_UNPROVEN"
    INTEGRITY_UNPROVEN = "INTEGRITY_UNPROVEN"
    MERGED = "MERGED"
    DEADLINE_MISSED = "DEADLINE_MISSED"
    DISCHARGED = "DISCHARGED"


class GovernedPaperUnfulfilledReason(str, Enum):
    """The closed reason list of §6.3 (CAP_BINDING and IMPACT_PAUSE are never produced here)."""

    CAP_BINDING = "CAP_BINDING"
    CAP_UNPROVEN = "CAP_UNPROVEN"
    IMPACT_PAUSE = "IMPACT_PAUSE"
    BOOK_UNAVAILABLE = "BOOK_UNAVAILABLE"
    POSITION_UNPROVEN = "POSITION_UNPROVEN"
    INTEGRITY_UNPROVEN = "INTEGRITY_UNPROVEN"
    AUTHORITY_UNPROVEN = "AUTHORITY_UNPROVEN"
    V1_PRECEDENCE = "V1_PRECEDENCE"
    ENGINE_UNREPRESENTABLE = "ENGINE_UNREPRESENTABLE"


class GovernedPaperProtectiveScheduleStatus(str, Enum):
    OPEN = "OPEN"
    DISCHARGED = "DISCHARGED"


class GovernedPaperProtectiveFillSource(str, Enum):
    CHILD = "CHILD"
    V1_ATTEMPT = "V1_ATTEMPT"
    DECISION = "DECISION"


# --- IR-2 integrity trigger proofs -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperIntegrityAnchor:
    """An anchor outside the lineage that an independent verifier checks raw sealed inputs against (IR-2).

    ``approval_kind`` is HUMAN_GOVERNANCE (usable only once a separate human authorization lists the anchor digest in the
    production table) or TEST_ONLY_SYNTHETIC (tests only). ``anchor_digest`` covers every other field.
    """

    anchor_id: str
    anchor_reference: str
    approval_kind: GovernedPaperApprovalKind
    approver_reference: str
    approved_at_ns: int
    anchor_digest: str


@dataclass(frozen=True)
class GovernedPaperIntegrityApprovalTable:
    """Which anchors may prove an integrity trigger: ``production`` lists HUMAN_GOVERNANCE digests; ``test_only`` lists
    none and admits only TEST_ONLY_SYNTHETIC anchors."""

    table_id: str
    admitted_kind: GovernedPaperApprovalKind
    admitted_anchor_digests: tuple[str, ...]


# No separate human authorization lists any anchor digest for production use, so this table refuses every proof.
GOVERNED_PAPER_INTEGRITY_PRODUCTION_APPROVAL_TABLE = GovernedPaperIntegrityApprovalTable(
    table_id="production",
    admitted_kind=GovernedPaperApprovalKind.HUMAN_GOVERNANCE,
    admitted_anchor_digests=(),
)
_APPROVAL_TABLE = GOVERNED_PAPER_INTEGRITY_PRODUCTION_APPROVAL_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperIntegrityTriggerProof:
    """One IR-2 proof of a KS-4 or SS-4 trigger, known from ``trigger_time_ns``.

    ``sealed_input_digests`` name the raw sealed inputs the verifier re-derived the trigger from, and
    ``threat_scope_digests`` the components it proves threatened (strictly increasing digests).
    ``threat_scope_complete`` False is an unknown threat scope. ``proof_digest`` covers every other field.
    """

    schema_version: str
    proof_id: str
    genesis_digest: str
    trigger_kind: GovernedPaperProtectiveObligationKind
    trigger_time_ns: int
    verifier_kind: GovernedPaperIntegrityVerifierKind
    verifier_id: str
    anchor: GovernedPaperIntegrityAnchor
    sealed_input_digests: tuple[str, ...]
    threat_scope_digests: tuple[str, ...]
    threat_scope_complete: bool
    proof_digest: str


@dataclass(frozen=True)
class GovernedPaperProtectiveLedgerContext:
    """The IR-2 integrity trigger proofs known at the horizon, in (instant, kind, digest) order (none in production)."""

    integrity_proofs: tuple[GovernedPaperIntegrityTriggerProof, ...] = ()


# --- the ledger records ------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class GovernedPaperProtectiveCaps:
    """The caps of one obligation (§6.2): ``CAP_UNPROVEN`` while a method is pending, ``EXEMPT_IR5`` for the integrity
    class, and the fill model's own visible-depth cap fraction (the economics policy's)."""

    participation_method: str
    impact_measure: str
    liquidity_regime_halving: str
    fill_model_depth_cap_fraction: str


@dataclass(frozen=True)
class GovernedPaperProtectiveObligation:
    """One proven v2 obligation (§6.2). ``position_at_trigger`` is a record only and never resizes the schedule."""

    obligation_id: str
    trigger_kind: GovernedPaperProtectiveObligationKind
    trigger_proof_digest: str
    integrity_class: bool
    opened_ns: int
    deadline_ns: int
    horizon: str
    position_at_trigger: str
    caps: GovernedPaperProtectiveCaps


@dataclass(frozen=True)
class GovernedPaperUnfulfilledProtectiveObligation:
    """``UNFULFILLED_PROTECTIVE_OBLIGATION_V1``: a deadline passed with remaining exposure. Never a closed position."""

    schema_version: str
    obligation_id: str
    deadline_ns: int
    evaluated_at_ns: int
    remaining_exposure: str
    reason: GovernedPaperUnfulfilledReason


@dataclass(frozen=True)
class GovernedPaperProtectiveMerge:
    """What a joining obligation binds (§6.3): never a TARGET value, which is undefined while HC-11c is pending."""

    anchor_digest: str
    joining_obligation_id: str
    joining_trigger_proof_digest: str
    effective_deadline_before_ns: int | None
    effective_deadline_after_ns: int | None
    attributed_fill_ids: tuple[str, ...]
    attributed_fill_quantities: tuple[str, ...]
    closed_quantity: str
    in_flight_reference: str
    in_flight_requested_quantity: str
    caps: GovernedPaperProtectiveCaps
    dec1_authority_digest: str


@dataclass(frozen=True)
class GovernedPaperProtectiveLedgerEvent:
    """One append-only lifecycle event of a schedule, chained to its predecessor (the anchor digest for the first).

    ``quantity`` is the requested (``CHILD_SENT``) or filled (``CHILD_FILLED``) quantity, or empty; ``closed_quantity``
    and ``remaining_quantity`` are ``C(t)`` and ``Rem(t)`` after the event. ``reference`` names the child, fill or
    obligation concerned by its content identity.
    """

    sequence: int
    kind: GovernedPaperProtectiveLedgerEventKind
    time_ns: int
    obligation_id: str
    quantity: str
    closed_quantity: str
    remaining_quantity: str
    reference: str
    reason: str
    merge: GovernedPaperProtectiveMerge | None
    unfulfilled: GovernedPaperUnfulfilledProtectiveObligation | None
    previous_event_digest: str
    event_digest: str


@dataclass(frozen=True)
class GovernedPaperProtectiveFill:
    """One verified close-only fill counted once in ``C(t)``: its content identity, source, instant, quantity and price."""

    fill_id: str
    source: GovernedPaperProtectiveFillSource
    time_ns: int
    quantity: str
    price: str


@dataclass(frozen=True)
class GovernedPaperProtectiveChildRecord:
    """One flatten child of the schedule (§6.2): requested, attributed fills, filled quantity and VWAP, and its outcome
    (``FILLED``, ``PARTIALLY_FILLED``, ``REJECTED:<reason>`` or ``IN_FLIGHT``)."""

    child_id: str
    decision_time_ns: int
    requested_quantity: str
    attributed_fill_ids: tuple[str, ...]
    filled_quantity: str
    vwap: str | None
    outcome: str


@dataclass(frozen=True)
class GovernedPaperProtectiveSchedule:
    """The one position schedule of an open position (§6.2), anchored by its first v2 obligation and never moved."""

    schedule_id: str
    position_id: str
    anchor_opened_ns: int
    anchor_q0: str
    anchor_digest: str
    position_proof_digest: str
    first_trigger_proof_digest: str
    obligations: tuple[GovernedPaperProtectiveObligation, ...]
    events: tuple[GovernedPaperProtectiveLedgerEvent, ...]
    attributed_fills: tuple[GovernedPaperProtectiveFill, ...]
    children: tuple[GovernedPaperProtectiveChildRecord, ...]
    closed_quantity: str
    remaining_quantity: str
    status: GovernedPaperProtectiveScheduleStatus
    discharged_at_ns: int | None
    head_event_digest: str


@dataclass(frozen=True)
class GovernedPaperIntegrityTrigger:
    """One admitted IR-2 trigger of the evaluation and whether its threat scope leaves the lineage's book unproven."""

    trigger_time_ns: int
    trigger_kind: GovernedPaperProtectiveObligationKind
    proof_digest: str
    book_threatened: bool


@dataclass(frozen=True)
class GovernedPaperProtectiveLedgerEvidence:
    """The v2 ledger of one governed evaluation over ``[start_ns, horizon_ns)``; ``evidence_digest`` covers the rest."""

    schema_version: str
    contract_id: str
    rule_id: str
    rule_digest: str
    instrument: str
    genesis_digest: str
    start_ns: int
    horizon_ns: int
    governed_outcome_digest: str
    kill_switch_ladder_digest: str
    book_source_digest: str
    integrity_triggers: tuple[GovernedPaperIntegrityTrigger, ...]
    integrity_halt_from_ns: int | None
    book_threatened_from_ns: int | None
    schedules: tuple[GovernedPaperProtectiveSchedule, ...]
    open_obligation_count: int
    evidence_digest: str
    paper_only: bool = True
    target_path_defined: bool = False
    impact_measure_defined: bool = False
    participation_method_defined: bool = False
    nonurgent_child_sent: bool = False
    production_authority_granted: bool = False
    venue_orders_created: bool = False
    venue_fill_truth_proven: bool = False
    entry_authorized: bool = False


GOVERNED_PAPER_PROTECTIVE_LEDGER_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("target_path_defined", False),
    ("impact_measure_defined", False),
    ("participation_method_defined", False),
    ("nonurgent_child_sent", False),
    ("production_authority_granted", False),
    ("venue_orders_created", False),
    ("venue_fill_truth_proven", False),
    ("entry_authorized", False),
)


# --- helpers -----------------------------------------------------------------------------------------------------------


def _fail(code: str) -> GovernedPaperProtectiveLedgerError:
    return GovernedPaperProtectiveLedgerError(f"{_PREFIX}:{code}")


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


def _digest(kind: str, *parts: object) -> str:
    return edge_sha256_text(edge_canonical_json([kind, *parts]))


def _render(value: Fraction) -> str:
    rendered = historical_execution_render_amount(value)
    if rendered is None:  # pragma: no cover - every quantity is an engine quantity on the scale-18 grid
        raise _fail("quantity_unrepresentable")
    return rendered


def _text(value: object, name: str) -> str:
    if type(value) is not str or not value or len(value) > 256 or value != value.strip():
        raise _fail(f"text_malformed:{name}")
    return value


def _instant(value: object, name: str) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail(f"instant_malformed:{name}")
    return value  # type: ignore[return-value]


def _hex_tuple(value: object, name: str, *, nonempty: bool) -> tuple[str, ...]:
    if type(value) is not tuple or any(not edge_is_hex64(item) for item in value) or (nonempty and not value):
        raise _fail(f"digests_malformed:{name}")
    if any(later <= earlier for earlier, later in zip(value, value[1:], strict=False)):
        raise _fail(f"digests_not_strictly_increasing:{name}")
    return value


def governed_paper_protective_ledger_rule() -> dict[str, object]:
    """The rule this ledger applies, digest-bound by every evidence."""

    return {
        "rule_id": GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_ID,
        "contract_id": GOVERNED_PAPER_PROTECTIVE_LEDGER_CONTRACT_ID,
        "approved_doctrine": "PRDV4 §1.19 D10 D11, §1.29 D13 D14; s1_approved_doctrine_adoption_v1 §6.1-§6.7 read with §0.4",
        "approved_items": ["4.1", "4.2", "FCD-11"],
        "pending_never_read": ["HC-11c", "HC-11f", "HD-04", "HC-05d", "HC-11a", "HC-11b", "HC-11e", "DEC-9"],
        "triggers": {
            "KS3_CLOSE": "the_proven_lower_bound_ladder_reaches_ks_3_absorbing",
            "SS3_CLOSE": "an_entry_decisions_proven_system_state_lower_bound_is_at_least_ss_3",
            "KS4_FLATTEN": "an_admitted_ir_2_independent_verifier_proof_against_an_outside_anchor",
            "SS4_FLATTEN": "an_admitted_ir_2_independent_verifier_proof_against_an_outside_anchor",
        },
        "deadlines_ns": {
            "KS3_CLOSE": _KS3_DEADLINE_NS,
            "SS3_CLOSE": _SS3_DEADLINE_NS,
            "KS4_FLATTEN": 0,
            "SS4_FLATTEN": 0,
        },
        "horizon": GOVERNED_PAPER_PROTECTIVE_LEDGER_HORIZON,
        "equal_instant_order": [
            "fill_outcomes",
            "v1_stop_and_max_hold",
            "new_triggers_ks4_ss4_ks3_ss3_then_proof_digest",
            "at_most_one_child",
            "deadlines",
            "entries_refused_while_open",
        ],
        "nonurgent_child": "never_target_impact_and_participation_undefined_cap_unproven",
        "integrity_child": "engine_close_only_whole_remaining_position_ir_5_dec_1_independent_book_fill_model",
        "unfulfilled_reason_order": [
            "POSITION_UNPROVEN",
            "V1_PRECEDENCE",
            "CAP_UNPROVEN_nonurgent",
            "INTEGRITY_UNPROVEN",
            "AUTHORITY_UNPROVEN",
            "BOOK_UNAVAILABLE",
            "ENGINE_UNREPRESENTABLE",
        ],
        "halt": "a_proven_integrity_trigger_refuses_every_later_exposure_increase",
    }


GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE = governed_paper_protective_ledger_rule()
GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_DIGEST = edge_sha256_text(
    edge_canonical_json(GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE)
)


# --- IR-2 proofs: building, admission and the active table ---------------------------------------------------------------


def build_governed_paper_integrity_anchor(
    *,
    anchor_id: str,
    anchor_reference: str,
    approval_kind: GovernedPaperApprovalKind,
    approver_reference: str,
    approved_at_ns: int,
) -> GovernedPaperIntegrityAnchor:
    """One outside-lineage anchor with its digest (a record; never a production permission)."""

    seed = GovernedPaperIntegrityAnchor(
        anchor_id=anchor_id,
        anchor_reference=anchor_reference,
        approval_kind=approval_kind,
        approver_reference=approver_reference,
        approved_at_ns=approved_at_ns,
        anchor_digest="",
    )
    _canonical_anchor(seed, digest=False)
    return replace(seed, anchor_digest=edge_payload_digest(_to_payload(seed), "anchor_digest"))


def _canonical_anchor(anchor: object, *, digest: bool = True) -> GovernedPaperIntegrityAnchor:
    if type(anchor) is not GovernedPaperIntegrityAnchor:
        raise _fail("anchor_malformed")
    _text(anchor.anchor_id, "anchor_id")
    _text(anchor.anchor_reference, "anchor_reference")
    _text(anchor.approver_reference, "approver_reference")
    if type(anchor.approval_kind) is not GovernedPaperApprovalKind:
        raise _fail("anchor_malformed:approval_kind")
    _instant(anchor.approved_at_ns, "approved_at_ns")
    if digest and edge_payload_digest(_to_payload(anchor), "anchor_digest") != anchor.anchor_digest:
        raise _fail("anchor_digest_mismatch")
    return anchor


def build_governed_paper_integrity_trigger_proof(  # noqa: PLR0913
    *,
    proof_id: str,
    genesis_digest: str,
    trigger_kind: GovernedPaperProtectiveObligationKind,
    trigger_time_ns: int,
    verifier_kind: GovernedPaperIntegrityVerifierKind,
    verifier_id: str,
    anchor: GovernedPaperIntegrityAnchor,
    sealed_input_digests: tuple[str, ...],
    threat_scope_digests: tuple[str, ...],
    threat_scope_complete: bool,
) -> GovernedPaperIntegrityTriggerProof:
    """One IR-2 proof record with its digest (a record; it proves a trigger only once its anchor is admitted)."""

    seed = GovernedPaperIntegrityTriggerProof(
        schema_version=GOVERNED_PAPER_INTEGRITY_TRIGGER_PROOF_SCHEMA,
        proof_id=proof_id,
        genesis_digest=genesis_digest,
        trigger_kind=trigger_kind,
        trigger_time_ns=trigger_time_ns,
        verifier_kind=verifier_kind,
        verifier_id=verifier_id,
        anchor=anchor,
        sealed_input_digests=sealed_input_digests,
        threat_scope_digests=threat_scope_digests,
        threat_scope_complete=threat_scope_complete,
        proof_digest="",
    )
    _canonical_proof(seed, digest=False)
    return replace(seed, proof_digest=edge_payload_digest(_to_payload(seed), "proof_digest"))


def _canonical_proof(proof: object, *, digest: bool = True) -> GovernedPaperIntegrityTriggerProof:
    if type(proof) is not GovernedPaperIntegrityTriggerProof:
        raise _fail("integrity_proof_malformed")
    if proof.schema_version != GOVERNED_PAPER_INTEGRITY_TRIGGER_PROOF_SCHEMA:
        raise _fail("integrity_proof_malformed:schema_version")
    _text(proof.proof_id, "proof_id")
    _text(proof.verifier_id, "verifier_id")
    if not edge_is_hex64(proof.genesis_digest):
        raise _fail("integrity_proof_malformed:genesis_digest")
    if (
        type(proof.trigger_kind) is not GovernedPaperProtectiveObligationKind
        or proof.trigger_kind not in _INTEGRITY_KINDS
    ):
        raise _fail("integrity_proof_malformed:trigger_kind")
    if type(proof.verifier_kind) is not GovernedPaperIntegrityVerifierKind:
        raise _fail("integrity_proof_malformed:verifier_kind")
    _instant(proof.trigger_time_ns, "trigger_time_ns")
    _canonical_anchor(proof.anchor)
    _hex_tuple(proof.sealed_input_digests, "sealed_input_digests", nonempty=True)
    _hex_tuple(proof.threat_scope_digests, "threat_scope_digests", nonempty=False)
    if type(proof.threat_scope_complete) is not bool:
        raise _fail("integrity_proof_malformed:threat_scope_complete")
    if digest and edge_payload_digest(_to_payload(proof), "proof_digest") != proof.proof_digest:
        raise _fail("integrity_proof_digest_mismatch")
    return proof


def _canonical_table(table: object) -> GovernedPaperIntegrityApprovalTable:
    if type(table) is not GovernedPaperIntegrityApprovalTable:
        raise _fail("approval_table_malformed")
    digests = table.admitted_anchor_digests
    if type(digests) is not tuple or any(not edge_is_hex64(item) for item in digests):
        raise _fail("approval_table_malformed")
    if table.table_id == "production" and table.admitted_kind is GovernedPaperApprovalKind.HUMAN_GOVERNANCE:
        return table
    if table.table_id == "test_only" and table.admitted_kind is GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC:
        if not digests:
            return table
    raise _fail("approval_table_malformed")


def governed_paper_integrity_active_table() -> GovernedPaperIntegrityApprovalTable:
    """The active approval table (the production table unless a test installed the test-only one)."""

    return _canonical_table(_APPROVAL_TABLE)


def governed_paper_integrity_proof_admission(proof: GovernedPaperIntegrityTriggerProof, *, genesis_digest: str) -> str:
    """Why ``proof`` does not prove its trigger under the active table (empty when it does). A malformed proof raises."""

    proof = _canonical_proof(proof)
    if proof.genesis_digest != genesis_digest:
        return "integrity_proof_of_another_lineage"
    if proof.verifier_kind is GovernedPaperIntegrityVerifierKind.EXECUTOR_SELF_REPORT:
        return "executor_self_report_never_proves_a_trigger"
    if proof.verifier_kind is GovernedPaperIntegrityVerifierKind.OPERATOR_RAISE_CHANNEL:
        return "operator_raise_channel_scope_pending_hc_05d"
    anchor, table = proof.anchor, governed_paper_integrity_active_table()
    if anchor.approved_at_ns > proof.trigger_time_ns:
        return "anchor_approved_after_the_trigger"
    if table.table_id == "production":
        if anchor.approval_kind is GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC:
            return "synthetic_anchor_refused_on_the_production_table"
        if anchor.anchor_digest not in table.admitted_anchor_digests:
            return "anchor_not_authorized_for_production_use"
        return ""
    if anchor.approval_kind is not GovernedPaperApprovalKind.TEST_ONLY_SYNTHETIC:
        return "only_test_only_synthetic_anchors_on_the_test_only_table"
    return ""


def governed_paper_protective_ledger_canonical_context(
    context: object, *, genesis_digest: str, horizon_ns: int
) -> GovernedPaperProtectiveLedgerContext:
    """Re-prove a context: every proof authentic, admitted, of this lineage, known before the horizon, unique and in
    (instant, kind, digest) order. A proof that does not prove its trigger is refused, never skipped."""

    if type(context) is not GovernedPaperProtectiveLedgerContext or type(context.integrity_proofs) is not tuple:
        raise _fail("context_malformed")
    keys: list[tuple[int, int, str]] = []
    for proof in context.integrity_proofs:
        reason = governed_paper_integrity_proof_admission(proof, genesis_digest=genesis_digest)
        if reason:
            raise _fail(f"integrity_proof_not_admitted:{reason}")
        if proof.trigger_time_ns >= horizon_ns:
            raise _fail("integrity_proof_unknown_at_the_horizon")
        keys.append((proof.trigger_time_ns, _KIND_ORDER[proof.trigger_kind], proof.proof_digest))
    if any(later <= earlier for earlier, later in zip(keys, keys[1:], strict=False)):
        raise _fail("integrity_proofs_not_ordered_unique")
    return context


def _triggers(
    context: GovernedPaperProtectiveLedgerContext, book_source_digest: str
) -> tuple[GovernedPaperIntegrityTrigger, ...]:
    return tuple(
        GovernedPaperIntegrityTrigger(
            trigger_time_ns=proof.trigger_time_ns,
            trigger_kind=proof.trigger_kind,
            proof_digest=proof.proof_digest,
            book_threatened=not proof.threat_scope_complete or book_source_digest in proof.threat_scope_digests,
        )
        for proof in context.integrity_proofs
    )


def governed_paper_protective_ledger_schedule_bounds(
    context: GovernedPaperProtectiveLedgerContext, *, book_source_digest: str, horizon_ns: int
) -> tuple[int | None, tuple[HistoricalExecutionFlattenWindow, ...]]:
    """The schedule v6 bounds a verified context implies: the exposure halt (the earliest proven integrity trigger) and
    the one flatten window from it until the book is first proven threatened or its threat scope unknown (IR-4), or the
    horizon; no window when the book is threatened from the halt. Facts of the inputs alone. Pure."""

    if not edge_is_hex64(book_source_digest):
        raise _fail("book_source_digest_malformed")
    _instant(horizon_ns, "horizon_ns")
    triggers = _triggers(context, book_source_digest)
    if not triggers:
        return None, ()
    halt = triggers[0].trigger_time_ns
    threatened = [item.trigger_time_ns for item in triggers if item.book_threatened]
    end = min([*threatened, horizon_ns])
    if end <= halt:
        return halt, ()
    return halt, (HistoricalExecutionFlattenWindow(halt, end, triggers[0].proof_digest),)


# --- the derivation ------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Trigger:
    time_ns: int
    kind: GovernedPaperProtectiveObligationKind
    proof_digest: str


@dataclass(frozen=True)
class _Excursion:
    position_id: str
    opened_ns: int
    closed_ns: int | None
    transitions: tuple[HistoricalExecutionPositionTransition, ...]


@dataclass(frozen=True)
class _ChildFacts:
    record: HistoricalExecutionProtectiveChild
    child_id: str
    refused_at_attempt: str  # the engine's refusal at the attempt instant, or ""
    outcome_ns: int | None  # the instant its fill outcome resolved (None: in flight at the evaluation end)
    outcome: HistoricalExecutionFill | None


def _fill_id(fill: HistoricalExecutionFill) -> str:
    return _digest(
        "protective_ledger_fill",
        fill.execution_time_ns,
        fill.book_record_digest,
        fill.side.value,
        fill.filled_quantity,
        fill.fill_price,
    )


def _child_id(child: HistoricalExecutionProtectiveChild) -> str:
    return _digest(
        "protective_ledger_child",
        child.flatten_authority_digest,
        child.attempt_time_ns,
        child.requested_quantity,
        child.side.value,
    )


def _ks3_trigger(ladder: GovernedPaperKillSwitchLadder) -> _Trigger | None:
    for item in ladder.transitions:
        if item.to_level >= _KS3_LEVEL:
            proof = _digest(
                "protective_ledger_ks3_proof",
                ladder.rule_digest,
                item.time_ns,
                item.phase,
                item.from_level,
                item.to_level,
                list(item.proven_trigger_ids),
            )
            return _Trigger(item.time_ns, GovernedPaperProtectiveObligationKind.KS3_CLOSE, proof)
    return None


def _excursions(
    outcome: HistoricalExecutionGovernedPaperOutcome, genesis_digest: str, fills: dict[str, HistoricalExecutionFill]
) -> list[_Excursion]:
    found: list[_Excursion] = []
    current: list[HistoricalExecutionPositionTransition] = []
    opened = 0
    position_id = ""
    for item in outcome.position_transitions:
        if item.transition_kind is HistoricalExecutionTransitionKind.OPEN:
            if current:
                raise _fail("outcome_transitions_inconsistent")
            opening = fills[item.fill_digest]
            opened = item.time_ns
            position_id = _digest(
                "protective_ledger_position",
                genesis_digest,
                item.time_ns,
                opening.book_record_digest,
                item.delta_quantity,
            )
            current = [item]
            continue
        if not current:
            raise _fail("outcome_transitions_inconsistent")
        current.append(item)
        if item.transition_kind is HistoricalExecutionTransitionKind.CLOSE:
            found.append(_Excursion(position_id, opened, item.time_ns, tuple(current)))
            current = []
    if current:
        found.append(_Excursion(position_id, opened, None, tuple(current)))
    return found


def _position_after(excursion: _Excursion, time_ns: int) -> Fraction:
    """The verified signed position after every fill of the nanosecond ``time_ns``."""

    quantity = Fraction(0)
    for item in excursion.transitions:
        if item.time_ns > time_ns:
            break
        quantity = Fraction(item.post_quantity)
    return quantity


def _covering(windows: Sequence[object], time_ns: int) -> object | None:
    starts = [item.window_start_ns for item in windows]  # type: ignore[attr-defined]
    index = bisect.bisect_right(starts, time_ns) - 1
    if index >= 0 and time_ns < windows[index].window_end_ns:  # type: ignore[attr-defined]
        return windows[index]
    return None


def _caps(integrity: bool, depth_cap: str) -> GovernedPaperProtectiveCaps:
    if integrity:
        return GovernedPaperProtectiveCaps(_EXEMPT, _EXEMPT, _EXEMPT, depth_cap)
    return GovernedPaperProtectiveCaps(
        _CAP_UNPROVEN, _CAP_UNPROVEN, "halved_rate_applies_liquidity_regime_unknown", depth_cap
    )


def _deadline(kind: GovernedPaperProtectiveObligationKind, opened: int) -> int:
    if kind is GovernedPaperProtectiveObligationKind.KS3_CLOSE:
        return opened + _KS3_DEADLINE_NS
    if kind is GovernedPaperProtectiveObligationKind.SS3_CLOSE:
        return opened + _SS3_DEADLINE_NS[GOVERNED_PAPER_PROTECTIVE_LEDGER_HORIZON]
    return opened


class _ScheduleBuilder:  # noqa: PLR0902 - the mutable state of one schedule's single pass
    """One schedule's single pass over its injected instants (internal; the records it emits are frozen)."""

    def __init__(self, *, genesis_digest: str, excursion: _Excursion, depth_cap: str) -> None:
        self.genesis_digest = genesis_digest
        self.excursion = excursion
        self.depth_cap = depth_cap
        self.schedule_id = ""
        self.anchor_opened = 0
        self.anchor_q0 = Fraction(0)
        self.anchor_digest = ""
        self.position_proof = ""
        self.first_proof = ""
        self.obligations: list[GovernedPaperProtectiveObligation] = []
        self.events: list[GovernedPaperProtectiveLedgerEvent] = []
        self.fills: list[GovernedPaperProtectiveFill] = []
        self.closed = Fraction(0)
        self.position_unproven = False
        self.integrity_unproven_recorded = False
        self.recorded_deadlines: set[str] = set()
        self.discharged_at: int | None = None

    @property
    def opened(self) -> bool:
        return self.schedule_id != ""

    def remaining(self, time_ns: int) -> Fraction:
        return min(self.anchor_q0 - self.closed, abs(_position_after(self.excursion, time_ns)))

    def event(  # noqa: PLR0913
        self,
        kind: GovernedPaperProtectiveLedgerEventKind,
        time_ns: int,
        *,
        obligation_id: str = "",
        quantity: str = "",
        reference: str = "",
        reason: str = "",
        merge: GovernedPaperProtectiveMerge | None = None,
        unfulfilled: GovernedPaperUnfulfilledProtectiveObligation | None = None,
    ) -> None:
        previous = self.events[-1].event_digest if self.events else self.anchor_digest
        seed = GovernedPaperProtectiveLedgerEvent(
            sequence=len(self.events),
            kind=kind,
            time_ns=time_ns,
            obligation_id=obligation_id,
            quantity=quantity,
            closed_quantity=_render(self.closed),
            remaining_quantity=_render(self.remaining(time_ns)),
            reference=reference,
            reason=reason,
            merge=merge,
            unfulfilled=unfulfilled,
            previous_event_digest=previous,
            event_digest="",
        )
        self.events.append(replace(seed, event_digest=edge_payload_digest(_to_payload(seed), "event_digest")))

    def open(self, trigger: _Trigger, time_ns: int) -> None:
        self.anchor_opened = time_ns
        self.anchor_q0 = abs(_position_after(self.excursion, time_ns))
        self.first_proof = trigger.proof_digest
        prefix = [
            [item.time_ns, item.transition_kind.value, item.delta_quantity, item.post_quantity]
            for item in self.excursion.transitions
            if item.time_ns <= time_ns
        ]
        self.position_proof = _digest("protective_ledger_position_proof", self.excursion.position_id, prefix)
        first = self.obligation_id(trigger, time_ns)
        self.schedule_id = _digest("protective_ledger_schedule", self.genesis_digest, self.excursion.position_id, first)
        self.anchor_digest = _digest(
            "protective_ledger_anchor",
            self.schedule_id,
            self.anchor_opened,
            _render(self.anchor_q0),
            self.first_proof,
            self.position_proof,
        )

    def obligation_id(self, trigger: _Trigger, time_ns: int) -> str:
        return _digest(
            "protective_ledger_obligation",
            self.genesis_digest,
            self.excursion.position_id,
            trigger.kind.value,
            trigger.proof_digest,
            time_ns,
        )

    def effective_deadline(self) -> int | None:
        deadlines = [item.deadline_ns for item in self.obligations if not item.integrity_class]
        return min(deadlines) if deadlines else None

    def obligation(self, trigger: _Trigger, time_ns: int) -> GovernedPaperProtectiveObligation:
        integrity = trigger.kind in _INTEGRITY_KINDS
        return GovernedPaperProtectiveObligation(
            obligation_id=self.obligation_id(trigger, time_ns),
            trigger_kind=trigger.kind,
            trigger_proof_digest=trigger.proof_digest,
            integrity_class=integrity,
            opened_ns=time_ns,
            deadline_ns=_deadline(trigger.kind, time_ns),
            horizon=GOVERNED_PAPER_PROTECTIVE_LEDGER_HORIZON,
            position_at_trigger=_render(abs(_position_after(self.excursion, time_ns))),
            caps=_caps(integrity, self.depth_cap),
        )


@dataclass(frozen=True)
class _Facts:
    """The read-only facts of one evaluation the schedules share."""

    outcome: HistoricalExecutionGovernedPaperOutcome
    fills: dict[str, HistoricalExecutionFill]
    sources: dict[str, GovernedPaperProtectiveFillSource]
    children: tuple[_ChildFacts, ...]
    v1_attempts: tuple[tuple[int, int | None], ...]  # (attempt instant, outcome instant or None while in flight)
    v1_obligations: tuple[tuple[int, int | None], ...]  # (created, discharged or None)
    instants: tuple[int, ...]
    horizon_ns: int


def _child_facts(outcome: HistoricalExecutionGovernedPaperOutcome) -> tuple[_ChildFacts, ...]:
    by_intent: dict[str, list[HistoricalExecutionFill]] = {}
    for item in outcome.fills:
        by_intent.setdefault(item.intent_id, []).append(item)
    found = []
    for child in outcome.protective_children:
        results = by_intent.get(child.child_id, [])
        if len(results) != 1:
            raise _fail("child_outcome_inconsistent")
        result = results[0]
        refused, resolved, outcome_record = "", result.execution_time_ns, result
        if result.outcome is HistoricalExecutionFillOutcome.REJECTED and result.execution_time_ns is None:
            refused, resolved = result.reason, child.attempt_time_ns
        elif result.outcome is HistoricalExecutionFillOutcome.UNFILLED:
            if result.reason not in _PENDING_REASONS or outcome.pending_protective_child_digest != child.child_digest:
                raise _fail("child_outcome_inconsistent")
            resolved, outcome_record = None, None
        found.append(_ChildFacts(child, _child_id(child), refused, resolved, outcome_record))
    return tuple(found)


def _in_flight(facts: _Facts, time_ns: int) -> tuple[str, str]:
    """The child or v1 attempt in flight after step 4 of ``time_ns``: its reference and requested quantity, or empty."""

    for child in facts.children:
        if child.refused_at_attempt:
            continue
        if child.record.attempt_time_ns <= time_ns and (child.outcome_ns is None or time_ns < child.outcome_ns):
            return child.child_id, child.record.requested_quantity
    for attempt, resolved in facts.v1_attempts:
        if attempt <= time_ns and (resolved is None or time_ns < resolved):
            return "v1_attempt", ""
    return "", ""


def _v1_outstanding(facts: _Facts, time_ns: int) -> bool:
    return any(
        created <= time_ns and (discharged is None or time_ns < discharged)
        for created, discharged in facts.v1_obligations
    )


def _unfulfilled_reason(
    builder: _ScheduleBuilder, obligation: GovernedPaperProtectiveObligation, facts: _Facts, time_ns: int
) -> GovernedPaperUnfulfilledReason:
    schedule = facts.outcome.schedule
    if builder.position_unproven:
        return GovernedPaperUnfulfilledReason.POSITION_UNPROVEN
    if _v1_outstanding(facts, time_ns):
        return GovernedPaperUnfulfilledReason.V1_PRECEDENCE
    if not obligation.integrity_class:
        return GovernedPaperUnfulfilledReason.CAP_UNPROVEN
    if _covering(schedule.flatten_windows, time_ns) is None:
        return GovernedPaperUnfulfilledReason.INTEGRITY_UNPROVEN
    if _covering(schedule.protective_windows, time_ns) is None:
        return GovernedPaperUnfulfilledReason.AUTHORITY_UNPROVEN
    latest = [
        child
        for child in facts.children
        if child.outcome_ns is not None and child.outcome_ns <= time_ns and child.outcome is not None
    ]
    if (
        latest
        and latest[-1].outcome.reason in _BOOK_REJECTIONS  # type: ignore[union-attr]
        and not _in_flight(facts, time_ns)[0]
    ):
        return GovernedPaperUnfulfilledReason.BOOK_UNAVAILABLE
    return GovernedPaperUnfulfilledReason.ENGINE_UNREPRESENTABLE


def _schedule(  # noqa: C901, PLR0912 - one linear pass of the §6.6 order over the instants
    facts: _Facts,
    excursion: _Excursion,
    triggers: Sequence[_Trigger],
    *,
    genesis_digest: str,
    depth_cap: str,
) -> GovernedPaperProtectiveSchedule | None:
    applicable: list[tuple[int, _Trigger]] = []
    for item in triggers:
        start = (
            max(item.time_ns, excursion.opened_ns)
            if item.kind is GovernedPaperProtectiveObligationKind.KS3_CLOSE
            else item.time_ns
        )
        if excursion.opened_ns <= start and (excursion.closed_ns is None or start < excursion.closed_ns):
            if start < facts.horizon_ns:
                applicable.append((start, item))
    if not applicable:
        return None
    applicable.sort(key=lambda entry: (entry[0], _KIND_ORDER[entry[1].kind], entry[1].proof_digest))
    builder = _ScheduleBuilder(genesis_digest=genesis_digest, excursion=excursion, depth_cap=depth_cap)
    end = excursion.closed_ns
    first = applicable[0][0]
    instants = sorted(
        {
            *(instant for instant in facts.instants if first <= instant and (end is None or instant <= end)),
            *(start for start, _ in applicable),
        }
    )
    children = [
        child
        for child in facts.children
        if excursion.opened_ns <= child.record.attempt_time_ns and (end is None or child.record.attempt_time_ns < end)
    ]
    schedule = facts.outcome.schedule
    child_records: dict[str, list[object]] = {}
    for time_ns in instants:
        # 1. fill outcomes landing now (only after the anchor: fills at the anchor instant precede its trigger)
        if builder.opened and time_ns > builder.anchor_opened:
            for fill in facts.outcome.fills:
                if fill.execution_time_ns != time_ns:
                    continue
                transition = facts.fills.get(fill.fill_digest)
                if fill.outcome in _EXECUTED and transition is not None:
                    if transition.transition_kind not in _CLOSE_ONLY:
                        if not builder.position_unproven:
                            builder.position_unproven = True
                            builder.event(
                                GovernedPaperProtectiveLedgerEventKind.POSITION_UNPROVEN,
                                time_ns,
                                reason="exposure_increased_after_the_anchor",
                            )
                        continue
                    quantity = Fraction(transition.closed_quantity)
                    builder.closed += quantity
                    identity = _fill_id(fill)
                    source = facts.sources[fill.intent_id]
                    builder.fills.append(
                        GovernedPaperProtectiveFill(
                            identity,
                            source,
                            time_ns,
                            transition.closed_quantity,
                            fill.fill_price,  # type: ignore[arg-type]
                        )
                    )
                    if source is GovernedPaperProtectiveFillSource.CHILD:
                        child = next(item for item in children if item.record.child_id == fill.intent_id)
                        child_records.setdefault(child.child_id, []).append(
                            (identity, quantity, Fraction(fill.fill_price))
                        )  # type: ignore[arg-type]
                        builder.event(
                            GovernedPaperProtectiveLedgerEventKind.CHILD_FILLED,
                            time_ns,
                            quantity=transition.closed_quantity,
                            reference=child.child_id,
                        )
                    continue
                child = next((item for item in children if item.record.child_id == fill.intent_id), None)
                if child is None or fill.outcome is not HistoricalExecutionFillOutcome.REJECTED:
                    continue
                if fill.reason in _BOOK_REJECTIONS:
                    kind = GovernedPaperProtectiveLedgerEventKind.BOOK_UNAVAILABLE
                elif fill.reason in _AUTHORITY_REFUSALS:
                    kind = GovernedPaperProtectiveLedgerEventKind.AUTHORITY_UNPROVEN
                elif fill.reason == _FLATTEN_REFUSAL:
                    kind = GovernedPaperProtectiveLedgerEventKind.INTEGRITY_UNPROVEN
                else:
                    raise _fail("child_outcome_unrecognized")
                builder.event(kind, time_ns, reference=child.child_id, reason=fill.reason)
            if (
                builder.anchor_q0 - builder.closed != abs(_position_after(excursion, time_ns))
                and not builder.position_unproven
            ):
                builder.position_unproven = True
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.POSITION_UNPROVEN,
                    time_ns,
                    reason="anchor_minus_closed_differs_from_the_verified_position",
                )
            if end is not None and time_ns == end:
                closing = [
                    fill for fill in facts.outcome.fills if fill.execution_time_ns == end and fill.outcome in _EXECUTED
                ]
                builder.discharged_at = end
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.DISCHARGED,
                    time_ns,
                    reference="" if not closing else _fill_id(closing[-1]),
                    reason="verified_position_zero",
                )
                break
        # 3. new proven triggers now, in the §6.6 order
        for start, trigger in applicable:
            if start != time_ns:
                continue
            if any(item.trigger_kind is trigger.kind for item in builder.obligations):
                continue  # a repeat of an open kind opens nothing and appends nothing
            joining = builder.opened
            if not joining:
                builder.open(trigger, time_ns)
            before = builder.effective_deadline()
            obligation = builder.obligation(trigger, time_ns)
            builder.obligations.append(obligation)
            if not joining:
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.OPENED,
                    time_ns,
                    obligation_id=obligation.obligation_id,
                    quantity=_render(builder.anchor_q0),
                    reference=builder.anchor_digest,
                )
            else:
                reference, requested = _in_flight(facts, time_ns)
                authority = _covering(schedule.protective_windows, time_ns)
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.MERGED,
                    time_ns,
                    obligation_id=obligation.obligation_id,
                    merge=GovernedPaperProtectiveMerge(
                        anchor_digest=builder.anchor_digest,
                        joining_obligation_id=obligation.obligation_id,
                        joining_trigger_proof_digest=trigger.proof_digest,
                        effective_deadline_before_ns=before,
                        effective_deadline_after_ns=builder.effective_deadline(),
                        attributed_fill_ids=tuple(item.fill_id for item in builder.fills),
                        attributed_fill_quantities=tuple(item.quantity for item in builder.fills),
                        closed_quantity=_render(builder.closed),
                        in_flight_reference=reference,
                        in_flight_requested_quantity=requested,
                        caps=obligation.caps,
                        dec1_authority_digest="" if authority is None else authority.authority_digest,  # type: ignore[attr-defined]
                    ),
                )
            if not obligation.integrity_class:
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.CAP_UNPROVEN,
                    time_ns,
                    obligation_id=obligation.obligation_id,
                    reason="nonurgent_demand_undefined_target_hc_11c_impact_hc_11f_participation_hd_04",
                )
                if _covering(schedule.protective_windows, time_ns) is None:
                    builder.event(
                        GovernedPaperProtectiveLedgerEventKind.AUTHORITY_UNPROVEN,
                        time_ns,
                        obligation_id=obligation.obligation_id,
                        reason="dec1_protective_window_absent",
                    )
        if not builder.opened:
            continue
        # 4. at most one child: the engine's own derivation, and the integrity class's book proof
        for child in children:
            if child.record.attempt_time_ns != time_ns:
                continue
            if child.refused_at_attempt:
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.AUTHORITY_UNPROVEN,
                    time_ns,
                    reference=child.child_id,
                    reason=child.refused_at_attempt,
                )
            else:
                builder.event(
                    GovernedPaperProtectiveLedgerEventKind.CHILD_SENT,
                    time_ns,
                    quantity=child.record.requested_quantity,
                    reference=child.child_id,
                )
        integrity = [item for item in builder.obligations if item.integrity_class]
        if (
            integrity
            and not builder.integrity_unproven_recorded
            and _covering(schedule.flatten_windows, time_ns) is None
        ):
            builder.integrity_unproven_recorded = True
            builder.event(
                GovernedPaperProtectiveLedgerEventKind.INTEGRITY_UNPROVEN,
                time_ns,
                obligation_id=integrity[0].obligation_id,
                reason="book_not_authenticated_independently_of_the_proven_threat",
            )
        # 5. every deadline reached now, once, while exposure remains
        for obligation in builder.obligations:
            if obligation.obligation_id in builder.recorded_deadlines or obligation.deadline_ns > time_ns:
                continue
            remaining = builder.remaining(time_ns)
            if remaining <= 0:
                continue
            builder.recorded_deadlines.add(obligation.obligation_id)
            builder.event(
                GovernedPaperProtectiveLedgerEventKind.DEADLINE_MISSED,
                time_ns,
                obligation_id=obligation.obligation_id,
                unfulfilled=GovernedPaperUnfulfilledProtectiveObligation(
                    schema_version=GOVERNED_PAPER_UNFULFILLED_PROTECTIVE_OBLIGATION_SCHEMA,
                    obligation_id=obligation.obligation_id,
                    deadline_ns=obligation.deadline_ns,
                    evaluated_at_ns=time_ns,
                    remaining_exposure=_render(remaining),
                    reason=_unfulfilled_reason(builder, obligation, facts, time_ns),
                ),
            )
    records = []
    for child in children:
        if child.record.attempt_time_ns < builder.anchor_opened:  # pragma: no cover - a child needs a proven trigger
            continue
        attributed = child_records.get(child.child_id, [])
        filled = sum((quantity for _, quantity, _ in attributed), Fraction(0))
        vwap = (
            None if filled == 0 else sum((quantity * price for _, quantity, price in attributed), Fraction(0)) / filled
        )
        if child.refused_at_attempt:
            state = f"REJECTED:{child.refused_at_attempt}"
        elif child.outcome is None:
            state = "IN_FLIGHT"
        elif child.outcome.outcome is HistoricalExecutionFillOutcome.REJECTED:
            state = f"REJECTED:{child.outcome.reason}"
        else:
            state = child.outcome.outcome.value
        records.append(
            GovernedPaperProtectiveChildRecord(
                child_id=child.child_id,
                decision_time_ns=child.record.attempt_time_ns,
                requested_quantity=child.record.requested_quantity,
                attributed_fill_ids=tuple(identity for identity, _, _ in attributed),
                filled_quantity=_render(filled),
                vwap=None if vwap is None else historical_execution_render_amount(vwap),
                outcome=state,
            )
        )
    last = instants[-1] if instants else builder.anchor_opened
    return GovernedPaperProtectiveSchedule(
        schedule_id=builder.schedule_id,
        position_id=excursion.position_id,
        anchor_opened_ns=builder.anchor_opened,
        anchor_q0=_render(builder.anchor_q0),
        anchor_digest=builder.anchor_digest,
        position_proof_digest=builder.position_proof,
        first_trigger_proof_digest=builder.first_proof,
        obligations=tuple(builder.obligations),
        events=tuple(builder.events),
        attributed_fills=tuple(builder.fills),
        children=tuple(records),
        closed_quantity=_render(builder.closed),
        remaining_quantity=_render(Fraction(0) if builder.discharged_at is not None else builder.remaining(last)),
        status=GovernedPaperProtectiveScheduleStatus.OPEN
        if builder.discharged_at is None
        else GovernedPaperProtectiveScheduleStatus.DISCHARGED,
        discharged_at_ns=builder.discharged_at,
        head_event_digest=builder.events[-1].event_digest if builder.events else builder.anchor_digest,
    )


def derive_governed_paper_protective_ledger(  # noqa: PLR0913, C901 - one evaluation's authoritative inputs
    *,
    genesis_digest: str,
    instrument: str,
    start_ns: int,
    outcome: HistoricalExecutionGovernedPaperOutcome,
    ladder: GovernedPaperKillSwitchLadder,
    system_states: Sequence[GovernedPaperSystemStateReading],
    decision_instants: Sequence[int],
    context: GovernedPaperProtectiveLedgerContext,
    book_source_digest: str,
    depth_cap_fraction: str,
) -> GovernedPaperProtectiveLedgerEvidence:
    """The v2 ledger of one governed evaluation (see the module docstring). Pure.

    ``outcome`` is that evaluation's one engine re-run under schedule v6 (outcome v4), ``ladder`` the kill-switch ladder
    of the same re-run, ``system_states`` the §1.29 readings of its entry decisions, ``decision_instants`` every decision
    instant of its run, ``context`` the IR-2 proofs known at the horizon, ``book_source_digest`` the dataset's source
    manifest digest (the authentication identity of the lineage's book) and ``depth_cap_fraction`` the economics
    policy's visible-depth cap fraction. The schedule's halt and flatten windows must be exactly those the context
    implies. Malformed or foreign input raises ``GovernedPaperProtectiveLedgerError``.
    """

    if type(outcome) is not HistoricalExecutionGovernedPaperOutcome or outcome.simulated is not True:
        raise _fail("outcome_malformed")
    if outcome.schema_version != HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_GOVERNED_PAPER_OUTCOME_SCHEMA_VERSION:
        raise _fail("outcome_needs_the_schedule_v6_re_run")
    if historical_execution_governed_paper_outcome_digest(outcome) != outcome.outcome_digest:
        raise _fail("outcome_digest_mismatch")
    if outcome.schedule.schema_version != HISTORICAL_EXECUTION_PROTECTIVE_LEDGER_ADMISSION_SCHEDULE_SCHEMA_VERSION:
        raise _fail("outcome_needs_the_schedule_v6_re_run")  # pragma: no cover - outcome v4 only under schedule v6
    if type(ladder) is not GovernedPaperKillSwitchLadder:
        raise _fail("ladder_malformed")
    if governed_paper_kill_switch_ladder_digest(ladder) != ladder.ladder_digest:
        raise _fail("ladder_digest_mismatch")
    if ladder.governed_outcome_digest != outcome.outcome_digest:
        raise _fail("ladder_not_of_this_re_run")
    if not edge_is_hex64(genesis_digest):
        raise _fail("genesis_digest_malformed")
    _text(instrument, "instrument")
    if outcome.instrument != instrument:
        raise _fail("outcome_not_of_this_instrument")
    _instant(start_ns, "start_ns")
    horizon = outcome.evaluation_end_ns
    readings = tuple(system_states)
    for item in readings:
        if type(item) is not GovernedPaperSystemStateReading:
            raise _fail("system_state_malformed")
        if governed_paper_system_state_reading_digest(item) != item.reading_digest:
            raise _fail("system_state_digest_mismatch")
    instants = tuple(decision_instants)
    if any(not historical_execution_wire_int_is_valid(item, minimum=0) for item in instants):
        raise _fail("decision_instants_malformed")
    if not historical_execution_decimal_is_canonical(depth_cap_fraction):
        raise _fail("depth_cap_fraction_malformed")
    context = governed_paper_protective_ledger_canonical_context(
        context, genesis_digest=genesis_digest, horizon_ns=horizon
    )
    halt, windows = governed_paper_protective_ledger_schedule_bounds(
        context, book_source_digest=book_source_digest, horizon_ns=horizon
    )
    if (outcome.schedule.exposure_halt_from_ns, outcome.schedule.flatten_windows) != (halt, windows):
        raise _fail("schedule_protective_ledger_bounds_not_derived")
    integrity = _triggers(context, book_source_digest)

    fills = {item.fill_digest: item for item in outcome.position_transitions}
    by_digest = {item.fill_digest: item for item in outcome.fills}
    children = _child_facts(outcome)
    sources: dict[str, GovernedPaperProtectiveFillSource] = {}
    for child in children:
        sources[child.record.child_id] = GovernedPaperProtectiveFillSource.CHILD
    attempts = {item.attempt_id for item in outcome.protective_attempts}
    for item in outcome.fills:
        if item.intent_id not in sources:
            sources[item.intent_id] = (
                GovernedPaperProtectiveFillSource.V1_ATTEMPT
                if item.intent_id in attempts
                else GovernedPaperProtectiveFillSource.DECISION
            )
    v1_attempts = []
    for attempt in outcome.protective_attempts:
        results = [item for item in outcome.fills if item.intent_id == attempt.attempt_id]
        resolved: int | None = None
        if results and results[-1].outcome is not HistoricalExecutionFillOutcome.UNFILLED:
            resolved = (
                attempt.attempt_time_ns if results[-1].execution_time_ns is None else results[-1].execution_time_ns
            )
        v1_attempts.append((attempt.attempt_time_ns, resolved))
    engine_instants = {
        *instants,
        *(
            item.time_ns
            for item in outcome.valuations
            if item.valuation_kind is not HistoricalExecutionValuationKind.EVALUATION_END
        ),
        *(item.execution_time_ns for item in outcome.fills if item.execution_time_ns is not None),
        *(item.attempt_time_ns for item in outcome.protective_attempts),
        *(item.attempt_time_ns for item in outcome.protective_children),
        *(item.created_at_ns for item in outcome.protective_obligations),
    }
    facts = _Facts(
        outcome=outcome,
        fills=fills,
        sources=sources,
        children=children,
        v1_attempts=tuple(v1_attempts),
        v1_obligations=tuple((item.created_at_ns, item.discharged_at_ns) for item in outcome.protective_obligations),
        instants=tuple(sorted(item for item in engine_instants if item < horizon)),
        horizon_ns=horizon,
    )
    triggers: list[_Trigger] = []
    ks3 = _ks3_trigger(ladder)
    if ks3 is not None:
        triggers.append(ks3)
    triggers.extend(
        _Trigger(item.decision_time_ns, GovernedPaperProtectiveObligationKind.SS3_CLOSE, item.reading_digest)
        for item in readings
        if item.state_lower_bound >= _SS3_STATE
    )
    triggers.extend(_Trigger(item.trigger_time_ns, item.trigger_kind, item.proof_digest) for item in integrity)
    schedules = tuple(
        schedule
        for excursion in _excursions(outcome, genesis_digest, by_digest)
        for schedule in (
            _schedule(facts, excursion, triggers, genesis_digest=genesis_digest, depth_cap=depth_cap_fraction),
        )
        if schedule is not None
    )
    threatened = [item.trigger_time_ns for item in integrity if item.book_threatened]
    seed = GovernedPaperProtectiveLedgerEvidence(
        schema_version=GOVERNED_PAPER_PROTECTIVE_LEDGER_EVIDENCE_SCHEMA,
        contract_id=GOVERNED_PAPER_PROTECTIVE_LEDGER_CONTRACT_ID,
        rule_id=GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_ID,
        rule_digest=GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_DIGEST,
        instrument=instrument,
        genesis_digest=genesis_digest,
        start_ns=start_ns,
        horizon_ns=horizon,
        governed_outcome_digest=outcome.outcome_digest,
        kill_switch_ladder_digest=ladder.ladder_digest,
        book_source_digest=book_source_digest,
        integrity_triggers=integrity,
        integrity_halt_from_ns=halt,
        book_threatened_from_ns=min(threatened) if threatened else None,
        schedules=schedules,
        open_obligation_count=sum(
            len(item.obligations) for item in schedules if item.status is GovernedPaperProtectiveScheduleStatus.OPEN
        ),
        evidence_digest="",
    )
    return replace(seed, evidence_digest=edge_payload_digest(_to_payload(seed), "evidence_digest"))


# --- reading a ledger ----------------------------------------------------------------------------------------------------


def governed_paper_protective_ledger_open_at(
    evidence: GovernedPaperProtectiveLedgerEvidence, time_ns: int
) -> tuple[str, ...]:
    """The obligations open after the child derivation of ``time_ns`` (§6.6 step 5 reads them), in schedule order."""

    return tuple(
        obligation.obligation_id
        for schedule in evidence.schedules
        if schedule.discharged_at_ns is None or time_ns < schedule.discharged_at_ns
        for obligation in schedule.obligations
        if obligation.opened_ns <= time_ns
    )


def governed_paper_protective_ledger_halted_at(evidence: GovernedPaperProtectiveLedgerEvidence, time_ns: int) -> bool:
    """Whether a proven integrity trigger halts every exposure increase at ``time_ns``."""

    halt = evidence.integrity_halt_from_ns
    return halt is not None and halt <= time_ns


def governed_paper_protective_ledger_prefix_digest(
    evidence: GovernedPaperProtectiveLedgerEvidence, *, before_ns: int
) -> str:
    """The digest of the ledger strictly before the nanosecond ``before_ns``: the integrity triggers, each schedule's
    anchor, the obligations opened and the events appended before it. Every field is a content identity, so a causal
    replay over a later archive yields the same prefix (X1 for the ledger)."""

    if type(evidence) is not GovernedPaperProtectiveLedgerEvidence:
        raise _fail("evidence_malformed")
    _instant(before_ns, "before_ns")
    return edge_sha256_text(
        edge_canonical_json(
            {
                "rule_digest": evidence.rule_digest,
                "genesis_digest": evidence.genesis_digest,
                "start_ns": evidence.start_ns,
                "integrity_triggers": [
                    _to_payload(item) for item in evidence.integrity_triggers if item.trigger_time_ns < before_ns
                ],
                "schedules": [
                    {
                        "schedule_id": schedule.schedule_id,
                        "position_id": schedule.position_id,
                        "anchor_opened_ns": schedule.anchor_opened_ns,
                        "anchor_q0": schedule.anchor_q0,
                        "anchor_digest": schedule.anchor_digest,
                        "obligations": [
                            _to_payload(item) for item in schedule.obligations if item.opened_ns < before_ns
                        ],
                        "events": [_to_payload(item) for item in schedule.events if item.time_ns < before_ns],
                    }
                    for schedule in evidence.schedules
                    if schedule.anchor_opened_ns < before_ns
                ],
            }
        )
    )


def governed_paper_protective_ledger_evidence_to_dict(
    evidence: GovernedPaperProtectiveLedgerEvidence,
) -> dict[str, object]:
    return _to_payload(evidence)


def governed_paper_protective_ledger_evidence_digest(evidence: GovernedPaperProtectiveLedgerEvidence) -> str:
    """Recompute the evidence digest, excluding only ``evidence_digest``."""

    return edge_payload_digest(_to_payload(evidence), "evidence_digest")


def governed_paper_protective_ledger_event_chain_intact(schedule: GovernedPaperProtectiveSchedule) -> bool:
    """Whether every event of ``schedule`` recomputes its digest and chains to its predecessor (the anchor first)."""

    previous = schedule.anchor_digest
    for index, item in enumerate(schedule.events):
        if item.sequence != index or item.previous_event_digest != previous:
            return False
        if edge_payload_digest(_to_payload(item), "event_digest") != item.event_digest:
            return False
        previous = item.event_digest
    return schedule.head_event_digest == previous


__all__ = [
    "GOVERNED_PAPER_INTEGRITY_PRODUCTION_APPROVAL_TABLE",
    "GOVERNED_PAPER_INTEGRITY_TRIGGER_PROOF_SCHEMA",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_CONTRACT_ID",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_EVIDENCE_SCHEMA",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_HORIZON",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_DIGEST",
    "GOVERNED_PAPER_PROTECTIVE_LEDGER_RULE_ID",
    "GOVERNED_PAPER_UNFULFILLED_PROTECTIVE_OBLIGATION_SCHEMA",
    "GovernedPaperIntegrityAnchor",
    "GovernedPaperIntegrityApprovalTable",
    "GovernedPaperIntegrityTrigger",
    "GovernedPaperIntegrityTriggerProof",
    "GovernedPaperIntegrityVerifierKind",
    "GovernedPaperProtectiveCaps",
    "GovernedPaperProtectiveChildRecord",
    "GovernedPaperProtectiveFill",
    "GovernedPaperProtectiveFillSource",
    "GovernedPaperProtectiveLedgerContext",
    "GovernedPaperProtectiveLedgerError",
    "GovernedPaperProtectiveLedgerEvent",
    "GovernedPaperProtectiveLedgerEventKind",
    "GovernedPaperProtectiveLedgerEvidence",
    "GovernedPaperProtectiveMerge",
    "GovernedPaperProtectiveObligation",
    "GovernedPaperProtectiveObligationKind",
    "GovernedPaperProtectiveSchedule",
    "GovernedPaperProtectiveScheduleStatus",
    "GovernedPaperUnfulfilledProtectiveObligation",
    "GovernedPaperUnfulfilledReason",
    "build_governed_paper_integrity_anchor",
    "build_governed_paper_integrity_trigger_proof",
    "derive_governed_paper_protective_ledger",
    "governed_paper_integrity_active_table",
    "governed_paper_integrity_proof_admission",
    "governed_paper_protective_ledger_canonical_context",
    "governed_paper_protective_ledger_event_chain_intact",
    "governed_paper_protective_ledger_evidence_digest",
    "governed_paper_protective_ledger_evidence_to_dict",
    "governed_paper_protective_ledger_halted_at",
    "governed_paper_protective_ledger_open_at",
    "governed_paper_protective_ledger_prefix_digest",
    "governed_paper_protective_ledger_rule",
    "governed_paper_protective_ledger_schedule_bounds",
]
