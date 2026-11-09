"""Governed paper CTR source qualification (``S1_APPROVED_SIZING_CHAIN_CONSTRUCTION_V1``): the CTR_SOURCE_QUALIFICATION_V1
consumer and the PRDV4 §1.12 Mechanism 2 / §7.2 depth cap.

Design authority: ``docs/PRDV4_MULTI_MARKET_CRYPTO.md`` §1.2 A.4 (amendment D15), §1.12 Mechanism 2 and §7.2, and the
approved companion ``docs/crypto_core/s1_approved_doctrine_adoption_v1.md`` §5 (items 3.1-3.2), adopted by PR #433. The
method is approved; NO real source is qualified (X-M1-C), and this module creates no qualification. Paper-only,
deterministic, point-in-time and fail-closed. Arithmetic is exact (``int`` and ``Fraction``; no float, no ``decimal``
context), and there is no IO, clock, randomness, network or environment.

Qualification. A ``GovernedPaperCtrSourceQualification`` records the §5 fields: the exact source identity (provider,
dataset or channel, venue, instrument, source version), the source class (``ORDER_LEVEL_EVENTS`` or
``VENUE_PUBLISHED_COUNTS``, nothing else), the rights (licence reference and digest, permitted uses, and whether this
system may process the source), the cancel and trade definitions, the coverage method and the approval (kind, approver
reference, approval instant). Revocations and supersessions are separate digest-bound records that apply from their own
instant. The approval table decides whether a qualification may be used:

* the PRODUCTION table admits only a HUMAN_GOVERNANCE qualification whose digest a separate human authorization lists. It
  lists none, so in production every CTR reading is unavailable and the depth cap never passes;
* a TEST-ONLY table, installed by tests alone, admits only TEST_ONLY_SYNTHETIC qualifications.

A usable qualification must also permit this system's use (``GOVERNED_PAPER_CTR_REQUIRED_USE``) and its processing.

Capture. A ``GovernedPaperCtrSourceCapture`` holds the source's records as received, bound to the qualification by
digest and by the exact source identity, and complete for every record received at or before
``complete_through_receipt_ns``. Each record has a sequence id, a publication instant and a receipt instant (never before
its publication). Its integrity is its digest binding; the origin of its timestamps is not proven by this system.

Reading at instant ``t`` (§1.2 A.4 and §5). Over the window ``(t - 60 s, t]``, a record counts only when it was received
at or before ``t``. The qualification must be admitted, approved at or before ``t``, neither revoked nor superseded at or
before ``t``, and of the genesis instrument; the capture must be complete through ``t``. The window must be covered,
judged on the records received at or before ``t`` in the capture's own receipt order, which is never re-sorted (a sort
by sequence id would erase the evidence of an arrival reorder): the anchor is the record of the highest sequence id
published at or before ``t - 60 s``, and the anchor, every record received after it and every record published inside
the window must carry exactly the anchor's sequence id and its successors, each received after its predecessor, with
publication instants that never run backwards (a gap, a duplicate or a reorder is BLOCKED). Records sharing a receipt
instant keep the capture's order, so a tie in any order other than the sequence's is a reorder; no arrival order is
inferred. For ``VENUE_HEARTBEATS`` there must also be no publication gap above the declared interval up to ``t``. The
capture's digest integrity never implies coverage: an intact capture can hold a reorder that blocks every reading whose
span contains it. ``ORDER_LEVEL_EVENTS`` count the cancels the definition names and every trade record;
``VENUE_PUBLISHED_COUNTS`` must tile the window exactly with contiguous published intervals. ``N_trades = 0`` is
BLOCKED. ``CTR = N_cancels / N_trades``; ``alpha = 1`` when ``CTR <= 5`` and ``1 / (1 + 0.2 (CTR - 5))`` above. No count
is ever inferred from L2 book changes, a quote disappearance, turnover or a model: no such path exists.

Depth (§1.12 Mechanism 2, §7.2). ``D`` is the visible depth within 5 bps of the mid on the side the order consumes
(the asks for a buy, the bids for a sell; the side the engine's fill model reads), the summed base quantity of that
side's levels inside the band of the dataset's authenticated ORDER_BOOK depth-50 tip. The dataset is re-proven whole
first, through ``verify_historical_pit_dataset``, and must be intact, READY and advancing: an authentic manifest is
never authority over the records, and a carried digest never authenticates altered records, so such a dataset yields no
index, no depth and no cap. ``D`` is exact when the side's 50th level lies strictly beyond the band, otherwise a lower
bound. At a decision the tip is the latest one visible at ``t`` by native event time and fresh within 10 s (the NT-D02
reading); at a fill it is the book record the fill executes against. Evaluation, with ``q`` the order quantity: FAIL
when ``q >= 0.02 D`` on an exact ``D`` (no CTR needed, since ``alpha <= 1``); PASS when ``q < 0.02 alpha D`` with a
qualified, covered reading; BLOCKED otherwise. The fill model's own depth cap is unchanged.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum
from fractions import Fraction

from crypto_core.validation.edge_artifact_core import (
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
)
from crypto_core.validation.governed_paper_regime_state import (
    GovernedPaperRegimeError,
    governed_paper_order_book_levels,
    governed_paper_order_book_series,
)
from crypto_core.validation.historical_execution_economics import HistoricalExecutionSide
from crypto_core.validation.historical_execution_economics_policy import (
    historical_execution_render_amount,
    historical_execution_wire_int_is_valid,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitRecord,
    verify_historical_pit_dataset,
)

_PREFIX = "governed_paper_ctr_qualification"
_NS = 1_000_000_000
_WINDOW_NS = 60 * _NS  # §1.2 A.4: rolling T = 60 s
_BOOK_FRESHNESS_NS = 10 * _NS  # the NT-D02 freshness of a decision-time book tip
_UNIT = 10**18  # the integer units of an ORDER_BOOK level (scale 18)
GOVERNED_PAPER_CTR_CONTRACT_ID = "CTR_SOURCE_QUALIFICATION_V1"
GOVERNED_PAPER_CTR_QUALIFICATION_SCHEMA = "governed-paper-ctr-source-qualification.v1"
GOVERNED_PAPER_CTR_REVOCATION_SCHEMA = "governed-paper-ctr-qualification-revocation.v1"
GOVERNED_PAPER_CTR_CAPTURE_SCHEMA = "governed-paper-ctr-source-capture.v1"
GOVERNED_PAPER_CTR_REQUIRED_USE = "crypto_core_paper_ctr_depth_cap"
GOVERNED_PAPER_CTR_THRESHOLD = Fraction(5)  # §1.2 A.4: CTR > 5.0 reduces depth trust
GOVERNED_PAPER_CTR_SLOPE = Fraction(1, 5)  # §1.2 A.4: 0.2
GOVERNED_PAPER_CTR_DEPTH_FRACTION = Fraction(2, 100)  # §1.12 Mechanism 2 and §7.2: strictly below 2% of the depth
GOVERNED_PAPER_CTR_DEPTH_BAND = Fraction(5, 10_000)  # §1.12 Mechanism 2 and §7.2: within 5 bps of the mid
GOVERNED_PAPER_CTR_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    ("paper_only", True),
    ("real_source_qualified", False),
    ("timestamp_origin_proven", False),
    ("venue_facts_proven", False),
    ("production_use_authorized", False),
)


class GovernedPaperCtrError(EdgeArtifactError):
    """Malformed input or a binding defect: no qualification, capture or reading is represented over it."""


class GovernedPaperCtrSourceClass(str, Enum):
    ORDER_LEVEL_EVENTS = "ORDER_LEVEL_EVENTS"
    VENUE_PUBLISHED_COUNTS = "VENUE_PUBLISHED_COUNTS"


class GovernedPaperCtrApprovalKind(str, Enum):
    """HUMAN_GOVERNANCE still needs a separate production authorization; TEST_ONLY_SYNTHETIC exists for tests only."""

    HUMAN_GOVERNANCE = "HUMAN_GOVERNANCE"
    TEST_ONLY_SYNTHETIC = "TEST_ONLY_SYNTHETIC"


class GovernedPaperCtrCancelDefinition(str, Enum):
    FULL_CANCEL_ONLY = "FULL_CANCEL_ONLY"
    FULL_CANCEL_AND_PARTIAL_REDUCTION = "FULL_CANCEL_AND_PARTIAL_REDUCTION"
    FULL_CANCEL_PARTIAL_REDUCTION_AND_AMEND = "FULL_CANCEL_PARTIAL_REDUCTION_AND_AMEND"


class GovernedPaperCtrTradeDefinition(str, Enum):
    PER_MATCH = "PER_MATCH"
    AGGREGATED_PER_TAKER_ORDER = "AGGREGATED_PER_TAKER_ORDER"


class GovernedPaperCtrCoverageMethod(str, Enum):
    SEQUENCE_CONTINUITY = "SEQUENCE_CONTINUITY"
    VENUE_HEARTBEATS = "VENUE_HEARTBEATS"


class GovernedPaperCtrRecordKind(str, Enum):
    ORDER_ADD = "ORDER_ADD"
    ORDER_CANCEL_FULL = "ORDER_CANCEL_FULL"
    ORDER_CANCEL_PARTIAL = "ORDER_CANCEL_PARTIAL"
    ORDER_AMEND = "ORDER_AMEND"
    TRADE = "TRADE"
    PUBLISHED_COUNTS = "PUBLISHED_COUNTS"
    HEARTBEAT = "HEARTBEAT"


class GovernedPaperCtrRevocationKind(str, Enum):
    REVOKED = "REVOKED"
    SUPERSEDED = "SUPERSEDED"


class GovernedPaperCtrDepthStatus(str, Enum):
    PASS = "PASS"  # noqa: S105 - check status label, not a credential.
    FAIL = "FAIL"
    BLOCKED = "BLOCKED"


_EVENT_KINDS = frozenset(
    {
        GovernedPaperCtrRecordKind.ORDER_ADD,
        GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL,
        GovernedPaperCtrRecordKind.ORDER_CANCEL_PARTIAL,
        GovernedPaperCtrRecordKind.ORDER_AMEND,
        GovernedPaperCtrRecordKind.TRADE,
        GovernedPaperCtrRecordKind.HEARTBEAT,
    }
)
_COUNT_KINDS = frozenset({GovernedPaperCtrRecordKind.PUBLISHED_COUNTS, GovernedPaperCtrRecordKind.HEARTBEAT})
_CANCELS = {
    GovernedPaperCtrCancelDefinition.FULL_CANCEL_ONLY: frozenset({GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL}),
    GovernedPaperCtrCancelDefinition.FULL_CANCEL_AND_PARTIAL_REDUCTION: frozenset(
        {GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL, GovernedPaperCtrRecordKind.ORDER_CANCEL_PARTIAL}
    ),
    GovernedPaperCtrCancelDefinition.FULL_CANCEL_PARTIAL_REDUCTION_AND_AMEND: frozenset(
        {
            GovernedPaperCtrRecordKind.ORDER_CANCEL_FULL,
            GovernedPaperCtrRecordKind.ORDER_CANCEL_PARTIAL,
            GovernedPaperCtrRecordKind.ORDER_AMEND,
        }
    ),
}


@dataclass(frozen=True)
class GovernedPaperCtrSourceQualification:
    """One CTR source qualification record (§5); ``qualification_digest`` covers every other field."""

    schema_version: str
    qualification_id: str
    revision: str
    provider: str
    dataset_channel: str
    venue: str
    instrument: str
    source_version: str
    source_class: GovernedPaperCtrSourceClass
    licence_reference: str
    licence_digest: str
    permitted_uses: tuple[str, ...]
    processing_by_this_system_permitted: bool
    cancel_definition: GovernedPaperCtrCancelDefinition
    trade_definition: GovernedPaperCtrTradeDefinition
    coverage_method: GovernedPaperCtrCoverageMethod
    heartbeat_max_interval_ns: int | None
    approval_kind: GovernedPaperCtrApprovalKind
    approver_reference: str
    approval_time_ns: int
    qualification_digest: str
    production_use_authorized: bool = False


@dataclass(frozen=True)
class GovernedPaperCtrQualificationRevocation:
    """One revocation or supersession of a qualification, applying from ``effective_from_ns``, never retroactively."""

    schema_version: str
    revocation_id: str
    qualification_digest: str
    kind: GovernedPaperCtrRevocationKind
    effective_from_ns: int
    approval_kind: GovernedPaperCtrApprovalKind
    approver_reference: str
    revocation_digest: str


@dataclass(frozen=True)
class GovernedPaperCtrApprovalTable:
    """Which qualifications may be used: ``production`` lists HUMAN_GOVERNANCE digests; ``test_only`` lists none."""

    table_id: str
    admitted_kind: GovernedPaperCtrApprovalKind
    admitted_qualification_digests: tuple[str, ...]


# No separate human authorization lists any qualification digest for production use, so this table refuses every one.
GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE = GovernedPaperCtrApprovalTable(
    table_id="production",
    admitted_kind=GovernedPaperCtrApprovalKind.HUMAN_GOVERNANCE,
    admitted_qualification_digests=(),
)
_APPROVAL_TABLE = GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE  # tests alone install a test-only table


@dataclass(frozen=True)
class GovernedPaperCtrSourceRecord:
    """One source record as received. ``PUBLISHED_COUNTS`` carries its interval ``(start, end]`` and its two counts;
    every other kind carries none of them."""

    sequence_id: int
    kind: GovernedPaperCtrRecordKind
    publication_time_ns: int
    receipt_time_ns: int
    interval_start_ns: int | None = None
    interval_end_ns: int | None = None
    cancel_count: int | None = None
    trade_count: int | None = None


@dataclass(frozen=True)
class GovernedPaperCtrSourceCapture:
    """The source's records in receipt order, complete through ``complete_through_receipt_ns``."""

    schema_version: str
    capture_id: str
    qualification_digest: str
    provider: str
    dataset_channel: str
    venue: str
    instrument: str
    source_version: str
    source_class: GovernedPaperCtrSourceClass
    complete_through_receipt_ns: int
    records: tuple[GovernedPaperCtrSourceRecord, ...]
    capture_digest: str


