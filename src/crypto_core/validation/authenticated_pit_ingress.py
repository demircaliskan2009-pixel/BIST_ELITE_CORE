"""Authenticated observed-market point-in-time ingress (FREE_FIRST_AUTHENTICATED_PIT_INGRESS_V2).

Maps one offline, source-neutral capture of native crypto market observations (order-book snapshots and diff deltas,
mark prices and final funding settlements) onto the accepted point-in-time authorities: the authenticated EF-3
``EdgeSourcePacketEvidence`` series semantics and a ``HistoricalPitDataset`` built through its public builders only.
The module never fetches, schedules or reads a clock. A synthetic capture proves construction only, never a real
market observation or real paper evidence.

Native order-book knowledge model (``update_span_chain_absolute_levels.v1``: documented, not qualified for any
provider):

* Observations. Within one declared stream scope (source, stream, instrument, native epoch) a delta is identified by
  its final update id ``u``; it spans the native ids ``(pu, u]`` with ``pu < U <= u`` (``U`` its first update id and
  ``pu`` the final id of its predecessor) and asserts the absolute quantity of every listed level as of ``u`` (zero
  means absent). A snapshot asserts the complete best levels of each side as of its last update id ``L``. Listed
  levels are present, and every other price between the best side and the deepest listed price is known absent.
  Every price beyond that horizon is UNKNOWN, never empty.
* Same-identity truth. One final id carries exactly one delta; a content-identical redelivery is a replay with no
  effect, and any other content under that id rejects the capture. Every pair of observations about the same native
  id (snapshot with snapshot, snapshot with delta) must agree wherever both carry knowledge, whatever the arrival order
  or transport session. The knowledge of each native id is kept as the union of every agreeing snapshot observed
  there, so a later, narrower snapshot never replaces broader knowledge.
* Native chains. Deltas join the stream chain in arrival order. A delta whose ``pu`` equals the current tip extends
  the chain. A delta whose ``pu`` lies beyond the tip opens a new chain after a native sequence gap. Any other
  non-replay delta is a sequence regression and rejects the capture. Transport sessions carry no native truth: a
  reconnect that loses no update continues the chain, and one that loses updates is a native gap.
* Knowledge. Inside one chain, the quantity of a price is a step function of native id that changes only where a delta
  lists that price. Every snapshot whose ``L`` lies in the chain span is projected onto those steps. Its value for a
  price is unconstrained only at an id strictly inside the span of a delta that lists that price. Knowledge therefore
  accumulates, forward and backward, across narrower, wider and repeated snapshots and is never replaced, and any two
  facts on one step must agree. Applying a delta is transactional: every conflict is decided before any state is
  published.
* Emission. Only the tip of the newest chain is ever emitted, at most once, and only at the first moment its best
  ``order_book_depth`` levels of both sides are exactly known. Exactly known means every price from the best level to
  the depth-th level lies inside the deepest snapshot coverage projected onto the tip. Availability and finality are
  that moment (the receipt that completed the knowledge); event time is the native event time of the tip delta. A
  crossed tip, an invalid level, a receipt before its event time or any contradiction rejects the whole capture before
  a dataset exists.

Marks are identified by native event time, one value per event time. A final funding settlement is identified by its
settlement time: event time is the window open (settlement minus the declared governed interval), availability is the
observed publication receipt (never before the settlement), finality is the settlement, and the PIT sequence id is the
governed cycle ordinal ``settlement // interval``. Settlements must be spaced by exactly the declared interval.

Trades and index prices (``S1_MARKET_DATA_INTEGRITY_NATIVE_MEASUREMENT_CLOSURE_V1``, evidence schema v2). A capture that
declares a ``last_trade`` or ``index_price`` stream binds it to the registered LAST_TRADE or INDEX_PRICE series with
their unchanged EF-3 semantics (registry 1.0: no sequence policy for either), and its evidence is
``authenticated-pit-ingress.v2``; a capture without one keeps the v1 evidence exactly.

* A trade is identified by its native trade id. Its record is that id as the PIT sequence id, its native event time,
  availability at its receipt (never before the event), finality at its event, and its exact price and base-asset
  quantity, both positive. One id carries exactly one trade: a content-identical redelivery is a replay with no effect,
  any other content under that id rejects the capture.
* Registry 1.0 declares no trade sequence policy, so no continuity is ever inferred. A trade stream may DECLARE the
  native continuity profile ``contiguous_trade_id.v1``: within its native epoch the source numbers consecutive trades
  by consecutive ids in non-decreasing event time. Under it a new trade id never regresses below the newest one, nor
  does its event time; a jump above the newest id is a native gap that opens a new contiguous run, and every trade
  record names the first id of its run (``trade_run_first_id``), which is fixed at its receipt. Without the profile no
  run is named and no gap is claimed.
* An index price is identified by its native event time, one positive value per event time, observed no earlier than
  that event and final at it, exactly like a mark. An index stream may DECLARE the native publication profile
  ``index_one_per_utc_second.v1``: the source publishes at most one index value per UTC second. Under it a second value
  inside one UTC second rejects the capture and every record names its UTC second (``index_utc_second_slot``).

A declared profile is documented, never qualified for any provider: the verdict keeps
``native_continuity_profile_unqualified`` open, and a capture never proves that a provider supplied complete history.

The evidence binds the source declaration (rights and source object identity), the exact canonical capture digest, the
EF-3 and registry anchors, every stream-to-series lineage and the output dataset digest. Status is integrity only. The
verdict always carries the open external facts (provider continuity qualification, rights, historical coverage and the
funding finality source), so the evidence never advances. Every real-market, real-paper, readiness and Stage-4 claim
stays structurally False. One assembly path serves the builder and the total verifier.
"""

from __future__ import annotations

import bisect
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, fields, is_dataclass, replace
from enum import Enum

from crypto_core.data.requirements import DataRequirementKey
from crypto_core.strategy.source_packet import SourcePacketRightsStatus
from crypto_core.validation.edge_artifact_core import (
    EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    EdgeArtifactError,
    EdgeEvidenceStatus,
    EdgeEvidenceVerification,
    EdgeGateVerdict,
    edge_canonical_json,
    edge_is_hex64,
    edge_payload_digest,
    edge_scope_violation,
    edge_sha256_text,
    resolve_edge_gate_verdict,
    verify_edge_artifact_total,
)
from crypto_core.validation.edge_source_packet_evidence import (
    EdgeSourcePacketEvidence,
    EdgeSourceSeriesRecord,
    verify_edge_source_packet_evidence,
)
from crypto_core.validation.historical_execution_economics_policy import (
    BEST_ASK_PRICE_NAME,
    BEST_ASK_QUANTITY_NAME,
    BEST_BID_PRICE_NAME,
    BEST_BID_QUANTITY_NAME,
    FUNDING_VALUE_NAME,
    MARK_VALUE_NAME,
)
from crypto_core.validation.historical_pit_dataset import (
    HistoricalPitDataset,
    HistoricalPitDatasetError,
    HistoricalPitRecord,
    HistoricalPitValue,
    build_historical_pit_dataset,
    build_historical_pit_record,
    is_canonical_pit_decimal,
)

_SCHEMA_VERSION = "authenticated-pit-ingress.v1"
_MARKET_SCHEMA_VERSION = "authenticated-pit-ingress.v2"
_REASON_PREFIX = "authenticated_pit_ingress"
_SELF_DIGEST_FIELD = "ingress_digest"
_MAX_WIRE_INT = 9223372036854775807
_INSTRUMENT_EXTRA_CHARS = frozenset("-_./:")
_PROFILE_QUALIFICATION = "documented_not_qualified"
_FINALIZED_ONLY = "finalized_only"
_IMMUTABLE_AFTER_FINALIZATION = "immutable_after_finalization"
_BID = 0
_ASK = 1
_BASE_STEP = -1
_UNCONSTRAINED = -2