@dataclass(frozen=True)
class GovernedPaperCtrSourceContext:
    """One CTR source as the day seal supplies it: the qualification, its revocations known at the seal, its capture."""

    qualification: GovernedPaperCtrSourceQualification
    revocations: tuple[GovernedPaperCtrQualificationRevocation, ...]
    capture: GovernedPaperCtrSourceCapture


@dataclass(frozen=True)
class GovernedPaperCtrReading:
    """The CTR reading at ``time_ns``: its counts, CTR and alpha (exact rational texts), or why none is available."""

    time_ns: int
    available: bool
    reason: str
    cancel_count: int | None
    trade_count: int | None
    ctr: str | None
    alpha: str | None


@dataclass(frozen=True)
class GovernedPaperVisibleDepth:
    """The visible depth within 5 bps on one side of one tip; ``depth`` is an exact rational text or None."""

    side: HistoricalExecutionSide
    book_record_digest: str | None
    depth: str | None
    exact: bool
    reason: str


@dataclass(frozen=True)
class GovernedPaperCtrDepth:
    """One depth-cap reading: status, the observed order share of the visible depth (empty when unavailable), reason."""

    status: GovernedPaperCtrDepthStatus
    observed: str
    reason: str


# --- helpers -----------------------------------------------------------------------------------------------------------


def _reason(code: str) -> str:
    return f"{_PREFIX}:{code}"


def _fail(code: str) -> GovernedPaperCtrError:
    return GovernedPaperCtrError(_reason(code))


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


def _text(value: object, name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or len(value) > 256
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{name}")
    return value


def _instant(value: object, name: str) -> int:
    if not historical_execution_wire_int_is_valid(value, minimum=0):
        raise _fail(f"{name}_invalid")
    return value  # type: ignore[return-value]


def _count(value: object, name: str) -> int:
    if type(value) is not int or value < 0 or value > 10**12:
        raise _fail(f"{name}_invalid")
    return value


def _identical(left: object, right: object) -> bool:
    return type(left) is type(right) and _to_payload(left) == _to_payload(right)


def _verification(digest: str, intact: bool, reasons: tuple[str, ...]) -> EdgeEvidenceVerification:
    return EdgeEvidenceVerification(intact=intact, reason_codes=reasons, recomputed_digest=digest, canonical_json="")


def _verify(
    artifact: object, cls: type, rebuild: Callable[[object], object], digest_field: str
) -> EdgeEvidenceVerification:
    """Re-derive one artifact through its builder; total: never raises."""

    if type(artifact) is not cls:
        return _verification("", False, (_reason(f"{cls.__name__}_malformed"),))
    try:
        rebuilt = rebuild(artifact)
    except GovernedPaperCtrError as exc:
        return _verification("", False, (str(exc),))
    except Exception:  # noqa: BLE001 - VERIFY_IS_TOTAL_FAIL_CLOSED_FOR_ANY_OBJECT
        return _verification("", False, (_reason(f"{cls.__name__}_rebuild_failed"),))
    intact = _identical(artifact, rebuilt)
    reasons = () if intact else (_reason(f"{cls.__name__}_not_its_canonical_form"),)
    return _verification(getattr(rebuilt, digest_field), intact, reasons)


def _rational(value: Fraction) -> str:
    return str(value)


# --- qualification, revocation, capture --------------------------------------------------------------------------------


def build_governed_paper_ctr_source_qualification(  # noqa: PLR0913 - the §5 fields
    *,
    qualification_id: str,
    revision: str,
    provider: str,
    dataset_channel: str,
    venue: str,
    instrument: str,
    source_version: str,
    source_class: GovernedPaperCtrSourceClass,
    licence_reference: str,
    licence_digest: str,
    permitted_uses: tuple[str, ...],
    processing_by_this_system_permitted: bool,
    cancel_definition: GovernedPaperCtrCancelDefinition,
    trade_definition: GovernedPaperCtrTradeDefinition,
    coverage_method: GovernedPaperCtrCoverageMethod,
    heartbeat_max_interval_ns: int | None,
    approval_kind: GovernedPaperCtrApprovalKind,
    approver_reference: str,
    approval_time_ns: int,
) -> GovernedPaperCtrSourceQualification:
    """One CTR source qualification over exactly the §5 fields (a record; never a production permission)."""

    for name, value, cls in (
        ("source_class", source_class, GovernedPaperCtrSourceClass),
        ("cancel_definition", cancel_definition, GovernedPaperCtrCancelDefinition),
        ("trade_definition", trade_definition, GovernedPaperCtrTradeDefinition),
        ("coverage_method", coverage_method, GovernedPaperCtrCoverageMethod),
        ("approval_kind", approval_kind, GovernedPaperCtrApprovalKind),
    ):
        if type(value) is not cls:
            raise _fail(f"qualification_malformed:{name}")
    if not edge_is_hex64(licence_digest):
        raise _fail("qualification_malformed:licence_digest")
    if type(permitted_uses) is not tuple or len(set(permitted_uses)) != len(permitted_uses):
        raise _fail("qualification_malformed:permitted_uses")
    for use in permitted_uses:
        _text(use, "permitted_use")
    if list(permitted_uses) != sorted(permitted_uses):
        raise _fail("qualification_malformed:permitted_uses_not_sorted")
    if type(processing_by_this_system_permitted) is not bool:
        raise _fail("qualification_malformed:processing_by_this_system_permitted")
    heartbeats = coverage_method is GovernedPaperCtrCoverageMethod.VENUE_HEARTBEATS
    if heartbeats:
        if type(heartbeat_max_interval_ns) is not int or not 0 < heartbeat_max_interval_ns <= _WINDOW_NS:
            raise _fail("qualification_malformed:heartbeat_max_interval_ns")
    elif heartbeat_max_interval_ns is not None:
        raise _fail("qualification_malformed:heartbeat_interval_without_heartbeat_coverage")
    seed = GovernedPaperCtrSourceQualification(
        schema_version=GOVERNED_PAPER_CTR_QUALIFICATION_SCHEMA,
        qualification_id=_text(qualification_id, "qualification_id"),
        revision=_text(revision, "revision"),
        provider=_text(provider, "provider"),
        dataset_channel=_text(dataset_channel, "dataset_channel"),
        venue=_text(venue, "venue"),
        instrument=_text(instrument, "instrument"),
        source_version=_text(source_version, "source_version"),
        source_class=source_class,
        licence_reference=_text(licence_reference, "licence_reference"),
        licence_digest=licence_digest,
        permitted_uses=permitted_uses,
        processing_by_this_system_permitted=processing_by_this_system_permitted,
        cancel_definition=cancel_definition,
        trade_definition=trade_definition,
        coverage_method=coverage_method,
        heartbeat_max_interval_ns=heartbeat_max_interval_ns,
        approval_kind=approval_kind,
        approver_reference=_text(approver_reference, "approver_reference"),
        approval_time_ns=_instant(approval_time_ns, "approval_time_ns"),
        qualification_digest="",
    )
    return replace(seed, qualification_digest=edge_payload_digest(_to_payload(seed), "qualification_digest"))


def verify_governed_paper_ctr_source_qualification(qualification: object) -> EdgeEvidenceVerification:
    """Re-derive a qualification through its builder (exact type, fields and digest). Total."""

    def rebuild(item: object) -> object:
        names = [entry.name for entry in fields(GovernedPaperCtrSourceQualification)]
        arguments = {
            name: getattr(item, name)
            for name in names
            if name not in ("schema_version", "qualification_digest", "production_use_authorized")
        }
        return build_governed_paper_ctr_source_qualification(**arguments)  # type: ignore[arg-type]

    return _verify(qualification, GovernedPaperCtrSourceQualification, rebuild, "qualification_digest")


def build_governed_paper_ctr_qualification_revocation(
    *,
    revocation_id: str,
    qualification_digest: str,
    kind: GovernedPaperCtrRevocationKind,
    effective_from_ns: int,
    approval_kind: GovernedPaperCtrApprovalKind,
    approver_reference: str,
) -> GovernedPaperCtrQualificationRevocation:
    """One revocation or supersession of the qualification ``qualification_digest``, from ``effective_from_ns``."""

    if not edge_is_hex64(qualification_digest):
        raise _fail("revocation_malformed:qualification_digest")
    if type(kind) is not GovernedPaperCtrRevocationKind or type(approval_kind) is not GovernedPaperCtrApprovalKind:
        raise _fail("revocation_malformed:kind")
    seed = GovernedPaperCtrQualificationRevocation(
        schema_version=GOVERNED_PAPER_CTR_REVOCATION_SCHEMA,
        revocation_id=_text(revocation_id, "revocation_id"),
        qualification_digest=qualification_digest,
        kind=kind,
        effective_from_ns=_instant(effective_from_ns, "effective_from_ns"),
        approval_kind=approval_kind,
        approver_reference=_text(approver_reference, "approver_reference"),
        revocation_digest="",
    )
    return replace(seed, revocation_digest=edge_payload_digest(_to_payload(seed), "revocation_digest"))


def verify_governed_paper_ctr_qualification_revocation(revocation: object) -> EdgeEvidenceVerification:
    """Re-derive a revocation through its builder. Total."""

    def rebuild(item: object) -> object:
        return build_governed_paper_ctr_qualification_revocation(
            revocation_id=item.revocation_id,  # type: ignore[attr-defined]
            qualification_digest=item.qualification_digest,  # type: ignore[attr-defined]
            kind=item.kind,  # type: ignore[attr-defined]
            effective_from_ns=item.effective_from_ns,  # type: ignore[attr-defined]
            approval_kind=item.approval_kind,  # type: ignore[attr-defined]
            approver_reference=item.approver_reference,  # type: ignore[attr-defined]
        )

    return _verify(revocation, GovernedPaperCtrQualificationRevocation, rebuild, "revocation_digest")


def _canonical_record(record: object, source_class: GovernedPaperCtrSourceClass) -> GovernedPaperCtrSourceRecord:
    if type(record) is not GovernedPaperCtrSourceRecord or type(record.kind) is not GovernedPaperCtrRecordKind:
        raise _fail("capture_malformed:record")
    _instant(record.sequence_id, "record_sequence_id")
    publication = _instant(record.publication_time_ns, "record_publication_time_ns")
    receipt = _instant(record.receipt_time_ns, "record_receipt_time_ns")
    if receipt < publication:
        raise _fail("capture_malformed:record_received_before_its_publication")
    allowed = _EVENT_KINDS if source_class is GovernedPaperCtrSourceClass.ORDER_LEVEL_EVENTS else _COUNT_KINDS
    if record.kind not in allowed:
        raise _fail("capture_malformed:record_kind_not_of_the_source_class")
    counted = (record.interval_start_ns, record.interval_end_ns, record.cancel_count, record.trade_count)
    if record.kind is GovernedPaperCtrRecordKind.PUBLISHED_COUNTS:
        start = _instant(record.interval_start_ns, "record_interval_start_ns")
        end = _instant(record.interval_end_ns, "record_interval_end_ns")
        _count(record.cancel_count, "record_cancel_count")
        _count(record.trade_count, "record_trade_count")
        if not start < end <= publication:
            raise _fail("capture_malformed:published_counts_interval_not_closed_at_publication")
    elif counted != (None, None, None, None):
        raise _fail("capture_malformed:counts_on_a_record_that_is_not_published_counts")
    return record


def build_governed_paper_ctr_source_capture(
    *,
    capture_id: str,
    qualification: GovernedPaperCtrSourceQualification,
    complete_through_receipt_ns: int,
    records: tuple[GovernedPaperCtrSourceRecord, ...],
) -> GovernedPaperCtrSourceCapture:
    """One capture of ``qualification``'s source: records in receipt order, complete through the declared instant."""

    if not verify_governed_paper_ctr_source_qualification(qualification).intact:
        raise _fail("capture_qualification_not_authentic")
    through = _instant(complete_through_receipt_ns, "complete_through_receipt_ns")
    if type(records) is not tuple:
        raise _fail("capture_malformed:records")
    previous = -1
    for record in records:
        _canonical_record(record, qualification.source_class)
        if record.receipt_time_ns < previous:
            raise _fail("capture_malformed:records_not_in_receipt_order")
        if record.receipt_time_ns > through:
            raise _fail("capture_malformed:record_received_after_the_completeness_instant")
        previous = record.receipt_time_ns
    seed = GovernedPaperCtrSourceCapture(
        schema_version=GOVERNED_PAPER_CTR_CAPTURE_SCHEMA,
        capture_id=_text(capture_id, "capture_id"),
        qualification_digest=qualification.qualification_digest,
        provider=qualification.provider,
        dataset_channel=qualification.dataset_channel,
        venue=qualification.venue,
        instrument=qualification.instrument,
        source_version=qualification.source_version,
        source_class=qualification.source_class,
        complete_through_receipt_ns=through,
        records=records,
        capture_digest="",
    )
    return replace(seed, capture_digest=edge_payload_digest(_to_payload(seed), "capture_digest"))


_IDENTITY = ("provider", "dataset_channel", "venue", "instrument", "source_version", "source_class")


def verify_governed_paper_ctr_source_capture(capture: object, qualification: object) -> EdgeEvidenceVerification:
    """Re-derive a capture of ``qualification`` through its builder (identity, records, digest). Total."""

    def rebuild(item: object) -> object:
        if type(qualification) is not GovernedPaperCtrSourceQualification:
            raise _fail("capture_qualification_malformed")
        if any(getattr(item, name) != getattr(qualification, name) for name in _IDENTITY):
            raise _fail("capture_source_identity_not_the_qualification")
        return build_governed_paper_ctr_source_capture(
            capture_id=item.capture_id,  # type: ignore[attr-defined]
            qualification=qualification,
            complete_through_receipt_ns=item.complete_through_receipt_ns,  # type: ignore[attr-defined]
            records=item.records,  # type: ignore[attr-defined]
        )

    return _verify(capture, GovernedPaperCtrSourceCapture, rebuild, "capture_digest")


def governed_paper_ctr_canonical_context(context: object, *, instrument: str) -> GovernedPaperCtrSourceContext:
    """A context whose qualification, revocations and capture are authentic and bound to one another; raises otherwise.

    The qualification must be of ``instrument`` (the genesis instrument); a foreign capture or revocation is refused.
    """

    if type(context) is not GovernedPaperCtrSourceContext:
        raise _fail("ctr_context_malformed")
    qualification = context.qualification
    verification = verify_governed_paper_ctr_source_qualification(qualification)
    if not verification.intact or verification.recomputed_digest != qualification.qualification_digest:
        raise _fail("ctr_qualification_not_authentic")
    if qualification.instrument != instrument:
        raise _fail("ctr_qualification_of_another_instrument")
    revocations = context.revocations
    if type(revocations) is not tuple:
        raise _fail("ctr_revocations_malformed")
    previous = -1
    for revocation in revocations:
        check = verify_governed_paper_ctr_qualification_revocation(revocation)
        if not check.intact or check.recomputed_digest != revocation.revocation_digest:
            raise _fail("ctr_revocation_not_authentic")
        if revocation.qualification_digest != qualification.qualification_digest:
            raise _fail("ctr_revocation_foreign")
        if revocation.effective_from_ns < previous:
            raise _fail("ctr_revocations_not_ordered")
        previous = revocation.effective_from_ns
    capture = context.capture
    capture_check = verify_governed_paper_ctr_source_capture(capture, qualification)
    if not capture_check.intact or capture_check.recomputed_digest != capture.capture_digest:
        raise _fail("ctr_capture_not_authentic")
    if capture.qualification_digest != qualification.qualification_digest:
        raise _fail("ctr_capture_foreign")
    return context


# --- the approval table ------------------------------------------------------------------------------------------------


def _canonical_table(table: object) -> GovernedPaperCtrApprovalTable:
    if type(table) is not GovernedPaperCtrApprovalTable:
        raise _fail("approval_table_malformed")
    digests = table.admitted_qualification_digests
    if type(digests) is not tuple or any(not edge_is_hex64(item) for item in digests):
        raise _fail("approval_table_malformed")
    if table.table_id == "production" and table.admitted_kind is GovernedPaperCtrApprovalKind.HUMAN_GOVERNANCE:
        return table
    if table.table_id == "test_only" and table.admitted_kind is GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC:
        if not digests:
            return table
    raise _fail("approval_table_malformed")


def governed_paper_ctr_admission(
    table: GovernedPaperCtrApprovalTable, qualification: GovernedPaperCtrSourceQualification
) -> str:
    """Why ``qualification`` may not be used under ``table`` (empty when it may)."""

    table = _canonical_table(table)
    kind = qualification.approval_kind
    if table.table_id == "production":
        if kind is GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC:
            return "synthetic_qualification_refused_on_the_production_table"
        if qualification.qualification_digest not in table.admitted_qualification_digests:
            return "qualification_not_authorized_for_production_use"
        return ""
    if kind is not GovernedPaperCtrApprovalKind.TEST_ONLY_SYNTHETIC:
        return "only_test_only_synthetic_qualifications_on_the_test_only_table"
    return ""


def governed_paper_ctr_active_table() -> GovernedPaperCtrApprovalTable:
    """The active approval table (the production table unless a test installed the test-only one)."""

    return _canonical_table(_APPROVAL_TABLE)


# --- the CTR reading ---------------------------------------------------------------------------------------------------


def _unavailable(time_ns: int, reason: str) -> GovernedPaperCtrReading:
    return GovernedPaperCtrReading(time_ns, False, reason, None, None, None, None)


def _coverage(  # noqa: C901 - one linear proof of the window's coverage
    records: Sequence[GovernedPaperCtrSourceRecord],
    *,
    time_ns: int,
    heartbeat_interval_ns: int | None,
) -> str:
    """Why the window ``(t - 60 s, t]`` is not covered by ``records``, the capture's records received at or before ``t``
    in the capture's own receipt order; empty when it is.

    That receipt order is the evidence and is never re-sorted. The anchor is the first-received record of the highest
    sequence id published at or before ``t - 60 s``; the span is the anchor, every record received after it and every
    record published inside the window, in receipt order. Its sequence ids must be exactly the anchor's and its
    successors in that order: an id below the anchor's, or a receipt order other than the sequence order (a tie
    included), is a reorder; a repeated id a duplicate; a missing id a gap. A publication instant running backwards
    along the span is a reorder too.
    """

    start = time_ns - _WINDOW_NS
    anchors = [index for index, item in enumerate(records) if item.publication_time_ns <= start]
    if not anchors:
        return "window_start_not_observed"
    position = max(anchors, key=lambda index: records[index].sequence_id)  # max() keeps the first on a tie
    first = records[position].sequence_id
    span = [item for index, item in enumerate(records) if index >= position or item.publication_time_ns > start]
    identifiers = [item.sequence_id for item in span]
    if min(identifiers) < first:
        return "sequence_reordered_in_the_window"
    if len(set(identifiers)) != len(identifiers):
        return "sequence_duplicate_in_the_window"
    if max(identifiers) != first + len(identifiers) - 1:  # distinct ids from ``first``: contiguous iff this holds
        return "sequence_gap_in_the_window"
    if identifiers != list(range(first, first + len(identifiers))):  # received out of sequence order
        return "sequence_reordered_in_the_window"
    if any(
        later.publication_time_ns < earlier.publication_time_ns for earlier, later in zip(span, span[1:], strict=False)
    ):
        return "sequence_reordered_in_the_window"
    if heartbeat_interval_ns is not None:
        instants = [*(item.publication_time_ns for item in span), time_ns]
        if any(later - earlier > heartbeat_interval_ns for earlier, later in zip(instants, instants[1:], strict=False)):
            return "heartbeat_coverage_gap_in_the_window"
    return ""


def governed_paper_ctr_reading(
    context: GovernedPaperCtrSourceContext | None, *, instrument: str, time_ns: int
) -> GovernedPaperCtrReading:
    """The CTR reading of the source ``context`` at ``time_ns`` (see the module docstring). Pure.

    ``context`` must be canonical (``governed_paper_ctr_canonical_context``) or None, for no source at all.
    """

    if not historical_execution_wire_int_is_valid(time_ns, minimum=0):
        raise _fail("time_ns_invalid")
    if context is None:
        return _unavailable(time_ns, "no_ctr_source_supplied")
    context = governed_paper_ctr_canonical_context(context, instrument=instrument)
    qualification, capture = context.qualification, context.capture
    admission = governed_paper_ctr_admission(governed_paper_ctr_active_table(), qualification)
    if admission:
        return _unavailable(time_ns, admission)
    if not qualification.processing_by_this_system_permitted or (
        GOVERNED_PAPER_CTR_REQUIRED_USE not in qualification.permitted_uses
    ):
        return _unavailable(time_ns, "source_rights_do_not_permit_this_use")
    if qualification.approval_time_ns > time_ns:
        return _unavailable(time_ns, "qualification_not_yet_approved_at_the_reading_instant")
    ended = [item for item in context.revocations if item.effective_from_ns <= time_ns]
    if ended:
        return _unavailable(time_ns, f"qualification_{ended[0].kind.value.lower()}_at_the_reading_instant")
    if capture.complete_through_receipt_ns < time_ns:
        return _unavailable(time_ns, "capture_not_complete_at_the_reading_instant")
    received = [item for item in capture.records if item.receipt_time_ns <= time_ns]  # the capture's receipt order
    reason = _coverage(received, time_ns=time_ns, heartbeat_interval_ns=qualification.heartbeat_max_interval_ns)
    if reason:
        return _unavailable(time_ns, reason)
    start = time_ns - _WINDOW_NS
    window = [item for item in received if start < item.publication_time_ns <= time_ns]
    if qualification.source_class is GovernedPaperCtrSourceClass.ORDER_LEVEL_EVENTS:
        cancels = sum(1 for item in window if item.kind in _CANCELS[qualification.cancel_definition])
        trades = sum(1 for item in window if item.kind is GovernedPaperCtrRecordKind.TRADE)
    else:
        intervals = sorted(
            (
                item
                for item in received
                if item.kind is GovernedPaperCtrRecordKind.PUBLISHED_COUNTS
                and item.interval_start_ns >= start  # type: ignore[operator]
                and item.interval_end_ns <= time_ns  # type: ignore[operator]
            ),
            key=lambda item: item.interval_start_ns,  # type: ignore[arg-type,return-value]
        )
        edges = [
            start,
            *(edge for item in intervals for edge in (item.interval_start_ns, item.interval_end_ns)),
            time_ns,
        ]
        if not intervals or any(edges[index] != edges[index + 1] for index in range(0, len(edges), 2)):
            return _unavailable(time_ns, "published_counts_do_not_tile_the_window")
        cancels = sum(item.cancel_count for item in intervals)  # type: ignore[misc]
        trades = sum(item.trade_count for item in intervals)  # type: ignore[misc]
    if trades == 0:
        return _unavailable(time_ns, "zero_trades_in_the_window_ctr_undefined")
    ctr = Fraction(cancels, trades)
    alpha = (
        Fraction(1)
        if ctr <= GOVERNED_PAPER_CTR_THRESHOLD
        else 1 / (1 + GOVERNED_PAPER_CTR_SLOPE * (ctr - GOVERNED_PAPER_CTR_THRESHOLD))
    )
    return GovernedPaperCtrReading(
        time_ns, True, "qualified_covered_reading", cancels, trades, _rational(ctr), _rational(alpha)
    )


# --- the visible depth -------------------------------------------------------------------------------------------------


def _side_depth(
    levels: tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]], side: HistoricalExecutionSide
) -> tuple[Fraction | None, bool, str]:
    """``(depth, exact, reason)`` of one parsed tip on the side ``side`` consumes, within 5 bps of the mid."""

    bids, asks = levels
    bid, ask = bids[0][0], asks[0][0]
    if bid >= ask:
        return None, False, "order_book_crossed"
    total = bid + ask  # twice the mid
    if side is HistoricalExecutionSide.BUY:
        edge = (1 + GOVERNED_PAPER_CTR_DEPTH_BAND) * total  # twice the band's upper edge
        units = sum(quantity for price, quantity in asks if 2 * price <= edge)
        exact = 2 * asks[-1][0] > edge
    else:
        edge = (1 - GOVERNED_PAPER_CTR_DEPTH_BAND) * total  # twice the band's lower edge
        units = sum(quantity for price, quantity in bids if 2 * price >= edge)
        exact = 2 * bids[-1][0] < edge
    return Fraction(units, _UNIT), exact, "" if exact else "depth_50_tip_does_not_cover_the_5bps_band_lower_bound_only"