# Registry-derived EF-3 semantics this ingress implements, field by field. A bound series that differs is refused,
# never adapted: the order book stays L2 / depth 50 / strict monotonic / snapshot_then_delta / sequence_gap_reject.
_REGISTRY_SEMANTICS: dict[DataRequirementKey, tuple[tuple[str, object], ...]] = {
    DataRequirementKey.ORDER_BOOK: (
        ("historical_source", "order_book_snapshot_delta_v1"),
        ("event_time_policy", "book_event_ns"),
        ("available_at_policy", "book_available_ns"),
        ("finalized_at_policy", "book_sequence_finalized_ns"),
        ("order_book_level", "l2"),
        ("order_book_depth", 50),
        ("sequence_policy", "strict_monotonic"),
        ("resync_policy", "snapshot_then_delta"),
        ("finality_policy", "sequence_gap_reject"),
    ),
    DataRequirementKey.MARK_PRICE: (
        ("historical_source", "mark_price_history_v1"),
        ("event_time_policy", "mark_event_ns"),
        ("available_at_policy", "mark_available_ns"),
        ("finalized_at_policy", "mark_finalized_ns"),
        ("price_semantics", "mark_price"),
        ("finality_policy", "mark_snapshot_final"),
    ),
    DataRequirementKey.FUNDING_RATE: (
        ("historical_source", "funding_history_v1"),
        ("event_time_policy", "funding_window_open_ns"),
        ("available_at_policy", "funding_published_ns"),
        ("finalized_at_policy", "funding_finalized_ns"),
        ("funding_semantics", "final"),
        ("finality_policy", "funding_cycle_closed"),
    ),
    # Registry 1.0 exactly: no sequence policy, so a trade or index continuity is only ever a declared capture profile.
    DataRequirementKey.LAST_TRADE: (
        ("historical_source", "trade_history_v1"),
        ("event_time_policy", "trade_event_ns"),
        ("available_at_policy", "trade_available_ns"),
        ("finalized_at_policy", "trade_finalized_ns"),
        ("price_semantics", "last_trade"),
        ("sequence_policy", None),
        ("finality_policy", "trade_tick_final"),
    ),
    DataRequirementKey.INDEX_PRICE: (
        ("historical_source", "index_price_history_v1"),
        ("event_time_policy", "index_event_ns"),
        ("available_at_policy", "index_available_ns"),
        ("finalized_at_policy", "index_finalized_ns"),
        ("price_semantics", "index_price"),
        ("sequence_policy", None),
        ("finality_policy", "index_snapshot_final"),
    ),
}
_BOOK_DEPTH = 50
_NS_PER_SECOND = 1_000_000_000
_UNIT = 10**18  # one whole unit at the canonical scale 18

# The record value names of the trade and index-price series (their only producer and the entry gate share them).
TRADE_PRICE_VALUE_NAME = "trade_price"
TRADE_QUANTITY_VALUE_NAME = "trade_quantity"
TRADE_RUN_FIRST_ID_VALUE_NAME = "trade_run_first_id"
INDEX_PRICE_VALUE_NAME = "index_price"
INDEX_UTC_SECOND_SLOT_VALUE_NAME = "index_utc_second_slot"

# The open M1 source gate: facts no capture can prove about itself, so the evidence never advances.
_EXTERNAL_FACT_REASONS = (
    "native_continuity_profile_unqualified",
    "source_rights_unverified",
    "historical_coverage_unknown",
    "funding_finality_source_unproven",
)

AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS: tuple[tuple[str, bool], ...] = (
    *EDGE_STRUCTURAL_NON_CLAIM_FLAGS,
    ("source_qualified", False),
    ("native_provider_qualified", False),
    ("source_rights_verified", False),
    ("historical_coverage_proven", False),
    ("funding_finality_source_proven", False),
    ("real_market_observation_proven", False),
    ("real_paper_observed", False),
    ("stage4_evidence_available", False),
    ("external_archive_truth_proven", False),
    ("orders_created", False),
    ("fills_simulated", False),
    ("pnl_computed", False),
    ("performance_metrics_computed", False),
)
_FLAG_NAMES = frozenset(name for name, _ in AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS)


class AuthenticatedPitIngressError(EdgeArtifactError):
    """Raised on malformed caller input, an unsupported declaration or a forbidden scope token."""


class NativeBookContinuityProfile(str, Enum):
    """Declared native semantics of an order-book stream. Unknown semantics are refused, never guessed."""

    UPDATE_SPAN_CHAIN_ABSOLUTE_LEVELS_V1 = "update_span_chain_absolute_levels.v1"


class NativeTradeContinuityProfile(str, Enum):
    """Optional declared native continuity of a trade stream. Unknown semantics are refused, never guessed."""

    CONTIGUOUS_TRADE_ID_V1 = "contiguous_trade_id.v1"


class NativeIndexPublicationProfile(str, Enum):
    """Optional declared native publication model of an index-price stream. Unknown semantics are refused."""

    ONE_PER_UTC_SECOND_V1 = "index_one_per_utc_second.v1"


# --- capture (caller input) ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CapturedLevel:
    """One native price level: canonical scale-18 price and quantity text exactly as captured."""

    price: str
    quantity: str


@dataclass(frozen=True)
class CapturedBookSnapshot:
    """A native order-book snapshot: the best levels of each side as of ``last_update_id``."""

    stream_id: str
    last_update_id: int
    receipt_ns: int
    bids: tuple[CapturedLevel, ...]
    asks: tuple[CapturedLevel, ...]


@dataclass(frozen=True)
class CapturedBookDelta:
    """A native diff event spanning ``(previous_final_update_id, final_update_id]`` with absolute level quantities."""

    stream_id: str
    first_update_id: int
    final_update_id: int
    previous_final_update_id: int
    event_time_ns: int
    receipt_ns: int
    bids: tuple[CapturedLevel, ...]
    asks: tuple[CapturedLevel, ...]


@dataclass(frozen=True)
class CapturedMarkPrice:
    """A native mark-price observation identified by its native event time."""

    stream_id: str
    event_time_ns: int
    receipt_ns: int
    mark_price: str


@dataclass(frozen=True)
class CapturedFundingSettlement:
    """A final funding settlement identified by its native settlement time, observed at ``receipt_ns``."""

    stream_id: str
    funding_time_ns: int
    receipt_ns: int
    funding_rate: str


@dataclass(frozen=True)
class CapturedTrade:
    """A native trade identified by its native trade id: event time, price and base-asset quantity as captured."""

    stream_id: str
    trade_id: int
    event_time_ns: int
    receipt_ns: int
    price: str
    quantity: str


@dataclass(frozen=True)
class CapturedIndexPrice:
    """A native index-price observation identified by its native event time."""

    stream_id: str
    event_time_ns: int
    receipt_ns: int
    index_price: str


@dataclass(frozen=True)
class CaptureStreamDeclaration:
    """One captured stream: its native scope, its EF-3 series lineage and its declared native semantics.

    ``continuity_profile`` is required for an order-book stream, optional for a trade stream (its continuity) and an
    index-price stream (its publication model), and absent for every other stream.
    """

    stream_id: str
    data_requirement_key: DataRequirementKey | str
    instrument: str
    series_id: str
    source_reference: str
    native_epoch_id: str
    continuity_profile: (
        NativeBookContinuityProfile | NativeTradeContinuityProfile | NativeIndexPublicationProfile | str | None
    )
    funding_interval_ns: int | None


@dataclass(frozen=True)
class CaptureDeclaration:
    """The source declaration of one capture: identity, rights and the declared streams."""

    capture_id: str
    source_id: str
    source_reference: str
    source_object_id: str
    source_object_digest: str
    rights_status: SourcePacketRightsStatus | str
    rights_reference: str
    streams: tuple[CaptureStreamDeclaration, ...]


@dataclass(frozen=True)
class AuthenticatedPitIngressInputs:
    """Everything one ingress consumes: the capture, its declaration and the accepted upstream anchors."""

    ingress_id: str
    correlation_id: str
    dataset_id: str
    source_manifest: EdgeSourcePacketEvidence
    expected_source_manifest_digest: str
    expected_data_requirement_registry_digest: str
    declaration: CaptureDeclaration
    observations: tuple[object, ...]


# --- evidence --------------------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthenticatedPitStreamSummary:
    """Deterministic per-stream account of one ingress: lineage, counts and the emitted native identity range."""

    stream_id: str
    data_requirement_key: str
    instrument: str
    series_id: str
    source_reference: str
    native_epoch_id: str
    continuity_profile: str | None
    funding_interval_ns: int | None
    observation_count: int
    replay_count: int
    native_chain_count: int
    attached_snapshot_count: int
    unattached_snapshot_count: int
    record_count: int
    first_record_sequence_id: int | None
    last_record_sequence_id: int | None


@dataclass(frozen=True)
class AuthenticatedPitIngressEvidence:
    """Immutable, digest-bound ingress evidence. Never advances: the source itself is not qualified."""

    schema_version: str
    status: EdgeEvidenceStatus
    gate_verdict: EdgeGateVerdict
    advances: bool
    ingress_id: str
    correlation_id: str
    dataset_id: str
    capture_id: str
    source_id: str
    source_reference: str
    source_object_id: str
    source_object_digest: str
    rights_status: str
    rights_reference: str
    source_manifest_digest: str
    data_requirement_registry_digest: str
    continuity_profile_qualification: str
    book_record_depth: int
    streams: tuple[AuthenticatedPitStreamSummary, ...]
    observation_count: int
    capture_digest: str
    dataset_digest: str
    record_count: int
    integrity_reason_codes: tuple[str, ...]
    verdict_reason_codes: tuple[str, ...]
    ingress_digest: str
    paper_only: bool = True
    edge_proven: bool = False
    profitability_proven: bool = False
    candidate_admitted_to_paper: bool = False
    preregistration_sealed: bool = False
    kill_criteria_sealed: bool = False
    performance_data_consumed: bool = False
    oos_evidence_consumed: bool = False
    regime_evidence_available: bool = False
    current_venue_facts_consumed: bool = False
    operational_readiness: bool = False
    live_ready: bool = False
    shadow_ready: bool = False
    deribit_ready: bool = False
    private_api_ready: bool = False
    live_api_called: bool = False
    connector_invoked: bool = False
    real_orders_enabled: bool = False
    real_money_enabled: bool = False
    real_capital_reserved: bool = False
    scheduler_enabled: bool = False
    auto_loop_enabled: bool = False
    source_qualified: bool = False
    native_provider_qualified: bool = False
    source_rights_verified: bool = False
    historical_coverage_proven: bool = False
    funding_finality_source_proven: bool = False
    real_market_observation_proven: bool = False
    real_paper_observed: bool = False
    stage4_evidence_available: bool = False
    external_archive_truth_proven: bool = False
    orders_created: bool = False
    fills_simulated: bool = False
    pnl_computed: bool = False
    performance_metrics_computed: bool = False