class GovernedPaperDepthIndex:
    """The visible-depth readings of one dataset's authenticated ORDER_BOOK depth-50 series of one instrument.

    The whole dataset is re-proven before any book is indexed: ``verify_historical_pit_dataset`` (exact schema and strict
    parse, the EF-3 manifest re-proof, every record re-digested, the record set and the dataset digest through the one
    canonical reassembly) must find it intact, and it must be READY and advancing. Otherwise ``GovernedPaperCtrError`` is
    raised and no index exists over it, so no depth or cap is ever read from it. ``dataset_digest`` is the digest of
    the verified dataset. The class is final: a subclass could skip the verification.
    """

    def __init_subclass__(cls, **kwargs: object) -> None:
        raise TypeError(_reason("depth_index_is_final"))

    def __init__(self, dataset: HistoricalPitDataset, *, instrument: str) -> None:
        if type(dataset) is not HistoricalPitDataset or type(instrument) is not str or not instrument:
            raise _fail("depth_inputs_malformed")
        verification = verify_historical_pit_dataset(dataset)
        if not verification.intact or dataset.status is not EdgeEvidenceStatus.READY or dataset.advances is not True:
            raise _fail("depth_dataset_not_authentic")
        self.dataset_digest = verification.recomputed_digest
        try:
            self.reason, series = governed_paper_order_book_series(dataset, instrument)
        except GovernedPaperRegimeError as exc:
            raise _fail("depth_dataset_manifest_not_authentic") from exc
        books: list[tuple[int, int, int, HistoricalPitRecord]] = []
        if not self.reason:
            for record in dataset.records:
                if record.series_id != series or record.instrument != instrument or record.finalized_at_ns is None:
                    continue
                visible = max(record.available_at_ns, record.finalized_at_ns)
                books.append((visible, record.event_time_ns, record.sequence_id, record))
        books.sort(key=lambda item: (item[0], item[1], item[2]))
        self._books = books
        self._visible = [item[0] for item in books]
        self._by_digest = {item[3].record_digest: item[3] for item in books}
        self._parsed: dict[str, tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]] | None] = {}

    def _levels(self, record: HistoricalPitRecord):  # noqa: ANN202
        digest = record.record_digest
        if digest not in self._parsed:
            self._parsed[digest] = governed_paper_order_book_levels(record)
        return self._parsed[digest]

    def _reading(self, record: HistoricalPitRecord, side: HistoricalExecutionSide) -> GovernedPaperVisibleDepth:
        levels = self._levels(record)
        if levels is None:
            return GovernedPaperVisibleDepth(side, record.record_digest, None, False, "order_book_tip_malformed")
        depth, exact, reason = _side_depth(levels, side)
        return GovernedPaperVisibleDepth(
            side, record.record_digest, None if depth is None else _rational(depth), exact, reason
        )

    def at(self, time_ns: int, side: HistoricalExecutionSide) -> GovernedPaperVisibleDepth:
        """The decision-time depth at ``time_ns``: the latest tip visible then by native event time, fresh within 10 s."""

        if self.reason:
            return GovernedPaperVisibleDepth(side, None, None, False, self.reason)
        count = bisect.bisect_right(self._visible, time_ns)
        if count == 0:
            return GovernedPaperVisibleDepth(side, None, None, False, "no_order_book_tip_visible_at_the_instant")
        latest = max(self._books[:count], key=lambda item: (item[1], item[2]))
        if time_ns - latest[1] > _BOOK_FRESHNESS_NS:
            return GovernedPaperVisibleDepth(
                side, latest[3].record_digest, None, False, "order_book_tip_older_than_10s"
            )
        return self._reading(latest[3], side)

    def of_record(self, book_record_digest: str, side: HistoricalExecutionSide) -> GovernedPaperVisibleDepth:
        """The depth of one book record of the series (the record a fill executes against)."""

        record = self._by_digest.get(book_record_digest)
        if record is None:
            return GovernedPaperVisibleDepth(side, book_record_digest, None, False, "book_record_not_in_the_series")
        return self._reading(record, side)

    def records_visible_between(self, first_ns: int, last_ns: int) -> tuple[HistoricalPitRecord, ...]:
        """Every series record visible in ``[first_ns, last_ns]``, in visibility order."""

        low = bisect.bisect_left(self._visible, first_ns)
        high = bisect.bisect_right(self._visible, last_ns)
        return tuple(item[3] for item in self._books[low:high])

    def visibility_of(self, book_record_digest: str) -> int | None:
        record = self._by_digest.get(book_record_digest)
        return None if record is None else max(record.available_at_ns, record.finalized_at_ns)  # type: ignore[type-var]