@dataclass(frozen=True)
class AuthenticatedPitIngressResult:
    """The ingress evidence and, exactly when it is READY, the PIT dataset built from the capture."""

    evidence: AuthenticatedPitIngressEvidence
    dataset: HistoricalPitDataset | None


# --- strict helpers --------------------------------------------------------------------------------------------------


class _Violation(Exception):
    """A capture fact that rejects the whole capture; ``code`` is its reason without the module prefix."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def _reason(code: str) -> str:
    return f"{_REASON_PREFIX}:{code}"


def _fail(code: str) -> AuthenticatedPitIngressError:
    return AuthenticatedPitIngressError(_reason(code))


def _sorted_unique(reasons: Sequence[str]) -> tuple[str, ...]:
    return tuple(sorted(set(reasons)))


def _require_text(value: object, field_name: str) -> str:
    if (
        type(value) is not str
        or value == ""
        or value != value.strip()
        or any(ord(char) < 32 or ord(char) == 127 for char in value)
    ):
        raise _fail(f"{field_name}_invalid")
    violation = edge_scope_violation(value)
    if violation is not None:
        raise _fail(f"{violation}:{field_name}")
    return value


def _require_token(value: object, field_name: str) -> str:
    if type(value) is not str or not value or len(value) > 128 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail(f"{field_name}_invalid")
    if any(not (char.isascii() and (char.islower() or char.isdigit() or char in "_.:-")) for char in value):
        raise _fail(f"{field_name}_invalid")
    return _require_text(value, field_name)


def _require_instrument(value: object) -> str:
    if type(value) is not str or not value or len(value) > 64 or not (value[0].isascii() and value[0].isalnum()):
        raise _fail("stream_instrument_invalid")
    if any(not (char.isascii() and (char.isalnum() or char in _INSTRUMENT_EXTRA_CHARS)) for char in value):
        raise _fail("stream_instrument_invalid")
    return _require_text(value, "stream_instrument")


def _require_nonnegative_int(value: object, field_name: str) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_positive_int(value: object, field_name: str) -> int:
    if type(value) is not int or value <= 0 or value > _MAX_WIRE_INT:
        raise _fail(f"{field_name}_invalid")
    return value


def _require_decimal(value: object, field_name: str) -> str:
    if not is_canonical_pit_decimal(value):
        raise _fail(f"{field_name}_noncanonical")
    return value  # type: ignore[return-value]


def _require_hex64(value: object, field_name: str) -> str:
    if not edge_is_hex64(value):
        raise _fail(f"{field_name}_invalid")
    return value  # type: ignore[return-value]


def _require_member(value: object, enum_cls: type[Enum], field_name: str) -> Enum:
    if type(value) is enum_cls:
        return value  # type: ignore[return-value]
    if type(value) is str:
        try:
            return enum_cls(value)
        except ValueError as exc:
            raise _fail(f"{field_name}_invalid") from exc
    raise _fail(f"{field_name}_invalid")


def _scaled(text: str) -> int:
    """Exact scale-18 integer of a canonical decimal text (the grammar guarantees one dot and 18 fraction digits)."""

    return int(text.replace(".", ""))


def _render(value: int) -> str:
    """Canonical scale-18 text of an exact scaled integer; the exact inverse of ``_scaled``."""

    digits = str(abs(value)).rjust(19, "0")
    return ("-" if value < 0 else "") + digits[:-18] + "." + digits[-18:]


def _serialize(value: object) -> object:
    if is_dataclass(value) and not isinstance(value, type):
        return _to_payload(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list)):
        return [_serialize(item) for item in value]
    return value


def _to_payload(artifact: object) -> dict[str, object]:
    return {field.name: _serialize(getattr(artifact, field.name)) for field in fields(artifact)}  # type: ignore[arg-type]


# --- canonical capture -----------------------------------------------------------------------------------------------

_SUPPORTED_KEYS = (
    DataRequirementKey.ORDER_BOOK,
    DataRequirementKey.MARK_PRICE,
    DataRequirementKey.FUNDING_RATE,
    DataRequirementKey.LAST_TRADE,
    DataRequirementKey.INDEX_PRICE,
)
_MARKET_KEYS = (DataRequirementKey.LAST_TRADE, DataRequirementKey.INDEX_PRICE)
_OBSERVATION_KINDS: dict[type, tuple[str, DataRequirementKey]] = {
    CapturedBookSnapshot: ("book_snapshot", DataRequirementKey.ORDER_BOOK),
    CapturedBookDelta: ("book_delta", DataRequirementKey.ORDER_BOOK),
    CapturedMarkPrice: ("mark_price", DataRequirementKey.MARK_PRICE),
    CapturedFundingSettlement: ("funding_settlement", DataRequirementKey.FUNDING_RATE),
    CapturedTrade: ("trade", DataRequirementKey.LAST_TRADE),
    CapturedIndexPrice: ("index_price", DataRequirementKey.INDEX_PRICE),
}
_OPTIONAL_PROFILES: dict[DataRequirementKey, type[Enum]] = {
    DataRequirementKey.LAST_TRADE: NativeTradeContinuityProfile,
    DataRequirementKey.INDEX_PRICE: NativeIndexPublicationProfile,
}


def _canonical_stream(item: object) -> CaptureStreamDeclaration:
    if type(item) is not CaptureStreamDeclaration:
        raise _fail("stream_declaration_malformed")
    key = _require_member(item.data_requirement_key, DataRequirementKey, "stream_data_requirement_key")
    if key not in _SUPPORTED_KEYS:
        raise _fail("stream_data_requirement_key_unsupported")
    profile = item.continuity_profile
    interval = item.funding_interval_ns
    if key is DataRequirementKey.ORDER_BOOK:
        if profile is None:
            raise _fail("stream_continuity_profile_missing")
        profile = _require_member(profile, NativeBookContinuityProfile, "stream_continuity_profile")
    elif key in _OPTIONAL_PROFILES:
        if profile is not None:
            profile = _require_member(profile, _OPTIONAL_PROFILES[key], "stream_continuity_profile")  # type: ignore[index]
    elif profile is not None:
        raise _fail("stream_continuity_profile_unexpected")
    if key is DataRequirementKey.FUNDING_RATE:
        interval = _require_positive_int(interval, "stream_funding_interval_ns")
    elif interval is not None:
        raise _fail("stream_funding_interval_unexpected")
    return CaptureStreamDeclaration(
        stream_id=_require_token(item.stream_id, "stream_id"),
        data_requirement_key=key,  # type: ignore[arg-type]
        instrument=_require_instrument(item.instrument),
        series_id=_require_token(item.series_id, "stream_series_id"),
        source_reference=_require_text(item.source_reference, "stream_source_reference"),
        native_epoch_id=_require_token(item.native_epoch_id, "stream_native_epoch_id"),
        continuity_profile=profile,  # type: ignore[arg-type]
        funding_interval_ns=interval,
    )


def _canonical_declaration(item: object) -> CaptureDeclaration:
    if type(item) is not CaptureDeclaration:
        raise _fail("declaration_malformed")
    if type(item.streams) not in (tuple, list) or not item.streams:
        raise _fail("declaration_streams_malformed")
    streams = tuple(_canonical_stream(stream) for stream in item.streams)
    if len({stream.stream_id for stream in streams}) != len(streams):
        raise _fail("stream_id_duplicate")
    if len({(stream.data_requirement_key, stream.instrument) for stream in streams}) != len(streams):
        raise _fail("stream_scope_duplicate")
    return CaptureDeclaration(
        capture_id=_require_token(item.capture_id, "capture_id"),
        source_id=_require_token(item.source_id, "source_id"),
        source_reference=_require_text(item.source_reference, "source_reference"),
        source_object_id=_require_text(item.source_object_id, "source_object_id"),
        source_object_digest=_require_hex64(item.source_object_digest, "source_object_digest"),
        rights_status=_require_member(item.rights_status, SourcePacketRightsStatus, "rights_status"),  # type: ignore[arg-type]
        rights_reference=_require_text(item.rights_reference, "rights_reference"),
        streams=tuple(sorted(streams, key=lambda stream: stream.stream_id)),
    )


def _canonical_levels(values: object, field_name: str) -> tuple[CapturedLevel, ...]:
    if type(values) not in (tuple, list):
        raise _fail(f"{field_name}_malformed")
    levels: list[CapturedLevel] = []
    for item in values:  # type: ignore[union-attr]
        if type(item) is not CapturedLevel:
            raise _fail(f"{field_name}_level_malformed")
        levels.append(
            CapturedLevel(
                price=_require_decimal(item.price, f"{field_name}_price"),
                quantity=_require_decimal(item.quantity, f"{field_name}_quantity"),
            )
        )
    return tuple(levels)


def _canonical_observation(item: object, streams: Mapping[str, CaptureStreamDeclaration]) -> object:
    kind = _OBSERVATION_KINDS.get(type(item))
    if kind is None:
        raise _fail("observation_malformed")
    stream_id = item.stream_id  # type: ignore[attr-defined]
    stream = streams.get(stream_id) if type(stream_id) is str else None
    if stream is None:
        raise _fail("observation_stream_unknown")
    if stream.data_requirement_key is not kind[1]:
        raise _fail("observation_stream_kind_mismatch")
    if type(item) is CapturedBookSnapshot:
        return CapturedBookSnapshot(
            stream_id=stream_id,
            last_update_id=_require_nonnegative_int(item.last_update_id, "snapshot_last_update_id"),
            receipt_ns=_require_positive_int(item.receipt_ns, "snapshot_receipt_ns"),
            bids=_canonical_levels(item.bids, "snapshot_bids"),
            asks=_canonical_levels(item.asks, "snapshot_asks"),
        )
    if type(item) is CapturedBookDelta:
        return CapturedBookDelta(
            stream_id=stream_id,
            first_update_id=_require_nonnegative_int(item.first_update_id, "delta_first_update_id"),
            final_update_id=_require_nonnegative_int(item.final_update_id, "delta_final_update_id"),
            previous_final_update_id=_require_nonnegative_int(
                item.previous_final_update_id, "delta_previous_final_update_id"
            ),
            event_time_ns=_require_positive_int(item.event_time_ns, "delta_event_time_ns"),
            receipt_ns=_require_positive_int(item.receipt_ns, "delta_receipt_ns"),
            bids=_canonical_levels(item.bids, "delta_bids"),
            asks=_canonical_levels(item.asks, "delta_asks"),
        )
    if type(item) is CapturedMarkPrice:
        return CapturedMarkPrice(
            stream_id=stream_id,
            event_time_ns=_require_positive_int(item.event_time_ns, "mark_event_time_ns"),
            receipt_ns=_require_positive_int(item.receipt_ns, "mark_receipt_ns"),
            mark_price=_require_decimal(item.mark_price, "mark_price"),
        )
    if type(item) is CapturedTrade:
        return CapturedTrade(
            stream_id=stream_id,
            trade_id=_require_nonnegative_int(item.trade_id, "trade_id"),
            event_time_ns=_require_positive_int(item.event_time_ns, "trade_event_time_ns"),
            receipt_ns=_require_positive_int(item.receipt_ns, "trade_receipt_ns"),
            price=_require_decimal(item.price, "trade_price"),
            quantity=_require_decimal(item.quantity, "trade_quantity"),
        )
    if type(item) is CapturedIndexPrice:
        return CapturedIndexPrice(
            stream_id=stream_id,
            event_time_ns=_require_positive_int(item.event_time_ns, "index_event_time_ns"),
            receipt_ns=_require_positive_int(item.receipt_ns, "index_receipt_ns"),
            index_price=_require_decimal(item.index_price, "index_price"),
        )
    return CapturedFundingSettlement(
        stream_id=stream_id,
        funding_time_ns=_require_positive_int(item.funding_time_ns, "funding_time_ns"),  # type: ignore[union-attr]
        receipt_ns=_require_positive_int(item.receipt_ns, "funding_receipt_ns"),  # type: ignore[union-attr]
        funding_rate=_require_decimal(item.funding_rate, "funding_rate"),  # type: ignore[union-attr]
    )


def _canonical_observations(values: object, streams: Mapping[str, CaptureStreamDeclaration]) -> tuple[object, ...]:
    if type(values) not in (tuple, list) or not values:
        raise _fail("observations_malformed")
    return tuple(_canonical_observation(item, streams) for item in values)  # type: ignore[union-attr]


def _capture_digest(declaration: CaptureDeclaration, observations: Sequence[object]) -> str:
    """Digest of the exact canonical capture: the declaration and every observation in capture order, kind-tagged."""

    payload = {
        "declaration": _to_payload(declaration),
        "observations": [{"kind": _OBSERVATION_KINDS[type(item)][0], **_to_payload(item)} for item in observations],
    }
    return edge_sha256_text(edge_canonical_json(payload))


# --- native order-book knowledge -------------------------------------------------------------------------------------


@dataclass(frozen=True)
class _Snapshot:
    last_update_id: int
    levels: tuple[dict[int, int], dict[int, int]]
    horizon: tuple[int, int]


@dataclass(frozen=True)
class _Delta:
    final_update_id: int
    previous_final_update_id: int
    event_time_ns: int
    native: tuple[object, ...]
    levels: tuple[dict[int, int], dict[int, int]]


def _covers(side: int, horizon: int | None, price: int) -> bool:
    """Whether ``price`` lies inside a side coverage: bids at or above, asks at or below the horizon."""

    if horizon is None:
        return False
    return price >= horizon if side == _BID else price <= horizon


def _deeper(side: int, current: int | None, candidate: int) -> int:
    if current is None:
        return candidate
    return min(current, candidate) if side == _BID else max(current, candidate)


def _book_side(levels: Sequence[CapturedLevel], *, snapshot: bool) -> dict[int, int] | None:
    """Exact levels of one side, or None for a non-positive price, an invalid quantity or a repeated price."""

    side: dict[int, int] = {}
    for level in levels:
        price = _scaled(level.price)
        quantity = _scaled(level.quantity)
        if price <= 0 or quantity < 0 or (snapshot and quantity == 0) or price in side:
            return None
        side[price] = quantity
    return side


def _parse_snapshot(item: CapturedBookSnapshot, scope: str) -> _Snapshot:
    where = f"{scope}:{item.last_update_id}"
    bids = _book_side(item.bids, snapshot=True)
    asks = _book_side(item.asks, snapshot=True)
    if bids is None or asks is None:
        raise _Violation(f"book_snapshot_level_invalid:{where}")
    if not bids or not asks:
        raise _Violation(f"book_snapshot_side_empty:{where}")
    if max(bids) >= min(asks):
        raise _Violation(f"book_snapshot_crossed:{where}")
    return _Snapshot(item.last_update_id, (bids, asks), (min(bids), max(asks)))


def _parse_delta(item: CapturedBookDelta, scope: str) -> _Delta:
    where = f"{scope}:{item.final_update_id}"
    if not item.previous_final_update_id < item.first_update_id <= item.final_update_id:
        raise _Violation(f"book_delta_span_invalid:{where}")
    if item.receipt_ns < item.event_time_ns:
        raise _Violation(f"book_receipt_before_event:{where}")
    bids = _book_side(item.bids, snapshot=False)
    asks = _book_side(item.asks, snapshot=False)
    if bids is None or asks is None:
        raise _Violation(f"book_delta_level_invalid:{where}")
    native = (item.first_update_id, item.final_update_id, item.previous_final_update_id, item.event_time_ns)
    return _Delta(
        final_update_id=item.final_update_id,
        previous_final_update_id=item.previous_final_update_id,
        event_time_ns=item.event_time_ns,
        native=(*native, bids, asks),
        levels=(bids, asks),
    )


def _delta_agrees(delta: _Delta, snapshot: _Snapshot) -> bool:
    """Same native id: every listed delta level inside the snapshot coverage has exactly the snapshot quantity."""

    for side in (_BID, _ASK):
        listed = snapshot.levels[side]
        for price, quantity in delta.levels[side].items():
            if _covers(side, snapshot.horizon[side], price) and listed.get(price, 0) != quantity:
                return False
    return True


def _snapshots_agree(first: _Snapshot, second: _Snapshot) -> bool:
    """Same native id: each snapshot's listed levels inside the other's coverage carry the same quantity there."""

    for side in (_BID, _ASK):
        for one, other in ((first, second), (second, first)):
            for price, quantity in one.levels[side].items():
                if _covers(side, other.horizon[side], price) and other.levels[side].get(price, 0) != quantity:
                    return False
    return True


def _merged(first: _Snapshot, second: _Snapshot) -> _Snapshot:
    """The union of two agreeing snapshots at one native id: every listed level and the deeper coverage per side.

    Agreement means every price inside both coverages carries one value, so the union never narrows and never
    contradicts either snapshot: comparing a later observation with it is comparing it with each snapshot it holds.
    """

    levels = ({**first.levels[_BID], **second.levels[_BID]}, {**first.levels[_ASK], **second.levels[_ASK]})
    horizon = (
        _deeper(_BID, first.horizon[_BID], second.horizon[_BID]),
        _deeper(_ASK, first.horizon[_ASK], second.horizon[_ASK]),
    )
    return _Snapshot(first.last_update_id, levels, horizon)


class _NativeChain:
    """One native chain of deltas joined by predecessor identity, with the step knowledge of every price.

    ``mentions[side][price]`` holds the chain positions of the deltas listing the price and their quantities.
    ``base[side][price]`` is the known quantity before the first mention (zero = known absent); a price never mentioned
    is otherwise known exactly when the deepest attached snapshot coverage ``horizon`` covers it. ``present`` and
    ``prices`` are the known present levels at the tip. The chain only grows at its tip; it never evicts a fact.
    """

    def __init__(self, start: int) -> None:
        self.start = start
        self.final_ids: list[int] = []
        self.event_times: list[int] = []
        self.mentions: tuple[dict[int, tuple[list[int], list[int]]], ...] = ({}, {})
        self.base: tuple[dict[int, int], ...] = ({}, {})
        self.horizon: list[int | None] = [None, None]
        self.present: tuple[dict[int, int], ...] = ({}, {})
        self.prices: tuple[list[int], ...] = ([], [])

    @property
    def tip(self) -> int:
        return self.final_ids[-1]

    def apply(self, delta: _Delta) -> None:
        position = len(self.final_ids)
        self.final_ids.append(delta.final_update_id)
        self.event_times.append(delta.event_time_ns)
        for side in (_BID, _ASK):
            mentions, base = self.mentions[side], self.base[side]
            present, prices = self.present[side], self.prices[side]
            for price, quantity in delta.levels[side].items():
                entry = mentions.get(price)
                if entry is None:
                    # The first mention freezes what the coverage knew before it.
                    if price not in base and _covers(side, self.horizon[side], price):
                        base[price] = 0
                    entry = ([], [])
                    mentions[price] = entry
                entry[0].append(position)
                entry[1].append(quantity)
                if quantity > 0:
                    if price not in present:
                        bisect.insort(prices, price)
                    present[price] = quantity
                elif price in present:
                    del present[price]
                    del prices[bisect.bisect_left(prices, price)]

    def step(self, side: int, price: int, native_id: int) -> int:
        """Known quantity of ``price`` at ``native_id`` (start <= id <= tip) as a mention, the base step marker, or
        unconstrained when the id lies strictly inside the span of a delta that lists the price."""

        if native_id == self.start:
            return _BASE_STEP
        entry = self.mentions[side].get(price)
        if entry is None:
            return _BASE_STEP
        position = bisect.bisect_left(self.final_ids, native_id)
        indices, quantities = entry
        index = bisect.bisect_left(indices, position)
        if index < len(indices) and indices[index] == position:
            return quantities[index] if self.final_ids[position] == native_id else _UNCONSTRAINED
        return _BASE_STEP if index == 0 else quantities[index - 1]

    def attach(self, snapshot: _Snapshot) -> bool:
        """Project a snapshot at an id inside the span onto the step knowledge; False on any contradiction."""

        native_id = snapshot.last_update_id
        for side in (_BID, _ASK):
            listed, coverage = snapshot.levels[side], snapshot.horizon[side]
            mentions, base, known_horizon = self.mentions[side], self.base[side], self.horizon[side]
            for price, quantity in listed.items():
                value = self.step(side, price, native_id)
                if value == _UNCONSTRAINED:
                    continue
                if value != _BASE_STEP:
                    if value != quantity:
                        return False
                    continue
                known = base.get(price)
                if known is None and price not in mentions and _covers(side, known_horizon, price):
                    known = 0
                if known is None:
                    base[price] = quantity
                elif known != quantity:
                    return False
            for price in mentions:
                if price in listed or not _covers(side, coverage, price):
                    continue
                value = self.step(side, price, native_id)
                if value == _UNCONSTRAINED:
                    continue
                if value != _BASE_STEP:
                    if value != 0:
                        return False
                    continue
                known = base.get(price)
                if known is None:
                    base[price] = 0
                elif known != 0:
                    return False
            for price, known in base.items():
                if known and price not in mentions and price not in listed and _covers(side, coverage, price):
                    return False
        for side in (_BID, _ASK):
            self.horizon[side] = _deeper(side, self.horizon[side], snapshot.horizon[side])
            present, prices = self.present[side], self.prices[side]
            for price, quantity in snapshot.levels[side].items():
                if price not in self.mentions[side] and price not in present:
                    bisect.insort(prices, price)
                    present[price] = quantity
        return True

    def crossed(self) -> bool:
        bids, asks = self.prices
        return bool(bids) and bool(asks) and bids[-1] >= asks[0]

    def best_levels(self, side: int, depth: int) -> list[tuple[int, int]] | None:
        """The exact best ``depth`` levels at the tip, or None while any of them may lie in unknown depth."""

        horizon = self.horizon[side]
        if horizon is None:
            return None
        prices = self.prices[side]
        if side == _BID:
            if len(prices) - bisect.bisect_left(prices, horizon) < depth:
                return None
            chosen = prices[-depth:][::-1]
        else:
            if bisect.bisect_right(prices, horizon) < depth:
                return None
            chosen = prices[:depth]
        return [(price, self.present[side][price]) for price in chosen]


# --- stream processors -----------------------------------------------------------------------------------------------


class _StreamProcessor:
    """Shared stream bookkeeping. The first violation rejects the stream; later observations are not evaluated."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        self.stream = stream
        self.scope = stream.stream_id
        self.violation: str | None = None
        self.observations = 0
        self.replays = 0
        self.records: list[HistoricalPitRecord] = []

    def observe(self, item: object, now: int) -> None:
        if self.violation is not None:
            return
        self.observations += 1
        try:
            self._observe(item, now)
        except _Violation as violation:
            self.violation = _reason(violation.code)

    def finish(self) -> None:
        if self.violation is not None:
            return
        try:
            self._finish()
        except _Violation as violation:
            self.violation = _reason(violation.code)

    def _observe(self, item: object, now: int) -> None:
        raise NotImplementedError

    def _finish(self) -> None:
        return None

    def _record(self, *, sequence_id: int, event_ns: int, available_ns: int, finalized_ns: int, values) -> None:
        self.records.append(
            build_historical_pit_record(
                series_id=self.stream.series_id,
                data_requirement_key=self.stream.data_requirement_key.value,  # type: ignore[union-attr]
                instrument=self.stream.instrument,
                sequence_id=sequence_id,
                event_time_ns=event_ns,
                available_at_ns=available_ns,
                finalized_at_ns=finalized_ns,
                revision_vintage_id=None,
                values=values,
            )
        )

    def _counts(self) -> tuple[int, int, int]:
        return 0, 0, 0

    def summary(self) -> AuthenticatedPitStreamSummary:
        stream = self.stream
        identities = [record.sequence_id for record in self.records]
        chains, attached, unattached = self._counts()
        return AuthenticatedPitStreamSummary(
            stream_id=stream.stream_id,
            data_requirement_key=stream.data_requirement_key.value,  # type: ignore[union-attr]
            instrument=stream.instrument,
            series_id=stream.series_id,
            source_reference=stream.source_reference,
            native_epoch_id=stream.native_epoch_id,
            continuity_profile=None if stream.continuity_profile is None else stream.continuity_profile.value,  # type: ignore[union-attr]
            funding_interval_ns=stream.funding_interval_ns,
            observation_count=self.observations,
            replay_count=self.replays,
            native_chain_count=chains,
            attached_snapshot_count=attached,
            unattached_snapshot_count=unattached,
            record_count=len(self.records),
            first_record_sequence_id=min(identities) if identities else None,
            last_record_sequence_id=max(identities) if identities else None,
        )


class _BookProcessor(_StreamProcessor):
    """Native order-book stream: same-identity truth, native chains, step knowledge and tip emission."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        super().__init__(stream)
        # Integrity evidence kept for the whole capture: every observed delta by final id, and per native id the
        # union of every agreeing snapshot observed there.
        self.deltas: dict[int, _Delta] = {}
        self.snapshots: dict[int, _Snapshot] = {}
        self.chains: list[_NativeChain] = []
        self.pending: list[_Snapshot] = []
        self.attached = 0
        self.unattached = 0
        self.last_event_ns: int | None = None
        self.last_emitted: int | None = None
        self.width = len(str(_BOOK_DEPTH))

    def _counts(self) -> tuple[int, int, int]:
        return len(self.chains), self.attached, self.unattached

    def _observe(self, item: object, now: int) -> None:
        if type(item) is CapturedBookSnapshot:
            self._snapshot(_parse_snapshot(item, self.scope), now)
        else:
            self._delta(_parse_delta(item, self.scope), now)  # type: ignore[arg-type]

    def _delta(self, delta: _Delta, now: int) -> None:
        where = f"{self.scope}:{delta.final_update_id}"
        existing = self.deltas.get(delta.final_update_id)
        if existing is not None:
            if existing.native != delta.native:
                raise _Violation(f"book_native_identity_conflict:{where}")
            self.replays += 1
            return
        known = self.snapshots.get(delta.final_update_id)
        if known is not None and not _delta_agrees(delta, known):
            raise _Violation(f"book_snapshot_delta_conflict:{where}")
        chain = self.chains[-1] if self.chains else None
        if chain is None or delta.previous_final_update_id > chain.tip:
            chain = _NativeChain(delta.previous_final_update_id)
            self.chains.append(chain)
            stranded = [snapshot for snapshot in self.pending if snapshot.last_update_id < chain.start]
            self.unattached += len(stranded)
            self.pending = [snapshot for snapshot in self.pending if snapshot.last_update_id >= chain.start]
        elif delta.previous_final_update_id != chain.tip:
            raise _Violation(f"book_native_sequence_regression:{where}")
        if self.last_event_ns is not None and delta.event_time_ns < self.last_event_ns:
            raise _Violation(f"book_event_time_regression:{where}")
        self.last_event_ns = delta.event_time_ns
        self.deltas[delta.final_update_id] = delta
        chain.apply(delta)
        waiting: list[_Snapshot] = []
        for snapshot in self.pending:
            if snapshot.last_update_id <= chain.tip:
                self._attach(chain, snapshot)
            else:
                waiting.append(snapshot)
        self.pending = waiting
        self._settle(chain, now)

    def _snapshot(self, snapshot: _Snapshot, now: int) -> None:
        native_id = snapshot.last_update_id
        where = f"{self.scope}:{native_id}"
        known = self.snapshots.get(native_id)
        if known is not None and not _snapshots_agree(snapshot, known):
            raise _Violation(f"book_snapshot_conflict:{where}")
        delta = self.deltas.get(native_id)
        if delta is not None and not _delta_agrees(delta, snapshot):
            raise _Violation(f"book_snapshot_delta_conflict:{where}")
        self.snapshots[native_id] = snapshot if known is None else _merged(known, snapshot)
        for chain in reversed(self.chains):
            if chain.start <= native_id:
                if native_id <= chain.tip:
                    self._attach(chain, snapshot)
                    self._settle(chain, now)
                    return
                break
        if not self.chains or native_id > self.chains[-1].tip:
            self.pending.append(snapshot)
        else:
            self.unattached += 1

    def _attach(self, chain: _NativeChain, snapshot: _Snapshot) -> None:
        if not chain.attach(snapshot):
            raise _Violation(f"book_knowledge_conflict:{self.scope}:{snapshot.last_update_id}")
        self.attached += 1

    def _settle(self, chain: _NativeChain, now: int) -> None:
        if chain.crossed():
            raise _Violation(f"book_crossed:{self.scope}:{chain.tip}")
        if chain is not self.chains[-1] or (self.last_emitted is not None and chain.tip <= self.last_emitted):
            return
        bids = chain.best_levels(_BID, _BOOK_DEPTH)
        asks = chain.best_levels(_ASK, _BOOK_DEPTH)
        if bids is None or asks is None:
            return
        values = [
            HistoricalPitValue(BEST_BID_PRICE_NAME, _render(bids[0][0])),
            HistoricalPitValue(BEST_BID_QUANTITY_NAME, _render(bids[0][1])),
            HistoricalPitValue(BEST_ASK_PRICE_NAME, _render(asks[0][0])),
            HistoricalPitValue(BEST_ASK_QUANTITY_NAME, _render(asks[0][1])),
        ]
        for name, levels in (("bid", bids), ("ask", asks)):
            for index, (price, quantity) in enumerate(levels, start=1):
                values.append(HistoricalPitValue(f"{name}_{index:0{self.width}d}_price", _render(price)))
                values.append(HistoricalPitValue(f"{name}_{index:0{self.width}d}_quantity", _render(quantity)))
        self._record(
            sequence_id=chain.tip,
            event_ns=chain.event_times[-1],
            available_ns=now,
            finalized_ns=now,
            values=tuple(values),
        )
        self.last_emitted = chain.tip


class _MarkProcessor(_StreamProcessor):
    """Native mark stream: one value per native event time, observed no earlier than that event."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        super().__init__(stream)
        self.marks: dict[int, tuple[int, int]] = {}

    def _observe(self, item: object, now: int) -> None:
        mark: CapturedMarkPrice = item  # type: ignore[assignment]
        where = f"{self.scope}:{mark.event_time_ns}"
        price = _scaled(mark.mark_price)
        if price <= 0:
            raise _Violation(f"mark_price_invalid:{where}")
        if mark.receipt_ns < mark.event_time_ns:
            raise _Violation(f"mark_receipt_before_event:{where}")
        existing = self.marks.get(mark.event_time_ns)
        if existing is not None:
            if existing[0] != price:
                raise _Violation(f"mark_identity_conflict:{where}")
            self.replays += 1
            return
        self.marks[mark.event_time_ns] = (price, mark.receipt_ns)

    def _finish(self) -> None:
        for event_ns in sorted(self.marks):
            price, receipt_ns = self.marks[event_ns]
            self._record(
                sequence_id=event_ns,
                event_ns=event_ns,
                available_ns=receipt_ns,
                finalized_ns=event_ns,
                values=(HistoricalPitValue(MARK_VALUE_NAME, _render(price)),),
            )