def evaluate_governed_paper_ctr_depth(
    *,
    quantity: Fraction | None,
    depth: GovernedPaperVisibleDepth,
    ctr: GovernedPaperCtrReading,
) -> GovernedPaperCtrDepth:
    """The §5 depth-cap status of an order of ``quantity`` against ``depth`` with the reading ``ctr``. Pure."""

    if quantity is not None and (type(quantity) is not Fraction or quantity <= 0):
        raise _fail("depth_inputs_malformed:quantity")
    if type(depth) is not GovernedPaperVisibleDepth or type(ctr) is not GovernedPaperCtrReading:
        raise _fail("depth_inputs_malformed")
    blocked = GovernedPaperCtrDepthStatus.BLOCKED
    if quantity is None:
        return GovernedPaperCtrDepth(blocked, "", "order_quantity_unavailable")
    if depth.depth is None:
        return GovernedPaperCtrDepth(blocked, "", f"visible_depth_unavailable:{depth.reason}")
    visible = Fraction(depth.depth)
    if visible <= 0:
        observed = ""
        if depth.exact:
            return GovernedPaperCtrDepth(
                GovernedPaperCtrDepthStatus.FAIL, observed, "order_at_or_above_2pct_of_the_unadjusted_visible_depth"
            )
        return GovernedPaperCtrDepth(blocked, observed, "visible_depth_lower_bound_zero")
    observed = historical_execution_render_amount(quantity / visible) or ""
    if depth.exact and quantity >= GOVERNED_PAPER_CTR_DEPTH_FRACTION * visible:
        return GovernedPaperCtrDepth(
            GovernedPaperCtrDepthStatus.FAIL, observed, "order_at_or_above_2pct_of_the_unadjusted_visible_depth"
        )
    if not ctr.available or ctr.alpha is None:
        return GovernedPaperCtrDepth(blocked, observed, f"ctr_unavailable:{ctr.reason}")
    if quantity < GOVERNED_PAPER_CTR_DEPTH_FRACTION * Fraction(ctr.alpha) * visible:
        return GovernedPaperCtrDepth(
            GovernedPaperCtrDepthStatus.PASS, observed, "order_below_2pct_of_the_ctr_adjusted_visible_depth"
        )
    return GovernedPaperCtrDepth(blocked, observed, "order_not_below_2pct_of_the_ctr_adjusted_visible_depth")