class _FundingProcessor(_StreamProcessor):
    """Final funding stream: one rate per settlement, published no earlier than the settlement, on the governed grid."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        super().__init__(stream)
        self.settlements: dict[int, tuple[int, int]] = {}

    def _observe(self, item: object, now: int) -> None:
        settlement: CapturedFundingSettlement = item  # type: ignore[assignment]
        where = f"{self.scope}:{settlement.funding_time_ns}"
        if settlement.receipt_ns < settlement.funding_time_ns:
            raise _Violation(f"funding_observed_before_settlement:{where}")
        rate = _scaled(settlement.funding_rate)
        existing = self.settlements.get(settlement.funding_time_ns)
        if existing is not None:
            if existing[0] != rate:
                raise _Violation(f"funding_identity_conflict:{where}")
            self.replays += 1
            return
        self.settlements[settlement.funding_time_ns] = (rate, settlement.receipt_ns)

    def _finish(self) -> None:
        interval: int = self.stream.funding_interval_ns  # type: ignore[assignment]
        times = sorted(self.settlements)
        for earlier, later in zip(times, times[1:], strict=False):
            if later - earlier != interval:
                raise _Violation(f"funding_interval_inconsistent:{self.scope}:{later}")
        for settlement_ns in times:
            if settlement_ns - interval <= 0:
                raise _Violation(f"funding_window_open_invalid:{self.scope}:{settlement_ns}")
        for settlement_ns in times:
            rate, receipt_ns = self.settlements[settlement_ns]
            self._record(
                sequence_id=settlement_ns // interval,
                event_ns=settlement_ns - interval,
                available_ns=receipt_ns,
                finalized_ns=settlement_ns,
                values=(HistoricalPitValue(FUNDING_VALUE_NAME, _render(rate)),),
            )


class _TradeProcessor(_StreamProcessor):
    """Native trade stream: one trade per native id; under ``contiguous_trade_id.v1`` its contiguous runs are named."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        super().__init__(stream)
        self.contiguous = stream.continuity_profile is NativeTradeContinuityProfile.CONTIGUOUS_TRADE_ID_V1
        self.trades: dict[int, tuple[int, int, int]] = {}
        self.newest: tuple[int, int] | None = None
        self.run_first = 0
        self.runs = 0

    def _counts(self) -> tuple[int, int, int]:
        return self.runs, 0, 0

    def _observe(self, item: object, now: int) -> None:
        trade: CapturedTrade = item  # type: ignore[assignment]
        where = f"{self.scope}:{trade.trade_id}"
        price, quantity = _scaled(trade.price), _scaled(trade.quantity)
        if price <= 0 or quantity <= 0:
            raise _Violation(f"trade_value_invalid:{where}")
        if trade.receipt_ns < trade.event_time_ns:
            raise _Violation(f"trade_receipt_before_event:{where}")
        native = (trade.event_time_ns, price, quantity)
        existing = self.trades.get(trade.trade_id)
        if existing is not None:
            if existing != native:
                raise _Violation(f"trade_identity_conflict:{where}")
            self.replays += 1
            return
        values = [
            HistoricalPitValue(TRADE_PRICE_VALUE_NAME, _render(price)),
            HistoricalPitValue(TRADE_QUANTITY_VALUE_NAME, _render(quantity)),
        ]
        if self.contiguous:
            # The run of a trade is fixed at its receipt: an older id arriving later would rewrite a published run.
            if self.newest is not None and trade.trade_id < self.newest[0]:
                raise _Violation(f"trade_native_id_regression:{where}")
            if self.newest is not None and trade.event_time_ns < self.newest[1]:
                raise _Violation(f"trade_event_time_regression:{where}")
            if self.newest is None or trade.trade_id != self.newest[0] + 1:
                self.run_first, self.runs = trade.trade_id, self.runs + 1  # capture start or a native gap
            self.newest = (trade.trade_id, trade.event_time_ns)
            values.append(HistoricalPitValue(TRADE_RUN_FIRST_ID_VALUE_NAME, _render(self.run_first * _UNIT)))
        self.trades[trade.trade_id] = native
        self._record(
            sequence_id=trade.trade_id,
            event_ns=trade.event_time_ns,
            available_ns=trade.receipt_ns,
            finalized_ns=trade.event_time_ns,
            values=tuple(values),
        )


class _IndexProcessor(_StreamProcessor):
    """Native index-price stream: one value per native event time; under ``index_one_per_utc_second.v1`` at most one
    value per UTC second, each record naming its second."""

    def __init__(self, stream: CaptureStreamDeclaration) -> None:
        super().__init__(stream)
        self.slotted = stream.continuity_profile is NativeIndexPublicationProfile.ONE_PER_UTC_SECOND_V1
        self.prices: dict[int, tuple[int, int]] = {}
        self.slots: set[int] = set()

    def _observe(self, item: object, now: int) -> None:
        index: CapturedIndexPrice = item  # type: ignore[assignment]
        where = f"{self.scope}:{index.event_time_ns}"
        price = _scaled(index.index_price)
        if price <= 0:
            raise _Violation(f"index_price_invalid:{where}")
        if index.receipt_ns < index.event_time_ns:
            raise _Violation(f"index_receipt_before_event:{where}")
        existing = self.prices.get(index.event_time_ns)
        if existing is not None:
            if existing[0] != price:
                raise _Violation(f"index_identity_conflict:{where}")
            self.replays += 1
            return
        if self.slotted:
            slot = index.event_time_ns // _NS_PER_SECOND
            if slot in self.slots:
                raise _Violation(f"index_publication_slot_conflict:{where}")
            self.slots.add(slot)
        self.prices[index.event_time_ns] = (price, index.receipt_ns)

    def _finish(self) -> None:
        for event_ns in sorted(self.prices):
            price, receipt_ns = self.prices[event_ns]
            values = [HistoricalPitValue(INDEX_PRICE_VALUE_NAME, _render(price))]
            if self.slotted:
                slot = event_ns // _NS_PER_SECOND
                values.append(HistoricalPitValue(INDEX_UTC_SECOND_SLOT_VALUE_NAME, _render(slot * _UNIT)))
            self._record(
                sequence_id=event_ns,
                event_ns=event_ns,
                available_ns=receipt_ns,
                finalized_ns=event_ns,
                values=tuple(values),
            )