def governed_paper_ctr_depth_cap(depth: GovernedPaperVisibleDepth, ctr: GovernedPaperCtrReading) -> Fraction | None:
    """The exact order-quantity cap ``0.02 alpha D`` an order must stay strictly below, or None when unproven. Pure."""

    if depth.depth is None or not ctr.available or ctr.alpha is None:
        return None
    return GOVERNED_PAPER_CTR_DEPTH_FRACTION * Fraction(ctr.alpha) * Fraction(depth.depth)


def governed_paper_ctr_capture_to_dict(capture: GovernedPaperCtrSourceCapture) -> dict[str, object]:
    return _to_payload(capture)


def governed_paper_ctr_qualification_to_dict(qualification: GovernedPaperCtrSourceQualification) -> dict[str, object]:
    return _to_payload(qualification)


__all__ = [
    "GOVERNED_PAPER_CTR_CAPTURE_SCHEMA",
    "GOVERNED_PAPER_CTR_CONTRACT_ID",
    "GOVERNED_PAPER_CTR_DEPTH_BAND",
    "GOVERNED_PAPER_CTR_DEPTH_FRACTION",
    "GOVERNED_PAPER_CTR_NON_CLAIM_FLAGS",
    "GOVERNED_PAPER_CTR_PRODUCTION_APPROVAL_TABLE",
    "GOVERNED_PAPER_CTR_QUALIFICATION_SCHEMA",
    "GOVERNED_PAPER_CTR_REQUIRED_USE",
    "GOVERNED_PAPER_CTR_REVOCATION_SCHEMA",
    "GOVERNED_PAPER_CTR_SLOPE",
    "GOVERNED_PAPER_CTR_THRESHOLD",
    "GovernedPaperCtrApprovalKind",
    "GovernedPaperCtrApprovalTable",
    "GovernedPaperCtrCancelDefinition",
    "GovernedPaperCtrCoverageMethod",
    "GovernedPaperCtrDepth",
    "GovernedPaperCtrDepthStatus",
    "GovernedPaperCtrError",
    "GovernedPaperCtrQualificationRevocation",
    "GovernedPaperCtrReading",
    "GovernedPaperCtrRecordKind",
    "GovernedPaperCtrRevocationKind",
    "GovernedPaperCtrSourceCapture",
    "GovernedPaperCtrSourceClass",
    "GovernedPaperCtrSourceContext",
    "GovernedPaperCtrSourceQualification",
    "GovernedPaperCtrSourceRecord",
    "GovernedPaperCtrTradeDefinition",
    "GovernedPaperDepthIndex",
    "GovernedPaperVisibleDepth",
    "build_governed_paper_ctr_qualification_revocation",
    "build_governed_paper_ctr_source_capture",
    "build_governed_paper_ctr_source_qualification",
    "evaluate_governed_paper_ctr_depth",
    "governed_paper_ctr_active_table",
    "governed_paper_ctr_admission",
    "governed_paper_ctr_canonical_context",
    "governed_paper_ctr_capture_to_dict",
    "governed_paper_ctr_depth_cap",
    "governed_paper_ctr_qualification_to_dict",
    "governed_paper_ctr_reading",
    "verify_governed_paper_ctr_qualification_revocation",
    "verify_governed_paper_ctr_source_capture",
    "verify_governed_paper_ctr_source_qualification",
]