_PROCESSORS: dict[DataRequirementKey, Callable[[CaptureStreamDeclaration], _StreamProcessor]] = {
    DataRequirementKey.ORDER_BOOK: _BookProcessor,
    DataRequirementKey.MARK_PRICE: _MarkProcessor,
    DataRequirementKey.FUNDING_RATE: _FundingProcessor,
    DataRequirementKey.LAST_TRADE: _TradeProcessor,
    DataRequirementKey.INDEX_PRICE: _IndexProcessor,
}


# --- authority and lineage -------------------------------------------------------------------------------------------


def _manifest_codes(
    manifest: EdgeSourcePacketEvidence, *, manifest_anchor: str, registry_anchor: str, correlation_id: str
) -> list[str]:
    verification = verify_edge_source_packet_evidence(manifest)
    if not verification.intact:
        return [_reason(f"source_manifest_integrity_failure:{code}") for code in verification.reason_codes]
    if verification.recomputed_digest != manifest_anchor:
        return [_reason("source_manifest_digest_mismatch")]
    if manifest.correlation_id != correlation_id:
        return [_reason("source_manifest_correlation_mismatch")]
    if manifest.status is not EdgeEvidenceStatus.READY:
        return [_reason("source_manifest_rejected")]
    if manifest.data_requirement_registry_digest != registry_anchor:
        return [_reason("data_requirement_registry_mismatch")]
    return []


def _semantics_codes(stream: CaptureStreamDeclaration, record: EdgeSourceSeriesRecord) -> list[str]:
    ref = stream.stream_id
    expected: list[tuple[str, object]] = [
        ("registry_requirement_bound", True),
        ("finality", _FINALIZED_ONLY),
        ("revision_policy", _IMMUTABLE_AFTER_FINALIZATION),
        *_REGISTRY_SEMANTICS[stream.data_requirement_key],  # type: ignore[index]
    ]
    codes: list[str] = []
    for name, value in expected:
        carried = getattr(record, name)
        if type(carried) is not type(value) or carried != value:
            codes.append(_reason(f"series_semantics_unsupported:{ref}:{name}"))
    return codes


def _lineage_codes(manifest: EdgeSourcePacketEvidence, declaration: CaptureDeclaration) -> list[str]:
    """Every stream binds exactly its EF-3 series: key, instrument, source, rights and implemented semantics."""

    series = {record.series_id: record for record in manifest.series}
    codes: list[str] = []
    for stream in declaration.streams:
        ref = stream.stream_id
        record = series.get(stream.series_id)
        if record is None:
            codes.append(_reason(f"series_missing:{ref}"))
            continue
        if record.data_requirement_key != stream.data_requirement_key.value:  # type: ignore[union-attr]
            codes.append(_reason(f"series_key_mismatch:{ref}"))
            continue
        if stream.instrument not in record.instrument_coverage:
            codes.append(_reason(f"series_instrument_foreign:{ref}"))
        if record.source_reference != stream.source_reference:
            codes.append(_reason(f"series_lineage_mismatch:{ref}:source_reference"))
        if record.rights_status != declaration.rights_status.value:  # type: ignore[union-attr]
            codes.append(_reason(f"series_lineage_mismatch:{ref}:rights_status"))
        if record.rights_reference != declaration.rights_reference:
            codes.append(_reason(f"series_lineage_mismatch:{ref}:rights_reference"))
        codes.extend(_semantics_codes(stream, record))
    return codes


def _process_capture(
    observations: Sequence[object], processors: Mapping[str, _StreamProcessor]
) -> tuple[list[str], list[HistoricalPitRecord]]:
    """Replay the capture in its own receipt order; any violation rejects it before a single record is published."""

    previous = 0
    for index, item in enumerate(observations):
        if item.receipt_ns < previous:
            return [_reason(f"capture_receipt_regression:{index}")], []
        previous = item.receipt_ns
        processors[item.stream_id].observe(item, item.receipt_ns)
    for processor in processors.values():
        processor.finish()
    codes = [processor.violation for processor in processors.values() if processor.violation is not None]
    if codes:
        return codes, []  # type: ignore[return-value]
    records = [record for processor in processors.values() for record in processor.records]
    if not records:
        return [_reason("capture_without_records")], []
    return [], records


# --- evidence --------------------------------------------------------------------------------------------------------


def _assemble(inputs: object) -> AuthenticatedPitIngressResult:
    """The one ingress assembly path, shared by the builder and the verifier reassembly.

    Order: structural canonicalization (construction errors) → EF-3 and registry re-proof → stream lineage → capture
    replay → dataset through the accepted builder → verdict. Any integrity reason rejects the whole capture and no
    dataset is returned.
    """

    if type(inputs) is not AuthenticatedPitIngressInputs:
        raise _fail("inputs_malformed")
    ingress_id = _require_text(inputs.ingress_id, "ingress_id")
    correlation_id = _require_text(inputs.correlation_id, "correlation_id")
    dataset_id = _require_text(inputs.dataset_id, "dataset_id")
    manifest = inputs.source_manifest
    if type(manifest) is not EdgeSourcePacketEvidence:
        raise _fail("source_manifest_malformed")
    manifest_anchor = _require_hex64(inputs.expected_source_manifest_digest, "expected_source_manifest_digest")
    registry_anchor = _require_hex64(
        inputs.expected_data_requirement_registry_digest, "expected_data_requirement_registry_digest"
    )
    declaration = _canonical_declaration(inputs.declaration)
    streams = {stream.stream_id: stream for stream in declaration.streams}
    observations = _canonical_observations(inputs.observations, streams)
    capture_digest = _capture_digest(declaration, observations)
    processors = {
        stream.stream_id: _PROCESSORS[stream.data_requirement_key](stream)  # type: ignore[index]
        for stream in declaration.streams
    }

    codes = _manifest_codes(
        manifest, manifest_anchor=manifest_anchor, registry_anchor=registry_anchor, correlation_id=correlation_id
    )
    if not codes:
        codes = _lineage_codes(manifest, declaration)
    dataset: HistoricalPitDataset | None = None
    if not codes:
        codes, records = _process_capture(observations, processors)
        if not codes:
            try:
                dataset = build_historical_pit_dataset(
                    manifest,
                    expected_source_manifest_digest=manifest_anchor,
                    expected_data_requirement_registry_digest=registry_anchor,
                    dataset_id=dataset_id,
                    correlation_id=correlation_id,
                    source_reference=declaration.source_reference,
                    rights_status=declaration.rights_status,
                    rights_reference=declaration.rights_reference,
                    records=records,
                )
            except HistoricalPitDatasetError as error:
                codes = [_reason(f"dataset_construction_refused:{error}")]
            else:
                if dataset.status is not EdgeEvidenceStatus.READY:
                    codes = [_reason(f"dataset_rejected:{code}") for code in dataset.integrity_reason_codes]
                    dataset = None
    integrity = _sorted_unique(codes)

    if integrity or dataset is None:
        status, verdict, verdict_reasons = EdgeEvidenceStatus.REJECTED, EdgeGateVerdict.NOT_EVALUATED, ()
        dataset = None
    else:
        fail: list[str] = []
        needs_external = [_reason(code) for code in _EXTERNAL_FACT_REASONS]
        needs_governance: list[str] = []
        if declaration.rights_status is SourcePacketRightsStatus.RESTRICTED:
            fail.append(_reason("capture_rights_restricted"))
        if dataset.advances is not True:
            code = _reason(f"dataset_not_advanced:{dataset.gate_verdict.value}")
            if dataset.gate_verdict is EdgeGateVerdict.NEEDS_EXTERNAL_FACTS:
                needs_external.append(code)
            elif dataset.gate_verdict is EdgeGateVerdict.NEEDS_GOVERNANCE_APPROVAL:
                needs_governance.append(code)
            else:
                fail.append(code)
        status = EdgeEvidenceStatus.READY
        verdict = resolve_edge_gate_verdict(fail, needs_external, needs_governance)
        verdict_reasons = _sorted_unique(fail + needs_external + needs_governance)

    market = any(stream.data_requirement_key in _MARKET_KEYS for stream in declaration.streams)
    seed = AuthenticatedPitIngressEvidence(
        schema_version=_MARKET_SCHEMA_VERSION if market else _SCHEMA_VERSION,
        status=status,
        gate_verdict=verdict,
        advances=status is EdgeEvidenceStatus.READY and verdict is EdgeGateVerdict.PASS,
        ingress_id=ingress_id,
        correlation_id=correlation_id,
        dataset_id=dataset_id,
        capture_id=declaration.capture_id,
        source_id=declaration.source_id,
        source_reference=declaration.source_reference,
        source_object_id=declaration.source_object_id,
        source_object_digest=declaration.source_object_digest,
        rights_status=declaration.rights_status.value,  # type: ignore[union-attr]
        rights_reference=declaration.rights_reference,
        source_manifest_digest=manifest_anchor,
        data_requirement_registry_digest=registry_anchor,
        continuity_profile_qualification=_PROFILE_QUALIFICATION,
        book_record_depth=_BOOK_DEPTH,
        streams=tuple(processors[stream_id].summary() for stream_id in sorted(processors)),
        observation_count=len(observations),
        capture_digest=capture_digest,
        dataset_digest="" if dataset is None else dataset.dataset_digest,
        record_count=0 if dataset is None else len(dataset.records),
        integrity_reason_codes=integrity,
        verdict_reason_codes=verdict_reasons,
        ingress_digest="",
    )
    evidence = replace(seed, ingress_digest=edge_payload_digest(_to_payload(seed), _SELF_DIGEST_FIELD))
    return AuthenticatedPitIngressResult(evidence=evidence, dataset=dataset)


def build_authenticated_pit_ingress(inputs: AuthenticatedPitIngressInputs) -> AuthenticatedPitIngressResult:
    """Build ingress evidence and, when READY, the PIT dataset of one offline capture.

    Malformed caller input, an unsupported declaration (including an unknown continuity profile) or a forbidden scope
    token raises ``AuthenticatedPitIngressError``. An EF-3 or registry authority that fails re-proof, a lineage or
    semantics mismatch, or any contradictory, incomplete or invalid capture fact yields ``REJECTED``/``NOT_EVALUATED``
    with no dataset. Otherwise the evidence is ``READY`` and never advances (``NEEDS_EXTERNAL_FACTS`` or ``FAIL``).
    """

    return _assemble(inputs)


def authenticated_pit_ingress_evidence_to_dict(evidence: AuthenticatedPitIngressEvidence) -> dict[str, object]:
    """Canonical JSON-ready mapping for ingress evidence, including its self-digest."""

    return _to_payload(evidence)


def authenticated_pit_ingress_evidence_digest(evidence: AuthenticatedPitIngressEvidence) -> str:
    """Recompute the canonical evidence digest, excluding only ``ingress_digest``."""

    return edge_payload_digest(_to_payload(evidence), _SELF_DIGEST_FIELD)


# --- strict parsing ----------------------------------------------------------------------------------------------------


def _as_str(value: object) -> str:
    if type(value) is not str:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_str(value: object) -> str | None:
    return None if value is None else _as_str(value)


def _as_bool(value: object) -> bool:
    if type(value) is not bool:
        raise _fail("payload_field_malformed")
    return value


def _as_int(value: object) -> int:
    if type(value) is not int or value < 0 or value > _MAX_WIRE_INT:
        raise _fail("payload_field_malformed")
    return value


def _as_optional_int(value: object) -> int | None:
    return None if value is None else _as_int(value)


def _as_str_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_as_str(item) for item in value)


def _as_enum(enum_cls: type[Enum]) -> Callable[[object], Enum]:
    def convert(value: object) -> Enum:
        try:
            return enum_cls(_as_str(value))
        except ValueError as exc:
            raise _fail("payload_field_malformed") from exc

    return convert


def _parse_exact(cls: type, payload: object, converters: Mapping[str, Callable[[object], object]]) -> object:
    names = [field.name for field in fields(cls)]
    if type(payload) is not dict or set(payload) != set(names):
        raise _fail("payload_fields_malformed")
    return cls(**{name: converters.get(name, _as_str)(payload[name]) for name in names})


_SUMMARY_CONVERTERS: dict[str, Callable[[object], object]] = {
    "continuity_profile": _as_optional_str,
    "funding_interval_ns": _as_optional_int,
    "observation_count": _as_int,
    "replay_count": _as_int,
    "native_chain_count": _as_int,
    "attached_snapshot_count": _as_int,
    "unattached_snapshot_count": _as_int,
    "record_count": _as_int,
    "first_record_sequence_id": _as_optional_int,
    "last_record_sequence_id": _as_optional_int,
}


def _as_summaries(value: object) -> tuple[AuthenticatedPitStreamSummary, ...]:
    if type(value) is not list:
        raise _fail("payload_field_malformed")
    return tuple(_parse_exact(AuthenticatedPitStreamSummary, entry, _SUMMARY_CONVERTERS) for entry in value)  # type: ignore[misc]


_EVIDENCE_CONVERTERS: dict[str, Callable[[object], object]] = {
    "status": _as_enum(EdgeEvidenceStatus),
    "gate_verdict": _as_enum(EdgeGateVerdict),
    "advances": _as_bool,
    "book_record_depth": _as_int,
    "streams": _as_summaries,
    "observation_count": _as_int,
    "record_count": _as_int,
    "integrity_reason_codes": _as_str_tuple,
    "verdict_reason_codes": _as_str_tuple,
    **dict.fromkeys(_FLAG_NAMES, _as_bool),
}


def authenticated_pit_ingress_evidence_from_payload(payload: object) -> AuthenticatedPitIngressEvidence:
    """Strictly reconstruct ingress evidence from its serialized payload (exact fields and types; no semantic proof)."""

    return _parse_exact(AuthenticatedPitIngressEvidence, payload, _EVIDENCE_CONVERTERS)  # type: ignore[return-value]


def _reassemble_evidence(inputs: object) -> AuthenticatedPitIngressEvidence:
    return _assemble(inputs).evidence


def verify_authenticated_pit_ingress(evidence: object, inputs: object) -> EdgeEvidenceVerification:
    """Re-prove ingress evidence against the exact capture inputs by strict parse and full reassembly. Total."""

    return verify_edge_artifact_total(
        evidence,
        cls=AuthenticatedPitIngressEvidence,
        to_payload=_to_payload,
        parse_payload=authenticated_pit_ingress_evidence_from_payload,
        reassemble=lambda _parsed: _reassemble_evidence(inputs),
        self_digest_field=_SELF_DIGEST_FIELD,
        reason=_reason,
    )


__all__ = [
    "AUTHENTICATED_PIT_INGRESS_NON_CLAIM_FLAGS",
    "INDEX_PRICE_VALUE_NAME",
    "INDEX_UTC_SECOND_SLOT_VALUE_NAME",
    "TRADE_PRICE_VALUE_NAME",
    "TRADE_QUANTITY_VALUE_NAME",
    "TRADE_RUN_FIRST_ID_VALUE_NAME",
    "AuthenticatedPitIngressError",
    "AuthenticatedPitIngressEvidence",
    "AuthenticatedPitIngressInputs",
    "AuthenticatedPitIngressResult",
    "AuthenticatedPitStreamSummary",
    "CaptureDeclaration",
    "CaptureStreamDeclaration",
    "CapturedBookDelta",
    "CapturedBookSnapshot",
    "CapturedFundingSettlement",
    "CapturedIndexPrice",
    "CapturedLevel",
    "CapturedMarkPrice",
    "CapturedTrade",
    "NativeBookContinuityProfile",
    "NativeIndexPublicationProfile",
    "NativeTradeContinuityProfile",
    "authenticated_pit_ingress_evidence_digest",
    "authenticated_pit_ingress_evidence_from_payload",
    "authenticated_pit_ingress_evidence_to_dict",
    "build_authenticated_pit_ingress",
    "verify_authenticated_pit_ingress",
]
